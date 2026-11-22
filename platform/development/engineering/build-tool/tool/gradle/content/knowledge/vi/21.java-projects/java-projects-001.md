# Java plugin và đồ thị task chuẩn của dự án Java trong Gradle

## 1. Tổng quan và mục tiêu

Gradle là hệ thống build theo **task graph**, không phải danh sách các lệnh được chạy theo thứ tự viết trong file. Khi áp dụng Java plugin, Gradle tự tạo những task để biên dịch mã Java, xử lý resources, biên dịch và chạy tests, đóng gói JAR và gom các công việc thành các lifecycle tasks.

Trong `build.gradle` Groovy DSL, chỉ cần:

~~~groovy
plugins {
    id 'java'
}
~~~

`java` là **core plugin** đi kèm Gradle distribution; không cần khai báo một plugin version riêng. Java plugin tạo hai source sets chuẩn `main` và `test`, những dependency configurations cần thiết và các task như `compileJava`, `processResources`, `classes`, `jar`, `compileTestJava`, `processTestResources`, `testClasses`, `test`, `javadoc`, `clean`, `assemble`, `check`, `build`.

Sau bài học, người đọc có thể:

1. Đọc đồ thị phụ thuộc giữa Java tasks, biết chạy task nào để biên dịch, test hoặc tạo artifact.
2. Phân biệt task **thực thi hành động** và task **lifecycle/aggregate**.
3. Hiểu cấu trúc `src/main`, `src/test` cùng các output trong `build/`.
4. Tạo một Java 17 project có JUnit Jupiter tests với Groovy DSL và Gradle Wrapper.
5. Dùng `tasks --all`, `--dry-run`, `help --task`, `--info` để kiểm tra graph.
6. Giải thích `UP-TO-DATE`, `NO-SOURCE`, `FROM-CACHE`, `SKIPPED` và tác động của `clean`.
7. Mở rộng task graph bằng `tasks.named` và `TaskProvider` mà không tạo dependency sai.

Bài thuộc nhóm **Dự án Java** trong **Build Tool Gradle**. Tất cả lệnh `./gradlew` dành cho Linux/macOS; trong PowerShell Windows dùng `.\gradlew.bat`. Demo yêu cầu Wrapper thật, Gradle version phù hợp JDK 17, Java toolchain 17 có sẵn hoặc có resolver hợp lệ và Internet để tải JUnit nếu chưa cache.

## 2. Java plugin thực sự cung cấp gì?

Java plugin thêm **model build** chứ không chỉ tự động gọi compiler:

| Thành phần | Vai trò |
| --- | --- |
| `java { }` extension | Java toolchain, compatibility, packaging conventions |
| `sourceSets.main` | Mã sản phẩm và production resources |
| `sourceSets.test` | Test code và test resources |
| `implementation`, `compileOnly`, `runtimeOnly` | Nhóm khai báo dependency cho main |
| `testImplementation`, `testRuntimeOnly` | Nhóm khai báo dependency cho test |
| `compileClasspath`, `runtimeClasspath` | Resolvable classpaths của main |
| `testCompileClasspath`, `testRuntimeClasspath` | Resolvable classpaths của test |
| `compileJava`, `processResources` | Biên dịch/copy các đầu vào main |
| `compileTestJava`, `processTestResources` | Biên dịch/copy các đầu vào test |
| `jar`, `test`, `javadoc` | Đóng gói, chạy test, sinh tài liệu |
| `classes`, `testClasses`, `assemble`, `check`, `build` | Task tập hợp các công việc liên quan |

Plugin cũng áp dụng các khả năng nền tảng từ Base plugin. Các quy ước task/file input này làm Gradle biết cần biên dịch lại phần nào khi có file thay đổi.

**Không mặc định có task `run`.** Java plugin chuẩn tạo JAR và chạy tests nhưng không tự biết class nào là entry point của application. Nếu dự án là ứng dụng có `main(String[])` và muốn task `run`, start scripts, distributions, hãy dùng `application` plugin. Nếu là thư viện cần công bố API dependency, hãy dùng `java-library` plugin và cấu hình `api`/`implementation` đúng mục đích.

| Plugin | Mục tiêu phổ biến | Khả năng bổ sung |
| --- | --- | --- |
| `java` | Java code, test và JAR | Đồ thị compile/test/package chuẩn |
| `java-library` | Java library để project khác sử dụng | API/implementation separation, `api` |
| `application` | Ứng dụng JVM cần chạy/phân phối | `run`, start scripts, distribution tasks |

`application`/`java-library` dựa trên nền tảng Java plugin; không nên tự dựng lại tất cả task chuyên dụng của chúng chỉ vì đã có `java`.

## 3. Source sets và layout theo convention

Mặc định Java plugin dùng:

~~~text
project-root/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/
    │   │   └── ... Java production sources
    │   └── resources/
    │       └── ... production resources
    └── test/
        ├── java/
        │   └── ... JUnit/TestNG Java tests
        └── resources/
            └── ... test resources
~~~

| Đường dẫn | Được xử lý bởi | Output mặc định |
| --- | --- | --- |
| `src/main/java` | `compileJava` | `build/classes/java/main` |
| `src/main/resources` | `processResources` | `build/resources/main` |
| `src/test/java` | `compileTestJava` | `build/classes/java/test` |
| `src/test/resources` | `processTestResources` | `build/resources/test` |

`sourceSets.main.output` là collection kết hợp compiled classes và processed resources của main. `sourceSets.test.output` tương ứng với test. Một project có Java và các JVM language plugins khác có thể chứa thêm output directories, vì vậy Gradle khuyến nghị dùng source set outputs thay vì hard-code duy nhất một đường dẫn.

Một project **không cần có sẵn cả bốn thư mục**. Nếu `src/main/resources` không tồn tại, `processResources` thường hiển thị `NO-SOURCE`; đó không phải mặc định là build failure. Tương tự, khi không có Java test source, những test-related tasks có thể không có nguồn hoặc bỏ qua hành động.

Ví dụ muốn dùng layout riêng:

~~~groovy
// Chỉ là trích đoạn thay layout, không dán cùng demo chuẩn
// trừ khi đã di chuyển các file nguồn.
sourceSets {
    main {
        java {
            srcDirs = ['src/product/java']
        }
        resources {
            srcDirs = ['src/product/resources']
        }
    }
}
~~~

Sau khi đổi `srcDirs`, task `compileJava` vẫn làm nhiệm vụ compile main source set nhưng sẽ đọc input ở location mới. Không cần cấu hình source sets nếu project đã tuân convention chuẩn.

## 4. Task chuẩn: loại và quan hệ phụ thuộc

| Task | Loại/vai trò | Công việc | Quan hệ quan trọng |
| --- | --- | --- | --- |
| `compileJava` | `JavaCompile` | Biên dịch Java `main` | Tasks cung cấp compile classpath, nếu có |
| `processResources` | `ProcessResources` | Copy resources của `main` | Nguồn resource và provider tasks liên quan |
| `classes` | Aggregate | Chuẩn bị compiled classes và resources của main | **`compileJava`, `processResources`** |
| `jar` | `Jar` | Đóng gói main output thành production JAR | **`classes`** |
| `compileTestJava` | `JavaCompile` | Biên dịch Java `test` | **`classes`** và test compile classpath producers |
| `processTestResources` | `Copy` | Copy test resources | Input resource của test |
| `testClasses` | Aggregate | Chuẩn bị compiled test classes và resources | **`compileTestJava`, `processTestResources`** |
| `test` | `Test` | Chạy tests bằng test runtime classpath | **`testClasses`** và runtime classpath producers |
| `javadoc` | `Javadoc` | Sinh API documentation | **`classes`** |
| `clean` | `Delete` | Xóa project build directory | Không tự là dependency của `build` |
| `assemble` | Lifecycle | Chuẩn bị artifacts | **`jar`** trong Java project chuẩn |
| `check` | Lifecycle | Chạy nhóm verification | **`test`** trong Java project chuẩn |
| `build` | Lifecycle | Packaging + verification | **`assemble`, `check`** |

Task loại `JavaCompile`/`Jar`/`Test` làm hành động thật. `classes`, `testClasses`, `assemble`, `check`, `build` là **lifecycle/aggregate tasks**: về cơ bản chúng phụ thuộc tasks khác và không tự compile/đóng gói một lần nữa.

Khi nói `compileTestJava` phụ thuộc `classes`, có nghĩa **test compile được phép dùng compiled main classes và resources phù hợp**. Điều này không có nghĩa test JAR phải được tạo trước. Với một classpath gồm dependency từ project khác, graph có thể bổ sung task `jar` của project đó, không phải luôn của project hiện tại.

### 4.1. Task graph chuẩn được vẽ thế nào?

Hướng từ task cha xuống task cần hoàn tất trước:

~~~text
build
├── assemble
│   └── jar
│       └── classes
│           ├── compileJava
│           └── processResources
└── check
    └── test
        └── testClasses
            ├── compileTestJava
            │   └── classes
            └── processTestResources

javadoc
└── classes

clean (task độc lập, không được build gọi tự động)
~~~

Đây là **sơ đồ đơn giản hóa** để học; mỗi node `classes` thực ra là **cùng một task**, không phải hai bản sao chạy hai lần. Task dependencies phát sinh từ project dependencies, file inputs và các plugins khác có thể mở rộng graph.

Vài quy tắc quan trọng:

- **`build` phụ thuộc cả `assemble` và `check`.** Một Java build chuẩn sẽ vừa chuẩn bị JAR, vừa chạy unit tests.
- **`assemble` không mặc định chạy `test`.** Chọn assemble để làm artifact, nhưng không dùng kết quả ấy thay cho test verification.
- **`check` không mặc định đóng JAR.** Chọn check để chạy kiểm tra (trong Java plugin chuẩn có `test`).
- **`jar` không mặc định chạy unit tests.** Nó lấy main output từ `classes`.
- **`test` không mặc định đòi JAR của chính project**. Nó cần test classes/resources và main/test runtime classpath.
- **`javadoc` không mặc định được gọi bởi `build` trong Java plugin chuẩn**, dù là một task hữu ích để tạo documentation.
- **`clean` không tự chạy trước `build`**, vì như vậy sẽ phá lợi ích incremental/up-to-date của Gradle.

### 4.2. Đồ thị task là DAG, không phải thứ tự cố định

Đồ thị bảo đảm **những task có phụ thuộc phải sẵn sàng đúng thứ tự**, không cam kết tất cả tasks độc lập được in theo một chuỗi duy nhất. `compileJava` và `processResources` là hai nhánh chuẩn bị `classes`; chúng không cần sắp theo thứ tự cố định trừ khi build logic thêm một quan hệ.

Nếu bật parallel execution hoặc có nhiều modules, cách các tasks được sắp lịch còn phụ thuộc khả năng chạy song song, worker limits và task relationships. Không viết script dựa trên thứ tự tình cờ trong một lần `--info`.

### 4.3. Chọn task nào theo mục tiêu?

| Bạn muốn | Lệnh | Đương nhiên chạy test? | Đương nhiên tạo main JAR? |
| --- | --- | --- | --- |
| Compile Java main | `./gradlew compileJava` | Không | Không |
| Chuẩn bị main classes/resources | `./gradlew classes` | Không | Không |
| Đóng main JAR | `./gradlew jar` | Không | Có |
| Chuẩn bị artifacts | `./gradlew assemble` | Không | Có |
| Chạy unit tests | `./gradlew test` | Có | Không mặc định |
| Chạy checks | `./gradlew check` | Có | Không mặc định |
| Build đầy đủ | `./gradlew build` | Có | Có |
| Sinh tài liệu API | `./gradlew javadoc` | Không | Không mặc định |
| Dọn outputs | `./gradlew clean` | Không | Không |

“Có” nghĩa task tương ứng có trong graph, **không có nghĩa action chắc chắn thực thi**: một task có thể `UP-TO-DATE`, `NO-SOURCE`, `FROM-CACHE` hoặc `SKIPPED`.

## 5. Task graph khác dependency graph của JAR

Cả hai đều dùng từ dependency nhưng là hai loại quan hệ:

| Loại | Node | Quan hệ | Công cụ quan sát |
| --- | --- | --- | --- |
| **Task graph** | `:compileJava`, `:jar`, `:test` | Task nào cần task nào | `./gradlew build --dry-run` |
| **Dependency graph** | Module/versions/variants như `g:a:1.0` | Thư viện nào phụ thuộc thư viện nào | `./gradlew dependencies --configuration runtimeClasspath` |

Ví dụ:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

Nó thêm Commons Lang vào classpath mà compiler/runtime cần, **không tạo một task tên CommonsLang**. Nhưng nếu project khác cung cấp dependency qua `implementation project(':library')`, các task tạo artifact của `:library` có thể được kéo vào **task graph của consumer**. Do đó nên đọc graph đúng mục đích:

~~~bash
./gradlew build --dry-run
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Không dùng report `runtimeClasspath` để trả lời “vì sao task `test` nằm trong `build`”: đó là task graph/lifecycle dependency, không phải Maven library dependency.

## 6. Demo đầy đủ: Java plugin, JUnit Jupiter và Java 17

Đây là demo single-project **có thể chạy độc lập khi đã có Gradle Wrapper thực**, JDK17 toolchain và Maven Central. Ta không dùng Application plugin để quan sát rõ Java plugin tự cung cấp những gì.

### 6.1. Cấu trúc file

~~~text
java-task-graph-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/demo/Greeting.java
    │   └── resources/app.properties
    └── test/
        ├── java/demo/GreetingTest.java
        └── resources/test.properties
~~~

Các file Wrapper là file được sinh đúng quy trình cho Gradle distribution tương thích, không phải file rỗng.

### 6.2. `settings.gradle`

~~~groovy
rootProject.name = 'java-task-graph-demo'
~~~

### 6.3. `build.gradle` hoàn chỉnh

~~~groovy
plugins {
    id 'java'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'skipped', 'failed'
    }
}
~~~

Giải thích:

1. `id 'java'` đăng ký default tasks, source sets và configurations.
2. `version = '1.0.0'` cùng `rootProject.name` giúp tên production JAR là `java-task-graph-demo-1.0.0.jar` theo quy ước.
3. `mavenCentral()` để tải JUnit, không phải nơi resolve Java plugin core.
4. `java.toolchain` chọn JDK17 cho compile/test/javadoc tasks có hỗ trợ toolchains; Gradle Daemon có thể dùng JDK khác tương thích.
5. `testImplementation` gồm JUnit Jupiter API và engine transitive dependencies để biên dịch và chạy tests.
6. `testRuntimeOnly` bổ sung Platform Launcher 1.12.0, tương ứng JUnit 5.12.0; đặc biệt quan trọng với Gradle 9+ khi runtime cần đủ dependencies tường minh.
7. `useJUnitPlatform()` nói với `test` chạy JUnit Platform tests; chỉ thêm JUnit dependency mà thiếu cấu hình có thể khiến Gradle không tìm test theo cách mong muốn.
8. `tasks.named('test', Test)` cấu hình **task đã có** theo cách lazy, không tạo một task `test` thứ hai.

Nếu dùng project thực tế có JUnit BOM, có thể quản lý Jupiter/Platform versions bằng BOM thay vì pin từng artifact; demo dùng version cụ thể để dễ tái lập.

### 6.4. `src/main/java/demo/Greeting.java`

~~~java
package demo;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String rawName) {
        String name = rawName.trim();
        if (name.isEmpty()) {
            name = "bạn";
        }
        return "Xin chào, " + name + "!";
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "Gradle" : args[0];
        System.out.println(message(name));
    }
}
~~~

Đây là class Java 17 hợp lệ. File phải đúng tên `Greeting.java` và nằm dưới package `demo`. Phương thức `message` được test mà không cần tạo một process JVM riêng cho mỗi assertion.

### 6.5. `src/main/resources/app.properties`

~~~properties
app.name=java-task-graph-demo
~~~

`processResources` copy file này vào `build/resources/main/app.properties`. `jar` đưa resources của main vào JAR cùng `Greeting.class`. Resource thuộc test không được đóng vào production JAR mặc định.

### 6.6. `src/test/java/demo/GreetingTest.java`

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;
import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void trimsWhitespace() {
        assertEquals("Xin chào, Linh!", Greeting.message(" Linh "));
    }

    @Test
    void usesFallbackName() {
        assertEquals("Xin chào, bạn!", Greeting.message("   "));
    }

    @Test
    void readsTestResource() throws IOException {
        try (InputStream stream =
                 getClass().getResourceAsStream("/test.properties")) {
            assertNotNull(stream);
            Properties props = new Properties();
            props.load(stream);
            assertEquals("test-mode", props.getProperty("mode"));
        }
    }
}
~~~

JUnit Jupiter xử lý các phương thức `@Test` (class/method có thể package-private). Vì test runtime classpath chứa test resources, `getResourceAsStream("/test.properties")` tìm thấy resource. Nếu không có resource, `assertNotNull` báo test failure.

### 6.7. `src/test/resources/test.properties`

~~~properties
mode=test-mode
~~~

`processTestResources` đặt file dưới `build/resources/test`. Task `test` sẽ có main/test outputs cùng JUnit dependencies trên runtime classpath.

### 6.8. Chạy build

~~~bash
./gradlew build
~~~

PowerShell:

~~~powershell
.\gradlew.bat build
~~~

Khi dependency repository/JDK sẵn và không có lỗi, build kết thúc với thông báo dạng:

~~~text
BUILD SUCCESSFUL
~~~

Số task và thời gian phụ thuộc Gradle version, cache, OS và các plugin khác. Một chuỗi task tiêu biểu sẽ có:

~~~text
:compileJava
:processResources
:classes
:jar
:assemble
:compileTestJava
:processTestResources
:testClasses
:test
:check
:build
~~~

Đây là **danh sách node**, không phải thứ tự stdout được cam kết. Cùng một `classes` xuất hiện trong graph một lần dù có thể được nhiều task phụ thuộc.

### 6.9. Output bạn có thể kiểm tra

Sau build thành công, các output thường ở:

~~~text
build/
├── classes/java/main/demo/Greeting.class
├── classes/java/test/demo/GreetingTest.class
├── resources/main/app.properties
├── resources/test/test.properties
├── libs/java-task-graph-demo-1.0.0.jar
├── reports/tests/test/index.html
└── test-results/test/
    └── ... kết quả test dạng XML/binary ...
~~~

Dùng JDK:

~~~bash
jar tf build/libs/java-task-graph-demo-1.0.0.jar
~~~

Các entries chính cần tìm:

~~~text
demo/Greeting.class
app.properties
~~~

`GreetingTest.class` và `test.properties` không thuộc production JAR mặc định. `META-INF/MANIFEST.MF` thường cũng có mặt, nhưng nội dung/thứ tự/timestamp của JAR không phải trọng tâm của bài.

### 6.10. Vì sao `./gradlew run` không hoạt động ở demo?

Vì ta chỉ áp dụng `java` plugin, mặc định **không có `run` task**. Lệnh:

~~~bash
./gradlew run
~~~

thường báo task `run` không được tìm thấy. Để chạy Java main ở đây mà không thêm plugin:

~~~bash
./gradlew classes
java -cp build/classes/java/main demo.Greeting
java -cp build/classes/java/main demo.Greeting Linh
~~~

Stdout của hai lệnh `java` lần lượt:

~~~text
Xin chào, Gradle!
~~~

và:

~~~text
Xin chào, Linh!
~~~

Đây là các dòng do Java program thực sự in. Lệnh `java` chạy thủ công cần Java trên `PATH`; toolchain Gradle không tự đổi Java executable của terminal. Nếu ứng dụng cần resources, phải đưa `build/resources/main` hoặc production JAR vào runtime classpath. Class `Greeting` của demo không cần resource lúc chạy.

Hoặc:

~~~bash
./gradlew jar
java -cp build/libs/java-task-graph-demo-1.0.0.jar demo.Greeting
~~~

Cũng in:

~~~text
Xin chào, Gradle!
~~~

**`java -jar` là chuyện khác:** plain JAR do Java plugin tạo **không mặc định có `Main-Class`**. Muốn `java -jar`, hãy thêm manifest và đảm bảo runtime dependencies có mặt. Với ứng dụng thực tế, `application` plugin thường là lựa chọn thuận tiện hơn.

## 7. Dùng CLI để kiểm tra đồ thị task

### 7.1. Xem task names và nhóm

~~~bash
./gradlew tasks
./gradlew tasks --all
./gradlew tasks --group build
~~~

`tasks` liệt kê task theo nhóm; `tasks --all` hiển thị thêm những task kỹ thuật như `compileJava`, `processResources`. `--group build` chỉ lọc theo nhóm; **không phải công cụ hiển thị edges đầy đủ**.

Đối với multi-project build, dùng:

~~~bash
./gradlew :app:tasks --all
~~~

nếu module `:app` thực sự tồn tại.

### 7.2. Xem thông tin task

~~~bash
./gradlew help --task compileJava
./gradlew help --task test
./gradlew help --task jar
~~~

Lệnh `help --task` thường hiển thị type/description/available options của task. Nó giúp nhận diện trách nhiệm, nhưng không thay thế task graph.

### 7.3. `--dry-run` để xem các task được chọn

~~~bash
./gradlew build --dry-run
./gradlew test --dry-run
./gradlew assemble --dry-run
~~~

`--dry-run` in ra những task sẽ được chọn mà **không thực thi task actions**. Nó không chứng minh tests pass và không tạo class/JAR mới. Một số dòng có thể có `SKIPPED` do dry run.

Ví dụ giản lược:

~~~text
:compileJava SKIPPED
:processResources SKIPPED
:classes SKIPPED
:jar SKIPPED
:assemble SKIPPED
:compileTestJava SKIPPED
:processTestResources SKIPPED
:testClasses SKIPPED
:test SKIPPED
:check SKIPPED
:build SKIPPED
~~~

Đừng coi thứ tự giữa các nhánh độc lập là quy tắc vĩnh viễn. `--dry-run` vẫn có thể cấu hình build và chạy plugin configuration logic, chỉ không thực thi task actions.

### 7.4. `--info` và test reports

~~~bash
./gradlew build --info
./gradlew test --info
./gradlew test --tests 'demo.GreetingTest'
~~~

`--info` giúp biết vì sao task chạy lại hoặc skip và có thêm log test/compilation. `--tests` lọc test class hoặc method theo pattern. HTML report của test thường ở `build/reports/tests/test/index.html`; XML results ở `build/test-results/test`.

## 8. Task ở trong graph không đồng nghĩa action đã chạy

Gradle có nhiều kết quả trạng thái:

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `UP-TO-DATE` | Input/output snapshots không đổi nên không cần chạy lại | `compileJava` sau khi code không đổi |
| `NO-SOURCE` | Không có input source hợp lệ cho task dạng source | `processResources` khi resource directory rỗng |
| `FROM-CACHE` | Lấy output task cacheable từ Build Cache | `compileJava` khôi phục class files |
| `SKIPPED` | Không chạy action theo điều kiện/quy tắc; dry-run cũng skip actions | `onlyIf` false hoặc `--dry-run` |
| `FAILED` | Task không hoàn thành | JUnit assertion fail, Java compile error |
| Không có nhãn đặc biệt | Task action được chạy hoặc lifecycle node được xử lý | `jar` tạo JAR lần đầu |

**Up-to-date checking**, **Build Cache** và **Configuration Cache** là ba cơ chế khác:

- Up-to-date kiểm tra input/output/task history trong các builds gần đây.
- Build Cache tái sử dụng output của task cacheable theo key phù hợp.
- Configuration Cache tái sử dụng trạng thái configuration/task graph, không phải byte `Greeting.class`.

Nếu code/main resources không đổi, gọi lại `./gradlew build` thường có nhiều `UP-TO-DATE`. Điều đó là **tối ưu đúng thiết kế**, không có nghĩa Gradle bỏ qua test validation sai cách.

### 8.1. Thí nghiệm thay đổi file và quan sát

Sau khi chạy build thành công:

1. Chạy `./gradlew build` lần nữa không thay file. Quan sát các task được skip do up-to-date.
2. Thay `src/main/java/demo/Greeting.java`. `compileJava` có thể thực thi, `jar` có thể tạo lại, còn test tasks có thể chịu ảnh hưởng.
3. Chỉ thay `src/test/java/demo/GreetingTest.java`. `compileTestJava`/`test` có thể chạy lại; `compileJava`/`jar` thường không phải làm lại.
4. Thay `src/main/resources/app.properties`. `processResources`/`jar` có thể chạy lại; test runtime inputs cũng có thể bị ảnh hưởng.
5. Thay `src/test/resources/test.properties`. `processTestResources`/`test` có thể chạy lại; production JAR không cần đổi.

Gradle có **compilation avoidance**: thay chi tiết implementation của main nhưng không đổi public ABI có thể giúp tránh recompilation của test source khi phù hợp. Vì vậy đừng hứa tất cả tasks downstream luôn compile lại chỉ vì thay một dòng code.

### 8.2. `clean` không thuộc graph của `build` mặc định

~~~bash
./gradlew build
./gradlew clean build
~~~

Hai lệnh có ý nghĩa khác nhau. `clean` xóa build directory trước khi tạo lại các outputs trong invocation thứ hai; nó có thể làm build chậm vì mất lợi ích incremental/up-to-date. Dùng `clean` khi cần kiểm chứng từ output trống hoặc xử lý file cũ, **không phải bước bắt buộc mỗi lần compile**.

Tương tự:

~~~bash
./gradlew build -x test
~~~

loại task `test` ra khỏi graph. Nó có thể tạo JAR nhưng **không chứng minh unit tests pass**. Nếu mục đích chỉ đóng gói, chọn `assemble` thay vì thường xuyên skip test từ `build`.

## 9. Mở rộng task graph đúng cách

### 9.1. Cấu hình task có sẵn bằng TaskProvider

~~~groovy
tasks.named('compileJava', JavaCompile) {
    options.encoding = 'UTF-8'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`tasks.named` lấy `TaskProvider` và cấu hình task do plugin đã đăng ký. Không dùng `tasks.create('compileJava')` để tạo task mới trùng tên. Với nhiều Java compile tasks:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

`configureEach` cho phép config lazy cho các task đúng type khi cần.

### 9.2. Thêm một verification task vào `check`

Ví dụ chỉ minh họa dependency, không phải security validation thực:

~~~groovy
def inspectPolicy = tasks.register('inspectPolicy') {
    group = 'verification'
    description = 'Demonstrates extending check lifecycle.'

    doLast {
        logger.lifecycle('Policy task completed')
    }
}

tasks.named('check') {
    dependsOn(inspectPolicy)
}
~~~

Sau khi thêm vào `build.gradle` và chạy `./gradlew check --dry-run`, `inspectPolicy` nằm trong task graph. Khi chạy thật, nó in `Policy task completed`. Task này chỉ in log, không có output artifact nên không nên quảng cáo nó là task cacheable.

Nếu viết verification thực tế, tốt hơn dùng plugin như Checkstyle/PMD/Spotless hoặc custom task có inputs và failure behavior rõ ràng; nối vào `check` thay vì trực tiếp ép vào `jar`.

### 9.3. `dependsOn` khác `mustRunAfter`

| Quan hệ | Ý nghĩa | Tự đưa task kia vào graph? |
| --- | --- | --- |
| `dependsOn` | Task này cần task khác hoàn tất trước | **Có** |
| `mustRunAfter` | Nếu cả hai cùng được chọn, task này phải chạy sau | **Không** |
| `shouldRunAfter` | Nếu cả hai cùng được chọn, Gradle ưu tiên thứ tự này khi có thể | **Không** |
| `finalizedBy` | Chạy finalizer khi task được chạy theo quy tắc của Gradle | **Có** với quan hệ finalizer |

Nếu một custom task tiêu thụ file do task khác tạo, dùng `dependsOn` hoặc tốt hơn **wire output Provider** vào input property để Gradle hiểu dependency dữ liệu. Chỉ dùng `mustRunAfter` cho yêu cầu thứ tự thật sự, không dùng nó để che việc thiếu dependency.

### 9.4. Tạo JAR có main manifest

Demo chỉ có một Java class không cần external runtime deps. Nếu muốn dùng `java -jar`, thêm:

~~~groovy
tasks.named('jar', Jar) {
    manifest {
        attributes 'Main-Class': 'demo.Greeting'
    }
}
~~~

Sau đó:

~~~bash
./gradlew jar
java -jar build/libs/java-task-graph-demo-1.0.0.jar
~~~

Output chương trình:

~~~text
Xin chào, Gradle!
~~~

Đây là một **trích đoạn tùy chọn**, không thuộc base demo. Với app có thư viện runtime ngoài, plain JAR **không tự chứa toàn bộ dependency JARs**: chỉ đặt Main-Class chưa đủ. Dùng Application plugin để tạo distribution/start scripts hoặc packaging strategy rõ ràng nếu cần bundle dependencies.

## 10. Javadoc, sources JAR và thêm source sets

`javadoc` được Java plugin tạo để sinh API documentation từ main source; nó có thể được chạy riêng:

~~~bash
./gradlew javadoc
~~~

`build` chuẩn không mặc định cần `javadoc`. Nếu muốn xuất sources JAR, Java plugin có API:

~~~groovy
java {
    withSourcesJar()
}
~~~

Nó bổ sung `sourcesJar`/artifact tương ứng và có thể thay đổi assembly/publishing graph tùy cách project cấu hình. Đừng suy rằng `sourcesJar` và `javadocJar` đã có trong build chỉ dùng `plugins { id 'java' }` trước khi bật các lựa chọn đó.

Nếu tạo thêm `sourceSets.integrationTest`, Gradle còn có thể tạo `compileIntegrationTestJava`, `processIntegrationTestResources` và `integrationTestClasses`. Tuy nhiên không tự tạo một task `integrationTest` chạy tests cho mọi source set mới; phải cấu hình test suite hoặc một `Test` task/target thích hợp. Các task names đều theo source set/plug-in và cần kiểm tra bằng `tasks --all`.

## 11. Multi-project build và Java task paths

Giả sử `settings.gradle` có:

~~~groovy
rootProject.name = 'multi-demo'
include 'app', 'library'
~~~

Trong `app/build.gradle` có thể dùng:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation project(':library')
}
~~~

Đây là **trích đoạn**, không phải project hoàn chỉnh: `:library` phải thực sự tồn tại và được cấu hình plugin/variants đúng. Khi `:app` cần output từ `:library`, Gradle có thể đưa vào graph các task producer của `:library`, ví dụ `:library:jar`, tùy selected variant.

Để chỉ định chính xác task của module:

~~~bash
./gradlew :app:build
./gradlew :app:test
./gradlew :library:jar
./gradlew :app:tasks --all
~~~

Đừng coi một lệnh `./gradlew tasks --all` ở root đủ giải thích mọi task của mọi module; dùng task path đầy đủ khi cần chẩn đoán.

## 12. Những lỗi thường gặp

| Hiện tượng | Vì sao? | Cách xử lý |
| --- | --- | --- |
| `Task 'run' not found` | Core `java` không tạo task `run` | Dùng `application` hoặc tự cấu hình `JavaExec` đúng classpath |
| `Could not find method implementation()` | Project chưa áp dụng plugin tạo configuration | Kiểm `plugins { id 'java' }` |
| `compileJava NO-SOURCE` | Không có `.java` ở main source dirs | Kiểm `src/main/java`, package, `sourceSets` |
| `processResources NO-SOURCE` | Không có main resources | Bình thường nếu không có resources |
| `compileTestJava NO-SOURCE` | Test source không tồn tại | Kiểm `src/test/java` |
| Không tìm thấy JUnit tests | Thiếu JUnit deps, Launcher, `useJUnitPlatform()` hoặc sai test layout | Kiểm test classpath và JUnit config |
| `:test FAILED` | Assertion fail hoặc test runtime lỗi | Xem HTML/XML test reports, `--info` |
| `assemble` không chạy test | Nó gắn với artifact branch, không phải check branch | Dùng `build`/`check` |
| `jar` thành công khi tests fail | Jar task không mặc định phụ thuộc test | Dùng `build` để verify trước release |
| `build` không tạo Java API docs | `javadoc` không tự là dependency của build | Chạy `javadoc` hoặc attach lifecycle có chủ đích |
| `java -jar` báo no main manifest | Plain JAR chưa có `Main-Class` | Cấu hình manifest hoặc Application plugin |
| `java -jar` thiếu class bên ngoài | Plain JAR không chứa các runtime dependencies | Dùng classpath/distribution đầy đủ |
| `UP-TO-DATE` bị hiểu là lỗi | Gradle thấy inputs/outputs không đổi | Dùng `--info` để xem task history |
| Resource không có trong JAR | Đặt sai `src/main/resources` hoặc exclude | Kiểm `processResources` và `jar tf` |
| Gradle dùng JDK khác dự kiến | Toolchain/Daemon JVM khác nhau | Kiểm `java.toolchain` và `./gradlew --version` |
| Root build không có `runtimeClasspath` | Root chưa áp dụng Java plugin | Chạy report trong đúng module |
| Chạy `clean build` quá chậm | Outputs bị dọn trước khi incremental | Tránh `clean` khi không cần |
| Custom verification task không chạy | Chưa nối vào `check` | Dùng `tasks.named('check') { dependsOn(...) }` |

### Quy trình chẩn đoán

~~~text
Plugin có đúng? java / application / java-library
              |
              v
Source set/layout đúng? src/main và src/test
              |
              v
Task có tồn tại? tasks --all / help --task
              |
              v
Graph có task đó? build --dry-run
              |
              v
Action chạy hay được skip? --info / NO-SOURCE / UP-TO-DATE
              |
              v
Compiler/test classpath đúng? dependencies / dependencyInsight
              |
              v
Xem build/libs và test reports, chỉnh input rồi chạy lại
~~~

## 13. Bài tập thực hành và đáp án

**Bài A — đọc lifecycle.** `./gradlew build` yêu cầu những lifecycle tasks cấp dưới nào? **`assemble` và `check`**. Java plugin nối `assemble` tới `jar`, `check` tới `test`.

**Bài B — đóng JAR không chạy tests.** Chọn `./gradlew jar` hoặc `./gradlew assemble` nếu chỉ cần artifact. Khi cần verify trước phát hành, chạy `./gradlew build`.

**Bài C — chạy test không tạo JAR?** `./gradlew test` cần test classes cùng main/test classpaths; không nhất thiết phải đóng JAR của chính project. Quan sát `test --dry-run`.

**Bài D — đổi một Java test.** Sửa `GreetingTest.java`, chạy `./gradlew build --info`. Dự đoán `compileTestJava`/`test` được làm lại, còn `compileJava`/`jar` có thể vẫn up-to-date.

**Bài E — thêm resource.** Tạo `src/main/resources/new.properties`, chạy `./gradlew jar`, kiểm `jar tf`. File phải có trong production JAR; test resource thì không.

**Bài F — `java -jar` khác `java -cp`.** Không có manifest Main-Class, dùng `java -cp path/to/file.jar demo.Greeting`. Sau khi cấu hình `jar.manifest`, dùng `java -jar` cho demo đơn giản.

**Bài G — task tùy chỉnh.** Tạo `inspectPolicy` và gắn vào `check` như mục 9.2. Chạy `./gradlew check --dry-run` để xem node mới; giải thích vì sao không cần thay `build.dependsOn`.

**Bài H — test resource.** Đổi `mode=test-mode` thành `mode=unexpected`, chạy `./gradlew test`. Test `readsTestResource` phải fail, báo cáo trong `build/reports/tests/test/index.html`.

**Bài I — source set thứ ba.** Tạo source set `integrationTest`, chạy `tasks --all`. Tìm `compileIntegrationTestJava` và `processIntegrationTestResources`; giải thích vì sao cần thêm JVM Test Suite/Test task để chạy integration tests.

**Bài J — multi-project.** Khi `:app` phụ thuộc `:library`, hãy quan sát `./gradlew :app:build --dry-run`. Các task `:library` xuất hiện theo producer/variant dependency, không phải vì mọi module trong settings luôn được build.

## 14. Checklist cuối bài

1. Đã dùng `java`/`application`/`java-library` đúng loại project?
2. `src/main/java`, `src/main/resources`, `src/test/java`, `src/test/resources` đúng convention?
3. Hiểu `classes` phụ thuộc compile/resources main và `testClasses` phụ thuộc compile/resources test?
4. Hiểu `jar` phụ thuộc `classes`, `test` phụ thuộc `testClasses`?
5. Biết `build` = `assemble` + `check`, còn `clean` không tự là dependency?
6. Không suy `jar`/`assemble` luôn chạy tests, hoặc `test` luôn đóng JAR?
7. Có cấu hình Java 17 toolchain và JUnit Jupiter đúng `testImplementation`/`testRuntimeOnly`/`useJUnitPlatform()`?
8. Đã dùng Gradle Wrapper thay vì dựa vào Gradle cài global?
9. Đã thử `tasks --all`, `help --task`, `build --dry-run` và `--info`?
10. Đã phân biệt `NO-SOURCE`, `UP-TO-DATE`, `FROM-CACHE` và Configuration Cache?
11. Nếu thêm custom task, đã nối vào đúng lifecycle bằng `dependsOn` hoặc Provider output/input?
12. Khi build app, không kỳ vọng Java plugin tự cung cấp `run`, launcher hoặc JAR chứa mọi runtime dependency?
13. CI có chạy đúng `build`/`check` và custom verification tasks, không ẩn test failure bằng `-x test`?
14. Khi lỗi do JAR dependency, đã xem `dependencies`/`dependencyInsight`, không nhầm nó với task graph?

## Tài liệu tham khảo chính thức

- [Gradle — The Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): các task và dependency edges, source sets, resources, output locations.
- [Gradle — The Base Plugin](https://docs.gradle.org/current/userguide/base_plugin.html): `clean`, `assemble`, `check`, `build`.
- [Gradle — Understanding Tasks](https://docs.gradle.org/current/userguide/more_about_tasks.html): task graph, incremental execution, `UP-TO-DATE`.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): JUnit Platform, test runtime dependencies, reports.
- [Gradle — The Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): `run` và distributions.
- [Gradle — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `api` và `implementation`.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): chọn JDK compiler/test/javadoc.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.register`, `tasks.named`, `configureEach`.
- [Gradle — Command Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--dry-run`, `--info`, `-x` và các task options.
- [JUnit 5.12.0 User Guide](https://docs.junit.org/5.12.0/user-guide/): Jupiter/Platform dependencies và integration với Gradle.
