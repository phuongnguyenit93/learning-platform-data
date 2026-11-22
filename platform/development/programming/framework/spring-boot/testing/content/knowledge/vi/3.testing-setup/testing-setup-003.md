# Spring Boot dependency management và tương thích thư viện kiểm thử

## 1. Mục tiêu và vấn đề cốt lõi

Khi thêm JUnit, Mockito, AssertJ, Spring Test, Testcontainers hoặc thư viện giả lập HTTP vào dự án Spring Boot, câu hỏi không chỉ là “thêm dependency nào?”. Còn phải xác định **ai quản lý phiên bản**, thư viện nằm trên **classpath nào**, bộ thực thi test có tương thích hay không, và chúng có phù hợp với phiên bản Spring Boot/Spring Framework/Java/Gradle hoặc Maven đang dùng không.

Sau bài này, bạn cần làm được các việc:

1. Giải thích starter, dependency bắc cầu (*transitive dependency*), BOM (*Bill of Materials*), plugin build, version constraint và test scope khác nhau thế nào.
2. Thiết lập JUnit Jupiter + Mockito + AssertJ bằng `spring-boot-starter-test` mà không tự ghim trùng phiên bản các thư viện đã được Spring Boot quản lý.
3. Chọn dependency thêm cho MVC/WebFlux, JPA, Spring Security và Testcontainers; biết thư viện nào chỉ cần ở lúc chạy test.
4. Đọc dependency graph thực tế để truy ra phiên bản đã được giải quyết, nguồn quản lý phiên bản và xung đột.
5. Nhận biết những khác biệt cần kiểm tra khi chuyển từ Spring Boot 3.x sang 4.x, đặc biệt về module test, JUnit, mock bean và Testcontainers.
6. Phân biệt lỗi dependency/version thật với lỗi Spring context, cấu hình runner, datasource hoặc test logic.

**Nguyên tắc xuyên suốt:** chọn một đường quản lý dependency nhất quán cho module, để Spring Boot quản lý những thư viện nó đã xác nhận tương thích; chỉ ghi đè phiên bản khi có lý do kỹ thuật, phép thử hồi quy và bằng chứng từ cây dependency.

## 2. Sơ đồ những thành phần tham gia quản lý phiên bản

```text
Phiên bản Spring Boot mà dự án chọn
                 |
                 v
  spring-boot-dependencies (BOM)
  [phiên bản Spring Framework, JUnit,
   Mockito, AssertJ, Testcontainers...]
                 |
        +--------+----------------+
        |                         |
   Maven parent/BOM        Gradle plugin quản lý
                           dependency hoặc platform(BOM)
        |                         |
        +------------+------------+
                     |
        dependencies được khai báo
          (direct + transitive)
                     |
          build tool giải quyết
       version + scope + xung đột
                     |
         testCompileClasspath /
          testRuntimeClasspath
                     |
       JUnit Platform chạy test
```

Các khái niệm hay nhầm:

| Khái niệm | Có nhiệm vụ gì? | Không tự bảo đảm điều gì? |
| --- | --- | --- |
| `spring-boot-starter-test` | Kéo vào bộ thư viện test thông dụng như JUnit Jupiter, Mockito, AssertJ, Spring Boot Test | Không cấu hình toàn bộ database, Docker hay HTTP stub server cho dự án |
| `spring-boot-dependencies` BOM | Đề xuất/quản lý một tập phiên bản tương thích với release Boot đã chọn | Không tự thêm thư viện vào classpath khi chưa khai báo dependency |
| Spring Boot Gradle plugin | Hỗ trợ build, chạy/đóng gói và phối hợp quản lý dependency | Chỉ dùng plugin Boot không có nghĩa mọi cấu hình đều được quản lý; phải chọn dependency-management plugin hoặc nhập BOM theo Gradle |
| Maven `spring-boot-starter-parent` | Kế thừa BOM và các mặc định plugin/build hữu ích | Không phải lựa chọn duy nhất; dự án có parent riêng có thể import BOM |
| JUnit Jupiter | API test `@Test` và engine chạy test Jupiter | Không thay thế JUnit Platform launcher/build runner |
| `testImplementation` / Maven `test` | Đưa thư viện vào phạm vi test | Không đưa thư viện đó vào production artifact chỉ vì test dùng |
| Transitive dependency | Dependency mà một thư viện trực tiếp kéo theo | Không mặc nhiên có cùng phiên bản trên mọi nhánh của dependency graph |

**Version được khai báo không luôn bằng version được dùng.** Một starter có thể kéo vào thư viện A; module khác cũng kéo A phiên bản khác. Maven chọn theo luật dependency mediation/management; Gradle giải quyết theo constraints, conflict resolution và configuration. Kết luận đúng phải đọc **resolved test runtime classpath**, thay vì chỉ đọc tệp build.

## 3. Những gì `spring-boot-starter-test` cung cấp

Ở Spring Boot 3.x, starter test thông dụng đưa vào hai module Spring Boot test chính cùng các thư viện hỗ trợ kiểm thử:

- **JUnit Jupiter / JUnit Platform:** định nghĩa `@Test`, `@BeforeEach`, `@ParameterizedTest` và chạy test.
- **Spring Test + Spring Boot Test:** tạo/inject test context, `@SpringBootTest`, các slice test, `MockMvc` khi có phần web tương ứng.
- **Mockito:** tạo mock/stub, khai báo `when(...).thenReturn(...)`, xác minh cộng tác viên.
- **AssertJ:** assertion dễ đọc như `assertThat(total).isEqualTo(100)`.
- **Hamcrest, JsonPath, JSONassert:** kiểm tra object, nội dung JSON và các biểu thức đường dẫn JSON.
- Các tiện ích test bổ trợ có thể thay đổi theo dòng Spring Boot.

Ở Spring Boot 4.x, `spring-boot-starter-test` vẫn cung cấp nền tảng test chung; các khả năng test gắn với công nghệ cụ thể được tổ chức thành module/starter tập trung hơn, ví dụ `spring-boot-starter-webmvc-test`, `spring-boot-starter-data-jpa-test`. Đừng giả định danh sách transitive dependency giữ nguyên qua một lần nâng major version.

**Không cần** thêm đồng thời, bằng phiên bản viết tay:

```groovy
// Cách dễ tạo xung đột khi starter đã cung cấp các module này:
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.junit.jupiter:junit-jupiter:5.9.0'
testImplementation 'org.mockito:mockito-core:4.8.0'
testImplementation 'org.assertj:assertj-core:3.23.1'
```

Các số phiên bản trên chỉ minh họa anti-pattern xung đột, **không phải bộ phiên bản được khuyến nghị**. Cách bắt đầu đúng, khi dự án đã nhập Spring Boot BOM, là:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Nếu thực sự cần API test nằm ngoài starter, hãy khai báo thêm đúng module, để BOM chọn version nếu BOM quản lý module đó. Nếu BOM không quản lý, phải chọn và kiểm tra phiên bản tương thích riêng.

## 4. Ví dụ hoàn chỉnh có thể chạy: Gradle Groovy DSL, Spring Boot 3.3.0

**Ví dụ được cố định ở Spring Boot 3.3.0 để các đoạn mã cùng một mốc phiên bản.** Đây là mốc minh họa cách cấu hình, không phải khuyến nghị giữ production ở bản cũ. Dự án thực tế nên dùng release đã được tổ chức chọn, bản bảo trì an toàn và wrapper tương ứng. Ví dụ này chạy với Java 17+, Gradle 8.5 và các dependency tải được từ Maven Central.

Cấu trúc:

```text
testing-dependencies/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/TestingDependenciesApplication.java
    └── test/java/example/
        ├── DependencySmokeTest.java
        └── ApplicationContextTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'testing-dependencies'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/example/TestingDependenciesApplication.java`:**

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingDependenciesApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingDependenciesApplication.class, args);
    }
}
```

**`src/test/java/example/DependencySmokeTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class DependencySmokeTest {
    interface RateProvider {
        int rate();
    }

    @Test
    void junitMockitoAndAssertJWorkTogether() {
        RateProvider provider = mock(RateProvider.class);
        when(provider.rate()).thenReturn(25);

        int result = provider.rate() * 4;

        assertThat(result).isEqualTo(100);
    }
}
```

**`src/test/java/example/ApplicationContextTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationContextTest {
    @Test
    void contextLoads() {
        // Pass nếu ApplicationContext khởi tạo được.
    }
}
```

Chạy bằng wrapper của dự án (sau khi wrapper Gradle 8.5 đã tồn tại):

```bash
./gradlew test
./gradlew test --tests example.DependencySmokeTest
./gradlew test --tests example.ApplicationContextTest
```

Trên PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.DependencySmokeTest
```

Khi cả hai bài chạy thành công, Gradle kết thúc ở trạng thái `BUILD SUCCESSFUL`; báo cáo số task và thời lượng thay đổi theo môi trường. Đây không phải ví dụ in dữ liệu ra stdout. Test thứ nhất chứng minh **JUnit + Mockito + AssertJ** khả dụng; test thứ hai chứng minh **Spring Boot Test** tạo context được. Chúng chưa chứng minh MVC, JPA hay cơ sở dữ liệu, vì dự án này chưa khai báo các phần đó.

**Vì sao cấu hình trên đúng?** `io.spring.dependency-management` phối hợp Spring Boot Gradle plugin để import BOM tương ứng với Spring Boot 3.3.0. Các dependency được BOM quản lý không phải ghi phiên bản riêng. `useJUnitPlatform()` chọn runner JUnit Platform. `junit-platform-launcher` ở runtime giúp build/test runner có launcher phù hợp với bộ JUnit mà BOM quản lý.

Không thể chạy hai tệp test chỉ bằng `javac`/`java` thuần khi chưa tự cung cấp JUnit/Mockito/AssertJ/Spring test classpath; dùng build tool để tải và liên kết dependencies đúng.

## 5. Hai cách quản lý BOM trong Gradle

### Cách A: plugin `io.spring.dependency-management`

Đây là cách được dùng ở ví dụ đầy đủ trên:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}
```

Khi cả Spring Boot plugin và dependency-management plugin cùng áp dụng, Spring Boot BOM được import phù hợp phiên bản Boot plugin. Có thể dùng các property được BOM hỗ trợ để điều chỉnh managed version, nhưng thay đổi đó cần được kiểm chứng kỹ.

### Cách B: Gradle native BOM bằng `platform(...)`

Thay phần plugin và dependencies quản lý tương ứng trong **một bản build khác**, không cộng hai cách vào cùng một ví dụ:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Trong một dự án Java Gradle tiêu chuẩn, test configuration kế thừa những gì cần từ main configuration, nên BOM khai báo trên `implementation` có thể ảnh hưởng đến `testImplementation`. Với **custom test suite/source set** tự tạo, hãy kiểm tra extends-from và đưa BOM vào configuration tương ứng nếu cần; đừng giả định `integrationTestImplementation` mặc nhiên có BOM.

| Đặc điểm | Dependency-management plugin | Native `platform(BOM)` |
| --- | --- | --- |
| Cách đưa phiên bản vào build | Plugin import BOM | Khai báo BOM như một dependency trong cấu hình |
| Điều chỉnh managed versions | Có thể qua các BOM properties | Theo version constraints/resolution của Gradle |
| Phạm vi tác động | Theo cơ chế plugin và configuration | Chỉ configuration khai báo BOM và những cấu hình kế thừa phù hợp |
| Hành vi khi bị transitive yêu cầu version khác | Theo dependency-management plugin và giải quyết của Gradle | `platform` là khuyến nghị/constraint; Gradle có thể chọn version khác theo graph |
| Khi nào chọn | Dự án đã chuẩn hóa plugin này | Dự án dùng quản lý dependency theo cách native Gradle |

`enforcedPlatform` ép mạnh hơn `platform`, có thể làm ảnh hưởng các thư viện tiêu thụ hoặc ràng buộc từ phụ thuộc khác; chỉ dùng sau khi hiểu lý do, không dùng máy móc để “chữa” mọi xung đột.

**Điểm kiểm tra quan trọng trong multi-project:** mỗi module có test riêng phải có dependency/BOM hiệu lực trên classpath của chính module ấy. Một BOM đặt trong root project không tự động bảo đảm mọi subproject dùng nó nếu build không truyền cấu hình.

## 6. Maven: `spring-boot-starter-parent` hoặc import BOM

### Cách A: Maven parent, phù hợp ví dụ độc lập

**`pom.xml`** cho cùng ứng dụng Java 17, Spring Boot 3.3.0:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>testing-dependencies</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Đặt ba tệp Java ở `src/main/java` và `src/test/java` như mục 4, sau đó chạy:

```bash
mvn test
mvn -Dtest=DependencySmokeTest test
```

Khi dùng Maven Wrapper của dự án, gọi `./mvnw test`; trên Windows dùng `.\mvnw.cmd test`. Maven parent cung cấp dependency management và plugin defaults giúp Surefire chạy JUnit Platform phù hợp. Không cần khai báo lại phiên bản JUnit/Mockito/AssertJ khi chúng đã được quản lý.

### Cách B: dự án có Maven parent riêng

Maven chỉ có **một `<parent>` trực tiếp**. Nếu tổ chức đã có parent, import Spring Boot BOM trong `dependencyManagement` của POM phù hợp:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **đoạn POM bổ sung**, không phải một tệp XML độc lập. Sau đó vẫn khai báo `spring-boot-starter-test` với `<scope>test</scope>` trong `<dependencies>`. Khác với kế thừa starter parent, import BOM **không** đem theo toàn bộ `pluginManagement` và các mặc định build từ parent; tổ chức phải cấu hình compiler, Maven Surefire/Failsafe và plugin versions tương ứng.

| Gradle | Maven | Ý nghĩa |
| --- | --- | --- |
| `implementation` | `compile` (mặc định) | Sử dụng trong mã ứng dụng |
| `runtimeOnly` | `runtime` | Chỉ cần lúc chạy ứng dụng |
| `testImplementation` | `test` | Biên dịch/chạy test, không dành cho main source |
| `testRuntimeOnly` | Thường là dependency `test` phù hợp | Chỉ cần lúc thực thi test; Gradle tách bạch rõ hơn |
| `testFixturesImplementation` | Không có đối ứng mặc định trực tiếp | Thư viện hỗ trợ test khi có Gradle test fixtures plugin |

**Maven dependencyManagement và Gradle BOM quản lý version, không phải cơ chế tự động tải mọi dependency trong BOM.** Khai báo starter, module hay driver mình thật sự dùng vẫn là trách nhiệm của module.

## 7. Classpath và scope: đặt thư viện vào đúng nơi

Một lỗi phổ biến là đưa tất cả thư viện thử nghiệm vào `implementation`, vô tình kéo công cụ kiểm thử vào ứng dụng triển khai. Hãy phân biệt:

```text
src/main/java   -> compileClasspath / runtimeClasspath
                  implementation + runtimeOnly

src/test/java   -> testCompileClasspath / testRuntimeClasspath
                  code main + testImplementation + testRuntimeOnly
```

Sơ đồ là mô hình đơn giản cho Java Gradle tiêu chuẩn, không mô tả mọi custom configuration.

Ví dụ:

```groovy
dependencies {
    // Ứng dụng thật:
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'

    // Chỉ dành cho kiểm thử:
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Ở đây PostgreSQL driver hỗ trợ ứng dụng khi chạy; H2 là database nhúng chỉ dùng trong test nếu test được cấu hình sử dụng nó. Nếu kiểm tra tính tương thích SQL với PostgreSQL production, H2 có thể **không đủ**, nên dùng database PostgreSQL test/Testcontainers. Có H2 trên test classpath không tự chứng minh Spring đã kết nối đúng datasource mong muốn.

Những nguyên tắc chọn scope:

- `testImplementation` cho API mà mã ở `src/test/java` import: JUnit, Mockito, Spring Security Test, Testcontainers annotations, test helpers.
- `testRuntimeOnly` cho thành phần chỉ được nạp khi chạy test: JUnit Platform launcher, driver DB chỉ dành cho test, engine không được import ở compile time.
- `runtimeOnly` cho driver/libraries chỉ cần lúc ứng dụng chạy; test runtime của Java project thông thường cũng thấy main runtime deps.
- `implementation` cho thư viện mà mã production cần compile. Không chuyển Mockito thành `implementation` chỉ để test compile được.
- Nếu một test suite riêng chạy bằng Gradle JVM Test Suites hoặc source set `integrationTest`, phải cấu hình classpath, runner, test dependencies cho **suite đó**, không mặc định mọi thứ trong `testImplementation` tự xuất hiện.

Ngoài scope, phải lưu ý **exclude transitive**. Loại một module có vẻ dư như `mockito-core` hoặc `junit-jupiter-engine` có thể làm `@Test`/mock runtime bị lỗi. Chỉ exclude sau khi biết artifact nào kéo vào và xác minh tree trước/sau.

## 8. Chọn dependency theo loại test

### 8.1. Unit test JUnit/Mockito không khởi tạo Spring

Thông thường `spring-boot-starter-test` đủ để chạy test Java thuần, Mockito và AssertJ trên JUnit Platform. Không cần `@SpringBootTest` hoặc dependency web nếu đối tượng được tạo bằng `new`.

### 8.2. Spring MVC với `@WebMvcTest`, `MockMvc`

- Spring Boot 3.x: ứng dụng Servlet MVC có `spring-boot-starter-web` và `spring-boot-starter-test`, sử dụng `@WebMvcTest`/`MockMvc` từ bộ test tương ứng.
- Spring Boot 4.x: kiểm tra starter được chia theo tính năng; dùng `spring-boot-starter-webmvc` cho ứng dụng và thêm `spring-boot-starter-webmvc-test` cho phần test MVC khi cần.
- Nếu dùng Spring Security filters, cần cấu hình identity/CSRF trong test; các assertion 401/403 là hành vi security, không nhất thiết là xung đột dependency.

Ví dụ **đoạn dependencies Spring Boot 4.x**, áp dụng vào một build đã có BOM 4.x hợp lệ:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
}
```

Không thêm đoạn Boot 4.x vào dự án Boot 3.3 chỉ vì ví dụ mới hơn: module/artifact của hai dòng phát hành khác nhau.

### 8.3. Persistence với `@DataJpaTest`

- Spring Boot 3.x: thường có `spring-boot-starter-data-jpa` và `spring-boot-starter-test`; thêm H2 test runtime nếu thật sự dùng H2.
- Spring Boot 4.x: thêm starter `spring-boot-starter-data-jpa-test` dành cho slice JPA.
- JPA cần driver/schema/transaction phù hợp. Thất bại ở `DataSource` có thể do thiếu driver hoặc URL, không đồng nghĩa JUnit không tương thích.

### 8.4. Spring Security

Nếu test dùng `@WithMockUser`, request postprocessors hoặc matcher của Spring Security Test:

```groovy
dependencies {
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Khi BOM đang quản lý Spring Security, không tự ghim một bản `spring-security-test` khác major với các Spring Security runtime modules. Các annotation chỉ test security không thay thế cấu hình FilterChain thực sự của ứng dụng.

### 8.5. Reactive WebFlux

- Ở dòng 3.x: phụ thuộc ứng dụng `spring-boot-starter-webflux`, starter test chung và những thư viện Reactor test cần thiết.
- Ở dòng 4.x: có `spring-boot-starter-webflux-test` cho test WebFlux.
- Với `StepVerifier`, kiểm tra dependency `io.projectreactor:reactor-test` có trên test classpath.
- Đừng dùng `@WebMvcTest` cho handler WebFlux và đừng trộn Spring MVC/WebFlux chỉ để “mượn” test annotation; hai stack có kiểu ứng dụng và auto-configuration khác nhau.

### 8.6. Testcontainers và database thật

Spring Boot có tích hợp hỗ trợ kết nối container qua `spring-boot-testcontainers` và `@ServiceConnection` ở những phiên bản phù hợp. Testcontainers còn cần module cho container cụ thể, integration JUnit khi dùng `@Testcontainers`/`@Container`, và container runtime hoạt động.

**Spring Boot 3.x + Testcontainers 1.x** (đoạn phụ thuộc Gradle, BOM phù hợp 3.x đã được áp dụng):

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
```

**Spring Boot 4.x + Testcontainers 2.x** đổi tên artifact modules:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:testcontainers-junit-jupiter'
    testImplementation 'org.testcontainers:testcontainers-postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
```

Hai đoạn là **phương án cho hai dòng riêng**, không dùng đồng thời. Testcontainers 2.x cũng có những thay đổi package API; cập nhật imports và API theo tài liệu migration thay vì chỉ thay artifactId. Nếu cần Docker trong CI, xác minh runtime trước; lỗi không kết nối được Docker không phải lỗi BOM.

### 8.7. Thư viện test không được BOM quản lý

Ví dụ một mock HTTP server hoặc thư viện tạo dữ liệu bên thứ ba không nằm trong managed dependency list. Khi ấy:

1. Kiểm tra nó có hỗ trợ Java, Jakarta/Spring Framework, JUnit và HTTP client version đang sử dụng không.
2. Chọn phiên bản tương thích từ tài liệu phát hành của thư viện.
3. Đặt dependency vào `testImplementation`/Maven `test` nếu chỉ test dùng.
4. Dùng `dependencyInsight`/`dependency:tree` để xác minh các thư viện bắc cầu (Jackson, Netty, SLF4J, Byte Buddy...) không tạo mâu thuẫn.
5. Giữ một kiểm thử chạy thật để phát hiện xung đột liên kết API ở runtime.

## 9. Ma trận tương thích: xác minh theo **dòng phát hành**

Không lấy một snippet từ Spring Boot 4.x đưa nguyên vào 3.3.x hoặc ngược lại. Những khác biệt thiết yếu:

| Thành phần | Spring Boot 3.3.x | Spring Boot 3.4–3.5.x | Spring Boot 4.x |
| --- | --- | --- | --- |
| Spring Framework | 6.1.x ở 3.3 | 6.2.x | 7.x |
| Java tối thiểu | 17 | 17 | 17 |
| JUnit dòng chính | Jupiter/JUnit 5 | Jupiter/JUnit 5 | Jupiter/JUnit 6 |
| Boot starter test cơ bản | `spring-boot-starter-test` | `spring-boot-starter-test` | `spring-boot-starter-test` + test starter/module theo chức năng |
| Mock Spring bean | `@MockBean` của Boot | `@MockBean` deprecated, chuyển dần `@MockitoBean` của Framework | Boot `@MockBean` bị loại bỏ; dùng `@MockitoBean` |
| MVC test annotation | Gói Boot 3.x | Gói Boot 3.x | Module/package MVC test chuyên biệt |
| JPA test annotation | Gói Boot 3.x | Gói Boot 3.x | Module/package JPA test chuyên biệt |
| Testcontainers thường được Boot BOM quản lý | 1.x | Kiểm tra version được quản lý của minor thực tế | 2.x, nhiều artifact đổi tên |
| Gradle plugin compatibility | Kiểm tra Gradle wrapper của 3.3 | Kiểm tra của minor cụ thể | Gradle 8.x từ 8.14 trở lên hoặc 9.x (theo yêu cầu Boot 4.0) |

Cần kiểm tra thêm **JDK thực sự đang chạy Gradle/Maven**, JDK toolchain biên dịch, plugin build, thư viện thứ ba và bản patch. Ma trận trên nêu khác biệt lớn; nó không thay cho yêu cầu phiên bản của bản phát hành chính xác.

Các import annotation khác nhau qua major version; ví dụ:

```java
// Boot 3.x:
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

// Boot 4.x:
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
```

Đây là **các dòng import đối chiếu**, không đặt cùng bốn import trùng tên vào một tệp Java. Với bean mock:

```java
// Spring Boot 3.3:
import org.springframework.boot.test.mock.mockito.MockBean;

// Spring Boot 3.4+ với Spring Framework 6.2+, và Boot 4.x:
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

`@MockitoBean` không đồng nghĩa với `@Mock` của Mockito: cái đầu tham gia thay thế bean trong Spring context, cái sau chỉ tạo mock ở mức Mockito. Khi nâng cấp, cần kiểm tra điều kiện thay thế bean, qualifier và context hierarchy chứ không chỉ đổi tên annotation.

**Không dùng các con số “JUnit 5/6” làm version chính xác để chèn vào Gradle**. Đó là dòng major; lấy minor/patch của JUnit Platform, Jupiter và launcher từ dependency tree/BOM tương ứng.

## 10. JUnit Platform, Jupiter, engine và discovery

JUnit Jupiter cung cấp annotation/API để viết test; **JUnit Platform** cung cấp cơ chế khám phá/chạy test; build tool (Gradle Test task hoặc Maven Surefire) tích hợp với platform; **test engine** thực thi test thuộc mô hình cụ thể.

```text
@Test từ org.junit.jupiter.api
            |
       JUnit Jupiter
            |
    Jupiter TestEngine
            |
      JUnit Platform
            |
    Gradle Test / Maven Surefire / IDE
```

Trong Gradle, nhớ:

```groovy
tasks.named('test') {
    useJUnitPlatform()
}
```

Tùy phiên bản Gradle, JUnit và starter, cấu hình runtime launcher nên có:

```groovy
testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
```

Khi test “không được chạy”, trước tiên kiểm tra **import `org.junit.jupiter.api.Test`**, task thực tế, test engine trên `testRuntimeClasspath` và filter `--tests`. Đừng vội nâng cả Spring Boot khi nguyên nhân chỉ là build tool dùng sai platform.

**JUnit 4 legacy:** `org.junit.Test` khác `org.junit.jupiter.api.Test`. Dự án còn test JUnit 4 có thể thêm JUnit Vintage Engine thích hợp phiên bản JUnit Platform để chạy chúng trong quá trình chuyển đổi. Khai báo JUnit 4 API cho code cũ và Vintage Engine theo BOM/phiên bản phù hợp; không coi Vintage Engine là mặc định của starter mới. Tốt nhất chuyển test sang Jupiter có kiểm soát, tránh giữ hai engine mãi nếu không cần.

Nếu dùng JUnit Platform launcher/engine riêng, phải giữ các module thuộc cùng thế hệ mà BOM quản lý. Một override Jupiter API nhưng không đồng bộ engine/launcher dễ gây `NoSuchMethodError`, `ClassNotFoundException` hoặc lỗi discovery ở runtime.

## 11. Chẩn đoán dependency bằng lệnh thay vì đoán

### Với Gradle

```bash
./gradlew --version
./gradlew dependencies --configuration testCompileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency mockito-core --configuration testRuntimeClasspath
./gradlew test --info
```

Trong multi-project, gọi đúng module nếu cần, ví dụ:

```bash
./gradlew :service:dependencies --configuration testRuntimeClasspath
./gradlew :service:dependencyInsight --dependency mockito-core --configuration testRuntimeClasspath
./gradlew :service:test --tests example.DependencySmokeTest
```

`:service` là **tên module minh họa**, chỉ áp dụng nếu thực sự tồn tại trong dự án. Với Windows đổi `./gradlew` sang `.\gradlew.bat`.

Cách đọc kết quả:

- `testCompileClasspath`: nhìn những API mà tệp test biên dịch dựa vào.
- `testRuntimeClasspath`: nhìn engine, launcher, driver, auto-configuration và phiên bản được dùng khi chạy.
- `dependencyInsight`: tra **vì sao** một phiên bản được chọn, yêu cầu nào tham gia conflict resolution, dependency đi từ nhánh nào.
- `--info`: đọc test runner thực tế, test được discovery, lỗi khởi tạo context và stack trace; không nhất thiết mỗi lần đều dùng log verbose.

### Với Maven

```bash
mvn -version
mvn help:effective-pom
mvn dependency:tree -Dscope=test
mvn dependency:tree -Dscope=test -Dincludes=org.junit.jupiter
mvn test
```

`help:effective-pom` cho biết phiên bản/plugin/dependency management sau khi kế thừa parent và profile. `dependency:tree` cho biết dependency thực và nhánh kéo vào. Nếu dùng Failsafe cho integration tests, kiểm tra thêm cấu hình plugin, naming convention (`*IT`, `*ITCase` tùy cấu hình) và goal `integration-test`/`verify`.

**Đọc kết quả như nhà điều tra:**

1. Xác định lỗi ở **compile**, **test discovery**, **context initialization** hay **runtime invocation**.
2. Ghi module đang lỗi và Java/build tool thực tế.
3. Xem resolved version của artifact xuất hiện trong stack trace cùng các module liên quan.
4. Tìm xem version do BOM, override trực tiếp, transitive dependency hoặc plugin/profile mang vào.
5. Thay đổi **một nguyên nhân có căn cứ**, chạy lại test tái hiện, kiểm tra lại graph.

Cây dependency có thể đổi sau thêm starter, nâng patch version, đổi profile hoặc thay plugin; vì vậy so sánh cả trước và sau khi fix.

## 12. Các lỗi tương thích thường gặp

| Triệu chứng | Giả thuyết cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `package org.junit.jupiter.api does not exist` | Thiếu test starter hoặc khai báo sai scope/source set | Xem `testCompileClasspath` và đúng module |
| `No tests found` / 0 tests executed | `useJUnitPlatform()` thiếu, import JUnit 4, filter sai, thiếu test engine | Kiểm tra runner/engine và test discovery |
| `NoClassDefFoundError` / `ClassNotFoundException` khi chạy | Thiếu runtime artifact, sai scope hoặc version không khớp | Xem `testRuntimeClasspath` và stack trace |
| `NoSuchMethodError` từ JUnit Platform, Mockito, Jackson... | Có thể là binary API version mismatch, IDE launcher cũ, override không đồng bộ | Dò `dependencyInsight`, bỏ override không cần, thử bằng wrapper |
| `@MockBean` không tồn tại sau lên Boot 4 | API của Boot bị loại bỏ | Chuyển `@MockitoBean` và kiểm tra cách override bean |
| `@WebMvcTest` / `@DataJpaTest` import lỗi khi lên Boot 4 | Package/module test chuyển | Thêm test starter theo chức năng và đổi import |
| Testcontainers `postgresql` không resolve sau nâng 2.x | ArtifactId cũ 1.x | Đổi sang `testcontainers-postgresql`; tương tự JUnit integration |
| `Could not find ...` khi resolve dependency | Sai tọa độ, thiếu repository hoặc hỏng truy cập repository | Kiểm tra artifact, version, `repositories`/mirror/auth |
| `Unable to find a @SpringBootConfiguration` | Vị trí package test/configuration, hoặc slice không tìm app chính | Kiểm tra package và cách chỉ định config |
| `No qualifying bean` ở `@WebMvcTest` | Slice cố tình không nạp service thật | Cung cấp mock/test config phù hợp |
| `Failed to configure DataSource` | Thiếu DB URL, driver, credentials, container hoặc profile test | Kiểm tra datasource và dependency runtime |
| `401 Unauthorized` / `403 Forbidden` ở MVC test | Security filter/CSRF và identity test | Dùng Spring Security Test đúng chính sách |
| Mockito agent/Byte Buddy warning trên JDK mới | Hành vi instrument/mock maker và hạn chế JVM | Kiểm tra Mockito/Byte Buddy do BOM quản lý, cấu hình agent theo tài liệu chính thức |
| Gradle chạy một JDK, source toolchain dùng JDK khác | JAVA_HOME/Gradle daemon khác Java toolchain | So sánh `gradlew --version`, toolchain và runtime |

Không nên xử lý mọi vấn đề bằng cách xóa cache, cưỡng ép version cao nhất hay exclude hàng loạt. Các thao tác đó có thể che lỗi tạm thời mà không giải quyết nguyên nhân trong graph.

### Ba ca điều tra mẫu

**Ca A — Test không phát hiện:** `@Test` import từ `org.junit.Test`, trong khi dự án bật JUnit Platform và không có Vintage Engine. Thêm test Jupiter bằng `org.junit.jupiter.api.Test` hoặc cấu hình Vintage có chủ đích. Khi đổi import, kiểm tra khác biệt API như `@Before` → `@BeforeEach`.

**Ca B — Mockito compile được nhưng lỗi runtime:** một thư viện test khác kéo phiên bản Mockito/Byte Buddy khác bộ BOM. Chạy `dependencyInsight --dependency mockito-core` và kiểm tra Byte Buddy trên test runtime; đối chiếu release notes của JDK/Mockito. Tránh thêm thủ công các phiên bản Mockito rời rạc khi chưa xác nhận chúng cùng thế hệ.

**Ca C — Upgrade Boot 4 làm test web fail compile:** mã vẫn import `org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest`, chỉ có starter test chung. Đọc migration guide, thêm `spring-boot-starter-webmvc-test` và đổi import sang package MVC test mới. Sau khi compile, kiểm tra lại MockMvc/bean overrides và behavior test.

## 13. Quy trình nâng cấp thư viện kiểm thử an toàn

Khi dự án cần nâng Spring Boot hoặc một thư viện test, ưu tiên **nâng theo một dòng tương thích**, có thể lặp lại:

1. **Chốt hiện trạng:** phiên bản Boot plugin/parent/BOM, Java, Gradle wrapper/Maven, libraries explicit version, test tasks, CI image.
2. **Liệt kê test dependencies:** starter test, Spring Security Test, WebMvc/JPA/WebFlux test, DB driver, Testcontainers và những thư viện test của bên thứ ba.
3. **Đọc hướng dẫn nâng cấp:** yêu cầu Java/Gradle; thay đổi package/annotation; module artifact rename; deprecated API bị loại bỏ; JUnit Platform và Testcontainers major.
4. **Nâng Boot/BOM nhất quán trước:** bỏ phiên bản viết tay không còn cần; chỉ giữ override có lý do. Nếu có Spring Cloud hoặc BOM thứ hai, kiểm tra release train tương thích và thứ tự quản lý.
5. **Resolve graph và compile test:** tìm lỗi class/package trước; xác minh test engine/launcher và runtime dependency.
6. **Chạy theo mức độ:** unit test thuần → slice (MVC/JPA) → `@SpringBootTest` → database/container → CI integration; ghi rõ test nào fail và lý do.
7. **Đối chiếu trước/sau:** artifact đã resolved, số test thực chạy, failure/log và thời gian chạy. Một build xanh nhưng số test giảm đột ngột có thể là lỗi discovery.
8. **Cập nhật tài liệu cấu hình:** thống nhất starter, BOM, wrapper, JDK và import mới; không để ví dụ build cũ khiến người khác sao chép sai.

Trong quá trình migration, nếu cần thử version override, thêm test tái hiện lỗi, lý do bằng văn bản và phương án bỏ override khi BOM phát hành bản sửa. Đừng ghim JUnit/Mockito/Testcontainers riêng chỉ vì “mới hơn” khi chưa biết mức tương thích với Spring Boot.

## 14. Bài tập tự thực hành và tiêu chí hoàn thành

**Bài tập 1 — Đọc một dependency graph thực**

Dùng ví dụ Gradle mục 4. Chạy `dependencies` và `dependencyInsight`, trả lời:

- Thư viện nào đưa `org.junit.jupiter.api.Test` vào test compile classpath?
- Phiên bản `mockito-core` được chọn là bao nhiêu và thuộc đường dependency nào?
- Vì sao `junit-platform-launcher` ở `testRuntimeOnly`?
- Nếu xóa `useJUnitPlatform()`, có chắc runner vẫn discovery đúng Jupiter test không? Hãy kiểm tra thay vì đoán.

**Bài tập 2 — Thêm một loại test**

Với một ứng dụng Spring MVC Boot 3.x đã có `spring-boot-starter-web`, thêm một `@WebMvcTest`. Dùng dependency graph chứng minh `MockMvc` có trên test classpath. Sau đó thử với dự án Boot 4.x riêng và dùng test starter MVC đúng dòng. Giải thích vì sao đổi BOM/starter/import là một nhóm thay đổi phải kiểm thử cùng nhau.

**Bài tập 3 — Tạo xung đột trong môi trường học**

Trong nhánh thí nghiệm, thêm explicit version của một test library thấp hơn BOM, chạy `dependencyInsight` để xem version thực tế có bị thay không. Sau đó gỡ override và so sánh tree cùng kết quả test. **Không chuyển thử nghiệm ép version này vào branch production.**

**Bài tập 4 — Testcontainers**

Tạo integration test dùng PostgreSQL container với đúng nhóm artifact Testcontainers theo dòng Boot. Chỉ ra dependency nào cung cấp PostgreSQL container, dependency nào cung cấp JUnit integration và module nào tích hợp `@ServiceConnection`. Kiểm tra nguyên nhân nếu CI thiếu container runtime. Không dùng dữ liệu DB thật của production cho bài tập.

### Checklist trước khi đánh dấu thiết lập kiểm thử đã đúng

- [ ] Phiên bản Spring Boot, Spring Framework, Java, Gradle/Maven phù hợp theo tài liệu của **release thực tế**.
- [ ] Có đúng một chiến lược rõ ràng để quản lý Spring Boot BOM trong module; các BOM khác được chọn có chủ đích.
- [ ] Thư viện được BOM quản lý không bị ghim thủ công thiếu lý do; version ngoài BOM đã xác minh.
- [ ] JUnit API, engine, launcher và runner cùng thế hệ; build thực sự khám phá/chạy số test mong muốn.
- [ ] Mockito, AssertJ, Spring Security Test và test module theo slice xuất hiện trên đúng test classpath.
- [ ] Testcontainers/DB driver đúng artifactId và runtime, không trộn API của 1.x và 2.x.
- [ ] Không kéo test libraries vào production artifact do scope đặt sai.
- [ ] Đã kiểm tra resolved dependency graph, không chỉ nhìn declarations.
- [ ] Đã chạy test nhỏ và ít nhất một test context/slice phù hợp với phạm vi công nghệ sử dụng.
- [ ] Khi upgrade, imports, starter/module và CI runner đã được đối chiếu với migration guide.

## 15. Các quy tắc dễ nhớ

- **BOM quyết định khung version; starter chọn bộ thư viện; scope quyết định nơi thư viện được dùng; build tool quyết định resolved graph; JUnit runner quyết định test có thực sự được chạy.**
- Dùng `spring-boot-starter-test` làm nền nhưng không cho rằng starter này thay thế mọi dependency test theo công nghệ.
- Phân biệt **lỗi dependency** (không resolve/class/method) với **lỗi test context** (bean, profile, datasource) và **lỗi nghiệp vụ** (assertion không đúng).
- Với Spring Boot 4, kiểm tra lại package test, starter test chia nhỏ, `@MockitoBean`, JUnit 6, Testcontainers 2 và wrapper Gradle phù hợp.
- Mỗi lần thêm thư viện hoặc override version, hãy tìm bằng chứng trên `testRuntimeClasspath` và giữ một test tái hiện hành vi cần bảo vệ.

## Nguồn chính thức để tra cứu theo phiên bản

- Spring Boot — Build Systems / Dependency Management: https://docs.spring.io/spring-boot/reference/using/build-systems.html
- Spring Boot 3.3 — Gradle dependency management: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Spring Boot 3.3 — Testing: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
- Spring Boot 4.0 — Test support: https://docs.spring.io/spring-boot/4.0/reference/testing/
- Spring Boot 4.0 — Build Systems và test starters: https://docs.spring.io/spring-boot/4.0/reference/using/build-systems.html
- Spring Boot 4.0 — System Requirements: https://docs.spring.io/spring-boot/4.0/system-requirements.html
- Spring Boot 4.0 Migration Guide: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
- JUnit User Guide: https://docs.junit.org/current/user-guide/
- Mockito: https://site.mockito.org/
- Testcontainers Java: https://java.testcontainers.org/
- Gradle — Dependency Management: https://docs.gradle.org/current/userguide/dependency_management.html
- Maven — Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
