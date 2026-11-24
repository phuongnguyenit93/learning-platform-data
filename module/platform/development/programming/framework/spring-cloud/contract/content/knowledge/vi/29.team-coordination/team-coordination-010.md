# Quy ước rà soát và tiêu chí chấp nhận thay đổi

## Mục tiêu bài học

Trong **Spring Cloud Contract**, producer và consumer có thể thỏa thuận hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**. Công cụ giúp sinh kiểm thử phía producer, tạo stub artifact để consumer dùng **Stub Runner** và tích hợp các kiểm tra vào CI. Nhưng kỹ thuật chỉ giải quyết một phần vấn đề: **ai được sửa hợp đồng, ai phải review và cần những bằng chứng gì để một thay đổi được chấp nhận?**

Bài học thuộc chương **Phối hợp nhiều nhóm**, dành cho những hệ thống có nhiều consumer, nhiều phiên bản được triển khai đồng thời và các nhóm không phát hành cùng một thời điểm.

Sau bài, bạn có thể:

- Xác định trách nhiệm của producer team, consumer team, contract owner và người phê duyệt release.
- Viết change proposal/PR mô tả hành vi trước–sau, impact analysis, migration và rollback.
- Phân loại thay đổi tương thích, có điều kiện hoặc phá tương thích với HTTP/message contracts.
- Định nghĩa **acceptance criteria có thể kiểm tra**, không chỉ câu “không ảnh hưởng consumer”.
- Yêu cầu đúng bằng chứng: generated producer tests, stub GAV/checksum, Stub Runner và consumer tests cho từng phiên bản.
- Tổ chức review, deprecation và giải quyết xung đột giữa các nhóm mà không che giấu các test đang FAIL hoặc chưa chạy.

## 1. Tại sao contract cần quy ước review?

Giả sử **Order Service** trả JSON:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

**Checkout Service** dựa vào trường `status` để cho phép giao hàng. Nhóm Order muốn đổi trường này thành `paymentStatus`:

~~~json
{
  "id": "ORD-1001",
  "paymentStatus": "PAID"
}
~~~

Với producer, đây có thể chỉ là đổi tên thuộc tính DTO. Với Checkout, việc xóa `status` có thể là **breaking change**. Nếu producer chỉ chạy unit tests của mình, Checkout vẫn có thể hỏng sau triển khai. Nếu Checkout chỉ mock một JSON tự viết mà producer chưa từng xác minh, consumer tests vẫn có thể PASS với hành vi không được producer thật cung cấp.

~~~mermaid
flowchart LR
    A["Consumer kỳ vọng<br/>status = PAID"] --> C["Contract được thỏa thuận"]
    B["Producer implementation"] --> PT["Generated producer tests"]
    C --> PT
    C --> S["Stub artifact"]
    S --> CT["Stub Runner + consumer tests"]
    PT --> E["Bằng chứng producer"]
    CT --> F["Bằng chứng consumer"]
    E --> R["Quyết định review/release"]
    F --> R
~~~

Một **hợp đồng được review** là bản mô tả hành vi quan sát được mà các bên đồng ý bảo vệ: HTTP method, path, headers, body, status, kiểu dữ liệu, semantics, message destination và event schema nếu cần. Nó **không** buộc producer tiết lộ cấu trúc database hay mọi chi tiết implementation.

Mục tiêu của quy trình review là phát hiện rủi ro **trước khi rollout**, không chỉ tìm lỗi sau khi consumer production ngừng hoạt động.

## 2. Các thuật ngữ cần thống nhất

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Producer** | Service triển khai HTTP API hoặc phát thông điệp được hợp đồng hóa |
| **Consumer** | Ứng dụng gọi API/nhận message và phụ thuộc hành vi producer |
| **Contract** | Groovy/YAML DSL mô tả hành vi có thể xác minh |
| **Contract owner** | Nhóm/vai trò quản lý quy ước, chất lượng và lịch sử contract |
| **Change proposal** | Đề xuất thay đổi có lý do, phạm vi, tác động và kế hoạch chuyển tiếp |
| **Review** | Quá trình kiểm tra semantics, tương thích, dữ liệu test và bằng chứng |
| **Approval** | Sự chấp thuận theo thẩm quyền; khác với test PASS |
| **Acceptance criteria** | Những điều kiện cụ thể, có thể quan sát/kiểm tra để chấp nhận thay đổi |
| **Producer verification** | Kết quả generated contract tests chạy với implementation producer |
| **Stub artifact** | Gói stubs được sinh từ hợp đồng, thường có classifier `stubs` |
| **Consumer verification** | Kết quả consumer tests chạy với đúng bộ stub |
| **Release gate** | Cổng ngăn merge/publish/rollout khi thiếu điều kiện bắt buộc |
| **Deprecation** | Thông báo và lộ trình ngừng hỗ trợ hành vi/giao diện cũ |

**Approval không thay thế test.** Một reviewer chọn “Approve” không chứng minh tất cả consumer versions đang chạy còn tương thích. Ngược lại, một test PASS với stub sai version không chứng minh change proposal đã được những bên liên quan chấp nhận.

## 3. Phân công trách nhiệm giữa các nhóm

Một mẫu phân quyền có thể như sau:

| Hoạt động | Producer team | Consumer team | Contract owner | Release/CI owner |
| --- | --- | --- | --- | --- |
| Đề xuất behavior mới | Đề xuất hoặc phản biện | Đề xuất nhu cầu thực | Giữ chuẩn đặc tả | Tham vấn |
| Xác định code path producer | **Chịu trách nhiệm** | Tham vấn | Review phạm vi | Không thay thế developer |
| Xác định field/event consumer cần | Tham vấn | **Chịu trách nhiệm** | Tổng hợp dependencies | Hỗ trợ inventory |
| Review DSL và compatibility | Đồng review | Đồng review | **Giữ quy ước** | Kiểm tra automation |
| Generated producer tests | **Thực hiện** | Theo dõi | Kiểm tra evidence | Vận hành CI |
| Stub generation/publishing | **Thực hiện** | Sử dụng bản đúng | Theo dõi provenance | Kiểm soát publish |
| Consumer tests với stub mới | Hỗ trợ | **Thực hiện** | Theo dõi coverage | Vận hành CI |
| Rollout/rollback decision | Đồng tham gia | Đồng tham gia | Ghi quyết định | Theo thẩm quyền phát hành |

Đây là **gợi ý quy trình**, không phải phân quyền có sẵn của Spring Cloud Contract. Tổ chức có thể dùng RACI hoặc hình thức khác, miễn là một thay đổi có **người chịu trách nhiệm cuối cùng** và có đường phản hồi của consumer.

### Không xem producer là người quyết định một chiều

- Producer xác nhận **mình có thể thực hiện hành vi nào** và chứng minh implementation.
- Consumer xác nhận **hành vi nào mình thật sự dùng**, tránh cố định hợp đồng theo chi tiết nội bộ producer.
- Contract owner giám sát naming, matcher, quy tắc review và traceability.
- Release owner xác nhận các cổng kiểm tra và quyền phát hành, không giả định một test xanh giải quyết mọi rủi ro.

Nếu producer có nhiều consumer, cần danh sách owner và phiên bản đang hoạt động. Việc chỉ hỏi một consumer quen thuộc không bảo đảm các client batch, mobile hoặc đối tác khác không bị ảnh hưởng.

## 4. Nguồn hợp đồng nào là nguồn chân lý?

Hợp đồng có thể được lưu:

1. **Cùng repository producer**, chẳng hạn `src/test/resources/contracts`.
2. Trong **repository contract riêng** có quy tắc pull request chung.
3. Trong **Maven contract dependency** được các build phân giải theo version.

Không có mô hình nào là bắt buộc cho mọi hệ thống. Tuy nhiên quy ước review phải xác định:

- **Đường dẫn thực** mà Contract Verifier sẽ đọc.
- **Repository và revision** của hợp đồng.
- Ai có quyền review/approve thay đổi DSL.
- Producer CI đang sử dụng revision nào.
- Stub artifact được sinh từ **cùng revision** với producer tests hay không.
- Consumer CI lấy stub từ artifact/repository nào.

Ví dụ cấu trúc:

~~~text
order-service/
└── src/
    └── test/
        └── resources/
            └── contracts/
                └── orders/
                    ├── get_paid_order.yml
                    ├── get_missing_order.yml
                    └── create_order.yml
~~~

Một PR nên chỉ ra **contract path và commit**, không chỉ tên file `get_paid_order.yml`, vì có thể có file trùng tên trong nhiều modules hoặc repositories.

Nếu hợp đồng ở repo riêng, **producer Git commit không thay thế contract Git commit**; phải ghi cả hai và khóa dependency tương ứng.

## 5. Review hành vi quan sát được thay vì implementation

Một HTTP contract YAML:

~~~yaml
description: "Lấy đơn hàng đã thanh toán"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

Reviewer nên hỏi:

- URL, HTTP method và status đã đúng thỏa thuận chưa?
- Headers và content type có quan trọng với consumer không?
- `PAID` là enum chính thức hay chỉ là một chuỗi mẫu?
- Có kiểm tra error scenarios mà consumer đang phụ thuộc không?
- Fixture `ORD-1001` là dữ liệu tổng hợp, không lấy từ production?
- Các giá trị động như ID/timestamp được kiểm soát bằng fixture hoặc matcher phù hợp?
- Base test của generated producer tests có thực sự gọi code producer cần xác minh không?
- Stub được sinh từ contract này có được consumer tải bằng đúng artifact/version không?

**Không nên nhồi mọi thuộc tính entity nội bộ vào hợp đồng** nếu consumer không sử dụng. Đồng thời, cũng không nên dùng matcher quá rộng, ví dụ `any string` thay cho enum `PAID` khi Checkout dùng chính enum đó để phân nhánh.

## 6. Phân loại thay đổi trước khi review

| Thay đổi | Đánh giá ban đầu | Điều cần xác minh |
| --- | --- | --- |
| Thêm endpoint mới | Thường tương thích | Route conflict, authorization, consumer mới |
| Thêm trường response tùy chọn | Có điều kiện | Strict JSON parser có thể từ chối field lạ |
| Xóa hoặc đổi tên field response | Thường breaking với consumer phụ thuộc | Mọi consumer dùng field cũ |
| Đổi number sang string | Thường breaking | Schema/deserializer và tính toán |
| Đổi HTTP status 404 thành 200 | Có thể breaking | Nhánh xử lý lỗi của consumer |
| Thêm request header bắt buộc | Thường breaking | Consumer cũ chưa gửi header |
| Đổi semantics dù giữ nguyên tên field | Có thể breaking nghiêm trọng | Nghiệp vụ consumer và assertions |
| Đổi event type hoặc enum | Có thể breaking | Message handlers, switch-case |
| Đổi message destination/topic | Có thể breaking | Subscriber không còn nhận event |
| Đổi schemaVersion/content type | Có thể breaking | Consumer deserialization |
| Thêm optional message header | Có điều kiện | Adapter/schema/header filters |
| Đổi controller/service method nội bộ, giữ API | Thường không ảnh hưởng | Producer contract tests chống hồi quy |
| Đổi retry/ordering/delivery guarantee | Cần kiểm thử bổ sung | Broker/integration behavior ngoài contract |

**“Thường tương thích” không đồng nghĩa với “đã PASS”.** Nếu consumer dùng strict deserialization, thêm một field response cũng có thể gây lỗi.

Một change proposal có thể ghi nhãn `additive`, `behavioral`, `breaking` hoặc `deprecation`; các nhãn đó là **metadata của quy trình review**, không phải field DSL Spring Cloud Contract mặc định.

## 7. Acceptance criteria phải cụ thể và kiểm tra được

Một câu như “API không ảnh hưởng consumer” **không đủ** vì không nói consumer nào, version nào hay bằng chứng nào.

Một tiêu chí có thể viết theo bốn phần:

| Thành phần | Câu hỏi |
| --- | --- |
| **Given** | Producer/consumer version, contract revision, profile nào? |
| **When** | Request/event nào hoặc CI job nào được chạy? |
| **Then** | Behavior/response/consumer outcome nào phải đúng? |
| **Evidence** | Test report, build ID, artifact checksum và trạng thái nào chứng minh? |

Ví dụ:

~~~text
AC-PRODUCER-01
Given: Order Service 2.5.0, contract revision def456.
When: generated producer tests cho get_paid_order chạy.
Then: response có id, status và paymentStatus đúng giá trị/thỏa thuận.
Evidence: producer CI run; số skipped required tests = 0.

AC-CONSUMER-01
Given: Checkout 1.8.0 và stub Order 2.5.0:stubs.
When: Checkout gọi GET /api/orders/ORD-1001 qua Stub Runner.
Then: Checkout xử lý order PAID mà không lỗi deserialization.
Evidence: consumer test report + resolved stub GAV/checksum.
~~~

Mẫu này là **quy ước do nhóm thiết kế**, không phải API đặc biệt của Contract Verifier.

### Tiêu chí nghiệm thu cần bao gồm phạm vi

- Những consumer đang hoạt động/được hỗ trợ nào cần PASS?
- Scenario happy path và error path nào là bắt buộc?
- Tổ hợp nào có thể xuất hiện khi rolling deploy hoặc rollback?
- Có feature flag, client serialization mode hoặc message schema nào thay đổi?
- Loại bằng chứng nào còn thiếu và xử lý khoảng trống thế nào?

Không thể nghiệm thu toàn bộ dựa trên một test `HTTP 200` nếu consumer phụ thuộc body, status enum hoặc error behavior cụ thể.

## 8. Ví dụ thay đổi phá tương thích và phương án review

Ban đầu Order Service trả:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

Nhóm Order đề xuất chỉ trả:

~~~json
{
  "id": "ORD-1001",
  "paymentStatus": "PAID"
}
~~~

Nếu Checkout 1.8.0 đang đọc `status`, đây là breaking change với consumer đó. Reviewer có thể đề xuất **expand–migrate–contract**.

### Expand: giữ field cũ và thêm field mới

~~~json
{
  "id": "ORD-1001",
  "status": "PAID",
  "paymentStatus": "PAID"
}
~~~

Contract YAML chuyển tiếp:

~~~yaml
description: "Giữ status khi bổ sung paymentStatus"
name: get_paid_order_transition
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
    paymentStatus: PAID
~~~

Generated producer test phải chứng minh **producer thật** trả cả hai field; stub mới phải đến consumer test.

### Migrate: nâng consumer theo lịch

Checkout 2.0.0 có thể chuyển sang đọc `paymentStatus`, đồng thời tạm hỗ trợ `status` nếu vẫn có khả năng gọi producer cũ trong rollback. Sales Portal/Analytics hoặc client khác cũng phải xác nhận cách họ dùng các field đó.

### Contract: loại bỏ behavior cũ

Chỉ bỏ `status` khi:

1. Không còn consumer được hỗ trợ phụ thuộc nó theo inventory và bằng chứng.
2. Các tổ hợp rollout/rollback còn có thể xuất hiện đã được kiểm tra.
3. Thời hạn deprecation và kế hoạch migration theo chính sách đã hoàn tất.
4. Producer tests và các consumer required cells đã PASS với artifact mới.
5. Quyết định phát hành ghi rõ phạm vi và giới hạn.

**Thêm field không được mặc định là an toàn**: một consumer cũ có strict parser vẫn có thể FAIL khi JSON xuất hiện `paymentStatus` mới, nên phải có consumer test thực tế.

## 9. Quy tắc review Groovy và YAML DSL

Ví dụ cùng ý tưởng bằng **Groovy DSL**:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description "Giữ hai trường trạng thái khi chuyển đổi"
    request {
        method GET()
        url "/api/orders/ORD-1001"
        headers {
            header("Accept", "application/json")
        }
    }
    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: "ORD-1001",
            status: "PAID",
            paymentStatus: "PAID"
        )
    }
}
~~~

Đây là Groovy DSL của **Spring Cloud Contract**, không phải code kiểm thử producer trực tiếp. Việc sinh/running tests cần plugin và base test class tương thích.

Reviewer kiểm tra:

- Có thay đổi thực sự trong hành vi quan sát được không?
- Có matcher quá yếu hoặc quá chặt?
- Có hai hợp đồng Groovy/YAML trùng một scenario ngoài chủ đích không?
- Có đặt implementation details vào DSL không?
- Có fixture ngẫu nhiên khiến CI flaky không?
- Có thể sinh stub mà consumer thật sự sử dụng không?

**Không cần tồn tại đồng thời cả Groovy và YAML cho cùng một case** nếu sẽ tạo trùng mappings và generated tests.

## 10. Đừng bỏ qua error contract và negative case

Một PR chỉ sửa hợp đồng `GET /api/orders/ORD-1001 → 200` có thể bỏ sót các phản hồi mà consumer phụ thuộc:

- `404` khi đơn hàng không tồn tại.
- `400` khi request sai.
- `409` khi xung đột trạng thái.
- `401/403` khi thiếu quyền.
- `429` hoặc timeout nếu consumer có retry policy theo thỏa thuận.
- `5xx` và cấu trúc error body mà consumer xử lý.

Ví dụ contract 404:

~~~yaml
description: "Đơn hàng không tồn tại"
name: get_missing_order
request:
  method: GET
  url: /api/orders/ORD-NOT-FOUND
response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: ORDER_NOT_FOUND
    message: "Không tìm thấy đơn hàng"
~~~

Các giá trị trên là **giao thức nghiệp vụ minh họa**, không phải error schema mặc định của SCC.

Một response 404 do WireMock không tìm thấy matching stub **không tương đương** với producer đã cam kết error schema 404 cụ thể. Nếu consumer cần body `code`, phải có contract scenario và producer test tương ứng.

## 11. Message contracts cần tiêu chí review riêng

Với thông điệp, thay đổi **destination, event type, schema, headers** có thể phá vỡ subscriber ngay cả khi HTTP APIs không đổi.

Ví dụ YAML message contract:

~~~yaml
description: "Thanh toán thành công phát ORDER_PAID"
label: order_paid
input:
  triggeredBy: markTestOrderAsPaid()
outputMessage:
  sentTo: orders.events
  body:
    eventType: ORDER_PAID
    orderId: ORD-1001
    schemaVersion: 2
  headers:
    correlationId: CORR-TEST-1001
~~~

Ở đây:

- `triggeredBy` gọi một phương thức base test **phía producer**.
- `sentTo` xác định logical destination theo adapter messaging được cấu hình.
- `body` và `headers` là nội dung consumer quan sát.
- `label` giúp nhận diện hoặc kích hoạt message stub khi tích hợp hỗ trợ.

`label` **không phải** Kafka topic; `sentTo` không tự tạo broker destination. Reviewer phải hiểu cách adapter/binder/broker diễn giải tên đó.

### Những câu hỏi reviewer message contract phải đặt

1. Đây là **event** đã xảy ra hay **command** yêu cầu producer làm việc?
2. Các consumer cũ có hiểu `schemaVersion: 2` không?
3. Đổi `eventType` hoặc `sentTo` có làm subscriber mất event không?
4. Headers có cam kết correlation ID/content type không?
5. Có message cũ còn trong broker khi consumer mới deploy không?
6. Producer test có thật sự đi qua logic publish cần kiểm tra không?
7. Stub Runner messaging consumer tests có đúng label/artifact/version không?
8. Retry, ordering, DLQ và idempotency có cần test khác ngoài contract không?

**Message contract PASS không tự chứng minh** exactly-once, delivery guarantees, retry, ordering hoặc broker routing thật. Nếu những điều này thuộc acceptance criteria, cần integration tests riêng và ghi rõ nguồn evidence.

## 12. Matcher, fixture và dữ liệu phải được review

| Thành phần | Quy tắc nên có | Rủi ro nếu thiếu |
| --- | --- | --- |
| Order ID | Format/kiểu phù hợp; dữ liệu tổng hợp | Matcher rộng quá mức |
| Status enum | Giá trị `PAID`/`PENDING` đúng nghiệp vụ | Consumer không nhận enum mới |
| Amount | Kiểu number, đơn vị, rounding | Đổi currency hoặc precision không được phát hiện |
| Timestamp | Format/timezone được thỏa thuận | CI phụ thuộc clock/timezone |
| Optional field | Thỏa thuận về absent/null/required | Parsing bị phá khi xóa/đổi |
| Error code | Giá trị cụ thể khi consumer xử lý theo code | Business branch sai |
| Correlation ID | Format và quan hệ input/output khi cần | Regex chỉ chứng minh một chuỗi tồn tại |
| Event destination | Đúng binding/route theo adapter | Event đến sai topic |

Cần dùng dữ liệu test **tổng hợp**, tránh token/PII từ production. Nếu response có generated ID hoặc timestamp, kiểm soát clock/fixture hay dùng matcher phù hợp thay vì làm expected body phụ thuộc giá trị không ổn định.

Generated tests flaky sẽ làm quy trình review thiếu tin cậy. **Đừng sửa bằng cách biến mọi assertion thành “bất kỳ chuỗi nào”** nếu consumer cần những bất biến cụ thể.

## 13. Tiêu chí phía producer: có kiểm thử thật

Producer-side acceptance criteria thường bao gồm:

| Tiêu chí | Evidence |
| --- | --- |
| Contracts được phát hiện | Log/manifest của đúng source root và revision |
| Generated producer tests được sinh | Generated source/test metadata |
| Generated tests biên dịch và **thực thi** | Test runner reports |
| Không skip ngoài ý muốn | Số skipped required tests bằng 0 |
| Test PASS trên mã producer | CI run ID và test reports |
| Base test thực sự kích hoạt behavior | Review fixture/code path |
| Stub mappings được tạo | Mapping files/scenario list |
| Stub JAR đã được attach/publish | Maven GAV/classifier + repository |
| Artifact không chứa dữ liệu production | Review/scan payload/headers |
| Stub có provenance | Contract revision, producer commit, checksum |

**`BUILD SUCCESS` không đủ** nếu tests đã bị skip hoặc plugin không phát hiện contract nào. Một JAR có tên `-stubs.jar` cũng không chứng minh nó chứa các mappings mong đợi.

### Record producer minh họa

~~~yaml
# Metadata do nhóm/CI xây dựng; KHÔNG phải output mặc định SCC.
producer:
  service: order-service
  version: "2.5.0"
  commit: "abc123_FULL_COMMIT"
contracts:
  revision: "def456_FULL_COMMIT"
  required_scenarios:
    - get_paid_order_transition
    - get_missing_order
verification:
  run_id: "producer-ci-7824"
  generated_tests_executed: true
  skipped: 0
  failed: 0
  result: PASS
stub:
  coordinate: "com.example.orders:order-service:2.5.0:stubs"
  sha256: "CHECKSUM_TU_ARTIFACT_THAT"
~~~

Chỉ ghi `PASS` sau khi CI đã đọc kết quả thật. Không thay placeholder bằng một SHA-256 tự bịa.

## 14. Tiêu chí phía consumer: phải thử đúng stub mới

Ví dụ consumer dùng Stub Runner:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-service:2.5.0:stubs:8090",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.test/maven/releases"
)
class CheckoutContractIntegrationTest {

    @Test
    void checkoutHandlesPaidOrder() {
        // Trỏ HTTP client thật của Checkout đến stub port 8090.
        // Gọi nghiệp vụ Checkout và assert kết quả.
    }
}
~~~

Đây là **khung minh họa**, cần cấu hình client/dependencies/assertions phù hợp; URL repository cũng là ví dụ.

Reviewer cần xác nhận:

- **Consumer Git commit/version** đúng bản đang hỗ trợ, không dùng HEAD thay bản cũ.
- **Stub Runner ID** là đúng producer version đang thay đổi, không phải bản cũ.
- **Artifact checksum** của bản consumer tải khớp bản producer verified khi cần truy vết.
- HTTP client thật được trỏ tới stub; không fallback vào staging/production.
- Assertions kiểm tra **logic consumer**, không chỉ stub server đã khởi động.
- Các scenario quan trọng được chạy và reports lưu được.

Consumer PASS với `order-service:2.4.0:stubs` **không chứng minh** tương thích với producer `2.5.0`.

## 15. Ma trận phiên bản là một phần của review

Giả sử:

~~~text
P_old = Order 2.4.0
P_new = Order 2.5.0
C_old = Checkout 1.8.0
C_new = Checkout 2.0.0
~~~

Bảng tổ hợp:

| Producer × Consumer | Tại sao cần? |
| --- | --- |
| `P_old × C_old` | Baseline hiện tại |
| `P_new × C_old` | Nâng producer khi consumer cũ còn chạy |
| `P_old × C_new` | Consumer nâng trước hoặc producer rollback |
| `P_new × C_new` | Trạng thái mục tiêu |

Khi nhiều consumer tồn tại, thêm các cột/required pairs cho Sales Portal, Analytics, Shipping hoặc client đối tác còn được hỗ trợ.

### Trạng thái cho từng ô

| Trạng thái | Ý nghĩa |
| --- | --- |
| `PASS` | Đã có producer verification và consumer test đúng cặp, trong phạm vi xác định |
| `FAIL` | Test đã chạy và thất bại |
| `NOT_RUN` | Chưa kiểm tra |
| `BLOCKED` | Chưa thể chạy do hạ tầng, dependency, quyền |
| `STALE` | Kết quả cũ không trùng revision/artifact mới |
| `UNSUPPORTED` | Không còn được hỗ trợ theo chính sách có bằng chứng |
| `NOT_APPLICABLE` | Tổ hợp không thể cùng tồn tại và có lý do rõ |

**Không tính `NOT_RUN`, `BLOCKED`, `STALE` là PASS.** Việc một required pair chưa được kiểm tra là lỗ hổng evidence, không phải dấu hiệu an toàn.

## 16. Luồng PR review và release gate đề xuất

~~~mermaid
flowchart TD
    A["Đề xuất thay đổi API/event"] --> B["Mô tả trước/sau và consumer impact"]
    B --> C["Review contract DSL + semantics"]
    C --> D["Cập nhật code producer và fixture"]
    D --> E["Sinh/chạy generated producer tests"]
    E --> F{"Producer PASS và đủ required scenarios?"}
    F -->|Không| X["BLOCK / sửa PR"]
    F -->|Có| G["Sinh, kiểm tra, khóa stub artifact"]
    G --> H["Consumer CI chạy đúng versions với stub mới"]
    H --> I{"Required consumer tests PASS?"}
    I -->|Không| X
    I -->|Có| J["Review migration, rollout, rollback"]
    J --> K{"Đủ approvals và evidence?"}
    K -->|Không| X
    K -->|Có| L["Merge/Release theo chính sách"]
~~~

Đây là **quy trình gợi ý**, không phải pipeline SCC bắt buộc. Các cổng phải được gắn vào công cụ CI thật của tổ chức.

### Bước 1 — Change proposal

Tác giả trình bày lý do, hành vi trước/sau, version producer, những consumer cần được bảo vệ, data model và breaking risk.

### Bước 2 — Contract review

Các nhóm thống nhất Groovy/YAML DSL, matcher, error cases, semantics, message destination, deprecation plan nếu cần.

### Bước 3 — Producer verification

CI chạy generated producer tests trên đúng producer commit/contract revision, không skip các phép thử bắt buộc.

### Bước 4 — Stub packaging

Tạo artifact có classifier `stubs`, kiểm tra mappings, version và checksum; publish vào repository được quản lý.

### Bước 5 — Consumer verification

Các consumer versions bắt buộc chạy qua Stub Runner với **stub mới**, có assertions nghiệp vụ.

### Bước 6 — Quyết định

Reviewer và release owner xem lại ma trận tương thích, các ngoại lệ, rủi ro còn lại và kế hoạch rollback rồi mới phê duyệt phát hành.

## 17. Mẫu PR change proposal

Đây là **mẫu văn bản**, không phải file Contract DSL:

~~~markdown
## Mục tiêu
- Interface: Order Service — GET /api/orders/{id}
- Lý do: tách paymentStatus khỏi status chung
- Phân loại: additive có điều kiện trong giai đoạn chuyển tiếp

## Hành vi trước/sau
- Trước: trả status
- Sau (expand): trả status và paymentStatus
- Sau cùng: chỉ xem xét loại bỏ status khi đủ bằng chứng

## Consumer ảnh hưởng
- Checkout 1.8.0: đang dùng status
- Checkout 2.0.0: dự kiến dùng paymentStatus
- Sales Portal 4.1.0: cần kiểm tra parser
- Client khác: inventory/đầu mối owner cần xác minh

## Contract và producer
- DSL path và revision: ...
- Producer commit/build: ...
- Generated producer test reports: ...
- Stub GAV/classifier/checksum: ...

## Acceptance criteria
- [ ] Producer tests chạy PASS, không skip
- [ ] Stub artifact đúng revision, chứa đủ mappings
- [ ] Checkout 1.8 PASS với stub mới
- [ ] Checkout 2.0 PASS với stub mới
- [ ] Sales Portal được kiểm tra hoặc có ngoại lệ hợp lệ
- [ ] Tổ hợp rollback đã được đánh giá
- [ ] Không có dữ liệu production nhạy cảm

## Rollout
- Thứ tự: ...
- Deprecation window: ...
- Điều kiện rollback: ...
- Người giám sát: ...

## Review/Decision
- Producer reviewer: ...
- Consumer reviewers: ...
- Contract owner: ...
- Release owner: ...
- Status: DRAFT / ACCEPTED / BLOCKED
~~~

Checkbox tự đánh dấu không phải bằng chứng. Kèm link CI run và metadata thực tế, có chính sách lưu giữ phù hợp.

## 18. Mẫu acceptance criteria do CI đo

Một file quản trị **riêng** có thể định nghĩa các ô bắt buộc:

~~~yaml
# Không phải cấu hình mặc định của Spring Cloud Contract.
change_id: "ORDER-API-2026-017"
producer:
  service: order-service
  target_version: "2.5.0"
required_consumer_cells:
  - consumer: checkout-service
    version: "1.8.0"
    stub_version: "2.5.0"
  - consumer: checkout-service
    version: "2.0.0"
    stub_version: "2.5.0"
  - consumer: sales-portal
    version: "4.1.0"
    stub_version: "2.5.0"
gates:
  generated_producer_tests: required
  stub_provenance: required
  consumer_tests: required
  rollback_review: required
~~~

Pipeline sử dụng cấu hình này để **thực thi và thu thập kết quả**, không coi chữ `required` hoặc `true` do tác giả gõ là bằng chứng PASS.

Ví dụ evidence một ô:

~~~yaml
# Chỉ là ví dụ minh họa thông tin cần thu thập.
producer_commit: "abc123_FULL_COMMIT"
contract_revision: "def456_FULL_COMMIT"
producer_ci_run: "producer-ci-7824"
producer_tests: PASS
stub_coordinate: "com.example.orders:order-service:2.5.0:stubs"
stub_sha256: "SHA256_DO_CI_TINH"
consumer: "checkout-service:1.8.0"
consumer_commit: "cde789_FULL_COMMIT"
consumer_ci_run: "checkout-ci-8812"
resolved_stub_sha256: "SHA256_DA_XAC_MINH"
consumer_tests: PASS
compatibility_scope: "GET paid/missing order"
~~~

Các SHA/build ID là placeholder, không phải bằng chứng cho một lần build thực. Một release gate cần các giá trị được tính từ artifacts/reports đúng job.

## 19. Merge gate khác release gate

Một số tổ chức cho phép merge một contract draft hoặc feature-flagged change **trước khi** phát hành. Một số khác deploy tự động khi merge. Vì thế cần quyết định rõ:

| Tình huống | Review quyết định |
| --- | --- |
| DSL draft chưa thống nhất | Không coi là accepted behavior |
| Producer generated tests FAIL | BLOCK theo cổng chất lượng |
| Test suite bị skip hoặc có 0 required tests | BLOCK vì thiếu evidence |
| Stub artifact sai revision/version | BLOCK vì consumer thử sai artifact |
| Required consumer FAIL với stub mới | BLOCK hoặc quy trình ngoại lệ có thẩm quyền |
| CI không chạy do repository lỗi | `BLOCKED`, chưa kết luận tương thích |
| Consumer đã ngừng hỗ trợ có bằng chứng | Có thể loại khỏi required set theo policy |
| Thay đổi chỉ ở tài liệu, không ảnh hưởng behavior | Có thể cần mức review khác |
| Dữ liệu production nhạy cảm bị đưa vào stub | BLOCK và xử lý bảo mật |

Nếu merge tự kích hoạt deploy, merge gate cần đủ tiêu chí của release gate. Nếu release là bước riêng, phải có **release evidence** và không mặc định PR review cũ vẫn đúng sau các commit mới.

**Ngoại lệ không làm test FAIL biến thành PASS.** Nếu phải phát hành khi còn thiếu bằng chứng, ghi rõ decision, người chịu trách nhiệm, phạm vi rủi ro, giám sát và rollback.

## 20. Rollout và rollback phải được rà soát

Một hệ thống có thể trải qua:

~~~text
T0: P_old + C_old
T1: P_new + C_old
T2: P_new + C_new
Rollback producer: P_old + C_new
~~~

Ngay cả khi `P_new × C_new` PASS, tổ hợp `P_old × C_new` có thể FAIL nếu consumer mới chỉ hiểu field mới còn producer cũ không cung cấp.

Review cần cân nhắc:

- Thứ tự triển khai các service.
- Rolling/blue–green/canary có tạo hỗn hợp phiên bản không?
- Khi rollback producer, consumer mới còn chạy được không?
- Feature flags có tạo nhiều dạng response/event không?
- Message cũ còn trong broker có được consumer mới xử lý không?
- Có deadline và chủ sở hữu quyết định bỏ API/event cũ không?

Nếu một tổ hợp được tuyên bố **không thể cùng tồn tại**, cần có bằng chứng từ orchestration/rollout policy, không đơn giản bỏ qua vì “không nằm trong kế hoạch chính”.

## 21. Quy tắc thông báo giữa các nhóm

Spring Cloud Contract **không áp đặt thời hạn** để một consumer phải trả lời review. Tổ chức cần thống nhất thời hạn hợp lý cho từng loại thay đổi.

Một quy trình:

1. Tác giả mở đề xuất **trước** khi xóa field, endpoint hoặc đổi topic.
2. Contract owner thông báo các consumer owners từ inventory.
3. Consumer xác nhận dependency, scenario và lịch migration.
4. Với breaking change, có review chung để chọn versioning hoặc lộ trình chuyển tiếp.
5. Nếu reviewer chưa phản hồi, trạng thái là **PENDING/BLOCKED**, không tự coi im lặng là chấp thuận.
6. Sau khi tạo stub mới, các consumer CI jobs chạy theo ma trận.
7. Cập nhật changelog/deprecation notice và release decision bằng văn bản.

Nếu có client ngoài tổ chức, danh sách consumer có thể không đầy đủ. Cần chính sách API versioning, deprecation window, telemetry có giới hạn quyền riêng tư và bộ test đại diện; **không tuyên bố tất cả consumer PASS** khi chưa thể kiểm chứng.

## 22. Giải quyết xung đột: producer cần thay đổi, consumer chưa sẵn sàng

Ví dụ producer muốn bỏ `status` ngay, nhưng Checkout cũ còn chạy trong hai tuần.

Một review mang tính hợp tác có thể:

- Producer nêu lý do kỹ thuật và chi phí duy trì hai field.
- Consumer cung cấp code path/test chứng minh dependency và lịch nâng cấp.
- Contract owner so sánh các phương án tương thích.
- Release owner đánh giá rollback, business impact và trách nhiệm chấp nhận rủi ro.
- Các bên ghi quyết định và điều kiện thoát khỏi giai đoạn chuyển tiếp.

| Phương án | Thích hợp khi | Lưu ý |
| --- | --- | --- |
| Giữ hai field tạm thời | API có thể mở rộng dễ dàng | Phải có test và deprecation deadline |
| Version endpoint `/v1`/`/v2` | Schema/semantics đổi lớn | Phải duy trì route và support policy |
| Consumer adapter | Có thể hỗ trợ hai schema | Cần test cả dữ liệu cũ/mới |
| Song song message event/topic | Subscriber không nâng đồng thời | Cần routing/broker integration test |
| Feature flag/canary | Có kiểm soát triển khai | Test cả flag ON/OFF khi được hỗ trợ |
| Hoãn breaking change | Consumer bắt buộc chưa thể migrate | Ghi blocker và quyết định sau |

**Không sửa contract chỉ để hợp thức hóa output mới của producer** nếu consumer chưa đồng ý thay đổi hành vi.

## 23. Bảo đảm evidence có thể truy vết

~~~mermaid
flowchart TD
    A["Contract path + revision"] --> B["Producer commit + CI build"]
    B --> C["Generated producer test reports"]
    A --> D["Stub mappings"]
    C --> E["Stub JAR GAV + checksum"]
    D --> E
    E --> F["Artifact repository"]
    F --> G["Consumer Stub Runner resolved artifact"]
    G --> H["Consumer commit + CI test report"]
    H --> I["Acceptance decision và phạm vi"]
~~~

Một record đáng tin ghi được:

- Contract repository, path và commit.
- Producer source commit và generated producer test CI run.
- Stub coordinate `groupId:artifactId:version:stubs` và SHA-256.
- Repository nơi artifact được publish.
- Consumer Git commit/tag và resolved stub checksum.
- Consumer test report/scenarios.
- Review decision và nhóm/phiên bản đang được hỗ trợ.

**Checksum giúp xác định bytes, không phải chữ ký số.** Nếu cần xác thực publisher và chống sửa evidence, bổ sung attestation/chữ ký theo chính sách supply-chain.

Không đưa token, private key hoặc dữ liệu production thật vào report, contract hay stub JAR.

## 24. Chẩn đoán khi CI báo FAIL

Nếu consumer test FAIL với stub mới, nên kiểm tra theo lớp:

1. **Danh tính artifact:** Đã tải đúng GAV/version/classifier chưa?
2. **Provenance:** JAR có đến từ contract revision và producer build đã verified không?
3. **Runtime:** Stub Runner có chạy, client có gọi đúng port/service ID không?
4. **HTTP matching/message routing:** Method/path/header/body hoặc destination có thay đổi không?
5. **Consumer behavior:** Version cũ có đang phụ thuộc hành vi bị xóa không?
6. **Producer implementation:** Generated tests thực sự chạy và xác minh code path nào?
7. **Phân loại:** Breaking change thật, lỗi fixture, flaky test hay hạ tầng CI?
8. **Giải pháp:** Giữ compatibility, nâng consumer, version endpoint/event hoặc điều chỉnh test nếu expectation sai.
9. **Bằng chứng mới:** Sau sửa, chạy lại producer và consumer required tests; không dùng report cũ.

### Một số nguyên nhân thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Producer tests PASS nhưng consumer FAIL | Consumer kỳ vọng behavior ngoài contract hoặc breaking change | Xem scenario và thỏa thuận |
| Producer tests không xuất hiện | Plugin/contract root hoặc skip flags | Chặn gate, sửa build |
| Stub Runner chỉ tải bản cũ | Version/cache/repository | Chốt version và checksum |
| Stub server trả 404 | Request mismatch hoặc sai server | Xem mapping, client URL |
| Messaging test không thấy event | Sai destination/adapter | Xác minh binder và routing |
| Test lúc PASS lúc FAIL | Fixture/clock/concurrency | Làm test deterministic |
| CI không tải artifact | Credentials/network | `BLOCKED`, không kết luận compatibility |
| Consumer code cũ nhưng test code đã đổi | Test không đại diện version production | Chạy đúng consumer source/behavior |

**Không được sửa test của Checkout 1.8.0 thành test hành vi Checkout 2.0.0**, rồi vẫn dùng kết quả để tuyên bố producer mới tương thích Checkout 1.8.0 đang chạy.

## 25. Những gì contract review chưa thể chứng minh

Một kết luận review đúng phạm vi không nên ghi “an toàn tuyệt đối”. Spring Cloud Contract không tự chứng minh:

- Mọi endpoint đã được mô tả và thử nghiệm.
- Mọi consumer version trên production đều được đưa vào ma trận.
- Production TLS, authentication và authorization đều đúng.
- Broker exactly-once, ordering, DLQ, retry hay retention đã được kiểm chứng.
- Hiệu năng, throughput, latency và failover đã đạt yêu cầu.
- Artifact repository không bị ghi đè, nếu chưa kiểm soát checksum/provenance.
- Rolling deployment luôn an toàn nếu chưa thử các phiên bản cùng tồn tại.

Một kết luận có căn cứ sẽ ghi:

> “Order Service 2.5.0 tại commit abc123 đã PASS generated producer contract tests của revision def456. Stub 2.5.0:stubs có checksum được ghi nhận đã được Checkout 1.8.0 và 2.0.0 sử dụng qua Stub Runner trong các scenario get_paid_order/get_missing_order; các required tests PASS. Những consumer/kịch bản ngoài danh sách chưa được kết luận.”

Đây là **ví dụ cách diễn đạt**, không phải xác nhận một pipeline thực đã chạy.

## 26. Bài tập thực hành

### Bài tập A — Viết tiêu chí nghiệm thu

Order muốn đổi `status` sang `paymentStatus`, nhưng Checkout 1.8.0 còn production.

**Yêu cầu:** soạn ít nhất năm acceptance criteria có test/evidence cụ thể trước khi xóa `status`.

**Gợi ý:** producer tests, stub artifact mới, Checkout 1.8, Checkout 2.0, rollout/rollback, trạng thái deprecation.

### Bài tập B — Review thiếu error scenario

PR có hợp đồng `GET /api/orders/ORD-1001 → 200`. Checkout phụ thuộc body `404 ORDER_NOT_FOUND`.

**Yêu cầu:** viết review comment và đề xuất contract scenario bổ sung.

**Gợi ý:** HTTP 404 có body/schema cụ thể và cả producer/consumer tests.

### Bài tập C — Consumer im lặng

Sales Portal chưa phản hồi thông báo breaking change trong thời hạn nội bộ.

**Yêu cầu:** có nên tự coi đã chấp thuận? Cần escalation hoặc bằng chứng gì?

**Gợi ý:** không; trạng thái PENDING/BLOCKED, tìm owner, xác minh dependency và ghi quyết định rủi ro.

### Bài tập D — Test bị skip

Maven báo BUILD SUCCESS nhưng không có generated contract tests trong test report.

**Yêu cầu:** đánh giá có đủ bằng chứng release không?

**Gợi ý:** chưa; kiểm tra plugin executions, contracts root, test runner và skip flags.

### Bài tập E — Consumer dùng stub sai phiên bản

Checkout 1.8 PASS với `order-service:2.4.0:stubs`. Producer chuẩn bị phát hành 2.5.0.

**Yêu cầu:** ô nào chưa được xác minh và cách sửa pipeline?

**Gợi ý:** `P2.5 × C1.8`; khóa stub 2.5.0 và kiểm tra resolved checksum.

### Bài tập F — Message destination thay đổi

Producer đổi `sentTo("orders.events")` thành `sentTo("orders.events.v2")` nhưng Shipping vẫn subscribe destination cũ.

**Yêu cầu:** phân loại breaking change và viết acceptance criteria cho migration.

**Gợi ý:** publish song song hoặc versioned event, xác minh consumer và routing, xét message tồn đọng.

### Bài tập G — Thiếu rollback pair

Checkout mới chỉ đọc `paymentStatus`. Producer cũ chỉ trả `status` và có thể được rollback.

**Yêu cầu:** nêu tổ hợp ma trận cần test và một cách thiết kế consumer an toàn.

**Gợi ý:** `P_old × C_new`, hỗ trợ cả hai field trong thời gian chuyển tiếp.

### Bài tập H — Mẫu PR

Thiết kế PR template cho Order, Checkout, Sales Portal và Analytics.

**Yêu cầu:** có before/after, consumer inventory, DSL paths, producer evidence, stub version/checksum, consumer matrix, deprecation và approvals.

**Gợi ý:** dùng mẫu ở mục 17 và ghi trạng thái thực của từng ô.

### Bài tập I — Matcher quá rộng

Generated producer test FAIL vì timestamp động. Reviewer muốn thay assertion ISO-8601 UTC bằng “bất kỳ chuỗi nào”.

**Yêu cầu:** vì sao không phù hợp với acceptance criteria của consumer?

**Gợi ý:** kiểm soát clock hoặc matcher ràng buộc format/timezone đúng thỏa thuận.

### Bài tập J — Ngoại lệ khi repository lỗi

Consumer bắt buộc chưa chạy vì remote artifact repository lỗi 503; business muốn release ngay.

**Yêu cầu:** chọn trạng thái, ai phải chấp nhận rủi ro và cần ghi gì?

**Gợi ý:** `BLOCKED` chứ không phải PASS; quyết định có thẩm quyền, rủi ro, giám sát, rollback và kế hoạch chạy lại.

## 27. Checklist review trước khi chấp nhận thay đổi

### Phạm vi và trách nhiệm

- [ ] Change proposal nêu rõ nhu cầu, hành vi trước/sau và rủi ro.
- [ ] Producer, consumer, contract owner và release owner được xác định.
- [ ] Danh sách các consumer còn được hỗ trợ được xác minh.
- [ ] Consumer liên quan có kênh review và thời hạn phản hồi rõ.
- [ ] Không coi im lặng là đồng ý.
- [ ] Có kế hoạch migration/deprecation nếu cần.

### Chất lượng hợp đồng

- [ ] Groovy/YAML DSL mô tả đúng hành vi quan sát được.
- [ ] HTTP method/path/status/headers/body hoặc message input/output rõ.
- [ ] Matcher bảo vệ các semantics consumer thực sự cần.
- [ ] Có happy path và negative/error scenarios bắt buộc.
- [ ] Dữ liệu test tổng hợp, không chứa secrets/PII production.
- [ ] Không trùng contract scenario ngoài chủ đích.
- [ ] Fixtures deterministic, tránh test flaky.

### Producer verification

- [ ] Contracts được phát hiện đầy đủ ở đúng revision.
- [ ] Generated producer tests được sinh, biên dịch và thực thi.
- [ ] Không có required tests bị skip hoặc 0 tests không mong muốn.
- [ ] Producer tests PASS trên implementation cần phát hành.
- [ ] Stub JAR đúng classifier/version, mappings đầy đủ.
- [ ] Producer commit, contract revision, CI run và checksum được ghi.
- [ ] Không dùng kết quả producer build khác để hợp thức hóa stub mới.

### Consumer verification

- [ ] Stub Runner dùng đúng GAV/classifier/version mới.
- [ ] Đã kiểm tra source repository và checksum khi cần.
- [ ] Consumer source đúng version còn được hỗ trợ.
- [ ] Tests gọi đúng stub server/adapter và có assertions nghiệp vụ.
- [ ] Required consumer matrix cells PASS.
- [ ] `NOT_RUN`, `BLOCKED`, `STALE` không được ghi thành PASS.
- [ ] Rollout/rollback và message schema cũ còn tồn đọng được xét nếu áp dụng.
- [ ] Consumer reports có thể truy vết đến producer verification.

### Quyết định

- [ ] Người phê duyệt theo thẩm quyền đã được xác định.
- [ ] Required release gates được thực thi hoặc ngoại lệ có quyết định minh bạch.
- [ ] Rollout/rollback, điều kiện quan sát và phương án khắc phục rõ.
- [ ] Đã ghi phạm vi và giới hạn của bằng chứng contract testing.
- [ ] Không publish breaking change âm thầm cho consumer còn được hỗ trợ.

## Kết luận

**Quy ước rà soát** giúp các nhóm thống nhất ai được đề xuất, ai cần tham gia, review những semantics nào và cách xử lý bất đồng. **Tiêu chí chấp nhận** biến thỏa thuận đó thành những điều kiện đo được: generated producer tests thật sự chạy PASS, stub artifact có nguồn gốc rõ, các consumer versions liên quan PASS với **stub mới** và kế hoạch rollout/rollback đã được xét.

Trong Spring Cloud Contract, review không kết thúc khi merge một file Groovy/YAML; nó kết thúc khi có **quyết định dựa trên bằng chứng đúng phiên bản và có phạm vi**.

**Ghi nhớ:** *Approval không thay thế kiểm thử; PASS với stub cũ không chứng minh producer mới tương thích; và một thay đổi chỉ được chấp nhận khi những consumer chịu ảnh hưởng có đường chuyển tiếp đã được kiểm chứng.*
