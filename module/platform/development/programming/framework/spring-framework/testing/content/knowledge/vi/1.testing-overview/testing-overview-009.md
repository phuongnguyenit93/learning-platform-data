# Luồng học từ đối tượng Java đến HTTP và tài nguyên thật

Kiểm thử trong Spring có nhiều mức vì một ứng dụng đi qua nhiều ranh giới: đối tượng Java, các thành phần hợp tác với nhau, vùng chứa Spring, bộ xử lý HTTP và những tài nguyên bên ngoài như cơ sở dữ liệu hay message broker. Mỗi mức trả lời một nhóm câu hỏi khác nhau. Chọn đúng mức giúp bài kiểm thử đủ tin cậy mà vẫn dễ đọc, chạy nhanh và khoanh vùng lỗi tốt.

Bài học này đi theo một luồng tăng dần: bắt đầu với một đối tượng Java độc lập, đưa các collaborator vào, kiểm tra việc Spring lắp ghép bean, đi qua MVC hoặc WebFlux, gửi request HTTP, rồi kết nối tới tài nguyên thật trong môi trường kiểm thử.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt unit test, test thành phần, test theo lát cắt, integration test và end-to-end test.
- Chọn giữa JUnit thuần, Mockito, Spring TestContext, các test slice của Spring Boot và `@SpringBootTest`.
- Giải thích chính xác `MockMvc` kiểm tra điều gì và khi nào cần khởi động web server thật.
- Kiểm tra repository và cấu hình persistence với cơ sở dữ liệu kiểm thử.
- Kết nối ứng dụng với tài nguyên cô lập bằng Testcontainers hoặc cấu hình kiểm thử tương đương.
- Thiết kế dữ liệu, transaction và cấu hình để các test chạy độc lập, có thể lặp lại.

## Bản đồ các ranh giới kiểm thử

Giả sử một chức năng tạo đơn hàng đi qua controller, service, repository và PostgreSQL. Ta có thể kiểm tra từng ranh giới theo thứ tự sau:

~~~mermaid
flowchart LR
    A["Đối tượng Java<br/>value object, quy tắc"] --> B["Logic và collaborator<br/>service + Mockito"]
    B --> C["Spring TestContext<br/>bean wiring, cấu hình"]
    C --> D["HTTP trong tiến trình<br/>MockMvc / WebTestClient"]
    D --> E["HTTP qua socket<br/>server thật + client"]
    E --> F["Tài nguyên thật<br/>PostgreSQL, Redis, broker"]
~~~

Mức kiểm thử càng về sau càng bao phủ nhiều thành phần và càng gần hành vi khi ứng dụng chạy thực tế. Đổi lại, nó thường cần nhiều thời gian khởi tạo, dữ liệu và hạ tầng hơn. Một test ở mức cao không tự động thay thế toàn bộ test ở mức thấp: khi test thất bại, một unit test nhỏ thường chỉ ra nguyên nhân nhanh hơn.

| Mức | Thành phần được chạy | Câu hỏi chính |
|---|---|---|
| Unit test Java | Đối tượng hoặc class cần kiểm tra | Quy tắc và kết quả có đúng với đầu vào không? |
| Unit test có mock | Class đang kiểm tra và collaborator giả lập | Class có phối hợp đúng với dependency không? |
| Spring context test | Một hoặc một nhóm bean thật | Spring có tạo và nối bean đúng không? |
| Test slice | Một phần framework, ví dụ MVC hoặc JPA | Phần framework đó có hoạt động đúng với cấu hình liên quan không? |
| Integration test ứng dụng | Hầu hết cấu hình và bean của ứng dụng | Các thành phần thật có phối hợp đúng không? |
| HTTP test với server thật | Embedded server và HTTP client | Ứng dụng có nhận và trả request qua socket đúng không? |
| Integration với tài nguyên thật | Ứng dụng cùng database, broker hoặc dịch vụ kiểm thử | Giao tiếp với hệ thống bên ngoài có đúng không? |

## 1. Bắt đầu từ đối tượng Java độc lập

Một đối tượng Java không cần Spring để tồn tại. Ví dụ, một value object có thể tự bảo vệ bất biến của nó:

~~~java
public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }
}
~~~

Ta kiểm tra hành vi bằng JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class QuantityTest {

    @Test
    void acceptsPositiveValue() {
        Quantity quantity = new Quantity(2);

        assertEquals(2, quantity.value());
    }

    @Test
    void rejectsZero() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new Quantity(0)
        );
    }
}
~~~

Test này không khởi tạo `ApplicationContext`, không cần `@SpringBootTest` và không cần database. Nó xác nhận trực tiếp hợp đồng của `Quantity`.

Hãy ưu tiên mức này cho:

- Value object, hàm chuyển đổi và bộ kiểm tra dữ liệu.
- Quy tắc tính toán hoặc quyết định nghiệp vụ thuần Java.
- Logic không phụ thuộc vào container, mạng hoặc tài nguyên ngoài tiến trình.

Một unit test tốt thường có ba phần rõ ràng: chuẩn bị đầu vào, gọi hành vi cần kiểm tra, rồi xác nhận kết quả hoặc tác dụng phụ. Tên test nên mô tả hành vi và điều kiện, chẳng hạn `rejectsZero` hoặc `calculatesTotalForMultipleItems`.

## 2. Kiểm tra service và collaborator bằng Mockito

Service thường điều phối nhiều thành phần. Ví dụ, `OrderService` kiểm tra số lượng rồi lưu đơn hàng qua `OrderRepository`. Ta có thể giữ service thật và thay repository bằng mock để kiểm tra logic điều phối:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    OrderRepository repository;

    @InjectMocks
    OrderService service;

    @Test
    void rejectsNonPositiveQuantityBeforeSaving() {
        assertThrows(
            IllegalArgumentException.class,
            () -> service.create("BOOK-1", 0)
        );

        verifyNoInteractions(repository);
    }

    @Test
    void savesAnOrderForValidInput() {
        when(repository.save(any(Order.class)))
            .thenAnswer(invocation -> invocation.getArgument(0));

        Order result = service.create("BOOK-1", 2);

        assertEquals("BOOK-1", result.getSku());
        assertEquals(2, result.getQuantity());
        verify(repository).save(any(Order.class));
    }
}
~~~

`@Mock` tạo dependency giả, còn `@InjectMocks` đưa các dependency đó vào service. `MockitoExtension` tích hợp Mockito với JUnit Jupiter. Spring không tham gia vào test này.

Mock phù hợp khi mục tiêu là kiểm tra logic của class đang xét và cách nó gọi collaborator. Ví dụ, ta muốn xác nhận service từ chối dữ liệu sai trước khi gọi repository, hoặc gửi đúng tham số tới một cổng thanh toán.

Không nên mock chính đối tượng mà test cần kiểm tra. Cũng không nên xác nhận quá nhiều chi tiết nội bộ như thứ tự các lời gọi không thuộc hợp đồng. Nếu mock mọi dependency trong mọi test, ta sẽ không còn kiểm tra được các thành phần thật có tương thích với nhau hay không.

## 3. Khi nào cần Spring TestContext?

Unit test không kiểm tra việc Spring tạo bean, giải quyết dependency, áp dụng profile hoặc đọc cấu hình. Khi chính việc lắp ghép đó là điều cần xác nhận, hãy khởi tạo một `ApplicationContext` nhỏ.

Spring TestContext cung cấp hạ tầng kiểm thử context và tích hợp với JUnit. Với cấu hình Spring Framework thuần, có thể dùng `@SpringJUnitConfig`; với ứng dụng Spring Boot, các annotation như `@SpringBootTest` hoặc test slice đã tích hợp Spring TestContext sẵn.

Ví dụ cấu hình tối giản:

~~~java
@Configuration
class GreetingConfiguration {

    @Bean
    GreetingService greetingService() {
        return new GreetingService("Hello");
    }
}
~~~

~~~java
@SpringJUnitConfig(GreetingConfiguration.class)
class GreetingServiceContextTest {

    @Autowired
    GreetingService greetingService;

    @Test
    void createsServiceFromConfiguration() {
        assertEquals("Hello, Ada", greetingService.greet("Ada"));
    }
}
~~~

Test này xác nhận Spring đọc cấu hình và cung cấp bean cho test. Nó không cần khởi động toàn bộ ứng dụng.

Một số công cụ của Spring TestContext thường gặp:

- `@ContextConfiguration` chỉ định cấu hình dùng để tạo context.
- `@SpringJUnitConfig` kết hợp cấu hình context với tích hợp JUnit Jupiter.
- `@ActiveProfiles` kích hoạt profile kiểm thử.
- `@TestPropertySource` bổ sung property dành cho test.
- `@DirtiesContext` đánh dấu context đã bị thay đổi và cần loại khỏi cache.
- `@Transactional` quản lý transaction cho test khi có transaction manager phù hợp.
- `@Sql` chạy script SQL để chuẩn bị hoặc dọn dữ liệu.

Spring có thể cache context giữa các test có cấu hình tương thích. Điều này giúp giảm thời gian khởi động. Chỉ dùng `@DirtiesContext` khi test thực sự làm thay đổi trạng thái context theo cách không thể khôi phục; dùng tùy tiện sẽ làm mất lợi ích của cache và khiến suite chậm hơn.

## 4. Kiểm tra HTTP bằng test slice

Một controller MVC nhận request, chuyển dữ liệu sang service rồi tạo response. Khi muốn kiểm tra mapping, binding, validation, status code, header và JSON mà không cần khởi động toàn bộ ứng dụng, hãy cân nhắc `@WebMvcTest`.

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    ResponseEntity<OrderResult> create(
            @RequestBody CreateOrderRequest request) {

        OrderResult result =
            orderService.create(request.sku(), request.quantity());

        URI location = URI.create("/api/orders/" + result.id());
        return ResponseEntity.created(location).body(result);
    }
}

record CreateOrderRequest(String sku, int quantity) {}

record OrderResult(UUID id, String sku, int quantity) {}
~~~

Test MVC:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void createsOrderAndReturnsLocation() throws Exception {
        UUID id = UUID.fromString(
            "7c1d4e5a-9b2f-4a6c-8d0e-123456789abc"
        );

        when(orderService.create("BOOK-1", 2))
            .thenReturn(new OrderResult(id, "BOOK-1", 2));

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "sku": "BOOK-1",
                      "quantity": 2
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                "Location", "/api/orders/" + id
            ))
            .andExpect(jsonPath("$.sku").value("BOOK-1"))
            .andExpect(jsonPath("$.quantity").value(2));
    }
}
~~~

`@WebMvcTest` chỉ nạp phần cấu hình MVC cần thiết cho controller được chọn cùng các thành phần liên quan. Service thường được thay bằng mock để test tập trung vào hợp đồng HTTP của controller.

`MockMvc` gửi request qua hạ tầng Spring MVC trong cùng tiến trình. Nó đi qua routing, argument resolver, converter, validation và các MVC component đã được cấu hình trong context. Tuy nhiên, nó **không mở cổng TCP và không gửi request qua mạng**. Vì vậy, `MockMvc` không xác nhận embedded server, socket, TLS, reverse proxy hoặc cấu hình mạng bên ngoài.

Với ứng dụng WebFlux, có thể dùng `@WebFluxTest` và `WebTestClient` để kiểm tra lát cắt reactive. `WebTestClient` cũng có thể làm việc với ứng dụng đang chạy thật; ý nghĩa của test phụ thuộc vào cách client được kết nối.

Khi controller có validation hoặc security, hãy kiểm tra cả các trường hợp hợp lệ và không hợp lệ: body sai định dạng, thiếu trường bắt buộc, dữ liệu vi phạm constraint, người dùng chưa xác thực hoặc không đủ quyền. Đảm bảo test đang chạy đúng filter và security configuration mà bạn muốn kiểm chứng.

## 5. Kiểm tra persistence bằng JPA test slice

Repository là ranh giới giữa ứng dụng và cơ sở dữ liệu. Test service với repository mock không thể chứng minh câu query, mapping entity, constraint hoặc transaction thực sự hoạt động.

Với Spring Data JPA, `@DataJpaTest` tạo một test slice tập trung vào JPA và repository:

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void savesAndFindsOrder() {
        Order saved = repository.save(new Order("BOOK-1", 2));

        Optional<Order> found = repository.findById(saved.getId());

        assertTrue(found.isPresent());
        assertEquals("BOOK-1", found.orElseThrow().getSku());
        assertEquals(2, found.orElseThrow().getQuantity());
    }
}
~~~

Theo cấu hình mặc định, `@DataJpaTest` có thể dùng database nhúng nếu dependency phù hợp có mặt. Điều này hữu ích cho nhiều kiểm tra mapping và repository cơ bản. Nhưng H2 hoặc một database nhúng khác không bảo đảm có cùng hành vi với PostgreSQL, MySQL hay hệ quản trị đang dùng ở production. Khác biệt về dialect, kiểu dữ liệu, collation, constraint, locking và câu SQL có thể khiến test xanh trong khi môi trường thật gặp lỗi.

Nếu hành vi cần kiểm tra phụ thuộc vào hệ quản trị cụ thể, hãy chạy test với đúng engine trong môi trường cô lập. Khi cần giữ nguyên datasource do Testcontainers cung cấp, có thể cấu hình `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)`.

## 6. Tích hợp toàn ứng dụng nhưng vẫn dùng HTTP giả lập

Khi cần xác nhận controller, service, repository và cấu hình ứng dụng phối hợp với nhau, có thể dùng:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderApplicationIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createsOrderThroughApplicationConfiguration()
            throws Exception {

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "sku": "BOOK-1",
                      "quantity": 2
                    }
                    """))
            .andExpect(status().isCreated());
    }
}
~~~

Khác với `@WebMvcTest`, `@SpringBootTest` nạp cấu hình ứng dụng rộng hơn. Service và repository có thể là bean thật; datasource và các tích hợp khác sẽ dùng theo cấu hình đang được kích hoạt.

Kết hợp `@AutoConfigureMockMvc` giúp gửi request qua MVC trong tiến trình. Đây là lựa chọn phù hợp để kiểm tra luồng xuyên nhiều tầng của ứng dụng mà không cần khởi động cổng HTTP thật.

Tên gọi integration test không có nghĩa là test đã chạm tới mọi hệ thống bên ngoài. Nếu datasource vẫn là database nhúng, hoặc email client vẫn là mock, thì những phần đó vẫn chưa được kiểm chứng với tài nguyên thật. Hãy ghi rõ ranh giới nào đang thật và ranh giới nào đang được thay thế.

## 7. Khởi động web server và gửi HTTP thật

Khi cần kiểm tra embedded server và giao tiếp qua socket, dùng web environment có cổng ngẫu nhiên:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void acceptsRequestOverRealHttpServer() {
        CreateOrderRequest request =
            new CreateOrderRequest("BOOK-1", 2);

        ResponseEntity<OrderResult> response =
            http.postForEntity(
                "/api/orders",
                request,
                OrderResult.class
            );

        assertEquals(HttpStatus.CREATED, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("BOOK-1", response.getBody().sku());
    }
}
~~~

Với `RANDOM_PORT`, Spring Boot khởi động embedded web server trên một cổng khả dụng. `TestRestTemplate` gửi request HTTP tới server đó. Cách này kiểm tra thêm quá trình nhận request qua socket và trả response từ server.

Các giá trị web environment thường dùng:

| Giá trị | Hành vi |
|---|---|
| `MOCK` | Tạo web application context mô phỏng; không khởi động embedded server. Đây là mặc định của `@SpringBootTest`. |
| `RANDOM_PORT` | Khởi động embedded server trên cổng ngẫu nhiên. |
| `DEFINED_PORT` | Khởi động embedded server trên cổng được cấu hình. |
| `NONE` | Tạo application context không phải web environment. |

Với ứng dụng Servlet, `MockMvc` thường phù hợp cho kiểm tra MVC trong tiến trình; `TestRestTemplate` hoặc một HTTP client phù hợp được dùng khi server đã chạy. Với WebFlux, `WebTestClient` có thể kết nối tới mock server hoặc server thật tùy cách cấu hình. Hãy chọn client theo stack và ranh giới cần kiểm chứng.

Test qua server thật thường tốn thời gian hơn. Chỉ dùng nó khi socket, server configuration, filter chain, codec hoặc giao tiếp HTTP thực tế là một phần của yêu cầu.

## 8. Kết nối tài nguyên thật trong môi trường kiểm thử

Đến đây, ứng dụng có thể đã chạy qua HTTP nhưng vẫn chưa chắc đang dùng database hoặc broker thật. Để kiểm tra phần tích hợp đó, hãy cung cấp tài nguyên kiểm thử có vòng đời và dữ liệu được kiểm soát.

Testcontainers có thể khởi chạy container cho PostgreSQL, Redis, Kafka và nhiều dịch vụ khác. Ví dụ với PostgreSQL:

~~~java
@Testcontainers
@SpringBootTest
class OrderPostgresIntegrationTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    OrderRepository repository;

    @Test
    void persistsOrderInPostgres() {
        Order saved = repository.save(new Order("BOOK-1", 2));

        assertTrue(repository.findById(saved.getId()).isPresent());
    }
}
~~~

Với Spring Boot có hỗ trợ service connection, `@ServiceConnection` giúp Spring Boot suy ra các thông tin kết nối từ container. Một cách cấu hình khác là dùng `@DynamicPropertySource` để đăng ký URL, username và password lấy từ container vào Environment. Chọn một cách phù hợp với phiên bản và cấu hình dự án; không cần khai báo trùng cả hai cơ chế.

Ví dụ đăng ký property thủ công:

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Khi ghép với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, một test có thể gửi HTTP thật tới ứng dụng đang kết nối PostgreSQL trong container. Khi đó, đường đi được kiểm tra là:

~~~mermaid
sequenceDiagram
    participant T as HTTP test client
    participant S as Embedded server
    participant C as Controller
    participant V as Service
    participant R as Repository
    participant D as PostgreSQL container

    T->>S: POST /api/orders
    S->>C: Request đã được xử lý
    C->>V: create(sku, quantity)
    V->>R: save(order)
    R->>D: INSERT
    D-->>R: Kết quả lưu
    R-->>V: Order
    V-->>C: OrderResult
    C-->>S: HTTP 201 + JSON
    S-->>T: Response
~~~

Test như vậy bao phủ nhiều ranh giới, nhưng cũng có nhiều điều kiện môi trường hơn: Docker phải chạy, image phải tải được, port và resource phải được cấp phát, migration phải hoàn tất và dữ liệu phải được cô lập.

“Tài nguyên thật” ở đây nghĩa là dùng engine hoặc dịch vụ thật trong môi trường kiểm thử có thể hủy và tạo lại. Không dùng database production hoặc tài khoản dịch vụ production làm tài nguyên của test. Mỗi lần chạy nên có dữ liệu riêng, hoặc có quy trình chuẩn bị và dọn dẹp xác định.

## 9. Transaction, dữ liệu và tính độc lập giữa các test

Một suite chỉ đáng tin khi kết quả không phụ thuộc vào thứ tự chạy. Một số quy tắc quan trọng:

**Transaction của test không phải lúc nào cũng bao trùm request HTTP.** Với test slice như `@DataJpaTest`, Spring thường chạy test trong transaction và rollback sau test. Nhưng khi dùng `RANDOM_PORT`, request được xử lý trên thread và transaction riêng của server. Transaction gắn với test method không tự động rollback các thao tác database do request đó thực hiện. Hãy chủ động dọn dữ liệu, dùng schema/database riêng hoặc tạo tài nguyên dùng một lần.

**Dữ liệu test cần có chủ sở hữu rõ ràng.** Tránh phụ thuộc vào một bản ghi được test khác tạo trước đó. Mỗi test nên tự chuẩn bị dữ liệu cần thiết và chỉ xác nhận kết quả thuộc phạm vi của nó. Nếu test chạy song song, tránh dùng chung khóa hoặc tên dữ liệu cố định có thể xung đột.

**Cấu hình test phải được tách biệt.** Dùng profile và property kiểm thử để đặt endpoint, credential giả lập và tùy chọn phù hợp. Không để test vô tình đọc secret hoặc ghi dữ liệu vào môi trường thật.

**Dọn dẹp phải tương ứng với loại tài nguyên.** Database có thể dùng transaction, truncate hoặc schema riêng; file system có thể dùng thư mục tạm; broker có thể dùng topic/queue riêng. Không giả định rollback database sẽ xóa được file, message hoặc tác dụng phụ ở hệ thống khác.

**Không dùng `@DirtiesContext` để sửa lỗi dữ liệu.** Annotation này loại context khỏi cache; nó không phải cơ chế tổng quát để xóa database hoặc khôi phục trạng thái bên ngoài. Hãy dọn đúng loại trạng thái đã thay đổi.

**Kiểm tra bất đồng bộ cần chờ điều kiện, không chờ một khoảng thời gian tùy ý.** Với message broker hoặc tác vụ nền, dùng cơ chế chờ có timeout và điều kiện kết thúc rõ ràng. Một `sleep` cố định vừa làm test chậm vừa có thể thất bại ngẫu nhiên.

## 10. Chọn đúng công cụ cho câu hỏi cần trả lời

| Bạn muốn xác nhận | Công cụ thường phù hợp |
|---|---|
| Quy tắc của một object hoặc hàm Java | JUnit Jupiter |
| Logic service và lời gọi collaborator | JUnit Jupiter + Mockito |
| Spring có tạo đúng một nhóm bean không | `@SpringJUnitConfig` hoặc Spring TestContext |
| Mapping, binding và response của MVC | `@WebMvcTest` + `MockMvc` |
| Controller reactive | `@WebFluxTest` + `WebTestClient` |
| Mapping entity và truy vấn repository | `@DataJpaTest` |
| Luồng xuyên qua cấu hình toàn ứng dụng | `@SpringBootTest` |
| HTTP qua embedded server thật | `@SpringBootTest(RANDOM_PORT)` + HTTP client |
| Tương thích với database hoặc broker cụ thể | Testcontainers + test tích hợp |
| Một hành trình người dùng xuyên nhiều dịch vụ | End-to-end test ở môi trường tích hợp |

Không cần tạo mọi loại test cho mọi chức năng. Hãy đặt câu hỏi cụ thể trước khi chọn annotation:

1. Hành vi này thuộc về một đối tượng Java hay phụ thuộc vào Spring?
2. Tôi cần kiểm tra một class, một lát cắt framework hay toàn bộ cấu hình ứng dụng?
3. Ranh giới HTTP có cần socket và embedded server thật không?
4. Kết quả có phụ thuộc vào dialect, transaction hoặc hành vi của một dịch vụ bên ngoài không?
5. Tôi có thể tạo dữ liệu và tài nguyên cô lập để test lặp lại không?

Chọn mức nhỏ nhất vẫn kiểm chứng được ranh giới đang quan tâm. Bổ sung một số integration test có mục tiêu cho những ranh giới mà mock không thể xác nhận.

## 11. Những nhầm lẫn thường gặp

- **Dùng `@SpringBootTest` cho mọi test:** context lớn làm suite chậm và lỗi khó khoanh vùng. Dùng unit test hoặc slice khi câu hỏi chỉ liên quan đến một phần nhỏ.
- **Cho rằng `MockMvc` là HTTP thật:** `MockMvc` kiểm tra pipeline MVC trong tiến trình, không kiểm tra socket hoặc embedded server.
- **Cho rằng `@DataJpaTest` luôn dùng cùng database production:** database nhúng có thể khác dialect và hành vi của engine thật.
- **Mock repository rồi kết luận persistence hoạt động:** mock chỉ xác nhận cách service gọi collaborator; nó không kiểm tra SQL, mapping hay constraint.
- **Cho rằng `@Transactional` trên test sẽ rollback mọi request:** request qua server thật chạy trong transaction riêng.
- **Dùng `@DirtiesContext` để dọn mọi trạng thái:** context, database, file và message broker có vòng đời riêng.
- **Chỉ kiểm tra status code:** một response có status đúng vẫn có thể có body, header hoặc dữ liệu sai. Hãy xác nhận các phần thuộc hợp đồng API.
- **Chia sẻ dữ liệu giữa các test:** test phụ thuộc thứ tự thường chạy được riêng lẻ nhưng thất bại trong suite hoặc khi chạy song song.

## 12. Quy trình thực hành đề xuất

Với chức năng tạo đơn hàng, có thể triển khai kiểm thử theo trình tự sau:

1. Viết unit test cho value object và quy tắc đầu vào.
2. Viết service unit test với repository mock để kiểm tra quyết định nghiệp vụ và tương tác.
3. Nếu việc cấu hình bean có rủi ro riêng, viết một context test nhỏ cho wiring hoặc profile.
4. Viết MVC slice test cho request, validation, status, header và JSON.
5. Viết JPA slice test cho mapping và truy vấn repository.
6. Viết một integration test ứng dụng để xác nhận controller, service và repository phối hợp.
7. Nếu yêu cầu phụ thuộc vào HTTP server, thêm test `RANDOM_PORT`.
8. Nếu yêu cầu phụ thuộc vào PostgreSQL hoặc broker cụ thể, thêm test với Testcontainers.
9. Chạy từng nhóm test độc lập, sau đó chạy suite liên quan; kiểm tra test có thể chạy lại mà không cần thứ tự cố định.

Khi một test thất bại, hãy xác định ranh giới gần nhất có thể giải thích lỗi. Unit test thất bại thường chỉ ra quy tắc hoặc logic; slice test có thể chỉ ra cấu hình framework; test với tài nguyên thật có thể phát hiện khác biệt dialect, transaction hoặc giao thức. Giữ mỗi test tập trung vào một hợp đồng rõ ràng sẽ giúp việc sửa lỗi nhanh và an toàn hơn.

## Kết luận

Luồng từ đối tượng Java đến HTTP và tài nguyên thật là một thang kiểm chứng các ranh giới của ứng dụng Spring. JUnit và Mockito giúp kiểm tra logic nhanh; Spring TestContext xác nhận việc lắp ghép bean; test slice tập trung vào MVC hoặc persistence; `@SpringBootTest` kiểm tra tích hợp ứng dụng; server thật và Testcontainers mở rộng phạm vi tới giao tiếp mạng và hạ tầng.

Một bộ kiểm thử cân bằng kết hợp nhiều mức với mục tiêu rõ ràng. Mỗi test nên trả lời được: ranh giới nào đang được kiểm tra, thành phần nào là thật, thành phần nào được thay thế, và dữ liệu được cô lập ra sao.

