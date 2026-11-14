# Audit và phân tích chiến lược dữ liệu

Run retrieval: `20261114T022140610429Z`. Dữ liệu audit:
`results/audit/20261114T022140610429Z/`. Mỗi nhãn đi kèm lý do, đoạn nội dung
được xem xét và thông tin truy vết về nguồn.

## 1. Phương pháp và phạm vi

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

## 2. Kết quả năm khía cạnh

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

## 3. A–B: tác động của chunking

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

## 4. B–C: tác động của metadata

B và C bằng nhau về điểm retrieval và grounding trong tập hiện tại. Tuy vậy,
q20 có khác biệt cụ thể: top-3 B chứa PEP 572, Type Standards Track, ngoài phạm
vi Informational mà câu hỏi yêu cầu. C loại kết quả này và giữ cả ba chunk
Informational. Filter giúp tôn trọng phạm vi, chưa giúp tăng điểm trong mẫu này.

source/page/unit_id giúp truy từ chunk về PEP và đơn vị; offset và line_map đưa
về dòng RST gốc. Type lấy từ header có ba phạm vi thật. Hạn chế: Type khá rộng,
không thể thay thế độ liên quan nội dung; nếu ngữ cảnh nhập sai Type thì filter
có thể loại tài liệu cần thiết. Đủ trường và đúng giá trị chỉ chứng minh truy
vết/cấu trúc, không chứng minh câu trả lời có đủ bằng chứng.

## 5. Ví dụ lỗi và khác biệt giữa metric

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

## 6. Lựa chọn và giới hạn

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

## 7. Kiểm tra artifact

Từ `starter/`, venv đã activate:

```powershell
python -m src.validate_audit
```

Lệnh kiểm tra hash, ranh giới, số mẫu và tổng hợp nhãn đã lưu.
Không cần Docker và không chạy
lại benchmark, sửa corpus, model, gold hoặc selection đã chốt.
