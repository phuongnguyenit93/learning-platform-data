# Classpath biên dịch, runtime, kiểm thử và annotation processor trong Gradle

Một ứng dụng Java dùng Gradle có thể **biên dịch thành công nhưng lỗi lúc chạy**, hoặc **chạy được nhưng không biên dịch được test**, hoặc **đã khai báo Lombok nhưng compiler không tạo getter**. Những trường hợp này thường không phải lỗi cú pháp Java mà do dependency nằm trên **sai classpath**.

Trong Gradle, *classpath* là tập các thư mục và JAR mà một tác vụ cần nhìn thấy ở một **thời điểm nhất định**. Java compiler, Java runtime, test compiler, test runner và annotation processor **không nhất thiết dùng cùng một tập thư viện**. Gradle mô hình hóa các tập đó bằng những *dependency configurations* khác nhau để giảm phụ thuộc thừa, giữ API rõ ràng và giúp build tái lập.

Mục tiêu của bài:

- Phân biệt rõ **compile classpath**, **runtime classpath**, **test compile/runtime classpaths** và **annotation processor path**.
- Chọn đúng `implementation`, `api`, `compileOnly`, `runtimeOnly`, `testImplementation`, `testRuntimeOnly`, `annotationProcessor`, `testAnnotationProcessor`.
- Hiểu khi nào dependency truyền đến project tiêu thụ, khi nào chỉ dùng nội bộ và khi nào cần đặt trên **hai classpaths riêng**.
- Chạy một ví dụ Gradle Kotlin DSL dùng Java 17+, SLF4J, Lombok và JUnit 5; kiểm tra phụ thuộc bằng Gradle CLI.
- Chẩn đoán `cannot find symbol`, `NoClassDefFoundError`, `ClassNotFoundException` và annotation processor không hoạt động.

## 1. Classpath không phải “mọi JAR mà Gradle tải xuống”

Java dùng nhiều nhóm classpath phục vụ từng việc:

| Nhóm | Ai sử dụng? | Thời điểm | Nội dung điển hình | Không nên nhầm với |
| --- | --- | --- | --- | --- |
| **Main compile classpath** | `javac` biên dịch `src/main/java` | Task `compileJava` | Thư viện API mà mã nguồn main cần tham chiếu, `implementation`, `compileOnly` | Dependencies chỉ dùng khi chạy |
| **Main runtime classpath** | JVM thực thi main hoặc các task tiêu thụ main output | Task `run`, runtime, các task liên quan | Main classes/resources, `implementation`, `runtimeOnly` và dependencies phù hợp | Annotation processors và test libraries |
| **Test compile classpath** | `javac` biên dịch `src/test/java` | Task `compileTestJava` | Main output, các API cần cho test, `testImplementation`, `testCompileOnly` | Main compile classpath trọn vẹn |
| **Test runtime classpath** | JVM chạy JUnit/test engine | Task `test` | Main/test outputs, dependency chạy của ứng dụng, `testImplementation`, `testRuntimeOnly` | Chỉ các compile-time annotations |
| **Annotation processor path (main)** | `javac` tìm và thực thi annotation processors khi compile main | Task `compileJava` | `annotationProcessor` cùng runtime dependencies của processor | Main compile/runtime classpath |
| **Annotation processor path (test)** | `javac` khi compile test | Task `compileTestJava` | `testAnnotationProcessor` | Main `annotationProcessor` mặc định |

Một số điểm cần nhớ:

1. **Classpath là kết quả sau phân giải dependency**, không đơn thuần là các dòng bạn viết trong `dependencies { }`. Gradle có thể thêm phụ thuộc bắc cầu (*transitive*), lựa chọn variant và quyết định version phù hợp.
2. **Java toolchain/JDK không phải dependency classpath.** JDK cung cấp compiler, runtime và Java standard library. Còn classpath Gradle chứa các thư viện/code bổ sung của ứng dụng; module path cũng có thể được sử dụng với Java modules.
3. **Test có classpath riêng** vì test phải nhìn thấy ứng dụng **và** test framework, nhưng JUnit thường không cần có trong artifact production.
4. **Annotation processor chạy trong quá trình biên dịch**, tạo source/classes hoặc metadata. Không có lý do mặc định đưa processor lên classpath khi chạy ứng dụng.

Với Java plugin, Gradle cung cấp các configuration tên `compileClasspath`, `runtimeClasspath`, `testCompileClasspath` và `testRuntimeClasspath` để phản ánh những tập dependencies phù hợp. Ngoài ra có configuration `annotationProcessor` và `testAnnotationProcessor` dành cho processor.

## 2. Phân biệt configuration để **khai báo** với configuration để **phân giải**

Trong build script, bạn thường khai báo **ý định** bằng:

```kotlin
plugins {
    java
}

dependencies {
    implementation("org.slf4j:slf4j-api:2.0.17")
    runtimeOnly("org.slf4j:slf4j-simple:2.0.17")
    compileOnly("org.projectlombok:lombok:1.18.36")
    annotationProcessor("org.projectlombok:lombok:1.18.36")

    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}
```

Đây là một **mảnh build script minh họa**; để Gradle tải được thư viện còn cần repositories như `mavenCentral()`. Ý nghĩa từng keyword:

- `implementation(...)`: thư viện dùng trong mã nguồn main, thông thường cần cho cả **biên dịch** lẫn **runtime**.
- `runtimeOnly(...)`: không cần nhìn thấy khi biên dịch main, nhưng cần khi chạy.
- `compileOnly(...)`: mã nguồn main cần kiểu/annotation lúc biên dịch; dependency **không tự được đưa vào runtime**.
- `annotationProcessor(...)`: dependency để compiler **thực thi processor**; **không tự đưa annotation types vào main compile classpath**.
- `testImplementation(...)`: thư viện cho **biên dịch và chạy test**, thường là test framework và helpers.
- `testRuntimeOnly(...)`: thành phần chỉ cần khi **test chạy**, ví dụ JUnit Platform launcher.
- `testCompileOnly(...)`: thư viện cần để biên dịch test nhưng không tự đưa lên test runtime classpath.
- `testAnnotationProcessor(...)`: processor chạy khi `compileTestJava` biên dịch test.

Ngược lại, `compileClasspath`, `runtimeClasspath`, `testCompileClasspath`, `testRuntimeClasspath` thường là các **configuration để phân giải**. Bạn dùng chúng để kiểm tra những gì thực sự được cấp cho compiler/runtime, **không cần khai báo mọi dependency trực tiếp vào đó**. Cấu trúc quan hệ cụ thể có thể được plugin, variant hoặc custom source set mở rộng.

### Sơ đồ khái niệm cho Java main

```text
                          Java plugin
                              |
       Khai báo dependency    |   Classpath được phân giải
       -------------------    |   -------------------------
       implementation ────────┼──> compileClasspath ──> compileJava
                  │           |
                  └───────────┼──> runtimeClasspath ──> run / main runtime
       compileOnly ───────────┼──> compileClasspath
       runtimeOnly ───────────┼──> runtimeClasspath
       annotationProcessor ───┼──> annotation processor path của compileJava
                              |
```

Các đường trong sơ đồ diễn tả **mục đích và phạm vi** chứ không phải danh sách đầy đủ các `extendsFrom`/variant inheritance nội bộ. Nên kiểm chứng graph thực tế qua lệnh Gradle thay vì giả định mỗi configuration có danh sách giống hệt nhau.

## 3. `implementation`: thư viện cho mã nguồn và runtime

Ví dụ:

```kotlin
dependencies {
    implementation("org.slf4j:slf4j-api:2.0.17")
}
```

Mã Java có thể dùng:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class LogExample {
    private static final Logger LOG =
        LoggerFactory.getLogger(LogExample.class);

    public static void print() {
        LOG.info("Example");
    }
}
```

Đoạn Java này là class hợp lệ nhưng không phải chương trình có `main`. Nó cần dependency SLF4J API trên classpath biên dịch. Khi chạy, ứng dụng cũng cần chính SLF4J API; **thường còn cần một SLF4J provider** để xử lý logging thực tế.

`implementation` dùng khi dependency là chi tiết triển khai nội bộ của project, không cần được phơi bày cho compiler của project dùng thư viện của bạn. Với project ứng dụng thông thường, đây là lựa chọn mặc định thích hợp cho hầu hết thư viện sử dụng trực tiếp trong source.

**Không nên dùng `api` chỉ vì thư viện “quan trọng”.** `api` có ý nghĩa khác khi dự án được sử dụng như **Java library** (mục 7).

## 4. `compileOnly`: cần tại compile time, không tự cung cấp tại runtime

Các trường hợp điển hình:

- Servlet API được web/container cung cấp trong môi trường chạy.
- Annotation hoặc compile-time API chỉ dùng cho code generation.
- Một thư viện interface mà môi trường triển khai **cam kết** sẽ cung cấp khi ứng dụng chạy.

Ví dụ:

```kotlin
dependencies {
    compileOnly("org.projectlombok:lombok:1.18.36")
}
```

Dòng trên giúp `javac` nhận ra lớp annotation `lombok.Getter`, nhưng **không đủ** để Gradle thực thi Lombok processor. Cần thêm `annotationProcessor` (và với một số processor phải chú ý cả transitive dependencies trên processor path).

**Quy tắc an toàn:** đừng đưa một thư viện được gọi thực sự tại runtime vào `compileOnly` trừ khi runtime khác bảo đảm sẽ cung cấp nó. Nếu không, ứng dụng có thể **compile thành công** rồi ném `ClassNotFoundException` hoặc `NoClassDefFoundError`.

Phân biệt *annotation retention*: nhiều annotation được dùng chỉ khi biên dịch và không cần ở runtime. Nhưng không phải mọi annotation đều `SOURCE`: những annotation được framework đọc qua reflection tại runtime (ví dụ một số Jakarta/Spring annotations) có thể cần thư viện chứa chúng ở runtime. Không phải cứ là annotation thì chắc chắn dùng `compileOnly`.

## 5. `runtimeOnly`: dependency chỉ phải tồn tại khi ứng dụng chạy

Một ví dụ phổ biến là backend logging:

```kotlin
dependencies {
    implementation("org.slf4j:slf4j-api:2.0.17")
    runtimeOnly("org.slf4j:slf4j-simple:2.0.17")
}
```

Mã Java biên dịch bằng kiểu `Logger` từ **SLF4J API**, không cần import kiểu từ `slf4j-simple`. Khi chạy, provider Simple SLF4J cung cấp cách ghi log.

Bởi thế:

- `slf4j-api` thuộc main compile **và** runtime classpath.
- `slf4j-simple` thuộc **runtime classpath**, thường không nằm trong compile classpath.
- Khi triển khai ứng dụng cần bảo đảm cách đóng gói/phân phối thực sự đưa runtime dependencies đến JVM; **JAR do `jar` task chuẩn tạo ra không mặc định chứa mọi JAR dependency bên trong**.

`runtimeOnly` cũng phù hợp cho JDBC driver khi mã nguồn dùng `java.sql` API hoặc được framework nạp driver ở runtime. Nếu source tự import kiểu cụ thể từ JDBC driver, `runtimeOnly` một mình lại không đủ cho compile.

Đừng dùng `runtimeOnly` để “giấu” một dependency mà chính mã Java đang import; lỗi compiler `package ... does not exist` lúc đó là kết quả đúng.

## 6. Test có **compile classpath** và **runtime classpath** riêng

Gradle Java plugin tạo `src/test/java` và `src/test/resources` theo quy ước, cùng các task `compileTestJava`, `processTestResources`, `testClasses`, `test`.

Ví dụ:

```kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}

tasks.test {
    useJUnitPlatform()
}
```

- `junit-jupiter` chứa API cần để **biên dịch test** (`@Test`, `Assertions`) và thành phần Jupiter engine qua các dependencies phù hợp.
- Launcher là thành phần cần cho Gradle/JUnit Platform khi **chạy tests**, thường không cần trong source của test.
- `useJUnitPlatform()` chỉ định Gradle Test task dùng JUnit Platform, thay vì chỉ dựa vào các framework test khác.
- Test runtime cần **main production classes**, test classes và những runtime dependencies phù hợp; test compile classpath cần main classes và test APIs.
- Test libraries **không nên lọt vào production runtime** chỉ vì project có test.

### `testCompileOnly` và `testAnnotationProcessor` có cần không?

Chỉ khi **chính các source test** cần kiểu chỉ có lúc biên dịch hoặc cần processor chạy khi biên dịch test. Ví dụ, nếu một test class cũng dùng Lombok `@Getter`, khai báo:

```kotlin
dependencies {
    testCompileOnly("org.projectlombok:lombok:1.18.36")
    testAnnotationProcessor("org.projectlombok:lombok:1.18.36")
}
```

Đây là **phần bổ sung có điều kiện** vào build script có Java plugin; không cần thêm nếu test chỉ gọi các getter đã được sinh trong **main source**, vì bytecode getter đã nằm trong main classes.

Không nên giả định rằng dependency `compileOnly` của main luôn được “thừa kế nguyên xi” vào `testCompileClasspath`, hoặc main `annotationProcessor` tự hoạt động trên test sources. Hãy coi main và test là **hai source sets có đường biên rõ ràng**, chỉ khai báo thêm khi thực tế test cần.

## 7. `api` khác `implementation` trong Java library

Với plugin:

```kotlin
plugins {
    `java-library`
}
```

Configuration `api` được thêm để thể hiện **dependency xuất hiện trong API công khai của thư viện**. Giả sử module `:model` công khai kiểu `com.fasterxml.jackson.databind.JsonNode` trong method public:

```java
package demo.model;

import com.fasterxml.jackson.databind.JsonNode;

public interface MessageParser {
    JsonNode parse(String raw);
}
```

Nếu `:model` dùng `java-library`, declaration hợp lý:

```kotlin
dependencies {
    api("com.fasterxml.jackson.core:jackson-databind:2.17.2")
}
```

Điều này giúp module tiêu thụ `:model` có dependency API Jackson cần thiết trên **consumer compile classpath** khi biên dịch mã gọi `MessageParser.parse`.

Nếu Jackson chỉ là chi tiết nội bộ của implementation và không xuất hiện trong API công khai, dùng `implementation`. Các dependency `implementation` vẫn có thể được đưa vào runtime variant của thư viện, nhưng không cần xuất hiện trên **compile classpath của consumer**.

| Scope của thư viện `:model` | Compiler của chính `:model` thấy? | Compiler project **tiêu thụ `:model`** thấy? | Runtime consumer có thể nhận dependency? |
| --- | --- | --- | --- |
| `api` | Có | **Có**, vì là public API dependency | Có, khi thuộc runtime variant |
| `implementation` | Có | **Không mặc định phơi bày** như API | Thông thường **có** qua runtime variant |
| `compileOnly` | Có | Không mặc định | **Không**, trừ môi trường khác cung cấp |
| `compileOnlyApi` | Có | Có trên compile-time API variant | Không tự cung cấp ở runtime |
| `runtimeOnly` | Không dùng cho compile | Không | Có qua runtime variant phù hợp |

Đây là **khái quát** cho project dùng `java-library` với Gradle module metadata và variant-aware resolution thông thường. Phân giải cuối cùng còn phụ thuộc producer variants, consumer attributes, capabilities và cấu hình publish.

### Quy tắc thiết kế API

- Một dependency xuất hiện trong public method parameters, return types, generic bounds, superclass/interface công khai, public annotations mà consumer compiler cần thấy → xem xét `api` hoặc `compileOnlyApi` nếu đó thực sự chỉ là compile-time contract.
- Một dependency chỉ dùng trong private method, implementation details → `implementation`.
- Dependency chỉ cho unit tests → `testImplementation` hoặc scope test phù hợp.
- Thư viện tự dùng compiler plugin/annotation processor → `annotationProcessor`, không phải `api`.

`api` không có nghĩa “tự động export mã Java của mọi thư viện như module path `requires transitive`”: cách hoạt động của Java Modules (JPMS) là lớp ngữ nghĩa khác, cần cấu hình/module descriptors phù hợp.

## 8. Annotation processor path: vì sao cần tách riêng?

JSR 269 annotation processing cho phép **compiler chạy mã processor** khi biên dịch Java. Processor có thể tạo:

- Java source mới trong `build/generated/sources/annotationProcessor/java/main` hoặc vị trí Gradle/compiler được cấu hình;
- metadata như `META-INF/services/...`;
- classes hoặc tài nguyên trợ giúp ở các vị trí do processor cho phép.

Ví dụ processor phổ biến: Lombok, MapStruct Processor, Dagger compiler, AutoService. Chúng không phải “thư viện mà ứng dụng gọi khi chạy”, dù một số annotation types hoặc runtime companion APIs có thể còn được dùng bởi ứng dụng.

### Hai classpaths cần phân biệt

1. **Compile classpath**: compiler cần nhìn thấy kiểu được mã nguồn **import**, ví dụ `lombok.Getter`.
2. **Processor path**: compiler cần tìm và chạy class triển khai `javax.annotation.processing.Processor` cùng dependencies của processor.

Với Lombok:

```kotlin
dependencies {
    compileOnly("org.projectlombok:lombok:1.18.36")
    annotationProcessor("org.projectlombok:lombok:1.18.36")
}
```

Cả hai dòng nhìn như trùng nhau, nhưng **vai trò khác nhau**. Nếu bỏ `compileOnly`, source import `lombok.Getter` có thể không compile. Nếu bỏ `annotationProcessor`, annotation được nhận diện ở compile classpath nhưng việc **sinh getter** có thể không xảy ra; nơi gọi getter sẽ lỗi `cannot find symbol`.

Gradle dùng đường dẫn annotation processor chuyên biệt, tránh phụ thuộc vào cơ chế tình cờ tự tìm processor trên regular compile classpath. Cách tách này giúp compile reproducibility, performance, bảo mật và phân tích input tốt hơn.

### Processor tạo source rồi compiler biên dịch tiếp

```text
src/main/java/demo/Greeter.java
       |
       | compileJava
       |-- main compileClasspath: lombok annotations, slf4j-api...
       |-- annotationProcessor path: lombok processor
       v
Processor xét annotations → bổ sung getter vào AST (Lombok)
       |
       v
compileJava → build/classes/java/main/demo/Greeter.class
       |
       v
run/test đọc class đã biên dịch; không cần Lombok processor runtime
```

Lombok là trường hợp đặc biệt: nó thay đổi cấu trúc compiler AST, nên không nhất thiết tạo ra một file getter Java riêng dưới `generated/sources`. Các processor chuẩn như MapStruct thường **có** Java source file được generate, nhưng muốn hiểu output cụ thể phải dựa trên processor được dùng.

### Annotation processor cho test tách biệt

`annotationProcessor` dành cho **main JavaCompile**. `testAnnotationProcessor` dành cho **test JavaCompile**. Nếu annotation chỉ có trong `src/main/java`, không cần chạy lại processor trong test. Nếu mã test dùng một annotation cần processor, khai báo riêng processor test.

**Không đồng nhất annotation processor với Kotlin compiler plugin hoặc KSP/kapt.** Dự án dùng Kotlin source có mô hình xử lý annotation và plugin chuyên biệt (`kapt`, KSP, compiler plugins) tùy Kotlin Gradle Plugin/version. Các cấu hình `annotationProcessor`/`testAnnotationProcessor` nêu ở đây tập trung vào **Java source sets và `JavaCompile`**.

## 9. Ví dụ đầy đủ: Java 17, Gradle Kotlin DSL, Lombok, SLF4J và JUnit 5

Ví dụ sau minh họa **bốn thời điểm** trong cùng dự án:

- Khi **compile main**, source sử dụng `@Getter` và `Logger`.
- Annotation processor **Lombok** thực thi để tạo getter `getName()`.
- Khi **run main**, SLF4J API và Simple provider có trên runtime classpath; Lombok processor không cần.
- Khi **compile/chạy test**, JUnit được đưa vào test classpaths chứ không thêm vào main runtime.

### 9.1. Yêu cầu môi trường và cấu trúc

Cần **JDK 17 trở lên phù hợp với bản Gradle Wrapper**; Gradle runtime JVM và Java toolchain là hai khái niệm khác nhau. Có network/Gradle cache đủ để tải dependency từ Maven Central; phiên bản tọa độ trong ví dụ là những version cố định nhằm làm kết quả có thể tái tạo trong bài học.

```text
classpath-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/demo/
    │   ├── Greeter.java
    │   └── Main.java
    └── test/java/demo/
        └── GreeterTest.java
```

Nếu chưa có Wrapper, tạo Wrapper theo hướng dẫn chính thức từ Gradle installation đã có, hoặc dùng `gradle` thay cho `./gradlew` trong môi trường phù hợp. Wrapper cần được commit đầy đủ vào repository thật.

### 9.2. `settings.gradle.kts`

```kotlin
rootProject.name = "classpath-demo"
```

### 9.3. `build.gradle.kts` — file đầy đủ

```kotlin
plugins {
    application
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

dependencies {
    // Thư viện API mà source main trực tiếp import.
    implementation("org.slf4j:slf4j-api:2.0.17")

    // Provider của SLF4J chỉ cần khi chạy.
    runtimeOnly("org.slf4j:slf4j-simple:2.0.17")

    // Annotation type ở compile classpath của main.
    compileOnly("org.projectlombok:lombok:1.18.36")

    // Mã processor chạy bởi javac khi compile main.
    annotationProcessor("org.projectlombok:lombok:1.18.36")

    // JUnit API/engine cho source và execution của test.
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")

    // Launcher phục vụ JUnit Platform khi chạy test.
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}

tasks.test {
    useJUnitPlatform()
}
```

`application` là **Gradle core plugin**, áp dụng cả Java plugin và tạo task `run`. Do đó các cấu hình `implementation`, `runtimeOnly`, `compileOnly`, `annotationProcessor`, `testImplementation`, `testRuntimeOnly` tồn tại trong ví dụ.

Bản JDK toolchain đặt là Java 17 cho task biên dịch/chạy tương ứng theo cơ chế toolchain; **nó không tự quyết định** dependency classpath nào được dùng. Khi chạy, Gradle vẫn cần JVM phù hợp để chạy Gradle itself, và resolver cần truy cập Maven Central.

### 9.4. `src/main/java/demo/Greeter.java`

```java
package demo;

import lombok.Getter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class Greeter {
    private static final Logger LOG =
            LoggerFactory.getLogger(Greeter.class);

    @Getter
    private final String name;

    public Greeter(String name) {
        this.name = name;
        LOG.debug("Created Greeter for {}", name);
    }

    public String sayHello() {
        return "Hello, " + name;
    }
}
```

Trong file này:

- Import `org.slf4j.Logger` và `LoggerFactory` yêu cầu **SLF4J API trên compile classpath**.
- `@Getter` yêu cầu **Lombok annotation type trên compile classpath**.
- `getName()` **không xuất hiện trực tiếp trong source**, mà được Lombok tạo khi `compileJava` dùng Lombok processor.
- Lệnh `LOG.debug` không bắt buộc in ra khi dùng Simple provider với mức log mặc định; nó minh họa API logging compile-time và runtime provider.

### 9.5. `src/main/java/demo/Main.java`

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter("Gradle");

        System.out.println(greeter.sayHello());
        System.out.println("Name: " + greeter.getName());
    }
}
```

Lời gọi `greeter.getName()` là kiểm chứng quan trọng: **nếu annotation processor không thực sự tạo getter**, `Main.java` sẽ không compile. Nó không phụ thuộc Lombok khi runtime vì bytecode của getter đã được tạo trong `Greeter.class`.

### 9.6. `src/test/java/demo/GreeterTest.java`

```java
package demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GreeterTest {
    @Test
    void greeterUsesGeneratedGetter() {
        Greeter greeter = new Greeter("Gradle");

        assertEquals("Hello, Gradle", greeter.sayHello());
        assertEquals("Gradle", greeter.getName());
    }
}
```

JUnit API được test compiler nhìn thấy qua `testImplementation`. Bản thân file test **không chứa annotation Lombok**, nên không cần khai báo `testAnnotationProcessor` trong ví dụ này; method `getName()` đã tồn tại trong main bytecode.

### 9.7. Lệnh chạy

Trên Linux/macOS:

```bash
./gradlew clean test --console=plain
./gradlew run --quiet
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat clean test --console=plain
.\gradlew.bat run --quiet
```

Với môi trường không tùy chỉnh logging và dependencies/JDK tương thích, **stdout của chương trình Java `Main`** là:

```text
Hello, Gradle
Name: Gradle
```

Dòng `LOG.debug` của `Greeter` mặc định thường không in vì SLF4J Simple có mức log mặc định INFO; tùy cấu hình log của môi trường, có thể xuất hiện thêm log. Ngoài stdout của chương trình, console Gradle có thể có thông báo build, deprecation hoặc progress riêng. **Không nên khẳng định toàn bộ console chỉ đúng hai dòng** trên mọi máy.

Với `./gradlew clean test`, Gradle compile main, process resources, compile test rồi chạy JUnit theo task graph; test thành công **không cần in ra stdout từ code test**. Muốn kiểm tra số lượng test và kết quả, xem report dưới thư mục `build/reports/tests/test/` khi task Test tạo report như mặc định.

### 9.8. Thử bỏ từng dependency để hiểu classpath

Chỉ thử trong project thực hành, không thay đổi code production tùy tiện.

| Tạm bỏ khỏi build script | Tác động có thể quan sát |
| --- | --- |
| `implementation("org.slf4j:slf4j-api:...")` | `Greeter.java` không biên dịch được vì import `Logger`/`LoggerFactory` không được giải quyết |
| `runtimeOnly("org.slf4j:slf4j-simple:...")` | Source vẫn có thể compile; SLF4J không có provider thực thi và có thể cảnh báo về provider, logging không hoạt động như dự kiến |
| `compileOnly("org.projectlombok:lombok:...")` | `lombok.Getter` không có trên compile classpath; lỗi import/annotation |
| `annotationProcessor("org.projectlombok:lombok:...")` | `@Getter` có thể được nhận diện nhưng getter `getName()` không được tạo, nên nơi gọi có thể báo `cannot find symbol` |
| `testImplementation("org.junit.jupiter:junit-jupiter:...")` | Test compiler không tìm được `@Test`/`Assertions`, trừ khi dependency khác tình cờ cung cấp |
| `testRuntimeOnly(...junit-platform-launcher...)` | Tùy version Gradle/JUnit, việc chạy test có thể cảnh báo hoặc thiếu launcher; nên khai báo launcher rõ theo hướng dẫn Gradle/JUnit |

Thử nghiệm có thể bị ảnh hưởng bởi dependency transitive, classpath khác hoặc Gradle cache; kết luận đúng cần xem **classpath đã resolve** thay vì chỉ dựa vào một dependency bị xóa.

## 10. Bảng quyết định: một dependency nên đặt ở đâu?

| Mục đích | Scope phù hợp | Ví dụ |
| --- | --- | --- |
| Main source import và runtime cần thư viện | `implementation` | `slf4j-api`, Jackson dùng nội bộ |
| Thư viện Java công khai kiểu của dependency cho project khác | `api` dưới `java-library` | Một public API trả về `JsonNode` |
| Compiler cần annotation/compile-time stub nhưng runtime được cấp từ nơi khác hoặc không dùng | `compileOnly` | Annotation Lombok, compile-time Servlet API trong mô hình container |
| Runtime cần provider/plugin/driver mà source không import trực tiếp | `runtimeOnly` | `slf4j-simple`, JDBC driver được framework nạp |
| Test source cần JUnit/test helpers | `testImplementation` | JUnit Jupiter, AssertJ |
| Test runtime cần engine/launcher hoặc integration fixture | `testRuntimeOnly` | JUnit Platform Launcher |
| Main Java compiler cần chạy processor | `annotationProcessor` | Lombok, MapStruct processor |
| Test compiler cần chạy processor riêng | `testAnnotationProcessor` | Lombok trên `src/test/java` nếu test dùng annotation |
| Test compiler cần annotation type compile-only | `testCompileOnly` | Lombok annotations trong test sources |
| Main public API có compile-time-only type, không muốn runtime kéo theo | `compileOnlyApi` dưới `java-library` | API annotation/compile-time contract khi phù hợp |

**Điểm mấu chốt:** từ tên dependency **không đủ** để chọn scope. Hỏi: *mã nguồn nào cần nhìn thấy loại nào, lúc nào, và class đó có phải API công khai của một library hay không?*

## 11. Một dependency có thể đổi bản trên các classpaths khác nhau

Gradle giải dependency theo **configuration, variant và dependency graph**. Do đó cùng một module có thể xuất hiện với các version khác nhau trên `compileClasspath` và `runtimeClasspath` nếu graph hoặc constraints khác nhau.

Ví dụ tưởng tượng:

```text
compileClasspath:
    lib-a:1.0 -> util:1.4

runtimeClasspath:
    lib-a:1.0 -> util:1.4
    lib-b:2.0 -> util:2.1

→ Gradle có thể chọn util:2.1 ở runtime theo rules/constraints
```

Đây là **sơ đồ khái niệm**, không phải output cố định cho mọi repository. Gradle sử dụng variant-aware resolution, platform constraints, version conflict resolution, capabilities và các quy tắc khác; hãy dùng `dependencyInsight` để biết **vì sao version được chọn** trong configuration cụ thể.

Vì vậy:

- `implementation("group:artifact:version")` là khai báo một dependency, **không có nghĩa mọi classpath luôn chỉ chứa đúng version đó**.
- Một thư viện compile được nhưng runtime dùng phiên bản API không tương thích có thể gặp `NoSuchMethodError` hoặc `NoClassDefFoundError`.
- Khi điều tra, cần so sánh cả `compileClasspath` **và** `runtimeClasspath`, đôi khi cả test runtime.

### Runtime variant của project dependency

Giả sử module `:app` khai báo:

```kotlin
dependencies {
    implementation(project(":lib"))
}
```

Nếu `:lib` dùng `java-library`, Gradle có thể chọn **API variant** của `:lib` cho `:app` compile classpath và **runtime variant** cho `:app` runtime classpath. Điều này giải thích vì sao `implementation` nội bộ của `:lib` **không bị lộ** cho compiler của consumer nhưng lại cần khi chạy.

Dùng project dependency/variant phù hợp đáng tin cậy hơn việc tự trỏ tới `../lib/build/libs/lib.jar`, vì Gradle hiểu dependency, tasks sản xuất artifact và metadata.

## 12. Annotation processors phải được coi là build-time code có quyền thực thi

Một processor không chỉ là một file chứa annotations để compiler đọc; nó là **mã Java được compiler chạy khi build**. Vì vậy:

- Chỉ dùng processor từ nguồn tin cậy, kiểm tra version và provenance.
- Cố định version hoặc dùng version catalog và dependency locking/verification nếu dự án cần reproducibility cao.
- Không đưa secret vào compiler args hay build logs không kiểm soát.
- Không gọi processor khi runtime bằng cách thêm nó vào `implementation` chỉ vì “cho chắc”.
- Khi gặp lỗi do processor không tương thích JDK, kiểm tra **phiên bản JDK compiler/toolchain** và processor version. Build chạy bằng JDK khác không nhất thiết dùng cùng compiler toolchain.

Trong JavaCompile hiện đại, annotation processor path được Gradle cấp rõ; các processor không nên được tìm ngẫu nhiên từ compileClasspath. Nếu processor xuất hiện cùng ở `compileOnly` và `annotationProcessor` như Lombok, đó là vì source cần annotation types **và** javac cần processor code riêng, không phải vì hai scope trùng nhau.

### `-proc:none` và compiler arguments

Nếu project cấu hình `options.compilerArgs.add("-proc:none")`, Java compiler sẽ **tắt annotation processing**, dù dependency processor đã tồn tại. Nếu build áp dụng custom `-processorpath` hoặc `-processor` thủ công, cần kiểm tra xung đột với cấu hình Gradle tự tạo.

Để chẩn đoán số vòng xử lý và processor được kích hoạt, có thể thêm flags compiler tạm thời:

```kotlin
import org.gradle.api.tasks.compile.JavaCompile

tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.addAll(
        listOf("-XprintRounds", "-XprintProcessorInfo")
    )
}
```

Đây là **snippet chẩn đoán** cho JDK compiler hỗ trợ các flags đó, không phải yêu cầu phải để vĩnh viễn. Log có thể khác phiên bản `javac`, và processor có thể tạo code mà không sinh file source riêng như trường hợp Lombok.

## 13. Công cụ Gradle CLI để soi đúng classpath

Từ root project ví dụ có Java plugin/Wrapper:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testCompileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencies --configuration annotationProcessor
./gradlew dependencies --configuration testAnnotationProcessor
```

Nếu cần xem classpath ở subproject `:app`, đưa path project:

```bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration annotationProcessor
```

Các lệnh này cho biết **dependency graph theo configuration**, thường liệt kê module/variant và các version đã được chọn. Chúng **không liệt kê tất cả class files thực** nằm trong từng JAR. Nếu `testAnnotationProcessor` không có declaration, output tương ứng có thể trống.

### Tìm nguyên nhân một module bị kéo vào

```bash
./gradlew dependencyInsight \
    --configuration runtimeClasspath \
    --dependency slf4j-api
```

PowerShell:

```powershell
.\gradlew.bat dependencyInsight --configuration runtimeClasspath --dependency slf4j-api
```

`dependencyInsight` tập trung vào **một dependency** trong **một configuration**, có thể hiển thị đường đến module và các nguyên nhân version selection. Thay `runtimeClasspath` bằng `compileClasspath`, `testRuntimeClasspath` hoặc configuration khác khi cần.

Khi cả compile và runtime gặp xung đột, **không chỉ xem dependency được yêu cầu trực tiếp**. Xem version **được chọn** sau resolution, các platform constraints, BOM, transitive dependencies, exclusions và variant selection.

### Task hữu ích khác

```bash
./gradlew compileJava --info
./gradlew compileTestJava --info
./gradlew test --info
./gradlew run --info
```

`--info` giúp hiểu task execution, compiler options, cache và test behavior. Không phải lúc nào log cũng in đầy đủ command line classpath; khi cần chuyên sâu, xem Gradle build scan trong phạm vi bảo mật cho phép hoặc viết công cụ chẩn đoán đọc `configurations.named("...")` theo đúng API.

**Không cố truy cập `configurations.implementation.get().resolve()` để in dependencies**: `implementation` là scope dành cho declaration và trong các bản Gradle hiện đại không phải một configuration được thiết kế để trực tiếp resolve. Dùng các *resolvable configurations* như `compileClasspath`/`runtimeClasspath`.

## 14. Lỗi phổ biến và cách xác định đúng scope

| Triệu chứng | Classpath cần điều tra | Nguyên nhân khả dĩ | Cách sửa có căn cứ |
| --- | --- | --- | --- |
| `package org.slf4j does not exist` ở `compileJava` | `compileClasspath` | Thiếu `implementation` hoặc thiếu variant | Khai báo thư viện mã nguồn main cần rồi xem resolution |
| `cannot find symbol: getName()` với `@Getter` | `annotationProcessor` và `compileClasspath` | Lombok processor không chạy, thiếu path hoặc không tương thích compiler | Kiểm tra đồng thời `compileOnly`, `annotationProcessor`, `-proc:none`, JDK |
| `package org.junit.jupiter.api does not exist` | `testCompileClasspath` | Thiếu `testImplementation` | Khai báo JUnit trong test scope |
| `ClassNotFoundException` khi chạy | `runtimeClasspath` | Class chỉ có ở `compileOnly` hoặc bị loại lúc đóng gói | Khai báo `implementation`/`runtimeOnly` tùy source usage; kiểm tra distribution |
| `NoClassDefFoundError` ở runtime | `runtimeClasspath` | Thiếu transitive dependency hoặc binary incompatible class | So compile/runtime graphs, xem packaging và selected variants |
| `NoSuchMethodError` | Thường cần so compile và runtime | Runtime dùng phiên bản thư viện không tương thích | `dependencyInsight` từng configuration; sửa constraints/versions |
| SLF4J cảnh báo không có provider | `runtimeClasspath` | Có `slf4j-api` nhưng không có provider, hoặc lệch version provider | Dùng provider runtime phù hợp; tránh nhiều provider |
| JUnit không tìm được test engine/launcher | `testRuntimeClasspath` | Thiếu JUnit Platform launcher/engine hoặc version lệch | Bổ sung dependency runtime, `useJUnitPlatform()` |
| Main code compile, test code dùng Lombok fail | `testCompileClasspath`, `testAnnotationProcessor` | Test sources cần annotations/processor riêng | Khai báo `testCompileOnly` + `testAnnotationProcessor` khi phù hợp |
| Consumer project không compile được public API của library | Consumer `compileClasspath` | Dependency của `:lib` bị khai báo `implementation` dù public API dùng kiểu đó | Với `java-library`, dùng `api`/scope public API phù hợp |
| Dependency nằm ở `annotationProcessor` nhưng ứng dụng import không thấy | Main `compileClasspath` | Processor path không phải compile classpath | Thêm annotation API/compile-only dependency cần thiết |
| Source tự import JDBC driver class nhưng chỉ có `runtimeOnly` | Main `compileClasspath` | Scope chỉ chạy không cung cấp compiler types | Dùng `implementation` nếu source thật sự dùng driver API |
| `dependencies` cho thấy version khác với khai báo | Configuration cụ thể | Conflict resolution, constraints, platforms, transitivity | Xem `dependencyInsight`, BOM và variant attributes |
| Chạy file JAR bằng `java -jar` bị thiếu thư viện | Distribution/classpath | JAR của Java plugin không chứa dependencies theo mặc định | Dùng distribution/Application plugin/classpath đúng, hoặc packaging được thiết kế riêng |

**Chú ý khi debug exception:** `ClassNotFoundException` và `NoClassDefFoundError` không hoàn toàn tương đương. Loại đầu thường phát sinh khi classloader cố tìm một tên class mà không thấy; loại sau có thể do class không được định nghĩa hoặc khởi tạo đúng khi JVM cần liên kết/sử dụng. Cả hai cần kiểm tra runtime classpath, nhưng cũng có thể liên quan đến module system, shaded JAR hoặc lỗi initialization khác.

## 15. Phân biệt dependency classpath với các “đường dẫn” khác

| Khái niệm | Tác dụng | Có phải classpath của ứng dụng? |
| --- | --- | --- |
| **Gradle Wrapper distribution** | Xác định phiên bản Gradle chạy build | Không |
| **Gradle Daemon JVM** | JVM chạy Gradle build engine/plugins | Không |
| **Java toolchain** | Chọn compiler/JDK/runtime tools cho tasks | Không |
| **Build script/plugin classpath** | Classpath để tải và chạy plugin/build logic | Không phải main/test classpath |
| **Main compile/runtime classpath** | Dependencies cho code ứng dụng | Có |
| **Test compile/runtime classpath** | Dependencies cho test code và test engine | Có nhưng trong phạm vi kiểm thử |
| **Annotation processor path** | Nơi compiler tìm processor code | Không tự là runtime classpath |
| **JPMS module path** | Nơi Java module system tìm các modules | Khác cơ chế classpath truyền thống; Gradle có thể bố trí tùy modular build |

Điều này giải thích vì sao thêm dependency vào `buildscript { dependencies { classpath(...) } }` **không** làm mã ở `src/main/java` import được class đó. Build logic và ứng dụng là **hai thế giới classloading khác nhau**.

Tương tự, plugin Gradle chạy trong Daemon có thể cần thư viện ở plugin/buildscript classpath, còn `compileJava` dùng Java toolchain/JDK và dependencies khai báo cho source set. Đừng sửa lỗi `cannot find symbol` của application source bằng cách thêm artifact vào buildscript dependencies.

## 16. Những quy tắc thực hành để tránh lỗi classpath

1. **Khai báo theo nơi thật sự dùng:** main code → `implementation`/scope main; tests → `testImplementation`; annotation processing → `annotationProcessor`.
2. **Dùng `api` có chọn lọc** với `java-library` khi dependency xuất hiện trong public contract, tránh vô tình mở rộng compile classpath cho mọi consumer.
3. **Tách annotation API khỏi processor** khi cần, như cặp Lombok `compileOnly` + `annotationProcessor`.
4. **Không nhét `runtimeOnly` vào `implementation` chỉ để dễ compile** khi source thực tế không cần nó; một classpath nhỏ hơn giúp che giấu phụ thuộc vô tình.
5. **Không đưa JUnit vào production main scope** nếu chỉ test dùng. Điều này giảm kích thước runtime và tránh side effects không mong muốn.
6. **Cố định version và giải conflict có chủ đích** bằng constraints, platforms/BOM hoặc version catalog; kiểm tra actual resolved graph.
7. **Bảo vệ reproducibility:** dùng Gradle Wrapper, dependency locking/verification và CI tests nếu dự án yêu cầu, thay vì phụ thuộc “máy tôi đã tải JAR này”.
8. **Nhớ packaging:** `compileJava`, `run` và `java -jar` có cách cấp dependencies khác nhau. Kiểm tra phân phối thực tế, không chỉ `./gradlew test`.
9. **Chẩn đoán đúng cấu hình:** compile lỗi → `compileClasspath`; runtime lỗi → `runtimeClasspath`; test compile/run lỗi → test classpaths; code generation lỗi → processor path.
10. **Không dựa vào thứ tự dependencies trong DSL** để quyết định version hay classloader order. Gradle resolver/variants và Java runtime classloader quyết định theo quy tắc của chúng.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `runtimeOnly("some-driver")` không giúp source Java import trực tiếp `com.vendor.Driver`?

**Đáp:** `runtimeOnly` không đưa thư viện đó lên **main compile classpath**. Nếu source trực tiếp tham chiếu kiểu trong driver, cần dependency compile-time thích hợp (thường `implementation`); nếu framework chỉ tải driver khi chạy thì `runtimeOnly` có thể đủ.

**Câu 2.** Với Lombok, chỉ khai báo `compileOnly("org.projectlombok:lombok:...")` thì đủ chưa?

**Đáp:** Chưa. Nó cho phép compiler nhìn thấy annotation types, nhưng processor còn phải có trên `annotationProcessor`. Ngoài ra cần compiler/JDK và thiết lập annotation processing tương thích.

**Câu 3.** Tại sao JUnit nên khai báo ở `testImplementation` thay vì `implementation`?

**Đáp:** JUnit phục vụ biên dịch/chạy test, không phải API/runtime production của ứng dụng. Test classpath đã được thiết kế có test dependencies.

**Câu 4.** Khi `:lib` trả về kiểu `JsonNode` trong method public, project tiêu thụ bị lỗi thiếu Jackson. Trong `:lib`, bạn kiểm tra scope nào?

**Đáp:** Nếu `:lib` dùng `java-library`, kiểm tra liệu Jackson được khai báo `implementation` thay vì `api` trong khi đã xuất hiện trong public API.

**Câu 5.** `compileClasspath` và `runtimeClasspath` của cùng một project có luôn chứa đúng cùng các JAR/version không?

**Đáp:** Không. `compileOnly`, `runtimeOnly`, API/runtime variants và transitive version resolution có thể tạo tập dependencies hoặc version khác nhau.

**Câu 6.** Main source đã dùng Lombok và test chỉ gọi getter đã sinh, có luôn cần `testAnnotationProcessor` không?

**Đáp:** Không. Getter đã nằm trong main bytecode sau `compileJava`. Chỉ cần processor test khi **test source** thực sự có annotation cần được xử lý lúc `compileTestJava`.

**Câu 7.** `./gradlew dependencies --configuration runtimeClasspath` có thay `./gradlew dependencies --configuration annotationProcessor` để chẩn đoán MapStruct processor không?

**Đáp:** Không. Processor path tách khỏi main runtime classpath. Xem đúng `annotationProcessor` và `compileClasspath` (cho annotation API) để xác định đường đi.

**Câu 8.** Build chạy trên JDK 21, nhưng Java toolchain là 17. Có nghĩa classpath chỉ chứa dependency hỗ trợ Java 17 không?

**Đáp:** Không tự động. Toolchain chọn compiler/JDK, còn dependencies resolve theo metadata và attributes. Bạn vẫn cần kiểm tra tương thích bytecode/API và variant selection; Gradle không bảo đảm thư viện được chọn chỉ vì toolchain được đặt 17 sẽ không yêu cầu Java mới hơn.

**Câu 9.** `java -jar build/libs/my-app.jar` không tìm thấy SLF4J nhưng `./gradlew run` chạy được. Điều này chứng minh `implementation` sai không?

**Đáp:** Chưa chắc. `run` của Application plugin cấp runtime classpath, còn JAR mặc định của Java plugin thường không đóng gói dependencies. Cần kiểm tra manifest, distribution hoặc packaging, không vội thay scope.

**Câu 10.** Một thư viện bị chọn bản 2.x trên runtime nhưng 1.x lúc compile. Dùng lệnh gì?

**Đáp:** `dependencyInsight --configuration runtimeClasspath --dependency <name>` và tương tự cho `compileClasspath`, rồi kiểm tra transitive paths/constraints và variant selection.

## 18. Tài liệu chính thức

- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): declaration/resolution roles, configurations và source sets.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): Java plugin dependency configurations, `compileJava`, `compileTestJava`, test/runtime classpaths.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `api` so với `implementation`, public API và consumer variants.
- [Gradle — Variant-Aware Resolution](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): lựa chọn API/runtime variants và attributes.
- [Gradle — Dependency Insight](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): cách xem tree và lý do chọn một dependency version.
- [Gradle — Annotation Processing](https://docs.gradle.org/current/userguide/java_plugin.html#sec:java_compile_avoidance): tách processor path khỏi compile classpath.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): `run`, application main class và distributions.
- [JUnit 5 — Running Tests: Gradle](https://junit.org/junit5/docs/current/user-guide/#running-tests-build-gradle): test engine, JUnit Platform và launcher.
- [Project Lombok — Gradle Setup](https://projectlombok.org/setup/gradle): `compileOnly`/`annotationProcessor` và cấu hình Lombok riêng cho test khi cần.
