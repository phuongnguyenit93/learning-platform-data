# Điều chỉnh Gradle Daemon, bộ nhớ JVM và mức độ chạy song song

Trong dự án Java/Spring Boot, khi `./gradlew build` chậm, tác vụ bị `OutOfMemoryError`, máy liên tục đổi sang swap, hoặc CI bị hệ điều hành kết thúc vì thiếu RAM, ba nhóm thiết lập cần hiểu là **Gradle Daemon**, **bộ nhớ của các JVM tham gia build**, và **mức độ chạy song song**.

Đây là **ba trục cấu hình khác nhau**:

- **Gradle Daemon** là tiến trình JVM chạy Gradle lâu dài và có thể được tái sử dụng giữa nhiều lần build. Daemon giảm chi phí khởi động và giữ một số trạng thái/cache trong bộ nhớ.
- **`org.gradle.jvmargs`** đặt JVM arguments cho **Gradle build/daemon process**, ví dụ `-Xmx` (giới hạn heap). Nó **không** tự thay đổi heap của mọi JVM con, của test, của `bootRun` hay của ứng dụng đang chạy production.
- **`org.gradle.parallel` / `--parallel`** và **`org.gradle.workers.max` / `--max-workers`** điều khiển khả năng thực thi đồng thời công việc trong build. Chạy nhiều hơn có thể nhanh hơn trên máy đủ CPU/RAM, nhưng cũng có thể làm tổng bộ nhớ tăng, tranh chấp I/O hoặc khiến build kém ổn định.

**Mục tiêu là tối ưu thời gian build trong giới hạn tài nguyên**, không phải luôn bật tất cả tùy chọn ở mức cao nhất. Một cấu hình hợp lý cho máy 4 GB RAM có thể hoàn toàn không hợp lý cho CI runner 16 GB RAM hoặc máy phát triển đang chạy Docker/database/IDE cùng lúc.

Bài viết dùng lệnh Gradle Wrapper (`./gradlew`, Windows: `.\gradlew.bat`), Java 17 và Spring Boot để làm ví dụ. Những số `-Xmx` và worker count là **giá trị minh họa để thử nghiệm**, không phải khuyến nghị áp chung cho mọi máy. Hãy dựa vào tài nguyên và số liệu đo được.

## 1. Gradle chạy trên những JVM/process nào?

Đây là nơi nhiều người tối ưu sai.

Khi chạy:

~~~bash
./gradlew :app:bootJar
~~~

có thể có nhiều tiến trình:

~~~text
Terminal
   |
   v
Gradle Client JVM
   |
   | kết nối tới Daemon tương thích
   v
Gradle Daemon JVM -------------------------+
   |                                      |
   +-- cấu hình projects, plugin, tasks   |
   +-- xử lý task graph                   |
   +-- có thể fork worker process --------+
   +-- có thể fork JVM chạy Test
   +-- có thể fork Java compiler (nếu được cấu hình)
   +-- có thể fork JVM cho bootRun
   |
   v
JAR/WAR output (nếu chạy bootJar/bootWar)

Sau build, triển khai:
java -jar app.jar
   |
   v
JVM ứng dụng chạy độc lập với Gradle
~~~

Đây là sơ đồ khái quát. Từng plugin có thể chọn process, thread hoặc classloader isolation khác nhau, không phải mỗi task tự tạo một JVM.

### Những tiến trình cần phân biệt

| Thành phần | Ai khởi tạo? | Điều chỉnh bộ nhớ điển hình | Có ảnh hưởng trực tiếp tới production JVM? |
| --- | --- | --- | --- |
| Gradle Client | Script `gradlew`/IDE | `JAVA_OPTS`, `GRADLE_OPTS` trong phạm vi client | Không |
| Gradle Daemon/build JVM | Gradle khi xử lý build | `org.gradle.jvmargs` | Không |
| Gradle Test worker JVM | Task loại `Test` | `maxHeapSize`, `jvmArgs`, `maxParallelForks` | Không |
| Java compiler fork (nếu có) | `JavaCompile`/toolchain hoặc plugin | Compiler fork options, JVM memory của process tương ứng | Không |
| Kotlin compiler daemon (nếu dùng Kotlin) | Kotlin Gradle plugin | Cấu hình JVM Kotlin daemon riêng | Không tự động |
| Spring Boot `bootRun` JVM | Task `BootRun`/`JavaExec` | `jvmArgs`, `maxHeapSize` nếu API hỗ trợ | Chỉ JVM do task chạy |
| Ứng dụng chạy `java -jar` | JVM tại môi trường triển khai | `java -Xmx... -jar ...`, biến môi trường/JVM/container config | Có |

**Ví dụ:** Nếu build thất bại ở task `:app:test` vì test JVM hết heap, tăng `org.gradle.jvmargs` từ 1 GB lên 4 GB có thể **không sửa đúng vấn đề**. Cần xem giới hạn heap của **test JVM** và số tiến trình test chạy song song. Ngược lại, nếu Gradle Daemon báo `Java heap space` ngay khi cấu hình một build lớn, điều chỉnh memory của daemon mới liên quan.

## 2. Gradle Daemon là gì và giúp tăng tốc ở đâu?

**Gradle Daemon** là một tiến trình JVM tồn tại giữa các lần gọi Gradle, xử lý việc đọc settings/build scripts, resolve dependencies, tổ chức và thực hiện công việc build. Các bản Gradle hiện đại **bật Daemon theo mặc định**.

So với luôn khởi động một JVM mới, Daemon có thể:

1. Tránh một phần chi phí JVM startup của các lệnh build liên tiếp.
2. Hưởng lợi từ JVM JIT compilation đã làm nóng (*warm-up*).
3. Giữ một số trạng thái build, plugin classes và caches trong bộ nhớ.
4. Tái sử dụng thông tin file-system watching trên hệ thống được hỗ trợ.
5. Giúp các thao tác `compileJava`, `test`, `bootJar` liên tiếp có độ trễ thấp hơn khi workload lặp lại.

Không phải tốc độ luôn tăng một tỷ lệ cố định: lần build đầu thường phải resolve/download dependencies và initialize cache; lần build sau có thể nhanh vì **UP-TO-DATE**, build cache hoặc configuration cache nữa, không chỉ Daemon.

### Bật/tắt theo lần chạy

~~~bash
./gradlew help --daemon
./gradlew help --no-daemon
~~~

`--daemon` yêu cầu dùng Daemon; `--no-daemon` yêu cầu không tái sử dụng một Daemon lâu dài cho invocation này. **Lưu ý quan trọng:** nếu JVM arguments của client không đáp ứng các requirements của build, Gradle vẫn có thể tạo một **single-use Daemon** (JVM chỉ dùng cho một build rồi kết thúc) ngay cả khi có `--no-daemon`. Do đó `--no-daemon` không luôn có nghĩa “chỉ một process JVM”.

Tắt Daemon cho mọi build của project (chỉ nếu có lý do cụ thể):

~~~properties
# gradle.properties
org.gradle.daemon=false
~~~

Khi thông thường cần tốc độ cho lặp lại build trên máy developer/CI agent, giữ Daemon bật là hợp lý. Không tắt chỉ vì thấy process `GradleDaemon` trong task manager.

### Xem và dừng Daemon

~~~bash
./gradlew --status
./gradlew --stop
~~~

- `--status` cho thấy các Daemon liên quan tới **phiên bản Gradle hiện tại**, với thông tin như PID/trạng thái; không phải bảng kiểm kê mọi Java process trong máy.
- `--stop` yêu cầu dừng các Daemon do **cùng Gradle version** quản lý, giúp chẩn đoán daemon bị lỗi hoặc khởi động lại sau khi thay đổi cấu hình. Nó **không** xóa source code, build cache hay `build/`.
- Không chạy `--stop` liên tục trước mỗi build nếu đang muốn tận dụng Daemon reuse; điều đó làm mất lợi ích warm-up.

Thay đổi `org.gradle.jvmargs` hoặc JDK dùng cho Daemon có thể khiến Gradle **tạo Daemon mới** thay vì reuse Daemon cũ. Nhiều Daemon khác version/JDK/JVM arguments có thể cùng tồn tại và chiếm RAM; kiểm tra chúng trước khi kết luận có memory leak.

### Logs và vấn đề Daemon

Trong Gradle User Home, thư mục thường là:

~~~text
~/.gradle/daemon/<gradle-version>/
    daemon-<pid>.out.log
    registry.bin
~~~

Trên Windows, Gradle User Home mặc định ở `%USERPROFILE%\.gradle` (trừ khi đổi `GRADLE_USER_HOME`). Log Daemon giúp kiểm tra lỗi GC, daemon bị crash, JVM start parameters hoặc vì sao Gradle không kết nối được. Khi có vấn đề kết nối, hãy xem thông báo console và log tương ứng, không vội tăng heap.

**Mức độ tái sử dụng:** Gradle sẽ tìm Daemon tương thích về Gradle version, Java runtime, JVM startup arguments và một số thuộc tính môi trường bất biến. Đổi `-Xmx` tạo một bộ requirements mới; Gradle không thể thay đổi max heap của một JVM đang chạy.

## 3. Những file và biến môi trường điều khiển Gradle

Cấu hình thông dụng:

| Nơi cấu hình | Phạm vi | Ví dụ |
| --- | --- | --- |
| `<root>/gradle.properties` | Các build dùng project root này | `org.gradle.jvmargs=-Xmx1g` |
| `<GRADLE_USER_HOME>/gradle.properties` | Thiết lập theo người dùng/CI agent | Giới hạn tài nguyên máy riêng |
| Command line option | Invocation hiện tại | `--parallel --max-workers=2` |
| `JAVA_HOME` / PATH/IDE JVM | JVM khởi động Gradle client, default khi không chỉ định khác | JDK runtime |
| `org.gradle.java.home` | JDK/JVM dùng để chạy Gradle build process theo cơ chế Gradle | Đường dẫn JDK cụ thể |
| Daemon JVM criteria (nếu sử dụng) | Quy tắc chọn JVM cho Daemon ở Gradle version hỗ trợ | `gradle/gradle-daemon-jvm.properties` |
| Java toolchain trong `build.gradle` | Java compiler/test/tool invocations theo plugin/toolchain support | Java 17 compile |
| Task-specific JVM properties | JVM fork của test/bootRun/worker | `maxHeapSize`, `jvmArgs` |

**Không trộn lẫn `-P...` với JVM args.** `-PbuildType=...` tạo project property; `-D...` thiết lập system property; `--max-workers` là Gradle CLI option. Mỗi nơi ảnh hưởng một cơ chế khác.

Gradle có thứ tự ưu tiên cụ thể giữa command-line system properties, user-home properties và root properties; đồng thời settings/plugin logic có thể điều chỉnh một số giá trị. Để tránh tranh chấp trong nhóm, chọn một nguồn mặc định được quản lý rõ ràng rồi override từng invocation khi đo đạc. Đừng có một `-Xmx` trong local profile, một trong CI environment và một trong root file mà không biết giá trị nào đang hiệu lực.

### Đặc biệt: `JAVA_OPTS` và `GRADLE_OPTS`

Hai biến thường làm người học hiểu sai:

- `JAVA_OPTS` thường điều chỉnh **Gradle Client JVM**, không phải Daemon JVM chạy build khi Daemon được sử dụng.
- `GRADLE_OPTS` cũng thường đi vào **Gradle Client JVM**; nó có thể chuyển system property cấu hình Gradle (như `-Dorg.gradle.jvmargs=...`) để làm thay đổi yêu cầu của Daemon.
- **Cách dễ kiểm soát nhất để đặt heap của Gradle build process là `org.gradle.jvmargs`.**

Vì vậy, cấu hình `JAVA_OPTS=-Xmx4g` rồi thấy Daemon vẫn dùng heap khác không nhất thiết là lỗi. Client chỉ chuyển yêu cầu và hiển thị output, còn Daemon có JVM args riêng.

### Gradle Daemon JVM khác Java toolchain

Ví dụ `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Cấu hình này yêu cầu compiler/tools tương thích Java 17 cho project. Nó **không đồng nghĩa** với “Gradle Daemon luôn chạy bằng JDK 17”. Daemon JVM có thể được chọn qua môi trường, `org.gradle.java.home` hoặc Daemon JVM criteria tùy Gradle version.

Trong phiên bản Gradle hỗ trợ **Daemon JVM criteria**, task `updateDaemonJvm` có thể tạo `gradle/gradle-daemon-jvm.properties` để khai báo Java version/vendor cần cho Daemon. Cơ chế này có thể có precedence cao hơn `JAVA_HOME` và `org.gradle.java.home`. Chỉ áp dụng khi project/Gradle version hỗ trợ, và cần kiểm tra quy tắc tải/cấp phát JDK của môi trường.

**Đừng thay JDK ngẫu nhiên khi chỉ muốn tăng heap.** Java toolchain, JVM của Daemon, JVM test và JVM production có thể khác nhau có chủ đích.

## 4. Điều chỉnh bộ nhớ JVM bằng `org.gradle.jvmargs`

Một file `gradle.properties` trong root project có thể có:

~~~properties
# Cấu hình minh họa, phải đo theo RAM thực tế.
org.gradle.daemon=true
org.gradle.jvmargs=-Xmx1g -XX:MaxMetaspaceSize=384m -Dfile.encoding=UTF-8
~~~

Phân tích:

- **`-Xmx1g`** đặt **giới hạn tối đa Java heap của Daemon** quanh mức 1 GiB. Nó không cấp phát ngay toàn bộ giá trị đó cho Java heap.
- **`-XX:MaxMetaspaceSize=384m`** giới hạn Metaspace lưu class metadata; không phải heap. Đặt giới hạn thấp quá có thể gây `OutOfMemoryError: Metaspace` trong build có nhiều plugins/classloaders.
- **`-Dfile.encoding=UTF-8`** đặt property encoding của JVM khi khởi động; Java 17/platform và plugin có thể có hành vi tương ứng, nhưng điều này không thay nhu cầu khai báo charset rõ ràng khi xử lý source/resource.
- **`-Xms`** (nếu đặt) là heap khởi tạo/khởi điểm; không mặc định cần đẩy `-Xms` ngang `-Xmx` vì có thể giữ footprint không cần thiết ở các máy thiếu RAM.
- Có thể dùng `-XX:+HeapDumpOnOutOfMemoryError` khi cần điều tra crash heap, nhưng heap dump có thể rất lớn và **chứa dữ liệu nhạy cảm**; hãy quản lý nơi lưu và quyền truy cập.

**Heap không phải tổng RAM một JVM.** Ngoài Java heap còn có Metaspace, thread stacks, code cache, direct/native buffers, JIT và overhead khác. Một Daemon với `-Xmx1g` có thể tiêu thụ tổng resident memory **lớn hơn 1 GiB**. Thêm JVM test/bootRun/worker thì tổng bộ nhớ build càng tăng.

### Khi nào tăng `-Xmx`?

Cân nhắc khi có bằng chứng:

- Gradle Daemon thực sự gặp `java.lang.OutOfMemoryError: Java heap space`.
- Build nhiều subprojects/plugins có configuration state quá lớn cho heap hiện tại.
- GC overhead cao/thường xuyên và profile cho thấy Daemon bị heap pressure.
- Một task chạy in-process cần bộ nhớ mà Daemon heap hiện tại chưa đủ.

**Không tăng Daemon heap để chữa tất cả lỗi:**

| Vị trí OOM | Chỉnh đúng nơi |
| --- | --- |
| Gradle Daemon: `Java heap space` | `org.gradle.jvmargs`, build logic và plugin behavior |
| Daemon: `Metaspace` | Metaspace trong daemon JVM args, nghi ngờ classloader churn |
| Test worker JVM | `tasks.withType(Test).configureEach { maxHeapSize=... }` |
| `bootRun` JVM | `tasks.named('bootRun') { jvmArgs ... }` |
| JVM production chạy `java -jar` | Cấu hình Java runtime/container, **không phải** Gradle Daemon |
| OS/container bị OOM killer | Tổng RAM của **tất cả** tiến trình, worker count và giới hạn container |
| Gradle process crash do native allocation | Native memory, JDK, thread count, các worker/processes |

Có thể build báo “Daemon disappeared unexpectedly” khi hệ điều hành giết process vì hết RAM; khi đó chưa có cơ sở để kết luận chỉ cần tăng `-Xmx`. Tăng heap quá cao có thể làm container **bị kill sớm hơn** do tổng resident memory tăng.

### Khi nào giảm `-Xmx`?

Giảm nếu machine có ít RAM, CI chạy nhiều Gradle builds cùng lúc hoặc build thực tế không cần mức heap cao. Mục tiêu là **đủ** chứ không phải **càng lớn càng tốt**. Nếu heap quá nhỏ sẽ gây GC thường xuyên và giảm tốc; nếu quá lớn sẽ làm tăng áp lực RAM, swap hoặc giảm headroom cho JVM con. Lựa chọn phải dựa trên đo đạc.

### Cấu hình cho JVM test

Trong `build.gradle` của module có test:

~~~groovy
tasks.withType(Test).configureEach {
    maxHeapSize = '512m'
    maxParallelForks = 1
}
~~~

`Test` là Gradle task dùng các JVM fork để thực thi tests. `maxHeapSize` điều chỉnh **heap của test worker**, còn `maxParallelForks` giới hạn số tiến trình test song song cho task này. Điều này tách biệt khỏi `org.gradle.jvmargs`.

Khi muốn chạy test nhanh hơn có thể thử:

~~~groovy
tasks.withType(Test).configureEach {
    maxHeapSize = '512m'
    maxParallelForks = 2
}
~~~

Nhưng **hai test forks** có thể đồng thời tiêu thụ gần gấp đôi **phần heap được phép**, chưa tính overhead. Nếu test dùng database shared, cổng server cố định, filesystem tạm chung hoặc static state không được cô lập, parallel forks có thể tạo flaky tests. Vì thế chỉnh test parallelism phải song hành với kiểm tra test isolation.

### Cấu hình riêng cho `bootRun`

Trong một Spring Boot `build.gradle` có Boot plugin:

~~~groovy
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named('bootRun', BootRun) {
    jvmArgs '-Xmx512m'
}
~~~

Task `bootRun` được thực hiện bằng JVM của ứng dụng dành cho development; `jvmArgs` tác động tới JVM đó. Khi sau này chạy `java -jar` tại production, lệnh `bootRun` **không còn tham gia** nên JVM arguments phải được cấu hình độc lập cho production runtime:

~~~bash
java -Xmx512m -jar build/libs/application.jar
~~~

`application.jar` là tên placeholder; phải thay bằng tên executable JAR thật. Không đặt `-Xmx` trong Gradle rồi mặc định coi ứng dụng production đã có giới hạn đó.

## 5. Điều chỉnh mức độ chạy song song

Gradle có nhiều cấp parallelism. Để tối ưu đúng cần phân biệt:

| Cấp | Tùy chọn | Phạm vi |
| --- | --- | --- |
| Parallel project execution | `--parallel` hoặc `org.gradle.parallel=true` | Cho phép các task từ các project độc lập chạy đồng thời khi được Gradle cho phép |
| Worker limit | `--max-workers=N` hoặc `org.gradle.workers.max=N` | Giới hạn năng lực thực thi concurrent work trong một Gradle build |
| Test processes | `Test.maxParallelForks` | Số JVM test fork của từng Test task |
| Tool-specific workers | Java compiler/Kotlin compiler, annotation processors, plugin task API | Có thể có cách fork và memory riêng |
| Configuration Cache | `--configuration-cache` | Cache configuration và có thể thay đổi hành vi parallel task execution theo phiên bản Gradle |
| Chạy nhiều Gradle commands/CI jobs | CI executor/concurrency | **Ngoài** giới hạn worker của một Gradle invocation |

### `--parallel` không đồng nghĩa “mọi task chạy đồng thời”

Không dùng configuration cache, `--parallel` tập trung vào **parallel execution giữa các projects** thuộc multi-project build. Các task còn phải tuân theo `dependsOn`, quan hệ input/output, constraints và lock/resource requirements. Ví dụ:

~~~text
:alpha:compileJava  ──┐
                       ├──> :app:compileJava ──> :app:bootJar
:beta:compileJava   ──┘
~~~

`:alpha` và `:beta` độc lập có thể compile đồng thời khi có đủ worker slots; `:app:compileJava` cần output của cả hai nên không được thực hiện trước khi những inputs cần thiết sẵn sàng.

Nếu chỉ có một project với task graph gần như tuyến tính, bật `--parallel` có thể **không tạo lợi ích đáng kể**. Thậm chí overhead hoặc cạnh tranh CPU/disk có thể làm build chậm hơn.

**Lưu ý theo version:** Các Gradle đời mới dùng **Configuration Cache** có thể cho phép task parallelism ngay cả trong cùng project khi task được cô lập/serialize đúng. Trong những chế độ đó `--parallel` không còn là công tắc duy nhất quyết định concurrency. Khi dạy hoặc benchmark, phải ghi rõ **Gradle version và configuration-cache mode**; không đưa nhận định tuyệt đối áp cho mọi phiên bản.

### `org.gradle.workers.max` và `--max-workers`

Thử trong root `gradle.properties`:

~~~properties
org.gradle.parallel=true
org.gradle.workers.max=2
~~~

Hoặc chỉ bật cho một invocation:

~~~bash
./gradlew :app:bootJar --parallel --max-workers=2
~~~

`--max-workers=2` giới hạn Gradle worker capacity cho invocation hiện tại. Không có nghĩa chắc chắn **chỉ hai OS processes** tồn tại: Daemon, client, compiler/test forks và các công cụ ngoài có lifecycle riêng; workers là giới hạn lập lịch của Gradle, không phải bộ đếm tiến trình tuyệt đối của cả hệ thống.

Giá trị `N` thường được chọn dựa trên **CPU cores có thể dùng, RAM và tính chất task**. Không chọn `--max-workers=32` trên container 2 vCPU chỉ vì máy host có 32 cores. Trong container, quotas/cgroups và memory limits quan trọng hơn cấu hình phần cứng của host.

### Khi parallelism phản tác dụng

- Chỉ có 2 GB RAM khả dụng nhưng khởi chạy nhiều JVM test, compiler và Daemon.
- Nhiều task cùng đọc/ghi vào một ổ đĩa chậm, gây I/O contention.
- Các task có hidden shared outputs, cùng ghi một file/cache không được khai báo.
- Test suites dùng chung fixed port, database schema hoặc thư mục tạm.
- Annotation processors/code generators không an toàn khi chạy đồng thời.
- CI runner vừa build vừa khởi chạy Docker containers chiếm bộ nhớ lớn.

Khi gặp lỗi khó tái hiện, thử **`--no-parallel --max-workers=1`** và giảm test forks để cô lập vấn đề. Tuy nhiên với configuration cache ở các phiên bản Gradle mới, `--no-parallel` không nhất thiết tắt mọi khả năng parallel task execution; lỗi race cuối cùng vẫn cần sửa dependency/input/output hoặc bảo vệ shared resources, không chỉ dựa vào việc buộc build tuần tự.

## 6. Bài thực hành: đo tác động của Daemon, heap và hai worker slots

Ví dụ Spring Boot này có ba subproject:

- `:alpha` — thư viện Java trả về chữ `FAST`.
- `:beta` — thư viện Java trả về chữ `BUILD`.
- `:app` — Spring Boot command-line app dùng cả hai module, tạo executable JAR.

Hai module library **độc lập**, vì thế Gradle có cơ hội chạy phần build của chúng đồng thời khi bật project parallelism. App phụ thuộc cả hai nên Gradle vẫn bảo toàn quan hệ build.

### 6.1. Cấu trúc

~~~text
daemon-parallel-demo/
├── settings.gradle
├── gradle.properties
├── alpha/
│   ├── build.gradle
│   └── src/main/java/com/example/alpha/AlphaWord.java
├── beta/
│   ├── build.gradle
│   └── src/main/java/com/example/beta/BetaWord.java
└── app/
    ├── build.gradle
    └── src/main/java/com/example/app/DaemonParallelApplication.java
~~~

Wrapper files (`gradlew`, `gradlew.bat`, `gradle/wrapper/...`) được tạo hoặc bổ sung sau nếu chưa có; chúng không cần đặt trong ba subprojects.

### 6.2. Root `settings.gradle`

~~~groovy
rootProject.name = 'daemon-parallel-demo'
include 'alpha', 'beta', 'app'
~~~

Lệnh `include` khai báo subprojects tham gia một build. Dependencies giữa chúng được khai báo sau trong `app/build.gradle`. Root `build.gradle` **không bắt buộc** trong ví dụ này.

### 6.3. Root `gradle.properties`

~~~properties
# Giá trị thử nghiệm, KHÔNG phải cấu hình tối ưu cho mọi máy.
org.gradle.daemon=true
org.gradle.jvmargs=-Xmx1g -XX:MaxMetaspaceSize=384m -Dfile.encoding=UTF-8
org.gradle.parallel=true
org.gradle.workers.max=2
~~~

Tại sao dùng `2`? Để quan sát hai library modules có thể chạy đồng thời và giữ yêu cầu tài nguyên ở mức vừa phải cho demo. Trên CI rất ít RAM hoặc CPU, `workers.max=1` có thể phù hợp hơn; trên máy nhiều CPU/RAM, có thể thử giá trị lớn hơn. Khi sửa file này, chạy lại đúng lệnh để Gradle chọn Daemon tương thích mới nếu JVM arguments đã thay đổi.

### 6.4. `alpha/build.gradle`

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

### 6.5. `alpha/src/main/java/com/example/alpha/AlphaWord.java`

~~~java
package com.example.alpha;

public final class AlphaWord {
    private AlphaWord() {
    }

    public static String value() {
        return "FAST";
    }
}
~~~

### 6.6. `beta/build.gradle`

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

### 6.7. `beta/src/main/java/com/example/beta/BetaWord.java`

~~~java
package com.example.beta;

public final class BetaWord {
    private BetaWord() {
    }

    public static String value() {
        return "BUILD";
    }
}
~~~

Các file Java library không cần Spring annotation. `java-library` cung cấp output/variants tiêu thụ qua project dependency; cả hai thư viện không có dependency đến nhau.

### 6.8. `app/build.gradle`

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation project(':alpha')
    implementation project(':beta')
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.app.DaemonParallelApplication'
}

tasks.named('bootJar', BootJar) {
    archiveFileName.set('daemon-parallel-demo.jar')
}
~~~

**Giải thích:**

1. Boot plugin chỉ áp dụng ở **app**, vì `alpha` và `beta` là plain Java libraries.
2. `implementation project(':alpha')` và `implementation project(':beta')` làm Gradle liên kết classpath/producer tasks, không cần copy JAR bằng tay.
3. Khi chạy `:app:bootJar`, Gradle biết cần output của `alpha` và `beta`; parallelism không được phép phá thứ tự dependency.
4. `spring-boot-starter` đủ cho command-line Spring Boot app, không tạo HTTP server.
5. `archiveFileName` tạo path artifact xác định để dễ smoke test.

### 6.9. `app/src/main/java/com/example/app/DaemonParallelApplication.java`

~~~java
package com.example.app;

import com.example.alpha.AlphaWord;
import com.example.beta.BetaWord;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DaemonParallelApplication {

    public static void main(String[] args) {
        SpringApplication.run(DaemonParallelApplication.class, args);
    }

    @Bean
    CommandLineRunner showResult() {
        return args -> System.out.println(
                "BUILD_RESULT=" + AlphaWord.value() + "-" + BetaWord.value());
    }
}
~~~

File Java sử dụng class của hai subprojects; nếu thiếu project dependencies, compiler ở `:app` sẽ báo không resolve được imports. Đây là bằng chứng đơn giản rằng build graph và runtime classpath có ý nghĩa.

### 6.10. Chạy và kiểm tra output

Nếu project đã có Gradle Wrapper version tương thích (ví dụ Gradle 8.7), từ build root trên Linux/macOS:

~~~bash
./gradlew projects
./gradlew :app:bootJar --parallel --max-workers=2
~~~

Lệnh đầu cho thấy `:alpha`, `:beta` và `:app` thuộc build. Lệnh thứ hai build executable JAR với tối đa hai worker slots. Output file được cấu hình là:

~~~text
app/build/libs/daemon-parallel-demo.jar
~~~

Chạy đúng artifact:

~~~bash
java -jar app/build/libs/daemon-parallel-demo.jar \
  --spring.main.banner-mode=off \
  --logging.level.root=OFF
~~~

Dấu backslash ở cuối dòng là cú pháp nối dòng **Linux/macOS shell**; Windows PowerShell nên viết lệnh `java -jar` trên một dòng. Dòng do ứng dụng in, nếu build và startup thành công:

~~~text
BUILD_RESULT=FAST-BUILD
~~~

Startup logs phụ thuộc môi trường; dòng trên chỉ là marker từ `CommandLineRunner`.

Không cần chạy `:alpha:jar` hoặc `:beta:jar` bằng tay trước `:app:bootJar`; Gradle project dependencies tạo task dependencies cần thiết.

### 6.11. So sánh song song và tuần tự

Chạy một bản đối chứng để quan sát sự khác nhau:

~~~bash
./gradlew :app:bootJar --no-parallel --max-workers=1 --info
./gradlew :app:bootJar --parallel --max-workers=2 --info
~~~

**Không kết luận tốc độ từ hai lần chạy trên cùng output đã UP-TO-DATE**. Lần chạy đầu có thể download dependencies, lần sau chỉ kiểm tra inputs; khác biệt thời gian khi đó không phản ánh riêng parallelism. Để kiểm tra task scheduling rõ hơn, có thể dùng `--dry-run`:

~~~bash
./gradlew :app:bootJar --parallel --max-workers=2 --dry-run
~~~

`--dry-run` không thực thi actions, không sinh artifact; nó chỉ giúp xem graph đã chọn. Muốn đo performance thực, cần cùng workload, cùng cache state/inputs, có lặp lại và đo đạc hợp lệ ở phần 9.

Nếu muốn không lặp lại build script khi điều chỉnh, `--no-parallel` và `--max-workers=1` là flags thử nghiệm có thể override giá trị root `gradle.properties` cho invocation tương ứng.

## 7. Thêm cấu hình cho test/bootRun một cách có chủ đích

Ví dụ ở phần 6 không có unit test source, vì vậy task `test` có thể `NO-SOURCE`. Nếu dự án Spring Boot thực tế có test suites, bạn có thể thêm **đoạn riêng** sau vào `app/build.gradle`:

~~~groovy
tasks.withType(Test).configureEach {
    maxHeapSize = '512m'
    maxParallelForks = 1
}
~~~

Sau khi test isolation đủ tốt và RAM cho phép, thử `maxParallelForks=2` rồi đo thời gian và memory. Không thêm vô hạn test forks chỉ vì `org.gradle.workers.max` đang lớn; các JVM test đều có overhead, và integration tests với embedded servers/database có thể ăn RAM hơn nhiều unit tests.

Nếu muốn đo JVM ứng dụng của `bootRun` độc lập:

~~~groovy
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named('bootRun', BootRun) {
    jvmArgs '-Xmx512m'
}
~~~

Đây là **đoạn tùy chọn** trong `app/build.gradle`; không cần thêm để build `bootJar`. Sau đó:

~~~bash
./gradlew :app:bootRun --args='--spring.main.banner-mode=off --logging.level.root=OFF'
~~~

Ứng dụng vẫn in `BUILD_RESULT=FAST-BUILD`, còn giới hạn heap của JVM do `bootRun` khởi động là một thiết lập riêng. `org.gradle.jvmargs` ở root vẫn điều khiển build/daemon JVM.

## 8. Tính ngân sách RAM cho cả build, không chỉ `-Xmx`

Giả sử CI runner được cấp 4 GiB RAM; dự án dùng:

~~~text
Daemon -Xmx1g
2 JVM test, mỗi JVM -Xmx512m
1 compiler process có thể fork khi được cấu hình
Kotlin daemon hoặc annotation processor (nếu có)
Native/metaspace/threads/code cache/direct buffers của mọi JVM
Gradle client, OS, container agent và services phụ trợ
~~~

Tổng **heap tối đa được phép** của Daemon và hai JVM test đã khoảng **2 GiB**, nhưng **tổng resident memory có thể lớn hơn đáng kể** vì overhead và các tiến trình khác. Không thể kết luận “4 GiB còn dư 2 GiB” mà không đo.

Một cách lập ngân sách:

1. Ghi giới hạn RAM thực của host/container, không dùng total RAM của machine host nếu build chạy dưới cgroup.
2. Liệt kê các process có thể hoạt động đồng thời: Daemon, Test forks, compiler/worker, Kotlin daemon, Docker/database.
3. Dành headroom cho metaspace, native memory, thread stacks, OS và agent.
4. Chọn số worker slots và fork count sao cho **peak memory** có thể chịu được.
5. Tăng parallelism từng nấc nhỏ trong khi theo dõi peak RSS, GC và build duration.

### Hai trường hợp thường gặp

**CPU còn rảnh, RAM còn nhiều, có nhiều subprojects độc lập:** thử `--parallel` và tăng `--max-workers` từ 1 → 2 → 4, đo xem có rút ngắn critical path không.

**CPU 100%, RAM thấp, swap/GC nhiều:** giảm workers hoặc test forks trước khi tiếp tục tăng heap. Nếu một JVM thực sự thiếu heap, chỉ tăng heap đúng JVM đó sau khi tạo headroom ở tổng hệ thống.

### Khi CI chạy nhiều jobs đồng thời

`org.gradle.workers.max=4` áp dụng **trong một Gradle invocation**. Nếu CI chạy ba build jobs cùng lúc trên một runner, giới hạn mỗi build không tự trở thành giới hạn tổng 4 workers cho cả ba. Quản lý **CI concurrency**, memory limits và Gradle worker settings cùng nhau.

Tương tự, laptop chạy hai terminal `./gradlew build` song song có thể có một hoặc nhiều Daemon/build JVMs tùy compatibility/trạng thái. Dùng `./gradlew --status` và công cụ OS để xem số tiến trình thực tế.

## 9. Đo tối ưu hóa một cách công bằng

Tăng tốc không thể được đánh giá bằng “lần này nhanh hơn lần trước” nếu workload đã thay đổi. Dùng một quy trình đơn giản:

### Bước 1 — Chọn đúng workload

- `./gradlew help`: đo configuration/startup overhead, không đại diện compile/test/packaging.
- `./gradlew :app:compileJava`: tập trung compile app và producer tasks liên quan.
- `./gradlew :app:test`: tập trung test JVM và parallel forks.
- `./gradlew :app:bootJar`: đo packaging và runtime dependency assembly.
- `./gradlew build`: tổng build pipeline với task graph thực tế.

Không so sánh `help` ở cấu hình A với `bootJar` ở cấu hình B.

### Bước 2 — Kiểm soát biến số

Đối với mỗi cặp thử:

- Dùng cùng Gradle Wrapper, Java version, source revision, dependency versions và máy/runner.
- Ghi lại Daemon warm/cold state, số JVM đang chạy và CPU/RAM có sẵn.
- Ghi rõ build cache, configuration cache và incremental build đang bật hay không.
- Không để lần đầu download dependencies còn lần sau không download rồi quy khác biệt cho `--parallel`.
- Chỉ đổi **một nhóm biến mỗi lần**: Daemon on/off, `-Xmx`, max-workers hoặc test forks.
- Lặp lại nhiều lần, bỏ qua hoặc báo riêng warm-up, lấy **median** thay vì chọn một lần may mắn.

### Bước 3 — Dùng Gradle reports/logs

~~~bash
./gradlew :app:bootJar --profile
./gradlew :app:bootJar --info
./gradlew :app:bootJar --stacktrace
~~~

- `--profile` tạo một HTML performance profile trong `build/reports/profile/` (vị trí chính xác theo Gradle/build layout); xem configuration time, tasks và các phần chi phí nổi bật.
- `--info` bổ sung thông tin vì sao tasks chạy hoặc bị `UP-TO-DATE`; log dài, không mặc định dùng trong mọi CI job.
- `--stacktrace` hữu ích khi gặp exception, **không** phải thước đo performance.
- Gradle có công cụ **Build Scan/Develocity** để phân tích bottlenecks chi tiết, nhưng `--scan` có thể tải dữ liệu build/environment lên một dịch vụ bên ngoài; cần tuân thủ chính sách bảo mật của tổ chức trước khi dùng.

Trong Gradle 9.x, **Configuration Cache** có thể đem tới một mô hình parallel task scheduling mạnh hơn; nếu so sánh các phiên bản, ghi rõ cấu hình cache đang dùng. Đừng tuyên bố `--no-parallel` đã bắt buộc mọi task chạy tuần tự nếu phiên bản/chế độ đang hoạt động không bảo đảm điều đó.

### Bước 4 — Quan sát bộ nhớ đúng process

Với JDK tools:

~~~bash
jps -lv
~~~

Tìm process `GradleDaemon`, test workers, Kotlin daemon hoặc các Java processes khác. PID và số tiến trình phụ thuộc thời điểm. Có thể kiểm tra JVM flags trên một **PID đã xác định**:

~~~bash
jcmd <PID> VM.flags
~~~

`<PID>` là placeholder cần thay bằng PID thật, không nhập dấu `<...>` trong shell khi chạy lệnh. Nếu quyền truy cập hoặc JVM version không tương thích, `jcmd` có thể báo lỗi. Trên Windows dùng Task Manager/Process Explorer; trên Linux/macOS có `top`/`ps` để xem resident memory. Đọc trực tiếp `max heap` của JVM nào thì mới biết giới hạn của **JVM đó**.

Heap dump/JFR/JVM diagnostics có thể chứa stack, đường dẫn và dữ liệu nhạy cảm; không công khai chúng nếu chưa được phép.

### Bước 5 — Ghi lại phép đo

Một bảng quyết định có thể dùng:

| Run | Daemon | `-Xmx` | Workers | Test forks | Workload | Median time | Peak RAM |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | On | 512m | 1 | 1 | `:app:build` | Đo thực tế | Đo thực tế |
| B | On | 1g | 1 | 1 | `:app:build` | Đo thực tế | Đo thực tế |
| C | On | 1g | 2 | 1 | `:app:build` | Đo thực tế | Đo thực tế |
| D | On | 1g | 2 | 2 | `:app:build` | Đo thực tế | Đo thực tế |

Đây là **template thí nghiệm**, không phải benchmark số liệu có thật. Chỉ chọn cấu hình sau khi điền đo đạc cùng workload/cache state và xác nhận tests không trở nên flaky.

## 10. Quan hệ với các cơ chế tối ưu khác

Daemon, heap và parallelism không thay thế các tối ưu Gradle về **tránh công việc không cần thiết**:

| Cơ chế | Tối ưu điều gì? | Có liên quan ba nhóm setting? |
| --- | --- | --- |
| **Up-to-date checks** | Bỏ task khi inputs/outputs không đổi | Giảm việc cần scheduler chạy |
| **Incremental compilation** | Chỉ biên dịch phần bị ảnh hưởng | Giảm tải CPU/heap |
| **Build Cache** | Dùng lại task outputs theo input fingerprints | Giảm số task phải thực thi |
| **Configuration Cache** | Dùng lại trạng thái configuration, task graph | Có thể giảm configuration time và thay đổi khả năng chạy task song song |
| **Configuration avoidance** | Không tạo/configure task không cần thiết | Giảm chi phí configuration/heap |
| **Parallel project execution** | Chạy nhiều việc độc lập đồng thời | Tăng throughput nhưng dùng nhiều RAM/CPU |
| **Gradle Daemon** | Tái sử dụng build JVM và trạng thái trong memory | Giảm startup/warm-up overhead |

Ví dụ các lệnh kiểm tra độc lập:

~~~bash
./gradlew :app:bootJar --build-cache
./gradlew :app:bootJar --configuration-cache
~~~

Đừng bật hàng loạt mọi option vào production build khi plugins chưa tương thích, bởi lỗi configuration cache có thể cần refactor build logic hoặc task actions. Với Gradle phiên bản mới, một số behavior và default có thể thay đổi; hãy đối chiếu tài liệu **đúng phiên bản wrapper** của project.

**Về parallelism trong configuration cache:** Gradle hiện đại có thể thực thi tasks song song ngay trong cùng project khi cấu hình cache bảo đảm cô lập state; lúc đó `--parallel` riêng lẻ không phải tín hiệu đầy đủ về concurrency. Thiết kế task inputs/outputs và shared-state coordination đúng vẫn quan trọng hơn tắt/bật một cờ.

## 11. Sự cố thường gặp: nguyên nhân và hướng giải quyết

| Triệu chứng | Giải thích có khả năng | Bước tiếp theo |
| --- | --- | --- |
| `Gradle Daemon disappeared unexpectedly` | Daemon crash, OS/cgroup kill, Java crash hoặc vấn đề môi trường | Xem Daemon log, OS/container OOM events, heap/native memory |
| `OutOfMemoryError: Java heap space` trong Daemon | Heap của build process thiếu hoặc build logic/plugin giữ quá nhiều object | Điều chỉnh `org.gradle.jvmargs` sau khi xác định PID; profile logic |
| `OutOfMemoryError: Metaspace` | Class metadata vượt giới hạn metaspace | Kiểm tra plugin/classloader churn, giới hạn metaspace |
| `OutOfMemoryError` trong test worker | JVM test thiếu heap hoặc fork count quá lớn | `Test.maxHeapSize`, `maxParallelForks` và test allocations |
| `bootRun` thiếu RAM | JVM ứng dụng được bootRun fork có giới hạn riêng | `BootRun.jvmArgs`, kiểm tra app allocations |
| `java -jar` production OOM | JVM production/container memory | Điều chỉnh runtime memory, không chỉ `gradle.properties` |
| `Cannot allocate memory` / OS kill | Tổng heap+native memory+quá nhiều workers/processes | Giảm concurrency, tính memory budget |
| Nhiều Daemon xuất hiện | Gradle/JDK/JVM args khác, daemon bận hoặc IDE/tooling yêu cầu khác | `--status`, kiểm tra JDK/Gradle version và JVM args |
| `--no-daemon` vẫn thấy JVM dùng một lần | Gradle cần JVM settings khác client | Đọc thông báo single-use Daemon; không nhầm với Daemon giữ lâu |
| Thời gian build không cải thiện với `--parallel` | Task graph tuyến tính, ít subprojects độc lập, CPU/IO đã đầy | Xem critical path và profile; so benchmark hợp lệ |
| Chạy parallel làm test thất bại ngẫu nhiên | Tests/shared outputs/ports không được cô lập | Sửa isolation/dependencies; giới hạn forks khi chẩn đoán |
| `--max-workers=8` làm CI chậm | Quá nhiều workers tranh CPU/RAM/disk | Hạ xuống 2/4/1 theo đo đạc |
| Config memory sửa rồi thấy JVM cũ | Daemon đang reuse theo settings khác hoặc đo nhầm process | Xem compatibility/PID; `--stop` để chẩn đoán |
| `JAVA_OPTS=-Xmx4g` nhưng Gradle không dùng 4 GiB | JAVA_OPTS thường là client JVM | Đặt `org.gradle.jvmargs` cho Daemon |
| Java 17 toolchain nhưng Daemon chạy JDK khác | Toolchain và Daemon JVM được chọn độc lập | Kiểm tra Gradle JVM criteria/JAVA_HOME/org.gradle.java.home |
| Profile nhanh vì task `UP-TO-DATE` | Không thực sự đo heavy task execution | Chuẩn hóa cache state và lặp benchmark |
| `--scan` bị chính sách công ty chặn | Công cụ có thể gửi dữ liệu build ra ngoài | Dùng `--profile` hoặc công cụ được phép trong tổ chức |

### Một lỗi phân tích hay gặp: “Tăng heap thì build nhanh hơn chắc chắn”

Không phải luôn đúng. Nếu trước đó Daemon GC quá nhiều vì heap thiếu, tăng hợp lý có thể giúp. Nhưng trên máy thiếu RAM, tăng heap còn khiến OS swap và làm chậm mọi process. Nếu build bottleneck ở download, compiler CPU hoặc test database, heap Daemon gần như không giải quyết gốc rễ.

### Một lỗi khác: “Có 8 cores thì `workers.max=8` luôn tốt”

Không. Với tasks phần lớn cần RAM hoặc I/O, 8 concurrent workers có thể làm throughput **giảm**. Nếu app test fork nhiều JVM với các web servers thật, giới hạn RAM và tài nguyên shared có thể quan trọng hơn CPU. Bắt đầu từ mức bảo thủ, đo rồi tăng.

## 12. Gợi ý cấu hình theo bối cảnh

Các ví dụ dưới đây là **điểm xuất phát có thể thử**, không phải quyết định tối ưu đã được benchmark:

### Máy học tập hoặc laptop RAM khiêm tốn

~~~properties
org.gradle.daemon=true
org.gradle.jvmargs=-Xmx768m -XX:MaxMetaspaceSize=384m
org.gradle.parallel=false
org.gradle.workers.max=1
~~~

Hữu ích để ưu tiên ổn định khi nhiều ứng dụng khác đang sử dụng RAM. Nếu build lớn bị heap pressure thật, cần điều chỉnh. `parallel=false` không bảo đảm test forks bị giới hạn nếu task test được cấu hình riêng.

### Máy developer có nhiều module và tài nguyên vừa đủ

~~~properties
org.gradle.daemon=true
org.gradle.jvmargs=-Xmx1g -XX:MaxMetaspaceSize=512m
org.gradle.parallel=true
org.gradle.workers.max=2
~~~

Đây là cấu hình khởi đầu đơn giản cho parallel project build; đo xem cores/RAM có được tận dụng tốt không trước khi tăng worker count.

### CI runner có giới hạn RAM nghiêm ngặt

~~~properties
org.gradle.daemon=true
org.gradle.jvmargs=-Xmx1g -XX:MaxMetaspaceSize=384m
org.gradle.parallel=true
org.gradle.workers.max=2
~~~

Cùng các giá trị nhìn có vẻ giống developer, nhưng CI cần tính thêm concurrent jobs, test forks, Docker services và memory limit. Runner 2 vCPU/4 GiB RAM có thể buộc `workers.max=1` và giảm test forks. **Không** sao chép config chỉ từ tổng RAM của host.

### Với CI ngắn hạn nên tắt Daemon không?

Không có câu trả lời một cờ cho tất cả. Với container/agent sống rất ngắn, Daemon không được reuse qua nhiều builds nên lợi ích warm-up giữa các lần nhỏ hơn. Tuy nhiên Gradle có thể vẫn dùng một single-use JVM để đáp ứng requirements và Daemon thường mang lại tối ưu trong chính build. Thử nghiệm on/off trên loại runner thật, không lấy máy developer làm đại diện.

## 13. Checklist trước khi chốt tối ưu build

1. **Dùng Gradle Wrapper cố định version** và JDK tương thích. Không so lệnh của hai Gradle versions mà không ghi nhận.
2. **Xác định lỗi/chỗ chậm nằm ở đâu**: configuration, compile, test, packaging, daemon startup, download hay environment.
3. **Xác định JVM/process liên quan** rồi mới sửa heap: Daemon khác test worker, `bootRun` và production.
4. **Bắt đầu bằng một memory budget thực tế** cho cgroup/CI runner, có headroom native/OS.
5. **Bật Daemon để tận dụng reuse** trừ khi có lý do/đo đạc rõ cần tắt.
6. **Chọn worker count vừa phải** và chỉ bật parallel khi có công việc độc lập đáng kể.
7. **Xem test forks riêng** và bảo đảm isolation khi tăng parallelism.
8. **Giữ dependency/task graph đúng**, khai báo inputs/outputs, không dựa vào thứ tự tình cờ.
9. **Đo từng thay đổi với workload đồng nhất**, tách cold/warm cache, lặp lại và xem peak RAM.
10. **Giữ an toàn thông tin** với heap dumps, logs, Build Scans; không công khai dữ liệu build nội bộ.
11. **Xác nhận artifact Spring Boot chạy được** bằng `java -jar` sau build, vì tăng tốc build nhưng tạo archive sai không phải tối ưu thành công.
12. **Ghi lại cấu hình đã được kiểm chứng**, điều kiện máy/runner và lý do lựa chọn để người khác không phải thử lại từ đầu.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `org.gradle.jvmargs=-Xmx2g` có làm `java -jar app.jar` ở production dùng heap 2 GiB không?

**Trả lời:** Không. Property này điều khiển JVM chạy Gradle build/Daemon. Runtime production nhận JVM arguments riêng từ lệnh chạy/container/environment.

**Câu 2.** `JAVA_OPTS=-Xmx4g` có đủ để đảm bảo Gradle Daemon dùng 4 GiB không?

**Trả lời:** Không trong mô hình Daemon thông dụng. `JAVA_OPTS` điều khiển client JVM; đặt `org.gradle.jvmargs` cho build/Daemon JVM.

**Câu 3.** Tại sao `--no-daemon` đôi khi vẫn tạo một process dạng Daemon?

**Trả lời:** Khi client JVM settings không đáp ứng yêu cầu của build, Gradle có thể tạo một **single-use Daemon** rồi dừng sau build, thay vì dùng một Daemon tái sử dụng lâu dài.

**Câu 4.** Một build có `--parallel --max-workers=8` luôn chạy nhanh hơn `--max-workers=2` không?

**Trả lời:** Không. Phụ thuộc số tasks độc lập, CPU, RAM, I/O, lock/shared resources và test fork count. Phải đo trên workload thật.

**Câu 5.** Vì sao `org.gradle.parallel=true` có ích trong multi-project build mà không chắc có ích với single-project?

**Trả lời:** Parallel project execution cho phép thực thi tasks từ **những projects độc lập** cùng lúc, trong khi single-project có thể thiếu cơ hội đó. Các chế độ configuration cache mới có semantics parallel khác, nên phải xem đúng Gradle version/mode.

**Câu 6.** Test bị `OutOfMemoryError` nhưng Daemon chưa đầy heap; chỉnh gì trước?

**Trả lời:** Xác định JVM test bị lỗi, thử `Test.maxHeapSize` phù hợp hoặc giảm `maxParallelForks`; đồng thời kiểm tra leak và RAM tổng. Không tự tăng heap Daemon.

**Câu 7.** `org.gradle.workers.max=2` có giới hạn tổng số JVM trên toàn máy thành 2 không?

**Trả lời:** Không. Đó là giới hạn năng lực worker trong một Gradle build; còn client, daemon, các process được fork và các build/CI jobs khác có thể tồn tại đồng thời.

**Câu 8.** Khi đổi `-Xmx`, vì sao có Daemon mới?

**Trả lời:** JVM không đổi max heap sau khi đã chạy; Daemon có JVM arguments khác không tương thích với yêu cầu mới, nên Gradle có thể khởi tạo Daemon tương ứng.

**Câu 9.** Cần đo gì để kết luận tăng workers thực sự tốt hơn?

**Trả lời:** Median build duration cho cùng task/workload, peak RSS/container memory, CPU saturation, I/O contention, GC và độ ổn định tests; loại bỏ sự khác biệt cache/download không liên quan.

**Câu 10.** Một test suite flaky chỉ khi bật parallel; có nên vô hiệu hóa parallel vĩnh viễn không?

**Trả lời:** Có thể giới hạn để ổn định tạm thời, nhưng cần xử lý shared filesystem, fixed ports, database/test data và task dependencies. Parallel chỉ làm lộ race condition vốn có.

## 15. Tài liệu chính thức

- Gradle — [Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): Client/Daemon JVM, reuse, `--status`, `--stop`, single-use Daemon và JVM criteria.
- Gradle — [Configuring Gradle](https://docs.gradle.org/current/userguide/config_gradle.html): `org.gradle.jvmargs`, `JAVA_OPTS` và ví dụ JVM heap.
- Gradle — [Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): `org.gradle.parallel`, `org.gradle.workers.max`, `org.gradle.java.home` và properties.
- Gradle — [Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--parallel`, `--max-workers`, `--profile` và Daemon flags.
- Gradle — [Improve the Performance of Gradle Builds](https://docs.gradle.org/current/userguide/performance.html): worker/parallelism, bottlenecks và profiling.
- Gradle — [Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `Test.maxHeapSize`, `maxParallelForks` và test worker JVM.
- Gradle — [Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): cache configuration và parallel task execution ở chế độ cache.
- Gradle — [Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): độc lập giữa modules, task/dependency graph.
- Spring Boot — [Gradle Plugin: Packaging](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html): `bootJar` và packaging artifact.
- Spring Boot — [Gradle Plugin: Running](https://docs.spring.io/spring-boot/gradle-plugin/running.html): `bootRun` và JVM/application arguments.

**Ghi nhớ:** Gradle Daemon giúp tránh khởi động JVM build lặp lại, `org.gradle.jvmargs` giới hạn bộ nhớ **đúng JVM build**, còn `--parallel` và `--max-workers` điều tiết **lượng công việc chạy đồng thời**. Tối ưu hiệu quả là **đo đúng process, dành đủ headroom, tăng concurrency có kiểm soát và kiểm chứng build + executable Spring Boot archive**, không phải cố tăng mọi con số.
