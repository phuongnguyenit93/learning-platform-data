# `Reader.transferTo` và giới hạn xử lý dữ liệu lớn

## 1. Mục tiêu và phạm vi

Trong nhóm **luồng ký tự (character streams)** của Java I/O, `Reader.transferTo(Writer)` cho phép sao chép toàn bộ dữ liệu ký tự từ nguồn `Reader` sang đích `Writer` mà không phải viết vòng lặp thủ công cho tình huống đọc đến hết dữ liệu. API này có từ **Java 10** và dùng được trên Java 17+.

Sau bài này, bạn cần hiểu chính xác API sao chép gì, trả về đơn vị gì, khi nào nó xử lý dữ liệu lớn với bộ nhớ nhỏ, vì sao vẫn có thể gây hết bộ nhớ/đầy ổ đĩa, và cách đặt giới hạn khi nguồn dữ liệu không đáng tin cậy.

> `transferTo` **không có tham số giới hạn**, không tự đóng hoặc flush hai luồng, không đặt thời gian chờ và không bảo đảm dữ liệu đã ghi được rollback khi xảy ra lỗi.

Với dữ liệu nhị phân (ảnh, ZIP, tệp nén, giao thức byte), dùng `InputStream`/`OutputStream` hoặc API tệp phù hợp. `Reader`/`Writer` dành cho nội dung **ký tự** và thường cần xử lý charset ở ranh giới tệp/luồng byte.

## 2. Cách `Reader.transferTo` hoạt động

Hình thức gọi:

```java
long transferred = reader.transferTo(writer);
```

Phương thức đọc ký tự từ `reader` theo các khối, lần lượt viết các ký tự đã đọc sang `writer` và dừng khi reader báo **EOF**. Không có phép biến đổi nghiệp vụ như tách dòng, lọc ký tự hay phân tích nội dung. Trong triển khai thông thường, việc sao chép theo khối giúp không phải giữ toàn bộ nội dung trong một mảng lớn, nhưng bộ nhớ thực tế phụ thuộc cả reader, writer và ứng dụng bao quanh.

| Thuộc tính | Ý nghĩa |
| --- | --- |
| Khai báo API | `public long transferTo(Writer out) throws IOException` trong `java.io.Reader` |
| Dữ liệu | Các đơn vị ký tự `char` (UTF-16 code units) |
| Điểm dừng | Reader báo EOF; nếu nguồn tiếp tục có dữ liệu, hàm tiếp tục đọc |
| Giá trị trả về | `long`: số đơn vị `char` truyền được, **không phải số byte** |
| Thứ tự | Các ký tự đến writer theo thứ tự reader cung cấp |
| Ngoại lệ | Lỗi đọc/ghi ném `IOException`; dữ liệu đích có thể đã ghi một phần |
| Đóng tài nguyên | Người gọi phải quản lý `close()` bằng `try-with-resources` khi phù hợp |
| Flush | Không dựa vào `transferTo` để tự flush writer |
| Giới hạn dung lượng | Không có giới hạn ký tự, byte hoặc tệp được tích hợp |
| Thời gian | Có thể block khi đọc/ghi; không tự đặt timeout/cancellation |

Phân biệt ba ý niệm thường bị nhầm:

- **`Reader.transferTo(Writer)`** sao chép ký tự và trả số UTF-16 code units.
- **`InputStream.transferTo(OutputStream)`** sao chép byte, phù hợp dữ liệu nhị phân và trả số byte.
- **`java.util.stream.Stream<T>`** là API xử lý phần tử theo mô hình stream, không phải luồng byte/ký tự trong `java.io`.

### 2.1. Số `char` không bằng số byte

Java `char` là một đơn vị mã UTF-16. Một Unicode code point ngoài BMP (ví dụ emoji) được biểu diễn bằng **hai** `char`. Trong UTF-8, một ký tự có thể chiếm nhiều byte.

| Văn bản | Unicode code points | UTF-16 code units | UTF-8 bytes |
| --- | ---: | ---: | ---: |
| `ABC` | 3 | 3 | 3 |
| `A😀B` | 3 | 4 | 6 |
| `A😀B\n` (có LF) | 4 | 5 | 7 |

Do đó `transferTo` trả `5` khi truyền `A😀B\n` qua reader/writer, nhưng tệp UTF-8 chứa **7 byte**. Không lấy `transferred` làm giá trị dung lượng file hoặc quota mạng. `String.length()` cũng đo đơn vị UTF-16, không đo số code points hay byte.

### 2.2. Charset nằm ở hai đầu luồng

Khi nguồn là tệp, `Files.newBufferedReader(path, StandardCharsets.UTF_8)` giải mã byte UTF-8 thành ký tự; khi ghi tệp, `Files.newBufferedWriter(path, StandardCharsets.UTF_8)` mã hóa ký tự trở lại UTF-8. Bản thân `Reader.transferTo` chỉ chuyển các ký tự.

```text
File source UTF-8 bytes
      |
Files.newBufferedReader(..., UTF_8)
      |
Reader -- char[] theo từng khối --> Writer
                                     |
                              Files.newBufferedWriter(..., UTF_8)
                                     |
                              File target UTF-8 bytes
```

Khi cần giữ nguyên **byte**, chẳng hạn sao chép file ZIP hoặc kiểm tra checksum nhị phân, không giải mã và mã hóa lại bằng character streams. Nếu đầu vào chứa byte không hợp lệ theo charset, reader/decoder có thể ném lỗi hoặc áp dụng chính sách thay thế tùy cách cấu hình; không tự giả định mọi byte tùy ý đều là văn bản.

## 3. Ví dụ chạy được: chuyển toàn bộ tệp văn bản

Chương trình Java 17 dưới đây dùng thư mục tạm, tạo tệp đầu vào nhỏ, chuyển ký tự UTF-8 sang tệp đích, rồi kiểm tra nội dung. Hai reader/writer được đóng bằng `try-with-resources`. Đoạn so sánh bằng `Files.readString` chỉ dành cho **tệp thử nhỏ**, không phải cách xác minh tệp hàng GB.

Lưu thành **`ReaderTransferToDemo.java`** (UTF-8):

```java
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReaderTransferToDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("reader-transfer-");
        Path source = directory.resolve("source.txt");
        Path target = directory.resolve("target.txt");

        try {
            Files.writeString(source, "A😀B\n", StandardCharsets.UTF_8);

            long transferred;
            try (Reader in = Files.newBufferedReader(
                        source, StandardCharsets.UTF_8);
                 Writer out = Files.newBufferedWriter(
                        target, StandardCharsets.UTF_8)) {
                transferred = in.transferTo(out);
            }

            String before = Files.readString(source, StandardCharsets.UTF_8);
            String after = Files.readString(target, StandardCharsets.UTF_8);
            System.out.println("UTF-16 units: " + transferred);
            System.out.println("Contents match: " + before.equals(after));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch, chạy với JDK 17+:

```bash
javac -encoding UTF-8 ReaderTransferToDemo.java
java ReaderTransferToDemo
```

`stdout` của lần chạy thành công:

```text
UTF-16 units: 5
Contents match: true
```

Giải thích: `A` và `B` chiếm một `char` mỗi ký tự, `😀` chiếm hai `char`, `\n` chiếm một `char`, tổng cộng 5. `Reader.transferTo` không đóng luồng; hai đối tượng được đóng khi thoát khối `try-with-resources`, kể cả khi có ngoại lệ. Sau khi đóng writer, chương trình đọc tệp đích để kiểm tra. `finally` cố dọn hai tệp và thư mục tạm; lỗi dọn tài nguyên cũng có thể phát sinh `IOException`, nên ứng dụng thực tế phải chọn chính sách xử lý lỗi rõ ràng.

**Giới hạn ví dụ:** Nội dung rất nhỏ; không có kiểm soát kích thước tối đa, timeout, ghi nguyên tử hay xác minh checksum streaming. Không lấy `Files.readString` trên tệp lớn chỉ để so sánh nội dung.

## 4. Khi nào xử lý dữ liệu lớn mà không dùng nhiều heap?

Nếu đầu vào là `Files.newBufferedReader` và đầu ra là `Files.newBufferedWriter`, reader và writer có bộ đệm hữu hạn, dữ liệu được chuyển dần, nên ứng dụng **không bắt buộc** phải nạp toàn bộ tệp vào RAM. Phân biệt:

- **Bộ đệm truyền**: mảng ký tự của quá trình đọc/ghi thường có kích thước giới hạn; việc sao chép không nhất thiết tạo một `String` bằng kích thước tệp.
- **Bộ nhớ của đích**: `StringWriter`, `StringBuilder` hoặc `List<String>` tích lũy dữ liệu trong heap; chúng vẫn có thể lớn tỷ lệ với toàn bộ input.
- **Bộ nhớ nguồn**: nếu ứng dụng đã gọi `Files.readString` trước đó, nội dung lớn vốn đã được giữ trong bộ nhớ dù về sau gọi `transferTo`.
- **Chi phí ngoài heap**: đích tệp có thể tăng liên tục và làm hết dung lượng đĩa; hệ điều hành, bộ mã hóa và các lớp bao có thêm chi phí I/O.

Ví dụ phản diện sau minh họa writer gom tất cả nội dung:

```java
// Đoạn minh họa: biến path phải là Path hợp lệ.
// Không phù hợp nếu nguồn có thể dài hàng GB.
try (Reader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    java.io.StringWriter writer = new java.io.StringWriter();
    reader.transferTo(writer);
    String entireContent = writer.toString();
}
```

`StringWriter` giữ tất cả ký tự trong bộ nhớ; `toString()` tiếp tục tạo đối tượng `String` kết quả. Không có gì trong `transferTo` bảo đảm toàn pipeline dùng ít RAM khi writer tích lũy nội dung. Đoạn trên không phải chương trình độc lập và đòi hỏi `path` cùng các import thích hợp.

Với đầu vào lớn, đầu ra nên có khả năng ghi dần (tệp, socket hoặc bộ tiếp nhận có backpressure), có cách đo/giới hạn dung lượng, không gom hết dữ liệu vào một collection. Nếu phải xử lý từng bản ghi, ưu tiên vòng đọc theo dòng/khối, tránh tạo bản sao đầy đủ.

## 5. Những giới hạn mà `Reader.transferTo` không cung cấp

### 5.1. Dung lượng và đơn vị đo

Không có đối số `maxChars` hoặc `maxBytes`. `long transferred` chỉ có ý nghĩa **sau** khi công việc thành công; nó không ngăn writer ghi quá dung lượng cho phép. Nếu đầu ra là tệp, số byte viết thực còn phụ thuộc charset. Hạn mức byte nghiêm ngặt phải được áp dụng ở tầng byte hoặc đầu ra mã hóa được đo đếm, không suy từ UTF-16 units.

### 5.2. Thời gian, EOF và nguồn mở lâu

`Reader.transferTo` đọc đến EOF. Một reader kết nối với socket/pipe có thể chờ khi chưa có dữ liệu mới; nếu nguồn không kết thúc, lệnh sao chép có thể kéo dài vô hạn. Đặt **read timeout, deadline, cancellation hoặc giới hạn giao thức** tại lớp nguồn/thành phần bao quanh khi hỗ trợ. Không coi việc dùng `BufferedReader` là cơ chế timeout.

### 5.3. Ghi dở khi lỗi

Nếu `Reader.read` hoặc `Writer.write` ném `IOException`, writer có thể đã nhận một số ký tự. Không có rollback tự động. Với đầu ra có ý nghĩa nghiệp vụ, cân nhắc ghi vào tệp tạm, xác minh hoàn chỉnh rồi mới công bố/thay thế. `Files.move` cùng `ATOMIC_MOVE` tùy khả năng của filesystem; không giả định mọi nền tảng đều hỗ trợ.

### 5.4. Không xử lý từng dòng hoặc dừng ở điều kiện

`transferTo` chuyển tất cả ký tự. Nếu phải kiểm tra độ dài từng dòng, xử lý CSV, cắt tại marker, lọc record hoặc đếm dòng, cần vòng đọc thích hợp với quy tắc nghiệp vụ. `BufferedReader.readLine()` bỏ ký tự kết thúc dòng; muốn giữ nguyên `\n` và `\r\n` thì không tái tạo văn bản bằng `readLine()` một cách mù quáng.

## 6. Sao chép có giới hạn: vòng lặp thay cho `transferTo`

Để chặn nguồn quá dài theo **số UTF-16 code units**, dùng vòng lặp với mảng `char[]` có kích thước giới hạn. Đoạn dưới sẽ báo lỗi khi nguồn vượt mức cho phép, thay vì im lặng coi bản bị cắt cụt là hoàn chỉnh.

Lưu thành **`BoundedReaderCopyDemo.java`**:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;

public class BoundedReaderCopyDemo {
    static long copyWithLimit(
            Reader reader, Writer writer, long maxUnits) throws IOException {
        if (maxUnits < 0) {
            throw new IllegalArgumentException("maxUnits must be nonnegative");
        }

        char[] buffer = new char[4096];
        long copied = 0;

        while (true) {
            long remaining = maxUnits - copied;

            if (remaining == 0) {
                if (reader.read() != -1) {
                    throw new IOException(
                            "Input exceeds " + maxUnits + " UTF-16 units");
                }
                return copied;
            }

            int requested = (int) Math.min(buffer.length, remaining);
            int read = reader.read(buffer, 0, requested);

            if (read == -1) {
                return copied;
            }
            if (read == 0) {
                throw new IOException("Reader made no progress");
            }

            writer.write(buffer, 0, read);
            copied += read;
        }
    }

    public static void main(String[] args) throws IOException {
        try (Reader reader = new StringReader("abcdef");
             StringWriter writer = new StringWriter()) {
            try {
                copyWithLimit(reader, writer, 4);
                System.out.println("Copy complete");
            } catch (IOException error) {
                System.out.println("Limit exceeded: " + error.getMessage());
            }
            System.out.println("Partial output: " + writer);
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 BoundedReaderCopyDemo.java
java BoundedReaderCopyDemo
```

`stdout`:

```text
Limit exceeded: Input exceeds 4 UTF-16 units
Partial output: abcd
```

**Cơ chế:** `copyWithLimit` đọc tối đa phần hạn mức còn lại. Sau khi đã ghi 4 đơn vị `abcd`, nó đọc thử thêm một đơn vị để xác định nguồn có tiếp tục hay không. Nguồn còn `e`, vì vậy ném `IOException`. Writer đang chứa `abcd`: **báo lỗi không có nghĩa đầu ra đã được hoàn tác**.

Các giới hạn còn lại của ví dụ:

1. **Hạn mức ký tự khác hạn mức byte**: đây là UTF-16 units; UTF-8 có độ dài byte khác. Nếu quota áp dụng cho dữ liệu lưu trữ, phải đếm byte thực.
2. **Có thể cắt giữa surrogate pair**: một giới hạn `char` rơi giữa hai đơn vị của emoji có thể làm nội dung đầu ra mất hợp lệ khi mã hóa. Nếu yêu cầu giới hạn theo code point, hãy thiết kế bộ đọc có xử lý surrogate pair; nếu yêu cầu không cắt grapheme cluster, cần quy tắc phân đoạn Unicode cao hơn.
3. **Vẫn có thể block**: bước đọc thêm khi chạm hạn mức cần xác định có EOF thật; với nguồn truyền liên tục hoặc không kết thúc, phải kết hợp timeout/cancellation ở tầng nguồn.
4. **Không tự xóa bản ghi dở**: nếu phát hiện vượt hạn mức sau khi đã ghi, đích cần được bỏ hoặc ghi vào file tạm thay vì được công bố.
5. **Ví dụ dùng input nhỏ để xác minh stdout**: `StringReader`/`StringWriter` phù hợp minh họa, không phải mô hình xử lý tệp lớn trong thực tế.

Trường hợp nghiệp vụ chỉ muốn **cắt lấy tối đa N đơn vị** và không cần kiểm tra còn dữ liệu hay không, có thể bỏ bước đọc thử ngoài hạn mức, nhưng phải ghi rõ đầu ra là bản cắt cụt theo chủ đích.

## 7. Chọn API theo yêu cầu

| Bài toán | Gợi ý API | Điểm cần kiểm soát |
| --- | --- | --- |
| Chuyển toàn bộ văn bản từ reader sang writer | `Reader.transferTo` | EOF, charset ở đầu/cuối, quản lý tài nguyên |
| Đọc tệp UTF-8 lớn và ghi tệp UTF-8 | `Files.newBufferedReader` → `transferTo` → `Files.newBufferedWriter` | Đường dẫn, dung lượng tệp đích, ngoại lệ |
| Giới hạn tổng số UTF-16 units | Vòng lặp `read(char[])`/`write` có bộ đếm | Surrogate pairs; tác động của bản ghi dở |
| Giới hạn theo byte | Byte streams và bộ đếm byte | Dữ liệu mã hóa thực; không đếm bằng `char` |
| Sao chép nguyên tệp | `Files.copy` | Xử lý tệp đã tồn tại, quyền truy cập, metadata |
| Sao chép nhị phân | `InputStream.transferTo(OutputStream)` | Byte, resource cleanup, quota |
| Phân tích từng dòng | `BufferedReader.readLine()`, hoặc `lines()` | Line ending, dòng quá dài, đóng stream |
| Đọc theo vị trí tệp | `FileChannel` với `ByteBuffer` | Position/limit, đọc/ghi từng phần |
| Truyền dữ liệu có thể mở vô hạn | API nguồn có timeout/cancellation kết hợp quota | Không đợi `transferTo` tự dừng |

Lựa chọn chính dựa trên **định dạng dữ liệu** (byte hay ký tự), **khả năng kết thúc**, **giới hạn tài nguyên** và **yêu cầu nhất quán** của đầu ra.

## 8. Lỗi phổ biến và phương pháp kiểm thử

**Lỗi dễ gặp:**

- Đo số byte bằng `Reader.transferTo`; với UTF-8 và emoji, giá trị sẽ sai.
- Cho rằng sao chép theo khối luôn tiết kiệm RAM, nhưng đích là `StringWriter` hoặc các khối được thêm vào `List`.
- Gọi `transferTo` với dữ liệu không đáng tin mà không có quota; input vô hạn có thể làm đầy tệp.
- Mong `transferTo` tự đóng writer hoặc tự flush/bảo đảm ghi bền vững; nó không làm vậy.
- Bắt `IOException` rồi tiếp tục công bố file kết quả chưa đầy đủ.
- Kiểm tra `Files.size(path)` trước khi đọc rồi cho rằng dữ liệu/đường dẫn không thể thay đổi trong lúc chạy.
- Dùng character streams để sao chép byte nhị phân.
- Dùng `readLine()` để sao chép chính xác văn bản mà quên mất ký tự kết thúc dòng đã bị bỏ.
- Không xử lý giới hạn thời gian khi Reader đang chờ đầu vào.
- Thực thi giới hạn theo `char` rồi nhầm đó là giới hạn Unicode code point hoặc grapheme cluster.

**Bài tập tự kiểm tra:**

1. Chuyển chuỗi rỗng và giải thích vì sao `transferred == 0`.
2. Chuyển `A😀B\n` bằng UTF-8; giải thích vì sao kết quả 5 units nhưng 7 bytes.
3. Dùng vòng lặp có ngưỡng 4: input `abcd` thành công; input `abcde` báo lỗi; giải thích writer có thể chứa gì sau lỗi.
4. Thử sử dụng `StringWriter` với input ngày càng lớn (trong giới hạn môi trường), so sánh với writer ra tệp.
5. Giả lập `IOException` từ writer và xác minh lỗi không bị nuốt, tài nguyên được đóng.
6. Thiết kế cách ghi tệp đích tạm, chỉ thay thế tệp thật khi toàn bộ quá trình đọc/ghi/kiểm tra thành công.
7. Với một reader đọc từ nguồn có thể không phát EOF, giải thích nơi phải đặt timeout, deadline hoặc cancellation.

## 9. Ghi nhớ để áp dụng đúng

`Reader.transferTo` là lựa chọn gọn cho việc **chuyển hết luồng ký tự đến EOF**. Nó thường hỗ trợ sao chép theo từng khối, nhưng không thay cho chính sách tài nguyên của ứng dụng. Khi xử lý dữ liệu lớn, cần xem toàn bộ pipeline: loại reader và writer, charset, giới hạn char/byte, timeout, cách xử lý output dở và điều kiện công bố kết quả. Nếu cần giới hạn hoặc biến đổi nội dung, triển khai vòng lặp có chủ đích thay vì chỉ dựa vào `transferTo`.