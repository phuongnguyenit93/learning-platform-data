Câu 01. Theo quy ước mặc định Spring Modulith, các application module thường được xác định từ cấu trúc nào?
A. Các profile Spring Boot được bật khi ứng dụng chạy
B. Các bảng dữ liệu được tạo trong cơ sở dữ liệu chính
C. Các bean mang annotation `@RestController` trong app
D. Các package con trực tiếp của package gốc ứng dụng
Đáp án đúng: D

Câu 02. Để xây mô hình module từ class ứng dụng Spring Boot `ShopApplication`, API nào phù hợp?
A. `ApplicationModules.of(ShopApplication.class)` dựng mô hình module
B. `ApplicationContext.of(ShopApplication.class)` dựng mô hình module
C. `Documenter.of(ShopApplication.class)` dựng mô hình module
D. `ObservationRegistry.of(ShopApplication.class)` dựng mô hình module
Đáp án đúng: A

Câu 03. Trong module graph sinh từ source code, một cạnh `orders → inventory` thường có ý nghĩa gì?
A. Module orders có latency lớn hơn module inventory
B. Module orders đã xuất bản HTTP request tới inventory
C. Module orders phụ thuộc code vào inventory theo graph
D. Module orders đang dùng chung Kafka consumer group
Đáp án đúng: C

Câu 04. Để phát hiện dependency cycle giữa các application module, thao tác nào thích hợp?
A. Gọi `ApplicationModules.verify()` để kiểm tra cấu trúc
B. Gọi `ObservationRegistry.getCurrentObservation()` để kiểm tra
C. Gọi `MeterRegistry.clear()` để kiểm tra module cycle
D. Gọi `Documenter.writeModuleCanvases()` để kiểm tra chu kỳ
Đáp án đúng: A

Câu 05. Nếu module A tham chiếu vào class nằm trong package nội bộ của module B, quy tắc nào cần kiểm tra?
A. Độ dài transaction timeout của module A có đủ
B. Mức sampling của tracer có làm mất link giữa module
C. HTTP cache header của module B có cần đổi tên
D. Ranh giới API module B có bị module A truy cập sai
Đáp án đúng: D

Câu 06. Khi chỉ muốn module `orders` phụ thuộc vào API cho phép của `inventory`, cấu hình nào phù hợp?
A. `@Profile` giới hạn phụ thuộc code giữa các module
B. `@ApplicationModule(allowedDependencies=...)` giới hạn chiều phụ thuộc
C. `@Transactional` giới hạn phụ thuộc code giữa module
D. `@RestControllerAdvice` giới hạn phụ thuộc code module
Đáp án đúng: B

Câu 07. Để khai báo một named interface `spi` của một module, annotation nào phù hợp?
A. `@NamedInterface("spi")` công bố API từ package tương ứng
B. `@ConfigurationProperties("spi")` trên package API
C. `@ConditionalOnProperty("spi")` trên package API
D. `@EventListener("spi")` trên package được xuất bản
Đáp án đúng: A

Câu 08. Trong Spring Modulith, thành phần nào hỗ trợ sinh tài liệu kiến trúc từ mô hình module?
A. `ObservationRegistry` tạo module diagram từ traces
B. `ApplicationEventPublisher` chuyển module graph thành tài liệu
C. `KafkaTemplate` chuyển module graph thành sơ đồ thành phần
D. `Documenter` sinh tài liệu kiến trúc từ module model
Đáp án đúng: D

Câu 09. Muốn xuất sơ đồ tổng quan toàn bộ module ra PlantUML, gọi method nào của `Documenter`?
A. `writeModuleCanvases()` tạo sơ đồ tổng quan module
B. `writeModulesAsPlantUml()` tạo sơ đồ các module
C. `writeModuleMetadata()` tạo sơ đồ tổng quan module
D. `writeAggregatingDocument()` tạo sơ đồ module
Đáp án đúng: B

Câu 10. Muốn xuất sơ đồ PlantUML riêng cho từng module kèm dependency liên quan, dùng gì?
A. `writeModuleMetadata()` tạo các sơ đồ module riêng
B. `writeAggregatingDocument()` tạo các sơ đồ module riêng
C. `writeIndividualModulesAsPlantUml()` tạo sơ đồ cho từng module
D. `writeModulesAsPlantUml()` tạo các sơ đồ tách riêng
Đáp án đúng: C

Câu 11. Muốn sinh Module Canvas cho toàn bộ application modules, dùng method nào?
A. `writeModuleCanvases()` tạo các canvas theo module
B. `writeAggregatingDocument()` tạo các canvas theo module
C. `writeModulesAsPlantUml()` tạo các canvas theo module
D. `writeModuleMetadata()` tạo các canvas theo module
Đáp án đúng: A

Câu 12. Một Module Canvas hữu ích nhất vì tập hợp thông tin nào?
A. HTTP latency histogram, thread dump và JVM heap metrics
B. Kafka partition offsets, ISR members và replica lag
C. Spring components, events và cấu hình của module
D. Trace sampling rules, proxy hostname và TLS cipher suites
Đáp án đúng: C

Câu 13. Nếu cần sinh tổng quan, sơ đồ riêng từng module và các canvas trong một lần gọi, dùng gì?
A. `new Documenter(modules).writeModuleCanvases()` sinh bộ tài liệu
B. `new Documenter(modules).writeAggregatingDocument()` sinh bộ tài liệu
C. `new Documenter(modules).writeModuleMetadata()` sinh bộ tài liệu
D. `new Documenter(modules).writeDocumentation()` sinh bộ tài liệu
Đáp án đúng: D

Câu 14. Muốn tạo `all-docs.adoc` liên kết các diagram và canvas đã sinh, API nào đúng?
A. `writeModulesAsPlantUml()` ghép tài liệu hiện có
B. `writeAggregatingDocument()` ghép tài liệu hiện có
C. `writeIndividualModulesAsPlantUml()` ghép tài liệu hiện có
D. `writeModuleMetadata()` ghép tài liệu hiện có
Đáp án đúng: B

Câu 15. Theo cấu hình tài liệu mặc định, tài liệu Spring Modulith thường được ghi vào đâu?
A. Thư mục `src/main/resources/static` của ứng dụng
B. Thư mục `spring-modulith-docs` dưới build directory
C. Thư mục `.git/hooks` nằm trong repository
D. Thư mục `META-INF/services` trong source tree
Đáp án đúng: B

Câu 16. Để tạo metadata mô hình module phục vụ tích hợp runtime, method nào của `Documenter` phù hợp?
A. `writeIndividualModulesAsPlantUml()` tạo metadata runtime
B. `writeAggregatingDocument()` tạo metadata runtime module
C. `writeModuleMetadata()` tạo metadata từ module model
D. `writeModuleCanvases()` tạo metadata runtime module
Đáp án đúng: C

Câu 17. Để sơ đồ kiến trúc không lỗi thời sau refactor package, quy trình nào hợp lý?
A. Chỉ xem APM traces và không tạo docs từ source
B. Sinh lại docs từ module model trong build hoặc CI
C. Sửa diagram thủ công sau mỗi lần code được triển khai
D. Chỉ dùng ảnh architecture vẽ từ lần release đầu
Đáp án đúng: B

Câu 18. Nếu diagram module A trỏ sang B, lý do nào không thể suy ra chỉ từ cạnh đó?
A. Sự phụ thuộc tĩnh giữa package A và package B
B. Độ trễ của lời gọi giữa A và B trong production
C. Một quan hệ tham chiếu được phát hiện từ code
D. Hướng dependency được thể hiện trên sơ đồ module
Đáp án đúng: B

Câu 19. Khi lập tài liệu tập trung vào module `billing`, sơ đồ theo module có lợi ích nào?
A. Tự gắn correlation id cho trace của `billing`
B. Khôi phục các publication chưa hoàn tất của `billing`
C. Thay toàn bộ nghiệp vụ `billing` thành API contract
D. Làm rõ các dependency liên quan đến `billing`
Đáp án đúng: D

Câu 20. Muốn kiểm chứng sơ đồ thay đổi khi code có dependency mới không mong muốn, cách nào đáng tin cậy?
A. Chỉ đọc SQL slow query log rồi suy ra module graph
B. Sinh lại module graph rồi kiểm tra thay đổi và rule
C. Chỉ đo heap usage rồi suy ra dependency mới
D. Chỉ đo HTTP status rồi suy ra package dependency
Đáp án đúng: B

Câu 21. Spring Modulith cung cấp Actuator endpoint nào để xem cấu trúc application modules trong phiên bản hiện hành?
A. Actuator endpoint id `metrics` biểu diễn module structure
B. Actuator endpoint id `health` biểu diễn module structure
C. Actuator endpoint `modulith` trả cấu trúc các module
D. Actuator endpoint id `beans` biểu diễn module structure
Đáp án đúng: C

Câu 22. Muốn truy cập metadata module qua HTTP Actuator, điều kiện vận hành nào cần chú ý?
A. Tắt Spring Security cho cả application trong production
B. Kích hoạt trace sampling toàn phần ở các endpoint
C. Mở trực tiếp toàn bộ API domain events ra Internet
D. Expose endpoint phù hợp và thiết lập quyền truy cập
Đáp án đúng: D

Câu 23. Vì sao cần giới hạn truy cập vào Actuator endpoint mô tả module graph?
A. Endpoint tạo thêm SQL schema cho cả application
B. Endpoint xuất dependency thành external HTTP API
C. Endpoint có thể ghi lại code nguồn của từng module
D. Metadata cấu trúc có thể bộc lộ ranh giới nội bộ
Đáp án đúng: D

Câu 24. Trong việc phân tích coupling, Actuator module structure khác distributed tracing ở điểm nào?
A. Actuator chỉ hiển thị latency của HTTP requests đã chạy
B. Tracing chỉ hiển thị dependency tĩnh giữa Java packages
C. Actuator cho module graph, tracing cho lời gọi runtime
D. Hai công cụ đều chỉ hiển thị database relationship
Đáp án đúng: C

Câu 25. Để bổ sung quan sát tương tác module trong Spring Modulith, dependency nào phù hợp?
A. `spring-modulith-jdbc` tạo runtime spans cho module
B. Thêm `spring-modulith-observability` để quan sát tương tác
C. `spring-modulith-test` thay cho Micrometer tracing backend
D. `spring-modulith-docs` tạo runtime spans cho endpoint
Đáp án đúng: B

Câu 26. Micrometer API nào làm điểm đăng ký và quản lý các Observation của ứng dụng Spring?
A. `MessageGroupStore` quản lý các observation scope
B. `ApplicationModules` quản lý các observation scope
C. `ObservationRegistry` quản lý lifecycle observation
D. `Documenter` quản lý các observation scope
Đáp án đúng: C

Câu 27. Module-boundary observations hữu ích nhất để phát hiện điều gì trong runtime?
A. Các dependency không được compile trong một source package
B. Các field DTO bị thiếu annotation Jackson ở serialization
C. Các lời gọi qua module boundary có thời gian xử lý cao
D. Các Java source files chưa được formatter chuẩn hóa
Đáp án đúng: C

Câu 28. Với dữ liệu latency từng module, phát biểu nào phân biệt metric và trace đúng?
A. Metric tổng hợp latency, trace mô tả một lần gọi
B. Trace chỉ lưu các tổng histogram của mỗi module
C. Metric dùng để xác định package có dependency cycle
D. Metric chứa parent span của mỗi request để debug
Đáp án đúng: A

Câu 29. Trong distributed tracing, các span thuộc cùng một request thường được liên kết qua gì?
A. Cùng `traceId` cho phép đối chiếu các bước xử lý
B. Cùng `threadName` cho phép đối chiếu các bước xử lý
C. Cùng `beanName` cho phép đối chiếu các bước xử lý
D. Cùng `packageName` cho phép đối chiếu các bước xử lý
Đáp án đúng: A

Câu 30. Nếu module `orders` gọi `payments` đồng bộ, parent/child spans giúp quan sát gì?
A. Quan hệ phụ thuộc tĩnh được lưu trong Java compiler
B. Quan hệ cha-con và thời gian của từng đoạn xử lý
C. Danh sách các API bị từ chối bởi Spring Security
D. Dữ liệu payload đầy đủ của mỗi business event
Đáp án đúng: B

Câu 31. Khi sự kiện được phát qua ApplicationEventPublisher và xử lý ở module khác, dạng đo lường nào hữu ích?
A. Đo số lần, thời lượng và lỗi xử lý ở event listener
B. Chỉ đếm số file PlantUML để suy ra listener latency
C. Đo HTTP cache hit rate để suy ra số lần event xử lý
D. Dùng số lượng bean definitions để thay cho error rate
Đáp án đúng: A

Câu 32. Một listener xử lý sự kiện bất đồng bộ; để span của listener liên kết với trace gọi ban đầu, cần gì?
A. Dùng @Transactional để thay cho việc truyền trace context
B. Đổi tên bean listener cho trùng tên bean publisher
C. Chỉ thêm header Content-Type lên payload domain event
D. Truyền trace context sang executor khi nhận event
Đáp án đúng: D

Câu 33. Vì sao chỉ dựa vào MDC ThreadLocal thường mất trace correlation khi handler chạy thread khác?
A. Một trace chỉ được tạo trong một Java thread
B. MDC ThreadLocal không tự truyền sang worker thread
C. Spring Modulith loại MDC của từng module khi build jar
D. Actuator không cho phép ghi MDC từ application events
Đáp án đúng: B

Câu 34. Với Spring TaskExecutor, cấu hình nào thường hỗ trợ lan truyền observation context sang task khác?
A. `SimpleAsyncTaskExecutor` chia sẻ ThreadLocal giữa các thread
B. `ErrorHandler` chuyển MDC sang parent thread khi có lỗi
C. `TaskScheduler` thay thế traceId bằng một hằng số
D. `ContextPropagatingTaskDecorator` truyền context qua task
Đáp án đúng: D

Câu 35. Để capture và restore ThreadLocal context trong đoạn code chuyển thread thủ công, công cụ nào phù hợp?
A. Micrometer `ContextSnapshot` chụp và restore context
B. Spring `BeanFactory` phục hồi tracing context cho mỗi task
C. Spring `Documenter` giúp chụp và khôi phục context
D. Actuator `ApplicationModulesEndpoint` giúp restore context
Đáp án đúng: A

Câu 36. Trong pipeline Reactor, nơi nào thích hợp để mang ngữ cảnh tracing qua các operator async?
A. Biến static mutable được nhiều request cập nhật liên tục
B. MDC của thread tạo Mono mà không có cầu nối context
C. Reactor Context và cơ chế context propagation phù hợp
D. Cookie trình duyệt được chia sẻ giữa các scheduler Reactor
Đáp án đúng: C

Câu 37. Khi xuất Micrometer metrics theo module, vì sao không nên dùng `orderId` làm label?
A. Label `orderId` làm thay đổi mã HTTP mặc định
B. Label `orderId` buộc Kafka consumer thực hiện rebalance
C. Giá trị có cardinality cao tạo thêm Spring components
D. Giá trị có cardinality cao làm tăng số time series
Đáp án đúng: D

Câu 38. Khi một module listener lỗi, thiết kế observability nào giúp tìm nguyên nhân nhanh hơn?
A. Gắn exception vào observation và log kèm trace id
B. Tắt metrics để số span của listener bớt thay đổi
C. Chỉ tính số dòng source code để khoanh vùng lỗi
D. Chỉ cập nhật diagram khi service phát sinh exception
Đáp án đúng: A

Câu 39. Một event publication registry lưu sự kiện chưa xử lý; vai trò nào khác với distributed tracing?
A. Registry lưu parent-child spans của các cuộc gọi HTTP
B. Registry tạo C4 diagram dựa vào throughput module
C. Registry lưu publication chưa hoàn tất để retry xử lý
D. Registry thay tracing backend và collector trong runtime
Đáp án đúng: C

Câu 40. Khi trace cho thấy `orders` gọi `inventory` bất thường nhưng static module graph chưa đủ để giải thích độ trễ, nên làm gì?
A. Đối chiếu module graph với runtime spans và metrics
B. Chỉ xóa module canvas và sinh lại diagram mặc định
C. Chỉ thay tên package của `inventory` để giảm latency
D. Chỉ tăng sampling nhưng không kiểm module dependency
Đáp án đúng: A
