# Fork tiến trình, `maxParallelForks` và tài nguyên dùng chung khi chạy test trong Gradle

Khi một project Java tăng từ vài chục lên hàng nghìn bài kiểm thử, thời gian chạy test thường chiếm phần lớn thời gian của lệnh `./gradlew build`. Gradle có thể tăng tốc bằng cách chia các **lớp kiểm thử** cho nhiều **tiến trình JVM test worker** chạy đồng thời. Nhưng việc chạy nhanh hơn chỉ đáng giá khi những bài test **không giẫm lên tài nguyên của nhau**: cùng cổng TCP, cùng file, cùng cơ sở dữ liệu, cùng tài khoản thử nghiệm hoặc cùng đối tượng bên ngoài.

Bài học thuộc phần **Kiểm thử** của *Build Tool Gradle*, tập trung vào ba tham số/hành vi hay bị nhầm:

- **Fork**: Gradle thực thi test trong một JVM con, tách khỏi JVM của Gradle Daemon.
- **`maxParallelForks`**: giới hạn số JVM test worker có thể thực thi **đồng thời cho một `Test` task**.
- **`forkEvery`**: giới hạn số test classes chạy trong **một JVM worker trước khi thay bằng JVM mới**.

Nội dung đi từ mô hình tiến trình, cấu hình Gradle Kotlin DSL, ví dụ **Java 17 + JUnit Jupiter 5** chạy được, quản trị CPU/RAM, `org.gradle.test.worker`, chống xung đột cổng/file/DB, phân biệt song song của Gradle và JUnit, đến cách chia unit/integration tests và gỡ lỗi flaky CI.

## 1. Fork trong Gradle Test là gì?

Với Java plugin, Gradle đăng ký một task kiểu `org.gradle.api.tasks.testing.Test` có tên mặc định `test`. Task này điều phối phát hiện, lập lịch và thu thập kết quả test từ JVM khác với JVM chạy Gradle.

```text
Gradle Daemon (quá trình cấu hình và điều phối build)
    |
    +-- :compileJava
    +-- :compileTestJava
    |
    +-- :test  (một task kiểu Test)
            |
            +-- Gradle Test Executor / worker JVM #1
            |       +-- ClassATest
            |       +-- ClassBTest
            |
            +-- Gradle Test Executor / worker JVM #2
                    +-- ClassCTest
                    +-- ClassDTest
```

Đây là **sơ đồ ví dụ** khi `maxParallelForks=2`; Gradle không bảo đảm class A/B luôn rơi vào worker #1 hay class C/D vào worker #2. Số lượng JVM thực sự còn phụ thuộc số classes, khả năng scheduling và tài nguyên build.

Lợi ích khi tách khỏi Gradle Daemon:

1. Test code không trực tiếp làm bẩn classpath/ứng dụng Java của Gradle Daemon.
2. Có thể đặt riêng **JVM heap, system properties, environment variables, JVM arguments, Java launcher** cho test.
3. Nếu một test làm hỏng static state hoặc tiêu tốn nhiều bộ nhớ, phạm vi tác động ít nhất được tách khỏi Gradle Daemon.
4. Gradle có thể tạo **nhiều workers** để phân phối test classes và rút ngắn tổng thời gian chạy nếu workload phù hợp.

Tuy nhiên, **fork không phải sandbox bảo mật**. JVM test vẫn thường có quyền của cùng user chạy Gradle: nó có thể đọc ghi filesystem, gọi network, DB, cloud sandbox theo credentials được cấp. Tách tiến trình cũng **không tự tách** cổng TCP, file trên disk hay server bên ngoài.

## 2. Phân biệt process, thread, test class và test method

| Cấp độ | Ví dụ | Cách điều khiển | Trạng thái/tài nguyên có thể chung |
| --- | --- | --- | --- |
| **Gradle build process** | Gradle Daemon | Gradle runtime, `org.gradle.jvmargs` | Build configuration, caches, task scheduling |
| **Gradle Test task** | `:app:test`, `:app:integrationTest` | `tasks.test { ... }` hoặc `tasks.withType<Test>()` | Một tập test classes, report và cấu hình thực thi |
| **Forked test JVM** | Gradle Test Executor 1/2 | `maxParallelForks`, `forkEvery` | Static fields, system properties, JVM heap bên trong fork |
| **JUnit test thread** | Thread chạy test method | JUnit Jupiter parallel configuration | Các thread trong **cùng một test JVM** chia sẻ static state |
| **Test class** | `FileATest` | Gradle/JUnit test discovery | Nhiều methods và lifecycle trong một class |
| **Test method** | `@Test void saves()` | JUnit engine execution mode | Có thể chạy tuần tự hoặc concurrent theo JUnit |

**`maxParallelForks=4` không có nghĩa một `@Test` method tự tạo bốn thread.** Nó chỉ cho Gradle dùng tối đa bốn **JVM worker processes** trong một `Test` task. Việc chạy nhiều methods trong **cùng worker** là một quyết định khác của JUnit Jupiter; JUnit 5 chạy tuần tự theo mặc định nếu chưa opt-in parallel execution.

Ngược lại, **`forkEvery=1` không có nghĩa chạy song song nhiều hơn**: nó chủ yếu làm JVM được thay sau mỗi test class, có chi phí khởi động lớn.

## 3. `maxParallelForks`: số JVM test đồng thời

Trong Kotlin DSL:

```kotlin
tasks.test {
    useJUnitPlatform()
    maxParallelForks = 2
}
```

Ý nghĩa:

- Mặc định: **`maxParallelForks = 1`**.
- Giá trị `2`: Gradle có thể duy trì **tối đa hai JVM workers cho cùng task `test`** tại một thời điểm.
- Giá trị `4`: tối đa bốn JVM workers, nếu có đủ test classes và worker capacity.
- Giá trị phải là số nguyên dương; `0` **không phải cách tắt parallelism**. Muốn chỉ một worker, dùng `1`.
- Đây là **giới hạn tối đa**, không cam kết chính xác từng đó worker luôn được tạo.

### Mối quan hệ với `--max-workers`

Gradle còn có giới hạn **global worker capacity** cho toàn build. Ví dụ:

```bash
./gradlew test --max-workers=2
```

Giới hạn này ảnh hưởng khả năng đồng thời của các tasks/worker operations, bao gồm các test worker JVMs. Theo tài liệu Gradle, `maxParallelForks` **không được lớn hơn** mức `max-workers` của build và Gradle cũng giới hạn tổng số test processes trên các `Test` tasks.

Vì thế, để demo `maxParallelForks=2` một cách rõ ràng, dùng lệnh:

```bash
./gradlew test --max-workers=2
```

Khi cần CI chạy trong container chỉ được 1 CPU/mức worker nhỏ, giảm cấu hình fork về `1` thay vì cố buộc số fork lớn.

### `--parallel` có phải `maxParallelForks` không?

**Không.**

- `--parallel`: cho Gradle lập lịch các **project tasks** có thể thực thi đồng thời khi dependency graph cho phép, chủ yếu quan trọng trong multi-project build.
- `--max-workers=N`: giới hạn worker capacity **trên toàn build**.
- `maxParallelForks=N`: giới hạn số forked JVMs **cho một task kiểu Test**.

Bạn có thể bật `maxParallelForks=2` mà **không cần** `--parallel`: một `:app:test` task đơn lẻ vẫn được phép phân phối test classes qua tối đa hai JVMs. Ngược lại, bật `--parallel` mà giữ `maxParallelForks=1` chỉ có nghĩa Gradle có thể chạy **các Test tasks khác nhau** đồng thời nếu có workers, chứ không tự chia một task test thành nhiều forks.

## 4. `forkEvery`: số lớp kiểm thử trên một JVM trước khi restart

Trong `build.gradle.kts`:

```kotlin
tasks.test {
    forkEvery = 50L
}
```

Ý nghĩa:

- Mặc định: **`forkEvery = 0`**, tức không đặt giới hạn số test classes trên một worker JVM; process có thể được tái sử dụng.
- `forkEvery = 1`: mỗi JVM test process chạy tối đa **một test class** rồi được thay bằng JVM khác.
- `forkEvery = 50`: một worker được thay sau khi chạy khoảng **50 test classes**.
- Tính theo **lớp kiểm thử**, không phải mỗi `@Test` method. Với framework không dựa trên class, Gradle có quy tắc tương ứng cho test definitions.

### Tại sao lại muốn restart JVM?

Một số test/framework để lại **static caches, classloaders, global registries, thread-local state** khó reset hoặc gây memory leaks khi chạy nhiều classes liên tục. Tái tạo JVM đôi khi giúp suite chạy ổn định hơn.

Nhưng cần thận trọng: **restart JVM là thao tác đắt**. Với 1.000 classes và `forkEvery=1`, Gradle có thể cần tạo rất nhiều JVMs trong suốt task, mất thời gian khởi động, JIT warm-up, framework initialization và tăng đỉnh tải CPU.

| Cấu hình | Số JVM đồng thời tối đa của một task | JVM được tái sử dụng giữa classes? |
| --- | --- | --- |
| `maxParallelForks=1, forkEvery=0` | 1 | Có; không có giới hạn số classes |
| `maxParallelForks=2, forkEvery=0` | 2 | Có; mỗi worker nhận nhiều classes theo scheduler |
| `maxParallelForks=2, forkEvery=1` | 2 | Không; mỗi JVM chạy tối đa một class |
| `maxParallelForks=4, forkEvery=100` | 4 | Có, nhưng mỗi worker được thay sau tối đa 100 classes |

**`forkEvery` không dùng để giải quyết mọi tài nguyên dùng chung**. Nếu class A ghi vào một database chung, JVM của class B vẫn có thể thấy dữ liệu đó sau khi A kết thúc, bất kể A và B chạy trên cùng JVM hay hai JVM khác nhau. Tài nguyên ngoài process không tự được reset khi fork kết thúc.

## 5. Một cấu hình thực tế cho Java 17 và JUnit 5

Với một project Java:

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()

    maxParallelForks = 2
    forkEvery = 0L

    maxHeapSize = "256m"

    testLogging {
        events("passed", "skipped", "failed")
        showStandardStreams = true
    }
}
```

Đây là cấu hình **Gradle Kotlin DSL**; project cần `settings.gradle.kts`, Java test sources và Gradle Wrapper/JDK phù hợp để chạy. `platform("org.junit:junit-bom:5.11.4")` giữ các phiên bản JUnit cùng dòng; `junit-jupiter` cung cấp API/engine, `junit-platform-launcher` phục vụ Gradle test launcher.

**Chi phí bộ nhớ:** `maxHeapSize="256m"` là trần **heap của mỗi test JVM**, không phải tổng RAM của toàn build. Hai test processes có thể tiêu thụ **2 × 256 MiB heap** cùng lúc, cộng metaspace, code cache, thread stacks, native memory, Gradle Daemon và compiler/other processes. Đây là ước lượng heap ceiling chứ không phải số RAM thực tế chắc chắn dùng.

**Khuyến nghị đầu tiên khi tối ưu:** bắt đầu `maxParallelForks=1`, đo baseline, tăng lên 2, so test duration/CPU/RAM/flaky rate rồi mới cân nhắc 4 hoặc nhiều hơn. Không copy cấu hình forks từ máy developer 32 cores vào CI container 2 cores mà không đo.

## 6. Ví dụ hoàn chỉnh: bốn lớp kiểm thử không xung đột file/cổng

Project dưới đây **chạy được với Java 17, JUnit 5 và Gradle Kotlin DSL**, chỉ tải JUnit từ Maven Central. Nó chứng minh:

- Gradle có thể phân phối **nhiều test classes** vào các worker JVMs khi `maxParallelForks=2`.
- `@TempDir` cung cấp thư mục tạm riêng cho test, tránh hai classes ghi cùng tên file cố định.
- `new ServerSocket(0)` để hệ điều hành chọn cổng trống trong lúc binding.
- `org.gradle.test.worker` cho biết định danh test worker được Gradle cấp; không khẳng định **số id hoặc thứ tự in** luôn giống nhau.

### 6.1. Cấu trúc thư mục

```text
gradle-test-fork-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/test/java/demo/
    ├── FileIsolationATest.java
    ├── FileIsolationBTest.java
    ├── PortIsolationTest.java
    └── ForkIdentityTest.java
```

Không cần `src/main/java` để chạy bộ tests này. Gradle Wrapper phải được tạo hợp lệ theo tài liệu chính thức, không viết thủ công `gradle-wrapper.jar`. Java toolchain 17 phải được cấp sẵn hoặc provisioning theo chính sách project; cần network/cache để resolve JUnit.

### 6.2. File `settings.gradle.kts`

```kotlin
rootProject.name = "gradle-test-fork-demo"
```

### 6.3. File `build.gradle.kts` đầy đủ

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()

    maxParallelForks = 2
    forkEvery = 0L

    maxHeapSize = "256m"

    testLogging {
        events("passed", "skipped", "failed")
        showStandardStreams = true
    }
}
```

Không bật JUnit parallel methods trong demo. **Gradle sẽ điều phối ở cấp class qua các forks**; trong mỗi JVM, Jupiter mặc định chạy methods tuần tự. Vì thế ví dụ dễ phân tích hơn thay vì đồng thời trộn hai tầng parallelism.

### 6.4. `src/test/java/demo/FileIsolationATest.java`

```java
package demo;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class FileIsolationATest {
    @Test
    void writesIndependentFile(@TempDir Path tempDir) throws Exception {
        Path file = tempDir.resolve("result.txt");
        Files.writeString(file, "A", StandardCharsets.UTF_8);
        assertEquals("A", Files.readString(file, StandardCharsets.UTF_8));
    }
}
```

JUnit inject một temporary directory dành cho test. Nếu `FileIsolationBTest` cũng tạo file `result.txt`, nó không dùng cùng đường dẫn vì `tempDir` khác. Code chỉ dùng Java NIO và JUnit Jupiter.

### 6.5. `src/test/java/demo/FileIsolationBTest.java`

```java
package demo;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class FileIsolationBTest {
    @Test
    void writesDifferentIndependentFile(@TempDir Path tempDir)
            throws Exception {
        Path file = tempDir.resolve("result.txt");
        Files.writeString(file, "B", StandardCharsets.UTF_8);
        assertEquals("B", Files.readString(file, StandardCharsets.UTF_8));
    }
}
```

Điểm mấu chốt: cùng tên **`result.txt`**, nhưng **khác thư mục tạm**. Nó khác hoàn toàn với việc cả hai tests cùng viết vào `Path.of("build/result.txt")` hoặc `/tmp/result.txt`.

### 6.6. `src/test/java/demo/PortIsolationTest.java`

```java
package demo;

import java.net.ServerSocket;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

final class PortIsolationTest {
    @Test
    void letsOperatingSystemChoosePort() throws Exception {
        try (ServerSocket server = new ServerSocket(0)) {
            int assignedPort = server.getLocalPort();
            assertTrue(assignedPort > 0);
        }
    }
}
```

`new ServerSocket(0)` yêu cầu hệ điều hành **chọn một cổng khả dụng và bind ngay**. Cổng thực tế khác nhau theo môi trường và thời điểm; **không có một số port output cố định**. Đóng socket bằng try-with-resources giải phóng cổng khi test hoàn tất.

Đừng gọi một hàm “find free port” rồi đóng socket và khởi động server sau đó với port vừa tìm: có thể có **TOCTOU race** vì process khác chiếm cổng trước khi server thực sự bind. Nếu framework hỗ trợ port 0 hoặc dynamic port binding, hãy để **chính server** bind và đọc port được cấp.

### 6.7. `src/test/java/demo/ForkIdentityTest.java`

```java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

final class ForkIdentityTest {
    @Test
    void printsGradleWorkerIdentifier() {
        String workerId = System.getProperty("org.gradle.test.worker");

        assertNotNull(workerId);
        assertFalse(workerId.isBlank());

        System.out.println("Gradle test worker = " + workerId);
    }
}
```

Gradle đặt system property **`org.gradle.test.worker`** trong mỗi test process. Giá trị dùng để tạo tài nguyên phân biệt các workers, nhưng **không được đoán trước**, không dùng để tạo ID nghiệp vụ ổn định lâu dài và không dùng làm chỉ số chắc chắn của test class nào chạy trước.

Chạy `ForkIdentityTest` trực tiếp từ một JUnit IDE runner **không dùng Gradle Test task** thì property có thể không có; assertion trong demo này **chủ đích yêu cầu Gradle runner**.

### 6.8. Các lệnh chạy

Linux/macOS:

```bash
./gradlew clean test --max-workers=2 --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test --max-workers=2 --console=plain
```

Nếu muốn chủ động chạy lại dù Gradle coi task up-to-date:

```bash
./gradlew test --rerun-tasks --max-workers=2 --console=plain
```

Với các test sources đúng như trên, kỳ vọng **4 test methods PASS**:

| Test class | Test method | Điều được kiểm chứng |
| --- | --- | --- |
| `FileIsolationATest` | `writesIndependentFile` | File tạm của A chứa `A` |
| `FileIsolationBTest` | `writesDifferentIndependentFile` | File tạm của B chứa `B` |
| `PortIsolationTest` | `letsOperatingSystemChoosePort` | TCP socket được bind trên một port hợp lệ |
| `ForkIdentityTest` | `printsGradleWorkerIdentifier` | Gradle cung cấp nonblank worker ID |

Dòng **stdout của `ForkIdentityTest`** có dạng:

```text
Gradle test worker = <id do Gradle cấp>
```

Dấu `<id do Gradle cấp>` là ký hiệu **mô tả giá trị thay đổi**, không phải chuỗi thực được test in ra. Ví dụ thực tế có thể là `Gradle test worker = 1` hoặc một worker ID khác. **Không có thứ tự thực thi test classes cố định** và Gradle không cam kết sẽ luôn tạo đủ hai forks nếu việc lập lịch không đòi hỏi.

Sau khi chạy, mở báo cáo HTML:

```text
build/reports/tests/test/index.html
```

JUnit XML thường ở `build/test-results/test/`. Các reports giúp xem class/test method nào PASS hoặc FAIL, thời gian và stdout/stderr đã được thu thập. **Đừng assert lên thứ tự log được in từ các worker JVMs.**

### 6.9. So sánh một fork và hai forks

Chỉnh file `build.gradle.kts`:

```kotlin
tasks.test {
    useJUnitPlatform()
    maxParallelForks = 1
}
```

Sau đó chạy `./gradlew test --rerun-tasks --max-workers=2`. Bốn tests vẫn phải PASS; Gradle dùng **tối đa một test JVM tại một thời điểm cho task**.

Đổi lại `maxParallelForks = 2` và chạy với cùng `--max-workers=2`. Tests vẫn phải PASS. Với workload nhỏ, thời gian chạy thực tế **có thể không giảm**, thậm chí tăng vì chi phí khởi động hai JVMs. Với hàng trăm lớp kiểm thử độc lập, tốc độ có thể cải thiện rõ hơn.

**Không suy rằng hai forks luôn nhanh gấp đôi**. Hiệu quả phụ thuộc độ dài tests, CPU scheduling, số class đủ để phân phối, I/O, DB/remote services và overhead.

## 7. Tài nguyên dùng chung: vì sao hai JVMs vẫn có thể gây race?

Giả sử hai classes cùng dùng một file:

```java
// Minh họa CỐ TÌNH KHÔNG AN TOÀN, không đưa vào bản demo chuẩn:
Path file = Path.of("build", "shared-result.txt");
Files.writeString(file, "expected");
assertEquals("expected", Files.readString(file));
```

Nếu test A ghi `expected-A`, test B ghi `expected-B`, thứ tự xen kẽ có thể là:

```text
Worker JVM #1: ghi expected-A vào build/shared-result.txt
Worker JVM #2: ghi expected-B vào build/shared-result.txt
Worker JVM #1: đọc file, thấy expected-B -> FAIL
```

Một biến `synchronized`/static lock trong JVM #1 **không thể khóa** static state trong JVM #2. Hai JVMs có heap và monitor locks **riêng**.

Cùng nguyên lý với:

- Hai embedded HTTP servers cùng `bind(8080)`.
- Hai tests cùng `DROP TABLE users` hoặc xóa dữ liệu trong chung test database/schema.
- Hai JVMs ghi cùng output filename hoặc cùng cache directory.
- Hai tests cùng thao tác một file cấu hình JSON, một cloud bucket hay một message queue subscription.
- Các tests chạy đồng thời với một server **được share bên ngoài JVM** và kỳ vọng trạng thái sạch.
- Test dùng cùng tên tài khoản, cùng email hoặc cùng transaction ID ở một môi trường staging.

**Fork cách ly memory, không cách ly tài nguyên ngoài tiến trình.** Đây là nguyên nhân chính của flaky tests khi tăng `maxParallelForks`.

## 8. Chiến lược 1: không chia sẻ file tạm

Ưu tiên **`@TempDir` của JUnit Jupiter** trong unit tests:

```java
@Test
void saves(@TempDir Path dir) throws Exception {
    Path file = dir.resolve("data.json");
    Files.writeString(file, "{\"ok\":true}");
    assertEquals("{\"ok\":true}", Files.readString(file));
}
```

Đây là **mảnh method** cần nằm trong class có imports `org.junit.jupiter.api.Test`, `org.junit.jupiter.api.io.TempDir`, Java `Files`, `Path`, và `assertEquals`. Bản demo ở phần 6 có đầy đủ imports và compile được.

Lợi ích:

- Mỗi test được cấp một directory riêng theo lifecycle Jupiter.
- Tên file `data.json` có thể giống nhau trong các tests khác nhau, vì directory khác nhau.
- JUnit quản lý việc dọn tài nguyên theo lifecycle và cấu hình cleanup policy.
- Không cần tạo random path thủ công rồi quên cleanup.

Nếu test dùng một external process không biết đến `@TempDir`, truyền đường dẫn riêng qua constructor/env/CLI argument của process đó. Không tự ghi file vào project root hoặc `src/test/resources` khi test cần mutating data.

### `java.io.tmpdir` không tự là unique cho từng fork

`System.getProperty("java.io.tmpdir")` thường trỏ một **thư mục chung của hệ điều hành**. Hai test JVMs có thể đều thấy cùng path gốc. Chỉ đổi sang `java.io.tmpdir` mà vẫn viết một file cố định `report.txt` sẽ **không giải quyết race**.

Các cách đúng:

- `Files.createTempFile(...)` hoặc `Files.createTempDirectory(...)` (JDK tạo tên riêng).
- JUnit `@TempDir` cho unit tests.
- Namespace theo worker ID + test ID + build/job ID khi bắt buộc dùng một work root được chia sẻ.
- Cleanup có chủ đích, không xóa root directory mà process khác vẫn sử dụng.

## 9. Chiến lược 2: `org.gradle.test.worker` để đặt tên tài nguyên

Gradle docs chỉ rõ mỗi test process có property:

```java
String worker = System.getProperty("org.gradle.test.worker");
```

Một test có thể dùng:

```java
// Mảnh method/test, cần imports Path, Files, Test:
String worker = System.getProperty("org.gradle.test.worker");
Path root = Path.of(System.getProperty("java.io.tmpdir"),
                    "app-tests", "worker-" + worker);
Files.createDirectories(root);
```

Điều này hữu ích khi framework hoặc test fixture cần **một directory cho cả worker JVM** thay vì một directory cho từng method. Nhưng cần xét các giới hạn:

1. **Nhiều classes có thể được chạy tuần tự trên cùng worker**, do đó dùng mỗi worker ID không đảm bảo các classes trong worker được cách ly với nhau. Cần reset/dọn dữ liệu hoặc thêm test/class identifier.
2. **Các Gradle builds khác nhau** trên cùng máy/CI runner có thể dùng lại cùng format worker ID. Không suy rằng ID này là global unique giữa tất cả builds trên mọi máy/thời điểm.
3. Nếu dùng cùng thư mục persistent giữa các build runs, data từ lần trước có thể còn lại. Dùng **run/session id** hoặc tạo temp directory ngẫu nhiên và cleanup.
4. Property do Gradle cung cấp **trong test worker**; đừng đọc nó ở buildscript configuration như một JVM system property của Daemon rồi mong thấy worker ID.
5. Một test chạy từ IDE runner không qua Gradle có thể không có property; nếu cùng code cần hỗ trợ IDE, nên có fallback hợp lý thay vì ghép `null` vào resource path.

Ví dụ helper Java với fallback dành cho IDE:

```java
String gradleWorker =
        System.getProperty("org.gradle.test.worker", "local");
```

Mảnh này là **cách đặt nhãn**, không phải khóa toàn cục. Cần kết hợp directory riêng, dữ liệu riêng và locking nếu các tests còn chia sẻ resource bên ngoài.

### Truyền root từ Gradle sang worker

Với một `Test` task:

```kotlin
tasks.test {
    val root = layout.buildDirectory.dir("test-work").get().asFile
    systemProperty("demo.test.workRoot", root.absolutePath)
}
```

Đây là **mảnh cấu hình** trong project có Java plugin. Nó chỉ truyền **cùng một root path** tới các worker JVMs; chính Java test code phải chia tiếp thành thư mục theo worker/test/build. Không nên cho mọi test ghi trực tiếp `root/result.json`.

Đối với code cần Configuration Cache mạnh, nên tránh đọc Project/Gradle model từ test task actions. Nếu root path trở thành task input/output được cache, cần mô hình hóa đầu vào/đầu ra và worker-specific files cẩn thận, không tự biến một thư mục mutable chung thành output của nhiều Test tasks.

## 10. Chiến lược 3: cấp port động, không hard-code `8080`

Ví dụ không an toàn khi hai test workers cùng khởi động server:

```java
// Chỉ là mảnh minh họa lỗi, không chạy đồng thời trên máy dùng chung.
try (ServerSocket server = new ServerSocket(8080)) {
    // ...
}
```

Nếu JVM #1 giữ port `8080`, JVM #2 có thể nhận `java.net.BindException: Address already in use`. Một `Thread.sleep(1000)` trước lúc bind không giải quyết gốc rễ; nó chỉ khiến lỗi khó tái hiện hơn.

Cách đúng khi framework hỗ trợ:

```java
try (ServerSocket server = new ServerSocket(0)) {
    int port = server.getLocalPort();

    // Khởi động client thử nghiệm với port thực tế.
    // Giữ server/socket đã bind khi client kết nối.
}
```

**Không tách “tìm port trống” rồi bind sau**:

```text
1. Open ServerSocket(0) -> nhận port P
2. Close socket
3. Mở server mới trên P
```

Giữa bước 2 và bước 3, một process khác có thể bind P. Nên để chính server/framework cần test bind port 0, rồi đọc port từ server đang mở. Với Spring Boot, có cơ chế RANDOM_PORT tương ứng; với một HTTP server tự xây, truyền port 0 vào constructor/framework builder nếu được hỗ trợ.

Nếu một external service **bắt buộc dùng port cố định**, hãy chọn một trong hai hướng:

- Chạy integration tests liên quan **tuần tự** và bảo đảm service không bị dùng bởi build khác.
- Cấp **service instance/namespace/container/host riêng** cho từng fork hoặc từng CI job, có quản lý vòng đời rõ ràng.

## 11. Chiến lược 4: cách ly cơ sở dữ liệu và dịch vụ bên ngoài

Database là tài nguyên chia sẻ thường gây lỗi khó nhất. Các tests có thể tranh chấp:

- Cùng schema/tables và records có ID cố định.
- `TRUNCATE`, `DROP TABLE` hoặc migration cùng lúc.
- Cùng account/auth session.
- Cùng named advisory lock hoặc global sequence.
- Cùng Redis keys, cache namespace hoặc message queue topic/subscription.
- Pool connection capacity giới hạn, dẫn đến timeout khi tăng fork count.

### Các cấp độ cách ly DB

| Phương án | Lợi ích | Giới hạn |
| --- | --- | --- |
| Transaction rollback sau từng test | Dữ liệu không tồn tại lâu nếu mọi thao tác ở cùng transaction | Async workers/commits bên ngoài transaction có thể vẫn ghi dữ liệu |
| Schema/database riêng theo test worker | Tránh va chạm tables/records giữa workers | Phải tạo, migrate và cleanup từng schema |
| Database/container riêng theo test class hoặc worker | Cách ly mạnh, dễ mô hình hóa fixtures | Chi phí RAM/CPU/startup cao |
| Namespace riêng cho key/tenant | Hợp với Redis/message queues/multi-tenant stores | Code/test phải tuân theo namespace |
| Một integration Test task chạy tuần tự | Đơn giản khi service chỉ có một instance | Có thể chậm; vẫn xung đột với build/CI job khác |
| CI environment độc lập cho mỗi job | Tránh cross-job collisions | Tăng chi phí provisioning và vận hành |

**Testcontainers** có thể giúp cấp containerized DB/service theo test lifecycle và dùng dynamically assigned exposed ports. Nhưng không tự tuyên bố rằng “dùng Testcontainers là luôn isolation”: nếu tests cùng dùng một **shared singleton container** và cùng schema, vẫn có thể va chạm trong cùng/các workers theo cách quản lý fixtures.

Một thiết kế an toàn hơn:

1. Xác định phạm vi resource cần riêng: test method, class, worker, Test task hay CI job.
2. Tạo resource ở cùng phạm vi đó.
3. Truyền endpoint/schema/credentials cụ thể vào test.
4. Đảm bảo cleanup khi PASS và khi FAIL.
5. Hạn chế connection pool để tổng số connections không vượt DB quota.
6. Không dùng chung test data/migration destructive với môi trường production/staging thật.

### Về transactions và rollback

Rollback chỉ cô lập được những thay đổi thực sự thuộc **transaction đó**. Một background job, một server khác, hoặc message consumer có thể dùng transaction khác và commit dữ liệu. Khi test thực hiện multi-service workflow, database rollback trong JUnit thread chưa chắc đã xóa mọi side effect. Cần unique IDs, per-job namespace, disposable resources và test fixtures độc lập.

## 12. Hai tầng song song: Gradle forks và JUnit Jupiter threads

JUnit Jupiter hỗ trợ parallel execution riêng, được cấu hình qua `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=2
```

**Không thêm tệp này vào bản demo chuẩn ở phần 6** nếu bạn muốn chỉ có concurrency cấp Gradle forks. Đây là **thí nghiệm nâng cao**, dùng để nhìn thấy tầng thứ hai.

Nếu:

```text
Gradle Test task: maxParallelForks = 3
Mỗi JVM worker: JUnit parallelism ~ 2
```

thì trong điều kiện phù hợp, có thể có **nhiều test methods/threads chạy đồng thời bên trong mỗi fork**. Số lượng chạy thực tế phụ thuộc JUnit execution modes, class lifecycles, scheduler, resource locks và giới hạn worker capacity. Không coi phép nhân `3 × 2 = 6` là cam kết luôn có sáu tests chạy cùng lúc.

**JUnit Jupiter theo mặc định là tuần tự**, kể cả khi Gradle `maxParallelForks` lớn hơn 1. Để methods chạy concurrent, cần bật JUnit parallel mode/annotations tương ứng.

### So sánh

| Mục đích | Gradle `maxParallelForks` | JUnit Jupiter parallel |
| --- | --- | --- |
| Đơn vị chạy đồng thời chủ đạo | Test classes trên **JVM khác nhau** | Classes/methods trên **threads trong cùng JVM** |
| Có tách static fields giữa hai đơn vị? | Có, nếu ở hai JVMs khác nhau | Không, threads dùng chung JVM static state |
| Có tách OS ports/files/DB? | Không | Không |
| `synchronized`/Java monitor bảo vệ trên toàn phạm vi? | Chỉ trong một JVM | Bảo vệ các threads cùng JVM nếu dùng đúng lock |
| `@ResourceLock` của JUnit điều phối? | Không đồng bộ các JVMs với nhau | Có tác dụng trong phạm vi JUnit engine/test execution tương ứng |
| Phù hợp | Nhiều test classes độc lập, tận dụng CPU cores | Methods/classes thread-safe trong cùng JVM |

Nếu đang gỡ một lỗi flaky, **chỉ bật một tầng parallelism mỗi lần**. Đầu tiên đảm bảo `maxParallelForks=1` và JUnit parallel tắt. Sau đó tăng Gradle forks, kiểm tra; cuối cùng mới bật JUnit threads nếu suite thật sự thread-safe và bạn đã đo được lợi ích.

## 13. `@ResourceLock` của JUnit 5: hữu ích nhưng không khóa được giữa các JVMs

JUnit Jupiter hỗ trợ gắn resource locks khi nhiều test methods/classes chạy song song **trong cùng một engine/test process**.

Ví dụ:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

import static org.junit.jupiter.api.Assertions.assertTrue;

class ResourceLockedTest {
    @Test
    @ResourceLock(value = "shared-config", mode = ResourceAccessMode.READ_WRITE)
    void editsSharedConfig() {
        assertTrue(true);
    }
}
```

Ví dụ trên là **Java test class độc lập nếu có JUnit Jupiter dependency**. `@ResourceLock` cho JUnit biết các tests tranh cùng logical resource `shared-config` không nên được chạy concurrent trái với chế độ truy cập đã khai báo **trong cùng một JUnit execution scope**.

Nhưng với `maxParallelForks=2`, hai classes có `@ResourceLock("shared-config")` **có thể nằm ở hai JVM test workers khác nhau**. Mỗi process có JUnit engine/lock state riêng; annotation này **không phải distributed lock**, nên không bảo đảm khóa cross-process trên cùng file/port/database.

Các cách cần dùng khi resource thật sự chỉ có một:

- Đặt tất cả tests nhạy cảm vào một **`Test` task chạy `maxParallelForks=1`** và không bật JUnit method parallelism.
- Dùng một cơ chế **OS-level file lock**, database advisory lock hoặc distributed lock nếu thật sự phải phối hợp giữa processes/machines, cùng timeout/error handling.
- Tạo **resource instance/namespace riêng** cho từng JVM/CI job để tránh cần lock.
- Kiểm soát **nhiều Test tasks/multi-project/CI jobs**, vì một task serial không ngăn task khác hoặc build khác dùng cùng DB.

**`@ResourceLock` rất hữu ích cho JUnit thread-level concurrency, nhưng không được quảng bá là giải pháp cho xung đột giữa hai Gradle forks.**

## 14. Tách unit tests và integration tests theo đặc tính tài nguyên

Một phương án thực tế: **unit tests** không dùng shared external resources nên được phép chạy nhiều forks; **integration tests** dùng một DB hoặc external service duy nhất nên bắt đầu tuần tự.

Ví dụ khi đã có hai `Test` tasks hợp lệ:

```kotlin
tasks.named<Test>("test") {
    useJUnitPlatform()
    maxParallelForks = 4
}

tasks.named<Test>("integrationTest") {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0L
}
```

**Đây là mảnh cấu hình**, không phải full build runnable: `integrationTest` chưa được Java plugin mặc định tạo. Cần đăng ký JVM Test Suite `integrationTest`, hoặc tự tạo source set/configurations và một Test task hợp lệ, rồi khai báo CI/check dependencies cho task đó.

### JVM Test Suite plugin (mô hình khuyến nghị)

Các phiên bản Gradle hiện đại có `jvm-test-suite` plugin để khai báo các test suites ngoài `test`. Khi muốn áp dụng cấu hình unit/integration theo tasks, bạn cần xác định tên test task phát sinh (thường `integrationTest`) và suites dependencies.

Quan trọng: Một Test task có `maxParallelForks=1` chỉ ngăn **nhiều JVMs bên trong task đó**. Nó không ngăn một task khác hoặc một subproject khác chạy integration tests đồng thời trên **cùng một database** nếu Gradle task scheduling/CI cho phép.

### Không dùng `shouldRunAfter` như mutex

`shouldRunAfter` là ordering preference, không phải cơ chế ngăn mọi tasks cùng dùng một resource, đặc biệt giữa nhiều builds độc lập. `mustRunAfter` tạo ràng buộc thứ tự khi cả hai tasks nằm trong graph, nhưng vẫn không bảo vệ resource đối với external processes.

Nếu cần điều phối giữa nhiều Gradle Test tasks **trong cùng build**, có thể sử dụng **shared Build Service** với `maxParallelUsages=1` và khai báo `usesService` cho các tasks cạnh tranh. Cách này điều phối **task-level** trong Gradle, **không tự khóa các test classes bên trong một Test task có `maxParallelForks>1`**, cũng không khóa CI jobs hoặc Gradle builds khác.

Nếu cần đồng bộ giữa nhiều CI runners, phải dùng resource/locking solution ở bên ngoài Gradle hoặc cấp riêng resource cho từng job.

## 15. Thiết lập JVM heap, garbage collector và giới hạn máy CI

Một Test task có thể cấu hình memory và JVM options:

```kotlin
tasks.withType<Test>().configureEach {
    maxHeapSize = "512m"
    minHeapSize = "128m"

    // Ví dụ chỉ dùng khi có vấn đề cụ thể cần chẩn đoán:
    jvmArgs("-Dfile.encoding=UTF-8")
}
```

Đây là **mảnh cấu hình**. Với Java 17, `-Dfile.encoding=UTF-8` chỉ là cách truyền system property cho Java fork; nó không thay thế nhu cầu kiểm soát charset khi đọc ghi file (`Files.writeString`, `StandardCharsets.UTF_8`) hoặc toolchain configuration.

### Lập ngân sách RAM

Giả sử một container CI có RAM limit 3 GiB, hai test forks với `maxHeapSize="512m"`:

```text
Test heaps potential max:  2 × 512 MiB = 1024 MiB
Gradle Daemon heap:        cấu hình riêng, ví dụ -Xmx768m
Metaspace/thread/native:  cộng thêm cho cả daemon/test JVMs
Compiler/other tasks:     cộng thêm tùy thời điểm
OS/container overhead:    cộng thêm
```

Đây **không phải** dự đoán lượng RSS chính xác. JVM heap limit chỉ ràng buộc một phần bộ nhớ, còn metaspace, direct buffers, thread stacks, JIT/code cache, native libraries và external services tiêu thụ RAM khác.

Giảm fork count có thể ổn định CI hơn khi:

- CI job bị **OOMKilled** hoặc exit 137.
- CPU thực được cấp thấp hơn số cores mà Gradle/JDK nhận diện.
- Mỗi test JVM khởi tạo Spring context lớn hoặc ORM/DI graph tốn RAM.
- Database/container/resource pool không chịu được nhiều connections.
- Tăng forks không giảm thời gian do lock contention hoặc I/O bottleneck.

**Tăng `-Xmx` cho Gradle Daemon không tự tăng heap của forked Test JVMs.** Gradle Daemon JVM arguments (`org.gradle.jvmargs`) và Test task `maxHeapSize` là hai cấu hình khác nhau.

## 16. Chọn số forks theo môi trường thay vì hard-code vô điều kiện

Một giải pháp rõ ràng cho CI là cấu hình qua Gradle project property:

```kotlin
// Mảnh thay cho cấu hình maxParallelForks cố định trong tasks.test.
val requestedTestForks = providers.gradleProperty("testForks")
    .map(String::toInt)
    .orElse(1)

tasks.withType<Test>().configureEach {
    maxParallelForks = requestedTestForks.get().coerceAtLeast(1)
}
```

Chạy mặc định:

```bash
./gradlew test --max-workers=2
```

Theo code trên, `testForks` mặc định là **1**, dù `--max-workers=2`. Khi muốn thử hai forks:

```bash
./gradlew test -PtestForks=2 --max-workers=2
```

**Phải điều phối hai giá trị này**: số forks yêu cầu không nên vượt global worker capacity. Nếu một CI runner chỉ được phép một worker, đặt `-PtestForks=1 --max-workers=1`.

Gradle cũng có thể đọc property từ `gradle.properties`, ví dụ:

```properties
testForks=2
```

Nhưng đừng commit `testForks=8` như mặc định tổ chức nếu các CI runners không đủ tài nguyên. Với máy có số cores khác nhau, tính fork count từ `Runtime.getRuntime().availableProcessors()` là lựa chọn có thể thử (Gradle performance guide có ví dụ dùng một nửa số cores), nhưng vẫn cần đảm bảo **không vượt max-workers** và tôn trọng container quotas.

### Không giả định số CPUs báo về luôn là quota thật

Trong Docker/Kubernetes, JVM/Gradle thường nhận diện container quotas tốt hơn ở các phiên bản hiện đại, nhưng môi trường không đồng nhất. Chạy `./gradlew --version` và quan sát CPU/RAM metrics từ runner/container khi chọn fork count; không có công thức đúng cho mọi suite.

## 17. Multi-project build: nhiều Test tasks cùng tranh worker capacity

Ví dụ repository:

```text
root/
├── api/
│   └── src/test/java/...
├── database/
│   └── src/test/java/...
└── app/
    └── src/test/java/...
```

Mỗi project có task `:api:test`, `:database:test`, `:app:test`. Khi chạy:

```bash
./gradlew test --parallel --max-workers=4
```

Gradle có thể thực thi các task test thuộc các projects khác nhau đồng thời nếu dependency graph cho phép. Nếu mỗi task tự khai báo `maxParallelForks=4`, **không suy rằng 3 × 4 = 12 test JVMs chắc chắn chạy cùng lúc**; Gradle có global worker limit và phân bổ scheduling.

Tuy nhiên, mức tải thực tế vẫn có thể lớn do các tasks khác, services và một số tiến trình ngoài Gradle. Hãy nhìn **CPU, resident memory, disk I/O, DB connections, container count**, chứ không chỉ nhân các cài đặt.

### Xung đột tài nguyên xuyên project

Hai project `:api:test` và `:database:test` đều dùng một Postgres server trong CI. Dù mỗi task có `maxParallelForks=1`, **hai tasks vẫn có thể chạy đồng thời** khi `--parallel` bật và worker capacity đủ.

Giải pháp:

- Tách database/schema/port theo project/job.
- Di chuyển những integration tests có dependency chung sang một suite được quản lý tập trung.
- Dùng shared Gradle Build Service để hạn chế task concurrency **trong một build** khi cần, với cấu hình `usesService` đúng.
- Nếu một DB được dùng bởi nhiều CI jobs độc lập, dùng resource coordinator ở cấp CI/environment thay vì chỉ task ordering trong một Gradle invocation.

**Giới hạn test forks và task parallelism là hai bài toán khác nhau.**

## 18. `forkEvery=1` không sửa được flaky tests chia sẻ cổng hoặc DB

Xét sequence:

```text
JVM #1 / ClassATest: bind port 9090
JVM #2 / ClassBTest: bind port 9090 -> BindException
```

Đổi `forkEvery=1` có nghĩa mỗi JVM mới được dùng cho một class, nhưng `maxParallelForks=2` vẫn có thể khiến hai classes chạy **đồng thời** và tranh cùng port. Không hề giải quyết lỗi.

Ngược lại, đặt `maxParallelForks=1` có thể ngăn hai classes trong **một Test task** chạy đồng thời; nhưng nếu một class để lại external server/process không cleanup hoặc project khác cũng bind port, lỗi vẫn xảy ra.

Vì vậy thứ tự sửa:

1. **Cô lập tài nguyên** hoặc quản lý vòng đời resource đúng.
2. Nếu resource chỉ có một instance, **giảm concurrency** ở scope phù hợp.
3. Chỉ xem xét `forkEvery` để xử lý các vấn đề **JVM-internal state/leak**, không dùng nó như mutex cho external resources.

### Một ví dụ state leak thực sự có thể cần fork

Test A:

```java
System.setProperty("demo.mode", "legacy");
```

Test B ở **cùng JVM** đọc `System.getProperty("demo.mode")` và kỳ vọng không có giá trị, nhưng Test A quên cleanup. `forkEvery=1` có thể che hiện tượng nếu hai classes không còn chia sẻ JVM, nhưng giải pháp lâu dài là test A **khôi phục system property trong `@AfterEach`/try-finally** hoặc thiết kế không phụ thuộc state chung.

Nếu Gradle phân phối hai classes vào **hai worker JVMs khác nhau**, chúng đã cách ly system properties; đừng kết luận suites đã sạch. Các tests vẫn phải hoạt động ổn định khi chạy tuần tự cùng fork và khi chạy độc lập.

## 19. Debug tests khi nhiều forks được bật

Khi đang điều tra lỗi logic hoặc cần attach debugger, nên giảm số forks về `1` để tránh nhiều JVMs tranh debug port:

```kotlin
tasks.test {
    maxParallelForks = 1
}
```

Sau đó:

```bash
./gradlew test --debug-jvm --max-workers=1
```

Gradle Test task hỗ trợ JVM debugging theo cơ chế CLI/plugin. Khi bật debug cho fork, Java process có thể **chờ debugger attach** trước khi chạy tests. Hãy attach đúng địa chỉ/port được Gradle thông báo; không hard-code một debug port giống nhau cho nhiều forks.

Nếu chỉ muốn chạy một lớp test:

```bash
./gradlew test --tests demo.FileIsolationATest --max-workers=1
```

Để chạy một test method:

```bash
./gradlew test --tests demo.FileIsolationATest.writesIndependentFile --max-workers=1
```

Công cụ này hữu ích để so sánh:

- Test đơn lẻ PASS nhưng cả suite FAIL → nghi shared state/order dependency.
- `maxParallelForks=1` PASS nhưng `2` FAIL → nghi resource collision/concurrent external state.
- Clean run PASS nhưng incremental run FAIL → nghi stale generated/resource inputs hoặc test fixture lifecycle.
- Trên developer PASS nhưng CI FAIL → so JDK, max-workers, heap, OS, timezone, ports, DB permissions, test data và container resources.

**Không dùng `--continue` hoặc `ignoreFailures=true` để tuyên bố flaky tests đã sửa.** Chúng thay đổi cách Gradle xử lý lỗi của build, không loại bỏ race.

## 20. Báo cáo, stdout và lập lịch không xác định

Gradle có thể thu thập:

```text
build/reports/tests/test/index.html
build/test-results/test/TEST-demo.FileIsolationATest.xml
build/test-results/test/TEST-demo.FileIsolationBTest.xml
...
```

Đường dẫn XML cụ thể có thể phụ thuộc bộ test/Gradle version và cấu hình reporting; ví dụ trên minh họa các class-level report files.

Khi nhiều JVMs cùng test:

- Thứ tự class hoàn thành **không ổn định**.
- Thứ tự các dòng console `println` từ nhiều workers **không nên dùng làm business assertion**.
- Test output có thể bị Gradle gom vào per-test descriptors/reports.
- Một test chỉ PASS do chạy trước test khác là **order-dependent** và cần sửa, không phải điều bạn nên “cố định” bằng class naming.
- `--tests` filter chỉ thay test selection, không bảo đảm một lịch chạy lặp lại như production suite.

Nếu đang đo hiệu năng, dùng duration ở test report/CI và so nhiều lần chạy. Một lần chạy nhanh hơn có thể chỉ do filesystem/Gradle dependency caches đã warm.

## 21. Phương pháp benchmark trước khi tăng forks

Một quy trình đo có kiểm soát:

1. Chốt **cùng commit, JDK/toolchain, Gradle Wrapper, test dataset và CPU/RAM quota**.
2. Chạy baseline `maxParallelForks=1` với số worker phù hợp.
3. Chạy cấu hình `2` forks; giữ JUnit method parallelism tắt để đo riêng một biến.
4. Chạy vài lượt, ghi **median test task time**, peak RSS/memory, CPU utilization và flaky failures.
5. Nếu cải thiện thực sự và không phát sinh race, thử `3`/`4` forks trong giới hạn machine/CI capacity.
6. Nếu test duration bị chi phối bởi DB/HTTP server, xem resource bottleneck thay vì tiếp tục tăng forks.
7. Thiết kế CI job profile khác workstation khi tài nguyên khác nhau.

Ví dụ bảng đo giả định:

| `maxParallelForks` | Thời gian task `test` | Peak RAM | Kết luận |
| --- | --- | --- | --- |
| 1 | 120 s | 900 MiB | Baseline ổn định |
| 2 | 74 s | 1.35 GiB | Có cải thiện, tiếp tục kiểm tra flakes |
| 4 | 72 s | 2.1 GiB | Lợi ích nhỏ, RAM tăng mạnh |

**Đây là số minh họa để hướng dẫn đánh giá**, không phải benchmark đã chạy trên project thực tế. Không chọn 4 forks chỉ vì 72s thấp hơn 74s nếu memory budget CI sát giới hạn và DB đang căng.

### Task duration khác wall-clock build duration

Giảm thời gian một Test task từ 120s xuống 74s không đồng nghĩa `./gradlew build` cũng giảm 46s. Các tasks có thể được cache/UP-TO-DATE, dependency graph có bottleneck khác, report generation hoặc integration tests còn chiếm nhiều thời gian. Đo cả **`:test` duration** và **toàn pipeline**.

## 22. Các lỗi thường gặp khi tăng `maxParallelForks`

| Triệu chứng | Gốc rễ thường gặp | Cách xử lý |
| --- | --- | --- |
| `Address already in use` | Nhiều JVMs bind cùng port | Dùng port 0/dynamic binding hoặc resource riêng |
| Unit test file assertions chập chờn | Hai tests ghi cùng filename | Dùng `@TempDir`/Files.createTempFile hoặc worker-specific path |
| DB tests thỉnh thoảng mất records | Tests mutate cùng schema/table | Per-worker schema, unique IDs, transaction isolation, serial integration suite |
| CI bị `OOMKilled` | Quá nhiều test JVM heaps + native memory/Daemon | Giảm forks, giảm heap phù hợp, điều chỉnh RAM quota |
| `maxParallelForks` vượt `max-workers` | Task config quá lớn so với global build capacity | Giảm maxParallelForks hoặc tăng max-workers nếu tài nguyên cho phép |
| Bật `--parallel` nhưng Test task vẫn một fork | `--parallel` là task/project parallelism | Cấu hình `maxParallelForks` cho `Test` task |
| Đặt `forkEvery=1` mà không chạy nhanh hơn | JVM startup, class loading và JIT overhead lớn | Trở về `0` trừ khi cần xử lý leak |
| `@ResourceLock` vẫn không ngăn DB collision | Test classes ở hai JVMs khác nhau | Resource lock bên ngoài JVM hoặc cô lập database |
| JUnit methods vẫn tuần tự | Jupiter parallel chưa bật | Xem `junit-platform.properties`, nhưng chỉ bật nếu thread-safe |
| Thứ tự log khác mỗi lần | Fork scheduler và test ordering không cố định | Không assert theo stdout order |
| Test chỉ pass khi chạy một mình | Dependency vào shared state/order | Cô lập fixtures, cleanup đúng, chạy randomized stress |
| `System.getProperty("org.gradle.test.worker")` null trong IDE | IDE không dùng Gradle Test fork | Delegate test to Gradle hoặc fallback cho IDE |
| `forkEvery=1` không sửa test giữ trạng thái DB | DB sống ngoài JVM | Cleanup DB/schema per test hoặc cô lập |
| Test suite một class lớn không tận dụng 4 forks | Gradle phân phối theo test classes, không tự chia methods | Chia suite hợp lý hoặc cân nhắc JUnit parallel methods |
| All tasks dùng cùng external service | Project tasks/CI jobs cạnh tranh nhau | Điều phối tasks hoặc cấp service riêng per build/job |
| `maxHeapSize` được đặt nhưng Gradle daemon vẫn OOM | Daemon có memory config riêng | Xem `org.gradle.jvmargs` vs Test JVM heap, quá trình native |
| Testcontainers chạy quá nhiều containers | Mỗi worker/class khởi tạo resources đắt | Kiểm soát container lifetime, fork count, resource quota và cleanup |
| Một số classes không được chạy | Test discovery/filter hoặc source set config | Kiểm tra report/tests filter/task, đừng chỉ xem số forks |
| Tests viết vào project root bị cache output sai | Shared/mutable outputs ngoài task tracking | Dùng temp fixtures, chuẩn hóa inputs/outputs |

**Ưu tiên sửa tính đúng đắn của test trước khi tối ưu tốc độ.** Một suite nhanh nhưng flaky làm mất giá trị CI hơn một suite hơi chậm mà đáng tin cậy.

## 23. Quy trình gỡ lỗi flaky test theo mức độ can thiệp

**Bước 1 — Tái hiện ở mức đơn giản nhất**

```bash
./gradlew clean test --max-workers=1 --rerun-tasks
```

Đặt `maxParallelForks=1`, `forkEvery=0`, JUnit parallelism tắt để có baseline tuần tự trong một Test task.

**Bước 2 — Chỉ tăng số forks của task**

```bash
./gradlew test --max-workers=2 --rerun-tasks
```

Đặt `maxParallelForks=2`, giữ JUnit parallelism tắt và so logs/tests. Nếu chỉ fail khi có hai forks, kiểm tra file/port/schema/cache/external service dùng chung.

**Bước 3 — In worker IDs, nhưng không assert thứ tự**

Sử dụng:

```java
System.out.println(
        "test-worker=" + System.getProperty("org.gradle.test.worker"));
```

Đây là **mảnh Java** đặt trong test method. Kết hợp test logging hoặc JUnit reports để nhận biết test chạy trong fork nào. Worker ID giúp phân nhóm, **không phải bằng chứng JVM đó có resource isolation đầy đủ**.

**Bước 4 — Phân tích shared resources**

Rà những đường dẫn `Path.of("build/...")`, `/tmp`, fixed ports, DB migrations, global caches, `System.setProperty`, static singletons, message queue, test users có email cố định. Mỗi tài nguyên cần scope riêng/cleanup đúng.

**Bước 5 — Kiểm chứng bằng đổi resource strategy**

Thay fixed port bằng `0`, file chung bằng `@TempDir`, database chung bằng per-worker schema. Chạy lại với fork count cũ. Nếu lỗi biến mất và test behavior giữ nguyên, có bằng chứng cho root cause.

**Bước 6 — Sau đó mới tối ưu lại parallelism**

Tăng forks theo workload, giữ budgets phù hợp. Nếu cần JUnit threads, bật riêng và test `@ResourceLock` cho static state nội JVM, không lẫn với cross-process locking.

## 24. Mẫu cấu hình cho các đội có CI runners khác nhau

Một cấu hình có thể điều chỉnh mà vẫn an toàn theo mặc định:

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

val testForks = providers.gradleProperty("testForks")
    .map(String::toInt)
    .orElse(1)

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    maxParallelForks = testForks.get().coerceAtLeast(1)
    forkEvery = 0L
    maxHeapSize = "512m"
}
```

Chạy trên CI runner có ít worker:

```bash
./gradlew test -PtestForks=1 --max-workers=1 --console=plain
```

Chạy trên runner đã kiểm tra đủ CPU/RAM, test fixtures isolated:

```bash
./gradlew test -PtestForks=2 --max-workers=2 --console=plain
```

Đây là **lựa chọn vận hành**, không phải yêu cầu của Gradle là luôn dùng 1 hoặc 2. Với suite thật, thử khác nhau theo test task. Không dùng cùng số forks cao cho unit tests CPU-bound và integration tests phụ thuộc một DB dùng chung.

### Đặt tên cấu hình có ý nghĩa

Nếu team có các suites với ràng buộc khác nhau, ghi rõ trong build logic:

- **`unitTestForks`**: có thể cao hơn nếu tests isolated.
- **`integrationTestForks`**: thường thấp hơn/1 nếu dùng shared external service.
- **`max-workers`**: do CI environment quyết định worker capacity toàn build.
- **JVM heap**: theo profile memory của từng Test task, không theo số cores một cách đơn giản.

Tránh viết `allprojects { tasks.withType<Test>().configureEach { maxParallelForks=8 } }` một cách mù quáng: điều đó có thể áp dụng 8 forks cho cả những suites tài nguyên chung và khiến multi-project build khó kiểm soát hơn.

## 25. Những câu hỏi tự kiểm tra

**Câu 1.** `maxParallelForks=4` nghĩa là bốn threads chạy cùng một `@Test` method?

**Đáp:** Không. Nó giới hạn tối đa bốn **forked JVM test processes** có thể chạy đồng thời trong một Gradle `Test` task.

**Câu 2.** `forkEvery=0` có nghĩa không fork JVM nào?

**Đáp:** Không. Gradle vẫn chạy tests trong JVM con; `forkEvery=0` chỉ có nghĩa **không giới hạn số classes trên một fork trước khi restart**.

**Câu 3.** `forkEvery=1` có khiến test chạy nhanh hơn không?

**Đáp:** Thường không; nó tạo JVM mới sau mỗi test class và có startup overhead lớn. Chủ yếu dùng khi cần cách ly JVM state/leaks khó dọn.

**Câu 4.** Hai Gradle test workers cùng chạy `new ServerSocket(8080)` thì lỗi gì có thể xảy ra?

**Đáp:** `BindException: Address already in use`. Giải pháp thường là dynamic port binding (`new ServerSocket(0)`) hoặc service instance riêng.

**Câu 5.** `org.gradle.test.worker` được dùng làm gì?

**Đáp:** Định danh worker JVM do Gradle cấp trong test process; có thể dùng khi phân chia filenames/resource namespaces. Không nên coi nó là globally unique across CI jobs/build runs.

**Câu 6.** `@ResourceLock("shared-db")` của JUnit Jupiter có khóa hai JVM forks của Gradle không?

**Đáp:** Không. Nó điều phối JUnit tests trong phạm vi engine/process liên quan; không là distributed lock giữa hai JVMs.

**Câu 7.** `maxParallelForks=1` có bảo đảm hai subprojects `:app:test` và `:db:test` không chạy đồng thời không?

**Đáp:** Không. Mỗi Test task có giới hạn riêng; `--parallel` và global workers có thể cho hai Test tasks chạy đồng thời. Resource dùng chung cần được điều phối ở scope phù hợp.

**Câu 8.** `--parallel` và `maxParallelForks` khác nhau ở điểm nào?

**Đáp:** `--parallel` cho phép các project tasks độc lập được lên lịch đồng thời; `maxParallelForks` điều khiển parallel test worker JVMs **bên trong một Test task**.

**Câu 9.** CI container có 2 GiB RAM, hai forks `maxHeapSize=1g` có an toàn không?

**Đáp:** Rất rủi ro. Hai heaps có thể đạt gần 2 GiB chưa kể daemon, metaspace, native memory và OS; cần tính tổng RAM budget và giảm fork/heap.

**Câu 10.** Hai tests tạo `tempDir.resolve("data.json")` với `@TempDir` riêng có va chạm không?

**Đáp:** Trong cấu hình Jupiter thông thường, mỗi test được cấp directory tách biệt nên hai files khác đường dẫn. Nếu test cố ý truyền/chia sẻ chung directory thì vẫn cần quản lý concurrency.

**Câu 11.** Tại sao chạy một test riêng PASS nhưng full suite ở hai forks FAIL?

**Đáp:** Có thể có resource collision/order-dependent shared state, ví dụ cổng, file, database, cache, test user. Cần tái hiện và xác minh, không khẳng định chắc nếu chưa điều tra.

**Câu 12.** Bật JUnit Jupiter parallelism có cần thiết để Gradle dùng `maxParallelForks=2` không?

**Đáp:** Không. Gradle có thể chạy **test classes** ở hai JVMs dù Jupiter vẫn chạy methods tuần tự bên trong mỗi JVM.

**Câu 13.** Khi dùng `--max-workers=1`, có nên đặt `maxParallelForks=8` không?

**Đáp:** Không. Giới hạn fork của Test task không nên vượt global max-workers. Hãy giảm forks hoặc tăng global worker capacity chỉ khi máy thật sự có đủ tài nguyên.

**Câu 14.** Testcontainers có bảo đảm hai tests không bao giờ chia sẻ DB state không?

**Đáp:** Không nếu chúng dùng chung singleton container/schema hoặc cùng external namespace. Phải thiết kế container lifetime, database/schema/tenant uniqueness và cleanup.

**Câu 15.** Có thể dùng `System.setProperty` để tạo semaphore giữa hai forked JVMs không?

**Đáp:** Không. Mỗi JVM có bộ system properties riêng. Cần external/process-safe coordination hoặc resource riêng.

## 26. Checklist khi review pull request tăng parallel test execution

- [ ] Tài liệu hóa baseline `maxParallelForks=1` và thời gian chạy của suite.
- [ ] Xác định `Test` tasks/source sets cần parallel: unit vs integration.
- [ ] Không vượt `--max-workers` và CPU/RAM quota của CI runner.
- [ ] Dùng `maxHeapSize` cho **mỗi test JVM** với ngân sách bộ nhớ tổng thể.
- [ ] Không dùng `forkEvery` như cách giảm xung đột file/port/DB.
- [ ] Tránh fixed ports; để server bind port `0` hoặc dùng tài nguyên riêng.
- [ ] Dùng `@TempDir`/temporary unique directories cho file artifacts.
- [ ] Các shared DB/Redis/queue resources có per-worker/per-job namespace hoặc được chạy tuần tự.
- [ ] Nắm rõ JUnit method parallelism và phạm vi `@ResourceLock`.
- [ ] Không dựa vào thứ tự test classes/logging hoặc tên worker ID.
- [ ] CI chạy đầy đủ suites với fork count mong muốn, không chỉ một class riêng lẻ.
- [ ] Đã kiểm tra cả multi-project Test tasks và CI jobs độc lập.
- [ ] Có cleanup fixtures/containers/service connections khi test lỗi.
- [ ] Đã đo wall-clock, task duration, RAM/CPU, flaky test rate trên nhiều runs.
- [ ] Tests không dùng shared production/staging data hoặc secrets không cần thiết.
- [ ] Test reports/JUnit XML được lưu đúng nơi để phân tích failures.

## 27. Tài liệu tham khảo chính thức

- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): Gradle Test forked JVM, `maxParallelForks`, `forkEvery`, `org.gradle.test.worker`, reports và test filtering.
- [Gradle — Test task DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html): các thuộc tính `maxParallelForks`, `forkEvery`, `maxHeapSize`, `jvmArgs`, `javaLauncher`, `testLogging`.
- [Gradle — Test task API/Javadoc](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/Test.html): semantics, giới hạn `max-workers`, Java fork options.
- [Gradle — Improving Gradle Build Performance](https://docs.gradle.org/current/userguide/performance.html): tối ưu test execution, lựa chọn số forks, chi phí restart JVM và đo performance.
- [Gradle — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html): `org.gradle.workers.max`, `org.gradle.parallel`, `org.gradle.jvmargs`.
- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): khai báo unit/integration test suites thay vì tự tạo task không có source set.
- [Gradle — Shared Build Services](https://docs.gradle.org/current/userguide/build_services.html): giới hạn concurrent task usages trong một Gradle build, không phải cross-JVM test-method lock.
- [JUnit 5 User Guide — Parallel Execution](https://docs.junit.org/5.12.1/user-guide/index.html#writing-tests-parallel-execution): opt-in Jupiter parallel execution, `@ResourceLock`, `@Isolated`.
- [JUnit 5 User Guide — `@TempDir`](https://docs.junit.org/5.12.1/user-guide/index.html#writing-tests-built-in-extensions-TempDirectory): temp directories, lifecycle/cleanup và tham số injection.
- [Java SE 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): port `0` và `getLocalPort()`.
