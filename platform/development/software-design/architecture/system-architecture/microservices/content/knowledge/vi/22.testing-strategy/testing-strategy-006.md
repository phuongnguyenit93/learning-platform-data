# Kiểm thử luồng liên dịch vụ mà không phụ thuộc môi trường dùng chung

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Chiến lược kiểm thử. Bài viết trình bày cách kiểm thử luồng nghiệp vụ xuyên qua nhiều microservice bằng cách kiểm soát ranh giới, dữ liệu và dependency của từng bài kiểm thử, nhằm có kết quả lặp lại được trên máy lập trình viên và CI mà không cần chờ một môi trường staging/integration dùng chung luôn sẵn sàng.

## 1. Vì sao môi trường dùng chung trở thành nút nghẽn?

Một thao tác đặt hàng có thể đi qua API Gateway → Order Service → Inventory Service → Payment Service → message broker → Notification Service. Mỗi service có database, phiên bản deploy, cấu hình và nhịp phát triển riêng. Nếu mọi testcase đều gọi vào staging chung, một lỗi test có thể bắt nguồn từ bất kỳ mắt xích nào, kể cả khi code vừa thay đổi hoàn toàn chính xác.

Các vấn đề thường gặp:

- **Chờ lịch deploy:** Order team phải chờ Inventory, Payment hoặc hạ tầng triển khai phiên bản mới thì mới kiểm thử được.
- **Trạng thái dữ liệu trôi:** test A trừ tồn kho, test B tạo order trùng ID, một background job đã xử lý message từ lần chạy trước.
- **Va chạm CI:** hai pull request cùng sử dụng một account, tenant, queue, topic hoặc database và làm hỏng fixture của nhau.
- **Flaky tests:** cùng commit, một lúc pass một lúc fail vì network, VPN, quota, feature flag, cache hoặc service khác đang restart.
- **Không tạo được lỗi cố ý:** không thể ép Payment staging trả 503, timeout sau khi nhận transaction hoặc duplicate webhook mà không gây ảnh hưởng người khác.
- **Phản hồi chậm:** phải build/deploy nhiều service, chờ pod sẵn sàng và dọn dữ liệu trước mỗi vòng thử.
- **Khó xác định owner:** lỗi HTTP 500 trong E2E có thể là bug logic của Order, schema của Inventory, config secret, RBAC hoặc broker.

**Mục tiêu:** chuyển phần lớn kiểm thử nghiệp vụ và hợp đồng sang phạm vi tự kiểm soát (unit, component, integration, contract), chỉ giữ một số bài workflow/deployed smoke để phát hiện rủi ro tương tác thật và hạ tầng. Cách này cải thiện tốc độ phản hồi nhưng vẫn duy trì bằng chứng về tính đúng đắn của hệ phân tán.

## 2. Thế nào là kiểm thử độc lập?

Một bài kiểm thử độc lập không dựa trên một trạng thái có sẵn của môi trường dùng chung. Nó đáp ứng:

1. Có **system under test (SUT)** rõ ràng: một service, một nhóm service hoặc một workflow.
2. Mỗi dependency là thành phần thật do test khởi tạo hoặc là test double được định nghĩa rõ hành vi.
3. Phiên bản artifact, schema migration, contract và fixture có thể pin để tái hiện.
4. Dữ liệu test tự tạo và được dọn trong phạm vi sở hữu; không dựa vào user/order có sẵn ở staging.
5. Thời gian, timeout, retry, random ID, feature flag và các sự cố cần mô phỏng được điều khiển.
6. Có thể chạy song song và không làm thay đổi trạng thái của testcase khác.
7. Khi fail, kết quả chứa thông tin đủ để phân biệt lỗi nghiệp vụ, contract, serialization, transaction, messaging và hạ tầng.

**Độc lập không đồng nghĩa mock mọi thứ.** PostgreSQL, Kafka hoặc Redis thật có thể chạy trong container tạm do test sở hữu. Ngược lại, gọi một Payment Provider thật chỉ để test chính sách xử lý lỗi 409 của Order thường không cần thiết; stub có response xác định sẽ nhanh và ít nhiễu hơn.

## 3. Chọn cấp kiểm thử theo rủi ro cần phát hiện

| Cấp | Những gì chạy thật | Dependency thường thay thế | Mục tiêu |
| --- | --- | --- | --- |
| Unit | Một class/hàm và business rule | Repository/client fake hoặc mock | Validation, tính toán, state transition |
| Component | Một microservice với HTTP/API và wiring thật | External HTTP/gRPC downstream | Request → xử lý → lưu state → outbound behavior |
| Integration | Service + database/broker/cache thật | Service không nằm trong SUT | SQL, migration, transaction, serializer, offset/ack |
| Consumer contract | Client code với contract mock | Provider thật | Consumer gửi request và xử lý response đúng hợp đồng |
| Provider verification | Provider implementation thật và test state | External dependency của provider | Provider đáp ứng hợp đồng đã publish |
| Workflow/slice | Một nhóm service thật và dependency tạm | Provider ngoài phạm vi | Tương tác và state nhiều service có đúng? |
| Deployed smoke/E2E | Artifact và platform triển khai thật | Ít hoặc không, theo mục tiêu | DNS, ingress, TLS, IAM, service discovery, config |

Không yêu cầu mọi testcase đều là E2E. Một unit test tìm bug tính thuế nhanh và chính xác hơn khởi động toàn bộ hệ thống. Một integration test PostgreSQL thật đáng tin hơn mock repository nếu muốn kiểm tra locking và migration. Một consumer contract phát hiện API drift của Inventory trước khi Order và Inventory gặp nhau ở staging.

**Test oracle** là điều kiện đúng/sai rõ ràng. Ở component test, có thể xác minh Order đã phát request đúng tới Inventory stub; muốn chứng minh Inventory thực đã trừ hàng, phải có workflow test chạy Inventory thật hoặc bài kiểm thử sở hữu bởi Inventory.

## 4. Bài toán mẫu: tạo đơn và thanh toán

~~~text
Client
  |
  v
API Gateway
  |
  v
Order Service ----------> Inventory Service
  |                              |
  +--------------------------> Payment Service
  |                              |
  |                        External Payment Provider
  |
  +--> Order DB
          |
          +--> Outbox --> Kafka/RabbitMQ --> Notification Service
~~~

Một kịch bản nghiệp vụ:

- **Given:** SKU-001 còn 5 sản phẩm, Payment chấp nhận authorization, chưa có command nào dùng idempotency key K-001.
- **When:** client gửi POST /orders với SKU-001, số lượng 2, key K-001.
- **Then:** API trả response đúng contract; Order có trạng thái hợp lệ; reservation và payment không có side effect trùng; event được ghi/publish đúng theo bảo đảm của thiết kế.

Ba cấp phù hợp:

**Component test Order:** chạy Order thật + PostgreSQL tạm; Inventory/Payment trả response từ WireMock. Xác minh request, DB, outbox và error-handling của Order.

**Workflow slice test:** chạy Order + Inventory thật, mỗi service có DB riêng, broker tạm; Payment Provider là stub. Xác minh reservation và trạng thái Order nhất quán.

**Deployed smoke test:** chạy image thật trên Kubernetes/managed platform; xác minh ingress, identity, routing, certificate, config và một luồng chính. Không dùng smoke test cho hàng trăm biến thể dữ liệu đã được component/contract tests bao phủ.

## 5. Kiến trúc component test tự kiểm soát

~~~text
              Test Runner (JUnit/pytest)
                        |
                        | HTTP
                        v
                 Order Service thật
                  /           \
                 v             v
           PostgreSQL      Outbound HTTP Client
           test container      /           \
             + migration      v             v
             + outbox       Inventory     Payment
                            WireMock      WireMock
                               \             /
                              Contract fixtures
~~~

Vòng đời khuyến nghị:

1. Sinh run ID, chọn phiên bản image/container và thời hạn cho suite.
2. Khởi động database, broker nếu cần và các stub trên port động.
3. Chạy migration và nạp runtime config trước khi service nhận traffic.
4. Seed dữ liệu tối thiểu, đăng ký stub cho testcase.
5. Khởi động hoặc dựng context SUT, chờ readiness.
6. Gửi request hoặc phát message khởi động workflow.
7. Assert API response, durable state, outbox/message và các interaction cần thiết.
8. Nếu có xử lý bất đồng bộ, chờ trạng thái cuối bằng condition polling có deadline.
9. Khi fail, lưu report, structured logs và request journal đã lọc thông tin nhạy cảm.
10. Dừng consumer/process, cleanup resource thuộc test run.

Khi test sở hữu tất cả resource, nhiều PR có thể chạy đồng thời mà không xóa dữ liệu lẫn nhau. Nếu một suite tái sử dụng broker/container để tiết kiệm startup, các test bên trong vẫn cần topic/schema/ID được cách ly.

## 6. Thiết kế test seam mà không sửa đường đi nghiệp vụ

Các URL, connection string và feature flag nên được inject qua config. Ví dụ:

~~~text
Production:
  INVENTORY_URL=https://inventory.internal
  PAYMENT_URL=https://payment.internal
  DB_URL=jdbc:postgresql://orders-db/orders

Component test:
  INVENTORY_URL=http://127.0.0.1:<inventory-port>
  PAYMENT_URL=http://127.0.0.1:<payment-port>
  DB_URL=jdbc:postgresql://<container-host>:<mapped-port>/orders_test
~~~

Service có thể dùng interface và adapter:

~~~java
public interface InventoryClient {
    Reservation reserve(String sku, int quantity, String idempotencyKey);
}

public final class PlaceOrderService {
    private final InventoryClient inventory;
    private final OrderRepository orders;

    public PlaceOrderService(
        InventoryClient inventory, OrderRepository orders
    ) {
        this.inventory = inventory;
        this.orders = orders;
    }

    public Order place(PlaceOrder command) {
        Reservation result = inventory.reserve(
            command.sku(), command.quantity(), command.idempotencyKey()
        );
        if (!result.accepted()) {
            throw new OutOfStockException(command.sku());
        }
        return orders.create(command);
    }
}
~~~

Unit test inject fake InventoryClient; component test dùng HTTP client thật trỏ tới stub; workflow test trỏ tới Inventory Service thật. Logic nghiệp vụ không đổi. **Tránh nhánh if (env == test) trả thành công giả hoặc tắt authorization/transaction** vì khi đó đường đi được kiểm tra khác production.

## 7. Stub, mock, fake và service thật

| Công cụ/phương pháp | Thích hợp cho | Cần cảnh giác |
| --- | --- | --- |
| Stub HTTP | Response thành công, hết hàng, timeout, 503 | Stub có thể lệch provider thật |
| Mock | Xác minh một interaction bắt buộc | Test quá gắn implementation detail |
| Fake stateful | Unit test các chuỗi state đơn giản | Fake trở thành bản sao sai của production |
| Contract mock | Consumer test theo artifact có version | Chỉ bao phủ những interaction mô tả |
| Provider verification | Kiểm chứng implementation theo contract | Không kiểm tra network/IAM production |
| Container DB/broker thật | SQL, migration, transaction, offset/ack | Tốn startup, cần isolation |
| Service thật trong slice | Tích hợp thực giữa các service | Suite nặng, khó khoanh lỗi hơn |

Stub nên strict: request sai endpoint/method/header/body phải thất bại rõ, không trả 200 mặc định cho mọi URL. Nên có response cho error codes và độ trễ theo contract. Không cài lại toàn bộ logic reservation/thanh toán vào stub; nếu cần chứng minh logic đó, hãy chạy service sở hữu nó.

## 8. Consumer-driven contract testing

HTTP integration giữa hai nhóm thường thay đổi độc lập. Consumer-driven contract (CDC) tách kiểm chứng tương thích khỏi lịch deploy staging:

~~~text
Order consumer
    |
    +-- mô tả request/response mà Order sử dụng
    +-- chạy consumer test trên mock server theo contract
    +-- publish contract artifact có version
                               |
                               v
Inventory provider
    |
    +-- chạy implementation thật trong test context
    +-- seed provider state tương ứng
    +-- verify interaction từ các contract đang hoạt động
    +-- publish verification result
                               |
                               v
Compatibility gate trước khi deploy
~~~

Có thể dùng Pact, Spring Cloud Contract hoặc một giải pháp tương đương. Điều kiện cốt lõi: **hai phía cùng sử dụng một contract artifact**; không chỉ viết hai bộ mock độc lập.

Một interaction minh họa:

~~~http
POST /reservations HTTP/1.1
Content-Type: application/json

{"sku":"SKU-001","quantity":2,"idempotencyKey":"K-001"}
~~~

Response khi còn hàng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"reservationId":"res-001","accepted":true}
~~~

Response khi hết hàng:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json

{"code":"OUT_OF_STOCK","available":0}
~~~

Contract cần ghi rõ method/path, required headers, schema, kiểu dữ liệu, nullable/optional fields, response codes, error mapping và state của provider. Nếu API có versioning hoặc idempotency semantics, đưa chúng vào hợp đồng khi liên quan.

### Rolling deployment và compatibility matrix

| Consumer | Provider | Điều kiện |
| --- | --- | --- |
| Order v1 | Inventory v1 | Baseline đang chạy |
| Order v1 | Inventory v2 | Provider mới vẫn phục vụ consumer cũ |
| Order v2 | Inventory v1 | Consumer mới chỉ deploy nếu provider cũ đáp ứng |
| Order v2 | Inventory v2 | Trạng thái mong muốn sau rollout |

Chỉ những tổ hợp có thể cùng tồn tại thực tế mới cần được gate. Thêm trường tùy chọn thường dễ tương thích hơn đổi tên field bắt buộc hoặc thay enum mà không có thời gian chuyển tiếp. **Contract pass không chứng minh SLO, throughput, TLS hoặc quyền truy cập trên môi trường triển khai**; những việc đó thuộc suite khác.

## 9. Ví dụ Spring Boot + Testcontainers + WireMock

Với Spring Boot 3, JUnit 5, PostgreSQL Testcontainers và WireMock, có thể khởi động service thật cùng một PostgreSQL tạm, inject URL của stub vào HTTP client. Tên endpoint/properties dưới đây mang tính minh họa, phải khớp ứng dụng thực tế.

~~~java
import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.*;
import static org.assertj.core.api.Assertions.assertThat;

import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.*;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PlaceOrderComponentIT {
    @Container
    static final PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16-alpine");

    static final WireMockServer inventory =
        new WireMockServer(wireMockConfig().dynamicPort());

    static final WireMockServer payment =
        new WireMockServer(wireMockConfig().dynamicPort());

    static {
        inventory.start();
        payment.start();
    }

    @DynamicPropertySource
    static void configure(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", db::getJdbcUrl);
        registry.add("spring.datasource.username", db::getUsername);
        registry.add("spring.datasource.password", db::getPassword);
        registry.add("clients.inventory.url", inventory::baseUrl);
        registry.add("clients.payment.url", payment::baseUrl);
    }

    @Autowired TestRestTemplate http;

    @BeforeEach
    void registerStubs() {
        inventory.resetAll();
        payment.resetAll();

        inventory.stubFor(post(urlEqualTo("/reservations"))
            .willReturn(okJson(
                "{\"reservationId\":\"res-001\",\"accepted\":true}"
            )));
        payment.stubFor(post(urlEqualTo("/authorizations"))
            .willReturn(okJson(
                "{\"authorizationId\":\"auth-001\",\"status\":\"APPROVED\"}"
            )));
    }

    @Test
    void createsOrderWhenDependenciesAccept() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        String body = """
            {"commandId":"cmd-001","sku":"SKU-001","quantity":1}
            """;
        ResponseEntity<String> response = http.postForEntity(
            "/orders",
            new HttpEntity<>(body, headers),
            String.class
        );

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
        inventory.verify(1, postRequestedFor(urlEqualTo("/reservations")));
        payment.verify(1, postRequestedFor(urlEqualTo("/authorizations")));

        // Trong dự án thật: assert trạng thái Order trong DB,
        // record outbox và tính idempotent khi gửi lại command.
    }

    @AfterAll
    static void stopStubs() {
        inventory.stop();
        payment.stop();
    }
}
~~~

Ví dụ giả định Order Service thực sự có endpoint POST /orders và dùng các property được inject. Cần đồng bộ dependency versions, DB migrations, test state reset, client configuration và lifecycle. Khi test chạy HTTP ở server thread khác, annotation @Transactional trên test method **không tự rollback giao dịch của request đó**.

Nếu test nhiều class song song, không dùng chung một WireMockServer rồi gọi resetAll từ các class khác nhau; như vậy testcase có thể xóa stub mapping của nhau. Có thể tạo server riêng, fixture riêng hoặc cấu hình suite không parallel cho phần không được cách ly.

### Mô phỏng 503 và timeout

Một test riêng có thể thay response của Payment bằng:

~~~java
payment.stubFor(post(urlEqualTo("/authorizations"))
    .willReturn(aResponse()
        .withStatus(503)
        .withHeader("Content-Type", "application/json")
        .withBody("{\"code\":\"TEMPORARY_UNAVAILABLE\"}")));
~~~

Kỳ vọng phụ thuộc nghiệp vụ: Order phải có trạng thái an toàn, không ghi nhận đã thanh toán khi chưa xác minh, retry hữu hạn và xử lý reconciliation/compensation nếu thiết kế yêu cầu. Có thể mô phỏng slow response hoặc ngắt connection để kiểm tra client timeout. Điều quan trọng là **assert outcome**, không chỉ số lần method mock được gọi.

## 10. Vì sao dùng database thật trong integration test?

H2 và mock repository không tái hiện đầy đủ PostgreSQL/MySQL về SQL dialect, locking, isolation level, constraint, transaction và migration. Nếu application chạy production trên PostgreSQL, một PostgreSQL container cùng major version và migration thật sẽ bắt được lỗi tích hợp mà mock không thấy.

Test DB cần:

- Migration tự chạy và kết thúc trước khi SUT nhận traffic.
- Schema/DB riêng hoặc chiến lược cleanup đúng từng testcase.
- Seed dữ liệu nhỏ, có thể xác định được.
- Assertion kiểm tra durable state khi có yêu cầu.
- Resource limit/timeout để tránh container treo.
- Không sử dụng shared production/staging credentials.

Nếu test gửi HTTP qua RANDOM_PORT, giao dịch của application không nằm trong test transaction; phải cleanup hoặc tái tạo database để không làm lệch test tiếp theo. Với async consumers, chờ xử lý xong trước khi truncate hoặc destroy state.

## 11. Message broker và kiểm thử luồng bất đồng bộ

Khi Order tạo outbox event và publisher gửi Kafka/RabbitMQ, việc mock phương thức send() chỉ xác minh lời gọi, chưa xác minh serialization, partition key, topic, ack, offset, consumer deserialization hay redelivery.

~~~text
Order Service thật
      |
      v
Order DB + Outbox (PostgreSQL tạm)
      |
      v
Publisher thật
      |
      v
Kafka/RabbitMQ container
      |
      v
Consumer thật / Test consumer
      |
      v
Assert event + business side effect
~~~

Với Kafka, mỗi run có topic hoặc namespace tên riêng và consumer group ID riêng. Đảm bảo consumer đã subscribe/assigned trước khi phát record nếu test dựa vào việc nhận từ thời điểm đó; kiểm soát offset. Với RabbitMQ, tách queue/exchange/vhost hoặc broker container riêng; không để unacked/redelivery từ lần test cũ làm nhiễu.

Một event contract có thể có:

~~~json
{
  "eventId": "evt-001",
  "eventType": "OrderPaid",
  "schemaVersion": 2,
  "occurredAt": "2026-11-12T02:00:00Z",
  "aggregateId": "ord-001",
  "correlationId": "flow-001",
  "data": {
    "orderId": "ord-001",
    "amount": 125000,
    "currency": "VND"
  }
}
~~~

Cần test schema, field types, key/headers, version compatibility và cách consumer xử lý field thiếu/không biết. Nếu dùng Avro/Protobuf/schema registry, kiểm thử với cấu hình compatibility tương ứng. Event cũ tồn trên broker có thể được xử lý bởi consumer mới sau rollout.

## 12. Outbox, replay và idempotency

Một workflow event-driven đáng tin nên kiểm tra:

1. Ghi Order và outbox trong cùng transaction nếu dùng transactional outbox.
2. Publisher chỉ đánh dấu đã phát sau khi có cơ sở xác nhận broker.
3. Nếu publisher crash sau send nhưng trước khi cập nhật trạng thái outbox, message có thể được phát lại.
4. Consumer chỉ ack/commit sau khi side effect quan trọng đã hoàn tất theo contract.
5. Khi cùng eventId được delivery hai lần, không tạo hai tác động nghiệp vụ nếu chính sách yêu cầu idempotency.
6. Poison message có retry budget, delayed retry hoặc DLQ, không lặp vô hạn.
7. Event out-of-order không đưa aggregate trở lại state cũ nếu có version/sequence guard.

Không khẳng định exactly-once delivery chỉ vì đã có retry hoặc transaction. Với at-least-once messaging, test có thể chứng minh **effectively-once business effect** bằng deduplication/idempotency, trong khi broker vẫn delivery nhiều lần.

## 13. Dữ liệu, thời gian và tính quyết định

### Seed và cleanup theo phạm vi

| Resource | Isolation | Lưu ý |
| --- | --- | --- |
| DB | Container/schema/database riêng | Không truncate dữ liệu người khác |
| Kafka | Topic + consumer group theo run ID | Tránh offset/message từ run trước |
| RabbitMQ | Queue/exchange/vhost riêng | Requeue/ack phải được kiểm soát |
| Redis | Namespace/key prefix hoặc instance riêng | Không FLUSHALL trên Redis chung |
| Object storage | Bucket/prefix riêng | Cleanup chỉ trong phạm vi sở hữu |
| HTTP stubs | Server/mapping/journal riêng | Không reset chéo testcase |
| Feature flag | Snapshot/fake config riêng | Không dùng flag staging thay đổi bất ngờ |
| Test account | Tenant và quota riêng | Không chia sẻ một người dùng test toàn CI |

Mỗi test tự xây fixture từ dữ liệu tối thiểu và không cần bài test khác chạy trước. Có thể dùng runId + scenarioId + entityId và ghi lại khi fail. Nếu cần random, dùng seed có kiểm soát và lưu seed trong report.

### Eventual consistency

Không sử dụng sleep cố định chỉ để chờ message. Đợi điều kiện với giới hạn:

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {
        var actual = orderClient.getStatus(orderId);
        assertThat(actual).isEqualTo("PAID");
    });
~~~

Ví dụ dùng Awaitility; timeout phải phù hợp budget test. Một bài async nên xác minh **trạng thái cuối** và ghi kết quả cuối cùng khi quá deadline, thay vì kiểm ngay sau khi nhận HTTP 202 Accepted rồi thất bại ngẫu nhiên.

### Clock và scheduler

Đối với hạn giữ hàng, token expiry, retry schedule hoặc end-of-day logic, inject Clock cố định/virtual scheduler thay vì dựa vào đồng hồ thực:

~~~java
Clock fixed = Clock.fixed(
    Instant.parse("2026-11-12T02:00:00Z"),
    ZoneOffset.UTC
);
OrderExpiryPolicy policy = new OrderExpiryPolicy(fixed);
~~~

Phân biệt deadline khởi động container, timeout HTTP và thời hạn chờ eventual consistency. Đừng tăng tất cả thời hạn lên vô hạn khi suite flaky.

## 14. Ma trận lỗi của một luồng liên dịch vụ

| Tình huống | Kỳ vọng cần kiểm |
| --- | --- |
| Inventory đủ hàng | Có reservation đúng, tiếp tục Payment |
| Inventory 409 hết hàng | Không gọi Payment, trả lỗi nghiệp vụ đúng |
| Inventory timeout | Timeout/retry có giới hạn, không treo thread |
| Inventory 503 kéo dài | Fail fast hoặc chuyển pending theo chính sách |
| Payment từ chối | Order không đánh dấu PAID; compensation nếu yêu cầu |
| Payment đã nhận nhưng client timeout | Idempotency + reconciliation, không double charge |
| Broker tạm thời unavailable | Outbox không mất event; retry được |
| Event delivery trùng | Consumer không nhân đôi business effect |
| Consumer crash trước commit | Replay an toàn |
| Event sai schema/version | Contract test phát hiện không tương thích |
| Message poison | Retry hữu hạn và DLQ phù hợp |
| Out-of-order events | Không ghi đè state mới bằng state cũ |
| API auth thiếu hoặc sai | 401/403 đúng, không bypass authorization |
| Dependency rất chậm | Deadline, bulkhead, load shedding hoạt động |

Không cần triển khai toàn bộ kịch bản bằng E2E. Component stubs kiểm thử lỗi HTTP; integration test broker kiểm tra replay/ack; workflow slice kiểm chứng saga/compensation với service thật; deployed smoke kiểm tra network/identity thực.

### Idempotency khi kết quả không chắc chắn

Một testcase quan trọng là provider **đã xử lý thanh toán** nhưng response bị timeout. Retry mù với key mới có thể tạo giao dịch thứ hai. Test nên mô phỏng response bị mất, gửi lại với cùng idempotency key, query trạng thái/reconciliation và assert một tác động nghiệp vụ. HTTP timeout không chứng minh provider chưa xử lý giao dịch.

## 15. Ephemeral environment cho nhóm service thật

**Testcontainers/Docker Compose** phù hợp cho một service hoặc slice nhỏ trên máy cá nhân/CI. Ưu điểm: khởi động container DB/broker/stub, inject ports và tạo resource riêng; không cần cluster cho một component test.

~~~yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: orders_test
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test-password-only
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test -d orders_test"]
      interval: 2s
      retries: 20

  inventory-stub:
    image: wiremock/wiremock:3
    ports:
      - "8080"

  order-service:
    image: example/order-service:test
    environment:
      JDBC_URL: jdbc:postgresql://postgres:5432/orders_test
      INVENTORY_URL: http://inventory-stub:8080
    depends_on:
      postgres:
        condition: service_healthy
~~~

Manifest mang tính minh họa; image, biến config và fixtures phải khớp dự án. Không publish host port cố định trong CI nếu nhiều job chạy song song. depends_on quản lý start order/health condition đã khai báo, không tự bảo đảm Order API thật đã sẵn sàng.

**Kubernetes namespace tạm theo PR** phù hợp khi cần kiểm tra ingress, mTLS/service mesh, identity, network policy hoặc chart/deployment behavior. Tạo namespace theo run ID, triển khai những service cần test, inject stub và data tạm, chạy test Job, lưu report, xóa namespace với TTL/cleanup.

**Chú ý:** Namespace riêng chưa độc lập nếu tất cả namespace vẫn gọi một database, Redis, Kafka topic, secret hoặc provider sandbox chung. Isolation cần bao phủ toàn bộ dependency graph, không chỉ tên namespace.

## 16. Tổ chức CI/CD

Một pipeline gợi ý:

~~~text
PR
 |
 +--> Compile, lint, static checks
 +--> Unit tests
 +--> Component tests (PostgreSQL + strict stubs)
 +--> Consumer/provider contract checks
 +--> Targeted workflow slice tests
 |
 v
Merge gate
 |
 v
Build/publish immutable artifact digest
 |
 v
Deploy environment
 |
 +--> Deployed smoke: ingress + auth + config + critical flow
 +--> Health/SLO rollout checks
 |
 v
Promote / rollback theo chính sách
~~~

Các suite có thể chạy song song khi độc lập. Contract verification cần bao phủ version của consumer/provider có thể cùng tồn tại, không chỉ bản mới nhất. Nếu failure do schema field đổi, báo rõ interaction và provider version; không đưa ra thông báo chung “staging failed”.

Pin image digest/version, config revision và test fixture revision để tái hiện. Cache image layers để tăng tốc, nhưng không cache **trạng thái dữ liệu dơ** giữa runs. Có deadline, quota và cleanup/finalizer kể cả khi CI bị cancel.

## 17. Bảo mật của các dependency test

Không dùng credential production hoặc dữ liệu khách hàng thật trong local/CI integration tests. Nên sinh dữ liệu synthetic, dùng secret riêng có quyền tối thiểu và thời gian sống ngắn.

Tách hai loại kiểm tra:

- **Application security:** token thiếu/sai, scope không đủ, tenant isolation, xác thực service-to-service, log không lộ secret. Có thể dùng local issuer hoặc test identity nhưng đường đi authorization phải được thực thi.
- **Deployment security:** RBAC/IAM, workload identity, TLS/mTLS, network policy, ingress và secret mount thật. Kiểm tra trong ephemeral namespace hoặc deployed smoke.

Không bật global “test mode” bỏ qua auth rồi kết luận flow đã được bảo vệ. Nếu một test logic dùng fake identity để tăng tốc, cần security tests riêng với cơ chế xác thực thực tế.

## 18. Flaky test: chẩn đoán theo nguyên nhân

| Nguyên nhân | Dấu hiệu | Giải pháp |
| --- | --- | --- |
| Shared state | Pass riêng, fail parallel | DB/topic/tenant riêng |
| Timing/async | Pass local, fail CI chậm | Await condition + readiness + deadline |
| Test order dependency | Chạy thứ tự khác thì fail | Fixture riêng mỗi test |
| Stub reset chéo | Mapping mất bất thường | Stub scope riêng hoặc không parallel |
| Contract drift | Stub pass, provider fail | CDC + provider verification |
| Clock/timezone | Fail cuối tháng, DST | Inject Clock, UTC |
| Floating image | Cùng code nhưng dependency thay | Pin image/version |
| Cleanup race | Consumer ghi sau khi DB bị dọn | Wait completion, stop consumer trước cleanup |
| Resource pressure | Nhiều container gây timeout | CPU/RAM quota và concurrency budget |
| Overstrict mocks | Refactor đúng vẫn fail | Assert hợp đồng và outcome |
| Retry masking | Rerun CI xanh nhưng không hiểu lỗi | Lưu report lần fail, theo dõi flake rate |

Đừng chữa flaky test bằng sleep dài hoặc tăng timeout vô hạn. Tìm đúng resource, timing và test ownership gây nhiễu.

## 19. Khi nào vẫn cần kiểm thử trên môi trường triển khai?

Component/contract tests không chắc phát hiện được:

- Ingress routing, DNS, service discovery hoặc service mesh mTLS sai.
- Kubernetes service account/RBAC/secret injection không đúng.
- ConfigMap/environment/feature flags khác với test harness.
- Quota của managed DB/broker hoặc external provider sandbox.
- Rolling deployment có hai service version không tương thích đang chạy.
- Network policy/firewall, truststore và certificate expiry.
- Runtime scaling/cold-start/connection budget dưới tải thực.

Vì vậy cần một số deployed smoke/E2E kiểm tra các rủi ro này sau khi release, cùng metrics/SLO và khả năng rollback. **Không bắt mọi PR đi qua một môi trường staging chung cho mọi biến thể nghiệp vụ**.

## 20. Ma trận kiểm thử tham khảo

| ID | Loại test | Dependency | Oracle |
| --- | --- | --- | --- |
| U01 | Unit | Fake Inventory | Hết hàng không tạo Order |
| U02 | Unit | Fake clock/retry | Retry không vượt budget |
| C01 | Component | Postgres + WireMock | Tạo Order, lưu state và gửi đúng outbound |
| C02 | Component | Postgres + WireMock | Xử lý Payment 503 an toàn |
| C03 | Component | Postgres + WireMock | Idempotency key trùng không double charge |
| I01 | Integration | Postgres + Kafka | Outbox phát record và cập nhật trạng thái |
| I02 | Integration | Broker + consumer + DB | Replay không nhân đôi business effect |
| CT01 | Contract | Order/Inventory | Request/response tương thích |
| CT02 | Contract | Producer/consumer event | Schema version tương thích |
| W01 | Workflow slice | Order + Inventory thật | Reservation và Order state nhất quán |
| W02 | Workflow slice | Broker + service thật | Crash/retry/ack/compensation đúng |
| E01 | Deployed smoke | Artifact triển khai thật | Ingress, TLS, auth, config và happy path |

Ma trận giúp mỗi rủi ro được xác minh ở **cấp thấp nhất còn phát hiện được lỗi**, rồi bổ sung một số bài tích hợp thật khi cần.

## 21. Lộ trình loại bỏ phụ thuộc vào staging chung

1. **Kiểm kê:** liệt kê test đang gọi shared endpoints, thời gian chạy, flake rate, owner và điều thật sự được kiểm tra.
2. **Tách config:** thay URL hard-code bằng property inject; hỗ trợ dynamic port và environment test.
3. **Chuyển unit/component:** chạy logic Order thật, database container, HTTP stubs theo case; tự seed/cleanup data.
4. **Thêm contract:** consumer publish interactions, provider verify các version còn active; gate deploy theo compatibility.
5. **Bổ sung async integration:** broker thật, event schema, ack/commit, replay, DLQ và idempotency.
6. **Tạo workflow slices:** chỉ chạy những service thật cần để kiểm tra các giao dịch xuyên ranh giới quan trọng.
7. **Thu gọn E2E:** giữ smoke/performance/security/deployment tests, không duplicate mọi component scenario.
8. **Chuẩn hóa CI:** artifact pin, run ID, quota, fixture, failure logs, cleanup/TTL và hướng dẫn chạy local.

Cách tiến hành theo từng luồng giúp không phải viết lại toàn bộ test suite cùng lúc. Mỗi testcase chuyển xong phải có oracle rõ và khả năng chạy độc lập trên PR.

## 22. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi shared staging trong mọi PR | Chờ deploy và state drift | Component/contract test tự chủ |
| Mock cả DB/broker | Không thấy lỗi transaction/offset | Dùng container thật đúng rủi ro |
| Stub không verify contract | API thật lệch fixture | CDC/provider verification |
| Dùng chung test account/order/topic | Va chạm khi chạy parallel | Tài nguyên/ID theo run |
| Port host cố định | Collision giữa CI jobs | Port/network động |
| Chỉ assert HTTP 200 | Bỏ sót durable state/outbox | Assert outcome nghiệp vụ |
| Sleep chờ async | Chậm và flaky | Await condition/deadline |
| @Transactional trên test HTTP | Không rollback server transaction | DB/schema/cleanup riêng |
| Bỏ qua retry/replay | Duplicate side effect | Test idempotency/ack/commit |
| Namespace tạm nhưng dùng DB chung | Vẫn phụ thuộc môi trường khác | Audit dependency graph |
| Tắt auth để test pass | Bỏ sót quyền truy cập | App security + deployed tests |
| Image latest | Test không tái lập | Pin digest |
| Không cleanup khi cancel | Rò resource/chi phí | TTL/finalizer |
| Dùng E2E cho mọi edge case | Slow feedback, khó triage | Test nhiều lớp |

## 23. Checklist triển khai

- [ ] Mỗi testcase có SUT và phạm vi dependency rõ ràng.
- [ ] Test CI quan trọng không cần trạng thái đặc biệt của staging chung.
- [ ] Resource có trạng thái được khởi tạo/cô lập theo run hoặc suite.
- [ ] Seed data, random seed, clock, feature flag có thể tái lập.
- [ ] DB/broker integration dùng engine thực khi semantics quan trọng.
- [ ] HTTP stubs strict, có error cases và version phù hợp contract.
- [ ] Consumer/provider contract verification chạy trong CI.
- [ ] Event schema/backward compatibility có test riêng.
- [ ] Test timeout, retry, duplicate, out-of-order và idempotency theo rủi ro.
- [ ] Async assertions chờ trạng thái với deadline thay vì sleep cố định.
- [ ] Parallel runs không chung port, group, schema hoặc cleanup.
- [ ] HTTP/DB/message assertions bám vào kết quả nghiệp vụ, không chỉ mock calls.
- [ ] Test credentials không chạm production, dữ liệu synthetic.
- [ ] Có artifact/version/fixture information để phát lại khi fail.
- [ ] Resource cleanup chạy cả khi pipeline bị cancel; có quota/TTL.
- [ ] Có deployed smoke kiểm tra routing, IAM, TLS, config và luồng chính.
- [ ] Nhóm có thể chạy suite liên quan trên máy cá nhân bằng một lệnh rõ ràng.

## 24. Câu hỏi thường gặp

**Không dùng staging chung có nghĩa bỏ E2E?**

Không. Vẫn cần kiểm tra một số rủi ro của platform thật, nhưng các bài nghiệp vụ/contract chạy độc lập sẽ phát hiện phần lớn lỗi trước. E2E nên tập trung vào điểm mà component/contract không kiểm chứng được.

**Mock Inventory rồi làm sao biết Inventory còn đúng?**

Consumer-driven contract kết hợp provider verification. Consumer test chứng minh Order dùng interaction đã mô tả; provider test chạy Inventory implementation thật để xác minh. Workflow slice có thể kiểm chứng business state xuyên service.

**Nên chọn Testcontainers hay Kubernetes namespace tạm?**

Testcontainers/Compose phù hợp DB/broker/component và slice nhỏ, chạy được local. Namespace tạm phù hợp kiểm tra ingress, mTLS, workload identity và triển khai nhiều service thật. Chọn theo mục tiêu thay vì luôn dùng công cụ nặng nhất.

**Nếu Kafka event có thể đến trễ, test thế nào?**

Đảm bảo consumer subscription/readiness, phát event có ID riêng, đợi state cuối bằng polling có deadline, kiểm tra schema/key/offset theo mục tiêu. Không sử dụng Thread.sleep cố định rồi hy vọng consumer đã xử lý.

**Nếu thanh toán timeout mà provider đã xử lý thì sao?**

Đây là trường hợp kết quả mơ hồ. Test retry với cùng idempotency key, kiểm tra trạng thái provider hoặc reconciliation và assert chỉ một side effect nghiệp vụ. Chỉ kiểm tra HTTP timeout không đủ.

**Vì sao component test xanh nhưng production lỗi?**

Có thể do DNS, IAM, secret, TLS, cấu hình deploy, resource quota hoặc version chạy thực tế. Contract và component tests cung cấp bằng chứng cho các phạm vi cụ thể; deployed smoke và monitoring lấp phần còn lại.

---

**Nguyên lý ghi nhớ:** *Kiểm thử liên dịch vụ đáng tin cậy khi mỗi bài test kiểm soát được ranh giới, dữ liệu, thời gian và dependency; hợp đồng giữa các service được xác minh bằng version rõ ràng; hạ tầng thật tạm thời được sử dụng ở những điểm semantics quan trọng; còn môi trường triển khai đầy đủ chỉ đảm nhận các kiểm tra thuộc về deployment.*