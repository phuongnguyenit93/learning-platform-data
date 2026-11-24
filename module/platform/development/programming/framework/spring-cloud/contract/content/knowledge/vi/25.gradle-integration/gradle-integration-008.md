# Quy trình nhiều module producer và consumer

## Mục tiêu học tập

Khi sử dụng **Spring Cloud Contract**, một dịch vụ **producer** định nghĩa các hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**. Gradle plugin có thể sinh **producer contract tests** để xác nhận implementation tuân thủ hợp đồng, đồng thời tạo **stub artifact** cho **consumer** dùng với **Stub Runner**. Trong một dự án có nhiều Gradle module, thử thách lớn nhất không chỉ là khai báo dependency mà là **đảm bảo các bước sinh test, kiểm chứng producer, đóng gói stub và kiểm tra consumer được chạy đúng thứ tự, đúng phiên bản**.

Bài thuộc chương **Tích hợp Gradle**, tập trung vào mô hình nhiều module trong cùng một Gradle multi-project build và cách chuyển mô hình ấy sang CI.

Sau bài học, bạn sẽ có thể:

- Thiết kế cấu trúc `settings.gradle` cho hai module `inventory-producer` và `checkout-consumer`, mỗi module có trách nhiệm riêng.
- Cấu hình Spring Cloud Contract Gradle plugin **ở module producer**, không áp dụng plugin verifier đại trà vào mọi consumer.
- Phân biệt thư mục `src/contractTest/resources/contracts`, source set `contractTest` và các task `generateContractTests`, `contractTest`, `generateClientStubs`, `verifierStubsJar`.
- Công bố một stub JAR có **classifier `stubs`** bằng `maven-publish`, chỉ sau khi producer tests đạt.
- Cho consumer dùng `@AutoConfigureStubRunner` và client HTTP thật, với stub đúng group/artifact/version.
- Sắp xếp task dependencies hoặc pipeline CI để consumer test không chạy trước khi có candidate stub.
- Tránh **circular dependency**, artifact cũ trong cache Maven, Gradle test-cache xanh giả và xuất bản stub khi producer test thất bại.
- Phân biệt bảo đảm của contract testing và những tích hợp DB, broker hoặc network cần kiểm thử bổ sung.

> **Quy tắc quan trọng:** producer phải chứng minh mình thực hiện đúng hợp đồng trước khi một stub được phát hành như một giao diện đã xác nhận; consumer phải chạy với chính phiên bản stub của thay đổi cần kiểm tra.

## 1. Bài toán: hai module trong một kho mã

Giả sử một hệ thống đặt hàng có:

- **Inventory Service**: producer của `GET /api/inventory/{sku}`.
- **Checkout Service**: consumer gọi Inventory để kiểm tra tồn kho.

Inventory công bố:

~~~http
GET /api/inventory/SKU-101 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sku": "SKU-101",
  "available": true,
  "quantity": 8
}
~~~

Checkout cần một HTTP client tạo request đúng và đọc response JSON với `quantity` là **number**, `available` là **boolean**.

Nếu hai dịch vụ đang phát triển chung một repository, bạn có thể muốn:

1. Thay đổi contract/implementation trong `inventory-producer`.
2. Chạy generated producer tests.
3. Đóng gói stub JAR của Inventory từ contract đó.
4. Cho `checkout-consumer` dùng stub để kiểm tra HTTP client và logic nghiệp vụ.
5. Chặn merge hoặc publish nếu một phía thất bại.

Một Gradle multi-project build hỗ trợ điều phối các bước ấy, **nhưng không tự biến project dependency thành Spring Cloud Contract stub**. Phải thiết kế rõ luồng artifact và kiểm thử.

### Bản đồ trách nhiệm

~~~mermaid
flowchart TD
    R["Gradle root project"] --> P[":inventory-producer"]
    R --> C[":checkout-consumer"]
    P --> D["Groovy/YAML DSL"]
    D --> T["Generated contract tests"]
    T --> V{"Producer implementation PASS?"}
    V -->|Không| X["Chặn publish / consumer gate"]
    V -->|Có| J["verifierStubsJar (:stubs)"]
    J --> M["Maven local hoặc artifact repository"]
    M --> S["Stub Runner trong consumer tests"]
    S --> H["HTTP client thật của Checkout"]
    H --> A["Assertion consumer"]
~~~

**Không cần** để `checkout-consumer` phụ thuộc trực tiếp vào runtime implementation của `inventory-producer`. Consumer nên phụ thuộc vào **hợp đồng giao tiếp** và stub ở phạm vi test, để việc build/triển khai của hai dịch vụ không bị nối cứng.

## 2. Ba kiểu dependency cần phân biệt

| Loại | Ví dụ | Có nên dùng? |
|---|---|---|
| **Gradle project dependency** | `implementation project(':inventory-producer')` | Thường **không** cho consumer microservice; nó kéo mã producer vào compile/runtime |
| **Artifact stub theo tọa độ** | `com.example:inventory-producer:1.2.0-rc.1:stubs` | **Có**, cho Stub Runner tại thời gian chạy test |
| **Shared API/schema module** | `implementation project(':inventory-api')` | Có thể cân nhắc khi dùng chung model theo chủ đích; không thay thế contract test |

Điểm khác biệt lớn là một `implementation project(':inventory-producer')` làm Gradle biên dịch và đưa thư viện producer vào classpath của consumer. Trong kiến trúc microservice, Checkout không nên gọi class nội bộ Inventory trực tiếp chỉ để test HTTP.

Còn Stub Runner cần **JAR chứa mappings/contract**, không phải JAR ứng dụng. Nếu producer xuất bản hai artifact:

~~~text
com.example:inventory-producer:1.2.0-rc.1
com.example:inventory-producer:1.2.0-rc.1:stubs
~~~

thì artifact có classifier `stubs` mới là thứ cần nạp cho Stub Runner. Artifact chính có thể là `jar`/`bootJar` phục vụ chạy ứng dụng, tùy cách package.

## 3. Tổ chức Gradle multi-project

Một bố cục tham khảo:

~~~text
commerce-contract-demo/
├── settings.gradle
├── build.gradle
├── gradle.properties
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── inventory-producer/
│   ├── build.gradle
│   ├── src/main/java/com/example/inventory/...
│   └── src/contractTest/
│       ├── java/com/example/inventory/contracts/InventoryContractBase.java
│       └── resources/contracts/inventory/stockAvailable.groovy
└── checkout-consumer/
    ├── build.gradle
    ├── src/main/java/com/example/checkout/...
    └── src/test/java/com/example/checkout/InventoryConsumerContractTest.java
~~~

`settings.gradle` ở root:

~~~groovy
rootProject.name = 'commerce-contract-demo'

include 'inventory-producer'
include 'checkout-consumer'
~~~

Đây là **hai Gradle subproject**, không phải hai biến thể source set trong cùng một module. Gradle nhận diện task theo đường dẫn:

~~~text
:inventory-producer:contractTest
:inventory-producer:verifierStubsJar
:checkout-consumer:test
~~~

Đường dẫn task cho phép CI gọi đúng module, tránh chạy mọi test vô tình hoặc bỏ sót bước bắt buộc.

### Tập trung phiên bản plugin ở root

Đối với một dự án thật, hãy quản lý các phiên bản Spring Boot, Spring Cloud Contract và Gradle tương thích. Ví dụ `settings.gradle` có thể khai báo plugin versions (cần thay các placeholder trước khi dùng):

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
    plugins {
        id 'org.springframework.boot' version 'REPLACE_BOOT_VERSION'
        id 'io.spring.dependency-management' version 'REPLACE_DEP_MGMT_VERSION'
        id 'org.springframework.cloud.contract' version 'REPLACE_SCC_VERSION'
    }
}

rootProject.name = 'commerce-contract-demo'
include 'inventory-producer', 'checkout-consumer'
~~~

Đoạn `settings.gradle` trên **thay thế cho snippet settings ngắn phía trên** khi bạn muốn quản lý phiên bản tập trung; không cần khai báo `include` hai lần. Các chuỗi `REPLACE_...` là placeholder, không phải version có thể tải về.

Root `build.gradle` có thể dùng cho thông tin tọa độ chung:

~~~groovy
allprojects {
    group = 'com.example'
    version = providers.gradleProperty('releaseVersion')
        .orElse('1.2.0-rc.1')
        .get()

    repositories {
        mavenCentral()
    }
}
~~~

`gradle.properties` minh họa:

~~~properties
releaseVersion=1.2.0-rc.1
~~~

**Cần lưu ý:** vì version Gradle project được chia sẻ trong ví dụ, cả producer và consumer có cùng project version. Điều đó **không** biến chúng thành cùng một artifact. Tọa độ đầy đủ vẫn khác ở `artifactId`.

Không đặt credentials cho repository publish hoặc token vào `gradle.properties` đã commit. Sử dụng credentials do CI/secret manager cấp tại bước được phép phát hành.

## 4. Producer giữ contract trong source set riêng

Với Spring Cloud Contract Gradle plugin từ dòng 3.x trở lên, thư mục convention được tài liệu mô tả là:

~~~text
inventory-producer/
└── src/contractTest/
    ├── resources/contracts/
    │   └── inventory/stockAvailable.groovy
    └── java/
        └── com/example/inventory/contracts/InventoryContractBase.java
~~~

**Đây là điểm khác biệt thường gặp so với ví dụ Maven.** Gradle plugin hiện đại dùng source set `contractTest`; đường dẫn `src/test/resources/contracts` xuất hiện trong các tài liệu cũ và là đường dẫn chuyển tiếp không nên mặc định làm chuẩn mới.

Một Groovy DSL đơn giản:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Ton kho SKU-101 con 8 san pham'

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

Nếu thích YAML DSL, có thể dùng một file `stockAvailable.yml` thay thế:

~~~yaml
description: 'Ton kho SKU-101 con 8 san pham'
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

**Chỉ chọn một phiên bản hợp đồng** cho cùng request/response khi đưa vào build; hai bản ở đây nhằm minh họa Groovy và YAML.

### Không để consumer giữ bản copy hợp đồng riêng

Trong mô hình này, Inventory là chủ sở hữu contract HTTP. Checkout kiểm thử với **artifact stub sinh từ contract** chứ không tự chép `stockAvailable.groovy` sang module consumer rồi sửa độc lập.

Nếu tổ chức muốn contract do consumer đề xuất hoặc giữ trong repository riêng, Spring Cloud Contract cũng hỗ trợ tải contract từ Maven/SCM. Tuy nhiên đó là **một mô hình sở hữu và phân phối khác**: vẫn phải đảm bảo producer chạy generated tests trên chính contract được consumer đề xuất và phát hành artifact có version rõ ràng.

## 5. Cấu hình Gradle plugin ở module producer

Ví dụ `inventory-producer/build.gradle` (Groovy DSL, chú thích giải thích cách tổ chức):

~~~groovy
import org.gradle.api.publish.maven.tasks.PublishToMavenLocal
import org.gradle.api.publish.maven.tasks.PublishToMavenRepository

plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
    id 'org.springframework.cloud.contract'
    id 'maven-publish'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-verifier'
}

contracts {
    testFramework = 'JUNIT5'
    testMode = 'MockMvc'

    baseClassForTests =
        'com.example.inventory.contracts.InventoryContractBase'

    contractsDslDir = file('src/contractTest/resources/contracts')
}

tasks.named('contractTest', Test) {
    useJUnitPlatform()
}

publishing {
    publications {
        stubs(MavenPublication) {
            artifact tasks.named('verifierStubsJar')
        }
    }
}

// Với cả local và remote publication, gate bắt buộc
// phải chạy producer contract tests trước khi publish.
tasks.withType(PublishToMavenLocal).configureEach {
    dependsOn tasks.named('contractTest')
}

tasks.withType(PublishToMavenRepository).configureEach {
    dependsOn tasks.named('contractTest')
}
~~~

Ví dụ này giả định:

- Các plugin versions đã được cấu hình trong `pluginManagement`.
- Spring Cloud BOM hoặc dependency-management tương thích được dùng để quản lý version các dependencies; nếu chưa có, bạn phải bổ sung BOM/dependency constraints phù hợp.
- Plugin Gradle đã tạo task `contractTest` và `verifierStubsJar` theo tài liệu tương ứng.
- Project chỉ định đúng base class và ứng dụng producer có controller hoạt động.
- `maven-publish` tạo publication `stubs` mang group/version từ Gradle project, artifactId mặc định là `inventory-producer` và `verifierStubsJar` có classifier `stubs` theo convention plugin.

**Lưu ý:** ví dụ trên là **khung cấu hình kỹ thuật**, không phải một repository đã chạy xác nhận. Cú pháp/behavior có thể thay đổi theo phiên bản Gradle, Spring Boot và Spring Cloud Contract. Hãy xem `./gradlew :inventory-producer:tasks --all` và build log để xác nhận các task, source sets và publication trong dự án thực.

### Vì sao `maven-publish` cần cấu hình thủ công?

Tài liệu Spring Cloud Contract nêu rằng từ **3.0.0**, việc tự động publication stubs mặc định đã bị vô hiệu hóa. Vì vậy, chỉ áp dụng plugin Verifier **không có nghĩa** `publishToMavenLocal` hoặc `publish` chắc chắn sẽ chứa `*-stubs.jar`. Cần thêm artifact `verifierStubsJar` vào một `MavenPublication` của Gradle.

Trong ví dụ:

~~~groovy
publishing {
    publications {
        stubs(MavenPublication) {
            artifact tasks.named('verifierStubsJar')
        }
    }
}
~~~

là phần quan trọng để tạo Maven artifact:

~~~text
com.example:inventory-producer:1.2.0-rc.1:stubs
~~~

Sau khi cấu hình, kiểm tra file trong `inventory-producer/build/libs` và artifact được publish thật. Không suy rằng mọi jar có tên gần giống `stubs` là đúng classifier hoặc đúng layout.

### Tại sao phải gate publication task?

Task `verifierStubsJar` có thể tạo stub JAR từ DSL kể cả khi producer chưa chứng minh code chạy đúng. Nó **không phải synonym của `contractTest`**.

Hai rule:

~~~groovy
tasks.withType(PublishToMavenLocal).configureEach {
    dependsOn tasks.named('contractTest')
}

tasks.withType(PublishToMavenRepository).configureEach {
    dependsOn tasks.named('contractTest')
}
~~~

giúp các publication tasks cùng Gradle build **đợi `contractTest`**. Nhưng chúng không bảo vệ các đường upload JAR nằm **ngoài Gradle task graph**, ví dụ script shell tự đẩy file `build/libs/*-stubs.jar` lên một repository. CI phải chặn tất cả đường publish không qua gate.

Nếu dự án có test tích hợp quan trọng khác, quality gate có thể yêu cầu thêm `check` hoặc task tương ứng, chứ không chỉ `contractTest`.

## 6. Base test phía producer dựng implementation thật

Generated producer test cần một base class mà plugin có thể kế thừa. Trong chế độ `MockMvc`, base class thường khởi tạo controller thật và fake/mock dependency để tạo fixture xác định.

Ví dụ file `src/contractTest/java/com/example/inventory/contracts/InventoryContractBase.java`:

~~~java
package com.example.inventory.contracts;

import com.example.inventory.InventoryController;
import com.example.inventory.InventoryService;
import com.example.inventory.StockResponse;
import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;

import java.util.Optional;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

public abstract class InventoryContractBase {

    @BeforeEach
    protected void setUpContract() {
        InventoryService service = mock(InventoryService.class);

        when(service.findBySku("SKU-101"))
            .thenReturn(Optional.of(
                new StockResponse("SKU-101", true, 8)
            ));

        RestAssuredMockMvc.standaloneSetup(
            new InventoryController(service)
        );
    }
}
~~~

Đây là ví dụ với các class `InventoryController`, `InventoryService` và `StockResponse` **do project tạo**. Cần tự triển khai controller với `GET /api/inventory/{sku}`, dependency injection, JSON response và status tương ứng.

Quan trọng:

1. Generated test phải gọi **controller thực của producer**, không gọi vào stub HTTP tự trả JSON.
2. Fake service trả `8` nhằm tạo tình huống rõ ràng, nhưng test không chứng minh repository/database thật.
3. Nếu response lỗi phụ thuộc `@ControllerAdvice`, security, filter hoặc converter tùy chỉnh, `standaloneSetup` có thể chưa dựng toàn bộ cấu hình. Cân nhắc WebApplicationContext hoặc test qua HTTP server thật khi mục tiêu yêu cầu.
4. `@BeforeEach` tương ứng **JUnit 5**, vì trong Gradle plugin đặt `testFramework = 'JUNIT5'`.
5. Base class phải nằm trong source set có thể biên dịch/được generated contract tests sử dụng; **không đặt tùy tiện chỉ trong main source**.

### Ba bằng chứng cần đọc từ generated test

- Test có kế thừa `InventoryContractBase` không?
- Test có gửi `GET /api/inventory/SKU-101` và assert `200` + body đúng kiểu không?
- Test **được thực thi** trong `:inventory-producer:contractTest` chứ không chỉ được sinh vào `build/generated-test-sources`?

Các file sinh ở Gradle thường nằm trong vùng `inventory-producer/build/generated-test-sources/contractTest/java` hoặc đường dẫn mà plugin đang cấu hình. **Không sửa generated test trực tiếp**; sửa DSL, base class và sinh lại.

## 7. Những task Gradle quan trọng và mối quan hệ

| Task của module producer | Vai trò | Có phải bằng chứng producer đạt không? |
|---|---|---|
| `generateContractTests` | Sinh test source từ Groovy/YAML DSL | Không; test có thể chưa chạy |
| `contractTest` | Chạy generated contract tests | **Có**, nếu test được phát hiện và thực thi thật |
| `generateClientStubs` | Sinh HTTP WireMock mappings/stub definitions | Không |
| `verifierStubsJar` | Đóng gói stub artifact từ mappings/contracts | Không |
| `copyContracts` | Đưa contract source vào vùng đóng gói stub | Không |
| `publishStubsPublicationToMavenLocal` | Công bố publication `stubs` vào Maven local repository | Có điều kiện; chỉ khi đã được gate |
| `publishStubsPublicationTo...Repository` | Công bố publication `stubs` lên repository cấu hình | Có điều kiện; chỉ khi đã được gate |

Spring Cloud Contract Gradle plugin đã đăng ký các task liên quan; những đường dẫn output và quan hệ dependsOn chính xác có thể thay đổi theo phiên bản. **Không chỉ nhìn tên task để suy kết quả.**

### Thứ tự về mặt tin cậy

~~~mermaid
flowchart TD
    A["generateContractTests"] --> B["contractTest thực thi"]
    B --> C{"PASS và số test hợp lệ?"}
    C -->|Không| X["STOP: không công bố"]
    C -->|Có| D["generateClientStubs"]
    D --> E["verifierStubsJar"]
    E --> F["publishStubsPublicationToMavenLocal"]
    F --> G[":checkout-consumer:test"]
    G --> H{"Consumer PASS?"}
    H -->|Không| I["Chặn release, rà soát compatibility"]
    H -->|Có| J["Đủ điều kiện review/publish"]
~~~

**Đây là sơ đồ thứ tự *đảm bảo chất lượng*, không phải khẳng định các task Gradle phải chạy theo đúng thứ tự vật lý từng dòng.** Một Gradle build có thể tạo mappings/JAR trước khi chạy producer test, miễn là bước **công bố** không thể thực thi khi producer test fail.

### Lệnh chạy theo từng bước

Với Gradle wrapper tại root:

~~~bash
# 1. Xác nhận plugin và task hiện có của producer.
./gradlew :inventory-producer:tasks --all

# 2. Chạy generated producer contract tests.
./gradlew :inventory-producer:contractTest

# 3. Tạo JAR stub theo plugin.
./gradlew :inventory-producer:verifierStubsJar

# 4. Publish candidate vào Maven local, khi producer gate đạt.
./gradlew :inventory-producer:publishStubsPublicationToMavenLocal

# 5. Chạy consumer test dùng Stub Runner LOCAL.
./gradlew :checkout-consumer:test
~~~

Các lệnh là **hướng dẫn thực hành**, không phải các lệnh đã được chạy trong bài học này. Vì publication task đã được cấu hình `dependsOn contractTest`, bước 4 vẫn cần producer test đạt theo Gradle task graph; test đã chạy từ bước 2 có thể được coi là up-to-date nếu inputs/outputs không đổi.

**Không được** thêm `-x contractTest`, `-x test` hoặc các cách vô hiệu hóa gate vào release pipeline.

## 8. Consumer chỉ cần Stub Runner, không cần verifier plugin

Trong `checkout-consumer/build.gradle`, consumer cần dependency cho test:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-stub-runner'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

Chỉ module **producer** cần Gradle plugin `org.springframework.cloud.contract` để sinh/check producer tests và stubs theo contract nguồn. Consumer dùng **stub-runner test dependency** là đủ khi lấy artifact đã được tạo.

Không thêm:

~~~groovy
// ANTI-PATTERN cho microservice consumer chỉ cần HTTP:
implementation project(':inventory-producer')
~~~

vì điều đó nối mã implementation producer vào runtime của Checkout và không thay thế Stub Runner.

### Một HTTP client thật của consumer

Ví dụ class Java:

~~~java
package com.example.checkout.inventory;

import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

public class InventoryClient {

    private final RestClient http;

    public InventoryClient(RestClient.Builder builder, String baseUrl) {
        this.http = builder.baseUrl(baseUrl).build();
    }

    public StockView findBySku(String sku) {
        return http.get()
            .uri("/api/inventory/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .body(StockView.class);
    }
}
~~~

Kiểu response:

~~~java
package com.example.checkout.inventory;

public record StockView(
    String sku,
    boolean available,
    int quantity
) {}
~~~

`RestClient` cần Spring Framework 6.1+; nếu dự án dùng phiên bản cũ, có thể sử dụng `RestTemplate`, `WebClient` hoặc Feign và áp dụng cùng nguyên tắc cấu hình base URL. `record` cần Java hỗ trợ records.

Trong production, client có thể được tạo bằng một bean `@Configuration` sử dụng property `inventory.base-url`. Trong consumer test adapter, ta truyền URL do Stub Runner cung cấp để chắc chắn không gọi nhầm Inventory thật.

## 9. Consumer test dùng đúng cổng runtime của Stub Runner

Ví dụ `checkout-consumer/src/test/java/.../InventoryConsumerContractTest.java`:

~~~java
package com.example.checkout.inventory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerPort;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:1.2.0-rc.1:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryConsumerContractTest {

    @StubRunnerPort("inventory-producer")
    int inventoryStubPort;

    @Autowired
    RestClient.Builder restClientBuilder;

    @Test
    void readsStockFromStub() {
        assertThat(inventoryStubPort).isGreaterThan(0);

        InventoryClient client = new InventoryClient(
            restClientBuilder,
            "http://localhost:" + inventoryStubPort
        );

        StockView result = client.findBySku("SKU-101");

        assertThat(result.sku()).isEqualTo("SKU-101");
        assertThat(result.available()).isTrue();
        assertThat(result.quantity()).isEqualTo(8);
    }
}
~~~

Trong ví dụ này:

- `ids` chỉ định **group, artifact, version, classifier** và yêu cầu cổng động `:0`.
- `LOCAL` khiến Stub Runner tìm stub trong Maven local repository của **môi trường chạy test**.
- `@StubRunnerPort("inventory-producer")` trả cổng thực tế mà stub đang nghe.
- `InventoryClient` là **client thực** của consumer, chỉ thay địa chỉ producer.
- Assertion kiểm tra cả field và kiểu dữ liệu consumer cần.

Đây là **consumer HTTP adapter test**, chưa kiểm tra việc production bean đã được Spring wiring với `inventory.base-url` thế nào vì client được tạo trong test bằng constructor. Nếu muốn kiểm tra cả wiring, cần cấu hình base URL **trước khi bean được khởi tạo** (chẳng hạn dùng stub port cố định trong test profile), không sửa property trong `@BeforeEach` rồi kỳ vọng singleton bean tự dựng lại.

### Tránh dùng port 0 làm URL

Khi `ids` kết thúc bằng `:0`, **cổng thực không phải 0**. Không viết:

~~~java
String baseUrl = "http://localhost:0"; // Sai
~~~

Phải lấy `@StubRunnerPort` hoặc `StubFinder` của Stub Runner. Với nhiều producer, mỗi cổng/URL phải được tra theo đúng artifact.

### Vì sao test với stub chưa đủ để tin producer?

Stub trả response theo DSL, không gọi Inventory Service thật. Nếu producer code trả `"quantity":"8"` nhưng DSL mô tả `quantity: 8`, consumer vẫn có thể xanh khi gọi stub. Vì vậy **generated producer contract tests là gate bắt buộc trước khi phát hành stub**.

## 10. Kết nối task của hai module trong cùng Gradle build

Nếu đang chạy thử trên một máy/CI job, có thể đảm bảo consumer test chỉ bắt đầu sau khi producer đã publish candidate stub vào local Maven repository.

Trong `checkout-consumer/build.gradle`, có thể thêm:

~~~groovy
tasks.named('test', Test) {
    // Task publication chỉ tồn tại khi producer đã cấu hình
    // MavenPublication tên 'stubs' như mục 5.
    dependsOn ':inventory-producer:publishStubsPublicationToMavenLocal'
}
~~~

Khi gọi:

~~~bash
./gradlew :checkout-consumer:test
~~~

Gradle sẽ đi qua dependency của test, nghĩa là phải thực hiện **producer publication task** trước; publication task trong ví dụ lại phụ thuộc `contractTest`.

### Vì sao không để producer phụ thuộc consumer?

Không tạo cả hai quan hệ:

~~~text
:checkout-consumer:test
    dependsOn :inventory-producer:publishStubsPublicationToMavenLocal

:inventory-producer:contractTest
    dependsOn :checkout-consumer:test    # SAI
~~~

Quan hệ trên tạo **vòng tròn task dependency**. Gradle sẽ không thể hoàn thành task graph.

Quy tắc:

- Producer **cung cấp** contract và stub.
- Consumer **sử dụng** stub.
- Task **kiểm chứng producer** không phụ thuộc vào việc consumer test chạy.
- Quyết định **phát hành công khai** có thể đòi cả producer và consumer gates PASS, nhưng đó là dependency của **release pipeline**, không phải vòng lặp giữa source modules.

### Root orchestration task tùy chọn

Nếu nhóm muốn một lệnh dễ nhớ, root `build.gradle` có thể đăng ký:

~~~groovy
tasks.register('verifyProducerAndConsumer') {
    group = 'verification'
    description = 'Verify producer contracts then run consumer tests'
    dependsOn ':checkout-consumer:test'
}
~~~

Với cấu hình consumer `test.dependsOn(':inventory-producer:publishStubsPublicationToMavenLocal')` và producer publication gate ở trên, một lệnh:

~~~bash
./gradlew verifyProducerAndConsumer
~~~

sẽ đi theo task graph đã cấu hình. **Không cần gọi hai test ở hai project theo thứ tự ngẫu nhiên bằng nhiều lệnh shell không kiểm tra exit code**.

### Phân biệt Gradle task graph và artifact resolution

Một `dependsOn` chỉ điều phối **khi task được chạy**. Stub Runner `LOCAL` vẫn phải tìm được artifact tại tọa độ đúng trong Maven local repository.

Nếu publication bị đổi tên, classifier sai, version không khớp `ids`, hoặc Gradle publish vào một repository khác, consumer test vẫn không tải được stub dù task graph chạy đúng.

## 11. Vấn đề version và cache trong multi-module

Trong ví dụ:

~~~text
Producer project version:
  1.2.0-rc.1

Published stub coordinate:
  com.example:inventory-producer:1.2.0-rc.1:stubs

Consumer test annotation:
  ids = "com.example:inventory-producer:1.2.0-rc.1:stubs:0"
~~~

**Ba nơi phải chỉ cùng một phiên bản.** Nếu project version đổi nhưng annotation vẫn giữ `1.1.0`, Stub Runner có thể dùng stub cũ và test vẫn xanh. Đây là **false positive** nghiêm trọng: thay đổi producer đang được review không được consumer kiểm chứng.

### Truyền version bằng Gradle property

Có thể đặt:

~~~properties
# gradle.properties
releaseVersion=1.2.0-rc.1
~~~

Trong consumer, có thể truyền property này vào test JVM:

~~~groovy
tasks.named('test', Test) {
    systemProperty 'stub.version', project.version.toString()
}
~~~

Với Stub Runner annotation, cách đưa version động vào `ids` phụ thuộc cơ chế property resolution của Spring Test/Stub Runner ở phiên bản đang dùng. **Không tự khẳng định mọi annotation đều nội suy chuỗi `${stub.version}` theo cùng quy tắc**. Cách ít mơ hồ nhất trong bài học là dùng **một candidate version cố định** đã được kiểm tra giữa root project và test, sau đó nâng cấp cùng lúc.

Ở CI chuyên nghiệp, có thể tạo cấu hình test profile/annotation từ một **versioned property** được framework hỗ trợ hoặc dùng cơ chế cấu hình Stub Runner qua application properties. Điều quan trọng là **log version thực tế mà Stub Runner đã resolve**.

### Hai loại cache có thể làm test xanh giả

| Cache | Nguy cơ | Cách phòng |
|---|---|---|
| **Maven local `~/.m2/repository`** | Có stub cùng version nhưng từ build cũ | Dùng version duy nhất/digest và môi trường repository cô lập |
| **Gradle build cache / up-to-date checks** | Task consumer `test` được đánh dấu up-to-date khi artifact `LOCAL` bên ngoài task inputs đã đổi | Khai báo inputs phù hợp, tắt caching cho gate nhạy cảm hoặc ép chạy lại test ở CI |

Ví dụ, nếu bạn **ghi đè stub artifact cùng version trong Maven local** nhưng không thay đổi code/inputs của module Checkout, Gradle có thể coi `:checkout-consumer:test` là **UP-TO-DATE**. Khi đó CI không có bằng chứng consumer test vừa chạy với stub mới.

Có thể dùng:

~~~bash
./gradlew :checkout-consumer:test --rerun-tasks --no-build-cache
~~~

như một biện pháp bảo đảm test chạy lại khi đang debug hoặc kiểm chứng candidate. Về lâu dài, thiết kế tốt hơn là **version artifact bất biến** và khai báo đầu vào của task để Gradle nhận biết thay đổi.

### Không để nhiều job CI dùng chung local Maven cache mutable

Nếu hai PR cùng ghi đè `com.example:inventory-producer:1.2.0-SNAPSHOT:stubs` trong cùng `~/.m2`, consumer test của PR A có thể tải nhầm artifact của PR B. Cách an toàn hơn:

- Mỗi pipeline có **Maven local repository riêng**, hoặc
- Dùng **candidate version duy nhất theo commit/build ID**, hoặc
- Chuyển artifact từ job producer sang job consumer bằng CI artifact có checksum, hoặc
- Dùng staging repository có quyền/cách phân tách rõ ràng.

Không dùng `latest`/`+` trong consumer release gate nếu cần chứng minh **đúng candidate revision**.

## 12. Khi producer và consumer nằm trong hai repository riêng

Gradle multi-project demo giúp hình dung quy trình, nhưng microservices thực tế thường có **hai repository và hai pipeline**.

Điểm khác biệt: không thể dựa vào task Gradle `dependsOn ':inventory-producer:...'` khi producer không phải subproject trong cùng build.

Một pipeline điển hình:

~~~mermaid
sequenceDiagram
    participant PR as Producer PR
    participant PV as Producer CI
    participant SA as Stub candidate artifact
    participant CR as Consumer CI
    participant R as Release
    PR->>PV: Update code + Groovy/YAML contracts
    PV->>PV: Run generated producer tests
    alt Producer PASS
        PV->>SA: Package artifact with unique version
        SA->>CR: Provide stub via artifact transfer/staging
        CR->>CR: Stub Runner + real consumer tests
        alt Consumer PASS
            CR-->>R: Compatibility gate passed
        else Consumer FAIL
            CR-->>PR: Investigate breaking change
        end
    else Producer FAIL
        PV-->>PR: Stop, do not publish verified stub
    end
~~~

Ở trường hợp này, consumer có thể dùng `StubRunnerProperties.StubsMode.REMOTE` với Maven artifact repository, `LOCAL` nếu CI đã cài candidate vào repo riêng, hoặc `CLASSPATH` nếu stub được đóng gói trên test classpath.

### CI artifact khác release artifact

Khi producer test thành công, có thể tạo **candidate stub** để thử compatibility. Candidate này chưa cần được public như một bản release; nó có thể nằm trong kho artifact tạm hoặc CI job artifacts.

- **Candidate artifact:** phục vụ các job test, version/digest có thể truy vết.
- **Published/released stub:** được công bố sau khi các gate bắt buộc của tổ chức đều đạt.

Nếu consumer test được yêu cầu như một release gate, đừng publish release stub trước khi consumer test chạy; hãy chuyển candidate theo cơ chế staging/CI phù hợp.

### Bảo đảm cùng revision

Một báo cáo CI hữu ích:

~~~text
Producer source SHA: <commit-A>
Contracts SHA:       <commit-A>
Producer test count: 6 run / 6 passed
Candidate stub:      com.example:inventory-producer:1.2.0-rc.1:stubs
Candidate checksum:  <sha256>
Consumer source SHA: <commit-B>
Consumer test count: 4 run / 4 passed
Stub actually loaded: 1.2.0-rc.1
Decision: eligible for release review
~~~

Các giá trị trong `<...>` là placeholder cần lấy từ CI thật. Nếu consumer dùng nhầm artifact `1.1.0`, không được ghi “candidate compatible” chỉ vì test vẫn PASS.

## 13. Ví dụ tổ chức task trên CI cho cùng một Gradle repository

Một job Gradle CI tối giản có thể gọi:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

# Wrapper và các plugin đã cấu hình trong root + subprojects.
./gradlew :inventory-producer:contractTest

# Task này phải phụ thuộc producer test gate theo build.gradle.
./gradlew :inventory-producer:publishStubsPublicationToMavenLocal

# Kiểm tra consumer với candidate stub vừa cài.
./gradlew :checkout-consumer:test --rerun-tasks --no-build-cache
~~~

Đây là **một hướng dẫn script**, không phải artifact đang được thực thi trong bài học. `set -euo pipefail` giúp dừng khi một lệnh thất bại. Với PowerShell/Windows, cần kiểm tra exit code bằng cơ chế phù hợp, không sử dụng `&&` nếu đang chạy Windows PowerShell 5.1.

### Khi dùng một lệnh aggregate

Nếu đã cấu hình task dependencies như mục 10:

~~~bash
./gradlew verifyProducerAndConsumer --no-build-cache
~~~

Gradle sẽ sắp xếp các nhiệm vụ theo task graph; dùng phiên bản Gradle wrapper đã ghim giúp CI và máy dev cùng một công cụ. Tuy nhiên, nếu artifact bên ngoài task inputs thay đổi mà task được coi là up-to-date, cần biện pháp chống cache như đã giải thích.

### Phân quyền publish

Một CI pipeline production nên tách:

1. **Verify job** không có quyền publish remote; chạy producer contracts, tạo candidate, test consumer.
2. **Release job** chỉ chạy khi commit/tag được phép và các gate PASS; upload đúng artifact đã kiểm tra, có checksum hoặc build lại và kiểm chứng đúng commit.

Trong Gradle, các publication tasks có thể được gọi bằng `publish`/`publishToMavenLocal`. Đừng coi `publish` đồng nghĩa Gradle tự chạy `contractTest` nếu chưa có rule `dependsOn` hoặc pipeline gate như đã cấu hình.

Với repository remote, thêm `publishing.repositories.maven { ... }` và credentials an toàn bằng CI secrets. **Không đặt password/token trong `build.gradle` đã commit**, và không phát hành artifact mutable dưới một release version cũ.

## 14. Gắn thêm module thứ ba: shared contracts hay shared models?

Một số nhóm muốn có module `inventory-api`, `contracts-common` hoặc `testing-support`. Cần phân biệt hai mục tiêu:

| Module bổ sung | Nội dung | Có nên tạo? |
|---|---|---|
| `inventory-api` | Interface/DTO dùng chung giữa hai dịch vụ | Chỉ khi có chủ đích chia sẻ code; có thể làm coupling chặt |
| `contract-test-support` | Helper/base tests chung, matcher utility hoặc test fixtures | Hữu ích khi nhiều producer có cùng cơ chế kiểm thử |
| `api-contracts` | Groovy/YAML DSL được nhiều bên review | Có thể dùng nếu ownership ở repository/module riêng |
| `inventory-producer` | Implementation của producer | **Không** nên là runtime dependency của Checkout chỉ để dùng stub |

Nếu đưa DSL sang module `api-contracts`, producer cần **lấy đúng version contract** và sinh generated producer tests từ đó. Spring Cloud Contract Gradle plugin có `contractDependency`/`contractRepository` để tải contract từ artifact/SCM, nhưng cấu hình có khác so với mô hình contract nằm ngay trong producer.

Không để:

~~~text
inventory-producer dependsOn checkout-consumer
checkout-consumer dependsOn inventory-producer
~~~

dưới hình thức Gradle project dependencies; đây là vòng phụ thuộc build/runtime không hợp lý với hai microservice độc lập.

### Chọn mô hình ownership

- **Producer-side contracts:** producer lưu DSL, generated tests và stub artifact; consumer dùng Stub Runner. Đơn giản nhất cho bài này.
- **Consumer-proposed contracts:** consumer đề xuất yêu cầu, producer phải verify và publish stub từ cùng contract được chấp nhận; có thể dùng repository/hợp đồng riêng.
- **Shared contract repository:** phù hợp khi nhiều producer và consumer cùng dùng quy trình review tập trung, nhưng cần governance, version và CI kiểm chứng chặt hơn.

Điểm bất biến: **mỗi hợp đồng được công bố phải có bằng chứng producer đã đáp ứng**, bất kể file DSL được lưu ở module nào.

## 15. Nhánh lỗi HTTP và thông điệp cũng cần vào pipeline

Không chỉ kiểm tra trường hợp `200 OK`. Một consumer có thể phụ thuộc:

- `404` + mã lỗi `SKU_NOT_FOUND` khi SKU không tồn tại.
- `503` + `Retry-After` khi Inventory tạm unavailable.
- `200` với `available=false` và `quantity=0` khi hết hàng.
- Một `StockChanged` message có destination, headers và payload đúng.

Với HTTP:

~~~groovy
Contract.make {
    description 'SKU khong ton tai'
    request {
        method 'GET'
        url '/api/inventory/SKU-404'
    }
    response {
        status 404
        headers {
            contentType(applicationJson())
        }
        body(code: 'SKU_NOT_FOUND')
    }
}
~~~

Với messaging:

~~~groovy
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

**Cả hai là Groovy DSL minh họa**, chưa có base class và binder configuration. Với messaging, producer test cần có `@AutoConfigureMessageVerifier` và integration phù hợp; consumer cần Stub Runner trigger theo label cùng listener/broker/test binder. Không suy rằng HTTP WireMock mapping tự mô phỏng một message.

Trong Gradle multi-project build, messaging contract test cũng là **trách nhiệm producer**, còn consumer test dùng message stub phải có assertion xử lý bất đồng bộ, ví dụ Awaitility chờ trạng thái cuối với deadline hợp lý.

## 16. Các lỗi Gradle multi-module phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| `Task 'contractTest' not found` | Plugin chưa áp dụng vào producer hoặc version khác task naming | Xem `:inventory-producer:tasks --all` và plugin |
| Generated tests không có file | DSL đặt sai folder; Gradle mới dùng `src/contractTest/resources/contracts` | Kiểm tra `contractsDslDir`, build log |
| Base class không biên dịch | Class đặt sai source set, thiếu verifier/test dependencies | Xác nhận `src/contractTest/java`, classpath và JUnit |
| `contractTest` không chạy test nào | Không phát hiện contract, test runner/filter/JUnit chưa đúng | Xem test reports và số tests executed |
| `verifierStubsJar` có nhưng không có Maven publication | Không cấu hình `maven-publish` hoặc chưa attach artifact | Kiểm tra `publishing.publications` và `:tasks --all` |
| Stub artifact không có classifier `stubs` | JAR custom classifier khác, publication sai | Kiểm tra tên file và Maven coordinates |
| Consumer Stub Runner `LOCAL` không tìm stub | Chưa chạy `publishStubsPublicationToMavenLocal` hoặc version khác | Kiểm tra Maven local repository và resolved artifact |
| Consumer nhận 404 không mong đợi | Request matcher không khớp mapping | Đọc generated WireMock mapping và HTTP request thực |
| Consumer test xanh dù đổi contract | Consumer dùng stub cũ hoặc Gradle test task UP-TO-DATE | Ghim version, kiểm tra resolved artifact, rerun test |
| Publication chạy khi test producer lỗi | Gate chỉ ở shell script lỏng, task publish không dependsOn test | Thiết lập task/pipeline dependencies và fail closed |
| Task graph báo circular dependency | Producer phụ thuộc consumer test, consumer phụ thuộc producer publish | Chỉ producer -> stub -> consumer; release gate ở pipeline |
| Tests chỉ fail khi parallel | Stub ports/dữ liệu/cache dùng chung | Cô lập môi trường/port/coordinate của từng pipeline |
| Multi-module build kéo cả producer vào Checkout | Dùng `implementation project(':inventory-producer')` không cần thiết | Chỉ dùng stub artifacts cho consumer HTTP tests |
| Consumer có result khác giữa máy và CI | Cache Maven/repository hoặc JDK/BOM không đồng nhất | Ghim Gradle wrapper, phiên bản và stub digest |

### Tập trung debug vào ba câu hỏi

1. **Producer có được kiểm chứng thật?** Mở generated contract tests và test report.
2. **Stub nào đã được publish/nạp?** Kiểm tra group/artifact/version/classifier/digest.
3. **Consumer có gọi đúng stub bằng client thật?** Kiểm tra URL runtime, request matcher và assertion nghiệp vụ.

Không giải quyết sự cố bằng cách chỉ tăng timeout hoặc đổi sang `latest`/`+`, vì chúng có thể che mất lỗi chính.

## 17. Bài thực hành: tìm điểm đứt trong pipeline

### Đề bài

Một repository có hai module `inventory-producer` và `checkout-consumer`. Nhóm cấu hình:

~~~groovy
// inventory-producer/build.gradle
publishing {
    publications {
        stubs(MavenPublication) {
            artifact tasks.named('verifierStubsJar')
        }
    }
}
~~~

Và script CI:

~~~bash
./gradlew :inventory-producer:verifierStubsJar
./gradlew :inventory-producer:publishStubsPublicationToMavenLocal
./gradlew :checkout-consumer:test
~~~

Nhưng không cấu hình `publishStubsPublicationToMavenLocal.dependsOn contractTest`. Consumer dùng Stub Runner `LOCAL` với version `1.1.0`, trong khi producer project đã đổi thành `1.2.0-rc.1`.

**Câu 1. Có bao nhiêu rủi ro cần sửa?**

Ít nhất ba:

- Build tạo và publish stub mà **không bảo đảm producer contract tests đã chạy thành công**.
- Consumer đang dùng **stub version cũ**, không phải candidate đang review.
- Script không cho thấy cơ chế chặn pipeline khi một lệnh thất bại (phụ thuộc shell/CI runner).

**Câu 2. Nên sửa gate ở đâu?**

Cấu hình task publication của producer phụ thuộc `contractTest`, đồng thời CI kiểm tra **số lượng generated contract tests** và trạng thái PASS. Không chỉ đổi thứ tự lệnh shell; giữ ràng buộc ở task graph để các đường gọi khác cũng được bảo vệ.

**Câu 3. Version nào consumer phải dùng?**

Trong bài tập, Stub Runner phải resolve:

~~~text
com.example:inventory-producer:1.2.0-rc.1:stubs
~~~

và chạy test với đúng artifact từ producer commit được kiểm chứng.

**Câu 4. Vì sao dùng `--rerun-tasks` có thể cần trong CI?**

Nếu task consumer `test` bị coi là up-to-date trong khi Maven local artifact đã thay, Gradle có thể không chạy lại test. `--rerun-tasks --no-build-cache` là một biện pháp ngắn hạn khi test candidate; tốt hơn là version/digest bất biến và task inputs được khai báo phù hợp.

**Câu 5. Nếu producer contract test PASS nhưng consumer FAIL thì sao?**

Đây có thể là thay đổi breaking đối với consumer cũ, matcher thiếu phù hợp, lỗi client hoặc stub artifact không đồng bộ. Không tự xuất bản bản mới khi policy yêu cầu compatibility; cần đối chiếu contract, implementation, generated test, stub và consumer assertion.

### Bài mở rộng: thêm module pricing

Thêm `pricing-producer` vào `settings.gradle` và thiết kế:

- Producer Inventory publish `com.example:inventory-producer:...:stubs`.
- Producer Pricing publish `com.example:pricing-producer:...:stubs`.
- Checkout dùng Stub Runner tải **hai artifact** và tra đúng cổng của từng producer.
- Task consumer chỉ chạy sau khi **cả hai producer contracts** được xác nhận và candidate stubs sẵn sàng.
- Không tạo vòng phụ thuộc Gradle task, không dùng một URL chung cho cả hai producer.
- CI ghi version/commit/digest của **từng artifact**.

### Câu hỏi tự kiểm tra

- Tại sao `project(':inventory-producer')` không đồng nghĩa dependency vào `:stubs`?
- Tại sao Gradle `contractTest` ở producer khác `test` của consumer?
- `verifierStubsJar` có cần được publish thủ công bằng `maven-publish` trong plugin hiện đại không?
- Vì sao `build/generated-test-sources/...` không phải chỗ nên sửa source test?
- Khi nào consumer nên dùng `LOCAL`, khi nào `REMOTE`?
- Vì sao một test consumer xanh vẫn cần producer contract tests?
- Nếu Gradle báo `UP-TO-DATE` khi artifact stub thay đổi, bạn cần làm gì?
- Vì sao không nên dùng cùng một mutable `SNAPSHOT` trong nhiều CI job song song?

## 18. Checklist cấu hình và phát hành

- [ ] Root `settings.gradle` khai báo đúng các subprojects và phiên bản plugin tương thích.
- [ ] Producer sở hữu Groovy/YAML DSL đúng thư mục `src/contractTest/resources/contracts` hoặc đã cấu hình `contractsDslDir` phù hợp.
- [ ] Producer Gradle plugin `org.springframework.cloud.contract` được áp dụng đúng module.
- [ ] `testFramework` và base class tương thích với generated test, classpath và JUnit lifecycle.
- [ ] Generated contract tests được sinh, biên dịch và **thực sự chạy**.
- [ ] `:inventory-producer:contractTest` PASS với số test phù hợp, không bị skip/disable.
- [ ] `verifierStubsJar` chứa mappings/contracts/fixtures cần thiết.
- [ ] `maven-publish` có publication chứa stub JAR với classifier `stubs`.
- [ ] Các publication tasks không chạy khi producer contract test fail.
- [ ] Consumer **không** có runtime dependency trực tiếp vào implementation producer chỉ để chạy HTTP contract test.
- [ ] Consumer có `spring-cloud-starter-contract-stub-runner` trong test classpath.
- [ ] Stub Runner resolve **đúng candidate group/artifact/version/classifier**.
- [ ] HTTP client thực của consumer dùng đúng URL/cổng stub; không gọi nhầm producer thật.
- [ ] Consumer tests assert field, status, kiểu dữ liệu và hành vi nghiệp vụ quan trọng.
- [ ] Task dependencies hoặc CI pipeline bảo đảm producer -> artifact -> consumer theo luồng một chiều.
- [ ] Artifact và test reports có version, commit/digest truy vết được.
- [ ] Gradle cache/Maven local repository không làm test dùng stub cũ hoặc bỏ chạy.
- [ ] Nếu thêm messaging, test binder/trigger và kiểm tra handler async được thiết kế đúng.
- [ ] Thay đổi breaking được review theo consumer đang triển khai, không chỉ theo contract mới.
- [ ] Release credentials chỉ nằm trong job được cấp quyền sau tất cả quality gates.

## 19. Ghi nhớ và tài liệu tham khảo

**Một Gradle multi-project build tốt không làm producer và consumer phụ thuộc vào implementation của nhau; nó sắp xếp một chuỗi bằng chứng:** contract Groovy/YAML → generated producer tests → stub artifact có version → Stub Runner → consumer test dùng HTTP client thật. Gradle `contractTest` và `verifierStubsJar` là những bước riêng; `publish` cần quality gate, còn `checkout-consumer:test` cần tải đúng artifact.

Với các phiên bản Spring Cloud Contract Gradle hiện đại, hãy chú ý **source set `contractTest`** và việc **publication stubs phải được khai báo rõ với `maven-publish`**. Trong CI, tạo candidate stub sau producer verification, cung cấp cùng revision cho consumer, chống cache stale và ngăn phát hành khi bất kỳ gate bắt buộc nào thất bại.

### Tài liệu tham khảo

- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): plugin, source set `contractTest`, tasks `contractTest`/`verifierStubsJar`, Gradle publication và tải hợp đồng từ nguồn ngoài.
- [Spring Cloud Contract — Stub Runner Core](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html): resolve stubs theo tọa độ, các chế độ `LOCAL`/`REMOTE`/`CLASSPATH`.
- [Spring Cloud Contract — Stub Runner Boot](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): `@AutoConfigureStubRunner` và cấu hình consumer tests.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): `settings.gradle`, `include`, project paths và task dependencies.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): `MavenPublication` và publication tasks.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): cách build cache và task inputs/outputs ảnh hưởng kết quả test.

**Kết luận thực hành:** khi nhiều module cùng dùng Gradle, đừng chỉ hỏi “build đã xanh chưa?”. Hãy xác nhận **test producer đã chạy và đạt**, **stub được publish từ đúng code/contract version**, và **consumer test thực sự chạy với artifact đó**. Ba bằng chứng này mới giúp CI phát hiện thay đổi giao diện không tương thích thay vì tạo cảm giác an toàn từ một pipeline xanh giả.
