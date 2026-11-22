# Phân chia kiểm thử đơn vị, thành phần, tích hợp và đầu cuối trong microservices

## 1. Vấn đề cần giải quyết

Một hệ thống microservices không chỉ có các hàm Java riêng lẻ. Yêu cầu người dùng có thể đi qua API Gateway, nhiều service, database, message broker, cache và API của đối tác. Một hàm tính tiền có thể đúng trong unit test nhưng endpoint trả JSON sai; endpoint đúng với mock nhưng lỗi khi chạy PostgreSQL; tất cả service chạy tốt khi đứng riêng nhưng người dùng vẫn không thể hoàn tất checkout vì contract hoặc quyền truy cập giữa chúng không tương thích.

Nếu dồn toàn bộ kiểm chứng vào một bộ end-to-end (E2E) khổng lồ, pipeline dễ chậm, không ổn định và rất khó xác định dịch vụ gây lỗi. Nếu chỉ viết unit test, các ranh giới mạng, cấu hình framework, schema, giao dịch và quá trình deploy lại không được kiểm chứng.

Bài học này xây dựng một **chiến lược phân chia trách nhiệm kiểm thử theo phạm vi và rủi ro**:

- **Unit test:** chứng minh quy tắc và hành vi nhỏ, cô lập, chạy rất nhanh.
- **Component test:** chứng minh một service hoàn chỉnh ở ranh giới vào/ra của chính nó, thường thay các phụ thuộc ngoài service bằng stub/fake.
- **Integration test:** chứng minh sự tương tác thật tại một hoặc vài ranh giới kỹ thuật như PostgreSQL, Kafka, HTTP client, authentication hoặc schema migration.
- **End-to-end test:** chứng minh một luồng nghiệp vụ quan trọng chạy xuyên nhiều thành phần trong môi trường đã triển khai.

Không có quy ước đặt tên tuyệt đối chung cho mọi tổ chức: có nơi gọi kiểm tra HTTP controller là integration test, có nơi gọi component test. Trong bài này, **phạm vi và các phụ thuộc thực/simulated** mới là định nghĩa có ý nghĩa. Tên lớp test chỉ nên phản ánh rõ quy ước đã thống nhất.

Sau bài học, bạn có thể đặt một lỗi vào cấp kiểm thử phù hợp, xác định test nào phải chạy trong pull request hay trước release, và thiết kế tổ hợp test có độ tin cậy cao mà không lặp lại cùng một kịch bản ở tất cả các tầng.

## 2. Bản đồ các cấp kiểm thử

Ví dụ một luồng đặt hàng:

```text
                       Client
                          |
                          v
                     API Gateway
                          |
                          v
                     Order Service
                     /      |      \
              PostgreSQL  Kafka  Payment Service
                                    |
                              Payment Provider
```

Mỗi cấp quan sát một phần khác nhau:

```text
UNIT
  OrderPricingPolicy.calculateTotal(...)
  [không HTTP, không DB, không broker]

COMPONENT
  HTTP request → Order Service → HTTP response
  [service thực; payment/DB/broker có thể dùng fake có kiểm soát]

INTEGRATION
  Order Repository ↔ PostgreSQL thật
  Event Publisher ↔ Kafka thật
  HTTP Adapter ↔ API mock server xác minh protocol/contract

END-TO-END
  Client → Gateway → Orders → Payments → DB/broker → kết quả nghiệp vụ
  [các service trọng yếu đã triển khai; mô phỏng phần bên ngoài nếu cần]
```

Hình kim tự tháp thường minh họa **nhiều test nhỏ ở đáy, ít test xuyên hệ thống ở đỉnh**, nhưng không bắt buộc tỷ lệ cố định. Chiến lược thực tế phải dựa vào cấu trúc service, chi phí thiết lập môi trường và rủi ro. Một service CRUD đơn giản cần nhiều kiểm tra persistence/HTTP hơn một thư viện tính toán; một luồng thanh toán cần thêm kiểm tra idempotency và xử lý kết quả không xác định.

## 3. So sánh phạm vi, tốc độ và loại lỗi

| Cấp | Ranh giới quan sát | Phụ thuộc thường dùng | Phát hiện tốt nhất | Hạn chế |
| --- | --- | --- | --- | --- |
| **Unit** | Hàm, class hoặc domain rule | Giá trị thật; mock/fake ở port | Logic tính toán, nhánh nghiệp vụ, edge cases | Không chứng minh wiring, SQL, HTTP hay deploy |
| **Component** | Một service như một khối | Application thật, phụ thuộc ngoài dùng fake/stub tùy thiết kế | Routing, serialization, validation, security filter, cấu hình trong service | Stub có thể khác hệ thống thật |
| **Integration** | Một ranh giới kết nối thật | DB, broker, container, API sandbox, protocol test server | SQL, transaction, migration, serialization mạng, cấu hình client | Chậm và phức tạp hơn unit; không chứng minh toàn bộ hành trình |
| **E2E** | Luồng qua các service đã triển khai | Nhiều service và hạ tầng chạy thật | Tương thích triển khai, quyền, cấu hình, orchestration, hành vi người dùng | Dễ chậm/flaky, khó khoanh lỗi, tốn dữ liệu và môi trường |

Một phép thử có thể thuộc nhiều góc nhìn. Ví dụ `@SpringBootTest` kết nối PostgreSQL Testcontainers vừa kiểm tra component wiring vừa kiểm tra integration với DB. Để giao tiếp rõ ràng, hãy ghi **“Order API component test với DB fake”** hoặc **“Order repository integration test với PostgreSQL thật”** thay vì chỉ ghi chung chung “integration test”.

**Nguyên tắc đặt test:** đẩy kiểm chứng xuống cấp thấp nhất mà vẫn có thể chứng minh được rủi ro cần kiểm tra. Nâng cấp phạm vi khi hành vi nằm tại ranh giới mà cấp thấp không thể quan sát.

## 4. Unit test: cô lập quy tắc và quyết định

Unit test nên kiểm tra **input → rule → output/state** của một đơn vị logic. Nó không cần khởi động Spring Context, container DB hay broker. Một domain rule có thể nhận các giá trị đầu vào thuần và trả kết quả xác định.

Ví dụ quy tắc chiết khấu:

```java
import java.math.BigDecimal;

public final class DiscountPolicy {
    public BigDecimal apply(BigDecimal subtotal, boolean vip) {
        if (subtotal == null || subtotal.signum() < 0) {
            throw new IllegalArgumentException("subtotal must be nonnegative");
        }
        BigDecimal ratio = vip
                ? new BigDecimal("0.90")
                : BigDecimal.ONE;
        return subtotal.multiply(ratio);
    }
}
```

Unit test bằng JUnit Jupiter:

```java
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import static org.junit.jupiter.api.Assertions.*;

class DiscountPolicyTest {
    private final DiscountPolicy policy = new DiscountPolicy();

    @Test
    void appliesTenPercentDiscountForVip() {
        assertEquals(
                new BigDecimal("900.00"),
                policy.apply(new BigDecimal("1000.00"), true));
    }

    @Test
    void doesNotDiscountRegularCustomer() {
        assertEquals(
                new BigDecimal("1000.00"),
                policy.apply(new BigDecimal("1000.00"), false));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.apply(new BigDecimal("-1"), true));
    }
}
```

Các test này không cần Mockito vì logic là thuần. Mock chỉ hữu ích khi dependency không thể hoặc không nên thực thi thật ở cấp unit, chẳng hạn cổng lấy tỷ giá, clock hoặc client gửi thông báo.

Ví dụ nghiệp vụ thanh toán quyết định gọi repository và publisher có thể dùng mock của các **port**. Nhưng một test chỉ có `verify(mock).save(...)` mà không kiểm tra outcome có ý nghĩa thường dễ bám quá chặt vào chi tiết triển khai; refactor hợp lệ có thể khiến nó hỏng dù hành vi không đổi.

### Nên kiểm tra ở unit

- Quy tắc giảm giá, trạng thái đơn hàng, giới hạn số lượng, phát hiện xung đột.
- Validation nghiệp vụ độc lập với HTTP framework.
- Mapping dữ liệu cần chính xác: tiền tệ, timezone, rounding, nullability.
- Xử lý idempotency ở domain/use-case nếu có logic lựa chọn trạng thái.
- Chính sách retry/backoff/deadline ở dạng hàm quyết định với clock giả kiểm soát.
- Trường hợp biên và invariants, không chỉ happy path.

### Không nên kỳ vọng unit chứng minh

- `@Transactional` đã commit/rollback đúng trên database.
- Spring Security filter thật đã xác thực request đúng.
- JSON serializer tạo body tương thích với contract.
- Kafka partitioning/consumer group và retry/redelivery hoạt động đúng.
- DNS, TLS, network timeout và cấu hình deployment chính xác.

Những rủi ro đó thuộc component, integration hoặc E2E.

## 5. Component test: coi một microservice là đơn vị kiểm chứng

**Component** ở đây là một service với entrypoint thật (HTTP, message handler, scheduler) và đường xử lý application/domain thực. Các hệ thống ngoài ranh giới service có thể được thay bằng fake/stub để kịch bản chạy độc lập, nhanh và có thể tái lập.

```text
               HTTP request
                    |
                    v
        +-------------------------+
        |     ORDER SERVICE       |
        | Routing / validation    |
        | Auth filter / use case  |
        | Domain / error mapping  |
        +-----------+-------------+
                    |
             Port / adapter
                    |
               Fake backend
```

Component test giúp trả lời:
- HTTP status, header, JSON, schema và error mapping có đúng không?
- Controller có gọi use case với dữ liệu đã validate không?
- Spring bean/wiring và cấu hình của service có làm ứng dụng khởi động không?
- Request không có quyền có bị từ chối trước khi vào domain không?
- Một sự kiện đầu vào có kích hoạt handler, state transition và output mong đợi không?
- Mọi dependency cần thiết có được fake/stub rõ ràng để test độc lập không?

### Các cách triển khai trong Spring Boot

**Slice test** như `@WebMvcTest` tập trung vào MVC, serializer, validation và filter liên quan. Khi mock các collaborator của controller, đây là một bài kiểm tra ranh giới HTTP mỏng; nó không chứng minh toàn bộ luồng nghiệp vụ của service.

**Full context component test** như `@SpringBootTest` với `@AutoConfigureMockMvc` hoặc WebTestClient tạo context ứng dụng rộng hơn. Các adapter bên ngoài có thể được thay ở port bằng fake có kiểm soát. Nếu dùng mock server HTTP, kiểm tra cả request mà adapter gửi đi, không chỉ stub response.

Ví dụ hướng kiểm tra component cho một API:

```text
Given:
  Payment Port trả APPROVED cho operationId=op-42

When:
  POST /checkout với item hợp lệ và credential phù hợp

Then:
  HTTP 201
  JSON có orderId, status=CONFIRMED
  response không rò dữ liệu payment credential
  application tạo operation và phát sự kiện đúng một lần
```

Sau đó kiểm tra biến thể:
- Body thiếu field → `400` hoặc lỗi theo contract.
- User thiếu scope → `403`, không tạo đơn.
- Payment Port trả từ chối → status nghiệp vụ phù hợp, không tạo đơn đã thanh toán.
- Payment timeout → response/command ở trạng thái không xác định được xử lý theo hợp đồng.
- Cùng idempotency key lặp lại → không nhân đôi tác dụng phụ.

Component test tốt có thể chạy song song và không cần chờ service khác triển khai. Tuy vậy, fake chỉ chứng minh **giả định của service**; nếu fake tự tạo format thuận lợi nhưng provider thật dùng format khác, cần contract hoặc integration test bổ sung.

## 6. Integration test: xác minh những ranh giới kỹ thuật thật

Integration test tập trung vào việc **hai hoặc vài thành phần thật tương tác đúng**, đặc biệt các nơi nhiều giả định không thể đảm bảo chỉ bằng mock.

### 6.1 Database thật với Testcontainers

Một repository có thể đúng khi gọi mock nhưng SQL sai trên PostgreSQL: kiểu dữ liệu, index unique, optimistic locking, timestamp, transaction isolation, migration hoặc constraint đều có thể là nguyên nhân.

Dùng PostgreSQL container cô lập theo test suite hoặc test class, tạo schema bằng migration như trong ứng dụng. Ví dụ khung JUnit/Testcontainers:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@DataJpaTest
class OrderRepositoryIT {
    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void dbProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    OrderRepository repository;

    @Test
    void enforcesUniqueBusinessId() {
        // Chuẩn bị hai bản ghi cùng businessId; xác nhận
        // unique constraint thật của PostgreSQL chặn bản ghi thứ hai.
        // Cần flush/commit để phát sinh lỗi database tại thời điểm kiểm tra.
    }
}
```

Đây là **khung minh họa**, phần assert và entity phụ thuộc repository thực tế. Chạy được cần dependency Testcontainers/JUnit/PostgreSQL và runtime Docker tương ứng; `@DataJpaTest` không tự đảm bảo mọi migration của production đã chạy. Hãy cấu hình migration giống production và chú ý transaction rollback của test có thể che lỗi chỉ xuất hiện lúc commit.

Những trường hợp nên kiểm tra với DB thật:
- Migration từ phiên bản schema trước và schema đang triển khai.
- Unique constraint, foreign key, phân vùng tenant, optimistic locking.
- Transaction commit/rollback, outbox write cùng nghiệp vụ, deadlock policy.
- Query có thứ tự ổn định, pagination, index/collation, dữ liệu Unicode.
- JSONB, timestamp/timezone và các kiểu đặc trưng DBMS.

### 6.2 Broker và event integration

Với Kafka/RabbitMQ, fake publisher không chứng minh:
- Serializer/deserializer đọc cùng schema.
- Topic/queue, partition key, routing và consumer group đúng.
- Ack, redelivery, retry, dead-letter, idempotent consumer.
- Outbox relay đã publish và không làm mất event khi lỗi.
- Ordering thực tế trong một partition hoặc per-key.

Integration test dùng broker thật (thường trong container) nên kiểm tra cả thông điệp trên broker và state của consumer. Kết quả bất đồng bộ cần chờ một **điều kiện xác định**, có deadline tối đa, không dùng `Thread.sleep(5000)` như một lời bảo đảm.

### 6.3 HTTP client và dịch vụ bên ngoài

Có thể dùng stub HTTP server thực, chẳng hạn WireMock/MockWebServer, để kiểm tra request mà adapter gửi:
- Method, path, query, header, body, media type và timeout.
- Mapping `200`, `400`, `429`, `503`, error payload.
- Authentication header đúng nơi, không lộ credential vào log.
- Retry có giới hạn, backoff, jitter và idempotency key.
- TLS verification khi cần thử riêng kết nối TLS.

Mock server chứng minh client nói đúng **giao thức mà test mô tả**. Nó không xác nhận provider thật đang triển khai đúng contract. Với đối tác, bổ sung contract verification, sandbox hoặc kiểm tra kết nối được phép có kiểm soát.

## 7. End-to-end test: hành trình xuyên các service đã triển khai

E2E kiểm chứng một luồng nghiệp vụ từ điểm vào gần người dùng nhất đến kết quả có thể quan sát, qua nhiều dịch vụ và hạ tầng. Ví dụ:

```text
Test client
   |
   v
Gateway → Checkout → Orders → Inventory → Payment
                       |          |          |
                       DB        broker      DB
   |
   v
GET /orders/{id} → trạng thái CONFIRMED sau các bước xử lý
```

Một E2E có ý nghĩa cần xác minh **kết quả nghiệp vụ**, không chỉ tất cả service trả health `200`. Ví dụ:
1. Tạo dữ liệu sản phẩm và account test cô lập.
2. Xác thực user test, tạo checkout request với operation ID riêng.
3. Chờ luồng bất đồng bộ đi tới trạng thái terminal trong deadline kiểm soát.
4. Đọc lại order và payment status qua API công khai hoặc giao diện nghiệp vụ.
5. Xác minh tồn kho, trạng thái đơn và tổng tiền nhất quán.
6. Dọn dữ liệu bằng cơ chế an toàn, tránh phụ thuộc thứ tự các test.

Nên có **ít E2E hơn unit/component/integration**, tập trung vào:
- Luồng tạo đơn, thanh toán, hoàn tiền hoặc nghiệp vụ cốt lõi.
- Đường đi qua authentication, Gateway, routing, TLS, config và migration.
- Một vài failure path liên dịch vụ rất quan trọng.
- Tương thích sau deployment và những hành vi chỉ môi trường triển khai mới bộc lộ.

Nếu bên ngoài là payment provider thật, E2E có thể sử dụng sandbox hoặc fake ở ranh giới bên ngoài phạm vi hệ thống. Hãy ghi rõ ranh giới được mô phỏng; gọi một luồng dùng fake provider là “E2E nội bộ” thay vì khẳng định nó chứng minh kết nối production với provider.

Không dùng một E2E để thử hàng trăm biến thể validation và logic tính toán. Những nhánh đó nhanh, ổn định và dễ chẩn đoán hơn ở unit hoặc component.

## 8. Contract test: lớp bảo vệ độc lập giữa hai service

Microservices triển khai độc lập dễ **lệch hợp đồng**: producer đổi field, enum, kiểu dữ liệu hoặc cách xử lý lỗi trong khi consumer chưa cập nhật.

**Contract testing** là một chiều bổ sung cho bốn cấp trên:
- Consumer mô tả yêu cầu mà nó thực sự sử dụng.
- Provider xác minh có thể đáp ứng hợp đồng đó.
- Contract có thể bao gồm HTTP request/response, event schema và những quy ước version.
- Kiểm tra compatibility trước khi cho hai bản service không tương thích cùng triển khai.

Ví dụ:

```json
{
  "orderId": "order-42",
  "status": "CONFIRMED",
  "totalAmount": "250000.00",
  "currency": "VND"
}
```

Nếu consumer chỉ cần `orderId` và `status`, nó không nên đòi mọi field không sử dụng xuất hiện và trùng giá trị cứng trong mỗi test. Nhưng nếu producer đổi `status` thành object, consumer contract phải phát hiện thay đổi không tương thích.

**Contract test không thay E2E:** provider có thể thỏa schema nhưng luồng đặt hàng vẫn thất bại vì DNS, auth, phiên bản config hoặc orchestration. **E2E cũng không thay contract:** nếu mọi thay đổi nhỏ đều phải chạy qua E2E mới phát hiện bất tương thích, phản hồi cho các nhóm sẽ chậm.

Với event-driven, cần kiểm tra schema evolution: field mới optional, field bị xóa/đổi tên, default, enum unknown, consumer cũ đọc event mới và consumer mới đọc event cũ.

## 9. Phân chia trách nhiệm theo từng rủi ro

| Rủi ro / hành vi | Cấp kiểm thử chính | Cấp bổ sung khi cần |
| --- | --- | --- |
| Tính tiền, làm tròn, business rule | Unit | Component kiểm tra HTTP mapping |
| Validation request và lỗi trả về | Component | E2E một số tình huống quan trọng |
| Quyền truy cập tài nguyên theo user/tenant | Unit policy + Component security | Integration DB/RLS, E2E auth path |
| Serialization HTTP và API compatibility | Component + Contract | Integration HTTP adapter |
| Mapping entity, SQL, transaction, migration | Integration với DB thật | E2E đường nghiệp vụ quan trọng |
| Publish/consume Kafka, redelivery, outbox | Integration với broker thật | E2E async workflow |
| Timeout/retry/circuit breaker policy | Unit quyết định + Component failure behavior | Integration với mock server/chaos có kiểm soát |
| Idempotency theo operation ID | Unit + Integration constraint/transaction | E2E lặp cùng request trong luồng quan trọng |
| Service discovery, Gateway route, TLS, IAM | E2E/smoke triển khai | Integration cấu hình/handshake |
| Data consistency xuyên nhiều service | Integration của các bước riêng | E2E nghiệp vụ cuối |
| Load, latency, saturation và capacity | Performance/load test riêng | E2E smoke sau deploy |
| Secret/certificate rotation | Integration với credential thật trong env kiểm soát | Deployment/E2E canary |

Bảng này là điểm khởi đầu, không phải lịch chạy cứng. Khi lỗi sản xuất xảy ra, hãy tạo regression test ở **cấp thấp nhất thực sự phát hiện lỗi** và một kiểm tra cao hơn nếu lỗi còn liên quan ranh giới triển khai chưa được bao phủ.

## 10. Thiết kế tổ hợp test cho một tính năng checkout

Giả sử tính năng: người dùng gửi request checkout; hệ thống tạo đơn, giữ tồn kho, yêu cầu thanh toán và cuối cùng xác nhận.

**Unit — nhanh và nhiều trường hợp:**
- Giá 100.000 VND, giảm giá đúng quy tắc.
- Không cho checkout giỏ rỗng.
- Trạng thái `NEW → RESERVED → CONFIRMED` hợp lệ; không thể `CANCELLED → CONFIRMED` tùy hợp đồng.
- Một operation ID đã xử lý không tạo command thứ hai.
- Deadline retry không cho retry sau khi đã hết thời gian.

**Component — kiểm tra Order/Checkout Service:**
- `POST /checkout` với body hợp lệ trả kết quả theo contract.
- Token không đủ quyền bị chặn.
- JSON không có field nhạy cảm, validation trả lỗi chuẩn.
- Payment port trả trạng thái không xác định được biểu diễn thành `PENDING_RECONCILIATION` hoặc trạng thái tương ứng.
- Broker port fake nhận event có order ID và correlation ID đúng.

**Integration — một ranh giới thật tại một thời điểm:**
- Lưu order và outbox trong cùng transaction PostgreSQL.
- Unique key/idempotency constraint chặn tạo đơn trùng khi hai request cạnh tranh.
- Outbox relay gửi event thật lên Kafka; consumer xử lý được.
- Payment HTTP adapter xử lý timeout, 429, 503 qua test server đúng retry budget.
- Migration mới vẫn đọc được dữ liệu tạo ở phiên bản schema trước.

**E2E — ít kịch bản nhưng có giá trị cao:**
- Người dùng hợp lệ checkout và nhìn thấy order xác nhận.
- Cùng idempotency key gửi lại sau timeout không gây đơn/thanh toán trùng.
- Người dùng tenant A không xem được order của tenant B qua Gateway.
- Sau triển khai, một smoke test chứng minh dữ liệu đi xuyên API, DB và broker đúng.

Điểm then chốt là **không chép nguyên toàn bộ test case vào bốn cấp**. Mỗi cấp nhận phần bằng chứng mà nó có khả năng cung cấp mạnh nhất.

## 11. Mock, stub, fake và container nên dùng thế nào?

| Công cụ | Ý nghĩa | Nơi thường hữu ích |
| --- | --- | --- |
| Mock | Đối tượng giả theo dõi tương tác/expectation | Unit test port/collaborator |
| Stub | Phụ thuộc trả kết quả định trước | Component hoặc HTTP client tests |
| Fake | Triển khai đơn giản nhưng có hành vi, ví dụ repository in-memory | Component test workflow của một service |
| Emulator | Mô phỏng hệ thống ngoài theo giao thức | Integration có giới hạn; cần hiểu fidelity |
| Testcontainer | Chạy phần mềm thật trong container tạm | Integration với DB, broker, cache |
| Sandbox service | Môi trường provider cung cấp để tích hợp | Kiểm tra hợp đồng với bên ngoài |
| Real deployed environment | Nhiều service thật cùng vận hành | E2E, smoke, resilience |

Có thể dùng fake repository để tăng tốc component test, nhưng fake thường không có unique constraint, isolation, collation hoặc transaction như DB thật. Vì vậy vẫn cần integration test cho các rủi ro persistence.

Ngược lại, sử dụng PostgreSQL thật cho mọi phép thử của một hàm tính giá không thêm nhiều bằng chứng, nhưng làm pipeline chậm.

Một nguyên tắc kiểm chứng: **dependency nào đang giả thì bài test không thể khẳng định hành vi thật của dependency đó**. Đây là lý do phải chọn tên và scope test rõ ràng.

## 12. Kiểm thử hệ thống bất đồng bộ không dựa vào giấc ngủ cố định

Một hành trình phát sự kiện có thể mất thời gian do queue, consumer group, backoff hoặc eventual consistency. Kiểm tra ngay sau khi publish có thể đọc trạng thái cũ dù hệ thống đúng; `Thread.sleep(3000)` có thể pass trên laptop và fail trên CI.

Hướng làm tốt:

1. Tạo `operationId` duy nhất cho mỗi test.
2. Publish command/event vào broker test thực hoặc gọi endpoint tương ứng.
3. Poll trạng thái cuối bằng điều kiện cụ thể trong deadline giới hạn.
4. Khi quá hạn, xuất thông tin có ích: trace ID, topic, partition, consumer offset, state hiện tại, timeout.
5. Dọn tài nguyên test, tránh ảnh hưởng test khác.

```text
Given: order-42 đang PENDING
When:  OrderConfirmed event được publish
Then:  chờ đến khi order-42 == CONFIRMED
       với deadline tối đa đã định

Không khẳng định:
       "đợi 3 giây thì chắc chắn thành công"
```

Cũng cần thử:
- Event trùng và xử lý idempotent.
- Consumer restart giữa lúc xử lý.
- Message sai schema vào dead-letter hoặc quy trình xử lý lỗi.
- Out-of-order event nếu domain phải hỗ trợ.
- Broker unavailable, retry có giới hạn và không mất nghiệp vụ.
- Không kỳ vọng thứ tự toàn cục nếu broker chỉ bảo đảm ordering theo partition/key.

## 13. Dữ liệu test, môi trường và tính độc lập

Một test tốt phải có thể chạy lại, chạy song song và có kết quả nhất quán trên CI. Để đạt được:

- Tạo dữ liệu có tên/ID riêng, có thể liên kết theo `testRunId` hoặc prefix.
- Không phụ thuộc bản ghi “có sẵn” của staging hoặc thứ tự test suite.
- Reset database/container hoặc quản lý transaction/cleanup đúng phạm vi.
- Không chia sẻ mutable global fake giữa các test chạy song song.
- Giữ clock và random seed có thể điều khiển khi kiểm tra hạn dùng, retry hoặc time-window.
- Dùng credential test có quyền tối thiểu; không sao chép production secrets vào CI.
- Không gửi email/thanh toán/notification thật từ E2E nếu không có môi trường sandbox an toàn.
- Trong multi-tenant, kiểm tra cả trường hợp người dùng hợp lệ nhưng truy cập nhầm tenant.
- Với DB, chỉ rollback transaction test khi hiểu rằng một số lỗi chỉ bộc lộ ở commit thật.

**Dọn dữ liệu E2E** có thể phức tạp khi nhiều service giữ bản sao eventual consistent. Ưu tiên namespace/tenant test biệt lập, dữ liệu hết hạn theo TTL và cleanup có thể chạy lại, thay vì xóa tùy tiện dữ liệu người dùng.

Một test luôn thành công khi chạy riêng nhưng thất bại khi chạy cả suite là dấu hiệu của shared state, thứ tự ngầm, race condition hoặc sự phụ thuộc môi trường cần được điều tra.

## 14. Kiểm thử lỗi mạng và khả năng chịu lỗi

Microservices phải đối mặt với timeout, lỗi một phần, kết quả không xác định và retry storm. Những hành vi này cần test ở cấp phù hợp:

**Unit:**
- Hàm `shouldRetry(error, attempt, deadlineRemaining)` trả đúng quyết định.
- Backoff/jitter nằm trong giới hạn; cancellation được tôn trọng.
- State machine không ghi nhận payment failed khi kết quả thực tế chưa biết.

**Component:**
- Downstream stub trả `503`, service trả trạng thái/fallback đúng.
- Circuit breaker mở sau chuỗi lỗi mô phỏng; request tiếp theo fail fast.
- Request bị hủy không kéo theo tác vụ thừa theo chính sách được thiết kế.

**Integration:**
- HTTP client thật xử lý connection reset, timeouts, `Retry-After`.
- Connection pool hồi phục sau database restart trong giới hạn cho phép.
- Kafka consumer redeliver không tạo thao tác nghiệp vụ trùng.

**E2E hoặc chaos test có giới hạn:**
- Một downstream bị vô hiệu trong môi trường kiểm soát; hành trình người dùng suy giảm đúng hợp đồng.
- Sau hồi phục, service tiếp tục nhận traffic mà không tạo bão reconnect.
- Alerting và dashboard ghi nhận ảnh hưởng thực.

Fault injection phải dùng môi trường được phép và giới hạn tài nguyên; không đưa thí nghiệm phá kết nối vào production nếu chưa có quy trình an toàn. Không dùng các kịch bản phá mạng nặng như điều kiện mặc định của mọi pull request.

## 15. Tổ chức pipeline CI/CD và thời điểm chạy

Một pipeline minh họa:

```text
Pull request
  |
  +--> Compile / static analysis
  +--> Unit tests
  +--> Component tests (fast)
  +--> Contract compatibility
  +--> Targeted integration tests
  |
  v
Merge / pre-release
  |
  +--> Full integration suite (DB/broker)
  +--> Security checks & migrations
  +--> Build artifact / deployment verification
  |
  v
Staging / preview
  |
  +--> Small E2E critical journeys
  +--> Smoke + async workflows
  |
  v
Production deployment
  |
  +--> Safe smoke/health/canary
  +--> Monitor SLO and rollback signals
```

Nhịp chạy tùy năng lực CI và rủi ro. Nếu integration suite chỉ mất vài phút và bắt được lỗi SQL nghiêm trọng, nên chạy trên PR thay vì chờ merge. Nếu E2E đòi môi trường nhiều service và rất chậm, chỉ nên chạy bộ critical path trên mỗi release, thêm bộ đầy đủ theo lịch hoặc trước các thay đổi quan trọng.

Nên phân loại các test theo tags/naming để pipeline có thể chọn:
- Unit: `*Test` hoặc tag `unit`.
- Integration: `*IT` hoặc tag `integration`.
- E2E: tag `e2e`, chạy bằng môi trường đã chuẩn bị.

Tên chỉ là quy ước; cấu hình Gradle/JUnit thực tế phải được thiết lập để suite được phát hiện và chạy. Không coi sự tồn tại của file `*IT.java` là bằng chứng nó đã được CI thực thi.

### Các gate nên có

Mỗi gate xác nhận một điều kiện có thể hành động:
- Unit/Component thất bại → cần sửa behavior trong service.
- Contract thất bại → có nguy cơ bất tương thích provider/consumer.
- Integration thất bại → DB/schema/protocol/adapter có thể không tương thích.
- E2E thất bại → chưa chứng minh hành trình triển khai an toàn; cần triage theo trace và service logs.

Tránh biến E2E flaky thành “luôn retry test 5 lần rồi coi là pass”. Retry một test hỏng có thể hỗ trợ chẩn đoán, nhưng phải đo và xử lý flakiness; kết quả pass sau retry không xóa được nguy cơ race condition.

## 16. Chi phí, tốc độ phản hồi và độ tin cậy

Một tổ hợp kiểm thử có ba nguồn chi phí:

1. **Thời gian chạy:** unit thường tính bằng mili giây đến giây; component nhanh hơn test xuyên nhiều service; E2E phụ thuộc deploy, hạ tầng và xử lý async.
2. **Chi phí bảo trì:** E2E phụ thuộc nhiều team/schema/data nên dễ bị ảnh hưởng bởi thay đổi không liên quan.
3. **Chi phí chẩn đoán:** unit thường chỉ ra rule hỏng; E2E chỉ báo hành trình thất bại, sau đó cần trace/log để khoanh vùng.

Không cố đạt tỷ lệ “70% unit, 20% integration, 10% E2E” như một chỉ tiêu bắt buộc. Số lượng test có thể bị thao túng bằng cách chia nhỏ assertions; thứ cần đo là **mức bao phủ rủi ro** và khả năng phát hiện lỗi có giá trị.

Các chỉ số vận hành test hữu ích:
- Median/p95 thời gian CI, thời gian nhận tín hiệu lỗi đầu tiên.
- Tỷ lệ test flaky và số lần phải retry test.
- Lỗi lọt lên staging/production theo loại ranh giới.
- Số lần hỏng do môi trường và do ứng dụng.
- Số test chỉ tồn tại nhưng không được chạy ở pipeline phù hợp.
- Thời gian trung bình khoanh vùng một test E2E thất bại.

**Coverage dòng code** là chỉ số bổ sung, không đồng nghĩa hành vi đã được chứng minh. Một test gọi vào tất cả nhánh nhưng assert sai hoặc không kiểm tra outcome có thể tạo coverage cao mà giá trị thấp.

## 17. Đặc thù test cho microservices triển khai độc lập

Khi các service deploy riêng, câu hỏi quan trọng là: **một phiên bản consumer có hoạt động với nhiều phiên bản provider đang tồn tại đồng thời không?**

Ví dụ Orders phiên bản mới muốn đọc `paymentStatus`, trong khi Payments cũ chỉ trả `status`. Dù đơn vị Orders đúng, E2E với hai phiên bản mới nhất vẫn chưa chứng minh rolling deployment có an toàn, vì production có thể chứa tổ hợp mới/cũ trong một khoảng thời gian.

Cần xây chiến lược compatibility:
- API/event schema thay đổi theo hướng backward/forward compatible khi thiết kế cho phép.
- Consumer-driven contract test kiểm tra nhu cầu hiện tại của từng consumer.
- Provider verify contract của những consumer version đang được hỗ trợ.
- Kiểm thử migration schema theo kiểu expand/contract khi có rolling deployment.
- Duy trì bộ smoke với những tổ hợp phiên bản có thể cùng hoạt động.
- Dọn support cho field cũ khi có bằng chứng consumer đã chuyển.

Đối với dữ liệu phân tán, E2E không chứng minh “toàn bộ hệ thống luôn nhất quán tức thời”. Hãy định nghĩa các trạng thái được phép, thời gian eventual consistency dự kiến và điều kiện kết thúc/compensation.

## 18. Phân quyền sở hữu test giữa các nhóm

| Nhóm / vai trò | Trách nhiệm chính |
| --- | --- |
| Team sở hữu service | Unit, component, integration của service; contract cung cấp/tiêu thụ; sửa khi test thất bại |
| Team sở hữu database/schema | Migration compatibility, permissions và rủi ro dữ liệu; hỗ trợ test repository |
| Platform/Infrastructure | Test harness, ephemeral environment, network, secrets, observability |
| Team sở hữu hành trình nghiệp vụ | Xác định critical journeys E2E và kết quả nghiệp vụ phải kiểm chứng |
| CI/Release owner | Bảo đảm test suite được chạy, gate có tín hiệu rõ, deployment canary |
| Security team hoặc security owner | Chính sách test authn/authz, tenant isolation, credential và threat scenarios |

Quyền sở hữu có thể khác theo tổ chức, nhưng mọi test phải có người chịu trách nhiệm khi fail. Tránh tình huống một “E2E team” chung ôm toàn bộ lỗi từ nhiều service mà không có đường phân công cụ thể.

Khi phát hiện một bug production, ghi rõ:
- Nguyên nhân thuộc rule, serialization, schema, async hay deployment?
- Cấp test thấp nhất có thể tái hiện bug?
- Contract hoặc E2E nào còn cần để ngăn lỗi kết hợp?
- Ai là owner của kiểm chứng và cảnh báo lâu dài?

## 19. Anti-patterns

**Chỉ dùng unit test rồi tuyên bố service sẵn sàng:** thiếu kiểm tra HTTP, migration, DB thật, broker và cấu hình deploy.

**Dùng E2E cho mọi nhánh logic:** chậm, flaky, cần dữ liệu khó quản lý; khi lỗi không biết đặt breakpoint ở đâu.

**Mock mọi thứ ở integration test:** không chứng minh integration; đặt tên đúng là component/unit hoặc bổ sung dependency thật.

**Đòi service thật ở mọi component test:** biến component thành E2E, khiến team không chạy độc lập được.

**Kiểm tra SQL trên H2 rồi khẳng định tương thích PostgreSQL:** khác biệt về dialect, constraint và transaction có thể bỏ lọt bug. Dùng đúng DBMS cho rủi ro cần chứng minh.

**Dùng `Thread.sleep` để đồng bộ async:** test phụ thuộc tốc độ máy và tải CI; chờ điều kiện với deadline.

**Không kiểm tra authentication/tenant:** happy path có thể pass trong khi user khác đọc được dữ liệu qua IDOR.

**Dùng chung dữ liệu staging:** test tương tác lẫn nhau, cleanup có thể ảnh hưởng nghiệp vụ, kết quả không thể lặp lại.

**Quarantine test flaky vô thời hạn:** biến một dấu hiệu race thành vùng không ai chịu trách nhiệm; cần owner và lịch xử lý rõ.

**Chỉ test từng service trên phiên bản mới nhất:** bỏ sót tương thích khi rolling deployment và phiên bản cũ/mới cùng tồn tại.

## 20. Ví dụ lập ma trận cho Order Service

Giả sử service có các endpoint `POST /orders`, `GET /orders/{id}` và event `OrderPlaced`:

| Kịch bản | Unit | Component | Integration | E2E |
| --- | :---: | :---: | :---: | :---: |
| Tính tổng tiền và chiết khấu | ✓ |  |  |  |
| Chặn item số lượng âm, HTTP 400 | ✓ | ✓ |  |  |
| User thiếu quyền tạo đơn |  | ✓ |  | Một kịch bản đại diện |
| Query order phải lọc tenant | ✓ policy | ✓ | ✓ DB constraint/query | Một kịch bản đại diện |
| Unique order operation ID | ✓ rule |  | ✓ concurrent transaction | Một flow cần thiết |
| Serialize `OrderPlaced` đúng schema |  | ✓ | ✓ broker |  |
| Retry khi Kafka tạm unavailable | ✓ policy | ✓ | ✓ adapter |  |
| Gateway routing sau deploy |  |  |  | ✓ |
| Checkout xác nhận đơn xuyên services |  |  |  | ✓ |
| Migration từ schema trước |  |  | ✓ | Smoke sau deploy |

Dấu ✓ không yêu cầu cùng một assertion được sao chép y hệt. Chẳng hạn unit test kiểm tra quy tắc tenant, integration test kiểm tra query thực không trả dữ liệu tenant khác, còn E2E đại diện kiểm tra toàn chuỗi identity propagation.

## 21. Bài tập thực hành

**Bài 1 — Phân cấp đúng.** Với bug “giảm giá VIP làm tròn sai 1 đồng”, “JSON thiếu currency”, “unique index không hoạt động trên PostgreSQL” và “Gateway định tuyến sai sau deploy”, hãy chọn cấp test thấp nhất phát hiện được từng bug và giải thích.

**Bài 2 — Thiết kế component test.** Viết kịch bản HTTP cho `POST /orders` khi Payment Port lần đầu timeout. Chỉ rõ đâu là xử lý thật trong service, đâu là stub, và assert kết quả nghiệp vụ nào.

**Bài 3 — Tạo DB integration test.** Dùng Testcontainers PostgreSQL và migration thật; kiểm tra hai transaction đồng thời không thể tạo hai order có cùng idempotency key. Lưu ý thời điểm commit/flush.

**Bài 4 — Async test.** Một consumer cập nhật trạng thái đơn sau event Kafka. Thiết kế chờ điều kiện tối đa 10 giây bằng polling, xác minh duplicate delivery không cập nhật hai lần và cleanup test data.

**Bài 5 — Contract compatibility.** Orders tiêu thụ JSON từ Payments. Lập hợp đồng cho field đang dùng, thử producer thêm field optional, xóa field bắt buộc và đổi enum. Chỉ ra khi nào provider verification phải fail.

**Bài 6 — Tinh gọn pipeline.** Bộ E2E hiện có 300 test, mất 40 phút và thường flaky. Chọn những kịch bản nên chuyển xuống unit/component/integration, giữ lại các critical journeys và đề xuất gate theo pull request, staging, release.

## 22. Ghi nhớ

- **Unit chứng minh logic nhỏ; component chứng minh một service; integration chứng minh ranh giới thật; E2E chứng minh hành trình xuyên hệ thống.**
- Một test chỉ có thể xác nhận hành vi của những thành phần **thật** trong phạm vi nó quan sát.
- **Contract testing** bảo vệ khả năng triển khai độc lập và tương thích phiên bản; nó bổ sung cho các cấp khác.
- Đặt test ở **cấp thấp nhất vẫn đủ bằng chứng**, rồi chỉ nâng phạm vi cho rủi ro mạng, hạ tầng, phối hợp hoặc triển khai.
- Với DB và broker, dùng implementation thật khi cần chứng minh constraint, transaction, schema và redelivery.
- Với async, chờ **điều kiện cuối** trong deadline thay vì ngủ một khoảng cố định.
- E2E nên ít nhưng đại diện cho những **hành trình nghiệp vụ quan trọng**, có dữ liệu độc lập và trace đủ để chẩn đoán.
- Mục tiêu là **thời gian phản hồi nhanh, khả năng phát hiện lỗi thực và chi phí bảo trì hợp lý**, không phải một tỷ lệ test hình thức.

### Tham khảo

- JUnit Jupiter User Guide: https://docs.junit.org/current/user-guide/
- Spring Boot Testing Documentation: https://docs.spring.io/spring-boot/reference/testing/index.html
- Testcontainers for Java: https://java.testcontainers.org/
- Consumer-Driven Contracts (Pact): https://docs.pact.io/
- Google SRE — Testing for Reliability: https://sre.google/sre-book/testing-reliability/

Tài liệu và ví dụ Spring Boot/JUnit trong bài mô tả các cách tiếp cận; khi áp dụng phải khớp phiên bản framework, dependency, cấu hình Gradle và hợp đồng thực tế của module.
