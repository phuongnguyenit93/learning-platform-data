# Đóng stream bọc, tài nguyên chia sẻ và tài nguyên do bên gọi truyền vào

## 1. Vấn đề cốt lõi: ai có trách nhiệm đóng tài nguyên?

Trong Java I/O, ta thường viết một chuỗi các lớp bọc quanh tệp, socket hoặc một nguồn/đích khác:

```text
Ứng dụng
   │ đọc ký tự theo dòng
   ▼
BufferedReader
   │ đọc ký tự
   ▼
InputStreamReader (giải mã UTF-8)
   │ đọc byte
   ▼
FileInputStream / Files.newInputStream
   │
   ▼
Tệp do hệ điều hành quản lý
```

Mỗi lớp có một nhiệm vụ: `FileInputStream` đọc byte từ tệp; `InputStreamReader` chuyển byte thành ký tự; `BufferedReader` bổ sung đệm và `readLine()`. Nhưng những đối tượng này **không độc lập hoàn toàn về vòng đời**. Đóng lớp bọc ngoài thường sẽ đóng lớp bên trong, rồi cuối cùng giải phóng tệp hoặc kết nối gốc.

Câu hỏi quan trọng không đơn thuần là “stream có cần `close()` không?”, mà là:

- **Ai tạo và sở hữu** tài nguyên gốc?
- **Ai được phép kết thúc** việc sử dụng tài nguyên?
- Một wrapper **có chuyển tiếp `close()`** xuống tài nguyên bên dưới không?
- Nếu cùng tài nguyên được nhiều thành phần sử dụng, **thành phần nào được đóng nó**?
- Nếu một phương thức được truyền `InputStream`, `OutputStream`, `Reader` hoặc `Writer` từ bên gọi, hợp đồng của phương thức có **chuyển quyền sở hữu** hay chỉ **mượn để dùng tạm**?

Đối với một luồng gắn với tệp hoặc socket, quên đóng có thể rò rỉ tài nguyên hệ điều hành hoặc làm dữ liệu đệm chưa được hoàn tất. Ngược lại, đóng quá sớm một luồng chia sẻ có thể khiến các phần còn lại của ứng dụng không thể đọc/ghi tiếp.

**Nguyên tắc mặc định để thiết kế API:** bên **sở hữu tài nguyên** chịu trách nhiệm đóng; phương thức chỉ **mượn stream** thường đọc/ghi theo hợp đồng rồi trả về, không tự ý đóng. Ngoại lệ phải được ghi rõ trong tài liệu API.

## 2. Phân biệt resource, wrapper và ownership

Một *resource* là đối tượng có vòng đời cần kiểm soát, chẳng hạn handle tệp, kết nối mạng, vùng nhớ native hoặc cấu trúc I/O cần hoàn tất trước khi kết thúc. *Wrapper* là đối tượng bổ sung hành vi cho resource hoặc stream khác: buffering, chuyển byte/ký tự, giải nén, mã hóa, ghi kiểu dữ liệu v.v.

Ví dụ:

```java
InputStream raw = Files.newInputStream(path);
InputStream buffered = new BufferedInputStream(raw);
```

Đây là **đoạn minh họa**, cần `java.io.InputStream`, `BufferedInputStream`, `java.nio.file.Files`, `Path` và xử lý `IOException`. Nếu code tạo cả `raw` và `buffered`, code đó thường sở hữu luồng và phải đóng chúng theo một chiến lược an toàn. Với cách bọc phổ biến này, đóng `buffered` sẽ đóng `raw`.

Cùng một stream gốc có thể được coi theo các cách khác nhau:

| Tình huống | Ai sở hữu? | Ai đóng? |
| --- | --- | --- |
| Hàm tự mở `Files.newInputStream(path)` để xử lý tại chỗ | Hàm mở stream | Hàm đóng, thường bằng try-with-resources |
| Hàm nhận `InputStream in` từ caller chỉ để parse | Caller | Caller đóng; hàm parse không đóng nếu hợp đồng nói mượn |
| Factory mở file, trả một `BufferedReader` cho caller | Caller nhận quyền sở hữu thông qua đối tượng trả về | Caller đóng reader trả về |
| Ứng dụng dùng `System.in`, `System.out`, `System.err` | Runtime/ứng dụng cấp cao | Không đóng tùy tiện trong thư viện |
| Hai component cùng dùng một stream do ứng dụng quản lý | Thành phần điều phối cấp cao | Đóng khi mọi người dùng đã kết thúc |
| `GZIPOutputStream` do hàm tự tạo và sở hữu để sinh định dạng GZIP | Hàm hoặc caller nhận stream, tùy API | Chủ sở hữu phải hoàn tất `finish`/`close` đúng lúc |

**Một wrapper không tự động trở thành chủ sở hữu hợp pháp chỉ vì nó giữ tham chiếu đến stream bên dưới.** Nhưng nhiều wrapper chuẩn **có hành vi chuyển tiếp close**, nên nếu API chỉ được phép mượn tài nguyên, ta phải thiết kế để không vô ý gọi `close()` trên wrapper ấy.

## 3. Close lan từ ngoài vào trong như thế nào?

Nhiều wrapper của `java.io` tuân theo mô hình: khi đóng wrapper ngoài, nó flush/xử lý trạng thái của chính mình và đóng đối tượng delegate bên trong.

```text
close(BufferedOutputStream)
    ├─ flush dữ liệu byte đang đệm
    └─ close(OutputStream bên dưới)
          └─ giải phóng tài nguyên thật (nếu có)
```

Một số wrapper quen thuộc:

| Wrapper | Hành vi vòng đời cần chú ý |
| --- | --- |
| `BufferedInputStream` | `close()` đóng luồng đầu vào được bọc |
| `BufferedOutputStream` | `close()` có thể flush dữ liệu đệm rồi đóng luồng bên dưới |
| `InputStreamReader` | `close()` đóng luồng byte được bọc |
| `OutputStreamWriter` | `close()` hoàn tất việc ghi/mã hóa rồi đóng luồng bên dưới |
| `BufferedReader` / `BufferedWriter` | `close()` đóng reader/writer được bọc |
| `DataInputStream` / `DataOutputStream` | `close()` thường chuyển đến stream delegate |
| `GZIPInputStream` / `GZIPOutputStream` | `close()` kết thúc tài nguyên bọc; đầu ra GZIP cần hoàn tất cấu trúc nén |
| `PrintWriter` / `PrintStream` | Có vòng đời ghi/flush/close và cơ chế báo lỗi riêng, có thể đóng đích bên dưới |

Hành vi cụ thể phải dựa vào **API của lớp cụ thể** chứ không suy ra từ tên. Ví dụ, `ByteArrayInputStream` và `ByteArrayOutputStream` có `close()` không làm mất khả năng sử dụng; `StringReader.close()` lại khiến thao tác đọc sau đó không hợp lệ. Việc một test dùng memory stream vẫn chạy sau khi close **không chứng minh** cách đóng sẽ an toàn với file hoặc socket.

### Một chuỗi được sở hữu trọn vẹn: đóng lớp ngoài là đủ

```java
Path path = Path.of("data.txt");
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                Files.newInputStream(path), StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý.
    }
}
```

Đây là **đoạn minh họa**, cần import `java.io.BufferedReader`, `InputStreamReader`, `java.nio.file.Files`, `Path`, `StandardCharsets` và xử lý `IOException`. Khi reader được đóng, nó đóng `InputStreamReader`, rồi đến input stream của tệp. Không cần gọi `reader.close()` lần nữa ở `finally`.

Lưu ý về **ngoại lệ trong khi xây dựng chuỗi wrapper**: nếu một phép tạo wrapper có thể ném exception sau khi đã mở resource gốc nhưng trước khi wrapper trở thành tài nguyên của `try`, resource gốc cần được bảo vệ riêng. Một mẫu xây dựng an toàn hơn trong trường hợp constructor có rủi ro là khai báo resource gốc ngay trong danh sách `try`, dù việc đóng cả wrapper lẫn gốc lúc kết thúc có thể tạo lời gọi close lặp lại. Cần chọn cấu trúc phù hợp với API và xem xét tính an toàn khi đóng lặp.

## 4. Try-with-resources: phương thức khuyến nghị cho resource do mình sở hữu

`try-with-resources` (Java 7+, cải tiến cú pháp từ Java 9) gọi `close()` tự động cho từng biến resource implement `AutoCloseable` hoặc `Closeable`, kể cả khi khối xử lý ném exception.

```java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    in.transferTo(out);
}
// out.close() được gọi trước in.close().
```

Đây là **đoạn minh họa**, giả định có `Path source`, `Path target` và các import phù hợp. Vì `in` và `out` là hai tài nguyên **độc lập**, khai báo cả hai trong `try` là hợp lý. Khi có nhiều resource, Java đóng chúng theo **thứ tự ngược với thứ tự khai báo**.

Nếu một tài nguyên **bọc tài nguyên khác**, ví dụ `BufferedInputStream(raw)`, đặt cả `raw` lẫn wrapper ở danh sách `try` sẽ khiến luồng gốc có khả năng nhận **hai lời gọi close**:

```java
// raw được đưa trực tiếp vào wrapper; minh họa close kép.
try (InputStream raw = Files.newInputStream(source);
     InputStream buffered = new BufferedInputStream(raw)) {
    // ...
}
// buffered.close() sẽ đóng raw; sau đó try-with-resources đóng raw nữa.
```

Một số stream được thiết kế để đóng lặp mà không ảnh hưởng, nhưng **không thể giả định mọi `AutoCloseable` đều idempotent**. Nếu constructor wrapper không ném lỗi sau khi mở resource (như các constructor wrapper đơn giản với đối số hợp lệ), một lựa chọn gọn là khai báo **chỉ wrapper ngoài** làm tài nguyên ở `try`. Nếu cần bảo vệ nhiều giai đoạn khởi tạo có thể thất bại, bảo vệ resource từ lúc mở và xử lý close nhiều lần theo hợp đồng cụ thể.

### Lỗi trong phần xử lý và lỗi lúc close

`try-with-resources` giữ ngoại lệ chính ném từ thân `try`; lỗi phát sinh khi đóng resource được gắn dưới dạng **suppressed exception**. Đây là khác biệt lớn so với `finally` tự viết không cẩn thận, nơi exception từ `close()` có thể che mất lỗi gốc.

```java
try (InputStream in = Files.newInputStream(source)) {
    // Nếu phần xử lý ném exception...
} // ...và close cũng lỗi, lỗi close được gắn là suppressed.
```

Vì tài nguyên có thể lỗi cả trong khi dùng lẫn khi đóng, thông tin suppressed exception rất hữu ích để chẩn đoán. Không nên bắt `IOException` rồi bỏ qua chỉ vì code đang “dọn dẹp”.

## 5. Ví dụ chạy được: xác minh wrapper đóng stream bên dưới

Ví dụ dùng `ByteArrayOutputStream` được mở rộng để ghi nhận số lần gọi `close()`. Điều này cho phép kiểm tra hành vi đóng mà không cần tệp thực.

**Tệp `WrapperCloseDemo.java`:**

```java
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class WrapperCloseDemo {
    static final class TrackingOutput extends ByteArrayOutputStream {
        private int closes;

        @Override
        public void close() throws IOException {
            closes++;
            super.close();
        }

        int closeCount() {
            return closes;
        }
    }

    public static void main(String[] args) throws IOException {
        TrackingOutput underlying = new TrackingOutput();

        try (BufferedOutputStream buffered = new BufferedOutputStream(underlying)) {
            buffered.write("ABC".getBytes(StandardCharsets.US_ASCII));
            System.out.println("Before close, bytes: " + underlying.size());
        }

        System.out.println("After close, text: "
                + underlying.toString(StandardCharsets.US_ASCII));
        System.out.println("Underlying close calls: "
                + underlying.closeCount());
    }
}
```

Lệnh với JDK 17+:

```bash
javac WrapperCloseDemo.java
java WrapperCloseDemo
```

**Stdout chính xác:**

```text
Before close, bytes: 0
After close, text: ABC
Underlying close calls: 1
```

`BufferedOutputStream` có buffer mặc định đủ chứa ba byte, nên trước khi đóng, `underlying` chưa nhận byte nào. Khi `try` kết thúc, wrapper được đóng, làm các byte đệm được ghi xuống `underlying`, rồi gọi `close()` của nó đúng một lần trong ví dụ. Ta vẫn đọc được nội dung `ByteArrayOutputStream` sau close vì lớp bộ nhớ này cho phép như vậy; không nên suy ra rằng **mọi** output stream cho phép truy cập dữ liệu sau khi đóng.

**Ý nghĩa quan trọng:** nếu `underlying` là một socket hay file stream do caller truyền vào và còn cần sử dụng, việc đóng `BufferedOutputStream` trên nó có thể cắt đứt công việc của caller.

## 6. Resource do caller truyền vào: mượn hay nhận quyền sở hữu?

Trong thư viện Java, một phương thức như sau rất thường gặp:

```java
static void encode(Data record, OutputStream output) throws IOException {
    // Ghi record vào output...
}
```

Đây là **chữ ký minh họa**; `Data` đại diện kiểu dữ liệu ứng dụng chưa định nghĩa. Chữ ký **không tự cho biết** ai phải đóng `output`. Cần công bố hợp đồng:

- **Borrowed input/output:** caller tiếp tục sở hữu; hàm không đóng stream. Nếu hàm tự tạo wrapper để dùng tạm thì cũng không được đóng tài nguyên bên dưới ngoài ý muốn.
- **Transferred ownership:** caller bàn giao quyền sở hữu; hàm được phép đóng stream và phải tài liệu hóa rõ, kể cả khi có ngoại lệ.
- **Resource returned by factory:** hàm tạo stream và trả về một `Closeable` mới, caller nhận trách nhiệm đóng khi dùng xong.
- **Shared resource:** nhiều thành phần cùng sử dụng; một thành phần điều phối quy định thời điểm đóng, không để từng consumer đóng tùy ý.

Quy ước **mượn** đặc biệt hữu ích khi một API nhận `InputStream`/`OutputStream`, vì caller có thể ghép nhiều thao tác trên cùng stream:

```text
Caller tạo output
  ├─ writeHeader(output)
  ├─ writeRecords(output)
  ├─ writeFooter(output)
  └─ caller flush/close(output) sau cùng
```

Nếu `writeRecords(output)` đóng output khi xong, `writeFooter(output)` có thể thất bại. Đó là lỗi **ownership**, ngay cả khi mỗi đoạn code chạy riêng lẻ vẫn đúng.

### Một API mượn OutputStream nên làm gì?

- Ghi dữ liệu đúng định dạng, xử lý `IOException` theo hợp đồng.
- Không gọi `output.close()` trừ khi nhận chuyển quyền sở hữu một cách rõ ràng.
- Thống nhất có `flush()` hay không. Thường caller sở hữu tài nguyên sẽ quyết định thời điểm flush; một giao thức tương tác có thể yêu cầu flush sau mỗi thông điệp.
- Nếu dùng `BufferedOutputStream` hay `OutputStreamWriter` bọc output mượn, cần flush dữ liệu đã ghi trước khi trả về mà **không đóng delegate**.
- Nếu wrapper sử dụng bộ mã hóa hoặc định dạng đòi “kết thúc luồng” mới hoàn tất (GZIP, ZIP, một số mã hóa có trạng thái), không thể tùy tiện thay close bằng flush. Cần dùng API `finish()` khi được hỗ trợ hoặc thiết kế lại quyền sở hữu.

### Một API mượn InputStream nên làm gì?

- Đọc theo số byte cần thiết, hoặc đến EOF nếu hợp đồng nói vậy.
- Không tự đóng input nếu caller còn sử dụng.
- Cân nhắc buffering và vị trí stream khi trả về: wrapper có thể **đọc trước** nhiều byte vào buffer, khiến caller đọc từ stream gốc sau đó không thấy dữ liệu theo cách dự đoán.
- Nếu cần phối hợp nhiều parser/consumer trên một stream, thống nhất framing, giới hạn đọc và việc chia sẻ **chính cùng một wrapper** thay vì tạo nhiều wrapper đọc trước độc lập.

**Đọc trước và đóng stream là hai vấn đề khác nhau:** ngay cả khi không gọi close, một `BufferedReader` riêng có thể giữ những byte/ký tự đã nạp trước trong buffer. Caller không nên lập tức tiếp tục với stream gốc nếu không có thiết kế về bộ đệm/vị trí.

## 7. Ví dụ chạy được: hàm mượn stream không được đóng nó

Chương trình sau chứng minh code xử lý chỉ ghi dữ liệu và để caller đóng. `TrackingOutput` ghi nhận nếu một lệnh `close()` đã xảy ra.

**Tệp `BorrowedStreamDemo.java`:**

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class BorrowedStreamDemo {
    static final class TrackingOutput extends ByteArrayOutputStream {
        private boolean closed;

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }

        boolean isClosed() {
            return closed;
        }
    }

    // Hợp đồng: borrowed OutputStream; method không close và không flush.
    static void writePart(OutputStream output, String value)
            throws IOException {
        output.write(value.getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws IOException {
        TrackingOutput shared = new TrackingOutput();

        try {
            writePart(shared, "A");
            writePart(shared, "B");

            System.out.println("Closed before caller: " + shared.isClosed());
            System.out.println("Accumulated: "
                    + shared.toString(StandardCharsets.UTF_8));
        } finally {
            shared.close(); // Caller là owner.
        }

        System.out.println("Closed by caller: " + shared.isClosed());
    }
}
```

Biên dịch/chạy:

```bash
javac BorrowedStreamDemo.java
java BorrowedStreamDemo
```

**Stdout chính xác:**

```text
Closed before caller: false
Accumulated: AB
Closed by caller: true
```

Điểm cần nhìn là **caller gọi `writePart` hai lần trên cùng đích**, và chỉ caller đóng đích sau cùng. Nếu `writePart` tự ý đóng một file stream thật, lần gọi tiếp theo có thể không còn ghi được. `ByteArrayOutputStream` vốn cho phép ghi sau close, nên ví dụ dùng cờ theo dõi để không dựa vào tính chất đó.

Khi hàm cần trao đổi nhiều phần dữ liệu trên một kết nối, ownership càng quan trọng: một parser riêng lẻ không được ngắt socket ngay sau khi xử lý xong message nếu giao thức còn dùng kết nối cho message tiếp theo.

## 8. Khi wrapper tự tạo lại đóng tài nguyên mượn: giải pháp nào?

Đây là một lỗi dễ gặp:

```java
// Mã minh họa NGUY HIỂM nếu output do caller sở hữu:
static void badWrite(OutputStream output) throws IOException {
    try (BufferedOutputStream buffered = new BufferedOutputStream(output)) {
        buffered.write(42);
    } // buffered.close() đóng cả output do caller truyền vào.
}
```

`BufferedOutputStream` là wrapper được tạo trong hàm nhưng delegate lại thuộc caller. `try-with-resources` trên wrapper có vẻ hợp lý ở bề mặt, nhưng vi phạm hợp đồng mượn.

Có ba hướng thiết kế tùy mục đích:

**Cách 1 — Không tạo wrapper trong hàm.** Để caller tạo một buffered stream và truyền sẵn:

```java
static void writeBytes(OutputStream output, byte[] bytes)
        throws IOException {
    output.write(bytes);
}
```

Caller quyết định khi nào flush/close; hàm dùng trực tiếp stream được cho. Cách này thường đơn giản nhất.

**Cách 2 — Tạo wrapper tạm và flush, nhưng không close.** Ví dụ:

```java
static void writeBuffered(OutputStream borrowed, byte[] bytes)
        throws IOException {
    BufferedOutputStream buffered = new BufferedOutputStream(borrowed);
    buffered.write(bytes);
    buffered.flush();
    // Không close buffered vì close sẽ đóng borrowed.
}
```

Chỉ sử dụng mẫu này khi **không cần bước finish/close để hoàn tất định dạng** và không giữ lại wrapper cho các lần gọi sau. Nếu caller kiểm soát cả vòng đời, tốt hơn là caller giữ một wrapper lâu dài để tránh tạo nhiều lớp đệm và tránh việc mỗi lời gọi flush không cần thiết.

**Cách 3 — Dùng wrapper có chính sách “không đóng delegate”** nếu phải đóng/hoàn tất wrapper ở phạm vi cục bộ. Có thể tạo `FilterOutputStream` override `close()` để chỉ flush mà không chuyển tiếp close, rồi bọc nó bằng wrapper cần đóng:

```java
final class NonClosingOutputStream extends FilterOutputStream {
    NonClosingOutputStream(OutputStream delegate) {
        super(delegate);
    }

    @Override
    public void close() throws IOException {
        flush(); // Cố ý không gọi super.close().
    }
}
```

Đây là **class minh họa**; cần import `java.io.FilterOutputStream`, `OutputStream`, `IOException`. Nó bảo vệ **việc close delegate** khi wrapper bên ngoài gọi close. Tuy nhiên:

- Nó **không ngăn code khác giữ tham chiếu đến delegate rồi tự đóng delegate**.
- Nó không biến một tài nguyên có quyền sở hữu khác trở thành thread-safe.
- Nó không thay thế yêu cầu quản lý buffer/encoding/định dạng của wrapper.
- Nếu wrapper khác đã sử dụng riêng resource gốc trước đó, vấn đề thứ tự/đọc trước vẫn tồn tại.
- Một số thư viện cung cấp sẵn các biến thể non-closing; cần hiểu chính xác hợp đồng của implementation được chọn.

### Ví dụ Java 17 hoàn chỉnh: đóng BufferedOutputStream mà vẫn giữ delegate

**Tệp `NonClosingWrapperDemo.java`:**

```java
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class NonClosingWrapperDemo {
    static final class TrackingOutput extends ByteArrayOutputStream {
        private boolean closed;

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }

        boolean wasClosed() {
            return closed;
        }
    }

    static final class NonClosingOutputStream extends FilterOutputStream {
        NonClosingOutputStream(OutputStream target) {
            super(target);
        }

        @Override
        public void close() throws IOException {
            flush();
        }
    }

    static void writeBorrowed(OutputStream borrowed) throws IOException {
        try (BufferedOutputStream buffered =
                     new BufferedOutputStream(
                             new NonClosingOutputStream(borrowed))) {
            buffered.write("Hello".getBytes(StandardCharsets.US_ASCII));
        }
    }

    public static void main(String[] args) throws IOException {
        TrackingOutput shared = new TrackingOutput();
        try {
            writeBorrowed(shared);
            System.out.println("Closed after wrapper: " + shared.wasClosed());

            shared.write('!');
            System.out.println("Content: "
                    + shared.toString(StandardCharsets.US_ASCII));
        } finally {
            shared.close();
        }
        System.out.println("Closed by caller: " + shared.wasClosed());
    }
}
```

Chạy:

```bash
javac NonClosingWrapperDemo.java
java NonClosingWrapperDemo
```

**Stdout chính xác:**

```text
Closed after wrapper: false
Content: Hello!
Closed by caller: true
```

Ở đây `BufferedOutputStream.close()` đẩy byte xuống `NonClosingOutputStream`, rồi gọi `close()` của lớp bảo vệ. `NonClosingOutputStream.close()` chỉ `flush()`, không đóng stream `shared`. Sau khi `writeBorrowed` trả về, caller tiếp tục ghi ký tự `!` và cuối cùng tự đóng resource. Đây là cách kiểm thử trực tiếp **ownership không bị chuyển vô tình**.

## 9. Tài nguyên chia sẻ: System.in, System.out, System.err

`System.in` là `InputStream`; `System.out` và `System.err` là `PrintStream` do môi trường JVM cung cấp. Chúng thường được dùng chung bởi nhiều đoạn code trong cùng tiến trình.

Một lỗi phổ biến:

```java
// Mã minh họa: nếu chương trình còn dùng stdin, không nên làm thế.
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
    System.out.println(reader.readLine());
} // Đóng reader => InputStreamReader => System.in.
```

Nếu những phần khác cần tiếp tục đọc `System.in`, chúng có thể không đọc được nữa. Tương tự, đóng một `PrintWriter` bọc `System.out` có thể đóng stdout, khiến `System.out.println` sau đó không hiển thị như mong đợi. `PrintStream` có thể ghi trạng thái lỗi thay vì ném `IOException` ra người gọi, nên lỗi dễ bị bỏ qua.

**Chiến lược hợp lý:** ứng dụng cấp cao quyết định vòng đời các luồng chuẩn; hàm thư viện chỉ mượn chúng. Nếu tạo wrapper để đọc stdin liên tục, giữ wrapper ở một chỗ và chuyển cho các component cần dùng theo hợp đồng. Tránh nhiều `Scanner`/`BufferedReader` độc lập cùng tiêu thụ stdin, vì buffering có thể làm mỗi component đọc trước và cản trở nhau.

### Scanner cũng có vấn đề quyền sở hữu

```java
Scanner scanner = new Scanner(System.in, StandardCharsets.UTF_8);
// ...
scanner.close(); // Đồng thời đóng System.in bên dưới.
```

Đây là đoạn minh họa, cần `java.util.Scanner` và `StandardCharsets`. `Scanner` implements `Closeable`; đóng Scanner sẽ đóng nguồn nếu nguồn implement `Closeable`. Dùng `try-with-resources` với Scanner trên **file stream do mình sở hữu** thì đúng, nhưng dùng trên `System.in` cần xem xét vòng đời chương trình.

### PrintWriter, PrintStream và lỗi khi đóng/ghi

`PrintWriter` và `PrintStream` cung cấp API `print`/`println` thuận tiện, nhưng thường **không ném checked IOException trong các phương thức in**. Chúng ghi nhận lỗi I/O, có thể được kiểm tra qua `checkError()`. Vì vậy ngay cả khi đã tuân thủ ownership, nếu kết quả đầu ra quan trọng, code cần chiến lược phát hiện lỗi thích hợp; `close()` trong `try-with-resources` của các lớp này không nhất thiết bộc lộ lỗi như các `Writer` khác.

Với output phải đảm bảo báo lỗi `IOException`, dùng `OutputStream`/`Writer` phù hợp (và kiểm tra lỗi trong quá trình ghi/flush/close) có thể rõ ràng hơn `PrintWriter` cho các nhu cầu nghiêm ngặt.

## 10. Shared resource không phải tự động an toàn để nhiều thread dùng chung

Có hai vấn đề độc lập:

1. **Lifecycle safety:** ai được đóng và vào thời điểm nào?
2. **Concurrency safety:** nếu hai thread cùng đọc/ghi một stream, dữ liệu và thứ tự có được giữ đúng giao thức không?

Việc không đóng một stream mượn giải quyết phần lớn rủi ro lifecycle, nhưng **không đảm bảo** nhiều thread cùng ghi sẽ không xen kẽ byte, nhiều reader cùng đọc sẽ không tranh dữ liệu, hoặc wrapper có buffer sẽ xử lý đồng thời an toàn.

Ví dụ, hai thành phần dùng chung một `OutputStream` để xuất JSON; nếu một thành phần ghi header và phần kia chen thông điệp vào giữa, dữ liệu có thể hỏng dù không ai gọi `close()`. Cần đồng bộ/gom toàn bộ một message ở cấp protocol, hoặc đưa việc ghi vào một thành phần điều phối.

Khi nhiều component cần dùng chung resource:

- Quy định **chủ sở hữu duy nhất** để đóng.
- Quy định **phạm vi mượn** và thời điểm không còn consumer hoạt động.
- Thiết kế giao thức đọc/ghi rõ framing và thứ tự.
- Không để mỗi consumer tự tạo wrapper buffering độc lập nếu chúng cùng thao tác một vị trí stream.
- Nếu có xử lý bất đồng bộ, đảm bảo resource còn sống đến khi tất cả tác vụ đã hoàn tất.

Trong các kiến trúc phức tạp, có thể dùng một **owner/coordinator** hoặc một abstraction chỉ cung cấp thao tác cần thiết, thay vì đưa thẳng stream cho nhiều nơi rồi trông cậy từng nơi không đóng.

## 11. Ví dụ lỗi close: suppressed exception trong try-with-resources

Một stream có thể thất bại khi đọc/ghi, đồng thời `close()` cũng có thể thất bại. Java giữ lỗi chính và gắn lỗi close thành suppressed.

**Tệp `SuppressedCloseDemo.java`:**

```java
import java.io.IOException;

public class SuppressedCloseDemo {
    static final class FaultyResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FaultyResource resource = new FaultyResource()) {
            throw new IOException("work failed");
        } catch (IOException failure) {
            System.out.println("Main failure: " + failure.getMessage());
            System.out.println(
                    "Suppressed count: " + failure.getSuppressed().length);
            for (Throwable suppressed : failure.getSuppressed()) {
                System.out.println(
                        "Suppressed: " + suppressed.getMessage());
            }
        }
    }
}
```

Lệnh:

```bash
javac SuppressedCloseDemo.java
java SuppressedCloseDemo
```

**Stdout chính xác:**

```text
Main failure: work failed
Suppressed count: 1
Suppressed: close failed
```

Nếu không có lỗi trong thân `try`, nhưng `close()` ném lỗi, lỗi close sẽ là lỗi chính. Nếu có nhiều tài nguyên và nhiều lần đóng lỗi, Java có thể giữ nhiều suppressed exception; thứ tự đóng vẫn là **ngược thứ tự khai báo**.

Điểm thực hành là **không che khuất lỗi gốc**. Tránh mẫu thủ công sau nếu không xử lý ngoại lệ đúng:

```java
// Mã minh họa NGUY HIỂM: exception từ close có thể che exception ban đầu.
try {
    doWork();
} finally {
    resource.close();
}
```

`doWork()` và `resource` ở đây là placeholder khái niệm trong mẫu giải thích, không phải chương trình độc lập. Khi có thể, ưu tiên `try-with-resources`; khi cần xử lý ngoại lệ phức tạp, giữ lại nguyên nhân gốc và suppressed thay vì bỏ qua.

## 12. Flush, finish và close: ba hành động không đồng nghĩa

**`flush()`** yêu cầu dữ liệu đang đệm của một luồng ghi được đẩy xuống tầng dưới. Nó thường không đóng luồng và không cam kết byte đã bền vững trên ổ đĩa.

**`finish()`** tồn tại ở một số wrapper định dạng, như `GZIPOutputStream` hoặc `ZipOutputStream`, nhằm hoàn tất cấu trúc dữ liệu đã tạo **mà không đóng underlying stream**, theo hợp đồng implementation. Nó không có trong `OutputStream` chung.

**`close()`** kết thúc vòng đời của resource/wrapper; wrapper ngoài thường flush/finish phần còn lại rồi đóng delegate.

Ví dụ về GZIP:

```java
// Đoạn minh họa, output do caller sở hữu, GZIP wrapper là cục bộ.
GZIPOutputStream gzip = new GZIPOutputStream(output);
gzip.write(payload);
gzip.finish(); // Hoàn tất dữ liệu GZIP.
gzip.flush();  // Nếu cần đẩy dữ liệu xuống output.
                // Không gọi gzip.close() nếu phải giữ output mở.
```

Đây là **đoạn minh họa**, cần `GZIPOutputStream`, `OutputStream output`, `byte[] payload` và xử lý `IOException`. `finish()` có thể hoàn tất GZIP member mà không đóng delegate, nhưng thiết kế cần xác định có dùng wrapper tiếp không và ai giải phóng wrapper. Không nên áp dụng tùy tiện cách này cho mọi định dạng; wrapper khác có thể **không có `finish()`** hoặc cần close để hoàn tất.

**Lưu ý:** ngay cả khi giữ underlying output mở, dữ liệu có thể chưa hiển thị tại đích cho đến khi flush. Ngược lại, flush không bảo đảm tính bền vững trên đĩa; một yêu cầu thật sự về durability cần cơ chế đồng bộ file thích hợp.

## 13. Trả stream từ một factory: chuyển quyền sở hữu cho caller

Một helper có thể tạo và trả lại luồng để code gọi dùng:

```java
static BufferedReader openUtf8Reader(Path path) throws IOException {
    return new BufferedReader(
            new InputStreamReader(
                    Files.newInputStream(path), StandardCharsets.UTF_8));
}
```

Đây là **phương thức minh họa**, cần import tương ứng. Nó mở luồng file và trả wrapper ngoài. Vì factory **chuyển quyền sở hữu qua giá trị trả về**, caller chịu trách nhiệm đóng:

```java
try (BufferedReader reader = openUtf8Reader(path)) {
    // Dùng reader.
}
```

Nếu caller quên đóng thì luồng file có thể bị rò rỉ. Trái lại, **không nên** làm:

```java
// Mã minh họa sai:
static BufferedReader brokenFactory(Path path) throws IOException {
    try (BufferedReader reader = openUtf8Reader(path)) {
        return reader; // Trả một reader đã bị đóng khi rời try.
    }
}
```

Ví dụ này thể hiện một lỗi vòng đời: trả đối tượng còn tham chiếu nhưng tài nguyên đã đóng. Nếu muốn đảm bảo caller không cần đóng, đừng trả về resource sống; thay vào đó có thể đọc hết dữ liệu trong phạm vi có giới hạn rồi trả một **giá trị bất biến** hoặc giá trị sở hữu dữ liệu, chấp nhận đánh đổi về bộ nhớ.

### Cách tránh nhầm quyền sở hữu trong API

Có thể đặt tên làm rõ ý nghĩa như `openReader()`, `withReader(...)` hoặc ghi Javadoc:

```java
/**
 * Reads records from a borrowed InputStream.
 * This method does not close the supplied stream.
 */
static void parse(InputStream borrowed) throws IOException {
    // ...
}
```

Đây là **khung tài liệu API**, thân phương thức được lược bỏ để minh họa hợp đồng. Nếu một API thực sự đóng stream truyền vào, ghi rõ “takes ownership and closes the stream” và xác định hành vi khi lỗi. Đừng chỉ dựa vào tên phương thức để người gọi đoán.

## 14. Thiết kế API bằng callback để đóng tài nguyên đúng phạm vi

Trong một số trường hợp, ta không cần trả resource sống cho caller. Có thể sở hữu việc mở/đóng ngay tại biên và nhận callback xử lý:

```java
@FunctionalInterface
interface ReaderAction<T> {
    T apply(BufferedReader reader) throws IOException;
}

static <T> T withUtf8Reader(Path path, ReaderAction<T> action)
        throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(
            path, StandardCharsets.UTF_8)) {
        return action.apply(reader);
    }
}
```

Đây là **đoạn minh họa**, cần import `BufferedReader`, `IOException`, `Files`, `Path`, `StandardCharsets`. Phương thức `withUtf8Reader` sở hữu stream và đảm bảo close trước khi trả kết quả. Callback chỉ **mượn reader trong phạm vi chạy**, không nên giữ tham chiếu rồi dùng sau khi callback kết thúc.

Ví dụ ngữ nghĩa:

```java
long count = withUtf8Reader(path, reader ->
        reader.lines().count());
```

Với `BufferedReader.lines()`, stream dòng phụ thuộc reader bên dưới; terminal operation `count()` thực thi **trong callback** nên khi callback kết thúc, toàn bộ việc đọc đã xong trước lúc reader đóng. Tránh trả `Stream<String>` lazy từ callback rồi mong đọc sau, vì reader lúc đó đã đóng.

Mẫu “with resource” giúp ràng buộc vòng đời trong API, nhưng chỉ phù hợp với xử lý đồng bộ trong phạm vi callback. Với tác vụ bất đồng bộ, cần mô hình quản lý ownership và completion phù hợp.

## 15. Stream<String> từ Files.lines và vấn đề đóng tài nguyên gián tiếp

Tên `Stream` trong Java có thể chỉ:

1. **I/O streams** trong `java.io`, ví dụ `InputStream`/`OutputStream`.
2. **Stream API** trong `java.util.stream`, ví dụ `Stream<String>`.

Hai khái niệm khác nhau. Tuy nhiên một số Stream API **được liên kết với resource I/O**:

```java
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(s -> !s.isBlank()).count();
    System.out.println(count);
}
```

Đây là **đoạn minh họa**, cần import `java.util.stream.Stream`, `java.nio.file.Files`, `Path`, `StandardCharsets`, xử lý `IOException`. `Files.lines` mở resource liên quan đến tệp và trả một stream lazy có `onClose` thích hợp. **Terminal operation như `count()` không mặc định đóng Stream API**; `try-with-resources` mới bảo đảm close khi xong.

Ngược lại, không phải mọi `Stream<T>` đều có tài nguyên hệ điều hành cần đóng, ví dụ `List.of("a", "b").stream()`. Đừng hiểu lầm rằng mọi đối tượng Stream API đều giống `FileInputStream`; cần biết nó được tạo từ đâu và quy định đóng của API tương ứng.

## 16. Nếu thực sự cần chia sẻ một stream cho nhiều consumer

Có thể thiết kế một lớp owner duy nhất, mọi consumer nhận một **giao diện hẹp** thay vì quyền truy cập đến `close()`.

Ví dụ khái niệm:

```java
interface MessageSink {
    void send(String message) throws IOException;
}
```

Chủ sở hữu tạo một `OutputStream` và cung cấp `MessageSink` cho các consumer. Chỉ chủ sở hữu giữ quyền đóng output. Interface không hề công bố phương thức `close()` nên giảm khả năng consumer tự đóng tài nguyên. Owner có thể đảm bảo đồng bộ, framing và flush trong một chỗ.

Với tài nguyên có nhiều người dùng bất đồng bộ, cần cơ chế biết khi nào người dùng cuối cùng đã xong: ví dụ lifecycle scope, reference counting được thiết kế cẩn thận, hoặc cơ chế shutdown của ứng dụng. **Không được đoán rằng một thread kết thúc có nghĩa không thread nào còn dùng stream**.

Nếu API buộc phải nhận một `Closeable` nhưng consumer không được đóng delegate, cân nhắc non-closing wrapper ở biên hoặc hợp đồng borrowed rõ ràng. Non-closing wrapper chỉ bảo vệ hành động close đi qua wrapper, **không bảo vệ chống ghi/đọc sai thứ tự**.

## 17. Những lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| `try (BufferedReader r = ... System.in ...)` trong từng hàm | Đóng stdin sau khi hàm xong, code sau không đọc được | Caller/app sở hữu stdin; giữ wrapper dùng chung hoặc không đóng khi chỉ mượn |
| `try (BufferedOutputStream b = new BufferedOutputStream(callerOut))` | Đóng output của caller ngoài ý muốn | Truyền wrapper từ caller hoặc dùng non-closing delegate/flush phù hợp |
| Mỗi parser tự tạo `BufferedReader` trên cùng input | Buffer có thể đọc trước dữ liệu dành cho parser khác | Dùng một wrapper phối hợp chung hoặc thiết kế framing rõ ràng |
| Đặt cả `raw` và wrapper vào try mà không suy nghĩ | Có thể gọi close lặp với delegate | Hiểu chuỗi ownership và hành vi close của từng lớp |
| Trả reader từ trong `try-with-resources` | Trả đối tượng đã đóng | Factory chuyển ownership, caller đóng |
| Quên đóng stream được factory trả về | Rò rỉ file/socket hoặc tài nguyên liên quan | Caller dùng `try-with-resources` |
| `close()` trong `finally` che lỗi ở thân try | Mất dấu nguyên nhân chính | Dùng `try-with-resources`, xem suppressed |
| Coi `flush()` thay cho `close()` ở GZIP | Thiếu trailer/dữ liệu định dạng cuối | Dùng `finish()`/ `close()` theo API |
| Đóng một resource chia sẻ trong một worker | Consumer khác bị lỗi | Owner cấp cao quyết định thời điểm đóng |
| Cho rằng một `ByteArrayOutputStream` vẫn dùng được sau close thì file cũng vậy | Unit test che mất lỗi lifecycle | Test bằng tracking stream/fake close |
| Dùng `PrintWriter.println` mà nghĩ sẽ nhận checked `IOException` | Lỗi ghi có thể bị ghi nhận bên trong | Xem `checkError()` hoặc chọn API báo lỗi rõ |
| Đóng Scanner trên `System.in` dù còn chức năng nhập khác | Stdin đóng theo Scanner | Giữ scanner trong vòng đời ứng dụng hoặc ghi rõ ownership |
| Đọc các dòng từ `Files.lines` mà không close | Resource file có thể giữ mở | `try (Stream<String> lines = Files.lines(...))` |
| Trả Stream API lazy phụ thuộc reader đã đóng | Lỗi khi dùng ở ngoài scope | Thực thi terminal operation trong scope hoặc chuyển quyền sở hữu rõ |
| Nhiều thread cùng dùng output và không ai đóng | Vẫn có thể xen kẽ byte và hỏng protocol | Điều phối thứ tự/đồng bộ, framing; close sau khi các tác vụ xong |

## 18. Checklist khi viết hoặc review một API nhận stream

Trước khi quyết định `try-with-resources`, xác định:

1. **Nguồn gốc:** stream được hàm mở, caller truyền vào hay lấy từ singleton/global?
2. **Chủ sở hữu:** thành phần nào có quyền kết thúc resource thật?
3. **Wrapper:** đóng wrapper nào sẽ đóng delegate nào? Có ngoại lệ như memory stream?
4. **Người dùng sau đó:** có hàm, task hoặc thread nào còn cần stream sau khi thao tác hiện tại kết thúc?
5. **Buffer và vị trí:** wrapper có đọc trước, giữ byte/ký tự chưa xử lý, hoặc ghi đệm chưa flush?
6. **Giao thức kết thúc:** format có yêu cầu `finish()`, footer/trailer hoặc stateful encoder trước khi đóng không?
7. **Lỗi:** lỗi close có cần được báo ra? Nếu nhiều lỗi, suppressed exception được giữ thế nào?
8. **API contract:** Javadoc có nêu borrowed/takes ownership/returns owned closeable không?
9. **Bằng chứng kiểm thử:** có test stream theo dõi close, lỗi giả lập và trường hợp dùng tiếp sau khi hàm trả về?
10. **Cấu trúc thực thi:** dùng đồng bộ hay bất đồng bộ; ai bảo đảm resource còn sống đến cuối tác vụ?

Nếu hàm chỉ cần thực hiện một phép biến đổi ngắn trên stream do caller truyền vào, hợp đồng **mượn và không đóng** thường hợp lý. Nếu hàm tự mở stream từ tệp, `try-with-resources` thường là cách an toàn nhất. Nếu luồng được trả từ factory, hãy ghi rõ caller là owner.

## 19. Bài tập thực hành

1. Chạy `WrapperCloseDemo`; giải thích vì sao trước khi đóng số byte bằng 0 và sau khi đóng nội dung trở thành `ABC`.
2. Thay `ByteArrayOutputStream` trong ví dụ bằng file stream tự tạo. Quan sát tác động của `close()` và vì sao không nên tiếp tục ghi sau close.
3. Trong `BorrowedStreamDemo`, thay `writePart` để tự đóng output, rồi dùng tracking stream phát hiện vi phạm ownership (không dựa vào việc `ByteArrayOutputStream` có thể ghi sau close).
4. Chạy `NonClosingWrapperDemo`; bỏ override `close()` của `NonClosingOutputStream` để xem khác biệt về số lần đóng delegate.
5. Chạy `SuppressedCloseDemo`; lần lượt bỏ lỗi từ thân try và bỏ lỗi từ `close()`. Xác định exception nào trở thành lỗi chính.
6. Viết một hàm `copy(InputStream, OutputStream)` nhận hai stream borrowed, không đóng, chỉ ghi `count` byte đọc thực tế. Dùng hai fixture có cờ `closed` để đảm bảo caller vẫn dùng tiếp được.
7. Tạo hai `BufferedReader` trên cùng `InputStream` chứa nhiều dòng và lý giải vì sao đọc trước khiến chia sẻ hai reader trở nên khó kiểm soát. Thiết kế lại để chỉ có một reader owner.
8. Viết factory `openUtf8Reader` rồi sử dụng bằng `try-with-resources`; thêm trường hợp mở tệp không tồn tại và kiểm tra không để resource bị treo.
9. Dùng `Files.lines` với một tệp nhỏ và `try-with-resources`, sau đó viết một callback `withUtf8Reader` thực hiện đọc trong phạm vi còn mở.
10. Thiết kế Javadoc cho hai phương thức: một phương thức **borrows an OutputStream**, phương thức còn lại **takes ownership**. Làm rõ hành vi khi ném `IOException`.
11. Mô tả cách xử lý khi một task bất đồng bộ đang ghi nhưng ứng dụng nhận yêu cầu shutdown: ai chờ hoàn tất, ai flush/close, và làm sao tránh đóng giữa message.
12. Với một output stream do caller sở hữu và định dạng GZIP cần hoàn tất, chọn giữa `finish()`, non-closing wrapper và việc chuyển quyền sở hữu; giải thích hợp đồng được chọn.

## 20. Tổng kết

Quản lý tài nguyên trong Java I/O cần đồng thời hiểu **vòng đời thực của stream**, **quan hệ wrapper–delegate** và **hợp đồng quyền sở hữu**.

- **Tự mở và sở hữu:** dùng `try-with-resources` để đóng đúng lúc; với wrapper chain, thường đóng lớp ngoài là đủ.
- **Được truyền vào để mượn:** không tự đóng delegate; chú ý wrapper có thể chuyển tiếp `close()`, buffering có thể đọc trước, và việc flush/finish cần quy ước.
- **Dùng chung:** một owner/coordinator quyết định shutdown; không để consumer tùy tiện đóng `System.in/out/err`, socket hoặc stream chung.
- **Trả resource sống:** caller nhận quyền sở hữu và trách nhiệm đóng; đừng trả stream đã bị đóng trong try.
- **Khi xử lý thất bại:** `try-with-resources` giữ lỗi chính và suppressed exceptions để chẩn đoán; đừng che lỗi.
- **Kiểm thử ownership:** dùng tracking stream để chứng minh phương thức mượn không đóng, wrapper đóng đúng delegate và caller còn dùng được sau khi hàm trả về.

**Câu hỏi quan trọng nhất mỗi khi viết `close()`: “Tôi có thực sự sở hữu tài nguyên này không, và có người khác còn cần nó sau đây không?”**

### Tài liệu tham khảo

- Java SE 17: [`AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html), [`Closeable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html), [`InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html), [`OutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html).
- Java SE 17: [`BufferedInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html), [`BufferedOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html), [`InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html), [`OutputStreamWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html).
- Java SE 17: [`Scanner`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html), [`PrintWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html), [`Files.lines`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html), [`GZIPOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPOutputStream.html).
