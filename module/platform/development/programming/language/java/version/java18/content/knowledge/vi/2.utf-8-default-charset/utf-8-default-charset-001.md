# JEP 400 và ý nghĩa của UTF-8 mặc định đối với tính di động của ứng dụng Java

## 1. Vì sao encoding mặc định từng là nguồn lỗi?

Một `String` trong Java chứa các ký tự Unicode. Khi lưu xuống tệp, gửi qua mạng hoặc đọc dữ liệu từ byte, chương trình phải **mã hóa** (`String` → byte) hoặc **giải mã** (byte → `String`) bằng một *charset*. UTF-8 là charset phổ biến, biểu diễn ký tự bằng 1–4 byte và tương thích với ASCII trong phạm vi ký tự ASCII.

Trước JDK 18, `Charset.defaultCharset()` thường phụ thuộc hệ điều hành, locale hoặc cấu hình môi trường khi tiến trình Java khởi động. Ví dụ, một máy có thể dùng UTF-8, trong khi môi trường Windows khác dùng `windows-1252` hoặc `windows-31j`. Vì thế, đoạn mã không nêu charset có thể ghi và đọc các byte theo hai quy tắc khác nhau:

```java
// Có phụ thuộc vào charset mặc định của JVM.
byte[] bytes = "cà phê".getBytes();
String value = new String(bytes);
```

Trong UTF-8, chuỗi `"cà"` có các byte `63 C3 A0` (ở dạng hex). Nếu một chương trình giải mã cùng dãy byte đó bằng `windows-1252`, kết quả có thể thành `"cÃ "`. Đây là lỗi *mojibake*: dữ liệu byte vẫn tồn tại, nhưng ký tự hiển thị sai vì chọn nhầm charset.

Các tình huống thường gặp gồm file CSV trao đổi giữa máy phát triển và máy chủ, log được đọc bởi công cụ bên ngoài, dữ liệu nhập từ ứng dụng cũ hoặc tệp văn bản được tạo bằng công cụ không dùng UTF-8.

## 2. JEP 400 thay đổi điều gì từ Java 18?

**JEP 400 (UTF-8 by Default)** được đưa vào JDK 18 và tiếp tục áp dụng trên các JDK hiện đại. Trong cấu hình mặc định thông thường, `Charset.defaultCharset()` trả về `UTF-8` bất kể hệ điều hành và locale. Các API Java SE vốn dùng *default charset* vì người lập trình không chỉ định charset sẽ sử dụng UTF-8 theo mặc định.

Sự thay đổi này làm hành vi của những thao tác chuyển đổi văn bản sang byte nhất quán hơn giữa môi trường phát triển, CI và triển khai:

- **Trước JDK 18:** cách diễn giải byte của API phụ thuộc default charset có thể khác nhau giữa các máy.
- **Từ JDK 18:** default charset thông thường là UTF-8. Vẫn có cấu hình khởi động `-Dfile.encoding=COMPAT` để phục vụ việc kiểm tra tương thích với môi trường cũ.
- **Về thiết kế ứng dụng:** nếu format dữ liệu hoặc giao thức đã xác định charset, vẫn nên khai báo charset **tường minh** để hợp đồng dữ liệu rõ ràng và không bị ảnh hưởng bởi tùy chọn khởi động.

JEP 400 **không tự chuyển mã** các tệp đã tồn tại trên đĩa; cũng không bảo đảm mọi công cụ ngoài JVM, thiết bị đầu cuối hay hệ thống khác đều dùng UTF-8. Khả năng di động được cải thiện vì quy tắc mặc định thống nhất, chứ không phải vì Java tự đoán chính xác encoding của mọi dữ liệu.

### API nào chịu ảnh hưởng?

| API hoặc thao tác | Khi không truyền charset | Ý nghĩa thực tế |
| --- | --- | --- |
| `String#getBytes()` và `new String(byte[])` | Dùng `Charset.defaultCharset()` | Mã hóa/giải mã byte với UTF-8 trong cấu hình JDK 18+ mặc định. |
| `new FileReader(file)`, `new FileWriter(file)` | Dùng default charset | Đọc/ghi văn bản UTF-8 trong cấu hình mặc định. |
| `new InputStreamReader(stream)`, `new OutputStreamWriter(stream)` | Dùng default charset | Cầu nối byte–ký tự mặc định chuyển sang UTF-8. |
| Một số constructor của `Scanner`, `Formatter`, `PrintStream` không truyền charset | Theo hợp đồng riêng của constructor, có thể dùng default charset | Cần kiểm tra overload đang gọi; riêng các luồng chuẩn có quy tắc khác được giải thích bên dưới. |
| `Files.readString(path)`, `Files.writeString(path, text)` và `Files.newBufferedReader(path)` | **Đã mặc định UTF-8 trước JDK 18** | Không phải hành vi mới do JEP 400; có thể truyền charset rõ ràng để thể hiện yêu cầu của định dạng dữ liệu. |
| `javac` khi đọc mã nguồn `.java`, nếu không có `-encoding` | Dùng default charset của môi trường biên dịch | Nguồn không phải UTF-8 có thể phát sinh lỗi hoặc sai ký tự khi đổi JDK; nên xác định encoding nguồn rõ ràng. |

**Phân biệt hai khái niệm:** *default charset của JVM* (`Charset.defaultCharset()`) không đồng nghĩa với charset mà mọi API Java đều sử dụng. Nhiều API có charset cố định từ trước hoặc nhận charset riêng qua đối số.

## 3. Thử nghiệm thực tế trên JDK 18 trở lên

Ví dụ sau ghi một tệp theo UTF-8, đọc lại bằng `FileReader` không chỉ định charset để minh họa quy tắc mặc định, sau đó so với cách đọc có charset tường minh. Ví dụ tương thích Java 18 và các JDK hiện đại.

```java
import java.io.FileReader;
import java.io.StringWriter;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class Utf8DefaultDemo {
    public static void main(String[] args) throws Exception {
        String original = "Tiếng Việt: cà phê";
        Path file = Path.of("demo-utf8.txt");

        // Mã hóa tường minh để dữ liệu trên đĩa luôn là UTF-8.
        Files.write(file, original.getBytes(StandardCharsets.UTF_8));

        System.out.println("Default charset: " + Charset.defaultCharset());

        // Minh họa API chịu ảnh hưởng bởi JEP 400.
        try (FileReader reader = new FileReader(file.toFile())) {
            StringWriter buffer = new StringWriter();
            reader.transferTo(buffer);
            System.out.println("Default decode matches: "
                    + original.equals(buffer.toString()));
        }

        // Cách nên dùng khi tệp được quy định rõ là UTF-8.
        String explicit = Files.readString(file, StandardCharsets.UTF_8);
        System.out.println("Explicit UTF-8 matches: "
                + original.equals(explicit));
    }
}
```

Lưu nguồn với encoding UTF-8, sau đó chạy:

```bash
javac -encoding UTF-8 Utf8DefaultDemo.java
java Utf8DefaultDemo
```

Trong cấu hình mặc định trên JDK 18+, ba dòng kết quả dự kiến là:

```text
Default charset: UTF-8
Default decode matches: true
Explicit UTF-8 matches: true
```

Điểm đáng chú ý: thao tác `Files.readString(file, StandardCharsets.UTF_8)` luôn giải mã bằng UTF-8 theo yêu cầu của chương trình, kể cả khi JVM được cấu hình dùng một default charset khác. Phép so sánh `true` kiểm tra nội dung ký tự sau khi đọc; việc hiển thị ký tự có dấu lên terminal còn tùy encoding của terminal.

### Kiểm tra định dạng byte

```java
byte[] utf8 = "cà".getBytes(StandardCharsets.UTF_8);
for (byte b : utf8) {
    System.out.printf("%02X ", Byte.toUnsignedInt(b));
}
// Dãy byte: 63 C3 A0
```

Vì UTF-8 dùng nhiều byte cho một số ký tự, **số ký tự không nhất thiết bằng số byte**. Chẳng hạn `"cà"` có hai ký tự nhưng ba byte UTF-8. Đây là khác biệt cần chú ý khi giới hạn dung lượng payload, tính độ dài bản ghi hoặc kết nối với hệ thống dùng encoding khác.

## 4. Những giới hạn phải hiểu đúng

### 4.1. Console và các luồng chuẩn có encoding riêng

`System.in`, `System.out` và `System.err` liên quan đến môi trường terminal và có thể dùng các charset được xác định riêng qua `stdin.encoding`, `stdout.encoding`, `stderr.encoding`. Những giá trị này **có thể khác** `Charset.defaultCharset()` và `file.encoding`.

Vì vậy, ngay cả khi `Charset.defaultCharset()` là UTF-8, không nên kết luận mọi dòng `System.out.println("Tiếng Việt")` sẽ hiển thị chính xác trên mọi terminal. Tùy nền tảng, cần kiểm tra terminal, công cụ bắt log và charset của luồng chuẩn. Khi xử lý dữ liệu nhập tương tác, tránh mặc định rằng `new InputStreamReader(System.in)` luôn dùng đúng encoding thực tế của terminal; có thể sử dụng `System.console()` khi phù hợp hoặc chọn charset tương thích với nguồn nhập đã biết.

### 4.2. Dữ liệu cũ không tự biến thành UTF-8

Ví dụ một tệp cũ được ghi theo ISO-8859-1, đọc nó bằng UTF-8 sẽ không khôi phục đúng dữ liệu. Khi đã **biết chắc** charset của dữ liệu nguồn, phải giải mã bằng charset đó, rồi mới mã hóa sang UTF-8 nếu cần chuyển đổi:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path legacyFile = Path.of("old-latin1.txt");
Path utf8File = Path.of("converted-utf8.txt");

// Chỉ dùng ISO-8859-1 khi đó thật sự là encoding của tệp nguồn.
String content = Files.readString(legacyFile, StandardCharsets.ISO_8859_1);
Files.writeString(utf8File, content, StandardCharsets.UTF_8);
```

Một chuỗi đã bị giải mã sai rồi ghi lại vẫn có thể chứa ký tự sai. Cần xác định encoding gốc từ đặc tả, metadata hoặc hệ thống tạo ra file; **không thể dựa vào JEP 400 để tự nhận diện mọi encoding**.

### 4.3. Charset không giải quyết tất cả khác biệt nền tảng

UTF-8 mặc định không thống nhất ký tự xuống dòng (`\n` hay `\r\n`), cách chuẩn hóa Unicode, encoding bắt buộc trong giao thức bên ngoài hoặc quy tắc hiển thị của font/terminal. Muốn dữ liệu có thể trao đổi ổn định, ứng dụng phải xác định thêm các quy tắc đó theo yêu cầu định dạng.

## 5. Cấu hình `file.encoding` và kiểm tra khi nâng cấp JDK

Trên JDK 18 trở lên, giá trị `file.encoding` được hỗ trợ khi **khởi động JVM** là:

| Tùy chọn | Hiệu quả | Khi nào dùng |
| --- | --- | --- |
| `-Dfile.encoding=UTF-8` | Chọn UTF-8 làm default charset. | Làm rõ cấu hình chạy hoặc kiểm chứng hành vi mã hóa. |
| `-Dfile.encoding=COMPAT` | Chọn encoding theo cách phụ thuộc môi trường giống JDK 17 trở về trước, thông qua `native.encoding`. | Điều tra ứng dụng trước khi chuyển đổi, xác định phần đang phụ thuộc encoding cũ. |
| Giá trị khác, ví dụ `-Dfile.encoding=windows-1252` | **Không được đặc tả là giá trị hỗ trợ**. | Không dùng làm cách cấu hình portable. |

Có thể chạy ví dụ theo hai cấu hình để phát hiện phụ thuộc encoding:

```bash
java -Dfile.encoding=UTF-8 Utf8DefaultDemo
java -Dfile.encoding=COMPAT Utf8DefaultDemo
```

Nếu `native.encoding` của máy không phải UTF-8, kết quả `Default decode matches` có thể khác nhau giữa hai lần chạy. Nếu cả hai đều giống nhau, điều đó **không đủ** để khẳng định ứng dụng không có rủi ro encoding; có thể môi trường đang dùng UTF-8 hoặc dữ liệu thử chỉ chứa ASCII.

Kiểm tra trực tiếp trên máy chạy chương trình:

```java
import java.nio.charset.Charset;

System.out.println("defaultCharset = " + Charset.defaultCharset());
System.out.println("file.encoding = "
        + System.getProperty("file.encoding"));
System.out.println("native.encoding = "
        + System.getProperty("native.encoding"));
System.out.println("stdout.encoding = "
        + System.getProperty("stdout.encoding"));
```

`native.encoding` cho biết encoding do môi trường gốc cung cấp và có thể khác UTF-8. Nó không phải cờ để ứng dụng tùy ý ghi đè. Không dựa vào việc gọi `System.setProperty("file.encoding", "...")` giữa lúc JVM đang chạy để thay đổi cách giải mã của API; cấu hình được xác lập khi JVM khởi động.

`COMPAT` hữu ích cho việc **chẩn đoán quá trình chuyển đổi**, nhưng không nên trở thành hợp đồng lâu dài để các ứng dụng trao đổi tệp với nhau. Định dạng dữ liệu nên xác định rõ charset ngay tại điểm đọc/ghi.

## 6. Cách viết ứng dụng di động và dễ bảo trì

Trong code ứng dụng, ràng buộc charset vào **hợp đồng dữ liệu**, không để phụ thuộc vào cài đặt máy:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path report = Path.of("report.txt");
String text = "Báo cáo: hoàn thành";

// Tệp được xác định là UTF-8, nhất quán trên mọi máy.
Files.writeString(report, text, StandardCharsets.UTF_8);
String loaded = Files.readString(report, StandardCharsets.UTF_8);

if (!text.equals(loaded)) {
    throw new IllegalStateException("Nội dung không khớp");
}

// Chuyển đổi byte cho các giao thức yêu cầu UTF-8.
byte[] payload = loaded.getBytes(StandardCharsets.UTF_8);
String reconstructed = new String(payload, StandardCharsets.UTF_8);
```

Những lựa chọn thực hành quan trọng:

1. **Khẳng định charset tại ranh giới I/O.** Với file, HTTP payload, message queue, CSV hoặc giao thức nội bộ, khai báo UTF-8 rõ ràng nếu đó là quy ước. Nếu chuẩn yêu cầu encoding khác, dùng đúng encoding của chuẩn.
2. **Ghi thống nhất encoding của mã nguồn.** Lưu `.java` bằng UTF-8; có thể dùng `javac -encoding UTF-8` hoặc cấu hình encoding tương đương trong build tool.
3. **Rà soát nơi không truyền charset.** Tìm `new String(bytes)`, `getBytes()`, `FileReader`, `FileWriter`, `InputStreamReader` và các constructor tương tự. Quyết định theo định dạng dữ liệu, thay vì thay thế máy móc mọi lời gọi.
4. **Kiểm thử dữ liệu thật có dấu và ký tự ngoài ASCII.** Dùng tiếng Việt, tên người, ký hiệu tiền tệ, emoji nếu ứng dụng có thể gặp. Kiểm tra cả nội dung byte sau khi ghi và ký tự sau khi đọc.
5. **Chuyển đổi hệ thống cũ có chủ đích.** Biết charset nguồn trước khi đọc, chuyển đổi dữ liệu có kiểm thử và thống nhất charset cho các hệ thống phụ thuộc.

### Bài tập tự kiểm tra

Một dịch vụ Java ghi CSV với `new FileWriter("orders.csv")` trên JDK 17 chạy ở máy có default charset `windows-1252`. Sau khi nâng lên JDK 18+, dịch vụ dùng cùng mã nguồn để ghi CSV, còn một chương trình bên ngoài vẫn giải mã CSV theo `windows-1252`.

- **Điều gì có thể thay đổi?** `FileWriter` chuyển sang UTF-8 theo mặc định của JDK 18+, nhưng chương trình đọc ngoài JVM vẫn dùng encoding cũ; ký tự ngoài ASCII có thể hiển thị sai.
- **Khắc phục ở đâu?** Thống nhất encoding với bên nhận: ưu tiên hợp đồng file UTF-8, thay đổi chương trình đọc theo UTF-8, hoặc chỉ định charset khác tại điểm ghi nếu giao thức hiện hành bắt buộc.
- **Có nên bật `COMPAT` vĩnh viễn?** Không nên lấy encoding phụ thuộc máy làm hợp đồng dữ liệu. `COMPAT` phù hợp để tái hiện hành vi cũ trong lúc chẩn đoán và chuyển đổi.

## 7. Ghi nhớ

JEP 400 đưa UTF-8 thành **default charset nhất quán** cho các Java SE API phụ thuộc default charset từ JDK 18. Đây là nền tảng quan trọng giúp ứng dụng di động hơn giữa các hệ điều hành, đặc biệt khi làm việc với văn bản đa ngôn ngữ. Tuy nhiên, dữ liệu cũ, giao thức riêng và terminal vẫn có thể sử dụng encoding khác; ứng dụng bền vững luôn xác định charset theo định dạng dữ liệu của mình.

### Tài liệu tham khảo chính thức

- [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400).
- [Oracle Java SE 27 — Migration Guide, Be Aware of the Default Charset](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html).
- [Oracle Java SE 25 — Supported Encodings: Default Charset, standard streams, file.encoding](https://docs.oracle.com/en/java/javase/25/intl/supported-encodings.html).
- [Oracle Java SE 25 — Charset.defaultCharset() API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/Charset.html).
