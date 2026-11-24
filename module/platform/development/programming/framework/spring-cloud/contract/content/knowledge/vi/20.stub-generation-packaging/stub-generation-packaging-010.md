# Tránh công bố stub khi producer test chưa đạt

## Mục tiêu học tập

Trong **Spring Cloud Contract**, producer định nghĩa hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**. Từ hợp đồng đó, công cụ có thể sinh **generated producer tests** để kiểm tra code cung cấp API thực tế và sinh **stub** để consumer chạy kiểm thử bằng **Stub Runner**. Với hệ thống nhiều dịch vụ, việc đặt những bước này đúng thứ tự trong **CI** là một phần của thiết kế kiểm thử hợp đồng, không chỉ là cấu hình build.

Bài này thuộc chương **Sinh và đóng gói stub**, tập trung vào nguyên tắc:

> **Không công bố stub như một hợp đồng đã được producer xác nhận nếu generated producer tests tương ứng chưa chạy thành công.**

Sau bài học, bạn có thể:

- Phân biệt **sinh stub**, **đóng gói stub**, **cài stub vào repository cục bộ** và **công bố stub lên artifact repository**.
- Giải thích vì sao một file `*-stubs.jar` tồn tại **không chứng minh** producer đáp ứng contract.
- Thiết kế **quality gate** dựa trên kết quả generated producer tests, test discovery và tính đồng nhất của revision.
- Cấu hình luồng phát hành với **Maven**, **Gradle** và CI mà không vô tình bỏ qua test.
- Tách **candidate stub dùng thử trong CI** khỏi **stub đã phát hành cho các consumer**.
- Phân tích các trường hợp thất bại: test đỏ, 0 generated tests, `skipTests`, artifact cũ, phiên bản mutable và job publish chạy độc lập.
- Gắn kết quả producer tests, stub artifact và consumer tests vào **cùng một commit/version** để phát hiện sớm thay đổi API không tương thích.

## 1. Vì sao sinh được stub chưa có nghĩa là đã kiểm chứng?

Giả sử **Inventory Service** là producer; **Checkout Service** là consumer. Checkout gọi:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

Hợp đồng mà hai nhóm thống nhất:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

Nhóm producer viết DSL cho tình huống trên. Khi chạy các bước build phù hợp, Spring Cloud Contract có thể tạo:

1. **Producer contract test:** gọi Inventory implementation với request đã mô tả và kiểm tra response.
2. **HTTP stub mapping:** mô tả request mà stub nhận và response giả lập mà stub trả.
3. **Stub artifact:** gói các mapping/contract cùng metadata để Stub Runner có thể tìm và chạy.

Giả sử code Inventory bị lỗi, trả response:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": "8"
}
~~~

Ở response này, `quantity` là **string** thay vì **number**. Consumer deserialize sang một trường số có thể lỗi hoặc có hành vi không mong muốn.

Điều nguy hiểm là **stub sinh từ contract vẫn có thể trả đúng `quantity: 8`**, vì stub dựa trên mô tả hợp đồng, không dựa vào response thực của code producer. Nếu nhóm publish stub đó mà chưa chạy test producer thành công, Checkout có thể:

- Chạy test bằng Stub Runner và **xanh** vì stub trả number `8`.
- Triển khai với producer thật và **lỗi** vì producer trả string `"8"`.

Đây là ví dụ **stub tự mô tả lời hứa nhưng chưa chứng minh lời hứa được thực hiện**.

### Phân biệt nguồn bằng chứng

| Thành phần | Cho biết điều gì? | Không tự chứng minh điều gì? |
|---|---|---|
| Groovy/YAML contract | Hành vi producer và consumer đã thống nhất | Code producer thật làm đúng |
| Generated producer test tồn tại | Generator đã tạo test từ DSL | Test đã chạy và đạt |
| Generated producer test **PASS** | Producer đáp ứng các tình huống contract được chạy trong test environment | Mọi tình huống thực tế, mọi consumer cũ đều tương thích |
| Stub mapping được sinh | Có cấu hình mô phỏng để Stub Runner dùng | Producer triển khai đúng |
| `*-stubs.jar` được tạo | Stub đã được đóng gói | Đã vượt quality gate |
| Consumer test chạy với stub **PASS** | Consumer xử lý được stub đang chạy | Stub cùng revision với producer hoặc producer thật đúng |
| Công bố artifact thành công | Consumer có thể lấy artifact từ repository | Quy trình publish đã tuân thủ kiểm soát chất lượng |

**Kết luận:** trạng thái của file artifact và trạng thái kiểm thử phải được xem là **hai loại dữ liệu độc lập**. Chỉ quality gate mới quyết định artifact có được đưa ra cho các consumer như một phiên bản tin cậy hay không.

## 2. Bốn hành động thường bị gọi chung là “publish stub”

Các từ dưới đây có ý nghĩa khác nhau:

| Hành động | Kết quả điển hình | Mức độ ảnh hưởng |
|---|---|---|
| **Generate** | Sinh WireMock mappings, contract definitions và mã test | Output tạm trong workspace build |
| **Package** | Tạo `inventory-producer-1.0.0-stubs.jar` | Có artifact trong workspace; chưa chắc đã xuất bản |
| **Install local** | Đưa artifact vào Maven local repository (`~/.m2/repository`) | Các test trên máy/runner đó có thể tìm thấy artifact |
| **Deploy/publish remote** | Đưa artifact lên Nexus/Artifactory/Maven repository | Các consumer khác có thể tải artifact nếu có quyền |

Trong Spring Cloud Contract, stub thường được xuất bản như một Maven artifact có **classifier `stubs`**, bên cạnh artifact ứng dụng thông thường.

Ví dụ tọa độ minh họa:

~~~text
groupId    = com.example
artifactId = inventory-producer
version    = 1.0.0
classifier = stubs
type       = jar

Maven notation:
com.example:inventory-producer:1.0.0:stubs
~~~

Tọa độ này giúp Stub Runner tìm stub. Nó không phải bằng chứng kiểm thử; artifact với cùng cấu trúc có thể được tạo từ một hợp đồng lỗi hoặc một build đã bỏ qua generated tests.

### File tồn tại khác với artifact đã công bố

~~~text
Workspace producer
  ├── generated contract tests
  ├── reports/ kết quả test
  ├── generated stubs / mappings
  └── inventory-producer-1.0.0-stubs.jar
          |
          | Chỉ được phép phát hành khi quality gate PASS
          v
Artifact repository
  └── com/example/inventory-producer/1.0.0/
        inventory-producer-1.0.0-stubs.jar
~~~

Đường dẫn, tên task và thư mục có thể thay đổi theo Maven/Gradle plugin và cấu hình build. Quy tắc cần giữ là **không suy ra quyền publish chỉ từ việc file JAR đã xuất hiện**.

## 3. Quality gate tối thiểu: điều kiện cần và đủ để được công bố

Một chính sách khuyến nghị có thể được viết bằng mệnh đề:

~~~text
CAN_PUBLISH_STUB =
    CONTRACT_FILES_DISCOVERED
    AND GENERATED_PRODUCER_TESTS_EXECUTED
    AND GENERATED_PRODUCER_TESTS_PASSED
    AND REQUIRED_BUILD_CHECKS_PASSED
    AND STUB_BUILT_FROM_SAME_REVISION
    AND PUBLICATION_AUTHORIZED
~~~

Một tổ chức có thể thêm điều kiện **consumer compatibility tests passed** hoặc phê duyệt release. Nhưng điều kiện **producer test đạt** không nên bị bỏ qua.

| Gate | Kiểm tra gì? | Nếu không đạt |
|---|---|---|
| **G1 — Phát hiện contract** | Plugin tìm được DSL đúng module và các fixture phụ thuộc | Không publish |
| **G2 — Sinh test** | Generated test được tạo và biên dịch cho phiên bản code hiện tại | Không publish |
| **G3 — Thực thi test** | Test thật sự chạy; không bị skip/disable/filter ngoài ý định | Không publish |
| **G4 — Assertion đạt** | Test producer xác nhận status/header/body hoặc message payload/header | Không publish |
| **G5 — Build cần thiết đạt** | Compile, các test bắt buộc và các kiểm tra của dự án | Không publish |
| **G6 — Artifact đồng nhất** | Stub đúng contract, cùng revision và version đã kiểm tra | Không publish |
| **G7 — Quyền phát hành** | Nhánh/tag/approval/credentials hợp lệ | Không publish |

**G1 và G3 đặc biệt quan trọng:** một build báo thành công khi không có generated tests nào được phát hiện có thể là false positive. Tương tự, build dùng `-DskipTests` vẫn có thể tạo output, nhưng không cung cấp bằng chứng producer test đã đạt.

### Không tự coi mọi test xanh là “producer contract test xanh”

Một repository có thể có 500 unit tests đạt nhưng **không chạy một generated contract test nào**. Nếu build đã cấu hình bỏ qua test source set của Spring Cloud Contract, màu xanh của job không có giá trị chứng minh giao diện.

Cần đối chiếu tên test được sinh, báo cáo test runner, số lượng test thực thi và module được chạy. Khi chưa xác nhận, trạng thái đúng phải là **UNVERIFIED**, không phải **PASSED**.

## 4. Contract HTTP làm ví dụ cho gate

File contract Groovy tại producer, chẳng hạn `src/test/resources/contracts/inventory/stockAvailable.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'SKU-101 con hang va quantity la number'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
        headers {
            accept(applicationJson())
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 8
        )
    }
}
~~~

YAML DSL có thể thay thế:

~~~yaml
description: 'SKU-101 con hang va quantity la number'
request:
  method: GET
  url: '/api/inventory/SKU-101'
  headers:
    Accept: 'application/json'
response:
  status: 200
  headers:
    Content-Type: 'application/json'
  body:
    sku: 'SKU-101'
    available: true
    quantity: 8
~~~

**Không cần tạo cả hai bản trong cùng build cho một tình huống**; ví dụ nhằm cho thấy Spring Cloud Contract hỗ trợ hai DSL.

Một generated producer test hợp lệ cần thực hiện tương đương:

~~~text
WHEN:
  GET /api/inventory/SKU-101
  Accept: application/json

THEN:
  HTTP status == 200
  Content-Type indicates application/json
  JSON $.sku == "SKU-101"
  JSON $.available == true
  JSON $.quantity == 8 (number)
~~~

Đây là **pseudocode**, không phải output Java nguyên văn của một phiên bản generator. Hãy mở **generated test thực tế** để xác nhận assertion giữ đúng kiểu dữ liệu, đặc biệt với number, boolean, null và matcher động.

### Base test phải chạy qua producer

Producer có thể cấu hình `baseClassForTests` để dựng:

- Controller thật với service fake có fixture `SKU-101`.
- Spring application context với database test/seed riêng.
- Ứng dụng qua HTTP thật, nếu đã chọn test mode `EXPLICIT`.

Dù chọn cách nào, test phải gửi request vào **mã producer cần kiểm chứng**. Nếu base class thay thế toàn bộ endpoint bằng một stub trả đúng JSON mong đợi, kết quả xanh không chứng minh implementation của Inventory.

Nếu generated test thất bại do producer trả `"quantity":"8"`, đó là tín hiệu cần **chặn publish**, không phải lý do chỉnh hợp đồng thành string cho khớp implementation mà chưa hỏi consumer.

## 5. Phân biệt kiểm tra producer và consumer

~~~mermaid
sequenceDiagram
    participant Dev as Pull request
    participant DSL as Contract DSL
    participant P as Producer test
    participant Jar as Candidate stubs.jar
    participant C as Consumer test
    participant Repo as Remote repository
    Dev->>DSL: Thay đổi API/message contract
    DSL->>P: Sinh test, chạy producer thật
    alt Producer test lỗi
        P-->>Dev: Chặn phát hành
    else Producer test đạt
        DSL->>Jar: Tạo stub từ cùng revision
        Jar->>C: Stub Runner dùng candidate
        alt Consumer test lỗi và policy yêu cầu pass
            C-->>Dev: Chặn phát hành, đánh giá tương thích
        else Các gate bắt buộc đạt
            Jar->>Repo: Publish version đã kiểm chứng
        end
    end
~~~

**Tại sao kiểm thử consumer thường đi sau producer test?** Vì consumer cần một stub ứng viên có độ tin cậy từ phía producer. Trong CI, có thể tạo candidate stub trước để chạy thử nội bộ, nhưng **không quảng bá nó là artifact phát hành hợp lệ** khi producer test chưa đạt.

Lưu ý về thứ tự build thực tế: một số plugin có thể sinh hoặc gói stub ở các phase/task khác nhau. **Thứ tự vật lý của việc sinh file không nhất thiết quyết định thứ tự tin cậy.** Gate publish mới là ranh giới không được vượt qua.

## 6. Maven: dùng lifecycle làm ranh giới an toàn

Với Maven, lifecycle thông thường có các phase theo thứ tự đại ý:

~~~text
validate
   ↓
compile
   ↓
test
   ↓
package
   ↓
verify
   ↓
install
   ↓
deploy
~~~

`mvn verify` chạy các phase cần thiết tới `verify`. `mvn install` và `mvn deploy` cũng thực thi các phase trước đó **nếu gọi bằng lifecycle bình thường**. Vì thế, một lệnh publish dùng đầy đủ lifecycle và không skip test thường an toàn hơn việc gọi trực tiếp một goal upload artifact.

### Cấu hình plugin minh họa

Trong POM của **producer**:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-contract-maven-plugin</artifactId>
      <version>REPLACE_WITH_COMPATIBLE_VERSION</version>
      <extensions>true</extensions>
      <configuration>
        <testFramework>JUNIT5</testFramework>
        <baseClassForTests>
          com.example.inventory.contract.InventoryContractBase
        </baseClassForTests>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Đây chỉ là đoạn cấu hình minh họa. `REPLACE_WITH_COMPATIBLE_VERSION` phải được thay bằng version Spring Cloud Contract tương thích với stack Spring Boot/Spring Cloud dự án. Các dependencies như `spring-cloud-starter-contract-verifier`, starter web, `spring-boot-starter-test` và repository quản lý version cũng phải được thiết lập đầy đủ.

### Lệnh kiểm tra trước khi công bố

~~~bash
# Kiểm chứng producer và các kiểm tra gắn vào lifecycle.
./mvnw -B -ntp clean verify

# Chỉ thực hiện trong bước release được cấp quyền,
# với test không bị bỏ qua và chính source revision cần phát hành.
./mvnw -B -ntp clean deploy
~~~

Lệnh thứ hai chạy lại các phase kiểm chứng trước khi deploy theo lifecycle. Trong CI, có thể chọn **một lệnh `clean deploy` duy nhất trong job release có gate** hoặc tách job verify/release mà **job release vẫn tự xác minh hoặc chỉ publish đúng artifact bất biến đã qua gate**.

**Không mặc định:**

~~~bash
# Chỉ là ví dụ ANTI-PATTERN, không sử dụng để phát hành.
./mvnw deploy -DskipTests
~~~

`-DskipTests` thường bỏ qua thực thi test; `-Dmaven.test.skip=true` có thể bỏ qua cả biên dịch test. Ngoài ra, một số plugin có tùy chọn skip riêng. Những chế độ này có thể làm artifact được tạo mà **không có bằng chứng producer tests đã chạy**.

### Maven lifecycle không phải phép màu

Nếu build cấu hình:

- Bỏ qua generated test source.
- Gắn generated tests vào một profile không được bật.
- Đặt `maven.test.failure.ignore=true`.
- Chạy `deploy:deploy-file` hoặc `install:install-file` trực tiếp với JAR đã có.
- Dùng script tự upload một file trong `target` mà không kiểm tra exit code.
- Cấu hình plugin phát hành theo một phase không có gate.

thì **không thể suy ra rằng `mvn deploy` đồng nghĩa với producer contract tests đã đạt**. Cần review POM, profiles, test reports và các lệnh CI thực tế.

### Khác biệt giữa `test` và `verify`

Một số test tích hợp dùng Maven Failsafe hoặc plugin khác được gắn vào phase sau `test`. Vì thế `mvn test` có thể chưa chạy mọi bước kiểm chứng mà dự án đặt ở `verify`.

Với contract test, hãy kiểm tra plugin thực tế đã tạo/biên dịch/chạy generated tests bằng runner nào. Nếu dự án dùng Failsafe để chạy một số kiểm thử cần context/broker, quality gate phải bao gồm phase liên quan.

## 7. Maven: kiểm tra stub artifact trước khi deploy

Các output thường gặp của Spring Cloud Contract Maven plugin có thể bao gồm:

~~~text
target/
├── generated-test-sources/contracts/
├── stubs/
└── inventory-producer-1.0.0-stubs.jar
~~~

Tên cụ thể có thể khác theo module, classifier, packaging và plugin version. Đừng hardcode đường dẫn khi dự án dùng custom build directory.

Có thể mở nội dung JAR để kiểm tra:

~~~bash
jar tf target/inventory-producer-1.0.0-stubs.jar
~~~

Một layout **mang tính minh họa** của stub HTTP:

~~~text
META-INF/com.example/inventory-producer/1.0.0/
├── contracts/
│   └── inventory/stockAvailable.groovy
└── mappings/
    └── inventory_stockAvailable.json
~~~

Một số build cũng đưa fixture vào artifact. Với **messaging contract**, cần bảo đảm contract/message definition và label cần dùng đã được đóng gói, không chỉ tìm WireMock JSON của HTTP.

### Kiểm tra những gì trong JAR?

1. **Artifact đúng tọa độ:** `groupId`, `artifactId`, `version` và classifier `stubs`.
2. **Mới nhất từ commit đang build:** không lấy JAR còn sót sau lần build cũ.
3. **Contract/mapping thực sự tồn tại:** không phải JAR rỗng hoặc thiếu tình huống quan trọng.
4. **Phiên bản đúng:** bên trong artifact không trộn version khác.
5. **Fixture cần thiết được đóng gói:** file body ngoài, XML hoặc binary mà stub phụ thuộc.
6. **Không chứa bí mật:** token, mật khẩu, dữ liệu người dùng thật hoặc endpoint nội bộ nhạy cảm trong fixture.

**Lưu ý:** kiểm tra nội dung JAR là gate về **đóng gói và toàn vẹn**, không thay thế gate **producer test đạt**.

## 8. Gradle: publication task phải phụ thuộc test bắt buộc

Trong Gradle, việc gọi `publish` không mặc định có nghĩa **mọi test trong dự án** sẽ được chạy. Mức ràng buộc phụ thuộc vào plugin và task graph được cấu hình.

Một số task hay gặp trong hệ sinh thái Spring Cloud Contract Gradle có tên liên quan tới `generateContractTests`, `contractTest`, `generateClientStubs` hoặc `verifierStubsJar`. **Tên thực tế và dependencies cần được kiểm tra bằng `./gradlew tasks --all` và cấu hình plugin của phiên bản đang dùng.**

### Ý tưởng gate ở task graph

Nếu dự án đã có task `contractTest` và task `check` có các kiểm tra bắt buộc, có thể cấu hình task publication tới Maven repository phụ thuộc cả hai:

~~~groovy
import org.gradle.api.publish.maven.tasks.PublishToMavenRepository

tasks.withType(PublishToMavenRepository).configureEach {
    dependsOn(tasks.named('check'))
    dependsOn(tasks.named('contractTest'))
}
~~~

Đây là **mẫu có điều kiện**: chỉ dùng nguyên đoạn này khi project thật có task `contractTest` và plugin `maven-publish`; nếu task tên khác, phải thay bằng task kiểm thử hợp đồng thực tế. Mẫu này chỉ ràng buộc các task **PublishToMavenRepository**; nếu CI sử dụng `publishToMavenLocal`, custom upload hoặc một job bên ngoài, phải tạo gate tương ứng, không mặc định đoạn trên bảo vệ tất cả đường phát hành.

Mệnh đề cần kiểm tra ở task graph là:

~~~text
publish remote stub
    depends on
all required producer contract tests
    depends on
contract generation + compilation + correct test environment
~~~

### Phân biệt kết quả task

| Task/result | Điều được chứng minh | Chưa đủ để công bố khi… |
|---|---|---|
| `generateContractTests` thành công | Generator tạo test | Chưa thực thi test |
| `generateClientStubs` thành công | Generator tạo stub | Producer tests chưa đạt |
| `verifierStubsJar` thành công | Tạo stub JAR | Test chưa chạy/đã skip |
| `test` thành công | Test thuộc task `test` đạt | Contract tests nằm ở task khác chưa chạy |
| `contractTest` thành công | Task test contract đạt nếu đúng được cấu hình | Task phát hiện 0 test, bị filter hoặc không gắn đúng contract |
| `check` thành công | Những verification tasks gắn vào `check` đạt | Contract tests không nằm trong graph của `check` |
| `publish` thành công | Các publication tasks đã được thực thi | Không có dependency tới gate |

Hãy xác minh task graph và log thực tế của dự án. **Không suy tên task là bằng chứng**: một task `contractTest` có thể tồn tại nhưng không chạy bất kỳ generated test nào nếu cấu hình input sai.

### Về `--continue` và skip

Gradle có thể chạy nhiều task dù một task lỗi khi dùng `--continue`, sau đó build vẫn báo thất bại. Điều quan trọng là CI **không được biến kết quả build thất bại thành success** rồi kích hoạt bước publish. Tương tự, việc dùng `-x test` hoặc loại trừ task contract test có thể bỏ qua gate nếu task publication không phụ thuộc ràng buộc chặt.

Tránh các shell pattern nuốt exit code, chẳng hạn tiếp tục publish sau khi lệnh test đã thất bại mà không có điều kiện kiểm tra.

## 9. Hai kiểu pipeline: một job và nhiều job

### Mô hình A — Một job release, chạy test trước deploy

~~~mermaid
flowchart TD
    A["Checkout đúng commit/tag"] --> B["Maven clean verify<br/>hoặc Gradle checks + contract tests"]
    B --> C{"Producer tests được chạy và PASS?"}
    C -->|Không| D["FAIL: không publish"]
    C -->|Có| E["Đóng gói và kiểm tra stub JAR"]
    E --> F{"Metadata/contract đúng revision?"}
    F -->|Không| D
    F -->|Có| G["Publish với quyền release"]
~~~

Ưu điểm: ít phải chuyển file giữa các job; dễ gắn kết quả test với artifact. Nhược điểm: job có quyền release phải được bảo vệ, không nên có secrets trong job chạy code từ PR không tin cậy.

Với Maven, một lệnh lifecycle `clean deploy` trong **job được phép phát hành** có thể tự đi qua các phase bắt buộc. Nhưng vẫn phải xác nhận không có skip flag, không có plugin bỏ qua test và generated tests được chạy thật.

### Mô hình B — Job verify và job publish riêng

~~~text
Job VERIFY (không có quyền upload repository)
  checkout commit A
  generate + run producer contract tests
  assert test count > 0
  package candidate stub
  checksum candidate stub
  attach artifact + test reports to CI

Job CONSUMER CHECK (tùy chính sách)
  tải candidate stub từ VERIFY của commit A
  Stub Runner chạy candidate
  chạy consumer tests
  ghi kết quả

Job PUBLISH (release credentials)
  needs VERIFY (+ CONSUMER CHECK nếu là gate)
  chỉ chạy cho branch/tag được phép
  dùng đúng candidate artifact từ commit A
  kiểm tra checksum, metadata, version
  upload tới repository
~~~

Ưu điểm: tách quyền rõ, tránh dùng release credentials trên PR, có thể reuse đúng artifact đã được kiểm chứng. Nhược điểm: phải **đảm bảo artifact bất biến** khi chuyển job, không âm thầm rebuild hoặc lấy file từ cache không liên quan.

### Hai cách bảo đảm cùng revision

- **Dùng chính JAR từ job verify:** lưu như CI artifact với checksum SHA-256, job publish tải lại và xác minh digest/commit.
- **Build lại trong job publish:** checkout **đúng commit/tag** và chạy lại toàn bộ producer tests trước deploy. Cách này có thể tốn thời gian nhưng không phụ thuộc vào việc giữ JAR từ job trước.

Tránh tình huống verify ở commit A nhưng publish JAR mới build từ commit B, hoặc verify phiên bản `1.0.1` nhưng upload file `1.0.0-stubs.jar` còn trong workspace.

## 10. Ví dụ GitHub Actions: publish chỉ sau producer verification

Đây là **workflow minh họa** cho một module Maven có wrapper `mvnw` và plugin Spring Cloud Contract đã cấu hình; cần điều chỉnh JDK, Maven repository, credentials và kiểm tra test-count cho dự án thật.

~~~yaml
name: contract-stub-gate

on:
  pull_request:
  push:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Verify producer contracts
        run: ./mvnw -B -ntp clean verify

      - name: Require stub JAR
        shell: bash
        run: |
          jar_path="$(find target -maxdepth 1 -type f -name '*-stubs.jar' -print -quit)"
          test -n "$jar_path"
          entries="$(jar tf "$jar_path")"
          [[ "$entries" == *META-INF/* ]]
          echo "Candidate stub: $jar_path"

  publish:
    needs: verify
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
          server-id: internal-releases
          server-username: MAVEN_USERNAME
          server-password: MAVEN_PASSWORD

      - name: Reverify exact commit and publish
        env:
          MAVEN_USERNAME: ${{ secrets.MAVEN_USERNAME }}
          MAVEN_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
        run: ./mvnw -B -ntp clean deploy
~~~

### Đọc ý nghĩa của workflow

- `verify` chạy cả trên PR và push; **không có thông tin xác thực để publish**.
- `publish` có `needs: verify`; nếu verify thất bại thì job publish không chạy.
- `publish` chỉ chạy khi push tới `main`; PR không được cấp đường phát hành.
- Job publish checkout lại commit kích hoạt workflow và chạy `clean deploy`, tức **tự chạy lại kiểm tra trong Maven lifecycle**, thay vì upload một JAR không rõ nguồn.
- `setup-java` cấu hình Maven server ID và lấy credentials từ secrets; ID `internal-releases` phải khớp repository được khai báo trong `distributionManagement`/settings của dự án.
- Bước `Require stub JAR` chỉ kiểm tra **có artifact**, không phải test-count. Dự án phải thêm gate xác nhận **generated producer tests thực sự chạy**, thông qua build/report phù hợp.

Ví dụ này **không bao gồm** consumer compatibility job. Nếu chính sách release yêu cầu consumer tests xanh trước khi công bố, thêm job dùng candidate stub và đặt `publish.needs` phụ thuộc cả `verify` và job consumer.

> Khi áp dụng workflow thực tế, hãy kiểm tra thêm **generated test discovery và test reports**, cấu hình credentials, quyền chạy job release và phiên bản Maven plugin. Bước kiểm tra JAR ở trên không thay thế bằng chứng rằng producer contract tests thực sự chạy.

## 11. Một điểm bảo mật của gate: PR không có quyền publish

Tại sao tách job kiểm chứng và job phát hành?

1. PR chưa được merge có thể chứa code do nhiều người đóng góp; không nên cho mặc định truy cập thông tin xác thực repository.
2. Nếu script build có thể đọc release token, một thay đổi độc hại có thể cố upload artifact chưa qua gate.
3. Trigger publish cần hạn chế cho branch/tag được bảo vệ, workflow đã được review và quyền nhỏ nhất cần thiết.
4. Artifact repository nên giới hạn quyền overwrite/deploy, đặc biệt với phiên bản release bất biến.

Các bước CI cần **fail closed**: khi không xác minh được kết quả test, không tìm thấy artifact hoặc không kiểm tra được version, thì dừng publish. Không dùng catch/ignore lỗi để “cố phát hành cho kịp”.

Có thể bổ sung environment protection, approvals, tag signing và kiểm soát provenance/SBOM tùy yêu cầu tổ chức. Đây là các lớp quản trị bổ sung, **không thay thế producer contract test**.

## 12. Stub candidate dùng trong CI không đồng nghĩa bản đã phát hành

Để kiểm tra consumer trước khi release, nhóm có thể tạo **candidate stub** ở một trong các nơi:

- Artifact tạm của CI job, chỉ dành cho các job cùng pipeline.
- Repository staging có phạm vi quyền truy cập hẹp và version duy nhất.
- Cache/workspace cô lập của test runner trong cùng pipeline.

Consumer dùng Stub Runner để chạy candidate và kiểm tra client thực.

**Nguyên tắc phân biệt:**

| Thuộc tính | Candidate trong CI | Published stub |
|---|---|---|
| Mục đích | Thử tương thích trước release | Làm hợp đồng được consumer khác tải về |
| Trạng thái producer | Có thể đang kiểm chứng, nhưng không được coi là release khi chưa đạt | Bắt buộc producer quality gate PASS |
| Phạm vi | CI/staging riêng, thời gian sống có kiểm soát | Artifact repository chính thức |
| Version | Commit/build-specific, không đè ứng viên khác | Version truy vết được, quản lý theo chính sách |
| Khả năng thay thế | Có thể dọn dẹp khi thất bại | Không nên overwrite một bản release bất biến |

Nếu consumer test dùng candidate **trước khi producer test đạt**, kết quả consumer test chỉ mang tính chẩn đoán; **không cho phép publish** dù consumer test xanh.

### Tại sao không dùng `latest`?

Giả sử consumer test dựa trên phiên bản `latest` đang trỏ tới stub hôm qua, còn producer vừa sửa contract hôm nay. Nếu test xanh, ta chưa biết consumer có tương thích với thay đổi mới không.

Ghim tọa độ hoặc ID artifact rõ ràng:

~~~text
Producer commit: a1b2c3d
Contract revision: a1b2c3d
Candidate stub:
  com.example:inventory-producer:1.1.0-rc.1:stubs

Consumer test:
  chạy Stub Runner với đúng 1.1.0-rc.1
~~~

Commit và version là ví dụ. Với `SNAPSHOT` mutable, phải có cơ chế tránh nhầm cache hoặc artifact cùng version bị cập nhật trong khi test đang chạy. Tốt hơn là dùng build ID/digest hoặc version bất biến cho từng candidate.

## 13. Stub Runner giúp bảo vệ điều gì sau producer gate?

Trong consumer, Stub Runner tải artifact theo tọa độ và chạy stub HTTP/message tương ứng. Ví dụ một test skeleton cho Checkout:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.1.0-rc.1:stubs:10000",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutInventoryContractTest {

    @Test
    void handlesStockAvailable() {
        // Gọi InventoryClient thật của Checkout, trỏ vào stub port 10000.
        // Kiểm tra client parse được sku, available, quantity
        // và quyết định nghiệp vụ cho phép đặt hàng.
    }
}
~~~

Đây là **skeleton**, không phải test chạy được ngay: cần có InventoryClient, cấu hình base URL stub và assertion. `LOCAL` giả định artifact đã có trong Maven local repository của môi trường test; trong CI có thể dùng một repository staging hoặc phương thức phân phối candidate stub phù hợp.

### Consumer test không phải bằng chứng producer test

Một consumer test xanh khi chạy Stub Runner chứng minh consumer xử lý **stub đã nạp**. Nó chưa chứng minh:

- Stub được lấy từ commit vừa review.
- Producer thật trả cùng body/status.
- Các nhánh không có contract đều hoạt động.
- Các thay đổi schema vẫn tương thích với mọi consumer cũ.

Do vậy, **gating producer test trước khi publish** vẫn là điều kiện cần; chạy consumer test trước release là lớp kiểm chứng thêm khi tổ chức yêu cầu.

## 14. Messaging stub cũng phải qua producer test

Nguyên tắc này áp dụng cả với message contract. Ví dụ Inventory phát event:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stock_changed'

    input {
        triggeredBy('emitStockChanged()')
    }

    outputMessage {
        sentTo('stock-events')
        body(
            eventType: 'StockChanged',
            sku: 'SKU-101',
            quantity: 0
        )
        headers {
            messagingContentType(applicationJson())
        }
    }
}
~~~

Generated producer test cần gọi method `emitStockChanged()` trong base test, nhận message từ destination, rồi kiểm tra payload/header. Nếu publisher thật không phát message hoặc phát `quantity: '0'` dạng string khi consumer cần number, producer test cần thất bại tương ứng.

Khi đó **không được publish stub message mới** chỉ vì nhãn `stock_changed` đã có trong artifact. Consumer dùng `StubTrigger.trigger("stock_changed")` có thể nhận event giả lập hoàn toàn đúng với DSL, trong khi producer thật chưa thực hiện đúng.

Với messaging, cần kiểm tra đặc biệt:

- Generated producer test **thực sự nhận message**, không chỉ gọi trigger method.
- Destination/binder/receiver đang quan sát đúng nơi.
- Payload và header đúng kiểu.
- Không nhận nhầm message cũ từ test khác.
- Fixture và thời gian chờ bất đồng bộ được kiểm soát.
- Stub artifact chứa **label và contract definition** cần dùng, không chỉ WireMock HTTP mapping.

Broker reliability, transaction outbox, retry và duplicate delivery vẫn cần test tích hợp thích hợp; gate về contract không tự chứng minh những tính chất đó.

## 15. Ngăn việc công bố khi test đỏ: ví dụ ba nhánh

### Nhánh A — Producer test lỗi vì sai kiểu

~~~text
Contract:
  quantity: 8         # number

Producer actual response:
  "quantity": "8"     # string

Generated producer test:
  FAIL — mismatch kiểu/giá trị tại $.quantity

Decision:
  BLOCK PUBLISH
~~~

Hành động đúng: điều tra xem producer sai schema hay contract mô tả sai thỏa thuận; không tự nới matcher để cho build xanh khi chưa trao đổi với consumer.

### Nhánh B — Không có generated producer test

~~~text
Build log:
  Build SUCCESS
  Unit tests: 74 passed
  Contract tests: 0 discovered / 0 executed

Output:
  inventory-producer-1.1.0-stubs.jar exists

Decision:
  BLOCK PUBLISH
~~~

Nguyên nhân có thể là đường dẫn DSL sai, plugin chưa chạy, test source set bị lọc, JUnit version không khớp hoặc task bị skip. **Có JAR không đủ**.

### Nhánh C — Test producer đạt và artifact đúng revision

~~~text
Commit: A
Contract tests discovered: 6
Contract tests executed: 6
Failed: 0
Skipped: 0
Stub JAR: built from commit A
JAR metadata/contracts/mappings: verified
Release authorization: approved

Decision:
  ELIGIBLE FOR PUBLISH
~~~

Nếu tổ chức yêu cầu chạy consumer compatibility tests trước release, trạng thái chỉ là **eligible** cho tới khi cổng consumer đạt. “Đủ điều kiện phát hành” không phải tự động đã publish.

## 16. Những lối đi tắt phá quality gate

| Anti-pattern | Vì sao nguy hiểm | Cách khắc phục |
|---|---|---|
| `mvn deploy -DskipTests` cho bản release | Bỏ qua kiểm chứng producer | Không skip; kiểm tra reports và generated test count |
| Script upload `target/*-stubs.jar` ngay sau `package` | JAR có thể được tạo trước khi test bắt buộc đạt | Chỉ upload sau quality gate, dùng artifact cùng revision |
| `gradle publish` không phụ thuộc contract tests | Artifact có thể publish dù `contractTest` chưa chạy | Nối task graph và kiểm tra CI dependencies |
| Publish job có `if: always()` | Vẫn chạy khi verify lỗi | Dùng điều kiện success và `needs` rõ ràng |
| Cho phép `testFailureIgnore` | Build có thể tiếp tục dù test fail | Fail build khi producer contract test thất bại |
| Job test dùng branch HEAD, publish dùng một HEAD mới | Source không đồng nhất | Checkout SHA/tag cụ thể hoặc truyền artifact bất biến |
| Dùng JAR cũ từ cache | Có artifact nhưng không phải của commit mới | Clean workspace, so version/digest |
| Reuse cùng một release version rồi overwrite | Consumer không biết mình đang chạy byte nào | Repository version bất biến |
| Chỉ kiểm tra CI màu xanh | Có thể xanh khi 0 contract tests | Bắt buộc xác nhận test discovery/execution |
| Chỉ chạy consumer tests với stub | Consumer không phát hiện producer thật sai | Chạy producer generated tests |
| Tự sửa stub mapping sau producer test | Artifact khác DSL đã kiểm chứng | Build lại và chạy gate cho artifact cuối |
| PR có quyền deploy | Rủi ro release ngoài quy trình | Bảo vệ branch/tag, dùng credentials ở job release |
| Nuốt exit code bằng script | Test fail nhưng publish vẫn chạy | Propagate failure, fail closed |
| Công bố một stub lỗi để “consumer sửa trước” | Consumer có thể nhận nhầm bản chưa được xác nhận | Chỉ chia sẻ candidate ở môi trường CI/staging được gắn nhãn rõ |

### Thận trọng với tự động retry job

Retry job CI vì lỗi hạ tầng tạm thời có thể hợp lý nếu được ghi rõ. Nhưng một test không ổn định do race condition hoặc dữ liệu dùng chung không nên được chữa bằng cách retry cho tới khi xanh rồi publish.

Chất lượng release gate phụ thuộc **kết quả có thể tái lập**, không phải xác suất một lần chạy tình cờ đạt.

## 17. Khi nào nên giữ lại candidate stub thất bại?

Một candidate stub từ PR producer test lỗi vẫn có thể hữu ích cho **debug**:

- So sánh mapping mà generator đã tạo với expected contract.
- Cho nhóm consumer nhìn thấy thay đổi schema dự kiến trước khi hoàn thiện producer.
- Chạy một test consumer thử nghiệm để phát hiện những giả định chưa được viết thành contract.

Tuy nhiên cần các điều kiện:

1. Candidate **không được đẩy lên repository phát hành** hoặc alias mà consumer production/CI chính thức dùng.
2. Metadata ghi rõ **UNVERIFIED / producer tests failed**.
3. Version hoặc build ID không trùng bản đã được phát hành.
4. Có vòng đời dọn dẹp/hết hạn phù hợp.
5. Không làm lộ bí mật qua fixtures hoặc mapping.

Mục tiêu của việc giữ candidate thất bại là **hỗ trợ phối hợp**, không phải bỏ gate.

## 18. Kiểm soát thay đổi breaking trước khi công bố

Ngay cả khi tất cả generated producer tests với hợp đồng **mới** đều xanh, API có thể đã phá vỡ consumer cũ.

Ví dụ trước đây Inventory trả:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

Hợp đồng mới đổi thành:

~~~json
{
  "sku": "SKU-101",
  "availability": "IN_STOCK",
  "units": 8
}
~~~

Nếu producer code và contract cùng đổi, producer tests có thể vẫn PASS. Nhưng Checkout phiên bản cũ vẫn đọc `available` và `quantity`, nên có nguy cơ hỏng.

Do đó, ngoài gate producer test, cần:

- Chạy consumer tests với **candidate stub đúng version**.
- Rà soát danh sách các consumer đang triển khai và field mà họ phụ thuộc.
- Có giai đoạn chuyển đổi, phiên bản API mới hoặc chính sách tương thích khi thay field/kiểu.
- Không ghi đè stub version cũ bằng artifact biểu diễn giao diện mới không tương thích.

**Producer PASS là điều kiện cần để công bố stub; consumer compatibility là câu hỏi bổ sung về mức độ an toàn khi các hệ thống đang dùng nhiều phiên bản.**

## 19. Checklist cho pipeline và người review

Trước khi cho phép phát hành stub, hãy kiểm tra:

- [ ] Contract Groovy/YAML đúng module, đúng nhánh và đúng revision.
- [ ] Plugin Spring Cloud Contract đã phát hiện contract/fixture cần thiết.
- [ ] Generated producer tests được sinh, biên dịch và **thực sự chạy**.
- [ ] Không có test bắt buộc bị skip/disable/filter ngoài chủ đích.
- [ ] Kết quả producer contract test **PASS**; có reports/log truy vết được.
- [ ] Test đi qua code producer đúng phạm vi, không chỉ gọi vào stub tự mô phỏng.
- [ ] Assertion giữ đúng status/header/body, message headers/payload và kiểu dữ liệu.
- [ ] Stub JAR chứa mapping/contract/fixture cần thiết; không rỗng và không chứa bí mật.
- [ ] JAR được tạo từ **cùng commit/version** mà producer test xác nhận.
- [ ] Job publication phụ thuộc verify và không có đường vòng upload riêng.
- [ ] Maven/Gradle build không bật `skipTests` hoặc bỏ qua `contractTest`.
- [ ] Artifact version rõ ràng; không overwrite bản release bất biến.
- [ ] Release credentials chỉ được dùng ở job/branch/tag cho phép.
- [ ] Nếu consumer tests là gate, chúng dùng đúng candidate stub qua Stub Runner và đều PASS.
- [ ] Thay đổi có nguy cơ breaking được review với consumer đang triển khai.
- [ ] Khi bất kỳ điều kiện bắt buộc nào chưa rõ, pipeline **không publish**.

## 20. Bài tập thực hành: phân tích một pipeline sai

### Đề bài

Một nhóm dùng Maven tạo stub cho Inventory Service:

~~~text
Step 1: mvn package -DskipTests
Step 2: find target -name '*-stubs.jar'
Step 3: upload JAR to remote Maven repository
Step 4: notify Checkout to update Stub Runner version
~~~

Ngày hôm sau, Checkout test dùng stub mới xanh nhưng khi triển khai thật lại lỗi deserialize vì producer trả `quantity` dưới dạng string.

Hãy trả lời:

1. Pipeline sai ở bước nào?
2. Tại sao stub tồn tại và consumer test xanh vẫn chưa chứng minh producer đúng?
3. Điều kiện tối thiểu nào phải được thêm trước bước upload?
4. Làm sao chống publish nhầm artifact cũ sau khi sửa pipeline?
5. Nếu producer test PASS nhưng consumer test với candidate FAIL, nên làm gì?

### Lời giải tham khảo

**Câu 1:** Bước 1 cố tình bỏ qua test; bước 3 upload artifact khi chưa có bằng chứng generated producer tests đạt. Đây là lỗ hổng của release gate.

**Câu 2:** Stub được sinh từ DSL và trả response mà hợp đồng mô tả, không nhất thiết phản ánh response thực của producer đang có lỗi.

**Câu 3:** Sinh/chạy generated producer tests, xác nhận test được thực thi và đạt; chỉ sau đó mới cho publish. Cần kiểm tra exit code, test reports và số generated tests.

**Câu 4:** Clean build từ commit đã xác định; lưu revision/version và checksum; dùng artifact bất biến hoặc rebuild/test lại đúng commit trong release job.

**Câu 5:** Không tự động phát hành nếu chính sách yêu cầu consumer compatibility. Điều tra xem đây là breaking change, client sai giả định hay stub matcher chưa đúng; sửa contract/producer/consumer hoặc lên kế hoạch chuyển đổi, rồi chạy lại gate.

### Bài mở rộng: thiết kế hai job

Viết sơ đồ hai job:

~~~text
verify:
  input: commit SHA
  output: tests PASS + candidate JAR + checksum
  permission: read source, no deploy secret

publish:
  dependsOn: verify
  conditions: approved main/tag + all required gates PASS
  input: same candidate JAR and checksum
  action: remote publish
  permission: limited deployment credential
~~~

**Thử nghĩ:** nếu job publish tải một JAR mới từ nhãn `latest` thay vì từ artifact verify, còn giữ được bảo đảm “đã kiểm chứng đúng artifact” không? **Không.** Khi đó không còn ràng buộc chắc chắn giữa kết quả producer test và nội dung được công bố.

## 21. Ghi nhớ và tham khảo

**Đường sinh stub và đường công bố stub phải có một cổng chất lượng rõ ràng.** Việc Spring Cloud Contract tạo WireMock mapping hoặc `*-stubs.jar` chỉ chứng minh công cụ đã xử lý DSL ở một mức nào đó, không chứng minh producer triển khai đúng hành vi. Trước khi artifact được phát hành cho consumer, CI cần xác nhận generated producer tests **được phát hiện, thực thi và đạt** trên cùng revision, rồi mới đóng gói/đưa đúng artifact vào repository.

Khi producer test xanh, vẫn nên chạy consumer tests với **candidate stub** qua Stub Runner để kiểm tra khả năng tương thích trong những tình huống mà consumer phụ thuộc. Không công bố bản chưa qua gate, không bỏ qua test vì muốn phát hành nhanh và không để `latest` hoặc cache che mất sự khác biệt giữa các phiên bản.

### Tài liệu tham khảo

- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): plugin, sinh producer tests và stub artifact.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): các task liên quan tới contract tests và stub packaging.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): cách consumer tải/chạy stub theo tọa độ/version.
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): ý nghĩa của `test`, `package`, `verify`, `install` và `deploy`.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): publication tasks và cách cấu hình publication.

**Kết luận thực hành:** hãy để hệ thống **sinh stub để kiểm thử**, nhưng chỉ **công bố stub khi producer đã chứng minh lời hứa trong hợp đồng**. Đó là ranh giới giúp consumer tin rằng stub mô phỏng một giao diện mà producer thực sự có thể cung cấp.
