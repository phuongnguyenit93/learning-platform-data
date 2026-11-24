# Quy trình đọc hợp đồng, generated test, mapping và request thực tế

## 1. Tại sao phải đọc đủ bốn lớp thay vì chỉ nhìn dòng test FAIL?

Trong **Spring Cloud Contract (SCC)**, producer và consumer mô tả giao tiếp HTTP hoặc message bằng **Groovy/YAML DSL**. Từ hợp đồng, Contract Verifier sinh **producer verification tests** để kiểm tra implementation cung cấp thật, đồng thời sinh **stub mappings** có thể đóng gói thành JAR và phục vụ qua **Stub Runner/WireMock**. Consumer dùng stubs để kiểm tra client hoặc handler trước khi các dịch vụ triển khai chung.

Khi một test thất bại, nguyên nhân có thể xuất hiện ở bất cứ mắt xích nào:

- Contract viết sai method, URL, body, matcher hoặc response status.
- Contract đúng nhưng generated test sử dụng base class/test mode không kết nối tới producer thật.
- Generated test đã cũ hoặc không được chạy.
- Generated mapping không phản ánh những ràng buộc người viết nghĩ rằng có trong DSL.
- Stubs JAR cũ được Stub Runner nạp qua LOCAL/REMOTE repository.
- Client consumer gửi một request khác so với request mà developer tưởng đã gửi.
- WireMock có mapping khác với độ ưu tiên cao hơn, hoặc một fallback che unmatched request.
- Response đến từ server/port khác, không phải instance chứa candidate stubs.
- Consumer xử lý response sai vì deserializer, error mapping hoặc business logic.

Vì thế, câu hỏi “**Contract sai hay code sai?**” thường chưa đủ. Cần một **quy trình đọc từ nguồn thỏa thuận đến bytes/request thực tế**.

Bài thuộc chương **Chẩn đoán sự cố** và hướng dẫn từng bước cách kiểm tra bốn lớp cốt lõi:

~~~text
[1] Contract DSL
      ↓ generation
[2] Generated producer test
      ↓ assertion với producer implementation thật
[3] Generated WireMock mapping + stubs artifact
      ↓ resolution / Stub Runner
[4] Request thực tế của consumer và response nhận được
~~~

Trong chẩn đoán, **không được mặc định bốn lớp ấy dùng cùng một revision**. Phải chứng minh quan hệ giữa chúng bằng file path, commit, version và artifact digest.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Đọc một hợp đồng Groovy/YAML để chỉ ra chính xác **request được chấp nhận** và **response được cam kết**.
2. Đọc generated producer tests để biết **assertions nào thực sự được thực thi**.
3. Mở generated WireMock mappings và stubs JAR để xác nhận method/path/headers/bodyPatterns, response và priority.
4. Thu **raw request thực tế** của consumer thay vì suy đoán từ code.
5. Dùng WireMock request journal và near-miss diagnostics để tách **unmatched request** khỏi **business 404**.
6. Phân biệt lỗi producer, lỗi generation/configuration, lỗi package/cache, lỗi consumer và lỗi test harness.
7. Liên kết log giữa CI jobs bằng contract revision, producer commit, candidate stubs version và checksum.
8. Tạo negative/mutation tests để chắc rằng một thay đổi API không tương thích **làm test đỏ**.
9. Ghi báo cáo sự cố có bằng chứng và sửa tại đúng lớp, tránh nới matcher hoặc mock để làm build xanh.

## 2. Nguyên tắc điều tra: từ bằng chứng gần nguồn đến hành vi thực

Một pipeline có thể có hai kiểu test hoàn toàn khác nhau:

| Kiểm tra | Input quan trọng | Thực thi đối tượng nào? | Khẳng định được gì? |
|---|---|---|---|
| **Producer contract verification** | Contract DSL → generated test | Controller/service/message producer **thật** | Implementation đáp ứng các behavior được sinh thành assertions |
| **Consumer stub testing** | Contract → generated stubs JAR → WireMock | HTTP client/message handler **thật** của consumer | Consumer hiểu những stub scenarios đã được nạp |
| **Integration/E2E** | Môi trường nhiều dịch vụ thật | Producer, consumer, network, DB, broker | Tích hợp trong phạm vi môi trường thử |

Không được lấy consumer stub PASS để kết luận producer implementation đúng: WireMock không gọi implementation producer. Cũng không được lấy producer test PASS để kết luận consumer cũ hiểu response mới.

**Thứ tự điều tra gợi ý:**

1. Xác định **test thất bại ở đâu**: producer verification, consumer/Stub Runner, CI artifact resolution hay môi trường thật.
2. Chốt **candidate identity** và bốn loại bằng chứng.
3. Đọc contract source.
4. Đọc generated producer test và **test execution report**.
5. Đọc generated stub mapping và JAR mà consumer thực sự tải.
6. Thu raw request/response từ đúng server instance.
7. So từng trường method → URL → query → headers → body → response → deserialization.
8. Tạo một phép thử đối chứng, sửa **lớp đầu tiên sai** và chạy lại đúng phạm vi.
9. Cập nhật CI/trace để tránh tái diễn.

Đây là một **quy trình chẩn đoán**, không phải thứ tự runtime của tất cả công cụ. Với lỗi consumer cụ thể, có thể bắt đầu bằng request journal để thu chứng cứ nhanh, nhưng khi kết luận vẫn phải nối về contract và artifact.

## 3. Ví dụ xuyên suốt: Checkout gọi Reservation Service

Giả sử Checkout là **consumer**, Reservation Service là **producer**. Hợp đồng yêu cầu:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json
Accept: application/json
X-Request-Id: req-1001

{
  "sku": "SKU-123",
  "quantity": 2
}
~~~

Response được cam kết cho fixture có đủ tồn kho:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "reservationId": "R-1001",
  "status": "RESERVED",
  "sku": "SKU-123",
  "quantity": 2
}
~~~

Một bug trong consumer có thể làm request thực thành:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "productCode": "SKU-123",
  "quantity": "2"
}
~~~

Khác biệt gồm:

- Thiếu `X-Request-Id` nếu header được hợp đồng yêu cầu.
- `sku` bị đổi tên thành `productCode`.
- `quantity` từ JSON number chuyển thành JSON string.
- URL, method và content type vẫn đúng.

Một mapping WireMock chỉ match `method+path` có thể trả 201 cho **cả hai request**. Vì thế status 201 **không đủ** chứng minh client đã gửi đúng contract.

## 4. Bảng bằng chứng cần thu ngay đầu sự cố

| Loại | Câu hỏi | Bằng chứng nên lưu |
|---|---|---|
| **Contract source** | Scenario, revision nào? | Full path, Git commit/contract artifact, DSL snippet |
| **Generated test** | Assert method, body, status, headers nào? | Java source đã sinh, test report, test count |
| **Generated mapping** | WireMock match những gì? | JSON mapping đúng candidate, body files, mapping ID |
| **Stubs artifact** | Stub Runner thực tế đã resolve build nào? | Group/artifact/version/classifier, JAR checksum, timestamp |
| **HTTP request** | Client gửi bytes nào tới server nào? | Method, URL, headers đã che secrets, raw JSON body |
| **HTTP response** | Server trả status/header/body nào? | Raw HTTP response và mapping name/ID nếu có |
| **Test runtime** | Base test, Stub Runner, WireMock được cấu hình ra sao? | Test mode, ports, startup log, extension versions |
| **Consumer assertion** | Test chứng minh behavior gì? | Assertions, deserializer/error mapper, result |
| **CI state** | Có skip, stale cache hay khác build không? | Job IDs, timestamps, executed test counts |

**Không bắt đầu bằng cách xóa toàn bộ cache.** Nếu URL thực sai nhưng mapping chính xác, việc refresh Maven local repository không giải quyết lỗi.

## 5. Đọc contract DSL: thứ tự kiểm tra từ ngoài vào trong

Khi mở contract Groovy/YAML, đọc theo thứ tự:

1. **Scenario identity:** description/name/label và source path, có đúng testcase đang fail không?
2. **Request method:** GET, POST, PUT, PATCH, DELETE; có khác code consumer không?
3. **URL:** exact URL hay regex/path pattern, path variables có encode đúng không?
4. **Query params:** tên, kiểu, nhiều giá trị, encoded spaces, optional/required.
5. **Headers:** `Content-Type`, `Accept`, authorization-related placeholders, version header, correlation ID.
6. **Body:** cấu trúc JSON, required fields, data type, null/empty/missing, enum/range.
7. **Request matchers:** equality, regex, JSONPath, type, priority; có matcher quá rộng không?
8. **Response status:** mã HTTP nào được cam kết cho scenario này?
9. **Response headers:** content type, location, retry/correlation headers.
10. **Response body:** JSON schema, dynamic fields, bodyFile reference, error code.
11. **Response matchers:** generated test sẽ so cụ thể gì?
12. **Consumer/producer sides:** có giá trị động hoặc DSL `value(consumer(...), producer(...))` làm hai phía nhận input khác nhau không?

Đặc biệt, **body mẫu không đồng nghĩa mọi generated assertion bắt buộc so toàn bộ body nguyên văn**. Matcher có thể nới một số JSONPath hoặc dùng regex. Phải xem Java test được sinh để biết thực tế.

## 6. Đọc một hợp đồng Groovy cụ thể

Contract minh họa theo cú pháp Groovy SCC:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout tạo reservation cho SKU-123'

    request {
        method POST()
        url '/api/reservations'

        headers {
            contentType(applicationJson())
            header('Accept', 'application/json')
            header('X-Request-Id', 'req-1001')
        }

        body(
            sku: 'SKU-123',
            quantity: 2
        )
    }

    response {
        status CREATED()

        headers {
            contentType(applicationJson())
        }

        body(
            reservationId: 'R-1001',
            status: 'RESERVED',
            sku: 'SKU-123',
            quantity: 2
        )
    }
}
~~~

Hợp đồng này mô tả một scenario **cố định**. Nếu production business cho phép mọi SKU, cần thêm scenarios/matchers phù hợp; không nên nới mọi trường chỉ để 1 contract đại diện cho toàn bộ miền.

**Việc phải xác minh:** plugin version có hỗ trợ DSL/hàm `CREATED()`/`contentType(applicationJson())` và cách generator dịch request header/body thành test/stub hay không. Các ví dụ trong bài không phải generated output lấy từ một build thực.

### Cặp yêu cầu và hệ quả

| Contract | Producer test cần thực hiện | Consumer stub cần nhận |
|---|---|---|
| POST | Gửi POST thật qua test adapter | Không nhận nhầm GET |
| `/api/reservations` | Gửi đúng path | Chỉ match path/pattern đã định |
| JSON body `sku`, `quantity` | Gửi fixture hợp lệ | Phân biệt body sai nếu mapping đã ràng buộc |
| Header `X-Request-Id` | Test setup gửi header | Yêu cầu header nếu contract/pattern bảo vệ |
| Response 201 | Assert 201 | Trả 201 theo mapping |
| `status=RESERVED` | Assert giá trị theo matcher thực | Response giả lập chứa giá trị ấy |

## 7. YAML: đọc cấu trúc như cùng một thỏa thuận

Ví dụ YAML thay thế Groovy cho **cùng scenario**:

~~~yaml
description: Checkout tạo reservation cho SKU-123
name: create_reservation_sku123

request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
    Accept: application/json
    X-Request-Id: req-1001
  body:
    sku: SKU-123
    quantity: 2

response:
  status: 201
  headers:
    Content-Type: application/json
  body:
    reservationId: R-1001
    status: RESERVED
    sku: SKU-123
    quantity: 2
~~~

**Không cần cùng lưu cả Groovy và YAML cho một scenario**, vì có thể sinh hai tests/mappings trùng nhau. Dùng một dạng chính mà nhóm quản trị.

Khi YAML parser không sinh test như mong đợi, kiểm indentation, key names và matcher syntax của **SCC version cụ thể**. Đừng sửa YAML theo cú pháp WireMock JSON: YAML ở đây là **contract DSL**, còn WireMock JSON là **mapping đầu ra**.

## 8. Đọc matcher trước khi kết luận “response sai mà test vẫn xanh”

Một contract có thể chứa:

~~~groovy
response {
    status CREATED()
    body(
        reservationId: 'R-1001',
        status: 'RESERVED',
        sku: 'SKU-123',
        quantity: 2
    )
    bodyMatchers {
        jsonPath('$.reservationId', byRegex('R-[0-9]+'))
        jsonPath('$.status', byType())
        jsonPath('$.sku', byType())
        jsonPath('$.quantity', byType())
    }
}
~~~

Trong scenario này, `status` và `sku` chỉ được kiểm kiểu. Response:

~~~json
{
  "reservationId": "R-9999",
  "status": "FAILED",
  "sku": "SKU-WRONG",
  "quantity": -100
}
~~~

có thể thỏa phần lớn matcher kiểu/regex dù nghiệp vụ sai.

Bốn câu hỏi chẩn đoán:

1. Field này có **giá trị bất biến** theo fixture không?
2. Một regex chỉ kiểm format có bỏ qua quan hệ request/response không?
3. JSON number/string/boolean có bị deserializer ép kiểu không?
4. Có contract riêng cho status lỗi/boundary mà consumer phụ thuộc không?

**Khắc phục tại nguồn:** sửa `bodyMatchers`/scenarios trong contract để bảo vệ đúng invariants, sinh lại producer test và mapping; **không thêm assertion tạm ở consumer để che một producer contract yếu**.

## 9. Cú pháp dynamic values: xác định phía producer và consumer

Khi response có dữ liệu động như ID hoặc timestamp, SCC có các cách diễn đạt giá trị khác nhau giữa **test producer** và **stub consumer**, tùy Groovy/YAML DSL version.

Ví dụ tư duy:

~~~text
Producer thực:
  trả reservationId bất kỳ theo format R-[0-9]+

Consumer stub:
  trả reservationId mẫu R-1001 để test có thể tái lập
~~~

Điều cần đọc không chỉ là `body()`, mà còn `value(...)`, `consumer(...)`, `producer(...)`, regular expressions, `byRegex` và `byCommand` nếu contract dùng chúng.

Lỗi dễ gặp:

- Giá trị dành cho stub lại được dùng như equality expectation trên producer, gây false FAIL.
- Giá trị dành cho producer được sinh ngẫu nhiên vào stub khiến consumer test flaky.
- Regex được viết quá rộng, ví dụ `.*`, làm lọt enum/status sai.
- Test mong exact ID nhưng producer có quyền sinh ID mới hợp lệ.
- Một dynamic field bị match trong response, nhưng consumer vẫn assert một ID sample cố định không thuộc contract.

**Không tự phỏng đoán direction của `value` trong một DSL version lạ**; xác minh ở hai đầu ra **generated Java test và WireMock JSON mapping**.

## 10. Generated producer test nằm ở đâu?

SCC Maven/Gradle plugin có thể sinh Java test sources, thông thường dưới các thư mục **build output** phụ thuộc plugin version và cấu hình:

~~~text
Producer Maven (ví dụ đường dẫn thường gặp):
  target/generated-test-sources/contracts/...

Producer Gradle (ví dụ đường dẫn thường gặp):
  build/generated-test-sources/contracts/...
  hoặc build/generated-test-sources/...
~~~

**Đây là đường dẫn minh họa, không phải chuẩn cứng cho mọi build.** Khi debug thật, dùng **plugin task logs/generated test compile inputs** để xác định output directory, và đọc file test được tạo cho **đúng contract name/scenario**.

Nếu không tìm thấy test:

- Contract files có được discovery không?
- `contractsDirectory` có trỏ đúng module/source không?
- Plugin được áp vào **producer module** nào?
- Task/goal generate tests có thật sự chạy không?
- Generated source có compile và được test runner discover không?
- Có skip flags, naming patterns hoặc JUnit mismatch không?

Đừng suy ra “không có generated test” chỉ bằng cách xem một thư mục mặc định; output directory có thể đã được cấu hình lại.

## 11. Đọc generated test: tìm request setup và response assertions

Ví dụ **pseudocode Java định hướng đọc**, không phải source do một phiên bản SCC cụ thể sinh:

~~~java
@Test
void shouldCreateReservation() {
    // Test adapter có thể là RestAssured, MockMvc, WebTestClient.
    HttpResponse result = testClient.post("/api/reservations")
        .header("Content-Type", "application/json")
        .header("Accept", "application/json")
        .header("X-Request-Id", "req-1001")
        .json("""
            {"sku":"SKU-123","quantity":2}
            """);

    assertThat(result.status()).isEqualTo(201);
    assertThat(result.header("Content-Type"))
        .contains("application/json");
    assertThat(result.json("$.reservationId"))
        .isEqualTo("R-1001");
    assertThat(result.json("$.status"))
        .isEqualTo("RESERVED");
    assertThat(result.json("$.sku"))
        .isEqualTo("SKU-123");
    assertThat(result.json("$.quantity"))
        .isEqualTo(2);
}
~~~

Trong file generated **thực tế**, tìm:

1. Tên test method/class liên hệ contract nào?
2. Request adapter có gọi app context, real HTTP server, MockMvc hay mock?
3. Method/path/header/body được serialize ra sao?
4. Response status assertion là exact hay range?
5. JSON body assertions là equality, regex, type hoặc custom command?
6. Có assertion kiểm toàn bộ response, hay chỉ vài JSONPath?
7. Có assertions cho error scenarios riêng chưa?
8. Test base class nào được kế thừa?
9. Có test count/execution report chứng minh method đã chạy chưa?

**Phân biệt generated test source tồn tại và executed test PASS.** Code đã sinh nhưng không được JUnit/Surefire/Gradle chạy không tạo bằng chứng producer thực thi đúng contract.

## 12. Generated test “đúng cú pháp” nhưng gọi nhầm implementation

Với Spring MVC, một base test kiểu:

~~~java
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class ReservationContractBase {

    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    void setup() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

cho phép generated test đi qua Spring MVC context thật. Nhưng nếu base setup sử dụng:

~~~java
// Phản ví dụ: fake controller luôn trả expected body.
RestAssuredMockMvc.standaloneSetup(
    new FakeReservationController()
);
~~~

test có thể PASS dù production controller/service đang lỗi.

Khi chẩn đoán:

- Base class có `@SpringBootTest`/`@AutoConfigureMockMvc` và injection đúng không?
- Có `@MockitoBean`/`@MockBean` cho **chính business service cần kiểm chứng** không?
- Nếu mock một external dependency, nó có làm test bỏ qua phần code quan trọng không?
- Producer state/setup có chuẩn bị dữ liệu chứ không trả thẳng expected response không?
- Test setup có chạy trước generated method không?

Một phép thử mutation: cố ý đổi production controller trả 200 thay vì 201. **Generated test phải đỏ**. Nếu vẫn xanh, nghi fake/mocks, test không chạy hoặc assertion không thực sự có mặt.

## 13. Đọc báo cáo thực thi thay vì chỉ đọc “BUILD SUCCESS”

Các trạng thái cần phân biệt:

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| **PASS** | Generated method đã chạy và assertions đạt | Đối chiếu source/commit và test count |
| **FAIL** | Assertion sai với actual response | So expected vs actual tại method/status/body |
| **ERROR** | Setup/context/connection/compile/runtime lỗi | Sửa môi trường/test wiring trước |
| **SKIPPED** | Test bị bỏ qua | Không coi là producer-verified |
| **NOT_RUN** | Không có generated execution report | Kiểm test discovery hoặc pipeline task |
| **STALE** | Report của commit/contract cũ | Không dùng làm bằng chứng cho candidate |
| **ZERO_TESTS** | Không có test được thực thi | Fail closed nếu module bắt buộc có contracts |

Một log như:

~~~text
BUILD SUCCESS
Tests run: 0, Failures: 0, Errors: 0, Skipped: 0
~~~

**không phải bằng chứng verification** nếu producer cần có contract tests.

Trong CI, cần gate executed generated producer tests **lớn hơn 0**, không bị skip và PASS. Không chỉ đếm số unit tests của toàn bộ module.

## 14. Từ generated test sang mapping: hiểu được kiểm tra ở hai phía

Một hợp đồng có thể sinh:

~~~mermaid
flowchart LR
    A["Contract request+response"] --> B["Generated producer test"]
    A --> C["Generated WireMock mapping"]
    B --> D["Gửi request fixture tới producer thật"]
    D --> E["Assert response thực"]
    C --> F["WireMock match consumer request"]
    F --> G["Trả stub response theo contract"]
~~~

Hãy nhớ:

- **Generated producer test:** request có thể được gửi với input cụ thể; response thật được kiểm theo matcher.
- **WireMock mapping:** consumer request phải match những predicate được sinh; sau đó server trả response mẫu (hoặc response templated).
- Nếu request matcher quá lỏng, consumer có thể gửi body sai vẫn nhận success.
- Nếu response matcher quá lỏng, producer có thể trả field sai business semantics nhưng test vẫn PASS.
- Nếu generated mapping khác contract source hiện tại, xem **plugin version, source revision, output/stale build hoặc customization** trước khi sửa client.

Lỗi ở một phía không tự chứng minh phía còn lại lỗi. Hai đầu ra cần được xem **độc lập** và ghim về cùng contract revision.

## 15. Đọc generated WireMock mapping: các trường quan trọng

Một mapping minh họa cho contract POST `/api/reservations`:

~~~json
{
  "name": "create-reservation-sku123",
  "request": {
    "method": "POST",
    "url": "/api/reservations",
    "headers": {
      "Content-Type": {
        "contains": "application/json"
      },
      "X-Request-Id": {
        "equalTo": "req-1001"
      }
    },
    "bodyPatterns": [
      {
        "equalToJson": "{\"sku\":\"SKU-123\",\"quantity\":2}"
      }
    ]
  },
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "reservationId": "R-1001",
      "status": "RESERVED",
      "sku": "SKU-123",
      "quantity": 2
    }
  }
}
~~~

**Đây là WireMock JSON minh họa, không phải khẳng định SCC sinh chính xác mapping đó**. Tùy contract DSL, matcher và WireMock version, mapping có thể dùng `urlPath`, `urlPattern`, `matchesJsonPath`, `equalToJson`, `bodyFileName` hoặc cách đối chiếu khác.

Trong mapping **thực**, hãy đọc theo thứ tự:

| Trường | Câu hỏi |
|---|---|
| `name`/`id` | Có liên quan tới contract scenario và artifact candidate không? |
| `priority` | Có mapping ưu tiên cao hơn đang chiếm request không? |
| `request.method` | Có đúng POST hay bị ANY/GET không? |
| `request.url`/`urlPath`/`urlPattern` | Exact match hay regex; có đúng path không? |
| `request.queryParameters` | Optional/required, encoding và nhiều values? |
| `request.headers` | `Content-Type`, version header, `X-Request-Id` có match? |
| `request.bodyPatterns` | JSON field name, number/string, null/array? |
| `response.status` | 201 hay 200/400/404/503? |
| `response.headers` | Content type, Location, correlation header? |
| `response.body`/`jsonBody`/`bodyFileName` | Body có đúng schema/value không? |
| `scenarioName`/`requiredScenarioState` | Server có đang ở state phù hợp? |
| `transformers`/`metadata` | Có custom extension thay behavior hay nhãn provenance? |

Không nên chỉ mở mapping của một request thành công. Mở **tất cả mappings có khả năng chồng lấn** với method/path đó.

## 16. Vì sao contract đúng mà generated mapping có thể khác kỳ vọng?

Một số nguyên nhân:

1. **Generated từ revision cũ:** build output chưa clean hoặc job dùng source khác.
2. **Cấu hình plugin khác:** contract DSL/extension version quyết định cách chuyển matcher.
3. **Dynamic value direction:** giá trị producer/consumer khác nhau theo DSL.
4. **Body file reference:** mapping chỉ có `bodyFileName`, nội dung nằm trong `__files`.
5. **Custom mapping overlay:** build step sau generation ghi đè hoặc bổ sung mapping.
6. **WireMock extension/template:** effective response bị transformer thay đổi khi runtime.
7. **Nhầm scenario:** tìm file mapping chứa `reservation` nhưng nó là error case hoặc scenario khác.
8. **Nhầm JAR:** local generated file mới, consumer Stub Runner tải JAR cũ.
9. **Cấu hình build module sai:** Gradle/Maven sinh stubs từ module khác hoặc source set khác.

**Không sửa generated mapping trong `target`/`build` để chữa tạm lỗi**. Nếu hành vi thuộc contract, sửa DSL; nếu là customization hợp lệ, lưu source kiểm soát và làm rõ thứ tự merge/version.

## 17. Đọc stubs JAR đã đóng gói, không chỉ file mapping trong workspace

Một artifact thường được phân phối theo tọa độ:

~~~text
groupId:    com.example
artifactId: reservation-service
version:    1.4.0-rc.pr173.a1b2c3d4
classifier: stubs
type:       jar
~~~

Trong môi trường có JDK, lệnh kiểm tra nội dung JAR:

~~~bash
jar tf target/reservation-service-1.4.0-rc.pr173.a1b2c3d4-stubs.jar
~~~

Một cấu trúc minh họa có thể là:

~~~text
META-INF/
  com.example/
    reservation-service/
      1.4.0-rc.pr173.a1b2c3d4/
        contracts/
          reservation/create-reservation.groovy
        mappings/
          create-reservation.json
        __files/
          reservation-body.json
~~~

**Đường dẫn chỉ là ví dụ**, cần xem output thực vì plugin version và `contractsPath`/packaging configuration có thể thay đổi layout.

Nếu mapping chứa:

~~~json
{
  "response": {
    "status": 201,
    "headers": {
      "Content-Type": "application/json"
    },
    "bodyFileName": "reservation-body.json"
  }
}
~~~

thì cần xác nhận `reservation-body.json` có tồn tại trong **JAR thực sự được tải** tại resource root mà WireMock dùng. Không đủ chỉ thấy file đó trong producer working tree.

## 18. Stub Runner LOCAL/REMOTE và bài toán lấy đúng phiên bản

Consumer test có thể cấu hình:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:reservation-service:1.4.0-rc.pr173.a1b2c3d4:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.invalid/repository/candidates"
)
class CheckoutReservationContractTest {
    @Test
    void runsWithStubs() {
        // Dùng ReservationClient thật của Checkout ở port Stub Runner.
    }
}
~~~

`example.invalid` là URL giả. Đây là **khung test minh họa**: cần bổ sung client wiring, method assertions, repository credentials và đối chiếu annotation properties với SCC version.

- **LOCAL:** thường resolve artifact từ Maven local repository; producer `package` không nhất thiết install JAR vào đó.
- **REMOTE:** tải từ Maven-compatible repository, phụ thuộc metadata/mirrors/credentials và proxy cache.
- **Port 18081:** phải khớp URL mà client dùng. Nếu dùng dynamic port, phải inject port được cấp, không hardcode vào client.
- **Consumer mới vs cũ:** cùng request code có thể pass với stub A nhưng fail với stub B; phải biết artifact B tương ứng producer candidate nào.

Một `404 artifact not found` lúc **resolution** khác HTTP 404 do WireMock trả khi request không match. Hãy phân biệt thời điểm lỗi: trước khi server start hay sau khi client gọi server.

## 19. SNAPSHOT, cache và độ mới: kiểm bằng chứng chứ không suy từ tên

Ví dụ producer publish liên tiếp:

~~~text
09:00  reservation-service:1.4.0-SNAPSHOT
       mapping A yêu cầu quantity number

09:30  reservation-service:1.4.0-SNAPSHOT
       mapping B thay đổi header/matcher

09:35  consumer Stub Runner vẫn giữ mapping A từ 09:05
~~~

Tọa độ logical `1.4.0-SNAPSHOT` **có thể chứa nhiều timestamped builds**. Một consumer test đang dùng version string đó chưa chắc đã tải build B.

Để xác minh:

1. Lấy producer commit, contract revision và build/job ID được yêu cầu.
2. Ghi **exact group/artifact/version/classifier**.
3. Với SNAPSHOT, ghi resolved timestamped version hoặc SHA-256 digest.
4. So JAR producer publish với **JAR consumer thực sự tải**.
5. Kiểm repository proxy/mirror/update policy nếu metadata cũ.
6. Kiểm thời điểm Stub Runner/WireMock start: server đã nạp mapping cũ không tự reload chỉ vì có JAR mới.
7. Restart/context refresh đúng quy trình nếu cần, rồi kiểm effective mappings và request journal.
8. Chỉ sau đó mới kết luận consumer test áp dụng cho candidate.

`mvn -U` và Gradle `--refresh-dependencies` có thể tác động resolver tương ứng; **không mặc nhiên làm mới WireMock đang chạy hoặc một resolver khác**.

Trong CI compatibility gate, **candidate version bất biến theo commit** thường dễ tái lập và tránh race hơn SNAPSHOT chung.

## 20. Checksum và manifest kết nối source với runtime

Để đối chiếu file đã đóng gói với file consumer tải, tính SHA-256:

~~~bash
sha256sum reservation-service-1.4.0-rc.pr173.a1b2c3d4-stubs.jar
~~~

Trên PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -Path .\reservation-service-1.4.0-rc.pr173.a1b2c3d4-stubs.jar
~~~

Một report provenance có thể gồm:

~~~yaml
producer:
  service: reservation-service
  commit: a1b2c3d4
contract:
  revision: a1b2c3d4
  source: contracts/reservation/create-reservation.groovy
stubs:
  groupId: com.example
  artifactId: reservation-service
  version: 1.4.0-rc.pr173.a1b2c3d4
  classifier: stubs
  sha256Published: FROM_PRODUCER_CI
  sha256Resolved: FROM_CONSUMER_CI
test:
  consumerCommit: FROM_CHECKOUT_CI
  stubRunnerPort: FROM_RUNTIME
  producerContractsExecuted: FROM_PRODUCER_TEST_REPORT
  consumerTestsExecuted: FROM_CONSUMER_TEST_REPORT
~~~

`FROM_*` là các placeholder cần điền từ hệ thống thật. **Checksum tự nó không chứng minh “mới”**; phải so với checksum kỳ vọng của producer CI đáng tin.

Có thể lưu provenance trong sidecar manifest/attestation liên kết digest. Nếu embed manifest vào JAR, phải **đóng gói manifest trước khi tính digest**, tránh vòng lặp khi ghi checksum của chính JAR vào bên trong nó.

## 21. Khi nào cần mở WireMock request journal?

Nếu consumer nhận response không như mong đợi, journal giúp trả lời **server đã nhận cái gì** thay vì chỉ dựa vào source của client.

Các ví dụ thông tin cần xem:

~~~text
Server: localhost:18081
Request:
  POST /api/reservations
  Content-Type: application/json
  X-Request-Id: <missing>
  Body: {"productCode":"SKU-123","quantity":"2"}

Match:
  matchedStubId: none
  nearestStub:
    create-reservation-sku123
  mismatch:
    header X-Request-Id absent
    body sku missing; quantity wrong type

Response:
  HTTP 404
  body: WireMock diagnostic (not business 404)
~~~

Đây là **log minh họa cách diễn giải**, không phải log nguyên văn của mọi WireMock version.

Một request không match có thể nhận mặc định 404 hoặc một fallback mapping. Vì vậy **HTTP 404 không tự chứng minh business `RESERVATION_NOT_FOUND`**. Dùng status **cộng error code/body** và journal khi cần.

**Lưu ý bảo mật:** request journal có thể chứa authorization tokens, cookies hoặc PII. Che/sanitize trước khi ghi vào CI report, không công bố raw secrets.

## 22. Lấy journal qua Admin API khi có quyền test server

WireMock cung cấp Admin API. Trong một test instance mà bạn có quyền quản lý, có thể truy vấn request journal bằng đường dẫn thường gặp:

~~~bash
curl -sS http://localhost:18081/__admin/requests
~~~

Với một số phiên bản:

~~~bash
curl -sS http://localhost:18081/__admin/requests/unmatched
~~~

Bạn cũng có thể dùng API Java `WireMock.verify(...)` hoặc `findAll(...)` nếu test sở hữu đúng client/server config.

**Đừng giả định đường dẫn Admin API và response JSON giống nhau trong mọi WireMock version.** Xác nhận API tài liệu phù hợp runtime và kiểm việc journal đã bật. Một server có thể tắt journal để giảm bộ nhớ hoặc để bảo vệ dữ liệu.

Quan trọng hơn: Admin API phải trỏ đến **đúng WireMock instance mà Checkout đang gọi**. Khi cùng test có nhiều services/ports, query nhầm server sẽ dẫn tới kết luận “không có request” sai.

## 23. Dùng curl như đối chứng để phân biệt client bug với stub bug

Trong test network, gửi một request hợp lệ trực tiếp:

~~~bash
curl -i -X POST "http://localhost:18081/api/reservations" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "X-Request-Id: req-1001" \
  --data '{"sku":"SKU-123","quantity":2}'
~~~

Nếu WireMock trả response 201 đúng mapping với lệnh trên, nhưng Checkout client nhận 404, cần so **request thực của Checkout** (không phải chỉ source method). Một lỗi có thể là DTO serializer dùng `productCode` hoặc thiếu required header.

Sau đó gửi request cố ý sai:

~~~bash
curl -i -X POST "http://localhost:18081/api/reservations" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: req-1001" \
  --data '{"productCode":"SKU-123","quantity":"2"}'
~~~

Kỳ vọng nếu baseline mapping ràng buộc request body: **không match happy-path 201**. Kết quả cụ thể có thể là 404/unmatched diagnostic hoặc mapping business-validation khác theo contract.

**Nếu cả request sai và request đúng đều nhận 201**, mở `bodyPatterns`, mapping priorities và custom fallback. Có thể matcher quá rộng hoặc một mapping khác trả success.

`curl` là công cụ thăm dò, **không thay thế consumer test thật** vì nó không đi qua serialization/deserialization/error mapping của client.

## 24. So raw request với DTO/client source: đừng đoán kiểu dữ liệu

Giả sử Java DTO:

~~~java
record CreateReservationRequest(
    String productCode,
    String quantity) {
}
~~~

và client:

~~~java
CreateReservationRequest req =
    new CreateReservationRequest("SKU-123", "2");
~~~

Nếu không có annotations/cấu hình serializer đổi field, JSON có thể là:

~~~json
{"productCode":"SKU-123","quantity":"2"}
~~~

Trong khi contract yêu cầu:

~~~json
{"sku":"SKU-123","quantity":2}
~~~

**Lỗi nằm ở client contract**, không phải mapping “quá nghiêm”. Cần sửa DTO/wiring theo thỏa thuận, ví dụ:

~~~java
record CreateReservationRequest(
    String sku,
    int quantity) {
}
~~~

Nhưng vẫn phải kiểm raw JSON thật, vì Jackson `@JsonProperty`, naming strategy, custom serializer, null inclusion, converters, WebClient/Feign/RestClient config và Content-Type có thể ảnh hưởng bytes.

Một số deserializer có thể ép `"2"` thành number; test payload type phải dựa trên **wire format đã cam kết**, không dựa vào việc producer hiện tại tình cờ chấp nhận coercion.

## 25. Header matching: tìm khác biệt không nhìn thấy trong JSON

Một lỗi phổ biến:

~~~text
Contract:
  X-Request-Id: req-1001
  Content-Type: application/json

Consumer request thực:
  X-Request-ID: absent
  Content-Type: text/plain; charset=UTF-8
~~~

**HTTP header names không phân biệt hoa/thường**; `X-Request-Id` và `x-request-id` cùng tên về mặt protocol. Nhưng **thiếu header** hoặc **giá trị sai** là chuyện khác.

Các điểm cần đọc:

- `Content-Type` có media type đúng không; có thêm `charset` được contract/matcher chấp nhận không?
- `Accept` có được gửi và có thể được proxy/client library gán khác không?
- `Authorization` có yêu cầu trong production; test có mock security filter không?
- `X-Request-Id` có được middleware thêm/ghi đè không?
- Request URL có bị redirect dẫn đến mất headers không?
- Content-Encoding/gzip có ảnh hưởng cách WireMock match body không?

Không nên sửa contract header matcher từ exact sang `.*` chỉ để cho request thiếu/sai pass. Nếu requirement là media type `application/json` có thể kèm charset, hãy dùng predicate phản ánh **chính xác phạm vi cho phép**.

## 26. Query params, path variables và encoding

Với URL:

~~~text
/api/items?search=red%20shoe&page=1
~~~

hãy phân biệt:

- URL path `/api/items`;
- Query parameter `search=red shoe` sau khi decode;
- `page` là chuỗi query `"1"` trên wire, mặc dù server có thể parse thành integer;
- Space có thể được encode `%20` hoặc `+` tùy URL encoding rules;
- Multivalue parameter `tag=red&tag=blue` cần contract/matcher thích hợp;
- Path variable chứa slash `/` hoặc Unicode có thể bị encode/normalize theo client/proxy;
- Query ordering thường không phải cam kết trừ khi signature/canonicalization yêu cầu.

Nếu contract dùng `url()` exact string trong khi API thực chỉ quan tâm query semantics, generated mapping có thể quá chặt. Ngược lại, dùng `urlPathPattern` mà không kiểm required query làm stub quá rộng.

**Cách debug:** so raw URL từ journal, sau đó chuyển sang path/query matching phù hợp **với contract**, không chỉnh URL chỉ vì một screenshot trông khác.

## 27. Mapping priority, scenario state và custom transformer

Khi mapping trông đúng nhưng response không đúng, xem các trường ngoài request:

~~~text
priority
scenarioName
requiredScenarioState
newScenarioState
transformers
metadata
bodyFileName
~~~

Ví dụ hai mappings cùng match `POST /api/reservations`:

~~~text
Generated contract:
  priority: 5
  response: 201 RESERVED

Custom fallback:
  priority: 1
  response: 200 ACCEPTED
~~~

Trong WireMock, **số priority nhỏ thường ưu tiên cao hơn**. Vì vậy fallback priority 1 có thể che generated mapping priority 5.

Một scenario ở trạng thái `Depleted` cũng có thể thay response; test A chưa reset state khiến test B nhận lỗi. Một response transformer hoặc response templating có thể sửa body/header sau khi mapping được chọn.

Chẩn đoán theo thứ tự:

1. Những mappings nào có thể match request?
2. Priority của mỗi mapping là bao nhiêu?
3. Server đang ở scenario state nào?
4. Extension/template nào đã được đăng ký trên đúng instance?
5. Body file nào thực sự được đọc?
6. Có Admin API dynamic stub nào được test trước thêm vào không?
7. Request journal cho biết mapping nào đã thắng?

**Generated mapping đúng chưa chắc WireMock đang phục vụ mapping đó** khi runtime có customizations. Nếu customization đổi semantics công khai, phải được review/kiểm chứng tương ứng, không chỉ sửa stub.

## 28. Producer actual response và Stub Runner response không phải một

Một tình huống thường gây nhầm:

~~~text
Producer (real HTTP):
  POST /api/reservations -> 200 ACCEPTED

Stub Runner (contract):
  POST /api/reservations -> 201 RESERVED
~~~

Producer contract test có thể FAIL (nếu thật sự chạy trên producer), trong khi consumer stub test PASS. Đây không phải mâu thuẫn: **WireMock mô phỏng contract**, không phản ánh code runtime tại mọi thời điểm.

Để điều tra producer thực:

- Kiểm generated producer test đã chạy trên **current code revision** chưa.
- Dùng test adapter/real HTTP ở đúng Spring context/cấu hình.
- Xác định controller route, service behavior, exception handler và serializer.
- So HTTP response thật với assertions generated.
- Kiểm filter/interceptor/ControllerAdvice có đổi status/body không.
- Nếu producer test PASS nhưng runtime sai, nghi fake base test, profile/config khác hoặc binary deploy không phải artifact đã test.

**Không sửa stub cho khớp một producer implementation sai** mà chưa xem contract/consumer requirements. Một contract change cần được review, nhất là khi breaking.

## 29. Chẩn đoán theo điểm thất bại đầu tiên

Một cây quyết định tối giản:

~~~mermaid
flowchart TD
    A["Contract test/consumer test FAIL"] --> B{"Contract DSL được discovery và parse?"}
    B -- "Không" --> B1["Sửa source path / YAML-Groovy / plugin config"]
    B -- "Có" --> C{"Generated producer test có chạy?"}
    C -- "Không" --> C1["Runner, skip flags, test count, base class"]
    C -- "Có" --> D{"Generated test PASS với producer thật?"}
    D -- "Không" --> D1["So request fixture, actual response và assertions"]
    D -- "Có" --> E{"Stubs artifact đúng candidate/digest?"}
    E -- "Không" --> E1["Generation/packaging/repository/cache"]
    E -- "Có" --> F{"WireMock nhận đúng request của client?"}
    F -- "Không" --> F1["Port/URL/method/headers/body/encoding"]
    F -- "Có" --> G{"Mapping mong đợi được chọn?"}
    G -- "Không" --> G1["Priority, state, fallback, custom extension"]
    G -- "Có" --> H{"Consumer xử lý response đúng?"}
    H -- "Không" --> H1["DTO, deserializer, status/error mapping"]
    H -- "Có" --> I["Kiểm assertions/CI report; xác nhận phạm vi PASS"]
~~~

**Đây là decision tree chẩn đoán, không phải quy tắc mọi producer đều phải có consumer ở mọi branch.** Nếu lỗi xảy ra ở contract source chưa có triển khai producer, trạng thái đúng là Draft/Not verified, không cưỡng ép release.

### Nguyên tắc sửa đúng lớp

- Contract parser FAIL → sửa DSL/cấu hình plugin, không xóa consumer assertions.
- Generated test FAIL do response producer sai → sửa implementation hoặc đề xuất contract change có review.
- Mapping không match request consumer sai → sửa client serializer/header/path, không bỏ mọi `bodyPatterns`.
- Stub Runner tải sai artifact → sửa resolution/provenance, không sửa contract.
- WireMock mapping bị custom override → sửa priority/extension/isolation.
- Consumer nhận đúng raw response nhưng parse sai → sửa DTO/handler hoặc điều chỉnh compatibility plan.
- Test report không có executed tests → sửa CI runner, không coi build success là verification.

## 30. Phân biệt HTTP status 404 theo ngữ cảnh

Ba loại lỗi có thể cùng xuất hiện dưới số 404:

| Tình huống | Nơi xảy ra | Diễn giải |
|---|---|---|
| Repository trả 404 khi tải stubs JAR | Artifact resolution trước khi Stub Runner chạy | Sai tọa độ/repository/classifier hoặc artifact chưa publish |
| WireMock trả 404 vì request không match | Stub Runner đang phục vụ HTTP | Client/protocol/mapping mismatch |
| Contract quy định business 404 + error code | Stub Runner/producer trả response theo scenario | Tình huống nghiệp vụ hợp lệ |

Ví dụ business error:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"RESERVATION_NOT_FOUND","message":"Reservation does not exist"}
~~~

Nếu consumer test chỉ nhìn `status == 404`, một **unmatched stub 404** có thể bị nhận nhầm là business error. Hãy kiểm **status + error.code + body schema**, và khi cần so request journal để biết mapping nào đã trả response.

Không hardcode mọi 404 thành “không tìm thấy reservation” trong client nếu API có nhiều error meanings hoặc WireMock unmatched response cần phát hiện là test error.

## 31. Phân biệt lỗi 400/422 của producer với stub không match

Một producer thực có thể trả 400/422 cho body sai:

~~~json
{"productCode":"SKU-123","quantity":"2"}
~~~

Nhưng một stub chỉ mô tả happy-path 201 có thể **không có mapping 400/422** và trả unmatched 404. Đừng kết luận producer thực sẽ trả 404.

Muốn kiểm validation contract, hãy tạo **scenario lỗi riêng**:

~~~yaml
description: Quantity sai kiểu trong request
name: reservation_invalid_quantity

request:
  method: POST
  url: /api/reservations
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    quantity: "two"

response:
  status: 422
  headers:
    Content-Type: application/json
  body:
    code: INVALID_QUANTITY
    message: Quantity must be a positive integer
~~~

Đoạn YAML minh họa một **request validation case**. Điều kiện phát 422 phải khớp policy API của dự án, không phải HTTP rule bắt buộc. Producer code và generated tests cần xác minh đúng behavior, còn Stub Runner consumer tests nên kiểm error mapper.

Nếu producer trả 400 thay vì 422 theo contract đã được thống nhất, đây có thể là regression. Đừng sửa expected status chỉ vì code đang trả 400 mà chưa review với consumer.

## 32. JSON null, missing, empty và number/string: so theo type lẫn semantics

Một response JSON có thể nhìn rất giống nhau khi log bị format:

~~~json
{"quantity":2,"reservationId":"R-1001"}
~~~

~~~json
{"quantity":"2","reservationId":"R-1001"}
~~~

~~~json
{"quantity":null,"reservationId":"R-1001"}
~~~

~~~json
{"reservationId":"R-1001"}
~~~

Nếu consumer DTO dùng primitive `int`, missing/null đôi khi bị mặc định theo deserialization config, che lỗi contract. Một mapper có thể ép string `"2"` thành integer `2`. Vì vậy phải xem **raw HTTP body** và có assertions thích hợp:

| Kiểm tra | Mục đích |
|---|---|
| JSON type/JSONPath assertion | Không nhận nhầm number thành string |
| Field presence | Phát hiện missing required field |
| Nullability | Phân biệt null và giá trị hợp lệ |
| Equality theo fixture | Bảo vệ business value |
| Enum whitelist | Bảo vệ consumer không gặp giá trị ngoài tập |
| Negative cases | Kiểm consumer fail/fallback đúng khi schema sai |

**Không chỉ nhìn object đã deserialize** rồi kết luận response wire format đúng. Deserializer có thể làm mất khác biệt quan trọng.

## 33. Request thừa header/body field: không luôn là breaking change

Một request có thể thêm field tùy chọn:

~~~json
{"sku":"SKU-123","quantity":2,"source":"checkout-mobile"}
~~~

Nếu contract/request schema **cho phép unknown fields**, một WireMock mapping `equalToJson` strict mọi key có thể reject request thực dù producer sẽ chấp nhận. Nhưng nếu API đã công bố **closed schema**, reject là đúng.

Chẩn đoán cần tách:

- **Required fields:** thiếu `sku` phải bị phát hiện.
- **Optional/additive fields:** được phép hay không theo contract?
- **Unknown fields:** producer/consumer có strict parsing không?
- **Order của JSON keys:** thông thường không phải ngữ nghĩa, trừ khi chữ ký/canonicalization đòi hỏi.
- **Whitespace/number formatting:** không nên so raw string nếu API cam kết semantic JSON, nhưng cần giữ phân biệt types.
- **Body matcher:** `equalToJson`/JSONPath có ignore-extra/array-order settings gì?

Không nới matcher thành “mọi JSON đều hợp lệ” chỉ vì một field bổ sung. Hãy thay bằng matcher đúng policy, rồi chạy negative tests cho required schema.

## 34. Message contracts: đọc output và handler thật thay vì HTTP journal

Khi SCC dùng message contract, không có HTTP request journal để kiểm. Ví dụ Groovy:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'reservationCreated'

    input {
        triggeredBy('triggerReservationCreated()')
    }

    outputMessage {
        sentTo('reservation.events')
        headers {
            header('eventType', 'ReservationCreated')
        }
        body(
            reservationId: 'R-1001',
            sku: 'SKU-123',
            quantity: 2
        )
    }
}
~~~

Để chẩn đoán producer message verification:

1. Contract `triggeredBy(...)` chỉ tới method nào trong base test?
2. Method ấy có gọi **production service/use case thật** hay chỉ tự gửi message mẫu?
3. Output destination `reservation.events` có được producer gửi thực qua test binder/verifier không?
4. Header `eventType` có giá trị đúng không?
5. Payload có đúng JSON type, required fields, schema version không?
6. Generated test có assertion/timeout rõ và thực sự chạy không?
7. Có message tồn đọng trong test channel từ run trước không?

Phía consumer, dùng **message handler/deserializer thật** để kiểm parse và business outcome. Chỉ test `ObjectMapper.readTree` trên fixture không chứng minh listener routing hoặc state update.

Đối với broker partition, retry, DLQ, ordering và at-least-once delivery, thêm broker/integration tests nếu contract stub không bảo vệ các hành vi đó. **Không dùng HTTP-oriented diagnostics cho message case.**

## 35. WebFlux và các test adapters: tìm sai lầm tại điểm khởi tạo request

Producer có thể là Spring MVC, WebFlux hoặc HTTP server thực. SCC hỗ trợ các adapter/test modes khác nhau tùy version; **generated test source** và base class là nguồn để biết test đã chạy theo cách nào.

Ví dụ nếu generated test dùng WebTestClient nhưng base test chỉ setup RestAssuredMockMvc, request có thể không đến controller dự kiến. Ngược lại, nếu test chỉ chạy standalone fake handler, nó không chứng minh production WebFlux router/filter/handler đúng.

Cách kiểm:

- Generated test imports dùng adapter nào?
- Base class khởi tạo `MockMvc`, `WebTestClient` hoặc real HTTP port?
- Test server port có được inject đúng, nhất là RANDOM_PORT?
- Filter/security configuration có được bật như trong phạm vi contract?
- RouterFunction/Controller có thuộc Spring test context không?
- Reactive pipeline có thực sự được subscribe/await đúng không?
- Timeout/cancellation có làm test hoàn thành sớm mà không kiểm output không?

Đừng copy một base test của Spring MVC sang dự án WebFlux rồi “sửa” bằng cách mock response. Chọn adapter/cấu hình tương thích Spring Boot–Spring Cloud Contract release train và xác minh bằng mutation test.

## 36. Đối chiếu bốn lớp bằng một bảng diff có thể review

Dưới đây là **bảng đối chiếu minh họa** khi Checkout POST reservation bị 404:

| Điều kiện | Contract DSL | Generated producer test | WireMock mapping | Request thực của Checkout |
|---|---|---|---|---|
| Method | POST | POST | POST | POST |
| Path | `/api/reservations` | Cùng path | Cùng path | Cùng path |
| Content-Type | application/json | Gửi JSON | Matcher có thể kiểm | application/json |
| `X-Request-Id` | `req-1001` | Có header | EqualTo `req-1001` | **Thiếu** |
| `sku` | `SKU-123` | Có field | EqualToJson/JSONPath | **`productCode`** |
| `quantity` | JSON number 2 | 2 | Number 2 | **String "2"** |
| Expected status | 201 | Assert 201 | Response 201 | **Unmatched 404** |
| Next action | Contract giữ nguyên | Test producer có thể PASS | Mapping có lý | **Sửa Checkout client** |

Bảng giúp nhìn ra **lớp sai đầu tiên**. Nếu source contract, generated test và mapping đều đồng nhất, nhưng request thực sai, đừng sửa contract/mapping chỉ để trả 201 cho request ấy.

Đối với một incident thật, thay “có thể” bằng thông tin trích từ generated code, mapping bytes và request journal thực. Đừng giả điền dữ liệu khi chưa thu.

## 37. Case study A — Producer test PASS, consumer nhận 404

### Bối cảnh

Contract Groovy yêu cầu POST `/api/reservations`, JSON `sku` và `quantity` number; generated producer tests PASS.

### Consumer hiện tượng

~~~text
Checkout CI:
  expected: HTTP 201
  actual: HTTP 404
~~~

### Chuỗi chẩn đoán

1. Xác nhận 404 là **HTTP response từ WireMock**, không phải lỗi tải JAR.
2. Kiểm Stub Runner đang phục vụ Reservation Service ở port consumer client gọi.
3. Xác nhận JAR/digest đúng candidate.
4. Đọc mapping `bodyPatterns`/headers.
5. Truy vấn request journal của đúng instance.
6. So body raw: `{"productCode":"SKU-123","quantity":"2"}`.
7. Đọc client DTO: tên Java field `productCode` và kiểu `String quantity`.
8. Sửa DTO/request serialization để gửi `{"sku":"SKU-123","quantity":2}`.
9. Chạy lại consumer test và giữ negative test để client sai trở lại sẽ đỏ.

### Điều không nên làm

- Không xóa `bodyPatterns` rồi tuyên bố test đã PASS.
- Không thêm catch-all 201 cho mọi POST.
- Không sửa producer contract để khớp một bug serialization ở consumer chưa được hai nhóm chấp thuận.

## 38. Case study B — Producer trả sai nhưng generated test vẫn xanh

### Bối cảnh

Contract yêu cầu:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"status":"RESERVED"}
~~~

Producer production implementation lỗi và trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"PENDING"}
~~~

Nhưng producer CI vẫn xanh.

### Điều tra

1. Generated Java test có assert status 201 và `status=RESERVED` không?
2. Test report có **executed generated tests > 0** không, hay zero/skip?
3. Base test dùng Spring context/controller thật hay `standaloneSetup(new FakeController())`?
4. Có mock `ReservationService` luôn trả expected DTO không?
5. Test đang chạy profile/config khác production hoặc gọi một mock endpoint khác?
6. Có exception handler/middleware riêng ở runtime bị bỏ qua trong test?
7. Thử mutation đổi 201→200 và `RESERVED`→`PENDING` trong code producer — test phải đỏ.
8. Nếu generated assertions thiếu, sửa contract matcher; nếu test dùng fake code, sửa base wiring.

**Kết luận:** test xanh có thể là lỗi **chứng cứ thực thi** hoặc matcher, không phải bằng chứng producer code luôn đúng.

## 39. Case study C — Mapping đúng trong workspace, Stub Runner dùng cũ

### Bối cảnh

Producer commit B sửa contract request header và đã generate mapping mới. Checkout CI vẫn pass với một version `1.4.0-SNAPSHOT`.

### Điều tra

1. Chụp commit B, expected stubs JAR và checksum từ producer CI.
2. Mở JAR consumer resolve, so timestamped snapshot/digest.
3. Xem Stub Runner start trước hay sau khi B được publish.
4. Kiểm repository mirror/proxy metadata và local cache nếu digest mismatch.
5. Khởi động Stub Runner mới với **exact candidate**.
6. Đọc effective mapping qua Admin API/journal để xác nhận header matcher B.
7. Cố ý bỏ required header trong Checkout client: test phải fail.
8. Ghi resolved identity/digest vào CI report, tránh tái diễn.

**Kết luận:** không quy lỗi cho DSL khi consumer chưa dùng đúng artifact được sinh từ DSL ấy.

## 40. Troubleshooting matrix: triệu chứng → lớp → bước tiếp theo

| Triệu chứng | Lớp nghi vấn | Bước kiểm trước |
|---|---|---|
| Contract file có nhưng không sinh test | Contract discovery/generator | File path, plugin configuration, task logs |
| Contract parse fail | Groovy/YAML DSL | Syntax, indentation, matcher type theo version |
| Generated test compile fail | Generator/test base/version | Imports, JUnit, class/method name, plugin train |
| Generated test PASS với tests run 0 | Test execution | Surefire/Gradle reports, skip flags |
| Test FAIL expected 201 actual 200 | Producer response | Controller/advice, business logic, assertion |
| Test PASS dù mutate producer code | Fake base/matcher weak | Test path, mocks, byType/byRegex |
| Stub JAR thiếu mapping | Packaging | Generated outputs, classifier, jar tf |
| Mapping tham chiếu `bodyFileName` không tồn tại | Packaging/resources | Kiểm `__files` trong JAR |
| Stub Runner không start, artifact 404 | Resolution | Repo/classifier/version/credentials |
| Consumer nhận 404 nhưng Stub Runner chạy | Request matching | Journal, bodyPatterns, headers, URL |
| Consumer nhận wrong stub response | Priority/state/extension | Matched stub ID, overlapping mappings |
| Consumer nhận 200 nhưng parse fail | Response schema/client DTO | Raw JSON, Content-Type, deserializer |
| Consumer thấy artifact cũ | Cache/version | Timestamped SNAPSHOT, digest, server startup |
| Không có request journal | Sai server/journal disabled/client mocked | Port, request journal config, client URL |
| E2E FAIL dù contracts PASS | Runtime integration | Network/auth/DB/broker/config khác test |
| Một rerun PASS mà không đổi code | Flaky/state/cache | Test isolation, deterministic data, resolver |

**Ma trận là điểm bắt đầu chẩn đoán, không phải chẩn đoán cuối.** Chỉ kết luận khi có bằng chứng tại đúng lớp.

## 41. Logging và bảo vệ dữ liệu nhạy cảm khi điều tra

Để debug nhanh, raw HTTP là hữu ích nhưng có rủi ro tiết lộ dữ liệu:

- Không in `Authorization`, access token, session cookie, API key và password vào CI logs.
- Không ghi payload chứa PII hoặc tài khoản khách hàng thật; dùng test fixture giả.
- Khi dùng RestAssured/WebClient/Feign logging, cấu hình redaction trước khi tăng log level.
- Với request journal/near misses, chỉ xuất thông tin đủ chẩn đoán: method, normalized path, allowed headers, schema-safe body.
- Không expose WireMock Admin API ra internet; chỉ truy cập trong test network đã được phân quyền.
- Dùng correlation ID không mang thông tin định danh nhạy cảm.
- Giữ log/report đủ commit, artifact digest và test name để audit, không giữ raw secrets.
- Tắt diagnostic verbosity hoặc giới hạn retention sau khi giải quyết sự cố.

**Log nhiều hơn không tự động tạo chẩn đoán tốt hơn.** Log đúng bốn lớp, gắn cùng candidate identity và che secrets mới là nguồn bằng chứng có giá trị.

## 42. Mẫu biên bản chẩn đoán có đủ bốn lớp

Khi một incident lặp đi lặp lại giữa producer/consumer teams, nên dùng một báo cáo có cấu trúc thay vì gửi từng screenshot rời rạc:

~~~yaml
incident:
  id: CONTRACT-INCIDENT-017
  scenario: create_reservation_sku123
  symptom: Consumer received unmatched HTTP 404
  environment: checkout-ci

source:
  producerService: reservation-service
  producerCommit: a1b2c3d4
  contractRevision: a1b2c3d4
  contractPath: contracts/reservation/create-reservation.groovy

generatedProducerTest:
  class: NAME_FROM_ACTUAL_GENERATION
  executed: COUNT_FROM_TEST_REPORT
  result: PASS_OR_FAIL
  baseTest: BASE_CLASS_NAME

stubArtifact:
  coordinates: com.example:reservation-service:1.4.0-rc.pr173.a1b2c3d4:stubs
  publishedSha256: PRODUCER_CI_DIGEST
  resolvedSha256: CONSUMER_CI_DIGEST
  mappingName: MAPPING_FROM_JAR
  loadedByWireMock: TRUE_OR_FALSE

wireRequest:
  method: POST
  path: /api/reservations
  contentType: application/json
  jsonBody: '{"productCode":"SKU-123","quantity":"2"}'
  matchedStubId: NONE_OR_REAL_ID
  actualHttpStatus: 404

diagnosis:
  firstDivergence: Consumer wire body differs from contract
  owner: checkout-team
  correction: Align request DTO and serializer with contract
  regressionTest: Require negative request with wrong field/type
~~~

Tất cả identifiers `NAME_FROM_*`, `COUNT_FROM_*`, `*_DIGEST` và `TRUE_OR_FALSE` là **placeholder**. Không tự bịa “PASS” hoặc mapping ID nếu pipeline chưa thu được bằng chứng.

Biên bản tốt phải chỉ ra được **chênh lệch đầu tiên**, **ai sở hữu lớp lỗi** và **test nào sẽ bảo vệ lần sau**. Với hệ thống nhiều consumer, ghi rõ consumer version/commit chứ không chỉ tên `checkout-service`.

## 43. Quy trình triage nhanh trong một phiên điều tra

Một cách làm có thể áp dụng khi developer vừa thấy Checkout test đỏ:

| Bước | Hành động | Nếu không có bằng chứng |
|---|---|---|
| 1 | Đọc failing test name và stack trace | Xem runner report; không suy đoán |
| 2 | Chốt producer commit và contract revision | Dừng kết luận về compatibility |
| 3 | Đọc contract scenario | Xác nhận method/URL/header/body |
| 4 | Mở generated producer Java test | Tìm assertions và base wiring |
| 5 | Kiểm tests executed > 0 | Fix generation/runner trước |
| 6 | Mở mapping trong **resolved JAR** | Fix artifact resolution/packaging |
| 7 | Thu request journal từ đúng WireMock port | Fix client/server routing hoặc bật diagnostic |
| 8 | So raw request với mapping và contract | Xác định first divergence |
| 9 | Xác nhận response/matched mapping | Kiểm priority, fallback, scenario state |
| 10 | Tạo negative regression test rồi sửa | Re-run đúng candidate, lưu report |

**Không nên chạy lại liên tục cho đến khi có màu xanh**. Nếu mỗi lần chạy dùng SNAPSHOT khác hoặc stateful WireMock server khác, các PASS/FAIL không còn so sánh được.

## 44. CI guard: bốn lớp phải liên kết cùng candidate

Một quality gate tối thiểu nên yêu cầu:

~~~text
contract_revision_known
AND generated_producer_tests_executed > 0
AND producer_contract_tests_passed
AND produced_stubs_jar_exists
AND mapping_scenarios_present
AND published_sha256 == resolved_sha256
AND stub_runner_loaded_expected_artifact
AND consumer_tests_executed > 0
AND consumer_tests_passed
AND consumer_client_used_real_http_or_message_adapter
~~~

Đây là **pseudocode chính sách**, không phải API built-in của SCC.

Trong một release gate, có thể thêm những yêu cầu theo rủi ro: supported consumer matrix, security, migration readiness, environment authorization, canary. **Test PASS và quyền triển khai không phải một khái niệm.**

### Nếu dùng SNAPSHOT

Với `1.4.0-SNAPSHOT` mutable, phải có resolved timestamp/digest và provenance. Nếu không xác minh được artifact, đánh dấu `STALE/UNKNOWN` thay vì tự mặc định PASS. Một job consumer báo PASS với stub A không chứng minh candidate B an toàn.

### Nếu có test bị skip

Phải đọc test report thực. `BUILD SUCCESS` với **0 generated tests** không cho phép kết luận producer-verified. Một job không có report hoặc dùng report của build cũ cũng không phải bằng chứng.

## 45. Bài thực hành A — Đọc từng lớp trong một scenario HTTP

**Mục tiêu:** hoàn thành bảng đối chiếu bốn lớp với request hợp lệ.

1. Tạo contract Groovy POST `/api/reservations` với `sku=SKU-123`, `quantity=2`, `X-Request-Id=req-1001`.
2. Implement producer controller/service thực và chuẩn bị fixture để trả 201.
3. Cấu hình SCC plugin và sinh producer tests.
4. Mở generated Java test, ghi method, URL, request JSON và response assertions.
5. Chạy generated test, xác nhận **executed count > 0** và PASS.
6. Mở generated WireMock mapping, ghi `bodyPatterns`, headers và response.
7. Package stubs JAR, xác nhận mapping có trong JAR.
8. Khởi động Stub Runner với JAR candidate ấy, ghi port và digest.
9. Gửi request hợp lệ bằng client Checkout thật, so journal/response.
10. Tạo một bảng contract → generated Java → mapping → raw request và ghi kết luận.

**Sản phẩm nộp:** bảng bốn lớp, producer test report, mapping JSON, artifact digest và consumer test report.

## 46. Bài thực hành B — Chẩn đoán request body sai kiểu

**Mục tiêu:** tìm nguyên nhân consumer nhận unmatched 404 khi producer test vẫn PASS.

1. Giữ contract yêu cầu `{"sku":"SKU-123","quantity":2}`.
2. Trong một nhánh thử, cho Checkout DTO gửi `{"productCode":"SKU-123","quantity":"2"}`.
3. Chạy consumer test với Stub Runner candidate và ghi HTTP status.
4. Mở journal của đúng WireMock server, xác nhận raw body sai.
5. Đọc mapping: yêu cầu field `sku` và kiểu number hay không?
6. Nếu mapping chưa bảo vệ kiểu, điều chỉnh **contract matcher** chứ không sửa output JSON bằng tay.
7. Sinh lại JAR và pin candidate version.
8. Với request sai, test phải **không nhận nhầm happy-path 201**.
9. Sửa DTO/serializer, chạy lại real consumer client, test PASS.
10. Ghi cả request bytes, mapping diff, candidate digest và test output.

**Không coi mọi unmatched 404 là business NotFound.** Đây là lỗi request không match, trừ khi contract có business scenario đúng được chọn.

## 47. Bài thực hành C — Phát hiện fake producer test và stale stub

**Mục tiêu:** xác minh hai đầu producer/consumer không báo xanh giả.

1. Tạo một producer base test gọi Spring context/implementation thật.
2. Cho generated contract test đạt.
3. Cố ý đổi producer response status 201→200 trong nhánh thử; test phải FAIL.
4. Nếu vẫn PASS, xem generated assertions, mock/fake base wiring và test executed count.
5. Khôi phục implementation.
6. Tạo candidate stubs JAR mới và ghi SHA-256.
7. Trong consumer test, cố ý dùng version/digest cũ.
8. Provenance check phải phát hiện artifact không khớp candidate.
9. Chạy lại với artifact mới, xác nhận server đã load mappings đúng.
10. Ghi report phân biệt **producer verification** và **consumer compatibility**.

**Sản phẩm:** evidence của mutation FAIL, before/after resolved JAR digest và log Stub Runner instance.

## 48. Bài thực hành D — Message contract không có HTTP request journal

**Mục tiêu:** áp dụng cùng nguyên tắc bốn lớp cho messaging.

1. Viết message contract `ReservationCreated` có label, trigger, destination, headers và payload.
2. Sinh producer message test và đọc Java assertions.
3. Bảo đảm trigger gọi production use case, không tự phát payload hardcoded.
4. Kiểm output message trong test binder/verifier, gồm routing/destination và headers.
5. Sinh/publish messaging stub artifact theo version.
6. Cho consumer listener/handler thật xử lý message contract tương ứng.
7. Cố ý đổi `eventType` hoặc `quantity` number→string; test phải phát hiện.
8. Thêm broker integration test nếu cần kiểm partition, ordering hoặc DLQ.
9. Ghi provenance giữa contract revision, producer output, stub message và consumer handler result.
10. Phân biệt errors thuộc generated test, message routing/test binder hay handler deserialization.

**Không áp dụng máy móc HTTP 404/journal** cho bài toán message broker; thay bằng message capture, headers, payload và destination evidence.

## 49. Checklist chẩn đoán trước khi kết luận

- [ ] Có đúng **contract scenario/path/revision** đang kiểm chứng.
- [ ] Đã đọc method, path, query, headers, body và matchers trong Groovy/YAML.
- [ ] Không nhầm contract YAML với WireMock JSON mapping.
- [ ] Generated Java producer test khớp contract và đúng adapter/test mode.
- [ ] Producer test base gọi implementation thật, không fake controller trả expected body.
- [ ] Generated test thực sự chạy, executed count > 0, không bị skip.
- [ ] Đã so expected/actual producer response status, headers, JSON body.
- [ ] Stubs JAR có classifier và artifact version đúng.
- [ ] Generated mapping được đọc từ **JAR consumer sử dụng**, không chỉ `target`.
- [ ] Mọi `bodyFileName` có file tương ứng trong artifact.
- [ ] Nếu SNAPSHOT, resolved timestamp/digest được lưu và so với producer candidate.
- [ ] Stub Runner server đã load mappings đúng; startup time phù hợp.
- [ ] Không có custom mapping priority/fallback/transformer che generated mapping.
- [ ] Stateful WireMock scenario được reset/cô lập.
- [ ] Consumer test dùng **real HTTP client/message handler**, không mock chính adapter.
- [ ] Consumer base URL/port trỏ đúng server.
- [ ] Raw request được xác minh từ đúng WireMock journal hoặc client wire logs.
- [ ] Method/path/query/header/body và JSON type đã được so từng phần.
- [ ] Unmatched WireMock 404 không bị nhầm với business error 404.
- [ ] Raw HTTP response và object deserialized được phân biệt.
- [ ] Error code/body được kiểm, không chỉ HTTP status.
- [ ] Dynamic values và request–response correlation được đánh giá đúng semantics.
- [ ] Negative/mutation test làm một regression quan trọng chuyển đỏ.
- [ ] Bằng chứng CI gắn commit, contract revision, version, digest và test count.
- [ ] Cấu hình/log không lộ token, cookies hoặc production PII.
- [ ] Đã sửa ở **lớp sai đầu tiên** và chạy lại với candidate bất biến.
- [ ] Kết luận nêu rõ test đã chứng minh gì và chưa chứng minh gì.

## 50. Câu hỏi tự kiểm tra

**1. Vì sao đọc contract source một mình không đủ để debug consumer test?**

Vì generated mapping, stubs artifact và raw request có thể khác contract hiện tại do matcher translation, stale build, cache, customizations hoặc client serialization.

**2. Generated test đã được sinh nhưng “Tests run: 0” có chứng minh producer đúng không?**

Không. Phải có generated tests thực sự được thực thi và PASS trên implementation producer cần bảo vệ.

**3. Tại sao consumer Stub Runner PASS không chứng minh producer implementation thật?**

WireMock trả response từ contract mapping, không gọi code producer thật. Producer verification là gate riêng.

**4. Một request trả 404 có thể do những nguyên nhân khác nhau nào?**

Artifact repository 404 khi resolution, WireMock unmatched 404 khi method/path/header/body không match, hoặc business 404 đã được contract định nghĩa. Phân biệt theo thời điểm, body/error code và journal.

**5. Tại sao `quantity:"2"` có thể là breaking change dù nhìn giống `quantity:2`?**

Một bên là JSON string, một bên là JSON number. Consumer/producer có thể có strict validation hoặc deserializer coercion khác nhau.

**6. Mở mapping trong producer `target` đã đủ biết Stub Runner đang trả gì chưa?**

Chưa. Phải kiểm JAR thực được consumer resolve, digest, runtime mappings, server startup và custom overrides.

**7. Nếu request journal rỗng, có phải WireMock không nhận request không?**

Không chắc. Có thể query sai server/port, journal bị tắt, client bị mock hoặc request chưa chạy. Cần xác định instance, config và client URL.

**8. Một mapping `priority:1` có thể che mapping `priority:5` không?**

Có, khi cả hai match request và WireMock áp quy tắc ưu tiên số nhỏ hơn trước. Cần kiểm matched stub ID và mapping overlap.

**9. Vì sao cần negative/mutation test khi producer/consumer tests đều xanh?**

Để chứng minh thay đổi sai như HTTP 201→200, field thiếu hoặc request body sai thực sự làm suite đỏ, tránh xác nhận giả do matcher quá rộng, fake code hoặc stale artifact.

**10. Khi nào được kết luận lỗi nằm ở Checkout thay vì Reservation producer?**

Khi contract đã được chấp thuận, generated test/mapping cùng revision và artifact đúng, nhưng raw request của Checkout **khác** ràng buộc contract; ví dụ gửi `productCode` thay `sku`. Kết luận cần bằng chứng, không chỉ một HTTP 404.

## 51. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, generated tests, DSL và stubs.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): request/response, matchers và dynamic values.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): LOCAL/REMOTE, artifact resolution và consumer tests.
- [Spring Cloud Contract — Maven](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): generated test và stubs packaging.
- [Spring Cloud Contract — Gradle](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): Gradle test generation và integration.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): mapping JSON, responses và priorities.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): method/path/query/headers/body matching.
- [WireMock — Verifying](https://wiremock.org/docs/verifying/): request journal, verification và unmatched requests.
- [WireMock — Mismatches](https://wiremock.org/docs/mismatches/): near-miss diagnostics và debugging.
- [WireMock — Stateful Behaviour](https://wiremock.org/docs/stateful-behaviour/): scenario state lifecycle.
- [WireMock — Response Templating](https://wiremock.org/docs/response-templating/): dynamic responses và template behavior.
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): artifact resolution và local/remote caches.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): changing/dynamic modules và refresh.
- [Martin Fowler — Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html): hợp đồng giữa producer và consumer.

**Lưu ý về phiên bản:** Spring Cloud Contract, Groovy/YAML DSL, generated test adapters, test output directories, Stub Runner và WireMock mapping/Admin API khác nhau theo Spring Boot–Spring Cloud Release Train–SCC/WireMock versions. Các Java tests, file paths, JSON mappings, ports, checksum và log trong bài là **ví dụ minh họa**, không phải output đã chạy trên một hệ thống thật. Khi áp dụng, hãy lấy **generated source, compiled test report, JAR và runtime journal của đúng phiên bản đang dùng**. Trong bước biên soạn này không chạy Maven, Gradle, Python hay vòng Content QA chuyên sâu.

---

**Điểm cần nhớ:** Chẩn đoán Spring Cloud Contract hiệu quả không bắt đầu bằng việc “sửa test cho xanh”, mà bằng việc **đối chiếu bốn lớp: contract DSL → generated producer test → WireMock mapping/stubs artifact → request/response thực của consumer**. Ghim chúng về cùng revision và artifact digest, xác định **lớp sai đầu tiên**, sửa đúng chủ sở hữu rồi chạy negative/mutation tests để đảm bảo một thay đổi không tương thích sẽ thực sự bị phát hiện trong CI.
