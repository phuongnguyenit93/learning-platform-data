# Source set hoặc JVM Test Suite cho integration test theo phiên bản Gradle

## 1. Mục tiêu và vấn đề

Trong module **Spring Boot - testing**, nhóm **Build và CI**, integration test khác unit test ở phạm vi phụ thuộc và thời gian thực thi. Unit test lý tưởng kiểm một class/hàm, dùng fixture trong bộ nhớ và chạy nhanh; integration test có thể khởi động `ApplicationContext`, profile riêng, database, HTTP server, Testcontainers hoặc broker. Để các nhóm có lifecycle và classpath tách biệt, Gradle cung cấp hai phương án:

1. **Source set + custom `Test` task:** tự tạo `sourceSets.integrationTest`, cấu hình dependency configurations, `testClassesDirs`, `classpath` và `useJUnitPlatform()`; hoạt động với những phiên bản Gradle cũ chưa có mô hình test suites.
2. **JVM Test Suite:** khai báo `integrationTest(JvmTestSuite)` trong `testing.suites`; Gradle tự tạo source set, configurations và Test task cho suite, sau đó bạn nối nó vào lifecycle `check`.

Hai phương án **thay thế nhau**, không cần cùng đăng ký một suite/task tên `integrationTest`. Bài hướng dẫn đầy đủ cả hai trên cùng Java code, nêu ranh giới hỗ trợ của Gradle/Spring Boot, cách khai báo runtime classpath, unit vs integration fixtures, lệnh CI, báo cáo, migration và lỗi khó phát hiện khi Gradle thay đổi phiên bản.

Kết quả cuối cùng mong muốn:

~~~text
./gradlew test             -> 3 unit tests trong src/test/java
./gradlew integrationTest  -> 4 integration tests trong src/integrationTest/java
./gradlew check            -> cả hai nhóm, tổng 7 JUnit methods

src/test/resources/fixtures/unit-only.txt
  -> có trong unit test runtime, không có trong integration runtime

src/integrationTest/resources/application-it.properties
  -> có trong integration runtime, không lọt vào production bootJar
~~~

**Quan trọng:** `@SpringBootTest` không tự làm lớp test chuyển từ `test` task sang `integrationTest` task; chính **source set hoặc suite** quyết định lớp Java thuộc nhóm nào.

## 2. Bảng tương thích theo phiên bản Gradle

| Gradle Wrapper | JVM Test Suite | Spring Boot Gradle plugin 3.5.16 | Khuyến nghị |
| --- | --- | --- | --- |
| Gradle 6.x, 7.0–7.2 | Chưa có | Không tương thích | Nếu ứng dụng dùng Boot cũ được hỗ trợ, dùng source set + Test task |
| Gradle 7.3–7.6.3 | Đã có từ **7.3**, incubating | Không thuộc mức hỗ trợ tối thiểu | Nâng Gradle/ghép đúng Boot version |
| **Gradle 7.6.4–7.6.x** | Có, vẫn incubating | **Được hỗ trợ** | Manual source set hoặc JVM suite, ưu tiên mức ổn định team cần |
| **Gradle 8.4–8.x** | Có, vẫn incubating | **Được hỗ trợ** | Cả hai; ví dụ chạy bằng **8.14.3** |
| Gradle 9.x | Có, API vẫn đánh dấu incubating | **Boot 3.5 không công bố hỗ trợ chính thức** | Kết hợp Spring Boot 4.x nếu muốn Gradle 9 |
| Gradle 8.14+ hoặc 9.x với Boot 4.x | Có | Spring Boot 4.x hỗ trợ cả hai dòng | Migrate rồi kiểm plugin/dependencies đầy đủ |

Hai nguồn quyết định là Gradle 7.3 release notes (giới thiệu declarative JVM Test Suite) và Spring Boot **3.5.16** system requirements (Gradle 7.x **7.6.4+** hoặc 8.x **8.4+**). Tài liệu Spring Boot 4.x hỗ trợ Gradle 8.x **8.14+** hoặc Gradle 9.x.

**Không suy ngược**: Gradle 7.3 có JVM Test Suite không đồng nghĩa Boot 3.5 có thể apply plugin trên Gradle 7.3; Gradle 9 có suites không đồng nghĩa Boot 3.5 được thử chính thức. Ngay trong Gradle 9 documentation, JVM Test Suite vẫn là **incubating API** có thể thay đổi.

Nếu dự án cũ thật sự phải chạy trên Gradle 6/đầu 7, chọn Spring Boot plugin/Java runtime tương thích riêng. Các build scripts Java 17 + Spring Boot 3.5 trong bài **không** dành cho những phiên bản đó.

## 3. Ba đối tượng cần phân biệt: SourceSet, Test task và JvmTestSuite

**SourceSet** mô tả Java classes, resources và compile/runtime classpath của một nhóm source. Java plugin mặc định tạo `main` và `test`, với các thư mục `src/main/java` và `src/test/java` cùng resource counterparts.

Khai báo `sourceSets.integrationTest` tạo thêm các cấu phần Gradle:

~~~text
compileIntegrationTestJava
processIntegrationTestResources
integrationTestClasses
integrationTestImplementation
integrationTestRuntimeOnly
integrationTestCompileClasspath
integrationTestRuntimeClasspath
~~~

Nhưng chỉ tạo source set **không tự tạo một Test task chạy JUnit**. Cần thêm:

~~~groovy
tasks.register('integrationTest', Test) {
    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath
    useJUnitPlatform()
}
~~~

Đây là **snippet**, không phải toàn bộ `build.gradle`.

**JvmTestSuite** là abstraction declarative gồm `SourceSet`, testing framework, dependencies và một hoặc nhiều targets. Khi khai báo:

~~~groovy
testing {
    suites {
        integrationTest(JvmTestSuite) {
            useJUnitJupiter()
        }
    }
}
~~~

Gradle tạo cấu hình tương ứng. Tuy nhiên **suite khác built-in `test` không tự có dependency tới production project**; phải khai báo `implementation project()`. Ngoài ra custom suite không tự được thêm vào `check`.

## 4. Quy ước dự án mẫu

Một project Java 17 Spring Boot 3.5.16 có cấu trúc:

~~~text
settings.gradle
build.gradle
gradle/wrapper/gradle-wrapper.properties
gradlew
gradlew.bat

src/main/java/com/example/buildci/
  BuildCiApplication.java
  GreetingService.java
src/main/resources/
  application.properties

src/test/java/com/example/buildci/
  GreetingUnitTest.java
src/test/resources/fixtures/
  unit-only.txt

src/integrationTest/java/com/example/buildci/
  GreetingSpringIntegrationTest.java
src/integrationTest/resources/
  application-it.properties
  fixtures/integration-only.txt
~~~

Tập mã **giống hệt** cho hai `build.gradle` khác nhau. Chỉ sử dụng **một** phương án build tại một thời điểm. Không cần Docker, broker hoặc database để minh họa tách tasks/classpath; integration test ở đây kiểm Spring bean discovery, profile property và resource visibility.

**`settings.gradle`:**

~~~groovy
rootProject.name = 'gradle-integration-suites-demo'
~~~

Chọn Wrapper Gradle **8.14.3** thuộc dòng 8.x được Boot 3.5 hỗ trợ. Từ môi trường đã có Gradle để khởi tạo wrapper:

~~~bash
gradle wrapper --gradle-version 8.14.3 --distribution-type bin
./gradlew --version
~~~

Windows PowerShell:

~~~powershell
gradle wrapper --gradle-version 8.14.3 --distribution-type bin
.\gradlew.bat --version
~~~

`gradle/wrapper/gradle-wrapper.properties` sẽ trỏ đến bản phân phối tương ứng, ví dụ:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
~~~

Giữ các cấu hình wrapper khác và checksum do project quản lý; commit cả `gradlew`, `gradlew.bat`, wrapper JAR và properties. CI phải chạy **./gradlew**, không chạy lệnh `gradle` của hệ thống với version khác repository.

## 5. Production application

**`src/main/java/com/example/buildci/BuildCiApplication.java`:**

~~~java
package com.example.buildci;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BuildCiApplication {

    public static void main(String[] args) {
        SpringApplication.run(BuildCiApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/buildci/GreetingService.java`:**

~~~java
package com.example.buildci;

import java.util.Objects;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final String prefix;

    public GreetingService(
            @Value("${demo.prefix:Default}") String prefix
    ) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank"
            );
        }
        return prefix + ", " + name.strip() + "!";
    }

    public String configuredPrefix() {
        return prefix;
    }
}
~~~

`GreetingService` không có mutable per-request state; test thuần Java có thể gọi `new GreetingService("Unit")`, còn integration test inject bean thực của Spring. Một `@Value` trên tham số constructor được Spring resolve khi tạo bean; khi khởi tạo thủ công, unit test truyền String tường minh.

**`src/main/resources/application.properties`:**

~~~properties
demo.prefix=Default
spring.main.banner-mode=off
~~~

Trong application mặc định, `GreetingService.greet("An")` trả `Default, An!`. Trong integration test bật profile `it`, file `application-it.properties` có precedence thích hợp để override prefix thành `Integration`.

Đừng đặt integration test config trong main resources: nếu làm vậy, file cấu hình test có thể lọt vào production executable JAR.

## 6. Unit tests trong src/test/java

**`src/test/java/com/example/buildci/GreetingUnitTest.java`:**

~~~java
package com.example.buildci;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class GreetingUnitTest {

    @Test
    void canRenderNameWithoutSpringContext() {
        GreetingService service =
                new GreetingService("Unit");

        assertThat(service.greet(" An "))
                .isEqualTo("Unit, An!");
    }

    @Test
    void rejectsBlankNameAtUnitBoundary() {
        GreetingService service =
                new GreetingService("Unit");

        assertThatThrownBy(() -> service.greet("   "))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("name must not be blank");
    }

    @Test
    void unitClasspathContainsOnlyUnitFixture() {
        assertThat(
                new ClassPathResource(
                        "fixtures/unit-only.txt"
                ).exists()
        ).isTrue();

        assertThat(
                new ClassPathResource(
                        "fixtures/integration-only.txt"
                ).exists()
        ).isFalse();
    }
}
~~~

Đây là **ba JUnit Jupiter test methods**. Lớp không dùng `@SpringBootTest`, không khởi động application context, và method đầu chỉ kiểm business behavior của một object tự tạo.

**`src/test/resources/fixtures/unit-only.txt`:**

~~~text
UNIT_ONLY
~~~

Classpath của built-in `test` source set có output/resources từ main và test, nhưng không tự có integrationTest source set outputs. Test thứ ba phát hiện trường hợp cấu hình vô tình đưa integration-only fixture vào unit runtime.

## 7. Integration tests trong src/integrationTest/java

**`src/integrationTest/java/com/example/buildci/GreetingSpringIntegrationTest.java`:**

~~~java
package com.example.buildci;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.core.io.ClassPathResource;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        classes = BuildCiApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("it")
class GreetingSpringIntegrationTest {

    @Autowired
    GreetingService greetingService;

    @Autowired
    ApplicationContext context;

    @Autowired
    Environment environment;

    @Test
    void usesIntegrationProfileConfiguration() {
        assertThat(environment.getProperty("demo.prefix"))
                .isEqualTo("Integration");
        assertThat(greetingService.configuredPrefix())
                .isEqualTo("Integration");
        assertThat(greetingService.greet(" An "))
                .isEqualTo("Integration, An!");
    }

    @Test
    void serviceReallyComesFromSpringContainer() {
        assertThat(context.getBean(GreetingService.class))
                .isSameAs(greetingService);
    }

    @Test
    void integrationClasspathContainsOnlyIntegrationFixture() {
        assertThat(
                new ClassPathResource(
                        "fixtures/integration-only.txt"
                ).exists()
        ).isTrue();

        assertThat(
                new ClassPathResource(
                        "fixtures/unit-only.txt"
                ).exists()
        ).isFalse();
    }

    @Test
    void rejectsBlankInputUsingConfiguredSpringBean() {
        assertThatThrownBy(
                () -> greetingService.greet("  ")
        ).isInstanceOf(IllegalArgumentException.class)
         .hasMessage("name must not be blank");
    }
}
~~~

**Bốn JUnit Jupiter methods** khởi động Spring Boot application context thật. Hai resource files trong integrationTest source set:

**`src/integrationTest/resources/application-it.properties`:**

~~~properties
demo.prefix=Integration
~~~

**`src/integrationTest/resources/fixtures/integration-only.txt`:**

~~~text
INTEGRATION_ONLY
~~~

Khi `@ActiveProfiles("it")` được Spring TestContext áp dụng, Spring Boot đọc profile-specific `application-it.properties` từ integrationTest runtime classpath và override giá trị main. Test này phản ánh **Spring configuration integration**, không giả vờ kiểm database/HTTP khi chưa dùng.

**Tính cách ly:** `src/integrationTest/resources` phải nằm trong runtimeClasspath của integration test, còn `src/test/resources` mặc định không nằm đó. Nếu bạn gắn `sourceSets.test.output` vào integrationTest classpath, assertion không có unit fixture sẽ FAIL; điều này là tín hiệu tốt cho code review.

## 8. Phương án A: source set + Test task truyền thống

Phương án A phù hợp khi dự án có custom build logic từ trước, cần tương thích với các phiên bản Gradle chưa có JVM Test Suite hoặc team không muốn phụ thuộc API incubating. Với Spring Boot 3.5, vẫn phải giữ Gradle 7.6.4+ (dòng 7) hoặc 8.4+ (dòng 8).

**`build.gradle` hoàn chỉnh, Groovy DSL, phương án A:**

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

// Source set thứ ba. Đường dẫn mặc định:
// src/integrationTest/java và src/integrationTest/resources.
sourceSets {
    integrationTest {
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}

// Kế thừa TEST LIBRARIES, không trộn output/classes
// hoặc resources của sourceSets.test vào integration.
configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.register('integrationTest', Test) {
    description = 'Runs Spring integration tests.'
    group = 'verification'

    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath
    useJUnitPlatform()

    shouldRunAfter(tasks.named('test'))
    maxParallelForks = 1
    systemProperty 'java.awt.headless', 'true'

    testLogging {
        events 'failed', 'skipped'
    }
}

tasks.named('check') {
    dependsOn(tasks.named('integrationTest'))
}
~~~

**Đây là một tập tin độc lập**. Không dán thêm phương án B vào script này.

### Tại sao mỗi dòng trên là cần thiết?

- `sourceSets.integrationTest` làm Gradle tạo compile task `compileIntegrationTestJava` và resource task `processIntegrationTestResources`.
- `compileClasspath += sourceSets.main.output` để Java tests import production `GreetingService`.
- `runtimeClasspath += sourceSets.main.output` để runtime nhìn thấy production classes và `application.properties`.
- `integrationTestImplementation.extendsFrom testImplementation` thừa hưởng dependency declarations từ unit tests như JUnit, AssertJ, Spring Boot starter-test, **không** có nghĩa tự thêm source output `src/test`.
- `integrationTestRuntimeOnly.extendsFrom testRuntimeOnly` đưa JUnit Platform launcher vào runtime.
- `testClassesDirs` và `classpath` là hai thông tin tối thiểu cho custom `Test` task; Gradle 9 còn nhấn mạnh phải gán tường minh.
- `useJUnitPlatform()` cần cho JUnit Jupiter khi tạo custom Test task.
- `shouldRunAfter` chỉ gợi ý thứ tự khi cả hai task có trong graph; không tự schedule `test`.
- `check.dependsOn` là kết nối **thực** để `./gradlew check` chạy integration tests.

### Phương án A nếu không muốn kế thừa toàn bộ test libraries

Nếu unit tests có rất nhiều thư viện mock/benchmark không dùng trong integration, hãy thay hai phần `configurations` và `dependencies` theo hướng khai báo riêng:

~~~groovy
configurations {
    integrationTestImplementation.extendsFrom implementation
    integrationTestRuntimeOnly.extendsFrom runtimeOnly
}

dependencies {
    integrationTestImplementation 'org.springframework.boot:spring-boot-starter-test'
    integrationTestRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
~~~

Đây là **biến thể tùy chọn**, không phải block bổ sung để dán vào full script mà không xóa cấu hình kế thừa cũ. Cần giữ đúng dependencies của production/IT và sourceSet classpaths; test starter dependency cần có version qua Spring Boot BOM/dependency-management plugin.

## 9. Phương án B: JVM Test Suite trên Gradle 8.x

Phương án B phù hợp dự án dùng Gradle mới và chấp nhận test suite API **incubating**. Java plugin trong Gradle mới cung cấp integration với JVM Test Suite. DSL khai báo một suite cùng testing framework, dependencies và target task; không tự tạo manual sourceSet/task cùng tên.

**`build.gradle` hoàn chỉnh, Groovy DSL, phương án B — THAY THẾ toàn bộ phương án A:**

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

testing {
    suites {
        test {
            useJUnitJupiter()
        }

        integrationTest(JvmTestSuite) {
            useJUnitJupiter()

            dependencies {
                // Không mặc nhiên nhìn thấy classes của project
                // trong một non-default JVM test suite.
                implementation project()

                implementation 'org.springframework.boot:spring-boot-starter-test'
                runtimeOnly 'org.junit.platform:junit-platform-launcher'
            }

            targets {
                all {
                    testTask.configure {
                        shouldRunAfter(tasks.named('test'))
                        maxParallelForks = 1
                        systemProperty 'java.awt.headless', 'true'
                        testLogging {
                            events 'failed', 'skipped'
                        }
                    }
                }
            }
        }
    }
}

tasks.named('check') {
    dependsOn(testing.suites.integrationTest)
}
~~~

**Đây là một tập tin độc lập** với cùng tên project, app, resources và JUnit tests ở các phần trước. `testing.suites.integrationTest` tự tạo source set, test task và dependency configurations.

Khác biệt đáng nhớ:

- Với custom `Test` task, gọi `useJUnitPlatform()`; với `JvmTestSuite`, gọi `useJUnitJupiter()` tại suite.
- Built-in `test` suite nhận production dependencies bằng convention; **integrationTest suite không tự nhận**, nên `implementation project()` cần được khai báo rõ.
- `integrationTest` suite không tự được add vào lifecycle `check`; cần `dependsOn(testing.suites.integrationTest)`.
- Test suite `dependencies { implementation ... }` là **scoped dependencies**, không phải global `dependencies`. Nó không tự kế thừa `testImplementation`.
- `targets.all { testTask.configure { ... } }` tùy biến `Test` task tương ứng mà suite tạo ra.
- Tránh `tasks.register('integrationTest', Test)` đồng thời: Gradle đã đăng ký task cho suite.

Gradle docs ghi chú JVM Test Suite cho các suites khác `test` mặc định thường dùng JUnit Jupiter, nhưng **khai báo tường minh** giúp người học nhìn ra contract và tránh phụ thuộc convention khi đọc build script.

## 10. Kiểm soát dependencies và classpath

| Nhu cầu | Source set manual A | JVM Test Suite B |
| --- | --- | --- |
| Production classes | `sourceSets.main.output` thêm vào compile/runtime | `implementation project()` |
| Spring Boot starter-test | Qua `integrationTestImplementation.extendsFrom testImplementation` hoặc khai báo riêng | Khai báo trong suite `dependencies` |
| JUnit Platform launcher | `integrationTestRuntimeOnly` kế thừa/được khai báo | Suite `runtimeOnly` tường minh |
| Test-only resource | `src/integrationTest/resources` | `src/integrationTest/resources` theo suite |
| Test classes runtime | `testClassesDirs = ...` | Suite tự wiring |
| JUnit Platform/Jupiter | `Test.useJUnitPlatform()` | `JvmTestSuite.useJUnitJupiter()` |
| Task registration | `tasks.register('integrationTest', Test)` | Suite auto tạo |
| Check lifecycle | `check.dependsOn integrationTest` | `check.dependsOn(testing.suites.integrationTest)` |

**Đặc biệt với Gradle 9:** Gradle thay đổi việc custom `Test` tasks mặc định được gán test source set/classpath. Không được dựng task trống rồi hy vọng Gradle tự suy ra. Ngay cả trên Gradle 8, gán explicit `testClassesDirs` và `classpath` làm build script rõ ràng hơn và tránh test detection im lặng sai.

Một số internal Gradle testing libraries trước Gradle 9 có thể bị leak vào runtime classpath, che việc thiếu JUnit Platform launcher; do đó khai báo launcher tường minh là thói quen tốt khi muốn nâng Gradle version.

### Cách xác định phụ thuộc thực sự được resolve

~~~bash
./gradlew dependencies --configuration integrationTestRuntimeClasspath
./gradlew dependencyInsight \
  --configuration integrationTestRuntimeClasspath \
  --dependency junit-jupiter-engine
~~~

Gradle suite và Spring Boot BOM đều có cơ chế version selection. Nếu JUnit artifacts bị lệch do pin cứng, hãy dùng `dependencyInsight` để xem resolved dependency graph, thay vì thêm một phiên bản JUnit tùy ý để “chạy được”.

## 11. shouldRunAfter không phải dependsOn

Ba cấu hình rất dễ nhầm:

~~~groovy
shouldRunAfter(tasks.named('test'))       // ưu tiên order nếu cả hai có trong graph
dependsOn(tasks.named('test'))            // lên lịch test như dependency
check.dependsOn(integrationTest)          // nối integration vào check
~~~

Các dòng là **snippet minh họa**, cú pháp `check.dependsOn(integrationTest)` chỉ hợp lệ khi đúng project scope/variables. Hai `build.gradle` hoàn chỉnh ở trên dùng `tasks.named('check')`.

Hành vi:

| Lệnh | Với cấu hình bài này |
| --- | --- |
| `./gradlew test` | Chạy unit; không tự chạy integrationTest |
| `./gradlew integrationTest` | Chạy integration; không tự chạy `test` chỉ vì shouldRunAfter |
| `./gradlew check` | Task graph có cả test và integrationTest |
| `./gradlew build` | Java build lifecycle gọi check, do đó có cả hai |
| `./gradlew test integrationTest` | Lên lịch cả hai; ưu tiên chạy test trước |
| `./gradlew integrationTest --tests "*SpringIntegrationTest"` | Filter class thuộc integration task |

`shouldRunAfter` thường được ưu tiên hơn `mustRunAfter` nếu chỉ muốn thực hiện unit tests trước IT khi cả hai task được schedule, vì Gradle vẫn có tính linh hoạt trong task scheduling. `dependsOn(test)` tạo dependency bắt buộc không cần thiết nếu mục tiêu chỉ là thứ tự và integration test có thể chạy độc lập.

Một CI muốn bỏ qua tests chậm khi chạy `./gradlew test` thì không nên nối integrationTest vào test task. Chỉ thêm vào `check` hoặc một CI verification stage phù hợp.

## 12. Source set mặc định, thư mục resources và tên task

Gradle Java plugin tự dùng convention:

~~~text
sourceSet name = integrationTest
src/integrationTest/java/
src/integrationTest/resources/
compileIntegrationTestJava
processIntegrationTestResources
integrationTestClasses
integrationTestImplementation
integrationTestRuntimeOnly
~~~

Trong phương án A, không cần thêm:

~~~groovy
java.srcDir 'src/integrationTest/java'
resources.srcDir 'src/integrationTest/resources'
~~~

nếu dùng đúng convention. Đây chỉ là snippet minh họa custom paths. Thêm paths chỉ khi project muốn đổi thư mục nguồn khác chuẩn.

Trong phương án B, suite `integrationTest(JvmTestSuite)` cũng sử dụng convention của source set cùng tên. Không cấu hình Java source directories trùng ở cả `sourceSets` và `testing.suites` gây khó hiểu.

### Khi không cần truy cập production Java classes trực tiếp

Một số black-box integration tests chỉ gọi HTTP endpoint đã được khởi động như tiến trình riêng. Khi đó không nhất thiết phải thêm production `classesDirs` vào compile classpath của test, nhưng vẫn cần runtime container/server trong CI. Ví dụ chính gọi `GreetingService` trực tiếp nên **cần** production code dependency.

## 13. Tách test fixtures khỏi runtime production

Bộ bài có ba nguồn resources:

~~~text
src/main/resources/application.properties
src/test/resources/fixtures/unit-only.txt
src/integrationTest/resources/application-it.properties
src/integrationTest/resources/fixtures/integration-only.txt
~~~

| Task/lifecycle | Có main resources? | Có unit resources? | Có integration resources? |
| --- | --- | --- | --- |
| `test` | Có | Có | Không |
| `integrationTest` | Có | Không mặc định | Có |
| `bootJar` application artifact | Có | Không mặc định | Không mặc định |

Hai test methods kiểm isolation theo logical path `fixtures/unit-only.txt` và `fixtures/integration-only.txt`. Nếu ai đó nối thêm `sourceSets.test.output` vào integration runtime, assertions của integration test sẽ phát hiện không còn cách ly như thiết kế.

**Không chép toàn bộ `src/test/resources` vào `BOOT-INF/classes`** chỉ để integration test thấy fixtures chung. Production packaging có thể vô tình chứa credential giả nhầm với thật, JSON fixtures, test-only profiles hoặc sample payloads.

Nếu có fixtures dùng chung thật sự, dùng `java-test-fixtures` plugin hoặc module test-support riêng.

## 14. Shared test fixtures không đồng nghĩa gộp source sets

Plugin `java-test-fixtures` cung cấp `src/testFixtures/java` và variant dùng chung được qua `testFixtures(project())`.

Ví dụ **snippet**:

~~~groovy
plugins {
    id 'java'
    id 'java-test-fixtures'
}
~~~

Sau đó với JVM suite:

~~~groovy
testing {
    suites {
        integrationTest(JvmTestSuite) {
            dependencies {
                implementation project()
                implementation testFixtures(project())
            }
        }
    }
}
~~~

Không dán nguyên một `plugins` block thứ hai vào `build.gradle` chính mà chưa hợp nhất. Mẫu đầy đủ hiện chưa cần test fixtures. Khi dùng, phân biệt `testFixturesApi` (lộ compile-time API dependencies cho consumers) với `testFixturesImplementation` (implementation-only), để tránh làm lớn compile classpath không cần.

Nếu helper cần ở cả unit và integration, test fixtures/module phụ trợ tốt hơn một import ngược từ `src/integrationTest/java` tới `src/test/java` hoặc copy toàn bộ test outputs.

## 15. Cách verify Gradle thực sự chạy đúng tests

Chạy task graph:

~~~bash
./gradlew --version
./gradlew tasks --all
./gradlew check --dry-run
./gradlew test integrationTest --rerun-tasks
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat tasks --all
.\gradlew.bat check --dry-run
.\gradlew.bat test integrationTest --rerun-tasks
~~~

**`--dry-run` chỉ hiển thị task graph, không chạy JUnit.** Với build cache/up-to-date checks, `BUILD SUCCESSFUL` có thể xảy ra mà các test tasks không thực thi lại. Dùng `--rerun-tasks` khi cần QA actual execution.

Gradle thường xuất JUnit XML và HTML riêng theo task:

~~~text
build/test-results/test/
build/reports/tests/test/

build/test-results/integrationTest/
build/reports/tests/integrationTest/
~~~

Trong project mẫu, kỳ vọng **3 unit methods + 4 integration methods**. Kiểm số testcases trong XML hoặc HTML report, không chỉ nhìn status tổng. Nếu task hiện `NO-SOURCE` hoặc `SKIPPED`, đó **không** phải bằng chứng integration đã được kiểm.

### Lọc test theo từng task

~~~bash
./gradlew test --tests "com.example.buildci.GreetingUnitTest"
./gradlew integrationTest --tests "com.example.buildci.GreetingSpringIntegrationTest"
./gradlew integrationTest --tests "*.GreetingSpringIntegrationTest"
~~~

`--tests` không tự thêm classes từ một source set khác. `./gradlew test --tests "*SpringIntegrationTest"` có thể báo không tìm thấy class vì nó không nằm trong `src/test/java`. Điều đó phản ánh tách nhóm đúng.

## 16. Khi nào dùng @Tag thay cho source set?

JUnit Jupiter có `@Tag("integration")`. Nếu tests ít, cùng dependencies/resources và chỉ muốn loại nhóm chậm khỏi một lần chạy, có thể cấu hình Test tasks lọc tag. Nhưng tag **không tách compile classpath/resources**:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        excludeTags 'integration'
    }
}
~~~

Đây là snippet minh họa, không có trong build đầy đủ. Nó chỉ lọc execution bên trong **test source set**; integration tests vẫn được compile cùng unit tests và các resource/dependencies vẫn có thể lẫn.

Dùng source set/JVM suite khi cần:
- Runtime dependencies khác nhau, ví dụ Testcontainers hoặc web server.
- CI stage và report riêng.
- Profile `application-it.properties` không leak vào unit tests.
- Integration tests có JVM heap/concurrency/timeouts khác.
- Muốn giới hạn Docker dependency khỏi fast unit `test`.
- Cần xác nhận đúng tập tests được chạy qua task names rõ ràng.

Không bắt buộc mọi dự án phải có nhiều suites; đây là lựa chọn theo lifecycle và hợp đồng dự án.

## 17. Cấu hình JVM riêng cho integration tests

Integration tests có thể cần heap/timezone/fork policies khác unit. Với manual Test task:

~~~groovy
tasks.named('integrationTest', Test) {
    maxHeapSize = '1g'
    maxParallelForks = 1
    systemProperty 'user.timezone', 'UTC'
    jvmArgs '-Dfile.encoding=UTF-8'
}
~~~

Đây là **snippet bổ sung**, có thể đặt trong full phương án A. Với JVM suite, đưa các settings vào:

~~~groovy
testing {
    suites {
        integrationTest(JvmTestSuite) {
            targets {
                all {
                    testTask.configure {
                        maxHeapSize = '1g'
                        maxParallelForks = 1
                        systemProperty 'user.timezone', 'UTC'
                    }
                }
            }
        }
    }
}
~~~

Đây là snippet chỉnh sửa **existing suite block** của B, không đăng ký thêm suite cùng tên. Testcontainers/embedded Kafka có thể ngốn RAM/CPU đáng kể; `maxParallelForks` nhân với concurrent Gradle tasks và CI shards có thể vượt capacity runner.

Không dùng `maxParallelForks=1` như bằng chứng JUnit parallel bị tắt: JUnit engine vẫn có thể chạy tests song song trong một fork nếu `junit-platform.properties` bật chế độ đó. Phải thiết kế test isolation phù hợp hoặc tắt/chia nhóm song song có chủ đích.

## 18. Khi dùng Testcontainers trong integrationTest

Một Spring `@SpringBootTest` khởi động context thật chưa chắc cần Docker. Khi integration cần PostgreSQL/Kafka, chỉ khai báo Testcontainers trong **integrationTest dependencies**, không buộc unit tests kéo toàn bộ container libraries.

Phương án A, snippet bổ sung:

~~~groovy
dependencies {
    integrationTestImplementation 'org.testcontainers:junit-jupiter'
    integrationTestImplementation 'org.testcontainers:postgresql'
    integrationTestRuntimeOnly 'org.postgresql:postgresql'
}
~~~

Phương án B, thay/chỉnh `integrationTest.dependencies`:

~~~groovy
testing {
    suites {
        integrationTest(JvmTestSuite) {
            dependencies {
                implementation project()
                implementation 'org.springframework.boot:spring-boot-starter-test'
                implementation 'org.testcontainers:junit-jupiter'
                implementation 'org.testcontainers:postgresql'
                runtimeOnly 'org.postgresql:postgresql'
            }
        }
    }
}
~~~

**Các đoạn trên không thuộc build Greeting demo và không phải một build script độc lập.** Versions của Testcontainers artifacts có thể đổi theo major; dùng Spring Boot BOM hoặc platform constraints tương ứng. Để dùng `@ServiceConnection` trong Spring Boot 3.5 còn cần `spring-boot-testcontainers` trong integrationTest dependencies. Không tự giả `spring-boot-starter-test` mang đủ Testcontainers support.

Trong CI:
1. Runner phải có Docker/container runtime được Testcontainers hỗ trợ.
2. Test cần startup/readiness timeout hữu hạn, tránh phụ thuộc public production services.
3. Container có lifecycle owner và cleanup.
4. Database/schema/topic IDs độc lập khi test parallel.
5. Kiểm credential/secret handling của CI, không cho untrusted PR chạy production secrets.
6. Limit concurrent test JVM/container count.
7. Dùng backend giống production khi business dựa vào DB locking/constraints, không suy từ H2.

## 19. GitHub Actions: một CI workflow dùng được cho hai phương án

**`.github/workflows/verify.yml` — ví dụ minh họa:**

~~~yaml
name: verify

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - uses: gradle/actions/setup-gradle@v4

      - name: Run both test groups
        run: ./gradlew --no-daemon clean check

      - name: Upload XML and HTML reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: gradle-test-results
          path: |
            build/test-results/test/
            build/test-results/integrationTest/
            build/reports/tests/test/
            build/reports/tests/integrationTest/
          if-no-files-found: warn
~~~

Đây là mẫu workflow có thể copy chỉnh sửa, nhưng phải kiểm GitHub Actions policy, action versions và secret permissions theo tổ chức. Nó dùng Gradle Wrapper trong repository và JDK 17.

Trong dự án thật:
- Fast PR lane có thể chỉ gọi `./gradlew test`.
- Required integration lane gọi `./gradlew integrationTest` hoặc `check`.
- Với Docker/Testcontainers, runner cần cấu hình hỗ trợ.
- Nếu integration là required check, đừng dùng `continue-on-error: true` rồi coi pipeline PASS.
- Upload XML/HTML khi fail bằng `if: always()` giúp chẩn đoán.
- Không chỉ upload report unit và quên `integrationTest`.
- Khi tách jobs, cần share/build lại artifact đúng, không dựa vào process-local H2 của job khác.

## 20. Gradle 9 và sự thay đổi test runtime

Với Gradle 9:
- Gradle daemon yêu cầu JDK 17+.
- Custom `Test` task không nên dựa vào ngầm định test source set; cần explicit `testClassesDirs`/`classpath`.
- JUnit Platform launcher phải có trên test runtime classpath; trước Gradle 9 có hiện tượng internal dependencies leak làm mất lỗi cấu hình.
- JVM Test Suite vẫn là incubating DSL theo tài liệu hiện tại; đọc release/upgrade guides.
- Spring Boot 3.5 **không công bố Gradle 9 support**; Spring Boot 4.x plugin có, cần migration/version alignment.

Không có đường tắt “chỉ thay Wrapper URL” rồi coi mọi thứ được xác nhận. Upgrade cần kiểm `gradlew help`, plugin graph, compile, `test`, `integrationTest`, reports, sourceSets, JaCoCo/publishing và CI task graph.

**Lưu ý về JVM toolchain:** JDK dùng để chạy Gradle daemon, JDK compile Java 17 và JDK test runtime là các khái niệm khác nhau; Gradle Java toolchain cho phép điều khiển một số tầng. Bài chọn JDK 17 chung để dễ tái hiện, không khẳng định Gradle mọi phiên bản đều chạy được trên mọi JDK.

## 21. Test task orchestration và báo cáo coverage

Một dự án có thể dùng `shouldRunAfter` để ưu tiên unit tests trước integration trong `check`. Nhưng `shouldRunAfter` không ép Gradle chạy unit nếu người dùng chỉ gọi `integrationTest`. Khi cần cả hai trong CI, dùng `check` đã nối hoặc gọi tường minh hai tasks.

JaCoCo/test coverage là trách nhiệm bổ sung:
- `jacocoTestReport` mặc định thường tập trung vào built-in `test`.
- Một `integrationTest` custom task có execution data riêng, nhưng không mặc định có báo cáo coverage gộp đúng cho cả hai.
- Nếu KPI yêu cầu coverage tổng, cấu hình `JacocoReport`/report aggregation với đúng execution data và source dirs.
- Không đè `reports.junitXml.outputLocation` của hai tasks lên cùng một thư mục.
- Test results có thể được cache hoặc up-to-date; không suy rằng mỗi `build SUCCESSFUL` là một lần thực thi integration mới.

Để QA build wiring, có thể chạy:

~~~bash
./gradlew check --dry-run
./gradlew test integrationTest --rerun-tasks
./gradlew dependencyInsight --configuration integrationTestRuntimeClasspath --dependency junit-jupiter-engine
~~~

Không gọi `--dry-run` là integration test đã PASS; nó chỉ chứng minh task graph được dựng.

## 22. Context cache, transaction và test isolation

Tách unit và integration task có thể khiến chúng chạy ở các forked JVMs khác nhau, nhưng **không tự** cách ly mọi resource:

- Trong cùng `integrationTest` JVM, Spring TestContext cache `ApplicationContext` giữa test classes tương đương.
- Spring singleton bean có mutable state vẫn có thể leak giữa integration methods.
- `@MockitoBean`/`@DirtiesContext` cần chú ý parallel test policy.
- Embedded HTTP server/`@Async` worker chạy thread khác, nên `@Transactional` trên JUnit test method không bảo đảm rollback DB write từ worker.
- H2 in-memory với URL cùng tên có thể chia sẻ state trong một JVM/context.
- Docker PostgreSQL/Kafka/Redis bên ngoài JVM có thể được cả nhiều forks/CI shards dùng chung.
- Một test gọi global `TRUNCATE`/cache.clear()` có thể phá test đang chạy song song.

Biện pháp tốt: unique IDs/schema/tenant per test, cleanup chỉ dữ liệu test sở hữu, await background work trước cleanup, test containers có scope, và giới hạn parallelism phù hợp. Source set separation giải quyết **build/test lifecycle**, không tự tạo business data isolation.

## 23. Những lỗi thường gặp khi cấu hình sai

| Triệu chứng | Nguyên nhân | Giải pháp |
| --- | --- | --- |
| `integrationTest` không tồn tại | Chỉ có source set, quên Test task | Register custom Test hoặc dùng JVM suite |
| Gradle báo duplicate task `integrationTest` | Đăng ký cả manual Test và suite | Chọn một phương án |
| `compileIntegrationTestJava NO-SOURCE` | Java file đặt nhầm path | `src/integrationTest/java` |
| Không tìm thấy `GreetingService` | Thiếu main output/project dependency | A: add main.output; B: implementation project() |
| Không tìm thấy `@SpringBootTest` | Thiếu starter-test trong IT compile classpath | Add đúng scope |
| Không có JUnit Platform launcher | Missing runtimeOnly/Gradle9 change | Thêm launcher |
| Test build được nhưng không discover | Sai testClassesDirs/useJUnitPlatform/filter | Kiểm Test task, XML count |
| `Integration` không xuất hiện | `application-it.properties` không trên IT runtime | processIntegrationTestResources/classpath |
| Unit fixture xuất hiện trong IT | Trộn sourceSets.test.output | Tách outputs, dùng testFixtures |
| `./gradlew test` không chạy IT | Đúng source set separation | `integrationTest`/`check` |
| `./gradlew check` không chạy IT | Thiếu check dependsOn | Attach lifecycle |
| `shouldRunAfter` bị hiểu như dependency | Ordering chỉ áp khi cả hai tasks schedule | Dùng dependsOn khi cần |
| Plugin Boot từ chối Gradle version | Không đúng compatibility matrix | Pin Wrapper/Boot phù hợp |
| `testing.suites` không biết JvmTestSuite | Gradle cũ dưới 7.3 hoặc DSL sai | Upgrade hoặc manual source set |
| Gradle 9 custom Test thiếu lớp | Không còn ngầm test source set | Explicit classpath/classesDirs |
| Gradle 9 + Boot 3.5 crash | Cặp version chưa được support | Boot 4 compatible hoặc Gradle 8 |
| Test reports trống | Test tasks skipped/NO-SOURCE | Verify paths, --rerun-tasks |
| Unit stage yêu cầu Docker | Integration tests đang đặt trong src/test | Chuyển đúng source set |
| CI dùng system Gradle | Local/CI version khác nhau | ./gradlew |
| Testcontainers fail vì thiếu Docker | CI runner thiếu engine/permission | Chuẩn bị runner, readiness, timeout |
| Test outcomes khác theo parallel | Shared DB/bean/static states | Unique IDs, cleanup, grouping |
| Khai báo dependencies ở sai suite | Unit và IT có classpath khác | dependencyInsight đúng configuration |

Không chữa mọi lỗi bằng cách nối `sourceSets.test.output` vào integrationTest classpath. Việc đó xóa ranh giới và có thể làm test PASS giả nhờ resource không được đóng gói.

## 24. Checklist trước khi merge build/CI

- [ ] Gradle Wrapper version được pin và phù hợp Spring Boot plugin version?
- [ ] Nếu Gradle dưới 7.3, không sử dụng JVM Test Suite DSL?
- [ ] Nếu Boot 3.5, đang dùng Gradle 7.6.4+/8.4+ và không mặc định Gradle 9?
- [ ] Chỉ có một phương án A/B đăng ký integrationTest?
- [ ] `src/test/java` chứa unit tests, `src/integrationTest/java` chứa integration?
- [ ] `src/integrationTest/resources` chứa profile và fixtures riêng, không ở main?
- [ ] Manual Test task có explicit classesDirs/classpath/useJUnitPlatform?
- [ ] JVM suite có implementation project() và starter-test dependency đúng scope?
- [ ] JUnit Platform launcher được khai báo trực tiếp, dependencies không lệch version?
- [ ] `test` và `integrationTest` tìm đúng 3/4 methods như fixture mẫu?
- [ ] `./gradlew check` schedule cả hai tasks?
- [ ] `shouldRunAfter` không bị hiểu nhầm là dependsOn?
- [ ] `--rerun-tasks`/XML reports được dùng để xác nhận lần chạy thật?
- [ ] Unit fixture không thấy ở integration runtime và ngược lại?
- [ ] Test-only resources không xuất hiện trong bootJar?
- [ ] CI chạy wrapper thay vì system Gradle?
- [ ] Testcontainers cần thiết đã ở đúng suite dependency?
- [ ] Runner có Docker/DB/broker cho IT thật?
- [ ] Test data namespace/cleanup có chịu được concurrency và CI shards?
- [ ] Source sets/shared fixtures không vô tình chứa credentials?
- [ ] Java/Gradle plugin/third-party plugin compatibility đã được đánh giá khi migrate?
- [ ] JaCoCo và HTML/XML reports không trùng output directories?
- [ ] Không gọi `BUILD SUCCESSFUL` là 7 tests chạy khi tasks bị SKIPPED/UP-TO-DATE?
- [ ] Không tuyên bố code đã compile/run nếu mới chỉ review nội dung?

## 25. Lệnh chạy và kết quả dự kiến

Dùng Gradle Wrapper và JDK 17. Từ thư mục chứa `build.gradle` cùng Java/resources ở mục 4–7:

~~~bash
./gradlew --version
./gradlew clean test
./gradlew clean integrationTest
./gradlew clean check

./gradlew test --tests "com.example.buildci.GreetingUnitTest"
./gradlew integrationTest --tests "com.example.buildci.GreetingSpringIntegrationTest"

./gradlew test integrationTest --rerun-tasks
./gradlew check --dry-run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test
.\gradlew.bat clean integrationTest
.\gradlew.bat clean check

.\gradlew.bat test --tests "com.example.buildci.GreetingUnitTest"
.\gradlew.bat integrationTest --tests "com.example.buildci.GreetingSpringIntegrationTest"

.\gradlew.bat test integrationTest --rerun-tasks
.\gradlew.bat check --dry-run
~~~

Kỳ vọng theo cấu trúc và assertions:

| Command | Expected count | Bài kiểm thử |
| --- | ---: | --- |
| `./gradlew test` | **3** | GreetingUnitTest |
| `./gradlew integrationTest` | **4** | GreetingSpringIntegrationTest |
| `./gradlew check` | **7** tổng | test + integrationTest |
| `./gradlew build` | **7** tổng nếu check không bị bỏ | Java build lifecycle |
| `test --tests "...GreetingUnitTest"` | 3 | Chỉ task test |
| `integrationTest --tests "...GreetingSpringIntegrationTest"` | 4 | Chỉ task integrationTest |

Kỳ vọng output logic:

~~~text
Unit: new GreetingService("Unit").greet(" An ") = "Unit, An!"
Unit: unit-only fixture present, integration-only fixture absent
Unit: blank input -> IllegalArgumentException

Integration: @ActiveProfiles("it") -> demo.prefix = Integration
Integration: greetingService.greet(" An ") = "Integration, An!"
Integration: @Autowired service = ApplicationContext bean
Integration: integration-only fixture present, unit-only fixture absent
Integration: blank input -> IllegalArgumentException
~~~

Đây là **kết quả kỳ vọng của code**, **không phải logs Gradle/JUnit thực tế**. Mã được rà soát với Gradle/JUnit/Spring API chính thức nhưng **chưa compile hoặc chạy `gradlew` trong quá trình biên soạn**. Nếu bạn dùng Gradle/Spring Boot version khác, kiểm compatibility, plugin versions và chạy CI trước khi tuyên bố passed thực tế.

## 26. Kết luận và tài liệu chính thức

**Không có một cú pháp duy nhất tốt nhất cho mọi Gradle version.** Với Gradle cũ hoặc muốn build logic tường minh, dùng manual source set + Test task. Với Gradle 7.3+ và team chấp nhận incubating API, JVM Test Suite làm cấu hình gọn hơn. Đừng quên **Spring Boot plugin compatibility**: Boot 3.5.16 chính thức hỗ trợ Gradle 7.6.4+/8.4+ (trong dòng 7/8), còn muốn Gradle 9 nên dùng Spring Boot 4.x đã công bố hỗ trợ.

Sáu quy tắc cần nhớ:

1. JVM Test Suite được giới thiệu ở **Gradle 7.3**, nhưng chưa mặc nhiên stable.
2. Manual Test task cần **testClassesDirs + classpath + useJUnitPlatform**.
3. Non-default JVM suite cần **implementation project()**, cùng test deps phù hợp.
4. `shouldRunAfter` **không** đưa task vào graph; `check.dependsOn(integrationTest)` mới làm điều đó.
5. Source set riêng là ranh giới **classpath/CI**, không phải bảo vệ shared database hay global state.
6. Kiểm **JUnit XML test count**, report paths, wrapper version và packaged resources để xác nhận build chạy đúng.

### Tài liệu chính thức

- [Gradle 7.3 Release Notes — giới thiệu JVM Test Suite](https://docs.gradle.org/7.3/release-notes.html)
- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html)
- [Gradle — Testing in Java & JVM projects / integration tests](https://docs.gradle.org/current/userguide/java_testing.html#sec:configuring_java_integration_tests)
- [Gradle — Java Plugin và SourceSet](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle — Java Test Fixtures](https://docs.gradle.org/current/userguide/java_testing.html#sec:java_test_fixtures)
- [Gradle — Upgrading to Gradle 9](https://docs.gradle.org/current/userguide/upgrading_major_version_9.html)
- [Gradle — Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Spring Boot 3.5.16 — Gradle Plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/)
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 4.x — Gradle 9 support](https://docs.spring.io/spring-boot/gradle-plugin/)
- [Spring Boot 3.5 — Spring Boot Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [JUnit Jupiter — Build Support](https://docs.junit.org/current/user-guide/#running-tests-build-gradle)