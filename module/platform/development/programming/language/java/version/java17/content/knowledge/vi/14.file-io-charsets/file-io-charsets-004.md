# Charset mặc định trên Java 17 và khác biệt giữa môi trường

Một chương trình Java có thể chạy đúng trên máy lập trình viên nhưng đọc sai tiếng Việt, ghi ra tệp bị lỗi dấu hoặc hiển thị ký tự lạ khi chuyển sang máy chủ. Một nguyên nhân phổ biến là **charset mặc định của môi trường khác nhau**.

Trong Java 17, charset mặc định của JVM thường được xác định khi khởi động và phụ thuộc môi trường hệ điều hành/locale. Vì vậy, không thể mặc định rằng mọi ứng dụng Java 17 đều đọc và ghi văn bản bằng UTF-8 nếu code không chỉ định charset.

Điều này thay đổi ở Java 18: JEP 400 đặt UTF-8 làm charset mặc định cho phần lớn API Java trên các nền tảng. Nhưng khi làm việc đúng với **Java 17**, cần hiểu hành vi trước thay đổi đó và chủ động chỉ định charset ở ranh giới đọc/ghi dữ liệu.

## 1. Charset là gì?

**Charset** (*character set and encoding*) xác định cách ánh xạ văn bản thành byte và ngược lại. Máy tính lưu trữ, truyền tải và đọc tệp dưới dạng byte; để hiểu các byte đó thành ký tự, chương trình cần biết quy tắc mã hóa.

Ví dụ, cùng ký tự tiếng Việt `ế` có thể được biểu diễn bằng nhiều byte khác nhau tùy charset. Nếu ghi bằng một charset nhưng đọc bằng charset khác, các byte có thể bị diễn giải thành ký tự sai.

Một số charset thường gặp:

| Charset | Đặc điểm |
| --- | --- |
| `UTF-8` | Mã hóa Unicode độ dài biến đổi từ 1 đến 4 byte cho mỗi code point; tương thích ASCII ở vùng ký tự cơ bản. Phù hợp cho trao đổi văn bản hiện đại. |
| `UTF-16` | Mã hóa Unicode bằng code unit 16 bit; một code point có thể dùng một hoặc hai code unit. |
| `ISO-8859-1` | Mã hóa đơn byte cho một tập ký tự Tây Âu; không biểu diễn đầy đủ tiếng Việt. |
| `windows-1252` | Mã hóa đơn byte thường gặp trong một số môi trường Windows phương Tây; không phải UTF-8 và không biểu diễn đầy đủ tiếng Việt. |

Charset không phải là font chữ. Font quyết định hình dạng ký tự khi hiển thị; charset quyết định cách chuyển giữa ký tự và byte. Đổi font không sửa được dữ liệu đã bị giải mã sai.

### 1.1. Ví dụ cùng một văn bản, byte khác nhau

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class EncodingBytesDemo {
    public static void main(String[] args) {
        String text = "Xin chào";

        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        byte[] utf16 = text.getBytes(StandardCharsets.UTF_16);

        System.out.println(Arrays.toString(utf8));
        System.out.println(Arrays.toString(utf16));
    }
}
```

Hai mảng byte khác nhau nhưng cùng biểu diễn văn bản `Xin chào` theo hai quy tắc mã hóa khác nhau. Muốn đọc lại đúng, phải dùng charset tương ứng với lúc mã hóa.

### 1.2. Độ dài chuỗi không phải độ dài byte

`String.length()` đếm số đơn vị UTF-16 code unit, không đếm số byte trong một charset cụ thể:

```java
import java.nio.charset.StandardCharsets;

public class StringLengthDemo {
    public static void main(String[] args) {
        String text = "Xin chào";

        System.out.println(text.length());
        System.out.println(text.getBytes(StandardCharsets.UTF_8).length);
    }
}
```

Với tiếng Việt có dấu, số byte UTF-8 thường lớn hơn số ký tự. Với ký tự ngoài Basic Multilingual Plane, một code point còn có thể chiếm hai `char` trong Java nhưng được mã hóa thành bốn byte UTF-8.

Khi giao thức yêu cầu độ dài theo byte, hãy đo sau khi encode bằng charset của giao thức, không dùng trực tiếp `String.length()`.

## 2. Charset mặc định của Java 17

API `Charset.defaultCharset()` trả về charset mặc định của JVM:

```java
import java.nio.charset.Charset;

public class DefaultCharsetDemo {
    public static void main(String[] args) {
        Charset charset = Charset.defaultCharset();
        System.out.println(charset.name());
    }
}
```

Trên Java 17, kết quả có thể khác giữa các máy do cấu hình hệ điều hành và locale. Ví dụ, một môi trường có thể dùng UTF-8 trong khi môi trường khác dùng một charset Windows cụ thể.

Các điểm cần nhớ:

- Charset mặc định được xác định khi JVM khởi động; không nên giả định nó thay đổi theo từng request hoặc từng file.
- `Charset.defaultCharset()` cho biết charset mặc định của JVM hiện tại.
- Charset mặc định không nhất thiết là charset của mọi API đọc/ghi trong Java; một số API đã quy định rõ UTF-8.
- Charset dùng cho terminal/console hoặc một giao thức bên ngoài còn có thể có quy tắc riêng.

### 2.1. Vì sao máy developer và máy production có thể khác nhau?

Các môi trường thường khác nhau ở:

- Hệ điều hành và cấu hình locale.
- Code page hoặc cấu hình vùng/ngôn ngữ trên máy.
- Image container và biến môi trường khởi chạy JVM.
- JDK vendor, phiên bản và cấu hình runtime.
- Charset mà một chương trình bên ngoài dùng khi tạo file.
- Cách terminal hoặc công cụ hiển thị byte đầu ra.

Ví dụ, một tệp cấu hình được tạo trên máy dùng UTF-8 có thể chứa byte tiếng Việt mà chương trình Java 17 trên một máy khác đọc bằng charset mặc định khác. Khi giải mã sai, chuỗi nhận được có thể xuất hiện dạng ký tự méo như `ChÃ o` thay vì `Chào`.

Lỗi này không nhất thiết do file bị hỏng. Có thể byte trong file vẫn đúng theo UTF-8, nhưng chương trình đã dùng sai charset để đọc.

### 2.2. Kiểm tra charset trong môi trường chạy

Để chẩn đoán:

```java
import java.nio.charset.Charset;

public class CharsetEnvironment {
    public static void main(String[] args) {
        System.out.println("Default charset: "
                + Charset.defaultCharset().name());
        System.out.println("File encoding property: "
                + System.getProperty("file.encoding"));
        System.out.println("Native encoding property: "
                + System.getProperty("native.encoding"));
    }
}
```

`Charset.defaultCharset()` là API để hỏi charset mặc định. Các system property được in ra có thể hữu ích khi điều tra runtime cụ thể, nhưng không nên dùng việc đọc/đặt property làm thay thế cho việc chỉ định charset trực tiếp trong code.

Không dựa vào kết quả trên máy cá nhân để kết luận mọi JVM Java 17 đều dùng cùng charset.

## 3. Phân biệt Java 17 với Java 18 trở lên

Một thay đổi quan trọng cần biết là **JEP 400 — UTF-8 by Default**, được đưa vào Java 18.

| Phiên bản | Hành vi mặc định |
| --- | --- |
| Java 17 và các phiên bản trước JEP 400 | Charset mặc định thường phụ thuộc hệ điều hành và locale. |
| Java 18 trở lên | UTF-8 trở thành charset mặc định cho phần lớn API Java, trừ các khu vực có charset riêng như console hoặc cấu hình tương thích. |

Do đó, nếu một ứng dụng Java 17 dựa vào charset mặc định mà không chỉ định rõ, việc nâng runtime lên Java 18+ có thể làm hành vi đọc/ghi thay đổi trên một số môi trường.

**JEP 400 không có nghĩa mọi luồng byte đều tự động là UTF-8.** Giao thức mạng, định dạng file, console, thư viện native hoặc API quy định charset riêng vẫn phải tuân thủ hợp đồng của chúng.

Với code cần chạy ổn định trên Java 17 và các JDK mới hơn, hãy chỉ định charset rõ ràng ở mọi nơi chuyển đổi giữa byte và văn bản.

## 4. Dùng UTF-8 tường minh khi đọc và ghi file

Trong Java 17, các overload của `java.nio.file.Files` được thiết kế để đọc/ghi văn bản theo UTF-8 khi không truyền charset. Tuy nhiên, viết tường minh vẫn giúp code thể hiện hợp đồng dữ liệu và tránh nhầm lẫn với các API khác có thể dùng charset mặc định.

### 4.1. Đọc file bằng Files.readString

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadUtf8Demo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("message.txt");

        String content = Files.readString(
                path,
                StandardCharsets.UTF_8);

        System.out.println(content);
    }
}
```

`Files.readString(path, charset)` giải mã byte trong file bằng charset được chỉ định. Nếu file được quy định là UTF-8, truyền `StandardCharsets.UTF_8` để hợp đồng này hiển thị ngay trong code.

### 4.2. Ghi file bằng Files.writeString

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class WriteUtf8Demo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("message.txt");
        String content = "Xin chào Java 17";

        Files.writeString(
                path,
                content,
                StandardCharsets.UTF_8);
    }
}
```

Khi đọc lại bằng UTF-8, nội dung được khôi phục đúng:

```java
String content = Files.readString(
        Path.of("message.txt"),
        StandardCharsets.UTF_8);
```

### 4.3. Files.readAllLines và BufferedReader

Các API văn bản trong `Files` có overload nhận charset:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

List<String> lines = Files.readAllLines(
        Path.of("data.txt"),
        StandardCharsets.UTF_8);

try (var reader = Files.newBufferedReader(
        Path.of("data.txt"),
        StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

`Files.readAllLines(path)` và `Files.newBufferedReader(path)` không truyền charset cũng dùng UTF-8 theo hợp đồng API. Overload tường minh hữu ích khi muốn code tự mô tả định dạng và tránh người đọc suy diễn từ charset mặc định của JVM.

### 4.4. Ghi văn bản theo từng dòng

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (var writer = Files.newBufferedWriter(
        Path.of("report.txt"),
        StandardCharsets.UTF_8)) {
    writer.write("Dòng thứ nhất");
    writer.newLine();
    writer.write("Dòng thứ hai");
}
```

`newBufferedWriter(path, charset, options...)` cho phép chọn charset và các tùy chọn mở file. Nếu cần append, chỉ định `StandardOpenOption.APPEND` và `StandardOpenOption.CREATE` theo yêu cầu.

## 5. Các API dùng charset mặc định nếu không chỉ định

Không phải mọi API Java đều tự chọn UTF-8. Một số constructor/phương thức tiện dụng sử dụng charset mặc định của JVM khi không nhận charset.

| API | Khi không truyền charset |
| --- | --- |
| `new InputStreamReader(inputStream)` | Dùng charset mặc định. |
| `new OutputStreamWriter(outputStream)` | Dùng charset mặc định. |
| `new FileReader(file)` | Dùng charset mặc định. |
| `new FileWriter(file)` | Dùng charset mặc định. |
| `new String(bytes)` | Giải mã bằng charset mặc định. |
| `string.getBytes()` | Mã hóa bằng charset mặc định. |
| `Files.readString(path)` | UTF-8 theo hợp đồng của API. |
| `Files.writeString(path, text)` | UTF-8 theo hợp đồng của API. |
| `Files.newBufferedReader(path)` | UTF-8 theo hợp đồng của API. |
| `Files.newBufferedWriter(path)` | UTF-8 theo hợp đồng của API. |

Điểm quan trọng là phải biết **API cụ thể quy định charset nào**, không thể suy ra tất cả từ `Charset.defaultCharset()`.

### 5.1. Tránh chuyển đổi ngầm qua String(byte[]) và getBytes()

Không nên:

```java
byte[] bytes = text.getBytes();
String decoded = new String(bytes);
```

Hai thao tác này cùng dùng charset mặc định nên có thể tình cờ khôi phục đúng trên một máy, nhưng hành vi không thể hiện rõ hợp đồng dữ liệu và dễ thay đổi giữa môi trường.

Nên:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
```

Khi chuyển đổi hai chiều bằng cùng charset, dữ liệu được giải mã nhất quán theo quy tắc đó.

### 5.2. InputStreamReader và OutputStreamWriter

Nếu làm việc với stream, chỉ định charset ở lớp chuyển đổi byte/char:

```java
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

var reader = new InputStreamReader(
        inputStream,
        StandardCharsets.UTF_8);

var writer = new OutputStreamWriter(
        outputStream,
        StandardCharsets.UTF_8);
```

`InputStream` và `OutputStream` làm việc với byte. `Reader` và `Writer` làm việc với ký tự. `InputStreamReader`/`OutputStreamWriter` là cầu nối giải mã/mã hóa; charset phải khớp với định dạng nguồn hoặc đích.

## 6. Charset của mã nguồn Java khác charset của file dữ liệu

Có hai việc thường bị nhầm:

1. **Mã hóa file nguồn `.java`:** compiler cần biết byte trong file nguồn tương ứng với ký tự nào.
2. **Mã hóa dữ liệu lúc chạy:** ứng dụng cần biết cách đọc/ghi file, stream hoặc giao thức.

Chỉ cấu hình một bên không tự giải quyết bên còn lại.

### 6.1. Chỉ định encoding khi biên dịch

Nếu mã nguồn chứa tiếng Việt hoặc ký tự Unicode, có thể chỉ định rõ:

```bash
javac -encoding UTF-8 -d out src/Hello.java
```

`-encoding UTF-8` quy định charset mà `javac` dùng để đọc file nguồn. Nếu bỏ tùy chọn này, compiler sử dụng charset mặc định của môi trường theo hành vi của phiên bản compiler.

Với dự án build bằng Gradle hoặc Maven, cấu hình encoding của compiler/plugin build cũng cần được thống nhất. Đừng cho rằng source file đã là UTF-8 thì mọi công cụ sẽ tự động đọc nó bằng UTF-8 trong mọi môi trường.

### 6.2. Runtime vẫn cần chỉ định charset

Ví dụ, compiler đọc `Hello.java` bằng UTF-8 không có nghĩa `new FileReader("message.txt")` cũng sẽ đọc file đó bằng UTF-8. Charset source code và charset dữ liệu runtime là hai cấu hình độc lập.

Một ứng dụng có thể biên dịch thành công nhưng vẫn đọc sai file khi chạy nếu API runtime dùng charset khác với charset của file.

## 7. Đọc dữ liệu từ InputStream và ranh giới byte/character

Một stream thường cung cấp byte mà không tự mang thông tin charset. Ứng dụng phải biết giao thức hoặc định dạng dữ liệu quy định charset nào.

Ví dụ:

```java
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.stream.Collectors;

static String readUtf8(InputStream input) throws Exception {
    try (var reader = new BufferedReader(
            new InputStreamReader(input, StandardCharsets.UTF_8))) {
        return reader.lines().collect(Collectors.joining("\n"));
    }
}
```

Trong ứng dụng thực tế, cần làm rõ ai sở hữu stream và ai chịu trách nhiệm đóng nó. Ví dụ trên đóng cả reader và stream bên dưới; nếu stream do caller quản lý, hãy thiết kế hợp đồng đóng tài nguyên cho phù hợp.

### 7.1. Charset phải đến từ hợp đồng giao thức

Nếu đọc HTTP response, email, CSV hoặc file do hệ thống khác tạo:

- Ưu tiên charset được chỉ định trong giao thức/header hoặc định dạng file.
- Nếu đặc tả yêu cầu UTF-8, dùng UTF-8 tường minh.
- Nếu đầu vào không khai báo charset, chỉ áp dụng fallback được đặc tả bởi ứng dụng/giao thức; không đoán theo máy đang chạy.
- Không dùng `Charset.defaultCharset()` làm fallback tùy tiện cho dữ liệu có hợp đồng đã biết.

Ví dụ, một API HTTP có thể khai báo `Content-Type: application/json`. Theo quy tắc JSON hiện đại, dữ liệu trao đổi cần được xử lý theo UTF-8; đừng tự ý giải mã bằng code page của máy chủ.

## 8. Dữ liệu lỗi định dạng và hành vi thay thế ký tự

Khi byte không hợp lệ theo charset, decoder có thể thay thế chuỗi byte lỗi bằng ký tự thay thế (`�`) hoặc báo lỗi, tùy API và cấu hình.

Với các constructor tiện dụng như `new String(bytes, charset)`, hành vi giải mã thường thay thế đầu vào lỗi bằng chuỗi thay thế. Điều này giúp chương trình tiếp tục nhưng có thể che dữ liệu hỏng.

Nếu ứng dụng cần từ chối dữ liệu sai định dạng, dùng `CharsetDecoder` với `CodingErrorAction.REPORT`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUtf8Demo {
    static String decodeStrict(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }
}
```

Các chính sách:

| Chính sách | Hành vi |
| --- | --- |
| `CodingErrorAction.REPORT` | Báo lỗi khi gặp byte không hợp lệ hoặc ký tự không ánh xạ được. |
| `CodingErrorAction.REPLACE` | Thay dữ liệu lỗi bằng chuỗi thay thế. |
| `CodingErrorAction.IGNORE` | Bỏ qua dữ liệu lỗi. |

Với dữ liệu cấu hình, dữ liệu tài chính, dữ liệu định danh hoặc giao thức cần xác thực nghiêm ngặt, `REPORT` có thể giúp phát hiện lỗi sớm. `REPLACE` hoặc `IGNORE` chỉ nên dùng khi chính sách ứng dụng cho phép mất hoặc thay thế dữ liệu.

## 9. BOM và các định dạng file

Một số file văn bản có thể bắt đầu bằng BOM (*Byte Order Mark*). BOM là dấu hiệu ở đầu luồng byte được một số định dạng sử dụng để nhận diện encoding hoặc thứ tự byte.

Với UTF-8, BOM là ba byte `EF BB BF`. UTF-8 không cần BOM để xác định thứ tự byte; nhiều định dạng vẫn có thể cho phép hoặc phát sinh BOM.

Không nên mặc định mọi decoder UTF-8 đều tự loại bỏ BOM theo cách mà ứng dụng mong muốn. Khi đọc file, hãy theo đặc tả định dạng:

- Nếu định dạng cho phép BOM, xử lý đúng theo đặc tả.
- Nếu định dạng cấm BOM, từ chối hoặc xử lý như dữ liệu sai định dạng.
- Nếu ứng dụng cần bỏ BOM đầu file, chỉ bỏ đúng dấu ở vị trí đầu và không xóa ký tự `U+FEFF` tùy tiện ở giữa nội dung.

Đừng nhầm BOM với charset mặc định của JVM. BOM là đặc điểm của nội dung file; charset mặc định là cấu hình môi trường Java.

## 10. Khác biệt giữa charset mặc định và charset của console

Một chương trình có thể đọc file UTF-8 đúng nhưng hiển thị tiếng Việt sai trong terminal. Khi đó, cần kiểm tra cả hai phía:

1. Byte được chương trình ghi ra `System.out` được mã hóa bằng charset nào.
2. Terminal/console giải mã và hiển thị byte theo encoding nào.
3. Font terminal có glyph cần thiết hay không.

Charset mặc định của JVM không phải lúc nào cũng mô tả đầy đủ encoding của console. Trong Java 17, cấu hình console và môi trường native có thể có quy tắc riêng. Vì vậy, nếu chỉ lỗi ở màn hình terminal mà file output đúng, hãy kiểm tra terminal/console thay vì đổi charset file một cách mù quáng.

Đối với file, log hoặc giao thức cần định dạng ổn định, hãy chọn charset tường minh ở writer/encoder. Đối với console, làm theo cấu hình của môi trường terminal và cách JVM khởi tạo standard streams.

## 11. Ví dụ thực hành: cùng code chạy trên nhiều môi trường

Giả sử một ứng dụng đọc file `customers.txt` có nội dung UTF-8:

```text
KH001,Nguyễn An
KH002,Trần Bình
```

### 11.1. Cách phụ thuộc charset mặc định

```java
import java.io.BufferedReader;
import java.io.FileReader;

public class DefaultReaderDemo {
    public static void main(String[] args) throws Exception {
        try (BufferedReader reader =
                     new BufferedReader(new FileReader("customers.txt"))) {
            reader.lines().forEach(System.out::println);
        }
    }
}
```

`FileReader(String)` dùng charset mặc định. Trên máy có default charset khác UTF-8, nội dung tiếng Việt có thể bị giải mã sai.

### 11.2. Cách chỉ định UTF-8

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ExplicitUtf8ReaderDemo {
    public static void main(String[] args) throws Exception {
        try (BufferedReader reader = Files.newBufferedReader(
                Path.of("customers.txt"),
                StandardCharsets.UTF_8)) {
            reader.lines().forEach(System.out::println);
        }
    }
}
```

Code này thể hiện rõ file được đọc theo UTF-8, không phụ thuộc default charset của Java 17.

### 11.3. Ghi file UTF-8 ổn định

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ExplicitUtf8WriterDemo {
    public static void main(String[] args) throws Exception {
        String content = "KH001,Nguyễn An\nKH002,Trần Bình\n";

        Files.writeString(
                Path.of("customers-export.txt"),
                content,
                StandardCharsets.UTF_8);
    }
}
```

Khi chương trình khác đọc file này, nó cần biết file được mã hóa UTF-8. Đây là hợp đồng dữ liệu ổn định, không phụ thuộc máy tạo file.

## 12. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Tiếng Việt thành `ChÃ o` hoặc ký tự lạ | Byte UTF-8 bị giải mã bằng charset khác | Xác định charset file và dùng đúng charset khi đọc. |
| Chạy trên Windows khác Linux | Java 17 có thể dùng default charset khác theo môi trường | Không dựa vào default; chỉ định UTF-8 hoặc charset của giao thức. |
| `String.length()` khác số byte file | Độ dài ký tự và độ dài byte là hai đơn vị khác nhau | Encode bằng charset cụ thể rồi lấy độ dài mảng byte. |
| `FileReader` đọc sai dấu | Constructor không charset dùng default charset | Dùng constructor nhận `Charset` hoặc `Files.newBufferedReader(path, charset)`. |
| Source `.java` lỗi ký tự khi compile | `javac` đọc file bằng charset khác với charset nguồn | Dùng `javac -encoding UTF-8` hoặc cấu hình build tương ứng. |
| File UTF-8 đúng nhưng terminal hiển thị sai | Encoding console hoặc font terminal khác | Kiểm tra standard output, terminal encoding và font. |
| Ký tự `�` xuất hiện | Byte đầu vào không hợp lệ theo charset hoặc đã bị giải mã sai trước đó | Kiểm tra byte gốc và dùng decoder `REPORT` nếu cần phát hiện lỗi. |
| Java 17 và Java mới hơn đọc cùng code khác nhau | Code phụ thuộc default charset; Java 18 thay đổi mặc định theo JEP 400 | Chỉ định charset tường minh ở API chuyển đổi byte/char. |

## 13. Nguyên tắc thiết kế để không phụ thuộc môi trường

1. **Xác định charset của dữ liệu ở ranh giới hệ thống.** File, HTTP, message queue và database cần có hợp đồng encoding rõ.
2. **Dùng `StandardCharsets.UTF_8` khi định dạng yêu cầu UTF-8.** Không dùng charset mặc định thay cho một hợp đồng đã biết.
3. **Chỉ dùng `Charset.defaultCharset()` để chẩn đoán hoặc khi thật sự muốn theo mặc định môi trường.** Đừng dùng nó cho định dạng trao đổi cần ổn định.
4. **Phân biệt byte và ký tự.** `String.length()` không phải số byte UTF-8.
5. **Chỉ định encoding của source code khi build nếu cần.** Ví dụ `javac -encoding UTF-8`.
6. **Xử lý dữ liệu lỗi theo chính sách rõ ràng.** Chọn `REPORT`, `REPLACE` hoặc `IGNORE` có chủ đích.
7. **Kiểm tra cả đầu vào và đầu ra.** Đọc đúng không đảm bảo ghi đúng nếu writer dùng charset khác.
8. **Không nhầm charset với locale, timezone hoặc font.** Chúng giải quyết những vấn đề khác nhau.
9. **Kiểm thử trên runtime mục tiêu.** Đặc biệt nếu ứng dụng hỗ trợ Java 17 và các phiên bản mới hơn.

## 14. Câu hỏi tự kiểm tra

**1. Charset mặc định của Java 17 có luôn là UTF-8 không?**  
Không. Trước JEP 400, charset mặc định thường phụ thuộc hệ điều hành và locale của môi trường JVM.

**2. API nào cho biết charset mặc định của JVM?**  
`Charset.defaultCharset()`.

**3. Java 18 thay đổi điều gì liên quan đến charset mặc định?**  
JEP 400 đặt UTF-8 làm mặc định cho phần lớn API Java từ Java 18, với một số ngoại lệ như console.

**4. Vì sao nên dùng `StandardCharsets.UTF_8` khi đọc file UTF-8?**  
Vì code thể hiện rõ hợp đồng encoding và hoạt động nhất quán giữa các môi trường.

**5. `Files.readString(path)` trong Java 17 dùng charset nào nếu không truyền charset?**  
UTF-8 theo hợp đồng của API.

**6. `new FileReader(file)` trong Java 17 dùng charset nào nếu không truyền charset?**  
Charset mặc định của JVM.

**7. `String.length()` có cho biết số byte UTF-8 không?**  
Không. Nó đếm UTF-16 code unit; cần encode rồi lấy độ dài mảng byte nếu muốn số byte.

**8. `javac -encoding UTF-8` ảnh hưởng đến điều gì?**  
Charset compiler dùng để đọc file nguồn Java; nó không tự cấu hình charset đọc/ghi file lúc runtime.

**9. Làm sao phát hiện byte UTF-8 không hợp lệ thay vì âm thầm thay bằng ký tự thay thế?**  
Dùng `CharsetDecoder` và đặt `CodingErrorAction.REPORT`.

**10. Vì sao file hiển thị sai trong terminal dù đọc bằng UTF-8?**  
Encoding của console/terminal hoặc font có thể không khớp; cần kiểm tra cả phía xuất byte và phía hiển thị.

## Tài liệu tham khảo chính thức

- [Java SE 17 API — `Charset`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html): charset mặc định và cơ chế mã hóa/giải mã.
- [Java SE 17 API — `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn như UTF-8, UTF-16 và ISO-8859-1.
- [Java SE 17 API — `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): các API đọc/ghi văn bản và overload nhận charset.
- [Java SE 17 API — `InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html) và [`OutputStreamWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html): cầu nối giữa byte stream và character stream.
- [Java SE 17 API — `CharsetDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html) và [`CodingErrorAction`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html): kiểm soát lỗi khi giải mã.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi charset mặc định từ Java 18.
- [Java SE 17 javac Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): tùy chọn `-encoding` cho file nguồn.
