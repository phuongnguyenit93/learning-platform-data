# Encoding, ký tự Unicode và khả năng tái lập khi đọc nguồn Java

Trong quá trình biên dịch Java, tệp `.java` bắt đầu là **một dãy byte**. Trình biên dịch phải giải mã dãy byte đó thành ký tự Unicode, xử lý Unicode escape, phân tích token và cú pháp rồi mới sinh bytecode. Nếu các máy khác nhau giải mã cùng một tệp theo charset khác nhau, chúng có thể nhận được chương trình khác nhau hoặc một máy biên dịch được còn máy khác báo lỗi. Đây là vấn đề thuộc tổ chức mã nguồn và tính tái lập của bản dựng.

Sau bài này, cần phân biệt được byte, charset, Unicode code point, UTF-16 code unit; cấu hình đúng encoding của `javac` và công cụ build; nhận biết rủi ro Unicode escape/normalization; kiểm tra rằng một nguồn được đọc nhất quán trên máy phát triển và CI.

## 1. Từ byte của tệp nguồn đến chương trình Java

Luồng khái niệm:

```text
Tệp .java (byte trên đĩa)
    -> giải mã theo charset nguồn, ví dụ UTF-8
    -> chuỗi ký tự Unicode
    -> dịch Unicode escape (\uXXXX) rất sớm
    -> phân tích ký tự, token, comment và literal
    -> phân tích cú pháp/kiểu, sinh .class
```

* **Unicode** xác định các ký tự và code point (ví dụ `U+1EC7` là “ệ”); Unicode tự nó không phải một định dạng lưu byte.
* **UTF-8** mã hóa một code point bằng 1–4 byte. Ký tự ASCII dùng một byte; “ệ” dùng ba byte; “😀” dùng bốn byte.
* **UTF-16** biểu diễn phần lớn ký tự thường gặp bằng một đơn vị 16 bit, nhưng ký tự ngoài Basic Multilingual Plane (như “😀”) cần hai đơn vị, gọi là *surrogate pair*.
* **Charset** quyết định byte ↔ ký tự. Nếu một editor lưu UTF-8 mà compiler đọc theo Windows-1252, Latin-1 hoặc một charset hệ thống khác, các dấu tiếng Việt có thể sai hoặc biên dịch thất bại.
* **Line ending** (LF hoặc CRLF) cũng là byte trong tệp nguồn. Nó thường không đổi ý nghĩa chương trình Java, nhưng làm đổi hash của tệp, vị trí lỗi và kết quả các bước xử lý văn bản.

Ví dụ chuỗi `"Việt 😀"` chứa 6 code point, 7 UTF-16 code unit và 11 byte khi mã hóa UTF-8. Ba con số đo ba thứ khác nhau. `String.length()` đếm UTF-16 code unit, không đếm code point hay byte.

## 2. Quy định rõ charset đầu vào của trình biên dịch

Dùng tùy chọn sau khi biên dịch trực tiếp:

```bash
javac -encoding UTF-8 -d out src/SourceEncodingDemo.java
```

`-encoding UTF-8` áp dụng cho **tệp nguồn mà `javac` đọc**. `-d out` chỉ chọn thư mục xuất lớp; cần tạo thư mục `out` trước khi chạy lệnh. Đường dẫn đến nguồn và tên tệp phải khớp với `public class` tương ứng.

Mặc định phụ thuộc phiên bản/môi trường: trên JDK 17 trở về trước, charset mặc định của các API phụ thuộc nền tảng có thể theo môi trường; từ JDK 18, JEP 400 xác định UTF-8 làm charset mặc định cho phần lớn API chuẩn. Tuy nhiên, một bản dựng tái lập nên **khai báo UTF-8 tường minh** thay vì phó mặc cho charset mặc định, cấu hình IDE, tiến trình Gradle/Maven hay máy CI. Sự chuyển đổi sang UTF-8 mặc định không tự sửa các tệp vốn được lưu bằng một encoding khác.

Trong Gradle Groovy DSL (`build.gradle`):

```groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Trong Maven (`pom.xml`):

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

Đây là cấu hình *đọc mã nguồn*. Những đầu vào khác như resource, fixture kiểm thử, file cấu hình hoặc dữ liệu do code generator tạo có thể cần chính sách charset riêng. Với Maven, nên kiểm tra cấu hình thực tế của compiler/resources plugin ở phiên bản dự án sử dụng. Với Gradle, nếu sinh Java source, hãy bảo đảm generator cũng **ghi UTF-8**.

Chỉ định charset không đồng nghĩa chỉ định phiên bản Java. Muốn bản dựng ổn định cần đồng thời khóa/cấu hình JDK/toolchain, `--release` hoặc `sourceCompatibility`/`targetCompatibility` khi thích hợp, dependency và các tham số build liên quan.

## 3. Unicode escape được xử lý trước cả comment và string literal

Java cho phép cú pháp Unicode escape dạng `\uXXXX`, trong đó `XXXX` là bốn chữ số hex của một UTF-16 code unit. Bước dịch escape xảy ra **rất sớm, trước khi nhận diện token và comment** theo quy tắc lexical translation của Java Language Specification.

Ví dụ dưới đây là **minh họa nguy cơ**, không phải đoạn code nên sao chép vào dự án:

```java
// \u000a System.out.println("Dòng này có thể trở thành code!");
```

Nếu chuỗi ký tự thô trong tệp đúng là dấu gạch chéo ngược theo sau bởi `u000a` hợp lệ, bước dịch Unicode escape tạo ký tự xuống dòng; phần sau có thể thoát khỏi comment `//` và trở thành câu lệnh Java. Vì vậy, **đừng coi `\uXXXX` trong comment hay literal là văn bản vô hại**. Các chuỗi backslash còn chịu quy tắc *eligible backslash* của ngôn ngữ, nên không thể thay mọi chuỗi `\u` một cách cơ học.

Khi cần chứa ký tự Unicode trong string literal, thường dễ đọc hơn nếu lưu nguyên ký tự trong tệp UTF-8, ví dụ `"Tiếng Việt"`. Dùng escape khi có lý do cụ thể (ký tự điều khiển, cần văn bản ASCII hoặc mã sinh tự động). Java Unicode escape `\uXXXX` biểu diễn từng **UTF-16 code unit**, nên không thể viết code point `U+1F600` trực tiếp thành `\u1F600`; phải dùng ký tự thực, escape thích hợp hoặc API như `Character.toChars(0x1F600)`.

Đừng nhầm Unicode escape được biên dịch ở bước đọc source với escape trong dữ liệu đọc lúc chạy. Một tệp CSV chứa sáu ký tự `\u0041` vẫn là sáu ký tự dữ liệu cho đến khi chính chương trình quyết định diễn giải nó.

## 4. Ví dụ Java 17+ có thể biên dịch và kiểm tra

Lưu tệp `src/SourceEncodingDemo.java` **UTF-8 không BOM**:

```java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

public class SourceEncodingDemo {
    public static void main(String[] args) {
        String text = "Việt 😀";
        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints=" + text.codePointCount(0, text.length()));
        System.out.println("utf8Bytes=" + text.getBytes(StandardCharsets.UTF_8).length);

        String composed = "\u00E9";     // é: một code point
        String decomposed = "e\u0301";  // e + dấu sắc kết hợp
        System.out.println("sameRaw=" + composed.equals(decomposed));
        System.out.println("sameNfc=" +
                Normalizer.normalize(decomposed, Normalizer.Form.NFC)
                        .equals(composed));
    }
}
```

Từ thư mục dự án, tạo `out` rồi chạy:

```bash
mkdir out
javac -encoding UTF-8 -d out src/SourceEncodingDemo.java
java -cp out SourceEncodingDemo
```

Stdout chính xác:

```text
utf16Units=7
codePoints=6
utf8Bytes=11
sameRaw=false
sameNfc=true
```

Giải thích: “Việt” có bốn code point, khoảng trắng có một, emoji có một. Emoji chiếm hai UTF-16 code unit và bốn byte UTF-8; ký tự “ệ” chiếm ba byte UTF-8. Hai chuỗi “é” và “e” + combining acute accent có thể nhìn giống nhau nhưng `String.equals` so sánh trình tự UTF-16 code unit, nên ban đầu trả `false`. Chuẩn hóa cả dữ liệu vào một dạng Unicode, chẳng hạn NFC, cho phép so sánh theo quy tắc mong muốn. **Java compiler không tự chuẩn hóa mọi literal, tên và đường dẫn theo NFC**.

Ví dụ chỉ in số và boolean để kết quả không lệ thuộc khả năng hiển thị emoji của terminal. Nếu in trực tiếp tiếng Việt hoặc emoji, chương trình có thể tạo đúng ký tự nhưng màn hình vẫn hiển thị sai do cấu hình terminal/font/encoding đầu ra; đó là vấn đề khác với đọc tệp `.java`.

## 5. Đọc nguồn bằng chương trình và bằng JavaCompiler API

Khi một công cụ phân tích source, linter hoặc generator tự đọc tệp `.java` như dữ liệu, hãy nêu charset trong mã Java thay vì dựa vào charset mặc định:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadSourceUtf8 {
    public static void main(String[] args) throws Exception {
        Path path = Path.of(args[0]);
        String source = Files.readString(path, StandardCharsets.UTF_8);
        System.out.println("codePoints=" +
                source.codePointCount(0, source.length()));
    }
}
```

Đây là **chương trình độc lập**, cần được lưu trong `ReadSourceUtf8.java` và truyền đường dẫn tệp tồn tại khi chạy, ví dụ:

```bash
javac -encoding UTF-8 ReadSourceUtf8.java
java ReadSourceUtf8 src/SourceEncodingDemo.java
```

Số code point được in phụ thuộc nội dung thực của tệp đầu vào, nên không có một stdout cố định cho mọi file. `Files.readString(path, UTF_8)` giải mã byte thành ký tự; nếu byte không hợp lệ với UTF-8, thao tác đọc báo lỗi thay vì im lặng đoán một charset khác. `Files.readAllBytes(path)` phù hợp khi cần so sánh byte gốc hoặc hash tệp.

Công cụ tích hợp compiler trong tiến trình JVM có thể chọn charset của `StandardJavaFileManager`:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
try (StandardJavaFileManager manager =
         compiler.getStandardFileManager(
             null, java.util.Locale.ROOT,
             java.nio.charset.StandardCharsets.UTF_8)) {
    // Truyền manager cho compiler task và xử lý diagnostics tại đây.
}
```

Đoạn trên là **mã minh họa trong một phương thức**, cần import `javax.tools.JavaCompiler`, `javax.tools.ToolProvider` và `javax.tools.StandardJavaFileManager` nếu dùng thật; nó không phải chương trình chạy độc lập. `ToolProvider.getSystemJavaCompiler()` có thể trả `null` nếu môi trường chạy không có system compiler. Chọn UTF-8 cho file manager giúp công cụ đọc nguồn nhất quán với `javac -encoding UTF-8`.

## 6. Unicode normalization, tên tệp và tính tái lập

Hai chuỗi có hình thức hiển thị giống nhau có thể được biểu diễn bằng code point khác nhau. Điều này ảnh hưởng đến:

- **Literal, dữ liệu và hash:** NFC và NFD không có cùng byte UTF-8; SHA-256 của file nguồn sẽ khác dù văn bản trông tương tự.
- **Tên định danh Java:** compiler xét ký tự theo quy tắc ngôn ngữ, không được giả định rằng các chuỗi nhìn giống nhau là cùng tên. Đặt tên identifier bằng ASCII thông thường là cách giảm khác biệt giữa công cụ; literal/comment vẫn dùng UTF-8 có dấu bình thường.
- **Tên tệp/đường dẫn:** hệ điều hành và filesystem có quy tắc phân biệt chữ hoa, chuẩn hóa Unicode và so khớp tên khác nhau. Tên tệp `public class` cần khớp chính xác; nếu repo chạy đa nền tảng, ưu tiên tên file/package ASCII ổn định.
- **Biểu diễn ký tự khi qua hệ thống ngoài:** JSON, HTTP, cơ sở dữ liệu, terminal và resource có thể cần charset riêng; byte đầu ra không nhất thiết trùng byte của tệp nguồn.

Đừng tự động chuyển toàn bộ source sang NFC chỉ để “làm đẹp”: một bước chuẩn hóa hàng loạt có thể thay đổi literal, comment, tài liệu hoặc các byte được dùng để so sánh; nên xác định chính sách, kiểm tra diff và áp dụng có chủ đích. Khi so sánh chuỗi đầu vào do người dùng nhập, chuẩn hóa cả hai phía theo cùng chính sách rồi mới so sánh.

## 7. Kiểm soát encoding trong kho mã và CI

Một quy trình thực tế:

1. **Chốt chuẩn:** mọi `.java` lưu UTF-8 (ưu tiên không BOM); cấu hình editor/IDE, formatter, generator và `javac`/Gradle/Maven theo cùng chuẩn.
2. **Chốt toolchain:** quy định JDK và bản phát hành đích; không dùng ngẫu nhiên JDK 17 ở máy dev và JDK 21 trên CI mà kỳ vọng `.class` giống hệt.
3. **Chốt newline:** chọn chính sách LF/CRLF nhất quán cho repository. Có thể đặt `.gitattributes` như sau nếu nhóm thống nhất lưu LF:
   
   ```gitattributes
   *.java text eol=lf
   ```
   
   Đây là chính sách checkout của Git. Thay đổi newline có thể làm khác hash file ngay cả khi Java xử lý cùng nghĩa.
4. **Kiểm tra tệp đầu vào:** phát hiện file lưu sai charset, BOM, byte UTF-8 không hợp lệ, ký tự thay thế U+FFFD hoặc khác biệt Unicode normalization ngoài mong đợi.
5. **Không dựa vào terminal:** log rõ tên JDK, compiler arguments, charset của source và checksum byte nguồn khi điều tra sai khác; kiểm tra byte và nội dung được decode thay vì chỉ nhìn chữ trên màn hình.
6. **Tái chạy trong môi trường sạch:** biên dịch cùng commit bằng cùng JDK/toolchain, cùng dependency và cấu hình; so lỗi/cảnh báo, output và hash phù hợp.

Nếu phải có build **byte-for-byte reproducible**, encoding chỉ là một điều kiện. Timestamp trong archive/JAR, thứ tự đóng gói, annotation processor, đường dẫn tuyệt đối, locale, timezone, biến môi trường, dependency và plugin cũng có thể ảnh hưởng đầu ra. “Đọc source giống nhau” không đủ để kết luận mọi artifact giống nhau.

## 8. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra/xử lý |
| --- | --- | --- |
| `unmappable character for encoding ...` hoặc `malformed input` khi biên dịch | Byte của file nguồn không hợp charset compiler | Kiểm tra encoding thực tế của file, chuyển đổi có kiểm soát sang UTF-8, biên dịch với `-encoding UTF-8` |
| `illegal character` ở đầu file, có thể chỉ ra `\ufeff` | BOM hoặc ký tự đầu file không phù hợp với parser/tool | Kiểm tra byte đầu tệp và lưu UTF-8 không BOM; không xóa mù ký tự khác |
| Source chạy nhưng literal tiếng Việt sai dấu | Text đã bị lưu/đọc sai charset hoặc mojibake trước khi compile | So sánh byte gốc trong Git, editor encoding và charset compiler; sửa từ bản nguồn chưa bị mất dữ liệu |
| In console thành `?` hay ký tự vuông | Encoding/font của output terminal | Kiểm tra code point trong JVM, charset đầu ra và khả năng font; đừng vội sửa tệp source |
| `String.length()` khác “số ký tự nhìn thấy” | `length()` đếm UTF-16 code unit | Dùng `codePointCount` nếu cần code point; *grapheme cluster* là khái niệm khác và có thể cần xử lý Unicode nâng cao |
| Chuỗi trông giống nhưng `equals` là `false` | NFC/NFD hoặc ký tự tương tự khác code point | In code point dạng hex; chuẩn hóa có chủ đích trước so sánh |
| Comment chứa `\u000a` làm thay đổi code | Unicode escape được dịch trước bước nhận comment | Rà soát escape trong nguồn/generator; không đặt escape nguy hiểm trong comment |
| Chỉ CI lỗi “không tìm thấy file/class” | Khác tên đường dẫn, case hoặc Unicode normalization của filesystem | Kiểm tra tên file thực, tên `public class` và thao tác checkout trên hệ điều hành CI |

Khi chẩn đoán, hãy tách ba lớp: **byte trong Git**, **ký tự compiler đã decode**, và **ký tự hiển thị ở console**. Sửa nhầm lớp có thể che triệu chứng trong một máy nhưng khiến bản dựng ở máy khác tiếp tục sai.

## 9. Bài thực hành và tiêu chí hoàn thành

Tạo tệp UTF-8 `SourceEncodingDemo.java` ở trên; chạy với JDK 17+ bằng `javac -encoding UTF-8` và đối chiếu đúng năm dòng stdout. Sau đó thử mở một bản **sao chép** bằng editor ở charset không khớp, hoặc sửa cấu hình compiler trên môi trường kiểm thử: quan sát lỗi giải mã/mojibake và kiểm tra nguyên nhân từ byte gốc. Kiểm tra chuỗi NFC/NFD bằng `equals` và `Normalizer`, rồi xác minh số lượng UTF-16 code unit, code point và byte UTF-8.

Cuối cùng, chạy build cùng một commit ở hai môi trường với **cùng JDK, cùng UTF-8 và cùng cấu hình**. Đối chiếu nguồn (byte, encoding, newline, hash) trước khi đánh giá artifact. Nếu artifact khác, tiếp tục khảo sát các đầu vào build khác; không quy ngay mọi khác biệt cho Unicode.

**Nguyên tắc áp dụng:** phiên bản Java và charset phải được cấu hình rõ; byte nguồn cần được lưu, đọc và kiểm tra nhất quán; Unicode escape, normalization và cách hiển thị ký tự là các tầng riêng biệt. Nắm rõ từng tầng sẽ giúp tìm đúng nguyên nhân khi mã Java chỉ biên dịch hoặc hiển thị đúng trên một máy.
