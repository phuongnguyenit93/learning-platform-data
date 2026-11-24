# Cân bằng tốc độ kiểm thử với mức tin cậy

## Mục tiêu bài học

**Spring Cloud Contract** giúp producer và consumer thống nhất hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**. Contract Verifier sinh kiểm thử phía producer; stub artifact cho phép consumer kiểm tra code với hành vi producer được mô tả qua **Stub Runner**; các kiểm tra này có thể chạy trong CI để phát hiện thay đổi API không tương thích.

Một hệ thống có thể có hàng trăm contracts, nhiều consumers, nhiều broker và nhiều môi trường. Nếu chạy mọi loại kiểm thử sau mỗi thay đổi, pipeline sẽ chậm và tốn tài nguyên. Nếu chỉ chạy một vài unit tests hoặc một consumer stub test đơn lẻ, pipeline có thể xanh nhưng vẫn bỏ sót lỗi ở serialization, message routing, transaction hoặc tích hợp thật.

Bài **“Cân bằng tốc độ kiểm thử với mức tin cậy”** thuộc chương **Lựa chọn chiến lược**. Mục tiêu là thiết kế một **danh mục kiểm thử theo rủi ro**: mỗi loại test phải trả lời một câu hỏi rõ ràng, chạy ở thời điểm phù hợp và có giới hạn bằng chứng được công bố.

Sau bài học, bạn có thể:

- Phân biệt mức tin cậy mà unit, producer contract, consumer Stub Runner, broker integration và end-to-end tests cung cấp.
- Chọn tập tests tối thiểu cần chạy trên pull request, nightly và trước release.
- Quyết định test nào cần chạy khi thay đổi contract, DTO, serializer, binding, broker hoặc business logic.
- Tối ưu tốc độ bằng fixture deterministic, test isolation, parallelism và cache an toàn.
- Giảm flaky tests mà không che lỗi bằng retry vô điều kiện.
- Dùng negative tests, mutation checks và consumer compatibility matrix để đánh giá chất lượng assertions.
- Đo thời gian pipeline, failure rate, flakiness và thời gian phản hồi mà không hy sinh bằng chứng quan trọng.
- Thiết kế CI gates cho producer và consumer, có provenance của stub artifact.

**Nguyên tắc cốt lõi:** nhanh và tin cậy không phải hai lựa chọn loại trừ nhau. Hãy chạy kiểm tra rẻ, xác định lỗi sớm thường xuyên; chạy kiểm tra tích hợp đắt hơn ở những thay đổi có rủi ro tương ứng; và luôn giữ một release gate đủ bằng chứng cho phạm vi được hỗ trợ.

## 1. Tại sao cần chiến lược kiểm thử?

Giả sử hệ thống có:

- Order Service phát event `ORDER_PAID`.
- Shipping Service nhận event và tạo shipment.
- Billing Service cập nhật sổ thanh toán.
- Notification Service gửi thông báo.
- Nhiều HTTP consumers gọi Order API.

Mỗi producer contract có thể tạo nhiều scenarios; mỗi consumer có test riêng; một số flows cần broker, database hoặc môi trường tích hợp. Nếu mọi PR đều dựng đầy đủ môi trường production-like, thời gian feedback tăng lên. Nếu chỉ test bằng mock nội bộ, thay đổi message schema có thể phá consumer mà không được phát hiện.

Một chiến lược tốt trả lời bốn câu hỏi:

1. **Điều gì có thể hỏng?** Ví dụ schema, serialization, destination, ordering, idempotency hoặc business logic.
2. **Test nào phát hiện được loại lỗi đó?**
3. **Test đó tốn bao lâu và cần tài nguyên gì?**
4. **Khi nào phải có kết quả trước khi merge hoặc release?**

### Hai kiểu thất bại của chiến lược

| Chiến lược | Hậu quả |
| --- | --- |
| Chạy mọi thứ ở mọi PR | Feedback chậm, chi phí cao, developer dễ bỏ qua hoặc tìm cách skip tests |
| Chỉ chạy unit tests và mock | Không phát hiện được nhiều lỗi contract, serialization, binding và tích hợp |
| Chạy E2E cho mọi thay đổi | Flaky, khó xác định nguyên nhân, môi trường nặng |
| Chỉ chạy Stub Runner | Không chứng minh producer thật phát response/message đúng |
| Chỉ chạy producer contract tests | Không chứng minh consumer xử lý stub mới đúng |
| Chạy test nhưng không đọc report | Build xanh có thể che 0 tests hoặc tests bị skip |

Mục tiêu là **đặt đúng test ở đúng gate**, không phải tối đa hóa số lượng test.

## 2. Bằng chứng của từng lớp kiểm thử

~~~mermaid
flowchart TD
    A["Unit tests"] --> B["Producer contract verification"]
    B --> C["Consumer Stub Runner tests"]
    C --> D["Component / broker integration"]
    D --> E["End-to-end / deployment verification"]
    A -.-> X["Nhanh, cô lập"]
    B -.-> Y["Producer có đáp ứng contract?"]
    C -.-> Z["Consumer có xử lý stub contract?"]
    D -.-> U["Adapter/broker/transaction có hoạt động?"]
    E -.-> V["Các thành phần deployed có phối hợp?"]
~~~

Sơ đồ mô tả một **danh mục test theo phạm vi**, không phải mọi dự án phải xếp thành một kim tự tháp cứng. Một số consumer contract tests có thể nhanh hơn nhiều integration tests; một số contract tests producer thực chất khởi tạo Spring context và nằm ở vùng component test.

| Lớp | Câu hỏi chính | Tốc độ tương đối | Mức tin cậy / giới hạn |
| --- | --- | --- | --- |
| Unit test | Logic domain/helper có đúng? | Rất nhanh | Không chứng minh HTTP/message wiring |
| Producer contract test | Producer thật có đáp ứng contract? | Nhanh đến trung bình | Phụ thuộc base test, adapter và test mode |
| Consumer Stub Runner test | Consumer xử lý hành vi producer được stub mô tả? | Nhanh đến trung bình | Không chứng minh broker production semantics |
| Component/integration test | Adapter, serializer, DB, broker phối hợp đúng? | Trung bình đến chậm | Chỉ tin cậy trong cấu hình/tài nguyên được test |
| End-to-end test | Luồng deployed giữa nhiều services có hoạt động? | Chậm, nhiều phụ thuộc | Bao phủ ít scenarios, khó khoanh vùng lỗi |

Không lớp nào thay thế hoàn toàn lớp khác. Chẳng hạn, producer generated test PASS không chứng minh Billing consumer parse được payload; Stub Runner consumer test PASS không chứng minh Kafka production ACL, partition assignment hoặc retry policy.

## 3. Phân biệt producer verification và consumer verification

Spring Cloud Contract tạo hai loại bằng chứng quan trọng.

### Producer side

Contract mô tả request/response hoặc message output. Contract Verifier sinh test để kích hoạt producer và kiểm tra behavior thực.

Với message contract, `input.triggeredBy` gọi phương thức trong base test để kích hoạt logic producer; verifier quan sát message phát ra rồi so destination, headers và body.

### Consumer side

Consumer test tải stub artifact của producer bằng Stub Runner. Với HTTP, consumer gọi stub endpoint. Với message, `StubTrigger` có thể kích hoạt message stub theo label, rồi consumer binding/handler xử lý.

~~~mermaid
flowchart LR
    A["Contract source"] --> B["Producer generated test"]
    B --> C["Producer implementation"]
    C --> D["Actual response/message"]
    D --> E["Producer assertions"]
    A --> F["Stub artifact"]
    F --> G["Consumer Stub Runner"]
    G --> H["Consumer code"]
    H --> I["Consumer business assertions"]
~~~

**Producer test** trả lời: “Producer này có thực hiện contract không?”

**Consumer stub test** trả lời: “Consumer này có xử lý hành vi contract được mô phỏng không?”

Cần cả hai nếu muốn kiểm soát tương thích giữa hai phía. Một test suite không tự chứng minh phía còn lại.

## 4. Mức tin cậy không đồng nghĩa với độ giống production

Một test có thể khởi tạo nhiều framework nhưng vẫn bỏ sót hành vi quan trọng. Ví dụ:

- Spring context dùng test binder không kiểm tra Kafka serialization thực.
- WireMock stub test không kiểm tra TLS giữa services.
- Test database in-memory không chứng minh transaction isolation của database production.
- E2E test đi qua API gateway nhưng chỉ kiểm tra status 200, không kiểm tra payload nghiệp vụ.
- Unit test mock publisher có thể PASS dù publisher binding sai destination.

Do đó, đánh giá test bằng **behavior được quan sát và failure mode được bao phủ**, không chỉ bằng số lượng dependencies được khởi động.

| Test setup | Có thể kiểm tra tốt | Không nên suy diễn |
| --- | --- | --- |
| Unit + mock publisher | Domain decision có phát lệnh publish | Broker nhận message |
| Producer verifier + test binder | Producer kích hoạt output theo contract trong adapter test | Production broker ACL/partition/retry |
| Consumer + StubTrigger/test binder | Consumer handler xử lý message stub | Broker production delivery guarantee |
| Consumer + WireMock | HTTP client và business code xử lý response | Producer implementation thực |
| Broker container integration | Serializer, broker protocol, binding và consumer thực | Toàn bộ deployed network/security nếu không test |
| E2E deployed environment | Một luồng phối hợp thật trong môi trường đã dựng | Mọi dữ liệu/edge cases và mọi consumers |

**Test fidelity** là mức môi trường giống hệ thống thật. **Test confidence** là mức bằng chứng test cung cấp cho câu hỏi cụ thể. Fidelity cao không tự động đồng nghĩa confidence cao nếu assertions yếu.

## 5. Chọn test theo rủi ro thay đổi

Không phải mọi thay đổi đều cần cùng một bộ tests.

| Thay đổi | Rủi ro chính | Tests ưu tiên |
| --- | --- | --- |
| Sửa thuật toán tính phí nội bộ | Business calculation | Unit + producer/consumer tests liên quan outcome |
| Đổi response field/type | Schema compatibility | Producer contract + consumer matrix |
| Đổi HTTP path/header | Routing/content negotiation | Producer contract + consumer Stub Runner |
| Đổi message destination | Binding/routing | Producer message contract + consumer binding + broker integration |
| Đổi serializer/Jackson config | Wire representation | Producer contract + consumer tests + serialization integration |
| Đổi retry/acknowledgement | Delivery semantics | Unit/policy tests + broker integration |
| Đổi transaction/outbox | Atomicity/duplicate events | Integration với DB/broker phù hợp |
| Đổi TLS/ACL/credentials | Security/connectivity | Environment integration/security tests |
| Refactor không đổi behavior | Regression logic | Unit + contract suite có phạm vi liên quan |
| Nâng SCC/Boot/WireMock | Tool compatibility | Build/generation + producer verification + Stub Runner compatibility |

### Một quyết định theo rủi ro

Hãy xem xét:

- **Impact:** nếu hỏng, bao nhiêu consumers hoặc giao dịch bị ảnh hưởng?
- **Likelihood:** thay đổi có chạm serialization, routing hoặc shared code không?
- **Detectability:** lỗi có dễ thấy ở test rẻ không?
- **Recovery cost:** rollback hoặc migrate dữ liệu/event có khó không?
- **Blast radius:** một service hay nhiều domains/consumers bị tác động?

Thay đổi nhỏ ở một shared event schema có thể có rủi ro lớn hơn thay đổi nhiều dòng trong một helper nội bộ.

## 6. Chia pipeline thành PR, nightly và release gates

Một cách phân tầng thường hữu ích:

<box>
  <title>PR gate</title>
  <text color="secondary" size="sm">Feedback nhanh cho mọi thay đổi</text>
  - Compile/static checks và unit tests.
  - Producer contract tests của module bị ảnh hưởng.
  - Consumer Stub Runner tests của consumers liên quan.
  - Kiểm tra số generated tests và test reports.
  <divider color="subtle"/>
  <title>Nightly / scheduled gate</title>
  <text color="secondary" size="sm">Bao phủ rộng hơn và phát hiện tương tác</text>
  - Consumer compatibility matrix rộng hơn.
  - Broker/database integration với môi trường cô lập.
  - Retry, duplicate, ordering và error scenarios.
  - Các test E2E chọn lọc và kiểm tra flakiness.
  <divider color="subtle"/>
  <title>Pre-release gate</title>
  <text color="secondary" size="sm">Bằng chứng cho artifact sắp phát hành</text>
  - Producer verification trên commit/revision cuối.
  - Stub artifact immutable và provenance.
  - Required consumers chạy với đúng stub.
  - Migration/deprecation gates và deployment smoke tests.
</box>

Đây là **đề xuất baseline**, cần điều chỉnh theo criticality và thời gian feedback của tổ chức. Nếu một thay đổi ảnh hưởng trực tiếp đến thanh toán, quyền truy cập hoặc dữ liệu không thể phục hồi, một số integration/security tests phải chạy trước merge thay vì đợi nightly.

### Không đẩy hết test đắt sang nightly

Nếu thay đổi contract có thể làm một consumer chính không deserialize được, consumer compatibility test tương ứng phải chạy **trước khi merge**. Nightly chỉ mở rộng phạm vi sang các combinations ít thường xuyên hoặc tốn tài nguyên hơn.

## 7. PR gate tối thiểu cho producer

Với một producer Spring Cloud Contract:

1. Compile application và test code.
2. Chạy unit tests cho business logic/serialization helpers.
3. Discover contracts và sinh generated tests.
4. Chạy tất cả producer contract scenarios bị ảnh hưởng.
5. Kiểm tra generated tests thực sự được thực thi, không bị skip.
6. Package stub artifact nếu pipeline cần consumer validation ngay.
7. Lưu contract revision và producer commit.

Một lệnh Maven thường gặp:

~~~bash
./mvnw clean verify
~~~

Nhưng lệnh chỉ có ý nghĩa khi plugin goals đã được bind/configured và test reports chứng minh generated tests chạy. **Không dựa vào exit code 0 đơn độc**.

### Chọn phạm vi tests

Nếu thay đổi chỉ ở một domain contract và build hỗ trợ chạy test selection đáng tin, có thể chạy suite bị ảnh hưởng trên PR để tăng tốc. Tuy nhiên:

- Contract shared/base class thay đổi có thể ảnh hưởng nhiều scenarios.
- Plugin/DSL config thay đổi cần chạy toàn bộ generated tests liên quan.
- CI phải biết chính xác tests nào bị bỏ qua và lý do.
- Nightly hoặc pre-release vẫn cần full required suite.

Không dùng test filtering để che một test FAIL.

## 8. PR gate tối thiểu cho consumer

Consumer cần test với stub của **producer version/revision mà PR đang nhắm tới**.

Ví dụ HTTP consumer test:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-service:2.5.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientContractTest {

    @Autowired
    private OrderClient orderClient;

    @Test
    void readsPaidOrder() {
        OrderView order = orderClient.getOrder("ORD-1001");

        assertThat(order.status()).isEqualTo("PAID");
        assertThat(order.id()).isEqualTo("ORD-1001");
    }
}
~~~

Ví dụ giả định artifact `2.5.0` đã được cài trong local repository và client được cấu hình gọi stub port tương ứng. Trong CI, dùng artifact/repository và port được quản lý theo pipeline.

Consumer gate cần kiểm tra:

- Stub Runner resolve đúng GAV/classifier/version.
- HTTP request thực sự match mapping.
- Response body deserialize được.
- Consumer business logic cho kết quả đúng.
- Các trường/headers quan trọng được xử lý.
- Test không chỉ assert Stub Runner đã khởi động.

Với message consumer, dùng `StubTrigger` để kích hoạt message stub theo label rồi xác minh handler và trạng thái nghiệp vụ.

## 9. Những gì nên chạy nightly?

Nightly phù hợp cho các tổ hợp tốn thời gian hoặc có phạm vi rộng:

- Consumer matrix với nhiều producer versions còn hỗ trợ.
- Consumer cũ với producer stub mới, khi schema evolution đang diễn ra.
- Broker integration với Kafka/RabbitMQ hoặc broker thực tế của hệ thống.
- Retry, redelivery, duplicate, ordering và dead-letter scenarios.
- Database transaction/outbox consistency.
- Test với nhiều partitions/consumer groups nếu đó là yêu cầu.
- E2E flows xuyên qua gateway và nhiều services.
- Kiểm tra runtime compatibility sau khi nâng JDK/framework.
- Quét flakiness và thống kê test duration.

Nightly phải tạo **artifact và report có thể truy vết**. Nếu producer build nightly khác commit hoặc stub bytes khác PR, không dùng kết quả đó thay cho bằng chứng của artifact sắp release.

## 10. Pre-release gate: xác minh đúng artifact sẽ phát hành

Trước release, cần kiểm tra đúng producer commit và contract revision cuối cùng:

~~~mermaid
flowchart TD
    A["Release candidate commit"] --> B["Producer contract verification"]
    B --> C{"All required scenarios PASS?"}
    C -->|No| X["BLOCK release"]
    C -->|Yes| D["Package immutable stub JAR"]
    D --> E["Record GAV + SHA-256 + contract revision"]
    E --> F["Run required consumer tests"]
    F --> G{"Consumer matrix PASS?"}
    G -->|No| X
    G -->|Yes| H["Deployment smoke / release checks"]
    H --> I["Release decision"]
~~~

**Artifact identity quan trọng hơn coordinate nhìn thấy.** Nếu dùng SNAPSHOT hoặc repository có thể overwrite, cùng GAV có thể trả bytes khác. Hãy dùng release artifact immutable hoặc ghi checksum và xác minh consumer đã tải đúng bytes.

Pre-release gate nên kiểm tra:

- Producer generated tests PASS.
- Không có required test bị skip.
- Stub artifact chứa mappings/resources đúng.
- Consumer required versions PASS với stub mới.
- Các compatibility/deprecation decisions được phê duyệt.
- Test reports gắn với source commit và artifact checksum.

## 11. Test pyramid không phải công thức cố định

Một cách hình dung phổ biến là nhiều unit tests, ít integration tests, rất ít E2E tests. Với Spring Cloud Contract, nên hiểu theo **chi phí và phạm vi**, không theo số lượng cứng.

~~~mermaid
flowchart TD
    E["E2E / deployed workflows"] --> I["Broker / DB / HTTP integration"]
    I --> C["Producer + consumer contract tests"]
    C --> U["Unit tests"]
    style U fill:#d9f2e6,stroke:#3d8b67,color:#173d2d
    style C fill:#e5efff,stroke:#5077b5,color:#1e3558
    style I fill:#fff0d9,stroke:#b88736,color:#503b18
    style E fill:#f5e5f2,stroke:#a66a9a,color:#4b2944
~~~

- Unit tests thường rẻ và nhiều.
- Producer contract tests có thể khởi động Spring context nên không phải lúc nào cũng rất rẻ.
- Consumer Stub Runner tests thường nhanh hơn broker integration nhưng vẫn có thể cần application context.
- Broker integration tests đắt hơn nhưng cần thiết cho delivery semantics.
- E2E tests ít nhưng bảo vệ một số luồng business critical.

**Đừng đặt mục tiêu “E2E dưới 5%” như luật chung.** Số lượng hợp lý phụ thuộc domain, hệ thống và khả năng cô lập.

## 12. Một contract test không thay thế unit test business logic

Ví dụ service tính phí:

~~~java
public BigDecimal calculateShippingFee(
        BigDecimal orderAmount,
        String region) {
    // Business rules
}
~~~

Unit tests phù hợp để kiểm tra:

- Các boundary amounts.
- Quy tắc region.
- Miễn phí vận chuyển.
- Rounding và currency.
- Invalid inputs.

Producer contract test phù hợp để kiểm tra:

- HTTP response chứa đúng fee field/type.
- Status/header/body đáp ứng contract.
- Producer endpoint gọi logic và serialize kết quả đúng.

Nếu chỉ có contract test với một fixture `amount=125000`, nhiều nhánh tính phí có thể không được kiểm tra. Nếu chỉ có unit test, response DTO có thể bị rename mà unit tests không phát hiện.

Hai loại test **bổ sung nhau**.

## 13. Consumer Stub Runner test không thay thế broker integration

Stub Runner là công cụ hữu ích để kiểm tra consumer với một hành vi producer đã đóng gói. Nhưng nó không chứng minh mọi semantics của broker.

| Điều cần bảo vệ | Stub Runner/test binder | Broker integration |
| --- | --- | --- |
| Consumer parse message schema | Có thể kiểm tra | Có thể kiểm tra |
| Handler business logic | Có | Có |
| Destination/label theo contract | Có, trong phạm vi adapter | Có |
| Kafka partition assignment | Không | Có |
| Broker ACL/authentication | Không nếu test không kết nối broker | Có |
| Consumer group rebalancing | Không | Có |
| Retry/DLQ thực tế | Chỉ nếu mô phỏng rõ; không chứng minh broker policy | Có |
| Transactional publish/outbox atomicity | Không đủ | Cần DB/broker integration phù hợp |
| Network/TLS giữa services | Không | Cần environment test tương ứng |

Nếu hệ thống phụ thuộc vào ordering hoặc redelivery, hãy có broker integration test dành riêng cho những behavior đó. Không bắt mọi PR phải khởi động broker nếu thay đổi không ảnh hưởng; nhưng cũng không được bỏ qua integration suite khi thay đổi adapter/retry/partition.

## 14. Chọn mức test theo loại thay đổi

### Contract file thay đổi

Chạy:

- Producer generated tests của contract.
- Các producer scenarios liên quan.
- Consumers sử dụng contract đó.
- Compatibility matrix nếu thay đổi field/type/requiredness.
- Stub packaging/provenance nếu artifact được publish.

### DTO hoặc serializer thay đổi

Chạy:

- Unit tests cho mapping/serialization.
- Producer contract tests.
- Consumer tests với stub.
- Nếu serializer/framework config thay đổi rộng, chạy component integration.

### Binding/destination thay đổi

Chạy:

- Producer message verification.
- Consumer StubTrigger/binding tests.
- Broker integration cho destination/routing thực tế.
- Các consumers liên quan.

### Retry/acknowledgement/transaction thay đổi

Chạy:

- Unit tests cho retry policy/idempotency.
- Consumer handler tests.
- Broker/DB integration với redelivery và failure injection.
- E2E có chọn lọc nếu transaction liên service thay đổi.

### Build plugin/toolchain thay đổi

Chạy:

- Plugin resolution và dependency graph checks.
- Contract discovery/generation.
- Compile generated sources.
- Producer tests.
- Stub packaging và consumer Stub Runner tests.
- Không chỉ chạy application unit tests.

## 15. Consumer compatibility matrix: test những consumer nào?

Không phải tất cả consumers đều có cùng mức ưu tiên.

Một inventory ví dụ:

| Consumer | Mức quan trọng | Tần suất deploy | Chiến lược |
| --- | --- | --- | --- |
| Checkout | Critical | Hàng ngày | PR gate bắt buộc |
| Billing | Critical | Hàng tuần | PR gate với stub mới |
| Analytics | Medium | Hàng tháng | Nightly + trước release |
| Legacy Export | Low nhưng còn hỗ trợ | Không thường xuyên | Compatibility suite theo lịch/deprecation |

Đây là dữ liệu ví dụ. Tổ chức cần xác định **consumer nào còn được hỗ trợ** và mức impact thực tế.

### Cách giảm số combinations

- Chạy mọi critical consumers trên PR khi contract breaking-risk thay đổi.
- Chạy toàn bộ supported consumers nightly hoặc pre-release.
- Chạy các phiên bản cũ có khả năng deserialize strict trong migration.
- Không chạy lại những combinations không liên quan nếu có impact analysis đáng tin.
- Giữ một lịch kiểm tra định kỳ cho consumers ít deploy nhưng vẫn được hỗ trợ.

**Consumer không deploy thường xuyên không có nghĩa là không còn rủi ro**; ngược lại, consumer cũ có thể là nơi dễ bị breaking change nhất.

## 16. Impact analysis để chỉ chạy tests liên quan

Có thể xây dependency map:

~~~text
order-service contract
  ├── checkout-service
  ├── billing-service
  ├── shipping-service
  └── analytics-service
~~~

Khi thay contract Order:

- Checkout và Billing có thể cần chạy ngay vì critical.
- Shipping cần chạy nếu thay message schema liên quan.
- Analytics có thể chạy nightly nếu không nằm trong release path, nhưng không được quên trước khi release nếu vẫn được hỗ trợ.

Impact analysis cần dựa vào **consumer inventory/contract ownership**, không chỉ tìm tên artifact trong source code. Một consumer có thể lấy stub qua dependency version catalog hoặc repository configuration.

Nếu không chắc impact map đầy đủ, chạy rộng hơn thay vì bỏ sót consumer.

## 17. Deterministic tests: nền tảng của pipeline nhanh

Test nhanh nhưng không ổn định sẽ làm giảm niềm tin. Một suite thường flaky do:

- Dữ liệu dùng chung.
- Thời gian hiện tại/timezone.
- Random IDs không được cố định.
- Async message chưa đến khi assertion chạy.
- Port hoặc resource conflict khi chạy song song.
- Test order phụ thuộc state từ test trước.
- External API/network.
- Retry hoặc scheduler tiếp tục chạy sau test.

### Quy tắc làm test deterministic

- Fixture synthetic và có ID riêng.
- Clock được inject hoặc cố định khi test thời gian.
- Test DB/broker namespace riêng.
- Không dùng shared mutable static state.
- Async assertion có timeout hữu hạn và điều kiện rõ.
- Cleanup chỉ xóa tài nguyên test sở hữu.
- External dependencies được stub hoặc chạy trong test environment cô lập.
- Không phụ thuộc thứ tự tests.

### Ví dụ với Clock

~~~java
@Service
public class InvoiceService {
    private final Clock clock;

    public InvoiceService(Clock clock) {
        this.clock = clock;
    }

    public Instant createdAt() {
        return Instant.now(clock);
    }
}
~~~

Trong test, inject `Clock.fixed(...)` để thời gian xác định. Nhờ đó response timestamp không thay đổi mỗi lần chạy, producer contract tests dễ tái lập hơn.

## 18. Async message tests: chờ điều kiện, không ngủ cố định

Anti-pattern:

~~~java
stubTrigger.trigger("order_paid");
Thread.sleep(3000);
assertThat(repository.findByOrderId("ORD-1001")).isPresent();
~~~

Test có thể chậm ba giây khi message xử lý nhanh, nhưng vẫn flaky nếu CI chậm hơn ba giây.

Dùng polling với deadline:

~~~java
stubTrigger.trigger("order_paid");

await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertThat(repository.findByOrderId("ORD-1001"))
            .isPresent()
    );
~~~

Cần:

- Timeout phản ánh SLA của test environment.
- Polling condition quan sát được.
- Khi timeout, log đủ thông tin để chẩn đoán.
- Không tăng timeout vô hạn để che deadlock.
- Dọn message/records giữa các tests.

Awaitility là một lựa chọn; có thể dùng API đồng bộ hoặc latch nếu phù hợp adapter. Điều quan trọng là chờ **điều kiện cụ thể**, không chờ một khoảng thời gian tùy tiện.

## 19. Parallelism và isolation

Chạy tests song song có thể giảm wall-clock time, nhưng chỉ an toàn khi test resources độc lập.

| Tài nguyên | Nguy cơ khi chạy song song | Cách cô lập |
| --- | --- | --- |
| HTTP stub ports | Port collision | Port động hoặc Stub Runner quản lý riêng |
| Database rows | Xóa/ghi đè fixture của test khác | Schema/namespace/test ID riêng |
| Message destination | Test nhận event của nhau | Destination/group riêng hoặc correlation ID |
| Static HTTP client config | Global state bị ghi đè | Instance-scoped config hoặc tắt parallel cho nhóm đó |
| Shared filesystem | File cùng tên bị ghi đè | Temp directory riêng |
| Testcontainers | Startup contention | Reuse có kiểm soát, lifecycle rõ |
| Scheduler/background job | Job chạy sau test | Disable/scope scheduler trong test |

Không bật parallel execution chỉ vì CI agent có nhiều CPU. Trước tiên xác nhận test suite **không chia sẻ mutable state**.

### Chạy theo nhóm

Có thể phân nhóm:

- Unit tests: parallel mạnh nếu stateless.
- Producer contract tests: parallel nếu Spring context và HTTP/message fixtures an toàn.
- Stub Runner tests: parallel khi ports, artifact caches và binder resources cô lập.
- Broker integration: giới hạn concurrency theo tài nguyên broker/container.

Đo wall-clock time và failure rate sau khi bật parallelism.

## 20. Cache và reuse môi trường: nhanh nhưng phải an toàn

Có thể tối ưu:

- Maven/Gradle dependency cache.
- Build cache cho tasks deterministic.
- Reuse container image layers.
- Reuse Spring test context khi cấu hình giống nhau.
- Tải stub artifact một lần cho job.
- Chạy impact-based tests song song.

Nhưng cache có thể làm test sai nếu key không chứa đầy đủ inputs.

**Cache key nên phản ánh:**

- Build files/lockfiles.
- JDK/toolchain version.
- Contract revision.
- Producer artifact version/checksum.
- Plugin/dependency versions.
- Test configuration có ảnh hưởng generated sources/mappings.

### Rủi ro stub cache

Nếu consumer dùng cùng GAV nhưng repository overwrite artifact, cache có thể trả stub bytes cũ. Dùng immutable release artifacts hoặc ghi checksum. Đừng giả định `2.5.0-SNAPSHOT` hôm nay giống hôm qua.

### Reuse Spring context

Spring Test context cache có thể tiết kiệm thời gian, nhưng các tests không được sửa global beans/config shared theo cách gây nhiễm state. Nếu test thay property, mock beans hoặc static HTTP config, cần xem lifecycle và context cache behavior.

## 21. Negative tests: chứng minh assertions có khả năng bắt lỗi

Một test chỉ PASS trên response đúng không chứng minh matcher đủ mạnh.

Ví dụ contract yêu cầu `status = PAID`. Cần biết test có FAIL nếu producer trả `PENDING` không.

Negative tests có thể kiểm tra:

- Thiếu required field.
- Wrong JSON type.
- Field rename không được phép.
- Status sai.
- Destination sai.
- Header content type sai.
- Event ID bị duplicate.
- Consumer nhận event type không hỗ trợ.
- Consumer parse null/missing field sai.

### Ví dụ test helper cho payload type

~~~java
@Test
void rejectsStringAmountWhenNumberIsRequired() {
    String payload =
        "{\"orderId\":\"ORD-1001\",\"amount\":\"125000\"}";

    assertThatThrownBy(() ->
        objectMapper.readValue(payload, OrderPaidEvent.class)
    ).isInstanceOf(Exception.class);
}
~~~

Đây là ví dụ minh họa; exception chính xác phụ thuộc DTO/Jackson configuration. Nếu ứng dụng cho phép coercion, test phải xác minh semantics được chọn thay vì giả định parser luôn từ chối.

**Không cần nhân đôi mọi contract scenario thành negative test.** Chọn các bất biến quan trọng và các failure modes có nguy cơ bị matcher bỏ sót.

## 22. Mutation testing và contract quality

Một cách đánh giá chất lượng test là cố ý tạo thay đổi sai (mutation) rồi xem test có phát hiện không.

Ví dụ mutation:

- Đổi response `status` từ `PAID` sang `PENDING`.
- Đổi `amount` number thành string.
- Bỏ header `Content-Type`.
- Đổi destination `orders.events` thành `order.events`.
- Bỏ publish message trong producer.
- Consumer bỏ qua `eventId` và tạo duplicate shipment.

Nếu tất cả tests vẫn PASS, có thể:

- Test không chạy.
- Matcher quá lỏng.
- Test fixture mock mất behavior cần xác minh.
- Consumer assertions chỉ kiểm tra trigger result.
- Mutation không nằm trong path test.

Mutation testing chuyên dụng có thể tốn thời gian. Bắt đầu với một vài **controlled negative cases** ở các contract critical; mở rộng khi có giá trị.

## 23. Flaky tests và retry: không che lỗi bằng rerun

Retry một test flaky có thể giúp phân biệt transient infrastructure failure, nhưng nếu retry vô điều kiện cho mọi test thì có thể che race condition hoặc bug thật.

Một chính sách hợp lý:

- Lưu kết quả **lần chạy đầu**.
- Nếu retry, đánh dấu test là flaky/quarantined theo chính sách rõ.
- Theo dõi số lần retry và tỷ lệ flaky.
- Có owner và thời hạn xử lý.
- Không coi “PASS ở lần retry” giống “PASS ổn định”.
- Với release-critical contracts, flaky test cần được điều tra trước khi release.

### Phân loại failure

| Loại | Ví dụ | Hành động |
| --- | --- | --- |
| Product regression | Contract assertion fail ổn định | Block và sửa |
| Toolchain regression | Generated test compile fail sau upgrade | Block, kiểm tra compatibility |
| Test flakiness | Race condition chỉ xảy ra một số lần | Ghi nhận, cô lập và sửa |
| Infrastructure outage | Maven repository/broker không truy cập | Retry có kiểm soát, không gán product PASS |
| Test misconfiguration | 0 tests, sai profile | Block verification |

**Infrastructure failure không phải product PASS**. Pipeline nên phân biệt trạng thái để release decision không nhập nhằng.

## 24. Quản lý test data và cleanup

Contract tests nên dùng dữ liệu tổng hợp:

~~~json
{
  "orderId": "ORD-CONTRACT-1001",
  "customerId": "CUS-CONTRACT-1001",
  "amount": 125000,
  "currency": "VND"
}
~~~

Quy tắc:

- Không copy dữ liệu production vào test fixtures.
- Dùng IDs có namespace để tránh va chạm.
- Dọn đúng rows/events do test tạo.
- Không xóa toàn bộ topic/table dùng chung khi chạy song song.
- Kiểm tra cleanup không che failure trước đó.
- Với event replay, dùng event IDs riêng.
- Không log secrets/PII trong failure reports.

### Transaction rollback không phải cleanup phổ quát

`@Transactional` trong test không tự rollback:

- HTTP request chạy qua server thread/transaction khác.
- Message đã publish.
- External service call.
- File ghi ra shared filesystem.
- Async job chạy sau test.

Chọn cleanup strategy theo từng tài nguyên và xác minh bằng integration tests.

## 25. Đo tốc độ và độ tin cậy của pipeline

Không chỉ đo tổng thời gian build. Một số chỉ số hữu ích:

| Chỉ số | Câu hỏi |
| --- | --- |
| PR feedback time | Developer nhận kết quả sau bao lâu? |
| Test duration p50/p95 | Nhóm test nào chậm hoặc biến động? |
| Failure rate theo suite | Suite nào phát hiện nhiều lỗi? |
| Flaky rate | Bao nhiêu tests fail rồi pass khi rerun? |
| Generated tests executed | Có bao nhiêu producer scenarios thực sự chạy? |
| Consumer matrix coverage | Bao nhiêu consumer versions bắt buộc đã được test? |
| Stub provenance coverage | Bao nhiêu consumer jobs dùng đúng artifact/checksum? |
| Escaped contract defects | Lỗi contract nào lọt qua CI đến môi trường sau? |
| Mean time to diagnose | Mất bao lâu xác định đúng lớp lỗi? |

### Không tối ưu chỉ theo số test

Một suite có 500 tests nhưng tất cả dùng cùng một fixture/matcher yếu có thể kém tin cậy hơn 80 tests bao phủ các failure modes quan trọng.

Đo cả **coverage of contracts/consumers** và **khả năng phát hiện lỗi**. Số lượng test là một tín hiệu, không phải mục tiêu.

## 26. Tính chi phí của một gate

Một gate có thể xem xét:

- Runtime trung bình và p95.
- CPU/memory/container usage.
- Chi phí broker/database test.
- Tỷ lệ rerun.
- Tỷ lệ tests liên quan bị bỏ qua.
- Chi phí chờ artifact/repository.
- Thời gian triage khi fail.

Nếu một broker integration suite mất 20 phút, có thể không chạy trên mọi PR không liên quan. Nhưng nếu thay đổi destination/retry/ack semantics, suite đó có thể phải chạy ngay.

### Phân bổ theo thay đổi

| Thay đổi | PR | Nightly | Release |
| --- | --- | --- | --- |
| Domain calculation | Unit + relevant contract | Full regression | Critical flow |
| Response schema | Producer + affected consumers | Full consumer matrix | Required consumers |
| Message schema | Producer message + consumers | Broker integration + matrix | Producer + required consumers |
| Broker configuration | Relevant integration | Full broker suite | Deployment smoke |
| Toolchain/plugin | Generate + compile + producer + consumer | Full suite | Immutable artifact check |
| Retry/ordering | Unit + broker tests liên quan | Failure injection | Release-critical integration |

Đây là ma trận khởi đầu. Criticality có thể buộc một suite chạy sớm hơn.

## 27. Ví dụ pipeline thực tế theo stage

~~~mermaid
flowchart TD
    A["Pull request"] --> B["Compile + static checks"]
    B --> C["Unit tests"]
    C --> D["Producer Contract Verifier"]
    D --> E["Build immutable stub artifact"]
    E --> F["Affected consumer Stub Runner tests"]
    F --> G{"PR gates PASS?"}
    G -->|No| X["Block merge"]
    G -->|Yes| H["Merge / publish candidate"]
    H --> I["Nightly: full consumer matrix"]
    I --> J["Broker + DB integration"]
    J --> K["E2E critical flows"]
    K --> L["Pre-release artifact provenance + required consumers"]
    L --> M["Release decision"]
~~~

### Mẫu stage declaration trung lập

~~~yaml
# Pseudocode CI, không phải syntax của một CI provider cụ thể.
stages:
  pull_request:
    - compile
    - unit_tests
    - producer_contract_tests
    - package_stub
    - affected_consumer_stub_tests

  nightly:
    - full_consumer_matrix
    - broker_integration
    - database_integration
    - critical_e2e
    - flakiness_report

  pre_release:
    - producer_verification_on_release_commit
    - immutable_stub_checksum
    - required_consumer_matrix
    - deployment_smoke
~~~

CI provider cụ thể cần chuyển các stage này thành workflow/jobs/dependencies tương ứng. Không copy pseudocode YAML vào GitHub Actions/Jenkins rồi kỳ vọng chạy được.

## 28. Ví dụ lựa chọn test cho thay đổi message schema

Giả sử Order Service đổi event:

~~~json
{
  "eventId": "EVT-1001",
  "eventType": "ORDER_PAID",
  "orderId": "ORD-1001",
  "amount": 125000
}
~~~

thành:

~~~json
{
  "eventId": "EVT-1001",
  "eventType": "ORDER_PAID",
  "orderId": "ORD-1001",
  "amountMinor": 125000,
  "currency": "VND"
}
~~~

Đây là thay đổi field/type/semantics. Chiến lược:

**PR gate:**

- Producer message contract tests cho schema mới và legacy behavior nếu còn hỗ trợ.
- Consumer Stub Runner tests cho Shipping/Billing.
- Unit tests cho amount/currency mapping.
- Kiểm tra strict deserializer ở các consumers.

**Nightly:**

- Full consumer versions matrix.
- Broker integration với serializer thực.
- Duplicate/replay tests.
- Retry/DLQ nếu event được phát qua broker.

**Pre-release:**

- Producer commit/contract revision đã verify.
- Stub artifact immutable.
- Consumers bắt buộc đã chạy với đúng stub.
- Telemetry/deprecation approval nếu xóa field cũ.

Không cần chạy E2E toàn bộ hệ thống cho mỗi sửa đổi tài liệu không ảnh hưởng behavior, nhưng schema change này không nên chỉ dựa vào unit tests.

## 29. Example: kiểm tra đúng behavior thay vì chỉ kiểm tra trigger

Một consumer message test yếu:

~~~java
@Test
void canTriggerOrderPaidStub() {
    assertThat(stubTrigger.trigger("order_paid")).isTrue();
}
~~~

Test mạnh hơn:

~~~java
@Test
void createsShipmentFromOrderPaidEvent() {
    assertThat(stubTrigger.trigger("order_paid")).isTrue();

    await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
            assertThat(shipmentRepository.findByOrderId("ORD-1001"))
                .isPresent()
        );

    Shipment shipment =
        shipmentRepository.findByOrderId("ORD-1001").orElseThrow();

    assertThat(shipment.getEventId())
        .isEqualTo("EVT-ORD-1001-PAID");
    assertThat(shipment.getStatus())
        .isEqualTo("READY_FOR_PICKUP");
}
~~~

Test thứ hai xác minh **business outcome**. Nhưng nó vẫn chưa chứng minh broker production partition/retry semantics. Đó là câu hỏi của integration tests khác.

## 30. Khi nào cần E2E test?

Dùng E2E cho các luồng mà nhiều components phối hợp tạo ra giá trị business critical, ví dụ:

- Customer đặt hàng → payment thành công → event phát → shipping tạo shipment.
- Gateway authorization → producer API → downstream service.
- Event schema mới được publish và các consumers deployed cùng xử lý.

Giữ E2E suite nhỏ, deterministic và có dữ liệu test rõ. Khi fail, phải có logs/correlation IDs để khoanh vùng. Không biến mọi business edge case thành E2E; những trường hợp đó thường dễ kiểm tra ở unit, contract hoặc component layer.

### E2E không thay contract matrix

E2E thường chạy một phiên bản deployed của mỗi service. Nó không nhất thiết thử tất cả consumer versions cũ còn được hỗ trợ. Contract compatibility matrix vẫn cần để kiểm tra các tổ hợp version độc lập.

## 31. Chọn mức tin cậy theo criticality

| Domain | Ví dụ | Gate đề xuất |
| --- | --- | --- |
| Low impact | Internal report field không critical | Unit + relevant contract; nightly consumer |
| Medium impact | Search/catalog API | Producer + affected consumers trên PR; matrix nightly |
| High impact | Order/payment event | Producer + all critical consumers trên PR; broker integration/nightly; release matrix |
| Safety/security critical | Authorization, payment settlement, data deletion | Contract + unit + integration/security + release smoke theo risk policy |

Bảng chỉ là gợi ý; tổ chức cần định nghĩa criticality và regulatory/security requirements riêng. Không hạ mức kiểm thử cho một thay đổi chỉ vì thời gian pipeline đang dài.

## 32. Những anti-pattern làm pipeline nhanh giả tạo

| Anti-pattern | Vì sao nguy hiểm | Thay thế |
| --- | --- | --- |
| Skip generated tests khi chậm | Mất producer evidence | Impact selection minh bạch, nightly/full release gate |
| Chỉ assert StubTrigger trả true | Không kiểm consumer business logic | Assert state/outcome |
| Dùng stub cũ vì cache | Test không phản ánh producer candidate | Pin artifact immutable/checksum |
| Retry mọi failure đến khi PASS | Che flaky/product regression | Lưu first result, phân loại và có owner |
| E2E cho mọi PR | Chậm, khó triage | Layered tests theo risk |
| Chỉ unit tests | Không kiểm serialization/contract | Producer + consumer contract tests |
| Chỉ producer tests | Không kiểm consumer | Stub Runner consumer tests |
| Chỉ Stub Runner | Không kiểm broker semantics | Broker integration có chọn lọc |
| Shared test database/topic | Flaky và cross-test contamination | Isolation/namespace riêng |
| Assert status code duy nhất | Bỏ qua body/schema/business outcome | Assert headers, payload và outcome |
| Test count làm KPI | Có thể tăng test yếu | Đo risk coverage, flakiness và escaped defects |
| Nightly PASS thay release commit | Artifact/source khác nhau | Pre-release verify trên exact commit/artifact |

## 33. Bài tập thực hành

### Bài tập A — Chọn test cho rename response field

Producer đổi `name` thành `displayName`. Có ba consumers, một consumer strict parser.

**Yêu cầu:** test nào phải chạy trước merge? Test nào có thể chạy nightly?

**Gợi ý:** strict consumer phải được kiểm tra ngay; consumer matrix đầy đủ và các phiên bản ít deploy có thể chạy nightly nhưng phải PASS trước release.

### Bài tập B — Thay đổi domain calculation

Chỉ sửa quy tắc tính phí theo region, không đổi schema.

**Yêu cầu:** vì sao unit tests là trọng tâm? Khi nào vẫn cần producer contract test?

**Gợi ý:** unit tests bao phủ boundary/business branches; producer contract xác minh response API vẫn biểu diễn đúng kết quả.

### Bài tập C — Đổi message destination

Producer chuyển destination từ `orders.events` sang `orders.v2.events`.

**Yêu cầu:** lựa chọn test cho PR/nightly/release.

**Gợi ý:** producer message verification và consumer binding tests trên PR; broker integration kiểm routing thực; release smoke.

### Bài tập D — Retry và redelivery

Consumer thêm retry khi handler lỗi tạm thời.

**Yêu cầu:** Stub Runner test có đủ không?

**Gợi ý:** cần unit/policy tests và broker integration để kiểm redelivery/ack/retry/DLQ semantics.

### Bài tập E — Pipeline 45 phút

PR hiện chạy toàn bộ E2E 45 phút dù thay đổi chỉ ở một helper thuần.

**Yêu cầu:** thiết kế lại mà vẫn giữ release confidence.

**Gợi ý:** unit + affected contract tests trên PR, full matrix/integration/E2E nightly và pre-release; nhưng dùng impact map đáng tin.

### Bài tập F — Test flake

Consumer test đôi khi timeout khi chờ message, rerun thường PASS.

**Yêu cầu:** cần đo và kiểm tra những gì trước khi tăng timeout?

**Gợi ý:** binder lifecycle, async handler logs, resource contention, shared state, correlation/event ID, polling condition và first failure.

### Bài tập G — Stub Runner PASS nhưng producer chưa test

Consumer dùng stub artifact từ build trước, test business outcome PASS.

**Yêu cầu:** có đủ bằng chứng cho producer release mới không?

**Gợi ý:** không; producer generated tests và stub provenance phải gắn đúng commit/revision.

### Bài tập H — Producer PASS nhưng consumer chưa chạy

Producer message contract PASS, stub được publish.

**Yêu cầu:** có thể release event schema mới ngay không?

**Gợi ý:** chỉ nếu release policy cho phép; các consumers critical/supported phải được kiểm với stub mới trước release.

### Bài tập I — Parallel execution

Khi bật parallelism, hai tests xóa chung table và cùng trigger message.

**Yêu cầu:** cách cô lập?

**Gợi ý:** namespace/test IDs, database schema riêng, correlation IDs, destination/group riêng hoặc giới hạn parallelism ở nhóm shared resources.

### Bài tập J — Mutation test

Đổi contract status từ `PAID` thành `PENDING` nhưng producer suite vẫn PASS.

**Yêu cầu:** liệt kê giả thuyết.

**Gợi ý:** matcher yếu, test không chạy, response fixture bị mock, wrong contract root hoặc generated test bị skip.

### Bài tập K — Criticality

Một API nội bộ được dùng bởi payment settlement và dashboard analytics.

**Yêu cầu:** chọn gate theo consumer impact, không theo tên API.

**Gợi ý:** payment consumer critical cần PR gate; dashboard có thể nightly nếu không release-critical, nhưng vẫn cần release verification nếu được hỗ trợ.

### Bài tập L — Cache stale stub

Consumer test nhanh hơn sau khi cache, nhưng vẫn dùng stub checksum cũ.

**Yêu cầu:** tối ưu cache thế nào mà không mất provenance?

**Gợi ý:** cache theo immutable artifact identity/checksum, invalidate theo GAV/build inputs, log resolved artifact.

## 34. Checklist thiết kế chiến lược kiểm thử

### Phạm vi và rủi ro

- [ ] Xác định producer, consumers và contract/event bị ảnh hưởng.
- [ ] Phân loại impact/criticality của behavior.
- [ ] Xác định failure modes: schema, routing, serialization, business logic, broker, security.
- [ ] Có consumer inventory và ownership.
- [ ] Không dựa vào tên file hoặc số test để suy coverage.

### Producer và consumer evidence

- [ ] Producer generated tests thực sự được sinh và chạy.
- [ ] Producer base test kích hoạt application behavior thật.
- [ ] Consumer Stub Runner dùng đúng stub version.
- [ ] Consumer tests assert business outcome, không chỉ trigger/server startup.
- [ ] Producer commit, contract revision, GAV và checksum được truy vết.
- [ ] Required consumers đã được chạy theo gate phù hợp.

### Integration và E2E

- [ ] Broker integration được chạy khi thay adapter, retry, ack, partition hoặc delivery semantics.
- [ ] Database integration được chạy khi thay transaction/outbox/persistence semantics.
- [ ] Security/network tests có mặt khi thay TLS, ACL hoặc credentials.
- [ ] E2E tập trung vào flows critical và có khả năng triage.
- [ ] Giới hạn của test binder/Stub Runner được ghi rõ.

### Tốc độ và độ ổn định

- [ ] PR gate trả feedback trong thời gian mục tiêu.
- [ ] Nightly bao phủ combinations rộng hơn.
- [ ] Pre-release chạy trên exact commit/artifact.
- [ ] Fixtures deterministic, không dùng dữ liệu production.
- [ ] Async tests chờ condition có timeout hữu hạn.
- [ ] Parallel tests có resource isolation.
- [ ] Retry không che product failures.
- [ ] Cache key phản ánh dependency/toolchain/artifact inputs.
- [ ] Test reports ghi số executed/skipped/failed.
- [ ] Flakiness, p95 duration và escaped defects được theo dõi.

## Kết luận

Cân bằng tốc độ với mức tin cậy trong Spring Cloud Contract là việc **phân bổ bằng chứng theo rủi ro**. Unit tests kiểm tra logic nhỏ; producer generated tests xác minh producer thực hiện contract; consumer Stub Runner tests xác minh consumer xử lý behavior đã thỏa thuận; broker/database integration kiểm tra semantics của hạ tầng; E2E xác minh một số luồng deployed quan trọng.

PR nên chạy những kiểm tra nhanh nhưng có khả năng phát hiện regression trực tiếp từ thay đổi. Nightly mở rộng consumer matrix và tích hợp hạ tầng. Pre-release xác minh đúng producer commit, contract revision, stub artifact và các consumers bắt buộc. Để pipeline vừa nhanh vừa đáng tin, cần test deterministic, resource isolation, cache có provenance, negative tests và reports cho biết tests thực sự đã chạy.

**Ghi nhớ:** *Đừng đo độ tin cậy bằng số lượng test hoặc thời gian build. Hãy hỏi mỗi test bảo vệ behavior nào, failure mode nào còn chưa được kiểm tra, và bằng chứng có gắn đúng producer/consumer artifact sắp phát hành hay không.*
