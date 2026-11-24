# Kiểm thử hồi quy pipeline công bố và tải stub

## Mục tiêu học tập

**Spring Cloud Contract** giúp producer và consumer thống nhất hành vi HTTP hoặc messaging qua **Groovy/YAML DSL**. Producer sinh test kiểm chứng implementation và đóng gói **stub artifact**; consumer dùng **Stub Runner** tải stub để kiểm tra client/handler. Trong CI/CD, chuỗi công bố và tải stub cần được kiểm thử hồi quy để thay đổi build tool, plugin, repository hoặc version không âm thầm làm mất artifact hay khiến consumer dùng nhầm bản.

Bài thuộc chương **Tương thích công cụ**, tập trung vào **kiểm thử hồi quy pipeline công bố và tải stub**. Sau bài, bạn có thể:

- Thiết kế end-to-end regression test cho publish → resolve → Stub Runner → consumer verification.
- Phân biệt contract definitions JAR, producer application JAR và producer stubs JAR.
- Kiểm tra Maven/Gradle publication, classifier `stubs`, POM/metadata và repository layout.
- Xây dựng compatibility matrix cho JDK, Maven/Gradle, Spring Boot/Cloud, Spring Cloud Contract và repository manager.
- Phân biệt lỗi contract discovery, generated tests, packaging, publishing, download, extraction, startup và request matching.
- Dùng version/digest/provenance để tái lập pipeline.
- Thiết kế smoke tests, negative tests, upgrade tests và release gates.
- Chẩn đoán build xanh nhưng consumer vẫn dùng stub cũ hoặc thiếu mapping.

> **Nguyên tắc:** regression phải kiểm tra **artifact mà consumer thực sự tải và chạy**, không chỉ file trong thư mục build của producer. Build xanh ở producer và consumer riêng rẽ chưa đủ nếu hai bên không dùng cùng tọa độ/version/digest.

## 1. Bối cảnh: một thay đổi công cụ có thể phá cả chuỗi stub

Giả sử **Inventory Service** là producer và **Checkout Service** là consumer. Contract định nghĩa:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

Response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-101","available":true,"quantity":8}
~~~

Producer build và publish:

~~~text
com.example:inventory-producer:2.3.0:stubs
~~~

Checkout tải stub qua Stub Runner, khởi động WireMock và test HTTP client.

Một lần nâng cấp pipeline có thể thay đổi plugin Spring Cloud Contract, Maven/Gradle publication, Spring Boot/Cloud BOM, JDK, wrapper, generated mapping layout, repository credentials, snapshot metadata hoặc cách Stub Runner resolve classifier.

Kết quả có thể là:

~~~text
Producer build: SUCCESS
Application JAR: published
Stub JAR: missing or stale

Consumer build: SUCCESS
Stub Runner: resolves old cached artifact
Consumer tests: PASS
Production producer: changed behavior
~~~

Đây là **false green**: không có bằng chứng consumer đã kiểm thử stub từ producer revision mới.

### Chuỗi cần kiểm chứng

~~~mermaid
flowchart LR
    A["Contract source + revision"] --> B["Producer discovery"]
    B --> C["Generate producer tests"]
    C --> D["Run against producer"]
    D --> E{"PASS?"}
    E -->|No| X["Block publish"]
    E -->|Yes| F["Package :stubs JAR"]
    F --> G["Publish exact coordinates"]
    G --> H["Resolve from clean consumer"]
    H --> I["Stub Runner starts"]
    I --> J["Consumer tests"]
    J --> K{"PASS?"}
    K -->|No| X
    K -->|Yes| L["Record digest + toolchain"]
~~~

Mỗi mũi tên là một ranh giới có thể lỗi. Đặc biệt phải chứng minh artifact được publish có thể tải từ **môi trường consumer**.

## 2. Ba loại artifact và chuỗi version

| Artifact | Tọa độ ví dụ | Nội dung và mục đích |
|---|---|---|
| **Contract definitions JAR** | `com.example.contracts:inventory-contracts:1.6.0` | Groovy/YAML DSL để producer sinh tests |
| **Producer application JAR** | `com.example:inventory-producer:2.3.0` | Ứng dụng Inventory |
| **Producer stubs JAR** | `com.example:inventory-producer:2.3.0:stubs` | Mappings/fixtures hoặc message stub definitions cho consumer |

Một pipeline có thể dùng các version khác nhau:

~~~text
Contract definitions: com.example.contracts:inventory-contracts:1.6.0
Producer application:  com.example:inventory-producer:2.3.0
Producer stubs:        com.example:inventory-producer:2.3.0:stubs
~~~

Contract JAR `1.6.0` không bắt buộc cùng version producer `2.3.0`. Điều cần giữ là **liên kết truy vết**: producer revision nào đã kiểm chứng contract revision nào và stub artifact nào được tạo từ lần kiểm chứng đó.

Một publication có thể thành công với main artifact nhưng bỏ quên classifier:

~~~text
Published:
  inventory-producer-2.3.0.pom
  inventory-producer-2.3.0.jar

Missing:
  inventory-producer-2.3.0-stubs.jar
~~~

Nếu chỉ kiểm tra application JAR, pipeline sẽ xanh dù consumer không resolve được stub. Ngược lại, JAR có tên `*-stubs.jar` vẫn có thể rỗng hoặc chứa mappings cũ; cần kiểm tra nội dung và consumer runtime.

## 3. Pipeline regression test cần chứng minh gì?

Đây là scenario tích hợp giữa producer build, artifact repository và consumer build, không chỉ là unit test của một script.

1. Producer phát hiện đúng contract files.
2. Generated tests có số lượng mong đợi và thực sự được thực thi.
3. Tests chạy trên producer implementation, đúng base class/test mode.
4. Stub JAR được tạo với classifier đúng.
5. JAR có mappings/fixtures/message definitions cần thiết.
6. Publication dùng đúng coordinates, repository và metadata.
7. Consumer tải artifact bằng môi trường sạch.
8. Consumer dùng đúng version/digest đã publish.
9. Stub Runner khởi động server/message stub.
10. Consumer client/handler tương tác và assertions có ý nghĩa.
11. Cấu hình sai có chủ đích khiến pipeline fail đúng tầng.
12. Toolchain upgrade không làm thay đổi behavior ngoài chủ đích.

| Loại test | Phạm vi | Giá trị |
|---|---|---|
| Build logic test | Task/script/plugin config nhỏ | Bắt lỗi cục bộ |
| Producer contract test | DSL → generated test → producer | Chứng minh producer đáp ứng contract |
| Packaging test | JAR/classifier/entries | Chứng minh output đúng |
| Publication test | Upload + metadata | Chứng minh registry nhận đúng tọa độ |
| Resolution test | Consumer resolve | Chứng minh resolver tải được |
| Stub Runner smoke | Resolve/extract/start | Chứng minh runtime có mapping |
| Consumer compatibility | Client/handler gọi stub | Chứng minh consumer dùng được interface |
| Toolchain test | Ma trận version | Phát hiện upgrade regression |

Có thể chạy fast checks cho PR và full matrix theo lịch/trước release. Không bỏ hẳn end-to-end test chỉ vì nó chậm.

## 4. Contract mẫu dùng cho regression pipeline

### Groovy DSL

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Inventory returns deterministic stock for SKU-101'

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

### YAML DSL tương đương

~~~yaml
description: 'Inventory returns deterministic stock for SKU-101'
request:
  method: GET
  url: /api/inventory/SKU-101
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-101
    available: true
    quantity: 8
~~~

Chỉ dùng một định nghĩa cho cùng request trong pipeline demo để tránh duplicate mappings. Fixture cố định giúp kiểm tra kết quả không phụ thuộc clock, UUID hoặc database state.

Regression nên giữ ổn định:

- Contract được discover từ đúng source path.
- Request method/path/header không đổi ngoài chủ đích.
- JSON boolean `true` và number `8` giữ đúng kiểu.
- Producer test vẫn assert status `200` và body.
- Stub mapping chứa request matcher và response fixture.
- Consumer nhận đúng JSON qua Stub Runner.
- Artifact version/classifier không bị thay đổi ngoài chủ đích.

## 5. Compatibility matrix cho toolchain

Không nên nâng đồng thời JDK, Spring Boot, Spring Cloud Contract plugin, Gradle và repository nếu muốn tìm nguyên nhân regression.

| Lớp công cụ | Biến thể cần quản lý | Kiểm tra |
|---|---|---|
| JDK | Major version/distribution | Compile, test runtime, encoding |
| Maven | Wrapper/version | Lifecycle, plugin goals, attached artifacts |
| Gradle | Wrapper/version | Task graph, cache, publication |
| Spring Boot | Release line | Test context, dependency alignment |
| Spring Cloud | BOM/release train | Compatibility với Boot |
| Spring Cloud Contract | Maven/Gradle plugin | DSL parser, generated tests, stubs |
| Test framework | JUnit 4/5, Spock nếu dùng | Generated test source/engine |
| Stub Runner | Version tương thích | Resolver và server startup |
| WireMock/binder | Dependency version | Mapping và message behavior |
| Repository manager | Nexus/Artifactory/config | Metadata, snapshots, auth, checksum |
| CI runner | OS/image/architecture | Path, permission, TLS, network |

Không chạy mọi tổ hợp. Phân matrix thành:

- **Supported baseline:** tổ hợp dự án chính thức hỗ trợ.
- **Current release:** tổ hợp đang build/release.
- **Upgrade candidate:** tổ hợp dự kiến nâng.
- **Compatibility boundary:** phiên bản cũ/mới cần giữ tương thích.
- **Negative cases:** cấu hình sai có chủ đích để kiểm tra fail rõ.

Chỉ kiểm tra tổ hợp framework hỗ trợ hoặc tổ chức cam kết. Build được trên một tổ hợp bất kỳ không tự chứng nhận nó tương thích.

## 6. Xác định toolchain thực sự đang chạy

### Maven

Kiểm tra Maven Wrapper, `spring-cloud-contract-maven-plugin`, Spring Boot/Cloud BOM, Surefire/Failsafe, JUnit engine, repository và profile CI.

~~~bash
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree
~~~

Các lệnh cho biết Maven/JDK, POM hiệu lực và dependency graph. POM cha không bảo đảm plugin version đang chạy nếu child module override hoặc profile khác.

### Gradle

Kiểm tra Gradle Wrapper, Spring Cloud Contract plugin, plugin repositories, dependency constraints, `maven-publish`, test source sets và build cache.

~~~bash
./gradlew --version
./gradlew :inventory-producer:tasks --all
./gradlew :inventory-producer:dependencies
~~~

Với multi-project, kiểm tra **subproject** publish artifact. Root `version`/`group` không bảo đảm mọi subproject dùng cùng giá trị.

### Ghi nhận trước/sau upgrade

~~~text
Before:
  JDK: <version-A>
  Gradle: <version-A>
  SCC plugin: <version-A>
  Producer tests: <count-A>
  Stub artifact: <coordinate-A>
  Stub digest: <digest-A>

After:
  JDK: <version-B>
  Gradle: <version-B>
  SCC plugin: <version-B>
  Producer tests: <count-B>
  Stub artifact: <coordinate-B>
  Stub digest: <digest-B>
~~~

Digest thay đổi không tự chứng minh regression vì metadata/timestamp/generated source có thể đổi. Cần so **tọa độ, nội dung mapping và hành vi consumer**.

## 7. Producer regression: từ DSL tới stub JAR

~~~mermaid
flowchart TD
    A["Pinned contract revision"] --> B["Pinned toolchain"]
    B --> C["Discover contract files"]
    C --> D{"Expected contracts > 0?"}
    D -->|No| X["Fail"]
    D -->|Yes| E["Generate producer tests"]
    E --> F["Compile and execute"]
    F --> G{"Tests executed and PASS?"}
    G -->|No| X
    G -->|Yes| H["Generate mappings"]
    H --> I["Package classifier stubs"]
    I --> J["Inspect archive and metadata"]
    J --> K["Publish to staging"]
~~~

### Gate A — Discovery

Kiểm tra path và số contract. Nếu module phải có contract nhưng plugin phát hiện 0 file, pipeline phải fail thay vì đóng gói JAR rỗng.

Nguyên nhân thường gặp:

- `contractsDslDir` (Gradle) hoặc `contractsDirectory` (Maven) sai.
- Contract JAR ngoài dự án có `contractsPath` sai.
- `includedFiles`/`ignoredFiles` loại hết DSL.
- Multi-module build chạy task ở sai project.
- Source/resource path đổi sau plugin upgrade.

### Gate B — Producer verification

Generated tests phải được sinh từ đúng revision, compile với test framework, kế thừa đúng base class, gọi producer implementation, thực sự chạy và PASS.

**Generated source tồn tại không phải producer verification.** Build SUCCESS nhưng 0 tests cũng không phải bằng chứng.

### Gate C — Packaging

Kiểm tra task/goal tạo stub thực sự chạy, classifier `stubs` được attach, mappings/fixtures/message definitions đầy đủ, body files được đóng gói và artifact cùng revision với tests đã PASS.

## 8. Maven producer: lifecycle và attached classifier

Với Maven producer đã cấu hình `spring-cloud-contract-maven-plugin`:

~~~bash
./mvnw -B -ntp clean verify
~~~

Cài vào Maven local repository:

~~~bash
./mvnw -B -ntp install
~~~

Đưa artifacts lên remote repository:

~~~bash
./mvnw -B -ntp deploy
~~~

| Goal/lifecycle | Kết quả chính |
|---|---|
| `verify` | Chạy verification goals đã cấu hình |
| `install` | Cài main và attached artifacts vào Maven local |
| `deploy` | Upload artifacts đã attach lên remote repository |

Maven lifecycle chỉ chạy plugin goals đã bind. Nếu plugin contract chưa được bind đúng phase, `verify` vẫn có thể thành công mà không sinh producer tests/stubs.

Regression assertions:

- Effective POM có đúng plugin version.
- Plugin được enable trong producer module.
- Generated tests được test runner nhận ra.
- Output có stub JAR.
- `install` đưa classifier `stubs` vào local repo.
- `deploy` upload main JAR, POM và stub JAR.
- Consumer build riêng resolve được classifier.

Có thể kiểm tra resolver bằng Maven Dependency Plugin:

~~~bash
./mvnw -B -ntp dependency:get -Dartifact=com.example:inventory-producer:2.3.0:jar:stubs -Dtransitive=false
~~~

Lệnh dùng một dòng để chạy được trong PowerShell, CMD hoặc Bash. Tọa độ CLI là `group:artifact:version:packaging:classifier`. Lệnh này không khởi động Stub Runner và không chứng minh JAR có mapping.


## 9. Gradle producer: task graph và publication

Với Gradle plugin hiện đại, các task thường gặp gồm `contractTest` và `verifierStubsJar`; **task availability phải kiểm tra ở plugin version thực tế**.

~~~bash
./gradlew --version
./gradlew :inventory-producer:tasks --all
./gradlew :inventory-producer:contractTest
./gradlew :inventory-producer:verifierStubsJar
~~~

Hãy kiểm tra task graph, output và exit code, không chỉ chạy một tên task rồi kết luận.

### Publication với Maven Publish

Một publication minh họa:

~~~groovy
plugins {
    id 'java'
    id 'maven-publish'
    // Spring Cloud Contract plugin/version được cấu hình riêng.
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

Đây là **đoạn minh họa**, không phải toàn bộ build file. Task `verifierStubsJar` phải tồn tại; artifact phải mang classifier `stubs` đúng theo plugin/version, và publication còn cần khai báo repository upload.

Nếu publication tên `verifiedStubs`, Gradle có thể tạo task dạng `publishVerifiedStubsPublicationToMavenLocal`. Hãy kiểm tra `tasks --all` thay vì giả định tên task của mọi dự án.

Regression assertions cho Gradle:

- `contractTest` được thực thi trong project đúng.
- Test report có số test thực thi và kết quả PASS.
- `verifierStubsJar` tạo JAR trong output directory.
- JAR có classifier đúng và entries mong đợi.
- Publication trỏ đúng group/artifact/version.
- Task publish chạy và repository nhận file đúng.
- Consumer job sạch resolve được artifact qua cùng tọa độ.

**`mavenLocal()` trong repositories chỉ cho phép Gradle đọc local Maven repository; nó không tự publish artifact vào đó.**

## 10. Kiểm tra archive và Maven metadata

Regression pipeline cần inspect artifact **sau packaging và trước promotion**.

~~~bash
jar tf inventory-producer-2.3.0-stubs.jar
~~~

Một layout Spring Cloud Contract thường gặp:

~~~text
META-INF/
META-INF/MANIFEST.MF
META-INF/com.example/inventory-producer/2.3.0/
META-INF/com.example/inventory-producer/2.3.0/mappings/
META-INF/com.example/inventory-producer/2.3.0/mappings/stockAvailable.json
~~~

Layout thực tế phụ thuộc plugin/configuration, consumer-specific stubs và loại contract. Đây là ví dụ, không phải schema bắt buộc cho mọi version.

Trong Maven repository, file thường có dạng:

~~~text
com/example/inventory-producer/2.3.0/
  inventory-producer-2.3.0.pom
  inventory-producer-2.3.0.jar
  inventory-producer-2.3.0-stubs.jar
~~~

Kiểm tra:

1. File `-stubs.jar` tồn tại.
2. POM/metadata phù hợp publication.
3. JAR có mapping cho contract cần test.
4. Fixtures bên ngoài mapping có mặt.
5. Không bị nhầm với application fat JAR.
6. Checksum/digest được lưu để so sánh với consumer download.

Một JAR có nhiều mappings không chứng minh mapping `GET /api/inventory/SKU-101` có mặt. Regression test nên kiểm tra entry cụ thể hoặc chạy consumer smoke test để xác nhận mapping thực sự được nạp.

Nếu mapping tham chiếu `bodyFileName`, file response tương ứng cũng phải có trong archive theo convention của Stub Runner/WireMock. Không chỉnh sửa archive đã publish; nếu nội dung sai, sửa DSL/build và tạo artifact mới.

## 11. Publish vào staging repository trước khi release

Không nên kiểm thử end-to-end bằng cách ghi thẳng vào release repository bất biến mỗi lần chạy PR.

~~~text
Producer PR / candidate commit
    |
    v
Producer verification PASS
    |
    v
Package stub JAR
    |
    v
Publish to isolated staging repository
    |
    v
Consumer smoke test resolves exact candidate
    |
    v
Compatibility tests PASS
    |
    v
Approval
    |
    v
Promote the same artifact to release repository
~~~

### Vì sao promote artifact đã test?

Nếu release job rebuild sau consumer test, output có thể khác do commit, dynamic dependencies, toolchain, contract DSL, timestamp/metadata hoặc cache/repository.

Tốt nhất **promote cùng candidate artifact theo digest**, thay vì rebuild rồi chỉ dựa vào cùng tên version.

| Thuộc tính | Staging | Release |
|---|---|---|
| Đối tượng | Candidate PR/build | Artifact đã duyệt |
| Version | Build ID/RC/unique candidate | Release version |
| Quyền ghi | Pipeline CI giới hạn | Protected release job |
| Overwrite | Theo policy, nên tránh | Nên bất biến |
| Consumer | Smoke/compatibility test | Consumer builds chính thức |
| Bằng chứng | Test reports + digest | Promotion record + cùng digest |

Không dùng một mutable version cho nhiều PR song song. Candidate phải có ID duy nhất để tránh job ghi đè artifact của job khác.

## 12. Consumer resolution regression: tải từ môi trường sạch

Producer publish thành công chưa đủ. Consumer cần resolve artifact trong **environment tương tự CI thực tế**, không dựa vào Maven local cache trên máy developer.

### Stub Runner REMOTE

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
    repositoryRoot = "https://repo.example.invalid/repository/staging-stubs"
)
class CheckoutStubPipelineSmokeTest {

    @StubRunnerPort("inventory-producer")
    int inventoryPort;

    @Test
    void stubRunnerStartsInventoryStub() {
        // Dùng HTTP client của consumer gọi:
        // http://localhost:<inventoryPort>/api/inventory/SKU-101
        // Assert status và body theo contract.
    }
}
~~~

Đây là skeleton; cần thay URL, dependencies, client và assertions theo project. `example.invalid` là placeholder.

### Clean environment nghĩa là gì?

- Maven local repository trống hoặc cache riêng cho run.
- Không có stub JAR cũ được copy thủ công.
- Không có dependency resolution từ IDE cache.
- Credentials lấy từ CI secret manager, với quyền read.
- Repository root đúng staging repository đã publish candidate.
- Version cụ thể, không dùng `+` hoặc `latest`.
- Artifact digest tải xuống được ghi nhận.

Có thể tạo Maven local repository tạm bằng `-Dmaven.repo.local=...` cho bước diagnostic; Gradle có cache riêng và cần cấu hình cô lập phù hợp. Không xóa global cache dùng chung tùy tiện; dùng namespace/cache mới cho regression job.

Consumer smoke test cần assert:

- Stub Runner resolve đúng tọa độ/classifier.
- Server khởi động và cấp port.
- Request đến đúng URL/method.
- Response status/header/body đúng.
- JSON type đúng (boolean/number/string).
- Error case có error code cụ thể nếu được kiểm thử.
- Consumer client thật parse và xử lý response.

**Chỉ khởi động context thành công chưa đủ** nếu test không gửi request tới mapping thực tế.

## 13. Ba chế độ tải stub và ý nghĩa regression

| Mode | Nguồn | Regression test phải chứng minh |
|---|---|---|
| `LOCAL` | Maven local repository | Stub đã install vào đúng local repo của consumer process |
| `REMOTE` | Maven-compatible repository | Consumer tải được từ đúng repository, với credentials/quyền thực |
| `CLASSPATH` | Test runtime classpath | Stub artifact/resources thực sự có trong classpath và đúng layout |

### LOCAL

Producer có thể chạy `install` để đưa artifact vào Maven local. Nhưng nếu producer và consumer chạy ở **hai runner khác nhau**, local repository của job producer không tự xuất hiện ở job consumer.

~~~text
Producer contractTest
    |
    v
Producer verifierStubsJar
    |
    v
Publish/install stubs to Maven local
    |
    v
Consumer test with stubsMode=LOCAL
~~~

Phải kiểm tra local path thực tế vì Maven settings có thể override `localRepository`. Nếu pipeline dùng container/job riêng, dùng remote staging hoặc chuyển artifact có provenance rõ ràng.

### REMOTE

`repositoryRoot` phải trỏ vào **gốc Maven repository**, không phải application URL, file JAR cụ thể hoặc folder version. Regression dùng identity/network policy giống consumer CI để bắt lỗi 401/403, TLS, proxy và permission.

### CLASSPATH

Đưa stub JAR vào test runtime classpath không tương đương với việc chỉ thấy file trong `build/libs` hoặc `~/.m2`. Regression kiểm tra test dependency resolution và archive layout. Mode này phù hợp khi stubs được đưa vào classpath theo cấu hình dự án.

Các mode là lựa chọn nguồn, không thay đổi yêu cầu rằng stub phải chứa mappings/definitions hợp lệ.

## 14. Kiểm tra Stub Runner port và request matching

Sau khi tải thành công, Stub Runner cần khởi động stub server hoặc cấu hình messaging stubs. Với HTTP, dùng cổng runtime:

~~~java
@StubRunnerPort("inventory-producer")
int inventoryPort;
~~~

Không hardcode `localhost:8080` hoặc `localhost:0` nếu Stub Runner dùng cổng động. Consumer phải lấy cổng thực qua `@StubRunnerPort` hoặc `StubFinder`.

Một smoke test có thể dùng Spring `RestClient` (Spring Framework 6.1+):

~~~java
import org.springframework.web.client.RestClient;

RestClient client = RestClient.builder()
    .baseUrl("http://localhost:" + inventoryPort)
    .build();

String body = client.get()
    .uri("/api/inventory/SKU-101")
    .header("Accept", "application/json")
    .retrieve()
    .body(String.class);
~~~

Đây là đoạn minh họa; test đầy đủ cần assert status, parse JSON và kiểm tra field/type.

### WireMock 404 không phải Maven 404

- **Maven 404:** resolver không tìm thấy file artifact ở repository.
- **WireMock 404:** server đã chạy nhưng request không match mapping (hoặc mapping cố ý trả business 404).

Khi consumer nhận 404, ghi URL gồm host/port/path, method, query, headers và body; xem unmatched request journal. Đừng lập tức publish lại artifact nếu mapping đã có mà path consumer gửi sai.

Nếu test chỉ assert `status == 404`, URL typo có thể làm WireMock trả unmatched 404 và test vẫn xanh. Với business not found, assert thêm error body/code như `SKU_NOT_FOUND`.

## 15. Consumer compatibility test với artifact chính xác

Regression có ý nghĩa phải chứng minh **consumer thực sự dùng artifact vừa được publish**, không chỉ artifact bất kỳ có cùng tên.

~~~text
Requested Stub Runner ID:
  com.example:inventory-producer:2.3.1:stubs:0

Resolved artifact:
  com.example:inventory-producer:2.3.1:stubs

Repository:
  staging-stubs

SHA-256:
  <digest>

Consumer:
  checkout source revision <consumer-sha>

Result:
  GET /api/inventory/SKU-101 -> 200
  JSON sku=SKU-101
  JSON available=true
  JSON quantity=8
~~~

Các giá trị digest/SHA là placeholder, phải lấy từ pipeline.

Consumer test chứng minh artifact resolve được, Stub Runner đọc và khởi động, client gửi đúng tương tác và consumer xử lý được response/message mô phỏng.

Consumer test **không chứng minh** producer thật đang deploy đúng revision, producer tests đã PASS, transaction/concurrency đúng ngoài contract, hay artifact có provenance nếu không ghi nhận.

**Consumer test không thay producer verification.** Pipeline cần cả hai bằng chứng và liên kết chúng bằng version/revision/digest.

## 16. Regression negative tests: chứng minh gate phát hiện lỗi

Một pipeline tốt không chỉ thử đường xanh. Nó cần những tình huống cố ý sai để xác nhận gate fail đúng nơi.

| Negative scenario | Thay đổi giả lập | Kết quả mong đợi |
|---|---|---|
| Không tạo stub JAR | Bỏ task/package stubs | Packaging gate fail |
| Sai classifier | Publish main JAR nhưng thiếu `stubs` | Artifact resolution fail |
| Sai version | Consumer yêu cầu version chưa publish | Resolve fail, không fallback |
| Sai group/artifact | ID trỏ tọa độ khác | Resolve fail rõ coordinates |
| Sai repository root | Trỏ application URL/repo khác | Resolve fail |
| Thiếu mapping | JAR không có mapping cần | Archive/smoke gate fail |
| Thiếu body file | Mapping tham chiếu file không có | Packaging/runtime gate fail |
| Request mismatch | Đổi path/method/header | WireMock unmatched request, test fail |
| Test bị skip | Producer tests không thực thi | Producer gate fail dù build success |
| Stub cũ trong cache | Consumer lấy version/digest cũ | Digest/version assertion fail |
| Credentials sai | Token thiếu read permission | Download fail 401/403 |
| Snapshot mutable | Cùng tọa độ có bytes khác | Provenance/digest check phát hiện |

Negative tests chạy trong repository test harness hoặc staging riêng. **Không cố tình làm hỏng release repository chính thức** để thử failure.

Nếu producer tests fail, pipeline không được publish. Nếu publish fail, consumer test không được dùng stub cũ từ cache rồi tạo PASS giả. Nếu consumer test fail, release promotion bị chặn theo policy.


## 17. Contract definitions, producer stubs và consumer trong cùng pipeline

Một tổ chức có thể dùng common contract repository:

~~~text
shared-contracts:
  com/example/inventory-producer/checkout-consumer/stockAvailable.groovy
~~~

Producer tải definitions, sinh tests, verify code rồi publish producer stubs. Consumer tải **producer stub artifact**.

~~~mermaid
sequenceDiagram
    participant CR as Contract repository
    participant P as Inventory producer CI
    participant R as Maven staging repository
    participant C as Checkout consumer CI
    participant Q as Release gate
    CR->>P: Contract definitions revision
    P->>P: Generate + run producer tests
    alt Producer PASS
        P->>P: Package classifier stubs
        P->>R: Publish candidate with digest
        C->>R: Resolve exact producer stubs
        C->>C: Stub Runner + consumer tests
        alt Consumer PASS
            C->>Q: Compatibility evidence
            Q->>R: Promote same artifact
        else Consumer FAIL
            C->>Q: Block and report
        end
    else Producer FAIL
        P->>Q: Block publication
    end
~~~

### Version không nhất thiết giống nhau

~~~text
Contract definitions: shared-contracts:1.6.0
Producer application: inventory-producer:2.3.1
Producer stubs:       inventory-producer:2.3.1:stubs
Consumer:             checkout-service:4.8.0
~~~

Đây là các version khác nhau có chủ đích. Cần ghi producer stubs `2.3.1` được sinh từ contract definitions `1.6.0` và revision cụ thể sau khi producer tests PASS.

Consumer nên ghi **resolved producer stub version**, không chỉ version của chính Checkout.

## 18. Regression test cho artifact repository metadata

Một file JAR tải được chưa chắc publication đã hoàn chỉnh. Maven resolution có thể cần POM và metadata theo loại/version.

### Kiểm tra tối thiểu

- Main POM được publish với group/artifact/version đúng.
- Stub JAR được attach với classifier `stubs`.
- Packaging/extension là JAR theo cấu hình dự án.
- Release version có metadata/đường dẫn ổn định.
- Snapshot version có `maven-metadata.xml` và resolver nhận timestamped snapshot đúng.
- Repository checksum/signature (nếu policy bật) được tạo và xác minh.
- Consumer read credentials có quyền với cả POM và JAR.
- Không redirect tới trang login trả status 200 HTML thay cho JAR.
- Repository mirror/proxy không trả artifact cũ từ cache.

### Tại sao phải test từ consumer identity?

Producer CI thường có quyền write, consumer CI chỉ có quyền read. Publish job có thể upload thành công nhưng consumer identity vẫn không đọc được do ACL khác nhau.

Regression nên chạy bằng **read-only identity** giống consumer. Không dùng publish token để test download rồi kết luận permission consumer đúng.

### Kiểm tra bytes

Linux/macOS:

~~~bash
sha256sum inventory-producer-2.3.1-stubs.jar
~~~

PowerShell:

~~~powershell
Get-FileHash .\inventory-producer-2.3.1-stubs.jar -Algorithm SHA256
~~~

So digest với output/provenance producer job. Hash xác nhận **bytes giống nhau**, không tự chứng minh nội dung đúng hay an toàn; cần archive inspection và test reports.

## 19. Git SCM và Maven repository: hai pipeline tương thích khác nhau

Một số cấu hình Spring Cloud Contract dùng Git SCM để lưu contracts/mappings, thường với URL có tiền tố `git://` và layout:

~~~text
META-INF/
  com.example/
    inventory-producer/
      2.3.1/
        contracts/
        mappings/
~~~

Đây không phải Maven repository layout. Regression phải kiểm tra đúng resolver:

| Nguồn | Bằng chứng cần kiểm tra |
|---|---|
| Maven REMOTE | Repository root, coordinates, POM, classifier JAR |
| Maven LOCAL | Maven local path và artifact đã install |
| CLASSPATH | Test runtime classpath và resource layout |
| Git SCM | URL/commit/ref, `META-INF/group/artifact/version`, `contracts`/`mappings` |

Nếu pipeline chuyển từ Git SCM sang Maven repository, phải test migration: mappings đã được publish thành producer stub JAR với coordinates/classifier mới chưa? Consumer ID/config đã được cập nhật không? Không thể chỉ đổi URL và giả định hai storage format tương đương.

## 20. Nâng cấp Spring Cloud Contract plugin: kiểm tra output và semantics

Plugin upgrade có thể thay đổi:

- DSL parsing/validation.
- Generated test source hoặc test framework integration.
- Task/goal names và lifecycle binding.
- Output directory và stub packaging.
- Mapping/fixture layout.
- Default values hoặc matcher behavior.
- Dependency graph của verifier/Stub Runner.
- Compatibility với Spring Boot/Cloud/JDK.

### Chiến lược nâng cấp an toàn

1. Chốt toolchain hiện tại làm baseline.
2. Lưu contract revision, producer test count/report, stub JAR entries và consumer test result.
3. Tạo branch upgrade riêng.
4. Chỉ nâng một lớp quan trọng mỗi lần nếu có thể.
5. Chạy lại producer verification.
6. So sánh generated tests và mapping semantics.
7. Publish vào staging với version/digest riêng.
8. Consumer test bằng artifact staging trong clean environment.
9. Chạy compatibility matrix tối thiểu.
10. Chỉ promote sau review diff và bằng chứng.

### Không so sánh generated source chỉ bằng số dòng

Plugin mới có thể đổi import, whitespace, tên generated class hoặc JSON key ordering mà không đổi behavior. Ngược lại, một matcher thay đổi nhỏ có thể làm consumer không match dù diff file rất ngắn.

Ưu tiên so:

- Request method/path/query/header/body matchers.
- Response status/header/body.
- Regex/type/date/JSONPath matcher.
- Message label/destination/header/payload.
- Producer test count và assertions.
- Consumer runtime behavior.

Nếu output byte thay đổi nhưng semantics không đổi, ghi nhận lý do và cập nhật baseline sau review; không tự động bỏ qua mọi diff.

## 21. Nâng cấp Maven, Gradle, JDK và repository

### Maven upgrade

- Kiểm tra plugin compatibility với Maven version.
- Kiểm tra effective POM, lifecycle order và attached artifacts.
- Kiểm tra Surefire/Failsafe/JUnit test discovery.
- Kiểm tra deploy plugin và repository credentials.
- Chạy resolve test bằng consumer project độc lập.

### Gradle upgrade

- Kiểm tra compatibility của Spring Cloud Contract plugin.
- Kiểm tra task configuration và configuration cache.
- Kiểm tra task inputs/outputs để build cache không dùng output stale.
- Kiểm tra `maven-publish` classifier/artifact attachment.
- Kiểm tra multi-project publication coordinates.
- Kiểm tra task publish thực tế và remote repository contents.

### JDK upgrade

- Kiểm tra compiler/test runtime toolchain.
- Kiểm tra Groovy/Gradle/Maven/plugin compatibility.
- Kiểm tra encoding, timezone/locale nếu ảnh hưởng fixture.
- Kiểm tra generated test compile và runtime behavior.
- Kiểm tra Docker/testcontainers image có cùng architecture/runtime yêu cầu.

### Repository manager upgrade

- Maven metadata và snapshot resolution.
- Release immutability/overwrite policy.
- Classifier artifact retention.
- Checksum/signature behavior.
- Authentication/authorization và token rotation.
- TLS certificate/truststore/proxy.
- Cache invalidation và replication giữa nodes.
- Download từ region/network của consumer CI.

**Không nâng tất cả cùng lúc** nếu chưa có regression baseline. Nếu build fail, sẽ khó biết nguyên nhân thuộc plugin, toolchain, repository hay source.

## 22. Caching: tối ưu tốc độ mà không mất tính đúng đắn

### Maven local repository

- Không dùng chung local repository giữa job không tin cậy và release jobs.
- Với clean-resolution regression, tạo repo local riêng hoặc cache key mới.
- Không dựa vào artifact install thủ công từ máy developer.
- Với SNAPSHOT, kiểm tra metadata/update policy và digest.
- Ghim release coordinates bất biến.

### Gradle dependency/build cache

- Dependency cache và task output cache là hai loại khác nhau.
- Task output cache an toàn khi task inputs/outputs được khai báo đúng.
- Nếu contract JAR/path hoặc plugin config không được khai báo là input, task có thể reuse generated output cũ.
- Cache namespace cần phân tách theo toolchain/branch/trust level.
- Không để PR không tin cậy ghi cache protected release job sử dụng.

### Một test chẩn đoán cache

~~~bash
./gradlew :inventory-producer:contractTest --rerun-tasks --no-build-cache
~~~

Lệnh yêu cầu chạy lại task và bỏ qua build cache cho invocation đó. Nó **không sửa** input declaration sai lâu dài và không giải quyết Maven repository trả artifact cũ.

Với Maven, dùng local repo tạm/clean workspace cho resolve regression thay vì xóa cache global của mọi developer.

## 23. Versioning và provenance: liên kết producer verification với consumer download

Một regression report tối thiểu:

~~~text
Contract source:
  repository: <contract-repository>
  revision: <contract-sha>
  artifact: com.example.contracts:inventory-contracts:1.6.0
  digest: <contract-digest>

Producer:
  repository: <producer-repository>
  revision: <producer-sha>
  toolchain: <jdk/maven-or-gradle/scc-versions>
  contract tests: 12 executed / 12 passed

Stub artifact:
  coordinate: com.example:inventory-producer:2.3.1:stubs
  repository: <staging-repository>
  digest: <stub-sha256>

Consumer:
  revision: <consumer-sha>
  resolved coordinate: com.example:inventory-producer:2.3.1:stubs
  downloaded digest: <downloaded-sha256>
  Stub Runner startup: PASS
  compatibility tests: 6 executed / 6 passed
~~~

Các giá trị trong dấu `<...>` là placeholder, phải được CI điền từ log/provenance thật.

### Những quan hệ cần giữ

- Contract source revision là nguồn producer verification đã dùng.
- Producer source revision là code generated tests đã chạy.
- Stub artifact được tạo từ chính lần build đó.
- Consumer download digest khớp digest candidate đã publish.
- Consumer report ghi đúng tọa độ/digest được resolve.

Không chỉ ghi version string; hai artifact có cùng version mutable có thể có bytes khác nhau.

## 24. Tách smoke test, compatibility test và full regression

| Cấp độ | Khi chạy | Nội dung |
|---|---|---|
| **Static/fast validation** | Mỗi PR | Diff, DSL discovery, build config |
| **Producer verification** | PR producer/protected branch | Generated tests + implementation |
| **Packaging smoke** | Sau producer verify | Classifier, JAR entries, metadata |
| **Publish/resolve smoke** | Trước merge/release hoặc staging | Upload, download bằng consumer identity |
| **Consumer compatibility** | Candidate stub mới | Stub Runner + client/handler tests |
| **Full toolchain matrix** | Theo lịch hoặc upgrade PR | JDK/build/plugin/repository matrix |
| **Repository failover** | Định kỳ/infra change | Mirror, auth, replication, cache |

Chọn test theo risk:

- Sửa DSL: producer tests + consumer compatibility.
- Sửa publication/classifier: packaging + remote resolution + Stub Runner.
- Nâng Gradle/Maven: producer lifecycle + publication + clean consumer resolution.
- Nâng Stub Runner/WireMock: startup + mapping behavior.
- Đổi repository: auth, metadata, snapshots, digest, clean download.
- Nâng JDK/Spring Boot/Cloud: full toolchain subset theo supported matrix.

Đừng bỏ end-to-end test hoàn toàn chỉ vì chậm; chạy ở tầng pipeline phù hợp, ví dụ nightly hoặc trước release.

## 25. Workflow CI tham khảo cho hai repository

~~~mermaid
flowchart TD
    A["Producer PR / approved commit"] --> B["Pinned toolchain"]
    B --> C["Generate + run producer tests"]
    C --> D{"PASS and count valid?"}
    D -->|No| X["Block publish"]
    D -->|Yes| E["Package :stubs JAR"]
    E --> F["Inspect classifier, mappings, digest"]
    F --> G["Publish unique candidate to staging"]
    G --> H["Clean consumer job"]
    H --> I["Resolve exact candidate"]
    I --> J["Stub Runner + consumer tests"]
    J --> K{"PASS?"}
    K -->|No| X
    K -->|Yes| L["Store provenance"]
    L --> M["Protected approval"]
    M --> N["Promote same artifact"]
~~~

### Producer job minh họa

~~~yaml
name: Producer contract pipeline

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify-and-package:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: gradle

      - name: Verify producer contracts
        run: ./gradlew :inventory-producer:contractTest

      - name: Package stub artifact
        run: ./gradlew :inventory-producer:verifierStubsJar

      - name: Inspect stub archive
        run: |
          jar tf inventory-producer/build/libs/inventory-producer-2.3.0-stubs.jar
~~~

Đây là **workflow minh họa**: action cần pin SHA theo policy; JDK, plugin, version, task names, path và output phải thay bằng cấu hình thực. Ví dụ chưa có publish step vì credentials/permissions cần tách riêng vào protected job sau verification.

### Consumer job minh họa

~~~yaml
name: Consumer stub compatibility

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  consume-candidate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Run consumer tests against staging stub
        run: ./mvnw -B -ntp clean verify
~~~

Consumer project cần cấu hình `StubRunnerProperties.StubsMode.REMOTE`, staging `repositoryRoot` và candidate version/digest. `workflow_dispatch` chỉ là ví dụ trigger, không tự truyền artifact giữa hai workflow.

Hai job cần trao đổi candidate coordinates/digest qua artifact metadata, workflow output hoặc release record đáng tin cậy. Không tự đoán version từ branch name.

## 26. Promotion: không rebuild sau khi compatibility PASS

Giả sử candidate:

~~~text
com.example:inventory-producer:2.3.1-rc.4:stubs
SHA-256 = abc...
~~~

Consumer compatibility test đã PASS trên chính bytes này. Release job nên **promote/copy chính artifact đã test** theo digest, thay vì build lại từ source rồi giả định output giống vì cùng version.

### Promotion record

~~~text
Candidate:
  staging coordinate: com.example:inventory-producer:2.3.1-rc.4:stubs
  digest: <digest-A>

Validation:
  producer tests: PASS
  archive inspection: PASS
  consumer tests: PASS

Release:
  release coordinate: com.example:inventory-producer:2.3.1:stubs
  promoted digest: <digest-A>
  approval: <release-approval>
~~~

Nếu release policy yêu cầu đổi version coordinate khi promote, repository có thể copy cùng bytes dưới release coordinate mới. Payload digest phải được giữ; POM/metadata phụ trợ có thể khác tùy policy và cần ghi nhận riêng.

Không promote nếu producer report không thuộc candidate build hoặc consumer test tải artifact có digest khác.

## 27. Compatibility regression cho nhiều consumer

Một producer thường có nhiều consumer:

~~~text
inventory-producer
  ├── checkout-consumer
  ├── reporting-consumer
  └── warehouse-consumer
~~~

Một stub JAR chung có thể chứa mappings cho nhiều consumer, hoặc producer tổ chức stubs per consumer tùy cấu hình. Regression phải kiểm tra **đúng consumer context** và mapping được chọn.

| Consumer | Tình huống cần kiểm tra |
|---|---|
| Checkout | GET stock, POST reservation, error insufficient stock |
| Reporting | Inventory snapshot và field thống kê |
| Warehouse | Stock changed event và message headers |

Nếu producer thay response field, một consumer có thể PASS còn consumer khác FAIL. Chỉ test Checkout không chứng minh tương thích với Reporting và Warehouse.

- Consumer critical: chạy compatibility test trong producer release candidate.
- Consumer ít thay đổi: chạy theo lịch hoặc khi contract path thay đổi.
- Consumer deprecated: vẫn kiểm tra nếu policy còn cam kết hỗ trợ.
- Consumer mới: dùng candidate stub để kiểm tra trước producer release.

Với stubs-per-consumer, regression nên xác minh artifact/filter riêng từng consumer. Một JAR có mapping Checkout không chứng minh mapping Reporting được publish.

## 28. Regression test cho breaking changes

Response cũ:

~~~json
{"sku":"SKU-101","available":true,"quantity":8}
~~~

Response mới:

~~~json
{"sku":"SKU-101","availability":"IN_STOCK","units":8}
~~~

Generated producer tests mới có thể PASS nếu DSL và code cùng đổi. Nhưng consumer cũ vẫn đọc `available` và `quantity`.

Regression cần:

1. Chạy consumer tests đã ghim với **stub phiên bản mới** để phát hiện breaking change.
2. Giữ compatibility tests với stub cũ nếu producer cam kết hỗ trợ behavior cũ.
3. Review schema/type/status/header/message changes.
4. Có migration/versioning/deprecation plan.
5. Chỉ promote nếu consumer bắt buộc đạt hoặc có quyết định release được phê duyệt.

**Contract tests không tự biết mọi consumer đang triển khai.** Cần dependency map hoặc danh sách consumer do tổ chức quản lý.

## 29. Cache và snapshot regression

Triệu chứng:

~~~text
Producer published 2.3.1-SNAPSHOT with new mapping
Consumer job reports PASS
But downloaded JAR still has old mapping
~~~

Có thể do Maven metadata/update policy, proxy cache, local repo hoặc Gradle dependency cache.

Cách kiểm tra:

- Ghi resolved artifact path/version/digest.
- So checksum với producer candidate.
- Kiểm tra Maven `maven-metadata.xml` và timestamped snapshot.
- Tạo clean local repo/cache namespace cho regression run.
- Không dùng dynamic version cho release gate.
- Kiểm tra mirror/proxy đang phục vụ bytes nào.

Quy tắc release:

- Dùng version release bất biến cho verified stubs.
- Candidate dùng build ID/RC duy nhất.
- Không overwrite release coordinates.
- Nếu artifact cần sửa, tăng version hoặc rollback/reissue theo policy.
- Giữ digest artifact producer đã verify và consumer đã test.

**Không dùng xóa cache làm fix lâu dài** nếu version vẫn mutable hoặc publication không có provenance.

## 30. Negative regression test cho repository access và metadata

Một bộ regression nên thử lỗi có kiểm soát ở staging/test repository:

| Case | Setup giả lập | Expected result |
|---|---|---|
| Read token sai | Consumer dùng token hết hạn | Download fail 401 |
| Không đủ quyền | Token chỉ đọc repository khác | Download fail 403 hoặc policy response |
| Artifact không tồn tại | ID version chưa publish | Resolve fail rõ tọa độ |
| Classifier thiếu | Chỉ publish main JAR | Stub resolution fail |
| POM có, JAR thiếu | Upload metadata nhưng thiếu payload | Resolve fail khi tải JAR |
| JAR rỗng | Publish JAR không mapping | Archive/smoke validation fail |
| Mapping thiếu | Bỏ endpoint cần test | Mapping assertion fail |
| Digest khác | Candidate bị thay bytes | Provenance check fail |
| TLS CA sai | Runner thiếu trust CA | Download fail rõ TLS |
| Mirror trỏ nhầm | Repo root khác staging | Repository assertion fail |

Negative tests chạy trong repository harness hoặc staging riêng. **Không cố tình làm hỏng release repository chính thức** để thử failure.

## 31. Quan sát và lưu bằng chứng pipeline

Một report hữu ích cần nối producer với consumer:

~~~text
Run:
  pipeline-id: <pipeline-id>
  started-at: <timestamp>

Toolchain:
  JDK: <jdk-version>
  Maven/Gradle: <build-tool-version>
  SCC plugin: <plugin-version>
  Stub Runner: <stub-runner-version>

Contract:
  repository/revision: <contract-source-sha>
  coordinates: <contract-group:artifact:version>
  digest: <contract-digest>
  discovered contracts: <count>

Producer:
  source revision: <producer-sha>
  generated tests: <executed>/<passed>/<failed>/<skipped>
  stub task: <task-or-goal>
  artifact coordinate: <group:artifact:version:stubs>
  published repository: <staging-root>
  artifact digest: <stub-digest>

Consumer:
  source revision: <consumer-sha>
  stubsMode: <LOCAL|REMOTE|CLASSPATH>
  resolved coordinate: <group:artifact:version:stubs>
  downloaded digest: <downloaded-digest>
  Stub Runner startup: <PASS/FAIL>
  consumer tests: <executed>/<passed>/<failed>

Decision:
  <PROMOTE/BLOCK/INVESTIGATE>
~~~

Các giá trị trong dấu `<...>` là placeholder. Không đưa credentials/token hoặc URL có embedded password vào log.

Metric nên theo dõi:

- Tỷ lệ producer builds có generated contract tests bằng 0.
- Tỷ lệ publish thành công nhưng consumer resolution fail.
- Tỷ lệ consumer test dùng stub version cũ hơn candidate.
- Tỷ lệ artifact digest mismatch.
- Số release bị chặn do compatibility test.
- Thời gian từ producer publish candidate tới consumer verification.
- Số flaky tests/retry rate, có phân loại root cause.

Metric không thay thế test nhưng giúp phát hiện regression pipeline lặp lại sau khi nâng công cụ.

## 32. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Producer build xanh, không có stub JAR | Task generation/package không chạy | Task graph, output directory |
| Main JAR publish, stubs JAR thiếu | Classifier chưa attach | POM/publication/artifact list |
| Local consumer PASS, remote consumer FAIL | Chưa publish hoặc ACL/repository sai | Repository root, read identity |
| Consumer resolve version cũ | Pin/cache/snapshot metadata | Resolved coordinate + digest |
| JAR tải được nhưng thiếu mapping | Contracts path/filter/packaging sai | Archive listing |
| Stub Runner context fail | Dependency/config/server startup | Startup log, port conflict |
| Context PASS nhưng HTTP 404 | Request không match mapping | Unmatched request journal |
| Consumer PASS với stub cũ | Candidate không truyền sang consumer job | Pipeline output coordinates |
| JDK upgrade làm generated tests compile fail | Plugin/test framework compatibility | Compatibility matrix/dependency tree |
| Gradle upgrade không chạy contractTest | Task/source set/plugin change | tasks --all, plugin config |
| Maven upgrade không attach stub | Lifecycle/plugin execution đổi | Effective POM, deploy logs |
| Repository upgrade trả HTML | Proxy/login/SSO redirect | Content-Type, response status |
| Multi-module publish sai tọa độ | Subproject group/artifact/version override | Publication metadata |
| Snapshot mapping stale | Metadata/cache | Clean repo, timestamped snapshot, digest |
| Consumer khác thiếu mapping | Stubs-per-consumer filter | Artifact entries per consumer |

### Quy trình chẩn đoán

1. Xác định run ID và source revisions producer/consumer.
2. Xác nhận producer tests thực sự chạy và PASS.
3. Kiểm tra stub JAR output và archive entries.
4. Kiểm tra publication coordinates và repository response.
5. Tải lại artifact bằng consumer identity vào môi trường sạch.
6. So digest với producer candidate.
7. Xác nhận Stub Runner startup và port.
8. Đối chiếu request thực với mapping.
9. Chỉ sau đó kết luận lỗi thuộc contract, producer, consumer hay infrastructure.

Không sửa consumer request khi artifact chưa tồn tại; không publish lại artifact khi lỗi chỉ là URL/port mismatch.

## 33. Bài thực hành 1 — Publish thành công nhưng classifier thiếu

Producer CI log:

~~~text
BUILD SUCCESS
Uploaded:
  inventory-producer-2.5.0.pom
  inventory-producer-2.5.0.jar
~~~

Consumer ID:

~~~text
com.example:inventory-producer:2.5.0:stubs:0
~~~

Consumer không resolve được artifact.

**Câu 1. Nguyên nhân chính?**

Publication chỉ có main JAR; classifier `stubs` chưa được attach/upload.

**Câu 2. Kiểm tra ở đâu?**

- Maven: plugin stub generation/attachment, effective POM và deploy logs.
- Gradle: `verifierStubsJar` output, publication artifact list và publish task.
- Registry: file `inventory-producer-2.5.0-stubs.jar` có thực sự tồn tại không?

**Câu 3. Có nên bỏ classifier trong consumer ID?**

Không. Resolver có thể tải main application artifact thay vì stub mappings. Sửa producer publication rồi chạy regression test từ consumer.

## 34. Bài thực hành 2 — Consumer PASS nhưng tải stub cũ

Producer candidate 2.5.1 có mapping mới `GET /api/inventory/SKU-202`. Consumer job báo PASS, nhưng log resolve cho biết:

~~~text
Resolved:
  inventory-producer:2.5.0:stubs
~~~

**Câu 1. Consumer đã test candidate 2.5.1 chưa?**

Chưa. Consumer chỉ test stub 2.5.0.

**Câu 2. Nguyên nhân có thể?**

Candidate coordinates không được truyền tới consumer job, ID còn pin 2.5.0, cache/version alias hoặc pipeline output stale.

**Câu 3. Cách sửa?**

Dùng tọa độ 2.5.1 cụ thể, tải từ staging, kiểm digest và assert version/digest trong report. Không đổi sang `latest`.

## 35. Bài thực hành 3 — JAR đúng nhưng Stub Runner trả 404

- Artifact resolution: PASS.
- Archive có mapping `GET /api/inventory/SKU-101`.
- Stub Runner mở port 14321.
- Consumer gửi `GET /inventory/SKU-101`.
- WireMock trả 404.

**Câu 1. Pipeline publish/download có lỗi không?**

Các bước publish/download/startup đã có bằng chứng PASS; request không khớp mapping vì thiếu prefix `/api`.

**Câu 2. Sửa ở đâu?**

Nếu contract đã chốt path `/api/inventory/...`, sửa consumer base path. Nếu contract thực sự đổi path, sửa DSL và chạy lại producer/consumer verification.

**Câu 3. Vì sao cần unmatched request journal?**

Nó cho biết request nào không match, giúp phân biệt WireMock 404 với business 404 do mapping trả.

## 36. Bài thực hành 4 — Nâng Gradle và Spring Cloud Contract plugin

Sau upgrade:

~~~text
Before:
  contractTest executed: 12
  stubs JAR published: yes
  consumer remote smoke: PASS

After:
  build SUCCESS
  contractTest executed: 0
  application JAR published: yes
  stubs JAR: missing
~~~

**Câu 1. Có thể chấp nhận upgrade không?**

Không. Build success nhưng không có producer tests và stub artifact là regression nghiêm trọng.

**Câu 2. Cần kiểm tra gì?**

- Plugin version và Gradle compatibility.
- Task graph `tasks --all`.
- Project path/source set/contract DSL directory.
- `verifierStubsJar` task/output.
- Publication có gắn đúng artifact/task không.
- Test report và CI task dependencies.

**Câu 3. Quality gate nào bắt lỗi?**

Bắt buộc generated producer test count > 0 (khi module có contract), tests PASS, stub artifact tồn tại, archive có mapping, consumer remote resolution và Stub Runner smoke PASS.

## 37. Checklist kiểm thử hồi quy pipeline công bố và tải stub

### Producer contract verification

- [ ] Contract source revision/version được ghim và ghi lại.
- [ ] Toolchain JDK/Maven/Gradle/SCC plugin tương thích.
- [ ] Đúng producer module/task được chạy.
- [ ] Số contract phát hiện phù hợp, không có 0 contracts bất ngờ.
- [ ] Generated producer tests được compile và thực thi.
- [ ] Test report có count/pass/fail/skip.
- [ ] Producer tests PASS trước publish.
- [ ] Không có skipTests/task exclusion ngoài policy.

### Packaging và publication

- [ ] Stub JAR được tạo từ đúng producer/contract revision.
- [ ] Classifier `stubs` được attach.
- [ ] JAR chứa mappings/message definitions cần.
- [ ] Fixtures/body files được đóng gói.
- [ ] Group/artifact/version/extension/classifier đúng.
- [ ] POM và repository metadata hợp lệ.
- [ ] Artifact được publish tới staging/repository đúng.
- [ ] Consumer read identity tải được artifact.
- [ ] Version candidate duy nhất, release bất biến.
- [ ] Digest/provenance được lưu.

### Consumer resolution và runtime

- [ ] Consumer ID khớp publication coordinates.
- [ ] `stubsMode` phù hợp LOCAL/REMOTE/CLASSPATH.
- [ ] Remote repository root đúng, credentials chỉ read.
- [ ] Consumer test chạy trong clean environment/cache phù hợp.
- [ ] Downloaded artifact digest khớp producer candidate.
- [ ] Stub Runner load mapping và mở port/label.
- [ ] Client dùng port runtime, không hardcode.
- [ ] HTTP request/message trigger match mapping.
- [ ] Consumer assertions kiểm tra status/body/type/error code.
- [ ] Không nhầm unmatched WireMock 404 với business 404.
- [ ] Consumer test thực sự chạy trên candidate version mới.

### Toolchain compatibility và release

- [ ] Supported baseline và upgrade candidate được ghi rõ.
- [ ] Maven/Gradle wrapper, JDK, Spring Boot/Cloud/SCC versions được pin.
- [ ] Upgrade test so sánh semantics generated tests/mappings.
- [ ] Cache không làm consumer dùng stub cũ.
- [ ] Negative tests xác nhận gate fail khi thiếu artifact/classifier/mapping.
- [ ] Consumer compatibility của các nhóm quan trọng được chạy.
- [ ] Artifact promotion dùng đúng bytes đã test, không rebuild tùy tiện.
- [ ] Release record liên kết producer SHA, contract SHA, consumer SHA và stub digest.
- [ ] Có owner xử lý flaky test và artifact resolution failures.

## 38. Ghi nhớ và tài liệu tham khảo

**Kiểm thử hồi quy pipeline công bố và tải stub** phải xác nhận cả chuỗi: producer discover contract → generate/run tests → package classifier `stubs` → publish → consumer resolve → Stub Runner startup → consumer compatibility tests.

Ba loại artifact cần phân biệt: **contract definitions JAR**, **producer application JAR** và **producer stubs JAR**. Main JAR publish thành công không chứng minh classifier stubs đã được upload; consumer test xanh với stub cache cũ không chứng minh candidate mới tương thích.

Khi nâng Maven/Gradle/JDK/Spring Cloud Contract plugin hoặc repository manager, chạy compatibility matrix phù hợp, kiểm tra archive/metadata và tải artifact trong môi trường consumer sạch. Ghim version, digest và provenance; promote **chính artifact đã được kiểm chứng**.

### Tài liệu tham khảo

- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): DSL, verifier, stub generation và Stub Runner.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): plugin Gradle, `contractTest` và `verifierStubsJar`.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): plugin Maven, lifecycle và artifact stubs.
- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): cấu hình Stub Runner trong consumer tests.
- [Spring Cloud Contract — Stub Runner Core](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html): resolve và khởi động stub artifacts.
- [Spring Cloud Contract — Git as Storage](https://docs.spring.io/spring-cloud-contract/reference/howto/how-to-use-git-as-storage.html): khi contracts/mappings lưu qua Git SCM.
- [Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html): tọa độ, local/remote repositories và metadata.
- [Maven Dependency Plugin — dependency:get](https://maven.apache.org/plugins/maven-dependency-plugin/get-mojo.html): resolve artifact/classifier.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): publication Maven-compatible từ Gradle.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): cache dependency và resolution.
- [SLSA — Supply-chain Levels for Software Artifacts](https://slsa.dev/): provenance và tính toàn vẹn artifact.

**Kết luận thực hành:** khi pipeline báo PASS, hãy chứng minh producer đã kiểm chứng contract, stub artifact đúng classifier/version đã được publish, consumer đã tải đúng digest và Stub Runner đã chạy mapping tương ứng. Đó mới là bằng chứng hồi quy cho chuỗi công bố và tải stub.
