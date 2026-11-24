# Quy trình package, install và deploy

## Mục tiêu bài học

Trong **Spring Cloud Contract**, producer định nghĩa hành vi HTTP hoặc thông điệp bằng **Groovy DSL** hay **YAML DSL**. **Contract Verifier** dùng các hợp đồng này để sinh kiểm thử phía producer; những hợp đồng HTTP còn có thể được chuyển thành stub mappings và đóng gói vào một **stub JAR** để consumer sử dụng qua **Stub Runner**. Để quy trình đó trở thành bằng chứng tương thích đáng tin cậy trong CI, không chỉ cần viết contract đúng: phải hiểu **Maven thực thi những pha nào, tạo ra artifact nào và công bố artifact ở đâu**.

Bài **“Quy trình package, install và deploy”** thuộc chương **Tích hợp Maven** tập trung vào vòng đời build từ hợp đồng trong repository producer đến bộ stub mà consumer thật sự tải. Phần quan trọng nhất là phân biệt:

- `package`: **tạo artifact trong thư mục build**, chưa đồng nghĩa đã chia sẻ cho dự án khác.
- `install`: **cài artifact vào Maven local repository**, phục vụ những build trên máy hoặc môi trường đó.
- `deploy`: **đẩy artifact lên remote Maven repository** cho các ứng dụng/CI khác tải.
- `verify`: chạy các kiểm tra được gắn vào lifecycle để xác minh chất lượng build; **không phải một loại repository publication**.

Sau bài học, bạn có thể đọc đường đi `contract → generated producer test → mappings → -stubs.jar → repository → consumer Stub Runner`, chọn lệnh Maven đúng mục tiêu, phát hiện artifact bị thiếu classifier hoặc consumer đang dùng version cũ và thiết kế release gate có thể tái lập.

## 1. Một dòng lệnh Maven thực hiện những pha nào?

Maven có **default lifecycle** gồm nhiều pha được chạy theo thứ tự. Khi yêu cầu một pha, Maven thường chạy **các pha đứng trước nó trong cùng lifecycle**, với các plugin goals đã được bind tương ứng.

~~~mermaid
flowchart LR
    A["validate"] --> B["compile"]
    B --> C["test"]
    C --> D["package"]
    D --> E["verify"]
    E --> F["install"]
    F --> G["deploy"]
~~~

Sơ đồ chỉ hiển thị một số pha quan trọng; thực tế còn có `generate-test-sources`, `process-test-resources`, `test-compile`, `integration-test` và nhiều pha khác.

| Lệnh | Mục tiêu | Những điều **không** nên suy luận |
| --- | --- | --- |
| `./mvnw package` | Xây dựng artifact qua pha package | Chưa tự cài vào Maven local hoặc deploy remote |
| `./mvnw verify` | Chạy qua package và các checks được bind tới verify | Chưa install/deploy |
| `./mvnw install` | Chạy qua verify rồi cài artifacts vào Maven local | Chưa đẩy lên repository chung |
| `./mvnw deploy` | Chạy qua install rồi đẩy artifacts tới remote repository | Không có nghĩa mọi consumer đã test bản mới |
| `./mvnw clean verify` | Dọn kết quả build cũ, rồi chạy lifecycle tới verify | `clean` là lifecycle khác, không phải pha của default |
| `./mvnw clean deploy` | Dọn build, kiểm tra và publish qua remote | Chỉ nên làm trong môi trường có quyền publish và cổng chất lượng phù hợp |

**Không cần chạy lần lượt ba lệnh `package`, `install` và `deploy`** trên cùng một build: gọi `deploy` đã đưa Maven qua các pha trước đó. Có thể chạy `clean verify` trước để kiểm tra, nhưng phải hiểu rằng một lần `deploy` sau đó lại chạy lifecycle; nếu artifact bị thay đổi giữa hai lần, bản publish có thể không còn đúng bytes đã kiểm thử trước đó.

### Khác biệt giữa phase và goal

- **Phase** như `package` hoặc `deploy` là điểm trong lifecycle.
- **Goal** như `spring-cloud-contract:generateTests` hoặc `spring-cloud-contract:generateStubs` là thao tác của một Maven plugin.
- **Binding** quyết định goal nào chạy ở phase nào trong build.

Ví dụ, gọi một goal thủ công:

~~~bash
./mvnw org.springframework.cloud:spring-cloud-contract-maven-plugin:generateTests
~~~

khác với chạy toàn bộ lifecycle tới `test` hoặc `verify`. Lệnh trên nhằm **sinh test**, không tự bảo đảm generated tests đã được biên dịch, chạy PASS hoặc stub artifact được đóng gói.

## 2. Spring Cloud Contract tham gia Maven lifecycle ở đâu?

Trong các phiên bản Spring Cloud Contract Maven plugin được tài liệu hóa, những goal quan trọng gồm:

| Goal của plugin | Mục đích | Pha binding thường được tài liệu mô tả |
| --- | --- | --- |
| `generateTests` | Đọc Groovy/YAML contracts, sinh acceptance tests phía producer | `generate-test-sources` |
| `convert` | Chuyển hợp đồng thành mappings dùng cho HTTP stubs | `process-test-resources` |
| `generateStubs` | Đóng gói mappings đã chuyển đổi thành stub JAR | `package` |
| `run` | Chạy stub phục vụ kiểm thử trong trường hợp cấu hình thích hợp | Goal riêng, không đồng nghĩa với publish |

Danh sách này mô tả **các chức năng và binding được công bố trong tài liệu plugin**, không thay thế việc kiểm tra version và effective POM của dự án. Tùy cấu hình, các goals có thể được bind tự động khi dùng plugin extension hoặc phải cấu hình executions rõ ràng.

Điều cần hiểu về thứ tự:

~~~mermaid
flowchart TD
    A["src/test/resources/contracts<br/>Groovy / YAML DSL"] --> B["generateTests<br/>generate-test-sources"]
    A --> C["convert<br/>process-test-resources"]
    B --> D["test-compile"]
    D --> E["test / generated producer tests"]
    C --> F["target/stubs<br/>mappings"]
    E --> G{"Tests PASS?"}
    F --> H["generateStubs<br/>package"]
    G -->|Không| X["BUILD FAIL"]
    G -->|Có| H
    H --> I["Producer JAR + attached stubs JAR"]
    I --> J["verify"]
    J --> K["install: local repository"]
    K --> L["deploy: remote repository"]
~~~

**Lưu ý:** sơ đồ thể hiện logic triển khai mong muốn; Maven chính xác sẽ thực thi goal theo **phase binding và thứ tự plugin executions thực tế**. Có thể cấu hình plugin để chạy khác sơ đồ. Đọc Maven log và test reports để khẳng định những thao tác đã xảy ra.

### Generated tests không giống stubs

- Generated **producer tests** thực thi trên **mã producer**, phát hiện implementation không còn thỏa thuận.
- Stub **mappings** trả response mẫu khi consumer gọi, giúp chạy consumer tests không cần producer thật.
- Stub **JAR** là artifact đóng gói được phát hành; chưa chắc đã được tạo chỉ vì một file JSON mapping xuất hiện dưới `target/stubs`.
- Stub Runner giúp tải/chạy stub; nó **không** thay thế producer contract tests.

Producer tests PASS và stub JAR có sẵn là **hai điều kiện khác nhau** cần kiểm tra.

## 3. Cấu hình Maven plugin minh họa

Một cấu hình tham khảo trong `pom.xml` của producer Order Service:

~~~xml
<properties>
    <!-- Thay bằng version tương thích Spring Boot/Spring Cloud của dự án -->
    <spring-cloud-contract.version>VERSION_PHU_HOP</spring-cloud-contract.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>${spring-cloud-contract.version}</version>
            <extensions>true</extensions>
            <configuration>
                <contractsDirectory>
                    ${project.basedir}/src/test/resources/contracts
                </contractsDirectory>
                <baseClassForTests>
                    com.example.orders.contract.OrderContractBase
                </baseClassForTests>
                <failOnNoContracts>true</failOnNoContracts>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`VERSION_PHU_HOP` là **placeholder**, không phải version thực có thể dán nguyên xi vào POM. Ví dụ cố ý lược bỏ dependency management, các test dependencies, packaging và những cấu hình ứng dụng khác.

Trong dự án thật có thể cần dependency test như:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
</dependency>
~~~

Phiên bản dependency nên được quản lý bởi BOM tương thích. Các dự án dùng WebFlux, MockMvc, JUnit hoặc messaging test có thể cần cấu hình `testMode`, base test class và libraries khác nhau. **Không nên sao chép một POM mẫu rồi cho rằng generated tests sẽ chạy trên mọi kiểu producer**.

### Tại sao base test class quan trọng?

Generated test phải có cách gọi producer hoặc kích hoạt message. `OrderContractBase` có thể cấu hình Spring test context, HTTP client, fixture và phương thức kích hoạt event.

Nếu cấu hình base class sai package, test có thể không biên dịch; nếu generated test bị bỏ qua, build có thể trông thành công nhưng chưa xác minh hành vi producer.

### Nếu muốn cấu hình goal executions tường minh

Trong một số dự án, nhóm khai báo mục `executions` với `convert`, `generateStubs` và `generateTests`. Không nên **vừa chép executions vừa bật extension mà không kiểm tra effective build**, vì có nguy cơ goal được cấu hình trùng hoặc thực thi ở pha không mong muốn. Hãy chọn một chiến lược rõ ràng và xác nhận trong log.

## 4. Ví dụ hợp đồng nguồn tạo ra cả test và stub

Giả sử tệp `src/test/resources/contracts/orders/get_paid_order.yml`:

~~~yaml
description: "Lấy đơn hàng đã thanh toán"
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

Từ hợp đồng này:

1. `generateTests` có thể tạo một producer test gửi `GET /api/orders/ORD-1001` rồi kiểm tra response.
2. `convert` có thể tạo WireMock mapping để mô phỏng request và response.
3. `generateStubs` có thể đóng gói mapping đã chuyển đổi vào stub artifact.
4. `install` hoặc `deploy` có thể đưa stub artifact đã được **attach** vào Maven repository.
5. Consumer dùng Stub Runner lấy artifact theo tọa độ và kiểm thử ứng dụng.

Bản hợp đồng không quyết định **localhost**, cổng Stub Runner hoặc URL repository. Những thông tin đó nằm ở tầng build/runtime và consumer test configuration.

## 5. package: sản phẩm nằm ở đâu?

Chạy:

~~~bash
./mvnw clean package
~~~

Trong một dự án JAR được cấu hình đầy đủ, các bước có thể gồm:

- Dọn thư mục `target` cũ (nhờ `clean`).
- Xử lý sources/resources, biên dịch code.
- Đọc contracts, sinh generated tests và mappings ở các pha được bind.
- Biên dịch và chạy unit/contract tests phù hợp.
- Tạo artifact ứng dụng chính.
- Tạo/attach stub JAR với classifier `stubs` nếu plugin được cấu hình để làm vậy.

Ví dụ các đầu ra:

~~~text
order-service/
├── src/test/resources/contracts/orders/get_paid_order.yml
└── target/
    ├── generated-test-sources/contracts/    # generated producer tests
    ├── generated-test-resources/contracts/  # tài nguyên khi cần
    ├── stubs/                               # converted mappings
    ├── surefire-reports/                    # kết quả tests
    ├── order-service-1.4.2.jar              # artifact chính
    └── order-service-1.4.2-stubs.jar        # attached stubs artifact
~~~

Đây là **cấu trúc minh họa**. Tên/thư mục đầu ra có thể khác theo version Spring Cloud Contract, plugin configuration, `finalName`, Maven packaging và các plugins khác.

### Hai artifact không được nhầm

~~~text
Application / producer artifact:
com.example.orders:order-service:1.4.2

Stub artifact:
com.example.orders:order-service:1.4.2:stubs
~~~

| Thành phần | Vai trò |
| --- | --- |
| `groupId` | Namespace, ví dụ `com.example.orders` |
| `artifactId` | Tên publication, ví dụ `order-service` |
| `version` | Version của build/artifact, ví dụ `1.4.2` |
| `classifier` | Biến thể stub, thường là `stubs` |

Một artifact có tên `order-service-stubs` như **artifactId riêng** không tương đương với artifactId `order-service` cùng classifier `stubs`. Nếu nhóm cố ý dùng quy ước khác, phải khai báo và công bố tọa độ thực tế.

### Kiểm tra đầu ra sau package

Với shell hỗ trợ lệnh `jar`, có thể xem nội dung artifact đã sinh:

~~~bash
jar tf target/order-service-1.4.2-stubs.jar
~~~

Kết quả cần được đối chiếu với hợp đồng. Một bố cục trong JAR mà Stub Runner có thể sử dụng có các đường dẫn dưới `META-INF` cho contracts, mappings và response files:

~~~text
META-INF/
  com.example.orders/
    order-service/
      1.4.2/
        contracts/
          orders/get_paid_order.yml
        mappings/
          orders/get_paid_order.json
~~~

Đây là **ví dụ bố cục**, không phải bản chụp đầu ra của mọi version plugin. Quan trọng là artifact có mapping đúng request/response và phù hợp với cấu trúc mà Stub Runner của version đó tìm kiếm.

**Không coi việc tồn tại `-stubs.jar` là đủ**: phải kiểm tra ít nhất những mapping bắt buộc được đóng gói, không chỉ một JAR trống.

## 6. verify: một cổng chất lượng trước publication

Lệnh:

~~~bash
./mvnw clean verify
~~~

thực thi lifecycle tới `verify`, nghĩa là **đi qua cả `package`**. Trong một dự án tích hợp test plugins phù hợp, nó có thể chạy thêm các kiểm tra sau package như integration tests, coverage hoặc validation.

Nhưng cần tránh một hiểu lầm: Maven **không tự chạy tất cả integration tests trên thế giới** chỉ vì có pha `verify`. Các plugin liên quan, ví dụ Failsafe hoặc kiểm tra tùy chỉnh, phải được cấu hình/bind đúng.

Kiểm tra ở release gate nên bao gồm:

| Cổng kiểm tra | Câu hỏi cần xác nhận |
| --- | --- |
| Contracts discovery | Có đúng tập hợp Groovy/YAML contract được phát hiện không? |
| Generated test sources | Test mới đã được sinh và có mặt trong test compilation chưa? |
| Test execution | Generated producer tests thực sự chạy PASS hay bị skip? |
| Stub conversion | Đã có mapping đúng và không bỏ sót scenario nào? |
| Stub packaging | Artifact `-stubs.jar` đã attach và chứa dữ liệu đúng chưa? |
| Extra quality checks | Integration tests và checks cần thiết có thật sự chạy không? |

Một pipeline `mvn verify` xanh nhưng chỉ có **0 contract tests** không phải bằng chứng tương thích. Nên để CI fail khi thiếu những kịch bản bắt buộc.

## 7. install: đưa cả artifact chính và stub vào Maven local

Chạy:

~~~bash
./mvnw clean install
~~~

Khi build thành công, Maven chạy qua `verify`, rồi cài các artifacts được attach vào **local Maven repository**, thường tại `~/.m2/repository` (đường dẫn có thể tùy chỉnh trong settings).

Ví dụ:

~~~text
~/.m2/repository/com/example/orders/order-service/1.4.2/
├── order-service-1.4.2.pom
├── order-service-1.4.2.jar
└── order-service-1.4.2-stubs.jar
~~~

**Chỉ những artifact thực sự được attach/install** mới xuất hiện. Nếu Maven plugin không tạo hoặc attach stub JAR, `install` không thể tự phát minh ra classifier `stubs`.

### Khi nào local install hữu ích?

- Người phát triển producer và consumer trên cùng máy.
- Thử nghiệm Stub Runner trong `LOCAL` mode.
- Kiểm tra xem consumer phân giải được tọa độ stub trước khi publish remote.
- Một pipeline local/CI có workspace riêng, nơi producer build chạy trước consumer test trên **cùng Maven local repository**.

Nhưng một artifact cài trong `~/.m2` của người phát triển **không tự tồn tại** trong máy CI hoặc máy của đồng nghiệp.

### Ví dụ consumer Stub Runner LOCAL

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-service:1.4.2:stubs:8090",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutContractTest {

    @Test
    void checkoutHandlesPaidOrder() {
        // Đưa HTTP client của Checkout đến stub trên port 8090.
        // Gọi nghiệp vụ Checkout và assert kết quả consumer.
    }
}
~~~

Đây là khung minh họa. Test thật còn cần dependencies, client configuration và assertions. ID Stub Runner chứa cả **port 8090**, nhưng port **không thuộc tọa độ Maven artifact**.

### Lỗi local cache

Nếu producer sửa contract nhưng chưa chạy lại install, consumer dùng `LOCAL` vẫn có thể lấy JAR cũ. Do đó, việc consumer test PASS không chứng minh hợp đồng mới đúng nếu version/bytes chưa được cập nhật.

Trong CI, ưu tiên **local repository riêng cho build** hoặc cô lập cache để tránh chia sẻ artifact không còn đúng revision.

## 8. deploy: công bố artifacts lên repository chung

Chạy:

~~~bash
./mvnw clean deploy
~~~

sẽ thực thi các pha trước đó (trong đó có `package`, `verify` và `install`), rồi đưa các artifacts có thể deploy lên **remote Maven repository** theo cấu hình.

Một ví dụ `distributionManagement` trong POM:

~~~xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <url>https://repo.example.test/maven/releases</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <url>https://repo.example.test/maven/snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

Đây là **URL minh họa**, không phải repository thật. Maven lựa chọn repository phù hợp version release/SNAPSHOT theo cấu hình deploy.

Thông thường credential được quản lý trong **Maven settings** hoặc secret storage của CI, với `server.id` tương ứng `distributionManagement.repository.id` / `snapshotRepository.id`. **Không để username/password/token vào POM hoặc contract source**.

Ví dụ khung `settings.xml`, chỉ thể hiện ID liên kết:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>company-releases</id>
            <username>CI_USER_PLACEHOLDER</username>
            <password>CI_SECRET_PLACEHOLDER</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>CI_USER_PLACEHOLDER</username>
            <password>CI_SECRET_PLACEHOLDER</password>
        </server>
    </servers>
</settings>
~~~

Các placeholder không được commit như credential thật. CI nên cung cấp settings tạm qua cơ chế secret, giới hạn quyền publish và tránh log giá trị nhạy cảm.

### Sau deploy cần xác minh gì?

1. Remote repository thực sự có `order-service-1.4.2.jar` **và** `order-service-1.4.2-stubs.jar`.
2. POM/metadata được publish dưới đúng group/artifact/version.
3. JAR có nội dung contract/mappings của revision mong muốn.
4. Artifact có checksum hoặc bằng chứng bytes đã publish, không bị thay đổi sau đó.
5. Consumer có quyền đọc repository và không vô tình lấy JAR từ nguồn khác.

Một log `BUILD SUCCESS` của producer **không chứng minh consumer đã phân giải thành công từ remote repository**. Sau deploy có thể thực hiện một consumer smoke test độc lập.

## 9. Remote Stub Runner: consumer tải đúng bản đã deploy

Một cách cấu hình consumer test:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-service:1.4.2:stubs:8090",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.test/maven/releases"
)
class CheckoutRemoteStubTest {
    // Consumer test với stub được lấy từ repository.
}
~~~

Đây là ví dụ **annotation**, cần classpath và phiên bản tương thích. URL repository là placeholder. Tên/chức năng repository URL, credentials và proxy phải được kiểm tra theo Stub Runner version; các CI jobs có thể cấu hình repository trong Maven settings hoặc môi trường riêng.

| Chế độ | Artifact từ đâu? | Trường hợp sử dụng |
| --- | --- | --- |
| **LOCAL** | Maven local repository của môi trường chạy test | Phát triển và pipeline cùng máy/agent |
| **REMOTE** | Artifact repository được cấu hình | Kiểm thử giữa các nhóm và CI phân tán |
| **CLASSPATH** | Stub resources/JAR đã nằm trên classpath | Test khi stub được đóng gói vào dependencies của consumer |

**Không tự động đổi version sang `+` hoặc “latest” để khỏi cập nhật cấu hình.** Version động khiến cùng consumer commit có thể thử với stub khác nhau ở các lần chạy. Release gate nên chốt version hoặc ít nhất ghi lại version/bytes đã phân giải.

## 10. Package, install, deploy với multi-module Maven

Một dự án có thể gồm:

~~~text
commerce/
├── pom.xml               # Parent / aggregator
├── order-api/
├── order-domain/
├── order-service/
│   ├── pom.xml
│   └── src/test/resources/contracts/orders/...
└── checkout-service/
~~~

Không phải module nào cũng cần chạy Spring Cloud Contract plugin. Nếu contracts thuộc `order-service` thì:

- `order-service` cần cấu hình plugin và base test class phù hợp.
- Parent POM có thể quản lý version plugin trong `pluginManagement`.
- Nhưng **`pluginManagement` chỉ khai báo cấu hình quản lý**, không tự bảo đảm plugin được thực thi trong module con.
- `order-api` hoặc `order-domain` không nên được ép sinh stub chỉ vì kế thừa một plugin không áp dụng.
- POM có packaging `pom` của aggregator không mặc định tạo `order-service-...-stubs.jar`.

Nếu cần build một module cùng các dependencies nội bộ trong reactor, có thể dùng:

~~~bash
./mvnw -pl order-service -am clean verify
~~~

`-pl` chọn module, `-am` xây thêm module mà Maven xác định là phụ thuộc cần thiết trong reactor. Đừng dựa vào nó để mặc định chạy **tất cả consumer modules** không nằm trong dependency graph. Các consumer contract suites riêng có thể cần pipeline hoặc command khác.

### Điều phối deploy nhiều module

Khi chạy `mvn deploy` từ parent, Maven có thể đưa nhiều modules lên remote repository, không chỉ producer stubs. Điều này có thể không phù hợp với quyền publish của một nhánh PR.

Nên phân biệt:

- **Build/verify**: có thể chạy rộng trong reactor để kiểm tra.
- **Publish**: chỉ chạy trong pipeline phát hành được phép, với release repository và modules đã xác định.
- **Consumer tests**: chọn các consumer versions cần hỗ trợ và stub artifact đã được kiểm chứng.

## 11. SNAPSHOT, release version và tính tái lập

Ví dụ:

~~~text
1.4.3-SNAPSHOT : dùng trong phát triển, nội dung có thể cập nhật.
1.4.2          : release version, nên là artifact bất biến.
+ / version range: có thể phân giải artifact khác theo thời gian.
~~~

| Tình huống | Rủi ro |
| --- | --- |
| Re-deploy cùng release version 1.4.2 với bytes khác | Không thể tái lập kết quả consumer test cũ |
| Consumer dùng SNAPSHOT nhưng CI cache bản trước | Consumer không test stub của commit mới |
| Consumer dùng `+`/dynamic version | Cùng một commit có thể chạy với hai producer stubs khác nhau |
| Producer mới publish nhưng consumer chưa cập nhật ID | CI xanh với stub cũ, bỏ sót breaking change |
| Cùng version nhưng source contract bên ngoài thay revision | Stub và test producer có thể không cùng cam kết |

Với release chính thức nên:

1. Chốt producer commit, contract revision và version.
2. Build và chạy generated producer tests.
3. Tạo stub JAR từ **cùng build/hợp đồng**.
4. Kiểm tra contents và checksum của stub artifact.
5. Publish vào repository có chính sách immutable.
6. Để consumer thử **đúng phiên bản mới** và lưu kết quả.

**Đánh số semantic version không thay thế kiểm thử tương thích.** Producer tăng minor hay patch vẫn có thể thay field mà consumer cũ cần.

## 12. Quy trình CI khuyến nghị

Một pipeline có thể chia thành các cổng rõ ràng:

~~~mermaid
flowchart TD
    A["Checkout producer + contract revision"] --> B["Clean + generate tests + convert"]
    B --> C{"Generated producer tests được chạy?"}
    C -->|Không| X["BLOCK"]
    C -->|Có| D{"Producer contract tests PASS?"}
    D -->|Không| X
    D -->|Có| E["package: main JAR + stubs JAR"]
    E --> F{"Stub JAR đủ mappings, đúng classifier?"}
    F -->|Không| X
    F -->|Có| G["verify: integration/quality gates"]
    G --> H{"PASS?"}
    H -->|Không| X
    H -->|Có| I["install/deploy có kiểm soát"]
    I --> J["Consumer tải đúng G:A:V:stubs"]
    J --> K{"Tọa độ + checksum đúng?"}
    K -->|Không| X
    K -->|Có| L["Stub Runner + consumer tests"]
    L --> M{"Consumer assertions PASS?"}
    M -->|Không| X
    M -->|Có| N["Lưu evidence và quyết định rollout"]
~~~

### Các cổng bắt buộc nên xét

| Cổng | Nếu bỏ qua có thể xảy ra |
| --- | --- |
| Contracts root và số contract được phát hiện | Build xanh vì Verifier không tìm được DSL |
| Generated test compilation và execution | Có code sinh ra nhưng không được test runner chạy |
| Check `-stubs.jar` | Chỉ publish JAR chính, consumer không tải được stubs |
| Truy vết contract revision | Stub tạo từ nguồn khác producer tests |
| Chọn repository và quyền deploy | Đẩy nhầm artifact lên release repository |
| Stub artifact checksum/version | Consumer dùng bản cũ hoặc bị ghi đè |
| Consumer integration assertions | Stub khởi động nhưng logic consumer vẫn có lỗi |
| Chống skip tests ngoài chủ đích | CI PASS không mang ý nghĩa bảo đảm tương thích |

### Không dùng lệnh skip như cách “sửa” contract test lỗi

Một số flags có thể bỏ qua các phép thử:

~~~bash
./mvnw package -DskipTests
./mvnw package -Dmaven.test.skip=true
./mvnw package -Dspring.cloud.contract.verifier.skip=true
~~~

Ý nghĩa chính xác có khác nhau: `-DskipTests` thường bỏ qua **thực thi** test nhưng vẫn có thể biên dịch; `-Dmaven.test.skip=true` có thể bỏ cả **biên dịch và chạy**; property của Verifier ảnh hưởng các goals của plugin. Chúng **không tương đương**, và không nên dùng trong release gate cần xác minh contract.

Một `package` hoặc `deploy` thành công với tests bị skip có thể vẫn tạo JAR, nhưng không có bằng chứng producer đúng hợp đồng.

## 13. Artifact nguồn hợp đồng tách riêng với producer

Trong một số tổ chức, contracts nằm ở **repository hoặc artifact độc lập** thay vì `src/test/resources/contracts`. Maven plugin có các cấu hình cho việc lấy contracts bên ngoài, chẳng hạn contract dependency, contracts path, mode và repository URL theo version.

Khi đó có ít nhất ba danh tính cần ghi:

~~~text
Producer build revision:       order-service@abc123
Contract source revision:      order-contracts@def456
Published stub artifact:       com.example.orders:order-service:1.4.2:stubs
~~~

Nếu plugin test producer với hợp đồng `def456` nhưng job khác đóng gói stub từ `xyz789`, consumer PASS không chứng minh producer đã được xác minh với đúng bộ stub đó.

**Bước package không tự bảo đảm provenance.** Pipeline cần khóa nguồn hợp đồng, ghi lại artifact/revision được phân giải và bảo đảm generated tests + mappings dùng cùng đầu vào.

## 14. Đừng nhầm chạy stub với phát hành stub

Spring Cloud Contract Maven plugin có thể cung cấp goal `run` để chạy HTTP stubs trong môi trường phù hợp. Nhưng:

| Thao tác | Mục đích |
| --- | --- |
| `spring-cloud-contract:run` | Khởi động stubs để thử request |
| `package` | Tạo artifact trong `target` |
| `install` | Đưa artifact vào Maven local |
| `deploy` | Công bố artifact qua remote Maven repository |
| Stub Runner consumer test | Tải/chạy stub được chọn và assert logic consumer |

Một WireMock server đang chạy trên `localhost:8090` **không có nghĩa artifact đã được publish**. Ngược lại, một `-stubs.jar` đã deploy không tự mở HTTP port; consumer test cần khởi chạy Stub Runner hoặc một runtime stub tương ứng.

Tọa độ artifact và port runtime là những thông tin khác nhau:

~~~text
Artifact: com.example.orders:order-service:1.4.2:stubs
Runtime:  http://localhost:8090
Request:  GET /api/orders/ORD-1001
~~~

## 15. Các lỗi thường gặp theo từng pha

| Triệu chứng | Pha/khâu thường liên quan | Điều cần kiểm tra |
| --- | --- | --- |
| Không thấy generated tests | `generate-test-sources` | Plugin chưa chạy, contracts root sai, file DSL bị lọc |
| Generated tests không biên dịch | `test-compile` | Base class, dependencies, test mode và generated source |
| Test producer thất bại | `test`/`verify` theo cấu hình | Implementation không đáp ứng contract hoặc fixture sai |
| `target/stubs` không có mappings | `convert` | Input contracts, plugin executions, conversion log |
| `package` tạo JAR chính nhưng thiếu `-stubs.jar` | `generateStubs`/attachment | Plugin goal, classifier, cấu hình skip và nội dung mappings |
| `install` thành công nhưng consumer LOCAL không thấy stub | Local repository | Tọa độ khác, chưa attach, build trên máy khác hoặc cache sai |
| `deploy` báo 401/403 | Remote repository | Credential, settings server ID, quyền publish |
| `deploy` báo thiếu repository | distributionManagement | Repository URL, release/SNAPSHOT target, plugin configuration |
| `deploy` có JAR chính mà không có stubs | Artifact attachment/publication | Kiểm tra artifact list, classifier, metadata sau publish |
| Consumer REMOTE báo không tải được | Stub Runner repository resolution | group/artifact/version/classifier, URL, quyền, proxy/cache |
| Stub Runner khởi động nhưng trả 404 | HTTP matching | Method/URL/headers/body và mappings trong JAR |
| Consumer CI PASS với API đã breaking | Version/provenance | Đang test stub cũ hoặc thiếu assertions |
| CI pass nhưng số contract tests bằng 0 | Test execution/filter | Fail khi thiếu contract hoặc test bị skip |

**Chẩn đoán theo lớp:** nguồn hợp đồng → sinh test → thực thi test → chuyển mapping → đóng gói → attach → install/deploy → tải artifact → HTTP matching → consumer logic.

Đừng sửa `response.body` trong DSL chỉ vì Maven báo lỗi 401 khi deploy, hoặc sửa repositoryRoot khi HTTP stub đã khởi động nhưng request không match.

## 16. Bài tập thực hành

### Bài tập A — package, install hay deploy?

Một lập trình viên chạy `./mvnw clean package` thành công, rồi đồng nghiệp ở máy khác cấu hình Stub Runner LOCAL và không thấy `order-service:1.4.2:stubs`.

**Yêu cầu:** giải thích vì sao và đề xuất hai quy trình: thử local cùng máy và chia sẻ artifact cho nhóm.

**Gợi ý:** package chỉ tạo artifact; install đưa vào local repository của máy chạy; deploy đưa tới remote repository để đồng nghiệp tải (thường bằng REMOTE).

### Bài tập B — Chỉ có JAR chính

Sau `./mvnw clean install`, Maven local có `order-service-1.4.2.jar` và POM, nhưng không có `order-service-1.4.2-stubs.jar`.

**Yêu cầu:** xác định lớp lỗi và liệt kê những điều cần kiểm tra trước khi chạy lại install.

**Gợi ý:** kiểm tra contract discovery, `convert`, `generateStubs`, attachment/classifier; `install` không tự tạo stub JAR nếu build không attach nó.

### Bài tập C — verify khác deploy thế nào?

Một CI job chạy `./mvnw clean verify` với các contract tests PASS. Một job khác cần consumer tải stubs qua remote repository.

**Yêu cầu:** nêu bước còn thiếu và điều kiện để cho phép bước đó.

**Gợi ý:** cần publish artifact; kiểm tra stubs JAR và provenance, có quyền deploy, rồi verify artifact có thể tải từ repository.

### Bài tập D — Bỏ qua test để release

Một producer có generated contract test FAIL; người phát triển dùng `-DskipTests` để `mvn deploy` thành công.

**Yêu cầu:** đánh giá tính hợp lệ của release evidence và đề xuất hướng sửa.

**Gợi ý:** deploy thành công chỉ chứng minh artifact được publish, không chứng minh producer đáp ứng hợp đồng; sửa implementation, fixture hoặc contract theo thay đổi đã thống nhất, rồi chạy lại producer tests.

### Bài tập E — Multi-module

Một parent POM quản lý plugin trong `pluginManagement`, nhưng module `order-service` không khai báo sử dụng plugin và không có generated tests.

**Yêu cầu:** giải thích vai trò của `pluginManagement` và cách bảo đảm plugin chạy đúng module.

**Gợi ý:** quản lý version/config khác với kích hoạt plugin; xác nhận effective POM và Maven log của module.

### Bài tập F — SNAPSHOT bị thay đổi

Checkout CI dùng `order-service:1.5.0-SNAPSHOT:stubs`. Cùng một commit Checkout chạy hai lần nhưng nhận hai tập mappings khác nhau.

**Yêu cầu:** phân tích rủi ro và cách làm release gate tái lập được.

**Gợi ý:** khóa revision/version cụ thể, ghi checksum, dùng artifact immutable hoặc môi trường tách biệt; không dùng bản mới nhất ngầm.

### Bài tập G — Consumer cũ cần thử bản producer mới

Producer 1.5.0 đổi trường JSON `status` thành `paymentStatus`. Checkout 2.8.0 PASS với stub 1.4.2.

**Yêu cầu:** có thể kết luận 1.5.0 tương thích Checkout 2.8.0 chưa? Cần kiểm tra gì?

**Gợi ý:** phải kiểm thử Checkout 2.8.0 với stub 1.5.0 được tạo từ cùng contract revision producer 1.5.0 đã verify, rồi đánh giá kế hoạch giữ tương thích trường cũ.

## 17. Checklist trước khi phát hành qua Maven

- [ ] Hợp đồng Groovy/YAML nằm ở nguồn chính xác và được plugin phát hiện.
- [ ] `generateTests` thực sự sinh producer tests vào test source set.
- [ ] Generated tests được biên dịch, thực thi và PASS, không bị skip.
- [ ] Base test class, fixture và test mode phù hợp với producer HTTP/messaging.
- [ ] `convert` tạo đủ mappings từ contracts mong đợi.
- [ ] `generateStubs` tạo artifact JAR được attach với classifier `stubs` hoặc classifier đã thỏa thuận.
- [ ] `package` tạo cả artifact chính lẫn stub artifact cần công bố.
- [ ] `verify` thực sự chạy quality/integration checks mà dự án yêu cầu.
- [ ] `install` đưa stub JAR vào Maven local đúng group/artifact/version.
- [ ] `deploy` chỉ chạy trong pipeline được phép với repository URL và credentials an toàn.
- [ ] Kiểm tra remote repository thực sự chứa `-stubs.jar` và metadata tương ứng.
- [ ] Không chấp nhận release do `-DskipTests` hoặc `spring.cloud.contract.verifier.skip` khi cần bằng chứng tương thích.
- [ ] Artifact release bất biến hoặc ít nhất được ghi checksum và revision.
- [ ] Không phụ thuộc `+`/latest trong release gate khi cần kết quả tái lập.
- [ ] Consumer Stub Runner dùng đúng artifact, classifier và version đã publish.
- [ ] Consumer integration tests có assertions nghiệp vụ, không chỉ kiểm tra stub khởi động.
- [ ] Với multi-module, plugin hoạt động đúng module và job publish không đẩy nhầm artifact.
- [ ] Với contracts nguồn ngoài, producer tests và stub JAR dùng cùng revision.
- [ ] Không đưa token, mật khẩu hoặc dữ liệu production nhạy cảm vào POM/contract/stub.
- [ ] Báo cáo CI lưu producer commit, contract revision, artifact coordinate và consumer versions đã kiểm chứng.

## 18. Tài liệu tham khảo

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): định nghĩa các pha `package`, `verify`, `install`, `deploy`.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): cấu hình plugin, contracts, sinh tests và base class.
- [Spring Cloud Contract Maven Plugin — Goals](https://docs.spring.io/spring-cloud-contract/docs/current/spring-cloud-contract-maven-plugin/plugin-info.html): các goals `generateTests`, `convert` và `generateStubs`.
- [Spring Cloud Contract Maven Plugin — generateStubs](https://docs.spring.io/spring-cloud-contract/docs/current/spring-cloud-contract-maven-plugin/generateStubs-mojo.html): đóng gói mappings thành stub JAR và classifier.
- [Spring Cloud Contract — Stub Runner Common Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-common.html): tọa độ stub và cách phân giải artifact.

**Ghi nhớ:** `package` **tạo** main/stub artifacts, `install` đưa chúng vào **Maven local repository**, còn `deploy` **công bố** chúng ở remote repository. Nhưng thành công của một pha Maven không tự chứng minh tương thích producer–consumer: CI phải xác nhận generated producer tests thật sự chạy PASS, stub JAR đúng classifier/nội dung/phiên bản và consumer kiểm thử với **chính artifact đó**. Đây là cách biến việc phát hành stub thành một quy trình có thể kiểm tra và truy vết, thay vì chỉ nhìn thấy dòng `BUILD SUCCESS`.
