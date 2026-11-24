# Áp dụng plugin Spring Cloud Contract và khai báo dependency

Một dự án sử dụng **Gradle** không thể chỉ đặt các tệp hợp đồng trong `src/test/resources/contracts` rồi kỳ vọng chúng tự trở thành kiểm thử. **Spring Cloud Contract Gradle Plugin** cần được áp dụng vào build; các dependency kiểm thử phải có mặt trên classpath; test framework, chế độ kiểm thử và base test phải tương thích với producer. Khi các bước này được cấu hình đúng, Gradle có thể **sinh producer verification tests** từ Groovy/YAML DSL, chạy chúng và tạo artifact **stubs** để consumer kiểm thử thông qua **Stub Runner**.

Bài thuộc chương **Tích hợp Gradle** của mô-đun **SPRING_CLOUD_CONTRACT**. Phạm vi học là kiểm thử hợp đồng giữa producer và consumer, mô tả HTTP hoặc thông điệp bằng Groovy/YAML DSL, xác minh producer, đóng gói stub và tích hợp CI để phát hiện API không tương thích. Trọng tâm bài này là **áp dụng plugin và khai báo dependency trong Gradle**, đồng thời giải thích mối liên hệ giữa phần cấu hình build và các bước thực sự diễn ra sau đó.

Các ví dụ dùng **Gradle Groovy DSL** (`build.gradle`) làm luồng chính; `build.gradle.kts` được giới thiệu riêng. Những phiên bản được ghi trong ví dụ là **một bộ minh họa có chủ đích**, không phải bản mới nhất hoặc mặc định cho mọi dự án. Khi đưa vào hệ thống thực, phải chọn **Spring Boot, Spring Cloud release train, Spring Cloud Contract, Gradle và Java** tương thích theo tài liệu của bộ phiên bản dự án.

## 1. Gradle Plugin giải quyết việc gì?

**Contract Verifier** và **Stub Runner** có nhiệm vụ khác nhau:

| Thành phần | Nằm ở đâu? | Trách nhiệm chính |
| --- | --- | --- |
| **Spring Cloud Contract Gradle Plugin** | Build của **producer** | Tìm hợp đồng, tạo test source, sinh stub resources và cung cấp các Gradle tasks tương ứng. |
| **spring-cloud-starter-contract-verifier** | `testImplementation` của producer | Cung cấp các thư viện cần để chạy kiểm thử hợp đồng đã sinh. |
| **Base test** | `src/test/java` hoặc test source phù hợp | Chuẩn bị Spring context, MockMvc/WebTestClient, fixture và trạng thái ban đầu. |
| **spring-cloud-starter-contract-stub-runner** | `testImplementation` của **consumer** | Tải và khởi chạy stub, cung cấp API/annotation cho consumer tests. |
| **Maven/Artifact repository** | Hạ tầng phân phối | Lưu JAR classifier `stubs` theo group/artifact/version. |
| **Groovy/YAML contracts** | Thường ở test resources của producer | Đặc tả request/response HTTP hoặc message observable. |

Một cách nhìn theo vòng đời:

~~~mermaid
flowchart TD
    A["Producer: Groovy/YAML contracts"] --> B["Gradle Spring Cloud Contract Plugin"]
    B --> C["Sinh producer tests"]
    B --> D["Sinh resources/mappings cho stubs"]
    C --> E["Gradle test task chạy trên producer thật"]
    E --> F{"Producer verification đạt?"}
    F -->|Không| G["Chặn phát hành"]
    F -->|Có| H["Đóng gói JAR classifier stubs"]
    D --> H
    H --> I["Publish Maven artifact"]
    I --> J["Consumer Gradle test + Stub Runner"]
    J --> K["Kiểm HTTP client hoặc message listener thật"]
~~~

**Plugin của producer không thay `spring-cloud-starter-contract-stub-runner` ở consumer**. Ngược lại, chỉ thêm dependency Contract Verifier vào producer mà **không áp dụng plugin** có thể không tạo ra bất kỳ generated test nào. Cần có cả **khâu sinh** và **khâu chạy**.

## 2. Xác định trước một bộ phiên bản tương thích

Giả sử bài thực hành dùng:

| Công cụ | Giá trị ví dụ | Vai trò |
| --- | --- | --- |
| Java | 17 | Ngôn ngữ/runtime cho ứng dụng Spring Boot 3.x minh họa. |
| Gradle | Phiên bản được Gradle Wrapper và Spring Boot plugin hỗ trợ | Chạy build, plugin và test tasks. |
| Spring Boot | 3.3.x | Framework producer/consumer. |
| Spring Cloud release train | 2023.0.x | Quản lý phiên bản Spring Cloud dependencies. |
| Spring Cloud Contract Gradle Plugin | 4.1.x | Sinh kiểm thử và tài nguyên stub theo bộ Spring Cloud phù hợp. |
| JUnit | JUnit Jupiter | Chạy generated tests khi chọn `JUNIT5`. |
| Producer HTTP stack | Spring MVC | Ví dụ dùng `MOCKMVC`. |

**Bảng này minh họa một hệ phiên bản, không phải cam kết mọi bản vá bất kỳ trong các dòng trên đều tương thích.** Đội ngũ phải kiểm release train và ma trận tương thích của những phiên bản thật sự được chọn. Khi nâng Spring Boot, thường cần đánh giá lại Gradle Wrapper, Spring Cloud BOM, Spring Cloud Contract plugin, các starter và cả base test.

Những quy tắc cần nhớ:

1. **Plugin version** trong `plugins` là phiên bản của build plugin, **không tự động thay thế toàn bộ quản lý phiên bản dependency** trên `testImplementation`.
2. **Spring Cloud BOM** giúp quản lý các dependency thuộc Spring Cloud trong project; nó **không nhất thiết quản lý phiên bản của plugin** được Gradle tải ở giai đoạn plugin resolution.
3. **Gradle Wrapper** (`./gradlew`, `gradlew.bat`) xác định Gradle runtime của build. Hãy dùng wrapper đã được dự án kiểm tra, tránh phụ thuộc Gradle cài sẵn trên từng máy.
4. **Java toolchain** giúp Gradle chọn JDK để biên dịch/chạy đúng kỳ vọng; nếu CI không có JDK hoặc không thể tải toolchain, build vẫn có thể thất bại.

## 3. Cấu trúc dự án producer với Gradle

Ví dụ Order Service:

~~~text
order-service/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
├── src/
│   ├── main/
│   │   └── java/com/acme/orders/
│   │       ├── OrderApplication.java
│   │       └── OrderController.java
│   └── test/
│       ├── java/com/acme/orders/
│       │   └── ContractTestBase.java
│       └── resources/
│           └── contracts/
│               └── orders/
│                   └── get_paid_order.groovy
└── build/
    └── ... generated test sources, mappings, reports và artifacts
~~~

`build/` là đầu ra do Gradle tạo, **không phải nguồn để sửa generated test bằng tay**. Những tài liệu cần được quản lý trong source control là **contract, base test, plugin/dependency configuration và implementation producer**.

Tệp `settings.gradle` có thể khai báo các repository để Gradle phân giải plugin:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = 'order-service'
~~~

`pluginManagement.repositories` dùng khi Gradle **tìm build plugin**; còn `repositories` ở `build.gradle` dùng khi dự án **tìm thư viện application/test**. Hai phạm vi không nên bị nhầm lẫn. Trong doanh nghiệp có mirror/repository nội bộ, có thể thay các repository công khai bằng nguồn được phép.

## 4. Áp dụng plugin trong `build.gradle`

Một ví dụ Groovy DSL cho producer Spring MVC:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
    id 'org.springframework.cloud.contract' version '4.1.5'
    id 'maven-publish'
}

group = 'com.acme'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

ext {
    springCloudVersion = '2023.0.4'
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-verifier'
}

contracts {
    baseClassForTests = 'com.acme.orders.ContractTestBase'
    testFramework = 'JUNIT5'
    testMode = 'MOCKMVC'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Phạm vi ví dụ:** các số phiên bản trong `plugins` và `springCloudVersion` chỉ minh họa cách khai báo. Nếu dự án đang ở một release train khác, hãy chọn bộ tương thích thay vì ghép `4.1.5` vào Spring Boot mới hơn mà không kiểm. Đoạn trên cũng chưa chứa controller, base test, hợp đồng và cấu hình phát hành artifact `stubs`; các phần này được xây dựng ở dưới.

### 4.1. Đọc ý nghĩa từng khối

| Khối hoặc dòng | Ý nghĩa |
| --- | --- |
| `id 'java'` | Bổ sung các task Java, source sets, compile và test. |
| `id 'org.springframework.boot'` | Tích hợp build Spring Boot. |
| `id 'io.spring.dependency-management'` | Cho phép nhập Maven BOM bằng khối `dependencyManagement` trong ví dụ. |
| `id 'org.springframework.cloud.contract'` | Áp dụng **Gradle Plugin của Spring Cloud Contract** lên producer. |
| `id 'maven-publish'` | Cho phép tạo Maven publication để phát hành artifact. |
| `group` và `version` | Một phần tọa độ Maven của artifact và stub. |
| `java.toolchain` | Yêu cầu môi trường Java 17 cho ví dụ. |
| `repositories { mavenCentral() }` | Chỉ nơi tìm application/test dependencies. |
| `springCloudVersion` + `mavenBom` | Đồng bộ nhóm Spring Cloud libraries theo release train đã chọn. |
| `testImplementation '...contract-verifier'` | Đưa thư viện xác minh vào **test classpath** của producer. |
| `contracts { ... }` | Hướng dẫn plugin sinh test theo base class, framework và mode đã chọn. |
| `useJUnitPlatform()` | Giúp Gradle `test` task nhận và chạy bài kiểm thử JUnit Jupiter. |

**Đừng nhầm cách cấu hình Maven:** Maven dùng `spring-cloud-contract-maven-plugin` trong `pom.xml`. Với Gradle, phải áp dụng **`org.springframework.cloud.contract`** trong `plugins`; không sao chép nguyên thẻ `<plugin>` của Maven vào `build.gradle`.

## 5. Vì sao cần cả Plugin và dependency Verifier?

Hai phần có trách nhiệm bổ trợ:

~~~groovy
plugins {
    id 'org.springframework.cloud.contract' version '4.1.5'
}

dependencies {
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-verifier'
}
~~~

- **Gradle Plugin** tham gia quá trình build, **đọc contract** và **sinh test/stub resources**.
- **Verifier starter** cung cấp thư viện để **mã test được sinh có thể biên dịch và thực thi** trong project producer.

Điều đó không có nghĩa plugin và starter có thể dùng **hai version bất kỳ**. Hãy quản lý dependency theo BOM phù hợp với plugin version. Nếu thấy lỗi `NoClassDefFoundError`, `NoSuchMethodError` hoặc generated tests có imports không tồn tại, cần kiểm lại **cả plugin, BOM, starter, Spring Boot** và Gradle runtime.

### 5.1. `implementation` và `testImplementation` khác nhau

| Gradle configuration | Ví dụ | Sử dụng khi |
| --- | --- | --- |
| `implementation` | `spring-boot-starter-web` | Thư viện cần cho ứng dụng producer khi chạy. |
| `testImplementation` | `spring-boot-starter-test`, `spring-cloud-starter-contract-verifier` | Thư viện cần để biên dịch/chạy test. |
| `testRuntimeOnly` | Test engine hoặc runtime provider trong những tổ hợp cần khai báo riêng | Cần ở runtime test nhưng không cần compile test. |
| `runtimeOnly` | JDBC driver của app hoặc thành phần runtime tùy kiến trúc | Không cần compile ứng dụng. |

**Không đưa Contract Verifier starter vào `implementation` chỉ để sửa test compile error**, vì như vậy có thể kéo các dependency phục vụ kiểm thử vào artifact runtime production. Hãy tìm nguyên nhân thiếu class ở **test configuration** trước.

Khi dùng Gradle Java plugin, `testImplementation` nằm trong dependency graph của test source set mặc định. Nếu tổ chức **custom test source set**, cần cấu hình các dependency và task khác tương ứng; đừng giả định generated tests tự chuyển sang custom source set.

## 6. Cấu hình `contracts` extension: base test, framework, mode

Một khối quan trọng của plugin:

~~~groovy
contracts {
    baseClassForTests = 'com.acme.orders.ContractTestBase'
    testFramework = 'JUNIT5'
    testMode = 'MOCKMVC'
}
~~~

Ba lựa chọn khác nhau:

| Thuộc tính | Ví dụ | Quyết định |
| --- | --- | --- |
| `baseClassForTests` | `com.acme.orders.ContractTestBase` | Lớp mà generated producer tests kế thừa, chuẩn bị fixture và HTTP test client. |
| `testFramework` | `JUNIT5` | Framework/cú pháp của generated tests. |
| `testMode` | `MOCKMVC` | Cách generated test gọi producer HTTP. |

Các chế độ phổ biến:

- **`MOCKMVC`** cho **Spring MVC**, dùng MockMvc qua Spring Test context mà không phải mở HTTP socket thực.
- **`WEBTESTCLIENT`** cho **Spring WebFlux** khi phiên bản plugin hỗ trợ đúng stack/client được cấu hình.
- **`EXPLICIT`** khi cần generated tests gọi một **HTTP server thực** qua host và port được khởi động trong test.
- Một số phiên bản/tích hợp có thể cung cấp **`JAXRSCLIENT`** cho JAX-RS; chỉ chọn nếu phù hợp framework và plugin thực tế.

**Groovy DSL của contract không bắt buộc generated tests dùng Groovy/Spock.** Một file `.groovy` vẫn có thể sinh Java JUnit 5 test. Ngược lại, đổi `testFramework` sang Spock cần có Groovy/Spock toolchain và test discovery phù hợp; không chỉ đổi một string rồi hy vọng Gradle đã cấu hình sẵn.

## 7. Viết một HTTP contract mẫu bằng Groovy DSL

Đặt tại `src/test/resources/contracts/orders/get_paid_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Order Service trả trạng thái đơn hàng đã thanh toán'

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
            status: 'PAID'
        )
    }
}
~~~

Hợp đồng này quy định:

1. Request là `GET /api/orders/42` với header `Accept: application/json`.
2. Response có HTTP `200` và Content-Type JSON.
3. Response body có `id=42` và `status=PAID`.

**Không có Gradle, Maven, MockMvc, Stub Runner, Java class hay port trong hợp đồng**. Nó mô tả tương tác HTTP; plugin và base test quyết định cách xác minh producer thực tế.

### 7.1. Nếu nhóm dùng YAML DSL

Một tệp YAML độc lập, ví dụ `get_paid_order.yml`:

~~~yaml
description: Order Service trả trạng thái đơn hàng đã thanh toán
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
~~~

**Chỉ chọn một trong hai tệp Groovy/YAML làm nguồn contract có hiệu lực** cho cùng kịch bản trong một build. Nếu cả hai được plugin nạp cùng lúc, có thể sinh generated tests hoặc mappings trùng, gây khó hiểu khi đổi hợp đồng.

## 8. Base test cho producer Spring MVC

Giả sử Order Service có endpoint:

~~~java
package com.acme.orders;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public OrderView getOrder(@PathVariable long id) {
        if (id != 42L) {
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.NOT_FOUND
            );
        }
        return new OrderView(42L, "PAID");
    }

    public record OrderView(long id, String status) {}
}
~~~

Và ứng dụng có một class `@SpringBootApplication` tên `com.acme.orders.OrderApplication`.

Tạo `src/test/java/com/acme/orders/ContractTestBase.java`:

~~~java
package com.acme.orders;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(classes = OrderApplication.class)
@AutoConfigureMockMvc
public abstract class ContractTestBase {

    @Autowired
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

Ở ví dụ này, `MOCKMVC` cần một `MockMvc` được Spring Test cấu hình; `RestAssuredMockMvc.mockMvc(mockMvc)` kết nối client test với Spring MVC handler. Nếu endpoint phụ thuộc database, authentication hoặc service ngoài, **base test còn phải chuẩn bị fixture và trạng thái ban đầu**; ví dụ cố định đơn 42 chỉ để tập trung vào cấu hình Gradle.

Nếu plugin không tìm được base class hoặc generated test gọi một client không được cấu hình, hãy kiểm **giá trị `baseClassForTests`, package, test framework và code test thực tế đã được sinh**. Không sửa generated tests trực tiếp vì build sau sẽ ghi đè.

## 9. Những Gradle tasks cần nhận biết

Sau khi plugin được áp dụng, các tác vụ thường liên quan gồm:

| Task phổ biến | Vai trò |
| --- | --- |
| `generateContractTests` | Đọc contract và sinh producer test sources. |
| `generateClientStubs` | Sinh tài nguyên stub từ hợp đồng. |
| `test` | Chạy test task của Java project, bao gồm generated tests nếu plugin wiring đúng. |
| `check` | Chạy các verification tasks đã được gắn vào lifecycle kiểm thử. |
| `build` | Build project, gồm kiểm tra/test và đóng gói theo cấu hình Gradle. |
| `verifierStubsJar` | Đóng gói artifact stub classifier `stubs` ở những phiên bản plugin có task này. |
| `publishToMavenLocal`, `publish` | Publish các Maven publications đã cấu hình, không mặc nhiên publish mọi artifact nếu chưa khai báo. |

**Tên task và task graph có thể khác theo phiên bản plugin/configuration**. Để xem môi trường thực tế, bạn có thể chạy trên dự án producer:

~~~shell
./gradlew tasks --all
./gradlew help --task generateContractTests
./gradlew help --task verifierStubsJar
~~~

Trên Windows PowerShell hoặc Command Prompt:

~~~powershell
.\gradlew.bat tasks --all
.\gradlew.bat test
~~~

Các lệnh trong bài là **hướng dẫn để người học tự thực hành**, không phải những lệnh đã được chạy trong quá trình soạn bài này.

### 9.1. Kiểm đường đi từ sinh test đến chạy test

Một lần chạy tham khảo:

~~~shell
./gradlew clean test
~~~

Kết quả cần kiểm:

- Tệp `get_paid_order.groovy` đã được plugin **phát hiện và phân tích**.
- Generated producer test class có trong **generated test sources** của Gradle (thường dưới `build/`, đường dẫn cụ thể tùy plugin).
- Generated test kế thừa đúng `ContractTestBase`.
- Gradle `test` task thực thi **JUnit Jupiter** test đó; báo cáo cho biết số test > 0.
- Response từ producer thật được kiểm đúng `status=200`, Content-Type và JSON.
- Nếu cố tình đổi `status` của controller từ `PAID` thành `PENDING`, test phải **FAIL**.

**Một dòng `BUILD SUCCESSFUL` không đủ.** Có thể test đã bị skip, task `test` nhận 0 test, hợp đồng nằm sai thư mục hoặc generated source set chưa nối vào Gradle test task. Để xác minh, hãy xem báo cáo `build/reports/tests/test/` nếu cấu hình mặc định tạo báo cáo ở đó, cùng log của `generateContractTests` và `test`.

## 10. Sinh JAR `stubs` và hiểu tọa độ artifact

Consumer cần tải đúng bộ stub mà producer đã xác minh. Với ví dụ:

~~~text
group       = com.acme
artifactId  = order-service
version     = 1.0.0
classifier  = stubs
~~~

Tọa độ thường dùng với Stub Runner:

~~~text
com.acme:order-service:1.0.0:stubs
~~~

Một JAR được Gradle tạo có thể mang tên:

~~~text
order-service-1.0.0-stubs.jar
~~~

**Phân biệt JAR ứng dụng với JAR stub**:

- JAR ứng dụng chứa code chạy producer.
- JAR `stubs` chứa HTTP mappings, hợp đồng và dữ liệu cần cho Stub Runner tùy loại contract và plugin.
- JAR `stubs` **không thay cho** Spring Boot application đang chạy.

Các bản stub HTTP thường có dữ liệu WireMock mapping; messaging contracts cần tài nguyên hợp đồng và messaging integration tương ứng. **Không nên chỉ kiểm số file mappings** rồi kết luận một messaging-only stub thiếu dữ liệu.

### 10.1. Khai báo publication cho stub artifact

Khi áp dụng `maven-publish`, có thể thêm một publication trong `build.gradle`:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            artifact(tasks.named('verifierStubsJar'))
        }
    }
}
~~~

Đoạn này **phụ thuộc task `verifierStubsJar` thực sự tồn tại ở phiên bản plugin đang dùng**. Hãy kiểm `./gradlew tasks --all` trước. Task Jar cần có classifier `stubs` để tọa độ artifact mà consumer yêu cầu khớp với artifact phát hành. Một số phiên bản/plugin configuration có thể đã tự thiết lập artifact/publication hoặc cung cấp cách publish riêng; đừng khai báo **hai lần** cùng classifier rồi làm publication chứa artifact trùng nhau.

Sau khi cấu hình publication, người học có thể thử:

~~~shell
./gradlew clean build
./gradlew publishToMavenLocal
~~~

**Không suy rằng `publishToMavenLocal` tự động buộc `test` phải chạy trong mọi cấu hình.** Với CI đáng tin, hãy thiết lập thứ tự các job hoặc task dependency rõ ràng để chỉ publish **sau khi producer verification đạt**. Nếu muốn publish lên repository riêng, khai báo `publishing.repositories` và dùng `./gradlew publish` theo quy trình có authentication phù hợp.

## 11. Gradle `maven-publish` không đồng nghĩa Stub Runner đã tải được JAR

Hai bước độc lập:

1. **Producer** phải xuất bản đúng JAR với `groupId`, `artifactId`, `version` và classifier `stubs`.
2. **Consumer** phải có quyền truy cập repository đó và yêu cầu đúng tọa độ.

Ví dụ consumer chạy với local repository sau `publishToMavenLocal`:

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

Với CI dùng repository từ xa:

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/maven-releases"
)
~~~

Địa chỉ repository chỉ là **minh họa**. `REMOTE` nghĩa là **tải artifact từ Maven repository**, không có nghĩa consumer HTTP client gửi request tới URL repository. Sau khi tải, Stub Runner có thể khởi động WireMock ở một **port động**, rồi consumer test tra URL qua `StubFinder`.

**Kiểm tra nhóm và tên artifact:** nếu `settings.gradle` đặt project name khác với `artifactId` mà Stub Runner yêu cầu, hoặc publication thay đổi tên artifact, consumer có thể không tìm thấy stubs dù producer đã build thành công.

## 12. Dependency phía consumer: Stub Runner, không phải Verifier Plugin

Trong repository **Billing Service** (consumer), thông thường **không cần áp dụng Spring Cloud Contract Gradle Plugin** chỉ để chạy test với stub do Order Service đã publish. Consumer cần **Stub Runner starter ở test scope**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

repositories {
    mavenCentral()
}

ext {
    springCloudVersion = '2023.0.4'
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-stub-runner'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Điểm khác biệt:**

- Producer dùng **`org.springframework.cloud.contract` Gradle Plugin** và **`spring-cloud-starter-contract-verifier`** để **sinh, chạy test và xuất stub**.
- Consumer dùng **`spring-cloud-starter-contract-stub-runner`** để **nạp stubs và chạy mã client thật** trong test.
- Cả hai phải chọn **dependency versions phù hợp Spring Boot và Spring Cloud BOM** tương ứng. Không nhất thiết producer và consumer cùng số version ứng dụng, nhưng artifact stub mà consumer tải phải đúng hợp đồng nó dùng.

Nếu consumer cũng là producer cho dịch vụ khác, cùng repository có thể cần **cả hai** loại tích hợp, nhưng phải giữ rõ mục đích và phạm vi dependency.

## 13. Test consumer đơn giản với Stub Runner

Một lớp HTTP client Spring RestClient của Billing:

~~~java
package com.acme.billing;

import org.springframework.web.client.RestClient;

public final class OrderClient {
    private final RestClient client;

    public OrderClient(String baseUrl) {
        this.client = RestClient.create(baseUrl);
    }

    public OrderDto getOrder(long id) {
        return client.get()
            .uri("/api/orders/{id}", id)
            .retrieve()
            .body(OrderDto.class);
    }

    public record OrderDto(long id, String status) {}
}
~~~

Consumer JUnit 5 test:

~~~java
package com.acme.billing;

import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientContractTest {

    @Autowired
    StubFinder stubFinder;

    @Test
    void readsPaidOrderThroughStub() {
        URL url = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Order Service stub was not started"
        );

        OrderClient orderClient = new OrderClient(url.toExternalForm());
        OrderClient.OrderDto order = orderClient.getOrder(42L);

        assertThat(order.id()).isEqualTo(42L);
        assertThat(order.status()).isEqualTo("PAID");
    }
}
~~~

**Tại sao lấy URL động?** Stub Runner có thể tự chọn một port trống; không nên hardcode `localhost:8089` khi CI chạy nhiều job song song. `StubFinder` ở đây trả địa chỉ **HTTP stub đang chạy**, không phải đường dẫn JAR hoặc repository Maven.

Ví dụ sử dụng **mã OrderClient thật** và JSON/HTTP contract đã publish. Tuy nhiên, consumer test xanh với stub **không tự chứng minh producer thật đúng hợp đồng**; điều đó được bảo vệ bởi producer verification chạy trong build Order Service.

## 14. Gradle Groovy DSL và Kotlin DSL có gì khác?

Hai loại tệp Gradle không thể sao chép cú pháp từng ký tự:

| Thành phần | Groovy DSL: `build.gradle` | Kotlin DSL: `build.gradle.kts` |
| --- | --- | --- |
| Plugin | `id 'org.springframework.cloud.contract' version '4.1.5'` | `id("org.springframework.cloud.contract") version "4.1.5"` |
| Test dependency | `testImplementation 'group:artifact'` | `testImplementation("group:artifact")` |
| Repository | `mavenCentral()` | `mavenCentral()` |
| JUnit test task | `tasks.named('test') { useJUnitPlatform() }` | `tasks.test { useJUnitPlatform() }` |
| BOM với Gradle platform | `implementation platform('group:bom:version')` | `implementation(platform("group:bom:version"))` |

Một khởi đầu Kotlin DSL minh họa:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.6"
    id("io.spring.dependency-management") version "1.1.6"
    id("org.springframework.cloud.contract") version "4.1.5"
    id("maven-publish")
}

group = "com.acme"
version = "1.0.0"

repositories {
    mavenCentral()
}

extra["springCloudVersion"] = "2023.0.4"

dependencyManagement {
    imports {
        mavenBom(
            "org.springframework.cloud:spring-cloud-dependencies:" +
                extra["springCloudVersion"]
        )
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.cloud:spring-cloud-starter-contract-verifier")
}

tasks.test {
    useJUnitPlatform()
}
~~~

**Phần trên minh họa cú pháp Kotlin cho plugins/dependencies/test task.** Việc viết `contracts { ... }` bằng Kotlin DSL phụ thuộc cách plugin công bố extension và kiểu của các properties trong phiên bản đang dùng. Cần tra API extension được IDE/Gradle nhận diện, không copy `baseClassForTests = '...'` của Groovy vào Kotlin mà không đổi cú pháp/kiểu.

Nếu muốn tránh dependency-management plugin, Gradle cũng hỗ trợ **`platform(...)`** để nhập BOM. Chọn **một chiến lược quản lý version rõ ràng**, không nhập cùng BOM bằng nhiều cơ chế với version khác nhau khiến dependency graph khó giải thích.

## 15. Có thể dùng Gradle native BOM thay dependency-management plugin?

Trong một số dự án, nhóm chọn native Gradle `platform(...)` để khai báo BOM thay vì `io.spring.dependency-management`:

~~~groovy
dependencies {
    implementation platform(
        'org.springframework.cloud:spring-cloud-dependencies:2023.0.4'
    )
    testImplementation platform(
        'org.springframework.cloud:spring-cloud-dependencies:2023.0.4'
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-verifier'
}
~~~

**Cần lưu ý:** nếu bỏ dependency-management plugin thì phải xác định cách quản lý **Spring Boot starter versions** và các dependency khác. Trong một số cấu hình, Spring Boot Gradle Plugin phối hợp với dependency-management plugin mới áp dụng BOM của Spring Boot theo quy ước được nhiều dự án sử dụng. Với native Gradle platform, cần nhập cả BOM thích hợp hoặc quy định versions tương ứng một cách minh bạch.

Hai cách quản lý version đều có thể hợp lệ. Mục tiêu không phải “cái nào ngắn hơn” mà là:

1. Mọi `spring-cloud-*` dependency có version **phù hợp release train**.
2. Spring Cloud Contract Gradle plugin có version **tương thích** với dependency contract/verifier.
3. Gradle dependency graph không chứa hai phiên bản xung đột của cùng thư viện.
4. Dự án và CI dùng cùng Gradle Wrapper/lockfile/version catalog khi có.

Nếu dependency bị conflict, hãy kiểm dependency graph của đúng configuration thay vì chỉ đọc một dòng `testImplementation`:

~~~shell
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-contract-verifier --configuration testRuntimeClasspath
~~~

Đây là các lệnh **người học có thể chạy để điều tra**; bài này không thực thi Gradle thay cho dự án.

## 16. Messaging contracts: dependency và test setup có khác

Spring Cloud Contract không chỉ xác minh HTTP. Với sự kiện `OrderCreated`, producer có thể phát message tới `orders.created`:

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
            header('eventType', 'OrderCreated')
        }
        body(
            eventId: 'evt-00042',
            orderId: 'ORD-1042'
        )
    }
}
~~~

Trong Gradle, ngoài Contract Verifier starter, ứng dụng **cần các dependency messaging thật** mà nó sử dụng (ví dụ Spring Cloud Stream/binder phù hợp). Generated test cần một **base test trigger method** tên `publishOrderCreated()` và **messaging adapter/MessageVerifier/test binder** để quan sát output.

**Không chọn `testMode=MOCKMVC` rồi coi đó là cấu hình messaging verification hoàn chỉnh.** `MOCKMVC` chỉ liên quan request HTTP trên Spring MVC; message contract cần test environment có kênh gửi/nhận phù hợp.

Khi đóng gói artifact `stubs`, messaging contract có thể được Stub Runner dùng để phát **message mẫu** bằng một `label` và messaging integration. Consumer không nhất thiết dùng HTTP port cho kịch bản đó. Trong CI, hãy kiểm riêng **serialization/wire metadata** khi consumer phụ thuộc JSON bytes, Avro/Protobuf hoặc broker header mapping.

## 17. Multi-module Gradle: áp dụng plugin ở đâu?

Một repository Gradle có thể gồm:

~~~text
commerce-platform/
├── settings.gradle
├── build.gradle
├── order-service/
│   └── build.gradle
├── inventory-service/
│   └── build.gradle
└── checkout-service/
    └── build.gradle
~~~

**Không áp dụng Contract Verifier plugin lên mọi module chỉ vì chúng nằm trong cùng repository.** Hãy xác định vai trò:

| Module | Vai trò | Cấu hình cần thiết |
| --- | --- | --- |
| `order-service` | Producer API Order | Plugin Contract Verifier + verifier test dependency + contracts/base test. |
| `inventory-service` | Producer API Inventory | Plugin Contract Verifier + verifier test dependency + contracts/base test. |
| `checkout-service` | Consumer của hai producer | Stub Runner test dependency + hai artifact stubs; plugin Verifier chỉ cần nếu nó cũng là producer. |

Nếu dùng root `build.gradle` để quản lý plugin versions, có thể khai báo plugin với `apply false` rồi áp dụng vào **subproject thực sự là producer**. Ví dụ:

~~~groovy
// Root build.gradle: chỉ công bố phiên bản plugin.
plugins {
    id 'org.springframework.cloud.contract' version '4.1.5' apply false
}
~~~

Và tại `order-service/build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.cloud.contract'
}
~~~

Đây là **mảnh ghép của multi-module build**, không phải cấu hình đầy đủ cho module. Gradle plugin resolution, `group`/`version`, BOM, dependencies và publication vẫn cần thiết ở scope thích hợp. Nếu root build kiểm version nhưng subproject thiếu plugin application, sẽ không có generated contract tasks của producer đó.

**Mỗi producer nên xuất JAR `stubs` theo tọa độ riêng.** Consumer đa producer cần nạp hai artifact theo group/artifact/version chính xác; không gộp ngẫu nhiên mappings của nhiều service vào một JAR rồi mất nguồn sở hữu hợp đồng.

## 18. Tích hợp CI: build → verify → publish → consumer test

~~~mermaid
flowchart TD
    A["Producer commit thay API/contract"] --> B["Gradle resolve plugins + dependencies"]
    B --> C["generateContractTests / generateClientStubs"]
    C --> D["./gradlew clean test"]
    D --> E{"Generated producer tests đã chạy và đạt?"}
    E -->|Không| F["Chặn artifact publication"]
    E -->|Có| G["verifierStubsJar + Maven publication"]
    G --> H["Publish stubs theo version"]
    H --> I["Consumer Gradle test + Stub Runner"]
    I --> J["Chạy mã client thật với stub"]
    J --> K["Kiểm response, request mapping, compatibility"]
~~~

Một pipeline producer tối thiểu nên:

1. Sử dụng **Gradle Wrapper** và Java toolchain được cấu hình/khả dụng trên runner.
2. Resolve plugin/dependencies từ repository có quyền truy cập và kiểm version compatibility.
3. Chạy **producer generated tests** với JUnit/Spock engine phù hợp.
4. Xác nhận **số lượng test đã thực thi**, không chỉ kiểm mã thoát 0 của lệnh build.
5. Nếu verification **FAIL**, dừng bước publish.
6. Nếu verification **PASS**, tạo/kiểm JAR classifier `stubs` và xuất bản đúng tọa độ.
7. Consumer CI **tải đúng version stub** và chạy consumer tests qua Stub Runner.

Với producer Gradle, lệnh kiểm thử thường là:

~~~shell
./gradlew clean test
~~~

Với consumer Gradle:

~~~shell
./gradlew test
~~~

**Không áp đặt thói quen Maven lên Gradle:** `mvn verify`, `mvn install` và `./gradlew test` thuộc hai lifecycle khác nhau. `./gradlew publishToMavenLocal` chỉ publish publications được khai báo, không phải thay thế cho việc sinh/chạy producer contract tests.

### 18.1. Kiểm chính artifact được phát hành

Sau bước publish, cần chứng minh:

- File stub thực sự có **classifier `stubs`**, không chỉ là JAR ứng dụng.
- Maven coordinates của artifact khớp `ids` trong `@AutoConfigureStubRunner`.
- Nội dung có HTTP mappings hoặc messaging contracts theo loại hợp đồng đã chọn.
- Những tài nguyên đó xuất phát từ **cùng commit/version đã được producer xác minh**.
- Consumer test tải artifact từ `LOCAL` hoặc `REMOTE` đúng nơi, không dựa vào file build cũ còn sót.

Không giả định Gradle mặc định publish stub chỉ vì `maven-publish` đã được apply; hãy xác minh `publishing.publications` và log/tọa độ xuất bản thực tế.

## 19. Lỗi phổ biến khi tích hợp Gradle

| Triệu chứng | Nguyên nhân có thể | Cách điều tra/sửa |
| --- | --- | --- |
| `Plugin [id: 'org.springframework.cloud.contract'] was not found` | Thiếu version hoặc plugin repository, phiên bản plugin không có ở nguồn khai báo. | Kiểm `plugins`, `pluginManagement.repositories`, quyền truy cập và phiên bản được hỗ trợ. |
| Gradle báo không tồn tại `contracts` extension. | Plugin chưa được apply ở module đang cấu hình. | Kiểm `plugins` trong đúng subproject, không chỉ ở root `apply false`. |
| Không có `generateContractTests`. | Plugin không áp dụng, sai module hoặc phiên bản có task name khác. | Chạy `./gradlew tasks --all` trong đúng project, kiểm plugin resolution. |
| `build` xanh nhưng không có generated tests. | Contract đặt sai thư mục, generator/task không nối vào test, test bị skip. | Kiểm contract paths, generated sources, test report và task graph. |
| Test Java không chạy với `JUNIT5`. | Thiếu JUnit Platform engine/configuration. | Kiểm `useJUnitPlatform()`, test dependencies và Gradle test report. |
| Generated test không tìm thấy base class. | `baseClassForTests` sai package hoặc base test không ở test source set. | So exact class name, test compiled classes và generated test imports. |
| MockMvc test lỗi chưa khởi tạo HTTP client. | Base test thiếu `RestAssuredMockMvc.mockMvc(mockMvc)` hoặc Spring test context. | Kiểm `@AutoConfigureMockMvc`, `@BeforeEach` và testMode. |
| `NoSuchMethodError` hoặc `NoClassDefFoundError`. | BOM, Contract Plugin, Verifier starter hoặc Spring Boot không tương thích. | Kiểm dependency graph và release train; không sửa bằng version tùy tiện. |
| Không có `verifierStubsJar`. | Task name khác theo phiên bản, plugin thiếu hoặc đóng gói chưa được cấu hình. | Kiểm `tasks --all` và cơ chế stub packaging của plugin đang dùng. |
| `publishToMavenLocal` chạy nhưng consumer không tìm thấy stub. | Chưa publish classifier `stubs`, sai group/artifact/version hoặc Maven local khác môi trường. | Kiểm Maven publication, artifact metadata và Stub Runner `ids`. |
| Consumer báo WireMock 404 dù stub đã tải. | Request không match mapping, base URL sai hoặc mapping của version khác. | Xem stub mappings và request journal; phân biệt no-match với 404 nghiệp vụ. |
| CI xanh dù producer sửa field phá hợp đồng. | Generated tests chưa chạy hoặc assertion quá lỏng. | Thử đổi field có chủ đích, xem report, sửa contract/setup. |
| Khi chạy nhiều job, port WireMock bị chiếm. | Consumer hardcode port `8089`. | Dùng Stub Runner port động và `StubFinder` tra URL. |
| Groovy contract có nhưng sinh Spock ngoài ý muốn. | `testFramework` hoặc Gradle test toolchain không khớp. | Đối chiếu `contracts` extension, test engine và generated source type. |

**Chẩn đoán theo chuỗi:** plugin được nạp → dependency resolve → contract được tìm thấy → generated sources tồn tại → base test chạy → producer verification thực thi → stub JAR được sinh → publication đúng tọa độ → consumer Stub Runner tải và chạy được.

## 20. Bài thực hành từ Gradle plugin đến consumer test

Thực hiện trên hai project Spring Boot độc lập (`order-service` và `billing-service`):

1. **Chuẩn bị Gradle Wrapper**, JDK thích hợp, repository và Spring Boot/Spring Cloud/Spring Cloud Contract versions tương thích.
2. **Áp dụng `org.springframework.cloud.contract`** vào producer `order-service/build.gradle`, khai báo `java`, Spring Boot, BOM và `testImplementation spring-cloud-starter-contract-verifier`.
3. **Cấu hình `contracts`** với `baseClassForTests`, `testFramework=JUNIT5` và `testMode=MOCKMVC`.
4. **Viết hợp đồng Groovy** cho `GET /api/orders/42`, status 200 và JSON `PAID`; có thể thử YAML tương đương nhưng chỉ giữ một DSL trong lượt build.
5. **Tạo controller và ContractTestBase**, kiểm việc nối MockMvc và fixture trước khi generated tests gửi request.
6. **Kiểm task graph** bằng `./gradlew tasks --all`, sau đó chạy `./gradlew clean test`; xác nhận generated test thật sự được thực thi và PASS.
7. **Cố tình gây breaking change**: đổi response `status=PAID` thành `status=PENDING` trong controller mà không đổi contract. Chạy lại và xác nhận test **FAIL**; hoàn nguyên.
8. **Đóng gói artifact stubs**, kiểm task `verifierStubsJar`/cơ chế đóng gói ở phiên bản plugin và cấu hình `maven-publish` nếu cần.
9. **Publish stub vào Maven local** bằng `./gradlew publishToMavenLocal` sau khi verification đạt; đối chiếu tọa độ `com.acme:order-service:1.0.0:stubs`.
10. **Ở consumer Billing**, thêm `testImplementation spring-cloud-starter-contract-stub-runner`, cấu hình BOM và JUnit Platform.
11. **Viết OrderClient thật**, dùng `@AutoConfigureStubRunner` với `LOCAL` và `StubFinder` để tìm URL động; chạy `./gradlew test` rồi assert DTO `id=42`, `status=PAID`.
12. **Thử đổi Gradle Plugin/BOM không tương thích trong nhánh thử nghiệm**, quan sát lỗi resolve/compile/test rồi phục hồi; ghi lại cách quyết định một bộ version tương thích.
13. **Đưa vào CI**: producer test bắt buộc → stub publication → consumer test dùng version xác định; không publish khi generated producer test chưa đạt.

**Tiêu chí hoàn thành:** bạn có một `build.gradle` producer chứa **plugin và dependency đúng vai trò**, generated producer test được sinh và thực thi, JAR `stubs` được publish đúng tọa độ, và consumer chạy **mã client thật** qua Stub Runner mà không phải khởi động producer.

## 21. Câu hỏi tự kiểm tra

1. Vì sao chỉ thêm `spring-cloud-starter-contract-verifier` vào `testImplementation` chưa bảo đảm generated producer tests được sinh?
2. Plugin `org.springframework.cloud.contract` và dependency `spring-cloud-starter-contract-verifier` khác nhau về trách nhiệm như thế nào?
3. `spring-cloud-dependencies` BOM giúp quản lý phần nào và có tự quyết định phiên bản plugin trong `plugins` không?
4. Vì sao nên dùng `testImplementation` thay vì `implementation` cho verifier?
5. Khối `contracts { baseClassForTests; testFramework; testMode }` điều khiển những gì?
6. Một hợp đồng viết bằng Groovy DSL có buộc generated test phải dùng Spock/Groovy không?
7. Khi ứng dụng dùng Spring WebFlux, `MOCKMVC` có còn là lựa chọn mặc định tốt nhất không?
8. Vì sao `./gradlew clean test` thành công mà báo cáo 0 generated tests chưa chứng minh producer đúng hợp đồng?
9. Vì sao không sửa trực tiếp Java test được sinh trong `build/`?
10. JAR application và JAR classifier `stubs` khác nhau thế nào?
11. Vai trò của `maven-publish` và `verifierStubsJar` trong quá trình tạo/publish artifact stub?
12. Vì sao `publishToMavenLocal` không đồng nghĩa consumer ở một CI runner khác đã tải được artifact?
13. `StubsMode.LOCAL` khác `REMOTE` về nơi lấy JAR thế nào; có quyết định HTTP port WireMock không?
14. Tại sao consumer thường chỉ cần `spring-cloud-starter-contract-stub-runner` mà không cần áp dụng Contract Verifier Gradle Plugin?
15. Trong multi-module Gradle, tại sao không áp dụng verifier plugin lên mọi module một cách tự động?
16. Để chứng minh đã tích hợp thành công, cần xác minh những bước nào từ contract đến consumer client?

**Ghi nhớ:** **Tích hợp Spring Cloud Contract với Gradle cần hai việc song hành: áp dụng đúng build plugin để sinh test/stubs, và khai báo đúng dependency để test chạy được**. Ở producer, chọn `org.springframework.cloud.contract`, `spring-cloud-starter-contract-verifier`, BOM/version tương thích, `contracts` extension và base test thích hợp. Xác nhận generated tests thật sự **chạy và phát hiện khi producer sai hợp đồng** trước khi đóng gói/phát hành JAR classifier `stubs`. Ở consumer, dùng `spring-cloud-starter-contract-stub-runner`, pin version artifact và chạy mã client thật qua stub. Khi kết nối đúng Gradle tasks với CI, nhóm có thể phát hiện thay đổi API không tương thích **mà không cần dựng đồng thời mọi microservice**.
