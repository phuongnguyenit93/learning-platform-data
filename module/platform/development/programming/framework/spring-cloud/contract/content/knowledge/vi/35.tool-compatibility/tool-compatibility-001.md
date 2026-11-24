# Đối chiếu Spring Boot, Spring Cloud Contract và phiên bản plugin

## Mục tiêu bài học

Trong **Spring Cloud Contract**, producer và consumer thống nhất hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**, sinh kiểm thử phía producer, đóng gói stub và dùng **Stub Runner** trong consumer tests. Quy trình này chỉ hoạt động đáng tin khi **Spring Boot**, **Spring Cloud release train**, **Spring Cloud Contract libraries**, **Maven/Gradle plugin**, Java/JDK và công cụ kiểm thử được chọn thành một **tổ hợp tương thích**.

Chương **Tương thích công cụ** không chỉ dạy cách khai báo một version. Mục tiêu là biết **version nào thuộc phạm vi nào**, **cách kiểm chứng version thực được phân giải**, và **khi nào một build xanh chưa phải bằng chứng tương thích producer–consumer**.

Sau bài học, bạn có thể:

- Phân biệt Spring Boot version, Spring Cloud release train, Spring Cloud Contract (SCC) library/plugin version và version của stub artifact.
- Hiểu sự khác nhau giữa **BOM/dependency management** với **Maven pluginManagement** và **Gradle plugin resolution**.
- Tạo cấu hình producer Maven/Gradle nhất quán, tránh ghép nhầm các line phiên bản.
- Đối chiếu JDK, Maven/Gradle wrapper, Groovy, JUnit, Spring MVC/MockMvc, WebFlux/WebTestClient và WireMock.
- Dùng effective POM, dependency tree, Gradle dependencyInsight và generated source để tìm lỗi.
- Nâng cấp framework/tooling mà không đánh mất producer contract tests hoặc consumer Stub Runner coverage.
- Thiết kế ma trận CI và hồ sơ bằng chứng cho tool compatibility **và** API compatibility.

> **Nguyên tắc về phiên bản:** Không có phép tính đơn giản kiểu `Spring Boot X.Y = Spring Cloud Contract X.Y` áp dụng mọi release. Bảng các phiên bản được hỗ trợ có thể thay đổi. Trước khi dùng một tổ hợp cụ thể, hãy xem **bảng tương thích Spring Boot–Spring Cloud và release notes/tài liệu chính thức của Contract plugin cho đúng bản đó**. Các nhãn phiên bản trong bài là placeholders minh họa phương pháp, **không phải bảng tương thích đã xác nhận**.

## 1. Vì sao hợp đồng đúng vẫn có thể làm build FAIL?

Giả sử contract:

~~~yaml
description: "Lấy đơn hàng đã thanh toán"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

Hợp đồng không phức tạp, nhưng người học có thể gặp:

- Plugin không được tải hoặc không sinh generated tests.
- Generated tests import JUnit API không có trên test classpath.
- `NoSuchMethodError`/`ClassNotFoundException` ở Spring, WireMock, Jackson hoặc RestAssured.
- Base test dùng MockMvc trong khi test mode được sinh cho WebTestClient.
- Maven báo `BUILD SUCCESS` dù không có producer contract tests chạy.
- Stub Runner consumer tải mappings từ artifact/version cũ.
- Producer test PASS nhưng consumer không đọc được format response mới.

Mỗi lỗi thuộc một lớp khác nhau:

| Lớp | Câu hỏi |
| --- | --- |
| **Toolchain** | JDK, build tool, plugin và libraries có chạy được cùng nhau? |
| **Contract syntax/semantics** | DSL có mô tả đúng hành vi API/message? |
| **Producer verification** | Generated tests có thực thi và chứng minh implementation? |
| **Stub packaging** | Artifact có đúng mappings/response files và checksum? |
| **Consumer verification** | Stub Runner và consumer có xử lý đúng artifact mới? |

**Không sửa DSL matcher chỉ để che lỗi classpath**, và cũng không nâng plugin mù quáng khi producer thực sự vi phạm contract.

## 2. Sơ đồ các lớp phiên bản

~~~mermaid
flowchart TD
    J["JDK + Maven/Gradle wrapper"] --> B["Spring Boot"]
    B --> C["Spring Cloud release train"]
    C --> L["SCC test/runtime libraries"]
    B --> F["Spring Framework/Jackson/Test"]
    M["Maven Contract plugin"] --> G["Generated tests + stub mappings"]
    D["Gradle Contract plugin"] --> G
    L --> G
    F --> G
    G --> A["Stub JAR của producer"]
    A --> SR["Stub Runner phía consumer"]
    SR --> CT["Consumer tests"]
~~~

Sơ đồ thể hiện **mối quan hệ phải kiểm tra**, không khẳng định Cloud BOM quản lý mọi công cụ trong hình.

| Thành phần | Ví dụ | Vai trò | Cơ chế version thông thường |
| --- | --- | --- | --- |
| Java/JDK | `JAVA_VERSION` | Biên dịch, chạy tool và tests | CI image/toolchain |
| Spring Boot | `BOOT_VERSION` | Framework, auto-config và test stack | Boot parent/BOM/Gradle plugin |
| Spring Cloud | `CLOUD_TRAIN` | Tập các Cloud projects tương thích | `spring-cloud-dependencies` BOM |
| Spring Cloud Contract | `SCC_LIBRARY_VERSION` | Verifier, Stub Runner, thư viện tests | Cloud BOM hoặc dependency management |
| Maven Contract plugin | `SCC_MAVEN_PLUGIN_VERSION` | Sinh tests/mappings/stub artifacts | `build.plugins/pluginManagement` |
| Gradle Contract plugin | `SCC_GRADLE_PLUGIN_VERSION` | Tasks và test generation | Gradle `plugins/pluginManagement` |
| JUnit/Test engine | `JUNIT_VERSION` | Discover/chạy generated tests | Test dependencies + runner |
| WireMock | `WIREMOCK_VERSION` | HTTP stub mappings/runtime | Resolved dependency graph |
| Stub artifact | `order-service:2.5.0:stubs` | Bộ responses giả lập producer | Version release của ứng dụng |

Đặc biệt, `2.5.0` trong `order-service:2.5.0:stubs` là **phiên bản ứng dụng**, không phải phiên bản Spring Cloud Contract plugin.

## 3. Spring Cloud release train và Spring Boot

Spring Cloud phối hợp nhiều projects, ví dụ Config, Gateway và Contract, theo một **release train**. Spring Boot có lifecycle riêng. Một release train được xác định là hỗ trợ những dòng Spring Boot nhất định.

Có thể gặp các tên train theo dạng `2023.0.x`, `2024.0.x` hoặc `2025.0.x`. Đây là **ví dụ cách đặt tên**, không phải lời khẳng định mọi patch của từng train hỗ trợ mọi Boot minor có năm gần tương ứng.

### Quy trình chọn cặp đúng

1. Xác định Spring Boot version hiện tại và version đích.
2. Tra **bảng tương thích chính thức của Spring Cloud** cho đúng Boot minor.
3. Chọn release train còn được hỗ trợ theo chính sách tổ chức.
4. Kiểm tra **SCC version** được train quản lý.
5. Đọc reference/release notes của **SCC Maven/Gradle plugin** tương ứng.
6. Xác minh minimum JDK, Maven/Gradle và test framework versions.
7. Chốt version trong repository/CI và chạy producer + consumer contract tests.

**Bảng tương thích là nguồn đầu vào cho quyết định**, không phải thứ suy ra từ việc build local thành công.

### Tại sao Boot major vẫn chưa đủ?

Một dòng Cloud train có thể chỉ hỗ trợ một số **Boot minor** nhất định. Vì vậy “đều là Spring Boot 3” chưa chứng minh train đã chọn hỗ trợ cả hai bản Boot 3.x cụ thể.

Nếu Boot version được nâng mà Cloud train giữ nguyên, cần đánh giá khả năng tương thích dựa trên tài liệu, kể cả khi ứng dụng vẫn compile.

## 4. Spring Boot BOM và Spring Cloud BOM quản lý gì?

Spring Boot parent/BOM quản lý nhiều dependencies cho:

- Spring Framework, Spring Test, Spring Boot Test.
- Jackson và các thư viện serialization phổ biến.
- JUnit Jupiter/test starter.
- Reactor, Netty và một số thành phần logging.
- Các starter và thư viện tích hợp trong hệ Boot.

Spring Cloud BOM quản lý các **Spring Cloud project dependencies** tương ứng với train.

Do đó, với producer contract tests, một bộ dependencies hợp lý thường là:

~~~text
Spring Boot test libraries      <- Boot dependency management
Spring Cloud Contract Verifier  <- Cloud dependency management
Spring Cloud Contract plugin    <- Plugin version riêng
JDK + Maven/Gradle              <- Wrapper/toolchain
~~~

### Quy tắc giảm xung đột

- Ưu tiên version từ BOM của nền tảng.
- Hạn chế explicit version overrides ở các libraries đã được BOM quản lý.
- Đối chiếu version **thực tế resolved**, không chỉ nhìn khai báo.
- Khi buộc phải override vì bug/security fix, phải review binary/runtime compatibility.
- Không copy một dependency version từ project Boot cũ sang project Boot mới mà không xem graph.

**Nếu lỗi `NoSuchMethodError` nằm trong `spring-core`, nguyên nhân có thể là dependency override sai**, không phải contract DSL.

## 5. BOM **không tự quản lý Maven/Gradle plugin version**

Đây là sai lầm quan trọng nhất của bài.

### Dependency Management trong Maven

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-dependencies</artifactId>
      <version>RELEASE_TRAIN_VERSION</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

Dependency:

~~~xml
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-starter-contract-verifier</artifactId>
  <scope>test</scope>
</dependency>
~~~

có thể nhận version từ BOM phù hợp.

Nhưng Maven Contract plugin:

~~~xml
<plugin>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-contract-maven-plugin</artifactId>
  <version>CONTRACT_PLUGIN_VERSION</version>
  <extensions>true</extensions>
</plugin>
~~~

cần version từ khai báo plugin hoặc `pluginManagement`. **Import `spring-cloud-dependencies` không mặc nhiên gán version cho `build.plugins`**.

### Gradle cũng có hai đường phân giải

Trong Gradle:

- `dependencies` dùng BOM/`platform(...)`/dependency-management/constraints.
- `plugins` được phân giải qua Gradle plugin marker, plugin repositories và `settings.pluginManagement` hoặc convention plugins.

**Cloud BOM không tự ép Gradle Contract plugin về đúng phiên bản**. Cần đối chiếu plugin version và Contract test dependency version riêng.

## 6. Cấu hình Maven producer mẫu

POM rút gọn dùng placeholders rõ ràng, **phải thay bằng version được xác nhận trước khi chạy**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>BOOT_VERSION_DA_XAC_NHAN</version>
    <relativePath/>
  </parent>

  <groupId>com.example.orders</groupId>
  <artifactId>order-service</artifactId>
  <version>2.5.0</version>

  <properties>
    <java.version>JAVA_VERSION_DA_XAC_NHAN</java.version>
    <spring-cloud.version>RELEASE_TRAIN_DA_XAC_NHAN</spring-cloud.version>
    <contract-plugin.version>CONTRACT_PLUGIN_VERSION</contract-plugin.version>
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

  <dependencies>
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
      <artifactId>spring-cloud-starter-contract-verifier</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-contract-maven-plugin</artifactId>
        <version>${contract-plugin.version}</version>
        <extensions>true</extensions>
        <configuration>
          <baseClassForTests>
            com.example.orders.contract.OrderContractBase
          </baseClassForTests>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Đây là khung minh họa, không phải POM chạy được khi còn placeholders**:

- `java.version` phải là giá trị Java hợp lệ như `17`, không phải chữ placeholder.
- Contract plugin version phải tương ứng với Contract library line được Cloud train hỗ trợ.
- `baseClassForTests` phải là lớp test có thật, với setup HTTP/message phù hợp.
- Nếu producer dùng WebFlux, thay `spring-boot-starter-web` và test mode thích hợp.
- Plugin có mặt trong POM chưa đủ để chứng minh goals chạy và generated tests được discover.

### Lưu ý Maven parent

Không suy Boot parent version từ `spring-cloud.version`. Hai cơ chế release và quản lý version khác nhau, dù chúng cần tương thích.

## 7. Kiểm tra Maven effective configuration

Những lệnh chẩn đoán phổ biến:

~~~bash
# POM sau khi áp dụng parent và dependency/plugin management.
./mvnw -B help:effective-pom

# Spring Cloud dependencies đã được phân giải.
./mvnw -B dependency:tree -Dincludes=org.springframework.cloud

# Xem toàn bộ test dependency tree nếu có conflict.
./mvnw -B dependency:tree -Dscope=test

# Xem goals và thông tin cấu hình của Contract Maven plugin.
./mvnw -B help:describe \
  -Dplugin=org.springframework.cloud:spring-cloud-contract-maven-plugin \
  -Ddetail
~~~

Các lệnh dạng nhiều dòng dùng `\` dành cho shell POSIX; trong PowerShell cần viết thành một dòng hoặc dùng cú pháp nối dòng của PowerShell.

| Công cụ | Để trả lời |
| --- | --- |
| `help:effective-pom` | Parent, properties, plugin versions, plugin executions thực là gì? |
| `dependency:tree` | Dependencies test/runtime đang được chọn ở versions nào? |
| `help:describe` | Plugin version đó hỗ trợ goals/options nào? |
| Generated test source | Generator thực sinh code gì và imports API nào? |
| Surefire/Failsafe reports | Generated tests có thật sự chạy? |

**Đừng suy Maven plugin version chỉ từ `dependency:tree`**: plugin có classpath/resolution riêng.

## 8. Cấu hình Gradle producer mẫu

Ví dụ Groovy DSL `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'BOOT_PLUGIN_VERSION'
    id 'io.spring.dependency-management' version 'DEPENDENCY_MANAGEMENT_PLUGIN_VERSION'
    id 'org.springframework.cloud.contract' version 'CONTRACT_PLUGIN_VERSION'
}

group = 'com.example.orders'
version = '2.5.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(JAVA_VERSION)
    }
}

ext {
    set('springCloudVersion', 'RELEASE_TRAIN_VERSION')
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
    baseClassForTests = 'com.example.orders.contract.OrderContractBase'
}
~~~

Các giá trị `BOOT_PLUGIN_VERSION`, `CONTRACT_PLUGIN_VERSION`, `JAVA_VERSION` và train version phải được thay; ví dụ không tự chạy nguyên trạng. Một dự án có thể dùng `platform(...)` thay cho `io.spring.dependency-management`; khi đó syntax import BOM sẽ khác.

**Ba version cần kiểm tra độc lập:**

1. Gradle **Spring Boot plugin**.
2. Gradle **Spring Cloud Contract plugin**.
3. `spring-cloud-dependencies` BOM và SCC test libraries được resolved từ nó.

Không có quy tắc “hai plugin đều thuộc Spring nên phải có cùng version”.

## 9. Kiểm tra Gradle dependencies và plugin resolution

~~~bash
# Buildscript/plugin dependencies.
./gradlew buildEnvironment

# Dependency graph của test runtime.
./gradlew dependencies --configuration testRuntimeClasspath

# Giải thích version Contract Verifier đã được chọn.
./gradlew dependencyInsight \
  --configuration testRuntimeClasspath \
  --dependency spring-cloud-contract-verifier

# Danh sách tasks của plugin trên project thực.
./gradlew tasks --all

# Nếu có task generateContractTests trong phiên bản đang dùng:
./gradlew help --task generateContractTests
~~~

Tên task `generateContractTests` là một tên thường gặp; task chính xác và cách nối vào lifecycle có thể khác tùy plugin/version/source set. Hãy xem `tasks --all` để biết kết quả thật.

Khi Gradle báo `Plugin ... was not found`, cần điều tra **plugin id**, **version**, `settings.pluginManagement.repositories`, Gradle Plugin Portal/corporate mirror, proxy/cache và Gradle wrapper. Không đổi `spring-cloud-starter-contract-verifier` dependency version để chữa lỗi **plugin resolution**.

## 10. Ví dụ hai dạng lệch version nguy hiểm

### Plugin mới hơn, thư viện test vẫn cũ

~~~text
Boot:               BOOT_A
Cloud train:        TRAIN_A
Contract library:   CONTRACT_A (theo BOM)
Contract plugin:    CONTRACT_B (override độc lập)
~~~

Nguy cơ: generated tests import API không còn phù hợp test classpath, DSL parser thay đổi hoặc mappings không tương thích với runner. Một số patch combinations có thể dùng được nếu đã được xác nhận, nhưng **không mặc định hợp lệ**.

### BOM mới hơn, plugin vẫn cũ

~~~text
Boot:               BOOT_B
Cloud train:        TRAIN_B
Contract library:   CONTRACT_B
Contract plugin:    CONTRACT_A (quên nâng)
~~~

Nguy cơ: plugin cũ sinh code cho runtime mới thiếu/đổi API, generated tests không compile, hoặc test/packaging defaults không còn phù hợp.

**Cách sửa đúng:** lấy **declared lẫn resolved versions**, đối chiếu với release train được hỗ trợ, align các thành phần theo một baseline có bằng chứng, rồi chạy generated producer tests và Stub Runner.

Không nên đổi matcher/DTO chỉ để vượt qua một lỗi binary compatibility ở generator.

## 11. Producer và consumer có bắt buộc cùng Boot version?

**Không nhất thiết.** Khi chạy production, hai service giao tiếp qua HTTP hoặc messaging chứ không chia sẻ JVM classpath.

~~~text
Producer Order Service:
  Spring Boot      = BOOT_P
  Spring Cloud     = TRAIN_P
  SCC plugin       = CONTRACT_P
  Stub artifact    = com.example.orders:order-service:2.5.0:stubs

Consumer Checkout:
  Spring Boot      = BOOT_C
  Spring Cloud     = TRAIN_C
  Stub Runner      = CONTRACT_C
  Resolved stub    = order-service:2.5.0:stubs
~~~

Producer và consumer có thể dùng hai generation Boot khác nhau khi **giao thức và hành vi** vẫn tương thích. Nhưng consumer test classpath phải **tự tương thích** với Boot/Cloud train của consumer:

- Stub Runner library có chạy được trong consumer test runtime không?
- Stub JAR được sinh từ plugin producer có mapping format mà runner đọc được không?
- WireMock dependencies/extensions có conflict không?
- Consumer DTO/deserializer có nhận được body/schema mới không?

**Producer compile thành công không chứng minh Stub Runner consumer tương thích.** Hai phía cần có evidence riêng.

## 12. Stub artifact version khác plugin version

~~~text
Producer application version: 2.5.0
Producer stub coordinate:    com.example.orders:order-service:2.5.0:stubs
SCC plugin version:         CONTRACT_PLUGIN_VERSION
~~~

`2.5.0` thuộc **Order Service**. `CONTRACT_PLUGIN_VERSION` thuộc **tool sinh tests/stubs**. Chúng không cần bằng nhau và không có phép ánh xạ số học giữa hai giá trị.

Một Stub Runner ID minh họa:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-service:2.5.0:stubs:8090",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.test/maven/releases"
)
class CheckoutContractTest {
    // Consumer assertions ở đây.
}
~~~

Đây là **khung chú thích** cần imports/dependencies/client wiring/assertions, không phải test hoàn chỉnh. Đọc ID:

~~~text
com.example.orders : order-service : 2.5.0 : stubs : 8090
groupId             artifactId       version  classifier port
~~~

Port là thông số Stub Runner runtime, **không phải một phần của Maven artifact identity**.

## 13. WireMock, Stub Runner và định dạng mappings

Spring Cloud Contract có thể chuyển DSL thành mappings/response resources phục vụ HTTP stubbing. Nhưng **WireMock runtime**, **Stub Runner**, **mapping format** và **SCC plugin** là những thành phần có khả năng thay đổi theo line.

Các rủi ro:

- Runtime WireMock không hiểu property mới trong mapping JSON.
- Custom response transformer/extension dùng API WireMock major cũ.
- Project ép WireMock dependency sang một major không được Stub Runner line hỗ trợ.
- Stub Runner start được nhưng request unmatched do mapping/body matcher khác.
- Artifact bị tạo từ plugin khác hoặc đóng gói thiếu response files.

Cách kiểm tra:

1. Xác định plugin version đã sinh mappings.
2. Liệt kê nội dung artifact `-stubs.jar`.
3. Xác định WireMock version **resolved ở consumer**.
4. Đọc parser/startup errors và request journal.
5. Nếu dùng extension, kiểm tra API của extension trên WireMock major hiện hành.
6. Gửi một request khớp scenario rồi assert response, không chỉ kiểm tra server khởi động.

**Một security override cho WireMock vẫn cần regression test**; việc nâng major độc lập có thể giải quyết một advisory nhưng gây lỗi tương thích extension hoặc Stub Runner.

## 14. JDK và Maven/Gradle wrapper cũng là phiên bản cần đối chiếu

Những lỗi liên quan toolchain:

~~~text
UnsupportedClassVersionError
invalid target release
release version not supported
class file has wrong version
NoSuchMethodError
NoClassDefFoundError
~~~

`UnsupportedClassVersionError` thường nói JVM chạy class không hiểu phiên bản bytecode. `invalid target release` thường liên quan compiler không hỗ trợ giá trị release. `NoSuchMethodError` có thể là dependency binary mismatch, không nhất thiết do JDK.

### Ba câu hỏi Java riêng

| Lớp | Cần xác định |
| --- | --- |
| **JVM chạy build tool** | Maven/Gradle daemon chạy JDK nào? |
| **Compiler/toolchain** | Generated test và application compile với `--release` nào? |
| **JVM chạy tests** | Test runner/container dùng Java nào để load class? |

Một build có thể compile bằng toolchain khác JVM chạy Maven/Gradle. Đừng chỉ dựa vào `JAVA_HOME` ở laptop khi CI dùng image/toolchain khác.

Ví dụ lệnh xem môi trường:

~~~bash
java -version
./mvnw -version
./gradlew --version
~~~

Trong dự án thật chỉ chạy wrapper đúng build tool đang sử dụng; các lệnh minh họa, không bắt buộc chạy cả Maven và Gradle.

### Chuyển generation Spring Framework

Một chuyển đổi lớn trong hệ Spring hiện đại là sử dụng nhiều **Jakarta EE APIs** với package `jakarta.*` thay vì các package `javax.*` đời trước (như Servlet, Validation, Persistence). Không phải mọi `javax.*` trong Java đều đổi. Nếu generated test hoặc dependency web báo missing `javax.servlet`/`jakarta.servlet`, hãy kiểm tra Boot/Framework generation và starter/test libraries, không tự thêm JAR `javax.servlet` cũ.

## 15. Groovy DSL và Groovy runtime/version

Groovy DSL được plugin xử lý trong build. Groovy runtime của Maven plugin, Gradle/embedded Groovy và Groovy trong test dependencies **có thể thuộc classpaths khác nhau**.

Một số triệu chứng:

- `MissingMethodException`/`MissingPropertyException` khi parse contract DSL.
- `NoClassDefFoundError` trong Groovy internals.
- Helper/extension gọi API không có trong Groovy version thực.
- Plugin không hiểu matcher/cú pháp mới.
- Spock hoặc test helper Groovy dùng line không phù hợp framework.

Cách chẩn đoán:

1. Xác định lỗi xảy ra ở **DSL parse**, **generated test compile** hay **test runtime**.
2. Kiểm tra Contract plugin version trước.
3. Kiểm tra direct Groovy overrides và Spock/test dependencies.
4. So sánh DSL với **reference documentation đúng plugin release**.
5. Dùng một contract tối thiểu để tách nguyên nhân nếu cần.
6. Không thêm một Groovy runtime bất kỳ chỉ để loại lỗi class không tìm thấy.

**Một lỗi DSL parser không tự chứng minh hợp đồng sai nghiệp vụ.** Có thể cú pháp được hỗ trợ ở một Contract version khác.

## 16. JUnit và generated test framework

Generated tests có thể được tạo cho test framework/runner khác nhau theo configuration và plugin version.

| Thành phần | Ví dụ cần kiểm tra |
| --- | --- |
| Generated import | `org.junit.Test` hay `org.junit.jupiter.api.Test`? |
| Setup annotation | `@Before` hay `@BeforeEach`? |
| Test engine | JUnit 4, JUnit Jupiter hoặc engine được hỗ trợ? |
| Maven runner | Surefire/Failsafe có discover generated tests không? |
| Gradle Test | Framework và source set được cấu hình đúng chưa? |
| Base class | Generated test extends class phù hợp không? |

Nếu generated test dùng **JUnit Jupiter** nhưng runtime chỉ discover **JUnit 4**, build có thể compile rồi thực thi **0 tests**. Cần kiểm tra generated imports, test reports và runner configuration.

**Điều kiện release gate:** đã có contracts bắt buộc mà `0 generated producer tests` chạy thì phải báo lỗi verification; không được suy PASS chỉ từ Maven/Gradle exit code 0.

## 17. Chọn test mode: MockMvc, WebTestClient và live HTTP

Một lỗi không phải do số version mà do **test mode sai framework**:

| Producer stack | Client/test mode thường phù hợp | Cần xác minh |
| --- | --- | --- |
| Spring MVC | MockMvc và RestAssuredMockMvc | MVC context, base class và generated test wiring |
| Spring WebFlux | WebTestClient/RestAssuredWebTestClient khi version hỗ trợ | Reactive codecs, application context hoặc server binding |
| Live HTTP server | RestAssured/HTTP client tương ứng | HTTP port, TLS, routing và môi trường |
| Messaging | Contract Verifier message testing | Trigger method, test binder/broker, destination |

Một số Contract plugin versions cung cấp test modes dạng `MOCKMVC`, `WEBTESTCLIENT`, `EXPLICIT`. **Giá trị cấu hình và API setup phải được kiểm tra theo plugin release cụ thể**.

### Ví dụ sai wiring

Generated test dùng RestAssuredWebTestClient, nhưng base test lại chỉ cấu hình:

~~~java
@BeforeEach
void setup() {
    RestAssuredMockMvc.mockMvc(mockMvc);
}
~~~

Khi đó, vấn đề là **test client không khớp với generated code**, không nhất thiết vì response body hoặc hợp đồng sai.

### WebFlux có thêm những khác biệt

- Reactor `Mono` và `Flux`, reactive HTTP codecs.
- Test qua application context khác test qua live server.
- Streaming SSE/NDJSON hoặc response vô hạn không giống một JSON object đơn.
- Helper block sai chỗ có thể gây deadlock/stall.
- Filter/security chain có thể khác nếu test sử dụng standalone handler thay vì context thật.

Một plugin có thể sinh thành công static JSON tests nhưng **chưa đủ** để chứng minh streaming behavior trong production. Cần xác định phạm vi contract và test bổ sung.

## 18. Jackson, REST Assured và message converters

Một producer contract có thể dùng:

~~~yaml
description: "Lấy đơn hàng đã thanh toán"
request:
  method: GET
  url: /api/orders/ORD-1001
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

Generated test FAIL khi JSONPath `$.status` không tồn tại có thể do:

- DTO đổi `status` thành `paymentStatus`.
- Jackson dùng naming strategy khác.
- `@JsonIgnore` hoặc `@JsonInclude` khiến field biến mất.
- Test context đăng ký khác module/converter so với application runtime.
- Contract/fixture sai, hoặc producer thực sự phá compatibility.

Những lỗi **không mặc định là version mismatch**. Phải đối chiếu actual response, headers, DTO/serialization, contract revision và generated matcher trước khi nâng dependency.

Ngược lại, `NoSuchMethodError` trong RestAssured/Jackson với stack trace chỉ tới API thư viện là dấu hiệu cần đọc **resolved dependency graph** và các overrides.

## 19. Stub Runner và WireMock có các version độc lập

WireMock là thành phần quan trọng của HTTP stubbing, nhưng có thể tồn tại nhiều cách đóng gói/phân giải theo Spring Cloud Contract line:

- Mappings/response files được sinh bởi Contract plugin.
- Stub JAR chứa mappings và resources, thường dưới cấu trúc `META-INF` theo convention.
- Stub Runner phía consumer tải JAR và khởi động một HTTP stub runtime.
- WireMock runtime cùng extensions xử lý mappings và incoming requests.

Nếu producer plugin và consumer runner thuộc hai line khác nhau, có thể phát sinh format/API mismatch.

### Trường hợp dễ nhầm

Một Stub Runner **đã khởi động** không có nghĩa:

1. Nó đã tải đúng **GAV/classifier/version**.
2. Mappings trong JAR đã được nạp hết.
3. Extensions có load được hay không.
4. Consumer request match ít nhất một mapping.
5. Consumer assertion đã kiểm tra business logic.

Một smoke test tốt gửi request vào chính stub port rồi đối chiếu status/headers/body theo scenario, đồng thời kiểm tra resolved artifact version và checksum khi cần.

### Không hardcode WireMock override tùy tiện

Nếu một dependency transitively kéo bản WireMock khác, không nên ép lên bản mới nhất chỉ để “các số giống nhau”. Cần xem version được SCC/Stub Runner line hỗ trợ, những extensions cần nâng và các security advisories liên quan.

## 20. Công cụ có thể PASS nhưng producer tests thực tế bằng 0

Đây là vấn đề nguy hiểm nhất trong migration:

~~~text
[INFO] BUILD SUCCESS

Generated contracts discovered: 0
Generated producer tests executed: 0
~~~

Trong tình huống này, **toolchain có thể build được nhưng không có bằng chứng producer đáp ứng hợp đồng**.

Nguyên nhân:

- Contracts root không đúng.
- Maven plugin goals không được bind/được bỏ qua.
- Gradle Contract plugin tasks không nằm trong test lifecycle.
- Generated test sources không được compiler/test runner nhận.
- Test framework/engine không discover tests.
- CLI dùng `-DskipTests` hoặc biến môi trường kích hoạt skip.
- Base class/test name/filter không đáp ứng convention.
- CI chỉ chạy module không chứa producer contract tests.

### Quy tắc CI

- Ghi số contract scenarios được phát hiện.
- Kiểm tra generated sources thực có tồn tại.
- Ghi số generated producer tests đã chạy và bị skip.
- Nếu tập contracts bắt buộc khác rỗng nhưng tests thực thi bằng 0, **BLOCK**.
- Kiểm tra producer verification PASS **trước** khi publish stub JAR.

Không thay một assertion lỗi bằng “skip test” rồi gọi migration thành công.

## 21. Compatibility baseline record cần những trường nào?

Một baseline do nhóm tự thiết kế có thể là:

~~~yaml
# Mẫu record, KHÔNG phải output mặc định của Spring Cloud Contract.
schema: "scc-toolchain-baseline/v1"
service: order-service

runtime:
  java_version: "JAVA_VERSION_DA_KIEM_TRA"
  spring_boot_version: "BOOT_VERSION_DA_KIEM_TRA"
  spring_cloud_train: "TRAIN_DA_KIEM_TRA"

build:
  tool: Maven
  wrapper_version: "WRAPPER_VERSION_DA_KIEM_TRA"
  contract_maven_plugin: "PLUGIN_VERSION_DA_KIEM_TRA"

testing:
  contract_libraries: "SCC_VERSION_DA_RESOLVE"
  test_framework: JUNIT5
  http_test_mode: MOCKMVC
  wiremock_runtime: "WIREMOCK_VERSION_DA_RESOLVE"

evidence:
  source_commit: "PRODUCER_COMMIT_THUC_TE"
  contract_revision: "CONTRACT_REVISION_THUC_TE"
  ci_run_id: "CI_RUN_ID"
  generated_tests_report: "LINK_TEST_REPORT"
  verification: "KET_QUA_THUC_TE"
~~~

**Không đưa các placeholder này vào release record rồi tự ghi PASS.** CI cần lấy resolved versions, commit IDs và test results thực.

### Declared version và resolved version

Hai loại thông tin cần tách:

- **Declared:** version đặt trong POM/Gradle/BOM hoặc constraints.
- **Resolved:** version thực được Maven/Gradle chọn sau parent inheritance, dependency mediation và plugin resolution.

Một dependency không khai báo version nhưng được BOM quản lý **vẫn có resolved version**. Một plugin được kế thừa từ parent có thể khác version mà người đọc root POM tưởng.

## 22. Ma trận công cụ khác ma trận API compatibility

### Ma trận A — Khả năng build/verify của một tổ hợp công cụ

| Bộ đề xuất | Boot | Cloud train | Contract plugin | JDK | Generated tests |
| --- | --- | --- | --- | --- | --- |
| A | `BOOT_A` | `TRAIN_A` | `PLUGIN_A` | `JDK_A` | PASS/FAIL |
| B | `BOOT_B` | `TRAIN_B` | `PLUGIN_B` | `JDK_B` | PASS/FAIL |
| C | `BOOT_B` | `TRAIN_A` | `PLUGIN_A` | `JDK_B` | Chỉ nếu được hỗ trợ |

Bảng là **khung kiểm tra**, không phải ma trận phiên bản hợp lệ đã được xác nhận.

### Ma trận B — Consumer phiên bản nào hoạt động với stub producer nào?

| Producer stub | Checkout 1.8 | Checkout 2.0 | Sales Portal 4.1 |
| --- | --- | --- | --- |
| Order 2.4.0 | PASS lịch sử | NOT_RUN | PASS lịch sử |
| Order 2.5.0 | REQUIRED | REQUIRED | REQUIRED |

Hai ma trận không thay thế nhau:

- Ma trận A PASS: build/test toolchain **chạy được**.
- Ma trận B PASS: các consumer **thực sự xử lý** hành vi producer được mô phỏng bằng stub từ producer đã verify.

**Cùng Boot/Cloud versions không tự chứng minh API tương thích**, còn khác Boot/Cloud versions không tự chứng minh API không tương thích.

## 23. Nâng cấp theo bộ, không thay đổi bừa từng thư viện

Một quy trình an toàn:

~~~mermaid
flowchart TD
    A["Chốt baseline đang PASS"] --> B["Tra Boot–Cloud compatibility matrix"]
    B --> C["Chọn SCC line và Contract plugin phù hợp"]
    C --> D["Xác minh JDK/Wrapper/JUnit/Test mode"]
    D --> E["Cập nhật BOM + plugin có chủ đích"]
    E --> F["Đọc effective dependency/plugin versions"]
    F --> G["Sinh + chạy producer contract tests"]
    G --> H{"Tests thực sự chạy PASS?"}
    H -->|Không| X["BLOCK / chẩn đoán"]
    H -->|Có| I["Đóng gói stub artifact + checksum"]
    I --> J["Consumer Stub Runner tải đúng JAR"]
    J --> K{"Required consumer tests PASS?"}
    K -->|Không| X
    K -->|Có| L["Ghi compatibility baseline và release record"]
~~~

### Bước 1 — Chốt baseline cũ

Ghi Boot/Cloud/SCC/plugin/JDK/wrapper/JUnit, producer commit, contract revision, test reports và stub artifact checksum hiện tại.

### Bước 2 — Chọn bộ có tài liệu hỗ trợ

Tra compatibility matrix chính thức cho Boot target, chọn Cloud train, xem SCC release notes/plugin versions và yêu cầu Java/build tool.

### Bước 3 — Nâng theo cụm

Không nhất thiết đổi tất cả versions cùng một ngày, nhưng từng **tổ hợp trung gian phải có cơ sở hỗ trợ**. Đừng vừa đổi API body vừa nâng framework nếu có thể tách commit; làm vậy giúp phân biệt regression nghiệp vụ với lỗi tooling.

### Bước 4 — Kiểm tra resolved graph

Đọc effective POM, Gradle dependency graph, plugin resolution, toolchain. So sánh trước–sau, tìm direct overrides hoặc dependency collision.

### Bước 5 — Sinh và thực thi producer tests

So số contracts discovered, generated test sources, actual tests executed và failures/skips. Không chấp nhận `BUILD SUCCESS` với `0 tests`.

### Bước 6 — Test stubs phía consumer

Đóng gói stub JAR từ cùng contract/producer build; consumer Stub Runner phải dùng đúng version/checksum và assertions thực tế.

### Bước 7 — Ghi evidence rồi mới xét release

Chỉ nói một tổ hợp tương thích **trong phạm vi các kịch bản đã kiểm chứng**. Không suy diễn đến production performance, TLS hoặc mọi consumer bên ngoài.

## 24. Khi chỉ nâng Contract plugin

Tổ hợp:

~~~text
Spring Boot:        BOOT_A
Spring Cloud BOM:   TRAIN_A
Contract library:   SCC_A
Contract plugin:    SCC_PLUGIN_B
~~~

có thể xảy ra vì team sửa một dòng trong `pom.xml` hoặc `build.gradle`.

Nếu plugin B được công bố tương thích với library line A thì có thể sử dụng sau kiểm chứng. Nhưng nếu không có xác nhận, cần dè chừng:

- Mã generated tests dùng API không có trên test classpath.
- DSL syntax/matcher semantics thay đổi.
- Default JUnit/test mode khác.
- Mapping format hoặc stub package layout đổi.
- Build tool/plugin API không còn tương thích.

### Quy tắc xử lý

1. Xác định lý do nâng riêng (bug, security, feature).
2. Đọc release notes và compatibility information.
3. Chốt chính xác SCC libraries và plugin versions.
4. Chạy helper unit tests, generated producer tests và stub tests.
5. Chỉ publish nếu các required consumer versions vượt qua Stub Runner.

Không “cập nhật plugin cho mới” rồi giữ report của build cũ như bằng chứng release mới.

## 25. Khi chỉ nâng Cloud BOM và quên plugin

Tổ hợp:

~~~text
Spring Boot:        BOOT_B
Spring Cloud BOM:   TRAIN_B
Contract library:   SCC_B
Contract plugin:    SCC_PLUGIN_A
~~~

Lúc đó generated source có thể không compile dù Java business code không đổi.

### Các bước điều tra

- Từ Maven effective POM/Gradle plugin config, lấy plugin version thực.
- Từ dependency graph, lấy SCC Verifier version resolved thực.
- Đọc generated test source để tìm method/import lệch.
- Kiểm tra JDK, JUnit engine và base class wiring.
- Align plugin và dependencies theo release đã xác nhận.
- Build sạch rồi chạy lại, lưu test report mới.
- So sánh stub mappings và consumer behavior.

**Không sửa contract fields để chữa lỗi method/import của thư viện.** Contract có thể hoàn toàn đúng nhưng generator và test classpath không cùng line.

## 26. Transitive dependencies và explicit overrides

Một dependency test nội bộ có thể kéo thêm WireMock/Groovy/Jackson/RestAssured khác version:

~~~xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>legacy-test-utils</artifactId>
  <version>LEGACY_VERSION</version>
  <scope>test</scope>
</dependency>
~~~

Những nơi nên kiểm tra:

- Direct dependency versions được pin.
- Import nhiều BOM và thứ tự/độ ưu tiên.
- Maven parent, profiles và module-specific overrides.
- Gradle version catalogs, constraints, `resolutionStrategy.force` và excludes.
- Shared test helper artifacts.
- Custom WireMock extensions và Groovy test runtime.
- Plugin classpath độc lập project dependency graph.

**Không dùng `exclude` theo phản xạ**: loại bỏ một transitive dependency có thể khiến class bị thiếu lúc chạy. Cần hiểu library nào yêu cầu class đó và thay bằng version tương thích đã được kiểm thử.

## 27. Multi-module builds: kiểm tra đúng module

Ví dụ:

~~~text
platform/
├── pom.xml                   # parent BOM/pluginManagement
├── order-service/            # producer
├── checkout-service/         # consumer
└── shared-test-support/      # base test/helper
~~~

Nguy cơ:

- Root quản lý plugin mới, module producer override plugin cũ.
- Shared helper được compile trên Java cao hơn JVM test.
- Contract DSL nằm ở source root khác plugin config.
- Module consumer dùng Stub Runner line không tương thích với Boot/Cloud của nó.
- CI chỉ chạy aggregator/root build mà không chạy producer generated tests.
- Stub được publish từ module sai artifactId/version.

**Đọc effective configuration tại module producer**. Không kết luận từ root POM hoặc một module khác.

| Kiểm tra | Mục đích |
| --- | --- |
| Parent/child effective POM | Tìm version kế thừa/override ở module |
| Build reactor/module selection | Xác minh module producer được test |
| Shared test helper Java target | Generated test có load được base class? |
| Contract source root | Plugin có discover DSL đúng chỗ? |
| Attached stub classifier | JAR được publish bởi module nào? |
| Stub Runner resolution | Consumer tải artifact nào thật? |

## 28. Local PASS nhưng CI FAIL: kiểm tra môi trường

Những nguyên nhân thường gặp:

- Local dùng JDK khác CI.
- Maven/Gradle global version khác wrapper.
- Build cache chứa generated source/plugin cũ.
- CI áp dụng profile/test exclusion khác.
- Repository mirror trả artifact/SNAPSHOT khác.
- Gradle daemon vẫn dùng cấu hình/caches cũ.
- Timezone/locale/charset khác ảnh hưởng fixture.
- Stub Runner `LOCAL` dùng JAR cũ ở Maven local repository.
- Test container network/port không giống laptop.
- CI chỉ chạy một subset tests vì module selection.

### Làm bằng chứng tái lập được

- Dùng wrapper trong repository.
- Khóa Java toolchain và versions.
- Dùng immutable release artifacts hoặc ghi checksum khi phải dùng SNAPSHOT.
- So sánh effective dependency/plugin versions.
- Ghi commit, contract revision, CI run ID và test reports.
- Không dùng trạng thái test PASS từ commit trước để xác nhận commit mới.

### SNAPSHOT không bất biến

`2.5.0-SNAPSHOT` có thể có nhiều build với bytes khác nhau. Consumer PASS hôm trước chưa chứng minh consumer PASS hôm nay, dù coordinate giống hệt. Ghi resolved artifact identity và SHA-256, rồi chạy lại hoặc chứng minh artifact thực không đổi.

## 29. Quy trình chẩn đoán theo giai đoạn

~~~mermaid
flowchart TD
    A["Build/test FAIL"] --> B{"Plugin resolve được?"}
    B -->|Không| P["ID, version, repositories, wrapper"]
    B -->|Có| C{"Contract parse/sinh tests?"}
    C -->|Không| D["DSL syntax, plugin API, Groovy runtime"]
    C -->|Có| E{"Generated code compile?"}
    E -->|Không| F["SCC plugin vs libs, JDK, JUnit, base class"]
    E -->|Có| G{"Tests có được thực thi?"}
    G -->|Không| H["Goals/tasks, test source set, engine"]
    G -->|Có| I{"Producer contract PASS?"}
    I -->|Không| J["Phân biệt tool mismatch với API mismatch"]
    I -->|Có| K{"Stub artifact đúng?"}
    K -->|Không| L["Mappings, packaging, contract revision"]
    K -->|Có| M{"Consumer Stub Runner + tests PASS?"}
    M -->|Không| N["Stub GAV, WireMock, DTO, behavior"]
    M -->|Có| O["Ghi evidence và đánh giá release"]
~~~

Một quy tắc tốt:

1. Ghi **exception đầu tiên** và stage xảy ra.
2. Lấy version thật: Boot, train, plugin, libraries, JDK/wrapper.
3. Đọc generated test/source/mapping khi liên quan.
4. Kiểm tra test reports thay vì chỉ build summary.
5. Tách lỗi dependency binary linkage khỏi lỗi contract semantics.
6. Chỉ sửa đúng tầng, rồi build sạch.
7. Chạy lại producer tests và consumer tests với artifact vừa verify.

Đừng chạy “upgrade all” khi thiếu bằng chứng; một lần nâng hàng loạt khiến việc khoanh vùng lỗi khó hơn.

## 30. Bảng tình huống và hướng kiểm tra nhanh

| Triệu chứng | Giả thuyết ưu tiên | Bằng chứng cần xem |
| --- | --- | --- |
| Maven không tìm Contract plugin | Plugin version/repository | Effective POM, plugin resolution logs |
| Gradle báo `Plugin not found` | Plugin id/version/pluginManagement | Gradle wrapper, repositories |
| `UnsupportedClassVersionError` | JVM chạy quá cũ | JDK/toolchain và class file version |
| Lỗi `javax.servlet`/`jakarta.servlet` | Sai framework/API generation | Boot/Framework/web dependencies |
| `NoSuchMethodError` | Binary dependency mismatch | Full stack trace, dependency tree |
| `MissingMethodException` Groovy | DSL/plugin incompatibility | Plugin release, syntax, classpath |
| Generated source import sai | Plugin và verifier libs lệch | Generated test + resolved dependencies |
| 0 generated tests | Plugin goals/tasks hoặc runner skip | Test reports, plugin logs |
| JUnit tests không discover | Test framework/engine mismatch | Generated imports, Surefire/Gradle Test |
| WebFlux test không setup | MockMvc/WebTestClient mode sai | Base test, generated source |
| Stub Runner unmatched 404 | Stub version/request matcher sai | Mappings, request journal, GAV |
| WireMock transformer không load | WireMock/extension API lệch | Dependency version và extension logs |
| Consumer parse body FAIL | JSON schema/serializer đổi | Actual response/DTO và contract |
| Local PASS, CI FAIL | JDK/wrapper/profile/cache khác | CI environment/effective graph |
| Cùng SNAPSHOT, bytes khác | Mutable artifact/repository | Resolved metadata và checksum |
| Producer PASS, consumer FAIL | API incompatibility hoặc stub runtime sai | Producer evidence + consumer tests |

Một exception có thể có nhiều nguyên nhân; bảng chỉ tạo **giả thuyết đầu tiên** chứ không thay stack trace.

## 31. Bài tập thực hành

### Bài tập A — BOM và Maven plugin

Producer import `spring-cloud-dependencies` nhưng không khóa version của `spring-cloud-contract-maven-plugin`.

**Yêu cầu:** giải thích vì sao BOM không tự quản lý plugin version, nêu cách tìm version thực.

**Gợi ý:** `dependencyManagement` khác `build.plugins/pluginManagement`. Đọc effective POM và plugin logs.

### Bài tập B — Boot minor mới, Cloud train cũ

Team nâng Boot minor nhưng không đổi Cloud train; project compile thành công.

**Yêu cầu:** đã đủ chứng minh hỗ trợ chưa?

**Gợi ý:** phải tra official Boot–Cloud compatibility matrix và chạy tests trên bộ thật.

### Bài tập C — Plugin Gradle không tìm thấy

Gradle báo không tìm thấy `org.springframework.cloud.contract` ở version được chỉ định.

**Yêu cầu:** kiểm tra những gì trước khi sửa DSL?

**Gợi ý:** plugin id/version, `settings.pluginManagement`, repositories/mirror, Gradle wrapper.

### Bài tập D — Generated Java compile fail

Chỉ nâng SCC Maven plugin, sau đó generated tests import API không có trong classpath.

**Yêu cầu:** liệt kê những versions cần ghi để chẩn đoán.

**Gợi ý:** plugin, SCC Verifier resolved, Boot, Cloud train, JDK và test engine.

### Bài tập E — Jakarta migration

Sau khi nâng Boot generation, generated test báo không tìm thấy Servlet API cũ.

**Yêu cầu:** đây có thể là lỗi gì và vì sao không nên thêm `javax.servlet` JAR tùy tiện?

**Gợi ý:** xác định Framework generation và Jakarta vs Javax APIs của web/test stack.

### Bài tập F — JUnit tests bằng 0

Generated tests dùng JUnit Jupiter nhưng runtime chỉ discover JUnit 4.

**Yêu cầu:** cần thay đổi gì trong test runner và release gate?

**Gợi ý:** chọn engine tương ứng; fail gate nếu required contracts có 0 tests.

### Bài tập G — WebFlux với MockMvc

Generated tests dùng RestAssuredWebTestClient nhưng base class chỉ setup RestAssuredMockMvc.

**Yêu cầu:** chẩn đoán sai ở lớp nào?

**Gợi ý:** test mode/base class wiring, không vội sửa response body.

### Bài tập H — WireMock extension lỗi

Stub Runner start nhưng một custom response transformer không load sau lần nâng WireMock.

**Yêu cầu:** những components nào phải đối chiếu?

**Gợi ý:** WireMock runtime, extension API và Stub Runner dependencies.

### Bài tập I — Producer/consumer Boot khác nhau

Producer Boot mới, consumer Boot cũ, JSON contract vẫn như trước.

**Yêu cầu:** có bắt buộc hai service dùng cùng Boot version không?

**Gợi ý:** runtime classpaths độc lập, nhưng consumer Stub Runner và API assertions phải PASS.

### Bài tập J — Artifact version và plugin version

SCC plugin có version `PLUGIN_X`, stub artifact là `order-service:2.5.0:stubs`.

**Yêu cầu:** hai version này nói về điều gì?

**Gợi ý:** plugin tool version khác application version; lưu cả contract revision và artifact checksum.

### Bài tập K — Multi-module

Parent POM import Cloud BOM mới nhưng module producer override Contract plugin cũ.

**Yêu cầu:** lệnh kiểm tra ở đâu và vì sao root POM chưa đủ?

**Gợi ý:** effective POM ở producer module, generated test source và reports.

### Bài tập L — SNAPSHOT không ổn định

Consumer PASS hôm trước với `2.5.0-SNAPSHOT:stubs`, hôm nay cùng coordinate nhưng checksum khác.

**Yêu cầu:** có thể tái sử dụng report cũ để release không?

**Gợi ý:** không nếu artifact identity khác; phải test lại hoặc có bằng chứng promotion đúng bytes.

### Bài tập M — Security override

Một thư viện WireMock được ép lên major mới vì advisory, nhưng Stub Runner bị lỗi linkage.

**Yêu cầu:** xử lý an toàn thế nào?

**Gợi ý:** tra release hỗ trợ, đánh giá upgrade line tương ứng, fix bảo mật có regression test, không bỏ qua advisory.

### Bài tập N — Lỗi nghiệp vụ hay tooling?

Generated producer test nhận HTTP 200 nhưng thiếu trường `status` trong JSON body; JDK/plugin/JUnit đều hoạt động đúng.

**Yêu cầu:** có nên nâng plugin ngay?

**Gợi ý:** kiểm tra producer serialization, contract semantics và consumer expectations trước.

## 32. Checklist đối chiếu phiên bản trước khi merge/release

### Chọn stack

- [ ] Đã đối chiếu Boot version và Cloud train từ **bảng hỗ trợ chính thức** cho dòng đang dùng.
- [ ] Contract libraries được quản lý có chủ đích qua Cloud BOM hoặc dependency management đã kiểm chứng.
- [ ] Maven/Gradle Contract plugin version được chọn **riêng**, không mặc định do BOM quản lý.
- [ ] Không dùng Boot version làm version cho Contract plugin.
- [ ] Release notes của Boot/Cloud/SCC đã được xem cho thay đổi major/minor.
- [ ] JDK và Maven/Gradle wrapper đáp ứng requirements của stack.
- [ ] Không có dependency overrides/conflicts chưa được review.

### Producer verification

- [ ] Contract DSL được phát hiện đúng source root/revision.
- [ ] Generated tests có được sinh và đọc lại source khi cần.
- [ ] JUnit/test engine khớp framework mà generator tạo ra.
- [ ] Base test class, lifecycle annotations và test mode đúng stack MVC/WebFlux/message.
- [ ] Producer tests thực sự chạy PASS, không phải 0 tests.
- [ ] Không nới matcher chỉ để lấp lỗi toolchain.
- [ ] Report ghi producer commit, contract revision và build ID.

### Stub và consumer

- [ ] Stub JAR chứa mappings/response files theo contract.
- [ ] GAV/classifier/version/checksum của artifact đúng.
- [ ] Stub Runner và WireMock runtime có thể đọc artifact format/extensions.
- [ ] Consumer Stub Runner test classpath phù hợp **với Boot/Cloud của consumer**, không mặc định theo producer.
- [ ] Consumer test tải đúng stub mới, không phải cache hoặc SNAPSHOT cũ.
- [ ] Consumer assertions kiểm tra business behavior, không chỉ stub server started.
- [ ] Các consumer versions còn hỗ trợ đã được kiểm tra trong ma trận thực tế.

### CI và quyết định

- [ ] CI dùng wrapper/toolchain có version được ghi rõ.
- [ ] Declared và resolved dependency/plugin versions được đối chiếu.
- [ ] Không tự dùng kết quả test lịch sử cho artifact khác checksum.
- [ ] Khi nâng plugin đã kiểm tra generation, producer verification và consumer Stub Runner.
- [ ] Có rollback/migration plan nếu cần.
- [ ] Chỉ công bố tương thích **trong phạm vi scenarios/versions đã test**.
- [ ] Những ô ma trận chưa test được ghi `NOT_RUN`/`BLOCKED`, không tự coi PASS.

## Kết luận

**Đối chiếu Spring Boot, Spring Cloud Contract và phiên bản plugin** là bài toán quản lý **một tập phiên bản**, không phải chỉnh một dependency đơn lẻ. Spring Cloud release train giúp quản lý Spring Cloud dependencies tương ứng với Spring Boot, nhưng **BOM không tự khóa build plugin version**. Cùng với đó, JDK, Maven/Gradle wrapper, Groovy, JUnit, test mode, WireMock và Stub Runner cũng phải tương thích trong môi trường build và consumer tests.

Một tổ hợp chỉ đủ điều kiện sử dụng khi resolved versions đã được xác nhận, **generated producer contract tests thật sự chạy**, stub artifact đúng nguồn được phát hành và consumer dùng đúng stub đó để kiểm tra hành vi. Chỉ có như vậy CI mới phân biệt được **lỗi công cụ** với **thay đổi API không tương thích**.

**Ghi nhớ:** *Chọn bộ phiên bản có tài liệu hỗ trợ; kiểm tra plugin riêng với BOM; đọc generated tests và resolved dependency graph; đừng gọi một release tương thích nếu producer hoặc consumer contract tests chưa chạy đúng artifact.*
