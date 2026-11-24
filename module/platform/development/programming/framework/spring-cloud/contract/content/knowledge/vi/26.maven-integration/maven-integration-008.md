# Tách cấu hình dùng cho local và CI bằng profile

## 1. Vì sao cần Maven profile khi kiểm thử hợp đồng?

Trong một hệ thống microservices, **producer** mô tả HTTP API hoặc thông điệp bằng Groovy/YAML DSL, **Spring Cloud Contract Verifier** sinh test kiểm tra implementation, rồi đóng gói các mappings thành stub artifact. **Consumer** chạy kiểm thử qua **Stub Runner** để phát hiện sớm các thay đổi làm client không còn tương thích. Quy trình đó phải vận hành được trên máy developer lẫn **CI**.

Vấn đề là **môi trường local và CI có điều kiện khác nhau**:

- Trên máy local, bạn có thể vừa thay contract ở producer, chạy `mvn install` và cho consumer lấy stub từ `~/.m2/repository`.
- Trên CI, producer và consumer thường chạy ở các pipeline/repository riêng, cần stub **đúng version** từ Nexus/Artifactory hoặc một artifact repository được kiểm soát.
- Local có thể thiếu mạng hoặc credentials của kho chung; CI cần đảm bảo không lấy ngầm bản stub cũ chỉ có trên máy build.
- CI phải thực thi generated producer tests, không được xanh do `skipTests` hoặc do không phát hiện contract nào.
- Cấu hình test phải có khả năng tái lập: cùng commit và cùng version stub phải sử dụng cùng thỏa thuận API.

**Maven profiles** cho phép giữ một `pom.xml` chung, nhưng chọn những thuộc tính/cấu hình phụ thuộc môi trường bằng `-P` hoặc điều kiện kích hoạt. Bài này thuộc chương **Tích hợp Maven** của module `SPRING_CLOUD_CONTRACT` và tập trung vào chủ đề **tách cấu hình dùng cho local và CI bằng profile**.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Maven build profile**, **Spring Boot runtime profile** và **Stub Runner stubs mode**.
2. Thiết kế profile `contract-local` và `contract-ci` mà không nhân đôi cấu hình plugin.
3. Nối Maven properties với Spring properties được consumer tests thực sự đọc.
4. Chọn `LOCAL` cho stub đã cài trong Maven local repository và `REMOTE` cho artifact repository CI.
5. Giữ cấu hình tạo/generated producer tests, base class, test framework và test mode nhất quán.
6. Phân biệt những lệnh skip test nguy hiểm với bước kiểm thử thật.
7. Đặt repository URL, artifact version, credentials và Maven `settings.xml` đúng chỗ.
8. Chẩn đoán vì sao local xanh nhưng CI đỏ hoặc CI xanh giả.
9. Xây release gate: producer verification đạt rồi mới phát hành stub cho consumer.

> **Nguyên tắc:** Profile thay đổi **môi trường lấy artifact và chính sách chạy build**; nó không nên thay đổi ý nghĩa contract để làm bài kiểm thử xanh. Producer và consumer vẫn phải thống nhất request/response hoặc message schema.

## 2. Ba khái niệm dễ nhầm: Maven profile, Spring profile và stubs mode

| Khái niệm | Điều khiển | Ví dụ | Kích hoạt |
| --- | --- | --- | --- |
| **Maven build profile** | Build POM, dependencies, plugins và Maven properties | `contract-local`, `contract-ci` | `mvn -Pcontract-ci verify` |
| **Spring profile** | Bean/configuration của ứng dụng Spring lúc chạy | `test`, `ci`, `local` | `spring.profiles.active=test` hoặc `@ActiveProfiles` |
| **Stub Runner stubs mode** | Cách Stub Runner tìm stub artifacts | `CLASSPATH`, `LOCAL`, `REMOTE` | `spring.cloud.contract.stubrunner.stubsMode` |
| **Verifier contractsMode** | Cách Maven plugin lấy **nguồn contracts bên ngoài** khi dùng external contracts | `LOCAL`, `REMOTE` | `<contractsMode>...` trong plugin |

Bốn đối tượng này có thể cùng dùng từ “local”, nhưng **không tự liên kết với nhau**.

Ví dụ lệnh:

~~~bash
./mvnw -Pcontract-ci -Dspring.profiles.active=test verify
~~~

Trong lệnh này:

- `-Pcontract-ci` kích hoạt **Maven profile**.
- `-Dspring.profiles.active=test` đặt **Spring profile** cho các test JVM được truyền property.
- `Stub Runner` có thể đọc `REMOTE` nhờ cấu hình Maven/Surefire trong profile; nó **không tự suy ra** mode từ tên `contract-ci`.
- `Verifier contractsMode` không phải `Stub Runner stubsMode`: một bên chọn nguồn *contract definitions*, bên kia chọn nguồn *stub artifacts*.

### 2.1. Chọn ranh giới trách nhiệm

Một phương án dễ bảo trì là:

- Trong phần chung của POM: giữ dependency versions, plugin verifier, `baseClassForTests`, `testFramework`, `testMode` và các quy tắc kiểm chứng ổn định.
- Trong `contract-local`: chọn nguồn stub local, cổng động hoặc cấu hình thân thiện cho developer.
- Trong `contract-ci`: chọn nguồn stub remote, cố định version, fail khi thiếu artifacts và chạy quality gates.
- Trong `settings.xml`/CI secrets: quản lý mirror, Maven repository credentials và quyền publish.
- Trong `application-test.yml` hoặc Spring test context: giữ những cấu hình ứng dụng như HTTP client base URL nếu không bị Maven profile điều khiển trực tiếp.

**Đừng đổi test mode từ MOCKMVC sang WEBTESTCLIENT theo môi trường** chỉ để che khác biệt: test mode phải đi theo stack của producer (Spring MVC hay WebFlux), không đi theo máy chạy build.

## 3. Luồng Maven local và CI cần thống nhất

~~~mermaid
flowchart TD
    A["Groovy/YAML contracts"] --> B["Maven Contract Verifier: generateTests"]
    B --> C["Generated producer tests"]
    C --> D{"Producer verification đạt?"}
    D -- "Không" --> E["Build fail, không publish"]
    D -- "Có" --> F["Generate/attach stubs classifier"]
    F --> L["Local: mvn install vào .m2"]
    F --> R["CI: mvn deploy tới artifact repository"]
    L --> S["Consumer -Pcontract-local"]
    R --> T["Consumer -Pcontract-ci"]
    S --> U["Stub Runner WireMock"]
    T --> U
    U --> V["Consumer test gọi client thật"]
    V --> W{"Assertions phù hợp?"}
    W -- "Không" --> X["Sửa consumer/contract hoặc version"]
    W -- "Có" --> Y["Có bằng chứng tương thích trong phạm vi test"]
~~~

**Hai phía phải được kiểm tra riêng**:

1. Producer tests xác nhận implementation thật đáp ứng contract.
2. Consumer tests xác nhận client và use case dùng stubs đúng.
3. Artifact stub chỉ nên được **publish/promote** nếu producer đạt gates cần thiết.
4. Local/CI có thể lấy stub ở nguồn khác nhau, nhưng phải biết chính xác tọa độ `groupId:artifactId:version:classifier` nào đã được kiểm tra.

### 3.1. Cùng tọa độ, không đồng nghĩa cùng bytes

Nếu developer cài lại `inventory-producer:1.2.3:stubs` vào local repository bằng nội dung mới nhưng release repository vẫn giữ bản `1.2.3` cũ, hai profile sẽ chạy với **hai nội dung stub khác nhau dưới cùng coordinates**.

Cần chính sách artifact **immutable** cho release, dùng version mới hoặc snapshot rõ ràng khi thay nội dung. Việc kiểm tra checksum, artifact metadata và provenance đặc biệt quan trọng khi local xanh nhưng CI đỏ.

## 4. Maven profiles hoạt động thế nào?

Profile được khai báo trong phần `<profiles>` của `pom.xml`, có `<id>` và có thể chứa `<properties>`, `<dependencies>`, `<build>` hoặc cấu hình repository phù hợp.

Ví dụ tối thiểu:

~~~xml
<profiles>
    <profile>
        <id>contract-local</id>
        <properties>
            <contract.environment>local</contract.environment>
        </properties>
    </profile>
    <profile>
        <id>contract-ci</id>
        <properties>
            <contract.environment>ci</contract.environment>
        </properties>
    </profile>
</profiles>
~~~

Kích hoạt cụ thể:

~~~bash
./mvnw -Pcontract-local help:active-profiles
./mvnw -Pcontract-ci help:active-profiles
~~~

Với bài toán contract testing, nên **dùng `-P` rõ ràng** khi đang phát triển và trong CI để log build cho biết chính xác profile nào được bật.

### 4.1. activeByDefault có một bẫy

Maven hỗ trợ:

~~~xml
<activation>
    <activeByDefault>true</activeByDefault>
</activation>
~~~

Nhưng theo Maven, profile `activeByDefault` trong cùng POM có thể bị **vô hiệu hóa khi một profile khác được kích hoạt** trong POM đó, ngay cả khi profile kia không liên quan tới contract testing. Vì thế:

- Không coi `activeByDefault` là một chính sách production CI chắc chắn.
- Nếu phải dùng default, kiểm tra `help:active-profiles` trong mọi lệnh build quan trọng.
- Với release, dùng `-Pcontract-ci` minh thị và fail khi các thuộc tính cần thiết thiếu.
- Đừng dựa vào việc profile đã được IDE kích hoạt để suy ra CI cũng kích hoạt giống vậy.

### 4.2. Kích hoạt từ môi trường có phù hợp không?

Maven cũng hỗ trợ kích hoạt dựa vào system property hoặc environment variable, ví dụ `env.CI`. Tuy nhiên một biến `CI` có thể có giá trị `true`, `1` hoặc tồn tại nhưng rỗng tùy nhà cung cấp.

Để đơn giản và dễ điều tra, ví dụ xuyên suốt chọn:

~~~bash
./mvnw -Pcontract-local clean verify
./mvnw -B -ntp -Pcontract-ci clean verify
~~~

Không bật cả `contract-local` và `contract-ci` trong cùng một build trừ khi đã thiết kế precedence rõ. Nếu cả hai cung cấp cùng property, việc hợp nhất có thể khiến nguồn stub không đúng ý định.

## 5. Chọn thứ gì nên nằm ở cấu hình chung?

Bất kể chạy ở local hay CI, contract của Inventory Service vẫn là `GET /api/inventory/SKU-100` với response status/body đã thống nhất. Các yếu tố không nên tự thay đổi theo profile:

- Nguồn contracts được duyệt.
- `testFramework`: JUnit 5 nếu dự án dùng JUnit Jupiter.
- `testMode`: `MOCKMVC` cho Spring MVC hoặc `WEBTESTCLIENT` cho WebFlux.
- `baseClassForTests` hoặc mapping base classes.
- Tên và nội dung contract.
- Định nghĩa DTO/schema và matcher cần bảo vệ.
- Quy tắc chạy generated producer tests trong quality gate.

Ví dụ contract Groovy:

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

Nếu CI muốn trả `quantity: 0` thay vì `8` chỉ vì fixture khác, hãy sửa **cách chuẩn bị dữ liệu producer test** cho đúng contract, không tạo một bản contract yếu hơn chỉ để CI xanh.

## 6. Ví dụ POM producer: giữ Verifier plugin ở cấu hình chung

Producer chịu trách nhiệm sinh/kiểm chứng các hợp đồng và tạo stub artifact. Ví dụ phần rút gọn trong `pom.xml`:

~~~xml
<properties>
    <!-- Thay bằng version tương thích Spring Boot/Spring Cloud trong dự án -->
    <spring-cloud-contract.version>VERSION_APPROVED_BY_PROJECT</spring-cloud-contract.version>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>${spring-cloud-contract.version}</version>
            <extensions>true</extensions>
            <configuration>
                <testFramework>JUNIT5</testFramework>
                <testMode>MOCKMVC</testMode>
                <baseClassForTests>com.example.inventory.contract.ContractVerifierBase</baseClassForTests>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

**Đây là một snippet POM, không phải file POM đầy đủ.** Bạn cần Spring Boot/test dependencies, versions tương thích và một `ContractVerifierBase` thực sự cấu hình `RestAssuredMockMvc` hoặc test context tương ứng. `VERSION_APPROVED_BY_PROJECT` là placeholder phải thay trước khi build.

Theo tài liệu Spring Cloud Contract Maven Plugin, mục tiêu `generateTests` gắn với phase `generate-test-sources` trong thiết lập plugin phù hợp; plugin có các goals `convert`, `generateStubs` và `generateTests`. Nếu cấu hình lifecycle khác ví dụ hoặc plugin không được bật, phải xác nhận generated tests và stub artifact thật sự được tạo.

### 6.1. Vì sao không đưa toàn bộ plugin chỉ vào profile CI?

Nếu chỉ CI mới chạy Contract Verifier, local developers sẽ khó thấy breaking change cho tới lúc đẩy code. Ngoài ra, việc generated tests không có trong build local khiến developer dễ đánh giá sai độ phủ. Nên giữ **logic sinh/kiểm chứng contract chung** và chỉ dùng profiles cho những thay đổi thực sự do môi trường.

Nếu local cần một quy trình rất nhanh, có thể có lệnh kiểm thử một nhóm test hoặc goal riêng, nhưng **đừng xem kết quả của bước nhanh là tương đương `clean verify` đầy đủ**.

### 6.2. Nếu producer dùng WebFlux thì sao?

Ở producer WebFlux:

~~~xml
<configuration>
    <testFramework>JUNIT5</testFramework>
    <testMode>WEBTESTCLIENT</testMode>
    <baseClassForTests>com.example.inventory.contract.ReactiveContractBase</baseClassForTests>
</configuration>
~~~

Chọn `MOCKMVC`/`WEBTESTCLIENT` theo công nghệ HTTP boundary, **không theo local hay CI**. Generated tests phải được chạy ở cả hai nơi nếu cùng tuyên bố quality gate.

### 6.3. Cần nhìn kết quả test thật

Sau build producer, kiểm tra:

- Generated test classes/methods xuất hiện theo contracts.
- Tests thực sự được test runner (Surefire/Failsafe theo dự án) thực thi.
- Contract Verifier không bị skip.
- Khi thử thay response field/status không tương thích, generated test có thể fail.
- Artifact `-stubs.jar` có mappings đúng, không chỉ một main JAR.

`BUILD SUCCESS` nhưng generated tests không được thực thi không chứng minh producer đáp ứng contract.

## 7. Từ Maven profile sang Stub Runner: cần một “cầu nối”

Một lỗi phổ biến:

~~~xml
<profile>
    <id>contract-ci</id>
    <properties>
        <stubrunner.mode>REMOTE</stubrunner.mode>
    </properties>
</profile>
~~~

Sau đó viết consumer test:

~~~java
@AutoConfigureStubRunner
class CheckoutContractTest {
    // ...
}
~~~

và mong Stub Runner tự nhận `REMOTE`. **Không có cơ chế tự động vì tên property `stubrunner.mode` là property do dự án đặt**, không phải property Spring Cloud Contract Stub Runner mặc định. Maven biết nó, nhưng JVM chạy Spring tests chưa chắc biết.

Có hai cách tường minh:

1. **Surefire/Failsafe systemPropertyVariables**: chuyển giá trị Maven profile thành Java system properties mà Spring/Stub Runner đọc.
2. **Spring test configuration**: sử dụng `application-test.yml` cùng Spring profile/env variables, bảo đảm Maven profile kích hoạt hoặc chuyển đúng môi trường.

Bài này minh họa cách 1 để thấy đường truyền rõ ràng. Không bắt buộc mọi dự án phải chọn cách đó, nhưng phải chứng minh property đã đến đúng test runtime.

### 7.1. Phân biệt Maven property với Java system property

| Vị trí | Ví dụ | Ai đọc? |
| --- | --- | --- |
| POM profile property | `stubrunner.mode=LOCAL` | Maven model/plugin interpolation |
| Surefire systemPropertyVariables | `spring.cloud.contract.stubrunner.stubsMode=LOCAL` | JVM chạy JUnit/Spring test |
| Spring configuration property | `spring.cloud.contract.stubrunner.stubs-mode=LOCAL` | Spring binder trong test application context |
| Environment variable | `SPRING_CLOUD_CONTRACT_STUBRUNNER_STUBS_MODE=LOCAL` | Spring environment nếu property binding hợp lệ |

Trong tài liệu Spring Cloud Contract, tên chuẩn dạng camelCase của system property là `spring.cloud.contract.stubrunner.stubsMode`, `repositoryRoot` và `ids`; nếu viết trong YAML Spring, có thể dùng dạng kebab-case `stubs-mode`, `repository-root` theo relaxed binding. Đừng trộn chúng khi đối chiếu log mà không biết binder làm việc thế nào.

## 8. POM consumer: hai profiles cùng một cấu hình test chung

Giả sử Checkout cần stub:

~~~text
com.example:inventory-producer:1.2.3:stubs
~~~

Chọn **một phiên bản cụ thể** để CI có thể tái lập. POM ví dụ dưới đây chỉ trình bày những phần liên quan, cần ghép vào project thực và pin các plugin versions qua parent/`pluginManagement`:

~~~xml
<properties>
    <inventory.stub.version>1.2.3</inventory.stub.version>
    <inventory.stub.id>com.example:inventory-producer:${inventory.stub.version}:stubs</inventory.stub.id>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <systemPropertyVariables>
                    <spring.cloud.contract.stubrunner.ids>${inventory.stub.id}</spring.cloud.contract.stubrunner.ids>
                    <spring.cloud.contract.stubrunner.stubsMode>${stubrunner.mode}</spring.cloud.contract.stubrunner.stubsMode>
                    <spring.cloud.contract.stubrunner.repositoryRoot>${stubrunner.repository.root}</spring.cloud.contract.stubrunner.repositoryRoot>
                </systemPropertyVariables>
            </configuration>
        </plugin>
    </plugins>
</build>

<profiles>
    <profile>
        <id>contract-local</id>
        <properties>
            <stubrunner.mode>LOCAL</stubrunner.mode>
            <stubrunner.repository.root></stubrunner.repository.root>
        </properties>
    </profile>

    <profile>
        <id>contract-ci</id>
        <properties>
            <stubrunner.mode>REMOTE</stubrunner.mode>
            <stubrunner.repository.root>https://repo.example.test/repository/maven-releases/</stubrunner.repository.root>
        </properties>
    </profile>
</profiles>
~~~

Cần hiểu:

- `inventory.stub.version` dùng chung để không vô tình thay contract giữa local/CI.
- `inventory.stub.id` được đưa tới Stub Runner qua system property `spring.cloud.contract.stubrunner.ids`.
- `stubrunner.mode` là Maven property được **profile gán**, sau đó Surefire chuyển thành `spring.cloud.contract.stubrunner.stubsMode`.
- `stubrunner.repository.root` rỗng ở LOCAL (resolver dùng local Maven repository), là URL artifact repository ở CI.
- `repo.example.test` chỉ là URL ví dụ; hãy thay bằng artifact repository thật mà tổ chức sử dụng.
- Không dùng credential literal trong POM. Xác thực cần xử lý bằng CI secrets/settings/properties tương ứng, theo cách đã được xác minh trong dự án.

**Điều kiện quan trọng:** `-Pcontract-local` hoặc `-Pcontract-ci` phải được bật trước khi Maven nội suy `stubrunner.mode` và `stubrunner.repository.root`. Nếu không bật, properties chưa được định nghĩa và test có thể nhận chuỗi literal chưa giải quyết. Có thể đặt default rõ ràng và fail-closed bằng Maven Enforcer hoặc kiểm tra trong CI nếu muốn hỗ trợ build không cần `-P`.

### 8.1. Cần dependency nào phía consumer?

Consumer cần Spring Cloud Contract Stub Runner test dependency, ví dụ:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-stub-runner</artifactId>
    <scope>test</scope>
</dependency>
~~~

Version có thể được quản lý bởi Spring Cloud Contract BOM tương thích. `@AutoConfigureStubRunner` cần Spring/JUnit test integration tương ứng.

**Không bắt buộc** thêm stub JAR làm `test dependency` trong consumer khi dùng `LOCAL` hoặc `REMOTE`, vì Stub Runner có thể tự phân giải artifact theo `ids`. Ngược lại, `CLASSPATH` thường yêu cầu stub JAR đã nằm trên test runtime classpath. Đây là khác biệt về cơ chế, không phải ba nguồn tương đương ở cấp dependency graph.

### 8.2. Consumer test đọc system properties

~~~java
@SpringBootTest
@AutoConfigureStubRunner
class CheckoutContractTest {

    @StubRunnerPort("com.example:inventory-producer")
    int inventoryPort;

    @Test
    void checkoutShouldUseInventoryStub() {
        InventoryClient inventory = new InventoryClient(
            "http://localhost:" + inventoryPort
        );
        CheckoutService checkout = new CheckoutService(inventory);

        assertThat(checkout.canPlaceOrder("SKU-100", 3))
            .isTrue();
    }
}
~~~

Đây là **khung test minh họa**; cần đủ imports, test dependencies và các class của ứng dụng. Quan trọng nhất, test phải dùng `InventoryClient`/`CheckoutService` thực, không chỉ ping WireMock để khẳng định stub chạy được.

Tránh đặt một giá trị `stubsMode = StubsMode.LOCAL` hoặc `ids = "..."` cố định trên annotation nếu mục tiêu là để profile bên ngoài điều khiển chúng. Khi có nhiều nguồn cấu hình, phải kiểm tra precedence và property binding thực tế của phiên bản Spring Cloud Contract.

### 8.3. Nếu dùng Failsafe thay Surefire

Maven Surefire thường chạy unit tests ở phase `test`; Failsafe thường được dùng cho integration tests `*IT` trong các phase `integration-test`/`verify`. Nếu `CheckoutContractIT` chạy bằng Failsafe nhưng bạn **chỉ cấu hình systemPropertyVariables ở Surefire**, các properties có thể **không đến JVM Failsafe**.

Cần truyền cùng giá trị cho Failsafe nếu integration test chạy ở đó:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <systemPropertyVariables>
            <spring.cloud.contract.stubrunner.ids>${inventory.stub.id}</spring.cloud.contract.stubrunner.ids>
            <spring.cloud.contract.stubrunner.stubsMode>${stubrunner.mode}</spring.cloud.contract.stubrunner.stubsMode>
            <spring.cloud.contract.stubrunner.repositoryRoot>${stubrunner.repository.root}</spring.cloud.contract.stubrunner.repositoryRoot>
        </systemPropertyVariables>
    </configuration>
</plugin>
~~~

Cũng cần dùng version Failsafe tương thích và đảm bảo các integration tests thực sự match quy ước tên. Chạy `mvn test` **không gọi phase Failsafe verify**; dùng `mvn verify` cho quy trình có Failsafe.

### 8.4. Kiểm chứng đường truyền bằng một assertion

Trong consumer test setup, có thể in **các giá trị không nhạy cảm** và fail nếu mode không đúng:

~~~java
String mode = System.getProperty(
    "spring.cloud.contract.stubrunner.stubsMode"
);

assertThat(mode).isEqualTo("REMOTE"); // Trong job contract-ci
~~~

Đây chỉ là một assertion cho **job CI**; nếu đặt cứng trong cùng test dùng cả local và CI sẽ làm local thất bại không cần thiết. Tốt hơn là logging/assertion được profile hóa hoặc một test cấu hình có expected mode truyền vào qua property tương ứng.

**Không in `repositoryRoot` nếu nó chứa credential trong URL**, không log username/password/token; chỉ ghi sanitized host hoặc mode/artifact version khi cần debug.


## 9. Lệnh chạy local và CI: cùng một contract, hai nguồn stub

Sau khi đã có POM và profiles đúng, developer có thể dùng:

~~~bash
# Trong producer: tạo tests, xác minh hợp đồng và cài stubs local
./mvnw -B clean install

# Trong consumer: lấy stubs từ Maven local repository
./mvnw -Pcontract-local clean verify
~~~

Lệnh `install` ở producer chỉ tạo `-stubs.jar` nếu Spring Cloud Contract Maven plugin đã được cấu hình và những goals/phase cần thiết thực sự chạy. Nếu Maven build thành công nhưng `inventory-producer-1.2.3-stubs.jar` không xuất hiện, cần kiểm tra cấu hình generation/packaging của producer.

CI thường đi theo trình tự:

~~~bash
# Producer CI: chỉ deploy nếu verify thành công và pipeline cho phép publish
./mvnw -B -ntp clean deploy

# Consumer CI: dùng artifact đã được publish từ repository chung
./mvnw -B -ntp -Pcontract-ci clean verify
~~~

`mvn deploy` chạy các phase trước đó trong Maven lifecycle, bao gồm `verify`, nếu không bị các skip flags hoặc các cấu hình khác làm vô hiệu hóa. **Không sử dụng cùng profile ID để ngầm quyết định publish artifact trên mọi loại job**: deploy nên là bước được pipeline cho phép sau quality gates, kèm credentials và repository policy.
Ví dụ producer dùng cấu hình Verifier chung của Mục 6 nên không cần `-Pcontract-ci`; nếu producer có profile CI riêng thì phải khai báo và kích hoạt nó ở **POM producer**, độc lập với `contract-ci` trong POM consumer. `mvn deploy` chạy các phase trước đó trong Maven lifecycle, bao gồm `verify`, nếu không bị skip flags hoặc cấu hình khác làm vô hiệu hóa. **Không sử dụng cùng profile ID để ngầm quyết định publish artifact trên mọi loại job**: deploy nên là bước được pipeline cho phép sau quality gates, kèm credentials và repository policy.

### 9.1. Nếu developer muốn kiểm tra nhanh hơn?

Có thể chạy một test đơn lẻ hoặc một module cụ thể khi đang sửa code:

~~~bash
./mvnw -Pcontract-local -Dtest=CheckoutConsumerContractTest test
~~~

Nhưng phải ghi rõ đây là **quick feedback**, không tương đương một pipeline `clean verify` đầy đủ. Khi test thực sự nằm ở Failsafe theo quy tắc `*IT`, cần dùng goal/phase của Failsafe tương ứng thay vì cố chạy bằng Surefire.

### 9.2. Không dùng profile để sửa contract

Một anti-pattern:

~~~text
contract-local  → response.quantity = 8
contract-ci     → response.quantity = 0
~~~

Nếu đây là cùng một use case và cùng hợp đồng với consumer, sự khác biệt này phá ý nghĩa verification. Thay vào đó, dùng **fixture có thể tái lập** trong producer base class, cô lập dữ liệu test hoặc định nghĩa hai tình huống có tên rõ (in-stock và out-of-stock) nếu consumer cần cả hai.

## 10. Cài/publish artifact: LOCAL khác REMOTE ở ranh giới nào?

| Bước | Local development | CI/release |
| --- | --- | --- |
| Nguồn contract | Groovy/YAML đã thống nhất | Cùng nguồn, cùng commit/revision |
| Producer test | Generated tests trên developer machine | Generated tests trên clean runner |
| Stub artifact | `...-stubs.jar` cài vào `~/.m2/repository` | `...-stubs.jar` publish lên repository chung |
| Consumer mode | `LOCAL` | `REMOTE` |
| Bản stub dùng | Tọa độ cụ thể đã cài local | Tọa độ cụ thể đã publish |
| Cổng WireMock | Dynamic hoặc riêng test | Dynamic; tránh tranh cổng giữa runners |
| Kết quả cần lưu | Test report và version artifact | Test report, artifact provenance, CI run ID |

### 10.1. Vì sao không dùng dấu + trong CI?

Stub Runner hỗ trợ Ivy notation:

~~~text
groupId:artifactId:version:classifier:port
~~~

Ví dụ:

~~~text
com.example:inventory-producer:1.2.3:stubs
~~~

Nếu bỏ version, resolver thường dùng `+` để chọn bản mới nhất. Khi CI lấy “latest”, một bản producer mới được publish có thể làm cùng một commit Checkout bắt đầu fail **mà không thay đổi code consumer**. Pin version trong profile/dependency management rồi nâng có chủ đích giúp tái lập và chẩn đoán.

### 10.2. Snapshot có thể thay đổi nội dung

Một artifact `1.2.4-SNAPSHOT` có thể được thay thế bằng build khác dưới cùng version. Trong `LOCAL`, người dùng còn có thể cài lại nội dung mới vào kho `.m2`. Nếu đang điều tra compatibility, nên ghi snapshot build metadata hoặc checksum, không chỉ tọa độ rút gọn.

Với release, nên coi tọa độ `1.2.3` là immutable. Đừng publish hai stub JAR khác nội dung dưới cùng release version rồi mong CI tái lập.

### 10.3. REMOTE có thể dùng cache

Chế độ `REMOTE` không đồng nghĩa “mỗi lần bắt buộc tải lại byte mới qua Internet”. Maven Resolver/Stub Runner có thể tận dụng cache và các quy tắc cập nhật metadata. Nếu artifact bị overwrite hoặc dùng version động, cache sẽ khiến một máy thấy mapping cũ và máy khác thấy bản mới. Giải pháp bền vững là **pin version + immutable artifact**, không phải xóa toàn bộ cache như cách chữa mặc định.

## 11. Repository và credentials: đặt đúng chỗ

Một câu hỏi thường gặp: có nên nhúng username/password vào `pom.xml` của profile CI?

**Không.** POM thường nằm trong Git; kể cả private repository, credential literal vẫn có thể bị lộ qua clone, artifact publishing hoặc build logs.

### 11.1. Maven settings.xml dành cho artifact resolution/deploy

Maven hỗ trợ `settings.xml` với `<servers>`, `<mirrors>`, `<profiles>` và `<activeProfiles>`. Ví dụ **rút gọn và không chứa credentials thật**:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>artifact-releases</id>
            <username>${env.CI_MAVEN_USER}</username>
            <password>${env.CI_MAVEN_PASSWORD}</password>
        </server>
    </servers>
</settings>
~~~

Trong producer `pom.xml`, nếu dùng `distributionManagement`:

~~~xml
<distributionManagement>
    <repository>
        <id>artifact-releases</id>
        <url>https://repo.example.test/repository/maven-releases/</url>
    </repository>
</distributionManagement>
~~~

**`<id>` phải khớp** để Maven deploy plugin tìm được cấu hình server thích hợp. Trong CI, dùng file settings được tạo hoặc inject bằng secret store, không commit bản chứa giá trị thật. Đừng ghi credential vào dòng lệnh `-Dpassword=...` dễ bị lộ trong process list/logs.

### 11.2. Cẩn thận: Maven Resolver credentials và Stub Runner credentials

Trong consumer test JVM, Stub Runner có thể dùng resolver/configuration riêng và hỗ trợ các properties `spring.cloud.contract.stubrunner.username`, `password`, `repositoryRoot`. Đừng mặc định credentials của Maven deploy sẽ **tự động** được mọi cách cấu hình Stub Runner đọc.

Nếu repository cần auth, xác minh đúng cơ chế mà phiên bản Spring Cloud Contract đang dùng hỗ trợ. Có thể inject:

~~~text
SPRING_CLOUD_CONTRACT_STUBRUNNER_USERNAME
SPRING_CLOUD_CONTRACT_STUBRUNNER_PASSWORD
~~~

vào môi trường của **process chạy consumer tests** nếu Spring property binding của dự án nhận các biến này. Ngoài ra có thể cấu hình resolver/server ID theo tài liệu version tương ứng. Không log giá trị secret.

Phân biệt:

- Maven `settings.xml`: cấu hình Maven artifact resolution/publishing.
- Stub Runner `repositoryRoot`: URL để tìm stub JAR tại runtime test.
- `ids`: tọa độ **stub artifact**.
- `@StubRunnerPort`: cổng của **WireMock server** sau khi artifact đã được tải.

### 11.3. Không để profile local yêu cầu secret CI

Profile `contract-local` nên hoạt động với local artifacts đã được cài mà không yêu cầu CI repository token. Nếu local profile vẫn thử dùng URL remote hoặc biến secret CI, kiểm tra các giá trị đến từ parent POM, Maven settings, environment hoặc annotation Spring đang override.

## 12. External contracts ở producer: contractsMode không phải stubsMode

Có dự án lưu hợp đồng trong **repository chung** thay vì `src/test/resources/contracts` của producer. Khi đó Spring Cloud Contract Maven plugin có thể dùng:

- `contractDependency`: artifact chứa contract definitions.
- `contractsMode`: cách phân giải artifact contracts (ví dụ `LOCAL` hoặc `REMOTE`).
- `contractsRepositoryUrl`: URL chứa contract artifact nếu cần.
- `contractsPath`: đường dẫn con có contracts trong JAR.

Ví dụ khung cấu hình:

~~~xml
<configuration>
    <contractsMode>${producer.contracts.mode}</contractsMode>
    <contractsRepositoryUrl>${producer.contracts.repository}</contractsRepositoryUrl>
    <contractDependency>
        <groupId>com.example</groupId>
        <artifactId>shared-inventory-contracts</artifactId>
        <version>1.2.3</version>
    </contractDependency>
    <contractsPath>/</contractsPath>
    <testFramework>JUNIT5</testFramework>
    <testMode>MOCKMVC</testMode>
    <baseClassForTests>com.example.inventory.contract.ContractVerifierBase</baseClassForTests>
</configuration>
~~~

Profile local có thể gán `producer.contracts.mode=LOCAL`; CI có thể gán `REMOTE` và URL repository. **Chỉ áp dụng ví dụ này khi producer thực sự lấy contracts từ external artifact**. Nếu contracts đã nằm trong source producer, không cần thêm external dependency chỉ vì muốn dùng Maven profiles.

Đặc biệt không được nhầm:

| Property | Chủ thể | Artifact được lấy |
| --- | --- | --- |
| Verifier `contractsMode` | Maven plugin **producer** | JAR chứa Groovy/YAML contracts |
| Stub Runner `stubsMode` | Runtime test **consumer** | JAR chứa WireMock/message stubs |

Một producer có thể dùng contracts local nhưng consumer dùng stubs remote, hoặc ngược lại. Hai quyết định độc lập.

### 12.1. Cùng nguồn contract khi chạy CI

Nếu producer tải contracts từ một artifact bên ngoài, hãy pin **contract artifact version** hoặc commit/revision rõ ràng. Đừng để `contractsMode=REMOTE` cùng version động tạo ra generated tests khác nhau giữa hai lần chạy. Khi contract repo cập nhật, hãy để CI fail đúng mức khi producer chưa đáp ứng thay đổi.

## 13. Tránh CI xanh giả do skip tests

Maven có nhiều cơ chế bỏ qua test; chúng **không tương đương nhau**:

| Cấu hình/lệnh | Tác động chính | Nguy cơ với contract |
| --- | --- | --- |
| `-DskipTests` | Thường bỏ chạy Surefire tests, vẫn có thể compile test | Generated producer tests có thể không được chạy |
| `-Dmaven.test.skip=true` | Bỏ qua biên dịch/chạy tests, một số plugin cũng kiểm tra flag này | Contract Verifier generation/execution có thể bị skip |
| `-Dspring.cloud.contract.verifier.skip=true` | Yêu cầu bỏ qua hoạt động Spring Cloud Contract Verifier plugin | Có thể không sinh tests/stubs |
| `-DskipITs` | Bỏ chạy integration tests do Failsafe quản lý | Consumer `*IT` có thể bị bỏ qua |
| `failOnNoTests=false` của Surefire | Cho phép một số trường hợp không có tests | CI có thể báo xanh dù thiếu bài test mong đợi |
| `failOnNoStubs=false` của Stub Runner | Có thể không fail khi không tìm thấy stubs | Consumer test có thể chạy mà thiếu dependency cần thiết |

Điểm tinh tế: Maven plugin version khác nhau có thể xử lý từng skip flag ở những phase khác nhau. Theo mã plugin Spring Cloud Contract, `generateTests` xem xét `spring.cloud.contract.verifier.skip` và `maven.test.skip`. Vì vậy **đừng đoán** rằng `-DskipTests` luôn ảnh hưởng giống `-Dmaven.test.skip`.

### 13.1. Vì sao chỉ kiểm tra BUILD SUCCESS chưa đủ?

Một pipeline có thể:

~~~text
[INFO] BUILD SUCCESS
Tests run: 0
~~~

hoặc chạy vài unit tests khác nhưng **không chạy generated contract tests**. Khi đó kết luận “producer tương thích với consumer” là không có cơ sở.

Hãy kiểm tra riêng:

1. Có contracts ở nguồn dự kiến.
2. Plugin `generateTests` và `generateStubs` được thực thi.
3. Generated test sources thực sự được sinh.
4. Test runner phát hiện và **thực thi** generated test classes/methods.
5. Bằng chứng test results được CI thu thập.
6. Stub JAR đúng classifier/mappings được attach.
7. Artifact publish chỉ sau khi các bước cần thiết đều đạt.

### 13.2. failIfNoTests không thay cho kiểm tra contract count

Có thể bật `failIfNoTests` ở Surefire/Failsafe, nhưng nếu một vài unit tests thông thường vẫn chạy, build có thể đạt dù **generated contract tests bằng 0**.

Vì vậy cần kiểm tra **đúng nhóm generated tests** hoặc có kiểm tra số lượng contracts/test classes theo cấu hình project. Tên class generated phụ thuộc package/folder layout, nên không hard-code một pattern chung cho mọi dự án mà không đọc output build.

### 13.3. Nên fail-closed ở CI

Một job CI có mục tiêu producer verification cần fail khi:

- Không tìm thấy contracts bắt buộc.
- Generated tests không được chạy.
- Contract assertions không đạt.
- Không tạo được expected `-stubs.jar`.
- Repository deployment thất bại.
- Không xác minh được version artifact được phát hành.

Một job consumer contract test cần fail khi:

- Không resolve được stub artifact cần thiết.
- WireMock không load được mappings mong đợi.
- Consumer client không gọi được stub.
- Consumer behavior/assertions sai.
- Profile kích hoạt không đúng hoặc thiếu required properties.

## 14. Kiểm tra cấu hình hiệu lực bằng Maven Help Plugin

Khi nghi ngờ Maven profile không được bật, đừng đoán từ tên folder hoặc biến môi trường.

### 14.1. Profile nào đang active?

~~~bash
./mvnw -Pcontract-local help:active-profiles
./mvnw -Pcontract-ci help:active-profiles
~~~

Các lệnh này hiển thị active profiles trong Maven session. Nếu dự án dùng parent POM và `settings.xml`, output có thể gồm những profiles khác ngoài hai profile contract.

### 14.2. POM sau khi hợp nhất đã ra sao?

~~~bash
./mvnw -Pcontract-ci help:effective-pom
~~~

Output có thể rất dài; tìm `maven-surefire-plugin`, `maven-failsafe-plugin`, `spring-cloud-contract-maven-plugin` và các `stubrunner` properties. Trong môi trường nhạy cảm, **không publish toàn bộ effective POM ra log công khai**, vì configuration có thể chứa endpoint nội bộ hoặc dữ liệu nhạy cảm từ các nguồn khác.

### 14.3. Một property cụ thể có giá trị gì?

~~~bash
./mvnw -q -Pcontract-ci help:evaluate \
  -Dexpression=stubrunner.mode \
  -DforceStdout
~~~

Dự kiến `REMOTE`. Tương tự, ở local:

~~~bash
./mvnw -q -Pcontract-local help:evaluate \
  -Dexpression=stubrunner.mode \
  -DforceStdout
~~~

Dự kiến `LOCAL`.

Maven `help:evaluate` kiểm tra **Maven property**. Nó chưa chứng minh Surefire đã chuyển giá trị sang Spring test process; để xác minh bước tiếp theo, kiểm tra system properties từ JUnit test setup hoặc Spring `Environment` với giá trị **không nhạy cảm**.

### 14.4. Kiểm tra đúng profile Spring

Lệnh `-Pcontract-ci` **không tự bật** `spring.profiles.active=ci` trong Spring Boot. Nếu ứng dụng phụ thuộc `application-ci.yml`, phải kích hoạt Spring profile bằng cơ chế riêng, ví dụ:

~~~bash
./mvnw -Pcontract-ci -Dspring.profiles.active=ci verify
~~~

Đừng mặc định `application-ci.yml` được nạp chỉ vì Maven profile tên `contract-ci` đã được kích hoạt.

## 15. Cơ chế kích hoạt profile tự động: nên dùng khi nào?

Maven cho phép:

~~~xml
<profile>
    <id>contract-ci</id>
    <activation>
        <property>
            <name>env.CI</name>
            <value>true</value>
        </property>
    </activation>
    <properties>
        <stubrunner.mode>REMOTE</stubrunner.mode>
    </properties>
</profile>
~~~

Lợi ích: nhiều CI providers đặt biến môi trường `CI=true` nên profile có thể được bật tự động.

Nhưng cần nhớ:

- Biến `CI` có thể tồn tại với giá trị khác `true`, tùy môi trường.
- Developer có thể chạy trong IDE/container với `CI=true` ngoài ý muốn.
- `activeByDefault` profiles trong POM có thể bị vô hiệu hóa khi một profile khác được kích hoạt.
- Một profile ở parent POM/settings có thể làm thứ tự hợp nhất cấu hình phức tạp.
- Nếu cả local và CI profiles cùng active, property cuối cùng có thể không như mong đợi.

**Khuyến nghị cho quality gates:** Dù có automatic activation, CI vẫn nên ghi rõ profile mong đợi trong command và kiểm tra `help:active-profiles`/effective configuration ở bước chuẩn bị.

## 16. So sánh hai chiến lược tách cấu hình

### 16.1. Profile điều khiển system properties

~~~text
Maven -Pcontract-local / -Pcontract-ci
    → Maven properties
    → Surefire / Failsafe systemPropertyVariables
    → Java system properties
    → Spring Environment
    → Stub Runner
~~~

Ưu điểm:

- Đường truyền cấu hình có thể theo dõi rõ.
- Tất cả lựa chọn local/CI tập trung ở POM.
- Cùng JUnit test chạy ở hai môi trường.

Nhược điểm:

- Nếu test runner khác Surefire/Failsafe, cần bridge tương ứng.
- Property precedence có thể phức tạp khi annotation override.
- POM nhiều dòng XML dài và khó đọc nếu thêm nhiều dependencies.

### 16.2. Spring profiles và environment configuration riêng

Một cách khác: giữ Maven profile chỉ cho build/repository policy; Spring application test configuration có:

~~~yaml
# application-local.yml, minh họa
spring:
  cloud:
    contract:
      stubrunner:
        stubs-mode: LOCAL
        ids:
          - "com.example:inventory-producer:1.2.3:stubs"
~~~

~~~yaml
# application-ci.yml, minh họa
spring:
  cloud:
    contract:
      stubrunner:
        stubs-mode: REMOTE
        repository-root: https://repo.example.test/repository/maven-releases/
        ids:
          - "com.example:inventory-producer:1.2.3:stubs"
~~~

Ưu điểm: phù hợp hệ sinh thái Spring configuration, dễ dùng trong Boot apps và tests. Nhược điểm: cần đảm bảo `spring.profiles.active` hoặc `@ActiveProfiles` được đặt đúng; cùng tên profile Maven/Spring **không tạo liên kết tự động**.

Cả hai chiến lược đều hợp lệ nếu được kiểm chứng. **Tránh cấu hình đồng thời ở nhiều nơi với giá trị mâu thuẫn**. Nếu sử dụng cả hai, ghi rõ source of truth và precedence.

### 16.3. Maven resource filtering có cần không?

Maven có thể filter `application-*.yml` bằng placeholders từ POM, nhưng cách này dễ gây lỗi do Spring cũng dùng placeholders `${...}` và có thể vô tình thay thế sai chuỗi. Khi không thật sự cần build-time substitution, ưu tiên **runtime environment properties** hoặc Surefire bridge. Nếu phải filtering, định nghĩa delimiters/escaping rõ và kiểm tra generated resources trong build output.

## 17. Khi local xanh nhưng CI đỏ: bảng chẩn đoán

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Local Stub Runner chạy, CI không tìm thấy stub | Local có `.m2` nhưng CI dùng REMOTE thiếu artifact | Kiểm tra artifact đã publish, tọa độ và repositoryRoot |
| CI `401/403` khi lấy artifact | Thiếu repository credentials hoặc quyền | Kiểm tra CI secrets, server/repository config |
| CI dùng CLASSPATH dù đặt `contract-ci` | Maven property chưa đến JVM; annotation override | Kiểm tra Surefire/Failsafe bridge và Spring Environment |
| CI nhận body cũ | Dùng `+`, snapshot/cache hoặc artifact overwrite | Pin version và so checksum/mappings |
| Local `mvn test` đạt, CI `mvn verify` fail | Failsafe integration tests chỉ chạy ở verify | Chạy đúng lifecycle, kiểm tra test naming |
| CI build xanh nhưng contracts không được verify | Skip flags, generated tests không chạy | Kiểm tra test report và plugin goals |
| Generated test fail trên CI nhưng local pass | Fixture/timezone/database/concurrency khác | Cô lập test data và deterministic setup |
| WireMock trả 404 nhưng producer có route | Consumer request không match stub mapping | So method/path/header và bản artifact đang dùng |
| Maven profile đúng nhưng Spring profile sai | `-P` không bật `spring.profiles.active` | Kích hoạt Spring profile riêng |
| Port WireMock xung đột trên CI | Pin cùng port cho nhiều jobs | Để Stub Runner cấp port động và lấy qua annotation/API |
| Lỗi resolution sau khi đổi version | Artifact chưa được producer publish | Chạy publish gate, kiểm tra repository metadata |
| CI thiếu test dù có contract source | Test runner pattern/source directory không đúng | Kiểm tra generated test path, Surefire/Failsafe patterns |

### 17.1. Quy trình điều tra theo thứ tự

1. Xác nhận `-Pcontract-ci` có thật trong command CI.
2. Chạy `help:active-profiles` hoặc xem log Maven.
3. Kiểm tra `stubrunner.mode` và `inventory.stub.version` đã được nội suy.
4. Kiểm tra Java system properties mà JUnit test nhận được.
5. Xác nhận Stub Runner dùng REMOTE và repositoryRoot đúng.
6. Xác nhận artifact tồn tại, classifier đúng, mapping có nội dung kỳ vọng.
7. Xác nhận consumer gọi đúng WireMock URL/port.
8. Đối chiếu response với contract và client behavior assertions.
9. Nếu producer verification fail, điều tra fixture/test mode/generated assertions, không đổ lỗi mặc định cho repository.
10. Nếu artifact resolution fail, không vội sửa business contract.

## 18. Bài thực hành: chuyển Checkout từ local .m2 sang CI repository

### 18.1. Bối cảnh

Inventory Service (producer) cung cấp:

~~~http
GET /api/inventory/SKU-100 HTTP/1.1
Accept: application/json
~~~

Response:

~~~json
{
  "sku": "SKU-100",
  "available": true,
  "quantity": 8
}
~~~

Checkout Service (consumer) cần bảo đảm đơn yêu cầu `3` sản phẩm được chấp nhận khi quantity là `8`, và đơn yêu cầu `9` sản phẩm bị từ chối.

Producer có stub tọa độ:

~~~text
com.example:inventory-producer:1.2.3:stubs
~~~

### 18.2. Nhiệm vụ A — Tạo hai profiles

Trong POM consumer, định nghĩa:

- `contract-local`: `stubrunner.mode=LOCAL`.
- `contract-ci`: `stubrunner.mode=REMOTE`, có `stubrunner.repository.root`.
- `inventory.stub.version=1.2.3` dùng chung.

Dùng Surefire/Failsafe bridge để test JVM nhận `spring.cloud.contract.stubrunner.ids`, `stubsMode` và `repositoryRoot`.

**Câu hỏi:** Vì sao chỉ định nghĩa Maven property `stubrunner.mode` chưa chứng minh Stub Runner sẽ dùng đúng mode?

### 18.3. Nhiệm vụ B — Chạy local

Trong producer, bảo đảm generated tests đạt và stub JAR được cài local:

~~~bash
./mvnw -B clean install
~~~

Trong consumer:

~~~bash
./mvnw -Pcontract-local clean verify
~~~

Kiểm tra mode, version artifact, WireMock port và assertions của Checkout.

### 18.4. Nhiệm vụ C — Chạy CI giả lập

Giả sử repository chung có bản `1.2.3` đã được publish. Chạy:

~~~bash
./mvnw -B -ntp -Pcontract-ci clean verify
~~~

Không đưa username/password lên dòng lệnh. Nếu repository cần auth, dùng CI secrets và Maven/Stub Runner credentials theo cơ chế dự án.

Ghi lại:

- `help:active-profiles` cho `contract-ci`.
- Giá trị `stubrunner.mode` mong đợi `REMOTE`.
- Stub coordinates/version thật được resolve.
- Kết quả success/out-of-stock consumer tests.
- Test reports, không chỉ BUILD SUCCESS.

### 18.5. Nhiệm vụ D — Cố ý tạo hai lỗi

**Lỗi 1:** Chuyển `inventory.stub.version` sang `9.9.9` (chưa publish). Dự kiến consumer CI **thất bại ở artifact resolution**, không phải vì Checkout xử lý JSON sai.

**Lỗi 2:** Để đúng version nhưng sửa InventoryClient gọi `/api/inventories/SKU-100` (sai path). Dự kiến Stub Runner khởi động nhưng request không khớp WireMock mapping; consumer test phải fail.

Hai lỗi giúp luyện phân biệt **cấu hình repository** với **contract mismatch**.

### 18.6. Nhiệm vụ E — Chứng minh generated tests thực sự chạy

Trong producer, kiểm tra build có generated tests và các test reports tương ứng. Thử một thay đổi phá contract, chẳng hạn trả `quantity` là String `"8"` thay vì number `8`. Generated test phải phát hiện mismatch khi contract bảo vệ đúng kiểu.

Khôi phục code trước khi kết thúc bài tập. Không phát hành stub từ build có producer verification fail.

### 18.7. Nhiệm vụ F — Giải thích lựa chọn profile

Viết một đoạn ngắn trả lời:

1. Vì sao `LOCAL` thuận tiện cho phát triển nhưng dễ khác nhau giữa hai máy?
2. Vì sao `REMOTE` phù hợp CI tách repository?
3. Tại sao không dùng `activeByDefault` như bảo đảm CI luôn bật profile?
4. Vì sao không cho phép `-DskipTests` trong job contract verification?
5. Khi consumer `*IT` chạy qua Failsafe, cần cấu hình property bridge ở đâu?
6. Vì sao pin version stub giúp tái lập lỗi?
7. Các loại credentials cần được quản lý ở đâu?
8. Trong tình huống nào nên dùng Spring profile riêng thay vì điều khiển tất cả qua Maven?

## 19. Checklist trước khi merge/release

- [ ] `contract-local` và `contract-ci` có mục tiêu rõ, không trùng lặp vô cớ.
- [ ] Lệnh CI bật profile đúng bằng `-Pcontract-ci`.
- [ ] Maven profile và Spring profile không bị nhầm lẫn.
- [ ] Test runner JVM nhận đúng Stub Runner mode, IDs và repositoryRoot.
- [ ] Surefire hoặc Failsafe được cấu hình đúng với lớp test thực chạy.
- [ ] Producer Verifier plugin và test mode/base class nằm ở cấu hình nhất quán.
- [ ] Generated producer tests thực sự được sinh và chạy.
- [ ] Không bật `spring.cloud.contract.verifier.skip` hay skip tests trong job bắt buộc verify.
- [ ] Không có build xanh với 0 generated contract tests mà vẫn được đánh dấu verified.
- [ ] Stub JAR có đúng group/artifact/version/classifier/mappings.
- [ ] LOCAL: artifacts được cài đầy đủ trong local Maven repository.
- [ ] REMOTE: repository artifact và version đã publish tồn tại.
- [ ] Stub version được pin hoặc có chiến lược version động rõ ràng.
- [ ] Repository credentials nằm ngoài Git, được cấp bằng secrets/settings phù hợp.
- [ ] Test không log token, password hoặc URL có embedded credentials.
- [ ] Consumer code thật gọi WireMock và có assertions về business behavior.
- [ ] Những nhánh lỗi quan trọng (404/400/5xx) có test phù hợp.
- [ ] Port/dữ liệu test được cô lập khi CI chạy song song.
- [ ] Local và CI đều có hướng dẫn command/expected outcome dễ tái lập.
- [ ] Producer publish stub chỉ sau quality gates đạt.
- [ ] Các kiểm thử transaction, resilience, broker delivery ngoài contract có owner riêng.

## 20. Tài liệu tham khảo

- [Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html): `-P`, profile activation, `activeByDefault` và environment properties.
- [Maven — Settings Reference](https://maven.apache.org/settings.html): `settings.xml`, servers, profiles, repository credentials và mirrors.
- [Maven Surefire — Using System Properties](https://maven.apache.org/surefire/maven-surefire-plugin/examples/system-properties.html): `systemPropertyVariables` và cách truyền Maven properties vào JVM test.
- [Maven Failsafe — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/): lifecycle integration-test/verify cho `*IT`.
- [Spring Cloud Contract — Maven Project](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html): cấu hình Verifier plugin, `generateTests`, test mode/base class và external contracts.
- [Spring Cloud Contract — Maven Plugin Goals](https://docs.spring.io/spring-cloud-contract/docs/current/spring-cloud-contract-maven-plugin/plugin-info.html): `generateTests`, `generateStubs`, `convert` và các goals.
- [Spring Cloud Contract — Stub Runner Common Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-common.html): `ids`, `stubsMode`, `repositoryRoot`, classifier và port.
- [Spring Cloud Contract — Step-by-step CDC](https://docs.spring.io/spring-cloud-contract/reference/getting-started/cdc.html): producer verification, stub publishing và consumer testing.

**Ghi nhớ:** Maven profiles giúp tách **cách build và lấy stub** giữa local và CI, nhưng không tự biến tên profile thành cấu hình Spring Cloud Contract. Hãy đặt Verifier và các quy tắc hợp đồng quan trọng ở phần chung, dùng `contract-local`/`contract-ci` để chọn nguồn artifacts, truyền giá trị tới JVM test qua Surefire/Failsafe hoặc Spring configuration, pin version và giữ secrets ngoài POM. CI chỉ được tuyên bố kiểm thử hợp đồng thành công khi **generated producer tests và consumer behavior tests thực sự chạy**, stub đúng version và release gates đạt.
