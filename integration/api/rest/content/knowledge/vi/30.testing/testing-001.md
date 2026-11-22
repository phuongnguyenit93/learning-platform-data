# Phân chia unit test, controller test, integration test và end-to-end test

Một REST API có thể trả `201 Created` trong bài kiểm thử controller, nhưng thực tế lại không tạo được đơn hàng vì migration database sai. Ngược lại, một bài kiểm thử gọi service thật và lưu được đơn hàng không chứng minh rằng HTTP response có `Location` chính xác, request không hợp lệ trả `400` hay người dùng không có quyền nhận `403`. Vì vậy, muốn kiểm thử API hiệu quả, trước tiên phải **chọn đúng ranh giới của mỗi bài kiểm thử**.

Bài học nằm trong chương **Kiểm thử** của mô-đun **INTEGRATION_API_REST**. Người học đã làm việc với resource, URI, phương thức và mã trạng thái HTTP, hợp đồng dữ liệu, phân trang, cache, idempotency, OpenAPI, xác thực và phân quyền. Chúng ta sẽ dùng một API đặt hàng làm ví dụ xuyên suốt để phân chia trách nhiệm giữa **unit test**, **controller test**, **integration test** và **end-to-end test (E2E)** bằng Java, JUnit 5, Spring MVC/Security, MockMvc và Testcontainers.

## 1. Mục tiêu: kiểm tra đúng thứ cần kiểm tra

Sau bài này, người học có thể:

1. Nêu rõ **thành phần nào chạy thật, thành phần nào được thay thế và điều gì được chứng minh** ở từng mức kiểm thử.
2. Viết unit test cho quy tắc nghiệp vụ thuần Java; controller test cho HTTP contract, validation, serialization và security behavior; integration test với repository, transaction và database thật; E2E test đi qua cửa vào ứng dụng và những dịch vụ cần thiết.
3. Chọn dữ liệu kiểm thử, test double, fixture và assertions sao cho bài kiểm thử phát hiện lỗi có ý nghĩa thay vì chỉ xác nhận cách mock được cấu hình.
4. Lập ma trận kiểm thử cho success/error, 401/403, paging, cache, optimistic concurrency, idempotency và các request đồng thời.
5. Phân bố bộ test trong CI/CD để có phản hồi nhanh mà vẫn kiểm soát được rủi ro ở môi trường triển khai.

**Nguyên tắc phân loại:** mức kiểm thử được xác định bởi **ranh giới hệ thống và phụ thuộc thực tế**, không chỉ bởi tên thư viện. Cùng dùng MockMvc, một bài `@WebMvcTest` với service mock thường là controller test, còn một bài `@SpringBootTest` với toàn bộ bean, database và filter chain thật có thể là integration test.

## 2. Ví dụ xuyên suốt: tạo đơn hàng

Giả sử hệ thống cung cấp API:

~~~http
POST /api/v1/orders HTTP/1.1
Authorization: Bearer <valid-access-token>
Idempotency-Key: "req-9b1"
Content-Type: application/json

{
  "skuId": "11111111-1111-4111-8111-111111111111",
  "quantity": 2
}
~~~

Khi người gọi có quyền và kho còn hàng, API ghi nhận đơn trong database, giữ tồn kho rồi trả:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/8c9b4ca4-2211-4cd0-a949-d176bcb8e35f
Content-Type: application/json

{
  "id": "8c9b4ca4-2211-4cd0-a949-d176bcb8e35f",
  "status": "PENDING"
}
~~~

Một số yêu cầu nghiệp vụ và HTTP khác:

- `quantity` phải lớn hơn 0; JSON sai cấu trúc hoặc dữ liệu không hợp lệ bị từ chối.
- Người gọi cần quyền `orders.create` và chỉ được đặt hàng trong phạm vi tenant phù hợp.
- Nếu tồn kho không đủ thì không tạo đơn hoặc giữ hàng dở dang.
- Hai request đồng thời không được giữ cùng một sản phẩm cuối cùng hai lần.
- Retry bằng cùng `Idempotency-Key` và cùng payload không được tạo hai đơn.
- Response thành công phải có mã HTTP, JSON, header và URI theo hợp đồng OpenAPI.

Đây là nhiều loại rủi ro khác nhau. Không nên ép một bài kiểm thử chạy từ trình duyệt qua mọi dịch vụ để xác minh từng nhánh của phép tính số lượng; cũng không nên dùng unit test để tuyên bố rằng database, JWT hay cấu hình gateway đã hoạt động.

### Bốn lớp kiểm thử và phần chúng bao phủ

~~~mermaid
flowchart TB
    E["End-to-end: client → cổng công khai → ứng dụng → dịch vụ cần thiết"] --> I["Integration: nhiều thành phần thật + DB/broker/HTTP dependency có kiểm soát"]
    I --> C["Controller: routing + JSON + validation + HTTP/security filter"]
    C --> U["Unit: hàm/lớp nghiệp vụ ở phạm vi hẹp"]
~~~

Sơ đồ thể hiện **phạm vi tăng dần**, không phải một thứ tự bắt buộc chạy test hay một quan hệ kế thừa giữa các framework. Controller test là một kiểu test ở ranh giới web; integration test có thể kiểm thử service và database **không đi qua controller**. End-to-end test có thể bắt đầu từ trình duyệt hoặc HTTP client tùy sản phẩm.

## 3. Ma trận phân chia trách nhiệm

| Mức | Thành phần chạy thật | Thường thay thế hoặc kiểm soát | Cần chứng minh | Chưa chứng minh |
| --- | --- | --- | --- | --- |
| **Unit test** | Một hàm/class hoặc một nhóm rất nhỏ; quy tắc nghiệp vụ | Database, clock, random, network, repository khi cần | Quy tắc, nhánh biên, tính toán, quyết định nghiệp vụ | Routing, JSON, Spring proxy, SQL thật, TLS |
| **Controller test** | Spring MVC slice: mapping, binding, validation, JSON serializer, advice, security filter nếu bật | Application service, repository, database | HTTP method/path, body/headers, response, lỗi 400/401/403, request được chuyển đúng | Commit transaction, schema DB, broker, reverse proxy |
| **Integration test** | Bean Spring cần thiết và ít nhất một ranh giới tích hợp thật: JPA+DB, transaction, serialization+service, broker... | Dịch vụ bên ngoài không thuộc mục tiêu có thể dùng stub/fixture | Query, migration, transaction, constraint, locking, cấu hình bean, mapping giữa thành phần | Hành trình đầy đủ qua ingress, UI, cấu hình staging |
| **End-to-end test** | Đường sử dụng công khai và các thành phần cần thiết để hoàn tất luồng | Thường dùng môi trường test, tài khoản test; chỉ stub ngoài ranh giới chủ đích | Luồng hành động người dùng/consumer, auth, routing, deploy, trạng thái quan sát được | Mọi trường hợp biên của mọi lớp hoặc chứng minh hệ thống không có lỗi |

| Tiêu chí vận hành | Unit | Controller | Integration | E2E |
| --- | --- | --- | --- | --- |
| Tốc độ mong đợi | Rất nhanh | Nhanh đến vừa | Vừa đến chậm | Thường chậm nhất |
| Khả năng cô lập lỗi | Cao | Cao tại web boundary | Trung bình, nhiều thành phần | Thấp hơn, lỗi có thể ở nhiều hop |
| Độ ổn định nếu viết tốt | Rất cao | Cao | Phụ thuộc DB/container/fixture | Dễ flake vì network, UI và bất đồng bộ |
| Chi phí bảo trì | Thấp cho logic ổn định | Vừa, theo contract HTTP | Vừa/cao, theo schema và môi trường | Cao hơn, theo luồng, dữ liệu, tích hợp |
| Tần suất chạy | Mỗi thay đổi | Mỗi thay đổi | CI của PR và main | Một số luồng quan trọng mỗi PR hoặc trước/sau deploy |

Các so sánh là **xu hướng**, không phải ngưỡng thời gian hay tỷ lệ test bắt buộc. Một controller test khởi động cả application context có thể chậm hơn một integration test tối giản; một E2E qua API đơn giản có thể nhanh hơn test database phức tạp.

## 4. Unit test: quyết định nghiệp vụ không phụ thuộc hạ tầng

Unit test kiểm tra **đầu vào → quyết định/đầu ra của một đơn vị logic**. Nếu có thể tách một quy tắc kinh doanh thành Java thuần, hãy kiểm thử nó mà không khởi tạo Spring context, không HTTP và không database. Ví dụ phép tính lượng hàng còn lại:

~~~java
public final class InventoryPolicy {
    private InventoryPolicy() {}

    public static int remaining(int available, int requested) {
        if (available < 0 || requested <= 0) {
            throw new IllegalArgumentException("Số lượng không hợp lệ");
        }
        if (requested > available) {
            throw new InsufficientStockException();
        }
        return available - requested;
    }
}

public final class InsufficientStockException extends RuntimeException {}
~~~

JUnit 5 + AssertJ:

~~~java
class InventoryPolicyTest {

    @Test
    void reservationReducesAvailableQuantity() {
        assertThat(InventoryPolicy.remaining(5, 2)).isEqualTo(3);
    }

    @ParameterizedTest
    @CsvSource({"0,1", "1,2", "3,4"})
    void notEnoughStockIsRejected(int available, int requested) {
        assertThatThrownBy(() ->
            InventoryPolicy.remaining(available, requested))
            .isInstanceOf(InsufficientStockException.class);
    }

    @Test
    void nonPositiveQuantityIsRejected() {
        assertThatThrownBy(() -> InventoryPolicy.remaining(10, 0))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Các import JUnit Jupiter, `org.junit.jupiter.params` và AssertJ được lược bớt để tập trung vào ý tưởng. Kết quả chỉ chứng minh quy tắc của `InventoryPolicy`; nó **không** chứng minh hai request đồng thời không bán vượt tồn kho. Điều đó cần kiểm tra SQL có điều kiện/locking và transaction ở integration test.

### Unit test cho service có dependency

Nếu application service dùng repository, có thể đặt Mockito mock tại những **cổng phụ thuộc**:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderApplicationServiceTest {
    @Mock InventoryGateway inventory;
    @Mock OrderWriter orderWriter;
    @InjectMocks OrderApplicationService orders;

    @Test
    void insufficientStockDoesNotWriteOrder() {
        UUID sku = UUID.randomUUID();
        when(inventory.tryReserve(sku, 2)).thenReturn(false);

        assertThatThrownBy(() -> orders.create(sku, 2))
            .isInstanceOf(InsufficientStockException.class);

        verify(orderWriter, never()).save(any());
    }
}
~~~

Đây là ví dụ phác thảo interface `InventoryGateway`, `OrderWriter` và chữ ký service tương ứng, không nhằm thay thế code cấu trúc của dự án. Mockito giúp điều khiển tình huống hiếm như “kho từ chối giữ hàng”. Nhưng mock trả `true` cho `tryReserve` **không chứng minh câu SQL đã khóa đúng row**, và việc mock toàn bộ service rồi verify số lần gọi có thể làm bài test quá phụ thuộc chi tiết cài đặt. Ưu tiên assert **hành vi và kết quả**; chỉ verify interaction khi chính việc không gọi dependency hoặc không gây side effect là yêu cầu nghiệp vụ.

Unit test nên bao phủ giá trị biên, dữ liệu rỗng, số âm/overflow, chuẩn hóa dữ liệu, chuyển trạng thái và điều kiện phân quyền nội bộ. Các nguồn không ổn định như thời gian, sinh ID, tỷ giá, random hoặc quyết định từ external service nên được đưa qua `Clock`, generator hoặc interface để có kết quả lặp lại được. Tránh dùng `Thread.sleep` hoặc `Instant.now()` trực tiếp trong assertion cần tính quyết định.

## 5. Controller test: hợp đồng HTTP và tầng web

Controller test trả lời: **route có tồn tại và nhận đúng request không; validation có tạo status đúng không; JSON/header có đúng contract không; luồng security ở tầng web có được kiểm tra không?** Với Spring MVC, `@WebMvcTest` nạp một phần application context tập trung vào MVC thay vì khởi động toàn bộ dịch vụ và database.

Giả sử controller:

~~~java
public record PlaceOrderRequest(
    @NotNull UUID skuId,
    @Min(1) int quantity) {}

public record OrderReceipt(UUID id, String status) {}

@RestController
@RequestMapping("/api/v1/orders")
class OrderController {
    private final OrderApplicationService orders;

    OrderController(OrderApplicationService orders) {
        this.orders = orders;
    }

    @PostMapping
    ResponseEntity<OrderReceipt> create(
            @Valid @RequestBody PlaceOrderRequest body,
            Authentication authentication) {
        OrderReceipt receipt =
            orders.placeOrder(authentication.getName(), body);

        return ResponseEntity
            .created(URI.create("/api/v1/orders/" + receipt.id()))
            .body(receipt);
    }
}
~~~

### 5.1. Test HTTP status, Location, JSON và input validation

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired MockMvc mvc;
    @MockitoBean OrderApplicationService orders;

    @Test
    void validRequestReturnsCreatedAndLocation() throws Exception {
        UUID sku = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        UUID orderId = UUID.fromString(
            "8c9b4ca4-2211-4cd0-a949-d176bcb8e35f");
        when(orders.placeOrder(eq("alice"), any(PlaceOrderRequest.class)))
            .thenReturn(new OrderReceipt(orderId, "PENDING"));

        mvc.perform(post("/api/v1/orders")
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"skuId":"11111111-1111-4111-8111-111111111111",
                     "quantity":2}
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                "Location", "/api/v1/orders/" + orderId))
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.status").value("PENDING"));
    }

    @Test
    void invalidQuantityReturnsBadRequestBeforeCallingService()
            throws Exception {
        mvc.perform(post("/api/v1/orders")
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"skuId":"11111111-1111-4111-8111-111111111111",
                     "quantity":0}
                    """))
            .andExpect(status().isBadRequest());

        verifyNoInteractions(orders);
    }
}
~~~

Ví dụ dùng Spring Boot có `spring-boot-starter-validation`, `spring-security-test`, JUnit, Mockito và static import MockMvc/AssertJ phù hợp. `@MockitoBean` thuộc Spring Framework 6.2 (thường đi cùng Spring Boot 3.4 trở lên); với bản Spring Boot 3 cũ hơn, project có thể còn dùng `@MockBean` của Spring Boot. Chọn annotation theo phiên bản dự án; không trộn hai cơ chế một cách tùy tiện.

`with(user("alice"))` tạo principal test để gửi request qua filter chain; việc test này thành công giả định cấu hình security của slice chấp nhận người dùng tương ứng. Một project kiểm tra scope/role sẽ cần thêm authority hoặc import `SecurityFilterChain` test phù hợp. **Không dùng test trên để tuyên bố JWT signature, issuer, audience hay cấu hình gateway đã được kiểm tra**: người dùng ở đây được giả lập.

### 5.2. Controller slice phải kiểm tra đúng những gì thuộc HTTP

| Contract cần thử | Ví dụ kỳ vọng | Vì sao thuộc controller test |
| --- | --- | --- |
| Routing và method | `POST /orders` hợp lệ; method không hỗ trợ có thể trả `405` | Kiểm tra mapping Spring MVC |
| Deserialize JSON | UUID sai định dạng → `400` | Kiểm tra Jackson/message converter |
| Bean Validation | `quantity=0` → `400` | Kiểm tra `@Valid` và validation |
| Content negotiation | `Accept`/`Content-Type` không hỗ trợ → `406`/`415` khi phù hợp | Hợp đồng representation |
| Response thành công | `201`, `Location`, JSON field chính xác | Hợp đồng client nhìn thấy |
| Error mapping | Domain exception → `409` hoặc Problem Details | Kiểm tra `@ControllerAdvice` |
| Authentication/authorization tại web | Thiếu principal → `401`, thiếu permission → `403` theo policy | Spring Security filter/method policy nếu được bật trong slice |
| Cache/ETag | `Cache-Control`, `ETag`, `304`/`412` khi có hỗ trợ | Hành vi HTTP; điều kiện DB thực cần integration test |
| CORS | Allowed Origin nhận header, origin lạ không được cấp quyền đọc | Hợp đồng browser do MVC/security cấu hình |

Điểm quan trọng với error handler: nếu muốn biết `InsufficientStockException` trở thành `409 Conflict` có cấu trúc `application/problem+json`, bạn có thể cho service mock ném exception rồi assert response. Không cần khởi động PostgreSQL để kiểm tra một ánh xạ HTTP đơn giản.

Đừng tắt mọi filter bằng `@AutoConfigureMockMvc(addFilters = false)` và sau đó gọi bài test đó là bằng chứng rằng authentication/CSRF/CORS được bảo vệ. Nếu dùng cấu hình bỏ filter để tập trung vào mapping, phải có test security riêng thực thi filter chain thật. Tương tự, `@WebMvcTest` có thể không nạp hết security configuration và bean của toàn ứng dụng; test phải khai báo chính sách cần kiểm tra trong slice.

## 6. Integration test: tương tác giữa các thành phần thật

Integration test nhắm vào **ranh giới kết nối** mà mock không mô phỏng chính xác được: JPA mapping, SQL, constraint, transaction, database isolation, migration, serialization thực giữa các bean, broker hoặc REST client. Có hai kiểu điển hình:

1. **Slice integration** với `@DataJpaTest` + database phù hợp: tập trung vào entity/repository, query, constraint, không nạp toàn bộ web stack.
2. **Application integration** với `@SpringBootTest`: nạp các bean thật và kiểm tra một hoặc nhiều use case qua service hoặc HTTP. Có thể dùng `@AutoConfigureMockMvc` để chạy qua Spring MVC filter chain mà **không mở port thật**, hoặc `webEnvironment = RANDOM_PORT` để mở HTTP socket.

Lựa chọn kiểu nào dựa vào rủi ro cần chứng minh. Bài test service+database không cần gọi HTTP khi mục tiêu là rollback; bài test full stack HTTP có thể cần để xác minh transaction và status cùng nhau.

### 6.1. Dùng database cùng loại với production khi SQL/locking quan trọng

Một database in-memory như H2 hữu ích cho bài tập đơn giản nhưng không bảo đảm tương thích với PostgreSQL/MySQL/Oracle về kiểu dữ liệu, migration, khóa row, isolation, JSON column, SQL dialect và constraint. Với API có tranh chấp hoặc native query, nên dùng **Testcontainers** để chạy engine gần môi trường thật:

~~~java
@Testcontainers
@SpringBootTest
class OrderTransactionIT {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired OrderApplicationService orders;
    @Autowired InventoryRepository inventory;
    @Autowired OrderRepository repository;

    @Test
    void insufficientStockDoesNotCreateOrder() {
        // Fixture độc lập: tenant-a, sku-1 còn một sản phẩm.
        // currentTenant trong test phải xác thực tenant-a.
        UUID sku = TestFixtures.skuWithAvailableQuantity(1);
        long beforeOrders = repository.count();

        assertThatThrownBy(() ->
            orders.placeOrder("alice", new PlaceOrderRequest(sku, 2)))
            .isInstanceOf(InsufficientStockException.class);

        assertThat(repository.count()).isEqualTo(beforeOrders);
        assertThat(inventory.availableQuantity("tenant-a", sku))
            .isEqualTo(1);
    }
}
~~~

Đoạn mã này là **khung tích hợp**, giả định dự án có `TestFixtures`, repository helper và service như ví dụ. `@ServiceConnection` hỗ trợ khai báo kết nối từ container ở Spring Boot 3.1 trở lên, cùng dependency Testcontainers và Docker runtime; bản cũ hơn có thể dùng `@DynamicPropertySource`. Migrations (Flyway/Liquibase) cần chạy trên database test nếu deployment cũng dùng migration.

Muốn chứng minh rollback khi **lỗi xảy ra sau một lệnh ghi**, hãy cố ý khiến bước lưu đơn vi phạm unique constraint sau khi cập nhật tồn kho, rồi kiểm tra cả hai bảng. Lỗi phát ra tại `flush` hoặc `commit` đều phải được xử lý đúng; chỉ kiểm tra trường hợp kho không đủ (lỗi trước bước ghi) **chưa chứng minh rollback**. Cần test riêng cho các nhánh thất bại giữa transaction.

**Cảnh báo đặc biệt:** `@Transactional` trên chính phương thức test có thể khiến test cuối cùng rollback toàn bộ, che mất lỗi commit/transaction boundary của code sản xuất. Với bài test rollback/commit, tránh bọc toàn test trong transaction và quan sát dữ liệu sau lời gọi service qua một transaction độc lập hoặc connection khác. Đồng thời chắc chắn service được gọi qua Spring proxy để `@Transactional` có hiệu lực.

### 6.2. Test migration, uniqueness và concurrency

Tối thiểu, integration test cần trả lời:

- Mapping entity, relation, index và migration khởi tạo được schema thực tế?
- `UNIQUE (tenant_id, customer_id, client_reference)` ngăn trùng dưới concurrent request?
- `UPDATE inventory SET available = available - :qty WHERE available >= :qty` có ngăn bán vượt kho, kể cả hai transaction cùng chạy?
- Lỗi ở bước lưu thứ hai có rollback bước ghi thứ nhất?
- Repository query có **lọc tenant** và không trả bản ghi của người dùng khác?
- Optimistic locking `@Version` hoặc điều kiện `If-Match` có chặn lost update?
- Một outbox event và trạng thái nghiệp vụ có cùng commit không; worker retry có gây xử lý trùng không?

Với SKU còn một sản phẩm, test chạy hai request song song qua service thật với `clientReference` khác nhau, dùng barrier để chúng bắt đầu gần nhau; kết quả phải cho thấy chỉ một request giữ được hàng, và tồn kho cuối không âm. Dữ liệu cần được seed ở database thật và cleanup theo namespace riêng. Không dựa duy nhất vào việc test chạy 100 lần đều pass: cần bảo vệ bằng **atomic SQL, constraint và cơ chế locking được hiểu rõ**.

### 6.3. Tích hợp với hệ thống bên ngoài

Khi test HTTP client của ứng dụng, có thể chạy một stub server như WireMock/MockWebServer để kiểm tra URL, method, timeout, retry và JSON contract, đồng thời chủ động trả `429`, `500`, kết nối đứt hoặc response trễ. Tại mức này, bạn đang kiểm tra **tích hợp phía mình với hợp đồng mô phỏng của đối tác**, chưa khẳng định đối tác thực sẽ luôn hoạt động như stub.

Đối với Kafka/RabbitMQ/Redis, ưu tiên container hoặc môi trường test riêng cho các hành vi khó mô phỏng: ack, delivery trùng, TTL, ordering, redelivery và transaction/outbox. Mọi kiểm thử liên quan network, broker hoặc database phải được đo ở môi trường có điều kiện gần thật; unit test vẫn phù hợp cho policy xử lý event thuần Java.

## 7. End-to-end: hành trình qua giao diện công khai

E2E test phải mô phỏng một **hành trình thực tế** từ điểm mà client sử dụng sản phẩm. Với API-first, client có thể là REST client dùng token thật của môi trường test; với ứng dụng web, hành trình có thể bắt đầu từ trang đăng nhập, nhấn “Đặt hàng”, kiểm tra trang kết quả và quan sát tài nguyên qua API.

~~~mermaid
sequenceDiagram
    participant C as Test client / Browser
    participant G as Gateway
    participant A as Deployed API
    participant D as Database
    participant W as Worker / Broker
    C->>G: Đăng nhập, tạo đơn qua HTTPS
    G->>A: Chuyển tiếp request
    A->>D: Commit order + outbox
    A-->>G: 201 Created / 202 Accepted
    G-->>C: Status + Location
    D->>W: Xử lý outbox, nếu có
    C->>G: GET /orders/{id} hoặc /jobs/{id}
    G->>A: Truy vấn trạng thái
    A-->>C: PENDING / CONFIRMED theo workflow
~~~

Một luồng E2E có thể gồm:

1. Lấy session/access token bằng cơ chế đăng nhập **của môi trường kiểm thử**; không hardcode secret vào repository.
2. Gửi `POST /api/v1/orders` qua **public base URL** và kiểm tra `201 Created` hoặc `202 Accepted` theo hợp đồng.
3. Đọc `Location` hoặc ID được trả về; gọi `GET` để xác minh tài nguyên thuộc đúng principal/tenant.
4. Nếu xử lý async, poll với giới hạn thời gian/backoff và xác minh kết quả eventual; không dùng sleep cố định thiếu điều kiện dừng.
5. Gửi lại cùng idempotency key và payload, xác minh không tạo đơn thứ hai.
6. Cleanup bằng API quản trị dành cho môi trường test hoặc dữ liệu có TTL; không để E2E phá dữ liệu dùng chung.

Ví dụ các lệnh smoke test, giả định đã có token test và API đang triển khai:

~~~bash
curl -i -X POST "https://staging-api.example.test/api/v1/orders" \
  -H "Authorization: Bearer <test-access-token>" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: "e2e-order-unique-001"' \
  --data '{"skuId":"11111111-1111-4111-8111-111111111111","quantity":1}'

curl -i "https://staging-api.example.test/api/v1/orders/<returned-order-id>" \
  -H "Authorization: Bearer <test-access-token>"
~~~

`<test-access-token>` và `<returned-order-id>` chỉ là ký hiệu minh họa; script E2E thật phải xử lý JSON/header, trạng thái thất bại, cleanup và dữ liệu test riêng. Không ghi token vào console log/CI artifact; không tái sử dụng cùng idempotency key với payload thay đổi. API E2E không có browser thì **không chứng minh** cookie `SameSite`, CSRF browser, CORS implementation trong trình duyệt hoặc giao diện người dùng; khi các rủi ro đó có ý nghĩa, thêm E2E bằng Playwright/Selenium trên browser thật.

E2E rất có giá trị để bắt lỗi “chỉ xảy ra khi ghép hệ thống”: route gateway sai, TLS/certificate sai hostname, biến môi trường thiếu, JWT audience không khớp, CORS chặn frontend, schema chưa migrate, message bị mất hoặc callback không kết nối được. Nhưng E2E quá rộng thường khó tìm nguyên nhân khi thất bại; giữ số luồng E2E ở mức hợp lý, tập trung hành trình quan trọng, và để các mức thấp hơn bao phủ nhánh nhỏ.

## 8. Thiết kế ma trận REST API theo rủi ro

Thay vì hỏi “phải có bao nhiêu phần trăm unit test?”, hãy hỏi “**mỗi rủi ro cần chứng minh ở lớp nào rẻ và đáng tin nhất?**”. Ma trận sau minh họa quyết định:

| Rủi ro / yêu cầu | Test chính | Test bổ sung | Tiêu chí thành công |
| --- | --- | --- | --- |
| Quy tắc `quantity > 0` trong domain | Unit | Controller validation | Dữ liệu xấu không tạo đơn |
| JSON sai loại/thiếu trường, content type | Controller | E2E smoke vài mẫu | `400`/`415` và lỗi định dạng nhất quán |
| `POST` trả `201` + `Location` | Controller | E2E | Client có thể dùng Location tìm resource |
| Exception → Problem Details | Controller | Integration cho lỗi DB thật | Status, `type`, `title`, `status`, media type chính xác |
| Token không có hoặc không hợp lệ | Controller/security integration | E2E token thật | `401`; không thay đổi dữ liệu |
| Có token nhưng thiếu scope/quyền | Controller/security integration | E2E một tuyến nhạy cảm | `403`; không có side effect |
| BOLA/cross-tenant | Integration | E2E cho đường rủi ro cao | Tenant A không đọc/sửa bản ghi của B |
| Đủ/thiếu tồn kho | Unit cho policy, integration cho SQL | E2E happy path | Bất biến kho đúng sau commit |
| Race khi chỉ còn một sản phẩm | Integration với database thật | Kiểm thử tải chọn lọc | Chỉ một đơn thành công, không âm kho |
| Unique/idempotency key | Integration với DB thật | E2E retry sau timeout giả lập | Cùng key/payload chỉ một hiệu ứng |
| Phân trang/sắp xếp | Controller cho tham số, integration cho query | E2E một hành trình collection | Limit, cursor/page, sort ổn định, không trùng/thiếu |
| Cache/ETag/If-Match | Controller cho header, integration cho version | E2E qua gateway/CDN khi cần | `304`/`412`/`428` theo contract, không trả stale data trái phép |
| Outbox và consumer retry | Integration với DB/broker | E2E eventual status | Không mất event khi commit; duplicate không gây side effect lặp |
| HTTPS/HSTS/CORS/proxy | Integration cấu hình web | E2E qua ingress/browser thật | Header, cert, origin, reverse proxy đúng |
| OpenAPI schema | Contract/controller | Consumer-driven contract/E2E smoke | Client/server không lệch URI, field, status |

Một tính năng thường cần **nhiều mức test bổ trợ**. Chẳng hạn tạo đơn yêu cầu unit test tính toán, controller test hợp đồng `POST`, integration test atomic transaction và E2E test chứng minh đường từ client tới database hoạt động. Không phải mỗi test đều cần lặp lại toàn bộ assertion ở tất cả các mức.

### 8.1. Test âm tính phải quan sát cả side effect

Chỉ assert `403` không bảo đảm controller/service chưa ghi DB rồi mới trả lỗi. Với hành động nhạy cảm, kiểm tra trạng thái sau request: số đơn không đổi, tồn kho không đổi, không có job mới và không phát event trái phép. Điều này đặc biệt quan trọng với authorization, CSRF, idempotency và lỗi transaction.

### 8.2. Phân trang và cache cần kiểm tra tính ổn định

Nếu `GET /api/v1/orders?limit=20&cursor=...` dùng keyset pagination, test query thật phải bao phủ dữ liệu trùng trường sort, bản ghi cùng thời điểm và thứ tự tie-breaker. Controller test chỉ chứng minh parse/default/validation của `limit`, `cursor`. Với cache, header `Cache-Control` và `ETag` có thể được kiểm tra ở MVC; hành vi shared cache hoặc CDN, xử lý `Vary` và dữ liệu theo tenant cần được kiểm tra tại tầng tích hợp/triển khai tương ứng.

### 8.3. Contract test không thay thế toàn bộ E2E

OpenAPI validation và consumer-driven contract hữu ích để phát hiện đổi tên field, enum, response code, header hoặc backward incompatibility. Chúng nhanh hơn việc phải chạy toàn bộ hành trình phân tán và có thể đưa vào PR. Tuy nhiên, schema match **không chứng minh** database đã commit, phân quyền đúng đối tượng, event được chuyển thành công hay API được route tới phiên bản deployment đúng.

## 9. Tổ chức test double và dữ liệu kiểm thử

### 9.1. Fake, stub, mock: dùng cho mục đích khác nhau

| Loại | Vai trò | Ví dụ |
| --- | --- | --- |
| **Stub** | Trả dữ liệu/response đã định để điều khiển tình huống | HTTP server trả `503` cho client retry |
| **Fake** | Cài đặt đơn giản nhưng có hành vi hoạt động | Repository in-memory cho một thuật toán |
| **Mock** | Ghi/kiểm tra tương tác với dependency | Mockito xác minh không gọi `paymentClient.charge()` |
| **Spy** | Bọc đối tượng thật và quan sát/chỉnh một phần hành vi | Quan sát callback khi cần, dùng tiết chế |
| **Real dependency** | Chạy thành phần thực để kiểm tra tương tác | PostgreSQL Testcontainers, Redis, broker |

Không mock thứ **chính bạn đang muốn kiểm tra**. Nếu muốn chứng minh query lọc tenant, không mock repository. Nếu muốn chứng minh JWT validator kiểm tra `issuer`/`audience`/chữ ký, test dùng `with(jwt())` của Spring Security Test chưa đủ, vì nó đưa principal giả vào context; cần test decoder với token hợp lệ và không hợp lệ hoặc một integration test theo luồng xác thực thật.

### 9.2. Fixture và cô lập dữ liệu

Dữ liệu test nên thể hiện rõ nghiệp vụ: `tenant-a`, `tenant-b`, hai tài khoản với quyền khác nhau, một SKU chỉ còn một đơn vị, một order đã được duyệt. Dùng fixture builder/factory với default hợp lệ và chỉ thay trường quan trọng trong test. Giá trị ID có thể cố định để dễ đọc, nhưng phải **tránh va chạm khi chạy song song**; namespace bằng ID riêng hoặc tạo dữ liệu theo test.

Chọn cơ chế cô lập tùy tầng: object mới cho unit, mock reset theo test cho controller, schema/database riêng hoặc cleanup transaction có chủ đích cho integration, test account/resource riêng và teardown cho E2E. Không xây test phụ thuộc “test A tạo dữ liệu trước để test B đọc”, vì chạy riêng hay song song sẽ thất bại.

Với thời gian, dùng `Clock.fixed(...)` hoặc test clock. Với async, chờ điều kiện đến deadline thay vì `Thread.sleep(5000)` cố định. Với ID/tên ngẫu nhiên, chỉ dùng randomness khi giúp cách ly; nếu test fail, cần in seed/correlation ID an toàn để tái hiện mà không lộ credential.

## 10. Tốc độ, độ tin cậy và cách chạy CI/CD

Một cách tổ chức thường dùng:

~~~mermaid
flowchart TD
    P["Pull request"] --> U["Unit + controller tests"]
    U --> I["Integration / contract tests"]
    I --> M{"Các gate qua?"}
    M -- "Không" --> F["Chặn merge, xem lỗi theo tầng"]
    M -- "Có" --> D["Deploy môi trường test"]
    D --> E["E2E smoke + security/route checks"]
    E --> R["Tiếp tục rollout nếu đạt tiêu chí"]
~~~

Thực tế có thể chạy các nhóm **song song** trong CI; sơ đồ thể hiện quan hệ gate. Nên cung cấp tên và metadata test để khi thất bại có thể biết lỗi ở logic, MVC, database hay đường triển khai. Sử dụng tag/suite như `unit`, `web`, `integration`, `e2e` nếu build tool của dự án hỗ trợ.

| Giai đoạn | Ưu tiên | Điều kiện để chạy ổn định |
| --- | --- | --- |
| Trên máy lập trình viên | Unit + controller cho phần code vừa đổi | Không phụ thuộc môi trường bên ngoài |
| PR | Tất cả unit, controller, contract và integration trọng yếu | Container/dữ liệu test được quản lý; không dùng service production |
| Main / build phát hành | Integration đầy đủ, test concurrency và luồng lỗi trọng yếu | Database/broker thực trong môi trường test |
| Sau triển khai staging | Một số E2E hành trình cốt lõi, HTTPS/auth/gateway/header | Test account, secret và cleanup riêng |
| Theo lịch / trước release lớn | E2E rộng hơn, performance, resilience và security chuyên sâu | Môi trường có dữ liệu/tải phù hợp, theo dõi và rollback |

Không đặt mục tiêu “100% test phải là unit” hoặc chỉ đo coverage dòng. Line coverage cao nhưng chỉ mock service rồi assert mock trả về không nói lên chất lượng. Khi chọn bổ sung test, ưu tiên những lỗi đã gặp trong production, hành động có side effect khó đảo ngược, các chỗ vừa đổi schema/authorization và những hành vi có tính cạnh tranh.

### 10.1. Nhận diện và xử lý flaky tests

Các nguyên nhân phổ biến:

- Dùng timeout/sleep cố định cho async, broker hoặc polling.
- Test đụng chung một user, DB row, port hoặc queue với test khác.
- Thứ tự thực thi ảnh hưởng kết quả vì singleton cache, static state hoặc transaction test còn sót.
- Phụ thuộc thời gian hệ thống, múi giờ, locale, random ID hoặc thứ tự không xác định của SQL.
- Test E2E chọn phần tử UI bằng selector không ổn định, kiểm tra ngay trước khi state eventual hoàn tất.
- HTTP stub không khớp chính xác request; test đi qua proxy thật trong khi fixture không sẵn sàng.

Khi flaky test thất bại, ghi lại request ID, trạng thái DB/queue và log đã loại bỏ thông tin nhạy cảm. Sửa nguyên nhân, không chỉ tăng timeout hoặc tự động retry toàn bộ test vô hạn. Quarantine test đang lỗi chỉ nên là biện pháp tạm có người chịu trách nhiệm và thời hạn khắc phục; không được coi gate đỏ là gate xanh một cách mặc định.

## 11. Quy trình viết test cho một endpoint mới

Giả sử đội phát triển thêm `PATCH /api/v1/orders/{id}` để hủy đơn:

1. **Nêu hợp đồng và bất biến:** ai được hủy, đơn ở trạng thái nào được hủy, có hoàn tồn kho không, cần `If-Match` hay idempotency không; kết quả hợp lệ trả status nào.
2. **Viết unit test:** policy trạng thái `PENDING → CANCELLED` hợp lệ, `SHIPPED → CANCELLED` bị từ chối; không cần mở DB để kiểm tra bảng chuyển trạng thái.
3. **Viết controller test:** route PATCH, JSON path, body/schema, `If-Match`, `412`/`409`/`204` theo contract, security filter/exception handler; service được mock ở lớp này.
4. **Viết integration test:** transaction cập nhật trạng thái và hoàn tồn kho phải cùng commit; cùng đơn bị hủy đồng thời không hoàn tồn hai lần; tenant khác không hủy được; DB constraint/version đúng.
5. **Chọn E2E:** một luồng từ client thật hủy đơn và đọc lại trạng thái, qua gateway/môi trường test; nếu có email/event, kiểm tra trạng thái eventual có chủ đích.
6. **Gắn test vào CI:** unit/controller chạy nhanh khi sửa code, integration chạy cùng schema thực tế, E2E trong pipeline có môi trường và dữ liệu ổn định.

Đối với bug production, nên thêm test ở **tầng thấp nhất tái hiện được nguyên nhân** rồi cân nhắc một test cao hơn nếu bug còn liên quan route/config/deploy. Ví dụ JSON field sai → controller/contract test; transaction ghi dở → integration test; ingress cắt mất header `Authorization` → E2E/infra smoke.

## 12. Bài tập thực hành

**Bài tập 1 — Phân loại và giải thích.** Một nhóm đã viết bốn test:

- A: gọi `InventoryPolicy.remaining(5, 2)` với JUnit, không có Spring.
- B: dùng `@WebMvcTest`, MockMvc, mock `OrderApplicationService`, assert `201` và `Location`.
- C: dùng `@SpringBootTest`, PostgreSQL Testcontainers, gọi service thật rồi kiểm tra tồn kho.
- D: gửi `POST /orders` vào staging qua gateway với token test, sau đó gọi `GET /orders/{id}`.

Hãy phân loại A/B/C/D; nêu một lỗi mỗi test có thể phát hiện và **một lỗi mà nó không có đủ bằng chứng để phát hiện**. Giải thích vì sao đổi `@WebMvcTest` thành `@SpringBootTest` có thể thay đổi mức kiểm thử dù vẫn dùng MockMvc.

**Bài tập 2 — Lập test matrix cho tạo đơn.** API `POST /api/v1/orders` cần xử lý request hợp lệ, `quantity=0`, JSON sai, token thiếu, không đủ quyền, tenant khác, thiếu hàng, request gửi lại cùng idempotency key, cùng key khác payload, hai request tranh SKU cuối cùng. Chọn tầng chính cho từng trường hợp, viết assertion HTTP/status/data và quyết định dependency nào cần chạy thật.

**Bài tập 3 — Viết controller test Spring.** Tạo `OrderController` nhận `PlaceOrderRequest` có `@Valid`. Dùng `@WebMvcTest` để xác minh `201`, `Location`, JSON status, `400` cho quantity không hợp lệ và ánh xạ `InsufficientStockException` sang Problem Details `409`. Đảm bảo bài test không dựa vào PostgreSQL; nếu tạm vô hiệu hóa filter để tập trung MVC, hãy bổ sung security test tương ứng có filter thật.

**Bài tập 4 — Kiểm thử rollback và concurrency.** Dùng PostgreSQL Testcontainers và service `@Transactional`. Một test gây lỗi insert đơn **sau** khi giữ hàng; một test tạo hai request đồng thời khi kho còn một sản phẩm. Quan sát dữ liệu sau service call từ transaction độc lập; chứng minh không có đơn/tồn kho dở dang và không có hai request cùng giữ một đơn vị hàng.

**Bài tập 5 — Thiết kế E2E đáng tin cậy.** Viết kịch bản tạo đơn qua HTTPS staging, đọc `Location`, xác minh resource, retry bằng cùng key và cleanup. Thêm negative test cho token sai audience hoặc route admin thiếu permission. Quy định cách quản lý token, ID của fixture, deadline cho xử lý async và loại thông tin log được phép ghi khi thất bại.

### Tiêu chí hoàn thành

Lời giải đạt khi: (1) phân loại test theo ranh giới chạy thật; (2) mỗi yêu cầu nghiệp vụ/HTTP được gán tầng kiểm thử có căn cứ; (3) test web kiểm tra contract mà không lẫn hành vi mock với kết quả database; (4) integration test chứng minh commit, rollback, constraint và concurrency trên DB phù hợp; (5) E2E đi qua điểm truy cập công khai và sử dụng dữ liệu độc lập; (6) các test bị từ chối kiểm tra **không có side effect**; (7) bộ CI có thể chạy lặp lại mà không phụ thuộc thứ tự.

## 13. Checklist review bộ kiểm thử REST API

- [ ] Tên test mô tả hành vi/kết quả có thể quan sát, đặc biệt trường hợp lỗi và ranh giới.
- [ ] Unit test không khởi tạo hạ tầng nếu chỉ kiểm tra quy tắc; không mock chính logic cần chứng minh.
- [ ] Controller test kiểm tra method/path, validation, status, headers, JSON, Problem Details và security theo phạm vi đã nêu.
- [ ] Test `with(jwt())`/`with(user())` không bị hiểu nhầm là kiểm thử xác thực token thật.
- [ ] Integration test dùng database/transaction manager phù hợp với production khi cần kiểm tra SQL, locking hoặc constraint; migration được thực thi.
- [ ] Rollback test quan sát dữ liệu sau lời gọi qua transaction độc lập; không để `@Transactional` của test che lỗi commit.
- [ ] Các lỗi 401/403/cross-tenant/CSRF và conflict không tạo side effect trái phép.
- [ ] Các chức năng idempotency, optimistic locking, paging, cache và outbox được test ở tầng có đủ dữ liệu/hạ tầng thật.
- [ ] E2E kiểm tra hành trình trọng yếu qua điểm truy cập thật, có credential test, dữ liệu cách ly, timeout có giới hạn và cleanup.
- [ ] CI phân tầng cho phản hồi nhanh, các test flaky được điều tra, test coverage không được xem là thước đo duy nhất của chất lượng.

**Điểm cốt lõi:** unit test bảo vệ **quy tắc**, controller test bảo vệ **hợp đồng HTTP**, integration test bảo vệ **sự phối hợp giữa các thành phần thật**, và end-to-end test bảo vệ **hành trình sử dụng sau triển khai**. Bộ kiểm thử REST API đáng tin cậy cần cả bốn ở phạm vi phù hợp với rủi ro, mỗi bài có assertions phản ánh hành vi thực tế và giới hạn được nêu rõ.
