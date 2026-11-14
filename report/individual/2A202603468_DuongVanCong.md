# Báo cáo cá nhân — Data Ingestion Engineering

**Họ tên:** Dương Văn Công  
**MSSV:** 2A202603468  
**Lớp:** L3A  
**Chủ đề:** Xây dựng kho truy xuất tài liệu Python PEP  
**Ngày tổng hợp:** 14/11/2026

## Mục tiêu

Tôi thực hiện pipeline từ tài liệu RST đến kho vector có khả năng truy vết
nguồn, sau đó so sánh ảnh hưởng của chunking và metadata filter. Tôi giữ cố định
corpus, model, vector store và bộ câu hỏi giữa A/B/C để quan sát thay đổi của
chiến lược dữ liệu. Phạm vi thực hành dừng ở retrieval, không xây chatbot.

## Corpus và xử lý

Tôi sử dụng PEP 1, 8, 257, 498, 572 và 636 trong data/raw/. Snapshot khai báo
là `155e5bee7d985ef30555b496eb994d24a591f70b`. Từng file có tuyên bố quyền public
domain hoặc public domain/CC0; nội dung quyền được lưu trong manifest cùng nguồn
và SHA-256. Chưa xác minh snapshot từ xa hoặc ngày tải gốc; ngày đọc local được
lưu riêng, không dùng thay ngày tải.

| PEP | Nội dung | Ký tự chuẩn hóa | Đơn vị nguồn |
|---|---|---:|---:|
| 1 | Quy trình và hướng dẫn PEP | 39.848 | 23 |
| 8 | Quy ước viết code | 50.090 | 31 |
| 257 | Quy ước docstring | 10.055 | 5 |
| 498 | F-string | 23.528 | 14 |
| 572 | Assignment expression | 46.009 | 29 |
| 636 | Hướng dẫn pattern matching | 24.740 | 15 |
| Tổng | | 194.270 | 117 |

Tôi chuẩn hóa Unicode NFC, newline LF, khoảng trắng cuối dòng và dòng trống;
giữ heading, đoạn, markup RST và thụt lề code. Header chỉ cung cấp các giá trị
thực tế có trong file. Phần References/Footnotes/Bibliography và Copyright/License
được loại khỏi nội dung tính đơn vị; nội dung sau các section này vẫn giữ nếu hợp lệ.

Mỗi đơn vị kết thúc tại ranh giới đoạn đầu tiên đạt 1.500 ký tự; đoạn dài không
bị cắt ở bước này, phần dư ngắn gộp vào đơn vị trước. Không nhân bản để đủ số
lượng. Số ký tự gồm markup và whitespace được giữ. page là số đơn vị nguồn,
không phải trang PDF. Offset 0-based, end-exclusive trong text chuẩn hóa; line_map
truy về dòng và offset của file UTF-8 gốc. Đơn vị nguồn khác với chunk retrieval.

## Công nghệ và cấu hình

- Python 3.15.2; dependency versions lưu trong starter/requirements-lock.txt.
- Sentence Transformers 5.7.0, Transformers 5.22.2, PyTorch 2.15.0, CPU local.
- Model `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, revision
  `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, 384 chiều, normalize L2.
- Query/document cùng encode không prefix; max_seq_length 128, right truncation
  có cảnh báo và token stats. Câu hỏi tiếng Việt, corpus tiếng Anh.
- PostgreSQL 16.16 + pgvector 0.8.7; schema day6_ingestion, cosine exact, top-k=3.
- Metadata document_id/source/page, unit_id và offset phục vụ truy vết; Type lấy
  từ header phục vụ filter. Không đưa gold source hoặc đáp án vào query/filter.
- Upsert toàn snapshot theo strategy và chunk_id trong transaction, xóa ID cũ;
  nạp lại kiểm tra count vẫn 488/576. C dùng B, không tạo thêm embedding.
- API cost bằng 0; điện, phần cứng và lưu trữ local chưa được định giá.

| Cấu hình | Chunking | Overlap | Retrieval |
|---|---|---:|---|
| A | Fixed-size 500 ký tự | 50 | Không filter |
| B | Đoạn/heading, tối đa 500 ký tự | 0 | Không filter |
| C | Dùng chính chunk/vector B | 0 | Type filter khi câu hỏi có yêu cầu |

## Benchmark và thứ tự đánh giá

Tôi dùng 20 câu có đáp án và evidence: q01–q15 dev, q16–q20 test. Các câu filter
là q04/q08/q14 trên dev và q16/q20 trên test. File freeze.json lưu hash của câu
hỏi và corpus; validator đối chiếu vị trí evidence và filter với metadata thật.
Bộ câu hỏi chia cố định theo câu/chủ đề, không document-disjoint; PEP 636 chỉ có
trong gold test nhưng vẫn được ingest cho mọi cấu hình.

Tôi chọn theo dev Hit@3 cao nhất, rồi Hit@1, tổng thời gian search thấp hơn,
cuối cùng A/B/C. Runner lưu selection trước khi chạy test, không lấy điểm test
để sửa cấu hình. Query encode một lần chia sẻ cho A/B/C; thứ tự search xoay vòng.
Timing gồm kết nối DB và nhận kết quả, không gồm encode; warm-up ngoài benchmark,
không reset cache. Run dùng trong báo cáo là `20261114T022140610429Z`.

Minh chứng: [metrics.csv](../../results/benchmark/20261114T022140610429Z/metrics.csv),
[selection.json](../../results/benchmark/20261114T022140610429Z/selection.json),
[trace dev](../../results/benchmark/20261114T022140610429Z/dev_traces.jsonl),
[trace test](../../results/benchmark/20261114T022140610429Z/test_traces.jsonl).

## Phương pháp audit

Tôi dùng cùng corpus 6 PEP, 117 đơn vị nguồn, cùng embedding model 384 chiều,
revision và PostgreSQL + pgvector cho ba cấu hình. A fixed-size 500/overlap 50;
B gom đoạn/heading tối đa 500, không overlap; C dùng đúng chunk/vector B và
thêm Type filter từ câu hỏi. Metric retrieval giữ nguyên kết quả đã chạy.

Coherence: sắp unit_id tăng dần, lấy 10 đơn vị đầu, vị trí start+100 ký tự;
chọn chunk bao phủ vị trí đó có start nhỏ nhất, rồi chunk_id nếu hòa. Quy tắc
được chọn trước gán nhãn coherence, nhưng sau lần chạy retrieval. C dùng lại
nhãn B vì nội dung chunk giống hệt. Mẫu đều từ PEP 1 nên không đại diện toàn corpus.

Thang coherence: 0 không hiểu được do mất chủ thể/cắt ý nghiêm trọng; 1 hiểu
một phần nhưng còn câu/danh sách/ngữ cảnh bị cắt; 2 tự hiểu và giữ trọn ý.
Chấm cả nội dung chunk, không chỉ câu nằm đúng vị trí lấy mẫu.

Grounding: đọc top-3 của cả 5 câu test mỗi cấu hình; 0 không có bằng chứng trả
lời, 1 có nhưng thiếu thành phần/điều kiện, 2 đủ và truy nguồn được. Top-3 có thể
bổ sung bằng chứng cho nhau; điều này không thay định nghĩa Hit@3 cần một chunk
đơn lẻ chứa đủ gold evidence. Không suy nhãn grounding từ boolean Hit@3.

Metadata: đối chiếu 45 bản ghi với manifest, header Type trong RST gốc, số đơn vị,
text và offset văn bản chuẩn hóa cùng bản đồ dòng nguồn. Phần này kiểm tra bằng
code. Chưa xác minh
qua mạng rằng file local trùng snapshot khai báo.

Việc đọc nội dung không blind với kết quả retrieval, có nguy cơ thiên lệch.
Protocol, hash đầu vào và ranh giới lấy mẫu được lưu trong `protocol.json`.

## Kết quả

| Strategy | Dev Hit@1 | Dev Hit@3 | Test Hit@1 | Test Hit@3 |
|---|---|---|---|---|
| A | 3/15 | 4/15 | 1/5 | 2/5 |
| B | 4/15 | 9/15 | 4/5 | 5/5 |
| C | 4/15 | 9/15 | 4/5 | 5/5 |

| Strategy | Coherence /2, n=10 | Metadata đúng/đủ | Đúng phạm vi Type trên câu yêu cầu lọc | Grounding 0/1/2 | Grounding /2 |
|---|---|---|---|---|---|
| A | 1,0 | 15/15 | 1/2 | 1 / 1 / 3 | 1,4 |
| B | 1,8 | 15/15 | 1/2 | 0 / 0 / 5 | 2,0 |
| C | 1,8 | 15/15 | 2/2 | 0 / 0 / 5 | 2,0 |

“Đúng phạm vi” đo theo Type mà câu hỏi yêu cầu, gồm q16 và q20. A/B không thực
thi filter nên tỷ lệ tuân thủ **filter thực sự được áp dụng** là N/A; tỷ lệ 1/2
chỉ cho thấy kết quả không lọc có vô tình nằm đúng phạm vi hay không. C áp dụng
filter cho cả hai câu, tuân thủ 2/2. Metadata đúng không đồng nghĩa retrieval đúng.

Nhãn từng trường hợp và text đọc được lưu trong `coherence.jsonl` và
`grounding.jsonl`; từng bản ghi metadata và số dòng nguồn trong `metadata.jsonl`.

## So sánh A–B

B tăng dev Hit@3 từ 4/15 lên 9/15 và test từ 2/5 lên 5/5. Trong mẫu coherence,
A thường chứa ý chính nhưng kết thúc giữa câu/từ hoặc danh sách; B giữ trọn
đoạn tốt hơn ở 8/10 vị trí. Hai vị trí B vẫn chỉ đạt 1: unit 4 có đoạn quá dài
bị cắt, unit 5 chứa câu dẫn danh sách sponsor nhưng không có danh sách phía sau.
Giới hạn cứng 500 ký tự vẫn gây mất ngữ cảnh dù chunking có nhận biết cấu trúc.

| Tài nguyên | A | B | C |
|---|---|---|---|
| Số chunk/vector | 488 | 576 | dùng chung 576 của B |
| Tổng ký tự chunk | 212.820 | 194.270 | không thêm bản sao |
| Độ dài trung bình | 436,1 | 337,3 | như B |
| Chunk vượt 128 token | 177/488 | 57/576 | như B |
| Encode CPU, giây | 31,613 | 45,090 | không encode thêm |
| Ghi DB lần đầu, giây | 0,593 | 0,647 | dùng B |
| API cost | 0 | 0 | 0 |

Thời gian encode/store lấy từ ingest run `20261114T021453497545Z`, không phải
thời gian retrieval. B có nhiều vector hơn và encode lâu hơn trong lần này dù
ít tổng ký tự hơn; batching, chiều dài token và overhead đều có thể ảnh hưởng,
chưa có thí nghiệm lặp để quy kết nguyên nhân. A có ký tự lặp do overlap.
Vector bị cắt token nhưng text lưu trong DB vẫn đầy đủ; điều này có thể làm
embedding không phản ánh phần cuối chunk. Chưa có ablation riêng để đo tác động.

## So sánh B–C

B và C bằng nhau về điểm retrieval và grounding trong tập hiện tại. Tuy vậy,
q20 có khác biệt cụ thể: top-3 B chứa PEP 572, Type Standards Track, ngoài phạm
vi Informational mà câu hỏi yêu cầu. C loại kết quả này và giữ cả ba chunk
Informational. Filter giúp tôn trọng phạm vi, chưa giúp tăng điểm trong mẫu này.

source/page/unit_id giúp truy từ chunk về PEP và đơn vị; offset và line_map đưa
về dòng RST gốc. Type lấy từ header có ba phạm vi thật. Hạn chế: Type khá rộng,
không thể thay thế độ liên quan nội dung; nếu ngữ cảnh nhập sai Type thì filter
có thể loại tài liệu cần thiết. Đủ trường và đúng giá trị chỉ chứng minh truy
vết/cấu trúc, không chứng minh câu trả lời có đủ bằng chứng.

## Ví dụ lỗi

**q17, A — truy xuất đúng chủ đề nhưng sai bằng chứng.** Câu hỏi cần quy tắc
docstring một dòng dùng mệnh lệnh và dấu chấm. Top-3 A gồm PEP 257 unit 5 về
trimming, PEP 8 unit 16 bị cắt và PEP 257 unit 1 về định nghĩa. Không có đoạn
nêu đủ quy tắc cần hỏi: grounding 0. B/C top-1 PEP 257 unit 2 giữ nguyên câu
“phrase ending in a period” và “as a command”, grounding 2.

**q18, A — phần cuối quan trọng bị cắt.** Top-3 A, PEP 572 unit 22, mới đến
“the = sta…” rồi hết chunk; thiếu +=, attributes và subscripts. Top-1 chỉ bổ
sung một phần về expression và multiple targets, nên grounding 1. B/C giữ
trọn so sánh trong top-3, grounding 2. Xem chunk ID/text trong grounding.jsonl.

**q16, A — grounding đủ nhưng Hit@3 vẫn 0.** Rank 1 nêu điều kiện nhóm đồng
thuận và 99 ký tự; rank 3 nêu 72 ký tự cho comments/docstrings. Hợp thông tin
top-3 đủ trả lời nên grounding 2. Không có một chunk chứa toàn bộ gold quote,
vì vậy giữ nguyên Hit@3=0; không sửa metric chính để hợp với nhãn grounding.

**q13, B — giới hạn metric và chunk.** Gold quote PEP 498 unit 5 dài 564 ký tự,
vượt max_size=500. Rank 3 có giải thích double braces nhưng bị cắt trước phần
kết luận; dù truy về đúng đoạn, không thể chứa toàn bộ quote trong một chunk.
Đây là false negative tiềm năng của metric whole-quote nếu một phần ngắn hơn
đã đủ trả lời. Cần review evidence tương đương đồng nhất cả A/B/C ở một phiên
bản đánh giá có ghi nhận; không thay gold hoặc báo lại điểm test trong lần này.

## Kết luận và giới hạn

Tôi giữ C là lựa chọn của lần chạy: selection được ghi trước test theo dev
Hit@3, Hit@1, rồi tổng thời gian search. B/C đều 9/15 và 4/15; C mất 0,415749 s,
B 0,466809 s trên dev. Đây là khác biệt nhỏ có nhiễu. Trên test B lại nhanh hơn
C (0,140739 so với 0,147827 s), minh họa vì sao không nên coi C nhanh hơn tổng
quát. Không thay lựa chọn dựa trên test.

Kết luận trong phạm vi corpus: ưu tiên giữ đoạn/heading; dùng filter khi câu hỏi
thật sự cung cấp phạm vi. Không khẳng định thắng trên corpus khác hoặc chất
lượng câu trả lời sinh. Test chỉ có 5 câu, có tài liệu/đơn vị chung dev; nhãn
có tính chủ quan, coherence lệch PEP 1 và việc đọc không blind. Mọi tỷ lệ 5/5
hoặc 15/15 đều có mẫu số nhỏ và tiêu chí cụ thể, không phải bảo đảm tuyệt đối.

Nếu làm tiếp, tôi sẽ review lại nhãn, mở rộng mẫu coherence ra các PEP khác,
thiết kế test mới lớn hơn, và thử chunk/token budget trên dev của phiên bản mới.
Không dùng những quan sát từ test hiện tại để tinh chỉnh rồi giữ tuyên bố nó
là một holdout độc lập chưa từng được xem.

## Kiểm tra và tái lập

Từ `starter/`, venv đã activate:

```powershell
python -m src.validate_audit
```

Lệnh kiểm tra hash, ranh giới, số mẫu và tổng hợp nhãn đã lưu.
Không cần Docker và không chạy
lại benchmark, sửa corpus, model, gold hoặc selection đã chốt.


## Chỉ mục minh chứng

- [Manifest](../../data/manifest.json): nguồn, quyền và ranh giới đơn vị.
- [Thống kê chunk](../../data/chunks/summary.json): cấu hình và phân bố kích thước.
- [Nhật ký thí nghiệm](../../artifacts/experiment_log.csv): giả thuyết và metric.
- [Ingest đã dùng](../../results/ingestion_runs/20261114T021453497545Z.json): model, runtime, thời gian và kiểm tra DB.
- [Protocol audit](../../results/audit/20261114T022140610429Z/protocol.json): cách lấy mẫu, input hashes.
- [Nhãn coherence](../../results/audit/20261114T022140610429Z/coherence.jsonl).
- [Nhãn grounding](../../results/audit/20261114T022140610429Z/grounding.jsonl).
- [Đối chiếu metadata](../../results/audit/20261114T022140610429Z/metadata.jsonl).
- [Tổng hợp audit](../../results/audit/20261114T022140610429Z/summary.json).
- [README](../../README.md): lệnh setup, chạy, khởi động lại và giới hạn tái tạo artifact.

Tôi kiểm tra normalization/chunking/metric bằng unittest, kiểm tra hash benchmark
và audit bằng các validator riêng. Chạy lại benchmark tạo run mới để không ghi đè
minh chứng gốc. Không cần chạy lại benchmark chỉ để xem báo cáo.
