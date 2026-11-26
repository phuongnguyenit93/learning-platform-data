Câu 1. Trong hệ thống gọi dịch vụ phụ thuộc, circuit breaker chủ yếu giải quyết rủi ro nào?
A. Phân phối request tới nhiều instance theo tải CPU
B. Chặn sớm lời gọi tới dependency lỗi để giảm lan truyền
C. Tự khôi phục dữ liệu đã ghi lỗi trong database
D. Thực hiện lại request thất bại theo lịch backoff
Đáp án đúng: B

Câu 2. Khi circuit breaker ở trạng thái CLOSED, điều gì diễn ra với lời gọi?
A. Chặn các lời gọi đến dependency cho tới hết thời gian chờ
B. Chỉ cho một số lời gọi thử đi qua để đo phục hồi
C. Chuyển mọi lời gọi sang phương án fallback
D. Cho phép lời gọi đi qua và ghi nhận kết quả để đánh giá
Đáp án đúng: D

Câu 3. Khi circuit breaker chuyển sang OPEN, hành vi điển hình là gì?
A. Đợi backend hoàn tất mỗi request rồi mới trả lỗi
B. Cho phép số lời gọi thử bằng số thread hiện tại
C. Xóa mọi kết quả gọi đã lưu trong sliding window
D. Từ chối sớm lời gọi thay vì truy cập dependency
Đáp án đúng: D

Câu 4. HALF_OPEN có mục đích chính nào trong vòng đời circuit breaker?
A. Gửi lại tất cả request bị từ chối ở trạng thái OPEN
B. Cho ít lời gọi thử để kiểm tra khả năng phục hồi
C. Khóa toàn bộ dependency đến khi ứng dụng restart
D. Bật chế độ đọc dữ liệu từ cache cho mọi lời gọi
Đáp án đúng: B

Câu 5. Sau các phép thử trong HALF_OPEN, khi nào breaker phù hợp để đóng lại?
A. Ngay khi nhận được phản hồi đầu tiên bất kể mã lỗi
B. Khi số request đồng thời bằng mức tối đa của bulkhead
C. Khi timeout của mọi lời gọi được tăng thêm một lần
D. Khi kết quả thử đáp ứng ngưỡng thành công đã cấu hình
Đáp án đúng: D

Câu 6. Nếu các lời gọi thử trong HALF_OPEN tiếp tục thất bại vượt ngưỡng, chuyện gì thường xảy ra?
A. Breaker giữ CLOSED vì đã có request thực thi được
B. Breaker chuyển vào một trạng thái retry vô hạn
C. Breaker quay lại OPEN để tiếp tục bảo vệ dependency
D. Breaker tự tăng ngưỡng lỗi cho tới khi đạt 100 phần trăm
Đáp án đúng: C

Câu 7. Count-based sliding window của Resilience4j theo dõi tập dữ liệu nào?
A. Các lời gọi hoàn tất gần nhất theo số lượng đã đặt
B. Mọi lời gọi từ khi tiến trình Java được khởi động
C. Mọi lời gọi trong số giây do time window quy định
D. Chỉ các request bị từ chối ở trạng thái OPEN
Đáp án đúng: A

Câu 8. Time-based sliding window trong Resilience4j hoạt động theo nguyên tắc nào?
A. Giữ cố định N lời gọi cuối bất kể thời điểm thực thi
B. Tính thống kê các lời gọi trong khoảng thời gian gần đây
C. Tính số thread bị bận trong khoảng thời gian timeout
D. Đếm số lượt chuyển OPEN sang HALF_OPEN mỗi phút
Đáp án đúng: B

Câu 9. minimumNumberOfCalls có ý nghĩa gì đối với failure-rate threshold?
A. Chỉ tính điều kiện mở khi đủ số lời gọi tối thiểu
B. Giới hạn tối đa số request được gọi ở trạng thái CLOSED
C. Đặt số request thử khi breaker đang ở trạng thái HALF_OPEN
D. Chọn số lần retry cho mỗi lời gọi thất bại
Đáp án đúng: A

Câu 10. failureRateThreshold trong Resilience4j thường biểu diễn điều gì?
A. Số mili giây tối đa mà mỗi lời gọi được phép chạy
B. Số lời gọi thử được cho qua khi chuyển HALF_OPEN
C. Phần trăm lời gọi lỗi dùng để quyết định mở breaker
D. Tổng số request cần lưu trong bộ đệm fallback
Đáp án đúng: C

Câu 11. slowCallRateThreshold phục vụ mục đích gì khi bảo vệ dịch vụ chậm?
A. Mở breaker khi tỷ lệ lời gọi chậm vượt ngưỡng cấu hình
B. Hủy ngay mọi request có độ trễ vượt giá trị timeout
C. Tăng số worker xử lý để giảm số lời gọi đang chờ
D. Chỉ ghi các lời gọi trả exception vào sliding window
Đáp án đúng: A

Câu 12. slowCallDurationThreshold xác định điều kiện nào?
A. Số giây cần đợi ở OPEN trước khi thử HALF_OPEN
B. Thời gian vượt quá thì một lời gọi được phân loại là chậm
C. Thời gian tối đa cho phép của một vòng retry backoff
D. Khoảng thời gian lấy mẫu cho count-based sliding window
Đáp án đúng: B

Câu 13. waitDurationInOpenState thường điều chỉnh điều gì?
A. Số request tối đa được phép vào cùng một time window
B. Thời gian ngủ giữa các lần retry của cùng request
C. Khoảng trễ bắt buộc trước mỗi lượt gọi ở CLOSED
D. Khoảng chờ ở OPEN trước khi được phép thăm dò lại
Đáp án đúng: D

Câu 14. Khi không bật automatic transition từ OPEN sang HALF_OPEN, cơ chế nào thường kích hoạt thử lại?
A. Mọi lời gọi bị từ chối sẽ tự chạy lại từ bộ nhớ
B. Bộ đếm retry tự đặt lại trạng thái vào CLOSED
C. Lời gọi tiếp theo sau khi thời gian OPEN đã hết
D. Timer của HTTP client tự đổi breaker thành HALF_OPEN
Đáp án đúng: C

Câu 15. permittedNumberOfCallsInHalfOpenState liên quan trực tiếp tới điều gì?
A. Giới hạn số lời gọi thử được cho qua trong HALF_OPEN
B. Số lượng lỗi bị bỏ qua khi breaker đang ở CLOSED
C. Số bản ghi được lưu trong count-based sliding window
D. Số thread dành riêng cho fallback khi service lỗi
Đáp án đúng: A

Câu 16. Khi một exception được cấu hình là recorded failure, nó tác động thế nào?
A. Bị bỏ qua hoàn toàn khỏi thống kê thành công và thất bại
B. Được tính vào thống kê thất bại của các lời gọi được phép
C. Luôn được tự retry dù chưa cấu hình cơ chế retry
D. Làm breaker chuyển trực tiếp sang trạng thái DISABLED
Đáp án đúng: B

Câu 17. Khi cấu hình ignoreExceptions trong Resilience4j, exception phù hợp sẽ được xử lý thế nào?
A. Được tính như một thành công để kéo giảm failure rate
B. Được tính như một failure nhưng không ghi vào log
C. Tự làm breaker mở mà không xét minimumNumberOfCalls
D. Không tính vào số call thành công hay thất bại
Đáp án đúng: D

Câu 18. Với HTTP 4xx do dữ liệu đầu vào của client không hợp lệ, cách phân loại nào thường phù hợp?
A. Luôn tính là dependency failure để tăng bảo vệ
B. Tự thay response 4xx thành 503 qua fallback
C. Bật retry không giới hạn trước khi kiểm tra input
D. Tránh tính lỗi validation của caller là lỗi phụ thuộc
Đáp án đúng: D

Câu 19. Trong Resilience4j, CallNotPermittedException thường báo hiệu điều gì?
A. Lời gọi đã vượt thời gian chờ của TimeLimiter
B. Lời gọi không được tìm thấy trong Service Registry
C. Circuit breaker chặn lời gọi trước khi chạy dependency
D. Lời gọi bị từ chối bởi bộ parse của HTTP client
Đáp án đúng: C

Câu 20. Fallback trong lời gọi có circuit breaker nên được hiểu là gì?
A. Một cơ chế tự động ghi lại request để retry về sau
B. Một cách khôi phục database transaction đã rollback
C. Phương án xử lý thay thế khi dependency gặp lỗi
D. Một thuật toán cân bằng tải giữa các instance backend
Đáp án đúng: C

Câu 21. Fallback gọi lại chính dependency đang lỗi có nguy cơ gì?
A. Làm failure-rate threshold được tính theo sliding window mới
B. Tiếp tục gây tải và làm mất hiệu quả bảo vệ của breaker
C. Tự đưa breaker trở về CLOSED sau mỗi yêu cầu thất bại
D. Làm các call bị từ chối trở thành call thành công
Đáp án đúng: B

Câu 22. Vì sao circuit breaker không thay thế timeout của HTTP client?
A. Breaker luôn chủ động hủy socket khi request vượt SLA
B. Timeout chỉ áp dụng cho cache chứ không áp dụng HTTP
C. Breaker không tự ngắt các HTTP request đang treo
D. Khi có breaker, dependency không còn cần giới hạn thời gian
Đáp án đúng: C

Câu 23. TimeLimiter trong bộ công cụ resilience chủ yếu giải quyết nhu cầu nào?
A. Giới hạn số lời gọi đồng thời được phép tới dependency
B. Đếm tỷ lệ lỗi qua cửa sổ N request gần nhất
C. Giới hạn thời gian chờ kết quả của tác vụ bất đồng bộ
D. Định tuyến mọi request tới một backend dự phòng
Đáp án đúng: C

Câu 24. Bulkhead khác circuit breaker chủ yếu ở khía cạnh nào?
A. Bulkhead phân loại lỗi bằng sliding window, breaker đếm thread
B. Bulkhead giới hạn tài nguyên đồng thời, breaker chặn theo sức khỏe
C. Bulkhead chỉ tạo fallback, breaker chỉ điều phối thread pool
D. Bulkhead chỉ áp dụng lúc OPEN, breaker chỉ áp dụng lúc CLOSED
Đáp án đúng: B

Câu 25. Semaphore bulkhead thường áp dụng cách kiểm soát nào?
A. Tạo một thread pool mới cho mỗi request được nhận
B. Tính tỷ lệ lỗi dựa trên số request đã kết thúc
C. Đợi đúng thời gian OPEN trước khi cấp permit
D. Giới hạn số lời gọi thực thi đồng thời bằng permit
Đáp án đúng: D

Câu 26. Thread-pool bulkhead khác semaphore bulkhead ở điểm điển hình nào?
A. Cách ly tác vụ bằng executor và hàng đợi riêng
B. Chỉ dùng permit trên thread hiện tại của caller
C. Thay sliding window bằng số thread có sẵn
D. Chỉ chạy khi đã cấu hình một breaker HALF_OPEN
Đáp án đúng: A

Câu 27. Nếu dependency bị nghẽn vì quá nhiều lời gọi đồng thời, lựa chọn nào trực tiếp giới hạn tải?
A. Đặt bulkhead để giới hạn concurrency tới backend
B. Tăng failureRateThreshold lên mức cao hơn hiện tại
C. Dùng timeout dài hơn để giữ thêm request đang chờ
D. Thêm cache vào kết quả retry để tránh metric đếm trùng
Đáp án đúng: A

Câu 28. Vì sao retry vô hạn có thể làm sự cố downstream nghiêm trọng hơn?
A. Làm circuit breaker quên mọi kết quả lỗi đã ghi nhận
B. Retry có thể nhân tải và làm cạn connection downstream
C. Biến các exception network thành kết quả HTTP thành công
D. Tự tăng thời gian chờ OPEN sau mỗi lần service hồi phục
Đáp án đúng: B

Câu 29. Kết hợp retry và circuit breaker cần cân nhắc yếu tố nào?
A. Retry và breaker luôn cùng đếm một request như nhau
B. Khi có retry thì breaker tự bỏ qua mọi failure rate
C. Thứ tự wrapper tác động số attempt được breaker tính
D. Thứ tự chỉ ảnh hưởng tên metric chứ không ảnh hưởng hành vi
Đáp án đúng: C

Câu 30. Với thao tác ghi có thể được retry sau timeout, thiết kế nào giúp tránh tạo đơn trùng?
A. Tạo idempotency key mới ở từng lần retry để dễ truy vết
B. Tăng sliding window size để database tự loại trùng
C. Giữ cùng idempotency key khi retry một yêu cầu ghi
D. Giảm slow-call threshold để tự rollback yêu cầu
Đáp án đúng: C

Câu 31. Trong Spring Cloud Circuit Breaker, CircuitBreakerFactory thường có vai trò gì?
A. Tạo repository lưu các bản ghi metric từ Actuator
B. Thay thế HTTP client của mọi microservice khi startup
C. Tự phát hiện các controller cần chạy fallback
D. Tạo breaker theo tên để bao quanh lời gọi dịch vụ
Đáp án đúng: D

Câu 32. Khi tích hợp Spring Cloud Circuit Breaker với Resilience4j, việc đặt tên instance giúp gì?
A. Tự sinh retry policy chỉ từ tên class Java
B. Gắn cấu hình và số liệu theo dependency hoặc nhóm gọi
C. Gộp mọi backend thành một breaker không phân biệt
D. Bỏ qua hoàn toàn các condition từ ứng dụng Spring Boot
Đáp án đúng: B

Câu 33. Trong Spring Cloud, một lời gọi qua breaker được gắn fallback ở đâu là hợp lý?
A. Trong phần cấu hình retry mặc định áp dụng cho mọi bean
B. Trong cấu hình timeout của HTTP client không kèm callback
C. Trong các tag metric được gửi tới exporter Prometheus
D. Trong logic chạy qua breaker với handler nhận lỗi tương ứng
Đáp án đúng: D

Câu 34. Khi API trả về Mono từ một lời gọi phụ thuộc, tích hợp reactive breaker cần giữ nguyên điều gì?
A. Sự bất đồng bộ và cơ chế subscribe của publisher
B. Việc block thread cho đến khi mọi span được export
C. Việc khởi tạo một subscription ngay lúc tạo bean
D. Việc chặn onError để luôn hoàn tất thành onComplete
Đáp án đúng: A

Câu 35. Vì sao nên bọc công việc phụ thuộc bằng Mono.defer khi cần trì hoãn side effect?
A. Để lời gọi chạy ngay trong constructor của controller
B. Để circuit breaker tự tạo một thread riêng cho Mono
C. Để mọi lần subscribe cùng dùng một HTTP response cũ
D. Để thao tác thực sự bắt đầu khi subscriber đăng ký
Đáp án đúng: D

Câu 36. Trong reactive pipeline, onErrorResume có vai trò phù hợp nào khi dùng fallback?
A. Buộc circuit breaker chuyển OPEN ngay sau lỗi đầu
B. Tạo một TimeLimiter mới ở mọi phần tử dữ liệu
C. Chọn publisher dự phòng theo loại lỗi được nhận
D. Tự gửi lại tất cả request HTTP đã bị hủy
Đáp án đúng: C

Câu 37. Dùng block() trong đường xử lý WebFlux đang chạy event loop có rủi ro gì?
A. Làm ReactiveCircuitBreakerFactory tự bỏ qua cấu hình tên
B. Block chiếm event-loop thread và giảm concurrency
C. Tăng số lần timeout khi request được xử lý trong executor
D. Làm Retry tự chuyển thành SemaphoreBulkhead
Đáp án đúng: B

Câu 38. Trong reactive request bị timeout, điều nào cần được kiểm chứng khi retry?
A. Mọi lời gọi phía server chắc chắn đã rollback transaction
B. Publisher tự xóa side effect khi nhận tín hiệu cancel
C. Tác vụ cũ có thể còn side effect dù subscriber đã hủy
D. Circuit breaker không thể ghi nhận một tín hiệu timeout
Đáp án đúng: C

Câu 39. Để theo dõi trạng thái breaker trong production, nhóm metric nào hữu ích?
A. Theo dõi state, failure/slow-call rate và call bị chặn
B. Chỉ số connection pool và tổng CPU sử dụng của JVM
C. Chỉ thời lượng của lần retry nhanh nhất khi thành công
D. Chỉ số lần timeout không gắn instance breaker
Đáp án đúng: A

Câu 40. Vì sao không nên dùng orderId hoặc userId làm tag metric circuit breaker?
A. Tag dạng số làm failureRateThreshold không còn hoạt động
B. Circuit breaker chỉ nhận metric có tag kiểu boolean
C. Timer tự chặn mọi lời gọi có tag không cố định
D. Mỗi giá trị tạo nhãn mới và gây cardinality lớn
Đáp án đúng: D

Câu 41. Công cụ nào hỗ trợ nhận biết breaker chuyển CLOSED sang OPEN theo thời gian?
A. Tổng số callback đã đăng ký trong bean CircuitBreakerFactory
B. Histogram độ trễ không theo dõi trạng thái breaker
C. Chỉ số timeout của client không gắn state transition
D. Event hoặc metric về state transition của breaker
Đáp án đúng: D

Câu 42. Khi nhiều replica của service dùng circuit breaker, điều nào thường đúng?
A. Mọi replica tự chia sẻ cùng state breaker qua JVM heap
B. Mỗi instance breaker theo dõi trạng thái cục bộ của nó
C. Trạng thái breaker bắt buộc lưu trong một transaction DB
D. Chỉ replica đầu tiên được phép chuyển sang HALF_OPEN
Đáp án đúng: B

Câu 43. Khi đặt slow-call threshold rất thấp so với latency bình thường, rủi ro nào xuất hiện?
A. Breaker chỉ ghi nhận exception mà không xét duration
B. Breaker mở nhầm vì coi request bình thường là chậm
C. Bulkhead tự tăng số permit khi thấy nhiều slow call
D. Fallback tự thay đổi cấu hình TimeLimiter phù hợp
Đáp án đúng: B

Câu 44. Trong HALF_OPEN, vì sao cần giới hạn số cuộc gọi kiểm tra?
A. Tránh dồn tải thử nghiệm lên backend vừa phục hồi
B. Đảm bảo mọi request chờ từ OPEN được phát lại cùng lúc
C. Để tăng số lời gọi chưa hoàn tất trong sliding window
D. Để reset toàn bộ số liệu thành công của service khác
Đáp án đúng: A

Câu 45. Trong thử nghiệm lỗi backend, kiểm tra nào xác nhận breaker thật sự bảo vệ hệ thống?
A. Vượt ngưỡng thì call mới bị chặn, fallback được chạy
B. Khi lỗi xảy ra, breaker vẫn luôn chuyển tiếp mọi call
C. Khi backend hỏng, retry sẽ không tạo thêm request
D. Khi lỗi một lần, tất cả replica cùng mở ngay lập tức
Đáp án đúng: A

Câu 46. Khi fallback trả dữ liệu cũ từ cache, điều kiện nghiệp vụ nào cần cân nhắc?
A. Coi cache luôn mới nên bỏ timestamp và TTL
B. Dùng dữ liệu cũ cho mọi lệnh ghi mà không kiểm tra
C. Cho biết mức độ cũ và chỉ dùng khi dữ liệu chấp nhận được
D. Bỏ phân quyền vì breaker đã chặn dependency
Đáp án đúng: C

Câu 47. Để đánh giá hiệu quả circuit breaker sau triển khai, nên quan sát điều gì?
A. Đo latency, lỗi lan truyền và số call backend khi lỗi
B. Chỉ tỷ lệ retry thành công lúc downstream còn khỏe
C. Chỉ số request thành công vào lúc backend không có lỗi
D. Chỉ lượng timeout khi circuit breaker còn CLOSED
Đáp án đúng: A

Câu 48. Khi breaker chuyển OPEN, hành vi của fallback nên được thiết kế thế nào?
A. Nhanh, có giới hạn tài nguyên và không tái gây nghẽn
B. Luôn đồng bộ gọi lại backend chính để chắc có dữ liệu
C. Chờ cho tất cả request trước đó hoàn tất mới trả
D. Tạo một thread riêng không giới hạn cho mỗi request
Đáp án đúng: A
