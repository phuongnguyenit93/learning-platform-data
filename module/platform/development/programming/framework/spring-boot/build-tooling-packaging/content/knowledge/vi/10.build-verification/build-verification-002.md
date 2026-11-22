# Chạy JUnit Platform và kiểm tra việc phát hiện đúng bài kiểm thử

Một dự án Spring Boot có thể **biên dịch thành công và báo BUILD SUCCESS** nhưng vẫn không chạy bài kiểm thử nào. Ngược lại, có thể nhìn thấy file `*Test.java` trong IDE nhưng Gradle/Maven không nhận diện nó, hoặc test được **phát hiện** nhưng bị `@Disabled`, bộ lọc tag hay rule loại trừ khiến không thực thi. Vì vậy, kiểm tra bản dựng không dừng ở việc gõ `test`; cần xác minh **đã chọn đúng engine, tìm thấy đúng test, thực thi đúng số lượng và ghi kết quả đáng tin cậy**.

Bài này hướng dẫn JUnit Platform với **JUnit Jupiter (JUnit 5)** trong dự án Spring Boot dùng **Gradle hoặc Maven**, từ cấu hình dependency và một bộ test Java 17 chạy được, đến lọc test, xem report, phân biệt test bỏ qua với không phát hiện, và thiết lập kiểm tra cho CI. Ví dụ thống nhất ở **Spring Boot 3.3.13, Java 17, Gradle 8.x và Maven 3.9.x** để diễn giải một cấu hình cụ thể; phiên bản minh họa không được hiểu là release mới nhất. Nếu project đang ở nhánh khác, đối chiếu version/plugin với tài liệu của chính nhánh đó.

## 1. JUnit Platform, Jupiter và build tool làm gì?

JUnit 5 có các thành phần khác nhau, mỗi thành phần xuất hiện ở một bước:

| Thành phần | Vai trò | Điều gì xảy ra nếu thiếu/sai? |
| --- | --- | --- |
| **JUnit Platform** | Cơ sở hạ tầng **khám phá và điều phối thực thi** test thông qua các `TestEngine` | Build tool không chạy được test qua Platform như mong muốn |
| **JUnit Jupiter API** | Các annotation/assertion như `@Test`, `@ParameterizedTest`, `Assertions.assertEquals` | Mã test không biên dịch nếu thiếu API |
| **JUnit Jupiter Engine** | Nhận và thực thi test theo mô hình Jupiter | Có thể compile test nhưng **không có engine để thực thi** |
| **JUnit Platform Launcher** | API mà IDE/build tool sử dụng để yêu cầu khám phá và chạy test | Tùy phiên bản công cụ, có thể lỗi/thiếu thành phần runtime cần thiết |
| **Gradle `Test` task** | Khởi động test worker, kết nối JUnit Platform và lưu report | Có thể dùng sai test framework nếu thiếu `useJUnitPlatform()` |
| **Maven Surefire Plugin** | Chạy unit test ở phase `test`, lựa chọn provider/framework và xuất report | Test có thể bị bỏ qua bởi naming pattern, bộ lọc hoặc plugin quá cũ |
| **`spring-boot-starter-test`** | Gom các dependency test hữu ích: Spring Boot Test, JUnit Jupiter, AssertJ, Mockito... | Không tự thay thế việc cấu hình test task/provider thích hợp |

Luồng khái niệm:

```text
src/test/java/*.java
     |
     v
compileTestJava / testCompile
     |
     v
.class trên test classpath
     |
     v
Gradle Test / Maven Surefire
     |
     v
JUnit Platform Launcher + TestEngine có trên classpath
     |
     +--> Discovery (selectors, test classes, methods)
     |
     +--> Filters (class name, method, tag, engine...)
     |
     +--> Execution (pass, fail, aborted, skipped/disabled)
     |
     v
XML / HTML / text reports + mã thoát của build
```

Đừng đánh đồng **đã biên dịch**, **đã khám phá** và **đã thực thi**. Một class Java có `@Test` có thể biên dịch nhưng không nằm trên test runtime classpath; một test được JUnit nhận diện có thể bị disabled; một lệnh `test` có thể không làm gì khi source set không có file test.

**JUnit 4 khác JUnit Jupiter.** Jupiter dùng `org.junit.jupiter.api.Test`; JUnit 4 dùng `org.junit.Test`. Để chạy test JUnit 4 trên Platform, thường cần thêm `junit-vintage-engine` và JUnit 4 phù hợp. Chỉ thêm Jupiter Engine **không bảo đảm chạy được** mọi test JUnit 4 cũ.

## 2. Cấu trúc dự án để công cụ tìm đúng test

Một dự án Spring Boot theo quy ước:

```text
testing-demo/
├── settings.gradle / build.gradle      (nếu dùng Gradle)
├── pom.xml                              (nếu dùng Maven)
└── src/
    ├── main/
    │   └── java/com/example/testing/
    │       ├── CheckBuildApplication.java
    │       └── MathPolicy.java
    └── test/
        ├── java/com/example/testing/
        │   └── MathPolicyTest.java
        └── resources/
            └── junit-platform.properties (chỉ cần nếu tùy chỉnh Platform)
```

Bốn điểm nền tảng:
- Mã ứng dụng nằm ở `src/main/java` và được biên dịch trước.
- Mã test nằm ở `src/test/java`; package có thể trùng package main để dễ truy cập các class/method package-private trong ví dụ.
- `src/test/resources` phục vụ test runtime, không được tự động đóng gói vào executable JAR production.
- Test dependency như Jupiter có **test scope** (Maven) hoặc **testImplementation/testRuntimeOnly** (Gradle).

Đặt test ở `src/main/java` khiến class test đi sai source set, dependency test có thể không sẵn và thậm chí bị đưa vào sản phẩm. Đặt test ở một thư mục tùy ý ngoài test source set mà không đăng ký nó với build tool thì IDE có thể hiển thị file nhưng task `test` không biết phải biên dịch/chạy.

## 3. Cấu hình Gradle chạy JUnit Platform

### 3.1. `build.gradle` Groovy DSL đầy đủ

Tạo `settings.gradle`:

```groovy
rootProject.name = 'testing-demo'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

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

Giải thích:

1. `java` tạo mặc định task `compileJava`, `compileTestJava`, `processTestResources` và `test`.
2. `spring-boot-starter-test` mang JUnit Jupiter cùng những công cụ test thường dùng vào test dependency graph.
3. `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` khai báo tường minh Platform Launcher trên test runtime classpath, tránh phụ thuộc vào launcher do phiên bản Gradle cung cấp ngầm. Version của artifact này được dependency management Spring Boot quản lý trong ví dụ.
4. `useJUnitPlatform()` **chọn JUnit Platform** làm framework khám phá/thực thi của task `test`. Đây là bước rất quan trọng khi dùng JUnit Jupiter trong cấu hình Gradle này.
5. `org.springframework.boot` hỗ trợ các Boot task; **bản thân `bootJar` không chạy test theo ý nghĩa thay thế `test`**. Trong vòng đời kiểm tra, `check`/`build` mới thường kéo theo test task qua Java plugin.

Có thể dùng Gradle native `platform(...)` thay cho `io.spring.dependency-management` nếu muốn chiến lược quản lý version riêng. Khi đó phải đưa BOM vào các test configuration phù hợp và đối chiếu phiên bản đã resolve; **không chỉ copy dòng `testImplementation` rồi bỏ cơ chế quản lý version**.

### 3.2. `build.gradle.kts` Kotlin DSL tương đương

Nếu dự án dùng Kotlin DSL, sử dụng cú pháp khác:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

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
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
```

Đây là một file `build.gradle.kts` **thay thế** cho Groovy DSL ở mục 3.1, không phải một block đặt vào `build.gradle`. `tasks.test { useJUnitPlatform() }` và `tasks.named('test') { useJUnitPlatform() }` là hai cách biểu diễn cùng ý định ở hai DSL.

Nếu project có nhiều task test riêng, cần cấu hình JUnit Platform cho **đúng task**. Đặt `useJUnitPlatform()` ở `test` mặc định không tự bảo đảm một custom task `integrationTest` cũng dùng Platform và đúng classpath.

## 4. Maven: cấu hình Surefire và JUnit Platform

Với **Spring Boot starter parent**, Maven thường được quản lý version plugin phù hợp, bao gồm Maven Surefire; starter test mang dependency Jupiter. Ví dụ `pom.xml` đầy đủ:

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
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>testing-demo</artifactId>
    <version>1.0.0</version>

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
```

**Surefire là plugin thực thi unit test ở phase `test`.** Với cấu hình `jar` mặc định, lệnh `mvn test` kích hoạt goal phù hợp của Surefire. Spring Boot parent cung cấp plugin management; nếu bạn có corporate parent hoặc chỉ import `spring-boot-dependencies` BOM, cần kiểm tra Surefire version/plugin configuration qua **effective POM**.

Không cần thêm `spring-boot-maven-plugin` để JUnit được phát hiện: plugin Boot phụ trách chạy/đóng gói ứng dụng, còn Surefire phụ trách unit tests. Ví dụ khai báo Boot plugin vì là ứng dụng Spring Boot có main class; **không nên coi `spring-boot:run` là cách chạy JUnit**.

Trong Maven Surefire 3.x, khi có JUnit Platform/Jupiter Engine trên test classpath, Surefire dùng provider Platform phù hợp để thực thi Jupiter test. Không sử dụng Surefire đời quá cũ mà chưa hỗ trợ tốt JUnit 5. Tên plugin, provider thực tế và version có thể xem ở `./mvnw help:effective-pom` và log `test`.

## 5. Bộ ví dụ Java 17 hoàn chỉnh để kiểm tra discovery

Phần này dùng **cùng mã Java** cho project Gradle hoặc Maven ở các mục trên.

### 5.1. Main class của ứng dụng

`src/main/java/com/example/testing/CheckBuildApplication.java`:

```java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CheckBuildApplication {

    public static void main(String[] args) {
        SpringApplication.run(CheckBuildApplication.class, args);
    }
}
```

Có main class để dự án Spring Boot còn có thể đóng gói ứng dụng. Bộ test bên dưới **không cần khởi động Spring application context**.

### 5.2. Lớp nghiệp vụ cần test

`src/main/java/com/example/testing/MathPolicy.java`:

```java
package com.example.testing;

public final class MathPolicy {

    private MathPolicy() {
    }

    public static int add(int left, int right) {
        return Math.addExact(left, right);
    }

    public static int divide(int dividend, int divisor) {
        return dividend / divisor;
    }
}
```

`Math.addExact` thực hiện cộng số nguyên có kiểm tra overflow; `divide` dùng phép chia nguyên Java, ném `ArithmeticException` khi divisor bằng 0. Class chỉ dùng JDK, giúp test độc lập với cơ sở dữ liệu và Spring context.

### 5.3. Bài test có test thường, tham số hóa và test bị vô hiệu hóa

`src/test/java/com/example/testing/MathPolicyTest.java`:

```java
package com.example.testing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.fail;

import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class MathPolicyTest {

    @Test
    @Tag("smoke")
    void addsTwoNumbers() {
        assertEquals(7, MathPolicy.add(3, 4));
    }

    @ParameterizedTest
    @CsvSource({
            "-1, 1, 0",
            "4, 5, 9"
    })
    @Tag("fast")
    void addsSeveralCases(int left, int right, int expected) {
        assertEquals(expected, MathPolicy.add(left, right));
    }

    @Test
    @Tag("validation")
    void dividingByZeroThrows() {
        assertThrows(ArithmeticException.class,
                () -> MathPolicy.divide(10, 0));
    }

    @Test
    @Disabled("Minh họa trạng thái skipped trong báo cáo")
    void intentionallySkipped() {
        fail("This test must stay disabled in the demonstration");
    }
}
```

**Vì sao test này hợp lệ?** JUnit Jupiter cho phép class và method test có quyền truy cập package-private; không bắt buộc khai báo `public`. Method test `@Test` không được `private` hay trả về giá trị, và ở ví dụ này không `static`. Chú ý import `org.junit.jupiter.api.Test` thay cho `org.junit.Test` của JUnit 4.

Bộ ví dụ tạo **5 test cases được nhận diện**:
- `addsTwoNumbers()`: 1 test, tag `smoke`.
- `addsSeveralCases(...)`: 2 lần chạy tương ứng 2 dòng `@CsvSource`, tag `fast`.
- `dividingByZeroThrows()`: 1 test, tag `validation`.
- `intentionallySkipped()`: 1 test **bị disabled**, không chạy body.

Với test mặc định **không có tag filter**, số liệu mong đợi là **5 được tính vào tổng, 4 thành công, 1 skipped, 0 failed, 0 errors**. Cách Gradle/Maven hiển thị dòng console khác nhau; **dùng XML/HTML report** để xác minh số liệu, không dựa vào một câu log cố định. Trong mã sản xuất, không nên để một test quan trọng bị `@Disabled` vô thời hạn; ở đây chỉ để phân biệt “đã phát hiện nhưng skipped” với “không được phát hiện”.

Các file Java ở trên biên dịch với **Java 17** trong cấu hình Gradle/Maven đã nêu. Bạn không thể dùng riêng `javac MathPolicyTest.java` khi thiếu JUnit trên classpath; hãy dùng build tool để resolve dependency, compile và chạy test.

## 6. Chạy test và xác nhận các test được phát hiện

### 6.1. Gradle

Từ thư mục dự án có Gradle Wrapper:

```bash
./gradlew clean test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat clean test
```

Tác vụ `test` phải biên dịch `src/test/java`, khởi tạo test worker qua JUnit Platform và ghi kết quả. Vị trí kết quả mặc định:

```text
build/
├── test-results/
│   └── test/
│       └── TEST-com.example.testing.MathPolicyTest.xml
└── reports/
    └── tests/
        └── test/
            └── index.html
```

Xem `build/reports/tests/test/index.html` ở trình duyệt; nếu muốn máy CI thu thập báo cáo, lấy các file XML trong `build/test-results/test/`. **Xem tổng số test và từng method/invocation**, vì dòng `BUILD SUCCESSFUL` chưa nói rõ những test nào đã chạy.

Để chạy lại khi Gradle báo `UP-TO-DATE`/`FROM-CACHE`, dùng:

```bash
./gradlew test --rerun-tasks
```

`--rerun-tasks` yêu cầu không dùng trạng thái up-to-date/cache để bỏ qua thực thi task trong lần chạy này; không nhất thiết phải `clean` toàn bộ build cho mỗi lần kiểm tra.

### 6.2. Maven

Từ thư mục dự án có Maven Wrapper:

```bash
./mvnw clean test
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd clean test
```

Maven Surefire xuất báo cáo trong:

```text
target/
└── surefire-reports/
    ├── TEST-com.example.testing.MathPolicyTest.xml
    └── com.example.testing.MathPolicyTest.txt
```

Bản report thông thường ghi kiểu:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 1
```

Đây là **số liệu mong đợi của bộ ví dụ**, không phải log thực được đo tại một môi trường cụ thể. JUnit parameterized test có **hai invocation** nên tính thành hai lần thực thi; test `@Disabled` không có method body được chạy.

### 6.3. Không có Wrapper?

Có thể thay `./gradlew` bằng `gradle` và `./mvnw` bằng `mvn` nếu Gradle/Maven đã cài phù hợp. Trong một project chia sẻ/CI, Wrapper giúp cố định phiên bản công cụ build. Kiểm tra:

```bash
java -version
./gradlew --version
./mvnw -version
```

Bạn chỉ chạy lệnh cho **build tool thực sự dùng trong dự án**, không cần cả Maven lẫn Gradle trong một project.

## 7. Discovery có nhiều tầng: tìm đúng vấn đề

Để một `@Test` được thực thi, các điều kiện sau phải đồng thời thỏa mãn:

1. **Source:** file nằm trong test source set mà build tool biết.
2. **Compile:** test class biên dịch thành bytecode trong `build/classes/java/test` (Gradle) hoặc `target/test-classes` (Maven).
3. **Classpath:** test worker có các class test, API/Engine Jupiter và dependency cần thiết.
4. **Runner/provider:** Gradle chọn `useJUnitPlatform()` hoặc Maven Surefire dùng JUnit Platform provider phù hợp.
5. **Selection/discovery:** build tool và JUnit Platform nhìn thấy class và test descriptors.
6. **Filters/conditions:** không bị loại bởi pattern, `--tests`/`-Dtest`, tag, engine filter, điều kiện disabled.
7. **Execution/report:** test được chạy hoặc ghi nhận skipped/aborted cùng kết quả.

| Quan sát | Có thể kết luận gì? | Cần xác minh tiếp |
| --- | --- | --- |
| `compileTestJava`/`testCompile` thành công | Mã test **biên dịch được** | Vẫn phải xem engine và số test chạy |
| Gradle `:test NO-SOURCE` | Task không có test source inputs hữu dụng theo cấu hình hiện tại | Vị trí file, source set, project được gọi |
| Gradle `:test UP-TO-DATE` | Task đã được quyết định không cần chạy lại do input/output không đổi | Xem report có sẵn hoặc dùng `--rerun-tasks` khi cần |
| Test được báo `skipped` | Test đã được nhận diện nhưng không thực thi body trong tình huống cụ thể | `@Disabled`, assumptions, conditions, filters |
| Maven `Tests run: 0` | Surefire không thực thi test nào | Pattern tên class, provider, test classpath, filters |
| Báo `No tests found` theo filter | Không có test khớp selector/filter cụ thể | Tên package/class/method, tag, module |
| Có lỗi `TestEngine` hoặc `Launcher` | Hạ tầng JUnit Platform trên classpath không phù hợp/thiếu | Dependency versions và testRuntimeClasspath |
| Build xanh nhưng report XML thiếu | Có thể không chạy test task, report bị đặt chỗ khác hoặc test không được phát hiện | Invocation build, task graph, report path |

**“Không có test” khác “tất cả test đều bị disabled”.** Trong ví dụ ở mục 5, `@Disabled` được phát hiện và có skip record. Nếu không có test nào khớp bộ lọc class/method/tag, số test chạy có thể là 0 hoặc build báo lỗi tùy tool/filter; đó là một trạng thái cần xử lý riêng.

## 8. Quy tắc chọn test và đặt tên lớp

### 8.1. JUnit Jupiter không đòi tên class kết thúc bằng `Test`

Ở mức JUnit Jupiter, annotation `@Test`/`@ParameterizedTest`, các điều kiện hợp lệ của class/method và engine mới quyết định test descriptor. Tuy nhiên, **build tool có thể lọc class trước khi chuyển cho engine**.

Đây là lý do đặt tên `MathPolicyTest` hữu ích: vừa rõ nghĩa vừa khớp các quy tắc của Maven Surefire.

### 8.2. Maven Surefire dùng naming patterns mặc định

Maven Surefire 3.x mặc định phát hiện các lớp có tên phù hợp một trong các mẫu:

```text
**/Test*.java
**/*Test.java
**/*Tests.java
**/*TestCase.java
```

`MathPolicyTest.java` khớp. Lớp `MathPolicyChecks.java` chứa cùng một `@Test` có thể **không được Surefire quét theo mặc định**; Gradle và IDE có thể có cách tìm khác, dẫn tới “IDE xanh nhưng Maven báo 0 tests”.

Giải pháp ưu tiên là **đặt tên lớp kiểm thử theo convention**, ví dụ `MathPolicyTest`. Nếu phải dùng tên tùy biến, cấu hình Surefire `<includes>` rõ ràng và đảm bảo không vô tình loại các lớp khác.

Đối với **integration tests** chạy bằng Maven Failsafe, tên như `*IT.java`/`IT*.java`/`*ITCase.java` thường dùng. Surefire và Failsafe là hai plugin/mục tiêu lifecycle khác nhau; không mặc định giả định `mvn test` sẽ chạy cả bộ integration tests được đặt tên `*IT.java`.

### 8.3. Class và method Jupiter hợp lệ

JUnit Jupiter cho phép:
- Class test bình thường có quyền truy cập package-private.
- Method `@Test` có quyền truy cập package-private, trả về `void`.
- Test tham số hóa qua `@ParameterizedTest` và nguồn dữ liệu phù hợp.
- Nested test class với `@Nested` khi dùng đúng cấu trúc (thường là inner class không `static`).
- Dynamic test thông qua `@TestFactory`, với quy tắc return type riêng.

Những lỗi phổ biến:
- Quên `@Test` hoặc import annotation từ JUnit 4 khi chỉ có Jupiter Engine.
- Đặt method test `private` hoặc viết sai chữ ký.
- Dùng `@ParameterizedTest` nhưng không cung cấp nguồn arguments hợp lệ.
- Đặt nested class không đúng annotation/cấu trúc hoặc chỉ chạy nested class bằng pattern không phù hợp.
- Test nằm trong source set khác nhưng task `test` không được gán classpath của source set ấy.

Test method được nhận diện không có nghĩa mọi logic assertion đúng; vẫn phải xem pass/fail và kiểm tra bằng hành vi thật.

## 9. Lọc theo class hoặc method: Gradle và Maven

### 9.1. Gradle `--tests`

Chạy riêng toàn bộ class:

```bash
./gradlew test --tests 'com.example.testing.MathPolicyTest'
```

Chạy riêng một method:

```bash
./gradlew test --tests 'com.example.testing.MathPolicyTest.addsTwoNumbers'
```

Mẫu ngắn khi biết đúng class:

```bash
./gradlew test --tests '*MathPolicyTest'
```

Dấu nháy bảo vệ ký tự `*` khỏi shell globbing ở những shell có hỗ trợ. Nếu filter không khớp test nào, Gradle thường báo **No tests found for given includes** và task có thể thất bại theo chính sách filter mặc định. Không tắt cảnh báo chỉ để pipeline xanh; xác nhận tên fully qualified class/method và project đang chạy.

Nếu bộ test đã có `@Disabled`, filter chọn đúng method đó vẫn không buộc nó chạy. `--tests` chọn test descriptors, không vô hiệu hóa annotation điều kiện của Jupiter.

### 9.2. Maven Surefire `-Dtest`

Chạy riêng class:

```bash
./mvnw -Dtest=MathPolicyTest test
```

Chạy riêng method:

```bash
./mvnw '-Dtest=MathPolicyTest#addsTwoNumbers' test
```

Với Maven, `-Dtest` là **Surefire test selection property**. Maven Surefire thường báo lỗi nếu một yêu cầu `-Dtest` cụ thể không khớp test nào (tùy phiên bản và `failIfNoSpecifiedTests`), kể cả khi một lần chạy `mvn test` không có test có thể trả về thành công. Đừng lẫn chính sách **không có test nói chung** với **không có test khớp selector tường minh**.

Trên Windows PowerShell, dùng `.\mvnw.cmd`. Những tên method/class có ký tự đặc biệt nên đặt trong dấu nháy phù hợp với shell. Đừng dùng `-DskipTests` khi muốn xác minh discovery: nó bỏ qua thực thi test.

### 9.3. Chạy đúng subproject/module

Trong Gradle multi-project, test có thể nằm trong module `:billing-service`:

```bash
./gradlew :billing-service:test --tests 'com.example.billing.BillingServiceTest'
```

Trong Maven multi-module, có thể chọn module bằng `-pl` và build dependency module cần thiết bằng `-am`:

```bash
./mvnw -pl billing-service -am test
```

Những tên module ở trên chỉ là ví dụ. Chạy `test` tại sai module hoặc module aggregate không chứa test có thể khiến bạn kết luận nhầm rằng Platform không phát hiện test.

## 10. Lọc bằng `@Tag` và `TestEngine`

### 10.1. Tag trong mã test

Ở bộ ví dụ, `@Tag("smoke")` đánh dấu `addsTwoNumbers`, `@Tag("fast")` đánh dấu hai invocation của `addsSeveralCases`, và `@Tag("validation")` đánh dấu phép thử chia cho 0.

**Gradle Groovy DSL** chỉ chạy tag `smoke`:

```groovy
tasks.named('test') {
    useJUnitPlatform {
        includeTags 'smoke'
    }
}
```

Với bộ ví dụ, khi bật filter này, **chỉ một test `addsTwoNumbers`** được chọn và chạy. Đây là đoạn **thay thế khối cấu hình `test` hiện có**, không nên tạo nhiều khối với filter mâu thuẫn. Khi bỏ bộ lọc, cả bộ test quay về số liệu 5 cases, 1 skipped. Để bỏ tag khỏi tập chạy:

```groovy
tasks.named('test') {
    useJUnitPlatform {
        excludeTags 'slow'
    }
}
```

Với **Gradle Kotlin DSL**:

```kotlin
tasks.test {
    useJUnitPlatform {
        includeTags("smoke")
    }
}
```

**Maven Surefire** lọc tag Jupiter qua tham số `groups`, ví dụ:

```bash
./mvnw -Dgroups=smoke test
```

Hoặc cấu hình plugin nếu một module luôn có chính sách test cố định:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <groups>smoke</groups>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đoạn POM là một **khối `<build>` minh họa**; trong POM đầy đủ mục 4, hãy thêm `maven-surefire-plugin` vào `<plugins>` đã có, không tạo `<build>` thứ hai. Parent Spring Boot quản lý version plugin trong cấu hình ví dụ. `groups`/`excludedGroups` có thể dùng tag expression tùy phiên bản Surefire, nhưng không cần ép mọi bộ test vào một tag duy nhất.

**Tác động của nhiều bộ lọc:** nếu đồng thời chọn `--tests MathPolicyTest.dividingByZeroThrows` (tag validation) và `includeTags 'smoke'`, giao của hai bộ lọc có thể rỗng. Đây là filter xung đột, không phải thiếu JUnit Engine.

### 10.2. Lọc engine

Nếu classpath có cả Jupiter và Vintage, Gradle có thể giới hạn engine:

```groovy
tasks.named('test') {
    useJUnitPlatform {
        includeEngines 'junit-jupiter'
    }
}
```

Điều này chỉ chọn test được Jupiter Engine nhận, không tự chuyển test JUnit 4 sang Jupiter. Muốn chạy test JUnit 4 qua Platform thì phải có **Vintage Engine** và dependency JUnit 4 thích hợp; khi đã chuyển đổi xong, có thể loại Vintage để tránh các test cũ vô tình được thực thi theo cách không còn mong muốn.

**Lưu ý:** engine filter, tag filter, class/method filter và `@Disabled` xử lý ở những tầng khác nhau. Kiểm tra riêng từng tầng khi test “biến mất”.

## 11. `@Disabled`, assumptions và “skipped” khác “failed”

Bốn trạng thái rất cần phân biệt:

| Trạng thái | Ý nghĩa | Hành động thích hợp |
| --- | --- | --- |
| **Passed** | Test thực thi và không có assertion/exception thất bại | Ghi nhận nhưng vẫn xem coverage và tính phù hợp của assertion |
| **Failed/Error** | Assertion sai hoặc exception không mong muốn, lỗi setup/engine... | Xem stack trace và sửa nguyên nhân |
| **Skipped/Disabled** | Test được chọn nhưng không chạy body hoặc bị abort theo điều kiện | Kiểm tra `@Disabled`, `@EnabledOnOs`, assumptions và lý do |
| **Not discovered** | Test không nằm trong tập được runner/engine nhìn thấy | Kiểm tra source set, file pattern, engine và selector |

`@Disabled("lý do")` loại test khỏi việc chạy; lý do có thể hiện trong report. Assumption như `Assumptions.assumeTrue(...)` có thể làm test **aborted** ở runtime, và reporter thường xếp vào skipped; nó khác với assertion failure.

Ví dụ **độc lập ở mức một test method** (cần import JUnit Jupiter):

```java
@Test
void requiresUnix() {
    org.junit.jupiter.api.Assumptions.assumeTrue(
            System.getProperty("os.name").toLowerCase().contains("linux")
    );
    org.junit.jupiter.api.Assertions.assertTrue(true);
}
```

Đây là **đoạn method minh họa để đặt bên trong một test class hợp lệ**, không phải tệp Java có thể compile độc lập. Nó không nên được copy nguyên vào bộ ví dụ ở mục 5 nếu bạn muốn giữ số liệu 5 cases. Trên non-Linux, test có thể abort; khi đó report sẽ phản ánh skipped/aborted tương ứng.

Một bộ test chỉ toàn skipped có thể cho build xanh nhưng **không xác nhận hành vi nghiệp vụ**. Khi kiểm tra CI, theo dõi cả số test thành công và số test bị skip; đừng dùng `@Disabled` để che lỗi thường trực.

## 12. Đọc báo cáo một cách có chứng cứ

### 12.1. Gradle XML và HTML report

Gradle thường tạo:

```text
build/test-results/test/TEST-com.example.testing.MathPolicyTest.xml
build/reports/tests/test/index.html
```

Trong XML dạng JUnit, thuộc tính `tests`, `failures`, `errors`, `skipped` cho biết thống kê; mỗi `<testcase>` đại diện một ca cụ thể. Tên hiển thị của parameterized invocations có thể chứa giá trị argument, nên đừng giả định chỉ có một ca vì trong Java chỉ có một method `@ParameterizedTest`.

Khi cần thấy test nào đã chạy trong console, Gradle Groovy DSL có thể bật logging:

```groovy
tasks.named('test') {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat = 'full'
    }
}
```

Đây là **cấu hình thay thế/ghép vào task `test` hiện có**. Không cần in mọi `System.out` trong CI nếu dữ liệu log có thể nhiều hoặc nhạy cảm. Khi đổi `testLogging`, nó ảnh hưởng hiển thị, không thay đổi discovery của JUnit.

### 12.2. Maven Surefire reports

Surefire thường tạo:

```text
target/surefire-reports/TEST-com.example.testing.MathPolicyTest.xml
target/surefire-reports/com.example.testing.MathPolicyTest.txt
```

Có thể đọc summary trên console hoặc XML. Đối với bộ ví dụ không có filter, kỳ vọng tổng **5**, skipped **1**, failures/errors **0**. Nếu thấy `Tests run: 0`, đừng vội kết luận test pass: cần truy nguồn vì sao test không được chọn.

Một bản báo cáo XML có thể phản ánh tên class, method, duration và skipped message. **Mã thoát của task và XML report đều quan trọng**: test failure thông thường khiến Gradle/Surefire trả exit code khác 0; nhưng nếu cấu hình `ignoreFailures`, `testFailureIgnore` hoặc `skipTests` thì build có thể được tiếp tục. Cần xem cả cách CI đánh giá fail/pass.

### 12.3. Một lần chạy filter chỉ phản ánh tập được chọn

Nếu chỉ chạy `smoke`, 1 passed là **đúng cho tập smoke**, không có nghĩa ba test khác và một skipped đều đã được thực thi. Khi QA toàn bộ module, dùng một lần chạy không có filter hoặc thêm job riêng bao phủ đầy đủ tập test cần nghiệm thu.

## 13. Bảo đảm build không âm thầm bỏ qua toàn bộ bài kiểm thử

### 13.1. Gradle

Với source set có test hữu ích, Gradle có thể hoàn tất `test` nhưng có `NO-SOURCE` khi nguồn rỗng hoặc cấu hình testClassesDirs/classpath không đúng. Nếu chạy `--tests`, bộ lọc không khớp thường báo lỗi nhờ cơ chế `failOnNoMatchingTests` của filter.

Có thể cấu hình filter policy rõ ràng ở Gradle:

```groovy
tasks.named('test') {
    useJUnitPlatform()
    filter {
        failOnNoMatchingTests = true
    }
}
```

**Giới hạn:** `failOnNoMatchingTests` xử lý trường hợp **đã cấu hình selection filter nhưng không khớp**. Nó không tự khẳng định một project hoàn toàn không có test source thì phải fail. Với những module bắt buộc có test, hãy dùng kiểm tra riêng ở CI (chẳng hạn xác minh report XML tồn tại và test count lớn hơn 0), thay vì tin rằng mọi `test` task tự fail khi không có input.

Khi cần kiểm tra một ca cụ thể, lệnh `--tests 'com.example.testing.MathPolicyTest.addsTwoNumbers'` là một **witness test**: nếu không được nhận diện, build phải báo thiếu test thay vì âm thầm thành công.

### 13.2. Maven

Đối với Maven Surefire, có thể yêu cầu fail khi không có test:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <failIfNoTests>true</failIfNoTests>
    </configuration>
</plugin>
```

Ghép vào `<build><plugins>` của POM; khi dùng Spring Boot parent, version Surefire được quản lý. `failIfNoTests` xử lý **không có test nào để chạy**. `failIfNoSpecifiedTests` là tham số khác, liên quan trường hợp người dùng **chỉ định `-Dtest=...` mà không khớp**.

Hai tùy chọn dễ gây nhầm:
- `-DskipTests`: bỏ chạy test; thông thường test source vẫn được biên dịch.
- `-Dmaven.test.skip=true`: bỏ cả test compile và test execution ở các plugin tuân thủ tham số này.

Không dùng các tùy chọn skip khi mục tiêu là xác minh chất lượng build. Trong CI, nên **đảm bảo reports được lưu** và có kiểm tra kỳ vọng tối thiểu về số test trong những module bắt buộc có test; policy skip/zero phải được giải thích rõ.

## 14. Những ca “IDE chạy được nhưng Maven/Gradle không tìm thấy”

| Triệu chứng | Nguyên nhân có khả năng | Hướng xử lý |
| --- | --- | --- |
| IDE chạy `MathPolicyTest` được, Maven báo 0 tests | Tên class không khớp Surefire default includes, hoặc profile/plugin khác | Đổi thành `*Test`/`*Tests` hoặc khai báo `<includes>` tường minh |
| `@Test` biên dịch nhưng Gradle không chạy Jupiter | Quên `useJUnitPlatform()` ở task `test` | Cấu hình Platform và kiểm tra engine classpath |
| Lỗi không có JUnit TestEngine | `junit-jupiter-engine`/runtime dependency thiếu hoặc version không tương thích | Kiểm tra `testRuntimeClasspath` và dependency tree |
| Import `org.junit.Test` và kỳ vọng Jupiter chạy | Đang dùng JUnit 4, thiếu Vintage Engine | Chuyển sang Jupiter API hoặc bổ sung Vintage có chủ đích |
| Test method `private`, sai chữ ký hoặc không được annotate | Jupiter không nhận nó là test hợp lệ | Dùng package-private method trả về `void`, `@Test` đúng package |
| `@ParameterizedTest` chạy 0 hoặc báo lỗi nguồn arguments | Không có provider hợp lệ hoặc dữ liệu nguồn rỗng/sai kiểu | Kiểm tra `@CsvSource`, `@ValueSource`, converter và report |
| Chỉ chạy test tag `smoke` nhưng không thấy `validation` | Bộ lọc tag loại test đó | Bỏ/chỉnh includeTags, `-Dgroups`, xem report |
| Test hiện skipped | `@Disabled`, điều kiện OS, assumption | Xem skipped reason và hoàn thiện test cần chạy |
| Gradle `:test NO-SOURCE` | Test đặt nhầm folder hoặc source set trống | Kiểm tra `src/test/java` và custom test task |
| Gradle báo `UP-TO-DATE` dù vừa nhìn test file | Kết quả task được tái sử dụng | Kiểm tra report hiện có, dùng `--rerun-tasks` khi cần |
| Maven test không chạy `*IT` | Surefire mặc định thường dùng pattern unit test, Failsafe khác | Cấu hình Maven Failsafe trong phase `integration-test`/`verify` |
| Chạy `test` từ root không thấy test module mong muốn | Đang chạy sai Gradle project hoặc Maven module | Gọi đúng `:module:test` hoặc `-pl module` |
| CI xanh nhưng không thấy XML test | Task không chạy, skip flag, cấu hình report khác hoặc thiếu input | Xem task graph/log, report directories và câu lệnh CI |
| Có Jupiter và Vintage nhưng kết quả khác dự kiến | Test engines và engine filters khác nhau | Liệt kê engines trên test runtime classpath, xem include/excludeEngines |
| Test pass local nhưng fail CI | JDK/time zone/locale/env var/DB/port/test order khác | Cố định môi trường và test isolation; không tùy tiện skip |

Nếu một test thật sự không được phát hiện, **hãy xác định tầng mất dấu đầu tiên**: file nguồn → class file → runtime classpath → engine → selector/filter → report. Quy trình này tiết kiệm thời gian hơn việc sửa annotation hoặc đổi plugin version ngẫu nhiên.

## 15. Kiểm tra các dependency test và build configuration

### 15.1. Gradle

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter-engine --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-platform-launcher --configuration testRuntimeClasspath
```

Các lệnh này giúp biết phiên bản **đã resolve** và đường dependency đưa JUnit Engine/Launcher vào test runtime. Maven hoặc Gradle có thể chọn version khác phiên bản bạn tưởng đã khai báo nếu có BOM, constraints hay overrides.

### 15.2. Maven

```bash
./mvnw dependency:tree
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
```

Tìm `org.junit.jupiter`, `org.junit.platform` trong dependency tree và `maven-surefire-plugin` trong effective POM. Với Maven corporate parent hoặc BOM import, đảm bảo version Surefire có support Platform. Nếu có override version JUnit/Surefire, kiểm tra tương thích và test lại; tránh ghim một artifact độc lập mà bỏ qua tập version do Spring Boot quản lý.

### 15.3. Spring Boot test và thuần JUnit khác nhau khi nào?

`@Test` và assertions của Jupiter **không cần khởi động Spring context**. Ví dụ `MathPolicyTest` nhanh và độc lập.

`@SpringBootTest` thường cần khi muốn kiểm tra cả `ApplicationContext`, DI, configuration hoặc web stack. Dùng nó có thể chậm hơn và có thêm điều kiện môi trường. **`@SpringBootTest` không phải điều kiện để JUnit Platform nhận diện một `@Test`**. Ngược lại, khi dùng `@SpringBootTest` với Jupiter, Spring Test hỗ trợ extension để tích hợp context; dependency `spring-boot-starter-test` thường cung cấp phần này.

Chạy test thuần trước để kiểm tra **discovery**, rồi mới thêm test Spring context phù hợp mục tiêu nghiệp vụ. Không trộn lỗi thiếu datasource, broker hay service bên ngoài với lỗi JUnit Engine không phát hiện test.

## 16. Pipeline kiểm tra bản dựng đáng tin cậy

Một quy trình kiểm tra phù hợp với module Spring Boot có thể đi theo thứ tự:

1. Xác định **module/test source set** và naming convention của bộ test.
2. Kiểm tra **JDK, Gradle/Maven, Spring Boot và JUnit** theo một tập phiên bản tương thích.
3. Đảm bảo **Jupiter API, Engine, Launcher/provider** được cung cấp bởi test dependencies và cấu hình build.
4. Chạy **một test witness theo tên class/method**, để kiểm chứng selector.
5. Chạy **toàn bộ test task không có filter**, xác nhận số tests discovered/executed/skipped trong report.
6. Nếu có tag policy, chạy thêm các tập như `smoke`/`fast` riêng và ghi rõ phạm vi mỗi tập.
7. Chạy `check`/`build` (Gradle) hoặc `verify` (Maven) theo vòng đời cần thiết.
8. Thu thập XML/HTML reports làm artifact CI, giữ mã thoát khác 0 khi có test thất bại.
9. Khi thêm test mới, xác nhận số test đã thực thi tăng theo kỳ vọng hoặc có lý do hợp lệ (parameterized test, disabled, nested).
10. Với module bắt buộc có test, kiểm tra **test count > 0** trong báo cáo; không coi `BUILD SUCCESS` là đủ.

Lệnh tổng quát:

```bash
# Gradle:
./gradlew clean test
./gradlew check
./gradlew build

# Maven:
./mvnw clean test
./mvnw verify
```

Trong CI, thường không cần gọi trùng cả ba lệnh Gradle trên cho một pipeline: `build` theo Java plugin đã phụ thuộc `check`, và `check` chạy `test` theo cấu hình mặc định. Có thể chọn **một lệnh phù hợp** rồi thu thập report; khi cần debug thêm, chạy riêng `test` với log rõ hơn.

### Checklist cuối bài

- [ ] Test ở `src/test/java`, tên lớp và package đúng convention của build tool.
- [ ] Test import `org.junit.jupiter.api.Test`; class/method hợp lệ với Jupiter.
- [ ] Gradle `test` dùng `useJUnitPlatform()`; Maven Surefire có hỗ trợ Platform.
- [ ] Có Jupiter Engine (và Launcher khi cần) trên **test runtime classpath**.
- [ ] `@ParameterizedTest` có nguồn arguments hợp lệ; biết một method có thể tạo nhiều test cases.
- [ ] Đã kiểm tra `--tests` hoặc `-Dtest` cho ít nhất một method xác định.
- [ ] Report nêu đúng **tests/failed/errors/skipped** và không vô tình chạy 0 tests.
- [ ] Đã kiểm tra tag/engine filter, `@Disabled`, assumptions và skip flags trong CI.
- [ ] Đã phân biệt JUnit unit test với Spring context integration test.
- [ ] Mỗi lần sửa build logic, chạy lại test và xác minh báo cáo từ artifact/CI thật.

**Ghi nhớ:** Để tin rằng bản dựng đã được kiểm thử, cần chứng minh chuỗi **đúng test source → compile → đúng JUnit Platform/Engine → đúng discovery và filters → có executions → có report và exit code đáng tin**. Chỉ thấy `@Test` trong source hoặc dòng `BUILD SUCCESSFUL` chưa đủ.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/index.html)
- [JUnit 5 User Guide — Test Classes and Methods / Running Tests](https://docs.junit.org/5.12.1/user-guide/index.html)
- [Gradle — Testing in Java and JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — useJUnitPlatform](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.tasks.testing/-test/use-j-unit-platform.html)
- [Maven Surefire — Using JUnit Platform](https://maven.apache.org/components/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Maven Surefire — Inclusion and Exclusion Patterns](https://maven.apache.org/surefire-archives/surefire-3.2.5/maven-surefire-plugin/examples/inclusion-exclusion.html)