# IDE hỗ trợ pattern matching trong Java 21

## 1. Tổng quan

IntelliJ IDEA, Eclipse IDE (JDT), Visual Studio Code kèm Java extensions và Apache NetBeans đều có thể hỗ trợ lập trình với **pattern matching** trong Java. Tuy nhiên, tính năng hoạt động đúng không chỉ phụ thuộc tên IDE: cần kiểm tra **phiên bản IDE/plugin**, **JDK của project**, **language/source level**, **JDK của Maven/Gradle** và **JVM chạy ứng dụng**.

Pattern matching cho phép kiểm tra và gắn biến trong một biểu thức:

```java
if (input instanceof String text) {
    System.out.println(text.strip());
}
```

Trong Java 21, cùng tư tưởng có thể áp dụng với `switch` và record patterns:

```java
return switch (input) {
    case String text when text.isBlank() -> "blank";
    case String text -> "text:" + text.strip();
    case Point(var x, var y) -> "point:" + x + "," + y;
    case null -> "null";
    default -> "other";
};
```

Đoạn code thứ hai là một **mảnh code minh họa** trong phương thức trả `String`, với `Point` đã được khai báo. Nó cần **Java 21** vì có record pattern và pattern matching cho switch; dù IDE tô màu cú pháp, compiler cấu hình ở Java 17 vẫn từ chối.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định **IDE và extension** có hiểu type/record patterns, `when`, `switch` expression không.
2. Cấu hình Java 21 cho **IntelliJ IDEA, Eclipse JDT, VS Code/Red Hat Java extension và NetBeans**.
3. Phân biệt **IDE runtime**, **language server runtime**, **Project SDK/JDK**, **compiler release** và **Run/Test JDK**.
4. Chạy chương trình Java 21 độc lập từ IDE và terminal, đối chiếu kết quả.
5. Dùng code actions, refactoring, inspections, debugger mà không vô ý thay đổi semantics.
6. Chẩn đoán lỗi source level, preview syntax, dominance, flow scoping, exhaustiveness và null.
7. Đồng bộ cấu hình Maven/Gradle/CI để cả nhóm biên dịch giống nhau.

## 2. Tính năng pattern matching thuộc phiên bản Java nào?

| Cấu trúc | Phiên bản chuẩn | Ví dụ | Dễ nhầm với |
| --- | --- | --- | --- |
| `switch` expression | Java 14 | `return switch(n) { case 0 -> "zero"; default -> "other"; };` | Dấu `->` không nhất thiết là pattern matching |
| `instanceof` type pattern | Java 16 | `obj instanceof String s` | Type cast thủ công `(String)obj` |
| Record declaration | Java 16 | `record Point(int x, int y) {}` | Record pattern để deconstruct |
| Sealed types | Java 17 | `sealed interface Event permits A,B {}` | Chỉ "được phép kế thừa", chưa phải pattern switch |
| Record patterns | Java 21 | `obj instanceof Point(var x, var y)` | Dùng constructor hoặc cast record |
| Pattern matching for `switch` | Java 21 | `case String s -> ...` | Nhãn hằng `case "go" -> ...` |
| Guard `when` | Java 21 | `case String s when !s.isBlank() -> ...` | Cú pháp preview cũ dùng `&&` trong case |

**Không cần `--enable-preview`** khi dùng các tính năng chuẩn Java 21 trong bài. Java 17–20 từng có preview versions của pattern switch, nhưng các bài hướng dẫn preview có thể khác cú pháp và hành vi cuối cùng. Muốn học Java 21 ổn định, chọn source/release 21 và cú pháp của JEP 440/441.

Khi dự án bắt buộc Java 17, `instanceof String s` vẫn dùng được vì nó chuẩn từ Java 16. Nhưng `case String s`, `case Point(var x,var y)` trong `switch` chuẩn từ Java 21, nên không thể chỉ bật một setting IDE để "hợp lệ hóa" chúng trong build Java 17.

## 3. IDE hỗ trợ không đồng nghĩa compiler hỗ trợ

Một IDE hiển thị mã Java có thể đang sử dụng nhiều JDK khác nhau:

| Thành phần | Tác dụng | Ví dụ tình huống |
| --- | --- | --- |
| **IDE boot/runtime** | Chạy IDE | IDE khởi động trên JDK mới, nhưng project vẫn target Java 17 |
| **Java Language Server** | Phân tích cú pháp/diagnostics trong VS Code | Extension chạy bằng runtime riêng, không bắt buộc bằng JDK target |
| **Project/Module SDK/JDK** | Bộ API và công cụ biên dịch của dự án | Module A dùng JDK 17, module B dùng JDK 21 |
| **Language/source level** | Xác định cú pháp được phép | Source 17 từ chối pattern switch Java 21 |
| **Compiler target/release** | Classfile và API nền tảng | `--release 21` biên dịch cho Java 21 |
| **Maven/Gradle JVM/toolchain** | Chạy build và chọn compiler | Terminal và IDE import build bằng hai JDK khác nhau |
| **Run/Test JDK** | Chạy chương trình/test | Class Java 21 không chạy trên Java 17 |

**Thiết lập thống nhất cho bài này:** JDK biên dịch hỗ trợ `--release 21`, project/module source level 21, build release 21, JVM chạy chương trình Java 21 trở lên. Nếu IDE là phiên bản cũ, còn phải nâng parser/extension/JDT để editor nhận cú pháp chuẩn.

Kiểm tra trước khi đổ lỗi cho editor:

```bash
java -version
javac -version
```

Hai lệnh có thể báo khác phiên bản nếu biến môi trường/`PATH` đang trỏ tới các bản Java khác nhau. Trên Windows có thể dùng `where.exe java` và `where.exe javac`; Linux/macOS thường dùng `which java` và `which javac`.

### Dấu hiệu compiler đã dùng sai source level

Nếu `javac --release 17` báo `patterns in switch statements are not supported in -source 17`, đó là **lỗi phiên bản nguồn**, không phải Java 21 bị sai. Với JDK 21+, hãy thử biên dịch lại bằng `--release 21`, đồng thời sửa build file chính thức chứ không chỉ lệnh kiểm tra nhất thời.

## 4. So sánh các IDE phổ biến

| IDE | Thành phần Java | Thiết lập cốt lõi cần xem | Lợi thế |
| --- | --- | --- | --- |
| **IntelliJ IDEA** | Java parser, compiler integration, inspections và refactoring tích hợp | Project SDK, Project language level, Modules, Maven/Gradle JVM | IDE Java đầy đủ, code intentions và debugger |
| **Eclipse IDE** | Eclipse Java Development Tools (JDT)/Eclipse Compiler for Java | Installed JREs, Java Build Path, Java Compiler compliance | Phù hợp dự án JDT/legacy workspace |
| **VS Code** | Language Support for Java by Red Hat/JDT Language Server và các Java extensions | Java Runtime config, `java.configuration.runtimes`, project import | Editor linh hoạt, Java tooling dạng extensions |
| **Apache NetBeans** | Java platform/project system, editor và debugger | Java Platforms, Project Properties, source level, Maven/Gradle | IDE Java tích hợp, thuận tiện dự án đã dùng NetBeans |

Một số mốc hỗ trợ đã được nhà phát triển công bố:

- JetBrains liệt kê **IntelliJ IDEA 2023.3** hỗ trợ chuẩn Java 21 gồm record patterns và pattern matching for switch.
- Eclipse JDT công bố hỗ trợ các standard features Java 21 cho **Eclipse 2023-09 (4.29)** qua bộ cập nhật Java 21. Bản Eclipse cụ thể phải có phần JDT này hoặc bản mới hơn hỗ trợ đầy đủ.
- VS Code phụ thuộc bản **Language Support for Java** và JDT Language Server đang cài. Mức JDK tối thiểu để **chạy language server** thay đổi theo extension version; không nên đồng nhất với target JDK của project.
- Apache NetBeans 20 đã hỗ trợ làm việc với Java 21. Với các bản mới hơn, kiểm tra Java Platform và source level thực tế thay vì suy rằng mọi project đều tự động dùng Java 21.

**Chọn IDE theo dự án và môi trường đang có**, không phải theo lời khẳng định tuyệt đối IDE nào "chạy pattern nhanh nhất". Hỗ trợ ngôn ngữ, mức tiện lợi của quick fixes và tốc độ indexing là các tiêu chí khác nhau.

## 5. IntelliJ IDEA: cấu hình Project SDK và Language Level

### 5.1. Bật Java 21 đúng nơi

1. Mở **File → Project Structure**.
2. Tại **Project**, chọn **Project SDK** là JDK 21 (hoặc JDK mới hơn tương thích target 21).
3. Đặt **Project language level** thành **21**, không phải 17 Preview.
4. Mở **Modules → Sources** và kiểm tra **Language level** của từng module; có thể chọn Project default hoặc 21.
5. Trong **Modules → Dependencies**, kiểm tra Module SDK nếu được override riêng.
6. Với Gradle/Maven, kiểm tra JVM/toolchain/runner được dùng khi IDE import và build dự án.
7. Reload dự án rồi thử Build/Run chương trình mục 10.

Nếu đổi Project SDK sang 21 mà module vẫn target 17, IDE vẫn có lý do báo lỗi tại `case String s` hoặc `case Record(...)`. Nếu sau Maven/Gradle reload IDE tự quay lại 17, hãy sửa nguồn cấu hình `pom.xml`/`build.gradle(.kts)`.

### 5.2. Những tính năng IDE hỗ trợ

Tùy phiên bản và inspections đang bật, IntelliJ IDEA có thể:

- Nhận diện cú pháp Java 21 và gợi ý code completion cho patterns.
- Tô sáng biến pattern trong `when` và thân nhánh.
- Phát hiện lỗi scope, dominance, switch expression chưa exhaustive.
- Gợi ý chuyển `instanceof + cast` sang biến pattern hoặc đổi cấu trúc `if/else` khi phù hợp.
- Format code, rename và navigate record/component/method.
- Chạy, debug và test.

Trên keymap mặc định của Windows/Linux, thường có thể xem intentions qua `Alt+Enter`. Nhưng **không phải mọi bản IDE đều có cùng quick fix**, tên refactoring có thể khác, và auto-refactor không thay thế việc review hành vi `null`/exception.

### 5.3. Khi editor đỏ nhưng terminal biên dịch tốt

So sánh Project SDK, Module language level, Maven/Gradle project model, bản IntelliJ và thông báo compiler thật. Code completion không nhận `when` có thể là do parser/setting cũ, không nhất thiết do code. Đừng đổi mã đang hợp lệ theo JDK 21 chỉ để làm biến mất false-positive từ IDE cũ.

Tham khảo các trang JetBrains *Supported Java versions and features* và *Project/Module structure settings* ở phần cuối.

## 6. Eclipse IDE/JDT: cấu hình Compiler Compliance

Eclipse thường dựa trên **JDT** để parse và biên dịch Java. Với Java 21:

1. Dùng bản **Eclipse IDE for Java Developers** có JDT hỗ trợ các standard Java 21 features, hoặc áp dụng gói cập nhật Java 21 tương ứng.
2. Vào **Window → Preferences → Java → Installed JREs** (tùy hệ điều hành giao diện có thể khác) và thêm JDK 21.
3. Với dự án, kiểm tra **Properties → Java Build Path → Libraries** và JRE System Library/Execution Environment.
4. Vào **Project Properties → Java Compiler**, chọn **Compiler compliance level = 21**.
5. Xem mục sử dụng project-specific compliance nếu dự án không lấy default từ workspace.
6. Với Maven/Gradle project, cấu hình build file chính thức trước rồi cập nhật import.
7. Clean/Build và chạy chương trình Java 21.

**JDK trong Installed JREs** và **Compiler compliance** không phải cùng một setting. Installed JREs có 21 nhưng dự án được cấu hình compliance 17 vẫn không cho phép record pattern.

### 6.1. JDT Quick Fix và diagnostics

Eclipse có Java Quick Fix/refactoring, nhưng các phép biến đổi tự động cụ thể phụ thuộc version. Khi JDT báo case bị dominated hoặc scope sai, kiểm tra nguyên nhân theo Java specification. Khi JDT báo cú pháp Java 21 sai trong khi `javac --release 21` chấp nhận, kiểm tra bản cập nhật JDT và target Java của project.

**Mốc:** thông báo Eclipse 2023-09 (4.29) nói rõ hỗ trợ standard features Java 21 như JEP 440 và JEP 441. Nếu chạy bản 2023-09 cũ không có cập nhật phù hợp, không nên tự suy rằng nó đã có đầy đủ trình phân tích Java 21.

## 7. VS Code: Java extensions, JDT LS và Project JDK

VS Code cần extension Java. Thực tế nên cài **Extension Pack for Java** hoặc tối thiểu **Language Support for Java by Red Hat**, thêm Java Debugger/Test Runner nếu muốn sử dụng các tính năng đó trong editor.

### 7.1. Các bước cấu hình

1. Mở **root folder/workspace của dự án** thay vì chỉ một file rời rạc ngoài context.
2. Mở Command Palette và chọn **Java: Configure Java Runtime**.
3. Kiểm tra project nào đang sử dụng JDK 21 và source level nào.
4. Với Java project không có Maven/Gradle, có thể cấu hình danh sách project JDK qua `java.configuration.runtimes`.
5. Với Maven/Gradle, sửa `pom.xml` hoặc `build.gradle(.kts)` rồi để extension import lại.
6. Kiểm tra **Problems**, **Output** của Java extension và compiler output khi có lỗi.
7. Chạy file mẫu và so với terminal.

Ví dụ `settings.json` **chỉ minh họa cho máy Linux có đúng đường dẫn JDK được nêu**:

```json
{
  "java.configuration.runtimes": [
    {
      "name": "JavaSE-21",
      "path": "/usr/lib/jvm/java-21-openjdk",
      "default": true
    }
  ]
}
```

Trên máy khác phải sử dụng **đường dẫn JDK thực tế**, không copy nguyên `path` một cách máy móc. `default: true` đặc biệt hữu ích cho project **không có build tool**; Maven/Gradle vẫn có thể quy định source/release riêng.

### 7.2. Tách JDK của Language Server khỏi JDK của dự án

Java language server (Eclipse JDT LS) là một chương trình chạy riêng. Một số bản extension theo nền tảng có runtime nhúng; bản universal có thể cần JDK ngoài đạt yêu cầu khởi động. Cài đặt `java.jdt.ls.java.home` (khi cần) chỉ JDK để khởi chạy server, trong khi `java.configuration.runtimes` mô tả JDK của Java projects.

**Yêu cầu JDK để chạy JDT LS có thể cao hơn JDK target 21 ở các extension release mới**. Khi có thông báo "language server requires newer Java", đọc tài liệu **JDK Requirements** của version đang cài thay vì ép toàn bộ project lên JDK đó. Một extension có thể chạy trên runtime mới nhưng vẫn hỗ trợ build các dự án target Java cũ qua toolchain.

### 7.3. Khắc phục Java extension không nhận pattern

Nếu code biên dịch bằng `javac --release 21` nhưng VS Code báo lỗi:

- Kiểm tra extension đã được bật, Java Language Server đã khởi động.
- Kiểm tra Project JDK và Maven/Gradle import, không chỉ Java version trong terminal.
- Mở lệnh **Java: Configure Java Runtime** để thấy các lựa chọn thực tế.
- Khi cache/workspace model bị hỏng, có thể dùng **Java: Clean Java Language Server Workspace**, sau đó để extension import lại dự án. Thao tác này tái tạo cache, không sửa mã nguồn.
- Nếu vẫn lỗi, đọc Output logs và kiểm tra phiên bản extension/JDT LS.

Các thao tác Code Action/Refactor thường xuất hiện qua menu editor khi Java language service hoạt động. Không suy rằng VS Code có cùng danh sách refactor hoặc shortcut như IntelliJ/Eclipse.

## 8. Apache NetBeans: Java Platform và source level

Apache NetBeans tích hợp editor, project support và debugger cho Java. Với bài thực hành Java 21:

1. Dùng bản NetBeans mới phù hợp JDK hiện hành (dòng NetBeans 20 trở lên đã có hỗ trợ Java 21; nên chọn bản đang được hỗ trợ).
2. Mở **Tools → Java Platforms** để kiểm tra JDK 21 đã được khai báo.
3. Trong **Project Properties**, xem Java Platform và Source/Binary Format hoặc Java source level của project.
4. Với project Maven/Gradle, bảo đảm compiler release/toolchain trong build file không bị đặt lại về 17.
5. Chạy Build/Clean và test file Java 21; đối chiếu thông báo với terminal.

JDK chạy NetBeans không nhất thiết là JDK biên dịch project. Nếu editor nhận record declaration nhưng không nhận `case Point(var x, var y)`, kiểm tra cả parser/support version và source level. Đừng đánh đồng "IDE đang chạy được trên JDK 21" với "dự án đã target Java 21".

## 9. Maven, Gradle và build CI phải đồng nhất với IDE

### 9.1. Maven Compiler Plugin

Trong `pom.xml`, giá trị cấu hình thông thường:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Đây là **đoạn thuộc `pom.xml`**, không phải một POM hoàn chỉnh. Compiler Plugin chuyển target thành chế độ tương đương `javac --release 21` với toolchain thích hợp. Cần dùng phiên bản Maven/Compiler Plugin hiểu property và JDK đủ mới. `--release` kiểm tra source syntax, classfile và API nền tảng mục tiêu, khác với chỉ đặt `-source`.

Kiểm tra môi trường build:

```bash
mvn -version
```

Lệnh `mvn -version` cho biết runtime Java mà Maven thực sự sử dụng. Khi repository có Maven Wrapper, ưu tiên wrapper phù hợp project, ví dụ `./mvnw test` trên môi trường hỗ trợ hoặc `mvnw.cmd test` trên Windows.

### 9.2. Gradle Java Toolchains

Ví dụ cho `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
```

Đây là **Kotlin DSL của Gradle**, không phải Java source. Toolchain chọn JDK dùng cho các tác vụ; `options.release` giữ target Java 21 với `javac`. Gradle phiên bản quá cũ có thể chưa hỗ trợ JDK 21 phù hợp, cần xem bảng tương thích và cập nhật có kiểm soát.

Nếu repository dùng Gradle Wrapper, chạy `./gradlew test` hoặc `gradlew.bat test` theo hệ điều hành. **Gradle daemon JVM**, **Java Toolchain** và **IDE JVM** có thể khác nhau, vì thế lỗi "IDE xanh, Gradle đỏ" thường do một trong các lớp này chưa đồng bộ.

### 9.3. Không lạm dụng preview flags

Record patterns, switch patterns và `when` đã chuẩn trong Java 21. Không thêm `--enable-preview` chỉ vì bài hướng dẫn Java 17 preview cũ yêu cầu. Cờ preview áp dụng cho các tính năng **chưa chuẩn trong chính release đang dùng**, và phải được quản lý đúng lúc compile/run nếu thực sự cần.

### 9.4. Compile độc lập

Đối với file mẫu mục 10:

```bash
javac --release 21 IdePatternSmokeTest.java
java IdePatternSmokeTest
```

Đây là cổng kiểm tra không phụ thuộc IDE. Nếu `javac` thành công còn IDE parser báo lỗi, phải điều tra cấu hình của IDE. Nếu compiler báo lỗi, ưu tiên sửa Java source hoặc target trước.

## 10. Chương trình Java 21 hoàn chỉnh để thử IDE

Tạo đúng file **`IdePatternSmokeTest.java`**. Mã này chỉ dùng Java standard library, giúp kiểm tra các tính năng IDE cần phân tích: nested record patterns, guard `when`, sealed hierarchy, `null` và flow scoping của `instanceof`.

```java
public class IdePatternSmokeTest {
    record Customer(String name, int age) {}
    record Purchase(Customer customer, int cents) {}

    sealed interface Command permits Print, Close {}
    record Print(String text) implements Command {}
    record Close() implements Command {}

    static String describe(Object input) {
        return switch (input) {
            case Purchase(Customer(var name, var age), var cents)
                    when name != null && !name.isBlank()
                            && age >= 18 && cents > 0 ->
                    "approved:" + name.trim() + ":" + cents;
            case Purchase(Customer(var name, var age), var cents) ->
                    "review:" + age + ":" + cents;
            case Purchase(var customer, var cents) ->
                    "missing customer";
            case String s when s.isBlank() -> "blank";
            case String s -> "text:" + s.strip();
            case null -> "null";
            default -> "other";
        };
    }

    static String route(Command command) {
        return switch (command) {
            case Print(var text) when text != null && !text.isBlank() ->
                    "print:" + text.strip();
            case Print(var text) -> "empty print";
            case Close c -> "close";
            case null -> "null command";
        };
    }

    static String tag(Object value) {
        if (!(value instanceof String s)) {
            return "not text";
        }
        return "len=" + s.length();
    }

    static void check(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + " expected=" + expected + ", got=" + actual);
        }
        System.out.println(name + " => " + actual);
    }

    public static void main(String[] args) {
        check("eligible", "approved:Lan:150",
                describe(new Purchase(new Customer(" Lan ", 22), 150)));
        check("minor", "review:17:150",
                describe(new Purchase(new Customer("Mai", 17), 150)));
        check("zero", "review:22:0",
                describe(new Purchase(new Customer("Mai", 22), 0)));
        check("null-name", "review:22:150",
                describe(new Purchase(new Customer(null, 22), 150)));
        check("missing-customer", "missing customer",
                describe(new Purchase(null, 150)));
        check("blank-text", "blank", describe(" \t "));
        check("plain-text", "text:Java", describe(" Java "));
        check("null-value", "null", describe(null));
        check("other", "other", describe(9));
        check("print", "print:hello", route(new Print(" hello ")));
        check("empty-print", "empty print", route(new Print(null)));
        check("close", "close", route(new Close()));
        check("null-command", "null command", route(null));
        check("scope", "len=3", tag("JDK"));
        check("scope-fallback", "not text", tag(10));
        System.out.println("SMOKE TEST PASS");
    }
}
```

Chạy:

```bash
javac --release 21 IdePatternSmokeTest.java
java IdePatternSmokeTest
```

**Đầu ra stdout chính xác đã xác minh:**

```text
eligible => approved:Lan:150
minor => review:17:150
zero => review:22:0
null-name => review:22:150
missing-customer => missing customer
blank-text => blank
plain-text => text:Java
null-value => null
other => other
print => print:hello
empty-print => empty print
close => close
null-command => null command
scope => len=3
scope-fallback => not text
SMOKE TEST PASS
```

### Những tính năng có trong bài test

- **Nested record pattern:** `Purchase(Customer(var name, var age), var cents)`.
- **Guard:** `when name != null && !name.isBlank() && age >= 18 && cents > 0`. Guard không chạy nếu pattern thất bại.
- **Component null:** `new Customer(null, 22)` vẫn match các `var` component; guard chặn NPE.
- **Record nested null:** `new Purchase(null,150)` không match `Customer(...)` nhưng match `Purchase(var customer, var cents)`.
- **Null selector:** `case null` được xử lý riêng; `default` không tự xử lý null.
- **Sealed interface:** `route(Command)` liệt kê `Print` và `Close`, không cần `default` vì bao phủ các subtype được phép.
- **Flow scoping:** trong `tag`, biến `s` dùng hợp lệ sau early return khi phủ định `instanceof`.
- **Assertions thực sự chạy:** `check` dùng `throw new AssertionError`, không phụ thuộc cờ JVM `-ea`.

Chương trình có 15 ca kiểm tra và dòng kết thúc **`SMOKE TEST PASS`**, tổng cộng 16 dòng stdout. Nếu một kết quả không khớp, chương trình ném `AssertionError`.

## 11. Thử language level sai để hiểu lỗi IDE

Cùng file mẫu, cố ý thử:

```bash
javac --release 17 IdePatternSmokeTest.java
```

**Kỳ vọng: compilation thất bại.** Trên JDK mới dùng `--release 17`, trình biên dịch báo đại ý:

```text
patterns in switch statements are not supported in -source 17
deconstruction patterns are not supported in -source 17
```

Đây là **diagnostics được trích dạng thông báo chính**, không phải toàn bộ output có đường dẫn tệp và số dòng; chẩn đoán chính xác có thể khác theo JDK. Bài kiểm thử chứng minh Java 17 không nhận syntax Java 21.

Khi IDE báo lỗi giống vậy, hãy ưu tiên kiểm tra **project/module language level** và build configuration, không viết lại cú pháp chuẩn Java 21 thành dạng preview cũ hoặc bật preview không cần thiết.

**Chú ý:** Đừng đưa lệnh cố ý thất bại này vào build pipeline bình thường; chỉ dùng khi học hoặc chẩn đoán source level.

## 12. Dùng IDE để debug và đọc pattern variables

IDE hỗ trợ Java 21 có thể giúp đặt breakpoint và xem các biến pattern:

```java
case Purchase(Customer(var name, var age), var cents)
        when name != null && !name.isBlank()
                && age >= 18 && cents > 0 ->
        "approved:" + name.trim() + ":" + cents;
```

Với khách hàng tuổi 22, tên `" Lan "`, số tiền 150, nhánh trả `approved:Lan:150`. Với khách hàng tuổi 17, pattern vẫn match nhưng guard false, Java xét nhánh `Purchase(Customer(...))` không guard phía sau và trả `review:17:150`.

**Khuyến nghị debug:**

- Đặt breakpoint trong nhánh xử lý hoặc trong helper boolean dùng làm guard.
- Kiểm tra `name`, `age`, `cents` sau khi chúng đã bind. Debugger có thể không hiển thị biến pattern khi đường đi chưa bảo đảm match.
- Nếu `when` quá dài, tách thành predicate có tên rõ ràng để test/step trong helper, nhưng **giữ nguyên thứ tự short-circuit**.
- Với record patterns lồng nhau, kiểm tra `null` ở từng cấp; đừng giả định record component luôn non-null.
- Khi statement chạy nhưng editor hiện warning, kiểm tra version/cấu hình thay vì vội sửa Java semantics.

Việc breakpoint chính xác trên nhãn `case` hoặc từng biểu thức `when` phụ thuộc debugger; không phải IDE nào cũng dừng ở vị trí giống nhau. Debug giúp quan sát runtime, còn **compiler/JLS** quyết định ngôn ngữ hợp lệ.

## 13. IDE refactoring: khi nào nên tin và khi nào phải kiểm tra lại?

IDE có thể gợi ý chuyển từ kiểm tra kiểu/cast thủ công sang type pattern.

**Trước:**

```java
static String textLabel(Object input) {
    if (input instanceof String) {
        String s = (String) input;
        return s.strip();
    }
    return "other";
}
```

**Sau:**

```java
static String textLabel(Object input) {
    if (input instanceof String s) {
        return s.strip();
    }
    return "other";
}
```

Khi guard và nhánh được giữ nguyên, đây là ứng viên phù hợp cho refactor bằng quick fix/inspection. Tuy nhiên, refactoring không được làm sai **null behavior**, exception hoặc thứ tự side effects.

### 13.1. Direct cast không tương đương với match + fallback

```java
static int oldApi(Object input) {
    return ((String) input).length();
}
```

Với `Integer` đầu vào, code cũ ném `ClassCastException`. Với `null`, cast trả về null rồi `length()` ném `NullPointerException`.

```java
static int newApi(Object input) {
    return input instanceof String s ? s.length() : -1;
}
```

Bản sau trả `-1` khi không match, **đã thay đổi hợp đồng**, không còn refactor cú pháp thuần túy. Dù IDE giúp sinh code, người phát triển vẫn phải đánh giá thay đổi.

### 13.2. Chuyển `if/else` sang `switch` cần thêm kiểm tra

- Với `if (value instanceof String s) ... else ...`, selector `null` thường đi vào fallback. Trong pattern switch, `null` cần `case null` nếu muốn giữ fallback.
- `case CharSequence cs` đứng trước `case String s` sẽ gây dominance; đặt kiểu con trước kiểu cha.
- Guard `when` có thứ tự: nếu hai guard có thể cùng đúng, nhánh đứng trước được ưu tiên.
- Record deconstruction có thể gọi accessor; nếu accessor custom có side effect/exception, refactor có thể thay đổi hành vi.
- `switch` expression cần exhaustive, và block trong expression dùng `yield` để tạo giá trị.

Auto-refactor tốt là khởi đầu cho code review và tests, **không phải chứng cứ chương trình đã tương đương**.

## 14. Chẩn đoán lỗi thường gặp

| Thông báo/triệu chứng | Khả năng cao | Kiểm tra/sửa |
| --- | --- | --- |
| `patterns in switch ... not supported in -source 17` | Compiler source/release = 17 | Chọn Java 21 trong build/project/module |
| `record/deconstruction patterns not supported` | JDK target hoặc parser cũ | Java 21 và IDE/JDT/extension hỗ trợ chuẩn Java 21 |
| `this case label is dominated...` | Case tổng quát đứng trước case đặc hiệu | Guard/specific/subtype trước general |
| `switch expression does not cover all possible input values` | Thiếu nhánh exhaustive | Thêm `default` hoặc đủ sealed subtype |
| `cannot find symbol: s` sau điều kiện pattern | Sai flow scope | Chỉ dùng `s` khi match được bảo đảm |
| `NullPointerException` khi chuyển `if` sang pattern switch | Chưa xử lý `null` selector theo hợp đồng | Xem `case null`, test null |
| `UnsupportedClassVersionError` lúc Run | JVM chạy cũ hơn target classfile | Chạy với Java 21+ hoặc build đúng target |
| IDE tô đỏ nhưng `javac --release 21` chạy được | Project model, cache, parser/version hoặc module level | Kiểm tra JDK, reload/reimport, cập nhật tooling |
| `mvn test` fail còn IDE build pass | Maven JVM/Compiler Plugin/source level khác | `mvn -version`, `maven.compiler.release` |
| `gradlew test` fail còn editor xanh | Toolchain/Gradle JVM/Gradle version | Kiểm tra Gradle toolchains và wrapper |
| VS Code không có Java completion | Java extension/JDT LS chưa chạy/import | Configure Java Runtime, xem Output logs |
| Eclipse project compliance 17 | Java Compiler project settings | Đặt compliance 21 và JRE System Library |
| IntelliJ tự quay về level 17 khi reload | Cấu hình Maven/Gradle là nguồn gốc | Sửa build file, reload project |
| NetBeans chạy trên JDK 21 nhưng source 17 | IDE boot JDK khác project source level | Kiểm tra Project Properties |
| Quick fix gây test null/exception đỏ | Refactor đã đổi behavior | So baseline, rollback hoặc sửa có test |

### Trình tự khắc phục an toàn

1. **Phân loại lỗi:** lỗi editor/JDT hay lỗi `javac` thật?
2. **Xác nhận compiler:** chạy `javac -version` và thử `javac --release 21` trên file mẫu.
3. **Kiểm tra build:** Maven `release` hoặc Gradle toolchains; build có thể override IDE.
4. **Kiểm tra project/module language level** và Java Platform/Installed JRE.
5. **Kiểm tra IDE/parser/extension version** có hỗ trợ Java 21 chuẩn.
6. Nếu cấu hình đúng nhưng diagnostics cũ, reload/clean workspace có kiểm soát.
7. Khi compiler vẫn báo lỗi, xem lại chính code: flow scoping, dominance, exhaustiveness, null.
8. Chạy regression tests trước khi chốt thay đổi.

Không nên tắt toàn bộ IDE inspections để che compiler errors. Ngược lại, cũng không nên sửa cú pháp Java 21 hợp lệ chỉ vì plugin phân tích Java cũ chưa hiểu nó.

## 15. Dự án nhiều module và khả năng tái lập trên CI

Một repository có thể có module Java 17 và module Java 21. **Project SDK=21** không tự đồng nghĩa mọi module được phép dùng `case Type variable` trong `switch`. Xác định release per-module, dependencies của từng module và runtime triển khai.

CI nên kiểm tra:

- Phiên bản JDK/toolchain được pin hoặc khai báo rõ.
- Build file source/release của project đã được commit.
- Test cho `null` selector, nested record, guard true/false, subtype và sealed switch.
- Refactor `instanceof + cast` không làm đổi output/exception/side effects.
- Build ở terminal và IDE đều ra cùng kết quả; không lệ thuộc máy riêng của một developer.

Nếu CI đang target Java 17, **không đưa Java 21 syntax vào** rồi cho rằng "IDE tôi chạy được" là đủ. Cần phê duyệt thay đổi target/JDK triển khai hoặc giữ cú pháp tương thích.

### Cách chọn IDE cho đội nhóm

Dùng công cụ mà nhóm quản lý được phiên bản và kiểm thử:

- IntelliJ: mạnh ở inspections, điều hướng và multi-module.
- Eclipse: hợp với workspace/JDT, project compliance rõ ràng.
- VS Code: tiện khi dự án nhiều ngôn ngữ, nhưng phải quản lý Java extensions/JDT LS.
- NetBeans: phù hợp nếu dự án và team đã quen Java Platform/project workflow.

Tất cả đều cần **build/test gate độc lập**. Không lấy việc IDE tô màu là bằng chứng đã hỗ trợ đúng Java 21.

## 16. Checklist hoàn tất thiết lập

- [ ] Đã xác định tính năng cần `instanceof` Java 16 hay record/switch patterns Java 21.
- [ ] JDK dùng compile hỗ trợ `--release 21`.
- [ ] IDE/extension/JDT có hỗ trợ standard features Java 21.
- [ ] Project/Module Language Level/Compliance được đặt 21.
- [ ] Maven Compiler Plugin hoặc Gradle toolchain/options.release nhắm Java 21.
- [ ] Run/Test JDK không thấp hơn target classfile.
- [ ] IntelliJ Module language level không override project một cách không mong muốn.
- [ ] Eclipse Installed JRE/JRE System Library/Compiler compliance tương thích.
- [ ] VS Code Language Server hoạt động, Project JDK cấu hình đúng, không nhầm với JDK chạy server.
- [ ] NetBeans Java Platform và project source level tương thích.
- [ ] `IdePatternSmokeTest.java` biên dịch, chạy và in chính xác 16 dòng.
- [ ] `null`, nested record, guards, sealed switch được test.
- [ ] Diagnostics IDE được so với compiler thật nếu có khác biệt.
- [ ] Quick fixes/refactorings đã được review về hành vi.
- [ ] CI build/test tương tự môi trường developer.

**Definition of Done:** Mở file mẫu trong IDE đã chọn, không có lỗi cú pháp giả, compiler source level 21 chạy được, kết quả đúng, debugger/test runner có thể quan sát đường thực thi, và cấu hình dự án tái lập được cho người khác.

## 17. Câu hỏi tự kiểm tra

**1. Dùng `case 1 -> ...` đã là pattern matching chưa?**  
Chưa. Đây là switch rule với nhãn hằng; pattern match nằm ở nhãn như `case String s`.

**2. Java 17 có hỗ trợ `instanceof String s` không?**  
Có, vì tính năng này chuẩn từ Java 16. Điều đó không có nghĩa Java 17 hỗ trợ chuẩn pattern switch.

**3. Nếu IntelliJ có Project SDK 21 nhưng Module language level 17, `case Point(...)` có hợp lệ không?**  
Không ở source level của module. Cần chỉnh override/module hoặc build file.

**4. Eclipse cài JDK 21 trong Installed JREs đã đủ chưa?**  
Chưa. Kiểm tra JRE System Library, Java Compiler compliance 21 và build tool.

**5. VS Code đang chạy Java Language Server trên JDK mới hơn 21 thì project buộc dùng JDK đó không?**  
Không. Project JDK/release có thể khác runtime của language server.

**6. Có bắt buộc dùng `--enable-preview` cho pattern switch Java 21 không?**  
Không. Pattern switch và record patterns là standard features trong Java 21.

**7. Vì sao `case String s` đặt dưới `case CharSequence c` bị compiler từ chối?**  
Mọi String đều là CharSequence; case hẹp bị case rộng trước nó dominate.

**8. Tại sao thiếu `case null` có thể làm refactor `if instanceof` sang switch đổi hành vi?**  
`instanceof` với null trả false; `switch` trên null thường ném NPE nếu không có nhánh thích hợp. `default` không tự xử lý null.

**9. Có nên tin Quick Fix của IDE mà không chạy test?**  
Không. Một thay đổi có thể làm sai null, exception, thứ tự guard hoặc side effects.

**10. Dòng `SMOKE TEST PASS` chứng minh điều gì?**  
Các phép so sánh trong chương trình mẫu đã đạt với 15 input đã thử; nó không tự chứng minh mọi code trong toàn repository đều chính xác.

**11. Khi `javac --release 21` chạy tốt nhưng IDE báo lỗi, phải làm gì?**  
Kiểm tra JDK/module language level, build import, version parser/extension/JDT, workspace cache và logs; không vội sửa Java code hợp lệ.

**12. Maven và Gradle target khác IDE thì tin kết quả nào khi merge?**  
Cần thống nhất target chính thức của repository và CI. Build reproducibility trên compiler/test suite là tiêu chí quan trọng hơn màu cảnh báo riêng của một IDE.

## 18. Tài liệu tham khảo chính thức

### Java

- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java SE 21 Language Specification — switch](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)

### IDE / Java support

- [JetBrains — Supported Java versions and features](https://www.jetbrains.com/help/idea/supported-java-versions.html)
- [JetBrains — Project structure settings](https://www.jetbrains.com/help/idea/project-settings-and-structure.html)
- [JetBrains — Module structure settings](https://www.jetbrains.com/help/idea/configure-modules.html)
- [Eclipse JDT — Java Compiler Preferences](https://help.eclipse.org/latest/topic/org.eclipse.jdt.doc.user/reference/preferences/java/ref-preferences-compiler.htm)
- [Eclipse — Java 21 support for Eclipse 2023-09](https://www.eclipse.org/lists/eclipse-dev/msg12203.html)
- [VS Code — Managing Java Projects](https://code.visualstudio.com/docs/java/java-project)
- [Red Hat Java extension — JDK Requirements](https://github.com/redhat-developer/vscode-java/wiki/JDK-Requirements)
- [Red Hat Java extension — Language Support for Java](https://github.com/redhat-developer/vscode-java)
- [Apache NetBeans — Version 20/Java 21](https://netbeans.apache.org/front/main/download/nb20/)

### Build tools

- [Apache Maven Compiler Plugin — Setting compiler release](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
