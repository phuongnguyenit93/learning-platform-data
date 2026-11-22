# Data Persistence File Persistence

Lưu trữ dữ liệu bằng tệp (file persistence) cho phép ứng dụng giữ thông tin qua nhiều lần chạy mà không cần hệ quản trị cơ sở dữ liệu. Cách tiếp cận này phù hợp cho cấu hình, trạng thái nhỏ, nhật ký hoặc dữ liệu trao đổi, nhưng đặt ra những yêu cầu về định dạng, đường dẫn, tính nhất quán và xử lý lỗi I/O.

Module dành cho người đã biết lập trình Java và cấu trúc dữ liệu cơ bản. Bạn sẽ bắt đầu từ vai trò của tệp và hệ tệp, tiếp tục với thao tác đường dẫn, đọc/ghi văn bản và byte, cách tổ chức bản ghi, streaming cho tệp lớn, rồi đến ghi an toàn, truy cập đồng thời và phân quyền. Các API Java như `Path`, `Files` và `FileChannel` được dùng làm ví dụ cụ thể cho những nguyên tắc này.

Sau tám mốc, bạn có thể chọn cách lưu tệp thích hợp, quản lý tài nguyên I/O, hạn chế mất dữ liệu khi ghi lỗi, kiểm soát truy cập và xây dựng kiểm thử cho các tình huống bất thường. Trọng tâm là tạo nền tảng vững chắc để thiết kế giải pháp lưu trữ tệp đáng tin cậy trước khi mở rộng sang các cơ chế lưu trữ phức tạp hơn.