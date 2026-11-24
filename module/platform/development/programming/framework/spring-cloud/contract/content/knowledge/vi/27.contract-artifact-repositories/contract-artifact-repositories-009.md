# Truy vết stub về hợp đồng, commit và lần xác minh producer

## Mục tiêu bài học

Với **Spring Cloud Contract**, một tệp hợp đồng **Groovy DSL** hoặc **YAML DSL** có thể được dùng để **sinh kiểm thử phía producer** và **tạo stub** cho consumer chạy qua **Stub Runner**. Trong chương **Kho hợp đồng và artifact**, vấn đề không chỉ là lưu được `-stubs.jar` ở đâu, mà còn là trả lời câu hỏi: **“Stub đang được consumer sử dụng được tạo từ hợp đồng nào, commit nào, và producer đã thực sự vượt qua lần kiểm chứng nào?”**

Một HTTP stub trả đúng JSON chưa chứng minh producer hiện tại còn đáp ứng hợp đồng. Ngược lại, producer test xanh ở một commit không chứng minh stub JAR trong repository được tạo từ **chính** commit và hợp đồng đã kiểm thử. Nếu không có đường truy vết, một consumer có thể PASS với bản stub cũ trong khi phiên bản producer chuẩn bị phát hành đã thay đổi API.

Sau bài học, bạn có thể:

- Nhận diện các mắt xích của **provenance** (nguồn gốc) từ contract source đến stub artifact và consumer test.
- Phân biệt **producer Git commit**, **contract revision**, **CI build/run**, **test execution**, **Maven artifact coordinate** và **artifact checksum**.
- Hiểu vì sao `BUILD SUCCESS`, tệp `-stubs.jar` và việc Stub Runner khởi động **chưa đủ** để công bố tương thích.
- Thiết kế bản ghi bằng chứng (evidence manifest) liên kết artifact với đầu vào, quá trình kiểm tra và bản đã phát hành.
- Phân biệt hợp đồng nằm **cùng repository** với producer và hợp đồng nằm ở **repository/artifact riêng**.
- Dùng tọa độ stub có version cố định, checksum và log consumer để tránh nhầm bản.
- Xây release gate trong CI, chẩn đoán provenance đứt gãy và đánh giá giới hạn của kết quả kiểm thử.

## 1. Tình huống: consumer PASS nhưng producer mới vẫn có breaking change

Giả sử:

- **Order Service** là producer, có API `GET /api/orders/{id}`.
- **Checkout Service** là consumer, đọc trường `status` trong response.
- Producer phiên bản `2.4.0` đã phát hành stub:
  `com.example.orders:order-service:2.4.0:stubs`.
- Một nhánh producer mới chuẩn bị phát hành `2.5.0` và đổi tên `status` thành `paymentStatus`.

Consumer CI đang cấu hình:

~~~text
Stub Runner artifact:
com.example.orders:order-service:2.4.0:stubs

Checkout client:
GET /api/orders/ORD-1001

Response mẫu:
{"id":"ORD-1001","status":"PAID"}
~~~

Checkout tests có thể PASS vì **stub 2.4.0** còn trường `status`, dù producer `2.5.0` sẽ không trả trường đó nữa.

Câu hỏi đúng trước khi phát hành `2.5.0` không phải “Checkout đã từng PASS hay chưa?” mà là:

> **Checkout ở phiên bản vẫn đang được hỗ trợ có PASS với stub mới được sinh từ hợp đồng đã được xác minh trên producer 2.5.0 hay không?**

Để trả lời đáng tin, cần biết **stub nào**, **hợp đồng nào**, **producer build nào**, **lần kiểm thử nào**, **consumer nào**.

## 2. Chuỗi truy vết đầu-cuối

Một chuỗi bằng chứng có thể thiết kế như sau:

~~~mermaid
flowchart TD
    A["Hợp đồng nguồn<br/>path + contract revision"] --> B["Build producer<br/>commit + môi trường build"]
    B --> C["Generated producer tests<br/>được sinh và thực thi"]
    A --> D["Stub mappings<br/>được chuyển từ cùng contract"]
    C --> E{"Producer contract tests PASS?"}
    E -->|Không| X["Chặn phát hành"]
    E -->|Có| F["Đóng gói stub JAR"]
    D --> F
    F --> G["Artifact coordinate + SHA-256"]
    G --> H["Remote artifact repository"]
    H --> I["Consumer CI dùng Stub Runner<br/>tải đúng tọa độ/checksum"]
    I --> J["Consumer tests + báo cáo"]
    J --> K["Đánh giá tương thích có phạm vi"]
~~~

**Điểm mấu chốt:** các mũi tên thể hiện những **quan hệ cần chứng minh**, không có nghĩa Spring Cloud Contract tự động phát hành mọi metadata truy vết. Maven, Git, CI server và repository cần được cấu hình để ghi lại bằng chứng.

Có thể coi provenance gồm ba lớp:

1. **Nguồn:** nội dung hợp đồng, vị trí và revision được chốt.
2. **Xác minh:** producer source revision, build environment, generated tests và kết quả thực thi.
3. **Phát hành/sử dụng:** artifact bytes được publish, tọa độ repository, phiên bản consumer thực sự tải và kiểm thử.

Thiếu một lớp, rất khó chứng minh lời khẳng định “consumer đang được bảo vệ bởi hợp đồng producer đã kiểm chứng”.

## 3. Các định danh không được nhầm lẫn

| Định danh | Ví dụ | Câu hỏi mà nó trả lời |
| --- | --- | --- |
| **Contract path** | `contracts/orders/get_paid_order.yml` | Scenario nào? |
| **Contract repository commit** | `def456...` | Bản nội dung hợp đồng nào? |
| **Producer Git commit** | `abc123...` | Mã producer nào đã chạy tests? |
| **CI run / attempt ID** | `ci-run-7824/attempt-1` | Lần build/test nào? |
| **Producer test report** | `surefire-reports/...` | Test nào đã chạy và kết quả gì? |
| **Maven groupId** | `com.example.orders` | Namespace artifact nào? |
| **Maven artifactId** | `order-service` | Module được publish là gì? |
| **Version** | `2.5.0` | Bản phát hành nào? |
| **Classifier** | `stubs` | Có phải stub JAR thay vì application JAR? |
| **Artifact checksum** | `sha256:<digest-thực-tế>` | Chính xác bytes artifact nào? |
| **Consumer commit** | `checkout@cde789...` | Consumer code nào được test? |
| **Consumer stub report** | `checkout-contract-test.xml` | Test consumer nào đã chạy với bản stub đó? |

Một **version** là nhãn. Một **Git commit** chỉ bản source trong repository. Một **checksum** xác định nội dung file. Một **CI run ID** xác định lần thực hiện. Những thứ này có liên quan nhưng **không thay thế nhau**.

Ví dụ, cùng tọa độ `2.5.0-SNAPSHOT` có thể chỉ đến các bytes khác nhau theo thời gian. Ngược lại, một Git commit có thể tạo output khác nếu dependencies, build plugin, biến môi trường hoặc artifact nguồn ngoài thay đổi.

## 4. Bắt đầu từ tệp hợp đồng nguồn

Giả sử producer có cấu trúc:

~~~text
order-service/
├── pom.xml
├── src/
│   └── test/
│       └── resources/
│           └── contracts/
│               └── orders/
│                   ├── get_paid_order.yml
│                   └── get_missing_order.yml
└── src/main/java/...
~~~

Tệp `get_paid_order.yml`:

~~~yaml
description: "Đọc đơn hàng đã thanh toán"
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

Một bản ghi truy vết tối thiểu cần biết:

- **Đường dẫn tương đối** của contract ở đúng revision nguồn.
- **Repository URL hoặc định danh nguồn** mà nhóm có thể truy cập theo quyền được cấp.
- **Commit SHA** hoặc version bất biến của nguồn contract.
- Nếu cần phân biệt các file cùng tên hoặc cùng commit, dùng **checksum file contract**.
- Cách Verifier phát hiện file: contracts root, bộ lọc, cấu hình repository hoặc source set.

### Tên file chưa đủ làm định danh

Hai repository có thể cùng tệp `get_paid_order.yml` nhưng nội dung khác nhau. Vì vậy:

~~~text
get_paid_order.yml
~~~

là bằng chứng yếu. Một tham chiếu mạnh hơn:

~~~text
contract_repo = order-contracts
contract_commit = def456...full-sha...
contract_path = orders/get_paid_order.yml
contract_sha256 = SHA256_THUC_TE_CUA_FILE
~~~

**Không tự điền một SHA-256 trông hợp lệ** vào manifest chỉ để đủ trường; checksum phải được tính từ bytes file thật đã dùng trong build.

### Khi hợp đồng và producer ở cùng repository

Trong thiết kế đơn repository, `contract_commit` thường trùng hoặc được suy ra từ **producer commit**, miễn là build dùng một checkout sạch của commit đó.

Tuy nhiên, vẫn nên ghi **đường dẫn** và xác minh:

- Working tree sạch hoặc build lấy từ checkout bất biến.
- Không có script trước test tự sửa contracts.
- Không lấy thêm hợp đồng ngoài repository mà không ghi nguồn.
- Hệ thống build không âm thầm dùng mapping cũ dưới thư mục `target`.

### Khi hợp đồng ở repository riêng

Không được ghi `producer_commit` thay cho `contract_commit`. Hai repository có lịch sử và vòng đời khác nhau:

~~~text
producer_repo    = git.example.test/order-service.git
producer_commit  = abc123...
contract_repo    = git.example.test/order-contracts.git
contract_commit  = def456...
~~~

Nếu producer lấy contracts từ một **Maven dependency** thay vì Git checkout, cần bổ sung group/artifact/version/classifier và checksum của **contract dependency**; ghi commit nguồn khi có thể truy ngược đến nguồn đã publish dependency đó.

## 5. Truy vết từ một hợp đồng sang generated producer tests

Spring Cloud Contract Verifier có thể sinh producer tests từ DSL. Nhưng **chỉ nhìn thấy generated Java source chưa đủ**. Cần biết:

1. Plugin thực sự **phát hiện những contracts nào**.
2. Generated tests được thêm vào **test source set**.
3. Generated tests **biên dịch** với base test class đúng.
4. Test runner đã **thực thi** chúng.
5. Test report ghi **PASS/FAIL/SKIPPED**, không phải `0 tests`.
6. Lần chạy này diễn ra trên đúng producer source revision và đúng contract revision.

Ví dụ chuỗi thao tác Maven:

~~~bash
./mvnw -B clean verify
~~~

Khi Spring Cloud Contract Maven plugin đã được bind đúng lifecycle, build có thể sinh test, chuyển hợp đồng thành WireMock mappings và đóng gói stub. Tuy nhiên `verify` chỉ là một pha Maven: các test/plugins cần phải được cấu hình để chạy đúng.

**Không kết luận tất cả generated tests đã chạy vì Maven báo `BUILD SUCCESS`.** Nếu goals hoặc test runner bị skip, build có thể thành công mà không có xác minh producer cần thiết.

### Bằng chứng về số lượng tests

Một báo cáo CI hữu ích nên chứa:

~~~yaml
# Dữ liệu minh họa, không phải output mặc định.
expected_contracts: 12
discovered_contracts: 12
generated_producer_tests: 12
executed_producer_tests: 12
failed_producer_tests: 0
skipped_producer_tests: 0
producer_test_result: PASS
~~~

Các số này **không nhất thiết có quan hệ 1 contract = 1 test** trong mọi cấu hình. Tổ chức generated methods/classes, grouping và kịch bản HTTP/message có thể khác. Quy trình thật cần đối chiếu tập contract/scenario và generated test report theo quy ước phiên bản dự án, không giả định một phép đếm đơn giản luôn đúng.

**Thực tế quan trọng:** số lượng 12 ở ví dụ là giả định. Chỉ ghi `generated_producer_tests: 12` khi CI đã thật sự đo được.

## 6. Truy vết sang stub mappings và JAR

Cùng nguồn hợp đồng có thể được chuyển thành WireMock mappings hoặc tài nguyên dùng để tạo message stub. Sau khi đóng gói, stub artifact thường mang classifier `stubs`.

~~~text
Producer artifact:
com.example.orders:order-service:2.5.0

Stub artifact:
com.example.orders:order-service:2.5.0:stubs

Tên file theo quy ước Maven thông dụng:
order-service-2.5.0-stubs.jar
~~~

Một số bản Spring Cloud Contract đóng gói contracts và mappings trong cấu trúc dưới `META-INF`. Ví dụ minh họa:

~~~text
order-service-2.5.0-stubs.jar
└── META-INF/
    └── com.example.orders/
        └── order-service/
            └── 2.5.0/
                ├── contracts/
                │   └── orders/get_paid_order.yml
                └── mappings/
                    └── orders/get_paid_order.json
~~~

**Không mặc định đường dẫn/tên file trong JAR giống hệt ví dụ**. Cấu trúc có thể thay đổi theo plugin version, contracts root hoặc cấu hình đóng gói.

Dùng lệnh kiểm tra nội dung artifact đã được sinh:

~~~bash
jar tf target/order-service-2.5.0-stubs.jar
~~~

Một thao tác kiểm tra có ý nghĩa cần xác minh:

- Có mapping cho từng kịch bản được trông đợi.
- Có response files nếu mapping tham chiếu response file.
- Mappings match method/path/headers/body theo hợp đồng.
- Không chứa fixture/secret production.
- JAR thực sự là bản **được publish**, không chỉ một file cục bộ khác cùng tên.

### Không phải lúc nào mapping name = contract name

Một contract có thể dẫn tới nhiều tài nguyên sinh ra; tên generated test, JSON mapping và YAML contract không nhất thiết tương ứng **một-một theo tên file**. Vì vậy, muốn truy vết chính xác theo kịch bản, nhóm có thể duy trì danh sách **contract IDs** và kiểm tra mapping được tạo ở bước build.

Đừng tuyên bố Spring Cloud Contract **tự động sinh** một manifest ánh xạ từng source contract tới từng mapping/test nếu dự án chưa kiểm chứng khả năng đó trên phiên bản đang dùng.

## 7. Tại sao cần SHA-256 của stub artifact?

Tọa độ Maven trả lời “tên và version là gì?” nhưng không luôn trả lời “**bytes nào** đã được test và publish?”.

Ví dụ:

~~~text
com.example.orders:order-service:2.5.0:stubs
~~~

Nếu một repository cho phép **ghi đè release artifact**, lần tải sau có thể nhận JAR có nội dung khác dù coordinate không đổi. Với `SNAPSHOT`, việc cùng version có bản build mới là hành vi thường gặp.

Do đó, sau khi đóng gói artifact đã hoàn chỉnh, CI có thể tính SHA-256:

~~~bash
sha256sum target/order-service-2.5.0-stubs.jar
~~~

Trên Windows PowerShell có thể dùng công cụ hash tương ứng như `Get-FileHash`; đoạn trên là ví dụ shell POSIX. **Không cần chạy những lệnh này để đọc bài**.

Một evidence record:

~~~yaml
artifact:
  group_id: com.example.orders
  artifact_id: order-service
  version: "2.5.0"
  classifier: stubs
  extension: jar
  sha256: "SHA256_THUC_TE_DO_CI_TINH"
~~~

### Tính checksum ở đúng thời điểm

1. Hoàn tất sinh/đóng gói stub JAR.
2. Tính checksum từ **artifact cuối cùng**.
3. Publish artifact.
4. Nếu kiểm soát quy trình publish, **tải lại** hoặc so checksum server-side của artifact remote.
5. Consumer kiểm tra checksum/artifact identity mà nó thật sự lấy về.

Nếu **sửa JAR sau khi tính hash**, checksum cũ không còn xác định đúng bytes. Có thể lưu manifest provenance **bên ngoài JAR**, gắn với coordinate và checksum, để tránh tình huống nhúng checksum của chính file vào file rồi làm thay đổi hash.

## 8. Evidence manifest: liên kết toàn bộ bằng chứng

Spring Cloud Contract cung cấp công cụ sinh test/stub, còn một **evidence manifest** là cấu trúc **do nhóm tự thiết kế** để gắn dữ liệu Git, CI, Maven và consumer.

Ví dụ:

~~~yaml
# Mẫu do dự án thiết kế; KHÔNG phải file SCC sinh mặc định.
schema: "contract-provenance/v1"
producer:
  service: "order-service"
  repository: "git.example.test/team/order-service"
  commit: "abc123_FULL_PRODUCER_COMMIT_SHA"
  build_version: "2.5.0"

contracts:
  source_kind: git
  repository: "git.example.test/team/order-contracts"
  revision: "def456_FULL_CONTRACT_COMMIT_SHA"
  root: "contracts/orders"
  files:
    - path: "get_paid_order.yml"
      sha256: "SHA256_THUC_TE_CUA_CONTRACT"

verification:
  ci_run_id: "build-7824-attempt-1"
  ci_run_url: "https://ci.example.test/runs/7824"
  result: PASS
  generated_tests_detected: true
  producer_tests_executed: true
  producer_tests_failed: 0
  producer_tests_skipped: 0
  report_uri: "https://ci.example.test/runs/7824/reports"
  build_tool: "Maven"
  plugin_version: "VERSION_DA_KHOA"

stub_artifact:
  group_id: "com.example.orders"
  artifact_id: "order-service"
  version: "2.5.0"
  classifier: "stubs"
  extension: "jar"
  repository: "https://repo.example.test/maven/releases"
  sha256: "SHA256_THUC_TE_CUA_JAR"
  published: true
~~~

**Không được thay placeholder bằng số liệu tưởng tượng rồi coi manifest là bằng chứng.** CI phải lấy các giá trị từ Git, Maven, test reports và artifact thực đã upload.

### Phân biệt bằng chứng và lời tự khai

| Trường | Nguồn tạo giá trị phù hợp |
| --- | --- |
| `producer.commit` | Git revision đã checkout trong CI |
| `contracts.revision` | Git/dependency revision thực sự được nạp |
| `contracts.files[].sha256` | Hash nội dung file đã dùng |
| `verification.result` | Test report và exit status của job xác minh |
| `producer_tests_executed` | Test runner reports, không phải dự đoán |
| `stub_artifact.version` | Maven project/publication metadata |
| `stub_artifact.sha256` | Hash của JAR đã đóng gói |
| `stub_artifact.published` | Kết quả upload và kiểm tra artifact ở repository |

Một manifest có trường `result: PASS` nhưng **không có test report** hoặc không xác định được run ID chỉ là **lời tuyên bố**, chưa phải chứng cứ đủ mạnh.

### Khi nào giữ manifest ngoài artifact?

Tách manifest khỏi JAR có vài lợi ích:

- Có thể ký/lưu evidence sau khi checksum JAR đã cố định.
- Dễ cập nhật link báo cáo CI mà không sửa JAR.
- Có thể quản lý retention hoặc quyền truy cập test logs khác với artifact.
- Không đưa thông tin hạ tầng nhạy cảm hoặc thông tin cá nhân vào stub JAR được consumer tải rộng rãi.

Nếu muốn nhúng metadata build **bên trong JAR**, cần tạo chúng **trước** khi tính checksum cuối cùng, kiểm tra không rò rỉ thông tin và vẫn duy trì bằng chứng ở hệ thống CI/repository.

## 9. Không phải mọi trường hợp đều dùng cùng một contract repository

Có ba mô hình thường gặp:

| Mô hình | Nguồn hợp đồng | Điều cần ghi |
| --- | --- | --- |
| **Cùng repository với producer** | `src/test/resources/contracts` trong repo producer | Producer commit, contracts root/path, trạng thái checkout |
| **Repository hợp đồng riêng** | Git repo của contracts | Producer commit và contract commit độc lập |
| **Contract dependency từ Maven repository** | Artifact chứa DSL đã publish | Coordinate/version/checksum của contract artifact và nguồn Git nếu truy được |

### Mô hình cùng repository

~~~text
order-service@abc123
  |
  +-- src/test/resources/contracts/orders/get_paid_order.yml
  |
  +-- generated producer tests (CI build-7824)
  |
  +-- order-service:2.5.0:stubs
~~~

Trong trường hợp này, một producer commit cố định thường xác định nguồn contract. Nhưng nếu build dùng cache cũ hoặc script tải thêm DSL ngoài, phải ghi bổ sung.

### Mô hình repository riêng

~~~text
order-contracts@def456
          |
          v
order-service@abc123  -->  CI build-7824
          |                   |
          +-------------------+
                   |
                   v
       order-service:2.5.0:stubs
~~~

Producer CI phải **khóa** contract revision mà nó dùng. Không chỉ khai báo `main`, `HEAD` hoặc `latest` rồi ghi commit hiện tại của producer, vì nguồn hợp đồng có thể thay đổi giữa hai lần build.

### Contract dependency là artifact

Ví dụ theo quy ước nhóm:

~~~text
com.example.contracts:order-contracts:7.3.1:contracts
~~~

Đây là **tọa độ minh họa**, không bắt buộc classifier `contracts` trong mọi dự án. Nếu plugin phân giải một contract dependency từ Maven repository, phải ghi đúng metadata của dependency thật được sử dụng.

Nếu contract artifact bị ghi đè cùng version, vẫn có nguy cơ mất truy vết. Tương tự stub JAR, checksum và chính sách immutable giúp bảo vệ tính tái lập.

## 10. Maven install/deploy: từ artifact local sang remote

Ba pha không giống nhau:

| Pha | Kết quả chính | Vai trò trong provenance |
| --- | --- | --- |
| `package` | Tạo main JAR và có thể attach `-stubs.jar` | Xác định bytes artifact của build |
| `verify` | Thực thi các checks đã bind | Gắn kết quả kiểm chứng với build |
| `install` | Đưa artifacts đã attach vào Maven local repository | Hữu ích cho thử nghiệm trên cùng máy/agent |
| `deploy` | Publish artifacts lên remote Maven repository | Cho phép consumer CI khác tải artifact |

Ví dụ:

~~~bash
./mvnw -B clean verify
# Kiểm tra test reports và stub jar ở target/.

./mvnw -B install
# Đưa artifacts vào Maven local nếu build đủ điều kiện.

./mvnw -B deploy
# Chỉ chạy trong pipeline có quyền publish.
~~~

Các lệnh trên minh họa từng bước. **Thực tế `install`/`deploy` sẽ chạy lại các pha trước của default lifecycle**, nên không nhất thiết phải chạy cả ba lệnh trong một release job. Nếu muốn bảo đảm **đúng một bộ bytes** được promote, thiết kế pipeline để artifact đã verify được lưu và publish **không bị rebuild với đầu vào thay đổi**; hoặc kiểm chứng checksum của artifact sau mỗi lần build.

### Maven local không phải nguồn dùng chung

Một stub được `install` vào `~/.m2/repository` trên laptop người viết **không tự xuất hiện** trên máy consumer hoặc runner CI. Trong `LOCAL` mode, Stub Runner lấy từ môi trường local của chính process đang chạy, vốn có thể đang cache artifact cũ.

Trong `REMOTE` mode, Stub Runner dùng repository được cấu hình. Vì vậy, evidence cần nói rõ nó đã sử dụng **nguồn nào**.

### Release repository nên tránh overwrite

Một release coordinate như:

~~~text
com.example.orders:order-service:2.5.0:stubs
~~~

nên trỏ tới một artifact bất biến. Nếu hệ thống cho phép ghi đè, phải kiểm tra checksum và lưu bằng chứng cụ thể cho từng lần publish; tốt hơn là thay đổi chính sách để không ghi đè release.

## 11. Git commit chưa đồng nghĩa build tái lập hoàn toàn

Hai lần build cùng commit có thể cho JAR khác nhau vì:

- Dependency snapshot hoặc dynamic dependency được cập nhật.
- Maven plugin/JDK/toolchain chưa được khóa version.
- Build tải contracts từ branch hoặc Maven artifact không bất biến.
- Test fixture hoặc code generator dùng `Instant.now()`, random không có seed hay dữ liệu ngoài.
- Resource order, build timestamp, archive metadata hoặc cơ chế đóng gói không reproducible.
- Job build từ working tree có file chưa commit hoặc nội dung generated được sửa sau đó.

Do đó cần phân biệt **provenance** với **reproducible build**:

- **Provenance:** biết *artifact nào được sinh bởi input và lần chạy nào*.
- **Reproducibility:** có thể tái tạo cùng artifact từ cùng input/toolchain theo quy trình đã định.
- **Compatibility:** producer và consumer thỏa mãn những hợp đồng/kịch bản được kiểm chứng.

Một evidence manifest tốt **không tự chứng minh reproducible bytes**. Nếu cần bảo đảm mạnh hơn, có thể chạy build tái lập ở môi trường độc lập, so checksum và ký provenance theo chính sách supply-chain của tổ chức.

## 12. Producer test PASS: cần biết test nào đã chạy

Một producer build có thể báo PASS dù hợp đồng quan trọng bị bỏ qua. Các nguyên nhân có thể gồm:

- Contracts root sai hoặc các file bị filter.
- Spring Cloud Contract plugin không được kích hoạt ở đúng Maven module.
- Generated tests không nằm trong test source set.
- Test runner bị cấu hình exclude/skip.
- `-DskipTests` hoặc `-Dmaven.test.skip=true` được dùng.
- Base test class mock toàn bộ producer response thay vì kích hoạt logic cần kiểm chứng.
- Các test chỉ kiểm tra matcher quá rộng, bỏ sót field mà consumer phụ thuộc.

Vì vậy, bản ghi `verification.result: PASS` nên đi kèm:

1. Danh sách/đếm **contracts đã phát hiện**.
2. Danh sách/đếm **producer tests sinh ra** theo cách parser/version thực tế hỗ trợ.
3. **Test execution reports** và số test bị skip.
4. Commit và run ID của lần chạy.
5. Đường dẫn tới log/report trong thời hạn lưu trữ phù hợp.
6. Kết quả các bài test bổ sung nếu hợp đồng chỉ bao phủ một phần behavior.

**Không biến việc test PASS thành cam kết “mọi API và mọi consumer đều tương thích”.** Producer contract test chỉ chứng minh các tình huống được mô tả và thực thi với fixture/base test cụ thể.

## 13. Consumer phải chứng minh nó tải và dùng đúng stub

Sau khi publish, phía consumer có thể dùng:

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
class CheckoutContractTest {

    @Test
    void checkoutHandlesPaidOrder() {
        // Cấu hình Checkout gọi đúng stub server.
        // Assert logic Checkout khi nhận response ORDER_PAID/PAID.
    }
}
~~~

Đây là **khung minh họa**, cần classpath, Spring test setup và assertions thực tế. Lệnh này không tự chứng minh consumer đã tải đúng bytes nếu repository/cache bị cấu hình khác.

Consumer CI nên ghi:

~~~yaml
# Bản ghi do nhóm tự thiết kế, không phải output mặc định.
consumer:
  service: "checkout-service"
  commit: "cde789_FULL_CONSUMER_COMMIT_SHA"
  ci_run_id: "checkout-build-8812"
  result: PASS
stub_used:
  coordinate: "com.example.orders:order-service:2.5.0:stubs"
  sha256: "SHA256_DA_XAC_MINH"
  resolution_mode: "REMOTE"
  repository: "https://repo.example.test/maven/releases"
~~~

### Vì sao cần biết checksum bên consumer?

Vì cùng version `SNAPSHOT` hoặc một repository bị ghi đè có thể trả bytes khác ở các lần tải. Nếu consumer chỉ ghi tọa độ và không xác minh artifact thực, có thể không chứng minh nó chạy trên đúng JAR đã được producer xác minh.

### Không chỉ kiểm tra Stub Runner khởi động

Một kết quả consumer có giá trị cần:

- Stub Runner thật sự tải đúng artifact.
- HTTP client của consumer gọi stub server đúng host/port/service ID.
- Request khớp mapping mong đợi.
- Consumer test assert **hành vi ứng dụng**, ví dụ trạng thái Checkout sau khi nhận response.
- Những kịch bản lỗi mà consumer dựa vào cũng được kiểm tra nếu thuộc phạm vi cam kết.

Stub Runner **không chạy producer implementation**. Nó mô phỏng behavior đã sinh từ contracts. Vì vậy phải giữ liên kết với producer verification.

## 14. Bằng chứng hai chiều: producer và consumer

~~~mermaid
flowchart LR
    CR["Contract revision<br/>def456"] --> PV["Producer CI<br/>commit abc123 / run 7824"]
    PV --> SJ["Stub JAR<br/>2.5.0:stubs / sha256"]
    SJ --> CV["Consumer CI<br/>Checkout cde789 / run 8812"]
    CV --> R["Tương thích trong<br/>tập kịch bản đã kiểm tra"]
~~~

Đối với một lần release, có thể dựng bảng:

| Thành phần | Giá trị minh họa | Bằng chứng |
| --- | --- | --- |
| Contract source | `order-contracts@def456` | Git commit + contract files |
| Producer implementation | `order-service@abc123` | Git commit + build metadata |
| Producer verification | `build-7824 PASS` | Test report, discovered contracts |
| Stub artifact | `order-service:2.5.0:stubs` | Published Maven coordinate |
| Artifact identity | `SHA256_THUC_TE` | Checksum |
| Consumer tested | `checkout@cde789` | Git revision của consumer |
| Consumer verification | `build-8812 PASS` | Test report + resolved stub checksum |

Đây là **quan hệ hai chiều** vì có thể bắt đầu từ:

- **Producer:** “Bản `2.5.0` đã được những consumer nào kiểm tra?”
- **Consumer:** “Stub mà build Checkout này tải được sinh từ source/hợp đồng và producer verification nào?”

Một hệ thống evidence tốt cho phép truy vấn theo cả hai hướng mà không cần suy đoán từ tên JAR.

## 15. Trace theo từng contract, không chỉ theo toàn bộ artifact

Một stub artifact thường chứa **nhiều kịch bản**. Để biết contract nào ảnh hưởng một consumer, có thể duy trì bảng truy vết ở mức scenario:

| Contract ID | Source path | Stub case | Consumer cần nó |
| --- | --- | --- | --- |
| `get_paid_order` | `orders/get_paid_order.yml` | GET /api/orders/ORD-1001 → 200 | Checkout |
| `get_missing_order` | `orders/get_missing_order.yml` | GET /api/orders/ORD-9999 → 404 | Checkout |
| `create_order` | `orders/create_order.yml` | POST /api/orders → 201 | Sales Portal |

Đây là **bảng do nhóm xây dựng**, không phải tính năng mặc định bảo đảm mọi mapping có thể truy vết một-một theo tên.

Lợi ích:

- Khi contract `get_paid_order` thay đổi, biết consumer nào cần chạy lại.
- Khi một mapping biến mất khỏi stub JAR, phát hiện thiếu scenario.
- Khi producer test được sinh nhưng không chạy, xác định phạm vi hợp đồng chưa có bằng chứng.
- Khi đánh giá breaking change, thấy ảnh hưởng đến từng consumer quan tâm.

**Không nên dùng bảng này để bỏ qua consumer không được liệt kê** nếu việc đăng ký consumer chưa đầy đủ. Danh sách phụ thuộc cũng phải được quản trị và cập nhật.

## 16. Hợp đồng HTTP và message contract khác nhau về cách kiểm chứng

Spring Cloud Contract có thể áp dụng cả với HTTP và message-based integration.

| Góc nhìn | HTTP contract | Message contract |
| --- | --- | --- |
| Input | Method/path/header/body | `triggeredBy` hoặc `messageFrom` |
| Output | HTTP status/headers/body | `outputMessage` với `sentTo`, body, headers |
| Producer verification | Generated test gọi endpoint | Generated test kích hoạt producer/gửi message rồi kiểm tra output |
| Stub phía consumer | WireMock mapping | Message stub/trigger theo tích hợp Stub Runner |
| Provenance chung | Source revision, producer tests, artifact, checksum, consumer result | Cùng các thành phần provenance đó |

Với message contracts, cần ghi thêm nếu consumer phụ thuộc:

- Tên topic/queue/binding hoặc logical destination được kiểm chứng.
- Schema/serializer và version nếu format trên wire có quy tắc riêng.
- Label của message stub khi consumer dùng trigger theo label.
- Giới hạn của broker test double so với broker production.

**Một message stub PASS không tự chứng minh delivery guarantee, ordering hoặc exactly-once của broker.** Những thuộc tính đó đòi hỏi test/hạ tầng bổ sung. Evidence nên mô tả chính xác producer test đã dùng mock binder hay broker thực.

## 17. Các tình huống provenance đứt gãy

| Dấu hiệu | Gốc rễ khả dĩ | Cách điều tra |
| --- | --- | --- |
| Consumer PASS với stub version cũ | Không thay version trong Stub Runner ID | Đối chiếu version producer đang phát hành |
| Cùng Maven version nhưng checksum khác | Snapshot/overwrite hoặc repository cache | Kiểm tra bytes, checksum, chính sách immutable |
| Producer tests PASS nhưng stub JSON khác hợp đồng đã review | Sinh mapping từ contract revision khác | Kiểm tra source root, checkout, contract dependency |
| Stub JAR có file nhưng producer test chưa chạy | Build skip tests hoặc misconfigured lifecycle | Xem test reports và goals thực thi |
| Manifest ghi commit nhưng build có uncommitted changes | CI không kiểm tra working tree | Dùng immutable checkout/snapshot và ghi dirty flag |
| Producer và contracts ở hai repo nhưng chỉ ghi producer SHA | Thiếu contract provenance | Ghi contract repository + pinned revision |
| Remote deploy thành công nhưng consumer LOCAL dùng JAR cũ | Cache Maven local không đồng bộ | Dùng nguồn REMOTE đúng hoặc cô lập local repository |
| Mapping trong JAR thiếu scenario | Filter/convert/package sai | So danh sách contracts và mappings sau package |
| Consumer report PASS nhưng không rõ artifact nào | Không log resolution/version | Ghi Stub Runner ID, repo, checksum của file đã dùng |
| Test report của CI đã bị xóa | Retention không đủ | Lưu bản tóm tắt ký xác nhận hoặc archive reports theo policy |
| Release artifact bị overwrite sau test | Không có immutable promotion | Khóa releases, kiểm tra checksum trước/ sau publish |
| Consumer test chỉ kiểm tra stub khởi động | Thiếu assertion logic | Thêm test thật sự sử dụng response của stub |

Chẩn đoán nên bắt đầu từ **câu hỏi provenance bị đứt ở mũi tên nào**, thay vì sửa matcher hoặc đổi version tùy tiện.

## 18. Quản trị bảo mật và quyền truy cập evidence

Stub JAR có thể chứa sample payload, headers hoặc response files; CI evidence có thể chứa đường dẫn repository nội bộ và test logs. Để chia sẻ an toàn:

1. Chỉ đưa **dữ liệu tổng hợp** vào hợp đồng/fixture; không sao chép request/response production có thông tin cá nhân.
2. Không nhúng password, access token, private key hay repository credentials vào stub artifact hoặc manifest.
3. Lưu credentials của Maven repository trong secret manager/CI settings, giới hạn quyền publish.
4. Đặt quyền đọc/ghi cho source contracts, artifact repository và test reports theo nhu cầu consumer/team.
5. Giữ artifact release bất biến; nếu cần revoke artifact lỗi, có quy trình rõ và ghi nhận hậu quả với consumer.
6. Lưu audit log cho người/job publish và thời điểm publish.
7. Dùng checksums/signatures/provenance attestations khi mức độ bảo đảm của tổ chức yêu cầu.
8. Xây retention hợp lý để sau một lần phát hành vẫn có thể tìm lại test report đã dẫn đến quyết định.

**Checksum không phải chữ ký số.** SHA-256 giúp so sánh bytes; nó không tự chứng minh người phát hành hợp lệ. Nếu cần xác thực publisher và chống giả mạo evidence, cần thêm chữ ký/attestation và quản lý khóa, không chỉ một trường hash trong YAML.

## 19. Thiết kế release gate với provenance bắt buộc

Một pipeline producer có thể chia các bước:

~~~mermaid
flowchart TD
    A["Checkout producer + pinned contract revision"] --> B["Xác minh working tree/inputs"]
    B --> C["Sinh generated producer tests"]
    C --> D{"Đủ test, không skip, PASS?"}
    D -->|Không| X["BLOCK"]
    D -->|Có| E["Sinh mappings và đóng gói stub JAR"]
    E --> F{"Đủ mappings, không chứa secret?"}
    F -->|Không| X
    F -->|Có| G["Tính artifact checksum"]
    G --> H["Lưu producer verification evidence"]
    H --> I["Publish artifact immutable"]
    I --> J{"Artifact remote đúng hash?"}
    J -->|Không| X
    J -->|Có| K["Consumer CI tải đúng artifact"]
    K --> L{"Consumer assertions PASS?"}
    L -->|Không| X
    L -->|Có| M["Lưu producer-consumer release record"]
~~~

### Quy tắc dừng phát hành

Nên BLOCK khi:

- Không phát hiện được contract bắt buộc.
- Generated producer tests bị skip hoặc không có báo cáo thực thi.
- Producer contract test FAIL.
- Mappings/stub JAR thiếu kịch bản hoặc chứa dữ liệu nhạy cảm.
- Artifact coordinate hoặc checksum không khớp với bản đã verify.
- Consumer cần hỗ trợ không được chạy với stub mới hoặc tests FAIL.
- Không xác định được revision contract đã dùng để sinh stub.

Cần phân biệt **lỗi xác minh** với **lỗi hạ tầng**. Ví dụ remote repository lỗi 503 chưa chứng minh hợp đồng sai, nhưng cũng chưa cho phép công bố release thành công.

### Không nên để consumer CI dùng một biến `latest` thiếu kiểm soát

Một ví dụ không phù hợp để kết luận release tương thích:

~~~text
com.example.orders:order-service:+:stubs
~~~

Các phiên bản Stub Runner hỗ trợ kiểu version động có thể phân giải bản mới theo repository ở các thời điểm khác nhau. **Chốt phiên bản** hoặc ghi cụ thể phiên bản đã phân giải và hash là cách xây bằng chứng có thể tái lập.

## 20. Ví dụ kịch bản CI theo bước, không phụ thuộc nhà cung cấp

Đây là **pseudocode shell/CI** để hiểu thứ tự, không phải script có thể copy và chạy ngay trong mọi repository:

~~~bash
# 1. CI checkout source commit và contract revision cố định.
#    Ghi producer_commit, contract_commit, run_id.

# 2. Build và xác minh producer.
./mvnw -B clean verify

# 3. Đọc báo cáo Surefire/Failsafe hoặc runner tương ứng.
#    Kiểm tra contract scenarios mong đợi,
#    generated tests thực sự chạy, không bị skip.

# 4. Kiểm tra stub artifact và mapping.
jar tf target/order-service-2.5.0-stubs.jar

# 5. Tính checksum của artifact hoàn chỉnh.
sha256sum target/order-service-2.5.0-stubs.jar

# 6. Sinh evidence manifest từ metadata và reports THẬT.
#    Không tự đánh dấu PASS nếu một bước chưa có bằng chứng.

# 7. Publish artifact vào repository được phép.
#    Xác minh checksum của bản ở remote repository.

# 8. Consumer CI phân giải đúng tọa độ/checksum của stub.
#    Chạy Stub Runner và assertions của consumer.

# 9. Ghi consumer commit, run_id, result và artifact đã dùng.
~~~

Bài học không quy định phải dùng Jenkins, GitHub Actions, GitLab CI hay một hệ thống riêng. Quan trọng là **metadata đo được**, **các cổng kiểm chứng**, và **quan hệ xác minh giữa bản được build và bản được tiêu thụ**.

### Những gì nên tự động hóa

- Trích xuất Git SHA và kiểm tra uncommitted changes trong checkout.
- Ghi dependency/plugin versions đã khóa.
- Tổng hợp test reports theo trạng thái `passed/failed/skipped`.
- Kiểm tra contracts root và số scenario bắt buộc.
- Kiểm tra tệp/tài nguyên bên trong stub JAR.
- Tính và xác minh checksum artifact.
- Ghi lại GAV/classifier/version đã publish.
- Ghi Stub Runner ID/version/repository và checksum mà consumer tải.
- Lưu producer–consumer compatibility record có thể truy vấn.

Một script CI chỉ grep chuỗi `BUILD SUCCESS` trong log **không đủ** để chứng minh các điều trên.

## 21. Đánh giá tương thích theo thời điểm phát hành

Giả sử producer phát hành liên tiếp:

| Phiên bản producer | Contract revision | Stub artifact | Producer tests |
| --- | --- | --- | --- |
| `2.4.0` | `contracts@d111` | `2.4.0:stubs` | PASS trên build 7001 |
| `2.5.0-rc1` | `contracts@d222` | `2.5.0-rc1:stubs` | PASS trên build 7824 |
| `2.5.0` | `contracts@d222` | `2.5.0:stubs` | Cần xác minh build phát hành riêng |

**Không mặc định** `2.5.0` đã được producer test chỉ vì release candidate `2.5.0-rc1` từng PASS. Nếu artifact cuối có bytes khác, code hoặc build input khác, phải có bằng chứng tương ứng hoặc một cơ chế promote artifact đã được verify mà không rebuild.

Tương tự, nếu Checkout đang chạy:

~~~text
checkout-service@cde789
test stub = order-service:2.4.0:stubs
result = PASS
~~~

thì không được gán kết quả đó thành:

~~~text
checkout-service@cde789
test stub = order-service:2.5.0:stubs
result = PASS
~~~

mà không có lần chạy consumer thực sự trên bản stub mới.

### Tương thích là quan hệ có phạm vi

Một kết quả hợp lệ nên được hiểu như:

> Consumer commit `cde789` đã PASS những kịch bản đã kiểm thử qua stub artifact `order-service:2.5.0:stubs` với checksum được ghi nhận, được tạo từ contract revision `d222` và producer verification run tương ứng.

Nó không tự chứng minh:

- Tất cả consumer trong tổ chức đã chạy.
- Mọi endpoint hay mọi trạng thái production đã được bao phủ.
- Broker delivery/ordering, TLS production, performance hoặc security policy đã được xác minh.
- Các service đang chạy ở production đều dùng đúng artifact/version.

## 22. Bài tập thực hành

### Bài tập A — Tìm mắt xích còn thiếu

Một báo cáo chỉ ghi:

~~~yaml
stub_artifact: "com.example.orders:order-service:2.5.0:stubs"
consumer_test: PASS
~~~

**Yêu cầu:** liệt kê tối thiểu các trường cần bổ sung để biết artifact này được sinh từ hợp đồng, commit và lần producer verification nào.

**Gợi ý:** contract repository/path/revision, producer commit, CI run ID, test report, artifact SHA-256, consumer commit và version/checksum thực sự được tải.

### Bài tập B — Cùng version, khác SHA-256

Một release repository cho phép ghi đè artifact `2.5.0:stubs`. Producer CI có hash `H1`; consumer CI tải được hash `H2`.

**Yêu cầu:** có thể tuyên bố consumer đã thử đúng bản producer verify không? Cần xử lý thế nào?

**Gợi ý:** không, trừ khi giải thích và chứng minh rõ quan hệ hai artifact; nên chặn release, điều tra overwrite/cache và sử dụng artifact bất biến, xác minh checksum.

### Bài tập C — Hợp đồng ở repository riêng

Producer commit `abc123` dùng contract repo commit `def456`. Một job sinh tests từ `def456`; job đóng gói stub lại tải hợp đồng trên branch `main` đã tiến đến `xyz789`.

**Yêu cầu:** xác định nguy cơ và đề xuất sửa pipeline.

**Gợi ý:** pin contract revision cho cả hai nhánh sinh test/mapping, ghi hash của input và build artifact từ cùng source snapshot.

### Bài tập D — Build xanh nhưng không có producer tests

CI có log `BUILD SUCCESS` và `-stubs.jar`. Tuy nhiên Surefire reports không có generated producer tests.

**Yêu cầu:** đánh giá release gate và các bước chẩn đoán.

**Gợi ý:** kiểm tra plugin executions, contracts root, test source set, skip flags, test runners và base class; chưa đủ bằng chứng producer đúng hợp đồng.

### Bài tập E — LOCAL cache khác REMOTE repository

Người phát triển Checkout dùng Stub Runner `LOCAL` và PASS với stub cũ. CI producer đã publish bản mới vào remote repository.

**Yêu cầu:** chứng minh vì sao kết quả local không xác nhận bản mới và nêu cách tạo consumer run có thể truy vết.

**Gợi ý:** chỉ định phiên bản stub mới, chọn nguồn phân giải rõ, làm sạch/kiểm soát cache và ghi checksum thật.

### Bài tập F — Artifact đã publish nhưng chưa có consumer PASS

Producer `2.5.0` PASS contract tests, JAR đúng checksum và đã publish. Checkout `2.8.0` chưa chạy với stub đó; chỉ có consumer run với `2.4.0`.

**Yêu cầu:** báo trạng thái tương thích như thế nào?

**Gợi ý:** producer-side verified và artifact published, nhưng **consumer compatibility not yet verified** cho cặp phiên bản mới. Không lấy kết quả cũ lấp khoảng trống.

### Bài tập G — Ký provenance và quản lý secret

Một nhóm muốn đính kèm manifest có producer SHA, artifact checksum và CI report URL. Nhóm định nhúng cả repository token vào manifest để consumer dễ tải.

**Yêu cầu:** chỉnh lại phương án cho an toàn.

**Gợi ý:** giữ credentials trong secret manager/CI, chỉ đặt metadata không nhạy cảm trong manifest; nếu cần chứng minh publisher hợp lệ, ký hoặc attestation theo policy.

### Bài tập H — Tạo ma trận kiểm chứng khi thay schema

Order Service `2.5.0` đổi `status` thành `paymentStatus`. Có ba consumer: Checkout `2.8`, Sales Portal `4.1` và Analytics `1.3`.

**Yêu cầu:** thiết kế bảng gồm consumer commit, stub coordinate/checksum, test result và kịch bản sử dụng; giải thích vì sao chỉ có Checkout PASS là chưa đủ.

**Gợi ý:** mỗi consumer cần kết quả riêng trên stub mới nếu còn thuộc phạm vi hỗ trợ; kết hợp contract path/ID để biết tác động.

## 23. Checklist truy vết trước khi công bố tương thích

- [ ] Xác định hợp đồng bằng **repository + revision + path**, không chỉ tên file.
- [ ] Nếu contracts nằm ngoài repo producer, đã khóa đúng dependency/revision.
- [ ] Producer commit và working tree/build input được ghi nhận.
- [ ] Generated producer tests được sinh từ đúng contract revision.
- [ ] Generated producer tests được **thực thi** và PASS, không chỉ tồn tại trong `target`.
- [ ] Không có tình trạng `0 contract tests` hoặc skip ngoài dự kiến.
- [ ] Đã lưu producer CI run ID, report và thời điểm verification.
- [ ] Stub mappings/response resources được sinh từ cùng contract input.
- [ ] Stub JAR chứa đủ kịch bản mong đợi, không có dữ liệu production nhạy cảm.
- [ ] Tọa độ Maven **groupId:artifactId:version:classifier** được ghi rõ.
- [ ] Artifact cuối cùng được tính SHA-256 sau khi đóng gói.
- [ ] Không thay đổi artifact bytes sau khi tính checksum mà không cập nhật evidence.
- [ ] Stub release được publish trong repository có chính sách immutable hoặc kiểm tra hash rõ ràng.
- [ ] Đã kiểm tra artifact remote thực sự tồn tại và khớp checksum.
- [ ] Consumer Stub Runner tải đúng bản từ nguồn được cấu hình, không dùng bản cũ trong cache.
- [ ] Consumer test thực sự gọi stub và assert hành vi ứng dụng.
- [ ] Consumer commit, run ID, kết quả và stub checksum được lưu cùng evidence.
- [ ] Những consumer đang được hỗ trợ có test với stub mới trước release khi cần.
- [ ] Những giới hạn về coverage, broker, TLS, security và production behavior được ghi rõ.
- [ ] Evidence manifest dựa trên dữ liệu đo được, không phải tự đánh dấu PASS.
- [ ] Token/secret/private key không bị đưa vào hợp đồng, stub artifact hay báo cáo.
- [ ] Có thể truy vấn cả hai hướng: **stub → producer verification** và **producer release → consumer runs**.

## Kết luận

**Truy vết stub** không chỉ là ghi `groupId:artifactId:version:stubs` trong một file cấu hình. Một chuỗi bằng chứng đáng tin phải kết nối **tệp hợp đồng và revision nguồn**, **commit producer**, **lần generated producer tests thực sự chạy**, **stub artifact có checksum cố định**, và **consumer run sử dụng đúng artifact đó**. Chỉ khi các quan hệ này được ghi và kiểm tra, CI mới có cơ sở để phát hiện thay đổi API không tương thích thay vì PASS trên một bản stub tình cờ còn tồn tại trong cache.

**Ghi nhớ:** *Một stub chỉ có giá trị như bằng chứng tương thích khi biết được nó đến từ đâu, producer đã được xác minh thế nào và consumer đã thử chính xác bản nào.*
