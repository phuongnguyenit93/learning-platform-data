# `PrintStream` khác `PrintWriter` trong Java I/O

## Mục tiêu

Java có hai lớp xuất dữ liệu quen thuộc hỗ trợ `print`, `println`, `printf` và `format`: `java.io.PrintStream` và `java.io.PrintWriter`. Cú pháp tương tự nhau nhưng chúng khác nhau về **loại đích nhận dữ liệu, byte và ký tự, charset, quy tắc auto-flush và cách báo lỗi I/O**.

Sau bài này, bạn sẽ:

- Phân biệt được `PrintStream extends FilterOutputStream` với `PrintWriter extends Writer` và lựa chọn theo kiểu đích.
- Hiểu vì sao `print("é")` khác `write(0xE9)` trên `PrintStream`.
- Chọn charset rõ ràng khi chuyển ký tự thành byte.
- Hiểu chính xác điều gì khiến mỗi lớp tự `flush()` khi bật `autoFlush`.
- Xử lý đúng những lỗi ghi mà `print` không ném `IOException` trực tiếp ra ngoài.
- Biết dùng các lớp này trong console, tệp, bộ nhớ và chương trình Java 17+.

## 1. Khác biệt cốt lõi ở hệ phân cấp

```text
Dữ liệu Java: int, double, String, Object
                     |
        print / println / printf / format
                     |
        +------------+-------------+
        |                          |
        v                          v
   PrintStream                PrintWriter
   (OutputStream)               (Writer)
        |                          |
        v                          +---> Writer đích:
  chuyển ký tự thành byte               StringWriter,
  theo charset đã chọn                  BufferedWriter,...
        |                          |
        v                          +---> hoặc OutputStream
    OutputStream                       qua tầng OutputStreamWriter
    (file/socket/memory)
```

`PrintStream` là một loại `OutputStream`: ngoài in biểu diễn văn bản, nó có phương thức ghi **byte thô**. `PrintWriter` là một loại `Writer`: các thao tác `write` của nó nhận **ký tự/chuỗi ký tự**, không có phương thức ghi `byte[]` thô. Tuy vậy, `PrintWriter` **vẫn có constructor nhận `OutputStream`**, khi đó nó đặt một tầng mã hóa ký tự thành byte ở phía dưới.

| Tiêu chí | `PrintStream` | `PrintWriter` |
| --- | --- | --- |
| Kế thừa | `FilterOutputStream` → `OutputStream` | `Writer` |
| Đích phù hợp trực tiếp | `OutputStream` | `Writer` hoặc `OutputStream` qua chuyển đổi |
| Ghi raw bytes | `write(int)`, `write(byte[], off, len)`, `writeBytes(byte[])` | Không có API `write(byte[])` |
| Ghi giá trị Java | `print`, `println`, `printf`, `format` | `print`, `println`, `printf`, `format` |
| Lỗi I/O trong thao tác in | Đánh dấu trạng thái lỗi; kiểm tra bằng `checkError()` | Cũng đánh dấu trạng thái lỗi; kiểm tra bằng `checkError()` |
| `autoFlush` | Gồm các trigger liên quan newline/ghi mảng byte và `println` | Chỉ khi `println`, `printf`, `format` |
| Ví dụ | `System.out`, `System.err` | Sinh báo cáo với `StringWriter`, `BufferedWriter` |

Cần hiểu chính xác câu “`PrintStream` làm việc với byte”: **không có nghĩa `PrintStream.print(String)` ghi thẳng từng Java `char` như byte**. Văn bản được mã hóa bằng charset rồi mới ghi tới `OutputStream`. Ngược lại, `PrintWriter` hướng đến ký tự nhưng vẫn có thể xuất ra tệp/socket thông qua một `OutputStreamWriter`.

## 2. Ví dụ Java 17+: cùng văn bản, hai loại đích

Chương trình dưới đây có kết quả xác định trên các hệ điều hành nhờ chuẩn hóa dấu xuống dòng để **hiển thị**, không thay đổi dữ liệu đã ghi.

Lưu thành **`PrintTargetsDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class PrintTargetsDemo {
    private static String display(String text) {
        return text.replace("\r\n", "\n")
                   .replace('\r', '\n')
                   .replace("\n", "|");
    }

    public static void main(String[] args) {
        ByteArrayOutputStream byteSink = new ByteArrayOutputStream();

        try (PrintStream ps =
                     new PrintStream(byteSink, true, StandardCharsets.UTF_8)) {
            ps.print("Count=");
            ps.println(7);
            ps.printf(Locale.ROOT, "Ratio=%.1f%n", 2.5);
        }

        StringWriter charSink = new StringWriter();
        try (PrintWriter pw = new PrintWriter(charSink, true)) {
            pw.print("Count=");
            pw.println(7);
            pw.printf(Locale.ROOT, "Ratio=%.1f%n", 2.5);
        }

        String textFromBytes =
                new String(byteSink.toByteArray(), StandardCharsets.UTF_8);
        System.out.println("PrintStream: " + display(textFromBytes));
        System.out.println("PrintWriter: " + display(charSink.toString()));
    }
}
```

Biên dịch và chạy:

```bash
javac PrintTargetsDemo.java
java PrintTargetsDemo
```

Kết quả:

```text
PrintStream: Count=7|Ratio=2.5|
PrintWriter: Count=7|Ratio=2.5|
```

Với `PrintStream`, kết quả được giữ trong `ByteArrayOutputStream` dưới dạng byte UTF-8; sau đó chương trình giải mã thành `String`. Với `PrintWriter`, `StringWriter` giữ trực tiếp ký tự. Cả hai in cùng nội dung; **sự khác nhau thể hiện ở giao diện, đích và quá trình mã hóa**, không phải hình thức `println`.

Lưu ý:

- `Locale.ROOT` giúp `%.1f` in `2.5` ổn định thay vì phụ thuộc locale hệ thống.
- `println` và `%n` sử dụng ký hiệu xuống dòng của nền tảng, vì thế đoạn mã hiển thị chuyển nó sang dấu `|`.
- `try-with-resources` gọi `close()` ở cuối phạm vi. Hai đích trong bộ nhớ vẫn cho phép lấy nội dung để minh họa sau đó; không suy diễn rằng có thể sử dụng mọi đích tệp/socket sau khi đóng.

## 3. Charset: một ký tự có thể tạo nhiều byte

Trong Java, `String`/`char` biểu diễn dữ liệu ký tự; `OutputStream` chứa byte. Với chữ `é`, mã hóa UTF-8 đúng là **hai byte `C3 A9`**.

- `PrintStream.print("é")` với UTF-8 ghi `C3 A9`.
- `PrintStream.write(0xE9)` ghi byte thô `E9`; byte đơn này **không phải** UTF-8 hợp lệ cho chữ `é`.
- `PrintWriter.print("é")` với tầng mã hóa UTF-8 ghi `C3 A9`.

Ví dụ độc lập **`PrintCharsetDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class PrintCharsetDemo {
    public static void main(String[] args) {
        ByteArrayOutputStream a = new ByteArrayOutputStream();
        try (PrintStream out =
                     new PrintStream(a, false, StandardCharsets.UTF_8)) {
            out.print("é");
        }

        ByteArrayOutputStream b = new ByteArrayOutputStream();
        try (PrintStream out =
                     new PrintStream(b, false, StandardCharsets.UTF_8)) {
            out.write(0xE9);
        }

        ByteArrayOutputStream c = new ByteArrayOutputStream();
        try (PrintWriter out =
                     new PrintWriter(c, false, StandardCharsets.UTF_8)) {
            out.print("é");
        }

        HexFormat hex = HexFormat.of();
        System.out.println("PrintStream text = " + hex.formatHex(a.toByteArray()));
        System.out.println("PrintStream raw = " + hex.formatHex(b.toByteArray()));
        System.out.println("PrintWriter text = " + hex.formatHex(c.toByteArray()));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 PrintCharsetDemo.java
java PrintCharsetDemo
```

Stdout:

```text
PrintStream text = c3a9
PrintStream raw = e9
PrintWriter text = c3a9
```

Đây là lý do **không dùng `write(int)` như cách thay thế `print(char)`**. Trong `PrintStream`, `write(int)` nhận byte chứ không phải Unicode code point. Nếu muốn xuất nội dung văn bản, hãy dùng `print` với charset tương thích với phía đọc.

### Chọn charset khi tạo đối tượng

```java
// Snippet minh họa; output là OutputStream hợp lệ của ứng dụng.
PrintStream ps =
        new PrintStream(output, true, StandardCharsets.UTF_8);
PrintWriter pw =
        new PrintWriter(output, true, StandardCharsets.UTF_8);
```

Đây là hai **lựa chọn constructor**, không phải lời khuyên sử dụng đồng thời hai writer trên cùng `output`. Các wrapper cùng chia sẻ một `OutputStream` có thể dùng bộ đệm/flush khác nhau và tranh quyền đóng tài nguyên, khiến thứ tự byte khó kiểm soát.

- Khi không truyền charset, những constructor dựa trên `OutputStream` sử dụng charset mặc định của JVM; với dữ liệu trao đổi bên ngoài, nên **khai báo charset tường minh**.
- Khi đã có `Writer`, `PrintWriter(writer)` phù hợp trực tiếp. Nếu đó là `OutputStreamWriter`, encoding do `OutputStreamWriter` quyết định.
- Cả hai lớp mặc định thay thế một số chuỗi ký tự không thể mã hóa bằng ký tự thay thế của charset. Nếu yêu cầu **phát hiện** dữ liệu không thể mã hóa, hãy dùng `CharsetEncoder` với `CodingErrorAction.REPORT`.
- Văn bản xuất theo `println` có dấu xuống dòng tùy hệ điều hành; nếu giao thức cần đúng một byte LF (`0A`) hoặc CRLF (`0D 0A`), hãy tuân thủ định dạng giao thức thay vì mặc định dùng `println`.

## 4. `autoFlush` khác nhau như thế nào?

Flush là thao tác đẩy phần dữ liệu chưa được chuyển khỏi các lớp đệm xuống tầng dưới. Flush **không đồng nghĩa** đóng tài nguyên, không khẳng định dữ liệu đã được đồng bộ vật lý lên đĩa và cũng không bảo đảm bên nhận mạng đã xử lý xong.

### Quy tắc `PrintStream`

Nếu bật `autoFlush=true`, API `PrintStream` quy định việc tự gọi flush khi:

1. Một phương thức `println(...)` được gọi.
2. Một mảng byte được ghi vào stream (ví dụ `write(byte[], off, len)`).
3. Ký tự/byte xuống dòng `'\n'` được ghi; ví dụ `print("\n")` hoặc `write('\n')`.

### Quy tắc `PrintWriter`

Nếu bật `autoFlush=true`, API `PrintWriter` tự flush **chỉ khi gọi**:

1. `println(...)`.
2. `printf(...)`.
3. `format(...)`.

**`PrintWriter.print("\n")` không tự flush chỉ vì chuỗi có newline.** Tương tự, `write("\n")` hoặc `append('\n')` không được coi là trigger tự flush. Khi muốn bảo đảm dữ liệu đã được chuyển qua lớp đệm sau thao tác này, hãy gọi `flush()`.

| Lời gọi (autoFlush=true) | `PrintStream` | `PrintWriter` |
| --- | --- | --- |
| `println("ready")` | Tự flush | Tự flush |
| `print("\n")` | Tự flush do newline | **Không tự flush** |
| `write('\n')` | Tự flush cho byte LF | **Không tự flush** khi ghi ký tự LF |
| `write(byte[], 0, len)` | Tự flush khi ghi mảng byte | Không có API ghi byte tương ứng |
| `printf("id=%d", 7)` | Không phải trigger được liệt kê riêng; nếu cần bảo đảm hãy gọi `flush()` | **Tự flush**, dù format không chứa newline |

Các chi tiết thực thi nội bộ có thể khiến `PrintStream` flush khi thao tác định dạng cuối cùng đi qua đường ghi byte; tuy nhiên, không được lấy điều đó thay thế một lần `flush()` tường minh ở **ranh giới giao thức**.

### Ví dụ Java 17+: nhìn được sự khác nhau ngay trong `PrintWriter`

Lưu tệp **`PrintWriterFlushDemo.java`**:

```java
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.Locale;

public class PrintWriterFlushDemo {
    static class CountingWriter extends StringWriter {
        int flushCount;

        @Override
        public void flush() {
            flushCount++;
        }
    }

    public static void main(String[] args) {
        CountingWriter sink = new CountingWriter();

        try (PrintWriter out = new PrintWriter(sink, true)) {
            out.print("first\n");
            System.out.println("after print = " + sink.flushCount);

            out.println("second");
            System.out.println("after println = " + sink.flushCount);

            out.printf(Locale.ROOT, "count=%d", 3);
            System.out.println("after printf = " + sink.flushCount);
        }
    }
}
```

Chạy:

```bash
javac PrintWriterFlushDemo.java
java PrintWriterFlushDemo
```

Kết quả:

```text
after print = 0
after println = 1
after printf = 2
```

Các số được in **trước khi** khối `try-with-resources` đóng writer. Ta đang quan sát số lần `flush` được kích hoạt trong khối lệnh, không đo tốc độ thiết bị hay thời điểm dữ liệu được lưu bền vững.

Một tình huống thực tế: chương trình gửi request bằng `PrintWriter.print(...)` rồi chờ phản hồi. Nếu chưa flush và bên kia đang chờ đủ request, hai phía có thể cùng chờ. Khi giao thức đòi hỏi delimiter hoặc độ dài cố định, phải **hoàn thành thông điệp** và gọi `flush()` hoặc dùng trigger thích hợp trước khi đọc response.

## 5. Lỗi ghi I/O không nhất thiết thoát ra từ `print()`

Cả hai lớp được thiết kế để những phương thức in văn bản có thể **ghi nhận lỗi I/O vào một cờ nội bộ** thay vì ném `IOException` cho từng lời gọi in. Do đó đoạn sau có thể chạy qua `println` mà thực tế đích không nhận được dữ liệu:

```java
// Snippet: out là PrintStream hoặc PrintWriter đã được tạo.
out.println("result");
if (out.checkError()) {
    // Ghi dữ liệu đã gặp lỗi I/O mà print API phát hiện được.
}
```

`checkError()` kiểm tra trạng thái lỗi và gọi flush khi đối tượng còn mở, giúp phát hiện cả một số lỗi xảy ra trong đệm. Lưu ý:

- `checkError() == true`: đã có lỗi được lớp in ghi nhận; cần xử lý theo logic ứng dụng.
- `checkError() == false`: chưa phát hiện lỗi **tại thời điểm kiểm tra**; không chứng minh ghi ra đĩa đã bền vững hay người nhận đã xử lý thành công.
- Constructor mở tệp có thể vẫn ném `IOException` hoặc ngoại lệ liên quan. Các lỗi cú pháp `printf` (`IllegalFormatException`) hay `NullPointerException` cũng không bị quy tắc “không ném IOException” loại bỏ.
- Nếu cần **bắt `IOException` trực tiếp tại nơi ghi**, hãy dùng `Writer`/`OutputStream` hoặc các lớp như `BufferedWriter`, `OutputStreamWriter` thay vì chỉ dựa vào `print`.

### Ví dụ Java 17+: mô phỏng đích ghi hỏng

Tạo **`PrintErrorDemo.java`**:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;

public class PrintErrorDemo {
    static class FailingOutputStream extends OutputStream {
        @Override
        public void write(int value) throws IOException {
            throw new IOException("write failed");
        }
    }

    static class FailingWriter extends Writer {
        @Override
        public void write(char[] chars, int offset, int length)
                throws IOException {
            throw new IOException("write failed");
        }

        @Override
        public void flush() throws IOException {
            throw new IOException("flush failed");
        }

        @Override
        public void close() {
            // No external resource.
        }
    }

    public static void main(String[] args) {
        try (PrintStream out = new PrintStream(
                new FailingOutputStream(), false, StandardCharsets.UTF_8)) {
            out.print("data");
            System.out.println("PrintStream error = " + out.checkError());
        }

        try (PrintWriter out = new PrintWriter(new FailingWriter())) {
            out.print("data");
            System.out.println("PrintWriter error = " + out.checkError());
        }
    }
}
```

Biên dịch, chạy:

```bash
javac PrintErrorDemo.java
java PrintErrorDemo
```

Stdout:

```text
PrintStream error = true
PrintWriter error = true
```

Các phương thức `print` **không ném trực tiếp `IOException`** từ hai đích giả lập thất bại; `checkError()` cho biết trạng thái lỗi. Trong dịch vụ thật, hãy kiểm tra trạng thái sau điểm ghi/flush quan trọng, ghi nhận lỗi và đưa ra chiến lược xử lý thay vì coi việc gọi `print` là đã giao dữ liệu thành công.

## 6. `System.out`, `System.err` và console

`System.out` và `System.err` là **`PrintStream`**, không phải `PrintWriter`:

```java
System.out.println("Ready");
System.err.printf("Status=%d%n", 500);
```

Đây là đoạn minh họa hợp lệ trong phương thức Java. Nó giải thích vì sao các ví dụ “Hello World” gọi `println` trực tiếp trên `System.out`.

Không nên đóng `System.out` hoặc `System.err` ở một hàm tiện ích:

```java
// Ví dụ thiết kế sai khi ứng dụng còn cần console:
try (PrintStream console = System.out) {
    console.println("Ready");
}
```

`close()` thường đóng cả nguồn lực bên dưới và có thể làm phần còn lại của chương trình không in được nữa. Hãy để thành phần quản lý vòng đời ứng dụng quyết định vòng đời các stream toàn cục.

Bạn **có thể** bọc `System.out` trong `PrintWriter`:

```java
// Đoạn minh họa: không tự ý close vì có thể đóng System.out bên dưới.
PrintWriter consoleWriter = new PrintWriter(System.out, true);
consoleWriter.println("Ready");
```

Nhưng việc bọc thêm thường không cần thiết để chỉ in console và có thể khiến quản lý flush/close rắc rối hơn. Muốn kiểm thử output, truyền `PrintStream` hoặc `Writer` từ caller; test dùng `ByteArrayOutputStream` hay `StringWriter` để so sánh nội dung.

Với ứng dụng server, phần lớn thông báo vận hành dài hạn nên đi qua API logging phù hợp thay vì sử dụng `System.out.println` ở mọi nơi.

## 7. Khi nào chọn loại nào?

### Chọn `PrintStream` khi

- Có sẵn `OutputStream` và cần xuất văn bản/giá trị định dạng.
- Đang làm việc với `System.out` hoặc `System.err`.
- API thư viện yêu cầu chính xác đối tượng `PrintStream`.
- Có lý do rõ ràng dùng thao tác byte thô lẫn in văn bản; phải quy định encoding và khung dữ liệu, không trộn tùy tiện trong giao thức.

### Chọn `PrintWriter` khi

- Có sẵn một `Writer` như `BufferedWriter`, `StringWriter` hoặc writer do framework cung cấp.
- Muốn làm việc theo **ký tự** và cần `print`, `println`, `printf` nhưng không có nhu cầu ghi byte thô.
- Muốn tạo text trong bộ nhớ rồi kiểm tra nội dung mà không cần encode/decode ở bước trung gian.

### Không nhất thiết dùng cả hai

| Yêu cầu | API cân nhắc |
| --- | --- |
| Ghi văn bản và cần bắt trực tiếp `IOException` | `BufferedWriter`, `OutputStreamWriter`, `Files.newBufferedWriter` |
| Ghi dữ liệu nhị phân | `OutputStream`, `BufferedOutputStream` |
| Ghi giá trị nguyên thủy theo dạng nhị phân | `DataOutputStream` |
| Tích lũy text trong bộ nhớ | `StringWriter`; thêm `PrintWriter` nếu cần định dạng |
| Kiểm soát lỗi mã hóa ký tự nghiêm ngặt | `CharsetEncoder` + `CodingErrorAction.REPORT` |
| Nhật ký ứng dụng production | Logging framework |

Không nên xem `PrintStream` là cách mặc định ghi protocol nhị phân chỉ vì nó cũng có `write(byte[])`. Ngược lại, không cần tạo `PrintWriter` nếu `Writer` sẵn có chỉ cần `write(String)` mà không dùng tiện ích định dạng.

## 8. Những lỗi thường gặp

1. **Nhầm `PrintStream` với stream chỉ chứa văn bản.** Nó có thể ghi byte thô; `print` là một API tiện ích chuyển giá trị thành văn bản trên byte stream.
2. **Nhầm `PrintWriter` không thể ghi file/socket.** Nó có thể nhận `OutputStream` và charset. Bản chất API vẫn là ký tự.
3. **Dùng `PrintStream.write(int)` để mã hóa Unicode.** Lệnh này ghi byte, không chuyển Unicode code point thành UTF-8.
4. **Giả định mọi lệnh chứa `\n` đều tự flush.** Với `PrintWriter` chỉ `println/printf/format` kích hoạt autoFlush; `print("\n")` không đủ.
5. **Bỏ qua `checkError()`.** `print` không bảo đảm phát hiện lỗi qua exception và có thể để lệnh tiếp theo chạy dù tầng dưới lỗi.
6. **Dùng `printf` nhưng không quản lý locale.** Với file trao đổi máy đọc, dùng locale rõ ràng và quy định dấu thập phân.
7. **Cho rằng `println` luôn ghi `\n`.** Nó dùng ký tự xuống dòng của nền tảng; định dạng mạng/tệp có quy định riêng cần được tuân thủ.
8. **Tạo nhiều wrapper cùng ghi một đích.** Khi bộ đệm, charset và thứ tự flush khác nhau, dữ liệu có thể bị xen kẽ hoặc đảo thứ tự; chọn một pipeline ghi có chủ sở hữu.
9. **Đóng writer mượn từ caller.** `close()` thường kéo theo đóng đích bên dưới; phân biệt wrapper do hàm sở hữu và stream do caller quản lý.
10. **Giả định flush nghĩa là đã lưu bền vững.** Flush chỉ chuyển dữ liệu qua tầng đệm thích hợp; độ bền dữ liệu hoặc xác nhận từ peer là vấn đề riêng.

## 9. Tự kiểm tra

**Câu 1.** Vì sao `System.out.println(...)` dùng `PrintStream`?

**Trả lời:** `System.out` là một `PrintStream`, một loại `OutputStream` có các phương thức in/định dạng tiện ích.

**Câu 2.** `PrintWriter` có thể nhận `OutputStream` không?

**Trả lời:** Có. Constructor nhận `OutputStream` tạo tầng chuyển ký tự thành byte phía dưới; nó vẫn là API `Writer`.

**Câu 3.** `PrintWriter.print("\n")` với `autoFlush=true` có bảo đảm flush ngay không?

**Trả lời:** Không. `PrintWriter` tự flush do `println`, `printf` hoặc `format`; nếu cần, gọi `flush()` rõ ràng.

**Câu 4.** `PrintStream.write(0xE9)` có ghi chữ `é` theo UTF-8 không?

**Trả lời:** Không. Nó ghi đúng byte `E9`, còn `print("é")` theo UTF-8 ghi `C3 A9`.

**Câu 5.** Lệnh `out.println("ok")` chạy qua mà không ném exception có chứng minh file đã ghi thành công không?

**Trả lời:** Không. Cả hai print API có thể cất lỗi I/O trong cờ nội bộ; phải kiểm tra `checkError()` và xử lý theo mức bảo đảm cần thiết của ứng dụng.

**Câu 6.** Muốn tạo báo cáo text vào `StringWriter`, nên dùng gì?

**Trả lời:** Dùng trực tiếp `StringWriter.write(...)` khi chỉ ghi chuỗi; bọc bằng `PrintWriter` nếu cần `println` và định dạng giá trị theo `printf`.

## 10. Tài liệu chuẩn

- [Java SE 17 — `PrintStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html)
- [Java SE 17 — `PrintWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html)
- [Java SE 17 — `OutputStreamWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html)
- [Java SE 17 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)

**Ghi nhớ:** `PrintStream` là lớp in có gốc **byte stream**, `PrintWriter` là lớp in có gốc **character writer**; cả hai đều có `print/println/printf` và `checkError`, nhưng **autoFlush không giống nhau**. Chọn lớp theo đích và dữ liệu thực sự, khai báo charset khi cần byte, kiểm tra lỗi I/O và quản lý đúng quyền sở hữu stream.
