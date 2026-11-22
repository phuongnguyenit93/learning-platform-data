# Tích hợp kiểm thử đơn vị với Maven Surefire và Gradle Test trong Spring Boot

## 1. Mục tiêu và lý do cần tích hợp test vào bản dựng

**Kiểm thử đơn vị (unit test)** xác minh một đơn vị hành vi nhỏ như phương thức, lớp hoặc service trong điều kiện đầu vào có kiểm soát. Đơn vị được kiểm thử nên chạy nhanh, dễ tái lập và không cần phụ thuộc vào database, HTTP server hoặc dịch vụ bên ngoài. Một dự án Spring Boot có thể viết unit test bằng **JUnit Jupiter** (JUnit 5) và dùng **Mockito** để thay thế cộng tác viên, nhưng để test thực sự chạy trong quá trình build, bạn còn cần tích hợp với **công cụ thực thi test** của Maven hoặc Gradle.

Trong dự án Maven, phần lớn unit test Java được chạy bởi **Maven Surefire Plugin** tại phase `test`. Trong dự án Gradle có Java plugin, unit test được chạy bởi task kiểu **`Test`**, thường tên là `test`. Với JUnit Jupiter, Gradle cần cấu hình `useJUnitPlatform()`.

Sau bài học, bạn có thể:

1. Phân biệt **JUnit/Mockito** là thư viện viết test với **Surefire/Gradle Test** là cơ chế phát hiện, thực thi và báo cáo test.
2. Đặt mã nguồn và test đúng thư mục chuẩn của Maven/Gradle; tạo một unit test Java 17+ chạy được ở cả hai hệ build.
3. Cấu hình `spring-boot-starter-test`, Surefire 3.x hoặc Gradle `useJUnitPlatform()` đúng cách.
4. Chạy toàn bộ test hoặc một lớp/method test trên Windows và Linux, đọc exit code, số test và báo cáo XML/HTML.
5. Tích hợp test vào `package`/`verify` của Maven và `build`/`check` của Gradle hoặc CI.
6. Nhận diện việc test bị bỏ qua, không được phát hiện hoặc chạy chậm do tải Spring ApplicationContext, và biết cách điều tra.

**Ví dụ xuyên suốt:** dùng Java 17 và Spring Boot 3.3.5 để minh họa cấu hình. Số phiên bản là ví dụ có chủ đích, không mặc định là bản Spring Boot mới nhất; khi áp dụng, dùng phiên bản được quản lý trong dự án thật và Gradle/Maven Wrapper tương thích.

## 2. JUnit, Mockito, Surefire và Gradle Test giữ vai trò nào?

| Thành phần | Vai trò | Chạy ở đâu? |
| --- | --- | --- |
| **JUnit Jupiter** | `@Test`, `@ParameterizedTest`, assertions, lifecycle callbacks | Chạy trên **JUnit Platform** thông qua test engine |
| **Mockito** | Tạo mock/stub, xác minh tương tác với dependency | Bên trong code unit test |
| **Spring Boot Starter Test** | Gom JUnit Jupiter, Spring Test, AssertJ, Mockito và công cụ test phổ biến | Dependency ở **test classpath** |
| **Maven Surefire** | Phát hiện và thực thi unit tests ở Maven phase `test` | Maven lifecycle, ghi báo cáo `target/surefire-reports/` |
| **Gradle Test** | Task test của Java/JVM plugin, lọc test và thực thi qua JUnit Platform khi cấu hình | Gradle task graph, báo cáo dưới `build/` |

Ví dụ một lớp `GreetingServiceTest` có `@Test` chỉ **mô tả** test. Nó được thực thi khi Maven Surefire hoặc Gradle Test nhận diện đúng JUnit engine và chọn lớp đó. **Biên dịch test thành công chưa chứng minh đã chạy test**.

Spring Boot Starter Test quản lý bộ thư viện test phù hợp với phiên bản Boot/BOM, giảm việc tự ghép các version JUnit, Mockito và phụ thuộc liên quan. Tuy nhiên, Starter Test **không thay thế plugin/task của build tool**. Maven vẫn cần Surefire tương thích, Gradle vẫn cần `Test` sử dụng JUnit Platform.

### Đường đi của một lần chạy unit test

~~~text
Mã Java: src/main/java
             |
             v
       compileJava / compile
             |
Test Java: src/test/java
             |
             v
       compileTestJava / testCompile
             |
             v
JUnit Jupiter annotations + Test Engine
             |
             +-- Maven Surefire tại phase test
             |      -> target/surefire-reports/
             |
             +-- Gradle task test
                    -> build/test-results/test/
                    -> build/reports/tests/test/
             |
             v
       PASS / FAIL / SKIPPED + mã thoát build
~~~

Thực tế Maven và Gradle đặt tên task/goal khác nhau; sơ đồ trên mô tả **luồng logic**, không phải log được in nguyên văn.

## 3. Cấu trúc thư mục dùng chung cho Maven và Gradle

Các ví dụ trong bài đặt ở một dự án tên `unit-test-demo`:

~~~text
unit-test-demo/
├── pom.xml                     # Dùng khi chọn Maven
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/
├── build.gradle                # Dùng khi chọn Gradle
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
└── src/
    ├── main/java/com/example/demo/
    │   ├── DemoApplication.java
    │   ├── GreetingService.java
    │   └── PriceService.java
    └── test/java/com/example/demo/
        ├── GreetingServiceTest.java
        └── PriceServiceTest.java
~~~

Sơ đồ hiển thị **hai phương án build** để so sánh; trong thực hành, chọn **Maven hoặc Gradle** tương ứng với dự án đã khởi tạo. Không cần duy trì cả hai bộ file build/Wrapper trong project thật.

Các file Java có thể giữ nguyên khi chuyển từ Maven sang Gradle vì đều dùng bố cục chuẩn `src/main/java`, `src/test/java` và package `com.example.demo`. Maven cũng hỗ trợ `src/test/resources`; Gradle Java plugin có source set `test` tương đương.

### File `src/main/java/com/example/demo/DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Ứng dụng mẫu có main class Spring Boot hợp lệ để cả task đóng gói Spring Boot JAR của Maven và Gradle có điểm vào. Vì chỉ dùng `spring-boot-starter`, ứng dụng **không bắt buộc mở HTTP port**.

### File `src/main/java/com/example/demo/GreetingService.java`

~~~java
package com.example.demo;

public final class GreetingService {

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        return "Xin chào, " + name.trim();
    }
}
~~~

Lớp này là mã Java 17+ độc lập với Spring ApplicationContext. Đây là đối tượng lý tưởng để viết unit test vì logic đầu vào/đầu ra rõ ràng và không cần kết nối môi trường bên ngoài.

### File `src/test/java/com/example/demo/GreetingServiceTest.java`

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceTest {

    private final GreetingService service = new GreetingService();

    @Test
    void greetsAndTrimsName() {
        assertEquals("Xin chào, An", service.greet(" An "));
    }

    @Test
    void rejectsNull() {
        IllegalArgumentException ex = assertThrows(
                IllegalArgumentException.class,
                () -> service.greet(null)
        );
        assertEquals("Name must not be blank", ex.getMessage());
    }

    @ParameterizedTest
    @ValueSource(strings = {"", "   "})
    void rejectsBlankNames(String value) {
        assertThrows(IllegalArgumentException.class,
                () -> service.greet(value));
    }
}
~~~

**Giải thích:**

- `@Test` đánh dấu hai phương thức kiểm thử độc lập.
- `assertEquals` so sánh **giá trị thực** với giá trị mong đợi.
- `assertThrows` xác minh exception type và cho phép kiểm tra thông điệp lỗi.
- `@ParameterizedTest` chạy cùng logic cho **hai bộ dữ liệu** `""` và `"   "`; JUnit báo cáo nhiều lần thực thi tương ứng.
- Test không có `@SpringBootTest` vì không cần tải container Spring. JUnit Jupiter cho phép phương thức test và lớp test không cần `public`.

Khi runner hỗ trợ JUnit Jupiter và `junit-jupiter-params` có trong test classpath (được Starter Test cung cấp trong cấu hình ví dụ), tất cả assertions phải pass. Không dự đoán số dòng log hoặc thời gian thực thi cố định: plugin và mức log thay đổi theo phiên bản.

## 4. Phương án Maven: tích hợp với Surefire

### 4.1. Một `pom.xml` tối thiểu có thể dùng cho ví dụ

Đây là **POM độc lập** cho project Maven dùng Spring Boot Starter Parent. Nếu dự án đã có `pom.xml`, chỉ thêm các dependency/plugin cần thiết vào cấu hình đang tồn tại:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>unit-test-demo</artifactId>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Vì sao không khai báo version JUnit/Surefire ở đây?** `spring-boot-starter-parent` cung cấp dependency management cho Starter Test và **plugin management** cho các Maven plugin phổ biến, gồm Surefire ở phiên bản Spring Boot tương ứng. Với packaging dạng `jar`, Maven lifecycle đã gắn Surefire test goal vào phase `test`; thông thường không cần tự thêm execution `surefire:test` vào POM.

Nếu dự án **chỉ import `spring-boot-dependencies` BOM** và không kế thừa Spring Boot Parent, cần phân biệt: BOM import quản lý **dependency versions**, nhưng **không mang theo toàn bộ Maven plugin management** từ Parent. Khi đó, dự án/corporate parent phải chỉ định Maven Compiler Plugin và **Surefire phiên bản hỗ trợ JUnit Platform** (thường dùng Surefire 3.x) cùng các plugin build liên quan. Không dựa vào phiên bản Surefire rất cũ do Maven mặc định cung cấp.

### 4.2. Surefire chạy ở phase nào?

Với Maven packaging `jar` thông thường, đường đi khi gọi `test` là:

~~~text
validate
  -> generate-sources
  -> process-resources
  -> compile
  -> process-test-resources
  -> test-compile
  -> test  [maven-surefire-plugin:test]
~~~

Đây là hình lược giản các phase quan trọng: Maven còn có các phase trung gian khác. Lệnh `mvn test` chạy mọi phase cần thiết **đến và bao gồm `test`**. `mvn package` và `mvn verify` cũng đi qua phase `test`; do đó chúng chạy unit tests khi không có cấu hình bỏ qua hoặc loại chúng.

Tách khỏi Maven **Failsafe Plugin**: Failsafe thường dùng cho **integration test** tại phase `integration-test` và `verify`, với tên lớp như `*IT`. Không cần Failsafe cho `GreetingServiceTest` đang học.

### 4.3. Cấu hình Surefire có chủ đích

Để bản dựng fail khi **không phát hiện unit test nào**, có thể cấu hình trong `<build><plugins>` của POM Spring Boot Parent:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <failIfNoTests>true</failIfNoTests>
    </configuration>
</plugin>
~~~

Đây là **trích đoạn plugin**, không phải POM đầy đủ. Parent quản lý version của plugin; dự án chỉ bổ sung cấu hình. Với POM không dùng Parent và không được corporate parent quản lý Surefire, phải khai báo `<version>` Surefire thích hợp một cách tường minh.

Quy tắc tên lớp mặc định của Surefire thường nhận các dạng `Test*.java`, `*Test.java`, `*Tests.java`, `*TestCase.java`; lớp `GreetingServiceTest` phù hợp. Lớp `GreetingServiceIT` thường không thuộc tập unit test mặc định của Surefire; nếu muốn chạy integration test riêng, dùng Failsafe hoặc cấu hình quy tắc có chủ đích.

**Không nên thêm include/exclude phức tạp khi chưa cần:** một pattern sai có thể khiến Surefire không tìm thấy test dù source code đúng. Khi thêm cấu hình, kiểm tra báo cáo và số test thực sự chạy.

## 5. Phương án Gradle: tích hợp với task `Test`

### 5.1. `settings.gradle` và `build.gradle` dùng Groovy DSL

File **`settings.gradle`**:

~~~groovy
rootProject.name = 'unit-test-demo'
~~~

File **`build.gradle`**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Vai trò từng phần:**

- `id 'java'` tạo source sets `main`/`test`, các task compile và task `test`; Spring Boot Gradle plugin hỗ trợ `bootJar`, `bootRun`.
- `io.spring.dependency-management` kết hợp Spring Boot plugin để import BOM, cung cấp version của `spring-boot-starter` và Starter Test.
- `testImplementation` đưa thư viện vào classpath test nhưng không biến chúng thành runtime dependency của ứng dụng.
- `useJUnitPlatform()` khiến Gradle Test task dùng JUnit Platform, cần để JUnit Jupiter engine phát hiện phương thức `@Test`.
- `java.toolchain` yêu cầu JDK 17 cho các công việc Java tương ứng; có thể cần cài JDK 17 hoặc cấu hình toolchain resolver để tìm được JDK.

Với project dùng `dependencyResolutionManagement` ở settings và `FAIL_ON_PROJECT_REPOS`, **bỏ block `repositories { mavenCentral() }` trong `build.gradle`** và đặt kho ở settings đúng chính sách. Phần còn lại vẫn có cùng ý nghĩa.

### 5.2. Kotlin DSL tương đương

File **`settings.gradle.kts`**:

~~~kotlin
rootProject.name = "unit-test-demo"
~~~

File **`build.gradle.kts`**:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Chọn **Groovy hoặc Kotlin DSL** theo file dự án hiện có; không cần tạo đồng thời hai bộ file. Source Java `DemoApplication`, `GreetingService`, `GreetingServiceTest` ở mục 3 giữ nguyên.

### 5.3. Task graph và vị trí unit test

Khi gọi Gradle `test`, Java plugin tự xác định các dependency task cần thiết để compile source `main`, compile `test`, xử lý test resources rồi thực thi. Với Java plugin thông thường, task `check` phụ thuộc `test`; task `build` phụ thuộc cả `assemble` và `check`, nên **`build` chạy unit test** trừ khi người dùng hoặc cấu hình cố tình vô hiệu hóa/bỏ qua chúng.

Khác Maven Surefire, Gradle dùng task `Test` và JUnit Platform engine để discover test; các **quy tắc tên mặc định của Surefire** không mặc nhiên là toàn bộ quy tắc của Gradle Test. Có thể giới hạn classes bằng `--tests` hoặc cấu hình filter, nhưng phải đọc kết quả thật để biết test nào được chọn.

## 6. Chạy test lần đầu trên Linux và Windows

Thực hiện tại thư mục chứa file Wrapper phù hợp. **Chọn Maven hoặc Gradle, không cần chạy cả hai đối với một project chỉ có một công cụ build.**

### 6.1. Linux/macOS với bash

~~~bash
# Phương án Maven
./mvnw --version
./mvnw clean test
./mvnw clean verify

# Phương án Gradle
./gradlew --version
./gradlew clean test
./gradlew clean build
~~~

`clean test` cho một lượt thực thi unit test sạch, còn `clean verify` (Maven) hoặc `clean build` (Gradle) chạy quy trình build/verification rộng hơn theo cấu hình. Không có yêu cầu phải chạy cả `test` và `verify/build` liên tiếp mỗi lần trong CI; chọn một goal/task bao phủ những kiểm tra cần thiết.

### 6.2. Windows PowerShell

~~~powershell
# Phương án Maven
.\mvnw.cmd --version
.\mvnw.cmd clean test
.\mvnw.cmd clean verify

# Phương án Gradle
.\gradlew.bat --version
.\gradlew.bat clean test
.\gradlew.bat clean build
~~~

Windows Command Prompt có thể gọi `mvnw.cmd` hoặc `gradlew.bat` tại thư mục hiện tại. Trong PowerShell cần `.` để chỉ script ở thư mục hiện tại.

### 6.3. Chạy một lớp hoặc một phương thức test

Với Maven Surefire:

~~~bash
./mvnw -Dtest=GreetingServiceTest test
./mvnw -Dtest=GreetingServiceTest#greetsAndTrimsName test
~~~

Với Gradle:

~~~bash
./gradlew test --tests 'com.example.demo.GreetingServiceTest'
./gradlew test --tests 'com.example.demo.GreetingServiceTest.greetsAndTrimsName'
~~~

Trên PowerShell, thay phần gọi Wrapper thành `.\mvnw.cmd` hoặc `.\gradlew.bat` và giữ các đối số. Các lệnh này **lọc phạm vi thực thi** cho việc debug; không thay thế một lần chạy đủ bộ test trên CI.

Nếu test class nằm ở package khác, thay `com.example.demo` bằng package thật. Nếu Maven reactor nhiều module, giới hạn bằng `-pl <module>` khi cần; với Gradle multi-project có thể dùng `:app:test`. Việc chọn một module mà các module phụ thuộc chưa được build có thể cần lệnh bổ sung tương ứng (ví dụ Maven `-am`).

## 7. Đọc kết quả: PASS, FAIL, SKIPPED và báo cáo

Không nên chỉ nhìn dòng cuối `BUILD SUCCESS` hoặc `BUILD SUCCESSFUL` rồi mặc định **mọi unit test đều đã chạy**. Cần xác nhận số lượng test được tìm thấy, số đã chạy, số fail/error/skipped, cùng bộ báo cáo có thể mở lại trong CI.

| Công cụ | Dấu hiệu terminal | Báo cáo test thường dùng |
| --- | --- | --- |
| Maven Surefire | Tóm tắt `Tests run: ..., Failures: ..., Errors: ..., Skipped: ...`, cuối cùng `BUILD SUCCESS` hoặc `BUILD FAILURE` | `target/surefire-reports/`, gồm XML `TEST-*.xml` và báo cáo text |
| Gradle Test | Task `:test` chạy hoặc được đánh dấu `UP-TO-DATE`/cache; lỗi thường dẫn tới `BUILD FAILED` | `build/test-results/test/TEST-*.xml` và `build/reports/tests/test/index.html` |

**Ví dụ test thất bại thực sự:** nếu thay assertion trong `greetsAndTrimsName()` bằng giá trị kỳ vọng `"Xin chào, Bình"` nhưng `greet(" An ")` vẫn trả `"Xin chào, An"`, JUnit báo lỗi so sánh. Surefire hoặc Gradle Test task sẽ báo build thất bại theo cấu hình thông thường, và CI nhận **exit code khác 0**. Điều này mới làm unit test trở thành cổng kiểm soát chất lượng, thay vì chỉ là file code nằm trong repository.

**Lưu ý về Gradle cache:** `UP-TO-DATE` hoặc `FROM-CACHE` có thể là kết quả hợp lệ khi input/task outputs không đổi. Nếu cần cưỡng bức chạy lại để điều tra, dùng `./gradlew test --rerun-tasks` khi có lý do. Không dùng nó mặc định ở mọi build vì mất lợi ích incremental build.

**Lưu ý về Maven:** chạy `./mvnw test` có thể bỏ qua `clean` và giữ output cũ theo lifecycle bình thường; khi cần xác minh từ đầu, dùng `clean test` hoặc `clean verify`.

### Xem báo cáo

Linux/bash:

~~~bash
ls -la target/surefire-reports/
ls -la build/test-results/test/
ls -la build/reports/tests/test/
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem .\target\surefire-reports\
Get-ChildItem .\build\test-results\test\
Get-ChildItem .\build\reports\tests\test\
~~~

Mỗi lệnh chỉ áp dụng cho **công cụ build tương ứng**. Nếu thư mục không tồn tại, kiểm tra trước tiên test task/plugin có chạy, có test class hợp lệ và có quyền ghi báo cáo hay không. **Đừng tạo báo cáo giả** khi test thực tế chưa được phát hiện.

## 8. Unit test có dependency: dùng Mockito để giữ test cô lập

Một service thường phụ thuộc vào repository, HTTP client hoặc gateway. Unit test không cần gọi cơ sở dữ liệu hay HTTP thật. Mockito tạo mock để cung cấp kết quả có kiểm soát rồi xác minh service đã sử dụng dependency đúng.

### File `src/main/java/com/example/demo/PriceService.java`

~~~java
package com.example.demo;

import java.util.Objects;

public final class PriceService {

    public interface DiscountProvider {
        long discountCents(String customerId);
    }

    private final DiscountProvider discountProvider;

    public PriceService(DiscountProvider discountProvider) {
        this.discountProvider = Objects.requireNonNull(discountProvider);
    }

    public long finalCents(String customerId, long subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Subtotal must not be negative");
        }
        long discount = discountProvider.discountCents(customerId);
        if (discount < 0 || discount > subtotalCents) {
            throw new IllegalArgumentException("Invalid discount");
        }
        return subtotalCents - discount;
    }
}
~~~

### File `src/test/java/com/example/demo/PriceServiceTest.java`

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class PriceServiceTest {

    @Test
    void subtractsDiscountReturnedByProvider() {
        PriceService.DiscountProvider provider =
                mock(PriceService.DiscountProvider.class);
        when(provider.discountCents("A01")).thenReturn(150L);

        PriceService service = new PriceService(provider);
        long actual = service.finalCents("A01", 1_000L);

        assertEquals(850L, actual);
        verify(provider).discountCents("A01");
    }
}
~~~

Test này biên dịch với JUnit Jupiter và Mockito trong Spring Boot Starter Test. Nó **không dùng** `@SpringBootTest` và không dựng ApplicationContext. `when(...).thenReturn(...)` là stub, còn `verify` xác nhận tương tác cần thiết. Chọn giá trị bằng số nguyên cents giúp tránh vấn đề so sánh dấu phẩy động ở ví dụ.

**Giới hạn của mock:** unit test chứng minh logic service với behavior giả lập, **không chứng minh** database driver, SQL query hoặc API đối tác hoạt động thực. Những đường đi ấy cần integration test riêng khi phù hợp.

## 9. Vì sao không nên dùng `@SpringBootTest` cho mọi unit test?

`@SpringBootTest` tải Spring ApplicationContext và nhiều bean theo cấu hình. Nó hữu ích khi cần xác minh **tích hợp Spring Boot** (auto-configuration, bean wiring, properties, context startup) nhưng thường tốn tài nguyên, có thể phụ thuộc môi trường và chạy chậm hơn test chỉ khởi tạo Java object.

Phân biệt:

| Bài toán | Cách kiểm thử phù hợp |
| --- | --- |
| Tính toán, validate, chuyển đổi giá trị | JUnit Jupiter thuần, khởi tạo đối tượng trực tiếp |
| Service gọi repository/gateway nhưng muốn cô lập logic | JUnit + Mockito mock |
| Cần test logic controller với Spring MVC infrastructure | Spring test slice như `@WebMvcTest` nếu phù hợp với project |
| Cần test toàn bộ wiring/configuration của ứng dụng | `@SpringBootTest` hoặc integration test thiết kế phù hợp |
| Cần database/container/HTTP service thực tế | Integration test riêng, setup và teardown rõ ràng |

**Không đồng nhất nhãn với plugin:** một `@SpringBootTest` đặt trong lớp `SomeTest` vẫn có thể được Surefire chạy ở phase `test`; framework annotation không tự chuyển lớp đó sang Maven Failsafe. Tương tự Gradle sẽ chạy những lớp được task `Test` chọn; muốn tách integration test về task/source set riêng cần cấu hình bổ sung.

Các unit test của mục 3 và 8 chạy không cần database, web server, `application-prod.yml` hay biến môi trường production. Đây là dấu hiệu tốt cho test suite nhanh và ổn định.

## 10. Chọn test, gắn tag và kiểm soát việc bỏ qua

### 10.1. JUnit Jupiter tag

Có thể đánh dấu một test bằng `@Tag("unit")`:

~~~java
// Trích đoạn đặt trên lớp hoặc phương thức test có JUnit Jupiter
@org.junit.jupiter.api.Tag("unit")
@org.junit.jupiter.api.Test
void calculatesAUnitRule() {
    org.junit.jupiter.api.Assertions.assertEquals(4, 2 + 2);
}
~~~

**Đoạn trên là một phương thức trong lớp test**, không phải file Java độc lập. Có thể cấu hình filter theo tag khi dự án có nhiều nhóm test. Với Gradle Groovy DSL:

~~~groovy
tasks.named('test') {
    useJUnitPlatform {
        includeTags 'unit'
    }
}
~~~

Đừng thêm `includeTags 'unit'` vào bản mẫu gốc nếu những test hiện tại chưa được gắn tag: điều đó có thể loại hết chúng khỏi lượt chạy. Maven Surefire 3.x hỗ trợ lựa chọn nhóm/tag của JUnit Platform qua cấu hình `groups`/ `excludedGroups` khi cần; phải đọc phiên bản plugin và kiểm tra test report.

### 10.2. Các lệnh bỏ qua test và rủi ro

| Lệnh | Tác động thường thấy | Khi nào dùng? |
| --- | --- | --- |
| Maven `-DskipTests` | Bỏ **thực thi** test của Surefire; test source thường vẫn biên dịch | Điều tra tạm thời, có ghi chú rõ |
| Maven `-Dmaven.test.skip=true` | Bỏ cả compile và thực thi test ở các plugin hỗ trợ property này | Trường hợp build đặc biệt, không dùng thay test của CI |
| Gradle `-x test` | Loại task `test` khỏi task graph cho lượt gọi đó | Debug tạm thời |
| JUnit `@Disabled` | Bỏ một test hoặc lớp được đánh dấu | Chỉ khi có lý do và theo dõi được |

**Bỏ test không chứng minh test đã pass.** CI nên xác nhận không có flag skip ngoài kế hoạch và có test reports thể hiện kết quả. Nếu dùng Maven `-Dtest=... test` hay Gradle `--tests`, bạn chỉ chạy một phần suite. Đừng lấy kết quả đó thay thế toàn bộ kiểm tra trước khi merge.

### 10.3. Không có test cũng có thể thấy build xanh

Nếu test class bị đặt sai package/thư mục, đặt tên không khớp pattern của Surefire, thiếu JUnit Platform engine hoặc Gradle không gọi `useJUnitPlatform()`, build có thể không chạy test mong muốn. Một số cấu hình sẽ vẫn báo thành công nếu không phát hiện test.

Kiểm tra **số test phát hiện và thực thi**, không chỉ trạng thái build. Với Maven có thể bật `failIfNoTests` như mục 4; với Gradle nên đọc XML/HTML test report và áp dụng chính sách báo lỗi khi test suite dự kiến trống phù hợp với phiên bản Gradle/dự án.

## 11. Đưa kiểm thử đơn vị vào CI

CI cần cấp **JDK phù hợp**, gọi đúng **Wrapper** và chạy lifecycle có test. Dưới đây là **hai lựa chọn thay thế**, mỗi repository chỉ chọn biến thể tương ứng với hệ build. Những major version của GitHub Actions được nêu để minh họa cấu trúc; kiểm tra phiên bản action/chính sách pin SHA đang được tổ chức hỗ trợ trước khi dùng thực tế.

### Phương án Maven: `.github/workflows/maven-test.yml`

~~~yaml
name: Maven unit tests

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Verify tool versions
        run: |
          java -version
          ./mvnw --version

      - name: Run tests and verify build
        run: ./mvnw --batch-mode --no-transfer-progress clean verify
~~~

### Phương án Gradle: `.github/workflows/gradle-test.yml`

~~~yaml
name: Gradle unit tests

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: gradle

      - name: Verify tool versions
        run: |
          java -version
          ./gradlew --version

      - name: Run tests and build
        run: ./gradlew clean build
~~~

Nếu Wrapper script `mvnw` hoặc `gradlew` thiếu executable bit trên Linux CI, runner báo `Permission denied`. Giải quyết bằng cách commit executable permission trong Git hoặc dùng cách gọi shell được dự án cho phép; không kết luận do JUnit/Surefire.

**Kiểm chứng CI:** job phải trả status thất bại khi test fail. Nếu cần đọc hoặc lưu báo cáo sau build, dùng cơ chế artifact/report của CI tương ứng và đặt bước thu thập dữ liệu có thể chạy khi test thất bại. Những bước nâng cao đó phụ thuộc chính sách pipeline; bản mẫu trên giữ nguyên phần cốt lõi là chạy unit tests trước khi chấp nhận bản dựng.

## 12. Lỗi phổ biến và cách khoanh vùng

| Triệu chứng | Nguyên nhân có khả năng | Cách kiểm tra và sửa |
| --- | --- | --- |
| Maven build thành công nhưng không có `GreetingServiceTest` trong report | Tên test không khớp Surefire patterns, sai thư mục, bị exclude, plugin quá cũ | Kiểm tra `src/test/java`, `target/surefire-reports`, Surefire version và effective POM |
| `No tests were executed` / không tìm thấy Jupiter | Thiếu JUnit Jupiter engine hoặc runner không cấu hình JUnit Platform | Dùng Starter Test/BOM phù hợp, Surefire 3.x hoặc Gradle `useJUnitPlatform()` |
| Gradle `test` không tìm thấy test | Chưa áp dụng Java plugin/source set, thiếu `useJUnitPlatform()`, filters loại hết test | Xem task `test`, `testRuntimeClasspath`, `--tests`, XML report và `build.gradle` |
| Lỗi `package org.junit.jupiter.api does not exist` | Thiếu JUnit dependencies trong test classpath, hoặc test source bị biên dịch như main source | Thêm `spring-boot-starter-test` với scope `test`/`testImplementation`, đặt file đúng `src/test/java` |
| Maven báo provider/plugin lỗi khi dùng JUnit 5 | Surefire version cũ hoặc dependency không tương thích | Kiểm tra effective POM và nâng Surefire lên bản hỗ trợ JUnit Platform theo matrix dự án |
| `UnnecessaryStubbingException` khi dùng Mockito | Stub không được sử dụng hoặc setup mock không phù hợp strictness | Xóa stub thừa và sửa test; không tắt strictness toàn cục chỉ để che lỗi |
| Test pass trong IDE nhưng fail Maven/Gradle | IDE dùng JDK/classpath/runner khác, cấu hình test khác | Chạy Wrapper từ terminal, kiểm tra JDK, phụ thuộc và report rồi đồng bộ IDE |
| Unit test fail vì thiếu database/secret | Test đang tải Spring context hoặc gọi dependency thật | Tách unit test khỏi Spring context, mock dependency, chuyển kiểm tra tích hợp sang test phù hợp |
| Test ngẫu nhiên pass/fail trong CI | Phụ thuộc thời gian, timezone, thứ tự chạy, shared static state hoặc network | Làm input deterministic, cách ly state, tránh `Thread.sleep` để đồng bộ |
| Maven `BUILD SUCCESS` nhưng CI không ghi report | Plugin không chạy, test bị skip hoặc report path sai | Kiểm tra Surefire summary, `skipTests` và `target/surefire-reports` |
| Gradle `:test UP-TO-DATE` nhưng muốn tái hiện lỗi | Output được Gradle xác nhận còn hợp lệ hoặc lấy từ cache | Sử dụng `test --rerun-tasks` cho mục đích điều tra, lưu log test |
| JUnit 4 `@Test` không chạy dưới Jupiter | Test cũ dùng JUnit 4 runner và thiếu Vintage engine | Ưu tiên migrate JUnit Jupiter; nếu cần giữ JUnit 4, cấu hình Vintage engine có chủ đích |

Khi điều tra, xác định lỗi ở bước **compile main → compile test → discover test → run assertions → generate report**. Không chữa lỗi thiếu engine bằng cách đổi tên mọi test, và không bỏ test khi lỗi thực sự thuộc assertion.

### Nhật ký cần đọc ở đâu?

- Maven: stdout của `mvnw clean test`, `target/surefire-reports/`, `./mvnw help:effective-pom` nếu nghi plugin/configuration.
- Gradle: stdout của `gradlew test --info` khi cần chẩn đoán, `build/reports/tests/test/index.html`, XML dưới `build/test-results/test/`.
- CI: log setup Java, command đã thực thi, output test summary và đường dẫn artifact/report của pipeline.

Không công khai thông tin secret hoặc chi tiết kết nối nhạy cảm từ log CI khi cần nhờ người khác xem lỗi.

## 13. Bài thực hành và tiêu chí hoàn thành

Thực hành trên **một** dự án Spring Boot Maven **hoặc** Gradle đã có Wrapper và Java 17+ tương ứng:

1. Xác định công cụ build và kiểm tra JDK bằng `java -version` cùng `./mvnw --version` hoặc `./gradlew --version`.
2. Thêm Starter Test và runner tương ứng: Maven Surefire 3.x được parent/plugin management cấp, hoặc Gradle `tasks.named('test') { useJUnitPlatform() }`.
3. Tạo `GreetingService.java`, `GreetingServiceTest.java`, `PriceService.java`, `PriceServiceTest.java` đúng package/thư mục của ví dụ. Giữ `DemoApplication.java` nếu muốn build Spring Boot executable JAR.
4. Chạy `clean test`, xác minh unit tests được tìm thấy và tất cả assertions pass; xác nhận report tồn tại.
5. Chạy lọc riêng `GreetingServiceTest`, rồi chạy đủ bộ test lại để không bỏ sót `PriceServiceTest`.
6. Cố tình đổi giá trị kỳ vọng trong một assertion để gây FAIL; quan sát Maven Surefire hoặc Gradle Test trả lỗi và report chỉ ra đúng test bị fail. **Khôi phục assertion** rồi chạy lại đầy đủ.
7. Chạy `clean verify` (Maven) hoặc `clean build` (Gradle) để xác minh unit test nằm trong quy trình build chuẩn.
8. Đối chiếu với CI cùng JDK/Wrapper và xác nhận job không cố ý dùng skip flag.

Bạn hoàn thành bài khi có thể giải thích **ai phát hiện và chạy JUnit test**, chứng minh test được thực thi qua Maven/Gradle, biết xem report, và phân biệt được lỗi assertion với lỗi discovery, thiếu dependency hoặc cấu hình test framework.

## Tài liệu chính thức tham khảo

- [JUnit 5 – User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Apache Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Maven Surefire – Inclusions and Exclusions](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html)
- [Maven Surefire – Using JUnit 5 Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Gradle – Testing in Java and JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle – Test Task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html)
- [Spring Boot – Testing Reference](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Spring Boot – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
