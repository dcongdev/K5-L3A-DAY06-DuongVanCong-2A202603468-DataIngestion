# Ghi nhận setup embedding/vector store

- Venv hiện có dùng CPython 3.15.2 trên Windows; không tạo lại venv.
- Kiểm tra thực tế: PostgreSQL 16.16, pgvector 0.8.7; container đã chạy sẵn.
- Lần cài Sentence Transformers đầu tiên dừng ở PyYAML 6.0.3: build C extension
  yêu cầu Microsoft Visual C++ 14.0 trở lên, máy chưa có compiler tương ứng.
- Đã build và cài thành công PyYAML 6.0.3 dạng Python thuần bằng
  `PYYAML_FORCE_LIBYAML=0`, rồi tiếp tục cài requirements. Đây chỉ là thay đổi
  backend đọc YAML config, không phải fallback embedding.
- Tên/revision model và cấu hình đã ghi vào experiment_log trước khi chạy
  benchmark. Metric dev/test vẫn trống; technical smoke check không phải benchmark.
- Kết quả chạy thực tế (hoặc lỗi/stage) được lưu trong `results/ingestion.json`
  và lịch sử `results/ingestion_runs/`; không suy diễn thành công từ việc cài thư viện.
- Ingest thực tế thành công: A 488 vector, B 576 vector, C dùng chung B; 384 chiều.
  Cả 9 database contract checks và 6 smoke query/filter checks đều qua; lần nạp
  thứ hai giữ nguyên count. Không chạy benchmark dev/test.
- Model max sequence length 128: A có 177 chunk, B có 57 chunk bị right truncation
  lúc encode. Text và offset lưu trong database vẫn đầy đủ.
