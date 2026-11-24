# Ma trận phiên bản và bằng chứng cần cho từng tổ hợp

## Mục tiêu bài học

Trong **Spring Cloud Contract**, hợp đồng **Groovy DSL** hoặc **YAML DSL** mô tả hành vi HTTP/thông điệp giữa **producer** và **consumer**. Contract Verifier sinh kiểm thử phía producer; từ cùng hợp đồng, hệ thống có thể sinh và phát hành **stub artifact** để consumer dùng qua **Stub Runner**. Việc cả hai phía từng có test xanh chưa đủ để kết luận mọi phiên bản đang triển khai tương thích: **phải xác minh đúng cặp phiên bản** và lưu bằng chứng tương ứng.

Trong chương **Phiên bản và tương thích**, bài **“Ma trận phiên bản và bằng chứng cần cho từng tổ hợp”** trả lời bốn câu hỏi:

1. Phiên bản producer nào phải hoạt động với phiên bản consumer nào?
2. Một ô `Pᵢ × Cⱼ` thực sự đại diện cho phép thử gì?
3. Cần lưu **kết quả producer contract tests, phiên bản/checksum stub, contract revision và consumer test report** thế nào để tuyên bố PASS có cơ sở?
4. Khi có ô FAIL, chưa chạy hoặc không còn được hỗ trợ, quyết định **triển khai, rollback hay trì hoãn** ra sao?

Sau bài, bạn có thể lập ma trận cho nhiều phiên bản producer/consumer, phân biệt tương thích ngược và tương thích xuôi theo hướng phụ thuộc, xây pipeline kiểm thử với Stub Runner, lập hồ sơ bằng chứng cho từng ô và xác định những giới hạn mà hợp đồng chưa bao phủ.

## 1. Ma trận phiên bản cần giải quyết vấn đề gì?

Giả sử:

- **Order Service** là producer của API `GET /api/orders/{id}`.
- **Checkout Service** và **Sales Portal** là các consumer của Order Service.
- Order Service phiên bản `2.4.0` trả trường JSON `status`.
- Order Service phiên bản `2.5.0` dự định chuyển sang `paymentStatus`.
- Một số phiên bản Checkout đã triển khai **vẫn đọc `status`**.

Nếu Checkout test với stub `2.4.0` và PASS, điều đó **không chứng minh** Checkout sẽ chạy với producer `2.5.0`. Tương tự, Order Service `2.5.0` PASS producer contract tests cũng chưa chứng minh **mọi consumer cũ** sẽ xử lý được response mới nếu những kỳ vọng của chúng chưa được biểu diễn đầy đủ trong hợp đồng.

~~~mermaid
flowchart LR
    P1["Order Service 2.4.0"] --> C1["Checkout 1.8.0"]
    P2["Order Service 2.5.0"] --> C1
    P2 --> C2["Checkout 2.0.0"]
    P1 --> C2
    P2 --> C3["Sales Portal 4.1.0"]
~~~

Các đường kết nối thể hiện **những cặp cần đánh giá**, không tự nói chúng PASS. Mỗi đường phải có một trạng thái và bằng chứng riêng.

**Ma trận phiên bản** là bản đồ các tổ hợp `producer version × consumer version` có thể cùng tồn tại trong thực tế hoặc trong kế hoạch triển khai, kèm kết quả kiểm chứng và quyết định hỗ trợ.

## 2. Xác định chính xác “phiên bản” đang nói đến

Trong Spring Cloud Contract, nhiều loại version cùng xuất hiện nhưng có vai trò khác nhau.

| Loại phiên bản/định danh | Ví dụ | Vai trò |
| --- | --- | --- |
| **Producer service version** | `order-service:2.5.0` | Bản producer dự kiến chạy hoặc đã triển khai |
| **Consumer service version** | `checkout-service:1.8.0` | Bản consumer đang chạy, chuẩn bị chạy hoặc có thể rollback |
| **Contract revision** | `contracts@def456` | Nội dung DSL đã dùng để kiểm chứng |
| **Stub artifact version** | `2.5.0:stubs` | Bộ stub đại diện cho hành vi producer được công bố |
| **Stub artifact checksum** | SHA-256 được tính từ JAR | Bytes thực tế được sử dụng |
| **Producer Git commit** | `order-service@abc123` | Mã producer đã build và chạy tests |
| **Consumer Git commit** | `checkout-service@cde789` | Mã consumer đã được kiểm tra |
| **Verifier/Stub Runner version** | Version Spring Cloud Contract trong build | Phiên bản công cụ kiểm thử, không phải business API version |
| **Schema/message version** | `schemaVersion: 2` | Version của payload/protocol, không nhất thiết bằng Maven version |

**Không đánh đồng** `order-service:2.5.0` với `schemaVersion: 2` hoặc version của Spring Cloud Contract plugin. Các phiên bản này có thể thay đổi độc lập và cần được ghi lại nếu ảnh hưởng phép thử.

Cũng không mặc định Docker image tag, Maven artifact version và Git tag luôn cùng một nội dung. Release pipeline phải xác minh cách ánh xạ giữa chúng.

## 3. Ma trận có hai trục chính, nhưng cần thêm metadata

Ma trận cơ bản:

- **Hàng:** producer versions `P₁, P₂, ...`.
- **Cột:** consumer versions `C₁, C₂, ...`.
- **Ô:** kết quả và bằng chứng khi **consumer Cⱼ tương tác với hành vi của producer Pᵢ** theo kịch bản đã thỏa thuận.

Ví dụ hoàn toàn **giả định để học cách đọc**, không phải kết quả test đã chạy:

| Producer \ Consumer | Checkout 1.8.0 (cũ) | Checkout 2.0.0 (mới) |
| --- | --- | --- |
| **Order 2.4.0 (cũ)** | PASS mẫu | NOT_RUN |
| **Order 2.5.0 (chuyển tiếp)** | PASS mẫu | PASS mẫu |
| **Order 2.6.0 (bỏ field cũ)** | FAIL mẫu | PASS mẫu |

Từ bảng minh họa:

- `Order 2.5.0 × Checkout 1.8.0` **đáng chú ý** để bảo vệ consumer cũ khi nâng producer.
- `Order 2.4.0 × Checkout 2.0.0` quan trọng nếu consumer có thể được triển khai trước producer, hoặc producer có thể **rollback**.
- `Order 2.6.0 × Checkout 1.8.0` là ví dụ rủi ro phá vỡ tương thích nếu Checkout cũ còn phụ thuộc trường đã bị xóa.
- `NOT_RUN` không thể được coi là PASS hay FAIL; đó là **thiếu bằng chứng**.

Một bảng trạng thái chỉ là phần nhìn nhanh. Mỗi ô PASS cần tham chiếu tới record chứa **producer verification, stub identity và consumer run** thực tế.

## 4. Định nghĩa rõ hướng tương thích

Các cụm “backward compatible” và “forward compatible” dễ gây hiểu nhầm nếu không chỉ rõ chủ thể. Trong bài này dùng định nghĩa theo **quan hệ producer–consumer**:

| Phép thử | Câu hỏi | Khi nào quan trọng |
| --- | --- | --- |
| **Producer mới × consumer cũ** | Producer mới còn phục vụ consumer đã triển khai trước đó không? | Nâng producer, tương thích ngược |
| **Producer cũ × consumer mới** | Consumer mới còn làm việc với producer chưa nâng hoặc bị rollback không? | Nâng consumer trước, rollback producer, tương thích xuôi theo hướng consumer |
| **Producer mới × consumer mới** | Hai bản mục tiêu có hoạt động với nhau không? | Triển khai mục tiêu |
| **Producer cũ × consumer cũ** | Baseline cũ đã được xác minh chưa? | Đối chiếu và phân tích hồi quy |

Nếu trong tổ chức có quy ước đặt tên “forward/backward” khác, hãy **ghi cụ thể hai phiên bản ở từng phía** thay vì chỉ dùng nhãn. Bản chất kỹ thuật là **P phiên bản nào tương tác với C phiên bản nào**.

### Đặc biệt quan trọng khi triển khai từng phần

Trong một hệ thống phân tán, hai service có thể không nâng cấp đồng thời:

~~~text
Thời điểm T0: P_old + C_old
Thời điểm T1: P_new + C_old
Thời điểm T2: P_new + C_new
Rollback P:   P_old + C_new
~~~

Nếu có khả năng rollback producer sau khi nâng consumer, **P_old × C_new** không thể bị loại khỏi ma trận chỉ vì kế hoạch chính là cập nhật producer trước.

## 5. Ví dụ xuyên suốt: đổi JSON field mà không phá consumer cũ

Giả sử consumer Checkout 1.8.0 đọc:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

Một producer mới muốn đổi tên `status` thành `paymentStatus`.

### Cách thay đổi phá tương thích

Producer 2.5.0 chỉ trả:

~~~json
{
  "id": "ORD-1001",
  "paymentStatus": "PAID"
}
~~~

Nếu Checkout 1.8.0 bắt buộc có trường `status`, tổ hợp `P2.5 × C1.8` có nguy cơ FAIL. Thêm một trường mới và xóa trường cũ trong cùng lần phát hành là hai tác động khác nhau.

### Cách mở rộng tạm thời để chuyển tiếp

Producer 2.5.0 có thể trả đồng thời:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID",
  "paymentStatus": "PAID"
}
~~~

Checkout 1.8.0 tiếp tục đọc `status`; Checkout 2.0.0 đọc `paymentStatus`. Trong một giai đoạn, cả hai consumer có thể hoạt động.

**Không mặc định “thêm trường là luôn tương thích”.** Một consumer có JSON deserializer rất nghiêm ngặt, schema validation chặt hoặc xử lý nhầm khi có hai trường có thể từ chối response. Vì vậy vẫn phải **chạy test consumer cũ** với response mới.

### Hợp đồng YAML cho giai đoạn chuyển tiếp

~~~yaml
description: "Trả cả status cũ và paymentStatus mới"
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

Hợp đồng mô tả hành vi mà producer phải thực sự đáp ứng. Không chỉnh contract thành response lý tưởng rồi **mock nguyên controller trả JSON mẫu** để làm generated producer test PASS; điều đó có thể bỏ qua logic producer cần xác minh.

### Kế hoạch ba pha

1. **Expand:** producer phát cả `status` và `paymentStatus`; xác minh với các consumer còn dùng cả hai schema.
2. **Migrate:** consumer lần lượt chuyển sang `paymentStatus`, nhưng vẫn cần kiểm tra phiên bản producer cũ nếu có khả năng rollback.
3. **Contract:** chỉ bỏ `status` khi danh sách consumer còn được hỗ trợ không phụ thuộc vào nó, ma trận và chính sách rollout cho phép.

Đây là chiến lược **expand–migrate–contract**, không phải quy định cú pháp bắt buộc của Spring Cloud Contract.

## 6. Những trạng thái cần có trong từng ô

Một ma trận có thể sử dụng bộ trạng thái sau. Chúng là **quy ước quản trị do nhóm thiết kế**, không phải enum có sẵn của Contract Verifier:

| Trạng thái | Ý nghĩa | Có thể tính là tương thích đã xác minh? |
| --- | --- | --- |
| **PASS** | Consumer tests thật sự chạy với stub đúng producer/version và PASS; producer verification tương ứng có bằng chứng | Có, **trong phạm vi kịch bản đã chạy** |
| **FAIL** | Một phép thử đã chạy và thất bại | Không; cần điều tra |
| **NOT_RUN** | Chưa chạy hoặc chưa có report | Không; chưa biết |
| **BLOCKED** | Không chạy được vì thiếu artifact, test infra hoặc quyền | Không; chưa biết |
| **SKIPPED** | Test/cell bị bỏ qua theo cấu hình | Không, trừ khi có chính sách riêng làm rõ lý do |
| **NOT_APPLICABLE** | Tổ hợp nằm ngoài kiến trúc hoặc không thể cùng tồn tại theo triển khai đã chứng minh | Không phải PASS; cần giải thích |
| **UNSUPPORTED** | Tổ hợp không còn được cam kết hỗ trợ theo chính sách phiên bản đã công bố | Không phải PASS; chỉ loại khỏi release gate khi được phê duyệt |
| **STALE** | Đã PASS với artifact, commit hoặc report khác/đã cũ so với bản cần đánh giá | Không cho release hiện tại |

Đặc biệt **NOT_RUN ≠ PASS** và **BLOCKED ≠ FAIL**. Một ô chưa thể chạy vì repository lỗi không chứng minh code consumer sai, nhưng cũng không cho phép tuyên bố tương thích.

### Hãy lưu trạng thái có lý do

~~~yaml
# Record minh họa do nhóm tự thiết kế.
producer_version: "2.5.0"
consumer_version: "1.8.0"
status: NOT_RUN
reason: "Chưa có consumer build của phiên bản 1.8.0"
required_for_release: true
~~~

Nếu ô này bắt buộc trong giai đoạn triển khai, release gate nên **chặn hoặc yêu cầu quyết định rủi ro có thẩm quyền**, không tự chuyển `NOT_RUN` thành `PASS`.

## 7. Bằng chứng cần cho từng ô ma trận

Một ô `Pᵢ × Cⱼ` không chỉ có “X” hoặc “✓”. Tối thiểu nên có các nhóm bằng chứng:

| Nhóm | Trường cần ghi | Mục đích |
| --- | --- | --- |
| **Danh tính producer** | Service/version/Git commit/build ID | Biết implementation nào được đánh giá |
| **Danh tính contract** | Repo/contract revision/contract IDs hoặc path | Biết những cam kết nào được sử dụng |
| **Producer verification** | CI run ID/report, số generated tests thực sự chạy, PASS/FAIL/SKIPPED | Xác minh producer đáp ứng contract |
| **Stub provenance** | GAV + classifier, repository, SHA-256, nguồn build | Bảo đảm stub là artifact từ producer verification tương ứng |
| **Danh tính consumer** | Service/version/Git commit/build configuration | Biết mã consumer nào đã chạy |
| **Consumer verification** | Run ID/report, assertions và trạng thái | Biết consumer xử lý những kịch bản đó ra sao |
| **Phạm vi** | Scenario IDs, protocol, flags, test environment | Biết những gì được và không được chứng minh |
| **Quyết định** | PASS/FAIL/NOT_RUN, required_for_release, thời điểm | Dùng cho release gate và audit |

**Quan hệ trọng yếu:** stub artifact trong consumer test phải được tạo từ **cùng contract input và producer build đã có producer verification phù hợp**. Nếu chỉ có một file stub JAR không rõ nguồn gốc, ô PASS không đủ chắc chắn.

### Mẫu evidence record cho một ô

~~~yaml
# Định dạng do nhóm tự thiết kế, không phải output mặc định SCC.
schema: "compatibility-cell/v1"
producer:
  service: order-service
  version: "2.5.0"
  git_commit: "abc123_FULL_COMMIT"
  build_id: "producer-ci-7824"
contracts:
  repository: "order-contracts"
  revision: "def456_FULL_COMMIT"
  scenarios:
    - get_paid_order_transition
    - get_missing_order
producer_verification:
  run_id: "producer-ci-7824"
  generated_tests_executed: true
  passed: true
  skipped: 0
  report_uri: "ci://producer-ci-7824/reports"
stub:
  coordinate: "com.example.orders:order-service:2.5.0:stubs"
  repository: "https://repo.example.test/maven/releases"
  sha256: "SHA256_DUOC_TINH_TU_JAR_THAT"
consumer:
  service: checkout-service
  version: "1.8.0"
  git_commit: "cde789_FULL_COMMIT"
consumer_verification:
  run_id: "consumer-ci-8812"
  resolved_stub_sha256: "SHA256_DUOC_XAC_MINH"
  passed: true
  skipped: 0
  report_uri: "ci://consumer-ci-8812/reports"
decision:
  status: PASS
  required_for_release: true
  scope: "GET order paid/missing qua HTTP stub"
~~~

Các giá trị trên chỉ minh họa cấu trúc. Để tạo **bằng chứng thật**, CI phải lấy Git revision, test results, artifact bytes và resolved stub từ lần chạy thực tế. Đừng ghi `passed: true` trước khi test kết thúc hoặc dùng chuỗi `SHA256_...` như một checksum hợp lệ.

## 8. Vì sao phải lưu cả producer tests và consumer tests?

Hai loại kiểm thử bổ sung cho nhau:

~~~mermaid
flowchart LR
    C["Hợp đồng YAML/Groovy"] --> PT["Generated producer tests"]
    C --> ST["Stub JAR"]
    P["Producer implementation P_i"] --> PT
    PT --> V["Producer verification result"]
    ST --> SR["Stub Runner"]
    SR --> CT["Consumer C_j integration tests"]
    CT --> R["Consumer result"]
    V --> E["Bằng chứng cho ô P_i × C_j"]
    R --> E
~~~

- **Producer contract tests**: kiểm tra implementation producer đang thực hiện đúng hành vi mô tả.
- **Stub Runner consumer tests**: kiểm tra consumer xử lý các stub scenarios tương ứng.
- **Artifact provenance**: nối hai nhánh với cùng nguồn hợp đồng/bản build.

Nếu producer tests chưa chạy, consumer PASS chỉ chứng minh consumer xử lý được **mock/stub**. Nếu consumer tests chưa chạy, producer PASS chưa chứng minh ứng dụng consumer cụ thể còn xử lý được hành vi mới.

### Một giới hạn quan trọng

Producer contract tests và consumer stub tests chỉ bảo vệ những behavior đã được mô tả đủ trong contracts và được test thật sự. Nếu Checkout dùng một header chưa được hợp đồng hóa hoặc một trường JSON bị matcher bỏ qua, hai bên vẫn có thể xanh nhưng production integration lỗi.

Ma trận không thay thế việc thiết kế **contract coverage** và các integration tests bổ sung.

## 9. Stub artifact phải khớp producer version

Trong Spring Cloud Contract, stub HTTP thường được đóng gói như một Maven artifact có classifier `stubs`:

~~~text
groupId      : com.example.orders
artifactId   : order-service
version      : 2.5.0
classifier   : stubs

Maven coordinate:
com.example.orders:order-service:2.5.0:stubs

Tên file thường thấy:
order-service-2.5.0-stubs.jar
~~~

Bốn thành phần xác định một artifact. Ngoài ra, nên lưu **SHA-256** của JAR đã publish, vì version `SNAPSHOT` có thể được cập nhật và một repository bị cấu hình sai có thể cho phép ghi đè release.

### Truy vết từ hợp đồng tới stub

~~~text
contract repository revision
        |
        +--> generated producer tests --> producer verification PASS
        |
        +--> stub mappings --> order-service-2.5.0-stubs.jar
                                      |
                                      +--> GAV/classifier
                                      +--> SHA-256
                                      +--> repository URL
                                              |
                                              +--> Stub Runner của Checkout
~~~

Không nên “copy JAR nào đó có tên gần giống” vào consumer test rồi ghi `P2.5 × C1.8 PASS`. Phải chứng minh **đúng GAV/checksum** được giải quyết từ đúng nguồn.

### Test với release candidate và release chính thức

Nếu producer có:

~~~text
2.5.0-rc1:stubs
2.5.0:stubs
~~~

hai coordinate này **không tự tương đương**. Kết quả consumer PASS với `rc1` không mặc nhiên áp dụng cho bản `2.5.0` nếu artifact cuối được rebuild hoặc có bytes khác. Muốn chuyển kết quả, cần quy trình promote cùng artifact đã verified và bằng chứng checksum/nguồn gốc phù hợp; nếu không, chạy lại kiểm thử cho bản cuối.

## 10. Consumer dùng Stub Runner để kiểm tra đúng một ô

Một consumer test dùng Spring Cloud Contract Stub Runner có thể cấu hình:

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
class CheckoutAgainstOrder250ContractTest {

    @Test
    void checkoutHandlesPaidOrder() {
        // Cấu hình HTTP client của Checkout gọi stub port 8090.
        // Thực hiện nghiệp vụ Checkout.
        // Assert trạng thái/nhánh xử lý mà Checkout phụ thuộc.
    }
}
~~~

Đây là **khung test minh họa**, chưa phải test hoàn chỉnh. Nó cần cấu hình client, dependencies và assertions thực tế. Lớp test này có thể chạy với **source/tag của Checkout 1.8.0** hoặc 2.0.0 theo tổ hợp cần đánh giá, thay vì chỉ chạy consumer HEAD.

Trong Stub Runner ID:

~~~text
com.example.orders:order-service:2.5.0:stubs:8090
        group            artifact  version classifier port
~~~

**Port 8090 không thuộc tọa độ Maven artifact.** Nó chỉ là tham số runtime của stub server trong cách khai báo ID này.

### Điều quan trọng khi kiểm tra P2.5 × C1.8

Nếu consumer test đang dùng:

~~~text
com.example.orders:order-service:2.4.0:stubs:8090
~~~

thì đó là bằng chứng cho **P2.4 × C1.8**, không phải **P2.5 × C1.8**. Đổi tên báo cáo hoặc tên job CI không biến một bản stub cũ thành bản mới.

### Không dùng “latest” để quyết định phát hành

Nếu phiên bản Stub Runner cho phép version động kiểu `+`:

~~~text
com.example.orders:order-service:+:stubs:8090
~~~

cùng một commit consumer có thể tải hai artifact khác nhau ở hai lần chạy. Với **release gate**, nên dùng version cố định, log version thực sự phân giải và kiểm tra checksum khi chính sách yêu cầu.

## 11. Ma trận tối thiểu khi nâng cấp từng phía

Giả sử deployment hiện tại:

~~~text
P_old = Order 2.4.0
C_old = Checkout 1.8.0

Mục tiêu:
P_new = Order 2.5.0
C_new = Checkout 2.0.0
~~~

Một ma trận 2 × 2 cơ bản:

| Tổ hợp | Tại sao cần kiểm tra? | Bằng chứng cụ thể |
| --- | --- | --- |
| **P_old × C_old** | Baseline hiện đang hoạt động | Historical producer verification P_old + consumer test C_old trên stub P_old |
| **P_new × C_old** | Nâng producer trước consumer | Producer verification P_new + C_old trên stub P_new |
| **P_old × C_new** | Nâng consumer trước producer hoặc rollback producer | Producer verification P_old + C_new trên stub P_old |
| **P_new × C_new** | Môi trường mục tiêu | Producer verification P_new + C_new trên stub P_new |

**Không phải mọi tổ hợp luôn bắt buộc.** Nếu tổ chức chứng minh P_old và C_new **không thể cùng tồn tại** và không có kế hoạch rollback tạo ra tổ hợp đó, có thể đánh dấu `NOT_APPLICABLE` với lý do được phê duyệt. Nhưng không nên bỏ ô chỉ vì nó chưa được nhắc tới trong kế hoạch chính.

### Khi nhiều consumer tồn tại

Giả sử Order Service phục vụ:

- Checkout `1.8.0` (đã triển khai).
- Checkout `2.0.0` (chuẩn bị triển khai).
- Sales Portal `4.1.0` (đã triển khai).
- Analytics `1.3.0` (job theo lịch vẫn sử dụng API).

Khi nâng producer, ma trận có thể thêm cột cho từng **consumer service/version**, không chỉ “một consumer mới nhất”.

| Producer | Checkout 1.8 | Checkout 2.0 | Sales 4.1 | Analytics 1.3 |
| --- | --- | --- | --- | --- |
| Order 2.4 | PASS lịch sử | Cần kiểm tra nếu rollback | PASS lịch sử | PASS lịch sử |
| Order 2.5 | **Bắt buộc** | **Bắt buộc** | **Bắt buộc** | **Bắt buộc** nếu còn hỗ trợ |

Một hàng chưa có kết quả không nên điền PASS chỉ vì không ai báo lỗi production. **Không có cảnh báo** không phải là **bằng chứng CI**.

## 12. Ma trận không đồng nghĩa chạy mọi tổ hợp vô hạn

Trong tổ chức lớn, số ô tăng nhanh: nhiều producer releases, consumer releases, protocol versions và feature flags. Chạy đầy đủ mọi version lịch sử có thể không khả thi.

Nên chọn phạm vi theo **chính sách hỗ trợ và khả năng cùng tồn tại thực tế**, không chỉ theo số lượng.

### Phạm vi tối thiểu nên xem xét

1. **Producer target × mọi consumer version đang hoạt động và còn được hỗ trợ.**
2. **Producer đang chạy × consumer target**, nếu consumer có thể deploy trước hoặc producer có thể rollback.
3. **Target × target** cho trạng thái triển khai mong muốn.
4. Những cặp cần thiết do **canary, blue/green, rolling upgrade**, vùng địa lý, tenant hoặc ứng dụng mobile offline.
5. Những cặp đã có FAIL hoặc breaking change cần tái kiểm tra sau sửa lỗi.

### Phạm vi có thể loại khỏi release gate

- Consumer version đã ngừng hỗ trợ và **không còn instance/client nào sử dụng** theo bằng chứng vận hành.
- Producer version đã hết thời gian hỗ trợ, không còn trong đường rollback/canary.
- Tổ hợp không thể cùng tồn tại do ràng buộc triển khai được chứng minh.

Với loại trừ, lưu **lý do, người/phương thức phê duyệt, thời điểm và bằng chứng triển khai**. Đừng đánh dấu `NOT_APPLICABLE` đơn giản để làm ma trận xanh.

### Mobile và client bên ngoài

Một consumer là ứng dụng mobile hoặc đối tác bên ngoài có thể không nâng cấp đồng thời với producer. Đôi khi **không thể biết hoặc điều khiển chính xác mọi consumer version đang hoạt động**.

Trong trường hợp đó, chính sách API versioning, tương thích ngược và deprecation window phải phản ánh thực tế; ma trận CI chỉ bao phủ những versions mà nhóm có bộ test/SDK hoặc đại diện phù hợp, và phải ghi rõ giới hạn đó.

## 13. Mỗi ô cần kịch bản, không chỉ phiên bản

Ngay cả khi ma trận đúng version, một ô PASS có thể yếu nếu consumer tests chỉ kiểm tra “HTTP 200”.

Đối với Checkout, các kịch bản có thể bao gồm:

| Scenario ID | Request/event | Consumer phụ thuộc gì? |
| --- | --- | --- |
| `get_paid_order` | GET /api/orders/ORD-1001 → 200 | Đọc id, trạng thái PAID |
| `get_missing_order` | GET /api/orders/ORD-9999 → 404 | Xử lý không tìm thấy |
| `get_pending_order` | GET order pending → 200 | Không cho checkout hoàn tất trước thời điểm |
| `order_service_error` | Response lỗi theo giao thức | Retry hoặc hiển thị lỗi an toàn |
| `order_paid_event` | Message ORDER_PAID | Consumer xử lý event đúng định dạng/đích |

Một bằng chứng cấp ô nên nói rõ **scenario nào** đã được chạy và assertion nào có ý nghĩa. Một số kịch bản có thể thuộc một contract file nhưng có nhiều consumer test methods; không nên suy `1 contract = 1 test` trong mọi cấu hình.

Ví dụ record phạm vi:

~~~yaml
# Minh họa danh sách scenario do nhóm quản lý.
producer_version: "2.5.0"
consumer_version: "1.8.0"
scenarios:
  get_paid_order: PASS
  get_missing_order: PASS
  get_pending_order: NOT_RUN
overall_status: NOT_RUN
reason: "Scenario get_pending_order thuộc phạm vi bắt buộc chưa chạy"
~~~

**Một ô chỉ nên PASS nếu các scenario bắt buộc của ô đều được kiểm chứng** theo chính sách đã công bố.

## 14. Không đồng nhất “thêm trường” với “không breaking”

Các thay đổi API có thể ảnh hưởng nhiều phía và nhiều phiên bản.

| Thay đổi ở producer | Rủi ro chính | Cần kiểm tra |
| --- | --- | --- |
| Xóa/đổi tên trường JSON | Consumer cũ không đọc được | P_new × C_old |
| Đổi kiểu `amount` từ number sang string | Mapping/deserializer lỗi | P_new × C_old và C_new |
| Thêm trường JSON tùy chọn | Consumer parse chặt có thể từ chối | P_new × C_old |
| Đổi HTTP status 404 thành 200 + body lỗi | Nhánh xử lý consumer sai | Mọi consumer dùng status |
| Đổi URL/path/query/header bắt buộc | Request consumer không match | P_new × C_old |
| Thay semantics của cùng trường | Test chỉ kiểm tra kiểu có thể bỏ sót | Scenario có assertion nghiệp vụ |
| Đổi default pagination/sort | Consumer xử lý danh sách khác | Các consumer phân trang |
| Thay error schema | Retry/UI bị ảnh hưởng | Consumer error scenarios |
| Đổi message destination/topic | Consumer không nhận event | P_new × C_old qua messaging integration |
| Đổi enum/event type | Consumer switch-case có thể fail | Message contract và consumer tests |
| Đổi version serializer/schema | Deserializer không tương thích | Message/wire-level tests |
| Chuyển từ HTTP sang HTTPS/mTLS | Client thiếu trust/client certificate | HTTP/TLS integration tests riêng |

**Một hợp đồng chỉ mô tả kiểu dữ liệu mà bỏ semantics** có thể PASS khi behavior thực tế đã thay đổi. Bởi vậy ma trận cần liên kết contract scenarios và consumer assertions, không chỉ schema snapshots.

## 15. Message contracts cũng cần ma trận

Với message-driven integration:

~~~text
Order Service 2.5.0
    -- ORDER_PAID --> Shipping Service 3.1.0
~~~

Một contract có thể mô tả:

~~~yaml
description: "Đơn thanh toán phát ORDER_PAID"
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

Đây là **ví dụ DSL**, phương thức `markTestOrderAsPaid()` phải tồn tại trong base test producer và tạo ra message thực; nó không được chạy bởi consumer Stub Runner.

Các thành phần ma trận vẫn giống HTTP, nhưng phạm vi bằng chứng cần thêm:

- Producer có thật sự phát event đến logical destination?
- Message body, headers và schema version có đúng contract không?
- Consumer version cũ có đọc event schema mới không?
- Bộ test dùng fake binder hay broker thật? Có kiểm tra topic/queue/routing key thật không?
- Consumer có xử lý event duplicate, mất thứ tự hoặc retry nếu yêu cầu không?

**Message contract PASS không tự chứng minh exactly-once, ordering, retention, retry hoặc DLQ**. Nếu những thuộc tính đó quyết định khả năng cùng tồn tại của hai phiên bản, phải có test tích hợp riêng và ghi vào evidence tương ứng.

## 16. Ma trận có thể cần thêm chiều ngoài P × C

Một ô 2D dễ đọc nhưng môi trường thực có nhiều biến:

~~~text
(P_version, C_version,
 contract_revision, stub_digest,
 protocol/schema, feature_flags,
 environment, config_profile)
~~~

Không nên tạo bảng tám chiều khó sử dụng. Cách thực tế:

- Duy trì **bảng 2D** `producer × consumer` để quyết định nhanh.
- Mỗi ô liên kết tới **record đầy đủ** chứa flags, protocol, schema, config và artifact.
- Nếu hai profile có behavior khác nhau và đều cần hỗ trợ, tạo **biến thể ô/scenario** hoặc ma trận riêng cho profile đó.
- Không trộn kết quả `C_new trên HTTP` thành bằng chứng cho `C_new qua HTTPS với mTLS`.

Ví dụ:

| P | C | Profile | Stub | Status |
| --- | --- | --- | --- | --- |
| 2.5.0 | Checkout 1.8 | default HTTP | 2.5.0:stubs | PASS mẫu |
| 2.5.0 | Checkout 1.8 | strict JSON | 2.5.0:stubs | NOT_RUN |
| 2.5.0 | Checkout 2.0 | HTTPS/mTLS | 2.5.0:stubs + TLS test | NOT_RUN |

Nếu profile `strict JSON` được dùng bởi consumer production, ô default PASS **không thay thế** ô strict JSON.

## 17. Mỗi tổ hợp phải có nguồn bằng chứng đáng tin

Một ô `PASS` nên có ít nhất:

1. **Producer commit + build ID** đã thực thi generated producer tests.
2. **Contract revision** đã sinh tests và stub mappings.
3. **Test report** xác nhận producer tests chạy và không bị skip ngoài dự kiến.
4. **Stub artifact tọa độ cố định**, classifier `stubs` và checksum từ bytes thực tế.
5. **Consumer commit/version** đã chạy.
6. **Stub Runner resolution log** hoặc metadata chứng minh consumer tải đúng artifact.
7. **Consumer test report**, danh sách scenarios và kết quả.
8. **Thời điểm, profile và cấu hình** để biết điều kiện phép thử.
9. **Quyết định hỗ trợ/release** và trạng thái được tính toán từ evidence chứ không tự nhập.

Một câu hỏi tự kiểm tra hữu ích: **nếu một người khác chỉ có record của ô đó, họ có xác định được code, hợp đồng, artifact và lần test đã dùng không?**

Nếu không, ma trận mới chỉ là bảng ghi nhớ; chưa phải bằng chứng phát hành có thể kiểm toán.

## 18. Sử dụng lại producer verification giữa các consumer tests

Không nhất thiết chạy lại **cùng một producer contract test suite** cho từng consumer version nếu tất cả dùng **chính một immutable stub artifact** từ **cùng producer build đã verified**.

Ví dụ:

~~~text
Producer P2.5:
  source commit abc123
  contract revision def456
  verification run producer-7824 = PASS
  stub artifact SHA-256 = H_P25

Consumer C1.8:
  consumer run checkout-8812 dùng H_P25 = PASS

Consumer C2.0:
  consumer run checkout-8813 dùng H_P25 = PASS
~~~

Hai ô `P2.5 × C1.8` và `P2.5 × C2.0` có thể **tham chiếu cùng một producer verification record và stub checksum**, nhưng phải có **consumer run riêng** cho từng phiên bản.

Điều này giảm công việc trùng lặp mà không làm mất truy vết. Tuy nhiên, khi producer hoặc contract revision thay đổi, kết quả verification cũ chỉ được sử dụng lại nếu nguồn/artifact identity vẫn khớp một cách có thể chứng minh.

## 19. Đừng dùng bản stub cũ để tạo màu xanh giả

Một số nguyên nhân khiến ma trận bị đánh dấu sai:

| Tình huống | Vì sao bằng chứng sai hoặc chưa đủ? |
| --- | --- |
| Checkout 1.8 PASS với `P2.4:stubs`, báo PASS cho P2.5 | Chưa dùng stub mới |
| Producer P2.5 test PASS nhưng stub JAR build từ P2.4 | Không cùng contract/build |
| Stub coordinate `2.5.0-SNAPSHOT` nhưng checksum không ghi | Có thể tải bytes khác |
| Consumer tests chạy với WireMock mapping copy tay | Có thể khác artifact sinh từ producer đã verified |
| Test runner báo 0 tests | Không có consumer assertions thực |
| Generated producer tests bị skip | Chưa xác minh implementation |
| Only happy-path GET 200 PASS | Chưa bao phủ lỗi/semantics khác |
| CI chỉ kiểm tra stub server started | Chưa kiểm tra consumer logic |
| Consumer mới chạy với producer mới nhưng chưa test rollback | Thiếu P_old × C_new nếu rollback có thể xảy ra |
| Báo PASS từ historical run trước khi code đổi | Evidence stale so với commit cần release |

Mỗi khi xuất hiện kết quả đáng nghi, hãy so sánh **producer/contract revision**, **stub checksum**, **consumer revision** và **run IDs** trước khi sửa DSL matcher.

## 20. Release gate: quyết định từ các ô bắt buộc

Với một lần nâng producer, release gate có thể được biểu diễn:

~~~mermaid
flowchart TD
    A["Xác định producer target + consumers còn hỗ trợ"] --> B["Tạo required P × C pairs"]
    B --> C["Producer contract verification target"]
    C --> D{"PASS, không skip, đúng contract revision?"}
    D -->|Không| X["BLOCK"]
    D -->|Có| E["Publish immutable stub artifact + checksum"]
    E --> F["Chạy required consumer versions với stub mới"]
    F --> G{"Tất cả required cells PASS?"}
    G -->|Không| X
    G -->|Có| H["Kiểm tra rollback/rolling pairs"]
    H --> I{"Các cặp cùng tồn tại được xác minh?"}
    I -->|Không| X
    I -->|Có| J["Lưu evidence và xét triển khai"]
~~~

**Quy tắc cơ bản:** một producer release không nên được đánh dấu “đã chứng minh tương thích với mọi consumer được hỗ trợ” nếu còn **required cell** là `FAIL`, `NOT_RUN`, `BLOCKED` hoặc `STALE`.

Tất nhiên, một tổ chức có thể có **quy trình chấp nhận rủi ro** cho trường hợp bắt buộc triển khai. Khi đó cần ghi quyết định, người có thẩm quyền, giới hạn ảnh hưởng và kế hoạch khắc phục; **không được giả mạo trạng thái PASS**.

### Thuật toán đánh giá trạng thái (pseudocode)

~~~text
requiredCells = lấy danh sách P × C cần hỗ trợ lúc release

for each cell:
    if thiếu producer verification:
        cell = BLOCKED
    else if stub provenance không trùng producer build:
        cell = STALE
    else if consumer test không chạy:
        cell = NOT_RUN
    else if assertions FAIL:
        cell = FAIL
    else:
        cell = PASS

if có required cell != PASS:
    releaseCompatibility = NOT_VERIFIED
else:
    releaseCompatibility = VERIFIED_WITHIN_DECLARED_SCOPE
~~~

Đoạn này là **mô hình logic**, không phải API chính thức của Spring Cloud Contract. Trong thực tế, thứ tự điều kiện và trạng thái có thể được mở rộng để phân biệt lỗi hạ tầng với lỗi contract.

## 21. CI thiết lập ma trận như thế nào?

Một pipeline điển hình cần hai nguồn thông tin:

1. **Producer target release** và tập stub artifacts đã được producer verify.
2. **Danh sách consumer versions bắt buộc**, lấy từ chính sách hỗ trợ, deployment inventory và kế hoạch rollout/rollback.

Ví dụ một file **input matrix do nhóm tự thiết kế**:

~~~yaml
# Đây KHÔNG phải file cấu hình mặc định của Spring Cloud Contract.
release_target:
  producer: order-service
  version: "2.5.0"
required_consumers:
  - service: checkout-service
    version: "1.8.0"
    reason: "đang chạy production"
  - service: checkout-service
    version: "2.0.0"
    reason: "phiên bản sắp triển khai"
  - service: sales-portal
    version: "4.1.0"
    reason: "đang chạy production"
rollback_pairs:
  - producer: "2.4.0"
    consumer: "checkout-service:2.0.0"
~~~

Một pipeline có thể:

1. Kiểm tra producer build/contract revision và tạo stub artifact `2.5.0:stubs`.
2. Tính/checksum artifact sau đóng gói và verify bản ở repository.
3. Với mỗi consumer version bắt buộc, checkout đúng Git tag/commit, nạp stub `2.5.0` và chạy consumer integration tests.
4. Với rollback pairs, nạp stub của producer phiên bản cũ đã được verified và chạy consumer version mới tương ứng.
5. Đối chiếu reports, logs resolved artifacts và scenario coverage.
6. Tạo compatibility matrix kết quả và lưu link evidence cho từng ô.
7. Chặn publish/rollout hoặc đưa vào quy trình quyết định rủi ro nếu thiếu required cells.

Một consumer có thể cần test với **nhiều phiên bản producer** bằng cách truyền version vào cấu hình thay vì viết lại test class cho từng version.

### Phân tách cấu hình khỏi business code

Một consumer `RestClient` có thể nhận base URL của stub qua cấu hình:

~~~yaml
orders:
  api:
    base-url: "${ORDER_STUB_BASE_URL:http://localhost:8090}"
~~~

Mỗi job ma trận chọn đúng stub version và xuất `ORDER_STUB_BASE_URL` cho ứng dụng consumer. Không hardcode `2.5.0` hoặc port `8090` trong business code chỉ để chạy test.

Nếu consumer dùng Feign/DiscoveryClient thay vì URL tĩnh, cần cấu hình Stub Runner Spring Cloud và service ID mapping đúng; ô ma trận phải ghi rõ cách routing đã được kiểm tra.

## 22. Chọn đúng consumer source version để chạy từng ô

Một sai lầm hay gặp: thay tên job CI thành “checkout 1.8” nhưng vẫn checkout mã `main` của Checkout 2.0. Khi đó không có bằng chứng cho C1.8.

Với từng ô, cần:

~~~text
Producer stub coordinate: order-service:2.5.0:stubs
Consumer source:          checkout-service tag/v1.8.0
Consumer resolved commit: cde789...
Test run:                 checkout-ci-8812
Resolved stub digest:     H_P25
Result:                   PASS/FAIL
~~~

Nếu tag có thể bị di chuyển, lưu **commit SHA** thực sự được checkout. Để tái lập hơn, khóa test dependencies/toolchain phù hợp với source consumer version.

**Không nên sửa mã consumer 1.8.0 để dùng phương thức chỉ có ở 2.0.0**, rồi vẫn gọi đó là test của bản production 1.8.0. Nếu cần tạo test harness ngoài repo consumer cũ, phải nêu rõ harness version và logic thật được thực thi, tránh vô tình thay đổi hành vi cần kiểm tra.

## 23. Kết quả giả lập theo kịch bản và cách ra quyết định

Giả sử nhóm đã thiết kế các ô với trạng thái **minh họa**:

| Tổ hợp | Status minh họa | Cách diễn giải |
| --- | --- | --- |
| P2.4 × Checkout 1.8 | PASS | Baseline cũ trong phạm vi test |
| P2.5 × Checkout 1.8 | FAIL | Producer mới có thể phá consumer cũ |
| P2.4 × Checkout 2.0 | PASS | Consumer mới hỗ trợ rollback về producer cũ |
| P2.5 × Checkout 2.0 | PASS | Trạng thái mục tiêu hoạt động |
| P2.5 × Sales 4.1 | NOT_RUN | Chưa có bằng chứng cho một consumer còn hoạt động |

Nếu producer P2.5 định triển khai ngay khi Checkout 1.8 và Sales 4.1 vẫn ở production, quyết định mặc định là **chưa có bằng chứng đủ cho rollout an toàn**.

Các bước xử lý hợp lý:

1. Xác định lý do FAIL của `P2.5 × Checkout1.8`; ví dụ P2.5 đã bỏ `status`.
2. Dùng chiến lược chuyển tiếp giữ `status` tạm thời hoặc nâng consumer cũ trước.
3. Chạy lại producer tests sau sửa producer/contract và publish **stub mới đúng build**.
4. Chạy lại Checkout 1.8 với stub mới; không giữ nguyên report PASS của bản cũ.
5. Chạy Sales 4.1 với stub P2.5 hoặc xác định có đủ căn cứ loại tổ hợp khỏi danh sách hỗ trợ không.
6. Đánh giá rollback pairs nếu C2.0 đã triển khai.
7. Ghi ma trận và bằng chứng mới trước quyết định release.

**Một ô PASS của Checkout 2.0 không được bù cho một ô FAIL của Checkout 1.8** nếu 1.8 vẫn là consumer được hỗ trợ.

## 24. Kết quả nào được phép tái sử dụng?

Có thể tái sử dụng một số bằng chứng khi **đối tượng được kiểm tra không thay đổi**:

| Bằng chứng | Có thể tái sử dụng khi nào? | Không nên tái sử dụng khi nào? |
| --- | --- | --- |
| Producer verification | Cùng producer build, contract revision và phạm vi tests; stub bytes tương ứng | Producer code/contract thay đổi |
| Stub checksum | Cùng file bytes artifact | JAR được rebuild hoặc ghi đè |
| Consumer test report | Cùng consumer commit/config, stub digest, scenarios và môi trường phù hợp | Consumer hoặc stub đổi |
| Historical matrix baseline | Để đối chiếu/hồi quy | Để thay thế phép thử bản release mới |
| Load/performance hoặc TLS integration tests | Khi giả định phạm vi còn nguyên và policy cho phép | Khi runtime/server/transport thay đổi liên quan |

Những trường hợp “cùng semantic version nhưng khác commit hoặc khác JAR” thường **không đủ** để tái sử dụng bằng chứng mà không có thêm chứng minh.

## 25. Bất đồng bộ và thứ tự triển khai làm ma trận phức tạp hơn

Trong HTTP, một request thường nhận một response. Với event-driven architecture:

- Producer mới có thể phát schemaVersion 2 trong khi consumer cũ chỉ hiểu version 1.
- Topic có thể chứa **message cũ còn tồn đọng** sau khi producer được nâng.
- Consumer mới có thể nhận event phát bởi producer cũ hoặc sự kiện tồn từ trước.
- Một producer rollback có thể phát lại event schema cũ trong khi consumer mới đã deploy.
- Duplicates, ordering, retry và DLQ có thể quyết định tính an toàn của lần chuyển phiên bản.

Vì thế một ma trận message-based có thể cần thêm chiều:

~~~text
Producer event version × Consumer handler version × In-flight schema versions
~~~

Một phép thử chỉ kích hoạt event mới và thấy consumer mới xử lý được **không chứng minh** nó xử lý tốt message version cũ còn trong queue. Nếu đó là yêu cầu rollout, cần thêm scenario và integration tests phù hợp.

**Spring Cloud Contract message stubs** giúp mô phỏng event payload/headers theo hợp đồng, nhưng không tự mô phỏng đầy đủ semantics của broker production.

## 26. Tránh ma trận “xanh” nhưng kém giá trị

Những điểm cần rà soát:

| Vấn đề | Dấu hiệu | Khắc phục |
| --- | --- | --- |
| Tổ hợp sai phiên bản | CI job label P2.5 nhưng Stub Runner ID P2.4 | Kiểm tra resolved artifact |
| Test không chạy | Báo 0 tests hoặc skipped | Fail gate, kiểm tra test runner |
| Stub không có provenance | JAR copy tay | Gắn contract revision/producer build/checksum |
| Test assertions quá yếu | Chỉ kiểm tra server trả 200 | Assert logic consumer và trường quan trọng |
| Thiếu error scenarios | Chỉ thử happy path | Bổ sung 400/404/5xx, timeout theo nhu cầu |
| Nhiều consumer bị bỏ qua | Chỉ chạy Checkout latest | Lấy danh sách từ support/deployment inventory |
| Cùng version nhưng bytes khác | Repository cho overwrite | Immutable artifacts và hash verification |
| Không thử rollback | Chỉ thử P_new × C_new | Chạy P_old × C_new nếu rollback có thể xảy ra |
| Feature flag lệch | CI test flag OFF, prod flag ON | Ghi và thử profile bắt buộc |
| Hạ tầng giả lập khác production | Stub PASS nhưng TLS/broker/routing lỗi | Integration tests chuyên biệt, ghi giới hạn |
| Ma trận stale | Link tới run trước commit mới | Kiểm tra SHA/version/run ID từng ô |
| Dùng dữ liệu production | Fixture chứa token/PII | Thay bằng dữ liệu tổng hợp |

Một ô PASS không phải một khẳng định tuyệt đối; nó là **kết quả có phạm vi và thời điểm**.

## 27. Bài tập thực hành

### Bài tập A — Xác định các ô cần chạy

Producer Order đang chạy `2.4.0`; chuẩn bị nâng `2.5.0`. Checkout `1.8.0` còn production, Checkout `2.0.0` chuẩn bị triển khai và có khả năng rollback producer.

**Yêu cầu:** lập ma trận 2 × 2, ghi lý do cần chạy mỗi ô và liệt kê bằng chứng tối thiểu.

**Gợi ý:** xét cả `P_new × C_old` và `P_old × C_new`, không chỉ `P_new × C_new`.

### Bài tập B — Stub cũ tạo PASS giả

CI ghi “Order 2.5 × Checkout 1.8 PASS”, nhưng log Stub Runner cho thấy `order-service:2.4.0:stubs`.

**Yêu cầu:** sửa trạng thái ô, xác định bằng chứng thiếu và đề xuất chạy lại.

**Gợi ý:** kết quả đó không áp dụng cho P2.5; phải tải stub mới gắn với producer verification P2.5 và chạy lại consumer version 1.8.

### Bài tập C — Thêm trường có phá compatibility không?

Producer 2.5 trả đồng thời `status` và `paymentStatus`. Một consumer cũ dùng deserializer không chấp nhận unknown properties.

**Yêu cầu:** giải thích vì sao vẫn có thể FAIL, và test gì cần có?

**Gợi ý:** kiểm tra `P2.5 × C_old` với chính consumer code/JSON settings cũ.

### Bài tập D — Rollback sau khi consumer nâng

Checkout 2.0 đã triển khai và chỉ đọc `paymentStatus`. Producer Order 2.5 xảy ra lỗi vận hành và phải rollback về 2.4 (chỉ có `status`).

**Yêu cầu:** xác định ô thiếu trong ma trận và phương án nâng consumer an toàn.

**Gợi ý:** `P_old × C_new`; Checkout 2.0 có thể cần đọc được cả trường cũ lẫn mới trong giai đoạn chuyển tiếp.

### Bài tập E — Tạo evidence manifest

Cho:

~~~text
Producer commit: abc123
Contract revision: def456
Producer CI run: 7824 (PASS)
Stub artifact: com.example.orders:order-service:2.5.0:stubs
Consumer: checkout-service 1.8.0 @ cde789
Consumer CI run: 8812 (PASS)
~~~

**Yêu cầu:** thiết kế record cho ô ma trận, liệt kê thêm trường chưa có mà CI phải đo thật.

**Gợi ý:** artifact SHA-256, repository, generated tests executed/skipped, scenario IDs, resolved stub bytes và test report URLs.

### Bài tập F — NOT_RUN khác FAIL thế nào?

Một ô Sales Portal 4.1 × Order 2.5 chưa chạy vì credential remote repository bị hết hạn.

**Yêu cầu:** chọn trạng thái và quyết định release nếu Sales Portal còn thuộc danh sách bắt buộc.

**Gợi ý:** `BLOCKED` hoặc `NOT_RUN` theo quy ước; thiếu bằng chứng, không phải chứng minh incompatibility. Khắc phục repository rồi chạy lại.

### Bài tập G — Tránh bùng nổ ma trận

Có 12 producer versions lịch sử và 25 consumer versions. Tổ chức chỉ hỗ trợ ba producer versions gần nhất và các consumer versions đang hoạt động trong 60 ngày.

**Yêu cầu:** xác định cách lựa chọn required cells theo chính sách, cách lưu lý do loại trừ và rủi ro còn lại.

**Gợi ý:** ưu tiên tổ hợp có thể cùng tồn tại, cặp rolling/rollback, API đang dùng và các consumer chưa thể nâng đồng loạt.

### Bài tập H — Message compatibility

Order 2.5 phát `ORDER_PAID` schemaVersion 2; Shipping 3.0 đọc được cả version 1 và 2, Shipping 2.9 chỉ hiểu version 1. Broker vẫn lưu một số event version 1.

**Yêu cầu:** nêu các ô và kịch bản message bổ sung cần kiểm tra.

**Gợi ý:** producer mới với consumer cũ, consumer mới với event cũ in-flight, schema/headers/destination và thử nghiệm broker phù hợp.

## 28. Checklist ma trận trước khi quyết định phát hành

- [ ] Đã xác định rõ producer service/version và consumer service/version của từng ô.
- [ ] Đã định nghĩa hai hướng: **P_new × C_old** và **P_old × C_new** khi có rollout/rollback.
- [ ] Danh sách consumer đang hoạt động/được hỗ trợ được xác nhận, không chỉ lấy bản latest.
- [ ] Mỗi ô có trạng thái `PASS`, `FAIL`, `NOT_RUN`, `BLOCKED`, `SKIPPED` hoặc loại trừ có lý do.
- [ ] Không đánh dấu `NOT_RUN`, `BLOCKED` hoặc `STALE` thành PASS.
- [ ] Producer Git commit và contract revision của artifact được ghi rõ.
- [ ] Generated producer contract tests thực sự được sinh, biên dịch và chạy PASS.
- [ ] Không có `0 contract tests` hoặc skip ngoài dự kiến.
- [ ] Stub JAR được sinh từ cùng contract/build đã producer-verified.
- [ ] Stub coordinate có đủ group/artifact/version/classifier và được khóa version.
- [ ] Artifact checksum được tính từ JAR cuối và xác minh sau publish khi cần.
- [ ] Consumer Stub Runner thực sự tải đúng artifact/checksum, không dùng bản cũ.
- [ ] Consumer source commit/tag đúng phiên bản mà ô ma trận công bố.
- [ ] Consumer tests có assertions nghiệp vụ và scenario coverage phù hợp.
- [ ] Các tình huống lỗi, boundary và protocol/message schema quan trọng được xem xét.
- [ ] Feature flags, client serialization profile và môi trường test được ghi trong evidence.
- [ ] Các kịch bản canary/rolling deploy/rollback được đưa vào required cells nếu có thể xảy ra.
- [ ] Các ô `UNSUPPORTED` hoặc `NOT_APPLICABLE` có lý do và bằng chứng hỗ trợ.
- [ ] Ma trận được cập nhật khi producer/consumer/contract/stub digest thay đổi.
- [ ] Các cặp chưa đủ bằng chứng bị chặn hoặc được đưa vào quy trình chấp nhận rủi ro có thẩm quyền.
- [ ] Kết quả tương thích được diễn đạt **đúng phạm vi**, không tuyên bố vượt qua những gì contract tests chứng minh.
- [ ] Báo cáo CI lưu đầy đủ link producer reports, consumer reports, artifact và revision để truy vết.

## Kết luận

**Ma trận phiên bản** không chỉ là bảng check “phiên bản nào xanh”. Nó là bộ hồ sơ mô tả **những cặp producer–consumer nào có thể cùng tồn tại**, **đã thử bằng stub nào**, và **bằng chứng nào xác nhận cả producer implementation lẫn consumer behavior**. Với Spring Cloud Contract, một ô đáng tin cần nối **hợp đồng Groovy/YAML**, **generated producer tests**, **stub artifact có version/checksum rõ ràng**, **Stub Runner** và **consumer assertions**. Khi những liên kết đó được giữ nguyên trong CI, nhóm mới có căn cứ phát hiện thay đổi API không tương thích trước rollout thay vì phát hiện sau khi consumer production lỗi.

**Ghi nhớ:** *Không có bằng chứng cho một tổ hợp nghĩa là chưa biết nó tương thích; PASS với stub cũ không chứng minh khả năng tương thích của producer mới.*
