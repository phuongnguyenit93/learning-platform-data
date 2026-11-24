# Phản hồi khi producer chưa đáp ứng tương tác mới

## Mục tiêu học tập

Trong **Spring Cloud Contract**, producer cung cấp HTTP API hoặc phát thông điệp; consumer dựa vào hành vi đó để thực hiện nghiệp vụ. Các bên mô tả kỳ vọng bằng **Groovy/YAML DSL**, sinh **producer contract tests**, tạo stub cho **Stub Runner** và tích hợp CI để phát hiện những thay đổi không tương thích.

Thách thức thường xuất hiện khi **consumer cần một tương tác mà producer chưa triển khai**. Một generated producer test đỏ lúc đó không nhất thiết cho thấy hợp đồng sai; nó có thể là bằng chứng đầu tiên rằng một đề xuất chưa trở thành cam kết được hỗ trợ.

Bài học thuộc chương **Phối hợp nhiều nhóm**, tập trung vào quy trình phản hồi một đề xuất mới mà producer chưa đáp ứng. Sau bài, bạn có thể:

- Phân biệt **proposed**, **accepted**, **implemented**, **verified** và **published**.
- Viết đề xuất HTTP/message contract đủ rõ để producer xem xét.
- Đọc generated producer test FAIL và xác định đó là thiếu implementation, sai DSL, sai test setup hay lỗi hạ tầng.
- Phản hồi với **bằng chứng, quyết định, lý do, owner và bước tiếp theo** thay vì chỉ nói “chưa hỗ trợ”.
- Chọn giữa **chấp nhận, thương lượng, chia giai đoạn, hoãn hoặc từ chối**.
- Giữ **candidate stub** để consumer phát triển mà không công bố nhầm như verified stub.
- Thiết kế CI giữ producer tests làm quality gate và kiểm tra tương thích consumer trước release.
- Phân tích các tình huống HTTP, messaging, thay đổi breaking, retry và rollout an toàn.

> **Nguyên tắc:** contract do consumer đề xuất là một **nhu cầu cần được review**. Chỉ khi producer triển khai, generated producer tests thực sự chạy và PASS, contract đó mới có bằng chứng là được hỗ trợ trong phạm vi đã kiểm chứng.

## 1. Tình huống xuyên suốt: Checkout cần reservation API mới

Giả sử có hai dịch vụ:

- **Checkout Service**: consumer, xử lý đặt hàng.
- **Inventory Service**: producer, quản lý số lượng hàng.

Hiện Checkout chỉ có thể kiểm tra tồn kho:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

~~~json
{"sku":"SKU-101","available":true,"quantity":8}
~~~

Nhưng kết quả đọc là **snapshot**. Hai đơn hàng có thể cùng thấy còn tám sản phẩm rồi đặt quá số lượng thực. Checkout muốn có thao tác giữ chỗ:

~~~http
POST /api/inventory/reservations HTTP/1.1
Content-Type: application/json
Idempotency-Key: checkout-req-1001

{"sku":"SKU-101","quantity":2}
~~~

Response đề xuất:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "reservationId": "RSV-1001",
  "sku": "SKU-101",
  "reservedQuantity": 2,
  "status": "ACTIVE"
}
~~~

**Vấn đề:** producer chưa có `POST /api/inventory/reservations`. Khi consumer gửi contract PR, producer sinh test và nhận **404 thay vì 201**.

Các nhóm không nên tự động “sửa 201 thành 404”, bỏ test hoặc công bố stub. Họ cần xác nhận:

1. Reservation có thuộc trách nhiệm Inventory không?
2. Endpoint và schema nào là phù hợp?
3. Đơn vị tồn kho được giữ chỗ có cần đảm bảo atomic dưới tải đồng thời không?
4. Idempotency và retry được hiểu như thế nào?
5. Producer sẽ triển khai trong phiên bản nào, hoặc có phương án khác?
6. Consumer xử lý thế nào trong lúc chưa được hỗ trợ?
7. Điều kiện nào cho phép gọi giao diện này là verified/published?

### Luồng phối hợp

~~~mermaid
flowchart TD
    A["Consumer gửi contract proposal"] --> B["Review use case và DSL"]
    B --> C["Producer thử generated test"]
    C --> D{"Test PASS?"}
    D -->|Có| E["Producer verified"]
    D -->|Không| F["Triage: code / DSL / fixture / CI"]
    F --> G{"Quyết định hai nhóm"}
    G -->|Accept| H["Implement + rerun producer tests"]
    G -->|Negotiate| I["Sửa phạm vi được thống nhất"]
    G -->|Defer| J["Giữ proposal, chưa publish"]
    G -->|Reject| K["Lý do + alternative"]
    H --> C
    I --> C
    E --> L["Candidate stub đúng revision"]
    L --> M["Stub Runner consumer tests"]
    M --> N["Compatibility + release gate"]
~~~

Tín hiệu thất bại là **feedback hữu ích trong nhánh đề xuất**, nhưng ở nhánh phát hành, producer contract tests đã cam kết phải PASS.

## 2. Contract được đề xuất khác contract được hỗ trợ

| Trạng thái phối hợp | Ý nghĩa | Có thể nói producer đã hỗ trợ? |
|---|---|---|
| **PROPOSED** | Consumer mới nêu nhu cầu và DSL | **Không** |
| **UNDER_REVIEW** | Hai nhóm đang làm rõ semantics, ownership | **Không** |
| **ACCEPTED_PENDING** | Producer đồng ý về phạm vi nhưng implementation chưa xong | **Chưa** |
| **IMPLEMENTED_UNVERIFIED** | Code đã viết nhưng chưa có producer test PASS | **Chưa đủ bằng chứng** |
| **VERIFIED** | Generated producer tests được chạy và PASS | **Có, trong phạm vi test** |
| **PUBLISHED** | Stub từ revision đã verify được phát hành | Có thể consumer tải để test |
| **DEFERRED / REJECTED** | Chưa cam kết hoặc chọn phương án khác | **Không** |

**Các nhãn trên là trạng thái công việc được đề xuất cho issue/PR**, không phải những giá trị status mặc định của Spring Cloud Contract DSL hay metadata bài học.

### Tại sao phân biệt quan trọng?

- `PROPOSED` cho phép consumer đưa ra kỳ vọng và nhận phản hồi.
- `ACCEPTED_PENDING` cho biết producer đồng ý về mục tiêu, **không hứa rằng API đã chạy được**.
- `IMPLEMENTED_UNVERIFIED` không đủ để consumer bật chức năng production.
- `VERIFIED` yêu cầu generated producer tests **thực sự được thực thi**.
- `PUBLISHED` đòi thêm quality gate về artifact/version/permission.
- `DEFERRED` và `REJECTED` cần có lý do và một hướng tiếp theo rõ ràng.

Nếu không phân biệt, consumer có thể hiểu “PR contract đã merge” là “producer endpoint đã sẵn sàng”.

## 3. Chuyển yêu cầu thành Groovy DSL cụ thể

Một file proposal, ví dụ `contracts/inventory/reservationCreated.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout giu cho 2 don vi SKU-101'

    request {
        method 'POST'
        url '/api/inventory/reservations'
        headers {
            contentType(applicationJson())
            header('Idempotency-Key', 'checkout-req-1001')
        }
        body(
            sku: 'SKU-101',
            quantity: 2
        )
    }

    response {
        status 201
        headers {
            contentType(applicationJson())
        }
        body(
            reservationId: 'RSV-1001',
            sku: 'SKU-101',
            reservedQuantity: 2,
            status: 'ACTIVE'
        )
    }
}
~~~

Phiên bản YAML thay thế:

~~~yaml
description: 'Checkout giu cho 2 don vi SKU-101'
request:
  method: POST
  url: /api/inventory/reservations
  headers:
    Content-Type: application/json
    Idempotency-Key: checkout-req-1001
  body:
    sku: SKU-101
    quantity: 2
response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    reservationId: RSV-1001
    sku: SKU-101
    reservedQuantity: 2
    status: ACTIVE
~~~

Hai ví dụ mô tả **một tình huống**; không nên đưa cả hai vào cùng build nếu làm tạo duplicate mappings.

### Điều gì đã được mô tả?

- Request `POST` đúng path.
- Content-Type và Idempotency-Key có ý nghĩa.
- `quantity` là **number**, không phải chuỗi.
- Response `201` và các field mà Checkout cần.
- `reservationId` cố định là fixture; ID production thường động và cần matcher phù hợp khi viết contract thực tế.

### Điều gì chưa được mô tả?

Một request/response mẫu chưa nói hết:

- Reservation hết hạn khi nào?
- Gửi cùng khóa hai lần trả cùng kết quả hay báo lỗi?
- Nếu dùng lại khóa với payload khác thì sao?
- Nếu không còn đủ hàng, response/error code thế nào?
- Nếu Checkout timeout sau khi producer đã tạo reservation, client retry ra sao?
- Có authentication, permission hay correlation ID bắt buộc không?

Đây là **những câu hỏi review cần chốt**, không phải lý do để nới matcher và xem như xong.

## 4. Đọc generated producer test đỏ như một tín hiệu

Spring Cloud Contract sẽ sinh test phía producer từ hợp đồng trên. Ý nghĩa của generated test:

~~~text
WHEN:
  POST /api/inventory/reservations
  Content-Type: application/json
  Idempotency-Key: checkout-req-1001
  body = {"sku":"SKU-101","quantity":2}

THEN:
  HTTP status = 201
  Content-Type = application/json
  $.reservationId = "RSV-1001"
  $.reservedQuantity = 2
  $.status = "ACTIVE"
~~~

Đây là **pseudocode**, không phải output Java nguyên văn của một version verifier.

Producer hiện chưa có route, nên log có thể cho biết:

~~~text
Test: ReservationContractTest.shouldReserveSku
Expected status: 201
Actual status:   404
Result: FAILED
~~~

**Phản hồi không đủ:** “Contract đỏ, consumer viết sai.”

**Phản hồi có ích:** “Trên producer commit A, generated test từ proposal B gọi `POST /api/inventory/reservations` vào controller thật và nhận 404 thay vì 201. Route chưa được triển khai. Chúng tôi đề xuất review semantics idempotency và tạo issue triển khai, giữ contract ở trạng thái proposal đến khi test PASS.”

### Đừng kết luận quá sớm khi thấy 404

Một `404` cũng có thể do base test chưa setup controller đúng, URL thiếu context path hoặc test đang gọi nhầm phiên bản. Trước khi ghi “chưa hỗ trợ”, cần:

1. Xác nhận **đúng contract revision**.
2. Đọc generated test và request thực tế.
3. Xác nhận base test chạy **controller/ứng dụng producer thật**.
4. Kiểm tra mapping controller, method, path.
5. Xem fixture, test security và exception handler.
6. Phân biệt implementation gap với test setup gap.

## 5. Bảng triage khi producer test chưa đạt

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| HTTP 404 thay vì 201 | Route chưa tồn tại, path/base test sai | Controller mapping + generated request |
| HTTP 405 | Route có nhưng chưa hỗ trợ HTTP method | Method contract và routing |
| HTTP 400 | Body/schema/validation chưa thống nhất | DTO required fields và JSON types |
| HTTP 401/403 | Security chưa được setup hoặc contract thiếu auth | Filter chain, test identity và API policy |
| HTTP 500 | Route có nhưng logic/fixture/service lỗi | Stack trace và test context |
| HTTP 201 nhưng thiếu field | Producer chưa trả đủ response | Assertion/body actual |
| Kiểu `quantity` sai | Producer trả string thay number | Generated JSON assertions |
| Message receive timeout | Publisher chưa có hoặc receiver sai | Trigger/destination/binder |
| Test không được sinh | DSL chưa được discover hoặc plugin sai | Contract path, source set, test report |
| Test compile failure | Base class/test framework sai | Generated test imports và base class |
| Build SUCCESS nhưng `0 tests` | Skip/filter/sai source set | Log test discovery và report |

Khi kết luận, ghi rõ **đã xác minh** hay **giả thuyết cần kiểm tra**. Không quy mọi fail cho producer implementation.

## 6. Những yếu tố bắt buộc trong một phản hồi

| Thành phần | Ví dụ phản hồi |
|---|---|
| **Đã tiếp nhận** | “Đã review proposal reservation của Checkout.” |
| **Bằng chứng** | “Generated test ở commit A nhận 404, expected 201.” |
| **Hiện trạng** | “Route chưa được triển khai trên nhánh hiện tại.” |
| **Quyết định** | “Chấp nhận mục tiêu nhưng chưa chốt idempotency.” |
| **Lý do** | “Cần bảo đảm reservation atomic, tránh oversell.” |
| **Owner** | “Inventory team mở issue triển khai và review thiết kế.” |
| **Điều cần làm rõ** | “Duplicate key, insufficient-stock error, expiration.” |
| **Mốc** | “Mốc triển khai chưa được chốt; cập nhật sau review.” |
| **Phương án tạm** | “Checkout giữ feature flag off, candidate stub chỉ để test.” |
| **Điều kiện Done** | “Producer test PASS, versioned stub, consumer compatibility PASS.” |

Không hứa ngày phát hành khi chưa được người phụ trách xác nhận. Nếu chưa có mốc, **nói rõ chưa có mốc** và cần một quyết định tiếp theo.

### Ví dụ comment trong PR

> Đã xem đề xuất `POST /api/inventory/reservations`. Producer hiện trả **404**, trong khi contract mong đợi **201**; generated test từ proposal chưa PASS. Nhóm Inventory đồng ý rằng cần atomic reservation, nhưng còn phải chốt `Idempotency-Key`, thời hạn giữ chỗ và mã lỗi khi thiếu hàng. Trước mắt giữ contract ở nhánh proposal, không công bố stub như đã xác nhận. Checkout có thể dùng candidate để phát triển client riêng, nhưng chưa bật luồng này trên production.

Đoạn trên là **mẫu minh họa**, không phải một thông báo thực sự đã gửi hoặc một cam kết roadmap.

## 7. Chọn quyết định phù hợp với yêu cầu mới

| Quyết định | Khi nào hợp lý? | Việc tiếp theo |
|---|---|---|
| **ACCEPT / IMPLEMENT** | Nhu cầu hợp lệ, thuộc ownership producer | Chốt DSL, owner, test, kế hoạch triển khai |
| **NEGOTIATE** | Schema, status, semantics hoặc SLA chưa thống nhất | Trao đổi ví dụ request/response, sửa DSL theo đồng thuận |
| **PHASE** | Một phần có thể triển khai an toàn trước | Contract riêng cho phần đã hỗ trợ, phần còn lại vẫn proposal |
| **DEFER** | Bị chặn bởi dependency, roadmap hoặc rủi ro | Ghi blocker, owner, điều kiện mở lại và cách consumer chờ |
| **REJECT** | Không thuộc ownership hoặc không thể bảo đảm correctness/security | Nêu lý do + giao diện/kiến trúc thay thế |
| **FIX TEST SETUP** | Implementation có nhưng base class/fixture sai | Sửa setup, chạy lại generated test trước khi đánh dấu verified |

**Không thay đổi sự thật để test xanh.** Ví dụ, đổi yêu cầu reservation thành `GET /inventory/{sku}` không mang lại bảo đảm giữ chỗ atomic. Nếu muốn chia giai đoạn, consumer phải **chấp nhận phạm vi đã thay đổi** và code không được giả định tính năng chưa được cung cấp.


## 8. Chốt acceptance criteria trước khi triển khai

Một hợp đồng HTTP chỉ mô tả một số ví dụ tương tác. Khi producer đồng ý hỗ trợ reservation, hai nhóm cần làm rõ **điều kiện chấp nhận**.

### Happy path

- `POST /api/inventory/reservations` nhận `sku` và `quantity` hợp lệ.
- `quantity` là number dương; producer không dựa vào việc parser tự ép kiểu một chuỗi.
- `Idempotency-Key` được xử lý theo chính sách đã thống nhất.
- Producer trả status `201` và `reservationId` có thể dùng để xác nhận hoặc hủy reservation.
- `reservedQuantity` và `status` có ý nghĩa ổn định đối với consumer.

### Nhánh lỗi

- Nếu số lượng không đủ, hai bên thống nhất status và mã lỗi, ví dụ `409` + `INSUFFICIENT_STOCK`.
- Nếu SKU không tồn tại, trả một mã lỗi phân biệt với tình huống thiếu tồn kho.
- Nếu request body sai schema, trả lỗi validation theo API policy.
- Nếu producer unavailable, consumer phải phân biệt lỗi tạm thời với kết luận “hết hàng”.
- Với retry cùng idempotency key, producer phải tuân thủ semantics đã chốt; không được mặc nhiên tạo hai reservation.

### Giới hạn của contract tests

Contract test có thể xác nhận HTTP method, path, headers, request/response shape và các ví dụ lỗi. Nhưng **tính atomic dưới tải đồng thời**, transaction isolation và hành vi khi database fail thường đòi integration/concurrency tests.

Không ghi “đã hỗ trợ reservation an toàn” chỉ vì một contract test `201` PASS nếu implementation còn có race condition làm oversell.

### Definition of Done đề xuất

~~~text
Contract review: ACCEPTED
Producer implementation: MERGED
Generated contract tests: EXECUTED and PASS
Additional concurrency/idempotency tests: PASS as required
Verified stubs artifact: created from same revision
Consumer Stub Runner tests: PASS
Compatibility review: PASS
Rollout ownership: agreed
~~~

Đây là **checklist quy trình**, không phải các field do Spring Cloud Contract tự đặt.

## 9. Anti-pattern: thay contract cho khớp code chưa có

Giả sử test hiện trả:

~~~text
Expected HTTP status: 201
Actual HTTP status: 404
~~~

**Cách sửa sai:** đổi DSL thành response `404` để test PASS, rồi báo Checkout rằng “contract đã được producer xác nhận”.

Tại sao sai? Vì consumer cần thao tác **giữ chỗ**, còn một response `404` không cung cấp chức năng đó. Việc test xanh sau khi hạ kỳ vọng không biến implementation thành hợp lệ.

Các biến thể khác:

| Thay đổi vội | Vấn đề |
|---|---|
| Xóa assertion `reservationId` | Checkout không có ID để xác nhận/hủy |
| Đổi `quantity` từ number thành string | Phá typed client/deserializer |
| Dùng regex `.*` cho mọi response field | Không phát hiện thiếu dữ liệu có ý nghĩa |
| Bỏ header `Idempotency-Key` | Mất yêu cầu chống xử lý trùng mà consumer cần |
| Chấp nhận status bất kỳ trong `2xx/4xx` | Test không còn bảo vệ flow happy path |
| Sửa mock để trả đúng JSON nhưng không gọi controller thật | Producer verification không kiểm chứng implementation |

**Điều chỉnh contract chỉ hợp lệ khi hai nhóm thống nhất thay đổi yêu cầu**, chứ không phải vì muốn CI xanh.

## 10. Phân biệt proposal test với verified release gate

Có thể duy trì **hai tuyến kiểm chứng** với mục tiêu khác nhau.

| Tuyến | Mục tiêu | Khi generated test của yêu cầu mới đỏ |
|---|---|---|
| **Proposal validation** | Consumer và producer thảo luận API tương lai | Báo **NOT SUPPORTED YET** cùng bằng chứng, tiếp tục review |
| **Producer release verification** | Chứng minh producer đáp ứng các hợp đồng đã cam kết | **Chặn publish/release** |

Proposal có thể nằm trong PR chưa merge, nhánh riêng hoặc artifact CI tạm. Khi chưa chốt phạm vi và chưa triển khai, nó **không nên vô tình trở thành contract được công bố như verified**.

### Về inProgress và ignored

Spring Cloud Contract có các cơ chế liên quan tới contract đang phát triển hoặc được bỏ qua trong một số phiên bản DSL/plugin, và các option như `failOnInProgress`.

Tuy nhiên, **cách một version xử lý việc sinh tests/stubs, skip và build failure cần được xác nhận trong tài liệu/plugin đang sử dụng**. Không dùng `inProgress` như nhãn bảo đảm producer đã hỗ trợ, không dùng `ignored` như đường tắt để biến release thành màu xanh.

Quy tắc vận hành an toàn là:

1. Có **issue/PR theo dõi proposal**, owner và lý do chưa đáp ứng.
2. Không đưa candidate không verified vào release artifact repository.
3. Quality gate phải nhận biết rõ những contract nào đã được cam kết.
4. Khi producer hoàn thành, chạy lại generated producer tests trước khi nâng trạng thái sang verified.

### Vì sao cần tách?

Nếu nhóm gộp mọi DSL đề xuất vào nhánh release, producer có thể luôn đỏ. Kịch bản xấu là sau đó ai đó thêm `skipTests` hoặc bỏ qua toàn bộ contract suite để kịp release, khiến **cả những hợp đồng cũ đang được hỗ trợ cũng mất bảo vệ**.

Tách tuyến proposal giúp giữ feedback sớm mà không phá quality gate của những giao diện đã cam kết.

## 11. Candidate stub cho consumer phát triển trước

Trong lúc Inventory chưa triển khai, Checkout có thể muốn viết HTTP client, DTO và UI. Spring Cloud Contract có thể sinh stub từ DSL, ngay cả khi producer thực tế chưa đáp ứng.

Điều đó có ích **nếu được dán nhãn rõ**:

~~~text
Artifact kind: experimental candidate
Contract revision: proposal-branch@commit-X
Producer verification: FAIL / NOT YET RUN
Eligible for verified release: NO
Allowed use: isolated consumer prototype / diagnostic tests
~~~

Không cho candidate chưa verified cùng version bất biến với stub chính thức. Có thể để ở CI artifacts, repository staging hạn chế quyền hoặc local Maven repository riêng với version/build ID duy nhất.

### Stub Runner kiểm tra điều gì?

Consumer test với Stub Runner chứng minh **consumer có thể gửi request và xử lý response mô phỏng theo DSL**. Nó không chứng minh Inventory production đã có endpoint đó.

Ví dụ skeleton dành cho Spring Boot consumer đã cấu hình Stub Runner dependency:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.5.0-rc.1:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutReservationContractTest {

    @StubRunnerPort("inventory-producer")
    int stubPort;

    @Autowired
    RestClient.Builder restClientBuilder;

    record ReserveRequest(String sku, int quantity) {}

    record ReserveResponse(
        String reservationId,
        String sku,
        int reservedQuantity,
        String status
    ) {}

    @Test
    void readsProposedReservationResponse() {
        RestClient client = restClientBuilder
            .baseUrl("http://localhost:" + stubPort)
            .build();

        ReserveResponse result = client.post()
            .uri("/api/inventory/reservations")
            .header("Idempotency-Key", "checkout-req-1001")
            .body(new ReserveRequest("SKU-101", 2))
            .retrieve()
            .body(ReserveResponse.class);

        assertThat(result.reservationId()).isNotBlank();
        assertThat(result.reservedQuantity()).isEqualTo(2);
        assertThat(result.status()).isEqualTo("ACTIVE");
    }
}
~~~

Ví dụ là **test minh họa có điều kiện**: cần Spring test context, candidate artifact đúng version nằm ở Maven local repo, các dependencies và cấu hình serialization phù hợp. `RestClient` có trong Spring Framework 6.1+, không đại diện cho mọi Spring Boot version.

**Chú ý:** `:0` trong Stub Runner ID yêu cầu cổng động; test phải lấy cổng thực qua `@StubRunnerPort`. Không dùng `localhost:0` làm base URL.

### Kết luận khi consumer test PASS

~~~text
Đúng:
  Checkout client xử lý được response do candidate stub cung cấp.

Sai:
  Inventory Service đã implement và sẽ trả response đó trong production.
~~~

Để kết luận thứ hai cần **generated producer tests PASS trên implementation thực**, cùng artifact/version đã kiểm chứng.

## 12. Nếu producer nhận triển khai, quy trình thế nào?

Một quy trình có thể kiểm toán:

1. Producer xác nhận use case, request/response semantics, error cases và owner.
2. Checkout và Inventory chốt DSL revision cùng acceptance criteria.
3. Producer triển khai controller/publisher, service logic và dữ liệu cần thiết.
4. Base test tạo đúng producer test environment: MockMvc/controller thật, HTTP runtime hoặc messaging binder.
5. Spring Cloud Contract sinh generated tests từ **cùng DSL revision**.
6. Generated tests được **biên dịch, thực thi và PASS**; số test phù hợp kỳ vọng.
7. Các test integration bổ sung về idempotency, concurrency, authorization được chạy nếu cần.
8. Stub artifact được đóng gói từ **cùng revision producer và DSL**.
9. Checkout chạy Stub Runner với **candidate version chính xác**, kiểm tra client/handler thật.
10. Release gate xác nhận tác động tới consumer cũ và kế hoạch rollout.

**Merge code chưa phải Done** nếu tests bị skip hoặc consumer vẫn dùng stub cũ.

### Giữ bản ghi revision

~~~text
Contract source SHA: <contract-sha>
Producer source SHA: <producer-sha>
Producer generated tests: 6 executed / 6 passed
Candidate stub: com.example:inventory-producer:2.5.0-rc.1:stubs
Candidate artifact SHA-256: <digest>
Consumer tests: 4 executed / 4 passed
Release decision: eligible after required review
~~~

Các giá trị trong dấu `<...>` là placeholder. Chúng phải được CI ghi lại, không được tự gán khi chưa có bằng chứng.

## 13. Nếu producer chỉ làm được một phần

Giả sử Inventory có thể tạo reservation nhưng chưa hỗ trợ **Idempotency-Key**.

| Quyết định | Điều kiện | Trách nhiệm thông báo |
|---|---|---|
| Giữ yêu cầu và chờ | Idempotency bắt buộc để tránh tạo reservation trùng | Producer chưa thể cam kết giao diện |
| Chia giai đoạn | Checkout có giải pháp an toàn khác được review | Contract giai đoạn 1 mô tả đúng giới hạn |
| Đổi mô hình | Reservation đồng bộ không phù hợp kiến trúc | Đề xuất command/event với semantics rõ |
| Từ chối một phần | Header/schema không có ý nghĩa theo API policy | Đề xuất quy tắc thay thế |

**Không xóa matcher của Idempotency-Key rồi vẫn ghi “API bảo đảm idempotency”.** Điều đó sai khác giữa contract và hành vi thật, không phải tối ưu test.

Một phân tách hợp đồng hợp lý:

~~~text
stockAvailable        -> verified existing GET
reservationCreated    -> proposed / implementing
reservationNoStock    -> planned error scenario after agreement
reservationCancelled  -> separate interaction when consumer needs it
~~~

Mỗi contract nên đại diện một tình huống rõ; không buộc producer cam kết cả lộ trình tương lai qua một test hiện tại.

## 14. Khi producer hoãn hoặc từ chối

### Hoãn

Một phản hồi đầy đủ nên cho biết:

- **Blocker**: transaction model, database migration, ownership, security hoặc năng lực phát triển.
- **Tác động**: flow Checkout nào không thể bật.
- **Owner**: ai đánh giá và cập nhật.
- **Tiêu chí mở lại**: điều kiện kỹ thuật hoặc quyết định product nào cần đạt.
- **Consumer plan**: feature flag/fallback hoặc alternative đã đồng thuận.
- **Review checkpoint**: nếu chưa có mốc, nêu rõ chưa chốt chứ không bịa deadline.

### Từ chối có lý do

Từ chối request như `POST /api/inventory/reservations` có thể hợp lý nếu reservation thuộc một service khác. Khi đó producer cần cung cấp:

1. Ranh giới ownership chính xác.
2. Rủi ro nếu gắn yêu cầu vào Inventory.
3. API/event thay thế có thể xem xét.
4. Các phần contract cần điều chỉnh.
5. Người phụ trách giúp consumer chuyển dependency.

Từ chối **một giải pháp** không đồng nghĩa phủ nhận **nhu cầu nghiệp vụ**. Cuộc thảo luận phải quay về yêu cầu chống oversell, không chỉ tên endpoint.

## 15. Consumer có thể làm gì trong lúc chờ?

Không nên gửi request mới tới production chỉ vì stub trong test đã trả `201`. Những lựa chọn an toàn:

- **Feature flag** giữ luồng reservation chưa có ở trạng thái tắt.
- **Isolated candidate tests** giúp code client và UI trước.
- **Hiển thị trạng thái an toàn** khi không thể giữ chỗ, thay vì tự coi reservation thành công.
- **API hiện có** chỉ được dùng trong phạm vi bảo đảm thực sự của nó. GET tồn kho không phải atomic hold.
- **Versioned rollout**: producer sẵn sàng trước, consumer bật sau.
- **Fallback có kiểm soát**: không tự tạo `reservationId` giả để truyền xuống các bước thanh toán/hủy.

### Pseudocode rollout

~~~text
if producer capability has been verified and deployed:
    enable Checkout reservation flow
else:
    keep new flow disabled or show safe unavailable state
~~~

Đây là chính sách thiết kế, không phải logic mà Spring Cloud Contract tự cài đặt. Hệ thống thật cần cơ chế capability/configuration phù hợp.

## 16. Bảo vệ các consumer cũ

Một endpoint mới có thể là additive; nhưng sửa API hiện có để phục vụ tương tác mới vẫn có thể phá vỡ consumer cũ.

Response cũ:

~~~json
{"sku":"SKU-101","available":true,"quantity":8}
~~~

Response mới bị đề xuất thay thế:

~~~json
{"sku":"SKU-101","availability":"IN_STOCK","units":8}
~~~

Nếu producer cập nhật code + contract mới đồng thời, generated tests mới có thể PASS. Nhưng Checkout cũ vẫn dùng `available` và `quantity` nên có thể lỗi.

| Thay đổi | Rủi ro | Phản hồi phù hợp |
|---|---|---|
| Thêm endpoint, giữ endpoint cũ | Thường thấp, vẫn cần rollout có thứ tự | Producer deploy trước, consumer bật sau |
| Thêm field response | Phụ thuộc client có chịu field lạ | Chạy consumer compatibility tests |
| Xóa/đổi tên field | Breaking | Migration/giữ field cũ/version mới |
| Đổi number thành string | Breaking với typed clients | Giữ schema hoặc versioning |
| Đổi status/error body | Có thể phá nhánh lỗi | Contract riêng cho error cases |
| Thêm required header | Có thể phá request của consumer cũ | Transition policy/versioning |
| Đổi message destination/event schema | Có thể làm listener ngừng nhận | Dual publish/migration khi phù hợp |

Không mặc định rằng một consumer đề xuất sửa giao diện có quyền quyết định thay cho tất cả các consumer khác. Cần xác định **danh sách consumer đang triển khai và field họ phụ thuộc**.


## 17. Phản hồi cho một message contract chưa được producer hỗ trợ

Đề xuất tương tác mới không chỉ là HTTP. Giả sử Checkout muốn nhận sự kiện **StockReserved** khi Inventory xác nhận giữ chỗ.

Groovy DSL minh họa:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stock_reserved'

    input {
        triggeredBy('emitStockReserved()')
    }

    outputMessage {
        sentTo('stock-reservations')
        body(
            eventType: 'StockReserved',
            reservationId: 'RSV-1001',
            sku: 'SKU-101',
            quantity: 2
        )
        headers {
            messagingContentType(applicationJson())
        }
    }
}
~~~

Trong producer test, base class cần cung cấp method `emitStockReserved()` và messaging adapter/receiver phù hợp để generated test có thể kích hoạt code publisher **thật** và quan sát message.

Nếu producer chưa phát event, có thể nhận:

~~~text
Expected:
  destination = stock-reservations
  eventType = StockReserved
  reservationId = RSV-1001

Actual:
  No matching message received before timeout

Result: FAILED
~~~

### Trước khi kết luận “chưa implement event”

Cần phân biệt:

1. Publisher chưa được triển khai.
2. `triggeredBy` gọi method trong base class nhưng method không kích hoạt producer thật.
3. Test binder/receiver đang nghe sai destination.
4. Broker hoặc routing chưa khởi động đúng.
5. Message được gửi trễ hoặc bị test khác tiêu thụ.
6. Payload/header khác DSL nên receiver không match.

Cách phản hồi là chia rõ **implementation gap** và **test infrastructure gap**, nêu bằng chứng log, destination và message nhận được (nếu có). **Tăng timeout lên rất lớn** không chứng minh publisher đã đúng.

### Consumer StubTrigger chỉ kiểm tra consumer

Checkout có thể dùng `StubTrigger.trigger("stock_reserved")` để phát message mô phỏng và test handler; việc đó không chứng minh Inventory thật đã xuất bản `StockReserved`.

Một message contract chỉ đủ điều kiện đưa vào verified release khi generated producer test chạy với publisher thật và PASS. Producer và consumer còn phải thống nhất **event timing**, correlation, duplicate delivery, schema versioning, ordering và retry/DLQ theo nhu cầu. Những đặc tính giao dịch và tính bền vững của broker cần integration tests phù hợp ngoài contract test cơ bản.

## 18. Quy trình CI hai tuyến: proposal và verified release

Một thiết kế CI có thể phản hồi nhanh mà không làm hỏng release gate:

~~~mermaid
flowchart TD
    A["Consumer contract proposal PR"] --> B["Validate DSL + review scope"]
    B --> C["Optional producer test với proposal"]
    C --> D{"Đã đáp ứng?"}
    D -->|Chưa| E["Feedback: NOT SUPPORTED YET"]
    D -->|Có| F["Candidate ready for full verification"]
    F --> G["Producer release CI"]
    G --> H["Generate + execute committed producer tests"]
    H --> I{"Required producer tests PASS?"}
    I -->|Không| X["Block verified stub publish"]
    I -->|Có| J["Package :stubs from same revision"]
    J --> K["Consumer Stub Runner compatibility tests"]
    K --> L{"Required consumers PASS?"}
    L -->|Không| M["Investigate breaking change"]
    L -->|Có| N["Publish according to release policy"]
~~~

### Proposal CI

Có thể kiểm tra cú pháp DSL, fixtures, test generation và chạy thử against producer hiện tại. Một failure vì endpoint mới chưa có là **feedback** cho quyết định hai nhóm.

Nhưng phải:

- Ghi rõ producer hiện **chưa hỗ trợ**.
- Không biến failure thành success của release gate.
- Không dùng artifact proposal làm version verified.
- Không đánh dấu `PUBLISHED` khi producer test chưa PASS.
- Giữ issue/owner và các câu hỏi chưa thống nhất.

### Release CI

Quality gate khuyến nghị:

~~~text
CAN_PUBLISH_VERIFIED_STUB =
    CONTRACT_FILES_DISCOVERED
    AND GENERATED_PRODUCER_TESTS_EXECUTED
    AND GENERATED_PRODUCER_TESTS_PASSED
    AND REQUIRED_BUILD_CHECKS_PASSED
    AND STUB_MATCHES_VERIFIED_REVISION
    AND RELEASE_AUTHORIZED
~~~

Nếu tổ chức yêu cầu consumer compatibility trước release, bổ sung điều kiện consumer tests PASS.

**Không coi “build SUCCESS, 0 generated contract tests” là bằng chứng producer đạt.** Không bật `-DskipTests`, `-Dmaven.test.skip=true` hoặc Gradle `-x contractTest` ở đường phát hành chính thức.

Lệnh tham khảo trong module đã cấu hình plugin:

~~~bash
# Maven producer:
./mvnw -B -ntp clean verify

# Gradle producer, nếu plugin có task này:
./gradlew :inventory-producer:contractTest
~~~

Các lệnh không được chạy trong bài học này; cần kiểm tra plugin version, task graph, reports và các test bị skip trong dự án thật.

## 19. Version và artifact: giao diện mới được công bố lúc nào?

Khi producer đã triển khai và contract test PASS, có thể tạo:

~~~text
Producer source SHA: <producer-sha>
Contract source SHA: <contract-sha>
Generated producer tests: 6 executed / 6 passed

Candidate stub:
  com.example:inventory-producer:2.5.0-rc.1:stubs
  sha256: <artifact-digest>

Checkout consumer:
  Stub Runner loaded: inventory-producer:2.5.0-rc.1:stubs
  consumer tests: 4 executed / 4 passed
~~~

Thông tin trong dấu `<...>` là placeholder, cần được CI điền từ kết quả thực.

### Candidate và published stub

| Thuộc tính | Candidate dùng nội bộ CI | Published verified stub |
|---|---|---|
| Mục đích | Thử nghiệm thay đổi/compatibility | Consumer khác tải để test |
| Tình trạng producer | Có thể là proposal hoặc đã test, phải dán nhãn rõ | Producer contract tests bắt buộc PASS |
| Phạm vi | Branch/job/staging có kiểm soát | Repository được phép phát hành |
| Version | Unique build/commit ID | Tọa độ/version truy vết được và nên bất biến |
| Quyền publish | Test job không cần release secrets | Job release được bảo vệ |
| Bản ghi cần giữ | Contract revision, test results | Producer source SHA, stub digest, release decision |

### Cache và `latest`

Một consumer test có thể vẫn xanh nếu nó tải stub cũ dù producer vừa đổi contract. Không dùng alias `latest` hoặc mutable SNAPSHOT làm bằng chứng chắc chắn về một proposal. Ghim artifact version, log resolved coordinates và cân nhắc lưu checksum/digest.

Nếu CI ở hai repository riêng, truyền **chính candidate artifact** (hoặc version bất biến) từ producer job sang consumer job. Không xác minh producer ở commit A rồi publish stub được rebuild không kiểm soát từ commit B.

## 20. Luồng bàn giao giữa Checkout và Inventory

~~~mermaid
sequenceDiagram
    participant C as Checkout team
    participant R as Contract PR / issue
    participant P as Inventory team
    participant CI as Producer CI
    participant A as Artifact repository
    participant T as Consumer CI
    C->>R: Đề xuất POST /reservations
    R->>P: Yêu cầu review
    P->>CI: Run generated producer tests
    CI-->>P: FAIL 404 instead of 201
    P->>R: Evidence + ACCEPTED_PENDING + owner
    P->>P: Implement route/idempotency/error cases
    P->>CI: Rerun producer tests
    CI-->>P: PASS
    P->>A: Publish candidate stub đúng revision
    A->>T: Stub Runner load exact version
    T-->>C: Consumer tests PASS hoặc feedback
    C->>R: Xác nhận readiness/compatibility
~~~

`ACCEPTED_PENDING` là nhãn **phối hợp nội bộ được đề xuất**, không phải trạng thái mặc định Spring Cloud Contract.

### Một bảng quyết định giúp tránh bỏ sót

| Quyết định | Owner | Bằng chứng | Điều kiện đóng |
|---|---|---|---|
| Accept request/schema | Hai nhóm | DSL review/acceptance criteria | Contract được chốt |
| Implement reservation | Inventory | Code PR + producer tests | Generated tests PASS |
| Handle retry/idempotency | Inventory và Checkout | Test integration + agreed semantics | Không tạo double reservation |
| Publish candidate verified stub | Inventory CI | Test report + digest | Artifact cùng revision |
| Test consumer behavior | Checkout CI | Stub Runner results | Client/flow PASS |
| Enable feature | Checkout/product + Inventory readiness | Deployment/version confirmation | Rollout an toàn |

Những mốc và owner thực phải được ghi trong issue/PR của dự án; không tự suy rằng một nhóm đã chấp thuận chỉ vì tên nhóm xuất hiện trong ví dụ.

## 21. Khi đỏ là lỗi test setup, cách phản hồi phải khác

Giả sử Inventory thực ra có endpoint reservation, nhưng generated test base class chỉ đăng ký controller cũ:

~~~text
Production:
  POST /api/inventory/reservations exists

Test setup:
  MockMvc standaloneSetup(OldInventoryController)
  ReservationController not registered

Observed:
  HTTP 404
~~~

**Không được** kết luận “Inventory chưa hỗ trợ route” khi test setup chưa gọi đúng implementation.

Hướng xử lý:

- Kiểm tra `baseClassForTests`/`baseClassMappings`.
- Kiểm tra application context, MockMvc setup hoặc test mode.
- Xác minh authentication/security setup.
- Kiểm tra fixture: `SKU-101` có tồn tại trong test environment không?
- Kiểm tra generated test gửi URL/header/body như dự kiến.
- Sửa setup, **chạy lại test**, rồi mới đánh dấu verified.

Tương tự, producer trả `409` vì fixture hết hàng có thể là **đúng nghiệp vụ nhưng sai fixture happy path**, không phải yêu cầu giữ chỗ bị từ chối. Feedback phải dựa trên request và trạng thái dữ liệu thực trong test.

## 22. Anti-pattern thường gặp trong phản hồi liên nhóm

| Anti-pattern | Vì sao nguy hiểm | Cách thay thế |
|---|---|---|
| “Consumer Stub Runner PASS, vậy producer đã hỗ trợ” | Stub không chạy code producer thật | Producer verification PASS |
| Xóa test đỏ mà không ghi issue | Mất dấu yêu cầu chưa hoàn thành | Giữ proposal, tracking và owner |
| Đổi status 201 thành 404 để xanh | Không còn đúng use case | Đàm phán hoặc triển khai hành vi |
| Xóa header/field quan trọng khỏi DSL | Consumer không còn bảo đảm cần thiết | Review semantics giữa hai nhóm |
| Merge proposal vào verified contracts rồi skip toàn bộ tests | Release gate bị vô hiệu hóa | Tách tuyến proposal và verified |
| Dùng `inProgress`/`ignored` không rõ semantics | Có thể che failure | Xác minh plugin version và governance |
| Publish candidate chưa đạt lên release repo | Consumer có thể nhầm là verified | Staging tách biệt và nhãn unverified |
| Dùng `latest`/cùng SNAPSHOT mutable | Không chứng minh đã test đúng bytes | Version + digest/commit |
| Trả lời “sẽ sớm làm” không có owner | Consumer không lập kế hoạch được | Issue/decision/next review |
| Producer đáp ứng new schema bằng cách xóa old schema | Có thể breaking consumer cũ | Compatibility review và migration |
| Consumer bật feature trước producer deploy | Gọi endpoint chưa tồn tại | Producer-first rollout và feature flag |
| Chỉ test HTTP happy path | Thiếu lỗi/side effect quan trọng | Error contracts + integration tests |
| Coi mọi HTTP 404 là đúng `NOT_FOUND` business case | Có thể là unmatched WireMock request | Assert body/error code và request |
| Gửi log thiếu commit và contract version | Khó tái lập | Expected/actual + source SHA + test name |
| Đổ lỗi cho producer khi base test sai | Làm chậm xử lý và gây tranh cãi | Triage test setup trước khi kết luận |

### Khi hai bên bất đồng

Không quyết định bằng cách “bên nào có test xanh hơn”. Hãy bắt đầu từ use case và bảo đảm nghiệp vụ, dùng ví dụ request/response hoặc event payload cụ thể, nêu lựa chọn và trade-off, ghi owner quyết định. Nếu chưa thống nhất, **chưa có cam kết hỗ trợ**.

## 23. Bài thực hành 1: trả lời khi endpoint chưa tồn tại

### Đề bài

Checkout gửi contract:

~~~text
POST /api/inventory/reservations
body = {"sku":"SKU-101","quantity":2}
expected = HTTP 201 + reservationId
~~~

Generated producer test trả:

~~~text
actual = HTTP 404
~~~

Inventory chưa có kế hoạch triển khai reservation trong release hiện tại.

**Câu 1. Có nên sửa expected 201 thành 404 cho test xanh?**

Không. Điều đó xóa hành vi consumer đang yêu cầu. Giữ proposal ngoài verified release, ghi rõ producer chưa hỗ trợ và thảo luận lựa chọn.

**Câu 2. Phản hồi nên chứa những gì?**

Contract path/version, producer SHA, generated test name, expected/actual, nguyên nhân đã xác minh, quyết định accept/defer/reject, owner, blocker, hành động tiếp theo và điều kiện Done.

**Câu 3. Checkout có được dùng candidate stub để viết client trước không?**

Có, trong **môi trường thử nghiệm cô lập** và gắn nhãn unverified. Không dùng kết quả đó làm bằng chứng Inventory đã triển khai hoặc bật feature production.

**Câu 4. Nếu producer chỉ đề nghị tiếp tục dùng GET tồn kho?**

GET không mang bảo đảm giữ chỗ atomic. Hai nhóm cần làm rõ liệu phương án này thật sự đáp ứng nhu cầu chống oversell hay cần đổi kiến trúc.

### Mẫu phản hồi tham khảo

> Inventory đã chạy generated contract test cho `POST /api/inventory/reservations` và nhận **404** thay vì **201**. Endpoint hiện chưa được hỗ trợ trong release đang xét. Chúng tôi đề nghị giữ proposal ở trạng thái chưa verified để làm rõ idempotency, expiration và quy tắc không đủ hàng; quyết định triển khai và mốc sẽ được cập nhật sau khi đánh giá thiết kế. Checkout có thể thử candidate stub trong test, nhưng cần giữ feature flag tắt cho tới khi producer tests và consumer compatibility cùng đạt.

## 24. Bài thực hành 2: consumer muốn message mới

### Đề bài

Checkout muốn nhận `StockReserved` event trên destination `stock-reservations`. DSL dùng `label 'stock_reserved'` và `triggeredBy('emitStockReserved()')`. Generated producer test timeout.

Hãy kiểm tra:

1. Publisher đã được triển khai chưa?
2. Trigger method có gọi producer thật không?
3. Binder/receiver lắng nghe đúng destination không?
4. Payload/header có khớp contract không?
5. Event có phát sau transaction commit không?
6. Consumer test có chờ handler cập nhật state với timeout hữu hạn không?

**Câu hỏi chính:** Stub Runner `StubTrigger` test PASS có đủ để producer publish verified message stub không?

**Không.** StubTrigger giúp consumer nhận message giả lập từ DSL, còn producer cần generated message test thực sự quan sát publisher và PASS.

### Bài nâng cao: khi producer chỉ chấp nhận một phần

Producer nhận làm API reservation nhưng từ chối header `Idempotency-Key` trong giai đoạn đầu.

Hãy tạo một quyết định có thể review:

- Consumer có thật sự chạy an toàn nếu không có idempotency không?
- Có alternative nào bảo đảm không tạo reservation trùng?
- Contract v1 sẽ mô tả điều gì và điều gì chưa hỗ trợ?
- Feature flag, retry policy và test nào cần bổ sung?
- Khi nào giai đoạn 2 được xem là verified?

Không tự đổi DSL rồi coi consumer đã chấp nhận.

## 25. Checklist trước khi phản hồi consumer

- [ ] Đã hiểu use case, không chỉ tên URL hoặc event.
- [ ] Đã xác định contract revision và nhóm đề xuất.
- [ ] Đã đọc generated producer test và expected/actual.
- [ ] Đã phân biệt implementation gap với test setup/fixture/broker failure.
- [ ] Đã phản hồi producer hỗ trợ tương tác trong phiên bản nào, nếu có.
- [ ] Đã chọn accept/negotiate/phase/defer/reject hoặc điều tra setup.
- [ ] Đã ghi lý do, owner và bước tiếp theo.
- [ ] Các câu hỏi semantics còn mở được liệt kê rõ.
- [ ] Nếu chưa có mốc phát hành, không tự hứa.
- [ ] Proposal chưa supported được giữ tách khỏi verified release.
- [ ] Candidate stubs nếu có mang nhãn unverified và version riêng.
- [ ] Không publish verified stub khi generated producer tests fail, skip hoặc chạy 0.
- [ ] Consumer có feature flag/fallback an toàn trong thời gian chờ.
- [ ] HTTP request/status/body/header và messaging destination/payload được review.
- [ ] Các bảo đảm ngoài contract như concurrency/idempotency có test bổ sung.
- [ ] Generated test gọi producer implementation thực, không phải fake endpoint.
- [ ] Stub artifact cùng revision đã verify và có tọa độ/digest rõ.
- [ ] Consumer tests dùng đúng candidate version qua Stub Runner.
- [ ] Các consumer cũ được review để tránh breaking change.
- [ ] Quyết định và trạng thái được thông báo lại cho nhóm phụ thuộc.

## 26. Ghi nhớ và tài liệu tham khảo

**Phản hồi khi producer chưa đáp ứng tương tác mới** là một phần quan trọng của consumer-driven contract testing. Một generated producer test đỏ có thể là tín hiệu chính xác rằng contract do consumer đề xuất **chưa được producer triển khai**, hoặc đang gặp lỗi setup cần điều tra. Thay vì sửa matcher cho xanh, xóa test hoặc publish stub chưa kiểm chứng, các nhóm cần biến kết quả đó thành một **quyết định rõ ràng, có bằng chứng và owner**.

Hãy phân biệt **proposed**, **accepted**, **implemented**, **verified** và **published**. Candidate stub có thể giúp consumer phát triển sớm nhưng không thay thế producer verification. Release CI phải bảo vệ mọi contract đã cam kết, còn consumer CI nên dùng đúng verified stub revision.

### Tài liệu tham khảo

- [Spring Cloud Contract — Reference](https://docs.spring.io/spring-cloud-contract/reference/): mô hình producer/consumer, Groovy/YAML DSL, Verifier và Stub Runner.
- [Spring Cloud Contract — Consumer Driven Contracts](https://docs.spring.io/spring-cloud-contract/reference/using/cdc.html): vai trò đề xuất contract và kiểm chứng.
- [Spring Cloud Contract — CDC with External Repository](https://docs.spring.io/spring-cloud-contract/reference/using/cdc-external-repo.html): phối hợp consumer và producer qua repository hợp đồng.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): sinh producer tests, build lifecycle và đóng gói stubs.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): task `contractTest` và tích hợp build.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): consumer kiểm tra với producer stub artifact.
- [Martin Fowler — Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html): cách dùng yêu cầu consumer để xác lập cam kết giao diện.

**Kết luận thực hành:** một phản hồi tốt không dừng ở “test đang đỏ”. Nó phải nói rõ **consumer cần gì, producer hiện chưa đáp ứng phần nào, bằng chứng là gì, quyết định của hai nhóm ra sao và điều kiện nào biến proposal thành verified contract**. Đó là cách phối hợp giúp Spring Cloud Contract phát hiện sự không tương thích sớm mà vẫn giữ được độ tin cậy của CI và artifact đã công bố.
