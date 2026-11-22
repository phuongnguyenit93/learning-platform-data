# Cấu hình compiler args, encoding và tham số trình biên dịch trong Gradle

## 1. Tổng quan và mục tiêu học tập

Trong dự án Java, việc sử dụng cùng bộ mã nguồn không bảo đảm mọi máy sẽ sinh ra cùng bytecode: lập trình viên có thể dùng một JDK khác CI; file `.java` chứa tiếng Việt có thể bị đọc nhầm charset; Java reflection có thể chỉ thấy tên tham số `arg0` thay cho tên gốc; và `javac` có thể in cảnh báo ở một môi trường nhưng không ở môi trường khác.

Gradle xử lý các vấn đề này thông qua task **`JavaCompile`** và cấu hình **`CompileOptions`**. Khi áp dụng plugin `java`, `java-library` hoặc `application`, Gradle tạo những task như `compileJava` và `compileTestJava`. Chúng quản lý source files, compile classpath, output directory, Java compiler/toolchain, encoding, target release và các tham số bổ sung được gửi tới `javac`.

Sau bài học, bạn sẽ có thể:

1. Phân biệt `JavaCompile`, `compileJava`, `compileTestJava`, compiler toolchain và `javac` command line.
2. Khai báo `options.encoding = "UTF-8"` và hiểu ranh giới với console encoding, resource filtering và JVM charset.
3. Sử dụng `options.compilerArgs` với `-parameters`, `-Xlint`, `-Werror` và các flags hữu ích.
4. Dùng `options.release.set(17)` và Java toolchain để kiểm soát ngôn ngữ, JDK APIs và class-file version.
5. Biên dịch và chạy ví dụ Java 17 có tiếng Việt và reflection, với stdout có thể kiểm chứng.
6. Chọn phạm vi cấu hình: mọi `JavaCompile` task hay chỉ main/test source set.
7. Phân biệt compiler flags với `org.gradle.jvmargs`, `Test.jvmArgs` và `JavaExec.jvmArgs`.
8. Biết khi nào dùng `options.compilerArgumentProviders` để truyền đối số động có khai báo task inputs.
9. Cấu hình annotation processor path, generated sources và hiểu `-A`, `-processor`, `-proc:none`.
10. Xử lý warnings-as-errors, preview language features, fork options, incremental compilation, build cache và các lỗi thường gặp.

Bài thuộc nhóm **Dự án Java** của **Build Tool Gradle**, tập trung Kotlin DSL (`build.gradle.kts`) với ví dụ tương đương Groovy DSL (`build.gradle`). Nội dung ưu tiên Java 17; những options có thể khác ở các phiên bản JDK/Gradle khác cần được đối chiếu với Gradle Wrapper của dự án.

## 2. Gradle JavaCompile làm gì?

Khi dùng plugin Java, Gradle tạo mô hình source sets:

~~~text
src/main/java/               Mã production
       |
       v
:compileJava                 JavaCompile task
       |
       +-- source            Các .java files
       +-- classpath         Dependencies để compile
       +-- javaCompiler      JDK compiler được lựa chọn
       +-- options.encoding  Charset đọc mã nguồn
       +-- options.release   Java API/language/bytecode target
       +-- options.compilerArgs  Javac arguments bổ sung
       |
       v
build/classes/java/main/     Các file .class

src/test/java/               Mã test
       |
       v
:compileTestJava             JavaCompile task
       |
       v
build/classes/java/test/     Test classes
~~~

`compileJava` và `compileTestJava` là task **cùng một kiểu `JavaCompile`**, nhưng dùng những source directories/classpaths khác nhau. Nếu có custom source set `integrationTest`, Gradle có thể tạo thêm task JavaCompile khác. Bởi vậy, cấu hình theo **type** đôi khi phù hợp hơn cấu hình theo một **tên task**.

Phần lớn công việc gọi `javac` là do Gradle thực hiện qua Java Compiler API hoặc compiler process theo thiết lập. Người viết build script thường không phải tự tạo shell command `javac -cp ... -d ...` vì Gradle đã quản lý source, classpath, task inputs và outputs.

### 2.1. Bảng ánh xạ Gradle ↔ javac

| Nhu cầu | Gradle | Javac tương ứng |
| --- | --- | --- |
| File source | Source set / `JavaCompile.source` | Danh sách file `.java` |
| Compile classpath | Dependencies, `JavaCompile.classpath` | `-classpath <paths>` |
| Nơi ghi `.class` | Task output directory | `-d <directory>` |
| Source charset | `options.encoding = "UTF-8"` | `-encoding UTF-8` |
| Java release | `options.release.set(17)` | `--release 17` |
| Java compiler version | `java.toolchain` / `javaCompiler` | Chọn JDK `javac` |
| Tên tham số method | `options.compilerArgs.add("-parameters")` | `-parameters` |
| Deprecation warning | `options.compilerArgs.add("-Xlint:deprecation")` | `-Xlint:deprecation` |
| Warnings thành lỗi | `options.compilerArgs.add("-Werror")` | `-Werror` |
| Annotation processors | Configuration `annotationProcessor` | Processor path và discovery |

**Ưu tiên API chuyên biệt cho encoding, release, classpath và output.** `compilerArgs` là nơi khai báo flags không được Gradle DSL cung cấp trực tiếp. Không lặp `-encoding`, `-d`, `-source`, `-target`, `--release` hoặc `-classpath` qua `compilerArgs` khi đã cấu hình các phần đó bằng typed properties.

### 2.2. JavaCompile không tự điều khiển Kotlin/Groovy/Scala

`tasks.withType<JavaCompile>()` chỉ áp dụng cho **các task biên dịch Java**. Nếu dự án dùng Kotlin plugin, các file `.kt` được xử lý bởi Kotlin compiler tasks với cấu hình riêng. Cũng không nên nghĩ rằng tùy chọn của JavaCompile tự đổi encoding cho `ProcessResources`, `Javadoc`, JavaExec, unit test runtime hoặc output console.

## 3. Những thuộc tính CompileOptions quan trọng

Trong Gradle Kotlin DSL, các thuộc tính chính có thể dùng như sau:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    java
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
    options.compilerArgs.addAll(
        listOf("-parameters", "-Xlint:deprecation")
    )
}
~~~

Đoạn này là một mẫu build.gradle.kts đơn giản, áp dụng cả main và test JavaCompile tasks.

| Tùy chọn | Tác dụng | Ghi nhớ |
| --- | --- | --- |
| `encoding` | Charset đọc source `.java` | Đặt UTF-8 rõ ràng |
| `compilerArgs` | Danh sách flags của javac | Một argument là một phần tử |
| `compilerArgumentProviders` | Tạo flags dựa trên inputs khai báo | Tốt cho custom plugins/flags động |
| `release` | Java language/API/class-file target | Thường ưu tiên `--release` |
| `annotationProcessorPath` | Nguồn tìm annotation processors | Do `annotationProcessor` configuration cung cấp |
| `generatedSourceOutputDirectory` | Thư mục source do processors sinh | Không tự chồng output của task khác |
| `fork` / `forkOptions` | Cấu hình compiler process và memory | Không phải runtime app |
| `debug` / `debugOptions` | Debug metadata trong `.class` | Khác `-parameters` |
| `warnings` / `deprecation` | Điều khiển warning reporting | Không thay toàn bộ `-Xlint` |
| `incremental` | Incremental Java compilation | Thường bật mặc định ở Gradle hiện đại |
| `failOnError` | Fail task khi compiler báo lỗi | Mặc định true |

Khi muốn thay flags một cách có kiểm soát, `options.compilerArgs.add(...)`/`addAll(...)` rõ hơn việc vô tình thay nguyên danh sách do plugin khác cấu hình.

## 4. Ví dụ hoàn chỉnh Java 17: encoding UTF-8 và -parameters

Bài thực hành này không phụ thuộc thư viện ngoài JDK; nó giúp kiểm tra **chuỗi tiếng Việt** và **tên tham số method** được ghi trong bytecode.

### 4.1. Cấu trúc dự án

~~~text
compiler-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── src/
│   └── main/
│       └── java/
│           └── demo/
│               ├── Greeter.java
│               └── Main.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Các file nguồn `.java` phải được lưu **thực tế dưới UTF-8**, không chỉ hiển thị như UTF-8 trong IDE. Nếu chưa có Gradle Wrapper, cần khởi tạo Wrapper theo quy trình của dự án trước khi dùng `./gradlew`.

**settings.gradle.kts**

~~~kotlin
rootProject.name = "compiler-demo"
~~~

### 4.2. build.gradle.kts hoàn chỉnh

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.Main")
}

tasks.withType<JavaCompile>().configureEach {
    // Charset đọc source .java.
    options.encoding = "UTF-8"

    // Chỉ dùng ngôn ngữ, API và bytecode Java 17.
    options.release.set(17)

    // Các flags còn lại của javac.
    options.compilerArgs.addAll(
        listOf(
            "-parameters",
            "-Xlint:deprecation",
            "-Xlint:unchecked"
        )
    )
}
~~~

Giải thích:

- `application` tạo workflow chạy Java app và áp dụng Java plugin.
- Toolchain chọn compiler JDK 17 cho Java tasks có tích hợp toolchain. Môi trường cần cài JDK 17 hoặc được cấu hình toolchain provisioning phù hợp.
- `options.release.set(17)` giới hạn Java language level, JDK APIs và target bytecode, tương ứng `javac --release 17`.
- `options.encoding` nêu rõ charset của `.java` để tránh phụ thuộc vào locale/JDK default.
- `-parameters` lưu formal parameter names trong bytecode, dùng được qua Java reflection.
- `-Xlint:deprecation` và `-Xlint:unchecked` làm javac hiển thị chi tiết một số warning khi thật sự có code gây warning.
- Không cần `repositories` và dependency bên ngoài vì mã chỉ dùng Java Standard Library.

### 4.3. src/main/java/demo/Greeter.java

~~~java
package demo;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

### 4.4. src/main/java/demo/Main.java

~~~java
package demo;

import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args)
            throws NoSuchMethodException {
        System.out.println(Greeter.greet("Lan"));

        Method method = Greeter.class.getDeclaredMethod(
            "greet", String.class
        );
        Parameter parameter = method.getParameters()[0];

        System.out.println(
            "parameterName=" + parameter.getName()
        );
        System.out.println(
            "namePresent=" + parameter.isNamePresent()
        );
    }
}
~~~

`Method.getParameters()` trả các tham số của phương thức. Khi `javac` biên dịch với `-parameters`, tên gốc `name` được lưu trong attribute `MethodParameters`, và `isNamePresent()` cho biết reflection có tên thật hay không.

### 4.5. Chạy chương trình

macOS/Linux:

~~~bash
./gradlew --quiet clean run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --quiet clean run
~~~

**Ba dòng stdout của ứng dụng**:

~~~text
Xin chào, Lan!
parameterName=name
namePresent=true
~~~

`--quiet` giảm log Gradle, nhưng đôi khi JVM/toolchain có thể ghi thông tin ngoài stdout của chương trình. Một terminal không hỗ trợ Unicode có thể **hiển thị** tiếng Việt sai; điều đó khác với việc file Java bị compile sai encoding.

Sau khi chạy, Gradle tạo các file đại diện:

~~~text
build/classes/java/main/demo/Greeter.class
build/classes/java/main/demo/Main.class
~~~

### 4.6. Kiểm tra bytecode

Với JDK tool:

~~~bash
javap -v build/classes/java/main/demo/Greeter.class
~~~

Tìm `MethodParameters` và tên `name` trong báo cáo, thay vì so khớp toàn bộ constant-pool output. Nếu `--release 17` có hiệu lực, Java class-file **major version là 61**.

### 4.7. Bỏ -parameters và so sánh

Tạm xóa `"-parameters"` khỏi danh sách rồi biên dịch lại từ sạch:

~~~bash
./gradlew --quiet clean run
~~~

Với javac chuẩn, kết quả phản ánh việc thiếu metadata tên tham số:

~~~text
Xin chào, Lan!
parameterName=arg0
namePresent=false
~~~

`arg0` là tên tổng hợp do Java reflection cung cấp khi bytecode không lưu tên gốc, không có nghĩa mã nguồn tự đổi `name` thành `arg0`. Sau thử nghiệm, thêm lại flag và `clean` để project trở về cấu hình ban đầu.

## 5. Cùng ví dụ đó với javac thuần

Để hiểu Gradle thực sự truyền gì tới compiler, ta có thể biên dịch hai Java files trên bằng JDK 17 trực tiếp.

### 5.1. Linux/macOS

~~~bash
mkdir -p out

javac \
  -encoding UTF-8 \
  --release 17 \
  -parameters \
  -Xlint:deprecation \
  -Xlint:unchecked \
  -d out \
  src/main/java/demo/Greeter.java \
  src/main/java/demo/Main.java

java -cp out demo.Main
~~~

### 5.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac -encoding UTF-8 --release 17 -parameters `
  -Xlint:deprecation -Xlint:unchecked -d out `
  .\src\main\java\demo\Greeter.java `
  .\src\main\java\demo\Main.java

java -cp out demo.Main
~~~

Output Java:

~~~text
Xin chào, Lan!
parameterName=name
namePresent=true
~~~

Điều kiện: `javac` trên `PATH` thực sự là JDK 17 hoặc một JDK mới hơn hỗ trợ `--release 17`. Kiểm tra `javac -version` khi cần. **Javac của terminal có thể khác compiler Gradle chọn bằng toolchain**.

Ánh xạ trực tiếp:

~~~text
Gradle: options.encoding = "UTF-8"
Javac:  -encoding UTF-8

Gradle: options.release.set(17)
Javac:  --release 17

Gradle: options.compilerArgs.add("-parameters")
Javac:  -parameters

Gradle: options.compilerArgs.add("-Xlint:deprecation")
Javac:  -Xlint:deprecation

Gradle: output directory của JavaCompile task
Javac:  -d out
~~~

Gradle có thêm task graph, input/output tracking, compile classpath resolution, build cache và incremental compilation, thay vì chỉ là một shell wrapper quanh javac.

## 6. Encoding là gì và vì sao nên đặt UTF-8?

Một file source chỉ chứa bytes trên disk. Khi mở file `.java`, IDE giải mã bytes thành ký tự; khi compiler chạy, javac cũng cần giải mã bytes theo một charset.

Nếu file chứa bytes UTF-8 nhưng compiler đọc theo charset khác, có thể:

- Báo `unmappable character for encoding ...`.
- Tạo literal String sai nếu bytes tình cờ tạo ký tự hợp lệ trong charset đó.
- Compile thành công nhưng in sai tiếng Việt ở runtime.
- Chỉ lỗi trên máy khác OS, locale hoặc JDK.

Trong Gradle:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

Thực hiện đúng nếu source files **đã được lưu UTF-8**.

### 6.1. Phân biệt nhiều tầng encoding

| Tầng dữ liệu | Điều khiển | Ý nghĩa |
| --- | --- | --- |
| Source `.java` | `JavaCompile.options.encoding` | Compiler đọc source bytes |
| Resource `.txt`, `.properties`, JSON | Resource filtering/Java API đọc file | Không tự đổi theo source encoding |
| Console stdout | Terminal/code page, JVM output stream | Hiển thị chuỗi ký tự khi chạy |
| Gradle Daemon | JVM settings và locale | Không thay thế option javac |
| Javadoc | Javadoc task options | Tài liệu có pipeline riêng |
| Editor/VCS | UTF-8 save settings, EditorConfig | Cách source được ghi xuống disk |

Với Java 18+, JEP 400 đưa UTF-8 thành charset mặc định trong nhiều API tiêu chuẩn. Nhưng vì dự án có thể dùng JDK 17 hoặc môi trường đặc biệt, đặt encoding trực tiếp cho JavaCompile vẫn hữu ích và rõ mục đích.

### 6.2. EditorConfig giúp thống nhất bytes file

File `.editorconfig`:

~~~ini
root = true

[*.java]
charset = utf-8
end_of_line = lf
insert_final_newline = true
~~~

Đây là file cấu hình **editor**, không phải một Gradle plugin bắt buộc. Các editor hỗ trợ nó có thể lưu `.java` theo UTF-8 và line endings nhất quán.

Nếu một file hiện có đang sử dụng legacy charset, cần chuyển đổi **bytes thực** với công cụ phù hợp và review thay đổi; chỉ chỉnh `options.encoding` không tự chuyển encoding.

### 6.3. Đừng nhầm -Dfile.encoding

Đặt trong `gradle.properties`:

~~~properties
org.gradle.jvmargs=-Dfile.encoding=UTF-8
~~~

có thể ảnh hưởng Java process chạy Gradle, nhưng **không phải cách thay thế cùng ngữ nghĩa cho `options.encoding`**. Nếu mục tiêu là kiểm soát javac đọc `.java`, hãy dùng `options.encoding` rõ ràng.

Tương tự, `Test.jvmArgs("-Dfile.encoding=UTF-8")` (khi hợp lệ/thiết lập được) chỉ hướng đến JVM test, không tự làm source Java được compiler đọc đúng. Thiết lập JVM default charset còn phụ thuộc JDK version và môi trường.

## 7. Toolchain, release và source/target compatibility

Đây là ba khái niệm rất dễ nhầm.

### 7.1. Java toolchain chọn JDK compiler

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Giúp Gradle chọn JDK 17 cho những tasks được Java plugin tích hợp. Việc Gradle Daemon chạy trên JDK khác **không nhất thiết** làm compiler bị đổi nếu toolchain đã được định nghĩa.

Tuy nhiên máy/CI vẫn phải có toolchain hoặc một resolver/provisioning được cấu hình phù hợp. Không nên mặc định Gradle tự download đúng JDK trong mọi môi trường.

### 7.2. --release chọn mức API, language và bytecode

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Tương đương javac `--release 17`. Nó ngăn source sử dụng cú pháp hoặc JDK API không có ở Java 17, đồng thời tạo classfile target phù hợp.

Ví dụ, nếu compiler thực tế là JDK 21 nhưng `release=17`, code dùng một JDK API chỉ có từ 21 sẽ bị từ chối ngay tại compile time, dù JDK 21 đang được dùng để biên dịch.

### 7.3. sourceCompatibility / targetCompatibility là cơ chế cũ

~~~kotlin
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
~~~

Hai property này gần với `-source` và `-target`. Chúng **không tự đảm bảo** code không tham chiếu JDK APIs ra đời sau target version. Khi mục tiêu là runtime compatibility ở một Java release xác định, ưu tiên `options.release`.

### 7.4. Toolchain mới hơn, release cũ hơn

Ví dụ dùng compiler JDK 21 nhưng tạo bytecode cho Java 17:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Đây là một **mẫu tùy chọn**, không thay đoạn toolchain JDK 17 trong bài thực hành chính. Project phải có/provision JDK 21. `--release` bảo đảm giới hạn APIs/language target mà compiler hỗ trợ; không tự đổi version của compiler.

### 7.5. Đừng truyền source/target mâu thuẫn trong compilerArgs

Cấu hình sau có ý định không nhất quán:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.compilerArgs.addAll(
        listOf("-source", "11", "-target", "11")
    )
}
~~~

`--release` có ưu tiên đối với source/target compatibility của Gradle DSL; thêm flags javac thủ công có thể bị từ chối hoặc khiến khó xác định mục tiêu. Hãy chọn **một nguồn sự thật** cho target API/bytecode.

## 8. CompilerArgs: những flags hay dùng

| Flag | Tác dụng | Lúc nào hữu ích |
| --- | --- | --- |
| `-parameters` | Ghi parameter names cho reflection | Framework binding, DI, metadata |
| `-Xlint:deprecation` | Chi tiết cảnh báo khi dùng API deprecated | Dọn API cũ |
| `-Xlint:unchecked` | Cảnh báo generic casts không kiểm chứng | Kiểm tra type safety |
| `-Xlint:rawtypes` | Cảnh báo raw generic types | Hiện đại hóa source |
| `-Xlint:all` | Bật các cảnh báo javac hỗ trợ | Audit warnings |
| `-Werror` | Fail compilation nếu có warnings | CI nghiêm ngặt |
| `-Xmaxerrs` + số | Giới hạn số lỗi hiện ra | Khi chẩn đoán compile |
| `-Xmaxwarns` + số | Giới hạn số warnings hiện ra | Khi audit warnings |
| `-Akey=value` | Cấu hình annotation processor | Theo tài liệu processor |
| `-proc:none` | Tắt annotation processing | Chỉ khi có lý do |
| `-processor` + class | Chọn processor cụ thể | Advanced processors |
| `--enable-preview` | Bật preview features của JDK tương ứng | Experimental code |

Có thể chỉ định lint categories theo hai cách:

~~~kotlin
options.compilerArgs.addAll(
    listOf("-Xlint:deprecation", "-Xlint:unchecked")
)
~~~

hoặc:

~~~kotlin
options.compilerArgs.add("-Xlint:deprecation,unchecked")
~~~

Với flags không hỗ trợ trên JDK toolchain đã chọn, javac sẽ báo lỗi `invalid flag` hoặc tương đương. Dùng `javac --help`, `javac -X` và tài liệu javac đúng JDK để xác minh.

### 8.1. Mỗi compiler argument là một phần tử

Đúng:

~~~kotlin
options.compilerArgs.addAll(
    listOf("-parameters", "-Xlint:all")
)
~~~

Sai ý tưởng:

~~~kotlin
// Gộp hai đối số thành một String; javac có thể xem là flag lạ.
options.compilerArgs.add("-parameters -Xlint:all")
~~~

Một option đi cùng value thành **hai tokens** khi javac yêu cầu như vậy:

~~~kotlin
options.compilerArgs.addAll(
    listOf("-Xmaxerrs", "200")
)
~~~

Trong khi `-Akey=value` là **một token**, ví dụ `-AcustomMode=strict`.

### 8.2. -parameters khác debug metadata

`-parameters` ghi formal method/constructor parameter names để `java.lang.reflect.Parameter` đọc được. Debug metadata (`-g` hoặc `CompileOptions.debugOptions`) dùng cho line numbers, source file và local variables khi gỡ lỗi.

Bật debug info **không tự thay thế** việc bật `-parameters` cho reflection. Ngược lại, `-parameters` không đảm bảo local variable debug symbols được ghi đầy đủ.

### 8.3. -Werror không tự tạo warning

`-Werror` **nâng những warnings thực sự phát sinh** thành compilation failure. Nếu source không có warning nào, `-Werror` không nhất thiết tạo output riêng. Lệnh này hữu ích cho CI sau khi đội ngũ có chính sách warning và đã làm sạch phần lớn cảnh báo.

## 9. Cấu hình toàn bộ tasks hay chỉ một task?

### 9.1. Áp cho mọi JavaCompile task

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
    options.compilerArgs.add("-parameters")
}
~~~

`configureEach` hỗ trợ **configuration avoidance**. Nó áp cho `compileJava`, `compileTestJava` và những task JavaCompile được đăng ký thêm trong cùng project.

### 9.2. Chỉ production compile

~~~kotlin
tasks.named<JavaCompile>("compileJava") {
    options.compilerArgs.add("-parameters")
}
~~~

Chỉ task `compileJava` nhận flag. Đây là lựa chọn khi test Java compilation có policy khác.

### 9.3. Chỉ compile tests

~~~kotlin
tasks.named<JavaCompile>("compileTestJava") {
    options.compilerArgs.add("-Xlint:unchecked")
}
~~~

Không ảnh hưởng compiler args của `compileJava`.

### 9.4. Cần chú ý custom source sets

Nếu một plugin tạo `compileIntegrationTestJava` hoặc task tương tự, chỉ chỉnh `compileJava` không đủ. Có thể dùng `withType<JavaCompile>().configureEach` để áp chính sách chung, sau đó cấu hình ngoại lệ bằng task name khi có lý do rõ.

### 9.5. Không sửa compilerArgs trong doFirst

Anti-pattern:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    doFirst {
        options.compilerArgs.add("-parameters")
    }
}
~~~

`doFirst` được gọi trong execution phase. Việc mutate input của compiler sát lúc task chạy có thể xung đột với cách Gradle snapshot inputs/build cache. **Cấu hình flags trước execution phase** hoặc dùng `compilerArgumentProviders` nếu flags động.

## 10. Bài thử riêng: warnings và -Werror

Bài thực hành chính không có deprecated API/unchecked cast nên có thể không in warning mặc dù `-Xlint` đã bật. Ta bổ sung một warning có chủ đích.

**src/main/java/demo/Legacy.java**

~~~java
package demo;

public final class Legacy {
    private Legacy() {
    }

    @Deprecated(since = "17")
    public static String oldMessage() {
        return "old";
    }
}
~~~

**src/main/java/demo/WarningDemo.java**

~~~java
package demo;

public final class WarningDemo {
    private WarningDemo() {
    }

    public static String sample() {
        return Legacy.oldMessage();
    }
}
~~~

`WarningDemo` gọi một method `@Deprecated`. Với `-Xlint:deprecation`, javac có thể báo vị trí gọi `Legacy.oldMessage()`.

Chạy:

~~~bash
./gradlew clean compileJava --console=plain
~~~

Nếu muốn chứng minh `-Werror`, thêm tạm:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-Werror")
}
~~~

Rồi chạy lại:

~~~bash
./gradlew clean compileJava --console=plain
~~~

Compiler có warning deprecation và `-Werror` có thể kết thúc compilation bằng failure. **Văn bản diagnostic, line number và formatting phụ thuộc JDK**, không có stdout chung cố định cần sao chép.

Sau thử nghiệm, bỏ `-Werror` và hai source files gây warning nếu muốn project demo ban đầu lại chạy sạch.

### 10.1. Chỉ bật warnings-as-errors qua property

Một tùy chọn bổ sung vào build.gradle.kts:

~~~kotlin
val strictWarnings = providers.gradleProperty("strictWarnings")
    .map { it.equals("true", ignoreCase = true) }
    .orElse(false)

tasks.withType<JavaCompile>().configureEach {
    if (strictWarnings.get()) {
        options.compilerArgs.add("-Werror")
    }
}
~~~

Chạy:

~~~bash
./gradlew -PstrictWarnings=true clean compileJava
~~~

`strictWarnings` là **property không nhạy cảm** điều khiển build policy. Không dùng `-P` để đưa mật khẩu/token vào command line. Trong tổ chức lớn, có thể dùng convention plugin để CI/local đồng bộ chính sách.

## 11. Compiler flags khác JVM flags

Một project Gradle Java có ít nhất ba JVM context:

1. **Gradle Daemon JVM** đang chạy build engine.
2. **Compiler JVM/JDK** đang cung cấp javac (có thể dùng Compiler API/fork).
3. **Application/Test JVM** đang thực thi code sau compile.

| Muốn cấu hình | Chỗ phù hợp |
| --- | --- |
| JDK chạy Gradle | Gradle daemon criteria / JAVA_HOME tùy setup |
| JDK compiler | Java toolchain / `JavaCompile.javaCompiler` |
| Charset source | `JavaCompile.options.encoding` |
| Javac flags | `JavaCompile.options.compilerArgs` |
| Bytecode/API target | `JavaCompile.options.release` |
| RAM của Daemon | `org.gradle.jvmargs` |
| RAM của compiler fork | `JavaCompile.options.forkOptions` |
| Java system property của test | `Test.jvmArgs` |
| Java system property của app run | `JavaExec.jvmArgs` |

Ví dụ RAM Gradle Daemon trong `gradle.properties`:

~~~properties
org.gradle.jvmargs=-Xmx2g
~~~

Không phải một cách tăng RAM trực tiếp cho compiler process độc lập hoặc chương trình Java khi chạy.

### 11.1. Fork compiler

Trong một project có JavaCompile tasks:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.isFork = true
    options.forkOptions.memoryMaximumSize = "1g"
}
~~~

Đây là **mẫu tùy chọn**, không cần cho project demo chính. `isFork=true` yêu cầu compiler chạy bằng cơ chế fork theo Gradle, nhưng **không nhất thiết tạo một process mới cho mỗi task**.

Cấu hình fork có thể tăng isolation hoặc giúp xử lý memory/performance đặc biệt, nhưng cũng tăng overhead. Chỉ thay khi đã đo lường vấn đề.

### 11.2. Test JVM args

~~~kotlin
tasks.withType<Test>().configureEach {
    jvmArgs("-Ddemo.testMode=true")
}
~~~

Lệnh này truyền system property cho **test JVM**, không làm javac bật `-parameters`.

### 11.3. JavaExec runtime args

~~~kotlin
tasks.withType<JavaExec>().configureEach {
    jvmArgs("-Ddemo.mode=runtime")
}
~~~

Mảnh này ảnh hưởng JavaExec tasks như `run` của application plugin, không thay compiler flags hoặc source encoding.

Không đưa `-Xmx1g` vào `options.compilerArgs` rồi mong nó là JVM memory argument; dùng đúng context.

## 12. compilerArgumentProviders cho flags động

`options.compilerArgs` phù hợp cho đối số **cố định**. Nếu một custom plugin cần sinh flags từ Gradle properties/file inputs một cách lazy, có thể dùng `CommandLineArgumentProvider`.

Gradle dùng các annotations như `@Input`, `@InputFile`, `@Classpath` và `@PathSensitive` để hiểu đâu là đầu vào quyết định command-line arguments. Điều này có thể quan trọng cho incremental compile, build cache và reproducibility.

### 12.1. Một ví dụ Kotlin DSL với Boolean input

Đây là **mẫu build.gradle.kts riêng**, minh họa sử dụng `compilerArgumentProviders`. Nó không thay file `application` của project demo chính.

~~~kotlin
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.process.CommandLineArgumentProvider
import javax.inject.Inject

plugins {
    java
}

abstract class LintOptions @Inject constructor() :
    CommandLineArgumentProvider {

    @get:Input
    abstract val enabled: Property<Boolean>

    override fun asArguments(): Iterable<String> =
        if (enabled.get()) {
            listOf("-Xlint:deprecation")
        } else {
            emptyList()
        }
}

val lintOptions = objects.newInstance<LintOptions>().apply {
    enabled.set(
        providers.gradleProperty("javacLint")
            .map { it.equals("true", ignoreCase = true) }
            .orElse(false)
    )
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.compilerArgumentProviders.add(lintOptions)
}
~~~

Khi chạy:

~~~bash
./gradlew -PjavacLint=true compileJava
~~~

provider trả danh sách gồm `-Xlint:deprecation`. Với:

~~~bash
./gradlew -PjavacLint=false compileJava
~~~

provider trả danh sách rỗng. Bản thân hai lệnh có thể không in gì nếu không có warning và task không cần chạy.

### 12.2. Vì sao cần @Input?

`enabled` là quyết định xem một flag có được truyền cho javac hay không. Đánh dấu `@Input` giúp Gradle xem thay đổi này là một task input có liên quan.

Nếu provider đọc **nội dung một file**, chỉ đánh dấu một string đường dẫn là `@Input` có thể không đủ: nội dung file đổi nhưng path vẫn như cũ. Hãy dùng `@InputFile` và `@PathSensitive`, hoặc `@Classpath` cho JAR classpath, theo đúng nghĩa của input.

Đừng sử dụng `asArguments()` để download tài nguyên, sinh file, in secrets hoặc tự đọc environment không được khai báo. Hàm này nên trả đối số từ những inputs đã định nghĩa.

### 12.3. Khi không cần provider

Với `-parameters`, `-Xlint:unchecked` và `-Werror` tĩnh, dùng `options.compilerArgs.add(...)` là đủ và đơn giản hơn. `CommandLineArgumentProvider` không phải nghĩa vụ cho mọi project, mà là công cụ nâng cao khi build logic có flags động hoặc cần chia sẻ trong plugin.

## 13. Annotation processing và compiler arguments

Java annotation processors chạy trong quá trình compile để phân tích annotations/sinh code. Ví dụ quen thuộc: Lombok, MapStruct, AutoValue hoặc Dagger.

### 13.1. Khai báo processor trên đúng classpath

Ví dụ mảnh cấu hình khi dự án thực sự dùng Lombok:

~~~kotlin
repositories {
    mavenCentral()
}

dependencies {
    compileOnly("org.projectlombok:lombok:1.18.34")
    annotationProcessor("org.projectlombok:lombok:1.18.34")

    testCompileOnly("org.projectlombok:lombok:1.18.34")
    testAnnotationProcessor("org.projectlombok:lombok:1.18.34")
}
~~~

Đây là **mẫu bổ sung**, không cần cho Greeter/Main; version chỉ minh họa, cần chọn bản tương thích với JDK và các plugins của dự án thực tế.

- `compileOnly`: cung cấp annotation types ở compile classpath, không tự đưa library vào runtime.
- `annotationProcessor`: đưa processor lên **processor path** để javac tìm/chạy.
- `testAnnotationProcessor`: tương tự cho test source.
- `options.annotationProcessorPath` là JavaCompile property liên quan; Java plugin thiết lập dựa trên configurations tương ứng.

### 13.2. Flag -Akey=value

Một processor có thể nhận options riêng, ví dụ:

~~~kotlin
tasks.named<JavaCompile>("compileJava") {
    options.compilerArgs.add("-AcustomMode=strict")
}
~~~

`customMode` chỉ là **tên minh họa**; muốn hoạt động, processor thực tế phải hỗ trợ key đó. Nếu processor không xử lý option, javac có thể báo warning hoặc bỏ qua theo behavior tương ứng. Đọc tài liệu annotation processor trước khi cấu hình.

### 13.3. -proc:none

~~~kotlin
tasks.named<JavaCompile>("compileJava") {
    options.compilerArgs.add("-proc:none")
}
~~~

Đây là lệnh **tắt annotation processing**, không phải optimization luôn an toàn. Nếu code cần generated classes, build sẽ thất bại vì output không được tạo. Chỉ dùng cho chẩn đoán hoặc khi chủ động không sử dụng processors.

### 13.4. Không tự tạo output bằng -s

`JavaCompile.options.generatedSourceOutputDirectory` cho Gradle biết thư mục output của generated Java sources. Truyền `-s` thủ công qua compilerArgs có thể làm output nằm ngoài nơi Gradle theo dõi, dẫn đến lỗi incremental/build cache hoặc đụng file do task khác quản lý.

Khi cần tùy biến, dùng typed property tương ứng và một thư mục build dành riêng cho task.

## 14. Preview features yêu cầu compile và runtime flags

Java preview features chỉ dành cho **release hiện hành của compiler được dùng**. Để thử preview feature trên JDK 17, dự án phải dùng toolchain JDK 17 và cấu hình cả compiler lẫn JVM runtime.

Mảnh bổ sung cho project có Java plugin:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.compilerArgs.add("--enable-preview")
}

tasks.withType<Test>().configureEach {
    jvmArgs("--enable-preview")
}

tasks.withType<JavaExec>().configureEach {
    jvmArgs("--enable-preview")
}
~~~

Giải thích:

- Compile cần javac `--enable-preview`.
- Test JVM cần runtime `--enable-preview` nếu chạy preview bytecode.
- App chạy bằng JavaExec cũng cần flag.
- `java -cp ...` hoặc `java -jar ...` bên ngoài Gradle phải nhận flag tương ứng khi cần.

**Project demo ở mục 4 không dùng preview**, vì vậy không thêm đoạn trên khi chỉ muốn kiểm tra encoding hoặc reflection.

Nếu toolchain là JDK 21 nhưng bạn đặt `options.release.set(17)`, không được bật preview theo cách nghĩ “dùng preview của Java 17”; javac chỉ hỗ trợ preview của release compiler phù hợp. Preview không phải cơ chế giữ ứng dụng tương thích JVM cũ.

## 15. Groovy DSL tương đương

Nếu project dùng `build.gradle` Groovy DSL, cấu hình tương đương bài thực hành chính:

~~~groovy
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.Main'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
    options.compilerArgs.addAll([
        '-parameters',
        '-Xlint:deprecation',
        '-Xlint:unchecked'
    ])
}
~~~

Với cùng `demo.Greeter` và `demo.Main`, lệnh:

~~~bash
./gradlew --quiet clean run
~~~

in ba dòng stdout ở mục 4.

Đừng đặt cả hai file `build.gradle` và `build.gradle.kts` với cấu hình cùng mục đích rồi mong Gradle tự kết hợp chúng; một project nên theo DSL và convention đã được chọn.

## 16. Incremental compilation, task inputs và build cache

Trong Gradle hiện đại, JavaCompile thường hỗ trợ incremental compilation:

- Không đổi source/classpath/compiler flags → task có thể `UP-TO-DATE`.
- Cùng input và cache key phù hợp → có thể `FROM-CACHE` nếu build cache dùng được.
- Không có Java source → task có thể `NO-SOURCE`.
- Source file hoặc ABI/classpath thay đổi → Gradle đánh giá lại các compilation units cần chạy.
- Flags như `-parameters` hoặc `options.encoding` đổi → compilation output có thể khác, nên cần được tính vào task inputs.

Ví dụ bật/bỏ `-parameters` làm `.class` của method `greet` khác ở metadata. Nếu Gradle không biết flag đổi thì cache có nguy cơ phục hồi output sai. Đây là lý do nên dùng DSL properties và providers có annotated inputs thay vì đọc file/env tùy tiện trong task action.

### 16.1. Annotation processors có thể ảnh hưởng hiệu suất

Một processor không hỗ trợ incremental annotation processing hoặc được cấu hình sai path có thể khiến Gradle compile rộng hơn cần thiết. Khai báo processor đúng `annotationProcessor`, dùng phiên bản tương thích và để Gradle quản lý generated output.

Không mặc định tắt incremental compilation để tránh một lỗi không xác định. Trước tiên kiểm tra source set, processor log, compiler options và task execution reasons.

### 16.2. Không đồng nhất UP-TO-DATE với compiler chưa nhận flags

Nếu Gradle báo `:compileJava UP-TO-DATE`, javac action không chạy trong lần đó, nên bạn không thấy warnings. Khi muốn chứng minh warnings cho một fixture, có thể chạy:

~~~bash
./gradlew clean compileJava --console=plain
~~~

Đối với build thường ngày, không cần `clean` mọi lần; Gradle đã có input tracking. Dùng `clean` phục vụ chẩn đoán để loại bỏ output cũ.

## 17. Gỡ lỗi và kiểm tra compiler thực tế

### 17.1. Các lệnh cơ bản

~~~bash
./gradlew --version
./gradlew javaToolchains
./gradlew clean compileJava --console=plain
./gradlew compileJava --info --console=plain
./gradlew test --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat javaToolchains
.\gradlew.bat clean compileJava --console=plain
.\gradlew.bat compileJava --info --console=plain
.\gradlew.bat test --console=plain
~~~

`./gradlew --version` báo JVM/Gradle đang chạy, **không nhất thiết là JDK mà JavaCompile chọn bằng toolchain**. `javaToolchains` giúp liệt kê JDK installations Gradle nhìn thấy. `--info` cho thêm diagnostics về task/compilation, nhưng không có bảo đảm mọi phiên bản Gradle đều in nguyên một command line `javac` dễ copy.

### 17.2. Kiểm tra classfile

~~~bash
javap -v build/classes/java/main/demo/Greeter.class
~~~

Tìm:

- `major version: 61` nếu class targeting Java 17.
- `MethodParameters` có tên `name` nếu `-parameters` đã được áp.
- Constant pool/bytecode phù hợp, nhưng không cần snapshot toàn bộ output.

### 17.3. Kiểm tra Java source bytes

Nếu code có tiếng Việt và một máy compile lỗi:

1. Kiểm tra editor đang lưu file `.java` bằng charset nào.
2. Kiểm tra JavaCompile `options.encoding`.
3. Xác định compiler toolchain và Gradle version.
4. Nếu compile thành công nhưng console sai dấu, xem encoding terminal/output stream riêng.
5. Không sửa source literal thành ASCII escape một cách vội vàng khi vấn đề nằm ở console.

### 17.4. Tách runtime và compile problems

`NoClassDefFoundError` hoặc `NoSuchMethodError` sau khi compile thành công thường liên quan runtime classpath/API compatibility, không nhất thiết do compilerArgs. Trước khi đổi flags, dùng:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency your-module --configuration runtimeClasspath
~~~

Mảnh lệnh này chỉ có ý nghĩa nếu project có Java runtimeClasspath configuration và một module thực để thay `your-module`.

## 18. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| `unmappable character` | File không có encoding mà compiler dùng | Chuyển file sang UTF-8, đặt `options.encoding` |
| Tiếng Việt in thành ký tự lạ | Console charset hoặc source encoding sai | Phân biệt bytes source và console output |
| Reflection cho `arg0` | Không có `-parameters` khi compile | Cấu hình đúng task và clean compile |
| `namePresent=false` | Bytecode thiếu `MethodParameters` | Dùng javap và xác minh flags |
| `invalid flag` | Gộp flags hoặc unsupported JDK option | Mỗi token riêng, xem `javac -X` |
| Compiler không hỗ trợ release | Toolchain quá cũ | Dùng JDK compiler hỗ trợ target |
| Dùng API JDK mới nhưng muốn chạy JVM cũ | Chỉ đặt targetCompatibility | Dùng `options.release` phù hợp |
| Warning không hiện | Không có code gây warning hoặc task UP-TO-DATE | Dùng warning fixture/clean để thử |
| CI fail do `-Werror` | Warning thực tế bị nâng thành error | Sửa warning hoặc policy hợp lý |
| Compile test khác main | Chỉ cấu hình `compileJava` | Dùng `withType` nếu muốn đồng bộ |
| Flags trùng lặp | Plugin khác cũng thêm flags | Rà soát convention plugins/tasks |
| JVM memory flag ở compilerArgs | Nhầm compiler flags và JVM flags | Dùng forkOptions/Daemon JVM context |
| Annotation processor không chạy | Sai dependency scope hoặc `-proc:none` | Dùng `annotationProcessor`, bỏ flag khi cần |
| Generated source bị thiếu | Processor không được chạy/path sai | Kiểm tra processor path/output |
| Preview code compile nhưng runtime fail | Thiếu `--enable-preview` lúc chạy | Set Test/JavaExec.jvmArgs |
| Test JVM flags không thay javac behavior | Sai process context | Chỉnh JavaCompile.options |
| Kotlin source không bị ảnh hưởng | KotlinCompile là task khác | Cấu hình Kotlin compilerOptions |
| Compiler flags đổi nhưng output vẫn cũ | Đọc nhầm output/cached state | Kiểm tra task graph và class path |
| Gradle Daemon JDK khác compiler JDK | Toolchain độc lập | Kiểm tra `javaToolchains` |
| Build chậm sau bật fork | Process overhead | Đo lường và cân nhắc bỏ fork |
| Output từ annotation processing phá cache | Inputs/outputs không được khai báo | Dùng providers/typed output và processor đúng |
| `--debug` in nhiều thông tin nhạy cảm | Log chứa path/classpath/options | Hạn chế log, không đưa secrets vào flags |

## 19. Bài tập tự kiểm tra có đáp án

**Câu 1.** Đặt UTF-8 cho tất cả JavaCompile tasks bằng Kotlin DSL.

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

**Câu 2.** Framework cần method parameter name qua reflection; cần flag nào?

**Đáp án:** `-parameters` trong JavaCompile `options.compilerArgs`. Kiểm tra `Parameter.isNamePresent()` thay vì chỉ nhìn tên tham số ở source.

**Câu 3.** Đã đặt `-parameters` nhưng vẫn thấy `arg0`, vì sao?

**Đáp án:** Có thể task tạo `.class` không nhận flag, compile chưa chạy lại hoặc bạn đang đọc một artifact cũ. Clean compile và dùng `javap -v` tìm `MethodParameters`.

**Câu 4.** Muốn compile bằng JDK 21 nhưng tạo bytecode chỉ dùng APIs Java 17?

**Đáp án:**

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

**Câu 5.** Vì sao targetCompatibility không thay thế hoàn toàn --release?

**Đáp án:** Target compatibility chọn classfile target nhưng không ràng buộc JDK API được phép tham chiếu bằng độ mạnh của `--release`.

**Câu 6.** `options.compilerArgs.add("-parameters -Xlint:all")` đúng chưa?

**Đáp án:** Không. Đây là một string duy nhất. Dùng `addAll(listOf("-parameters", "-Xlint:all"))`.

**Câu 7.** `-Werror` có tự sửa deprecation không?

**Đáp án:** Không. Nó khiến compile fail khi warnings tồn tại; code hoặc chính sách warnings phải được xử lý riêng.

**Câu 8.** `org.gradle.jvmargs=-Xmx2g` có đặt RAM của app chạy bằng JavaExec không?

**Đáp án:** Không. Nó điều chỉnh Gradle JVM process; app JVM/JavaExec có cấu hình riêng.

**Câu 9.** `options.encoding` có buộc IDE save source thành UTF-8 không?

**Đáp án:** Không. Nó chỉ bảo javac cách giải mã file. Để editor lưu bytes đúng, dùng setting IDE/EditorConfig và chuyển mã file nếu cần.

**Câu 10.** Một annotation processor có được thêm chỉ bằng `implementation(...)` không?

**Đáp án:** Với Gradle Java hiện đại, khai báo processor rõ bằng `annotationProcessor(...)`; annotation types có thể cần compileOnly/implementation tùy library.

**Câu 11.** Dùng `-proc:none` có thể gây lỗi gì?

**Đáp án:** Generated classes không được sinh nếu project phụ thuộc vào annotation processing, khiến compile fail.

**Câu 12.** Khi nào sử dụng `compilerArgumentProviders`?

**Đáp án:** Khi compiler args được tạo từ inputs động và cần Gradle theo dõi chính xác; khai báo các properties ảnh hưởng flags bằng `@Input`, `@InputFile` hoặc loại annotation thích hợp.

**Câu 13.** Preview features chỉ cần `options.compilerArgs.add("--enable-preview")` là đủ?

**Đáp án:** Chưa. JVM chạy application/test cũng cần `--enable-preview` tương ứng và JDK/release phù hợp.

**Câu 14.** Vì sao JavaCompile warning không xuất hiện ở lần build thứ hai?

**Đáp án:** Task có thể UP-TO-DATE hoặc FROM-CACHE, nên javac action không chạy. Muốn kiểm tra fixture warnings, clean compile.

**Câu 15.** Nếu build có cả Java và Kotlin source, `withType<JavaCompile>` có điều chỉnh Kotlin compiler không?

**Đáp án:** Không, Kotlin compiler tasks có DSL riêng; chỉ Java source được JavaCompile xử lý.

## 20. Checklist áp dụng trong dự án thật

1. Dùng Gradle Wrapper của repository và xác định JDK toolchain cần thiết.
2. Đặt source files `.java` dưới UTF-8 bằng IDE/EditorConfig.
3. Đặt `options.encoding = "UTF-8"` cho những JavaCompile tasks tương ứng.
4. Khai báo `options.release` khi cần Java APIs/bytecode target chắc chắn.
5. Đặt compiler flags qua `options.compilerArgs`, đúng token syntax.
6. Bật `-parameters` khi cần metadata reflection.
7. Bật `-Xlint` có mục tiêu và xác định chính sách dùng `-Werror`.
8. Phân biệt JavaCompile arguments, compiler JVM memory, Gradle Daemon args, Test/JavaExec JVM args.
9. Khai báo `annotationProcessor` và `testAnnotationProcessor` đúng configuration.
10. Không tự thay `-d`, `-classpath`, `-s`, `-encoding` hoặc `--release` khi đã có typed Gradle properties.
11. Với flags động, dùng `compilerArgumentProviders` và input annotations.
12. Tránh `doFirst` mutation và secrets trong javac command line.
13. Chạy compile/test trên CI và kiểm tra generated classes hoặc reflection output.
14. Kiểm tra source encoding và console encoding như hai vấn đề riêng.
15. Đối chiếu Gradle và `javac` docs đúng phiên bản trước khi dùng flags nâng cao.

**Ghi nhớ:**

~~~text
options.encoding = "UTF-8"
    -> Javac đọc file nguồn .java bằng UTF-8

options.release.set(17)
    -> Cú pháp, JDK APIs và classfile target Java 17

java.toolchain
    -> Chọn JDK compiler, không phải danh sách flags

options.compilerArgs.add("-parameters")
    -> Lưu parameter names cho reflection

options.compilerArgs.add("-Xlint:deprecation")
    -> Bật diagnostics cho API deprecated

options.compilerArgumentProviders
    -> Tạo flags động từ các Gradle inputs đã khai báo

KHÔNG NHẦM:
    compilerArgs != Test.jvmArgs != JavaExec.jvmArgs != org.gradle.jvmargs
~~~

## 21. Nguồn tài liệu chính thức

1. Gradle — Building Java & JVM Projects: https://docs.gradle.org/current/userguide/building_java_projects.html
2. Gradle — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
3. Gradle — CompileOptions DSL: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.CompileOptions.html
4. Gradle — JavaCompile Java API: https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/compile/JavaCompile.html
5. Gradle — Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
6. Gradle — Java Library Plugin and Annotation Processing: https://docs.gradle.org/current/userguide/java_library_plugin.html
7. Gradle — Gradle Build Performance: https://docs.gradle.org/current/userguide/performance.html
8. Gradle — Configuring Gradle JVM: https://docs.gradle.org/current/userguide/config_gradle.html
9. Oracle — Java 17 javac command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
10. OpenJDK — JEP 400 (UTF-8 by Default): https://openjdk.org/jeps/400

Đường dẫn `current` mô tả API Gradle hiện hành; dự án cụ thể có thể dùng một Gradle Wrapper khác. Nên kiểm tra tài liệu đúng bản Wrapper/JDK đang chạy, đặc biệt khi tùy chọn javac, compilerArgumentProviders hoặc hành vi annotation processing thay đổi giữa các bản phát hành.