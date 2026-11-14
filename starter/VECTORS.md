# Embedding local và PostgreSQL + pgvector

Từ `starter/`, với venv đã activate:

```powershell
python -m pip install -r requirements.txt
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py
python -m src.ingest_vectors
```

`requirements-lock.txt` lưu phiên bản đầy đủ của venv đã chạy thành công; có thể
dùng `python -m pip install -r requirements-lock.txt` để tái tạo đúng các phiên bản.

Lệnh ingest tự kiểm tra input đã chốt, tạo embedding thật cho toàn bộ chunk A/B,
lưu vào PostgreSQL, nạp lại lần hai và kiểm tra count không đổi. C dùng chung B,
không tạo embedding hoặc index riêng. Không chạy câu hỏi benchmark dev/test.

Nếu tạo môi trường mới trên Python 3.15 và PyYAML báo thiếu Visual C++ compiler,
cài bản Python thuần trước rồi chạy lại requirements (không đổi thuật toán embedding):

```powershell
$env:PYYAML_FORCE_LIBYAML = '0'
python -m pip install PyYAML==6.0.3
python -m pip install -r requirements.txt
```

Biến trên chỉ áp dụng cho terminal hiện tại. Đây là tùy chọn build chính thức trong
[PyYAML setup.py](https://github.com/yaml/pyyaml/blob/6.0.3/setup.py).

## Model và cách encode

- Local CPU, `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- Revision cố định `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, 384 chiều.
- Model đa ngữ có cả vi/en theo [model card](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2).
- Cùng `encode` cho query/document, không prefix/prompt, normalize L2.
- Giữ max sequence length từ model; cắt bên phải nếu vượt giới hạn. 500 ký tự
  không đồng nghĩa 500 token. In cảnh báo và lưu số chunk bị cắt theo từng cấu hình,
  tổng token trước cắt, giới hạn token trong receipt. Cắt token là một hạn chế của
  embedding; text lưu trong database vẫn đầy đủ để truy nguồn.
- Không có API key/chi phí API; thời gian máy, điện và tải mạng không được định giá.
- Model tải lần đầu về `.cache/` ở gốc repo (Git ignore); có thể cần vài trăm MB.
- Lỗi model hoặc DB dừng lệnh; không thay bằng vector ngẫu nhiên/mock.

API encoding/revision: [SentenceTransformer](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html).
Model signature gồm tên/revision, chiều, preprocessing và phiên bản thư viện;
query dùng model khác bị chặn cho đến khi ingest lại.

## Database

Đọc DATABASE_URL từ `starter/.env`; không ghi DSN/key vào receipt. Dùng schema riêng
`day6_ingestion`, bảng `indexes` lưu signature và bảng `chunks` lưu vector, text,
source/page/document_id cùng metadata JSONB. Dùng cosine `<=>`, xếp chính xác
(không HNSW/IVFFlat), tie-break bằng chunk_id; score = 1 - cosine distance.
Theo [pgvector](https://github.com/pgvector/pgvector), mặc định search là exact.

Filter chỉ cho phép key Type dạng string, tham số hóa bằng JSONB. A/B không lọc;
C trỏ B và lọc khi query có filter, không có filter thì cùng kết quả B.

`upsert` nhận **toàn bộ snapshot của một strategy** trong một transaction:
upsert theo primary key (strategy,chunk_id), xóa ID cũ không còn trong snapshot,
và cập nhật signature. Không dùng hàm này cho một batch tài liệu nhỏ. Lỗi rollback.
Tài liệu đổi: chạy lại prepare_corpus/prepare_chunks và review/version benchmark
trước khi ingest; hash đã chốt sẽ chặn corpus thay đổi âm thầm. Không xóa volume.

## Kiểm tra và output

`results/ingestion.json` (bản mới nhất) và `results/ingestion_runs/<run_id>.json`
(lịch sử, kể cả lần lỗi) ghi model, revision, runtime packages, phiên bản DB,
hash chunk, token stats, thời gian encode/store/reingest, count trước/sau và
technical smoke checks. Đây không phải Hit@k hoặc nhãn audit chất lượng.
Nếu lỗi, receipt ghi stage/error_type để không lộ thông tin kết nối.

Contract checks dùng embedding thật trong schema tạm `day6_check_<uuid>` rồi xóa
đúng schema đó: nạp không trùng, xóa chunk cũ, persistence, filter, cosine tự khớp,
vector sai chiều, rollback khi lỗi DB và chặn model/filter không hợp lệ.
Smoke query riêng không thuộc benchmark kiểm tra top-3 và cả ba giá trị Type.

Sau khi ingest, có thể thử query tự chọn:

```powershell
python -m src.search_vectors --strategy C --type Process --question "Tìm nội dung liên quan đến lập trình Python."
```

Không dùng output test để chỉnh cấu hình. Benchmark runner, metrics, trace dev/test
và audit thủ công sẽ được hiện thực ở bước tiếp theo.

## Lần chạy đã kiểm chứng

Xem receipt thực tế: A 488 vector, B 576 vector (384 chiều), C dùng chung B.
Count không đổi sau lần upsert thứ hai. Cả 9 database contract checks và 6 smoke
search/filter checks đều qua. Model mặc định 128 token: A có 177/488 chunk, B có
57/576 chunk vượt giới hạn và bị cắt bên phải khi encode; đây là giới hạn cần
phân tích trong báo cáo, chưa phải bằng chứng về chất lượng retrieval.
