# Tạo integration test và gắn vào lifecycle có chủ đích trong Gradle

## 1. Vấn đề: kiểm thử tích hợp không đơn thuần là “nhiều unit test hơn”

Trong một project Java, Gradle thường có task `test` để chạy những test thuộc `src/test/java`. Nhưng khi phần mềm có nhiều lớp/phần tương tác với nhau — ví dụ service → repository → filesystem/database, API → HTTP client → server hoặc ứng dụng → message broker — bạn cần thêm **integration tests** để kiểm tra sự phối hợp thực tế.

Integration test thường:

- Mất thời gian hơn unit test.
- Cần cấu hình riêng về dependencies, environment variables, ports, tài nguyên hoặc test fixtures.
- Phải cách ly dữ liệu và dọn tài nguyên sau test.
- Không nên bị lẫn vào các vòng chạy unit test nhanh.
- Chỉ được đưa vào lifecycle `check`/`build` sau khi team xác định rõ chính sách chạy local và CI.

Chủ đề bài học là **tạo một suite integration test riêng trong Gradle và nối nó vào lifecycle một cách có chủ đích**. Nó bao gồm hai cách triển khai hợp lệ:

1. **JVM Test Suite plugin**: DSL `testing { suites { ... } }` hiện đại, tiện quản lý nguồn, dependencies, testing framework và task. API này vẫn được Gradle đánh dấu *incubating*, nên cần đối chiếu phiên bản Gradle Wrapper.
2. **SourceSet + Test task thủ công**: khai báo `sourceSets.create("integrationTest")`, configurations, classpath và `tasks.register<Test>("integrationTest")`. Phù hợp khi cần kiểm soát chi tiết hoặc tránh phụ thuộc một DSL incubating.

Hai cách là **các lựa chọn thay thế**, không áp dụng đồng thời vào một project vì sẽ tạo trùng source set/task `integrationTest`.

### Mục tiêu đạt được

Sau bài học, bạn sẽ biết phân biệt integration test với unit/functional/E2E test; tạo `src/integrationTest/java`; dùng JUnit Jupiter; quản lý integration-only dependencies; hiểu quan hệ `check`/`build`/`test`/`integrationTest` và khác biệt `dependsOn`, `shouldRunAfter`, `mustRunAfter`; chủ động bật/tắt trong pipeline; kiểm tra log, reports và giải quyết lỗi classpath hoặc test discovery.

## 2. Phân biệt những cấp độ test

| Loại | Trọng tâm | Ví dụ | Thời điểm thường chạy |
| --- | --- | --- | --- |
| **Unit test** | Một đơn vị xử lý, cô lập I/O bằng fake/mock. | Service chuẩn hóa text với in-memory repository. | Trên mỗi commit, ngay khi phát triển. |
| **Integration test** | Các component thật tương tác qua ranh giới. | Service lưu và đọc lại dữ liệu qua file repository; DB repository + database. | CI thích hợp, có thể chạy local khi cần. |
| **Functional test** | Một hành vi người dùng hoặc chức năng ở mức hệ thống. | Gọi ứng dụng qua HTTP rồi kiểm tra business result. | Pipeline xác minh chức năng. |
| **End-to-end (E2E)** | Luồng hoàn chỉnh qua nhiều dịch vụ/phần môi trường. | Browser → gateway → service → DB. | Pipeline với environment kiểm soát. |
| **Gradle plugin functional test** | Build thử bằng Gradle TestKit. | Tạo test project và gọi `GradleRunner`. | Khi phát triển Gradle plugin; khác integration test của ứng dụng Java. |

Tên gọi có thể khác theo team; một test dùng filesystem thật nhưng không cần Docker vẫn có thể là integration test nếu nó xác minh **mối tương tác giữa component và adapter lưu trữ thật**.

**Đừng lấy thời gian chạy làm tiêu chí duy nhất:** một integration test chạy 50 ms vẫn là integration test về phạm vi. Mục tiêu phân chia là để quản trị dependencies, isolation, reporting và lifecycle rõ ràng.

## 3. Bốn đối tượng cần tách biệt trong Gradle

1. **Source set** `integrationTest`: quy ước vị trí file Java/resources, đầu ra biên dịch và các configurations classpath.
2. **Dependencies**: JUnit libraries, project production outputs, DB drivers, HTTP testing libraries hoặc test fixtures mà integration test cần.
3. **Task `integrationTest`** (kiểu `Test`): chọn test classes, runtime classpath và testing framework để chạy.
4. **Lifecycle task `check`**: không tự biết integrationTest do bạn tạo; phải quyết định có `dependsOn` suite/task đó hay không.

Ví dụ cây:

```text
src/
├── main/
│   ├── java/           # Production code
│   └── resources/
├── test/
│   ├── java/           # Unit tests, task test
│   └── resources/
└── integrationTest/
    ├── java/           # Integration tests, task integrationTest
    └── resources/      # Dữ liệu riêng, nếu có
```

**Cùng tên “integrationTest” ở các đối tượng khác nhau không có nghĩa chúng tự xuất hiện đồng thời.** JVM Test Suite tạo source set và task theo mô hình suite; nếu tạo `SourceSet` thủ công, bạn phải tự đăng ký một `Test` task để chạy test.

## 4. Vòng đời Java plugin: check, build, test và integrationTest

Với Java/Application plugin, các lifecycle tasks quan trọng thường là:

- `compileJava`: compile production Java.
- `test`: chạy unit tests ở built-in test source set.
- `check`: thực hiện các verification tasks được nối vào nó. Java plugin nối `test` vào `check`.
- `assemble`: tạo đầu ra package/artifact; không đồng nghĩa chạy mọi test.
- `build`: lifecycle tổng hợp, thường phụ thuộc cả `assemble` và `check`.
- `integrationTest`: task tùy biến, không mặc nhiên chạy cùng `check` trừ khi được nối.

Sau khi định nghĩa rõ `check.dependsOn(integrationTest)`, mô hình đơn giản sẽ là:

```text
                ./gradlew build
                       |
              +--------+--------+
              |                 |
           assemble            check
                                |
                         +------+------+
                         |             |
                        test     integrationTest
                           \         /
                      shouldRunAfter(test)
                         (thứ tự mềm)
```

Sơ đồ chỉ mô tả phụ thuộc/lifecycle; Gradle có thêm task như `classes`, `jar`, `compileTestJava`, `compileIntegrationTestJava` và các task sinh resources. Quan hệ `shouldRunAfter(test)` thuộc về integrationTest, không phải một đường `dependsOn` ngược.

### 4.1. Ba khái niệm task graph phải tách biệt

| Cú pháp | Ý nghĩa | Tự làm task kia chạy? |
| --- | --- | --- |
| `dependsOn(taskB)` trên taskA | TaskA cần TaskB hoàn thành trước khi chạy. | **Có**, TaskB tham gia graph khi TaskA được chọn. |
| `shouldRunAfter(taskB)` trên taskA | Nếu cả hai cùng tham gia graph, ưu tiên A sau B khi khả thi. | **Không**. |
| `mustRunAfter(taskB)` trên taskA | Nếu cả hai cùng tham gia graph, bắt buộc A sau B. | **Không**. |
| `finalizedBy(cleanupTask)` | Lập lịch finalizer sau task chính cho cleanup phù hợp. | Có, về mục đích finalization, nhưng **không** là thay thế cho dependency check/test. |

**Tình huống sai thường gặp:**

```kotlin
tasks.named("integrationTest") {
    shouldRunAfter(tasks.named("test"))
}
```

Đoạn này chỉ yêu cầu thứ tự **nếu cả hai được chọn**. Nó không làm `./gradlew test` tự chạy `integrationTest`, cũng không làm `./gradlew check` tự chạy integration test nếu bạn chưa thêm `dependsOn` vào `check`.

Gradle docs khuyến nghị `shouldRunAfter` thay vì `mustRunAfter` cho trường hợp test tích hợp nên chạy sau unit test vì nó cho Gradle linh hoạt hơn khi thực thi song song. Cả hai **không phải dependency edges**.

## 5. Hướng A — JVM Test Suite plugin (khuyến nghị khi phù hợp Gradle version)

JVM Test Suite plugin có ID `jvm-test-suite`, được áp dụng tự động cùng Java plugin ở các Gradle versions hỗ trợ. Với `java` hoặc `application` bạn có thể dùng extension `testing` để khai báo suites.

**Trạng thái:** Gradle vẫn đánh dấu API `JvmTestSuite` là *incubating*. Khi cần hỗ trợ nhiều Gradle releases, đọc tài liệu của **Gradle Wrapper thực tế**, không copy DSL của bản mới vào Wrapper cũ rồi kết luận logic sai.

### 5.1. Vì sao dùng suite thay vì register Test trống?

Khai báo:

```kotlin
testing {
    suites {
        register<JvmTestSuite>("integrationTest") {
            useJUnitJupiter("5.11.4")
            dependencies {
                implementation(project())
            }
        }
    }
}
```

tạo một suite có source set `integrationTest`, configurations tương ứng, một target mặc định và `Test` task cùng tên `integrationTest`. Framework `useJUnitJupiter("5.11.4")` giúp cấu hình test execution và các dependencies JUnit cần thiết.

Khác biệt rất quan trọng:

- Built-in suite `test` được nối với production code/dependencies theo quy ước của Java plugin.
- **Suite `integrationTest` bổ sung không tự nhận production output/dependencies**. Bạn phải khai báo `dependencies { implementation(project()) }` nếu test này cần gọi trực tiếp mã của chính project.
- Custom suite **không tự được nối vào `check`**. Muốn chạy khi `check` chạy thì khai báo dependency rõ.
- Mỗi suite có configurations như `integrationTestImplementation`, `integrationTestRuntimeOnly`, `integrationTestCompileClasspath` và `integrationTestRuntimeClasspath`, nhưng bạn thường không phải tự tạo.

### 5.2. Version JUnit có thể cố định

Có thể dùng `useJUnitJupiter()` để Gradle chọn version mặc định, hoặc `useJUnitJupiter("5.11.4")` để bài thực hành dùng version cụ thể. Đây là **version minh họa được pin**, không phải tuyên bố nó là bản JUnit mới nhất.

Framework ở cấp `JvmTestSuite` khác `Test.useJUnitPlatform()`: `useJUnitJupiter(...)` **vừa thêm các framework dependencies thích hợp vừa cấu hình task chạy chúng**. Với các `Test` tasks tự tạo bằng tay, bạn phải khai báo dependencies và gọi `useJUnitPlatform()` riêng.

## 6. Bài thực hành hoàn chỉnh — ứng dụng Java 17 có unit test và integration test

Bài lab này tạo một service chuẩn hóa nội dung và lưu vào repository. Unit test dùng in-memory fake repository; integration test dùng **filesystem thật trong thư mục tạm riêng** và kiểm tra dữ liệu vẫn đọc được qua một repository instance mới.

Không cần Docker hoặc PostgreSQL để thấy đúng ý nghĩa test tích hợp. Bài lab cần JDK 17/toolchain, Gradle Wrapper phù hợp, và lần đầu có Maven Central/cached artifacts cho JUnit 5.

### 6.1. Cây file

```text
gradle-integration-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    ├── main/java/demo/
    │   ├── TaskRepository.java
    │   ├── FileTaskRepository.java
    │   ├── TaskService.java
    │   └── Main.java
    ├── test/java/demo/
    │   └── TaskServiceTest.java
    └── integrationTest/java/demo/
        └── TaskServiceIntegrationTest.java
```

**Chỉ chọn một build script**: Kotlin ở mục 6.2 hoặc Groovy tương đương ở mục 7. Java source files được dùng chung cho cả hai.

### 6.2. settings.gradle.kts

```kotlin
rootProject.name = "gradle-integration-lab"
```

### 6.3. build.gradle.kts — đầy đủ theo JVM Test Suite DSL

```kotlin
plugins {
    id("application")
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.Main")
}

testing {
    suites {
        // Built-in unit test suite: cần chọn framework rõ ràng.
        named<JvmTestSuite>("test") {
            useJUnitJupiter("5.11.4")
            targets {
                all {
                    testTask.configure {
                        testLogging {
                            events("passed", "failed", "skipped")
                            showStandardStreams = true
                        }
                    }
                }
            }
        }

        // Custom integration suite: không tự thấy production outputs.
        register<JvmTestSuite>("integrationTest") {
            useJUnitJupiter("5.11.4")

            dependencies {
                // Kết nối test suite với production component của project.
                implementation(project())
            }

            targets {
                all {
                    testTask.configure {
                        group = "verification"
                        description = "Runs filesystem integration tests"
                        shouldRunAfter(tasks.named("test"))

                        testLogging {
                            events("passed", "failed", "skipped")
                            showStandardStreams = true
                        }
                    }
                }
            }
        }
    }
}

// Quyết định có chủ đích: check BAO GỒM integrationTest.
tasks.named("check") {
    dependsOn(testing.suites.named("integrationTest"))
}
```

**Giải thích từng khối:**

1. `application` áp dụng Java support và tạo `run`; JVM Test Suite DSL đã có qua Java plugin.
2. `mavenCentral()` cung cấp JUnit dependencies, không ảnh hưởng Java standard library của production code.
3. `java.toolchain` yêu cầu Java 17 cho compile/test theo plugin integration.
4. `named<JvmTestSuite>("test")` cấu hình **suite có sẵn**; không tạo thêm một test task cùng tên.
5. `register<JvmTestSuite>("integrationTest")` tạo suite riêng, với `src/integrationTest/java` và task `integrationTest`.
6. `implementation(project())` trong **suite dependencies** cho phép integration test dùng classes/dependencies của chính project. Đây **không phải** `implementation(project())` đặt trong top-level dependencies của production code.
7. `shouldRunAfter(tasks.named("test"))` yêu cầu integration test ưu tiên chạy sau unit test **nếu cả hai cùng trong graph**.
8. `tasks.named("check").dependsOn(testing.suites.named("integrationTest"))` là liên kết **thực sự** đưa suite vào verification lifecycle.

Khi chạy riêng `./gradlew integrationTest`, Gradle **không có nghĩa vụ** chạy `test` trước vì `shouldRunAfter` không tự thêm task `test` vào graph. Khi chạy `./gradlew check`, Java plugin đã nối unit test và đoạn trên nối integration suite; cả hai sẽ được lên lịch.

### 6.4. TaskRepository.java — contract cho lưu trữ

**`src/main/java/demo/TaskRepository.java`:**

```java
package demo;

import java.io.IOException;

public interface TaskRepository {
    void save(String id, String content) throws IOException;

    String load(String id) throws IOException;
}
```

Một interface giúp service không phụ thuộc trực tiếp vào cách lưu trữ. Unit test có thể cung cấp fake implementation, còn integration test dùng adapter filesystem thật.

### 6.5. FileTaskRepository.java — filesystem adapter thật

**`src/main/java/demo/FileTaskRepository.java`:**

```java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class FileTaskRepository implements TaskRepository {
    private final Path directory;

    public FileTaskRepository(Path directory) {
        this.directory = Objects.requireNonNull(directory);
    }

    private Path pathFor(String id) {
        if (id == null || !id.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid task id");
        }
        return directory.resolve(id + ".txt");
    }

    @Override
    public void save(String id, String content) throws IOException {
        Path file = pathFor(id);
        Files.createDirectories(directory);
        Files.writeString(file, content, StandardCharsets.UTF_8);
    }

    @Override
    public String load(String id) throws IOException {
        return Files.readString(pathFor(id), StandardCharsets.UTF_8);
    }
}
```

`pathFor` giới hạn ID vào chữ/số/dấu gạch hợp lệ, tránh biến input thành đường dẫn arbitrary. `Files.writeString` và `Files.readString` có sẵn từ Java 11, do đó chạy được trên Java 17. Khi lưu, adapter tạo directory nếu chưa có; khi đọc một file không tồn tại, IOException sẽ được truyền lên caller.

### 6.6. TaskService.java — business logic

**`src/main/java/demo/TaskService.java`:**

```java
package demo;

import java.io.IOException;
import java.util.Locale;
import java.util.Objects;

public final class TaskService {
    private final TaskRepository repository;

    public TaskService(TaskRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public String save(String id, String message) throws IOException {
        String normalized = Objects.requireNonNull(message)
            .trim()
            .toUpperCase(Locale.ROOT);
        repository.save(id, normalized);
        return normalized;
    }

    public String load(String id) throws IOException {
        return repository.load(id);
    }
}
```

Service đảm nhiệm chuẩn hóa text, repository đảm nhiệm I/O. Sự phối hợp giữa hai component là điều integration test sẽ quan sát.

### 6.7. Main.java — chương trình Java 17 chạy trực tiếp

**`src/main/java/demo/Main.java`:**

```java
package demo;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("task-lab-");
        try {
            TaskService service =
                new TaskService(new FileTaskRepository(root));

            service.save("demo1", " hello ");
            System.out.println("APP_OK:" + service.load("demo1"));
        } finally {
            Files.deleteIfExists(root.resolve("demo1.txt"));
            Files.deleteIfExists(root);
        }
    }
}
```

Lệnh `./gradlew -q run` (khi toolchain hoạt động) in đúng:

```text
APP_OK:HELLO
```

Chương trình đã tạo directory tạm, lưu rồi đọc lại file và dọn hai file/directory biết trước. Đây là ví dụ học tập tối giản; hệ thống production cần chính sách cleanup khi có nhiều file, lỗi mở file hoặc concurrent writes.

### 6.8. TaskServiceTest.java — unit test với fake

**`src/test/java/demo/TaskServiceTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;

public class TaskServiceTest {
    @Test
    void normalizesWithoutTouchingDisk() throws IOException {
        Map<String, String> values = new HashMap<>();

        TaskRepository fake = new TaskRepository() {
            @Override
            public void save(String id, String content) {
                values.put(id, content);
            }

            @Override
            public String load(String id) {
                return values.get(id);
            }
        };

        TaskService service = new TaskService(fake);

        assertEquals("HELLO", service.save("unit1", " hello "));
        assertEquals("HELLO", service.load("unit1"));

        System.out.println("UNIT_OK");
    }
}
```

Test này không gọi filesystem vì fake repository chỉ lưu trong Map. Nó xác minh logic chuẩn hóa và phối hợp ở mức interface, nhưng chưa kiểm tra rằng adapter thật sẽ ghi/đọc file đúng.

### 6.9. TaskServiceIntegrationTest.java — integration test thật

**`src/integrationTest/java/demo/TaskServiceIntegrationTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

public class TaskServiceIntegrationTest {
    @TempDir
    Path tempDirectory;

    @Test
    void persistsAcrossRepositoryInstances() throws IOException {
        TaskService first =
            new TaskService(new FileTaskRepository(tempDirectory));

        assertEquals("HELLO", first.save("it1", " hello "));

        Path persistedFile = tempDirectory.resolve("it1.txt");
        assertTrue(Files.exists(persistedFile));
        assertEquals(
            "HELLO",
            Files.readString(persistedFile, StandardCharsets.UTF_8)
        );

        // Tạo instance mới để kiểm tra dữ liệu đã thực sự lưu.
        TaskService restarted =
            new TaskService(new FileTaskRepository(tempDirectory));

        assertEquals("HELLO", restarted.load("it1"));

        System.out.println("INTEGRATION_OK");
    }
}
```

JUnit Jupiter `@TempDir` tạo một thư mục tạm cho bài test. Test vừa đi qua service, vừa gọi FileTaskRepository thật, vừa kiểm chứng file tồn tại/nội dung, rồi tạo repository instance mới để đọc lại. Đây là một **integration test của các component với filesystem**, không phải unit test dùng fake.

Không sử dụng một đường dẫn cố định `/tmp/integration-test` cho tất cả tests: `@TempDir` giảm va chạm giữa test cases và chạy song song. Nếu test có nhiều tài nguyên bên ngoài (database/container), cần cơ chế lifecycle/cleanup bổ sung.

## 7. Bản Groovy DSL cho bài lab ở mục 6

Các file Java **không thay đổi**. Thay `settings.gradle.kts` bằng `settings.gradle`:

```groovy
rootProject.name = 'gradle-integration-lab'
```

Thay toàn bộ `build.gradle.kts` bằng **`build.gradle`**:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.Main'
}

testing {
    suites {
        test {
            useJUnitJupiter('5.11.4')

            targets {
                all {
                    testTask.configure {
                        testLogging {
                            events 'passed', 'failed', 'skipped'
                            showStandardStreams = true
                        }
                    }
                }
            }
        }

        integrationTest(JvmTestSuite) {
            useJUnitJupiter('5.11.4')

            dependencies {
                implementation project()
            }

            targets {
                all {
                    testTask.configure {
                        group = 'verification'
                        description = 'Runs filesystem integration tests'
                        shouldRunAfter tasks.named('test')

                        testLogging {
                            events 'passed', 'failed', 'skipped'
                            showStandardStreams = true
                        }
                    }
                }
            }
        }
    }
}

tasks.named('check') {
    dependsOn testing.suites.integrationTest
}
```

Điểm khác cú pháp:

- Kotlin dùng `register<JvmTestSuite>("integrationTest")`; Groovy dùng `integrationTest(JvmTestSuite)`.
- Kotlin dùng `implementation(project())` trong suite; Groovy dùng `implementation project()`.
- Kotlin gọi `languageVersion.set(...)`; Groovy thường gán `languageVersion = ...`.
- Cả hai áp dụng cùng JVM Test Suite concepts; kết quả unit/integration tests giống nhau khi chạy trong môi trường có JUnit và JDK 17.

Đừng giữ đồng thời hai build scripts cùng vai trò rồi đoán Gradle sẽ chọn file nào; dùng một DSL rõ ràng cho bài tập.

## 8. Chạy bài lab và hiểu output

Từ root có Gradle Wrapper:

```bash
./gradlew --version
./gradlew tasks --group verification
./gradlew -q run
./gradlew test
./gradlew integrationTest
./gradlew check
./gradlew build
```

Với Windows, dùng `gradlew.bat` (PowerShell: `.\gradlew.bat`). Nếu repository mới chưa có Wrapper nhưng máy đã cài Gradle, có thể tạo bằng `gradle wrapper` trước khi chạy các lệnh trên.

### 8.1. Những kết quả đáng tin cậy

- `./gradlew -q run`: chương trình Java in **`APP_OK:HELLO`**.
- `./gradlew test`: chạy test ở `src/test/java`; với cấu hình test logging trên, captured stdout của test chứa **`UNIT_OK`**.
- `./gradlew integrationTest`: chạy test ở `src/integrationTest/java`; captured stdout của test chứa **`INTEGRATION_OK`**.
- `./gradlew check`: chạy những verification dependencies của `check`, bao gồm unit test và integration test bởi vì ta đã khai báo `dependsOn`.
- `./gradlew build`: chạy `assemble` và `check` (và các task con), do đó bao gồm integration test trong cấu hình này.

**Không khẳng định toàn bộ terminal stdout cố định:** Gradle có thể thêm task path, trạng thái `UP-TO-DATE`, download logs, test class/method labels hoặc report links tùy version, cache, mức log. Các chuỗi `APP_OK:HELLO`, `UNIT_OK` và `INTEGRATION_OK` là những dòng được code Java in ra nếu test thực sự chạy, không phải toàn bộ log Gradle.

### 8.2. Kiểm tra task graph mà không chạy tests

```bash
./gradlew check --dry-run
./gradlew integrationTest --dry-run
```

`--dry-run` liệt kê các task dự định chạy mà không thực thi chúng. Trong output của `check --dry-run` nên thấy cả `test` và `integrationTest` nếu cấu hình đã nối đúng. Nhưng **dry-run không chứng minh assertions chạy đúng**, environment được cấp đủ hoặc DB/service có thể truy cập; vẫn phải chạy integration test thật.

### 8.3. Kiểm tra đúng một test class hoặc method

```bash
./gradlew integrationTest --tests "demo.TaskServiceIntegrationTest"
./gradlew integrationTest --tests "demo.TaskServiceIntegrationTest.persistsAcrossRepositoryInstances"
```

`--tests` là filter của task `Test` cụ thể. `./gradlew test --tests ...` sẽ không tìm bài integration test trong source set khác, trừ khi người làm thay đổi cấu trúc task/test classes khác với lab này.

### 8.4. Reports khác nhau

Thông thường báo cáo HTML/XML của hai tasks ở các vị trí:

```text
build/reports/tests/test/index.html
build/reports/tests/integrationTest/index.html

build/test-results/test/
build/test-results/integrationTest/
```

Đường dẫn có thể bị override bằng cấu hình reports hoặc thay đổi theo Gradle version. Không coi report của `integrationTest` được tự động gộp vào báo cáo `test`; nếu cần coverage/report aggregation phải cấu hình riêng.

## 9. Hướng B — tự tạo SourceSet + Test task (không dùng JVM Test Suite DSL)

Nếu tổ chức không muốn sử dụng API `JvmTestSuite` còn incubating, bạn có thể dùng Java source sets và một custom `Test` task. Đây là **phương án thay thế toàn bộ build file ở mục 6/7**, không phải các đoạn được phép copy bổ sung vào cùng một build.

Vẫn dùng cùng Java files, cùng layout `src/main/java`, `src/test/java` và `src/integrationTest/java` của bài lab. Chỉ thay Gradle build script.

### 9.1. Bản Kotlin DSL đầy đủ

**`build.gradle.kts`:**

```kotlin
plugins {
    id("application")
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.Main")
}

// Bước 1: tạo source set riêng (và các configurations tương ứng).
val integrationTestSourceSet = sourceSets.create("integrationTest") {
    compileClasspath += sourceSets["main"].output
    runtimeClasspath += sourceSets["main"].output
}

// Bước 2: kế thừa dependencies production khi thực sự cần.
configurations[integrationTestSourceSet.implementationConfigurationName]
    .extendsFrom(configurations["implementation"])

configurations[integrationTestSourceSet.runtimeOnlyConfigurationName]
    .extendsFrom(configurations["runtimeOnly"])

// Bước 3: khai báo JUnit Jupiter và Platform Launcher.
// Không dựa vào dependencies mà Gradle test worker từng leak.
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")

    add(
        integrationTestSourceSet.implementationConfigurationName,
        "org.junit.jupiter:junit-jupiter:5.11.4"
    )
    add(
        integrationTestSourceSet.runtimeOnlyConfigurationName,
        "org.junit.platform:junit-platform-launcher:1.11.4"
    )
}

// Bước 4: chỉ chọn JUnit Platform cho unit test task.
tasks.named<Test>("test") {
    useJUnitPlatform()
    testLogging {
        events("passed", "failed", "skipped")
        showStandardStreams = true
    }
}

// Bước 5: tạo task Test thật cho integration source set.
val integrationTestTask = tasks.register<Test>("integrationTest") {
    group = "verification"
    description = "Runs integration tests"

    testClassesDirs = integrationTestSourceSet.output.classesDirs
    classpath = integrationTestSourceSet.runtimeClasspath
    useJUnitPlatform()

    shouldRunAfter(tasks.named("test"))

    testLogging {
        events("passed", "failed", "skipped")
        showStandardStreams = true
    }
}

// Bước 6: nối vào lifecycle có chủ đích.
tasks.named("check") {
    dependsOn(integrationTestTask)
}
```

**Các điểm khác với JVM Test Suite:**

- `sourceSets.create("integrationTest")` tạo source set, related configurations và compile tasks, **không tự tạo test-execution task**. Bước 5 bắt buộc.
- `compileClasspath += sourceSets["main"].output` và `runtimeClasspath += sourceSets["main"].output` cho tests gọi production classes/resources.
- `extendsFrom(configurations["implementation"])` và `extendsFrom(configurations["runtimeOnly"])` truyền dependency declarations của production sang test classpath theo policy đã chọn.
- `testImplementation` và `integrationTestImplementation` là các buckets **khác nhau**; ở đây mỗi bên nhận JUnit riêng vì không mặc nhiên kế thừa toàn bộ test dependencies.
- `testRuntimeOnly` và `integrationTestRuntimeOnly` thêm `junit-platform-launcher` để Gradle 9+ không phụ thuộc classpath injection cũ.
- `useJUnitPlatform()` chọn framework execution cho mỗi `Test` task; nó **không tự kéo thư viện JUnit**, nên cần dependencies ở bước 3.
- `testClassesDirs` là directory của compiled test classes, khác `classpath` là toàn bộ runtime classpath cho test worker.
- `dependsOn(integrationTestTask)` bảo đảm `check` chạy custom task nếu policy yêu cầu.

### 9.2. Bản Groovy DSL tương đương

**`build.gradle` — thay cho Kotlin script của mục 9.1:**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.Main'
}

def integrationTestSourceSet = sourceSets.create('integrationTest') {
    compileClasspath += sourceSets.main.output
    runtimeClasspath += sourceSets.main.output
}

configurations[integrationTestSourceSet.implementationConfigurationName]
    .extendsFrom(configurations.implementation)

configurations[integrationTestSourceSet.runtimeOnlyConfigurationName]
    .extendsFrom(configurations.runtimeOnly)

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'

    add(
        integrationTestSourceSet.implementationConfigurationName,
        'org.junit.jupiter:junit-jupiter:5.11.4'
    )
    add(
        integrationTestSourceSet.runtimeOnlyConfigurationName,
        'org.junit.platform:junit-platform-launcher:1.11.4'
    )
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
        showStandardStreams = true
    }
}

def integrationTestTask = tasks.register('integrationTest', Test) {
    group = 'verification'
    description = 'Runs integration tests'

    testClassesDirs = integrationTestSourceSet.output.classesDirs
    classpath = integrationTestSourceSet.runtimeClasspath
    useJUnitPlatform()

    shouldRunAfter tasks.named('test')

    testLogging {
        events 'passed', 'failed', 'skipped'
        showStandardStreams = true
    }
}

tasks.named('check') {
    dependsOn integrationTestTask
}
```

File `settings.gradle` của Groovy có:

```groovy
rootProject.name = 'gradle-integration-lab'
```

Hai cách trong mục 9 đều tạo task `integrationTest` chạy cùng Java tests, với framework/runtime classpath tường minh và `check` được nối rõ. **Chọn một cách** (suite DSL hoặc sourceSet thủ công), không tạo cả hai cùng tên trong một project.

### 9.3. Vì sao không nên kế thừa toàn bộ unit test configuration?

Có thể gặp:

```kotlin
// Chỉ khi test tích hợp thật sự dùng cùng dependency set:
configurations["integrationTestImplementation"]
    .extendsFrom(configurations["testImplementation"])
```

Điều này thuận tiện nhưng cũng kéo theo tất cả libraries chỉ phục vụ unit tests, ví dụ Mockito, JUnit4 Vintage hoặc nhiều mocking tools không cần thiết. Dự án lớn nên giữ `integrationTestImplementation` độc lập và chỉ chia sẻ dependency groups có lý do.

Ngược lại, không kế thừa production outputs/dependencies khi test gọi production code có thể gây `cannot find symbol` hoặc `ClassNotFoundException`. Chọn classpath theo cách test thật sự tương tác với ứng dụng: gọi class trực tiếp khác với gửi HTTP request đến một process độc lập.

## 10. Gắn lifecycle như thế nào là “có chủ đích”?

Một team có thể muốn **luôn chạy integration test khi check/build**. Team khác chỉ muốn **chạy ở CI stage riêng**, vì integration test cần Docker/database hoặc mất 10 phút.

Đây là **quyết định về task graph**, không phải luật cố định của Gradle.

### 10.1. Chính sách A — check luôn chạy integration tests

Chính sách đã dùng trong lab:

**Kotlin:**

```kotlin
tasks.named("check") {
    dependsOn(testing.suites.named("integrationTest"))
}
```

**Groovy:**

```groovy
tasks.named('check') {
    dependsOn testing.suites.integrationTest
}
```

Lệnh:

```bash
./gradlew check
./gradlew build
```

sẽ có integration test trong graph. Trong Java plugin, `build` thường phụ thuộc `check`; nếu build bỏ qua test qua `-x`, `--continue` hoặc task được up-to-date, kết quả cần diễn giải theo command đã chạy.

**Không nên thêm ngược `test.dependsOn(integrationTest)`** nếu bạn muốn unit test nhanh luôn độc lập: nó khiến `./gradlew test` vô tình chạy integration test và phá mục đích phân tầng.

### 10.2. Chính sách B — chỉ chạy theo yêu cầu của CI

Với JVM Test Suite, **bỏ** block `tasks.named("check") { dependsOn(...) }` ở cuối bài lab rồi thay bằng block có điều kiện:

**Kotlin:**

```kotlin
val withIntegrationTests = providers.gradleProperty("withIntegrationTests")
    .map { it.toBoolean() }
    .getOrElse(false)

tasks.named("check") {
    if (withIntegrationTests) {
        dependsOn(testing.suites.named("integrationTest"))
    }
}
```

**Groovy:**

```groovy
def withIntegrationTests = providers.gradleProperty('withIntegrationTests')
    .map { it.toBoolean() }
    .getOrElse(false)

tasks.named('check') {
    if (withIntegrationTests) {
        dependsOn testing.suites.integrationTest
    }
}
```

Ví dụ hai cách dùng:

```bash
# Chỉ những verification tasks đã được check nối mặc định:
./gradlew check

# Chủ động bao gồm integration test:
./gradlew check -PwithIntegrationTests=true

# Luôn có thể chạy trực tiếp, dù property không bật:
./gradlew integrationTest
```

**Đây là lựa chọn thay thế của block lifecycle**, không copy cả hai. Nếu giữ `dependsOn` vô điều kiện ở nơi khác, property sẽ không thể tắt integration test.

Với phương án SourceSet thủ công, chỉ thay biểu thức `dependsOn(testing.suites.named("integrationTest"))` bằng `dependsOn(integrationTestTask)`; phần logic property tương tự.

**Cảnh báo:** không nên dùng `onlyIf { providers.gradleProperty("...")... }` để âm thầm skip integration test khi `check` vốn là gate bắt buộc. CI có thể báo xanh mà không thực sự chạy kiểm thử. Tốt hơn là thể hiện rõ policy qua task graph hoặc CI stages và xác minh test reports tồn tại.

### 10.3. Chính sách C — CI tách hai jobs rõ ràng

Ví dụ lịch chạy có chủ đích:

```text
Job 1 — unit + compile (nhanh):
    ./gradlew clean test

Job 2 — integration (sau Job 1, có environment):
    ./gradlew integrationTest

Job 3 — package/release:
    ./gradlew assemble
    chỉ chạy khi các gates bắt buộc đều PASS
```

Đây là **minh họa CI flow**, không phải YAML cho hệ thống CI cụ thể. Gradle không tự ép Job 2 chạy sau Job 1: **CI pipeline** phải định nghĩa dependency giữa jobs/stages. Nếu integration tests là yêu cầu release, hãy cấu hình stage/job failures **chặn publish/deploy**, kể cả khi bạn không nối integrationTest vào `check`.

## 11. Diễn giải chính xác dependsOn, shouldRunAfter và mustRunAfter

### 11.1. dependsOn — quan hệ điều kiện cần

```kotlin
tasks.named("check") {
    dependsOn(tasks.named("integrationTest"))
}
```

`check` sẽ yêu cầu chạy `integrationTest` trước khi `check` hoàn tất (trừ khi bị skip/disabled/excluded và các chính sách command khác). Nhưng dòng này **không tự quy định** integrationTest chạy trước hay sau task `test`; cả hai cùng là dependencies của `check`.

Trong suite DSL, có thể depend trực tiếp vào `testing.suites.named("integrationTest")` như tài liệu chính thức: Gradle sẽ đưa tất cả targets phù hợp của suite vào task graph.

### 11.2. shouldRunAfter — thứ tự mềm

```kotlin
tasks.named("integrationTest") {
    shouldRunAfter(tasks.named("test"))
}
```

Nó hữu ích khi integration suite đắt và bạn muốn unit test fail sớm. Nhưng:

- Không thêm `test` vào graph khi bạn chạy riêng `integrationTest`.
- Không thay thế `check.dependsOn(integrationTest)`.
- Gradle vẫn có thể có những ràng buộc task ordering khác; không dùng nó làm cơ chế đồng bộ correctness cho cơ sở dữ liệu hoặc shared mutable state.
- Với project đa module hoặc chạy song song, hãy xem xét isolation và dependencies thực sự giữa task outputs/environment.

### 11.3. mustRunAfter — thứ tự cứng nếu cùng được chọn

```kotlin
tasks.named("integrationTest") {
    mustRunAfter(tasks.named("test"))
}
```

Đây là yêu cầu thứ tự mạnh hơn; nó **vẫn không làm task test tự tham gia graph**. Chỉ nên dùng nếu có lý do kỹ thuật cần bảo đảm thứ tự hai tasks khi cùng được chọn. Nếu hai nhóm test chia sẻ state đến mức phải bắt buộc serial, cũng nên xem lại tính độc lập, vì ordering không giải quyết hoàn toàn tranh chấp dữ liệu trong test processes.

### 11.4. finalizedBy — dành cho cleanup, không dành cho verification dependency

Nếu phải khởi động service/container cho integration test, có thể cần task dọn sau khi test hoàn tất. `finalizedBy(...)` là cơ chế liên kết finalizer nhưng không có nghĩa Gradle tự biết cách chờ service ready hay cleanup mọi môi trường bên ngoài.

Ví dụ minh họa:

```kotlin
val cleanupSandbox = tasks.register("cleanupSandbox") {
    doLast {
        println("Sandbox cleanup completed")
    }
}

tasks.named("integrationTest") {
    finalizedBy(cleanupSandbox)
}
```

Đoạn này chỉ minh họa finalizer và log, **không thực sự dọn database/container**. Với môi trường thật, cleanup phải được lập trình idempotent, chạy được kể cả khi test thất bại và không xóa tài nguyên không thuộc bài test.

## 12. Tổ chức dependencies và test fixtures

### 12.1. Test suite dependencies là scope riêng

Trong JVM Test Suite DSL:

```kotlin
testing {
    suites {
        register<JvmTestSuite>("integrationTest") {
            useJUnitJupiter("5.11.4")
            dependencies {
                implementation(project())
                implementation("org.assertj:assertj-core:3.27.3")
                runtimeOnly("org.slf4j:slf4j-simple:2.0.17")
            }
        }
    }
}
```

Đây là ví dụ mở rộng độc lập với bài lab chính (những artifacts phải tồn tại và được repo cung cấp). `implementation(project())` đưa production component vào suite; AssertJ chỉ dành cho integration test assertions; SLF4J binding chỉ cần runtime khi project/framework thực sự dùng SLF4J.

**Không nhầm `dependencies { implementation(...) }` trong suite với top-level `dependencies`**: DSL suite tự ánh xạ tới `integrationTestImplementation`, `integrationTestRuntimeOnly`..., trong khi top-level `implementation` thuộc production code.

### 12.2. Java Test Fixtures plugin để chia sẻ helper đúng chỗ

Khi unit/integration tests cần chung test data builders hoặc fake dependencies, cân nhắc plugin `java-test-fixtures` và source set `src/testFixtures/java`. Với suite integration:

```kotlin
plugins {
    id("java-test-fixtures")
}

testing {
    suites {
        register<JvmTestSuite>("integrationTest") {
            useJUnitJupiter("5.11.4")
            dependencies {
                implementation(project())
                implementation(testFixtures(project()))
            }
        }
    }
}
```

Đây là **mẫu minh họa riêng**; cần sử dụng trong project có Java plugin và test fixtures source. Không phải mọi helper của unit test nên trở thành dependency của integration test; ưu tiên fixtures ổn định, tách khỏi data/state dùng chung không an toàn.

Nếu consumer lấy fixtures từ project khác, cú pháp có thể là `testFixtures(project(":shared-test-support"))` khi producer có published fixtures variant phù hợp.

### 12.3. Không kéo testImplementation sang integrationTest một cách mù quáng

Một build source-set cũ có thể cấu hình:

```kotlin
configurations["integrationTestImplementation"]
    .extendsFrom(configurations["testImplementation"])
```

Điều này giúp chia sẻ các dependencies nhưng cũng có thể kéo MockK/Mockito, Vintage engine và nhiều libs chỉ phục vụ unit test. Chỉ kế thừa nếu đó là chiến lược có chủ đích. Với JVM Test Suite, việc khai báo framework và dependencies theo suite riêng thường dễ bảo trì hơn.

## 13. Cấu hình Test task: timeout, heap, fork, logging và filter

Integration tests có thể tốn RAM, cần flags hoặc cần ngăn chạy song song. Với JVM Test Suite DSL:

```kotlin
testing {
    suites {
        named<JvmTestSuite>("integrationTest") {
            targets {
                all {
                    testTask.configure {
                        maxHeapSize = "512m"
                        maxParallelForks = 1

                        testLogging {
                            events("failed", "skipped", "passed")
                            showStandardStreams = true
                            exceptionFormat =
                                org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
                        }

                        // Chỉ dùng khi integration test cần giá trị này:
                        systemProperty("app.test.profile", "integration")
                    }
                }
            }
        }
    }
}
```

Đây là **đoạn cấu hình bổ sung** cho suite đã được định nghĩa ở bài lab, không phải lời yêu cầu đăng ký suite lần thứ hai. Nếu copy, hãy đưa phần `targets` vào suite hiện có hoặc cấu hình nó bằng `named<JvmTestSuite>`, không tạo duplicate registration.

- `maxParallelForks = 1` hạn chế số JVM test workers **trong một Test task**, không tự tuần tự hóa toàn bộ các task của nhiều subprojects.
- `maxHeapSize` quy định JVM heap cho test workers, không phải Gradle Daemon.
- `systemProperty` truyền cấu hình vào test process; tránh đẩy secrets vào log.
- JUnit Platform tags có thể được lọc qua `useJUnitPlatform { includeTags("integration") }` trong task nếu team dùng `@Tag`, nhưng **không dùng tags thay thế cho source set** nếu cần dependencies/environment riêng.
- `--tests` lọc test classes/methods của đúng task, thuận tiện debug.

### 13.1. Dùng JUnit @Tag khi cần phân tầng trong cùng source set

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("integration")
class TaggedIntegrationTest {
    @Test
    void example() {
        // Test logic thực của dự án đặt ở đây.
    }
}
```

Đây là ví dụ Java **không độc lập** (thiếu package và project JUnit), dùng để giải thích tag. Khi dùng JUnit `@Tag("integration")`, task phải được cấu hình filter tương ứng nếu muốn chỉ chạy tag đó. Chỉ đặt `@Tag` không khiến Gradle tự tạo task `integrationTest` và cũng không tự thiết lập classpath/environment.

## 14. Integration test với database, HTTP service hoặc containers

Bài lab filesystem là một integration test có môi trường đơn giản. Khi chuyển sang thành phần thật như PostgreSQL, Redis, Kafka hoặc HTTP service, cần xác định:

1. **Ai chuẩn bị resource?** CI service container, Testcontainers, một task setup, hay một môi trường được cấp sẵn?
2. **Khi nào resource được coi là ready?** Có health check/readiness condition, không chỉ sleep cố định.
3. **Ai sở hữu dữ liệu?** Mỗi test dùng schema/database/namespace riêng, hoặc rollback/reset rõ ràng.
4. **Ai cleanup khi thất bại?** JUnit extension, `try/finally`, lifecycle của Testcontainers, hoặc CI teardown.
5. **Secrets được cung cấp thế nào?** Environment/CI secret store, không commit credential.
6. **Có thể chạy song song không?** Tránh port hard-code và shared mutable state.
7. **Failure là lỗi sản phẩm hay môi trường?** Report/log nên tách connection refused, service unhealthy với assertion fail.

Ví dụ nhận JDBC URL qua system property trong test process:

```kotlin
tasks.named<Test>("integrationTest") {
    systemProperty(
        "it.jdbc.url",
        providers.gradleProperty("integrationJdbcUrl").orNull ?: ""
    )
}
```

Đây là **mẫu điều khiển cấu hình**, không phải một test JDBC chạy độc lập; phải có driver, DB và code/credentials cụ thể. Không tự coi chuỗi rỗng là database URL hợp lệ; test setup phải báo thiếu cấu hình bằng lỗi rõ hoặc CI chỉ chạy suite khi môi trường đã chuẩn bị.

**Ưu tiên test tự sở hữu vòng đời dependency** khi có thể; nếu dùng shared CI environment, cần ranh giới dữ liệu và chính sách bảo vệ dữ liệu. Không chạy integration tests phá dữ liệu trên database production.

## 15. Gradle build cache, up-to-date, --rerun-tasks và test reports

Tasks kiểu `Test` có input/output được Gradle theo dõi. Tùy cấu hình, nếu inputs không đổi và kết quả còn hợp lệ, Gradle có thể đánh dấu `UP-TO-DATE` hoặc tận dụng build cache thay vì chạy lại tests.

Đây là điều cần lưu ý khi integration test phụ thuộc trạng thái **bên ngoài Gradle** như database đang chạy: task inputs không nhất thiết phản ánh đầy đủ trạng thái external service.

- Khi debug một integration test cần chạy lại, dùng `./gradlew integrationTest --rerun-tasks` nếu phù hợp. Nó có thể khiến các dependency tasks cũng rerun; cân nhắc chi phí.
- Khi môi trường test thay đổi mà Gradle không thấy trong inputs, cần khai báo task inputs hoặc quản lý khả năng cache/up-to-date theo đúng mức độ.
- Đừng vô hiệu hóa caching của mọi test task chỉ vì một integration suite đặc biệt; tập trung vào suite cần thiết.
- Reports của `test` và `integrationTest` tách riêng; CI có thể thu thập cả hai tập XML ở `build/test-results/...`.
- Nếu yêu cầu code coverage, JaCoCo cần cấu hình cho custom test tasks/suites. `jacocoTestReport` không nhất thiết tự bao phủ `integrationTest`.
- Khi test lỗi, xem XML/HTML report, stacktrace và captured stdout. Log chỉ chứa một phần thông tin.

## 16. Lựa chọn runtime Java và chạy test trên nhiều JDK

Với Java plugin cấu hình toolchain 17, built-in `test` và custom/suite test tasks được hỗ trợ thường dùng Java 17 launcher. Nếu muốn kiểm thử integration trên Java 21, có thể override launcher của riêng suite target:

```kotlin
testing {
    suites {
        named<JvmTestSuite>("integrationTest") {
            targets {
                all {
                    testTask.configure {
                        javaLauncher.set(
                            javaToolchains.launcherFor {
                                languageVersion.set(JavaLanguageVersion.of(21))
                            }
                        )
                    }
                }
            }
        }
    }
}
```

Đoạn này chỉ thay **JVM chạy tests**, không đổi bytecode đã compile. Phải đảm bảo JDK 21 tồn tại hoặc có toolchain resolver. Nếu mã đang compile thành Java 21 bytecode, không thể hạ launcher test xuống Java 17 mà mong nó chạy.

Custom test suite có thể có nhiều targets chạy trên JVM versions khác nhau nếu mục tiêu là compatibility matrix. Nhưng mỗi target có môi trường/tài nguyên riêng và Gradle plugin version phải hỗ trợ API đó.

## 17. Tích hợp vào multi-project builds

Với `:api`, `:service` và `:app`, không nhất thiết mọi module đều cần integration test. Ví dụ:

- `:api` chỉ chứa DTO: unit test có thể đủ.
- `:service` có repository adapter: cần integration tests với DB/filesystem.
- `:app` có HTTP endpoint: có thể cần integration tests với server.

Khi chạy:

```bash
./gradlew :service:integrationTest
./gradlew :service:check
./gradlew check
```

- `:service:integrationTest` chạy đúng task của service (nếu module định nghĩa).
- `:service:check` chỉ chạy những verification dependencies của module service.
- `./gradlew check` ở root có thể chọn tasks theo tên trong nhiều project; hành vi phụ thuộc cấu trúc build và task selection. Không nên dùng nó như một contract CI mơ hồ khi bạn cần chỉ định một subset modules chính xác.

Nếu nhiều module cần chung policies, dùng **convention plugin** đăng ký test suite và kết nối lifecycle thay vì copy-paste block `subprojects { ... }` phức tạp. Nhưng convention phải chỉ áp dụng cho project có JVM plugin và environment test phù hợp; không bắt Android/native modules nhận `JvmTestSuite` vô điều kiện.

### 17.1. Tách integration testing của plugin Gradle

Nếu project phát triển **Gradle plugin**, test tích hợp chức năng plugin thường dùng **Gradle TestKit** và `GradleRunner`. Khi tạo source set/suite functional riêng, cần thêm `gradleTestKit()` và cấu hình plugin classpath thông qua `java-gradle-plugin`/`gradlePlugin.testSourceSets(...)` tương ứng.

Đừng đem cấu hình TestKit áp dụng nguyên xi vào một Java web service: TestKit kiểm thử build/plugin behavior, không tự kiểm thử HTTP/database business logic.

## 18. Troubleshooting: build xanh nhưng integration test không chạy

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| `./gradlew check` chỉ chạy unit tests | Chưa nối `integrationTest` vào `check`. | Thêm `check.dependsOn(...)` hoặc quy định CI chạy suite riêng. |
| `./gradlew test` không chạy integration tests | Chủ ý tách suite, `test` chỉ chạy source set test. | Dùng `integrationTest` hoặc `check` theo policy; không coi là lỗi. |
| `shouldRunAfter(test)` nhưng integration test không thấy trong graph | Ordering không thêm dependencies. | Dùng `dependsOn` ở lifecycle hoặc gọi task trực tiếp. |
| `mustRunAfter` mà task test không chạy | mustRunAfter chỉ áp khi cả hai tasks được chọn. | Dùng `dependsOn` nếu cần task tham gia graph. |
| `Task 'integrationTest' not found` | Chưa đăng ký suite/task, hoặc tên khác, áp nhầm project. | Kiểm tra `tasks --all`, plugin và `src/integrationTest`/task registration. |
| `Cannot add a task with name 'integrationTest'` | Đã dùng JVM Test Suite và lại register thủ công task cùng tên. | Chọn một mô hình; không tạo hai lần. |
| `cannot find symbol TaskService` khi compile integration tests | Suite thiếu `implementation(project())` hoặc manual source set không có main output. | Khai báo project dependency hoặc nối compileClasspath đúng cách. |
| `NoClassDefFoundError` khi chạy tests | Thiếu runtime dependency/project output. | Kiểm tra `integrationTestRuntimeClasspath`, runtimeOnly và classpath của Test task. |
| JUnit `@Test` không được phát hiện | Chưa chọn framework hoặc thiếu JUnit Platform/engine/launcher. | Suite dùng `useJUnitJupiter`; manual task dùng dependencies + `useJUnitPlatform`. |
| `No tests found for given includes` | `--tests` filter sai package/class/method hoặc chọn nhầm task. | Xem fully qualified class name và đúng task. |
| Test chỉ chạy ở local, CI fail | CI thiếu filesystem permission, DB, Docker, JDK hoặc network. | Chuẩn hóa môi trường và kiểm tra readiness/permissions. |
| Test treo hoặc chậm | External resource không sẵn sàng, connection timeout quá dài, shared locks. | Thêm timeout/readiness hợp lý, isolation, logs, và giới hạn parallelism khi cần. |
| Integration test chạy song song làm hỏng dữ liệu | Test dùng DB/schema/port/file cố định. | Mỗi test sở hữu resource/namespace hoặc phối hợp resource lock được quản lý. |
| Không thấy `INTEGRATION_OK` trong terminal | TestLogging chưa show stdout, task UP-TO-DATE hoặc không chạy. | Bật `showStandardStreams`, kiểm tra reports, dùng rerun khi cần. |
| `build` chạy quá lâu ngoài dự kiến | `check` được nối integration tests tốn tài nguyên. | Chọn policy opt-in hoặc CI stage riêng, có documentation. |
| `No matching toolchains found` | JDK 17 không được tìm thấy/cấp phát. | Kiểm tra `javaToolchains` và toolchain resolver/CI image. |
| Suite có JUnit version khác unit tests | Version framework khác nhau hoặc dependencies/constraints xung đột. | Pin version có chủ đích và dùng `dependencyInsight`. |
| `jacocoTestReport` thiếu coverage integration tests | Task report chỉ gắn unit test. | Cấu hình custom/aggregation report theo JaCoCo Gradle docs. |
| Test pass vì bị skip âm thầm | `onlyIf`/`enabled=false`, `-x integrationTest` hoặc env flag. | Xác minh task graph, reports và CI gate, không chỉ exit code. |

### 18.1. Lệnh điều tra có hệ thống

```bash
# Xem plugin/tasks và lifecycle graph:
./gradlew tasks --all
./gradlew check --dry-run

# Xem classpath của hai test scopes:
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencies --configuration integrationTestRuntimeClasspath

# Chạy đúng test suite và chẩn đoán chi tiết:
./gradlew integrationTest --tests "demo.TaskServiceIntegrationTest"
./gradlew integrationTest --info
./gradlew integrationTest --stacktrace

# Xem JVM và versions:
./gradlew --version
./gradlew -q javaToolchains
```

Khi chỉ định version dependency test sai, báo cáo `dependencies`/`dependencyInsight` giúp biết module nào được chọn. Nhưng `--dry-run` chỉ xác minh task selection, không thay thế chạy thật.

### 18.2. Chiến lược khi unit PASS nhưng integration FAIL

Phân loại nguyên nhân:

1. **Classpath/compilation**: test không thấy production classes hoặc JUnit.
2. **Test discovery**: classes/method/package/filter không đúng.
3. **Environment**: database/port/credential/permission không đúng.
4. **Functional behavior**: assertion fail, dữ liệu ghi/đọc sai, API contract thay đổi.
5. **Isolation**: tests ảnh hưởng lẫn nhau hoặc phụ thuộc dữ liệu có sẵn.
6. **Lifecycle graph**: task thực ra không chạy hoặc chạy nhầm module.

Sau khi phân loại, sửa đúng tầng; không thêm `--ignore-failures` hoặc `ignoreFailures = true` chỉ để CI xanh khi integration test là quality gate bắt buộc.

## 19. Các bài tập mở rộng

1. **Để test độc lập:** chạy `./gradlew test` và xác minh không có `integrationTest` trong task graph. Giải thích tại sao `shouldRunAfter` không khiến nó chạy.
2. **Bật lifecycle:** chạy `./gradlew check --dry-run`, xác nhận có unit/integration tasks; rồi chạy `check` thật.
3. **Thử sai dependency:** bỏ `implementation(project())` khỏi custom suite rồi chạy compile integration tests. Dự đoán lỗi class `TaskService` không tìm thấy; khôi phục dependency sau khi quan sát.
4. **Thử isolation:** thêm một integration test khác với `@TempDir` của riêng nó; chạy `integrationTest` nhiều lần để kiểm tra không phụ thuộc state từ lần chạy trước.
5. **Thử chính sách CI:** chuyển từ `check.dependsOn` luôn bật sang `-PwithIntegrationTests=true` opt-in, đối chiếu task graph ở hai chế độ.
6. **Đổi Gradle DSL:** thay Kotlin bằng Groovy build script đã cung cấp mà không đổi Java sources, so sánh số tests được chạy.
7. **Dùng Java 21 cho test:** cấu hình `javaLauncher` của suite và kiểm tra class files Java 17 vẫn chạy được trên JVM 21; nếu không cài JDK 21, giải quyết toolchain chứ không bỏ validation.
8. **Thêm DB adapter:** viết test dùng Testcontainers và một database thực; bảo đảm resource readiness, cleanup và CI policy trước khi nối vào `check`.
9. **Thêm báo cáo coverage:** cấu hình JaCoCo thu thập cả unit và integration test data, so sánh coverage riêng trước khi quyết định merge.
10. **Kiểm tra build reproducibility:** dùng Gradle Wrapper, pin dependency versions, chạy integration test trong CI sạch và so sánh kết quả với local.

## 20. Bảng tra nhanh

| Câu hỏi | Câu trả lời |
| --- | --- |
| Dùng thư mục nào cho integration tests? | `src/integrationTest/java` và `src/integrationTest/resources` theo source set/suite. |
| API hiện đại? | `testing.suites.register<JvmTestSuite>("integrationTest")` (Kotlin), `integrationTest(JvmTestSuite)` (Groovy). |
| JVM Test Suite đã ổn định hoàn toàn chưa? | Gradle vẫn đánh dấu **incubating**; kiểm tra Wrapper và compatibility. |
| Suite có tự thấy production code không? | Không đối với custom suite; thêm `dependencies { implementation(project()) }`. |
| Suite có tự chọn JUnit Jupiter không? | Custom suite thường mặc định Jupiter; explicit `useJUnitJupiter("version")` giúp thống nhất. Built-in `test` nên chọn framework rõ. |
| Suite có tự chạy cùng `check` không? | **Không**; thêm `tasks.named("check") { dependsOn(...) }` nếu muốn. |
| Muốn chạy riêng integration tests? | `./gradlew integrationTest`. |
| Muốn chạy cả unit/integration theo lifecycle? | `./gradlew check` hoặc `build` khi đã nối task. |
| Muốn unit tests chạy trước nếu cả hai cùng được chọn? | `integrationTest.shouldRunAfter(test)`. |
| `shouldRunAfter` có buộc unit test chạy không? | Không; chỉ là quy tắc ordering mềm. |
| Muốn chính sách CI opt-in? | Không nối vô điều kiện; dùng property hoặc CI stage riêng với gate rõ. |
| Không muốn JVM Test Suite DSL? | Tạo `SourceSet` + configurations + `Test` task thủ công. |
| Chọn JUnit trong custom `Test`? | `useJUnitPlatform()` + test dependencies + launcher/engine. |
| Chọn riêng một test? | `integrationTest --tests "package.Class.method"`. |
| Xem lifecycle có task integrationTest chưa? | `./gradlew check --dry-run`. |
| Xem kết quả? | `build/reports/tests/integrationTest/` và `build/test-results/integrationTest/`. |
| Nếu CI không có Docker/DB? | Dùng filesystem test cho lab, hoặc provision service rõ ràng; không skip âm thầm. |

**Kết luận:** Tạo source set/test suite riêng **chưa đủ** để tích hợp integration test vào quy trình bảo đảm chất lượng. Bạn cần **dependencies đúng, Test task thật, môi trường được kiểm soát và quyết định task graph rõ ràng**. Với Java project hiện đại, JVM Test Suite cung cấp DSL thuận tiện và tự cấu hình framework/targets; với build yêu cầu API ổn định hơn hoặc kiểm soát thủ công, có thể dùng `SourceSet + Test`. `dependsOn` quyết định task nào được chạy; `shouldRunAfter` chỉ hỗ trợ thứ tự; CI mới quyết định integration tests là gate bắt buộc ở giai đoạn nào.

### Tài liệu chính thức để đối chiếu

- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): suites, dependencies, targets, `implementation(project())`, và ví dụ `check.dependsOn`.
- [Gradle — Testing in Java and JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `SourceSet + Test` thủ công, JUnit Platform, reports, integration tests.
- [Gradle — Best Practices for Testing](https://docs.gradle.org/current/userguide/best_practices_testing.html): tách các loại test, TestKit và cấu hình test suites.
- [Gradle — Test Task DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html): testClassesDirs, classpath, logging, filters, heap/forks.
- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html): dependsOn, mustRunAfter, shouldRunAfter, finalizedBy, onlyIf và task graph.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): source sets, configurations, test/check/build lifecycle.
- [Gradle — JaCoCo Plugin](https://docs.gradle.org/current/userguide/jacoco_plugin.html): coverage cho các task Test khác nhau.
- [Gradle — Java Test Fixtures Plugin](https://docs.gradle.org/current/userguide/java_testing.html#sec:java_test_fixtures): tái sử dụng test fixtures giữa suites/projects.
