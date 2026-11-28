# InputStreamReader và OutputStreamWriter: lựa chọn constructor có charset cho luồng byte

## 1. Vì sao cần quan tâm đến charset khi làm việc với stream?

Trong Java, `InputStream` và `OutputStream` trao đổi **byte**, còn `Reader` và `Writer` xử lý **ký tự**. Khi chuyển đổi giữa hai loại luồng này, chương trình phải biết dữ liệu văn bản đang được mã hóa theo quy tắc nào (**charset**).

`InputStreamReader` và `OutputStreamWriter` là hai lớp cầu nối:

```text
TỆP / SOCKET / MESSAGE / BYTE ARRAY
           |
           | byte theo một charset
           v
    InputStream (byte)
           |
           | InputStreamReader: giải mã byte -> ký tự
           v
         Reader
           |
           v
      Xử lý văn bản

      Xử lý văn bản
           |
           v
         Writer
           |
           | OutputStreamWriter: mã hóa ký tự -> byte
           v
    OutputStream (byte)
           |
           v
TỆP / SOCKET / MESSAGE / BYTE ARRAY
```

Vấn đề xuất hiện khi code sử dụng constructor không truyền charset:

```java
Reader reader = new InputStreamReader(inputStream);
Writer writer = new OutputStreamWriter(outputStream);
```

Những lời gọi này có thể phụ thuộc vào charset của môi trường chạy. Kể từ Java 18, UTF-8 là **default charset thông thường** theo JEP 400; tuy nhiên, một luồng dữ liệu có hợp đồng riêng (chẳng hạn ISO-8859-1) vẫn phải được đọc hoặc ghi bằng đúng charset đó. Đặc biệt, constructor không truyền charset của `OutputStreamWriter` có ngoại lệ khi `OutputStream` đầu vào là `PrintStream` (xem phần 3).

**Mục tiêu học tập:** Sau bài này, bạn có thể chọn constructor phù hợp, đọc/ghi luồng UTF-8 và luồng theo charset đã quy định, quản lý buffer và vòng đời stream, phát hiện byte không hợp lệ và xây dựng phép kiểm tra không lệ thuộc máy triển khai. Các kỹ thuật đều áp dụng trên Java 18 và các JDK hiện đại.

## 2. Phân biệt byte stream, character stream và bộ chuyển mã

| Loại | API tiêu biểu | Đơn vị xử lý | Có giải mã/mã hóa charset? |
| --- | --- | --- | --- |
| Byte input | `InputStream`, `FileInputStream`, `ByteArrayInputStream` | `byte` | Không |
| Byte output | `OutputStream`, `FileOutputStream`, `ByteArrayOutputStream` | `byte` | Không |
| Character input | `Reader`, `InputStreamReader`, `BufferedReader` | Ký tự Java (`char`) | Có khi đi qua `InputStreamReader` |
| Character output | `Writer`, `OutputStreamWriter`, `BufferedWriter` | Ký tự Java (`char`) | Có khi đi qua `OutputStreamWriter` |

Ví dụ, ký tự `é` được mã hóa bằng **hai byte** `C3 A9` trong UTF-8, nhưng bằng **một byte** `E9` trong ISO-8859-1. Vì vậy, một byte đọc từ `InputStream` chưa chắc tạo thành một ký tự; `InputStreamReader` phải tích lũy đủ byte để giải mã.

`String` trong Java lưu văn bản theo ngữ nghĩa Unicode; `char` là đơn vị mã UTF-16. Một ký tự Unicode bên ngoài vùng BMP như `🌍` được biểu diễn bằng **hai `char` (surrogate pair)**, còn UTF-8 dùng **bốn byte**. Do đó:

- Không quy đổi số byte sang số ký tự bằng cách đếm vị trí.
- Không giả định mỗi lần `read()` tương ứng với một lần đọc đúng một byte.
- Khi lưu trữ hoặc truyền dữ liệu, charset phải là một phần của hợp đồng giữa bên tạo và bên nhận.

## 3. Chọn đúng constructor

### 3.1. Các constructor thường dùng của `InputStreamReader`

| Constructor | Charset áp dụng | Khi nào nên dùng? |
| --- | --- | --- |
| `new InputStreamReader(in)` | `Charset.defaultCharset()` | Chỉ khi định dạng đầu vào **được xác định** là charset mặc định của JVM |
| `new InputStreamReader(in, StandardCharsets.UTF_8)` | UTF-8 tường minh | Luồng văn bản quy định UTF-8 |
| `new InputStreamReader(in, charset)` | Charset của biến `Charset` | Định dạng cho phép lựa chọn charset theo hợp đồng |
| `new InputStreamReader(in, "UTF-8")` | Charset theo tên | Hỗ trợ code dùng chuỗi cấu hình; constructor này có thể ném `UnsupportedEncodingException` |
| `new InputStreamReader(in, decoder)` | `CharsetDecoder` được cấu hình | Cần báo lỗi khi gặp byte sai định dạng hoặc quy tắc xử lý riêng |

### 3.2. Các constructor thường dùng của `OutputStreamWriter`

| Constructor | Charset áp dụng | Khi nào nên dùng? |
| --- | --- | --- |
| `new OutputStreamWriter(out)` | Thông thường dùng default charset; **nếu `out` là `PrintStream`, dùng charset của `PrintStream` đó** | Chỉ khi đã hiểu rõ hợp đồng của luồng |
| `new OutputStreamWriter(out, StandardCharsets.UTF_8)` | UTF-8 tường minh | Gửi hoặc lưu văn bản UTF-8 |
| `new OutputStreamWriter(out, charset)` | Charset của biến `Charset` | Dữ liệu dùng charset được quy định riêng |
| `new OutputStreamWriter(out, "UTF-8")` | Charset theo tên | Code nhận cấu hình từ chuỗi; có thể ném `UnsupportedEncodingException` |
| `new OutputStreamWriter(out, encoder)` | `CharsetEncoder` được cấu hình | Cần chủ động chọn cách xử lý ký tự không thể biểu diễn |

**Ưu tiên `Charset` thay cho chuỗi tên charset** trong code khi đã biết chuẩn: `StandardCharsets.UTF_8`, `StandardCharsets.ISO_8859_1`, `StandardCharsets.US_ASCII`, v.v. Các hằng số này giúp truyền ý định một cách rõ ràng và tránh lỗi đánh vần tên charset.

Lưu ý: constructor `OutputStreamWriter(OutputStream)` có ngoại lệ với `PrintStream` theo Javadoc hiện hành. Ví dụ, `new OutputStreamWriter(System.out)` có thể chọn encoding của `System.out` thay vì `Charset.defaultCharset()`. Nếu hợp đồng yêu cầu UTF-8, hãy truyền `StandardCharsets.UTF_8` trực tiếp.

## 4. Liên hệ với Java 18: JEP 400 và những gì vẫn cần chỉ rõ

Java 18 đưa ra **JEP 400: UTF-8 by Default**, làm cho `Charset.defaultCharset()` thông thường là UTF-8 trên các nền tảng. Quy tắc này vẫn hữu ích và hiện hành trên các JDK mới.

```java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset());
```

Trong cấu hình thông thường của JDK 18+, kết quả là `UTF-8`. Tuy nhiên, cần nhớ:

1. JVM có thể được chạy với một cấu hình hỗ trợ tương thích, ví dụ `-Dfile.encoding=COMPAT`, làm thay đổi charset mặc định theo môi trường; chi tiết phụ thuộc JDK và cách khởi động.
2. Default charset **không phải charset của mọi nguồn dữ liệu**. File cũ, payload mạng và hệ thống ngoài có thể có đặc tả mã hóa khác.
3. Việc đọc bàn phím qua `System.in` và hiển thị bằng `System.out`/`System.err` có quy tắc riêng liên quan đến `stdin.encoding`, `stdout.encoding` và `stderr.encoding`. Không thể mặc nhiên đồng nhất chúng với `Charset.defaultCharset()`.

Vì vậy, muốn đổi kết quả byte và ký tự một cách xác định, chọn constructor **có `Charset`**, gắn với định dạng của luồng. Đây là cách viết code bền vững ngay cả khi môi trường hiện tại đã dùng UTF-8.

## 5. Ví dụ đầy đủ: ghi UTF-8 rồi đọc lại từ luồng byte

Dùng `ByteArrayOutputStream` và `ByteArrayInputStream` để quan sát byte mà không cần tạo file thật:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class Utf8StreamRoundTrip {
    public static void main(String[] args) throws Exception {
        String original = "Xin chào 🌍";

        ByteArrayOutputStream destination = new ByteArrayOutputStream();

        // Chỉ rõ hợp đồng UTF-8 ngay tại lúc tạo Writer.
        try (BufferedWriter writer = new BufferedWriter(
                new OutputStreamWriter(destination, StandardCharsets.UTF_8))) {
            writer.write(original);
        } // close() hoàn tất việc ghi, flush phần byte còn đệm.

        byte[] payload = destination.toByteArray();
        System.out.println("UTF-8 hex: " + HexFormat.of().formatHex(payload));

        // Dùng cùng charset mà bên gửi đã công bố.
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        new ByteArrayInputStream(payload),
                        StandardCharsets.UTF_8))) {
            String restored = reader.readLine();
            System.out.println("Khôi phục: " + restored);
            System.out.println("Khớp: " + original.equals(restored));
        }
    }
}
```

Chạy:

```text
javac Utf8StreamRoundTrip.java
java Utf8StreamRoundTrip
```

Đầu ra có dòng `Khớp: true`. Byte được mã hóa đúng UTF-8, độc lập với default charset của JVM. `HexFormat` dùng được từ Java 17 nên phù hợp với môi trường Java 18+.

Ở ví dụ này, `BufferedReader.readLine()` đọc một dòng không chứa dấu kết thúc dòng. Nếu yêu cầu giữ **nguyên văn** các ký tự xuống dòng, cần đọc ký tự theo khối và ghép lại; `readLine()` sẽ bỏ dấu kết thúc dòng `\n`, `\r` hoặc `\r\n`.

### Khi luồng thực tế đến từ file

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path source = Path.of("input.txt");
Path target = Path.of("output.txt");

try (BufferedReader reader = Files.newBufferedReader(source, StandardCharsets.UTF_8);
     BufferedWriter writer = Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        writer.write(line);
        writer.newLine();
    }
}
```

`Files.newBufferedReader`/`Files.newBufferedWriter` là API tiện ích phù hợp nếu thao tác trực tiếp với file văn bản. Trong ví dụ trên, dấu xuống dòng của file đích được tạo bằng `newLine()` theo môi trường, có thể khác file gốc. Nếu cần giữ byte hoặc ký tự xuống dòng chính xác, hãy dùng cách copy phù hợp với yêu cầu; nếu cần copy file nhị phân thì không dùng reader/writer để chuyển mã.

## 6. Tình huống thực tế: đọc đúng dữ liệu theo charset của đối tác

Giả sử nguồn dữ liệu quy định ISO-8859-1 và gửi bốn byte `63 61 66 E9` (`café`). Byte `E9` đứng riêng **không** là UTF-8 hợp lệ:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

byte[] legacyPayload = {
    (byte) 0x63, (byte) 0x61, (byte) 0x66, (byte) 0xE9
};

try (InputStreamReader reader = new InputStreamReader(
        new ByteArrayInputStream(legacyPayload),
        StandardCharsets.ISO_8859_1)) {
    char[] chars = new char[16];
    int count = reader.read(chars);
    String value = new String(chars, 0, count);
    System.out.println(value); // café
}
```

Nếu thay `StandardCharsets.ISO_8859_1` bằng `StandardCharsets.UTF_8`, bộ giải mã sẽ xử lý byte `E9` như dữ liệu sai quy tắc UTF-8, dẫn tới lỗi hoặc ký tự thay thế tùy chính sách. Điều đó không có nghĩa dữ liệu của đối tác sai; **charset dùng để đọc không khớp định dạng đã được thỏa thuận**.

Khi phân tích lỗi hiển thị `�`, `Ã`, ký tự tiếng Việt biến dạng hoặc kết quả khác nhau giữa máy triển khai, hãy kiểm tra charset **ở nơi tạo byte** và **nơi giải mã byte**. Không có API nào tự bảo đảm xác định đúng charset chỉ từ các byte tùy ý.

## 7. Buffer, flush và close: chọn cách dùng an toàn

`InputStreamReader` chuyển đổi byte thành ký tự và có thể đọc trước nhiều byte từ `InputStream` để phục vụ một lần `read()`. Vì vậy, không nên luân phiên đọc trực tiếp từ `InputStream` và đọc qua `InputStreamReader` đang bọc cùng một nguồn: vị trí luồng byte thực tế có thể đã vượt quá vị trí ký tự mà chương trình nhìn thấy.

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

BufferedReader textReader = new BufferedReader(
        new InputStreamReader(input, StandardCharsets.UTF_8));
```

Với luồng đầu ra, `OutputStreamWriter` mã hóa ký tự thành byte, đồng thời **đệm byte** trước khi chuyển xuống `OutputStream`. Bọc thêm `BufferedWriter` thường giúp giảm số lần chuyển mã khi thực hiện nhiều lệnh ghi nhỏ:

```java
import java.io.BufferedWriter;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

BufferedWriter textWriter = new BufferedWriter(
        new OutputStreamWriter(output, StandardCharsets.UTF_8));

textWriter.write("xin chào");
textWriter.newLine();
textWriter.flush(); // Đẩy ký tự/byte đang đệm xuống luồng bên dưới.
```

Các hành vi quan trọng:

- `flush()` đẩy dữ liệu đã đệm qua tầng writer và xuống output stream. Nó **không** tự bổ sung ký tự xuống dòng và không có nghĩa dữ liệu đã được đồng bộ vật lý xuống ổ đĩa hoặc đối tác đã nhận đủ.
- `close()` của `OutputStreamWriter` flush trước khi đóng. Với try-with-resources, việc đóng tài nguyên được quản lý tự động khi rời khối.
- Đóng reader/writer thường **đóng cả stream bên dưới**. Đối với tệp do phương thức hiện tại tự mở, try-with-resources là lựa chọn hợp lý. Với luồng dùng chung do tầng khác quản lý, xác định rõ ai có quyền đóng trước khi tạo wrapper.
- Với đầu vào lớn, dùng vòng lặp đọc từng khối hoặc từng dòng; không cần tải toàn bộ nội dung vào một `String` nếu nghiệp vụ cho phép xử lý streaming.

**Cảnh báo về giao thức:** Nếu một kết nối trộn trường nhị phân và văn bản, cần thiết kế ranh giới byte rõ ràng (độ dài, frame hoặc delimiter) và có chiến lược buffer nhất quán. `InputStreamReader` có thể đọc trước qua ranh giới; không được giả định “đọc một dòng xong là toàn bộ byte tiếp theo vẫn nằm nguyên trong InputStream gốc”.

## 8. Khi muốn phát hiện byte lỗi: sử dụng CharsetDecoder

Với việc hiển thị text thông thường, chính sách thay thế ký tự lỗi đôi khi chấp nhận được. Nhưng khi đọc file nghiệp vụ, kiểm tra checksum văn bản hoặc nhập dữ liệu quan trọng, **âm thầm biến byte lỗi thành `�` có thể che giấu mất dữ liệu**.

`InputStreamReader` có constructor nhận `CharsetDecoder`. Ta cấu hình decoder để báo lỗi thay vì thay thế:

```java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] input) throws IOException {
    CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);

    try (BufferedReader reader = new BufferedReader(
            new InputStreamReader(new ByteArrayInputStream(input), decoder))) {
        StringBuilder text = new StringBuilder();
        char[] buffer = new char[1024];
        int count;
        while ((count = reader.read(buffer)) != -1) {
            text.append(buffer, 0, count);
        }
        return text.toString();
    }
}
```

Ví dụ gọi `decodeUtf8Strict(new byte[] {(byte) 0xE9})` sẽ phát sinh `MalformedInputException` (thuộc họ `IOException`) vì chuỗi byte UTF-8 không hợp lệ. Ở tầng nghiệp vụ, có thể từ chối payload và yêu cầu bên gửi sửa dữ liệu.

Với chiều ghi, `OutputStreamWriter` theo cách dùng thông thường có thể thay ký tự không thể biểu diễn được trong charset đích. Khi cần kiểm soát nghiêm ngặt, dùng `CharsetEncoder` với `CodingErrorAction.REPORT` và constructor `OutputStreamWriter(out, encoder)` hoặc trực tiếp mã hóa bằng `CharsetEncoder`; cần bảo đảm ghi/đóng stream xử lý ngoại lệ đúng. Ví dụ viết `🌍` vào ISO-8859-1 không có cách biểu diễn tương ứng nên không được tự coi là thành công nếu giao thức yêu cầu giữ nguyên dữ liệu.

## 9. Trường hợp stdin, stdout và lỗi thiết kế luồng

Một số tình huống cần phân biệt:

| Tình huống | Cách làm |
| --- | --- |
| Đọc dữ liệu UTF-8 từ mạng, file hoặc message | `new InputStreamReader(in, StandardCharsets.UTF_8)` |
| Ghi UTF-8 ra luồng byte | `new OutputStreamWriter(out, StandardCharsets.UTF_8)` |
| Đọc dữ liệu của hệ thống cũ có hợp đồng ISO-8859-1 | `new InputStreamReader(in, StandardCharsets.ISO_8859_1)` |
| Đọc bàn phím tương tác qua `System.in` | Cân nhắc `stdin.encoding` theo hướng dẫn của JDK/console, vì encoding terminal có thể khác default charset |
| Ghi đầu ra terminal qua `System.out` | Tôn trọng encoding của console hoặc cấu hình giao diện người dùng; không áp quy tắc file UTF-8 một cách mù quáng |
| Cần nhập dữ liệu với kiểm tra byte chặt chẽ | `InputStreamReader(in, CharsetDecoder)` và `CodingErrorAction.REPORT` |
| Cần ghi từng dòng số lượng lớn | Dùng `BufferedWriter` bọc `OutputStreamWriter` hoặc API tiện ích của `Files` |

Ví dụ Javadoc hiện hành khuyến nghị sử dụng thuộc tính `stdin.encoding` khi tạo reader trực tiếp từ `System.in`:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;

BufferedReader consoleInput = new BufferedReader(
        new InputStreamReader(
                System.in,
                System.getProperty("stdin.encoding")));
```

Cách này dành cho **stdin** và giả định thuộc tính được môi trường/JDK cung cấp hợp lệ. Với một stream từ file hoặc kết nối mạng, charset phải được lấy từ hợp đồng của dữ liệu đó. Trong ứng dụng tương tác, `System.console()` và API console cũng đáng cân nhắc khi có console thực sự; tránh tự đóng `System.in` nếu các phần khác của ứng dụng còn cần đọc nó.

## 10. Kiểm thử để phát hiện lỗi khi nâng cấp JDK

Sử dụng `ByteArrayOutputStream` để so sánh **byte thực tế**, không dựa vào mắt nhìn trên terminal:

```java
import java.io.ByteArrayOutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

static void verifyEncoding() throws Exception {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    try (OutputStreamWriter writer =
            new OutputStreamWriter(out, StandardCharsets.UTF_8)) {
        writer.write("café");
    }

    byte[] expected = {
        (byte) 0x63, (byte) 0x61, (byte) 0x66,
        (byte) 0xC3, (byte) 0xA9
    };
    if (!Arrays.equals(expected, out.toByteArray())) {
        throw new AssertionError("UTF-8 encoding mismatch");
    }
}
```

Nên kiểm tra ít nhất:

1. Nội dung ASCII và Unicode có dấu: `café`, `Tiếng Việt`.
2. Ký tự ngoài BMP, ví dụ `🌍`, để kiểm tra không chia vỡ surrogate pair khi xử lý ký tự.
3. Payload đến từ encoding khác UTF-8 mà hợp đồng cho phép, ví dụ ISO-8859-1.
4. Byte UTF-8 lỗi hoặc chưa đủ byte, xác minh hành vi báo lỗi nếu dùng decoder strict.
5. Chuỗi đầu ra dài hơn buffer và luồng được `flush()`/`close()` đúng cách.
6. Giao thức có nhiều message liên tiếp, đặc biệt nếu trộn text và binary trên cùng một kết nối.

Kiểm thử theo byte giúp phát hiện hồi quy ngay cả khi `Charset.defaultCharset()` có giá trị khác giữa môi trường chạy test và production.

## 11. Những hiểu nhầm cần tránh

- **“Java 18 mặc định UTF-8 nên có thể bỏ `StandardCharsets.UTF_8`.”** Không bảo đảm hợp đồng dữ liệu ở mọi môi trường hoặc với mọi nguồn byte. Truyền charset rõ ràng khi trao đổi định dạng xác định.
- **“`OutputStreamWriter(out)` lúc nào cũng lấy `Charset.defaultCharset()`.”** Có ngoại lệ khi `out` là `PrintStream`; hãy xem constructor Javadoc.
- **“Reader đọc một ký tự tức là InputStream đọc một byte.”** Sai với UTF-8 và nhiều charset; reader còn có thể đọc trước.
- **“`BufferedReader.readLine()` giữ nguyên mọi dấu kết thúc dòng.”** Sai. Phương thức trả về nội dung dòng mà không chứa dấu kết thúc dòng.
- **“`flush()` bảo đảm dữ liệu đã được lưu bền vững.”** Không. Flush ở tầng Java I/O không đồng nghĩa với `fsync` hay xác nhận nhận dữ liệu từ mạng.
- **“Có thể dùng reader/writer để copy mọi byte.”** Không. Reader/writer là công cụ chuyển đổi văn bản; dùng byte stream cho ảnh, ZIP, nội dung mã hóa hoặc dữ liệu nhị phân.
- **“Nếu UTF-8 decode lỗi thì Java sẽ đoán đúng charset khác.”** Không. Cần xác định charset từ hợp đồng hoặc metadata đáng tin cậy.

## 12. Tài liệu chính thức để tham khảo

- [JEP 400 — UTF-8 by Default (OpenJDK)](https://openjdk.org/jeps/400): thay đổi default charset từ Java 18.
- [InputStreamReader — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/InputStreamReader.html): các constructor, `CharsetDecoder`, cơ chế đọc trước.
- [OutputStreamWriter — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/OutputStreamWriter.html): các constructor, ngoại lệ `PrintStream`, cơ chế buffer và thay thế ký tự lỗi.
- [CharsetDecoder — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html) và [CharsetEncoder — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetEncoder.html): kiểm soát lỗi chuyển mã.
- [Supported Encodings — Java SE 25](https://docs.oracle.com/en/java/javase/25/intl/supported-encodings.html): charset mặc định, `stdin.encoding`, `stdout.encoding` và `stderr.encoding`.
