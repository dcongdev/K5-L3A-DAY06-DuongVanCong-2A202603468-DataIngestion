# Data Ingestion Engineering — Python PEP Corpus

**Dương Văn Công · 2A202603468 · L3A**

Tôi xây dựng pipeline đọc tài liệu PEP dạng RST, chuẩn hóa và chia dữ liệu,
tạo embedding đa ngữ, lưu vào PostgreSQL + pgvector rồi so sánh ba cấu hình
truy xuất trên cùng bộ câu hỏi. Bài thực hành tập trung vào chuẩn bị dữ liệu,
truy vết nguồn và đánh giá retrieval.

## Kết quả chính

Corpus gồm PEP 1, 8, 257, 498, 572 và 636: **194.270 ký tự chuẩn hóa, 117 đơn vị
nguồn**, mỗi đơn vị ít nhất 1.500 ký tự. Benchmark có **15 câu dev / 5 câu test**,
5 câu có Type filter, gồm 2 câu test.

| Cấu hình | Chunking | Số vector | Dev Hit@1 | Dev Hit@3 | Test Hit@1 | Test Hit@3 |
|---|---|---:|---:|---:|---:|---:|
| A | Fixed 500 ký tự, overlap 50 | 488 | 3/15 | 4/15 | 1/5 | 2/5 |
| B | Đoạn/heading, tối đa 500 ký tự | 576 | 4/15 | 9/15 | 4/5 | 5/5 |
| C | Chunk/vector B + Type filter khi có | dùng B | 4/15 | 9/15 | 4/5 | 5/5 |

C được chốt từ dev trước test. B/C bằng điểm; C thắng theo tổng thời gian search
dev trong lần chạy này. Đây không phải kết luận C tốt hơn trên mọi dữ liệu.

| Cấu hình | Coherence /2 (10 mẫu) | Grounding /2 (5 câu) | Metadata đúng/đủ |
|---|---:|---:|---:|
| A | 1,0 | 1,4 | 15/15 |
| B | 1,8 | 2,0 | 15/15 |
| C | 1,8 | 2,0 | 15/15 |

Báo cáo đầy đủ: [2A202603468_DuongVanCong.md](report/individual/2A202603468_DuongVanCong.md).
Phân tích từng lỗi: [audit_analysis.md](report/audit_analysis.md).

## Môi trường

- Windows PowerShell, Docker Desktop, Python và venv.
- Môi trường đã chạy: Python 3.15.2, Sentence Transformers 5.7.0,
  Transformers 5.22.2, PyTorch 2.15.0, PostgreSQL 16.16, pgvector 0.8.7.
- Model local CPU: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`,
  revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, 384 chiều, L2 normalize.
- Query/document dùng cùng encode, không prefix; cosine exact search, top-k=3.
- Model mặc định 128 token: 177 chunk A và 57 chunk B bị cắt khi encode;
  text và offset lưu vẫn đầy đủ. Chi phí API bằng 0, chưa định giá điện/phần cứng.

## Setup lần đầu

Từ gốc repo:

```powershell
cd starter
python -m venv .venv
.\.venv\Scripts\Activate.ps1
$env:PYYAML_FORCE_LIBYAML = '0'
python -m pip install -r requirements-lock.txt
```

Nếu đã có venv thì chỉ activate, không cần tạo lại. Biến PyYAML dùng bản Python
thuần trên môi trường thiếu compiler; xem [VECTORS.md](starter/VECTORS.md).

Tạo `starter/.env` từ mẫu nếu file chưa tồn tại, giữ cấu hình DATABASE_URL local:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py
```

Mở Docker Desktop trước và đợi engine sẵn sàng. PostgreSQL mở cổng local 55433;
không cần API key vì model chạy local. Lần ingest đầu cần mạng để tải model.

## Kiểm tra artifact đã lưu

Các lệnh dưới chạy từ `starter/`, không cần database:

```powershell
python -m unittest discover -s tests -v
python -m src.validate_benchmark
python -m src.validate_audit
```

## Chạy lại pipeline

Từ `starter/`, sau khi setup và activate venv:

```powershell
python -m src.prepare_corpus
python -m src.validate_benchmark
python -m src.prepare_chunks
python -m src.ingest_vectors
python -m src.benchmark_runner --split all
```

Pipeline đọc `data/raw/` ở **gốc repo**, không phải `starter/data/`.
Benchmark chạy dev, lưu selection rồi mới chạy test. Mỗi lần benchmark tạo thư
mục kết quả mới, không ghi đè lần cũ. Chạy `python -m src.run` chỉ chạy dev.
Xem [BENCHMARK_RUN.md](starter/BENCHMARK_RUN.md) nếu muốn chạy dev/test riêng.

Audit hiện tại gắn với hash đầu vào của run gốc. Tạo lại manifest/chunk summary
sẽ thay timestamp/thời gian và có thể làm kiểm tra audit cũ báo input thay đổi;
cần lưu và kiểm tra artifact gốc trước khi tái tạo, sau đó lập audit cho phiên
bản mới. Không cập nhật hash cũ để che khác biệt. Không dùng kết quả test đã xem
để tinh chỉnh rồi báo lần sau như holdout mới.

## Sau khi khởi động lại máy

Mở Docker Desktop, activate venv trong terminal rồi chạy từ `starter/`:

```powershell
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py
```

Không cần ingest lại vì Docker volume giữ vector. Thử query riêng:

```powershell
python -m src.search_vectors --strategy C --type Process --question "Tìm nội dung liên quan đến lập trình Python."
```

Dừng database và giữ dữ liệu: `docker compose -p day6_student_starter stop`.

## Cấu trúc và minh chứng

| Đường dẫn | Nội dung |
|---|---|
| `data/raw/` | 6 file RST gốc |
| `data/manifest.json` | Nguồn, quyền, snapshot, hash và ranh giới đơn vị |
| `data/processed/` | Văn bản chuẩn hóa, line_map, units.jsonl |
| `data/chunks/` | Chunk A/B và thống kê; C dùng chung B |
| `benchmark/` | Câu hỏi, đáp án/evidence, dev/test và khóa phiên bản |
| `starter/src/` | Các module pipeline và validator |
| `starter/tests/` | Kiểm tra normalization, chunking và metric |
| `artifacts/experiment_log.csv` | Cấu hình, giả thuyết và metric |
| `results/ingestion_runs/` | Lịch sử ingest và kiểm tra database |
| `results/benchmark/20261114T022140610429Z/` | Run được dùng trong báo cáo, 60 trace và selection |
| `results/audit/20261114T022140610429Z/` | 30 nhãn coherence, 15 grounding, 45 metadata records |
| `report/individual/` | Báo cáo cá nhân |

## Nguồn và giới hạn

Nguồn là repository `python/peps`, snapshot khai báo
`155e5bee7d985ef30555b496eb994d24a591f70b`. Quyền public domain hoặc public
domain/CC0 được trích riêng từng file vào manifest. SHA-256 nhận diện file local;
chưa đối chiếu file với snapshot từ xa, chưa biết ngày tải gốc nên accessed_at là null.

Hit cần một chunk đúng nguồn/đơn vị chứa toàn bộ evidence đã ghi sau chuẩn hóa
whitespace. Evidence dài hơn chunk có thể làm metric bảo thủ. Grounding đọc cả
top-3 nên có thể khác Hit@3. Test nhỏ, có nguồn chung dev; mẫu coherence chỉ gồm
10 vị trí PEP 1 và việc đọc không blind. Các giới hạn được phân tích trong báo cáo.

`.env`, key/token, `.venv` và `.cache` không đưa vào Git. Các file hướng dẫn đề bài
như GUIDE.md, BENCHMARK.md và RULES.md được giữ làm tài liệu tham chiếu.
