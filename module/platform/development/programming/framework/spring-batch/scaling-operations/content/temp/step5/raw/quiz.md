Câu 1. Trước khi tăng số thread của một Spring Batch job chậm, nên làm gì?
A. Tăng chunk size trước rồi dùng CPU để suy ra tốc độ
B. Đo CPU, I/O, DB và thời gian step trước khi tăng concurrency
C. Chuyển toàn bộ job sang remote chunking để so sánh
D. Tăng TaskExecutor pool ngay mà không đo latency DB
Đáp án đúng: B

Câu 2. Nếu step xử lý tính toán thuần đã dùng gần hết CPU, nhận định nào hợp lý?
A. Tăng thread sẽ giảm ngay lượng phép tính trên mỗi item
B. Tăng chunk size sẽ khiến tác vụ CPU thành I/O bound
C. Dùng partitioning sẽ giảm số chu kỳ CPU cần thiết
D. Tăng thread không bảo đảm tăng tốc nếu CPU đã bão hòa
Đáp án đúng: D

Câu 3. Nếu step chờ I/O phần lớn thời gian và CPU còn dư, lựa chọn nào đáng thử?
A. Giảm pool kết nối để bắt truy vấn phải chạy tuần tự
B. Tăng số lần retry dù không xảy ra lỗi ở service đích
C. Tăng concurrency và kiểm tra năng lực hệ thống đích
D. Dồn việc đọc và ghi vào một transaction của job
Đáp án đúng: C

Câu 4. Tăng chunk size trong xử lý dữ liệu lớn thường tạo đánh đổi nào?
A. Nhiều commit hơn nhưng giảm mọi thao tác tạo transaction
B. Không đổi phạm vi rollback vì mỗi item commit độc lập
C. Ít lần commit hơn nhưng tăng phạm vi rollback và bộ nhớ
D. Chỉ đổi số partition mà không đổi kích thước transaction
Đáp án đúng: C

Câu 5. Để thực thi chunk-oriented step trên nhiều thread, cơ chế nào thường dùng?
A. Dùng TaskExecutor để chạy song song các chunk của cùng step
B. Đặt cùng tên Step cho nhiều JobInstance được chạy
C. Bật restartable để ItemReader tự tạo worker thread
D. Chỉ thay JobParameters mà không cấu hình executor
Đáp án đúng: A

Câu 6. Điều nào cần lưu ý về thứ tự xử lý trong multi-threaded step?
A. Mọi item luôn được ghi theo đúng thứ tự input file
B. Mỗi thread luôn chỉ được phân công một item duy nhất
C. Thứ tự sẽ tự ổn định khi tăng kích thước chunk
D. Chunk có thể hoàn tất khác thứ tự đọc từ nguồn
Đáp án đúng: D

Câu 7. Với ItemReader có cursor và trạng thái dùng chung, rủi ro khi nhiều thread đọc là gì?
A. Các thread tự tạo checkpoint độc lập cho từng item
B. Transaction của writer sẽ tự đồng bộ cursor đầu vào
C. Race condition gây đọc trùng hoặc bỏ sót bản ghi
D. TaskExecutor tự sao chép reader cho mỗi task được tạo
Đáp án đúng: C

Câu 8. Nếu buộc dùng reader không thread-safe trong step đa luồng, nên cân nhắc gì?
A. Tăng thread pool để reader tự trở thành thread-safe
B. Đồng bộ thao tác đọc và đo lại throughput
C. Bỏ lưu checkpoint để reader khỏi tranh chấp dữ liệu
D. Đổi exception handler để sửa xung đột trên cursor
Đáp án đúng: B

Câu 9. ItemWriter giữ bộ đệm mutable dùng chung qua các thread có nguy cơ gì?
A. Mỗi thread tự nhận một writer riêng ngay khi subscribe
B. Ghi sai hoặc lặp dữ liệu nếu không bảo vệ trạng thái
C. Spring Batch tự biến mọi field mutable thành atomic
D. JobRepository sẽ rollback mọi lần ghi đồng thời
Đáp án đúng: B

Câu 10. Khi reader phụ thuộc dữ liệu riêng của từng partition, scope nào phù hợp?
A. Singleton scope giữ cùng cursor cho tất cả partition
B. Job scope bắt mỗi partition dùng chung vị trí đọc
C. Step scope tạo reader riêng theo từng partition
D. Prototype scope tự truyền partition key cho mọi reader
Đáp án đúng: C

Câu 11. Trong multi-threaded step, vì sao cần cẩn trọng khi sửa ExecutionContext từ nhiều thread?
A. Các lần cập nhật trạng thái có thể chồng lấn nhau
B. ExecutionContext chỉ chứa dữ liệu bất biến của job
C. Mỗi thread luôn được cấp một JobRepository riêng
D. Bất kỳ update nào cũng tự chạy ở transaction riêng
Đáp án đúng: A

Câu 12. Để chạy hai step độc lập cùng lúc trong một Job, nên chọn cấu trúc nào?
A. Dùng next(stepB) để bảo đảm hai step cùng bắt đầu
B. Dùng cùng một StepExecution cho cả hai step
C. Chỉ tăng số item mỗi chunk ở step đầu tiên
D. Dùng split flows và TaskExecutor cho các step
Đáp án đúng: D

Câu 13. Khi hai parallel flow đều phải xong trước khi chạy step tổng hợp, cần gì?
A. Đặt step tổng hợp trong một trong hai flow đang chạy
B. Chỉ định cùng tên bean cho cả hai flow để đồng bộ
C. Điểm join sau split trước khi chạy step tổng hợp
D. Bật skip policy để step tổng hợp đợi đủ dữ liệu
Đáp án đúng: C

Câu 14. Parallel steps khác multi-threaded step chủ yếu ở phạm vi nào?
A. Parallel steps chỉ chia một chunk thành nhiều transaction
B. Multi-threaded step bắt buộc có nhiều StepExecution
C. Multi-threaded step chỉ hoạt động qua message broker
D. Parallel steps chạy các step riêng, không chia một step
Đáp án đúng: D

Câu 15. Khi một flow phụ thuộc kết quả flow khác, chạy song song ngay có vấn đề gì?
A. Có thể đọc dữ liệu khi bước tiền nhiệm chưa hoàn tất
B. Spring Batch sẽ mặc định thêm barrier cho mọi dependency
C. JobRepository tự sắp xếp flow theo thứ tự bean name
D. Đặt chunk size nhỏ sẽ thay thế dependency giữa flow
Đáp án đúng: A

Câu 16. Trong local partitioning, Partitioner được dùng để tạo gì?
A. Các JobInstance riêng với toàn bộ JobParameters khác
B. Các transaction chung cho mọi ItemWriter worker
C. Các bean Step mới thay vì dùng một worker Step
D. Tạo dải dữ liệu trong ExecutionContext từng partition
Đáp án đúng: D

Câu 17. Giá trị map do Partitioner trả về thường gắn với thông tin nào?
A. Tên worker thread và toàn bộ message payload
B. Tên database cùng cấu hình kết nối JDBC mới
C. Map tên partition với ExecutionContext tương ứng
D. Tên JobRepository và trạng thái toàn bộ Job
Đáp án đúng: C

Câu 18. Vai trò của PartitionHandler trong Spring Batch là gì?
A. Phân phối StepExecution cho các worker thực thi
B. Xác định cách deserialize mọi bản ghi CSV đầu vào
C. Tính tổng checksum dữ liệu sau khi commit job
D. Thay thế ItemProcessor trong mọi step bị partition
Đáp án đúng: A

Câu 19. Trong cấu hình partitioning, gridSize thường là tham số liên quan đến gì?
A. Số row cần commit trong từng chunk của worker
B. Số partition dự kiến tạo trong đợt phân chia
C. Giới hạn số retry cho mỗi record không hợp lệ
D. Số lần một JobInstance được phép restart
Đáp án đúng: B

Câu 20. Khi chia bảng theo ID cho nhiều worker, yêu cầu nào giúp tránh trùng hoặc sót?
A. Mọi partition đọc toàn bảng để cân bằng hiệu năng
B. Mỗi worker dùng một ID cố định cho tất cả row
C. Chọn ngẫu nhiên các dải mà không kiểm tra độ phủ
D. Chia ID không trùng, bao phủ đầy đủ các bản ghi cần xử lý
Đáp án đúng: D

Câu 21. Nếu một partition chứa phần lớn dữ liệu, hiện tượng thường gặp là gì?
A. Job sẽ kết thúc ngay khi các worker nhanh hoàn thành
B. PartitionHandler tự chia lại mọi partition đang chạy
C. Worker chậm nhất kéo dài thời gian hoàn tất toàn step
D. Worker nhanh luôn tiếp quản transaction đang mở của nó
Đáp án đúng: C

Câu 22. Để giảm partition skew trong dữ liệu có phân bố lệch, nên cân nhắc gì?
A. Chia theo khối lượng thực để giảm partition skew
B. Chỉ tăng gridSize nhưng giữ nguyên các dải ID quá lệch
C. Buộc một partition chứa toàn bộ dữ liệu lớn nhất
D. Bỏ đo kích thước dữ liệu sau khi đã tạo partition
Đáp án đúng: A

Câu 23. Partitioned worker step thường nhận vùng dữ liệu từ đâu?
A. Một biến static duy nhất lưu dải ID của mọi worker
B. Một JobParameter bị worker tự thay đổi theo thread
C. Tên Step bean được parser suy ra từ dữ liệu CSV
D. ExecutionContext riêng được gắn với StepExecution
Đáp án đúng: D

Câu 24. Trong partitioned step, restart một worker lỗi dựa vào cơ chế nào?
A. Giữ nguyên thread Java và stack frame sau khi crash
B. Bỏ toàn bộ checkpoint để bắt worker quét dữ liệu mới
C. Chỉ kiểm tra số lượng worker đang chạy ở manager
D. Dựa trạng thái StepExecution đã lưu để phục hồi
Đáp án đúng: D

Câu 25. Remote partitioning khác local partitioning ở điểm nào?
A. Mọi worker bắt buộc chia sẻ cùng một JVM với manager
B. Worker StepExecution chạy trên tiến trình xa
C. Manager trực tiếp đọc và ghi từng chunk cho worker
D. Mỗi partition chỉ được phép chứa đúng một item
Đáp án đúng: B

Câu 26. Remote chunking chia trách nhiệm giữa manager và worker thế nào?
A. Manager đọc chunk, worker xử lý và ghi chunk được giao
B. Manager chỉ phân dải ID, worker tự đọc từ nguồn
C. Manager thực thi writer, worker chỉ quyết định chunk size
D. Manager và worker cùng đọc một item để đối soát
Đáp án đúng: A

Câu 27. Trong remote chunking, điểm nghẽn nào vẫn có thể tập trung ở manager?
A. Số CPU worker dùng để chạy ItemProcessor cục bộ
B. Tốc độ đọc dữ liệu và gửi chunk sang các worker
C. Số worker dùng để thực thi các partition độc lập
D. Số transaction viết bởi mỗi worker từ xa
Đáp án đúng: B

Câu 28. Vì sao remote chunking cần quan tâm đến độ bền message?
A. Message broker tự lưu transaction của database writer
B. Giữ message bền để không mất chunk khi có lỗi
C. Mỗi chunk luôn được xử lý đúng một lần trong mọi mạng
D. Worker tự đọc lại nguồn nếu message không tới được
Đáp án đúng: B

Câu 29. Khi hệ thống giao chunk qua broker theo at-least-once, worker cần gì?
A. Tắt mọi bước xác nhận để giảm thời gian ghi dữ liệu
B. Tạo khóa nghiệp vụ mới ở mỗi lần nhận lại chunk
C. Ghi idempotent để chunk phát lại không tạo side effect trùng
D. Chỉ tăng số worker để loại bỏ mọi message bị trùng
Đáp án đúng: C

Câu 30. Khi chọn multi-threaded step thay vì partitioning, điểm cần cân nhắc nào rõ nhất?
A. Thread safety khi các thread dùng chung state reader/writer
B. Mỗi thread luôn có StepExecution riêng như partition
C. Mọi chunk buộc gửi qua message broker ở xa
D. JobRepository không được phép ghi restart metadata
Đáp án đúng: A

Câu 31. Nếu cần mỗi worker có reader và context độc lập, kiến trúc nào phù hợp?
A. Một singleton reader cùng cursor cho mọi thread
B. Partitioning với reader riêng cho mỗi worker
C. Parallel flow nhưng dùng chung một StepExecution
D. Tăng chunk size trong một step tuần tự duy nhất
Đáp án đúng: B

Câu 32. Nếu dùng connection pool nhỏ hơn tổng concurrency, hậu quả nào có thể xảy ra?
A. Các worker chờ connection dù thread vẫn còn khả dụng
B. Mỗi worker tự tạo một database instance mới
C. JobRepository sẽ tăng kích thước pool tự động
D. Chunk transaction tự chuyển sang non-transactional
Đáp án đúng: A

Câu 33. Với hàng triệu dòng chia theo dải ID, yếu tố DB nào thường quyết định throughput?
A. Chỉ số worker thread độc lập với tốc độ đọc DB
B. Tên step trong JobRepository và cấu hình logging
C. Số lần khai báo bean processor trong application
D. Chọn index và query plan phù hợp với dải partition
Đáp án đúng: D

Câu 34. Khi tăng concurrency nhưng throughput không tăng, nên khảo sát điều gì?
A. Chỉ số lượng class ItemProcessor được biên dịch
B. Chỉ version Java mà không đo tài nguyên runtime
C. Chỉ số JobParameter không liên quan đến phân vùng
D. Đo DB pool, I/O, lock và nghẽn ở downstream
Đáp án đúng: D

Câu 35. Khi bước gọi API ngoài bị lỗi kết nối tạm thời, cơ chế nào phù hợp?
A. Retry hữu hạn với backoff và phân loại lỗi tạm thời
B. Skip ngay mọi lỗi dù dịch vụ ngoài có thể phục hồi
C. Retry vô hạn không giới hạn cho cùng một chunk
D. Bỏ transaction để xem lời gọi đã thành công hay chưa
Đáp án đúng: A

Câu 36. Nếu một record sai định dạng và không thể parse, lựa chọn nào hợp lý khi policy cho phép?
A. Retry liên tục vì parse sẽ tự hợp lệ theo thời gian
B. Skip có giới hạn và ghi nhận lỗi để xử lý sau
C. Tắt mọi validation để ghi cả record chưa parse
D. Tạo partition mới rồi chuyển record lỗi sang đó
Đáp án đúng: B

Câu 37. Tại sao retry quá nhiều có thể làm job phân tán kém ổn định?
A. Retry giảm mọi tranh chấp lock ở database theo mặc định
B. Retry quá nhiều chiếm thread và kết nối downstream
C. Retry buộc chunk commit trước khi processor hoàn thành
D. Retry tự thay đổi cấu hình partition để chia đều tải
Đáp án đúng: B

Câu 38. Khi restart chunk step, trạng thái đọc cần được quản lý qua đâu?
A. Lưu checkpoint ItemStream qua ExecutionContext
B. Chỉ dùng biến static để giữ offset sau khi JVM dừng
C. Chỉ dùng log của API gateway không chứa item state
D. Chỉ dựa vào số thread hiện có trong TaskExecutor
Đáp án đúng: A

Câu 39. Nếu writer gọi dịch vụ ngoài không cùng transaction DB, thiết kế nào an toàn hơn?
A. Giả định rollback DB sẽ đảo mọi HTTP request đã gửi
B. Tăng timeout để việc ghi ngoài trở thành atomic
C. Dùng idempotency hoặc đối soát side effect
D. Bỏ JobRepository vì đã dùng API bên ngoài
Đáp án đúng: C

Câu 40. Khi restart job thất bại với cùng identifying JobParameters, Spring Batch nhận diện gì?
A. Dùng lại JobInstance cũ để restart các step chưa hoàn tất
B. Một JobInstance khác bắt buộc vì thời điểm chạy đổi
C. Một StepExecution duy nhất cho toàn bộ lịch sử job
D. Một partition mới cho từng record đã commit trước đó
Đáp án đúng: A

Câu 41. Muốn chạy lại một job đã COMPLETED như lần chạy mới, cách nào phù hợp?
A. Chỉ gọi restart với tham số y hệt job đã hoàn tất
B. Dùng identifying JobParameters mới cho JobInstance
C. Xóa mọi StepExecution đã lưu để dùng lại instance cũ
D. Đổi chunk size mà giữ nguyên identifying parameters
Đáp án đúng: B

Câu 42. Khi vận hành job dài, JobOperator thường hỗ trợ tác vụ nào?
A. Thay thế mọi ItemReader bằng reader dùng nội bộ
B. Thay đổi bản ghi DB nghiệp vụ sau từng chunk commit
C. Điều khiển start, stop và restart JobExecution phù hợp
D. Tự sửa nội dung lỗi trong file đầu vào của worker
Đáp án đúng: C

Câu 43. Khi gửi yêu cầu stop một batch job đang chạy, cần hiểu điều gì?
A. Mọi worker bị kill ngay ở giữa transaction đang mở
B. JobRepository xóa ngay metadata của mọi StepExecution
C. Manager lập tức rollback các side effect HTTP đã có
D. Stop thường được xử lý có kiểm soát tại điểm phù hợp
Đáp án đúng: D

Câu 44. Để phát hiện partition bị treo trong vận hành, chỉ số nào hữu ích?
A. Chỉ tổng số bean được Spring Boot đăng ký lúc khởi động
B. Đo thời gian, tiến độ và lỗi của từng partition
C. Chỉ tên của từng step trong source code Java
D. Chỉ kích thước file cấu hình của manager
Đáp án đúng: B

Câu 45. Trong load test cho batch partitioned, tiêu chí nào cần đo cùng throughput?
A. Chỉ thời gian build dự án trước khi launch job
B. Chỉ số lượng worker được cấu hình trong YAML
C. Kiểm tra đủ bản ghi, không trùng và restart đúng
D. Chỉ số log INFO do TaskExecutor gửi trong một phút
Đáp án đúng: C

Câu 46. Khi tăng số partition quá mức so với tài nguyên, hậu quả nào dễ thấy?
A. Mọi partition sẽ được thực thi trên CPU riêng mới
B. Các transaction sẽ tự hợp nhất làm một lần commit
C. Chi phí điều phối và tranh chấp vượt lợi ích
D. JobRepository sẽ ngừng ghi metadata của worker
Đáp án đúng: C

Câu 47. Khi worker remote mất kết nối rồi tham gia lại, nguyên tắc nào giúp phục hồi an toàn?
A. Tin rằng chunk trước đó chắc chắn chưa ghi xuống DB
B. Gửi lại mọi partition mà không kiểm tra kết quả cũ
C. Thay tên job để xóa trạng thái đang được lưu
D. Dựa trạng thái bền vững và tránh lặp side effect
Đáp án đúng: D

Câu 48. Khi nâng cấp remote worker trong lúc manager vẫn chạy, cần bảo đảm điều gì?
A. Giữ tương thích phiên bản payload giữa manager và remote worker
B. Worker mới có thể đổi mọi field mà không cần thương lượng
C. Manager có thể dùng schema cũ nhưng tự hiểu kiểu mới
D. Mọi worker phải thay JobParameters để cùng xử lý
Đáp án đúng: A
