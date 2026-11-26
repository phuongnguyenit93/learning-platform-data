Câu 01. Trong JUnit Jupiter, annotation nào kết nối test class với Spring TestContext Framework?
A. `@ContextConfiguration` thay thế extension Jupiter
B. `@ExtendWith(SpringExtension.class)` cho JUnit Jupiter
C. `@TestPropertySource` đăng ký extension Jupiter
D. `@RunWith(SpringRunner.class)` kích hoạt Jupiter
Đáp án đúng: B

Câu 02. `@SpringJUnitConfig(TestConfig.class)` kết hợp những cấu hình nào?
A. `@WebAppConfiguration` kết hợp với `@ActiveProfiles`
B. `@Sql` và `@TestPropertySource` cho test class
C. `SpringExtension` cùng với `@ContextConfiguration`
D. `@DirtiesContext` và `@Transactional` cho test
Đáp án đúng: C

Câu 03. Muốn tải `AppTestConfig` làm nguồn cấu hình context của integration test, dùng gì?
A. `@DirtiesContext(classes = AppTestConfig.class)`
B. `@ContextConfiguration(classes = AppTestConfig.class)`
C. `@TestPropertySource(classes = AppTestConfig.class)`
D. `@ActiveProfiles(classes = AppTestConfig.class)`
Đáp án đúng: B

Câu 04. Khi `SpringExtension` quản lý test, cách nhận bean `OrderService` từ context là gì?
A. `@Value` trên field để quét component của test
B. `@TestPropertySource` trên field để lấy bean
C. `@Mock` trên field để lấy Spring bean thực
D. Dùng `@Autowired` để Spring inject bean cho test
Đáp án đúng: D

Câu 05. Muốn chạy integration test với các bean `@Profile("test")`, dùng annotation nào?
A. `@ActiveProfiles("test")` bật profile test
B. `@TestPropertySource("test")` kích hoạt profile test
C. `@ContextHierarchy("test")` kích hoạt profile test
D. `@DirtiesContext("test")` kích hoạt profile test
Đáp án đúng: A

Câu 06. Muốn ghi đè property `feature.enabled` cho test bằng giá trị cố định, nên dùng gì?
A. `@DirtiesContext(properties = "feature.enabled=true")`
B. `@TestPropertySource(properties = "feature.enabled=true")`
C. `@ActiveProfiles(properties = "feature.enabled=true")`
D. `@Sql(properties = "feature.enabled=true")`
Đáp án đúng: B

Câu 07. Với URL database do Testcontainers cấp sau khi khởi chạy, cách cấp property động nào hợp lý?
A. Method static `@DynamicPropertySource` với `DynamicPropertyRegistry`
B. Method `@ActiveProfiles` nhận `DynamicPropertyRegistry`
C. Method `@BeforeTransaction` nhận `DynamicPropertyRegistry`
D. Method `@TestPropertySource` nhận `DynamicPropertyRegistry`
Đáp án đúng: A

Câu 08. Spring TestContext có thể dùng lại ApplicationContext giữa hai test class trong trường hợp nào?
A. Tên method test của hai class đều giống nhau
B. Hai class có cùng số lượng lời gọi tới repository
C. JUnit tái sử dụng cùng một instance test object
D. Hai test có khóa cấu hình context cache tương đương
Đáp án đúng: D

Câu 09. Khi test class thay đổi bean singleton khiến context không còn dùng được, annotation nào đánh dấu cần loại cache?
A. `@SqlConfig` dùng để loại context khỏi cache
B. `@DirtiesContext` loại context đã bẩn khỏi cache
C. `@ActiveProfiles` dùng để loại context khỏi cache
D. `@TestPropertySource` dùng để loại context khỏi cache
Đáp án đúng: B

Câu 10. Vì sao tránh gắn `@DirtiesContext` cho mọi test method khi context vẫn sạch?
A. MockMvc mất khả năng xác minh HTTP response
B. Tạo lại ApplicationContext làm test chạy chậm
C. Repository không nhận transaction do hết cache
D. TestContext bỏ qua profile đã được kích hoạt
Đáp án đúng: B

Câu 11. Muốn thêm hook trước/sau execution test vào Spring TestContext, extension point nào phù hợp?
A. Dùng `HandlerInterceptor` cho vòng đời test
B. Dùng `BeanFactoryPostProcessor` cho mỗi assertion
C. Dùng `ApplicationListener` bao mỗi JUnit test
D. Dùng `TestExecutionListener` nhận lifecycle callbacks
Đáp án đúng: D

Câu 12. Khi cần quan hệ context cha–con trong một test integration, annotation nào mô tả hierarchy?
A. `@ActiveProfiles` thiết lập các tầng ApplicationContext
B. `@ContextHierarchy` khai báo parent/child context
C. `@ContextConfiguration` tự suy ra parent test context
D. `@WebAppConfiguration` tạo các tầng parent context
Đáp án đúng: B

Câu 13. Muốn chạy `schema.sql` trước mỗi test method, annotation nào phù hợp?
A. `@TestPropertySource(scripts = "classpath:schema.sql")`
B. `@DirtiesContext(scripts = "classpath:schema.sql")`
C. `@Sql(scripts = "classpath:schema.sql")` để chạy script
D. `@Import(scripts = "classpath:schema.sql")` thực thi script
Đáp án đúng: C

Câu 14. Nếu dữ liệu SQL setup phải commit độc lập với rollback của transaction test, chọn cấu hình nào?
A. `@SqlConfig(transactionMode = DEFAULT)` tách transaction
B. `@Rollback(false)` trên script chạy riêng trong SQL tx
C. `@Commit` trên method làm SQL scripts commit độc lập
D. `@SqlConfig(transactionMode = ISOLATED)` tạo transaction riêng
Đáp án đúng: D

Câu 15. Với Spring TestContext hỗ trợ transaction, test method `@Transactional` mặc định kết thúc thế nào?
A. Transaction được lưu lại để test method tiếp theo dùng
B. Transaction do test quản lý được commit sau assertion
C. Test-managed transaction rollback khi test kết thúc
D. Transaction được đóng trước khi method test chạy
Đáp án đúng: C

Câu 16. Để transaction test được commit thay vì rollback mặc định, annotation nào phù hợp?
A. `@ActiveProfiles` trên method/class yêu cầu commit
B. `@WebAppConfiguration` trên method/class yêu cầu commit
C. `@Commit` yêu cầu commit transaction của test
D. `@DirtiesContext` trên method/class yêu cầu commit
Đáp án đúng: C

Câu 17. Đang trong transactional test, thao tác nào cho phép kết thúc transaction với commit theo chương trình?
A. `TestTransaction.flagForRollback(); TestTransaction.end();`
B. `TestTransaction.start(); TestTransaction.flagForRollback();`
C. `TestTransaction.isActive(); TestTransaction.start();`
D. `TestTransaction.flagForCommit(); TestTransaction.end();`
Đáp án đúng: D

Câu 18. Method mang `@BeforeTransaction` trong transactional integration test được gọi khi nào?
A. Trong transaction do `@Sql` thiết lập cho test
B. Trong transaction của `@BeforeEach` trước các assert
C. Sau khi transaction test đã commit hoặc rollback
D. `@BeforeTransaction` chạy trước transaction của test
Đáp án đúng: D

Câu 19. Với `@Transactional` test chạy qua SpringExtension, callback JUnit `@BeforeEach` thường ở đâu?
A. `@BeforeEach` chạy trong test-managed transaction
B. Chạy ngoài transaction như `@BeforeTransaction`
C. Được chạy trong transaction do listener tự commit
D. Nằm sau transaction test đã rollback xong
Đáp án đúng: A

Câu 20. Khi service mở transaction `REQUIRES_NEW` và commit trong transactional test, điều gì cần chú ý?
A. Commit `REQUIRES_NEW` không bị rollback của test hoàn tác
B. Rollback test sẽ hoàn tác cả transaction mới đã commit
C. `REQUIRES_NEW` tái sử dụng cùng transaction của test
D. Commit transaction mới chỉ xảy ra sau khi test teardown
Đáp án đúng: A

Câu 21. Muốn một test method không chạy trong test-managed transaction, cấu hình nào phù hợp?
A. `@Transactional(propagation = MANDATORY)` trên method
B. `@Transactional(propagation = REQUIRED)` trên method
C. `@Transactional(propagation = SUPPORTS)` trên method
D. `@Transactional(propagation = NOT_SUPPORTED)` cho test
Đáp án đúng: D

Câu 22. Vì sao Testcontainers dùng đúng engine DB production có giá trị trong integration test?
A. Kiểm SQL dialect và constraint trên engine DB thực
B. Kiểm controller bằng mock response mà không nạp schema
C. Thay entity mapping để không mở connection pool
D. Tách JDBC query khỏi DB nên không cần migrations
Đáp án đúng: A

Câu 23. Spring Framework 6.2+ hỗ trợ annotation nào thay một bean bằng Mockito mock trong test context?
A. `@MockitoBean` ghi đè bean bằng Mockito mock
B. `@MockitoSpyBean` bọc bean hiện hữu thành spy
C. `@TestBean` gắn bean factory theo cấu hình riêng
D. `@DirtiesContext` đánh dấu context cần được tạo lại
Đáp án đúng: A

Câu 24. Khi muốn theo dõi lời gọi nhưng vẫn chạy logic của bean thực, dùng annotation nào?
A. `@Autowired` inject bean thực vào field của test
B. `@MockitoSpyBean` dùng spy bọc bean thực
C. `@MockitoBean` thay bean hiện có bằng Mockito mock
D. `@TestBean` dùng factory method để thay bean gốc
Đáp án đúng: B

Câu 25. Trong Spring Framework 6.2+, `@TestBean` thường dùng theo cách nào?
A. Tạo Mockito spy bằng cách bọc bean gốc tại runtime
B. `@TestBean` dùng static factory method cung cấp bean
C. Tạo TestExecutionListener bằng constructor JUnit
D. Tạo dữ liệu JPA bằng script SQL trước test method
Đáp án đúng: B

Câu 26. Khi một test method làm context bẩn, muốn đóng context sau đúng method đó thì dùng gì?
A. `@DirtiesContext(classMode = AFTER_CLASS)` trên method
B. `@Sql(executionPhase = AFTER_TEST_METHOD)` trên method
C. `@DirtiesContext(methodMode = AFTER_METHOD)` trên method
D. `@Rollback(false)` trên method để context tự evict
Đáp án đúng: C

Câu 27. Muốn test một MVC controller bằng MockMvc mà không nạp ApplicationContext, tạo nó thế nào?
A. `MockRestServiceServer.bindTo(restTemplate).build()`
B. `MockMvcBuilders.webAppContextSetup(wac).build()`
C. `WebTestClient.bindToApplicationContext(ctx).build()`
D. `MockMvcBuilders.standaloneSetup(controller).build()`
Đáp án đúng: D

Câu 28. Muốn MockMvc sử dụng cấu hình MVC thật của WebApplicationContext, chọn setup nào?
A. `WebTestClient.bindToServer().build()`
B. `MockRestServiceServer.bindTo(restTemplate).build()`
C. `MockMvcBuilders.webAppContextSetup(wac).build()`
D. `MockMvcBuilders.standaloneSetup(controller).build()`
Đáp án đúng: C

Câu 29. Để kiểm HTTP 200 của request GET `/orders/42` bằng MockMvc, câu lệnh nào đúng?
A. `perform(get("/orders/42")).andExpect(status().isOk())`
B. `perform(get("/orders/42")).andExpect(status().isCreated())`
C. `perform(post("/orders/42")).andExpect(status().isOk())`
D. `perform(get("/orders/42")).andExpect(status().isNotFound())`
Đáp án đúng: A

Câu 30. Khi MockMvc nhận JSON body `{"status":"PAID"}`, matcher nào kiểm đúng thuộc tính?
A. `content().contentType("PAID")` kiểm giá trị JSON
B. `header().string("status", "PAID")` kiểm giá trị JSON
C. `jsonPath("$.status").value("PAID")` kiểm field JSON
D. `cookie().value("status", "PAID")` kiểm giá trị JSON
Đáp án đúng: C

Câu 31. Để MockMvc gửi JSON POST tới `/orders`, phần cấu hình request nào đúng?
A. `post("/orders").accept(APPLICATION_JSON).param("body", json)`
B. `post("/orders").header("body", json).accept(APPLICATION_JSON)`
C. `post("/orders").contentType(APPLICATION_JSON).content(json)`
D. `get("/orders").contentType(APPLICATION_JSON).content(json)`
Đáp án đúng: C

Câu 32. Một controller Spring MVC trả `Callable` và xử lý async, bước nào xác minh response sau khi tác vụ xong?
A. Gọi `standaloneSetup` lần nữa để chạy async controller
B. Chỉ assert `request().asyncStarted()` là đã có response
C. Gọi `webAppContextSetup` sau khi HTTP request kết thúc
D. Dùng `asyncDispatch(result)` kiểm kết quả MVC async
Đáp án đúng: D

Câu 33. Khi kiểm authorization trong MockMvc với Spring Security, cấu hình nào gắn security test filter?
A. `apply(springSecurity())` cho MockMvc builder
B. `apply(activeProfiles())` trên MockMvc builder
C. `apply(transactional())` trên MockMvc builder
D. `apply(contextCaching())` trên MockMvc builder
Đáp án đúng: A

Câu 34. Muốn test WebFlux controller qua WebTestClient mà không mở server HTTP thật, nên làm gì?
A. `MockMvcBuilders.webAppContextSetup(wac).build()`
B. `WebTestClient.bindToApplicationContext(context).build()`
C. `MockRestServiceServer.bindTo(restTemplate).build()`
D. `WebTestClient.bindToServer().baseUrl(url).build()`
Đáp án đúng: B

Câu 35. Muốn WebTestClient thực sự gọi endpoint HTTP đang chạy ở port ngẫu nhiên, chọn gì?
A. `WebTestClient.bindToApplicationContext(context).build()`
B. `MockMvcBuilders.standaloneSetup(controller).build()`
C. `MockRestServiceServer.bindTo(restTemplate).build()`
D. `WebTestClient.bindToServer().baseUrl(url).build()`
Đáp án đúng: D

Câu 36. Với HTTP 200 và JSON body `{"id":42}`, bước nào của WebTestClient kiểm cả status lẫn ID?
A. `expectStatus().isOk().expectCookie().valueEquals("id", "42")`
B. `expectStatus().isOk().expectBody().jsonPath("$.id").isEqualTo(42)`
C. `expectStatus().isCreated().expectBody().jsonPath("$.id").isEqualTo(42)`
D. `expectStatus().isOk().expectHeader().valueEquals("id", "42")`
Đáp án đúng: B

Câu 37. Muốn dùng cú pháp WebTestClient để kiểm Spring MVC trên MockMvc, công cụ nào phù hợp?
A. `MockRestServiceServer.bindTo(restTemplate).build()`
B. `MockMvcBuilders.standaloneSetup(controller).build()`
C. Dùng `MockMvcWebTestClient` kiểm Spring MVC
D. `WebTestClient.bindToServer().baseUrl(url).build()`
Đáp án đúng: C

Câu 38. Trong integration test của service dùng RestTemplate để gọi HTTP outbound, công cụ nào giả lập server đích?
A. `MockRestServiceServer` mock HTTP outbound response
B. `MockMvc` mock HTTP responses từ RestTemplate trực tiếp
C. `WebTestClient` mock RestTemplate request thông qua JUnit
D. `@Sql` mock RestTemplate response bằng DB scripts
Đáp án đúng: A

Câu 39. Để Spring TestContext tạo WebApplicationContext với MockServletContext, annotation nào phù hợp?
A. `@WebAppConfiguration` đánh dấu web test context
B. `@TestPropertySource` đánh dấu web application test context
C. `@SpringJUnitConfig` đánh dấu web application test context
D. `@ActiveProfiles` đánh dấu web application test context
Đáp án đúng: A

Câu 40. Nhiều test chạy song song cùng sửa shared singleton state, cách nào giảm flakiness tốt nhất?
A. Bật context caching để chia sẻ mutable test state
B. Tăng timeout chờ để các task đồng thời tự đồng bộ
C. Cô lập dữ liệu và reset shared state giữa các test
D. Dùng thêm @Order để chia thread chạy các JUnit test
Đáp án đúng: C
