# Kiểm tra chất lượng, hợp đồng, bảo mật và kiến trúc trong CI

> **Chủ đề:** Software Design · System Architecture · Microservices  
> **Nhóm:** Tích hợp và phát hành  
> **Mục tiêu:** Xây dựng một hệ thống Continuous Integration (CI) đủ nhanh để hỗ trợ lập trình viên tích hợp code thường xuyên, nhưng đủ mạnh để chặn lỗi chức năng, thay đổi phá vỡ hợp đồng dịch vụ, lỗ hổng bảo mật và vi phạm các nguyên tắc kiến trúc trước khi đưa thay đổi vào nhánh chính hoặc phát hành.

## 1. CI không chỉ là chạy unit test

Trong hệ thống microservices, một thay đổi nhỏ ở Order Service có thể gây hậu quả ở nơi khác dù Order Service tự build thành công:

- Đổi tên một field trong response JSON khiến Web Client hoặc Billing Service không đọc được.
- Đổi tên event **OrderConfirmed** hoặc đổi cách diễn giải field khiến consumer xử lý sai.
- Thêm một thư viện có lỗ hổng bảo mật hoặc bị gỡ khỏi nguồn cung cấp.
- Tham chiếu trực tiếp package nội bộ của Payment Service, tạo phụ thuộc sai kiến trúc.
- Sửa truy vấn làm tăng độ trễ p99, nhưng unit test vẫn xanh.
- Thực hiện migration cơ sở dữ liệu không tương thích với phiên bản Pod đang chạy.
- Cấu hình pipeline lộ credential hoặc cho phép mã không đáng tin cậy chạy với quyền deploy production.

**CI hiệu quả phải bảo vệ cả chất lượng của bản thân service và khả năng tích hợp của toàn hệ thống.**

Một pipeline có thể dùng nhiều loại tín hiệu khác nhau:

1. **Quality:** code có build, chạy đúng và đáp ứng chuẩn chất lượng không?
2. **Contract:** thay đổi có còn tương thích với consumer/provider và dữ liệu lưu trữ không?
3. **Security:** code, dependency, cấu hình và artifact có vi phạm chính sách bảo mật không?
4. **Architecture:** cấu trúc dependency và ranh giới module/service có đúng quyết định kiến trúc không?
5. **Delivery readiness:** artifact có thể được triển khai và kiểm chứng nguồn gốc, tính lặp lại, khả năng rollback không?

CI không thay thế hoàn toàn thử nghiệm môi trường production, canary hoặc giám sát sau triển khai. Nó là **một chuỗi quality gates được tự động hóa**, hoạt động sớm để lỗi rẻ hơn khi sửa và giảm rủi ro phát hành.

## 2. Khái niệm: Pipeline, stage, check, quality gate

- **Pipeline:** tập công việc được kích hoạt theo sự kiện như pull request, push vào main, tạo release tag.
- **Stage/job:** nhóm bước cùng mục đích, ví dụ build, unit tests, contract verification, security scans.
- **Check:** một phép kiểm tra có đầu ra xác định như PASS/FAIL hoặc báo cáo lỗi.
- **Quality gate:** quy tắc quyết định có cho phép merge/promote artifact hay không dựa trên kết quả các checks và chính sách.
- **Artifact:** thành phẩm build bất biến như JAR, OCI image, SBOM hoặc report được gắn với commit và build run.
- **Evidence:** dữ liệu làm căn cứ cho quyết định, chẳng hạn test results, API diff, SCA report, chữ ký artifact và provenance.
- **Policy exception:** ngoại lệ được phê duyệt có owner, phạm vi, thời hạn và biện pháp giảm thiểu; không phải tắt toàn bộ kiểm tra.

Một pipeline tốt phải **deterministic ở mức hợp lý, có khả năng tái chạy, dễ chẩn đoán và cho kết quả rõ ràng**. Một check lúc xanh lúc đỏ do môi trường bị chia sẻ mà không có nguyên nhân là một nguồn cản trở, không phải bảo đảm chất lượng.

### 2.1. PR CI khác release pipeline

**PR pipeline** ưu tiên phản hồi sớm và chặn thay đổi nguy hiểm: compile, format, unit tests, architecture rules, API compatibility, những kiểm tra bảo mật nhanh và component tests quan trọng.

**Main branch/release pipeline** có thể chạy toàn bộ integration tests, contract verification, kiểm tra image/IaC, tạo SBOM, ký artifact và xuất provenance. **Nightly/scheduled pipeline** có thể chạy fuzz tests, extended DAST, soak/load tests hoặc phân tích bảo mật sâu; tuy nhiên lỗi mức nghiêm trọng vẫn cần có chính sách chặn phát hành phù hợp, không phải tự động bỏ qua chỉ vì check chạy ban đêm.

**CD/deployment** xử lý promotion, smoke test, canary, feature flags và rollback. CI nên tạo được artifact đủ tin cậy để CD dùng, thay vì mỗi môi trường tự rebuild một version khác.

## 3. Kiến trúc pipeline phân lớp

Một thiết kế tham khảo:

~~~text
Pull Request / Commit
        |
        v
[Source integrity + permissions + change detection]
        |
        v
[Format / Lint / Compile / Static analysis] -----> Feedback sớm
        |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
[Unit tests]      [Architecture rules]    [SAST/Secret/SCA]
        |                   |                   |
        +-------------------+-------------------+
                            |
                            v
           [Component / Integration tests]
                            |
              +-------------+--------------+
              |                            |
              v                            v
       [API contracts]            [Event contracts]
              |                            |
              +-------------+--------------+
                            |
                            v
                [Migration/compatibility]
                            |
                            v
                  [Build immutable artifact]
                            |
                            v
            [SBOM / Image & IaC scan / Sign]
                            |
                            v
                     [Policy gate]
                            |
               +------------+-------------+
               |                          |
             PASS                        FAIL
               |                          |
               v                          v
       Ready for promotion         Block + actionable
                                   feedback/evidence
~~~

Đây là **logic phụ thuộc**, không bắt buộc chạy tuần tự. Những job không phụ thuộc có thể chạy song song. Trình tự tối ưu thường là **fail fast với bước rẻ, sau đó thực hiện bước đắt**. Không cần đợi một bài test môi trường 20 phút mới thông báo rằng source code không compile.

### 3.1. Feedback latency là một thuộc tính kiến trúc

Một CI mất 45 phút cho mọi PR sẽ khuyến khích developer batch nhiều thay đổi, chậm nhận phản hồi và làm tăng rủi ro xung đột tích hợp. Nhưng pipeline rất nhanh mà không chặn breaking contract cũng không hữu ích.

Nên đo:

- Thời gian từ push tới **first actionable failure**.
- Median/p95 thời gian một PR CI chạy xong.
- Tỷ lệ lỗi do code so với lỗi hạ tầng/test không ổn định.
- Số lần retry pipeline không tạo ra thông tin mới.
- Tỷ lệ thay đổi đi qua merge rồi rollback vì lỗi có thể phát hiện trước.
- Coverage của các rủi ro quan trọng, không chỉ độ bao phủ dòng code.

Mục tiêu thời gian do team và hạ tầng quyết định; không có một con số cố định phù hợp mọi dự án.

## 4. Xây dựng tầng kiểm thử theo giá trị

### 4.1. Unit tests — nhiều, nhanh, cô lập

Unit test xác minh quy tắc nghiệp vụ và điều kiện biên mà không cần mạng, database thực hay container. Nên tập trung vào những quyết định mà một thay đổi code dễ phá vỡ: hạn mức, chuyển trạng thái, rounding, authorization predicates, timeout-budget calculation.

Ví dụ Java/JUnit minh họa:

~~~java
class PaymentRetryPolicyTest {

    private final PaymentRetryPolicy policy = new PaymentRetryPolicy(3);

    @Test
    void shouldStopAfterMaxAttempts() {
        assertFalse(policy.canRetry(3, true));
    }

    @Test
    void shouldNotRetryOnValidationError() {
        assertFalse(policy.canRetry(1, false));
    }

    @Test
    void shouldRetryTransientFailureWithinBudget() {
        assertTrue(policy.canRetry(2, true));
    }
}
~~~

Hợp đồng của ví dụ: tham số thứ hai biểu diễn lỗi có thể retry; số lần được truyền là lần thử đã sử dụng. Tên method của class tùy ứng dụng. Điểm chính là **kiểm tra quy tắc theo đầu vào/đầu ra**, không khóa chặt unit test vào việc gọi một method nội bộ đúng mấy lần.

Đừng coi test coverage 90% là bằng chứng tuyệt đối: 100% line coverage vẫn có thể không kiểm tra nhánh lỗi, lỗi concurrency hoặc business invariant. Dùng coverage như **tín hiệu bổ sung**, ưu tiên test của code mới/thay đổi và các nhánh rủi ro.

### 4.2. Component/slice tests — sát framework nhưng vẫn nhanh

Ví dụ với Spring, **@WebMvcTest** giúp kiểm tra HTTP mapping, validation, status và serialization trong web layer. Với API, cần kiểm tra:

- Request hợp lệ trả đúng status/content type/JSON structure.
- Request sai validation bị từ chối có lỗi máy đọc được.
- Thiếu credentials trả 401; không đủ quyền trả 403 khi phù hợp.
- Endpoint không leak stack trace, token hoặc dữ liệu riêng tư.
- Idempotency key, pagination, error semantics theo hợp đồng.

Có thể dùng mock cho application service để kiểm tra web boundary, nhưng **đừng dùng mock để tự chứng minh rằng database transaction hoặc message broker thật hoạt động đúng**.

### 4.3. Integration tests — kiểm tra điểm nối thực

Đặc biệt quan trọng với microservices:

- ORM mapping, migrations, index/unique constraint với database giống production.
- Kafka/RabbitMQ serialization, ack, retry, duplicate, DLQ.
- HTTP client timeout, TLS và cách dịch lỗi downstream.
- Transaction/outbox, atomicity, idempotency dưới retry.
- Cache expiry, locking hoặc optimistic concurrency.

Testcontainers có thể khởi động PostgreSQL/Kafka để giảm sai khác giữa môi trường test và production:

~~~java
@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @Autowired
    OrderRepository repository;

    @Test
    void shouldRejectDuplicateBusinessKey() {
        repository.saveAndFlush(newOrder("ORDER-42"));
        assertThrows(
            DataIntegrityViolationException.class,
            () -> repository.saveAndFlush(newOrder("ORDER-42"))
        );
    }
}
~~~

Đây là **ví dụ rút gọn**: hàm **newOrder** do dự án định nghĩa; **@ServiceConnection** yêu cầu phiên bản Spring Boot phù hợp và Testcontainers setup tương ứng. Một test thực tế cần dọn trạng thái/transaction rõ và bảo đảm schema đã được migrate. Không dùng bản test minh họa như snippet production hoàn chỉnh.

### 4.4. End-to-end tests — ít nhưng kiểm tra hành trình sống còn

E2E có giá trị với một số luồng như **đăng nhập → tạo đơn → thanh toán giả lập → xác nhận**. Nhưng chạy hàng nghìn E2E phụ thuộc chung môi trường dễ chậm và flaky. Nên:

- Có một số luồng smoke/happy path và failure path quan trọng.
- Dùng dữ liệu riêng, idempotent, có cleanup.
- Mock hệ thống bên ngoài không thuộc quyền kiểm soát khi cần; ghi rõ coverage bị giới hạn.
- Chỉ chạy production-like E2E ở môi trường được kiểm soát, không dùng credential production.
- Điều tra nguyên nhân flaky thay vì retry vô hạn đến khi xanh.

**Kim tự tháp kiểm thử** là định hướng kinh tế: nhiều kiểm thử nhanh ở lớp thấp, ít hơn ở lớp tích hợp liên dịch vụ rộng. Nhưng không dùng hình dạng kim tự tháp để bỏ qua loại kiểm tra thực sự phát hiện rủi ro quan trọng.

## 5. Quality gates cho source code

Các bước phổ biến:

1. **Build/compile:** dependency resolve đúng, không bỏ qua compiler warning nghiêm trọng mà team đã định nghĩa.
2. **Format/lint:** coding conventions, phát hiện import thừa, API misuse, code smells rõ.
3. **Static analysis:** các vấn đề như null dereference, resource leak, concurrent access, regex nguy hiểm, complexity ở nơi phù hợp.
4. **Tests:** unit, component, integration; kết quả phải được xuất theo định dạng CI đọc được.
5. **Coverage:** theo chính sách code mới và critical modules; tránh gate máy móc khiến code dễ test nhưng logic quan trọng chưa được kiểm tra.
6. **Mutation testing (có chọn lọc):** xem test có phát hiện thay đổi logic hay không; thường phù hợp job sâu do chi phí chạy cao.
7. **Build reproducibility:** cùng commit, dependency lock và môi trường xác định tạo artifact tương đương ở mức được hỗ trợ.

Một **quality gate nên có thông điệp lỗi hành động được**: file/line, rule, link báo cáo, cách tái hiện và người chịu trách nhiệm. Một kết quả “quality score thấp” không biết sửa ở đâu sẽ nhanh bị coi là nhiễu.

## 6. Contract testing: Vì sao kiểm thử riêng service chưa đủ?

Trong microservices, các service thay đổi và deploy độc lập. **Contract** là tập giả định được chấp nhận giữa consumer và provider, gồm schema, status code, error semantics, auth, message format, ordering và behavior cần bảo đảm.

Ví dụ Order API trả response:

~~~json
{
  "id": "ORD-1001",
  "status": "CONFIRMED",
  "totalAmount": 590000,
  "currency": "VND"
}
~~~

Billing Service đang đọc **totalAmount**. Một thay đổi đổi tên thành **amount** mà không có giai đoạn tương thích có thể khiến Billing Service lỗi dù Order Service vẫn hoàn thành unit tests.

**Contract testing phát hiện các khác biệt ở ranh giới giao tiếp**. Nó không thay thế toàn bộ integration tests, vì contract có thể đúng schema mà transaction vẫn sai nghiệp vụ.

## 7. API contracts: OpenAPI, schema và tương thích ngược

### 7.1. Contract-first hoặc code-first

Có hai hướng:

- **Contract-first:** thiết kế OpenAPI trước, review diff, sau đó implement và test.
- **Code-first:** sinh OpenAPI từ controller và annotations, sau đó kiểm tra diff với baseline đã phát hành.

Điều quan trọng không phải chọn phương pháp nào “đúng” tuyệt đối mà là **có một artifact hợp đồng được version và kiểm tra trong CI**, không để tài liệu API trôi xa code.

Ví dụ OpenAPI rút gọn:

~~~yaml
openapi: 3.0.3
info:
  title: Order API
  version: "1.0"
paths:
  /orders/{id}:
    get:
      operationId: getOrder
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Order details
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
components:
  schemas:
    Order:
      type: object
      required: [id, status, totalAmount]
      properties:
        id: { type: string }
        status: { type: string, enum: [PENDING, CONFIRMED, CANCELLED] }
        totalAmount: { type: integer, format: int64 }
        currency: { type: string }
~~~

Bản công bố cần có quy tắc về amount unit, nullability, pagination, error contract, authentication, status transitions và giới hạn size/rate. OpenAPI mô tả nhiều khía cạnh cấu trúc nhưng **không tự bảo đảm toàn bộ hành vi nghiệp vụ**.

### 7.2. Những thay đổi có thể phá vỡ client

| Thay đổi | Rủi ro |
|---|---|
| Xóa endpoint hoặc đổi method/path | Consumer cũ không tìm thấy API |
| Xóa/đổi tên field mà consumer dùng | Deserialize hoặc logic sai |
| Đổi kiểu từ integer sang string | Mất tương thích parser |
| Một field trước đây nullable nay luôn non-null | Có thể tương thích về mặt nhận dữ liệu nhưng cần kiểm tra consumer assumptions |
| Một optional request field trở thành required | Consumer cũ gửi thiếu sẽ lỗi |
| Thêm giá trị enum mới | Có thể phá client dùng exhaustive switch |
| Đổi HTTP status/meaning của lỗi | Client retry hoặc hiển thị lỗi sai |
| Đổi quyền truy cập/scope | Client cũ có thể bị 401/403 |
| Đổi phân trang/thứ tự dữ liệu | Client có thể lặp hoặc bỏ sót |
| Thêm response field optional | Thường dễ chấp nhận nhưng strict parser có thể lỗi |
| Thêm một request field optional | Thường ít rủi ro nhưng cần kiểm tra validation/default |

Phân loại **breaking/non-breaking** phải dựa trên cả hợp đồng được công bố và tập consumer thực tế. Tool API diff giúp phát hiện thay đổi cấu trúc, nhưng đôi khi không nhìn thấy thay đổi semantics như “totalAmount nay là đơn vị cent thay vì VND”.

### 7.3. Cách đặt gate API

~~~text
New API spec
    |
    v
Validate syntax/schema
    |
    v
Compare với published baseline
    |
    +--> Breaking change? --> FAIL hoặc explicit versioning plan
    |
    v
Contract tests / provider verification
    |
    v
Publish versioned spec + evidence
~~~

Baseline nên là **phiên bản API đang được consumers sử dụng**, không chỉ file ở nhánh main. Nếu main vừa chấp nhận một breaking change khác chưa triển khai, so sánh với main có thể bỏ sót rủi ro với client đang chạy.

## 8. Consumer-driven contracts (CDC)

Trong mô hình consumer-driven contracts, consumer mô tả những tương tác thực sự cần ở provider. **Pact** là một công cụ phổ biến, nhưng ý tưởng contract có thể áp dụng với công cụ và ngôn ngữ khác.

~~~text
Billing Service (Consumer)
    |
    | ghi contract: GET /orders/{id} trả
    | id, status, totalAmount đúng kiểu
    v
Contract artifact / broker
    |
    v
Order Service (Provider)
    |
    | Verify provider đáp ứng interactions
    v
Result published, compatibility decision
~~~

Các bước thường gồm:

1. Consumer tests phát hành contract được gắn version consumer.
2. Provider CI lấy các contract liên quan và chạy verification đối với provider.
3. Kết quả verification được lưu với version provider và contract tương ứng.
4. Gate deploy/merge dựa trên **tập consumer đang được triển khai hoặc dự kiến triển khai**, không chỉ một bản mới nhất bất kỳ.
5. Khi thay đổi breaking, provider triển khai tương thích hai dạng nếu cần, chờ consumers migrate rồi mới loại bỏ dạng cũ.

Một CDC test có thể chứng minh một interaction có đúng với mock/provider tại thời điểm kiểm tra, nhưng **không bảo đảm mọi nhánh nghiệp vụ đã được test**. Provider vẫn cần tests độc lập cho validation, authorization, lỗi và database transaction.

### Vì sao không chỉ stub một provider?

Consumer test dùng stub tự viết có thể mãi xanh dù provider đổi. Giá trị của CDC nằm ở **provider verification against the same published contract** và kết quả được liên kết với các phiên bản cần triển khai.

## 9. Async contracts: Kafka/RabbitMQ và event schema

Event-driven microservices có contract không kém HTTP:

~~~json
{
  "eventId": "evt-123",
  "eventType": "OrderConfirmed",
  "eventVersion": 2,
  "occurredAt": "2026-11-12T08:00:00Z",
  "aggregateId": "ORD-1001",
  "payload": {
    "orderId": "ORD-1001",
    "amount": 590000,
    "currency": "VND"
  }
}
~~~

Cần kiểm tra:

- **Schema compatibility:** thay đổi field, default, nullability, enum, type.
- **Semantic compatibility:** amount có cùng đơn vị không? timestamp biểu diễn UTC không?
- **Envelope:** eventId, eventType, schemaVersion, correlationId, trace context theo policy.
- **Delivery semantics:** consumer có chịu được **at-least-once** và duplicate không?
- **Ordering:** thông điệp cùng aggregate có yêu cầu thứ tự không? partition key có ổn định không?
- **Reprocessing:** consumer mới có đọc được event cũ còn trong retention không?
- **Error handling:** retry, poison message, DLQ, idempotency và backfill.

Với Avro/Protobuf/JSON Schema có thể dùng **Schema Registry** hoặc công cụ so sánh schema tương ứng. Compatibility mode như backward/forward/full có ý nghĩa phụ thuộc format và quy tắc serialization; **schema compatible không tự động là business semantic compatible**.

Ví dụ đổi tên **OrderConfirmed** thành **PurchaseAccepted** nhưng không giữ consumer mapping cũ là breaking change kể cả payload cùng shape. CI cần test event type routing và contract consumer, không chỉ parse JSON.

### 9.1. Expand–migrate–contract cho event

1. Provider phát version có hỗ trợ consumer cũ hoặc cung cấp field mới mà vẫn giữ field cũ.
2. Consumers hỗ trợ cả dạng cũ và mới trong giai đoạn chuyển tiếp.
3. Theo dõi consumption, DLQ và version distribution.
4. Chỉ bỏ field/event cũ khi đã chứng minh không còn consumer hợp lệ phụ thuộc.

Không trông chờ mọi service deploy cùng giây để tránh vấn đề tương thích.

## 10. Contract với database cũng phải kiểm tra

Database là boundary chia sẻ theo thời gian giữa code cũ và code mới trong rolling deploy. Một migration có thể chạy trước khi mọi instance được nâng cấp.

Ví dụ **nguy hiểm**:

~~~sql
-- Phiên bản cũ đọc column total_amount
ALTER TABLE orders DROP COLUMN total_amount;
~~~

Nếu Pod cũ còn chạy, query sẽ lỗi. Thay bằng chiến lược **expand–migrate–contract**:

1. **Expand:** thêm column/schema mới tương thích với binary đang chạy, không xóa column cũ ngay.
2. **Migrate:** dual-read/dual-write hoặc backfill có kiểm soát, kiểm tra dữ liệu và tính nhất quán.
3. **Switch:** deploy consumer/code sử dụng cấu trúc mới sau khi dữ liệu và version readiness được xác minh.
4. **Contract:** bỏ cấu trúc cũ ở release sau khi không còn consumer cũ.

CI nên chạy migration trên **database rỗng** và trên **database chứa schema/data đại diện phiên bản trước**, test rollback/recovery strategy và kiểm tra các bước khóa bảng/DDL dài. Công cụ như Flyway hoặc Liquibase hỗ trợ versioned migrations, nhưng không tự bảo đảm migration không phá compatibility hoặc không khóa bảng quá lâu.

Đối với thay đổi lớn, thêm **performance/migration rehearsal** trong môi trường gần thực tế trước khi promote.

## 11. Security checks trong CI: Phòng thủ nhiều lớp

Bảo mật không phải một job duy nhất tên **security-scan**. Các loại rủi ro khác nhau cần tín hiệu khác nhau.

| Loại kiểm tra | Phát hiện | Giới hạn |
|---|---|---|
| **Secret scanning** | Token, private key hoặc credential lộ trong repo/diff | Không phát hiện được mọi secret; lịch sử và artifact cũng có thể chứa |
| **SAST** | Pattern code nguy hiểm: injection, deserialization, path traversal, crypto misuse | Có false positive/false negative; không xác minh toàn bộ behavior |
| **SCA/dependency scan** | CVE và vấn đề trong direct/transitive dependencies | Phụ thuộc dữ liệu advisory và mapping package/version |
| **SBOM generation** | Danh sách thành phần phần mềm và version | SBOM là inventory, không tự chứng minh artifact an toàn |
| **License policy** | Phụ thuộc license không phù hợp chính sách | Cần diễn giải pháp lý/chính sách của tổ chức |
| **IaC scan** | Security group mở quá rộng, encryption tắt, IAM quá quyền | Không bảo đảm cấu hình runtime thực tế không drift |
| **Container image scan** | Vulnerabilities trong OS packages và application dependencies | Cần biết image digest/layer và khả năng khai thác thực tế |
| **DAST/API security tests** | Lỗi xuất hiện khi chạy ứng dụng, misconfig, một số injection | Không thay thế threat modeling và kiểm thử logic nghiệp vụ |
| **Policy-as-code** | Kiểm tra bắt buộc như deny privileged containers hoặc allowlist registries | Policy sai cũng có thể chặn nhầm hoặc cho lọt |
| **Provenance/signature verification** | Nguồn build, artifact integrity và chuỗi promotion | Không chứng minh logic ứng dụng không có bug |

Một pipeline có thể chạy **secret scan + SAST nhanh** ở PR, **SCA và IaC/image scan** trong PR hoặc build, **DAST/pen testing chuyên sâu** trên artifact triển khai ở môi trường test. Không nên đợi đến sau deploy mới phát hiện secret lộ trong commit.

### 11.1. Secret scanning và phản ứng khi lộ secret

Nếu tìm thấy credential trong commit:

1. Chặn merge theo policy.
2. **Revoke/rotate secret** đã lộ; xóa khỏi branch hiện tại chưa bảo đảm credential không từng bị người khác xem.
3. Loại bỏ secret khỏi code và cấu hình; đưa vào Secret Manager/identity flow.
4. Kiểm tra phạm vi lộ gồm CI logs, artifact, PR comments và các nhánh liên quan.
5. Ghi incident/audit theo chính sách; tránh copy nguyên secret vào báo cáo scan.

Trong log CI, tool nên **redact** giá trị nhạy cảm. Không in full environment variables hoặc chạy shell với verbose trace chứa credentials.

### 11.2. SAST không thay thế authorization tests

Code có thể không vi phạm pattern injection nhưng vẫn cho Alice đọc đơn của Bob. Những lỗi **BOLA/IDOR**, tenant isolation hoặc business logic cần tests cụ thể:

~~~text
Given: Alice đã authenticated
When:  GET /orders/ORDER-OF-BOB
Then: 403 hoặc chính sách che giấu tài nguyên phù hợp
And:  không trả dữ liệu của Bob
~~~

Cần test các trường hợp **cùng scope nhưng khác object owner**, không chỉ test “có token” và “không token”.

## 12. SCA, SBOM, CVE và cách phân loại rủi ro

Dependency của một Java service thường gồm thư viện direct, transitive, plugin build, base image packages và runtime components. SCA dùng advisory để phát hiện phiên bản có lỗ hổng.

Không nên đặt duy nhất quy tắc **mọi CVE có severity HIGH đều làm mọi PR fail mãi mãi** rồi khiến team bắt đầu tắt scanner. Một policy thực dụng xét:

- **Mức độ nghiêm trọng** và dạng tác động.
- Dependency có thực sự nằm trong **artifact/runtime path** hay chỉ test/build-time?
- **Exploitability/độ phổ biến khai thác** và điều kiện kích hoạt với workload cụ thể.
- Service có Internet exposure hoặc xử lý dữ liệu nhạy cảm?
- Có bản vá hoặc biện pháp giảm thiểu hợp lệ?
- Lỗ hổng mới được đưa vào so với **baseline đã chấp nhận**?
- SLA xử lý theo risk tier và thời hạn ngoại lệ.

Ví dụ: một vulnerability mới, đã có exploit, ảnh hưởng runtime của internet-facing Payment API có thể là **hard fail**. Một advisory ảnh hưởng thư viện test không đóng gói vào runtime có thể cần xử lý theo SLA khác. Việc xác định **reachable/not reachable** phải có bằng chứng; scanner không tìm thấy đường gọi không tự chứng minh an toàn tuyệt đối.

**SBOM** (Software Bill of Materials) nên được tạo gắn với **artifact digest** và lưu như bằng chứng của build. Dùng định dạng thông dụng như CycloneDX hoặc SPDX theo hệ sinh thái. SBOM hỗ trợ truy vấn “những service nào dùng thư viện X?” khi có lỗ hổng mới sau khi phát hành.

### 12.1. Bảo vệ chuỗi cung ứng phần mềm

CI là thành phần nhạy cảm vì có thể build và ký artifact:

- Pin dependency version, dùng lockfile hoặc dependency management/BOM.
- Ưu tiên build không phụ thuộc artifact “latest” trôi theo thời gian.
- Kiểm soát repository và package provenance; tránh package từ nguồn không tin cậy.
- Không cho untrusted pull request tự động nhận **deploy secrets**.
- Dùng **short-lived credentials / workload identity / OIDC federation** khi tương thích.
- Giới hạn quyền token của workflow, runner và artifact registry.
- Tạo artifact bất biến, gắn commit SHA, build run, SBOM, provenance và chữ ký khi chính sách yêu cầu.
- Khi promote từ staging sang production, **promote cùng digest**, không tự rebuild lại từ source.
- Kiểm tra chữ ký và provenance tại điểm deploy nếu tổ chức thiết kế cơ chế admission.

Đối với workflow gọi action/plugin bên thứ ba, nên pin version theo policy, và trong môi trường nhạy cảm có thể pin **full commit SHA** được kiểm soát để giảm rủi ro thay đổi upstream ngoài ý muốn.

## 13. Kiểm tra IaC, container và deployment manifests

Một ứng dụng có unit tests xanh vẫn có thể được triển khai với:

- Container chạy dưới root khi không cần.
- Privileged mode hoặc hostPath mount quá rộng.
- Kubernetes service account có quyền cluster-admin.
- Public LoadBalancer hoặc security group mở đường quản trị.
- Secret được in vào biến môi trường/log hoặc file được commit.
- Không đặt resource requests/limits phù hợp, readiness/liveness sai.
- NetworkPolicy thiếu hoặc ingress cho mọi nguồn.
- Image tag **latest** không truy ra được artifact.

Pipeline nên thực hiện:

1. **Parse/validate** manifest, Helm chart hoặc Terraform plan.
2. **Schema validation** theo Kubernetes API version/thành phần tương ứng.
3. **Policy-as-code** kiểm tra điều kiện không được vi phạm.
4. **IaC security scan** cho IAM, networking, encryption và secret exposure.
5. **Environment diff/review:** biết chính xác thay đổi gì trước khi apply.
6. **Post-deploy verification:** đối chiếu cấu hình thực tế, không chỉ tin file nguồn.

Cần phân biệt **configuration policy** (ví dụ workload không được privileged) và **architecture policy** (ví dụ service thuộc miền Payment không được gọi trực tiếp database Order).

## 14. Architecture tests: Biến nguyên tắc thành code

Architecture drift xảy ra khi code compile nhưng từng thay đổi nhỏ làm phá vỡ các ranh giới đã chọn.

Ví dụ trong kiến trúc phân lớp:

~~~text
com.example.order
  ├── api
  ├── application
  ├── domain
  └── infrastructure
~~~

Một quy tắc có thể là **domain không phụ thuộc vào api hoặc infrastructure**, và **api chỉ gọi application**, không truy cập repository/adapter trực tiếp.

Với Java, **ArchUnit** hỗ trợ kiểm tra dependency giữa packages và classes:

~~~java
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.lang.ArchRule;
import org.junit.jupiter.api.Test;

class ArchitectureRulesTest {

    @Test
    void domainMustNotDependOnInfrastructureOrApi() {
        var classes = new ClassFileImporter()
            .importPackages("com.example.order");

        ArchRule rule = noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAnyPackage("..infrastructure..", "..api..");

        rule.check(classes);
    }
}
~~~

Quy tắc kiểm tra phụ thuộc code, không tự xác minh **ý định nghiệp vụ** của mọi class. Nếu team có cấu trúc package khác, viết rules theo kiến trúc thực tế, không copy tên package một cách máy móc.

Các ràng buộc thường hữu ích:

- Domain không phụ thuộc trực tiếp framework web/persistence nếu đó là lựa chọn kiến trúc.
- Controller không gọi database repository trực tiếp.
- Module **payments** không truy cập class **internal** của module **orders**.
- Không tồn tại cyclic dependency giữa module quan trọng.
- Không import thư viện bị cấm hoặc sử dụng API deprecated ở boundary đã công bố.
- Các service không truy cập schema/database sở hữu của service khác.
- API public chỉ lộ DTO/contract, không lộ JPA entity.
- Thư viện dùng chung không chứa logic domain của nhiều bounded contexts làm tăng coupling.

**Lưu ý:** Quy tắc “database ownership” xuyên repository thường phải kết hợp static analysis, IaC/network policy và integration tests; ArchUnit trong một repository không thể tự biết mọi SQL được chạy ở service khác.

## 15. Kiểm tra coupling giữa microservices

Trong một monorepo hay multi-repo, ranh giới service không chỉ là package. Có các dấu hiệu coupling:

- Service A import trực tiếp source hoặc internal library riêng của B.
- Cả hai dùng chung DTO nội bộ nhưng không có versioning contract.
- A tự query vào database schema của B.
- Một service triển khai version mới buộc nhiều service khác deploy cùng lúc.
- RPC fan-out tăng và có dependency cycle: Order → Payment → Inventory → Order.
- Đồng bộ hóa logic nghiệp vụ bằng cách chia sẻ một “common” module khổng lồ.

Kiểm tra trong CI có thể gồm:

1. **Dependency graph:** phát hiện cycle hoặc forbidden edge.
2. **Build module boundaries:** chỉ cho phép public modules/declared interfaces.
3. **Static checks:** cấm import/endpoint/DB schema đặc thù.
4. **API/event compatibility checks:** phát hiện thay đổi ảnh hưởng consumer.
5. **Architecture decision record (ADR) policy:** thay đổi ranh giới lớn cần review ADR, nhưng không nên bắt máy móc mọi PR đều tạo ADR.

Một CI gate tốt tự động hóa **những quy tắc có thể kiểm chứng**. Các đánh đổi lớn như tách bounded context hay chọn giữa choreography và orchestration vẫn cần **human architecture review** với bằng chứng, không thay bằng một điểm số tự sinh.

## 16. NFR gates: Hiệu năng và độ bền

**Non-functional requirements** có thể suy giảm ngay cả khi chức năng đúng.

Các kiểm tra có giá trị:

- **Performance smoke:** số request nhỏ, so với baseline về latency/throughput.
- **Query plan/regression:** tránh thêm N+1 queries hoặc full scan ở luồng nóng.
- **Resource budget:** kích thước image, startup time, CPU/RAM baseline, giới hạn connection pool.
- **Resilience:** timeout/retry/circuit breaker, idempotency, duplicate event handling, backpressure.
- **Concurrency tests:** race condition, transaction isolation và lock contention với kịch bản quan trọng.
- **Accessibility/compatibility:** nếu có frontend/mobile, kiểm tra phù hợp sản phẩm.
- **Deployment safety:** startup/readiness, graceful shutdown và backward-compatible migrations.

Performance test trong CI chia sẻ runner có thể nhiễu; tránh đặt gate cực kỳ nhạy dựa vào một lần đo trên môi trường không ổn định. Dùng **budget đủ biên độ**, repeated runs, statistical confidence hoặc dedicated performance runner cho kiểm tra nghiêm ngặt. Với load/soak tests dài, nên dùng scheduled/release stage và theo dõi xu hướng.

## 17. Quality gate theo mức rủi ro và bối cảnh

Không phải tất cả kết quả đều phải chặn merge ngay. Có thể xây ma trận:

| Check | Pull request | Trước release | Xử lý khi fail |
|---|---|---|---|
| Compile/build | **Required** | Required | Block |
| Formatting/lint chuẩn đã thống nhất | Required | Required | Block/auto-fix |
| Unit + architecture tests | **Required** | Required | Block |
| Component/integration tests cốt lõi | Required theo service | Required | Block nếu regression |
| API contract diff phá tương thích | **Required** | Required | Block hoặc approved compatibility plan |
| Consumer/provider verification | Required nếu đổi boundary | Required | Block deploy khi không tương thích |
| Event schema compatibility | Required khi đổi event | Required | Block/upgrade strategy |
| Secret scanning | **Required** | Required | Block + revoke/rotate nếu đã lộ |
| SAST critical policy | Required | Required | Block theo policy |
| SCA/runtime critical actionable | Required hoặc cảnh báo theo SLA | Required | Risk-based block/exception |
| IaC security / container image | Required nếu đổi deploy | Required | Block theo severity/policy |
| SBOM + provenance + artifact integrity | Có thể tạo ở build | Required theo supply-chain policy | Không promote nếu thiếu bằng chứng bắt buộc |
| Full E2E / performance / DAST sâu | Chọn lọc | Required theo release risk | Có thể chạy ở dedicated gate |
| Manual architecture review | Khi đổi ranh giới lớn | Theo policy | Review/ADR |

**Required check** phải có owner, mô tả hành vi khi bị lỗi, cơ chế xử lý false positive và nơi xem kết quả. Không tuyên bố “all green” nếu check chưa chạy, bị skip không đúng lý do hoặc bị vô hiệu hóa bởi workflow path filter.

### 17.1. Hard fail, warning và ngoại lệ

- **Hard fail:** thay đổi chắc chắn không build, test trọng yếu lỗi, secret lộ, breaking contract không có chiến lược tương thích, policy vi phạm nghiêm trọng.
- **Warning/advisory:** code smell mới mức thấp, dependency advisory chưa xác thực, đề xuất cải thiện performance chưa đủ độ tin cậy.
- **Exception có kiểm soát:** issue ID, lý do, owner, scope component/version, expiry, mitigations, người phê duyệt; tự động hết hạn và bị kiểm tra lại.
- **Quarantine flaky test:** phải có tracking, hạn xử lý và coverage thay thế nếu rủi ro cao; không “disable forever”.

**Không viết exception toàn cục** kiểu skip mọi security scan. Ngoại lệ cụ thể giúp pipeline giữ uy tín và ngăn acceptance rủi ro âm thầm.

## 18. Ví dụ GitHub Actions CI tối giản cho Java/Spring

Ví dụ bên dưới minh họa **cấu trúc**; tên action/version và plugin dự án cần được xác minh theo stack đang dùng. Trong môi trường nhạy cảm, pin actions theo full commit SHA và quản lý quyền runner theo chính sách tổ chức.

~~~yaml
name: service-ci

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: maven
      - name: Maven verify
        run: ./mvnw -B -ntp verify
      - name: Upload test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: surefire-reports
          path: |
            **/target/surefire-reports/**
            **/target/failsafe-reports/**
          if-no-files-found: ignore

  contract:
    needs: verify
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - name: Validate and compare published API contracts
        run: ./ci/check-contract-compatibility.sh

  architecture:
    needs: verify
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - name: Architecture verification
        run: ./mvnw -B -ntp -Dtest=ArchitectureRulesTest test
~~~

**Những điều cần triển khai thật trước khi chạy:**

- **check-contract-compatibility.sh** là script do dự án cung cấp; ví dụ không giả định script đã tồn tại.
- Job **verify** nên bao gồm unit/integration rules qua Maven profiles và plugin đã cấu hình. **mvn verify** không tự nhiên chạy SAST, SCA, secret scan hoặc contract tests nếu chưa được cài đặt.
- Một số integration tests dùng Docker/Testcontainers cần runner có Docker daemon phù hợp.
- Quyền workflow được giữ ở mức **contents: read** trong PR. Không để untrusted PR workflow có write/deploy permissions hoặc truy cập production secrets.
- **Upload test reports** giúp điều tra dù Maven verify thất bại; runner vẫn phải tuân thủ retention/PII policy.
- Cần thêm jobs security, IaC, image scan, SBOM/provenance/signing ở pipeline phù hợp; ví dụ trên không tự đại diện cho pipeline production hoàn chỉnh.
- Branch protection/rulesets phải yêu cầu **đúng job names** và không cho merge khi các required checks bị skip/bypass ngoài policy.

Nếu dùng GitLab CI, Jenkins hoặc Azure Pipelines, logic gate và phạm vi quyền vẫn tương tự nhưng syntax khác.

## 19. Cấu trúc Maven cho tầng kiểm thử

Một dự án Java có thể tổ chức:

~~~text
service/
  pom.xml
  src/main/java/...
  src/test/java/...                 # unit + selected component tests
  src/test/resources/...
  src/it/java/...                   # integration tests nếu profile/build hỗ trợ
  architecture-tests/
  contracts/
    openapi/order-api.yaml
    events/order-confirmed-v2.json
  ci/
    check-contract-compatibility.sh
    scan-security.sh
    validate-helm.sh
~~~

Có thể dùng Maven Surefire cho unit tests, Failsafe cho integration tests hoặc một cấu hình tương đương. Điều quan trọng là tên/profile được ánh xạ rõ thành các gates:

~~~text
./mvnw -B -ntp test
  → unit/component fast tests

./mvnw -B -ntp verify
  → tests và các plugin bound to lifecycle trong pom.xml

./ci/check-contract-compatibility.sh
  → OpenAPI/event diff so với published baseline

./ci/scan-security.sh
  → SAST/SCA/secrets theo công cụ đã cài và policy
~~~

Không nên truyền một option **-DskipTests** trong release gate rồi vẫn công bố build đã được kiểm thử. Nếu cần skip test ở một job chuyên trách (ví dụ packaging sau khi cùng commit đã qua test), phải **liên kết evidence của đúng commit/artifact**, tránh bỏ qua hoàn toàn mà không có đảm bảo.

## 20. Test data, môi trường và determinism

Lỗi CI có thể do môi trường test, không phải code. Nhưng việc này không biện minh cho retry tất cả tests không giới hạn.

Các nguyên tắc:

- **Isolation:** mỗi job/test dùng database/schema/namespace riêng hoặc test dữ liệu theo khóa duy nhất.
- **Reproducibility:** dependency versions, container image digest, test fixtures có version.
- **Fixed time / fake clock:** test logic hết hạn, lịch và timeout mà không phụ thuộc thời gian thực.
- **Stable test data:** dùng fixtures không chứa dữ liệu production nhạy cảm.
- **Concurrency safety:** tests có thể chạy song song mà không giẫm resource nhau.
- **Control external dependencies:** dùng fake/stub cho bên thứ ba khi hợp lý, nhưng giữ integration verification cho những boundary thật cần kiểm tra.
- **Network flakiness:** xác định timeout, retries có hạn ở test setup; không che lỗi nghiệp vụ.
- **Clear failure logs:** chỉ thu thập logs cần thiết, redact secret và PII.

Khi một test fail không ổn định, tách vấn đề bằng bằng chứng: lịch sử failure, môi trường, test order, resource usage, timing, race, network. **Quarantine** là phương án tạm thời có owner và deadline, không phải định nghĩa “flaky tests không quan trọng”.

## 21. Cấu trúc artifact và bằng chứng release

Một pipeline nên tạo bản ghi có thể truy xuất:

~~~text
commit: abc1234
service: order-service
build-run: ci-2026-11-12-418
artifact-digest: sha256:...   # placeholder, không phải digest thật
quality:
  compile: passed
  unit-tests: passed
  integration-tests: passed
  architecture: passed
contracts:
  openapi-diff: compatible
  provider-verification: passed
security:
  secret-scan: passed
  sca-policy: passed
  image-policy: passed
supply-chain:
  sbom: attached
  provenance: attached
  signature: verified
~~~

Đây là **biểu diễn evidence minh họa**, không phải một chuẩn định dạng. Trong triển khai thực tế, evidence phải liên kết với **commit, build run và artifact digest**, có nguồn kiểm chứng; không tin một file JSON tự khai **passed** nếu nó có thể bị PR không đáng tin cậy sửa trực tiếp.

Đối với container, dùng **OCI digest** khi promote. Tag như **v1.8.0** có thể hữu ích cho con người nhưng không thay thế bằng chứng byte-identical của digest trong các môi trường.

## 22. Chính sách branch protection và quyền merge

Quality gate không có giá trị nếu mọi người có thể bỏ qua mà không có audit.

Thiết kế quản trị:

1. **Required checks:** chỉ định chính xác workflow/job bắt buộc cho nhánh bảo vệ.
2. **Review:** số lượng/phạm vi approvers tương ứng rủi ro; review không thay tự động tests.
3. **CODEOWNERS:** thay đổi authentication, payment, deployment/IaC, shared contracts có owner chuyên môn.
4. **No silent bypass:** quyền bypass hạn chế, có audit và quy trình emergency rõ.
5. **Checks on final commit:** kết quả phải khớp commit sẽ merge; tránh dùng pass của commit cũ sau rebase/force-push.
6. **External contribution:** workflow PR không nhận secret nhạy cảm; phân quyền tách job kiểm tra và job deploy.
7. **Merge queue khi phù hợp:** bảo đảm kết quả trên sự kết hợp của các PR có thể gây conflict hoặc regression.
8. **Dependency update bots:** đi qua cùng contract/security rules, không tự merge chỉ dựa vào tên bot.

Nếu workflow path filters làm job **không chạy**, branch protection phải diễn giải trạng thái đó theo policy. Không gắn nhãn **PASS** cho một bước bị skip mà rủi ro vẫn còn.

## 23. Chính sách scan hiệu quả và xử lý false positives

Một scanner có thể báo nhiều issue không liên quan, nhất là với generated code hoặc dependency chỉ dùng test. Cần tránh hai cực:

- **Bỏ qua toàn bộ scanner** vì có false positives.
- **Chặn mọi thay đổi** dựa trên hàng nghìn issues tồn tại từ trước, khiến developer phải tìm cách bypass.

Phương án:

1. Lập **baseline** của nợ kỹ thuật và rủi ro cũ được biết.
2. Chặn **newly introduced violations** theo policy nghiêm ngặt.
3. Lập backlog xử lý baseline theo severity và thời hạn.
4. Mỗi suppression phải có **reason, scope, owner, expiry**.
5. Định kỳ nâng ruleset, dependency advisory database và verify scan coverage.
6. Tách lỗi **scanner infrastructure unavailable** khỏi kết luận **security clean**.
7. Nếu scanner không chạy, đánh giá gate là **UNKNOWN/FAIL** theo policy, không tự tuyên bố PASS.

Một lỗ hổng có exploit active hoặc secret lộ có thể yêu cầu phản ứng ngay bất kể nó “đã có từ trước”, nên baseline không phải giấy phép bỏ qua mọi rủi ro cũ.

## 24. Contract gate khi có nhiều phiên bản triển khai song song

Microservices được deploy độc lập nên cùng lúc có:

~~~text
Order API provider:
  production: v12
  staging:    v13
  main:       v14

Consumers:
  Billing production: v7
  Reporting production: v3
  Mobile client: nhiều phiên bản vẫn còn hoạt động
~~~

Một API diff chỉ so **v14 với v13** chưa chắc phát hiện Billing v7 vẫn dùng field bị xóa từ v12. Tương tự, CI của provider pass nhưng consumer mobile phát hành lâu trước vẫn còn tồn tại.

Cần xác định:

- Provider đang chạy phiên bản nào ở từng environment?
- Consumer nào đang tồn tại và dùng hợp đồng nào?
- Có **compatibility horizon** cho mobile/partner APIs lâu hơn backend nội bộ không?
- Có thể chấp nhận song song nhiều API versions trong bao lâu?
- Khi nào được retire một endpoint/field? Bằng chứng telemetry/contract nào xác nhận?
- Gate deploy dựa trên **các versions đang/sắp được triển khai** chứ không chỉ mã mới nhất?

**Không đồng nhất merge compatibility với deploy compatibility.** Một thay đổi có thể merge sau khi đã implement dual-read, nhưng chưa được phép xóa field cũ cho đến khi consumers migrate.

## 25. Architecture governance và ADR trong CI

**Architecture Decision Record (ADR)** lưu lý do chọn phương án, phạm vi và các lựa chọn đã cân nhắc. CI có thể kiểm tra:

- Một thay đổi ranh giới lớn có chỉnh sửa tài liệu kiến trúc theo policy không?
- Dependency graph có phát sinh edge bị cấm không?
- API/event schema có version và owner không?
- Module có vi phạm rule đã mã hóa bằng ArchUnit/dependency checks không?
- Deployment manifest có tạo quyền truy cập trái trust boundary không?

Tuy nhiên CI không thể phán quyết hoàn toàn những câu hỏi như “tách service nào là hợp lý” hoặc “saga orchestration tốt hơn choreography ở domain này không”. Các quyết định đó cần **review có người**, dựa trên SLO, coupling, ownership và chi phí vận hành.

Một anti-pattern là dùng CI như công cụ áp đặt phong cách kiến trúc không phù hợp mọi module. Rules nên có **động cơ và phạm vi rõ**, ví dụ module payment có yêu cầu đặc thù hơn module reporting.

## 26. Ví dụ workflow thay đổi Order → Payment

Đề bài: developer thêm field **paymentMethod** vào request tạo order và thêm event mới **PaymentRequested**.

### 26.1. Những vấn đề có thể phát sinh

- Order API bỏ bắt buộc field cũ hoặc thay response JSON làm web client lỗi.
- Payment Service không hiểu event version mới.
- Một value enum lạ khiến Billing dùng switch thiếu default.
- Consumer chạy trùng event, tạo hai giao dịch thanh toán.
- Log request vô tình chứa card details hoặc access token.
- Migration mới drop column mà Pod cũ còn sử dụng.
- Dependency mới có advisory bảo mật.
- Service Order import trực tiếp repository của Payment module, phá ranh giới.

### 26.2. Các gate phù hợp

| Rủi ro | Tín hiệu CI |
|---|---|
| Validation request sai | Web/controller tests |
| Sai logic tạo order | Unit tests/domain invariants |
| Giao dịch DB/outbox không nhất quán | Integration tests dùng DB/broker phù hợp |
| API breaking change | OpenAPI diff + consumer contract verification |
| Event không tương thích | Schema registry compatibility + consumer tests |
| Giao event trùng tạo thanh toán trùng | Idempotency/duplicate delivery integration tests |
| Log rò dữ liệu nhạy cảm | Secure logging tests + SAST/secret policy |
| Migration phá rolling deploy | Migration compatibility test |
| Phụ thuộc sai lớp | ArchUnit/dependency graph gate |
| Dependency vulnerability | SCA + risk policy |
| Image/IaC cấu hình nguy hiểm | Image/IaC policy gates |

Khi các gate xanh, artifact vẫn cần đi qua **staging smoke, canary và production monitoring**. CI giảm rủi ro trước merge/promotion, không hứa hẹn không có lỗi thực tế.

## 27. Khi nào chạy song song, khi nào chạy nối tiếp?

**Song song thích hợp** khi job độc lập:

~~~text
Checkout
   |
   +--> Compile/Lint
   +--> SAST/Secret Scan
   +--> Architecture rules
   +--> Contract syntax/diff
~~~

Các job sau cần artifact hoặc môi trường:

~~~text
Compile → Unit/Component tests → Package
                                |
                                +--> Integration tests
                                +--> Build image → Image scan / SBOM
                                +--> Provider contract verification
                                                 |
                                                 v
                                          Promotion gate
~~~

Chạy mọi việc song song không luôn nhanh hơn: Docker image cần được build trước khi scan đúng image digest, provider verification có thể cần service fixture, và các job dùng chung database có thể làm test flaky. Cần xác định **dependency edges** theo dữ liệu thật, đồng thời dùng caching và parallelism có kiểm soát.

Cache build/dependency không được trở thành nguồn artifact không tin cậy hoặc làm bypass scanner. Cache keys nên tính đến lockfiles, toolchain và trust boundary của branch/PR.

## 28. CI và deployment: Rollout an toàn sau gates

Ngay cả khi CI pass, production vẫn là môi trường có traffic thực, dữ liệu thực và dependency chưa thể mô phỏng đầy đủ.

Kế hoạch phát hành nên gồm:

1. **Promote cùng artifact digest** đã qua gate.
2. **Deploy tới staging** tương thích production về các dependency quan trọng.
3. **Smoke checks** cho API, database connectivity, event processing và auth.
4. **Canary/progressive delivery** theo instance/traffic/region khi phù hợp.
5. **Theo dõi RED metrics, error budgets, consumer lag, DLQ, business invariants**, không chỉ CPU/RAM.
6. **Kill switch/feature flag** có giới hạn quyền và default an toàn.
7. **Rollback hoặc roll-forward** khi cần; database migrations có thể làm binary rollback phức tạp nên thiết kế expand–contract trước.

Một deploy thất bại có thể do config/secret/runtime environment. Việc đó cần feedback trở lại CI và contract tests để ngăn lặp ở lần sau.

## 29. Metrics để cải thiện chính hệ thống CI

Không nên chỉ đo “bao nhiêu test cases đã chạy”. Những chỉ số hữu ích:

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| **Speed** | PR pipeline p50/p95, queue time, time-to-first-failure | Developer nhận phản hồi nhanh đến đâu |
| **Reliability** | Flaky rate, infra failures, rerun rate | Pipeline có đáng tin không |
| **Coverage** | Tỷ lệ API/event boundaries có contract verification | Rủi ro tích hợp nào đã được kiểm chứng |
| **Security** | Scan coverage, time-to-remediate, exception age | Chính sách có thực thi và xử lý được không |
| **Architecture** | Số forbidden dependency edges, module cycles, suppressions | Ranh giới hệ thống có bị xói mòn |
| **Delivery** | Lead time, change failure rate, rollback cause | CI có giảm lỗi phát hành không |
| **Cost** | Compute minutes, container build cost, cache hit rate | Cân bằng thời gian và chi phí |

Không nên tối ưu bằng cách đơn giản **giảm số test để pipeline nhanh**. Nhanh hơn chỉ có ý nghĩa nếu khả năng phát hiện rủi ro quan trọng vẫn đủ và các lỗi bị chặn trước khi lan ra production.

### 29.1. Cách xử lý một check thường xuyên fail

1. Xác định đó là **lỗi sản phẩm**, **lỗi môi trường test**, **flaky assertion** hay **tooling outage**.
2. Ghi lại bằng chứng failure và tái hiện có kiểm soát.
3. Sửa nguyên nhân thay vì tăng retry vô hạn.
4. Nếu cần tạm cách ly, đặt owner/expiry và kiểm soát release risk.
5. Thêm metric cho tỷ lệ skip/quarantine và kiểm tra định kỳ.

Một check mà developer không tin sẽ bị bỏ qua. **Độ tin cậy của gates là một tài sản vận hành.**

## 30. Anti-pattern cần tránh

**1. CI xanh vì chỉ chạy compile.** Không có unit, contract hay security tests để phát hiện lỗi tích hợp.

**2. Dùng E2E khổng lồ thay cho mọi loại test.** Pipeline chậm, khó debug, flaky và vẫn không chỉ rõ contract nào bị phá.

**3. Chỉ dùng coverage percentage.** Test có thể chạy qua toàn bộ code mà không assert behavior hoặc kiểm tra nhánh lỗi.

**4. So sánh OpenAPI chỉ với nhánh main.** Bỏ sót consumers thực tế đang dùng version lâu hơn.

**5. Contract tests chỉ chạy ở consumer, không verify provider.** Stub vẫn xanh khi provider đã thay đổi.

**6. Kiểm tra schema event nhưng bỏ qua semantics.** Field **amount** vẫn integer nhưng chuyển từ VND sang xu gây sai nghiệp vụ.

**7. Thêm SAST/SCA nhưng tắt khi có false positives.** Cần baseline, suppression có owner/expiry và risk-based triage.

**8. Chấp nhận scan không chạy như PASS.** Tool unavailable là trạng thái thiếu bằng chứng, không phải bằng chứng an toàn.

**9. CI trên PR có quyền deploy production.** Làm tăng nguy cơ khai thác qua source code không đáng tin.

**10. Deploy bằng cách rebuild image từ cùng git tag.** Không còn chắc artifact đã được scan là artifact đang chạy; dùng digest và provenance.

**11. Ghi secret hoặc token vào CI logs.** Pipeline trở thành kênh rò rỉ credential; dùng secret manager và redact.

**12. Không kiểm tra migration với binary cũ.** Rolling deployment gây outage dù migration thành công trên DB trống.

**13. Tất cả kiến trúc nằm trong wiki không có enforceable rules.** Code drift dần đến coupling khó gỡ.

**14. Chặn mọi PR bằng một test benchmark nhiễu.** Developer có xu hướng bỏ gate; dùng môi trường/budget phù hợp.

**15. Không quan sát gate skip/bypass.** Bề ngoài có pipeline đầy đủ nhưng nhiều đường code không được kiểm tra.

## 31. Lộ trình triển khai theo mức trưởng thành

### Giai đoạn 1 — Tạo nền tảng đáng tin

- Bảo vệ nhánh main, yêu cầu compile, format, unit tests và test reports.
- Cài secret scanning; khóa quyền workflow ở mức tối thiểu.
- Dùng dependency management/lockfiles và artifact version cố định.
- Chạy integration tests quan trọng với database/broker phù hợp.
- Tổ chức failure output đủ để developer sửa được.

### Giai đoạn 2 — Khóa ranh giới tích hợp

- Đưa OpenAPI/event schemas vào version control và phát hành artifact.
- Thêm API diff và provider/consumer contract verification.
- Thêm migration compatibility tests và negative authorization tests.
- Áp dụng ArchUnit/module dependency rules cho những ranh giới có giá trị.
- Tạo baseline SCA và policy exceptions có thời hạn.

### Giai đoạn 3 — Supply-chain và promotion

- Build immutable image theo digest, tạo SBOM.
- Scan image/IaC với policy bắt buộc.
- Ghi provenance/attestation và ký artifact nếu yêu cầu.
- Tách quyền PR, build và deploy; dùng short-lived credentials.
- Dùng cùng artifact digest cho staging và production.

### Giai đoạn 4 — Tối ưu và kiểm soát rủi ro sâu

- Tailor gates theo service tier và threat model.
- Thêm performance/resilience tests có giá trị, scheduled deep scans.
- Canary và theo dõi release metrics.
- Đo false-positive/flaky rate, thời gian phản hồi, chi phí chạy CI.
- Thực hiện incident review để thêm test/contract rule phòng ngừa tái diễn.

Mỗi giai đoạn cần có **owner**, định nghĩa hoàn tất và khả năng đo được; không nên thêm hàng loạt tool trước khi các gate hiện có đáng tin.

## 32. Checklist cho một pull request microservice

Trước khi merge thay đổi có ảnh hưởng behavior hoặc boundary, cần trả lời:

1. Code có compile, lint/format và unit tests pass không?
2. Có unit test cho điều kiện biên, lỗi, retry, concurrency/idempotency khi liên quan không?
3. Những integration boundaries thay đổi có test với database/broker/client đủ tương đồng production không?
4. OpenAPI contract có cập nhật, diff và được kiểm tra với consumers đang triển khai không?
5. Event schema/semantics có tương thích hoặc có kế hoạch migration/phát song song không?
6. DB migration có tương thích với Pod cũ/new trong rolling deploy không?
7. SAST, secrets, SCA, IaC, image scan đã chạy **thật** và có evidence không?
8. Không có secrets/PII lộ qua source, logs, test fixtures hoặc artifacts chứ?
9. Code có vi phạm module/service boundary hay ADR quan trọng không?
10. Dependency, toolchain, container base image đã được pin và rà rủi ro theo policy không?
11. Test không phụ thuộc data/clock/network thiếu kiểm soát chứ?
12. Required checks có khớp chính xác commit merge và branch protection không?
13. Artifact có build digest, SBOM/provenance/signature cần thiết không?
14. Có thể rollout, giám sát và rollback/roll-forward an toàn không?
15. Nếu có exception, nó có owner, justification, scope và expiry rõ không?
16. Nếu một check fail vì scanner/runner lỗi, hệ thống có ghi nhận **không xác nhận được** thay vì báo pass không?

## 33. Kết luận

**CI là hệ thống tự động kiểm tra rủi ro trước tích hợp, không đơn thuần là một lệnh chạy tests.**

Đối với microservices, cần bảo vệ đồng thời bốn lớp:

- **Chất lượng:** code đúng hành vi, có kiểm thử phù hợp và phản hồi nhanh.
- **Hợp đồng:** HTTP API, events, database và phiên bản service cùng tồn tại được trong rollout.
- **Bảo mật:** source, dependency, secret, IaC, image và chuỗi cung ứng có kiểm soát.
- **Kiến trúc:** module boundaries, ownership, dependency graph và quyết định thiết kế được thực thi ở nơi có thể tự động hóa.

Sau các gates, **cùng một artifact đã được kiểm chứng** được promote qua các môi trường, kết hợp kiểm tra khi deploy và observability thực tế.

**Câu hỏi cốt lõi:** *Nếu Order Service thay đổi hôm nay, CI có đủ bằng chứng để khẳng định các consumer đang chạy vẫn hiểu hợp đồng, không có rủi ro bảo mật mới không được chấp nhận, và không phá ranh giới kiến trúc — trước khi thay đổi đó được merge hoặc triển khai?*

Một pipeline tốt phải trả lời bằng **test reports, contract verification, scan evidence và policy decisions có thể truy xuất**, không chỉ bằng một dấu tick xanh.
