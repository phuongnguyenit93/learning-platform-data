# Plugin IDE, trình phân tích cú pháp và mức ngôn ngữ của dự án

## 1. Một dự án Java có thể biên dịch thành công nhưng IDE vẫn báo lỗi

Khi nâng JDK, nhóm phát triển thường chú ý đến `javac`, phiên bản Gradle/Maven và runtime production. Tuy nhiên, còn một hệ công cụ khác đọc và phân tích mã Java mỗi ngày: **IDE, language server, plugin, formatter, static analyzer, generator và test tooling**.

Giả sử một dự án đã nâng compiler lên JDK 21 và dùng pattern matching trong `switch`:

~~~java
static String describe(Object value) {
    return switch (value) {
        case Integer number -> "integer: " + number;
        case String text -> "text: " + text;
        case null -> "absent";
        default -> "other";
    };
}
~~~

Đây là một dạng cú pháp được hỗ trợ chính thức trong Java 21. Build ngoài terminal có thể thành công, nhưng một IDE hoặc plugin phân tích Java cũ vẫn gạch đỏ `case Integer number`. Trong tình huống đó, việc sửa code theo cảnh báo IDE có thể vô tình làm mất một tính năng hợp lệ của Java 21. Ở hướng ngược lại, IDE có thể hiểu cú pháp mới, nhưng CI dùng compiler JDK 17 hoặc cấu hình `--release 17` nên build thất bại.

Một số triệu chứng thường gặp:

- IDE báo `record`, `sealed` hoặc cú pháp `switch` mới là lỗi dù `javac` đích chấp nhận.
- Plugin Checkstyle/PMD hoặc formatter không parse được một file mới.
- Annotation processor chạy trong compiler gây `IllegalAccessError` sau khi đổi JDK.
- Một plugin hoặc coverage agent đọc class file rồi báo `Unsupported class file major version`.
- Generated source do OpenAPI, JAXB, protobuf hoặc Lombok tạo ra dùng API/cú pháp khác mức Java của module.
- IDE và terminal hiển thị hai kết quả kiểm tra khác nhau.
- IDE import dự án bằng một Gradle JVM khác với JDK mà project đang chọn.

Vấn đề chính là **không chỉ có một “phiên bản Java” trong dự án**. Mỗi công cụ có phiên bản parser, runtime và phạm vi hỗ trợ riêng. Bài học này hướng dẫn cách xác định đúng lớp bị lỗi, chọn mức ngôn ngữ phù hợp, quản lý plugin IDE và kiểm chứng hệ thống khi migration trong ngữ cảnh **Java Advance Compatibility Migration – Sinh mã và công cụ test**.

## 2. Phân biệt sáu khái niệm thường bị gọi chung là “Java version”

| Khái niệm | Vai trò | Ví dụ rủi ro |
| --- | --- | --- |
| IDE runtime | JVM chạy chính tiến trình IDE hoặc language server | IDE/plugin không chạy trên JVM mới |
| Project SDK/JDK | JDK gắn với project/module để biên dịch hoặc hỗ trợ code insight | IDE thấy Java 21 nhưng CI dùng JDK 17 |
| Language level | Phiên bản cú pháp/ngữ nghĩa Java mà source được phép dùng | IDE coi `record` là lỗi nếu module đặt mức quá thấp |
| Compiler toolchain | Compiler/JDK được build tool chọn cho tác vụ biên dịch | `javac` quá cũ không hiểu source release được yêu cầu |
| Target release/class-file version | API Java và dạng bytecode mà artifact hướng tới | Artifact Java 21 không chạy trên JVM Java 17 |
| Test/application runtime | JVM thực sự chạy tests và ứng dụng | Compile thành công nhưng test runner/agent không hỗ trợ JDK mới |

Ngoài ra còn **phiên bản riêng của parser**, có thể nằm trong Java language server, IDE plugin, code analyzer hoặc code generator. Một parser thường được phát hành độc lập với JDK và có thể không hỗ trợ cú pháp mới dù compiler dự án hỗ trợ.

Ví dụ ghi nhận một cấu hình thực tế:

~~~text
IDE version:             bản đã kiểm tra hỗ trợ Java 21
IDE runtime:             JBR hoặc JDK dùng để khởi chạy IDE
Project SDK:             JDK 21
Module language level:   Java 17
Gradle daemon JVM:       JDK được Gradle release hỗ trợ
Java compiler toolchain: JDK 21
Java --release target:   17
JUnit test runtime:      JDK 17 và/hoặc JDK 21
Production runtime:      Java 17 (mức tối thiểu còn được hỗ trợ)
~~~

Cấu hình này **có thể hợp lệ** nếu mục tiêu là dùng công cụ mới để biên dịch thư viện vẫn tương thích Java 17. Nó không có nghĩa source được phép dùng cú pháp chỉ xuất hiện trong Java 21. Chọn compiler mới và chọn source language level là hai quyết định khác nhau.

## 3. IDE parser, Java compiler và bytecode reader không làm cùng một việc

Một file Java có thể đi qua nhiều bộ phân tích:

~~~text
             File .java
                  |
        +---------+----------+
        |                    |
        v                    v
 IDE / Language Server    javac / ECJ
 parser + AST             compile + type checking
        |                    |
        v                    v
 Inspections, formatter    File .class
 refactoring, navigation      |
                              v
                        ASM / Byte Buddy /
                        JaCoCo / analyzers
                              |
                              v
                           JVM runtime
~~~

**Source parser** nhận cú pháp Java và tạo một cấu trúc như AST (Abstract Syntax Tree). Nó cần biết những cấu trúc ngôn ngữ được cho phép ở release đang phân tích: `record`, `sealed`, switch pattern, text block, lambda, v.v.

**Compiler** thực hiện nhiều bước hơn parse: resolve tên/type, áp dụng luật ngôn ngữ, annotation processing và sinh bytecode. IDE parser có thể hiểu cấu trúc nhưng compiler vẫn từ chối vì type error, API không có trong `--release` hoặc configuration sai.

**Bytecode parser** như ASM/Byte Buddy đọc class file thay vì Java source. Nó phải hiểu class-file major version, constant pool và attributes mới. Một tool có thể hỗ trợ source Java 21 nhưng bytecode reader vẫn không hiểu class-file version 65, hoặc ngược lại.

**JVM runtime** thực thi bytecode. Thành công ở IDE và compiler chưa chứng minh runtime có module, dependency, agent, native library hoặc mức Java cần thiết.

Không nên sửa lỗi của một tầng bằng cách đổi cấu hình tầng khác mà không xác định nguyên nhân. Ví dụ tăng IDE language level không nâng `javac`; nâng `javac` không tự nâng parser của Checkstyle.

## 4. Mức ngôn ngữ Java (language level) cụ thể là gì?

*Language level* quy định các tính năng **cú pháp và ngữ nghĩa của mã nguồn** có thể sử dụng. Một số mốc minh họa:

| Java release | Tính năng ngôn ngữ tiêu biểu |
| --- | --- |
| Java 8 | Lambda expressions, method references, default methods |
| Java 9 | Module declarations (`module-info.java`), một số cải tiến cú pháp |
| Java 10 | Local-variable type inference bằng `var` |
| Java 14 | Switch expressions được chuẩn hóa |
| Java 15 | Text blocks được chuẩn hóa |
| Java 16 | Records và pattern matching cho `instanceof` được chuẩn hóa |
| Java 17 | Sealed classes được chuẩn hóa |
| Java 21 | Record patterns và pattern matching for `switch` được chuẩn hóa |

Bảng nêu những cột mốc tiêu biểu, không liệt kê toàn bộ thay đổi của từng bản. Một tính năng có thể từng trải qua preview trước khi được chuẩn hóa. Khi dùng preview feature, cú pháp và mức hỗ trợ phải được xét theo **đúng JDK release**.

### 4.1. Ví dụ source level thấp hơn tính năng

~~~java
public record UserId(String value) {
}
~~~

Record là tính năng chuẩn từ Java 16. Nếu module đặt language level Java 11, IDE có cơ sở cảnh báo; compiler sử dụng `--release 11` cũng sẽ từ chối. Khi đó không nên “sửa IDE cho hết đỏ” bằng cách chọn language level 21 nếu sản phẩm vẫn phải phát hành Java 11.

Phải chọn một trong hai hướng có chủ đích:

1. Nâng mức Java mà module cam kết hỗ trợ, sau đó đổi toolchain, tests và runtime tương ứng.
2. Giữ mức Java thấp, thay cách biểu diễn bằng class phù hợp release đó.

### 4.2. Language level không phải runtime version

IDE cho phép viết Java 17 không có nghĩa code có thể chạy trên Java 8. Ngược lại, chạy `javac` của JDK 21 với `--release 17` có thể tạo artifact tương thích nền tảng Java 17 mà không yêu cầu runtime Java 21.

Ở cấp ứng dụng nhiều module, một module có thể có language level thấp hơn module khác. Điều này chỉ an toàn khi **mối quan hệ compile/runtime** được xác định rõ; module dùng chung không nên vô tình phụ thuộc vào API hoặc bytecode yêu cầu runtime cao hơn những consumer còn phải hỗ trợ.

## 5. Source language level, Java API và bytecode là ba ràng buộc riêng

Ba ví dụ sau minh họa:

~~~java
// Yêu cầu Java 16+ về cú pháp record.
public record Point(int x, int y) {
}
~~~

~~~java
// Cú pháp không đặc biệt mới, nhưng API List.of cần Java 9+.
List<String> roles = List.of("reader", "writer");
~~~

~~~java
// Một thư viện được compile thành class-file major 65
// yêu cầu JVM có thể nạp class-file Java 21.
~~~

Nếu chỉ đặt `-source 8` hoặc language level 8 nhưng vẫn compile với JDK mới và không ràng buộc platform APIs, compiler có thể nhìn thấy các API Java mới không thuộc Java 8. Muốn xây artifact dùng được trên nền tảng Java cũ, nên xét `javac --release N` theo JDK/toolchain hỗ trợ.

Lệnh minh họa:

~~~bash
javac --release 17 -d build/classes src/main/java/example/Main.java
~~~

`--release 17` giới hạn cú pháp/ngữ nghĩa và Java platform APIs theo release 17, đồng thời tạo class-file target phù hợp. Nó **không bảo đảm** rằng mọi dependency bên thứ ba được dùng cũng chạy trên Java 17: vẫn phải kiểm tra JARs và thử trên runtime tối thiểu.

### 5.1. Khi IDE và build tool khác nhau, build là nguồn kiểm chứng

Mức ngôn ngữ của IDE có thể được chọn thủ công hoặc suy ra từ Maven/Gradle import. Nếu build script xác định `--release 17` nhưng IDE đang hiển thị Java 21, warning của IDE có thể chưa đại diện cho build CI. Một thay đổi code chỉ được coi là hợp lệ sau khi **compile bằng toolchain và release target chính thức của dự án**.

Không nên tắt hết cảnh báo IDE vì “CI mới là nguồn chân lý”; IDE vẫn hữu ích để phát hiện lỗi sớm. Cần **đồng bộ cấu hình** để hai hệ thống đưa ra kết luận nhất quán.

## 6. Phiên bản IDE và phiên bản plugin cần được kiểm kê

Một IDE là hệ sinh thái gồm nhiều thành phần:

- IDE core và parser Java chính.
- Extension/plugin thêm syntax support, refactoring, framework integration.
- Language server hoặc Java extension host (ở một số editor).
- Build integration như Gradle, Maven, Kotlin, Groovy.
- Formatter, static analyzer, code quality plugins.
- Test runner, coverage/debugger và bytecode tooling.
- Plugin sinh mã từ schema hoặc annotation processor.

**Phiên bản IDE mới không tự chứng minh tất cả plugin được cài cũng hỗ trợ language level mới.** Một plugin có thể dùng AST API của IDE đã đổi, parser riêng chưa có cú pháp Java mới, hoặc runtime libraries không hỗ trợ class-file version mới.

Khi chọn bộ phiên bản cho migration, ghi:

| Thành phần | Điều cần xác nhận |
| --- | --- |
| IDE release | Có hỗ trợ Java syntax và project model mục tiêu không |
| IDE runtime | IDE chạy trên runtime được nhà cung cấp hỗ trợ không |
| Plugin release | Có hỗ trợ IDE build, parser/AST API và JDK đích không |
| Plugin runtime dependencies | Có bytecode/parser libraries phù hợp không |
| Build integration | Maven/Gradle import có đọc đúng toolchain/release không |
| Test support | Runner, debugger và coverage hỗ trợ class files đích không |

Không nên đưa ra kết luận chỉ từ tên plugin hoặc giả định “release mới nhất luôn đúng”. Cần đọc compatibility information của **phiên bản cụ thể** và kiểm chứng bằng sample project.

## 7. IntelliJ IDEA: Project SDK, language level và Gradle JVM

Ở IntelliJ IDEA, có thể phải xét các lựa chọn độc lập:

1. **JDK dùng để chạy IDE:** thường được IDE phân phối hoặc cấu hình riêng; không đồng nghĩa Project SDK.
2. **Project SDK:** JDK gắn với project.
3. **Project language level:** cú pháp mà IDE cho phép ở project.
4. **Module language level:** có thể khác project nếu module cấu hình riêng.
5. **Gradle JVM:** JVM chạy Gradle daemon khi IDE gọi Gradle.
6. **Maven importer/runner JDK:** JDK dùng cho Maven integration.
7. **Compiler và test run configuration:** có thể có lựa chọn riêng theo build.

Vị trí menu trong UI thay đổi theo phiên bản IDE; nên tìm các phần **Project Structure**, **SDK**, **Language Level**, **Gradle settings**, **Maven settings** và **Run Configurations** theo bản đang dùng, thay vì phụ thuộc vào đường dẫn menu được ghi từ một bản cũ.

### 7.1. Trường hợp IDE gạch đỏ còn Gradle build thành công

Ví dụ:

~~~text
IDE Project SDK:       Java 17
IDE language level:    17
Gradle toolchain:      Java 21
Gradle compile target: 21
Source:                Java 21 pattern switch
~~~

Gradle có thể compile mã Java 21, nhưng IDE cấu hình Java 17 có thể phân tích như cú pháp không hợp lệ. Cần import lại project model và xác nhận language level thực tế, thay vì sửa source theo gợi ý của IDE cũ.

### 7.2. Trường hợp IDE xanh còn CI lỗi

~~~text
IDE language level:    21
Gradle release target: 17
Source:                Java 21 pattern switch
~~~

IDE có thể hiểu cú pháp nhưng CI đúng khi từ chối vì artifact phải tương thích Java 17. Cách sửa là **thống nhất hợp đồng mức Java**, không chỉ đổi setting để xóa warning.

### 7.3. Plugin sử dụng PSI

Trong IntelliJ Platform, các plugin Java có thể dùng PSI (Program Structure Interface) để thao tác với cấu trúc source. Plugin cũ có thể chưa xử lý đúng loại PSI element ứng với ngôn ngữ mới hoặc phụ thuộc API plugin platform đã thay đổi.

Nếu refactoring, inspection hoặc code generator của plugin sinh kết quả sai:

- Ghi IDE build và plugin version.
- Tái hiện trên một file Java tối thiểu.
- Phân biệt lỗi parser core của IDE với lỗi inspection/plugin.
- Cập nhật plugin theo compatibility guide.
- Nếu plugin nội bộ, sửa code xử lý PSI theo AST/type mới.

Không mặc định warning từ một inspection plugin là kết luận của `javac`.

## 8. Eclipse IDE/JDT: compiler compliance khác Installed JRE

Eclipse Java Development Tools (JDT) có Java compiler và mô hình phân tích source riêng (ECJ/JDT). Khi nâng JDK cần xác nhận:

- Eclipse/JDT release hỗ trợ Java language level đích.
- Installed JRE/JDK được cấu hình cho workspace và project.
- **Compiler compliance level** của project.
- Java build path, execution environment và các module dependencies.
- Maven integration (m2e) hoặc Gradle integration (Buildship).
- Plugin dựa vào JDT AST/ECJ và mức hỗ trợ cú pháp của chúng.

Một project có Installed JDK 21 nhưng compiler compliance đặt Java 17 có thể từ chối cú pháp Java 21. Ngược lại, cấu hình compliance cao hơn JDK thực tế có thể không hoạt động như kỳ vọng.

### 8.1. Eclipse build không nhất thiết giống `javac` build

JDT compiler có thể có diagnostics và hành vi incremental build khác `javac` trong một số trường hợp. Điều này không tự chứng minh code là đúng hay sai; cần dùng **compiler chính thức trong build pipeline** để xác định contract phát hành.

Ví dụ một warning xuất hiện ở Eclipse nhưng không có trong Maven:

1. Kiểm tra project compliance và execution environment.
2. Kiểm tra m2e/Buildship đã import đúng Maven/Gradle model chưa.
3. Xác định plugin annotation processor có chạy trong Eclipse hay chỉ trong terminal build.
4. Tái hiện bằng clean build và xem output generated source thực tế.

Với plugin nội bộ dùng `org.eclipse.jdt.core.dom`, cần kiểm tra AST level và API xử lý các node Java mới; không nên tái sử dụng một parser mode quá cũ để phân tích source mới.

## 9. VS Code Java: language server, extension và runtime của project

Trong VS Code, các tính năng Java phổ biến được cung cấp qua Java language server và extensions. Điều cần phân biệt:

- JVM chạy Java language server.
- Danh sách runtime/JDK dùng để import project.
- JDK của Gradle/Maven khi được gọi từ editor.
- Java source level, compiler/release target lấy từ build configuration.
- Extension versions và những công cụ code analysis bổ sung.

Ví dụ cấu hình mang tính minh họa trong `settings.json`:

~~~json
{
  "java.configuration.runtimes": [
    {
      "name": "JavaSE-17",
      "path": "/path/to/jdk-17"
    },
    {
      "name": "JavaSE-21",
      "path": "/path/to/jdk-21",
      "default": true
    }
  ]
}
~~~

Đường dẫn chỉ là placeholder; cần thay bằng nơi cài JDK thực tế trên máy. Cấu hình JVM chạy language server có thể dùng setting riêng theo version extension; đừng suy ra nó chỉ từ `java.configuration.runtimes`.

Nếu editor hiểu syntax nhưng build terminal không, xem Maven/Gradle settings. Nếu terminal build pass nhưng editor không hiểu cú pháp, kiểm tra language server/Java extension release và project import status. Có thể làm mới project import hoặc language-server workspace theo hướng dẫn editor khi môi trường đã được đồng bộ.

Không mặc định xóa toàn bộ workspace cache là bước đầu tiên; cần xác nhận trước rằng phiên bản extension có hỗ trợ cú pháp mới và build model đã được import đúng.

## 10. Apache NetBeans và các IDE khác

Với NetBeans hoặc IDE Java khác, cách xử lý vẫn dựa trên cùng các câu hỏi:

1. IDE release có nhận Java language level đích không?
2. Project đang sử dụng Java platform nào?
3. Source/binary format được đặt ở đâu trong project/build configuration?
4. Maven/Gradle project import có đồng bộ model không?
5. Plugin editor, refactoring hoặc analyzer có parser riêng không?
6. Có dùng compiler/test runner/JDK khác nhau giữa IDE và CI không?

Không nên chuyển toàn bộ team sang IDE khác chỉ vì một plugin báo lỗi khi parser chưa được cập nhật. Phân loại chính xác core IDE, plugin và build compatibility trước khi quyết định.

## 11. Maven: cấu hình compiler release là nguồn tham chiếu rõ ràng

Với Maven, Java language target thường được quản lý qua Maven Compiler Plugin và cấu hình version tương ứng. Ví dụ phần quan trọng trong `pom.xml`:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Hoặc cấu hình plugin:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>APPROVED_PLUGIN_VERSION</version>
      <configuration>
        <release>17</release>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

`APPROVED_PLUGIN_VERSION` là placeholder, không được để nguyên trong build thật. Chọn plugin được nhà cung cấp xác nhận hỗ trợ Maven/JDK đích.

Lệnh kiểm tra môi trường và effective model:

~~~bash
mvn -version
mvn help:effective-pom
mvn -DskipTests=false test
~~~

`mvn -version` cho biết Java runtime Maven thực sự chạy. Nó không tự chứng minh một toolchain cấu hình riêng hoặc test fork sử dụng cùng JDK. Nếu dùng Maven Toolchains Plugin hoặc tính năng fork, cần xác nhận toolchain được chọn trong log.

### 11.1. Mismatch thường gặp

Một developer mở project bằng IDE có SDK 21, nhưng Maven chạy trên JDK 17 và POM cấu hình `release 21`. Compiler có thể báo:

~~~text
error: release version 21 not supported
~~~

Nguyên nhân là compiler đang chạy không nhận target release đó. Sửa language level trong IDE không thay thế việc cấu hình đúng JDK cho compiler.

### 11.2. Multi-module parent POM

Với Maven reactor, parent POM có thể đặt `maven.compiler.release` chung, nhưng một số module cần target khác do public API hoặc downstream consumers. Nếu dùng profile/properties/module overrides, cần ghi rõ trong ma trận module để tránh “một module được nâng vô tình” khi thay parent property.

## 12. Gradle: Java toolchain, compiler target và Gradle JVM

Ví dụ Gradle Groovy DSL để dùng JDK 21 compile source vẫn hỗ trợ Java 17:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Ở đây:

- Java toolchain xác định compiler JDK được dùng cho JavaCompile, tùy Gradle và provisioning configuration.
- `options.release = 17` buộc source/API target Java 17.
- **Gradle daemon JVM** là một thành phần khác; Gradle version phải hỗ trợ JVM chạy daemon.
- IDE có thể cần import lại model để hiểu đúng mức Java.

Lệnh tham khảo:

~~~bash
./gradlew --version
./gradlew :service:compileJava
./gradlew :service:test
~~~

Nếu Gradle quá cũ không chạy được trên JDK mà IDE chọn làm Gradle JVM, lỗi có thể xảy ra **trước khi compiler toolchain được chọn**. Nâng build tool theo compatibility matrix, không mặc định rằng vì JDK 21 được dùng cho toolchain nên Gradle daemon bản cũ cũng chạy trên Java 21.

### 12.1. Runtime của test có thể khác compiler toolchain

Một dự án có thể cần chạy tests trên JDK 17 và JDK 21 để xác minh thư viện còn hỗ trợ cả hai. Trong Gradle, `Test` tasks có thể cấu hình `javaLauncher` phù hợp; trong Maven, cần xem cấu hình test JVM/fork/toolchains của plugin.

Tách bạch:

~~~text
compileJava  -> javac JDK 21, --release 17
testOn17     -> JVM JDK 17
testOn21     -> JVM JDK 21
production   -> min supported runtime từ policy
~~~

Chạy tests chỉ trên Java 21 có thể bỏ sót việc dependency mới được compile cho Java 21 nhưng artifact vẫn hứa hỗ trợ Java 17.

### 12.2. IDE import Gradle project

IDE có thể lấy language level từ Gradle model, nhưng vẫn còn module-specific overrides, generated sources hoặc dự án lai có cấu hình riêng. Khi hai môi trường lệch:

1. Xác nhận Gradle Wrapper version đang dùng.
2. Xác nhận Gradle JVM.
3. Xác nhận Java toolchain và `options.release` của module.
4. Re-import/sync project theo cơ chế IDE.
5. Kiểm tra module language level được import thực tế.
6. Chạy compile task đúng module để xác định source hợp lệ.

Đừng chỉnh thủ công một mục SDK trong IDE rồi quên đồng bộ lại build model, vì lần import sau có thể ghi đè setting đó.

## 13. Multi-module project: mỗi module có thể cần một mức Java khác

Ví dụ:

~~~text
root
 ├─ api-contract      Java 17 minimum
 ├─ shared-model      Java 17 minimum
 ├─ service-runtime   Java 21
 ├─ admin-ui-backend  Java 21
 └─ codegen-tools     JVM chạy generator theo tool support
~~~

`api-contract` và `shared-model` có consumer dùng JDK 17 nên phải giữ source/API/class-file target 17. `service-runtime` chỉ chạy trên Java 21 có thể dùng ngôn ngữ Java 21. `codegen-tools` lại phụ thuộc JDK mà generator và build plugin được hỗ trợ.

Rủi ro:

- Đặt language level chung ở root khiến module public library sinh class-file Java 21.
- Module Java 17 tham chiếu public API dùng kiểu chỉ có ở Java 21.
- Generated source nằm chung source set nhưng generator sinh syntax Java 21.
- IDE nhận một language level cho toàn project và hiển thị sai module.
- Test runner nạp một module build mới trong runtime JDK cũ.

Nên có bảng ràng buộc:

| Module | Source level | `--release`/target | Compiler JDK | Runtime tối thiểu | Consumers |
| --- | --- | --- | --- | --- | --- |
| `api-contract` | 17 | 17 | 21 | 17 | SDK bên ngoài |
| `shared-model` | 17 | 17 | 21 | 17 | Nhiều service |
| `service-runtime` | 21 | 21 | 21 | 21 | Nội bộ |
| `codegen-tools` | Theo tool support | Theo tool support | Theo build | Build-time | CI |

Các giá trị chỉ minh họa; cần dùng policy thật của dự án. Việc “mỗi module một language level” chỉ có ý nghĩa khi dependency graph và runtime support cho phép kết hợp.

## 14. Trình phân tích cú pháp Java trong plugin là thành phần có vòng đời riêng

Nhiều công cụ dùng parser độc lập với compiler chính:

- **IntelliJ PSI**: mô hình source cho inspections, navigation và refactorings của IntelliJ Platform.
- **Eclipse JDT AST/ECJ**: phân tích/công cụ và compiler của hệ Eclipse.
- **JavaParser**: thư viện phân tích cú pháp Java và biểu diễn AST.
- **`javac` compiler tree API**: AST trong phạm vi compiler/tooling.
- **ANTLR grammar**: parser tự xây hoặc sinh từ grammar, cần cập nhật grammar khi cú pháp mới xuất hiện.
- **Tree-sitter grammar**: parser dùng trong một số editor/tooling, có release và mức hỗ trợ riêng.
- **ASM/Byte Buddy/Javassist**: chủ yếu phân tích và thao tác bytecode, không phải parser Java source tương đương.

Các hệ AST không hoàn toàn giống nhau. Một plugin cũ giả định mọi class declaration có một cấu trúc node cụ thể có thể xử lý sai `record` hoặc `sealed class`. Một formatter chưa cập nhật có thể coi pattern switch là token không hợp lệ. Còn bytecode analyzer có thể báo class-file version không nhận.

### 14.1. Kiểm tra parser theo tính năng chứ không chỉ số version

Không có một “parser Java 21” thống nhất cho mọi thư viện. Cần biết version parser thực sự hỗ trợ những phần nào:

- Records.
- Sealed types và permits.
- Switch expressions và pattern matching.
- Text blocks.
- Record patterns.
- Preview syntax nếu dự án bật.
- Javadoc/documentation comments và annotation forms.

Với một plugin nội bộ, test tối thiểu nên chứa từng syntax feature thật sự có trong source code của dự án. Đừng chỉ tạo một file `class Foo {}` và kết luận parser đã hỗ trợ JDK mới.

### 14.2. Parse được chưa đủ để refactor đúng

Một parser có thể tạo AST hợp lệ nhưng plugin refactor vẫn sai nếu:

- Không xử lý một node type mới.
- Không giữ comments/formatting.
- Không resolve symbol đúng.
- Đổi semantic của pattern variables hoặc scope.
- Làm mất annotations/modifiers khi ghi lại source.

Vì vậy, khi nâng parser của plugin, cần test cả **read → transform → output** theo các tình huống có cú pháp mới. Một test “không crash” chưa chứng minh chức năng code transformation chính xác.

## 15. Cú pháp mới và ví dụ lỗi parser không phải lỗi compiler

Xét Java 17:

~~~java
public sealed interface Payment
        permits CardPayment, CashPayment {
}

public record CardPayment(String token) implements Payment {
}

public record CashPayment(long amount) implements Payment {
}
~~~

Một analyzer cũ có thể báo:

~~~text
Unexpected token "sealed"
Unexpected token "record"
Could not parse Java source
~~~

Nếu compiler JDK 17+ với `--release 17` chấp nhận source này, lỗi có thể nằm ở analyzer/parser version. Chọn hướng giải quyết:

1. Xác định tool nào đưa ra diagnostic (IDE core, plugin, Checkstyle, PMD, formatter, compiler).
2. Xác nhận source level/release đích hợp lệ.
3. Kiểm tra tool version và compatibility matrix.
4. Nâng tool/parser hoặc dùng bản có hỗ trợ cú pháp tương ứng.
5. Kiểm chứng lại behavior của tool, không chỉ việc nó ngừng báo lỗi.

Không nên vô hiệu hóa toàn bộ kiểm tra chất lượng chỉ để build pass khi một parser cụ thể chưa cập nhật. Có thể tạm giới hạn scope hoặc ghi waiver có hạn, nhưng phải có owner và kế hoạch khắc phục.

## 16. Static analysis: mỗi công cụ có mô hình phân tích và giới hạn riêng

Trong một dự án Java, có thể có nhiều lớp kiểm tra:

| Công cụ/nhóm | Phạm vi điển hình | Điểm cần kiểm tra khi nâng JDK |
| --- | --- | --- |
| Checkstyle | Quy tắc style trên source Java | Parser có hiểu syntax mới; cấu hình rules tương thích |
| PMD | Source analysis và rules | Java language version/parser/ruleset |
| SpotBugs | Phân tích bytecode | Class-file version và dependencies parser |
| Error Prone | Phân tích trong compiler/Javac integration | Compiler JDK và plugin/tool version |
| Sonar analyzers | Source, bytecode và quality rules tùy analyzer | Scanner, analyzer và Java language support |
| Formatter | Viết lại format source | Cú pháp mới và tính ổn định của output |
| IDE inspection | Source semantics trong IDE | IDE/parser/plugin phiên bản tương thích |

Không phải cùng một lỗi parser đều có cách sửa giống nhau. Checkstyle/PMD có thể cần tăng version hoặc cấu hình language version, trong khi SpotBugs có thể thất bại khi đọc `.class` vì version bytecode. Error Prone có thể phụ thuộc mạnh vào `javac` APIs của compiler JDK.

### 16.1. Không chỉ sửa cấu hình `languageVersion`

Nếu một parser release cũ chưa có grammar cho pattern switch, đặt cấu hình “Java 21” có thể không giúp gì. Tool đó cần một phiên bản được phát hành có implementation hỗ trợ. Ngược lại, tool đã hỗ trợ syntax nhưng project vẫn cấu hình mode Java 8 cũng có thể từ chối code hợp lệ.

Luồng điều tra đúng là **tool version → parser capabilities → language-level setting → test source**.

### 16.2. Quality gate có thể không chạy dù build xanh

Trong migration, một nhóm có thể bỏ qua Checkstyle hoặc PMD vì parser crash, rồi chỉ chạy `compileJava` để báo hoàn thành. Điều này làm chất lượng kiểm tra giảm ngầm.

Hãy ghi rõ những task chất lượng phải hoạt động trong CI, ví dụ:

~~~text
compile
unit tests
integration tests
checkstyle / PMD
SpotBugs / bytecode analysis
formatter verification
generated-code validation
~~~

Khi cần tạm ngưng một tool, ghi rõ rủi ro và mốc bật lại; không coi compile pass là tương đương “mọi quality gate đã pass”.

## 17. Formatter và codemod: parser sai có thể làm thay đổi hàng loạt source

Các formatter/codemod thường **ghi lại source**, không chỉ phân tích. Vì vậy rủi ro có thể lớn hơn một warning:

- Formatter cũ không hiểu syntax mới và từ chối file.
- Plugin ghi lại AST rồi làm mất comment hoặc modifier.
- Refactoring tool thay đổi import, pattern variable scope hoặc generic type.
- OpenRewrite/codemod recipe không phù hợp phiên bản library/framework.
- Hai tool format khác nhau tạo diff qua lại trong CI.

### 17.1. Cấu hình reproducible

Nên:

1. Cố định formatter/recipe version trong build.
2. Không dựa vào plugin IDE riêng của một developer làm nguồn format duy nhất.
3. Tách commit “nâng formatter” khỏi commit “đổi logic” khi khả thi.
4. Chạy formatter trên source mẫu có syntax mới, rồi review diff.
5. Đặt kiểm tra format trong CI theo đúng tool/version được duyệt.

Không nên tự động chạy “format all” trên toàn repository ngay sau khi nâng IDE nếu chưa xác định plugin mới có thay đổi quy tắc output. Hàng chục nghìn dòng diff format sẽ khiến regression khó được nhận diện.

### 17.2. Plugin dùng `javac` internals

Một số formatter hoặc compiler plugin truy cập API compiler bên trong JDK. Việc đổi JDK có thể gây `IllegalAccessError` hoặc `NoSuchFieldError` ngay cả khi Java syntax không đổi. Đây là vấn đề **tool/JDK API compatibility**, không đơn thuần là parser language level.

Không nên xem `--add-exports` hoặc `--add-opens` là cách thay thế bền vững cho việc nâng tool. Nếu phải dùng workaround tạm, cần theo dõi loại API nội bộ và ngày loại bỏ.

## 18. Annotation processors và mã sinh trong compiler

Trong chủ đề “Sinh mã và công cụ test”, một nhóm quan trọng là annotation processors như Lombok, MapStruct, Dagger, AutoValue và công cụ nội bộ.

### 18.1. Processor không giống IDE plugin

Annotation processor thường chạy trong build/compiler hoặc một pipeline processing tương ứng. IDE có thể hỗ trợ annotation processing hoặc dùng plugin để hiển thị code sinh theo cách riêng.

Do đó có thể xảy ra:

- IDE hiểu field/getter do Lombok cung cấp nhưng Maven compile fail.
- Maven compile pass vì processor được cấu hình, IDE lại báo thiếu method do chưa bật/import annotation processing.
- Processor cũ lỗi trên `javac` mới vì phụ thuộc `com.sun.tools.javac.*`.
- Generated source compile được nhưng runtime dependency của generated API bị thiếu.

### 18.2. Ví dụ MapStruct

Mã nguồn:

~~~java
@Mapper
public interface OrderMapper {
    OrderDto toDto(OrderEntity entity);
}
~~~

Processor có thể sinh `OrderMapperImpl` tại build time. Nếu IDE chưa chạy/cập nhật annotation processing model, nó có thể không thấy implementation hoặc generated sources. Nếu `javac` 21 chạy processor quá cũ, lỗi có thể nằm trong processor chứ không phải interface ở trên.

Khi kiểm kê cần ghi riêng:

- Processor artifact và version.
- Annotation API/runtime artifact và version (nếu có).
- Compiler JDK.
- Build tool integration.
- Generated output directory.
- IDE annotation processing setup.
- Consumers của generated code.

Không sửa trực tiếp `OrderMapperImpl.java` để vượt lỗi, vì processor sẽ ghi đè ở lần build sau.

## 19. OpenAPI, JAXB và Protocol Buffers có thể sinh code vượt language level

Các generator từ contract có tool/version và options riêng. Một pipeline có thể sinh Java classes hợp lệ ở Java 21, trong khi module public SDK vẫn yêu cầu Java 17.

Ví dụ mã do template mới sinh:

~~~java
// Template lựa chọn record; cần Java 16+.
public record OrderDto(String id, long totalCents) {
}
~~~

Nếu SDK còn hỗ trợ Java 11, output này không phù hợp. Lỗi nằm ở quyết định chọn generator/template/model style và target Java, không phải “IDE parser cũ”.

### 19.1. OpenAPI

Kiểm tra:

- Generator/version và library template.
- Generated Java syntax và imports.
- `javax`/`jakarta` annotation family.
- JSON library và nullability/date mapping.
- Java class/method names của SDK.

### 19.2. JAXB/XJC

Kiểm tra:

- XJC/plugin version và binding customizations.
- JAXB API/runtime thế hệ `javax.xml.bind` hay `jakarta.xml.bind`.
- Generated annotations và reflection/module access.
- XML schema/namespace compatibility.

### 19.3. Protocol Buffers/gRPC

Kiểm tra:

- `protoc` version và Java code generator.
- `protobuf-java` runtime và gRPC plugin/runtime nếu có.
- Generated classes dùng APIs có mặt trên Java runtime tối thiểu.
- Java package/class layout cùng wire schema compatibility.

Việc generated source đổi API Java không nhất thiết làm wire format đổi, và ngược lại. Phải kiểm thử cả hai chiều theo yêu cầu sản phẩm.

### 19.4. Nguyên tắc với thư mục generated

Không nên sửa bằng tay những file dưới `build/generated` hoặc `target/generated-sources`. Hãy thay schema, generator options, template hoặc JDK target rồi regenerate từ sạch. Nếu cần logic tùy chỉnh, đặt adapter/hook ở source viết tay.

## 20. Preview features: một chiều tương thích đặc biệt

Một số tính năng ngôn ngữ được cung cấp ở trạng thái **preview** trong một Java release trước khi trở thành chuẩn hoặc bị thay đổi. Preview không phải lời hứa tính năng sẽ giữ nguyên cú pháp/API ở mọi release tiếp theo.

Khi dùng preview feature:

- Compiler phải là phiên bản JDK phù hợp với preview đó.
- Build phải bật preview và chọn source/release tương ứng theo quy tắc compiler.
- Test/runtime cần bật preview khi chạy bytecode yêu cầu điều đó.
- IDE/parser/plugin phải có khả năng hiểu cú pháp preview ở release đang dùng.
- CI và runtime production phải có cấu hình nhất quán.

Ví dụ trên JDK có preview feature dành cho chính release đó:

~~~bash
javac --enable-preview --release 21 -d out Example.java
java --enable-preview -cp out Example
~~~

Lệnh chỉ minh họa cơ chế bật preview cho **tính năng preview của Java 21**; không phải mọi cú pháp Java 21 đều yêu cầu preview. Ví dụ pattern matching cho `switch` được chuẩn hóa trong Java 21 nên không cần bật preview chỉ để dùng tính năng chuẩn đó.

### 20.1. Không “nâng language level preview” để né lỗi không liên quan

Nếu parser Checkstyle cũ chưa hiểu record đã là tính năng chuẩn, bật preview không sửa được thiếu hụt implementation parser. Nếu dependency bytecode parser không hiểu class-file major mới, bật preview trong IDE cũng không giúp.

Một cơ chế preview là một quyết định sản phẩm có rủi ro version lock và được theo dõi riêng; không dùng nó như nút “enable mọi cú pháp”.

### 20.2. Tính năng đã thành chuẩn có thể cần cập nhật cả IDE

Khi một tính năng đi từ preview đến final, cú pháp/ngữ nghĩa có thể khác giữa hai release. Plugin từng hỗ trợ một preview version chưa chắc đúng với cú pháp cuối cùng. Cần xác định **phiên bản cụ thể của tính năng** chứ không chỉ nói “plugin hỗ trợ pattern switch”.

## 21. Lỗi parser và lỗi bytecode version: hai họ lỗi khác nhau

### 21.1. Lỗi source parser

Ví dụ:

~~~text
Unexpected token: record
Parse error at "case String s ->"
Java language level 11 does not support sealed types
~~~

Những lỗi này thường hướng tới source language level hoặc parser chưa được cập nhật. Cần xác định tool tạo thông báo trước khi sửa source.

### 21.2. Lỗi bytecode reader

Ví dụ:

~~~text
Unsupported class file major version 65
~~~

Class-file major version 65 tương ứng Java 21. Nếu xuất hiện trong ASM, JaCoCo, mock framework hoặc plugin, có thể tool/embedded bytecode parser chưa hỗ trợ dạng class file mới.

| Java release | Class-file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 22 | 66 |

Khi lỗi đến từ **JVM runtime** nạp class mới hơn khả năng hỗ trợ, có thể là `UnsupportedClassVersionError`. Nếu lỗi đến từ **thư viện parse bytecode**, thường là exception riêng của thư viện. Hướng sửa khác nhau:

- Runtime JVM thấp hơn class-file target → chọn runtime phù hợp hoặc compile bằng `--release` thấp hơn.
- Parser ASM/Byte Buddy/coverage cũ → nâng tool/library theo compatibility matrix.
- JAR bắc cầu vượt Java tối thiểu → xem lại dependency version và artifact release target.

Đừng chỉ đổi “Project SDK” trong IDE để né một lỗi phát sinh từ bytecode parser của agent đang chạy trong test JVM.

## 22. Test runner, mocking và coverage cũng là công cụ phân tích Java

Một migration có thể compile source thành công nhưng thất bại ở `test`:

- JUnit engine/plugin không được khởi động hoặc không discover đủ tests.
- Mockito/Byte Buddy instrumentation không hỗ trợ class-file version/JDK behavior.
- Coverage agent/JaCoCo không thể phân tích class file mới.
- Test framework dùng reflection sâu gặp access restrictions.
- IDE test runner dùng JVM khác với Maven/Gradle runner.
- Preview bytecode được compile nhưng test JVM chưa bật preview.

### 22.1. Phân biệt test-only blocker và production blocker

Một lỗi xảy ra trong Mockito/coverage của unit test không tự chứng minh runtime production không tương thích. Nhưng test infrastructure không hoạt động nghĩa là nhóm chưa có bằng chứng chất lượng để phát hành. Hãy phân loại:

| Loại | Phạm vi | Cách xử lý |
| --- | --- | --- |
| Build blocker | Không compile được | Xác định compiler/toolchain/processor |
| Test tooling blocker | Test runner/agent/analyzer lỗi | Nâng đúng test dependency/tool |
| Runtime blocker | App không start/nạp dependency | Kiểm tra JDK/module/runtime path |
| Behavioral regression | App chạy nhưng kết quả sai | Kiểm thử hợp đồng và changes ngoài compiler |

Không tắt toàn bộ unit tests chỉ để hoàn thành migration. Nếu một test runner cần nâng, xử lý nó như một dependency trong kế hoạch cutover.

### 22.2. IDE test runtime không phải luôn là CI test runtime

Ví dụ IDE dùng JDK 21 để chạy JUnit, nhưng Gradle task test được cấu hình chạy trên JDK 17. Những test tải class Java 21 có thể pass trong IDE và fail trong CI. Cần so sánh test JVM, classpath và build output được thực thi, không chỉ đọc kết quả màu xanh trong một IDE.

## 23. Cách phân loại lỗi trước khi thay cấu hình

| Triệu chứng | Nơi cần kiểm tra trước | Không nên làm ngay |
| --- | --- | --- |
| IDE gạch đỏ, terminal `javac` pass | IDE/module language level, parser, plugin, sync | Sửa code hợp lệ theo parser cũ |
| IDE xanh, CI `release version not supported` | Compiler JDK thật và `--release` | Chỉ tăng IDE Project SDK |
| Checkstyle báo syntax error ở `record` | Checkstyle version/parser settings | Tắt toàn bộ rules |
| Formatter crash khi gặp pattern switch | Formatter/parser version | Format lại toàn repo bằng tool khác |
| `Unsupported class file major version 65` | JVM hoặc ASM/Byte Buddy/agent nào báo | Đổi ngẫu nhiên source compatibility |
| Lombok lỗi `javac` internals | Lombok/processor version và compiler JDK | Sửa generated getters bằng tay |
| IDE không thấy `MapperImpl` | Annotation processing model/output | Commit một implementation tạm |
| Gradle không khởi động trên JDK mới | Gradle Wrapper/daemon JVM support | Chỉ đặt toolchain = JDK mới |
| Runtime `NoClassDefFoundError` | Resolved runtime dependency/module | Chỉ xóa IDE caches |
| OpenAPI generated imports sai | Generator template/options/runtime APIs | Tìm-thay trong thư mục generated |
| Protobuf generated code gọi method runtime thiếu | `protoc`/`protobuf-java` version alignment | Thêm JAR tùy ý để dập lỗi |
| JUnit pass ở IDE, fail ở CI | JDK chạy tests, classpath, agent | Kết luận code khác do IDE |

Đây là gợi ý phân loại ban đầu, không thay stack trace và môi trường thực tế. Một exception có thể phát sinh ở nhiều tầng; cần xác nhận **tool đầu tiên thất bại**.

## 24. Bộ lệnh điều tra tối thiểu

Một nhóm có thể ghi lại đầu ra của các lệnh dưới đây trong môi trường thực tế khi migration:

~~~bash
java -version
javac -version
./gradlew --version
mvn -version
~~~

Với Gradle:

~~~bash
./gradlew :module:compileJava
./gradlew :module:test
./gradlew :module:dependencies --configuration testRuntimeClasspath
~~~

Với Maven:

~~~bash
mvn help:effective-pom
mvn test
mvn dependency:tree
~~~

Với bytecode:

~~~bash
javap -verbose -classpath build/classes/java/main \
    com.example.Main
~~~

Đọc dòng `major version: ...` để biết class-file level. Trên Windows, đường dẫn và separator của classpath khác so với ví dụ shell kiểu Unix; hãy áp dụng đúng shell/JDK đang dùng.

### 24.1. Mục tiêu khi lưu bằng chứng

Ghi kèm:

- Commit/hash của source và build configuration.
- JDK distribution/version thật.
- IDE release và plugin versions.
- Build tool, compiler, parser/analyzer/formatter versions.
- Source/release target của module.
- Command và exit code.
- File/source construct gây lỗi.
- Stack trace đầu tiên, không chỉ summary.

Với dependency bắc cầu, tìm version đã resolve thực tế bằng `dependencyInsight` (Gradle) hoặc `dependency:tree` (Maven). Không lấy con số khai báo trong build file làm bằng chứng duy nhất.

## 25. Một ví dụ điều tra: IDE không nhận cú pháp Java 21

Tình huống giả định:

~~~text
Module:     search-service
Source:     pattern matching for switch
Gradle:     Java toolchain 21, --release 21
CLI build:  success
IDE:        parser error ở case String s
~~~

Các bước:

1. Dùng compiler task của module xác nhận source Java 21 được chấp nhận.
2. Xem IDE project/module language level đang là bao nhiêu.
3. Nếu mức đã là 21, xác định thông báo từ IDE core hay một plugin inspection.
4. Kiểm tra IDE build và plugin version có hỗ trợ cú pháp Java 21 cuối cùng hay không.
5. Sync/reimport Gradle project model nếu cấu hình IDE bị lệch.
6. Tái hiện bằng một source file ngắn có pattern switch để tách plugin khỏi code nghiệp vụ.
7. Sau khi cập nhật IDE/plugin, kiểm tra lại chức năng navigation, refactoring và formatter trên file đó.

Không nên đổi code Java 21 hợp lệ về chuỗi `if-else` chỉ để chiều lòng parser cũ nếu sản phẩm đã chính thức chấp nhận Java 21. Nhưng nếu module thật sự phải hỗ trợ Java 17, chính compiler release target mới quyết định hướng sửa source.

## 26. Ví dụ điều tra: generated source vượt quá Java release target

Tình huống:

~~~text
Module:         client-sdk
Minimum Java:   11
Compiler JDK:   21
--release:      11
Code generator: template mới dùng record
Build result:   compilation error
~~~

Generated file:

~~~java
public record ApiResponse(String code, String message) {
}
~~~

Đây không phải vấn đề IDE “chưa hiểu record”: compiler đã đúng khi từ chối một syntax không thuộc Java 11. Khâu cần sửa là source generator/template hoặc chính sách Java tối thiểu của SDK.

Các lựa chọn:

- Chọn generator/template tạo POJO phù hợp Java 11.
- Sử dụng một generator version đã được kiểm chứng với Java 11.
- Nếu chủ động nâng SDK minimum runtime lên Java 17/21, công bố breaking support change và thử trên consumers.

Không sửa generated Java sau mỗi build; phải làm cho pipeline sinh code đúng contract từ đầu.

### 26.1. Nếu compiler pass nhưng runtime cũ vẫn lỗi

Kiểm tra generated code có tham chiếu runtime library được compile cho Java cao hơn hay không. `--release 11` không tự đảm bảo JAR của các thư viện bên ngoài chỉ dùng Java 11. Có thể cần đổi runtime library version hoặc tăng minimum runtime có chủ đích.

## 27. Ví dụ điều tra: formatter hoặc static analyzer bị lỗi sau nâng JDK

Một dịch vụ dùng records và sealed classes, JDK 17 compile bình thường, nhưng `checkstyleMain` báo:

~~~text
ParseException: unexpected token "record"
~~~

Phương pháp xử lý:

1. Xác định Checkstyle bản nào được plugin/build resolved.
2. Đối chiếu release notes về hỗ trợ Java 17 syntax.
3. Kiểm tra plugin Gradle/Maven có dùng đúng version analyzer mong đợi không.
4. Nâng analyzer và plugin integration nếu cần, giữ ruleset rõ.
5. Chạy lại analyzer với cả files mới và files cũ.
6. Review những rule results thay đổi ngoài cú pháp để tránh âm thầm hạ chất lượng.

Nếu sau khi nâng analyzer, số lượng violations thay đổi vì rule behavior, cần tách “tool/parser được cập nhật” khỏi “coding standard đổi” để đánh giá rõ. Không nên coi mọi cảnh báo mới là lỗi JDK.

## 28. Ví dụ điều tra: plugin test không hiểu class-file version

Tình huống:

~~~text
compileJava: success
test:        fails before tests execute
message:     Unsupported class file major version 65
stack:       coverage/mocking/bytecode library
~~~

Vì Java 21 tạo class-file major 65 nếu target là 21, một bytecode parser cũ của coverage hoặc mocking tool có thể không hiểu. Cần:

1. Xác nhận class file offending có major version nào qua `javap -verbose`.
2. Xác định tool đầu tiên parse class đó (ASM, agent, Byte Buddy, framework).
3. Đối chiếu version được vendor hỗ trợ.
4. Nâng test dependency/agent phù hợp, không override một transitive engine vượt support matrix tùy tiện.
5. Chạy lại discovery, tests, coverage và integration.

Nếu stack trace là `UnsupportedClassVersionError` do JVM JDK 17 cố tải class-file 65, cách xử lý là dùng runtime JDK 21 hoặc build artifact cho Java 17 nếu đúng hợp đồng. Cùng cụm từ “class-file version” nhưng nguyên nhân thuộc tầng khác nhau.

## 29. Workspace settings không phải nguồn chân lý duy nhất

Một repository có thể có:

~~~text
.idea/
.settings/
.classpath
.project
.vscode/settings.json
build.gradle / build.gradle.kts
pom.xml
gradle.properties
gradle/wrapper/...
.mvn/wrapper/...
CI pipeline configuration
Dockerfile
~~~

Các file này có mục đích và phạm vi khác nhau; một số chứa setting cá nhân của developer, số khác là cấu hình build chung.

Nguyên tắc:

- **Build files và toolchains** nên mô tả contract compilation chính thức.
- **IDE settings** nên giúp developer import và phân tích đúng contract đó.
- **CI** phải dùng toolchain versions có thể tái lập.
- **Runtime image** phải phản ánh production Java support policy.
- **Generated source directories** phải được quản lý rõ bởi build, không phụ thuộc trạng thái cache của IDE.

Không nên commit đường dẫn JDK tuyệt đối trên máy cá nhân vào cấu hình team. Thay bằng cơ chế toolchain, environment variables hoặc cấu hình IDE portable khi có thể.

### 29.1. Chú ý IDE caches

Cache/index bị lỗi có thể tạo cảnh báo giả. Tuy nhiên, dọn cache chỉ nên thực hiện **sau khi** đã xác nhận project SDK, module language level, parser/plugin support và build import. Nếu plugin thực sự không hỗ trợ Java 21, xóa cache một trăm lần vẫn không bổ sung grammar cho parser.

## 30. Thực hành thiết kế ma trận hỗ trợ

Một ma trận nên phân tách **syntax support**, **compiler support** và **runtime/test support**:

| Thành phần | Đang dùng | Mục tiêu | Bằng chứng cần có |
| --- | --- | --- | --- |
| IDE core | Version hiện tại | Release hỗ trợ Java syntax đích | Source insight/inspection thử với features thật |
| IDE plugin | Plugin version cũ | Version hỗ trợ IDE/JDK | Plugin compatibility notes và test |
| Parser library | JavaParser/JDT/ANTLR/khác | Version parse được syntax dùng | Parser fixtures, transformation tests |
| Gradle/Maven | Wrapper hiện tại | Version chạy được build JVM | Official compatibility matrix, clean build |
| Java compiler | JDK hiện tại | Toolchain mục tiêu | Compile với `--release` đúng |
| Annotation processor | Lombok/MapStruct/custom | Version hỗ trợ compiler | Generated code compile + behavior |
| Formatter/static analyzer | Tool version hiện tại | Parser/rules hỗ trợ language level | Quality tasks chạy đầy đủ |
| Test tooling | JUnit/Mockito/coverage | Version hỗ trợ class file | Test discovery, execution, coverage |
| Runtime dependencies | Application/SDK libs | Version phù hợp Java minimum | Runtime smoke/integration |
| Production JVM | Image hiện tại | JDK runtime được duyệt | Deploy và startup tests |

Không điền “SUPPORTED” khi chỉ thấy thư viện không báo lỗi trong một unit test. Phân biệt:

- **Vendor-supported:** tài liệu công bố hỗ trợ tổ hợp.
- **Observed working:** đã chạy qua một bộ test xác định.
- **Untested:** chưa có bằng chứng.
- **Known incompatible:** có giới hạn/issue hoặc failure tái hiện.

Với mỗi ô rủi ro, ghi owner, kế hoạch nâng cấp và mức ưu tiên. Mục tiêu là tạo một tổ hợp phiên bản hỗ trợ nhau, không phải nâng đồng loạt mọi plugin lên newest.

## 31. Phương pháp nâng cấp tuần tự

### Giai đoạn 1: Khóa baseline

Ghi JDK, build tool, IDE, plugin versions, parser libraries, source/release targets và các test/quality tasks hiện có. Lưu một source fixture nhỏ chứa những cú pháp dự án thực sự sử dụng.

### Giai đoạn 2: Cập nhật toolchain/build

Chọn Gradle/Maven version có thể chạy trên build JVM đích. Kiểm tra compiler toolchain, `--release` và test JVM. Đừng đồng thời đổi source syntax và framework major nếu có thể tránh.

### Giai đoạn 3: Cập nhật IDE và parser ecosystem

Chọn IDE release và plugin versions phù hợp language level. Nâng source analyzers, formatter, compiler extensions và annotation processors theo compatibility matrix.

### Giai đoạn 4: Sinh lại mã từ sạch

Nếu dùng OpenAPI/JAXB/Protobuf hoặc annotation processing, xóa sự lệ thuộc vào generated source cũ bằng một clean generation pipeline. Review generated API/behavior differences; không sửa file generated bằng tay.

### Giai đoạn 5: Kiểm thử nhiều tầng

Chạy compile, unit, integration, static analysis, formatting, coverage, runtime smoke, cùng tests trên Java tối thiểu được hỗ trợ. Kiểm tra riêng source API, bytecode compatibility và behavior.

### Giai đoạn 6: Triển khai và theo dõi

Đảm bảo container/runtime/JVM flags/agents đúng với môi trường đã test. Theo dõi startup, exceptions, coverage, latency và các chỉ số nghiệp vụ liên quan. Có phương án rollback hoặc roll-forward nếu generated API/data format đã thay đổi không thể đảo ngược bằng cách chỉ đổi runtime.

## 32. Checklist để tránh nhầm lẫn “IDE xanh” và “build sẵn sàng”

- [ ] Đã xác định JDK chạy IDE/language server riêng với Project SDK.
- [ ] Đã ghi đúng language level của từng module.
- [ ] Đã xác định compiler JDK, `--release` và runtime tối thiểu.
- [ ] Gradle/Maven wrapper hỗ trợ build JVM dự kiến.
- [ ] IDE import Maven/Gradle model đúng; không chỉ cấu hình SDK thủ công.
- [ ] IDE core/parser hỗ trợ đúng cú pháp Java đang dùng.
- [ ] Plugin IDE nội bộ và bên ngoài hỗ trợ AST/PSI/JDT API tương ứng.
- [ ] Checkstyle/PMD/formatter/other source analyzers parse được syntax mới.
- [ ] SpotBugs/ASM/Byte Buddy/coverage hiểu class-file version sinh ra.
- [ ] Annotation processors tương thích compiler mới, không phụ thuộc internal APIs đã đổi.
- [ ] Generated source được sinh từ schema/tool/template version được cố định.
- [ ] Generated code không vượt language level của module.
- [ ] Runtime libraries của generated code phù hợp JDK/framework mục tiêu.
- [ ] Preview features (nếu dùng) được bật nhất quán ở compiler, IDE và test/runtime.
- [ ] Không bỏ qua unit tests hoặc quality tasks chỉ để cho build xanh.
- [ ] Có test chạy trên Java runtime tối thiểu nếu sản phẩm hỗ trợ nhiều JDK.
- [ ] Không chỉnh sửa file generated bằng tay để che lỗi toolchain.
- [ ] Đã xác nhận class-file major version của artifact quan trọng.
- [ ] Có integration test trên runtime image và agents của production.
- [ ] Release notes ghi rõ thay đổi yêu cầu Java tối thiểu hoặc generated public APIs.

Checklist này là công cụ lập kế hoạch migration, không thay thế việc kiểm tra compatibility của từng công cụ ở phiên bản cụ thể.

## 33. Những ngộ nhận thường gặp

**“Đã cài JDK 21 nên IDE tự hiểu mọi cú pháp Java 21.”** Sai. IDE parser, language server và plugin cần version hỗ trợ, đồng thời module phải đặt language level đúng.

**“IDE báo đỏ là `javac` chắc chắn sẽ lỗi.”** Sai. Diagnostic có thể đến từ plugin parser hoặc IDE model đang cũ. Cần chạy compiler chính thức với cấu hình đích.

**“IDE xanh nghĩa là artifact dùng được trên Java 17.”** Sai. Cần `--release`/bytecode/API compatibility và test runtime Java 17 nếu đó là mức hỗ trợ.

**“Gradle toolchain = 21 nghĩa là Gradle daemon cũng chạy được trên Java 21.”** Sai. Toolchain và JVM chạy Gradle là hai cơ chế khác nhau; phải xem Gradle Java compatibility matrix.

**“Nâng compiler là tự nâng Checkstyle/formatter/parser.”** Sai. Các công cụ có release và parser riêng.

**“Cấu hình parser ở Java 21 sẽ khiến bản plugin cũ hiểu toàn bộ cú pháp mới.”** Không đúng nếu implementation parser chưa có grammar cho cú pháp đó.

**“Class-file major error luôn là do `javac`.”** Không đúng. Có thể là JVM quá cũ hoặc bytecode analyzer/agent chưa hỗ trợ.

**“Chỉ cần thêm `--enable-preview` để mọi cú pháp mới hoạt động.”** Sai. Preview phụ thuộc release cụ thể; nhiều tính năng đã chuẩn hóa và không cần preview, còn parser cũ vẫn phải nâng.

**“Generated code compile lỗi thì sửa thẳng generated file.”** Sai trong pipeline tái sinh mã. Cần sửa schema, options, templates hoặc runtime/tool versions.

**“Đổi IDE plugin không ảnh hưởng kết quả refactoring.”** Không bảo đảm. Plugin có thể xử lý AST khác và ghi lại source sai; cần test transformation.

**“Chỉ cần unit test pass, không cần chạy Checkstyle, PMD hoặc coverage.”** Sai nếu đó là quality gates của dự án. Migration phải giữ hoặc chủ động thay đổi policy được duyệt.

**“Nếu một module Java 21 chạy tốt, mọi thư viện trong repository cũng có thể phát hành cho Java 17.”** Sai. Mỗi artifact có bytecode, API dependencies và minimum runtime riêng.

## 34. Tài liệu kỹ thuật nên đối chiếu

Khi triển khai thực tế, nên đọc tài liệu theo đúng release, không suy luận từ phiên bản khác:

- **Java Language Specification (JLS):** grammar và semantics của từng ngôn ngữ Java release.
- **`javac` Tool Guide:** `--release`, `--enable-preview`, source/target options và toolchain compiler.
- **Java Virtual Machine Specification:** class-file format và version support.
- **Gradle Java Compatibility Matrix và Toolchains documentation:** JVM chạy Gradle khác compiler toolchain.
- **Maven Compiler Plugin và Maven Toolchains documentation:** release target, plugin version và compiler JDK.
- **IntelliJ IDEA Java support/SDK/language level documentation:** project/module SDK, Gradle/Maven import, plugin compatibility.
- **Eclipse JDT/ECJ và Buildship/m2e documentation:** compiler compliance, Installed JRE và AST support.
- **VS Code Java Extension documentation:** Java runtimes, language server và project configuration.
- **Checkstyle, PMD, SpotBugs, Error Prone, formatter release notes:** mức parser/bytecode/compiler hỗ trợ.
- **OpenAPI Generator, JAXB/XJC, Protocol Buffers/gRPC Java documentation:** generator, generated sources và runtime version compatibility.
- **JUnit, Mockito/Byte Buddy, JaCoCo documentation:** test runner, instrumentation và class-file support.

Với các công cụ thay đổi nhanh, nên lấy **số phiên bản và ma trận hỗ trợ thực tế** từ tài liệu nhà cung cấp ở thời điểm nâng cấp; không ghi một phiên bản duy nhất như lựa chọn đúng cho mọi dự án.

## 35. Kết luận

Plugin IDE, parser và language level là một phần thiết yếu của Java compatibility migration. Một file Java được phân tích bởi nhiều hệ công cụ khác nhau trước khi chạy: IDE parser, plugin inspection/refactoring, compiler, annotation processor, formatter, bytecode analyzer, test agent và cuối cùng là JVM. Mỗi lớp có version và hợp đồng hỗ trợ riêng; vì vậy “IDE đỏ nhưng build xanh” hoặc “IDE xanh nhưng CI đỏ” đều có thể xảy ra mà không mâu thuẫn.

Để xử lý đúng, hãy **tách JDK chạy IDE, project SDK, module language level, compiler toolchain, `--release` và test/runtime JVM**. Kiểm kê plugin/parser versions, đồng bộ project model với Maven/Gradle, cố định generator và runtime dependencies, rồi dùng các ví dụ cú pháp thật cùng clean build và contract tests để xác nhận. Khi gặp lỗi, xác định tool đầu tiên thất bại trước khi đổi code hoặc tăng version ngẫu nhiên.

Một đợt migration thành công không chỉ giúp source compile trên JDK mới. Nó còn đảm bảo IDE hiểu đúng mã nguồn, plugin có thể phân tích/refactor an toàn, generated code không vượt Java minimum, quality gates và test infrastructure tiếp tục hoạt động, và artifact cuối cùng chạy đúng trên runtime đã được sản phẩm cam kết hỗ trợ.
