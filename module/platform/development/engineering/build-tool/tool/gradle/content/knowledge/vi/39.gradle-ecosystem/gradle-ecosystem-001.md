# Tích hợp Kotlin JVM và phối hợp Java, Kotlin trong một Gradle project

## 1. Mục tiêu và bối cảnh

Nhiều ứng dụng JVM được viết bằng Java nhưng muốn sử dụng Kotlin cho API mới, dịch vụ, kiểm thử hoặc DSL nội bộ. Chuyển toàn bộ repository sang Kotlin trong một lần thường không cần thiết. **Gradle có thể biên dịch và đóng gói Java cùng Kotlin trong một project**, dùng chung dependency graph, Java toolchain, test lifecycle và runtime classpath.

Tuy nhiên, “cả hai cùng chạy trên JVM” không có nghĩa chỉ cần đặt các tệp **.kt** cạnh **.java** rồi gọi javac. Kotlin và Java có compiler riêng, cách mô hình hóa nullability khác nhau, cách sinh các thành viên JVM khác nhau và các task Gradle cần được liên kết đúng.

Bài thuộc **Build Tool Gradle**, nhóm **Hệ sinh thái Gradle**, với đề bài **“Tích hợp Kotlin JVM và phối hợp Java, Kotlin trong một project”**.

Sau bài học, bạn sẽ:

1. Phân biệt **Kotlin JVM plugin**, **Gradle Kotlin DSL** và **Kotlin Multiplatform plugin**.
2. Áp dụng **org.jetbrains.kotlin.jvm** vào một build Groovy DSL hoặc Kotlin DSL.
3. Hiểu mặc định **src/main/kotlin**, **src/main/java**, **src/test/kotlin**, **src/test/java**.
4. Biết cách Gradle phối hợp **compileKotlin**, **compileJava**, **compileTestKotlin**, **compileTestJava**.
5. Cấu hình **JDK toolchain 17**, Kotlin **jvmTarget**, Java bytecode target đồng nhất.
6. Viết Kotlin gọi Java class và Java gọi Kotlin class, top-level function, object và default arguments.
7. Hiểu **@file:JvmName**, **@JvmStatic**, **@JvmOverloads**, properties/getters, platform types và null safety.
8. Tạo project hỗn hợp Java 17 + Kotlin JVM 2.4.21 có Java Main và hai test classes bằng Java/Kotlin.
9. Chạy **Gradle Wrapper**, **test**, **run**, **jar**, **installDist**, kiểm tra stdout chính xác.
10. Thử **javac/java** độc lập cho phần Java thuần và hiểu vì sao không thể biên dịch cả project Kotlin bằng javac.
11. Phân biệt Kotlin stdlib, Kotlin Gradle plugin, Kotlin compiler/daemon và JUnit dependencies.
12. Tránh lỗi **Inconsistent JVM-target compatibility**, **Unresolved reference**, **cannot find symbol**, **NoClassDefFoundError**.
13. Phân tích dependency scope, source set, Java/Kotlin ABI, incremental compilation, build cache và CI.
14. Biết khi nào cần **KSP**, **kapt**, Java annotationProcessor và cách di chuyển Java sang Kotlin an toàn.
15. Đánh giá sự tương thích giữa Kotlin Gradle plugin, Gradle Wrapper, JDK và IDE, không nâng cấp chúng tùy tiện.

**Trọng tâm:** Một project có **hai ngôn ngữ nguồn** nhưng **một JVM application**, **một Gradle task graph** và **một bộ công cụ phát hành**.

## 2. Kotlin JVM plugin, Kotlin DSL và Kotlin Multiplatform là ba khái niệm khác nhau

| Thành phần | Dùng vào việc gì? | Ví dụ |
| --- | --- | --- |
| **Kotlin JVM plugin** | Biên dịch file .kt thành JVM bytecode và tích hợp với Java plugin/task graph | id 'org.jetbrains.kotlin.jvm' |
| **Gradle Kotlin DSL** | Viết Gradle build scripts bằng Kotlin thay vì Groovy | build.gradle.kts |
| **Kotlin Multiplatform** | Tạo targets/source sets cho JVM, JS, Native, Wasm... | id 'org.jetbrains.kotlin.multiplatform' |
| **Kotlin stdlib** | Các APIs/runtime classes Kotlin cần khi app chạy | org.jetbrains.kotlin:kotlin-stdlib |
| **Kotlin compiler** | Dịch .kt thành .class / metadata | Kotlin compiler do plugin điều phối |
| **Kotlin daemon** | Tiến trình compiler riêng được plugin quản lý để giảm startup | Không phải Gradle Daemon |
| **Gradle Wrapper** | Cố định distribution Gradle cho dự án | gradlew, gradlew.bat |
| **Java toolchain** | Chọn JDK phù hợp cho compile/test | jvmToolchain(17) |

Một **build.gradle** sử dụng Groovy DSL vẫn có thể biên dịch Kotlin source. Một **build.gradle.kts** sử dụng Kotlin DSL vẫn có thể chỉ chứa Java source. Hai quyết định này độc lập.

Ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'org.jetbrains.kotlin.jvm' version '2.4.21'
}
~~~

Ví dụ Kotlin DSL tương đương, **không đặt cùng trong file Groovy**:

~~~kotlin
plugins {
    kotlin("jvm") version "2.4.21"
}
~~~

**Tên plugin Kotlin/JVM** là **org.jetbrains.kotlin.jvm**. Không dùng Kotlin Multiplatform plugin chỉ vì ứng dụng có cả Kotlin và Java; cả hai đang chạy trên **một JVM target**.

## 3. Bức tranh cơ chế: source files tới JAR

Một Java/Kotlin project có thể trải qua:

~~~text
settings.gradle
       |
       v
build.gradle
  application / java plugin
  org.jetbrains.kotlin.jvm plugin
       |
       v
sourceSets.main
  src/main/kotlin/**/*.kt
  src/main/java/**/*.java
       |
       +-----------------------------+
       |                             |
       v                             |
  compileKotlin                      |
  - Kotlin compiler                 |
  - đọc declarations từ Java source |
  - sinh .class Kotlin              |
       |                             |
       v                             v
  build/classes/kotlin/main      compileJava
                                 - javac
                                 - sử dụng Kotlin compiled classes
                                 - sinh Java .class
                                     |
                          +----------+
                          |
                          v
                   classes / jar / run
                          |
                          v
                      JVM runtime
                  Kotlin stdlib + deps
~~~

Đây là **mô hình khái niệm** để thấy sự phối hợp. Gradle/Kotlin plugin thực tế sử dụng task dependency, compiler classpaths và source snapshots; chi tiết task graph có thể khác theo plugin version.

### 3.1. Kotlin nhìn thấy Java dù javac chưa tạo class files?

Kotlin Gradle plugin có thể cung cấp thông tin **Java source declarations** cho Kotlin compiler ở bước biên dịch Kotlin, nên Kotlin code có thể gọi một class Java cùng source set. Sau đó Java compiler nhìn thấy outputs của Kotlin compilation để biên dịch những Java files đang gọi Kotlin.

Bạn không cần tự thêm:

~~~groovy
tasks.named('compileKotlin') {
    dependsOn tasks.named('compileJava')
}
~~~

**Đây là anti-pattern** có thể gây dependency cycle khi Java phải dùng Kotlin compiled classes. Để Kotlin Gradle plugin quản lý mối quan hệ mặc định, trừ khi có kiến trúc task khác đặc biệt.

### 3.2. Vì sao không biên dịch tất cả bằng javac?

**javac** biên dịch Java source và không tự hiểu syntax **fun**, **val**, **data class** hay Kotlin metadata. Kotlin files cần Kotlin compiler. Từ Gradle CLI, plugin điều phối cả hai rồi tập hợp **.class** thành artifact JVM.

### 3.3. Kotlin/Java không phải hai JVM runtime khác nhau

Sau khi compile, cả Java class và Kotlin class đều chạy trong JVM. Chúng chia sẻ heap, threads, GC, class loader, Java modules và dependencies; không cần “Kotlin VM”. Kotlin stdlib vẫn có thể được ứng dụng sử dụng như một dependency runtime.

## 4. Phiên bản mẫu và điều kiện môi trường

Bài sử dụng:

- **JDK 17** để chạy compiler toolchain và source Java.
- **Kotlin Gradle plugin 2.4.21** (bản ổn định được Kotlin documentation công bố ngày 8/10/2026).
- **Gradle Wrapper 9.7** cho lab; chọn một tổ hợp version đã được Kotlin/Gradle docs kiểm tra tương thích.
- **Groovy DSL build.gradle** để trình bày plugin theo đúng syntax.
- **JUnit Jupiter 5.11.4** và **JUnit Platform Launcher 1.11.4** làm test dependencies.
- **application plugin** để chạy một Main Java class.

Kotlin 2.4.20 công bố mức tương thích đầy đủ với Gradle 7.6.3–9.7.0; Kotlin 2.4.21 là bản sửa lỗi trong cùng dòng 2.4. Nếu bạn dùng Gradle mới hơn hoặc cũ hơn, **hãy kiểm tra bảng compatibility chính thức theo đúng Kotlin plugin patch/version**, không mặc định mọi phiên bản đều hỗ trợ tất cả Gradle APIs. Gradle 9.x có yêu cầu tối thiểu đối với Kotlin Gradle plugin khác với Gradle 8.x.

Bạn có thể đọc trước:

~~~bash
java -version
javac -version
./gradlew --version
~~~

Các version in thực tế phụ thuộc máy; **không bịa output** nếu chưa chạy.

### 4.1. JDK chạy Gradle và JDK compile là hai việc

Gradle Daemon có JVM riêng. Kotlin Gradle plugin còn có compiler daemon và lựa chọn Java toolchain. Một toolchain Java 17 không có nghĩa JVM đang chạy Gradle buộc phải là cùng một đường dẫn JDK.

Điều cần thiết là: dùng một phiên bản Gradle hỗ trợ JDK chạy Gradle, và cấu hình Java/Kotlin compilation cùng target 17. Khi gặp lỗi, ghi **Gradle JVM** và **toolchain** riêng biệt.

## 5. Cấu trúc thư mục chuẩn

Một project Java/Kotlin JVM thường có:

~~~text
mixed-jvm-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── demo/mixed/
│   │   │       ├── JavaText.java
│   │   │       ├── Main.java
│   │   │       └── StandaloneCheck.java
│   │   ├── kotlin/
│   │   │   └── demo/mixed/
│   │   │       └── KotlinMessage.kt
│   │   └── resources/
│   └── test/
│       ├── java/
│       │   └── demo/mixed/
│       │       └── JavaInteropTest.java
│       ├── kotlin/
│       │   └── demo/mixed/
│       │       └── KotlinInteropTest.kt
│       └── resources/
└── .gitignore
~~~

Các thư mục **src/main/java** và **src/main/kotlin** là mặc định. Tương tự với **test**. Gradle Kotlin JVM plugin tự tạo/điều chỉnh Kotlin compilation gắn với Java source sets.

**Lưu ý từ Kotlin documentation:** Không đặt tệp **.java** trong **src/main/kotlin** theo thói quen; Java files trong thư mục Kotlin không được xử lý như Java sources theo convention. Đặt .java trong **src/main/java** và .kt trong **src/main/kotlin**. Kotlin files có thể nằm ở nơi khác nếu source sets đã được cấu hình chính xác, nhưng cấu trúc mặc định dễ hiểu và dễ được IDE nhận diện.

### 5.1. Package không nhất thiết giống folder?

Kotlin/Java dùng **package declarations** để xác định fully-qualified class name. Giữ path phản ánh package giúp tooling, source navigation và team conventions, nhưng JVM runtime dùng bytecode class name. Với Java source, public class name và file name phải đúng theo quy tắc Java.

Ví dụ:

~~~text
src/main/java/demo/mixed/Main.java
package demo.mixed;
public final class Main { ... }
~~~

và:

~~~text
src/main/kotlin/demo/mixed/KotlinMessage.kt
package demo.mixed
fun greeting(...) = ...
~~~

### 5.2. Không đưa test code vào main

Source sets **main** và **test** có classpaths/outputs riêng. JUnit chỉ khai báo ở **testImplementation** để production artifact không phải mang test engine. Test Kotlin/JVM có thể gọi Java main classes, và test Java có thể gọi Kotlin main classes nếu task wiring/visibility đúng.

## 6. settings.gradle

Tạo **settings.gradle**:

~~~groovy
rootProject.name = 'mixed-jvm-lab'
~~~

Trong lab, plugin **org.jetbrains.kotlin.jvm** mặc định được resolve qua Gradle Plugin Portal, còn JUnit/Kotlin runtime dependencies qua **mavenCentral()** ở build.gradle. Nếu tổ chức dùng artifact proxy/mirror, phải cấu hình pluginManagement và dependency repositories theo policy, không tự thay repo URL thiếu TLS.

### 6.1. Plugin resolution khác library resolution

Một lỗi resolve Kotlin plugin có thể xảy ra ở **plugins {}**, trước khi Gradle xử lý project dependencies. Khi đó thêm **mavenCentral()** vào **repositories {}** của build.gradle có thể **không sửa** được việc plugin marker không tìm thấy. Plugin resolution có cơ chế và repositories riêng.

Ví dụ cấu hình dạng tham khảo nếu tổ chức cần chỉ định plugin repo:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = 'mixed-jvm-lab'
~~~

Đây là **phương án thay thế toàn bộ settings.gradle**, không đặt hai file settings khác nhau trong một project. Không thêm private repository credentials trực tiếp vào script.

## 7. build.gradle hoàn chỉnh

Tạo **build.gradle** bằng Groovy DSL:

~~~groovy
plugins {
    id 'application'
    id 'org.jetbrains.kotlin.jvm' version '2.4.21'
}

repositories {
    mavenCentral()
}

kotlin {
    // Kotlin Gradle plugin 2.4.21
    // Cập nhật toolchain của Kotlin và các Java compile/test tasks.
    jvmToolchain(17)

    compilerOptions {
        // Sử dụng typed enum, không dùng chuỗi "17" kiểu cũ.
        jvmTarget.set(
            org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
        )
    }
}

application {
    mainClass = 'demo.mixed.Main'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release.set(17)
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'failed', 'skipped'
    }
}
~~~

Đây là **cấu hình đủ để chạy lab** nếu Wrapper/JDK/network được chuẩn bị.

### 7.1. Tại sao apply application và Kotlin JVM?

- **application** áp dụng Java ecosystem, cung cấp **run**, **startScripts**, **installDist**, **distZip**, **distTar**.
- **org.jetbrains.kotlin.jvm** thêm các Kotlin compilations, Kotlin compile tasks và hỗ trợ Java/Kotlin mixed source sets.
- Không cần thêm **id 'java'** trong trường hợp **application** đã áp dụng Java plugin.
- Kotlin stdlib được Kotlin Gradle plugin thêm tự động vào dependencies theo convention hiện hành. Có thể kiểm chứng bằng dependencies report; không lặp lại dependency version thủ công không cần thiết.

### 7.2. Vì sao jvmToolchain(17)?

Kotlin plugin hỗ trợ Java toolchains và **jvmToolchain(17)** là cách cấu hình ngắn, đồng bộ công cụ Java/Kotlin trong cùng project. Cũng có thể thiết lập Java toolchain qua **java { toolchain {...} }** và plugin sẽ dùng toolchain tương ứng cho Kotlin; nhưng trong lab chỉ chọn một cách chủ đạo để tránh hai nguồn cấu hình khác nhau.

### 7.3. Vì sao compilerOptions.jvmTarget dùng enum?

Kotlin compilerOptions DSL là API được khuyến nghị thay cho **kotlinOptions** cũ (đã deprecated từ Kotlin 2.0.0). JvmTarget là typed enum; dùng **JvmTarget.JVM_17** để tránh vô tình gán một String không đúng kiểu API.

Khi project cần target thấp hơn JDK toolchain, có thể dùng jvmTarget tương ứng **nhưng phải đồng bộ Java targetCompatibility/options.release** và bảo đảm APIs sử dụng có thể chạy trên JVM mục tiêu. Không bật chế độ bỏ qua validation để che target mismatch.

### 7.4. Java options.release và Kotlin jvmTarget không hoàn toàn giống nhau

**JavaCompile.options.release** giới hạn Java language/API level và bytecode target mà javac được phép sử dụng. Kotlin **jvmTarget** điều khiển mức JVM bytecode Kotlin compiler tạo. Kotlin plugin còn sử dụng toolchain JDK. Hai cài đặt phải phù hợp, nhưng không coi JVM bytecode version là một bảo đảm rằng mọi thư viện dùng đều tương thích Java 17.

### 7.5. Cần nhớ Gradle Kotlin DSL là lựa chọn riêng

Nếu dùng **build.gradle.kts**, cùng ý tưởng có dạng:

~~~kotlin
plugins {
    application
    kotlin("jvm") version "2.4.21"
}

repositories {
    mavenCentral()
}

kotlin {
    jvmToolchain(17)
    compilerOptions {
        jvmTarget.set(
            org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
        )
    }
}

application {
    mainClass.set("demo.mixed.Main")
}
~~~

Đây là **snippet đối chiếu DSL**, không phải bản thay thế đầy đủ của lab Groovy vì chưa khai báo JUnit dependencies và test tasks. Không trộn cú pháp **mainClass.set(...)** vào mọi Groovy snippet một cách mù quáng hoặc viết **kotlin("jvm")** trong Groovy plugins block.

## 8. JavaText.java: một Java class được Kotlin gọi

Tạo **src/main/java/demo/mixed/JavaText.java**:

~~~java
package demo.mixed;

public final class JavaText {
    private JavaText() {
    }

    public static String prefix() {
        return "JAVA";
    }

    public static String javaOnly(String input) {
        if (input == null) {
            throw new IllegalArgumentException(
                    "input must not be null");
        }
        return prefix() + ":" + input.trim();
    }

    public static String maybeName(boolean available) {
        return available ? "Ada" : null;
    }
}
~~~

Class này hoàn toàn là Java 17-compatible (không dùng Kotlin APIs), nên **javac** có thể biên dịch nó độc lập.

Vai trò:

- **prefix()** trả phần đầu chuỗi, được Kotlin gọi.
- **javaOnly()** là ví dụ Java function có thể gọi từ cả Java và Kotlin.
- **maybeName()** cố tình có thể trả null để minh họa **Java platform types**. Trong API thật, nên dùng nullability annotations/Optional hoặc type contract rõ ràng nếu phù hợp.

## 9. KotlinMessage.kt: Kotlin gọi Java class

Tạo **src/main/kotlin/demo/mixed/KotlinMessage.kt**:

~~~kotlin
@file:JvmName("KotlinMessageApi")

package demo.mixed

fun greeting(name: String): String {
    val trimmed = name.trim()
    return JavaText.prefix() + "+KOTLIN:" + trimmed
}

@JvmOverloads
fun salutation(
    name: String,
    prefix: String = "Hi"
): String {
    return prefix + ", " + name.trim() + "!"
}

fun safeDisplayName(available: Boolean): String {
    val fromJava: String? = JavaText.maybeName(available)
    return fromJava?.trim() ?: "anonymous"
}

class KotlinFormatter(private val label: String) {
    fun format(name: String): String {
        return label + ":" + name.trim()
    }
}

object KotlinStatus {
    @JvmStatic
    fun version(): String = "KOTLIN_2_4"
}
~~~

Trong tệp này, Kotlin thực sự gọi Java:

~~~kotlin
JavaText.prefix()
JavaText.maybeName(available)
~~~

Các declarations được JVM compiler chuyển thành classes/static members để Java code có thể gọi ngược lại.

### 9.1. @file:JvmName

Kotlin top-level functions thường được biên dịch thành static methods trong class có tên dựa trên tên tệp. Nếu file tên **KotlinMessage.kt** và không có annotation, Java thường gọi qua **KotlinMessageKt.greeting(...)**.

Đặt:

~~~kotlin
@file:JvmName("KotlinMessageApi")
~~~

ở đầu tệp khiến Java gọi **KotlinMessageApi.greeting(...)**. Đây là một cách tạo API Java dễ đọc và tránh tên facade phụ thuộc filename.

### 9.2. @JvmOverloads

Kotlin cho phép default parameter:

~~~kotlin
fun salutation(name: String, prefix: String = "Hi"): String
~~~

Kotlin caller có thể bỏ prefix. **Java không tự hiểu Kotlin default arguments**. Annotation **@JvmOverloads** yêu cầu sinh overloads tương ứng để Java gọi cả:

~~~java
KotlinMessageApi.salutation("Ada");
KotlinMessageApi.salutation("Ada", "Hello");
~~~

Không dùng annotation tràn lan cho mọi method nếu một API có nhiều optional parameters: overload explosion có thể tăng complexity của binary/public API.

### 9.3. @JvmStatic

Kotlin **object KotlinStatus** là singleton. Java thường có thể truy cập instance qua **KotlinStatus.INSTANCE**, nhưng với **@JvmStatic**, nó còn có thể gọi:

~~~java
KotlinStatus.version();
~~~

Dùng khi một function cần Java static-friendly API. Không nhầm **@JvmStatic** với “đối tượng này trở thành class Java thuần”.

### 9.4. KotlinFormatter là Kotlin class bình thường

Kotlin class:

~~~kotlin
class KotlinFormatter(private val label: String) {
    fun format(name: String): String =
        label + ":" + name.trim()
}
~~~

có constructor và method dễ gọi từ Java:

~~~java
new KotlinFormatter("PAIR").format(" Gradle ");
~~~

Dùng Kotlin class thay vì chỉ top-level functions giúp team Java dễ áp dụng Kotlin từng phần mà không phải refactor toàn bộ APIs.

### 9.5. Nullability khi gọi Java

Java function **maybeName(boolean)** có thể trả null, nhưng nếu không có annotation đầy đủ, Kotlin coi return type là **platform type** (thường biểu diễn như **String!** trong IDE). Kotlin có thể cho phép dùng như String hoặc String?, nhưng non-null assumption sai có thể ném exception lúc runtime.

Trong lab:

~~~kotlin
val fromJava: String? = JavaText.maybeName(available)
return fromJava?.trim() ?: "anonymous"
~~~

Việc chọn **String?** làm ranh giới nullability rõ ràng. Khi available=false, kết quả **anonymous**, không phải NPE.

## 10. Main.java: Java gọi Kotlin

Tạo **src/main/java/demo/mixed/Main.java**:

~~~java
package demo.mixed;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(
                KotlinMessageApi.greeting(" Java "));

        System.out.println(
                new KotlinFormatter("PAIR").format(" Gradle "));

        System.out.println(
                KotlinMessageApi.salutation("Ada"));

        System.out.println(
                KotlinStatus.version());
    }
}
~~~

Main.java phụ thuộc trực tiếp vào Kotlin declarations được biên dịch bởi Kotlin compiler. Gradle Kotlin JVM plugin điều phối **compileKotlin** và **compileJava** theo đúng task graph.

**Stdout chính xác của Java Main:**

~~~text
JAVA+KOTLIN:Java
PAIR:Gradle
Hi, Ada!
KOTLIN_2_4
~~~

Hãy chú ý hai hướng phụ thuộc:

- **Kotlin gọi Java:** KotlinMessage.greeting() gọi **JavaText.prefix()**.
- **Java gọi Kotlin:** Main.main() gọi **KotlinMessageApi.greeting()**, **KotlinFormatter.format()** và **KotlinStatus.version()**.

Như vậy, cùng một JVM project có interop **hai chiều**.

### 10.1. Vì sao không cho Java Main gọi greeting() trực tiếp?

Trong JVM bytecode, top-level Kotlin function không phải global Java function. Nó là static method của một JVM class facade. Vì dùng **@file:JvmName("KotlinMessageApi")**, Java caller cần class đó. Nếu file annotation thay đổi, Java API surface có thể đổi, gây **cannot find symbol** hoặc binary incompatibility cho consumers.

### 10.2. Chạy từ Gradle, không cần tự dựng classpath

~~~bash
./gradlew run --console=plain
~~~

Gradle **application** plugin thiết lập runtimeClasspath gồm Kotlin classes, Java classes và Kotlin stdlib. Với project hỗn hợp, đây là cách dễ và ít lỗi hơn tự ghép hàng loạt JAR vào **java -cp**.

## 11. StandaloneCheck.java: kiểm tra Java thuần

Tạo **src/main/java/demo/mixed/StandaloneCheck.java**:

~~~java
package demo.mixed;

public final class StandaloneCheck {
    private StandaloneCheck() {
    }

    public static void main(String[] args) {
        System.out.println(
                JavaText.javaOnly(" Gradle "));
    }
}
~~~

Class này chỉ gọi JavaText nên có thể chạy độc lập qua **javac/java 17**, không cần Kotlin compiler.

Linux/macOS từ root:

~~~bash
mkdir -p out

javac --release 17 -encoding UTF-8 \
  -d out \
  src/main/java/demo/mixed/JavaText.java \
  src/main/java/demo/mixed/StandaloneCheck.java

java -cp out demo.mixed.StandaloneCheck
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -encoding UTF-8 -d out src\main\java\demo\mixed\JavaText.java src\main\java\demo\mixed\StandaloneCheck.java

java -cp out demo.mixed.StandaloneCheck
~~~

**Stdout chính xác:**

~~~text
JAVA:Gradle
~~~

**Không dùng lệnh javac độc lập này để compile Main.java**: Main có references tới KotlinMessageApi, KotlinFormatter và KotlinStatus; raw javac chưa biết các compiled Kotlin outputs. Muốn compile toàn bộ project, dùng **./gradlew classes** hoặc compiler toolchain/classpath được cấu hình tương đương.

## 12. JavaInteropTest.java

Tạo **src/test/java/demo/mixed/JavaInteropTest.java**:

~~~java
package demo.mixed;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JavaInteropTest {

    @Test
    void javaCanCallKotlinTopLevelFunction() {
        assertEquals(
                "JAVA+KOTLIN:Ada",
                KotlinMessageApi.greeting(" Ada "));
    }

    @Test
    void javaCanCallKotlinClassAndSingleton() {
        KotlinFormatter formatter =
                new KotlinFormatter("PAIR");

        assertEquals(
                "PAIR:Gradle",
                formatter.format(" Gradle "));

        assertEquals(
                "KOTLIN_2_4",
                KotlinStatus.version());
    }

    @Test
    void jvmOverloadsMakeDefaultArgCallable() {
        assertEquals(
                "Hi, Ada!",
                KotlinMessageApi.salutation("Ada"));

        assertEquals(
                "Hello, Ada!",
                KotlinMessageApi.salutation("Ada", "Hello"));
    }
}
~~~

Java test compile task thấy Kotlin main compiled classes nhờ Kotlin Gradle plugin. Không cần thêm test source files vào main classpath bằng file() thủ công.

Tests dùng **JUnit 5** và **assertEquals** để xác minh JVM interop, không chỉ in output.

## 13. KotlinInteropTest.kt

Tạo **src/test/kotlin/demo/mixed/KotlinInteropTest.kt**:

~~~kotlin
package demo.mixed

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class KotlinInteropTest {

    @Test
    fun kotlinCanCallJavaMethods() {
        assertEquals("JAVA", JavaText.prefix())
        assertEquals(
            "JAVA:Gradle",
            JavaText.javaOnly(" Gradle ")
        )
    }

    @Test
    fun kotlinCanUseTopLevelFunctions() {
        assertEquals(
            "JAVA+KOTLIN:Ada",
            greeting(" Ada ")
        )

        assertEquals(
            "Hi, Ada!",
            salutation("Ada")
        )
    }

    @Test
    fun kotlinHandlesNullableJavaReturn() {
        assertEquals(
            "anonymous",
            safeDisplayName(false)
        )
        assertEquals(
            "Ada",
            safeDisplayName(true)
        )
    }
}
~~~

Có tổng cộng **sáu JUnit test methods** trong hai test classes: ba Java, ba Kotlin.

**Expected:** Cả sáu pass nếu sources/build scripts không bị thay đổi. Khi chạy lần sau, Gradle có thể báo **UP-TO-DATE**, tức tasks không cần chạy lại; đó là hành vi bình thường, không phải tests mới thực thi lần hai.

### 13.1. Tại sao không thêm kotlin("test")?

Trong lab, Kotlin tests import trực tiếp **org.junit.jupiter.api.Test** và **Assertions**, nên dependencies JUnit Jupiter/Platform đã đủ. Với project thích sử dụng **kotlin.test.assertEquals** hoặc các Kotest frameworks, cần thêm dependency/runner tương ứng và bảo đảm test engine được cấu hình.

Không thêm **kotlin-test** không cần thiết chỉ để Kotlin source test compile khi toàn bộ assertions đang dùng Jupiter.

## 14. Chạy và kiểm tra project hoàn chỉnh

Lệnh Linux/macOS:

~~~bash
./gradlew --version
./gradlew clean test --console=plain
./gradlew -q run
./gradlew jar --console=plain
./gradlew installDist --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test --console=plain
.\gradlew.bat -q run
.\gradlew.bat jar --console=plain
.\gradlew.bat installDist --console=plain
~~~

**Stdout của Main từ lệnh run**:

~~~text
JAVA+KOTLIN:Java
PAIR:Gradle
Hi, Ada!
KOTLIN_2_4
~~~

Lệnh **test** cần phát hiện sáu JUnit test methods và exit code 0. Gradle có thể in thêm thời gian, deprecation warnings, Daemon messages hoặc task status: không đưa ra “stdout toàn build” cố định.

### 14.1. Các tasks chính

~~~bash
./gradlew tasks --all --console=plain
~~~

Trong build Kotlin/JVM có thể thấy:

~~~text
compileKotlin
compileJava
compileTestKotlin
compileTestJava
classes
testClasses
test
jar
run
startScripts
installDist
distZip
distTar
~~~

Không coi danh sách trên là output nguyên văn; plugin versions, Gradle conventions và tasks thêm vào có thể khác. **tasks --all** giúp xác minh tên task thật.

### 14.2. Kiểm tra outputs

Thông thường:

~~~text
build/classes/kotlin/main/
build/classes/java/main/
build/classes/kotlin/test/
build/classes/java/test/
build/libs/mixed-jvm-lab.jar
build/reports/tests/test/
build/test-results/test/
build/install/mixed-jvm-lab/
~~~

Không hardcode đường dẫn output vào source code; những paths này là layout mặc định minh họa có thể thay theo Gradle/plugin version và artifact naming conventions.

### 14.3. jar chưa phải fat/uber JAR

Task **jar** đóng gói classes/resources của project, **không tự bundle toàn bộ external Kotlin stdlib/JUnit dependencies** thành một executable fat JAR. Với Java/Kotlin app, chạy:

~~~bash
./gradlew installDist
~~~

rồi sử dụng distribution scripts và libs directory do **application plugin** tạo. Nếu dự án cần self-contained/fat JAR, dùng packaging plugin đã được duyệt và kiểm tra license, resource merging, signature/duplicate handling. Không giả rằng **java -jar build/libs/...jar** tự chạy được khi chưa cấu hình Main-Class và external classpath.

### 14.4. Kiểm tra distributions

Linux/macOS (tùy generated launcher):

~~~bash
./build/install/mixed-jvm-lab/bin/mixed-jvm-lab
~~~

Windows:

~~~powershell
.\build\install\mixed-jvm-lab\bin\mixed-jvm-lab.bat
~~~

Kỳ vọng cùng bốn dòng stdout của Main. Distribution chứa các runtime library JARs do Gradle quản lý.

## 15. Kotlin stdlib, Kotlin compiler và Kotlin Gradle plugin khác nhau

Một project có thể liên quan ba thành phần với nhiệm vụ khác nhau:

1. **org.jetbrains.kotlin.jvm plugin**: tích hợp Gradle task model, Kotlin compiler, source sets, incremental compilation và toolchains.
2. **Kotlin compiler**: biến .kt thành JVM bytecode.
3. **kotlin-stdlib**: cung cấp API/runtime classes Kotlin cho ứng dụng.

Với Kotlin/JVM plugin hiện hành, Kotlin stdlib thông thường được thêm tự động. Kotlin version của stdlib/reflect/compiler cần phù hợp để tránh metadata/binary incompatibility.

### 15.1. Kiểm tra dependency graph

~~~bash
./gradlew dependencies \
  --configuration runtimeClasspath \
  --console=plain

./gradlew dependencies \
  --configuration testRuntimeClasspath \
  --console=plain
~~~

Quan sát Kotlin stdlib version được resolve. Nếu phải sửa mismatch:

~~~bash
./gradlew dependencyInsight \
  --dependency kotlin-stdlib \
  --configuration runtimeClasspath \
  --console=plain
~~~

**Không mặc định chép một dependency Kotlin stdlib version khác** vào implementation để “đè” lên compiler. Cần xem plugin version, platform/BOM/constraints và dependencyInsight trước.

### 15.2. Kotlin stdlib không phải JUnit engine

Kotlin stdlib giúp Kotlin code chạy; nó không tự cung cấp JUnit Jupiter test engine. Plugin Kotlin JVM cũng không tự kích hoạt **useJUnitPlatform()** trong mọi cấu hình. Lab khai báo JUnit test dependencies và **useJUnitPlatform()** rõ ràng.

### 15.3. KGP version và Kotlin DSL embedded version không đồng nhất

Gradle tự nhúng Kotlin runtime/DSL support để biên dịch **build.gradle.kts** và một số plugins. Phiên bản Kotlin nhúng trong Gradle có thể khác **org.jetbrains.kotlin.jvm** version dùng cho **application Kotlin source**. Không suy “Gradle có Kotlin embedded” nghĩa là có thể bỏ Kotlin JVM plugin trong app.

## 16. JVM target compatibility là lỗi cần nhận diện sớm

Kotlin Gradle plugin kiểm tra **related compile tasks** như:

- **compileKotlin** và **compileJava** trong main source set.
- **compileTestKotlin** và **compileTestJava** trong test source set.

Nếu Kotlin **jvmTarget** không khớp Java **targetCompatibility** hoặc Java compile configuration, Gradle/Kotlin plugin có thể báo lỗi **Inconsistent JVM-target compatibility detected for tasks ...**.

### 16.1. Ví dụ sai

~~~groovy
kotlin {
    compilerOptions {
        jvmTarget.set(
            org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
        )
    }
}

java {
    targetCompatibility = JavaVersion.VERSION_11
}
~~~

Đây là **snippet lỗi minh họa**, không dùng trong lab hoàn chỉnh. Kotlin sinh bytecode Java 17 nhưng JavaCompile target Java 11 có thể tạo metadata/variant và runtime requirements sai lệch.

### 16.2. Cách đúng

Dùng toolchain nhất quán:

~~~groovy
kotlin {
    jvmToolchain(17)
    compilerOptions {
        jvmTarget.set(
            org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
        )
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release.set(17)
}
~~~

Tổ hợp này điều khiển Kotlin JVM target và Java release target về 17. Nếu cần build cho Java 11 consumers, hãy cấu hình cả hai target thích hợp và chỉ sử dụng APIs phù hợp với Java 11.

### 16.3. Không “sửa” bằng IGNORE

Có thể gặp Gradle property:

~~~properties
kotlin.jvm.target.validation.mode=ignore
~~~

Đây là **anti-pattern khi chỉ muốn giấu lỗi**. Kiểm tra target mismatch là công cụ bảo vệ compatibility. Chỉ thay validation mode khi có lý do đặc biệt và hiểu hậu quả; cách khắc phục thông thường là đồng bộ toolchains/targets.

### 16.4. Vấn đề Gradle JVM vs compiler target

Nếu Gradle chạy trên JDK 21 nhưng Kotlin/Java target 17, điều đó **không mặc định là lỗi** nếu Gradle/KGP support và toolchain cấu hình đúng. Cái cần kiểm tra là các compile tasks liên quan có targets tương thích, và compiler/test JVM thực tế được chọn đúng.

## 17. Java ↔ Kotlin interoperability ngoài lab

Hai ngôn ngữ chia sẻ bytecode nhưng không có cùng source-level semantics.

### 17.1. Java gọi Kotlin properties

Kotlin:

~~~kotlin
class Customer(val id: String, var displayName: String)
~~~

Java:

~~~java
Customer customer = new Customer("1", "Ada");
String id = customer.getId();
customer.setDisplayName("Grace");
String current = customer.getDisplayName();
~~~

Trong Kotlin, **val** thường sinh getter, **var** sinh getter/setter. Java không gọi **customer.displayName** như public Java field trừ khi field được expose bằng cơ chế phù hợp.

Kotlin property bắt đầu bằng **is** có quy tắc getter/setter naming riêng; khi xây Java-facing API hãy kiểm tra bytecode/JVM signatures.

### 17.2. @JvmField

Kotlin:

~~~kotlin
class Configuration {
    @JvmField
    val answer: Int = 42
}
~~~

Java có thể đọc:

~~~java
int n = new Configuration().answer;
~~~

**@JvmField** expose field thay vì chỉ getter, với các hạn chế Kotlin docs (property có backing field, không private, không delegated, không open/override/const). Đừng dùng rộng rãi nếu public Java field sẽ làm API khó thay đổi.

### 17.3. Kotlin companion và object

Kotlin:

~~~kotlin
class TokenFactory {
    companion object {
        @JvmStatic
        fun create(): String = "SAFE"
    }
}
~~~

Java:

~~~java
String result = TokenFactory.create();
~~~

Không có **@JvmStatic**, Java thường gọi qua **TokenFactory.Companion.create()**. Với Kotlin object, Java có **INSTANCE** singleton, còn @JvmStatic tạo static-call convenience.

### 17.4. Top-level function tên JVM class

Nếu file **Format.kt** có:

~~~kotlin
package demo.api

fun normalize(value: String): String = value.trim()
~~~

Java thường gọi:

~~~java
String s = demo.api.FormatKt.normalize("  A  ");
~~~

Nếu đặt **@file:JvmName("TextApi")**, Java sẽ gọi **demo.api.TextApi.normalize(...)**. Thay tên file khi chưa có @JvmName có thể thay binary API của một library tiêu thụ từ Java.

### 17.5. Default parameters

Kotlin function có default values không tự sinh mọi Java overload. Dùng **@JvmOverloads** ở API cần hỗ trợ Java callers. Việc chuyển một Java overload set thành một Kotlin function có defaults có thể phá Java source/binary compatibility nếu bỏ các overloads Java đang sử dụng.

### 17.6. Checked exceptions và @Throws

Kotlin không bắt buộc khai báo checked exceptions ở source như Java. Khi Java caller cần checked exception trong method signature, Kotlin có **@Throws(...)**:

~~~kotlin
@Throws(java.io.IOException::class)
fun loadText(): String {
    throw java.io.IOException("TEST_IO")
}
~~~

Đây là **snippet minh họa**, không gọi trong Main của lab. Java callers cần catch/throws theo API signature được tạo. Không dùng raw exception message chứa secrets ở production.

### 17.7. Platform types và nullability

Java declarations không có nullability annotations có thể xuất hiện như Kotlin platform types **String!**. Compiler cho phép xử lý chúng như nullable/non-nullable, nhưng đó không phải bảo đảm runtime không null.

Nên:
- Đưa giá trị qua boundary với **String?** khi có thể null.
- Dùng null-aware calls **?.** và Elvis **?:**.
- Thêm các nullability annotations chuẩn cho Java APIs khi team đã chọn một bộ annotation.
- Viết tests cho null/empty/blank handling.
- Không dùng **!!** chỉ để làm compiler yên lặng.

Ngược lại, khi Java gọi Kotlin function nhận **String** non-null, passing null có thể làm Kotlin generated runtime check ném exception. Một Kotlin nullable **String?** không tự biến Java signature thành kiểu Optional.

### 17.8. Generics, variance và wildcards

Kotlin **List<out T>**, mutable collections và Java **List<? extends T>** có semantics khác nhau. Kotlin compiler có thể sinh JVM wildcards để giữ variance, đôi khi làm Java caller API dài hoặc khó gọi.

**@JvmSuppressWildcards** / **@JvmWildcard** hữu ích ở một số boundaries, nhưng chỉ thêm khi đã thấy exact Java signature issue qua javap hoặc IDE. Không tùy tiện “xóa wildcards” vì có thể ảnh hưởng type safety và binary API.

### 17.9. Kotlin data classes

Kotlin:

~~~kotlin
data class User(val id: String, val active: Boolean)
~~~

Java có thể gọi constructor/getters, **component1()**, **component2()**, **copy(...)** trong những điều kiện signature phù hợp. Không đồng nhất data class với Java record: equality, copy semantics, nullability, serialization frameworks và bytecode APIs có thể khác.

### 17.10. Java records và Kotlin

Kotlin/JVM có thể làm việc với Java records khi toolchain/target phù hợp. Java record accessors **name()**, **age()** không nhất thiết được dùng trong Kotlin như property syntax giống JavaBeans. Hãy kiểm tra Kotlin compiler/IDE behavior, và giữ Java record là immutable API rõ ràng nếu cả hai ngôn ngữ dùng.

### 17.11. suspend functions từ Java

Kotlin **suspend fun** có JVM representation liên quan **Continuation**. Java không gọi trực tiếp suspend function như một blocking method bình thường. Để expose coroutine APIs cho Java, tạo một **Java-friendly boundary** như CompletionStage/CompletableFuture hoặc một adapter phù hợp, dùng kotlinx-coroutines version được quản lý.

Đừng nói “Kotlin coroutine tự động là Java Future”. Hai APIs có lifecycle, cancellation và exception propagation khác nhau.

### 17.12. Kotlin value classes

**@JvmInline value class** có thể có bytecode representation unboxed/mangled, khó gọi trực tiếp từ Java. Kotlin documentation hiện hành có cơ chế expose boxed representations theo version/opt-in. Đối với API Java phổ biến, ưu tiên một public class/DTO đơn giản hoặc wrapper được kiểm thử ABI thay vì xuất value class chưa hiểu JVM signature.

## 18. Source sets và thư mục tùy chỉnh

Mặc định nên dùng **src/main/kotlin** và **src/main/java**. Nếu tổ chức có legacy folders, cấu hình các source sets tương ứng.

Ví dụ **chỉ dùng khi thư mục thật sự tồn tại**:

~~~groovy
sourceSets {
    main {
        java.srcDirs = ['src/main/java', 'src/legacy/java']
        kotlin.srcDirs = ['src/main/kotlin', 'src/legacy/kotlin']
    }
}
~~~

Đây là snippet mở rộng, không thuộc lab hoàn chỉnh. Cấu hình sourceSets quá rộng có thể làm Gradle compile nhầm generated output hoặc test sources; tránh thêm thư mục **build/** làm source root bằng cách hardcode path khi task generation chưa được wiring qua providers.

### 18.1. Generated Kotlin/Java sources

Nếu task code generation tạo **.kt** hoặc **.java**:

- Khai báo input và output directory.
- Tạo files dưới **build/generated/**.
- Nối output provider vào source set/compiler task đúng cách.
- Không commit generated files trừ khi dự án có chính sách rõ ràng.
- Không cho hai tasks ghi cùng output folder.
- Không dùng **tasks.compileKotlin.dependsOn(... )** thủ công nếu producer output có thể nối qua provider để Gradle hiểu dependency tự động.

### 18.2. Test source sets

Gradle Java plugin cung cấp main/test mặc định. **compileTestKotlin** xử lý Kotlin tests, **compileTestJava** xử lý Java tests. Nếu tạo integrationTest source set hoặc JVM test suite mới, cần kiểm tra Kotlin plugin có tự tạo compilation tương ứng hay cần cấu hình rõ.

Không mong **src/integrationTest/kotlin** tự chạy chỉ vì tên folder tồn tại; phải định nghĩa test suite/source set và classpath/test task chính xác.

### 18.3. Multi-project khác mixed-language single project

Bài này tập trung **một project chứa cả Java và Kotlin**. Nhưng trong multi-project build cũng có thể phân chia:
- :java-core Java thuần
- :kotlin-service Kotlin
- :app Java/Kotlin mixed

Khi chia modules, Gradle project dependencies/variants điều phối classpath. Đừng tạo vòng phụ thuộc **:java-core -> :kotlin-service -> :java-core**. Với mixed sources cùng module, compiler plugin xử lý interop mà không cần tạo project dependency cycle.

## 19. Task graph: main và test compilations

Ở mức khái niệm:

~~~text
compileKotlin   + Java source declarations
      |
      v
compileJava  (thấy Kotlin compiled classes)
      |
      v
classes
      |
      +------------------------+
      |                        |
      v                        v
compileTestKotlin         compileTestJava
      |                        |
      +------------+-----------+
                   |
                   v
               testClasses
                   |
                   v
                  test
~~~

Đây là **sơ đồ học tập**: task dependencies/classpaths do plugin quản lý và có thể thay đổi theo version. Kotlin test compilation và Java test compilation còn dùng main outputs, nên không phải hai branches hoàn toàn độc lập trong mọi build. Để xem task graph thực tế dùng Gradle **--dry-run**.

~~~bash
./gradlew test --dry-run --console=plain
~~~

**--dry-run** liệt kê tasks được chọn mà không thực thi actions; không dùng kết quả này để chứng minh code đã compile hoặc tests đã pass.

### 19.1. Trạng thái task có nghĩa gì?

| Outcome | Ý nghĩa |
| --- | --- |
| **UP-TO-DATE** | Inputs/outputs hiện tại hợp lệ, task không cần action |
| **FROM-CACHE** | Outputs khôi phục từ Gradle build cache |
| **NO-SOURCE** | Không có source files phù hợp |
| **SKIPPED** | Task bị skip bởi điều kiện |
| Task không có suffix | Task có thể đang chạy action |
| **FAILED** | Task action/validation/compilation/test không thành công |

Nếu project không có Kotlin tests, **compileTestKotlin** có thể NO-SOURCE. Nếu compileTestJava NO-SOURCE, không có nghĩa compileTestKotlin đã thất bại. Nếu test task UP-TO-DATE, không có test mới thực thi trong invocation đó.

### 19.2. Không chỉnh task dependencies bằng suy đoán

Kotlin Gradle plugin đã cấu hình các dependencies cần thiết cho main/test. Việc ép **compileJava.dependsOn(compileKotlin)** không phải luôn cần vì plugin đã quản lý; có thể làm build logic giòn. Điều nguy hiểm hơn là ép **compileKotlin.dependsOn(compileJava)** rồi sinh cycle khi Java references tới Kotlin.

## 20. Đọc compiler diagnostics và Gradle logs

Để điều tra source/kotlin compiler:

~~~bash
./gradlew compileKotlin \
  --console=plain --info

./gradlew compileJava \
  --console=plain --info

./gradlew test \
  --console=plain --stacktrace
~~~

**--info** làm log dài hơn; kiểm tra IDE/CI privacy policy trước khi chia sẻ. Với bug report, ghi task path, Gradle/KGP version, Java toolchain, exact error, source tối thiểu, không upload toàn **~/.gradle/** hoặc environment dump.

### 20.1. Kotlin errors

Thông báo Kotlin compiler thường chỉ vào file **.kt** và line/column, ví dụ lỗi **Unresolved reference**. Nguyên nhân thường:
- Sai package/import.
- Không áp dụng Kotlin JVM plugin.
- Source file không thuộc configured Kotlin source directory.
- Dependency scope sai.
- Java method/property signature không như Kotlin caller tưởng.
- Compiler/Kotlin metadata version mismatch.

### 20.2. Java errors

**cannot find symbol** khi Java Main gọi Kotlin có thể do:
- **@file:JvmName** khác tên Java caller.
- Kotlin file không được compile vào source set main.
- Kotlin code compile fail trước.
- Java đang compile bằng raw javac không có Kotlin outputs.
- Kotlin declaration là internal/private hoặc signature bị mangled.
- Java/Kotlin code thuộc modules với dependency relationship sai.
- Stale IDE cache/source model.

### 20.3. JVM runtime errors

**NoClassDefFoundError: kotlin/jvm/internal/Intrinsics** gợi ý thiếu Kotlin stdlib ở runtime classpath khi chạy trực tiếp bằng java. Sử dụng Gradle **run/installDist** hoặc classpath đúng, không copy một vài .class để tạo executable giả.

**UnsupportedClassVersionError** cho biết class được biên dịch bằng bytecode cao hơn JVM đang chạy hỗ trợ. Kiểm tra **java -version**, Java toolchain, Kotlin jvmTarget, Java options.release và runtime executor.

**NoSuchMethodError/AbstractMethodError** có thể là dấu hiệu binary incompatibility sau khi thay Kotlin compiler/plugin, Java-facing function overload hoặc Kotlin library runtime version. Kiểm tra resolved dependencies và bytecode ABI thay vì vội xóa Gradle caches.

## 21. Dependency scopes: Java/Kotlin trong một Gradle configuration model

Các dependencies thường gặp:

| Configuration | Mục đích | Ví dụ |
| --- | --- | --- |
| **implementation** | Dependency cần compile/runtime của app nhưng không công bố như API của java-library | Kotlin library, logging implementation |
| **api** | Public API dependency trong java-library project | DTO types trong public signatures |
| **compileOnly** | Có ở compile, không tự nằm trên runtime classpath | Annotation APIs được runtime cung cấp khác |
| **runtimeOnly** | Runtime cần nhưng compilation không cần | JDBC driver |
| **testImplementation** | Dependencies cho Java/Kotlin tests | JUnit Jupiter |
| **testRuntimeOnly** | Test runtime engine/launcher | JUnit Platform Launcher |
| **annotationProcessor** | Java annotation processors | MapStruct processor cho javac |
| **kapt** | Annotation processing bridge cho Kotlin trong project bật kapt | Processor Java annotation API được kapt hỗ trợ |
| **ksp** | Kotlin Symbol Processing plugin configuration (khi dùng KSP) | KSP processor compatible |

Kotlin và Java source trong **cùng main source set** sử dụng chung Gradle configurations như **implementation**, **runtimeOnly** và classpaths với vai trò tương ứng. Không cần tạo **kotlinImplementation** cho trường hợp JVM project chuẩn.

### 21.1. implementation vs api

Nếu một mixed-language library publish Kotlin class có public signature:

~~~kotlin
fun parse(input: ExternalParser): Result
~~~

thì **ExternalParser** type thuộc API; consumer cần compile dependency thích hợp. Trong **java-library** project, việc phân biệt **api** và **implementation** giúp tránh downstream compilation thay đổi vô ích.

Không nên đẩy mọi dependency lên api chỉ vì Kotlin type system đòi import một số types; thiết kế API và dependency declaration nhất quán.

### 21.2. Kotlin BOM/stdlib alignment

Kotlin Gradle plugin hiện hành có quy tắc quản lý Kotlin stdlib version. Khi dependency graph có nhiều Kotlin libraries (stdlib, reflect, coroutines, serialization), dùng resolved dependency reports để kiểm tra versions. Nếu dự án cần khóa versions, cân nhắc Gradle version catalogs/platforms/constraints theo policy.

Không ép tất cả artifacts mang tiền tố **org.jetbrains.kotlinx** theo đúng version của Kotlin compiler: kotlinx-coroutines/kotlinx-serialization runtime có version line riêng.

### 21.3. Dependency resolution không phải compiler error

Nếu Gradle fail ở **Could not resolve org.jetbrains.kotlin...**, cần kiểm tra Maven/network/proxy/plugin repositories trước. Nếu resolve thành công nhưng Kotlin source báo **Unresolved reference**, có thể là dependency chưa ở đúng compile configuration hoặc API không tồn tại ở version resolved.

## 22. Kotlin annotation processing: KSP, kapt và Java APT

Một Java/Kotlin project có thể dùng MapStruct, Dagger, Room, Hibernate/JPA, validation hoặc serialization plugins.

### 22.1. Java annotationProcessor

Java source annotation processors chạy qua javac khi được khai báo:

~~~groovy
dependencies {
    annotationProcessor 'group.example:example-processor:1.0'
}
~~~

Đây là **snippet mô tả**, group:artifact chỉ là placeholder học thuật, không phải dependency runnable. Với một processor thật, dùng coordinate/version chính thức, pin version và kiểm tra incremental annotation processing support.

### 22.2. kapt

**kapt** (Kotlin annotation processing tool) cho phép dùng nhiều Java annotation processors với Kotlin declarations qua generated stubs. Nó có overhead, giới hạn compatibility và cần cấu hình plugin:

~~~groovy
plugins {
    id 'org.jetbrains.kotlin.jvm' version '2.4.21'
    id 'org.jetbrains.kotlin.kapt' version '2.4.21'
}
~~~

Đây là **snippet plugin mở rộng**, không thuộc build.gradle lab đầy đủ. Nếu dùng processor, cần thêm **kapt '...'** với dependency thật. Không cố đưa mọi processor vào **annotationProcessor** rồi kỳ vọng Kotlin source được xử lý đầy đủ.

### 22.3. KSP

**Kotlin Symbol Processing (KSP)** thường là lựa chọn phù hợp nếu framework đã cung cấp KSP processor compatible. KSP có API riêng và phiên bản plugin phải được chọn theo KSP/Kotlin compatibility. Không tự lấy một version KSP trùng số với Kotlin plugin rồi cho rằng đúng.

**KSP không tự thay tất cả annotation processors**; một số processors chỉ hỗ trợ Java APT hoặc kapt. Khi migrate, kiểm tra generated source layout, task graph và output compatibility.

### 22.4. Tác động tới task graph

Generated sources cần được tạo trước đúng compilation task và được nối bằng provider/task dependency phù hợp. Lỗi **Unresolved reference generatedType** thường xuất phát từ:
- Processor không chạy.
- Processor configuration sai (kapt/ksp/annotationProcessor).
- Generated source root không được IDE/Gradle đăng ký.
- Processor incompatible với Kotlin compiler/plugin version.
- Generated file của module khác không có dependency.
- Build cache chứa output không hợp lệ hoặc plugin thiếu @Input/@Output declarations.

Không ép compile order thủ công trước khi xem task graph thực sự.

## 23. Incremental compilation và build cache

Kotlin Gradle plugin hỗ trợ incremental compilation mặc định cho Kotlin/JVM trong những điều kiện bình thường. Nó theo dõi source/classpath changes và dùng classpath snapshots để tránh recompile quá rộng.

Một sequence:

~~~bash
./gradlew clean classes --console=plain
./gradlew classes --console=plain
~~~

Sau lần đầu, khi không đổi source, compileKotlin/compileJava có thể **UP-TO-DATE**. Đó không phải chứng cứ lần hai compiler chạy rất nhanh; lần hai compiler actions có thể không chạy.

### 23.1. Đổi Kotlin implementation

Nếu đổi body của **greeting()** nhưng giữ Kotlin ABI/JVM method signature, Gradle/Kotlin compiler có thể chỉ recompile những source affected và không buộc mọi Java downstream compilation làm lại trong điều kiện phù hợp.

Tuy nhiên Kotlin có **inline functions**, constants, default argument implementation và metadata có thể ảnh hưởng semantic dependencies. Không đơn giản kết luận “body change không bao giờ ảnh hưởng Java”.

### 23.2. Đổi Java ABI

Nếu JavaText.prefix() đổi return type hoặc Java class public method signatures, Kotlin code gọi nó có thể cần recompile. Gradle/KGP dùng classpath snapshots để xác định phần affected. Nếu chỉ đổi private implementation Java, Kotlin tasks có thể tránh làm lại tùy ngữ cảnh.

### 23.3. Tắt incremental để điều tra, không phải cải thiện mặc định

Một Kotlin JVM project có thể dùng Gradle property:

~~~properties
kotlin.incremental=false
~~~

hoặc command:

~~~bash
./gradlew compileKotlin \
  -Pkotlin.incremental=false \
  --console=plain
~~~

Đây là thử nghiệm để phân biệt incremental compiler issue, **không phải đề xuất lâu dài**. Tắt incremental làm build lớn chậm hơn; kết quả đầu tiên sau đổi policy có thể không so được với warm incremental build.

### 23.4. Build cache

Kotlin compile tasks có thể dùng Gradle task output build cache. Khi task **FROM-CACHE**, Gradle restore compiled outputs thay vì compile. Đây khác **dependency cache** chứa JARs đã tải và **configuration cache** chứa configuration model.

~~~bash
./gradlew classes --build-cache --console=plain
./gradlew clean classes --build-cache --console=plain
~~~

Lần sau clean có thể FROM-CACHE **nếu cache entry phù hợp vẫn còn**, không phải bảo đảm. Bật build cache không tự làm mọi custom processor/task cacheable.

### 23.5. Kotlin daemon

Kotlin compiler có thể dùng một daemon process riêng để tối ưu compile sessions; nó không phải Gradle Daemon. Khi gặp build chậm hoặc memory issue, đọc Kotlin plugin build report/daemon diagnostics, kiểm tra JVM args và process count. Không xóa daemons hoặc tăng heap mà không đo.

### 23.6. Kotlin build reports

Kotlin plugin có hỗ trợ build reports về compilation phases, thời gian và incremental compilation causes. Khi chẩn đoán performance, dùng tài liệu plugin version hiện tại để bật report đúng cách; không dựa vào một flag đã bị deprecated. Build Scan có thể xem task durations, nhưng Kotlin-specific report có thể chi tiết hơn về compiler work.

## 24. IDE: IntelliJ, Android Studio, Eclipse, VS Code

### 24.1. IntelliJ IDEA

IDE thường nhận diện **src/main/kotlin** và **src/main/java** sau khi Gradle project được import/sync. Khi code báo **Unresolved reference** chỉ trong editor:

- Kiểm tra Kotlin/JVM plugin ở đúng project.
- Dùng Gradle Wrapper distribution.
- Chọn Gradle JVM thích hợp.
- Sync Gradle project.
- Đối chiếu **./gradlew classes**: CLI fail là lỗi build thật, CLI pass nhưng editor fail thì điều tra IDE indexing/IDE Kotlin plugin/model.
- Kiểm tra Kotlin source root/module model và Gradle delegated builds.

Không xóa toàn **~/.gradle** khi vấn đề chỉ là IDE indexing.

### 24.2. Android Studio

Android có Kotlin Android plugin, Android Gradle Plugin và compileOptions riêng, nên build.gradle của lab JVM **không tự áp dụng nguyên xi vào Android**. Bài này giải thích plain JVM project; Android có source sets/variants/tasks và plugin compatibility khác.

### 24.3. Eclipse Buildship/VS Code

Hỗ trợ Kotlin editor/compiler có thể phụ thuộc plugin/extension. Gradle CLI vẫn là nguồn thực thi thống nhất. Hãy đối chiếu **./gradlew test** với IDE-runner tasks và ghi rõ cái nào đang chạy JUnit Platform.

### 24.4. Kotlin IDE plugin khác Kotlin Gradle plugin

IDE có thể bundle Kotlin tooling/compiler analysis version riêng. Runtime build nên đi qua Gradle Wrapper và Kotlin Gradle plugin khai báo trong project. Nếu thấy cảnh báo IDE plugin không tương thích, ghi versions rồi đối chiếu release notes; không tự đổi app dependencies để giải quyết lỗi IDE indexing.

## 25. CI cho Java/Kotlin cùng project

Một GitHub Actions workflow tối giản:

Tạo **.github/workflows/mixed-jvm.yml**:

~~~yaml
name: Mixed Java and Kotlin JVM

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Install JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v6

      - name: Compile and test
        run: |
          ./gradlew --no-daemon clean test \
            --console=plain

      - name: Verify Java main with Kotlin classes
        shell: bash
        run: |
          output="$(./gradlew -q run)"
          expected="$(printf '%s\n' \
            'JAVA+KOTLIN:Java' \
            'PAIR:Gradle' \
            'Hi, Ada!' \
            'KOTLIN_2_4')"
          test "$output" = "$expected"

      - name: Upload JUnit XML
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: java-kotlin-test-results
          path: build/test-results/test/TEST-*.xml
          if-no-files-found: warn
          retention-days: 14
~~~

Đây là **ví dụ CI**, không phải log đã chạy. Một runner cold cần resolve Kotlin plugin/stdlib/JUnit qua internet hoặc internal Maven mirror; CI cần được cấp quyền đúng để truy cập repository được phép.

### 25.1. Không che test failures

- Không dùng **|| true** cho ./gradlew test.
- Nếu Java hoặc Kotlin test fail, process exit nonzero, job phải đỏ.
- **if: always()** cho upload JUnit XML chỉ giữ diagnostics, không làm build pass.
- Không upload Gradle User Home, credentials hoặc toàn workspace.
- Không cấp signing/publish tokens cho untrusted PR jobs.
- Pin JDK và Gradle Wrapper version trong repository.

### 25.2. Reproducibility trên CI

- Không dùng dynamic versions như Kotlin plugin **2.+**.
- Giữ Wrapper files đầy đủ.
- Dùng dependency locking/verification nếu team yêu cầu.
- Cẩn thận OS line endings/encoding/timezone.
- Có ít nhất một Java caller test và một Kotlin caller test, không chỉ test ứng dụng Java thuần.
- Đừng đánh giá compile success chỉ bằng việc task FROM-CACHE; có thể thêm clean/forced compilation trong quality jobs phù hợp.
- Nếu dùng remote build cache, chỉ trusted jobs được push và bảo vệ cache khỏi poisoning.

## 26. Chuyển dần Java sang Kotlin mà không làm vỡ build

### Bước 1 — Thêm Kotlin JVM plugin

Giữ Java source như cũ, thêm plugin và toolchain. Chạy:

~~~bash
./gradlew clean classes test --console=plain
~~~

Không đổi logic business trong cùng commit nếu muốn cô lập plugin integration.

### Bước 2 — Thêm một Kotlin class nhỏ

Viết một class hoặc utility bằng Kotlin, đặt tại **src/main/kotlin**, để Java gọi nó. Chạy Java test và Kotlin test. Nếu team chưa sẵn sàng, bắt đầu bằng Kotlin test/helper không nằm trên public library ABI.

### Bước 3 — Viết Kotlin gọi Java API có sẵn

Tạo Kotlin facade sử dụng JavaText hoặc service Java hiện tại. Với Java nullability không annotated, thêm explicit String? khi cần. Đừng chuyển toàn bộ DTOs sang Kotlin data classes một lần.

### Bước 4 — Giữ Java-facing API ổn định

Nếu nhiều module/clients Java gọi functions cũ, dùng **@JvmName**, **@JvmStatic**, **@JvmOverloads** hoặc facade Java duy trì binary names/signatures. Kiểm tra bằng **javap** và tests tiêu thụ APIs từ Java.

### Bước 5 — Chuyển tests và services từng phần

Mỗi module đổi Java→Kotlin theo từng tính năng. Chỉ bỏ dependencies hoặc plugins Java annotation processing sau khi xác nhận không còn processors/Java sources cần chúng.

### Bước 6 — Theo dõi performance

Thêm compiler Kotlin có thể tăng configuration, JVM memory và compile times ở cold build. Đo incremental developer loops, test outcomes và CI times. Đừng chọn “viết Kotlin ngắn hơn” làm chứng cứ build luôn nhanh hơn.

### Bước 7 — Nâng versions riêng biệt, có kiểm chứng

Không nâng Gradle Wrapper, Kotlin plugin, JDK target, Kotlin coroutines, JUnit và IDE plugin trong cùng commit nếu không có lý do. Kiểm tra Kotlin/Gradle compatibility matrix và CI kết quả sau từng thay đổi.

## 27. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Plugin org.jetbrains.kotlin.jvm not found | Plugin marker repo/network/version | Kiểm tra plugins {} và pluginManagement |
| Unresolved reference trong Kotlin | Sai import/package, source root hoặc dependency | Xem compileKotlin, sourceSets, dependencies |
| cannot find symbol KotlinMessageApi | JVM facade name sai hoặc compileKotlin fail | Kiểm tra @file:JvmName, task graph |
| Java Main không compile bằng javac đơn | Chưa có Kotlin class files/classpath | Dùng ./gradlew classes hoặc build classpath đúng |
| Inconsistent JVM-target compatibility | Kotlin jvmTarget khác Java target | jvmToolchain, compilerOptions, options.release |
| Kotlin source .kt không được compile | Đặt sai directory/sourceSet | src/main/kotlin hoặc sourceSets.kotlin |
| Java source trong src/main/kotlin bị bỏ qua | Không phải Java source root | Chuyển vào src/main/java |
| compileTestKotlin NO-SOURCE | Không có Kotlin tests | Kiểm tra test directories, không tự coi lỗi |
| JUnit tests không được chạy | Thiếu useJUnitPlatform/JUnit deps/test sourceSet | Xem reports, test task config |
| NoClassDefFoundError Intrinsics | Thiếu Kotlin stdlib runtime | Gradle run/installDist, runtimeClasspath |
| Kotlin metadata version mismatch | Incompatible Kotlin library/Compiler version | dependencyInsight, align Kotlin versions |
| UnsupportedClassVersionError | Chạy trên JVM thấp hơn compiled bytecode | Đồng bộ runtime/JDK/targets |
| NoSuchMethodError sau refactor | Java-facing JVM signature thay đổi | ABI tests, @JvmName/@JvmOverloads |
| NullPointerException từ platform type | Java method trả null bất ngờ | Explicit String?, Java nullability contracts |
| Kotlin default parameter Java call fail | Thiếu Java overload | @JvmOverloads hoặc explicit overload |
| Kotlin object static method không thấy | Thiếu @JvmStatic hoặc dùng sai INSTANCE | Kiểm tra Java-facing API |
| Kotlin property field không thấy | property có getter/setter, không field | getX()/setX(), @JvmField khi phù hợp |
| KSP generated class missing | Processor/plugin variant/version/source roots | Kiểm tra KSP task + compatible versions |
| kapt processor không chạy | Chưa apply kapt hoặc wrong dependency config | kapt plugin và processor coordinate |
| Java annotationProcessor không xử lý Kotlin | APT javac khác Kotlin processing | KSP/kapt tùy processor |
| Gradle clean xong vẫn FROM-CACHE | Build cache entry tồn tại | --no-build-cache khi điều tra |
| compileKotlin UP-TO-DATE | Inputs/outputs hợp lệ | Đổi source hoặc --rerun-tasks có chủ đích |
| IDE đỏ nhưng CLI xanh | IDE indexing/SDK/Gradle model khác | Sync IDE, kiểm tra Gradle JVM |
| Kotlin stdlib duplicate/conflict | Transitive Kotlin libraries lệch versions | dependencyInsight/runtimeClasspath |
| Gradle 9 upgrade lỗi plugin cũ | KGP/Gradle APIs không tương thích | Chọn Kotlin plugin version được hỗ trợ |
| Build chậm hơn sau Kotlin adoption | Kotlin daemon, cold builds, annotation processors | Build reports, đo performance A/B |
| Runtime jar thiếu dependency | Plain jar không phải fat jar | application distribution, dependencies |
| Kotlin coroutines khó gọi từ Java | Suspend function có Continuation signature | Tạo CompletionStage adapter |
| Java compile version sai trên CI | Toolchain không có JDK hoặc Java settings override | ./gradlew --version, --info, toolchain resolver |

### 27.1. Khi gặp incompatible JVM target

Chạy:

~~~bash
./gradlew clean classes \
  --console=plain --info
~~~

Xem **compileKotlin/compileJava** target values và toolchain. Không sửa bằng cách tắt validation nếu chưa điều chỉnh bytecode target thực.

### 27.2. Khi gặp Kotlin unresolved reference

Xác nhận source file ở **src/main/kotlin** hoặc configured Kotlin sourceSets, package/import đúng, Java dependency có trong main compileClasspath. Không dùng **src/test/java** class làm dependency của main Kotlin class.

### 27.3. Khi Java Main không thấy Kotlin class

Kiểm tra:

~~~bash
./gradlew classes --console=plain
./gradlew -q run
~~~

Nếu Gradle chạy được nhưng raw javac không, đây là dấu hiệu manual classpath chưa đầy đủ, không phải Kotlin plugin hỏng.

### 27.4. Khi thiếu class ở runtime

~~~bash
./gradlew dependencies \
  --configuration runtimeClasspath \
  --console=plain
~~~

Kotlin stdlib/other libraries có trong Gradle runtimeClasspath chưa? Nếu có, dùng **run** hoặc **installDist**; tránh copy class files ra **out/** rồi chạy với classpath thiếu Kotlin stdlib.

## 28. Bài tập thực hành

### Bài 1 — Groovy DSL và Kotlin DSL

Viết lại plugins block cho build.gradle.kts. Phân biệt việc Gradle script là Kotlin DSL với Kotlin compiler xử lý project .kt.

### Bài 2 — Java gọi Kotlin top-level function

Chạy Java Main trong lab, xác minh **KotlinMessageApi.greeting(" Java ")** in **JAVA+KOTLIN:Java**. Xóa @file:JvmName trong branch thử nghiệm và sửa Java caller theo tên facade được sinh; giải thích sự thay đổi ABI.

### Bài 3 — Kotlin gọi Java

Trong KotlinInteropTest kiểm tra JavaText.javaOnly(). Đổi JavaText.prefix() trong branch thử nghiệm rồi ghi những tasks cần chạy lại; không thay package hoặc public signatures trong cùng phép thử.

### Bài 4 — Kotlin property từ Java

Tạo Kotlin class **Customer(val id: String, var displayName: String)**. Viết Java test gọi getId(), getDisplayName() và setDisplayName(). Vì sao customer.id không phải public Java field?

### Bài 5 — Default parameters

Bỏ @JvmOverloads khỏi salutation() rồi compile JavaInteropTest. Ghi exact compiler error, sau đó thêm annotation trở lại. Kotlin test gọi salutation("Ada") có thay đổi không?

### Bài 6 — Singleton interop

Bỏ @JvmStatic khỏi KotlinStatus.version(), thử Java caller KotlinStatus.version() rồi sửa thành KotlinStatus.INSTANCE.version(). Giải thích đường gọi khác nhau.

### Bài 7 — Nullability

Đổi safeDisplayName thành code dùng **JavaText.maybeName(false).trim()** mà không kiểm tra null (chỉ trong branch thử nghiệm). Điều gì xảy ra? Sửa bằng String? và Elvis operator.

### Bài 8 — JVM target

Đặt Kotlin jvmTarget 17 và Java target 11, quan sát validation error. Khôi phục target 17, không đặt validation mode IGNORE.

### Bài 9 — Source directories

Di chuyển KotlinMessage.kt sang src/main/java rồi xem plugin source recognition theo cấu hình hiện tại. Giải thích vì sao convention src/main/kotlin dễ quản lý hơn. Không dùng layout khác cho production khi chưa thử IDE sync/Gradle tasks.

### Bài 10 — Java thuần

Biên dịch JavaText và StandaloneCheck bằng **javac --release 17**. Tại sao cùng cách đó không compile Main.java khi nó đang gọi Kotlin declarations?

### Bài 11 — Kotlin stdlib runtime

Chạy **./gradlew dependencies --configuration runtimeClasspath**. Tìm Kotlin stdlib. Vì sao Java Main trong mixed project có thể gặp NoClassDefFoundError nếu dùng raw java -cp chỉ chứa classes?

### Bài 12 — Tests ở hai ngôn ngữ

Chạy **./gradlew clean test** và kiểm tra hai test classes cùng sáu methods. Không dựa chỉ vào dòng BUILD SUCCESSFUL nếu Test task NO-SOURCE.

### Bài 13 — Incremental build

Chạy classes hai lần, quan sát UP-TO-DATE ở lần hai. Đổi Kotlin greeting implementation, quan sát tasks và giải thích vì sao không thể suy “tất cả Java files phải compile lại”.

### Bài 14 — KSP/kapt

Lấy một annotation processor thật mà framework đang dùng; kiểm tra nó hỗ trợ KSP hay cần kapt. Thiết kế task graph code generation và không thêm processor artifacts bừa vào implementation.

### Bài 15 — ABI compatibility

Dùng **javap** kiểm tra KotlinMessageApi, KotlinFormatter và KotlinStatus sau compilation. Ghi names/signatures Java consumer thấy. Điều gì xảy ra nếu đổi tên @file:JvmName hoặc bỏ một overload đã publish?

### Bài 16 — CI

Đưa lab vào một CI job JDK 17 và chạy test/run. Ghi Kotlin plugin version và Wrapper version; kiểm tra task failures không bị che bởi || true.

### Bài 17 — Phân tách modules

Giả sử team có Java core và Kotlin service: thiết kế :java-core -> :kotlin-service -> :app dependencies không tạo vòng. Khi nào giữ mixed sources trong một module đơn giản hơn?

### Bài 18 — Coroutine boundary

Giải thích vì sao Java không gọi **suspend fun** như một synchronous method bình thường. Thiết kế adapter CompletionStage cho Java API, không cần tự viết runtime coroutine scheduler.

## 29. Câu hỏi tự kiểm tra

1. Kotlin JVM plugin dùng làm gì?
2. Gradle Kotlin DSL có phải Kotlin JVM plugin không?
3. Vì sao build.gradle Groovy vẫn compile .kt?
4. Kotlin Multiplatform có cần cho project Java+Kotlin chỉ chạy JVM không?
5. Những thư mục source files mặc định là gì?
6. Vì sao không đặt Java files trong src/main/kotlin?
7. Task nào compile .kt ở main source set?
8. Task nào compile .java?
9. Kotlin compiler có thể hiểu Java source declarations cùng source set không?
10. Vì sao Java compiler cần Kotlin compiled classes khi Java gọi Kotlin?
11. Có nên tự đặt compileKotlin.dependsOn(compileJava) không?
12. jvmToolchain(17) ảnh hưởng gì?
13. Kotlin compilerOptions.jvmTarget dùng type gì?
14. JavaCompile.options.release khác Kotlin jvmTarget thế nào?
15. Vì sao related compile tasks cần compatible JVM targets?
16. Có nên tắt validation bằng IGNORE để build xanh không?
17. @file:JvmName giải quyết vấn đề gì?
18. Top-level Kotlin function mặc định có facade class tên thế nào?
19. @JvmStatic giúp Java gọi singleton/companion thế nào?
20. @JvmOverloads dùng cho trường hợp nào?
21. Kotlin val/var trông như gì trong Java?
22. @JvmField có giúp expose field không?
23. Kotlin gọi Java method trả nullable nhưng không annotated có rủi ro gì?
24. Platform type có luôn non-null không?
25. Kotlin String? tương đương Java Optional<String> không?
26. @Throws có tác dụng gì với Java caller?
27. Vì sao Java không gọi suspend fun như Java static method thông thường?
28. Kotlin data class có giống hệt Java record không?
29. Kotlin stdlib khác Kotlin Gradle plugin thế nào?
30. Kotlin Gradle plugin có thêm stdlib theo convention không?
31. Kotlin compiler version có phải luôn bằng Kotlin embedded trong Gradle DSL không?
32. Test classes Java/Kotlin cần JUnit runtime nào?
33. Java Main stdout trong lab gồm mấy dòng?
34. Java-only StandaloneCheck stdout là gì?
35. Có thể compile toàn bộ mixed project chỉ với javac không?
36. jar mặc định có bao gồm toàn bộ Kotlin stdlib không?
37. run/installDist khác java -jar plain JAR thế nào?
38. KSP và kapt khác Java annotationProcessor thế nào?
39. compileKotlin UP-TO-DATE có compiler action chạy không?
40. FROM-CACHE có nghĩa outputs được lấy từ đâu?
41. Configuration cache khác build cache như thế nào?
42. Vì sao không dùng --rerun-tasks để đo incremental compile avoidance?
43. Khi Java Main gặp NoClassDefFoundError Intrinsics, kiểm tra gì?
44. Khi nâng Kotlin plugin cần kiểm tra gì ngoài source syntax?
45. Trong CI, vì sao cần tests từ cả Java và Kotlin?

**Đáp án gợi ý:** (1) compiler/task integration; (2) không; (3) plugin tách biệt DSL; (4) không; (5) main/test/java/kotlin; (6) Java source root khác; (7) compileKotlin; (8) compileJava; (9) có; (10) JVM classpath; (11) không, có thể cycle; (12) align toolchain; (13) JvmTarget enum; (14) Java API/release vs Kotlin bytecode; (15) tránh mismatch; (16) không; (17) ổn định JVM facade name; (18) FileNameKt; (19) tạo static method; (20) Java overloads cho default args; (21) getters/setters; (22) có điều kiện; (23) NPE; (24) không; (25) không; (26) Java throws declaration; (27) Continuation/coroutine protocol; (28) không; (29) runtime API vs build compiler plugin; (30) có trong KGP hiện hành; (31) không; (32) Jupiter/Platform; (33) bốn; (34) JAVA:Gradle; (35) không; (36) không; (37) runtime classpath/distribution; (38) Kotlin processors vs javac processors; (39) không; (40) build cache; (41) config model vs task outputs; (42) ép tasks chạy, che avoidance; (43) runtimeClasspath/kotlin-stdlib; (44) Gradle/JDK/IDE/dependency compatibility; (45) bảo đảm hai compiler/interop directions.

## 30. Checklist trước khi đưa mixed Java/Kotlin project lên production

- [ ] Gradle Wrapper version được pin và kiểm tra compatibility.
- [ ] Kotlin JVM plugin version được pin rõ, không dùng dynamic versions.
- [ ] JDK runtime Gradle và Java toolchain đáp ứng compatibility matrix.
- [ ] Kotlin jvmTarget và Java target/release được cấu hình tương thích.
- [ ] Không dùng kotlin.jvm.target.validation.mode=ignore để giấu lỗi.
- [ ] Kotlin sources đúng source set, ưu tiên src/main/kotlin.
- [ ] Java sources đúng source set, ưu tiên src/main/java.
- [ ] Không cho Kotlin main classes phụ thuộc test-only dependencies.
- [ ] Không tự thêm task dependsOn gây cycle compileJava/compileKotlin.
- [ ] Đã có Java→Kotlin interop tests.
- [ ] Đã có Kotlin→Java interop tests.
- [ ] Test runtime dùng JUnit Platform/engine và source tests được phát hiện.
- [ ] Kotlin stdlib trên runtimeClasspath phù hợp Kotlin compiler.
- [ ] Không ép Kotlin stdlib version khác nếu chưa kiểm tra dependency graph.
- [ ] Default args có @JvmOverloads khi Java API thực sự cần.
- [ ] Top-level facade class name ổn định cho Java clients.
- [ ] Singleton API có @JvmStatic nếu thiết kế Java static calls.
- [ ] Kotlin properties/getters/sam/callback API đã được kiểm tra từ Java.
- [ ] Java platform types được xử lý nullability rõ ràng.
- [ ] Exceptions từ Kotlin không làm lộ dữ liệu nhạy cảm.
- [ ] Suspend/coroutine APIs có Java adapter khi cần.
- [ ] API dùng data/value classes được kiểm tra JVM signature.
- [ ] Annotation processors được đặt đúng annotationProcessor/kapt/KSP.
- [ ] Generated sources có task ownership và dependency wiring.
- [ ] Incremental compilation/build cache được hiểu đúng và debug được.
- [ ] Kotlin daemon memory/process behavior được theo dõi khi build lớn.
- [ ] Application distribution chứa runtime dependencies.
- [ ] Không suy plain jar tự là fat/executable jar.
- [ ] IDE Gradle JVM và CLI Wrapper build được đối chiếu.
- [ ] CI kiểm tra Gradle test, run, Java/Kotlin source compilation.
- [ ] CI không cung cấp release credentials cho untrusted PRs.
- [ ] Build logs, scans và artifacts không chứa secrets.
- [ ] Có kế hoạch nâng Gradle/Kotlin/JDK độc lập và rollback.
- [ ] Có tests bảo vệ Java-facing binary API khi library có consumer.

## 31. Tài liệu chính thức

- [Kotlin — Configure a Gradle project](https://kotlinlang.org/docs/gradle-configure-project.html)
- [Kotlin — Compiler options in the Kotlin Gradle plugin](https://kotlinlang.org/docs/gradle-compiler-options.html)
- [Kotlin — Calling Kotlin from Java](https://kotlinlang.org/docs/java-to-kotlin-interop.html)
- [Kotlin — Calling Java from Kotlin](https://kotlinlang.org/docs/java-interop.html)
- [Kotlin — Compilation and caches in the Kotlin Gradle plugin](https://kotlinlang.org/docs/gradle-compilation-and-caches.html)
- [Kotlin — Releases and upgrade notes](https://kotlinlang.org/docs/releases.html)
- [Kotlin — Java/JVM Overview](https://kotlinlang.org/docs/jvm-get-started.html)
- [Kotlin — KSP Overview](https://kotlinlang.org/docs/ksp-overview.html)
- [Kotlin — kapt](https://kotlinlang.org/docs/kapt.html)
- [Gradle — Building Java & JVM projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — Application plugin](https://docs.gradle.org/current/userguide/application_plugin.html)
- [Gradle — Java Library plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — JVM toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Java testing](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — Dependency configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html)
- [Gradle — Dependency insight and reports](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle — Build cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle — Configuration cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle — Upgrade to Gradle 9](https://docs.gradle.org/current/userguide/upgrading_major_version_9.html)
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)

**Kết luận:** Tích hợp Kotlin JVM với Java không đòi chia dự án thành hai ứng dụng. **org.jetbrains.kotlin.jvm** gắn Kotlin compiler vào Gradle Java ecosystem; **application/java** plugin cung cấp JVM tasks/runtime/distribution, còn **jvmToolchain** và **compilerOptions.jvmTarget** giữ các compiler targets thống nhất. Chia source folders theo convention, để Gradle điều phối compile tasks, viết tests từ cả hai phía và thiết kế Java-facing API bằng @file:JvmName, @JvmStatic, @JvmOverloads và nullability rõ ràng. Kết quả là một project có thể áp dụng Kotlin từng phần, vẫn sử dụng Java code hiện tại và giữ build có thể tái lập trên IDE/CI mà không phải tái cấu trúc toàn bộ repository.
