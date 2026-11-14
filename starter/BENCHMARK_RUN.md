# Chạy benchmark retrieval

Điều kiện: Docker/pgvector chạy, venv đã activate, corpus/chunks đã tạo và vector
đã ingest. Không cần ingest lại sau khi khởi động máy. Model dùng cache local;
không tải model khác, không đổi tham số hoặc dữ liệu để chạy benchmark.

Từ `starter/`:

```powershell
python -m src.benchmark_runner --split all
```

Lệnh chạy dev trước, lưu `selection.json`, rồi mới đọc/chạy test. Mỗi lần tạo một
thư mục mới trong `results/benchmark/<run_id>/`; không ghi đè lần cũ.
Nếu muốn dừng sau dev:

```powershell
python -m src.benchmark_runner --split dev
```

`python -m src.run` cũng chạy dev mặc định. Chạy test của một lần dev đã chốt:

```powershell
python -m src.benchmark_runner --split test --run-dir ../results/benchmark/<run_id>
```

Thay `<run_id>` bằng thư mục được in sau lần dev. Test yêu cầu selection có sẵn,
model/database/code/input/dev summary giống khi chốt. Không cho ghi đè test đã bắt
đầu, kể cả trace một phần. Muốn chạy lại phải giữ trace cũ và ghi lý do rõ ràng.
Không dùng test để điều chỉnh chiến lược rồi coi lần chạy sau là holdout mới.

## Kết quả và cách chấm

- `dev_traces.jsonl`, `test_traces.jsonl`: mọi câu × A/B/C; nguyên câu hỏi, gold,
  chunk ID/text/score/metadata top-3, filter input/áp dụng, thời gian và nhãn hit.
- `dev_summary.json`, `test_summary.json`, `metrics.csv`: tử số/mẫu số và tỷ lệ
  Hit@1, Evidence Hit@3 riêng mỗi strategy/split, tổng thời gian search.
- `selection.json`: cấu hình được chọn và thời điểm chốt **trước khi chạy test**,
  hash cấu hình/model/database/dev summary. Chọn dev Hit@3 cao nhất, sau đó Hit@1,
  tổng thời gian search thấp hơn, cuối cùng thứ tự A/B/C, đúng quy tắc đã ghi.
- `run_config.json`: model/revision/runtime signature, input/code hashes và quy
  ước đo. Không lưu DATABASE_URL, key hoặc vector query vào trace.

Hit tự động yêu cầu đúng document_id và số đơn vị gold, đồng thời toàn bộ đoạn
evidence đã ghi nằm trong **một** chunk sau chuẩn hóa whitespace. Không cộng nhiều
chunk thiếu thành một hit, không tính rank 4, không suy hit chỉ từ đúng trang.
Chấp nhận các gold alternatives đã ghi. Phương pháp này bảo thủ: evidence dài
hơn chunk hoặc diễn đạt tương đương chưa ghi có thể thành false negative; cần
review và ghi nhận ở bước audit. Không sửa gold theo từng strategy để nâng điểm.
Đây không phải coherence/grounding thủ công hay độ chính xác câu trả lời LLM.

Chỉ question và filter input đi vào retrieval. A/B bỏ filter, C áp dụng khi có.
Gold và expected_answer chỉ đến evaluator sau khi search. Mỗi câu encode một lần,
chia sẻ vector cho A/B/C; thứ tự search xoay vòng theo câu để giảm thiên lệch thứ
tự. Thời gian search gồm kết nối DB và nhận kết quả, không gồm query embedding.
Warm-up dùng câu chung ngoài benchmark, không tính điểm/thời gian chọn cấu hình;
không reset OS/database cache. Timing của một lần chạy nhỏ có nhiễu, không suy
luận hiệu năng tổng quát từ khác biệt nhỏ. Receipt ghi token stats từng query.

Runner kiểm tra hash benchmark đã chốt, model signature và toàn bộ chunk trong
database so với artifact A/B. Fingerprint gồm cả vector được kiểm tra sau mỗi
split; database đổi trong lúc chạy khiến lệnh thất bại, không báo kết quả hợp lệ.
Các output một phần vẫn được giữ để xác minh lỗi. Không cập nhật model/chunks khi chạy.

## Kiểm tra code và công việc còn lại

```powershell
python -m unittest discover -s tests -v
```

Gold hiện do AI hỗ trợ soạn và chưa có xác nhận review độc lập của học viên.
Kết quả tự động không hoàn thành audit bắt buộc. Bước tiếp theo cần chấm coherence
trên cùng 10 vị trí nguồn mỗi strategy, kiểm tra metadata trên 5 câu test × top-3,
chấm grounding trên 5 câu test mỗi strategy, rồi phân tích lỗi/đánh đổi và báo cáo.
