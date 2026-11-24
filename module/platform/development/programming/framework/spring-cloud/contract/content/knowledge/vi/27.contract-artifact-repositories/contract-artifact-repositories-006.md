# Xác thực, proxy và truy cập kho trong CI

Trong hệ thống microservices, **Spring Cloud Contract** phát huy giá trị khi producer không chỉ sinh kiểm thử từ Groovy/YAML DSL mà còn **phát hành artifact stub** để consumer sử dụng độc lập. Tuy nhiên, một pipeline có thể thất bại ngay cả khi các hợp đồng đều đúng: CI không xác thực được với kho Maven, proxy chặn đường tải dependency, certificate của repository không được Java tin cậy, hoặc Stub Runner tải nhầm artifact do version/classifier không đúng.

Bài thuộc chương **Kho hợp đồng và artifact** của mô-đun **SPRING_CLOUD_CONTRACT**. Mô-đun tập trung vào hợp đồng giữa producer và consumer qua HTTP hoặc message, sinh producer tests, xuất bản stubs, chạy Stub Runner và kết hợp CI để phát hiện thay đổi API không tương thích. Ở đây, ta học cách **thiết kế quyền truy cập kho**, cung cấp **credentials qua secret manager của CI**, định tuyến qua **proxy**, kiểm tra **TLS**, và chẩn đoán những lỗi truy xuất artifact mà không làm lộ thông tin nhạy cảm.

Ví dụ xuyên suốt: **Order Service** (producer) tạo và phát hành `com.acme:order-service:1.0.0:stubs` vào một kho Maven riêng; **Billing Service** (consumer) dùng `Stub Runner` để tải phiên bản đó rồi kiểm thử mã HTTP client. Các tên miền, tài khoản và version trong bài đều là **giá trị minh họa**, cần thay bằng thông tin nội bộ được cấp phép của dự án.

## 1. Nhìn đúng ba nơi lưu trữ và một server chạy thử

Trước khi cấu hình xác thực, cần xác định **đang truy cập dịch vụ nào**:

| Thành phần | Ví dụ | Chứa gì? | Ai cần truy cập? |
| --- | --- | --- | --- |
| **Kho source contract** | Git repository nội bộ | Groovy/YAML DSL, code producer, base tests. | Developer và CI có quyền đọc source; người sửa hợp đồng cần quyền ghi theo quy trình review. |
| **Maven artifact repository** | `https://repo.example.org/repository/releases` | JAR ứng dụng, JAR classifier `stubs`, POM và metadata. | Producer CI cần quyền publish; consumer CI cần quyền read. |
| **Maven dependency/plugin repositories** | Maven Central hoặc mirror nội bộ | Spring Boot/Spring Cloud libraries và Maven plugins. | Cả producer lẫn consumer CI cần quyền resolve. |
| **HTTP stub server đang chạy** | `http://localhost:12543` | WireMock mappings đã nạp, trả response mẫu trong test. | HTTP client của consumer test; không phải nơi publish artifact. |

**Một URL của Maven repository không phải base URL của API producer.** Khi dùng `Stub Runner REMOTE`, consumer có thể tải JAR `stubs` từ `https://repo.example.org/...`, sau đó khởi động WireMock ở `localhost` với **cổng động**. Mã `OrderClient` phải gọi **URL WireMock được cấp**, không gọi địa chỉ của Maven repository.

~~~mermaid
flowchart TD
    A["Kho Git: hợp đồng + producer code"] --> B["Producer CI"]
    B --> C["Contract Verifier sinh/chạy producer tests"]
    C --> D{"Tests đạt?"}
    D -->|Không| E["Chặn publish"]
    D -->|Có| F["Đóng gói order-service-1.0.0-stubs.jar"]
    F -->|Credential có quyền ghi| G["Maven artifact repository"]
    G -->|Credential chỉ đọc| H["Billing consumer CI + Stub Runner"]
    H --> I["WireMock HTTP stub được khởi động"]
    I --> J["OrderClient gửi HTTP tới URL stub động"]
    J --> K["Assert response + request thực tế"]
~~~

Nếu dùng **hợp đồng ngoài repository producer**, có thêm một đường tải source contracts (Git, SCM hoặc Maven contract artifact tùy workflow). Khi đó, quyền truy cập **nguồn hợp đồng** và quyền truy cập **artifact stub đã phát hành** có thể là hai bộ credentials khác nhau. Không tự đồng nhất chúng chỉ vì cả hai cùng tên “contract repository”.

## 2. Artifact tọa độ nào được publish và tải?

Giả sử Order Service có tọa độ Maven:

~~~text
groupId    = com.acme
artifactId = order-service
version    = 1.0.0
classifier = stubs
extension  = jar
~~~

Đối với Stub Runner, dạng rút gọn phổ biến:

~~~text
com.acme:order-service:1.0.0:stubs
~~~

Một bản release có thể được repository lưu như:

~~~text
com/acme/order-service/1.0.0/
    order-service-1.0.0.pom
    order-service-1.0.0.jar
    order-service-1.0.0-stubs.jar
~~~

**Tên file trong repository phụ thuộc Maven layout và cách publisher đính kèm artifact.** Điều quan trọng là tọa độ group/artifact/version/**classifier** phải khớp. Nếu producer chỉ publish `order-service-1.0.0.jar` nhưng consumer yêu cầu `...:stubs`, một lỗi `artifact not found` là hợp lý, dù artifact ứng dụng bình thường đã có trong kho.

Trước khi xét xác thực/proxy, hãy xác nhận:

1. Producer đã chạy **generated producer tests** và đạt.
2. JAR classifier `stubs` thực sự được tạo, đính kèm vào publication.
3. Artifact đã được **publish vào đúng repository và đúng version**.
4. Consumer yêu cầu **chính tọa độ đó**, không nhầm SNAPSHOT/release, classifier hay groupId.
5. Repository URL là **endpoint Maven layout**, không phải trang web quản trị, trang login hoặc URL duyệt thư mục không dành cho Maven resolver.

**Không chữa lỗi “artifact không tồn tại” bằng cách cấp quyền ghi rộng hơn.** Cần tách lỗi **tọa độ/đường dẫn** khỏi lỗi **xác thực hoặc phân quyền**.

## 3. Mô hình quyền: ai được đọc, ai được ghi?

Tối thiểu có hai danh tính CI:

| Danh tính | Công việc | Quyền tối thiểu nên cấp |
| --- | --- | --- |
| **Producer publish identity** | Đẩy `stubs.jar`, POM/metadata lên kho được phép. | Quyền **write/deploy** vào repository hoặc namespace của Order Service; có read nếu công cụ cần kiểm tồn tại. |
| **Consumer read identity** | Stub Runner tải artifact theo tọa độ. | Quyền **read** những stubs/repositories được dùng. |
| Developer local | Chạy test hoặc publish thử trong môi trường cá nhân. | Quyền read, write chỉ khi được phép và có audit. |
| Release automation | Phát hành bản release đã qua kiểm thử. | Quyền publish theo quy trình phê duyệt và môi trường chỉ định. |

**Không dùng một tài khoản quản trị kho cho mọi CI job.** Một consumer bị lộ token chỉ-read ít gây hại hơn token có thể ghi/ghi đè toàn bộ kho release. Với repository manager như Nexus/Artifactory hoặc artifact service tương đương, hãy tạo role/service principal phù hợp và giới hạn phạm vi, thay vì cấp quyền rộng cho mọi dự án.

Các chính sách hữu ích:

- **Credentials ngắn hạn** hoặc workload identity/OIDC khi nền tảng repository và CI hỗ trợ; nếu dùng token dài hạn, có chính sách rotation rõ.
- **Tách môi trường snapshot và release**; consumer production nên pin release/version đã duyệt.
- **Artifact release bất biến** khi chính sách repository cho phép, ngăn ghi đè cùng tọa độ làm kết quả test thay đổi ngầm.
- **Không đưa token vào POM, `build.gradle`, contract DSL hoặc Git history**.
- **Không cấp bí mật publish** cho untrusted pull requests từ fork hoặc code chưa được chấp thuận.
- **Không dùng token thật trong WireMock stub headers/body**: stub artifact được phân phối rộng hơn log kiểm thử thông thường.

## 4. Maven: thông tin repository nằm ở POM, bí mật nằm ở settings

Trong producer Maven, endpoint phát hành thường được khai báo bằng `distributionManagement`:

~~~xml
<distributionManagement>
    <repository>
        <id>releases</id>
        <url>https://repo.example.org/repository/releases</url>
    </repository>
    <snapshotRepository>
        <id>snapshots</id>
        <url>https://repo.example.org/repository/snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

Đây là **cấu hình đích deploy**, không chứa mật khẩu. `<id>releases</id>` và `<id>snapshots</id>` là **khóa logic** để Maven tìm credentials tương ứng trong `settings.xml`.

Ví dụ `settings.xml` được CI tạo từ template an toàn, minh họa bằng Maven settings interpolation từ biến môi trường:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>releases</id>
            <username>${env.MAVEN_PUBLISH_USER}</username>
            <password>${env.MAVEN_PUBLISH_TOKEN}</password>
        </server>
        <server>
            <id>snapshots</id>
            <username>${env.MAVEN_PUBLISH_USER}</username>
            <password>${env.MAVEN_PUBLISH_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

**Chú ý:** tài khoản thường dùng password hoặc token do repository cấp; một số nhà cung cấp yêu cầu token ở trường `username`, `password` hay header khác. Ví dụ này chỉ áp dụng khi **repository hỗ trợ Basic authentication/token dưới hình thức username/password** và Maven/plugin thực tế hỗ trợ cách cấu hình đó.

Điểm cần nhớ:

1. `settings.xml` là **cấu hình người dùng/CI**, không phải nội dung bắt buộc commit vào repository.
2. Biểu thức `${env.MAVEN_PUBLISH_TOKEN}` được Maven diễn giải từ **environment của tiến trình Maven**, khi Maven settings interpolation áp dụng.
3. ID trong `settings.xml` phải khớp **ID của repository mà lệnh deploy dùng**. ID sai có thể khiến request bị gửi **không kèm credentials**.
4. Nếu dự án dùng mirror nội bộ hoặc alternate deployment repository, **repository ID thực mà Maven gửi request tới** có thể khác ID được đọc từ một đoạn POM đơn lẻ. Cần kiểm effective settings, CI profile và Maven deploy configuration.
5. Đừng đặt password/token thô vào `pom.xml` hoặc truyền `-Dpassword=...` trên command line nếu có thể xuất hiện trong process list/log.

### 4.1. Lệnh Maven trong CI

Khi CI đã đặt môi trường và cung cấp settings qua đường dẫn được kiểm soát:

~~~shell
./mvnw -s "$MAVEN_SETTINGS_FILE" clean verify
./mvnw -s "$MAVEN_SETTINGS_FILE" deploy
~~~

Đây là **hai cách gọi minh họa**; `deploy` cũng đi qua các phase trước và có thể chạy lại test. Một pipeline có thể tách job build/verify và job publish artifact đã xác minh để tránh rebuild, nhưng khi tách phải đảm bảo artifact được publish là **đúng bytes từ job đạt verification**.

**`mvn deploy` không tự chứng minh producer verification đã chạy** nếu pipeline dùng `-DskipTests`, generated tests chưa được phát hiện hoặc task publish là một goal độc lập. Cần kiểm reports và điều kiện CI, không chỉ đọc mã thoát 0.

## 5. Maven: consumer tải dependency qua repository nào?

Khác `distributionManagement` (dùng để publish), consumer có thể cấu hình **repository dùng để tải dependency/artifact**:

~~~xml
<repositories>
    <repository>
        <id>contract-releases</id>
        <url>https://repo.example.org/repository/releases</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>
~~~

CI consumer chỉ cần credential **read** cho repository đó:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>contract-releases</id>
            <username>${env.MAVEN_READ_USER}</username>
            <password>${env.MAVEN_READ_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

**Phân biệt:** ID `contract-releases` của **repository đọc** và ID `releases` của **repository ghi** có thể khác nhau, dù URL trỏ tới cùng kho. Nếu dùng Maven settings để xác thực, ID phải khớp với **repository mà resolver thực sự chọn**, không phải tự động là tên file JAR.

Trong môi trường doanh nghiệp, có thể dùng **một mirror/repository group được cấp quyền** để Maven tải dependencies từ nhiều nguồn. Nhưng **không tự giả định Stub Runner luôn dùng cùng resolver, same effective settings và mirror rules của lệnh `mvn`**; cần kiểm hành vi của phiên bản Stub Runner đang chạy trong process consumer.

### 5.1. Mirror không phải repository upload

Maven `mirrors` trong `settings.xml` định hướng việc **resolve artifact/plugin** về proxy repository hoặc mirror:

~~~xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <mirrorOf>external:*</mirrorOf>
        <url>https://repo.example.org/repository/maven-group</url>
    </mirror>
</mirrors>
~~~

Ví dụ `external:*` hướng việc tải từ các external repositories được áp dụng tới mirror nội bộ theo quy tắc Maven; cần kiểm policy của công ty và repository IDs. Mirror có thể giúp cache Maven Central và tránh để CI tự truy cập internet.

**Không cho rằng cấu hình mirror là đích deploy**. Publish lên một repository cụ thể vẫn cần `distributionManagement`/deploy configuration và quyền ghi tại đích đó. Một repository group read-only dù tải được dependency cũng có thể **không cho upload**.

## 6. Stub Runner REMOTE: tải JAR và tìm địa chỉ server là hai bước

Billing Service dùng Stub Runner với một artifact cụ thể:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/repository/releases"
)
class BillingContractTest {
    // Inject StubFinder, gọi OrderClient thật và assert response.
}
~~~

`repositoryRoot` trong ví dụ là **URL Maven repository để tải JAR `stubs`**. Nó **không phải base URL** cho `GET /api/orders/42`. Sau khi nạp artifact, Stub Runner có thể khởi động WireMock cục bộ ở một cổng khả dụng.

Một bài test có thể tra đúng địa chỉ HTTP stub đang chạy:

~~~java
import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cloud.contract.stubrunner.StubFinder;

@Autowired StubFinder stubFinder;

@Test
void resolvesOrderStub() {
    URL url = Objects.requireNonNull(
        stubFinder.findStubUrl("com.acme", "order-service"),
        "Order Service stub not started"
    );

    OrderClient client = new OrderClient(url.toExternalForm());
    OrderClient.OrderDto order = client.getOrder(42L);

    assertThat(order.id()).isEqualTo(42L);
    assertThat(order.status()).isEqualTo("PAID");
}
~~~

Đây là **đoạn test minh họa**, giả định ứng dụng Billing đã có `OrderClient`, DTO và AssertJ; không phải một class Java đầy đủ. Mục tiêu là phân biệt:

- **Repository URL:** `https://repo.example.org/repository/releases`, dùng **credentials read**.
- **Stub HTTP URL:** chẳng hạn `http://localhost:12543`, dùng để gọi **API giả** trong consumer test.

### 6.1. Cách cung cấp credentials cho Stub Runner

Spring Cloud Contract Stub Runner có thể dùng cơ chế resolver/transport tích hợp để tải artifact. **Không giả định mọi phiên bản tự đọc `settings.xml` và credentials giống hệt Maven CLI**. Tùy release train và cách khởi tạo, có thể hỗ trợ các thuộc tính Stub Runner, Aether/Maven settings hoặc custom repository resolver.

Quy trình đúng:

1. Xác nhận repository **thực sự yêu cầu loại auth nào**: Basic/token, cloud identity, bearer token, mTLS hay cách khác.
2. Kiểm tài liệu/API của **phiên bản Spring Cloud Contract Stub Runner** mà consumer đang dùng về cách cấu hình authentication.
3. Truyền secrets từ **CI secret manager** vào cơ chế hỗ trợ, không hardcode trong annotation hoặc `application-test.yml` được commit.
4. Chạy consumer test trong môi trường CI **không có Maven local cache sẵn artifact** để chứng minh remote download thật.
5. Kiểm log resolver ở mức đủ để chẩn đoán nhưng **không in username/password/token**.

Nếu repository dùng Basic auth và phiên bản Stub Runner hỗ trợ cấu hình username/password tương ứng, hãy nối chúng tới **environment/secret injection** theo cơ chế của dự án. Trường hợp repository yêu cầu OIDC/mTLS/custom header, **không cố biến token đó thành một Basic password** nếu transport không hỗ trợ; cần resolver/proxy có khả năng xác thực phù hợp.

**Không đưa token vào URL** như `https://user:token@repo.example.org/...`. URL có thể bị ghi trong exception, CI artifacts, test reports, shell history và log proxy. Ưu tiên credentials tách biệt và masked.

### 6.2. LOCAL không phải là cách lách xác thực REMOTE

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

`LOCAL` dùng artifact đã có trong **Maven local repository** của môi trường chạy. Nó phù hợp khi producer đã `mvn install` vào cùng local repo hoặc có bước CI chuẩn bị artifact đúng cách.

`LOCAL` **không chứng minh** consumer có thể tải bản release từ remote repository. Một test CI vô tình có artifact cache sẵn có thể PASS dù **credential đọc kho đã hết hạn**. Vì thế, bài kiểm riêng cho remote download nên chạy từ cache sạch hoặc một runner cô lập.

## 7. CI secrets: cấp phát, truyền và thu hồi

Một pipeline bảo mật không đưa secrets vào Git, POM hay Markdown. Thay vào đó, hệ thống CI lưu secrets và cung cấp chúng tại runtime cho **job được phép**.

| Biến môi trường minh họa | Job dùng | Quyền |
| --- | --- | --- |
| `MAVEN_PUBLISH_USER` | Producer publish job | Service identity được phép upload. |
| `MAVEN_PUBLISH_TOKEN` | Producer publish job | **Write/deploy** vào namespace producer. |
| `MAVEN_READ_USER` | Consumer contract test job | Service identity chỉ-read. |
| `MAVEN_READ_TOKEN` | Consumer contract test job | **Read** artifacts cần thiết. |
| `MAVEN_SETTINGS_FILE` | Job chạy Maven | Đường dẫn settings do runner tạo hoặc provision. |
| `ARTIFACT_REPO_URL` | Job build/test | URL repository được duyệt, không chứa credentials. |

Những biến này **chỉ là tên minh họa**, không phải biến bắt buộc của Spring Cloud Contract.

Một pipeline tốt cần các chính sách sau:

- Secret publish chỉ xuất hiện trong **job phát hành** sau khi producer verification đạt, không phải trong mọi job unit test.
- Secret read chỉ xuất hiện trong **consumer CI** cần tải artifact.
- Pull request từ nguồn không đáng tin cậy **không được nhận secret publish**; việc chạy workflow trên branch lạ phải được kiểm soát.
- Mask giá trị secret trong logs; tránh bật trace/debug quá mức hoặc in toàn bộ process environment.
- Không lưu `settings.xml` chứa credentials vào CI artifacts/cache và không in `help:effective-settings` nguyên văn khi chưa xác minh dữ liệu nhạy cảm được che.
- Gắn quyền với **tài khoản máy/service principal**, có audit và rotation; revoke ngay nếu token bị lộ.
- Tách quyền read của public dependency mirror và quyền read/write của private release repository nếu chính sách yêu cầu.

### 7.1. Ví dụ quy trình tạo settings trong CI

CI có thể tạo một file settings tạm trong workspace được bảo vệ, với credentials tham chiếu từ biến môi trường:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>releases</id>
            <username>${env.MAVEN_PUBLISH_USER}</username>
            <password>${env.MAVEN_PUBLISH_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

Sau đó truyền file này cho Maven khi chạy job phát hành. **Không nên reuse file chứa quyền write trong job consumer chỉ-read**. Nếu runner tạo file có nội dung secret đã được render thay vì biểu thức môi trường, cần đặt permissions chỉ owner đọc, tránh in file và xóa khi kết thúc job theo cơ chế runner.

**Secrets đã mask không đồng nghĩa không thể lộ.** Token có thể đi vào URL, HTTP proxy logs, heap dump, crash report hoặc output của một công cụ build. Chọn cách truyền bí mật ít xuất hiện trong command line và kiểm plugin logging theo môi trường.

## 8. HTTP proxy: đường mạng CI có thể khác laptop

Trong doanh nghiệp, CI runner có thể phải đi qua proxy mới truy cập Maven Central, Gradle Plugin Portal hoặc kho nội bộ. Đôi khi kho nội bộ lại phải **đi thẳng**, không qua proxy. Vì vậy cần biết:

1. Địa chỉ host/port của proxy và giao thức mà proxy chấp nhận.
2. Danh sách host được **bypass proxy**.
3. Proxy có yêu cầu **username/password** không.
4. HTTPS traffic được **CONNECT tunnel** hay bị TLS inspection.
5. Runner container/VM có DNS và route tới **repository host** không.

**Không nhầm proxy với repository.** Proxy là nơi chuyển tiếp request mạng; Maven repository là nơi lưu artifact. Một request tới `repo.example.org` có thể đi qua proxy, nhưng tọa độ Maven/artifact không đổi.

### 8.1. Khai báo proxy trong Maven settings

Ví dụ `settings.xml`:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <proxies>
        <proxy>
            <id>corporate-proxy</id>
            <active>true</active>
            <protocol>http</protocol>
            <host>proxy.example.internal</host>
            <port>3128</port>
            <nonProxyHosts>
                localhost|127.0.0.1|*.corp.internal|repo.example.org
            </nonProxyHosts>
        </proxy>
    </proxies>
</settings>
~~~

Các hostname trên chỉ là **mẫu**. `nonProxyHosts` dùng dấu `|` để ngăn cách trong cú pháp Maven/Java thường gặp; nó **không giống** cú pháp `NO_PROXY` dùng dấu phẩy trong nhiều HTTP clients. Nếu repository nội bộ phải đi thẳng, đưa nó vào danh sách bypass; nếu kho thực sự chỉ có thể truy cập qua proxy, đừng bypass một cách máy móc.

Ví dụ proxy cần xác thực có thể dùng `<username>`/`<password>` bên trong `<proxy>`, lấy từ secrets của CI theo cơ chế settings interpolation hoặc file runtime bảo vệ. **Không đặt mật khẩu proxy thật** trong tệp commit.

**`<protocol>http</protocol>` mô tả proxy**, không có nghĩa URL repository phải là HTTP; một HTTPS repository thường có thể dùng HTTP proxy thông qua CONNECT nếu hạ tầng hỗ trợ. Không suy rằng mọi HTTPS/mTLS repo đều hoạt động với mọi proxy: phải kiểm yêu cầu SSL và cấu hình doanh nghiệp.

### 8.2. Cẩn thận với HTTP_PROXY, HTTPS_PROXY và NO_PROXY

Một số tool dùng các biến:

~~~text
HTTP_PROXY=http://proxy.example.internal:3128
HTTPS_PROXY=http://proxy.example.internal:3128
NO_PROXY=localhost,127.0.0.1,.corp.internal
~~~

Nhưng **Java/Maven, Gradle, curl, Git và Stub Runner có thể đọc các biến/cấu hình khác nhau**. Việc `curl` tải được JAR **không chứng minh** Maven hoặc Stub Runner đã dùng cùng proxy. Khi debug, cần kiểm **process thực sự phát request** và cơ chế proxy nó hỗ trợ.

Trong CI dùng container, còn phải kiểm biến môi trường đã **được truyền vào container chạy Maven/test**, không chỉ tồn tại ở host runner.

## 9. Gradle: dependency repository, publication và credentials

Với producer/consumer dùng **Gradle**, khái niệm vẫn là **tách read và write credentials**, nhưng cú pháp khác Maven. Ví dụ Groovy DSL:

~~~groovy
repositories {
    mavenCentral()
    maven {
        name = 'contractReleases'
        url = uri('https://repo.example.org/repository/releases')
        credentials {
            username = providers.environmentVariable(
                'MAVEN_READ_USER'
            ).orNull
            password = providers.environmentVariable(
                'MAVEN_READ_TOKEN'
            ).orNull
        }
    }
}
~~~

Đây là **cấu hình để resolve dependencies** trong Gradle build. Với Gradle version phù hợp, `providers.environmentVariable(...)` đọc biến môi trường mà CI inject; không cần viết token vào source. Trong dự án có repository group/mirror nội bộ, có thể thay `mavenCentral()` bằng kho được phép.

Producer Gradle cần publication riêng để publish artifact JAR `stubs` (được Contract Gradle Plugin tạo), và một repository publish với credential **write**:

~~~groovy
publishing {
    repositories {
        maven {
            name = 'companyReleases'
            url = uri(
                'https://repo.example.org/repository/releases'
            )
            credentials {
                username = providers.environmentVariable(
                    'MAVEN_PUBLISH_USER'
                ).orNull
                password = providers.environmentVariable(
                    'MAVEN_PUBLISH_TOKEN'
                ).orNull
            }
        }
    }
}
~~~

**Khối `publishing.repositories` chỉ khai báo đích phát hành**, không tự đính kèm JAR `stubs`. Cần `maven-publish`, Maven publication chứa artifact classifier `stubs` và task đóng gói stub đúng plugin version. Khi publish, kiểm cả **tọa độ và nội dung** của JAR, không chỉ status code upload thành công.

### 9.1. Proxy cho Gradle dùng JVM/network settings

Gradle chạy trên JVM nên trong nhiều trường hợp dùng các system properties như:

~~~properties
systemProp.http.proxyHost=proxy.example.internal
systemProp.http.proxyPort=3128
systemProp.https.proxyHost=proxy.example.internal
systemProp.https.proxyPort=3128
systemProp.http.nonProxyHosts=localhost|127.0.0.1|*.corp.internal
~~~

Đây là **ví dụ cấu hình**, không chứa password và không nhất thiết hoạt động cho mọi HTTP client/plugin do Gradle gọi. Không ghi proxy credentials thật vào `gradle.properties` trong source control. Hãy xác định file `gradle.properties` nào được runner dùng, xem cấu hình Gradle daemon và loại trừ proxy cho kho nội bộ đúng chính sách.

**Một lưu ý nữa:** Maven `settings.xml` không tự điều khiển tất cả Gradle dependency resolution; nếu producer dùng Gradle nhưng consumer dùng Maven, **mỗi build tool cần cấu hình repository và credentials riêng**.

## 10. HTTPS/TLS: xử lý lỗi certificate đúng cách

Repository riêng cần **HTTPS hợp lệ**. Các lỗi thường gặp:

~~~text
PKIX path building failed
unable to find valid certification path
SSLHandshakeException
hostname verification failed
~~~

Một số nguyên nhân:

| Nguyên nhân | Biểu hiện | Hướng xử lý đúng |
| --- | --- | --- |
| Repository dùng CA nội bộ | JVM không tin cậy certificate chain. | Cài **CA được tổ chức duyệt** vào truststore của JDK/JVM chạy build. |
| Proxy TLS inspection ký lại certificate | Browser/curl hoạt động nhưng JVM không tin CA proxy. | Xác minh với nhóm security và trust đúng corporate CA. |
| Hostname không khớp certificate | `hostname verification failed`. | Sửa DNS/repository URL hoặc certificate SAN; không tắt verification. |
| Certificate hết hạn | Handshake thất bại sau ngày hết hạn. | Gia hạn certificate trên repository/proxy, kiểm đồng hồ runner. |
| JDK cũ thiếu trust roots/thuật toán phù hợp | Laptop pass, runner cũ fail. | Nâng JDK/truststore theo chính sách, pin toolchain CI. |
| Proxy/SSL MITM ngoài dự kiến | Chain khác môi trường đã duyệt. | Điều tra mạng với đội bảo mật; không chấp nhận bừa certificate mới. |

**Không sửa bằng cách tắt SSL verification** hoặc đặt các cờ `insecure/allowall` trong Maven/Gradle để qua CI. Việc đó có thể cho phép kẻ tấn công thay thế JAR stub/dependency hoặc chặn credentials.

### 10.1. Truststore là của process JVM nào?

Trong một pipeline có Maven, Gradle, Java test process và Stub Runner, có thể có **nhiều JVM**:

- Maven launcher dùng JDK A.
- Gradle daemon dùng JDK B.
- Test fork/Surefire chạy JDK C.
- Một ứng dụng Stub Runner độc lập chạy JDK D.

Nếu chỉ cập nhật truststore của laptop hoặc một JDK không được runner dùng, lỗi SSL vẫn xảy ra. Hãy kiểm **`java -version`, `mvn -version`, Gradle Java home/toolchain và process test**, rồi cài trust CA được duyệt vào đúng môi trường cần thiết.

### 10.2. Với mTLS hoặc kho không dùng Basic auth

Một số repository yêu cầu **client certificate**, IAM/OIDC hoặc một gateway phát hành token ngắn hạn. Khi đó, cấu hình username/password trong Maven settings có thể **không đủ**. Cần:

1. Xác nhận phương thức auth do repository/gateway hỗ trợ.
2. Cấu hình client certificate/truststore/identity bằng cơ chế của Maven, Gradle, Stub Runner hoặc proxy resolver được hỗ trợ.
3. Đảm bảo secret key/certificate chỉ có trong job được phép, không ghi vào artifact hoặc source control.
4. Kiểm expiration/rotation và xử lý failed authentication một cách an toàn.

Đừng tuyên bố “kho chỉ cần `<server><password>`” khi hệ thống thực tế dùng cơ chế khác.

## 11. Phân biệt lỗi 401, 403, 404, 407, 429 và SSL

Khi consumer CI không tải được stubs, HTTP status giúp khoanh vùng nhưng **không thể dùng một status để kết luận mọi nguyên nhân**. Một số repository cố tình trả 404 thay cho 403 để không làm lộ artifact riêng tư.

| Lỗi | Ý nghĩa thường gặp | Kiểm điều gì trước? |
| --- | --- | --- |
| **401 Unauthorized** | Thiếu hoặc sai credentials, token hết hạn. | Có credential không? Repo ID/server ID đúng? Token còn hiệu lực? |
| **403 Forbidden** | Đã xác thực nhưng không đủ quyền hoặc policy chặn. | Role, namespace, repository, branch/environment policy, allowlist IP. |
| **404 Not Found** | Artifact/URL không tồn tại, classifier/version sai, hoặc repo ẩn tài nguyên. | Tọa độ Maven, repository layout, metadata, quyền read. |
| **407 Proxy Authentication Required** | Proxy yêu cầu xác thực riêng. | Proxy username/password và client có thực sự đi qua proxy. |
| **429 Too Many Requests** | Rate limit của repository/gateway. | Quota, retry có backoff và concurrency/caching đúng policy. |
| **5xx** | Repository/proxy/gateway không ổn định. | Trạng thái hạ tầng, deadline, số lần retry, sự cố dịch vụ. |
| **PKIX/SSLHandshakeException** | Chain certificate, hostname, TLS hoặc truststore sai. | JDK/truststore, certificate hợp lệ, proxy TLS inspection. |
| **Connection refused / timeout** | Sai host/port, DNS, routing, firewall hoặc proxy. | URL thực, DNS, network namespace của CI, khả năng truy cập TCP. |

**Đừng mặc định** lỗi 401 là “artifact không tồn tại” hoặc lỗi 404 là “thiếu mật khẩu”. Để debug hiệu quả, cần ghi nhận **URL host không chứa credentials**, mã lỗi, Maven coordinates, repository ID và bước pipeline đang lỗi.

### 11.1. Cách chẩn đoán theo thứ tự

1. Đối chiếu **group/artifact/version/classifier/extension** với producer publication.
2. Xác nhận **repository URL** trỏ đúng Maven endpoint, không phải UI login hoặc trang quản trị.
3. Kiểm CI job **đang có identity phù hợp** và secret chưa hết hạn; không in secret.
4. Xác nhận **server ID/repository ID** khớp trong Maven, hoặc config credentials được Gradle/Stub Runner thực sự sử dụng.
5. Kiểm **proxy và non-proxy hosts** của process đang phát request.
6. Kiểm **TLS chain/truststore** của đúng JDK/process.
7. Xem log repository/gateway có kiểm soát nếu nhóm sở hữu kho; đối chiếu request ID và policy.
8. Từ một runner sạch, thử tải **đúng phiên bản stub** bằng công cụ trong CI, rồi thực thi Stub Runner consumer test.

**Không khắc phục bằng cách đưa token thật vào exception message hoặc tăng logging vô hạn.** Nếu phải chia sẻ log để điều tra, redaction mọi Authorization header, cookie, query credentials và repository user info.

## 12. Tách lỗi download artifact và lỗi HTTP stub matching

Sau khi giải quyết xác thực, test vẫn có thể fail ở một tầng khác:

| Tình huống | Dấu hiệu | Phương án điều tra |
| --- | --- | --- |
| **Không tải được JAR** | Stub Runner báo không resolve artifact, HTTP 401/403/404 từ kho. | Repository/credential/proxy/TLS/Maven coordinates. |
| **JAR tải được nhưng không có HTTP mapping** | WireMock khởi động nhưng không phục vụ endpoint. | Đọc nội dung `stubs.jar`, kiểm Contract Verifier output, artifact đúng version. |
| **WireMock không khởi động** | Không có URL ở `StubFinder`, lỗi bind port/config. | Stub Runner startup, classpath, port, mapping parser. |
| **WireMock chạy nhưng request không khớp** | Consumer nhận 404 no-match. | So method/path/query/header/body với mapping và journal. |
| **WireMock trả 404 nghiệp vụ** | Mapping lỗi 404 được khớp, có error body/code. | Assert error payload và hành vi consumer. |
| **Mã client sai base URL** | Kết nối đến Maven repo hoặc server khác. | Tra `StubFinder.findStubUrl(...)` và truyền URL đó vào client thật. |
| **Consumer không parse được response** | Jackson/schema error. | Kiểm contract body, DTO, header Content-Type và version. |

Đặc biệt, **HTTP 404 của WireMock** không liên quan trực tiếp đến **HTTP 404 khi tải JAR từ Maven repository**. Hai request gửi tới **hai host/port và hai dịch vụ** khác nhau. Dùng đúng log và đúng công cụ cho từng tầng.

## 13. Kho nội bộ, snapshots, releases và metadata

Nhiều tổ chức tách repository:

~~~text
https://repo.example.org/repository/snapshots
https://repo.example.org/repository/releases
https://repo.example.org/repository/maven-group
~~~

| Loại kho | Dùng để | Lưu ý |
| --- | --- | --- |
| **Snapshots** | Artifacts phát triển chưa ổn định. | Một version snapshot có thể thay đổi; cần chính sách update/metadata/cache rõ. |
| **Releases** | Bản phát hành được chấp thuận. | Ưu tiên bất biến, pin version và hạn chế quyền ghi đè. |
| **Group/proxy** | Resolve từ nhiều upstream repos. | Có thể read-only; không tự dùng làm đích publish. |
| **Staging** | Chờ QA/approval trước khi chuyển release. | Consumer không nên coi staging artifact là release nếu chưa được duyệt. |

Ví dụ consumer đang kiểm `1.0.0` nhưng producer publish `1.0.1`. CI không nên tự động nhận bản mới chỉ vì dùng một version động như `+`/`LATEST`. Hãy **chọn version cụ thể theo ma trận tương thích** và có cơ chế nâng cấp có review.

Với `-SNAPSHOT`, Maven metadata có thể dẫn tới timestamped artifacts. Nếu repository/mirror/cache dùng metadata cũ, consumer có thể tải một bản snapshot khác kỳ vọng. Khi phân tích, hãy so **version, checksum, timestamp và metadata** ở kho và local cache, không chỉ so tên `...-SNAPSHOT`.

### 13.1. Caching giúp tốc độ nhưng có thể che lỗi xác thực

CI cache thường lưu thư viện và stubs đã tải:

- Cache giúp tránh tải lại dependencies, giảm thời gian và phụ thuộc mạng.
- Cache có thể **che lỗi repository** nếu artifact đã có sẵn.
- Cache không được chứa `settings.xml` có credentials, private keys hoặc token.
- Cache key cần phù hợp OS/JDK/build tool/policy để tránh lấy artifacts sai hoặc không còn tin cậy.
- Nên có một bài kiểm **cold-cache remote download** trong pipeline phù hợp để bảo vệ auth/repository.
- Nếu gặp `Could not find artifact` sau lần tải thất bại, Maven có thể ghi nhớ kết quả resolve theo chính sách update; kiểm `-U`/cập nhật metadata đúng cách, không xóa toàn bộ cache bừa bãi nếu nguyên nhân thực là sai tọa độ.

**Đừng coi cache-hit là bằng chứng** identity của CI còn quyền đọc remote repository. Nếu cần kiểm xác thực, hãy thật sự yêu cầu repository xử lý một lượt tải trong môi trường cô lập.

## 14. Phòng tránh rò rỉ dữ liệu qua artifact và logs

Hợp đồng và stubs có thể được chia sẻ cho nhiều consumer hơn source producer. Không nên cho rằng artifact chỉ có “dữ liệu test” nên không cần kiểm:

| Rủi ro | Ví dụ sai | Cách phòng tránh |
| --- | --- | --- |
| Token trong WireMock mapping | Header Authorization chứa bearer token thật. | Dùng token giả/placeholder không có hiệu lực và kiểm contract không chứa secret. |
| Private data trong response mẫu | Email, số tài khoản hoặc dữ liệu cá nhân thật. | Dùng synthetic fixtures, kiểm quyền xem artifact. |
| Credential trong repository URL | `https://user:token@repo...` | Cấu hình secrets riêng, không chèn vào URL. |
| Secret lộ trong build logs | `echo $TOKEN`, command trace, exception debug. | Không in env/secrets; bật masking, redaction và giới hạn debug. |
| Upload artifact sai namespace | Producer có quyền ghi toàn bộ kho. | Least privilege theo repository/namespace/service. |
| Ghi đè release cũ | Publish cùng group/artifact/version với nội dung khác. | Immutable release, review và kiểm metadata/checksum. |
| Artifact giả mạo | Tải từ endpoint HTTP không được xác thực hoặc mirror không tin cậy. | HTTPS/TLS, repository allowlist, checksum/signature/policy phù hợp. |

Trong CI, kiểm artifact được phát hành từ **commit và pipeline đã qua producer verification**. Tùy tổ chức có thể bổ sung SBOM, checksum/signature, provenance hoặc policy kiểm dependency; những công cụ này tăng bảo vệ nguồn gốc nhưng **không thay thế kiểm đúng hợp đồng**.

## 15. CI producer: từ verification đến phát hành có quyền

Một luồng producer đáng tin:

~~~mermaid
flowchart TD
    A["Producer PR/commit"] --> B["CI chỉ-read: resolve dependencies"]
    B --> C["Contract Verifier generate producer tests"]
    C --> D["Chạy tests + kiểm reports"]
    D --> E{"Verification đạt?"}
    E -->|Không| F["Fail; không cấp quyền publish"]
    E -->|Có| G["Đóng gói classifier stubs"]
    G --> H["Kiểm JAR, version, metadata và secret scan"]
    H --> I["Job publish được cấp credential write"]
    I --> J["Upload tới releases/snapshots phù hợp"]
    J --> K["Kiểm artifact có thể resolve và audit"]
~~~

Các bước được khuyến nghị:

1. **Resolve plugin/dependencies** qua repository/mirror được phép; CI có quyền read tối thiểu.
2. **Chạy generated producer tests** từ Groovy/YAML contracts, xác minh test count > 0 và không bị skip.
3. **Chạy các integration/security tests cần thiết**, đặc biệt nếu contract phụ thuộc DB, auth hoặc messaging.
4. **Đóng gói JAR stubs** sau verification; kiểm classifier `stubs` và nội dung mappings/contracts.
5. **Chặn publish nếu verification fail**; không cấp secret write cho job chưa được phê duyệt.
6. **Publish artifact versioned** lên đúng snapshot hoặc release repository với account có quyền ghi giới hạn.
7. **Kiểm artifact metadata/provenance** và đảm bảo các consumer có quyền read cần thiết.

Không có lý do để đưa credential publish vào bước consumer test. Ngược lại, consumer không nên có khả năng thay đổi stubs mà nó đang kiểm.

### 15.1. Pseudocode pipeline CI có kiểm soát

~~~yaml
# Pseudocode: chuyển thành cú pháp GitHub Actions/GitLab CI/Jenkins thật.
jobs:
  verify-producer:
    permissions: read-only
    steps:
      - checkout-source
      - configure-java-and-maven-settings-readonly
      - run: ./mvnw clean verify
      - inspect: generated-tests-and-surefire-reports
      - archive: verified-stubs-artifact

  publish-stubs:
    needs: verify-producer
    if: verification-and-release-policy-pass
    secrets:
      - MAVEN_PUBLISH_USER
      - MAVEN_PUBLISH_TOKEN
    steps:
      - download: verified-stubs-artifact
      - check: version-checksum-and-publish-target
      - publish: exact-verified-artifact
~~~

**Đây là pseudocode, không phải YAML hợp lệ cho một hệ thống CI cụ thể.** Nó thể hiện đúng ý tưởng: **quyền read trong job verify**, chỉ inject **write secret** trong job publish sau khi qua cổng kiểm. Nếu job publish rebuild bằng Maven, phải kiểm rằng build đó không làm thay đổi artifact chưa được xác minh; cách sạch hơn là publish **chính artifact đã được tạo trong job verify** qua cơ chế repository được dự án chấp thuận.

## 16. CI consumer: tải cold-cache và chạy Stub Runner

Consumer có thể cấu hình Stub Runner:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/repository/releases"
)
class BillingConsumerContractTest {
    @Autowired
    private StubFinder stubFinder;

    @Test
    void readsOrderFromPublishedStub() {
        URL url = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service")
        );
        OrderClient client = new OrderClient(url.toExternalForm());
        assertThat(client.getOrder(42L).status()).isEqualTo("PAID");
    }
}
~~~

Đây là **đoạn test minh họa**, giả định imports, `OrderClient` và các dependencies đã có. Với kho riêng, cần thêm **credential read** theo cơ chế được Stub Runner của phiên bản dự án hỗ trợ. Trước khi chạy, CI phải có đường mạng tới repository, proxy/TLS đúng và artifact được publish.

Một quy trình test consumer nên có:

1. Được cấp **credential read** từ CI secret store, không có credential write.
2. Xác nhận repository URL và proxy/TLS kết nối được từ đúng runner/container.
3. Tải **artifact stubs cụ thể** bằng Stub Runner `REMOTE`.
4. Khởi động WireMock từ mappings trong artifact hoặc messaging adapter tùy hợp đồng.
5. Tra HTTP base URL động bằng `StubFinder` nếu dùng HTTP.
6. Gọi **mã client thật** và assert response/status/header/body, không chỉ xác nhận stub tải thành công.
7. Khi cần, kiểm **request journal** để phát hiện client gửi sai path/header hay gọi nhiều lần.
8. Ghi lại **artifact version** trong test report để tái lập, không ghi credentials.

Nếu CI chạy nhiều consumer jobs song song, dùng cổng động và tách Stub Runner context để không tranh `8089`. Một lỗi `Address already in use` **không phải lỗi Maven credentials**.

## 17. Cách kiểm thủ công từ một CI runner mà không lộ secret

Khi có lỗi tải artifact, một chuỗi kiểm hợp lý:

~~~text
1. Xác định host repository và Maven coordinates.
2. Kiểm DNS/routing từ container hoặc runner thực.
3. Kiểm proxy được process Maven/Stub Runner sử dụng.
4. Kiểm TLS certificate chain với truststore/JDK đúng.
5. Kiểm read identity có quyền tại repository/namespace.
6. Thử resolve artifact trong môi trường sạch.
7. Kiểm JAR được trả là đúng classifier stubs và version.
8. Chạy consumer contract test, không dừng ở download success.
~~~

Maven có thể được dùng để kiểm resolution của một artifact cụ thể, ví dụ trên runner đã có credentials an toàn trong `settings.xml`:

~~~shell
./mvnw -s "$MAVEN_SETTINGS_FILE" \
  org.apache.maven.plugins:maven-dependency-plugin:get \
  -Dartifact=com.acme:order-service:1.0.0:jar:stubs \
  -DremoteRepositories=contract-releases::default::https://repo.example.org/repository/releases
~~~

Lệnh này dùng một goal của **Maven Dependency Plugin** để chẩn đoán Maven artifact resolution; **không tự bảo đảm Stub Runner sử dụng chính cấu hình resolver đó**. Khi đưa vào CI, cần kiểm cú pháp/phiên bản plugin, quyền và policy của kho, tránh in credentials hoặc chạy tùy tiện trên môi trường production.

Nếu `mvn dependency:get` thành công mà Stub Runner vẫn tải thất bại, hãy kiểm **khác biệt resolver/settings/proxy/credentials/classpath** trong test process. Ngược lại, nếu Maven CLI không thể resolve artifact do 401/403, cần xử lý xác thực trước khi điều tra WireMock mappings.

**Lưu ý về cú pháp:** tọa độ của Maven Dependency Plugin có thể được biểu diễn `groupId:artifactId:version:type:classifier`; Stub Runner dùng cú pháp `groupId:artifactId:version:classifier[:port]` trong nhiều cấu hình. **Hai chuỗi không phải lúc nào cũng hoán đổi trực tiếp**.

## 18. Các trường hợp đặc biệt: Git contract source, private proxy và cloud CI

### 18.1. Contract nằm trong Git riêng

Một nhóm có thể dùng **consumer-driven contracts** trong SCM repository riêng. CI producer cần tải source contract ở một phiên bản/tag/commit xác định, trong khi Stub Runner consumer vẫn tải **stub artifact** từ Maven repository.

Quy tắc:

- **Git token** chỉ cần quyền đọc SCM trong pipeline tiêu thụ contract; quyền sửa hợp đồng đi qua PR/review.
- **Maven read/write tokens** phục vụ kho artifact riêng; không đưa Git token vào Maven repository URL.
- Pin **Git commit/tag** hoặc version contract source để build tái lập.
- Kiểm contract source và stub artifact tương ứng **cùng phiên bản logic**; không lấy contract từ branch chưa duyệt rồi publish stubs như release ổn định.

Nếu không biết workflow dự án dùng Git hay artifact external contracts, đừng cấu hình “một repository URL” cho mọi thành phần.

### 18.2. Container và proxy nội bộ

CI runner có thể ở Kubernetes với `service DNS`; Maven process và Stub Runner test process có thể chạy trong hai container khác nhau:

| Vấn đề | Biểu hiện | Phòng tránh |
| --- | --- | --- |
| DNS nội bộ không phân giải | `UnknownHostException`. | Kiểm DNS từ container thực, không chỉ từ host. |
| `localhost` hiểu sai | HTTP client gọi chính container consumer thay vì stub khác. | Dùng URL StubFinder hoặc service DNS/port mapping đúng. |
| Proxy dùng sai cho internal repo | Request bị proxy chặn, 407 hoặc timeout. | Cấu hình bypass cho host đúng, phân biệt JVM `nonProxyHosts` và `NO_PROXY`. |
| TLS CA chỉ có ở host | Java trong container báo PKIX. | Provision CA được duyệt vào JDK/truststore container. |
| Secret chỉ cấp cho job khác | Consumer 401 dù producer publish OK. | Tách đúng secret scopes và truyền vào step/process cần. |
| Port WireMock cố định | Parallel tests tranh cổng. | Stub Runner port động, isolation theo test process. |

### 18.3. Repository cho phép read anonymous nhưng publish cần auth

Một số kho nội bộ cho phép consumer **read không cần credentials** trong một mạng tin cậy nhưng upload vẫn yêu cầu auth. Đó là **chính sách của kho**, không phải behavior của Spring Cloud Contract. Khi chọn cách này, vẫn phải giới hạn network access, TLS, khả năng audit và rủi ro lộ artifact.

Không tự thêm credential giả để “chữa” một kho không yêu cầu Basic auth; nó có thể gây 401 hoặc lộ metadata không cần thiết. Luôn kiểm chính sách truy cập thực tế.

## 19. Bảng điều tra nhanh cho developer và CI

| Triệu chứng | Nơi có lỗi nhiều khả năng | Việc nên làm |
| --- | --- | --- |
| Producer `mvn deploy` nhận 401 | Credential publish hoặc server ID. | Kiểm `distributionManagement.id`, `settings.xml`, token expiry và auth method. |
| Producer upload bị 403 | Thiếu quyền write/deploy, namespace/release policy. | Kiểm role/repository policy; không tăng quyền toàn hệ thống. |
| Consumer Stub Runner REMOTE nhận 401 | Credential read không được resolver dùng. | Kiểm cách Stub Runner phiên bản hiện tại lấy credentials; test cold cache. |
| Consumer REMOTE nhận 404 | Sai tọa độ/classifier/version, URL hoặc kho che quyền. | So artifact Maven layout/metadata; xác nhận read ACL. |
| Maven/Gradle báo 407 | Proxy auth lỗi. | Kiểm proxy username/password và client proxy config. |
| Maven CLI tải được, Stub Runner không tải được | Khác resolver, settings, cache, proxy hoặc TLS process. | So cấu hình thực của test JVM và Maven CLI. |
| `PKIX path building failed` | JVM chưa tin corporate CA/chain. | Kiểm JDK/truststore và TLS proxy; không tắt SSL check. |
| `Connection timed out` | Routing/DNS/proxy/firewall hoặc repository quá tải. | Kiểm từ network namespace của CI và server health. |
| Chỉ CI fail, laptop pass | Secret scopes, proxy, CA, cache, JDK/Gradle/Maven version khác. | So environment có chọn lọc, không in secrets. |
| Stub JAR tải được nhưng consumer nhận 404 | WireMock mapping mismatch hoặc lỗi nghiệp vụ. | Kiểm request journal/mapping, không điều tra Maven auth tiếp. |
| Consumer test pass nhưng producer đã phá API | Producer verifier bị skip hoặc stub artifact cũ. | Kiểm producer test report, version/commit artifact. |
| Test pass khi cache ấm, fail khi cache lạnh | Quyền remote repo/mirror hoặc metadata chưa đúng. | Chạy cold-cache test có controlled credentials. |
| Publish thành công nhưng người khác không tải được | Khác repo/group quyền, staging chưa promote, wrong classifier. | Kiểm publication và consumer read path. |
| Không thấy artifact mới mặc dù version không đổi | Immutable release hoặc snapshot metadata/cache. | Dùng version mới; không ghi đè release để “ép” thay đổi. |

Phân loại trước khi sửa: **source retrieval**, **dependency resolution**, **stub artifact publishing**, **artifact download**, **HTTP stub runtime** hoặc **contract mismatch**. Mỗi loại có logs, quyền và phương án khắc phục riêng.

## 20. Thực hành: producer publish, consumer tải qua private repository

Chuẩn bị một môi trường thử nghiệm có **private Maven repository** dành cho học tập, không dùng tài khoản quản trị production:

1. **Định nghĩa HTTP contract** cho Order Service: `GET /api/orders/42` trả 200 JSON `{"id":42,"status":"PAID"}` bằng Groovy hoặc YAML DSL.
2. **Cấu hình Contract Verifier** ở producer; sinh generated tests và kiểm chúng thực thi thật, phát hiện được một thay đổi sai cố ý.
3. **Tạo/publish classifier JAR `stubs`**, dùng tọa độ `com.acme:order-service:1.0.0:stubs`. Kiểm nội dung artifact sau khi build.
4. **Tạo hai service identities** trong kho thử nghiệm: một có quyền publish ở namespace producer, một chỉ có quyền read.
5. **Ở Maven producer**, khai báo `distributionManagement` trỏ đến release repository; cung cấp credential publish qua `settings.xml` do CI secrets tạo, không commit token.
6. **Chạy producer verification trước** rồi mới cho job publish nhận credential write. Xác nhận artifact xuất hiện ở đúng Maven path.
7. **Ở Billing consumer**, cấu hình `@AutoConfigureStubRunner` với `REMOTE`, `repositoryRoot` và version đã publish; truyền credential read qua resolver được phiên bản Stub Runner hỗ trợ.
8. **Chạy từ CI runner/cache sạch**: xác nhận Stub Runner tải được artifact, khởi động WireMock, `StubFinder` trả URL và `OrderClient` đọc được `PAID`.
9. **Thử lỗi credential có kiểm soát**: dùng token read hết quyền hoặc tạm thời bỏ credential trong môi trường thử nghiệm; ghi nhận 401/403 và cách xác định nguyên nhân mà không in token.
10. **Thử lỗi tọa độ**: đổi classifier/version sang bản chưa tồn tại; giải thích vì sao 404 không nhất thiết là lỗi xác thực.
11. **Thử proxy**: cấu hình proxy test và danh sách bypass đúng cho repository nội bộ; xác minh Maven và test JVM đều đi qua đường mạng kỳ vọng.
12. **Thử truststore** trên môi trường có CA nội bộ được phép; xác nhận JDK của CI tin cậy certificate hợp lệ. Không tắt TLS verification.
13. **Thử cache**: so một lượt warm cache với cold cache để xác minh pipeline không phụ thuộc artifact còn sót.
14. **Đưa thành CI gate**: producer verification PASS → publish versioned stubs → consumer REMOTE test → ghi lại artifact version và kết quả tương thích.

**Tiêu chí hoàn thành:** cả producer và consumer hoạt động từ hai job/runner độc lập, quyền **write/read được tách**, credentials không xuất hiện trong source/log, Stub Runner **tải artifact thật từ kho riêng**, và bạn phân biệt được lỗi repository/proxy/TLS với lỗi WireMock request matching.

## 21. Câu hỏi tự kiểm tra

1. Kho Git chứa contract source, kho Maven chứa JAR `stubs` và HTTP WireMock server khác nhau thế nào?
2. Vì sao `repositoryRoot` của Stub Runner không phải base URL cho `OrderClient`?
3. `groupId:artifactId:version:stubs` biểu thị điều gì, và vì sao thiếu classifier có thể gây 404 artifact?
4. Producer CI cần loại quyền gì để publish, consumer CI cần quyền gì để tải?
5. Tại sao không dùng một admin token chung cho tất cả CI jobs?
6. Vai trò của `distributionManagement` khác `repositories` và `mirrors` như thế nào?
7. Vì sao `<id>` của Maven server credentials phải khớp repository ID mà Maven thực dùng?
8. `StubsMode.LOCAL` khác `REMOTE` về nguồn artifact thế nào? Cả hai có thể sử dụng WireMock HTTP local không?
9. Vì sao Maven CLI tải được artifact chưa chắc Stub Runner test JVM tải được?
10. Trong Maven proxy config, `nonProxyHosts` khác `NO_PROXY` ở cách khai báo như thế nào?
11. Khi gặp 407, cần kiểm credential của repository hay của proxy trước?
12. Khi gặp `PKIX path building failed`, vì sao tắt TLS verification là cách sửa nguy hiểm?
13. Vì sao một CI runner có cache ấm có thể che lỗi credential read đã hết hạn?
14. Khi một repository trả 404, có thể kết luận artifact chắc chắn không tồn tại không?
15. Vì sao release artifact bất biến giúp consumer contract tests có thể tái lập?
16. Khi consumer nhận WireMock 404 từ `GET /api/orders/43`, tại sao đó không tự động là lỗi Maven repository 404?
17. Trong CI, secrets publish nên được cấp lúc nào và cần thu hồi khi nào?
18. Vì sao hợp đồng và dữ liệu mẫu trong stub JAR cũng phải được kiểm rò rỉ thông tin?

## 22. Checklist áp dụng cho hệ thống thật

| Kiểm tra | Kỳ vọng |
| --- | --- |
| Quyền riêng cho producer/consumer | Publisher **write tối thiểu**, consumer **read tối thiểu**. |
| Repository URLs và identities | Đúng host, đúng Maven layout, đúng server IDs, đúng release/snapshot policy. |
| Truyền secrets | Chỉ qua secret manager/workload identity hoặc kênh an toàn tương đương; không commit. |
| Proxy/DNS/network | Cấu hình trên đúng CI process, bypass đúng internal hosts. |
| TLS | Certificate hợp lệ, CA tin cậy ở đúng JDK/truststore; không tắt SSL verify. |
| Maven/Gradle build | Đã resolve dependencies/plugins đúng qua mirror/repo. |
| Producer verification | Generated tests thực sự chạy, báo cáo đạt trước publish. |
| Artifact classifier/version | JAR `stubs` đúng tọa độ, không dùng artifact cũ từ cache. |
| Consumer Stub Runner | `REMOTE` tải thật khi cần, dùng URL stub động để gọi client. |
| CI reproducibility | Version pin, audit logs có redaction, cold-cache test có chủ đích. |
| Compatibility | Consumer thực thi client/listener theo contract; lỗi API được tách khỏi lỗi hạ tầng. |

**Ghi nhớ:** **Xác thực vào kho, cấu hình proxy và chứng thực TLS là những điều kiện vận hành để hợp đồng có thể được phân phối, không phải nội dung hợp đồng API**. Producer phải xác minh Groovy/YAML contracts bằng generated tests trước khi publish artifact classifier `stubs`; consumer cần quyền read phù hợp để Stub Runner tải **đúng version**, rồi gọi **URL HTTP stub đang chạy**, không gọi Maven repository. Tách quyền read/write, truyền secrets từ CI một cách an toàn, kiểm server IDs/proxy/truststore và chẩn đoán đúng tầng giúp pipeline phát hiện thay đổi API không tương thích mà không đánh đổi bảo mật hoặc khả năng tái lập.
