# Kiểm thử API với WebTestClient và cơ sở dữ liệu thật

Một API dùng Spring WebFlux và Spring Data Relational R2DBC cần được kiểm thử qua cả hai ranh giới: HTTP và database. Test chỉ gọi controller với service giả có thể xác nhận status, JSON và cách xử lý request, nhưng không chứng minh SQL, mapping, constraint, transaction hoặc R2DBC driver hoạt động đúng. Ngược lại, test repository trực tiếp có thể chứng minh persistence nhưng không xác nhận API trả đúng status, header, body hay bảo vệ endpoint đúng cách.

**WebTestClient** giúp gửi request HTTP và kiểm tra response trong test Spring reactive. Khi kết hợp với một database thật, chẳng hạn PostgreSQL hoặc Oracle chạy trong môi trường kiểm thử riêng, ta có thể đi qua toàn bộ luồng:

~~~text
Test
 |
 | HTTP request
 v
WebTestClient
 |
 v
WebFlux server / Security filters
 |
 v
Controller
 |
 v
Service / reactive transaction
 |
 v
Spring Data repository / DatabaseClient
 |
 v
R2DBC driver
 |
 v
Database thật
 |
 v
HTTP response
 |
 v
Assertion về status, headers, JSON và dữ liệu đã lưu
~~~

Bài học này trình bày cách chọn chế độ WebTestClient, khởi chạy ứng dụng với database thật bằng Testcontainers, nạp schema và fixture, kiểm tra request/response cùng trạng thái persistence, kiểm thử bảo mật và transaction, xử lý stream reactive, cleanup và chạy test ổn định trong CI.

## 1. Phân biệt các loại kiểm thử API

Không phải test nào dùng WebTestClient cũng chạy toàn bộ ứng dụng hoặc truy cập database thật. Cần chọn đúng phạm vi.

| Cách kiểm thử | Phạm vi | Khi phù hợp |
|---|---|---|
| Gọi controller trực tiếp | Method controller, không có HTTP stack | Unit test logic điều phối đơn giản |
| WebTestClient.bindToController | Controller và một phần WebFlux test infrastructure | Kiểm tra routing/serialization với dependency giả |
| WebTestClient.bindToRouterFunction | Functional endpoint | Kiểm tra router function |
| WebTestClient.bindToApplicationContext | Handler, filter và bean trong application context qua mock server | Kiểm tra tích hợp trong context; có thể nối database thật |
| WebTestClient.bindToServer | Gửi HTTP tới server đang chạy | Kiểm tra HTTP qua network |
| @WebFluxTest | Slice tập trung vào WebFlux/controller | Kiểm tra API contract với service mock |
| @SpringBootTest với RANDOM_PORT | Application context đầy đủ và web server thật trên port ngẫu nhiên | Integration test đầu-cuối với database thật |

Nếu mục tiêu là kiểm tra API cùng R2DBC database thật, lựa chọn thường phù hợp là **@SpringBootTest(webEnvironment = RANDOM_PORT)** kết hợp **WebTestClient** và database riêng. Cách này khởi động server thật và gửi request qua HTTP tới server đó.

**@WebFluxTest** thường chỉ nạp slice web và các dependency được chọn. Nó hữu ích cho controller test nhưng không tự chứng minh repository và database thật được cấu hình đúng. Có thể import thêm thành phần persistence, nhưng khi phạm vi đã bao gồm ứng dụng và database, full application integration test thường dễ hiểu hơn.

## 2. WebTestClient hoạt động như thế nào?

WebTestClient có API fluent để tạo request và khai báo assertion:

~~~java
webTestClient.get()
        .uri("/api/customers/42")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
            .jsonPath("$.id").isEqualTo(42);
~~~

Các bước:

1. Chọn HTTP method như GET, POST, PUT, PATCH hoặc DELETE.
2. Chọn URI và query parameter.
3. Đặt header, cookie hoặc authentication.
4. Gửi body nếu cần.
5. Gọi **exchange()** để thực hiện request.
6. Kiểm tra status, header và body.

WebTestClient có thể hoạt động với mock server hoặc server thật. API assertion gần giống nhau, nhưng phạm vi hệ thống được thực thi khác nhau.

### 2.1. bindToController

Ví dụ:

~~~java
WebTestClient client = WebTestClient
        .bindToController(new CustomerController(customerService))
        .build();
~~~

Cách này phù hợp khi service đã được mock hoặc cung cấp test double. Nó không tự khởi chạy toàn bộ application context, security chain, R2DBC connection factory hay database.

### 2.2. bindToApplicationContext

Ví dụ:

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .build();
~~~

Cách này dùng bean trong context và mock web server infrastructure. Nếu application context đã cấu hình repository và kết nối database test thật, request có thể đi qua persistence thật dù không mở network socket tới một port ngẫu nhiên.

Đây là integration test hữu ích cho handler/filter và context, nhưng không kiểm tra mọi chi tiết của embedded server hoặc network.

### 2.3. bindToServer

Ví dụ:

~~~java
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
~~~

Client gửi request tới server đang chạy. Test phải tự quản lý vòng đời server và base URL.

Trong Spring Boot integration test, có thể để Spring khởi chạy server trên port ngẫu nhiên rồi inject WebTestClient, tránh hardcode port cố định.

## 3. Dependency cho integration test

Với ứng dụng Spring Boot WebFlux và R2DBC, test thường cần:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")

    runtimeOnly("org.postgresql:r2dbc-postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")

    // Chỉ thêm nếu ứng dụng dùng Spring Security.
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Các version nên được quản lý bởi Spring Boot dependency management/BOM và phiên bản Testcontainers phù hợp. Ví dụ này dùng PostgreSQL; nếu production dùng Oracle, SQL Server hoặc database khác, thay driver và container/test environment bằng đúng hệ quản trị mục tiêu.

Spring Boot starter test thường cung cấp JUnit Jupiter, AssertJ và các thư viện kiểm thử Spring. WebTestClient được cấu hình qua Spring Boot/WebFlux test infrastructure.

Không thêm JDBC driver chỉ để chạy R2DBC test, trừ khi dự án dùng một công cụ migration hoặc tác vụ khác cần JDBC. Nếu dùng Flyway truyền thống, có thể cần cấu hình JDBC connection riêng cho migration; runtime repository vẫn dùng R2DBC.

## 4. Khởi chạy database thật bằng Testcontainers

Testcontainers khởi chạy database trong container và cung cấp host/port động. Test dùng đúng database engine thay vì dựa vào mock hoặc một embedded database có SQL semantics khác.

Ví dụ PostgreSQL:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("test")
class CustomerApiIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
                "r2dbc:postgresql://"
                        + database.getHost()
                        + ":"
                        + database.getMappedPort(5432)
                        + "/"
                        + database.getDatabaseName());

        registry.add("spring.r2dbc.username", database::getUsername);
        registry.add("spring.r2dbc.password", database::getPassword);
    }

    @Autowired
    WebTestClient webTestClient;
}
~~~

Điểm quan trọng:

- Container được khởi động trước khi Spring tạo application context.
- **@DynamicPropertySource** đăng ký R2DBC URL và credential thực tế của container.
- **RANDOM_PORT** tránh xung đột port khi nhiều test suite chạy trên cùng máy.
- **WebTestClient** được inject và gửi request tới server Spring Boot đang chạy.
- Test không cần biết port được cấp trước khi container/server khởi động.

Tag image trong ví dụ minh họa một major version. Với CI, nên chọn tag hoặc digest đã được kiểm soát để tránh một lần chạy test tải về image khác với lần trước. Nếu ứng dụng dùng database khác, chạy đúng engine và phiên bản tương thích với production.

### 4.1. Nếu không dùng Testcontainers

Có thể chạy database test riêng bên ngoài container, ví dụ instance dành cho CI hoặc một database ephemeral do pipeline tạo. Khi đó cung cấp các thuộc tính:

- R2DBC URL.
- Username/password dành riêng cho test.
- Database/schema test.
- Cấu hình TLS nếu cần.
- Migration/schema initializer.

Không trỏ test tới database development dùng chung hoặc production. Tên profile là chưa đủ để bảo đảm an toàn; cần xác nhận URL và quyền của database user.

### 4.2. Kiểm thử Oracle hoặc database có yêu cầu đặc biệt

Với Oracle, SQL Server hoặc database cần image được cấp phép, dùng container image và cấu hình được nhà cung cấp hỗ trợ hoặc một test instance chuyên biệt. Không giả định mọi database đều có image public có thể chạy tùy ý.

Dù dùng container hay test service, mục tiêu là chạy đúng engine, đúng driver R2DBC và phiên bản gần production. H2 compatibility mode không thay thế được điều này.

## 5. Cấu hình schema và migration

Database container mới thường chưa có bảng. Ứng dụng phải tạo schema trước khi test gửi request.

Có hai hướng phổ biến:

1. Chạy migration của dự án, chẳng hạn Flyway hoặc Liquibase.
2. Dùng SQL initialization cho test nhỏ hoặc bài tập.

Nếu dùng Spring Boot SQL initialization cho R2DBC, cấu hình test profile có thể chỉ định script:

~~~yaml
spring:
  sql:
    init:
      mode: always
      schema-locations: classpath:db/test-schema.sql
      data-locations: classpath:db/test-data.sql
      continue-on-error: false
~~~

Tên thuộc tính và thứ tự khởi tạo cần kiểm tra theo phiên bản Spring Boot. Không để script có lệnh DROP/TRUNCATE chạy trong profile mặc định hoặc production.

Trong dự án thực tế, ưu tiên chạy cùng migration được dùng khi triển khai. Điều đó giúp test phát hiện migration lỗi, thiếu index, constraint hoặc kiểu cột khác với schema mong đợi.

### 5.1. Flyway/Liquibase có thể dùng JDBC trong khi ứng dụng dùng R2DBC

Flyway truyền thống thường quản lý migration qua JDBC. Khi dùng cách này, test có thể cần cung cấp cả hai cấu hình trỏ tới cùng database:

~~~java
@DynamicPropertySource
static void configureDatabase(DynamicPropertyRegistry registry) {
    String host = database.getHost();
    Integer port = database.getMappedPort(5432);
    String name = database.getDatabaseName();

    registry.add("spring.r2dbc.url", () ->
            "r2dbc:postgresql://" + host + ":" + port + "/" + name);
    registry.add("spring.r2dbc.username", database::getUsername);
    registry.add("spring.r2dbc.password", database::getPassword);

    registry.add("spring.datasource.url",
            () -> "jdbc:postgresql://" + host + ":" + port + "/" + name);
    registry.add("spring.datasource.username", database::getUsername);
    registry.add("spring.datasource.password", database::getPassword);
}
~~~

Cấu hình JDBC chỉ cần nếu migration tool thực sự dùng nó và test có JDBC driver tương ứng. Không gán JDBC URL cho thuộc tính R2DBC hoặc nghĩ rằng Flyway tự dùng R2DBC chỉ vì ứng dụng dùng R2DBC.

### 5.2. Kiểm tra migration trước khi test API

Một bài test API không nên âm thầm tạo bảng tối giản khác schema production. Hãy để migration tạo schema và sau đó test các hành vi cần thiết:

- Insert hợp lệ.
- Unique constraint.
- Foreign key.
- Not-null/check constraint.
- Index và query plan nếu là mục tiêu test.
- Kiểu dữ liệu và converter.

Nếu migration thất bại, application context nên fail sớm để lỗi được phát hiện ngay khi khởi tạo test.

## 6. Gửi request và kiểm tra response

Ví dụ API tạo customer nhận JSON và trả status 201:

~~~java
@Test
void createsCustomerThroughHttp() {
    CreateCustomerRequest request =
            new CreateCustomerRequest(
                    "api-test@example.test",
                    "API Test Customer");

    webTestClient.post()
            .uri("/api/customers")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .exchange()
            .expectStatus().isCreated()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
                .jsonPath("$.id").exists()
                .jsonPath("$.email")
                    .isEqualTo("api-test@example.test");
}
~~~

Test này kiểm tra:

- Route nhận POST.
- JSON request được deserialize.
- Content type và response format đúng.
- API trả status 201.
- Body có ID và email mong đợi.

Nhưng nếu chỉ assert response thì chưa chứng minh dữ liệu đã được lưu đúng. Cần kiểm tra trạng thái database ở bước tiếp theo.

### 6.1. Lấy response body để dùng ID do database sinh

Ví dụ DTO response là record:

~~~java
public record CustomerResponse(
        Long id,
        String email,
        String fullName) {
}
~~~

Test có thể lấy kết quả:

~~~java
@Test
void createsAndPersistsCustomer() {
    CreateCustomerRequest request =
            new CreateCustomerRequest(
                    "persisted@example.test",
                    "Persisted Customer");

    EntityExchangeResult<CustomerResponse> result =
            webTestClient.post()
                    .uri("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(request)
                    .exchange()
                    .expectStatus().isCreated()
                    .expectBody(CustomerResponse.class)
                    .returnResult();

    CustomerResponse response = result.getResponseBody();

    assertThat(response).isNotNull();
    assertThat(response.id()).isNotNull();
    assertThat(response.email())
            .isEqualTo("persisted@example.test");

    StepVerifier.create(customerRepository.findById(response.id()))
            .assertNext(saved -> {
                assertThat(saved.getEmail())
                        .isEqualTo("persisted@example.test");
                assertThat(saved.getFullName())
                        .isEqualTo("Persisted Customer");
            })
            .verifyComplete();
}
~~~

Ví dụ này giả định repository được inject và DTO/entity phù hợp với ứng dụng. **ID lấy từ response** là ID database trả về; không đoán ID bằng 1 hoặc dùng SELECT MAX(id).

Test gọi API qua HTTP, sau đó đọc repository bằng một subscription khác. Với một endpoint đồng bộ thông thường, response chỉ được trả sau khi publisher của service hoàn tất; nếu service transaction đã commit trước khi hoàn tất, truy vấn tiếp theo sẽ thấy dữ liệu.

### 6.2. Kiểm tra response JSON chính xác hơn

Có thể dùng JSONPath:

~~~java
webTestClient.get()
        .uri("/api/customers/{id}", customerId)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(customerId)
        .jsonPath("$.email").isEqualTo("persisted@example.test")
        .jsonPath("$.fullName").isEqualTo("Persisted Customer");
~~~

Dùng assertion theo contract công khai của API. Tránh assert vào field nội bộ của entity nếu API không cam kết công bố field đó.

## 7. Kiểm tra dữ liệu được lưu bằng repository hoặc DatabaseClient

Mục tiêu của integration test là xác nhận cả response lẫn dữ liệu thực tế. Có thể dùng:

- Repository để kiểm tra entity và mapping.
- DatabaseClient để truy vấn SQL cụ thể.
- Một API GET khác để xác nhận client có thể đọc lại tài nguyên.

Ví dụ repository:

~~~java
StepVerifier.create(customerRepository.findByEmail("persisted@example.test"))
        .assertNext(customer -> {
            assertThat(customer.getId()).isNotNull();
            assertThat(customer.getFullName())
                    .isEqualTo("Persisted Customer");
        })
        .verifyComplete();
~~~

Ví dụ DatabaseClient:

~~~java
StepVerifier.create(
        databaseClient.sql("""
                SELECT COUNT(*) AS total
                FROM customer
                WHERE email = :email
                """)
                .bind("email", "persisted@example.test")
                .map((row, metadata) ->
                        row.get("total", Long.class))
                .one())
        .expectNext(1L)
        .verifyComplete();
~~~

Kiểu dữ liệu trả về của COUNT phụ thuộc database/driver; có thể cần map sang Number/BigInteger hoặc kiểu phù hợp với dialect. Ví dụ cần điều chỉnh theo driver thật.

Dùng repository để xác nhận mapping entity. Dùng SQL trực tiếp khi cần kiểm tra constraint, column value hoặc behavior database mà repository abstraction không bộc lộ.

## 8. Kiểm tra GET, not found và danh sách

Test GET thành công:

~~~java
@Test
void readsCustomerById() {
    Customer saved = customerRepository.save(
            CustomerFixtures.defaultCustomer())
            .block(Duration.ofSeconds(5));

    assertThat(saved).isNotNull();

    webTestClient.get()
            .uri("/api/customers/{id}", saved.getId())
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo(saved.getId())
            .jsonPath("$.email")
                .isEqualTo(saved.getEmail());
}
~~~

Việc dùng **block()** ở test setup là chấp nhận được khi được giới hạn ở ranh giới test và có timeout. Không đưa blocking vào service/controller reactive của ứng dụng.

Test không tìm thấy:

~~~java
webTestClient.get()
        .uri("/api/customers/{id}", 999999999L)
        .exchange()
        .expectStatus().isNotFound()
        .expectBody()
        .jsonPath("$.code").isEqualTo("CUSTOMER_NOT_FOUND");
~~~

Test danh sách cần xác nhận query parameter và thứ tự:

~~~java
webTestClient.get()
        .uri(uriBuilder -> uriBuilder
                .path("/api/customers")
                .queryParam("page", 0)
                .queryParam("size", 10)
                .queryParam("sort", "email,asc")
                .build())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.content").isArray()
        .jsonPath("$.page.totalElements").isEqualTo(2);
~~~

Tên JSON field và cấu trúc page phụ thuộc response DTO của ứng dụng. Đặt sort key ổn định, thường thêm ID làm tie-breaker nếu nhiều hàng có cùng giá trị.

## 9. Kiểm tra validation và constraint database

Validation ở API và constraint ở database là hai lớp bảo vệ khác nhau.

Ví dụ request thiếu email có thể bị Bean Validation từ chối trước khi truy cập database:

~~~java
webTestClient.post()
        .uri("/api/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("""
                {
                  "email": "",
                  "fullName": "No Email"
                }
                """)
        .exchange()
        .expectStatus().isBadRequest();
~~~

Test unique constraint nên gửi hai request cùng email:

~~~java
CreateCustomerRequest request =
        new CreateCustomerRequest(
                "duplicate@example.test",
                "Duplicate");

webTestClient.post()
        .uri("/api/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(request)
        .exchange()
        .expectStatus().isCreated();

webTestClient.post()
        .uri("/api/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(request)
        .exchange()
        .expectStatus().isEqualTo(HttpStatus.CONFLICT);
~~~

Test này chứng minh database constraint và exception mapping được thực thi nếu API chuyển lỗi duplicate thành 409. Kết quả phụ thuộc exception translator và handler của ứng dụng; nếu API có contract khác, assertion phải theo contract đã định nghĩa.

Đừng chỉ test service kiểm tra tồn tại trước khi insert. Hai request đồng thời có thể cùng vượt qua bước kiểm tra. Unique constraint của database mới là hàng rào cuối cùng.

## 10. Kiểm tra lỗi và transaction rollback qua HTTP

Một API có thể thực hiện nhiều thao tác trong một transaction, ví dụ tạo đơn hàng và các dòng chi tiết. Nếu bước thứ hai thất bại, transaction phải rollback theo contract nghiệp vụ.

Test nên:

1. Chuẩn bị fixture hợp lệ.
2. Gửi request kích hoạt lỗi ở một bước sau khi bước đầu đã ghi.
3. Kiểm tra status/error body.
4. Truy vấn database để xác nhận không có dữ liệu một phần.
5. Nếu có audit/outbox, xác nhận trạng thái của chúng đúng với thiết kế.

Ví dụ minh họa:

~~~java
@Test
void rollsBackOrderWhenLineInsertFails() {
    CreateOrderRequest request =
            OrderFixtures.requestWithInvalidLine();

    webTestClient.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .exchange()
            .expectStatus().isBadRequest();

    StepVerifier.create(orderRepository
                    .findByOrderNumber(request.orderNumber()))
            .verifyComplete();
}
~~~

Ví dụ này giả định lỗi được ánh xạ thành 400 và repository trả empty khi không có đơn. Nếu lỗi là vi phạm constraint kỹ thuật được chuyển thành conflict hoặc lỗi server, điều chỉnh status theo API contract.

### 10.1. Vì sao @Transactional trên test không tự rollback request HTTP?

Khi test gửi request qua WebTestClient tới server đang chạy, server xử lý request trong subscription và reactive context của request đó. Transaction của service được tạo và kết thúc theo luồng server.

Một transaction gắn vào test method không tự bao bọc transaction của HTTP request. Test client và server request là hai execution context riêng; việc chúng chạy trong cùng JVM không làm Reactor Context hoặc connection transaction tự truyền qua ranh giới HTTP.

Vì vậy, không dựa vào **@Transactional** trên test class để tự rollback mọi thao tác mà API đã thực hiện. Dữ liệu có thể đã commit và cần cleanup tường minh.

### 10.2. Test transaction rollback ở service và qua HTTP có mục đích khác nhau

- Service/repository transaction test kiểm tra semantics transaction trực tiếp.
- API integration test kiểm tra lỗi được trả về đúng và database không có trạng thái dở dang.
- Cả hai đều có giá trị, nhưng một loại không thay thế hoàn toàn loại kia.

Nếu endpoint trả 202 Accepted và xử lý nền sau response, test cần đợi trạng thái cuối bằng điều kiện eventual assertion hoặc API trạng thái công việc. Không giả định response 202 đồng nghĩa database đã hoàn tất.

## 11. Chuẩn bị và dọn fixture một cách reactive

Fixture có thể được tạo qua repository trước khi gọi API:

~~~java
@BeforeEach
void resetDatabase() {
    databaseClient.sql("DELETE FROM purchase_order_item")
            .then()
            .then(databaseClient.sql("DELETE FROM purchase_order").then())
            .then(databaseClient.sql("DELETE FROM customer").then())
            .block(Duration.ofSeconds(10));
}
~~~

Ví dụ này xóa bảng con trước bảng cha. SQL phải điều chỉnh theo schema thật; với PostgreSQL có thể dùng TRUNCATE/RESTART IDENTITY CASCADE trên database test riêng, nhưng không dùng lệnh xóa toàn cục trên database dùng chung.

JUnit lifecycle method đồng bộ không tự subscribe hoặc chờ một Mono chỉ vì method trả về publisher. Cần chờ cleanup hoàn tất rõ ràng, ví dụ dùng .block(timeout) tại test boundary như trên, hoặc một extension/lifecycle integration có hỗ trợ reactive.

### 11.1. Dùng ID hoặc namespace riêng cho test

Nếu nhiều test cùng database, fixture có key duy nhất như email cố định có thể va chạm. Dùng UUID hoặc namespace test:

~~~java
String email = "it-" + UUID.randomUUID() + "@example.test";
~~~

Giữ giá trị này trong test để truy vấn và cleanup đúng hàng. Không dùng random data cho trường đang được so sánh với giá trị cố định nếu không giữ lại giá trị đã tạo.

### 11.2. Cleanup theo thứ tự foreign key

Nếu test tạo customer rồi order rồi order item, cleanup thường theo thứ tự ngược:

~~~text
DELETE order_item
       |
       v
DELETE purchase_order
       |
       v
DELETE customer
~~~

Dùng cascade chỉ khi đó là semantics được schema chấp nhận. Cleanup phải hoàn tất trước khi test tiếp theo dùng lại database.

## 12. Test security filter và authentication

Nếu API dùng Spring Security WebFlux, test nên xác nhận cả endpoint được phép và bị từ chối.

Với security test support, có thể thêm authentication giả vào WebTestClient:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

webTestClient.mutateWith(mockUser("alice").roles("USER"))
        .get()
        .uri("/api/profile")
        .exchange()
        .expectStatus().isOk();
~~~

Với endpoint POST dùng CSRF protection trong session-based security, có thể cần thêm CSRF token:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

webTestClient.mutateWith(mockUser("alice").roles("USER"))
        .mutateWith(csrf())
        .post()
        .uri("/api/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(request)
        .exchange()
        .expectStatus().isCreated();
~~~

Cấu hình cụ thể phụ thuộc security chain. Một số API bearer-token không bật CSRF theo cùng cách session/cookie app.

Các test nên bao gồm:

- Không có authentication.
- User đã đăng nhập nhưng thiếu role.
- User có role phù hợp.
- Token hết hạn hoặc không hợp lệ nếu test validation thật.
- CSRF token thiếu/có nếu CSRF được bật.
- Quyền truy cập tenant hoặc owner.
- Auditor của request nếu auditing dựa vào SecurityContext.

### 12.1. Mock authentication khác xác thực token thật

**mockUser()** hoặc **mockJwt()** tạo security context cho test; chúng hữu ích để kiểm tra authorization và controller behavior. Chúng không chứng minh JWT signature, issuer, audience, key rotation hoặc identity provider đang hoạt động đúng.

Nếu cần kiểm thử token end-to-end, dùng token ký bằng test key và cấu hình decoder tương ứng, hoặc test identity provider trong môi trường tích hợp. Không dùng token production trong test.

Nếu auditing cần principal custom có user ID, hãy thiết lập principal đúng kiểu ứng dụng. **mockUser("alice")** thường cung cấp principal kiểu UserDetails mặc định, không tự động trở thành custom principal có ID database.

## 13. Kiểm tra auditor và dữ liệu audit

Nếu entity có **@CreatedBy**, **@LastModifiedBy**, **@CreatedDate** và **@LastModifiedDate**, API test có thể xác nhận security context được truyền tới ReactiveAuditorAware và dữ liệu audit được lưu.

Một kịch bản:

1. Gửi POST với user A.
2. Lấy ID entity trả về.
3. Đọc database và xác nhận createdBy là A.
4. Gửi PATCH với user B.
5. Đọc lại và xác nhận createdBy vẫn là A, lastModifiedBy là B.
6. Xác nhận timestamp cập nhật phù hợp.

Không chỉ kiểm tra response nếu auditor được ghi ở persistence callback. Đọc entity hoặc cột trong database để chứng minh auditing đã chạy trên đường ghi thật.

## 14. Kiểm thử pagination, sorting và filtering

API list thường kết hợp query parameter với Spring Data repository. Test với database thật giúp xác nhận SQL dialect và sort mapping.

Fixture nên chứa:

- Hàng có trạng thái khớp filter.
- Hàng không khớp filter.
- Hai hàng có cùng timestamp để kiểm tra tie-breaker.
- Đủ hàng để tạo ít nhất hai trang.

Ví dụ:

~~~java
webTestClient.get()
        .uri(uriBuilder -> uriBuilder
                .path("/api/orders")
                .queryParam("status", "OPEN")
                .queryParam("page", 0)
                .queryParam("size", 2)
                .queryParam("sort", "createdAt,desc")
                .build())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.content.length()").isEqualTo(2)
        .jsonPath("$.totalElements").isEqualTo(3);
~~~

Thực hiện thêm request trang tiếp theo và xác nhận không trùng/mất hàng theo contract. Nếu database có thể trả cùng sort value, thêm ID làm sort tie-breaker để thứ tự ổn định.

## 15. Kiểm thử streaming endpoint và Flux response

WebTestClient hỗ trợ đọc response stream. Với Server-Sent Events:

~~~java
FluxExchangeResult<OrderEvent> result =
        webTestClient.get()
                .uri("/api/orders/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(OrderEvent.class);

StepVerifier.create(result.getResponseBody())
        .expectNextMatches(event ->
                event.type().equals("ORDER_CREATED"))
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

Dùng **StepVerifier** để kiểm tra các phần tử phát ra, completion, error và cancellation. Nếu stream là vô hạn, test cần giới hạn thời gian và hủy subscription có chủ đích.

Khi test stream đọc từ database:

- Xác nhận connection được giữ trong thời gian nào.
- Hủy stream có giải phóng resource không.
- Không buffer toàn bộ dữ liệu lớn nếu mục tiêu là streaming.
- Kiểm tra lỗi xuất hiện sau khi một phần response đã được gửi.
- Không giả định client nhận được một JSON array hoàn chỉnh nếu endpoint là stream.

Với endpoint trả Flux<T> dưới dạng JSON array, server có thể encode response theo cấu hình codec. Nếu cần kiểm tra từng phần tử hoặc backpressure, dùng returnResult thay vì chỉ đọc toàn bộ body.

## 16. Timeout và test bất đồng bộ

WebTestClient có response timeout. Có thể cấu hình client:

~~~java
WebTestClient client = WebTestClient
        .bindToServer()
        .responseTimeout(Duration.ofSeconds(5))
        .baseUrl(baseUrl)
        .build();
~~~

Trong Spring Boot test, có thể cấu hình client được inject hoặc dùng timeout của test framework theo API phiên bản đang dùng.

Không tăng timeout thật lớn để che query chậm. Xác định test đang chờ:

- Server khởi động.
- Connection pool cấp connection.
- Migration chạy.
- SQL query.
- Background job.
- Stream phát event.
- External service.

Nếu endpoint trả 202 rồi xử lý nền, dùng polling theo điều kiện có timeout, không dùng Thread.sleep cố định. Điều kiện cần xác nhận là trạng thái nghiệp vụ đã đạt, không phải chỉ thời gian đã trôi qua.

## 17. Kiểm thử đồng thời và tính toàn vẹn dữ liệu

Một số lỗi chỉ xuất hiện khi nhiều request chạy cùng lúc:

- Hai request đăng ký cùng email.
- Hai request cập nhật cùng một entity có @Version.
- Hai worker lấy cùng một job.
- Hai request cùng giảm tồn kho.
- Connection pool bị cạn.
- Lock timeout hoặc deadlock.

WebTestClient thường được dùng theo API test fluent; nếu cần tạo nhiều HTTP request reactive đồng thời, có thể dùng **WebClient** trỏ tới port của test server:

~~~java
Flux.range(0, 10)
        .flatMap(index ->
                webClient.post()
                        .uri("/api/reservations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(requestFor(index))
                        .retrieve()
                        .toBodilessEntity(),
                10)
        .collectList()
        .block(Duration.ofSeconds(20));
~~~

Đây là ví dụ minh họa cho test concurrency. Sau khi các request hoàn tất, truy vấn database để xác nhận invariant, chẳng hạn tổng reservation không vượt tồn kho hoặc chỉ có một bản ghi unique.

Không chỉ assert rằng mọi request trả 200. Trong tình huống cạnh tranh, một số request có thể đúng khi trả 409/423 hoặc status được định nghĩa. Điều quan trọng là trạng thái database cuối cùng không vi phạm invariant.

## 18. Không dùng H2 làm bằng chứng cho database production

H2 có thể phù hợp cho test nhanh, nhưng không thay thế database thật khi ứng dụng phụ thuộc:

- Dialect và SQL riêng.
- Sequence/identity và generated key.
- JSON, array, enum, LOB.
- Precision và timezone.
- Isolation và locking.
- DDL transaction semantics.
- Error code và exception translation.
- Index, collation và execution plan.

Nếu production dùng PostgreSQL, chạy integration test với PostgreSQL. Nếu dùng Oracle, kiểm tra Oracle. Nếu dùng SQL Server, kiểm tra SQL Server. Compatibility mode chỉ giúp mô phỏng một phần cú pháp; nó không biến engine này thành engine khác.

Có thể giữ H2 cho một số unit/in-memory test, nhưng không dùng kết quả đó để kết luận API persistence tương thích production.

## 19. Chạy test song song an toàn

Một container static có thể được dùng chung cho nhiều method trong cùng class. Nếu nhiều class cùng chia sẻ database, cần có chiến lược rõ ràng.

Các cách cô lập:

- Một database/container cho mỗi test class.
- Một schema riêng cho mỗi test suite.
- Namespace dữ liệu riêng theo test.
- Cleanup theo ID của fixture.
- Tắt parallel execution cho test cần truncate dữ liệu chung.
- Tạo container/database riêng cho nhóm test destructive.

Không chạy TRUNCATE toàn database trong @BeforeEach nếu test khác có thể đang đọc hoặc ghi cùng lúc. Không dùng một email cố định ở nhiều test chạy song song.

Testcontainers mặc định quản lý vòng đời container; đừng bật reuse toàn cục trong CI nếu không kiểm soát việc reset dữ liệu và version image.

## 20. Kiểm tra lỗi API và error contract

Database thật có thể phát lỗi mà mock không mô phỏng chính xác. Nên kiểm tra cách API chuyển các nhóm lỗi:

| Tình huống | Response thường cân nhắc |
|---|---|
| Request sai định dạng/validation | 400 Bad Request |
| Không tìm thấy tài nguyên | 404 Not Found |
| Unique/business conflict | 409 Conflict |
| Thiếu authentication | 401 Unauthorized |
| Không đủ quyền | 403 Forbidden |
| Database tạm thời không sẵn sàng | 503 Service Unavailable hoặc lỗi hệ thống theo contract |
| Lỗi SQL triển khai | 500 Internal Server Error |

Status cụ thể phải theo contract API của ứng dụng. Không trả SQL, stack trace, tên schema hoặc vendor error code thô cho client.

Test nên kiểm tra cả error body ổn định, ví dụ code, message và traceId, chứ không assert thông điệp exception driver vốn có thể thay đổi theo phiên bản hoặc ngôn ngữ database.

## 21. Tách test API khỏi test repository

Một test API với database thật có chi phí khởi động server, context, migration và container. Không cần lặp lại mọi trường hợp mapping ở cả hai tầng.

Có thể chia trách nhiệm:

| Test | Kiểm tra chính |
|---|---|
| Unit test service | Quy tắc nghiệp vụ và nhánh xử lý |
| Repository integration test | SQL, mapping, converter, constraint, dialect |
| API slice test | Routing, validation, status, serialization, security mapping |
| Full API + database integration test | HTTP, security, service, transaction và persistence phối hợp |
| Concurrency/load test | Locking, pool, throughput và invariant dưới tải |

API integration test nên tập trung vào các use case quan trọng và contract bên ngoài. Repository test kiểm tra chi tiết SQL/mapping nhiều hơn.

## 22. CI và khả năng tái lập

Để test đáng tin cậy trong CI:

- Pin version database image.
- Dùng database test ephemeral hoặc container.
- Chờ health/readiness của database trước khi chạy migration.
- Chạy migration từ trạng thái rỗng.
- Dùng credential chỉ có quyền trên test database.
- Không lấy secret production làm biến môi trường test.
- Thu thập log container khi test thất bại.
- Đặt timeout cho container startup, HTTP response và query.
- Cleanup container sau test.
- Chạy lại các test quan trọng với đúng database major version của production.
- Giữ test fixture nhỏ và xác định.

Khi test thất bại, lưu thông tin hữu ích như request correlation ID, SQLState, exception class và log database đã được lọc dữ liệu nhạy cảm. Không ghi token, password hoặc toàn bộ request body nếu chứa dữ liệu cá nhân.

## 23. Ví dụ tổng hợp một API integration test

Ví dụ dưới đây ghép WebTestClient, Testcontainers, repository và kiểm tra persistence:

~~~java
@Testcontainers
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("test")
class CustomerApiIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
                "r2dbc:postgresql://"
                        + database.getHost()
                        + ":"
                        + database.getMappedPort(5432)
                        + "/"
                        + database.getDatabaseName());
        registry.add("spring.r2dbc.username", database::getUsername);
        registry.add("spring.r2dbc.password", database::getPassword);
    }

    @Autowired
    WebTestClient client;

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void createsCustomerAndPersistsIt() {
        CreateCustomerRequest request =
                new CreateCustomerRequest(
                        "integration@example.test",
                        "Integration Customer");

        EntityExchangeResult<CustomerResponse> result =
                client.post()
                        .uri("/api/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .bodyValue(request)
                        .exchange()
                        .expectStatus().isCreated()
                        .expectBody(CustomerResponse.class)
                        .returnResult();

        CustomerResponse response = result.getResponseBody();

        assertThat(response).isNotNull();
        assertThat(response.id()).isNotNull();

        StepVerifier.create(customerRepository.findById(response.id()))
                .assertNext(saved -> {
                    assertThat(saved.getEmail())
                            .isEqualTo("integration@example.test");
                    assertThat(saved.getFullName())
                            .isEqualTo("Integration Customer");
                })
                .verifyComplete();

        client.get()
                .uri("/api/customers/{id}", response.id())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(response.id())
                .jsonPath("$.email")
                    .isEqualTo("integration@example.test");
    }
}
~~~

Đây là khung tích hợp. Test thực tế cần import DTO/entity/repository của dự án, cấu hình schema hoặc migration, cleanup dữ liệu và điều chỉnh assertion theo API contract. Không cần mock repository trong test này vì mục tiêu là đi qua database thật.

## 24. Checklist triển khai theo trình tự

Khi xây dựng API integration test với R2DBC, đi theo thứ tự:

1. Chọn database test riêng và đúng engine với production.
2. Chọn R2DBC driver và version tương thích Spring Boot/Spring Data.
3. Cấu hình Testcontainers hoặc test database bên ngoài.
4. Khởi tạo application context với profile test.
5. Cung cấp R2DBC URL và credential qua dynamic properties.
6. Chạy migration/schema initializer trước khi test gửi request.
7. Inject WebTestClient và chọn RANDOM_PORT nếu cần HTTP server thật.
8. Tạo fixture bằng repository hoặc DatabaseClient và chờ hoàn tất.
9. Gửi HTTP request, kiểm tra status/header/body.
10. Đọc lại database để xác nhận insert/update/delete.
11. Kiểm tra validation, constraint, not-found, security và transaction rollback.
12. Kiểm tra stream/cancellation nếu API trả Flux hoặc SSE.
13. Cleanup dữ liệu bằng cách có thể await.
14. Cô lập test song song và không dùng chung production data.
15. Chạy trong CI với database version và cấu hình gần production.

## 25. Ghi nhớ

- WebTestClient kiểm tra HTTP request/response nhưng phạm vi phụ thuộc cách bind: controller, application context hay server thật.
- Kết hợp @SpringBootTest với RANDOM_PORT và WebTestClient khi cần kiểm tra full HTTP stack cùng database.
- Testcontainers cung cấp database engine thật; hãy dùng đúng engine và version phù hợp production.
- Đăng ký R2DBC URL, username và password bằng DynamicPropertySource khi container cấp host/port động.
- Chạy migration/schema initializer trước khi test API.
- Assert cả HTTP response và dữ liệu persistence; status 201 không tự chứng minh row được lưu đúng.
- Dùng ID do database trả về, không đoán ID hoặc dùng SELECT MAX(id).
- @Transactional trên test method không tự bao bọc transaction của request HTTP được server xử lý.
- Cleanup reactive phải được chờ hoàn tất; không gọi subscribe() tách rời trong lifecycle method.
- Test security cần phân biệt mock authentication với việc xác thực token thật.
- Dùng StepVerifier để kiểm tra Flux/SSE, completion, error và cancellation.
- Kiểm thử constraint và transaction rollback bằng database thật, không chỉ mock exception.
- Không dùng H2 làm bằng chứng tương thích cho SQL, type, locking hoặc transaction của database production.
- Test song song cần database/schema/namespace riêng hoặc giới hạn parallelism.
- Giữ test database ephemeral, credential riêng và không đưa dữ liệu production nhạy cảm vào fixture.

