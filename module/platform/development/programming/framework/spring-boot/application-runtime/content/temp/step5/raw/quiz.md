Câu 01. Khi `SpringApplication.run(...)` khởi động thành công, kết quả trả về là gì?
A. Một `ApplicationArguments` chứa tham số dòng lệnh
B. Một `Environment` chưa gắn vào application context
C. Một `ConfigurableApplicationContext` đã được khởi tạo và refresh
D. Một `BeanDefinitionRegistry` chưa khởi tạo các bean
Đáp án đúng: C

Câu 02. Sự kiện nào được phát sau khi Environment chuẩn bị xong, trước khi tạo ApplicationContext?
A. `ApplicationPreparedEvent` thông báo bean definitions được nạp
B. `ApplicationEnvironmentPreparedEvent` báo môi trường đã sẵn
C. `ApplicationStartedEvent` thông báo context refresh thành công
D. `ApplicationReadyEvent` thông báo runner đã hoàn thành
Đáp án đúng: B

Câu 03. `ApplicationContextInitializedEvent` xuất hiện ở giai đoạn nào?
A. Sau khi tạo tất cả singleton bean và refresh context thành công
B. Sau initializer, trước khi nạp bean definitions vào context
C. Sau khi các runner chạy xong và trạng thái sẵn sàng được phát
D. Sau khi web server bắt đầu graceful shutdown của ứng dụng
Đáp án đúng: B

Câu 04. Trong Spring Boot, `ApplicationPreparedEvent` có ý nghĩa thời điểm nào?
A. Đã nạp bean definitions, context chưa refresh
B. Web server đã nhận được tín hiệu dừng ứng dụng
C. Environment chưa được tạo và chưa có property source
D. Context đã refresh và tất cả runner đã thực thi xong
Đáp án đúng: A

Câu 05. Muốn can thiệp vào ApplicationContext trước `refresh()`, cơ chế nào thích hợp?
A. `ApplicationRunner` chạy trước khi bean definitions được nạp
B. `CommandLineRunner` chạy trước khi ApplicationContext được tạo
C. `ApplicationContextInitializer` chạy trước khi context refresh
D. `ContextClosedEvent` chạy trước khi context bắt đầu refresh
Đáp án đúng: C

Câu 06. Thời điểm của `ApplicationStartedEvent` trong Spring Boot là khi nào?
A. Sau refresh của context và trước khi chạy các runner
B. Sau khi ContextClosedEvent hoàn tất việc dừng bean
C. Trước khi Environment và property sources được chuẩn bị
D. Sau khi các runner đã kết thúc và ứng dụng ready
Đáp án đúng: A

Câu 07. `ApplicationReadyEvent` báo hiệu thời điểm nào?
A. Các runner đã hoàn tất, ứng dụng chuyển sang ready
B. Environment đã chuẩn bị nhưng context chưa được tạo
C. Ứng dụng vừa nhận yêu cầu dừng từ nền tảng chạy
D. Bean definitions vừa được nạp, còn context chưa refresh
Đáp án đúng: A

Câu 08. Nếu `CommandLineRunner` ném exception chưa được xử lý, ứng dụng thường sẽ thế nào?
A. Ứng dụng báo ready vì các runner được chạy sau ready
B. Boot chuyển exception thành cảnh báo và tiếp tục startup
C. Startup lỗi, không tới bước phát `ApplicationReadyEvent`
D. Spring tự rollback các side effect của runner bằng JDBC
Đáp án đúng: C

Câu 09. `ApplicationRunner` nhận tham số dòng lệnh ở kiểu dữ liệu nào?
A. `ApplicationArguments` cho option lẫn non-option
B. `JobParameters` gồm các tham số identifying của Job
C. `String[]` kèm các chuỗi raw do JVM cung cấp
D. `Environment` chứa system property đã được parse
Đáp án đúng: A

Câu 10. `CommandLineRunner.run` nhận tham số ứng dụng theo dạng nào?
A. Mảng `String... args` được truyền từ lệnh chạy ứng dụng
B. `ConfigurableEnvironment` của context sau khi refresh
C. `ApplicationEvent` chứa thông tin thời gian bắt đầu
D. `ApplicationArguments` với phương thức `getOptionNames`
Đáp án đúng: A

Câu 11. Khi có nhiều runner muốn kiểm soát thứ tự chạy, nên cấu hình gì?
A. Đổi tên các runner theo thứ tự chữ cái trong package
B. Cấu hình `@Order` hoặc `Ordered` cho từng runner
C. Dựa vào thứ tự bean discovery khi component scan
D. Đặt các runner vào cùng một `@Async` executor pool
Đáp án đúng: B

Câu 12. `@PostConstruct` trên một singleton bean thường được gọi khi nào?
A. Trước khi bean được tạo, ngay khi Spring đọc classpath
B. Sau tiêm dependency, khi bean được khởi tạo bởi Spring
C. Sau khi nhận `ApplicationReadyEvent` và hoàn thành runner
D. Khi nhận tín hiệu `ContextClosedEvent` trước khi hủy bean
Đáp án đúng: B

Câu 13. `InitializingBean.afterPropertiesSet()` thường phục vụ mục đích gì?
A. Định nghĩa property sources trước khi tạo Environment
B. Đăng ký các runner sau khi ApplicationReadyEvent được phát
C. Chạy callback dừng bean khi ApplicationContext đóng
D. Xử lý khởi tạo sau khi các property của bean được gán
Đáp án đúng: D

Câu 14. `BeanFactoryPostProcessor` thường tác động vào phần nào của lifecycle?
A. Xử lý HTTP request sau khi server báo sẵn sàng
B. Gọi callback hủy bean sau khi executor được dừng
C. Điều khiển thread của các runner khi bắt đầu startup
D. Chỉnh metadata bean definition trước bước khởi tạo bean
Đáp án đúng: D

Câu 15. `ContextRefreshedEvent` cho biết điều gì về context đang chạy?
A. Các tài nguyên của bean vừa được hủy khi đóng context
B. ApplicationRunner và CommandLineRunner đã thực thi hết
C. ApplicationContext đã hoàn tất một lần refresh thành công
D. Tín hiệu readiness của Spring Boot đã chuyển sang ready
Đáp án đúng: C

Câu 16. Muốn khởi động tác vụ sau khi runner hoàn tất, nên lắng nghe sự kiện nào?
A. `ApplicationPreparedEvent` diễn ra trước khi context refresh
B. `ApplicationStartingEvent` diễn ra trước khi chuẩn bị Environment
C. `ApplicationStartedEvent` diễn ra trước giai đoạn runner
D. `ApplicationReadyEvent` diễn ra sau giai đoạn chạy runner
Đáp án đúng: D

Câu 17. Khi chưa có cấu hình async riêng, listener `@EventListener` thường chạy thế nào?
A. Chạy đồng bộ trên luồng phát sự kiện mặc định
B. Được gọi trên một executor mới tạo cho từng sự kiện
C. Được gọi trên scheduler của web server bất kể nguồn
D. Được gọi từ một process riêng của event multicaster
Đáp án đúng: A

Câu 18. Vì sao gọi một method `@Async` từ method khác trong cùng bean có thể không bất đồng bộ?
A. ApplicationContext tắt hết executor trước khi ready
B. Lời gọi trong bean không qua proxy hỗ trợ `@Async`
C. Method nội bộ được đổi thành `@Scheduled` khi khởi tạo
D. Spring Boot yêu cầu method `@Async` trả về `void`
Đáp án đúng: B

Câu 19. Muốn Spring xử lý annotation `@Async` theo cơ chế proxy, cần bật gì?
A. `@EnableConfigurationProperties` để nạp property bean
B. `@EnableTransactionManagement` để khởi tạo transaction
C. `@EnableScheduling` để đăng ký các tác vụ định kỳ
D. `@EnableAsync` để đăng ký khả năng xử lý lời gọi bất đồng bộ
Đáp án đúng: D

Câu 20. Muốn phương thức `@Scheduled` được lên lịch trong Spring, cần bật gì?
A. `@EnableScheduling` để kích hoạt cơ chế scheduled tasks
B. `@EnableAsync` để chuyển tác vụ thành lệnh định kỳ
C. `@EnableCaching` để lưu kết quả mỗi lần chạy
D. `@EnableBatchProcessing` để tạo scheduler cho request
Đáp án đúng: A

Câu 21. Trong startup, một `SmartLifecycle` bean có `isAutoStartup() == true` hỗ trợ gì?
A. Tự mở server socket, tách khỏi vòng đời context của Spring
B. Tự start khi refresh, sau đó được quản lý lúc shutdown
C. Tự chạy ApplicationRunner sau khi ApplicationReadyEvent phát
D. Tự sinh bean definition trước khi Environment được tạo
Đáp án đúng: B

Câu 22. Với các `SmartLifecycle` bean, thứ tự phase thường hoạt động thế nào?
A. Phase thấp start trước; phase cao được dừng trước
B. Phase giống nhau được xử lý bằng thread riêng cho mỗi bean
C. Phase là số lượng retry khi callback stop gặp lỗi
D. Phase cao start trước; phase thấp được dừng trước
Đáp án đúng: A

Câu 23. Trong `SmartLifecycle.stop(Runnable callback)`, khi nào nên gọi callback?
A. Ngay sau khi nhận lệnh stop dù tác vụ chưa thoát
B. Sau khi `ApplicationReadyEvent` được phát lần tiếp
C. Trước khi gọi `start()` để tránh giữ lifecycle lock
D. Sau khi dừng xong để Spring tiếp tục các phase
Đáp án đúng: D

Câu 24. `ApplicationAvailability` trong Spring Boot giúp quan sát trạng thái nào?
A. `EnvironmentState` và `BeanFactoryState` của context
B. `BatchStatus` và `ExitStatus` của Step hiện tại
C. `LivenessState` và `ReadinessState` của ứng dụng
D. `ServerState` và `DatabaseState` của JDBC pool
Đáp án đúng: C

Câu 25. Ý nghĩa của `ReadinessState.ACCEPTING_TRAFFIC` là gì?
A. ApplicationContext đã đóng và không nhận thêm request
B. Ứng dụng đang chạy rollback của một giao dịch JDBC
C. Ứng dụng đã sẵn sàng nhận lưu lượng phục vụ
D. JVM vẫn đang sống nhưng chưa đủ điều kiện phục vụ
Đáp án đúng: C

Câu 26. Khi cần tạm từ chối traffic dù tiến trình vẫn sống, cách nào phù hợp?
A. Phát `AvailabilityChangeEvent` cho `REFUSING_TRAFFIC`
B. Phát `ApplicationReadyEvent` một lần nữa từ controller
C. Phát `ContextRefreshedEvent` để từ chối HTTP connection
D. Đặt `LivenessState.BROKEN` cho tác vụ bảo trì ngắn
Đáp án đúng: A

Câu 27. Khi probes của Spring Boot Actuator được bật, endpoint nào thường biểu thị readiness?
A. `/actuator/metrics` thay thế readiness probe
B. `/actuator/health/liveness` phản ánh nhóm readiness
C. `/actuator/info` phản ánh lần readiness gần nhất
D. `/actuator/health/readiness` phản ánh nhóm readiness
Đáp án đúng: D

Câu 28. `ApplicationFailedEvent` được dùng để quan sát tình huống nào?
A. Exception khiến startup của SpringApplication thất bại
B. Một scheduled task ném exception khi ứng dụng đang ready
C. Một JDBC transaction rollback khi gọi API nghiệp vụ
D. Một HTTP request thất bại sau khi startup hoàn tất
Đáp án đúng: A

Câu 29. Muốn báo nguyên nhân lỗi khởi động kèm hướng sửa cụ thể, mở rộng điểm nào?
A. Viết `ApplicationRunner` để bắt exception của bean chưa tạo
B. Viết `FailureAnalyzer` cho loại exception cần chẩn đoán
C. Viết `CommandLineRunner` để thay đổi log JVM đã dừng
D. Viết `@PostConstruct` để bắt các bean chưa thể được tạo
Đáp án đúng: B

Câu 30. Khi bật chế độ `--debug` của Spring Boot để điều tra autoconfiguration, báo cáo gì hữu ích?
A. `ApplicationArguments` liệt kê các bean bị từ chối
B. `ConditionEvaluationReport` cho biết điều kiện autoconfig
C. `ThreadDump` ghi trạng thái thread khi autoconfiguration chạy
D. `HeapHistogram` phân loại bean không được khởi tạo
Đáp án đúng: B

Câu 31. Cấu hình `spring.main.lazy-initialization=true` có đánh đổi startup nào?
A. Đảm bảo bean lỗi được phát hiện trước khi HTTP server mở
B. Tắt cơ chế dependency injection của bean chưa được dùng
C. Buộc các bean singleton tạo trước khi context refresh
D. Giảm việc tạo bean ban đầu nhưng có thể làm lộ lỗi muộn
Đáp án đúng: D

Câu 32. Để thu thập các bước startup phục vụ phân tích, Spring Boot hỗ trợ gì?
A. Cấu hình `ApplicationRunner` để ghi heap dump từng bean
B. `BufferingApplicationStartup` thu thập các `StartupStep`
C. Cấu hình `ApplicationArguments` để thay thế bean factory
D. Cấu hình `CommandLineRunner` để đổi phase của lifecycle
Đáp án đúng: B

Câu 33. Ứng dụng có executor nền riêng ngoài Spring container; khi đóng context cần lưu ý gì?
A. Dựa vào cơ chế rollback JDBC để đóng các luồng background
B. Dừng executor và thu hồi tài nguyên khi đóng context
C. Để executor chạy tiếp vì JVM xử lý các task đang chờ
D. Đợi ApplicationReadyEvent được phát lại rồi hủy executor
Đáp án đúng: B

Câu 34. Cấu hình nào bật graceful shutdown của web server Spring Boot?
A. Đặt `management.endpoint.shutdown.enabled=true` cho web
B. Đặt `spring.application.admin.enabled=true` cho servlet
C. Đặt `server.shutdown=graceful` trong cấu hình ứng dụng
D. Đặt `spring.main.lazy-initialization=true` cho bean web
Đáp án đúng: C

Câu 35. Trong graceful shutdown của embedded web server, điều gì là mục tiêu chính?
A. Hủy ngay request đang chạy để giải phóng socket trước
B. Chuyển request dở dang thành ApplicationRunner mới
C. Yêu cầu client gửi lại request trước khi web server đóng
D. Ngừng nhận request mới, chờ request đang chạy xong
Đáp án đúng: D

Câu 36. `spring.lifecycle.timeout-per-shutdown-phase` điều chỉnh yếu tố nào?
A. Thời hạn chờ token của một HTTP request riêng lẻ
B. Thời hạn tạo ApplicationContext trước khi refresh
C. Giới hạn chờ cho mỗi phase khi dừng lifecycle
D. Thời hạn mỗi lời gọi ItemReader khi đóng Job
Đáp án đúng: C

Câu 37. `ContextClosedEvent` thường được phát ở thời điểm nào?
A. Khi ApplicationRunner bắt đầu thực thi sau refresh
B. Khi SpringApplication bắt đầu nạp Environment
C. Khi ApplicationContext phát tín hiệu bắt đầu đóng
D. Khi ApplicationContext chuẩn bị tạo bean definition
Đáp án đúng: C

Câu 38. Callback nào dùng để giải phóng tài nguyên khi bean được Spring hủy?
A. `@PostConstruct` trên phương thức setup của bean
B. `@Bean` trên phương thức tạo singleton ở startup
C. `@Order` trên phương thức xử lý ApplicationEvent
D. `@PreDestroy` trên phương thức cleanup của bean
Đáp án đúng: D

Câu 39. Một tác vụ background muốn hoàn tất có giới hạn khi context dừng; thiết kế nào phù hợp?
A. Phát ApplicationStartedEvent lại khi nhận tín hiệu dừng
B. Khởi tạo thread daemon rồi bỏ trạng thái lifecycle
C. Đặt tác vụ vào ApplicationRunner đang chạy vô hạn
D. Quản lý qua `SmartLifecycle` và báo xong bằng stop callback
Đáp án đúng: D

Câu 40. Muốn hệ điều hành nhận exit code theo kết quả Spring Boot, cách gọi nào phù hợp?
A. `context.refresh()` chuyển exit code của bean lỗi cho OS
B. `Environment.getProperty(...)` tự kết thúc tiến trình JVM
C. `System.exit(SpringApplication.exit(context))` chuyển mã thoát
D. `SpringApplication.run(context)` tự đặt exit code của JVM
Đáp án đúng: C
