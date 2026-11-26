Câu 1. Trong hệ thống Spring Cloud Task, workload nào phù hợp nhất?
A. Chạy HTTP server tiếp nhận request liên tục qua nhiều ngày
B. Duy trì WebSocket connection đến khi người dùng ngắt
C. Chạy service discovery để theo dõi instance trong cluster
D. Xử lý một đợt dữ liệu hữu hạn rồi kết thúc tiến trình
Đáp án đúng: D

Câu 2. Sự khác biệt chính giữa ứng dụng Task và web service luôn chạy là gì?
A. Task hoàn thành công việc rồi dừng thay vì phục vụ liên tục
B. Task tự tạo REST endpoint để giám sát từng lần thực thi
C. Task không thể dùng bean Spring hoặc dependency injection
D. Task phải được triển khai thành Kubernetes Deployment dài hạn
Đáp án đúng: A

Câu 3. Với ứng dụng Spring Cloud Task, @EnableTask giúp thực hiện điều gì?
A. Tạo một JobRepository của Spring Batch không cần cấu hình
B. Lập lịch Cron mặc định để chạy lại mỗi phút
C. Kích hoạt hạ tầng theo dõi vòng đời thực thi Task
D. Bật API HTTP quản trị task trên cổng actuator riêng
Đáp án đúng: C

Câu 4. TaskExecution thường dùng để biểu diễn thông tin nào?
A. Một định nghĩa CronJob dùng để khởi chạy theo lịch
B. Một tập các StepExecution trong một Batch job
C. Một pool thread đang hoạt động của ứng dụng
D. Một lần chạy với thời điểm, trạng thái và mã kết thúc
Đáp án đúng: D

Câu 5. TaskRepository có vai trò chính nào trong Spring Cloud Task?
A. Định tuyến request HTTP giữa các instance của dịch vụ
B. Tự retry nghiệp vụ khi một tác vụ trả exit code lỗi
C. Lưu nội dung từng bản ghi input của tất cả batch step
D. Lưu và cập nhật metadata của các lần thực thi Task
Đáp án đúng: D

Câu 6. Muốn truy vấn lịch sử TaskExecution để báo cáo vận hành, abstraction nào phù hợp?
A. TaskScheduler tự trả danh sách TaskExecution từ Cron
B. TaskExplorer cung cấp thao tác đọc thông tin Task đã ghi
C. JobLauncher luôn truy vấn metadata Task qua StepExecution
D. ServiceRegistry cho phép lấy lịch sử theo service ID
Đáp án đúng: B

Câu 7. Khi nhiều lần chạy Task phải được lưu qua các lần khởi động, nên chọn gì?
A. Chỉ dùng cấu trúc Map trong bộ nhớ của tiến trình Task
B. Đưa lịch sử Task vào biến static của ApplicationContext
C. TaskRepository có nguồn lưu trữ bền vững và cấu hình DB
D. Ghi TaskExecution vào cache chỉ tồn tại trong một Pod
Đáp án đúng: C

Câu 8. Vì sao cần chuẩn bị schema database tương thích với Spring Cloud Task?
A. Repository phải truy cập được các bảng metadata của Task
B. TaskRepository sẽ tự sinh Kubernetes Job manifest để chạy
C. TaskRunner chỉ lưu các bản ghi trong file cấu hình YAML
D. Schema Batch luôn đủ để chứa mọi trường của TaskExecution
Đáp án đúng: A

Câu 9. Khi database lưu TaskExecution không truy cập được lúc startup, rủi ro nào cần xử lý?
A. Task tự tiếp tục ghi lịch sử vào mọi replica trong cluster
B. Task chuyển sang lưu metadata trong HTTP response mặc định
C. TaskExplorer tự tạo một database khác để bỏ qua lỗi
D. Không ghi nhận được metadata và có thể làm Task khởi động lỗi
Đáp án đúng: D

Câu 10. Một execution ID của TaskExecution nên được hiểu như thế nào?
A. Tên logic giữ nguyên cho mọi lần chạy của cùng một Task
B. Khóa dùng để gom mọi Batch JobInstance có chung profile
C. Mã nhận diện riêng cho một lần thực thi được lưu trữ
D. Mã phiên bản artifact được Kubernetes cấp khi deploy
Đáp án đúng: C

Câu 11. Một ứng dụng Task được gọi hai lần với cùng business parameter, điều gì thường đúng?
A. Framework tự hợp nhất hai lần chạy thành một TaskExecution
B. Lần chạy thứ hai bị từ chối nếu chưa bật Spring Batch
C. Hai lượt chạy được ghi thành TaskExecution riêng
D. TaskRepository tự rollback dữ liệu do lần chạy đầu tạo
Đáp án đúng: C

Câu 12. Khi Task hoàn tất bình thường, metadata nào hữu ích để đo thời lượng?
A. Start time và end time của từng TaskExecution
B. Tên thread và lượng heap lúc compile file JAR
C. Số lượng bean singleton đã đăng ký trong context
D. Tên profile Kubernetes và số lượng ServiceInstance
Đáp án đúng: A

Câu 13. Nếu tiến trình bị kill trước khi cập nhật kết quả, dữ liệu TaskExecution có thể ra sao?
A. TaskRepository tự tạo kết quả thành công dù JVM đã chết
B. Mọi batch step được đánh dấu COMPLETED do Pod đã dừng
C. Bản ghi có thể thiếu end time hoặc trạng thái kết thúc
D. TaskExplorer tự thực thi lại lệnh chưa hoàn thành
Đáp án đúng: C

Câu 14. Exit code của Task giúp công cụ điều phối nhận biết điều gì?
A. Số instance cần tăng sau mỗi lần tác vụ hoàn thành
B. Số tham số bắt buộc phải truyền tới TaskRepository
C. Kết quả thành công hay lỗi của lần chạy theo quy ước
D. Thời điểm scheduler cần phát lệnh chạy tiếp theo
Đáp án đúng: C

Câu 15. Khi Task bắt được exception nhưng không báo lỗi ra ngoài, cần chú ý điều gì?
A. TaskRepository tự suy ra mọi lỗi từ log message của Java
B. Exit code có thể che lỗi nghiệp vụ đã bị bắt
C. Lệnh gọi tiếp theo sẽ tự nhận lại exception đã xử lý
D. JobExplorer tự đặt exit code dựa theo số dòng ghi log
Đáp án đúng: B

Câu 16. TaskExecutionListener thường được dùng để giải quyết nhu cầu nào?
A. Gửi yêu cầu cân bằng tải đến các instance khác trong cluster
B. Thay thế transaction manager của mọi Spring Batch step
C. Tự tạo retry policy cho scheduler bên ngoài ứng dụng
D. Callback tại startup, kết thúc và thất bại của Task
Đáp án đúng: D

Câu 17. Callback onTaskFailed trong TaskExecutionListener hữu ích lúc nào?
A. Xử lý bổ sung khi Task báo một lần chạy thất bại
B. Khi cần xác định địa chỉ Pod để load balancing HTTP
C. Khi cần tạo bean DataSource cho mọi lần refresh scope
D. Khi cần khai báo Cron trigger cho một task định kỳ
Đáp án đúng: A

Câu 18. CommandLineRunner trong một ứng dụng Spring Boot Task dùng để làm gì?
A. Chạy logic tác vụ sau khi Spring context được tạo
B. Tạo metadata Task trước khi các bean Spring được nạp
C. Buộc TaskRepository chỉ lưu các tham số dạng số
D. Đăng ký Task như một endpoint servlet xử lý HTTP
Đáp án đúng: A

Câu 19. ApplicationRunner khác CommandLineRunner chủ yếu ở tham số đầu vào nào?
A. Nhận TaskExecution thay cho mọi loại tham số dòng lệnh
B. Nhận JobRepository thay vì ApplicationContext khởi tạo
C. Nhận CronExpression thay vì các tùy chọn command line
D. Nhận ApplicationArguments thay vì mảng String trực tiếp
Đáp án đúng: D

Câu 20. Khi truyền --date=2026-11-26 cho một lần chạy Task, cách nào hợp lý để đọc giá trị?
A. Đọc trực tiếp tên Pod từ DiscoveryClient để tìm ngày
B. Đọc option từ ApplicationArguments hoặc Environment
C. Đọc JobExecutionContext bất kể tác vụ có dùng Batch
D. Đặt @Scheduled lên mọi tham số của phương thức main
Đáp án đúng: B

Câu 21. Khi cần ghi lại tham số launch để tái hiện một Task, điểm nào quan trọng?
A. Lưu thông tin không nhạy cảm và có cách truy vết đầu vào
B. In toàn bộ token xác thực vào bảng TaskExecution.arguments
C. Đặt mật khẩu database trong CLI để TaskExplorer dễ đọc
D. Gửi mọi giá trị raw arguments đến metric tag theo taskName
Đáp án đúng: A

Câu 22. Vì sao không nên truyền password hoặc token qua command-line arguments?
A. CommandLineRunner sẽ tự mã hóa mọi token trước khi sử dụng
B. Spring Cloud Task chỉ hỗ trợ đối số đã có trong ConfigMap
C. Các tham số CLI được bảo vệ bởi transaction của TaskRepository
D. CLI arguments có thể lộ trong metadata và hệ thống giám sát
Đáp án đúng: D

Câu 23. Làm thế nào để một Task chạy theo yêu cầu của người dùng?
A. TaskRepository tự tạo REST API gọi tác vụ theo tên
B. TaskExplorer mở HTTP listener để chờ lệnh khởi chạy
C. Hệ thống bên ngoài chạy process khi có yêu cầu
D. TaskExecutionListener duy trì một scheduler đa tenant
Đáp án đúng: C

Câu 24. Muốn chạy Task mỗi đêm trong Kubernetes, thành phần nào thường phù hợp?
A. Spring Cloud Task tự đăng ký CronJob khi @EnableTask
B. Kubernetes CronJob điều phối việc tạo Job theo lịch
C. Spring Batch JobRepository tự lên lịch theo cron expression
D. Kubernetes Service thực thi main class vào đúng thời điểm
Đáp án đúng: B

Câu 25. Vì sao phải xét concurrency khi scheduler có thể chạy trùng một Task?
A. TaskRepository tự khóa mọi nghiệp vụ theo taskName
B. TaskExecution ID giống nhau nên database tự bỏ lần thứ hai
C. Mọi Task được chạy trong cùng một JVM nếu trùng lịch
D. Hai execution có thể cùng sửa dữ liệu và gây xung đột
Đáp án đúng: D

Câu 26. Trong bài toán import đơn hàng chạy lại sau timeout, biện pháp nào hạn chế duplicate?
A. Tạo khóa nghiệp vụ mới cho mỗi lần launch Task
B. Xóa các execution record cũ trước mỗi lần chạy lại
C. Ghi dữ liệu idempotent bằng khóa nghiệp vụ ổn định
D. Tăng số thread xử lý để hai lần chạy kết thúc nhanh
Đáp án đúng: C

Câu 27. Khi orchestrator tự retry một Task bị lỗi, điều cần quan tâm là gì?
A. Retry luôn tiếp tục JVM cũ từ dòng code đang dở
B. Retry có thể lặp side effect của lần chạy trước
C. TaskRepository tự hoàn tác toàn bộ HTTP side effect
D. Lần retry sẽ tự dùng chính execution ID cũ
Đáp án đúng: B

Câu 28. Nếu Task gửi dữ liệu sang dịch vụ ngoài trước khi bị lỗi, cách phục hồi nào an toàn?
A. Dùng checkpoint hoặc idempotency để tránh gửi trùng
B. Chạy lại toàn bộ lời gọi mà không ghi nhận tiến độ
C. Chỉ xóa bảng TaskExecution để bắt đầu một execution mới
D. Tăng exit code để dịch vụ ngoài bỏ qua bản ghi cũ
Đáp án đúng: A

Câu 29. Khi chạy nhiều replica của cùng một Task độc lập, nên quan sát gì để phát hiện xung đột?
A. Số lượng HTTP controller đang mở trên mỗi replica
B. Tên Config Server trùng nhau giữa các ứng dụng
C. Số session sticky do load balancer giữ cho Pod
D. Theo dõi thời điểm chạy chồng lấn và khóa dữ liệu
Đáp án đúng: D

Câu 30. Sử dụng TaskRepository không có nghĩa framework tự bảo đảm điều gì?
A. Exactly-once cho các side effect nghiệp vụ ngoài Task
B. Có thể lưu metadata cho từng TaskExecution được chạy
C. Có thể tra cứu thông tin Task đã chạy qua TaskExplorer
D. Có thể ghi nhận mã kết thúc khi Task đóng đúng vòng đời
Đáp án đúng: A

Câu 31. Khi một Task xử lý lượng dữ liệu lớn theo từng phần, tích hợp nào phù hợp?
A. Dùng DiscoveryClient để chia chunk dữ liệu tự động
B. Dùng Spring Batch quản lý job, step và checkpoint
C. Dùng Config Server làm kho checkpoint cho từng record
D. Dùng LoadBalancerClient thay transaction của Batch step
Đáp án đúng: B

Câu 32. TaskRepository khác JobRepository của Spring Batch ở điểm chính nào?
A. Cả hai dùng để ghi log HTTP nhưng khác định dạng output
B. TaskRepository lưu TaskExecution; JobRepository lưu job/step
C. TaskRepository chỉ lưu cache, JobRepository chỉ lưu metric
D. JobRepository lưu Pod IP còn TaskRepository lưu Service ID
Đáp án đúng: B

Câu 33. Khi Task khởi chạy một Spring Batch job, cần hiểu quan hệ nào?
A. TaskExecution có thể gắn với một Batch JobExecution
B. TaskExecution luôn đồng nhất với từng Batch StepExecution
C. JobInstance chính là tên file JAR chứa Task và config
D. Batch metadata tự thay thế TaskRepository khi job bắt đầu
Đáp án đúng: A

Câu 34. Vì sao Batch job chạy trong Task vẫn cần JobRepository riêng?
A. TaskRepository tự ghi mọi chunk commit thay cho Batch
B. TaskExplorer có đủ metadata để rollback từng item
C. Spring Cloud Task dùng Batch JobRepository làm exit-code mapper
D. Batch cần lưu trạng thái job/step để restart và checkpoint
Đáp án đúng: D

Câu 35. Khi muốn restart Batch job thất bại, yếu tố nào quan trọng?
A. Thay TaskExecution ID bằng tên Pod để khởi động lại job
B. Xóa JobRepository trước để tránh metadata từ lần cũ
C. JobParameters nhận diện JobInstance và metadata restart
D. Tăng service ID của JobLauncher sau mỗi lần restart
Đáp án đúng: C

Câu 36. Nếu cùng JobParameters nhận diện một Batch JobInstance đã COMPLETED, việc chạy lại thường có rủi ro gì?
A. Spring Batch tự khởi tạo lại mọi step dù đã COMPLETED
B. Batch có thể từ chối chạy lại JobInstance đã COMPLETED
C. TaskRepository luôn biến JobParameters thành tên Task khác
D. JobLauncher mặc định bỏ qua toàn bộ metadata lịch sử
Đáp án đúng: B

Câu 37. Vì sao không nên coi exit code Task và Batch ExitStatus hoàn toàn giống nhau?
A. Task và Batch có lifecycle riêng, cần đồng bộ kết quả
B. Mỗi Batch ExitStatus tự tạo process exit code bằng TaskRepository
C. Batch JobRepository không lưu kết quả đã chạy của các step
D. TaskExecution ID chính là Batch ExitStatus khi hoàn tất
Đáp án đúng: A

Câu 38. Khi một Batch job thất bại nhưng Task wrapper vẫn trả exit code 0, hệ quả nào dễ gặp?
A. Orchestrator hiểu nhầm Batch job lỗi là Task thành công
B. Batch JobRepository tự xóa trạng thái FAILED của mọi step
C. TaskExplorer tự động gọi lại JobLauncher với tham số cũ
D. Kubernetes CronJob tự sửa exit code trong container
Đáp án đúng: A

Câu 39. Khi một Batch Step commit từng chunk rồi Task bị kill, restart đúng cách cần dựa vào gì?
A. Chỉ dựa vào TaskExecution ID được lưu bởi TaskRepository
B. Dùng checkpoint của Batch và xử lý lại dữ liệu an toàn
C. Bỏ mọi transaction để chunk không cần trạng thái bền
D. Tạo mới mọi primary key và xử lý lại toàn bộ file
Đáp án đúng: B

Câu 40. Để cấu hình kết nối metadata database ở production, nguyên tắc nào phù hợp?
A. Ghi mật khẩu database trực tiếp vào đối số CLI mỗi job
B. Credential ít quyền và schema metadata nhất quán
C. Dùng database tạm theo từng Pod để dễ xóa lịch sử
D. Cấp quyền quản trị server cho mọi Task chỉ đọc metadata
Đáp án đúng: B

Câu 41. Khi nhiều Task đồng thời truy cập bảng metadata, yêu cầu nào quan trọng?
A. Mọi Task phải dùng chung TaskExecution ID để tránh trùng
B. TaskExplorer được phép xóa mọi record đang active khi lỗi
C. DB và transaction đáp ứng các Task chạy đồng thời
D. Tắt transaction cho bảng metadata để tăng số process
Đáp án đúng: C

Câu 42. Nếu Task thường xuyên thất bại vì thiếu tài nguyên, hướng vận hành nào phù hợp?
A. Chỉ tăng retry vô hạn để chắc chắn job được xử lý
B. Giới hạn concurrency, cấp CPU và memory phù hợp
C. Tắt ghi nhận TaskExecution để tránh chi phí database
D. Đặt time limit bằng không để task không bao giờ kết thúc
Đáp án đúng: B

Câu 43. Để theo dõi Task bị treo hoặc mất kết nối, tín hiệu nào hữu ích?
A. Số bean @Controller có trong ApplicationContext Task
B. Số ServiceInstance được trả bởi Eureka cho application
C. Thời điểm build JAR mà không đối chiếu thời gian chạy
D. TaskExecution thiếu end time quá thời lượng kỳ vọng
Đáp án đúng: D

Câu 44. Khi cần tương quan log của nhiều lần chạy cùng tên Task, nên gắn trường gì?
A. Execution ID và task name trong log ngữ cảnh tác vụ
B. Toàn bộ mật khẩu DB và giá trị Secret theo launch
C. Tên thread đầu tiên của JVM thay cho ID lần chạy
D. Tên Kubernetes node làm khóa duy nhất của mỗi Task
Đáp án đúng: A

Câu 45. Để kiểm thử một Task có lỗi giữa chừng, assertion nào nên ưu tiên?
A. Chỉ assert CommandLineRunner tạo bean và không chạy nghiệp vụ
B. Chỉ đo thời gian nạp ApplicationContext lúc startup
C. Kiểm tra metadata lỗi và ngăn side effect lặp
D. Chỉ xác minh có một dòng log INFO khi Task khởi chạy
Đáp án đúng: C

Câu 46. Khi kiểm thử phối hợp Task với Batch, cần xác minh điều gì?
A. Chỉ số bean TaskRepository bằng số step trong một job
B. Tất cả batch step chạy trên cùng một thread Java
C. Đối chiếu trạng thái TaskExecution và Batch JobExecution
D. CronJob luôn tạo một Pod ngay sau khi Task hoàn thành
Đáp án đúng: C

Câu 47. Khi một Task nhận tín hiệu dừng sớm, mục tiêu shutdown an toàn là gì?
A. Hủy các bảng metadata để tránh giữ execution lỗi
B. Dừng nhận việc mới và ghi checkpoint trước khi thoát
C. Chỉ đóng log exporter trước khi xử lý dữ liệu còn dở
D. Đổi exit code về 0 dù dữ liệu đang xử lý dang dở
Đáp án đúng: B

Câu 48. Khi chạy một Kubernetes CronJob của Task, cách nào giúp giữ cùng phiên bản ứng dụng giữa các lần chạy đã phê duyệt?
A. Dùng image latest để scheduler tự chọn bản vừa xuất hiện
B. Đổi tên TaskExecution ở mọi lần chạy để chọn code mới
C. Xóa image cache trên Node mỗi khi lịch Cron được kích hoạt
D. Ghim image tag bất biến hoặc digest theo đợt phát hành
Đáp án đúng: D
