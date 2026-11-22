# `PrintWriter` nhận `Charset` khi ghi ra luồng hoặc tệp trong Java

## Mục tiêu bài học

Từ **Java 10**, `java.io.PrintWriter` có thêm các constructor nhận trực tiếp một đối tượng `java.nio.charset.Charset` khi ghi ra `OutputStream`, tệp `File` hoặc tên tệp dạng `String`. Đây là các API vẫn còn được hỗ trợ trong Java hiện đại. Chúng giúp bạn **chỉ định bộ mã hóa ký tự một cách tường minh**, thay vì để định dạng dữ liệu đầu ra phụ thuộc vào charset mặc định của môi trường.

Bài học tập trung vào cách `PrintWriter` chuyển **ký tự** Java thành **byte** khi đích là luồng/tệp, các constructor của Java 10 và những đặc điểm cần biết để ghi văn bản tiếng Việt an toàn.

Sau bài này, bạn sẽ:

- Đọc đúng ba constructor nhận `Charset` của `PrintWriter` và lựa chọn theo loại đích.
- Dùng `StandardCharsets.UTF_8` thay vì dựa vào charset mặc định khi định dạng tệp/giao thức đòi hỏi UTF-8.
- Hiểu quan hệ giữa `print`, `println`, `printf`, `autoFlush`, `flush`, `close` và byte thực sự được gửi đi.
- Phân biệt lỗi mở tệp có thể ném `IOException` với lỗi I/O khi in thường được ghi nhận qua `checkError()`.
- Biết `PrintWriter` **thay thế ký tự không biểu diễn được** trong charset đã chọn, chứ không mặc nhiên báo lỗi.
- Viết chương trình Java 17+ kiểm tra byte UTF-8, độ an toàn của việc đọc lại, ghi đè tệp và hành vi flush.

## 1. Charset là gì khi ghi bằng `PrintWriter`?

Trong Java, `String` lưu dữ liệu dạng ký tự (về mặt API chuỗi dùng các đơn vị UTF-16). Còn `OutputStream` và tệp nhị phân thực chất nhận **byte**. Khi ghi văn bản qua một `PrintWriter` được tạo từ `OutputStream` hoặc tệp, cần **mã hóa ký tự thành byte** theo một `Charset` cụ thể.

Ví dụ:

~~~java
String text = "Xin chào";
Charset charset = StandardCharsets.UTF_8;
~~~

Nếu chọn UTF-8, ký tự tiếng Việt như `à` có thể được mã hóa thành nhiều byte. Điều này dẫn đến:

- Số lượng `char` của chuỗi **không nhất thiết bằng** kích thước byte sau khi mã hóa.
- Đọc lại bằng charset **khác** có thể gây sai chữ (*mojibake*).
- Nội dung muốn dùng cho một định dạng hoặc một giao thức cần ghi/đọc thống nhất theo charset mà định dạng/giao thức đó quy định.

Java cung cấp các hằng `StandardCharsets.UTF_8`, `StandardCharsets.US_ASCII`, `StandardCharsets.ISO_8859_1`, `StandardCharsets.UTF_16` và các biến thể UTF-16. Dùng hằng đã được chuẩn hóa giúp code dễ đọc và không phải tra tên mã hóa bằng chuỗi.

**Vì sao vẫn chỉ định UTF-8 tường minh?** Trong JDK 17 trở về trước, charset mặc định thường phụ thuộc môi trường. Từ **JDK 18, JEP 400** đưa UTF-8 thành mặc định cho các API chuẩn, trừ những cấu hình tương thích/ngoại lệ được quy định. Tuy nhiên, charset **của định dạng dữ liệu** vẫn nên được chỉ rõ khi đó là một phần hợp đồng của tệp hoặc giao tiếp hệ thống. Đừng dùng “máy tôi mặc định UTF-8” để thay cho đặc tả dữ liệu.

## 2. Ba constructor `PrintWriter` nhận `Charset` từ Java 10

Bảng dưới đây mô tả chính xác các constructor thêm từ Java 10:

| Đích ghi | Constructor | `autoFlush` | Ngoại lệ đáng chú ý |
| --- | --- | --- | --- |
| Một `OutputStream` đã mở | `PrintWriter(OutputStream out, boolean autoFlush, Charset charset)` | Bạn chỉ định `true` hoặc `false` | Không khai báo checked `IOException` khi tạo từ luồng; kiểm tra lỗi ghi bằng `checkError()` |
| Đối tượng tệp | `PrintWriter(File file, Charset charset)` | Mặc định **`false`** | Khai báo `throws IOException` khi mở hoặc tạo tệp |
| Đường dẫn tệp dạng chuỗi | `PrintWriter(String fileName, Charset charset)` | Mặc định **`false`** | Khai báo `throws IOException` khi mở hoặc tạo tệp |

Ví dụ ba cách gọi:

~~~java
import java.io.*;
import java.nio.charset.StandardCharsets;

var stream = new ByteArrayOutputStream();

// OutputStream: bắt buộc truyền cả cờ autoFlush và Charset.
try (var out = new PrintWriter(stream, true, StandardCharsets.UTF_8)) {
    out.println("Xin chào");
}

// File: có thể chỉ định Charset trực tiếp.
try (var out = new PrintWriter(new File("report.txt"),
                               StandardCharsets.UTF_8)) {
    out.println("Xin chào");
}

// String fileName: tương tự, nhưng nhận chuỗi đường dẫn.
try (var out = new PrintWriter("report.txt", StandardCharsets.UTF_8)) {
    out.println("Xin chào");
}
~~~

Các lệnh ghi vào `report.txt` ở trên là **các cách sử dụng minh họa riêng biệt**. Nếu chạy nối tiếp như đoạn mẫu, constructor thứ hai ghi lại cùng tệp mà constructor trước đã tạo. **Các constructor nhận `File` hoặc `String fileName` tạo tệp nếu chưa có và cắt tệp hiện có về độ dài 0 khi mở thành công**. Chúng không mặc định mở ở chế độ append.

Đối với `OutputStream`, Java 10 **không có** constructor `PrintWriter(OutputStream, Charset)` chỉ gồm hai tham số. Hãy dùng đủ ba tham số:

~~~java
var out = new PrintWriter(outputStream, false, StandardCharsets.UTF_8);
~~~

Nếu đã có sẵn một `Writer` được cấu hình charset, dùng `PrintWriter(Writer)` hoặc `PrintWriter(Writer, boolean)`; charset thuộc trách nhiệm của `Writer` nền:

~~~java
Writer encoded = new OutputStreamWriter(outputStream, StandardCharsets.UTF_8);
PrintWriter out = new PrintWriter(encoded, true);
~~~

Điều này không phải constructor `PrintWriter(Writer, Charset)`: constructor như vậy **không tồn tại** trong API chuẩn. Tránh nhầm kiểu `OutputStream` (byte) với kiểu `Writer` (ký tự).

## 3. Ghi vào `OutputStream` với UTF-8

`ByteArrayOutputStream` là công cụ tốt để kiểm tra byte mà không ghi tệp thật:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;

var bytes = new ByteArrayOutputStream();

try (var writer = new PrintWriter(
        bytes, false, StandardCharsets.UTF_8)) {
    writer.print("Xin chào");
    writer.flush();
    if (writer.checkError()) {
        throw new IllegalStateException("Không ghi được nội dung");
    }
}

String decoded = bytes.toString(StandardCharsets.UTF_8);
System.out.println(decoded); // Xin chào
~~~

`PrintWriter` chuyển ký tự sang UTF-8 trước khi ghi xuống `bytes`. `ByteArrayOutputStream.toString(Charset)` giải mã ngược những byte đó, nên đầu ra trùng với dữ liệu ban đầu nếu quá trình ghi và giải mã đều thành công.

**Điều đáng nhớ:**

- `print` ghi biểu diễn dạng văn bản, không phải phương thức ghi byte thô.
- `Charset` được áp dụng khi PrintWriter tạo tầng `OutputStreamWriter` để mã hóa văn bản xuống luồng byte.
- Dùng cùng charset ở đầu đọc và đầu ghi khi định dạng yêu cầu điều đó.
- Đóng `PrintWriter` từ try-with-resources có thể **đóng luôn `OutputStream` nền**. Chỉ tạo wrapper sở hữu stream nếu ứng dụng chấp nhận vòng đời đó. Đặc biệt không tự ý bọc `System.out` rồi đóng nó khi đầu ra chuẩn còn được dùng ở nơi khác.

Trong trường hợp giao thức hoặc định dạng cần giữ luồng còn mở sau khi ghi, hãy thiết kế quyền sở hữu tài nguyên rõ ràng và quyết định lúc nào `flush` thay vì mặc định đóng wrapper ở giữa phiên làm việc.

## 4. Ghi tệp bằng `File` hoặc tên tệp

Khi dùng:

~~~java
try (var writer = new PrintWriter(
        new File("data.txt"), StandardCharsets.UTF_8)) {
    writer.println("Xin chào");
}
~~~

constructor sẽ mở hoặc tạo tệp, thiết lập mã hóa đã chỉ định và không bật `autoFlush`. `try-with-resources` gọi `close()` khi kết thúc khối, giúp đẩy phần dữ liệu đang đệm xuống đích và giải phóng tài nguyên.

Với tên tệp dạng chuỗi:

~~~java
try (var writer = new PrintWriter(
        "data.txt", StandardCharsets.UTF_8)) {
    writer.println("Xin chào");
}
~~~

Hai dạng dùng cùng chính sách charset và **đều có thể cắt nội dung tệp cũ** khi mở. Hãy đặc biệt cẩn thận khi tệp chứa dữ liệu quan trọng.

Nếu cần **ghi nối tiếp (append)** thay vì ghi đè, bạn có thể chủ động mở `FileOutputStream` với `append=true`, rồi đưa vào constructor `OutputStream` của Java 10:

~~~java
try (var raw = new FileOutputStream("data.txt", true);
     var writer = new PrintWriter(
             raw, false, StandardCharsets.UTF_8)) {
    writer.println("Một dòng mới");
    if (writer.checkError()) {
        throw new IOException("Không ghi được tệp");
    }
}
~~~

Ví dụ này minh họa cách quyết định append. Không có tham số `append` trong hai constructor `PrintWriter(File, Charset)` và `PrintWriter(String, Charset)`.

Một lựa chọn hiện hành khác là `Files.newBufferedWriter(path, charset, openOptions...)` khi cần xử lý lỗi I/O bằng ngoại lệ checked hoặc cần điều khiển chế độ mở tệp chi tiết hơn. Không cần ép mọi bài toán ghi văn bản qua `PrintWriter`.

## 5. Tự động flush: `println` khác `print("\n")`

Với constructor `PrintWriter(OutputStream, boolean autoFlush, Charset)`, cờ `autoFlush` được xác định khi tạo đối tượng:

~~~java
var bytes = new ByteArrayOutputStream();

try (var writer = new PrintWriter(
        bytes, true, StandardCharsets.UTF_8)) {
    writer.print("A\n"); // Chỉ in các ký tự; không kích hoạt autoFlush.
    // Tại thời điểm này, nội dung vẫn có thể nằm trong buffer.

    writer.println("B"); // Kích hoạt autoFlush.
}
~~~

Theo hợp đồng của `PrintWriter`, khi `autoFlush=true`, việc tự flush được kích hoạt bởi các lời gọi **`println`**, **`printf`** hoặc **`format`**; không phải chỉ vì chuỗi dữ liệu có ký tự `\n`.

| Lời gọi | Kích hoạt autoFlush khi cờ bật? | Ghi chú |
| --- | --- | --- |
| `print("A")` | Không | Không thêm dấu xuống dòng |
| `print("A\n")` | Không | Ký tự xuống dòng nằm trong chuỗi, không phải lệnh `println` |
| `write('\\n')` | Không | Ghi một ký tự, không tự kích hoạt autoFlush |
| `println("A")` | Có | Ghi thêm dấu kết thúc dòng theo nền tảng |
| `printf(...)` | Có | Định dạng văn bản, autoFlush khi bật |
| `format(...)` | Có | Tương tự `printf` |
| `flush()` | Có, theo yêu cầu tường minh | Không phụ thuộc cờ `autoFlush` |

Lưu ý `println` dùng ký tự kết thúc dòng **theo nền tảng**; vì vậy số byte viết ra khi kết thúc một dòng có thể khác giữa Windows và Linux/macOS. Khi cần định dạng có newline chính xác như `\n`, hãy chỉ rõ dấu phân cách của giao thức và gọi `flush()` khi cần dữ liệu được chuyển xuống luồng ngay.

**`autoFlush=false` không có nghĩa PrintWriter không bao giờ ghi:** nó chỉ không tự flush theo ba phương thức trên. Nội dung vẫn có thể được gửi khi bộ đệm đầy, khi gọi `flush()` hoặc khi đóng. Trong bài kiểm tra cụ thể với `ByteArrayOutputStream` nhỏ, `print` chưa flush ngay; đừng tổng quát thành một bảo đảm rằng mọi `print` luôn giữ nguyên toàn bộ byte trong buffer.

## 6. `checkError()`: lỗi I/O không được ném trực tiếp từ `print`

Đây là đặc điểm quan trọng và dễ gây sai sót của `PrintWriter`:

- **Constructor ghi tệp** như `new PrintWriter(file, charset)` hoặc `new PrintWriter(fileName, charset)` có thể ném `IOException` khi mở/tạo tệp.
- Khi đã tạo thành công, các phương thức in, ghi, flush/close của `PrintWriter` **không ném `IOException` trực tiếp** theo cùng cách `Writer` thông thường. Lỗi I/O được ghi nhận vào trạng thái lỗi nội bộ.
- Có thể gọi **`checkError()`** để kiểm tra. Khi stream chưa đóng, phương thức này còn cố flush trước khi kiểm tra trạng thái.

~~~java
writer.println("Nội dung");
if (writer.checkError()) {
    throw new IOException("Ghi dữ liệu thất bại");
}
~~~

Không nên cho rằng một lời gọi `println` không ném ngoại lệ đồng nghĩa dữ liệu đã được ghi thành công. Đặc biệt với ghi tệp quan trọng, cần quyết định cách kiểm tra lỗi và lúc nào xác nhận hoàn tất.

**Phân biệt loại lỗi:** `PrintWriter` chủ yếu hấp thụ **lỗi I/O**; các lỗi lập trình khác như dùng đối số sai cho bộ định dạng vẫn có thể ném những ngoại lệ không phải `IOException`. `checkError` cũng **không phải** là cơ chế xác nhận byte đã được đồng bộ bền vững xuống thiết bị lưu trữ; flush ở tầng Java không tương đương cam kết `fsync` hoặc một giao dịch ghi bền vững.

Nếu yêu cầu xử lý từng `IOException` bằng cơ chế checked exception và kiểm soát lỗi chặt, cân nhắc dùng `BufferedWriter` hoặc `OutputStreamWriter` trực tiếp.

## 7. Charset không biểu diễn được ký tự: `PrintWriter` thay thế

Chọn charset là chọn tập mã hóa có thể chuyển ký tự thành byte. Không phải charset nào cũng biểu diễn được mọi ký tự Unicode.

Ví dụ `US_ASCII` chỉ biểu diễn nhóm ký tự ASCII cơ bản. Chuỗi `"AéB"` chứa `é` nằm ngoài ASCII:

~~~java
var bytes = new ByteArrayOutputStream();

try (var writer = new PrintWriter(
        bytes, false, StandardCharsets.US_ASCII)) {
    writer.print("AéB");
    writer.flush();
}

String decoded = bytes.toString(StandardCharsets.US_ASCII);
// Theo chính sách thay thế của PrintWriter: "A?B".
~~~

Theo hợp đồng `PrintWriter`, những chuỗi ký tự không hợp lệ hoặc không thể mã hóa được **bị thay bằng chuỗi thay thế mặc định của charset**. Với `US_ASCII`, đó thường là dấu `?`, như ví dụ. **`checkError()==false` không chứng minh rằng toàn bộ ký tự gốc đều được bảo toàn**, bởi việc thay thế theo chính sách mã hóa không nhất thiết được xem là lỗi I/O.

Nếu ứng dụng cần **từ chối dữ liệu không mã hóa được** thay vì lặng lẽ thay thế, hãy sử dụng `CharsetEncoder` có `CodingErrorAction.REPORT` cùng một `Writer` phù hợp và quản lý `IOException`/`CharacterCodingException` theo hợp đồng. Đừng dựa vào `PrintWriter` như cơ chế kiểm tra không mất dữ liệu khi mã hóa.

Ví dụ cấu hình encoder nghiêm ngặt (minh họa):

~~~java
var encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Writer out = new OutputStreamWriter(outputStream, encoder)) {
    out.write("AéB"); // Không mã hóa được é: có thể ném
                        // UnmappableCharacterException khi flush/close.
}
~~~

Ở đoạn minh họa, `outputStream` là một `OutputStream` do chương trình cung cấp. Dùng `Writer` trực tiếp giúp lỗi mã hóa không bị che bởi hành vi ghi nhận lỗi của `PrintWriter`.

## 8. Chương trình Java 17+ hoàn chỉnh và đã kiểm chứng

Để tránh phụ thuộc khả năng hiển thị Unicode của terminal và có thể kiểm tra **byte thực tế**, chương trình bên dưới dùng chuỗi Java chứa các escape `\uXXXX` cho một số ký tự tiếng Việt. Khi chạy, các escape đó tương ứng với đúng ký tự Unicode.

Lưu mã sau vào tệp **PrintWriterCharsetDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class PrintWriterCharsetDemo {
    static final class FailingOutputStream extends OutputStream {
        @Override
        public void write(int value) throws IOException {
            throw new IOException("simulated");
        }
    }

    public static void main(String[] args) throws Exception {
        String message = "Ti\u1EBFng Vi\u1EC7t: c\u00E0 ph\u00EA";
        System.out.println("chars: " + message.length());

        var utf8Bytes = new ByteArrayOutputStream();

        // (1) Chỉ định UTF-8 cho một OutputStream.
        try (var writer = new PrintWriter(
                utf8Bytes, false, StandardCharsets.UTF_8)) {
            writer.print(message);
            writer.flush();

            System.out.println("utf8 bytes: " + utf8Bytes.size());
            System.out.println("utf8 roundtrip: "
                    + message.equals(utf8Bytes.toString(StandardCharsets.UTF_8)));
            System.out.println("utf8 error: " + writer.checkError());
        }

        // (2) Charset hẹp hơn sẽ thay thế ký tự không biểu diễn được.
        var asciiBytes = new ByteArrayOutputStream();
        try (var writer = new PrintWriter(
                asciiBytes, false, StandardCharsets.US_ASCII)) {
            writer.print("A\u00E9B");
            writer.flush();
        }
        System.out.println("ascii replaced: "
                + asciiBytes.toString(StandardCharsets.US_ASCII).equals("A?B"));

        // (3) autoFlush: print có ký tự newline không đồng nghĩa println.
        var sink = new ByteArrayOutputStream();
        try (var writer = new PrintWriter(
                sink, true, StandardCharsets.UTF_8)) {
            writer.print("A\n");
            System.out.println("print flushes automatically: " + (sink.size() > 0));

            writer.println("B");
            System.out.println("println flushes automatically: "
                    + sink.toString(StandardCharsets.UTF_8).contains("B"));
        }

        // (4) Hai constructor nhận Charset cho File và String fileName.
        Path file = Files.createTempFile("printwriter-charset-", ".txt");
        try {
            try (var writer = new PrintWriter(
                    file.toFile(), StandardCharsets.UTF_8)) {
                writer.print(message);
                if (writer.checkError()) {
                    throw new IOException("file write error");
                }
            }
            System.out.println("File overload roundtrip: "
                    + Files.readString(file, StandardCharsets.UTF_8).equals(message));

            try (var writer = new PrintWriter(
                    file.toString(), StandardCharsets.UTF_8)) {
                writer.print("updated");
                if (writer.checkError()) {
                    throw new IOException("file write error");
                }
            }
            System.out.println("String overload truncates: "
                    + Files.readString(file, StandardCharsets.UTF_8).equals("updated"));
        } finally {
            Files.deleteIfExists(file);
        }

        // (5) PrintWriter ghi nhận lỗi I/O bằng trạng thái lỗi.
        try (var writer = new PrintWriter(
                new FailingOutputStream(), true, StandardCharsets.UTF_8)) {
            writer.println("test");
            System.out.println("simulated error: " + writer.checkError());
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac PrintWriterCharsetDemo.java
java PrintWriterCharsetDemo
~~~

**Kết quả chính xác:**

~~~text
chars: 18
utf8 bytes: 24
utf8 roundtrip: true
utf8 error: false
ascii replaced: true
print flushes automatically: false
println flushes automatically: true
File overload roundtrip: true
String overload truncates: true
simulated error: true
~~~

### Phân tích từng dòng kết quả

1. `message.length() == 18` vì chuỗi có 18 đơn vị `char` trong Java.
2. Chuỗi này khi mã hóa UTF-8 chiếm **24 byte**, nhiều hơn số `char` do các chữ có dấu được biểu diễn bằng nhiều byte.
3. Đọc lại các byte bằng UTF-8 trả đúng chuỗi ban đầu, nên `utf8 roundtrip: true`. `checkError()` trả `false` trên luồng ghi vào bộ nhớ hoạt động bình thường.
4. `US_ASCII` không thể biểu diễn `é`, nên phiên bản đã ghi và giải mã không giữ nguyên ký tự đó. Ví dụ xác minh đúng kết quả thay thế `A?B`.
5. Với sink đệm nhỏ, `print("A\n")` chưa tự flush, còn `println("B")` kích hoạt autoFlush khi đã bật cờ. Dùng giá trị boolean thay vì so sánh chuỗi newline, vì ký tự kết thúc dòng phụ thuộc nền tảng.
6. Hai constructor ghi tệp nhận `Charset` đều ghi đúng UTF-8; mở lần thứ hai trên cùng tệp với `String fileName` đã **ghi đè** nội dung ban đầu. Tệp tạm được xóa trong `finally`.
7. `FailingOutputStream` cố ý ném `IOException` khi được ghi xuống. `PrintWriter.println` không ném checked `IOException` ra phía gọi; sau đó `checkError()` phản ánh lỗi bằng `true`.

Ví dụ không phụ thuộc một file có sẵn, tên thư mục cố định hay charset mặc định của máy. Chương trình chỉ in ASCII ở phần thông báo và dùng so sánh byte/chuỗi làm bằng chứng, nên kết quả in ra ổn định trên các hệ thống phù hợp.

## 9. Phân biệt với `Files.newBufferedWriter` và `OutputStreamWriter`

Các cách ghi văn bản đều còn hợp lệ, nhưng hợp đồng khác nhau:

| Nhu cầu | API nên cân nhắc | Đặc điểm |
| --- | --- | --- |
| In văn bản có `print`, `println`, `printf` trực tiếp xuống `OutputStream` với Charset | `new PrintWriter(stream, autoFlush, charset)` | Thuận tiện cho văn bản có định dạng; kiểm tra `checkError()` |
| Ghi ra `File` hoặc tên tệp với charset cố định | `new PrintWriter(file, charset)` / `new PrintWriter(fileName, charset)` | Tạo/ghi đè tệp; `autoFlush` mặc định false |
| Ghi văn bản với ngoại lệ I/O theo kiểu `Writer` | `Files.newBufferedWriter(path, charset, options...)` | Hỗ trợ lựa chọn chế độ mở, bao gồm append |
| Đã có `OutputStream` và cần `Writer` có kiểm soát mã hóa | `new OutputStreamWriter(stream, charset)` | Chuyển ký tự sang byte; có thể cấu hình encoder |
| Ghi chuỗi vào tệp với API gọn | `Files.writeString(path, text, charset)` | Hữu ích khi không cần các phương thức `print`/`printf` |

Ví dụ muốn ghi nối tiếp vào tệp và xử lý `IOException` thông thường:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path path = Path.of("app.log");
try (var writer = Files.newBufferedWriter(
        path,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND)) {
    writer.write("Một bản ghi mới");
    writer.newLine();
}
~~~

Đoạn này minh họa trong một phương thức có `throws IOException` hoặc bắt lỗi tương ứng. Đừng đưa `PrintWriter` vào mọi nơi chỉ vì nó có `println`; khi cần quản lý lỗi chính xác, `BufferedWriter` trực tiếp có thể rõ nghĩa hơn.

### `printf` còn có vấn đề `Locale`

Charset điều khiển **mã hóa ký tự thành byte**; `Locale` ảnh hưởng đến **cách định dạng** giá trị bằng `printf` và `format` (ví dụ dấu tách phần thập phân ở một số locale).

~~~java
writer.printf(java.util.Locale.ROOT, "%.2f", 12.5);
~~~

Khi xuất dữ liệu máy đọc theo định dạng cố định, hãy chỉ định **cả Charset lẫn Locale** nếu đặc tả đầu ra cần sự ổn định. Charset không tự quyết định định dạng ngày, số hoặc ngôn ngữ của nội dung.

## 10. Những sai lầm phổ biến

| Sai lầm | Vì sao không đúng | Cách xử lý |
| --- | --- | --- |
| `new PrintWriter(stream, StandardCharsets.UTF_8)` | Không có overload nhận đúng `OutputStream` và `Charset` gồm hai tham số | Truyền `autoFlush`: `new PrintWriter(stream, false, UTF_8)` |
| `new PrintWriter(writer, UTF_8)` | `Writer` đã biểu diễn luồng ký tự; không có constructor này | Tạo `OutputStreamWriter(stream, UTF_8)` trước rồi bọc |
| Cho rằng Java 10 tự luôn dùng UTF-8 | JDK 17 trở về trước mặc định có thể phụ thuộc môi trường; JDK 18+ đã thay đổi mặc định | Chọn Charset tường minh theo hợp đồng dữ liệu |
| Cho rằng `String.length()` bằng số byte tệp | UTF-8 có ký tự đa byte | Kiểm tra byte thực tế hoặc đọc lại đúng charset |
| Dùng `US_ASCII` để ghi tiếng Việt rồi mong giữ nguyên | Nhiều ký tự không biểu diễn được, bị thay thế | Dùng UTF-8 hoặc encoder nghiêm ngặt |
| Nghĩ `print("A\n")` tự flush khi cờ true | Chỉ `println`, `printf`, `format` kích hoạt autoFlush | Gọi `flush()` nếu cần |
| Nghĩ `println` luôn ghi byte `0A` | Line separator theo nền tảng | Viết dấu phân cách do giao thức quy định |
| Nghĩ `println` im lặng tức ghi thành công | PrintWriter ghi nhận lỗi I/O | Kiểm tra `checkError()` và xử lý lỗi |
| Nghĩ file constructor sẽ append | Constructor file mặc định tạo/ghi đè | Mở `FileOutputStream(file,true)` hoặc `Files.newBufferedWriter` với APPEND |
| Nghĩ đóng wrapper không ảnh hưởng stream nền | `close` có thể đóng cả OutputStream | Thiết kế ownership; tránh đóng `System.out` ngoài ý muốn |
| Nghĩ `checkError()` chứng minh dữ liệu bền vững trên đĩa | Nó kiểm tra trạng thái lỗi I/O, không cam kết fsync | Áp dụng cơ chế durability riêng nếu cần |
| Dùng charset ở lúc ghi nhưng quên lúc đọc | Byte có thể bị giải mã sai | Giữ cùng charset theo đặc tả ở cả hai đầu |

## 11. Bài tập tự kiểm tra

### Bài 1 — chọn constructor

Giả sử có `OutputStream socketOutput`, muốn ghi văn bản UTF-8 và tự flush khi gọi `println()`. Constructor nào đúng?

~~~java
// A. new PrintWriter(socketOutput, StandardCharsets.UTF_8)
// B. new PrintWriter(socketOutput, true, StandardCharsets.UTF_8)
// C. new PrintWriter(socketOutput, false, StandardCharsets.UTF_8)
~~~

**Đáp án:** B. A không có overload phù hợp; C dùng UTF-8 nhưng không tự flush theo `println` khi cờ `autoFlush` là false.

### Bài 2 — dữ liệu byte và `Charset`

~~~java
var raw = new ByteArrayOutputStream();
try (var out = new PrintWriter(raw, false, StandardCharsets.UTF_8)) {
    out.print("A\u00E9B");
    out.flush();
}

// raw.size() bằng bao nhiêu?
// Giải mã bằng UTF-8 có trả đúng AéB không?
~~~

**Đáp án:** `raw.size() == 4`. `A` và `B` mỗi ký tự một byte, `é` trong UTF-8 chiếm hai byte. Giải mã bằng `StandardCharsets.UTF_8` trả `"AéB"` đúng; không nên đoán dung lượng từ `String.length() == 3`.

### Bài 3 — khi nào cần `checkError`?

~~~java
var raw = new ByteArrayOutputStream();
try (var out = new PrintWriter(raw, false, StandardCharsets.UTF_8)) {
    out.println("hello");
    // Có thể kiểm tra ghi thành công bằng cách nào?
}
~~~

**Đáp án:** Gọi `out.checkError()` để kiểm tra trạng thái lỗi của PrintWriter (đồng thời flush nếu chưa đóng). Với luồng bộ nhớ bình thường, kỳ vọng `false`. Với một luồng tệp/mạng thực tế, cần thêm chiến lược xử lý lỗi và kiểm soát tài nguyên của đích. `checkError` không phải xác nhận dữ liệu đã được máy nhận hoặc ghi bền vững.

### Bài 4 — `File` và tên tệp

~~~java
try (var a = new PrintWriter(new File("result.txt"), UTF_8)) {
    a.print("A");
}
try (var b = new PrintWriter("result.txt", UTF_8)) {
    b.print("B");
}
~~~

**Đáp án:** Nếu cả hai lần mở/ghi đều thành công và không có yếu tố khác can thiệp, tệp cuối cùng chỉ chứa `B`, không phải `AB`. Constructor mở tệp ở chế độ ghi đè. Với `FileOutputStream("result.txt", true)` cùng constructor `PrintWriter(OutputStream, boolean, Charset)`, bạn mới yêu cầu chế độ nối tiếp.

### Bài 5 — so sánh với JDK mới

Từ JDK 18 mặc định của Java thường đã là UTF-8. Vậy có cần chỉ định `StandardCharsets.UTF_8` ở nơi tệp/giao thức yêu cầu UTF-8 không?

**Đáp án:** Vẫn nên chỉ định. Charset là một phần **hợp đồng của dữ liệu**, còn charset mặc định là thuộc tính môi trường/runtime, có thể bị cấu hình và có thể khác trên những môi trường/JDK mà ứng dụng cần tương thích.

## 12. Ghi nhớ và tài liệu chính thức

- Java 10 bổ sung ba constructor: **`PrintWriter(OutputStream, boolean, Charset)`**, **`PrintWriter(File, Charset)`** và **`PrintWriter(String, Charset)`**.
- Chọn **`StandardCharsets.UTF_8`** khi định dạng cần UTF-8. Đọc lại bằng cùng charset để tránh sai ký tự.
- Constructor nhận `File` hoặc tên tệp **có thể ghi đè tệp hiện có** và có thể ném `IOException` trong giai đoạn mở.
- `PrintWriter` thuận tiện cho `print/println/printf`, nhưng **không ném checked `IOException` từ hoạt động in thông thường**; dùng `checkError()`.
- `autoFlush` chỉ được kích hoạt bởi `println`, `printf` hoặc `format`, không phải bất kỳ `\n` nào trong chuỗi.
- Ký tự không biểu diễn được bằng charset đã chọn có thể bị thay thế. Nếu không chấp nhận mất dữ liệu, dùng `CharsetEncoder` nghiêm ngặt và một `Writer` quản lý lỗi thích hợp.
- `Charset` kiểm soát mã hóa thành byte; `Locale` kiểm soát một phần cách định dạng. Hai khái niệm khác nhau.
- Các constructor mới từ Java 10 **vẫn còn được hỗ trợ**; không cần thay chúng bằng API khác chỉ vì đã có `Files`.

Tài liệu tham khảo chính thức:

- [Java SE 17 — `PrintWriter` và các constructor nhận `Charset`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html)
- [Java SE 10 — `PrintWriter`, các constructor bổ sung từ Java 10](https://docs.oracle.com/javase/10/docs/api/java/io/PrintWriter.html)
- [Java SE 17 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Java SE 17 — `CharsetEncoder` và `CodingErrorAction`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html)
- [Java SE 17 — `Files.newBufferedWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [JEP 400 — UTF-8 by Default, JDK 18](https://openjdk.org/jeps/400)

**Kết luận:** Khi in văn bản từ Java ra luồng byte hoặc tệp, hãy chọn **charset theo định dạng dữ liệu**, không theo sự tình cờ của môi trường. Ba constructor `PrintWriter` bổ sung từ Java 10 giúp thực hiện điều đó rõ ràng; nhưng vẫn cần chú ý **ghi đè tệp, flush, vòng đời luồng, lỗi I/O và chính sách thay thế ký tự**.
