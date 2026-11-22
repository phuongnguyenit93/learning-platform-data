# Reader và Writer xử lý đơn vị `char` trong Java

Trong Java, `java.io.Reader` và `java.io.Writer` là hai lớp trừu tượng nền tảng cho **I/O ký tự**. `Reader` cung cấp thao tác **đọc** đơn vị `char` từ nguồn, còn `Writer` cung cấp thao tác **ghi** các đơn vị `char` đến đích. Đây là mô hình phù hợp khi ứng dụng làm việc với **văn bản**: nội dung file, chuỗi ký tự, log, dữ liệu trao đổi ở dạng text, v.v.

Điều quan trọng cần hiểu ngay từ đầu: một Java `char` là **một đơn vị mã UTF-16 16 bit**, không phải luôn luôn là một “ký tự người dùng nhìn thấy”. Vì thế API đọc/ghi `char` khác với API đọc/ghi **byte**, và cũng khác với việc duyệt **Unicode code point**.

## 1. Mô hình Reader/Writer và ranh giới dữ liệu

`Reader` và `Writer` thuộc gói `java.io`:

- **`Reader`**: nhận dữ liệu dạng ký tự từ một nguồn; ví dụ `StringReader` đọc chuỗi có sẵn, `InputStreamReader` giải mã byte từ `InputStream`, `BufferedReader` bọc một `Reader` để tăng hiệu quả và hỗ trợ đọc dòng.
- **`Writer`**: gửi dữ liệu dạng ký tự đến một đích; ví dụ `StringWriter` tích lũy ký tự trong bộ nhớ, `OutputStreamWriter` mã hóa ký tự thành byte để ghi vào `OutputStream`, `BufferedWriter` bổ sung bộ đệm và `newLine()`.
- Một `Reader` hoặc `Writer` là **kênh thao tác đọc/ghi**, không phải danh sách hay collection chứa sẵn toàn bộ văn bản; hành vi đọc, ghi, buffering và đóng phụ thuộc lớp triển khai và nguồn/đích.
- `Reader` không cung cấp `write()`, còn `Writer` không cung cấp `read()`. Muốn đọc một nguồn và ghi sang đích, dùng đồng thời hai đối tượng.

Sơ đồ luồng chuyển đổi khi dữ liệu lưu dưới dạng byte:

```text
Nguồn byte (file/socket/byte[])
         |
         v
InputStream --[InputStreamReader + Charset: giải mã]--> char/Reader
                                                           |
                                                           v
                                               Chương trình xử lý văn bản
                                                           |
                                                           v
OutputStream <--[OutputStreamWriter + Charset: mã hóa]-- char/Writer
         |
         v
Đích byte (file/socket/byte[])
```

`InputStreamReader` và `OutputStreamWriter` là **cầu nối** giữa byte stream và character stream; còn `StringReader`/`StringWriter` làm việc với ký tự đã ở bộ nhớ, không cần giải mã file.

## 2. `char` chính xác là đơn vị gì?

Kiểu nguyên thủy `char` trong Java có 16 bit và lưu **một UTF-16 code unit** (giá trị từ `0x0000` đến `0xFFFF`). Unicode code point là định danh của một ký tự Unicode trong khoảng `U+0000` đến `U+10FFFF`, loại trừ vùng surrogate khi xét code point hợp lệ.

- Phần lớn ký tự thông dụng trong **Basic Multilingual Plane (BMP)** dùng **một** `char`: `'A'`, `'đ'`, `'中'`.
- Ký tự thuộc vùng ngoài BMP, chẳng hạn emoji `😊` (U+1F60A), dùng **hai** `char` liên tiếp trong UTF-16, gọi là **surrogate pair**: `\uD83D` và `\uDE0A`.
- Một ký tự hiển thị có thể còn gồm **nhiều code point**, ví dụ chữ kèm dấu kết hợp hoặc emoji có biến thể. Vì vậy **đếm `char`**, **đếm code point** và **đếm grapheme cluster** là ba phép đếm khác nhau.
- `String.length()` trả về số UTF-16 code unit; `String.codePointCount(0, s.length())` đếm code point trong phạm vi đó; cả hai không bảo đảm tương đương số ký tự người dùng nhận thức.

Điều này tác động trực tiếp đến I/O: `Reader.read()` đọc **một UTF-16 code unit** trong mỗi lần trả về thành công, chứ không cam kết trả về nguyên vẹn một Unicode code point. `Writer.write(int)` ghi **16 bit thấp** của đối số thành một đơn vị `char`; nó không phải API “ghi một Unicode code point” tổng quát. Nếu cần biến code point ngoài BMP thành văn bản, hãy chuyển bằng `Character.toChars(codePoint)` hoặc xử lý chuỗi chứa surrogate pair đầy đủ.

### Ví dụ 1 — quan sát từng đơn vị `char` bằng `StringReader`

Tạo tệp `ReaderWriterUnitsDemo.java`:

```java
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;

public class ReaderWriterUnitsDemo {
    public static void main(String[] args) throws Exception {
        String text = "A😊B";
        try (Reader reader = new StringReader(text);
             StringWriter writer = new StringWriter()) {
            int codeUnit;
            while ((codeUnit = reader.read()) != -1) {
                System.out.printf("unit=U+%04X%n", codeUnit);
                writer.write(codeUnit);
            }
            String copy = writer.toString();
            System.out.println("char units=" + copy.length());
            System.out.println("code points=" + copy.codePointCount(0, copy.length()));
            System.out.println("same=" + text.equals(copy));
        }
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 ReaderWriterUnitsDemo.java
java ReaderWriterUnitsDemo
```

Kết quả chính xác:

```text
unit=U+0041
unit=U+D83D
unit=U+DE0A
unit=U+0042
char units=4
code points=3
same=true
```

`Reader.read()` trả về `int` để có đủ chỗ biểu diễn mọi giá trị `char` từ 0 đến 65535 **và** giá trị đặc biệt `-1` cho cuối luồng (EOF). Không nên chuyển ngay kết quả `read()` sang `char` rồi mới kiểm tra EOF, vì sẽ mất dấu hiệu `-1`.

Ví dụ có bốn code unit: `A`, surrogate cao, surrogate thấp, `B`; nhưng chỉ có ba code point. `StringWriter` ghi lại đúng từng unit nên khôi phục được chuỗi ban đầu. Nếu chuyển đổi từng code unit độc lập thành byte hoặc thành chuỗi rồi xử lý tùy tiện, surrogate pair có thể bị tách và làm sai văn bản.

## 3. Các phương thức cốt lõi và ý nghĩa giá trị trả về

| API | Ý nghĩa | Điểm cần nhớ |
|---|---|---|
| `int Reader.read()` | Đọc một UTF-16 code unit | Trả `0..65535` hoặc `-1` khi EOF; có thể ném `IOException` |
| `int Reader.read(char[] buffer)` | Đọc tối đa `buffer.length` code unit vào mảng | Trả **số phần tử thực sự đọc** hoặc `-1`; đừng giả sử mảng được lấp đầy |
| `int Reader.read(char[] b, int off, int len)` | Đọc tối đa `len` unit vào mảng từ vị trí `off` | Phải tôn trọng `off` và số lượng trả về; `len = 0` có thể trả `0` |
| `long Reader.skip(long n)` | Bỏ qua số `char` | Đơn vị là code unit; kết quả là số lượng thực sự bỏ qua |
| `boolean Reader.ready()` | Kiểm tra khả năng đọc không bị chặn ngay | **Không** phải phép kiểm tra EOF; `false` không có nghĩa đã hết dữ liệu |
| `void Writer.write(int c)` | Ghi một `char` | Dùng 16 bit thấp của `c` |
| `void Writer.write(char[] b, int off, int len)` | Ghi đúng đoạn mảng ký tự | Phù hợp khi sao chép từng khối đọc từ `Reader` |
| `void Writer.write(String s)` | Ghi chuỗi ký tự | Không tự chèn dấu xuống dòng |
| `void Writer.flush()` | Đẩy dữ liệu đang đệm xuống đích bên dưới | Không đồng nghĩa dữ liệu đã được đồng bộ bền vững xuống đĩa |
| `void close()` | Giải phóng tài nguyên | Gọi bằng `try-with-resources` khi sở hữu nguồn/đích |

Các thao tác trên có thể phát sinh `IOException` tùy triển khai. Khi đọc bằng `read(char[])`, một lần gọi **có thể lấy ít ký tự hơn số lượng yêu cầu**; đây không phải EOF. Kiểm tra `n == -1` để kết thúc và chỉ xử lý `buffer[0..n)`.

Một mẫu sao chép ký tự đúng là:

```java
char[] buffer = new char[4096];
int n;
while ((n = reader.read(buffer, 0, buffer.length)) != -1) {
    writer.write(buffer, 0, n);
}
writer.flush();
```

Đây là **đoạn minh họa nằm bên trong một hàm**; hai biến `reader` và `writer` phải được tạo ở nơi gọi, và caller phải xử lý `IOException`. Đặc biệt, dùng `writer.write(buffer)` thay cho `writer.write(buffer, 0, n)` có thể ghi cả ký tự cũ còn sót lại trong mảng ở lượt đọc cuối.

Sao chép các code unit nguyên vẹn bằng phương thức trên vẫn giữ đúng surrogate pair, kể cả khi hai phần của cặp nằm ở hai lượt đọc khác nhau. Ngược lại, các phép **biến đổi** theo từng khối (ví dụ cắt chuỗi, viết hoa theo `char`, mã hóa riêng mỗi khối) cần quan tâm khả năng tách surrogate và xử lý theo code point hoặc từng đoạn văn bản đầy đủ.

Từ Java 10, `Reader.transferTo(Writer)` có thể sao chép trực tiếp toàn bộ `char` còn lại sang writer, trả số đơn vị đã truyền; phương thức này **không tự đóng** reader hoặc writer.

## 4. Đọc và ghi văn bản thực tế qua `BufferedReader`/`BufferedWriter`

`BufferedReader` và `BufferedWriter` bọc nguồn/đích ký tự bằng bộ đệm, giảm chi phí của nhiều thao tác nhỏ:

- `BufferedReader.readLine()` lấy nội dung một dòng, **không kèm** ký tự kết thúc dòng; trả `null` khi không còn dòng nào. Dòng rỗng hợp lệ trả chuỗi rỗng `""`, không phải `null`.
- `BufferedWriter.newLine()` ghi dấu kết thúc dòng theo nền tảng (như LF hoặc CRLF); muốn định dạng chính xác bất kể hệ điều hành thì chủ động ghi dấu kết thúc dòng được giao thức/file format quy định.
- Bộ đệm không biến I/O thành một nguồn dữ liệu nằm hoàn toàn trong RAM. Nó chỉ giúp giảm số lần đọc/ghi xuống lớp bên dưới, tùy kích thước và cách truy cập.
- `Files.newBufferedReader(path, charset)` / `Files.newBufferedWriter(path, charset)` là cách thuận tiện để mở file văn bản với charset rõ ràng.

### Ví dụ 2 — đọc ghi file UTF-8, giữ tiếng Việt và emoji

Tạo tệp `TextFileDemo.java`:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextFileDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("reader-writer-", ".txt");
        String first = "Tiếng Việt: Nguyễn";
        String second = "Emoji: 😊";
        try {
            try (BufferedWriter writer =
                     Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
                writer.write(first);
                writer.newLine();
                writer.write(second);
            }
            try (BufferedReader reader =
                     Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String a = reader.readLine();
                String b = reader.readLine();
                String end = reader.readLine();
                System.out.println("line 1 matches=" + first.equals(a));
                System.out.println("line 2 matches=" + second.equals(b));
                System.out.println("EOF=" + (end == null));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 TextFileDemo.java
java TextFileDemo
```

```text
line 1 matches=true
line 2 matches=true
EOF=true
```

**Diễn giải luồng xử lý:**

1. `Files.createTempFile` tạo đường dẫn file thực tế. Chương trình không phụ thuộc vào file có sẵn.
2. `newBufferedWriter` ghi các code unit từ `String`, đồng thời lớp mã hóa chuyển chúng thành **byte UTF-8**. `newLine()` ghi dấu xuống dòng phù hợp nền tảng.
3. Khối `try-with-resources` đóng writer trước khi mở reader, bảo đảm dữ liệu đã đệm được gửi xuống dưới và file sẵn sàng cho lần đọc tiếp theo.
4. `newBufferedReader` đọc byte UTF-8 và giải mã thành code unit UTF-16. `readLine` trả các đoạn text **đã bỏ dấu kết thúc dòng**, vì vậy cả hai phép so sánh đều đúng.
5. Lần `readLine()` thứ ba trả `null`: EOF. Khối `finally` xóa file tạm sau khi reader đã đóng.

Lưu ý: `try-with-resources` cũng xử lý đóng khi có ngoại lệ. `finally` được dùng ở ví dụ để dọn file tạm; một lỗi xóa file vẫn có thể khiến chương trình ném `IOException`. Kết quả in ra là boolean nên ổn định ngay cả khi console của máy không hiển thị tiếng Việt hoặc emoji đúng.

## 5. Vì sao ký tự phải chuyển qua charset khi đi ra/vào byte?

**Java `char` không phải byte UTF-8.** Một code point có thể chiếm số byte khác nhau trong UTF-8; Java `String` giữ các UTF-16 code unit. Việc ghi text ra file, socket, hoặc một `OutputStream` cần một bước **mã hóa** (`encode`). Khi đọc byte thành text, cần **giải mã** (`decode`).

| Tầng dữ liệu | Đại diện | Đơn vị |
|---|---|---|
| Byte I/O | `InputStream`, `OutputStream`, `byte[]` | 8-bit byte |
| Character I/O | `Reader`, `Writer`, `char[]` | UTF-16 code unit |
| Unicode code point | `int`, `String.codePoints()` | Giá trị code point (có thể tương ứng một hoặc hai code unit) |
| Ký tự nhìn thấy | Grapheme cluster, giao diện người dùng | Có thể gồm nhiều code point |

Cầu nối phổ biến:

- **`InputStreamReader(input, StandardCharsets.UTF_8)`** giải mã byte từ input stream thành `char`.
- **`OutputStreamWriter(output, StandardCharsets.UTF_8)`** mã hóa `char` rồi ghi byte vào output stream.
- `Files.newBufferedReader` và `Files.newBufferedWriter` kết hợp mở file, chuyển charset và buffering theo cách tiện dụng.

Không nên phụ thuộc vào **charset mặc định của hệ thống** khi yêu cầu đọc/ghi văn bản chính xác giữa các máy. Hãy chọn charset theo định dạng dữ liệu hoặc giao thức, ví dụ `StandardCharsets.UTF_8`, và dùng thống nhất ở cả hai phía. Sai charset có thể làm biến dạng văn bản; xử lý chuỗi byte không hợp lệ còn tùy chính sách của bộ giải mã (thay thế ký tự lỗi hay báo lỗi).

### Ví dụ 3 — byte ⇄ char với `OutputStreamWriter` và `InputStreamReader`

Tạo tệp `EncodingBridgeDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Reader;
import java.io.StringWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;

public class EncodingBridgeDemo {
    public static void main(String[] args) throws Exception {
        String text = "Chữ 😊";
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (Writer writer = new OutputStreamWriter(sink, StandardCharsets.UTF_8)) {
            writer.write(text);
        }
        byte[] bytes = sink.toByteArray();
        StringWriter result = new StringWriter();
        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes), StandardCharsets.UTF_8)) {
            char[] buffer = new char[2];
            int n;
            while ((n = reader.read(buffer, 0, buffer.length)) != -1) {
                result.write(buffer, 0, n);
            }
        }
        String copy = result.toString();
        System.out.println("UTF-8 bytes=" + bytes.length);
        System.out.println("UTF-16 units=" + copy.length());
        System.out.println("same=" + text.equals(copy));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 EncodingBridgeDemo.java
java EncodingBridgeDemo
```

```text
UTF-8 bytes=10
UTF-16 units=6
same=true
```

Đoạn `"Chữ 😊"` có sáu UTF-16 code unit: `C`, `h`, `ữ`, dấu cách, hai unit của emoji. Nhưng sau khi mã hóa UTF-8, dãy dữ liệu cần **10 byte**. `OutputStreamWriter` nhận văn bản và tạo byte; `InputStreamReader` đọc lại byte và tái lập văn bản.

Bộ đệm ký tự trong ví dụ chỉ dài hai phần tử nhằm thể hiện việc **đọc từng khối**. Ngay cả khi một surrogate pair nằm qua ranh giới hai khối, thao tác `StringWriter.write(buffer, 0, n)` sao chép lại đúng chuỗi các code unit. Không giả định `n == 2`; lần đọc có thể trả ít hơn kích thước buffer.

`OutputStreamWriter` có thể giữ byte/code unit đang đệm, nên cần **flush hoặc close** trước khi lấy toàn bộ kết quả ở đích. Ví dụ đóng writer bằng `try-with-resources`; `ByteArrayOutputStream` trong bộ nhớ vẫn cho phép truy xuất `toByteArray()` sau đó.

## 6. Cách quản lý tài nguyên và buffering

`Reader` và `Writer` là các lớp triển khai `Closeable`, dùng được trong `try-with-resources`. Khi mở file, socket hay kết nối khác, hãy xác định **đối tượng nào sở hữu tài nguyên** và đóng nó đúng thời điểm:

```java
try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý từng dòng tại đây.
    }
}
```

Đây là **mẫu minh họa**, cần định nghĩa biến `path` và xử lý/khai báo `IOException` tại nơi gọi. Khi `BufferedReader` được đóng, nó cũng đóng `Reader` nằm bên dưới. Tương tự, đóng `BufferedWriter` làm đóng writer bên dưới; không đóng nguồn byte trước khi lớp bao ngoài hoàn tất việc đọc/ghi.

**`flush()` khác `close()`:**

- `flush()` đẩy dữ liệu đang được `Writer` giữ trong bộ đệm xuống các tầng bên dưới và vẫn cho phép ghi tiếp (nếu đích hỗ trợ).
- `close()` hoàn tất và giải phóng tài nguyên; với `BufferedWriter`/`OutputStreamWriter`, việc đóng đảm bảo flush phần dữ liệu đang đệm theo hợp đồng của lớp, nhưng có thể ném `IOException`.
- `flush()`/`close()` **không thay thế** yêu cầu đồng bộ bền vững xuống lưu trữ vật lý (ví dụ `FileChannel.force`) khi ứng dụng cần bảo đảm durability đặc biệt.

**Bộ đệm phù hợp cho thao tác nhỏ:** gọi `write` từng `char` không phải lúc nào cũng hiệu quả trên file hoặc mạng. Bọc writer bằng `BufferedWriter` hoặc dùng `Files.newBufferedWriter`; tương tự `BufferedReader` giúp hạn chế đọc lẻ từ nguồn. Không tự mặc định một buffer lớn hơn luôn tốt: quy mô, giao thức, dung lượng và thời gian phản hồi mới quyết định.

**Các lớp trong bộ nhớ:** `StringReader` và `StringWriter` vẫn tuân theo mô hình `Reader`/`Writer` nhưng không nắm file descriptor. Việc đóng chúng có sắc thái riêng theo triển khai; vẫn có thể dùng `try-with-resources` khi muốn thể hiện ranh giới sở hữu rõ ràng.

## 7. Các lỗi phổ biến và cách khắc phục

1. **Nghĩ `char` luôn là một Unicode code point.** Emoji ngoài BMP chiếm hai `char`. Muốn thao tác theo code point, dùng `String.codePoints()`, `Character.codePointAt(...)` và `Character.toChars(...)` thay vì xử lý từng `char` độc lập.
2. **Ép kết quả `read()` sang `char` trước khi kiểm tra `-1`.** Hãy nhận bằng `int`, so sánh với `-1`, rồi mới sử dụng giá trị đọc được.
3. **Giả sử `read(buffer)` luôn điền đầy mảng.** Lấy đúng số đơn vị `n` mà API trả về; khi ghi lại, gọi `write(buffer, 0, n)`.
4. **Dùng `ready()` để quyết định đã hết file.** `ready() == false` không tương đương EOF. Đọc tới lúc `read()` trả `-1` hoặc `readLine()` trả `null`.
5. **Nhầm dòng trống với EOF.** `readLine()` trả `""` cho dòng rỗng hợp lệ; `null` mới là hết dữ liệu.
6. **Dùng sai charset hoặc bỏ qua charset.** File UTF-8 đọc bằng charset khác có thể trở thành chữ lỗi; định nghĩa mã hóa rõ ràng ngay tại biên byte↔char.
7. **Dùng `Reader`/`Writer` để sao chép dữ liệu nhị phân.** Chuyển mã có thể biến đổi byte; ảnh, ZIP và nội dung nhị phân nên đi qua `InputStream`/`OutputStream` hoặc API byte tương ứng.
8. **Xử lý riêng từng nửa surrogate.** Một lần `read()` hoặc một khối buffer không bảo đảm ranh giới code point. Nếu sửa nội dung Unicode, phải chú ý kết hợp surrogate, dấu kết hợp và trường hợp có nhiều code point tạo thành một ký tự hiển thị.
9. **Bỏ `close()` hoặc quên `flush()` khi cần.** Với tài nguyên I/O, dùng `try-with-resources` và để lớp bao ngoài kiểm soát vòng đời của lớp bên dưới.
10. **Giả định `write(String)` hoặc `readLine()` giữ nguyên dấu xuống dòng.** `write(String)` không tự thêm xuống dòng; `readLine()` loại bỏ terminator. Khi bảo toàn định dạng newline quan trọng, đọc/ghi ký tự thô theo khối hoặc xử lý rõ chính sách dấu xuống dòng.
11. **Giả định các writer đều báo lỗi theo cùng cách.** `Writer` thường ném `IOException`; riêng `PrintWriter` có các phương thức in không ném `IOException` trong thao tác in thông thường và cung cấp `checkError()`. Hiểu hợp đồng của lớp thực tế.
12. **Xem `Reader`/`Writer` là đồng nghĩa `java.util.stream.Stream`.** Reader/Writer là API I/O theo `char`; `java.util.stream.Stream<T>` là pipeline xử lý phần tử. `BufferedReader.lines()` có thể tạo `Stream<String>` để xử lý dòng, nhưng vẫn cần quản lý reader đã mở.

## 8. Khi nào chọn lớp nào?

| Nhu cầu | Lựa chọn thường dùng | Lý do |
|---|---|---|
| Đọc file văn bản, xử lý từng dòng | `Files.newBufferedReader(path, UTF_8)` | `BufferedReader.readLine()` tiện lợi, có buffer |
| Ghi file văn bản, cần xuống dòng | `Files.newBufferedWriter(path, UTF_8)` | `write` và `newLine`, có buffer |
| Chuyển byte từ socket/file thành text | `InputStreamReader` + charset, có thể bọc `BufferedReader` | Giải mã theo đúng charset |
| Chuyển text thành byte cho socket/file | `OutputStreamWriter` + charset, có thể bọc `BufferedWriter` | Mã hóa theo đúng charset |
| Thử nghiệm hoặc tạo nội dung text trong bộ nhớ | `StringReader` / `StringWriter` | Không cần nguồn/đích hệ điều hành |
| Sao chép văn bản theo `char` | `Reader.transferTo(writer)` hoặc vòng lặp `read(char[])`/`write(char[],0,n)` | Sao chép dữ liệu ký tự đúng số lượng |
| Sao chép file nhị phân nguyên vẹn | `InputStream`/`OutputStream`, `Files.copy` | Giữ byte, không chuyển mã |

## 9. Kiểm tra hiểu bài

**Tình huống A.** Một `Reader` trả lần lượt `0xD83D` và `0xDE0A`. Có phải nguồn chứa hai emoji? **Không**. Đó là một surrogate pair biểu diễn một code point U+1F60A (😊).

**Tình huống B.** `reader.read(buffer)` trả `3` trong khi mảng dài `1024`. Có nên ghi toàn bộ `1024` phần tử? **Không**. Chỉ xử lý/ghi `buffer[0..3)`; phần còn lại không thuộc lần đọc này.

**Tình huống C.** `BufferedReader.readLine()` trả `""`. Đã đến EOF? **Chưa chắc; thông thường đó là dòng rỗng**. EOF được báo bằng `null`.

**Tình huống D.** File chứa tiếng Việt được ghi qua `OutputStreamWriter` nhưng đọc ra bị lỗi dấu. Kiểm tra gì trước? **Charset khi mã hóa và giải mã**, sau đó kiểm tra byte đầu vào và chính sách xử lý dữ liệu không hợp lệ.

**Tình huống E.** Cần lưu ảnh PNG mà không làm thay đổi một byte nào. Dùng `Writer`? **Không**. Chọn API I/O byte; `Writer` dành cho văn bản và có thể thực hiện chuyển mã.

## Kết luận

**`Reader` và `Writer` thao tác trên UTF-16 `char`, không trực tiếp trên byte hoặc Unicode code point.** `Reader.read()` trả một code unit dưới dạng `int` hoặc `-1` khi EOF; `Writer.write(...)` nhận code unit hay chuỗi code unit. Khi đi qua file, mạng hoặc nguồn byte, phải có một charset để **giải mã** hoặc **mã hóa**. Với văn bản thực tế, `BufferedReader`/`BufferedWriter` và `try-with-resources` giúp đọc/ghi hiệu quả, rõ quyền sở hữu tài nguyên và tránh bỏ sót dữ liệu đệm.

### Tài liệu tra cứu Java SE 17

- [`java.io.Reader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Reader.html) và [`java.io.Writer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Writer.html)
- [`InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html) và [`OutputStreamWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html)
- [`BufferedReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html) và [`BufferedWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html)
- [`java.lang.Character`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html), [`java.lang.String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`Files.newBufferedReader`, `Files.newBufferedWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
