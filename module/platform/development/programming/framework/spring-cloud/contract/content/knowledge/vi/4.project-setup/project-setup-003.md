# Phụ thuộc cần thiết cho producer và consumer

## Mục tiêu bài học

Trong chương **Thiết lập dự án**, bài học này hướng dẫn chọn và cấu hình các phụ thuộc cho hai phía của **Spring Cloud Contract**:

- **Producer**: dịch vụ cung cấp API HTTP hoặc phát thông điệp, chịu trách nhiệm đáp ứng hợp đồng đã thống nhất và chạy các kiểm thử được sinh từ Groovy/YAML DSL.
- **Consumer**: dịch vụ gọi API hoặc nhận thông điệp, kiểm tra logic tích hợp của mình với **stub** do producer công bố, thường thông qua **Spring Cloud Contract Stub Runner**.

Sau bài này, bạn sẽ phân biệt được dependency dùng khi chạy ứng dụng với dependency dùng cho kiểm thử; cấu hình cơ bản trên Maven và Gradle; hiểu cách quản lý phiên bản Spring Boot, Spring Cloud và Spring Cloud Contract; và đưa bước sinh test, phát hành stub, chạy consumer test vào CI.

> Các đoạn cấu hình dưới đây minh họa **dự án Spring Boot** đã có mã ứng dụng tương ứng. Phiên bản Spring Boot, Spring Cloud release train và Spring Cloud Contract phải được chọn tương thích với nhau. Bài học dùng ký hiệu phiên bản thay thế để tránh ghim một bộ phiên bản không còn phù hợp với dự án của bạn.

## 1. Hai phía cần những thành phần nào?

Xét ví dụ **Inventory Service** cung cấp API tồn kho và **Checkout Service** gọi API đó:

~~~mermaid
flowchart LR
    C["Checkout Service<br/>consumer"] -->|"GET /api/inventory/SKU-101"| P["Inventory Service<br/>producer"]
    K["Contract<br/>Groovy / YAML DSL"] --> G["Sinh contract test"]
    K --> S["Sinh HTTP stub"]
    G --> P
    S --> R["Stub Runner"]
    R --> T["Consumer integration test"]
    T --> C
~~~

Trong luồng kiểm thử, producer được kiểm chứng bằng **generated contract tests**; consumer được kiểm chứng bằng cách gọi một **stub HTTP** giả lập đúng hành vi đã mô tả trong hợp đồng. Hai luồng bổ sung cho nhau và không thay thế hoàn toàn kiểm thử tích hợp đầu cuối.

| Thành phần | Dùng ở đâu | Vai trò | Phạm vi phụ thuộc thường dùng |
|---|---|---|---|
| `spring-boot-starter-test` | Producer và consumer | JUnit, công cụ assertion và hỗ trợ Spring Boot Test | Maven `test` / Gradle `testImplementation` |
| `spring-cloud-starter-contract-verifier` | Producer | Hỗ trợ kiểm thử hợp đồng được sinh từ DSL | Maven `test` / Gradle `testImplementation` |
| `spring-cloud-contract-maven-plugin` | Producer dùng Maven | Sinh test và stub, tích hợp chúng vào vòng đời build | Maven **build plugin** |
| `org.springframework.cloud.contract` Gradle plugin | Producer dùng Gradle | Sinh test và đóng gói stub trong build | Gradle **plugin**, không phải dependency runtime |
| `spring-cloud-starter-contract-stub-runner` | Consumer | Tìm, tải và khởi chạy stub phục vụ test | Maven `test` / Gradle `testImplementation` |
| `spring-cloud-dependencies` BOM | Các module có dùng Spring Cloud | Quản lý phiên bản tương thích của các thư viện Spring Cloud | Maven `dependencyManagement` / Gradle `platform` hoặc dependency management |
| `spring-boot-starter-web` hoặc stack HTTP tương ứng | Producer HTTP; consumer nếu thực sự cần | Cung cấp HTTP server/client theo kiến trúc ứng dụng | Runtime/implementation, tùy nhu cầu |

**Nguyên tắc:** thư viện contract verifier và Stub Runner phục vụ **build/test**. Ứng dụng triển khai lên production thường **không cần** mang chúng dưới dạng dependency runtime. Riêng client HTTP thật của consumer (ví dụ `RestClient`, `WebClient` hoặc OpenFeign) vẫn cần dependency theo công nghệ mà ứng dụng đang dùng.

## 2. Đồng bộ phiên bản Spring Boot, Spring Cloud và Contract

Một lỗi thiết lập phổ biến là chọn ba phiên bản độc lập mà không xem bảng tương thích của Spring Cloud. Những thư viện có thể tải về thành công nhưng vẫn gặp lỗi khi khởi động test hoặc khi sinh test do thay đổi API của Spring Boot, Spring Framework, JUnit hoặc các thư viện liên quan.

Quy trình chọn phiên bản:

1. **Chốt phiên bản Spring Boot** của dự án producer và consumer.
2. **Chọn Spring Cloud release train** tương thích với phiên bản Boot đó, theo tài liệu/bảng tương thích của phiên bản bạn triển khai.
3. **Nhập BOM `spring-cloud-dependencies`** để các starter Spring Cloud dùng phiên bản do release train quản lý.
4. **Đặt phiên bản build plugin Spring Cloud Contract** khớp với dòng Spring Cloud Contract được BOM quản lý; BOM dành cho thư viện không tự quản lý phiên bản Maven/Gradle plugin.
5. **Kiểm tra phiên bản hiệu lực** trong build, nhất là khi nhiều module hoặc BOM khác cùng tham gia quản lý phụ thuộc.

Không lấy **số phiên bản release train** và gán trực tiếp làm **số phiên bản Maven plugin**. Ví dụ tên một release train Spring Cloud và phiên bản artifact Spring Cloud Contract không nhất thiết giống nhau.

### Cấu hình BOM chung cho Maven

Với dự án đã sử dụng Spring Boot parent hoặc Spring Boot BOM, có thể thêm cấu hình sau vào `pom.xml` của parent/root:

~~~xml
<properties>
    <!-- Thay bằng release train tương thích với Spring Boot của dự án -->
    <spring-cloud.version>REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>

    <!-- Thay bằng phiên bản Spring Cloud Contract phù hợp với BOM trên -->
    <spring-cloud-contract.version>REPLACE_WITH_MATCHING_CONTRACT_VERSION</spring-cloud-contract.version>
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

Hai giá trị bắt đầu bằng `REPLACE_WITH_` là **chỗ cần điền**, không phải version có thể tải từ Maven Repository. Nếu project đã import BOM trong parent, không cần import lại tại từng module. Trong `dependencyManagement`, BOM cung cấp phiên bản cho các starter nên thông thường không cần `<version>` trong mỗi dependency Spring Cloud.

**Maven plugin** vẫn phải có version được quản lý riêng; đặt `spring-cloud-contract.version` trong root và dùng nó cho plugin bên dưới.

### Cấu hình BOM chung cho Gradle

Ví dụ với Gradle Groovy DSL, khi sử dụng BOM qua cơ chế `platform`:

~~~groovy
ext {
    springCloudVersion = 'REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN'
}

dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    testImplementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
}
~~~

Đây là phần cấu hình dependency management, **chưa phải** toàn bộ `build.gradle`: project vẫn cần Spring Boot plugin, Java plugin, repository và các dependency ứng dụng thông thường.

Với multi-module, hãy bảo đảm module producer và consumer đều nhận BOM phù hợp; chỉ cấu hình `platform` ở module khác mà không áp dụng cho module hiện tại có thể làm test dependency mất phiên bản. Một số dự án thay thế `platform` bằng plugin `io.spring.dependency-management`; chọn một cơ chế nhất quán với build hiện tại.

## 3. Maven: phụ thuộc và plugin phía producer

Giả sử producer là ứng dụng Spring Boot MVC tên `inventory-producer`. Trong module producer, tối thiểu cần công nghệ phục vụ HTTP của ứng dụng, thư viện kiểm thử và **contract verifier**:

~~~xml
<dependencies>
    <!-- Dành cho API HTTP đồng bộ bằng Spring MVC -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- Dùng khi tạo/chạy contract test phía producer -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-contract-verifier</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Bổ sung Maven plugin để xử lý hợp đồng trong vòng đời build:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>${spring-cloud-contract.version}</version>
            <extensions>true</extensions>
            <configuration>
                <baseClassForTests>com.example.inventory.contract.ContractTestBase</baseClassForTests>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`baseClassForTests` là ví dụ đường dẫn đến **lớp test cơ sở do dự án tạo**. Lớp này cần dựng đúng môi trường kiểm thử HTTP và chuẩn bị dữ liệu giả lập hoặc mock service cần thiết để generated tests chạy ổn định. Không thêm cấu hình này rồi bỏ trống lớp tương ứng: generated tests có thể không compile hoặc không chạy được. Nếu dự án dùng quy tắc base class khác, điều chỉnh theo cấu trúc test đang dùng.

Thường lưu file hợp đồng ở:

~~~text
inventory-producer/
├── pom.xml
└── src/
    └── test/
        ├── java/
        │   └── com/example/inventory/contract/ContractTestBase.java
        └── resources/
            └── contracts/
                └── inventory/
                    └── shouldReturnStock.groovy
~~~

Ví dụ một contract Groovy tối thiểu:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Lay ton kho cua mot SKU da biet'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 12
        )
    }
}
~~~

Khi plugin được cấu hình đúng, quá trình build sẽ **sinh test từ hợp đồng**, chạy test với ứng dụng producer được dựng cho mục đích kiểm thử và **tạo stub** tương ứng. Các giá trị `SKU-101`, `true`, `12` là tình huống mẫu; với dữ liệu động, có thể dùng matcher của Spring Cloud Contract thay vì luôn so khớp nguyên văn.

**Chạy trên máy phát triển:**

~~~bash
./mvnw clean verify
~~~

Lệnh trên thực hiện các pha kiểm thử và đóng gói theo lifecycle đã cấu hình. Để producer phát hành artifact cùng stub vào Maven local và cho consumer chạy thử ở chế độ LOCAL, dùng:

~~~bash
./mvnw clean install
~~~

Một bản build producer được cấu hình đúng thường có artifact stub mang **classifier `stubs`**, chẳng hạn tọa độ `com.example:inventory-producer:1.0.0:stubs`. Cách đặt version và nơi đặt artifact phụ thuộc `groupId`, `artifactId`, `version` thực tế của dự án. Chỉ coi stub đủ tin cậy sau khi contract tests producer đã vượt qua.

## 4. Maven: phụ thuộc phía consumer

Consumer `checkout-consumer` cần thư viện HTTP client phù hợp với ứng dụng và dependency **Stub Runner** trong phạm vi test.

Ví dụ nếu dùng Spring Boot và đã có mã gọi Inventory Service:

~~~xml
<dependencies>
    <!-- Tùy client của ứng dụng; ở đây là ví dụ Spring Boot MVC -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-contract-stub-runner</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Consumer **không cần** `spring-cloud-starter-contract-verifier` chỉ để gọi stub bằng Stub Runner. Cũng không cần Spring Cloud Contract Maven plugin ở module consumer nếu consumer không phải bên sinh contract test/stub.

### Consumer lấy stub bằng cách nào?

Stub Runner sử dụng tọa độ artifact của producer để tìm bản stub. Một ví dụ cấu hình test của consumer:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest(properties = {
    "inventory.base-url=http://localhost:10000"
})
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.0.0:stubs:10000",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryClientContractTest {

    @Test
    void checkoutUnderstandsInventoryResponse() {
        // Gọi InventoryClient thật của consumer với
        // base URL đã trỏ về stub ở localhost:10000.
        // Assert logic xử lý response của consumer tại đây.
    }
}
~~~

Ý nghĩa của cấu hình:

- `ids` có dạng tổng quát `groupId:artifactId:version:classifier:port`; ở đây `stubs` là classifier và `10000` là cổng stub trong test.
- `LOCAL` tìm artifact stub trong Maven local repository của môi trường test. Vì vậy, cần **build và install producer trước** hoặc cung cấp sẵn artifact ở local repository.
- `inventory.base-url` chỉ là **tên property minh họa**: phải trùng với cấu hình thật mà `InventoryClient` đọc. Nếu client đang dùng URL cố định hoặc cấu hình khác, test chưa gọi vào stub.
- Nội dung trong `@Test` cố ý là vị trí cho assertion của **client thật**. Một bài test chỉ gọi trực tiếp stub và kiểm tra stub trả JSON đúng chưa chứng minh logic consumer xử lý đúng.

Trong CI, mỗi job có thể có Maven local repository riêng. Không thể giả định stub vừa được `mvn install` trong một job khác sẽ tự xuất hiện. Hoặc thiết kế job liên tiếp trong cùng workspace/repository, hoặc phát hành stub lên kho artifact mà consumer được cấp quyền truy cập.

### Khi cần tải stub từ artifact repository

Thay vì `LOCAL`, dùng chế độ lấy stub từ repository đã cấu hình (thường gọi là `REMOTE`). Đặt địa chỉ repository bằng cấu hình tương ứng của Stub Runner, ví dụ property `spring.cloud.contract.stubrunner.repositoryRoot`, và cấu hình quyền truy cập theo cơ chế bảo mật của hệ thống build.

Không đặt mật khẩu hoặc token trực tiếp trong `pom.xml`, test source hay file cấu hình commit lên Git. Nếu các dịch vụ thuộc nhiều nhóm khác nhau, kho artifact dùng chung cùng cơ chế version rõ ràng giúp các pipeline sử dụng đúng stub đã được kiểm chứng.

## 5. Gradle: thiết lập tương đương

Nếu dự án dùng Gradle Groovy DSL, producer cần Spring Cloud Contract **plugin** và verifier ở scope kiểm thử. Mẫu sau minh họa các phần cần có; giá trị phiên bản phải được thay bằng phiên bản tương thích đã chọn:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'REPLACE_WITH_BOOT_VERSION'
    id 'org.springframework.cloud.contract' version 'REPLACE_WITH_CONTRACT_PLUGIN_VERSION'
}

repositories {
    mavenCentral()
}

def springCloudVersion = 'REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN'

dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    testImplementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")

    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-verifier'
}

contracts {
    baseClassForTests = 'com.example.inventory.contract.ContractTestBase'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Gradle plugin cung cấp các task liên quan đến sinh contract test và stub. **Tên task và cách nối vào vòng đời build có thể thay đổi theo dòng plugin**; kiểm tra các task thực tế trong dự án và bảo đảm test được sinh thực sự chạy trước khi xuất bản stub.

Ở consumer Gradle, giả sử đã có `org.springframework.boot` và `java` plugin cùng cấu hình BOM tương thích:

~~~groovy
dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    testImplementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-stub-runner'
}
~~~

Với Gradle, `testImplementation` giữ Stub Runner và verifier khỏi runtime classpath của ứng dụng thông thường. Cũng như Maven, phải có đường lấy artifact stub và phải cấu hình client consumer gọi đúng cổng stub khi chạy test.

**Lưu ý về version plugin:** dòng `id 'org.springframework.cloud.contract' version '...'` yêu cầu version của Gradle plugin, không phải giá trị `springCloudVersion`. Không chỉ định cùng một số cho cả hai nếu chưa đối chiếu phiên bản trong release train.

## 6. Chọn phụ thuộc theo loại hợp đồng: HTTP hay messaging?

Spring Cloud Contract có thể mô tả **HTTP** bằng Groovy/YAML DSL và kiểm thử những tương tác **thông điệp**. Tuy nhiên, phụ thuộc nghiệp vụ khác nhau theo giao tiếp đang dùng.

| Loại giao tiếp | Producer cần thêm gì? | Consumer cần thêm gì? | Phần nào không đổi? |
|---|---|---|---|
| HTTP với Spring MVC | Starter web hoặc stack phục vụ HTTP tương ứng | HTTP client thực tế đang dùng | Contract verifier + plugin ở producer, Stub Runner ở consumer test |
| HTTP với WebFlux | Starter webflux và cấu hình test mode phù hợp | WebClient hoặc client phù hợp | Quản lý BOM, DSL, kiểm thử hai phía |
| HTTP qua OpenFeign | Producer vẫn dùng stack HTTP của mình | Dependency OpenFeign nếu ứng dụng chọn Feign | Stub Runner vẫn là dependency test của consumer |
| Messaging (Kafka/RabbitMQ, Spring Cloud Stream hoặc thư viện khác) | Phụ thuộc binder/broker hoặc thư viện messaging phù hợp và cấu hình contract test có khả năng kích hoạt/quan sát thông điệp | Thư viện nhận thông điệp phù hợp; môi trường test phải mô phỏng được đường nhận sự kiện | Tư duy producer/consumer, contract và yêu cầu kiểm chứng hành vi |

**Không thêm Kafka, RabbitMQ, Stream binder hoặc thư viện Rest Assured vào mọi module chỉ vì sử dụng Spring Cloud Contract.** Chỉ đưa những phụ thuộc cần cho loại tương tác và cách kiểm thử thực tế.

Với messaging, stub không nhất thiết là một HTTP server giống ví dụ ở trên. Cấu hình tạo và chạy test message, đích gửi/nhận, trigger và hạ tầng giả lập cần tương thích với cách ứng dụng phát/tiêu thụ sự kiện. Producer nên mô tả payload và header có ý nghĩa với consumer; các bảo đảm như thứ tự sự kiện, retry hay duplicate delivery cần kiểm tra riêng nếu nghiệp vụ phụ thuộc chúng.

## 7. Quy trình chạy thử từ producer tới consumer

Dưới đây là thứ tự hợp lý cho lần tích hợp đầu tiên của ví dụ HTTP:

~~~mermaid
sequenceDiagram
    participant Dev as Developer / CI
    participant Prod as Producer build
    participant Repo as Stub repository
    participant Cons as Consumer test
    Dev->>Prod: Cấu hình BOM, verifier và Contract plugin
    Dev->>Prod: Commit Groovy/YAML contracts
    Prod->>Prod: Sinh và chạy contract tests
    alt Test producer thành công
        Prod->>Repo: Đóng gói và phát hành artifact :stubs
        Repo-->>Cons: Lấy đúng phiên bản stub
        Cons->>Cons: Stub Runner khởi chạy stub
        Cons->>Cons: Chạy test với client thật của consumer
    else Test producer thất bại
        Prod-->>Dev: Báo lệch contract, dừng phát hành
    end
~~~

1. **Chuẩn bị producer:** có ứng dụng chạy được, test base class hợp lệ, BOM phù hợp, verifier và plugin sinh test/stub.
2. **Viết hợp đồng:** ví dụ `GET /api/inventory/SKU-101` trả `200` với JSON hoặc trường hợp `404` cho SKU không tồn tại.
3. **Chạy producer tests:** kiểm tra generated tests được biên dịch, thực thi và kiểm chứng implementation đúng như hợp đồng.
4. **Đóng gói stub:** phát hành stub cùng version của producer. Khi thử trên máy, Maven có thể dùng `./mvnw clean install`; trên CI phát hành vào repository phù hợp.
5. **Chuẩn bị consumer:** thêm Stub Runner test dependency, chỉ định chính xác artifact và version, chuyển base URL của client sang stub.
6. **Chạy consumer tests:** kiểm tra consumer gửi request và xử lý response thành công, không có dữ liệu, lỗi hay những hành vi mà consumer thực sự phụ thuộc.
7. **Đưa vào CI:** đặt kiểm thử producer trước bước phát hành stub; pipeline consumer dùng phiên bản stub đã xác thực, tránh vô tình sử dụng bản cũ.

Nếu sử dụng `+` hoặc một dải phiên bản trong tọa độ stub, cần hiểu chính sách phân giải phiên bản và tính tái lập của CI. Với build yêu cầu reproducible, **ghim bản stub cụ thể** thường giúp dễ truy ra vì sao một lần chạy thành công hoặc thất bại.

## 8. Các lỗi dependency hay gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Plugin Maven/Gradle không được tìm thấy | Sai plugin id, group/artifact hoặc version; repository plugin thiếu | Kiểm tra tọa độ plugin, version và repository được cho phép |
| `NoClassDefFoundError`, `NoSuchMethodError` khi sinh/chạy test | Xung đột hoặc lệch phiên bản Boot/Cloud/Contract | Kiểm tra dependency graph, BOM, version plugin và override |
| Generated tests không xuất hiện | Chưa áp dụng plugin, sai vị trí contract, task/goal chưa chạy | Xem log build, đường dẫn contract và các task/goal được cấu hình |
| Generated tests có nhưng không compile | Thiếu test base class, import hoặc test dependency | Kiểm tra tên class, package, test framework và test scope |
| Producer contract test thất bại dù endpoint có tồn tại | Dữ liệu test, status, header, body hoặc matcher không khớp | So sánh chính request/response mà test được sinh đang kiểm tra |
| Stub Runner không tìm thấy `:stubs` | Producer chưa xuất bản stub, sai `groupId`/`artifactId`/version/classifier, sai chế độ LOCAL/REMOTE | Kiểm tra tọa độ artifact và repository thực tế |
| Consumer test gọi producer thật | URL client chưa chuyển sang cổng stub | Cấu hình base URL của client theo cổng Stub Runner |
| Test consumer xanh nhưng triển khai thật lỗi | Stub cũ; producer chưa chạy generated tests; thiếu tình huống hợp đồng | Đồng bộ phiên bản, kiểm tra cả hai phía và bổ sung nhánh cần thiết |
| Bản build production mang theo dependency kiểm thử | Đặt verifier hoặc Stub Runner ở scope runtime/implementation | Chuyển về `test` / `testImplementation` |

Với Maven, các lệnh chẩn đoán thường hữu ích là:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Với Gradle:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew tasks --all
~~~

Đây là những lệnh **tham khảo để người học tự chạy** trong dự án; không phải điều kiện tự động chứng minh mọi contract hoặc mọi phiên bản đều đúng. Cần đọc các dependency và task thực tế được giải quyết, đặc biệt khi có nhiều BOM, plugin hoặc cấu hình test tùy chỉnh.

## 9. Thực hành: xác định cấu hình còn thiếu

Một nhóm đã có producer Spring Boot, endpoint `GET /api/inventory/{sku}` hoạt động khi chạy bằng tay. Họ thêm một file `shouldReturnStock.groovy` vào `src/test/resources/contracts`, rồi phát hiện:

- Lệnh `./mvnw test` không tạo generated contract test;
- consumer thêm `spring-cloud-starter-contract-verifier` nhưng không chạy được stub;
- pipeline consumer đang lấy artifact version cũ;
- producer trả sai kiểu `quantity` nhưng chưa có bước nào báo lỗi.

Hãy đối chiếu với các phần đã học:

1. **Producer thiếu gì?** Kiểm tra Spring Cloud Contract Maven plugin và cách tích hợp lifecycle, test verifier, base class và cấu hình test. Chỉ có file Groovy không bảo đảm test được sinh và chạy.
2. **Consumer nên thêm gì?** `spring-cloud-starter-contract-stub-runner` ở scope test; dùng một stub artifact do producer xuất bản, rồi viết test gọi client thật.
3. **CI cần thay gì?** Kiểm tra generated tests trước khi phát hành stub; consumer dùng đúng tọa độ và phiên bản stub đã qua kiểm chứng.
4. **Phát hiện đổi kiểu `quantity` bằng cách nào?** Định nghĩa kiểu trong contract/matcher phù hợp; producer test phải kiểm tra response chứa số theo thỏa thuận, còn consumer test với stub tương ứng kiểm tra khả năng giải mã và xử lý của client.

### Tự kiểm tra

- Vì sao producer cần **plugin sinh test** nhưng consumer chủ yếu cần **Stub Runner**?
- Vì sao dependency `spring-cloud-starter-contract-verifier` thường ở scope `test`?
- BOM Spring Cloud có tự chọn version của Maven/Gradle Contract plugin không?
- Vì sao `LOCAL` không thể tự tìm stub nếu producer chưa cài đặt artifact ở môi trường đó?
- Nếu hai pipeline đều xanh nhưng dùng hai version stub khác nhau, còn rủi ro nào?

## Ghi nhớ

Để tích hợp **Spring Cloud Contract**, cần ghép đúng ba phần: **phiên bản tương thích**, **công cụ producer sinh và chạy test rồi phát hành stub**, và **consumer dùng Stub Runner với đúng bản stub để kiểm thử client thật**. Phân tách dependency runtime với test dependency giúp build gọn và rõ trách nhiệm. Khi CI thực thi chuỗi kiểm tra theo đúng thứ tự và quản lý version stub nhất quán, các thay đổi API hoặc thông điệp không tương thích sẽ được phát hiện sớm hơn.
