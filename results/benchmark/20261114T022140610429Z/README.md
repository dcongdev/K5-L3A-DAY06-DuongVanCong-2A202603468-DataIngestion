# Benchmark retrieval — kết quả thực tế

| Split | Strategy | Hit@1 | Evidence Hit@3 | Search seconds |
|---|---|---|---|---|
| dev | A | 3/15 | 4/15 | 0.437320 |
| dev | B | 4/15 | 9/15 | 0.466809 |
| dev | C | 4/15 | 9/15 | 0.415749 |
| test | A | 1/5 | 2/5 | 0.154837 |
| test | B | 4/5 | 5/5 | 0.140739 |
| test | C | 4/5 | 5/5 | 0.147827 |

Chọn **C** trên dev, lưu selection trước khi chạy test.
B và C bằng nhau về Hit@1/Hit@3 dev; C thắng theo tổng thời gian search trong lần chạy này.
Khác biệt timing nhỏ và có nhiễu; không kết luận C vượt B nói chung. Test không được dùng để chọn.

Metric tự động bảo thủ yêu cầu nguyên đoạn evidence đã ghi trong một chunk đúng nguồn/đơn vị.
Không gộp evidence nhiều chunk. Evidence tương đương chưa ghi cần review riêng và chấm đồng nhất.
Chưa có nhãn coherence, metadata hoặc grounding thủ công; không gọi kết quả này là chất lượng câu trả lời LLM.

Các query được encode cùng model local đã ingest. A/B không lọc; C dùng filter từ câu hỏi.
Trace đầy đủ và nhãn tự động ở dev_traces.jsonl/test_traces.jsonl; xem run_config.json, selection.json và metrics.csv.
Gold do AI hỗ trợ soạn; review độc lập của học viên vẫn còn thiếu. Bộ test 5 câu nhỏ và có tài liệu/đơn vị chung với dev.

Lần chạy này không sửa corpus, model, chunk hoặc gold sau khi xem test.
Không chỉnh chiến lược bằng test rồi báo lần chạy sau như một holdout độc lập mới.
