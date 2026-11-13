# Benchmark v1 — chốt trước retrieval

20 câu tiếng Việt trên corpus PEP tiếng Anh: `dev.jsonl` gồm q01–q15;
`test.jsonl` gồm q16–q20. Có 5 câu filter, gồm q04/q08/q14 ở dev và q16/q20
ở test. Bộ này kiểm tra thêm khả năng truy xuất xuyên ngôn ngữ; cần nêu giới hạn
đó trong báo cáo khi chọn embedding model.

## Gold và filter

Mỗi câu có đáp án, `gold_source_id`, `gold_page`, nguyên văn evidence và
`gold_evidence` liệt kê vị trí được chấp nhận. `gold_page` là số đơn vị nguồn
1-based của từng tài liệu, không phải trang PDF. Offset start/end 0-based,
end-exclusive trong text của `data/processed/pep-*.json`.

Các câu và đáp án được AI hỗ trợ soạn, đọc đối chiếu với evidence local.
Kiểm tra tự động xác minh vị trí và điều kiện filter; không chứng minh tự động
đáp án đầy đủ về ngữ nghĩa và không phải nhãn audit thủ công của học viên.
Học viên cần đọc lại trước thí nghiệm và ghi việc dùng AI trong báo cáo.
Không có kết quả retrieval nào được tạo ở bước này.

Filter `Type` giữ đúng tên trường và giá trị header: Process, Informational,
Standards Track. Giá trị được nêu trực tiếp trong câu hỏi và có trước retrieval;
không dùng PEP ID, gold source, số đơn vị hay đáp án làm filter.
Giữ nguyên câu hỏi giữa A/B/C. A/B bỏ qua filter, C áp dụng filter được cung cấp;
với filter rỗng, C không lọc. Chỉ truyền question/filter vào retrieval, không
truyền expected_answer hoặc các trường gold. Lưu gold riêng trong evaluator.

## Chia tập và hạn chế

Chia cố định theo câu hỏi/chủ đề, không random. Dev bao phủ 5 tài liệu; test gồm
ngoại lệ line length, cách viết docstring, so sánh hai dạng gán, thứ tự case và
guard. PEP 636 chỉ xuất hiện trong gold test để thêm một chủ đề chưa có ở dev.
Các câu test còn lại dùng tài liệu chung với dev, thậm chí có đơn vị nguồn chung;
đây không phải document-disjoint split. Không suy diễn chất lượng tổng quát từ
5 câu test. Toàn bộ corpus, gồm PEP 636, vẫn phải được ingest ở mọi cấu hình.

Tập test đã được đọc khi biên soạn; chưa dùng điểm retrieval test để chọn cấu hình.
Sau khi bắt đầu thí nghiệm chỉ tối ưu trên dev. Chốt cấu hình trước khi chạy test;
nếu dùng test để sửa cấu hình, ghi rõ và không báo nó là holdout độc lập.

Gold hiện liệt kê các vị trí chứa nguyên văn đoạn đã chọn trong corpus và đáp ứng
filter (nếu có). Bằng chứng tương đương ở vị trí khác vẫn có thể hợp lệ: người chấm
phải xác nhận, ghi bổ sung và chấm lại đồng nhất cả ba cấu hình; không tự coi mọi
vị trí chưa liệt kê là sai. Không thay gold có chọn lọc để ưu ái một chiến lược.

## Tiêu chí lựa chọn chốt trước khi chạy

Giữ cùng corpus, model, vector store, cosine và top-k=3 giữa A/B/C. A fixed-size;
B theo đoạn/heading; C giống B chỉ thêm filter. Tham số và model cụ thể phải được
ghi vào experiment log trước lần chạy dev đầu tiên; bước này chưa chọn hay chạy chúng.

Chọn cấu hình có Evidence Hit@3 trên dev cao nhất; nếu bằng nhau chọn Hit@1 dev
cao hơn; tiếp tục bằng nhau chọn tổng thời gian retrieval dev thấp hơn (cùng máy,
cùng cách đo và ghi trạng thái cache). Nếu vẫn bằng nhau chọn A rồi B rồi C.
Không dùng grounding test hoặc bất cứ metric test nào để phá hòa.

Hit yêu cầu một chunk đúng nguồn/đơn vị và đủ evidence hoặc bằng chứng tương đương
được xác nhận. Báo tử/mẫu riêng dev/test. Không thay metric chính bằng hợp evidence
từ nhiều chunk. Coherence, metadata và grounding vẫn phải có audit theo GUIDE ở
bước sau, không suy ra nhãn thủ công từ kiểm tra chuỗi.

## Kiểm tra và khóa phiên bản

Từ `starter/`, với venv đã activate:

```powershell
python -m src.validate_benchmark
```

`freeze.json` ghi thời điểm chốt và SHA-256 của dev, test, units corpus và tài liệu
quy trình này. Lệnh chỉ đọc và kiểm tra, không tạo kết quả đánh giá. Thay đổi
corpus/câu hỏi/quy trình phải được review, ghi lý do và tạo phiên bản chốt mới một
cách chủ đích; không tự cập nhật hash để che thay đổi sau khi đọc điểm test.
