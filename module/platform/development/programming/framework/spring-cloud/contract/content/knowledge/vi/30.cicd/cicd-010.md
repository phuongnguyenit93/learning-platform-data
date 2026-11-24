# Tái chạy pipeline với cùng đầu vào và cùng phiên bản stub

Trong CI/CD, một bài **consumer contract test** có thể xanh vào hôm qua nhưng đỏ khi người phát triển bấm **Rerun** hôm nay, dù không có commit mới. Nguyên nhân không nhất thiết là mã nguồn thay đổi: repository có thể trả bản `SNAPSHOT` khác, Stub Runner tải một JAR `stubs` mới ở cùng tọa độ mutable, Gradle/Maven resolve lại dependency, data fixture bị dùng chung, thời gian hệ thống đổi hoặc hai job tranh cùng cổng WireMock. Khi đó, nhóm không còn biết mình đang **tái hiện lỗi cũ** hay đang kiểm một bộ đầu vào khác.

**Tái chạy có thể tái lập (reproducible rerun)** nghĩa là xác định và kiểm soát đủ các đầu vào của pipeline để lần chạy lại có thể so sánh đáng tin với lần trước. Với **Spring Cloud Contract**, những đầu vào quan trọng gồm **Git commit của producer/consumer, Groovy/YAML contract, generated producer tests, Maven/Gradle configuration, phiên bản artifact `stubs`, nội dung bytes của JAR, cấu hình Stub Runner, test fixture và môi trường CI**.

Bài thuộc chương **CI/CD** của mô-đun **SPRING_CLOUD_CONTRACT**. Mô-đun dạy kiểm thử hợp đồng HTTP và thông điệp, sinh test cho producer, phát hành stub, dùng Stub Runner và CI để phát hiện thay đổi API không tương thích. Chủ đề này tập trung vào một năng lực vận hành thiết yếu: **khi contract test thất bại, có thể chạy lại đúng phiên bản đang được kiểm để phân biệt regression thực, lỗi hạ tầng và test không ổn định**.

## 1. “Cùng đầu vào” có nghĩa gì?

Không nên định nghĩa “cùng đầu vào” đơn giản là **cùng branch** hoặc **cùng một file `pom.xml`**. Một lần chạy CI phụ thuộc nhiều lớp trạng thái:

| Lớp đầu vào | Ví dụ | Điều cần cố định hoặc ghi nhận |
| --- | --- | --- |
| **Source code** | Git commit của Billing Service | Full Git SHA, submodules/đường dẫn checkout. |
| **Contract source** | `orders/get_paid_order.groovy` | Git SHA hoặc checksum của tập hợp contract được dùng. |
| **Producer build** | Order Service release `1.4.2` | Git SHA, test report, artifact `stubs` của đúng release. |
| **Stub artifact** | `com.acme:order-service:1.4.2:stubs` | Tọa độ **và SHA-256 của JAR thực tế**. |
| **Dependencies** | Spring Boot, Spring Cloud Contract, Jackson | Version resolved thực; tránh dynamic/mutable versions. |
| **Build tools** | JDK, Maven Wrapper/Gradle Wrapper | Toolchain, phiên bản plugin, container/tool image. |
| **CI definition** | Workflow revision, scripts, matrix | Phiên bản workflow/actions/runners và flags thực. |
| **Test configuration** | `StubsMode.REMOTE`, repo root, profile | Mode, environment variables được phép, cấu hình resolver. |
| **Fixtures và trạng thái** | DB, clock, auth token giả, message backlog | Cùng điều kiện khởi tạo, reset/cô lập giữa các tests. |
| **Hạ tầng phụ trợ** | Repository, network, proxy, broker | Nguồn truy cập, trạng thái dịch vụ hoặc bản mô phỏng ổn định. |

Một lần chạy có thể dùng **cùng tọa độ Maven** nhưng **khác bytes** nếu artifact bị ghi đè. Ngược lại, hai job có thể dùng **cùng JAR checksum** nhưng tạo test outcome khác nhau do fixture, thời gian hoặc cách gọi client bị thay đổi.

Vì vậy, nên phân biệt **identity của đầu vào** với **độ ổn định của môi trường thực thi**. Cố định identity là điều kiện cần; cô lập và kiểm soát nguồn nondeterminism mới giúp kết quả nhất quán.

## 2. Ba mục tiêu của việc chạy lại

| Mục tiêu | Cách làm | Khi dùng |
| --- | --- | --- |
| **Rerun cùng job** | Chạy lại cùng Git SHA, cùng workflow revision và cùng artifact stub đã ghim. | Xem một lỗi CI có lặp lại không. |
| **Rebuild có thể đối chiếu** | Biên dịch lại từ cùng source/toolchain/dependency graph, so artifact/test results. | Điều tra build hoặc supply-chain drift. |
| **Replay đúng artifact đã kiểm** | Tải lại đúng JAR `stubs` theo checksum và dùng lại container image/đầu ra từ run đã xác minh. | Tái hiện sự cố của một release cụ thể hoặc kiểm consumer cũ. |

**Không nên coi ba mục tiêu là một.** Một lệnh `Rerun all jobs` trên hệ CI có thể dùng lại commit nhưng **resolve dependencies mới**, kéo một action mới hoặc truy cập repository ở trạng thái khác. Một lệnh `mvn clean verify` từ cùng Git SHA vẫn có thể không tạo ra byte-for-byte cùng JAR nếu build phụ thuộc timestamp hay plugin không quyết định.

Kết luận điều tra nên ghi rõ: **“rerun cùng source”**, **“rerun cùng artifact”** hay **“byte-for-byte rebuild”**. Đừng tuyên bố “reproducible” khi mới chỉ có hai lượt test xanh.

## 3. Chuỗi producer → stub → consumer cần giữ bất biến

~~~mermaid
flowchart TD
    A["Producer source + Groovy/YAML contract tại Git SHA P"] --> B["Contract Verifier sinh producer tests"]
    B --> C{"Producer tests thực sự chạy và PASS?"}
    C -->|Không| X["Chặn publish"]
    C -->|Có| D["Đóng gói artifact stubs"]
    D --> E["Ghi coordinates + SHA-256 + CI run ID"]
    E --> F["Publish immutable release artifact"]
    F --> G["Consumer source tại Git SHA C"]
    G --> H["Stub Runner tải đúng artifact đã ghim"]
    H --> I["WireMock / message adapter khởi động"]
    I --> J["Consumer test dùng mã client/listener thật"]
    J --> K["Lưu test result + input manifest"]
~~~

Hai kiểu kiểm tra bổ trợ:

1. **Producer verification** chứng minh implementation ở **producer commit P** đáp ứng các hợp đồng đã chọn.
2. **Consumer test qua Stub Runner** chứng minh client/listener ở **consumer commit C** có thể sử dụng **stub artifact cụ thể**.

Nếu consumer test chỉ dùng artifact từ **producer release quá cũ**, kết quả xanh không bảo đảm producer release đang chuẩn bị triển khai vẫn tương thích. Nếu producer build bỏ qua generated tests, JAR stub vừa publish cũng không tự có bảo đảm về implementation. Pipeline cần nối **đúng release đang kiểm**, không chỉ tải bất kỳ JAR có classifier `stubs`.

## 4. Hợp đồng mẫu để làm chuẩn so sánh

Giả sử Order Service là producer và Billing Service là consumer. Một hợp đồng HTTP lưu tại:

~~~text
src/test/resources/contracts/orders/get_paid_order.groovy
~~~

Nội dung Groovy DSL:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Order Service trả đơn hàng đã thanh toán'

    request {
        method 'GET'
        url '/api/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            status: 'PAID',
            amountMinor: 125000
        )
    }
}
~~~

Hoặc **chọn YAML DSL** để biểu diễn cùng hành vi:

~~~yaml
description: Order Service trả đơn hàng đã thanh toán
request:
  method: GET
  url: /api/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
    amountMinor: 125000
~~~

Đây là **hai cách minh họa**, không phải hai bản contract phải được nạp cùng lúc. Trong producer build, chỉ giữ một dạng có hiệu lực cho cùng trường hợp để tránh generated tests hoặc stub mappings trùng nhau.

Hợp đồng chứa **method/path/request/response semantics**, không chứa Maven repository URL, port WireMock hoặc Git SHA. Các thông tin môi trường và provenance phải được quản lý ở **pipeline/release record**, không nhồi vào DSL để “khóa” bản build.

### 4.1. Vì sao fixture cũng quan trọng?

Generated producer test chỉ có giá trị khi Order Service **thực sự có đơn hàng 42 ở trạng thái PAID** trong môi trường kiểm. Nếu một lần test database sạch nhưng lần khác trùng với dữ liệu do test trước để lại, kết quả không thể tái lập.

Base test của producer có thể dùng profile test, transaction/cleanup có kiểm soát, `@BeforeEach`/`@Sql`, Testcontainers với image version ghim, hoặc repository mock theo mức kiểm chứng mong muốn. **Không dùng một shared development database** làm nguồn dữ liệu ngẫu nhiên cho contract verification.

## 5. Tọa độ artifact chưa đủ: phải biết nội dung JAR nào

Một consumer thường khai báo Stub Runner:

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/repository/releases"
)
~~~

Tọa độ được phân tách:

~~~text
groupId    = com.acme
artifactId = order-service
version    = 1.4.2
classifier = stubs
extension  = jar
~~~

**Nguyên tắc cho CI tái lập:**

- Ghim **version cụ thể**, không dùng những selector biến đổi theo thời gian khi mục tiêu là rerun.
- Ưu tiên **release artifact bất biến** (không ghi đè cùng group/artifact/version/classifier).
- Tính và lưu **SHA-256 checksum** của file JAR mà CI thật sự tải/build.
- Liên kết artifact đó với **producer Git SHA, CI run và báo cáo producer verification**.
- Nếu có mirror/proxy repository, kiểm metadata và checksum để phát hiện stale/mismatch.
- Không tự cho rằng file trong `~/.m2/repository` là đúng bản mới vì tên file khớp.

Ví dụ một build record:

~~~text
stubCoordinate = com.acme:order-service:1.4.2:stubs
stubSha256     = <64 hexadecimal characters of actual JAR>
producerCommit = <full Git SHA of the verified producer build>
producerRunId  = <CI build ID>
~~~

Những giá trị trong `<...>` là **placeholder**, tuyệt đối không dùng làm checksum hay cam kết đã được xác minh. Digest cần được lấy từ **bytes thật** của artifact được publish hoặc resolver tải về.

### 5.1. Vì sao version `-SNAPSHOT` dễ làm rerun khác nhau?

Một version như:

~~~text
com.acme:order-service:1.5.0-SNAPSHOT:stubs
~~~

có thể được publish nhiều lần với **nội dung khác nhau**. Repository snapshot metadata có thể chuyển từ timestamp/build number A sang B. Nếu CI retry hôm sau, cùng chuỗi tọa độ có thể trỏ tới một JAR khác.

Trong phát triển, `SNAPSHOT` vẫn hữu ích để thử thay đổi mới. Nhưng đối với **replay một lỗi lịch sử**, cần:

1. Ghi lại **timestamped snapshot artifact hoặc checksum** đã dùng.
2. Lưu artifact vào kho lưu trữ build có tính bất biến theo run ID, nếu policy cho phép.
3. Hoặc publish **release/test-candidate version riêng**, không ghi đè để phục vụ compatibility CI.
4. Cài/tra lại artifact từ **cùng bytes** khi rerun, không chỉ chọn lại alias `-SNAPSHOT`.

**Không gọi `-U` với kỳ vọng “lấy lại đúng bản cũ”**: Maven `-U` có thể buộc kiểm tra các bản cập nhật snapshot, làm bản đã resolve thay đổi. `-U` chỉ là công cụ điều tra/cache-policy, không phải cơ chế pin artifact.

## 6. Cố định Git commit, không chỉ branch hoặc pull request number

Một workflow triggered ở pull request có thể dùng:

- **Head commit** của nhánh PR.
- **Synthetic merge commit** do CI tạo để thử trạng thái merge.
- Commit mới sau khi PR được cập nhật.

Ba thứ đó **không nhất thiết giống nhau**. Khi rerun, cần biết **chính xác Git SHA đã checkout và hash của các submodules/external contract sources**.

| Dữ liệu | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Source repository | `billing-service` | Nguồn consumer test. |
| Full Git SHA | `abc123...` | Snapshot code được kiểm. |
| Ref type | `pr-head` hoặc `merge-ref` | Cách CI tạo checkout. |
| Workflow revision | Commit của thư mục `.github/workflows`/Jenkinsfile | Quy tắc CI đã thực thi. |
| External contract source | Tag/commit hoặc Maven coordinates riêng | Hợp đồng được kéo từ nguồn khác. |
| Submodule commit | SHA của module phụ | Phần source nằm ngoài repository chính. |

**Không dùng `git checkout main` cho một job replay lỗi hôm trước**, vì `main` có thể đã nhận thêm nhiều commits. Nếu muốn test một bản sửa mới trên `main`, đó là **lần kiểm khác**, không còn rerun cùng đầu vào.

Nếu producer và consumer sống ở **hai repositories**, phải ghi **hai Git SHAs**, không ghi một “source version” chung rồi suy luận nhầm.

## 7. Khóa phiên bản công cụ build và test

Không chỉ source, môi trường biên dịch cũng ảnh hưởng generated tests và behavior:

| Thành phần | Cách kiểm soát |
| --- | --- |
| **JDK** | Khai báo version/toolchain; tốt hơn ghi vendor và exact runtime build hoặc digest của CI image. |
| **Maven** | Dùng Maven Wrapper từ commit đã ghim, ghi `./mvnw -version` trong record. |
| **Gradle** | Dùng Gradle Wrapper từ commit đã ghim, Java toolchain và plugin versions cố định. |
| **Spring Boot** | Version cụ thể qua parent/BOM; không trộn release train tùy tiện. |
| **Spring Cloud Contract** | Plugin + Verifier/Stub Runner dependencies tương thích theo release train. |
| **JUnit/Spock** | Framework engine và cách test discovery không bị thay đổi âm thầm. |
| **Docker/CI image** | Ưu tiên image digest hoặc immutable tag được quản trị. |
| **Third-party CI actions/plugins** | Ghim revision/version đã phê duyệt; audit các thay đổi. |

Ví dụ Maven `pom.xml` phần producer:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>2023.0.4</spring-cloud.version>
    <spring-cloud-contract.version>4.1.5</spring-cloud-contract.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Các phiên bản ở đây **chỉ là một bộ ví dụ**, không phải version mới nhất hay bảo đảm phù hợp với mọi JDK/Maven/Gradle. Khi triển khai thật, phải chọn bộ Spring Boot, Spring Cloud release train, Spring Cloud Contract và build tool **tương thích** theo yêu cầu project.

**BOM không tự ghim version build plugin** nếu plugin được cấu hình độc lập với dependencies. Và bản thân việc chọn Spring Cloud BOM không tự làm image CI, Maven Wrapper, Gradle Wrapper hoặc JDK bất biến.

## 8. Khóa dependency tree và kiểm version đã resolve

Một `pom.xml` hoặc `build.gradle` cố định top-level dependencies chưa chắc đã đủ khi:

- Dùng version range/dynamic version.
- Dùng SNAPSHOT hoặc dependency nội bộ có thể bị ghi đè.
- Registry/mirror có policy resolve khác nhau.
- Cấu hình Maven profiles hoặc Gradle variants thay đổi theo môi trường.
- Plugin dùng transitives khác nhau khi version/plugin repositories đổi.

**Maven**: dùng BOM/`dependencyManagement`, pin plugin versions và ghi dependency tree khi cần điều tra:

~~~shell
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

**Gradle**: dùng version catalog/BOM và **dependency locking** khi phù hợp; kiểm graph thực sự resolve:

~~~shell
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-contract-stub-runner \
    --configuration testRuntimeClasspath
~~~

Gradle có cơ chế lockfile để ghim dependency resolution. Nhưng **Gradle dependency locking không tự khóa mọi Maven/Gradle plugin, CI action, container image hoặc artifact mà Stub Runner tự tải**. Cần kiểm riêng từng lớp input.

**Không tự đưa output `dependency:tree`/`dependencies` vào repository như một “chứng cứ” khi chưa biết nó được sinh trên môi trường nào**. Tốt hơn lưu file/report được CI tạo cho run tương ứng, đối chiếu toolchain và nguồn repository.

## 9. Cache: tăng tốc nhưng có thể che drift

CI thường cache:

~~~text
~/.m2/repository/
~/.gradle/caches/
build/
target/
container image layers
artifact download cache của Stub Runner
~~~

Không phải cache nào cũng có tính chất như nhau:

| Cache | Có thể làm lệch gì? | Chính sách gợi ý |
| --- | --- | --- |
| Maven local artifact cache | Lưu `stubs` khác với remote artifact có cùng coordinates. | Dùng immutable releases, checksum, cold-cache verification có chủ đích. |
| Maven `.lastUpdated`/metadata | Ghi nhớ lỗi/metadata cũ, fail khác giữa rerun. | Điều tra update policy/TTL, không xóa bừa khi lỗi thật là 401. |
| Gradle dependency cache | Trả dynamic version hoặc module metadata đã cache. | Dependency locking, refresh có kiểm soát, so lockfile. |
| `target/` hoặc `build/` | Generated tests/mappings cũ còn sót nếu build thiếu clean. | Dùng clean cho verification/replay khi cần xác minh nguồn. |
| CI artifact cache | Dùng lại report hoặc JAR của job khác. | Cache key có Git SHA/toolchain; artifact identity có checksum. |
| Docker layer cache | Ảnh hưởng bytes/nhánh build nếu nguồn hoặc base image mutable. | Pin base image digest và record image digest cuối. |

**Warm-cache test** trả lời “pipeline thông thường chạy được khi cache có sẵn?”; **cold-cache test** trả lời “có resolve được mọi dependency/artifact từ nguồn được phép và cùng bytes không?”. Cả hai có ích. Tuy nhiên, cold-cache **không tự đảm bảo** cùng dependency nếu nguồn repository có bản mutable; cần kết hợp version pin và checksum/provenance.

### 9.1. Tại sao không dùng `LOCAL` để kết luận `REMOTE` hoạt động?

Ví dụ:

~~~java
stubsMode = StubRunnerProperties.StubsMode.LOCAL
~~~

chỉ yêu cầu Stub Runner tìm artifact đã có trong **Maven local repository** ở môi trường đó. Nó **không chứng minh** kho artifact từ xa hoạt động, token còn hạn hay proxy/TLS đã đúng.

Nếu muốn kiểm **khả năng tải lại artifact release**, dùng `REMOTE` và một môi trường/cache được cô lập phù hợp. Nếu muốn **replay đúng artifact bytes đã archive**, dùng bản đã được giữ với checksum đối chiếu và không phụ thuộc resolver chọn bản khác.

## 10. Producer CI: kiểm thật trước khi phát hành stubs

Một release đáng tin cần có generated tests thực sự được sinh và chạy:

~~~mermaid
flowchart TD
    A["Checkout producer Git SHA P"] --> B["Khôi phục toolchain + dependencies đã ghim"]
    B --> C["Sinh tests từ Groovy/YAML contracts"]
    C --> D["Compile generated tests"]
    D --> E["Run producer verification"]
    E --> F{"Có tests yêu cầu và PASS?"}
    F -->|Không| G["Fail; không publish"]
    F -->|Có| H["Tạo JAR stubs"]
    H --> I["Tính SHA-256; lưu provenance"]
    I --> J["Publish immutable coordinates"]
~~~

Với producer Maven đã cấu hình plugin/lifecycle đúng:

~~~shell
./mvnw -B -ntp clean verify
~~~

Sau đó có thể `install`/`deploy` hoặc publish artifact đã xác minh theo pipeline được tổ chức phê duyệt.

Với producer Gradle:

~~~shell
./gradlew --no-daemon clean test
./gradlew tasks --all
~~~

Lệnh `tasks --all` giúp kiểm tên task đóng gói stubs ở phiên bản Spring Cloud Contract Gradle Plugin đang dùng. **`test` không nhất thiết tạo/publish classifier JAR**; cần task packaging/publication riêng khi muốn đưa stub sang consumer runner.

**Điều cần kiểm ở mọi build:** generated tests có xuất hiện trong reports, **test count thực tế không phải 0** nếu project có contract bắt buộc, không có skip flags, và **một thay đổi cố ý phá response** có thể khiến build FAIL. Nếu producer test chưa thực thi, một artifact stub có tên đúng version cũng không đáng tin.

### 10.1. Không rebuild artifact khác sau verification

Giả sử job A chạy `verify` ở commit P và tạo `order-service-1.4.2-stubs.jar`. Job B checkout một branch mới hơn, chạy plugin đóng gói riêng rồi publish **cùng tọa độ**. Khi đó kết quả producer test A **không còn xác minh bytes được publish**.

An toàn hơn:

1. Tạo artifact trong **workspace của build đã chạy verification**.
2. Tính checksum và lưu JAR như **CI output/artifact**.
3. Đưa **đúng JAR đã kiểm** vào job publish/staging.
4. Chặn overwrite release coordinates và xác minh checksum sau publish.
5. Ghi producer Git SHA, CI run, test report và digest vào release manifest.

Nếu chính sách yêu cầu **rebuild khi publish**, hãy chứng minh build lại dùng cùng source/toolchain/dependencies và chạy verification gate phù hợp; chỉ so file name là không đủ.

## 11. Mã consumer test thật với Stub Runner version cố định

Giả sử Billing Service dùng Spring Framework 6.1+ để gọi Order Service. Mã client:

~~~java
package com.acme.billing;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public final class OrderClient {
    private final RestClient http;

    public OrderClient(String baseUrl) {
        this.http = RestClient.create(baseUrl);
    }

    public OrderDto getOrder(long id) {
        return http.get()
            .uri("/api/orders/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(OrderDto.class);
    }

    public record OrderDto(long id, String status, long amountMinor) {}
}
~~~

Một consumer JUnit 5 test:

~~~java
package com.acme.billing;

import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = OrderClientContractTest.TestApp.class)
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/repository/releases"
)
class OrderClientContractTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {}

    @Autowired
    private StubFinder stubFinder;

    @Test
    void readsPaidOrderFromPinnedStubVersion() {
        URL url = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Required Order Service stub did not start"
        );

        OrderClient client = new OrderClient(url.toExternalForm());
        OrderClient.OrderDto dto = client.getOrder(42L);

        assertThat(dto.id()).isEqualTo(42L);
        assertThat(dto.status()).isEqualTo("PAID");
        assertThat(dto.amountMinor()).isEqualTo(125000L);
    }
}
~~~

Ví dụ yêu cầu **JDK 17+, Spring Boot/Spring Cloud Contract tương thích, RestClient, AssertJ** và artifact `stubs` đã được publish; repository URL chỉ là **minh họa**. Kho riêng có thể cần read credentials, TLS/proxy do CI cấu hình. `StubsMode.REMOTE` nói về **nguồn tải JAR**, không có nghĩa HTTP client gọi trực tiếp Maven repository.

Điểm then chốt: annotation yêu cầu **version `1.4.2` cố định** và bài test tìm **URL HTTP stub động** qua `StubFinder`. Khi CI rerun, cần giữ **chính checksum của `1.4.2-stubs.jar`**, không chỉ chuỗi annotation.

### 11.1. Khi test phải đổi sang stub release mới

Nếu mục tiêu là kiểm ứng dụng Billing với **producer release 1.4.3**, hãy cập nhật rõ tọa độ artifact và record phiên bản test. Đây là **một compatibility test mới**, không phải “rerun cùng input 1.4.2”.

Với nhiều producer:

~~~java
@AutoConfigureStubRunner(
    ids = {
        "com.acme:order-service:1.4.2:stubs",
        "com.acme:inventory-service:2.1.0:stubs"
    },
    stubsMode = StubRunnerProperties.StubsMode.REMOTE
)
~~~

Cần ghi **cả hai artifact coordinates + checksums** và tra URL riêng cho Order/Inventory. Một lần rerun giữ Order v1.4.2 nhưng tự nâng Inventory lên v2.1.1 **không còn cùng bộ đầu vào**.

## 12. Cổng WireMock động không phải nguồn nondeterminism về hợp đồng

Một bản test có thể chạy:

~~~text
Run A: Order stub URL = http://localhost:12347
Run B: Order stub URL = http://localhost:13782
~~~

Hai port khác nhau **không nhất thiết có nghĩa đầu vào hợp đồng khác**. Stub Runner có thể chọn cổng khả dụng ở mỗi run; consumer test phải dùng **địa chỉ thực do StubFinder trả**. Nếu cố định `localhost:8089`, các job song song có thể tranh cổng hoặc gọi nhầm instance.

Với test đã được thiết kế đúng:

~~~java
URL stubUrl = Objects.requireNonNull(
    stubFinder.findStubUrl("com.acme", "order-service")
);
OrderClient client = new OrderClient(stubUrl.toExternalForm());
~~~

**Tính tái lập mong muốn là cùng HTTP semantics/response từ cùng artifact**, không bắt mọi CI job nhận đúng cùng một số port. Port là tài nguyên môi trường runtime, cần được **khám phá** thay vì hardcode. Vẫn phải đảm bảo URL có hostname có thể truy cập từ network namespace của consumer test; `localhost` ở container A không trỏ tới container B.

## 13. Fixtures, database và trạng thái test: cố định trước mỗi lần chạy

Một pipeline có thể tải **đúng JAR stub** nhưng test vẫn flaky vì trạng thái bị lẫn:

| Nguồn trạng thái | Lỗi điển hình | Cách cô lập |
| --- | --- | --- |
| **Database producer test** | Order 42 ở trạng thái `PAID` trong run A, `PENDING` ở run B. | Seed fixture nhất quán, reset DB/transactions có kiểm soát. |
| **WireMock request journal** | Run B đếm lại request của test trước. | Tạo instance riêng hoặc `resetRequests()` an toàn giữa tests. |
| **WireMock scenarios** | State `recovered` tồn tại từ test retry trước. | Reset scenarios hoặc tạo server độc lập. |
| **Consumer in-memory cache** | Client đọc cache thay vì gửi request tới stub. | Clear cache cho từng test hoặc assert hành vi caching rõ. |
| **Clock/timezone** | Deadline/expiration thay đổi theo giờ chạy. | Inject `Clock.fixed`/timezone xác định khi kiểm logic thời gian. |
| **Random IDs** | Body/key thay đổi không có cách tái hiện. | Dùng seed có ghi nhận hoặc dữ liệu cố định phù hợp. |
| **Authentication** | JWT test hết hạn vào ngày hôm sau. | Fake/test token hoặc mock decoder được reset, tránh token thật phụ thuộc thời gian. |
| **Async messages** | Consumer verify trước khi event tới. | Đợi điều kiện có timeout hữu hạn, cô lập queue/topic. |
| **Network dependency** | Tải từ một dịch vụ thật không ổn định. | Stub/fake external boundary hoặc môi trường integration đã kiểm soát. |

**Không chỉ dùng `Thread.sleep(3000)` để làm test ổn định.** Một sleep cố định không chứng minh request/event đã tới đúng nơi. Với bất đồng bộ, chờ future/publisher hoàn tất, hoặc chờ trạng thái nghiệp vụ có timeout hữu hạn và thông báo lỗi rõ.

### 13.1. Cố định thời gian bằng một abstraction test được

Trong Java:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
    Instant.parse("2027-02-03T10:00:00Z"),
    ZoneOffset.UTC
);
~~~

Code nghiệp vụ nên nhận `Clock` qua dependency injection thay vì gọi `Instant.now()` tùy ý ở khắp nơi, nếu logic expiration/deadline là phần quan trọng của test. Giá trị thời gian **minh họa** và có thể đặt trong fixture configuration.

Với producer HTTP response có timestamp động, cần quyết định rõ contract kiểm **format/miền giá trị** hay kiểm **giá trị cố định**. Đừng cố định response chứa timestamp vô lý ngoài production hoặc làm matcher quá lỏng khiến lỗi định dạng lọt qua.

## 14. Thiết kế reset state mà không phá stubs

Trong WireMock, các khái niệm khác nhau:

~~~java
wireMockServer.resetRequests();  // Xóa lịch sử requests.
wireMockServer.resetScenarios(); // Đặt lại state của scenarios.
wireMockServer.resetAll();       // Xóa cả mappings và các state liên quan.
~~~

Nếu Stub Runner đã nạp **contract mappings** từ JAR, đừng gọi `resetAll()` không có chủ đích: request có thể bắt đầu trả 404 vì **mapping bị xóa**, không phải vì contract sai.

Với server chia sẻ giữa nhiều test chạy song song, một test gọi `resetRequests()` có thể xóa dữ liệu journal mà test khác đang đếm. Khi cần parallel execution, hãy ưu tiên **mỗi test/class có instance độc lập**; nếu dùng chung, cần correlation ID và quy tắc phối hợp bảo đảm tính nhất quán của measurements.

### 14.1. No-match 404 khác 404 nghiệp vụ

Nếu stub chỉ có mapping:

~~~http
GET /api/orders/42
~~~

mà consumer gửi `GET /api/order/42`, WireMock có thể trả **404 do request không khớp mapping**. Đó không phải bằng chứng producer đã xử lý `ORDER_NOT_FOUND`. Một consumer test lỗi 404 muốn tái lập phải có **hợp đồng lỗi riêng** với status và error body/code rõ ràng, đồng thời assert đúng request path/header.

Việc xác định **đúng mapping được chạy** giúp phân biệt regression của client với một stale/missing stub artifact.

## 15. Messaging contracts: giữ version và broker state

Spring Cloud Contract còn kiểm message qua Groovy/YAML DSL. Ví dụ sự kiện `OrderCreated`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV1'

    input {
        triggeredBy('publishOrderCreated()')
    }

    outputMessage {
        sentTo('orders.created')
        headers {
            header('contentType', 'application/json')
            header('schemaVersion', 1)
        }
        body(
            eventId: 'evt-001',
            orderId: 'ORD-42',
            amountMinor: 125000
        )
    }
}
~~~

Với messaging, **một JAR stub giống nhau** chưa đủ để kết quả giống nhau nếu:

- Broker dùng **queue/topic còn message cũ**.
- Consumer group/offset được dùng chung và thay đổi theo run.
- Retry/DLQ/replay khiến sự kiện từ run trước xuất hiện lại.
- Serializer/schema registry trả version hoặc compatibility mode khác.
- Đầu ra producer tạo `eventId` ngẫu nhiên hoặc timestamp không được kiểm soát.
- Test chạy song song và nhận nhầm message của nhau.

Một phương án an toàn có thể dùng **test binder/in-memory adapter** cho consumer contract test, và dùng **broker container version cố định** cho integration test transport thật. Với test trên broker:

1. Dùng namespace/topic/consumer group riêng theo run khi cần.
2. Thiết lập offset/start position có chủ đích, dọn dữ liệu theo policy.
3. Ghi version schema, destination và image của broker.
4. Đợi message theo điều kiện với timeout, không giả định event đến tức thời.
5. Dùng `eventId`/correlation ID để tránh xử lý nhầm hoặc trùng.

**`StubTrigger`/label có thể khởi phát message mẫu**, nhưng không tự chứng minh serialization trên broker thật hoặc exactly-once processing. Tính tái lập của messaging test cần cả **artifact contract** và **trạng thái/môi trường transport**.

## 16. Đầu vào CI nên được lưu trong một run manifest

Mỗi pipeline quan trọng nên xuất một **manifest có thể dùng để tái chạy** (run provenance). Ví dụ:

~~~json
{
  "runId": "billing-contract-ci-991",
  "source": {
    "repository": "billing-service",
    "commit": "0123456789abcdef0123456789abcdef01234567",
    "workflowRevision": "abcdefabcdefabcdefabcdefabcdefabcdefabcd"
  },
  "build": {
    "jdk": "17",
    "mavenWrapperVersion": "3.9.x",
    "springCloudReleaseTrain": "2023.0.x",
    "testProfile": "contract"
  },
  "stubs": [
    {
      "coordinate": "com.acme:order-service:1.4.2:stubs",
      "sha256": "<actual-jar-sha256>",
      "sourceProducerRunId": "order-producer-ci-483",
      "resolutionMode": "REMOTE",
      "repositoryId": "contract-releases"
    }
  ],
  "environment": {
    "runnerImageDigest": "<actual-image-digest>",
    "timezone": "UTC",
    "testDataRevision": "fixtures-v5"
  },
  "result": {
    "producerVerificationRef": "order-producer-ci-483/report",
    "consumerTestReportRef": "billing-contract-ci-991/tests",
    "status": "FAILED"
  }
}
~~~

Manifest này là **mẫu thiết kế nội bộ**, không phải schema bắt buộc của Spring Cloud Contract hay CI provider. Các placeholder `<...>` và version có `x` **không đủ để bảo đảm tái lập**; trong production cần điền **exact tool versions/digests và checksum thật** do tool xuất ra.

### 16.1. Các dữ liệu cần lưu nhưng không đưa vào manifest

Một số đầu vào là **bí mật** hoặc nhạy cảm:

- Maven/Gradle repository token.
- Private key/client certificate.
- Password broker/database.
- JWT production hoặc dữ liệu người dùng thật.

Không lưu chúng ở JSON manifest hay artifact logs. Thay vào đó, ghi **secret reference/identity và policy version** theo cách không làm lộ giá trị, bảo đảm người có quyền có thể phục hồi môi trường hợp lệ qua secret manager. Một credential được rotation có thể đổi giữa hai run mà **không thay đổi kết quả contract mong đợi**, miễn khả năng truy cập artifact giống nhau.

**Không đưa raw secrets vào test fixtures hay stubs** chỉ để tạo “cùng đầu vào”. Dữ liệu hợp đồng nên là synthetic test data, không có khả năng truy cập hệ thống thật.

## 17. Mẫu pipeline theo nguyên tắc “build once, test, promote”

Một pipeline producer/consumer thường có ba chặng:

~~~text
PRODUCER:
  checkout immutable producer SHA
    -> restore verified toolchain/dependencies
    -> generate producer contract tests
    -> run tests, require nonzero required test count
    -> package stubs and producer application
    -> compute stub SHA-256 / image digest
    -> store artifact + producer run manifest

COMPATIBILITY:
  checkout immutable consumer SHA
    -> use exact stub artifact from producer run
    -> run Stub Runner consumer test with pinned coordinates
    -> save consumer run manifest/test reports

PUBLISH/DEPLOY:
  require producer and compatibility gates pass
    -> publish or promote immutable stubs/app artifact
    -> deploy verified image digest
    -> record deployment revision/health metrics
~~~

**Thứ tự stage có thể khác theo tổ chức:** để chạy consumer compatibility test **trước** publish vào release repository, có thể dùng **staging repository/artifact handoff** hoặc cài JAR đúng bytes vào local test repository. Sau khi các gates đạt, promote **chính artifact đó** sang release. Không cần publish một release chưa được xác minh rồi hy vọng consumer test đỏ sẽ chặn kịp.

Nếu consumer chạy từ một CI runner khác, một bản `LOCAL` chỉ hoạt động khi JAR được chuyển/cài đúng cách vào Maven local của runner đó. Trong môi trường chia sẻ liên nhóm, `REMOTE` với staging/release repository có kiểm soát thường rõ ràng hơn.

## 18. Pseudocode CI giữ đầu vào cố định

Ví dụ dưới đây là **pseudocode trung lập nhà cung cấp**, không phải file GitHub Actions/GitLab CI/Jenkins chạy trực tiếp:

~~~yaml
pipeline:
  checkout:
    source: exact-git-commit
    workflow: approved-workflow-revision

  environment:
    jdk: pinned-vendor-and-version
    build_tool: repository-wrapper
    ci_image: pinned-image-digest
    test_timezone: UTC

  inputs:
    stub_coordinate: com.acme:order-service:1.4.2:stubs
    stub_sha256: <verified-digest>
    fixture_revision: fixtures-v5
    dependency_lock: committed-or-controlled-version-graph

  producer_gate:
    generated_contract_tests_required: true
    test_count_must_be_positive: true
    fail_if_contract_tests_skipped: true

  consumer_gate:
    run_real_client_through_stub_runner: true
    assert_status_and_business_data: true
    preserve_request_matching_evidence: true

  publish:
    allowed_after_required_gates: true
    promote_verified_bytes: true
    prevent_release_overwrite: true
    save_run_manifest: true
~~~

**Các khóa trong YAML này không phải tùy chọn Spring Cloud Contract**. Một hệ thống CI thực cần ánh xạ chúng sang script, artifact store, job dependencies, checks và permissions có hiệu lực. Dòng `stub_sha256: <verified-digest>` chỉ là **quy tắc phải kiểm**, không tự tính hay đối chiếu checksum.

### 18.1. Một đoạn shell minh họa cho Maven producer

Trong Linux CI runner có Maven Wrapper:

~~~shell
# Kiểm đúng source/toolchain của run.
git rev-parse HEAD
./mvnw -version

# Sinh và chạy tests producer theo lifecycle đã cấu hình.
./mvnw -B -ntp clean verify

# Chỉ sau khi đúng artifact tồn tại và test report đạt:
sha256sum target/order-service-1.4.2-stubs.jar
~~~

Trong Windows PowerShell, có thể tính SHA-256 bằng `Get-FileHash -Algorithm SHA256`. Các lệnh trong bài chỉ là **hướng dẫn thực hành**, không được chạy khi soạn nội dung. `target/order-service-1.4.2-stubs.jar` là đường dẫn minh họa; packaging configuration/version plugin có thể tạo artifact ở vị trí khác.

**Tính checksum chỉ sau khi chứng minh generated tests đã thực sự chạy.** Một file stale còn trong `target/` từ build trước không được coi là artifact của run hiện tại; dùng `clean` hoặc isolated workspace để loại trừ.

## 19. Ba kiểu rerun và cách diễn giải kết quả

### 19.1. Kiểu A: rerun từ CI run hiện tại

Tình huống: consumer job thất bại vì một request tới WireMock trả 404. Nút `Rerun failed job` có thể phù hợp nếu hệ CI cho phép giữ:

- Same **consumer source Git SHA** và workflow revision.
- Same **stub artifact coordinates/checksum**.
- Same toolchain/CI image và test profile.
- Same data fixture/reset policy và dependency graph.

Nếu rerun PASS, đây **chưa đủ** để tuyên bố “lỗi đã hết”. Có thể là một flaky test hoặc đầu vào đã drift. So manifest của hai lần chạy để loại trừ sai khác, sau đó xem request journal và trạng thái hạ tầng.

### 19.2. Kiểu B: cold-cache rebuild

Tình huống: nghi Maven local cache chứa stub cũ.

Cách làm là chạy từ **workspace/repository cache mới, được cô lập**, dùng nguồn artifact và dependency có version xác định. Với Maven, có thể chỉ định Maven local repository dành riêng cho run:

~~~shell
./mvnw -B -ntp \
  -Dmaven.repo.local=/tmp/contract-rerun-m2 \
  clean verify
~~~

Đường dẫn `/tmp/contract-rerun-m2` chỉ phù hợp Linux runner minh họa. Đây là **kiểm tra có thể tải lại từ remote**, không phải bảo đảm Maven/Stub Runner của mọi phiên bản tự cùng dùng local repository này; Stub Runner resolver cần được kiểm riêng.

Nếu warm-cache PASS nhưng cold-cache FAIL:

- Artifact hoặc dependency có thể chưa publish đúng.
- Credentials/proxy/TLS/metadata resolver có thể đang lỗi.
- Cache đã che một bản local không đúng version hoặc chưa được publish.
- Có thể job đang phụ thuộc các file đã được tạo thủ công trên một runner cũ.

**Đừng vội xóa toàn bộ cache production** khi chưa biết nguyên nhân: hãy tái hiện trong môi trường riêng và đối chiếu manifest/checksum.

### 19.3. Kiểu C: replay từ artifact đã archive

Tình huống: cần tái hiện lỗi của một release từ nhiều tuần trước.

Tải đúng **JAR `stubs` đã archive và kiểm SHA-256**; chạy consumer source/version tương ứng với toolchain/test fixture được ghi. Nếu CI muốn tránh mạng, có thể cài artifact vào Maven local của môi trường cô lập và dùng Stub Runner `LOCAL`. Nhưng cần chứng minh **đúng JAR** được nạp; `LOCAL` không tự đảm bảo checksum.

Đây là cách hữu ích khi repository snapshot đã thay đổi hoặc release trước bị gỡ khỏi remote theo chính sách retention. Nếu không còn artifact/bộ dependency để phục hồi, phải ghi nhận **giới hạn tái lập** thay vì kết luận lỗi không tồn tại.

## 20. Test song song: “cùng input” không đồng nghĩa cùng thứ tự thực thi

Trong CI, hai test threads có thể chạy theo thứ tự khác nhau. Nếu chúng cùng sửa global state, cùng port, cùng WireMock request journal hoặc dùng một DB schema chung, kết quả có thể phụ thuộc lịch scheduling.

Ví dụ dễ lỗi:

~~~java
// Cấu hình static dùng chung dễ gây xung đột khi chạy parallel.
RestAssured.baseURI = "http://localhost";
RestAssured.port = 8089;
~~~

Một test khác có thể thay `RestAssured.port` hoặc dùng port 8089 khiến toàn bộ test suite bị lẫn. Hãy dùng **request specification/client instance riêng**, port động từ `StubFinder` hoặc server riêng cho từng class/context.

| Nguồn race | Cách giải quyết |
| --- | --- |
| Shared mutable client config | Tạo client riêng, base URL được inject. |
| Shared WireMock mappings/journal | Mỗi test context/server riêng, hoặc khóa state/correlation phù hợp. |
| Database transaction chồng lấn | Cô lập schema/database, seed/cleanup rõ; không dựa thứ tự tests. |
| Shared message topic/consumer group | Namespace và group theo run khi cần, quản lý offsets. |
| Fixed port | Dynamic port và service discovery có kiểm soát. |
| Global fake clock hoặc random | Inject test-scoped instances, không đổi static giữa tests. |
| External rate limit | Stub/fake hoặc phân bổ quota, retry có giới hạn. |

Khi một test **chỉ PASS nếu test A chạy trước**, đó là lỗi cô lập test, không phải lý do để ghim thứ tự suite mãi mãi. Một rerun đáng tin phải không phụ thuộc vào side effects không được khai báo.

## 21. Khi cùng checksum mà kết quả vẫn khác

Một JAR `stubs` có SHA-256 giống nhau chỉ chứng minh **bytes JAR không đổi**. Nó không chứng minh:

1. Mọi test đều gửi **cùng HTTP request**.
2. Cùng Java/Jackson version sẽ parse body giống nhau.
3. Cùng Spring profile và retry configuration được áp dụng.
4. Cùng broker/DB/timezone/hệ thống mạng.
5. Cùng thứ tự test hoặc concurrency.
6. Consumer đã lấy đúng URL của **stub instance** thay vì gọi một server cũ.
7. Consumer test có cùng expectations/fixtures.

Vì vậy khi thấy SHA-256 giống nhưng test fail khác, hãy chuyển trọng tâm từ **artifact drift** sang **source/configuration/environment/test state**. Một bước điều tra hữu ích là kiểm **request thật** trên WireMock:

~~~java
wireMockServer.verify(
    1, getRequestedFor(urlEqualTo("/api/orders/42"))
);
~~~

Nếu đang dùng Stub Runner và không có bean `WireMockServer`, có thể dùng **WireMock Admin API** tại URL stub đã tìm được để xem request journal. Không dump Authorization/cookie/body dữ liệu nhạy cảm lên CI logs.

## 22. Ma trận chẩn đoán rerun khác kết quả

| Triệu chứng | Nghi ngờ đầu tiên | Kiểm chứng |
| --- | --- | --- |
| Cùng Git SHA nhưng checksum stub khác | Artifact bị ghi đè, SNAPSHOT/remote metadata đổi. | So coordinates, source producer run, checksum và repository audit. |
| Cùng stub checksum nhưng JSON parse khác | Client/Jackson/toolchain hoặc consumer source đổi. | So consumer SHA, dependency graph, profile, DTO và request/response thật. |
| Warm cache xanh, cold cache đỏ | Artifact chưa publish, repo auth/proxy/TLS, version dynamic. | Test resolver từ runner sạch, log đã redaction. |
| Cold cache xanh, warm cache đỏ | Local cache stale/corrupt hoặc snapshot metadata cũ. | So local file hash với remote, cô lập cache để đối chiếu. |
| Run A port 12347, run B port 13782 | Stub Runner cấp port động bình thường. | Kiểm `StubFinder` và actual request target, không ép port giống nhau. |
| `Address already in use` | Hardcode port hoặc hai tests chia sẻ server. | Dynamic port, isolation. |
| Mỗi rerun WireMock verify count tăng | Request journal chưa reset, shared context. | `resetRequests()` đúng lifecycle hoặc tạo instance mới. |
| Kết quả phụ thuộc thời điểm ngày chạy | Clock, token expiry, timezone. | Inject fixed clock và test token, lưu timezone. |
| Test messaging khi 0 khi 2 events | Broker group/offset, DLQ/replay và parallel consumers. | Cô lập topic/group và đợi event có timeout. |
| Consumer stub trả 404 | Sai mapping, request method/path/header hoặc artifact cũ. | Inspect JAR, request journal, phân biệt no-match với 404 nghiệp vụ. |
| Artifact tọa độ đúng nhưng tải 401/403 | Auth/permissions repository thay đổi. | Kiểm read identity và secret refs, không in token. |
| Maven `-U` làm test khác | Snapshot/dependency metadata được cập nhật. | So dependency graph và artifact hashes trước/sau. |
| Producer test xanh nhưng deployed producer phá consumer | Test thiếu coverage, sai image digest hoặc publish/deploy lệch build. | So generated tests, release manifest và actual deployment. |
| Rerun job được run với workflow mới | CI config drift/actions khác. | So workflow revision, script versions và runner image. |
| Test fail khi chạy tất cả nhưng pass riêng | Shared state/race/ordering. | Chạy parallel/isolation experiments và kiểm fixtures. |

**Điều tra theo thứ tự:** identity của source → toolchain/dependencies → stub coordinates **và bytes** → CI configuration → fixtures/state → request thực → producer/consumer implementation. Đừng sửa contract DSL chỉ để chữa một lỗi cache hoặc auth của repository.

## 23. Bảo mật khi thu thập đầu vào để rerun

Mục tiêu “lưu đủ thông tin tái lập” **không cho phép lưu mọi thứ**. Các rủi ro:

| Dữ liệu | Có nên lưu trong CI manifest? | Lý do |
| --- | --- | --- |
| Git SHA, CI run ID | **Có** | Định danh source và test run. |
| Artifact coordinates, SHA-256 | **Có** | Chứng minh đúng JAR được dùng. |
| JDK/build tool versions | **Có** | Điều tra runtime/toolchain drift. |
| Image digest, test profile | **Có** | Xác định CI runtime. |
| Secret reference/identity name không nhạy cảm | **Có thể** | Tái thiết quyền từ secret manager mà không lộ giá trị. |
| Repository token/password/private key | **Không** | Không đưa secrets vào artifacts/logs. |
| Raw HTTP Authorization/Cookie | **Không** | Có thể cho phép truy cập thật. |
| Dữ liệu khách hàng thật trong stub/fixture | **Không** | Rò rỉ PII và vi phạm chính sách dữ liệu. |
| Full environment dump | **Không** | Có thể chứa token, endpoints nội bộ nhạy cảm. |

Nếu cần share run manifest cho nhóm khác, hãy xác định **quyền đọc** vì tên repo, service graph, deployment revision và artifact registry có thể là thông tin nội bộ. Đặt retention policy cho CI logs/test reports và redaction trước khi upload.

## 24. Khi nào rerun không thể cho kết quả hoàn toàn giống?

Có những yếu tố **không thể hoặc không nên cố định tuyệt đối**:

- Scheduler và network latency.
- Port động và process ID.
- Chứng thư/token ngắn hạn đã rotation.
- Nguồn dịch vụ ngoài hoặc broker có state động.
- Timeouts và contention trên shared CI runner.
- Artifact SNAPSHOT đã bị ghi đè và không còn archive.
- External integrations có side effects không thể đảo ngược.

Khi đó, mục tiêu là:

1. **Cố định những đầu vào ảnh hưởng semantics**: source, contract, stubs, dependencies, fixtures.
2. **Cô lập những yếu tố có thể cô lập**: server, DB, broker, cache, clock.
3. **Ghi nhận những yếu tố không thể cố định**: runner, network, time, external service versions.
4. **Dùng assert theo hành vi ổn định**: không assert port số cụ thể hoặc wall-clock duration cứng nếu hợp đồng không cam kết.
5. **Báo cáo giới hạn**: “cùng artifact/commit nhưng khác môi trường mạng” thay vì khẳng định đây là rerun đồng nhất.

Khả năng tái lập là **mức độ có thể giải thích và kiểm chứng**, không phải yêu cầu mọi log lines có timestamp, port và thứ tự hoàn toàn giống nhau.

## 25. Bài thực hành: tái chạy một consumer contract failure

Chuẩn bị hai dự án Spring Boot: **Order Service** có Contract Verifier, **Billing Service** có Stub Runner.

1. **Định nghĩa HTTP contract** cho `GET /api/orders/42` trả JSON `id=42`, `status=PAID`, `amountMinor=125000` bằng Groovy hoặc YAML DSL.
2. **Tạo producer implementation + base test**, seed dữ liệu và xác nhận generated producer tests thật sự được sinh/chạy.
3. **Ghim JDK, Maven/Gradle Wrapper và Spring Cloud BOM/plugin versions** trong build configuration; ghi chúng vào một run manifest.
4. **Chạy producer verification**, kiểm reports và test count; cố tình đổi kiểu `amountMinor` từ number sang string để xác nhận test FAIL, rồi hoàn nguyên.
5. **Đóng gói và publish JAR `stubs` phiên bản xác định**, ví dụ `com.acme:order-service:1.4.2:stubs`; tính SHA-256 thật của JAR.
6. **Viết OrderClient thật và Stub Runner consumer test** với version `1.4.2`, dùng `StubFinder` lấy URL động, assert status/body và method/path quan trọng.
7. **Lưu consumer Git SHA, producer release SHA, artifact coordinates/checksum, CI run ID, toolchain và profile** vào manifest.
8. **Chạy consumer CI lần A**, ghi kết quả và test reports. Không commit secrets.
9. **Chạy lại cùng source/artifact lần B** với warm cache; so manifest và checksum trước khi kết luận kết quả giống/khác.
10. **Tái chạy từ cold cache lần C**, kiểm repository có tải lại đúng artifact và quyền read còn hiệu lực.
11. **Thử gây drift** trong môi trường thử nghiệm: publish SNAPSHOT mới ở cùng tọa độ hoặc thay một dynamic dependency; xác minh checksum/dependency graph bộc lộ đầu vào đã khác. Không ghi đè release thật.
12. **Thử gây flaky**: cho hai tests dùng chung request journal hoặc không reset scenario; quan sát count không ổn định rồi cô lập server/state.
13. **Thử clock giả** bằng `Clock.fixed` và test token; so với cách phụ thuộc thời gian thực.
14. **Thử lỗi 404 no-match** do client gọi sai path; dùng request journal để phân biệt với contract lỗi nghiệp vụ.
15. **Nếu có messaging**, dùng topic/group cô lập và một event có `schemaVersion`/`eventId` xác định; thử replay để thấy ảnh hưởng của broker state.
16. **Tạo báo cáo điều tra**: chỉ rõ trường hợp nào là source drift, artifact drift, environment drift, test state leak hoặc regression thật.
17. **Đưa vào CI gate**: chỉ publish immutable stubs sau producer verification; consumer compatibility tests dùng đúng version, report và checksum tương ứng.

**Tiêu chí đạt:** người học có thể chỉ ra **chính xác Git SHA, artifact `stubs` và checksum của hai lần chạy**, tái chạy consumer test từ môi trường mới, giải thích vì sao port có thể khác mà contract không đổi, và phân biệt được **sai lệch đầu vào** với **lỗi contract/implementation**.

## 26. Checklist cho pipeline có thể tái chạy

| Kiểm tra | Kỳ vọng |
| --- | --- |
| Source | Git SHA đầy đủ của producer/consumer và workflow revision có thể truy xuất. |
| Contracts | Source paths/commit xác định; không nạp trùng cùng tình huống qua Groovy/YAML. |
| Build toolchain | Maven/Gradle Wrapper, JDK và CI image được ghim hoặc ghi exact version/digest. |
| Dependency resolution | BOM/plugin/lock versions đúng; không có dynamic/mutable input ngoài kiểm soát. |
| Producer verification | Generated tests thật sự chạy, test count hợp lệ và PASS trước publish. |
| Stub artifact | Coordinates, classifier `stubs`, SHA-256 và producer run có thể đối chiếu. |
| Publication | Release bất biến; nếu dùng SNAPSHOT phải có định danh bytes của run. |
| Consumer testing | Stub Runner tải đúng artifact; client/listener thật được kiểm, không chỉ test WireMock. |
| HTTP runtime | Stub URL động được tra đúng, không hardcode port. |
| Messaging runtime | Schema/destination, broker/container version, topic/group/offset được kiểm soát. |
| Fixtures | DB, clock, random seed, auth test data, request journal/scenario được reset/cô lập. |
| Concurrency | Tests không chia sẻ mutable state thiếu kiểm soát. |
| Cache | Có chiến lược warm/cold cache và đối chiếu artifact checksum. |
| Manifest | Có source/toolchain/stub hashes/test result refs và không chứa secrets/PII. |
| Rerun semantics | Ghi rõ rerun source, rebuild hay replay artifact; công bố sai lệch còn lại. |
| Incident handling | Có đường từ failure log → manifest → artifact → contract → producer/consumer source. |

## 27. Câu hỏi tự kiểm tra

1. Vì sao “bấm Rerun trên cùng branch” chưa chắc là chạy với cùng đầu vào?
2. Khác biệt giữa **cùng Maven coordinates** và **cùng checksum artifact** là gì?
3. Một JAR `-SNAPSHOT` có thể làm consumer CI đổi kết quả mà không đổi source ra sao?
4. `StubsMode.LOCAL` có chứng minh remote repository/credentials còn hoạt động không?
5. Vì sao cần ghi cả producer Git SHA và consumer Git SHA?
6. Khi một PR được CI chạy trên synthetic merge commit, bạn cần ghi gì để rerun chính xác?
7. Dùng Spring Cloud BOM có tự khóa Gradle/Maven plugin version, JDK và runner image không?
8. Vì sao generated producer test count = 0 khiến artifact `stubs` không đủ tin cậy dù build xanh?
9. Một consumer test dùng đúng stub checksum có còn flake vì Clock, DB hoặc WireMock journal không?
10. Vì sao port WireMock khác giữa run A và B không nhất thiết phá khả năng tái lập?
11. `resetRequests()` khác `resetAll()` thế nào và vì sao phải cẩn thận khi dùng Stub Runner?
12. Nếu consumer test lỗi 404, làm sao biết là no-match do sai path hay lỗi 404 nghiệp vụ?
13. Vì sao một run warm-cache PASS chưa đủ chứng minh remote artifact có thể tải từ cold cache?
14. Dùng `mvn -U` có đảm bảo tải đúng bytes của bản SNAPSHOT cũ không?
15. Trong messaging test, broker offset/consumer group/DLQ ảnh hưởng rerun như thế nào?
16. Phân biệt **rerun same job**, **rebuild same SHA** và **replay verified artifact**.
17. Một run manifest phải lưu gì và phải tránh lưu gì?
18. Khi có nhiều producer stubs, cần ghi những identity nào để chứng minh đúng tổ hợp version?
19. “Build once, test, promote” giúp tránh producer image và artifact stub lệch nhau ra sao?
20. Nếu cold cache FAIL nhưng warm cache PASS, những nguyên nhân nào cần điều tra trước khi sửa code?
21. Khi nào hai lần chạy khác nhau mà vẫn được coi là kiểm cùng contract semantics?
22. Vì sao CI kết quả xanh của consumer không thể thay thế generated producer verification?

**Kết luận:** **Tái chạy pipeline với cùng đầu vào không chỉ là giữ nguyên Git commit; phải xác định đúng phiên bản và bytes của artifact `stubs`, toolchain, dependency graph, CI configuration, fixtures và trạng thái môi trường**. Trong Spring Cloud Contract, producer phải sinh và chạy generated tests trước khi xuất bản JAR `stubs`; consumer dùng Stub Runner nạp **đúng artifact được ghim**, tra HTTP URL động hoặc cấu hình messaging adapter theo hợp đồng rồi kiểm mã client/listener thật. Lưu **run manifest với Git SHAs, artifact coordinates/checksums, toolchain và test reports**, phân biệt warm/cold cache, tránh mutable snapshots khi replay lịch sử và cô lập shared state. Nhờ đó, khi một job CI fail, nhóm có thể chứng minh mình đang tái hiện **cùng tương tác và cùng artifact** hay đã gặp **một đầu vào mới**, thay vì sửa hợp đồng hoặc rerun vô hạn mà không biết nguyên nhân.
