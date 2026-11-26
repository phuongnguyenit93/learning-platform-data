Bạn phân biệt độ tin cậy, tính sẵn sàng và khả năng phục hồi của một dịch vụ qua những tình huống nào?
Bạn xác định hành vi người dùng quan trọng nào cần được bảo vệ khi xây dựng mục tiêu kiểm thử độ tin cậy?
Bạn định nghĩa và đo SLI về tính sẵn sàng từ góc nhìn người dùng dựa trên tiêu chí thành công nào?
Bạn sẽ lựa chọn SLO phù hợp với nhu cầu nghiệp vụ và mức rủi ro của hệ thống ra sao?
Error budget giúp nhóm quyết định ưu tiên tính năng mới hay cải thiện độ tin cậy như thế nào?
Bạn phân biệt mục tiêu SLO với cam kết SLA và chỉ số nội bộ khi thiết kế bài kiểm thử ra sao?
Nếu một endpoint trả mã 200 nhưng dữ liệu sai, bạn xây dựng SLI nào để phản ánh lỗi thực sự?
Bạn thiết kế kịch bản kiểm thử độ tin cậy bắt đầu từ giả thuyết lỗi và kết quả kỳ vọng như thế nào?
Bạn sẽ chọn tải nền phù hợp để các bài kiểm tra failover phản ánh điều kiện vận hành thực tế ra sao?
Khi phép thử fault injection có thể lan sang hệ thống dùng chung, bạn giới hạn phạm vi tác động bằng cách nào?
Bạn phân biệt kiểm thử chạy dài hạn với kiểm thử chịu tải ngắn hạn theo mục tiêu cần phát hiện như thế nào?
Trong một bài soak test, bạn theo dõi biến động heap, connection pool, thread và hàng đợi ra sao?
Bạn nhận diện memory leak hoặc rò rỉ tài nguyên qua nhiều giờ vận hành bằng những bằng chứng nào?
Khi số lỗi tăng dần theo thời gian, bạn phân biệt suy giảm hệ thống với thay đổi lưu lượng như thế nào?
Bạn xác định mức độ chịu lỗi mong đợi khi một dịch vụ phụ thuộc phản hồi chậm hoặc không phản hồi ra sao?
Bạn sẽ mô phỏng mất kết nối mạng tới database trong môi trường thử nghiệm có kiểm soát như thế nào?
Khi dependency trả lỗi ngắt quãng, bạn kiểm chứng timeout, retry và circuit breaker hoạt động đúng ra sao?
Bạn thiết kế retry với giới hạn số lần, exponential backoff và jitter để tránh khuếch đại quá tải như thế nào?
Trong thao tác ghi dữ liệu, bạn kiểm tra tính idempotent khi client retry sau timeout bằng cách nào?
Khi service phụ thuộc bị ngắt hoàn toàn, bạn đánh giá khả năng giảm chức năng có kiểm soát như thế nào?
Bạn sẽ đo ảnh hưởng của cơ chế fallback lên độ đúng của dữ liệu và trải nghiệm người dùng ra sao?
Bạn phân biệt lỗi ứng dụng, lỗi hạ tầng và lỗi phụ thuộc bên ngoài qua các tín hiệu quan sát nào?
Bạn đo thời gian load balancer loại bỏ một instance dừng đột ngột bằng cách nào?
Bạn thiết kế bài test failover cho cụm active-passive và xác định thời điểm hoàn tất chuyển đổi như thế nào?
Nếu dùng cụm active-active, bạn kiểm thử định tuyến và nhất quán khi một vùng bị cô lập ra sao?
Bạn phát hiện nguy cơ split-brain khi nhiều node đồng thời cho rằng mình là primary như thế nào?
Khi cơ sở dữ liệu chuyển vai trò primary, bạn kiểm tra kết nối ứng dụng và giao dịch đang dở dang ra sao?
Bạn sẽ thử nghiệm mất một vùng khả dụng mà vẫn xác minh các hành trình nghiệp vụ quan trọng như thế nào?
Bạn phân biệt RTO và RPO bằng tình huống mất dịch vụ có dữ liệu ghi gần thời điểm sự cố ra sao?
Bạn chọn điểm bắt đầu, điểm kết thúc và bằng chứng nào để đo RTO trong diễn tập phục hồi?
Bạn sẽ đo RPO thực tế bằng cách so sánh dữ liệu được xác nhận ghi và dữ liệu sau khôi phục như thế nào?
Khi backup thành công nhưng restore thất bại, bạn cải tiến bộ tiêu chí kiểm chứng bản sao lưu ra sao?
Bạn xác định chu kỳ backup và tần suất diễn tập khôi phục dựa trên RPO mong đợi như thế nào?
Khi khôi phục từ snapshot cũ, bạn xử lý giao dịch chưa được phản ánh và việc phát lại sự kiện ra sao?
Bạn sẽ kiểm chứng dữ liệu không bị mất, ghi trùng hoặc đảo thứ tự sau failover bằng các bất biến nghiệp vụ nào?
Trong hệ thống dùng message broker, bạn mô phỏng consumer crash và xác minh việc xử lý lại message ra sao?
Bạn đánh giá khả năng hệ thống phục hồi sau backlog lớn và cơ chế backpressure bằng cách nào?
Khi thông số của bộ kiểm thử gây mất ổn định, bạn sẽ phân biệt lỗi do kịch bản với lỗi của hệ thống ra sao?
Bạn đặt tiêu chí dừng và rollback thử nghiệm chaos dựa trên SLI, error rate và tác động người dùng như thế nào?
Một bài fault injection có kết quả tốt nhưng thiếu metrics có thể tạo kết luận thiếu tin cậy ra sao?
Bạn sử dụng log, tracing và dashboard để tái dựng trình tự lỗi, failover và phục hồi như thế nào?
Khi cảnh báo không kích hoạt trong lúc mô phỏng sự cố, bạn đánh giá chất lượng detection và routing ra sao?
Bạn sẽ kiểm chứng runbook xử lý sự cố bằng một diễn tập có các bước và thời gian ghi nhận như thế nào?
Khi sự cố làm vi phạm SLO nhưng hệ thống vẫn khôi phục trong RTO, bạn đánh giá hai mục tiêu này như thế nào?
Bạn so sánh kết quả nhiều lần diễn tập để phát hiện sự cải thiện thực chất hay dao động ngẫu nhiên như thế nào?
Nếu triển khai phiên bản mới làm thời gian phục hồi tăng, bạn xác định điểm thay đổi gây ảnh hưởng bằng cách nào?
Bạn lựa chọn phép thử độ tin cậy nào có thể chạy thường xuyên trong CI và phép thử nào cần môi trường riêng?
Bạn thiết kế báo cáo gồm giả thuyết, phạm vi lỗi, SLI/SLO, RTO/RPO và bằng chứng phục hồi như thế nào?
Sau khi sửa vấn đề failover, bạn thiết kế phép thử hồi quy để xác nhận lỗi cũ không tái diễn ra sao?
Bạn sẽ đưa các phát hiện từ kiểm thử độ tin cậy vào kế hoạch cải thiện kiến trúc và vận hành như thế nào?
