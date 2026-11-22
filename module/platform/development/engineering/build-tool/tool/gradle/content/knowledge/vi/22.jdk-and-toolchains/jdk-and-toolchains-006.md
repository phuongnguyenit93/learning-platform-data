# Cấu hình toolchain riêng cho JavaCompile, Test và JavaExec trong Gradle

## Mục tiêu bài học

Một dự án Java có thể cần **biên dịch bằng JDK 21**, nhưng **tạo bytecode chạy trên Java 17**, đồng thời **chạy unit tests bằng Java 21** và **khởi động ứng dụng bằng Java 17** để kiểm chứng khả năng tương thích. Đây là ba quyết định khác nhau: **JDK nào dùng để biên dịch, JVM nào dùng chạy test, và JVM nào dùng khởi động chương trình**. Nếu chỉ chỉnh JAVA_HOME hoặc một thuộc tính sourceCompatibility, bạn có thể vô tình chạy toàn bộ quá trình trên JDK khác dự kiến.

Gradle cung cấp **Java toolchains** để lựa chọn công cụ Java theo version/vendor/implementation cho project hoặc cho **từng task**. Với JavaCompile, bạn gán một **JavaCompiler**; với Test và JavaExec, bạn gán một **JavaLauncher**. Các công cụ được cung cấp dưới dạng **Provider**, giúp cấu hình lười, tái sử dụng và tránh hardcode đường dẫn cài JDK trên máy lập trình viên.

Sau bài này, bạn có thể:

1. Phân biệt **JVM chạy Gradle Daemon**, **JDK biên dịch**, **JVM chạy Test**, **JVM chạy JavaExec** và **target bytecode**.
2. Thiết lập mặc định **java { toolchain { ... } }** rồi override cho từng task một cách rõ ràng.
3. Dùng **javaToolchains.compilerFor { ... }** cho **JavaCompile.javaCompiler**.
4. Dùng **javaToolchains.launcherFor { ... }** cho **Test.javaLauncher** và **JavaExec.javaLauncher**.
5. Kết hợp **JDK 21 compiler + options.release = 17** để không vô tình dùng API Java 18+ khi sản phẩm phải chạy trên Java 17.
6. Chạy cùng một tập tests trên nhiều JVM bằng nhiều Test tasks có classpath và testClassesDirs được cấu hình đúng.
7. Đăng ký thêm JavaCompile hoặc JavaExec task bằng **tasks.register**, tránh eager configuration.
8. Chẩn đoán lỗi **No matching toolchains**, **invalid source release**, **UnsupportedClassVersionError**, vấn đề IDE/JAVA_HOME, toolchain auto-provisioning.
9. Chuyển cấu hình Groovy DSL sang Kotlin DSL và thiết lập CI có JDK 17/21 một cách tái lập.
10. Thực hành trên một ứng dụng Java 17+ với JUnit Jupiter; kiểm chứng compiler, target bytecode và JVM thực sự chạy test/ứng dụng.

**Điều kiện:** ví dụ tổng hợp dùng **Gradle tương thích Java 21**, JDK 17 và JDK 21 được cài và Gradle phát hiện, và kết nối tới Maven Central cho JUnit lần đầu (hoặc có sẵn dependencies trong cache). Khi không có mạng, phần JavaExec không dùng JUnit vẫn có thể chạy nếu môi trường Gradle/Wrapper đã sẵn sàng.

---

## 1. Năm khái niệm dễ bị nhầm

| Khái niệm | Ví dụ | Nó quyết định điều gì? |
| --- | --- | --- |
| **Gradle Daemon JVM** | JDK 17 | JVM chạy chính Gradle và các plugins trong build process |
| **JavaCompile.javaCompiler** | JDK 21 | Bộ biên dịch **javac** được dùng cho một task JavaCompile |
| **CompileOptions.release** | **17** | Giới hạn cú pháp, JDK API và phiên bản bytecode mà javac tạo ra |
| **Test.javaLauncher** | JDK 21 | Java executable chạy JVM chứa test framework/tests |
| **JavaExec.javaLauncher** | JDK 17 | Java executable chạy main class của task JavaExec |

Năm lựa chọn này **có thể khác nhau** mà không mâu thuẫn. Ví dụ Gradle có thể chạy trên JDK 17, gọi JDK 21 để compile nhưng phát hành class file tương thích Java 17, rồi chạy tests trên Java 21.

### 1.1. Sơ đồ thực thi

~~~text
JDK 17 (Gradle Daemon)
          |
          +-- :compileJava (JavaCompile)
          |      javaCompiler = JDK 21 / javac
          |      options.release = 17
          |      => bytecode class file version 61 (Java 17)
          |
          +-- :compileTestJava (JavaCompile)
          |      javaCompiler = JDK 21 / javac
          |      options.release = 17
          |
          +-- :test (Test)
          |      javaLauncher = JDK 21 / java
          |      => tests chạy trên JVM 21
          |
          +-- :run (JavaExec)
          |      javaLauncher = JDK 17 / java
          |      => ứng dụng chạy trên JVM 17
          |
          +-- :runOn21 (JavaExec)
                 javaLauncher = JDK 21 / java
                 => ứng dụng chạy trên JVM 21
~~~

Đây là **sơ đồ tình huống minh họa**; Gradle Daemon không nhất thiết phải chạy JDK 17 trên mọi hệ thống. Các task có thể thực hiện theo thứ tự phụ thuộc/lịch trình Gradle, không phải theo thứ tự nhánh trong sơ đồ.

### 1.2. JAVA_HOME không nhất thiết là toolchain được chọn

**JAVA_HOME** thường giúp Gradle chọn một JVM để khởi chạy, còn **javaToolchains** cho phép mỗi task dùng công cụ Java khác. Nếu bạn đặt JAVA_HOME=JDK17 rồi dùng JavaCompile toolchain21, Gradle có thể vẫn gọi **javac 21** cho task ấy.

Ngoài ra, Gradle có **Daemon JVM criteria** (theo phiên bản/thiết lập Gradle) có thể điều khiển JVM chạy Daemon và có ưu tiên riêng. Hãy đọc **./gradlew --version**, **./gradlew javaToolchains** và task configuration, thay vì suy luận từ biến môi trường duy nhất.

### 1.3. Toolchain Java version khác source/target compatibility

**javaCompiler=JDK21** không tự đồng nghĩa bytecode luôn cần Java 21 nếu bạn đặt **options.release=17**. Nhưng nếu không đặt release/source/target thích hợp, compiler JDK 21 có thể tạo bytecode/API cao hơn yêu cầu sản phẩm.

**sourceCompatibility=17** chỉ giới hạn ngữ pháp Java 17; **targetCompatibility=17** chỉ nhằm phát class file với target version tương ứng. Hai thuộc tính legacy này **không kiểm soát đầy đủ API JDK được tham chiếu**. **--release 17** là lựa chọn đáng ưu tiên cho cross-compilation khi compiler hỗ trợ.

---

## 2. Cơ chế Java Toolchain Service

Gradle expose **javaToolchains**, một extension/service kiểu **JavaToolchainService**. Nó cung cấp:

- **compilerFor { spec }** → **Provider<JavaCompiler>**.
- **launcherFor { spec }** → **Provider<JavaLauncher>**.
- **javadocToolFor { spec }** → **Provider<JavadocTool>**.

**JavaToolchainSpec** thường có:

- **languageVersion**: JavaLanguageVersion.of(17), of(21), ...
- **vendor**: chọn hãng JDK nếu có yêu cầu thực sự (ví dụ JvmVendorSpec.ADOPTIUM).
- **implementation**: yêu cầu loại JVM/implementation khi cần (ví dụ một bản vendor-specific hoặc J9 theo API Gradle hỗ trợ).

Không phải máy nào cũng có JDK đúng vendor/implementation. Nếu chỉ cần Java 21 bất kể hãng, **đừng ép vendor** vì điều đó làm CI khó tái hiện hơn.

### 2.1. Provider và lazy configuration

Ví dụ Groovy DSL:

~~~groovy
def compiler21 = javaToolchains.compilerFor {
    languageVersion = JavaLanguageVersion.of(21)
}

def launcher17 = javaToolchains.launcherFor {
    languageVersion = JavaLanguageVersion.of(17)
}
~~~

Hai biến là **Provider objects**, không phải đường dẫn đã được tự động hardcode thành một chuỗi. Gradle có thể giải quyết chúng khi cần để thực thi task, chọn installation hợp lệ và theo dõi chúng như toolchain inputs.

Đặc biệt:

- **compiler21** không phải đường dẫn tới java executable cho Test.
- **launcher17** không phải compiler phù hợp cho JavaCompile.
- Có thể tái sử dụng Provider của cùng JDK cho nhiều tasks.
- Dùng providers giúp code bền hơn khi đường dẫn khác giữa Windows, Linux, macOS hoặc CI.
- Tránh gọi **.get()** quá sớm trong configuration logic chỉ để in đường dẫn; có thể làm mất tính lười và khiến build khó cấu hình khi JDK chưa sẵn sàng.

### 2.2. Kiểu tool tương ứng với từng task

| Task type | Thuộc tính | Tool provider tương ứng |
| --- | --- | --- |
| **JavaCompile** | **javaCompiler** | **javaToolchains.compilerFor { ... }** |
| **Test** | **javaLauncher** | **javaToolchains.launcherFor { ... }** |
| **JavaExec** | **javaLauncher** | **javaToolchains.launcherFor { ... }** |
| **Javadoc** | **javadocTool** | **javaToolchains.javadocToolFor { ... }** |

**Test** là một task chạy JVM cho test framework, không phải một JavaCompile task; nó cần **JavaLauncher**, không phải **JavaCompiler**. Dù tests chạy bằng Java 21, mã nguồn tests vẫn được biên dịch bởi một task **compileTestJava** riêng.

### 2.3. Dự án có Java plugin đã có service

**java**, **java-library**, **application** và nhiều JVM language plugins áp hỗ trợ toolchain tự động qua Java base support. Bạn thường không cần tự apply plugin **jvm-toolchains**. Một plugin/task tùy chỉnh không dùng Java language plugin nhưng cần toolchain có thể áp core plugin **jvm-toolchains** theo tài liệu chính thức.

---

## 3. Mặc định cấp project: java.toolchain

**build.gradle**:

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

Khi không override ở task, các JavaCompile/Test/Javadoc tasks do Java plugin tạo thường dùng toolchain 17 theo convention. Tư duy đúng: **project toolchain là default, task-level property là quyền ghi đè có mục đích**.

Ví dụ trên đủ cho project nhỏ compile và test cùng JDK 17. Nó cũng tránh lỗi “máy tôi dùng JDK 21 nhưng CI có JDK 17 nên class file khác” nếu toolchains được cấu hình/detected ổn định.

### 3.1. Khi nên override

Các nhu cầu thực tế:

- Dùng **compiler 21** để được bản vá compiler hoặc tính năng build tooling mới, nhưng phát **Java 17 bytecode**.
- **Test JVM 17 và 21** trên cùng binary để phát hiện khác biệt behavior/runtime.
- Chạy **integration tests trên Java 21**, giữ unit tests trên Java 17.
- Chạy ứng dụng kiểm thử với **JVM 17** trong khi dev thường dùng 21.
- Tạo một **JavaExec code generator** chạy trên JDK21, còn sản phẩm chính target17.
- Một module/library cần Java 17, nhưng một task thử nghiệm compile source chuyên biệt với --release11.

**Không nên override chỉ vì một môi trường tình cờ đặt JAVA_HOME khác.** Nếu dự án thực sự cần một JDK cho mọi task, giữ cấu hình project-level sẽ ngắn và dễ bảo trì hơn.

---

## 4. Cấu hình riêng JavaCompile.javaCompiler

### 4.1. Override duy nhất compileJava

**build.gradle**:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('compileJava', JavaCompile) {
    javaCompiler = javaToolchains.compilerFor {
        languageVersion = JavaLanguageVersion.of(21)
    }

    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

Ý nghĩa:

1. **compileJava** là task JavaCompile compile nguồn **src/main/java**.
2. **javaCompiler** được chọn từ JDK **21** chứ không phải mặc định project 17.
3. **options.release = 17** làm javac 21 tạo **Java 17 class files** và chỉ cho phép API thuộc Java 17 theo --release.
4. **options.encoding = 'UTF-8'** giúp xử lý nguồn có ký tự tiếng Việt nhất quán.
5. **compileTestJava** không được override trong đoạn này; nó tiếp tục theo project toolchain 17 trừ khi bạn cấu hình khác.

### 4.2. Vì sao cần options.release?

Giả sử compiler JDK 21 và code gọi một JDK API chỉ có ở Java 21. Nếu chỉ yêu cầu target bytecode cũ bằng targetCompatibility mà không giới hạn API, bạn có thể compile code dùng API mới rồi chạy trên Java 17 gặp **NoSuchMethodError** hoặc **NoClassDefFoundError**.

Với:

~~~groovy
options.release = 17
~~~

compiler sẽ từ chối sử dụng JDK APIs/cú pháp không có trong Java 17. Nó cũng phát bytecode với **major version 61**. Compiler JDK 21 đủ mới để hỗ trợ --release17; chiều ngược lại **JDK17 không thể compile --release21**.

### 4.3. Chỉ định tất cả JavaCompile tasks

~~~groovy
tasks.withType(JavaCompile).configureEach {
    javaCompiler = javaToolchains.compilerFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

Dạng này áp dụng cho **compileJava, compileTestJava** và những JavaCompile tasks được thêm sau đó. Hữu ích khi mọi Java source set cần cùng compiler, nhưng **có thể ảnh hưởng cả custom tasks** mà một plugin đã đăng ký. Khi chỉ cần main sources, dùng **tasks.named('compileJava', JavaCompile)** hẹp hơn.

**configureEach** là API configuration avoidance: task chưa cần chạy không bị eager realized chỉ vì bạn cấu hình theo type.

### 4.4. Một task compile custom với compiler khác

Ví dụ bổ sung cho một project có thư mục **src/probe/java**:

~~~groovy
tasks.register('compileProbe', JavaCompile) {
    source = fileTree('src/probe/java') {
        include '**/*.java'
    }
    classpath = files()
    destinationDirectory = layout.buildDirectory.dir('classes/probe')

    javaCompiler = javaToolchains.compilerFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
    options.release = 11
}
~~~

Nếu source ở **src/probe/java** chỉ dùng API Java 11, task này có thể compile bằng **JDK 21** tạo bytecode **Java 11 (major version 55)**. Đây là **task riêng**; nó không làm đổi target của **compileJava**.

### 4.5. Vì sao không chỉ dùng forkOptions.executable?

Các cấu hình legacy như:

~~~groovy
options.forkOptions.executable = '/opt/jdk-21/bin/javac'
~~~

có thể hoạt động trong một số tình huống, nhưng **hardcode path phụ thuộc OS/CI** và dễ mâu thuẫn với toolchain selection của Gradle. Tránh đặt song song **javaCompiler** và các compiler-executable override không nhất quán. Toolchain providers thể hiện yêu cầu Java version rõ hơn, phù hợp task caching/configuration hơn.

---

## 5. Cấu hình riêng Test.javaLauncher

**Test** chạy các tests trong một JVM. **Nó không compile test sources**; việc compile do **compileTestJava** đảm nhiệm. Do đó, muốn tests chạy trên JDK21, cấu hình **javaLauncher** của Test:

~~~groovy
tasks.named('test', Test) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Một project có:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

vẫn có thể compile Java 17 mà tests thực thi trên Java 21. **Không phải nâng sourceCompatibility/test source level lên 21 chỉ vì test runtime là 21**.

### 5.1. Ví dụ JUnit Jupiter

~~~groovy
dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Đây là cấu hình JUnit Jupiter trên Maven Central; cần **repositories { mavenCentral() }** và có mạng/cache sẵn. **useJUnitPlatform()** là cơ chế chọn test framework, không chọn JDK. **javaLauncher** mới là lựa chọn JVM process cho tests.

**Version 5.11.4** là version cụ thể dùng cho ví dụ tái lập; production nên dùng phiên bản được tổ chức kiểm duyệt và cập nhật có kiểm soát.

### 5.2. test JVM khác compileTestJava

Mô hình:

~~~text
src/test/java/*.java
      |
      v
compileTestJava (JavaCompile: compiler JDK17 hoặc JDK21)
      |
      v
build/classes/java/test (bytecode tương thích Java17)
      |
      v
test (Test: javaLauncher JDK21)
      |
      v
JUnit engine và test classes chạy trên JVM 21
~~~

**JDK runtime phải hỗ trợ class file version được tạo**. Bytecode Java17 chạy trên Java21 là bình thường. Bytecode Java21 **không thể chạy trên Java17**. Nếu bạn compile tests bằng JDK21 với options.release21 rồi đặt test.javaLauncher=17, khả năng gặp **UnsupportedClassVersionError** là rất cao.

### 5.3. Chạy cùng test classes trên nhiều JDK

Bạn có thể đăng ký thêm Test task:

~~~groovy
tasks.register('testOn17', Test) {
    group = 'verification'
    description = 'Run standard unit tests with Java 17'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform()

    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Đây là **task thực thi test** riêng, không tự compile source ở lần khác. **testClassesDirs** chỉ class directories; **classpath** cần runtime dependencies của test framework và code ứng dụng. Tập file từ **sourceSets.test.output** thường mang task dependencies cần thiết để Gradle tự lập lịch compile khi chạy test task.

Nếu tests có yêu cầu chỉ dành cho Java21, không nên chạy chúng trên 17 mà kỳ vọng pass. Muốn thật sự kiểm tra compatibility matrix, viết tests chỉ dùng API runtime phù hợp hoặc conditionally skip theo version có lý do rõ ràng.

### 5.4. Hiển thị stdout của tests

Gradle không nhất thiết hiển thị stdout của từng test mặc định. Cấu hình:

~~~groovy
tasks.withType(Test).configureEach {
    testLogging {
        events 'passed', 'failed', 'skipped'
        showStandardStreams = true
    }
}
~~~

Khi test in **System.out.println(...)**, nó có thể xuất hiện trong Gradle test logging. Thứ tự và trình bày log tùy Gradle/worker process; không so khớp toàn bộ transcript, chỉ kiểm tra nội dung từ từng test.

### 5.5. Đừng nhầm JavaLauncher với JVM args

~~~groovy
tasks.named('test', Test) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
    jvmArgs '-Dfile.encoding=UTF-8'
    maxHeapSize = '1g'
}
~~~

**javaLauncher** chọn **bản java executable**; **jvmArgs** và **maxHeapSize** đặt lựa chọn cho process đó. Một JVM arg như **-Djava.version=21** không thể biến Java17 thành Java21; system properties tùy ý không thay runtime binary.

---

## 6. Cấu hình riêng JavaExec.javaLauncher

**JavaExec** chạy main class từ classpath. Nó xuất hiện trong task **run** khi dùng **application plugin**, và cũng được dùng cho nhiều task tự tạo.

### 6.1. Override task run của application plugin

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.App'
}

tasks.named('run', JavaExec) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Với code được compile tương thích Java17, **./gradlew run** sẽ chạy **demo.App trên Java17**, bất kể Gradle Daemon đang dùng Java21 hay compiler của compileJava là JDK21.

### 6.2. Tạo JavaExec task chạy một version khác

~~~groovy
tasks.register('runOn21', JavaExec) {
    group = 'verification'
    description = 'Run the application using Java 21'

    classpath = sourceSets.main.runtimeClasspath
    mainClass = application.mainClass

    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Các thuộc tính:

- **classpath** phải gồm output của main source set và runtime dependencies.
- **mainClass** phải chỉ tới tên lớp có **public static void main(String[] args)**.
- **javaLauncher** chỉ JVM process.
- **group/description** giúp task dễ tìm trong **./gradlew tasks --all**.
- Nếu classpath là **sourceSets.main.runtimeClasspath**, nó liên kết với outputs Gradle và hỗ trợ dependency ordering thay vì tham chiếu trực tiếp vào một JAR path cố định.

Lệnh:

~~~bash
./gradlew runOn21
~~~

### 6.3. Khi dùng JavaExec cho code generation

Một custom generator cần Java21 nhưng sản phẩm cuối cần Java17:

~~~groovy
tasks.register('runGenerator21', JavaExec) {
    group = 'build'
    description = 'Run a pre-built Java 21 compatible generator'

    classpath = configurations.generator
    mainClass = 'org.example.GeneratorMain'

    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

**Đây chỉ là mẫu minh họa**, không tự chạy vì cần tạo **generator configuration**, cung cấp module có **GeneratorMain**, khai báo outputs/inputs và dependencies. Nó cho thấy toolchain chạy công cụ có thể khác toolchain compile sản phẩm.

Không chỉ đổi javaLauncher rồi cho rằng generator artifact sẽ tự xuất hiện; JavaExec vẫn cần classpath đúng.

### 6.4. JavaExec khác Exec

**Exec** chạy một process bất kỳ với executable path; nó **không có JavaExec.javaLauncher**. Nếu dùng Exec để gọi java, bạn phải quản lý executable path, JVM args và classpath thủ công. Với Java main class, **JavaExec** thường an toàn, rõ ràng và nhất quán với Gradle toolchains hơn.

---

## 7. Dự án mẫu chạy được: JDK 21 compile, test 21, run 17 hoặc 21

Lab dưới đây là **một dự án hoàn chỉnh để kiểm chứng**. Bạn cần **JDK17 và JDK21** được Gradle nhận diện; dự án dùng **JUnit Jupiter** từ Maven Central cho test, vì vậy chạy tests lần đầu cần mạng nếu dependencies chưa cache.

### 7.1. Cây thư mục

~~~text
toolchain-per-task-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/demo/App.java
    └── test/java/demo/AppTest.java
~~~

Lấy Gradle Wrapper từ Gradle hoặc một project đáng tin với phiên bản hỗ trợ Java21 toolchains; **không tự chế gradle-wrapper.jar**. Gradle 8.5+ hoặc Gradle 9.x có hỗ trợ phù hợp cho tình huống Java21, nhưng vẫn nên xem **Java Compatibility Matrix** của bản Wrapper đang dùng.

### 7.2. settings.gradle

~~~groovy
rootProject.name = 'toolchain-per-task-lab'
~~~

### 7.3. build.gradle hoàn chỉnh (Groovy DSL)

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    // Mặc định cho những Java tasks không override.
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.App'
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

// Tool providers: không hardcode đường dẫn.
def compiler21 = javaToolchains.compilerFor {
    languageVersion = JavaLanguageVersion.of(21)
}

def launcher17 = javaToolchains.launcherFor {
    languageVersion = JavaLanguageVersion.of(17)
}

def launcher21 = javaToolchains.launcherFor {
    languageVersion = JavaLanguageVersion.of(21)
}

// Cả main/test Java sources compile bằng JDK21,
// nhưng chỉ dùng Java17 language/API và bytecode.
tasks.named('compileJava', JavaCompile) {
    javaCompiler = compiler21
    options.release = 17
    options.encoding = 'UTF-8'
}

tasks.named('compileTestJava', JavaCompile) {
    javaCompiler = compiler21
    options.release = 17
    options.encoding = 'UTF-8'
}

// Task test mặc định: thực thi trên JDK21.
tasks.named('test', Test) {
    useJUnitPlatform()
    javaLauncher = launcher21
    systemProperty 'expectedJavaFeature', '21'

    testLogging {
        events 'passed', 'failed', 'skipped'
        showStandardStreams = true
    }
}

// Task run của application plugin: chạy Java17.
tasks.named('run', JavaExec) {
    javaLauncher = launcher17
}

// Task thêm: cùng classpath/main class, chạy Java21.
tasks.register('runOn21', JavaExec) {
    group = 'verification'
    description = 'Run demo.App on Java 21'

    classpath = sourceSets.main.runtimeClasspath
    mainClass = application.mainClass
    javaLauncher = launcher21
}

// Task thêm: chạy chính test classes trên Java17.
tasks.register('testOn17', Test) {
    group = 'verification'
    description = 'Run unit tests on Java 17'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform()
    javaLauncher = launcher17
    systemProperty 'expectedJavaFeature', '17'

    testLogging {
        events 'passed', 'failed', 'skipped'
        showStandardStreams = true
    }
}
~~~

**Điểm cần đọc kỹ:**

1. Project default **17** áp dụng cho tasks không override.
2. **compileJava/compileTestJava** đều dùng compiler21, release17.
3. **test** chạy Java21; **testOn17** chạy cùng test classes trên Java17.
4. **run** dùng launcher17; **runOn21** dùng launcher21.
5. **launchers** là providers, không phải **JAVA_HOME** cứng.
6. **JUnit Jupiter** cần download từ Maven Central khi chưa có cache.
7. **testOn17** có testClassesDirs/classpath riêng vì đó là Test task mới, không phải bản sao tự động của **test**.
8. Mã ứng dụng phải thật sự tương thích Java17. options.release17 giúp compiler cấm API Java mới hơn ngay lúc compile.
9. Chạy **./gradlew build** thường chạy test mặc định, **không tự chạy testOn17**. Muốn CI chạy cả hai JVM phải gọi task testOn17 tường minh hoặc nối nó vào một verification lifecycle task theo policy.

### 7.4. src/main/java/demo/App.java

~~~java
package demo;

public final class App {
    private App() {
    }

    public static String message() {
        return "Hello, toolchains!";
    }

    public static void main(String[] args) {
        System.out.println(message());
        System.out.println("Runtime feature: " + Runtime.version().feature());
    }
}
~~~

**Runtime.version().feature()** trả major feature release của JVM thật, ví dụ 17 hoặc 21. Nó giúp kiểm chứng launcher thay vì suy đoán từ **JAVA_HOME**.

### 7.5. src/test/java/demo/AppTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

public final class AppTest {
    @Test
    void messageIsStable() {
        assertEquals("Hello, toolchains!", App.message());
    }

    @Test
    void runtimeMatchesTaskLauncher() {
        int expected = Integer.parseInt(
                System.getProperty("expectedJavaFeature")
        );
        int actual = Runtime.version().feature();

        assertEquals(expected, actual);
        System.out.println("Test JVM feature: " + actual);
    }
}
~~~

Test chỉ dùng **Java 17 APIs**. Khi chạy **test** bằng JDK21, system property expected=21; khi chạy **testOn17** bằng JDK17, expected=17. Vì thế **cùng một test source** có thể kiểm tra launcher khác nhau mà không thay code.

### 7.6. Các lệnh kiểm tra môi trường

Linux/macOS:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
~~~

Kiểm tra output **javaToolchains** thấy cả Java17 và Java21 có **Is JDK: true** hoặc ít nhất Java17 launcher/JDK21 compiler đáp ứng đúng. Nếu thiếu JDK21, task compileJava sẽ không thể lấy **JavaCompiler(21)** cho tới khi cài/provision JDK đúng.

### 7.7. Chạy main bằng JDK17

~~~bash
./gradlew clean run
~~~

Phần stdout do ứng dụng in, khi chạy đúng launcher17:

~~~text
Hello, toolchains!
Runtime feature: 17
~~~

Gradle còn có log task và build status; hai dòng trên là **stdout của demo.App**, không phải toàn transcript Gradle.

### 7.8. Chạy main bằng JDK21

~~~bash
./gradlew runOn21
~~~

Phần stdout:

~~~text
Hello, toolchains!
Runtime feature: 21
~~~

**Cùng App.class**, nhưng launcher khác nên feature version khác. Điều này chứng minh **JavaExec.javaLauncher** tách biệt khỏi **JavaCompile.javaCompiler** và **Gradle Daemon JVM**.

### 7.9. Chạy tests bằng JDK21

~~~bash
./gradlew test
~~~

Trong log nếu bật **showStandardStreams**, test **runtimeMatchesTaskLauncher** in:

~~~text
Test JVM feature: 21
~~~

Nếu assertions pass, Gradle task **:test** thành công. Report HTML tests thông thường nằm dưới **build/reports/tests/test/**.

### 7.10. Chạy cùng tests bằng JDK17

~~~bash
./gradlew testOn17
~~~

Test in:

~~~text
Test JVM feature: 17
~~~

Task **testOn17** có report riêng ở vị trí Gradle quy định cho task đó. Vì cả hai Test tasks dùng một tập source tests, chúng hữu ích cho compatibility matrix: khi một test chỉ pass trên 21 nhưng fail trên 17, bạn đã phát hiện khác biệt cần xử lý.

### 7.11. Kiểm tra bytecode target không phụ thuộc runtime

Class file được sinh tại:

~~~text
build/classes/java/main/demo/App.class
~~~

Dùng JDK có **javap**:

~~~bash
javap -verbose build/classes/java/main/demo/App.class
~~~

Tìm dòng:

~~~text
major version: 61
~~~

**61** là class file major của Java17. Nó không thay đổi khi chạy **run** hay **runOn21**; đổi JVM chạy chương trình không tự biên dịch lại class file theo version runtime.

PowerShell có thể lọc:

~~~powershell
javap -verbose .\build\classes\java\main\demo\App.class |
    Select-String 'major version'
~~~

**Đọc có ý nghĩa:** compiler thực tế là JDK21, nhưng **options.release17** tạo bytecode Java17. App chạy thành công trên Java17/21 vì không dùng APIs chỉ có sau Java17.

### 7.12. Chạy tất cả nhiệm vụ mục tiêu

~~~bash
./gradlew clean compileJava compileTestJava test testOn17 run runOn21
~~~

Gradle lập lịch dựa vào task dependencies và tránh chạy lặp các compile tasks trong cùng invocation. Không khẳng định thứ tự trên console đúng bằng thứ tự tên tasks khi có tối ưu/scheduling; kết quả cần xem là từng task thành công và những dòng stdout tương ứng.

### 7.13. Phụ thuộc mạng của lab

- **Maven Central** dùng cho JUnit Jupiter/launcher; lần tải đầu cần mạng trừ khi Gradle cache đã có.
- Application **run/runOn21** chỉ cần compile main sources, không cần JUnit artifacts nếu không chạy tests hoặc task khác bắt resolve test configuration.
- **Gradle Wrapper** có thể cần tải Gradle distribution nếu chưa có.
- **Java21 toolchain** nếu không cài cục bộ chỉ được auto-provision khi cấu hình đúng **toolchain resolver repository**.
- Nếu công ty dùng internal Maven mirror, thay mavenCentral bằng repository được cấp phép theo chính sách.

Không coi demo là hoàn toàn offline khi nó chứa **testImplementation** từ Maven Central.

---

## 8. Tạo cùng ý tưởng bằng Kotlin DSL

**build.gradle.kts** không dùng cú pháp Groovy. Phần cấu hình tương đương:

~~~kotlin
plugins {
    application
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
    mainClass = "demo.App"
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

val compiler21 = javaToolchains.compilerFor {
    languageVersion = JavaLanguageVersion.of(21)
}

val launcher17 = javaToolchains.launcherFor {
    languageVersion = JavaLanguageVersion.of(17)
}

val launcher21 = javaToolchains.launcherFor {
    languageVersion = JavaLanguageVersion.of(21)
}

tasks.named<JavaCompile>("compileJava") {
    javaCompiler = compiler21
    options.release = 17
    options.encoding = "UTF-8"
}

tasks.named<JavaCompile>("compileTestJava") {
    javaCompiler = compiler21
    options.release = 17
    options.encoding = "UTF-8"
}

tasks.named<Test>("test") {
    useJUnitPlatform()
    javaLauncher = launcher21
    systemProperty("expectedJavaFeature", "21")
}

tasks.named<JavaExec>("run") {
    javaLauncher = launcher17
}

tasks.register<JavaExec>("runOn21") {
    group = "verification"
    classpath = sourceSets["main"].runtimeClasspath
    mainClass = application.mainClass
    javaLauncher = launcher21
}

tasks.register<Test>("testOn17") {
    group = "verification"
    testClassesDirs = sourceSets["test"].output.classesDirs
    classpath = sourceSets["test"].runtimeClasspath
    useJUnitPlatform()
    javaLauncher = launcher17
    systemProperty("expectedJavaFeature", "17")
}
~~~

Kotlin DSL có **typed task registration** như **tasks.named<JavaCompile>**, **tasks.register<Test>**, và Kotlin-style function calls. Một số tài liệu viết các property thông qua **.set(provider)** thay cho **= provider**; với Gradle Kotlin DSL hiện đại, hai cách có thể xuất hiện tùy API/compiler version, nhưng sử dụng cách chính thức của Gradle version mà project đang chạy.

Ví dụ gán tường minh:

~~~kotlin
tasks.named<JavaCompile>("compileJava") {
    javaCompiler.set(
        javaToolchains.compilerFor {
            languageVersion.set(JavaLanguageVersion.of(21))
        }
    )
    options.release.set(17)
}
~~~

Sự khác biệt về cú pháp DSL **không thay đổi cơ chế JavaCompiler vs JavaLauncher**.

---

## 9. Ưu tiên khi task-level khác project-level

Giả sử:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Rồi:

~~~groovy
tasks.named('test', Test) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

**test.javaLauncher=21** là override cụ thể cho task test; project default 17 không “ghi đè ngược lại” trừ khi một đoạn cấu hình khác viết lại cùng property sau đó.

### 9.1. Đừng áp hai quy tắc mâu thuẫn lên cùng task

Ví dụ dễ gây nhầm:

~~~groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('test', Test) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Cả hai cùng cấu hình **test**; thứ tự và thời điểm actions được áp dụng có thể ảnh hưởng giá trị cuối cùng, làm logic khó đọc. Tránh nhiều writers cho cùng **javaLauncher**. Tốt hơn: một default theo type và chỉ override các tasks cần thiết trong một vị trí được kiểm soát, hoặc khai báo rõ mọi Test task.

### 9.2. Đổi launcher không đổi compiler

Gán **test.javaLauncher=21** không làm **compileTestJava** tự chuyển sang compiler21. Nếu test sources cần cú pháp Java21, bạn cũng cần đổi compiler/options.release cho compileTestJava và nhớ rằng test classes Java21 sẽ **không chạy được trên Java17**.

Tương tự, **JavaExec.javaLauncher** không compile main code; nó chỉ chạy các outputs đã có. Muốn chạy Java17, phải đảm bảo class files và library runtime dependencies tương thích Java17.

---

## 10. Lọc toolchain theo vendor/implementation

Ngoài languageVersion:

~~~groovy
def adoptium21 = javaToolchains.compilerFor {
    languageVersion = JavaLanguageVersion.of(21)
    vendor = JvmVendorSpec.ADOPTIUM
}
~~~

Đây là snippet minh họa. Chỉ chạy khi máy/auto-provisioner có toolchain JDK21 từ vendor tương ứng. Vendor restriction giúp reproducing vendor-specific bugs nhưng giảm lựa chọn hợp lệ. **Không thêm JvmVendorSpec.ADOPTIUM nếu mọi JDK21 chuẩn đều chấp nhận**.

Bạn cũng có thể dùng spec cho launcher:

~~~groovy
def launcher21 = javaToolchains.launcherFor {
    languageVersion = JavaLanguageVersion.of(21)
    vendor = JvmVendorSpec.ADOPTIUM
}
~~~

Toolchain không tự cài đúng vendor chỉ nhờ khai báo filter: nếu không có bản tương ứng, Gradle phải tìm download repository được hỗ trợ hoặc báo lỗi.

### 10.1. JDK và JRE

- **JavaCompile** cần JDK có compiler; một JRE không thể đáp ứng JavaCompiler.
- **Test** và **JavaExec** có thể chỉ cần Java runtime/JRE phù hợp, dù Gradle thường ưu tiên JDK installs khi chọn toolchains.
- Khi cần compiler21, kiểm tra **Is JDK: true** cho Java21 trong **javaToolchains** report.
- Cùng major version nhưng khác vendor hoặc implementation có thể cho behavior khác; chỉ giới hạn vendor khi có test compatibility hoặc chính sách yêu cầu.

---

## 11. Toolchain discovery và installation

Trước khi kết luận Gradle “dùng sai JDK”, hãy xem toolchains được phát hiện:

~~~bash
./gradlew -q javaToolchains
~~~

Báo cáo có thể liệt kê:

~~~text
+ Options
    | Auto-detection:  Enabled
    | Auto-download:   Enabled

+ Some JDK 17 installation
    | Language Version: 17
    | Is JDK:          true
    | Location:        ...

+ Some JDK 21 installation
    | Language Version: 21
    | Is JDK:          true
    | Location:        ...
~~~

**Dữ liệu trên là minh họa**, tên vendor/path/tình trạng auto-download thay đổi tùy máy. Điều quan trọng là có công cụ đúng version và loại.

### 11.1. Khai báo vị trí JDK tùy môi trường

Trong **gradle.properties** (ví dụ trên hệ thống Unix có hai JDK):

~~~properties
org.gradle.java.installations.paths=/opt/jdks/jdk-17,/opt/jdks/jdk-21
~~~

Gradle xem các paths là **đường dẫn root của Java installations**; nó không tự tìm sâu trong mọi subdirectories của một parent tùy ý.

Bạn cũng có thể khai báo tên env vars trỏ đến Java homes:

~~~properties
org.gradle.java.installations.fromEnv=JDK17,JDK21
~~~

Với cách này, môi trường cần đặt **JDK17** và **JDK21** thành đường dẫn cài đặt tương ứng. Windows dùng Windows paths và environment variables phù hợp; tránh copy đường dẫn Unix vào Windows.

### 11.2. Auto-detection và auto-provisioning là hai chuyện khác

- **Auto-detection**: Gradle tìm local JDK/JRE installations từ môi trường, IDE, SDKMAN và các nguồn hệ thống được hỗ trợ.
- **Auto-provisioning**: Gradle có thể download JDK chưa được cài nếu có **toolchain resolver plugin/repositories được cấu hình** đúng.

**Không có resolver đã cấu hình, khai báo Java21 không bảo đảm Gradle tự tải JDK21 từ Maven Central.** Dependency repositories cho JUnit và toolchain download repositories **là hai loại repository khác nhau**.

Gradle hiện đại hỗ trợ toolchain resolver plugins (ví dụ Foojay resolver convention). Cấu hình chính xác và version plugin phải khớp bản Gradle/organization policy, xem tài liệu chính thức thay vì dùng một số phiên bản tự đoán trong lab.

### 11.3. Vì sao JAVA_HOME đúng mà Gradle vẫn không tìm thấy?

- **JAVA_HOME** trỏ tới một JRE thay vì JDK.
- JDK được cài sau khi Gradle Daemon đã khởi tạo và Daemon giữ thông tin toolchains cũ.
- **javaToolchains** spec yêu cầu vendor/implementation không có.
- Gradle bị tắt auto-detection và chưa khai báo paths/fromEnv.
- Toolchain JDK21 có kiến trúc/OS không phù hợp.
- Toolchain resolver plugin chưa được cấu hình.
- Gradle Wrapper version không hỗ trợ Java version mong muốn.

Thử kiểm tra **./gradlew -q javaToolchains**, xem **--info**, rồi khi thay paths/Java installations có thể dùng **./gradlew --stop** để khởi tạo Daemon mới. Không xóa cache toàn cục làm bước đầu.

---

## 12. Cách xác minh từng task thật sự chọn đúng Java

### 12.1. --version chỉ cho biết Gradle đang chạy JVM nào

~~~bash
./gradlew --version
~~~

Kết quả cho thấy JVM của Gradle/Daemon theo cách bản Gradle trình bày; **không phải bằng chứng compileJava đang dùng cùng JDK**. Khi toolchain task-level được thiết lập, compiler/launcher có thể khác hoàn toàn.

### 12.2. --info cho compiler và launcher

~~~bash
./gradlew compileJava --info
./gradlew test --info
./gradlew run --info
~~~

Gradle có thể ghi thông tin toolchain/compiler executable và runtime launcher. Log thực tế tùy bản Gradle; không nên so khớp từng dòng như một API ổn định. Từ góc nhìn học tập, **App/Test tự in Runtime.version().feature()** cho thấy rõ JVM process đã chạy.

### 12.3. In JavaCompiler metadata ở execution time

Đoạn chẩn đoán có thể thêm vào build.gradle:

~~~groovy
tasks.named('compileJava', JavaCompile) {
    doFirst {
        println 'compileJava compiler version: ' +
                javaCompiler.get().metadata.languageVersion
    }
}
~~~

Khi compileJava thực sự chạy, thông tin metadata đến từ compiler toolchain đã chọn. **Không nên dùng println trong cấu hình thông thường như một cơ chế tracking lâu dài**; dùng có chủ đích rồi bỏ để log gọn.

Lưu ý Gradle có thể báo task UP-TO-DATE và không thực hiện action; nếu cần thấy log doFirst thì dùng một lượt compile có thay đổi đầu vào hoặc **clean compileJava**.

### 12.4. Bytecode major version vs JVM runtime version

| Java release | Major class-file version |
| --- | --- |
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |

**javap -verbose** kiểm tra class-file major. **Runtime.version().feature()** kiểm tra JVM process. Một ứng dụng có major61 vẫn có thể chạy trên 21; điều đó không có nghĩa compiler chỉ là JDK17.

### 12.5. CI matrix và kiểm chứng hai runtimes

Ví dụ các lệnh của lab:

~~~bash
./gradlew --dependency-verification strict clean test testOn17
./gradlew run
./gradlew runOn21
~~~

Flag dependency verification chỉ có ý nghĩa khi project đã có **gradle/verification-metadata.xml** hợp lệ và được review; nếu lab chưa bật verification, không cần thêm flag này. Với JUnit được tải từ Maven Central, hãy giữ repository policy theo tổ chức.

Muốn các test tasks luôn chạy trong **check**, có thể:

~~~groovy
tasks.named('check') {
    dependsOn tasks.named('testOn17')
}
~~~

Nếu project áp Java plugin, **check** đã phụ thuộc test mặc định. Dòng trên **bổ sung** testOn17 vào lifecycle; không tạo một task mới. Chỉ sử dụng khi CI thật sự cần kiểm tra trên cả Java17 và21.

---

## 13. Những lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| **No matching toolchains found** | Gradle không tìm thấy JDK đúng languageVersion/vendor/implementation | Dùng javaToolchains report; cài đúng JDK hoặc cấu hình resolver |
| **Toolchain download repositories have not been configured** | Thiếu resolver cho auto-provisioning | Cài JDK cục bộ hoặc cấu hình settings toolchainManagement/resolver plugin |
| **Cannot find a Java installation matching 21** | JDK21 chưa được phát hiện | Kiểm tra JAVA_HOME, fromEnv/paths, Gradle Daemon cache |
| **No compiler available** | Chỉ có JRE, JavaCompile cần javac | Cài đầy đủ JDK phù hợp |
| **invalid source release: 21** | Dùng javac quá cũ cho release21 | Chọn compiler21 trở lên, đừng đổi runtime launcher để chữa |
| **release version 21 not supported** | Compiler không hỗ trợ --release21 | Nâng compiler toolchain hoặc hạ target đã được chấp nhận |
| **UnsupportedClassVersionError** khi runOn17 | Classfile biên dịch Java21 (major65) chạy trên Java17 (tối đa61) | Dùng compiler >=17 với --release17, kiểm tra dependencies |
| Java17 chạy nhưng gặp **NoSuchMethodError** | Code/thư viện gọi API mới không có trên runtime17 | Recompile với --release17 và chọn dependency/runtime tương thích |
| test chạy Java21 dù JAVA_HOME là Java17 | Test.javaLauncher đã override21 | Đây có thể là đúng mục tiêu; kiểm tra build.gradle |
| testOn17 fail còn test pass | Bytecode/library/test behavior phụ thuộc Java21 | Tìm API classfile khác biệt, không bỏ test tương thích |
| Không thấy JUnit tests | Chưa useJUnitPlatform hoặc thiếu engine/runtime launcher | Kiểm tra dependencies, framework và Gradle test report |
| testOn17 báo no tests | Sai testClassesDirs/classpath hoặc test framework chưa cấu hình | Trỏ tới sourceSets.test output/runtimeClasspath và useJUnitPlatform |
| **Could not resolve JUnit** | Maven Central/proxy hoặc repository policy thiếu | Sửa dependency repositories/credentials, không liên quan Java launcher |
| IDE run dùng Java21, Gradle run dùng Java17 | IDE run configuration khác Gradle task | Chạy qua Gradle task hoặc đồng bộ IDE settings |
| Build chậm vì nhiều JDK | Nhiều toolchain resolves và forked JVMs | Chỉ tạo tasks cần thiết, cấu hình providers lazy, reuse daemon phù hợp |
| JavaExec không tìm thấy main class | Thiếu classpath/mainClass hoặc compile chưa được liên kết | Đặt sourceSets.main.runtimeClasspath và tên lớp đúng |
| JavaCompile custom không tạo output | source sai hoặc destinationDirectory thiếu | Kiểm tra fileTree path và output directory |
| Gradle chạy JVM21 nhưng compilation vẫn JDK17 | Project/task compiler toolchain chọn17 | Kiểm tra javaCompiler chứ không chỉ ./gradlew --version |
| Có vendor restriction nhưng chỉ cài JDK khác vendor | Filter toolchain quá hẹp | Bỏ vendor constraint nếu không thật cần |
| Gradle version cũ gặp lỗi với JDK21 | Wrapper không hỗ trợ JDK version | Xem Gradle Compatibility Matrix và cập nhật Wrapper theo policy |
| Plugin thay đổi javaCompiler sau cấu hình | Nhiều nơi viết cùng Property | Tập trung config và inspect effective task values |

### 13.1. Trình tự debug ngắn gọn

1. **./gradlew --version**: biết Gradle/Daemon dùng JVM nào.
2. **./gradlew -q javaToolchains**: biết local installations đã được Gradle phát hiện.
3. Đọc **java.toolchain** mặc định, rồi kiểm tra các **tasks.named/withType** đã override.
4. Phân loại lỗi thuộc compiler/launcher/bytecode/dependency repository.
5. Với compile, xem **javaCompiler** và **options.release**; với tests/exec xem **javaLauncher**.
6. Dùng **--info**, **Runtime.version().feature()**, **javap -verbose** cho chứng cứ.
7. Kiểm tra source sets, classpaths và framework khi lỗi test/javaexec.
8. Khi mọi cấu hình đúng, chạy lại trên CI có JDKs phù hợp và commit task-level policy rõ ràng.

---

## 14. Những pattern nên sử dụng trong dự án nhiều module

### 14.1. Mặc định nhất quán, ngoại lệ hẹp

Một hướng thiết kế:

~~~text
Convention plugin cho toàn tổ chức
└── java.toolchain = 17
    ├── compileJava = JDK 21 compiler + release 17 (khi cần)
    ├── compileTestJava = JDK 21 compiler + release 17
    ├── test = launcher17 (unit tests cơ bản)
    ├── testOn21 = launcher21 (compatibility matrix)
    ├── run = launcher17 (production baseline)
    └── integrationTest = launcher21 (integration-only environment)
~~~

Đây là **pattern kiến trúc**, không phải một file chạy độc lập. Dùng convention plugin nếu nhiều project cần policy giống nhau, tránh copy/paste nhiều blocks với sự khác biệt âm thầm.

### 14.2. Đừng biến Java toolchain thành global switch

Một project có thể cần:
- Main library API Java17.
- Test runtime cả 17 và21.
- Code generator Java21.
- Gradle Daemon trên JVM được chính sách tổ chức cho phép.

**Một biến JAVA_HOME không thể truyền tải hết những ràng buộc này**. Toolchains cung cấp các thuộc tính per task để xây dựng đúng mục tiêu, version release giữ compatibility, test matrix xác minh behavior.

### 14.3. Bảo vệ compatibility library public

Nếu thư viện bạn publish hứa hỗ trợ Java17:
- Compile public/main source bằng --release17.
- Kiểm thử Java17 và các JVM mới tổ chức hỗ trợ.
- Kiểm tra transitive runtime dependencies cũng tương thích Java17.
- Không để annotation processor/code generator vô tình thêm classfiles Java21 vào JAR.
- Kiểm tra **jar** output và published artifacts, không chỉ compileJava.
- Nếu dùng **multi-release JAR**, cần build logic/test riêng, không thể chỉ đổi javaLauncher và cho là xong.

### 14.4. Toolchain cho plugin authors

Khi tự viết Gradle plugin/task type, có thể dùng **JavaToolchainService** được inject và khai báo **Property<JavaLauncher>** làm input nested, đồng thời đặt default convention từ **JavaPluginExtension.toolchain**, cho người dùng override từng task. Không giữ Project object hoặc đường dẫn hardcoded làm input ẩn, và không tự resolve tools trong constructor khi chưa cần.

Đây là chủ đề nâng cao khác với **JavaCompile/Test/JavaExec** có properties toolchain sẵn. Với các task chuẩn, ưu tiên API có sẵn thay vì tạo lớp task mới.

---

## 15. Bài tập có đáp án

### Bài 1 — Compiler và launcher khác nhau

Project default17, compileJava.javaCompiler=21, options.release=17, test.javaLauncher=21. Hỏi **App.class** target nào, test chạy JVM nào?

**Đáp án:** App.class thường là Java17 class file major61; test JVM là Java21. Gradle Daemon có thể chạy một JDK thứ ba tương thích với Gradle.

### Bài 2 — JavaCompile dùng launcherFor được không?

Code:

~~~groovy
tasks.named('compileJava', JavaCompile) {
    javaCompiler = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

**Đáp án:** sai loại tool; javaCompiler yêu cầu **JavaCompiler**, không phải JavaLauncher. Sửa bằng **javaToolchains.compilerFor**.

### Bài 3 — Test dùng compilerFor được không?

**Đáp án:** không. Test chạy JVM nên cần **javaLauncher = javaToolchains.launcherFor {...}**. Việc compile tests thuộc **compileTestJava**.

### Bài 4 — Có options.release17 là đủ chọn JDK17?

**Đáp án:** không. **--release17** hạn chế API/cú pháp/bytecode; nó không chọn JDK compiler. Compiler có thể là JDK21 và vẫn release17. Dùng **javaCompiler** để kiểm soát JDK.

### Bài 5 — JavaExec21 có thể chạy classfile major61?

**Đáp án:** có. Java21 chạy bytecode Java17. Cần đảm bảo dependencies cũng tương thích runtime.

### Bài 6 — JavaExec17 có thể chạy classfile major65?

**Đáp án:** không. Java17 không hỗ trợ Java21 bytecode. Cần compile --release17 hoặc dùng runtime Java21 nếu policy sản phẩm cho phép.

### Bài 7 — Vì sao ./gradlew --version nói Java17 nhưng test in Java21?

**Đáp án:** Gradle Daemon JVM khác Test launcher. Test dùng **Test.javaLauncher=21**, nên JVM process chạy tests khác JVM chạy build.

### Bài 8 — Mỗi task Test mới có tự biết tests ở đâu?

**Đáp án:** không nên dựa vào suy đoán. Với custom Test task, đặt **testClassesDirs = sourceSets.test.output.classesDirs**, **classpath = sourceSets.test.runtimeClasspath**, framework runner và launcher đúng.

### Bài 9 — Muốn tất cả JavaCompile dùng compiler21 thì làm gì?

**Đáp án:** dùng **tasks.withType(JavaCompile).configureEach { javaCompiler = javaToolchains.compilerFor { languageVersion = JavaLanguageVersion.of(21) } }**. Cẩn trọng vì ảnh hưởng mọi JavaCompile tasks.

### Bài 10 — Maven Central giải quyết thiếu JDK21 không?

**Đáp án:** không. Dependency repository tải JUnit/libs; **toolchain resolver repositories** dùng để cung cấp JDKs khi auto-provisioning. Hoặc cài JDK21 cục bộ.

### Bài 11 — JAVA_HOME là JDK21 nhưng muốn app chạy Java17

**Đáp án:** đặt **tasks.named('run', JavaExec) { javaLauncher = javaToolchains.launcherFor { languageVersion = JavaLanguageVersion.of(17) } }**, đảm bảo bytecode/libs target17 và JDK17 có sẵn.

### Bài 12 — JUnit tests fail do version Java?

**Đáp án:** trước tiên xem stacktrace: **UnsupportedClassVersionError** cho classfile mới hơn runtime, **NoClassDefFoundError** cho thiếu runtime library, **NoSuchMethodError** cho API mismatch, hoặc toolchain not found cho thiếu JDK. Không quy tất cả về toolchain setting.

### Bài 13 — Tại sao task runOn21 tự chạy compileJava?

**Đáp án:** classpath dùng **sourceSets.main.runtimeClasspath** là Gradle FileCollection liên kết với outputs/source set và task dependencies; Gradle có thể lập lịch classes/compile cần thiết. Không cần chèn đường dẫn build/classes bằng string và tự tạo dependsOn vô lý.

### Bài 14 — Khi nào cần vendor pinning?

**Đáp án:** khi kiểm tra lỗi vendor-specific hoặc chính sách doanh nghiệp yêu cầu vendor cụ thể. Nếu mục tiêu chỉ là Java21, giữ vendor unconstrained để tránh No matching toolchains không cần thiết.

### Bài 15 — Làm thế nào xác minh output là Java17?

**Đáp án:** dùng **javap -verbose** trên App.class, tìm **major version: 61**, đồng thời chạy App bằng JDK17. Đây là hai lớp kiểm tra bổ sung: bytecode target và runtime behavior.

---

## 16. Checklist đưa vào CI/production

- [ ] Đã phân biệt rõ **Gradle Daemon JVM**, compiler, Test runtime, JavaExec runtime?
- [ ] Có yêu cầu **project-level toolchain** rõ hay chỉ task-level?
- [ ] **JavaCompile.javaCompiler** được gán từ **compilerFor**?
- [ ] **Test.javaLauncher / JavaExec.javaLauncher** được gán từ **launcherFor**?
- [ ] Mọi toolchain Provider đều không hardcode path, không .get() sớm?
- [ ] **options.release** có đúng API/bytecode compatibility cần cam kết?
- [ ] JDK compiler đủ mới để hỗ trợ --release target?
- [ ] Test classes có target không cao hơn JVM chạy test?
- [ ] Runtime dependencies cũng tương thích JVM version được dùng?
- [ ] Custom Test tasks có testClassesDirs, classpath và framework configuration?
- [ ] Custom JavaExec tasks có runtimeClasspath/mainClass đúng?
- [ ] Đã chạy **./gradlew -q javaToolchains** trên CI hoặc tài liệu hóa JDK provisioning?
- [ ] Toolchain resolver/cài đặt JDK đúng version, vendor, architecture?
- [ ] Đã kiểm tra **Runtime.version().feature()** và **javap major version**?
- [ ] Có test trên JVM tối thiểu mà sản phẩm hỗ trợ?
- [ ] Không có nhiều scripts/plugins mâu thuẫn cùng ghi javaLauncher/javaCompiler?
- [ ] Gradle Wrapper có tương thích với JDK muốn chạy/compile?
- [ ] Nếu có JUnit, Maven dependencies/repositories có nguồn được kiểm duyệt?
- [ ] Đã chạy tasks cần thiết trong CI, không chỉ **build** bỏ sót custom Test task?
- [ ] Thay đổi toolchain được lưu trong build scripts/convention plugin có review?

## Tài liệu chính thức của Gradle

- [Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html): project-level và per-task configuration, compilerFor/launcherFor, discovery, auto-provisioning, vendor và Daemon.
- [JavaToolchainService Javadoc](https://docs.gradle.org/current/javadoc/org/gradle/jvm/toolchain/JavaToolchainService.html): service API cho JavaCompiler, JavaLauncher, JavadocTool.
- [JavaCompile task API](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.JavaCompile.html): javaCompiler và JavaCompile properties.
- [CompileOptions task API](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.CompileOptions.html): options.release, encoding và compiler options.
- [Test task API](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html): javaLauncher, testClassesDirs, classpath, testLogging và testing framework.
- [JavaExec task API](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.JavaExec.html): javaLauncher, mainClass, classpath.
- [Java plugin](https://docs.gradle.org/current/userguide/java_plugin.html): sourceSets, compileJava, compileTestJava và lifecycle tasks.
- [Application plugin](https://docs.gradle.org/current/userguide/application_plugin.html): task run và mainClass.
- [JVM Toolchains Plugins](https://docs.gradle.org/current/userguide/jvm_toolchains_plugins.html): javaToolchains extension, auto-applied plugin, settings toolchain management.
- [Java compatibility matrix](https://docs.gradle.org/current/userguide/compatibility.html): phiên bản Java nào được Gradle hỗ trợ để chạy chính Gradle và dùng làm toolchain.

**Kết luận:** Một cấu hình tốt không chỉ ghi “project dùng Java17” mà chỉ rõ **javac phiên bản nào**, **output phải tương thích JVM nào**, **tests chạy bằng Java nào** và **ứng dụng thực thi bằng Java nào**. Trong Gradle, **JavaCompile nhận JavaCompiler từ compilerFor**, còn **Test và JavaExec nhận JavaLauncher từ launcherFor**. Kết hợp **task-level toolchains + options.release + JVM compatibility tests** giúp build vừa linh hoạt vừa dự đoán và kiểm chứng được trên máy developer và CI.