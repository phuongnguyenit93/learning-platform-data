# JUnit 5 và JUnit 6: tương thích với dòng Spring Boot đang sử dụng

## 1. Vấn đề: JUnit nào nên dùng cho dự án Spring Boot hiện tại?

Trong module **Spring Boot - testing**, nhóm **Phiên bản và chuyển đổi**, một dự án Spring Boot có thể đã viết hàng trăm bài test với `org.junit.jupiter.api.Test`, `@SpringBootTest`, Mockito, AssertJ, parameterized tests và JUnit Platform. Khi nhìn thấy JUnit 6 được phát hành, đội phát triển thường hỏi:

- Ứng dụng đang dùng **Spring Boot 3.5** có cần lập tức nâng `junit-jupiter` lên `6.x` không?
- **Spring Boot 4.1** đã cung cấp JUnit 6 chưa? JUnit Platform 1.x có đi với Jupiter 6.x được không?
- Chuyển JUnit 5 → JUnit 6 có phải sửa imports `org.junit.jupiter.*` thành package khác?
- Một test viết theo JUnit 4 có tự chạy khi thêm `spring-boot-starter-test` không?
- Nếu Gradle/Maven báo `No tests found`, `TestEngine` không tìm thấy, `NoSuchMethodError` hoặc context khởi động lỗi, đâu là nguyên nhân?
- Làm thế nào xác minh **resolved dependency tree thực tế** thay vì đoán từ blog, IDE hay version khai báo trong một file?

**Quy tắc thực tế:** mặc định **để Spring Boot BOM/parent quản lý cả bộ phiên bản JUnit**, dùng `spring-boot-starter-test` và khai báo JUnit Platform launcher đúng scope. Không nâng riêng Jupiter lên một major mới trong ứng dụng Boot cũ mà không kiểm tương thích của toàn bộ test stack.

Tại thời điểm đối chiếu tài liệu chính thức **08/11/2026**, hai mốc ổn định để minh họa là **Spring Boot 3.5.16** và **Spring Boot 4.1.2**. Bài cung cấp ma trận chính xác cho chúng, giải thích những thay đổi có thật của JUnit 6, hai `build.gradle` thay thế nhau, một bộ Java 17/JUnit/Spring/Mockito có thể dùng chung, Maven tương đương, lệnh phân tích dependency và kế hoạch chuyển đổi CI. **Không nhầm kết quả kiểm tra cấu trúc/mã trong tài liệu với việc đã chạy Gradle/JUnit thực tế.**

## 2. Ma trận đã xác minh từ Spring Boot managed dependency coordinates

| Dòng Spring Boot / bản minh họa | Spring Framework | JUnit Jupiter | JUnit Platform | Java tối thiểu | Hướng dùng |
| --- | --- | --- | --- | --- | --- |
| **Spring Boot 3.4.13** | Spring Framework 6.2 | **5.11.4** | **1.11.4** | **17** | Giữ JUnit 5 do Boot BOM quản lý |
| **Spring Boot 3.5.16** | Spring Framework 6.2 | **5.12.2** | **1.12.2** | **17** | Giữ JUnit 5; đây là mẫu A |
| **Spring Boot 4.0.x (theo BOM 4.0)** | Spring Framework 7 | **6.0.3** trong BOM 4.0 được tra cứu | **6.0.3** | **17** | JUnit 6 theo Boot BOM; rà soát test starter/Boot APIs |
| **Spring Boot 4.1.2** | Spring Framework 7.0 | **6.0.3** | **6.0.3** | **17** | JUnit 6; đây là mẫu B |

Các version ở bảng là **managed defaults của BOM được tham chiếu**, không tuyên bố mọi patch release trong cùng dòng phải giữ chính xác mã version đó. Ví dụ JUnit 5 đã có các bản 5.14.x, nhưng **Boot 3.5.16 quản lý 5.12.2**; một thư viện có release mới hơn không làm dependency của Boot tự thay đổi.

**Quan trọng về đặt tên:** trên JUnit 5, `Jupiter 5.12.2` đi cùng **Platform 1.12.2**, không phải Platform 5.12.2. Từ **JUnit 6**, các artifact của Platform, Jupiter và Vintage thống nhất **cùng version 6.0.3** trong BOM minh họa. Không mix `org.junit.jupiter:junit-jupiter:6.0.3` với `org.junit.platform:junit-platform-launcher:1.12.2`.

Spring Boot 4.1.2 hỗ trợ Gradle **8.14+ trong dòng 8** hoặc **Gradle 9.x** và Maven **3.6.3+**; Spring Boot 3.5.16 hỗ trợ Gradle **7.6.4+ trong dòng 7** hoặc **8.4+ trong dòng 8** và Maven **3.6.3+**. Cả hai đòi Java 17+. Ví dụ chọn **Gradle 8.14.3 + JDK 17** vì nằm trong phần giao nhau của hai ma trận được hỗ trợ.

### Cảnh báo về dòng 3.x và 4.x

- Đừng suy rằng **cứ Spring Boot 3** là có thể cập nhật độc lập Jupiter sang 6 và vẫn có cấu hình được hỗ trợ.
- Đừng suy rằng **cứ Spring Boot 4** thì application code và Spring test-slice imports từ Boot 3 vẫn giữ nguyên: Boot 4 có **modular test starters** và các API Spring Boot bị xóa/đổi.
- Đừng lấy JUnit 6 đã hỗ trợ Java 17 làm bằng chứng Boot 2.x chạy được trên Java 17/JUnit 6: phải đối chiếu cả Boot/Framework/launcher/plugin.
- Đừng lấy IDE “chạy được một test” làm bằng chứng CI với Maven/Gradle và toàn bộ test engines tương thích.

## 3. JUnit là ba thành phần, không chỉ một dependency

JUnit hiện đại có ba subprojects:

~~~text
                     Test code
          @Test / @ParameterizedTest
                     |
                     v
              JUnit Jupiter API
                     |
                     v
              JUnit Jupiter Engine
                     |
                     v
               JUnit Platform
          Launcher / TestEngine SPI
                     |
                     v
              Gradle / Maven / IDE
~~~

| Thành phần | Tên artifact điển hình | Vai trò |
| --- | --- | --- |
| Jupiter API | `org.junit.jupiter:junit-jupiter-api` | Annotations, assertions, extension APIs |
| Jupiter Engine | `org.junit.jupiter:junit-jupiter-engine` | Phát hiện và chạy tests viết theo Jupiter |
| Jupiter aggregate | `org.junit.jupiter:junit-jupiter` | Dependency tiện lợi để có API/engine/params đúng phiên bản |
| Jupiter Params | `org.junit.jupiter:junit-jupiter-params` | `@ParameterizedTest`, `@CsvSource` và nguồn tham số |
| Platform Launcher | `org.junit.platform:junit-platform-launcher` | API để Gradle/Maven/IDE launch TestEngines |
| Platform Commons/Engine | `org.junit.platform:junit-platform-commons/engine` | Các API/hạ tầng dùng chung |
| Vintage Engine | `org.junit.vintage:junit-vintage-engine` | Chạy test JUnit 3/4 cũ qua Platform; **deprecated trong JUnit 6** |
| Spring Test | `org.springframework:spring-test` | `SpringExtension`, TestContext, mocks/integration |
| Spring Boot Test | `spring-boot-starter-test` và các test modules | Boot bootstrap, test facilities + managed JUnit/Mockito/AssertJ |

`spring-boot-starter-test` giúp không phải tự lắp từng artifact JUnit Jupiter, AssertJ và Mockito; nhưng nó không thay trách nhiệm kiểm **launcher trên test runtime** hoặc compatibility của một custom testing plugin.

**JUnit 5 = Platform 1.x + Jupiter 5.x + Vintage 5.x. JUnit 6 = Platform 6.x + Jupiter 6.x + Vintage 6.x.** Đây là một **thay đổi version scheme có thật**, không phải lỗi tài liệu.

## 4. Những gì không đổi khi từ JUnit 5 lên JUnit 6

JUnit 6 được thiết kế để đa số source code Jupiter hiện có có thể tiếp tục biên dịch. Các imports cốt lõi **không đổi**:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.api.extension.ExtendWith;
~~~

**Giữ nguyên** `@Test`, `@BeforeEach`, `@AfterEach`, `@ParameterizedTest`, `@CsvSource`, `@TempDir`, `@Nested`, `assertEquals`, `assertThrows`, `assertAll`, `MockitoExtension`, `SpringExtension` (nếu dependencies đi kèm tương thích). Không có package `org.junit6.*`.

Điều này không có nghĩa mọi custom extension/build plugin đều tương thích binary ngay lập tức. **JUnit API công khai** được duy trì rộng rãi, nhưng các APIs deprecated lâu năm đã bị xóa, baseline Java/Kotlin tăng và JSpecify nullability có thể ảnh hưởng static analysis/Kotlin compilation.

### JUnit 5 → 6 khác JUnit 4 → 5

Nâng `JUnit 5 Jupiter` lên `JUnit 6 Jupiter` **không** yêu cầu viết lại mọi tests sang annotation mới. Ngược lại, chuyển từ `JUnit 4` sang `JUnit Jupiter` là thay đổi programming model lớn: `@RunWith`, `@Before`/`@After`, `@Rule`, `@Test(expected=...)` và JUnit 4 runner/parameterization cần migration. Đừng gọi hai bài toán này là cùng một bước.

## 5. Những thay đổi JUnit 6 thực sự cần rà soát

Theo JUnit 6.0 migration/release notes:

| Chủ đề | JUnit 5 | JUnit 6 | Hành động |
| --- | --- | --- | --- |
| Java runtime baseline | Java 8+ cho JUnit 5 | **Java 17+** | Nâng test JVM, Gradle/Maven/CI JDK khi cần |
| Version number của Platform | **1.x** | **6.x** (thống nhất Jupiter/Vintage) | Align cả Platform, engine, launcher |
| `MethodOrderer.Alphanumeric` | Deprecated | **Đã bị xóa** | Dùng `MethodOrderer.MethodName` hoặc `OrderAnnotation` theo semantics thực |
| `InvocationInterceptor.interceptDynamicTest(Invocation, ExtensionContext)` | API cũ đã deprecated | **Đã bị xóa** | Cập nhật custom JUnit extension |
| `junit.jupiter.tempdir.scope` property | Đã deprecated | **Không còn được hỗ trợ** | Dùng lifecycle/`@TempDir` đúng API |
| `@CsvFileSource(lineSeparator=...)` | Deprecated option | **Đã bị xóa** | Để JUnit tự nhận `\r`/`\n`/`\r\n` |
| `junit-platform-runner` | Module legacy cho JUnit 4 runner | **Đã bị loại bỏ** | Dùng Platform launcher/engines, migrate runner |
| `junit-platform-jfr` | Module riêng | **Đã bị loại bỏ**; chức năng JFR chuyển vào launcher | Bỏ dependency cũ, dùng launcher |
| Vintage Engine | Có | **Deprecated** | Chỉ dùng tạm nếu còn JUnit 4 tests |
| Kotlin metadata/nullability | Baseline cũ | Baseline Kotlin tăng, JSpecify nullability | Kiểm Kotlin/IDE/static checker |
| Test annotation package | `org.junit.jupiter` | **Vẫn `org.junit.jupiter`** | Không mass-rename imports |
| Maven Surefire/Failsafe | Phụ thuộc bản đang dùng | **JUnit 6 yêu cầu >=3.0.0** | Nâng test plugins tương ứng |

**Không được sửa tự động mọi `@CsvSource` hoặc `@ParameterizedTest` như thể chúng bị xóa.** Chỉ các APIs thực sự removed/deprecated mới cần code migration. Với `@CsvFileSource`, parser behavior và thông điệp lỗi malformed CSV có thể thay đổi, nhưng basic valid inputs vẫn được hỗ trợ.

JUnit 6.0.x đưa JSpecify annotations để mô tả nullability trong APIs; một số strict null-checkers có thể cảnh báo khác. Điều đó không đồng nghĩa Java code bình thường phải đổi tất cả parameters thành `@Nullable`.

## 6. Nên chọn JUnit nào? Một bảng quyết định nhanh

| Tình huống thực tế | Quyết định ưu tiên |
| --- | --- |
| Đang dùng Spring Boot 3.4/3.5, tests ổn định | Giữ JUnit 5 do Boot BOM quản lý; xử lý dependencies alignment |
| Đang ở Boot 3.5, muốn nâng riêng JUnit 6 vì bản mới | **Không mặc định**; đánh giá đầy đủ Spring Test, build tool và mọi test engines; ưu tiên lên Boot 4 ở migration riêng |
| Nâng ứng dụng lên Boot 4.1.2 | Sử dụng JUnit 6.0.3 managed bởi Boot, **không cần ép JUnit 6 thủ công** |
| Java runtime còn dưới 17 | Không thể chạy JUnit 6; upgrade JDK trước |
| Có JUnit 4 tests còn phải chạy | Thêm JUnit 4 + Vintage engine đúng major do Boot quản lý, dùng tạm; lập kế hoạch migrate Jupiter |
| Dự án framework/library không dùng Boot BOM | Dùng **JUnit BOM** cùng version cho Jupiter, Platform, Vintage |
| IDE chạy nhưng Gradle test 0 tests | Kiểm launcher, TestEngine, Test task, source set và filters |
| Boot 4 API test không compile | Kiểm Spring Boot 4 test modularization/import removals, **đừng mặc định đổ cho JUnit 6** |
| Mockito integration trên Spring Boot 4 | Dùng `@MockitoBean`/`@MockitoSpyBean`, MockitoExtension; `@MockBean`/`@SpyBean` đã bị xóa |
| Maven có JUnit 6 nhưng Surefire 2.x | Nâng Surefire/Failsafe >=3.0.0, không chỉ đổi Jupiter version |

**Phiên bản nên coi là một tập:** Spring Boot plugin/parent, Spring Framework, JUnit Jupiter/Platform/Vintage, Mockito, AssertJ, JDK, Gradle/Maven và IDE engine support.

## 7. Build Gradle A — Spring Boot 3.5.16 dùng JUnit 5 do Boot quản lý

Đây là **`build.gradle` hoàn chỉnh** cho phương án A, Groovy DSL, JDK 17, Gradle Wrapper 8.14.3:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    testLogging {
        events 'failed', 'skipped'
    }
}
~~~

**Kết quả dependency dự kiến từ Spring Boot 3.5.16 BOM:** Jupiter **5.12.2**, Platform launcher **1.12.2**. Không ghi version sau `spring-boot-starter-test`, `junit-platform-launcher` hoặc từng JUnit artifact. Spring Boot dependency management tự chọn phiên bản đã kiểm.

### Vì sao khai báo launcher tường minh?

`spring-boot-starter-test` đem tới Jupiter API/engine cùng các test libraries. `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` bảo đảm launcher xuất hiện ở test runtime với **version thuộc BOM**. JUnit/Gradle docs khuyến nghị dependency rõ ràng, đặc biệt khi nâng Gradle/IDE. Nếu dự án có launcher qua dependency transitive khác, khai báo tường minh vẫn giúp dễ audit.

### Đừng tự ép Jupiter 6 trong phương án A

Đây là **anti-pattern**, không phải config chạy được:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:6.0.3'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}
~~~

Nó phối hợp Jupiter 6 với Platform 1.12 không cùng release train, tạo nguy cơ linkage/discovery errors. Cũng đừng tưởng chỉ đặt `ext['junit-jupiter.version']='6.0.3'` trong Boot 3.5 tự thay `junit-platform.version` và mọi extension transitive: cần đánh giá BOM/version graph nếu có lý do bất thường để override.

## 8. Build Gradle B — Spring Boot 4.1.2 dùng JUnit 6 do Boot quản lý

Dùng **`build.gradle` hoàn chỉnh khác**, thay toàn bộ phương án A:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'io.spring.dependency-management' version '1.1.7'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    testLogging {
        events 'failed', 'skipped'
    }
}
~~~

**Kết quả dependency dự kiến từ Spring Boot 4.1.2 BOM:** Jupiter **6.0.3**, Platform launcher **6.0.3**. JUnit 6 có Java 17 baseline, phù hợp toolchain này. Spring Boot 4.1 sử dụng Spring Framework 7.0; khác biệt APIs/auto-configuration ngoài JUnit là một phần migration riêng cần rà soát.

Hai Gradle scripts dùng **một bộ Java/JUnit tests chung** ở các mục sau. Không copy cả hai `plugins` blocks vào cùng file và không override JUnit version cho “cập nhật hơn BOM” khi chưa có nhu cầu/tương thích đã xác minh.

**Lưu ý Boot 4 modularization:** core `spring-boot-starter-test` vẫn tồn tại và có Jupiter/Mockito/AssertJ; nhưng với web/JPA/security/GraphQL cụ thể, Spring Boot 4 đưa thêm **`spring-boot-starter-<technology>-test`**. Một `@WebMvcTest` từ Boot 3 có thể cần starter WebMVC test riêng trên Boot 4; ví dụ này cố tình chỉ dùng core `@SpringBootTest` để giữ chung nguồn giữa hai builds.

## 9. Gradle Wrapper, Java toolchain và lệnh thiết lập

**`settings.gradle`:**

~~~groovy
rootProject.name = 'junit-boot-compatibility-demo'
~~~

Với Gradle đã cài trên máy để tạo wrapper:

~~~bash
gradle wrapper --gradle-version 8.14.3 --distribution-type bin
./gradlew --version
java -version
~~~

Trên Windows:

~~~powershell
gradle wrapper --gradle-version 8.14.3 --distribution-type bin
.\gradlew.bat --version
java -version
~~~

Sau khi tạo, commit `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` và `gradle/wrapper/gradle-wrapper.properties`. Tránh dùng system Gradle trên CI vì có thể lệch version giữa dev và CI. Nên pin trusted Gradle distribution/checksum theo chính sách tổ chức.

**Ba Java có thể khác nhau:** JDK chạy Gradle daemon, toolchain dùng compile Java, và runtime JVM của Test tasks. `java.toolchain` giúp Gradle chọn JDK build/test tương thích, nhưng nếu Gradle daemon chạy trên JDK không được Gradle hỗ trợ thì build vẫn fail trước khi dùng toolchain. Chạy `./gradlew --version` xác nhận JVM của Gradle, và `./gradlew test --info` để xem task execution.

Gradle 8.14.3 là lựa chọn nằm trong **vùng giao của Boot 3.5 và Boot 4.1**; với Gradle 9 chỉ nên dùng cùng Boot 4.1 chứ không tuyên bố Boot 3.5 support Gradle 9.

## 10. Cấu trúc project chung có thể chạy ở hai cấu hình

~~~text
settings.gradle
build.gradle              # chọn CHỈ A hoặc B
gradle/wrapper/...
gradlew
gradlew.bat

src/main/java/com/example/junitmatrix/
    JunitMatrixApplication.java
    GreetingService.java
    PriceCalculator.java
    RateGateway.java
    CurrencyConverter.java

src/main/resources/
    application.properties

src/test/java/com/example/junitmatrix/
    PriceCalculatorTest.java
    FileFixtureTest.java
    MockitoBoundaryTest.java
    SpringBootCompatibilityTest.java

src/test/resources/
    application-test.properties
~~~

**Chỉ bốn test classes.** Ba lớp là unit/Mockito/file tests không khởi động Spring, một lớp tích hợp khởi động Boot TestContext. Có **tám phương thức mang test annotation** (gồm một `@ParameterizedTest` chạy ba bộ dữ liệu); về logic dự kiến **mười test invocations**. Số hiển thị trong một báo cáo Gradle/IDE có thể có khác biệt về container/display grouping, vì thế khi QA cần xem XML/report thực tế. **Không đặt tên unit test trùng class production hoặc đặt một `@SpringBootApplication` mới trong `src/test`**.

Hai phương án Build A/B dùng **chính xác bộ sources** này, không cần H2/Docker/web server. Nhờ vậy nếu build một phương án fail, có thể tập trung vào JUnit/Spring/Mockito/Gradle compatibility thay vì ảnh hưởng database.

## 11. Spring Boot application và bean đơn giản

**`src/main/java/com/example/junitmatrix/JunitMatrixApplication.java`:**

~~~java
package com.example.junitmatrix;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JunitMatrixApplication {
    public static void main(String[] args) {
        SpringApplication.run(JunitMatrixApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/junitmatrix/GreetingService.java`:**

~~~java
package com.example.junitmatrix;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final String prefix;

    public GreetingService(
            @Value("${lesson.greeting:Hello}") String prefix
    ) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank"
            );
        }
        return prefix + ", " + name.strip() + "!";
    }

    public String prefix() {
        return prefix;
    }
}
~~~

**`src/main/resources/application.properties`:**

~~~properties
lesson.greeting=Hello
spring.main.banner-mode=off
~~~

Một `@SpringBootTest` ở cùng package `com.example.junitmatrix` sẽ tìm được `JunitMatrixApplication` qua cơ chế lookup của Spring Boot. Test bật profile `test` sẽ đọc `application-test.properties` ở test classpath, không đưa test-only property vào production JAR.

**`src/test/resources/application-test.properties`:**

~~~properties
lesson.greeting=Integration
~~~

Expected:
- Nếu khởi tạo thủ công `new GreetingService("Unit")`: `greet(" An ")` -> `Unit, An!`.
- Nếu Spring test với profile test: `GreetingService.prefix()` -> `Integration`, `greet(" An ")` -> `Integration, An!`.
- Nếu application bình thường không có profile test: prefix `Hello`.

Hai builds có Spring Framework khác nhau nhưng annotations Java/Spring trên được hỗ trợ ở cả các phiên bản minh họa.

## 12. Business logic thuần dùng JUnit Jupiter

**`src/main/java/com/example/junitmatrix/PriceCalculator.java`:**

~~~java
package com.example.junitmatrix;

public final class PriceCalculator {

    public long afterDiscount(
            long originalCents,
            int discountPercent
    ) {
        if (originalCents < 0
                || discountPercent < 0
                || discountPercent > 100) {
            throw new IllegalArgumentException(
                    "Invalid price or discount"
            );
        }

        // Nguyên mẫu chỉ dùng đơn vị cent và chia nguyên.
        long numerator = Math.multiplyExact(
                originalCents,
                100L - discountPercent
        );
        return numerator / 100L;
    }
}
~~~

Công thức dùng integer cents và **truncate phần cent lẻ**. `Math.multiplyExact` ném `ArithmeticException` nếu phép nhân tràn `long`; production tiền tệ nên dùng domain money type/BigDecimal với currency, rounding policy, overflow limits. Trong project demo số tiền nhỏ nên kết quả xác định.

Ví dụ:
- 1.000 cents giảm 10% -> 900.
- 500 cents giảm 20% -> 400.
- 199 cents giảm 10% -> floor(179,1 cents) = 179.
- Giảm 0% -> giữ nguyên tiền.
- Giảm 100% -> 0.

Test mã này không cần Spring context, Mockito hoặc database; không dùng `@SpringBootTest` để test một phép toán thuần.

## 13. PriceCalculatorTest: @Test, @ParameterizedTest, @CsvSource

**`src/test/java/com/example/junitmatrix/PriceCalculatorTest.java`:**

~~~java
package com.example.junitmatrix;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceCalculatorTest {

    private final PriceCalculator calculator =
            new PriceCalculator();

    @Test
    void calculatesTenPercentDiscount() {
        assertEquals(
                900L,
                calculator.afterDiscount(1_000L, 10)
        );
    }

    @ParameterizedTest
    @CsvSource({
        "1000, 10, 900",
        "500, 20, 400",
        "199, 10, 179"
    })
    void worksForParameterizedExamples(
            long original,
            int percent,
            long expected
    ) {
        assertEquals(
                expected,
                calculator.afterDiscount(original, percent)
        );
    }

    @Test
    void rejectsInvalidArguments() {
        assertAll(
            () -> assertThrows(
                    IllegalArgumentException.class,
                    () -> calculator.afterDiscount(-1L, 10)
            ),
            () -> assertThrows(
                    IllegalArgumentException.class,
                    () -> calculator.afterDiscount(100L, -1)
            ),
            () -> assertThrows(
                    IllegalArgumentException.class,
                    () -> calculator.afterDiscount(100L, 101)
            )
        );
    }
}
~~~

Đây là **ba test methods**: hai `@Test` và một `@ParameterizedTest` với **ba invocations**; tức **năm test invocations** theo logic JUnit Jupiter. Các imports/annotations trên **giữ nguyên** giữa JUnit Jupiter 5.12.2 và 6.0.3.

`@CsvSource` cần module `junit-jupiter-params` trên test classpath, đã có thông qua `spring-boot-starter-test`. Nếu Maven/Gradle báo `ParameterizedTest cannot be resolved`, trước tiên kiểm test dependencies có thật, không sửa annotation.

Trường hợp `199,10,179` kiểm quy ước truncate: 199 × 90 /100 = 179 dư 10. Nếu yêu cầu rounding khác, đổi domain logic và assertions, không coi đây là lỗi JUnit.

## 14. @TempDir: vẫn còn trong JUnit 6

**`src/test/java/com/example/junitmatrix/FileFixtureTest.java`:**

~~~java
package com.example.junitmatrix;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FileFixtureTest {

    @Test
    void createsUtf8FileInsideTempDirectory(
            @TempDir Path tempDir
    ) throws IOException {
        Path file = tempDir.resolve("customer.txt");
        String value = "Xin chào JUnit";

        Files.writeString(
                file,
                value,
                StandardCharsets.UTF_8
        );

        assertTrue(Files.exists(file));
        assertEquals(
                value,
                Files.readString(file, StandardCharsets.UTF_8)
        );
    }
}
~~~

Đây là **một `@Test` method**. JUnit quản lý temporary directory lifecycle; test không cần tạo/ghi một path cố định ở root project hay dùng `Thread.sleep`. **JUnit 6 không xóa annotation `@TempDir`.** Thứ bị xóa là **configuration parameter cũ `junit.jupiter.tempdir.scope`** đã deprecated, vì vậy một hệ thống giữ property cũ cần bỏ và dùng lifecycle đúng theo JUnit 6.

Chạy test trên Windows và Linux đều dùng `Path` và charset UTF-8, không dựa vào separator `/` hoặc hệ mã hóa mặc định. `Files.writeString` yêu cầu JDK 11+, trong bài Java 17 nên hợp lệ.

## 15. MockitoExtension trong cả JUnit 5 và 6

**`src/main/java/com/example/junitmatrix/RateGateway.java`:**

~~~java
package com.example.junitmatrix;

public interface RateGateway {
    int multiplier();
}
~~~

**`src/main/java/com/example/junitmatrix/CurrencyConverter.java`:**

~~~java
package com.example.junitmatrix;

import java.util.Objects;

public class CurrencyConverter {

    private final RateGateway rates;

    public CurrencyConverter(RateGateway rates) {
        this.rates = Objects.requireNonNull(
                rates, "rates"
        );
    }

    public long convert(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException(
                    "cents must not be negative"
            );
        }

        int multiplier = rates.multiplier();
        if (multiplier <= 0) {
            throw new IllegalStateException(
                    "rate must be positive"
            );
        }

        return Math.multiplyExact(cents, multiplier);
    }
}
~~~

`CurrencyConverter` không được annotate `@Component`. Nó là một unit fixture, không tạo dependency thiếu bean làm hỏng `@SpringBootTest` ở phần sau. Method gọi gateway stub và kiểm input; đây là ví dụ cách testing Mockito hoạt động **trên JVM** độc lập với Spring context.

**`src/test/java/com/example/junitmatrix/MockitoBoundaryTest.java`:**

~~~java
package com.example.junitmatrix;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MockitoBoundaryTest {

    @Mock
    RateGateway rates;

    @InjectMocks
    CurrencyConverter converter;

    @Test
    void convertsWithTestScopedMock() {
        when(rates.multiplier()).thenReturn(3);

        assertEquals(600L, converter.convert(200L));
        verify(rates).multiplier();
    }

    @Test
    void invalidMultiplierIsNotRetried() {
        when(rates.multiplier()).thenReturn(0);

        assertThrows(
                IllegalStateException.class,
                () -> converter.convert(200L)
        );
        verify(rates).multiplier();
    }
}
~~~

Đây là **hai `@Test` methods**. `@ExtendWith(MockitoExtension.class)` là extension Jupiter dùng được với bản Mockito tương thích được Boot quản lý. Nó không đồng nghĩa `@MockitoBean`: `@Mock`/`@InjectMocks` tạo mock/test fixture, **không thay bean** trong Spring ApplicationContext. Để mock bean của `@Autowired` service, dùng Spring `@MockitoBean` nếu cần và tránh chạy nhiều tests đồng thời trên shared mock/context.

### Spring Boot 4 và Mockito TestExecutionListener

Boot 4 loại bỏ `MockitoTestExecutionListener` đã deprecated (liên quan @Mock/@Captor behavior trong context). Với **pure Mockito unit tests**, dùng `MockitoExtension` tường minh như trên. Lỗi Spring test Mockito sau khi upgrade Boot 4 có thể liên quan listener/bean override thay đổi, không phải vì `org.junit.jupiter.api.Test` biến mất.

## 16. @SpringBootTest thật trên cả hai dòng Boot

**`src/test/java/com/example/junitmatrix/SpringBootCompatibilityTest.java`:**

~~~java
package com.example.junitmatrix;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("test")
class SpringBootCompatibilityTest {

    @Autowired
    GreetingService greetings;

    @Autowired
    ApplicationContext context;

    @Test
    void loadsAppAndTestProfile() {
        assertNotNull(
                context.getBean(JunitMatrixApplication.class)
        );
        assertEquals(
                "Integration",
                greetings.prefix()
        );
        assertEquals(
                "Integration, An!",
                greetings.greet(" An ")
        );
    }

    @Test
    void rejectsBlankInputInManagedBean() {
        assertThrows(
                IllegalArgumentException.class,
                () -> greetings.greet("   ")
        );
    }
}
~~~

Đây là **hai `@Test` methods**. Test class ở đúng package gốc của `@SpringBootApplication` để Spring Boot có thể autodetect main source; `@ActiveProfiles("test")` tải `src/test/resources/application-test.properties`. Vì không khởi động web server và không cần database, đây là một Spring context integration smoke test gọn cho cả Boot 3.5 và 4.1.

**Điểm tương thích:** `@SpringBootTest`, `@ActiveProfiles`, `@Autowired`, `ApplicationContext`, `org.junit.jupiter.api.Test` vẫn thuộc những APIs được dùng trong Spring Boot 3.5/Spring 6.2/JUnit 5 và Spring Boot 4.1/Spring 7/JUnit 6. Test không dựa vào Boot 3-specific test-slice packages hoặc removed `@MockBean` nên dễ so sánh.

Đừng dùng test này để tuyên bố **mọi** `@WebMvcTest`, `@DataJpaTest`, Spring Security, Jackson 2/3, Kafka hoặc plugin của project thật tương thích. Nó chỉ smoke-test một Spring context + property binding/DI, không có infrastructure khác.

## 17. Kiểm đếm rõ số phương thức test và invocations

Trong **bốn** Java test classes ở mục 13–16:

| Class | Test methods có annotation | Jupiter test invocations dự kiến |
| --- | ---: | ---: |
| `PriceCalculatorTest` | **3** (2 `@Test`, 1 `@ParameterizedTest`) | **5** (2 + 3 CSV rows) |
| `FileFixtureTest` | **1** `@Test` | **1** |
| `MockitoBoundaryTest` | **2** `@Test` | **2** |
| `SpringBootCompatibilityTest` | **2** `@Test` | **2** |
| **Tổng** | **8** | **10** |

Một parameterized method có ba CSV rows **không phải ba Java methods**, nhưng sẽ tạo ba JUnit test invocations. Vì mỗi method không có `@TestFactory`/dynamic tests hay disabled tests, đây là số logical invocations dự kiến. **Không gắn nhãn “10 tests passed” nếu chưa chạy!** Gradle/XML test report thực tế mới là bằng chứng execution; có thể có tests skipped/fail trong môi trường khác.

Dự án không cố tình in `System.out.println`; không có stdout nghiệp vụ cố định để hứa. Spring startup/JUnit test runner logs phụ thuộc version/IDE và không phải output contract.

## 18. Cách kiểm resolved versions bằng Gradle, không đoán BOM

Chạy với phương án A hoặc B đã chọn:

~~~bash
./gradlew --version
./gradlew dependencyInsight \
  --configuration testRuntimeClasspath \
  --dependency junit-jupiter-engine
./gradlew dependencyInsight \
  --configuration testRuntimeClasspath \
  --dependency junit-platform-launcher
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew test --rerun-tasks
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat dependencyInsight --configuration testRuntimeClasspath --dependency junit-jupiter-engine
.\gradlew.bat dependencyInsight --configuration testRuntimeClasspath --dependency junit-platform-launcher
.\gradlew.bat dependencies --configuration testRuntimeClasspath
.\gradlew.bat test --rerun-tasks
~~~

**Đọc resolved dependency**, không chỉ xem một dòng trong `build.gradle`. Một dependency constraint, imported BOM khác, test plugin hay Gradle platform có thể làm số thực tế khác với default. `dependencyInsight` chỉ ra **selection reason** và đường phụ thuộc vào artifact.

Kỳ vọng:
- Boot **3.5.16**: `junit-jupiter-engine:5.12.2`; `junit-platform-launcher:1.12.2`.
- Boot **4.1.2**: `junit-jupiter-engine:6.0.3`; `junit-platform-launcher:6.0.3`.

**Không chạy lệnh `java -version` rồi kết luận JUnit resolved version**; đó chỉ là version Java runtime. Và **không chỉ kiểm `compileClasspath`**: Jupiter engine/launcher nằm trên test runtime, cần query `testRuntimeClasspath`.

Để bắt test discovery rỗng, sau `--rerun-tasks` kiểm `build/test-results/test/TEST-*.xml` và `build/reports/tests/test/index.html`. Nếu task `NO-SOURCE`/`SKIPPED`, không có bằng chứng đã chạy 10 invocations.

## 19. Maven POM tối thiểu cũng nên để Boot parent quản lý JUnit

Maven sử dụng `spring-boot-starter-parent` và `spring-boot-starter-test`. Một **`pom.xml` độc lập** cho Boot 3.5.16:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>junit-boot-compatibility-demo</artifactId>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Để dùng **Boot 4.1.2** trong ví dụ core này, tạo một bản **`pom.xml` thay thế** có toàn bộ nội dung giống trên nhưng sửa đúng một trường `<parent><version>4.1.2</version>`. **Không dùng hai Boot parents trong cùng POM**. Test code core ở mục 10–16 không phụ thuộc test modules chuyên ngành Boot 3, nên là cơ sở so sánh hợp lý.

JUnit 6 yêu cầu **Maven Surefire/Failsafe >=3.0.0**; ví dụ pin `3.5.4` để tránh inherited plugin quá cũ. Maven parent Boot có thể đã quản lý version thích hợp, nhưng pin tường minh trong tài liệu giúp minh họa điều kiện JUnit 6. Với production repo, so Maven effective POM để tránh không cần thiết override version đã được parent quản lý.

Đừng thêm một JUnit BOM độc lập vào project đã dùng Spring Boot parent/BOM chỉ để “cập nhật bản mới”: tài liệu JUnit khuyến nghị dùng Boot dependency management khi dự án phụ thuộc Boot.

## 20. Kiểm Maven effective POM và dependency tree

~~~bash
mvn -version
mvn help:effective-pom
mvn dependency:tree -Dincludes=org.junit.jupiter,org.junit.platform,org.junit.vintage
mvn -Dtest=PriceCalculatorTest test
mvn test
~~~

Cùng lệnh dùng được trên Windows PowerShell khi Maven đã có trong PATH; nếu dự án có Maven Wrapper nên dùng `./mvnw`/`.\mvnw.cmd` tương ứng.

`help:effective-pom` cho biết plugin/configuration sau inheritance; `dependency:tree` cho biết dependency versions Maven thực sự chọn. Đừng đọc riêng `pom.xml` rồi suy ra `junit-jupiter-api` đang là 6.x trong khi Maven có một imported BOM/plugin constraint khác.

**Phân biệt Surefire và Failsafe**: Surefire mặc định chạy unit tests trong phase `test`. Failsafe thường dùng cho integration tests trong phases `integration-test`/`verify` theo cấu hình và naming; JUnit 6 yêu cầu cả plugin có version ít nhất 3.0.0 nếu được dùng. Chỉ thêm `maven-failsafe-plugin` vào POM chưa đủ để nó tự chạy integration test; còn phải khai báo executions phù hợp.

## 21. Khi không dùng Spring Boot BOM: JUnit BOM mới là lựa chọn đúng

Với **plain Java library** không dùng Spring Boot parent/dependency-management, bạn có thể dùng JUnit BOM để align:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform(
        'org.junit:junit-bom:6.0.3'
    )
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Đây là **standalone build snippet cho ứng dụng không dùng Boot**, không phải phần phải dán vào cả hai Spring Boot builds. Nếu cần JUnit 5 trên một Java project thuần, chọn JUnit BOM 5.x tương ứng (Platform sẽ là 1.x theo BOM), không mix một BOM 6.x với các Jupiter 5.x artifacts.

JUnit 6 artifact POMs cũng có thông tin platform; BOM explicit giúp intent rõ. Trong Spring Boot project, **ưu tiên BOM của Boot**, vì Boot đã quyết định một tập third-party versions hoạt động cùng nhau. Nếu có hai BOMs cùng điều khiển JUnit, Gradle/Maven conflict resolution có thể không theo kỳ vọng.

## 22. JUnit Vintage: JUnit 4 tests không tự biến thành Jupiter tests

Phân biệt hai kiểu import:

~~~java
// JUnit 4:
import org.junit.Test;

// JUnit Jupiter 5 hoặc 6:
import org.junit.jupiter.api.Test;
~~~

Với JUnit 4 test cũ:

~~~java
import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class LegacyMathTest {

    @Test
    public void adds() {
        assertEquals(4, 2 + 2);
    }
}
~~~

Đây là **tệp minh họa JUnit 4**, không nằm trong source tree của demo chính. JUnit Jupiter `@Test` không tự discover JUnit 4 annotation nếu không có Vintage engine. Trong Boot 3.5 và Boot 4.1, thêm có chủ đích:

~~~groovy
dependencies {
    testImplementation 'junit:junit:4.13.2'
    testRuntimeOnly 'org.junit.vintage:junit-vintage-engine'
}
~~~

Đây là **phần bổ sung** vào một trong hai Gradle builds, không phải một build độc lập. Version Vintage được Boot BOM quản lý: **5.12.2** trên Boot 3.5.16, **6.0.3** trên Boot 4.1.2. **JUnit Vintage 6 đã deprecated**; nên dùng nó tạm trong kế hoạch migration, không làm lời hứa hỗ trợ JUnit 4 mãi mãi.

Sau khi mọi test đã sang Jupiter, xóa dependency `junit:junit`/Vintage nếu không còn cần. Xác nhận IDE/Gradle reports không mất các JUnit 4 tests vốn được chạy trong quá khứ.

## 23. Ví dụ chuyển JUnit 4 sang Jupiter, khác với nâng Jupiter 5 → 6

JUnit 4:

~~~java
import org.junit.Before;
import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class LegacyServiceTest {
    private GreetingService service;

    @Before
    public void init() {
        service = new GreetingService("Legacy");
    }

    @Test
    public void canGreet() {
        assertEquals("Legacy, An!", service.greet("An"));
    }
}
~~~

Jupiter 5 hoặc 6 tương ứng:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class ModernServiceTest {
    private GreetingService service;

    @BeforeEach
    void init() {
        service = new GreetingService("Modern");
    }

    @Test
    void canGreet() {
        assertEquals("Modern, An!", service.greet("An"));
    }
}
~~~

Cả hai là **snippets độc lập minh họa** cùng package giả định có `GreetingService`; không thêm vào project demo nếu không đặt đúng file/package/import. Điểm thay đổi là **JUnit 4 → Jupiter**, chứ không phải JUnit 5 → JUnit 6. Spring Boot JUnit Jupiter integration thường dùng `@SpringBootTest` (đã tích hợp SpringExtension) thay cho JUnit 4 `@RunWith(SpringRunner.class)`.

Mapping cơ bản:

| JUnit 4 | Jupiter 5 và 6 |
| --- | --- |
| `org.junit.Test` | `org.junit.jupiter.api.Test` |
| `@Before` / `@After` | `@BeforeEach` / `@AfterEach` |
| `@BeforeClass` / `@AfterClass` | `@BeforeAll` / `@AfterAll` |
| `@RunWith(SpringRunner.class)` | `SpringExtension` hoặc `@SpringBootTest`/`@SpringJUnitConfig` |
| `@Test(expected=X.class)` | `assertThrows(X.class, () -> ...)` |
| `@Rule TemporaryFolder` | `@TempDir` |
| `@RunWith(Parameterized.class)` | `@ParameterizedTest` và source annotations |
| JUnit 4 categories | Jupiter `@Tag` |

`@BeforeAll` mặc định thường static với JUnit Jupiter `PER_METHOD` lifecycle; với `@TestInstance(PER_CLASS)` có thể dùng instance method tùy API. Đừng copy nguyên lifecycle/runner assumptions từ JUnit 4.

## 24. Spring Boot 4 test starter modularization: lỗi không phải JUnit 6

Spring Boot 4 có test infrastructure được chia thành các mô-đun công nghệ. Trong Boot 3.5, nhiều libraries phục vụ web/data testing được cấp qua starter bao quát; trong Boot 4, với một số công nghệ cần thêm **companion test starter**.

| Công nghệ | Boot 4 main starter | Boot 4 test starter phù hợp |
| --- | --- | --- |
| Core Spring Boot + Jupiter | `spring-boot-starter` | `spring-boot-starter-test` |
| Spring MVC | `spring-boot-starter-webmvc` | `spring-boot-starter-webmvc-test` |
| Spring WebFlux | `spring-boot-starter-webflux` | `spring-boot-starter-webflux-test` |
| Spring Data JPA | `spring-boot-starter-data-jpa` | `spring-boot-starter-data-jpa-test` |
| Spring JDBC | `spring-boot-starter-jdbc` | `spring-boot-starter-jdbc-test` |
| Spring Security | `spring-boot-starter-security` | `spring-boot-starter-security-test` |
| Spring Kafka | `spring-boot-starter-kafka` | `spring-boot-starter-kafka-test` |

Đây là **mẫu tên starter trong Spring Boot 4.1**, không phải khẳng định tất cả đã có trong Boot 3.5 hoặc mọi starter test đều cần với app core. Các test starters chuyên biệt sẽ kéo core `spring-boot-starter-test` khi phù hợp.

Nếu `@WebMvcTest` hoặc `@DataJpaTest` không compile sau Boot 4, kiểm **package annotation mới và công nghệ test starter**. Không “chữa” bằng nâng JUnit Jupiter lên bản khác; đó là vấn đề Spring Boot modularization.

### @MockBean và @SpyBean

Trong Boot **3.4/3.5**, `@MockBean`/`@SpyBean` đã deprecated; trong Boot **4.0+**, chúng đã được **loại bỏ**. Dùng Spring Framework `@MockitoBean`/`@MockitoSpyBean`:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

// Trong Spring Boot test class:
@MockitoBean
PaymentGateway paymentGateway;
~~~

Đoạn trên là **snippet** với `PaymentGateway` là một type minh họa, không thuộc runnable project. Nếu cùng code phải build trên Boot 3.5 và 4.1, `@MockitoBean` là lựa chọn tương thích hơn vì Spring Framework 6.2 và 7 hỗ trợ nó. Cần phân biệt mock bean trong Spring context với Mockito `@Mock` thuần trên unit test.

### Boot 4 @SpringBootTest và web testing

Spring Boot 4 migration guide nêu `@SpringBootTest` không còn tự cung cấp một số hỗ trợ MockMvc/HTTP test clients như trước; với MockMvc phải sử dụng `@AutoConfigureMockMvc` và test dependencies đúng, với TestRestTemplate/RestTestClient cần companion modules và annotations thích hợp. Đây là **thay đổi Boot 4**, không phải breaking change `@Test` của JUnit 6.

## 25. Gradle/JUnit Platform TestEngine: không có test được chạy

Một build có thể compile thành công nhưng task `test` báo `NO-SOURCE`, `SKIPPED`, `No tests found` hoặc 0 tests. Trước khi thay code, kiểm bốn tầng:

~~~text
1) Gradle test source set
   src/test/java / custom src/integrationTest/java
        |
        v
2) Test task configuration
   testClassesDirs / runtime classpath / useJUnitPlatform()
        |
        v
3) JUnit Platform launcher + registered engines
   junit-platform-launcher + junit-jupiter-engine
        |
        v
4) Jupiter discovery + filters
   @org.junit.jupiter.api.Test, --tests, tags, engines
~~~

Nếu `src/test/java` trống, thêm Jupiter engine không tạo tests. Nếu `junit-jupiter-api` có nhưng engine thiếu, test Java compile nhưng Platform không có engine để discover. Nếu `useJUnitPlatform()` thiếu trên custom `Test` task, Gradle có thể không chạy Jupiter như mong đợi. Nếu có `includeTags("slow")` mà không test nào gắn tag, task không tìm thấy tests phù hợp.

**Gradle 9:** các custom `Test` task nên cấu hình rõ `testClassesDirs` và `classpath`; một Gradle 9 runner không tự sửa dependency graph JUnit/Boot của dự án. Với Spring Boot 3.5 nên tiếp tục dùng Gradle 8.x trong phạm vi được công bố; Boot 4 có thể dùng Gradle 9 sau khi verify plugins.

## 26. Maven Surefire/Failsafe, IDE và version drift

JUnit 6 cần Maven Surefire/Failsafe **>=3.0.0**. Một `maven-surefire-plugin` 2.x có thể không hiểu engine/launcher hiện đại; triệu chứng có thể là 0 tests hoặc platform/provider mismatch. Với JUnit Jupiter 5, cũng nên dùng bản plugin được Boot parent quản lý hoặc bản mới tương thích; không cố giữ Surefire cũ vì tests trước đây “chạy được trong IDE”.

Điều khác nhau giữa IDE và CI:

- IDE có thể chạy test qua JUnit launcher tích hợp, còn Gradle/Maven dùng runtime dependency/configurations của project.
- IntelliJ/Eclipse/VS Code versions cũ có thể không hiểu JUnit 6/Platform 6 ngay, nhất là custom test engines hoặc project Kotlin.
- Chế độ IDE “Run tests using Gradle” giúp so sánh cùng task, nhưng không loại bỏ khác biệt JDK/env variables.
- JUnit dependency tree trong IDE có thể stale do cache, import chưa refresh.
- CI đa module có Gradle/Maven parents/dependencyManagement khác; phải kiểm từng module/test configuration.
- Cần kiểm test discovery counts thực, không chỉ nhìn “green triangle” ở một phương thức.

**Lệnh kiểm Maven phù hợp:** `mvn -version`, `mvn help:effective-pom`, `mvn dependency:tree`, `mvn -Dtest=... test`. **Lệnh kiểm Gradle:** `./gradlew --version`, `dependencyInsight` cho Jupiter engine và launcher, `./gradlew test --rerun-tasks`.

## 27. Những lỗi linkage thường báo khi trộn JUnit 5 và 6

| Dấu hiệu | Nguồn gốc có thể | Hành động |
| --- | --- | --- |
| `NoClassDefFoundError` trong `org.junit.platform.*` | Platform JAR/runtime launcher thiếu hoặc lệch | Kiểm `testRuntimeClasspath`, align BOM |
| `NoSuchMethodError` / `AbstractMethodError` | Extension/engine compile theo API khác version | Tìm JAR mismatch, nâng đồng bộ |
| `ClassNotFoundException: org.junit.jupiter.api.Test` | Jupiter API không trên test compile classpath | `spring-boot-starter-test` scope/test dependency |
| `Cannot create Launcher without at least one TestEngine` | Không có Jupiter/Vintage engine | Thêm engine qua starter/Jupiter aggregate |
| Test classes compile, Gradle không discover | Sai `useJUnitPlatform`, source set, test filter | Kiểm task/engine/annotations |
| `UnsupportedClassVersionError` | JUnit 6/Boot 4/JDK compiled cho Java mới hơn runtime | Test JVM >=Java17; kiểm daemon/toolchain |
| `junit-platform-runner` không resolve trên JUnit 6 | Module đã bị loại bỏ | Migrate sang launcher/Jupiter, bỏ runner |
| `MethodOrderer.Alphanumeric` không compile | API deprecated đã bị xóa ở JUnit 6 | Đổi ordering strategy |
| `@CsvFileSource(lineSeparator=...)` không compile | Attribute đã xóa | Bỏ attribute, để auto-detect line endings |
| JUnit 4 test không được chạy | Không có Vintage engine | Thêm Vintage tạm hoặc migrate Jupiter |
| `@MockBean` không compile sau Boot4 | API Boot đã loại bỏ | Dùng `@MockitoBean` |
| `@WebMvcTest` thiếu sau Boot4 | Boot test starter/module/package khác | Thêm MVC test starter, sửa imports |
| `No qualifying bean` sau migration | Spring context configuration/bean scan khác | Debug Spring Boot context, không kết luận JUnit version |
| Mockito extension không init mocks | Không gắn `@ExtendWith(MockitoExtension.class)` hoặc dependency mismatch | Dùng Mockito Jupiter extension đúng |
| Mockito inline/ByteBuddy cảnh báo với JDK mới | Mockito/ByteBuddy/agent/JDK compatibility | Dùng versions Boot-managed, kiểm warnings |
| IDE chạy, CI Maven 0 tests | Surefire/Failsafe/provider quá cũ | Update >=3.0.0 với JUnit6 |
| JUnit report count không như expected | Parameterized tests/disabled/dynamic tests/filters | Kiểm XML nodes và test discovery |

**Không đồng nhất** mọi `Failed to load ApplicationContext` với lỗi JUnit 6. Khi Spring test extension chạy và context fail vì datasource, profile, bean ambiguity, đó là lỗi **Spring bootstrap/business infrastructure**. Đọc root cause trước khi đụng BOM.

## 28. Một migration plan không làm hỏng CI

Để chuyển ứng dụng thực từ Boot 3.5/JUnit 5 sang Boot 4.1/JUnit 6:

1. **Chốt baseline:** dùng Boot 3.5 patch đang có, chạy `./gradlew test`/`mvn test`, lưu JUnit XML counts và danh sách skipped tests.
2. **Kiểm Java:** production và test JVM >=17; JDK chạy Gradle/Maven/plugin đúng vùng hỗ trợ.
3. **Kiểm deprecated APIs:** tìm `@MockBean`, `@SpyBean`, `org.junit.platform.runner`, `MethodOrderer.Alphanumeric`, `@CsvFileSource(lineSeparator=...)`, `junit.jupiter.tempdir.scope`, custom extensions.
4. **Đọc Boot 4 migration guide:** package moves, modular test starters, Jackson 3, Spring Framework 7, auto-configuration và Mockito bean override changes.
5. **Tạo nhánh migration:** đổi Spring Boot plugin/parent sang bản Boot 4 phù hợp; **để Boot BOM kéo JUnit 6**.
6. **Đặt build tool:** Gradle 8.14+ hoặc 9 với Boot4; Maven 3.6.3+ và Surefire/Failsafe >=3.0.0.
7. **Chọn test starters:** thêm technology-specific test starters cho MVC/JPA/Security/Kafka/WebFlux/GraphQL phù hợp; không gộp mọi starter bừa.
8. **Sửa imports/code bị deprecated/removed:** ưu tiên `@MockitoBean`, sửa runner/ordering/CSV options nếu thật sự dùng.
9. **Kiểm resolved tree:** Jupiter/Platform/Vintage cùng major/release; không còn stale engine 5 hoặc Platform 1 trên Boot4.
10. **Chạy nhóm nhỏ:** pure unit, Mockito, Spring Boot context, MVC/data slices rồi toàn suite.
11. **Kiểm CI artifacts:** actual test counts, failures, skipped/disabled, XML/HTML paths, Gradle test forks/Maven Surefire reports.
12. **Kiểm external integrations:** Testcontainers, embedded Kafka, Spring Security/REST docs, dependency plugins có thể cần versions Boot4-specific.
13. **Không che lỗi bằng skip:** tránh `-x test`, `-DskipTests`, `ignoreFailures=true` như một giải pháp migration.
14. **Giữ fallback:** nếu Boot4 migration chưa chín, tiếp tục Boot3.5/JUnit5 managed, ưu tiên sửa build/reliability thay vì ép major mới.
15. **Đo hiệu năng và isolation:** context cache, mocks, JUnit parallelism, database cleanup; JUnit 6 không làm biến mất state leaks.

Nên tách PR **upgrade dependency platform** và PR **refactor business tests** khi có thể; thay mọi thứ cùng lúc khiến khó xác định lỗi do JUnit, Boot, Java, hay framework khác.

## 29. Test slice, SpringExtension và @MockitoBean sau nâng cấp

**SpringExtension** tích hợp Jupiter với Spring TestContext:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = MiniConfig.class)
class SmallSpringTest {
}
~~~

Đây là **snippet minh họa** thiếu `MiniConfig`/imports nên không thuộc project runnable. `@SpringJUnitConfig(MiniConfig.class)` thường diễn đạt gọn hơn. Với `@SpringBootTest`, Spring Boot đã cấu hình Jupiter/SpringExtension phù hợp; không cần luôn lặp `@ExtendWith(SpringExtension.class)`.

Đối với bean mocks trong Spring context, ví dụ định hướng:

~~~java
@SpringBootTest
class PartnerServiceTest {
    @MockitoBean
    RemotePartner partner;

    @Test
    void replacesRemoteDependency() {
        // Stub/verify partner theo contract cần kiểm.
    }
}
~~~

Đây là **skeleton**, không có `RemotePartner`/service implementation và không phải test runnable. Trong Boot 3.5, `@MockitoBean` đã có qua Spring Framework 6.2; trong Boot 4.1 qua Spring 7. Khi nhiều tests share cached ApplicationContext, mock trong context có thể được reuse/reset; tránh chạy song song các tests cùng mock mà không có isolation.

**Slice APIs:** Boot4 modular hóa packages/test dependencies; một cách gọi tên `@WebMvcTest` trong Boot3 không chắc import package giữ nguyên ở Boot4. Khi nâng Boot, sửa đúng annotation package và companion starter theo migration docs, đồng thời kiểm primary `@SpringBootApplication` của test vẫn được phát hiện. JUnit 6 không phải nguyên nhân trực tiếp của tất cả test-slice import changes.

## 30. Version override: bao giờ nên làm và cần kiểm gì?

Không phải cấm mọi override: một tổ chức có thể phải vá bảo mật của JUnit/Mockito trong khi chờ Boot maintenance release. Nhưng override phải là **chủ đích có bằng chứng**, không phải việc mặc định của mỗi developer.

Quy trình khi thực sự cần:

- Xác định CVE/bug hoặc feature cần, risk và phạm vi test stack.
- So Boot BOM effective version, release notes của JUnit/Mockito và compatibility của Spring Framework.
- Với Spring Boot dependency management, dùng **đúng BOM property** hoặc dependency constraints tương ứng, tránh pin lẻ một artifact.
- Align Jupiter API/engine/params, Platform launcher/engine/commons, Vintage (nếu có).
- Chạy pure unit + SpringBootTest + Mockito + integration/slices trên ít nhất JDK/Gradle/Maven CI chính.
- Kiểm JUnit Platform custom TestEngine từ third-party và IDE.
- Ghi lại exception được chấp thuận và kế hoạch trở về managed version sau khi Boot cập nhật.
- Nếu override vượt major JUnit 5 → 6 **trong Boot3.x**, phải coi đây là configuration **tự chịu trách nhiệm tương thích**, không thuộc đường nâng được khuyến nghị.

**Đừng** thêm đồng thời `org.junit:junit-bom:6.0.3` và Spring Boot 3.5 BOM rồi tin rằng engine/launcher/Spring Test chắc chắn nhất quán. Dùng `dependencyInsight` hoặc Maven dependency tree xác minh từng JAR.

## 31. JUnit Vintage 6 deprecated và rủi ro các tests bị bỏ quên

Nếu project có cả:

~~~text
LegacyOrderTest.java    import org.junit.Test;          (JUnit 4)
ModernOrderTest.java    import org.junit.jupiter.api.Test; (Jupiter)
~~~

trong Boot 4.1 `spring-boot-starter-test` mặc định cung cấp Jupiter, nhưng **không nên giả mọi JUnit 4 tests tự chạy**. Thêm `junit:junit:4.13.2` và `junit-vintage-engine` đúng 6.x nếu vẫn cần tạm, sau đó xem report xác nhận từng lớp legacy có execution.

Điểm quan trọng khi chuyển JUnit 5 → 6:
- **Vintage 6 vẫn tồn tại**, không phải JUnit 4 bị cấm ngay lập tức.
- Nhưng Vintage 6 **deprecated** và phát discovery issue ở mức INFO khi phát hiện JUnit 4 tests theo release notes.
- Không phụ thuộc `junit-platform-runner` cũ: module đã bị xóa.
- Có thể migrate từng lớp JUnit 4 sang Jupiter trong các PR riêng, giữ test coverage.
- Khi xóa Vintage, CI phải báo nếu còn JUnit 4 tests được compile nhưng không được discover.

Các test classes có `@RunWith(SpringRunner.class)` liên quan JUnit 4; đổi sang Jupiter `@SpringBootTest`/`SpringExtension` theo contract. Đừng nhầm với việc chỉ thay `org.junit.jupiter.api.Test` của Jupiter 5 thành Jupiter 6 — nó không cần đổi.

## 32. Test speed, parallelism và context cache không thay bằng version upgrade

Dùng JUnit 6 không đồng nghĩa Spring tests sẽ tự hết flaky. Cần kiểm:

- JUnit default test instance lifecycle `PER_METHOD` và tùy chọn `PER_CLASS`.
- `@Execution(CONCURRENT)`/`@ResourceLock`/`@Isolated` khi bật parallel (các API phù hợp theo version).
- Spring TestContext cached `ApplicationContext` có thể chia singleton beans và `@MockitoBean` giữa test classes.
- Spring mock reset lifecycle không bảo đảm thread-safety cho nhiều tests đang dùng chung một mock.
- `@Transactional` test rollback trên test thread không tự rollback HTTP server/`@Async` worker threads.
- Shared H2/Redis/Kafka/DB data cần unique IDs, scoped cleanup, awaited worker completion.
- `@TempDir` là tiện ích test temp file; nó không giúp dọn external database.
- Mốc Gradle test forks và JUnit internal parallel threads khác nhau.

Nếu sau migration tests FAIL ngẫu nhiên dưới parallel nhưng PASS khi tuần tự, chẩn đoán shared mutable state và context/mocks trước khi đổ lỗi cho Jupiter 6. Một version upgrade có thể chỉ làm thay đổi timing và lộ race vốn đã tồn tại.

## 33. Troubleshooting JUnit 6 trên IDE và CLI

| Trường hợp | Vì sao dễ xảy ra | Kiểm tra |
| --- | --- | --- |
| Chạy nút Test trong IDE PASS, Gradle FAIL | IDE runner tích hợp khác JUnit Platform launcher/runtime deps | Delegate test to Gradle, kiểm `testRuntimeClasspath` |
| Gradle PASS, Maven FAIL | Surefire/Failsafe cũ, effective POM khác Gradle | `mvn help:effective-pom`, Surefire >=3.0.0 |
| Build compile, không test nào chạy | Jupiter engine/runtime launcher/filter thiếu | `useJUnitPlatform`, dependencies, XML counts |
| Các tests có Jupiter 5 lẫn Jupiter 6 | Imported BOM/constraints conflict | `dependencyInsight` cho mọi JUnit module |
| Java 11 CI, Java 17 local | JUnit 6 classfile Java 17 | Java toolchain/test JVM, pipeline JDK |
| Test class có `org.junit.Test` | Còn JUnit 4 | Vintage tạm hoặc migrate |
| Lỗi `@MockBean` trên Boot4 | Spring Boot removed API | `@MockitoBean` (Spring Test) |
| Lỗi `@DataJpaTest` import trên Boot4 | Test modules được tách | Starter tương ứng, import mới |
| Failure `Failed to load ApplicationContext` | Bean/profile/DB/scan issue | Đọc `Caused by` gốc của Spring context |
| Gọi `gradle` hệ thống | Wrapper version drift | `./gradlew --version` |
| Chỉ có API nhưng thiếu engine | Jupiter API có trên compile classpath | Thêm proper test runtime Jupiter aggregate/engine |
| Không tìm thấy `@SpringBootConfiguration` | Test package/source sai | Package app, `classes=...` |
| Parameterized test output khác display name | JUnit6 formatting CSV display names thay đổi | Assert data/results, đừng assert display name không ổn định |
| CSV parser nhận line endings khác | `lineSeparator` removed; auto detection | Dùng UTF-8 fixture đúng, bỏ deprecated option |
| Gradle 9 + Boot3.5 | Spring Boot 3.5 không công bố Gradle9 | Giữ Gradle8 hoặc lên Boot4 |
| IDE version cũ không hiểu JUnit 6 | IDE runtime integration chưa cập nhật | Update IDE hoặc delegate Gradle/Maven |

**Trình tự chẩn đoán:** (1) Java/Gradle/Maven versions; (2) resolved JUnit artifacts; (3) test engine/task discovery; (4) Spring context source/beans; (5) Mockito/extension; (6) domain assertions. Đừng sửa code nghiệp vụ trước khi xác định chính xác tầng lỗi.

## 34. CI hai nhánh Boot 3.5 và Boot 4.1: đừng trộn dependencies

Nếu library/shared code thật sự hỗ trợ cả Boot 3.5 và 4.1, nên chạy **hai jobs độc lập** với version Boot BOM/parent riêng, không tạo một JVM classpath chứa **cả Spring Boot 3 và 4**.

Ví dụ pipeline logic:

~~~text
Job A:
  Java 17 + Gradle 8.14.3
  build.gradle với Boot 3.5.16
  JUnit Jupiter 5.12.2 / Platform 1.12.2
  ./gradlew clean test

Job B:
  Java 17 + Gradle 8.14.3
  build.gradle với Boot 4.1.2
  JUnit Jupiter 6.0.3 / Platform 6.0.3
  ./gradlew clean test

Cả hai:
  kiểm JUnit test results/XML
  kiểm errors/ignored/skipped
  kiểm dependencyInsight và JDK
~~~

Hai cấu hình ở mục 7–8 là **hai build files thay thế**, không tự tạo một Gradle matrix dynamic bằng cách sửa file trên shared workspace giữa parallel tasks. Nếu dùng CI matrix với `-PbootVersion=...`, build script cần thiết kế dependency/plugin versions có thể cấu hình, job mỗi workspace sạch và verify plugin marker/management; không nên thay version bằng `sed` trên cùng file mà hai jobs đang dùng.

Với service ứng dụng thông thường, không cần support hai Boot majors cùng lúc; tập trung target release đúng rồi chạy đầy đủ CI trên nó.

## 35. Checklist QA trước khi kết luận tương thích

- [ ] Dòng Spring Boot/plugin/parent version thực tế là bao nhiêu?
- [ ] Đã tra **managed dependency coordinates** đúng patch version?
- [ ] Có phân biệt Jupiter **5.x** với Platform **1.x** trên Boot 3.5?
- [ ] Có phân biệt Jupiter/Platform/Vintage cùng **6.x** trên Boot 4.1?
- [ ] Không pin ngẫu nhiên Jupiter/Platform khác release train?
- [ ] Chỉ dùng một Boot BOM/parent làm owner các test dependencies?
- [ ] Có `spring-boot-starter-test` ở test scope?
- [ ] JUnit Platform launcher và Jupiter engine xuất hiện trong test runtime?
- [ ] Đã gọi `useJUnitPlatform()` trên Gradle `Test` task?
- [ ] Maven Surefire/Failsafe >=3.0.0 khi JUnit 6?
- [ ] JDK chạy tests ≥17 khi dùng JUnit 6?
- [ ] Gradle Wrapper phù hợp Spring Boot plugin (Boot3.5: 7.6.4+/8.4+; Boot4.1: 8.14+/9.x)?
- [ ] Test Java Jupiter imports `org.junit.jupiter.*` vẫn được giữ?
- [ ] Đã kiểm APIs bị xóa như `MethodOrderer.Alphanumeric`/`junit-platform-runner`?
- [ ] Đã bỏ `junit.jupiter.tempdir.scope` và `@CsvFileSource(lineSeparator)` cũ?
- [ ] `@TempDir`, `@ParameterizedTest`, `@CsvSource` vẫn được import đúng?
- [ ] Mockito unit tests dùng `MockitoExtension` với Mockito compatible?
- [ ] Boot4 tests đã thay `@MockBean`/`@SpyBean` bằng `@MockitoBean`/`@MockitoSpyBean`?
- [ ] Boot4 tech-specific tests có starter -test tương ứng?
- [ ] Không lẫn test-slice Boot4 migration với Jupiter API migration?
- [ ] JUnit 4 legacy tests có explicit Vintage hoặc đã migrate Jupiter?
- [ ] `dependencyInsight`/`dependency:tree` xác minh versions thật?
- [ ] JUnit XML/test reports cho thấy đúng test invocations thực thi, không bị filter/skip?
- [ ] ApplicationContext smoke test đúng app/config/profile?
- [ ] CI test JVM/JDK và IDE runner tương thích?
- [ ] Không dùng `-x test`, `skipTests` hay `ignoreFailures` để che lỗi?
- [ ] Test classes độc lập, không leak shared singleton/DB/mock state?
- [ ] Kết quả expected trong README được phân biệt với build thực tế?

## 36. Lệnh chạy và kết quả dự kiến của project mẫu

Với **một** trong hai `build.gradle`, Java 17, Gradle Wrapper, các files ở mục 10–16:

~~~bash
./gradlew --version
./gradlew clean test
./gradlew test --tests "com.example.junitmatrix.PriceCalculatorTest"
./gradlew test --tests "com.example.junitmatrix.FileFixtureTest"
./gradlew test --tests "com.example.junitmatrix.MockitoBoundaryTest"
./gradlew test --tests "com.example.junitmatrix.SpringBootCompatibilityTest"
./gradlew test --rerun-tasks --stacktrace
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test
.\gradlew.bat test --tests "com.example.junitmatrix.PriceCalculatorTest"
.\gradlew.bat test --tests "com.example.junitmatrix.FileFixtureTest"
.\gradlew.bat test --tests "com.example.junitmatrix.MockitoBoundaryTest"
.\gradlew.bat test --tests "com.example.junitmatrix.SpringBootCompatibilityTest"
.\gradlew.bat test --rerun-tasks --stacktrace
~~~

**Mã và Assertions dự kiến:**

| Test/nhóm | Kỳ vọng nếu dự án được biên dịch/chạy đúng |
| --- | --- |
| `PriceCalculatorTest.calculatesTenPercentDiscount` | `afterDiscount(1000,10)==900` |
| `PriceCalculatorTest.worksForParameterizedExamples` | 3 CSV cases: 900, 400, 179 |
| `PriceCalculatorTest.rejectsInvalidArguments` | 3 input lỗi đều ném `IllegalArgumentException` |
| `FileFixtureTest.createsUtf8FileInsideTempDirectory` | Tạo và đọc lại `"Xin chào JUnit"` bằng UTF-8 |
| `MockitoBoundaryTest.convertsWithTestScopedMock` | Mock multiplier=3, kết quả 600, verify gọi gateway |
| `MockitoBoundaryTest.invalidMultiplierIsNotRetried` | Mock multiplier=0, ném `IllegalStateException` |
| `SpringBootCompatibilityTest.loadsAppAndTestProfile` | `JunitMatrixApplication` bean tồn tại, prefix Integration, greeting "Integration, An!" |
| `SpringBootCompatibilityTest.rejectsBlankInputInManagedBean` | Ném `IllegalArgumentException` khi name blank |
| **Tổng** | **8 test methods; 10 expected Jupiter invocations** |

Với Maven POM ở mục 19, dùng `mvn test` và `mvn -Dtest=SpringBootCompatibilityTest test` để chạy nhóm tương ứng.

**Đây là expected behavior suy ra từ mã và tài liệu API, không phải kết quả Gradle/Maven/JUnit đã được thực thi.** Project mẫu cần dựng đúng file paths, Gradle Wrapper và dependencies để chạy; khi thực thi, logs từ Spring Boot/Gradle có thể khác và số counts phản ánh engine/provider. Không được tuyên bố “10 tests PASS” nếu chưa có report/CI output.

## 37. Kết luận: chọn JUnit bằng BOM của dòng Spring Boot

**Spring Boot 3.5.16 → Jupiter 5.12.2 + Platform 1.12.2. Spring Boot 4.1.2 → Jupiter/Platform 6.0.3.** Đây là hai tập managed dependencies được xác minh trong tài liệu chính thức. Không có một quy tắc “JUnit 6 mới hơn thì nên pin ngay trong mọi Boot 3 project”.

JUnit 6 giữ `org.junit.jupiter` cùng phần lớn programming model JUnit 5, nhưng nâng Java baseline lên 17, thống nhất numbering Platform/Jupiter/Vintage và loại một số APIs deprecated. Khi chuyển Boot3 → Boot4, phải đồng thời xử lý Spring Framework 7, starter modularization, `@MockBean` removal, Maven/Gradle/IDE test engines và test source discovery.

**Một chiến lược nâng cấp an toàn:** baseline test trên Boot3/JUnit5 → nâng Boot4/BOM đồng bộ → sửa APIs thực sự bị xóa → kiểm dependency tree và actual JUnit XML counts → chạy cả unit/Spring/integration tests. Nếu chưa chuyển Boot4, giữ JUnit5 theo Boot3 BOM cho tới khi có lý do và bằng chứng kiểm tương thích đầy đủ.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Managed Dependency Coordinates (JUnit Jupiter 5.12.2, Platform 1.12.2)](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot 3.4 — Managed Dependency Coordinates (Jupiter 5.11.4, Platform 1.11.4)](https://docs.spring.io/spring-boot/3.4/appendix/dependency-versions/coordinates.html)
- [Spring Boot 4.1 — Managed Dependency Coordinates (Jupiter/Platform 6.0.3)](https://docs.spring.io/spring-boot/4.1/appendix/dependency-versions/coordinates.html)
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 4.1 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 4 — Migration Guide, test module split, MockitoBean](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [JUnit 6 — User Guide / Getting Started](https://docs.junit.org/6.0.3/index.html)
- [JUnit 6 — Build Support, Gradle, Maven Surefire, BOM, launcher](https://docs.junit.org/6.0.3/running-tests/build-support.html)
- [JUnit 6 — Release Notes / API removals and Java 17 baseline](https://docs.junit.org/6.0.3/release-notes.html)
- [JUnit — Upgrading to JUnit 6.0 Migration Guide](https://github.com/junit-team/junit-framework/wiki/Upgrading-to-JUnit-6.0)
- [Spring Framework — @MockitoBean / @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Boot 4 — Core Testing](https://docs.spring.io/spring-boot/reference/testing/)
- [Gradle — Testing in Java Projects](https://docs.gradle.org/current/userguide/java_testing.html)