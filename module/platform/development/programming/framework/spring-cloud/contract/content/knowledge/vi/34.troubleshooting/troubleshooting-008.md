# Stub artifact không tồn tại, sai classifier hoặc sai phiên bản

## Mục tiêu học tập

**Spring Cloud Contract** cho phép producer và consumer định nghĩa hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**. Producer sinh test để kiểm chứng implementation, sau đó đóng gói **stub artifact**. Consumer sử dụng **Stub Runner** để chạy client tests và kết hợp với **CI** phát hiện thay đổi API không tương thích.

Trong thực tế, câu báo lỗi **“Không tìm thấy stub”** có thể chỉ bốn sự cố khác nhau:

1. **Artifact chưa tồn tại** tại repository mà consumer đang tìm.
2. **Artifact tồn tại nhưng sai tọa độ**: `groupId`, `artifactId`, `version`, `classifier` hoặc loại file.
3. **Tải được JAR nhưng thiếu stub**: không có HTTP mappings hoặc message definitions đúng.
4. **Stub chạy nhưng request không khớp**: consumer gọi sai cổng, method, path, header hoặc body nên WireMock trả 404.

Bài thuộc chương **Chẩn đoán sự cố** và tập trung vào lỗi stub artifact không tồn tại, sai classifier hoặc sai phiên bản. Sau bài, bạn có thể:

- Đọc chính xác ID `group:artifact:version:classifier:port` của Stub Runner.
- Phân biệt contract definitions JAR, producer application JAR và producer `:stubs` JAR.
- Kiểm tra producer đã sinh test, chạy test, tạo stub và publish hay chưa.
- Xác minh tọa độ consumer dùng so với artifact thực trong Maven repository.
- Chẩn đoán `LOCAL`, `REMOTE` và `CLASSPATH`, repository URL, permission và cache.
- Kiểm tra nội dung JAR, `mappings` và `__files` thay vì dựa vào tên file.
- Phân biệt artifact resolution error với unmatched WireMock 404.
- Xây dựng CI quality gates và báo cáo lỗi có bằng chứng để tái hiện.

> **Quy tắc đầu tiên:** xác minh theo thứ tự **artifact có tồn tại → tọa độ đúng → JAR chứa stub → Stub Runner khởi động → request match mapping**. Đừng sửa assertion JSON khi lỗi nằm ở classifier hoặc repository.

## 1. Tình huống xuyên suốt: Inventory và Checkout

**Inventory Service** cung cấp:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

Response đã thống nhất:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-101","available":true,"quantity":8}
~~~

**Checkout Service** cần kiểm thử HTTP client nhưng không muốn khởi động toàn bộ Inventory. Nó tải stub bằng Stub Runner.

Giả sử các artifact liên quan là:

| Artifact | Tọa độ mẫu | Vai trò |
|---|---|---|
| **Contract definitions** | `com.example.contracts:inventory-contracts:1.6.0` | Chứa Groovy/YAML DSL, có thể được phát hành từ kho hợp đồng riêng |
| **Producer application** | `com.example:inventory-producer:2.3.0` | JAR chạy ứng dụng Inventory thật |
| **Producer stub** | `com.example:inventory-producer:2.3.0:stubs` | JAR mappings và fixture cho consumer test |

Các file có thể tương ứng:

~~~text
inventory-contracts-1.6.0.jar
inventory-producer-2.3.0.jar
inventory-producer-2.3.0-stubs.jar
~~~

**Chỉ file cuối là producer stub JAR** ở ví dụ này. Một application JAR có cùng group/artifact/version nhưng **không có classifier** không thể tự thay thế stub JAR.

### Stub Runner trong consumer

Ví dụ JUnit 5 + Spring Boot:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.3.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.invalid/repository/verified-stubs"
)
class CheckoutInventoryClientTest {

    @StubRunnerPort("inventory-producer")
    int inventoryStubPort;

    @Test
    void usesInventoryStub() {
        // Cấu hình HTTP client thật của Checkout:
        // http://localhost:<inventoryStubPort>
        // Gửi GET /api/inventory/SKU-101 rồi assert response.
    }
}
~~~

Đây là **skeleton cấu hình**, không phải test đầy đủ; dự án cần dependencies, HTTP client và assertions. `example.invalid` là URL placeholder không tồn tại.

Nếu consumer fail ngay khi Spring test context khởi tạo vì không resolve được `inventory-producer:2.3.0:stubs`, sửa JSONPath trong method test sẽ không giải quyết nguyên nhân.

## 2. Giải mã Stub Runner ID

Một ID thông dụng có dạng:

~~~text
groupId:artifactId:version:classifier:port
~~~

Ví dụ:

~~~text
com.example:inventory-producer:2.3.0:stubs:0
    |            |          |    |   |
    |            |          |    |   +-- Port=0: chạy stub ở cổng động
    |            |          |    +------ Classifier: stubs
    |            |          +----------- Producer stub version
    |            +---------------------- Maven artifactId
    +----------------------------------- Maven groupId
~~~

| Thành phần | Ví dụ | Lỗi phổ biến |
|---|---|---|
| `groupId` | `com.example` | Nhầm với group của contract definitions |
| `artifactId` | `inventory-producer` | Nhầm tên service hiển thị với artifactId Maven |
| `version` | `2.3.0` | Dùng version mới chưa publish hoặc version cũ |
| `classifier` | `stubs` | Bỏ classifier khiến resolver tìm main JAR hoặc artifact khác |
| `port` | `0` | Consumer hiểu nhầm cổng động là URL localhost:0 |

**Cẩn thận với các định dạng tọa độ khác nhau:**

- Stub Runner ID: `group:artifact:version:classifier:port`.
- Maven dependency plugin CLI: `group:artifact:version:packaging:classifier`, ví dụ `com.example:inventory-producer:2.3.0:jar:stubs`.

Không đưa nguyên chuỗi `...:stubs:0` vào lệnh Maven dependency rồi nghĩ `0` là port mà Maven hiểu được.

### Dùng cổng động đúng cách

`:0` khiến Stub Runner tự chọn cổng có sẵn. Client phải lấy cổng runtime qua `@StubRunnerPort` hoặc `StubFinder`, không hardcode `http://localhost:0` hay `localhost:8080`.

Nếu consumer báo `Connection refused` vì gọi sai cổng, đó là **lỗi client routing**, không chứng minh artifact chưa tồn tại.

### Phiên bản động có nên dùng?

Các cơ chế resolver/phiên bản có thể hỗ trợ dynamic versions (ví dụ `+`). Nhưng CI yêu cầu tái lập nên ưu tiên **version cụ thể** và, khi cần, lưu digest JAR. Không đổi sang bản mới nhất chỉ để né lỗi.

## 3. Cây quyết định phân loại lỗi

~~~mermaid
flowchart TD
    A["Consumer báo không thấy stub"] --> B{"Artifact resolve được?"}
    B -->|Không| C["Xác minh group/artifact/version/classifier"]
    C --> D["Kiểm repository root, mode, auth, publish"]
    B -->|Có| E{"JAR chứa mappings cần thiết?"}
    E -->|Không| F["Kiểm packaging, META-INF, __files, filters"]
    E -->|Có| G{"Stub Runner đã mở port?"}
    G -->|Không| H["Kiểm bootstrap/config/port conflict"]
    G -->|Có| I{"Request match WireMock mapping?"}
    I -->|Không| J["Kiểm URL, method, query, header, body"]
    I -->|Có| K{"Consumer assertions PASS?"}
    K -->|Không| L["Kiểm contract expectation và phiên bản"]
    K -->|Có| M["Ghi version/digest + reports"]
~~~

| Triệu chứng | Tầng nghi ngờ trước tiên | Chưa nên làm |
|---|---|---|
| `Could not resolve artifact` | Repository/tọa độ/publish | Sửa JSONPath response |
| HTTP 401/403 từ repository | Credentials/quyền đọc | Đổi classifier ngẫu nhiên |
| HTTP 404 khi tải `-stubs.jar` | File/tọa độ không có | Tăng timeout của HTTP client |
| JAR tải xong nhưng `no mappings` | Generation/packaging | Kết luận Stub Runner đã chạy |
| Stub Runner không bind được port | Startup/configuration | Sửa contract body |
| WireMock HTTP 404 sau khi stub khởi động | Request không match | Giả rằng artifact chưa tồn tại |
| Consumer kết nối nhầm port | Client base URL | Publish lại JAR |
| Stub mapping match nhưng response assert fail | DSL, implementation hoặc artifact cũ | Dùng `latest` để tìm bản xanh |

**Hai loại 404 khác nhau:** HTTP 404 khi resolver cố tải một file trên Maven repository và HTTP 404 do WireMock trả khi request không khớp mapping. Hãy ghi rõ **URL nào trả 404**.

## 4. Artifact được lưu ở đâu trong Maven repository?

Repository tương thích Maven sắp xếp artifact theo:

~~~text
<repository-root>/
  <group-id-as-folders>/
    <artifact-id>/
      <version>/
        <artifact-id>-<version>-<classifier>.<extension>
~~~

Ví dụ:

~~~text
https://repo.example.invalid/repository/verified-stubs/
└── com/
    └── example/
        └── inventory-producer/
            └── 2.3.0/
                ├── inventory-producer-2.3.0.pom
                ├── inventory-producer-2.3.0.jar
                └── inventory-producer-2.3.0-stubs.jar
~~~

Đường dẫn tương đối tới stub JAR:

~~~text
com/example/inventory-producer/2.3.0/inventory-producer-2.3.0-stubs.jar
~~~

`repositoryRoot` của Stub Runner cần trỏ vào **gốc repository** `.../repository/verified-stubs`, không trỏ vào `.../2.3.0` hoặc thẳng file JAR.

### Trình tự đối chiếu

1. ID consumer yêu cầu đúng group/artifact/version/classifier chưa?
2. Repository tương ứng có file `*-stubs.jar` không?
3. Repository có POM/metadata mà resolver cần không?
4. Response khi tải bằng quyền của CI là 200, 401, 403, 404 hay 5xx?
5. File thực sự tải xuống có đúng JAR không, hay trang đăng nhập HTML?
6. `jar tf` có liệt kê mapping của producer này không?
7. Stub Runner logs ghi artifact/port nào đã tải và chạy?

### Với SNAPSHOT

Maven snapshots có thể được lưu thành **timestamped snapshots** cùng `maven-metadata.xml`, ví dụ path directory `2.3.1-SNAPSHOT` nhưng filename chứa timestamp/build number.

Đừng tự xây URL tới `inventory-producer-2.3.1-SNAPSHOT-stubs.jar` và kết luận không tồn tại nếu repository dùng timestamped filename. Hãy dùng Maven/Stub Runner resolver và đọc metadata/log download.

## 5. Không nhầm contract definitions và producer stubs

Sai lầm điển hình:

~~~text
Producer tải contract definitions:
  com.example.contracts:inventory-contracts:1.6.0

Consumer Stub Runner cấu hình:
  com.example.contracts:inventory-contracts:1.6.0:stubs:0
~~~

**Không đúng mục tiêu:** contract definitions JAR chứa Groovy/YAML DSL để **producer sinh tests**. Consumer cần stub JAR từ **producer đã verify**, ví dụ:

~~~text
Producer code:
  com.example:inventory-producer:2.3.0

Producer generated contract tests:
  PASS

Stub artifact:
  com.example:inventory-producer:2.3.0:stubs

Checkout Stub Runner ID:
  com.example:inventory-producer:2.3.0:stubs:0
~~~

Không có quy tắc Spring Cloud Contract bắt version contract JAR `1.6.0` phải bằng version producer `2.3.0`. CI nên ghi liên kết contract revision, producer revision và verified stub artifact.

**Có contract JAR trên Nexus không chứng minh producer đã publish stub JAR.**

## 6. Producer phải sinh và phát hành stub thật

Chuỗi cần xác minh:

~~~text
Groovy/YAML DSL
    |
    v
Generate producer tests
    |
    v
Run against real producer implementation
    |
    v
PASS
    |
    v
Generate HTTP mappings / message definitions
    |
    v
Package stubs JAR (classifier stubs)
    |
    v
Install/publish to repository
~~~

Tạo file và đưa file vào repository là **hai hành động riêng**.

### Maven producer

Với Maven producer đã cấu hình Spring Cloud Contract Maven plugin:

~~~bash
# Chạy verification theo lifecycle và cấu hình hiện có.
./mvnw -B -ntp clean verify

# Install artifacts vào Maven local repository theo plugin attachment.
./mvnw -B -ntp install
~~~

Không dùng `-DskipTests` hoặc `-Dmaven.test.skip=true` để ép build stub: producer tests chưa chạy thì artifact không thể được coi là verified.

Nếu output dự kiến:

~~~text
target/inventory-producer-2.3.0.jar
target/inventory-producer-2.3.0-stubs.jar
~~~

mà chỉ có main application JAR, hãy kiểm tra contract discovery, plugin configuration, stub generation và việc **attach artifact**. Tên file có thể thay đổi theo Maven finalName/plugin version.

### Gradle producer

Với Gradle module có Spring Cloud Contract plugin hiện đại:

~~~bash
./gradlew :inventory-producer:tasks --all
./gradlew :inventory-producer:contractTest
./gradlew :inventory-producer:verifierStubsJar
~~~

Thông thường artifact xuất hiện trong vùng:

~~~text
inventory-producer/build/libs/
~~~

`verifierStubsJar` chủ yếu **tạo/đóng gói** stub; nó không có nghĩa artifact đã được publish sang Maven repository consumer đang dùng. Cần cấu hình publication/upload và kiểm tra log publish riêng.

### Các câu hỏi quan trọng

- Producer có phát hiện đúng DSL và sinh **khác 0 tests** không?
- Generated producer tests đã thực thi và PASS, hay bị skip?
- Artifact có classifier `stubs` trong metadata/publication thực tế không?
- Có logs chỉ ra install/publish đã thành công không?
- Consumer yêu cầu đúng version vừa publish hay một version khác?
- Artifact được build từ **cùng revision** đã producer verify không?

**Đừng bắt đầu bằng cách sửa consumer nếu producer chưa xuất bản stub.**


## 7. Mở stub JAR để xác minh nội dung

Tên file `inventory-producer-2.3.0-stubs.jar` **không bảo đảm** nó chứa đúng mappings. Artifact có thể rỗng, đóng gói sai layout hoặc chứa nhầm application classes.

Sử dụng công cụ JDK:

~~~bash
jar tf inventory-producer-2.3.0-stubs.jar
~~~

Với một HTTP stub JAR theo convention Spring Cloud Contract, kết quả có thể gồm:

~~~text
META-INF/
META-INF/MANIFEST.MF
META-INF/com.example/inventory-producer/2.3.0/
META-INF/com.example/inventory-producer/2.3.0/contracts/
META-INF/com.example/inventory-producer/2.3.0/mappings/
META-INF/com.example/inventory-producer/2.3.0/mappings/stockAvailable.json
~~~

Đây là **layout minh họa**: plugin version, path/consumer-specific configuration có thể khác. Cần inspect JAR thật và log Stub Runner đang sử dụng.

### Dấu hiệu một JAR sai nội dung

~~~text
Downloaded:
  inventory-producer-2.3.0-stubs.jar

Archive:
  META-INF/MANIFEST.MF
  BOOT-INF/classes/application.properties
  BOOT-INF/lib/...
~~~

Nếu JAR trông như Spring Boot fat JAR nhưng không có mappings/contract definitions, có thể pipeline **đã publish application JAR dưới classifier stubs**. Stub Runner không tự lấy controller class làm WireMock stub.

Một JAR khác có thể chứa `mappings` nhưng hoàn toàn không có mapping `GET /api/inventory/SKU-101` vì:

- Contract DSL chưa được generator phát hiện.
- Producer không cấu hình đúng nguồn Groovy/YAML DSL.
- `contractsPath` hoặc `includedFiles`/`ignoredFiles` loại file.
- Artifact thuộc consumer khác khi bật `stubs-per-consumer`.
- Artifact được đóng gói từ revision cũ.
- File mapping không được đưa vào JAR do cấu hình copy/package.

**Cách sửa:** sửa bước tạo/đóng gói ở producer, xác nhận generated contract tests và phát hành artifact mới đúng version; không tự thêm một JSON mapping không qua producer verification vào artifact đã công bố.

### Nếu mapping tham chiếu file ngoài

WireMock mapping có thể dùng:

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-101"
  },
  "response": {
    "status": 200,
    "bodyFileName": "stock-available.json",
    "headers": {
      "Content-Type": "application/json"
    }
  }
}
~~~

Khi đó stub artifact phải có body file tương ứng trong vùng `__files` theo quy ước/đường dẫn mà WireMock và Spring Cloud Contract packaging sử dụng. Nếu thiếu, artifact resolve và server có thể khởi động nhưng response request sẽ fail ở runtime.

**Không suy từ “có mapping JSON” rằng file response bên ngoài cũng có.** Phải kiểm tra cả mapping lẫn fixtures được tham chiếu.

## 8. Sai classifier: main JAR có nhưng stubs JAR không

Tình huống điển hình:

~~~text
Maven repository contains:
  inventory-producer-2.3.0.pom
  inventory-producer-2.3.0.jar

Maven repository DOES NOT contain:
  inventory-producer-2.3.0-stubs.jar
~~~

Consumer yêu cầu:

~~~text
com.example:inventory-producer:2.3.0:stubs:0
~~~

Artifact resolver không thể tìm thấy **classifier stubs** chỉ nhờ main JAR tồn tại.

### Bảng phân biệt

| File | Classifier | Là artifact consumer cần? |
|---|---|---|
| `inventory-producer-2.3.0.jar` | Không có | Không, là application artifact |
| `inventory-producer-2.3.0-stubs.jar` | `stubs` | **Có**, cho Stub Runner convention này |
| `inventory-producer-2.3.0-tests.jar` | `tests` | Không, test classes JAR không mặc nhiên chứa stub mappings |
| `inventory-producer-2.3.0-sources.jar` | `sources` | Không, source artifact |
| `inventory-contracts-1.6.0.jar` | Không có; artifact khác | Không, contract definition artifact |

**Classifier là một phần của tọa độ artifact**, không phải tên folder tùy ý. Việc đặt `-stubs` trong filename trước khi upload bằng tay chưa chắc tạo Maven metadata đúng nếu publisher gắn artifact ở coordinate khác.

### Gradle: liên kết verifierStubsJar với publication

Một pattern `maven-publish` minh họa cho producer Gradle đã áp dụng Spring Cloud Contract plugin:

~~~groovy
plugins {
    id 'java'
    id 'maven-publish'
    // Spring Cloud Contract plugin và version cần được cấu hình
    // theo BOM/toolchain thực tế của dự án.
}

group = 'com.example'
version = '2.3.0'

publishing {
    publications {
        verifiedStubs(MavenPublication) {
            groupId = 'com.example'
            artifactId = 'inventory-producer'
            version = project.version.toString()

            artifact(tasks.named('verifierStubsJar'))
        }
    }
}
~~~

**Đoạn code là ví dụ publication, không phải build.gradle hoàn chỉnh.** Task `verifierStubsJar` phải tồn tại và cấu hình output classifier đúng trong Spring Cloud Contract plugin version đang dùng. `maven-publish` nhận artifact từ task, nhưng **vẫn cần repository upload** và một release gate bảo đảm producer contract tests đã PASS.

Không mặc định một plugin đã tự sinh task `publishVerifiedStubsPublicationToMavenLocal` nếu publication chưa được tạo. Hãy dùng `./gradlew tasks --all` và xem output task thực.

### Maven: attached artifact có classifier stubs không?

Trong Maven producer dùng Spring Cloud Contract Maven plugin, cần kiểm tra:

- Plugin đã chạy các mục tiêu sinh stub theo lifecycle?
- Stub JAR được **attach** với classifier `stubs`?
- `install`/`deploy` có mang theo attached artifact không?
- Có profile hoặc parent POM nào disable contract plugin?
- Đã xác minh thực tế thư mục target và Maven local/remote chưa?

Nếu main JAR publish được nhưng `stubs` JAR không, nguyên nhân thường nằm ở **plugin goal, attached artifact hoặc deploy/publish configuration**, không phải quyền đọc của consumer.

### Không sửa bằng cách đổi consumer classifier thành rỗng

Bỏ `stubs` để resolver tải được main JAR thường chỉ chuyển lỗi sang giai đoạn **không tìm thấy mappings**. Cần sửa **bản được publish**, không hạ kỳ vọng đối với artifact type.

## 9. LOCAL: JAR phải thật sự có trong Maven local repository

Stub Runner `LOCAL` tìm artifact theo cơ chế Maven local repository của môi trường chạy test.

Ví dụ:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.3.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

Đối với thiết lập Maven mặc định, đường dẫn có thể là:

~~~text
~/.m2/repository/com/example/inventory-producer/2.3.0/
  inventory-producer-2.3.0.pom
  inventory-producer-2.3.0.jar
  inventory-producer-2.3.0-stubs.jar
~~~

Trên Windows, local Maven repository mặc định thường nằm dưới thư mục người dùng tương ứng với `.m2/repository`. Nếu Maven `settings.xml` thay `localRepository`, vị trí thực có thể khác.

### Hai câu hỏi quan trọng

**JAR có trong `target/` hoặc `build/libs/` đã đủ chưa?**

**Chưa.** File output của producer build không tự xuất hiện ở Maven local repository theo đúng tọa độ mà Stub Runner `LOCAL` giải quyết.

**Consumer đang chạy trên cùng máy/container với producer build không?**

Nếu producer chạy tại job A và consumer chạy tại job B với filesystem riêng, `LOCAL` của job B **không nhìn thấy Maven local của job A**. Cần install/publish vào môi trường consumer hoặc dùng `REMOTE` với repository có thể truy cập chung.

### Maven: cài stub vào local

~~~bash
# Tại producer đã cấu hình plugin attach stubs:
./mvnw -B -ntp clean install
~~~

Sau lệnh, **kiểm tra thực tế file `-stubs.jar`** dưới Maven local repository. Nếu không có, xem plugin attachment, không kết luận rằng `install` luôn xuất bản stub theo mọi cấu hình.

### Gradle: publish đúng publication vào Maven local

Khi đã cấu hình `maven-publish` với publication stub:

~~~bash
./gradlew :inventory-producer:tasks --all

# Tên task phụ thuộc publication tên gì trong build.gradle:
./gradlew :inventory-producer:publishVerifiedStubsPublicationToMavenLocal
~~~

Sau đó kiểm tra file ở Maven local và thử consumer test `LOCAL`.

**Phân biệt:** `mavenLocal()` trong một khối Gradle repositories chỉ nói Gradle **có thể đọc** Maven local. Nó **không tự ghi artifact** vào Maven local.

### Maven local cache không phải nguồn tin tuyệt đối

Một file ở `~/.m2` có thể là:

- Stub của commit cũ cùng SNAPSHOT version.
- Artifact install thủ công sai classifier.
- Artifact do project khác publish vào cùng tọa độ.
- Main JAR bị đặt nhầm tên.
- Metadata chưa đồng bộ.

Kiểm tra filename, JAR entries, version và, khi cần, digest trước khi kết luận bản local phù hợp.

## 10. REMOTE: repositoryRoot phải trỏ vào nguồn đúng

Cấu hình `REMOTE`:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.3.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.invalid/repository/verified-stubs"
)
~~~

Từ `repositoryRoot`, resolver giải quyết Maven coordinates. URL này **không phải**:

- Base URL của producer production như `https://inventory.example.invalid`.
- Endpoint HTTP mà consumer client sẽ gọi.
- Đường dẫn đến file Groovy DSL trong Git.
- Đường dẫn trực tiếp đến `-stubs.jar`.
- URL của contract definition repository, trừ khi tổ chức chủ động lưu cả loại artifact ở đó.

### Phân biệt các trạng thái HTTP từ registry

| Kết quả | Ý nghĩa thường gặp | Cách xử lý |
|---|---|---|
| **200** trả JAR đúng | File có thể tải được | Xem nội dung, checksum, version |
| **200** trả HTML trang login | Redirect/proxy auth không đúng | Xem Content-Type, redirect và auth |
| **401** | Chưa xác thực hoặc token lỗi | Kiểm tra credentials của CI |
| **403** | Có identity nhưng thiếu quyền read | Kiểm tra repository ACL/tenant |
| **404** | Artifact/path không có hoặc bị che do auth policy | Xác minh metadata, tọa độ và quyền |
| **429** | Registry rate-limited | Retry có kiểm soát, không sửa contract |
| **5xx** | Repository/proxy/network lỗi | Kiểm tra trạng thái server và hệ thống cache |
| **TLS/certificate error** | CA/proxy/truststore không đúng | Cấu hình trust đúng, không tắt TLS validation |

Không commit token/password vào `@AutoConfigureStubRunner`, YAML cấu hình hoặc repository URL. Sử dụng secret management và cơ chế resolver/credentials được phiên bản Stub Runner hỗ trợ.

### Một kho Maven có nhiều repository logic

Ví dụ Artifactory/Nexus có:

~~~text
repository/maven-releases/
repository/maven-snapshots/
repository/verified-stubs/
repository/contract-definitions/
~~~

Producer có thể publish stub vào `verified-stubs` nhưng Checkout lại trỏ `maven-releases`. Hai repo ở cùng máy chủ **không có nghĩa cùng artifact**.

Chẩn đoán cần ghi rõ **URL root thực sự consumer đã dùng**, không chỉ “Nexus của công ty”.

### Tài khoản dev tải được nhưng CI không tải được

Có thể vì:

- Dev có Maven settings credentials, CI không có.
- Dev có VPN/internal DNS, CI runner ở network khác.
- Dev đang dùng Maven local cache dù nghĩ là remote.
- CI gặp proxy/certificate policy khác.
- Consumer pipeline lấy nhầm environment variable repositoryRoot.
- CI dùng version chưa được promoted sang repository công bố.

**Cách xác minh:** thử giải quyết đúng tọa độ **trong cùng environment/identity** mà consumer CI sử dụng; không suy từ laptop của developer.

## 11. CLASSPATH: artifact có trong test runtime classpath

Một số cấu hình Stub Runner hỗ trợ mode `CLASSPATH`, đọc stubs từ classpath test thay vì tải Maven remote mỗi lần.

Ví dụ ý tưởng:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.3.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.CLASSPATH
)
~~~

Để mode này hoạt động, stub artifact/resources phải được **đưa thật vào test runtime classpath** theo cấu trúc mà phiên bản Stub Runner nhận diện.

Một Maven test dependency minh họa:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>inventory-producer</artifactId>
    <version>2.3.0</version>
    <classifier>stubs</classifier>
    <type>jar</type>
    <scope>test</scope>
</dependency>
~~~

**Không đồng nhất CLASSPATH với LOCAL.** Một JAR nằm ở `~/.m2` chỉ để Maven resolve chưa chứng minh nó có trên runtime classpath. Cần xem effective test dependencies và JAR entries.

Một số cơ chế CLASSPATH ở phiên bản cụ thể cũng có convention cho việc quét resource; hãy kiểm tra tài liệu plugin version đang dùng. Nếu job chạy trong IDE có test classpath khác CI, kết quả cũng có thể khác.

### Chọn mode dựa vào mục tiêu

| Mode | Nguồn chính | Dùng khi | Lỗi thường gặp |
|---|---|---|---|
| `LOCAL` | Maven local repository | Dev tích hợp nhiều module, thử stub chưa remote publish | Không install hoặc sai `~/.m2` |
| `REMOTE` | Maven-compatible repository | Consumer CI/release cần stub artifact dùng chung | Sai URL, credentials, version, classifier |
| `CLASSPATH` | Test runtime classpath | Stub được đưa vào test dependencies/resources | JAR không ở classpath hoặc layout không đúng |

**Các mode này là lựa chọn nguồn**, không thay đổi requirement rằng stub phải chứa mappings/definitions hợp lệ.

## 12. Sai version: producer và consumer chưa dùng cùng artifact

Ví dụ:

~~~text
Producer release:
  inventory-producer 2.3.1
  inventory-producer 2.3.1:stubs

Checkout consumer:
  ids = com.example:inventory-producer:2.3.0:stubs:0
~~~

Checkout có thể vẫn PASS nhưng chỉ chứng minh tương thích với stub `2.3.0`. Nó **không xác nhận API của 2.3.1**.

Một tình huống khác:

~~~text
Checkout requests:
  inventory-producer:2.3.2:stubs

Repository contains:
  2.3.0:stubs
  2.3.1:stubs

Producer has not released:
  2.3.2:stubs
~~~

Kết quả “artifact not found” là đúng: consumer yêu cầu **version chưa tồn tại**.

### Các nguyên nhân lệch version

- Consumer cập nhật constant trước khi producer publish.
- Producer chỉ publish application version mới, quên stub classifier.
- CI build candidate với `-SNAPSHOT` nhưng consumer dùng release version.
- Gradle `project.version` ở subproject khác root version.
- Maven parent POM khai báo revision/property khác artifact publish.
- Tag Git không tương ứng version đã install/deploy.
- Maven/Gradle cache giữ artifact cũ cùng version mutable.
- Producer build từ branch A, publish từ branch B.

### Quy tắc chẩn đoán

Không chỉ so string `2.3.0` trong `build.gradle`/`pom.xml`. Phải kiểm tra **artifact đã publish thực tế**: tọa độ, version, classifier, digest, thời điểm publish, source revision, test reports.

### SNAPSHOT và release

- `2.3.1-SNAPSHOT` phù hợp development nhưng có thể thay đổi bytes cùng logical version.
- `2.3.1` release nên bất biến; không overwrite để “sửa artifact” mà không tăng version hoặc thực hiện chính sách rollback được duyệt.
- Consumer CI compatibility gate nên ghim candidate version/digest chính xác.
- Khi dùng Maven snapshots, resolver metadata/cache có thể khiến hai runner nhận bytes khác nhau.

**Không đề xuất “xóa hết cache trên mọi máy” như giải pháp lâu dài.** Cần versioning, immutability và input/provenance rõ.

## 13. GroupId, artifactId và version trong multi-module build

Trong multi-module project, tên module không nhất thiết là Maven artifactId.

Ví dụ Gradle:

~~~text
project root:
  :services:inventory
  :services:checkout

Maven publication configured:
  groupId = com.example.platform
  artifactId = inventory-api
  version = 3.0.0
~~~

Nếu Checkout Stub Runner dùng:

~~~text
com.example:inventory:3.0.0:stubs:0
~~~

thì resolver tìm **sai group/artifact** dù Gradle task `:services:inventory:verifierStubsJar` đã chạy thành công.

Tọa độ đúng theo publication minh họa:

~~~text
com.example.platform:inventory-api:3.0.0:stubs:0
~~~

### Cần xem những chỗ nào?

**Maven:**

- `<groupId>` và `<artifactId>` trong POM hiệu lực.
- Parent POM và các property version, `revision`, profile.
- Maven deploy/install logs với attached stub artifact.
- POM và artifact files đã được publish lên repository.

**Gradle:**

- `project.group` và `project.version` ở **subproject**.
- `publishing.publications` có override `groupId`/`artifactId`/`version` không.
- `verifierStubsJar` có classifier/output gì.
- Task publish chính xác (có thể khác `publish` chung).
- Repository mà publication thực sự upload đến.

### Service name không quyết định coordinates

Một ứng dụng có `spring.application.name=inventory-service` nhưng artifactId là `inventory-api`. Stub Runner resolver sẽ theo **artifact coordinates**, không tự đổi artifactId dựa vào Spring application name.

`@StubRunnerPort` cũng cần chỉ đúng stub ID/artifact được khởi chạy. Cách consumer lấy port và cách Maven tìm artifact là hai bước liên quan nhưng không thay thế nhau.

## 14. Artifact đúng nhưng mappings bị lọc hoặc trùng

Có lúc consumer đã tải đúng `inventory-producer-2.3.0-stubs.jar` nhưng startup báo không có stub phù hợp. Nguyên nhân có thể là **nội dung hoặc bộ lọc**, không phải bản thân classifier.

### Contract được đặt sai nguồn

Ví dụ DSL thực nằm trong:

~~~text
shared-contracts.jar:
  com/example/inventory-producer/checkout/stockAvailable.groovy
~~~

nhưng producer cấu hình `contractsPath` tới:

~~~text
com/example/contracts/shared-contracts
~~~

Khi đó producer có thể tải contract definition artifact thành công nhưng không discover DSL. Kết quả là stub artifact rỗng, thiếu mapping hoặc pipeline không sinh tests.

**Cách sửa:** align `contractsPath` với path bên trong contract JAR; bật fail-on-no-contracts theo plugin version và kiểm tra test count.

### Stubs per consumer

Nếu dùng **stubs-per-consumer**, artifact/Stub Runner có thể tổ chức hoặc lọc mappings theo consumer identity. Một consumer khai báo sai tên hoặc folder có thể không nhận mapping của mình dù JAR không rỗng.

Cần kiểm tra:

1. Có dùng stubs-per-consumer ở producer không?
2. Cấu trúc thư mục contract là gì?
3. Consumer name dùng trong Stub Runner là gì?
4. Generated mappings nằm ở folder nào?
5. File mapping cho Checkout thực sự được chọn khi Stub Runner khởi động không?

Không chỉ nhìn thấy `mappings/` là đủ; phải tìm **mapping của tương tác cần test**.

### Nhiều mapping trùng điều kiện

Nếu hai mapping cùng match:

~~~text
GET /api/inventory/SKU-101
~~~

nhưng trả response khác nhau, thứ tự/priority có thể ảnh hưởng stub được dùng. Đây là vấn đề **mapping ambiguity**, khác lỗi “artifact không tồn tại”.

Để có test tin cậy, mỗi tình huống cần request matcher phân biệt rõ, hoặc thiết kế scenario/priority có chủ đích, và kiểm tra mapping runtime thực tế.


## 15. Artifact tải được nhưng Stub Runner không mở cổng

Đây là bước sau khi đã xác nhận artifact và JAR nội dung đúng. Stub Runner còn phải giải nén/stage stub files và khởi động WireMock HTTP server hoặc cấu hình messaging stubs phù hợp.

Các nguyên nhân thường gặp:

- Port cố định đã bị process khác sử dụng.
- Cấu hình Stub Runner không được nạp vào Spring test context.
- `@AutoConfigureStubRunner` không có trên test/config đúng.
- Có lỗi khi load JSON mapping hoặc body file.
- Dependency WireMock/Stub Runner không tương thích với Spring Boot/Cloud version đang dùng.
- Test dùng `@StubRunnerPort` sai tên artifact ID hoặc chưa chạy server.
- Maven artifact resolve thành công nhưng stub contents không theo layout resolver chờ đợi.
- Sử dụng mode/phiên bản plugin có khác biệt về cách tìm mappings.
- Resource conflict giữa nhiều Stub Runner instances trên cùng port.

### Phân biệt startup fail với request fail

**Startup fail:**

~~~text
Spring test context fails before the test method
Reason: stub download / mapping load / server port bind
~~~

**Runtime request fail:**

~~~text
Stub Runner reports a listening HTTP port
Consumer test makes a request
WireMock responds 404 unmatched request
~~~

Đây là hai giai đoạn khác nhau. Khi stub chưa khởi động, không có ý nghĩa gì khi so sánh response schema.

### Cách xác minh

1. Xem log Stub Runner tải artifact nào, có extract mappings không.
2. Kiểm tra test context configuration và phiên bản dependency.
3. Xác định cổng được Stub Runner cấp.
4. Với cổng cố định, kiểm tra có service khác bind port không.
5. Mở danh sách mapping loaded/unmatched request journal nếu test server cho phép.
6. Nếu mapping load fail, xem JSON syntax/body file paths.
7. Nếu lỗi dependency, kiểm tra Spring Boot/Cloud/Contract BOM và dependency graph.

Đừng chỉ thay port theo kiểu thử từng số; ưu tiên `:0` để cấp cổng động cho parallel tests, rồi lấy cổng tại runtime.

## 16. WireMock 404: không được nhầm với artifact 404

Đây là một trong những lỗi gây nhầm lẫn nhất.

**Lỗi Maven artifact 404** xảy ra khi resolver cố tải:

~~~text
.../com/example/inventory-producer/2.3.0/
inventory-producer-2.3.0-stubs.jar
~~~

**Lỗi WireMock 404** xảy ra khi HTTP client gọi:

~~~http
GET /api/inventory/SKU-102 HTTP/1.1
Host: localhost:<stub-runner-port>
~~~

trong khi Stub Runner chỉ có mapping:

~~~http
GET /api/inventory/SKU-101
~~~

WireMock có thể trả 404 mặc định vì **không có mapping match request**.

### Mapping minh họa

~~~json
{
  "request": {
    "method": "GET",
    "url": "/api/inventory/SKU-101",
    "headers": {
      "Accept": { "contains": "application/json" }
    }
  },
  "response": {
    "status": 200,
    "headers": { "Content-Type": "application/json" },
    "jsonBody": {
      "sku": "SKU-101",
      "available": true,
      "quantity": 8
    }
  }
}
~~~

Đây là **WireMock mapping minh họa**, không khẳng định Spring Cloud Contract generator sẽ xuất chính xác từng key/ordering như vậy.

Request bị mismatch khi:

- Dùng `POST` thay vì `GET`.
- URL thiếu `/api` hoặc dùng SKU khác.
- Query parameter có matcher mà client không gửi.
- Header `Accept`/`Content-Type` không đúng hoặc giá trị khác.
- JSON body thiếu field, sai kiểu number/string, thứ tự hay encoding.
- Consumer gọi vào đúng hostname nhưng **cổng của service khác**.
- Consumer load stub artifact version cũ chưa chứa mapping mới.

### Đừng biến unmatched 404 thành test xanh

Nếu consumer test nhánh lỗi chỉ assert:

~~~java
assertThat(status).isEqualTo(404);
~~~

thì một URL typo có thể cho kết quả xanh dù **không match business 404 stub**.

Một contract lỗi nghiệp vụ cần status **và** error body/code có nghĩa:

~~~json
{
  "code": "SKU_NOT_FOUND",
  "message": "SKU does not exist"
}
~~~

Consumer test nên assert `code=SKU_NOT_FOUND` và xác minh request thực tế được WireMock mapping nhận đúng.

### Quy trình debug request mismatch

1. Xác nhận Stub Runner có listening port thật.
2. Ghi method, path, query, headers và body mà **client của Checkout thật** đã gửi.
3. Xem matched/unmatched requests của WireMock test server.
4. Mở mapping JSON bên trong artifact vừa tải.
5. Đối chiếu từng điều kiện request matcher.
6. Nếu contract đúng mà client sai, sửa consumer.
7. Nếu consumer request hợp lệ nhưng mapping quá chặt/sai, sửa Groovy/YAML DSL và để producer verify lại.
8. Không sửa mapping JSON được sinh bằng tay ở artifact đang phát hành; sửa nguồn và rebuild.

## 17. Không tìm thấy message stub khác lỗi WireMock HTTP

Spring Cloud Contract không chỉ hỗ trợ HTTP. Producer có thể phát message và consumer dùng Stub Runner/StubTrigger để nhận event theo **label**.

Một Groovy messaging contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'stock_changed'

    input {
        triggeredBy('publishStockChanged()')
    }

    outputMessage {
        sentTo('inventory-events')
        body(
            eventType: 'StockChanged',
            sku: 'SKU-101',
            quantity: 8
        )
        headers {
            messagingContentType(applicationJson())
        }
    }
}
~~~

Consumer có thể gọi `StubTrigger.trigger("stock_changed")` **khi messaging Stub Runner đã được cấu hình với binder/adapter tương ứng**. Test handler ở consumer phải chờ xử lý event và assert kết quả.

### Những lỗi cần tách

| Triệu chứng | Nơi nghi ngờ |
|---|---|
| Không tải được `:stubs` JAR | Artifact coordinate/repository giống HTTP case |
| Tải được JAR nhưng thiếu label `stock_changed` | Contract/message stub contents, lọc consumer |
| Có label nhưng không trigger được | StubTrigger configuration/label mapping |
| Trigger thành công nhưng consumer không nhận | Destination, binder, listener, test context |
| Consumer nhận payload sai | Schema, serialization, matcher, artifact version |
| Producer tests không phát message | Producer publisher/base test/test binder |
| Consumer test PASS nhưng producer test FAIL | Candidate stub không chứng minh publisher thật |

**Đừng kỳ vọng tất cả message stubs nhất thiết xuất hiện dưới dạng WireMock HTTP mapping**. Cần kiểm tra contract/message definitions và label/destination tương ứng.

Nếu consumer báo timeout sau `StubTrigger`, chưa thể suy rằng artifact không tồn tại: có thể message đã trigger nhưng handler không lắng nghe đúng destination.

## 18. Git SCM và Maven artifact repository không dùng chung cách resolve

Một số dự án Spring Cloud Contract lưu contracts/stubs trong **Git SCM** thay vì Maven-compatible repository. Trong cơ chế SCM downloader, URL có thể bắt đầu bằng tiền tố:

~~~text
git://https://git.example.invalid/team/service-contracts.git
~~~

Khi dùng Git làm nguồn stubs theo quy ước SCM, layout thường liên quan:

~~~text
META-INF/
  com.example/
    inventory-producer/
      2.3.0/
        contracts/
        mappings/
~~~

Đây là **cây file SCM**, không phải yêu cầu phải có một Maven repository URL chứa `inventory-producer-2.3.0-stubs.jar`.

### Phân biệt trường hợp

- Nếu consumer dùng **Maven/REMOTE repositoryRoot HTTPS thông thường**, hãy kiểm tra POM, Maven coordinates và file `-stubs.jar`.
- Nếu consumer dùng **Git SCM resolver `git://...`**, hãy kiểm tra Git URL, credentials, commit/branch, bố cục `META-INF/group/artifact/version` và nội dung `mappings`.
- Nếu dùng **LOCAL**, hãy kiểm tra Maven local repository của môi trường consumer.
- Nếu dùng **CLASSPATH**, hãy kiểm tra test runtime classpath.

Không đưa một Git URL không có tiền tố SCM vào chỗ Maven repository rồi mặc định Stub Runner biết clone. Cũng không đòi file `-stubs.jar` tại HTTP root của Git khi pipeline được thiết kế theo SCM layout.

### `pushStubsToScm` không tự xảy ra

Với workflow SCM, việc đẩy mappings/stubs lên Git thường cần goal/task `pushStubsToScm` được cấu hình và gọi có chủ đích. Việc có Groovy/YAML DSL trong `contracts/` **không bảo đảm** đã có mappings được producer sinh/verify và push.

Nếu consumer dùng Git SCM không thấy mapping mới, kiểm tra:

1. Producer generated contract tests đã PASS chưa?
2. Job push stubs thực sự chạy chưa?
3. Git ref/branch/commit mà consumer đọc có đúng không?
4. File mappings được push vào đúng `META-INF/.../version` không?
5. Quyền push/read, branch protection và revision tracking có phù hợp không?

Không sửa lỗi bằng cách cho unverified proposal đẩy mappings thẳng sang branch được consumer coi là release.

## 19. Những lệnh chẩn đoán có giá trị nhất

Các lệnh dưới đây dùng **trong dự án đã có Maven/Gradle plugin, wrapper và cấu hình repository tương ứng**. Chúng là ví dụ để thực hành, không phải các lệnh đã chạy cho bài học.

### Producer Maven

~~~bash
# Xác nhận producer tests và artifact packaging.
./mvnw -B -ntp clean verify

# Install artifact/attached stubs vào Maven local repository.
./mvnw -B -ntp install
~~~

Nếu muốn kiểm tra riêng việc resolve classifier với Maven dependency plugin:

~~~bash
./mvnw -B -ntp dependency:get \
  -Dartifact=com.example:inventory-producer:2.3.0:jar:stubs \
  -Dtransitive=false
~~~

Dạng `-Dartifact` ở đây là `group:artifact:version:packaging:classifier`, không phải Stub Runner ID. Lệnh giải quyết theo Maven repositories/settings hiện hành; nếu cần repository riêng, hãy cấu hình repository hoặc tham số resolver theo tài liệu phiên bản plugin.

### Producer Gradle

~~~bash
./gradlew :inventory-producer:tasks --all
./gradlew :inventory-producer:contractTest
./gradlew :inventory-producer:verifierStubsJar
~~~

Nếu publication Maven `verifiedStubs` đã được cấu hình:

~~~bash
./gradlew :inventory-producer:publishVerifiedStubsPublicationToMavenLocal
~~~

Đây là **tên task suy từ tên publication minh họa ở mục 8**. Tên thực có thể khác theo cấu hình. Không giả rằng task đã có khi chưa xem `tasks --all`.

### Kiểm tra archive

~~~bash
jar tf inventory-producer-2.3.0-stubs.jar
~~~

Kiểm tra các entries thuộc:

~~~text
META-INF/.../mappings/
META-INF/.../contracts/
META-INF/.../__files/  (nếu body files được sử dụng)
~~~

### Kiểm tra Maven local path

Trên hệ thống dùng Maven local mặc định:

~~~text
~/.m2/repository/com/example/inventory-producer/2.3.0/
~~~

Nếu Maven settings override `localRepository`, phải dùng path thực. Trong CI multi-job, mỗi job có thể có local repository riêng.

### Quan sát Stub Runner

- Bật logging chẩn đoán có kiểm soát trong môi trường test để xem tọa độ resolved.
- Ghi requested ID, repository root, mode và artifact version thực.
- Xem lỗi resolution: 401/403/404/TLS/timeout.
- Nếu bootstrap thành công, ghi HTTP port hoặc message stub labels.
- Đọc unmatched request journal của WireMock khi HTTP client nhận 404.
- Không in secrets vào logs và không bật verbose HTTP auth tracing tùy tiện.

Một tập lệnh chẩn đoán có ích là tập lệnh cung cấp **bằng chứng chính xác** về bước nào đã đạt, chứ không đơn thuần retry nhiều lần.

## 20. CI phải kiểm tra toàn bộ chuỗi, không chỉ việc đóng gói

Một pipeline producer–consumer có thể tổ chức:

~~~mermaid
flowchart TD
    A["Producer commit + contract revision"] --> B["Generate contract tests"]
    B --> C{"Nonzero tests executed and PASS?"}
    C -->|Không| X["Block stub publish"]
    C -->|Có| D["Package :stubs JAR"]
    D --> E{"Classifier, mappings, fixtures correct?"}
    E -->|Không| X
    E -->|Có| F["Publish candidate with exact version/digest"]
    F --> G["Consumer resolves that artifact"]
    G --> H{"Artifact download and startup PASS?"}
    H -->|Không| X
    H -->|Có| I["Stub Runner consumer tests"]
    I --> J{"HTTP/message assertions PASS?"}
    J -->|Không| X
    J -->|Có| K["Approval and release"]
~~~

**Không lấy “Gradle BUILD SUCCESS” hoặc “Maven BUILD SUCCESS” làm bằng chứng duy nhất.** Build có thể chạy `0 contract tests` hoặc package application artifact thay vì stub classifier.

### Các quality gates tối thiểu

| Bước | Bằng chứng bắt buộc |
|---|---|
| Contract discovery | Đúng DSL version/paths, không có 0 contract bất ngờ |
| Producer verification | Generated producer tests thực sự chạy và PASS |
| Stub packaging | File `-stubs.jar` với classifier đúng và mappings/fixtures cần |
| Publication | Repository, `group:artifact:version:stubs` và digest đúng |
| Consumer resolution | Stub Runner tải đúng artifact, mode và URL đúng |
| Stub runtime | Port/labels sẵn sàng, mapping cần thiết được load |
| Consumer verification | HTTP client/message handler thật xử lý đúng success/error cases |
| Release | Artefact được promote từ đúng candidate đã kiểm chứng |

### CI ở cùng job với Maven local

Đối với mono-repo hoặc local experiment, có thể cho producer publish-to-local rồi consumer test ngay trong **cùng môi trường**:

~~~bash
# Conceptual sequence for a configured Gradle multi-project.
./gradlew :inventory-producer:contractTest
./gradlew :inventory-producer:publishVerifiedStubsPublicationToMavenLocal
./gradlew :checkout-consumer:test
~~~

Các lệnh phải được CI chạy **fail-fast**: nếu producer test fail, không thực thi các bước còn lại. Consumer cần `stubsMode=LOCAL` và đủ dependency/repository settings.

Nếu producer và consumer ở **hai CI jobs trên hai runners tách biệt**, đừng dùng `LOCAL` rồi mong artifact tự xuất hiện ở runner khác. Khi đó nên dùng repository staging/remote hoặc chuyển artifact có provenance rõ giữa jobs.

### Khi publish thành công nhưng consumer vẫn không tải được

Hãy ghi:

~~~text
Publish log:
  uploaded: com.example:inventory-producer:2.3.0:stubs
  repository: <actual-publish-repository>

Consumer config:
  ids: com.example:inventory-producer:2.3.0:stubs:0
  repositoryRoot: <actual-read-repository>
  stubsMode: REMOTE
~~~

Sau đó so sánh **repository URL, group/artifact/version/classifier và quyền đọc**. Hai log cùng chứa `inventory-producer` vẫn có thể trỏ tới hai repository logic khác nhau.


## 21. Từ log tới nguyên nhân gốc: bảng troubleshooting đầy đủ

| Triệu chứng | Giả thuyết cần kiểm tra trước | Bằng chứng cần thu thập | Sửa đúng tầng |
|---|---|---|---|
| `Failed to download stub` | Artifact chưa publish | Repository không có `*-stubs.jar` | Producer package và publish |
| `Artifact not found` nhưng main JAR có | Thiếu classifier `stubs` | Chỉ có `artifact-version.jar` | Attach/publish stub classifier |
| Maven báo `Missing artifact ...:jar:stubs` | Sai tọa độ hoặc repo | Group/artifact/version/type/classifier trong log | Đồng bộ producer publication và Stub Runner ID |
| Bản release 2.3.1 chưa có | Consumer nâng version sớm | Registry chỉ có 2.3.0 | Publish verified 2.3.1 hoặc tạm ghim bản đã có |
| Consumer dùng `2.3.0-SNAPSHOT`, producer publish `2.3.0` | Version mismatch | POM/version/log deploy | Dùng chính version đã phát hành |
| `REMOTE` fail, `LOCAL` PASS trên laptop | Dev local cache che lỗi remote | So file remote và `~/.m2` | Publish remote/cấp quyền đúng |
| `LOCAL` fail trong CI job mới | Không có file ở Maven local CI | Path/local repo của job | Install trong cùng job hoặc dùng REMOTE |
| Remote trả HTTP 401 | Thiếu auth | HTTP status và identity của CI | Cấu hình read credentials |
| Remote trả HTTP 403 | Thiếu quyền | Repository ACL | Cấp read scope tối thiểu |
| Remote trả HTTP 404 | Sai URL hoặc artifact thực không có | Root/path/file/metadata | Sửa tọa độ, repositoryRoot hoặc publish |
| Remote trả HTML login | Redirect/proxy | Content-Type, redirect target | Sửa authentication/SSO resolver |
| Remote trả timeout/5xx | Network/proxy/repository | Registry logs/health | Sửa network hoặc retry có kiểm soát |
| JAR tải được nhưng thiếu mappings | Contract discovery/packaging sai | `jar tf` và generated stubs directory | Sửa producer build |
| JAR có mappings nhưng thiếu body file | `__files` không được package | Mapping `bodyFileName` + archive listing | Package fixture đúng |
| Stub Runner khởi động thất bại | JSON mapping lỗi hoặc port/dependency | Startup exception | Sửa mapping/config/dependency |
| Consumer gọi URL và nhận 404 | Unmatched WireMock request | Unmatched request journal | So method/path/header/body |
| Consumer gọi `localhost:0` | Nhầm dynamic port | Stub Runner port runtime | Inject `@StubRunnerPort`/StubFinder |
| Consumer PASS nhưng producer thiếu endpoint | Candidate stub chưa verify | Producer generated test FAIL | Chặn verified publication |
| Checkout test xanh trên 2.3.0, production chạy 2.3.1 | Stub stale | Consumer resolved ID + deploy version | Chạy compatibility với candidate đúng |
| Mapping của consumer khác được chọn | Consumer filtering hoặc duplicate | JAR layout, loaded mapping list | Cấu hình/filter đúng |
| Message trigger không thấy label | Message stub không được package | Contract label + archive content | Rebuild messaging stub |
| Message trigger được nhưng handler timeout | Binder/destination không đúng | Consumer logs và destination | Sửa messaging test setup |
| Artifact khác bytes dù cùng version | Mutable artifact/cache | SHA-256 hoặc metadata | Immutable release + provenance |

### Ưu tiên xử lý khi có nhiều lỗi đồng thời

Nếu thấy cả “artifact 404” lẫn “response assertion failed” trong các lượt chạy khác nhau, hãy bắt đầu từ **kết quả run hiện tại**:

1. Chụp yêu cầu artifact và source của **chính run đang fail**.
2. Kiểm tra nó có tải được artifact không.
3. Nếu không, không phân tích WireMock request ở run khác để kết luận.
4. Nếu có, đối chiếu bytes/digest với artifact được producer verify.
5. Chỉ khi stub runtime đã sẵn sàng mới đi vào mapping và consumer assertion.

Không trộn log từ nhiều build/version rồi coi chúng mô tả một lỗi duy nhất.

## 22. Bài thực hành 1 — Artifact hoàn toàn chưa tồn tại

### Đề bài

Checkout consumer cấu hình:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.4.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.invalid/repository/verified-stubs"
)
~~~

Tại repository có:

~~~text
com/example/inventory-producer/
  2.3.0/inventory-producer-2.3.0-stubs.jar
  2.3.1/inventory-producer-2.3.1-stubs.jar
~~~

Không có folder `2.4.0`. Producer `main` hiện đang ở commit chuẩn bị cho release 2.4.0 nhưng chưa publish artifact.

**Câu 1. Đây có phải lỗi WireMock mapping không?**

**Không.** Stub Runner chưa resolve được stub artifact 2.4.0, nên WireMock tương ứng chưa có mapping để kiểm tra.

**Câu 2. Có nên đổi consumer ID thành `+` hoặc `latest` không?**

Không nếu mục tiêu là kiểm tra tương thích release 2.4.0. Việc tải bản cũ có thể cho test xanh nhưng **không chứng minh** consumer tương thích với candidate producer mới.

**Câu 3. Cần producer làm gì?**

Producer phải sinh/chạy contract tests và PASS, package stub JAR với classifier `stubs`, publish candidate 2.4.0 tới repository staging/approved theo chính sách, rồi truyền đúng coordinates/digest cho Checkout.

**Câu 4. Nếu Checkout cần phát triển trước?**

Có thể dùng stub 2.3.1 để kiểm tra các tương tác đã hỗ trợ hoặc candidate stub chưa verified **trong nhánh test cô lập**, được dán nhãn rõ. Không xem stub chưa verified là bằng chứng 2.4.0 đã triển khai.

### Bằng chứng phản hồi mẫu

~~~text
Requested:
  com.example:inventory-producer:2.4.0:stubs

Available:
  2.3.0:stubs
  2.3.1:stubs

Root cause:
  producer 2.4.0 stubs not published

Action:
  run producer verification, package and publish candidate,
  update Checkout CI to use exact candidate coordinates

Status:
  BLOCKED_ON_PRODUCER_ARTIFACT
~~~

Tên status là ví dụ quy trình team, không phải trạng thái chính thức Spring Cloud Contract.

## 23. Bài thực hành 2 — Sai classifier trong publication

### Đề bài

Producer build output:

~~~text
build/libs/inventory-producer-2.4.0-stubs.jar
~~~

Nhưng Maven repository sau publish chỉ có:

~~~text
inventory-producer-2.4.0.jar
inventory-producer-2.4.0.pom
~~~

Checkout yêu cầu:

~~~text
com.example:inventory-producer:2.4.0:stubs:0
~~~

**Câu 1. Producer đã tạo stub chưa?**

Có dấu hiệu task đã tạo file tại build output. Nhưng cần kiểm tra `jar tf` để xác nhận file đó đúng nội dung. **Tạo file không có nghĩa đã publish.**

**Câu 2. Consumer có cấu hình sai không?**

Không nhất thiết. `:stubs` là classifier đúng cho convention đang áp dụng. Lỗi có vẻ nằm ở **publication/attachment**: JAR có mặt trong build nhưng chưa được đưa lên repository dưới classifier.

**Câu 3. Cần xem cấu hình nào?**

- Maven: plugin stub generation/attachment, `install`/`deploy` và attached artifacts.
- Gradle: `publishing.publications`, artifact `verifierStubsJar`, `archiveClassifier`/classifier metadata và publish task.
- Registry: tọa độ thực sự của file đã upload, có bị đổi artifactId/groupId không.

**Câu 4. Có nên bỏ `:stubs` trong consumer ID không?**

Không. Khi đó resolver có thể tải main application JAR và lỗi chuyển thành “không tìm thấy mappings”, chưa giải quyết được yêu cầu consumer stub.

### Hướng sửa được kiểm chứng

~~~text
Before:
  repository has inventory-producer-2.4.0.jar

After:
  repository has inventory-producer-2.4.0.jar
  repository has inventory-producer-2.4.0-stubs.jar

Verify:
  expected mapping exists inside -stubs.jar
  consumer REMOTE resolves exact classifier
  Stub Runner starts and client test passes
~~~

Với version release immutable, **không overwrite** cùng tọa độ nếu policy cấm; thực hiện version/republish theo quy trình kiểm soát phù hợp.

## 24. Bài thực hành 3 — Sai phiên bản trong multi-module

### Đề bài

Gradle project có:

~~~text
:platform:inventory-service
:platform:checkout-service
~~~

Publication producer thực:

~~~text
groupId    = com.example.platform
artifactId = inventory-api
version    = 3.1.0
classifier = stubs
~~~

Checkout lại dùng:

~~~text
com.example:inventory-service:3.1.0:stubs:0
~~~

**Câu 1. Những thành phần nào lệch?**

Cả `groupId` và `artifactId`. Consumer dùng tên project/service thay vì Maven publication coordinates.

**Câu 2. Stub Runner ID nào đúng trong ví dụ?**

~~~text
com.example.platform:inventory-api:3.1.0:stubs:0
~~~

**Câu 3. Chỉ sửa ID là đủ chưa?**

Cần xác minh publication thực sự có file `inventory-api-3.1.0-stubs.jar` và JAR chứa mappings. Sau đó Stub Runner khởi động và consumer chạy test với đúng port.

**Câu 4. Nếu source Inventory đã sang 3.1.1 nhưng artifact vẫn là 3.1.0?**

Kết quả consumer test chỉ chứng minh behavior từ stub 3.1.0. Muốn xác nhận 3.1.1, producer cần verify/publish stub tương ứng và consumer ghim candidate mới.

## 25. Bài thực hành 4 — 404 ở stub runtime, không phải registry

### Đề bài

Log cho thấy:

~~~text
Resolved stub artifact:
  com.example:inventory-producer:2.3.0:stubs

Stub Runner HTTP port:
  13142

Loaded mapping:
  GET /api/inventory/SKU-101
~~~

Checkout lại gửi:

~~~http
GET /inventory/SKU-101 HTTP/1.1
Host: localhost:13142
Accept: application/json
~~~

WireMock trả 404.

**Câu 1. Có cần publish lại stub không?**

Chưa. Stub Runner đã tải artifact và khởi động thành công. Vấn đề nằm ở **request path khác mapping**: client thiếu `/api`.

**Câu 2. Có thể test false positive ở đâu?**

Nếu consumer test đang mong 404 và chỉ assert HTTP status, WireMock unmatched 404 có thể bị nhầm với business 404. Cần assert error code/body và xác minh matched mapping.

**Câu 3. Khi nào sửa contract thay vì sửa consumer?**

Nếu yêu cầu đã được review là `GET /inventory/{sku}` nhưng producer contract hiện mô tả `/api/inventory/{sku}`, hai bên phải thống nhất lại API path, sửa DSL nguồn và chạy producer/consumer gates. Không chỉnh generated mapping bằng tay để làm test hiện tại xanh.

### Ghi nhận lỗi rõ ràng

~~~text
Artifact resolution: PASS
Stub Runner startup: PASS
HTTP request match: FAIL

Expected mapping: GET /api/inventory/SKU-101
Actual request:   GET /inventory/SKU-101

Root cause: client base path mismatch
Owner: Checkout integration
~~~

Đây là báo cáo có thể hành động, khác với việc chỉ nói “stub not found”.

## 26. Một mẫu báo cáo sự cố stub có thể tái hiện

Khi gửi issue cho producer/platform team, nên điền:

~~~text
Title:
  Stub resolution failure for Inventory -> Checkout

Consumer:
  repository/commit: <consumer-repo>@<consumer-sha>
  test: CheckoutInventoryClientTest
  Stub Runner ID: <group:artifact:version:classifier:port>
  stubsMode: <LOCAL|REMOTE|CLASSPATH>
  repositoryRoot: <url-or-not-applicable>

Observed failure:
  phase: <resolve|extract|bootstrap|request-match|assertion>
  error category: <404|401|403|timeout|no-mappings|...>
  exact error: <sanitized-message>

Producer:
  source commit: <producer-sha>
  contract revision: <contract-sha>
  contract test count/result: <count/passed/failed/skipped>
  packaged stub file: <filename>
  published coordinate: <group:artifact:version:classifier>
  artifact digest: <sha256>

Evidence:
  archive mapping entries: <paths>
  Maven registry path: <url-without-secret>
  Stub Runner port: <port-or-none>
  unmatched request: <method/path/headers/body-if-safe>

Root cause:
  <what is confirmed, not a guess>

Next action:
  <owner and concrete step>
~~~

Không đưa token/password, private user data hoặc nhạy cảm từ logs vào issue. Các dữ liệu trong dấu `<...>` là placeholders.

### Phân biệt các mức kết luận

- **Đã xác minh:** “Repository không có classifier stubs ở version 2.4.0.”
- **Giả thuyết:** “Có thể CI publish thiếu attached artifact.”
- **Cần điều tra:** “Kiểm tra Gradle publication và registry metadata.”
- **Đã khắc phục:** “Stub JAR được publish dưới đúng tọa độ; consumer test dùng phiên bản đó PASS.”

Đây là cách rút ngắn vòng trao đổi giữa producer, consumer và platform thay vì phải hỏi nhiều lần “Bạn dùng bản nào?”.

## 27. Checklist kiểm tra trước khi báo lỗi artifact không tồn tại

### Producer và build

- [ ] Đã xác định đúng producer module tạo stub.
- [ ] Groovy/YAML contracts được phát hiện đúng số lượng.
- [ ] Generated producer contract tests đã thực sự chạy và PASS.
- [ ] Test không bị skip, filter hoặc `0 tests` ngoài ý định.
- [ ] Stub JAR được tạo bởi task/goal phù hợp.
- [ ] Stub JAR có HTTP mappings hoặc message definitions cần thiết.
- [ ] `bodyFileName` và file `__files` tham chiếu hợp lệ.
- [ ] Artifact được attach/published với classifier `stubs`.
- [ ] Publication group/artifact/version đúng với mục tiêu.
- [ ] Publish/install logs có bằng chứng thành công.
- [ ] Artifact cùng revision với producer tests PASS.
- [ ] Không tái publish release mutable để che lỗi.

### Repository và resolver

- [ ] Consumer dùng đúng `groupId`/`artifactId`/`version`/`classifier`.
- [ ] Không nhầm `:stubs:0` của Stub Runner với Maven dependency coordinates.
- [ ] `stubsMode` đúng theo nguồn `LOCAL`, `REMOTE` hoặc `CLASSPATH`.
- [ ] Nếu LOCAL, JAR đã được install vào Maven local của **chính consumer environment**.
- [ ] Nếu REMOTE, `repositoryRoot` là gốc Maven repository đúng.
- [ ] Registry chứa chính file `*-stubs.jar`, không chỉ main JAR.
- [ ] Credentials chỉ có read scope cần thiết; không hardcode secrets.
- [ ] HTTP 401/403/404/5xx/TLS được phân loại đúng.
- [ ] Với SNAPSHOT, metadata/resolver/caching được kiểm tra.
- [ ] Version và digest không khác artifact producer vừa verify.
- [ ] Với Git SCM, `git://` và layout SCM được xác minh thay vì áp Maven file path.

### Consumer và runtime

- [ ] JAR contents chứa mapping tương ứng use case đang test.
- [ ] Nếu stubs-per-consumer, consumer identity/filter phù hợp.
- [ ] Stub Runner đã khởi động đúng cổng hoặc message handler.
- [ ] HTTP client dùng cổng runtime từ `@StubRunnerPort`/`StubFinder`.
- [ ] Method, URL, query, headers, JSON body match mapping.
- [ ] Không nhầm WireMock unmatched 404 với business 404.
- [ ] Error contract được assert cả status và body/code.
- [ ] Messaging label/destination/consumer binder đúng.
- [ ] Consumer test dùng HTTP client/message handler thật, không chỉ kiểm thử stub mapping.
- [ ] CI không tự chọn version `latest` để né lỗi.
- [ ] Có log source SHA, version, classifier, digest, test reports và owner khắc phục.

## 28. Ghi nhớ và tài liệu tham khảo

**Stub artifact không tồn tại, sai classifier hoặc sai phiên bản** là vấn đề thuộc **chuỗi phân phối artifact**, không phải lúc nào cũng là lỗi contract DSL hoặc HTTP client.

Giải quyết theo thứ tự:

1. **Producer:** generated tests có chạy/PASS và stub JAR có được tạo?
2. **Publication:** artifact có được attach/upload dưới đúng `group:artifact:version:stubs`?
3. **Resolution:** Stub Runner consumer có đang tìm đúng mode, repository, version và credentials?
4. **Packaging:** JAR tải về có mappings/fixtures/labels đúng?
5. **Runtime:** Stub Runner có khởi động và consumer request có match?
6. **Compatibility:** consumer tests có dùng đúng stub của producer đã verified?

Một producer application JAR, một contract definition JAR và một producer stub JAR là **ba loại artifact khác nhau**. Không thay thế chúng cho nhau bằng cách đổi classifier tùy tiện.

### Tài liệu tham khảo

- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): cấu hình `@AutoConfigureStubRunner`, ID, mode và cổng.
- [Spring Cloud Contract — Stub Runner Core](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html): resolver, download và stub server lifecycle.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): sinh tests/stubs và Maven artifact attachment.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): `contractTest`, `verifierStubsJar` và Gradle integration.
- [Spring Cloud Contract — Git as Storage](https://docs.spring.io/spring-cloud-contract/reference/howto/how-to-use-git-as-storage.html): trường hợp SCM repository thay Maven artifacts.
- [Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): cấu trúc local/remote repository và tọa độ.
- [Maven Dependency Plugin — dependency:get](https://maven.apache.org/plugins/maven-dependency-plugin/get-mojo.html): kiểm tra resolve một artifact/classifier.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): cấu hình publication và Maven local/remote.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): request matching, mappings và response files.

**Kết luận thực hành:** khi Checkout nói “không tìm thấy stub”, hãy hỏi **“nó không tìm được artifact, không tìm được mapping trong artifact, hay request không khớp stub đã chạy?”** Chỉ khi xác định đúng tầng lỗi và đối chiếu tọa độ/version/classifier với artifact thật, chúng ta mới sửa chính xác mà không làm mất độ tin cậy của kiểm thử hợp đồng.
