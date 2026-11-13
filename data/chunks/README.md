# Chunk A/B — trước embedding

Chạy từ `starter/` với venv đã activate:

```powershell
python -m src.prepare_chunks
python -m unittest discover -s tests -v
```

Input là 117 đơn vị nguồn đã chốt. Lệnh kiểm tra hash benchmark/corpus trước khi
chia; không dùng câu hỏi, đáp án hoặc evidence để chọn ranh giới chunk.

- A: cửa sổ cố định 500 ký tự Unicode, overlap 50, không vượt đơn vị nguồn.
- B: gom đoạn tối đa 500 ký tự, không overlap; bắt đầu nhóm mới khi gặp heading
  RST dạng title + underline. Ghép heading với đoạn kế tiếp trước khi chia theo
  giới hạn. Đoạn quá dài chia tại whitespace gần cuối cửa sổ, hoặc cắt ký tự nếu
  không có whitespace phù hợp. Không thêm text, không bỏ delimiter.
- C: dùng chính `B.jsonl`, chưa tạo bản sao hoặc chunk riêng; sau này chỉ khác
  filter metadata từ câu hỏi ở thời điểm truy xuất.

`A.jsonl`, `B.jsonl` giữ source, document_id, page (số đơn vị nguồn), header thật
và unit_id. `metadata.start/end` là offset ký tự trong văn bản chuẩn hóa tài liệu;
`unit_offset_start/end` là offset trong đơn vị. Tất cả 0-based, end-exclusive.
Tra bản đồ dòng trong `data/processed/pep-*.json` để quay về file RST gốc.
ID SHA-256 phụ thuộc tài liệu, số đơn vị, cấu hình, ranh giới và text; chạy lại
cùng input cho cùng ID, ghi đè output cùng tên.

`summary.json` ghi cấu hình, SHA-256, số chunk, phân bố chiều dài, tổng ký tự và
thời gian riêng bước chunking (không gồm embedding, database, retrieval hay I/O).
Tổng ký tự A gồm phần overlap; không dùng nó để tính lại số trang corpus.

Giới hạn: không nối qua đơn vị nguồn; heading đầu đơn vị có thể không phải heading
cha của các đoạn sau. Giới hạn 500 ký tự vẫn có thể tách code/table hoặc đoạn dài,
và heading dài có thể tách khỏi ngữ cảnh. Chưa chứng minh B mạch lạc hơn A;
cần chấm coherence thủ công và chạy retrieval ở bước sau.
