Bạn giải thích vì sao một lời gọi qua mạng không thể được xem như lời gọi hàm nội bộ dù cùng có đầu vào và đầu ra như thế nào?
Bạn phân biệt lỗi toàn bộ hệ thống với lỗi từng phần khi một số nút vẫn hoạt động còn nút khác mất kết nối ra sao?
Khi client không nhận được phản hồi, bạn phân tích những khả năng nào về việc server đã thực thi yêu cầu?
Bạn xác định timeout phù hợp cho một lời gọi phân tán dựa trên độ trễ mạng, tải và yêu cầu nghiệp vụ như thế nào?
Bạn phân biệt độ trễ truyền mạng với thời gian xử lý tại một nút khi phân tích một request chậm ra sao?
Bạn giải thích vì sao đồng hồ trên các máy có thể lệch nhau và tác động của điều đó đến việc sắp thứ tự sự kiện như thế nào?
Bạn dùng quan hệ nhân quả giữa các sự kiện để lý giải thứ tự thực thi trong hệ thống không có đồng hồ chung ra sao?
Bạn nhận diện những giả định về mạng luôn ổn định, không mất gói hoặc không lặp thông điệp có thể làm thiết kế sai như thế nào?
Bạn phân biệt failure detection bằng heartbeat với bằng chứng chắc chắn một nút đã chết như thế nào?
Bạn thiết kế retry có giới hạn và backoff để giảm lỗi tạm thời mà không gây bão yêu cầu khi nhiều client cùng thất bại ra sao?
Bạn dùng idempotency key để bảo đảm thao tác tạo đơn hàng không bị lặp khi client gửi lại yêu cầu như thế nào?
Bạn phân biệt idempotency của một API với bảo đảm thông điệp được giao đúng một lần trong thực tế như thế nào?
Bạn mô tả cách phân tách trạng thái trên nhiều nút có thể làm xuất hiện kết quả đọc không nhất quán ra sao?
Bạn giải thích mục tiêu của replication và các đánh đổi giữa độ sẵn sàng, độ trễ ghi và tính nhất quán như thế nào?
Bạn so sánh leader-follower với mô hình cho phép nhiều nút nhận ghi theo khả năng xử lý xung đột ra sao?
Bạn xác định chuyện gì xảy ra với yêu cầu đọc khi replica chưa nhận được một bản cập nhật vừa ghi ở leader như thế nào?
Bạn phân biệt synchronous replication và asynchronous replication về mất dữ liệu và độ trễ xác nhận ghi ra sao?
Bạn lựa chọn mức bảo đảm đọc theo phiên người dùng như read-your-writes hoặc monotonic reads cho tình huống nào?
Bạn phân biệt strong consistency với eventual consistency qua những kết quả quan sát được của client như thế nào?
Bạn giải thích tính linearizability bằng ví dụ hai client cùng đọc và cập nhật một bản ghi như thế nào?
Bạn phân biệt thứ tự giao dịch theo serializability với thời điểm quan sát theo linearizability trong bài toán nào?
Bạn phân tích CAP khi xảy ra network partition và giải thích vì sao không nên hiểu CAP là chọn tùy ý hai trong ba thuộc tính lúc nào cũng đúng?
Bạn lựa chọn hành vi từ chối ghi hay tiếp tục nhận ghi khi hai vùng dữ liệu mất liên lạc dựa trên tính chất nghiệp vụ nào?
Bạn giải thích cách quorum đọc và ghi có thể cải thiện bảo đảm nhất quán và những giả định giới hạn của nó ra sao?
Bạn nhận diện split-brain trong hệ có nhiều nút tin rằng mình là leader và cơ chế hạn chế tác hại như thế nào?
Bạn thiết kế cơ chế bầu leader để giảm nguy cơ hai leader cùng chấp nhận cập nhật xung đột như thế nào?
Bạn giải thích mục tiêu của consensus trong việc để nhiều nút thống nhất một quyết định trước lỗi từng phần ra sao?
Bạn phân biệt quorum, majority và số nút chịu lỗi trong nhóm consensus khi xác định khả năng tiến triển như thế nào?
Bạn đánh giá điều gì xảy ra khi nhóm consensus mất khả năng đạt đa số dù một số nút vẫn xử lý request ra sao?
Bạn giải thích vai trò của log có thứ tự trong việc tái lập trạng thái trên các nút như thế nào?
Bạn lựa chọn partition key để dữ liệu phân bố đều mà những truy vấn cùng nghiệp vụ không phải phân tán quá nhiều nút ra sao?
Bạn xử lý hot partition khi một khóa nhận phần lớn lưu lượng dù tổng dung lượng hệ thống còn dư như thế nào?
Bạn phân biệt phân mảnh theo khoảng giá trị và phân mảnh theo hàm băm về truy vấn phạm vi và phân phối tải ra sao?
Bạn thiết kế kế hoạch thay đổi số partition hoặc chuyển dữ liệu giữa các nút mà vẫn duy trì khả năng phục vụ như thế nào?
Bạn phân biệt partitioning với replication khi giải thích mục tiêu mở rộng dung lượng và mục tiêu chịu lỗi ra sao?
Bạn phân tích hệ quả của truy vấn hoặc transaction trải nhiều partition đối với độ trễ và khả năng khôi phục như thế nào?
Bạn mô tả cách message broker tách thời điểm producer gửi và consumer xử lý để hệ thống chịu tải biến động như thế nào?
Bạn phân biệt at-most-once, at-least-once và effectively-once trong giao nhận thông điệp qua các tình huống mất kết nối ra sao?
Bạn thiết kế consumer xử lý một sự kiện bị giao lại mà không cập nhật số dư hoặc trạng thái nghiệp vụ hai lần như thế nào?
Bạn xác định khi nào thứ tự message quan trọng và lựa chọn khóa phân vùng để giữ thứ tự trong phạm vi cần thiết ra sao?
Bạn thiết kế dead-letter queue và quy trình xử lý message không hợp lệ để tránh vòng retry vô hạn như thế nào?
Bạn xử lý producer đã commit dữ liệu nhưng chưa gửi được message bằng cơ chế nào nhằm hạn chế sự không nhất quán?
Bạn lựa chọn request-response hay event-driven communication khi một bước nghiệp vụ cần kết quả tức thì hoặc có thể chờ như thế nào?
Bạn thiết kế Saga hoặc hành động bù trừ cho quy trình nhiều dịch vụ không thể dùng một transaction cơ sở dữ liệu chung ra sao?
Bạn phân biệt rollback nguyên tử với hành động bù trừ có thể thất bại hoặc cần con người xử lý như thế nào?
Bạn lựa chọn giới hạn hàng đợi và backpressure để một consumer chậm không làm cạn bộ nhớ hoặc kéo sập toàn hệ thống ra sao?
Bạn thiết kế circuit breaker để cô lập dịch vụ phụ thuộc đang lỗi mà không chặn vô hạn các yêu cầu có thể phục hồi như thế nào?
Bạn áp dụng bulkhead hoặc giới hạn concurrency để một loại request chậm không chiếm hết tài nguyên của các chức năng khác ra sao?
Bạn đánh giá mối quan hệ giữa retry, timeout và circuit breaker để tránh những chính sách tự mâu thuẫn như thế nào?
Bạn xây dựng chiến lược graceful degradation khi dịch vụ gợi ý ngừng hoạt động nhưng luồng mua hàng vẫn cần chạy như thế nào?
Bạn xác định những thao tác nào cần ưu tiên tính đúng đắn tuyệt đối hơn độ sẵn sàng và giải thích bằng rủi ro nghiệp vụ ra sao?
Bạn thiết kế giám sát độ trễ, tỷ lệ lỗi, backlog và độ trễ replica để nhận diện tình trạng suy giảm của hệ phân tán như thế nào?
Bạn truyền trace ID và thông tin nhân quả qua nhiều dịch vụ để truy vết một yêu cầu bị thất bại ở chặng nào ra sao?
Bạn lập kế hoạch thử lỗi từng phần như ngắt mạng, dừng một nút hoặc làm chậm broker để kiểm chứng cơ chế phục hồi như thế nào?
Bạn phân biệt kết quả hệ thống tự phục hồi với việc dữ liệu vẫn nhất quán sau khi nút quay lại bằng cách kiểm tra nào?
Bạn thiết kế việc triển khai phiên bản mới tương thích với message hoặc API cũ khi các nút nâng cấp không đồng thời ra sao?
Bạn so sánh phương án tăng số replica, thêm partition hoặc tối ưu thuật toán khi hệ thống chạm giới hạn throughput như thế nào?
Bạn đánh giá đánh đổi giữa độ trễ, độ tin cậy, chi phí vận hành và khả năng mở rộng để chọn kiến trúc phân tán phù hợp như thế nào?
