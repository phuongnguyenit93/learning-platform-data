# Phiên bản SNAPSHOT, cache và độ mới của stub

## 1. Tại sao phiên bản stub quyết định giá trị của contract testing?

**Spring Cloud Contract (SCC)** giúp producer và consumer thống nhất hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**. Công cụ sinh **generated producer tests** để kiểm tra implementation cung cấp thật, đồng thời sinh **stub** để consumer kiểm tra client/handler bằng **Stub Runner**. Trong CI, hai phía phải dùng **cùng revision hợp đồng** mới phát hiện được những thay đổi API không tương thích.

Một trường hợp nguy hiểm:

- 09:00 — Inventory Service publish `1.4.0-SNAPSHOT`, JSON trả `available`.
- 09:30 — Producer đổi contract/code thành JSON trả `inStock`, rồi publish lại `1.4.0-SNAPSHOT`.
- 09:35 — Checkout Service chạy Stub Runner nhưng lại dùng stub cũ đã cache từ 09:00.
- Test Checkout xanh vì code vẫn đọc `available`. Pipeline không phát hiện breaking change của ứng viên lúc 09:30.

Cả hai lần đều có cùng **logical version `1.4.0-SNAPSHOT`**, nhưng chúng không nhất thiết cùng **artifact bytes**. Vì thế, độ mới của stub là một phần **tính đúng đắn của kiểm thử**, không chỉ là vấn đề tối ưu tốc độ tải.

Bài học thuộc chương **Kho hợp đồng và artifact** và tập trung vào **phiên bản SNAPSHOT, cache và độ mới của stub**: Maven snapshot metadata, timestamped builds, cache theo tầng, Stub Runner LOCAL/REMOTE, chiến lược candidate artifacts và cổng CI.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **release**, **SNAPSHOT logical version** và **timestamped SNAPSHOT**.
2. Giải thích `maven-metadata.xml`, repository snapshot, update policy và local/remote caches.
3. Nhận diện cache của **Maven**, **Gradle**, **artifact repository proxy**, **Stub Runner** và **WireMock**.
4. Cấu hình Stub Runner LOCAL/REMOTE phù hợp ngữ cảnh.
5. Dùng `mvn -U` hoặc `gradle --refresh-dependencies` đúng phạm vi, không coi chúng là phép màu.
6. Xác minh stub đã load tương ứng với producer commit, classifier và contract revision mong muốn.
7. Thiết kế CI dùng **candidate version bất biến** hoặc snapshot đã được xác định timestamp/digest.
8. Chẩn đoán stale stub, sai repository, missing artifact, test xanh giả và race khi nhiều pipeline publish.

## 2. Bốn tài sản khác nhau thường bị gọi chung là “contract”

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| **Contract source** | `get-stock.groovy` hoặc `get-stock.yml` | Định nghĩa HTTP/message behavior |
| **Generated producer tests** | Java test được Contract Verifier sinh | Kiểm tra **code producer thật** |
| **Generated stub mappings** | WireMock JSON, response files | Mô phỏng request/response của contract |
| **Stubs artifact** | `inventory-service-1.4.0-SNAPSHOT-stubs.jar` | Cung cấp stub cho consumer qua repository |

~~~mermaid
flowchart TD
    A["Code + contract producer commit A"] --> B["SCC generated producer tests"]
    A --> C["SCC generated stub mappings"]
    B --> D{"Producer tests đạt?"}
    D -- "Không" --> X["Chặn release"]
    D -- "Có" --> E["Candidate stubs artifact"]
    C --> E
    E --> F["Maven artifact repository"]
    F --> G["Stub Runner resolve và load"]
    G --> H["WireMock HTTP server"]
    H --> I["Consumer client thật"]
    I --> J{"Tương thích?"}
    J -- "Không" --> X
    J -- "Có" --> K["Tiếp tục CI/release gates"]
~~~

Nếu producer tests chạy với contract B nhưng consumer tải artifact của contract A, hai vế kiểm tra **không còn liên quan tới cùng thay đổi**. Do đó, trong CI phải chứng minh quan hệ **producer commit → contract → generated test → stubs JAR → Stub Runner → consumer test**.

## 3. Tọa độ stub artifact là gì?

Một bộ stubs có thể được publish theo tọa độ Maven:

~~~text
groupId:     com.example
artifactId:  inventory-service
version:     1.4.0-SNAPSHOT
classifier:  stubs
type:        jar
~~~

Một chuỗi ID trong Stub Runner thường được biểu diễn:

~~~text
com.example:inventory-service:1.4.0-SNAPSHOT:stubs:18081
~~~

| Thành phần | Ý nghĩa | Nếu dùng sai |
|---|---|---|
| `groupId` | Namespace tổ chức | Có thể tải nhầm producer |
| `artifactId` | Tên artifact producer | Tải nhầm dịch vụ |
| `version` | Bản contract/stub | Dùng code API cũ hoặc không đúng PR |
| `classifier=stubs` | JAR chứa mapping/fixture | Nhầm với application JAR |
| `type=jar` | Định dạng artifact | Không giải nén/đọc được |
| `port=18081` | Cổng HTTP của Stub Runner | Consumer gọi nhầm server |

Tọa độ `group:artifact:version:classifier` chỉ định **artifact logic**. Với SNAPSHOT mutable, thông tin đó chưa chắc xác định được **bytes duy nhất**.

## 4. Release và SNAPSHOT khác nhau ra sao?

### 4.1. Release

~~~text
com.example:inventory-service:1.4.0:stubs
~~~

Một repository nên áp dụng chính sách **release bất biến**: cùng tọa độ không được redeploy với nội dung khác. Nhiều repository managers có thể chặn việc ghi đè; nhưng tính bất biến là **policy phải được thiết lập và kiểm tra**, không phải bảo đảm tự động ở mọi kho.

### 4.2. SNAPSHOT

~~~text
com.example:inventory-service:1.4.0-SNAPSHOT:stubs
~~~

SNAPSHOT thường là phiên bản đang phát triển, có thể publish nhiều lần. Ví dụ:

~~~text
1.4.0-SNAPSHOT lần A -> {"available":true}
1.4.0-SNAPSHOT lần B -> {"inStock":true}
~~~

Hai artifact khác nhau có thể được yêu cầu bằng **cùng một chuỗi version logical**. Điều đó khiến kết quả consumer test khó tái lập nếu không ghi timestamp/build identity hoặc checksum.

SNAPSHOT vẫn hữu ích cho **phát triển liên tục**. Nhưng khi quyết định “PR này có phá consumer cũ không?”, nên dùng **candidate version bất biến** hoặc một snapshot đã được cố định identity và provenance.

## 5. Timestamped SNAPSHOT là gì?

Maven-compatible repositories có thể lưu một logical SNAPSHOT như:

~~~text
1.4.0-SNAPSHOT
~~~

dưới những file timestamped (ví dụ):

~~~text
inventory-service-1.4.0-20261124.051500-12-stubs.jar
inventory-service-1.4.0-20261124.051500-12.pom
maven-metadata.xml
~~~

Trong đó `20261124.051500` là timestamp minh họa và `12` là build number minh họa. Tùy repository và deploy tool, những phiên bản timestamped khác nhau có thể lần lượt đại diện cho các lần publish.

~~~mermaid
flowchart LR
    A["Consumer khai báo 1.4.0-SNAPSHOT"] --> B["Resolver đọc metadata"]
    B --> C["Chọn timestamp/build tương ứng"]
    C --> D["Tải JAR classifier stubs"]
    D --> E["Stub Runner nạp mappings"]
    E --> F["WireMock phục vụ HTTP"]
~~~

Không thể suy ra “consumer đang dùng snapshot mới nhất trên server” chỉ từ một cấu hình có `-SNAPSHOT`. Resolver còn chịu ảnh hưởng update policy, metadata cache, proxy, thời điểm request và cả trạng thái Stub Runner.

## 6. maven-metadata.xml quyết định phiên bản nào?

Tệp `maven-metadata.xml` ở Maven repository có thể mô tả snapshot timestamp, build number và danh sách `snapshotVersions` theo extension/classifier.

Ví dụ **rút gọn, chỉ để hiểu cơ chế**:

~~~xml
<metadata>
  <groupId>com.example</groupId>
  <artifactId>inventory-service</artifactId>
  <version>1.4.0-SNAPSHOT</version>
  <versioning>
    <snapshot>
      <timestamp>20261124.051500</timestamp>
      <buildNumber>12</buildNumber>
    </snapshot>
    <snapshotVersions>
      <snapshotVersion>
        <extension>jar</extension>
        <classifier>stubs</classifier>
        <value>1.4.0-20261124.051500-12</value>
        <updated>20261124051500</updated>
      </snapshotVersion>
    </snapshotVersions>
  </versioning>
</metadata>
~~~

Metadata có thể có nhiều entries (POM, main artifact, stubs JAR...). Khi chẩn đoán:

- Metadata ở **remote origin** có mới không?
- Proxy/mirror có đang trả **metadata cũ** không?
- Metadata trong local cache có trỏ timestamp cũ?
- Metadata có entry `classifier=stubs` của bản publish mới?
- Timestamp mà Stub Runner đã resolve là bản nào?
- Artifact đã tải có checksum khớp output producer CI hay không?

**Đừng đồng nhất metadata mới với bytes mới đang được WireMock phục vụ**. Server đã nạp JAR cũ vẫn có thể trả response cũ.

## 7. Một timeline gây xanh giả

~~~mermaid
sequenceDiagram
    participant P as Producer CI
    participant R as Snapshot Repository
    participant C as Consumer CI
    participant S as Stub Runner
    P->>R: 09:00 publish SNAPSHOT A
    C->>R: 09:05 resolve A
    R-->>C: JAR A
    C->>S: Load mappings A
    P->>R: 09:30 publish SNAPSHOT B
    Note over S: WireMock vẫn giữ mapping A
    C->>S: 09:35 GET inventory
    S-->>C: JSON của A
    Note over C: Test có thể PASS giả
~~~

Hai câu hỏi độc lập:

1. **Resolver đã tải được stubs JAR mới chưa?**
2. **Stub Runner/WireMock instance đang chạy đã load JAR mới chưa?**

Một pipeline chỉ refresh repository nhưng **không restart server** có thể vẫn dùng mapping trước khi producer publish.

## 8. Cache có nhiều lớp, không phải một chỗ

| Tầng | Nội dung có thể cache | Rủi ro |
|---|---|---|
| **Producer build output** | `target`/`build`, generated mappings | JAR publish từ output cũ |
| **Artifact repository** | Timestamped snapshots, metadata | Artifact classifier sai hoặc chưa hiện diện |
| **Repository proxy/mirror** | Cached metadata + bytes | Chưa thấy build mới từ origin |
| **Maven local repository** | `~/.m2/repository` và metadata | Resolver dùng snapshot cũ |
| **Gradle dependency cache** | Module metadata và artifact | Dynamic/changing dependencies chưa refresh |
| **Stub Runner resolver/cache** | Artifact đã resolve/extract | Runner chọn file từ lần trước |
| **WireMock in-memory mappings** | Mapping nạp lúc khởi động | Publish mới không tự hot reload |
| **CI workspace/cache** | Local repository, compiled tests, cached process | Job sau dùng state trước |

Một hành động `mvn -U` chỉ tác động đến Maven resolution liên quan; nó không làm mới tất cả các lớp. Chỉ nên khắc phục sau khi **xác định nơi dữ liệu đang bị cũ**.

## 9. Maven updatePolicy: luôn, hàng ngày, theo khoảng, không cập nhật

Repository SNAPSHOT policy có thể khai báo:

| Policy | Ý nghĩa tổng quát |
|---|---|
| `always` | Kiểm tra cập nhật khi resolver cần |
| `daily` | Thường kiểm tra theo chu kỳ ngày |
| `interval:N` | Kiểm tra sau N phút |
| `never` | Không chủ động cập nhật |

Ví dụ POM **minh họa**:

~~~xml
<repositories>
    <repository>
        <id>company-snapshots</id>
        <url>https://repo.example.invalid/repository/snapshots</url>
        <releases>
            <enabled>false</enabled>
        </releases>
        <snapshots>
            <enabled>true</enabled>
            <updatePolicy>always</updatePolicy>
        </snapshots>
    </repository>
</repositories>
~~~

`repo.example.invalid` cố tình là địa chỉ giả, không phải nguồn để kết nối. Maven có policy mặc định và khả năng override bằng settings/mirrors; nhiều trường hợp mặc định là `daily`. Repository manager cũng có cache TTL hoặc cơ chế riêng.

**Không khuyến nghị bật `always` cho mọi dependency**: có thể gây tải repository mà vẫn không bảo đảm Stub Runner đã nạp lại mapping mới. Đối với CI có yêu cầu tái lập, version ứng viên bất biến thường đáng tin hơn.

## 10. mvn -U có và không có tác dụng gì?

~~~bash
./mvnw -U clean verify
~~~

`-U` yêu cầu Maven kiểm tra/cập nhật snapshots qua resolver của **Maven process đó** theo semantics phiên bản Maven. Nó cũng có thể ảnh hưởng tới việc kiểm tra các release dependency trước đây bị thiếu.

Nhưng:

- Không tự bắt **Stub Runner JVM khác** tải lại artifact.
- Không tự hot reload **WireMock instance đang chạy**.
- Không làm xuất hiện JAR nếu producer chưa publish hoặc publish nhầm repository.
- Không khắc phục proxy vẫn trả metadata cũ.
- Không gắn logical `SNAPSHOT` với commit cụ thể.
- Không đảm bảo Gradle dependency cache cũng được refresh.

Khi cần chứng minh độ mới, cần **resolved snapshot identity + content digest + commit provenance**, không chỉ log “đã chạy Maven -U”.

## 11. Gradle --refresh-dependencies không phải lệnh refresh Stub Runner

Nếu consumer/producer sử dụng Gradle:

~~~bash
./gradlew --refresh-dependencies test
~~~

Lệnh này làm mới/kiểm tra cache của **Gradle dependency resolver**. Những module dynamic hoặc changing (như Maven `-SNAPSHOT` được Gradle nhận diện là changing) có semantics caching riêng.

Ví dụ thay đổi chính sách cache chỉ để minh họa:

~~~groovy
configurations.configureEach {
    resolutionStrategy {
        cacheChangingModulesFor 0, 'seconds'
        cacheDynamicVersionsFor 0, 'seconds'
    }
}
~~~

Cấu hình này có thể làm tăng network traffic và giảm hiệu năng build; **không nên sao chép vào mọi dự án**. Nếu Stub Runner sử dụng resolver/cache riêng, `--refresh-dependencies` cũng không bảo đảm runtime của nó đã đổi stub.

**Dynamic version** (ví dụ `1.+`) và **changing module** (`1.4.0-SNAPSHOT`) không phải một khái niệm. Đừng dùng `+` cho compatibility gate khi mục tiêu là kiểm thử một commit producer cụ thể.

## 12. Stub Runner LOCAL nhận stub từ đâu?

Ví dụ consumer test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest(properties =
    "inventory.base-url=http://localhost:18081")
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.4.0-SNAPSHOT:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryLocalStubTest {
    @Test
    void consumerUsesStub() {
        // Gọi InventoryClient thật của Checkout đến Stub Runner.
    }
}
~~~

`LOCAL` thường lấy artifact từ **Maven local repository** hoặc nguồn local do Stub Runner hỗ trợ. Nếu producer đổi contract mà developer chỉ chạy `mvn test` hoặc `mvn package` thì chưa chắc JAR mới được **install** vào local repo.

Một luồng phát triển LOCAL hợp lý:

~~~text
Producer đổi contract + code
  -> Generate/runs producer tests
  -> Package stubs JAR
  -> Install JAR vào Maven local repo
  -> Khởi động lại consumer test/Stub Runner
  -> Xác nhận mapping mới
~~~

Trong producer Maven đã cấu hình plugin, ví dụ lệnh:

~~~bash
./mvnw clean install
~~~

**Không mặc định** một lệnh build luôn tạo/attach classifier `stubs`; phải kiểm tra output/log plugin. Với Gradle, `build` cũng không tự đồng nghĩa publish vào Maven local trừ khi dự án cấu hình task tương ứng.

## 13. Stub Runner REMOTE lấy artifact như thế nào?

Khi producer và consumer chạy ở các CI jobs/container khác nhau, thường cần **remote repository**.

Ví dụ cấu hình dạng skeleton:

~~~java
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.4.0-SNAPSHOT:stubs:18081",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.invalid/repository/snapshots"
)
class InventoryRemoteStubTest {
    // Hoàn thiện bằng Spring test và consumer client thật.
}
~~~

Cần kiểm tra annotation `repositoryRoot`, authentication, repository URL và semantics của resolver theo **SCC version đang dùng**. Đây không phải class test hoàn chỉnh.

Với REMOTE:

1. Producer publish JAR `stubs` sau khi generated producer tests đạt.
2. Repository/proxy phải expose artifact và metadata đúng.
3. Consumer resolver có quyền đọc repository.
4. Stub Runner log cho biết artifact nào được resolve.
5. Stub server được khởi động sau khi artifact đã có mặt.
6. HTTP client thực của consumer trỏ đúng port và kiểm tra response.

**REMOTE không mặc định “mới hơn” LOCAL**. Repository proxy cũng có cache; bản local vừa install mới có thể mới hơn bản remote metadata đang được proxy trả.

## 14. Một version logic chưa đủ để kết luận độ mới

Hai logs cùng ghi:

~~~text
com.example:inventory-service:1.4.0-SNAPSHOT:stubs
~~~

nhưng có thể sử dụng **hai JAR khác nhau**. Bằng chứng đáng tin hơn gồm:

- Resolved **timestamped SNAPSHOT**;
- SHA-256 digest của JAR thực được tải;
- Producer **Git commit SHA** và build/job ID;
- Contract revision đi cùng producer build;
- Mapping JSON thực tế trong JAR;
- Stub Runner startup log và WireMock mappings đang phục vụ;
- Consumer tests có assertions đối với behavior mới.

| Quan sát | Độ tin cậy |
|---|---|
| Chỉ thấy `1.4.0-SNAPSHOT` | Không biết bytes nào |
| Thấy resolved timestamp A | Biết một snapshot build, chưa chắc đúng PR |
| Timestamp B + digest khớp producer CI | Bằng chứng mạnh về đúng candidate |
| Unique candidate version + digest + immutable repository policy | Dễ tái lập/audit nhất |

**Immutability phải được thực thi**, không chỉ được viết trong tên version.

## 15. Publish mới không tự làm WireMock đang chạy cập nhật

~~~text
T1: Stub Runner start -> load mappings A
T2: Producer publish JAR mới chứa mappings B
T3: Checkout gọi Stub Runner instance của T1
T4: Server vẫn trả mappings A
~~~

Để kiểm tra và sửa:

1. Xác định startup time của Stub Runner.
2. Kiểm tra resolved artifact khi server start.
3. Nếu cần, dừng/tạo test context mới và **khởi động Stub Runner sau khi candidate mới đã sẵn sàng**.
4. Kiểm soát cache/resolver để startup mới không nạp lại file A.
5. Gọi endpoint có thuộc tính mới, kiểm tra raw response.
6. Xác nhận consumer client thật xử lý đúng behavior B.

Cần lưu ý Spring test **application-context caching**: chạy lại test method không nhất thiết tạo mới Stub Runner server. Không suy ra hot reload chỉ vì SNAPSHOT trên repository đã thay đổi.

## 16. Local file, Maven cache và remote artifact có thể khác nhau

Ba nơi này độc lập:

~~~text
Producer source:
  src/test/resources/contracts/inventory/get-stock.groovy

Producer build output:
  target/inventory-service-1.4.0-SNAPSHOT-stubs.jar

Consumer local repository:
  ~/.m2/repository/com/example/inventory-service/1.4.0-SNAPSHOT/
~~~

Producer có thể đổi contract mà chưa regenerate mappings; có thể generate JAR mới nhưng chưa `install`; hoặc consumer ở một container khác không có local artifact ấy.

**Ví dụ ranh giới quan trọng:**

~~~text
Producer CI:
  ./mvnw clean install
  -> viết ~/.m2/repository của producer runner

Consumer CI container khác:
  stubsMode=LOCAL
  -> đọc ~/.m2/repository của consumer runner
~~~

Hai `~/.m2` không tự động chia sẻ với nhau. Trong CI tách job, nên publish repository từ xa hoặc chuyển artifact qua cơ chế CI có kiểm tra nguồn gốc, thay vì mặc định local cache được đồng bộ.

## 17. Version động và latest làm mất tính tái lập

Một số cấu hình Stub Runner có thể hỗ trợ version động:

~~~text
com.example:inventory-service:+:stubs:18081
~~~

Đây là **ví dụ cần tránh cho release gate**, trừ khi hệ thống có cơ chế ghi và ghim kết quả resolve. Nguy cơ:

- Job A và B tải hai versions khác nhau dù cùng commit consumer.
- Một bản mới xuất hiện giữa hai lần test.
- Cache metadata khiến “latest” không thống nhất.
- Các nhánh cùng publish SNAPSHOT vào một nơi.
- Test pass không gắn được với commit producer đang review.

**Khuyến nghị:** truyền exact candidate coordinate từ producer pipeline sang consumer pipeline; nếu bắt buộc dùng SNAPSHOT, phải ghi **timestamped identity và digest** của bản đã tải.

## 18. Không nên giải quyết mọi thứ bằng xóa cache

Khi consumer thấy response cũ, hãy phân loại lỗi trước:

1. Producer đã publish **mapping mới thật** chưa?
2. Remote repository có **stubs JAR classifier** đúng không?
3. Snapshot metadata đã trỏ tới build mới chưa?
4. Proxy/mirror có cache metadata cũ không?
5. Maven/Gradle resolver đã refresh theo policy chưa?
6. Stub Runner đã khởi động lại và resolve đúng artifact chưa?
7. Client consumer đang gọi **đúng server/port** không?
8. Test có thể đang gọi mock/fixture khác không?

Chỉ sau khi xác định rõ **cache layer** mới chọn thao tác làm sạch phù hợp. Xóa toàn bộ `~/.m2/repository` hoặc `~/.gradle/caches` có thể rất tốn kém, ảnh hưởng dự án khác và chưa chắc sửa lỗi ở proxy hay WireMock runtime.

## 19. Candidate version riêng cho commit giúp tránh SNAPSHOT nhập nhằng

Một chiến lược mạnh hơn việc luôn làm mới cache là phát hành **phiên bản ứng viên riêng cho từng PR/commit**:

~~~text
producerCommit: a1b2c3d4
pullRequest: 173
candidateVersion: 1.4.0-rc.pr173.a1b2c3d4

Maven coordinate:
com.example:inventory-service:1.4.0-rc.pr173.a1b2c3d4:stubs
~~~

Ưu điểm:

- Có thể biết chính xác artifact nào cần dùng.
- Hai PR không ghi đè cùng một logical SNAPSHOT.
- Cache theo version bất biến sẽ không vô tình lấy build của commit khác.
- Consumer CI nhận **exact coordinate** từ producer job, không tự chọn `latest`.
- Báo cáo có thể lưu commit SHA, build ID và digest.
- Có thể chạy test consumer với nhiều ứng viên khi cần so sánh.

**Điều kiện bắt buộc:** repository phải ngăn việc **redeploy cùng tọa độ với bytes khác**. Chỉ đặt commit SHA trong tên version nhưng cho phép ghi đè vẫn không đảm bảo tính bất biến.

## 20. Phân biệt workflow SNAPSHOT liên tục và PR compatibility gate

| Bối cảnh | Version strategy | Lý do |
|---|---|---|
| Developer thử nhanh trên máy | `1.4.0-SNAPSHOT`, Stub Runner LOCAL | Đơn giản, nhưng phải install và restart |
| Tích hợp main/develop | SNAPSHOT theo chính sách nhánh | Phù hợp tích hợp đang phát triển |
| PR compatibility gate | Unique candidate version | Có thể truy vết một commit và tránh race |
| Release chính thức | Release version bất biến | Consumer có thể tái lập |
| So sánh A/B | Hai versions khác nhau | Tránh lẫn mappings |

Nếu buộc dùng SNAPSHOT trong PR, hãy cố định **resolved timestamped build hoặc SHA-256 digest** cho CI run, thay vì resolve lại logical version tùy thời điểm.

Không phải mọi phiên bản Stub Runner hỗ trợ đưa timestamped snapshot trực tiếp vào `ids`. Khi thiếu hỗ trợ, **publish candidate version riêng** thường đơn giản và chắc chắn hơn.

## 21. Repository snapshots và releases có nhiệm vụ khác nhau

Ví dụ hệ thống kho artifact phân tách:

~~~text
Snapshots:
com.example:inventory-service:1.4.0-SNAPSHOT:stubs

Releases:
com.example:inventory-service:1.4.0:stubs
~~~

Trong Maven, phần **đích deploy** có thể được mô tả:

~~~xml
<distributionManagement>
    <snapshotRepository>
        <id>company-snapshots</id>
        <url>https://repo.example.invalid/repository/snapshots</url>
    </snapshotRepository>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.invalid/repository/releases</url>
    </repository>
</distributionManagement>
~~~

Ngược lại, `<repositories>`, Maven settings/mirrors và cấu hình của Stub Runner quyết định **nơi tải/resolve**. Publish và resolve không tự động dùng cùng URL.

Ví dụ một số lỗi thực tế:

- Producer deploy vào repository A nhưng consumer đọc repository B.
- Repository release không cho phép lấy SNAPSHOT.
- Producer publish main JAR, bỏ qua classifier `stubs`.
- Metadata mới có entry main JAR nhưng entry stubs vẫn cũ.
- Consumer CI thiếu quyền đọc hoặc đi qua proxy cache khác laptop.
- Repository xóa snapshot cũ theo retention policy, khiến test lịch sử không tải lại được.

Địa chỉ `example.invalid` chỉ là minh họa, không có thật. Không ghi credentials trong POM, annotation, Markdown fixture hay log.

## 22. Cẩn trọng với proxy cache và retention

Repository managers có thể tạo **repository group/proxy**, với TTL cho metadata, chính sách cleanup snapshots và quyền truy cập theo project.

Nếu origin có snapshot B nhưng proxy vẫn trả metadata A, consumer có thể tải đúng artifact theo thông tin proxy đang có — dù đó là bản cũ. Tương tự, một timestamped snapshot đã được test tháng trước có thể bị xóa khi retention chạy.

Để điều tra:

1. Xem producer deploy log và xác nhận origin đã nhận `stubs` artifact.
2. So metadata của origin với metadata mà consumer resolver đọc.
3. Kiểm tra mirror/repository group thực tế và update policy.
4. Xem snapshot retention có xóa artifact đang cần không.
5. Ghi timestamped build hoặc digest vào test report.
6. Với bản cần audit dài hạn, lưu artifact/metadata theo retention policy phù hợp.

**Không nên dùng việc “repository proxy cần một lúc” làm lý do bỏ provenance.** CI cần artifact identity xác định, thay vì phụ thuộc độ trễ tùy may rủi.

## 23. Đọc đúng JAR đã resolve, không chỉ file trong target

Giả sử contract đổi từ:

~~~json
{"sku":"SKU-123","available":true}
~~~

sang:

~~~json
{"sku":"SKU-123","inStock":true}
~~~

Nếu producer build ra JAR mới nhưng Stub Runner LOCAL đang đọc bản cũ trong Maven local repo, chỉ mở `target/...-stubs.jar` **không đủ**.

Cần mở **chính JAR được Stub Runner sử dụng**. Lệnh tham khảo khi có Java CLI:

~~~bash
jar tf target/inventory-service-1.4.0-SNAPSHOT-stubs.jar
~~~

Cấu trúc một JAR có thể có:

~~~text
META-INF/
  com.example/
    inventory-service/
      1.4.0-SNAPSHOT/
        mappings/
          get-stock.json
        contracts/
          inventory/get-stock.groovy
        __files/
          stock-response.json
~~~

Cấu trúc trên mang tính **minh họa**, không phải bảo đảm về layout của mọi phiên bản SCC. Các trường cần kiểm tra trong mappings:

- `request.method` và URL/path/query predicates.
- Headers và bodyPatterns nếu contract cần kiểm tra.
- `response.status`, headers và JSON body.
- Sự hiện diện của field `inStock` mới và việc bỏ field cũ nếu là breaking change có chủ đích.
- Mọi `bodyFileName` đều có response file đóng gói.
- Không có mappings trùng/chồng lấn gây chọn sai scenario.
- Các error cases consumer phụ thuộc đã được sinh.

Nếu JAR được publish sau commit mới nhưng mapping vẫn cũ, nguyên nhân có thể nằm ở **generation hoặc packaging của producer**, không phải cache của Stub Runner.

## 24. SHA-256 giúp xác nhận nội dung artifact

Một checksum được tính trên **JAR đã tải** có thể được so với digest producer CI công bố.

Unix:

~~~bash
sha256sum inventory-service-1.4.0-SNAPSHOT-stubs.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -Path .\inventory-service-1.4.0-SNAPSHOT-stubs.jar
~~~

Ví dụ schema báo cáo:

~~~text
producerCommit: a1b2c3d4
candidateVersion: 1.4.0-rc.pr173.a1b2c3d4
groupId: com.example
artifactId: inventory-service
classifier: stubs
producerArtifactSha256: <digest thật của producer job>
consumerArtifactSha256: <digest thật của JAR consumer tải>
digestMatched: true / false
~~~

Giá trị trong dấu `<...>` phải được thu thập từ hệ thống thật. Một checksum **chỉ có giá trị chứng minh provenance khi so với checksum kỳ vọng**. Timestamp modification của file local không thể thay thế kiểm tra nội dung; file vừa copy có thể chứa mappings cũ.

## 25. Code producer đổi và contract đổi có thể tạo hai kiểu lỗi

| Trường hợp | Producer verification | Consumer verification |
|---|---|---|
| Chỉ implementation producer đổi, contract giữ nguyên | Phải phát hiện nếu code vi phạm contract | Stub không nhất thiết thay |
| Contract đổi, implementation chưa đổi | Generated test có thể đỏ | Chưa đủ điều kiện publish candidate làm chuẩn |
| Code và contract cùng đổi | Generated test có thể xanh | Consumer cũ phải thử **candidate stub mới** |
| Chỉ consumer đổi | Có thể giữ producer artifact | Kiểm tra với những producer versions vẫn cần hỗ trợ |

Ví dụ:

~~~text
Producer A/contract A:
  {"available": true}

Producer B/contract B:
  {"inStock": true}

Checkout consumer cũ:
  vẫn đọc available
~~~

Nếu test Checkout dùng stub A, có thể pass nhưng **chưa kiểm tra B**. Khi dùng stub B, client/DTO cũ có thể fail hoặc trả sai business result. Nếu test vẫn xanh, cần xem deserializer có default `false` cho field thiếu không, assertion có đủ chặt không và client có thật sự gọi mapping B không.

## 26. Consumer test phải dùng HTTP client thực

Một test Stub Runner với candidate version riêng:

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
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.invalid/repository/candidates"
)
class InventoryCandidateContractTest {
    @Autowired
    InventoryClient inventory;

    @Test
    void consumerReadsCandidateResponse() {
        StockResponse result = inventory.getStock("SKU-123");

        assertThat(result.sku()).isEqualTo("SKU-123");
        assertThat(result.inStock()).isTrue();
    }
}
~~~

`InventoryClient`/`StockResponse` là **code consumer giả định** cần được xây dựng trong dự án thật. Repository URL không tồn tại và phải thay bằng nơi CI được cấp quyền. Annotation property support, dependency và test context phải đối chiếu phiên bản SCC.

**Không được mock chính `inventory.getStock(...)` trong bài này**: nếu mock HTTP client rồi trả DTO mẫu, test không sử dụng stub và không thể phát hiện sự khác biệt giữa artifact A và B. Consumer verification cần đi qua method/path/headers, deserialization và error mapping của client thật.

## 27. Multi-producer: mỗi artifact phải có provenance riêng

Checkout có thể phụ thuộc Inventory và Pricing:

~~~text
Inventory candidate:
com.example:inventory-service:1.4.0-rc.pr173.a1b2c3d4:stubs:18081

Pricing stable:
com.example:pricing-service:2.2.0:stubs:18082
~~~

Khi chỉ Inventory thay đổi, test dùng Pricing stable được chốt là hợp lệ. Nhưng không nên lưu một biến `STUB_VERSION` chung khiến một producer dùng nhầm version của producer kia.

Ví dụ nhiều `ids`:

~~~java
@AutoConfigureStubRunner(
    ids = {
        "com.example:inventory-service:1.4.0-rc.pr173.a1b2c3d4:stubs:18081",
        "com.example:pricing-service:2.2.0:stubs:18082"
    },
    stubsMode = StubRunnerProperties.StubsMode.REMOTE
)
~~~

Đây là phần cấu hình minh họa; cần bổ sung URL repository, credentials và wiring HTTP clients thực. Nếu một producer dùng SNAPSHOT, phải ghi **resolved timestamp/digest** của riêng producer đó.

## 28. Version ứng viên bất biến không loại bỏ việc kiểm tra producer thật

Một consumer test có thể pass với candidate artifact đúng và mới, nhưng producer implementation thật **không đáp ứng contract** vì controller/service bị refactor sai. Stub mô phỏng contract chứ không gọi code producer.

Vì vậy phải có **hai cổng riêng**:

1. **Generated producer tests** chạy với code producer của candidate, không dùng fake controller trả response mẫu.
2. **Consumer tests** chạy client/handler thật với stub artifact được sinh từ contract candidate ấy.

Nếu chỉ cổng 2 xanh, chưa chứng minh code producer thật trả đúng. Nếu chỉ cổng 1 xanh, chưa chứng minh consumer cũ hiểu API mới. Provenance liên kết hai cổng bằng **commit, contract revision và stubs JAR cụ thể**.

## 29. CI gate xác nhận stub mới trước khi test consumer

Một pipeline tương thích cần kiểm tra **đúng artifact** ở mọi giai đoạn:

~~~mermaid
flowchart TD
    A["Producer PR: contract + code"] --> B["Sinh generated producer tests"]
    B --> C{"Có test thực thi và PASS?"}
    C -- "Không" --> X["BLOCK"]
    C -- "Có" --> D["Sinh stubs JAR từ cùng commit"]
    D --> E["Publish candidate version duy nhất"]
    E --> F["Consumer CI nhận exact coordinate + checksum"]
    F --> G["Resolve, so checksum và kiểm mappings"]
    G --> H["Khởi động Stub Runner mới"]
    H --> I["Consumer HTTP client thật chạy tests"]
    I --> J{"Compatibility đạt?"}
    J -- "Không" --> X
    J -- "Có" --> K["Tiếp tục release gates"]
~~~

Các bước kiểm tra bắt buộc:

1. Producer generated test count **lớn hơn 0** và tất cả assertions đạt.
2. Artifact được đóng gói từ **đúng producer commit/contract revision**.
3. JAR có classifier `stubs` và mappings cần thiết, không rỗng.
4. Có tọa độ `group:artifact:version:classifier` duy nhất cho candidate.
5. Repository đã publish và consumer resolver có quyền tải.
6. Nếu dùng SNAPSHOT, resolved timestamp hoặc digest phải được ghi lại.
7. Consumer test không gọi một server Stub Runner từ job cũ.
8. Test sử dụng **client thật** của consumer, không chỉ raw HTTP test helper hoặc Mockito.
9. Cả success/error response schemas được kiểm tra khi consumer phụ thuộc.
10. CI chặn nếu tọa độ/digest không khớp candidate hoặc artifact bị mất.
11. Log có đủ commit, artifact, phiên bản plugin, test report để truy vết.

Trong một CI run, **không đổi artifact giữa các test phases** bằng cách resolve lại logical SNAPSHOT. Một test pass với version A và test khác pass với version B không chứng minh cùng một candidate an toàn.

## 30. Khi hai pipelines cùng publish một logical SNAPSHOT

Giả sử:

~~~text
Branch feature-a:
  publish inventory-service:1.4.0-SNAPSHOT
  body: {"available":true}

Branch feature-b:
  publish inventory-service:1.4.0-SNAPSHOT
  body: {"inStock":true}

Consumer PR feature-a:
  resolves 1.4.0-SNAPSHOT
  không rõ resolver chọn build của branch nào
~~~

Repository vẫn có thể lưu **timestamped snapshots riêng**, nhưng metadata của logical version thường hướng tới một snapshot hiện thời. Do đó producer/consumer CI có thể tạo một **race condition**.

Hướng xử lý:

- Không chia sẻ cùng logical SNAPSHOT cho nhiều nhánh cần kiểm chứng độc lập.
- Đặt candidate version có PR/commit/build ID.
- Giới hạn quyền publish logical main SNAPSHOT theo pipeline thích hợp.
- Truyền exact candidate coordinate từ producer job sang consumer job.
- So artifact digest với producer output.
- Ghi resolved timestamp khi buộc dùng SNAPSHOT.
- Không dùng `latest` hoặc `+` ở release gate mà không log/version pin.

SNAPSHOT chung có thể phục vụ nightly integration, nhưng **không nên là định danh duy nhất** của một PR compatibility check.

## 31. Những triệu chứng stale stub và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Hành động phù hợp |
|---|---|---|
| JAR mới nằm trong producer `target`, LOCAL vẫn dùng cũ | Chưa install vào Maven local | Install artifact, kiểm path, restart consumer |
| Snapshot mới remote nhưng HTTP response cũ | WireMock process đã load trước publish | Khởi động lại Stub Runner và kiểm resolved mapping |
| `mvn -U` không đổi stub | Stub Runner resolver khác Maven process hoặc server cũ | Xem log runner, file JAR, digest |
| Gradle refresh nhưng Stub Runner vẫn cũ | Chỉ Gradle cache được refresh | Kiểm tra resolver Stub Runner |
| Metadata ở origin mới, consumer metadata cũ | Proxy/mirror TTL hoặc update policy | So repository endpoint và metadata |
| Artifact có version đúng nhưng field cũ | SNAPSHOT timestamp cũ hoặc producer packaging lỗi | So build timestamp, JAR mapping và checksum |
| JAR đã có `inStock` nhưng client vẫn nhận `available` | Consumer gọi sai port/server | Xem URL và WireMock request journal |
| JAR mới thiếu response body file | Packaging `__files` lỗi | Mở JAR, kiểm `bodyFileName` |
| Stub trả 404 bất ngờ | WireMock unmatched request | So request method/path/header/body |
| Pipeline pass/fail khác nhau dù không đổi code | Mutable version/race/cache TTL | Ghim unique candidate + provenance |
| Producer tests xanh nhưng API thật vẫn sai | Test base fake implementation hoặc tests bị skip | Kiểm generated tests và thử mutation |
| Consumer tests xanh dù candidate breaking | Dùng stub cũ, mock client hoặc assertions yếu | Kiểm artifact và client request thật |

Trình tự debug hữu ích:

~~~text
Producer commit và contract
  -> Generated producer tests
  -> Generated stub mappings
  -> Published JAR cùng checksum
  -> Repository metadata / proxy
  -> Resolver + local cache
  -> Stub Runner startup
  -> WireMock mapping đã nạp
  -> Consumer HTTP request
  -> Deserialization + business assertion
~~~

Hãy tìm **tầng đầu tiên có bằng chứng sai khác** trước khi quyết định xóa cache, thay policy hoặc sửa contract.

## 32. Ghi báo cáo provenance cho mỗi lần kiểm chứng

Một report CI hữu ích:

~~~text
producerService: inventory-service
producerCommit: a1b2c3d4
contractRevision: a1b2c3d4
artifactGroup: com.example
artifactName: inventory-service
artifactVersion: 1.4.0-rc.pr173.a1b2c3d4
classifier: stubs
repository: company-candidates
artifactSha256: <digest do consumer tải và xác nhận>
stubMappingsCount: <số mapping thực>
stubRunnerPort: <port thực>
consumerService: checkout-service
consumerCommit: <consumer commit>
producerTestsExecuted: <test count>
consumerTestsExecuted: <test count>
result: PASS/FAIL
~~~

Nếu dùng SNAPSHOT, ghi thêm:

~~~text
logicalVersion: 1.4.0-SNAPSHOT
resolvedTimestampedVersion: 1.4.0-20261124.051500-12
metadataSource: <origin/proxy cụ thể>
metadataCheckedAt: <thời gian thực>
~~~

Giá trị trong dấu `<...>` phải do pipeline **thu thập**, không tự điền số giả. Một thông báo `PASS` chỉ có ý nghĩa khi có thể trả lời **producer commit nào** và **stub artifact bytes nào** đã được kiểm tra.

## 33. Bài thực hành A — So sánh hai bản SNAPSHOT

**Mục tiêu:** quan sát cùng một logical version nhưng nội dung khác nhau.

1. Viết contract Inventory trả `{"available":true}`.
2. Chạy generated producer tests và đóng gói stubs JAR.
3. Publish `1.4.0-SNAPSHOT` vào **repository thử nghiệm được phép**.
4. Ghi timestamped identity và SHA-256 của artifact đầu tiên.
5. Đổi code và contract thành `{"inStock":true}`, chạy producer tests lại.
6. Publish SNAPSHOT mới theo chính sách repository.
7. So metadata, timestamps, checksums và WireMock mappings của hai builds.
8. Giải thích tại sao consumer khai báo `1.4.0-SNAPSHOT` chưa chắc có thể tái lập test.

**Bằng chứng:** hai artifacts/identities, diff mapping, digests và producer test reports.

## 34. Bài thực hành B — Định vị cache của LOCAL, REMOTE và WireMock

1. Cho Checkout chạy Stub Runner ở `LOCAL`; ghi artifact được nạp.
2. Sửa contract producer nhưng **chưa install**, chạy consumer lại.
3. Install stubs JAR mới vào đúng Maven local repository.
4. Khởi động lại Stub Runner và kiểm response đã đổi chưa.
5. Thực hành với `REMOTE` snapshot repository thử nghiệm.
6. So hiệu quả của `mvn -U` và Gradle `--refresh-dependencies` theo resolver đang dùng.
7. Kiểm tra startup time và application-context caching.
8. Lập bảng “nơi stale → bằng chứng → hành động khắc phục”.

**Bằng chứng:** JAR contents, repository metadata, Stub Runner log, response trước/sau và nhận xét.

## 35. Bài thực hành C — Chặn xanh giả khi API breaking

1. Checkout cũ đọc `available`; producer A có contract tương ứng.
2. Producer ứng viên B đổi field thành `inStock` và vượt qua generated producer tests.
3. Publish stubs JAR B với version ứng viên **duy nhất**.
4. Cho **cùng Checkout cũ** test với stable stub A, ghi kết quả.
5. Chạy Checkout cũ với candidate B, mong đợi lỗi khi không tương thích.
6. Nếu không đỏ, điều tra client có bị mock, DTO có default field, assertion có yếu hoặc version có sai không.
7. Khôi phục tương thích bằng giai đoạn mở rộng API hoặc versioning có chủ đích.
8. Chạy lại producer tests + consumer tests với artifact mới.
9. Lưu cả hai tọa độ, commit, digest và báo cáo kết quả.

**Bằng chứng:** test reports trước/sau, mapping changes, candidate version và quyết định migration.

## 36. Checklist trước khi merge

- [ ] Generated producer tests được sinh và thực thi trên code producer thật.
- [ ] Số contract tests > 0, không coi skip/zero-test là thành công.
- [ ] Stubs JAR được tạo từ cùng producer commit và contract revision.
- [ ] Classifier `stubs`, artifact version và repository đúng.
- [ ] SNAPSHOT đã xác định resolved timestamp/digest, không chỉ logical version.
- [ ] Candidate version duy nhất hoặc bị ràng buộc immutability theo repository policy.
- [ ] Không dùng `latest`/`+` mơ hồ cho PR compatibility gate.
- [ ] Repository deploy/resolve endpoints và credentials được phân biệt rõ.
- [ ] Maven/Gradle/Stub Runner/proxy cache được xử lý theo **đúng tầng**.
- [ ] Stub Runner đã nạp mappings từ JAR hiện hành.
- [ ] Consumer HTTP client/handler thật gọi stub đúng host/port.
- [ ] Stub mappings có các error cases và matchers quan trọng.
- [ ] Có negative test để chứng minh breaking change làm consumer test đỏ.
- [ ] Nếu có nhiều producer, ghi tọa độ/commit/digest cho từng dependency.
- [ ] CI log đủ thông tin provenance và artifact checksum.
- [ ] Snapshot retention và release immutability được kiểm soát.
- [ ] Không có secret, token hoặc dữ liệu khách hàng thật trong stub fixtures.
- [ ] Compatibility gate chặn nếu artifact không tương ứng ứng viên.

## 37. Câu hỏi tự kiểm tra

**1. `1.4.0-SNAPSHOT` có luôn đại diện cho một artifact bất biến không?**

Không. Logical SNAPSHOT có thể ánh xạ tới nhiều builds theo thời gian. Muốn biết bản consumer thực dùng, cần timestamped identity hoặc digest.

**2. Vì sao `mvn -U` không chắc khiến Stub Runner trả response mới?**

Vì nó có phạm vi Maven resolution tương ứng, không tự cập nhật Stub Runner resolver độc lập hoặc reload WireMock mappings đã được nạp.

**3. LOCAL có luôn cũ hơn REMOTE không?**

Không. LOCAL vừa install có thể mới, REMOTE proxy vẫn cache metadata cũ; cần chứng cứ artifact cụ thể.

**4. Producer tests B pass, consumer dùng stub A và pass có đủ phát hành B không?**

Không. Consumer phải thử với **candidate stub B**, vì contract B có thể khác A.

**5. Tại sao version riêng gắn commit tốt hơn logical SNAPSHOT cho PR?**

Nó ngăn race giữa nhiều candidate và dễ tái lập, miễn repository chặn ghi đè tọa độ đã publish.

**6. Vì sao phải mở JAR và so checksum?**

Vì tên logical version không phản ánh bytes. JAR mappings và checksum cho biết nội dung thực sự được nạp.

**7. Stub Runner start lúc 09:00, producer publish lúc 09:30: vì sao 09:35 server vẫn trả response cũ?**

WireMock đã load mappings lúc startup. Publish artifact mới không đồng nghĩa hot reload server hiện tại.

**8. Có nên xóa sạch Maven repository khi consumer test fail không?**

Không. Hãy xác định tầng stale: build output, remote metadata, proxy, local resolver, Stub Runner hoặc client URL rồi xử lý riêng.

## 38. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, stub packaging và Stub Runner.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner.html): artifact resolution, LOCAL/REMOTE và cấu hình server.
- [Spring Cloud Contract — Maven](https://docs.spring.io/spring-cloud-contract/reference/project-features-maven.html): sinh producer tests và stub JAR.
- [Spring Cloud Contract — Gradle](https://docs.spring.io/spring-cloud-contract/reference/project-features-gradle.html): Gradle tasks và publishing.
- [Apache Maven — Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): local/remote repository semantics.
- [Apache Maven — Settings](https://maven.apache.org/settings.html): mirrors, credentials, repository policies.
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html): distribution management và repositories.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): dynamic/changing module caching.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): mapping behavior và response files.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): chẩn đoán unmatched requests.

**Lưu ý phiên bản:** Maven metadata/policies, timestamped snapshots, Stub Runner resolver và annotation `repositoryRoot`, repository proxy, Gradle cache behavior, artifact packaging có thể khác theo bộ Spring Boot–Spring Cloud Release Train–SCC–Maven/Gradle. Các URL `example.invalid` chỉ minh họa. Khi triển khai hãy kiểm tra **metadata, output build, JAR digest, mappings và resolved artifact thực tế**. Các lệnh trong bài chỉ mang tính hướng dẫn, chưa chạy trên repository tại bước biên soạn.

---

**Điểm cần nhớ:** `-SNAPSHOT` là **logical version mutable** và cache có thể nằm ở nhiều tầng từ Maven/Gradle tới repository proxy, Stub Runner và WireMock in-memory mappings. Vì vậy, câu hỏi quyết định không phải “đã dùng SNAPSHOT chưa?” mà là **“consumer test đã thực sự chạy với stubs JAR sinh từ producer commit nào?”**. Để phát hiện thay đổi API không tương thích, hãy kiểm chứng producer code thật, publish candidate có provenance rõ, nạp đúng stub rồi chạy **consumer client thật** trong CI.
