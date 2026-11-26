Bạn xác định nhu cầu nghiệp vụ và vận hành nào đủ mạnh để cân nhắc microservices thay vì monolith?
Những dấu hiệu nào cho thấy việc tách một ứng dụng thành nhiều dịch vụ sẽ làm tăng độ phức tạp mà ít mang lại lợi ích?
Bạn tìm ranh giới nghiệp vụ phù hợp cho từng service từ quy trình, thuật ngữ và quyền sở hữu như thế nào?
Khi hai chức năng thường xuyên cần thay đổi cùng nhau, bạn đánh giá có nên đặt chúng trong một service ra sao?
Bạn phân biệt ranh giới bounded context với ranh giới triển khai microservice bằng cách nào?
Một microservice nên sở hữu những dữ liệu và quy tắc nghiệp vụ nào để có thể thay đổi độc lập?
Khi hai service cùng muốn ghi một bảng, bạn thiết kế quyền sở hữu dữ liệu để tránh ghép nối như thế nào?
Bạn lựa chọn cách chia sẻ dữ liệu qua API hoặc event thay vì đọc trực tiếp database của service khác ra sao?
Trong một giao dịch nghiệp vụ trải qua nhiều service, bạn xác định bất biến nào có thể bảo đảm cục bộ?
Bạn sẽ quyết định kích thước service dựa trên độ kết dính, tần suất thay đổi và khả năng quản lý của nhóm như thế nào?
Bạn thiết kế hợp đồng API để giảm phụ thuộc vào cấu trúc dữ liệu nội bộ của service ra sao?
Khi nhiều client cần tổng hợp dữ liệu từ nhiều service, bạn cân nhắc API gateway và lớp tổng hợp như thế nào?
Bạn lựa chọn giao tiếp đồng bộ hay bất đồng bộ dựa trên yêu cầu phản hồi và độ tin cậy như thế nào?
Chuỗi lời gọi đồng bộ qua nhiều service làm tăng độ trễ và nguy cơ lỗi dây chuyền ra sao?
Bạn thiết kế timeout, retry có giới hạn và circuit breaker để tránh làm quá tải dependency như thế nào?
Khi một service không sẵn sàng, bạn xác định chức năng nào có thể giảm cấp và chức năng nào phải từ chối xử lý?
Bạn phân biệt sự kiện nghiệp vụ đã xảy ra với command yêu cầu service khác thực hiện hành động như thế nào?
Bạn thiết kế event contract để consumer không phụ thuộc vào mô hình lưu trữ của producer ra sao?
Nếu service ghi database thành công nhưng publish event thất bại, bạn dùng transactional outbox để bảo đảm điều gì?
Bạn sẽ thiết kế consumer có tính idempotent để sự kiện được gửi lại không tạo tác dụng phụ trùng lặp như thế nào?
Khi các event đến chậm hoặc sai thứ tự, bạn bảo vệ trạng thái của service nhận dựa trên thông tin nào?
Bạn lựa chọn retry, backoff và dead-letter queue cho một consumer theo loại lỗi như thế nào?
Bạn mô hình hóa Saga cho quy trình đặt hàng gồm giữ tồn kho, thanh toán và xác nhận đơn như thế nào?
Khi một bước Saga thất bại sau các bước đã thành công, bạn thiết kế hành động bù trừ ra sao?
Bạn so sánh Saga choreography với orchestration theo khả năng quan sát và độ ghép nối như thế nào?
Bạn diễn đạt trạng thái nghiệp vụ đang xử lý khi nhiều service chỉ đạt eventual consistency ra sao?
Nếu người dùng đọc dữ liệu ngay sau ghi nhưng read model chưa cập nhật, bạn xử lý kỳ vọng nhất quán như thế nào?
Khi một service thay đổi định dạng event, bạn kiểm soát tương thích với consumer được triển khai độc lập ra sao?
Bạn thiết kế chiến lược versioning API để nhiều phiên bản client và service cùng hoạt động như thế nào?
Bạn sử dụng consumer-driven contract test để phát hiện thay đổi phá vỡ dịch vụ phụ thuộc ra sao?
Bạn xác định phạm vi kiểm thử đơn vị, tích hợp, hợp đồng và end-to-end trong hệ thống nhiều service như thế nào?
Khi kiểm thử end-to-end thất bại do nhiều phụ thuộc, bạn khoanh vùng nguyên nhân mà không phụ thuộc hoàn toàn vào log ra sao?
Bạn sẽ tạo môi trường thử nghiệm để mô phỏng timeout, mất kết nối và broker bị gián đoạn như thế nào?
Khi lưu lượng tăng ở một nghiệp vụ, bạn đo và mở rộng riêng service gây nghẽn theo chỉ số nào?
Bạn quyết định giới hạn số request đồng thời, hàng đợi và backpressure cho một service bằng cách nào?
Bạn dùng correlation ID, distributed tracing và metrics để theo dõi một hành trình qua nhiều service ra sao?
Bạn phân biệt lỗi phát sinh ở service gốc với lỗi lan truyền qua các lời gọi phụ thuộc như thế nào?
Khi có sự cố dữ liệu giữa hai service, bạn thiết kế đối soát và khả năng phát lại sự kiện ra sao?
Bạn đặt ranh giới xác thực và phân quyền thế nào giữa gateway và từng service để tránh tin cậy quá mức?
Bạn bảo vệ secret, kết nối giữa service và dữ liệu nhạy cảm trong các event bằng những biện pháp nào?
Bạn thiết kế quy trình triển khai độc lập để một service mới không yêu cầu phát hành đồng thời các service khác ra sao?
Khi nâng cấp schema lưu trữ, bạn áp dụng thay đổi theo giai đoạn để phiên bản service cũ và mới cùng chạy như thế nào?
Bạn lựa chọn rolling deployment, canary và rollback theo rủi ro nghiệp vụ như thế nào?
Khi service được nhân bản trên nhiều instance, bạn xử lý trạng thái phiên và công việc chạy định kỳ để tránh trùng như thế nào?
Bạn xác định ai chịu trách nhiệm vận hành, giám sát và xử lý sự cố của mỗi service bằng cách nào?
Bạn đánh giá chi phí hạ tầng, CI/CD, quan sát và hỗ trợ vận hành khi số lượng microservice tăng ra sao?
Nếu một service phải sửa cùng lúc với nhiều service khác cho hầu hết yêu cầu, bạn sẽ đánh giá lại ranh giới như thế nào?
Bạn tổ chức quá trình tách một chức năng khỏi monolith để chuyển dữ liệu và lưu lượng từng bước ra sao?
Bạn kiểm chứng hành vi nghiệp vụ và tính nhất quán dữ liệu sau mỗi giai đoạn tách dịch vụ như thế nào?
Bạn lựa chọn bằng chứng gì để kết luận microservices đã cải thiện khả năng triển khai và thay đổi so với monolith?
