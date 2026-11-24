# Phân biệt kết quả kiểm thử với quyết định cho phép triển khai

## 1. Vì sao một pipeline màu xanh chưa phải giấy phép đưa API lên production?

Trong hệ thống microservices, một **producer** cung cấp HTTP API hoặc phát message, còn **consumer** gọi API hay xử lý message đó. **Spring Cloud Contract (SCC)** cho phép hai phía định nghĩa hành vi bằng **Groovy/YAML DSL**, sinh **generated tests phía producer**, đóng gói **stubs JAR** và cho consumer sử dụng **Stub Runner** để phát hiện thay đổi API không tương thích.

Khi áp dụng CI/CD, một lỗi diễn giải thường gặp là:

> “Toàn bộ test trong job này PASS, vì vậy có thể triển khai ngay.”

Suy luận đó chỉ đúng nếu **chính sách triển khai của hệ thống đã được xác định** và mọi điều kiện bắt buộc của chính sách ấy thực sự được kiểm tra. Một bài test xanh có thể là bằng chứng tốt cho một hành vi, nhưng không tự chứng minh những điều sau:

- Producer implementation đang được triển khai chính là code đã được test.
- Stub mà consumer sử dụng được sinh từ **contract/version ứng viên hiện tại**, không phải phiên bản cũ.
- **Mọi consumer version cần hỗ trợ** đều tương thích với producer candidate.
- Generated producer tests thực sự được chạy, không bị skip hoặc có số test bằng 0.
- Test base gọi **implementation producer thật**, không phải fake controller trả body mong đợi.
- Consumer chạy **HTTP client/message handler thật**, không chỉ một Mockito stub.
- Những yêu cầu khác như security, migration database, hạ tầng, quan sát vận hành, rollback hoặc phê duyệt đã hoàn tất.

Bài này thuộc chương **CI/CD**, tập trung vào chủ đề **“Phân biệt kết quả kiểm thử với quyết định cho phép triển khai”**. Nội dung xây dựng tư duy ra quyết định có bằng chứng, không đánh đồng test status với release authorization.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích khác biệt giữa **test execution result**, **test evidence**, **quality gate**, **release approval** và **deployment authorization**.
2. Phân tích một pipeline có producer tests xanh nhưng vẫn **không được phép triển khai**.
3. Xây ma trận bằng chứng SCC: generated producer tests, stubs candidate, Stub Runner consumer tests và phạm vi kiểm chứng.
4. Phân biệt `PASS`, `FAIL`, `ERROR`, `SKIPPED`, `NOT_RUN`, `STALE` và `UNKNOWN` khi đưa ra quyết định.
5. Thiết kế **policy gates** yêu cầu đúng artifact identity, test counts, consumer compatibility và approvals.
6. Hiểu tại sao deploy lên staging, phát hành artifact, triển khai production và bật traffic có thể là **các quyết định riêng**.
7. Xử lý waiver, flaky tests, rollout canary và rollback mà không biến lỗi thành PASS giả.
8. Tạo một mẫu **decision record** có thể audit và dùng nó để giải thích vì sao một lần deploy được cho phép hoặc bị chặn.

## 2. Năm khái niệm phải được phân biệt rõ

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| **Test execution** | Test nào chạy, với input và môi trường nào? | JUnit generated producer test gọi GET inventory |
| **Test result** | Test đã chạy cho kết quả gì? | PASS, FAIL, ERROR, SKIPPED |
| **Test evidence** | Kết quả đó chứng minh điều gì, từ phiên bản nào? | 42 tests, commit A, stubs JAR digest B, report C |
| **Quality/release gate** | Bằng chứng có đáp ứng tiêu chí chính sách không? | Required consumers PASS, không có stale artifact |
| **Deployment authorization** | Ai/cơ chế nào được phép triển khai artifact nào lên môi trường nào? | Cho deploy build 173 vào staging; production cần approval |

Hai ý dễ nhầm:

**Test result là quan sát.** Nó mô tả một lần thực thi tại thời điểm, phạm vi và điều kiện cụ thể. **Authorization là quyết định dựa trên chính sách.** Nó có thể sử dụng kết quả test, nhưng không thể rút gọn thành một Boolean từ một job bất kỳ.

Một bước sau cũng quan trọng: **được phép triển khai** không đồng nghĩa **đã triển khai thành công**. Deployment cần thực hiện, kiểm tra rollout, giám sát và có thể rollback sau khi điều kiện thời gian thực thay đổi.

## 3. Ba lớp quyết định: build, release và deployment

~~~mermaid
flowchart TD
    A["Code + contracts + version"] --> B["Build và chạy tests"]
    B --> C{"Test evidence đạt?"}
    C -- "Không / thiếu bằng chứng" --> X["BLOCK hoặc REVIEW theo policy"]
    C -- "Có" --> D["Candidate artifact đã xác định"]
    D --> E{"Release quality gate đạt?"}
    E -- "Không" --> X
    E -- "Có" --> F["Release candidate được phê duyệt"]
    F --> G{"Môi trường production có cho phép deploy?"}
    G -- "Không" --> W["Giữ candidate chờ điều kiện"]
    G -- "Có" --> H["Triển khai và rollout có kiểm soát"]
    H --> I["Quan sát health/SLO"]
    I --> J{"An toàn sau deploy?"}
    J -- "Không" --> K["Halt/Rollback theo runbook"]
    J -- "Có" --> L["Tiếp tục hoặc hoàn tất rollout"]
~~~

Ví dụ:

- Build và contract tests PASS, nhưng đội vận hành đã khóa thay đổi vào giờ cao điểm: **chưa cho deploy production**.
- Artifact đã được phê duyệt để release, nhưng secret hoặc migration chưa sẵn sàng: **chưa được phép triển khai môi trường đích**.
- Deploy thành công ở staging, consumer compatibility của một ứng dụng production chưa chạy: **không chuyển kết luận staging PASS thành production approval**.
- Canary đã triển khai 5% traffic và health metrics xấu đi: **dừng rollout**, dù mọi pre-deployment tests vẫn PASS.

Bài kiểm thử hợp đồng là một lớp quan trọng trong **quality gate**, không phải nguồn quyết định duy nhất.

## 4. Ví dụ xuyên suốt: Inventory Service và Checkout Service

Giả sử Checkout (consumer) gọi Inventory (producer):

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

Contract đang vận hành (v1):

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-123","available":true,"quantity":12}
~~~

Producer candidate (v2) muốn thay `available` bằng `inStock`:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-123","inStock":true,"quantity":12}
~~~

Các kết quả có thể xảy ra:

| Kiểm tra | Kết quả | Kết luận đúng |
|---|---|---|
| Generated producer test v2 với Inventory v2 | PASS | Producer v2 đáp ứng **contract v2** |
| Checkout v3 dùng stub của Inventory v1 | PASS | Checkout v3 tương thích **contract v1**, chưa kết luận về v2 |
| Checkout v3 dùng stub Inventory v2 | FAIL | Có khả năng **breaking change** với consumer v3 |
| Checkout v4 đã nâng DTO, dùng stub v2 | PASS | Checkout v4 tương thích với scenario v2 đã test |
| Security/infrastructure readiness | NOT_RUN | Chưa có bằng chứng phục vụ quyết định production |

**Kết luận:** không thể cho deploy Inventory v2 chỉ vì producer tests v2 xanh và một consumer test khác cũng xanh nếu chúng **không kiểm tra cùng ứng viên** hoặc thiếu kiểm tra một consumer vẫn được hỗ trợ.

## 5. Mô hình kết quả test cần giàu thông tin hơn xanh/đỏ

Một pipeline thực tế thường có nhiều trạng thái:

| Trạng thái | Ý nghĩa | Đưa vào release gate thế nào? |
|---|---|---|
| **PASS** | Test đã chạy và assertions đạt | Chỉ đủ cho phạm vi test và artifact đã xác minh |
| **FAIL** | Assertions phát hiện behavior sai | Thường **BLOCK** nếu test bắt buộc |
| **ERROR** | Test hỏng vì setup, dependency, compile, timeout... | Không coi là PASS; cần phân tích/chạy lại |
| **SKIPPED** | Test đã được phát hiện nhưng bị bỏ qua | Không thỏa điều kiện “đã được thực thi” |
| **NOT_RUN** | Không có lần chạy hoặc thiếu report | Không được mặc định PASS |
| **STALE** | Có report nhưng dùng artifact/commit cũ hoặc quá thời hạn policy | Không dùng để cho phép candidate mới |
| **UNKNOWN** | Không xác định được kết quả, nguồn hoặc phạm vi | Fail closed hoặc yêu cầu review |
| **CANCELLED** | Job bị hủy trước khi có kết luận | Không có bằng chứng đạt |

**Quy tắc an toàn:** nếu một kiểm tra **bắt buộc** không có bằng chứng PASS hợp lệ, pipeline không nên cho phép triển khai tự động. Có thể có cơ chế **ngoại lệ được phê duyệt**, nhưng nó phải hiển thị là ngoại lệ, không được giả dạng PASS.

Đối với test flaky, việc chạy lại có thể giúp phân loại lỗi môi trường, nhưng **PASS sau lần chạy lại không tự xóa sự thật rằng lần đầu FAIL**. Gate cần policy rõ về retries, số lần flaky và khi nào yêu cầu điều tra.

## 6. “PASS có giá trị” là PASS có đầy đủ ngữ cảnh

Một kết quả test nên được liên kết với:

~~~text
testSuite: inventory-producer-contract-tests
result: PASS
testsExecuted: 18
testsFailed: 0
testsSkipped: 0
producerCommit: a1b2c3d4
contractRevision: a1b2c3d4
artifactVersion: 1.4.0-rc.pr173.a1b2c3d4
artifactSha256: <SHA-256 thu thập từ build>
testRunner: JUnit Jupiter + Maven Surefire
testEnvironment: producer-ci
executedAt: <thời điểm thực>
reportUri: <vị trí test report thật>
~~~

Các trường `<...>` cần được điền từ pipeline thực tế, **không phải số liệu đã được xác minh của một dự án nào**.

Tối thiểu cần biết: **test nào, phiên bản nào, môi trường nào, khi nào, có bao nhiêu test đã chạy và test thuộc phạm vi nào**. Một ảnh chụp màn hình hiển thị chữ PASS không đủ để liên kết với artifact chuẩn bị triển khai.

### Test pass không tự mở rộng phạm vi

- 18 HTTP producer tests không chứng minh message contracts nếu không có test message.
- Test `GET /api/inventory/SKU-123` không chứng minh mọi SKU, error paths hoặc race conditions.
- Consumer compatibility với Checkout v4 không chứng minh Checkout v3 đã được nâng cấp.
- Test trên JDK và config A không tự chứng minh deploy runtime có config B cũng hoạt động.
- Test với WireMock không chứng minh broker, load balancer hoặc production network đã sẵn sàng.

**Không đánh tráo “test đã chạy đúng” với “mọi điều kiện triển khai đều đúng”.**

## 7. Bản đồ bằng chứng Spring Cloud Contract trong CI

Một quality gate cho thay đổi API cần ít nhất các lớp sau:

| Bằng chứng | Nguồn | Khi thiếu sẽ có rủi ro |
|---|---|---|
| Contract source revision | Git commit, contract artifact | Không biết contract nào được kiểm tra |
| Generated producer tests | SCC Contract Verifier | Không có kiểm tra implementation producer |
| Executed producer test reports | Surefire/Failsafe/Gradle | File test có thể tồn tại nhưng chưa chạy |
| Stubs JAR candidate | SCC build/package | Consumer có thể dùng mapping tự viết hoặc cũ |
| Resolved artifact provenance | Repository + SHA/commit | Test consumer không gắn với candidate |
| Consumer integration tests | Client/handler thật + Stub Runner | Producer mới có thể phá consumer |
| Compatibility matrix | Các consumer versions hỗ trợ | Một nhóm consumer có thể bị bỏ sót |
| Required extra gates | Security, deploy readiness, migrations... | Test hợp đồng không bao phủ rủi ro này |
| Approval/audit record | CI policy + environment owner | Không rõ ai cho phép deploy và theo quy định nào |

Chỉ một hoặc hai dòng PASS trong bảng **không đủ** để tự động gán trạng thái `RELEASE_APPROVED`.

## 8. Generated producer tests phải chạy trên code thật

Contract Groovy DSL cho Inventory v1:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout đọc tồn kho SKU-123'

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
            available: true,
            quantity: 12
        )
    }
}
~~~

Trong producer Maven/Gradle đã cấu hình SCC, Contract Verifier sẽ sinh test, gọi endpoint theo adapter/test mode tương ứng và assert response theo contract.

Ví dụ **test base Spring MVC** có thể dùng:

~~~java
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
public abstract class ContractTestBase {
    @Autowired
    MockMvc mockMvc;

    @BeforeEach
    void setup() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

Tác dụng của base test là đưa generated tests tới **Spring MVC controller/service production**. Nếu base class lại tự dùng `FakeInventoryController` trả body contract bằng hardcode, test có thể xanh dù producer implementation thật sai.

**Quality gate cần xác minh:** contract được phát hiện, generated source compile, **executed generated tests > 0** và test thực sự đi qua code cần kiểm chứng. Có thể làm thử mutation trong nhánh thử: sửa producer để trả `available=false` trong khi contract giữ `true`; test phải chuyển đỏ.

## 9. Khác biệt giữa test source tồn tại và test được thực thi

Các trường hợp có thể tạo “xanh giả”:

- Maven sinh Java tests nhưng Surefire/Failsafe không phát hiện do naming hoặc JUnit version.
- Gradle plugin sinh tests nhưng source set/task `test` không chạy.
- CI bật `-DskipTests`, `-Dmaven.test.skip=true` hoặc profile làm skip generation.
- Test report cũ vẫn nằm trong workspace được cache.
- Pipeline chỉ đếm **tổng số unit tests**, bỏ qua việc contract tests bằng 0.
- Generated test bị `@Disabled` hoặc điều kiện môi trường loại bỏ.
- Base test dùng mock toàn bộ behavior producer, khiến assertions không có giá trị.

Ví dụ lệnh thực hành cho Maven producer:

~~~bash
./mvnw clean verify
~~~

Với Gradle producer:

~~~bash
./gradlew clean test
~~~

Những lệnh đó **không tự bảo đảm mọi task đã được cấu hình đúng**; cần đọc generated source, execution reports và artifact outputs. Nếu policy yêu cầu có contract, hãy chặn **zero-contract** hoặc **zero-executed-contract-test** runs.

## 10. Stub Runner test của consumer có nhiệm vụ khác producer test

Một test Checkout có thể chạy với candidate stub:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties =
    "inventory.base-url=http://localhost:18081")
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.4.0-rc.pr173.a1b2c3d4:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutInventoryCompatibilityTest {

    @Autowired
    InventoryClient inventoryClient;

    @Test
    void checkoutCanReadInventoryCandidate() {
        StockResponse response = inventoryClient.getStock("SKU-123");

        assertThat(response.sku()).isEqualTo("SKU-123");
        assertThat(response.available()).isTrue();
        assertThat(response.quantity()).isEqualTo(12);
    }
}
~~~

`InventoryClient` và `StockResponse` ở đây là **các class giả định thuộc Checkout**. Code ví dụ chưa triển khai hoàn chỉnh các bean và artifacts; `LOCAL` chỉ dùng được khi stubs JAR của tọa độ đó đã có trong nguồn local mà runner hỗ trợ.

Điểm cốt lõi: test dùng **HTTP client thật**. Nếu mock `InventoryClient.getStock()` rồi trả `StockResponse` mẫu, ta chỉ đang test orchestration, **không kiểm tra method/path/headers/serialization/error handling** hay artifact Stub Runner.

**Kết luận từ PASS:** consumer class/version này hiểu **response scenarios đã test** của **stub artifact cụ thể này**. Nó không chứng minh producer implementation thật, vì Stub Runner trả response mô phỏng theo contract.

## 11. Lý do hai bộ test cùng xanh vẫn chưa cho phép deploy

~~~mermaid
flowchart LR
    A["Producer test B PASS với contract B"] --> C["Báo cáo tổng hợp: 2 jobs PASS"]
    D["Consumer test PASS với stub A cũ"] --> C
    C --> E{"Artifact giữa hai jobs có cùng candidate?"}
    E -- "Không" --> X["BLOCK: bằng chứng không liên kết"]
    E -- "Có" --> F["Tiếp tục đánh giá policy khác"]
~~~

Trong ví dụ Inventory đổi `available` thành `inStock`:

- Producer code B + contract B có thể hoàn toàn đúng.
- Consumer Checkout cũ + stub A có thể hoàn toàn đúng.
- Nhưng **điểm giao tiếp giữa B và Checkout cũ có thể bị phá**.

Quality gate cần so sánh **producer candidate** với **stub artifact đã resolve trong consumer job**, không chỉ đếm số job xanh.

Nếu consumer code dùng primitive `boolean available`, field thiếu có thể bị default thành `false` tùy Jackson config, khiến test chỉ assert “response không null” vẫn xanh. Cần assertions có ý nghĩa, kiểm tra field bắt buộc và thử breaking changes để đánh giá sức phát hiện của suite.

## 12. Status kiểm thử và status quyết định triển khai phải là hai bảng riêng

Một mô hình báo cáo minh họa:

| Producer tests | Consumer tests | Artifact hợp lệ? | Approval/policy khác | Quyết định |
|---|---|---|---|---|
| PASS | PASS | Đúng candidate | Đã đáp ứng | **ALLOW** |
| PASS | PASS | Stub cũ/khác commit | Dù đã review | **BLOCK** |
| PASS | FAIL | Đúng candidate | Chưa có ngoại lệ hợp lệ | **BLOCK** |
| PASS | NOT_RUN | Đúng candidate | Chưa hoàn tất | **BLOCK/WAIT** |
| PASS | PASS | Đúng candidate | Chưa được phê duyệt production | **WAIT_APPROVAL** |
| FAIL | PASS | Đúng candidate | Không có waiver | **BLOCK** |
| PASS | PASS | Đúng candidate | Môi trường production bị freeze | **WAIT_WINDOW** |
| PASS | PASS | Đúng candidate | Runtime canary bất thường | **HALT/ROLLBACK** |

**ALLOW/BLOCK/WAIT_APPROVAL/WAIT_WINDOW** là những trạng thái quyết định **do đội phát triển xây chính sách**, không phải enum bắt buộc do Spring Cloud Contract cung cấp. Bảng cũng không hàm ý rằng mọi tổ chức phải áp giống nhau: độ nghiêm ngặt của compliance và release process có thể khác.

Điều không được thay đổi là **không suy ra bằng chứng không tồn tại thành PASS** và **không đổi report FAILED thành PASSED chỉ để có màu xanh**.

## 13. Chọn phạm vi test bắt buộc theo thay đổi, không theo màu dashboard

Không phải mọi thay đổi đều yêu cầu cùng một ma trận test, nhưng policy cần xác định **điều kiện tối thiểu cho từng loại rủi ro**:

| Loại thay đổi | Test tối thiểu nên cân nhắc | Điểm cần phê duyệt |
|---|---|---|
| Sửa nội bộ producer, contract giữ nguyên | Generated producer tests + regression liên quan | Có thay đổi semantics chưa ghi contract? |
| Thêm endpoint mới | Producer contract cho endpoint mới, consumer được xác định | Endpoint chưa dùng có ảnh hưởng auth/routing không? |
| Thêm response field | Producer verification + affected consumer tests | Unknown-field policy có strict không? |
| Xóa/đổi tên field | Producer tests + **consumer versions hiện hành** | Breaking change và kế hoạch migration |
| Đổi error status/code | Error contracts + consumer error mapping | Có consumer retry/fallback theo code cũ không? |
| Đổi request validation/required header | Producer negative tests + consumer request tests | Client cũ có gửi đủ input không? |
| Đổi message schema/destination | Messaging contract tests + handler tests + broker integration cần thiết | Có event tồn kho, replay hay consumer chưa nâng cấp không? |
| Đổi networking/security config | Contract tests + security/config integration | Authentication và route production được xác minh chưa? |

**Phạm vi test là một quyết định có owner.** Không nên cho pipeline tự bỏ những consumer chưa đăng ký chỉ vì test “lâu”. Hãy duy trì dependency map từ API/message contract tới các nhóm đang sử dụng.

Quality gate có thể tối ưu bằng cách chạy **affected suites** ở PR, rồi **full supported matrix** trước khi production release. Quan trọng là policy phải có cơ chế kiểm tra danh sách affected consumers, không biến “chưa chạy” thành “không liên quan” theo suy đoán.

## 14. Contract không chỉ chứa happy path

Để chọn gate đủ mạnh, hãy xem request/response mà consumer thực sự phụ thuộc:

- HTTP method, path variables và query encoding;
- `Accept`/`Content-Type` và header bắt buộc;
- Request body fields và kiểu JSON;
- Response status, body fields và nullability;
- Mã lỗi nghiệp vụ, ví dụ `SKU_NOT_FOUND`;
- Retryable errors như `INVENTORY_UNAVAILABLE`;
- Enum, numeric precision, timestamp/timezone semantics;
- Message event type, destination, headers, schema version và key khi áp dụng.

Một producer test `GET SKU-123 -> 200` xanh không bảo vệ được consumer nếu lỗi 404 đổi body hoặc response success xóa field bắt buộc. Vì thế **một PASS không nên được diễn giải vượt quá scenarios đã khai báo và thực thi**.

Tuy nhiên, contract suite cũng không nên cố mô phỏng tất cả infrastructure faults: phân biệt **hành vi producer cam kết** với **resilience tests**, chẳng hạn latency, connection refused, broker redelivery và circuit breaker.

## 15. Ví dụ error contract YAML và tác động tới gate

Một contract HTTP error riêng:

~~~yaml
description: Inventory trả lỗi khi SKU không tồn tại
name: inventory_sku_not_found

request:
  method: GET
  url: /api/inventory/SKU-404
  headers:
    Accept: application/json

response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: SKU_NOT_FOUND
    message: SKU does not exist
~~~

Với producer candidate, generated test cần bảo đảm **implementation thật** trả đúng status và body. Ở consumer, test phải bảo đảm client phân biệt:

| Response | Ý nghĩa | Hành vi client cần thử |
|---|---|---|
| 404 + `SKU_NOT_FOUND` | Business error đã cam kết | Chuyển thành `InventoryNotFoundException` hoặc equivalent |
| 404 unmatched WireMock | Request không match mapping | **Không** coi là SKU_NOT_FOUND chỉ vì status |
| 503 + `INVENTORY_UNAVAILABLE` | Upstream unavailable theo contract | Retry/fallback theo policy |
| Connection refused | Không có HTTP response hợp lệ | Transport failure riêng |
| HTTP 200 + field bắt buộc thiếu | Protocol/schema mismatch | Không âm thầm mặc định giá trị nghiệp vụ |

Bởi vậy, một consumer compatibility gate chỉ nhìn HTTP status 200 là quá hẹp nếu client quyết định nghiệp vụ bằng các field và mã lỗi khác.

## 16. Artifact được test phải là artifact được dự kiến triển khai

Một pipeline dễ tạo vấn đề:

~~~text
Producer CI:
  build commit A
  test A PASS

Release job:
  rebuild từ HEAD commit B
  deploy artifact B
~~~

Bằng chứng test A không tự chứng minh artifact B an toàn, dù branch name không đổi. Điều tương tự xảy ra khi:

- Consumer test chạy stub `inventory-service:1.3.0:stubs`, nhưng production sắp triển khai producer `1.4.0-rc1`.
- Pipeline publish lại cùng SNAPSHOT logical version sau khi consumer test hoàn tất.
- Docker image được build lại với dependency mới mà không tái tạo test evidence.
- Có bước sửa package/JAR sau khi test nhưng không ghi lại checksum.

Mô hình an toàn hơn là **build once, verify once, promote the same immutable artifact** theo chính sách dự án:

~~~text
commit A + contract A
    ↓
build producer artifact A + stubs artifact A
    ↓
producer verification A
    ↓
consumer compatibility với stubs A
    ↓
lưu digests và quality evidence
    ↓
promote đúng artifact A
    ↓
deploy đúng artifact A vào môi trường đích
~~~

Nếu pipeline buộc rebuild, phải chứng minh tính tương đương và chạy lại những gates cần thiết cho output mới. Một nhãn version trên Docker image/JAR không đủ nếu registry cho phép ghi đè tag.

## 17. Snapshot, cache và tính mới của bằng chứng

Một ID Stub Runner có thể chứa:

~~~text
com.example:inventory-service:1.4.0-SNAPSHOT:stubs:18081
~~~

Nhưng `-SNAPSHOT` thường là version **có thể thay đổi**. Maven metadata, Gradle caching, repository proxy hoặc Stub Runner đã khởi động trước khi publish có thể khiến consumer dùng **mapping cũ**.

Để xác nhận độ mới:

1. Ghi **producer commit**, contract revision và candidate build ID.
2. Ghi tọa độ **group/artifact/version/classifier** của stubs artifact.
3. Nếu dùng SNAPSHOT, xác định timestamped build hoặc digest của JAR đã resolve.
4. Xác nhận Stub Runner đã thực sự **load mapping đó**, không giữ server/process cũ.
5. Kiểm tra consumer HTTP client trỏ vào đúng server/port.
6. Chạy assertions nhận biết behavior ứng viên.
7. Chặn tự động khi không xác định được provenance.

`mvn -U` và `gradle --refresh-dependencies` có thể giúp làm mới resolver tương ứng, nhưng **không tự khiến một WireMock server đang chạy reload mapping**. Với release gate có yêu cầu tái lập, **candidate version duy nhất theo commit cùng repository immutability policy** thường tốt hơn một SNAPSHOT mutable.

## 18. Compatibility matrix: không chỉ kiểm tra consumer mới nhất

Một producer có thể phục vụ Checkout v3, Cart v2 và Analytics v1. Ví dụ ma trận mang tính **minh họa, không phải kết quả test thật**:

| Producer candidate | Checkout v3 | Cart v2 | Analytics v1 | Quyết định |
|---|---|---|---|---|
| A: `available` | PASS | PASS | PASS | Có thể xem xét gate khác |
| B: `available` + `inStock` | PASS | PASS | NOT_RUN | **WAIT/BLOCK** theo policy |
| C: chỉ `inStock` | FAIL | PASS | FAIL | **BLOCK** nếu còn hỗ trợ các bản đó |
| D: dual-field sau sửa | PASS | PASS | PASS | Có thể xét release gate tiếp |

Một compatibility matrix có giá trị khi:

- Hàng là **producer artifact/version cụ thể**, có digest.
- Cột là **consumer version/commit cụ thể**, không chỉ tên ứng dụng.
- PASS/FAIL/NOT_RUN có **test report riêng**.
- Danh sách consumers cần hỗ trợ đã được owner xác nhận.
- Thay đổi consumer ở production đã được rollout hoặc migration criteria đạt trước khi bỏ field cũ.

**Producer contract PASS không thể thay thế toàn bộ ma trận.** Nếu một consumer chưa test, phải ghi NOT_RUN thay vì suy luận nó sẽ tương thích.

## 19. Phân biệt điều kiện bắt buộc và điều kiện theo rủi ro

Không phải mọi tổ chức cần một checklist deployment giống nhau. Policy có thể có hai tầng:

**Điều kiện bắt buộc tuyệt đối của tự động hóa**, ví dụ:

- Artifact cần deploy và test evidence phải có provenance đối chiếu được.
- Không có required producer/consumer test thất bại hoặc bị bỏ qua mà không có quyết định hợp lệ.
- Các job bắt buộc đã hoàn thành; không có `UNKNOWN`.
- Caller có quyền yêu cầu deploy môi trường đích.
- Môi trường không bị khóa theo lịch thay đổi hoặc incident policy.

**Điều kiện theo rủi ro**, ví dụ:

- Có cần review thủ công do breaking API change không?
- Có cần DBA approve migration không?
- Có cần test tải, bảo mật hoặc compliance bổ sung không?
- Có cần canary, giới hạn lưu lượng và rollback plan không?
- Có consumer đang hoạt động nhưng chưa được phép loại bỏ field cũ không?

Điều kiện theo rủi ro **không có nghĩa được bỏ qua tùy hứng**. Chúng phải được diễn đạt bằng các tiêu chí, owner, phạm vi và lý do khi không áp dụng.

## 20. Quy tắc policy dưới dạng logic rõ ràng

Một mô hình logic cho **triển khai tự động**:

~~~text
ALLOW_AUTOMATED_DEPLOY =
    candidate_is_immutable
    AND evidence_matches_candidate
    AND producer_contract_tests_executed
    AND producer_contract_tests_pass
    AND required_consumer_tests_executed
    AND required_consumer_tests_pass
    AND required_security_and_operational_gates_pass
    AND deployment_window_allows
    AND environment_authorization_satisfied
~~~

Đây là **pseudocode chính sách**, không phải đoạn code SCC cung cấp sẵn.

Trường hợp một trong các dữ kiện bằng `UNKNOWN`, quyết định thường là **BLOCK hoặc WAIT_FOR_REVIEW**, không suy luận UNKNOWN thành true. Nếu có waiver, policy cần một nhánh **tường minh** do người/cơ chế có thẩm quyền chấp thuận, ghi nguyên nhân, ngày hết hạn và phạm vi.

Mọi cổng cũng cần có khái niệm **“not applicable” được phê duyệt**. Một test message không cần chạy cho service chỉ có HTTP API có thể là N/A, nhưng người định nghĩa policy phải có căn cứ rằng service thực sự không có message contract.

## 21. Thông tin đầu vào để đưa ra quyết định phải độc lập với mong muốn deploy

Một quy tắc đơn giản nhưng quan trọng:

> Không để deployment job tự đánh dấu `testsPassed=true` mà không đọc/kiểm tra report từ test job tương ứng.

Một record đánh giá minh họa:

~~~json
{
  "candidate": {
    "service": "inventory-service",
    "commit": "a1b2c3d4",
    "version": "1.4.0-rc.pr173.a1b2c3d4",
    "artifactDigest": "sha256:<actual-digest>"
  },
  "evidence": {
    "producerContractTests": "PASS",
    "producerContractTestsExecuted": 18,
    "checkoutV3Compatibility": "PASS",
    "cartV2Compatibility": "NOT_RUN",
    "securityGate": "PASS"
  },
  "authorization": {
    "environment": "production",
    "decision": "BLOCK",
    "reason": "Required consumer cart-v2 was not tested"
  }
}
~~~

Đây là **schema minh họa**, không phải attestation chính thức. `sha256:<actual-digest>` là placeholder cần thay từ artifact build thực. Mẫu cho thấy các trạng thái riêng biệt: test producer PASS, Checkout PASS, Cart NOT_RUN, kết luận production **BLOCK**. Không có mâu thuẫn vì **quyết định dựa trên tập điều kiện lớn hơn một test result**.

## 22. Approval thủ công: bằng chứng bổ sung, không thay thế kiểm thử

Một tổ chức có thể yêu cầu người có quyền (release manager, service owner, DBA, security owner) phê duyệt trước khi triển khai production.

Approval nên xem:

- Candidate artifact ID/digest và Git commit;
- Contract diff cùng impact lên các consumer;
- Test reports, coverage và kết quả negative/mutation tests quan trọng;
- Những job chưa chạy, flaky, failures và ngoại lệ;
- Kế hoạch migration/rollback/monitoring;
- Môi trường, lịch triển khai và quyền của người yêu cầu.

**Approval không làm một failed test biến thành passed test.** Nó là quyết định có trách nhiệm về rủi ro (nếu policy cho phép), phải ghi rõ waiver/giới hạn và lý do. Với những cổng bắt buộc không có ngoại lệ, approval cũng **không được override**.

Cần phân biệt **review code/contract PR** với **authorization triển khai**. Người review code xác nhận thay đổi phù hợp; người duyệt production có thể cần xét điều kiện vận hành xuất hiện sau khi PR đã merge.

## 23. Từ policy tới CI implementation: không chỉ nhìn job dependency

Một workflow CI/CD có thể có những job logic:

~~~text
producer-contract-verification
    |
    v
candidate-build-and-attach-stubs
    |
    v
consumer-compatibility-matrix
    |
    +----> security-and-ops-readiness
                 |
                 v
          policy-evaluation
                 |
                 v
       production-approval
                 |
                 v
       controlled-deployment
                 |
                 v
       post-deploy-observation
~~~

**Lưu ý:** `needs`/job dependencies của hệ CI chỉ bảo đảm thứ tự và kết quả ở mức job. Nó không tự kiểm tra:

- Số generated producer tests executed > 0;
- Artifact digest giữa các job có khớp;
- Consumer matrix có đủ cột;
- Stub Runner nạp đúng candidate;
- Một job PASS có bị skip test bên trong không.

Những điều đó cần được **thực thi bằng quality checks** và lưu thành dữ liệu input cho policy evaluation.

### Chạy lại job phải không làm sai lệch provenance

Một CI system có thể cho rerun một job sau nhiều ngày. Nếu job consumer dùng `1.4.0-SNAPSHOT` hoặc `latest`, lần chạy lại có thể tải artifact khác lần đầu. Vì thế **rerun cùng workflow không đồng nghĩa rerun cùng candidate** nếu artifacts không được cố định.

## 24. Ví dụ GitHub Actions ở mức kiến trúc

Một workflow **skeleton để giải thích orchestration** (các bước build/stub publishing/consumer tests thực tế phải được bổ sung đúng repository; không chạy nguyên văn khi chưa hoàn thiện):

~~~yaml
name: inventory-contract-release-gate

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  producer_contracts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Configure Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: Run producer verification
        run: ./mvnw -B clean verify
      # BẮT BUỘC: kiểm generated tests > 0,
      # xác minh không skip, lưu reports và candidate commit/digest.

  candidate_and_consumers:
    needs: producer_contracts
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Publish candidate and run affected consumers
        run: |
          echo "DEMO ONLY: integrate artifact publishing and compatibility matrix"
          exit 1
      # Không thay 'exit 1' bằng PASS giả.
      # Tạo artifact version bất biến từ producer commit.
      # Truyền version/digest tới consumer job và kiểm reports.

  deploy_production:
    needs: [producer_contracts, candidate_and_consumers]
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Production release gate
        run: |
          echo "DEMO ONLY: policy decision and deployment go here"
          exit 1
      # Environment protection, reviewers và secrets
      # cần cấu hình ở repository/org settings.
~~~

Vì đây là skeleton, nó **chủ động kết thúc lỗi** ở những job chưa có implementation để tránh tạo cảm giác rằng chạy echo là đã kiểm thử tương thích hoặc deploy an toàn.

Khi triển khai thực tế cần thêm các bước để publish stub ứng viên **sau producer verification**, chạy consumer matrix bằng đúng artifact, so digest và công bố decision record. `environment: production` **chỉ tham chiếu môi trường**; cơ chế required reviewers/branch restrictions phải được cấu hình trong GitHub repository/org. Tên môi trường trong YAML **không tự tạo approval policy**.

JDK `21` và action versions ở ví dụ là lựa chọn minh họa, không phải yêu cầu chung cho mọi dòng Spring Boot/SCC.

## 25. Branch protection và environment protection là hai tầng khác nhau

- **Branch protection:** bảo vệ việc merge vào nhánh quan trọng dựa trên required status checks, review, signed commits hoặc quy tắc dự án.
- **Environment protection:** bảo vệ deployment vào môi trường cụ thể, ví dụ production yêu cầu reviewer và/hoặc hạn chế branch được phép deploy.
- **Runtime access control:** xác định job/identity nào có quyền dùng credentials để thao tác cluster/cloud; nên dựa trên least privilege và workload identity khi có thể.
- **Contract-specific release gate:** kiểm tra producer verification, consumer compatibility và artifact provenance.

Một PR đã merge nhờ status checks **không tự động có quyền triển khai production**. Ngược lại, một người có quyền bấm deploy **không nên bỏ qua required compatibility gates**.

Để giảm nguy cơ bypass, cần thiết lập chính sách trên **nền tảng CI/registry/environment**, không chỉ dựa vào comment trong YAML. Các secrets production nên chỉ cấp cho job đã vượt qua authorization thích hợp.

## 26. Phân biệt publish artifact, release, deploy và bật traffic

Đây là bốn hành động có thể diễn ra ở những thời điểm khác nhau:

| Hành động | Đối tượng | Rủi ro khi đánh đồng |
|---|---|---|
| **Publish artifact** | Đưa JAR/stubs/image vào registry | Chưa có nghĩa được phép chạy production |
| **Release approval** | Phê duyệt ứng viên theo policy | Chưa có nghĩa deployment đã thực hiện |
| **Deploy** | Đưa build vào môi trường staging/prod | Chưa có nghĩa toàn bộ traffic đã dùng build đó |
| **Expose/rollout** | Điều hướng traffic/feature flag để người dùng dùng phiên bản mới | Cần theo dõi runtime, kill switch và rollback |

Ví dụ producer có thể publish `1.4.0-rc1-stubs.jar` để consumer CI kiểm tra **trước** khi cho phép triển khai API mới. Đây không phải thay đổi production traffic.

Tương tự, có thể deploy ứng dụng mới lên môi trường production dưới feature flag **tắt**, rồi chỉ bật field behavior mới sau approval và canary. Nhưng bật flag cũng là **một thay đổi tác động người dùng**, cần chính sách riêng nếu có khả năng phá consumer.

## 27. Security và operational readiness không nằm trọn trong SCC

Spring Cloud Contract rất phù hợp để xác minh những tương tác đã mô tả, nhưng nó không thay thế:

- Secret scanning, dependency vulnerability checks, container image scanning;
- Authorization/tenant isolation và security configuration thực;
- Migration database, compatibility schema dữ liệu, rollback migration;
- Readiness/liveness, rate limiting, timeouts/retries, load/capacity;
- Broker topology, event ordering/duplicate delivery và DLQ;
- Kế hoạch SLO, observability, alerts, incident response và change window;
- Tuân thủ yêu cầu nội bộ hoặc regulatory nếu có.

Một release policy có thể yêu cầu các cổng này **tùy mức độ rủi ro**. Khi không áp dụng, cần ghi **N/A theo quy tắc đã duyệt** thay vì giả tạo PASS.

Đừng suy ra “contract test PASS” là “security và runtime behavior đã được kiểm chứng”. Hãy ghi rõ trong report **phạm vi mà SCC bảo vệ** và các bài kiểm tra bổ sung đã hoàn thành.

## 28. Canary và progressive delivery: PASS trước deploy không bảo đảm PASS khi có traffic

Sau khi một ứng viên vượt qua policy gate, triển khai vẫn có thể phát sinh vấn đề do data production, service discovery, network hoặc traffic pattern.

Một rollout có kiểm soát có thể gồm:

~~~mermaid
flowchart TD
    A["Release approved: artifact digest A"] --> B["Deploy canary 5%"]
    B --> C["Quan sát errors, latency, business metrics"]
    C --> D{"SLO và guardrails đạt?"}
    D -- "Không" --> X["Dừng rollout + rollback/disable flag"]
    D -- "Có" --> E["Tăng 25%"]
    E --> F{"Metrics đạt?"}
    F -- "Không" --> X
    F -- "Có" --> G["Tiếp tục lên 100%"]
    G --> H["Theo dõi sau rollout"]
~~~

Các tỷ lệ 5%/25% chỉ để minh họa; dự án phải chọn theo quy mô traffic và rủi ro. Một hệ thống ít traffic có thể cần thời gian quan sát khác hoặc chạy synthetic checks.

Điểm cần tách:

- **Contract test PASS:** API/message behavior được test theo các fixtures.
- **Release approval:** các điều kiện chất lượng và quản trị đã đạt.
- **Canary health PASS:** rollout thực tế không phá ngưỡng runtime đã đặt trong giai đoạn quan sát.
- **Rollout complete:** toàn bộ traffic/feature flag đã chuyển và health sau chuyển tiếp được xác nhận.

Một canary failure **không làm producer contract tests trước đó thành FAIL**; nó cho thấy một **loại bằng chứng khác** đã không đạt. Quyết định đúng là dừng/rollback theo policy, giữ nguyên test report để điều tra.

## 29. Rollback cũng cần quan hệ đúng giữa artifact và contract

Giả sử Inventory v2 đã triển khai cùng một migration schema dữ liệu. Rollback về v1 có thể gặp vấn đề nếu:

- v2 ghi các field/database rows mà v1 không đọc được;
- producer v1 không hiểu event format mới đã được publish;
- consumer vừa nâng lên v2 phụ thuộc endpoint mới không tồn tại ở v1;
- API gateway routing/cache vẫn dùng config mới;
- việc xóa field cũ đã được deploy trước khi consumer migration hoàn tất.

Vì vậy, một kế hoạch rollback cần chỉ rõ:

1. **Artifact cũ nào** được phép redeploy (digest chính xác);
2. Consumer versions nào tương thích với artifact cũ;
3. Dữ liệu/DB/schema version có tương thích ngược không;
4. Feature flags nào cần tắt hoặc đổi;
5. Event/message đã phát có ảnh hưởng khi replay không;
6. Điểm giám sát và tiêu chí dừng rollout;
7. Người/cơ chế nào có quyền thực hiện rollback.

**Rollback là quyết định vận hành có điều kiện**, không phải hệ quả tự động của một contract test fail. Đôi khi phương án an toàn hơn là tắt flag/roll forward bằng hotfix thay vì quay lại một binary không còn tương thích dữ liệu.

## 30. Quyết định có thời hạn và có thể hết hiệu lực

Một quality gate PASS hôm qua không nhất thiết cho phép deploy hôm nay nếu điều kiện đã đổi:

- Artifact bị rebuild hoặc tag bị ghi đè;
- Một consumer production mới được triển khai và chưa được test trong matrix;
- Có security advisory mới tác động dependency của artifact;
- Production đang có incident/change freeze;
- Migration prerequisite chưa hoàn tất hoặc dữ liệu đã chuyển trạng thái;
- Waiver đã hết hạn;
- Cấu hình triển khai đổi khác với candidate được duyệt.

Policy nên quy định **evidence freshness** và **reevaluation triggers**. Khi một trigger xảy ra, deployment job phải **đánh giá lại** điều kiện tương ứng, không chỉ tái sử dụng `ALLOW` lưu trong file cũ.

Ví dụ quyết định có thể ghi:

~~~yaml
candidate:
  service: inventory-service
  commit: a1b2c3d4
  imageDigest: sha256:ACTUAL_DIGEST_FROM_BUILD
decision:
  environment: production
  state: APPROVED_FOR_DEPLOY
  approvedAt: PLACEHOLDER_TIME
  expiresAt: PLACEHOLDER_TIME
  policyRevision: release-policy-v3
  invalidatedBy:
    - artifact_digest_changed
    - supported_consumer_matrix_changed
    - security_gate_changed
    - waiver_expired
~~~

Đây là **schema minh họa cho decision record**, không phải cấu hình SCC/GitHub Actions có sẵn. Những placeholder phải được thay bằng dữ liệu thật. Khi hết hạn hoặc điều kiện thay đổi, trạng thái nên chuyển sang **REVIEW_REQUIRED** hoặc **BLOCKED** theo policy.

## 31. Flaky tests, retry và tình huống “đỏ lần đầu, xanh lần sau”

Một test có thể fail ngẫu nhiên do port collision, database fixture không ổn định hoặc race khi Stub Runner khởi động. Cách xử lý không nên là “rerun đến khi xanh”.

| Quan sát | Cách diễn giải hợp lý |
|---|---|
| PASS ngay lần đầu | Có bằng chứng đạt cho test run đó |
| FAIL rồi PASS sau retry | **Flaky incident** cần ghi lại; quyết định theo policy |
| FAIL luôn với candidate mới | Có regression hoặc lỗi setup thật |
| ERROR do repository không tải được artifact | Chưa có bằng chứng tương thích |
| SKIPPED vì test bị `@Disabled` | Không chứng minh behavior được bảo vệ |
| Test chạy nhưng gọi server khác | Kết quả không liên quan candidate |
| Test xanh nhờ stub cũ | Bằng chứng stale/invalid cho thay đổi mới |

Cách quản lý:

1. Giữ log và nguyên nhân của cả lần FAIL lẫn PASS.
2. Giới hạn retry count; không retry vô hạn.
3. Điều tra fixture, port lifecycle, clocks, eventual consistency và data isolation.
4. Nếu test quan trọng chưa đáng tin, **không dùng PASS ngẫu nhiên để mở auto-deploy**.
5. Nếu có quarantine test, quality gate phải ghi rõ yêu cầu bị loại và owner/deadline sửa.
6. Với integration test network thật, phân biệt hạ tầng không khả dụng với producer/consumer regression.

**Một retry PASS là kết quả test mới, không phải việc xóa lịch sử lỗi.** Khi thiếu thông tin để kết luận, nên giữ deployment ở trạng thái chờ review theo chính sách.

## 32. Viết một policy guard đơn giản, fail closed khi thiếu dữ liệu

Ví dụ dưới đây minh họa một **cổng kiểm chứng evidence** trước khi cho phép một bước deploy tự động. Nó là một cấu phần ví dụ cho CI dùng Bash + `jq`, không thay thế được quyền deployment, security review hoặc toàn bộ policy nghiệp vụ.

Giả sử report `ci-evidence.json` được sinh **bởi các job đáng tin**, có cấu trúc:

~~~json
{
  "candidate": {
    "commit": "a1b2c3d4",
    "imageDigest": "sha256:example",
    "stubsDigest": "sha256:example-stub"
  },
  "producer": {
    "result": "PASS",
    "executed": 18,
    "failed": 0,
    "skipped": 0
  },
  "consumers": {
    "required": [
      {
        "name": "checkout-v3",
        "result": "PASS",
        "executed": 12,
        "stubDigest": "sha256:example-stub"
      }
    ]
  },
  "security": {
    "result": "PASS"
  }
}
~~~

Bash guard minh họa:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

# CI phải cung cấp commit và digest của artifact chuẩn bị deploy.
: "${EXPECTED_COMMIT:?missing expected commit}"
: "${EXPECTED_IMAGE_DIGEST:?missing expected image digest}"
: "${EXPECTED_STUB_DIGEST:?missing expected stubs digest}"

jq -e \
  --arg commit "$EXPECTED_COMMIT" \
  --arg image "$EXPECTED_IMAGE_DIGEST" \
  --arg stub "$EXPECTED_STUB_DIGEST" \
  '
    (.candidate.commit == $commit)
    and (.candidate.imageDigest == $image)
    and (.candidate.stubsDigest == $stub)
    and (.producer.result == "PASS")
    and (.producer.executed > 0)
    and (.producer.failed == 0)
    and (.producer.skipped == 0)
    and ((.consumers.required | length) > 0)
    and (.consumers.required |
      all(.[];
        .result == "PASS"
        and .executed > 0
        and .stubDigest == $stub
      )
    )
    and (.security.result == "PASS")
  ' ci-evidence.json
~~~

Nếu có `FAIL`, `NOT_RUN`, `null` hoặc digest không khớp, `jq -e` thường trả exit code khác 0 và `set -e` làm job **fail closed**. Đây là chủ đích: **missing evidence không được coi là thành công**.

### Giới hạn của ví dụ

- JSON phải được tạo bằng cơ chế **bảo vệ nguồn dữ liệu**; nếu một job không đáng tin tự điền `PASS`, guard không thể xác minh sự thật.
- Phải xác định tập consumers bắt buộc từ dependency registry/policy; chỉ kiểm tra array được gửi vào có thể bỏ sót consumer khác.
- Cần xác minh **report source, executed test names, timestamps, coverage, signatures/attestations** nếu yêu cầu, không chỉ số đếm.
- Chính sách production có thể cần approval, change window, migration và canary rules không nằm trong script.
- Trường digest ví dụ chỉ là placeholder, không phải digest chuẩn để triển khai.

Mục tiêu của đoạn mã là cho thấy **deployment decision đọc và đánh giá bằng chứng có cấu trúc**, không phải chỉ đọc dòng `Tests passed` từ log.

## 33. Waiver: ngoại lệ có kiểm soát không phải PASS

Đôi khi một nhóm phải đưa ra quyết định trong tình huống chưa đủ kiểm thử, ví dụ một consumer nội bộ đã lên lịch ngừng hoạt động nhưng job compatibility của nó hiện không chạy được.

Nếu chính sách **cho phép ngoại lệ**, cần record tối thiểu:

~~~yaml
waiver:
  id: WAIVER-2026-014
  appliesTo:
    candidate: inventory-service:1.4.0-rc.pr173.a1b2c3d4
    environment: staging
    failedOrMissingGate: analytics-v1-compatibility
  status: APPROVED_WITH_RISK
  reason: Job không khả dụng do môi trường thử bị lỗi
  mitigation: Không expose API mới tới Analytics v1
  expiresAt: PLACEHOLDER_TIME
  approverRole: ReleaseManager
  ownerRole: AnalyticsTeam
  remediationTicket: FIX-1234
~~~

Đây là **ví dụ về quản trị**, không phải một ngoại lệ thực đã được duyệt. Một waiver tốt có đặc điểm:

- Chỉ áp dụng **đúng artifact, môi trường, gate và thời hạn**.
- Có người/cơ chế có thẩm quyền và lý do được ghi lại.
- Có giới hạn rủi ro, mitigation, rollback hoặc thời hạn sửa.
- Không làm test report từ FAIL thành PASS.
- Không bỏ qua những cổng mà tổ chức quy định **không thể waive**.
- Bị xét lại nếu artifact hay phạm vi deploy đổi.

**Điểm phân biệt:** `Test status = FAIL/NOT_RUN` vẫn giữ nguyên; `Deployment decision = APPROVED_WITH_RISK` có thể tồn tại **riêng** nếu policy cho phép và các guardrails có hiệu lực. Đừng gọi trạng thái ấy là “toàn bộ kiểm thử đã đạt”.

## 34. Audit trail: “ai quyết định gì dựa trên dữ liệu nào?”

Một decision record nên trả lời được:

1. **Artifact:** commit, image digest, JAR/stubs coordinate và checksum nào?
2. **Contract:** revision nào, những endpoints/messages nào thay đổi?
3. **Producer tests:** generated tests nào chạy, có failures/skips không?
4. **Consumers:** những phiên bản nào thuộc phạm vi hỗ trợ, kết quả từng bản?
5. **Extra gates:** security/compliance/operational readiness nào cần và đã đạt?
6. **Policy:** quy tắc và phiên bản policy nào được áp dụng?
7. **Approval:** ai hoặc cơ chế nào phê duyệt, thời điểm, môi trường, expiry?
8. **Waiver:** nếu có, rủi ro nào được chấp nhận và ai chịu trách nhiệm?
9. **Deployment:** artifact nào thực sự được deploy, timestamp và môi trường?
10. **Runtime:** canary metrics, rollout status, incidents và rollback actions?

Đây là cách phân biệt **báo cáo kiểm thử** với **biên bản cho phép triển khai**. Hai tài liệu liên hệ bằng ID/commit/digest nhưng không nên gộp thông tin đến mức không còn phân biệt “quan sát” và “quyết định”.

Không đưa token, PII, thông tin nhạy cảm hoặc raw production payload vào report; log cần **đủ để truy vết** nhưng tuân thủ data handling policy.

## 35. Case study: hai pipeline xanh, deployment vẫn bị chặn

### Bối cảnh

Inventory v1 trả:

~~~json
{"sku":"SKU-123","available":true,"quantity":12}
~~~

Nhóm Inventory chuẩn bị v2 chỉ trả:

~~~json
{"sku":"SKU-123","inStock":true,"quantity":12}
~~~

Checkout v3 còn dùng `available`. Một nhóm Analytics v1 cũng đang đọc Inventory nhưng chưa có job compatibility trong CI.

### Dữ liệu quan sát

| Bằng chứng | Kết quả |
|---|---|
| Inventory v2 generated producer tests | PASS |
| Inventory v2 stubs JAR | Đã publish candidate |
| Checkout v3 tests với Inventory v1 stable stub | PASS |
| Checkout v3 tests với Inventory v2 candidate stub | NOT_RUN |
| Analytics v1 compatibility với candidate | NOT_RUN |
| Review breaking change | Chưa phê duyệt |
| Deployment window | Có thể triển khai |

**Không có mâu thuẫn** khi nhiều job đều xanh và deployment vẫn bị BLOCK. Lý do là **chưa có bằng chứng candidate tương thích với các consumer đang dùng**, và thay đổi breaking chưa được chấp thuận.

### Sửa quy trình

1. Cho Checkout v3 dùng exact candidate stub v2, chạy client thật.
2. Bổ sung Analytics v1 vào compatibility matrix.
3. Nếu fail, giữ `available` cùng `inStock` theo giai đoạn expand–migrate–contract.
4. Sinh lại producer contract tests và candidate artifact; không sử dụng stub tự viết.
5. Chạy lại consumers với candidate mới, lưu artifact digests.
6. Review release/rollback và các gates khác.
7. Nếu tất cả bắt buộc đạt, cho deploy có canary/monitoring theo policy.

### Bài học

**Kết quả test chưa đầy đủ không phải thất bại của bản thân test runner; đó là thiếu bằng chứng để ra quyết định.** Một quality gate tốt phát hiện khoảng trống ấy và giữ deployment ở trạng thái BLOCK/WAIT thay vì tạo false approval.

## 36. Case study: contract tests đạt nhưng canary vẫn rollback

Inventory v2 được kiểm tra đầy đủ với consumer candidates, test reports có đủ provenance, security gate PASS và release approved. Sau khi deploy canary, p95 latency tăng mạnh vì một truy vấn DB mới thiếu index.

**Diễn giải đúng:**

- Producer/consumer contract tests vẫn PASS với phạm vi HTTP behavior đã kiểm tra.
- **Operational canary gate FAIL** vì runtime latency vượt guardrail.
- Quyết định rollout chuyển từ ALLOW sang **HALT/ROLLBACK**.
- Phần còn lại của production traffic không nên tiếp tục tăng theo kế hoạch cũ.

Không cần xóa test reports hoặc tuyên bố SCC “sai”. Cần thêm performance/regression test phù hợp, tối ưu query, cập nhật canary policy và thử lại candidate theo quy trình.

Trường hợp này cho thấy **quyết định triển khai có thể thay đổi khi có dữ liệu mới**, trong khi lịch sử kết quả kiểm thử vẫn nguyên vẹn.

## 37. Bài thực hành A — Tạo bảng trạng thái test và bảng deployment decision

**Mục tiêu:** thực hành phân biệt một quan sát kỹ thuật với một quyết định.

1. Giả lập producer candidate Inventory `1.4.0-rc1` có generated tests PASS (18/18).
2. Cho Checkout v3 test với stub v1 PASS, nhưng chưa thử candidate.
3. Ghi từng result đúng: producer PASS, Checkout-stable PASS, Checkout-candidate NOT_RUN.
4. Tạo decision record cho production: **BLOCK do thiếu consumer candidate evidence**.
5. Sau đó giả lập Checkout-candidate PASS nhưng Analytics v1 NOT_RUN.
6. Duy trì BLOCK nếu Analytics nằm trong policy required consumers.
7. Giả lập Analytics PASS, artifact digests khớp, security/approval đầy đủ.
8. Lúc này mới chuyển thành `ALLOW`, ghi rõ policy revision.

**Sản phẩm cần có:** hai bảng riêng, lý do quyết định và artifact IDs cho mỗi lượt.

## 38. Bài thực hành B — Tạo lỗi có chủ đích để kiểm tra quality gate

**Mục tiêu:** chứng minh policy phát hiện những trường hợp xanh giả.

1. Trong producer test branch, khiến test base trả fake response đúng contract; thử mutation code production. Nếu test vẫn xanh, ghi nhận test không bảo vệ code thật.
2. Khôi phục base class đúng; mutation cần làm generated test đỏ.
3. Bật cờ skip test trong nhánh thử; pipeline guard phải phát hiện **executed tests = 0**.
4. Cho consumer test dùng stale stub version; provenance check phải chặn.
5. Mock trực tiếp consumer HTTP client; test có thể xanh nhưng không phát HTTP request. Thay bằng client thật.
6. Làm request body matcher quá rộng; thử request sai kiểu và quan sát nó bị nhận.
7. Khôi phục matcher phù hợp, negative test phải phát hiện request không đúng.
8. Xác nhận policy không mở deploy khi một required check `SKIPPED`, `NOT_RUN` hoặc `STALE`.

**Sản phẩm cần có:** bảng “false PASS → nguyên nhân → cách phát hiện → hành động sửa”, log/test report từng tình huống.

## 39. Bài thực hành C — Bổ sung điều kiện phê duyệt và canary

1. Thiết kế giả lập pipeline có ba gates: producer contracts, consumer compatibility và security readiness.
2. Định nghĩa policy yêu cầu đủ ba bằng chứng PASS và đúng artifact digest.
3. Đưa vào bước production approval có reviewer có thẩm quyền.
4. Nếu thiếu approval, giữ trạng thái `WAIT_APPROVAL` dù tests PASS.
5. Khi approval hợp lệ, chạy canary 5% traffic trong mô phỏng.
6. Nếu error rate vượt ngưỡng minh họa, chuyển sang `HALT` và ghi rollback action.
7. Giữ nguyên test reports PASS; ghi canary health FAIL **riêng**.
8. Thử waiver cho một gate không bắt buộc chỉ nếu policy cho phép; ghi phạm vi, expiry và owner.

**Sản phẩm cần có:** decision matrix, decision record, log status transitions và sơ đồ rollback/mitigation.

## 40. Troubleshooting: vì sao job xanh nhưng deploy gate vẫn chặn?

| Hiện tượng | Điều cần kiểm tra | Không nên kết luận vội |
|---|---|---|
| Producer tests xanh, deploy BLOCK | Consumer matrix có đủ version? | “CI lỗi vì không tin test” |
| Consumer test xanh, artifact mismatch | Stub Runner resolve candidate nào? | “Test đã chứng minh ứng viên mới” |
| Test report hiển thị 0 tests | Generator/runner/skip flags | “Không có lỗi nên PASS” |
| Status `SKIPPED` | Test có bị disable theo profile? | “Test gần như PASS” |
| Build report stale | Cache/workspace/test report timestamp | “Là kết quả commit hiện tại” |
| Candidate digest đổi sau build | Có rebuild/tag overwrite? | “Version giống nên an toàn” |
| Nhiều consumer PASS, một NOT_RUN | Consumer đó required hay N/A? | “Đa số đã pass nên cho deploy” |
| Approval chưa có | Environment protection và owner | “Một developer có quyền merge tức được deploy” |
| Deployment freeze | Change window/incident policy | “Contract tests bị lỗi” |
| Canary metrics xấu | SLO guardrails và runtime evidence | “Contract tests không có giá trị” |
| Rerun PASS sau FAIL | Flaky cause và retry policy | “FAIL cũ không còn cần quan tâm” |
| Waiver hết hạn | Scope, expiry và approver | “Ngoại lệ vĩnh viễn” |

Thứ tự điều tra hợp lý:

~~~text
1. Xác định candidate artifact chính xác
2. Xác định gate đang chặn và policy revision
3. Kiểm tra reports: PASS/FAIL/ERROR/SKIPPED/NOT_RUN/STALE
4. Kiểm tra contract producer và consumer compatibility provenance
5. Kiểm tra supplementary gates, approvals, environment restrictions
6. Kiểm tra runtime rollout/canary nếu đã deploy một phần
7. Lập action item với owner và bằng chứng bổ sung cần thu thập
~~~

Mỗi tầng có ý nghĩa khác nhau. Đừng “fix deployment” bằng cách xóa một required check chỉ vì nguyên nhân đang ở artifact provenance hoặc approval.

## 41. Checklist review release authorization

- [ ] Đã phân biệt **test status** với **deployment decision** trong report.
- [ ] Contract Groovy/YAML thuộc đúng producer commit và đã được review.
- [ ] Generated producer tests được sinh, compile, thực thi **> 0** và đạt.
- [ ] Test base gọi implementation producer thật, không fake response.
- [ ] Stubs JAR được sinh từ cùng contract revision và đúng classifier.
- [ ] Artifact version/digest của stubs tương ứng producer candidate.
- [ ] Consumer tests sử dụng **client/message handler thật** qua Stub Runner.
- [ ] Stub Runner nạp đúng candidate, không stale SNAPSHOT hoặc mapping cũ.
- [ ] Danh sách required consumer versions đã được owner xác nhận.
- [ ] Compatibility matrix đủ các consumers cần hỗ trợ, không thay NOT_RUN bằng PASS.
- [ ] Test cover success/error cases và các trường hợp breaking quan trọng.
- [ ] Khi cần, mutation/negative tests chứng minh suite có khả năng phát hiện sai.
- [ ] Bằng chứng có commit, digest, test count, timestamp và report URI.
- [ ] Artifact thực sự deploy là **artifact đã được duyệt**, không rebuild ngầm.
- [ ] Các gates về security, migration, config và operation được đánh giá theo policy.
- [ ] Những `SKIPPED`, `ERROR`, `STALE`, `UNKNOWN` được xử lý tường minh.
- [ ] Flaky test retries có log nguyên nhân và giới hạn.
- [ ] Không có required check bị disable chỉ để dashboard xanh.
- [ ] Deployment window và environment permissions đáp ứng.
- [ ] Nếu cần manual approval, có approver đúng thẩm quyền.
- [ ] Waiver (nếu được phép) có scope, risk, owner, expiry và mitigation.
- [ ] Rollout có health checks, guardrails và rollback/disable-flag plan.
- [ ] Decision record phân biệt ALLOW/BLOCK/WAIT và giữ nguyên raw test results.
- [ ] CI không lộ token/PII/secret trong fixtures, logs hay evidence artifact.
- [ ] Những điều chưa được test được ghi rõ, không suy luận ngoài phạm vi.

## 42. Câu hỏi tự kiểm tra

**1. Producer contract tests PASS có đủ cho phép triển khai producer API mới không?**

Không. Chúng chứng minh implementation producer đáp ứng contract đã test, không chứng minh các consumer cũ vẫn tương thích hoặc các điều kiện vận hành khác đã đáp ứng.

**2. Consumer test PASS nhưng dùng stub của commit trước có chứng minh candidate hiện tại an toàn không?**

Không. Kết quả gắn với artifact cũ và phải bị coi là **STALE/không liên quan candidate** trong release gate.

**3. Một job bị SKIPPED có được xem là PASS nếu không hiển thị failure không?**

Không. Nếu đó là required check, thiếu executed test evidence phải làm gate block/wait hoặc đi qua quy trình ngoại lệ hợp lệ.

**4. Tại sao approval thủ công và test PASS cần lưu riêng?**

Vì test PASS là quan sát kỹ thuật; approval là quyết định có thẩm quyền về phạm vi/rủi ro/môi trường. Approval không biến failed tests thành passed tests.

**5. Đã có production approval, deployment có luôn thành công không?**

Không. Deployment vẫn có thể fail, hoặc canary/health gates không đạt. Cần giám sát rollout và rollback/halt theo policy.

**6. Nếu kết quả một required consumer là NOT_RUN, một trăm consumer khác PASS thì sao?**

Không được đổi NOT_RUN thành PASS. Policy cần quyết định BLOCK/WAIT hoặc ngoại lệ được kiểm soát; đa số đạt không thay thế một điều kiện bắt buộc.

**7. Vì sao phải gắn artifact digest với test evidence?**

Để bảo đảm artifact được test là artifact đang được xét deploy; version string/tag có thể bị ghi đè, đặc biệt SNAPSHOT hoặc mutable image tags.

**8. Có thể dùng waiver để vượt qua compatibility failure không?**

Chỉ khi chính sách tổ chức cho phép, phạm vi/rủi ro/owner/expiry/mitigation được ghi rõ. Test FAIL vẫn phải được ghi là FAIL, không giả dạng PASS.

**9. Test contract có tự phát hiện DB index thiếu khiến canary chậm không?**

Thường không. Đó là rủi ro performance/runtime cần test, giám sát và rollout gate riêng.

**10. Khác biệt giữa RELEASE_APPROVED và DEPLOYED_HEALTHY là gì?**

RELEASE_APPROVED cho biết policy cho phép dùng candidate ở môi trường/thời điểm xác định; DEPLOYED_HEALTHY cần bằng chứng sau khi triển khai thành công và health metrics đáp ứng điều kiện vận hành.

## 43. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): generated producer tests, Groovy/YAML DSL, stubs và Stub Runner.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): HTTP/message contracts, matchers và cấu trúc nguồn.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): tải artifact và chạy consumer compatibility tests.
- [Spring Cloud Contract — Maven](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): sinh producer tests và đóng gói stubs JAR.
- [Spring Cloud Contract — Gradle](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): Gradle plugin và build integration.
- [GitHub Actions — Workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): jobs, needs, environment và conditions.
- [GitHub — Deployments and environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments): protection rules, reviewers và deployment configuration.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): test discovery/execution/reporting.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): kiểm tra client request và unmatched calls.
- [Martin Fowler — Consumer-Driven Contracts](https://martinfowler.com/articles/consumerDrivenContracts.html): tư duy hợp đồng theo nhu cầu consumer.
- [Martin Fowler — BlueGreenDeployment](https://martinfowler.com/bliki/BlueGreenDeployment.html): một chiến lược triển khai và rollback có kiểm soát.

**Lưu ý phiên bản/phạm vi:** Cú pháp SCC Contract Verifier, Stub Runner, plugin Maven/Gradle và các tính năng CI platform có thể khác theo phiên bản được sử dụng. Các giá trị artifact, digest, test count và deployment trong bài đều là **ví dụ minh họa**, chưa được chạy ở một repository thật. Các quy tắc ALLOW/BLOCK/WAIT, waiver, compatibility matrix và approval là **đề xuất policy cần điều chỉnh theo tổ chức**, không phải enum mặc định của SCC. Bước biên soạn này không chạy Maven/Gradle, không thực hiện release hoặc Content QA chuyên sâu.

---

**Điểm cần nhớ:** **Kết quả kiểm thử trả lời “điều gì đã được kiểm chứng, với phiên bản và phạm vi nào?”; quyết định cho phép triển khai trả lời “liệu toàn bộ bằng chứng, chính sách, thẩm quyền và điều kiện vận hành đã đủ cho artifact và môi trường đích hay chưa?”**. Dùng Spring Cloud Contract để kiểm chứng producer code thật, dùng Stub Runner để kiểm chứng consumer thật với candidate stubs đúng revision, sau đó đánh giá đầy đủ quality gates, approvals và rủi ro rollout. Chỉ như vậy, một pipeline màu xanh mới trở thành **bằng chứng đáng tin**, thay vì một giấy phép triển khai bị suy luận quá mức.
