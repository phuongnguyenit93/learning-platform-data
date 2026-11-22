# Giao dịch kiểm thử không tự bao phủ yêu cầu HTTP ở luồng máy chủ

Một test Spring có thể được đánh dấu `@Transactional` và được rollback sau khi chạy. Điều này rất tiện khi kiểm thử repository, service hoặc controller bằng `MockMvc`. Tuy nhiên, nếu test gửi HTTP request qua một server đang chạy thật, giao dịch do Spring Test mở cho test method thường **không bao phủ giao dịch được xử lý ở luồng máy chủ**.

Sự khác biệt nằm ở ranh giới thực thi. Giao dịch kiểm thử của Spring gắn với thread thực thi test. Khi dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và gửi request qua HTTP tới embedded server, server xử lý request trong thread khác. Service ở phía server có thể mở và commit transaction riêng. Khi test method kết thúc, Spring rollback transaction của test thread; thao tác đã commit ở server thread vẫn còn trong database.

Vì vậy, cần phân biệt rõ kiểm thử request trong cùng tiến trình/thread với kiểm thử qua HTTP thật. Hãy chọn chiến lược transaction và cleanup theo cách request được thực thi, thay vì giả định mọi thay đổi phát sinh từ một test đều được rollback cùng transaction của test method.

## 1. Test-managed transaction là gì?

Spring TestContext Framework có thể quản lý transaction cho test method khi test được đánh dấu `@Transactional` và có `PlatformTransactionManager` phù hợp. `TransactionalTestExecutionListener` bắt đầu transaction trước khi test method chạy và kết thúc nó theo chính sách rollback/commit.

Ví dụ:

```java
@SpringBootTest
@Transactional
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void savesOrder() {
        Order order = repository.save(new Order("customer-42"));

        assertTrue(repository.findById(order.getId()).isPresent());
    }
}
```

Theo mặc định, test-managed transaction được rollback sau method. Vì thao tác repository tham gia transaction đó, dữ liệu test tạo ra không được commit xuống database.

`@Rollback` có thể làm rõ hành vi:

```java
@Test
@Rollback(true)
void createsTemporaryOrder() {
    // Transaction của test được rollback sau method.
}
```

Hoặc có thể yêu cầu commit bằng `@Commit` hay `@Rollback(false)`. Các annotation này điều khiển transaction test-managed. Chúng không biến transaction của một request HTTP ở thread khác thành transaction con của test.

## 2. Transaction của test gắn với thread thực thi

Với các transaction manager imperative phổ biến của Spring, transaction resources và trạng thái transaction được gắn với thread hiện tại. Khi một method service có `@Transactional(propagation = REQUIRED)` được gọi trên cùng thread, nó thường tham gia transaction đang hoạt động.

Nếu một lời gọi diễn ra trên thread khác, thread đó không tự động thừa hưởng transaction của test thread. Nó sẽ dùng transaction riêng nếu có cấu hình transaction tương ứng, hoặc thực thi theo semantics của repository/connection mà nó sử dụng.

```text
Test thread
    |
    +-- Spring Test mở transaction T1
    |
    +-- gọi một method đồng bộ trên cùng thread
    |       |
    |       +-- service REQUIRED có thể tham gia T1
    |
    +-- test kết thúc -> rollback T1

Server thread
    |
    +-- nhận HTTP request
    |
    +-- service mở transaction T2
    |
    +-- ghi dữ liệu và commit T2
    |
    +-- response trả về client

Rollback T1 không rollback T2.
```

Đây là lý do cốt lõi khiến `@Transactional` trên test method không tự dọn dữ liệu do một HTTP request thật tạo ra.

## 3. `MockMvc` và HTTP request tới server thật khác nhau

Hai cách test endpoint có thể nhìn giống nhau ở mức API nhưng khác về cách request được thực thi.

| Cách kiểm thử | Cách request được xử lý | Transaction test-managed có thể bao phủ? |
| --- | --- | --- |
| Gọi service/repository trực tiếp trong test | Trên thread test | Có, nếu lời gọi tham gia transaction hiện tại |
| `MockMvc` với Spring MVC đồng bộ | Servlet pipeline được thực thi trong lời gọi test, thường trên thread test | Thường có, nếu service dùng propagation tham gia transaction hiện tại |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` và `TestRestTemplate` | Request đi qua socket tới embedded server, server xử lý trên thread riêng | Không; server dùng transaction riêng |
| `@SpringBootTest(webEnvironment = DEFINED_PORT)` và HTTP client | Request tới server đang chạy trên thread riêng | Không; server dùng transaction riêng |
| Request bất đồng bộ hoặc công việc chuyển sang executor | Phần công việc chạy trên thread/task khác | Không tự động tham gia transaction của test thread |

### `MockMvc`: request đồng bộ trong cùng thread

Với Spring MVC Test, `MockMvc.perform(...)` gọi pipeline MVC trong tiến trình test mà không cần mở socket tới một server thật. Trong trường hợp đồng bộ thông thường, request được xử lý trên thread gọi `perform()`. Nếu test-managed transaction đang hoạt động trên thread đó, các thao tác database của service với propagation `REQUIRED` có thể tham gia cùng transaction.

Ví dụ:

```java
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class OrderMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    OrderRepository orders;

    @Test
    void createsOrderThroughMvcPipeline() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerId":"customer-42", "items":[{"sku":"BOOK-1","quantity":1}]}
                    """))
            .andExpect(status().isCreated());

        assertTrue(orders.existsByCustomerId("customer-42"));
    }
}
```

Trong tình huống đồng bộ, transaction test thường bao phủ thao tác persistence và rollback sau test. Test vẫn chạy qua mapping, filter và controller của Spring MVC, nhưng không kiểm tra TCP, port binding hoặc toàn bộ hành vi của một server đang nhận request thật.

Đừng coi đây là bảo đảm cho mọi request `MockMvc`. Nếu controller bắt đầu async processing, gọi `@Async`, tự tạo thread hoặc dùng transaction propagation độc lập, phần công việc đó có thể không tham gia transaction test. Khi dùng `MockMvc` async, hãy xác nhận transaction và thời điểm hoàn tất của phần xử lý nền.

## 4. `RANDOM_PORT`: test transaction và server transaction tách biệt

`@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` khởi chạy web server trên một cổng ngẫu nhiên. Test dùng HTTP client như `TestRestTemplate`, `RestClient`, `WebClient` hoặc `WebTestClient` cấu hình để gọi server qua mạng.

Ví dụ:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class OrderHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    OrderRepository orders;

    @Test
    void createsOrderThroughRealHttpServer() {
        ResponseEntity<OrderResponse> response = http.postForEntity(
            "/orders",
            new CreateOrderRequest("customer-42"),
            OrderResponse.class
        );

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertTrue(orders.existsById(response.getBody().id()));
    }
}
```

Trong ví dụ, annotation `@Transactional` mở transaction cho test method. Nhưng request được xử lý ở thread của embedded server. Nếu `OrderService` mở transaction và commit khi xử lý request, dữ liệu được commit trong transaction server-side. Rollback cuối test chỉ hoàn tác transaction của test thread, không hoàn tác transaction server-side.

Do đó, ví dụ trên có thể để lại order trong database sau khi test kết thúc, dù class có `@Transactional`. Đây là một khác biệt quan trọng giữa `MockMvc` đồng bộ và HTTP request tới server thật.

## 5. `@Rollback` và `@Commit` không điều khiển transaction phía server

Các annotation sau điều khiển transaction do Spring Test quản lý:

```java
@Transactional
@Rollback
@Test
void testRequest() {
    // ...
}
```

Hoặc:

```java
@Transactional
@Commit
@Test
void testRequest() {
    // ...
}
```

Với test gọi server qua HTTP thật:

- `@Rollback` rollback transaction của test thread nếu có.
- `@Commit` commit transaction của test thread nếu có.
- `@Rollback(false)` cũng yêu cầu transaction test commit.
- Không annotation nào tự động gắn transaction của test với request đang được xử lý trên server thread.

Nếu request server đã commit, `@Rollback` trên test không thể hoàn tác dữ liệu đó. Nếu server transaction thất bại và rollback, `@Commit` trên test cũng không thể làm transaction server commit trở lại.

Không thêm `@Transactional` vào test HTTP thật với mục đích duy nhất là “tự động rollback mọi dữ liệu”. Nó tạo cảm giác an toàn sai và đôi khi còn giữ một connection không cần thiết trong lúc server cần connection khác.

## 6. Vì sao server có thể commit trước khi HTTP response trả về?

Trong một request Spring MVC đồng bộ, service có thể chạy trong transaction:

```java
@Service
class OrderService {

    @Transactional
    public OrderId create(CreateOrderCommand command) {
        Order order = Order.create(command);
        repository.save(order);
        return order.getId();
    }
}
```

Khi method transactional kết thúc bình thường, transaction interceptor có thể commit trước khi luồng xử lý request tiếp tục hoàn tất response. Vì vậy, khi HTTP client nhận response thành công, dữ liệu server-side thường đã được commit.

Điều này phụ thuộc transaction boundary thực tế. Nếu controller trả về kết quả bất đồng bộ, đẩy công việc sang executor hoặc chỉ enqueue message để xử lý sau, response có thể được trả trước khi nghiệp vụ hoàn tất. Khi đó, test phải chờ trạng thái hoàn thành bằng điều kiện có timeout thay vì giả định response đồng nghĩa mọi side effect đã xong.

## 7. Cleanup dữ liệu đã commit bằng khóa riêng của test

Với HTTP test chạy qua server thật, cách phổ biến là tạo dữ liệu có định danh duy nhất rồi xóa đúng dữ liệu đó sau test.

Ví dụ dùng test run ID:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    OrderTestDataCleaner cleaner;

    private String testRunId;

    @BeforeEach
    void setUp() {
        testRunId = "http-test-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanUp() {
        cleaner.deleteByTestRunId(testRunId);
    }

    @Test
    void createsOrderThroughHttp() {
        CreateOrderRequest request = new CreateOrderRequest(
            "customer-42",
            testRunId
        );

        ResponseEntity<OrderResponse> response = http.postForEntity(
            "/orders", request, OrderResponse.class
        );

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
    }
}
```

Service cleanup là một Spring bean riêng:

```java
@Service
class OrderTestDataCleaner {

    private final OrderItemRepository items;
    private final OrderRepository orders;

    OrderTestDataCleaner(
            OrderItemRepository items,
            OrderRepository orders) {
        this.items = items;
        this.orders = orders;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void deleteByTestRunId(String testRunId) {
        items.deleteByTestRunId(testRunId);
        orders.deleteByTestRunId(testRunId);
    }
}
```

`REQUIRES_NEW` bảo đảm cleaner chạy trong transaction riêng khi có transaction khác đang hoạt động trên thread gọi. Nếu test class không có test-managed transaction, một transaction `REQUIRED` thông thường cũng có thể đủ; `REQUIRES_NEW` hữu ích khi muốn cleanup được commit độc lập với transaction bao ngoài.

Cleaner phải được gọi qua Spring bean proxy để propagation được áp dụng. Đặt method `@Transactional` trên chính test class hoặc gọi self-invocation trong cùng bean không tạo ra ranh giới proxy tương đương. Trong ví dụ, test inject `OrderTestDataCleaner` và gọi method public trên bean được Spring quản lý.

## 8. Vì sao cần ID riêng thay vì xóa toàn bộ bảng?

Test HTTP có thể chạy song song với test khác hoặc với một worker CI khác. Nếu cleanup dùng lệnh xóa toàn bộ bảng, nó có thể xóa dữ liệu của một test đang chạy.

Không nên dùng cleanup rộng như:

```sql
DELETE FROM orders;
TRUNCATE TABLE orders CASCADE;
```

trên database được chia sẻ giữa các test.

Thay vào đó, hãy:

- Tạo UUID hoặc test run ID riêng cho mỗi test method.
- Ghi ID đó vào request hoặc metadata của dữ liệu tạo ra.
- Lưu liên kết từ các bản ghi con để có thể cleanup theo cùng ID.
- Xóa đúng bản ghi do test hiện tại tạo.
- Dùng thao tác cleanup idempotent để gọi nhiều lần vẫn an toàn.

Nếu không thể đưa test run ID vào domain model, có thể dùng một trường metadata, correlation ID, tenant test riêng hoặc schema riêng. Điều quan trọng là test có cách xác định chính xác dữ liệu thuộc về nó.

## 9. Cleanup bằng `@Sql` và transaction mode

`@Sql` có thể chạy script sau test method để xóa dữ liệu. Với HTTP test thật, cần lưu ý script cleanup phải thực sự commit; nếu nó tham gia một test-managed transaction sẽ rollback, thao tác xóa có thể không được lưu.

Ví dụ:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Sql(
    scripts = "/sql/cleanup-http-test-data.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED)
)
class OrderHttpIntegrationTest {
    // ...
}
```

`ISOLATED` yêu cầu script chạy trong transaction riêng và commit độc lập. Hãy dùng điều kiện này khi script cần xóa dữ liệu server đã commit và cần bảo đảm cleanup không bị rollback cùng transaction khác.

Script vẫn cần xóa theo ID riêng của test. Nếu script dùng một ID cố định trong khi nhiều test chạy song song, nó có thể xóa nhầm dữ liệu của test khác. Với ID động, có thể dùng cơ chế tạo script/parameter phù hợp hoặc dùng một cleanup bean để truyền tham số an toàn.

## 10. Dùng database hoặc schema riêng cho HTTP test

Khi test có nhiều bảng, nhiều luồng request và cần chạy song song, database/schema riêng có thể tạo isolation tốt hơn cleanup từng bản ghi.

Các lựa chọn gồm:

| Cách tổ chức | Lợi ích | Chi phí/cân nhắc |
| --- | --- | --- |
| Transaction rollback | Nhanh cho thao tác cùng transaction | Không bao phủ server thread hoặc side effect ngoài transaction |
| Cleanup theo test run ID | Dùng được với database chung | Cần quản lý ID và thứ tự xóa |
| `@Sql` cleanup | Script rõ ràng, dễ tái sử dụng | Cần quản lý transaction mode và ID test |
| Schema riêng | Tách dữ liệu giữa suite/worker | Cần tạo schema và chạy migration |
| Database/container riêng | Isolation cao, gần production | Khởi tạo tốn tài nguyên và thời gian |

Testcontainers giúp tạo database dùng trong test, nhưng nếu nhiều test cùng ghi vào một container và một schema thì dữ liệu vẫn được chia sẻ. Container không tự làm cho mỗi test có transaction riêng hoặc tự rollback các request server-side.

## 11. Không dùng `@DirtiesContext` để rollback request HTTP

`@DirtiesContext` đánh dấu `ApplicationContext` cần loại khỏi context cache. Nó không xóa các bản ghi database đã commit, không xóa message trong broker, không hoàn tác HTTP request và không khôi phục trạng thái dịch vụ bên ngoài.

Ví dụ, request tạo order đã commit vào PostgreSQL. Sau test, Spring đóng context vì `@DirtiesContext`; database vẫn chứa order. Context mới tạo datasource mới nhưng đọc lại cùng database, nên order cũ vẫn còn.

Hãy chỉ dùng `@DirtiesContext` khi test làm thay đổi chính context hoặc bean singleton theo cách không thể khôi phục. Dữ liệu nghiệp vụ cần được dọn bằng transaction, repository, SQL script hoặc tài nguyên test riêng.

## 12. Async request và công việc chạy nền

Một request có thể trả về `202 Accepted` hoặc một response khác trước khi tác vụ nghiệp vụ hoàn tất. Ví dụ:

```java
@PostMapping("/reports")
ResponseEntity<Void> createReport(@RequestBody ReportRequest request) {
    reportService.schedule(request);
    return ResponseEntity.accepted().build();
}
```

Nếu `schedule()` gửi công việc sang `@Async`, executor hoặc message broker, transaction và thời điểm cleanup càng tách biệt khỏi test thread. Test không nên gọi cleanup ngay sau khi nhận `202` nếu worker vẫn có thể ghi dữ liệu sau đó.

Hãy chờ điều kiện nghiệp vụ hoàn tất với timeout:

```java
await()
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() ->
        assertTrue(reportRepository.existsByTestRunId(testRunId))
    );
```

Sau khi xác nhận công việc đã hoàn tất, test mới cleanup dữ liệu. Dùng Awaitility hoặc cơ chế đồng bộ tương đương; tránh `Thread.sleep()` cố định vì thời gian xử lý phụ thuộc tải máy và trạng thái hạ tầng.

Nếu cần cleanup cả khi test timeout hoặc assertion thất bại, hãy giữ test run ID ngay khi gửi request và đặt cleanup trong `@AfterEach`. Với tác vụ có thể chạy lâu hơn test, cần thêm cơ chế hủy hoặc xác nhận worker đã dừng trước khi xóa fixture.

## 13. `REQUIRES_NEW` và các transaction độc lập

Ngay cả khi dùng `MockMvc` cùng thread test, transaction rollback cũng không bao phủ mọi thao tác. Một service có thể khai báo:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAuditEvent(AuditEvent event) {
    auditRepository.save(event);
}
```

`REQUIRES_NEW` tạm ngưng transaction hiện tại, mở transaction mới và có thể commit độc lập. Khi transaction ngoài của test rollback, audit record đã commit trong transaction độc lập vẫn còn.

Các trường hợp khác có thể vượt ra ngoài transaction test:

- `@Transactional(propagation = NOT_SUPPORTED)` chạy phần method không có transaction hiện tại.
- Code chạy trong `@Async` hoặc executor riêng.
- Transaction bắt đầu qua một datasource hoặc transaction manager khác.
- Side effect được gửi tới hệ thống ngoài.
- Một service tự mở connection hoặc transaction không tham gia transaction manager của test.

Khi một test để lại dữ liệu dù dùng `@Transactional`, hãy kiểm tra propagation, thread, datasource và transaction manager trước khi kết luận Spring Test không rollback đúng.

## 14. Nguy cơ cạn connection pool khi test giữ transaction

Một HTTP test thật có thể mở transaction ở test thread rồi gửi request tới server. Nếu test transaction giữ một connection trong pool trong khi server thread cần connection khác, pool nhỏ có thể bị cạn.

Tình huống có thể xảy ra:

1. Test thread bắt đầu transaction và giữ connection.
2. Test gửi request HTTP tới server.
3. Server thread xử lý request và cần connection để ghi database.
4. Pool không còn connection khả dụng, server phải chờ.
5. Test thread chờ HTTP response; server thread chờ connection.

Với pool chỉ có một connection, tình huống này có thể gây timeout hoặc deadlock ở mức ứng dụng. Tăng pool size có thể che triệu chứng nhưng không giải quyết mục đích rollback sai lầm. Nếu test gọi server thật, thường nên tránh mở một test-managed transaction không cần thiết trên client thread.

## 15. Cách xác minh dữ liệu sau HTTP request

Sau khi server trả response, test có thể đọc dữ liệu bằng repository. Nhưng nếu test method đang giữ một transaction riêng, khả năng nhìn thấy commit của server còn phụ thuộc isolation level và snapshot của database.

Với isolation `READ COMMITTED`, một truy vấn mới thường có thể thấy transaction server đã commit trước đó. Với isolation như `REPEATABLE READ`, transaction test có thể tiếp tục nhìn snapshot cũ. Ngoài ra, persistence context có thể giữ entity cũ trong first-level cache.

Để xác nhận trạng thái đã commit:

- Tránh mở test transaction nếu không cần.
- Đọc qua một transaction mới sau khi request hoàn tất.
- Nếu cần, dùng `EntityManager.clear()` để tránh đọc entity còn được quản lý trong persistence context.
- Dùng repository/transaction template với ranh giới rõ ràng.
- Chờ tác vụ nền hoàn tất nếu endpoint trả response trước khi ghi dữ liệu.

Không dùng một assertion trên object đang nằm trong persistence context làm bằng chứng duy nhất rằng request server đã commit dữ liệu xuống database.

## 16. Một chiến lược test cho từng loại mục tiêu

| Mục tiêu | Cách kiểm thử phù hợp | Chiến lược dữ liệu |
| --- | --- | --- |
| Quy tắc service | Gọi service trực tiếp với mock/fake dependency | Transaction test rollback nếu cần database thật |
| MVC mapping, validation, exception handler | `MockMvc` với test transaction khi xử lý đồng bộ | Rollback thường phù hợp nếu mọi ghi dữ liệu tham gia transaction test |
| Giao tiếp HTTP qua socket, port binding, server thật | `RANDOM_PORT` hoặc `DEFINED_PORT` với HTTP client | Không dựa vào rollback test thread; cleanup dữ liệu đã commit |
| Async endpoint hoặc background job | HTTP test cộng chờ trạng thái hoàn tất | Cleanup sau khi worker kết thúc, dùng ID riêng |
| Transaction propagation/commit thực tế | Integration test với ranh giới transaction rõ ràng | Đọc lại từ transaction mới và cleanup độc lập |
| Contract với dịch vụ ngoài | Mock server hoặc sandbox | Dùng tài nguyên/ID riêng và API cleanup nếu có |

Không cần dùng HTTP server thật cho mọi test controller. Nếu mục tiêu chỉ là mapping và response, `MockMvc` thường nhanh hơn. Dành `RANDOM_PORT` cho những điều chỉ có thể xác nhận bằng server và HTTP client thực tế.

## 17. Ví dụ hoàn chỉnh: HTTP test không dùng test-managed transaction

Một cách tổ chức rõ ràng là để server tự quản lý transaction production, còn test quản lý dữ liệu qua cleaner riêng:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    OrderRepository orders;

    @Autowired
    OrderTestDataCleaner cleaner;

    private String testRunId;

    @BeforeEach
    void setUp() {
        testRunId = "http-" + UUID.randomUUID();
    }

    @AfterEach
    void tearDown() {
        cleaner.deleteByTestRunId(testRunId);
    }

    @Test
    void persistsOrderCreatedByHttpRequest() {
        ResponseEntity<OrderResponse> response = http.postForEntity(
            "/orders",
            new CreateOrderRequest("customer-42", testRunId),
            OrderResponse.class
        );

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertNotNull(response.getBody());

        assertTrue(orders.existsByTestRunId(testRunId));
    }
}
```

Ở đây không có `@Transactional` trên test class. Server xử lý request và commit theo transaction boundary của ứng dụng. Khi response đồng bộ trả về, test xác nhận dữ liệu rồi `@AfterEach` gọi cleaner để xóa đúng bản ghi thuộc test run.

Nếu request là bất đồng bộ, thay assertion tức thời bằng một điều kiện chờ có timeout. Cleaner phải chạy sau khi công việc đã hoàn tất hoặc đã được hủy an toàn.

## 18. Ví dụ dùng `MockMvc` khi muốn rollback

Nếu mục tiêu là kiểm tra MVC pipeline và muốn dữ liệu tự rollback, có thể dùng `MockMvc`:

```java
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class OrderMvcTransactionTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    OrderRepository orders;

    @Test
    void createsOrderWithinTestTransaction() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerId":"customer-42", "testRunId":"mvc-test-1"}
                    """))
            .andExpect(status().isCreated());

        assertTrue(orders.existsByTestRunId("mvc-test-1"));
    }
}
```

Với request đồng bộ, transaction của service có propagation `REQUIRED` có thể tham gia transaction test. Spring rollback khi test kết thúc. Nếu controller dùng async processing, service dùng `REQUIRES_NEW`, hoặc code chuyển sang thread khác, cần cleanup riêng như HTTP test thật.

## 19. Các lỗi thường gặp

- **Gắn `@Transactional` lên `RANDOM_PORT` test rồi kỳ vọng database rollback:** request được server thread xử lý và transaction của server độc lập.
- **Nhầm `MockMvc` với HTTP thật:** `MockMvc` không mở socket tới embedded server; semantics thread/transaction thường khác.
- **Cho rằng `@Rollback` rollback mọi transaction:** annotation chỉ điều khiển test-managed transaction.
- **Cho rằng `@Commit` làm server transaction commit:** server transaction đã có lifecycle riêng.
- **Dùng `@DirtiesContext` để xóa dữ liệu request:** context restart không xóa dữ liệu đã commit trong database hoặc dịch vụ ngoài.
- **Cleanup toàn bảng:** test chạy song song có thể xóa dữ liệu của nhau.
- **Cleanup trong cùng transaction sẽ rollback:** lệnh delete có thể không được commit nếu tham gia test transaction.
- **Bỏ qua `REQUIRES_NEW`:** transaction độc lập có thể commit dù transaction ngoài rollback.
- **Bỏ qua async:** response `202` không có nghĩa worker đã hoàn tất; cleanup quá sớm có thể bị worker ghi lại dữ liệu.
- **Giữ transaction test trong lúc chờ server:** có thể giữ connection và làm pool cạn.
- **Đọc từ persistence context cũ:** test có thể không thấy dữ liệu server vừa commit do cache hoặc isolation snapshot.

## 20. Quy trình chọn transaction và cleanup

Khi viết một test gửi HTTP request, hãy xác định theo thứ tự:

1. **Request được thực thi ở đâu?** `MockMvc` đồng bộ trong thread test, hay server thật qua `RANDOM_PORT`/`DEFINED_PORT`?
2. **Có chuyển thread hoặc async không?** Kiểm tra `@Async`, executor, async MVC/WebFlux và message consumer.
3. **Transaction nào đang hoạt động?** Xem `@Transactional`, propagation, transaction manager và datasource.
4. **Test cần rollback hay cần xác nhận commit?** Không thêm `@Transactional` nếu nó không phục vụ mục tiêu rõ ràng.
5. **Dữ liệu server-side được nhận diện thế nào?** Dùng UUID, test run ID, tenant hoặc schema riêng.
6. **Cleanup chạy trong transaction nào?** Dùng cleaner bean với transaction phù hợp hoặc SQL script `ISOLATED` khi cần commit độc lập.
7. **Có test chạy song song không?** Tránh ID cố định và lệnh xóa rộng.
8. **Request đã hoàn tất hoàn toàn chưa?** Với async, chờ trạng thái hoàn tất có timeout trước khi cleanup.
9. **Có thể kiểm tra dữ liệu từ transaction mới không?** Tránh dựa vào snapshot hoặc persistence context cũ.

Giao dịch kiểm thử là công cụ cô lập hiệu quả khi thao tác được thực hiện trong cùng transaction boundary. Với HTTP request tới server thật, transaction được mở trên server thread và có thể commit độc lập; rollback ở test thread không thể hoàn tác nó. Hãy dùng `MockMvc` khi cần kiểm tra MVC đồng bộ cùng test transaction, và dùng ID riêng, cleanup có commit hoặc database/schema riêng cho các test cần server HTTP thật. Hiểu đúng ranh giới này giúp test vừa phản ánh hành vi production vừa không để dữ liệu nghiệp vụ rò rỉ giữa các lần chạy.
