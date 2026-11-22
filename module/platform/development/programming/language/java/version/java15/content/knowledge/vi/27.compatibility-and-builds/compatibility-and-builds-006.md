# Tài nguyên văn bản, charset và line ending trong build Java 15+

## 1. Vấn đề và mục tiêu

Một chương trình Java có thể biên dịch đúng trên máy lập trình nhưng sau khi chạy trong CI hoặc đóng JAR lại gặp những lỗi khó hiểu:

- `messages.properties` chứa tiếng Việt nhưng khi đọc xuất hiện `ChÃ o` hoặc ký tự thay thế.
- Test so file thất bại trên Windows vì `CRLF` thay cho `LF`.
- Resource tìm thấy trong IDE nhưng `getResourceAsStream(...)` trả `null` khi chạy file JAR.
- Một file JSON/template thay đổi sau khi Maven hoặc Gradle xử lý resources.
- Hai bản build từ cùng source tạo bytes resource khác nhau, dù nội dung nhìn bằng mắt vẫn giống nhau.
- Java 15 và JDK mới có cách dùng **default charset** khác nhau ở những API không chỉ định encoding.

**Chủ đề trực tiếp:** cách phối hợp **tài nguyên văn bản, charset và line ending trong build**, đảm bảo source code, resources, classpath JAR và runtime sử dụng cùng hợp đồng dữ liệu.

Sau bài, bạn có thể xác định:
1. Encoding nào áp dụng cho **mã nguồn**, encoding nào áp dụng cho **file resource**, encoding nào được chọn **khi đọc runtime**.
2. Cách điều khiển `javac -encoding UTF-8 --release 15`, Maven và Gradle mà không lẫn compile với resource filtering.
3. Sự khác nhau giữa LF, CRLF, CR, BOM, final newline và Unicode normalization.
4. Cách kiểm soát line endings bằng `.gitattributes`, bảo vệ fixture **byte-exact**.
5. Cách đọc resources trong JAR bằng classpath, phân biệt các dạng đường dẫn.
6. Vì sao `Properties.load(InputStream)` không giống `Properties.load(Reader UTF-8)` hoặc `ResourceBundle`.
7. Cách kiểm thử bằng một chương trình Java 15 thực sự biên dịch, đóng JAR và chạy được.

**Special Note áp dụng:** Chỉ dùng những nguyên tắc/API còn phù hợp với Java và build tools hiện nay. Khi có thay đổi giữa Java 15 và JDK mới, bài chỉ rõ thay vì khuyên dùng cách xử lý đã lỗi thời.

## 2. Bốn tầng encoding/EOL của một project

```text
src/main/java/demo/App.java       --[javac -encoding]---> App.class
src/main/resources/demo/a.txt     --[copy/filter]--------> demo/a.txt
                    |                |
               Git checkout     Maven/Gradle processing
                    +----------------+
                             |
                         JAR archive
                             |
                    Class.getResourceAsStream
                             |
                     bytes --> UTF-8 decoder
                             |
                       Java String
```

| Tầng | Điều cần quy định | Sự cố phổ biến |
| --- | --- | --- |
| Source Java | Encoding của `.java` khi compiler đọc | Ký tự trong string literal biến dạng hoặc compile fail |
| Resource source | Bytes, charset, EOL và BOM của `.txt/.properties/.json` | File đã sai trước khi build |
| Build processing | Copy raw hay filter/expand, charset, include/exclude | Placeholder bị thay ngoài ý muốn; bytes thay đổi |
| Runtime | Classpath path và charset decoder/Properties API | Không tìm thấy resource hoặc mojibake |

**Không có một flag duy nhất làm đúng cả bốn tầng.** `javac -encoding UTF-8` chỉ quyết định cách compiler đọc mã nguồn; nó **không chuyển toàn bộ `src/main/resources` sang UTF-8**. Còn một file là UTF-8 không nói nó đang dùng LF hay CRLF.

Một pipeline có thể hoàn toàn đúng khi dùng resource CRLF (giao thức yêu cầu CRLF) hoặc resource binary, miễn hợp đồng được xác định và kiểm thử. Mục tiêu không phải ép mọi bytes về một dạng bất kể ngữ cảnh.

## 3. Charset của Java source: Java 15 và các JDK hiện đại

### 3.1. Compile source rõ ràng

```bash
javac --release 15 -encoding UTF-8 -d out src/main/java/demo/BuildTextResourcesDemo.java
```

- `--release 15` yêu cầu cú pháp, public API và bytecode target tương ứng Java 15. Nó không chỉ là cờ version hiển thị.
- `-encoding UTF-8` quy định compiler đọc file `.java` dưới dạng UTF-8.
- `-d out` ghi class files tới thư mục output.

Nếu editor lưu source theo một bảng mã khác với compiler, mã nguồn có dấu có thể lỗi ngay khi compile hoặc tạo literal không đúng. Đảm bảo editor/repo đặt UTF-8; trên CI luôn compile với một hợp đồng rõ.

### 3.2. Default charset thay đổi từ JDK 18 (JEP 400)

- **Java 15/JDK 17 trở xuống:** default charset ở nhiều APIs có thể phụ thuộc OS/locale/code page.
- **JDK 18+ (JEP 400):** UTF-8 là default charset của Java SE APIs sử dụng default, với các cơ chế tương thích được mô tả riêng.
- **Khuyến nghị không lỗi thời:** với file/protocol bắt buộc UTF-8, truyền `StandardCharsets.UTF_8` trực tiếp, đặc biệt khi phần mềm còn hỗ trợ nhiều JDK/OS.

Ví dụ:

```java
try (InputStream in = ...;
     Reader reader = new InputStreamReader(in, StandardCharsets.UTF_8)) {
    // Reader biến UTF-8 bytes thành Java characters.
}
```

Đây là **mã minh họa trong một phương thức**, cần stream hợp lệ và các import `java.io.*`, `java.nio.charset.StandardCharsets`.

**Ngoại lệ quan trọng:** `Files.readString(path)` và `Files.writeString(path,text)` đã mặc định **UTF-8 theo API từ Java 11**, không dùng default charset tùy OS. Vì vậy không thể nói “mọi method không có tham số Charset đều phụ thuộc default”. Tốt nhất vẫn ghi rõ `Files.readString(path, StandardCharsets.UTF_8)` khi yêu cầu readability.

### 3.3. Số ký tự không bằng số bytes

```java
String message = "Cà phê ☕";
byte[] encoded = message.getBytes(StandardCharsets.UTF_8);
int utf16Units = message.length();
int utf8Bytes = encoded.length;
```

Đoạn này nằm trong một phương thức; `String.length()` trả số đơn vị UTF-16, trong khi `encoded.length` trả số byte UTF-8. Khi giới hạn payload/file/protocol, dùng **bytes thực** chứ không lấy length của String rồi suy thành byte count.

## 4. Ranh giới dòng: LF, CRLF và CR

| Kết thúc dòng | Java escape | Hex bytes của UTF-8 | Ví dụ |
| --- | --- | --- | --- |
| LF | `\n` | `0A` | Phổ biến trong repository và Unix |
| CRLF | `\r\n` | `0D 0A` | Phổ biến ở nhiều file Windows và giao thức cụ thể |
| CR | `\r` | `0D` | Một số dữ liệu/fixture hoặc legacy format |

Một file UTF-8 vẫn có thể chứa cả ba dạng. Hai file:

```text
A\nB\n
A\r\nB\r\n
```

có thể trông giống nhau trong editor, nhưng raw bytes khác, SHA-256 khác và độ dài bytes khác. Đặc biệt khi dữ liệu được **ký số/hash**, đổi newline khiến chữ ký/hash sai.

### 4.1. Java nhận biết line endings nhưng không nhất thiết bảo toàn chúng

`String.lines()` từ Java 11 phân tách dòng dựa vào **LF, CRLF và CR** và trả phần nội dung **không chứa terminator**. Ví dụ:

```java
String mixed = "A\r\nB\nC\r";
System.out.println(mixed.lines().count()); // 3
```

`BufferedReader.readLine()` cũng đọc nội dung dòng thay vì giữ nguyên terminator. Vì vậy, hai file khác EOL có thể cho cùng danh sách dòng. Nếu cần xác minh EOL cụ thể, phải kiểm tra raw bytes hoặc String trước khi tách dòng.

### 4.2. Normalize đúng thứ tự và chỉ khi được phép

```java
String canonical = original
        .replace("\r\n", "\n")
        .replace("\r", "\n");
byte[] canonicalBytes = canonical.getBytes(StandardCharsets.UTF_8);
```

Đây là snippet với `String original`. **Thay CRLF trước CR** để tránh vô tình biến `\r\n` thành hai `\n`. Có thể lựa chọn LF làm canonical EOL cho README/config/JSON của một dự án nếu format cho phép.

**Không được tự normalize**:
- Test fixture muốn chứng minh CRLF được xử lý đúng.
- Wire protocol thực sự yêu cầu CRLF.
- Files đang được so raw hash/signature.
- Dữ liệu cần bảo toàn nguyên văn hoặc có ràng buộc pháp lý/byte-for-byte.

Nếu muốn tạo file theo chuẩn OS, `System.lineSeparator()` có ý nghĩa; nhưng đối với artifact reproducible hoặc format quy định LF, hãy ghi LF trực tiếp. Cũng cần quyết định **file có newline cuối hay không**: `"A"` và `"A\n"` là hai byte sequences khác nhau.

## 5. Git .gitattributes: chính sách EOL không phải chính sách charset

Ví dụ một repository đa hệ điều hành:

```gitattributes
* text=auto

*.java       text eol=lf
*.kt         text eol=lf
*.kts        text eol=lf
*.properties text eol=lf
*.xml        text eol=lf
*.md         text eol=lf
*.sh         text eol=lf
*.bat        text eol=crlf
*.cmd        text eol=crlf

*.png        -text
*.jar        -text
test-fixtures/required-crlf.dat -text
```

- `text eol=lf` điều khiển **end-of-line conversion** của tracked text khi đi giữa Git index và working tree.
- `-text` bảo Git **không chuyển đổi** EOL của file; dùng cho binary và những fixtures cần bytes chính xác.
- `text=auto` cho Git nhận diện text/binary, không đủ bảo đảm mọi file đặc biệt được giữ nguyên.
- `core.autocrlf`/`core.eol` của người dùng vẫn có tác động khi không có rule cụ thể.
- **`.gitattributes` không tự transcode file sang UTF-8**. Charset là hợp đồng khác.

Kiểm tra:

```bash
git check-attr text eol -- src/main/resources/demo/message.txt
git ls-files --eol
git diff --check
```

**Điểm dễ mắc:** Nếu test cần file CRLF nhưng bạn đặt `*.txt text eol=lf`, Git có thể chuẩn hóa file đó theo LF khi checkout. Đặt ngoại lệ cụ thể `-text` cho fixture, hoặc lưu test dưới dạng bytes được dựng bởi chương trình.

Thay đổi .gitattributes cho repository đã có lịch sử cần được review riêng; `git add --renormalize .` có thể được dùng sau khi kiểm tra chính sách, nhưng không chạy mù vì có thể sửa rất nhiều file hoặc fixtures không nên bị đổi.

## 6. Resource và classpath: IDE đúng chưa chắc JAR đúng

### 6.1. Layout project thông dụng

```text
project/
  src/main/java/demo/BuildTextResourcesDemo.java
  src/main/resources/demo/message.txt
  src/main/resources/demo/labels.properties
```

Sau build, JAR cần chứa các entry:

```text
demo/BuildTextResourcesDemo.class
demo/message.txt
demo/labels.properties
```

Đừng dùng `Path.of("src/main/resources/demo/message.txt")` trong production để đọc resource. Đường dẫn đó chỉ có thể tồn tại khi current working directory là project root. Sau triển khai JAR, file nguồn không nhất thiết còn nằm trên máy.

### 6.2. Class.getResourceAsStream và ClassLoader.getResourceAsStream

```java
try (InputStream in = BuildTextResourcesDemo.class
        .getResourceAsStream("message.txt")) {
    if (in == null) {
        throw new IOException("Missing classpath resource");
    }
    byte[] raw = in.readAllBytes();
}
```

Đoạn code nằm trong method của class ở package `demo` và cần imports `java.io.*`. Quy tắc:

| API | Path | Chỉ tới |
| --- | --- | --- |
| `Demo.class.getResourceAsStream("message.txt")` | Không có slash đầu | `demo/message.txt` vì relative to package |
| `Demo.class.getResourceAsStream("/demo/message.txt")` | Slash đầu | `demo/message.txt` từ classpath root |
| `Demo.class.getClassLoader().getResourceAsStream("demo/message.txt")` | Không có slash đầu | `demo/message.txt` từ classloader root |

**Luôn kiểm tra `null`** nếu resource thiếu. Không biến một resource bị bỏ khỏi build thành `NullPointerException` khó hiểu trong logic nghiệp vụ.

Trong JAR, resource có URL dạng `jar:file:...!/demo/message.txt` hoặc tương đương. Đừng mặc định `Paths.get(resourceUrl.toURI())` hoạt động như file thường; `getResourceAsStream` thích hợp để đọc nội dung mà không quan tâm resource nằm trong thư mục hay archive.

### 6.3. Kiểm tra file JAR thật

```bash
jar --list --file demo.jar
java -cp demo.jar demo.BuildTextResourcesDemo
```

Bước đầu kiểm tra tên entry; bước sau kiểm tra classloader thực sự đọc được file. Nếu dùng Maven/Gradle, cần test final JAR thay vì chỉ chạy code trong IDE.

## 7. UTF-8 BOM, strict decoding và Unicode normalization

### 7.1. UTF-8 BOM không bắt buộc

Ba byte đầu `EF BB BF` biểu diễn UTF-8 BOM. Nhiều format UTF-8 **không yêu cầu** BOM, nhưng một số editor/tool có thể thêm nó. Khi decode, U+FEFF có thể xuất hiện ở đầu String và làm khóa config không khớp.

```java
boolean bom = data.length >= 3
        && (data[0] & 0xFF) == 0xEF
        && (data[1] & 0xFF) == 0xBB
        && (data[2] & 0xFF) == 0xBF;
```

Đây là snippet với `byte[] data`. Nếu format cấm BOM, hãy kiểm tra ở **raw bytes**, fail fast hoặc strip chính xác prefix theo hợp đồng; không dùng `trim()` hoặc `strip()` để tự động “sửa” dữ liệu.

### 7.2. Decode strict thay vì thay lỗi bằng `�`

```java
String text = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(raw))
        .toString();
```

Code nằm trong method có imports `java.nio.*` và `java.nio.charset.*`, biến `raw` hợp lệ và xử lý `CharacterCodingException`. Đây là lựa chọn tốt cho text config, fixture và dữ liệu protocol cần tính đúng đắn. `new String(bytes, UTF_8)` có thể thay bytes lỗi bằng replacement character nên không luôn phù hợp cho kiểm tra.

### 7.3. Unicode NFC/NFD khác EOL

Hai chuỗi tiếng Việt có thể trông giống nhưng dùng precomposed/combining Unicode code points khác nhau, kéo theo UTF-8 bytes khác. Nếu business contract yêu cầu canonical Unicode, chọn chính sách và dùng:

```java
String canonical = java.text.Normalizer.normalize(
        value, java.text.Normalizer.Form.NFC);
```

Đây là phép biến đổi **khác** chuẩn hóa LF/CRLF. Đối với nội dung cần signature/hash, hai phía phải áp dụng quy tắc normalization **trước** khi ký; không tự sửa một phía sau đó.

## 8. .properties: cùng tên file, ba cách đọc khác nhau

Đây là nguồn gốc phổ biến của lỗi tiếng Việt sau build.

### 8.1. Properties.load(InputStream): ISO-8859-1

`java.util.Properties.load(InputStream)` giải mã bytes bằng **ISO-8859-1 theo hợp đồng Javadoc**, kể cả khi JVM default charset là UTF-8. Những ký tự Unicode ngoài Latin-1 cần escape theo syntax properties nếu chọn overload này.

Với UTF-8 thô:

```properties
message=Chào Việt Nam
```

đọc bằng `load(InputStream)` có thể tạo mojibake. Đây không phải bug Java hoặc vấn đề LF.

### 8.2. Properties.load(Reader): charset của Reader

```java
Properties props = new Properties();
try (InputStream in = MyClass.class
        .getResourceAsStream("/demo/labels.properties")) {
    if (in == null) {
        throw new IOException("Missing labels.properties");
    }
    try (Reader r = new InputStreamReader(in, StandardCharsets.UTF_8)) {
        props.load(r);
    }
}
```

Đây là snippet trong method thích hợp (cần imports `java.io.*`, `java.util.*`, `java.nio.charset.StandardCharsets`). `Reader` đã decode UTF-8 nên `Properties` nhận Unicode text đúng. Dĩ nhiên vẫn phải tôn trọng grammar của properties (backslash, separator, comment, continuation).

### 8.3. ResourceBundle / PropertyResourceBundle từ Java 9+

Với `ResourceBundle.getBundle("demo.labels", Locale.ROOT)`, file `demo/labels.properties` được đọc **UTF-8 theo mặc định** từ Java 9 và có **fallback ISO-8859-1** khi gặp malformed/unmappable UTF-8 theo Javadoc.

Nếu cần strict UTF-8 không fallback, `java.util.PropertyResourceBundle.encoding=UTF-8` là một system property được hỗ trợ, cần được thiết lập **trước khi class được khởi tạo**; không kỳ vọng thay đổi property lúc runtime sẽ đổi behavior đã init.

| API | Charset đọc .properties | UTF-8 có dấu |
| --- | --- | --- |
| `Properties.load(InputStream)` | ISO-8859-1 | Không trực tiếp phù hợp |
| `Properties.load(Reader UTF-8)` | UTF-8 | Phù hợp |
| `ResourceBundle/PropertyResourceBundle` | UTF-8 mặc định Java 9+, có fallback | Phù hợp với UTF-8 hợp lệ |

**Không nên nói** “mọi .properties của Java bắt buộc Latin-1” hoặc “mọi .properties của Java giờ tự UTF-8”. Phải phân biệt API và overload.

## 9. Maven: sourceEncoding, release và filtering resources

### 9.1. Mẫu POM liên quan Java 15

Đoạn bên trong `<project>` của `pom.xml`:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>15</maven.compiler.release>
</properties>

<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
    </resources>
</build>
```

- `project.build.sourceEncoding` là cấu hình phổ biến cho compiler/resources plugins.
- `maven.compiler.release=15` giới hạn cú pháp, API, bytecode theo Java 15 (khi plugin/JDK hỗ trợ).
- `filtering=false` yêu cầu **không làm text token expansion** trên vùng resources này.
- **Copy không filtering không đồng nghĩa tự normalize CRLF thành LF**: resource source có bytes nào còn phụ thuộc Git checkout/editor. Cần policy EOL và test.

### 9.2. Filtering chỉ những file template có chủ đích

Nếu cần file build-info được nội suy:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
        <resource>
            <directory>src/main/filtered-resources</directory>
            <filtering>true</filtering>
            <includes><include>**/*.properties</include></includes>
        </resource>
    </resources>
</build>
```

Đây là **mẫu thay thế cho block build ở trên**, không phải hai block `<build>` cùng tồn tại trong một POM. File có placeholder nên ở folder riêng; các fixtures, ảnh, JSON/template dùng syntax tương tự và files đòi hash byte-exact không được filter bừa.

Maven Resources Plugin hỗ trợ `encoding` cho filtered text và với các phiên bản có tính năng đó còn có `propertiesEncoding` (từ 3.2.0) dành cho filtered .properties. Chọn phiên bản plugin phù hợp JDK/Maven đang dùng, đặt encoding UTF-8 rõ ràng, không suy rằng `-encoding` của javac sẽ điều khiển plugin resources.

Nếu dùng template `${project.version}` hoặc `@project.version@`, filtering có thể thay nó; nếu cú pháp đó là **literal của ứng dụng** chứ không phải build variable, cần escape/tách khỏi vùng filter.

### 9.3. Kiểm chứng output Maven

```bash
mvn process-resources
# Đọc target/classes/demo/message.txt rồi so bytes với expected.
mvn package
jar --list --file target/your-artifact.jar
```

Tên `your-artifact.jar` ở đây là **ví dụ đường dẫn cần thay bằng tên artifact thực tế**, không phải file demo có sẵn. Không đưa binary vào filtering. Nếu resource không thay đổi theo contract, so SHA-256 của **source file, copied file và JAR entry**.

## 10. Gradle: JavaCompile và ProcessResources

Với Gradle Kotlin DSL `build.gradle.kts` dùng Java plugin, có thể cấu hình rõ:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(15)
}

val versionLabel = version.toString()

tasks.processResources {
    filteringCharset = "UTF-8"
    filesMatching("**/build-info.properties") {
        expand(mapOf("buildVersion" to versionLabel))
    }
}
```

Đây là **cấu hình minh họa**, cần Gradle version hỗ trợ và toolchain đã cài. Nó cho thấy:
- `options.encoding` áp dụng cho source Java.
- `options.release.set(15)` target Java SE 15, dù toolchain đang dùng JDK 21.
- `filteringCharset` áp dụng cho **text filtering** trong `CopySpec/ProcessResources`.
- `filesMatching` hạn chế expand vào đúng `build-info.properties`; không biến tất cả resources thành template.
- `expand` có thể xử lý placeholder kiểu Groovy `${buildVersion}`, nên không chạy trên resource chưa tin cậy hoặc file cần giữ nguyên literal syntax.

Theo Gradle docs hiện hành, khi không khai báo `filteringCharset`, filter dùng JVM default charset của môi trường build. Vì thế Java 15/JDK 17 có thể khác JDK 18+; khai báo rõ giúp nhất quán.

**Không nhầm:** việc `processResources` copy resource không có nghĩa nó được phép đổi line endings khi bạn chỉ muốn copy bytes. Nếu cần transform EOL, hãy thêm một bước **có chủ đích**, không lạm dụng filter cả thư mục.

## 11. Chương trình Java 15 hoàn chỉnh: EOL, UTF-8 và Properties

### 11.1. Các file đầu vào

```text
src/main/java/demo/BuildTextResourcesDemo.java
src/main/resources/demo/message.txt
src/main/resources/demo/labels.properties
```

Fixture `message.txt` được **cố ý** tạo ở UTF-8 no BOM với nội dung:

```text
"Cà phê ☕" + CRLF + "Dòng 2" + LF + "Dòng 3" + CR
```

Tức là ba dạng EOL ở ba vị trí khác nhau. File `labels.properties` là UTF-8 no BOM chứa `message=Chào Việt Nam` và LF cuối file.

Để không phụ thuộc vào editor, trên PowerShell 5.1+ có thể tạo fixture như sau (chạy ở project root):

```powershell
New-Item -ItemType Directory -Force "src/main/resources/demo" | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)
$text = "Cà phê ☕" + [char]13 + [char]10 + "Dòng 2" + [char]10 + "Dòng 3" + [char]13
[System.IO.File]::WriteAllText("src/main/resources/demo/message.txt", $text, $utf8)
[System.IO.File]::WriteAllText("src/main/resources/demo/labels.properties", "message=Chào Việt Nam" + [char]10, $utf8)
```

Nếu fixture này được commit vào Git, cần thêm rule riêng `-text` để giữ nguyên bytes; nếu `*.txt text eol=lf` ghi đè nó, test không còn kiểm tra CRLF nữa.

### 11.2. Source chạy độc lập

Lưu đúng tên `src/main/java/demo/BuildTextResourcesDemo.java`:

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Locale;
import java.util.Properties;
import java.util.ResourceBundle;

public final class BuildTextResourcesDemo {
    private static byte[] resource(String relativeName) throws IOException {
        try (InputStream in = BuildTextResourcesDemo.class.getResourceAsStream(
                relativeName)) {
            if (in == null) {
                throw new IOException("Missing classpath resource: " + relativeName);
            }
            return in.readAllBytes();
        }
    }

    private static String strictUtf8(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes)).toString();
    }

    public static void main(String[] args) throws Exception {
        byte[] raw = resource("message.txt");
        String text = strictUtf8(raw);
        String expected = "Cà phê ☕\r\nDòng 2\nDòng 3\r";
        System.out.println("resource decoded exactly: " + text.equals(expected));

        boolean hasUtf8Bom = raw.length >= 3 &&
                (raw[0] & 255) == 0xEF &&
                (raw[1] & 255) == 0xBB &&
                (raw[2] & 255) == 0xBF;
        System.out.println("UTF-8 BOM present: " + hasUtf8Bom);

        int crlf = 0, lf = 0, cr = 0;
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (c == '\r') {
                if (i + 1 < text.length() && text.charAt(i + 1) == '\n') {
                    crlf++;
                    i++;
                } else {
                    cr++;
                }
            } else if (c == '\n') {
                lf++;
            }
        }
        System.out.println("line endings CRLF/LF/CR: "
                + crlf + "/" + lf + "/" + cr);
        System.out.println("String.lines count: " + text.lines().count());

        String normalized = text.replace("\r\n", "\n").replace("\r", "\n");
        System.out.println("normalized LF only: " +
                (!normalized.contains("\r")));
        System.out.println("normalized final LF: " +
                normalized.endsWith("\n"));
        System.out.println("raw vs normalized SHA-256 differ: " +
                !Arrays.equals(MessageDigest.getInstance("SHA-256")
                        .digest(raw), MessageDigest.getInstance("SHA-256")
                        .digest(normalized.getBytes(StandardCharsets.UTF_8))));

        Properties propsUtf8 = new Properties();
        try (InputStream in = BuildTextResourcesDemo.class.getResourceAsStream(
                "/demo/labels.properties");
             Reader reader = new InputStreamReader(in, StandardCharsets.UTF_8)) {
            propsUtf8.load(reader);
        }
        Properties propsByte = new Properties();
        try (InputStream in = BuildTextResourcesDemo.class.getResourceAsStream(
                "/demo/labels.properties")) {
            propsByte.load(in);
        }
        String expectedLabel = "Chào Việt Nam";
        System.out.println("Properties Reader UTF-8 correct: " +
                expectedLabel.equals(propsUtf8.getProperty("message")));
        System.out.println("Properties InputStream UTF-8 correct: " +
                expectedLabel.equals(propsByte.getProperty("message")));
        ResourceBundle bundle = ResourceBundle.getBundle("demo.labels", Locale.ROOT);
        System.out.println("ResourceBundle value correct: " +
                expectedLabel.equals(bundle.getString("message")));
    }
}
```

Trong chương trình, helper `resource("message.txt")` đã kiểm tra `null`. Hai stream đọc labels giả định file được đóng gói theo bài thử. **Trong production phải kiểm tra null cho cả labels**, thay vì để `InputStreamReader`/`Properties.load` ném NPE khi resource thiếu.

### 11.3. Compile, copy và chạy từ JAR

Trên Linux/macOS shell:

```bash
mkdir -p out
javac --release 15 -encoding UTF-8 \
  -d out src/main/java/demo/BuildTextResourcesDemo.java
cp -R src/main/resources/. out/
java -cp out demo.BuildTextResourcesDemo

jar --create --file demo.jar -C out .
jar --list --file demo.jar
java -cp demo.jar demo.BuildTextResourcesDemo
```

Trên PowerShell, sau khi chuẩn bị fixture:

```powershell
New-Item -ItemType Directory -Force "out" | Out-Null
javac --release 15 -encoding UTF-8 -d out "src/main/java/demo/BuildTextResourcesDemo.java"
Copy-Item "src/main/resources/*" -Destination "out" -Recurse -Force
jar --create --file demo.jar -C out .
jar --list --file demo.jar
java -cp demo.jar demo.BuildTextResourcesDemo
```

**Đã kiểm thử thực tế** với `javac --release 15 -encoding UTF-8`, tạo JAR và chạy bằng **OpenJDK 24.0.2**. Cả run từ classes directory và từ JAR cho cùng **10 dòng stdout chính xác**:

```text
resource decoded exactly: true
UTF-8 BOM present: false
line endings CRLF/LF/CR: 1/1/1
String.lines count: 3
normalized LF only: true
normalized final LF: true
raw vs normalized SHA-256 differ: true
Properties Reader UTF-8 correct: true
Properties InputStream UTF-8 correct: false
ResourceBundle value correct: true
```

Các dòng trên chứng minh:
- UTF-8 resource được đọc đúng, không có BOM.
- CRLF, LF và CR được đếm riêng; `String.lines()` vẫn thấy 3 dòng.
- Chuẩn hóa EOL đổi hash của raw bytes.
- `Properties.load(Reader UTF-8)` đọc đúng tiếng Việt; `Properties.load(InputStream)` không đọc UTF-8 thô theo cùng cách.
- `ResourceBundle` Java 9+ đọc bundle UTF-8 hợp lệ.
- Classpath resources tồn tại và hoạt động khi chạy từ JAR.

**Giới hạn thử nghiệm:** Mã Java và JAR đã chạy; các đoạn Maven/Gradle là **mẫu cấu hình cần kiểm tra với build tool/version thật của dự án**, không được coi đã thử mọi plugin/OS. Console hiển thị Unicode cũng phụ thuộc terminal encoding, khác với bytes trong resource.

## 12. Text blocks Java 15 không thay thế resource files

Text blocks (ba dấu nháy kép) là tính năng Java chính thức từ **Java 15**:

```java
String query = """
        SELECT id, name
        FROM products
        WHERE active = true
        """;
```

Compiler có quy tắc riêng về incidental indentation và line terminators của text blocks. **Những quy tắc đó không tự áp dụng cho resource file** được copy từ `src/main/resources`: resource vẫn là bytes do Git và build tool xử lý.

Chọn text blocks nếu literal nhỏ, cố định và gắn với code. Chọn classpath resources nếu cần file config, localized messages, fixtures, hoặc muốn kiểm soát raw bytes độc lập. Đừng dùng text block như một mẹo “tự động sửa encoding” của cả dự án.

## 13. Reproducible build: kiểm tra resource entry chứ không chỉ JAR hash

Cùng source có thể cho JAR khác vì **timestamps, thứ tự entries, zip metadata, generated version/time, plugin/JDK version** hoặc resource transformation. Ngoài ra, một Git checkout Windows có CRLF và một checkout Linux có LF sẽ khiến cùng file text hiển thị tương tự nhưng bytes khác.

Hai cấp kiểm thử:
1. **Bytes của từng resource**: nếu file không được filter, so SHA-256 source → build output → JAR entry; nếu được filter có chủ đích, so với **expected generated bytes**.
2. **Reproducible toàn artifact**: cần thêm cấu hình archive metadata/timestamp và toolchain ổn định. Hash của một JAR không giải thích riêng resource nào bị đổi.

Có thể đọc một entry bằng Java:

```java
try (java.util.jar.JarFile jar =
        new java.util.jar.JarFile("demo.jar")) {
    java.util.jar.JarEntry entry =
            jar.getJarEntry("demo/message.txt");
    if (entry == null) {
        throw new IOException("Missing JAR entry");
    }
    try (InputStream in = jar.getInputStream(entry)) {
        byte[] packagedBytes = in.readAllBytes();
        // Hash packagedBytes và so với expected bytes.
    }
}
```

Đoạn này là **snippet trong method** có imports `java.io.*`; không phải phần của chương trình mục 11. Đừng coi hash của **toàn file JAR** là bằng chứng entry text giữ nguyên bytes. Nếu build cố tình expand version, thay đổi bytes là đúng **khi và chỉ khi expected output đã được định nghĩa**.

## 14. Ma trận sự cố và cách tìm đúng tầng

| Triệu chứng | Nghi vấn | Cách kiểm chứng |
| --- | --- | --- |
| Source compile lỗi với chữ Việt | Editor/`javac -encoding` không khớp | Inspect source bytes, compile rõ UTF-8 |
| Tiếng Việt thành `ChÃ o` | UTF-8 bytes bị đọc Latin-1; filter charset sai | Kiểm tra API `Properties` hoặc Maven/Gradle filtering |
| IDE chạy được, JAR resource missing | Resource path/copy/packaging sai | `jar --list`, classpath absolute vs package-relative |
| Windows fail, Linux pass | CRLF/LF, BOM, default charset, path | `git ls-files --eol`, hash, strict decoder, JDK version |
| SHA resource sau package đổi | Maven/Gradle filter, Git checkout, generated file | So raw bytes source/output/JAR entry |
| Shell script chạy lỗi trên Linux | Shebang line có CRLF | `*.sh text eol=lf`, kiểm tra bytes |
| JSON/template biến đổi ngoài ý muốn | Filter/expand chạy sai vùng | Giới hạn filesMatching/include, escape template |
| Test dùng `String.lines()` vẫn pass nhưng hash fail | API bỏ terminators nên EOL khác bị che | Kiểm tra raw bytes/sha256 |
| U+FEFF nằm đầu cấu hình | UTF-8 BOM | Kiểm tra `EF BB BF` và fail theo policy |
| Unicode text giống mắt nhưng compare fail | NFC/NFD hoặc EOL | Kiểm tra code points, normalize theo hợp đồng |
| Nâng Java 15 lên JDK 24 rồi decode khác | JEP 400 đổi default charset | Dùng overload có `Charset` rõ |
| Test fixture CRLF bị chuyển LF | Git attributes rule bao trùm fixture | `-text` cụ thể, byte-level test |

**Quy trình tìm lỗi hiệu quả:** bắt đầu từ **source bytes**, xem Git working tree, kiểm tra **copied/filtered resource**, rồi **JAR entry**, sau cùng mới nhìn **runtime decoding**. Đừng chỉ sửa một string bị mojibake ở tầng UI khi bytes đã bị đọc sai trước đó.

## 15. Bảo mật và hạn chế tự động chuẩn hóa

- **Không filter binary**: PNG, ZIP, JAR, fonts hoặc các bytes có chữ ký.
- **Không đưa secrets vào filtered JAR**: Build artifact có thể bị tải về/giải nén; secret phải quản lý qua cơ chế phù hợp tại runtime.
- **Không tự normalize text đã ký/hash** hoặc data giao thức cần giữ CRLF.
- **Không sử dụng `String.length()` làm byte length** cho UTF-8.
- **Không bỏ qua malformed UTF-8** bằng replacement khi protocol yêu cầu strict.
- **Không đọc classpath resource như đường dẫn filesystem tương đối**.
- **Không mặc định mọi .properties đều Latin-1 hoặc đều UTF-8**; phân biệt API.
- **Không đổi `file.encoding` tùy tiện** thay cho việc xác định charset của từng file/protocol.
- **Không normalize hàng loạt Git repo** nếu chưa audit những fixtures byte-exact.
- **Không dùng current directory/IDE behavior làm kiểm chứng packaging**; chạy JAR thật và so bytes output.
- **Không dùng build-time expansion trên template chưa tin cậy**: Gradle `expand` có khả năng xử lý biểu thức template; chỉ cho phép template/code do dự án kiểm soát.

## 16. Checklist QA/CI nên áp dụng

- [ ] Java source lưu UTF-8, compile `-encoding UTF-8 --release 15` hoặc tương đương Maven/Gradle.
- [ ] Resources có charset/EOL/BOM/final newline policy riêng.
- [ ] `.gitattributes` định nghĩa LF/CRLF và các ngoại lệ `-text`.
- [ ] Text config UTF-8 kiểm tra bằng strict decoder; BOM xử lý theo contract.
- [ ] File .properties được đọc bằng đúng API/charset như production.
- [ ] Maven/Gradle filtering chỉ áp dụng cho files chủ đích; filtered encoding UTF-8.
- [ ] Build output có đúng đường dẫn resource; không bị bỏ do include/exclude hoặc duplicate.
- [ ] Smoke test chạy từ **final JAR** (không chỉ IDE).
- [ ] Kiểm tra hash bytes của fixtures và JAR entries khi cần giữ nguyên.
- [ ] Test CRLF, LF, CR, mixed EOL, final newline và empty file.
- [ ] Test Unicode NFC/NFD, emoji, malformed UTF-8 khi domain cần.
- [ ] CI trên Windows/Linux và runtime Java 15/17/18+ phù hợp support matrix.
- [ ] Không log secrets, không đóng gói token vào generated resources.
- [ ] Mọi thay đổi build tooling/version phải chạy lại artifact-level tests.

## 17. Câu hỏi luyện tập và đáp án

**Câu 1.** `javac -encoding UTF-8 --release 15` có tự làm `message.txt` UTF-8/LF không?

**Đáp án:** **Không.** Cờ tác động tới compiler và target API/bytecode, không tự chuyển resources.

**Câu 2.** File LF và CRLF có thể có cùng nội dung khi dùng `String.lines()` nhưng SHA-256 khác không?

**Đáp án:** **Có.** `lines()` bỏ separators; hash tính trên bytes nhận `0A` khác `0D 0A`.

**Câu 3.** Vì sao `Properties.load(InputStream)` với UTF-8 raw tiếng Việt có thể sai, dù đang chạy JDK 24?

**Đáp án:** Overload này theo **ISO-8859-1**. Dùng `Properties.load(Reader UTF-8)` hoặc ResourceBundle phù hợp.

**Câu 4.** `ResourceBundle` đọc .properties bằng encoding nào từ Java 9?

**Đáp án:** UTF-8 mặc định, có fallback Latin-1 khi UTF-8 không hợp lệ theo Javadoc; strict policy cần config tương ứng.

**Câu 5.** Vì sao đọc `src/main/resources/foo.txt` bằng File API trong production là không đáng tin?

**Đáp án:** Máy chạy JAR không nhất thiết có thư mục source. Dùng classpath resource.

**Câu 6.** Làm sao bảo toàn fixture yêu cầu CRLF khi repo dùng `*.txt text eol=lf`?

**Đáp án:** Đặt ngoại lệ `-text` cho fixture hoặc sinh bytes trong test, kiểm tra bằng hash/raw bytes.

**Câu 7.** Maven/Gradle filtering có thể đổi line ending hoặc token trong file không?

**Đáp án:** Có, khi file được xử lý như text. Chỉ filter file template chọn lọc, đặt UTF-8 cho filter và test generated bytes.

**Câu 8.** Chữ “Cà phê” hiển thị giống nhau mà equals/hash khác, nguyên nhân có thể là gì?

**Đáp án:** Khác Unicode normalization NFC/NFD, EOL hoặc các ký tự ẩn như BOM; kiểm tra code points và bytes trước.

**Câu 9.** `Files.readString(path)` trên Java 15 dùng OS default charset hay UTF-8?

**Đáp án:** Theo API, overload này dùng **UTF-8** từ Java 11.

**Câu 10.** `System.lineSeparator()` nên dùng để tạo golden fixtures reproducible không?

**Đáp án:** Thường không, trừ khi fixture cần EOL native. Nếu contract là LF, dùng `"\n"`.

**Câu 11.** Kiểm tra hash toàn JAR có đủ để biết một .properties entry giữ nguyên không?

**Đáp án:** Không. Archive còn metadata/entries khác; hash bytes **riêng entry** với expected content.

**Câu 12.** Java text block từ Java 15 có khiến resources trong JAR tự normalize newline không?

**Đáp án:** **Không.** Compiler xử lý text block literal, còn resources được Git/build tool copy/filter theo pipeline riêng.

**Tiêu chí đạt:** Bạn có thể mô tả đường đi bytes từ repository tới JAR, cấu hình charset đúng ở từng tầng, đọc/kiểm thử classpath resource và chọn rõ khi nào normalize LF, khi nào cần giữ raw bytes.

## 18. Tài liệu chuẩn còn áp dụng

- [Java SE 15 – InputStreamReader](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/io/InputStreamReader.html): chọn charset cho reader.
- [Java SE 15 – Files](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/nio/file/Files.html): `readString`/`writeString` UTF-8 mặc định.
- [Java SE 15 – String.lines](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/String.html#lines()): LF/CR/CRLF.
- [Java SE 25 – Properties](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Properties.html): overload InputStream ISO-8859-1 và Reader.
- [Java SE 25 – PropertyResourceBundle](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/PropertyResourceBundle.html): UTF-8 default/fallback.
- [Java SE 25 – Class.getResourceAsStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#getResourceAsStream(java.lang.String)): classpath relative/absolute paths.
- [OpenJDK JEP 400](https://openjdk.org/jeps/400): UTF-8 by Default từ JDK 18.
- [OpenJDK JEP 378](https://openjdk.org/jeps/378): Text Blocks chính thức trong Java 15.
- [Maven Compiler Plugin – Set --release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html): API target.
- [Maven Resources Plugin – Encoding](https://maven.apache.org/plugins/maven-resources-plugin/examples/encoding.html): charset khi filtering.
- [Maven – Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html): placeholders và `propertiesEncoding`.
- [Gradle – Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): `CopySpec`, `expand`, `filteringCharset`.
- [Gradle – CopySpec API](https://docs.gradle.org/current/javadoc/org/gradle/api/file/CopySpec.html): filtering charset.
- [Git – gitattributes](https://git-scm.com/docs/gitattributes): `text`/`eol`/`-text` và normalization.

**Ghi nhớ:** Một build đáng tin cần đồng thời xác định **Java source encoding, resource bytes, Git EOL, Maven/Gradle filtering, classpath JAR và charset lúc runtime**. Nếu bytes cần được giữ nguyên, hãy kiểm chứng chính xác bytes; nếu cần chuẩn hóa text, hãy chuẩn hóa **có chủ đích và theo hợp đồng** trước khi ký/hash hoặc đóng gói.