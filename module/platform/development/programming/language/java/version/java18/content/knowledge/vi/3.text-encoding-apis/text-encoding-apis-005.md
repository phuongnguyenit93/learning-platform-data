# BufferedReader và BufferedWriter: lớp đệm không quyết định lại charset của luồng bên dưới

## 1. Vai trò của lớp đệm trong xử lý văn bản

Trong Java, `Reader` và `Writer` làm việc với ký tự; `InputStream` và `OutputStream` làm việc với byte. Khi chương trình trao đổi văn bản với file, socket hoặc nguồn byte khác, cần hai quyết định độc lập:

- **Charset:** quy tắc chuyển đổi byte thành ký tự hoặc ngược lại.
- **Buffering:** cách giữ tạm dữ liệu trong bộ nhớ để giảm số lần gọi xuống tầng I/O bên dưới.

`BufferedReader` và `BufferedWriter` giải quyết quyết định thứ hai. Chúng bọc một `Reader` hoặc `Writer` có sẵn, đệm ký tự và cung cấp các thao tác tiện lợi. **Bản thân hai lớp này không chọn, phát hiện hay thay đổi charset.**

Đây là điểm cần nhớ khi học các thay đổi Java 18 còn áp dụng trên JDK hiện đại. JEP 400 đặt UTF-8 làm default charset thông thường từ Java 18, nhưng thêm `BufferedReader` vào một reader không làm cho dữ liệu tự chuyển thành UTF-8. Charset vẫn do tầng chuyển mã bên dưới quyết định.

Sau bài này, bạn có thể phân biệt đúng hai tầng, xây dựng chuỗi đọc/ghi UTF-8 rõ ràng, dùng `readLine()` và `newLine()` đúng hợp đồng, quản lý buffer và tài nguyên, và kiểm thử byte thực tế.

## 2. Hai tầng riêng biệt: chuyển mã và đệm ký tự

Luồng đọc văn bản từ nguồn byte thường có cấu trúc:

```text
File / Socket / byte source
          |
          | byte
          v
    InputStream
          |
          v
 InputStreamReader
 (giải mã bằng Charset)
          |
          | char
          v
   BufferedReader
 (đệm ký tự, readLine)
          |
          v
   Logic ứng dụng
```

Chiều ghi đi theo hướng ngược lại:

```text
   Logic ứng dụng
          |
          | char
          v
   BufferedWriter
 (đệm ký tự, newLine)
          |
          v
  OutputStreamWriter
 (mã hóa bằng Charset)
          |
          | byte
          v
   OutputStream
          |
          v
 File / Socket / byte destination
```

| Tầng | Lớp tiêu biểu | Trách nhiệm |
| --- | --- | --- |
| Byte I/O | `InputStream`, `OutputStream` | Đọc và ghi byte |
| Chuyển mã | `InputStreamReader`, `OutputStreamWriter` | Decode/encode theo charset |
| Đệm ký tự | `BufferedReader`, `BufferedWriter` | Giữ tạm ký tự, giảm thao tác I/O, hỗ trợ tiện ích theo dòng |
| Ứng dụng | `String`, xử lý nghiệp vụ | Diễn giải và tạo nội dung văn bản |

Ví dụ, khi đọc UTF-8, `InputStreamReader` mới là thành phần giải mã chuỗi byte UTF-8 thành ký tự. `BufferedReader` nhận các ký tự đó, đệm lại rồi cung cấp cho ứng dụng. Nếu reader bên dưới dùng sai charset, lớp đệm sẽ chuyển tiếp kết quả đã giải mã sai.

## 3. Constructor và hợp đồng API

### 3.1. `BufferedReader`

Các constructor thông dụng:

| Constructor | Ý nghĩa |
| --- | --- |
| `new BufferedReader(Reader in)` | Bọc reader bằng bộ đệm ký tự mặc định |
| `new BufferedReader(Reader in, int size)` | Bọc reader bằng bộ đệm có kích thước chỉ định |

Tham số `in` phải là một `Reader`, ví dụ `FileReader`, `InputStreamReader`, `StringReader` hoặc reader khác. Không có constructor nhận `InputStream` hay `Charset` trực tiếp.

### 3.2. `BufferedWriter`

| Constructor | Ý nghĩa |
| --- | --- |
| `new BufferedWriter(Writer out)` | Bọc writer bằng bộ đệm ký tự mặc định |
| `new BufferedWriter(Writer out, int size)` | Bọc writer bằng bộ đệm có kích thước chỉ định |

Tham số `out` phải là một `Writer`, ví dụ `FileWriter`, `OutputStreamWriter`, `StringWriter` hoặc writer khác. `BufferedWriter` không nhận `OutputStream` hay `Charset` trực tiếp.

Kích thước buffer phải là số dương. Kích thước không hợp lệ sẽ gây `IllegalArgumentException`. Khi dùng constructor không truyền kích thước, API chọn kích thước mặc định đủ dùng cho phần lớn trường hợp; không nên dựa vào một con số nội bộ cố định giữa các phiên bản JDK.

**Điểm cốt lõi:** API đệm nhận đối tượng `Reader`/`Writer` đã được tạo. Nó không nhận charset vì trách nhiệm charset thuộc về đối tượng chuyển mã ở tầng dưới.

## 4. Vì sao thêm BufferedReader không sửa được charset?

Đây là cách viết dễ gây hiểu nhầm:

```java
// Vẫn phụ thuộc default charset của JVM.
BufferedReader reader = new BufferedReader(
        new InputStreamReader(inputStream));
```

`BufferedReader` chỉ bọc reader. `InputStreamReader(inputStream)` ở bên trong mới chọn `Charset.defaultCharset()`. Nếu muốn đọc UTF-8 theo hợp đồng của dữ liệu, hãy chỉ rõ charset tại constructor chuyển mã:

```java
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

BufferedReader reader = new BufferedReader(
        new InputStreamReader(inputStream, StandardCharsets.UTF_8));
```

Chiều ghi cũng tương tự. Đoạn sau vẫn dùng charset mặc định ở tầng `OutputStreamWriter`:

```java
// Buffer không tự biến dữ liệu thành UTF-8.
BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(outputStream));
```

Cách rõ ràng cho dữ liệu UTF-8:

```java
import java.io.BufferedWriter;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(outputStream, StandardCharsets.UTF_8));
```

Có thể đọc quy tắc qua bảng:

| Cách tạo | Charset | Lớp đệm có thay đổi charset không? |
| --- | --- | --- |
| `new BufferedReader(new InputStreamReader(in))` | Default charset của JVM | Không |
| `new BufferedReader(new InputStreamReader(in, UTF_8))` | UTF-8 | Không |
| `new BufferedWriter(new OutputStreamWriter(out))` | Default charset của JVM | Không |
| `new BufferedWriter(new OutputStreamWriter(out, UTF_8))` | UTF-8 | Không |
| `new BufferedReader(new StringReader(text))` | Không có chuyển mã byte | Không áp dụng |

Trong bảng, `UTF_8` là cách viết rút gọn để chỉ `StandardCharsets.UTF_8`. Với `StringReader`, văn bản đã là ký tự trong bộ nhớ, không có byte đầu vào để giải mã.

## 5. Java 18, JEP 400 và cách tạo chuỗi I/O ổn định

Từ Java 18, JEP 400 quy định UTF-8 là default charset trong cấu hình thông thường của Java SE. Vì vậy, những API dựa vào `Charset.defaultCharset()` thường dùng UTF-8 trên JDK 18+.

Tuy nhiên:

- Default charset có thể khác trong cấu hình tương thích được JDK hỗ trợ, chẳng hạn `-Dfile.encoding=COMPAT`.
- File hoặc giao thức bên ngoài có thể quy định charset khác UTF-8.
- `BufferedReader`/`BufferedWriter` không kiểm tra và cũng không sửa các lựa chọn charset đó.

Do đó, chuỗi I/O nên thể hiện rõ hợp đồng dữ liệu tại tầng chuyển mã:

```java
Reader decoded = new InputStreamReader(input, StandardCharsets.UTF_8);
BufferedReader reader = new BufferedReader(decoded);
```

Hoặc dùng API tiện ích dành cho file:

```java
BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
```

`Files.newBufferedReader(path, charset)` trả về một `BufferedReader` và nhận charset tường minh. API này gộp bước tạo reader, decoder và lớp đệm vào một lời gọi, nhưng nguyên tắc vẫn vậy: charset đến từ tham số `charset`, không đến từ bộ đệm.

## 6. Đọc theo dòng với `BufferedReader.readLine()`

`BufferedReader` cung cấp `readLine()` để đọc từng dòng. Phương thức nhận diện các dạng kết thúc dòng `\n`, `\r` và `\r\n`, sau đó trả về phần nội dung **không chứa dấu kết thúc dòng**.

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;

static void printLines(Reader source) throws IOException {
    try (BufferedReader reader = new BufferedReader(source)) {
        String line;
        while ((line = reader.readLine()) != null) {
            System.out.println("Dòng: " + line);
        }
    }
}
```

Ba kết quả cần phân biệt:

- Dòng có nội dung trả về một `String`.
- Dòng trống trả về chuỗi rỗng `""`.
- Hết dữ liệu trả về `null`.

Vì `readLine()` bỏ dấu xuống dòng, không thể đọc rồi ghi lại bằng `write(line)` mà mong giữ nguyên loại newline ban đầu. Nếu định dạng đầu ra yêu cầu một dấu phân cách, chương trình phải tự ghi dấu phân cách.

Ví dụ đọc file UTF-8 theo dòng:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("messages.txt");

try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
```

`process` đại diện cho xử lý nghiệp vụ của ứng dụng. Đọc từng dòng giúp xử lý file lớn mà không phải tải toàn bộ nội dung vào một `String`.

### Khi cần giữ nguyên ký tự xuống dòng

Nếu yêu cầu giữ nguyên nội dung ký tự bao gồm cả dấu kết thúc dòng, đọc theo khối thay vì `readLine()`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;

static String readAllCharacters(Reader source) throws IOException {
    try (BufferedReader reader = new BufferedReader(source)) {
        StringBuilder result = new StringBuilder();
        char[] buffer = new char[4096];
        int count;

        while ((count = reader.read(buffer)) != -1) {
            result.append(buffer, 0, count);
        }
        return result.toString();
    }
}
```

Đoạn code giữ nguyên các ký tự mà `Reader` cung cấp, bao gồm `\r`, `\n` và `\r\n`. Nó vẫn không bảo toàn byte gốc nếu quá trình decode đã thay thế dữ liệu lỗi hoặc chuẩn hóa theo một quy tắc khác. Nếu cần copy file byte-for-byte, hãy dùng byte stream hoặc `Files.copy`, không chuyển qua Reader/Writer.

## 7. Ghi văn bản với `BufferedWriter`

`BufferedWriter` đệm ký tự trước khi chuyển chúng xuống writer bên dưới. Khi ghi nhiều đoạn nhỏ, buffer có thể giảm số lần gọi đến writer bên dưới.

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.Writer;

static void writeReport(Writer destination) throws IOException {
    try (BufferedWriter writer = new BufferedWriter(destination)) {
        writer.write("Báo cáo");
        writer.newLine();
        writer.write("Đã hoàn thành");
        writer.newLine();
    }
}
```

`write()` ghi ký tự; `newLine()` ghi dấu kết thúc dòng theo quy ước của hệ điều hành hiện tại. `newLine()` không có tham số charset và cũng không chọn charset cho writer bên dưới.

Nếu giao thức yêu cầu newline cố định, chẳng hạn LF (`\n`) bất kể hệ điều hành, hãy ghi rõ:

```java
writer.write("record-1");
writer.write('\n'); // LF theo đặc tả giao thức
```

Nếu định dạng yêu cầu CRLF, ghi `"\r\n"` theo đặc tả. Dùng `newLine()` khi định dạng cho phép line separator của nền tảng.

### Ghi ra UTF-8

```java
import java.io.BufferedWriter;
import java.io.OutputStreamWriter;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

static void writeUtf8(OutputStream output) throws IOException {
    try (BufferedWriter writer = new BufferedWriter(
            new OutputStreamWriter(output, StandardCharsets.UTF_8))) {
        writer.write("Xin chào, Tiếng Việt 🌍");
        writer.newLine();
    }
}
```

Ở đây, `BufferedWriter` đệm ký tự; `OutputStreamWriter` mã hóa các ký tự thành byte UTF-8. Nếu thay `StandardCharsets.UTF_8` bằng constructor không có charset, bộ đệm không thay đổi lựa chọn default charset.

## 8. Flush, close và thứ tự dữ liệu

Có thể có nhiều tầng đệm trong một chuỗi ghi:

```text
BufferedWriter
   | buffer ký tự
   v
OutputStreamWriter
   | chuyển mã + buffer byte
   v
OutputStream
   | buffer hoặc cơ chế riêng của đích
   v
File / Socket / thiết bị
```

`BufferedWriter.flush()` đẩy ký tự đang đệm xuống writer bên dưới và gọi `flush()` ở tầng đó. Nếu writer bên dưới là `OutputStreamWriter`, các byte đã mã hóa cũng được đẩy xuống output stream.

`close()` của `BufferedWriter` hoàn tất việc ghi và đóng writer bên dưới. Vì vậy, đóng wrapper ngoài cùng sẽ đóng cả chuỗi tài nguyên bên dưới.

| Thao tác | Tác dụng | Giới hạn |
| --- | --- | --- |
| `write(...)` | Đưa ký tự vào writer | Chưa chắc dữ liệu đã ra khỏi buffer |
| `flush()` | Đẩy dữ liệu đã đệm xuống tầng bên dưới | Không bảo đảm dữ liệu đã bền vững trên ổ đĩa hoặc được phía mạng xác nhận |
| `close()` | Hoàn tất ghi và đóng writer cùng tài nguyên bên dưới | Không phải transaction nguyên tử |
| `read()` | Lấy ký tự từ reader, có thể từ buffer | Không tương ứng một-một với lần đọc byte |

Không cần gọi `flush()` trước `close()` trong trường hợp thông thường vì `close()` hoàn tất việc flush. Chỉ flush giữa chừng khi luồng vẫn phải mở nhưng tầng tiêu thụ cần nhận dữ liệu ngay, ví dụ sau khi gửi một message hoàn chỉnh qua kết nối.

### Dùng try-with-resources ở wrapper ngoài cùng

```java
try (BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(output, StandardCharsets.UTF_8))) {
    writer.write("message");
    writer.flush(); // Chỉ cần nếu bên nhận cần dữ liệu trước khi đóng.
}
```

Chỉ cần quản lý wrapper ngoài cùng. Không cần khai báo cả `OutputStreamWriter` và `BufferedWriter` như hai resource riêng nếu wrapper là chủ sở hữu của writer bên trong; đóng wrapper đã đóng tầng dưới.

Tuy nhiên, nếu stream được chia sẻ hoặc do một tầng khác sở hữu, việc đóng wrapper cũng đóng stream gốc. Hãy thống nhất quyền sở hữu tài nguyên trước khi bọc nó. Không đóng `System.in`, `System.out` hoặc stream dùng chung khi phần khác của ứng dụng vẫn cần dùng.

## 9. Kích thước buffer và hiệu năng

Lớp đệm hữu ích khi ứng dụng thực hiện nhiều thao tác đọc/ghi nhỏ. Ví dụ, thay vì gọi xuống writer bên dưới cho từng ký tự, `BufferedWriter` có thể tích lũy ký tự và gửi theo khối.

Tuy nhiên, buffer lớn hơn không phải lúc nào cũng nhanh hơn:

- Dữ liệu nhỏ có thể không hưởng lợi đáng kể từ buffer rất lớn.
- Nhiều luồng đồng thời với buffer lớn làm tăng bộ nhớ sử dụng.
- Kích thước phù hợp phụ thuộc nguồn/đích, kích thước record và cách ứng dụng xử lý.
- `BufferedReader`/`BufferedWriter` mặc định đã chọn kích thước dùng chung phù hợp cho phần lớn trường hợp; chỉ truyền `size` khi có số đo hoặc yêu cầu cụ thể.

Ví dụ tùy chỉnh:

```java
BufferedReader reader = new BufferedReader(inputReader, 16 * 1024);
BufferedWriter writer = new BufferedWriter(outputWriter, 16 * 1024);
```

Con số `16 * 1024` chỉ là lựa chọn minh họa. Hãy đo hiệu năng với dữ liệu và môi trường triển khai thực tế trước khi điều chỉnh.

Đừng nhầm kích thước buffer ký tự với số byte. Một buffer có 16.384 đơn vị `char` không đồng nghĩa với buffer 16.384 byte UTF-8. Charset có thể mã hóa mỗi ký tự thành số byte khác nhau.

## 10. Mark, reset và đọc trước

`BufferedReader` hỗ trợ `mark(int readAheadLimit)` và `reset()` để đánh dấu một vị trí rồi quay lại trong giới hạn đã quy định:

```java
import java.io.BufferedReader;
import java.io.StringReader;

try (BufferedReader reader = new BufferedReader(
        new StringReader("header\nbody\n"))) {
    reader.mark(64);
    String first = reader.readLine();

    reader.reset();
    String again = reader.readLine();

    System.out.println(first.equals(again)); // true
}
```

`BufferedReader` hỗ trợ đánh dấu và quay lại; `readAheadLimit` xác định giới hạn ký tự có thể đọc sau điểm đánh dấu trước khi mark trở nên không còn hợp lệ. Không giả định có thể reset tùy ý sau khi đã đọc một lượng dữ liệu không giới hạn.

Lớp đệm có thể đọc trước ký tự từ reader bên dưới để lấp đầy buffer. Vì vậy, **không luân phiên đọc từ `BufferedReader` và reader gốc mà nó bọc**. Reader gốc có thể đã được đọc vượt qua vị trí mà ứng dụng quan sát được ở wrapper. Hãy chọn một đường đọc duy nhất và sử dụng nó nhất quán.

## 11. API tiện ích `Files` và khi nào không cần tự bọc

Khi làm việc với file, `Files` cung cấp các phương thức tạo reader/writer đã được đệm:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path input = Path.of("input.txt");
Path output = Path.of("output.txt");

try (BufferedReader reader =
        Files.newBufferedReader(input, StandardCharsets.UTF_8);
     BufferedWriter writer =
        Files.newBufferedWriter(output, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        writer.write(line);
        writer.newLine();
    }
}
```

Các phương thức này đã trả về `BufferedReader` và `BufferedWriter`; không cần bọc thêm lần nữa chỉ để có buffer.

Một khác biệt hữu ích: overload `Files.newBufferedReader(path)` và `Files.newBufferedWriter(path, options...)` không truyền charset có hợp đồng UTF-8 riêng. Trong khi đó, `new InputStreamReader(input)` hoặc `new OutputStreamWriter(output)` dùng default charset của JVM. Khi cần charset cụ thể, dùng overload có `Charset`.

Với `Files.newBufferedWriter(path, charset)` khi không truyền `OpenOption`, hành vi mặc định tương đương tạo file nếu chưa có, cắt ngắn file đã tồn tại và mở để ghi. Muốn append, truyền rõ `StandardOpenOption.CREATE` và `StandardOpenOption.APPEND` cùng charset. Lớp `BufferedWriter` không quyết định chế độ mở file; điều đó được xác định lúc tạo writer/stream.

Nếu dữ liệu vừa phải và cần lấy toàn bộ nội dung, `Files.readString(path, charset)` và `Files.writeString(path, text, charset)` có thể đơn giản hơn. Nếu cần xử lý streaming theo dòng hoặc dữ liệu lớn, `Files.newBufferedReader`/`newBufferedWriter` phù hợp hơn.

## 12. Kiểm soát lỗi giải mã và mã hóa

`BufferedReader` không có cơ chế chọn cách xử lý byte sai charset, vì nó chỉ nhận ký tự từ `Reader`. Chính sách decode được đặt ở `CharsetDecoder` mà `InputStreamReader` sử dụng.

Nếu yêu cầu UTF-8 hợp lệ và muốn báo lỗi thay vì âm thầm thay byte sai bằng ký tự thay thế, cấu hình decoder ở tầng chuyển mã:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(inputStream, decoder))) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
```

Khi chuỗi byte không hợp lệ, thao tác đọc có thể ném `MalformedInputException` hoặc ngoại lệ mã hóa liên quan (thuộc họ `IOException`). Ứng dụng cần quyết định từ chối record, báo lỗi cho nguồn gửi hoặc ghi nhận để xử lý. Không đổi charset tùy tiện để làm cho lỗi biến mất.

Chiều ghi cũng vậy: `BufferedWriter` không quyết định cách xử lý ký tự không thể biểu diễn trong charset. Nếu cần phát hiện mất dữ liệu, cấu hình `CharsetEncoder` với `CodingErrorAction.REPORT` và truyền encoder đó cho `OutputStreamWriter`.

## 13. Kiểm thử: buffer không làm thay đổi byte theo charset

Một kiểm thử tốt xác nhận byte thực tế ở tầng output và nội dung đọc lại bằng cùng charset. Dùng luồng byte trong bộ nhớ để tránh phụ thuộc terminal hoặc default charset:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String original = "café - Tiếng Việt 🌍";
ByteArrayOutputStream bytes = new ByteArrayOutputStream();

try (BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(bytes, StandardCharsets.UTF_8))) {
    writer.write(original);
}

byte[] expected = original.getBytes(StandardCharsets.UTF_8);
byte[] actual = bytes.toByteArray();

if (!Arrays.equals(expected, actual)) {
    throw new AssertionError("Buffering changed the UTF-8 byte sequence");
}

try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                new ByteArrayInputStream(actual),
                StandardCharsets.UTF_8))) {
    char[] buffer = new char[128];
    int count = reader.read(buffer);
    String restored = new String(buffer, 0, count);

    if (!original.equals(restored)) {
        throw new AssertionError("UTF-8 round-trip failed");
    }
}
```

Kiểm thử minh họa rằng `BufferedWriter` không thay đổi quy tắc mã hóa do `OutputStreamWriter` quyết định, và `BufferedReader` không thay đổi quy tắc giải mã do `InputStreamReader` quyết định.

Trong dự án thực tế, nên bổ sung:

1. Nội dung ASCII, tiếng Việt có dấu và ký tự ngoài BMP như `🌍`.
2. Nhiều dòng có `\n`, `\r\n`, dòng trống và dòng cuối không có newline.
3. Nội dung lớn hơn kích thước buffer.
4. Byte UTF-8 không hợp lệ khi dùng decoder `REPORT`.
5. Kiểm tra flush trước khi đóng nếu giao thức cần nhận dữ liệu giữa chừng.
6. Kiểm tra wrapper đóng đúng stream theo quyền sở hữu tài nguyên.

## 14. Những hiểu nhầm thường gặp

- **“Thêm `BufferedReader` sẽ khiến file được đọc bằng UTF-8.”** Sai. Charset do `InputStreamReader` hoặc API đọc file quyết định.
- **“`BufferedWriter` tự chọn charset khi ghi.”** Sai. Nó chuyển ký tự xuống `Writer` bên dưới.
- **“Buffer là buffer byte.”** Không. Hai lớp này đệm ký tự; tầng byte và tầng mã hóa có thể có buffer riêng.
- **“`readLine()` giữ lại dấu xuống dòng.”** Sai. Chuỗi trả về không chứa ký tự kết thúc dòng.
- **“`newLine()` luôn ghi LF.”** Sai. Nó ghi line separator của nền tảng.
- **“Gọi `flush()` đồng nghĩa dữ liệu đã được lưu bền vững.”** Sai. Flush đẩy dữ liệu qua tầng writer, không thay thế cơ chế đồng bộ lưu trữ hoặc xác nhận mạng.
- **“Đọc một phần qua wrapper rồi đọc tiếp từ reader gốc là an toàn.”** Sai. Buffer có thể đã đọc trước dữ liệu từ reader gốc.
- **“Tăng buffer luôn làm chương trình nhanh hơn.”** Không có bảo đảm; cần đo theo workload.

## 15. Tài liệu tham khảo chính thức

- [BufferedReader — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/BufferedReader.html): constructor, buffer, `readLine()`, `mark()` và `reset()`.
- [BufferedWriter — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/BufferedWriter.html): constructor, `write()`, `newLine()`, `flush()` và `close()`.
- [InputStreamReader — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/InputStreamReader.html): chuyển byte thành ký tự theo charset hoặc decoder.
- [OutputStreamWriter — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/OutputStreamWriter.html): chuyển ký tự thành byte theo charset hoặc encoder.
- [Files — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): `newBufferedReader`, `newBufferedWriter`, `readString` và `writeString`.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset từ Java 18 và các điểm tương thích.

