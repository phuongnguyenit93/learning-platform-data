# Đồng bộ UTF-8 giữa mã nguồn, tài nguyên, IDE và cấu hình build của dự án

## 1. Mục tiêu: một hợp đồng UTF-8 xuyên suốt dự án

Trong module **JAVA_VERSION_JAVA18**, Java 18 đưa UTF-8 thành charset mặc định của nhiều API Java theo [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400). Thay đổi này giúp ứng dụng có hành vi mặc định nhất quán hơn giữa các hệ điều hành. Tuy nhiên, nó không tự đồng bộ encoding của mã nguồn, tài nguyên, IDE, compiler và plugin build.

Bài thuộc chương **Kiểm chứng mã hóa**. Ta sẽ thiết lập và kiểm tra UTF-8 tại bốn lớp:

1. **Mã nguồn và compiler:** editor lưu file Java bằng UTF-8, compiler đọc source bằng UTF-8.
2. **Tài nguyên và build:** resource được lưu theo charset của định dạng; bước lọc/thay placeholder phải dùng đúng encoding.
3. **Runtime:** chương trình đọc resource bằng Reader/decoder có charset tường minh; không phụ thuộc default charset ngoài ý muốn.
4. **IDE và nhóm phát triển:** cấu hình dự án và EditorConfig giúp các máy lưu file nhất quán; build vẫn là nơi xác nhận cuối cùng.

Mục tiêu là tránh tình huống IDE hiển thị đúng nhưng compiler đọc sai, source compile đúng nhưng resource bị đổi byte khi build, hoặc file resource đúng nhưng runtime đọc theo charset khác.

## 2. Phân biệt encoding của source, resource và runtime

Một dự án Java có nhiều ranh giới chuyển đổi. Cùng một charset UTF-8 có thể cần được khai báo ở nhiều nơi vì mỗi công cụ chịu trách nhiệm cho một bước riêng.

| Thành phần | Bước chuyển đổi | Cấu hình cần kiểm tra |
| --- | --- | --- |
| File `.java` | Byte trên đĩa → ký tự source cho compiler | Encoding của editor và `javac -encoding UTF-8` |
| Maven compiler | Source → bytecode | `maven-compiler-plugin` với encoding UTF-8 |
| Gradle compiler | Source → bytecode | `JavaCompile.options.encoding = "UTF-8"` |
| Resource filtering | Byte resource → ký tự → byte resource đã xử lý | Charset của Maven Resources Plugin hoặc Gradle filtering |
| Runtime resource | Byte resource → String | `InputStreamReader`/`CharsetDecoder` với UTF-8 |
| File văn bản | Byte file → String hoặc String → byte file | `Files.readString/writeString` hoặc overload có `Charset` |
| IDE | Chỉnh sửa và lưu file | Project encoding, file encoding và cấu hình `.editorconfig` |

**Không có một công tắc duy nhất** điều khiển mọi bước trên. `Charset.defaultCharset()` là default của JVM theo JEP 400; nó không thay thế tùy chọn encoding của compiler, cấu hình resource filtering hay charset mà ứng dụng cần dùng để đọc một định dạng file cụ thể.

Một nguyên tắc hữu ích là ghi charset ở đúng ranh giới chuyển đổi. Nếu resource được quy định UTF-8, hãy đọc nó bằng UTF-8 ngay tại nơi tạo Reader. Nếu compiler phải đọc source UTF-8, hãy cấu hình compiler thay vì trông chờ IDE hoặc máy phát triển.

## 3. Lưu mã nguồn Java bằng UTF-8 và cấu hình compiler

### 3.1. Vì sao phải cấu hình cả editor và compiler?

Editor quyết định byte được ghi xuống file. Compiler quyết định cách giải mã byte đó thành ký tự source. Nếu hai bên không thống nhất, một chuỗi literal như tiếng Việt có thể bị đọc sai trước khi tạo class file.

Ví dụ source có literal:

```java
public final class SourceEncodingExample {
    public static String message() {
        return "Tiếng Việt | café | € | 🚀";
    }
}
```

Lưu file trên đĩa bằng UTF-8 và cấu hình compiler đọc UTF-8. Với `javac`, chỉ định rõ encoding:

```bash
javac -encoding UTF-8 -d out src/main/java/SourceEncodingExample.java
```

Tùy chọn `-encoding` điều khiển charset của file source mà compiler đọc. Nó độc lập với `-d` (thư mục output) và `--release` (phiên bản API/ngôn ngữ mục tiêu). Không dùng `--release` để thay thế cấu hình encoding.

JEP 400 thay đổi default charset của runtime trên JDK 18+, nhưng build nên khai báo encoding tường minh để không phụ thuộc JDK, toolchain hoặc cấu hình môi trường của từng máy. Điều này cũng giúp dự án có cùng hành vi khi compile trên máy lập trình viên và CI.

### 3.2. Cấu hình Maven

Đặt encoding dùng chung trong `pom.xml`:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>
```

Cấu hình compiler plugin để source encoding được thể hiện rõ:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <encoding>${project.build.sourceEncoding}</encoding>
            </configuration>
        </plugin>
    </plugins>
</build>
```

`project.build.sourceEncoding` là property quy ước được nhiều Maven plugin sử dụng. `project.reporting.outputEncoding` dành cho nội dung báo cáo; nó không thay thế encoding của source hay resource. Trong dự án thực tế, nên quản lý phiên bản plugin rõ ràng trong `build/plugins` hoặc `pluginManagement` để các máy và CI dùng cùng hành vi build.

Nếu dự án dùng property chung cho compiler, có thể tham chiếu property đó trong cấu hình plugin thay vì lặp chuỗi `UTF-8`; điều quan trọng là giá trị cuối cùng phải được xác định rõ trong effective POM.

### 3.3. Cấu hình Gradle

Với Gradle Groovy DSL:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Với Gradle Kotlin DSL:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
```

Cấu hình này áp dụng cho các task `JavaCompile`, bao gồm source set chính và test khi chúng dùng task loại này. Nếu dự án có task compiler tự tạo hoặc plugin bên ngoài, kiểm tra task đó có kế thừa cấu hình chung hay cần khai báo riêng.

## 4. Đồng bộ encoding cho resource và bước filtering

### 4.1. Resource được copy và resource được filtering

Resource có thể được copy nguyên byte từ `src/main/resources` sang output, hoặc được xử lý như văn bản khi build thay placeholder như `$`{app.name}.

- Nếu chỉ copy file và không filter, build thường giữ nguyên byte nguồn; không cần giải mã rồi mã hóa lại.
- Nếu filter nội dung, plugin phải giải mã resource thành ký tự rồi ghi lại byte. Khi đó cần khai báo charset filtering là UTF-8.
- Không áp dụng text filtering lên ảnh, font, archive hoặc resource nhị phân. Filtering có thể làm hỏng byte của các file này.

Một lỗi thường gặp là mã nguồn được compile UTF-8 nhưng resource filtering dùng charset mặc định khác. Khi đó file trong source tree đúng, còn file ở thư mục build output đã thay đổi byte.

### 4.2. Cấu hình Maven Resources Plugin

Ví dụ cấu hình:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-resources-plugin</artifactId>
            <configuration>
                <encoding>${project.build.sourceEncoding}</encoding>
                <propertiesEncoding>UTF-8</propertiesEncoding>
            </configuration>
        </plugin>
    </plugins>
</build>
```

`encoding` điều khiển việc đọc/ghi resource dạng văn bản trong plugin. `propertiesEncoding` cho phép chỉ định riêng encoding của resource `.properties`; tham số này có trong Maven Resources Plugin từ phiên bản 3.2.0. Hãy dùng phiên bản plugin có hỗ trợ tham số đó và pin phiên bản plugin theo quy ước build của dự án.

Không bật filtering cho toàn bộ resource một cách máy móc. Chỉ filter các file văn bản thật sự có placeholder; khai báo riêng các nhóm resource cần filter và loại trừ file nhị phân.

### 4.3. Cấu hình Gradle khi có resource filtering

Với Gradle Groovy DSL:

```groovy
tasks.withType(ProcessResources).configureEach {
    filteringCharset = 'UTF-8'
}
```

Với Gradle Kotlin DSL:

```kotlin
tasks.withType<ProcessResources>().configureEach {
    filteringCharset = "UTF-8"
}
```

`filteringCharset` được dùng khi task filter nội dung resource. Nếu task chỉ copy byte và không thực hiện filter, resource được giữ nguyên byte; thiết lập này không tự chuyển mã tất cả file. Nếu dự án có task copy/filter tự định nghĩa, kiểm tra charset ở chính task đó.

## 5. Đọc resource UTF-8 một cách tường minh ở runtime

Resource đóng gói trong JAR không nhất thiết là file có đường dẫn trên filesystem. Dùng class loader để lấy stream và chỉ định UTF-8 tại ranh giới byte → ký tự.

Ví dụ resource `src/main/resources/messages.txt` có nội dung:

```text
Tiếng Việt | café | € | 🚀
```

Đọc resource bằng `InputStreamReader`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public final class MessageResource {
    public static String readMessage() throws IOException {
        InputStream input = MessageResource.class
                .getResourceAsStream("/messages.txt");

        if (input == null) {
            throw new IOException("Không tìm thấy /messages.txt");
        }

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(input, StandardCharsets.UTF_8))) {
            return reader.readLine();
        }
    }
}
```

Không dùng `new InputStreamReader(input)` nếu định dạng resource đã quy định UTF-8 mà không truyền charset. Overload không có charset dựa vào default charset; charset tường minh thể hiện đúng hợp đồng và dễ review.

Nếu resource là file văn bản trên filesystem, `Files.readString(path)` và `Files.writeString(path, text)` dùng UTF-8 theo hợp đồng API từ Java 11. Khi định dạng khác UTF-8, dùng overload nhận `Charset`. Với resource trong classpath/JAR, dùng class loader để lấy stream thay vì giả định resource có thể truy cập bằng `Path`.

### 5.1. Kiểm tra giải mã nghiêm ngặt khi cần xác thực

Nếu yêu cầu là từ chối resource có byte UTF-8 lỗi, dùng decoder `REPORT`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] bytes)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
```

Cách này phát hiện byte malformed thay vì âm thầm thay bằng U+FFFD. Dùng nó cho fixture, file cấu hình hoặc dữ liệu đầu vào mà tính toàn vẹn encoding là một phần của hợp đồng.

## 6. Lưu ý riêng với file `.properties`

Không đồng nhất mọi API đọc `.properties`:

- `Properties.load(InputStream)` có quy tắc ISO-8859-1 và hỗ trợ escape Unicode `\uXXXX`. Nó không tự dùng UTF-8 chỉ vì JDK 18+ có default charset UTF-8.
- `Properties.load(Reader)` nhận ký tự đã được giải mã. Nếu file properties là UTF-8, hãy tạo `InputStreamReader` bằng `StandardCharsets.UTF_8`.
- `Properties.store(OutputStream, ...)` ghi theo quy tắc định dạng của API, trong đó ký tự ngoài ISO-8859-1 được biểu diễn bằng escape Unicode; nếu cần ghi văn bản theo charset khác, dùng overload nhận `Writer` và quy định charset khi tạo Writer.

Ví dụ đọc file UTF-8:

```java
import java.io.InputStream;
import java.io.InputStreamReader;
import java.util.Properties;
import java.nio.charset.StandardCharsets;

static Properties loadUtf8Properties() throws java.io.IOException {
    Properties properties = new Properties();

    try (InputStream input = MessageResource.class
            .getResourceAsStream("/messages.properties")) {
        if (input == null) {
            throw new java.io.IOException("Không tìm thấy messages.properties");
        }

        try (InputStreamReader reader =
                new InputStreamReader(input, StandardCharsets.UTF_8)) {
            properties.load(reader);
        }
    }
    return properties;
}
```

Ví dụ này làm rõ charset ở nơi đọc byte. Đừng đổi file properties sang UTF-8 rồi vẫn gọi `load(InputStream)` với giả định rằng API sẽ dùng default UTF-8.

## 7. Đồng bộ cấu hình IDE và EditorConfig

IDE ảnh hưởng cách file được hiển thị và lưu. Cấu hình IDE giúp tránh mỗi thành viên ghi cùng một file bằng charset khác nhau, nhưng không thay thế compiler/build configuration.

### 7.1. EditorConfig

Tạo file `.editorconfig` ở thư mục gốc dự án:

```ini
root = true

[*]
charset = utf-8
```

Editor hỗ trợ EditorConfig sẽ dùng UTF-8 khi mở/lưu file phù hợp. Nếu IDE hoặc editor không hỗ trợ, cấu hình này không tự thay đổi cách lưu file; hãy kiểm tra trạng thái hỗ trợ và encoding hiển thị trên thanh trạng thái.

Có thể mở rộng theo loại file khi dự án có ngoại lệ được tài liệu hóa, nhưng không khai báo charset legacy chỉ vì một máy phát triển đang có locale cũ. Nếu một file thực sự dùng encoding khác, ghi nhận rõ lý do và chỉ giới hạn ngoại lệ ở đúng nhóm file đó.

### 7.2. IntelliJ IDEA

Trong IntelliJ IDEA, kiểm tra **Settings | Editor | File Encodings**:

- Đặt **Global Encoding** theo chuẩn làm việc của nhóm nếu cần.
- Đặt **Project Encoding** là UTF-8.
- Kiểm tra **Default encoding for properties files** theo định dạng properties mà dự án đã chọn.
- Với file có encoding riêng, xem encoding hiển thị ở status bar và chỉ chuyển đổi khi đã xác nhận byte/nội dung hiện tại.

### 7.3. Eclipse

Trong Eclipse, kiểm tra:

- **Window | Preferences | General | Workspace | Text file encoding** để đặt mặc định workspace.
- **Project | Properties | Resource | Text file encoding** để đặt riêng cho dự án.
- Nếu một file riêng có encoding khác, kiểm tra thuộc tính resource của file đó.

### 7.4. Visual Studio Code và editor khác

Trong VS Code, có thể đặt mặc định trong workspace settings:

```json
{
    "files.encoding": "utf8"
}
```

Nếu dự án dùng EditorConfig, hãy xác nhận editor đã nạp quy tắc đó. Với mọi IDE, mở một file chứa tiếng Việt và emoji, xem encoding đang được nhận diện, lưu lại rồi kiểm tra byte bằng công cụ hex nếu có nghi ngờ.

## 8. Kiểm tra source và resource bằng cùng một fixture

Một fixture nhỏ giúp kiểm tra hai đường đi độc lập:

- Chuỗi literal trong `.java` kiểm tra compiler đã đọc source đúng.
- Resource `messages.txt` kiểm tra resource có được giữ đúng qua build và runtime có đọc đúng charset.

Giả sử resource chứa một dòng:

```text
Tiếng Việt | café | € | 🚀
```

Chương trình kiểm tra:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class EncodingContractCheck {
    private static final String SOURCE_LITERAL =
            "Tiếng Việt | café | € | 🚀";

    // Expected chỉ dùng Unicode escape ASCII, độc lập với encoding của source.
    private static final String EXPECTED =
            "Ti\u1EBFng Vi\u1EC7t | caf\u00E9 | \u20AC | \uD83D\uDE80";

    public static void main(String[] args) throws Exception {
        if (!SOURCE_LITERAL.equals(EXPECTED)) {
            throw new AssertionError("Compiler đọc source literal sai");
        }

        byte[] expectedBytes = (EXPECTED + "\n")
                .getBytes(StandardCharsets.UTF_8);

        byte[] resourceBytes;
        try (InputStream input = EncodingContractCheck.class
                .getResourceAsStream("/messages.txt")) {
            if (input == null) {
                throw new IOException("Không tìm thấy /messages.txt");
            }
            resourceBytes = input.readAllBytes();
        }

        if (!Arrays.equals(expectedBytes, resourceBytes)) {
            throw new AssertionError("Byte resource khác UTF-8 kỳ vọng");
        }

        String resourceText = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(resourceBytes))
                .toString();

        if (!resourceText.equals(EXPECTED + "\n")) {
            throw new AssertionError("Resource sau decode không khớp");
        }

        System.out.println("SOURCE_LITERAL=PASS");
        System.out.println("RESOURCE_BYTES=PASS");
        System.out.println("RESOURCE_UTF8_DECODE=PASS");
    }
}
```

Chương trình kiểm tra:

1. Compiler đã tạo literal có đúng nội dung mong đợi. Giá trị đối chiếu dùng Unicode escape ASCII nên không phụ thuộc cách compiler đọc ký tự ngoài ASCII trong file.
2. Byte resource sau build giống chính xác byte UTF-8 của fixture.
3. Resource giải mã bằng UTF-8 strict và giữ đúng nội dung, kể cả newline cuối dòng.

Đặt `EncodingContractCheck.java` trong source set test hoặc một source set kiểm tra riêng; đặt `messages.txt` trong resource root tương ứng. Khi chạy test, classpath phải chứa resource đã được build. Nếu build có resource filtering, hãy kiểm tra file ở output directory/JAR vì byte sau filtering mới là dữ liệu runtime nhận được.

## 9. Checklist cho build local và CI

| Điểm kiểm tra | Cách xác nhận | Kết quả mong đợi |
| --- | --- | --- |
| Source file | IDE/EditorConfig và byte file | `.java` được lưu UTF-8 |
| Compiler | `javac -encoding UTF-8`, Maven hoặc Gradle config | Source được giải mã bằng UTF-8 |
| Resource source | Hex viewer hoặc strict decoder | Byte đúng theo định dạng đã khai báo |
| Resource filtering | Cấu hình plugin/task và output sau build | Filtering dùng UTF-8; binary không bị filter |
| Runtime reader | Kiểm tra overload/constructor | Charset được truyền tường minh |
| Properties | Kiểm tra `load(InputStream)` hay `load(Reader)` | Charset phù hợp quy tắc API |
| IDE dự án | Project encoding và file encoding | Thành viên dùng cùng quy tắc lưu file |
| CI | Chạy compile/test trên môi trường sạch | Kết quả không phụ thuộc locale máy cá nhân |

Một pipeline CI nên chạy build từ checkout mới, không dùng class file hoặc resource output cũ. Điều đó giúp phát hiện source/resource đã bị sửa encoding trên máy lập trình viên nhưng chưa được commit đúng.

Git lưu và so sánh nội dung file dưới dạng byte; nó không tự chuyển mọi file văn bản sang UTF-8. `.editorconfig` hướng dẫn editor, còn compiler và build plugin mới là nơi quy định cách đọc source/resource trong build. Nếu cần chuẩn hóa line ending, cấu hình riêng qua `.gitattributes`; line ending và charset là hai vấn đề khác nhau.

## 10. Bài thực hành và tiêu chí hoàn thành

1. Tạo source file có literal tiếng Việt, `é`, `€` và emoji; lưu bằng UTF-8.
2. Compile bằng `javac -encoding UTF-8` và xác nhận chương trình in code point/literal đúng.
3. Cấu hình Maven Compiler Plugin hoặc Gradle `JavaCompile` dùng UTF-8; chạy build từ terminal và CI.
4. Tạo resource `messages.txt` chứa cùng nội dung; đặt vào resource root và kiểm tra byte trong output directory hoặc JAR.
5. Nếu có resource filtering, khai báo UTF-8 trong Maven Resources Plugin hoặc Gradle `ProcessResources`; xác nhận resource sau filter vẫn đúng byte.
6. Đọc resource bằng `InputStreamReader(..., UTF_8)` hoặc decoder strict; không dựa vào default charset.
7. Nếu dùng `.properties`, so sánh `Properties.load(InputStream)` với `Properties.load(Reader)` được tạo bằng UTF-8.
8. Thêm `.editorconfig`, cấu hình project encoding của IDE và mở/lưu lại fixture trên ít nhất hai môi trường phát triển.
9. Chạy `EncodingContractCheck` trong build để xác nhận source literal, resource bytes và kết quả decode.

**Tiêu chí hoàn thành:** bạn cấu hình được UTF-8 cho source/compiler, resource filtering, runtime reader và IDE; phân biệt được resource copy nguyên byte với resource filtering; xử lý đúng `.properties`; và có fixture tự động phát hiện source hoặc resource bị đọc/ghi sai encoding. Đây là cách giữ hợp đồng UTF-8 nhất quán trên JDK hiện đại, kể cả khi JEP 400 đã đặt UTF-8 làm default charset của runtime.

### Tài liệu tham khảo

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): phạm vi UTF-8 mặc định của JDK 18+.
- [Java javac documentation](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): tùy chọn `-encoding` của compiler.
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html): cấu hình encoding khi compile source.
- [Maven Resources Plugin](https://maven.apache.org/plugins/maven-resources-plugin/resources-mojo.html): `encoding`, `propertiesEncoding` và resource filtering.
- [Gradle JavaCompile](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.JavaCompile.html): `options.encoding`.
- [Gradle ProcessResources](https://docs.gradle.org/current/dsl/org.gradle.language.jvm.tasks.ProcessResources.html): xử lý resource trong build.
- [EditorConfig](https://editorconfig.org/): quy tắc `charset = utf-8` dùng chung cho editor.
- [Java Properties](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Properties.html): khác biệt giữa API đọc từ `InputStream` và `Reader`.
