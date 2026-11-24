# Chế độ lấy stub từ CLASSPATH, LOCAL và REMOTE

## 1. Vì sao Stub Runner cần nhiều chế độ lấy stub?

Trong hệ thống microservices, **consumer** thường gọi HTTP API hoặc nhận thông điệp từ **producer**. Khi viết kiểm thử consumer, việc khởi động đầy đủ tất cả producer, database và hạ tầng liên quan có thể vừa chậm vừa khó tái lập. **Spring Cloud Contract Stub Runner** giải quyết một phần bài toán bằng cách chạy các stub được xây dựng từ hợp đồng, nhờ đó consumer có thể gửi request và nhận response theo giao diện mà producer đã công bố.

Giả sử có hai ứng dụng:

- **Inventory Service** (producer) cung cấp `GET /api/inventory/SKU-100` và trả trạng thái tồn kho.
- **Checkout Service** (consumer) cần gọi endpoint đó trước khi xác nhận một đơn hàng.

Ví dụ response mà consumer kỳ vọng:

~~~json
{
  "sku": "SKU-100",
  "available": true,
  "quantity": 8
}
~~~

Nhóm Inventory Service viết contract bằng Groovy/YAML DSL, sinh kiểm thử phía producer và tạo artifact chứa stub mappings. Nhóm Checkout Service dùng **Stub Runner** để khởi động một WireMock server nạp mappings đó. Khi client của Checkout gọi WireMock, nó nhận response theo contract mà không cần Inventory Service thật đang chạy.

Câu hỏi then chốt là: **Stub Runner lấy stub từ đâu?** Spring Cloud Contract cung cấp ba chế độ thuộc `StubRunnerProperties.StubsMode`:

- `CLASSPATH` — quét stubs trên **test runtime classpath**.
- `LOCAL` — tìm artifacts trong **kho cục bộ**, điển hình là Maven local repository `~/.m2/repository`.
- `REMOTE` — lấy artifacts từ **repository bên ngoài** như Nexus/Artifactory hoặc một location được hỗ trợ qua custom protocol.

Chọn đúng chế độ giúp bộ kiểm thử consumer không vô tình lấy nhầm phiên bản, không phụ thuộc vào máy người viết, và tái lập được trong CI.

Bài này thuộc chương **Stub Runner** của module `SPRING_CLOUD_CONTRACT`. Nội dung gắn với quy trình học kiểm thử hợp đồng producer–consumer bằng Groovy/YAML DSL, sinh producer tests, phát hành stub, sử dụng Stub Runner và phát hiện thay đổi API không tương thích.

### Mục tiêu

Sau khi học xong, bạn có thể:

1. Giải thích Stub Runner tải, tìm và chạy stub như thế nào.
2. Phân biệt `CLASSPATH`, `LOCAL` và `REMOTE` theo **nguồn artifact** và tình huống sử dụng.
3. Đọc chuỗi `groupId:artifactId:version:classifier:port`.
4. Chuẩn bị stub JAR để test theo từng chế độ.
5. Cấu hình `@AutoConfigureStubRunner`, `repositoryRoot` và `ids` một cách có chủ đích.
6. Kết nối consumer client với cổng WireMock do Stub Runner cung cấp.
7. Chẩn đoán lỗi không tìm thấy stub, sai classifier, sai phiên bản, không khớp request và lỗi repository.
8. Lập chiến lược LOCAL cho phát triển, REMOTE cho CI và CLASSPATH cho bộ kiểm thử tự chứa.

> **Ghi nhớ:** Ba mode khác nhau chủ yếu ở **cách tìm/lấy stubs**, không phải ở ý nghĩa của contract. Sau khi tìm thấy mappings, Stub Runner vẫn có thể tạo WireMock servers phục vụ consumer tests theo các quy tắc đã được đóng gói.

## 2. Stub Runner nằm ở đâu trong vòng đời contract?

~~~mermaid
flowchart TD
    DSL["Producer viết contract Groovy/YAML"] --> GEN["Sinh generated producer tests"]
    GEN --> VERIFY{"Producer verification đạt?"}
    VERIFY -- "Không" --> STOP["Chặn phát hành"]
    VERIFY -- "Có" --> PACK["Sinh và đóng gói stubs JAR"]
    PACK --> SRC{"Chọn nguồn stub"}
    SRC --> CP["CLASSPATH: test dependencies"]
    SRC --> LOC["LOCAL: Maven local repository"]
    SRC --> REM["REMOTE: Nexus / Artifactory / supported location"]
    CP --> RUN["Stub Runner nạp mappings"]
    LOC --> RUN
    REM --> RUN
    RUN --> WM["Khởi động WireMock HTTP stubs"]
    WM --> CT["Consumer integration tests"]
~~~

Dòng dữ liệu cần hiểu:

1. **Contract nguồn** mô tả request/response hoặc messages đã được các bên thống nhất.
2. **Contract Verifier** sinh test gửi request tới producer thật hoặc test context của producer rồi kiểm tra response.
3. Từ contract, build có thể sinh **WireMock stub mappings** và đóng gói chúng thành một **stub artifact**.
4. **Stub Runner** tìm artifact theo mode, giải nén/đăng ký mappings và chạy WireMock server cho từng dependency phù hợp.
5. **Consumer test** gọi server stub và xác minh hành vi client/consumer.
6. CI nên chỉ phát hành stub tương ứng với producer đã đạt kiểm chứng theo chính sách dự án.

**Stub JAR không phải ứng dụng producer đang chạy.** WireMock mô phỏng các tương tác đã được mô tả; nó không tự thực thi service code, repository, transaction hay middleware của producer. Vì vậy consumer tests với stub và generated producer tests bổ sung nhau, không thay thế nhau.

### 2.1. Stub Runner không phải chỉ dành cho HTTP

Với HTTP, Stub Runner chạy WireMock mappings. Với messaging, Spring Cloud Contract có các cơ chế để trigger/send messages qua integration phù hợp. Tuy nhiên **chọn nguồn stub `CLASSPATH`, `LOCAL` hay `REMOTE` không tự cấu hình broker, message binder hoặc message verifier**. Những phần đó cần setup riêng khi test giao tiếp message.

## 3. So sánh nhanh ba chế độ

| Thuộc tính | CLASSPATH | LOCAL | REMOTE |
| --- | --- | --- | --- |
| Nguồn stub | Các JAR/mappings có trên runtime classpath | Local artifact repository, thường `.m2` | Artifact repository như Nexus/Artifactory, hoặc location được hỗ trợ |
| Giá trị enum | `StubsMode.CLASSPATH` | `StubsMode.LOCAL` | `StubsMode.REMOTE` |
| Mode mặc định | **Có** | Không | Không |
| Cần tải mạng lúc test? | Thường không, sau khi dependencies đã được resolve | Không nếu artifact đã được cài trong kho local | Thường có, nhưng có thể dùng cache |
| Cách đưa stub vào test | Khai báo stub JAR là test dependency | Producer chạy `install` / publish-to-local | Producer publish stub artifact lên kho chung |
| Điểm dễ nhầm | Có dependency không đồng nghĩa đúng mappings | Artifact chưa `install` hoặc version cũ | URL/quyền truy cập/cache/version |
| Dùng khi | Test tự chứa, fixture ổn định | Phát triển offline, thử thay đổi producer chưa publish | CI liên nhóm, consumer ở repo khác |
| Kiểm soát version | Theo test dependency | Theo artifact/version cài local | Theo artifact/version trong repository |
| Cần `repositoryRoot` | Không để quét classpath | Thông thường không, dùng local repository | Có khi lấy từ remote/custom location |

Sự khác biệt giữa `LOCAL` và `CLASSPATH` đặc biệt quan trọng:

- Một artifact **đã có trên test classpath** thì `CLASSPATH` có thể quét nó.
- Một artifact chỉ **nằm trong `~/.m2/repository`** nhưng **không được đưa vào classpath** không tự được `CLASSPATH` quét.
- `LOCAL` dùng cơ chế phân giải artifact từ local repository theo định danh Maven; không cần declare từng stub JAR làm test dependency theo cùng cách với `CLASSPATH`.

## 4. Đọc chính xác định danh stub: Ivy notation

Stub Runner nhận danh sách `ids` theo quy ước:

~~~text
groupId:artifactId:version:classifier:port
~~~

Ví dụ:

~~~text
com.example:inventory-producer:1.2.3:stubs:8095
~~~

| Phần | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| `groupId` | `com.example` | Nhóm Maven |
| `artifactId` | `inventory-producer` | Module producer đã publish artifact |
| `version` | `1.2.3` | Phiên bản stub artifact |
| `classifier` | `stubs` | Phân biệt stub JAR với main application JAR |
| `port` | `8095` | Cổng WireMock server Stub Runner cố dùng |

Theo tài liệu, `version`, `classifier` và `port` là **tùy chọn**; nếu thiếu version thì mặc định thường dùng `+` để chọn phiên bản mới nhất theo cơ chế resolver; nếu thiếu classifier thì mặc định `stubs`; nếu thiếu port thì Stub Runner chọn cổng trong dải cấu hình. Giá trị mặc định và cách resolver chọn “latest” cần được kiểm tra với phiên bản/nguồn artifact của dự án.

Ví dụ các cách viết:

~~~text
com.example:inventory-producer
com.example:inventory-producer:1.2.3
com.example:inventory-producer:1.2.3:stubs
com.example:inventory-producer:1.2.3:stubs:8095
com.example:inventory-producer:+:stubs:8095
~~~

**Khuyến nghị:** Với CI hoặc khi kiểm tra breaking change, dùng **version cụ thể** thay vì `+`. “Latest” có thể thay đổi giữa hai lần chạy, khiến cùng commit consumer sử dụng stub khác nhau và gây lỗi khó tái hiện.

### 4.1. Phân biệt port và artifact identity

`8095` là **WireMock server port**, không phải port thật của Inventory Service trên production và cũng không phải cổng Maven repository.

Với nhiều producer, mỗi stub server cần cổng riêng. Nếu không cần pin port, có thể để Stub Runner chọn cổng rồi lấy cổng runtime bằng `@StubRunnerPort` hoặc các thuộc tính running stubs; điều này tránh xung đột khi nhiều test suites chạy song song.

### 4.2. Classifier không phải một thư mục bất kỳ

Theo quy trình đóng gói phổ biến, producer có:

~~~text
inventory-producer-1.2.3.jar
inventory-producer-1.2.3-stubs.jar
~~~

Tệp thứ hai là **artifact có classifier `stubs`**, không phải một bản sao ứng dụng. Nếu producer dùng classifier khác như `contract-stubs`, consumer phải chỉ đúng classifier đó hoặc cấu hình mặc định phù hợp.

## 5. CLASSPATH: quét những stub đã nằm trên test classpath

`StubsMode.CLASSPATH` là **mặc định**. Stub Runner không cần phân giải một stub artifact mới từ remote trong lúc khởi tạo nếu các stub cần dùng đã được đưa vào classpath.

Ví dụ consumer khai báo dependency Maven lên stub JAR của producer:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>inventory-producer</artifactId>
    <version>1.2.3</version>
    <classifier>stubs</classifier>
    <type>jar</type>
    <scope>test</scope>
</dependency>
~~~

Sau khi Maven resolve dependency, JAR có thể xuất hiện trên **test runtime classpath**. Spring Cloud Contract quét các vị trí mappings/contracts theo convention trong artifact, chẳng hạn các đường dẫn `META-INF/.../mappings` và `META-INF/.../contracts` tương ứng với group/artifact. **Đưa đúng JAR vào classpath và đóng gói đúng layout** là điều kiện quan trọng. 

### 5.1. Cấu hình consumer test ở mode CLASSPATH

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubRunnerProperties;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs:8095",
    stubsMode = StubRunnerProperties.StubsMode.CLASSPATH
)
class CheckoutConsumerContractTest {

    @Test
    void consumerShouldHandleInventoryResponse() {
        // Gọi consumer client đã cấu hình trỏ tới stub ở localhost:8095.
        // Assertion phải kiểm tra hành vi của Checkout Service.
    }
}
~~~

Đây là **khung minh họa**: test runner và ứng dụng consumer cần dependency Stub Runner/JUnit/Spring Boot phù hợp. Phần thân test phải gọi client thực hoặc logic consumer; việc chỉ thấy annotation không có nghĩa đã kiểm chứng consumer.

Nếu bạn bỏ `stubsMode`, tài liệu hiện tại xác định mặc định là `CLASSPATH`. Tuy nhiên **chỉ dựa vào mặc định nên được ghi chú trong code review** để thành viên mới hiểu nguồn stubs đang dùng.

### 5.2. CLASSPATH phù hợp khi nào?

- Consumer có thể khai báo version stub JAR như một **test dependency**.
- Muốn test tương đối tự chứa, không cần truy cập repository tại runtime sau dependency resolution.
- Các module cùng một build hoặc CI có dependency graph rõ ràng.
- Muốn lock version stubs bằng quản lý dependency thay vì để Stub Runner tự chọn latest.
- Muốn giảm bất ổn do remote network khi chạy tests.

Nhược điểm cần lưu ý: đổi version stub có thể yêu cầu cập nhật build dependency; packaging sai khiến scanner không thấy mappings dù JAR đã tồn tại.

### 5.3. Tránh hai hiểu nhầm

**Hiểu nhầm 1:** Có file `some-stubs.jar` nằm trong thư mục download nhưng không khai báo vào test classpath thì CLASSPATH tự thấy.

Không. Nó phải nằm trên **classpath mà Stub Runner quét**, với layout/coordinates phù hợp.

**Hiểu nhầm 2:** CLASSPATH nghĩa là không bao giờ cần mạng.

Không chính xác. Maven/Gradle có thể cần mạng **để tải test dependency trước khi chạy test**. Sau khi classpath đã được dựng đủ, Stub Runner quét từ đó thay vì tự giải quyết bằng `REMOTE`.

## 6. LOCAL: lấy artifacts trong Maven local repository

`StubsMode.LOCAL` phù hợp cho phát triển giữa producer và consumer trên máy cá nhân hoặc môi trường offline có local repository được chuẩn bị.

Ví dụ producer đã sinh và đóng gói stub JAR với tọa độ:

~~~text
com.example:inventory-producer:1.2.3:stubs
~~~

Trên máy có Maven repository mặc định, artifact có thể nằm ở:

~~~text
~/.m2/repository/com/example/inventory-producer/1.2.3/
    inventory-producer-1.2.3.pom
    inventory-producer-1.2.3.jar
    inventory-producer-1.2.3-stubs.jar
~~~

Một cách chuẩn bị thường dùng cho producer đã cấu hình Spring Cloud Contract Maven plugin và attach stub artifact:

~~~bash
# Trong repository producer; ví dụ lệnh cho dự án Maven đã cấu hình
./mvnw clean install
~~~

Lệnh này **chỉ cài stub classifier** nếu dự án producer thật sự đã cấu hình sinh/đính kèm stub artifact vào lifecycle cài đặt. Nếu chưa có plugin hoặc task đóng gói, `install` một ứng dụng Java thông thường sẽ **không tự tạo** `-stubs.jar`.

### 6.1. Cấu hình Stub Runner LOCAL

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubRunnerProperties;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs:8095",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutLocalStubTest {

    @Test
    void shouldUseLocallyInstalledStub() {
        // Checkout client trỏ tới http://localhost:8095.
        // Kiểm tra nghiệp vụ dựa trên response stub.
    }
}
~~~

Không nhất thiết khai báo `repositoryRoot` khi dùng local repository Maven tiêu chuẩn. Nếu hệ thống dùng custom local Maven repository, hãy đối chiếu cơ chế repository resolution và cấu hình của phiên bản Stub Runner đang sử dụng.

### 6.2. LOCAL phù hợp khi nào?

- Đang phát triển song song hai repository producer/consumer.
- Producer chưa publish version thử nghiệm lên repository chung.
- Có thể xây stub mới, chạy `install` và lập tức thử consumer trên cùng máy.
- Muốn làm việc offline sau khi đã chuẩn bị đầy đủ dependencies/artifacts.

**Điểm yếu:** Máy A có stub `1.2.3` nhưng máy B chưa `install` hoặc đã cài một nội dung khác dưới cùng version; kết quả có thể khác nhau. Với CI, cần cài artifact một cách có kiểm soát trước khi chạy consumer tests, hoặc chuyển sang `REMOTE` với version bất biến.

### 6.3. Kiểm tra đúng version ở LOCAL

Giả sử contract mới đổi response từ:

~~~json
{"sku":"SKU-100","available":true,"quantity":8}
~~~

thành:

~~~json
{"sku":"SKU-100","available":true,"quantity":0}
~~~

Nếu consumer vẫn dùng artifact local cũ, test sẽ không phản ánh thay đổi mới. Cần bảo đảm producer build đã **sinh và cài lại stubs** đúng version, rồi khởi động lại test. Không xem kết quả xanh từ stale local artifacts là bằng chứng consumer tương thích với producer mới.


## 7. REMOTE: lấy stub từ repository dùng chung

`StubsMode.REMOTE` phù hợp khi producer và consumer nằm ở hai repository hoặc có pipeline riêng. Sau khi producer verification đạt, stub artifact được phát hành lên **Nexus**, **Artifactory** hoặc một repository tương thích. Consumer CI truy xuất artifact bằng tọa độ `groupId:artifactId:version:classifier`.

Ví dụ địa chỉ kho nội bộ:

~~~text
https://repo.example.test/repository/maven-releases/
~~~

Đây chỉ là **URL minh họa**, không phải một repository hoạt động thực tế.

### 7.1. Cấu hình bằng @AutoConfigureStubRunner

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubRunnerProperties;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs:8095",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot =
        "https://repo.example.test/repository/maven-releases/"
)
class CheckoutRemoteStubTest {

    @Test
    void shouldHandleInventoryResult() {
        // Gọi client Checkout trỏ tới stub: localhost:8095
        // rồi kiểm tra hành vi của consumer.
    }
}
~~~

Khi test khởi tạo, Stub Runner tìm artifact `inventory-producer-1.2.3-stubs.jar`, tải hoặc dùng cache phù hợp, giải nén và đăng ký mappings trên WireMock.

**Hai URL khác nhau:** `repositoryRoot` là **địa chỉ tải artifact**. Nó **không phải** URL HTTP của producer thật hoặc base URL mà consumer client gọi. Client gọi **WireMock server do Stub Runner khởi động**.

### 7.2. Cấu hình bằng Spring YAML

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        stubs-mode: REMOTE
        repository-root: https://repo.example.test/repository/maven-releases/
        ids:
          - "com.example:inventory-producer:1.2.3:stubs"
~~~

Port được bỏ trống, nên Stub Runner chọn cổng từ dải có thể sử dụng. Test nên lấy cổng runtime thay vì đoán là `8095`.

Nếu vừa khai báo annotation `@AutoConfigureStubRunner` vừa đặt configuration properties ở nhiều nơi, hãy kiểm tra giá trị có hiệu lực và precedence thật trước khi chẩn đoán.

### 7.3. Bảo vệ thông tin truy cập kho

Repository nội bộ thường có authentication. Spring Cloud Contract hỗ trợ username/password properties, nhưng **không commit credential vào Git**. Sử dụng CI secrets/environment variables hoặc cơ chế xác thực repository hỗ trợ, cấp quyền chỉ đọc nếu consumer chỉ cần download.

Ví dụ sơ đồ tên biến môi trường (không chứa secret):

~~~text
STUB_REPOSITORY_URL
STUB_REPOSITORY_USER
STUB_REPOSITORY_PASSWORD
~~~

Các giá trị đó có thể được ánh xạ vào `spring.cloud.contract.stubrunner.repositoryRoot`, `username` và `password` bằng cơ chế cấu hình Spring/CI. Không in token ra build logs.

### 7.4. REMOTE phù hợp khi nào?

- Producer và consumer thuộc các nhóm hoặc repository khác nhau.
- CI cần lấy đúng stub artifact đã publish.
- Artifact có quy trình version/release/promotion.
- Nhiều consumer cùng cần một nguồn stub chung.
- Muốn tránh phụ thuộc việc từng developer đã chạy `mvn install` hay chưa.

Nhược điểm: resolution có thể thất bại do mạng, DNS, authentication, repository outage, cache hoặc thiếu artifact/version. Đây là lỗi **tải artifact**, chưa phải contract mismatch.

## 8. REMOTE với stubs://file:// không phải LOCAL

Tên `REMOTE` dễ khiến người học nghĩ chế độ này **luôn** tải qua HTTPS. Spring Cloud Contract còn hỗ trợ downloader với `stubs://` để lấy stub hoặc contract definitions từ một location được hỗ trợ, bao gồm thư mục trên đĩa.

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot =
        "stubs://file://location/to/producer/target/stubs/"
)
~~~

Ví dụ mang ý nghĩa:

1. `stubsMode` vẫn là **REMOTE** theo cơ chế downloader.
2. `repositoryRoot` chỉ tới một thư mục nguồn có bố cục phù hợp.
3. Đây **không phải** mode LOCAL tìm Maven artifacts trong `~/.m2/repository`.
4. Không phải mọi thư mục chứa một vài file JSON đều có thể sử dụng ngay; phải đáp ứng convention/producer coordinates mà downloader hỗ trợ.

### 8.1. Trường hợp monorepo

~~~text
monorepo/
├── inventory-producer/
│   └── target/stubs/
└── checkout-consumer/
    └── src/test/
~~~

Pipeline có thể build producer tạo `target/stubs` trước, rồi consumer trỏ vào thư mục này bằng `stubs://file://...`. Đường dẫn và định dạng URI phải được điều chỉnh theo môi trường, hệ điều hành và phiên bản Stub Runner.

**Lưu ý:** Thư mục sinh stubs chưa tự chứng minh producer verification đã đạt. Với pipeline release, nên chỉ sử dụng hoặc publish những artifacts đã vượt qua các bước xác minh cần thiết.

## 9. Một contract, ba nơi lấy stub

Ví dụ contract Inventory Service:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_inventory_available')

    request {
        method GET()
        urlPath('/api/inventory/SKU-100')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-100',
            available: true,
            quantity: 8
        )
    }
}
~~~

Cùng một artifact `com.example:inventory-producer:1.2.3:stubs`:

- **CLASSPATH:** Test dependency JAR nằm trên runtime classpath và được scanner đọc.
- **LOCAL:** JAR được cài trong Maven local repository và được resolver đọc.
- **REMOTE:** JAR được publish lên repository chung rồi được tải về/cache.

Đổi mode **không làm đổi ý nghĩa contract**. Nếu response thay đổi giữa các môi trường dù tọa độ/version giống nhau, hãy kiểm tra checksum/nội dung artifact, cache hoặc chính sách ghi đè releases.

~~~mermaid
flowchart LR
    CP["Test classpath"] --> SR["Stub Runner"]
    LO["Maven local repository"] --> SR
    RE["Remote repository"] --> SR
    SR --> W["WireMock HTTP stubs"]
    C["Checkout consumer client"] --> W
    T["Consumer assertions"] --> C
~~~


## 10. Lấy cổng WireMock đúng cách

Nếu `ids` chứa port `8095`, WireMock sẽ cố chạy trên port đó. Trong CI nhiều test chạy song song, **cổng cố định có thể xung đột**. Bỏ phần port trong ID để Stub Runner chọn cổng khả dụng từ dải cấu hình, rồi nhận port bằng `@StubRunnerPort`, `StubFinder` hoặc running-stubs properties.

### 10.1. Dùng @StubRunnerPort

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubRunnerProperties;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryStubPortTest {

    @StubRunnerPort("com.example:inventory-producer")
    int stubPort;

    @Test
    void shouldGetStubResponse() {
        RestClient restClient =
            RestClient.create("http://localhost:" + stubPort);

        String json = restClient.get()
            .uri("/api/inventory/SKU-100")
            .retrieve()
            .body(String.class);

        assertThat(json).contains("SKU-100");
    }
}
~~~

Ví dụ dùng `RestClient` của Spring Framework 6.1+; phiên bản cũ hơn có thể dùng RestTemplate, WebClient hoặc HTTP client tương thích. Đây chủ yếu là **smoke test của stub**. Consumer test có giá trị hơn phải **gọi InventoryClient thật của Checkout** với base URL đến stub, rồi assert logic của Checkout.

### 10.2. Dùng StubFinder

~~~java
@Autowired
StubFinder stubFinder;

@Test
void shouldFindInventory() {
    java.net.URL url =
        stubFinder.findStubUrl("com.example", "inventory-producer");

    assertThat(url).isNotNull();
}
~~~

`StubFinder` được cung cấp trong Spring integration hoặc JUnit Extension/Rule theo cách sử dụng tương ứng. Đoạn trên cần import và context phù hợp để chạy trong dự án thật.

### 10.3. Running-stubs properties

Spring integration có thể cung cấp:

~~~text
spring.cloud.contract.stubrunner.runningstubs.inventory-producer.port
spring.cloud.contract.stubrunner.runningstubs.com.example.inventory-producer.port
~~~

Khi ứng dụng consumer lấy base URL từ configuration, có thể nối property port này thay vì hard-code `8095`. Nếu dùng artifact IDs chứa ký tự đặc biệt, kiểm tra tên property thực tế trong `Environment`.

### 10.4. Kiểm tra client thật thay vì chỉ ping stub

Giả sử Checkout dùng client:

~~~java
public final class InventoryClient {
    private final RestClient restClient;

    public InventoryClient(String baseUrl) {
        this.restClient = RestClient.create(baseUrl);
    }

    public InventoryStock findStock(String sku) {
        return restClient.get()
            .uri("/api/inventory/{sku}", sku)
            .retrieve()
            .body(InventoryStock.class);
    }
}

public record InventoryStock(
    String sku,
    boolean available,
    int quantity
) {}
~~~

Đây là code minh họa cho Java record và Spring RestClient, cần package/import đúng. Trong test đã nhận `stubPort`:

~~~java
InventoryClient inventory =
    new InventoryClient("http://localhost:" + stubPort);

InventoryStock stock = inventory.findStock("SKU-100");

assertThat(stock.sku()).isEqualTo("SKU-100");
assertThat(stock.available()).isTrue();
assertThat(stock.quantity()).isEqualTo(8);
~~~

Một bước tiếp theo là gọi **Checkout use case** sử dụng InventoryClient thật để bảo vệ logic quyết định đặt hàng. Chỉ assert nội dung HTTP từ WireMock chưa chứng minh consumer đã sử dụng response đúng.

## 11. Các Spring properties thường dùng

| Property | Công dụng | Ví dụ |
| --- | --- | --- |
| `spring.cloud.contract.stubrunner.ids` | Danh sách artifacts | `com.example:inventory-producer:1.2.3:stubs` |
| `spring.cloud.contract.stubrunner.stubsMode` | Nguồn stub | `CLASSPATH`, `LOCAL`, `REMOTE` |
| `spring.cloud.contract.stubrunner.repositoryRoot` | Repository/location | URL Nexus/Artifactory |
| `spring.cloud.contract.stubrunner.classifier` | Classifier mặc định | `stubs` |
| `spring.cloud.contract.stubrunner.minPort` | Đầu dải WireMock port | `10000` (mặc định trong tài liệu) |
| `spring.cloud.contract.stubrunner.maxPort` | Cuối dải WireMock port | `15000` (mặc định trong tài liệu) |
| `spring.cloud.contract.stubrunner.username` | Username truy cập repository | CI secret |
| `spring.cloud.contract.stubrunner.password` | Password/token truy cập | CI secret |
| `spring.cloud.contract.stubrunner.stubsPerConsumer` | Chọn dedicated stubs theo consumer | `false` mặc định |
| `spring.cloud.contract.stubrunner.consumerName` | Tên consumer khi cần | Theo consumer ID |

Ví dụ `application-test.yml` cho LOCAL:

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        stubs-mode: LOCAL
        ids:
          - "com.example:inventory-producer:1.2.3:stubs"
        min-port: 12000
        max-port: 12999
~~~

Spring hỗ trợ property binding theo cách viết kebab-case trong YAML. Khi có nhiều nguồn cấu hình (annotation/profile/env), hãy kiểm tra giá trị có hiệu lực.

### 11.1. Có nên tắt failOnNoStubs?

Theo tài liệu, Stub Runner mặc định **thất bại khi không tìm thấy stub**. Có thể đặt `failOnNoStubs = false` trong `@AutoConfigureStubRunner` hoặc `withFailOnNoStubs(false)` với Rule/Extension.

Đối với consumer test **bắt buộc cần stub**, nên để kiểm tra này hoạt động; nếu tắt đi chỉ để CI xanh, có nguy cơ **0 stub nhưng test vẫn báo đạt**. Chỉ tắt khi có lý do kiến trúc rõ và có assertions khác chứng minh hành vi cần test.

### 11.2. Khi consumer phụ thuộc nhiều producers

~~~java
@AutoConfigureStubRunner(
    ids = {
        "com.example:inventory-producer:1.2.3:stubs",
        "com.example:pricing-producer:2.0.1:stubs"
    },
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot =
        "https://repo.example.test/repository/maven-releases/"
)
~~~

Stub Runner chạy WireMock riêng cho từng artifact; phải phân biệt port Inventory với Pricing. Nếu không đặt port, dùng `@StubRunnerPort` hoặc `StubFinder` cho đúng dependency.

## 12. JUnit 5 Extension: không bắt buộc có SpringBootTest

Spring Cloud Contract hỗ trợ `StubRunnerExtension` cho JUnit 5, bên cạnh `StubRunnerRule` cho JUnit 4. Có thể sử dụng khi không muốn tải toàn bộ Spring application context chỉ để lấy/chạy stub.

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.springframework.cloud.contract.stubrunner.StubRunnerProperties;
import org.springframework.cloud.contract.stubrunner.junit.StubRunnerExtension;

import static org.assertj.core.api.Assertions.assertThat;

class PlainJUnitStubTest {

    @RegisterExtension
    static StubRunnerExtension stubs = new StubRunnerExtension()
        .downloadStub("com.example:inventory-producer:1.2.3:stubs")
        .stubsMode(StubRunnerProperties.StubsMode.LOCAL);

    @Test
    void shouldFindRunningStub() {
        java.net.URL url =
            stubs.findStubUrl("com.example:inventory-producer");

        assertThat(url).isNotNull();
    }
}
~~~

Đây là ví dụ nhận diện Extension API; consumer test thật phải dùng URL đó để gọi logic consumer. Tên method và import phụ thuộc phiên bản Spring Cloud Contract/JUnit đang dùng.

Với REMOTE, Extension có thể thêm `repoRoot(...)` và `stubsMode(StubsMode.REMOTE)`. Chọn Spring annotation hoặc JUnit Extension là quyết định test infrastructure; không làm thay đổi ý nghĩa contract.

## 13. Chẩn đoán lỗi từ lúc tải đến lúc consumer xử lý

~~~mermaid
flowchart TD
    A["Consumer test khởi động"] --> B{"Tìm được stub?"}
    B -- "Không" --> R["Mode, coords, repository, classifier"]
    B -- "Có" --> C{"WireMock khởi động?"}
    C -- "Không" --> P["Port, mappings, dependency versions"]
    C -- "Có" --> D{"Request khớp mapping?"}
    D -- "Không" --> M["Method, path, headers, body"]
    D -- "Có" --> E{"Consumer xử lý đúng response?"}
    E -- "Không" --> F["Sửa consumer hoặc thương lượng contract"]
    E -- "Có" --> G["Consumer test đạt"]
~~~

**Lỗi tải artifact khác lỗi request không khớp WireMock**, và cả hai khác lỗi consumer code xử lý JSON sai.

### 13.1. Xem mappings WireMock đã nạp

~~~http
GET /__admin/mappings HTTP/1.1
Host: localhost:8095
~~~

Ngoài WireMock admin API, Stub Runner có `mappingsOutputFolder` để xuất các mappings vào thư mục debug theo cấu hình. Hãy kiểm tra **mapping thực được đăng ký**, không chỉ đọc contract nguồn.

Nếu WireMock trả `404`, khả năng thường gặp là client gọi sai port, method/path/header/body không khớp, hoặc artifact thiếu mapping. Một unmatched WireMock `404` **không tương đương** một error response nghiệp vụ `404` kèm JSON code `ORDER_NOT_FOUND`.

### 13.2. Có artifact nhưng không có mapping mong muốn

Kiểm tra:

1. `ids` có đúng `groupId:artifactId:version:classifier` không?
2. File JAR có đúng classifier, đúng nội dung mappings không?
3. Layout `META-INF/.../mappings` hoặc format tương ứng có đúng không?
4. Phiên bản đang dùng có stale cache hoặc stale LOCAL artifact không?
5. Producer đã chạy generator và attach/publish stub classifier chưa?
6. Một subset contract có được sinh do điều kiện/filter hay không?
7. Test có đang kiểm tra đúng producer artifact chứ không nhầm service khác không?

Với CLASSPATH, kiểm tra **runtime classpath**; với LOCAL, kiểm tra **Maven local repository**; với REMOTE, kiểm tra **repository endpoint, permission và artifact metadata**.


## 14. Bảng xử lý lỗi theo từng chế độ

| Triệu chứng | CLASSPATH | LOCAL | REMOTE |
| --- | --- | --- | --- |
| `Stub not found` | Thiếu test dependency hoặc JAR sai layout | Chưa install đúng version/classifier | Repository không có artifact hoặc không truy cập được |
| Version khác mong muốn | Dependency version bị quản lý/override | Local JAR cũ hoặc snapshot chưa cài lại | `+` chọn bản khác, metadata/cache cũ |
| `401/403` khi tải | Có thể do build dependency resolver | Hiếm ở bước lấy local artifact | Credentials/repository permissions |
| Timeout khi khởi tạo | Build dependency resolution trước test | I/O local bất thường | Network/proxy/TLS/repository |
| WireMock port conflict | Cổng cố định bị chiếm | Tương tự | Tương tự |
| WireMock chạy nhưng `404` | Request/mapping không khớp | Tương tự | Tương tự |
| Mapping bị thiếu | Artifact đóng gói sai | Stub JAR local thiếu mapping | Artifact publish thiếu hoặc sai version |
| Build local xanh, CI đỏ | CI classpath khác local | CI chưa install artifact | CI thiếu secret/không truy cập repository |

### 14.1. Thứ tự gỡ lỗi hữu ích

Bắt đầu từ **nguồn** rồi đi tới **ứng dụng**:

1. Đọc `stubsMode` hiệu lực: đang dùng `CLASSPATH`, `LOCAL` hay `REMOTE`?
2. Đọc đầy đủ `ids`, xác định groupId, artifactId, version, classifier và port.
3. Chứng minh **artifact thực sự tồn tại** ở nguồn tương ứng.
4. Chứng minh stub JAR chứa **mapping mong đợi**.
5. Chứng minh WireMock đã chạy trên cổng test định dùng.
6. Đối chiếu request của consumer với method/path/headers/body của mapping.
7. Đối chiếu response thực với schema mà consumer đã thống nhất.
8. Mới xác định sửa **consumer**, **producer**, **contract** hoặc **CI configuration**.

Ví dụ một `401` từ repository trong quá trình download khác với một HTTP `401` do WireMock trả theo **contract authentication**. Đừng xử lý chúng như cùng một loại lỗi.

### 14.2. Không tắt lỗi chỉ để làm CI xanh

Một số cách “chữa nhanh” nguy hiểm:

- Bật `failOnNoStubs=false` khi test bắt buộc cần stub.
- Đổi `REMOTE` thành `LOCAL` khi CI chưa cài artifact.
- Để version `+` với ý nghĩ sẽ tự sửa lỗi không tìm thấy bản đã publish.
- Xóa request matchers khiến mọi request đều trả cùng response.
- Chép stub JSON thủ công vào consumer mà quên cập nhật từ producer.
- Bỏ kiểm tra JSON body, chỉ assert HTTP `200`.

Mỗi cách đều có thể làm mất ý nghĩa kiểm thử hợp đồng và để lọt breaking change.

## 15. Versioning và cache: yếu tố quyết định tính tái lập

Stub Runner không thể bảo vệ đúng sự tương thích nếu cùng một consumer commit chạy với những stub **khác nhau một cách khó kiểm soát**.

### 15.1. Pin version thay vì luôn dùng dấu +

Ví dụ:

~~~text
Nên dùng trong CI:
  com.example:inventory-producer:1.2.3:stubs

Thận trọng:
  com.example:inventory-producer:+:stubs
~~~

`+` hữu ích khi thử “phiên bản mới nhất” theo ý đồ rõ ràng, nhưng không phù hợp làm baseline CI nếu cần tái lập tuyệt đối. Khi một artifact mới được publish, cùng một source commit có thể bắt đầu dùng stub mới và thất bại mà không có thay đổi code consumer.

### 15.2. Snapshot và release có đặc tính khác nhau

- **Snapshot:** Có thể được publish lại theo version, thích hợp cho phát triển nhưng dễ thay đổi nội dung/cached metadata.
- **Release bất biến:** Nên được coi là artifact không bị overwrite, giúp kiểm soát và truy vết.
- **CLASSPATH:** Version có thể được khóa qua dependency management.
- **LOCAL:** Hai máy có thể cài khác nội dung dưới cùng tọa độ nếu quy trình không chặt.
- **REMOTE:** Cần chính sách giữ artifact, authentication, cache và promotion rõ ràng.

### 15.3. Ba cách hạn chế lệch môi trường

1. Ghi rõ stub coordinates/version mà consumer CI dùng.
2. Không publish release khác nội dung dưới cùng version; lưu metadata/checksum khi cần.
3. Chạy consumer contract tests với artifacts đã được producer verification chấp nhận, và kiểm tra đúng version của artifact ở bước release.

**Một bài test xanh trên stub cũ không chứng minh consumer tương thích với thay đổi producer mới.** Khi producer đổi contract, cần cập nhật/publish artifact và kiểm thử với bản phù hợp theo release policy.

## 16. Thực hành: chuyển một consumer test qua ba chế độ

### 16.1. Tình huống và dữ liệu đầu vào

Producer `Inventory Service` cung cấp:

~~~http
GET /api/inventory/SKU-100 HTTP/1.1
Accept: application/json
~~~

Response contract:

~~~json
{
  "sku": "SKU-100",
  "available": true,
  "quantity": 8
}
~~~

Giả sử producer đã có Groovy/YAML contract đúng và đã cấu hình Spring Cloud Contract Verifier để sinh test và attach `stubs` classifier khi build. Consumer `Checkout Service` phải đọc `available` và `quantity` để quyết định cho phép tạo đơn.

**Nhiệm vụ chung:** Với mỗi mode, khởi động Stub Runner, gọi InventoryClient thật của Checkout, kiểm tra response đúng kiểu và việc Checkout không nhận đơn khi số lượng yêu cầu vượt quá `quantity`.

### 16.2. Bài A — CLASSPATH

1. Đảm bảo artifact `inventory-producer-1.2.3-stubs.jar` có thể được Maven/Gradle resolve.
2. Khai báo stub JAR là **test dependency** như ví dụ ở Mục 5.
3. Cấu hình:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs",
    stubsMode = StubRunnerProperties.StubsMode.CLASSPATH
)
~~~

4. Dùng `@StubRunnerPort` hoặc `StubFinder` lấy WireMock URL.
5. Chạy consumer test qua đúng InventoryClient; kiểm tra các field và logic Checkout.
6. Thử bỏ stub dependency khỏi test runtime classpath để quan sát khác biệt giữa **không có JAR** và **request không match mapping**.

**Câu hỏi:** Vì sao chỉ đặt stub JAR trong `~/.m2/repository` nhưng không thêm nó vào test classpath có thể khiến CLASSPATH không tìm thấy mappings?

### 16.3. Bài B — LOCAL

1. Trong producer, xây generated tests và stub JAR theo plugin/lifecycle đã cấu hình.
2. Chạy bước cài vào Maven local repository:

~~~bash
# Chạy trong producer project, chỉ minh họa khi đã cấu hình plugin
./mvnw -B clean install
~~~

3. Xác nhận local repository có `inventory-producer-1.2.3-stubs.jar`.
4. Trong Checkout, bỏ yêu cầu dùng stub JAR như test dependency nếu chỉ còn LOCAL.
5. Đặt:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

6. Chạy consumer test, ghi kết quả.
7. Thay đổi contract response ở producer, sinh và cài lại artifact, rồi thử consumer với version mới tương ứng.

**Câu hỏi:** Vì sao `LOCAL` có thể xanh trên máy developer nhưng fail trên CI runner sạch? Cần chuẩn bị artifact nào trước khi chạy consumer?

### 16.4. Bài C — REMOTE

1. Producer chạy verification thành công và publish stub classifier tới repository dùng chung (ví dụ Nexus/Artifactory).
2. Consumer cấu hình:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.3:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot =
        "https://repo.example.test/repository/maven-releases/"
)
~~~

3. Cung cấp credentials theo CI secrets nếu repository cần xác thực.
4. Lấy port động, gọi InventoryClient và khẳng định Checkout xử lý đúng response.
5. Thử một version không tồn tại để quan sát lỗi **resolution**.
6. Thử giữ artifact nhưng đổi request path ở consumer để quan sát lỗi **WireMock unmatched request**.

**Câu hỏi:** Vì sao REMOTE phù hợp hơn LOCAL cho consumer CI ở repository khác, và vì sao cần pin version thay vì dùng `+`?

### 16.5. Bảng đánh giá ba bài thực hành

| Nội dung | CLASSPATH | LOCAL | REMOTE |
| --- | --- | --- | --- |
| Đã chứng minh stub ở đâu? | Test dependency/classpath | Maven local repository | Artifact repository chia sẻ |
| Có phụ thuộc producer chạy lúc consumer test không? | Không | Không | Không |
| Có cần publish trước khi test? | Cần có artifact để resolve dependency | Chỉ cần install local | Cần publish lên repository |
| Có thể offline tại runtime? | Có, nếu dependencies đã có | Có, nếu artifact local đầy đủ | Không nên phụ thuộc vào offline nếu chưa có cache |
| Điểm quan trọng cần ghi vào báo cáo | Dependency/version | Installed artifact/version | Repository/version/credentials |

### 16.6. Thử thêm một nhánh lỗi 404

Giả sử contract còn có `GET /api/inventory/SKU-404` trả:

~~~json
{
  "code": "INVENTORY_NOT_FOUND"
}
~~~

với HTTP `404` và `Content-Type: application/json`. Viết consumer test để Checkout hiển thị hoặc ghi nhận trạng thái “không có SKU” đúng quy định. **Đừng coi 404 do request không khớp bất kỳ stub nào là response nghiệp vụ**, vì nó có thể không mang `code: INVENTORY_NOT_FOUND`.

## 17. Chọn mode theo bối cảnh

| Bối cảnh | Mode thường phù hợp | Lý do |
| --- | --- | --- |
| Tất cả stubs là test dependencies đã được pin version | **CLASSPATH** | Scanner đọc classpath đã chuẩn bị |
| Hai repository cùng phát triển trên một máy, cần thử nhanh | **LOCAL** | Build/install producer rồi resolve local |
| Consumer CI tách producer CI, dùng registry chung | **REMOTE** | Versioned artifacts được chia sẻ |
| Monorepo có thư mục output stubs trực tiếp | **REMOTE + stubs://file://** | Downloader lấy từ location không phải .m2 |
| Test chạy tại môi trường hạn chế mạng | **CLASSPATH** hoặc **LOCAL** | Chuẩn bị dependencies/artifacts trước |
| Cần thử với release stub đã được duyệt | **REMOTE** với version cố định | Truy vết artifact và release promotion |

Đây là gợi ý lựa chọn, **không phải luật bắt buộc**. Một CI vẫn có thể dùng CLASSPATH nếu dependencies được quản lý cẩn thận; LOCAL cũng có thể chạy trong một pipeline nhiều module nếu có bước cài artifact xác định. Trọng tâm là **nguồn stubs rõ ràng, phiên bản có thể tái lập và tests thực sự dùng chúng**.

## 18. Checklist trước khi coi Stub Runner đã chạy đúng

- [ ] Có ít nhất một contract producer đúng giao diện consumer sử dụng.
- [ ] Producer verification đã được sinh và chạy, không chỉ tạo mappings.
- [ ] Stub artifact chứa classifier/layout và version dự kiến.
- [ ] `ids` ghi đúng `groupId:artifactId:version:classifier[:port]`.
- [ ] `stubsMode` được chọn có chủ đích: CLASSPATH, LOCAL hoặc REMOTE.
- [ ] CLASSPATH: Stub JAR có trên test runtime classpath.
- [ ] LOCAL: Artifact đã được cài và có trong Maven local repository.
- [ ] REMOTE: Repository URL, credentials và artifact version được xác minh.
- [ ] Với `stubs://file://`, dùng mode/location và layout phù hợp; không nhầm với Maven LOCAL.
- [ ] Có thể xác định WireMock port bằng `@StubRunnerPort`, `StubFinder` hoặc properties.
- [ ] Client của consumer thực sự gọi WireMock thay vì producer thật.
- [ ] Consumer tests gọi code consumer và kiểm tra hành vi, không chỉ ping stub.
- [ ] Request method, URL, headers, query và body khớp mapping.
- [ ] Test kiểm tra status và response JSON của những nhánh lỗi quan trọng.
- [ ] Không tắt `failOnNoStubs` vô cớ khi test bắt buộc có stub.
- [ ] CI dùng stub version có thể truy vết, tránh phụ thuộc `+` nếu cần tái lập.
- [ ] Port và test data không gây xung đột khi chạy song song.
- [ ] Không đưa token repository vào code hoặc build logs.
- [ ] Có phân biệt lỗi artifact resolution, WireMock matching và lỗi ứng dụng consumer.
- [ ] Stub được phát hành theo pipeline chỉ sau producer verification cần thiết.

## 19. Tài liệu tham khảo

- [Spring Cloud Contract — Stub Runner Core](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html): ba mode `CLASSPATH`, `LOCAL`, `REMOTE`, classpath scanning, tạo WireMock.
- [Spring Cloud Contract — Common Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-common.html): `ids`, `classifier`, `minPort`, `maxPort`, `repositoryRoot` và version defaults.
- [Spring Cloud Contract — Stub Runner JUnit Rule and JUnit 5 Extension](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-junit.html): `StubRunnerExtension`, `StubFinder`, `@StubRunnerPort` và running stubs.
- [Spring Cloud Contract — Fetching Stubs from a Location](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-stubs-protocol.html): sử dụng `stubs://file://` với mode REMOTE.
- [Spring Cloud Contract — Fail on No Stubs](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-fail-on-no-stubs.html): hành vi khi không tìm thấy stub.
- [Spring Cloud Contract — Developing Your First Application](https://docs.spring.io/spring-cloud-contract/reference/getting-started/first-application.html): vòng đời producer verification, publish stub và consumer tests.

**Ghi nhớ:** **CLASSPATH** quét stubs đã có trên classpath; **LOCAL** tìm stub artifacts trong Maven local repository; **REMOTE** lấy từ kho chung hoặc một supported location như `stubs://file://`. Ba chế độ chỉ thay đổi **nguồn phân giải stub**, không thay đổi contract mà consumer cần tuân thủ. Hãy pin version khi cần tái lập, lấy đúng WireMock port, thực sự gọi consumer code và chạy producer verification trước khi publish stub trong CI.
