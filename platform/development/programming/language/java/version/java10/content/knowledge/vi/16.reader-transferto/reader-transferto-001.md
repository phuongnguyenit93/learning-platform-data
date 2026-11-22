# Chuyển ký tự từ `Reader` sang `Writer` bằng `transferTo` (Java 10+)

## 1. Vấn đề và ý tưởng của `Reader.transferTo`

Trong Java, dữ liệu văn bản thường được đọc qua `java.io.Reader` và ghi qua `java.io.Writer`. Trước khi có phương thức tiện ích mới, để sao chép hết nội dung còn lại của một Reader sang Writer, người lập trình thường cần tự tạo mảng `char[]`, đọc từng khối và ghi từng khối.

**Từ Java 10**, `java.io.Reader` cung cấp phương thức:

```java
public long transferTo(Writer out) throws IOException
```

Phương thức này đọc **toàn bộ ký tự còn lại** từ vị trí hiện tại của Reader, ghi các ký tự vào Writer **theo đúng thứ tự đọc**, rồi trả về **số đơn vị ký tự đã chuyển** với kiểu `long`.

```java
var reader = new java.io.StringReader("Java 10");
var writer = new java.io.StringWriter();

long copied = reader.transferTo(writer);

System.out.println(copied);            // 7
System.out.println(writer.toString()); // Java 10
```

Đây là đoạn minh họa trong phương thức có `throws IOException` hoặc xử lý ngoại lệ. `transferTo` giúp diễn đạt rõ ý định: **chuyển phần ký tự còn lại từ nguồn đến đích**.

Những điều quan trọng ngay từ đầu:

- Đọc **từ vị trí hiện tại** đến khi hết luồng (EOF).
- Truyền dữ liệu ở mức **ký tự Java `char`**, **không** phải byte.
- Trả về `long` là số ký tự đã chuyển, **không** phải số dòng hay số Unicode code point.
- Khi thành công, Reader ở EOF.
- **Không tự đóng** cả Reader lẫn Writer; không thay việc quản lý tài nguyên.
- Không bảo đảm đích được tự gọi `flush()`.
- Writer `null` gây `NullPointerException`; lỗi I/O có thể gây `IOException`.
- Không tự chuẩn hóa ký tự, chuyển `\r\n` thành `\n` hay chọn charset.

Đây là một API chuẩn vẫn áp dụng trên Java hiện đại, không phải kỹ thuật đã trở thành legacy. Chủ đề này thuộc module Java 10 vì `Reader.transferTo(Writer)` được thêm từ bản đó.

## 2. Mục tiêu học tập và khái niệm cốt lõi

Sau bài học, bạn có thể:

1. Gọi `reader.transferTo(writer)` đúng chiều.
2. Hiểu `Reader` trừu tượng hóa nguồn **ký tự**, còn `Writer` trừu tượng hóa đích **ký tự**.
3. Dự đoán số đếm `long` và trạng thái Reader khi chuyển hết, rỗng hoặc đã đọc một phần.
4. Phân biệt số **`char` UTF-16**, Unicode code point và byte UTF-8.
5. Sử dụng `StringReader/StringWriter` để thử nghiệm, `Files.newBufferedReader/newBufferedWriter` để chép văn bản trong file.
6. Biết vì sao `transferTo` không thay thế `try-with-resources` hoặc xử lý `flush`.
7. Xử lý đúng `IOException` và rủi ro đầu ra đã được ghi một phần.
8. Phân biệt `Reader.transferTo(Writer)` với `InputStream.transferTo(OutputStream)` và `Files.copy`.
9. Bảo toàn line endings khi sao chép nguyên bản theo chuỗi ký tự.
10. Tạo kiểm thử với stdout độc lập charset mặc định và file hệ thống.

**Ba khái niệm cần tách biệt:**

- **Ký tự Java:** một đơn vị `char` 16 bit theo mô hình UTF-16 của Java.
- **Code point Unicode:** một ký tự Unicode trừu tượng, có thể được biểu diễn bằng 1 hoặc 2 `char`.
- **Byte:** đơn vị dữ liệu của `InputStream/OutputStream`. Kích thước byte sau mã hóa phụ thuộc charset.

`transferTo` trong `Reader` đếm đơn vị đầu tiên, không đếm hai đơn vị còn lại.

## 3. Cú pháp, chiều chuyển và giá trị trả về

Cách gọi đúng:

```java
long charactersTransferred = reader.transferTo(writer);
```

| Thành phần | Vai trò |
| --- | --- |
| `reader` | Nguồn ký tự thuộc `Reader`, ví dụ `StringReader`, `BufferedReader`, `InputStreamReader` |
| `writer` | Đích ký tự thuộc `Writer`, ví dụ `StringWriter`, `BufferedWriter`, `OutputStreamWriter` |
| `transferTo(writer)` | Đọc mọi ký tự còn lại rồi ghi vào Writer |
| `long` trả về | Số `char` được chuyển thành công |
| `IOException` | Có thể được ném khi đọc hoặc ghi xảy ra lỗi |
| `NullPointerException` | Xảy ra nếu Writer được truyền vào là `null` |

```java
reader.transferTo(writer); // Đúng
// writer.transferTo(reader); // Sai: Writer không định nghĩa API này
```

Sơ đồ logic:

```text
Reader (vị trí hiện tại)
          |
          | read các char cho tới EOF
          v
   transferTo(writer)
          |
          | write các char theo thứ tự đọc
          v
Writer (đích nhận ký tự)

Kết quả: long = số char được chuyển
Sau thành công: Reader ở EOF
Không tự close/flush: caller xử lý vòng đời tài nguyên
```

Đây là mô hình **hành vi API**. Không nên dựa vào kích thước buffer, số lần `read`/`write`, lịch chạy hay chiến lược tối ưu của implementation cụ thể.

Không có tham số offset hay `maxChars` trong `Reader.transferTo`. Nếu bạn cần chuyển chính xác một đoạn với giới hạn kích thước, cần Reader được giới hạn hoặc một vòng lặp sao chép có quota.

## 4. Vì sao API mới thay được vòng lặp sao chép thông thường?

Mẫu cũ (vẫn hợp lệ, nhưng dài hơn):

```java
char[] buffer = new char[8192];
int n;
long copied = 0L;

while ((n = reader.read(buffer)) != -1) {
    writer.write(buffer, 0, n);
    copied += n;
}
```

Đoạn mã này minh họa logic trong phương thức đã có `reader` và `writer`. Nó cần:

- Cấp phát buffer.
- Đọc tối đa một khối ký tự mỗi lần.
- Ghi đúng `n` ký tự hợp lệ.
- Cộng dồn số lượng.
- Dừng khi `read` trả về `-1`.

Với Java 10+:

```java
long copied = reader.transferTo(writer);
```

Phương thức làm ý định **chuyển toàn bộ phần còn lại** rõ ràng, giảm lỗi dùng nhầm kích thước buffer hoặc offset. Bạn vẫn cần viết vòng lặp thủ công khi phải biến đổi dữ liệu từng khối, báo tiến độ, dừng theo quota hoặc xử lý streaming theo chính sách riêng.

**Không nên kết luận** mọi `Reader.transferTo` luôn dùng buffer 8192 ký tự; đó là một lựa chọn trong ví dụ thủ công, không phải bảo đảm của public API.

## 5. Ví dụ trong bộ nhớ: `StringReader` → `StringWriter`

Với một chuỗi nhỏ, dùng Reader/Writer trong bộ nhớ giúp kiểm tra mà không phụ thuộc file và charset mặc định.

```java
try (var reader = new java.io.StringReader("Xin\nJava!");
     var writer = new java.io.StringWriter()) {

    long copied = reader.transferTo(writer);

    System.out.println(copied); // 9
    System.out.println(
            "Xin\nJava!".equals(writer.toString())); // true
}
```

`"Xin\nJava!"` có:

- `Xin`: 3 `char`.
- Ký tự xuống dòng `\n`: 1 `char`.
- `Java!`: 5 `char`.
- Tổng: **9 `char`**.

Lời gọi **không tự thêm** ký tự dòng mới; nó ghi chính xác chuỗi ký tự do Reader cung cấp.

`StringWriter` tích lũy toàn bộ kết quả trong bộ nhớ, phù hợp test và dữ liệu nhỏ. Khi đọc file lớn, nếu không cần tạo `String` chứa toàn bộ nội dung, nên ghi trực tiếp qua Writer hướng tới file thay vì đưa tất cả vào `StringWriter`.

## 6. Chuyển từ vị trí hiện tại; sau thành công Reader ở EOF

Reader có trạng thái vị trí đọc. Nếu đã đọc một phần:

```java
var reader = new java.io.StringReader("abcdef");
int first = reader.read(); // 'a'

var target = new java.io.StringWriter();
long copied = reader.transferTo(target);

System.out.println((char) first); // a
System.out.println(copied);       // 5
System.out.println(target);       // bcdef
```

`transferTo` không quay về đầu và **không chuyển lại `a`**.

Khi nguồn đã hết:

```java
var reader = new java.io.StringReader("OK");

long firstTime = reader.transferTo(new java.io.StringWriter());
long secondTime = reader.transferTo(new java.io.StringWriter());

System.out.println(firstTime);  // 2
System.out.println(secondTime); // 0
```

Lần hai trả 0 vì reader đang ở EOF; không phải một ngoại lệ. Nếu cần sao chép lại toàn bộ, tạo Reader mới hoặc dùng `reset()` **chỉ khi nguồn hỗ trợ và đã được mark hợp lệ theo hợp đồng**. Không giả định mọi `Reader` đều có thể seek.

### Nguồn rỗng

```java
var reader = new java.io.StringReader("");
var output = new java.io.StringWriter();

System.out.println(reader.transferTo(output)); // 0
System.out.println(output.toString().isEmpty()); // true
```

Không có ký tự nào được chuyển: 0 là kết quả hợp lệ.

## 7. Writer có sẵn nội dung: trả về chỉ tính phần chuyển mới

```java
var writer = new java.io.StringWriter();
writer.write("prefix:");

long copied = new java.io.StringReader("OK").transferTo(writer);

System.out.println(copied);            // 2
System.out.println(writer.toString()); // prefix:OK
```

Với `StringWriter`, phần mới được nối vào dữ liệu đã tích lũy. `copied` chỉ tính `"OK"`, không cộng số ký tự của `prefix:`.

**Không suy rộng** hành vi nối dữ liệu của `StringWriter` sang Writer của mọi file. Writer có thể được mở với chế độ tạo mới, ghi đè hoặc append; cách mở file đích mới quyết định việc ghi tiếp hay ghi thay, không phải `transferTo`.

## 8. Số ký tự trả về khác số Unicode code point và số byte

Xét chuỗi chứa emoji:

```java
var text = "A🙂B";
System.out.println(text.length()); // 4
System.out.println(
        text.codePointCount(0, text.length())); // 3

var writer = new java.io.StringWriter();
long copied = new java.io.StringReader(text).transferTo(writer);

System.out.println(copied); // 4
System.out.println(
        text.getBytes(java.nio.charset.StandardCharsets.UTF_8).length); // 6
```

Số liệu:

| Thành phần | `char` UTF-16 | Unicode code point | Byte UTF-8 |
| --- | ---: | ---: | ---: |
| `A` | 1 | 1 | 1 |
| `🙂` | 2 | 1 | 4 |
| `B` | 1 | 1 | 1 |
| **Tổng** | **4** | **3** | **6** |

Một emoji ngoài BMP dùng **cặp surrogate** gồm 2 đơn vị `char`, nhưng chỉ là 1 Unicode code point. Vì vậy `Reader.transferTo` trả **4**, khác số code point **3** và kích thước UTF-8 **6** byte.

### Với chữ tiếng Việt

Ký tự có dấu có thể là code point dựng sẵn hoặc một chuỗi code point gồm ký tự cơ sở và dấu kết hợp. Reader chuyển các `char` đã đọc; **không tự Unicode normalization**. Vì thế không được lấy giá trị trả về làm số “chữ nhìn thấy” theo trực giác người đọc.

**Nhớ rằng:** giá trị `long` được trả từ `Reader.transferTo` là số `char` đã chuyển, không dùng trực tiếp để dự đoán kích thước file trên đĩa.

## 9. Bảo toàn chuỗi ký tự xuống dòng

`transferTo` chép chuỗi ký tự mà Reader cung cấp, gồm các ký tự `\r` và `\n`. Nó **không** chia chuỗi thành các dòng rồi tạo lại line endings.

```java
var text = "a\r\nb\nc";
var writer = new java.io.StringWriter();

long copied = new java.io.StringReader(text).transferTo(writer);
System.out.println(copied);                        // 6
System.out.println(text.equals(writer.toString())); // true
```

Các đơn vị `char` là `a`, `\r`, `\n`, `b`, `\n`, `c`.

Đừng dùng một vòng lặp `BufferedReader.readLine()` cộng `Writer.write(line)` nếu mục tiêu là giữ nguyên line endings, vì `readLine` loại ký tự kết thúc dòng. Nếu tự ghi `System.lineSeparator()`, bạn còn có thể thay CRLF gốc bằng một quy tắc khác.

Khi cần **biến đổi theo từng dòng**, `readLine` hoặc `lines` có thể đúng, nhưng phải xác định rõ chính sách xuống dòng, không gọi đó là sao chép ký tự nguyên trạng.

## 10. Chuyển nội dung file văn bản với charset tường minh

Ví dụ sao chép file UTF-8 bằng character streams:

```java
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path inputPath = Path.of("input.txt");
Path outputPath = Path.of("output.txt");

try (Reader reader = Files.newBufferedReader(
             inputPath, StandardCharsets.UTF_8);
     Writer writer = Files.newBufferedWriter(
             outputPath, StandardCharsets.UTF_8)) {

    long copied = reader.transferTo(writer);
    System.out.println("Chars copied: " + copied);
}
```

Đây là **đoạn minh họa** trong một phương thức xử lý hoặc ném `IOException`, yêu cầu file `input.txt` tồn tại và có quyền đọc. Khi không truyền open option, `Files.newBufferedWriter` sử dụng cách mở mặc định để tạo hoặc truncate file đích, không mặc định append.

### Tại sao phải biết charset?

Ở tầng file, dữ liệu là byte:

1. `newBufferedReader(inputPath, UTF_8)` **giải mã** byte UTF-8 thành ký tự.
2. `Reader.transferTo(Writer)` chuyển các ký tự.
3. `newBufferedWriter(outputPath, UTF_8)` **mã hóa** ký tự thành byte UTF-8.

Vì vậy `transferTo` làm việc ở tầng **văn bản**, không phải tầng byte. Nếu charset đọc sai, ký tự đã sai trước lúc transfer. Nếu ghi theo charset khác, byte trong file đích có thể khác dù ký tự logic giống nhau.

### Vì sao dùng `try-with-resources`?

- Đảm bảo Reader và Writer được đóng ở cuối khối theo `AutoCloseable`.
- Hỗ trợ cleanup khi xảy ra ngoại lệ.
- Writer có thể đang đệm dữ liệu; việc đóng hoàn tất vòng đời ghi theo hợp đồng Writer.
- Không phụ thuộc vào việc `transferTo` tự đóng tài nguyên.

Nếu Writer thuộc sở hữu của caller khác (ví dụ Writer được truyền từ framework), không tự đóng nó nếu hợp đồng ownership không cho phép. Quản lý tài nguyên phải dựa trên ai có trách nhiệm tạo/đóng.

## 11. Close và flush: hai trách nhiệm `transferTo` không đảm nhận

Javadoc của `Reader.transferTo` quy định: sau khi trả về bình thường, Reader ở EOF, nhưng **không đóng Reader hay Writer**.

```java
var reader = new java.io.StringReader("abc");
var writer = new java.io.StringWriter();

reader.transferTo(writer);

// Nếu chính mã này sở hữu hai tài nguyên:
reader.close();
writer.close();
```

Với file và các tài nguyên quan trọng khác, ưu tiên `try-with-resources` thay vì hai lời gọi `close` thủ công.

### Writer có được flush tự động không?

`transferTo` **không cam kết gọi `writer.flush()`**. Nếu Writer có buffer và chương trình cần dữ liệu được chuyển tiếp **khi Writer vẫn còn mở**, gọi `flush()` ở điểm thích hợp.

```java
try (var reader = new java.io.StringReader("Hello");
     var writer = new java.io.BufferedWriter(
             new java.io.OutputStreamWriter(
                 outputStream,
                 java.nio.charset.StandardCharsets.UTF_8))) {
    reader.transferTo(writer);
    writer.flush();
}
```

Đoạn trên minh họa một `outputStream` có sẵn. **Khi đóng Writer bọc một OutputStream, OutputStream bên dưới thường cũng bị đóng**; vì vậy chỉ dùng ví dụ này khi mã được phép sở hữu/đóng stream đó. `flush` không thay `close` về giải phóng tài nguyên, và `close` không thay kiểm soát tính hoàn tất/atomicity của một quy trình nghiệp vụ.

### Không có bảo đảm nguyên tử

Một Reader có thể đã đọc nhiều ký tự, Writer có thể đã ghi một phần, rồi lỗi I/O xuất hiện. Đừng hiểu `transferTo` là thao tác “tất cả hoặc không có gì”.

## 12. Ngoại lệ: null, I/O lỗi và phần ghi dở dang

### Writer `null`

```java
var reader = new java.io.StringReader("A");
// reader.transferTo(null); // Ném NullPointerException
```

Writer bắt buộc không null. Thực tế nên kiểm soát đầu vào trước thao tác thay vì dùng ngoại lệ như một nhánh logic thường xuyên.

### Lỗi đọc/ghi `IOException`

Nếu nguồn bị lỗi hoặc đích không thể ghi, `transferTo` có thể ném `IOException` **sau khi đã chuyển một phần dữ liệu**. Javadoc không bảo đảm Reader đã ở EOF hoặc Writer chưa chứa ký tự nào tại thời điểm lỗi.

Điều cần làm:

- Không báo sao chép hoàn thành nếu exception xảy ra.
- Đóng nhanh Reader/Writer; `try-with-resources` hỗ trợ điều này.
- Quyết định xử lý file đích có thể đã ghi một phần.
- Không tự gọi lại ngay trên Reader/Writer cũ nếu không có kế hoạch khôi phục; có nguy cơ lặp, thiếu hoặc hỏng dữ liệu.
- Nếu yêu cầu ghi kết quả nguyên vẹn, cân nhắc ghi vào file tạm, hoàn tất và kiểm tra trước khi chuyển sang file đích; việc move nguyên tử chỉ có nếu hệ thống file và option hỗ trợ.

```java
try (Reader reader = Files.newBufferedReader(
             inputPath, StandardCharsets.UTF_8);
     Writer writer = Files.newBufferedWriter(
             outputPath, StandardCharsets.UTF_8)) {

    long copied = reader.transferTo(writer);
    System.out.println("Copied " + copied + " characters");

} catch (IOException ex) {
    // Log và báo lỗi; không đánh dấu file đích là hoàn chỉnh.
    throw ex;
}
```

Đây là minh họa trong phương thức có `inputPath`, `outputPath`, import cần thiết và `throws IOException`. Không dùng ví dụ này làm bằng chứng rằng Writer chưa hề ghi dữ liệu khi lỗi xảy ra.

### Nguồn dài hoặc không kết thúc

`transferTo` cố đọc đến EOF và có thể block vì nguồn/đích chậm. Nếu nguồn dữ liệu không tin cậy hoặc yêu cầu quota, hãy giới hạn ký tự ở tầng Reader hoặc dùng vòng lặp có bộ đếm; API không có đối số dừng sau N ký tự.

## 13. So sánh với `InputStream.transferTo(OutputStream)`

Có hai phương thức cùng tên nhưng **không tương đương về đơn vị dữ liệu**:

| API | Được bổ sung | Chuyển gì? | Kết quả `long` |
| --- | --- | --- | --- |
| `Reader.transferTo(Writer)` | **Java 10** | Ký tự Java `char` | Số `char` đã chuyển |
| `InputStream.transferTo(OutputStream)` | **Java 9** | Byte | Số byte đã chuyển |

```java
String text = "A🙂B";
byte[] utf8 = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

var bytesIn = new java.io.ByteArrayInputStream(utf8);
var bytesOut = new java.io.ByteArrayOutputStream();

long bytes = bytesIn.transferTo(bytesOut);
System.out.println(bytes); // 6

var charsOut = new java.io.StringWriter();
long chars = new java.io.StringReader(text).transferTo(charsOut);
System.out.println(chars); // 4
```

Chọn theo yêu cầu:

- Sao chép văn bản, đổi charset, đã có Reader/Writer → **`Reader.transferTo`**.
- Giữ nguyên byte, đọc file nhị phân hoặc stream byte → **`InputStream.transferTo`**.
- Sao chép nguyên trạng một file → **`Files.copy`** có thể phù hợp hơn.
- Cần chuyển đổi từng dòng/chunk hoặc dừng sớm → xử lý chuyên biệt, không chỉ gọi `transferTo`.

Đừng dùng Reader/Writer để sao chép ảnh, tệp ZIP, PDF nhị phân hoặc dữ liệu byte tùy ý rồi cho rằng nội dung byte chắc chắn không đổi.

## 14. Hiệu năng, memory và phạm vi sử dụng

`Reader.transferTo` thuận tiện và rõ ràng nhưng không tự động tốt nhất cho mọi ứng dụng:

- Với Writer hướng thẳng tới file, có thể chuyển kiểu streaming mà không cần lưu toàn bộ output như một `String`.
- Với `StringWriter`, chính Writer **tích lũy toàn bộ output trong RAM**. Đừng dùng nó cho file lớn nếu không cần.
- Việc đọc/ghi có thể block; dữ liệu quá lớn hoặc nguồn không kết thúc cần cơ chế giới hạn nếu nghiệp vụ yêu cầu.
- API không công bố một kích thước buffer cố định để chương trình dựa vào.
- Khi sử dụng Reader/Writer đã buffered, chi phí thực tế phụ thuộc I/O, charset, buffer, filesystem và JVM.
- `transferTo` giảm mã lặp, nhưng không có cam kết luôn nhanh hơn mọi vòng lặp tự viết.
- Nếu cần báo tiến độ từng chunk hoặc kiểm tra nội dung trong lúc chuyển, vòng lặp có buffer riêng vẫn hợp lý.
- Nếu Writer có side effect như gửi dữ liệu qua mạng, vấn đề timeout, retry và partial delivery phải được giải quyết ở tầng ứng dụng.

Đặc biệt, Reader/Writer của file text **không tự giải quyết lỗi decoding/encoding theo mọi chính sách**. Nếu có ký tự không hợp lệ hoặc không biểu diễn được trong charset mục tiêu, hành vi còn phụ thuộc decoder/encoder và cấu hình cụ thể.

## 15. Ví dụ chạy độc lập Java 17+ (không cần file đầu vào)

Tạo tệp **`ReaderTransferToDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.StringReader;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class ReaderTransferToDemo {
    static final class ObservedReader extends StringReader {
        boolean closeCalled;

        ObservedReader(String text) {
            super(text);
        }

        @Override
        public void close() {
            closeCalled = true;
            super.close();
        }
    }

    static final class ObservedWriter extends StringWriter {
        boolean closeCalled;
        boolean flushCalled;

        @Override
        public void close() {
            closeCalled = true;
        }

        @Override
        public void flush() {
            flushCalled = true;
        }
    }

    static String visible(String text) {
        return text.replace("\r", "\\r").replace("\n", "\\n");
    }

    public static void main(String[] args) throws IOException {
        var reader = new StringReader("Xin\nJava!");
        var writer = new StringWriter();

        System.out.println("basicCount=" + reader.transferTo(writer));
        System.out.println("basicText=" + visible(writer.toString()));
        System.out.println("basicEOF=" + (reader.read() == -1));
        System.out.println("secondCount="
                + reader.transferTo(new StringWriter()));

        var partialReader = new StringReader("abcdef");
        System.out.println("firstChar=" + (char) partialReader.read());
        var partialWriter = new StringWriter();
        System.out.println("remainingCount="
                + partialReader.transferTo(partialWriter));
        System.out.println("remainingText=" + partialWriter);

        var prefixed = new StringWriter();
        prefixed.write("prefix:");
        System.out.println("prefixedCount="
                + new StringReader("OK").transferTo(prefixed));
        System.out.println("prefixedText=" + prefixed);

        var emptyTarget = new StringWriter();
        emptyTarget.write("keep");
        System.out.println("emptyCount="
                + new StringReader("").transferTo(emptyTarget));
        System.out.println("emptyText=" + emptyTarget);

        var emojiText = "A🙂B";
        var emojiTarget = new StringWriter();
        long emojiCopied = new StringReader(emojiText)
                .transferTo(emojiTarget);
        System.out.println("unicodeChars=" + emojiText.length());
        System.out.println("unicodeCodePoints="
                + emojiText.codePointCount(0, emojiText.length()));
        System.out.println("unicodeUtf8Bytes="
                + emojiText.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("unicodeCopied=" + emojiCopied);
        System.out.println("unicodeSame="
                + emojiText.equals(emojiTarget.toString()));

        var lineEndings = "a\r\nb\nc";
        var lineTarget = new StringWriter();
        System.out.println("lineEndingsCount="
                + new StringReader(lineEndings).transferTo(lineTarget));
        System.out.println("lineEndingsSame="
                + lineEndings.equals(lineTarget.toString()));

        try (var buffered = new BufferedReader(
                    new StringReader("line1\nline2"));
             var bufferedWriter = new StringWriter()) {
            System.out.println("bufferedCount="
                    + buffered.transferTo(bufferedWriter));
            System.out.println("bufferedText="
                    + visible(bufferedWriter.toString()));
        }

        var observedReader = new ObservedReader("hi");
        var observedWriter = new ObservedWriter();
        System.out.println("trackedCount="
                + observedReader.transferTo(observedWriter));
        System.out.println("readerStillOpen="
                + !observedReader.closeCalled);
        System.out.println("writerStillOpen="
                + !observedWriter.closeCalled);
        System.out.println("writerNotFlushed="
                + !observedWriter.flushCalled);
        observedReader.close();
        observedWriter.close();
        System.out.println("callerClosedBoth="
                + (observedReader.closeCalled
                        && observedWriter.closeCalled));

        try {
            new StringReader("x").transferTo(null);
        } catch (NullPointerException expected) {
            System.out.println("nullRejected=true");
        }

        byte[] sourceBytes = emojiText.getBytes(StandardCharsets.UTF_8);
        try (var in = new ByteArrayInputStream(sourceBytes);
             var out = new ByteArrayOutputStream()) {
            long bytesCopied = in.transferTo(out);
            System.out.println("bytesCopied=" + bytesCopied);
            System.out.println("bytesSame="
                    + Arrays.equals(sourceBytes, out.toByteArray()));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 ReaderTransferToDemo.java
java ReaderTransferToDemo
```

**Stdout chính xác:**

```text
basicCount=9
basicText=Xin\nJava!
basicEOF=true
secondCount=0
firstChar=a
remainingCount=5
remainingText=bcdef
prefixedCount=2
prefixedText=prefix:OK
emptyCount=0
emptyText=keep
unicodeChars=4
unicodeCodePoints=3
unicodeUtf8Bytes=6
unicodeCopied=4
unicodeSame=true
lineEndingsCount=6
lineEndingsSame=true
bufferedCount=11
bufferedText=line1\nline2
trackedCount=2
readerStillOpen=true
writerStillOpen=true
writerNotFlushed=true
callerClosedBoth=true
nullRejected=true
bytesCopied=6
bytesSame=true
```

### Giải thích những nhóm cần quan sát

1. Chuỗi cơ bản có 9 đơn vị `char`; Reader được dùng lại sau EOF cho kết quả 0.
2. Đã đọc `a` trước thì chỉ chuyển 5 ký tự `bcdef`.
3. Với `StringWriter` có sẵn `prefix:`, kết quả được nối thêm; return 2 chỉ tính `OK`.
4. Chuỗi `A🙂B` có 4 `char`, 3 code point và 6 byte UTF-8.
5. Đầu vào chứa `\r\n` và `\n` giữ nguyên chuỗi ký tự; `BufferedReader` cũng có thể dùng `transferTo`.
6. Lời gọi `transferTo` trên các class theo dõi không tự gọi `close` hoặc `flush`. Caller đóng cả hai tài nguyên sau đó.
7. Writer `null` bị từ chối với `NullPointerException`.
8. `InputStream.transferTo` cho byte count bằng 6, khác char count bằng 4.

Không có phụ thuộc vào đường dẫn file, charset mặc định, thứ tự Set/Map hay lịch chạy song song. Chương trình dùng emoji literal trong mã nguồn và biên dịch với `-encoding UTF-8`.

## 16. Các lỗi hay gặp và cách sửa

### Lỗi A: Nhầm chiều gọi

```java
// writer.transferTo(reader); // Writer không có API này
reader.transferTo(writer); // Đúng
```

### Lỗi B: Đo dung lượng byte bằng số `char` trả về

```java
var text = "A🙂B";
long chars = new StringReader(text).transferTo(new StringWriter()); // 4
int bytes = text.getBytes(StandardCharsets.UTF_8).length;         // 6
```

Nếu cần dung lượng byte, đo ở tầng byte sau encoding thích hợp.

### Lỗi C: Không biết Reader đã bị tiêu thụ

```java
var reader = new StringReader("ABC");
reader.read();
// transferTo giờ chỉ chuyển "BC"
```

Tạo Reader mới hoặc reset có kiểm soát khi nguồn hỗ trợ.

### Lỗi D: Mong lần chuyển thứ hai sao chép lại

Sau thành công ở EOF, không còn dữ liệu mới để chuyển; `transferTo` không tự quay đầu.

### Lỗi E: Quên đóng tài nguyên

`transferTo` không đóng Reader/Writer; hãy dùng `try-with-resources` theo hợp đồng ownership.

### Lỗi F: Quên flush khi cần

Writer có buffering có thể chưa chuyển toàn bộ dữ liệu đến đích. `transferTo` không cam kết tự flush; gọi `flush` khi cần dữ liệu trước khi Writer được đóng.

### Lỗi G: Dùng `readLine` rồi mong bảo toàn line endings

`readLine` không giữ dấu xuống dòng, vì thế chuỗi tái tạo có thể khác đầu vào; `transferTo` giữ ký tự như Reader cung cấp.

### Lỗi H: Dùng Reader/Writer cho file nhị phân

Giải mã byte sang ký tự rồi mã hóa lại không bảo đảm giữ nguyên byte; dùng `Files.copy` hoặc `InputStream.transferTo`.

### Lỗi I: Dùng charset mặc định không đúng

Nếu file UTF-8 mà reader giải mã sai charset, nội dung đã hỏng trước khi transfer. Dùng charset đã biết, ví dụ `StandardCharsets.UTF_8`.

### Lỗi J: Tin rằng `IOException` nghĩa là chưa ghi gì

Một phần ký tự có thể đã được ghi trước lỗi. Phải xác định chính sách phục hồi và cleanup, không báo thành công từ file đích dở dang.

### Lỗi K: Không giới hạn nguồn dài hoặc không tin cậy

`transferTo` chuyển đến EOF và có thể block. Nếu cần quota hoặc hủy, dùng Reader giới hạn hoặc vòng lặp có kiểm soát.

## 17. Checklist thực hành

Trước khi gọi `reader.transferTo(writer)`:

1. Nguồn có thật sự là **văn bản** không?
2. Reader đang ở đầu hay đã đọc/skip một phần?
3. Bạn muốn chuyển **toàn bộ phần còn lại** hay chỉ N ký tự?
4. Writer được tạo với chế độ mở file nào?
5. Input/Output có được cấu hình đúng charset không?
6. Cần biết số byte, số Unicode code point hay số `char`?
7. Nguồn có Unicode supplementary character hoặc dấu kết hợp không?
8. Có phải giữ nguyên `\r\n` và `\n` không?
9. Ai có quyền đóng Reader và Writer?
10. Có sử dụng `try-with-resources` khi sở hữu tài nguyên không?
11. Có cần flush trong khi Writer còn mở không?
12. Nếu lỗi một phần, có xóa file tạm hoặc đánh dấu lỗi phù hợp không?
13. Nguồn có kích thước quá lớn hoặc chưa biết khi nào EOF không?
14. Có nhu cầu chuyển đổi nội dung/giới hạn dung lượng không?
15. Test đã kiểm Reader rỗng, đã đọc một phần, UTF-16 và Writer null chưa?

## 18. Luyện tập và đáp án

**Câu 1.** `new StringReader("Java").transferTo(writer)` trả về bao nhiêu?

**Câu 2.** `var r = new StringReader("ABCDE"); r.read(); r.read();` rồi `r.transferTo(writer)` còn chuyển bao nhiêu ký tự?

**Câu 3.** Sau khi `transferTo` hoàn tất bình thường, Reader đang ở đâu? Reader/Writer có được đóng tự động không?

**Câu 4.** `"A🙂B"` có bao nhiêu `char`, code point và byte UTF-8? Giá trị return của `Reader.transferTo` là gì?

**Câu 5.** `StringWriter` có sẵn `prefix:`; transfer từ chuỗi `OK` thì Writer có gì và return bao nhiêu?

**Câu 6.** Nếu Reader đã rỗng, `transferTo` trả 0 hay ném lỗi?

**Câu 7.** Tại sao không chọn Reader/Writer để chép ảnh hoặc ZIP nguyên byte?

**Câu 8.** Sự khác biệt giữa `Reader.transferTo` và `InputStream.transferTo` là gì?

**Câu 9.** Nếu Writer được giữ mở sau transfer, lúc nào cần quan tâm `flush()`?

**Câu 10.** Tại sao `BufferedReader.readLine()` rồi ghi lại có thể không giữ nguyên ký tự xuống dòng?

**Câu 11.** `IOException` có đồng nghĩa chưa có ký tự nào được ghi không?

**Câu 12.** Nếu chỉ muốn chuyển 100 ký tự đầu, dùng trực tiếp `transferTo` từ Reader nguồn đầy đủ có đúng mục tiêu không?

**Đáp án:**

1. `4` đơn vị `char`.
2. `3`, chỉ còn `CDE`.
3. Ở EOF; `transferTo` không tự đóng hai tài nguyên.
4. 4 `char`, 3 code point, 6 byte UTF-8; return 4.
5. `prefix:OK`, return 2.
6. Trả 0, nguồn rỗng là trường hợp bình thường.
7. Reader/Writer giải mã và mã hóa text, có thể thay đổi byte; dùng API byte hoặc `Files.copy`.
8. Reader/Writer chuyển ký tự từ Java 10, InputStream/OutputStream chuyển byte từ Java 9.
9. Khi cần Writer đưa dữ liệu đệm tới đích trước lúc đóng, theo hợp đồng Writer cụ thể.
10. `readLine` bỏ dấu xuống dòng và tự tái tạo có thể thay CRLF gốc.
11. Không. Lỗi có thể xuất hiện sau partial transfer.
12. Không. `transferTo` lấy hết phần còn lại; cần giới hạn nguồn hoặc vòng đọc có quota.

## 19. Tóm tắt và nguồn chính thức còn hiệu lực

- `Reader.transferTo(Writer)` có từ **Java 10**, tiếp tục là API chuẩn của `java.io.Reader`.
- Đọc đến EOF từ vị trí Reader hiện tại, ghi các ký tự theo thứ tự đọc, trả về số **đơn vị `char` dưới dạng `long`**.
- Không tự reset Reader, đóng Reader/Writer, chuẩn hóa ký tự hay chuyển đổi line endings.
- Không cam kết flush Writer, không đảm bảo ghi nguyên tử khi gặp lỗi.
- `IOException` có thể xuất hiện sau partial output; phải có chính sách cleanup.
- `Reader.transferTo` khác `InputStream.transferTo` ở đơn vị ký tự so với byte.
- Chọn Reader/Writer có charset rõ khi làm việc với file văn bản; dùng `try-with-resources` theo quyền sở hữu tài nguyên.
- Dùng vòng lặp có buffer khi cần quota, tiến độ hoặc xử lý ký tự từng khối.

Nguồn Java chính thức:

1. [Java SE 26 — `java.io.Reader.transferTo(Writer)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Reader.html#transferTo(java.io.Writer)): hợp đồng đọc đến EOF, không tự đóng, số ký tự, null và IOException.
2. [Java SE 26 — `java.io.Writer`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Writer.html): `write`, `flush` và `close`.
3. [Java SE 26 — `InputStream.transferTo(OutputStream)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStream.html#transferTo(java.io.OutputStream)): API chuyển byte.
4. [Java SE 26 — `Files.newBufferedReader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#newBufferedReader(java.nio.file.Path,java.nio.charset.Charset)) và [`Files.newBufferedWriter`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#newBufferedWriter(java.nio.file.Path,java.nio.charset.Charset,java.nio.file.OpenOption...)): API file text kèm charset.
5. [Java SE 26 — `StandardCharsets.UTF_8`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html#UTF_8): charset UTF-8 chuẩn.
