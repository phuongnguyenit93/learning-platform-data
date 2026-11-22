# Chạy task song song, giới hạn worker và kiểm soát tài nguyên trong Gradle

## 1. Mục tiêu: nhanh hơn nhưng vẫn đúng

Trong một build Java, Gradle có thể phải biên dịch nhiều module, chạy unit test, sinh mã, kiểm tra chất lượng, tạo JAR và đóng gói ứng dụng. Một số công việc độc lập có thể chạy đồng thời; một số khác cần output của task trước. Dù độc lập về code, chúng vẫn có thể cạnh tranh CPU, bộ nhớ, đĩa, network, cổng TCP, Docker daemon hoặc database.

**Chạy song song không phải mục tiêu tự thân.** Mục tiêu là giảm thời gian chờ **mà không làm sai kết quả, gây flaky tests, hết RAM hoặc làm CI kém ổn định**. Muốn quyết định có nên tăng parallelism, hãy trả lời:

- Các task có phụ thuộc dữ liệu vào nhau không? Chúng có thể chạy đồng thời an toàn không?
- Giới hạn `--max-workers` có phù hợp CPU quota và memory thực tế?
- `Test.maxParallelForks` có làm xuất hiện nhiều JVM hơn khả năng runner đáp ứng?
- Worker API có giải quyết được một task lớn không, hay chỉ tạo overhead?
- Một resource dùng chung có cần `BuildService.maxParallelUsages`?
- Configuration Cache có làm thay đổi khả năng task chạy đồng thời trong cùng subproject?
- Có đo được hiệu quả trên workload và trạng thái cache tương đương không?

Bài này dùng một ví dụ **multi-project Java 17 chạy được**, so sánh `--parallel`, `--no-parallel` và `--max-workers`; sau đó đi sâu vào forked test processes, Worker API, shared build services, ngân sách tài nguyên và CI.

## 2. Các mức độ parallelism: không trộn với nhau

| Tầng | Công cụ | Nơi áp dụng | Điều cần nhớ |
| --- | --- | --- | --- |
| Song song giữa các Gradle tasks | `--parallel`, `org.gradle.parallel` | Task scheduler | Chỉ các tasks đủ điều kiện; tôn trọng dependency graph |
| Giới hạn worker toàn build | `--max-workers`, `org.gradle.workers.max` | Invocation/scheduler | Là giới hạn worker capacity, **không** phải RAM hoặc OS thread cap |
| Chia một task thành work items | `WorkerExecutor` | Custom task/plugin | `noIsolation`, `classLoaderIsolation`, `processIsolation` |
| Fork nhiều JVM chạy tests | `Test.maxParallelForks` | Từng Gradle Test task | Giới hạn số test processes, có quan hệ với max workers |
| Song song bên trong test engine | JUnit Jupiter/framework config | Bên trong JVM test | Method/class execution có thể có threads riêng |
| Nhiều builds trong CI | CI parallel jobs/runners | Nhiều Gradle invocations | Không được một `--max-workers` của job A khóa job B |
| Song song của external tools | Docker/BuildKit, compiler, Node/native apps | Process riêng | Tool có thread/process pool và resource policy riêng |

**Ví dụ phân biệt:** một build chạy `--parallel` và `--max-workers=2` có thể đồng thời chọn tasks từ hai subprojects. Một trong các tasks ấy là `Test` với `maxParallelForks=2`: test JVMs được Gradle điều phối bằng worker limits, không phải “2 Gradle workers × 2 test forks = chắc chắn 4 JVM”. Một external tool lại có thể tự tạo nhiều threads trong một worker slot. Phải nhìn **từng tầng thực tế**.

### 2.1. Ba khái niệm dễ nhầm

**Concurrency** là nhiều công việc cùng tiến triển trong cùng khoảng thời gian. **Parallelism** là nhiều phần công việc thật sự chạy đồng thời trên CPU cores/processors. **Throughput/latency** là kết quả đo được. Tăng concurrency không bảo đảm latency thấp nếu CPU, RAM hoặc I/O bị bão hòa.

### 2.2. Tối ưu khác song song

`UP-TO-DATE` và `FROM-CACHE` có thể làm task không cần chạy. Incremental compilation có thể giảm khối lượng compile. Configuration Cache có thể tránh việc cấu hình lại build. Đây là các tối ưu khác, đôi khi tạo giá trị lớn hơn việc chạy nhiều tasks cùng lúc.

## 3. --parallel: cho phép tasks độc lập được lập lịch đồng thời

Gradle CLI:

~~~bash
./gradlew build --parallel
~~~

Hoặc cấu hình `gradle.properties`:

~~~properties
org.gradle.parallel=true
~~~

Tắt cho một invocation:

~~~bash
./gradlew build --no-parallel
~~~

Theo tài liệu Gradle, mode `--parallel` đặc biệt hữu ích trong **multi-project builds** có các subprojects độc lập. Gradle có thể chạy tasks của các projects khác nhau cùng lúc, miễn dependency graph và worker resources cho phép.

**Không có bảo đảm** “mọi task ở mọi module chạy một lượt”:

- Task consumer vẫn phải chờ producer.
- Tasks không được chọn trong task graph sẽ không tự chạy.
- Các tasks cần service slot/lock phải chờ.
- Nếu worker capacity chỉ có một, phần lớn Gradle-managed work phải tuần tự.
- Cache/up-to-date checking có thể skip tasks thay vì execute.
- Scheduler không cam kết thứ tự logs cho những tasks độc lập.

### 3.1. Configuration Cache có một sắc thái mới

Các bản Gradle hiện hành hỗ trợ việc thực thi tasks song song **ngay trong cùng một subproject khi Configuration Cache được bật**. Bởi vậy câu cũ “hai tasks cùng project luôn tuần tự” không còn đúng tuyệt đối. Đừng dựa vào thứ tự task cùng project để ghi chung một thư mục hay thay đổi mutable global state.

Muốn so `--parallel` ở chế độ multi-project thông thường mà không bị tác động bởi mode Configuration Cache, có thể dùng `--no-configuration-cache` trong thí nghiệm. Khi bật trở lại:

~~~bash
./gradlew :cli:build --configuration-cache --parallel
~~~

cần kiểm tra plugin/task compatibility và resource isolation. Configuration Cache **không phải** một cơ chế khóa tài nguyên dùng chung.

## 4. --max-workers: giới hạn concurrency chứ không cấp thêm CPU

Ví dụ:

~~~bash
./gradlew build --parallel --max-workers=2
~~~

Cấu hình mặc định theo project/user:

~~~properties
org.gradle.workers.max=2
~~~

Theo tài liệu Gradle, mặc định liên quan đến số processors khả dụng; flag CLI cho phép đặt giới hạn trong invocation. Giới hạn này điều phối Gradle worker capacity cho work mà Gradle quản lý, bao gồm worker-enabled tasks/Test worker processes theo contract tương ứng.

| Giá trị | Ý nghĩa | Không có nghĩa |
| --- | --- | --- |
| `--max-workers=1` | Rất ít concurrency Gradle-managed | Mọi OS process đều chỉ có 1 thread |
| `--max-workers=2` | Cho phép tối đa hai worker slots | Runner tự có hai CPU cores |
| `--max-workers=8` | Nới mức worker capacity | Mọi task tự động đạt tốc độ gấp 8 |
| `org.gradle.workers.max=2` | Thiết lập worker limit mặc định | Giới hạn Gradle Daemon heap là 2 GiB |
| `--no-parallel` | Tắt mode parallel project tasks | Tắt mọi framework internal parallelism |

**Worker là một giới hạn trên**, không phải số threads phải chạy. Trong graph chỉ có một task runnable, dù `max-workers=16` Gradle cũng không tự chia nó thành 16 tasks.

### 4.1. Tại sao tăng worker quá cao có thể chậm hơn?

Nhiều JavaCompile/Test workers cùng lúc có thể gây:

- CPU context switching và run queue dài;
- garbage collection và áp lực heap;
- swap/page faults hoặc OOM;
- disk I/O wait, đặc biệt với output nhiều file nhỏ;
- tranh chấp cache/metadata, database locks;
- rate-limit 429 của repository/external API;
- build race do tasks thiếu dependency.

Nhiều workers chỉ tốt nếu **workload độc lập và runner còn headroom**. Một máy 2 CPU quota/4 GiB RAM có thể hoạt động ổn định hơn với mức 1–2 workers thay vì 8; đó là ví dụ định hướng, không phải khuyến nghị cố định.

## 5. Task dependency graph luôn có quyền ưu tiên

Giả sử:

~~~text
:messages:compileJava
          |
          v
    :cli:compileJava
          |
          v
       :cli:run

:reports:simulateWork    (nhánh độc lập)
~~~

`:cli:compileJava` phải nhận classes/dependency của `:messages` phù hợp trước. `:reports:simulateWork` có thể được lên lịch song song với công việc ở nhánh Java. `--parallel` không cho phép bỏ qua những cạnh dữ liệu.

**Bốn loại quan hệ cần phân biệt:**

1. `dependsOn`: đưa prerequisite task vào graph.
2. Producer output provider → consumer input provider: mô hình hóa **dữ liệu và implicit dependency**, thường tốt hơn chỉ đặt thứ tự.
3. `mustRunAfter`: thứ tự bắt buộc **nếu cả hai tasks đã được chọn**, không tự đưa producer vào graph.
4. `shouldRunAfter`: ưu tiên thứ tự mềm, không phải dependency dữ liệu.

Nếu hai tasks cùng ghi một file, **thêm `mustRunAfter` không chữa overlapping outputs**. Cần một owner rõ, tách output path hoặc ghép công việc vào một producer đúng nghĩa.

## 6. Ví dụ đầy đủ Java 17: ba subprojects độc lập một phần

Ta tạo project `parallel-lab`:

- `:messages`: Java library và một task `simulateWork`.
- `:cli`: Java application dùng `:messages`.
- `:reports`: một Base-plugin project có `simulateWork` độc lập.
- Root: task `demoParallel` gom hai simulations, task `demoAppAndReport` gom app và reports.

Mỗi `simulateWork` chờ 900 ms để dễ nhìn task scheduling. **`Thread.sleep` không phải production optimization hay CPU benchmark.**

### 6.1. Cấu trúc file

~~~text
parallel-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── messages/
│   ├── build.gradle.kts
│   └── src/main/java/demo/messages/Greeter.java
├── cli/
│   ├── build.gradle.kts
│   └── src/main/java/demo/cli/Main.java
└── reports/
    └── build.gradle.kts
~~~

Yêu cầu: JDK 17 hoặc toolchain Java 17 được provision, Gradle Wrapper tương thích và quyền ghi build directory. Không cần Docker, database hay third-party production Java dependency.

### 6.2. settings.gradle.kts

~~~kotlin
rootProject.name = "parallel-lab"
include(":messages", ":cli", ":reports")
~~~

`include` tạo ba subprojects trong một build. Nó không tự định nghĩa ai phụ thuộc ai.

### 6.3. Root build.gradle.kts

~~~kotlin
plugins {
    base
}

tasks.register("demoParallel") {
    group = "verification"
    description = "Run two independent simulated tasks"
    dependsOn(
        ":messages:simulateWork",
        ":reports:simulateWork"
    )
}

tasks.register("demoAppAndReport") {
    group = "verification"
    description = "Run app and independent report task"
    dependsOn(
        ":cli:run",
        ":reports:simulateWork"
    )
}
~~~

**Quan trọng:** `dependsOn(A, B)` không cam kết task A đứng trước B. Chỉ có quan hệ “aggregate phải chờ cả hai”. Không thêm `mustRunAfter` giữa messages và reports vì chúng được thiết kế độc lập.

### 6.4. messages/build.gradle.kts

~~~kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.register("simulateWork") {
    group = "verification"
    description = "Simulate messages work"

    doLast {
        logger.lifecycle("START messages")
        Thread.sleep(900L)
        logger.lifecycle("DONE messages")
    }
}
~~~

Task này không có output file và chỉ tạo console logs/chờ, nên không dùng `@CacheableTask` để giả tạo “caching”. Không cần `mavenCentral()` vì demo chính chỉ sử dụng built-in Gradle plugins và Java standard library.

### 6.5. messages/src/main/java/demo/messages/Greeter.java

~~~java
package demo.messages;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Class không có shared mutable state nên dễ tái sử dụng ở app. Nó có một public API đơn giản.

### 6.6. reports/build.gradle.kts

~~~kotlin
plugins {
    base
}

tasks.register("simulateWork") {
    group = "verification"
    description = "Simulate report work independently"

    doLast {
        logger.lifecycle("START reports")
        Thread.sleep(900L)
        logger.lifecycle("DONE reports")
    }
}
~~~

`:reports` không có Java sources, vì vậy Base plugin là đủ. Task này độc lập với `:messages` cả về input, output và resource. Đừng biến nó thành task ghi chung vào `messages/build`; điều đó sẽ phá tính độc lập.

### 6.7. cli/build.gradle.kts

~~~kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(project(":messages"))
}

application {
    mainClass.set("demo.cli.Main")
    applicationName = "parallel-cli"
}
~~~

Project dependency làm Gradle biết đúng compile/runtime classpath và producer task graph. Không dùng `tasks.named("compileJava").dependsOn(":messages:jar")` để thay thế dependency notation.

### 6.8. cli/src/main/java/demo/cli/Main.java

~~~java
package demo.cli;

import demo.messages.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "Gradle" : args[0];
        System.out.println(Greeter.greet(name));
    }
}
~~~

### 6.9. Lệnh Gradle chạy ứng dụng

Linux/macOS:

~~~bash
./gradlew :cli:run --args="Ada" --quiet
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :cli:run --args="Ada" --quiet
~~~

**Stdout Java Main chính xác:**

~~~text
Hello, Ada!
~~~

Nếu không truyền `--args`, Java in:

~~~text
Hello, Gradle!
~~~

Các log Gradle/JVM khác có thể xuất hiện theo version/môi trường, nên không xem hai dòng trên là toàn bộ transcript Gradle.

### 6.10. Chạy Java thuần bằng javac/java

Nếu muốn xác minh code Java 17 mà không chạy Gradle task graph:

Linux/macOS từ root:

~~~bash
mkdir -p out/messages out/cli

javac --release 17 -encoding UTF-8 \
    -d out/messages \
    messages/src/main/java/demo/messages/Greeter.java

javac --release 17 -encoding UTF-8 \
    -cp out/messages \
    -d out/cli \
    cli/src/main/java/demo/cli/Main.java

java -cp out/cli:out/messages demo.cli.Main Ada
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out\messages,out\cli | Out-Null

javac --release 17 -encoding UTF-8 -d out\messages messages\src\main\java\demo\messages\Greeter.java

javac --release 17 -encoding UTF-8 -cp out\messages -d out\cli cli\src\main\java\demo\cli\Main.java

java -cp "out\cli;out\messages" demo.cli.Main Ada
~~~

Stdout chính xác: `Hello, Ada!`. Lệnh javac/java **không thử song song Gradle**; nó chỉ kiểm chứng Java classes/classpath của ví dụ.

## 7. Thí nghiệm 1 — Không bật song song giữa projects

Linux/macOS:

~~~bash
./gradlew demoParallel \
    --no-parallel \
    --max-workers=2 \
    --no-configuration-cache \
    --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat demoParallel --no-parallel --max-workers=2 --no-configuration-cache --console=plain
~~~

Trong mode multi-project thông thường, hai tasks ở hai subprojects sẽ được Gradle xử lý tuần tự nếu không bật `--parallel`. Một dạng logs có thể là:

~~~text
START messages
DONE messages
START reports
DONE reports
~~~

Hoặc reports có thể xuất hiện trước messages. **Không cam kết thứ tự giữa tasks độc lập**; điều cần quan sát là các cặp START/DONE không overlap.

## 8. Thí nghiệm 2 — Song song với hai worker slots

~~~bash
./gradlew demoParallel \
    --parallel \
    --max-workers=2 \
    --no-configuration-cache \
    --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat demoParallel --parallel --max-workers=2 --no-configuration-cache --console=plain
~~~

Một log **minh họa có thể xảy ra**:

~~~text
START messages
START reports
DONE messages
DONE reports
~~~

Có thể thấy hai START trước một DONE, phản ánh overlap. Scheduler không cam kết thứ tự, timing hoặc cách console interleave logs. `Thread.sleep(900L)` cho mỗi task **không chứng minh** parallel production build luôn mất 0,9 giây và sequential build luôn mất 1,8 giây: thời gian tổng còn gồm startup, configuration, JVM, I/O và scheduling.

### 8.1. Thí nghiệm với max-workers=1

~~~bash
./gradlew demoParallel \
    --parallel \
    --max-workers=1 \
    --no-configuration-cache \
    --console=plain
~~~

Bật `--parallel` nhưng giới hạn chỉ một worker slot khiến Gradle không có capacity để chạy hai simulated tasks cùng lúc. Đây là minh họa tốt nhất cho sự khác nhau giữa **“được phép song song”** và **“có đủ tài nguyên để song song”**.

### 8.2. Thí nghiệm thứ ba: app và reports

~~~bash
./gradlew demoAppAndReport --parallel --max-workers=2
~~~

`:cli` phải chờ output của `:messages` để compile, nhưng `:reports:simulateWork` không phụ thuộc nhánh này. Nó có thể overlap với một phần công việc app khi Gradle có capacity. Không nên suy timeline cụ thể từ thứ tự `dependsOn` trong root build script.

## 9. Task graph đúng quan trọng hơn parallel flags

### 9.1. dependsOn là điều kiện thực thi

Nếu một task cần generated file trước, có thể dùng `dependsOn(generator)` để yêu cầu producer chạy. Tốt hơn nữa, nếu có provider cho generated file:

~~~kotlin
val generator = tasks.named("generateMetadata")
tasks.named("consumeMetadata") {
    dependsOn(generator)
}
~~~

Đây là **snippet khái niệm** trong project có hai tasks ấy; chúng không thuộc demo trước. Khi có task type với `@OutputFile`, nên nối trực tiếp `producer.outputFile` tới `consumer.inputFile` để Gradle hiểu cả data provenance, không chỉ order.

### 9.2. mustRunAfter không đủ

`mustRunAfter` chỉ đặt thứ tự khi cả hai tasks đã được thêm vào graph, không tự schedule task producer. `shouldRunAfter` còn yếu hơn. `finalizedBy` có nghĩa khác: chạy finalizer/cleanup theo Gradle semantics. **Không dùng ordering rule thay vì file input/output ownership.**

### 9.3. Không chia sẻ một output directory

Nếu hai tasks đồng thời ghi `build/generated/config.json`, dù bật/tắt `--parallel` chúng vẫn đang vi phạm output ownership. Có thể một lượt tuần tự tình cờ PASS, rồi parallel mode làm lỗi lộ ra. Giải pháp là tách output path, gom thành một producer hoặc quản lý artifact bằng TaskProvider đúng.

## 10. Gradle Daemon heap, Test JVM heap và OS memory là ba thứ khác nhau

Một Gradle invocation thường có:

~~~text
Gradle Daemon JVM
   |
   +--- Task actions / in-process work
   |
   +--- Worker API isolated worker process JVMs (nếu dùng)
   |
   +--- Java Test Worker #1
   +--- Java Test Worker #2
   |
   +--- Java compiler/forked tool JVMs (nếu cấu hình)
   |
   +--- External programs, Docker, native compilers ...
~~~

**`--max-workers` không đặt giới hạn RAM của cả hệ thống.** Nó điều chỉnh mức Gradle-managed work, còn mỗi JVM/process có chi phí heap + metaspace/native threads + GC và hệ điều hành.

### 10.1. Cấu hình heap Gradle Daemon

Ví dụ trong `gradle.properties`:

~~~properties
org.gradle.jvmargs=-Xmx1024m -Dfile.encoding=UTF-8
~~~

Đây là **giá trị mẫu**, không phải mặc định tốt nhất. Nó cấu hình JVM chạy Gradle Daemon, **không tự thiết lập** heap của mọi test JVM. Đổi `org.gradle.jvmargs` có thể tạo Gradle Daemon mới vì JVM args không khớp Daemon cũ.

### 10.2. Test JVM heap riêng

Trong build có Test tasks:

~~~kotlin
import org.gradle.api.tasks.testing.Test

tasks.withType<Test>().configureEach {
    maxParallelForks = 2
    maxHeapSize = "512m"
}
~~~

Mỗi forked test JVM có max heap riêng. Nếu runner cấp 4 GiB RAM, đừng cộng hai lần `512m` và cho rằng toàn hệ thống chỉ cần 1 GiB: Daemon, native memory, cache, OS và external processes còn tiêu thụ RAM.

### 10.3. CPU quota trong container khác host CPU count

JVM `Runtime.availableProcessors()` phụ thuộc phiên bản JDK và container/cgroup detection. Trên CI runner, CPU quota thực có thể khác số cores hiển thị trên host. Đo **CPU quota thực, peak RSS, GC và I/O wait** trước khi tăng workers.

## 11. maxParallelForks: song song của Gradle Test tasks

Gradle `Test` task có thuộc tính:

~~~kotlin
tasks.withType<Test>().configureEach {
    maxParallelForks = 2
    maxHeapSize = "512m"
    forkEvery = 0L
}
~~~

- `maxParallelForks=2` cho phép tối đa hai **test JVM processes** thực thi các test classes trong một Test task.
- Mặc định thường là `1`.
- `forkEvery=0L` cho phép reuse test process cho các classes, là mặc định thông thường.
- `forkEvery=1L` tạo một process mới sau mỗi test class, thường tốn startup và chỉ phù hợp khi cần process isolation.
- Test API xác định `maxParallelForks` không thể vượt `max-workers` cho build.
- Gradle điều phối test processes qua các Test tasks, nên không thể kết luận cứ có ba tasks mỗi task hai forks là luôn có sáu test processes chạy đồng thời.

**Đừng nhầm** với JUnit Jupiter method-level parallelism. JUnit có cấu hình threads/parallel execution riêng bên trong JVM; `maxParallelForks` chủ yếu chia test classes giữa Gradle test processes. Nếu một test suite chỉ có một class, tăng forks chưa chắc giúp gì.

### 11.1. Khi nào chọn maxParallelForks=1?

Một integration test suite dùng một DB schema duy nhất, cùng port 8080 hay fixed temp files có thể không chạy an toàn ở nhiều forks. `maxParallelForks=1` ở riêng task đó là giải pháp giảm concurrency, nhưng vẫn phải xem liệu nhiều **Test tasks khác nhau** có đang truy cập cùng resource không. Khi đó cần resource isolation/BuildService/CI control.

## 12. Demo JUnit Jupiter trên :messages

Đây là phần **bổ sung cho `messages/build.gradle.kts`** từ demo mục 6; giữ nguyên `java-library`, toolchain và simulated task đã có:

~~~kotlin
repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
    maxParallelForks = 2
    maxHeapSize = "512m"
}
~~~

JUnit 5.11.4 là **version được pin cho ví dụ**, không phải lời khẳng định phiên bản mới nhất. Cần repository/network hoặc mirror đã được tổ chức phê duyệt.

**messages/src/test/java/demo/messages/GreeterTest.java:**

~~~java
package demo.messages;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GreeterTest {
    @Test
    void greetsAda() {
        assertEquals("Hello, Ada!", Greeter.greet("Ada"));
    }
}
~~~

**messages/src/test/java/demo/messages/DefaultNameTest.java:**

~~~java
package demo.messages;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class DefaultNameTest {
    @Test
    void greetsGradle() {
        assertEquals("Hello, Gradle!", Greeter.greet("Gradle"));
    }
}
~~~

Chạy:

~~~bash
./gradlew :messages:test --max-workers=2 --console=plain
~~~

Hai test classes độc lập, không dùng shared mutable state. Kiểm tra số tests trong XML/HTML report, không đợi một stdout đặc biệt vì các tests chỉ assert.

Muốn buộc thực thi để quan sát test workers:

~~~bash
./gradlew :messages:test \
    --max-workers=2 \
    --rerun-tasks \
    --info --console=plain
~~~

`--rerun-tasks` có thể làm các tasks prerequisite rerun, nên không mặc định dùng nó làm benchmark của warm build.

## 13. Worker API: chia một task lớn thành công việc song song

`--parallel` chủ yếu chọn **các task nodes khác nhau**. Nếu chỉ có một task xử lý nhiều files độc lập, plugin author có thể dùng `WorkerExecutor` để submit một hoặc nhiều `WorkAction` instances.

~~~text
:generateAssets (một task)
    |
    +--> WorkAction A: assets/a.png
    +--> WorkAction B: assets/b.png
    +--> WorkAction C: assets/c.png
    |
    +--> await queue completion
    |
    v
build/generated/assets/
~~~

Worker API có ba isolation modes:

| API | Điểm chính | Đánh đổi |
| --- | --- | --- |
| `noIsolation()` | Work trong Gradle worker runtime, ít overhead | Thread safety/static shared state rất quan trọng |
| `classLoaderIsolation()` | Classloader riêng cho work actions theo cấu hình | Classloading và setup overhead |
| `processIsolation()` | Worker daemon JVM riêng | Memory/startup/serialization cost lớn hơn |

**Process isolation không phải security sandbox**; nó vẫn có quyền OS theo runner. Chọn mode dựa trên tool/classloader/memory requirements, không mặc định process isolation luôn nhanh.

### 13.1. Mẫu plugin task dùng Worker API

Đoạn sau là **task implementation minh họa viết bằng Kotlin trong binary/convention plugin**, không phải một build script độc lập có thể paste thay toàn bộ demo Java trước.

~~~kotlin
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.util.Locale
import javax.inject.Inject

import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.workers.WorkAction
import org.gradle.workers.WorkParameters
import org.gradle.workers.WorkerExecutor

abstract class UppercaseWork : WorkAction<UppercaseWork.Parameters> {
    interface Parameters : WorkParameters {
        val inputFile: RegularFileProperty
        val outputFile: RegularFileProperty
    }

    override fun execute() {
        val input = parameters.inputFile.get().asFile.toPath()
        val output = parameters.outputFile.get().asFile.toPath()
        Files.createDirectories(output.parent)

        val upper = Files.readString(
            input, StandardCharsets.UTF_8
        ).uppercase(Locale.ROOT)

        Files.writeString(
            output, upper, StandardCharsets.UTF_8
        )
    }
}

abstract class UppercaseBatch : DefaultTask() {
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sources: ConfigurableFileCollection

    @get:OutputDirectory
    abstract val destination: DirectoryProperty

    @get:Inject
    abstract val workerExecutor: WorkerExecutor

    @TaskAction
    fun process() {
        val queue = workerExecutor.noIsolation()

        sources.files.forEach { source ->
            queue.submit(UppercaseWork::class.java) { params ->
                params.inputFile.set(source)
                params.outputFile.set(
                    destination.file(source.name)
                )
            }
        }

        queue.await()
    }
}
~~~

Ở đây:

- `UppercaseBatch` là task cha có declared file inputs/output directory.
- `queue.submit` gửi typed parameters cho work actions.
- `queue.await` bảo đảm work complete trước khi task coi như hoàn tất.
- `max-workers` tham gia điều phối số Gradle work items có thể chạy.
- Worker API không tự sửa file/path ownership; mỗi action vẫn phải ghi vào output riêng.

**Lưu ý correctness:** `destination.file(source.name)` không xử lý trường hợp hai files ở thư mục khác nhau cùng basename, có thể gây output collision. Plugin production nên preserve relative paths hoặc validate uniqueness, rồi thêm tests cho deletion/rename/path normalization. Không dùng snippet này như file transformer production đã xử lý mọi edge case.

### 13.2. Process-isolated workers và heap

Một phương án khác khi tool cần JVM riêng:

~~~kotlin
val queue = workerExecutor.processIsolation {
    forkOptions.maxHeapSize = "512m"
}
~~~

Đây là **snippet thay thế** cho `noIsolation()` trong custom task có WorkerExecutor; cần implementation/classpath phù hợp với process isolation. Mỗi worker daemon JVM có memory/GC/startup overhead. Không cho rằng thay `noIsolation` thành `processIsolation` tự bảo đảm tăng tốc.

### 13.3. Đừng chia thành quá nhiều work items quá nhỏ

Nếu mỗi action chỉ viết vài bytes hoặc cộng hai số, overhead submit/serialization/classloading có thể vượt giá trị. Batch files hoặc dùng built-in Gradle `Copy`/`Sync` nếu tác vụ là copy đơn giản. Worker API có lợi khi mỗi đơn vị work **đủ nặng, thread-safe và độc lập**.

## 14. Shared Build Services: giới hạn đúng tài nguyên dùng chung

`--max-workers=1` sẽ khiến nhiều phần build không liên quan mất cơ hội song song. Nếu chỉ một API/license server/hardware test rig cho phép **một client tại một thời điểm**, dùng Shared Build Service để giới hạn tasks truy cập **đúng resource đó**.

### 14.1. Service implementation mẫu

Trong convention/binary plugin Kotlin:

~~~kotlin
import org.gradle.api.services.BuildService
import org.gradle.api.services.BuildServiceParameters

abstract class ExclusiveEndpoint :
    BuildService<BuildServiceParameters.None>,
    AutoCloseable {

    override fun close() {
        // Release resource owned by service, if any.
    }
}
~~~

Đăng ký:

~~~kotlin
val slot = gradle.sharedServices.registerIfAbsent(
    "endpointSlot",
    ExclusiveEndpoint::class.java
) {
    maxParallelUsages.set(1)
}
~~~

Kết nối task sử dụng resource:

~~~kotlin
tasks.register("callSharedEndpoint") {
    usesService(slot)
    doLast {
        logger.lifecycle("Using limited shared endpoint")
        // Actual authorized API work would be here.
    }
}
~~~

Các snippets này minh họa **API contract**, không thực hiện external network call. Để áp dụng cho nhiều modules, đặt service implementation trong **một convention plugin có class identity chung**, và bảo đảm các tasks dùng **cùng registered service** thay vì mỗi project tự định nghĩa class khác nhau rồi tưởng là cùng một slot.

### 14.2. maxParallelUsages và usesService

`maxParallelUsages.set(1)` nói Gradle không để hơn một task **được đăng ký sử dụng service ấy** chạy đồng thời. Khi task dùng service qua `@Internal` hoặc gián tiếp, `Task.usesService(slot)` giúp Gradle biết mối quan hệ; có thể dùng `@ServiceReference` task property đúng Gradle API.

**Bẫy:** chỉ register service không tự động làm mọi task bị giới hạn. Mỗi consumer task phải declare service usage, nếu không constraint không phát huy tác dụng.

### 14.3. Phạm vi Build Service không vượt mọi CI jobs

Shared Build Service chỉ điều phối tasks của invocation dùng chính service ấy. Nó **không** khóa:

- một Gradle invocation khác,
- một CI job khác,
- một Docker process do người khác mở,
- một remote database/service có clients từ nhiều machines.

Với tài nguyên global, cần CI concurrency group, external lease/distributed lock hoặc quota tại server. Không dùng `--max-workers=1` trong từng job rồi kết luận toàn cluster chỉ có một deployment.

## 15. Phân loại tài nguyên và cách giới hạn

| Tài nguyên | Biểu hiện tranh chấp | Biện pháp phù hợp |
| --- | --- | --- |
| CPU | CPU 100%, run queue dài | Hạn chế workers, tối ưu compile/algorithm |
| RAM | OOM, GC cao, swap | Giảm test forks/process workers, điều chỉnh heap |
| Disk I/O | build chậm, I/O wait | Giảm simultaneous writers, cache, SSD/runner |
| Temp directory | Hai tests ghi đè files | Per-test `@TempDir`, unique paths |
| Port TCP | “Address already in use” | Dynamic ports, service slot |
| DB schema | Data race, deadlocks, stale fixtures | Transaction/test data isolation |
| Docker daemon | Image tag overwritten, CPU/disk contention | Isolated builder/tags, CI limits |
| License server | Vượt license slots | BuildService/CI semaphore |
| API quota | HTTP 429 | Throttle, caching, backoff theo policy |
| Registry | Rate-limit, push overlap | Unique immutable tags/digests, release pipeline |

### 15.1. Mỗi output chỉ nên có một owner

Nếu `:a:generate` và `:b:generate` cùng ghi `build/generated/config.json`, đó là overlapping outputs. Việc tuần tự hóa chỉ che bớt race, không giải quyết task caching/ownership. Tách output directories hoặc tạo một producer của artifact đó rồi chia sẻ qua Provider/project dependency.

### 15.2. Retry không thay resource design

Thêm retries cho flaky tests do cùng port/DB không tạo isolation. Retry có thể làm CI xanh một cách ngẫu nhiên nhưng vẫn tốn tài nguyên, làm kết quả khó tin. Ưu tiên tách resource hoặc hạn chế concurrency đúng scope.

## 16. Kiểm thử có song song: cách tránh flaky tests

Tests thường PASS khi chạy một mình nhưng FAIL khi chạy `--parallel`, bật nhiều test forks hoặc JUnit method-level parallelism. Những nguyên nhân điển hình:

- Mutable static state bị tests ghi/đọc đồng thời.
- Hai JVMs cùng sử dụng cổng 8080.
- Các tests cùng ghi `/tmp/output.json`.
- DB fixture ID cố định bị xóa bởi test khác.
- Container/queue/topic có tên chung.
- Clock/random/network không được cô lập.
- Cleanup sau test fail bỏ lại state.
- Test assertions ngầm phụ thuộc thứ tự chạy.

**Phương án:** dùng `@TempDir`, dynamic ports, transaction isolation, per-test identifiers, fake external clients, deterministic input và cleanup robust. Nếu resource thật sự không thể share, giới hạn test fork/task service usage và ghi rõ lý do.

### 16.1. Một Test task có maxParallelForks=1 vẫn có thể tranh tài nguyên

Nếu module `:a` và `:b` mỗi module có một `Test` task, mỗi task đặt `maxParallelForks=1`, nhưng Gradle chạy **hai Test tasks** đồng thời, vẫn có hai JVMs. Nếu cùng dùng một DB schema cần serialize toàn bộ, hãy kết nối các Test tasks qua **shared BuildService/CI policy**, không chỉ set một fork mỗi task.

### 16.2. JUnit threads và Gradle forks khác phạm vi

JUnit Jupiter có cơ chế parallel execution của methods/classes bên trong một JVM. Gradle Test forks là nhiều JVM processes. Khi kết hợp, có thể có **nhiều JVM × nhiều framework threads**, gây CPU oversubscription dù `--max-workers` không đổi. Chỉ bật phối hợp sau khi tests có state isolation.

## 17. Lập ngân sách bộ nhớ cho CI

Giả sử một runner có 2 CPU quota và 4 GiB RAM (chỉ là ví dụ). Cấu hình khởi đầu cần kiểm chứng bằng thực tế có thể là:

~~~properties
org.gradle.parallel=true
org.gradle.workers.max=2
org.gradle.jvmargs=-Xmx1024m -Dfile.encoding=UTF-8
~~~

Với integration tests nặng:

~~~kotlin
tasks.withType<Test>().configureEach {
    maxParallelForks = 1
    maxHeapSize = "512m"
}
~~~

Đây **không phải một template an toàn chung** cho mọi dự án. Phải tính cả Gradle Daemon, test worker/native memory, compiler daemons, Docker, Node, OS caches, non-heap và các CI jobs khác.

### 17.1. Chỉ số cần đo

- Peak process RSS và cgroup memory.
- JVM heap/GC pauses của Gradle Daemon và test workers.
- Số worker/test processes thực sự chạy đồng thời.
- CPU run queue và CPU quota/throttling.
- Disk queue depth và I/O wait.
- API latency/rate-limit errors.
- Elapsed build time median/p95.
- Test fail rate khi tăng concurrency.

`--max-workers=4` có thể phù hợp desktop 16 cores/32 GiB RAM nhưng tệ trên container CI 2 cores/4 GiB. Không sao chép worker count giữa môi trường nếu chưa đo.

### 17.2. Dấu hiệu over-subscription

- OOMKilled/exit 137 trên môi trường Linux/container.
- Gradle Daemon disappeared unexpectedly.
- GC thrashing, memory swap, random timeouts.
- Nhiều forked test JVMs cùng peak RAM.
- Docker/buildpack processes cùng saturate CPU/disk.
- Build chậm **hơn** khi tăng workers.
- Các tests hoặc external API trả lỗi chỉ khi parallel.

Khi gặp, kiểm tra logs/metrics và giảm concurrency trước khi tăng heap vô hạn.

## 18. Đo hiệu năng: không so hai workload khác nhau

Một so sánh sai:

~~~text
Lần A: clean build, --no-parallel
Lần B: warm build, --parallel
Kết luận: parallel nhanh hơn 10 lần
~~~

Lần B có thể gần như toàn `UP-TO-DATE` hoặc `FROM-CACHE`. Điều đó không chứng minh tác động của parallelism.

### 18.1. Quy trình benchmark tương đối công bằng

1. Chọn chính xác task graph muốn đo, ví dụ `:cli:build` cùng các test modules hoặc root `build`.
2. Pin Gradle Wrapper, JDK/toolchain, dependency versions.
3. Ghi runner CPU quota, RAM, filesystem, network.
4. Đo **clean/cold** và **warm/incremental** riêng.
5. Đặt cùng `--max-workers` khi so bật/tắt `--parallel`.
6. Ghi Configuration Cache/Build Cache bật hay tắt ở cả hai lượt.
7. Lặp nhiều lần để giảm nhiễu, so median và p95.
8. Theo dõi peak RAM/GC/CPU/I/O và test correctness, không chỉ thời gian.

Ví dụ cờ CLI:

~~~bash
./gradlew build --no-parallel --max-workers=2 --no-configuration-cache --profile
./gradlew build --parallel --max-workers=2 --no-configuration-cache --profile
~~~

Các lệnh là **khung tham khảo**, không nên chạy ngay hai lượt trong cùng workspace rồi lấy chênh lệch làm kết luận vì cache state có thể đổi.

### 18.2. --profile và Build Scan

`--profile` tạo report hiệu năng (thường `build/reports/profile`) để xem configuration/task timing. Build Scan/Develocity có timeline sâu hơn về overlaps và critical path:

~~~bash
./gradlew build --parallel --max-workers=2 --scan
~~~

**Bảo mật:** Build Scan có thể gửi build metadata đến dịch vụ bên ngoài hoặc server của tổ chức; chỉ bật nếu policy chia sẻ dữ liệu cho phép. Nếu không, dùng local `--profile`, CI metrics và các công cụ nội bộ.

### 18.3. Đọc timeline đúng cách

Nếu có nhiều tasks bị UP-TO-DATE, ít khoảng công việc phải chạy; tăng workers không thể giảm nhiều. Nếu một task chiếm phần lớn critical path, nó là ưu tiên tối ưu. Nếu hai tasks overlap nhưng disk I/O wait tăng vọt, parallelism có thể làm tổng thời gian tệ hơn.

## 19. Critical path giới hạn mức tăng tốc

Một task graph minh họa:

~~~text
    +--> A (2s) --+
    |             |
    +--> B (2s) --+--> D (8s) --> Done
    |             |
    +--> C (2s) --+
~~~

A/B/C độc lập có thể overlap, nhưng D phải chờ đủ đầu vào và tự chạy 8 giây. Tăng workers không làm D ngắn lại nếu task D không chia nhỏ được hoặc không thay thuật toán. Đây là ý tưởng gần với **Amdahl's law**: phần tuần tự trên critical path hạn chế tổng speedup.

**Cải thiện có thể có:** giảm unnecessary dependencies, cải thiện compile avoidance, incremental tasks, cache, tìm bottleneck trong D hoặc dùng Worker API nếu D thực sự gồm nhiều work items độc lập. Không tạo module/task mới chỉ để “đẹp timeline” mà tăng coupling.

## 20. Gradle parallelism và Configuration Cache không giống Build Cache

| Cơ chế | Tối ưu phần nào? | Kết quả phổ biến |
| --- | --- | --- |
| `--parallel` | Song song task scheduling | Nhiều task actions cùng tiến triển |
| `--max-workers` | Giới hạn capacity | Kiểm soát mức concurrency |
| Worker API | Chia một task thành work items | Song song bên trong custom task |
| Configuration Cache | Tái sử dụng task graph/configuration | Giảm configuration time, có thể thay scheduling behavior |
| Build Cache | Khôi phục task outputs | Task `FROM-CACHE`, action không chạy |
| Incremental build | Tránh hoặc giảm work từ input changes | `UP-TO-DATE` hoặc xử lý phần thay đổi |
| Compile avoidance | Không recompile downstream khi API/ABI phù hợp | Ít JavaCompile work hơn |
| Dependency cache | Lưu dependency artifacts/metadata | Giảm network/download/resolution |

**Không dùng `--no-build-cache` để “tắt song song”**. Tương tự, `--no-configuration-cache` không tự làm tasks có cùng outputs an toàn. Mỗi cờ có đúng một phạm vi.

### 20.1. Isolated Projects và Tooling API

Gradle mới có Isolated Projects giúp giảm cross-project model coupling khi configuration; có yêu cầu compatibility riêng. Thay vì `subprojects { ... }` cấu hình chéo tùy tiện, ưu tiên convention plugins và project dependencies đúng.

Từ các bản Gradle 9.4+, `org.gradle.tooling.parallel` cho phép điều chỉnh song song của **Tooling API/IDE model actions** riêng:

~~~properties
org.gradle.parallel=true
org.gradle.tooling.parallel=false
~~~

Đây là phương án cho những build cần song song tasks nhưng muốn giới hạn IDE sync/tooling parallelism; **không bắt buộc** cho mọi dự án, và cần xác nhận Gradle Wrapper hỗ trợ property này.

## 21. Quyết định khi nào cần Worker API thay vì thêm subproject

| Đặc điểm | Hướng phù hợp |
| --- | --- |
| Nhiều subprojects độc lập đã có tasks rõ | `--parallel` và đúng task graph |
| Một task tạo nhiều independent artifacts nặng | Worker API |
| Một task chỉ copy files | Ưu tiên built-in `Copy`/`Sync` |
| Một task compile Java | Dùng `JavaCompile` và incremental compile |
| Nhiều tests trong một Test task | `maxParallelForks`, đúng test isolation |
| Một work item rất nhẹ | Batch work hoặc chạy tuần tự để tránh overhead |
| Một tool không thread-safe | Classloader/process isolation hoặc serialize usage |
| Work action dùng file output chung | Phải sửa output ownership trước khi song song |
| Một external API có rate limit | BuildService quota/CI-level throttle |
| Một service chung giữa nhiều CI jobs | Distributed lock/concurrency group |

**Nguyên tắc:** không viết custom parallel engine nếu Gradle built-in tasks hoặc tool đã có cơ chế incremental/cache chuẩn. Bảo trì custom WorkAction, isolation, parameters và lỗi concurrency có chi phí đáng kể.

## 22. Lỗi điển hình và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Bật `--parallel` mà logs tuần tự | Graph có dependencies hoặc chỉ 1 worker | Kiểm tra task graph và max-workers |
| Build chậm khi workers tăng | CPU/memory/I/O contention | Đo metrics, giảm cap |
| Gradle Daemon OOM | Heap/GC, nhiều processes | Kiểm tra daemon logs, RAM budget |
| CI OOMKilled | Tổng RSS vượt cgroup | Giảm forks/workers, đo peak RSS |
| Tests chỉ fail khi parallel | Ports, files, DB fixtures, global state | Unique resource/test isolation |
| `maxParallelForks=4` chỉ thấy 1 process | Không đủ classes/worker cap/graph | Xem `--info` và Test task model |
| Giới hạn Test.maxHeapSize nhưng vẫn OOM | Daemon/native/external process memory | Xem toàn bộ process tree |
| BuildService không serialize | Thiếu `usesService`/`@ServiceReference` | Nối cùng registered service |
| Hai CI jobs vẫn tranh DB | BuildService chỉ trong invocation | CI concurrency/distributed lock |
| Worker API output bị ghi đè | Hai inputs map cùng output path | Unique output/relative paths |
| Plugin crash với processIsolation | Classpath/serialization/heap | Kiểm tra Worker API contracts |
| Task cùng project chạy cạnh nhau bất ngờ | Configuration Cache scheduling | Không dựa vào project-local sequencing |
| `:cli:run` không thấy Greeter | Thiếu project dependency | `implementation(project(":messages"))` |
| `--no-parallel` nhưng tests vẫn overlap | Test forks/framework parallelism | Kiểm tra cả ba tầng |
| Test dùng chung port 8080 | Hardcode host resource | Dynamic port hoặc resource gate |
| Output cũ khiến tests PASS sai | Up-to-date/inputs sai | Kiểm tra inputs/outputs và task ownership |
| Network repo trả 429 | Quá nhiều requests/cache misses | Mirror, cache, quotas |
| Build Scan không được phép | Metadata ra ngoài policy | Dùng profile nội bộ |
| `--profile` báo task rất nhanh | UP-TO-DATE/FROM-CACHE | So work states |
| CI chậm hơn local | CPU quota, I/O, memory, JDK khác | So runner characteristics |

### 22.1. Checklist debug theo thứ tự

1. Xác nhận Gradle Wrapper/JDK/Configuration Cache modes.
2. Xem task graph `--dry-run` và dependencies.
3. Xác nhận `--parallel`/`--max-workers` thực tế.
4. Với Test tasks, kiểm tra `maxParallelForks` và `maxHeapSize`.
5. Nếu Worker API, kiểm tra number of work actions, isolation mode.
6. Nếu có external shared service, kiểm tra `usesService` và concurrency ngoài Gradle.
7. Xem CPU quota, cgroup memory, GC, I/O wait, network.
8. So cùng workload/cache states trước và sau tuning.
9. Kiểm chứng output content/tests/reports, không chỉ “BUILD SUCCESSFUL”.

## 23. Anti-patterns cần tránh

**A — Đặt `--max-workers=64` trên mọi máy.** Không phù hợp với runner thiếu RAM/CPU quota.

**B — Nhìn `--parallel` rồi cho rằng task dependencies không quan trọng.** Gradle vẫn tôn trọng data dependencies; thiếu dependency là lỗi build model.

**C — Tạo `Thread.sleep` trong production task để “đợi resource”.** Đây không phải synchronization tốt; dùng provider dependency hoặc resource coordination.

**D — Cho hai tasks ghi chung build output.** Overlapping outputs làm cache/incremental/concurrency không đáng tin.

**E — Dùng `mustRunAfter` để thay output provenance.** Nó chỉ ordering, không schedule producer.

**F — Tăng Test forks trong suite dùng shared database.** Cần transaction/fixture isolation hoặc shared service slot.

**G — Tưởng `--max-workers` giới hạn toàn bộ native process threads.** External tools có concurrency policy riêng.

**H — Đặt Gradle heap lớn rồi bỏ qua Test JVM memory.** Nhiều heap limits cộng lại có thể làm OOM.

**I — Bật cả JUnit method parallelism lẫn Gradle forks mà không isolation.** Nested concurrency gây race.

**J — Copy BuildService class/service registration vào mỗi module rồi gọi cùng tên.** Cần class identity và same registered service đúng contract.

**K — Bật processIsolation cho work items chỉ vài microseconds.** Isolation overhead có thể lớn hơn compute.

**L — So clean sequential với warm parallel build.** Kết luận benchmark sai vì lượng work khác.

**M — Retry flaky tests thay vì sửa contention.** Che lỗi resource ownership.

**N — Gắn `--scan` vào CI public không kiểm tra metadata policy.** Có thể lộ thông tin build.

**O — Coi Configuration Cache là chế độ “tasks luôn tuần tự trong project”.** Gradle mới có scheduling khác.

**P — Không đọc test reports mà chỉ xem task name UP-TO-DATE.** Phải xác nhận tests thực sự có và được chạy đúng gate.

## 24. Bài tập thực hành có đáp án

**Câu 1.** `--parallel` cho phép gì?  
**Đáp án:** chạy tasks đủ điều kiện đồng thời, đặc biệt giữa subprojects ở mode thông thường.

**Câu 2.** `--max-workers=2` có bảo đảm đúng hai tasks chạy mọi lúc?  
**Đáp án:** không, đó là giới hạn worker capacity.

**Câu 3.** `--max-workers=1` nhưng `--parallel` bật, hai simulated tasks có overlap không?  
**Đáp án:** không trong thí nghiệm, vì chỉ một worker slot.

**Câu 4.** `:cli` cần classes từ `:messages`. Bật parallel có thể bỏ dependency không?  
**Đáp án:** không; `implementation(project(":messages"))` vẫn cần.

**Câu 5.** Demo Java `:cli:run --args="Ada"` in gì?  
**Đáp án:** `Hello, Ada!`.

**Câu 6.** Java Main không truyền args in gì?  
**Đáp án:** `Hello, Gradle!`.

**Câu 7.** Lệnh javac/java có kiểm thử task scheduling Gradle không?  
**Đáp án:** không, chỉ Java code/classpath.

**Câu 8.** Hai tasks độc lập nhưng cùng ghi một file. Có nên bật parallel không?  
**Đáp án:** phải sửa output ownership trước.

**Câu 9.** `mustRunAfter` có tự thêm task producer vào graph không?  
**Đáp án:** không.

**Câu 10.** `maxParallelForks` đặt ở đâu?  
**Đáp án:** Gradle `Test` task.

**Câu 11.** `maxParallelForks=2` có nghĩa hai test methods trong một class luôn ở hai JVMs?  
**Đáp án:** không; cần đủ test classes và framework có rules riêng.

**Câu 12.** `maxParallelForks=4` có hợp lệ với `--max-workers=2`?  
**Đáp án:** không; Gradle Test API quy định không vượt max-workers.

**Câu 13.** `Test.maxHeapSize="512m"` có giới hạn heap Gradle Daemon không?  
**Đáp án:** không; mỗi test process có heap riêng.

**Câu 14.** `org.gradle.jvmargs=-Xmx1024m` tự giới hạn RAM Docker không?  
**Đáp án:** không.

**Câu 15.** Khi tests dùng chung port 8080, nên làm gì?  
**Đáp án:** dynamic ports hoặc serialize đúng resource, không retry vô hạn.

**Câu 16.** Worker API dùng để làm gì?  
**Đáp án:** chia một custom task thành các work actions.

**Câu 17.** `processIsolation` có free memory overhead không?  
**Đáp án:** không; worker JVMs tốn startup/heap/native memory.

**Câu 18.** Vì sao `noIsolation` cần thread safety?  
**Đáp án:** work actions có thể dùng chung JVM/state, phải tránh race.

**Câu 19.** Khi nào dùng `BuildService.maxParallelUsages=1`?  
**Đáp án:** một resource hạn chế trong build chỉ cho một consumer task tại thời điểm.

**Câu 20.** Chỉ register BuildService mà không `usesService` có đủ không?  
**Đáp án:** không nhất thiết; phải khai báo task usage phù hợp.

**Câu 21.** BuildService có bảo vệ resource khỏi hai CI jobs khác nhau không?  
**Đáp án:** không; cần CI/global locking.

**Câu 22.** Vì sao WorkerAction dùng `destination.file(source.name)` có thể sai?  
**Đáp án:** trùng basename từ hai thư mục sẽ map cùng output.

**Câu 23.** Một build chỉ có một task trên critical path, tăng workers 2→16 có chắc nhanh không?  
**Đáp án:** không, thiếu công việc độc lập.

**Câu 24.** Khi worker cap tăng và build chậm hơn, nguyên nhân nào cần xem?  
**Đáp án:** CPU/RAM/I-O contention, GC, tests, external quotas.

**Câu 25.** `--configuration-cache` có cùng nghĩa `--parallel` không?  
**Đáp án:** không; Configuration Cache tối ưu configuration và trên Gradle mới có thể ảnh hưởng scheduling.

**Câu 26.** `--no-build-cache` có tắt song song tasks không?  
**Đáp án:** không.

**Câu 27.** `--profile` dùng làm gì?  
**Đáp án:** tạo báo cáo thời gian build/tasks/configuration, không tự tăng tốc.

**Câu 28.** Có nên so clean sequential với warm parallel build để quyết định không?  
**Đáp án:** không, phải giữ workload/cache state so sánh được.

**Câu 29.** `Thread.sleep(900L)` trong demo có chứng minh CPU speedup không?  
**Đáp án:** không, chỉ minh họa overlapping schedule.

**Câu 30.** `maxParallelForks=1` trong hai modules có chắc chỉ một test JVM toàn build không?  
**Đáp án:** không; hai Test tasks độc lập vẫn có thể chạy đồng thời.

**Câu 31.** Gradle mới có thể chạy tasks cùng project song song không?  
**Đáp án:** có trong một số modes như Configuration Cache, nên không dựa vào sequential assumptions.

**Câu 32.** `org.gradle.tooling.parallel=false` khác `org.gradle.parallel=false` ở đâu?  
**Đáp án:** cái đầu kiểm soát Tooling API parallelism ở Gradle hỗ trợ, cái sau điều khiển task parallelism.

## 25. Checklist điều chỉnh parallelism trước khi áp dụng trên CI

- [ ] Task graph có branches độc lập thật hay chỉ một critical path dài?
- [ ] `--parallel` và `--max-workers` được chọn dựa trên CPU quota, RAM thực?
- [ ] Không nhầm worker slots với số CPU cores hoặc JVM threads?
- [ ] Project dependencies và task output providers được mô hình hóa đúng?
- [ ] Không có overlapping outputs hoặc shared temp files?
- [ ] `Test.maxParallelForks` không vượt worker limit?
- [ ] Test JVM heap được tính riêng với Gradle Daemon heap?
- [ ] `forkEvery` chỉ thay khi có lý do process isolation?
- [ ] JUnit method-level parallelism được quản lý riêng?
- [ ] Tests có isolated ports/data/filesystem?
- [ ] Các tasks cùng dùng license/API/DB có shared BuildService policy?
- [ ] Các tasks cần BuildService đều declare usage?
- [ ] Có CI-level limit nếu nhiều invocations dùng một môi trường?
- [ ] Worker API chỉ dùng khi work items độc lập, đủ nặng?
- [ ] Isolation mode phù hợp cost/GC/classloading?
- [ ] Worker actions không viết đè file cùng basename?
- [ ] Gradle Daemon, tests, compiler workers và external tools có memory budget?
- [ ] Runner CPU quota/cgroup memory được xác định?
- [ ] Đã theo dõi GC, OOM, disk I/O, network/rate-limit?
- [ ] Benchmark clean và incremental states riêng, so nhiều lần?
- [ ] Có profile/timeline và critical path trước/sau?
- [ ] Bảo mật dữ liệu Build Scan/CI logs đã được xem xét?
- [ ] Không lạm dụng retries để che race conditions?
- [ ] Configuration Cache/Tooling API settings khớp Gradle Wrapper version?
- [ ] Build vẫn PASS từ clean checkout và tests/reports đúng kết quả?

## 26. Tài liệu chính thức

- [Gradle — Improve Build Performance](https://docs.gradle.org/current/userguide/performance.html): parallel execution, critical path, tests, cache và profiling.
- [Gradle — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): `org.gradle.parallel`, `org.gradle.workers.max`, `org.gradle.jvmargs`.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/gradle_command_line.html): `--parallel`, `--max-workers`, `--profile`, `--scan`, Configuration Cache flags.
- [Gradle — Developing Parallel Tasks](https://docs.gradle.org/current/userguide/worker_api.html): `WorkerExecutor`, work actions và isolation modes.
- [Gradle — Using Shared Build Services](https://docs.gradle.org/current/userguide/build_services.html): `maxParallelUsages`, `usesService`, `@ServiceReference` và service lifecycle.
- [Gradle — Test task Javadoc](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/Test.html): `maxParallelForks`, `maxHeapSize`, `forkEvery`.
- [Gradle — Testing Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): test execution, forked workers và test filtering.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): project dependency graph.
- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html): `dependsOn`, `mustRunAfter` và ordering.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration state caching và parallel execution.
- [Gradle — Configuration on Demand](https://docs.gradle.org/current/userguide/configuration_on_demand.html): decoupled projects, parallel execution.
- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): inputs/outputs và UP-TO-DATE.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): cacheable outputs và FROM-CACHE.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): dependency scope và compile avoidance.

**Kết luận:** Song song chỉ hiệu quả khi **có các đơn vị công việc độc lập và không tranh tài nguyên quá mức**. `--parallel` cho phép Gradle chạy các tasks có thể overlap; `--max-workers` giữ concurrency phù hợp runner. `Test.maxParallelForks`, Worker API và framework-level parallelism là các lớp riêng cần điều chỉnh; `BuildService.maxParallelUsages` giúp giới hạn tài nguyên chung đúng phạm vi một invocation. Hãy bảo vệ task dependencies, output ownership và test isolation, đo bằng cùng workload/cache state và ưu tiên critical path. **Một build nhanh hơn nhưng dễ OOM hoặc chạy sai không phải một tối ưu thành công.**