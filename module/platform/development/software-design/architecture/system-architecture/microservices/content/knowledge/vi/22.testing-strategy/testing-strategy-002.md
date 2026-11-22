# Kiểm thử dịch vụ độc lập với các phụ thuộc được kiểm soát trong Microservices

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Chiến lược kiểm thử.
>
> **Ý chính:** Kiểm thử một microservice cần đủ độc lập để chạy lặp lại với kết quả đáng tin, nhưng vẫn phải giữ đúng các hợp đồng mà service đó giao tiếp với thế giới bên ngoài. Hãy kiểm soát dependency bằng test double, service virtualization, container hạ tầng và contract test ở những mức thích hợp; đồng thời kiểm chứng những ranh giới thật sự có nguy cơ lỗi tích hợp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định **System Under Test (SUT)** của một microservice và nhận diện các dependency cần kiểm soát trong từng loại test.
2. Phân biệt **mock, stub, fake, spy, service virtualization, test container** và dependency thật; giải thích ưu nhược điểm của từng lựa chọn.
3. Tổ chức unit test, component/service test, integration test, contract test và end-to-end test thành một chiến lược cân bằng tốc độ với độ tin cậy.
4. Kiểm thử độc lập một service có REST API, database, message broker và lời gọi outbound HTTP/gRPC mà không phụ thuộc trạng thái ngẫu nhiên của môi trường chung.
5. Tạo dữ liệu test, đồng hồ, ID, cấu hình và tình huống lỗi có thể tái lập.
6. Kiểm tra những điều kiện ít gặp nhưng quan trọng như timeout, 429, 503, retry, idempotency, duplicate message, transaction rollback và tương thích hợp đồng.
7. Thiết kế pipeline CI có tín hiệu lỗi rõ, tài nguyên hợp lý và bằng chứng giúp tìm nguyên nhân khi một test thất bại.

Các tên service và đoạn Java/Spring Boot bên dưới là ví dụ minh họa. Phiên bản Spring Boot, JUnit, Mockito, WireMock, Testcontainers, Spring Cloud Contract hoặc Pact cần được đối chiếu với dependency thực tế của dự án khi triển khai.

## 2. Vì sao kiểm thử độc lập lại quan trọng?

Giả sử Order Service nhận yêu cầu đặt hàng. Trong một request, nó có thể:

1. Xác thực người dùng và quyền tạo đơn.
2. Gọi Inventory Service để giữ hàng.
3. Ghi dữ liệu vào Order Database.
4. Phát message OrderCreated.
5. Gọi Payment Service hoặc đợi một bước thanh toán bất đồng bộ.

Sơ đồ đơn giản:

~~~text
                     ┌──────────────────┐
Client ── HTTP ──────►│  Order Service   │
                     └───┬────┬────┬────┘
                         │    │    │
           HTTP/gRPC ────┘    │    └──── Event Broker
                              │
                            Database
                         Inventory / Payment
~~~

Nếu unit test của Order gọi trực tiếp Inventory ở một môi trường dùng chung, kết quả có thể thay đổi khi:

- Inventory được deploy phiên bản mới.
- Dữ liệu tồn kho của người khác thay đổi.
- Internet nội bộ hoặc DNS chập chờn.
- Một worker khác đang tiêu thụ message.
- Hạn mức hoặc khóa API hết hiệu lực.
- Test chạy song song làm đụng dữ liệu.
- Thời gian thực, scheduler hay retry khiến kết quả phụ thuộc thứ tự.

Khi đó test thất bại không nói rõ Order có lỗi hay dependency đang không sẵn sàng. Càng nhiều microservice, mỗi test phụ thuộc vào hệ thống sống càng gây **flakiness**, thời gian chạy lâu và khó phân biệt regression.

**Mục tiêu của kiểm thử độc lập:** chạy SUT với **những đầu vào và hành vi dependency đã kiểm soát**, đo kết quả dự kiến và tạo cùng kết luận sau nhiều lần chạy.

**Không có nghĩa mọi test phải giả lập tất cả.** Nếu chỉ dùng mock cho database, HTTP và message broker, có thể bỏ sót query sai, migration lỗi, serialization không tương thích và cấu hình bảo mật. Chiến lược tốt xác định rõ **điều gì cần cô lập** và **ranh giới nào phải chạy bằng thành phần thật**.

## 3. Xác định đúng phạm vi SUT

SUT là thành phần mà bài test trực tiếp đánh giá. Phạm vi có thể nhỏ hoặc lớn:

| Loại test | SUT | Dependency thường được kiểm soát | Điều có thể chứng minh |
| --- | --- | --- | --- |
| Unit | Hàm, class hoặc domain service | Repository, HTTP client, clock, ID generator | Logic nghiệp vụ trong một đơn vị |
| Component/service | Một microservice chạy trong process test | HTTP downstream giả, broker/DB test riêng | Wiring, serialization, filter, transaction và behavior API của service |
| Integration | Một ranh giới với DB, broker, cache, IdP hoặc provider | Thành phần thật bằng container/test endpoint | Kết nối, schema, giao thức, migration, retry delivery |
| Consumer contract | Kỳ vọng client đối với dependency | Mock contract server hoặc fixture tương ứng | Consumer khai báo đúng request/response cần dùng |
| Provider contract | API do service cung cấp | Provider chạy với trạng thái được kiểm soát | Provider đáp ứng các interaction đã thỏa thuận |
| End-to-end | Luồng nghiệp vụ qua nhiều service | Ít hoặc không giả lập các ranh giới quan trọng | Một hành trình thực có thể hoàn tất qua các service |

**Độc lập không phải một nhãn tuyệt đối.** Một service test vẫn có thể chạy PostgreSQL container thật trong khi mô phỏng Payment bằng WireMock. Nó độc lập với **dịch vụ Payment đang chạy trong môi trường chung**, nhưng vẫn kiểm thử đúng SQL và transaction của service.

### 3.1. Phân loại dependency theo ranh giới

Với Order Service:

- **Trong process:** domain rules, validator, mapper, clock, ID generator, repository port, event publisher interface.
- **Ngoài process:** DB, Redis, RabbitMQ/Kafka, Inventory API, Payment API, OAuth/JWKS endpoint.
- **Nền tảng:** DNS, TLS, proxy, filesystem, time zone, env variables, feature flags, container runtime.
- **Con người/quy trình:** dữ liệu test chung, quyền truy cập, shared staging, quota bên thứ ba.

Mỗi ranh giới cần câu trả lời: **test này đang xác nhận contract của ranh giới, hay chỉ cần giả hành vi của nó để tập trung vào logic Order?**

Nếu kiểm tra thuật toán tính tổng tiền, không cần DB thật. Nếu kiểm tra transaction rollback, dùng mock Repository không chứng minh được điều gì về database thật.

## 4. Phân biệt mock, stub, fake, spy và dependency thật

Thuật ngữ thường bị dùng lẫn; cần hiểu theo vai trò:

### 4.1. Stub — cấp kết quả đã định trước

Stub trả lời theo input được cấu hình để test một nhánh nghiệp vụ.

Ví dụ: Inventory luôn trả available=5 với SKU A; Payment luôn trả trạng thái approved. Test kiểm tra Order phản ứng đúng, không quan tâm stub đã được gọi bao nhiêu lần nếu interaction không phải yêu cầu nghiệp vụ.

**Hợp khi:** muốn điều khiển response 200/404/503, body, latency hoặc exception.

### 4.2. Mock — kiểm tra tương tác theo kỳ vọng

Mock ghi hoặc xác minh việc collaborator được gọi với arguments nào, bao nhiêu lần, theo thứ tự nào nếu thứ tự thực sự có ý nghĩa.

Ví dụ: giao dịch bị từ chối trước khi giữ hàng phải **không gọi** Payment. Mockito mock thích hợp để assert không có side effect.

**Rủi ro:** verify mọi method call nhỏ khiến test phụ thuộc chi tiết hiện thực. Khi refactor mà behavior người dùng không đổi, test vẫn hỏng.

### 4.3. Fake — hiện thực đơn giản nhưng có hành vi

Fake có implementation nhỏ, ví dụ repository lưu trong Map, clock cố định, fake gateway có bảng dữ liệu và bộ đếm gọi.

Fake giúp test dễ đọc, có thể chạy nhiều tình huống nghiệp vụ mà không cấu hình hàng trăm lời gọi mock. Nhưng fake DB thường không mô phỏng transaction isolation, lock, constraint, query dialect hoặc migration chính xác.

### 4.4. Spy — quan sát một đối tượng hoạt động thật

Spy thường giữ phần lớn logic thật nhưng ghi lại invocation hoặc thay đổi một số hành vi. Dùng để xác nhận điểm tương tác quan trọng khi thật sự cần.

**Rủi ro:** spy lên class lớn có state/side effect khiến test khó hiểu và có thể vô tình gọi dependency thật. Ưu tiên test từ public behavior nếu khả thi.

### 4.5. Service virtualization — dependency theo giao thức

WireMock, MockWebServer, một gRPC test server hoặc local HTTP stub có thể chạy **một server giả với network stack thật**. SUT thực sự tạo HTTP request, serialize JSON, gửi header và xử lý status.

Khác với Mockito mock trên interface client: virtualization bắt được nhiều lỗi về URL, method, header, body, timeout và cách mapping status.

### 4.6. Dependency thật trong môi trường test

PostgreSQL Testcontainer, Kafka/RabbitMQ container hoặc một instance Redis riêng có thể kiểm chứng integration behavior thật. Chúng tiêu tốn tài nguyên hơn stub nhưng có giá trị khi SQL, transaction, protocol, broker ack/retry hoặc cấu hình là rủi ro chính.

| Cách kiểm soát | Tốc độ tương đối | Fidelity tại boundary | Rủi ro chính |
| --- | --- | --- | --- |
| Fake class trong bộ nhớ | Rất nhanh | Thấp ở hạ tầng, cao với logic fake tự viết đúng | Fake khác production |
| Mockito stub/mock | Rất nhanh | Thấp ở network/serialization | Quá phụ thuộc implementation |
| HTTP/gRPC stub server | Nhanh đến vừa | Khá tốt ở giao thức và mapping client | Fixture lệch provider thật |
| DB/broker test container | Vừa đến chậm hơn | Cao với công nghệ cùng loại/phiên bản | Cấu hình test lệch production, Docker/CI resources |
| Shared integration environment | Thường chậm/không ổn định | Có thể cao nhưng khó kiểm soát | Data drift, deploy và tác động chéo |
| End-to-end production-like | Tốn kém nhất | Cao về luồng liên service | Khó cô lập root cause, coverage tình huống hiếm thấp |

**Quy tắc lựa chọn:** test nhanh nhất có khả năng phát hiện đúng loại lỗi đang nhắm tới. Không dùng đơn vị test nhỏ để chứng minh chuyện chỉ có database hay broker thật mới thực hiện.

## 5. Kiến trúc code dễ kiểm thử

Một service có thể dùng **ports and adapters**:

~~~text
           Inbound HTTP Adapter
                    │
                    ▼
          OrderApplicationService
             ┌──────┼──────┐
             ▼      ▼      ▼
       Inventory  Repository  EventPublisher
         Port       Port         Port
             │      │            │
             ▼      ▼            ▼
        HTTP Client  JDBC/JPA   Broker Adapter
~~~

Application service chỉ biết contract của các port, không cần biết host Inventory, DB connection string hay broker URL. Trong unit test, thay port bằng fake; trong integration test, dùng adapter thật cùng container/hệ thống giả thích hợp.

**Lợi ích:** logic nghiệp vụ không phụ thuộc thời gian thực, mạng hoặc thư viện transport. **Giới hạn:** chỉ có interface chưa đảm bảo adapter hoạt động đúng; phải có test cho adapter và contract.

Ví dụ định nghĩa Java tối giản:

~~~java
public interface InventoryGateway {
    Reservation reserve(String sku, int quantity, String requestId);
}

public interface OrderRepository {
    void save(Order order);
    java.util.Optional<Order> findById(String id);
}

public interface OrderEventPublisher {
    void orderCreated(OrderCreated event);
}

public interface OrderIdGenerator {
    String nextId();
}
~~~

Các port nên đặt tên theo nhu cầu nghiệp vụ. Không tạo interface chỉ để mock từng static/helper function; testability là một kết quả của thiết kế ranh giới có ý nghĩa.

## 6. Unit test: giữ toàn bộ yếu tố ngẫu nhiên trong tầm kiểm soát

Ví dụ business rule: một order chỉ được tạo nếu số lượng dương và Inventory xác nhận giữ hàng. Khi thất bại, không được save hoặc phát event.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class PlaceOrderService {
    private final InventoryGateway inventory;
    private final OrderRepository orders;
    private final OrderEventPublisher events;
    private final OrderIdGenerator ids;
    private final Clock clock;

    public PlaceOrderService(
            InventoryGateway inventory,
            OrderRepository orders,
            OrderEventPublisher events,
            OrderIdGenerator ids,
            Clock clock) {
        this.inventory = Objects.requireNonNull(inventory);
        this.orders = Objects.requireNonNull(orders);
        this.events = Objects.requireNonNull(events);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
    }

    public String place(String sku, int quantity, String requestId) {
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }

        Reservation reservation =
                inventory.reserve(sku, quantity, requestId);
        if (!reservation.accepted()) {
            throw new IllegalStateException("Out of stock");
        }

        String orderId = ids.nextId();
        Order order = new Order(orderId, sku, quantity, Instant.now(clock));
        orders.save(order);
        events.orderCreated(new OrderCreated(orderId, requestId));
        return orderId;
    }
}
~~~

Đây là code minh họa, trong đó Order, Reservation và OrderCreated là record/domain type do dự án định nghĩa. Quy trình hoàn chỉnh phải giải quyết transaction/outbox/idempotency ở các lớp thích hợp; đoạn này chỉ minh họa cách test business flow bằng các dependency rõ ràng.

### 6.1. Ví dụ JUnit 5 + Mockito

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class PlaceOrderServiceTest {
    @Test
    void whenInventoryDenies_thenDoNotSaveOrPublish() {
        InventoryGateway inventory = mock(InventoryGateway.class);
        OrderRepository orders = mock(OrderRepository.class);
        OrderEventPublisher events = mock(OrderEventPublisher.class);

        when(inventory.reserve("sku-1", 2, "req-1"))
                .thenReturn(new Reservation(false));

        PlaceOrderService sut = new PlaceOrderService(
                inventory, orders, events,
                () -> "order-fixed",
                Clock.fixed(
                        Instant.parse("2026-01-01T00:00:00Z"),
                        ZoneOffset.UTC));

        assertThrows(IllegalStateException.class,
                () -> sut.place("sku-1", 2, "req-1"));

        verify(inventory).reserve("sku-1", 2, "req-1");
        verifyNoInteractions(orders, events);
    }
}
~~~

**Điều được chứng minh:** Order không ghi dữ liệu/phát event khi Inventory từ chối. **Điều chưa được chứng minh:** HTTP client Inventory xử lý đúng response JSON hay database rollback sau lỗi; những việc đó cần test ở lớp khác.

### 6.2. Nên assert behavior nào?

Ưu tiên:

- Return value và domain state cuối cùng.
- Exception hoặc result type thể hiện contract.
- Một sự kiện hoặc side effect có ý nghĩa nghiệp vụ.
- Không xảy ra side effect khi điều kiện bảo vệ không đạt.
- Số lần gọi khi số lần gọi liên quan tới idempotency, chi phí hoặc duplication.

Tránh verify những chi tiết như gọi getter, mapper, logger, thứ tự private method. Chúng có thể thay đổi khi refactor mà kết quả nghiệp vụ vẫn đúng.

## 7. Kiểm soát Clock, ID, randomness và cấu hình

Các test hay flake vì dependency không nằm ở HTTP hoặc database mà ở **thời gian và nguồn ngẫu nhiên**.

### 7.1. Clock cố định

Tránh gọi Instant.now() trực tiếp ở nhiều nơi trong domain nếu logic có timeout, token expiry hoặc deadline. Inject java.time.Clock hoặc một TimeSource interface:

~~~java
Clock testClock = Clock.fixed(
    Instant.parse("2026-02-03T10:15:30Z"),
    ZoneOffset.UTC);
~~~

Test có thể assert chính xác createdAt/expiresAt mà không sleep. Khi muốn mô phỏng thời gian tiến, dùng mutable test clock hoặc scheduler ảo có điều khiển.

### 7.2. ID generator được inject

Thay UUID.randomUUID() bên trong domain bằng OrderIdGenerator. Test trả order-123, dễ kiểm tra event và repository record.

Không yêu cầu production dùng ID cố định; chỉ thay nguồn sinh ID ở test.

### 7.3. Tránh random không kiểm soát

Property-based testing vẫn có thể dùng random, nhưng cần seed được ghi lại khi fail. Fuzzer nên lưu input làm testcase hồi quy và tránh phụ thuộc vào thứ tự chạy.

### 7.4. Feature flags và config

Mỗi test nên đặt rõ feature flag và settings ảnh hưởng tới behavior. Không để test tự đọc profile staging/prod. Khi test bật/tắt flag, assert hai nhánh độc lập và dọn state sau test.

### 7.5. Cô lập time zone/locale

Dùng UTC/ISO 8601 cho timestamp và inject Clock/ZoneId nếu logic có nghiệp vụ theo múi giờ. Không giả định máy CI chạy cùng múi giờ với laptop.

## 8. Kiểm thử service-level: chạy service thật, kiểm soát outbound dependency

Một service test có thể khởi động Spring Boot app thật tại random port, gửi request qua HTTP client test và route mọi outbound HTTP đến stub server:

~~~text
JUnit Test
   │ HTTP thật
   ▼
Order Service (Spring Boot)
   ├──► Test PostgreSQL / schema riêng
   ├──► Inventory HTTP Stub (WireMock/MockWebServer)
   └──► Fake event adapter hoặc broker test
~~~

**Giữ những thành phần thuộc SUT chạy thật:**

- Request routing, JSON serialization, validation, authentication filter khi nằm trong phạm vi test.
- Service/application layer, bean wiring và exception mapping.
- Transaction/persistence adapter nếu đang kiểm tra DB behavior.
- Retry/timeout/Circuit Breaker config nếu cần kiểm tra resilience.

**Kiểm soát những thành phần ngoài phạm vi:**

- Inventory/Payment response và độ trễ.
- Broker behavior, consumer concurrency và acknowledgement.
- External IdP/JWKS endpoint.
- Thời gian, token expiry và process environment.

Mục tiêu là bài test có thể chạy trên laptop và CI mà không yêu cầu toàn bộ platform đã được triển khai sẵn.

### 8.1. Ví dụ cấu hình test profile

~~~yaml
# application-test.yml (minh họa)
inventory:
  base-url: http://127.0.0.1:18080
payment:
  base-url: http://127.0.0.1:18081

order:
  notify-enabled: false

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Các port cố định ở ví dụ chỉ để dễ đọc. Trong test song song, **nên dùng port động** và truyền URL đã bind bằng DynamicPropertySource hoặc cấu hình tương ứng để tránh port collision.

Không để test profile chứa credential production, default endpoint thật hoặc biến môi trường ngầm có thể chuyển request ra internet.

## 9. Service virtualization cho REST/HTTP dependency

### 9.1. Vì sao không chỉ mock HTTP client?

Khi mock một method như InventoryClient.reserve(), unit test không kiểm tra:

- URL, HTTP method, path hoặc query params có đúng không.
- Header Authorization, Content-Type, Accept có được gửi đúng không.
- JSON field name, enum, date format có khớp provider không.
- HTTP 404/409/429/5xx được map thành kết quả hoặc exception nào.
- Connect timeout, response timeout và redirect có hoạt động không.
- Retry có lặp request và gây duplicate side effect không.

Một HTTP stub server cho phép request đi qua HTTP client thật, vì thế thích hợp để test adapter và nhiều quy tắc resilience.

### 9.2. Ví dụ WireMock dạng cấu hình minh họa

Giả sử endpoint Inventory là:

~~~http
POST /v1/reservations
Content-Type: application/json

{"sku":"sku-1","quantity":2,"requestId":"req-1"}
~~~

Stub thành công:

~~~java
stubFor(post(urlEqualTo("/v1/reservations"))
        .withHeader("Content-Type", containing("application/json"))
        .withRequestBody(matchingJsonPath("$.sku", equalTo("sku-1")))
        .withRequestBody(matchingJsonPath("$.quantity", equalTo("2")))
        .willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("""
                    {"accepted":true,"reservationId":"r-1"}
                    """)));
~~~

Các hàm trên thuộc DSL WireMock khi đã import static methods thích hợp và khởi tạo đúng server. Tên helper/annotation cụ thể có thể khác theo phiên bản.

Kiểm tra:

- Order gửi đúng request và requestId.
- Client deserialize accepted/reservationId đúng.
- Không bị gọi lại không cần thiết trong trường hợp success.
- Nếu response body thiếu field bắt buộc, adapter phải xử lý theo hợp đồng.

### 9.3. Các tình huống HTTP cần có fixture

| Kích thích từ dependency | Kỳ vọng ở SUT |
| --- | --- |
| 200 + JSON hợp lệ | Deserialize và tiếp tục nghiệp vụ |
| 200 + JSON thiếu field bắt buộc | Xử lý lỗi schema hoặc reject, không ghi dữ liệu sai |
| 400 do request sai | Nhận diện lỗi tích hợp hoặc input theo contract |
| 404 tài nguyên không tồn tại | Map thành domain result nếu contract định nghĩa |
| 409 conflict/idempotency | Không tạo giao dịch trùng |
| 401/403 | Không retry bừa; phát hiện lỗi credential/quyền |
| 429 + Retry-After | Backoff/throttle theo policy và deadline |
| 500/502/503/504 | Áp dụng timeout, retry giới hạn hoặc fallback |
| Connection refused / DNS failure | Tạo lỗi rõ; giữ resource và request budget |
| Response trễ quá timeout | Hủy/timeout đúng; không treo request |
| JSON malformed / connection reset giữa stream | Không coi là response thành công |
| Redirect ngoài domain hợp lệ | Không rò token sang host không được tin |
| Provider có extra field mới | Client tương thích nếu hợp đồng cho phép |

**Một fixture nên biểu đạt một hành vi có ý nghĩa**, không chỉ status code. Ví dụ 409 do duplicate requestId khác 409 do hết tồn kho.

### 9.4. Simulate latency mà không làm test chờ quá lâu

Có thể cấu hình delay ngắn có kiểm soát ở stub để xác nhận client timeout; nhưng test có sleep cố định vài chục giây sẽ chậm và dễ flaky. Đối với thuật toán retry/backoff, ưu tiên clock/scheduler có thể điều khiển khi thư viện hỗ trợ; với adapter HTTP thật, một số test timing cần tolerance được ghi rõ.

Đặt **timeout tại HTTP client** thay vì cho rằng JUnit timeout đồng nghĩa request thực đã bị hủy. JUnit timeout chủ yếu bảo vệ thời gian chạy test; nó không thay thế network timeout production.

## 10. Database integration: dùng công nghệ tương thích với production

Đối với truy vấn, migration, constraint và transaction, **mock repository không phải bằng chứng đủ**. Ví dụ production dùng PostgreSQL nhưng test dùng H2 có thể bỏ sót:

- SQL dialect hoặc kiểu dữ liệu khác nhau.
- Unique constraint, transaction isolation, row lock.
- JSONB, array, timestamp/time zone semantics.
- Native queries và index behavior.
- Flyway/Liquibase migration không chạy đúng.
- Deadlock hoặc optimistic locking khác biệt.

Một PostgreSQL container riêng trong test giúp phát hiện lỗi integration trước khi deploy. Phạm vi nên chọn đúng: không nhất thiết mọi unit test đều cần container.

### 10.1. Ví dụ JUnit/Testcontainers với Spring Boot

Minh họa cơ chế, không phải template ràng buộc version:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTest {
    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("orders")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry props) {
        props.add("spring.datasource.url", postgres::getJdbcUrl);
        props.add("spring.datasource.username", postgres::getUsername);
        props.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void savesOrderAndEnforcesUniqueBusinessKey() {
        // Arrange: tạo order có business key cố định.
        // Act: lưu hai order trùng business key.
        // Assert: DB thật từ chối vi phạm constraint
        // và trạng thái sau transaction đúng kỳ vọng.
    }
}
~~~

Test trên minh họa **cấu hình** container, phần body mô tả việc cần test; một bài test thực phải viết assertions tương ứng theo entity/repository dự án. Container cần môi trường CI có container runtime hoặc một backend được Testcontainers hỗ trợ.

### 10.2. Seed và làm sạch dữ liệu

Để test độc lập:

- Seed tối thiểu những record cần thiết cho scenario.
- Dùng primary/business keys riêng cho test.
- Dọn dữ liệu bằng rollback, truncate, database/schema riêng hoặc container lifecycle thích hợp.
- Khi async worker/transaction chạy ở thread khác, đừng giả định annotation transactional của test tự rollback mọi side effect bên ngoài thread/transaction hiện tại.
- Chạy migration production trước test để tránh schema test không giống thực.
- Đừng dùng database staging chứa dữ liệu thật hoặc test chung không kiểm soát.

**Không trộn state của test A với test B.** Một test chỉ pass khi chạy sau test khác là dấu hiệu dependency ẩn.

### 10.3. Transaction, outbox và event publication

Với thao tác “lưu Order rồi phát OrderCreated”, cần test những thuộc tính:

1. Ghi Order và outbox record trong **cùng transaction** nếu đây là contract hệ thống.
2. Khi transaction rollback, không có Order và outbox event thành công.
3. Publisher có thể gửi lại outbox event sau lỗi broker.
4. Consumer nhận duplicate event không tạo tác động nghiệp vụ lần hai.
5. Mark dispatched/offset/ack tuân theo chính sách retry và delivery.

Một unit test chỉ verify publisher.publish() được gọi không chứng minh tính nguyên tử giữa DB commit và event delivery.

## 11. Message broker và consumer test

Các hệ thống event-driven có thêm khó khăn: xử lý bất đồng bộ, retry, at-least-once delivery, ordering và DLQ.

### 11.1. Unit test handler không cần broker

Tách domain handler:

~~~java
public final class OrderCreatedHandler {
    private final NotificationGateway notifications;
    private final ProcessedEventRepository processed;

    public OrderCreatedHandler(
            NotificationGateway notifications,
            ProcessedEventRepository processed) {
        this.notifications = notifications;
        this.processed = processed;
    }

    public void handle(OrderCreated event) {
        if (processed.exists(event.eventId())) {
            return;
        }

        notifications.sendOrderConfirmation(event.orderId());
        processed.mark(event.eventId());
    }
}
~~~

Unit test với fakes:

- Event đầu tiên → gửi một thông báo và đánh dấu đã xử lý.
- Cùng eventId được xử lý lại → không gửi lần hai.
- Notification thất bại → xác định theo thiết kế: có đánh dấu processed không, retry thế nào?

**Lưu ý:** implementation minh họa chưa bảo đảm nguyên tử giữa send và mark; concurrency và crash ở giữa hai bước có thể tạo duplicate. Để bảo đảm idempotency trong thực tế, cần xử lý atomicity/dedup/outbox, idempotency key tại provider hoặc transaction strategy tương ứng.

### 11.2. Integration test với broker thật

Testcontainers Kafka/RabbitMQ hoặc broker test riêng có thể kiểm tra:

- Producer serializer và consumer deserializer.
- Topic/queue routing, exchange/binding, headers.
- Consumer group, partition key, ordering trong phạm vi được bảo đảm.
- Ack/nack, retry/backoff, DLQ.
- Duplicate delivery, stale event và poison message.
- Schema evolution và backward compatibility.
- Khởi động consumer đúng cấu hình và đóng consumer/connection sạch.

### 11.3. Awaitility và async assertion

Một test async nên đợi **điều kiện quan sát được** với timeout hợp lý, không sleep một số giây ngẫu nhiên:

~~~java
await()
    .atMost(java.time.Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertEquals(1, notificationRepository.countForOrder("o-1")));
~~~

Đây là DSL minh họa của Awaitility với imports thích hợp. Khi điều kiện chưa được thỏa trong thời hạn, lỗi phải chứa đủ event ID/queue/dependency context để chẩn đoán.

**Tại sao không dùng Thread.sleep(5000)?** Nếu hệ thống xử lý xong sau 100 ms, test lãng phí; nếu CI đang chậm và cần 5,1 giây, test thất bại không cần thiết. Await condition giảm cả hai vấn đề, dù timeout vẫn phải được chọn có căn cứ.

## 12. Contract test: ngăn mock của consumer lệch provider

Rủi ro lớn nhất của mô phỏng dependency: test chỉ xác nhận **giả định của consumer**, không xác nhận provider thật có hỗ trợ giả định ấy.

Ví dụ Consumer Order tin Inventory trả:

~~~json
{
  "reservationId": "r-123",
  "accepted": true,
  "expiresAt": "2026-11-12T10:00:00Z"
}
~~~

Nhưng provider thực trả:

~~~json
{
  "id": "r-123",
  "status": "RESERVED",
  "expirationTime": "2026-11-12T10:00:00Z"
}
~~~

Unit test vẫn pass với fake theo định dạng đầu tiên; khi deploy, mapping của Order có thể hỏng.

**Consumer-driven contract testing** giúp lưu và xác minh interaction mà consumer cần.

### 12.1. Quy trình contract

1. **Consumer test** khai báo request, field response, status và quy tắc matching mà consumer phụ thuộc.
2. Contract artifact được công bố có version/consumer identity rõ.
3. **Provider verification** chạy provider với trạng thái dữ liệu đã kiểm soát và xác minh từng interaction.
4. CI/deploy gate xác nhận version đang dự kiến triển khai tương thích với các contract liên quan.
5. Khi thay API, test chạy trước khi consumer/provider được đưa vào môi trường không tương thích.

Có thể dùng Pact, Spring Cloud Contract hoặc một bộ schema + compatibility tests tương đương. Công cụ cụ thể phụ thuộc cách tổ chức contract và cách mỗi service được quản lý.

### 12.2. Provider state

Một contract “GET /inventory/sku-1 trả 200” chỉ hợp lệ khi provider có **state** chứa sku-1. Provider test cần seed trạng thái theo một phương pháp riêng, có thể gọi setup hook hoặc tạo record trong test DB.

Không chạy provider verification vào production DB hoặc môi trường có dữ liệu bất định. Contract test phải kiểm soát được state hoặc sử dụng fixture có version rõ ràng.

### 12.3. Contract xác nhận được gì?

Contract test bắt được:

- URL/method/header/body sai.
- Field hoặc type bị đổi làm consumer không thể parse.
- Status code/response shape consumer yêu cầu không còn hợp lệ.
- Event schema bị thay đổi không tương thích.

Contract test **không tự chứng minh**:

- End-to-end business flow thành công.
- Provider đáp ứng SLO latency hoặc tải.
- Database transaction đúng.
- Authn/authz cho mọi identity.
- Network routing, DNS, certificate và production configuration.

Vì vậy vẫn cần test integration, smoke test và một số test end-to-end có giá trị cao.

### 12.4. Tương thích ngược

Với REST/JSON, **thêm field response tùy chọn** thường tương thích nếu consumer bỏ qua field lạ; **đổi tên hoặc xóa field đang được dùng** thường không tương thích. Nhưng kết luận phụ thuộc parser strictness, validation và schema version.

Với message events, cần cân nhắc schema registry, nullable/default fields, enum evolution, consumer version đang chạy và khả năng replay event cũ.

## 13. Kiểm thử resilience: failure là một phần contract

Khi microservice phụ thuộc network, **timeout, retry, Circuit Breaker và Bulkhead** quyết định user experience khi dependency suy giảm. Chúng phải có test tách riêng với happy path.

### 13.1. Timeout

Scenario: Inventory chưa trả lời khi response deadline đã vượt ngân sách.

Test cần xác nhận:

- HTTP client có timeout thực.
- SUT không chờ vô hạn.
- Trạng thái Order không bị xác nhận sai khi không chắc reservation thành công.
- Metrics/log đánh dấu timeout phù hợp.
- Resource được trả lại và request mới không bị dồn đống.

Một timeout không chứng minh Inventory chưa thực hiện side effect. Với operation reserve hoặc payment cần idempotency key và reconciliation.

### 13.2. Retry có giới hạn

Scenario: Inventory trả 503 một lần rồi 200.

Kỳ vọng có thể là:

- Chỉ retry loại lỗi đã cho phép.
- Số lần tối đa đúng policy.
- Có backoff, jitter hoặc test scheduler phù hợp.
- Không retry 400/403 khi đó là lỗi không thoáng qua.
- Không retry khi Circuit Breaker đã OPEN.
- End-to-end deadline không bị vượt chỉ vì nhiều lượt retry.

Test ở lớp unit có thể dùng fake đếm số attempt; test HTTP stub có thể xác minh số request HTTP thật.

### 13.3. Circuit Breaker

Thiết kế kịch bản:

~~~text
CLOSED → đủ lỗi để OPEN
OPEN   → lời gọi bị chặn, không phát HTTP outbound
OPEN   → hết khoảng chờ
HALF_OPEN → N lời gọi thử có giới hạn
HALF_OPEN → thành công theo threshold → CLOSED
HALF_OPEN → thất bại theo threshold → OPEN
~~~

Để test không flaky, dùng clock/scheduler kiểm soát được khi thư viện hỗ trợ. Tách việc test **logic lựa chọn trạng thái** với integration test rằng HTTP adapter thực sự bị bảo vệ.

Không nên verify cụ thể một enum state ở mọi request nếu thư viện dùng cửa sổ và số mẫu; thiết lập input đủ mẫu theo cấu hình test để chuyển trạng thái quyết định.

### 13.4. Bulkhead, rate limit và backpressure

Test khi số request đồng thời vượt capacity:

- SUT giới hạn concurrency hoặc hàng đợi theo policy.
- Request bị từ chối có response rõ ràng.
- Không mất thread/permit khi exception hoặc cancellation.
- Không dùng hàng đợi vô hạn gây memory pressure.
- Không vô tình làm nghẽn dependency khác dùng chung pool.

Những test race/concurrency nên dùng CountDownLatch, barrier, executor kiểm soát được và timeout hợp lý thay vì sleep đoán thời điểm.

## 14. Idempotency và duplicate delivery

Trong microservices, mạng có thể làm client không biết server đã xử lý thành công hay chưa. Retry là bình thường; duplicate side effect là lỗi nghiêm trọng nếu operation yêu cầu đúng một tác động.

Ví dụ request:

~~~http
POST /payments
Idempotency-Key: checkout-123
Content-Type: application/json

{"orderId":"o-123","amount":120000,"currency":"VND"}
~~~

Các trường hợp test:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Gửi một lần | Tạo một payment hợp lệ |
| Gửi lại cùng key + cùng nội dung | Trả cùng kết quả/cùng operation, không tạo payment mới |
| Hai request đồng thời cùng key | Chỉ một side effect được commit |
| Cùng key nhưng payload khác | Bị từ chối theo hợp đồng, không âm thầm tạo giao dịch khác |
| Process crash sau commit trước response | Retry vẫn nhận được kết quả xác định |
| DB uniqueness violation | Không tạo duplicate; xử lý lỗi race có chủ đích |

Các test concurrency/idempotency **cần DB/transaction thật hoặc một mô hình có fidelity tương đương** nếu hệ thống dựa vào unique constraint, lock và transaction isolation. Mock repository không thể chứng minh behavior race của DB.

Với event consumer, test nhận cùng eventId nhiều lần, event đến lệch thứ tự và event đã bị xử lý nhưng ack chưa gửi. Kết quả nghiệp vụ phải theo contract idempotency, không theo số lần framework gọi handler.

## 15. Kiểm thử authentication và authorization khi dependency được kiểm soát

Một microservice thường xác minh JWT, mTLS workload identity hoặc gọi IdP/introspection endpoint. Test độc lập vẫn phải kiểm tra chính sách thật của service.

### 15.1. Những trường hợp cơ bản

- Không có token → 401 nếu endpoint yêu cầu authn.
- Token hết hạn, issuer sai, audience sai, chữ ký không hợp lệ → bị từ chối.
- Token hợp lệ nhưng thiếu role/scope → 403.
- Token hợp lệ, có scope phù hợp → thao tác được phép.
- User A truy cập tài nguyên tenant B → bị từ chối theo policy đa tenant.
- Service-to-service caller không được phép thay người dùng chỉ bằng header tự khai báo.
- Internal endpoint không bị mở ngoài dự kiến.
- Logs/metrics không chứa bearer token, refresh token hoặc private key.

### 15.2. JWT test keys và JWKS stub

Dùng khóa ký **chỉ dành cho test**, có thể dựng một JWKS endpoint local kiểm soát được:

- Public key đúng → xác minh thành công.
- Key ID không được tin → từ chối.
- Rotate key theo test fixture → xác minh cache/refresh behavior.
- JWKS endpoint unavailable → xử lý lỗi theo policy, không tự động bỏ qua xác minh.

Không dùng credential production, không gọi IdP production trong unit/component test. Test không nên phụ thuộc mật khẩu hoặc token có thể hết hạn ngoài dự kiến.

### 15.3. Kiểm tra security filter thật

Nếu test chỉ gọi trực tiếp application service với mock user, nó chưa kiểm tra HTTP filter, JWT decoder, method security hoặc route authorization. Cần có web/security integration test gửi request đến entry point thích hợp, xác nhận status và quyết định policy tại boundary.

Việc vô hiệu hóa security cho mọi test profile có thể làm những test "pass" nhưng không phát hiện endpoint mở nhầm.

## 16. Dữ liệu test phải đại diện nhưng được kiểm soát

### 16.1. Fixture nhỏ, có mục đích

Ví dụ đặt hàng:

~~~json
{
  "sku": "sku-test-1",
  "quantity": 2,
  "unitPrice": 100000,
  "currency": "VND",
  "inventoryAvailable": 5,
  "paymentAuthorized": true
}
~~~

Một fixture đủ cho một nhánh test. Không sử dụng bản dump production lớn làm mặc định nếu mục tiêu có thể được chứng minh bằng vài record.

### 16.2. Builder/factory

Một TestDataBuilder có thể tạo order mặc định hợp lệ, chỉ thay trường cần kiểm tra:

~~~java
OrderDraft valid = OrderDraftBuilder.valid()
        .sku("sku-test-1")
        .quantity(2)
        .build();

OrderDraft invalid = OrderDraftBuilder.valid()
        .quantity(0)
        .build();
~~~

Builder giúp giảm noise nhưng không che điều kiện quan trọng. Một test nên đọc được input liên quan ngay tại nơi assert.

### 16.3. Không tái sử dụng state mutable

Mỗi test tạo object mới hoặc reset fake. Một singleton fake repository với dữ liệu tồn từ bài test trước khiến kết quả phụ thuộc thứ tự.

Các test chạy song song cần:

- Database/schema/key prefix khác nhau, hoặc transaction isolation đủ đúng.
- Queue/topic/consumer group riêng hoặc cleanup có thể chứng minh.
- Stub server dùng port riêng.
- Clock, config, feature flags và registry state riêng.
- Không ghi shared static mutable state tùy tiện.

### 16.4. Sensitive data

Không dùng token thật, mật khẩu thật, thông tin thanh toán thật, email/định danh người dùng thật trong fixture. Dùng tài khoản sandbox/synthetic và keys giả; log lỗi test cũng phải có redaction.

## 17. Cấu hình môi trường test cô lập

Một môi trường component test điển hình:

~~~text
JUnit/Test Runner
    │
    ├─ Order Service: random web port, test profile
    │     ├─ DB URL → PostgreSQL container
    │     ├─ Inventory URL → WireMock random port
    │     ├─ Payment URL → WireMock random port
    │     ├─ Broker URL → RabbitMQ container, nếu thuộc test
    │     └─ Clock/ID/config → test-controlled
    │
    └─ Assertions: HTTP response, DB state, event/outbound calls
~~~

**Khuyến nghị thiết kế hạ tầng:**

1. Khởi động chỉ những dependency cần cho scenario.
2. Cấp port động, không ràng buộc môi trường chạy cụ thể.
3. Dùng config test rõ, không kế thừa bí mật từ developer machine.
4. Đóng server/container và connection đúng lifecycle.
5. Ghi trace/log khi fail, nhưng tránh in bí mật và dữ liệu nhạy cảm.
6. Tránh phụ thuộc DNS public, API quota hoặc dịch vụ shared.
7. Hạn chế timeout và retry để test thất bại có giới hạn thời gian.
8. Nếu dùng container cache/reuse, xác định rõ chính sách isolation và tránh state chéo test run.

### 17.1. Dùng mock server khi nào?

Khi cần xác minh mapping HTTP của Inventory client hoặc fault injection như 503/delay.

### 17.2. Dùng DB container khi nào?

Khi migration, query, constraint, transaction, locking, optimistic concurrency hoặc JSON serialization tới database quan trọng.

### 17.3. Dùng broker container khi nào?

Khi serializer, queue/topic declaration, ack/retry/DLQ, ordering hoặc consumer config có nguy cơ lỗi.

### 17.4. Dùng E2E environment khi nào?

Khi cần kiểm tra wiring/trust/routing thực giữa nhiều service, một số hành trình nghiệp vụ quan trọng hoặc hạ tầng chung không thể mô phỏng đầy đủ. Đừng biến mọi scenario unit thành E2E; chi phí và độ nhiễu sẽ cao.

## 18. Thiết kế test cho mỗi loại thay đổi

Một thay đổi mã nguồn nên dẫn đến loại test phù hợp:

| Thay đổi | Test chính | Test bổ sung khi rủi ro cao |
| --- | --- | --- |
| Quy tắc tính giá | Domain/unit | API test để kiểm tra mapping |
| HTTP response mapper | Client adapter với stub | Consumer contract |
| Field mới trong API | Consumer/provider contract | Smoke E2E |
| SQL query hoặc migration | DB integration container | Data migration rehearsal |
| Event schema mới | Serialization/consumer contract | Broker integration |
| Retry/timeout config | Fault injection ở HTTP stub | Controlled load test |
| JWT audience/role policy | Security integration | E2E auth smoke |
| Transaction/outbox | DB integration | Broker delivery/duplicate test |
| Hạ tầng deploy/routing | Deployment smoke test | End-to-end path |
| Performance optimization | Unit correctness + benchmark | Load test trên realistic environment |

**Mỗi lớp test nên có câu hỏi riêng.** Nếu 20 test cùng assert “POST /orders trả 201 với payload mẫu” thì số lượng test lớn nhưng độ phủ failure mode có thể thấp.

## 19. Tạo ma trận kiểm thử theo dependency

Đối với Order Service:

| Dependency | Happy path | Failure path | Consistency path | Test level |
| --- | --- | --- | --- | --- |
| Inventory HTTP | Reserve success | Timeout, 503, out-of-stock | Retry không giữ hàng trùng | Unit + HTTP stub + contract |
| Payment HTTP | Authorized | 401/403/503, unknown result | Idempotency và reconciliation | Unit + HTTP stub + provider sandbox khi cần |
| Order DB | Save/load | Unique violation, transaction error | Rollback và concurrent update | DB container |
| Event broker | Publish/consume | Broker unavailable, nack | Duplicate, replay, DLQ | Broker integration |
| Identity Provider | Valid token | Expired, wrong audience, unavailable JWKS | Key rotation/caching | Security test + local JWKS |
| Cache | Hit/miss | Timeout/unavailable | Stale reads, invalidation | Fake + Redis integration khi cần |
| Clock/scheduler | Deadline chưa đến | Deadline đã qua | Retry/backoff đúng thời gian | Fixed/mutable clock |
| Configuration | Flag on/off | Missing required setting | Test/prod mismatch | Context/config test |

Bảng là khung để người phát triển **xác định phạm vi**, không có nghĩa mọi hàng luôn cần đủ bốn loại test trong mỗi pull request.

### 19.1. Những điểm quan trọng trong flow Order

Kết hợp test:

- Validation ở boundary.
- Authorization, tenant isolation.
- Reservation success/fail.
- DB commit/rollback.
- Event publish after durable commit.
- Retry/idempotency.
- Downstream failure và user-facing outcome.
- Observability cho cả success/failure.

Đảm bảo cùng một event hoặc request ID có thể truy xuyên các thành phần khi điều tra.

## 20. Sự khác biệt giữa component test và end-to-end test

**Component test** kiểm tra **một service thực** nhưng dependency bên ngoài bị kiểm soát. Nó có thể:

- Chạy nhanh hơn E2E vì không cần cả hệ thống.
- Dễ tạo lỗi hiếm như timeout/chậm/duplicate.
- Có log và dữ liệu rõ để tìm root cause.
- Chạy trực tiếp trong PR pipeline.

**End-to-end test** kiểm tra đường tích hợp thật:

- Gateway routing, authentication, IAM, service discovery.
- TLS, certificate và network policy.
- Triển khai config, version tương thích.
- Luồng nghiệp vụ qua service thật và data stores.
- Runtime behavior không thể tái tạo hoàn toàn bằng stub.

Không nên chọn một trong hai rồi loại bỏ cái còn lại. Phần lớn behavior/failure scenarios nên nằm ở test nhỏ, kiểm soát được; E2E tập trung số lượng vừa đủ những đường đi quan trọng mà chỉ hệ thống tích hợp mới chứng minh được.

## 21. Test pyramid và kiểm soát chi phí CI

Một phân bố hợp lý thường có dạng:

~~~text
                     /\
                    /  \
                   / E2E\       Một số luồng trọng yếu
                  /------\
                 /Contract\     Ranh giới consumer/provider
                /----------\
               / Component  \  Service + controlled deps
              / Integration  \
             /----------------\
            /  Unit / Domain   \ Nhiều test nhanh và ổn định
           /____________________\
~~~

Pyramid chỉ là mô hình ưu tiên, **không phải số lượng tuyệt đối bắt buộc**. Một dự án chuyên dữ liệu/streaming có thể cần nhiều integration tests; một domain thuần tính toán có thể có nhiều unit tests.

### 21.1. Pipeline PR gợi ý

**Giai đoạn nhanh:**

- Compile, static analysis, unit tests.
- Domain/application service tests với fake/mock.
- Serialization/schema checks.

**Giai đoạn tích hợp cô lập:**

- Service HTTP component tests với mock server.
- PostgreSQL/container repository tests.
- Security filter/JWKS test.
- Broker/outbox tests.
- Consumer/provider contract verification phù hợp.

**Giai đoạn trước triển khai hoặc theo rủi ro:**

- Smoke tests trên environment được quản lý.
- Một số end-to-end user journeys.
- Load/performance hoặc chaos experiments theo lịch hay khi thay đổi thành phần liên quan.

Dùng cache build/dependency và reuse container thận trọng để giảm thời gian nhưng vẫn giữ isolation. Không giảm test coverage bằng cách bỏ các test quan trọng vì chúng chậm; trước hết điều tra setup, dữ liệu, cache và tài nguyên CI.

### 21.2. Gắn kết quả test với commit/artifact

Artifact dùng để deploy nên là phiên bản đã chạy test tương ứng. Nếu contract verify provider build A nhưng deploy provider build B, báo cáo “contract passed” không còn là bằng chứng đúng cho bản đang chạy.

Nên ghi:

- Commit SHA/build ID.
- Test suite và profile.
- Version của container dependency.
- Contract artifact version.
- JUnit XML/test reports.
- Logs/traces đã làm sạch khi test fail.

## 22. Quản lý flakiness: không che lỗi bằng retry vô hạn

**Flaky test** là test cho kết quả khác nhau khi đầu vào và thay đổi code không đổi. Nguyên nhân thường gặp:

- Thread scheduling/race.
- Static mutable state hoặc dữ liệu DB dùng chung.
- Fixed port collision.
- Test lệ thuộc thời gian thực, TTL hoặc time zone.
- Sleep thay cho condition.
- Network/shared dependency không sẵn sàng.
- Container không đủ CPU/memory.
- Broker message tồn từ test trước.
- Cấu hình cache/consumer asynchronous chưa được reset.
- Thứ tự chạy test làm state khác nhau.

**Quy trình xử lý:**

1. Lưu failure logs và seed/input để tái hiện.
2. Xác định bài test có thể chạy một mình và khi chạy song song không.
3. Kiểm tra dữ liệu, clock, scheduler, resource lifecycle, correlation ID.
4. Thay sleep bằng await condition hoặc virtual time.
5. Cô lập port/schema/queue/consumer group.
6. Kiểm tra dependency và timeouts.
7. Sửa nguyên nhân, chạy lại để xác nhận.

Test retry trong CI có thể là công cụ tạm thời để giảm ảnh hưởng, nhưng **không xem một lần chạy lại thành công là đã sửa flakiness**. Cần theo dõi tỷ lệ retry/failure và có owner khắc phục.

### 22.1. Không lạm dụng “test quarantine”

Nếu một test quan trọng bị bỏ qua vô thời hạn, pipeline xanh tạo cảm giác an toàn giả. Quarantine chỉ nên có điều kiện, lý do, owner và thời hạn xử lý.

## 23. Đảm bảo test không tác động ra ngoài

Một service test độc lập phải có **đường biên network và dữ liệu** được kiểm soát:

- Không gửi email/SMS thật.
- Không gọi Payment Provider production.
- Không tạo đơn/tài nguyên production.
- Không gửi message vào broker chung.
- Không đọc/ghi database staging chung nếu test yêu cầu isolation.
- Không dùng key/secret thật.
- Không xóa tài nguyên ngoài namespace test.
- Không dựa vào một service tình cờ đang chạy ở localhost của developer.

Có thể thiết kế test profile chặn outbound hosts không nằm trong allowlist local/test endpoints. Khi framework/CI hỗ trợ, dùng network isolation hoặc DNS policy để phát hiện request trốn khỏi stub. **Một HTTP request ngoài ý muốn cần làm test fail rõ ràng** thay vì vô tình gọi production.

Tuy nhiên, những test integration được chủ đích dùng provider sandbox phải ghi rõ boundary, credential test và chính sách làm sạch tài nguyên.

## 24. Observability của test run

Khi component test fail, người phát triển cần biết **điều gì thật sự xảy ra**:

- HTTP request/response đã làm sạch, status, route.
- Correlation/request ID.
- Test fixture và stub scenario ID.
- Service logs, exception class, stack trace khi cần.
- Trạng thái DB, outbox và transaction.
- Broker topic/queue, message ID, headers, delivery count.
- Retry count, backoff, timeout, Circuit Breaker state.
- Container startup error, health và resource metrics.

Lưu trace/log ở build artifact có TTL phù hợp. Cắt bỏ token, password, cookie, API key, payload nhạy cảm. Đối với thất bại bất đồng bộ, report cần nêu event ID đang chờ, số message consumer đã nhận và timeout của assertion.

**Thông tin quan sát chỉ là bằng chứng.** Không làm test pass chỉ vì log chứa “success”; phải assert state/result/side effect đúng contract.

## 25. Ví dụ thực hành: thiết kế một component test cho đặt hàng

### 25.1. Yêu cầu nghiệp vụ

Endpoint **POST /orders** nhận:

~~~json
{
  "sku": "sku-1",
  "quantity": 2
}
~~~

Hợp đồng:

- Khi quantity > 0 và Inventory giữ hàng thành công, trả 201 kèm orderId.
- Ghi order vào database.
- Tạo outbox event OrderCreated trong cùng transaction.
- Nếu Inventory báo hết hàng, trả lỗi nghiệp vụ phù hợp và không tạo order.
- Nếu Inventory timeout, trả trạng thái không thể xác nhận theo hợp đồng; không tự cho rằng reservation đã thất bại nếu downstream có thể đã xử lý.
- Mọi lệnh reserve mang requestId/idempotency key để kiểm soát trùng lặp.

### 25.2. Thiết lập

~~~text
Test runner
  ├─ Start PostgreSQL Testcontainer
  ├─ Run migrations
  ├─ Start Inventory stub server at random port
  ├─ Start Order Spring Boot at random port
  └─ Configure:
       inventory.base-url = stub URL
       datasource.url = container URL
       clock = fixed clock
       event delivery = test outbox mode
~~~

### 25.3. Test thành công

**Arrange:**

- Stub Inventory trả 200 với reservationId hợp lệ.
- DB rỗng.
- requestId cố định.

**Act:** POST /orders.

**Assert:**

1. HTTP 201, response schema đúng.
2. Một order row được commit với sku/quantity chính xác.
3. Một outbox OrderCreated có orderId/requestId tương ứng.
4. Stub Inventory nhận đúng một reserve call chứa requestId.
5. Không có credential hoặc payload nhạy cảm trong logs.
6. Test không phụ thuộc service bên ngoài.

### 25.4. Test Inventory hết hàng

**Arrange:** Stub trả kết quả OUT_OF_STOCK hợp lệ theo contract.

**Assert:**

- HTTP status và response đúng với quy ước nghiệp vụ.
- Không có order row mới.
- Không có OrderCreated outbox event.
- Không gọi Payment.
- Metric/outcome phân loại là business rejection, không là lỗi hạ tầng nếu đó là contract.

### 25.5. Test Inventory timeout

**Arrange:** Stub delay vượt HTTP client timeout.

**Assert:**

- Request Order kết thúc trong deadline hợp lý.
- Không ghi order được xác nhận khi kết quả reservation chưa rõ.
- Không retry vượt chính sách.
- Response cho biết trạng thái phù hợp, không hứa chắc “hết hàng” hoặc “đã giữ hàng”.
- Observability có timeout/correlation ID.
- Nếu thiết kế có reconciliation, phát đúng trạng thái PENDING/UNKNOWN để tiếp tục đối soát.

### 25.6. Test idempotency đồng thời

**Arrange:** Hai request cùng idempotency key, cùng payload, gửi gần đồng thời vào Order service thật.

**Assert:**

- Không có hai order độc lập khi contract yêu cầu một operation.
- DB constraint/locking thực bảo vệ race.
- Outbox event không tạo side effect trùng không kiểm soát.
- Client nhận kết quả nhất quán.
- Transaction behavior được kiểm chứng qua DB test chứ không dựa vào fake đơn luồng.

### 25.7. Test contract Inventory

Tách khỏi component suite:

- Consumer Order phát hành contract của request reserve và response cần dùng.
- Provider Inventory chạy verification trên trạng thái dữ liệu đã kiểm soát.
- Gate deployment khi phiên bản provider dự kiến không tương thích.

Khi cả component test và provider verification đều pass, độ tin cậy lớn hơn so với chỉ stub theo một fixture do Order tự nghĩ ra.

## 26. Cách đánh giá một bài test có giá trị

Trước khi thêm test mới, trả lời:

1. **Failure mode nào cần phát hiện?** Logic sai, serialization, DB constraint, timeout hay contract mismatch?
2. **SUT là gì?** Hàm, service instance, adapter, provider hay toàn hệ thống?
3. **Boundary nào phải thật?** Nếu test SQL dialect, cần PostgreSQL; nếu test domain rule, không cần.
4. **Dependency nào cần kiểm soát?** HTTP stub, clock, fake repository, local JWKS, broker container?
5. **Outcome được quan sát ở đâu?** Return value, HTTP response, database, event, outbound request?
6. **Điều gì khiến test deterministic?** ID, thời gian, seed, concurrency, cleanup?
7. **Khi fail có thể chỉ ra lỗi của SUT không?** Hay chỉ là shared staging thay đổi?
8. **Có khả năng bỏ sót mismatch với provider không?** Nếu có, bổ sung contract verification.
9. **Chi phí chạy và bảo trì tương xứng rủi ro không?** Tránh nhiều E2E test trùng nhau.
10. **Có thể chạy an toàn trong CI song song không?** Không rò request, dữ liệu và credential.

Một test có ý nghĩa khi nó phát hiện được loại lỗi cụ thể và cung cấp bằng chứng dễ truy nguyên.

## 27. Sai lầm thường gặp

**Sai lầm 1 — Mock tất cả và gọi đó là integration test.** Không kiểm tra được giao thức, query, migration hoặc cấu hình thật.

**Sai lầm 2 — Dùng shared staging làm dependency cho mọi unit/component test.** Kết quả phụ thuộc deploy, dữ liệu, hạn mức và network.

**Sai lầm 3 — Để test thực hiện network request ngoài ý muốn.** Có thể vô tình thay dữ liệu môi trường khác; cần default-deny/allowlist boundary.

**Sai lầm 4 — Fake DB và kết luận transaction đúng.** Fake Map không tái hiện lock, rollback, isolation hoặc constraint.

**Sai lầm 5 — Chỉ test response 200.** Các lỗi khó và tốn kém nhất thường ở timeout, duplicate, retries, partial commit và provider mismatch.

**Sai lầm 6 — Verify mọi lời gọi nhỏ trên mock.** Refactor bình thường làm test hỏng dù contract vẫn giữ.

**Sai lầm 7 — Stub body theo giả định không kiểm chứng.** Provider đổi schema nhưng consumer test vẫn xanh; cần contract.

**Sai lầm 8 — Dùng Thread.sleep dài để chờ async.** Test chậm, flaky và không chứng minh điều kiện thật.

**Sai lầm 9 — Không kiểm soát clock và ID.** Test phụ thuộc ngày giờ, deadline, time zone hoặc random seed.

**Sai lầm 10 — Reuse dữ liệu DB, queue và static state giữa các test.** Test order/parallelism làm thay kết quả.

**Sai lầm 11 — Bỏ security filter trong mọi API test.** Endpoint có thể bị mở mà suite không phát hiện.

**Sai lầm 12 — Chỉ assert HTTP status mà không kiểm tra DB/event/outbound side effect.** Trả 201 không chứng minh transaction đã đúng.

**Sai lầm 13 — Không có test idempotency/race.** Retry trong network làm tạo giao dịch trùng.

**Sai lầm 14 — Coi timeout là chắc chắn downstream không làm gì.** Kết quả có thể chưa xác định; cần đối soát hoặc idempotency.

**Sai lầm 15 — Sử dụng dữ liệu hoặc token production trong test.** Có nguy cơ an toàn, vi phạm phân quyền và tác động môi trường thật.

**Sai lầm 16 — Thấy test flaky rồi tăng timeout vô hạn.** Che nguyên nhân state/concurrency/network, làm suite ngày càng chậm.

**Sai lầm 17 — E2E test quá nhiều nhưng thiếu unit/integration.** Khó bao phủ failure mode và khó tìm root cause.

**Sai lầm 18 — Chạy contract verification sai version.** Bằng chứng pass không gắn với artifact thực tế được triển khai.

## 28. Bài tập tự luyện

### Bài tập A — Chọn test double

OrderService tính tổng tiền từ danh sách item. Nó gọi PriceCatalogClient để lấy unit price. Cần kiểm tra quy tắc áp dụng coupon, discount cap và rounding.

**Câu hỏi:** Cần PostgreSQL hay Price Service thật không?

**Hướng giải:** Unit test có thể dùng PriceCatalogClient fake/stub cung cấp các mức giá cố định. Cần các assertions trên tổng tiền và rounding. Thêm HTTP client adapter/contract tests riêng để xác minh mapping giá ngoài process.

### Bài tập B — Cảnh báo giả từ shared dependency

Test của Order thỉnh thoảng fail 503 vì Inventory staging đang được một nhóm khác deploy. Code Order không đổi.

**Câu hỏi:** Làm gì để test PR đáng tin hơn?

**Hướng giải:** Dùng local HTTP stub có fixture cho response/timeout; giữ một suite E2E/smoke riêng trên môi trường tích hợp thật. Contract verification giúp giảm rủi ro fixture lệch provider.

### Bài tập C — Database constraint

Hai request đồng thời cùng idempotency key tạo hai order vì application check-then-insert không atomic.

**Câu hỏi:** Test mức nào sẽ phát hiện?

**Hướng giải:** Test integration với DB thật, unique constraint và concurrent requests. Fake repository đơn luồng khó tái hiện race; application phải xử lý duplicate conflict theo contract.

### Bài tập D — Message duplicate

Consumer xử lý OrderCreated, gửi email và ack. Broker redeliver event vì ack bị mất.

**Câu hỏi:** Test gì và làm sao không gửi email lần hai?

**Hướng giải:** Unit test handler với duplicate event, integration test broker ack/retry và thiết kế idempotency/dedup tại ranh giới side effect. Fake đếm gửi chỉ là bước đầu, cần kiểm tra crash/concurrency theo mức rủi ro.

### Bài tập E — Contract mismatch

Order stub trả field availableQuantity, còn Inventory production đã đổi thành stockCount.

**Câu hỏi:** Vì sao unit/component test vẫn pass, và cần thêm gì?

**Hướng giải:** Stub do Order quản lý bị lệch provider. Thêm consumer/provider contract verification chạy provider build tương ứng; khi thay schema, gate deploy nếu breaking change.

### Bài tập F — JWT security

Unit test OrderApplicationService dùng actorId=admin nên pass, nhưng HTTP endpoint thiếu kiểm tra audience JWT.

**Câu hỏi:** Test gì còn thiếu?

**Hướng giải:** Security integration test đi qua HTTP filter với local signing key/JWKS và token audience sai; phải nhận 401/403 theo policy thay vì gọi vào nghiệp vụ.

### Bài tập G — Timeout và giao dịch chưa chắc chắn

Payment HTTP request timeout sau 500 ms; Payment có thể đã trừ tiền. Order tự retry bằng một requestId mới.

**Câu hỏi:** Vấn đề gì và cách kiểm thử?

**Hướng giải:** Có nguy cơ thanh toán trùng. Cần idempotency key ổn định, truy vấn trạng thái/reconciliation, HTTP stub/fake mô phỏng “side effect đã thực hiện nhưng response mất” và integration test xác nhận không phát side effect thứ hai.

## 29. Checklist triển khai chiến lược kiểm thử

### Cấu trúc test

- [ ] SUT và ranh giới rõ ràng cho từng loại test.
- [ ] Unit test tập trung domain/application behavior với fake/mock/stub phù hợp.
- [ ] Service/component test chạy service thật, dependency bên ngoài có thể điều khiển.
- [ ] Integration test dùng DB/broker/cache đúng công nghệ khi cần kiểm tra semantics.
- [ ] Contract test nối kỳ vọng consumer với verification provider.
- [ ] E2E test tập trung luồng nghiệp vụ thực sự cần hệ thống nhiều service.
- [ ] Các loại test không chỉ lặp lại cùng một happy path.

### Tính tái lập

- [ ] Không phụ thuộc shared staging cho test yêu cầu isolation.
- [ ] Clock, ID, random seed và config được kiểm soát.
- [ ] Test data nhỏ, độc lập, tự dọn dẹp.
- [ ] Ports/schema/queues được cô lập khi chạy song song.
- [ ] Async assertions đợi condition, không sleep tùy tiện.
- [ ] Không có request đến production/secret thật; test fixture đã làm sạch.

### Tình huống lỗi

- [ ] HTTP 4xx/5xx, timeout, malformed response và network failure.
- [ ] Retry/backoff, Circuit Breaker, Bulkhead và degraded outcome theo policy.
- [ ] DB transaction, constraint, rollback, race/idempotency.
- [ ] Broker duplicate, retry, ordering, DLQ và serialization.
- [ ] Security 401/403, issuer/audience/signature, tenant isolation.
- [ ] Contract compatibility với provider version được triển khai.

### CI và bằng chứng

- [ ] PR pipeline chạy test nhanh trước, integration/contract khi phù hợp.
- [ ] Test reports gắn commit/artifact và dependency versions.
- [ ] Logs/traces hỗ trợ chẩn đoán nhưng không rò credential/PII.
- [ ] Flaky tests có owner, root cause và kế hoạch sửa.
- [ ] Có smoke/E2E kiểm tra wiring thực trước hoặc sau deployment.
- [ ] Pipeline phân biệt test failure do code và infrastructure failure để đội ngũ phản ứng đúng.

## 30. Tổng kết

**Kiểm thử dịch vụ độc lập với các phụ thuộc được kiểm soát** là cách giữ microservice đủ cô lập để có kết quả nhanh, tái lập và dễ chẩn đoán, đồng thời vẫn kiểm chứng đúng nơi các lỗi tích hợp có thể xảy ra.

- **Dùng fake/mock/stub** để điều khiển collaborator ở cấp unit và xác nhận quy tắc nghiệp vụ.
- **Dùng HTTP/gRPC stub server** để kiểm tra serialization, network client và các trường hợp lỗi của dependency.
- **Dùng database/broker/container thật** để kiểm chứng transaction, migration, ack, concurrency và các semantics không thể giả chính xác bằng mock.
- **Dùng consumer/provider contract test** để tránh việc fixture của consumer khác provider thật.
- **Dùng một số E2E test có chọn lọc** để xác nhận route, trust, deployment và luồng nghiệp vụ liên service.

Điểm cốt lõi không phải “mock càng nhiều càng tốt”, mà là **chọn ranh giới phù hợp với điều muốn chứng minh, kiểm soát được đầu vào/phụ thuộc và giữ bằng chứng có thể tái tạo**. Một test đáng tin phải cho biết chính xác *hành vi nào đã được chứng minh*, *điều gì chưa được chứng minh* và *đâu là lớp test phù hợp để kiểm tra phần còn lại*.
