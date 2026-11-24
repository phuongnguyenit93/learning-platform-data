# Bằng chứng cần có trước khi công bố khả năng tương thích

## Mục tiêu bài học

Trong vòng đời hợp đồng giữa **producer** (bên cung cấp API/phát thông điệp) và **consumer** (bên gọi API/nhận thông điệp), tuyên bố **“phiên bản mới tương thích”** có thể ảnh hưởng trực tiếp đến quyết định triển khai của nhiều đội. Một bản build thành công hay một bộ stub chạy được chưa đủ để đưa ra tuyên bố đó.

**Spring Cloud Contract** giúp biến hành vi HTTP hoặc thông điệp được đặc tả bằng **Groovy/YAML DSL** thành các phép kiểm tra có thể tự động hóa: sinh test để kiểm chứng producer, tạo stub, dùng **Stub Runner** để consumer kiểm thử tương tác, và chạy các bước này trong CI. Nhưng kết luận tương thích chỉ đáng tin khi **các phép kiểm tra được liên kết đúng với hợp đồng, mã nguồn, bản build, artifact và tập consumer thực tế**.

Sau bài học, bạn có thể:

- Xác định một tuyên bố tương thích có phạm vi kiểm chứng rõ ràng.
- Phân biệt bằng chứng từ hợp đồng, kiểm thử producer, stub, kiểm thử consumer và kiểm thử tích hợp bổ sung.
- Lập chuỗi truy vết từ phiên bản hợp đồng đến bản build và kết quả CI.
- Đánh giá ma trận phiên bản khi hai dịch vụ không triển khai đồng thời.
- Thiết kế điều kiện phát hành và hồ sơ bằng chứng trước khi công bố một thay đổi API/thông điệp an toàn cho consumer.

## 1. Trước tiên, phải nói rõ “tương thích với ai, ở phiên bản nào?”

Không nên công bố chung chung:

> “Order API phiên bản 2 tương thích ngược.”

Một phát biểu có thể kiểm chứng cần cụ thể hơn:

> “Producer Order API bản 2.4.0, được build từ commit P2, vẫn đáp ứng các hợp đồng HTTP mà consumer Checkout 1.9.0 đang phụ thuộc, trong các kịch bản đã khai báo và được CI xác minh bằng stub cùng bản build.”

Phát biểu thứ hai trả lời được những câu hỏi quan trọng:

| Câu hỏi | Nội dung cần ghi |
| --- | --- |
| **Producer nào?** | Tên dịch vụ, bản build, commit, version hoặc image digest |
| **Consumer nào?** | Tên consumer, phiên bản, nhánh hoặc commit được kiểm thử |
| **Bề mặt tích hợp nào?** | Endpoint, HTTP method, schema, mã lỗi, sự kiện/message |
| **Hợp đồng nào?** | Tệp hoặc tập hợp hợp đồng cùng revision xác định |
| **Bằng chứng từ đâu?** | Test run và artifact có thể truy xuất lại |
| **Phạm vi giới hạn?** | Kịch bản được kiểm tra, phiên bản chưa được kiểm tra, rủi ro còn mở |

Trong hệ thống nhiều dịch vụ, “tương thích” là một **quan hệ giữa các phiên bản trong một phạm vi**, không phải thuộc tính tuyệt đối của một producer. Bản producer mới có thể tương thích với Checkout nhưng chưa chắc tương thích với Reporting nếu hai consumer sử dụng những trường hoặc mã lỗi khác nhau.

### Phân biệt hai chiều tương thích

- **Consumer cũ → Producer mới:** bản producer mới phải tiếp tục xử lý các yêu cầu và trả hành vi mà consumer hiện tại kỳ vọng. Đây thường là yêu cầu quan trọng khi nâng cấp producer trước.
- **Consumer mới → Producer cũ:** bản consumer mới phải tiếp tục chạy được với producer chưa nâng cấp. Chiều này đặc biệt quan trọng khi triển khai consumer trước hoặc rolling deployment.

Việc chứng minh một chiều không tự động chứng minh chiều còn lại. Cần dựa vào **thứ tự phát hành**, khả năng rollback và khoảng thời gian nhiều phiên bản cùng tồn tại để quyết định kiểm tra tổ hợp nào.

## 2. Chuỗi bằng chứng từ cam kết đến phiên bản phát hành

Một quy trình có thể kiểm toán cần xây được chuỗi liên kết sau:

~~~mermaid
flowchart TD
    A["Hợp đồng Groovy/YAML<br/>revision xác định"] --> B["Test sinh bởi Spring Cloud Contract"]
    A --> C["Stub/mapping sinh từ cùng hợp đồng"]
    B --> D["Kiểm thử với producer build P"]
    C --> E["Stub artifact có tọa độ/phiên bản"]
    D --> F{"Producer test PASS?"}
    F -->|Có| G["Cho phép phát hành artifact đã kiểm tra"]
    F -->|Không| X["Dừng: chưa đủ bằng chứng"]
    E --> H["Consumer test với đúng stub version"]
    G --> I["Hồ sơ phát hành"]
    H --> J{"Consumer test PASS?"}
    J -->|Có| I
    J -->|Không| X
    I --> K["Đánh giá phạm vi, ma trận phiên bản và rủi ro"]
    K --> L["Quyết định công bố khả năng tương thích"]
~~~

Đây là **quy trình tham khảo**, không phải một pipeline được Spring Cloud Contract tự triển khai sẵn. Đội dự án phải nối các bước này bằng cấu hình build, kho artifact, CI và chính sách phát hành phù hợp.

Một hồ sơ bằng chứng nên có ít nhất các nhóm sau:

| Nhóm bằng chứng | Nội dung cần xác minh | Điều bằng chứng này **chưa** khẳng định |
| --- | --- | --- |
| **Hợp đồng đã được thống nhất** | Request/response hoặc message nào là cam kết, ai phụ thuộc, revision nào được kiểm tra | Mọi hành vi chưa được mô tả đều tương thích |
| **Kiểm thử phía producer** | Test sinh từ hợp đồng chạy đạt với bản producer dự kiến phát hành | Mọi cấu hình mạng, bảo mật và dữ liệu production đều hoạt động |
| **Stub có nguồn gốc rõ** | Stub được sinh/đóng gói từ đúng hợp đồng và build đã kiểm tra, có tọa độ phiên bản | Consumer hiện tại xử lý thành công stub đó |
| **Kiểm thử consumer** | Consumer tương ứng chạy đạt với stub đúng phiên bản qua Stub Runner hoặc cơ chế tương đương | Producer thật có mọi tính chất mà stub không mô phỏng |
| **Ma trận triển khai** | Các cặp phiên bản cần cùng tồn tại được kiểm tra hoặc có phương án kiểm soát | Mọi phiên bản lịch sử đều an toàn |
| **Điều kiện vận hành liên quan** | Rủi ro còn lại về auth, gateway, broker, thứ tự sự kiện, timeout... có bằng chứng riêng nếu có ảnh hưởng | Chỉ test hợp đồng có thể thay thế kiểm thử hệ thống/hiệu năng |

Điều kiện quan trọng: **tất cả bằng chứng phải cùng chỉ về một phiên bản có thể xác định**, hoặc có giải thích rõ ràng cho mối quan hệ giữa các phiên bản. Báo cáo producer PASS của commit hôm qua không mặc nhiên áp dụng cho image mới build từ commit hôm nay.

## 3. Bằng chứng số 1: Hợp đồng mô tả đúng nhu cầu consumer

Spring Cloud Contract kiểm chứng những gì được **khai báo**. Vì vậy, trước cả bước chạy test, phải có bằng chứng rằng tập hợp hợp đồng thực sự phản ánh nhu cầu tích hợp.

Một bản rà soát hợp đồng cần trả lời:

1. Consumer nào sử dụng endpoint hoặc thông điệp này, vào thời điểm nào?
2. Method, path, tham số, header, body và HTTP status nào là bắt buộc?
3. Trường dữ liệu nào consumer đọc và dùng để ra quyết định?
4. Trường hợp lỗi hoặc trạng thái đặc biệt nào consumer có xử lý?
5. Những giá trị nào phải cố định và những giá trị nào chỉ cần thỏa mãn kiểu/định dạng?
6. Có điều kiện tương thích cụ thể nào như chấp nhận trường mở rộng hoặc giữ nguyên enum hay không?

Giả sử consumer Checkout đọc trạng thái đơn hàng. Đây là hợp đồng **YAML DSL minh họa**, không phải API có sẵn mặc định của Spring Cloud Contract:

~~~yaml
description: "Consumer có thể đọc trạng thái đơn hàng đã thanh toán"
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

Trường hợp thiếu đơn hàng cũng cần hợp đồng riêng nếu Checkout phân nhánh theo lỗi:

~~~yaml
description: "Đơn hàng không tồn tại trả về mã lỗi ổn định"
name: get_missing_order
request:
  method: GET
  url: /api/orders/ORD-9999
  headers:
    Accept: application/json
response:
  status: 404
  headers:
    Content-Type: application/json
  body:
    code: ORDER_NOT_FOUND
~~~

Điểm cần kiểm tra trong review: Checkout dùng **status = PAID** để hiển thị thanh toán, và dùng **404 + code = ORDER_NOT_FOUND** để xử lý đơn không tồn tại. Hợp đồng không cần ràng buộc producer phải dùng lớp Java, database hay cache nào.

Nếu consumer còn phân nhánh với CANCELLED, REFUNDED hoặc cần một trường khác, hai hợp đồng trên **chưa đủ** để công bố khả năng tương thích cho toàn bộ hành vi đó. Số lượng test PASS không bù được những kịch bản bị bỏ sót.

**Bằng chứng cần lưu:** revision của hợp đồng, nội dung thay đổi được review, danh sách consumer/tình huống áp dụng và các giả định về schema hoặc cách xử lý giá trị chưa biết.

## 4. Bằng chứng số 2: Producer thật đáp ứng hợp đồng

Từ hợp đồng Groovy/YAML, **Spring Cloud Contract Verifier** có thể sinh test phía producer. Trong pipeline producer, cần chạy các test này với mã nguồn và cấu hình test tương ứng của **bản sắp phát hành**.

Ví dụ, để chạy test GET /api/orders/ORD-1001, producer phải có trạng thái dữ liệu phù hợp: trong fixture test, ORD-1001 có status PAID. Hợp đồng cho ORD-9999 cần đảm bảo bản ghi đó không tồn tại trong bối cảnh kiểm thử. Các dữ liệu này có thể do lớp nền test, mock tại biên thích hợp, seed database hoặc fixture quản lý; hợp đồng không quyết định cách triển khai fixture.

Kiểm thử đạt là bằng chứng rằng **producer trong môi trường test đã tạo phản hồi khớp hợp đồng**. Để phát biểu có thể đối chiếu, báo cáo nên gắn với:

- Commit hoặc image digest của producer.
- Revision tập hợp hợp đồng được dùng để sinh test.
- Phiên bản cấu hình công cụ và tập test đã chạy, nếu ảnh hưởng khả năng tái lập.
- Kết quả PASS/FAIL; tên test bị bỏ qua và lý do bỏ qua nếu có.
- Thời điểm chạy và liên kết job/artifact test report.

Chẳng hạn kết luận hợp lệ là “test get_paid_order PASS với producer commit abc123 trong build 527”. Kết luận “producer tương thích với tất cả consumer” cần thêm bằng chứng từ các consumer cụ thể.

**Không được coi các trường hợp sau là PASS đầy đủ:** chỉ biên dịch thành công, test sinh nhưng không được chạy, test bị bỏ qua, fixture trả lời trực tiếp bằng stub trong khi logic HTTP cần xác minh chưa được gọi, hoặc báo cáo PASS của commit khác.

## 5. Bằng chứng số 3: Stub xuất phát từ đúng hợp đồng và đúng build

Spring Cloud Contract có thể tạo các mapping/stub từ hợp đồng; artifact stub có thể được đóng gói và phát hành trong kho artifact để các consumer dùng qua **Stub Runner**.

Với một dự án Maven/Gradle, tọa độ sau là **minh họa** cho một artifact stub:

~~~text
groupId:    com.example
artifactId: order-service
version:    2.4.0
classifier: stubs
~~~

Consumer phải biết nó đã kiểm thử **bản stub nào**, không chỉ biết test đã khởi chạy một stub server. Để giữ chuỗi chứng cứ, pipeline nên chứng minh:

1. Stub được tạo từ revision hợp đồng đã xác minh.
2. Build tạo stub gắn với phiên bản producer cụ thể.
3. Artifact sau khi kiểm thử có định danh ổn định (tọa độ, version và tốt nhất checksum/digest).
4. Consumer test lấy chính artifact này, tránh tự động trôi sang một bản mới không rõ trong thời gian kiểm thử.

Một số setup dùng phiên bản động như latest hoặc dấu cộng (+) để khám phá stub khi phát triển. Với bằng chứng trước phát hành, nên **khóa phiên bản được xác minh** để việc chạy lại cùng test có thể tái lập. Cũng cần phân biệt stub phát hành **thành công** với stub **đã được consumer kiểm thử**: đây là hai mốc khác nhau.

Nếu producer đổi hợp đồng nhưng không tái tạo/phát hành stub, consumer có thể tiếp tục PASS với stub cũ. Trạng thái đó **không chứng minh** producer mới tương thích.

## 6. Bằng chứng số 4: Consumer hiện tại chạy đạt với stub được chốt

Stub Runner giúp consumer khởi chạy hoặc truy cập stub đã phát hành để kiểm thử các lời gọi HTTP mà không cần dựng producer thật trong cùng bài test.

Ví dụ cấu hình **minh họa** cho test dùng một version cụ thể (tùy phiên bản dependency và cấu hình repository của dự án):

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:order-service:2.4.0:stubs:8080",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE
)
class CheckoutContractIntegrationTest {
    // Test gửi request đến stub server và xác minh
    // logic consumer xử lý status PAID hoặc lỗi ORDER_NOT_FOUND.
}
~~~

Để ví dụ hoạt động trong dự án thật, cần cấu hình đường dẫn repository và dependency phù hợp, đồng thời đặt URL client HTTP của consumer tới stub server do test quản lý. Đoạn Java ở trên **không phải một bài test chạy đầy đủ**; nó minh họa nguyên tắc chốt version artifact.

Test consumer có giá trị khi nó thực sự gọi client/adapter của ứng dụng và xác minh **hành vi mà consumer quan tâm**. Ví dụ:

| Kịch bản | Bằng chứng từ consumer test |
| --- | --- |
| Nhận 200 với status PAID | Checkout nhận diện đơn đã thanh toán và không cho thanh toán lại |
| Nhận 404 với code ORDER_NOT_FOUND | Checkout hiển thị hoặc xử lý đúng trường hợp thiếu đơn |
| Nhận trường tùy chọn bổ sung nếu contract cho phép | Parser của consumer không lỗi vì một trường lạ |
| Producer công bố giá trị enum mới | Consumer có nhánh xử lý an toàn hoặc phiên bản yêu cầu cập nhật đã được kiểm tra |

Nếu test chỉ kiểm tra “HTTP 200” nhưng không xác minh logic Checkout dùng status như thế nào, kết quả PASS chưa chứng minh chức năng consumer tương thích.

Ngược lại, consumer chạy đạt với stub cũng **không chứng minh** kết nối production tới producer thật sẽ thành công qua TLS, gateway, xác thực, giới hạn truy cập, cân bằng tải hay dữ liệu thực. Cần kiểm thử thêm những lớp liên quan khi rủi ro triển khai đòi hỏi.

## 7. Bằng chứng số 5: Ma trận phiên bản phù hợp thứ tự triển khai

Trong kiến trúc microservices, producer và consumer hiếm khi được thay thế cùng một lúc. Vì vậy phải kiểm tra **các cặp phiên bản có thể cùng hoạt động**, bao gồm cả khoảng chuyển tiếp và rollback.

Giả sử:

- P1 là producer đang chạy; P2 là producer mới.
- C1 là consumer đang chạy; C2 là consumer mới.
- P2 bổ sung trường paymentState nhưng **giữ** status để phục vụ C1.
- C2 đọc paymentState, đồng thời có thể fallback sang status nếu cần làm việc với P1.

Ma trận kiểm tra minh họa:

| Cặp triển khai | Vì sao cần kiểm tra | Kết quả để được đánh dấu “hỗ trợ” |
| --- | --- | --- |
| C1 ↔ P1 | Trạng thái nền trước nâng cấp | Có test nền đã xác minh |
| **C1 ↔ P2** | Producer nâng cấp trước | C1 vẫn chạy được với hành vi P2 |
| **C2 ↔ P1** | Consumer nâng cấp trước hoặc rollback producer | C2 xử lý được hợp đồng P1 |
| C2 ↔ P2 | Đích sau khi cả hai nâng cấp | C2 xử lý đúng hành vi P2 |

Không được đánh dấu một ô PASS chỉ vì các ô khác đã PASS. Nếu kế hoạch triển khai không bao giờ cho phép C2 chạy với P1 và cơ chế rollback cũng loại trừ cặp này, có thể ghi ô đó là **không hỗ trợ**, kèm điều kiện triển khai. Đây là một quyết định quản lý phiên bản cần được ghi công khai.

Đối với thay đổi gây phá vỡ hợp đồng, một phương án chuyển tiếp thường là:

1. Producer bổ sung hành vi mới và giữ hành vi cũ trong giai đoạn quá độ.
2. Producer test và phát hành stub cho hành vi mà các consumer cũ vẫn sử dụng.
3. Consumer mới được kiểm thử với các phiên bản producer mà nó có thể gặp.
4. Sau khi xác nhận không còn consumer phụ thuộc hành vi cũ, mới xem xét gỡ bỏ theo chính sách version/deprecation.

Việc bổ sung một trường không tự động luôn tương thích: một consumer dùng deserializer nghiêm ngặt có thể từ chối trường lạ. Tương tự, một giá trị enum mới có thể làm consumer lỗi dù kiểu JSON vẫn là string. Bằng chứng test phải phản ánh những khác biệt đó.

## 8. Với thông điệp bất đồng bộ, cần những bằng chứng nào?

Spring Cloud Contract cũng hỗ trợ các hợp đồng **message-based**. Lúc này, ranh giới tích hợp nằm ở thông điệp được phát/nhận, không phải mã trạng thái HTTP.

Ví dụ payload của một sự kiện nghiệp vụ:

~~~json
{
  "eventType": "ORDER_PAID",
  "orderId": "ORD-1001",
  "occurredAt": "2026-11-24T04:00:00Z"
}
~~~

Đây là dữ liệu minh họa để thảo luận về bằng chứng, không phải cú pháp DSL của một contract message hoàn chỉnh. Tập hợp hợp đồng thực tế cần mô tả kịch bản kích hoạt, loại message, header/destination nếu chúng là giao diện cam kết, payload và quy tắc dữ liệu mà consumer sử dụng.

Đối với sự kiện ORDER_PAID, nên đối chiếu:

- **Producer:** test từ hợp đồng xác minh thông điệp do producer phát có eventType, orderId và định dạng thời gian phù hợp.
- **Stub/message test:** consumer nhận mẫu thông điệp theo hợp đồng và kiểm tra logic cập nhật trạng thái hoặc tính idempotent cần thiết.
- **Tương thích schema:** tên trường, kiểu, giá trị enum, khả năng nhận trường mới hoặc trường thiếu và chính sách phiên bản sự kiện được kiểm tra.
- **Tích hợp vận hành:** nếu consumer dựa vào thứ tự, retry, giao hàng trùng, dead-letter queue hay bảo đảm delivery, cần kiểm chứng các tính chất này bằng kiểm thử broker/hạ tầng hoặc bằng chứng vận hành phù hợp.

**Chỉ một payload khớp contract không chứng minh broker luôn giao đúng thứ tự hoặc đúng một lần.** Những cam kết vận hành phải được đánh giá ở lớp có khả năng kiểm chứng chúng.

## 9. Dùng CI làm cổng kiểm soát bằng chứng

Một pipeline CI tham khảo có thể được tổ chức như sau:

~~~mermaid
sequenceDiagram
    participant R as Hợp đồng/Repository
    participant P as Producer CI
    participant A as Kho artifact
    participant C as Consumer CI
    participant G as Release gate
    R->>P: Chốt revision hợp đồng
    P->>P: Sinh và chạy producer tests
    alt Producer test thất bại
        P-->>G: BLOCK, báo sai khác
    else Producer test đạt
        P->>A: Phát hành stub version cố định
        A->>C: Consumer test dùng stub đó
        C->>C: Chạy các scenario tích hợp
        C-->>G: Báo cáo PASS/FAIL + version
        G->>G: Đối chiếu matrix và rủi ro còn mở
    end
~~~

Trong công ty, các pipeline có thể nằm ở nhiều repository; việc trigger consumer CI từ artifact mới, chờ kết quả và tập hợp bằng chứng là trách nhiệm của quy trình CI/CD.

Ví dụ **mã giả pipeline**, không phải cú pháp Jenkins/GitHub Actions có thể chạy nguyên xi:

~~~yaml
producer_pipeline:
  contract_revision: "contracts@c12abc"
  source_revision: "producer@p34def"
  steps:
    - generate_contract_tests
    - run_producer_contract_tests
    - publish_versioned_stubs_if_tests_pass
  outputs:
    - producer_test_report
    - stub_artifact_coordinates
    - stub_checksum

consumer_pipeline:
  source_revision: "checkout@a56bcd"
  stub_version: "com.example:order-service:2.4.0:stubs"
  steps:
    - fetch_exact_stub_version
    - run_stub_runner_integration_tests
  outputs:
    - consumer_test_report

release_gate:
  require:
    - producer_contract_tests_pass
    - stub_matches_verified_build
    - required_consumers_pass_with_exact_stub
    - required_version_pairs_approved
    - open_breaking_changes_resolved_or_explicitly_accepted
~~~

Điều kiện phát hành phải **fail closed** cho những yêu cầu bắt buộc: thiếu báo cáo, consumer test FAIL, artifact không tồn tại hoặc version sai không nên được tự động tính là PASS. Nếu consumer nào được phép ngoại lệ, ngoại lệ cần ghi rõ người quyết định, lý do, phạm vi, thời hạn và biện pháp giảm rủi ro.

### Nên cố định điều gì trong CI?

| Thành phần | Cách gắn bằng chứng |
| --- | --- |
| Producer source | Commit SHA và build ID/image digest |
| Hợp đồng | Commit/revision hoặc checksum của tập contract |
| Generated tests | Log build và danh sách test được thực thi |
| Stub | Artifact coordinates, version và checksum |
| Consumer source | Commit và version consumer |
| Consumer test run | Job URL/ID, kết quả, version stub đã sử dụng |
| Quyết định release | Danh sách cặp phiên bản hỗ trợ, phạm vi và ngoại lệ |

Không nhất thiết phải đưa tất cả thông tin vào một tệp vật lý. Có thể lưu trong metadata của CI và liên kết qua một release record, miễn người kiểm tra **truy xuất lại được đúng dữ liệu tại thời điểm quyết định**.

## 10. Ví dụ một hồ sơ bằng chứng trước phát hành

Giả sử đội Order API chuẩn bị triển khai 2.4.0, đội Checkout đang chạy 1.9.0. Release record có thể được lưu dưới dạng JSON như sau:

~~~json
{
  "producer": {
    "service": "order-service",
    "version": "2.4.0",
    "commit": "p34def",
    "buildId": "527"
  },
  "contracts": {
    "revision": "c12abc",
    "coveredScenarios": [
      "get_paid_order",
      "get_missing_order"
    ]
  },
  "producerVerification": {
    "result": "PASS",
    "ciRun": "producer-ci/527"
  },
  "stub": {
    "coordinates": "com.example:order-service:2.4.0:stubs",
    "checksum": "artifact-sha256-recorded-by-ci"
  },
  "consumerVerification": [
    {
      "service": "checkout",
      "version": "1.9.0",
      "result": "PASS",
      "ciRun": "checkout-ci/814",
      "stubVersion": "2.4.0"
    }
  ],
  "compatibilityClaim": {
    "supportedPair": "checkout 1.9.0 -> order-service 2.4.0",
    "scope": "GET order: paid and not-found scenarios",
    "unverified": [
      "Checkout flows not included in these contracts",
      "Production gateway and network conditions"
    ]
  }
}
~~~

**Lưu ý:** đây là một **mẫu hồ sơ do đội tự thiết kế**, không phải file mà Spring Cloud Contract mặc định sinh ra. Các commit ID, job ID và checksum ở đây là giả định. Trong hệ thống thực tế, checksum phải là giá trị hash xác thực của artifact, không dùng chuỗi mô tả như ví dụ.

Hồ sơ này đủ rõ để nói về **hai kịch bản GET được liệt kê** với cặp phiên bản Checkout 1.9.0 / Order API 2.4.0. Nó chưa đủ để tuyên bố rằng toàn bộ API, mọi consumer hoặc mọi đường đi nghiệp vụ đều tương thích.

## 11. Những “bằng chứng” dễ gây hiểu nhầm

| Dấu hiệu tưởng đã đủ | Vì sao còn thiếu | Cách khắc phục |
| --- | --- | --- |
| Producer build SUCCESS | Có thể chưa chạy test hợp đồng | Ghi rõ báo cáo test đã thực thi và PASS |
| Test contract PASS nhưng không rõ commit | Không biết test cho bản sắp phát hành hay bản khác | Gắn test run với commit/build bất biến |
| Consumer test PASS với latest stub | Khi kiểm lại có thể resolve ra artifact khác | Chốt artifact/version/checksum |
| Stub mới đã publish | Chưa có bằng chứng consumer xử lý được | Chạy test consumer thực với stub tương ứng |
| Test producer và consumer đều PASS ở hai revision khác nhau | Có thể cả hai đang kiểm các hợp đồng không đồng nhất | Đối chiếu revision, nguồn stub và build |
| Một consumer PASS | Consumer khác có thể dùng trường hoặc error code khác | Liệt kê từng consumer được hỗ trợ |
| Test với stub PASS | Stub không mô phỏng hết hạ tầng và dữ liệu thật | Bổ sung integration/e2e/operational tests khi cần |
| Đổi JSON nhưng schema vẫn hợp lệ | Consumer có thể phụ thuộc tên trường, enum hoặc semantics | Kiểm tra contract theo hành vi nghiệp vụ |
| Test không có assertion quan trọng | Bài test chạy nhưng không phát hiện lỗi mà consumer thực sự gặp | Xác minh cách consumer diễn giải phản hồi |

Một lỗi đặc biệt nguy hiểm là **stub drift**: producer thực tế đã đổi hành vi, nhưng consumer CI vẫn dùng artifact stub cũ và tiếp tục PASS. Kiểm soát provenance và version giữa hợp đồng, producer và stub giúp giảm rủi ro này.

## 12. Quyết định công bố: PASS, giới hạn hay BLOCK?

Phạm vi khuyến nghị:

| Tình huống | Quyết định nên đưa ra |
| --- | --- |
| Contract đã được rà soát; producer test PASS; stub đúng build; consumer cần thiết PASS; cặp phiên bản áp dụng đã kiểm tra | Có thể công bố **tương thích trong phạm vi đã xác minh** |
| Producer test PASS nhưng chưa có consumer test với stub mới | **Chưa đủ bằng chứng** cho consumer đó; chờ kết quả hoặc có quyết định ngoại lệ rõ ràng |
| Consumer test PASS nhưng producer contract test FAIL | **BLOCK** bản producer vì chưa đáp ứng cam kết |
| Hợp đồng được sửa sau khi các test chạy | Test cũ hết hiệu lực với revision mới; **chạy lại** các bước bị ảnh hưởng |
| Producer thêm enum mới và consumer không xử lý được | **Không tương thích** với consumer đó; cần sửa consumer, điều chỉnh rollout hoặc version giao diện |
| Những test chức năng đều PASS nhưng thay đổi gateway/auth chưa được kiểm tra | Chỉ công bố trong phạm vi contract; bổ sung bằng chứng tích hợp trước rollout nếu thay đổi này ảnh hưởng đường đi thật |

“Có thể công bố” vẫn không đồng nghĩa với bảo đảm tuyệt đối không có lỗi. Thông tin công bố nên chỉ ra **phiên bản, kịch bản, consumer, kết quả test và giới hạn đã biết**.

### Khi cần release gấp nhưng còn thiếu bằng chứng

Nếu quy trình cho phép chấp nhận rủi ro, ghi rõ:

1. Bằng chứng còn thiếu và nguyên nhân.
2. Cặp producer–consumer chịu ảnh hưởng.
3. Người chấp thuận và thời hạn bổ sung kiểm chứng.
4. Cách giám sát sau triển khai, tiêu chí dừng rollout và phương án rollback.

Không đổi một trạng thái FAIL/UNKNOWN thành PASS chỉ vì thời hạn phát hành. Quyết định ngoại lệ phải **phân biệt rõ với xác minh tương thích đầy đủ**.

## 13. Bài tập tình huống

**Tình huống A — Bản build và stub không cùng nguồn.**

Producer Order API 2.4.0 được build từ commit P2 và test contract thành công. Consumer Checkout chạy thành công với stub 2.3.0. Một thành viên đề xuất công bố “Checkout tương thích Order API 2.4.0”.

- Bằng chứng nào đã có?
- Bằng chứng nào còn thiếu?
- Cần thay đổi gì trong CI để kết luận có thể tái lập?

**Gợi ý:** Producer đã chứng minh hành vi của build được kiểm tra theo các contract của nó, nhưng consumer chưa được chứng minh với **stub 2.4.0** tương ứng. Cần phát hành/định danh chính xác stub từ build đã xác minh, chạy lại consumer với stub đó và đối chiếu revision hợp đồng.

**Tình huống B — Thay đổi có nguy cơ phá vỡ.**

P2 bỏ trường status và chỉ trả paymentState. Producer test mới PASS, consumer test với stub P2 FAIL vì Checkout 1.9.0 vẫn đọc status.

- Có thể gọi P2 “tương thích ngược” với Checkout 1.9.0 không?
- Đề xuất ít nhất một phương án triển khai tránh gián đoạn.

**Gợi ý:** Không thể công bố tương thích cho cặp đang lỗi. Có thể giữ status song song trong thời gian chuyển tiếp, hoặc nâng Checkout trước với khả năng đọc cả hai trường rồi mới loại bỏ trường cũ theo quy trình đã thỏa thuận.

**Tình huống C — Event contract PASS nhưng consumer vẫn mất dữ liệu.**

Payload ORDER_PAID hợp lệ, nhưng hệ thống broker giao trùng sự kiện khiến consumer cộng tiền hai lần.

- Contract test đã chứng minh được điều gì?
- Cần bổ sung kiểm chứng hoặc cam kết nào?

**Gợi ý:** Contract test chứng minh hình dạng/nội dung message của kịch bản đã khai báo; nó chưa kiểm chứng điều kiện giao trùng. Consumer cần chiến lược idempotency và bài test phù hợp với bảo đảm delivery của hệ thống thực.

## 14. Checklist trước khi tuyên bố tương thích

- [ ] Tuyên bố nêu rõ cặp phiên bản producer–consumer và phạm vi hành vi được kiểm tra.
- [ ] Tập hợp contract Groovy/YAML phản ánh những hành vi consumer thực sự phụ thuộc, gồm cả nhánh lỗi quan trọng.
- [ ] Revision hợp đồng có thể truy vết và không bị thay đổi sau test mà chưa chạy lại.
- [ ] Generated tests phía producer đã **thực sự chạy PASS** với build/commit sắp phát hành.
- [ ] Stub được sinh và phát hành từ đúng hợp đồng/build đã xác minh, có version cố định.
- [ ] Consumer tests dùng đúng stub version và xác minh logic ứng dụng, không chỉ kiểm tra khả năng khởi động.
- [ ] Các cặp phiên bản cần hỗ trợ khi rollout và rollback đã được xác định, kiểm chứng hoặc loại trừ có chủ đích.
- [ ] Các thay đổi schema, enum, HTTP status, header và semantics được đánh giá nguy cơ phá vỡ.
- [ ] Rủi ro auth/gateway/broker/timeout/production còn lại đã được xử lý bằng bằng chứng thích hợp khi cần.
- [ ] Báo cáo CI, nguồn artifact, phạm vi, giới hạn và ngoại lệ được liên kết trong release record.
- [ ] Nếu thiếu bằng chứng bắt buộc, release gate báo BLOCK/UNKNOWN hoặc ghi nhận ngoại lệ minh bạch.

**Điểm cốt lõi:** Trong Spring Cloud Contract, test producer, stub và test consumer tạo thành **chuỗi bằng chứng**, chứ không phải ba dấu tích rời rạc. Chỉ công bố khả năng tương thích khi có thể truy ngược tuyên bố đó đến **hợp đồng cụ thể, build cụ thể, stub cụ thể, consumer cụ thể và kết quả kiểm thử cụ thể**. Phạm vi công bố phải bằng hoặc hẹp hơn phạm vi thực sự đã được xác minh.
