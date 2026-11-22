# Code Quality Static Analysis Architecture Rules

Quy tắc kiến trúc giúp bảo đảm cấu trúc mã nguồn tiếp tục tuân theo thiết kế khi hệ thống phát triển. Module này giới thiệu cách mô tả ranh giới giữa các tầng, gói và module thành những điều kiện có thể kiểm tra tự động, qua đó phát hiện phụ thuộc sai chiều, truy cập vào phần nội bộ hoặc chu trình phụ thuộc trước khi lỗi thiết kế lan rộng.

Lộ trình đi từ việc xác định ranh giới và hướng phụ thuộc đến kiểm soát API module, thư viện và chu trình. Tiếp theo, người học chuyển các nguyên tắc thành bài kiểm thử kiến trúc, quản lý ngoại lệ có lý do và tích hợp kiểm tra vào quy trình build/CI. Các ví dụ ưu tiên hệ sinh thái Java và ArchUnit, đồng thời nhấn mạnh những nguyên tắc có thể áp dụng rộng hơn.

Nội dung phù hợp với lập trình viên đã biết cấu trúc gói, module và dependency, cũng như người muốn duy trì chất lượng kiến trúc trong dự án nhiều thành phần. Sau khi hoàn thành, bạn có thể viết và kiểm chứng một bộ luật kiến trúc nhỏ, phân tích vi phạm và quyết định cách khắc phục hoặc quản lý ngoại lệ mà vẫn ngăn được hồi quy.