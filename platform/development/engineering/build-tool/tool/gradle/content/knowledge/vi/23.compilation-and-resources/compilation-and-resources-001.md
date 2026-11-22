# Luồng compileJava, processResources, classes và testClasses trong Gradle

## 1. Bức tranh tổng thể: hai nhánh compile và resources

Trong dự án Java, **mã Java** cần được biên dịch thành bytecode `.class`, còn **resources** như `.properties`, JSON, XML, ảnh hoặc templates cần xuất hiện trên runtime classpath ở đúng vị trí. Gradle Java plugin tách hai phần này thành các task khác nhau để theo dõi input/output và chỉ chạy lại phần công việc cần thiết.

Groovy DSL trong `build.gradle`:

~~~groovy
plugins {
    id 'java'
}
~~~

Java plugin là **core plugin** đi cùng Gradle, không yêu cầu plugin version riêng. Những task trọng tâm:

- **`compileJava`**: biên dịch main Java source.
- **`processResources`**: sao chép hoặc biến đổi main resources.
- **`classes`**: task tập hợp phụ thuộc `compileJava` và `processResources`; không tự biên dịch thêm lần nữa.
- **`compileTestJava`**: biên dịch Java test source; cần output từ `main`.
- **`processTestResources`**: sao chép hoặc biến đổi test-only resources.
- **`testClasses`**: task tập hợp phụ thuộc `compileTestJava` và `processTestResources`; **không chạy test methods**.
- **`test`**: thực thi JUnit/TestNG tests với test runtime classpath.

Bài thuộc nhóm **Biên dịch và tài nguyên** của **Build Tool Gradle**. Mục tiêu là hiểu đầu vào/đầu ra, các dependency edges của task graph, ranh giới `main`/`test`, cách xem trạng thái tasks, và dựng một demo **Java 17 + Groovy DSL + JUnit Jupiter** chạy được có main resource và test resource.

Các lệnh `./gradlew` dành cho Linux/macOS; Windows PowerShell dùng `.\gradlew.bat`. Demo cần Gradle Wrapper hợp lệ, bản Gradle tương thích Java 17, JDK 17 có thể được Gradle tìm thấy hoặc cấp qua toolchain resolver, và quyền truy cập Maven Central khi cache chưa có JUnit.

## 2. Source sets và cấu trúc thư mục chuẩn

Java plugin tạo hai source sets:

| Source set | Java source mặc định | Resources mặc định | Mục đích |
| --- | --- | --- | --- |
| `main` | `src/main/java` | `src/main/resources` | Code/resource của sản phẩm |
| `test` | `src/test/java` | `src/test/resources` | Code/resource phục vụ kiểm thử |

Các task tương ứng:

| Task | Input | Output theo convention |
| --- | --- | --- |
| `compileJava` | `src/main/java` | `build/classes/java/main` |
| `processResources` | `src/main/resources` | `build/resources/main` |
| `compileTestJava` | `src/test/java` | `build/classes/java/test` |
| `processTestResources` | `src/test/resources` | `build/resources/test` |

Ví dụ:

~~~text
project/
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   └── test/
│       ├── java/
│       └── resources/
└── build/
    ├── classes/java/
    │   ├── main/
    │   └── test/
    └── resources/
        ├── main/
        └── test/
~~~

**`sourceSets.main.output`** là tập hợp compiled main classes và processed main resources; **`sourceSets.test.output`** tương tự cho tests. Không nên coi mỗi output là một path duy nhất. Khi project có thêm Kotlin/Groovy hoặc generated sources, tập outputs có thể chứa nhiều thư mục.

Không bắt buộc mọi thư mục nguồn phải có file. Nếu không có `src/main/resources`, task `processResources` có thể `NO-SOURCE` mà build vẫn hợp lệ. Nếu chưa có test sources thì `compileTestJava` hoặc `test` cũng có thể không có việc để làm.

### 2.1. Thay đổi layout bằng sourceSets

Nếu project dùng layout tùy chỉnh:

~~~groovy
sourceSets {
    main {
        java.srcDirs = ['src/product/java']
        resources.srcDirs = ['src/product/resources']
    }
    test {
        java.srcDirs = ['src/unit/java']
        resources.srcDirs = ['src/unit/resources']
    }
}
~~~

Đây là **cấu hình thay thế**, không dán vào demo chuẩn ở phần sau nếu chưa di chuyển các files. Task `compileJava` vẫn mang tên cũ vì thuộc source set `main`; điều thay đổi là input directory.

## 3. Đồ thị task: mối quan hệ mới là điều quan trọng

Đồ thị giản lược; một nhánh nằm dưới task nghĩa là task phía trên **phụ thuộc** task phía dưới:

~~~text
:classes
  ├── :compileJava
  └── :processResources

:testClasses
  ├── :compileTestJava
  │    └── :classes
  │         ├── :compileJava
  │         └── :processResources
  └── :processTestResources

:test
  └── :testClasses
~~~

`classes` xuất hiện hai lần trên hình để dễ đọc, nhưng là **cùng một task trong một DAG**, không phải hai task bị chạy lặp. Gradle xác định graph từ task dependencies và model file inputs/outputs, không dựa vào thứ tự các dòng trong build script.

### 3.1. Các dependency edges then chốt

| Consumer/task | Những task quan trọng cần sẵn | Lý do |
| --- | --- | --- |
| `classes` | `compileJava`, `processResources` | Main bytecode và main resources |
| `compileTestJava` | `classes`, tasks cung cấp test compile classpath | Test source sử dụng main output |
| `testClasses` | `compileTestJava`, `processTestResources` | Test bytecode và test resources |
| `test` | `testClasses`, tasks cung cấp test runtime classpath | Chạy tests sau khi các đầu vào sẵn |
| `jar` | `classes` | Đóng JAR từ main output |
| `assemble` | `jar` trong Java project chuẩn | Tạo artifacts |
| `check` | `test` trong Java project chuẩn | Verification |
| `build` | `assemble`, `check` | Packaging và verification |

**Quan trọng:** `compileJava` và `processResources` không mặc định phụ thuộc trực tiếp vào nhau. `classes` đợi cả hai. Tương tự, `compileTestJava` và `processTestResources` là hai nhánh khác nhau được `testClasses` tập hợp. Đừng viết thêm `mustRunAfter` hay `dependsOn` giữa chúng chỉ vì muốn log luôn có cùng thứ tự.

### 3.2. Tại sao `testClasses` không chứng minh tests đã pass?

Task `testClasses` chuẩn bị các `.class` cho tests và test resources. Nó **không thực thi phương thức `@Test`**. Nếu lệnh:

~~~bash
./gradlew testClasses
~~~

thành công, bạn chỉ biết khâu chuẩn bị đầu vào test đã xong. Để chạy JUnit assertions:

~~~bash
./gradlew test
~~~

`test` chạy test framework và sinh báo cáo/kết quả. Đây là khác biệt thường gặp khi viết CI: chạy `testClasses` không thể thay cho `test`.

### 3.3. Chọn lệnh theo nhu cầu

| Lệnh | Công việc chính | Chạy tests? | Tạo production JAR? |
| --- | --- | --- | --- |
| `./gradlew compileJava` | Compile Java main | Không | Không |
| `./gradlew processResources` | Xử lý main resources | Không | Không |
| `./gradlew classes` | Cả hai nhánh main | Không | Không |
| `./gradlew compileTestJava` | Main output và compile test Java | Không | Không |
| `./gradlew processTestResources` | Copy test resources | Không | Không |
| `./gradlew testClasses` | Main/test outputs | Không | Không |
| `./gradlew test` | Thực thi tests | Có | Không mặc định |
| `./gradlew jar` | Đóng JAR từ main outputs | Không | Có |
| `./gradlew assemble` | Tạo artifacts | Không mặc định | Có |
| `./gradlew check` | Test/verification | Có | Không mặc định |
| `./gradlew build` | `assemble` + `check` | Có | Có |

Dòng “có” nghĩa là task được chọn theo graph thông thường, **không hứa task action luôn chạy lại**: Gradle có thể `UP-TO-DATE`, `NO-SOURCE`, `FROM-CACHE` hoặc `SKIPPED`.

## 4. `compileJava`: xử lý mã nguồn

`compileJava` là task kiểu **`JavaCompile`**. Input thường gồm:

1. Java files từ `sourceSets.main.java`.
2. Main `compileClasspath` với libraries/classes mà source import.
3. Compiler/toolchain, source/target options, encoding và processor path nếu có.
4. Những task producer cung cấp các files trên compile classpath.

Output là `.class` dưới `build/classes/java/main` theo mặc định. Nó **không** copy `messages.properties` sang `build/resources/main` và **không** đóng JAR.

Ví dụ dependency cho source Java:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

`implementation` là bucket để **khai báo** dependency; `compileClasspath` là configuration được Gradle resolve cho Java compiler. Nếu Java source không import thư viện bên ngoài, có thể không cần `implementation` nào.

### 4.1. Toolchain và UTF-8

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Java toolchain chọn JDK cho các Java tasks hỗ trợ nó. Điều này không tự đổi Java executable trong terminal và không tự đổi JVM chạy Gradle Daemon. Encoding UTF-8 giúp source có tiếng Việt được compile nhất quán giữa developer/CI.

Nếu JDK 17 không được tìm thấy và project chưa cấu hình toolchain provisioning, lỗi có thể xuất hiện **trước** khi compiler xử lý source. Đừng nhầm lỗi toolchain với thiếu `compileJava` task.

### 4.2. Annotation processors vẫn thuộc công việc compiler

Một annotation processor được khai báo qua `annotationProcessor`, không phải `processResources`:

~~~groovy
// Trích đoạn minh họa API, không phải dependency để chạy trong demo.
dependencies {
    annotationProcessor 'com.example:processor:1.0'
}
~~~

Processor có thể sinh Java source/classes/resources theo cơ chế annotation processing, nhưng đó là phần công việc của Java compilation. Đừng coi tên “process” trong `processResources` là annotation processing.

## 5. `processResources`: copy và transform tài nguyên

`processResources` có type **`ProcessResources`**, sử dụng các khả năng copy/`CopySpec` của Gradle.

Ví dụ nguồn và output:

~~~text
src/main/resources/
  messages.properties
  images/logo.png
  config/default.json

build/resources/main/
  messages.properties
  images/logo.png
  config/default.json
~~~

Theo mặc định, files được copy theo đường dẫn tương đối. Java plugin không tự biến file `.properties` thành Java class, không mặc định nội suy project version vào resources và không tự parse JSON.

### 5.1. Include và exclude

~~~groovy
tasks.named('processResources', ProcessResources) {
    exclude '**/*.bak'
    exclude '**/.DS_Store'
}
~~~

Đây là **trích đoạn tùy chọn**, không thuộc demo chính. Nếu exclude nhầm `messages.properties`, `classes` vẫn có thể hoàn thành nhưng app sẽ thiếu file khi chạy.

### 5.2. Resource filtering với `expand`

Giả sử file text `src/main/resources/build-info.properties` có:

~~~properties
build.version=$version
~~~

Đoạn Groovy DSL tùy chọn:

~~~groovy
version = '1.0.0'

def releaseVersion = project.version.toString()

tasks.named('processResources', ProcessResources) {
    inputs.property('releaseVersion', releaseVersion)
    filteringCharset = 'UTF-8'

    filesMatching('build-info.properties') {
        expand(version: releaseVersion)
    }
}
~~~

Khi chạy `./gradlew processResources`, output tương ứng là:

~~~properties
build.version=1.0.0
~~~

`expand` sử dụng Groovy template engine. `filesMatching` chỉ định đúng file text cần biến đổi; tránh gọi expand trên ảnh/JAR hoặc files nhị phân. `filteringCharset` giúp xử lý ký tự có dấu. `inputs.property` khai báo giá trị version là một input của task, để Gradle kiểm tra thay đổi theo up-to-date rules.

Đây là **biến thể độc lập**, muốn thử phải thêm file build-info và cấu hình vào build script. Base demo phía dưới giữ resources nguyên gốc để người học quan sát rõ cơ chế copy.

### 5.3. Classpath resource name

Nếu nguồn ở `src/main/resources/messages.properties`, file đầu ra ở root `build/resources/main/messages.properties`. Java có thể dùng:

~~~java
Greeter.class.getResourceAsStream("/messages.properties");
~~~

Dấu `/` đầu nghĩa là tìm từ classpath root. Nếu nguồn ở `src/main/resources/config/messages.properties`, resource name phải là `/config/messages.properties`. Package Java là `demo` **không tự làm resource chuyển vào thư mục demo**.

## 6. Demo đầy đủ: Java 17, JUnit Jupiter, main và test resources

Ta tạo một project chỉ áp dụng Java plugin (không có Application plugin), gồm Java main class đọc resource tiếng Việt và một JUnit class đọc test-only resource.

### 6.1. Cây thư mục

~~~text
compile-resources-demo/
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
    │   ├── java/demo/Greeter.java
    │   └── resources/messages.properties
    └── test/
        ├── java/demo/GreeterTest.java
        └── resources/test-only.properties
~~~

Bốn file Gradle Wrapper phải được chuẩn bị bằng cơ chế Wrapper thật; file `gradle-wrapper.jar` không thể chỉ là placeholder rỗng. Cần JDK 17 toolchain, Gradle distribution tương thích và Maven Central có thể truy cập nếu JUnit chưa có trong cache.

### 6.2. `settings.gradle`

~~~groovy
rootProject.name = 'compile-resources-demo'
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

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

Đoạn này là file độc lập dùng Groovy DSL:

- `java` tạo source sets và compile/resource/test tasks.
- `group`/`version` cùng project name giúp xác định JAR theo convention `compile-resources-demo-1.0.0.jar`.
- `java.toolchain` chọn JDK 17 cho những Java tasks được hỗ trợ.
- `testImplementation` đưa JUnit Jupiter vào test compile/runtime classpaths.
- `testRuntimeOnly` cung cấp JUnit Platform Launcher, đặc biệt quan trọng trên Gradle 9+.
- `useJUnitPlatform()` yêu cầu `test` dùng JUnit Platform để chạy `@Test` methods.
- `tasks.named('test', Test)` cấu hình task đã có theo hướng lazy; không tạo một task test khác.

### 6.4. `src/main/java/demo/Greeter.java`

~~~java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class Greeter {
    private Greeter() {
    }

    public static String greeting(String rawName) throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                 Greeter.class.getResourceAsStream("/messages.properties")) {
            if (input == null) {
                throw new IOException("Missing messages.properties");
            }
            properties.load(new InputStreamReader(input, StandardCharsets.UTF_8));
        }

        String prefix = properties.getProperty("messages.prefix");
        if (prefix == null) {
            throw new IOException("Missing messages.prefix");
        }

        return prefix + ", " + rawName.strip() + "!";
    }

    public static void main(String[] args) throws IOException {
        String name = args.length == 0 ? "Gradle" : args[0];
        System.out.println(greeting(name));
    }
}
~~~

Đây là Java 17 source hoàn chỉnh. `strip()` hỗ trợ từ Java 11. File phải tên `Greeter.java` dưới `src/main/java/demo`. Chương trình dùng Java standard library ở main runtime; JUnit chỉ phục vụ tests.

`Properties.load(Reader)` với `InputStreamReader(..., UTF_8)` được chọn để file `.properties` UTF-8 có tiếng Việt được đọc đúng. Không dùng `Properties.load(InputStream)` rồi mặc định nó sẽ hiểu UTF-8 theo cùng quy ước.

### 6.5. `src/main/resources/messages.properties`

~~~properties
messages.prefix=Xin chào
~~~

Lưu file bằng UTF-8. `processResources` copy tới `build/resources/main/messages.properties`. `Greeter.greeting("Ada")` trả `Xin chào, Ada!` và `Greeter.main` không có argument sẽ in `Xin chào, Gradle!`.

### 6.6. `src/test/java/demo/GreeterTest.java`

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import org.junit.jupiter.api.Test;

class GreeterTest {
    @Test
    void readsMainResource() throws IOException {
        assertEquals("Xin chào, Ada!", Greeter.greeting("Ada"));
    }

    @Test
    void trimsWhitespace() throws IOException {
        assertEquals("Xin chào, Mai!", Greeter.greeting("  Mai  "));
    }

    @Test
    void readsTestOnlyResource() throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                 getClass().getResourceAsStream("/test-only.properties")) {
            assertNotNull(input);
            properties.load(new InputStreamReader(input, StandardCharsets.UTF_8));
        }

        assertEquals("test", properties.getProperty("mode"));
    }
}
~~~

Test class cần `Greeter.class` từ main outputs cùng JUnit API từ `testImplementation`, nên `compileTestJava` phụ thuộc `classes`. Ba `@Test` methods chỉ thực sự được chạy bởi `test`, **không** bởi `testClasses`.

### 6.7. `src/test/resources/test-only.properties`

~~~properties
mode=test
~~~

`processTestResources` copy file tới `build/resources/test/test-only.properties`. Test runtime classpath có main outputs và test outputs, nhờ đó đọc được `messages.properties` và `test-only.properties`.

### 6.8. Chạy từng task và kiểm outputs

~~~bash
./gradlew compileJava
./gradlew processResources
./gradlew classes
./gradlew compileTestJava
./gradlew processTestResources
./gradlew testClasses
./gradlew test
./gradlew jar
~~~

Trong Windows PowerShell, ví dụ:

~~~powershell
.\gradlew.bat classes
.\gradlew.bat testClasses
.\gradlew.bat test
~~~

Các outputs tiêu biểu:

| Task | Files đáng kiểm tra |
| --- | --- |
| `compileJava` | `build/classes/java/main/demo/Greeter.class` |
| `processResources` | `build/resources/main/messages.properties` |
| `compileTestJava` | `build/classes/java/test/demo/GreeterTest.class` |
| `processTestResources` | `build/resources/test/test-only.properties` |
| `test` | `build/reports/tests/test/index.html` và `build/test-results/test` |
| `jar` | `build/libs/compile-resources-demo-1.0.0.jar` |

`classes`/`testClasses` là aggregate tasks nên không có thư mục output riêng ngoài các tasks producer. Với đúng source và resources, `test` sẽ chạy **3 JUnit Jupiter tests** và các assertions đều pass khi dependencies được resolve thành công.

### 6.9. Chạy Java main thủ công trên classpath đã chuẩn bị

Do chỉ áp dụng `java`, project **không có `run` task mặc định**. Sau `./gradlew classes`, chạy Linux/macOS:

~~~bash
java -cp "build/classes/java/main:build/resources/main" demo.Greeter
java -cp "build/classes/java/main:build/resources/main" demo.Greeter Mai
~~~

Stdout của hai lệnh:

~~~text
Xin chào, Gradle!
~~~

và:

~~~text
Xin chào, Mai!
~~~

Windows PowerShell:

~~~powershell
java -cp "build\classes\java\main;build\resources\main" demo.Greeter
java -cp "build\classes\java\main;build\resources\main" demo.Greeter Mai
~~~

Dấu ngăn cách classpath là **`:`** trên Unix và **`;`** trên Windows. `java` trong terminal phải trỏ tới Java runtime tương thích trên PATH; Gradle toolchain không tự thay Java CLI trên shell.

Nếu chạy chỉ với classes directory:

~~~bash
java -cp build/classes/java/main demo.Greeter
~~~

Java có thể ném `java.io.IOException: Missing messages.properties` vì classpath **không có build/resources/main**.

### 6.10. Thử `javac`/`java` không qua Gradle

Vì main class chỉ dùng Java standard library:

~~~bash
javac -encoding UTF-8 -d out src/main/java/demo/Greeter.java
java -cp "out:src/main/resources" demo.Greeter
~~~

Stdout:

~~~text
Xin chào, Gradle!
~~~

Ở đây resource được đọc trực tiếp từ **source directory** trên classpath, không phải output của `processResources`. Đây là phép so sánh khái niệm; nếu project dùng resource filtering, generated files, Maven dependencies hoặc plugins khác, lệnh Gradle là cách đúng để tái hiện full build.

### 6.11. Kiểm tra production JAR

~~~bash
./gradlew jar
jar tf build/libs/compile-resources-demo-1.0.0.jar
~~~

Các entries tiêu biểu:

~~~text
demo/Greeter.class
messages.properties
~~~

Không kỳ vọng có `demo/GreeterTest.class` hoặc `test-only.properties` trong JAR, vì `jar` lấy **`sourceSets.main.output`**, không lấy test output.

Có thể chạy:

~~~bash
java -cp build/libs/compile-resources-demo-1.0.0.jar demo.Greeter
~~~

Stdout vẫn là `Xin chào, Gradle!`. Nhưng `java -jar` không mặc định hoạt động vì plain JAR chưa chắc có manifest `Main-Class`. Nếu cần launcher/distribution, cân nhắc Application plugin hoặc cấu hình manifest/classpath rõ ràng.

## 7. Đọc task graph bằng CLI

Các lệnh khám phá:

~~~bash
./gradlew tasks --all
./gradlew help --task compileJava
./gradlew help --task processResources
./gradlew help --task classes
./gradlew help --task testClasses
~~~

`tasks --all` liệt kê cả các task kỹ thuật. `help --task` cung cấp thông tin về task type/description/options khi có, nhưng không phải công cụ đồ họa hóa toàn bộ graph.

### 7.1. `--dry-run` để so sánh nhánh

~~~bash
./gradlew compileJava --dry-run
./gradlew processResources --dry-run
./gradlew classes --dry-run
./gradlew compileTestJava --dry-run
./gradlew processTestResources --dry-run
./gradlew testClasses --dry-run
./gradlew test --dry-run
~~~

Dự đoán:

- `compileJava --dry-run` không tự đòi process main resources.
- `processResources --dry-run` không tự đòi Java compilation.
- `classes --dry-run` có **cả** compile và resources.
- `compileTestJava --dry-run` cần `classes`; test compiler nhìn thấy main output.
- `processTestResources --dry-run` không cần chạy compile test source theo mặc định.
- `testClasses --dry-run` có nhánh compile test và process test resources.
- `test --dry-run` có thêm task `test` nhưng **không thực thi JUnit assertions**.

Trong dry-run, task lines có thể ghi `SKIPPED` vì actions không chạy; điều đó khác một lệnh thực thi thật mà task bị skip do up-to-date hoặc no-source.

### 7.2. `--info` và classpath reports

~~~bash
./gradlew classes --info
./gradlew testClasses --info
./gradlew test --info
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

`--info` giúp chẩn đoán vì sao task chạy lại hoặc skip. `dependencies` in **dependency graph của artifacts**, không phải task graph. Phân biệt task dependency như `testClasses` phụ thuộc `compileTestJava` với library dependency JUnit nằm trên `testRuntimeClasspath`.

## 8. Khi thay đổi file, task nào phải làm lại?

| Thay đổi | Task có thể cần làm lại | Task thường không bị tác động trực tiếp |
| --- | --- | --- |
| Sửa `src/main/java/demo/Greeter.java` | `compileJava`, `jar`, có thể `test` và test compile | `processResources` nếu resource không đổi |
| Sửa `src/main/resources/messages.properties` | `processResources`, `jar`, có thể `test` | `compileJava` nếu source/classpath không đổi |
| Sửa `src/test/java/demo/GreeterTest.java` | `compileTestJava` và `test` | Main compile/main resources/production JAR |
| Sửa `src/test/resources/test-only.properties` | `processTestResources` và `test` | Main compile và production JAR |
| Đổi JUnit dependency trên test classpath | `compileTestJava` hoặc `test` tùy API/runtime | Main compile nếu main classpath không đổi |
| Đổi Java toolchain/compiler args | Java compile tasks và downstream consumers | Resource copy nếu filtering inputs không đổi |
| Đổi value cho `expand` có khai task input | `processResources` và consumers như `jar` | `compileJava` nếu Java inputs không đổi |

Không cam kết mọi task downstream luôn thực thi action. Nếu main implementation đổi nhưng **public ABI không đổi**, Gradle compilation avoidance có thể giữ `compileTestJava` up-to-date khi phù hợp. Nếu file resource thay đổi, `processResources` cần kiểm soát output, nhưng `compileJava` thường không phải compile lại.

### 8.1. Task status

| Status | Ý nghĩa |
| --- | --- |
| `UP-TO-DATE` | Inputs/outputs và lịch sử cho thấy không cần chạy lại |
| `NO-SOURCE` | Task không có source inputs cần xử lý |
| `FROM-CACHE` | Task output cacheable được phục hồi từ Build Cache |
| `SKIPPED` | Task action được bỏ theo điều kiện, ví dụ `onlyIf` false hoặc dry-run |
| `FAILED` | Task không thành công, ví dụ Java compiler error hoặc assertion fail |

**Build Cache** lưu outputs của task cacheable; **Configuration Cache** lưu trạng thái cấu hình/task graph; **dependency cache** lưu JAR/metadata từ repository. Chúng không đồng nghĩa một task `compileJava` đang `UP-TO-DATE`.

### 8.2. `clean` không phải giải pháp mặc định

~~~bash
./gradlew classes
./gradlew clean classes
~~~

`clean` xóa project build output và làm nhiều task phải tạo lại đầu ra. Điều này có thể dùng khi kiểm chứng clean build, nhưng không nên chạy trước mọi compile vì mất lợi ích up-to-date/incremental compilation.

Nếu một generated resource không được Gradle nhận ra, hãy sửa **input/output/provider wiring** thay vì luôn ép `clean`.

## 9. Classpath của main, test compile và test runtime

| Classpath/configuration | Ai dùng | Nội dung điển hình |
| --- | --- | --- |
| `compileClasspath` | `compileJava` | Libraries cho main Java compile |
| `runtimeClasspath` | Main execution tasks | Main output và runtime libraries |
| `testCompileClasspath` | `compileTestJava` | Main output, JUnit API/test compile libs |
| `testRuntimeClasspath` | `test` | Main output, test output, JUnit engine/launcher/runtime libs |

Đây là diễn giải khái niệm: Gradle thực tế kết hợp source set outputs, configurations, variants và FileCollections. Khi `GreeterTest` gọi `Greeter.greeting`, test compiler cần biết class `Greeter` được biên dịch ở main. Vì vậy có dependency tới `classes`.

`testClasses` thành công **không bảo đảm JUnit runtime hoàn chỉnh**: thiếu launcher/engine có thể làm `test` fail dù test `.class` đã được tạo. Đây là lý do `testImplementation`, `testRuntimeOnly` và `useJUnitPlatform()` có vai trò khác nhau.

## 10. Mở rộng compile/resource tasks một cách an toàn

### 10.1. Cấu hình task có sẵn qua TaskProvider

~~~groovy
tasks.named('compileJava', JavaCompile) {
    options.encoding = 'UTF-8'
}

tasks.named('processResources', ProcessResources) {
    exclude '**/*.bak'
}
~~~

`tasks.named` lấy **TaskProvider** của task đã được plugin tạo; không `tasks.create` một task khác trùng tên `compileJava`. Với nhiều JavaCompile tasks, dùng `tasks.withType(JavaCompile).configureEach` để hỗ trợ configuration avoidance.

### 10.2. `dependsOn` khác `mustRunAfter`

| API | Nghĩa | Tự đưa task khác vào graph? |
| --- | --- | --- |
| `dependsOn` | Consumer cần producer hoàn thành | Có |
| `mustRunAfter` | Chỉ ép thứ tự khi cả hai đã được chọn | Không |
| `shouldRunAfter` | Ưu tiên thứ tự mềm | Không |
| `finalizedBy` | Task finalizer được thực thi theo quan hệ finalizer | Có |

Nếu task tùy chỉnh sinh resource cho `processResources`, cần **wire output Provider** của producer vào input resource directory/file của consumer hoặc khai báo `dependsOn` đúng, không chỉ `mustRunAfter`. Điều đó giúp Gradle theo dõi task graph, cacheability và thay đổi input.

### 10.3. Task để xem quan hệ `classes`

~~~groovy
def reportMain = tasks.register('reportMainPrepared') {
    group = 'verification'

    dependsOn(tasks.named('classes'))

    doLast {
        logger.lifecycle('Main outputs are prepared')
    }
}
~~~

Gọi:

~~~bash
./gradlew reportMainPrepared
~~~

Task sẽ kéo `classes`, `compileJava` và `processResources` vào graph, rồi in:

~~~text
Main outputs are prepared
~~~

Đây là task minh họa **chỉ in log**, không phải task kiểm tra tính hợp lệ của Java program. Với build production, gắn task custom vào lifecycle phù hợp và khai báo inputs/outputs nếu tạo artifacts.

## 11. Những sai lầm phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `compileJava NO-SOURCE` | Không có main `.java` đúng thư mục | Kiểm `src/main/java` và `sourceSets.main.java` |
| `processResources NO-SOURCE` | Không có main resource files hoặc source dir sai | Kiểm `src/main/resources` |
| `classes` pass nhưng Java runtime không tìm resource | Chỉ thêm classes dir vào classpath hoặc resource file sai path | Kiểm `build/resources/main` và `-cp` |
| `compileTestJava` không thấy class main | Test classpath bị override hoặc main source chưa compile | Kiểm `classes`/`testCompileClasspath` |
| `compileTestJava` không biết `@Test` | Thiếu JUnit `testImplementation` | Kiểm test compile classpath |
| `processTestResources NO-SOURCE` | Không có test resources | Kiểm `src/test/resources` |
| `testClasses` pass mà tests chưa chạy | `testClasses` là aggregate, không phải execution | Chạy `test` |
| `test` báo thiếu JUnit Launcher | Thiếu test runtime dependency | Thêm `testRuntimeOnly` phù hợp |
| Test không đọc được `test-only.properties` | Resource không copy đúng hoặc classpath sai | Kiểm `build/resources/test` |
| Production JAR chứa test resource | Tùy biến `jar` lấy sai output | Kiểm `sourceSets.main.output` và `jar tf` |
| `jar` không xuất hiện sau `classes` | `classes` không đóng JAR | Chạy `./gradlew jar` |
| `java -jar` thiếu Main-Class | Plain Java plugin JAR chưa có manifest entry point | Dùng `java -cp` hoặc Application plugin |
| Resource filtering làm hỏng binary | `expand` áp vào file không phải text | Giới hạn `filesMatching` |
| `--dry-run` hiện SKIPPED | Dry-run không chạy task actions | Không kết luận tests đã pass |
| `clean classes` mới sửa được lỗi | Generated task input/output wiring sai | Sửa producer/consumer wiring |

### 11.1. Quy trình debug

~~~text
Plugin 'java' đã được apply đúng project?
            |
            v
Source files và resources ở đúng main/test directories?
            |
            v
tasks --all: các task có tồn tại?
            |
            v
classes/testClasses --dry-run: graph chọn những task nào?
            |
            v
--info: task chạy, UP-TO-DATE hay NO-SOURCE?
            |
            v
build/classes và build/resources: output nào thiếu?
            |
            v
testCompileClasspath và testRuntimeClasspath đúng?
            |
            v
Sửa source path, filtering, dependency, toolchain hay task wiring
~~~

## 12. Bài tập thực hành và đáp án gợi ý

**Bài 1.** `./gradlew compileJava` có tự copy `messages.properties` không? **Không mặc định.** `processResources` chịu trách nhiệm, còn `classes` gom cả hai nhánh.

**Bài 2.** `./gradlew testClasses` có chạy ba JUnit methods không? **Không.** Muốn chạy và xem test report phải gọi `./gradlew test`.

**Bài 3.** Test source gọi `Greeter.greeting("Ada")`. Tại sao `compileTestJava` phụ thuộc `classes`? Vì compiler phải có main compiled output trên test compile classpath.

**Bài 4.** Runtime báo `Missing messages.properties` khi dùng `java -cp build/classes/java/main demo.Greeter`. Thêm `build/resources/main` vào classpath, hoặc dùng production JAR chứa resource.

**Bài 5.** Chỉ sửa `src/test/resources/test-only.properties`. Dự đoán `processTestResources` và `test` có thể chạy lại; production `jar` thường không bị ảnh hưởng.

**Bài 6.** `processResources NO-SOURCE` trong project không có resources có phải lỗi? **Không.** Chỉ cần điều tra khi application thật sự cần file resource mà output không có.

**Bài 7.** Trong `build.gradle`, `filesMatching('build-info.properties')` và `expand(version: releaseVersion)` tạo gì từ file `build.version=$version`? Với `version='1.0.0'`, output là `build.version=1.0.0`.

**Bài 8.** Vì sao test-only resource không nằm trong main JAR? Bởi `jar` dùng `sourceSets.main.output` thay vì `sourceSets.test.output`.

**Bài 9.** Đăng ký task `reportMainPrepared` phụ thuộc `classes`, chạy `./gradlew reportMainPrepared --dry-run`. Graph sẽ có main compile và resources, nhưng task actions không chạy trong dry-run.

**Bài 10.** Với multi-project build, `:app` có `implementation project(':library')`, `:app:compileJava` có thể kéo task producer của `:library` vào graph. Phần mở rộng này đến từ **project dependency/variant inputs**, không có nghĩa hai project có chung một task `classes`.

## 13. Checklist và tài liệu đọc tiếp

1. `compileJava` biến `.java` thành `.class`; `processResources` copy/transform non-Java resources.
2. `classes` phụ thuộc **cả `compileJava` và `processResources`**, không phải Java compiler khác.
3. `compileTestJava` cần main output, nên phụ thuộc `classes` cùng test compile classpath producers.
4. `processTestResources` chỉ chuẩn bị test resources, không chạy tests.
5. `testClasses` phụ thuộc `compileTestJava` và `processTestResources`, **không thực thi JUnit methods**.
6. `test` chạy JUnit Platform với đúng test runtime classpath/Launcher/engine.
7. Main/test outputs nằm ở `build/classes/java` và `build/resources` theo source set, trừ khi được tùy chỉnh.
8. Java runtime classpath phải chứa cả compiled classes và resource roots nếu chương trình load file bằng classloader.
9. Production `jar` theo mặc định chỉ lấy main output, không mang test-only classes/resources.
10. `--dry-run` giúp nhìn task DAG; `--info` giúp xem nguyên nhân chạy/skip.
11. Phân biệt `NO-SOURCE`, `UP-TO-DATE`, `FROM-CACHE` và các loại Gradle caches.
12. Với task custom, dùng `TaskProvider` và wire input/output hoặc `dependsOn` đúng, không dùng `mustRunAfter` thay dependency dữ liệu.
13. Dùng Gradle Wrapper và Java 17 toolchain nhất quán giữa máy dev/CI.
14. Khi mục tiêu là verify tests, chạy `test` hoặc `build`, không dừng ở `testClasses`.

Tài liệu chính thức:

- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): source sets, `compileJava`, `processResources`, `classes`, `compileTestJava`, `testClasses` và quan hệ task.
- [Gradle — Working With Files](https://docs.gradle.org/current/userguide/working_with_files.html): CopySpec, `expand`, filtering, resource paths.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `test` và cấu hình JUnit Platform.
- [Gradle — Base Plugin](https://docs.gradle.org/current/userguide/base_plugin.html): `assemble`, `check`, `build`, `clean`.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): compiler/toolchain Java 17.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `TaskProvider`, `tasks.named`, `configureEach`.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): inputs, outputs, up-to-date checking.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--dry-run`, `--info` và task selection.
- [JUnit 5.12.0 User Guide](https://docs.junit.org/5.12.0/user-guide/): Java 17-compatible JUnit Jupiter syntax và test execution.
