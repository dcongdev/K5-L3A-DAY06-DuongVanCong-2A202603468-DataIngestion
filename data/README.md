# Chuẩn bị corpus RST

Chạy từ `starter/` (chỉ dùng Python standard library, không cần Docker/API):

```powershell
.\.venv\Scripts\python.exe -m src.prepare_corpus
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Nếu đã kích hoạt môi trường Python, thay `.\.venv\Scripts\python.exe` bằng `python`.
Input luôn là `data/raw/*.rst` ở gốc repo, không phải `starter/data/`.

Output:

- `manifest.json`: metadata header nguyên giá trị (gộp continuation), giấy phép trích từ file,
  SHA-256, snapshot, phần bị loại và ranh giới đơn vị. URL nguồn được dựng theo
  repository python/peps và snapshot người dùng cung cấp, chưa đối chiếu qua mạng.
- `processed/pep-*.json`: văn bản RST chuẩn hóa cùng bản đồ từng dòng về file gốc.
- `processed/units.jsonl`: đơn vị nguồn tuần tự, text và metadata. `page` là số đơn vị
  trong tài liệu, không phải trang PDF; `unit_id` ổn định với cùng input/quy tắc.

NFC, LF, bỏ khoảng trắng cuối dòng, gộp dòng trống và khoảng trắng trên dòng không
thụt lề. Giữ heading, đoạn, markup RST và khoảng trắng bên trong dòng thụt lề
để bảo toàn code/table/list. Đây không phải trình render RST thành plain text.
Loại header và các section References/Footnotes/Bibliography/Copyright/License
đến heading cùng cấp hoặc cao hơn; nội dung sau section đó vẫn được giữ.

Mỗi đơn vị kết thúc ở ranh giới đoạn đầu tiên đạt 1.500 ký tự; không cắt đoạn dài.
Phần dư ngắn gộp vào đơn vị trước. Tài liệu dưới ngưỡng báo lỗi, không nhân bản.
Số ký tự tính trên RST đã chuẩn hóa, gồm markup và whitespace được giữ lại.
Các đơn vị nối lại khôi phục chính xác nội dung đã giữ; đây chưa phải chunk A/B/C.

Offset là ký tự Unicode 0-based, end-exclusive, không phải byte. `start/end` trỏ vào
text trong JSON chuẩn hóa. `raw_start/raw_end` trong line_map trỏ vào file gốc
decode UTF-8 trước chuyển newline. Bản đồ ở độ chính xác từng dòng; số dòng 1-based.
Đơn vị đi qua phần bị loại có thể bao phủ khoảng dòng không liên tục: dùng line_map,
không lấy toàn bộ khoảng raw_line_start/raw_line_end làm text đơn vị.

Không biết ngày tải gốc nên `accessed_at` là null; `processed_at` ghi thời điểm đọc
local thực tế. Snapshot là khai báo của người dùng, SHA-256 nhận diện file local;
không tuyên bố đã xác minh file khớp commit từ xa. Chạy lại ghi đè các output cùng
tên; raw không đổi. Lỗi đọc/UTF-8/header/quyền/độ dài dừng lệnh với exit code 1;
phân tích toàn bộ input thành công mới bắt đầu ghi output.
