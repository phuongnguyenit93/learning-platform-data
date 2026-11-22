# Đo tác động của test fork, compiler, I/O và dependency resolution trong Gradle

## 1. Bài toán cần giải quyết

Một build Java chạy chậm có thể do việc biên dịch, khởi động các JVM chạy test, đọc và ghi hàng nghìn tệp, hoặc truy vấn Maven repositories. Nếu chỉ nhìn tổng thời gian rồi tăng số worker, tăng heap hay xóa caches, rất dễ tối ưu sai nguyên nhân.

Bài học thuộc nhóm **Hiệu năng build**, chủ đề **Build Tool Gradle**, tập trung vào **“Đo tác động của test fork, compiler, I/O và dependency resolution”**.

Mục tiêu:

1. Đo được **wall-clock build time**, **task duration**, thời gian configuration, dependency resolution và critical path.
2. Hiểu hai tham số **Test.maxParallelForks** và **Test.forkEvery**, phân biệt với **--parallel**, **--max-workers** và JUnit parallelism.
3. So sánh **JavaCompile.options.fork**, incremental compilation, compile avoidance và tác động của toolchain.
4. Tách thời gian **I/O trên filesystem** khỏi CPU và network, đặc biệt với Copy/Sync, JARs và reports.
5. Phân biệt **dependency graph resolution**, repository metadata lookup, artifact downloads và dependency cache.
6. Thiết kế benchmark warm/cold, có warm-up, lặp lại và đo median, không lấy một lần chạy làm kết luận.
7. Dùng **--profile**, **--info**, Build Scan/Develocity, logs và một chương trình Java 17 thu kết quả CSV.
8. Thực hành bằng Gradle Groovy DSL, Java 17, JUnit 5, multi-project build và các thí nghiệm có thể lặp lại.
9. Phát hiện tác dụng phụ: tăng CPU contention, GC, flakiness, quá tải RAM, slow Maven proxy và đo sai do UP-TO-DATE/FROM-CACHE.
10. Đưa ra quyết định tối ưu phù hợp với desktop và CI mà vẫn giữ correctness/security.

**Nguyên tắc:** Phải xác định *điều gì bị đo*, *điều kiện nào được giữ cố định* và *bằng chứng nào chứng minh nguyên nhân* trước khi thay đổi Gradle configuration.

## 2. Các loại thời gian khác nhau

~~~text
Gradle invocation
  |
  +-- JVM launcher / Daemon startup
  |
  +-- Initialization and settings
  |
  +-- Project configuration
  |     +-- Plugin resolution / configuration cache
  |     +-- Có thể phát sinh dependency resolution không mong muốn
  |
  +-- Task graph
  |
  +-- Tasks trên critical path
         +-- compileJava              CPU, compiler, source/classpath I/O
         +-- compileTestJava          CPU, test classpath
         +-- test                     fork JVMs, test body, GC, reports
         +-- processResources/Sync    filesystem metadata + bytes
         +-- publish/artifact tasks   packaging, network (nếu được chọn)
  |
  v
BUILD COMPLETE
~~~

**Wall-clock duration** đo từ khi gọi Gradle đến khi process hoàn tất. **Task duration** đo riêng mỗi task. **CPU time** đo số thời gian CPU thực sự làm việc. **Elapsed wall time** của một task có thể lớn khi nó chờ I/O, process startup, locks, network hoặc JVM GC.

Các tasks có thể chồng lấp nhờ parallel execution. Không được cộng mọi task durations rồi coi đó là tổng build duration.

| Metric | Câu hỏi nó trả lời | Giới hạn |
| --- | --- | --- |
| Tổng wall time | Người dùng chờ bao lâu? | Gộp launcher, configuration, tasks, report |
| Configuration time | Có tốn thời gian trước khi task chạy? | Không nói riêng compiler/test |
| Task duration | Task nào mất lâu? | Không tách CPU khỏi I/O nếu thiếu metrics phụ |
| Critical path | Những công việc nào chặn build xong? | Không phải mọi task lâu đều trên critical path |
| CPU utilization/GC | JVM có CPU-bound/memory pressure? | Có thể che contention trên máy chia sẻ |
| Disk throughput/IOPS/latency | Có đợi filesystem? | Filesystem cache có thể làm sai kết luận cold I/O |
| Network requests/downloads | Maven repo/remote cache có chậm? | Không phải mọi dependency resolution đều download |
| Test count/JUnit reports | Có thật sự chạy đủ tests? | Không phải trực tiếp performance metric |
| Task outcome | EXECUTED, UP-TO-DATE, FROM-CACHE, NO-SOURCE? | Không thay thế benchmark timing |

## 3. Công cụ đo chính thức

### 3.1. Gradle profile

~~~bash
./gradlew :app:test --profile --console=plain
~~~

**--profile** tạo báo cáo HTML trong vùng **build/reports/profile/** của build. Báo cáo giúp phân tách thời gian ở các phần của build và task execution. Đây là timing overview; nó **không phải CPU sampling profiler** và không cho biết tự động test process nào GC bao lâu.

### 3.2. Gradle info logs

~~~bash
./gradlew :app:compileJava --info --console=plain
~~~

**--info** hữu ích để biết vì sao task chạy lại, lý do up-to-date/cache misses, một số dependency resolution/download events và compiler-related messages.

**Không đo các mẫu A/B khác nhau về logging level.** Ghi quá nhiều logs tăng I/O và console overhead, nhất là khi có hàng nghìn test cases.

### 3.3. Build Scan

~~~bash
./gradlew :app:test --scan
~~~

Build Scan/Develocity có thể cung cấp task timeline, performance insights, network activity, dependency resolution breakdown, test class durations và caching. Nhưng việc bật scan có thể yêu cầu plugin/điều khoản/server, và có thể xuất bản dữ liệu về build. Chỉ dùng nếu tổ chức cho phép; với dự án có secrets hoặc internal paths, cần review chính sách chia sẻ diagnostics.

### 3.4. OS/JVM tools

Dùng công cụ hệ điều hành phù hợp để theo dõi CPU %, vCPU quota, RSS/heap, garbage collection, disk read/write, file open latency và network. Linux có top, pidstat, iostat khi được cài; macOS có Activity Monitor; Windows có Task Manager, Resource Monitor, Performance Monitor. Với memory/CPU Java sâu hơn có thể dùng JFR, nhưng bật profiler cũng gây overhead: chạy riêng một lượt diagnostic, không trộn vào mọi sample benchmark.

## 4. Thiết kế phép đo có kiểm soát

**Không đoán từ một lần chạy.** Quy trình:

1. Ghi commit hash, Gradle Wrapper version, JVM chạy Gradle, Java toolchain, số CPU/vCPU, RAM, loại disk và CI image.
2. Xác định một biến chính: testForks, forkEvery, compilerFork, file count/size hoặc dependency cache state.
3. Chọn workload phù hợp và đảm bảo nó thực sự có công việc phải làm.
4. Làm warm-up để tải dependencies, compile Java source và làm nóng Gradle Daemon.
5. Đo tối thiểu vài lượt; với biến động lớn nên 5–10 lượt hoặc hơn.
6. Dùng cùng cache policy, cùng test count và cùng input source.
7. Đảo thứ tự A/B/B/A để giảm bias do thermal throttling/noisy neighbors.
8. Lưu logs/CSV, tính median và độ phân tán.
9. Đọc task timeline để xem thay đổi có rút ngắn critical path không.
10. Kiểm tra tests pass, artifacts đúng, không tăng flakiness/OOM.
11. Chỉ giữ thay đổi nếu lợi ích ổn định, có thể tái hiện.
12. Rollback nếu cải thiện nằm trong noise.

Ví dụ số liệu **giả định để minh họa**, không phải benchmark đã thực hiện:

| Biến thể | Lượt 1 | Lượt 2 | Lượt 3 | Median |
| --- | ---: | ---: | ---: | ---: |
| A | 5,10 s | 4,95 s | 7,20 s | 5,10 s |
| B | 4,70 s | 4,80 s | 6,95 s | 4,80 s |

Median B thấp hơn A, nhưng chênh lệch nhỏ có thể bị nhiễu. Không cherry-pick kết quả nhanh nhất.

## 5. Test forks: ba mức song song khác nhau

Trong Gradle:

- **--parallel** cho phép scheduling tasks từ nhiều projects song song khi task graph và compatibility cho phép.
- **--max-workers=N** giới hạn worker budget của Gradle cho công việc song song.
- **Test.maxParallelForks=N** quy định số **JVM test workers** tối đa chạy đồng thời của một Test task.
- **JUnit Jupiter parallel execution** có thể song song hóa tests ở bên trong một JVM: đây là tầng khác, không phải Test.maxParallelForks.

Ví dụ:

~~~text
--parallel            : task execution giữa projects
--max-workers=4       : giới hạn Gradle worker budget
maxParallelForks = 2  : tới hai JVM test workers cùng lúc cho Test task
JUnit parallel mode   : nhiều test threads trong JVM (nếu bật riêng)
~~~

Giới hạn worker resources, số test classes, CPU/RAM và các tasks khác quyết định concurrency thực. Không tuyên bố maxParallelForks=4 có nghĩa luôn có đúng bốn JVM active trong mọi thời điểm.

### 5.1. maxParallelForks

Theo Gradle docs, mặc định **maxParallelForks=1**. Tăng lên 2, 4 hoặc số phù hợp có thể giảm thời gian test suite khi các test classes độc lập và có đủ CPU.

Rủi ro:

- CPU-bound tests tranh nhau cores, khiến latency tăng.
- JVM startup, metaspace, thread stacks và heap dùng thêm RAM.
- Shared database, TCP port cố định, temporary directory hoặc static state ngoài process gây race/flakiness.
- I/O và report generation bị tranh băng thông.
- CI container vCPU quota có thể thấp hơn số CPUs báo cáo.
- Một test class rất dài có thể khiến một worker trở thành critical path.

### 5.2. forkEvery

Theo Gradle docs:

- **forkEvery=0** mặc định: không giới hạn số test classes cho mỗi test worker JVM trước khi thay JVM.
- **forkEvery=1**: mỗi test class chạy trong JVM worker mới, tốn startup.
- **forkEvery=100**: JVM worker được đổi sau tối đa khoảng 100 test classes.

forkEvery điều khiển **tần suất tái tạo process**, không quyết định số process được chạy **đồng thời**. Không cần đặt forkEvery=1 chỉ để “bật JVM fork”: Gradle Test task đã chạy test trong process riêng khỏi Gradle build process.

| maxParallelForks | forkEvery | Ý nghĩa |
| ---: | ---: | --- |
| 1 | 0 | Một worker, tái sử dụng trong suite |
| 2 | 0 | Tối đa hai workers, mỗi worker reuse |
| 4 | 0 | Nhiều workers, có thể tăng contention |
| 1 | 1 | Nhiều lần startup JVM theo từng test class |
| 2 | 1 | Parallel + liên tục thay test worker |
| 2 | 100 | Parallel, giới hạn tái sử dụng để kiểm soát leak |

forkEvery thấp đôi khi giúp giải quyết memory/static-state leak ở framework cũ. Nhưng tốt nhất vẫn là sửa root cause và chỉ dùng khi có bằng chứng.

## 6. Compiler fork là cơ chế khác Test fork

**JavaCompile.options.fork** cho phép chạy Java compiler trong một process riêng thay vì đường thực thi compiler mặc định trong Gradle process. Một compiler process riêng có thể giảm pressure lên Gradle JVM và cải thiện GC behavior của build lớn. Gradle có thể tái sử dụng forked compiler process trong cùng build.

Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.fork = true
}
~~~

Đo cả **false** và **true**. Với ít Java files, forked compiler có thể không có lợi vì startup/memory overhead. Với nhiều source files hoặc compile song song trên máy đủ RAM, lợi ích có thể khác.

**Không nhầm compiler fork với JVM Test forks**: compilerFork đo compiler process, maxParallelForks đo test worker processes.

### 6.1. Incremental compilation và compile avoidance

- **Incremental compilation**: JavaCompile task thực thi nhưng chỉ biên dịch lại những phần cần thiết dựa trên thay đổi.
- **Compile avoidance**: một downstream project có thể không cần chạy JavaCompile nếu dependency thay đổi ở implementation nhưng public ABI không đổi.
- **UP-TO-DATE**: task không cần chạy vì inputs/outputs hiện hành vẫn hợp lệ.
- **FROM-CACHE**: task không chạy action vì khôi phục outputs từ cache.

Khi thử compiler fork, dùng **--rerun-tasks --no-build-cache** để buộc compilation thật. Khi thử incremental/compile avoidance, **không dùng --rerun-tasks**, vì chính cờ đó loại khả năng task được Gradle tránh chạy.

## 7. Lab Java 17 có cấu trúc rõ ràng

Ta tạo **gradle-performance-lab** gồm:

~~~text
gradle-performance-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── library/
│   ├── build.gradle
│   └── src/main/java/demo/library/GreetingFormatter.java
├── app/
│   ├── build.gradle
│   ├── src/main/java/demo/app/Main.java
│   └── src/test/java/demo/app/
│       ├── AlphaTest.java
│       ├── BetaTest.java
│       ├── GammaTest.java
│       └── DeltaTest.java
└── tools/src/demo/tools/
    ├── Fixtures.java
    └── Measure.java
~~~

Trong lab:

- **:library** cung cấp Java class được app tiêu thụ.
- **:app** là Java application và có bốn test classes độc lập.
- **copyIo** đo một Sync task với binary fixtures tự sinh.
- **resolveTestArtifacts** cần actual JUnit dependency files, nên có thể quan sát resolution và download.
- **Fixtures.java** tạo số lượng/bytes files cố định.
- **Measure.java** gọi Gradle nhiều lần và ghi CSV thời gian.

Cần **JDK 17**, Gradle Wrapper tương thích, Maven Central/mirror cho JUnit. Nếu chưa có Wrapper, dùng Gradle CLI đã cài chạy **gradle wrapper** một lần rồi commit Wrapper scripts, JAR và properties. Không dùng một Wrapper JAR chưa rõ nguồn.

## 8. settings.gradle

~~~groovy
dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        mavenCentral()
    }
}

rootProject.name = 'gradle-performance-lab'
include 'library', 'app'
~~~

Dùng **include** vì library và app là subprojects của cùng build. **mavenCentral()** chỉ cần cho JUnit dependencies, không cần publish library lên Maven Local vì app dùng project dependency.

## 9. Root build.gradle

~~~groovy
plugins {
    id 'base'
}

tasks.register('copyIo', Sync) {
    from(layout.projectDirectory.dir('io-fixtures'))
    into(layout.buildDirectory.dir('io-copy'))
}
~~~

Root **base** plugin cung cấp **clean**. Task copyIo đọc **io-fixtures/** được tạo ở phần sau và đồng bộ vào **build/io-copy/**.

Không mặc định gọi duration của Sync là “disk throughput”: nó bao gồm Gradle startup/configuration, task snapshots, metadata operations, bytes transfer và OS page cache effects.

## 10. library/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release.set(17)

    options.fork = providers.gradleProperty('compilerFork')
            .map { it.toBoolean() }
            .getOrElse(false)

    options.incremental = providers.gradleProperty('incrementalCompiler')
            .map { it.toBoolean() }
            .getOrElse(true)
}
~~~

Knobs:

- **-PcompilerFork=true/false** đổi compiler process policy.
- **-PincrementalCompiler=true/false** điều khiển incremental compilation.
- **Java toolchain 17** và **--release 17** giữ compiler target và Java API compatibility.
- **UTF-8** tránh output khác do default charset.

Khi đo tác động của compilerFork, giữ incrementalCompiler cố định. Khi đo compile avoidance, không dùng --rerun-tasks.

## 11. library/src/main/java/demo/library/GreetingFormatter.java

~~~java
package demo.library;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String message(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        return "Hello, " + name.trim() + "!";
    }
}
~~~

Public method **message(String)** có ABI ổn định. Khi muốn thử implementation-only change, có thể đổi **name.trim()** thành **name.strip()** mà không đổi method signature. Với input ASCII **" Gradle "**, cả hai đều trả **Hello, Gradle!**.

## 12. app/build.gradle

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.app.Main'
}

dependencies {
    implementation project(':library')

    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release.set(17)

    options.fork = providers.gradleProperty('compilerFork')
            .map { it.toBoolean() }
            .getOrElse(false)

    options.incremental = providers.gradleProperty('incrementalCompiler')
            .map { it.toBoolean() }
            .getOrElse(true)
}

tasks.named('test', Test) {
    useJUnitPlatform()

    maxParallelForks = providers.gradleProperty('testForks')
            .map { Integer.parseInt(it) }
            .getOrElse(1)

    forkEvery = providers.gradleProperty('forkEvery')
            .map { Long.parseLong(it) }
            .getOrElse(0L)

    maxHeapSize = '256m'

    testLogging {
        showStandardStreams =
                providers.gradleProperty('showTestWorkers')
                        .map { it.toBoolean() }
                        .getOrElse(false)
    }

    if (providers.gradleProperty('benchTests')
            .map { it.toBoolean() }.getOrElse(false)) {
        // Rerun chỉ task test trong benchmark, không ép compiler.
        outputs.upToDateWhen { false }
    }
}

tasks.register('resolveTestArtifacts', Sync) {
    from(configurations.testRuntimeClasspath)
    into(layout.buildDirectory.dir('dependency-probe'))
}
~~~

**Vì sao cấu hình này hữu ích?**

- testForks điều khiển số Gradle Test worker JVMs.
- forkEvery điều khiển số test classes tối đa trước khi thay JVM.
- maxHeapSize là heap **mỗi Test worker**, không phải tổng memory của CI. JVM còn metaspace, threads, native memory và Gradle Daemon.
- showTestWorkers chỉ mở standard streams khi chẩn đoán, không mở khi benchmark để tránh tăng logging overhead.
- **benchTests=true** khiến :app:test không UP-TO-DATE; kết hợp **--no-build-cache** để ngăn FROM-CACHE và buộc Test action chạy ở mỗi mẫu. Compiler task dependencies vẫn có thể UP-TO-DATE.
- **resolveTestArtifacts** copy JARs từ testRuntimeClasspath vào app/build/dependency-probe; thời gian của nó gồm **resolution + downloads nếu cần + file copy**, không thể xem toàn bộ là network time.

Cẩn trọng: một benchmark lặp lại **:app:test** trên JUnit test suite quá nhỏ có thể bị Gradle configuration/JVM startup chi phối. Vì vậy phải kiểm tra riêng task durations.

## 13. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.library.GreetingFormatter;

public final class Main {
    private Main() {
    }

    public static String message() {
        return "RESULT=" +
                GreetingFormatter.message(" Gradle ");
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Chạy:

~~~bash
./gradlew :app:run --console=plain
~~~

**Stdout chính xác của Java program:**

~~~text
RESULT=Hello, Gradle!
~~~

Gradle có thể in thêm task status, daemon messages và warnings; khối này chỉ là output của class Main.

## 14. Bốn JUnit Jupiter test classes

Mỗi class có một test method ngủ 300 ms để mô phỏng một đoạn công việc có thể overlap khi chạy nhiều JVMs. Đây chỉ là **synthetic wait-bound workload**, không đại diện cho CPU-bound production tests.

### AlphaTest.java

Tạo **app/src/test/java/demo/app/AlphaTest.java**:

~~~java
package demo.app;

import demo.library.GreetingFormatter;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AlphaTest {
    @Test
    void checksAlpha() throws InterruptedException {
        Thread.sleep(300);
        assertEquals(
                "Hello, Alpha!",
                GreetingFormatter.message(" Alpha "));
        System.out.println(
                "TEST_WORKER=" +
                System.getProperty("org.gradle.test.worker"));
    }
}
~~~

### BetaTest.java

Tạo **app/src/test/java/demo/app/BetaTest.java**:

~~~java
package demo.app;

import demo.library.GreetingFormatter;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BetaTest {
    @Test
    void checksBeta() throws InterruptedException {
        Thread.sleep(300);
        assertEquals(
                "Hello, Beta!",
                GreetingFormatter.message(" Beta "));
        System.out.println(
                "TEST_WORKER=" +
                System.getProperty("org.gradle.test.worker"));
    }
}
~~~

### GammaTest.java

Tạo **app/src/test/java/demo/app/GammaTest.java**:

~~~java
package demo.app;

import demo.library.GreetingFormatter;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GammaTest {
    @Test
    void checksGamma() throws InterruptedException {
        Thread.sleep(300);
        assertEquals(
                "Hello, Gamma!",
                GreetingFormatter.message(" Gamma "));
        System.out.println(
                "TEST_WORKER=" +
                System.getProperty("org.gradle.test.worker"));
    }
}
~~~

### DeltaTest.java

Tạo **app/src/test/java/demo/app/DeltaTest.java**:

~~~java
package demo.app;

import demo.library.GreetingFormatter;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DeltaTest {
    @Test
    void checksDelta() throws InterruptedException {
        Thread.sleep(300);
        assertEquals(
                "Hello, Delta!",
                GreetingFormatter.message(" Delta "));
        System.out.println(
                "TEST_WORKER=" +
                System.getProperty("org.gradle.test.worker"));
    }
}
~~~

Bốn tests độc lập, không ghi shared file hoặc chiếm port. Property **org.gradle.test.worker** cho biết worker process identifier theo Gradle docs; giá trị thực phụ thuộc run, không đưa ra một stdout worker ID cố định.

Kiểm tra:

~~~bash
./gradlew :app:test \
  -PtestForks=2 -PforkEvery=0 \
  -PbenchTests=true -PshowTestWorkers=true \
  --no-build-cache --console=plain
~~~

Khi benchmark, **bỏ -PshowTestWorkers=true** vì console output tạo overhead.

## 15. Sinh binary files để đo I/O

Tạo **tools/src/demo/tools/Fixtures.java**:

~~~java
package demo.tools;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public final class Fixtures {
    private Fixtures() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                "Usage: Fixtures <directory> <count> <kib>");
        }

        Path directory = Path.of(args[0]);
        int count = Integer.parseInt(args[1]);
        int kib = Integer.parseInt(args[2]);

        if (count < 1 || count > 1000 ||
                kib < 1 || kib > 2048) {
            throw new IllegalArgumentException(
                "count 1..1000 and KiB 1..2048 required");
        }

        Files.createDirectories(directory);

        byte[] bytes = new byte[kib * 1024];
        long total = 0L;

        for (int file = 0; file < count; file++) {
            for (int i = 0; i < bytes.length; i++) {
                bytes[i] = (byte) ((file * 31 + i) & 255);
            }

            String name = String.format(
                    Locale.ROOT, "data-%04d.bin", file);

            Files.write(directory.resolve(name), bytes);
            total += bytes.length;
        }

        System.out.println(
                "FILES=" + count + ";BYTES=" + total);
    }
}
~~~

Lệnh Linux/macOS:

~~~bash
mkdir -p tools/out
javac --release 17 -encoding UTF-8 \
  -d tools/out tools/src/demo/tools/Fixtures.java

java -cp tools/out demo.tools.Fixtures \
  io-fixtures 64 64
~~~

**Stdout chính xác:**

~~~text
FILES=64;BYTES=4194304
~~~

64 files × 64 KiB = 4 MiB.

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force tools\out | Out-Null
javac --release 17 -encoding UTF-8 -d tools\out tools\src\demo\tools\Fixtures.java
java -cp tools\out demo.tools.Fixtures io-fixtures 64 64
~~~

Nếu cần đo throughput thực, tạo đủ dữ liệu lớn hơn, ví dụ **64 × 1024 KiB** cho 64 MiB. Hãy bảo đảm quota/disk còn trống và chỉ ghi trong directory **io-fixtures** của lab.

**Quan trọng:** Khi đổi từ 512 files về 64 files mà vẫn dùng cùng folder, các tệp cũ có thể còn. Dùng directory mới cho mỗi workload hoặc dọn fixture directory có chủ đích để so sánh không bị nhiễu.

## 16. Java 17 benchmark runner ghi CSV

Tạo **tools/src/demo/tools/Measure.java**:

~~~java
package demo.tools;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public final class Measure {
    private Measure() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 4) {
            throw new IllegalArgumentException(
                "Usage: Measure <label> <runs> <command> [args...]");
        }

        String label = args[0];
        int runs = Integer.parseInt(args[1]);

        if (!label.matches("[A-Za-z0-9_-]+") || runs < 1) {
            throw new IllegalArgumentException(
                "A safe label and positive runs are required");
        }

        List<String> command =
                Arrays.asList(args).subList(2, args.length);

        Path root = Path.of("bench-results");
        Path logs = root.resolve("logs");
        Path csv = root.resolve("samples.csv");

        Files.createDirectories(logs);

        if (Files.notExists(csv)) {
            Files.writeString(csv,
                    "scenario,iteration,wall_ms,exit_code\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW);
        }

        for (int iteration = 1;
                iteration <= runs;
                iteration++) {
            Path log = logs.resolve(
                    label + "-" + iteration + ".log");

            ProcessBuilder builder =
                    new ProcessBuilder(command);
            builder.redirectErrorStream(true);
            builder.redirectOutput(log.toFile());

            long started = System.nanoTime();
            int exitCode = builder.start().waitFor();
            long elapsed = System.nanoTime() - started;

            String sample = String.format(
                    Locale.ROOT,
                    "%s,%d,%.3f,%d%n",
                    label, iteration,
                    elapsed / 1_000_000.0,
                    exitCode);

            Files.writeString(csv, sample,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.APPEND);

            System.out.print(sample);

            if (exitCode != 0) {
                throw new IllegalStateException(
                    "Command failed; read log " + log);
            }
        }
    }
}
~~~

Ý nghĩa:

- **System.nanoTime()** đo elapsed time theo monotonic clock, phù hợp hơn wall clock có thể thay đổi do NTP.
- Ghi **bench-results/samples.csv** và một log riêng cho từng iteration.
- **wall_ms** gồm launcher, configuration, compilation/test và report: không phải thời gian task duy nhất.
- Exit code khác 0 khiến benchmark dừng, không tính build fail là một chiến thắng về performance.
- Không xóa caches hoặc tự warm-up; người chạy phải kiểm soát workload và cache policy.
- Khi chạy lại cùng label, log file iteration cũ có thể bị thay; dùng label khác cho đợt mới nếu muốn giữ lịch sử.

Biên dịch:

~~~bash
javac --release 17 -encoding UTF-8 \
  -d tools/out tools/src/demo/tools/Measure.java
~~~

Windows:

~~~powershell
javac --release 17 -encoding UTF-8 -d tools\out tools\src\demo\tools\Measure.java
~~~

Ví dụ một phép đo:

~~~bash
java -cp tools/out demo.tools.Measure \
  smoke 1 ./gradlew :app:run --console=plain
~~~

CSV có một sample chứa wall_ms thực tế, nên không có con số stdout cố định cho Measure.

## 17. Baseline và warm-up

Chạy từ project root:

~~~bash
./gradlew --version
./gradlew projects
./gradlew :library:compileJava
./gradlew :app:compileJava
./gradlew :app:test
./gradlew :app:run
~~~

Stdout Java Main:

~~~text
RESULT=Hello, Gradle!
~~~

Làm warm-up:

~~~bash
./gradlew :app:test \
  -PtestForks=1 -PforkEvery=0 \
  -PbenchTests=true \
  --no-build-cache --console=plain
~~~

Warm-up này giúp tải dependencies, compile source và làm nóng Daemon. Những lần benchmark sau phải kiểm tra **:library:compileJava** và **:app:compileJava** thường UP-TO-DATE, còn **:app:test** EXECUTED do benchTests=true.

Nếu Test hiện **NO-SOURCE**, test count khác 4, một test fail hoặc JavaCompile chạy do source đổi, mẫu không phù hợp để kết luận hiệu quả test fork.

## 18. Đo maxParallelForks=1,2,4

Chạy ba biến thể trên cùng runner:

~~~bash
java -cp tools/out demo.tools.Measure \
  forks1 3 ./gradlew :app:test \
  -PtestForks=1 -PforkEvery=0 -PbenchTests=true \
  --no-build-cache --max-workers=4 --console=plain

java -cp tools/out demo.tools.Measure \
  forks2 3 ./gradlew :app:test \
  -PtestForks=2 -PforkEvery=0 -PbenchTests=true \
  --no-build-cache --max-workers=4 --console=plain

java -cp tools/out demo.tools.Measure \
  forks4 3 ./gradlew :app:test \
  -PtestForks=4 -PforkEvery=0 -PbenchTests=true \
  --no-build-cache --max-workers=4 --console=plain
~~~

Windows PowerShell ví dụ:

~~~powershell
java -cp tools\out demo.tools.Measure forks1 3 cmd.exe /c gradlew.bat :app:test -PtestForks=1 -PforkEvery=0 -PbenchTests=true --no-build-cache --max-workers=4 --console=plain
~~~

**Đây chỉ là bộ mẫu đầu.** Hãy đảo thứ tự variants ở đợt tiếp theo (4, 2, 1) và dùng labels mới. Nếu CPU quota chỉ 2 vCPU hoặc RAM thấp, không ép 4 forks rồi xem OOM là lỗi của Gradle.

### 18.1. Cách đọc kết quả

- **bench-results/samples.csv**: tổng elapsed wall time từng lượt.
- **bench-results/logs/**: task outcomes/console diagnostics.
- **--profile** hoặc Build Scan: thời gian thật của Test task và critical path.
- **JUnit XML**: đủ 4 methods, không skipped/failed ngoài dự kiến.
- **OS metrics**: CPU utilization, peak memory/RSS, I/O và GC.

Không suy **forks4 nhanh nhất** chỉ vì bốn tests sleep 300 ms. JVM startup và JUnit initialization có thể lớn hơn phần sleep được chồng lấp.

## 19. Đo forkEvery=0 so với forkEvery=1

Giữ testForks=1, chỉ thay tần suất thay JVM:

~~~bash
java -cp tools/out demo.tools.Measure \
  reuseJvm 3 ./gradlew :app:test \
  -PtestForks=1 -PforkEvery=0 -PbenchTests=true \
  --no-build-cache --max-workers=4 --console=plain

java -cp tools/out demo.tools.Measure \
  newJvmPerClass 3 ./gradlew :app:test \
  -PtestForks=1 -PforkEvery=1 -PbenchTests=true \
  --no-build-cache --max-workers=4 --console=plain
~~~

**forkEvery=1** thường tăng startup overhead, nhưng lợi ích isolation có thể quan trọng cho tests bị memory leak/static-state contamination. Thử 100 hoặc một giá trị phù hợp nếu có hàng nghìn classes.

Một test class duy nhất thì so forks 1/4 khó cho thấy khác biệt, vì không có đủ classes để Gradle chia công việc. Lab dùng bốn classes để quan sát rõ hơn.

## 20. Đo compiler fork

Ở cả **library** và **app**, Gradle property **compilerFork** điều khiển options.fork.

~~~bash
java -cp tools/out demo.tools.Measure \
  compilerDefault 3 ./gradlew :app:compileJava \
  -PcompilerFork=false \
  --rerun-tasks --no-build-cache \
  --max-workers=2 --console=plain

java -cp tools/out demo.tools.Measure \
  compilerForked 3 ./gradlew :app:compileJava \
  -PcompilerFork=true \
  --rerun-tasks --no-build-cache \
  --max-workers=2 --console=plain
~~~

Tại sao **--rerun-tasks --no-build-cache**? Nếu compileJava là UP-TO-DATE hoặc FROM-CACHE, bạn đang đo task avoidance/cache restore, không đo compiler process.

Lệnh đo là **compiler chain** của :app, bao gồm producer :library. Với hai Java files, chênh lệch chủ yếu là startup/overhead và có thể rất nhỏ; production project lớn thường cho phép quan sát khác biệt có ý nghĩa hơn.

Kết hợp profile:

~~~bash
./gradlew :app:compileJava \
  -PcompilerFork=true \
  --rerun-tasks --no-build-cache \
  --profile --console=plain
~~~

**Không tuyên bố compilerFork=true luôn nhanh hơn.** Với compile workload nhỏ, process startup và memory overhead có thể làm nó chậm. Khi đo bản lớn, theo dõi compiler daemon/process, GC của Gradle và CPU usage.

## 21. Đo incremental compilation và compile avoidance

### 21.1. Thay implementation nhưng giữ ABI

Trong library, thay:

~~~java
return "Hello, " + name.trim() + "!";
~~~

bằng:

~~~java
return "Hello, " + name.strip() + "!";
~~~

Giữ signature của **message(String)**. Chạy:

~~~bash
./gradlew :app:compileJava \
  --no-build-cache --info --console=plain
~~~

Kết quả **dự kiến trong điều kiện phù hợp**:

~~~text
> Task :library:compileJava
> Task :app:compileJava UP-TO-DATE
~~~

Vì Java source của library đổi nên library compile, nhưng public ABI không đổi, app có thể được compile avoidance. Đây là hành vi hữu ích khi project lớn.

**Không dùng --rerun-tasks** trong thí nghiệm này, vì nó ép app compileJava thực thi và sẽ che compile avoidance.

### 21.2. Thay public API

Thay method signature hay public type dependencies là thay ABI, có thể khiến downstream project phải recompile. Chạy compilation và đọc --info/task outputs. Sau đó khôi phục lab source. Đừng dùng thay đổi ABI để đo trường hợp implementation-only.

### 21.3. api và implementation

Với **java-library**, dùng **api** cho dependencies trong public API và **implementation** cho dependencies chỉ dùng nội bộ. Điều này giảm compile classpath downstream và có thể giúp compile avoidance. Không đưa mọi dependency vào api để “đơn giản”, vì nó có thể làm nhiều projects recompile không cần thiết.

### 21.4. Annotation processors

Annotation processors có thể làm compiler mất thời gian khởi tạo, scan và generate files. Khai báo processors trên **annotationProcessor**/ **testAnnotationProcessor**, kiểm tra incremental annotation processing support, generated source output và Classpath. Compiler fork không giải quyết mọi bottleneck của annotation processors.

## 22. I/O: files, bytes, filesystem latency

Một Gradle build đọc nhiều source/JAR files, quét metadata, ghi class files, JUnit reports, JAR ZIP entries, copied resources và cached outputs.

Hai workloads cùng tổng 4 MiB có thể rất khác:

| Workload | Files | KiB/file | Tổng |
| --- | ---: | ---: | ---: |
| A | 64 | 64 | 4 MiB |
| B | 512 | 8 | 4 MiB |
| C | 64 | 1024 | 64 MiB |
| D | 128 | 1024 | 128 MiB |

B có nhiều file opens/metadata entries; C nặng bytes throughput hơn. OS filesystem cache, antivirus, NFS/overlayfs, drive type và concurrent CI tasks ảnh hưởng kết quả.

### 22.1. Chạy copyIo

Sau khi đã dùng Fixtures tạo data:

~~~bash
./gradlew copyIo --no-build-cache --console=plain
./gradlew copyIo --no-build-cache --console=plain
~~~

Lần thứ hai có thể UP-TO-DATE nên **không đo được copy throughput**.

Để buộc task chạy:

~~~bash
./gradlew copyIo \
  --rerun-tasks --no-build-cache \
  --profile --console=plain
~~~

Nhưng destination đang có đầy đủ files, Sync có thể tận dụng per-file checks hoặc OS cache. Điều này đo steady-state task overhead, không phải fresh physical disk copy.

### 22.2. Fresh destination có kiểm soát

Linux/macOS từ **lab root**:

~~~bash
rm -rf build/io-copy
./gradlew copyIo --no-build-cache --profile --console=plain
~~~

Windows PowerShell:

~~~powershell
Remove-Item -LiteralPath build\io-copy -Recurse -Force -ErrorAction SilentlyContinue
.\gradlew.bat copyIo --no-build-cache --profile --console=plain
~~~

Chỉ xóa **build/io-copy** của lab; không xóa production workspace hoặc ~/.gradle. Chạy vài lượt, xóa destination trước từng lượt và ghi duration. **OS page cache** vẫn có thể giữ source bytes trong RAM; phân biệt “fresh destination” với “cold disk cache”.

### 22.3. Generate workload lớn hơn

~~~bash
java -cp tools/out demo.tools.Fixtures \
  io-fixtures 64 1024
~~~

Stdout:

~~~text
FILES=64;BYTES=67108864
~~~

Nếu thư mục fixtures còn những file từ workload trước với count lớn hơn, dùng một directory khác hoặc chủ động dọn đúng directory lab trước khi so sánh. Không đưa dữ liệu generated I/O vào Git.

### 22.4. I/O của reports và packaging

Test task có thể ghi JUnit XML/HTML; plugin JaCoCo, Checkstyle và Javadoc tạo nhiều output files. Nếu reports có chi phí lớn, đo riêng. Không tắt JUnit XML trong CI nếu tổ chức dùng nó để phát hiện flaky tests; chỉ thay report formats khi biết downstream consumers và đã chứng minh lợi ích.

Khi JAR/ZIP task lâu, xem số entries, compression, reproducibility, signed archives, antivirus và disk latency. Không xem mọi ZIP packaging là “compiler chậm”.

## 23. Dependency resolution khác việc tải JAR

Gradle có thể mất thời gian:

1. Resolve requested versions và variants.
2. Đọc POM/Gradle Module Metadata.
3. Resolve transitive dependencies, constraints, platforms.
4. Xác định repository gốc cho từng module.
5. Kiểm tra metadata cho dynamic/changing versions.
6. Download artifact files nếu chưa được cache.
7. Snapshot inputs và cung cấp classpath cho JavaCompile/Test.

**Dependency resolution không luôn có actual JAR download.** Các task như **dependencies** có thể chỉ resolve graph/metadata. Lệnh copyTestArtifacts/resolveTestArtifacts của lab buộc Gradle cung cấp file JAR, nhưng cũng có output copy I/O.

### 23.1. Đọc dependency graph

~~~bash
./gradlew :app:dependencies \
  --configuration testRuntimeClasspath \
  --profile --console=plain
~~~

Đây là báo cáo metadata/graph. Nó không chứng minh tất cả JAR bytes đã được tải ở invocation hiện tại.

### 23.2. Buộc artifact files được cần đến

~~~bash
./gradlew :app:resolveTestArtifacts \
  --no-build-cache --info --profile --console=plain
~~~

Task Sync đọc testRuntimeClasspath và copy các JARs vào **app/build/dependency-probe**.

**Diễn giải đúng:** tổng thời gian task = dependency resolution nếu cần + artifact download nếu thiếu + snapshotting + file copy. Để tách network, dùng Build Scan Network Activity/Dependency Resolution tabs nếu được phép hoặc xem --info/network logs.

### 23.3. Warm dependency cache

Chạy task hai lần có thể gặp UP-TO-DATE ở lần hai vì copied output đã hợp lệ. Khi đó không được gọi đó là “dependency cache nhanh”. Nếu cần quan sát warmed artifact resolution, xóa riêng **app/build/dependency-probe** trong lab rồi chạy lại; giữ Gradle User Home cache.

### 23.4. Cold dependency cache an toàn

Không xóa bừa **~/.gradle/caches/** của máy người dùng vì ảnh hưởng nhiều projects. Dùng một **GRADLE_USER_HOME riêng cho benchmark**:

~~~bash
mkdir -p bench-gradle-home

GRADLE_USER_HOME="$PWD/bench-gradle-home" \
  ./gradlew :app:resolveTestArtifacts \
  --no-build-cache --info --profile --console=plain

GRADLE_USER_HOME="$PWD/bench-gradle-home" \
  ./gradlew :app:resolveTestArtifacts \
  --no-build-cache --info --profile --console=plain
~~~

Khi so cold và warm, nhận diện thêm các confounders: Wrapper distribution, Daemon startup, Gradle plugin dependencies, JDK provisioning, filesystem snapshots và task output UP-TO-DATE. Một dedicated user home tốt cho cô lập cache, nhưng **lần đầu vẫn không phải thời gian network thuần**.

### 23.5. --refresh-dependencies không đồng nghĩa download lại tất cả

~~~bash
./gradlew :app:resolveTestArtifacts \
  --refresh-dependencies --info --console=plain
~~~

Gradle có thể dùng HTTP HEAD hoặc checksums để xác định artifacts/metadata không đổi; bytes không nhất thiết được download lại. Cờ này kiểm tra freshness của dependency cache, không phải lệnh ép full cold download.

### 23.6. --offline

~~~bash
./gradlew :app:resolveTestArtifacts \
  --offline --console=plain
~~~

Gradle chỉ dùng dependencies đã có trong cache và không truy cập remote repositories cho resolution. Nếu JUnit artifact còn thiếu, fail là đúng; không tự tạo JAR giả.

## 24. Tác động của repository order và changing versions

Gradle tìm dependencies theo thứ tự repositories. Một repo ở đầu liên tục 404/timeout, repo mirror quá xa, hoặc nhiều repos chứa cùng groups sẽ gây metadata lookup thừa.

Hướng xử lý:

- Dùng repository hosting nhiều dependencies nhất ở vị trí phù hợp.
- Giảm repositories thừa, dùng **content filters** để định tuyến groups.
- Sử dụng repository mirror/proxy gần mạng CI khi đáng tin.
- Pin stable versions hoặc dependency locking khi policy cần reproducibility.
- Không tải POM/JAR thủ công bằng URL trong project configuration.
- Không tắt TLS/dependency verification chỉ để giảm vài giây.

### 24.1. Dynamic/changing modules

Một dependency động dạng:

~~~groovy
dependencies {
    testImplementation 'org.example:sample-utils:1.+'
}
~~~

là **snippet lý thuyết, không phải dependency trong lab runnable**. Dynamic versions hoặc SNAPSHOT/changing dependencies có TTL và có thể kích hoạt metadata refresh.

Gradle default thường cache resolution của dynamic versions/changing modules khoảng **24 giờ**, có thể điều chỉnh:

~~~groovy
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor 10, 'minutes'
    resolutionStrategy.cacheChangingModulesFor 4, 'hours'
}
~~~

TTL ngắn giúp thấy bản mới sớm nhưng tăng remote requests. TTL dài có thể làm development dùng metadata cũ. Không áp một TTL tùy ý lên mọi projects nếu không có nhu cầu.

### 24.2. Repository stickiness

Gradle lưu metadata gắn với repository nơi artifact được resolve, tránh âm thầm lấy cùng coordinate từ nguồn khác có bytes không giống. Đổi repository URL/order có thể thay hit rate và provenance. Repository strategy là **vấn đề correctness và supply chain**, không chỉ performance.

### 24.3. Antipattern: resolve trong configuration phase

Không làm:

~~~groovy
def jars = configurations.testRuntimeClasspath.files
println jars.size()
~~~

ở top-level build.gradle. Nó buộc dependency resolution ngay khi cấu hình project, kể cả lệnh **help** không cần JUnit. Trong lab, **Sync.from(configurations.testRuntimeClasspath)** cho phép Gradle resolve khi task thực sự cần các file đầu vào.

## 25. Build cache, dependency cache, configuration cache

| Cơ chế | Tác dụng | Dấu hiệu |
| --- | --- | --- |
| **UP-TO-DATE** | Task outputs tại workspace còn hợp lệ | Task được skip |
| **FROM-CACHE** | Khôi phục task outputs từ build cache | Task action không chạy |
| **Dependency cache** | Tái sử dụng downloaded JARs và module metadata | Không đồng nghĩa Task FROM-CACHE |
| **Configuration cache** | Tái sử dụng project configuration/task graph | Console báo configuration cache reused |
| **Incremental JavaCompile** | Chỉ compile phần source thay đổi | JavaCompile vẫn có thể EXECUTED |
| **Compile avoidance** | Downstream không cần compile nếu ABI không đổi | Downstream task có thể UP-TO-DATE |

Benchmark **Test forks** cần các Test actions được thực thi thật, không phải FROM-CACHE. Benchmark **compiler fork** cũng vậy. Khi đo trải nghiệm developer warm build, lại nên **giữ caching** vì đó là điều kiện người dùng thật trải nghiệm. Hai kiểu benchmark trả lời hai câu hỏi khác nhau.

## 26. Task timing, critical path và hiệu quả thực sự

Giả sử có các tasks:

~~~text
:library:compileJava     4 s
:app:compileJava         3 s
:app:test                6 s
:app:copyResources       2 s
~~~

Nếu tasks chạy tuần tự trên critical path, giảm Test từ 6 xuống 4 giây có thể giảm tổng build. Nếu Test chạy song song và task khác giữ critical path dài hơn, cải thiện Test chưa chắc giảm tổng wall time.

Do đó:

- Đo Test task duration khi điều chỉnh Test forks.
- Đo compiler task durations khi điều chỉnh compiler options.
- Đo resolution timing/network hoạt động khi điều chỉnh Maven repositories.
- **Luôn** đo end-to-end wall-clock ở workflow mục tiêu.
- Xem những tasks nào trên critical path; đừng chỉ tối ưu task có duration lớn nhất nếu nó không chặn hoàn tất.

Công thức cải thiện:

~~~text
improvement_percent =
    (baseline_median_ms - variant_median_ms)
    / baseline_median_ms * 100
~~~

Ví dụ baseline median 5000 ms, variant median 4500 ms thì cải thiện minh họa 10%. Chỉ là phép tính, không phải số liệu thực nghiệm của lab.

## 27. Phân tích CSV

File **bench-results/samples.csv** có dạng:

~~~csv
scenario,iteration,wall_ms,exit_code
forks1,1,2300.000,0
forks1,2,2200.000,0
forks1,3,2250.000,0
forks2,1,2050.000,0
forks2,2,2080.000,0
forks2,3,2070.000,0
~~~

Đây là **dữ liệu minh họa không phải kết quả thực đo**.

Nếu có Python 3, có thể tính median:

~~~python
import csv
from collections import defaultdict
from statistics import median

samples = defaultdict(list)

with open("bench-results/samples.csv",
          encoding="utf-8", newline="") as stream:
    for row in csv.DictReader(stream):
        if int(row["exit_code"]) == 0:
            samples[row["scenario"]].append(
                float(row["wall_ms"]))

for label in sorted(samples):
    values = sorted(samples[label])
    print(label,
          "runs=", len(values),
          "median_ms=", round(median(values), 3),
          "min_ms=", round(values[0], 3),
          "max_ms=", round(values[-1], 3))
~~~

Python ở đây chỉ dùng **phân tích kết quả**, không cần cho mã lab Java 17. Median của 3 samples chưa đủ chứng minh sự khác biệt nhỏ có ý nghĩa thống kê; dùng thêm mẫu/CI intervals khi quyết định quan trọng.

## 28. CI minh họa

Ví dụ **.github/workflows/gradle-perf.yml**:

~~~yaml
name: Gradle performance lab

on:
  workflow_dispatch:
  pull_request:

permissions:
  contents: read

jobs:
  benchmark:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Gradle
        uses: gradle/actions/setup-gradle@v6

      - name: Compile benchmark tools
        shell: bash
        run: |
          mkdir -p tools/out
          javac --release 17 -encoding UTF-8 -d tools/out \
            tools/src/demo/tools/Fixtures.java \
            tools/src/demo/tools/Measure.java

      - name: Warm up the build
        run: |
          ./gradlew :app:test -PbenchTests=true \
            --no-build-cache --console=plain

      - name: Compare test fork counts
        shell: bash
        run: |
          java -cp tools/out demo.tools.Measure \
            forks1 3 ./gradlew :app:test \
            -PbenchTests=true -PtestForks=1 \
            -PforkEvery=0 --no-build-cache \
            --max-workers=4 --console=plain

          java -cp tools/out demo.tools.Measure \
            forks2 3 ./gradlew :app:test \
            -PbenchTests=true -PtestForks=2 \
            -PforkEvery=0 --no-build-cache \
            --max-workers=4 --console=plain

      - name: Preserve logs and test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: gradle-performance-results
          path: |
            bench-results/**
            app/build/test-results/test/TEST-*.xml
          if-no-files-found: warn
          retention-days: 14
~~~

**Giới hạn:** GitHub-hosted shared runner có noisy neighbors, vCPU/memory quotas và cache policy riêng. Script này giúp học quy trình, không tự tạo số liệu đủ tin cậy cho một quyết định vài phần trăm. Đối với benchmark quan trọng nên dùng dedicated runner, multiple batches, fixed JDK/Gradle images và đối chiếu logs.

Không cấp signing key hoặc Maven publish token cho PR benchmark. Không sử dụng **continue-on-error** hoặc **|| true** để che lỗi test/benchmark. Được phép upload logs nếu workflow fail, nhưng không đưa environment dumps hoặc Gradle user home chứa credentials lên artifact public.

## 29. Các lỗi đo đạc phổ biến

| Dấu hiệu | Nguyên nhân có thể | Phép kiểm tra/sửa |
| --- | --- | --- |
| Forks=4 chậm hơn forks=2 | CPU/RAM/I-O contention | Quan sát cores, RSS và test worker count |
| forkEvery=1 rất chậm | JVM startup thường xuyên | Thử forkEvery=0 hoặc giá trị lớn khi có leak |
| Tests fail khi parallel | Shared database, port, filesystem | Isolate per worker, reset state |
| Test NO-SOURCE nhưng build xanh | Test classes không được phát hiện | Kiểm tra test source set/JUnit XML |
| Test UP-TO-DATE trong benchmark | Action không chạy | benchTests=true, --no-build-cache |
| Test FROM-CACHE | Outputs được restore | --no-build-cache để đo execution |
| --rerun-tasks làm test benchmark chậm | Compiler dependencies cũng bị buộc chạy | Dùng benchTests opt-in trên Test task |
| Compiler fork thấy không khác | Project quá nhỏ, startup/noise | Đo project thực có nhiều Java source |
| Compiler fork gây OOM | Nhiều compiler/JVMs | Giảm workers, xem RSS/GC |
| compileJava chạy sau source edit | Source/ABI/input changes | --info, incremental compilation |
| :app:compileJava không chạy sau lib method body đổi | Compile avoidance hợp lệ | Kiểm tra ABI và output |
| Copy task chạy rất nhanh lần 2 | UP-TO-DATE hoặc OS cache | Xóa riêng destination khi đo fresh copy |
| Tiny files chậm | Metadata/IOPS overhead | So same bytes/different file counts |
| Cold dependency resolution chậm | Metadata/downloads, new Daemon | Dùng dedicated GRADLE_USER_HOME và network logs |
| --refresh-dependencies không download hết | HEAD/checksum reuse | Đây là hành vi đúng của Gradle |
| --offline fail | JAR/metadata thiếu cache | Warm cache hoặc cấu hình repo |
| Build Scan không khả dụng | Plugin/server/TOS/policy | Dùng --profile và --info local |
| Task times cộng lớn hơn wall time | Tasks chồng lấp | Xem timeline/critical path |
| CI nhanh bất thường | Test filtering/skip/cache | Kiểm tra outcomes và JUnit counts |
| Console quá nhiều logs | showStandardStreams/--debug | Tắt khi đo |
| Source thay giữa A/B | Workload không tương đương | Pin commit |
| Wrapper/JDK thay đổi | Compiler/process behavior khác | Giữ toolchain cố định |
| Maven mirror không tin cậy | Tối ưu gây supply-chain risk | TLS, verification, approval |
| Reports bị tắt | Benchmark “nhanh” nhưng mất CI diagnostics | Giữ reports cần thiết |
| Heap tăng mà không cải thiện | Không memory-bound | Xem GC, CPU và I/O |
| Remote cache chậm | Download/unpack cost > execution | Đo hit cost thực |
| Cache metric bị gọi là CPU time | Cache outputs không phải execution | Xem task outcomes |
| Một lần fastest được chọn | Cherry-picking | Median/variance với samples đủ |

## 30. Bài tập thực hành

### Bài 1 — Baseline

Chạy **./gradlew :app:test --profile**. Đọc report và xác nhận bốn test methods; tách time của compilation và test task.

### Bài 2 — Test forks

Đo testForks=1, 2, 4 bằng Measure; đọc median và peak memory. Có chắc forks4 luôn nhanh nhất không? Vì sao?

### Bài 3 — forkEvery

Giữ testForks=1, so forkEvery=0 và 1. Dùng showTestWorkers để nhìn worker IDs trong một run chẩn đoán, nhưng tắt logging khi benchmark.

### Bài 4 — Compiler fork

So compilerFork=false/true với --rerun-tasks --no-build-cache, xem profile per JavaCompile. Giải thích sự khác biệt giữa compiler process và Test JVM.

### Bài 5 — Incremental compilation

Chỉnh method body trong library nhưng giữ public signature, chạy :app:compileJava không --rerun-tasks. Giải thích compile avoidance.

### Bài 6 — ABI change

Trong branch thử nghiệm, đổi public API library rồi sửa consumer. Vì sao app JavaCompile có thể phải chạy lại?

### Bài 7 — I/O small files

Dùng Fixtures để so 64 × 64 KiB với 512 × 8 KiB. Cùng tổng bytes, different file count. Đo fresh copy và ghi OS cache state.

### Bài 8 — I/O throughput

Tăng workload lên 64 MiB, đo với local SSD và network-mounted directory nếu có quyền. Vì sao end-to-end wall time không thuần là disk throughput?

### Bài 9 — Cold dependencies

Dùng dedicated GRADLE_USER_HOME, chạy resolveTestArtifacts cold/warm. Ghi số lần download, task outcome và JVM startup confounders.

### Bài 10 — --refresh-dependencies

Quan sát --info; vì sao việc refresh metadata không nhất thiết tải lại cùng JAR?

### Bài 11 — --offline

Sau khi warm cache, chạy --offline; thử cấu hình test dependency mới chưa có trong cache ở branch thử nghiệm. Giải thích failure.

### Bài 12 — Configuration-phase anti-pattern

Tạm đọc **configurations.testRuntimeClasspath.files** ở top-level build.gradle, chạy help. Quan sát phụ thuộc được resolve sớm; hoàn tác.

### Bài 13 — Reports và quality

Thử đo overhead JUnit HTML/XML khi có nhiều test classes. Những reports nào CI bắt buộc giữ để phát hiện lỗi?

### Bài 14 — Memory contention

Trên runner giới hạn RAM, so 2 forks và 4 forks. Theo dõi RSS/GC để tránh đề xuất gây OOM.

### Bài 15 — CI regression

Xây quy trình 5–10 repetitions, lưu CSV/logs, chỉ báo regression khi chênh lệch vượt noise band và tests vẫn pass.

### Bài 16 — Critical path

Tìm một task lâu nhưng không thuộc critical path. Nếu tối ưu task ấy thì wall-clock có luôn giảm không?

### Bài 17 — Security

Một repository proxy nội bộ nhanh hơn nhưng không có TLS hoặc dependency verification. Có chấp nhận chỉ vì nhanh không? Thiết kế biện pháp sửa đúng.

## 31. Câu hỏi tự kiểm tra

1. Wall time khác task duration ở đâu?
2. Vì sao không cộng mọi task durations để ra build time?
3. Test.maxParallelForks mặc định bao nhiêu?
4. Test.forkEvery mặc định bao nhiêu?
5. maxParallelForks điều khiển gì?
6. forkEvery điều khiển gì?
7. forkEvery=1 có đảm bảo nhanh hơn không?
8. --parallel khác Test forks thế nào?
9. --max-workers ảnh hưởng gì?
10. JUnit Jupiter parallel mode có phải Gradle fork không?
11. JVM test workers dùng bộ nhớ nào ngoài heap?
12. Vì sao tăng forks gây flakiness?
13. JavaCompile.options.fork làm gì?
14. Khi nào compiler fork có thể có lợi?
15. Incremental compilation khác compile avoidance thế nào?
16. Khi nào không nên dùng --rerun-tasks?
17. Vì sao benchTests=true đi kèm --no-build-cache?
18. UP-TO-DATE và FROM-CACHE có đo task execution không?
19. Dependency resolution có luôn download JAR không?
20. --refresh-dependencies có tải lại mọi artifact không?
21. --offline sẽ làm gì nếu thiếu artifact cache?
22. Tại sao repository order ảnh hưởng latency?
23. Vì sao không resolve dependencies trong configuration phase?
24. Sync task UP-TO-DATE có đo disk I/O không?
25. Vì sao nhiều files nhỏ thường khó xử lý hơn ít files lớn cùng tổng bytes?
26. OS page cache ảnh hưởng benchmark thế nào?
27. Vì sao cần warm-up?
28. Vì sao phải đo nhiều samples và đảo thứ tự A/B?
29. Median có loại hết noise không?
30. Build Scan có thể có vấn đề quyền riêng tư gì?
31. Gradle dependency cache khác build cache ở đâu?
32. Configuration cache giúp phase nào?
33. Vì sao tăng heap khi disk bị nghẽn thường không giải quyết?
34. CPU quota trên CI khác số cores reported như thế nào?
35. Khi đưa ra đề xuất performance cần lưu những gì?

**Đáp án gợi ý:** (1) toàn lệnh so với task; (2) parallel overlap; (3) 1; (4) 0; (5) số test JVMs đồng thời; (6) classes mỗi worker process; (7) không; (8) task scheduling so với test concurrency; (9) worker budget; (10) không; (11) metaspace/native/thread stacks; (12) shared state; (13) compiler process; (14) giảm GC pressure trong build lớn; (15) selective recompile so với skip downstream; (16) khi đo compile avoidance; (17) đảm bảo Test action chạy; (18) không; (19) không; (20) không; (21) fail nếu cache thiếu; (22) lookup tới repos; (23) gây network/I/O ngay cả help; (24) không; (25) metadata/opens/IOPS; (26) warm reads từ RAM; (27) JVM/dependency/daemon state; (28) giảm bias; (29) không; (30) tải build diagnostics ra dịch vụ; (31) task outputs so với dependencies; (32) configuration; (33) bottleneck khác; (34) virtualization/container quota; (35) commit/Gradle/JDK/hardware/cache/outcomes/test counts/timings/variance.

## 32. Checklist áp dụng vào dự án thực

- [ ] Biết rõ workflow cần tối ưu: developer incremental hay cold CI.
- [ ] Có baseline và chỉ một biến chính trong mỗi phép đo.
- [ ] Ghi Gradle Wrapper, JDK, plugins và source commit.
- [ ] Cố định CPU/vCPU, RAM, filesystem type và runner image.
- [ ] Có warm-up và ít nhất vài repetitions.
- [ ] Không so nhầm EXECUTED với UP-TO-DATE/FROM-CACHE.
- [ ] Không gọi NO-SOURCE/SKIPPED là test pass.
- [ ] Quan sát task duration và total wall-clock.
- [ ] Biết Test.maxParallelForks/forkEvery là hai knobs khác nhau.
- [ ] Không vượt resource budget khi tăng test forks.
- [ ] Kiểm tra isolation của test files, DB, sockets và external services.
- [ ] Kiểm tra GC, RSS và process startup nếu thay fork policy.
- [ ] Compiler fork được so khi thực sự có compiler actions.
- [ ] Incremental compilation được đo không dùng --rerun-tasks.
- [ ] Compile avoidance được đánh giá theo public ABI changes.
- [ ] I/O đo số files, bytes, disk type, latency và OS page cache.
- [ ] Copy output destination được chuẩn bị đúng khi đo fresh copy.
- [ ] Dependency metadata resolution khác downloads được ghi riêng.
- [ ] Không xóa ~/.gradle bừa bãi; dùng dedicated Gradle User Home.
- [ ] Không hiểu sai --refresh-dependencies thành “tải lại hết”.
- [ ] Không resolve dependency files ở configuration time.
- [ ] Giữ Maven repositories, TLS và verification an toàn.
- [ ] CI giữ JUnit XML/report evidence khi fail.
- [ ] Đọc critical path trước khi ưu tiên tối ưu.
- [ ] Tính median, min/max và variance, không cherry-pick.
- [ ] Đảo thứ tự A/B khi có thể.
- [ ] Chỉ giữ thay đổi nhanh hơn ổn định và không giảm correctness.
- [ ] Có rollback plan nếu change làm flakiness/OOM tăng.

## 33. Tài liệu chính thức

- [Gradle — Improve the Performance of Gradle Builds](https://docs.gradle.org/current/userguide/performance.html)
- [Gradle — Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — Building Java & JVM projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html)
- [Gradle — Dependency Resolution](https://docs.gradle.org/current/userguide/dependency_resolution.html)
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html)
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Profile report option](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Gradle Develocity — Build Scans](https://gradle.com/develocity/)
- [Gradle Profiler — GitHub project](https://github.com/gradle/gradle-profiler)

**Kết luận:** Test forks, compiler, filesystem I/O và dependency resolution đều có thể làm Gradle build chậm nhưng cần những phép đo khác nhau. **maxParallelForks** kiểm soát concurrency của Test JVMs, **forkEvery** kiểm soát tần suất thay JVM; **JavaCompile.options.fork** ảnh hưởng compiler process; I/O cần đo số files/bytes và latency; dependency resolution cần phân biệt metadata lookups với artifact downloads. Kết hợp **--profile**, **--info**, task outcomes, Java 17 benchmark CSV, lặp lại có kiểm soát và critical path analysis sẽ giúp chọn tối ưu đúng thay vì đoán theo cảm giác.
