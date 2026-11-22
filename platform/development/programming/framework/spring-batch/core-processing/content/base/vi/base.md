# Spring Batch Core Processing

Spring Batch là framework xử lý dữ liệu theo lô dành cho các tác vụ cần đọc, biến đổi và ghi nhiều bản ghi theo một quy trình có kiểm soát. Trọng tâm của module này là cách xây dựng một Job gồm các Step, theo dõi trạng thái chạy và bảo đảm dữ liệu được xử lý nhất quán trong từng giao dịch.

Lộ trình phù hợp với lập trình viên Java đã biết Spring cơ bản và muốn triển khai các tác vụ nhập, xuất hoặc biến đổi dữ liệu định kỳ. Bạn sẽ bắt đầu với Job, Step và JobParameters, thực hành Tasklet và chunk-oriented processing, rồi kết nối ItemReader, ItemProcessor, ItemWriter. Cuối cùng, module hướng dẫn cấu hình retry/skip, hiểu rollback và khôi phục Job bằng metadata trong JobRepository và ExecutionContext.

Hãy luyện tập bằng một Job đọc dữ liệu đơn hàng từ tệp, chuẩn hóa và kiểm tra từng bản ghi rồi ghi kết quả ra cơ sở dữ liệu. Khi đã chạy thành công, tạo vài bản ghi lỗi và mô phỏng gián đoạn để quan sát cách skip, retry và restart hoạt động. Sau module, bạn có thể xây dựng và kiểm tra một quy trình batch cơ bản, dễ hiểu và có khả năng khôi phục.