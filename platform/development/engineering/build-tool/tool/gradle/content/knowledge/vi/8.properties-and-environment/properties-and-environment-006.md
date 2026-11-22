# Cấu hình JVM của Gradle và JVM của tiến trình do task khởi chạy

## 1. Mục tiêu: biết JVM nào nhận cấu hình nào

Một build Gradle chạy trên Java có thể có nhiều JVM cùng tồn tại. Nếu chỉ thấy một tham số `-Xmx` rồi tăng giá trị, bạn rất dễ sửa nhầm tiến trình: Gradle Daemon có thể chạy ổn nhưng test vẫn `OutOfMemoryError`; hoặc test được cấp nhiều bộ nhớ nhưng Gradle vẫn hết heap khi cấu hình project.

Sau bài này, bạn cần phân biệt được:

1. **Gradle Client JVM**: tiến trình Java bắt đầu từ lệnh `./gradlew` hoặc `gradlew.bat`; khởi tạo và giao tiếp với build.
2. **Gradle Daemon JVM (build JVM)**: tiến trình thực hiện configuration và điều phối execution của build, thường được tái sử dụng giữa các lần gọi.
3. **Task JVM**: JVM con do một task tạo ra, thường gặp với `Test`, `JavaExec`, các compiler/worker forked hoặc công cụ ngoài.
4. **Java toolchain**: chọn bản JDK/công cụ `javac` hoặc `java` cho một loại công việc hay task; không mặc nhiên quyết định JVM đang chạy Gradle.
5. **Thông số heap/JVM args/system property/environment**: mỗi nhóm có phạm vi, cách truyền và độ ưu tiên riêng.

Trong ví dụ, dùng **Gradle Wrapper của dự án** và **Groovy DSL** (`build.gradle`). Mã Java minh họa theo Java 17. Những giá trị như 2 GiB/256 MiB là số học tập; cấu hình thực tế cần cân đối theo RAM, CPU, container, plugin và lượng công việc.

## 2. Sơ đồ một lần chạy Gradle

~~~text
Terminal / CI / IDE
    |
    |  ./gradlew test
    v
gradlew / gradlew.bat  --->  Java khởi động Wrapper + Client JVM
                                     |
                                     |  tìm/khởi động Gradle Daemon tương thích
                                     v
                            Gradle Daemon JVM
                          (đọc settings/build.gradle,
                           cấu hình task, lên lịch công việc)
                                     |
                        +------------+-------------+
                        |                          |
                        v                          v
                 Test task                    JavaExec task
              JVM test forked                JVM app forked
                  (-Xmx)                        (-Xmx,
                                               -D, env, args)
                        |                          |
                        +------------+-------------+
                                     |
                       Kết quả/log gửi về Gradle
~~~

Sơ đồ là trường hợp điển hình. Một vài tác vụ biên dịch hoặc plugin có thể chạy trong daemon, dùng compiler daemon riêng, dùng Gradle Worker API, hoặc khởi chạy công cụ ngoài; không nên giả định **mọi** task đều fork JVM. Ngược lại, task Java `Test` và `JavaExec` điển hình có JVM riêng khi chúng thực thi.

| Đối tượng | Nhiệm vụ | Nguồn chọn JDK/JVM phổ biến | Nguồn heap/JVM args phổ biến |
| --- | --- | --- | --- |
| Gradle Client | Launcher, giao tiếp CLI/daemon | `JAVA_HOME` hoặc `java` trong `PATH`/IDE | `JAVA_OPTS`, `GRADLE_OPTS` dùng cho client |
| Gradle Daemon | Chạy configuration và điều phối build | Daemon JVM criteria; `org.gradle.java.home`; mặc định từ môi trường Client | `org.gradle.jvmargs` |
| `Test` task | Chạy test trong tiến trình forked | Java toolchain hoặc `Test.javaLauncher` | `maxHeapSize`, `minHeapSize`, `jvmArgs`, `systemProperty` |
| `JavaExec` task | Chạy main class trong JVM mới | Toolchain/`JavaExec.javaLauncher` | Cùng nhóm `JavaForkOptions` với `Test` |
| `JavaCompile`/compiler | Biên dịch Java; cách thực thi tùy thiết lập | `java.toolchain`/`javaCompiler` | `options.fork` và `options.forkOptions` khi dùng compiler fork |
| Gradle Worker API | Work action; có thể dùng thread, classloader hoặc JVM riêng | Worker isolation và JVM cấu hình cho worker | `processIsolation { forkOptions { ... } }` khi fork process |

**Kết luận thao tác:** muốn sửa lỗi của tiến trình nào thì tìm nơi cấu hình tiến trình đó; không lấy tên flag giống nhau làm bằng chứng chúng ảnh hưởng cùng một JVM.

## 3. JVM khởi động Gradle: `JAVA_HOME`, `PATH` và Client VM

Script `gradlew`/`gradlew.bat` cần tìm chương trình Java để chạy Wrapper và Client. Trên terminal, thông thường nó dựa trên:

- `JAVA_HOME` nếu được đặt đúng tới thư mục JDK/JRE phù hợp (Java của Gradle phiên bản đó phải tương thích).
- `java` tìm được trong `PATH` nếu không có `JAVA_HOME`.
- IDE/Tooling API có thể chọn một JDK khác terminal.

Trên Linux/macOS:

~~~bash
echo "$JAVA_HOME"
java -version
./gradlew --version
~~~

Trên Windows PowerShell:

~~~powershell
$env:JAVA_HOME
java -version
.\gradlew.bat --version
~~~

Hai kết quả `java -version` và `./gradlew --version` có thể khác nhau nếu Gradle Daemon chạy bằng JDK khác Client hoặc IDE có cấu hình riêng. `./gradlew --version` cho biết bản Gradle/JVM mà lệnh báo cáo, nhưng để biết một task cụ thể đang dùng JVM nào cần quan sát task hoặc công cụ chẩn đoán chuyên biệt.

### 3.1. `JAVA_OPTS` và `GRADLE_OPTS` tác động đến đâu?

Hai biến sau thường được launcher Gradle áp dụng khi khởi động **Client VM**:

~~~bash
export JAVA_OPTS="-Xmx128m"
export GRADLE_OPTS="-Dfile.encoding=UTF-8"
./gradlew help
~~~

Đây là ví dụ Unix; không khuyến nghị mọi dự án tự thay biến toàn hệ thống. Tăng `JAVA_OPTS=-Xmx2g` **không có nghĩa** Gradle Daemon được cấp heap 2 GiB, và cũng không tự đổi heap của `Test` hay `JavaExec`.

`GRADLE_OPTS` có thể truyền một **system property Gradle** như `-Dorg.gradle.jvmargs=...` để yêu cầu cấu hình cho Daemon; đó là cơ chế khác với JVM flag của Client. Để dự án dễ tái lập, hãy đặt thiết lập của Daemon trong `gradle.properties` khi phù hợp.

**Cẩn thận với `JAVA_TOOL_OPTIONS` hoặc `JDK_JAVA_OPTIONS`**: đây là biến được JVM launcher/JDK xử lý và có thể được tiến trình forked kế thừa. Chúng khác `JAVA_OPTS`/`GRADLE_OPTS`. Nếu JVM con xuất hiện tham số ngoài mong đợi, kiểm tra biến môi trường được kế thừa trước khi cho rằng Gradle đã chuyển tự động `org.gradle.jvmargs` sang task.

## 4. Cấu hình JVM của Gradle Daemon bằng `gradle.properties`

Đặt trong `gradle.properties` ở root project, hoặc theo chính sách tổ chức tại Gradle User Home:

~~~properties
# gradle.properties -- minh họa cho Gradle Daemon
org.gradle.jvmargs=-Xms256m -Xmx2g -XX:MaxMetaspaceSize=512m -Dfile.encoding=UTF-8
org.gradle.daemon=true
org.gradle.workers.max=2
org.gradle.parallel=false
~~~

Giải thích:

- `-Xms256m`: heap khởi tạo của **build JVM**.
- `-Xmx2g`: giới hạn heap tối đa của **build JVM**.
- `-XX:MaxMetaspaceSize=512m`: giới hạn metaspace JVM đó, **không phải** thêm 512 MiB vào Xmx theo cùng một quỹ heap.
- `-Dfile.encoding=UTF-8`: Java system property cho **build JVM**.
- `org.gradle.daemon=true`: chọn chế độ Daemon của Gradle; từ lâu mặc định đã là true.
- `org.gradle.workers.max=2`: giới hạn số worker Gradle có thể thực thi đồng thời; **không** giới hạn RAM mỗi worker ở 2 GiB.
- `org.gradle.parallel=false`: không chạy cấu hình/execution các project một cách song song theo cơ chế parallel project execution; đây không phải công tắc duy nhất quyết định mọi loại song song.

Giá trị `org.gradle.jvmargs` chỉ điều khiển JVM thực thi build Gradle. Nó **không tự làm** `test.maxHeapSize = '2g'`, `JavaExec.maxHeapSize = '2g'` hay heap ứng dụng chạy bằng `java -jar` tăng lên.

### 4.1. Thay cấu hình cho một lần chạy

Trên Unix:

~~~bash
./gradlew help -Dorg.gradle.jvmargs="-Xms128m -Xmx1g -Dfile.encoding=UTF-8"
~~~

Cờ `-D` truyền system property vào cơ chế Gradle; khi key là `org.gradle.jvmargs`, Gradle diễn giải nó để cấu hình JVM chạy build. Dấu nháy giữ toàn bộ chuỗi có khoảng trắng thành **một tham số** của shell. Không dùng `-Porg.gradle.jvmargs=...` để thay thế: `-P` cung cấp *project property*, không phải cơ chế chính để chỉ định Gradle daemon JVM args.

Trong build nhiều môi trường, xác định rõ cấu hình có thể đến từ:

1. Tham số dòng lệnh có độ ưu tiên thích hợp.
2. `GRADLE_USER_HOME/gradle.properties`.
3. `<root-project>/gradle.properties`.
4. `GRADLE_HOME/gradle.properties` (nếu có bản cài Gradle riêng).

Thứ tự trên mô tả ưu tiên của **Gradle properties** khi trùng key. Không áp dụng máy móc cho mọi môi trường hay cho setting của task. Ví dụ `-PbuildFlavor=ci` là project property của người dùng, không thuộc cùng loại với `org.gradle.jvmargs`.

### 4.2. `--no-daemon` không nhất thiết chỉ có một JVM

~~~bash
./gradlew --no-daemon help
~~~

Nếu các JVM args cần cho build khác những gì Client đang sử dụng, Gradle có thể khởi động một **single-use daemon** để thực hiện build rồi dừng nó khi xong. Vì vậy vẫn có thể thấy Java process bổ sung dù đã dùng `--no-daemon`.

Nếu daemon được bật, Gradle tìm daemon tương thích về Gradle version, Java home/version và các JVM args quan trọng rồi tái sử dụng; thay `org.gradle.jvmargs` hoặc JDK có thể dẫn đến một daemon mới. Tham khảo:

~~~bash
./gradlew --status
./gradlew --stop
./gradlew help --info
~~~

`--status` và `--stop` chủ yếu xử lý daemon của **phiên bản Gradle đang gọi**, không quản lý mọi tiến trình Java trên máy; `--stop` chỉ nên dùng khi cần chẩn đoán hoặc thay đổi môi trường, không cần đặt trước mọi lệnh build.

## 5. Chọn JDK chạy Gradle khác với Java toolchain của dự án

Có ba thứ cần quyết định riêng:

1. **Client launcher JDK**: `JAVA_HOME`/`PATH`/IDE dùng để khởi động Gradle.
2. **Daemon JDK**: mặc định từ môi trường Client, hoặc do `org.gradle.java.home`, Tooling API/IDE và **Daemon JVM criteria** xác định.
3. **Toolchain JDK**: dành cho biên dịch, chạy test và `JavaExec`/task dùng Java launcher.

Ví dụ chọn Java cho Daemon:

~~~properties
# Dòng minh họa; phải thay bằng đường dẫn JDK có thật trên môi trường của bạn.
org.gradle.java.home=/opt/jdks/jdk-17
~~~

Đường dẫn riêng của một máy thường phù hợp với cấu hình người dùng/CI hơn là commit vào `gradle.properties` dùng chung. `org.gradle.java.home` thay Java **build/daemon**, không thay Java Client khởi động Wrapper.

Gradle hiện đại hỗ trợ **Daemon JVM criteria** được lưu tại `gradle/gradle-daemon-jvm.properties`, do task `updateDaemonJvm` quản lý. Nếu dự án khai báo criteria này, Gradle ưu tiên nó hơn `JAVA_HOME` và `org.gradle.java.home` khi quyết định JVM cho Daemon. Đó là một nguồn cấu hình cần xem khi “đã thay JAVA_HOME nhưng build vẫn chạy Java cũ”.

Không nên tự đoán JDK hợp lệ: phiên bản Gradle/Wrapper phải hỗ trợ phiên bản Java đang chạy Gradle. Trong một dự án cần target Java 17, bạn vẫn có thể dùng bản JDK tương thích khác để **chạy Gradle** rồi để **Java toolchain 17** biên dịch và chạy application/test.

### 5.1. Khai báo toolchain ở cấp project

Trong `build.gradle` dùng Groovy DSL:

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

Cấu hình này yêu cầu các task thuộc Java plugin có toolchain Java 17 phù hợp; không có nghĩa Gradle Daemon cũng chạy Java 17. JDK 17 phải được Gradle phát hiện, hoặc dự án phải cấu hình repository cho phép cung cấp toolchain nếu có cơ chế auto-provisioning.

Để xem các JDK mà Gradle phát hiện:

~~~bash
./gradlew -q javaToolchains
~~~

Chỉ khai báo `sourceCompatibility = JavaVersion.VERSION_17`/`targetCompatibility` không đảm bảo Gradle thực sự dùng JDK 17 khi biên dịch. Nếu cần giới hạn API/bytecode đầu ra ở mức Java 17 khi biên dịch bằng JDK mới hơn, có thể kết hợp `options.release = 17` ở `JavaCompile`. Chọn đúng compiler JDK và yêu cầu bytecode là hai quyết định liên quan nhưng không đồng nhất.

### 5.2. Chọn JDK riêng cho task

~~~groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaExec).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Hai đoạn này yêu cầu các task `Test` và `JavaExec` dùng Java launcher 17. Chúng là cấu hình thêm **trong một dự án đã áp dụng Java plugin** và có Gradle/toolchain tương thích. Không bắt buộc cấu hình thủ công nếu project toolchain đã đáp ứng, nhưng hữu ích khi muốn chắc chắn hoặc cần một task có phiên bản riêng.

**Toolchain** trả về compiler/launcher theo yêu cầu. Nó không truyền toàn bộ `org.gradle.jvmargs` từ Daemon xuống mọi task, và không bảo đảm JVM con có cùng system properties hay environment.

## 6. `Test` task: cấu hình JVM chạy bài kiểm thử

Java plugin tạo task `test` (và các task `Test` tùy build). Gradle **fork JVM riêng cho test**, cách ly classpath và tài nguyên khỏi build JVM. Ví dụ tại `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('test', Test) {
    minHeapSize = '128m'
    maxHeapSize = '512m'

    // Tùy chọn JVM cho process test; dùng cho flags không thuộc các property chuyên biệt
    jvmArgs '-ea'
    systemProperty 'app.profile', 'test'

    // Hai JVM test tối đa chạy đồng thời; chưa phải JUnit parallel test trong cùng JVM
    maxParallelForks = 2

    // Hạn chế giữ quá nhiều test class trong cùng một fork
    forkEvery = 0
}
~~~

Các thuộc tính có ý nghĩa:

| Thuộc tính | Ảnh hưởng |
| --- | --- |
| `minHeapSize`, `maxHeapSize` | `-Xms`/`-Xmx` của từng JVM test, không phải heap Gradle Daemon |
| `jvmArgs(...)` | JVM flags bổ sung cho test process, ví dụ `-ea` hoặc `--add-opens=...` khi thực sự cần |
| `systemProperty(name, value)` | Java system property xuất hiện trong test JVM qua `System.getProperty(...)` |
| `environment(name, value)` | Biến môi trường của test process qua `System.getenv(...)` |
| `javaLauncher` | JDK/`java` dùng để khởi chạy test JVM |
| `maxParallelForks` | Số process test tối đa có thể chạy song song trong task này |
| `forkEvery` | Số lượng test class tối đa trong một test process trước khi tạo fork mới; 0 nghĩa không chủ động fork lại theo ngưỡng class |
| `workingDir` | Thư mục làm việc của test process, thường là project directory; không nên dùng làm cách truyền đầu vào lỏng lẻo |

Ví dụ `maxParallelForks = 2` và `maxHeapSize = '512m'` cho phép tối đa **hai JVM test** đồng thời, mỗi JVM có heap tối đa theo thiết lập; ngoài heap còn có metaspace, stack, native memory, compiler/GC threads. Vì thế không thể cộng đơn giản 2 × 512 MiB rồi cho rằng đó là toàn bộ RAM build sẽ dùng.

**Không nhầm hai loại song song:**

- `maxParallelForks` là số **process forked** của Gradle Test task.
- JUnit 5 parallel execution là việc **nhiều test được điều phối trong một hoặc nhiều JVM** theo cấu hình JUnit; bật một cái không tự bật cái kia.

Khi dùng JUnit Jupiter cần thêm dependency và cấu hình test engine (ví dụ `useJUnitPlatform()`) phù hợp với project. Đoạn `tasks.named('test', Test)` trên chỉ là cấu hình JVM; không tự cài JUnit hay tạo test class.

### 6.1. Mẫu test dùng property riêng và toolchain

~~~groovy
tasks.named('test', Test) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
    maxHeapSize = '768m'
    systemProperty 'service.mode', 'integration-test'
    environment 'DEMO_TEST_STAGE', 'local'
}
~~~

Trong một test Java, các giá trị truyền vào sẽ được đọc như sau:

~~~java
String mode = System.getProperty("service.mode");
String stage = System.getenv("DEMO_TEST_STAGE");
~~~

Ở trên là **trích đoạn Java**, không phải chương trình standalone. Tại JVM test, `mode` có thể là `integration-test` và `stage` là `local` nếu không có cấu hình khác ghi đè. Trong **Gradle Daemon** không có bảo đảm hai giá trị đó được đặt giống như vậy.

## 7. `JavaExec`: chạy ứng dụng/CLI ở JVM khác với Gradle

`JavaExec` thực thi một Java main class bằng Java launcher riêng. Đây là task phù hợp để học ranh giới JVM vì có thể chủ động đặt heap, system property, environment và arguments.

Ví dụ cấu hình phần task:

~~~groovy
tasks.register('runProbe', JavaExec) {
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'demo.JvmProbe'
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }

    minHeapSize = '64m'
    maxHeapSize = '256m'
    jvmArgs '-ea'
    systemProperty 'demo.origin', 'javaexec-task'
    environment 'DEMO_STAGE', 'from-task'
    args 'alpha', 'beta'
}
~~~

Phân biệt chính xác:

| Cú pháp trong task | Nơi nhận và cách đọc |
| --- | --- |
| `maxHeapSize = '256m'` | JVM chạy `demo.JvmProbe` nhận giới hạn heap; không đổi Gradle Daemon |
| `jvmArgs '-ea'` | JVM chạy main class nhận cờ bật assertions |
| `systemProperty 'demo.origin', 'javaexec-task'` | `System.getProperty("demo.origin")` trong **child JVM** |
| `environment 'DEMO_STAGE', 'from-task'` | `System.getenv("DEMO_STAGE")` trong **child process** |
| `args 'alpha', 'beta'` | `String[] args` của phương thức `main`; **không phải** JVM flags |
| `javaLauncher = ...` | Lựa chọn `java` dùng để start child JVM |
| `classpath` | Đường dẫn class cần chạy; không chuyển thành buildscript classpath của Gradle |
| `workingDir` | Working directory của process con; không chuyển Gradle root project |

Cờ cho JVM (`-D...`, `-Xmx...`, `-XX:...`) thuộc cấu hình JVM. Ngược lại, `args` là các tham số **ứng dụng** ở phía sau tên main class. Ví dụ nếu chương trình yêu cầu `--config=dev.yaml` thì dùng `args '--config=dev.yaml'`; không gửi tùy tiện vào `jvmArgs`.

### 7.1. `Exec` khác `JavaExec`

`Exec` chạy **một executable bất kỳ**. Ví dụ:

~~~groovy
tasks.register('printJavaVersion', Exec) {
    commandLine 'java', '-version'
}
~~~

Đây là snippet minh họa: `Exec` nhờ hệ điều hành tìm `java` theo môi trường của process, nên không bảo đảm JDK trùng với Java toolchain của project. Vì `Exec` không phải `JavaForkOptions`, bạn không cấu hình nó bằng `maxHeapSize` giống `JavaExec`; nếu thật sự chạy `java` qua `Exec`, cần đưa JVM flags vào **command line** theo đúng thứ tự, hoặc chuyển sang `JavaExec` để dùng API Java chuyên biệt. `java -version` thường in thông tin ra stderr và phiên bản cụ thể phụ thuộc JDK.

Một số plugin khác như Kotlin compiler, Scala compiler hoặc Android Gradle Plugin có daemon/worker riêng cùng quy tắc memory riêng. Hãy xem tài liệu plugin tương ứng trước khi kết luận `org.gradle.jvmargs` sẽ điều khiển chúng.

## 8. Ví dụ thực hành Java 17 hoàn chỉnh, chạy được

Ví dụ này sử dụng **Groovy DSL** và `JavaExec`, không cần tải dependency ngoài để chương trình hoạt động (ngoại trừ Gradle Wrapper và JDK đã được chuẩn bị). Giả sử repository demo đã có đủ bốn tệp Wrapper: `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` và `gradle/wrapper/gradle-wrapper.properties`.

### 8.1. Cấu trúc

~~~text
jvm-boundaries-demo/
├── settings.gradle
├── gradle.properties
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    └── main/
        └── java/
            └── demo/
                └── JvmProbe.java
~~~

### 8.2. `settings.gradle`

~~~groovy
rootProject.name = 'jvm-boundaries-demo'
~~~

### 8.3. `gradle.properties`

~~~properties
# Cấu hình JVM chạy Gradle build; không phải JVM JavaExec
org.gradle.jvmargs=-Xms128m -Xmx1024m -XX:MaxMetaspaceSize=384m -Ddemo.origin=gradle-daemon
org.gradle.daemon=true
~~~

Để minh họa sự cách ly, giá trị `demo.origin=gradle-daemon` được khai báo **cho JVM thực thi build**. Trong task `JavaExec` dưới đây, ta lại đặt `demo.origin=javaexec-task` cho JVM con. Hai process không mặc nhiên chia sẻ chung system property.

### 8.4. `build.gradle`

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

// In ra property của JVM đang cấu hình Gradle.
tasks.register('showBuildJvmProperty') {
    doLast {
        println('build.origin=' + System.getProperty('demo.origin'))
    }
}

// Task này khởi chạy JVM riêng bằng Java 17.
tasks.register('runProbe', JavaExec) {
    group = 'verification'
    description = 'Demonstrates JVM settings of a JavaExec child process.'

    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'demo.JvmProbe'

    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }

    minHeapSize = '64m'
    maxHeapSize = '256m'
    jvmArgs '-ea'

    systemProperty 'demo.origin', 'javaexec-task'
    environment 'DEMO_STAGE', 'from-task'
    args 'alpha', 'beta'
}
~~~

`JavaExec.classpath = sourceSets.main.runtimeClasspath` liên kết đầu ra của Java source set với task; Java plugin tạo task biên dịch cần thiết. `mainClass` dùng tên đầy đủ kèm package. `javaLauncher` và `java.toolchain` đều chọn Java 17, nên kết quả ổn định khi JDK 17 được cung cấp.

Task `showBuildJvmProperty` là task trình diễn không có output file, chỉ in một Java system property của tiến trình chạy Gradle. Ở chế độ Daemon thông thường, nó chạy trong build JVM. Vì đây là snippet chẩn đoán, không cần dùng nó làm task build có cache.

### 8.5. `src/main/java/demo/JvmProbe.java`

~~~java
package demo;

public final class JvmProbe {
    private JvmProbe() {
    }

    public static void main(String[] args) {
        System.out.println("child.origin="
                + System.getProperty("demo.origin"));
        System.out.println("child.env="
                + System.getenv("DEMO_STAGE"));
        System.out.println("child.args="
                + String.join(",", args));
    }
}
~~~

Đây là một Java 17 program độc lập, không dùng API Gradle và không cần thư viện ngoài. Tên file phải đúng `JvmProbe.java` trong thư mục package `demo`.

Có thể tự biên dịch/chạy riêng nếu đã có JDK 17 trong terminal:

~~~bash
javac -d out src/main/java/demo/JvmProbe.java
java -Ddemo.origin=manual -cp out demo.JvmProbe alpha beta
~~~

Với lệnh Java thủ công ở trên, phần output của chương trình là:

~~~text
child.origin=manual
child.env=null
child.args=alpha,beta
~~~

Giá trị `child.env=null` chỉ đúng nếu biến `DEMO_STAGE` **chưa được đặt** trong môi trường của lệnh thủ công. Nếu shell/CI đã có biến đó, giá trị sẽ phản ánh môi trường thật; đây là một ví dụ cho thấy environment có thể khác nhau giữa các process.

### 8.6. Chạy từ Gradle Wrapper

Trên Linux/macOS, tại root project:

~~~bash
./gradlew -q showBuildJvmProperty
./gradlew -q runProbe
~~~

Output do task đầu tiên in ra:

~~~text
build.origin=gradle-daemon
~~~

Output do task thứ hai in ra:

~~~text
child.origin=javaexec-task
child.env=from-task
child.args=alpha,beta
~~~

Với giả định không có cấu hình JVM cao ưu tiên hơn ghi đè `demo.origin` của Gradle build, các dòng trên minh họa **hai JVM có system property khác nhau**. `-q` giảm log Gradle, nhưng các cảnh báo hoặc thông báo từ môi trường/plugin có thể xuất hiện tùy setup; ba dòng của `JvmProbe` là output xác định bởi mã nguồn và cấu hình task.

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat -q showBuildJvmProperty
.\gradlew.bat -q runProbe
~~~

Muốn thử thay heap child mà không đổi heap Daemon, sửa **chỉ** `maxHeapSize` của task `runProbe` rồi chạy lại. Không cố dùng các dòng output trên để suy ra chính xác lượng bộ nhớ mà JVM đã cấp phát: `-Xmx` là giới hạn heap; RAM thực của cả tiến trình thường lớn hơn và thay đổi theo JDK, GC, platform, thread và workload.

## 9. Tùy chỉnh thêm cho task: heap, system properties, environment, workdir và args

Những API dưới đây có ý nghĩa khác nhau:

~~~groovy
tasks.named('runProbe', JavaExec) {
    maxHeapSize = '384m'                     // heap child JVM
    systemProperty 'demo.origin', 'manual'  // -D được chuyển vào child JVM
    environment 'DEMO_STAGE', 'training'    // biến môi trường của child process
    args 'first', 'second'                  // app args, truyền tới main(String[])
    workingDir = projectDir                // working directory của child
}
~~~

Đây là **đoạn cấu hình thêm** cho task `runProbe` đã khai báo ở ví dụ trước, không phải script chạy độc lập. Nếu áp dụng đoạn này sau định nghĩa gốc, giá trị mới sẽ ghi đè những property tương ứng và thay đổi output. Không tự dùng nó để tính stdout đã nêu ở mục 8.

Phân biệt hệ thống tham số:

- **System property**: Java `System.getProperty("key")`; cấu hình bằng `systemProperty` trên `JavaExec`/`Test`, hoặc `-Dkey=value` khi trực tiếp gọi Java.
- **Environment variable**: Java `System.getenv("KEY")`; dùng `environment` cho task hoặc biến môi trường do OS/CI cung cấp.
- **Application arguments**: Java `main(String[] args)`; dùng `args`.
- **JVM options**: `-Xmx`, `-Xms`, `-XX:...`, `--add-opens`; dùng các API dành cho JVM của task. Ưu tiên `maxHeapSize`/`minHeapSize` thay vì lồng nhiều flag `-Xmx` trùng nhau vào `jvmArgs`.
- **Build JVM args**: `org.gradle.jvmargs`, ảnh hưởng JVM Gradle, không thay thế bốn dòng trên.

Biến môi trường ở máy CI có thể được kế thừa bởi JVM con và có thể chứa secret; chỉ truyền những giá trị thật cần thiết. Để bảo vệ thông tin nhạy cảm, không in biến credential vào log và không commit nó vào repo.

## 10. JavaCompile, compiler fork và JVM worker: xử lý trường hợp không phải Test/JavaExec

`JavaCompile` khác `JavaExec`: mục tiêu là **biên dịch** class, không phải chạy `main` của ứng dụng. Khi sử dụng toolchain, Gradle xác định một `JavaCompiler` phù hợp; cách vận hành compiler là chi tiết phụ thuộc Gradle/plugin và cấu hình fork.

Ví dụ cấu hình thêm trong dự án Java:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17

    // Cấu hình compiler chạy forked, tách JVM khỏi build.
    options.fork = true
    options.forkOptions.memoryInitialSize = '128m'
    options.forkOptions.memoryMaximumSize = '768m'
}
~~~

`options.forkOptions` chỉ thực sự áp dụng khi `options.fork` bật. Giới hạn memory ở đây dành cho **compiler process khi forked**, không phải `Test` hay `JavaExec`. Đừng bỏ `options.release = 17` nếu dự án cần ràng buộc Java API mục tiêu, nhưng hãy điều chỉnh theo target thực tế và compiler đang dùng.

**Gradle Worker API** có các isolation mode:

- `noIsolation()`: work action chạy với mức cô lập thấp, không phải JVM con riêng.
- `classLoaderIsolation()`: cách ly classloader, vẫn không mặc định tạo JVM process độc lập.
- `processIsolation()`: công việc chạy trong worker JVM riêng; cấu hình bằng `forkOptions` của worker.

Với plugin tự phát triển dùng `processIsolation()`, có thể cấu hình `forkOptions.maxHeapSize`/system properties của worker đó. Không nhầm các worker JVM này với Gradle Daemon hoặc test forks; chúng có vòng đời và giới hạn riêng, và có thể được tái sử dụng trong cùng một build.

Một số công cụ khác (ví dụ Javadoc, Kotlin compiler daemon, annotation processor chạy bên ngoài) có quy tắc riêng. Nếu gặp `OutOfMemoryError` trong compiler hay Kotlin daemon, cần xác nhận **tiến trình thực sự** phát sinh lỗi thay vì chỉ sửa `test.maxHeapSize`.

## 11. Memory là ngân sách toàn hệ thống, không phải một con số `-Xmx`

Giả sử một CI runner cấp 4 GiB RAM cho job. Bạn cấu hình:

~~~properties
# Heap tối đa cho Gradle Daemon
org.gradle.jvmargs=-Xmx2g
~~~

và:

~~~groovy
tasks.named('test', Test) {
    maxHeapSize = '1g'
    maxParallelForks = 3
}
~~~

Các cấu hình này **cho phép** tới ba JVM test với heap tối đa 1 GiB mỗi JVM, cộng với Gradle Daemon có heap tối đa 2 GiB. Nếu cả ba test fork chạy đồng thời và sử dụng nhiều heap, riêng tổng mức trần heap đã lên tới 5 GiB, vượt 4 GiB trước khi tính metaspace, thread stacks, native memory, JVM code cache, filesystem cache và các process khác. OOM có thể xảy ra dù từng process chưa vượt `-Xmx` của chính nó.

Cần phân biệt:

| Dấu hiệu | Thường nghi ngờ trước |
| --- | --- |
| `java.lang.OutOfMemoryError: Java heap space` trong log Gradle Daemon | Heap build JVM, chi phí configuration/plugin, số project/task |
| Java test stack trace báo `OutOfMemoryError` | `Test.maxHeapSize`, số test fork, rò rỉ bộ nhớ trong test |
| Child JavaExec bị `OutOfMemoryError` | `JavaExec.maxHeapSize`, dữ liệu chương trình, GC |
| Linux/CI báo process bị kill, exit 137 | Container/cgroup hoặc OS memory limit, **không nhất thiết** Java heap OOM |
| `GC overhead limit exceeded` ở process nào đó | Heap và tốc độ GC của chính process đó, vòng đời dữ liệu |
| `unable to create native thread` | Native memory, số thread/process, giới hạn hệ điều hành; tăng `-Xmx` có thể làm còn ít native memory hơn |
| JVM không khởi động với `Unrecognized VM option` | Flag không được JDK đang chạy process đó hỗ trợ |

`-Xmx` là giới hạn heap; tổng RSS của một JVM thường còn có metaspace, code cache, stack và native allocations. **Tăng `-Xmx` không luôn giải quyết thiếu RAM**: đôi khi phải giảm `maxParallelForks`, `--max-workers`, độ song song của plugin hoặc kích thước từng task.

Một điểm đáng nhớ: `org.gradle.workers.max` và `Test.maxParallelForks` chi phối hai lớp song song khác nhau; tổng số process thực tế cũng phụ thuộc cách Gradle điều phối task, các task khác và plugin. Đo lường bằng OS monitoring/cgroup và daemon/test logs sẽ chính xác hơn giả định rằng mỗi worker luôn là một JVM.

## 12. Debug chính xác JVM nào đang chạy

### 12.1. Kiểm tra CLI, Gradle Daemon và toolchain

~~~bash
java -version
./gradlew --version
./gradlew --status
./gradlew -q javaToolchains
./gradlew test --info
~~~

- `java -version`: Java trên shell (không chứng minh JDK test).
- `--version`: thông tin phiên bản Gradle/JVM mà launcher báo cáo.
- `--status`: daemon liên quan tới Gradle version này; nếu bị thay JVM args/JDK, có thể thấy daemon khác.
- `javaToolchains`: JDK/JRE Gradle phát hiện cho compile/test/run.
- `test --info`: log chi tiết task và những hoạt động fork được Gradle ghi lại; chỉ chạy thành công nếu project có task `test`.

Daemon logs thường ở `<GRADLE_USER_HOME>/daemon/<gradle-version>/daemon-<pid>.out.log`. Kiểm tra PID/log khi cần phân biệt build JVM với child JVM. Trong IDE, xem Gradle JVM và Java toolchain riêng; IDE có thể không dùng cùng JDK với terminal.

### 12.2. In thông tin trong đúng process

Trong Java test hoặc `JavaExec`:

~~~java
System.out.println(System.getProperty("java.home"));
System.out.println(System.getProperty("java.version"));
System.out.println(System.getProperty("demo.origin"));
System.out.println(Runtime.getRuntime().maxMemory());
~~~

Đây là **trích đoạn đặt bên trong main/test**, không phải Java class độc lập. `java.home` và `java.version` cho biết JDK của JVM thực sự đang chạy code đó. `Runtime.maxMemory()` trả số byte heap tối đa JVM nhận thức, có thể không trùng số byte tính bằng 1024^n tuyệt đối với `-Xmx` do cách VM làm tròn.

Với process trên máy có JDK đầy đủ, công cụ như `jcmd <pid> VM.command_line` và `jcmd <pid> VM.flags` có thể giúp xem JVM flags; cần quyền truy cập PID và JDK hỗ trợ. Hãy cẩn trọng vì command line/flags có thể chứa thông tin nội bộ hoặc secret.

### 12.3. Phân biệt source log và symptom

Nếu log báo “Gradle build daemon disappeared unexpectedly”, hãy kiểm tra **daemon log và tình trạng OS/container** trước. Nếu kết quả test XML hoặc test stdout báo exception, hãy xem **test worker JVM**; không suy ra ngay build Daemon đã hết bộ nhớ. Nếu một task `JavaExec` thất bại khi JVM khởi động, xem `javaLauncher`, `jvmArgs`, `maxHeapSize` và phiên bản JDK của task.

Khi một vấn đề chỉ xuất hiện trên CI, ghi lại: Gradle Wrapper version, JDK chạy daemon, toolchain JDK, Gradle User Home/caches, lệnh/task, tài nguyên container, max test forks và system/environment properties cần thiết (không log secret).

## 13. Tình huống thực tế và cách giải quyết

### Tình huống A — đã tăng heap Gradle nhưng test vẫn hết bộ nhớ

Build có:

~~~properties
org.gradle.jvmargs=-Xmx4g
~~~

Nhưng `test` chạy một JVM riêng, ví dụ giới hạn heap mặc định khác. Điều chỉnh chính task:

~~~groovy
tasks.named('test', Test) {
    maxHeapSize = '768m'
    maxParallelForks = 1
}
~~~

Không nên tăng các giá trị tùy tiện; đo đạc bộ nhớ và test data. Hạn chế test forks đôi khi hiệu quả hơn việc tăng heap cho mọi fork.

### Tình huống B — tăng `test.maxHeapSize` nhưng Gradle hết heap ở configuration

Nếu JVM Daemon chết khi tải/cấu hình project trước khi chạy test, thay heap của `Test` không giúp vì test JVM còn chưa được tạo. Kiểm tra `org.gradle.jvmargs`, dependency/plugin/build logic, xem daemon log và đo configuration memory.

### Tình huống C — test chạy Java 17 còn Gradle chạy Java 21

Có thể chọn JDK chạy Gradle 21 (nếu Gradle version hỗ trợ), nhưng khai báo:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Khi đó `JavaCompile`/`Test` do Java plugin quản lý chọn toolchain 17 (trừ khi task override); Daemon có thể dùng JDK 21. Đây là hành vi được thiết kế để build những target JVM khác nhau. Cần JDK 17 được phát hiện/cấp bởi toolchain resolver.

### Tình huống D — `--no-daemon` vẫn thấy hai JVM

Nếu Client VM flags và yêu cầu `org.gradle.jvmargs` của build khác nhau, Gradle có thể chạy disposable daemon để đảm bảo build JVM có đúng thông số. Không kết luận `--no-daemon` bị Gradle bỏ qua; xem thông báo và log Daemon.

### Tình huống E — JavaExec không nhìn thấy `-Penv=prod`

`-Penv=prod` là Gradle **project property**, không tự trở thành Java system property hoặc environment của JVM con. Nếu ứng dụng Java cần nhận giá trị:

~~~groovy
tasks.named('runProbe', JavaExec) {
    def envName = providers.gradleProperty('env').orElse('dev')
    systemProperty 'app.env', envName.get()
}
~~~

Đây là **đoạn cấu hình thêm**; task đang có trong ví dụ mục 8. Khi chạy `./gradlew runProbe -Penv=prod`, giá trị `app.env=prod` được đặt vào JVM con, nhưng mã `JvmProbe` trong demo không in property này trừ khi được bổ sung `System.getProperty("app.env")`. Với build lớn, ưu tiên giữ Provider lazy và khai báo task input phù hợp thay vì gọi `get()` sớm nếu không cần.

### Tình huống F — child JVM nhận sai `-D` hoặc missing env

Nếu CLI gọi `./gradlew -Dapp.mode=prod runProbe`, `-Dapp.mode=prod` nhắm vào **Gradle build JVM**. Muốn chương trình của task `JavaExec` nhìn thấy nó, phải truyền chủ động qua `systemProperty` hoặc `jvmArgs` của task. Tương tự, biến môi trường do CI đặt có thể được child kế thừa, nhưng Gradle có thể cấu hình `environment` để ghi đè hoặc dùng một môi trường khác; không nên coi mọi biến môi trường là cấu hình portable.

## 14. Checklist cho người cấu hình và người review build

1. Xác định **lỗi xuất phát từ Client, Gradle Daemon, Test/JavaExec, compiler hay worker JVM**; đọc log của đúng process.
2. Dùng `JAVA_HOME`/`PATH` để khởi động Wrapper; dùng `org.gradle.java.home` hoặc Daemon JVM criteria khi cần chọn riêng JVM chạy Gradle.
3. Dùng `org.gradle.jvmargs` để điều chỉnh heap/metaspace/JVM flags của Gradle Daemon; kiểm tra mức ưu tiên trong `gradle.properties` của dự án và user home.
4. Dùng **Java toolchain** và `javaLauncher`/`javaCompiler` để chọn JDK cho task, không dựa duy nhất vào Java version của Gradle.
5. Dùng `Test.maxHeapSize`/`JavaExec.maxHeapSize`, `jvmArgs`, `systemProperty`, `environment`, `args` cho đúng task/JVM con.
6. Không lẫn `args` của application với JVM options; không lẫn `-P` project property với `-D` system property.
7. Khi chạy song song, tính đến **số test fork + worker/process khác + native memory**, không chỉ nhìn `-Xmx` của Daemon.
8. Chạy các lệnh chẩn đoán thích hợp: `--version`, `--status`, `javaToolchains`, `--info`; đối chiếu code trong child JVM khi cần.
9. Nếu build dùng plugin tạo compiler/worker process riêng, đọc tài liệu cấu hình JVM của **plugin/task đó**.
10. Khi quản lý cấu hình trong CI, pin Gradle Wrapper/JDK và giữ credential ngoài mã nguồn/log; dùng thông số đã kiểm chứng bằng đo đạc.

## Tài liệu chính thức để tra cứu

- [Gradle — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): `org.gradle.jvmargs`, `org.gradle.java.home`, `JAVA_OPTS`, `GRADLE_OPTS` và thứ tự cấu hình.
- [Gradle — Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): Client/Daemon JVM, Daemon JVM criteria, `--no-daemon` và phiên daemon tương thích.
- [Gradle — Configuring Gradle: JVM Memory](https://docs.gradle.org/current/userguide/config_gradle.html): heap Gradle, launcher, test JVM.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): chọn JavaCompiler/JavaLauncher, task toolchains.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): forked test JVM, `maxParallelForks`, test process isolation.
- [Gradle — Test DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html) và [JavaExec DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.JavaExec.html): API `JavaForkOptions`, heap, JVM arguments, system properties.
- [Gradle — JavaCompile ForkOptions](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.ForkOptions.html): tùy chọn cho compiler fork.
- [Gradle — Worker API](https://docs.gradle.org/current/userguide/worker_api.html): thread/classloader/process isolation và worker JVM.
