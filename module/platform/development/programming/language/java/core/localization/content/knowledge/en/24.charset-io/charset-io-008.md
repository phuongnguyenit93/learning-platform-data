# Kiểm tra chuỗi qua ranh giới tệp, tài nguyên và đầu ra trong Java

## 1. Vì sao cùng một chuỗi lại có thể bị lỗi dấu?

Trong Java, `String` chứa dữ liệu ký tự Unicode (theo mô hình UTF-16). Nhưng khi lưu tệp, đọc tài nguyên, gửi HTTP hoặc in ra terminal, văn bản đi qua **ranh giới giữa ký tự và byte**:

~~~text
String (Unicode)
      |
      | encode bằng một Charset
      v
bytes trên tệp / tài nguyên / mạng / stdout
      |
      | decode bằng Charset của bên nhận
      v
String hoặc chữ được render trên màn hình
~~~

Nếu bên ghi dùng UTF-8 nhưng bên đọc hiểu ISO-8859-1, chuỗi `café` có thể thành `cafÃ©`. Nếu một ký tự không thể biểu diễn trong charset đích, hệ thống có thể thay bằng dấu `?` hoặc báo lỗi. Nếu terminal nhận đúng byte nhưng diễn giải bằng bảng mã khác, chương trình vẫn có thể đúng trong bộ nhớ mà **đầu ra nhìn thấy bị sai**.

Bài này tập trung vào **kiểm tra chuỗi qua ba ranh giới**:

1. **Tệp (file I/O)**: dữ liệu đi từ `String` sang byte và trở lại.
2. **Tài nguyên (resource files)**: `.properties`, `ResourceBundle`, cấu hình, bản dịch.
3. **Đầu ra (output)**: console, log, stream và dữ liệu trao đổi với hệ thống khác.

Chúng ta dùng Java 17+ và các API `StandardCharsets`, `Files`, `InputStreamReader`, `OutputStreamWriter`, `Properties`, `ResourceBundle`, `CharsetDecoder` và `CharsetEncoder` để tìm **đúng ranh giới gây lỗi**, thay vì đoán rằng Java “không hỗ trợ tiếng Việt”.

**Nguyên tắc:** một thao tác format theo `Locale` và một thao tác encode theo `Charset` là **hai việc khác nhau**. `Locale.forLanguageTag("vi-VN")` không tự biến byte thành UTF-8; `StandardCharsets.UTF_8` không tự dịch thông điệp sang tiếng Việt.

## 2. Phân biệt Unicode, Charset, Locale và Encoding

| Khái niệm | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Unicode code point | Nhận diện ký tự trừu tượng | `é` là `U+00E9`, `🌍` là `U+1F30D` |
| `String` của Java | Lưu chuỗi bằng các UTF-16 code unit | `String.equals`, `length`, `codePoints` |
| Charset | Ánh xạ giữa ký tự và byte | UTF-8, UTF-16, ISO-8859-1 |
| Encoder | Chuyển `char`/chuỗi sang byte | `String.getBytes(UTF_8)` |
| Decoder | Chuyển byte về ký tự | `new String(bytes, UTF_8)` |
| Locale | Quy tắc ngôn ngữ/vùng cho format và chọn bản dịch | `Locale.US`, `vi-VN` |
| ResourceBundle | Chọn tài nguyên theo locale và cơ chế fallback | `Messages_vi_VN.properties` |
| Terminal/font | Nhận byte rồi chọn glyph để vẽ | Console Windows, terminal Linux, CI log |

UTF-8 là **encoding**, không phải ngôn ngữ. Cùng chuỗi `"Xin chào"` có thể hiển thị cho người dùng ở nhiều locale nhưng vẫn được lưu bằng UTF-8 trong hệ thống.

### Không lấy `String.length()` làm số byte

`String.length()` đếm **UTF-16 code unit**; ký tự ngoài BMP như `🌍` thường chiếm 2 code unit, trong UTF-8 lại chiếm 4 byte. Một ký tự có dấu có thể ở dạng dựng sẵn hoặc dạng chữ cơ sở + dấu kết hợp, làm số code point/code unit khác nhau dù nhìn giống.

Ví dụ:

~~~java
String text = "🌍";
System.out.println(text.length());                       // 2
System.out.println(text.codePointCount(0, text.length())); // 1
System.out.println(text.getBytes(StandardCharsets.UTF_8).length); // 4
~~~

Đây là **mảnh mã trong method**, cần import `java.nio.charset.StandardCharsets`. Không suy số byte của file, giới hạn truyền mạng hoặc độ rộng cột từ `String.length()`.

## 3. Sơ đồ kiểm tra ranh giới: kiểm tra ở cả bên ghi và bên đọc

Khi thấy chuỗi lỗi dấu, hãy thu thập bằng chứng ở từng điểm:

~~~text
[1] String gốc
    - các code point là gì?
    - có đúng dấu trước khi encode không?
        |
        v
[2] byte sau encode
    - Charset nào được chọn?
    - hex byte có đúng không?
        |
        v
[3] byte khi đọc lại
    - còn nguyên các byte?
    - có BOM hoặc bước chuyển đổi trung gian?
        |
        v
[4] String sau decode
    - dùng charset gì?
    - có xuất hiện U+FFFD hoặc mojibake?
        |
        v
[5] đầu ra hiển thị
    - stdout/log đã encode đúng chưa?
    - terminal/browser có decode/font phù hợp không?
~~~

Nếu `String` đọc từ tệp đã sai, nguyên nhân nằm ở một bước **trước khi render**. Nếu các code point trong `String` đúng nhưng màn hình sai, xem lại **encoding của output, môi trường terminal và font**.

### Ba kiểu lỗi quan trọng

- **Mojibake**: byte hợp lệ bị giải mã bằng charset không khớp. Ví dụ UTF-8 của `é` là `C3 A9`, đọc hai byte như ISO-8859-1 sẽ ra `Ã©`.
- **Replacement character**: decoder không đọc được chuỗi byte nên thay bằng `U+FFFD`, thường hiển thị `�`.
- **Unmappable character**: encoder không thể biểu diễn ký tự trong charset đích; tùy chính sách có thể ghi `?` hoặc ném exception.

Không nên “sửa dấu” bằng nhiều lần `new String(old.getBytes(...), ...)` nếu chưa biết **các byte gốc và lịch sử encode/decode**. Một chuỗi đã bị thay ký tự mất mát có thể không thể khôi phục chính xác.

## 4. Chọn StandardCharsets.UTF_8 tường minh

Java cung cấp hằng `StandardCharsets.UTF_8` trong `java.nio.charset`. Đây là lựa chọn thống nhất phổ biến cho file văn bản, tài nguyên và giao thức hiện đại khi không có tiêu chuẩn khác bắt buộc.

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

Đây là **mảnh mã trong method**, cần import `java.nio.charset.StandardCharsets` và biến `text` có sẵn.

**Quy tắc round-trip:** Nếu văn bản đầu vào hợp lệ, được encode và decode cùng charset có thể biểu diễn đầy đủ các ký tự, thông thường `text.equals(decoded)` phải là `true`. Khi chuyển sang ISO-8859-1, UTF-16BE hoặc charset khác mà không có hợp đồng rõ, round-trip có thể không đảm bảo.

### Java 17 và Java 18+ khác nhau về default charset

- Trong **JDK 17 và cũ hơn**, charset mặc định của nhiều API phụ thuộc hệ điều hành, cấu hình locale/máy và cách JVM khởi động.
- Từ **JDK 18**, JEP 400 chuyển default charset của phần lớn Java SE API sang UTF-8 theo mặc định; có những ngoại lệ liên quan I/O console và cơ chế tương thích.
- Dù vậy, **không nên dựa vào default charset** nếu định dạng tệp/giao thức là một hợp đồng cần tái lập trên các JDK, máy chủ và CI khác nhau.
- Các API như `Files.readString(Path)` và `Files.writeString(Path, ...)` đã chọn UTF-8 theo tài liệu của chính chúng, độc lập với việc đoán default charset của `FileReader` cũ.

Để xem môi trường:

~~~java
System.out.println(Charset.defaultCharset());
System.out.println(System.getProperty("file.encoding"));
~~~

Đây là **mảnh mã trong method**, cần import `java.nio.charset.Charset`. Đây là dữ liệu chẩn đoán, **không** phải cách cấu hình encoding cho từng tệp. Tránh dựa vào việc gọi `System.setProperty("file.encoding", ...)` lúc runtime để đổi mọi I/O đang tồn tại.

## 5. Ví dụ hoàn chỉnh: ghi và đọc UTF-8 không mất thông tin

Tạo `Utf8RoundTripDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.HexFormat;

public class Utf8RoundTripDemo {
    public static void main(String[] args) throws Exception {
        String source = "Xin chào, 世界 🌍";
        Path file = Files.createTempFile("utf8-roundtrip-", ".txt");

        try {
            byte[] expectedBytes =
                    source.getBytes(StandardCharsets.UTF_8);

            Files.writeString(file, source, StandardCharsets.UTF_8);
            byte[] actualBytes = Files.readAllBytes(file);
            String decoded =
                    Files.readString(file, StandardCharsets.UTF_8);

            System.out.println("Same bytes: "
                    + Arrays.equals(expectedBytes, actualBytes));
            System.out.println("Same text: "
                    + source.equals(decoded));
            System.out.println("UTF-8 for é: "
                    + HexFormat.of().formatHex(
                            "é".getBytes(StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Chạy trên Java 17+:

~~~bash
javac -encoding UTF-8 Utf8RoundTripDemo.java
java Utf8RoundTripDemo
~~~

Đầu ra:

~~~text
Same bytes: true
Same text: true
UTF-8 for é: c3a9
~~~

Bài kiểm tra xác nhận hai thứ **khác nhau nhưng liên quan**:

1. `Same bytes`: file thực sự chứa đúng byte UTF-8 được tạo từ nguồn.
2. `Same text`: decoder tái tạo được chính xác `String` đầu vào.

Nếu chỉ in văn bản ra console rồi so bằng mắt, bạn khó phân biệt lỗi xảy ra ở file, decoder hay terminal. So sánh byte/chuỗi trong chương trình giúp cô lập vấn đề **không phụ thuộc khả năng hiển thị Unicode của console**.

`HexFormat` có từ Java 17; nếu dùng Java cũ hơn, có thể tự định dạng hex bằng vòng lặp hoặc công cụ phù hợp.

## 6. Files.readString/writeString và các API cũ

### Chọn API mà bạn biết chính xác charset

| Cách dùng | Charset được chọn | Đánh giá |
| --- | --- | --- |
| `Files.readString(path, UTF_8)` | Tường minh UTF-8 | Rõ ràng, nên dùng cho text file |
| `Files.writeString(path, text, UTF_8)` | Tường minh UTF-8 | Dễ kiểm thử byte chính xác |
| `Files.readString(path)` | UTF-8 theo API | Ổn khi đúng hợp đồng UTF-8 |
| `Files.newBufferedReader(path, UTF_8)` | UTF-8 | Phù hợp đọc dòng theo stream |
| `Files.newBufferedWriter(path, UTF_8)` | UTF-8 | Phù hợp ghi dòng theo stream |
| `new InputStreamReader(in, UTF_8)` | UTF-8 | Phù hợp khi làm việc với byte stream |
| `new OutputStreamWriter(out, UTF_8)` | UTF-8 | Phù hợp khi ghi ra byte stream |
| `new InputStreamReader(in)` | Default charset | Dễ lệch hợp đồng trên Java 17 |
| `new FileReader(file)` ở Java 17 | Default charset | Cần xem xét khi di trú code |
| `new String(bytes)` | Default charset | Không nên dùng khi byte có encoding xác định |
| `text.getBytes()` | Default charset | Không nên dùng làm giao thức ổn định |

### Đọc dạng stream

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý một dòng đã được giải mã UTF-8.
    }
}
~~~

Đây là **mảnh mã trong method**, cần import `java.io.BufferedReader`, `java.nio.file.Files`, `java.nio.file.Path` và `java.nio.charset.StandardCharsets`; `path` đã được xác định.

Chọn đọc dạng stream khi tệp lớn hoặc cần xử lý từng dòng. `Files.readString` đọc toàn bộ nội dung vào bộ nhớ, nên không nên dùng vô điều kiện cho file rất lớn hoặc file không đáng tin.

### Đóng stream và flush

Khi ghi bằng `BufferedWriter`/`OutputStreamWriter`, phải `flush`/`close` phù hợp để đảm bảo byte đã được chuyển xuống đích. Dùng `try-with-resources` để đóng và lan truyền lỗi I/O. Nhưng **đóng writer không sửa được charset sai**; hãy xác định encoding đúng ngay khi tạo writer.

## 7. Khi byte sai: strict decoder và chính sách thay thế

Một số API convenience có thể thay byte không hợp lệ bằng ký tự thay thế, khiến chương trình **không ném lỗi** nhưng âm thầm mất thông tin. Khi đang xử lý tệp nhập quan trọng, nên chủ động chọn `CodingErrorAction.REPORT`.

### Chương trình Java 17+ đầy đủ

Tạo `StrictDecodeDemo.java`:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class StrictDecodeDemo {
    public static void main(String[] args) {
        // C3 phải theo sau bởi UTF-8 continuation byte,
        // nhưng 28 là dấu '(' (không hợp lệ trong vị trí đó).
        byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(invalidUtf8));

            System.out.println("Unexpected success");
        } catch (CharacterCodingException ex) {
            System.out.println("Strict decode failed: "
                    + ex.getClass().getSimpleName());
        }

        String replaced = new String(
                invalidUtf8, StandardCharsets.UTF_8);

        System.out.printf(Locale.ROOT,
                "First code point after replacement: U+%04X%n",
                replaced.codePointAt(0));
        System.out.println("Replaced length: " + replaced.length());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 StrictDecodeDemo.java
java StrictDecodeDemo
~~~

Đầu ra:

~~~text
Strict decode failed: MalformedInputException
First code point after replacement: U+FFFD
Replaced length: 2
~~~

**Vì sao quan trọng?**

- `CharsetDecoder` với `REPORT` thông báo byte không hợp lệ.
- `new String(invalidUtf8, UTF_8)` trong ví dụ dùng hành vi thay thế đối với byte không hợp lệ, đưa `U+FFFD` vào kết quả.
- Một khi byte gốc bị thay bằng `U+FFFD` hoặc dấu `?`, thông tin gốc có thể đã mất; đừng cho rằng có thể sửa ngược một cách đáng tin.
- Trong pipeline phải kiểm tra nghiêm ngặt, dùng decoder/encoder có chính sách rõ ràng và ghi nhận lỗi tại **ranh giới byte**.

### Encoder cũng cần chính sách lỗi

Nếu đích là ISO-8859-1, các ký tự như tiếng Nhật không thể biểu diễn. Dùng `CharsetEncoder` và `CodingErrorAction.REPORT` nếu muốn thất bại rõ ràng thay vì thay ký tự:

~~~java
CharsetEncoder encoder =
        StandardCharsets.ISO_8859_1.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
ByteBuffer bytes = encoder.encode(CharBuffer.wrap("日本語"));
~~~

Đây là **mảnh mã minh họa** trong method, cần import `java.nio.charset.CharsetEncoder`, `CodingErrorAction`, `StandardCharsets`, `java.nio.CharBuffer`, `java.nio.ByteBuffer` và khai báo `throws CharacterCodingException` hoặc xử lý exception. Ví dụ này sẽ ném lỗi unmappable: tệp Latin-1 không thể chứa trực tiếp các chữ đó.

Chỉ dùng charset lịch sử như ISO-8859-1 hoặc Windows code page khi đầu vào/đầu ra **đã được xác nhận** dùng charset đó. Nếu là giao thức mới, UTF-8 thường là lựa chọn rõ ràng hơn.

## 8. Properties.load(InputStream) khác Properties.load(Reader)

Đây là một trong những ranh giới gây lỗi dấu nhiều nhất trong ứng dụng Java.

**`java.util.Properties.load(InputStream)`** định nghĩa rằng mỗi byte được hiểu theo ISO-8859-1, với Unicode escape `\uXXXX` để biểu diễn ký tự ngoài tập. Điều này **không thay đổi** chỉ vì JDK 18+ chọn UTF-8 làm default charset.

Trong khi đó, **`Properties.load(Reader)`** đọc **ký tự** từ Reader đã được giải mã; nếu Reader dùng UTF-8, nội dung properties UTF-8 được đưa vào đúng Unicode.

### Ví dụ Java 17+ đầy đủ, không cần tạo file

Tạo `PropertiesEncodingDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public class PropertiesEncodingDemo {
    public static void main(String[] args) throws Exception {
        String source = "label=café\n";
        byte[] utf8 = source.getBytes(StandardCharsets.UTF_8);

        Properties legacyBytes = new Properties();
        legacyBytes.load(new ByteArrayInputStream(utf8));

        Properties utf8Reader = new Properties();
        try (InputStreamReader reader = new InputStreamReader(
                new ByteArrayInputStream(utf8),
                StandardCharsets.UTF_8)) {
            utf8Reader.load(reader);
        }

        System.out.println("InputStream value: "
                + legacyBytes.getProperty("label"));
        System.out.println("Reader value: "
                + utf8Reader.getProperty("label"));
        System.out.println("Reader correct: "
                + "café".equals(utf8Reader.getProperty("label")));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 PropertiesEncodingDemo.java
java PropertiesEncodingDemo
~~~

Đầu ra khi console hiển thị Unicode đúng:

~~~text
InputStream value: cafÃ©
Reader value: café
Reader correct: true
~~~

Giải thích:

- UTF-8 của `é` gồm hai byte `C3 A9`.
- `Properties.load(InputStream)` đọc hai byte như hai ký tự ISO-8859-1, tạo `Ã©`.
- `Properties.load(Reader)` nhận `é` đã giải mã bằng UTF-8, nên giữ đúng `café`.
- Nếu terminal dùng charset sai, các dòng chứa ký tự Unicode có thể vẫn **trông khác**. Dòng `Reader correct: true` là kiểm tra trong bộ nhớ, đáng tin hơn quan sát glyph.

### Những điều cần nhớ với Properties

- `Properties.load(Reader)` không bỏ mọi quy tắc của file `.properties`: escape, dấu `=`/`:`, continuation và `\uXXXX` vẫn được xử lý theo cú pháp properties.
- `Properties.store(OutputStream, ...)` sử dụng quy tắc byte stream truyền thống, có thể tạo Unicode escape cho các ký tự không thuộc ISO-8859-1.
- `Properties.store(Writer, ...)` ghi các ký tự qua Writer và charset đã chọn; không phải luôn cho ra byte giống overload OutputStream.
- Nếu lấy `InputStream` từ `ClassLoader.getResourceAsStream(...)`, bản thân `getResourceAsStream` chỉ cung cấp **byte**; bạn vẫn phải chọn đúng lớp decode sau đó.

**Đừng nhầm `Properties` và `PropertyResourceBundle`**: chúng có các quy tắc encoding khác nhau trong Java 9+.

## 9. ResourceBundle .properties trong Java 9+ có quy tắc riêng

`ResourceBundle.getBundle(...)` được dùng để chọn bản dịch theo locale. Với tài nguyên được cung cấp qua `PropertyResourceBundle(InputStream)` trên Java 9+, quy tắc encoding mặc định là:

1. Thử đọc `.properties` theo **UTF-8**.
2. Nếu xảy ra lỗi byte UTF-8 không hợp lệ theo loại lỗi được tài liệu hóa, đọc lại theo **ISO-8859-1**.
3. Nếu muốn chỉ dùng một encoding, có thể chỉ định thuộc tính hệ thống `java.util.PropertyResourceBundle.encoding` bằng giá trị `UTF-8` hoặc `ISO-8859-1` **khi JVM khởi động, trước khi class được khởi tạo**.

Hệ thống đánh giá thuộc tính này **một lần tại thời điểm khởi tạo class** `PropertyResourceBundle`. Gọi `System.setProperty(...)` quá muộn hoặc `ResourceBundle.clearCache()` không biến nó thành tùy chọn encoding có thể thay đổi tùy từng lần đọc.

Đặc biệt, behavior UTF-8 mặc định của `PropertyResourceBundle` **không** làm `Properties.load(InputStream)` chuyển sang UTF-8.

### Ví dụ file tài nguyên UTF-8

Tạo hai file cùng thư mục:

~~~text
demo/
  ResourceBundleUtf8Demo.java
  Messages_vi_VN.properties
~~~

Nội dung `Messages_vi_VN.properties` (lưu **UTF-8**):

~~~properties
welcome=Xin chào, thế giới!
currency=Đồng Việt Nam
~~~

Tạo `ResourceBundleUtf8Demo.java`:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class ResourceBundleUtf8Demo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        ResourceBundle bundle =
                ResourceBundle.getBundle("Messages", locale);

        String message = bundle.getString("welcome");
        System.out.println("Correct value: "
                + "Xin chào, thế giới!".equals(message));
        System.out.println("Message: " + message);
    }
}
~~~

Biên dịch/chạy tại thư mục `demo` bằng Java 17+:

~~~bash
javac -encoding UTF-8 ResourceBundleUtf8Demo.java
java -cp . ResourceBundleUtf8Demo
~~~

Kết quả khi terminal hiển thị Unicode đúng:

~~~text
Correct value: true
Message: Xin chào, thế giới!
~~~

Dòng `Correct value: true` chứng minh giá trị `String` đọc được đúng. Nếu dòng `Message` bị lỗi dấu trong terminal, kiểm tra **đầu ra**, không sửa vội nội dung bundle.

### Chế độ UTF-8 nghiêm ngặt

Khi muốn phát hiện file tài nguyên có byte không hợp lệ thay vì fallback sang Latin-1, có thể chạy:

~~~bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp . ResourceBundleUtf8Demo
~~~

Lưu ý:

- Viết `-D...` **trước tên main class**.
- Giá trị được hỗ trợ là `UTF-8` hoặc `ISO-8859-1` theo Javadoc.
- Nếu cần áp dụng cho chương trình thực, cấu hình từ **lúc startup**, không gọi `System.setProperty` sau khi resource đã được sử dụng.
- Bài test cần kiểm tra đúng base name, package, classpath, locale fallback và nội dung thực sự được đóng gói.

### Resource có Unicode escape

Trong các hệ thống legacy, nội dung có thể được viết:

~~~properties
welcome=Xin ch\u00E0o
~~~

Cú pháp escape giúp biểu diễn Unicode trong file properties ASCII/Latin-1. Nhưng nếu dự án Java 17+ dùng UTF-8 thống nhất, việc giữ nội dung Unicode trực tiếp có thể dễ đọc và review hơn. Chọn một chính sách encoding nhất quán, tránh vừa tự chuyển escape, vừa decode bằng charset khác, khiến khó xác định lỗi.

## 10. Charset của compiler không giống Charset của tệp lúc chạy

Mã nguồn Java cũng là một **tệp có byte**. Trước khi `String` được tạo trong JVM, `javac` phải đọc source file theo encoding phù hợp.

Ví dụ file `Hello.java` chứa literal `"Tiếng Việt"`. Nếu file lưu UTF-8 nhưng compiler đọc bằng một charset khác, literal có thể sai ngay **trong class file**; mọi thao tác Files/ResourceBundle sau đó không thể tự sửa.

Biên dịch chỉ định charset rõ:

~~~bash
javac -encoding UTF-8 Hello.java
~~~

Đây là lệnh minh họa nếu có tệp `Hello.java`. Với dự án thực tế, cấu hình encoding ở hệ thống build:

- Maven: source/resource encoding cần được đặt và kiểm tra theo phiên bản plugin/chuỗi build đang dùng.
- Gradle: cấu hình encoding cho compile task và processing resources nếu có bước lọc/chuyển đổi nội dung.
- IDE: xác minh encoding của tệp và cài đặt compiler tương ứng.
- CI: build lại từ mã nguồn trong môi trường khác, không phụ thuộc encoding của máy dev.

**Lưu ý:** `javac -encoding UTF-8` chỉ áp dụng cho **source files do javac đọc**, không tự đặt encoding của mọi file `.properties`, dữ liệu runtime, terminal hay HTTP response.

### Cẩn thận với tài nguyên bị build tool biến đổi

Một file `Messages_vi_VN.properties` có thể nằm trong thư mục resources, sau đó đi qua các bước lọc biến, copy, minify, merge hoặc đóng gói JAR. Nếu bản nguồn UTF-8 đúng nhưng classpath resource sau build sai byte, lỗi nằm ở **build pipeline**.

Để debug, hãy kiểm tra **file được đóng gói thật** và byte của nó, không chỉ kiểm tra bản nguồn trong IDE. Khi lấy resource từ JAR, `getResourceAsStream` cho byte của bản đóng gói chứ không nhất thiết là file gốc trên máy phát triển.

## 11. Byte Order Mark (BOM) và ký tự U+FEFF

Một số tệp UTF-8 bắt đầu bằng ba byte `EF BB BF`, gọi là **UTF-8 BOM**. Trong một số API đọc văn bản, ba byte này có thể được decode thành ký tự `U+FEFF` ở đầu `String`.

Điều này tạo ra lỗi khó thấy:

- File nhìn như bắt đầu bằng `"name="` nhưng key đầu có thể thực sự là `"\uFEFFname"`.
- So sánh `text.startsWith("name")` có thể trả false.
- Một parser theo giao thức khác có thể chủ động nhận/bỏ BOM, nhưng **không được giả định mọi API đều làm vậy**.

### Ví dụ Java 17+ độc lập

Tạo `Utf8BomDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public class Utf8BomDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("bom-test-", ".txt");

        try {
            byte[] withBom = {
                    (byte) 0xEF, (byte) 0xBB, (byte) 0xBF,
                    (byte) 'H', (byte) 'e',
                    (byte) 'l', (byte) 'l', (byte) 'o'
            };
            Files.write(path, withBom);

            String content =
                    Files.readString(path, StandardCharsets.UTF_8);

            System.out.printf(Locale.ROOT,
                    "First character: U+%04X%n",
                    (int) content.charAt(0));
            System.out.println("Equals Hello: "
                    + content.equals("Hello"));
            System.out.println("Without initial BOM: "
                    + (content.startsWith("\uFEFF")
                        ? content.substring(1) : content));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 Utf8BomDemo.java
java Utf8BomDemo
~~~

Đầu ra:

~~~text
First character: U+FEFF
Equals Hello: false
Without initial BOM: Hello
~~~

Đây là **chính sách loại BOM ở đầu tệp khi hợp đồng file cho phép**, không phải giấy phép xóa mọi `U+FEFF` ở mọi vị trí trong văn bản. Với XML, CSV, JSON, source hoặc format chuyên biệt, cần theo quy định BOM của **giao thức tương ứng**. Không dùng `strip()` để suy rằng nó chắc chắn loại `U+FEFF`.

## 12. Ghi ra output: console và log là một ranh giới byte khác

Đầu ra console không đơn giản là `System.out.println(text)` rồi “Unicode tự đúng”. Có thể có các lớp:

~~~text
String Java đúng
     |
     v
PrintStream / logger encode thành byte
     |
     v
stdout / terminal / CI / redirect / log collector
     |
     v
decoder + font của nơi xem
~~~

Nếu in `"Tiếng Việt"` mà người dùng thấy chuỗi lỗi, thử xác nhận **chuỗi trong bộ nhớ** qua test và kiểm tra **byte xuất ra**. Đừng tự sửa Unicode trong business data chỉ để hợp với terminal đang cấu hình sai.

### Java 18+ không có nghĩa System.out luôn UTF-8

JEP 400 đổi default charset cho phần lớn Java SE API sang UTF-8, nhưng `System.out`/`System.err` có các cân nhắc riêng về charset của console/host. Vì vậy không nên suy “`Charset.defaultCharset()` là UTF-8 nên mọi terminal chắc chắn đọc được UTF-8”.

Thực tế, cần kiểm tra:

- Charset thực tế của console/terminal và cách JVM khởi tạo output stream.
- Charset của log appender/file writer.
- Charset của hệ thống thu thập log/CI.
- Font có glyph cho ngôn ngữ đang in.
- Trường hợp stdout được redirect sang file khác với console tương tác.

Trong Java 17+, `System.console()` có thể bằng `null` nếu chạy dưới IDE/CI/redirect; nếu tồn tại, `System.console().charset()` có thể giúp chẩn đoán charset console. Không dựa vào `System.console()` luôn có giá trị.

### Ví dụ Java 17+ kiểm tra byte output trong bộ nhớ

Thay vì phụ thuộc terminal, tạo một output stream với charset tường minh.

Lưu `OutputEncodingDemo.java`:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class OutputEncodingDemo {
    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();

        try (OutputStreamWriter writer = new OutputStreamWriter(
                output, StandardCharsets.UTF_8)) {
            writer.write("café");
        }

        byte[] bytes = output.toByteArray();
        String decoded = new String(bytes, StandardCharsets.UTF_8);

        System.out.println("Hex: "
                + HexFormat.of().formatHex(bytes));
        System.out.println("Same text: " + "café".equals(decoded));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 OutputEncodingDemo.java
java OutputEncodingDemo
~~~

Đầu ra:

~~~text
Hex: 636166c3a9
Same text: true
~~~

Khi output được tạo bằng `OutputStreamWriter(..., UTF_8)`, có thể kiểm tra byte độc lập với terminal. `OutputStreamWriter` cần được flush/close; ví dụ dùng try-with-resources.

Nếu muốn dùng `PrintStream` cho destination cụ thể, có overload `new PrintStream(output, true, StandardCharsets.UTF_8)` trong Java 17. Tuy nhiên, tạo một PrintStream mới trỏ vào `System.out` không tự bảo đảm console đích diễn giải UTF-8 đúng; phải xét toàn bộ pipeline.

## 13. Chạy chương trình với chuyển hướng output và kiểm tra hex

Khi nghi ngờ terminal, một quy trình QA hữu ích:

1. Chạy chương trình ghi **file UTF-8 có charset tường minh** hoặc chuyển stdout sang file trong môi trường đã biết.
2. Kiểm tra byte hex của output ở bước gần ứng dụng nhất.
3. Đọc lại bằng `Files.readString(path, StandardCharsets.UTF_8)`.
4. So sánh `String` được đọc với expected text trong unit test.
5. Nếu byte đúng mà công cụ mở file hiển thị sai, kiểm tra encoding do **công cụ mở file** lựa chọn.

Ví dụ đọc file đã có `output.txt` được xác nhận là UTF-8:

~~~java
Path path = Path.of("output.txt");
String content = Files.readString(path, StandardCharsets.UTF_8);
System.out.println(content.contains("Tiếng Việt"));
~~~

Đây là **mảnh mã trong method**, cần import `java.nio.file.Path`, `java.nio.file.Files`, `java.nio.charset.StandardCharsets`; file phải được tạo từ trước bằng UTF-8. Kết quả boolean giúp biết nội dung đọc đúng hay không nhưng vẫn cần kiểm tra từng ranh giới nếu pipeline đã làm mất byte.

### Locale không giải quyết lỗi charset

Ví dụ `NumberFormat.getNumberInstance(Locale.GERMANY)` có thể tạo dấu phẩy thập phân và dấu nhóm theo locale Đức. Nhưng khi ghi kết quả ra file, **vẫn phải chọn charset**. Đồng thời, `StandardCharsets.UTF_8` không tự tạo dấu phẩy theo locale Đức.

Sơ đồ trách nhiệm:

~~~text
Giá trị số/ngày
   -> Locale: tạo String có dấu, tên tháng và định dạng đúng
   -> Charset: chuyển String đó thành byte
   -> Destination: nhận byte / lưu trữ
   -> Charset của reader: khôi phục String
   -> Font/renderer: hiển thị glyph
~~~

Không cố xử lý lỗi ở một lớp bằng cách thay đổi một lớp hoàn toàn khác.

## 14. HTTP, JSON và dữ liệu mạng: thêm một bên quyết định encoding

Khi gửi chuỗi qua mạng, cả client và server phải có hợp đồng về byte.

- **JSON** được dùng phổ biến với UTF-8; hãy tuân thủ quy định của giao thức/phiên bản chuẩn JSON đang sử dụng.
- **HTTP Content-Type** và charset có thể tác động cách client hiểu body đối với các media type liên quan; cần đặt header đúng theo API/framework.
- Thư viện HTTP, servlet, JSON mapper có thể encode/decode thay bạn; phải xem cấu hình thực tế và không double-encode.
- Không dùng `String.getBytes()` không tham số cho một giao thức cần byte ổn định giữa máy chủ khác nhau.
- URL encoding/percent-encoding là bài toán cấu trúc URI, **không đồng nhất** với UTF-8 text file encoding dù có liên hệ tại cấp byte.

Ví dụ một API trả JSON chứa `"Xin chào"`: hãy kiểm tra byte response đúng, Content-Type phù hợp và parser JSON bên nhận đã diễn giải đúng. Không suy nội dung sai chỉ vì DevTools/terminal hiển thị một kiểu font lạ.

Nếu có bước chuyển dữ liệu qua database, cần xem **charset của kết nối, kiểu cột và driver**. Với cơ sở dữ liệu, nếu chuỗi trong JVM đúng trước insert nhưng sai sau select, so sánh dữ liệu/byte tại ranh giới driver/database để xác định nguyên nhân.

## 15. Phân biệt “lỗi encoding” với “lỗi Unicode normalization”

Hai chuỗi có dấu có thể hiển thị giống nhau nhưng có code point khác:

~~~text
café       -> ... U+00E9
cafe\u0301 -> ... U+0065 U+0301
~~~

Đó là vấn đề **Unicode canonical equivalence**, không nhất thiết là lỗi đọc byte. Java `Normalizer.Form.NFC` có thể đưa chúng về biểu diễn tương đương chuẩn tắc, nhưng vẫn **giữ dấu**.

Ngược lại:

- `cafÃ©` thường gợi ý mojibake do UTF-8 bị hiểu theo một charset khác.
- `caf�` cho thấy có khả năng byte bất hợp lệ đã bị thay bằng replacement character.
- `caf?` có thể do encoder không biểu diễn được ký tự rồi thay thế.
- `cafe` thay cho `café` có thể là do dữ liệu gốc không dấu hoặc phép biến đổi **cố ý** loại dấu, không nhất thiết là lỗi charset.

Không áp dụng `NFD + replaceAll("\\p{M}+", "")` để “sửa encoding”. Đó là phép **bỏ dấu mất thông tin**, có thể biến `má`, `mã`, `mạ` về cùng `ma`, làm nội dung sai nghĩa.

### In code point để chẩn đoán

~~~java
text.codePoints().forEach(cp ->
        System.out.printf("U+%04X ", cp)
);
~~~

Đây là **mảnh mã trong method** với biến `text`. Kết hợp in code point và byte hex giúp phân biệt trường hợp **ký tự đã sai trong JVM** với trường hợp **ký tự đúng nhưng renderer hiển thị không đúng**.

Nếu làm việc với emoji hoặc ký tự ngoài BMP, `codePoints()` tốt hơn lặp từng `char` khi cần xem mã Unicode thật.

## 16. Bộ kiểm thử end-to-end nên gồm những gì?

Một unit test chỉ kiểm `String.equals` trong bộ nhớ chưa đủ nếu ứng dụng có nhiều ranh giới. Cần dùng cả bài kiểm tra tệp/resource/output trên **đường đi thực tế**.

### Ma trận kiểm thử đề xuất

| Biên giới | Dữ liệu thử | Bằng chứng cần kiểm |
| --- | --- | --- |
| Source → class | `Tiếng Việt`, `café`, `日本語` | `javac -encoding UTF-8`, literal trong JVM đúng |
| String → file | Tiếng Việt, emoji, dấu kết hợp | Byte UTF-8 khớp expected |
| File → String | UTF-8 hợp lệ, UTF-8 lỗi | Round-trip; strict decode phải bắt lỗi |
| Properties InputStream | `label=café` chứa byte UTF-8 | Phát hiện Latin-1 mojibake |
| Properties Reader | Cùng file UTF-8 | Giá trị Unicode khôi phục đúng |
| PropertyResourceBundle | `Messages_vi_VN.properties` | Bản dịch được nạp đúng; policy UTF-8 rõ ràng |
| BOM | File bắt đầu bằng `EF BB BF` | Có/không còn `U+FEFF` theo quy tắc đích |
| OutputWriter | `café` | Byte `63 61 66 C3 A9` |
| Console/log | Nhiều ngôn ngữ, CI và redirect | Tách encoding của stream và decoder phía hiển thị |
| Network/database | UTF-8, tên bản địa hóa | Cả hai phía giữ đúng chuỗi và hợp đồng giao thức |
| Unicode normalization | `é` so với `e + ◌́` | Không nhầm NFC với loại bỏ dấu |
| Unsupported charset | Văn bản Nhật qua Latin-1 | Encoder REPORT thay vì mất dữ liệu âm thầm |

### Dữ liệu mẫu nên đa dạng

Không chỉ test ASCII `"Hello"` vì nhiều charset truyền thống có cùng byte cho ASCII. Bộ dữ liệu có giá trị:

- Tiếng Việt: `"Tiếng Việt, Đặng, Trường"`.
- Latin có dấu: `"café, naïve"`.
- Chữ Nhật: `"日本語"`.
- Chữ Ả Rập: `"مرحبا"`.
- Emoji: `"🌍"`.
- Biểu diễn Unicode phân rã: `"cafe\u0301"`.
- Đầu vào UTF-8 lỗi: byte `C3 28`.
- Tệp có và không có BOM.

Cần kiểm tra **bản thực sự được đóng gói/deploy**, không chỉ file trong source repository. Một số lỗi chỉ xuất hiện sau resource filtering hoặc khi chuyển môi trường Windows/Linux.

## 17. Checklist xử lý sự cố theo dấu hiệu

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
| --- | --- | --- |
| `cafÃ©` | UTF-8 bị giải mã như ISO-8859-1/Windows code page | Hex byte nguồn và charset của reader |
| `caf�` | Byte lỗi hoặc decoder đã thay thế | Có `U+FFFD` trong String không? Strict decoder |
| `caf?` | Encoder không biểu diễn được ký tự | Charset output, chính sách encoder |
| Console lỗi nhưng test String đúng | Charset của output/terminal hoặc font | Hex output/terminal settings, log file UTF-8 |
| File source đúng, runtime bundle sai | Resource filtering/copy/JAR hoặc encoding bundle | Đọc byte của resource sau đóng gói |
| `Properties.load(InputStream)` sai dấu | ISO-8859-1 semantics của API | Đổi sang Reader UTF-8 nếu hợp đồng cho phép |
| `ResourceBundle` sai trong Java 17 | Byte tệp, fallback, config encoding hoặc nhầm resource | Kiểm tra base name, locale, classpath, property startup |
| Key properties bắt đầu bằng ký tự lạ | UTF-8 BOM được giữ dưới dạng U+FEFF | Kiểm tra ba byte đầu và rule BOM |
| Unicode cùng hình nhưng `equals` false | Dạng NFC/NFD khác nhau | In code point, cân nhắc NFC |
| Java 17 OK, Java khác lỗi hoặc ngược lại | Default charset/JDK/provider khác | Truyền `StandardCharsets.UTF_8` tường minh |
| Log ghi đúng nhưng mở file sai dấu | Viewer dùng charset không khớp | Kiểm tra byte và chế độ mở UTF-8 |
| Có chữ sai sau khi chuyển DB | Kết nối, cột, chuyển đổi driver | So String trước insert/sau select |

**Không thử ngẫu nhiên hàng loạt charset để chọn kết quả “trông ổn” rồi ghi đè dữ liệu gốc.** Hãy xác định nguồn byte và hợp đồng encoding, kiểm tra lỗi có thể tái hiện và bảo toàn bản gốc để điều tra.

## 18. Quy trình kiểm soát trong ứng dụng thực tế

Một chính sách hợp lý cho dự án Java đa ngôn ngữ:

1. **Nguồn và tài nguyên UTF-8:** đặt encoding nhất quán trong IDE/build/CI, kiểm tra nội dung JAR cuối.
2. **Tệp và network rõ charset:** dùng overload có `Charset` tường minh; với byte stream, chọn Reader/Writer có encoding tương ứng.
3. **Tách Locale và Charset:** định dạng ngôn ngữ trước, encode khi đi ra ngoài JVM.
4. **Đọc nghiêm ngặt khi cần:** dùng `CharsetDecoder/Encoder` với `REPORT` cho dữ liệu quan trọng.
5. **Không làm mất dấu để che lỗi:** không tự transliteration/strip Mark khi vấn đề là I/O encoding.
6. **Theo dõi điểm chuyển đổi:** log charset, byte length, mã lỗi; tránh đưa thông tin nhạy cảm thô vào log.
7. **Kiểm tra ở CI:** thử nhiều ngôn ngữ, surrogate pair, byte lỗi, BOM, file trong JAR và output redirect.
8. **Chuẩn hóa bản dịch đúng trách nhiệm:** `ResourceBundle` chọn chuỗi theo `Locale`, byte của resource có chính sách encoding độc lập.
9. **Không lưu output đã format làm dữ liệu nguồn:** lưu Unicode đúng và dữ liệu có kiểu; render theo ngữ cảnh người nhận.
10. **Nâng JDK có kiểm thử:** đặc biệt chú ý Java 17 vs 18+ về default charset; giữ các hợp đồng tường minh để giảm thay đổi hành vi.

### Bài tập tự luyện

1. Giải thích vì sao `String.length()`, số Unicode code point và độ dài byte UTF-8 của `"🌍"` là ba con số khác nhau.
2. Ghi `"Tiếng Việt 🌍"` ra tệp UTF-8, đọc lại và kiểm tra cả byte lẫn `String.equals`.
3. Parse byte `C3 28` bằng `CharsetDecoder.REPORT` và bằng `new String(bytes, UTF_8)`. Quan sát khác biệt.
4. Tạo properties chứa `label=café` bằng UTF-8; so kết quả `Properties.load(InputStream)` và `load(Reader UTF8)`.
5. Đọc `Messages_vi_VN.properties` bằng `ResourceBundle.getBundle`. Vì sao kết quả có thể khác `Properties.load(InputStream)`?
6. Chạy `ResourceBundleUtf8Demo` với `-Djava.util.PropertyResourceBundle.encoding=UTF-8` lúc startup. Vì sao đổi property sau khi class đã init không có tác dụng?
7. Tạo file UTF-8 có BOM, dùng `Files.readString` xem ký tự đầu. Khi nào được phép bỏ `U+FEFF`?
8. Viết `OutputStreamWriter` ra `ByteArrayOutputStream` và kiểm tra hex byte của `"café"`. Vì sao test byte mạnh hơn chỉ nhìn console?
9. Một hệ thống có đúng `String` trước khi gọi `println` nhưng sai chữ trong terminal. Hãy liệt kê các ranh giới cần kiểm tra trước khi sửa code xử lý bản dịch.
10. Thử `"caf\u00E9"` và `"cafe\u0301"`; phân biệt vấn đề normalization với charset khi kiểm tra equality.
11. Đưa bài test Unicode vào build Java 17 và Java 21 trên môi trường khác nhau; kiểm chứng việc truyền charset tường minh giúp ổn định kết quả.
12. Nếu API lấy `Locale.US` nhưng đọc file bằng Latin-1, điều gì xảy ra? Vì sao `Locale` không phải giải pháp cho lỗi byte?

**Ghi nhớ:** kiểm tra chuỗi đúng phải đi qua **các ranh giới byte**. Dữ liệu có thể đúng trong `String` nhưng sai khi ghi file, nạp properties hoặc xuất terminal. Dùng `StandardCharsets.UTF_8` rõ ràng, kiểm tra **hex byte và Unicode code point**, round-trip file/resource/output, phân biệt `Properties.load(InputStream)` (ISO-8859-1) với `PropertyResourceBundle` Java 9+ (UTF-8 mặc định và fallback theo tài liệu), và xử lý byte lỗi bằng decoder/encoder nghiêm ngặt khi cần. **Không dùng bỏ dấu, thay ký tự hàng loạt hoặc đổi Locale để che lỗi Charset.**

### Tài liệu tham khảo

- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html) — `readString`, `writeString` và reader/writer.
- [Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html) — các charset chuẩn.
- [Java SE 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html) — malformed/unmappable và `CodingErrorAction`.
- [Java SE 17 — Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html) — `load(InputStream)` vs `load(Reader)`.
- [Java SE 17 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html) — UTF-8 mặc định và cách điều khiển encoding.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400) — default charset thay đổi từ Java 18 và ngoại lệ.
- [Java SE 17 — PrintStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html) — output byte và charset.
- [Unicode Standard Annex #15](https://www.unicode.org/reports/tr15/) — phân biệt Unicode normalization với thay đổi encoding.