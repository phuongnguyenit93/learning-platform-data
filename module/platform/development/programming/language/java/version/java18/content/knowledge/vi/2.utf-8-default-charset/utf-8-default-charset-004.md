# `Charset.defaultCharset()` và các API thực sự sử dụng charset mặc định

## 1. Vì sao cần biết API nào dùng charset mặc định?

Từ Java 18, **UTF-8 là charset mặc định** của Java SE theo **JEP 400**. Khi gọi `Charset.defaultCharset()` trong cấu hình thông thường trên JDK 18 trở lên, chương trình nhận về `UTF-8`. Thay đổi này làm hành vi của nhiều API nhập xuất văn bản ổn định hơn giữa Windows, Linux, macOS và các môi trường triển khai.

Tuy nhiên, không phải API nào xử lý văn bản cũng dùng charset mặc định. Có API dùng default charset khi bạn bỏ qua tham số, có API đã quy định UTF-8 cố định từ trước, có API buộc người gọi truyền charset, và có API chỉ thao tác trên ký tự nên không tự quyết định cách chuyển đổi byte.

Nếu không phân biệt các nhóm đó, ta dễ mắc hai lỗi:

- Nghĩ rằng mọi API đọc/ghi văn bản đều đổi sang UTF-8 nhờ JEP 400.
- Nghĩ rằng mọi API không có tham số charset đều gọi `Charset.defaultCharset()`.

Bài này thuộc chương **UTF-8 mặc định** của `JAVA_VERSION_JAVA18`. Mục tiêu là nhận diện đúng hợp đồng của API trên JDK hiện đại, hiểu ngoại lệ của luồng chuẩn và biết cách kiểm tra mã nguồn đang phụ thuộc vào default charset ở đâu.

## 2. `Charset.defaultCharset()` trả về điều gì?

`java.nio.charset.Charset` đại diện cho một charset dùng để mã hóa và giải mã văn bản. Phương thức tĩnh `Charset.defaultCharset()` trả về charset mặc định của JVM hiện tại.

```java
import java.nio.charset.Charset;

Charset charset = Charset.defaultCharset();
System.out.println(charset.name());
```

Trong cấu hình thông thường của JDK 18 trở lên, kết quả là:

```text
UTF-8
```

Trước JDK 18, charset mặc định thường được xác định theo hệ điều hành, locale và môi trường khi JVM khởi động. Ví dụ, một máy Windows có thể dùng `windows-1252` hoặc `windows-31j`, trong khi máy khác dùng UTF-8. Điều này làm cho cùng một lời gọi chuyển đổi byte–văn bản có thể cho kết quả khác nhau giữa các máy.

JEP 400 chuẩn hóa mặc định thành UTF-8 từ JDK 18. Vì vậy, các API **thật sự phụ thuộc** `Charset.defaultCharset()` sẽ dùng UTF-8 theo mặc định trong các lần chạy thông thường trên JDK 18+.

### 2.1. Có thể kiểm tra charset mặc định và cấu hình khởi động

```java
import java.nio.charset.Charset;

System.out.println("defaultCharset = "
        + Charset.defaultCharset().name());
System.out.println("file.encoding = "
        + System.getProperty("file.encoding"));
System.out.println("native.encoding = "
        + System.getProperty("native.encoding"));
```

- `defaultCharset` là kết quả trực tiếp của API `Charset.defaultCharset()`.
- `file.encoding` liên quan đến cấu hình default charset của JDK.
- `native.encoding` cho biết encoding của môi trường gốc. Giá trị này có thể khác UTF-8 và hữu ích khi điều tra khả năng tương thích với môi trường cũ.

Trên JDK 18+, tùy chọn khởi động được đặc tả để chọn một trong hai chế độ:

```bash
java -Dfile.encoding=UTF-8 MyApplication
java -Dfile.encoding=COMPAT MyApplication
```

| Giá trị khi khởi động | Kết quả |
| --- | --- |
| `UTF-8` | Dùng UTF-8 làm default charset. Đây cũng là mặc định thông thường từ JDK 18. |
| `COMPAT` | Dùng default charset theo cách tương thích với JDK 17 trở về trước, dựa trên encoding môi trường gốc. |

Các giá trị khác của `file.encoding` không được hỗ trợ. Khi dùng `COMPAT`, giá trị runtime của `file.encoding` có thể được thay bằng giá trị `native.encoding`; không nên giả định rằng đọc lại property sẽ luôn nhận nguyên văn chuỗi `COMPAT`.

Thiết lập này phải được truyền lúc khởi động JVM. Gọi `System.setProperty("file.encoding", "...")` sau khi chương trình chạy không phải cách được hỗ trợ để thay đổi charset mặc định mà các API đang dùng.

**Vai trò của `COMPAT`:** chủ yếu phục vụ kiểm tra và chuyển đổi ứng dụng cũ. Định dạng file, giao thức hoặc dữ liệu trao đổi vẫn nên xác định charset rõ ràng tại điểm nhập xuất.

## 3. Các API thực sự dùng default charset

Khi một overload không nhận tham số charset, một số API Java SE chọn `Charset.defaultCharset()`. Trên JDK 18+ thông thường, chúng vì thế dùng UTF-8. Các nhóm quan trọng được Oracle liệt kê gồm `java.io` và `java.util`.

### 3.1. `String` chuyển đổi byte mà không chỉ định charset

Hai lời gọi sau phụ thuộc default charset:

- `new String(byte[])`: giải mã byte thành `String` bằng charset mặc định.
- `String.getBytes()`: mã hóa `String` thành `byte[]` bằng charset mặc định.

```java
import java.nio.charset.Charset;
import java.util.Arrays;

String text = "Tiếng Việt: cà phê";
byte[] implicitBytes = text.getBytes();
byte[] utf8Bytes = text.getBytes(Charset.forName("UTF-8"));

System.out.println(Charset.defaultCharset());
System.out.println(Arrays.equals(implicitBytes, utf8Bytes));
```

Trong cấu hình JDK 18+ mặc định, kết quả so sánh là `true`. Nếu chạy với `-Dfile.encoding=COMPAT` trên môi trường có default charset khác UTF-8, kết quả có thể là `false`.

Khi hợp đồng dữ liệu yêu cầu UTF-8, hãy dùng overload tường minh:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
```

Điều này khiến code thể hiện rõ quy tắc dữ liệu, không phụ thuộc cấu hình JVM.

### 3.2. `java.io`: reader và writer dạng byte–ký tự

Các constructor không truyền charset trong nhóm sau sử dụng default charset:

| API | Hướng chuyển đổi | Ví dụ không chỉ định charset |
| --- | --- | --- |
| `InputStreamReader` | Byte → ký tự | `new InputStreamReader(inputStream)` |
| `FileReader` | Byte của file → ký tự | `new FileReader(file)` |
| `OutputStreamWriter` | Ký tự → byte | `new OutputStreamWriter(outputStream)` |
| `FileWriter` | Ký tự → byte của file | `new FileWriter(file)` |

Một chi tiết của hợp đồng `OutputStreamWriter`: nếu `outputStream` thực chất là một `PrintStream`, constructor không charset sẽ dùng charset của `PrintStream` đó. Với một `OutputStream` thông thường, nó dùng default charset. Vì vậy cần xem cả kiểu đối tượng được truyền vào, không chỉ chữ ký biến ở nơi gọi.

Ví dụ:

```java
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;

try (FileWriter writer = new FileWriter("note.txt")) {
    writer.write("Chào bạn");
}

try (FileReader reader = new FileReader("note.txt")) {
    char[] buffer = new char[128];
    int count = reader.read(buffer);
    System.out.println(new String(buffer, 0, count));
}
```

Trong cấu hình thông thường của JDK 18+, file được ghi và đọc bằng UTF-8. Nhưng hai constructor này vẫn có nghĩa là **dùng default charset**. Nếu ứng dụng được khởi chạy với `-Dfile.encoding=COMPAT`, chúng có thể dùng charset theo môi trường cũ.

Các overload hiện đại cho phép truyền `Charset` trực tiếp:

```java
import java.io.FileReader;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;

try (FileWriter writer =
             new FileWriter("note.txt", StandardCharsets.UTF_8)) {
    writer.write("Chào bạn");
}

try (FileReader reader =
             new FileReader("note.txt", StandardCharsets.UTF_8)) {
    // Đọc theo UTF-8 được xác định rõ.
}
```

`FileReader` và `FileWriter` có constructor nhận `Charset` trên các JDK hiện đại. Khi định dạng file đã quy định UTF-8, hãy chọn overload đó hoặc dùng các API `Files` được trình bày ở phần sau.

### 3.3. `PrintStream`, `Formatter` và `Scanner`

Các API tiện ích này cũng có overload phụ thuộc default charset:

| API | Constructor phụ thuộc default charset | Ghi chú |
| --- | --- | --- |
| `PrintStream` | `new PrintStream(outputStream)`, `new PrintStream(file)` | Mã hóa theo default charset; nếu `outputStream` bản thân là `PrintStream`, charset của stream đó được kế thừa. |
| `Formatter` | `new Formatter(outputStream)`, `new Formatter(file)`, `new Formatter(fileName)` | Dùng default charset khi đích là luồng byte hoặc file và không truyền charset. |
| `Scanner` | `new Scanner(inputStream)`, `new Scanner(file)`, `new Scanner(path)` | Giải mã byte của nguồn đầu vào bằng default charset. |

Ví dụ với `Scanner`:

```java
import java.nio.file.Path;
import java.util.Scanner;

try (Scanner scanner = new Scanner(Path.of("input.txt"))) {
    while (scanner.hasNextLine()) {
        System.out.println(scanner.nextLine());
    }
}
```

Nếu file đầu vào có hợp đồng UTF-8, nên truyền charset:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Scanner;

try (Scanner scanner =
             new Scanner(Path.of("input.txt"), StandardCharsets.UTF_8)) {
    while (scanner.hasNextLine()) {
        System.out.println(scanner.nextLine());
    }
}
```

`Scanner` và `Formatter` cũng có overload nhận `Charset`. Một khi nguồn đã là `Reader` hoặc đích đã là `Writer`, charset được quyết định bởi reader/writer đó; bản thân các API ký tự này không tự giải mã hay mã hóa thêm lần nữa.

Với `Formatter(PrintStream)`, ký tự được ghi qua `PrintStream` đã cho nên dùng charset của stream đó. Không nên suy luận rằng mọi constructor của `Formatter` đều dùng cùng một charset.

### 3.4. Cách truyền charset tường minh cho từng API

| API | Ví dụ chỉ định UTF-8 |
| --- | --- |
| `String` | `text.getBytes(StandardCharsets.UTF_8)` |
| `String` | `new String(bytes, StandardCharsets.UTF_8)` |
| `InputStreamReader` | `new InputStreamReader(in, StandardCharsets.UTF_8)` |
| `OutputStreamWriter` | `new OutputStreamWriter(out, StandardCharsets.UTF_8)` |
| `FileReader` | `new FileReader(file, StandardCharsets.UTF_8)` |
| `FileWriter` | `new FileWriter(file, StandardCharsets.UTF_8)` |
| `PrintStream` | `new PrintStream(out, true, StandardCharsets.UTF_8)` |
| `Scanner` | `new Scanner(path, StandardCharsets.UTF_8)` |
| `Formatter` | `new Formatter(file, StandardCharsets.UTF_8, Locale.ROOT)` |

Những overload nhận `Charset` giúp người đọc hiểu ngay encoding của dữ liệu, đồng thời tránh việc cấu hình khởi động làm thay đổi hành vi.

## 4. Các API văn bản không dùng default charset

Không phải cứ bỏ tham số charset là API sẽ dùng `Charset.defaultCharset()`. Một số API đã quy định UTF-8 cố định trong hợp đồng của chúng, kể cả trước khi JEP 400 xuất hiện.

### 4.1. Các phương thức văn bản mặc định UTF-8 của `Files`

Các phương thức sau dùng UTF-8 khi không truyền charset:

- `Files.newBufferedReader(path)`
- `Files.newBufferedWriter(path, options...)`
- `Files.readAllLines(path)`
- `Files.readString(path)`
- `Files.writeString(path, text, options...)`

Ví dụ:

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("vietnamese.txt");
Files.writeString(file, "Xin chào Việt Nam");

String text = Files.readString(file);
System.out.println(text);
```

`Files.writeString(path, text)` và `Files.readString(path)` vẫn dùng UTF-8 khi chạy với `-Dfile.encoding=COMPAT`. Hợp đồng của các overload này quy định UTF-8, không gọi default charset của JVM.

Có thể truyền `StandardCharsets.UTF_8` tường minh để làm rõ ý định:

```java
Files.writeString(file, "Xin chào Việt Nam",
        StandardCharsets.UTF_8);

String text = Files.readString(file, StandardCharsets.UTF_8);
```

Những phương thức này được bổ sung từ Java 11; việc chúng dùng UTF-8 mặc định đã tồn tại trước JEP 400. JEP 400 mở rộng tính nhất quán sang các API phụ thuộc default charset khác.

### 4.2. `Properties.load(InputStream)` có encoding cố định

Một ngoại lệ quan trọng khác: `Properties.load(InputStream)` đọc byte theo **ISO-8859-1** theo hợp đồng API. Phương thức này không dùng default charset và cũng không tự đổi sang UTF-8 theo JEP 400.

Nếu file properties được lưu bằng UTF-8, dùng `Reader` để chủ động giải mã:

```java
import java.io.InputStream;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

Path path = Path.of("app.properties");
Properties properties = new Properties();

try (Reader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    properties.load(reader);
}
```

`Properties.load(Reader)` nhận ký tự đã được giải mã, nên charset do `Reader` quyết định. Điều này khác `Properties.load(InputStream)`, vốn có quy tắc encoding cố định riêng.

### 4.3. API chỉ xử lý ký tự không tự chọn charset

`Reader`, `Writer`, `StringBuilder`, `StringBuffer` và nhiều API xử lý chuỗi làm việc với dữ liệu ký tự đã có. Chúng không có byte để tự giải mã hoặc mã hóa nếu không được kết nối với luồng byte.

Ví dụ:

- `StringBuilder.append(text)` nối nội dung văn bản.
- `BufferedReader(Reader)` đọc từ một nguồn đã chuyển thành ký tự.
- `BufferedWriter(Writer)` ghi vào một đích đã quyết định cách chuyển đổi byte.
- `Scanner(Readable)` đọc từ một nguồn `Readable` đã cung cấp ký tự.

Nếu cần biết charset, hãy lần theo reader/writer hoặc stream ở ranh giới byte, thay vì tìm một cấu hình default trong mọi lớp xử lý chuỗi.

## 5. Luồng chuẩn không dùng cùng charset với default charset

Đây là ngoại lệ rất dễ bị bỏ sót.

Các luồng chuẩn:

- `System.in`: đầu vào chuẩn, kiểu `InputStream`.
- `System.out`: đầu ra chuẩn, kiểu `PrintStream`.
- `System.err`: đầu ra lỗi chuẩn, kiểu `PrintStream`.

Charset của chúng được xác định riêng qua các system property:

| Luồng | Property |
| --- | --- |
| `System.in` | `stdin.encoding` |
| `System.out` | `stdout.encoding` |
| `System.err` | `stderr.encoding` |

`System.in` bản thân là một `InputStream` chứa byte, không phải một reader có charset. `stdin.encoding` cho biết charset cần dùng để giải mã byte từ đầu vào chuẩn. Tương tự, `stdout.encoding` và `stderr.encoding` là charset của hai luồng in chuẩn được JVM thiết lập.

Các giá trị này phụ thuộc nền tảng và môi trường console; chúng có thể khác `file.encoding`, `native.encoding` và `Charset.defaultCharset()`.

### 5.1. Kiểm tra charset thực tế của đầu ra console

Từ Java 18, `PrintStream.charset()` trả về charset mà một đối tượng `PrintStream` sử dụng. Có thể kiểm tra `System.out` và `System.err`:

```java
System.out.println("Default charset: "
        + java.nio.charset.Charset.defaultCharset().name());

System.out.println("System.out charset: "
        + System.out.charset().name());

System.err.println("System.err charset: "
        + System.err.charset().name());
```

`System.out` và `System.err` là các print stream được JVM thiết lập đặc biệt. Không lấy việc `Charset.defaultCharset()` trả về UTF-8 làm bằng chứng rằng terminal chắc chắn nhận UTF-8.

### 5.2. Đọc `System.in` theo charset của nguồn nhập

`System.in` là luồng byte. Nếu dùng `new InputStreamReader(System.in)` hoặc `new Scanner(System.in)` không truyền charset, lớp chuyển đổi sẽ dùng default charset.

Khi đọc dữ liệu terminal, tài liệu Java khuyến nghị dùng charset được chỉ định bởi `stdin.encoding`:

```java
import java.nio.charset.Charset;
import java.util.Scanner;

String inputCharset = System.getProperty("stdin.encoding");
if (inputCharset == null) {
    throw new IllegalStateException(
            "Môi trường không cung cấp stdin.encoding");
}

Scanner scanner = new Scanner(
        System.in, Charset.forName(inputCharset));

// Đọc dữ liệu tương tác theo encoding của stdin.
String line = scanner.nextLine();
```

Trong ứng dụng thực tế, chỉ sử dụng property này cho luồng nhập chuẩn của môi trường cung cấp nó. Với file, socket hoặc giao thức khác, charset phải lấy từ hợp đồng của nguồn dữ liệu.

Nếu ứng dụng dùng `System.console()` để tương tác, các thao tác đọc/ghi của `Console` cũng sử dụng encoding tương ứng của đầu vào và đầu ra console. Đừng đánh đồng chúng với charset mặc định của JVM.

### 5.3. `Scanner(System.in)` và `Formatter(System.out)` có ý nghĩa khác nhau

`Scanner(System.in)` nhận `InputStream` nên constructor không truyền charset sẽ dùng default charset để giải mã byte. Nếu nguồn nhập terminal dùng charset riêng, cần chọn `stdin.encoding` như ví dụ trên.

`Formatter(System.out)` nhận `PrintStream` nên ghi ký tự qua charset của `System.out`. Nó không tạo một bộ chuyển đổi độc lập dùng default charset.

Sự khác biệt nằm ở **loại đối số constructor**: một bên nhận luồng byte đầu vào, một bên nhận print stream đã biết cách mã hóa.

## 6. Công cụ biên dịch cũng có charset đầu vào riêng

Ngoài API chạy ứng dụng, encoding của file nguồn `.java` cũng cần được xác định khi biên dịch. `javac` mặc định đọc mã nguồn theo charset mặc định của môi trường JDK nếu không có tùy chọn `-encoding`.

Với mã nguồn được lưu bằng UTF-8, nên khai báo rõ:

```bash
javac -encoding UTF-8 MyApplication.java
```

Điều này đặc biệt quan trọng khi mã nguồn chứa tiếng Việt trong comment, string literal hoặc text block. Default charset của runtime và charset mà một lệnh biên dịch sử dụng là hai bước khác nhau trong quy trình build; cấu hình build nên thể hiện rõ encoding của source file.

## 7. Ví dụ tổng hợp: API nào bị ảnh hưởng bởi `COMPAT`?

Chương trình sau so sánh một API phụ thuộc default charset với một API có UTF-8 cố định:

```java
import java.io.FileReader;
import java.io.IOException;
import java.io.Reader;
import java.io.StringWriter;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class DefaultCharsetApiDemo {
    public static void main(String[] args) throws IOException {
        Path file = Path.of("sample.txt");
        String original = "Tiếng Việt: cà phê";

        // Files.writeString không truyền charset vẫn ghi UTF-8.
        Files.writeString(file, original);

        // Files.readString không truyền charset vẫn đọc UTF-8.
        String fromFiles = Files.readString(file);

        // FileReader không truyền charset dùng default charset.
        String fromFileReader;
        try (Reader reader = new FileReader(file.toFile())) {
            StringWriter buffer = new StringWriter();
            reader.transferTo(buffer);
            fromFileReader = buffer.toString();
        }

        System.out.println("Default: " + Charset.defaultCharset());
        System.out.println("Files matches: "
                + original.equals(fromFiles));
        System.out.println("FileReader matches: "
                + original.equals(fromFileReader));

        // Cách xác định encoding rõ ràng cho FileReader.
        try (Reader reader =
                     new FileReader(file.toFile(), StandardCharsets.UTF_8)) {
            StringWriter buffer = new StringWriter();
            reader.transferTo(buffer);
            System.out.println("Explicit FileReader matches: "
                    + original.equals(buffer.toString()));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 DefaultCharsetApiDemo.java
java DefaultCharsetApiDemo
java -Dfile.encoding=COMPAT DefaultCharsetApiDemo
```

Trong lần chạy mặc định JDK 18+, kết quả dự kiến:

```text
Default: UTF-8
Files matches: true
FileReader matches: true
Explicit FileReader matches: true
```

Trong lần chạy `COMPAT`:

- `Files matches` vẫn là `true` vì `Files.writeString` và `Files.readString` dùng UTF-8 cố định.
- `Explicit FileReader matches` vẫn là `true` vì charset đã được chỉ định.
- `FileReader matches` phụ thuộc default charset của môi trường. Nếu `COMPAT` chọn charset khác UTF-8, kết quả có thể sai.

Nếu máy đang có native encoding là UTF-8, chạy `COMPAT` vẫn cho kết quả UTF-8; vì vậy kết quả giống nhau trên một máy không chứng minh code không phụ thuộc default charset. Hãy kiểm thử trên môi trường có native encoding khác UTF-8 hoặc rà soát các lời gọi API trong mã nguồn.

## 8. Cách rà soát codebase khi nâng cấp JDK

Khi chuyển ứng dụng từ JDK 17 hoặc cũ hơn lên JDK 18+, nên tìm các điểm chuyển đổi văn bản–byte không chỉ định charset.

| Từ khóa nên tìm | Vì sao cần xem lại |
| --- | --- |
| `getBytes()` | Mã hóa theo default charset |
| `new String(byte[])` | Giải mã theo default charset |
| `new FileReader(...)` | Constructor không charset dùng default charset |
| `new FileWriter(...)` | Constructor không charset dùng default charset |
| `new InputStreamReader(...)` | Overload chỉ nhận luồng byte dùng default charset |
| `new OutputStreamWriter(...)` | Overload chỉ nhận luồng byte dùng default charset |
| `new Scanner(InputStream/File/Path)` | Các overload này dùng default charset |
| `new Formatter(OutputStream/File)` | Các overload này dùng default charset |
| `new PrintStream(OutputStream/File)` | Các overload này dùng default charset, trừ trường hợp kế thừa charset của print stream |

Khi tìm thấy lời gọi, hãy trả lời ba câu hỏi:

1. **Nguồn hoặc đích dữ liệu quy định charset gì?** Ví dụ, file cũ có thể là Windows-1258, trong khi giao thức HTTP hoặc file mới quy định UTF-8.
2. **API đang dùng overload nào?** Kiểm tra chữ ký constructor/phương thức cụ thể. Overload không có charset có thể khác hoàn toàn overload khác cùng lớp.
3. **Nếu default charset thay đổi, dữ liệu có bị đọc sai hoặc ghi sai không?** Chạy thử với UTF-8 và `COMPAT` để tìm khác biệt.

Không thay thế máy móc mọi lời gọi bằng UTF-8. Nếu dữ liệu nguồn là encoding khác, hãy chỉ định đúng encoding của nguồn. Nếu giao thức quy định UTF-8, hãy truyền `StandardCharsets.UTF_8` tường minh.

### Quy trình kiểm chứng ngắn

1. Ghi nhận `Charset.defaultCharset()`, `file.encoding` và `native.encoding` trên môi trường hiện tại.
2. Tìm các API dùng default charset trong mã nguồn và thư viện tự viết.
3. Kiểm tra file dữ liệu cũ và hợp đồng của các hệ thống gửi/nhận.
4. Chạy test với `-Dfile.encoding=UTF-8` và `-Dfile.encoding=COMPAT` trên JDK 18+.
5. Kiểm tra byte thực tế của file/payload và nội dung sau giải mã bằng charset đúng.
6. Chuyển các ranh giới có hợp đồng rõ ràng sang overload nhận `Charset`.

## 9. Bảng ghi nhớ: phân loại API

| Nhóm | Ví dụ | Charset thực tế khi không truyền charset |
| --- | --- | --- |
| Phụ thuộc default charset | `String.getBytes()`, `new String(bytes)` | `Charset.defaultCharset()` |
| Phụ thuộc default charset | `FileReader`, `FileWriter`, `InputStreamReader`, `OutputStreamWriter` | `Charset.defaultCharset()` |
| Phụ thuộc default charset | `Scanner(InputStream/File/Path)`, `Formatter(OutputStream/File)`, `PrintStream(OutputStream/File)` | `Charset.defaultCharset()` |
| UTF-8 cố định | `Files.readString(path)`, `Files.writeString(path, text)`, `Files.newBufferedReader(path)`, `Files.newBufferedWriter(path)` | UTF-8 theo hợp đồng API |
| Charset cố định khác | `Properties.load(InputStream)` | ISO-8859-1 theo hợp đồng API |
| Nhận ký tự đã giải mã | `BufferedReader(Reader)`, `Formatter(Writer)`, `Scanner(Readable)` | Dùng nội dung từ nguồn Reader/Writer/Readable |
| Luồng console | `System.in`, `System.out`, `System.err` | `stdin.encoding`, `stdout.encoding`, `stderr.encoding` tương ứng |

## 10. Bài tập tự kiểm tra

**Bài 1.** Trên JDK 18+ mặc định, `Charset.defaultCharset()` trả về UTF-8. Nếu chạy `java -Dfile.encoding=COMPAT MyApp` trên máy có native encoding là `windows-1258`, `FileReader(file)` sẽ dùng charset nào?

*Đáp án:* `FileReader(file)` dùng default charset. Trong chế độ `COMPAT`, default charset được xác định theo môi trường cũ, nên trong giả định này là `windows-1258`.

**Bài 2.** `Files.readString(path)` và `new FileReader(path.toFile())` có luôn dùng cùng charset không?

*Đáp án:* Không. `Files.readString(path)` dùng UTF-8 theo hợp đồng API. `FileReader` không chỉ định charset dùng default charset của JVM, có thể khác UTF-8 khi chạy `COMPAT`.

**Bài 3.** `System.out.charset()` và `Charset.defaultCharset()` có nhất thiết trả về cùng một charset không?

*Đáp án:* Không. `System.out` là luồng chuẩn có charset được thiết lập riêng qua `stdout.encoding`. `Charset.defaultCharset()` trả về default charset của JVM.

**Bài 4.** `Properties.load(InputStream)` có đổi sang UTF-8 khi chạy trên JDK 18+ không?

*Đáp án:* Không. Overload nhận `InputStream` có hợp đồng đọc theo ISO-8859-1. Muốn đọc file properties UTF-8, mở một `Reader` UTF-8 rồi truyền cho `Properties.load(Reader)`.

**Bài 5.** Một chương trình dùng `new String(bytes)` để đọc dữ liệu nhận từ một đối tác. Có nên giữ cách này chỉ vì JDK 18+ mặc định là UTF-8 không?

*Đáp án:* Chỉ khi hợp đồng của nguồn dữ liệu quy định UTF-8 và nhóm phát triển chấp nhận phụ thuộc default charset. Cách rõ ràng hơn là `new String(bytes, StandardCharsets.UTF_8)` để thể hiện hợp đồng và tránh ảnh hưởng của `COMPAT`.

## 11. Ghi nhớ

`Charset.defaultCharset()` trả về charset mặc định của JVM; từ Java 18, UTF-8 là giá trị mặc định thông thường theo JEP 400. Các API như `String.getBytes()`, `new String(byte[])`, `FileReader`, `FileWriter`, `InputStreamReader`, `OutputStreamWriter`, `Scanner`, `Formatter` và `PrintStream` có những overload thực sự sử dụng default charset.

Các API `Files` không truyền charset đã quy định UTF-8 cố định; `Properties.load(InputStream)` có quy tắc ISO-8859-1; luồng chuẩn có encoding riêng. Vì thế, cần đọc đúng hợp đồng của **từng overload** thay vì suy luận từ tên lớp hoặc từ việc API đang xử lý văn bản.

Đối với ứng dụng hiện đại, hãy xác định charset ở ranh giới dữ liệu. Dùng UTF-8 tường minh khi định dạng yêu cầu UTF-8, dùng đúng charset của dữ liệu cũ khi nhập, và chỉ dựa vào default charset khi hành vi phụ thuộc môi trường thật sự là chủ đích của ứng dụng.

### Tài liệu tham khảo chính thức

- [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400).
- [Oracle Java SE 27 — Supported Encodings, Default Charset và standard streams](https://docs.oracle.com/en/java/javase/27/intl/supported-encodings.html).
- [Oracle Java SE 27 — Charset.defaultCharset()](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html).
- [Oracle Java SE 27 — String](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html).
- [Oracle Java SE 26 — FileReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/FileReader.html).
- [Oracle Java SE 26 — FileWriter](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/FileWriter.html).
- [Oracle Java SE 26 — InputStreamReader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStreamReader.html).
- [Oracle Java SE 26 — OutputStreamWriter](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/OutputStreamWriter.html).
- [Oracle Java SE 26 — PrintStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/PrintStream.html).
- [Oracle Java SE 26 — Scanner](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Scanner.html).
- [Oracle Java SE 26 — Formatter](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Formatter.html).
- [Oracle Java SE 26 — Files](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html).
- [Oracle Java SE 26 — Properties](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Properties.html).
- [Oracle Java SE 27 — Migration Guide: Be Aware of the Default Charset](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html).
