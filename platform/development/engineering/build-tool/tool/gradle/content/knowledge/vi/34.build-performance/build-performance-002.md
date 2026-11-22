# Gradle Daemon, tái sử dụng JVM và cấu hình bộ nhớ

## 1. Vấn đề: tại sao lần build thứ hai thường nhanh hơn?

Một lập trình viên chạy `./gradlew build` lần đầu, phải chờ Gradle khởi động, nạp plugin classes, phân tích build scripts và biên dịch. Lần thứ hai, dù không thay đổi code, build hoàn thành nhanh hơn. Một phần lợi ích có thể đến từ **Gradle Daemon**: JVM process sống lâu mà Gradle tái sử dụng qua nhiều build invocations, thay vì khởi động build engine từ đầu cho mỗi câu lệnh.

Nhưng chuyện gì xảy ra khi:

- Bạn tăng `org.gradle.jvmargs` từ `-Xmx768m` lên `-Xmx2g` và nhìn thấy nhiều Gradle daemons?
- Bạn có `-Xmx4g` cho Gradle nhưng `test` vẫn lỗi `Java heap space`?
- IDE và terminal cùng build một repository mà không reuse cùng daemon?
- CI báo `Gradle build daemon disappeared unexpectedly`?
- Task `run` của ứng dụng dùng Java 17 và heap 256 MiB, trong khi Gradle daemon lại chạy JDK 21 với heap 2 GiB?
- Build quá chậm nhưng tăng heap không cải thiện, thậm chí khiến container bị `OOMKilled`?

Lý do chung là **Daemon reuse, JVM selection, Java heap, process isolation và task caching là những vấn đề liên quan nhưng không đồng nhất**.

Bài Knowledge thuộc chủ đề **Hiệu năng build** của module **Build Tool Gradle**. Mục tiêu là giải thích cơ chế Gradle Daemon, thiết lập JVM/memory đúng phạm vi và đo lường hiệu năng thực tế bằng một project Java 17 có thể chạy được.

### 1.1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **Gradle Client JVM**, **Gradle Daemon JVM**, project Java toolchain, forked Test JVM, JavaExec, compiler worker và Kotlin daemon.
2. Mô tả vòng đời daemon: khởi động, IDLE, BUSY, tái sử dụng và dừng.
3. Hiểu điều kiện daemon compatible: Gradle version, Java installation/JVM criteria, JVM startup arguments và trạng thái IDLE.
4. Dùng `--status`, `--stop`, `--no-daemon`, `--info`, `jps` và `jcmd` đúng mục đích.
5. Thiết lập `org.gradle.jvmargs`, `-Xmx`, `-Xms`, `MaxMetaspaceSize`, heap dump và idle timeout.
6. Hiểu sự khác nhau giữa `JAVA_HOME`, `org.gradle.java.home`, Daemon JVM criteria và `java.toolchain`.
7. Tuning `Test.maxHeapSize`, `Test.maxParallelForks`, `JavaExec.maxHeapSize`, forked JavaCompile và Kotlin compiler JVM.
8. Ước lượng tổng memory footprint dưới CI/container limits, tránh overcommit do quá nhiều forks.
9. Đọc logs/OS metrics để phân biệt Java heap OOM, Metaspace OOM và OS OOM kill.
10. Quan sát daemon PID, Java version và heap bằng typed Gradle task, rồi chạy application JVM riêng bằng Java 17.
11. So benchmark cold/warm builds mà không nhầm Daemon với Build Cache/Configuration Cache.
12. Thiết kế chính sách JVM/Gradle Wrapper/CI phù hợp và tránh thao tác làm mất JVM warm-up.

## 2. Daemon hoạt động như thế nào?

### 2.1. Kiến trúc client và daemon

Một Gradle invocation thường có client process ngắn hạn và daemon process dài hạn:

~~~text
Terminal, IDE hoặc CI
        |
        | ./gradlew build
        v
Gradle Client JVM
        |
        | request: build, options, environment
        v
Gradle Daemon JVM
        |
        +--> settings, project configuration
        +--> plugin/build logic, task graph
        +--> task execution coordination
        |
        +--> javac / JavaCompile workers khi cần
        +--> Test JVM worker(s)
        +--> JavaExec application JVM
        +--> Kotlin compiler daemon khi dùng KGP
~~~

- **Client** khởi động theo lệnh, chuyển yêu cầu tới daemon, chuyển log/output về terminal và trả exit code.
- **Daemon** chạy build engine, xử lý Gradle scripts và phối hợp tasks. Khi build xong, nó có thể tiếp tục tồn tại ở trạng thái IDLE.
- **Các JVMs phụ** chỉ xuất hiện khi tasks/plugins cần chúng. Không phải mọi build đều chạy tất cả các process trong sơ đồ.
- Các process có thể chạy bằng **các JDK versions và heap limits khác nhau**.

### 2.2. Vì sao Gradle Daemon tăng tốc?

Các lợi ích chính:

- Tránh một lần khởi động Gradle build JVM/engine cho mỗi invocation.
- Giữ nhiều Gradle/plugin classes đã được load.
- JVM JIT compiler có thể tối ưu những đoạn code Gradle thường chạy.
- Tận dụng một số in-memory caches như file snapshots/hash data.
- Phối hợp với file system watching để giảm công việc quan sát input files.

Điều này không có nghĩa Gradle “không chạy configuration nữa”. Muốn tái sử dụng configuration/task graph, cần xét **Configuration Cache**. Muốn phục hồi outputs đã build, xét **Build Cache**. Daemon là nền tảng JVM/process reuse, không thay cả hai.

### 2.3. Daemon có được bật mặc định?

Trên Gradle hiện đại, Daemon được bật mặc định; Gradle 3.0 đã chuyển sang mặc định bật. Có thể viết:

~~~properties
org.gradle.daemon=true
~~~

trong `gradle.properties`, nhưng việc thêm dòng này vào project vốn đã bật Daemon không tự tạo speedup mới.

### 2.4. Daemon tự dừng khi nào?

Một daemon không sống vĩnh viễn. Gradle có thể dừng khi:

- Idle lâu hơn timeout quy định.
- Hệ thống đang gặp memory pressure.
- User gọi `gradle --stop`.
- Daemon được restart sau khi phát hiện dấu hiệu memory leak/heap pressure.
- JVM gặp crash, OOM hoặc bị OS/container/user kill.
- CI agent hoặc container bị phá hủy.

Mặc định Daemon tự dừng sau **ba giờ idle** trên tài liệu Gradle hiện hành. Có property điều chỉnh timeout bằng milliseconds (mục 5).

## 3. Điều kiện để tái sử dụng cùng Gradle Daemon

### 3.1. Không phải cứ cùng repository là reuse

Gradle chỉ chọn daemon khi phù hợp với yêu cầu build, chủ yếu gồm:

| Yếu tố | Vì sao quan trọng? |
| --- | --- |
| Gradle distribution/version | Daemon Gradle 8.x không serve build Gradle 9.x |
| Java home/version/vendor/criteria | JVM runtime phải đáp ứng yêu cầu build |
| Immutable JVM arguments | `-Xmx`, `-Xms`, JVM properties cần phù hợp |
| Requested environment | IDE Tooling API/CLI có thể yêu cầu JVM khác |
| Trạng thái daemon | Daemon đang BUSY không thể tự do nhận cùng request |
| Version-specific compatibility policy | Gradle có rules riêng cho việc reuse |

Vì `-Xmx` là giới hạn JVM tại startup, một daemon khởi động với `-Xmx768m` không thể được sử dụng như daemon mới yêu cầu `-Xmx2g`. Gradle thường tạo một daemon khác.

### 3.2. Ví dụ có nhiều daemon nhưng không lỗi

~~~text
PID 10001: Gradle 9.x, JDK 17, -Xmx768m, IDLE
PID 10002: Gradle 9.x, JDK 17, -Xmx2g,   IDLE
PID 10003: Gradle 9.x, JDK 21, -Xmx2g,   IDLE
PID 10004: Gradle 8.x, JDK 17, -Xmx2g,   IDLE
~~~

Đây là **tình huống mô phỏng**, không phải output từ `gradle --status`. Nhiều JVM PIDs có thể do Gradle versions, Java versions và JVM flags khác nhau — **không tự chứng minh memory leak**.

### 3.3. Những JVM attributes có thể ảnh hưởng compatibility

Các JVM settings như:

~~~text
-Xmx2048m
-Xms256m
-Dfile.encoding=UTF-8
-Duser.language=en
-Duser.country=US
~~~

có thể quyết định khả năng reuse nếu Gradle phải giữ các immutable settings tương thích. Một môi trường IDE dùng Java home khác terminal, hoặc file `gradle.properties` bị override ở user home, cũng có thể tạo daemon khác.

### 3.4. Daemon đang BUSY

Nếu bạn chạy hai build invocations đồng thời, một daemon đang xử lý build A có thể không sẵn sàng phục vụ B. Gradle có thể khởi động daemon khác, khiến **peak RAM tăng**. Không chỉ nhìn cấu hình heap một daemon rồi kết luận host đủ RAM cho nhiều jobs chạy song song.

### 3.5. Giữ cấu hình ổn định để tăng reuse

- Pin Gradle version bằng Wrapper.
- Chọn một policy rõ ràng cho Gradle runtime JDK.
- Giữ `org.gradle.jvmargs` ổn định giữa IDE/terminal/CI khi hợp lý.
- Tránh thay đổi JVM args tùy tiện trong từng lệnh.
- Giảm số build invocations đồng thời nếu tài nguyên giới hạn.
- Đừng cưỡng ép các project có compatibility requirements khác nhau dùng cùng Gradle/JDK bằng mọi giá.

## 4. Các lệnh quản lý Daemon

### 4.1. Xem trạng thái

~~~bash
gradle --status
~~~

Với Wrapper:

~~~bash
./gradlew --status
~~~

`--status` cho PID, trạng thái như IDLE/BUSY và Gradle version. **Chỉ các daemons của cùng Gradle version** đang chạy lệnh đó mới được liệt kê; đây không phải công cụ nhìn mọi JVM trên hệ thống.

### 4.2. Dừng daemon khi cần

~~~bash
gradle --stop
~~~

Hoặc:

~~~bash
./gradlew --stop
~~~

`--stop` dừng daemons do **cùng Gradle version** tạo ra. Nó không đóng toàn bộ JVM của IDE, Test workers hay mọi version Gradle khác.

Dùng khi muốn reset daemon state, xử lý lỗi kết nối hoặc dọn JVM settings cũ. **Không** thêm `--stop` vào cuối mọi local build: bạn sẽ đánh mất startup/classloading/JIT warm-up benefits.

### 4.3. Bật/tắt daemon cho một invocation

~~~bash
gradle build --daemon
gradle build --no-daemon
~~~

Trên Gradle hiện đại, `--daemon` gần như xác nhận default. `--no-daemon` tắt reuse daemon lâu sống trong invocation, nhưng **vẫn có thể tạo single-use daemon** để đáp ứng JVM settings của build. JVM dùng một lần đó sẽ kết thúc khi build hoàn tất.

### 4.4. Vì sao --no-daemon vẫn tạo process mới?

Nếu client JVM args không khớp với yêu cầu build VM, Gradle có thể fork một **single-use Daemon** rồi dừng sau build. Khi client và build JVM settings tương thích, Gradle có thể thực hiện build trong client JVM.

Do đó:

~~~bash
gradle help --no-daemon --info
~~~

có thể xuất hiện log về single-use daemon; đó không tự động là lỗi hay bug. Đừng dùng sự tồn tại của JVM process làm bằng chứng flag `--no-daemon` bị bỏ qua.

### 4.5. JDK process tools

Nếu JDK có sẵn:

~~~bash
jps -lv
~~~

Sẽ có JVM processes có tên/main class liên quan `GradleDaemon` khi Daemon đang sống, cùng các Test/Kotlin/tool JVMs có thể đang chạy. Với một PID thật của daemon, có thể dùng:

~~~bash
jcmd 12345 VM.flags
jcmd 12345 GC.heap_info
jcmd 12345 Thread.print
~~~

`12345` là PID ví dụ. Bạn phải thay bằng PID thuộc quyền quản trị; `jcmd` có thể bị hạn chế bởi permissions, container isolation hoặc JVM attach settings.

### 4.6. Daemon logs

Gradle Daemon logs thường ở:

~~~text
~/.gradle/daemon/<gradle-version>/daemon-<pid>.out.log
~~~

Nếu cấu hình `GRADLE_USER_HOME` riêng, log nằm trong user home tương ứng. Trên Windows mặc định thường nằm dưới:

~~~text
%USERPROFILE%\.gradle\daemon\
~~~

Logs giúp xác định JVM startup flags, PID, connection errors, OOM/crash hints. Không chia sẻ nguyên logs/heap dumps ra bên ngoài khi chứa đường source, biến môi trường hoặc credentials.

## 5. Idle timeout và monitoring

### 5.1. Ba giờ idle mặc định

Property:

~~~properties
org.gradle.daemon.idletimeout=10800000
~~~

là 10.800.000 **milliseconds = ba giờ**. Có thể dùng timeout khác theo hạ tầng, nhưng giảm xuống vài giây trên máy developer khiến Daemon liên tục restart và dễ chậm hơn.

### 5.2. Memory pressure

Gradle có thể dừng một daemon trong điều kiện available system memory thấp. Trong các bản Gradle hiện đại, còn có cơ chế theo dõi heap/memory leak để restart daemon sau build khi cần. Điều này giải thích vì sao PID sau một loạt builds có thể đổi dù repo và JVM args không đổi.

Không tắt monitoring như một tối ưu mặc định. Nếu Daemon cứ restart, đọc logs/heap data để tìm nguyên nhân thay vì ép giữ một PID bằng mọi giá.

### 5.3. File-system watching

Daemon có thể hưởng lợi từ filesystem watching trên platforms được hỗ trợ. Nó giúp Gradle tận dụng thông tin file changes qua builds. Có thể chẩn đoán qua:

~~~bash
gradle build --info
gradle build --watch-fs
gradle build --no-watch-fs
~~~

Các command cuối là toggles, không phải yêu cầu chạy cả ba. File watching **khác** `--continuous` (tự chạy lại task khi files thay đổi) và khác Build Cache/Configuration Cache.

## 6. Cấu hình JVM heap bằng org.gradle.jvmargs

### 6.1. Giá trị mặc định

Theo tài liệu Gradle hiện hành, JVM chạy build thường có default JVM args:

~~~properties
org.gradle.jvmargs=-Xmx512m -XX:MaxMetaspaceSize=384m
~~~

512 MiB heap thường đủ cho build nhỏ và vừa. Với multi-project rất lớn/plugins nặng, việc tăng heap có thể giảm GC pressure và OOM, nhưng phải đo trước.

### 6.2. Heap, -Xms và -Xmx

- `-Xmx`: giới hạn **tối đa** cho Java object heap.
- `-Xms`: heap **ban đầu** khi JVM start.
- Dùng `m` và `g` để chỉ memory units theo JVM syntax.
- `-Xmx2g` không có nghĩa JVM lập tức sử dụng đúng 2 GiB physical RAM.
- `-Xmx` **không phải giới hạn tổng RSS** của process.

Ví dụ:

~~~properties
org.gradle.jvmargs=-Xms256m -Xmx2g
~~~

Đặt `-Xms` quá cao cho nhiều idle daemons có thể làm tăng memory footprint; không cần chỉnh cả hai nếu workload không yêu cầu.

### 6.3. Metaspace khác Java heap

`Metaspace` chứa class metadata của JVM, thường dùng native memory bên ngoài Java object heap. Java process còn dùng Code Cache, thread stacks, direct buffers, mapped files và native allocations.

Vì vậy:

~~~properties
org.gradle.jvmargs=-Xmx2g -XX:MaxMetaspaceSize=512m
~~~

không có nghĩa tổng process memory chỉ tối đa 2,5 GiB. Những memory areas khác và OS overhead vẫn tồn tại.

Nếu gặp:

~~~text
java.lang.OutOfMemoryError: Metaspace
~~~

cần xem classloaders/plugin behavior và metaspace limit của đúng JVM, **không** chỉ tăng heap `-Xmx`.

### 6.4. Một profile để thử nghiệm

Trong root `gradle.properties`:

~~~properties
org.gradle.daemon=true
org.gradle.jvmargs=-Xmx1536m -XX:MaxMetaspaceSize=512m -Dfile.encoding=UTF-8
~~~

Ý nghĩa:

- Heap tối đa cho **Gradle build VM** khoảng 1,5 GiB.
- Metaspace ceiling 512 MiB.
- Default encoding UTF-8 khi dùng runtime/JVM phù hợp.
- Daemon được phép sống lâu/tái sử dụng.

Đây **không phải** preset tối ưu cho mọi project/CI; nên giữ riêng số liệu benchmark và memory monitoring để điều chỉnh.

### 6.5. JAVA_OPTS không thay org.gradle.jvmargs

| Cơ chế | JVM/process chủ yếu |
| --- | --- |
| `JAVA_OPTS` | Gradle **client** do launcher script khởi động |
| `org.gradle.jvmargs` | Gradle **build JVM**, thường là Daemon |
| `Test.maxHeapSize` | Mỗi forked Test JVM |
| `JavaExec.maxHeapSize` | JVM do `JavaExec`/application `run` khởi chạy |
| `JavaCompile.options.forkOptions.memoryMaximumSize` | Compiler process nếu dùng fork |
| `kotlin.daemon.jvmargs` | Kotlin compiler daemon khi có Kotlin Gradle Plugin |

Đặt `JAVA_OPTS="-Xmx8g"` rồi hy vọng tất cả Gradle Test workers có heap 8 GiB là không đúng. Tương tự, tăng Gradle daemon heap không tự nâng max heap của một application server chạy bằng `JavaExec`.

### 6.6. File gradle.properties và phạm vi áp dụng

Có thể đặt Gradle JVM settings tại:

- Root project `gradle.properties` cho policy repo.
- `GRADLE_USER_HOME/gradle.properties` cho cấu hình cá nhân/agent.
- Các lớp Gradle properties hoặc command-line system properties thích hợp.
- IDE/Tooling API options trong environment phù hợp.

Nếu có các settings trùng khóa, cần kiểm **property precedence** trên Gradle version đang dùng. Không đặt tokens/passwords trực tiếp trong `org.gradle.jvmargs`: JVM flags có thể xuất hiện trong process listing và logs.

### 6.7. Heap dump khi OOM

Để điều tra heap:

~~~properties
org.gradle.jvmargs=-Xmx2g -XX:MaxMetaspaceSize=512m -XX:+HeapDumpOnOutOfMemoryError
~~~

Heap dump có thể lớn và chứa strings/secrets. Hãy lưu trong môi trường được bảo vệ; tránh upload công khai. Có thể thêm `-XX:HeapDumpPath=...` trỏ vị trí ghi được theo môi trường của bạn, nhưng không commit đường tuyệt đối máy cá nhân vào repo chung.

## 7. Chọn JVM: JAVA_HOME, org.gradle.java.home và Daemon criteria

### 7.1. Ba Java versions cần tách bạch

| Java version | Chọn bằng | Ảnh hưởng tới |
| --- | --- | --- |
| Client JVM | `JAVA_HOME` hoặc `java` trên PATH/IDE launcher | JVM khởi chạy Gradle command |
| Daemon JVM | Daemon criteria, `org.gradle.java.home`, Tooling API hoặc client default | Chạy Gradle engine và build logic |
| Project toolchain | `java.toolchain`/task JavaLauncher/JavaCompiler | Compile/test/run source project |
| Compile target | `options.release` | Java language/API level và bytecode |

Một project có thể build Java 17 binaries bằng Java 17 toolchain trong khi Daemon chạy JDK 21. Ngược lại, Gradle release có minimum JVM requirement riêng; không thể dùng JDK quá cũ chạy Gradle chỉ vì source target Java 8.

### 7.2. Kiểm launcher/JVM hiện tại

Linux/macOS:

~~~bash
echo "$JAVA_HOME"
java -version
gradle --version
~~~

PowerShell:

~~~powershell
$env:JAVA_HOME
java -version
gradle --version
~~~

Đọc cả Wrapper version/IDE Gradle JVM khi so terminal và IDE. Với Daemon JVM criteria riêng, `JAVA_HOME` có thể không quyết định Daemon JDK; xem criteria và task inspection.

### 7.3. org.gradle.java.home

Có thể chọn JVM cho Gradle Daemon bằng property như:

~~~properties
org.gradle.java.home=/opt/jdks/jdk-17
~~~

**Đây chỉ là đường dẫn ví dụ của Unix**. Đặt absolute JDK path trong repo chung thường không portable qua Windows/macOS/Linux. Hợp lý hơn khi CI image có JDK location được kiểm soát hoặc thiết lập qua user/CI properties.

### 7.4. Daemon JVM criteria: Gradle 8.8+

Gradle giới thiệu `updateDaemonJvm` từ Gradle 8.8, tạo criteria file:

~~~text
gradle/gradle-daemon-jvm.properties
~~~

Với Wrapper đã có và Gradle hỗ trợ:

~~~bash
./gradlew updateDaemonJvm --jvm-version=17
~~~

Có thể chọn vendor:

~~~bash
./gradlew updateDaemonJvm --jvm-version=17 --jvm-vendor=adoptium
~~~

Trong generated file có version criterion tương tự:

~~~properties
toolchainVersion=17
~~~

File thật có thể chứa vendor và các platform-specific `toolchainUrl...` được sinh từ configured toolchain download repositories/URLs. **Không tự điền URL giả** để tưởng đã cấu hình provisioning.

Khi criteria file hợp lệ, nó có precedence trước `JAVA_HOME` và `org.gradle.java.home` để chọn **Daemon JVM**. Có thể commit criteria file để developer/CI áp cùng JVM requirement. `updateDaemonJvm` có thể cần toolchain download repository configured; nếu gặp lỗi thiếu resolver, làm theo docs đúng Gradle version.

### 7.5. Java toolchain cho project khác Daemon JDK

Trong `build.gradle.kts`:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

`java.toolchain` chọn tools dùng compile/test/runtime cho source. `options.release` giúp compiler tạo binary/API target tương thích Java 17. Không có dòng nào trên tự đổi Gradle Daemon heap.

### 7.6. Kiểm version compatibility

Thay đổi JDK/Gradle Wrapper phải tuân [Gradle compatibility matrix](https://docs.gradle.org/current/userguide/compatibility.html). Nếu Gradle không chạy trên JDK yêu cầu, daemon không start; tăng `-Xmx` không giải quyết lỗi unsupported Java runtime.

## 8. Các JVM khác cũng dùng bộ nhớ

Một build đa module có thể có:

~~~text
Gradle Client
   |
   +-- Gradle Daemon (-Xmx2g)
          |
          +-- Test JVM #1 (-Xmx768m)
          +-- Test JVM #2 (-Xmx768m)
          +-- Java compiler fork/worker
          +-- Kotlin compiler daemon (nếu KGP)
          +-- JavaExec application JVM
          +-- native tools / annotation processors
~~~

Sơ đồ mô phỏng, số lượng thật phụ thuộc tasks và cách plugin thực thi. `-Xmx2g` của Gradle daemon không cấp 2 GiB chung cho toàn bộ process tree.

### 8.1. Forked Test JVM

Gradle `Test` tasks mặc định chạy tests trong JVM khác Gradle build JVM. Với Kotlin DSL:

~~~kotlin
import org.gradle.api.tasks.testing.Test

tasks.withType<Test>().configureEach {
    maxHeapSize = "768m"
    maxParallelForks = 2
}
~~~

- `maxHeapSize` là heap ceiling của **mỗi test process**.
- `maxParallelForks=2` cho phép tối đa hai test fork workers đồng thời **trong một Test task** khi đủ workload.
- Hai modules cùng chạy tests song song có thể sinh nhiều Test JVMs hơn nữa.
- JUnit framework còn có cơ chế parallel test methods riêng; đừng đồng nhất với Gradle `maxParallelForks`.

### 8.2. JavaExec / application run

Application plugin tạo task `run` kiểu `JavaExec`, khởi JVM riêng:

~~~kotlin
import org.gradle.api.tasks.JavaExec

tasks.named<JavaExec>("run") {
    maxHeapSize = "512m"
    systemProperty("app.mode", "development")
}
~~~

Đây là snippet cho project **đã apply `application` plugin**; `run.maxHeapSize` khác `org.gradle.jvmargs`.

### 8.3. Forked JavaCompile

`JavaCompile` có chế độ fork compiler process:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

tasks.withType<JavaCompile>().configureEach {
    options.fork = true
    options.forkOptions.memoryMaximumSize = "1g"
}
~~~

`memoryMaximumSize` chỉ có hiệu lực khi `options.fork = true`. Đừng tự bật fork cho mọi module rồi kỳ vọng chắc chắn build nhanh hơn: JVM startup/worker overhead và memory pressure có thể tăng. Số JVM compiler thực tế phụ thuộc implementation Gradle/toolchain/plugin.

### 8.4. Kotlin compiler daemon

Dự án có Kotlin Gradle Plugin có thể sử dụng **Kotlin compiler daemon** với memory riêng:

~~~properties
kotlin.daemon.jvmargs=-Xmx1024m
~~~

Theo Kotlin documentation, compiler daemon có thể kế thừa một tập JVM arguments của Gradle daemon (như `-Xmx`) khi không override. Vì vậy tăng `org.gradle.jvmargs` đôi khi còn làm Kotlin daemon có heap ceiling cao hơn. Đây là **hai processes**, không phải một chung object heap.

Không thêm property này vào Java-only project nếu không sử dụng Kotlin Gradle Plugin.

### 8.5. Worker API và parallel tasks

~~~properties
org.gradle.parallel=true
org.gradle.workers.max=4
~~~

Các properties ảnh hưởng parallel execution/worker scheduling. `workers.max` **không** có nghĩa RAM của mỗi worker chỉ là 1/4 RAM máy; cũng không thay JVM `-Xmx`.

Có thể thử giảm concurrency:

~~~bash
gradle build --max-workers=2
~~~

Nếu build bớt OOM và elapsed time tốt hơn, đó là bằng chứng tài nguyên đang bị tranh chấp; vẫn cần xác định process bottleneck.

## 9. Bài toán memory budget trên CI

Giả sử CI container có limit 8 GiB:

| Thành phần | Cấu hình thử | Heap ceiling tiềm năng |
| --- | --- | --- |
| Gradle Daemon | `-Xmx2g` | ~2 GiB |
| Test process 1 | `-Xmx1g` | ~1 GiB |
| Test process 2 | `-Xmx1g` | ~1 GiB |
| Kotlin daemon | `-Xmx1g` | ~1 GiB |
| Compiler worker | Tùy task | Có thể thêm |
| Metaspace/native/OS | Không thuộc Xmx | Cần headroom |

Không lấy `2 + 1 + 1 + 1 = 5 GiB` rồi kết luận còn chắc chắn 3 GiB. Mỗi JVM còn Code Cache, Metaspace, thread stacks, direct/mapped buffers và OS overhead. Mặt khác, JVM **không nhất thiết tiêu thụ toàn bộ maximum heap** ở mọi thời điểm.

### 9.1. Quy trình sizing có kiểm soát

1. Đo **peak RSS/container memory** của build đại diện.
2. Xác định số JVM processes và memory policy của từng process.
3. Đọc GC/heap metrics để xác định thiếu heap hay native memory.
4. Tăng heap cho **đúng process** đang thiếu.
5. Giảm `maxParallelForks`/`--max-workers` khi concurrency vượt memory budget.
6. Dành headroom cho OS, metaspace, network/file caches và CI runtime.
7. So tổng build time và peak memory trước/sau.
8. Kiểm lại khi thay Gradle Wrapper/JDK/plugins.
9. Không đặt quá nhiều JVM args profiles khác nhau gây nhiều incompatible daemons.
10. Nếu workload rất nặng, cân nhắc chia CI jobs thay vì tăng heap một JVM.

### 9.2. Khi nào tăng Gradle heap hữu ích?

- Nhiều projects/plugins và configuration model lớn.
- Heap của Gradle daemon gần max trong nhiều lần GC.
- OOM thực sự phát sinh trong Gradle Daemon.
- Build có tasks/build logic nặng chạy trong daemon JVM.

### 9.3. Khi nào tăng heap không giúp?

- Dependency downloads/network latency là bottleneck.
- Java Test JVM lỗi OOM.
- Kotlin compiler daemon riêng thiếu memory.
- OS/container OOM kill vì **tổng RSS**.
- Gradle task inputs bị invalidated khiến compilation chạy lại.
- Build configuration chậm do eager plugin logic.
- Disk I/O hoặc CPU saturation.
- Có nhiều daemon PID do JDK/Gradle versions khác nhau.

## 10. Project Java 17 runnable: so Gradle Daemon với app JVM

Bài lab tạo hai phép đo độc lập:

- Typed Gradle task `inspectGradleJvm` chạy trong JVM thực thi build, in Gradle process PID/JDK/heap.
- Java 17 program `demo.daemon.ProbeMain` chạy qua `application.run` trong JVM riêng, in application PID/JDK/heap.
- Thay `org.gradle.jvmargs` để thấy daemon mới, trong khi `run.maxHeapSize` không đổi.

### 10.1. Thư mục đầy đủ

~~~text
daemon-memory-lab/
├── settings.gradle.kts
├── gradle.properties
├── build.gradle.kts
└── src/main/java/demo/daemon/ProbeMain.java
~~~

Không cần external dependencies; core `application` plugin đủ. Dùng JDK17 và Gradle version tương thích. Với project mới chưa có Wrapper, ví dụ dùng `gradle` đã cài trên PATH.

### 10.2. settings.gradle.kts

~~~kotlin
rootProject.name = "daemon-memory-lab"
~~~

### 10.3. gradle.properties

~~~properties
org.gradle.daemon=true
org.gradle.jvmargs=-Xmx768m -XX:MaxMetaspaceSize=384m -Dfile.encoding=UTF-8
~~~

Đây là heap ceiling **Gradle build JVM** 768 MiB, chưa phải heap của application JVM.

### 10.4. build.gradle.kts hoàn chỉnh

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.tasks.JavaExec
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id("application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

application {
    mainClass.set("demo.daemon.ProbeMain")
}

abstract class InspectGradleJvm : DefaultTask() {
    @TaskAction
    fun report() {
        val runtime = Runtime.getRuntime()
        println("GRADLE_INSPECTION=OK")
        println("GRADLE_PID=" + ProcessHandle.current().pid())
        println("GRADLE_JAVA_FEATURE=" + Runtime.version().feature())
        println(
            "GRADLE_HEAP_MAX_MIB=" +
                runtime.maxMemory() / (1024 * 1024)
        )
    }
}

tasks.register<InspectGradleJvm>("inspectGradleJvm") {
    group = "verification"
    description = "Prints build JVM PID, Java version and heap"
}

tasks.named<JavaExec>("run") {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
    maxHeapSize = "256m"
    systemProperty("probe.role", "application")
}
~~~

**Tại sao code đúng phạm vi:**

- `inspectGradleJvm` có `@TaskAction`; nó chạy trong **JVM chứa Gradle task action**.
- `run` là `JavaExec`, gọi **java launcher khác**; được chọn tường minh là JDK17.
- `options.release.set(17)` bảo đảm source/API target Java17.
- `ProcessHandle.current().pid()` trả PID thật, không phải hằng.
- `Runtime.maxMemory()` đo **Java heap maximum**, không đo toàn bộ RSS.
- `maxHeapSize="256m"` chỉ áp dụng cho `run` JVM.
- Task `inspectGradleJvm` không khai output, nên không cần kỳ vọng `UP-TO-DATE`/`FROM-CACHE`; nó luôn có hành động kiểm tra khi được chạy.

### 10.5. src/main/java/demo/daemon/ProbeMain.java

~~~java
package demo.daemon;

public final class ProbeMain {
    private ProbeMain() {
    }

    public static void main(String[] args) {
        String role = System.getProperty("probe.role");
        if (!"application".equals(role)) {
            throw new IllegalStateException(
                    "Missing probe.role=application");
        }

        System.out.println("APP_PROBE=OK");
        System.out.println("APP_ROLE=" + role);
        System.out.println(
                "APP_JAVA_FEATURE=" + Runtime.version().feature()
        );
        System.out.println(
                "APP_PID=" + ProcessHandle.current().pid()
        );
        System.out.println(
                "APP_HEAP_MAX_MIB=" +
                    Runtime.getRuntime().maxMemory() / (1024 * 1024)
        );
    }
}
~~~

Code dùng Java 17 APIs và chỉ standard library. Nó chủ động fail nếu `probe.role` chưa được truyền, giúp xác minh cấu hình JavaExec thật.

### 10.6. Chạy task quan sát Gradle JVM

Từ thư mục cha của project:

~~~bash
gradle -p daemon-memory-lab inspectGradleJvm --quiet
~~~

Dòng stdout **chính xác, ổn định**:

~~~text
GRADLE_INSPECTION=OK
~~~

Ngoài dòng đó, task còn in `GRADLE_PID=...`, `GRADLE_JAVA_FEATURE=...` và `GRADLE_HEAP_MAX_MIB=...` với **giá trị động** từ machine/JVM. Không thể hard-code PID/heap/Daemon Java version vào expected output vì phụ thuộc runtime.

### 10.7. Chạy application JVM

~~~bash
gradle -p daemon-memory-lab run --quiet
~~~

**Ba dòng đầu** của stdout Java program, khi dùng đúng Java17 launcher, là:

~~~text
APP_PROBE=OK
APP_ROLE=application
APP_JAVA_FEATURE=17
~~~

Program còn in `APP_PID=...` và `APP_HEAP_MAX_MIB=...`; hai con số không cố định. Application heap được giới hạn khoảng 256 MiB; build daemon `-Xmx768m`. Đây là phép chứng minh **hai JVM/process heaps khác nhau**.

### 10.8. Thử reuse Daemon PID

Chạy hai lần:

~~~bash
gradle -p daemon-memory-lab inspectGradleJvm --quiet
gradle -p daemon-memory-lab inspectGradleJvm --quiet
~~~

Nếu daemon vẫn IDLE, Gradle/JDK/flags không đổi và không có process restart, hai lần thường in **cùng GRADLE_PID**. Nếu khác, đọc `--status` và daemon logs; PID không có guarantee tuyệt đối.

### 10.9. Đổi daemon heap

Chỉ sửa trong `gradle.properties` thành:

~~~properties
org.gradle.jvmargs=-Xmx1536m -XX:MaxMetaspaceSize=384m -Dfile.encoding=UTF-8
~~~

Rồi chạy:

~~~bash
gradle -p daemon-memory-lab inspectGradleJvm --quiet
gradle --status
~~~

Gradle thường tạo daemon **mới** phù hợp `-Xmx1536m` thay vì nâng heap của daemon cũ. Build PID và measured max heap có thể khác. Cấu hình `run.maxHeapSize=256m` vẫn giữ nguyên; **ứng dụng không tự lên 1536 MiB**.

### 10.10. Quan sát single-use daemon

~~~bash
gradle -p daemon-memory-lab inspectGradleJvm --no-daemon --info
~~~

Nếu Gradle cần JVM settings khác client, log có thể nói về **single-use daemon**. Nó chạy một build rồi dừng; không phải daemon được reuse xuyên các invocations.

## 11. Kiểm Java 17 độc lập bằng javac/java

Để xác minh Java source mà **không chạy Gradle**, dùng JDK17.

### 11.1. Linux/macOS

Đứng trong `daemon-memory-lab`:

~~~bash
mkdir -p out
javac --release 17 -d out src/main/java/demo/daemon/ProbeMain.java
java -Xmx256m -Dprobe.role=application -cp out demo.daemon.ProbeMain
~~~

### 11.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out src\main\java\demo\daemon\ProbeMain.java
java -Xmx256m -Dprobe.role=application -cp out demo.daemon.ProbeMain
~~~

Với **Java17 runtime**, ba dòng đầu:

~~~text
APP_PROBE=OK
APP_ROLE=application
APP_JAVA_FEATURE=17
~~~

PID và heap cuối vẫn thay đổi. Nếu PATH trỏ runtime Java21, dòng Java feature phản ánh 21 dù bytecode được compile với `--release17`. Các lệnh độc lập này **không chứng minh daemon reuse**; phải chạy Gradle `inspectGradleJvm` để đo Gradle build process.

### 11.3. Khi repo đã có Gradle Wrapper

Linux/macOS:

~~~bash
./gradlew --version
./gradlew inspectGradleJvm --quiet
./gradlew run --quiet
~~~

Windows:

~~~bat
gradlew.bat --version
gradlew.bat inspectGradleJvm --quiet
gradlew.bat run --quiet
~~~

Nếu project mới chưa có `gradlew`, không chạy Wrapper command rồi kết luận Daemon lỗi. Có thể dùng Gradle cài sẵn để tạo Wrapper và commit cấu trúc Wrapper đầy đủ theo team policy.

## 12. Benchmark cold vs warm builds

### 12.1. Ba trường hợp cần đo

| Chế độ | Tình trạng đầu | Thông tin thu được |
| --- | --- | --- |
| Cold daemon | Không có daemon phù hợp | JVM startup + warm-up cost |
| Warm daemon | Có daemon IDLE compatible | Trải nghiệm build lặp lại |
| No-daemon | Không reuse giữa invocations | Chi phí không duy trì JVM lâu sống |

Một benchmark chỉ gọi `gradle build` đúng một lần không có ý nghĩa để đánh giá lợi ích JVM reuse trên developer workflow.

### 12.2. Chạy thử

Với Wrapper:

~~~bash
./gradlew --stop

./gradlew help --info
./gradlew help --info
./gradlew help --info
~~~

Lệnh đầu tạo điều kiện cold-daemon cho Gradle version tương ứng; các invocation sau thường warm. Nhưng lần đầu còn có plugin caches, JIT, filesystem/OS caches khác, nên **không quy toàn bộ chênh lệch thời gian cho Daemon**.

### 12.3. Profile task timing

~~~bash
./gradlew assemble --profile
~~~

Gradle tạo profiling report dưới build reports/profile theo Gradle version. Với tổ chức cho phép dùng Build Scan:

~~~bash
./gradlew assemble --scan
~~~

Scan giúp xem execution/configuration/cache diagnostics, nhưng có thể truyền metadata/source paths lên dịch vụ ngoài; phải xem security policy và quyền chia sẻ trước khi dùng.

### 12.4. Cách benchmark ít sai lệch

1. Dùng cùng Gradle Wrapper và JDK.
2. Pin JVM flags, number of workers và test forks.
3. Dùng cùng source inputs/dependencies.
4. Tách cold vs warm Daemon iterations.
5. Ghi Configuration Cache/Build Cache state.
6. Ghi task outcomes (`UP-TO-DATE`/`FROM-CACHE`/executed).
7. Lấy nhiều mẫu, xem median/trend thay vì một thời điểm.
8. Đo peak RSS/GC vì build nhanh nhưng OOM không phải cải thiện.
9. Không gọi `--stop` giữa các vòng đo warm.
10. So trên cùng CPU/RAM/CI resource quotas.

## 13. Daemon, Build Cache và Configuration Cache khác nhau

| Công nghệ | Dữ liệu được reuse | Có cần cùng PID không? |
| --- | --- | --- |
| Daemon | JVM/classes/JIT/in-memory state | Thường cần reuse process |
| Configuration Cache | Kết quả configuration/task graph | Không |
| Build Cache | Task outputs theo keys | Không |
| Dependency Cache | Downloaded libraries/metadata | Không |
| Incremental compilation | Chỉ compile phần affected | Không nhất thiết |

Ví dụ:

~~~bash
gradle test --configuration-cache
gradle test --configuration-cache
~~~

Lần sau có thể reuse configuration khi inputs/compatibility cho phép, **ngay cả khi daemon đã restart** vì snapshot nằm trong cache. Ngược lại, daemon warm không bảo đảm task graph được reuse nếu Configuration Cache tắt.

### 13.1. Các Gradle properties không thể thay thế nhau

~~~properties
org.gradle.daemon=true
org.gradle.caching=true
org.gradle.configuration-cache=true
org.gradle.parallel=true
org.gradle.workers.max=4
~~~

Đây là năm controls khác nhau:

- `daemon` quyết định process reuse.
- `caching` quyết định task output cache.
- `configuration-cache` lưu configuration/task graph.
- `parallel` cho phép parallel project tasks.
- `workers.max` giới hạn Gradle workers.

Không bật tất cả bừa bãi rồi quy một lần speedup hoặc OOM cho `org.gradle.daemon`.

### 13.2. Up-to-date không phải From-cache

~~~text
> Task :compileJava UP-TO-DATE
> Task :resources FROM-CACHE
~~~

Đây là các outcome **minh họa**. Up-to-date thường dựa local input/output history; From-cache là lấy output từ Build Cache. Cả hai độc lập với việc daemon PID đã reuse.

## 14. Cấu hình bộ nhớ Test, compiler và JavaExec tách khỏi daemon

### 14.1. Test heap

Một cấu hình mặc định thận trọng cho các tests nhỏ:

~~~kotlin
import org.gradle.api.tasks.testing.Test

tasks.withType<Test>().configureEach {
    maxHeapSize = "512m"
    maxParallelForks = 1
}
~~~

Nếu test suite lớn và host có RAM:

~~~kotlin
tasks.withType<Test>().configureEach {
    maxHeapSize = "768m"
    maxParallelForks = 2
    forkEvery = 0
}
~~~

`forkEvery=0` nghĩa Gradle không tự thay Test JVM sau mỗi số lượng test classes cố định; đặt `forkEvery=1` có thể gây chi phí startup lớn. Nhiều Test tasks từ các modules khác nhau vẫn có thể chạy song song.

### 14.2. Parallel workers

~~~properties
org.gradle.parallel=true
org.gradle.workers.max=2
~~~

Kết hợp Test forks để giảm memory spike, nhưng chỉ nên commit khi benchmark chứng minh phù hợp. Có thể override theo CLI:

~~~bash
gradle build --max-workers=2
~~~

Parallelism không mặc nhiên nhanh hơn nếu RAM ít hoặc workload tranh cùng filesystem/database.

### 14.3. Compiler fork

Nếu JavaCompile worker thực sự cần heap riêng:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.fork = true
    options.forkOptions.memoryMaximumSize = "1g"
}
~~~

Đây là fragment mở rộng cần import `JavaCompile` và Java plugin. Forking mọi task có thể tăng startup/RSS; đừng áp chỉ vì Gradle Daemon đã có heap lớn.

### 14.4. Kotlin daemon inheritance

Kotlin Gradle Plugin có compiler daemon và memory setting riêng:

~~~properties
kotlin.daemon.jvmargs=-Xmx1500m -Xms256m
~~~

Kotlin docs cho biết một số JVM args của Gradle daemon được kế thừa khi Kotlin daemon chưa override, ví dụ heap maximum. Vì vậy tăng `org.gradle.jvmargs` đôi khi làm **tổng potential heap** tăng cả ở compiler daemon. Kiểm process list/GC khi build Kotlin, không tự áp property Kotlin cho Java-only demo.

## 15. Chẩn đoán OOM: heap, Metaspace và OS kill

### 15.1. Java heap space

~~~text
java.lang.OutOfMemoryError: Java heap space
~~~

Có thể xảy ra trong Gradle Daemon, Test JVM, Kotlin daemon, forked javac hoặc application process. Cần xác định **task, PID và JVM flags** trước khi đổi setting.

Nếu stacktrace thuộc Test task/worker, tăng daemon heap không trực tiếp chữa. Nếu daemon chính bị thiếu heap, xét `org.gradle.jvmargs` và root cause của build scripts/plugins.

### 15.2. Metaspace

~~~text
java.lang.OutOfMemoryError: Metaspace
~~~

có thể do quá nhiều classes/classloaders hoặc Metaspace ceiling thấp. Tăng `-Xmx` (heap) không trực tiếp giải quyết native metadata limit. Kiểm `-XX:MaxMetaspaceSize`, classloader references và plugin lifecycle.

### 15.3. OOMKilled, exit 137 và Daemon disappeared

~~~text
Gradle build daemon disappeared unexpectedly
~~~

không chứng minh lỗi heap thiếu. OS/container có thể kill JVM khi **tổng RSS vượt cgroup limit**, không nhất thiết JVM có thời gian ném `Java heap space`.

Kiểm:

- Daemon `out.log` và JVM crash logs `hs_err_pid...`.
- CI job/container status `OOMKilled`, SIGKILL/exit137.
- Host memory pressure, swap, cgroup metrics.
- Số Test/Kotlin/compiler/Gradle worker JVMs chạy song song.
- Gradle/JDK compatibility hoặc local daemon socket/permissions issues.
- Heap/Metaspace/native memory và GC metrics.

**Cảnh báo:** với container 4 GiB, đặt Daemon `-Xmx4g` rồi chạy thêm Test forks thường gây áp lực lớn. Tăng heap có thể khiến OS kill sớm hơn.

### 15.4. GC overhead

Nếu build chậm do GC pauses, có thể thử:

- Đo heap used/max, allocation rate, GC count/time.
- Tăng daemon heap vừa phải nếu đúng process bị pressure.
- Giảm object churn do build script/plugin.
- Giảm parallelism nếu CPU/RAM bị tranh chấp.
- Xem classloader/heap leaks nếu live objects tăng qua nhiều builds.

Không thay bộ thu gom rác liên tục nếu không có metrics, vì JVM defaults có thể đã phù hợp.

### 15.5. GC logs và heap dump phải bảo mật

Một JDK17 JVM option chẩn đoán:

~~~properties
org.gradle.jvmargs=-Xmx2g -XX:MaxMetaspaceSize=512m -Xlog:gc*:file=gradle-gc.log:time,uptime,level,tags
~~~

Đây **chỉ là snippet khi troubleshooting**. File log phải có vị trí ghi được; nhiều daemon có thể cùng tên log file và tạo xung đột. Xem docs JDK tương ứng. Heap dump/logs có thể chứa dữ liệu nhạy cảm của build; lưu trữ và chia sẻ có kiểm soát.

## 16. Khi nào nên stop Daemon để sửa lỗi?

Dùng `gradle --stop` có ý nghĩa khi:

- Thử thay JVM/JDK/heap settings và muốn dọn daemon cũ.
- Nghi daemon state/classloader leak, cần kiểm xem restart có tạm hết lỗi.
- Daemon connection/registry lỗi và logs hướng tới restart.
- Debug cần một JVM mới sạch.
- Điều tra Gradle upgrade giữa versions.

Không nên:

- Stop mỗi lần hoàn tất `gradle test`.
- Stop để “xóa Build Cache”.
- Stop vì task có outcome `UP-TO-DATE`.
- Stop chỉ vì phát hiện nhiều PIDs nhưng chưa xác định versions/flags.
- Lạm dụng stop như giải pháp vĩnh viễn cho memory leak.

Nếu daemon stop rồi mọi thứ tạm ổn nhưng sau N builds lại lỗi, hãy thu heap/GC logs và tìm root cause.

## 17. Groovy DSL tương đương

`gradle.properties` không phụ thuộc DSL:

~~~properties
org.gradle.daemon=true
org.gradle.jvmargs=-Xmx768m -XX:MaxMetaspaceSize=384m -Dfile.encoding=UTF-8
~~~

Phần ứng dụng của lab có thể viết bằng `build.gradle` Groovy:

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

application {
    mainClass = 'demo.daemon.ProbeMain'
}

tasks.named('run', JavaExec) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
    maxHeapSize = '256m'
    systemProperty 'probe.role', 'application'
}
~~~

Và `settings.gradle`:

~~~groovy
rootProject.name = 'daemon-memory-lab'
~~~

Đây là **phương án thay thế cấu hình application** của Kotlin DSL lab, chưa bao gồm typed `inspectGradleJvm` task. Giữ nguyên `ProbeMain.java`; khi muốn đo daemon có thể dùng `--status`/`jps`/`jcmd` hoặc viết task type Groovy/Java riêng. Không ghép `build.gradle` và `build.gradle.kts` như hai cấu hình cạnh tranh trong cùng demo.

## 18. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm |
| --- | --- | --- |
| Lần đầu chậm, lần sau nhanh | JVM warm-up, cache, tasks up-to-date | PID, task outcomes, profile |
| Luôn "Starting a Gradle Daemon" | JVM args/JDK/version đổi, daemon tự dừng | `--status`, logs, gradle.properties |
| IDE khác terminal PID | Gradle JVM/Wrapper criteria khác | IDE settings, `JAVA_HOME`, version |
| Nhiều Daemon processes | Multiple versions/JVM args, concurrent builds | `jps`, process flags |
| `--no-daemon` vẫn fork JVM | Single-use daemon để honor JVM flags | `--info` |
| Daemon heap OOM | Heap quá thấp/leak trong build logic | daemon log/GC/jcmd |
| Test OOM | Test worker heap quá thấp | Test.maxHeapSize, test process logs |
| Kotlin OOM | Kotlin daemon memory/strategy | kotlin.daemon.jvmargs, KGP logs |
| JVM `Metaspace` OOM | Class metadata/classloader pressure | Metaspace settings/heap diagnostics |
| Container OOMKilled | Tổng RSS của nhiều JVM vượt limit | Container metrics, worker limits |
| Daemon disappeared | JVM crash/OS kill/connection issue | daemon log, hs_err, OS/CI events |
| Build chậm dù heap lớn | CPU/I/O/configuration/dependency bottleneck | `--profile`, scan, task outcomes |
| Gradle fail khi chọn JDK | Unsupported Gradle runtime/toolchain resolution | compatibility matrix, `--version` |
| `updateDaemonJvm` fail | Chưa có toolchain resolver/URLs | daemon JVM docs và settings |
| Có warm daemon nhưng không FROM-CACHE | Hai loại cache khác nhau | Build Cache settings, task keys |

### 18.1. Không xóa ~/.gradle tùy tiện

Xóa user-home caches/distributions có thể khiến plugin/dependency downloads tốn nhiều thời gian, không sửa JVM flags hoặc plugin bug. Trước hết dùng diagnostics có phạm vi hẹp; xóa dữ liệu chỉ khi có bằng chứng corruption và đã cân nhắc hậu quả.

### 18.2. Không áp memory rule toàn máy

Một daemon Gradle 9.x/JDK21 của IDE và daemon Gradle 8.x/JDK17 của CLI có thể cùng tồn tại hợp lệ. Không dùng kill-all Java processes nếu nó cũng giết application servers, IDE hoặc test services.

## 19. Hai mươi bài tập có đáp án

### Bài 1. Vì sao Daemon tăng tốc build lặp lại?

**Đáp án:** Reuse JVM/loaded classes/JIT/in-memory state, tránh startup overhead.

### Bài 2. Daemon bật mặc định hay chưa?

**Đáp án:** Bật trên Gradle hiện đại, từ Gradle 3.0.

### Bài 3. Điều kiện reuse?

**Đáp án:** Cùng Gradle version, Java runtime/JVM criteria/JVM settings tương thích và daemon sẵn sàng.

### Bài 4. Vì sao đổi -Xmx sinh PID mới?

**Đáp án:** Xmx là startup attribute; JVM cũ không thể hot-resize max heap theo requested flags.

### Bài 5. org.gradle.jvmargs là memory của ai?

**Đáp án:** Gradle build JVM/Daemon, không mặc định Test hoặc JavaExec.

### Bài 6. JAVA_OPTS và org.gradle.jvmargs?

**Đáp án:** JAVA_OPTS thường áp client; org.gradle.jvmargs cho build JVM.

### Bài 7. Idle timeout mặc định?

**Đáp án:** Ba giờ, tương đương 10.800.000 milliseconds theo Gradle docs hiện hành.

### Bài 8. gradle --status có liệt kê mọi Gradle versions?

**Đáp án:** Không. Chỉ daemons của cùng Gradle version đang thực hiện command.

### Bài 9. gradle --stop dừng gì?

**Đáp án:** Daemons thuộc Gradle version tương ứng, không kill mọi JVM.

### Bài 10. --no-daemon vẫn có build JVM mới?

**Đáp án:** Có thể có single-use daemon khi client JVM options không phù hợp requested build JVM.

### Bài 11. Daemon JDK khác Java toolchain?

**Đáp án:** Được, miễn cả Gradle runtime và project tasks dùng JDK versions được hỗ trợ.

### Bài 12. Daemon JVM criteria ưu tiên gì?

**Đáp án:** Khi có criteria hợp lệ, nó có precedence trước JAVA_HOME và org.gradle.java.home đối với Daemon JVM.

### Bài 13. Xmx2g có nghĩa RSS tối đa 2 GiB?

**Đáp án:** Không. Metaspace, Code Cache, thread/native/buffer memory ngoài Java heap.

### Bài 14. Test task OOM còn Daemon có 4 GiB?

**Đáp án:** Kiểm Test.maxHeapSize, workers, leaks và test JVM process; Daemon Xmx không trực tiếp cấp cho test.

### Bài 15. Hai test forks?

**Đáp án:** `maxParallelForks=2` có thể chạy hai Test JVMs đồng thời trong một Test task; mỗi process có heap limit riêng.

### Bài 16. Kotlin daemon memory?

**Đáp án:** `kotlin.daemon.jvmargs`, có thể kế thừa một số JVM flags của Gradle daemon khi không override.

### Bài 17. Lab app stdout?

Với `gradle -p daemon-memory-lab run --quiet`, dòng đầu chính xác?

**Đáp án:**

~~~text
APP_PROBE=OK
~~~

### Bài 18. Hai lần inspectGradleJvm cho PID khác?

**Đáp án:** Kiểm Daemon stop/restart, busy, JVM args/JDK/Gradle version, monitoring hoặc IDE vs CLI environment.

### Bài 19. Build trong container 4 GiB có Daemon Xmx4g và Test workers?

**Đáp án:** Có rủi ro OOMKilled cao; hạ heap/workers hoặc tăng limit hợp lý dựa trên peak RSS.

### Bài 20. Daemon disappeared unexpectedly có chắc heap OOM?

**Đáp án:** Không. Kiểm logs, JVM crash, OS/container kill, socket/network/permission và JDK compatibility.

## 20. Checklist áp dụng thực tế

| Kiểm tra | Điều kiện đạt |
| --- | --- |
| Gradle Wrapper | Version pin, phù hợp JDK của build engine |
| Client JVM | JAVA_HOME/PATH/IDE launcher rõ |
| Daemon JVM | Criteria hoặc org.gradle.java.home/Tooling API policy rõ |
| JVM reuse | PID/--status cho thấy compatible idle daemon được reuse khi phù hợp |
| Heap | org.gradle.jvmargs đủ cho build nhưng có headroom |
| Non-heap | Metaspace, Code Cache/native/RSS được xét |
| Test forks | maxHeapSize và maxParallelForks phù hợp RAM/CPU |
| Kotlin compiler | JVM options/daemon process riêng được xét khi có KGP |
| Java compiler | Fork options đặt đúng task nếu cần |
| Application JVM | JavaExec/launcher/maxHeapSize không bị nhầm với Daemon |
| Parallel | workers.max và CI job concurrency trong memory budget |
| Idle behavior | Không stop daemon sau mỗi build; cleanup theo policy |
| Cache | Daemon, Configuration Cache, Build Cache được đo tách biệt |
| Benchmark | Cold/warm iterations, task outcomes, GC/peak RSS |
| Diagnostics | Daemon logs, jps/jcmd, CI/container events khi có lỗi |
| Security | Heap dumps/GC logs/credentials được bảo vệ |
| Lab Java17 | inspectGradleJvm và ProbeMain chạy, PID/heap đúng phạm vi |

**Kết luận:** Gradle Daemon giúp build lặp lại nhanh hơn nhờ **tái sử dụng JVM chạy Gradle** và các lợi ích JIT/in-memory state. Chỉ daemon có Gradle version, Java runtime và JVM startup settings tương thích mới được reuse. Bộ nhớ Gradle Daemon do `org.gradle.jvmargs` điều khiển, nhưng Test, JavaExec, Java compiler và Kotlin daemon có JVM/memory controls riêng. Khi tối ưu hiệu năng hoặc xử lý OOM, phải đo **đúng process, đúng task và tổng memory budget**, thay vì tự động tắt daemon hay tăng `-Xmx` ở mọi nơi.

## 21. Tài liệu tham khảo chính thức

- [Gradle — The Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html) — lifecycle, client vs daemon, compatible JVMs, status/stop, logs, idle timeout, monitoring, criteria.
- [Gradle — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html) — `org.gradle.jvmargs`, `org.gradle.java.home`, `org.gradle.daemon` và property precedence.
- [Gradle — Configuring Gradle](https://docs.gradle.org/current/userguide/config_gradle.html) — heap/metaspace defaults, client `JAVA_OPTS`, separate JVMs.
- [Gradle — Improve Build Performance](https://docs.gradle.org/current/userguide/performance.html) — Daemon, heap, caches, parallel scheduling và profiling.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/gradle_command_line.html) — `--status`, `--stop`, `--no-daemon`, `--max-workers`, `--profile`, `--scan`.
- [Gradle — Toolchains](https://docs.gradle.org/current/userguide/toolchains.html) — Java toolchains cho project, Daemon JVM criteria.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) — JVM/Gradle versions được hỗ trợ.
- [Gradle — Testing Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html) — forked Test JVMs, maxHeapSize, maxParallelForks, forkEvery.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html) — JavaExec run process.
- [Gradle — JavaExec DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.JavaExec.html) — maxHeapSize, jvmArgs, javaLauncher.
- [Gradle — ForkOptions](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.ForkOptions.html) — forked Java compiler memoryMaximumSize.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html) — configuration/task graph reuse.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html) — task output caching.
- [Kotlin — Compilation and Caches](https://kotlinlang.org/docs/gradle-compilation-and-caches.html) — Kotlin compiler daemon JVM arguments và inheritance.
- [Oracle Java SE 17 — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html) — JVM diagnostics.
- [Oracle Java SE 17 — jps](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jps.html) — Java process list.
