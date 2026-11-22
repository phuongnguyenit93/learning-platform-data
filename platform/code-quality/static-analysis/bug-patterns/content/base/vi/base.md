# Code Quality Static Analysis Bug Patterns

**Static Analysis Bug Patterns** là các mẫu dấu hiệu trong mã nguồn thường liên quan đến lỗi logic, sử dụng API sai, rò rỉ tài nguyên, vấn đề đồng thời hoặc điểm yếu bảo mật. Công cụ phân tích tĩnh như SpotBugs, Error Prone và PMD giúp phát hiện sớm những dấu hiệu này mà không cần chạy chương trình; tuy nhiên, một cảnh báo vẫn cần được đối chiếu với ngữ cảnh thực tế trước khi kết luận đó là lỗi.

Lộ trình gồm **8 mốc**: nhận diện và phân loại bug pattern; lỗi null và kiểu dữ liệu; so sánh và collection; luồng điều khiển và API; exception và tài nguyên; đồng thời và trạng thái; bảo mật và dữ liệu đầu vào; cuối cùng là phân loại cảnh báo, sửa lỗi và kiểm chứng. Mỗi mốc nhấn mạnh cách nhận ra biểu hiện, tìm nguyên nhân và lựa chọn cách khắc phục có cơ sở.

Học phần dành cho người đã nắm lập trình Java cơ bản, muốn đọc báo cáo phân tích tĩnh và cải thiện chất lượng mã một cách có hệ thống. Sau khi học, bạn có thể giải thích các nhóm cảnh báo phổ biến, ưu tiên vấn đề đáng xử lý, nhận ra false positive và xác minh bản sửa bằng kiểm thử hồi quy cùng lần quét tiếp theo.