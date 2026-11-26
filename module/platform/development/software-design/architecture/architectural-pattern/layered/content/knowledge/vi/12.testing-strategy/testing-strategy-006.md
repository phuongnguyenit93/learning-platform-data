# Lựa chọn mock, stub, fake hoặc hạ tầng thật theo điều cần chứng minh

Khi kiểm thử một thành phần, ta thường phải quyết định nên thay dependency bằng mock, stub, fake hay kết nối đến hạ tầng thật. Chọn sai có thể khiến test nhanh nhưng không chứng minh được điều quan trọng, hoặc test quá nặng, chậm và dễ lỗi do phụ thuộc môi trường. Cách chọn phù hợp bắt đầu từ câu hỏi: **bài kiểm thử này cần chứng minh điều gì?**

Trong module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED` — học tổ chức phần mềm theo kiến trúc phân tầng — bài học này tập trung vào lựa chọn test double và hạ tầng theo ranh giới cần kiểm tra. Ta sẽ phân biệt mock, stub, fake và implementation thật; xem xét điều gì nên cô lập ở tầng trình bày, ứng dụng, nghiệp vụ và truy cập dữ liệu; sau đó chọn mức kiểm thử đủ tin cậy mà vẫn có chi phí hợp lý.

## 1. Bắt đầu từ bằng chứng cần thu được

Một test chỉ có ý nghĩa khi kết quả của nó cung cấp bằng chứng cho một thuộc tính cụ thể của hệ thống. Trước khi chọn công cụ, hãy viết câu cần chứng minh dưới dạng hành vi quan sát được.

Ví dụ với chức năng đặt hàng:

- Khi khách hàng không tồn tại, ca sử dụng từ chối tạo đơn và không lưu dữ liệu.
- Khi đơn hợp lệ, dịch vụ lưu đơn và ghi outbox trong cùng transaction.
- Repository JPA ánh xạ đúng entity và truy vấn đúng database.
- Controller chuyển request HTTP thành command và trả đúng mã trạng thái.
- Adapter thanh toán gửi đúng URL, header, payload và idempotency key.

Những câu trên cần các loại bằng chứng khác nhau. Unit test cho logic nghiệp vụ có thể dùng object thật và fake repository. Test repository cần database thật để chứng minh SQL, mapping và ràng buộc. Test adapter HTTP cần một server HTTP có thể quan sát request. Một mock xác nhận phương thức được gọi không thể chứng minh câu SQL chạy đúng trên database.

Hãy tránh câu mục tiêu mơ hồ như “test service hoạt động”. Thay vào đó, xác định đầu vào, điều kiện, kết quả và side effect cần kiểm chứng. Khi biết điều gì cần chứng minh, việc chọn test double trở nên rõ ràng hơn.

## 2. Phân biệt mock, stub, fake và implementation thật

Các thuật ngữ test double thường được dùng lẫn nhau. Trong thực tế, điều quan trọng là hiểu vai trò của từng loại trong test.

| Loại | Cách hoạt động | Dùng để chứng minh điều gì? | Ví dụ |
|---|---|---|---|
| Stub | Trả về dữ liệu được thiết lập trước khi được gọi | Thành phần xử lý đúng với một phản hồi cụ thể | `PaymentGateway` trả về `DECLINED` |
| Mock | Ghi nhận tương tác để test xác minh lời gọi, đối số hoặc thứ tự khi cần | Thành phần phát ra tương tác mà hợp đồng yêu cầu | Xác minh `outboxRepository.save(event)` được gọi một lần |
| Fake | Implementation thay thế có hành vi làm việc được nhưng đơn giản hơn production | Logic consumer hoạt động với một implementation có trạng thái | Repository lưu vào `Map` trong bộ nhớ |
| Spy | Bọc hoặc theo dõi một đối tượng thật để quan sát tương tác | Một tương tác cụ thể với đối tượng được bọc | Spy ghi nhận phương thức được gọi trong khi vẫn chạy hành vi thật |
| Hạ tầng thật | Dùng implementation thực tế như database, broker hoặc dịch vụ được triển khai | Tích hợp công nghệ, giao thức, transaction, SQL hoặc cấu hình thực | PostgreSQL chạy bằng Testcontainers |

Một mock có thể được cấu hình để trả dữ liệu như stub, vì vậy ranh giới giữa các tên gọi trong thư viện không phải lúc nào cũng tuyệt đối. Hãy gọi theo vai trò mà test đang dùng: cung cấp câu trả lời cố định, kiểm tra tương tác hay thực thi hành vi thay thế.

### Stub: điều khiển câu trả lời của dependency

Giả sử ca sử dụng cần biết kết quả thanh toán. Trong test, ta muốn kiểm tra nhánh bị từ chối mà không gọi nhà cung cấp thật:

```java
PaymentGateway gateway = request ->
    AuthorizationResult.declined("INSUFFICIENT_FUNDS");

AuthorizeOrderPayment useCase = new AuthorizeOrderPayment(gateway);
AuthorizationResult result = useCase.authorize(samplePaymentRequest());

assertEquals(AuthorizationStatus.DECLINED, result.status());
```

Lambda trên đóng vai trò stub: nó cung cấp câu trả lời được định trước để test kiểm tra logic xử lý kết quả. Test không cần biết HTTP client hoặc credential.

### Mock: kiểm tra tương tác có ý nghĩa

Với Mockito, có thể xác minh một thông điệp outbox được tạo khi ca sử dụng hoàn tất:

```java
@Test
void savesOrderAndRecordsEvent() {
    OrderRepository orders = mock(OrderRepository.class);
    OutboxRepository outbox = mock(OutboxRepository.class);
    PlaceOrderService service = new PlaceOrderService(orders, outbox);

    service.place(validCommand());

    verify(orders).save(any(Order.class));
    verify(outbox).save(argThat(message ->
        message.eventType().equals("OrderPlaced")
    ));
}
```

Mock giúp xác nhận tương tác với dependency. Tuy nhiên, test này chỉ chứng minh hai phương thức được gọi với điều kiện matcher đã kiểm tra; nó không chứng minh hai thao tác cùng commit, SQL đúng hoặc message được broker nhận. Những điều đó cần test tích hợp khác.

Chỉ xác minh tương tác khi tương tác là một phần quan trọng của hợp đồng. Nếu test xác minh mọi lời gọi getter, setter hoặc thứ tự nội bộ không có ý nghĩa bên ngoài, nó dễ bị hỏng khi refactor dù hành vi sản phẩm không đổi.

### Fake: implementation thay thế có hành vi

Một fake repository có thể lưu entity trong bộ nhớ để test ca sử dụng:

```java
final class InMemoryOrderRepository implements OrderRepository {
    private final Map<OrderId, Order> store = new HashMap<>();

    @Override
    public void save(Order order) {
        store.put(order.id(), order);
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return Optional.ofNullable(store.get(id));
    }
}
```

Fake thực hiện một phần hành vi của repository và có thể được dùng trong nhiều test. Nó hữu ích khi cần lưu/đọc trạng thái thực tế nhưng không cần database. Tuy nhiên, fake này không mô phỏng transaction, SQL, khóa, constraint, kiểu dữ liệu hay hành vi đồng thời của PostgreSQL. Không được suy luận rằng test pass với fake đồng nghĩa adapter JPA hoạt động đúng.

### Implementation thật

Khi câu hỏi là “repository có chạy đúng với PostgreSQL không?”, cần chạy PostgreSQL thật hoặc một môi trường tương thích đủ để kiểm chứng. Khi câu hỏi là “HTTP client có gửi đúng header và xử lý timeout không?”, cần một HTTP server test có thể nhận request thật. Hạ tầng thật cung cấp bằng chứng về tích hợp, nhưng thường tốn thời gian và cần quản lý dữ liệu, cổng mạng, khởi động và dọn dẹp.

## 3. Chọn theo ranh giới của kiến trúc phân tầng

Mỗi tầng có trách nhiệm khác nhau, vì vậy test double phù hợp cũng khác nhau. Bảng dưới đây là gợi ý, không phải quy tắc cứng cho mọi dự án.

| Thành phần đang kiểm tra | Điều cần chứng minh | Lựa chọn thường phù hợp |
|---|---|---|
| Entity và value object | Bất biến, phép tính và chuyển trạng thái | Đối tượng thật, không cần mock chính đối tượng đang kiểm tra |
| Domain service / policy | Quy tắc nghiệp vụ với các đầu vào đã xác định | Đối tượng thật; stub/fake cho collaborator bên ngoài nếu cần |
| Application service | Điều phối ca sử dụng và phản ứng với kết quả dependency | Fake hoặc stub cho port; mock cho tương tác có ý nghĩa |
| Controller | Binding HTTP, validation, mã trạng thái và response | MockMvc/WebTestClient với dependency ứng dụng giả hoặc mock |
| Repository / DAO | SQL, mapping, query, constraint và transaction | Database thật tương thích, thường qua Testcontainers |
| HTTP adapter | URL, header, serialization, timeout và ánh xạ response | Stub HTTP server như WireMock hoặc MockWebServer |
| Message consumer | Deserialize, xử lý duplicate, commit và ack | Test unit với message giả; integration với broker khi cần chứng minh giao thức/ack |
| Composition root / Spring wiring | Bean được tạo và dependency được nối đúng | Spring context test với cấu hình tương ứng |

Một tầng có thể cần nhiều cấp test. Ví dụ, application service có unit test dùng fake để bao phủ các nhánh nghiệp vụ, cùng một vài integration test xác minh transaction thật với repository. Không cần chọn duy nhất một loại test double cho toàn bộ lớp.

## 4. Unit test logic nghiệp vụ bằng đối tượng thật

Entity và value object thường là những đối tượng mà test cần kiểm tra trực tiếp. Mock chúng sẽ làm mất chính hành vi cần chứng minh.

Ví dụ, `Order` bảo vệ bất biến rằng chỉ đơn nháp mới được thêm dòng:

```java
@Test
void cannotAddLineAfterOrderIsPlaced() {
    Order order = new Order(OrderId.newId());
    order.addLine(validLine());
    order.place();

    assertThrows(IllegalStateException.class,
        () -> order.addLine(anotherValidLine()));
}
```

Test tạo `Order` thật và gọi hành vi thật. Không cần mock `Order` vì mục tiêu là chứng minh bất biến của chính entity. Nếu `Order` phụ thuộc một service ngoài, đó có thể là dấu hiệu cần xem lại thiết kế: entity thường nên bảo vệ quy tắc dựa trên trạng thái mà nó sở hữu, còn việc gọi hệ thống ngoài được điều phối ở tầng ứng dụng hoặc domain service phù hợp.

Với một policy phụ thuộc thời gian, inject `Clock` rồi dùng đồng hồ cố định:

```java
@Test
void deadlineIsExpiredAtBoundary() {
    Instant deadline = Instant.parse("2026-08-01T12:00:00Z");
    Clock clock = Clock.fixed(deadline, ZoneOffset.UTC);
    PaymentDeadlinePolicy policy = new PaymentDeadlinePolicy(clock);

    assertTrue(policy.isExpired(deadline));
}
```

Ở đây `Clock.fixed` là một dependency thật của Java nhưng được cấu hình cho test. Không cần mock `Clock` vì API đã cung cấp implementation cố định, rõ ràng và dễ dự đoán.

## 5. Test application service bằng fake hoặc stub

Application service thường điều phối repository, gateway, publisher hoặc các port khác. Unit test nên tập trung vào quyết định và luồng điều phối của ca sử dụng, không lặp lại kiểm thử chi tiết SQL hay HTTP.

Giả sử `CancelOrderService` cần tải đơn và lưu trạng thái hủy. Có thể dùng fake repository:

```java
final class InMemoryOrderRepository implements OrderRepository {
    private final Map<OrderId, Order> orders = new HashMap<>();

    void add(Order order) {
        orders.put(order.id(), order);
    }

    @Override
    public void save(Order order) {
        orders.put(order.id(), order);
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return Optional.ofNullable(orders.get(id));
    }
}

@Test
void cancellationChangesOrderState() {
    InMemoryOrderRepository repository = new InMemoryOrderRepository();
    Order order = placedOrder();
    repository.add(order);

    CancelOrderService service = new CancelOrderService(repository);
    service.cancel(order.id());

    assertEquals(OrderStatus.CANCELLED,
        repository.findById(order.id()).orElseThrow().status());
}
```

Fake phù hợp vì test cần xem trạng thái đã lưu sau khi ca sử dụng chạy. Nếu chỉ muốn điều khiển kết quả `findById` và xác minh `save` được gọi, stub và mock có thể ngắn hơn. Chọn cách thể hiện ý định rõ nhất, tránh dựng framework giả phức tạp hơn logic đang kiểm tra.

Với lỗi dependency, stub có thể trả `Optional.empty()` hoặc ném exception theo hợp đồng. Khi đó test xác minh service trả lỗi nghiệp vụ phù hợp và không thực hiện bước tiếp theo. Các test này nên kiểm tra kết quả quan sát được, chẳng hạn trạng thái đơn, command được gửi hoặc kết quả trả về.

## 6. Khi nào dùng mock và khi nào tránh mock?

Mock đặc biệt hữu ích khi muốn xác minh một side effect bắt buộc hoặc một tương tác khó quan sát qua trạng thái cuối. Ví dụ:

- Service phải gọi cổng thanh toán với idempotency key gắn với payment attempt.
- Application service phải ghi một sự kiện vào port outbox.
- Khi kiểm tra quyền truy cập thất bại, repository không được gọi để tránh truy cập dữ liệu.
- Một adapter phải gửi đúng tham số tới client bên dưới.

Mock thường không phù hợp khi:

- Mock chính entity/value object mà test cần xác minh hành vi.
- Mock mọi collaborator và chỉ kiểm tra chuỗi lời gọi nội bộ.
- Dùng mock repository để kết luận SQL hoặc mapping đúng.
- Dùng mock transaction manager để kết luận rollback thực sự hoạt động.
- Mock một thư viện phức tạp đến mức test đang kiểm tra giả định của mock hơn là ứng dụng.

Một dấu hiệu của over-mocking là thay đổi cách triển khai nhỏ làm rất nhiều test thất bại dù đầu ra và hành vi sản phẩm không đổi. Khi đó, cân nhắc fake, đối tượng thật hoặc kiểm tra trạng thái đầu ra thay vì kiểm tra chi tiết tương tác.

## 7. Repository cần database thật khi kiểm tra điều gì?

Repository là ranh giới giữa mô hình ứng dụng và cơ chế lưu trữ. Unit test với mock có thể xác minh application service gọi repository, nhưng không chứng minh implementation repository hoạt động.

Với Spring Data JPA/JDBC, database thật hoặc database test tương thích cần thiết khi muốn xác minh:

- Entity và quan hệ được ánh xạ đúng.
- JPQL, SQL native, query method và projection trả dữ liệu chính xác.
- `NULL`, collation, precision/scale, timezone và kiểu dữ liệu có hành vi như mong đợi.
- Unique constraint, foreign key, check constraint và index có tác dụng.
- Transaction commit/rollback và isolation có hành vi phù hợp.
- Câu truy vấn hoạt động với dialect của database production.

Ví dụ kiểm thử repository với PostgreSQL bằng Testcontainers:

```java
@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class JpaOrderRepositoryTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    OrderJpaRepository repository;

    @Test
    void persistsAndLoadsOrder() {
        OrderJpaEntity entity = sampleOrderEntity();

        repository.saveAndFlush(entity);

        OrderJpaEntity loaded = repository.findById(entity.getId()).orElseThrow();
        assertEquals(entity.getCustomerId(), loaded.getCustomerId());
    }
}
```

Đoạn mã minh họa cần các dependency Spring Boot test, Spring Data JPA và Testcontainers PostgreSQL tương thích. `@DataJpaTest` cấu hình slice kiểm thử JPA; `@Testcontainers` khởi động container database. Nếu dự án dùng migration như Flyway hoặc Liquibase, nên có kiểm thử xác minh schema được dựng bằng migration production thay vì chỉ dựa vào schema tự sinh từ entity.

Một số test slice có thể tự rollback transaction test sau mỗi phương thức. Điều đó giúp cô lập dữ liệu nhưng không chứng minh đầy đủ ranh giới transaction của một ca sử dụng gọi từ ngoài. Với kiểm thử rollback của application service, cần kiểm soát transaction của test để quan sát commit/rollback thực tế, hoặc dùng test tích hợp không bị transaction ngoài của test che khuất kết quả.

### H2 hoặc database thay thế có đủ không?

Database trong bộ nhớ như H2 khởi động nhanh và có thể phù hợp với một số truy vấn đơn giản. Nhưng dialect, kiểu dữ liệu, khóa, isolation, JSON, sequence hoặc hàm SQL có thể khác database production. Nếu ứng dụng phụ thuộc PostgreSQL, MySQL hay SQL Server ở các đặc tính đó, hãy dùng chính hệ quản trị tương ứng cho test tích hợp quan trọng. Chỉ dùng database thay thế khi đã xác định test không phụ thuộc hành vi riêng của production database.

## 8. HTTP adapter cần một server test có thể quan sát request

Nếu adapter gọi một API bên ngoài, mock `PaymentHttpClient` chỉ chứng minh adapter gọi client với tham số mong đợi. Nó không chứng minh URL được ghép đúng, header được gửi, JSON được serialize hay response được parse.

Một HTTP stub server như WireMock hoặc MockWebServer cho phép adapter gửi request HTTP thật đến server cục bộ, còn test điều khiển response:

```java
@Test
void sendsIdempotencyKeyAndMapsApprovedResponse() {
    wireMockServer.stubFor(post(urlEqualTo("/payments/authorize"))
        .withHeader("Authorization", equalTo("Bearer test-token"))
        .withHeader("Idempotency-Key", equalTo("payment-123"))
        .willReturn(okJson("""
            {"status":"APPROVED","reference":"pay-789"}
            """)));

    AuthorizationResult result = gateway.authorize(samplePaymentRequest());

    assertEquals(AuthorizationStatus.APPROVED, result.status());
    assertEquals("pay-789", result.reference());
    wireMockServer.verify(postRequestedFor(urlEqualTo("/payments/authorize")));
}
```

Ví dụ giả định `wireMockServer` đã được khởi động trên một cổng động và `gateway` được cấu hình base URL trỏ đến server đó. Cần cấu hình lifecycle server trong test và dừng server sau khi hoàn tất. Dùng token giả, không dùng credential production. Test có thể bổ sung response lỗi, timeout, body sai định dạng và header bị thiếu.

HTTP stub server là một server giả có hành vi được kiểm soát, không phải nhà cung cấp production. Nó cho bằng chứng tốt hơn mock client về giao thức HTTP và serialization, nhưng không chứng minh dịch vụ ngoài thật đang hoạt động hoặc có cùng chính sách xác thực. Với hợp đồng của nhà cung cấp, có thể bổ sung contract test hoặc một số kiểm thử sandbox có kiểm soát.

## 9. Message broker và các phụ thuộc bất đồng bộ

Với message consumer hoặc publisher, lựa chọn test phụ thuộc vào câu hỏi:

- Muốn kiểm tra logic xử lý event: gọi handler bằng event object hoặc message giả.
- Muốn kiểm tra serialize/deserialize và header: dùng serializer thật và message mẫu.
- Muốn kiểm tra consumer ack, retry, partition hoặc transaction broker: dùng broker test tương thích, thường bằng container.
- Muốn kiểm tra phối hợp database với outbox: dùng database thật; broker có thể được stub trong test relay, rồi bổ sung integration test với broker thật nếu cần xác minh giao thức.

Không nên dùng một mock broker để kết luận rằng broker bảo đảm thứ tự, durability hoặc semantics ack. Những thuộc tính đó thuộc về broker thật và cấu hình thực tế.

## 10. Kiểm thử Spring wiring và composition root

Unit test có thể khởi tạo service bằng constructor và truyền fake trực tiếp. Nhưng nó không chứng minh Spring tạo đúng bean, profile được kích hoạt hay dependency được inject đúng implementation.

Khi cấu hình Spring là điều cần kiểm tra, dùng context test với phạm vi vừa đủ:

- `@WebMvcTest` để kiểm tra controller, binding và validation; thay application service bằng bean test.
- `@DataJpaTest` để kiểm tra JPA repository và mapping với database phù hợp.
- `@SpringBootTest` khi cần xác minh nhiều cấu hình và bean cùng hoạt động; tránh dùng cho mọi unit test vì chi phí khởi động cao.
- `ApplicationContextRunner` hoặc context slice phù hợp để kiểm tra một nhóm auto-configuration hoặc conditional bean.

Ví dụ, nếu hai adapter cùng implement `PaymentGateway`, cần test cấu hình để xác minh qualifier/profile chọn đúng implementation. Một unit test khởi tạo service trực tiếp sẽ không bắt được lỗi thiếu bean hoặc ambiguity của Spring.

## 11. Cô lập dữ liệu và giữ test ổn định

Hạ tầng thật làm test có giá trị tích hợp cao hơn nhưng cũng tăng trách nhiệm dọn dẹp. Một test tốt cần dữ liệu độc lập và kết quả có thể lặp lại.

- Tạo dữ liệu riêng cho từng test, dùng ID ngẫu nhiên hoặc namespace riêng nếu phù hợp.
- Dọn dữ liệu sau test bằng transaction rollback, truncate có kiểm soát hoặc database/container riêng.
- Không để test phụ thuộc thứ tự chạy hoặc dữ liệu còn sót từ test trước.
- Chỉ dùng thời gian cố định qua `Clock` khi kiểm tra deadline, expiration hoặc lịch.
- Không gọi API production hoặc gửi email thật trong test tự động.
- Cấu hình timeout và giới hạn tài nguyên cho container, broker và server test.
- Nếu test dùng chung container, bảo đảm dữ liệu được cô lập bằng schema/database hoặc cleanup rõ ràng.

Test tích hợp thất bại ngẫu nhiên thường là dấu hiệu có trạng thái dùng chung, thời gian chờ thiếu kiểm soát, cổng xung đột hoặc phụ thuộc mạng ngoài. Đừng bỏ qua flaky test vì nó làm giảm niềm tin vào cả bộ kiểm thử.

## 12. Một ví dụ quyết định theo câu hỏi kiểm thử

Giả sử nhóm đang xây dựng chức năng đặt hàng và cần chọn cách test cho từng câu hỏi:

| Câu hỏi cần trả lời | Cách test phù hợp | Vì sao |
|---|---|---|
| Đơn trống có bị từ chối không? | Unit test với `Order` thật | Cần chứng minh invariant của entity |
| Khách hàng không tồn tại có làm use case dừng trước khi lưu không? | Unit test application service với stub/mock repository | Cần điều khiển kết quả lookup và kiểm tra hành vi use case |
| Repository có lưu đúng quan hệ dòng hàng không? | Integration test với PostgreSQL | Cần chứng minh mapping và persistence thực |
| API có trả 400 khi request thiếu trường bắt buộc không? | MVC slice test với MockMvc | Cần chứng minh binding và validation của Spring MVC |
| Adapter có gửi đúng idempotency key đến cổng thanh toán không? | Test adapter với HTTP stub server | Cần quan sát HTTP request thực |
| Hai thao tác order và outbox có rollback cùng nhau không? | Integration test với database và transaction manager thật | Cần chứng minh tính nguyên tử của transaction |
| Spring có chọn đúng adapter theo profile production không? | Context test với profile và cấu hình tương ứng | Cần chứng minh composition root và bean wiring |

Không cần chạy tất cả các test này trong mỗi thay đổi. Hãy chọn test gần nhất với rủi ro của thay đổi và duy trì một tập test tích hợp đủ bao phủ các ranh giới quan trọng.

## 13. Các dấu hiệu chọn sai test double

- **Mock quá sâu:** test xác minh nhiều lời gọi nội bộ, dễ vỡ khi refactor và ít nói về hành vi.
- **Fake quá đơn giản nhưng dùng để kết luận về database:** fake không có SQL, transaction, khóa hay constraint như database thật.
- **Stub không phản ánh hợp đồng lỗi:** test chỉ dùng phản hồi thành công nên bỏ qua timeout, lỗi xác thực hoặc kết quả từ chối.
- **Dùng hạ tầng thật cho mọi test:** suite chậm, khó chạy local và làm việc phát triển thường ngày nặng nề.
- **Dùng hạ tầng giả cho thuộc tính cần chứng minh:** mock broker không chứng minh ack; mock repository không chứng minh mapping.
- **Mock chính đối tượng đang kiểm tra:** test không chạy logic cần xác minh.
- **Không cô lập dữ liệu:** kết quả phụ thuộc thứ tự hoặc môi trường chạy.
- **Không kiểm tra cấu hình thật:** unit test pass nhưng Spring context không khởi động do thiếu hoặc trùng bean.

## 14. Quy trình chọn mock, stub, fake hay hạ tầng thật

Trước khi viết test, hãy trả lời lần lượt:

1. **Thuộc tính nào cần chứng minh?** Hành vi nghiệp vụ, tương tác, mapping, transaction, giao thức hay cấu hình?
2. **Ranh giới nào chứa thuộc tính đó?** Entity, application service, repository, adapter HTTP, broker hay Spring container?
3. **Có thể dùng đối tượng thật mà không kéo theo hạ tầng không?** Nếu có, ưu tiên đối tượng thật cho logic đang kiểm tra.
4. **Cần điều khiển câu trả lời hay xác minh tương tác?** Dùng stub cho câu trả lời; mock khi tương tác là một phần của hợp đồng.
5. **Cần trạng thái thay thế có hành vi không?** Dùng fake nếu nó đủ đơn giản và có ý nghĩa.
6. **Thuộc tính phụ thuộc công nghệ thật không?** Dùng database, broker, HTTP server hoặc Spring context tương thích để lấy bằng chứng.
7. **Có cô lập và dọn dẹp được không?** Xác định dữ liệu, timeout, lifecycle và cleanup trước khi thêm test hạ tầng.
8. **Test đang kiểm tra hành vi hay chi tiết triển khai?** Nếu refactor không đổi hành vi mà test vẫn hỏng hàng loạt, hãy xem lại mức độ mock và assertion.

Không có một tỷ lệ mock/fake/integration cố định đúng cho mọi dự án. Một hệ thống có nhiều quy tắc miền có thể có nhiều unit test với đối tượng thật; một hệ thống tích hợp nhiều dịch vụ có thể cần nhiều contract và integration test hơn. Điều quan trọng là mỗi test cung cấp bằng chứng đúng với mục tiêu của nó.

Khi lựa chọn mock, stub, fake hoặc hạ tầng thật dựa trên điều cần chứng minh, bộ kiểm thử sẽ có ranh giới rõ: test nhỏ xác minh logic nhanh, test tích hợp xác minh công nghệ và kết nối thật, còn test cấu hình xác minh ứng dụng được lắp ráp đúng. Nhờ vậy, kiến trúc phân tầng vừa dễ kiểm tra từng trách nhiệm, vừa có bằng chứng rằng các tầng phối hợp chính xác khi chạy cùng nhau.
