# Hợp đồng đang phát triển và cách ngăn xác nhận giả

## 1. Bối cảnh: “test xanh” không có nghĩa “hai nhóm đã thống nhất”

Trong hệ thống microservices, **producer** cung cấp HTTP API hoặc phát thông điệp, còn **consumer** gọi hoặc xử lý các giao tiếp đó. **Spring Cloud Contract (SCC)** cho phép mô tả hành vi bằng **Groovy/YAML DSL**, từ đó sinh **producer verification tests**, tạo **stub artifacts** và cho consumer sử dụng **Stub Runner** trong kiểm thử tương thích. Nếu được tổ chức đúng, các kiểm tra này phát hiện thay đổi API không tương thích trước khi triển khai.

Tuy nhiên, khi nhiều nhóm cùng phát triển, một hợp đồng có thể đang ở trạng thái **đề xuất**, **chưa triển khai**, **chưa được producer chấp nhận**, hoặc **đang chuyển đổi để giữ tương thích ngược**. Trường hợp nguy hiểm là pipeline báo PASS nhưng chưa hề kiểm tra đúng phiên bản, đúng code hoặc đúng hành vi đang được thương lượng. Đó là **xác nhận giả** (*false assurance/false-positive validation*): tín hiệu “đã an toàn” không được hỗ trợ bởi bằng chứng kiểm thử phù hợp.

Ví dụ thực tế trong một hệ thống bán hàng:

- Nhóm Checkout muốn Inventory API trả trường `available`.
- Nhóm Inventory dự định thay bằng `inStock`.
- Nhóm Checkout viết lại fixture/stub theo field mới; test với WireMock xanh.
- Producer implementation thật vẫn chỉ trả field cũ, hoặc đang chạy contract version khác.
- CI của Checkout báo thành công, nhưng **không chứng minh** hai dịch vụ có thể giao tiếp sau khi deploy.

Ngược lại, producer cũng có thể sửa code và contract cùng lúc: generated producer tests mới xanh, nhưng Checkout phiên bản đang chạy không còn đọc được response. Hai tình huống cho thấy cần **phối hợp kỹ thuật và quy trình**, không chỉ viết DSL đúng cú pháp.

Bài học thuộc chương **Phối hợp nhiều nhóm**, tập trung trả lời: **hợp đồng đang phát triển nên được quản lý, kiểm chứng và công bố thế nào để ngăn trạng thái PASS giả?**

### Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt **hợp đồng đề xuất**, **đã được chấp thuận**, **đã được producer triển khai**, **đã publish stub** và **đã kiểm chứng consumer**.
2. Xác định trách nhiệm giữa nhóm producer, consumer, QA và người quản lý CI/repository.
3. Thiết kế quy trình review hợp đồng cho thay đổi tương thích và breaking change.
4. Phát hiện các dạng xanh giả: **stub tự viết**, **fake producer**, **test skip**, **matcher quá rộng**, **artifact cũ** và **assertions yếu**.
5. Sử dụng SCC generated producer tests và Stub Runner để tạo hai bằng chứng **độc lập nhưng liên kết cùng revision**.
6. Ghim candidate artifact theo version/commit, kiểm tra mapping và log runtime thay vì tin mỗi dòng BUILD SUCCESS.
7. Tổ chức kiểm thử tiêu cực/mutation tests để chứng minh suite có khả năng chuyển đỏ.
8. Thiết lập release gates, ownership, compatibility matrix và quy trình expand–migrate–contract.

## 2. Ba câu hỏi khác nhau nhưng thường bị nhập làm một

Khi nhận thông báo “contract đã được xác nhận”, cần hỏi rõ:

| Câu hỏi | Bằng chứng phù hợp | Chưa đủ để chứng minh |
|---|---|---|
| **Hai nhóm có thống nhất hành vi không?** | Contract PR đã được owner/reviewer chấp thuận, semantics và migration được ghi rõ | File YAML hợp lệ hoặc một bình luận “LGTM” từ một nhóm |
| **Producer có thực thi hành vi đã cam kết không?** | Generated producer tests chạy trên **implementation thật**, PASS với test count hợp lệ | Consumer test với stub hoặc test base fake response |
| **Consumer đang vận hành có hiểu hành vi ứng viên không?** | Consumer client/handler **thật** chạy với **stubs của đúng candidate**, assert kết quả | Producer test xanh hoặc consumer unit test dùng Mockito |

Ba câu hỏi có quan hệ nhưng **không thay thế nhau**. Có thể đã thỏa thuận contract nhưng implementation chưa xong. Có thể implementation đáp ứng contract mới nhưng consumer cũ bị phá. Có thể consumer test xanh nhưng artifact Stub Runner tải vẫn là phiên bản cũ.

Một định nghĩa có ích cho nhóm:

> **Contract được kiểm chứng cho một cặp phiên bản** khi có bằng chứng producer candidate đáp ứng contract và consumer version nằm trong phạm vi hỗ trợ xử lý đúng stub được tạo từ **chính contract candidate đó**.

Định nghĩa này **không đồng nghĩa chứng minh toàn bộ production end-to-end**. Auth, mạng, database, broker topology, timeout, concurrency và chất lượng vận hành còn cần các lớp kiểm thử khác.

## 3. Một ví dụ xuyên suốt: Inventory và Checkout

Giả sử Checkout cần tra tồn kho SKU-123:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

Contract **v1** quy định:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-123",
  "available": true,
  "quantity": 12
}
~~~

Nhóm Inventory muốn đổi sang **v2**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-123",
  "inStock": true,
  "quantity": 12
}
~~~

Nếu Checkout đang deserialize `available` vào `Boolean available` và yêu cầu nó không null, xóa field này có thể là **breaking change**. Chỉ nhìn response của v2 có vẻ hợp lý không cho thấy Checkout cũ có hiểu được nó hay không.

Một lộ trình an toàn hơn là **giai đoạn chuyển tiếp**:

~~~json
{
  "sku": "SKU-123",
  "available": true,
  "inStock": true,
  "quantity": 12
}
~~~

Sau khi consumer cũ được nâng cấp và không còn phụ thuộc `available`, producer mới có thể xem xét bỏ trường đó theo lịch deprecation. Nhưng **thêm field mới cũng không phải luôn vô hại**: consumer dùng strict unknown-property policy hoặc schema closed có thể fail. Phải kiểm tra **những consumer thật trong phạm vi hỗ trợ**.

Bài sẽ dùng ví dụ này để đối chiếu hợp đồng đề xuất, producer tests, stub ứng viên, consumer tests và release gate.

## 4. Trạng thái vòng đời hợp đồng: quy ước phối hợp, không phải trạng thái mặc định của SCC

Một nhóm nên công bố một bộ trạng thái dễ hiểu:

| Trạng thái quy trình đề xuất | Ý nghĩa | Ai xác nhận? |
|---|---|---|
| **Draft** | Ý tưởng hoặc hợp đồng nháp, semantics chưa thống nhất | Người đề xuất |
| **Proposed** | Có PR, API examples và consumer requirements | Consumer owner |
| **Reviewed** | Producer và consumer đã review request/response, lỗi, versioning | Hai bên cùng tham gia |
| **Accepted** | Chấp thuận cách contract sẽ vận hành và mốc migration | API/contract owners |
| **Producer-verified** | Generated tests chạy trên producer candidate code và đạt | Producer CI |
| **Stub-published** | Artifact stubs candidate được đóng gói và truy vết nguồn gốc | Producer pipeline |
| **Consumer-verified** | Consumer versions cần hỗ trợ chạy với đúng candidate stub và đạt | Consumer CI/owners |
| **Release-approved** | Các gates và ràng buộc triển khai đã đạt | Release owner |
| **Deprecated/Retired** | Hợp đồng cũ có kế hoạch bỏ và bằng chứng không còn consumer phụ thuộc | API owner + consumers |

Đây là **quy ước nhóm**, **không phải danh sách trạng thái dựng sẵn trong Spring Cloud Contract**. Không nên tự thêm các trạng thái này vào một schema DSL nếu công cụ không hỗ trợ; có thể quản lý qua PR labels, ticket, contract metadata ngoài DSL hoặc release records.

Không được đổi nhãn **Draft → Verified** chỉ vì YAML parse được hoặc một consumer tự viết stub và test xanh. Mỗi lần chuyển trạng thái phải đi kèm **bằng chứng phù hợp**.

## 5. Quyền sở hữu: ai chịu trách nhiệm điều gì?

| Vai trò | Trách nhiệm chính | Không nên làm một mình |
|---|---|---|
| **Producer team** | Thực thi API/message, giữ generated producer tests, phát hành stubs đúng implementation | Đơn phương xóa field đang được consumer dùng |
| **Consumer team** | Mô tả yêu cầu giao tiếp, kiểm tra client/handler thật, cảnh báo migration | Tự sửa contract rồi coi producer đã triển khai |
| **Contract/API owner** | Điều phối schema, versioning, compatibility policy | Chấp thuận breaking change mà không xét consumers |
| **QA/contract test maintainer** | Review coverage, mutation, negative tests, tránh zero-tests | Dùng mock thay code thật rồi tuyên bố production an toàn |
| **CI/repository owner** | Cấp artifact identity, quyền publish/read, retention, traceability | Để candidate SNAPSHOT mutable hoặc fallback âm thầm |
| **Release owner** | Ra quyết định rollout/rollback từ đủ gates | Dựa duy nhất vào một kết quả PASS thiếu provenance |

Một producer có nhiều consumer. Vì vậy, “consumer A chấp nhận contract mới” **không chứng minh** consumer B/C còn tương thích. Cần có **danh sách consumer được hỗ trợ**, kể cả các phiên bản đang chạy ngoài production hoặc tại khách hàng nếu chính sách hệ thống yêu cầu.

## 6. Single source of truth cho hợp đồng đang phát triển

Có nhiều mô hình tổ chức hợp đồng:

1. **Producer-owned contracts:** hợp đồng được đặt ngay trong repository producer; consumer gửi PR để đề xuất behavior.
2. **Consumer-driven contracts:** các consumer đóng góp contract và producer kiểm chứng chúng theo workflow có phê duyệt.
3. **Shared contract repository:** hai bên dùng một nguồn contract versioned, được CI đồng bộ/consume chính xác.

Không có một lựa chọn phù hợp cho mọi tổ chức. Dù chọn cách nào, cần bảo đảm:

- Chỉ có **một revision được xem là nguồn chính thức** cho một candidate/release.
- Mọi bên biết contract commit/version được áp dụng.
- Contract PR có **producer + consumer review** khi thay đổi giao tiếp.
- Generated producer tests và published stubs có thể truy về **cùng revision**.
- Consumer test dùng **exact candidate stubs artifact** chứ không dùng local fixture tự ý chỉnh.
- Không có hai bản copy Groovy/YAML âm thầm lệch nhau mà vẫn được gọi chung là một contract.

**Phản ví dụ:** consumer lưu `contracts/new-inventory.yml` riêng, producer lưu `contracts/old-inventory.groovy` riêng, cả hai test đều xanh với fixture của mình. Khi đó không có bằng chứng hai phía đang kiểm tra **cùng một thỏa thuận**.

## 7. Phân biệt “đang phát triển” với “đang được công bố”

Một thay đổi có thể được mô tả bằng DSL nhưng chưa nên xuất hiện trong stub artifact được nhóm khác coi là stable.

Ví dụ:

~~~text
Contract PR A (draft):
  GET /api/inventory/SKU-123 -> {"inStock":true}

Producer release hiện tại:
  GET /api/inventory/SKU-123 -> {"available":true}
~~~

Nếu Stub Runner tự động lấy `latest` hoặc SNAPSHOT trên nhánh phát triển và consumer test chạy với A, kết quả có thể phản ánh **API chưa triển khai**. Ngược lại, consumer test chạy với stable stub v1 không đánh giá được draft v2.

Quy ước khuyến nghị:

- **Draft/proposed:** để review, ví dụ và thiết kế; có thể sinh stub **thử nghiệm**, nhưng phải gắn nhãn **unverified**.
- **Producer-verified candidate:** chỉ sau khi generated tests đạt với producer implementation cùng commit mới được dùng làm **candidate compat artifact**.
- **Released:** đã qua gates tương thích và publication policy; artifact ổn định, không tự ghi đè.
- **Deprecated:** vẫn được phục vụ trong thời gian migration đã cam kết, không xóa chỉ vì API mới đã xuất hiện.

Không để stub thử nghiệm của một consumer bị hiểu thành artifact đã được producer xác nhận.

## 8. Phân biệt test giả định thiết kế và test chứng minh tương thích

Một consumer có thể dùng stub do mình viết để phát triển tính năng **trước khi producer hoàn thành**. Điều này là hợp lý nếu gọi đúng tên:

| Loại test | Dữ liệu dùng | Kết luận hợp lệ |
|---|---|---|
| **Design/mock test** | Consumer tự dựng response tương lai | Client/UI có thể xử lý giả định nếu producer sau này cung cấp đúng |
| **Producer contract verification** | Generated test từ contract, chạy producer candidate thật | Producer implementation đáp ứng thỏa thuận |
| **Consumer compatibility test** | Stubs từ contract producer đã kiểm chứng, chạy consumer client thật | Consumer tương thích với behavior artifact cụ thể |
| **Deployment/E2E test** | Hệ thống thật và hạ tầng phù hợp | Hành vi tích hợp ở phạm vi môi trường test |

Một **design stub** không xấu; sai ở việc **gắn nhãn “contract verified”** cho nó. Cần một cổng chuyển tiếp rõ: khi producer hoàn thành, thay design stub bằng **producer-published candidate stubs** và chạy lại cùng consumer tests.

## 9. Luồng phối hợp hai nhóm từ ý tưởng tới release

~~~mermaid
sequenceDiagram
    participant C as Nhóm Checkout
    participant P as Nhóm Inventory
    participant R as Contract/Artifact Repository
    participant CI as Consumer CI
    C->>P: Đề xuất field inStock + error cases
    P-->>C: Review semantics và compatibility
    C->>P: Thống nhất contract PR/revision
    P->>P: Implement + generated producer tests
    P->>R: Publish candidate stubs đúng commit
    R-->>CI: Exact artifact + provenance
    CI->>CI: Stub Runner + Checkout client thật
    CI-->>C: Compatibility report PASS/FAIL
    C-->>P: Review lỗi/migration nếu cần
    P->>P: Release gate/rollout sau khi đạt
~~~

Mọi mũi tên cần có **artifact hoặc bằng chứng**:

- Đề xuất: API example, request/response, errors, owner và deadline.
- Review: xác nhận field type, nullability, versioning, negative cases.
- Producer build: test reports với **executed contract tests > 0**.
- Publish: tọa độ artifact + checksum + commit.
- Consumer CI: test report, client target URL, stubs version.
- Release: matrix supported consumers, rollout/rollback và deprecation plan.

## 10. Các phần contract phải thống nhất trong review

Một contract HTTP không chỉ là ví dụ JSON body. Checklist review gồm:

| Phần | Câu hỏi |
|---|---|
| HTTP method/path | GET/POST? URL hay path variable có thay không? |
| Query parameters | Bắt buộc hay tùy chọn? Giá trị mặc định/encoding? |
| Request headers | `Accept`, `Content-Type`, auth headers và version headers? |
| Request body | Tên field, kiểu JSON, nullability, validation, defaults? |
| Success status | 200, 201, 202, 204 hay response khác? |
| Response headers | Content-Type, caching headers, correlation IDs? |
| Response body | Field bắt buộc, number/string, enum, timestamps, money format? |
| Error schema | Status + error code + message, retryability? |
| Compatibility | Field cũ có còn? Consumer cũ có hiểu field mới? |
| Idempotency | Khi POST retry, request idempotency key có yêu cầu? |
| Auth/security | Contract không mặc nhiên kiểm tra toàn bộ security topology |
| Messaging | Event name, destination, headers, key, schema version, retry/DLQ? |
| Dynamic data | Matcher đủ chặt hay vô tình chấp nhận dữ liệu sai? |

**Chỉ review một response happy path thường là không đủ**. Một consumer cũng có thể bị phá do thay đổi error code, HTTP 204 thay 200, enum value, content type hoặc behavior khi thiếu dữ liệu.

## 11. Ví dụ Groovy contract ứng viên chưa tương thích

Giả sử hai nhóm đề xuất API response chỉ chứa `inStock`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Inventory candidate tra tồn kho SKU-123'

    request {
        method GET()
        url '/api/inventory/SKU-123'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-123',
            inStock: true,
            quantity: 12
        )
    }
}
~~~

Contract này **chưa tự chứng minh producer code mới đã trả `inStock`**. Nó chỉ là khai báo hành vi. Producer phải chạy generated tests với code thực; nếu chưa triển khai, generated tests phải đỏ — đó là tín hiệu đúng để ngăn phát hành artifact đã xác nhận.

Đồng thời, một consumer đang dùng DTO:

~~~java
public record StockResponse(
        String sku,
        Boolean available,
        Integer quantity) {
}
~~~

có thể parse body mới nhưng `available == null`. Nếu consumer chỉ dùng primitive `boolean`, dữ liệu thiếu có thể bị mặc định thành false tùy Jackson config, che breaking change. Consumer contract test nên có **validation về field bắt buộc**, không chỉ assert HTTP 200.

## 12. Contract YAML của giai đoạn chuyển tiếp

Một ứng viên hỗ trợ migration có thể tạm giữ field cũ và thêm field mới:

~~~yaml
description: Inventory trong giai đoạn chuyển field
name: inventory_stock_migration

request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    inStock: true
    quantity: 12
~~~

Mục tiêu của giai đoạn chuyển tiếp:

- Consumer cũ vẫn có thể đọc `available`.
- Consumer mới có thể đọc `inStock`.
- Producer verification bảo đảm **cả hai field** có mặt và nhất quán, nếu đó là contract đã thống nhất.
- Consumer compatibility matrix kiểm tra những phiên bản đang cần hỗ trợ.
- Chỉ sau khi không còn consumer phụ thuộc `available` và lịch deprecation được chấp thuận mới xét bỏ nó.

**Nhưng thêm field không luôn tương thích với mọi consumer:** một số JSON deserializer được cấu hình strict unknown properties. Vì vậy **không chỉ suy luận**, cần chạy consumer tests với stubs ứng viên.

## 13. Thay đổi nào thường gây breaking change?

| Thay đổi của producer | Mức rủi ro | Kiểm tra cần có |
|---|---|---|
| Thêm response field tùy chọn | Thường có thể tương thích | Consumer unknown-field policy |
| Xóa/đổi tên field bắt buộc | **Cao** | Consumer DTO/validation |
| Đổi number thành string | **Cao** | Serialization/deserialization strict types |
| Thêm enum value | Có thể breaking | Consumer xử lý unknown enum |
| Đổi 200 thành 204 | Có thể breaking | Consumer có yêu cầu body không? |
| Đổi error code dù status giữ nguyên | Có thể breaking | Error mapping của consumer |
| Thêm required request header | **Cao** | Consumer có gửi header? |
| Thêm required request body field | **Cao** | Consumer cũ có gửi field? |
| Siết validation input | **Cao** với request cũ | Negative/request compatibility tests |
| Nới validation input | Thường dễ tương thích hơn | Security/business invariants |
| Đổi message event name/destination | **Cao** | Consumer binding/listener |
| Thêm field trong message | Tùy schema policy | Schema evolution và converter |
| Đổi timestamp/locale/timezone semantics | **Cao** | Tests ở biên thời gian |
| Thay authentication/version header | **Cao** | Security/integration tests |

Không có quy tắc “mọi field thêm đều non-breaking” hoặc “mọi version tăng đều breaking”. Phải đánh giá theo **consumer contract** và chính sách compatibility đã công bố.

## 14. Xác nhận giả loại A: consumer test dùng stub tự viết

Một dạng test dễ gây ngộ nhận:

~~~java
// Ví dụ tư duy: test stub do consumer tự cấu hình.
stubFor(get(urlEqualTo("/api/inventory/SKU-123"))
    .willReturn(okJson("""
        {"sku":"SKU-123","inStock":true,"quantity":12}
    """)));
~~~

Nếu Checkout client đọc `inStock` và test xanh, kết luận đúng là:

> Code Checkout tương thích với **response giả định đã tự cấu hình**.

Kết luận **không hợp lệ** là:

> Inventory producer đã triển khai và cam kết response ấy.

Để loại bỏ khoảng trống, cần:

1. Đưa proposal vào contract source/revision được hai nhóm thống nhất.
2. Producer chạy SCC generated tests với implementation thật.
3. Publish stubs artifact từ **cùng revision** sau khi producer tests đạt.
4. Consumer chạy lại **client thật** với artifact ứng viên đó qua Stub Runner.
5. Ghi kết quả và provenance.

Stub tự viết vẫn có thể hữu ích cho **TDD và khám phá thiết kế**, nhưng phải được phân loại là **design test**, không phải release gate xác nhận producer.

## 15. Xác nhận giả loại B: producer verifier chạy trên fake implementation

Trong Spring MVC, test base có thể được cấu hình sai:

~~~java
// Phản ví dụ: controller giả tự trả đúng body mẫu.
@BeforeEach
void wrongSetup() {
    RestAssuredMockMvc.standaloneSetup(
        new FakeInventoryController()
    );
}
~~~

Nếu `FakeInventoryController` trả đúng JSON của contract, generated producer test luôn có thể xanh dù controller production đã lỗi.

Mục tiêu đúng:

~~~java
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class InventoryContractBase {
    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    void setup() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

Ở đây generated tests phải thực sự đi qua **Spring context và controller/service production** mà contract cần bảo vệ. Có thể thay thế dependency bên ngoài hoặc chuẩn bị data fixture, nhưng **không nên mock chính behavior được công bố**.

**Phép thử đối chứng:** cố ý thay implementation để `available` trả sai; generated producer test phải chuyển đỏ. Nếu không, xem lại base test, mock beans và số test đã chạy.

## 16. Xác nhận giả loại C: test bị skip hoặc không có generated tests

Một build có thể hiển thị:

~~~text
BUILD SUCCESS
Tests run: 0
~~~

hoặc chỉ chạy unit tests không liên quan đến contract. Nguyên nhân:

- Maven plugin chưa được kích hoạt hoặc `contractsDirectory` trỏ sai.
- Gradle plugin áp dụng ở parent/root thay vì producer module.
- Contract files không được parse/generate, nhưng build không fail theo policy.
- JUnit version/test runner không khớp với generated Java.
- Surefire/Failsafe pattern không tìm thấy tên generated test.
- Test bị bỏ qua bởi `-DskipTests`, `-Dmaven.test.skip=true`, `-DskipITs`, Gradle exclusions hoặc profiles.
- Pipeline chạy `mvn package`/`gradle build` với cờ skip, rồi publish stub.
- Report chỉ đếm **unit tests tổng**, không kiểm tra **contract tests thực thi**.

Một guard tốt cần ít nhất ba bằng chứng:

1. **Contract source discovered > 0** nếu module producer bắt buộc có hợp đồng.
2. **Generated producer test sources** xuất hiện và compile thành công.
3. **Executed generated producer tests > 0**, không có failures và không bị skip ngoài chủ đích.

Ví dụ các lệnh **tham khảo** cho producer đã cấu hình plugin:

~~~bash
# Với Maven:
./mvnw clean verify

# Với Gradle:
./gradlew clean test
~~~

Những lệnh này **không tự chứng minh** tests có chạy; vẫn phải đọc Surefire/Failsafe hoặc Gradle test reports và generated sources. Không chạy các lệnh trong bước biên soạn bài này.

## 17. Xác nhận giả loại D: matcher quá rộng

Một contract/stub chỉ kiểm tra method/path nhưng bỏ qua request body có thể chấp nhận những request sai.

Ví dụ mapping WireMock **quá rộng**:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations"
  },
  "response": {
    "status": 201,
    "jsonBody": {
      "reservationId": "R-1001",
      "status": "RESERVED"
    }
  }
}
~~~

Consumer có thể gửi:

~~~json
{"productCode":"SKU-123","quantity":"2"}
~~~

trong khi producer yêu cầu:

~~~json
{"sku":"SKU-123","quantity":2}
~~~

Cả hai request vẫn có thể nhận HTTP 201 với mapping rộng đó. Consumer test xanh nhưng **không kiểm tra serialization của DTO**.

Một mapping **chặt hơn theo hợp đồng** có thể yêu cầu JSON semantic matching:

~~~json
{
  "request": {
    "method": "POST",
    "url": "/api/reservations",
    "headers": {
      "Content-Type": {
        "contains": "application/json"
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
      "status": "RESERVED"
    }
  }
}
~~~

Đây là **mapping WireMock minh họa**; SCC có thể sinh các predicate khác theo DSL/plugin version. Hãy mở mapping thực tế thay vì giả định generator luôn dùng `equalToJson`.

Nếu API cho phép dữ liệu động, dùng JSONPath/regex matchers **đủ chặt theo kiểu và phạm vi giá trị**. Regex `.*` không phải ràng buộc có ý nghĩa nếu trường quan trọng cần tuân thủ pattern hoặc format. Nhưng cũng **không siết các giá trị tùy ý** như request ID/timestamp đến mức làm test flaky: matcher phải bảo vệ **cam kết thực sự**, không bảo vệ chi tiết nội bộ không quan trọng.

## 18. Xác nhận giả loại E: consumer client bị mock

Ví dụ:

~~~java
// Phản ví dụ: kiểm thử business branch, không phải compatibility.
when(inventoryClient.getStock("SKU-123"))
    .thenReturn(new StockResponse("SKU-123", true, 12));

CheckoutPreview result = checkout.preview("SKU-123", 2);
assertThat(result.canCheckout()).isTrue();
~~~

Test này có thể có ích cho **unit test orchestration**, nhưng không đi qua HTTP client thực. Do đó nó không phát hiện:

- Client gửi sai HTTP method/path/query;
- Content-Type/Accept header không đúng;
- JSON serialization đổi tên field;
- Response deserialization xử lý null/sai kiểu;
- Error mapping 404/503 bị nhầm;
- Stub Runner đang nạp version nào.

Để gọi là **consumer compatibility test**, phải giữ **client production** và thay **producer runtime** bằng stubs. Khi dùng WebClient/RestClient/Feign hoặc message consumer, cần kiểm tra đúng adapter/handler thực của ứng dụng.

**Nguyên tắc:** mock **bên ngoài ranh giới HTTP/message của consumer** khi thích hợp, đừng mock chính ranh giới cần kiểm chứng.

## 19. Xác nhận giả loại F: stub cũ của hợp đồng mới

Một dạng rất phổ biến khi phối hợp nhiều repository:

~~~text
Inventory commit A:
  Contract A trả available
  Stubs JAR: inventory-service:1.3.0:stubs

Inventory commit B:
  Contract B trả inStock
  Stubs JAR: inventory-service:1.4.0-rc.pr173:stubs

Checkout CI:
  Vẫn khai báo inventory-service:1.3.0:stubs
  Kết quả: PASS
~~~

PASS ở đây chỉ chứng minh Checkout tương thích với **A**, không phải B. Cần truyền tọa độ artifact B từ producer PR pipeline tới consumer job.

Với SNAPSHOT mutable, vấn đề tinh vi hơn:

~~~text
com.example:inventory-service:1.4.0-SNAPSHOT:stubs
~~~

Tọa độ logical giống nhau nhưng Maven metadata, local cache, repository proxy hoặc WireMock process có thể khiến consumer nạp phiên bản khác. Cần xác nhận **resolved timestamp/digest/commit**, không chỉ tên SNAPSHOT.

**Khuyến nghị release gate:** dùng **unique candidate version gắn commit/build** và repository chặn redeploy cùng tọa độ với bytes khác. Không dùng latest/`+` không kiểm soát để chứng minh một PR cụ thể đã được kiểm tra.

## 20. Xác nhận giả loại G: producer tự sửa contract cho khớp code sai

Trong quá trình nâng cấp, producer vô tình làm response đổi từ `quantity:12` thành `quantity:"12"`. Một nhóm có thể sửa ngay contract thành kiểu string để test xanh mà không tham khảo consumer.

Đó không phải “sửa test” đơn thuần; đó là **thay đổi giao diện công khai**. Quy trình phù hợp:

1. Xác định failure đến từ implementation regression hay contract requirement thật sự đổi.
2. Nếu code sai: sửa code để đáp ứng **contract đã chấp nhận**.
3. Nếu API cần thay đổi: mở **contract change proposal**, mô tả lý do và migration.
4. Consumer owners review khả năng deserialize/validation.
5. Producer và consumer tests dùng cùng candidate.
6. Release gate chỉ mở khi thay đổi được chấp thuận và có bằng chứng tương thích.

Không để một người sửa expected response để test xanh mà không có **diff contract**, **review** và **ảnh hưởng downstream**.

## 21. Xác nhận giả loại H: chỉ kiểm tra happy path

Một API có thể đúng trong trường hợp 200 nhưng sai ở các tình huống lỗi:

~~~http
GET /api/inventory/SKU-404 HTTP/1.1
Accept: application/json
~~~

Contract business error:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"code":"SKU_NOT_FOUND","message":"SKU does not exist"}
~~~

Nếu producer đổi `code` thành `ITEM_UNKNOWN` mà consumer vẫn map `SKU_NOT_FOUND`, HTTP status 404 **chưa đủ để kết luận tương thích**.

Cần các scenarios theo rủi ro:

| Scenario | Hành vi cần test |
|---|---|
| `200` còn hàng | DTO đúng và các field bắt buộc tồn tại |
| `200` hết hàng | False/zero được phân biệt với missing/null |
| `404 SKU_NOT_FOUND` | Consumer trả lỗi “không có SKU” |
| `503 INVENTORY_UNAVAILABLE` | Consumer xử lý unavailable, không nhầm not found |
| `422 INVALID_QUANTITY` | Validation response đúng schema |
| Timeout/connection refused | Transport error không bị chuyển thành business 404 |
| Unmatched WireMock 404 | Không bị xem là business 404 |
| Message duplicate/unknown enum | Consumer behavior theo chính sách |

**Không phải mọi network fault đều cần nằm trong contract artifact chuẩn**. Contract nên chứa behavior mà producer cam kết; resilience/negative protocol cases có thể thuộc bộ test riêng. Quan trọng là không dùng happy-path PASS thay cho bằng chứng mọi error path đã được xử lý.

## 22. Business 404 và unmatched WireMock 404

WireMock có thể trả HTTP 404 khi không tìm thấy mapping cho request sai path/header/body. Trường hợp đó khác với **business 404** từ hợp đồng.

| HTTP response | Nguyên nhân | Cách consumer nên hiểu |
|---|---|---|
| 404 + `{"code":"SKU_NOT_FOUND"}` | Producer cam kết SKU không tồn tại | Domain NotFound |
| 404 + body chẩn đoán WireMock | Request không match stub | Test/protocol mismatch |
| 404 + code khác | API error khác hoặc sai schema | Không tự xem là SKU_NOT_FOUND |
| Connection refused | Không có HTTP response | Transport failure |
| 503 + `INVENTORY_UNAVAILABLE` | Producer/gateway báo unavailable theo contract | Retry/fallback theo policy |

Nếu client viết:

~~~java
// Phản ví dụ: đánh đồng mọi HTTP 404.
if (status == 404) {
    throw new InventoryNotFoundException("No stock");
}
~~~

thì khi client gửi **URL sai**, test có thể bị chuyển thành “SKU không tồn tại” thay vì báo lỗi request mismatch.

Trong consumer test, nên assert **status + mã lỗi + body** và, khi cần, xem WireMock request journal/near misses để xác định request thực sự match contract.

## 23. Phối hợp qua contract PR thay vì trao đổi bằng tin nhắn rời rạc

Một PR hợp đồng có thể dùng mẫu mô tả:

~~~text
Title: Inventory response adds inStock, deprecates available

Owner: Inventory API team
Affected consumers: Checkout v3, Cart v2, Analytics v1
Proposed behavior:
  GET /api/inventory/{sku}
  200 JSON: sku, quantity, available, inStock

Existing behavior:
  200 JSON: sku, quantity, available

Compatibility:
  - Keep available during migration.
  - Do not remove it before supported clients migrate.

Error contract:
  - 404: SKU_NOT_FOUND
  - 503: INVENTORY_UNAVAILABLE

Producer verification:
  - Contract tests generated/executed: pending
  - Commit/revision: pending

Candidate stubs:
  - Artifact/version/digest: pending

Consumer compatibility:
  - Checkout v3: pending
  - Cart v2: pending
  - Analytics v1: pending

Rollout/rollback:
  - Deploy additive fields first.
  - Move consumers to inStock.
  - Remove available only after explicit approval.
~~~

Các trạng thái `pending` trong PR là **thực tế chưa có bằng chứng**, không nên thay bằng PASS trước khi job hoàn tất. Tên field, consumer list và chính sách ở trên là **ví dụ**, không phải tiêu chuẩn cố định của SCC.

### PR review nên hỏi gì?

- Người đề xuất có mô tả **wire format** cụ thể chưa?
- Có ví dụ **request** và **success/error responses** chưa?
- Những consumer nào sẽ bị ảnh hưởng và đang dùng version nào?
- Đã đánh giá backward/forward compatibility chưa?
- Có đủ fixture/producer-state để generated tests chạy **code thật** không?
- Candidate stub có được tạo từ cùng revision không?
- CI có chứng minh consumer versions được hỗ trợ tương thích không?
- Kế hoạch rollback có khả thi khi producer đã phát message/state mới?

## 24. Expand–migrate–contract: giảm rủi ro thay đổi phá vỡ

Với thay đổi tên field, quy trình phổ biến:

~~~mermaid
flowchart LR
    A["Expand: Producer thêm inStock, giữ available"] --> B["Verify producer + consumers"]
    B --> C["Migrate: Consumer dần chuyển sang inStock"]
    C --> D["Theo dõi và xác nhận không còn consumer dùng available"]
    D --> E["Contract: Chấm dứt hỗ trợ available theo kế hoạch"]
    E --> F["Verify lại mọi consumer cần hỗ trợ"]
~~~

### Giai đoạn 1 — Expand

Producer vẫn trả `available`, thêm `inStock` theo semantics đã review. Contract cập nhật và generated producer tests bảo vệ cả hai field. Consumer cũ và mới chạy với candidate stub tương ứng.

### Giai đoạn 2 — Migrate

Consumer team nâng cấp DTO/handler và triển khai từng bước. CI kiểm tra **cả ứng viên consumer lẫn những consumer versions vẫn chạy** theo policy. Monitor/telemetry được dùng để xác nhận adoption nếu có thể.

### Giai đoạn 3 — Contract

Chỉ khi deprecation window, danh sách consumer và migration criteria đạt mới loại bỏ `available`. Khi bỏ field, generated producer tests mới phải bảo vệ giao diện mới; consumer tests phải chạy với **stub mới**.

**Rủi ro cần quản lý:** đối với message brokers có lưu trữ event cũ, consumer mới còn có thể đọc dữ liệu từ **schema cũ tồn tại trong topic/queue**. Chỉ kiểm tra event mới chưa đủ; phải xét backward/forward schema compatibility, replay và retention.

## 25. Compatibility matrix cho nhiều consumer versions

Một producer có thể phục vụ nhiều phiên bản consumer:

| Producer candidate | Checkout v3 | Cart v2 | Analytics v1 | Kết luận |
|---|---|---|---|---|
| V1, field `available` | PASS | PASS | PASS | Đang hỗ trợ |
| V2 additive, có cả hai field | PASS | PASS | PASS giả định sau khi test | Có thể tiếp tục nếu kiểm chứng thực |
| V3, chỉ `inStock` | PASS với Checkout mới | FAIL với Cart cũ | Chưa chạy Analytics | Chưa đủ điều kiện loại bỏ field |

**Giá trị PASS/FAIL trong bảng là ví dụ minh họa**, không phải test report của một dự án thật. Cách dùng matrix:

1. Liệt kê **consumer versions đang được hỗ trợ**, không chỉ main branch của mỗi repo.
2. Gắn mỗi cột vào **một build/commit consumer cụ thể**.
3. Gắn mỗi hàng producer vào **candidate artifact cụ thể**.
4. Chạy client/handler thật của từng consumer với candidate.
5. Ghi status cho mỗi ô: PASS, FAIL, NOT RUN, NOT APPLICABLE, BLOCKED.
6. Không chuyển **NOT RUN** thành PASS.
7. Định nghĩa policy: cần mọi consumer production PASS, hay chỉ tập được support có cam kết khác.

Matrix giúp phát hiện một nguy cơ: nhóm producer kiểm tra với Checkout mới nhất nhưng bỏ qua Analytics v1 vẫn đang vận hành.

## 26. Test đối chứng: làm thay đổi sai để chứng minh test chuyển đỏ

Một bộ kiểm thử có giá trị phải **nhạy với lỗi mà nó tuyên bố bảo vệ**.

### Đối chứng producer

Trong nhánh thử, đổi implementation producer từ:

~~~java
return new StockResponse("SKU-123", true, 12);
~~~

thành:

~~~java
// Cố ý sai để thử khả năng phát hiện lỗi:
return new StockResponse("SKU-123", false, 12);
~~~

Nếu contract vẫn cam kết `available=true`, generated producer test phải fail. Nếu test xanh, kiểm tra test count, base class fake, mocks và test mode.

### Đối chứng consumer

Giữ stub candidate nhưng trong client đổi path:

~~~text
Đúng: GET /api/inventory/SKU-123
Sai:  GET /api/stock/SKU-123
~~~

Consumer test phải fail vì request không match, thay vì âm thầm map unmatched WireMock 404 thành business NotFound.

### Đối chứng schema evolution

Cho producer candidate xóa `available`; chạy **consumer cũ** với stub candidate. Test phải phát hiện field bắt buộc mất hoặc behavior sai. Nếu pass, xem DTO primitive/default, assertions và artifact identity.

### Đối chứng cache/stub

Thay request/response fingerprint trong candidate và xác nhận stub trả dữ liệu mới; nếu response vẫn cũ, điều tra cache/resolver/process.

**Lưu ý:** mutation chỉ thực hiện trong nhánh/môi trường thử, không merge code cố tình sai; khôi phục code rồi chạy test lại.

## 27. Bảo vệ test bằng assertions có giá trị nghiệp vụ

Một test như:

~~~java
assertThat(response).isNotNull();
~~~

thường quá yếu để phát hiện breaking change. Nó không chứng minh quantity, availability, error mapping hoặc ID khớp.

Đối với Checkout preview, nên kiểm tra:

~~~java
CheckoutPreview preview = checkout.preview("SKU-123", 2);

assertThat(preview.sku()).isEqualTo("SKU-123");
assertThat(preview.canCheckout()).isTrue();
assertThat(preview.requestedQuantity()).isEqualTo(2);
assertThat(preview.subtotalVnd()).isEqualTo(300_000L);
~~~

Đoạn này giả định `CheckoutPreview` chứa các accessor tương ứng và là **kiểu của ứng dụng minh họa**, không phải SCC API.

Các assertions nên phản ánh **điều consumer thực sự phụ thuộc**:

- Field bắt buộc tồn tại và không null;
- Number/boolean/string giữ đúng kiểu;
- Error code được map thành domain exception đúng;
- Response gắn đúng request ID/SKU;
- Price/quantity calculation có ý nghĩa;
- Unknown enum/field policy được tuân thủ;
- Message handler không bỏ qua event sai schema âm thầm.

Không viết assertions bằng cách copy toàn bộ stub expected body vào test rồi chỉ so raw response khi mục tiêu là kiểm chứng **behavior consumer**. So raw JSON có thể bổ sung, nhưng phải kiểm tra DTO/business logic thật.

## 28. Messaging contracts: vì sao xác nhận giả còn dễ xảy ra?

Spring Cloud Contract hỗ trợ message contracts, ví dụ producer phát `InventoryChanged`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'inventoryChanged'

    input {
        triggeredBy('triggerInventoryChanged()')
    }

    outputMessage {
        sentTo('inventory.events')

        body(
            eventId: 'evt-demo-101',
            eventType: 'InventoryChanged',
            sku: 'SKU-123',
            available: true
        )
    }
}
~~~

Để producer verification có giá trị:

- Generated test cần gọi **trigger method** từ base test hoặc test support.
- Trigger phải kích hoạt **production application logic** thực sự phát message.
- Message verifier/test binder phải nhận được **output do producer phát**, không phải payload do chính test tự tạo.
- Destination/header/body matchers phải thể hiện giao tiếp mà consumer cần.
- Test timeout và cleanup phải rõ để tránh nhận nhầm message từ test khác.

**Xác nhận giả:** `triggerInventoryChanged()` chỉ gọi test sink gửi đúng JSON mẫu, không hề gọi business service. Generated test xanh nhưng producer runtime không chắc phát được event đó.

Consumer side cũng phải kiểm tra **handler thật** deserialize event và xử lý đúng state/error, không chỉ assert payload sample có thể parse bởi một ObjectMapper unit test.

## 29. Những giới hạn phải công bố rõ khi test đạt

Ngay cả với hai cổng producer/consumer pass, các rủi ro sau vẫn có thể nằm ngoài phạm vi test:

| Lớp | Vì sao contract stub chưa đủ? | Test bổ sung thường cần |
|---|---|---|
| TLS, proxy, DNS, service discovery | Stub thường chạy localhost/test network | Deployment/network integration |
| Authentication/authorization | Test có thể bypass security filters hoặc dùng token test | Security integration |
| Database state và transaction | Stub response không phụ thuộc DB thật | Producer integration/E2E |
| API performance/latency | WireMock trả nhanh | Performance/resilience |
| Timeout, retry, circuit breaker | Stub không tự mô phỏng fault | Fault injection tests |
| Message broker topology | Stub message không chứng minh exchange/partition thật | Broker integration |
| Event ordering/duplicate delivery | Một message sample không chứng minh distributed semantics | Messaging concurrency tests |
| Runtime config drift | Consumer test URL khác production | Configuration validation |
| Contract compatibility với mọi version | CI chỉ chạy matrix đã cấu hình | Inventory consumer versions/support policy |

**Không gọi một cặp contract tests là bảo đảm toàn bộ hệ thống an toàn**. Kết luận đúng là **tương thích trong phạm vi contract, version, scenario và môi trường đã được kiểm chứng**.

## 30. Khi contract thay đổi nhanh: tránh biến review thành nút thắt

Đội phát triển thường muốn feedback nhanh nhưng cũng không muốn bỏ review. Một workflow cân bằng:

1. **Design preview:** consumer đề xuất Groovy/YAML và sample request/response, có design stub tạm; nhãn unverified.
2. **Producer feasibility check:** xác nhận path, schema, validation, error cases và khả năng triển khai.
3. **Automated syntax/generation check:** CI bảo đảm contract parse, generated tests được tạo.
4. **Producer implementation PR:** code và contract thuộc cùng revision được kiểm chứng.
5. **Candidate artifact publication:** version duy nhất, provenance rõ, không dùng mutable latest.
6. **Targeted consumer checks:** chạy affected consumers trước; không bỏ các bản production trong scope.
7. **Compatibility gate:** block nếu consumer fail hoặc chưa có bằng chứng bắt buộc.
8. **Release coordination:** deploy additive producer trước consumer migration, theo dõi, rồi remove field sau deprecation.

Để feedback nhanh, có thể dùng **nhóm affected consumers** dựa trên phụ thuộc API, rồi chạy full matrix trước release. Nhưng danh sách affected consumers phải **có nguồn và được cập nhật**, không đoán theo repo gần nhất.

Đối với các contract thay đổi không liên quan (ví dụ thêm endpoint mới chưa consumer nào dùng), có thể áp policy khác với breaking change trên endpoint đang phục vụ production. Điều kiện là **được ghi thành quy tắc cụ thể**, không tùy tiện bỏ gate khi pipeline chậm.

## 31. CI/CD gate để ngăn hợp đồng đang phát triển được xác nhận giả

Một quy trình CI nên phân biệt rõ **design validation**, **producer verification** và **consumer compatibility**:

~~~mermaid
flowchart TD
    A["Contract proposal / PR"] --> B["Review và phân tích breaking change"]
    B --> C["Producer code + contract cùng revision"]
    C --> D["SCC generate producer tests"]
    D --> E{"Generated tests thực thi > 0 và PASS?"}
    E -- "Không" --> X["BLOCK hoặc giữ Draft"]
    E -- "Có" --> F["Sinh stubs JAR ứng viên"]
    F --> G["Publish unique coordinate + commit + checksum"]
    G --> H["Consumer CI resolve exact artifact"]
    H --> I["Stub Runner nạp mappings ứng viên"]
    I --> J["Consumer client/handler thật chạy tests"]
    J --> K{"Affected consumer versions PASS?"}
    K -- "Không" --> X
    K -- "Có" --> L{"Có breaking changes chưa được chấp thuận?"}
    L -- "Có" --> X
    L -- "Không" --> M["Release-approved"]
~~~

### Bằng chứng ở từng gate

| Gate | Yêu cầu tối thiểu | Điều gì chưa đủ? |
|---|---|---|
| **Contract review** | Producer + affected consumer owners review behavior | Chỉ lint YAML/Groovy |
| **Producer verification** | Generated tests chạy trên code thực, count > 0, pass | File generated đã tồn tại |
| **Artifact verification** | Stubs JAR có mappings/fixtures, đúng candidate revision | Filename `-stubs.jar` tồn tại |
| **Repository verification** | Version bất biến hoặc snapshot resolved identity, checksum khớp | `SNAPSHOT` / `latest` không truy vết |
| **Consumer compatibility** | Client/handler thật chạy với candidate, assert nghiệp vụ | Mockito trả response mẫu |
| **Release decision** | Compatibility matrix và migration policy đạt | Một test suite ngẫu nhiên báo xanh |

**Block khi thiếu bằng chứng** khác với block do test fail. Không được coi `NOT_RUN` hoặc `NO_ARTIFACT` là `PASS` chỉ vì kỹ thuật gặp sự cố mạng hoặc job timeout.

## 32. Báo cáo minh bạch: PASS phải gắn vào một cặp artifact

Một record có thể có cấu trúc:

~~~text
contractChangeId: INV-173
contractRevision: a1b2c3d4
contractStatus: Producer-verified
producerService: inventory-service
producerCommit: a1b2c3d4
producerArtifact: com.example:inventory-service:1.4.0-rc.pr173.a1b2c3d4:stubs
producerArtifactSha256: <digest được đối chiếu>
producerContractTestsExecuted: <số test đã chạy>
consumerService: checkout-service
consumerVersion: 3.8.2
consumerCommit: <SHA của bản consumer được test>
consumerContractTestsExecuted: <số test đã chạy>
stubRunnerPort: <cổng đang dùng>
stubMappingsLoaded: <số mapping>
result: PASS | FAIL | NOT_RUN | BLOCKED
reviewers: <producer owner + consumer owner>
migrationDecision: <quyết định được phê duyệt>
~~~

Các giá trị trong `<...>` chỉ là trường **cần lấy từ CI**, không nên bịa ra số đo thực. Khi dùng snapshot, bổ sung resolved timestamp/digest, vì tên logical `-SNAPSHOT` không xác định được bytes.

Không gộp nhiều consumer versions vào một dòng `PASS` trừ khi có danh sách/các report tương ứng. Để quyết định release, cần biết **ai đã được test với artifact gì**, không chỉ “pipeline chạy thành công”.

## 33. Khi producer và consumer bất đồng: giải quyết bằng contract diff và bằng chứng

Giả sử nhóm Inventory cần bỏ `available` vì muốn chỉ giữ `inStock`, trong khi Checkout vẫn cần field cũ.

Một cách điều phối:

1. **Ghi rõ contract diff**: field nào bị thêm/xóa/đổi kiểu? API examples trước/sau?
2. **Lập danh sách consumer** sử dụng field đó và phiên bản đang vận hành.
3. **Đánh giá backward compatibility**: có thể tạm trả cả hai field không?
4. **Thử bằng code**: consumer versions hiện hành được chạy với candidate stub mới.
5. **So chi phí**: giữ field trong deprecation window so với nâng tất cả consumers đồng thời.
6. **Thỏa thuận ownership và mốc migration**: ai sửa client, ai cung cấp telemetry, ai quyết định remove?
7. **Dùng feature flag hoặc API versioning** nếu cần hỗ trợ hai behaviors cùng lúc.
8. **Không nới matcher/xóa assertion** chỉ để chuyển CI đỏ thành xanh mà không giải quyết giao tiếp thực.
9. **Ghi rõ quyết định kỹ thuật** trong PR/ticket, không để yêu cầu nằm trong tin nhắn riêng.

Nếu không thể giữ tương thích và phải breaking change, có thể cần **API version mới** hoặc phối hợp deploy đồng bộ có rollback plan. Nhưng rollout đồng bộ giữa nhiều microservices rất dễ thất bại ở hệ phân tán; tránh coi nó là phương án mặc định.

## 34. Phân biệt thay đổi schema với thay đổi semantics

Một API có thể giữ nguyên JSON và vẫn trở thành breaking change.

Ví dụ producer luôn trả:

~~~json
{"sku":"SKU-123","available":true,"quantity":12}
~~~

Nhưng trước đây `available=true` nghĩa là “còn ít nhất 1 đơn vị”; nay producer đổi semantics thành “còn đủ số lượng mặc định cho một gói 5”. Consumer Checkout cũ vẫn parse được JSON và test chỉ nhìn field presence có thể xanh.

Để ngăn xác nhận giả kiểu **semantic drift**:

- Hợp đồng phải có **scenario đủ ý nghĩa** để phân biệt behavior, không chỉ một response mẫu dễ đạt.
- Dùng nhiều request inputs hoặc producer states, ví dụ quantity 0, 1, 4, 5 và available tương ứng policy.
- Consumer test assert **quyết định nghiệp vụ** (cho checkout hay không) theo scenario.
- Producer verification kiểm tra implementation thực, không đơn giản echo body mẫu.
- Contract review ghi rõ field **meaning**, units, default, rounding, timezone, idempotency và edge cases.
- Khi semantics đổi, đánh dấu là **API behavior change** kể cả wire format không đổi.

**Schema compatibility không đồng nghĩa semantic compatibility.** Đây là lý do nhiều nhóm cần trao đổi nghiệp vụ, không chỉ review JSON diff.

## 35. Provider state: fixture phải phản ánh producer behavior thật

Một hợp đồng có thể mô tả:

~~~text
Given SKU-123 exists with quantity=12
When GET /api/inventory/SKU-123
Then 200 {available:true, quantity:12}
~~~

Để generated producer test tái lập:

- Chuẩn bị data fixture/DB state `SKU-123 quantity=12` bằng cơ chế test phù hợp.
- Gọi controller/service production thật.
- Đảm bảo query logic, mapping và serializer đều được thực thi.
- Dọn dữ liệu sau test; tránh lệ thuộc vào thứ tự chạy.
- Dùng clock/test ID cố định khi response chứa timestamp/correlation ID.
- Khi backend thật không trong phạm vi contract, mock **dependency ngoại vi tối thiểu**, không mock cả response nghiệp vụ.

**Xác nhận giả:** base test trực tiếp mock `InventoryService.getStock()` để trả chính `StockResponse` trong contract; generated test chỉ chứng minh controller serialize mock thành JSON, không kiểm chứng logic tồn kho. Có thể chấp nhận kiểu test controller-only nếu phạm vi được ghi rõ, nhưng không nên gọi nó là bằng chứng đầy đủ cho behavior thực của Inventory.

## 36. Bất đồng về test fail: nên dừng hay cho phép ngoại lệ?

Có thể có tình huống bắt buộc triển khai gấp dù một consumer compatibility test thất bại. Quy trình ngoại lệ cần **công khai và có người phê duyệt**, không biến `FAIL` thành `PASS`.

Một record ngoại lệ tối thiểu:

~~~text
contractChange: INV-173
failedConsumer: analytics-service v1
failure: Đổi tên field available -> inStock
risk: Analytics v1 không deserialize được response mới
decision: BLOCK / CONDITIONAL_WAIVER
approver: <tên vai trò có quyền>
expiry: <thời điểm ngoại lệ hết hiệu lực>
mitigation: <dual-field response / API v2 / rollout flag>
rollback: <kế hoạch rollback producer>
followUp: <ticket + owner + deadline>
evidence: <test logs + candidate artifact digest>
~~~

Nếu có waiver, trạng thái cuối phải thể hiện **“được phép đi tiếp dưới ràng buộc”**, không bị giả dạng thành “toàn bộ consumer tests PASS”. Với các hệ thống tài chính/safety-critical hoặc rủi ro cao, chính sách có thể yêu cầu **không có waiver** cho breaking changes.

Điều quan trọng là tránh “làm xanh dashboard” bằng cách disable test, skip consumer v1 hoặc đổi contract expected body mà không ghi nhận risk.

## 37. Các thước đo chất lượng hợp đồng khi nhiều nhóm phát triển

Một số chỉ số hữu ích:

| Chỉ số | Điều muốn biết | Tránh diễn giải sai |
|---|---|---|
| **Producer contract tests executed** | Có generated tests chạy thật không? | Số lượng nhiều không bảo đảm đủ scenarios |
| **Consumer compatibility coverage** | Bao nhiêu consumer versions trong phạm vi hỗ trợ đã được chạy? | Không coi các consumer chưa đăng ký là an toàn |
| **Candidate artifact provenance** | Tỷ lệ runs có commit/version/digest rõ | Có checksum nhưng không so với producer chưa đủ |
| **Mutation detection rate** | Suite có chuyển đỏ khi code/request cố ý sai? | Mutation hữu ích không thay việc review semantics |
| **Contract breaking changes caught pre-release** | Phát hiện sớm được bao nhiêu thay đổi | Số lỗi thấp có thể do kiểm thử yếu |
| **Stale-stub incidents** | Có consumer runs dùng sai/cũ artifact không? | Chỉ đo build pass sẽ bỏ lỡ hiện tượng |
| **Unreviewed contract changes** | Có thay đổi giao tiếp chưa được owner chấp thuận? | “LGTM” của nhóm khác không thay review đúng vai trò |
| **Deprecation lead time** | Consumers có đủ thời gian migration? | Không đồng nghĩa đã không còn consumer dùng field |
| **Flaky contract test rate** | Test phụ thuộc clock/network/data không ổn định? | Không xóa test mà không xử lý nguyên nhân |

Đừng tối ưu chỉ số “% tests xanh” bằng cách giảm assertions hoặc nới request matcher. KPI quan trọng nhất là **khả năng phát hiện thay đổi gây hỏng giao tiếp trước khi người dùng gặp lỗi**.

## 38. Case study tổng hợp: checkout bị phá dù hai pipeline đều xanh

### Bối cảnh

Inventory v1 trả:

~~~json
{"sku":"SKU-123","available":true,"quantity":12}
~~~

Checkout v3 dùng `available` để quyết định cho đặt hàng. Nhóm Inventory v2 thay bằng `inStock`.

### Điều đã xảy ra

1. Inventory PR đổi code và contract cùng lúc.
2. Generated producer tests v2 đạt vì kiểm tra response mới.
3. Nhóm Checkout chạy test với `inventory-service:1.3.0:stubs` cũ, vẫn thấy `available`.
4. Checkout test xanh vì code v3 còn tương thích với v1.
5. Release Inventory v2 trả `inStock` và không còn `available`.
6. Checkout v3 parse thiếu field; nếu DTO primitive `boolean`, giá trị có thể trở thành false.
7. Người dùng không đặt được hàng dù kho còn 12 đơn vị.

### Sai lầm nằm ở đâu?

Không nhất thiết ở syntax Groovy/YAML hoặc generated producer tests. Lỗi nằm ở **thiếu liên kết artifact giữa producer candidate và consumer verification**, cộng với assertions/validation không phát hiện field thiếu.

### Cách sửa quy trình

- Sinh candidate stubs v2 từ chính Inventory PR commit.
- Truyền exact coordinate/digest sang Checkout CI.
- Chạy **Checkout v3 đang được hỗ trợ** với candidate v2.
- Validate field bắt buộc; không dựa vào primitive default.
- Đưa compatibility result vào release gate.
- Nếu fail, dùng dual-field migration hoặc version API phù hợp.
- Chỉ remove `available` sau khi consumer migration hoàn tất.

### Phép thử chứng minh sửa đúng

Tạo mutation cố tình bỏ field `available`, chạy Checkout cũ với candidate stub, kiểm tra test **đỏ** và báo đúng lỗi schema/behavior. Sau đó thử contract giai đoạn chuyển tiếp có cả hai field, test **xanh** khi nghiệp vụ phù hợp.

**Bài học:** hai pipeline xanh độc lập **không đủ** nếu chúng không cùng kiểm chứng **cặp producer candidate và consumer version thực**.

## 39. Bài thực hành A — Đề xuất hợp đồng và ngăn design stub được coi là verified

**Mục tiêu:** luyện quy trình liên nhóm khi producer chưa hoàn thành implementation.

1. Nhóm Checkout đề xuất thêm `inStock`; tạo contract PR Groovy hoặc YAML.
2. Ghi API examples, status codes, error schema, affected consumers.
3. Dùng một design stub tạm để phát triển DTO và business logic consumer.
4. Gắn nhãn `UNVERIFIED DESIGN STUB` cho test/fixture tạm.
5. Nhóm Inventory review và chấp nhận behavior hoặc đề xuất thay đổi.
6. Khi producer code triển khai, chạy generated producer tests trên implementation thật.
7. Publish candidate stubs artifact gắn commit, có digest.
8. Thay design stub bằng Stub Runner dùng candidate và chạy consumer tests.
9. Chỉ khi cả producer và consumer gates đạt mới gắn nhãn release-approved.

**Bằng chứng cần lưu:** contract diff, review approval, generated producer test report, candidate coordinate/digest và consumer result.

## 40. Bài thực hành B — Chủ động tạo bốn loại xanh giả

**Mục tiêu:** chứng minh test suite phát hiện được lỗi do quá trình kiểm thử chứ không chỉ do API.

1. **Fake producer:** base test dùng fake controller trả đúng body → test có thể xanh. Thay bằng context thật, thử mutation để test đỏ.
2. **Mock consumer client:** mock InventoryClient trả DTO → test xanh dù stub không chạy. Đổi sang client thật, kiểm tra HTTP request tới Stub Runner.
3. **Matcher quá rộng:** dùng WireMock mapping chỉ match method/path → client body sai vẫn được chấp nhận. Bổ sung matcher contract và negative test.
4. **Stale stub:** chạy Checkout cũ với stable artifact khi Inventory candidate đã đổi schema → thấy PASS giả. Truyền candidate coordinate mới, kiểm tra fail.
5. Thử cấu hình runner để generated tests không được discover (trong nhánh thử) → CI guard phải chặn zero-tests.
6. Khôi phục mọi thay đổi cố ý sai, chạy lại bộ test chính.

**Bằng chứng cần lưu:** đối chiếu false PASS → nguyên nhân → thay đổi test/gate → FAIL đúng kỳ vọng → PASS sau khi sửa production behavior.

## 41. Bài thực hành C — Di chuyển field không phá consumer

1. Lập compatibility matrix gồm Checkout v3 và một consumer giả định khác như Analytics v1.
2. Producer triển khai `available` và `inStock` song song trong giai đoạn Expand.
3. Sinh contract và generated tests để bảo vệ cả hai field.
4. Publish candidate stubs có version duy nhất.
5. Consumer cũ và mới chạy tests với **cùng candidate**.
6. Analytics/Checkout cập nhật để dùng `inStock`; kiểm tra cùng field semantics.
7. Ghi ngày deprecation và tiêu chí được phép bỏ `available`.
8. Khi criteria đạt, tạo candidate chỉ còn `inStock`; chạy compatibility matrix lại.
9. Quyết định release hoặc tiếp tục duy trì dual-field behavior theo kết quả.

**Bằng chứng:** matrix có PASS/FAIL/NOT_RUN, contract versions, stubs artifacts, test reports và kế hoạch rollback.

## 42. Checklist review và release gate

- [ ] Contract đang là Draft/Proposed hay đã Accepted? Trạng thái có bằng chứng?
- [ ] Producer và affected consumer owners đã review field types, semantics và error cases?
- [ ] Có một nguồn contract revision rõ ràng, không tồn tại bản copy lệch nhau?
- [ ] Generated producer tests **được sinh, compile và thực thi > 0**?
- [ ] Test base gọi **producer implementation thật**, không fake response của contract?
- [ ] Mutation của producer làm test đỏ khi behavior vi phạm?
- [ ] Stubs JAR có mapping/fixtures phù hợp và đúng candidate revision?
- [ ] Artifact được publish với group/artifact/version/classifier và provenance rõ?
- [ ] Không dùng SNAPSHOT mutable/latest/`+` không kiểm soát làm release gate?
- [ ] Consumer CI tải exact candidate stub, kiểm tra version và digest?
- [ ] Stub Runner thực sự chạy với mappings candidate và đúng host/port?
- [ ] Client/handler production của consumer được test, không mock ngay ranh giới giao tiếp?
- [ ] Request matcher đủ chặt với những fields/headers quan trọng?
- [ ] Có negative tests cho request sai, schema thiếu/sai kiểu và business errors?
- [ ] Business 404 phân biệt với WireMock unmatched 404?
- [ ] Consumer assertion phản ánh behavior quan trọng, không chỉ not-null/status?
- [ ] Compatibility matrix chứa những consumer versions vẫn được hỗ trợ?
- [ ] `NOT_RUN`/`BLOCKED` không được diễn giải thành PASS?
- [ ] Breaking change có phương án expand–migrate–contract hoặc versioning?
- [ ] Migration có owner, deadline, rollout, rollback và deprecation policy?
- [ ] Với message contracts, trigger gọi production logic và verifier quan sát output thật?
- [ ] Những giới hạn ngoài stub test (auth, network, broker, performance) được kiểm chứng ở tầng phù hợp?
- [ ] Mọi waiver có phê duyệt/rủi ro/expiry, không được xóa logs hoặc disable tests âm thầm?
- [ ] Báo cáo lưu đủ commit, artifact, test counts và quyết định release?

## 43. Câu hỏi tự kiểm tra

**1. Vì sao consumer tự viết một WireMock stub rồi test xanh chưa đủ chứng minh hợp đồng đã được producer chấp nhận?**

Vì consumer đang thử **behavior tự giả định**. Cần contract PR/review, producer generated tests chạy trên code thật và stubs artifact từ revision đã được producer kiểm chứng.

**2. Generated producer tests xanh có chứng minh consumer cũ còn tương thích không?**

Không. Producer có thể đã đổi cả code và contract; phải chạy **consumer cũ** với stub ứng viên mới.

**3. Vì sao số test bằng 0 có thể tạo xác nhận giả?**

Vì pipeline có thể báo BUILD SUCCESS dù không có assertion nào kiểm chứng API. Gate cần xác minh contract discovery và executed generated tests.

**4. Matcher WireMock chỉ kiểm tra method/path có vấn đề gì?**

Nó có thể chấp nhận request body/header sai mà vẫn trả response thành công. Test không bảo vệ serialization contract.

**5. Vì sao cần mutation tests?**

Để xác nhận bộ test **thực sự thất bại** khi hành vi được bảo vệ bị cố ý vi phạm, thay vì luôn báo xanh vì fake/mocks/assertions yếu.

**6. Hợp đồng Draft, Accepted và Producer-verified khác nhau ở đâu?**

Draft mới là đề xuất; Accepted đã thống nhất semantics; Producer-verified có bằng chứng implementation thật đáp ứng contract. Đây là **quy ước quy trình nhóm**, không phải trạng thái mặc định của SCC.

**7. Thêm field mới vào JSON có luôn tương thích không?**

Không. Consumer strict decoder có thể từ chối unknown fields, hoặc field mới làm đổi semantics. Cần kiểm tra affected consumer versions.

**8. Khi một consumer không thể upgrade kịp, có thể xóa field cũ của producer không?**

Chỉ theo compatibility/migration policy đã được phê duyệt, có thử nghiệm và kế hoạch xử lý breaking change; thông thường nên trì hoãn remove hoặc dùng API versioning/dual-field.

**9. Tại sao PASS phải gắn với producer commit và consumer version?**

Vì “PASS” của cặp phiên bản A/X không chứng minh cặp B/Y an toàn. Cần artifact provenance và matrix để tránh nhầm.

**10. Contract tests đủ để khẳng định hệ thống production không bao giờ lỗi không?**

Không. Chúng bảo vệ những behavior đã khai báo trong môi trường test. Network, authentication, broker, concurrency và nhiều rủi ro runtime cần kiểm thử bổ sung.

## 44. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): producer/consumer contract testing, generated tests và stubs.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML, HTTP/message behaviors và matchers.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): tải stubs JAR, mode LOCAL/REMOTE, artifact resolution.
- [Spring Cloud Contract — Maven](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): producer-generated tests và stub packaging.
- [Spring Cloud Contract — Gradle](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): plugin generation, test execution và publishing.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): request matchers và near misses.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): response mappings và behavior của HTTP stubs.
- [Martin Fowler — Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html): hợp đồng theo nhu cầu consumer và phối hợp giữa các nhóm.
- [Martin Fowler — Patterns of Distributed Systems](https://martinfowler.com/articles/patterns-of-distributed-systems/): các rủi ro điều phối trong hệ phân tán.
- [Pact Documentation — Provider Verification](https://docs.pact.io/provider): tham khảo thêm một cách tiếp cận consumer-driven contract verification khác; không đồng nhất API Pact với SCC.

**Lưu ý về phiên bản và phạm vi:** Tên annotation, method DSL, cấu hình test mode, cơ chế publish và resolution của Spring Cloud Contract thay đổi theo Spring Boot–Spring Cloud Release Train–SCC version. Các trạng thái quản trị Draft/Accepted/Verified, mẫu PR và compatibility matrix là **đề xuất quy trình nhóm**, không phải chức năng mặc định của framework. Các đoạn code/hợp đồng là ví dụ tự học; **chưa chạy build/Content QA chuyên môn trong bước biên soạn này**.

---

**Điểm cần nhớ:** Hợp đồng đang phát triển chỉ trở thành **bằng chứng tương thích** khi (1) các nhóm đã thống nhất semantics, (2) generated producer tests chạy với code cung cấp **thật**, (3) stubs artifact được sinh từ **cùng contract revision/candidate** và có provenance, (4) consumer client/handler **thật** chạy với artifact ấy, và (5) các consumer versions đang được hỗ trợ vượt qua release gates. Hãy kiểm tra cả khả năng test chuyển **đỏ** khi giao tiếp sai, thay vì dựa vào màu xanh của một pipeline thiếu bằng chứng.
