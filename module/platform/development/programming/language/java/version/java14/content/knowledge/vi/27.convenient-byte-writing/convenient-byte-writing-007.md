# Quyền đóng `PrintStream` khi bọc một luồng dùng chung — viết byte và quản lý vòng đời tài nguyên

## 1. Mục tiêu

Từ Java 14, `java.io.PrintStream` có phương thức tiện dụng:

```java
void writeBytes(byte[] buf)
```

Phương thức này ghi **toàn bộ mảng byte** vào `PrintStream` mà không yêu cầu caller bắt checked `IOException`. Đây là API **vẫn còn được hỗ trợ** trên các JDK hiện hành. Nhưng tính tiện dụng của thao tác ghi **không thay đổi quyền sở hữu tài nguyên**: một `PrintStream` thường **bọc một `OutputStream` bên dưới**, và gọi `PrintStream.close()` sẽ **flush rồi đóng luôn OutputStream đó**.

Nếu `OutputStream` được **dùng chung** bởi nhiều thành phần — chẳng hạn `System.out`, luồng ghi của socket, output của server hoặc một luồng do caller truyền vào — việc đóng wrapper có thể làm **những thành phần khác mất khả năng ghi**.

Ví dụ ngắn về lỗi cần tránh:

```java
// Không làm điều này nếu code của bạn KHÔNG sở hữu System.out:
try (PrintStream temporary = new PrintStream(
        System.out, true, StandardCharsets.UTF_8)) {
    temporary.writeBytes("Hello".getBytes(StandardCharsets.UTF_8));
}
// temporary.close() đã được gọi tự động,
// và close() đóng cả System.out mà nó bọc.
```

Đoạn trên minh họa nguy cơ; không nên thực thi trực tiếp trong chương trình cần tiếp tục dùng console. Bài sẽ giải thích **ai có quyền đóng gì**, chỉ ra cách quản lý tài nguyên an toàn và đưa ra một chương trình Java 17+ đã biên dịch/chạy được để kiểm chứng.

**Sau bài học, bạn có thể:**

- Phân biệt luồng **owned** (do mình tạo và sở hữu) và **borrowed/shared** (được cho mượn hoặc dùng chung).
- Hiểu chính xác quan hệ giữa `PrintStream.close()`, `flush()` và `OutputStream.close()`.
- Sử dụng `writeBytes(byte[])` (từ Java 14) mà không vô tình đóng luồng của caller.
- Áp dụng `try-with-resources` cho tài nguyên thực sự sở hữu và dùng **non-closing adapter** khi cần tạo wrapper tạm quanh luồng mượn.
- Nhận biết giới hạn của `checkError()`, `autoFlush`, byte encoding và việc ghi đồng thời.
- Thiết kế API Java với hợp đồng sở hữu tài nguyên rõ ràng, có test chứng minh dữ liệu vẫn ghi được sau khi wrapper kết thúc.

## 2. Cốt lõi: sở hữu luồng khác với có tham chiếu tới luồng

Một method nhận `OutputStream` làm tham số không mặc nhiên là chủ sở hữu của nó:

```java
void renderReport(OutputStream destination) {
    // destination có thể do caller, server hoặc framework sở hữu.
}
```

Hợp đồng API cần nói rõ: method **chỉ ghi/flush** hay method **chịu trách nhiệm close**? Đây là một lựa chọn thiết kế của ứng dụng, **không được suy ra từ việc tham số có kiểu `OutputStream`**.

### 2.1. Bốn tình huống sở hữu thường gặp

| Nguồn luồng | Ai thường sở hữu? | Caller có nên đóng sau khi ghi? |
| --- | --- | --- |
| `Files.newOutputStream(path)` do chính method mở | Method tạo ra nó | **Có**, thường bằng `try-with-resources` |
| `OutputStream` được truyền vào method dưới dạng borrowed | Caller / thành phần bên ngoài | **Không**, trừ khi hợp đồng chuyển quyền sở hữu |
| `System.out` hoặc `System.err` | Môi trường ứng dụng/JVM, dùng chung | **Không** trong thư viện/helper thông thường |
| Socket output stream hoặc servlet response output do framework quản lý | Chủ socket/response hoặc framework | **Tuân theo lifecycle chính thức**; helper không tự ý đóng |

**Nguyên tắc thực tế:** bên **tạo hoặc được chuyển giao quyền sở hữu** tài nguyên có trách nhiệm đóng nó. Bên chỉ **mượn** luồng nên ghi và (nếu được phép) flush, nhưng không kết thúc tài nguyên của người khác.

Quy tắc này là **hợp đồng ứng dụng**, không phải một thuộc tính runtime của Java: `PrintStream` không có một flag “borrowed” để tự biết phải giữ luồng bên dưới mở.

### 2.2. Sơ đồ một wrapper và một luồng dùng chung

```text
                        ┌── Component A ── ghi bằng PrintStream A
Shared OutputStream ────┤
                        └── Component B ── ghi trực tiếp / PrintStream B

Nếu A gọi close():
    PrintStream A.close()
        ├── flush()
        └── sharedOutputStream.close()

Hậu quả: B có thể không thể ghi tiếp dù B không yêu cầu close.
```

Khi có nhiều wrappers, **đóng wrapper A không chỉ đóng A**, mà theo hợp đồng `PrintStream.close()` còn đóng **luồng nằm dưới**. Một luồng đã đóng có thể ném `IOException` khi B ghi, hoặc một wrapper kiểu `PrintStream` khác có thể chỉ đánh dấu lỗi nội bộ.

**Ngoại lệ cần nhớ:** một số implementation như `ByteArrayOutputStream.close()` không làm mất khả năng tiếp tục ghi. Chính vì thế việc chỉ thử với `ByteArrayOutputStream` có thể **che giấu bug sở hữu**; bài kiểm thử nên dùng một `OutputStream` thực sự từ chối ghi sau `close()`.

## 3. Ngữ nghĩa hiện hành của `PrintStream.close()`

Theo Javadoc, `PrintStream.close()` có hợp đồng:

1. Flush output còn được đệm của print stream.
2. Gọi `close()` trên **underlying output stream**.
3. Kết thúc vòng đời wrapper; các thao tác ghi tiếp theo không còn đáng tin và có thể khiến trạng thái lỗi được thiết lập.

```java
PrintStream view = new PrintStream(shared);
view.close(); // KHÔNG chỉ đóng "view"; cũng đóng shared.
```

Đoạn là ví dụ trừu tượng, với biến `shared` kiểu `OutputStream`. Để sử dụng `new PrintStream(shared)` cần `import java.io.PrintStream;`. Đây là hành vi documented, **không** phải chi tiết implementation tùy JDK.

### 3.1. `close()` khác `flush()`

| Thao tác | Ảnh hưởng wrapper | Ảnh hưởng underlying stream | Có nghĩa “hoàn tất quyền sở hữu” không? |
| --- | --- | --- | --- |
| `print/println/writeBytes` | Ghi nội dung | Chuyển byte xuống tầng dưới | Không |
| `flush()` | Đẩy dữ liệu còn chờ | Gọi `flush()` trên luồng bên dưới | **Không đóng** |
| `close()` | Đóng wrapper | Flush **và đóng underlying stream** | **Có**, kể cả khi caller không sở hữu |
| `checkError()` | Xem lỗi I/O đã ghi nhận | Có thể flush nếu chưa đóng | Không phải thao tác đóng |

Nếu chỉ cần đảm bảo dữ liệu đã được đẩy qua bộ đệm, `flush()` **không tương đương** `close()`. Ngược lại, `flush()` không bảo đảm dữ liệu đã được ghi bền vững tới thiết bị/lưu trữ; điều này phụ thuộc stream và OS.

### 3.2. `autoFlush=true` không bảo vệ luồng dùng chung khỏi `close()`

```java
new PrintStream(shared, true, StandardCharsets.UTF_8)
```

Tham số `autoFlush=true` yêu cầu tự flush trong những trường hợp Javadoc quy định: sau khi ghi **mảng byte**, gọi `println` hoặc ghi ký tự/byte newline tương ứng. Nó **không** có nghĩa wrapper sẽ tự tránh đóng luồng bên dưới, và **không** có nghĩa mọi lệnh `print` đều flush ngay lập tức trong mọi trường hợp.

Với `writeBytes(buf)`, `autoFlush=true` cũng kích hoạt flush sau khi ghi mảng byte. Dùng `flush()` một cách có chủ đích khi cần, thay vì nhầm autoFlush với quyền ownership.

### 3.3. Các method của `PrintStream` và checked `IOException`

`PrintStream` được thiết kế để các hoạt động ghi thường **không ném checked `IOException`**; lỗi I/O thường được lưu ở trạng thái bên trong để xem bằng `checkError()`.

Đặc biệt:

- `writeBytes(byte[])`: không khai báo `throws IOException`, có từ **Java 14**.
- `write(byte[], int, int)`: cũng không buộc caller bắt `IOException`.
- `write(byte[])`: do chữ ký override vẫn **khai báo `throws IOException`**, mặc dù Javadoc của `PrintStream` giải thích implementation không thực sự ném `IOException` khi ghi mà đặt error flag; nếu muốn không phải catch checked exception, dùng `writeBytes(buf)` hoặc `write(buf, 0, buf.length)`.
- `close()` của `PrintStream` không bắt caller khai báo `IOException`; nếu underlying stream thất bại khi đóng, tình trạng I/O có thể được biểu diễn bằng trạng thái lỗi.

**Hệ quả:** thao tác ghi bị lỗi trên `PrintStream` không nhất thiết làm chương trình ném exception ngay. Với ghi dữ liệu có yêu cầu nghiêm ngặt về độ tin cậy, phải kiểm tra `checkError()` hoặc dùng trực tiếp `OutputStream`/API có cơ chế báo lỗi tường minh phù hợp.

## 4. `writeBytes(byte[])` trong bối cảnh chia sẻ output

`PrintStream.writeBytes(byte[] buf)` ghi **toàn bộ các byte nguyên trạng**. Theo Javadoc, nó tương đương:

```java
printStream.write(buf, 0, buf.length);
```

Chữ ký của `writeBytes`:

```java
public void writeBytes(byte[] buf)
```

Mặc dù API bổ sung ở Java 14, vấn đề đóng underlying stream **không phải tính năng mới**: `PrintStream.close()` từ trước đã đóng stream bên dưới. Việc có thêm phương thức ghi byte tiện dụng **không thay đổi vòng đời wrapper**.

Ví dụ ghi ba byte ASCII:

```java
byte[] bytes = {65, 66, 67};
printStream.writeBytes(bytes); // Các byte 0x41 0x42 0x43: "ABC" theo ASCII.
```

Đây là **trích đoạn** với biến `printStream` đã có. Phương thức **không tự thêm dấu xuống dòng**, khác `println("ABC")`. Nội dung byte được giữ nguyên; không tự mã hóa lại theo charset của `PrintStream`.

### 4.1. Phân biệt `writeBytes` với `print(String)`

```java
byte[] utf8 = "Xin chào".getBytes(StandardCharsets.UTF_8);

stream.writeBytes(utf8); // Ghi đúng byte UTF-8 đã mã hóa.
stream.print("Xin chào"); // Mã hóa text bằng charset của PrintStream.
```

Đoạn minh họa yêu cầu `stream` kiểu `PrintStream` và import `StandardCharsets`. Kết quả trên raw bytes có thể khác ý nghĩa của text tuỳ charset/protocol của luồng đích.

Nếu ghi **giao thức binary**, `writeBytes` thường thích hợp với byte array đã được tạo chính xác. Nếu ghi **text**, hãy chọn charset tường minh, ví dụ `StandardCharsets.UTF_8`, để tránh kết quả phụ thuộc môi trường. Không nên trộn binary và text tùy tiện trên cùng shared stream nếu các component có giả định định dạng khác nhau.

**Lưu ý:** `PrintStream.writeBytes` không tự cấp quyền đóng, mở/đóng socket, giữ lock hay đồng bộ vòng đời. Quyền sở hữu phải được quyết định **bên ngoài thao tác ghi**.

## 5. Sai lầm với `try-with-resources` trên luồng mượn

`PrintStream` là `AutoCloseable`. Vì vậy:

```java
try (PrintStream view = new PrintStream(
        shared, true, StandardCharsets.UTF_8)) {
    view.writeBytes(bytes);
} // Tự gọi view.close() → đóng shared.
```

`try-with-resources` hoạt động **đúng theo đặc tả Java**: nó gọi `close()` khi rời block. **Bug không nằm ở try-with-resources**, mà nằm ở việc bạn đặt **wrapper đang đóng một borrowed resource** vào một scope quản lý vòng đời như thể nó sở hữu resource.

### 5.1. Trường hợp owned: dùng try-with-resources là đúng

Nếu method **tự mở file** và có toàn quyền đóng:

```java
Path path = Path.of("report.bin");

try (PrintStream out = new PrintStream(
        Files.newOutputStream(path), false, StandardCharsets.UTF_8)) {
    out.writeBytes(new byte[] {1, 2, 3, 4});
    if (out.checkError()) {
        throw new IllegalStateException("Failed to write report bytes");
    }
} // Đóng PrintStream và cả file OutputStream do method tạo.
```

Đây là **trích đoạn** cần được đặt trong method có `throws IOException` hoặc xử lý IOException ở bước `Files.newOutputStream`, đồng thời import `Path`, `Files`, `PrintStream`, `StandardCharsets`. Dòng `new PrintStream(Files.newOutputStream(...))` chuyển quyền đóng của file stream vừa tạo cho wrapper.

**Nhận xét thiết kế:** nếu đang ghi binary file và muốn `IOException` trực tiếp, cách đơn giản hơn là:

```java
try (OutputStream out = Files.newOutputStream(path)) {
    out.write(new byte[] {1, 2, 3, 4});
}
```

Dùng `OutputStream` trực tiếp rất phù hợp khi không cần `print/printf` hoặc `PrintStream.writeBytes`. Tùy mục tiêu, `Files.write(path, bytes)` còn ngắn gọn hơn. `PrintStream` có tiện ích formatting, nhưng cách báo lỗi khác nên cần hiểu rõ.

### 5.2. Trường hợp borrowed: không tự ý close

Ví dụ một API được truyền luồng từ caller:

```java
static void writeHeader(OutputStream borrowed) throws IOException {
    borrowed.write(new byte[] {0x48, 0x44, 0x52});
    borrowed.flush(); // Chỉ flush nếu hợp đồng cho phép.
    // Không gọi borrowed.close().
}
```

Đây là method độc lập trong một class phù hợp, với imports `OutputStream` và `IOException`. Khi không cần PrintStream, **trực tiếp dùng OutputStream là thiết kế đơn giản nhất**: không tạo wrapper cần quản lý thêm.

Nếu method **bắt buộc phải dùng PrintStream** để in giá trị, có các lựa chọn an toàn được trình bày tiếp.

## 6. Giải pháp đơn giản nhất: tái sử dụng `PrintStream` có sẵn

Nếu caller đã cung cấp `PrintStream`, **không tạo thêm wrapper** khi không cần:

```java
static void writeStatus(PrintStream borrowed, byte[] bytes) {
    borrowed.writeBytes(bytes);
    borrowed.flush();
    // Caller vẫn sở hữu PrintStream; method này không close().
}
```

Caller có thể gọi:

```java
writeStatus(System.out, "Ready".getBytes(StandardCharsets.UTF_8));
```

Không có `new PrintStream(System.out)`, không có `try-with-resources` cho borrowed stream, và quyền đóng vẫn ở nơi sở hữu `System.out`.

**Với thư viện tiện ích:** nhận trực tiếp kiểu `PrintStream` nếu ứng dụng luôn dùng `PrintStream`, hoặc nhận `OutputStream` và ghi bytes bằng OutputStream API. Việc chỉ tạo thêm wrapper để gọi `writeBytes` thường không đem lại lợi ích tương xứng với rủi ro.

## 7. Giải pháp khi phải đóng wrapper nhưng giữ shared stream: non-closing adapter

Nếu API cần một `PrintStream` **tạm thời** vì phải sử dụng `print`/`printf`/`writeBytes`, ta có thể bọc borrowed stream bằng một adapter **không chuyển tiếp `close()`**.

Ý tưởng:

```text
PrintStream (do helper tạo, được phép close)
    |
    v
NonClosingOutputStream (close() chỉ flush)
    |
    v
Shared OutputStream (caller sở hữu, vẫn mở)
```

Một adapter gọn:

```java
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;

final class NonClosingOutputStream extends FilterOutputStream {
    NonClosingOutputStream(OutputStream shared) {
        super(shared);
    }

    @Override
    public void close() throws IOException {
        flush(); // KHÔNG gọi super.close() hoặc out.close().
    }
}
```

Vì `FilterOutputStream` thông thường có `close()` đóng underlying stream, **phải override** `close()` như trên. Adapter vẫn cho phép `flush()` truyền xuống luồng dùng chung nhưng **không chuyển tiếp close**.

Dùng adapter:

```java
static void writeWithTemporaryPrintStream(OutputStream shared) {
    try (PrintStream view = new PrintStream(
            new NonClosingOutputStream(shared),
            true, StandardCharsets.UTF_8)) {
        view.writeBytes("payload".getBytes(StandardCharsets.UTF_8));
        if (view.checkError()) {
            throw new IllegalStateException("Could not write payload");
        }
    }
    // view đã đóng; shared do caller sở hữu vẫn mở.
}
```

Đây là ví dụ có thể đặt trong class có định nghĩa `NonClosingOutputStream` cùng các imports phù hợp. `PrintStream.close()` vẫn đóng **đối tượng adapter** theo contract của nó; adapter giữ việc close không đi xuống **shared**. Điều đó làm hợp đồng sở hữu của helper rõ ràng.

### 7.1. Adapter không chuyển giao ownership

**Phải có chủ sở hữu thực sự** đóng `shared` khi vòng đời kết thúc. Non-closing adapter chỉ ngăn **bên mượn đóng quá sớm**, không thay thế nhiệm vụ cleanup cuối cùng.

- Trong handler nhận socket, owner của socket/connection quản lý lúc kết thúc.
- Trong web response, framework quản lý lifecycle output.
- Với `System.out`, application/JVM quản lý trong vòng đời tiến trình.
- Với file stream được tạo ở caller, caller dùng `try-with-resources` để đóng sau khi các helper đã ghi xong.

### 7.2. Không gọi nhầm `super.close()`

Đoạn sau **không** phải close shield:

```java
@Override
public void close() throws IOException {
    super.close(); // FilterOutputStream.close() đóng underlying.
}
```

Muốn giữ shared stream mở thì implementation `close()` **không** được gọi `super.close()` hoặc `out.close()`. Trong adapter ở bài này, `flush()` là hành vi có chủ đích.

### 7.3. Tránh tạo API “close không làm gì” trên tài nguyên thật

Non-closing adapter nên được dùng **ở ranh giới borrowed resource**, không dùng để biến mọi stream thành “không bao giờ đóng”. Nếu chủ sở hữu đóng adapter thay vì đóng underlying stream, bạn có nguy cơ **rò rỉ file descriptor hoặc socket**.

Tên `NonClosingOutputStream` có ý nghĩa: nó chỉ là **view/adapter**, không phải output resource chính. Chủ sở hữu cần giữ tham chiếu tới stream thật để gọi `close()` đúng thời điểm.

## 8. Chương trình Java 17+ chạy được: chứng minh ownership, close shield và lỗi ghi

Ví dụ dưới đây chủ động tạo một `TrackedOutputStream` **từ chối mọi ghi sau khi đóng**. Cách này tránh một test sai lệch thường gặp: `ByteArrayOutputStream.close()` không vô hiệu hóa stream nên nếu chỉ kiểm thử trực tiếp bằng nó, ta có thể hiểu nhầm rằng `PrintStream.close()` không đóng underlying resource.

Chương trình thử ba trường hợp:

1. Bọc trực tiếp luồng dùng chung, sau đó đóng `PrintStream` → underlying bị đóng; ghi tiếp bị từ chối.
2. Bọc qua `NonClosingOutputStream`, đóng `PrintStream` → underlying vẫn mở; owner ghi tiếp và cuối cùng tự đóng.
3. Underlying stream mô phỏng lỗi `IOException` khi ghi → `PrintStream.writeBytes` không ném checked exception mà `checkError()` báo `true`.

Lưu toàn bộ mã thành **`PrintStreamOwnershipDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

public class PrintStreamOwnershipDemo {
    static final class TrackedOutputStream extends OutputStream {
        private final ByteArrayOutputStream data = new ByteArrayOutputStream();
        private boolean closed;

        @Override
        public void write(int b) throws IOException {
            ensureOpen();
            data.write(b);
        }

        @Override
        public void write(byte[] bytes, int off, int len)
                throws IOException {
            ensureOpen();
            data.write(bytes, off, len);
        }

        @Override
        public void flush() throws IOException {
            ensureOpen();
        }

        @Override
        public void close() {
            closed = true;
        }

        private void ensureOpen() throws IOException {
            if (closed) {
                throw new IOException("underlying stream is closed");
            }
        }

        String content() {
            return data.toString(StandardCharsets.UTF_8);
        }

        boolean isClosed() {
            return closed;
        }
    }

    static final class NonClosingOutputStream extends FilterOutputStream {
        NonClosingOutputStream(OutputStream shared) {
            super(shared);
        }

        @Override
        public void close() throws IOException {
            flush(); // Do not close out: ownership stays with caller.
        }
    }

    static final class FailingOutputStream extends OutputStream {
        @Override
        public void write(int b) throws IOException {
            throw new IOException("simulated write failure");
        }
    }

    public static void main(String[] args) throws IOException {
        TrackedOutputStream shared = new TrackedOutputStream();

        try (PrintStream view = new PrintStream(
                shared, true, StandardCharsets.UTF_8)) {
            view.writeBytes("A".getBytes(StandardCharsets.UTF_8));
        }

        boolean writeRejected = false;
        try {
            shared.write('X');
        } catch (IOException expected) {
            writeRejected = true;
        }

        System.out.println("directClosed=" + shared.isClosed());
        System.out.println("directBytes=" + shared.content());
        System.out.println("directWriteRejected=" + writeRejected);

        TrackedOutputStream shared2 = new TrackedOutputStream();

        try (PrintStream view = new PrintStream(
                new NonClosingOutputStream(shared2), true,
                StandardCharsets.UTF_8)) {
            view.writeBytes("B".getBytes(StandardCharsets.UTF_8));
        }

        shared2.write('C');

        System.out.println("shieldClosed=" + shared2.isClosed());
        System.out.println("shieldBytes=" + shared2.content());

        shared2.close();
        System.out.println("ownerClosed=" + shared2.isClosed());

        try (PrintStream failed = new PrintStream(
                new FailingOutputStream(), false,
                StandardCharsets.UTF_8)) {
            failed.writeBytes(new byte[] {65});
            System.out.println("writeErrorFlag=" + failed.checkError());
        }
    }
}
```

### 8.1. Biên dịch/chạy

Từ thư mục chứa file, dùng JDK 17+:

```bash
javac --release 17 PrintStreamOwnershipDemo.java
java PrintStreamOwnershipDemo
```

**Output đã kiểm chứng**:

```text
directClosed=true
directBytes=A
directWriteRejected=true
shieldClosed=false
shieldBytes=BC
ownerClosed=true
writeErrorFlag=true
```

### 8.2. Giải thích bảy dòng kết quả

| Dòng | Ý nghĩa |
| --- | --- |
| `directClosed=true` | Đóng `PrintStream` trực tiếp đã đóng `TrackedOutputStream` bên dưới |
| `directBytes=A` | Byte `A` đã ghi trước lúc đóng vẫn còn trong buffer quan sát |
| `directWriteRejected=true` | Gọi `shared.write('X')` sau khi bị đóng ném `IOException` |
| `shieldClosed=false` | Adapter `NonClosingOutputStream.close()` không chuyển tiếp close xuống shared |
| `shieldBytes=BC` | Wrapper ghi `B`, đóng wrapper; owner vẫn ghi tiếp `C` thành công |
| `ownerClosed=true` | Chính owner cuối cùng đóng luồng thật |
| `writeErrorFlag=true` | Lỗi `IOException` của underlying write được `PrintStream` phản ánh qua `checkError()` |

**Điểm cốt lõi:** chỉ khác việc bọc thêm adapter **không đóng underlying** mà `PrintStream` có thể dùng `try-with-resources` an toàn cho wrapper tạm thời, trong khi chủ sở hữu vẫn quản lý vòng đời resource thật.

### 8.3. Vì sao phải dùng `TrackedOutputStream`?

`ByteArrayOutputStream` là một trường hợp đặc biệt: theo hợp đồng hiện hành, `ByteArrayOutputStream.close()` **không có tác dụng**, có thể tiếp tục gọi các method sau khi close. Do đó ví dụ chỉ dựa trên `ByteArrayOutputStream` không tái hiện việc socket/file bị đóng và không chứng minh một wrapper đang giữ ownership đúng.

`TrackedOutputStream` dùng `ByteArrayOutputStream` **chỉ làm nơi giữ bytes**, đồng thời thêm biến `closed` và `ensureOpen()` để mô phỏng semantics “đã close thì từ chối ghi” của một stream thật. Khi test code nhiều wrappers, cách kiểm thử bằng một stream có thể theo dõi close giúp nhìn đúng nguy cơ.

### 8.4. Vì sao không đóng `System.out` trong demo?

Đóng `System.out` ngay trong phép thử có thể làm chính những dòng in trạng thái ở cuối chương trình **không còn hiển thị**. Do đó demo dùng stream giả lập. Trong ứng dụng thật, không bọc `System.out` bằng một `PrintStream` tạm rồi auto-close; sử dụng trực tiếp `System.out` hoặc non-closing adapter nếu thật sự cần.

## 9. Tình huống thực tế: `System.out` và `System.err`

### 9.1. Không đóng console stream trong helper

**Cách dễ gây lỗi**:

```java
static void printMessage(String text) {
    try (PrintStream out = new PrintStream(System.out)) {
        out.println(text);
    } // out.close() cũng đóng System.out.
}
```

Sau khi gọi, các phần khác của chương trình có thể không còn in console được. `System.setOut(...)` chỉ thay tham chiếu chuẩn, không hồi sinh một underlying stream đã bị đóng.

**Cách đúng, đơn giản**:

```java
static void printMessage(String text) {
    System.out.println(text); // Không đóng System.out.
}
```

Nếu method nhận `PrintStream` từ caller:

```java
static void report(PrintStream out, String message) {
    out.println(message);
    out.flush();
    // Không gọi out.close().
}
```

`report(System.out, "READY")` không chiếm ownership của `System.out`.

### 9.2. Cân nhắc khi bọc luồng chuẩn để đổi charset

Nếu thật sự cần một `PrintStream` với charset xác định quanh `System.out`, có thể dùng non-closing adapter:

```java
try (PrintStream utf8View = new PrintStream(
        new NonClosingOutputStream(System.out),
        true, StandardCharsets.UTF_8)) {
    utf8View.println("Xin chào");
}
```

Đoạn cần class `NonClosingOutputStream` trong mục 7 và imports tương ứng. Việc ghi UTF-8 **không bảo đảm terminal sẽ hiển thị đúng ký tự** nếu môi trường console đang dùng một cách diễn giải encoding khác. Cần thống nhất charset giữa ứng dụng và consumer.

Không nên tạo nhiều wrappers đồng thời với charset khác nhau cùng ghi vào một output text stream; dữ liệu có thể khó đọc hoặc bị xen kẽ.

## 10. Tình huống thực tế: socket và response output

### 10.1. Socket thuộc về owner của connection

Giả sử một hàm nhận `OutputStream` từ socket do tầng transport quản lý:

```java
static void sendHeader(OutputStream socketOut) throws IOException {
    byte[] header = "HDR".getBytes(StandardCharsets.US_ASCII);
    socketOut.write(header);
    socketOut.flush();
    // Không đóng socketOut vì caller quản lý connection.
}
```

Đây là một method standalone trong class có imports phù hợp. Nếu dùng `PrintStream` đóng trực tiếp trên `socketOut`, việc `close()` có thể kết thúc đầu ra của kết nối khi protocol vẫn cần gửi thêm dữ liệu.

**Cẩn trọng:** một socket output stream có thể gắn với lifetime của socket. Gọi `close()` lên stream ấy có thể đóng connection theo hợp đồng socket cụ thể. Không coi thao tác này chỉ là “đóng một view”. Hãy để chủ kết nối quyết định khi nào đóng hoặc half-close theo API protocol/transport.

### 10.2. Response output do framework quản lý

Với output stream của servlet hoặc framework web, owner thường là **container/framework**. Helper serialize nên ghi và return; **không tự ý close** trừ khi contract framework cho phép. Một hàm đóng output giữa chừng có thể ngăn middleware hoặc code phía sau tiếp tục gửi response.

Trường hợp này liên quan trực tiếp đến **quyền sở hữu**, chứ không chỉ đến `PrintStream`; quy tắc tương tự còn áp dụng khi dùng `Writer`, `BufferedOutputStream`, `OutputStreamWriter` hoặc các stream wrappers có close chain.

## 11. Rủi ro riêng khi nhiều wrappers chia sẻ một luồng

Giả sử A và B cùng bọc một stream:

```java
PrintStream a = new PrintStream(shared, true, StandardCharsets.UTF_8);
PrintStream b = new PrintStream(shared, true, StandardCharsets.UTF_8);
```

Đây là **trích đoạn** với `shared` kiểu `OutputStream`. Các nguy cơ:

1. **Close propagation**: `a.close()` đóng shared, khiến `b` có thể không ghi tiếp được.
2. **Buffering**: mỗi wrapper có trạng thái buffering riêng; flush một wrapper chưa chắc đã flush nội dung chờ của wrapper khác.
3. **Concurrency**: việc đồng bộ hóa trên từng đối tượng wrapper **không có nghĩa** các wrappers dùng chung một lock, nên output từ nhiều thread/print streams có thể xen kẽ.
4. **Encoding**: hai wrappers có charset khác nhau có thể làm output text không còn nhất quán.
5. **Error detection**: lỗi underlying stream có thể bị một wrapper biểu diễn bằng `checkError()`, trong khi caller chỉ nhìn thấy “không có exception”.

**Thiết kế bền vững hơn:** tạo **một chủ sở hữu luồng**, cung cấp một API xuất dữ liệu hoặc một writer được điều phối duy nhất, và quy định rõ khi nào flush/close. Nếu cần chia sẻ giữa threads, dùng cơ chế đồng bộ/queue phù hợp với protocol, đừng mặc định mỗi `PrintStream` riêng tự đảm bảo tính nguyên tử của toàn bộ message.

Non-closing adapter **giải quyết vấn đề close propagation**, nhưng **không tự giải quyết** concurrency, encoding hay memory/backpressure.

## 12. `checkError()` và báo cáo lỗi khi ghi

Theo Javadoc, `PrintStream` thường **không ném checked `IOException`** từ các phương thức ghi; thay vào đó nó đặt trạng thái lỗi. Ví dụ test:

```java
static final class FailingOutputStream extends OutputStream {
    @Override
    public void write(int b) throws IOException {
        throw new IOException("simulated write failure");
    }
}

try (PrintStream ps = new PrintStream(
        new FailingOutputStream(), false, StandardCharsets.UTF_8)) {
    ps.writeBytes(new byte[] {65});
    System.out.println("error=" + ps.checkError()); // true
}
```

Đoạn minh họa cũng có trong chương trình hoàn chỉnh, ở đó output là `writeErrorFlag=true`.

**Vì sao kiểm tra này quan trọng?** Nếu ghi log hoặc response nhưng PrintStream giấu checked IOException vào error flag, chương trình không nhất thiết nhận exception ngay tại lệnh `writeBytes`. Với dữ liệu quan trọng, hãy kiểm tra `checkError()` và quyết định retry/fail/rollback ở lớp ứng dụng thích hợp.

`checkError()` có thể flush stream nếu nó chưa đóng; đây là một hành vi quan sát kèm tác động I/O, không hoàn toàn là phép đọc biến không tác dụng phụ. Nó chỉ cho biết **trạng thái lỗi mà PrintStream biết**, không thay thế xác nhận end-to-end rằng peer đã nhận/ghi bền vững dữ liệu.

**Không dùng `checkError()` để suy ra ownership:** một stream chưa báo lỗi vẫn có thể bị đóng bởi component khác ngay sau đó; ngược lại lỗi I/O không nhất thiết do bị close, có thể do disk full, network hoặc underlying writer.

## 13. Thiết kế API để ownership không bị hiểu nhầm

### 13.1. Ghi hợp đồng rõ trong method docs

Ví dụ JavaDoc cho API mượn:

```java
/**
 * Writes a record to the supplied destination.
 * The caller retains ownership of destination;
 * this method does not close it.
 */
static void writeRecord(OutputStream destination, byte[] record)
        throws IOException {
    destination.write(record);
}
```

**Tốt ở chỗ:** caller biết method **không đóng** stream. Nếu muốn flush, ghi rõ hợp đồng flush vì việc flush shared stream có thể tác động đến dữ liệu của caller khác.

API chuyển quyền sở hữu nên đặt tên/documentation tường minh:

```java
/**
 * Writes records and closes the stream supplied to this method.
 * Ownership is transferred for the duration of this call.
 */
static void writeAndCloseOwned(OutputStream owned, byte[] record)
        throws IOException {
    try (OutputStream output = owned) {
        output.write(record);
    }
}
```

Đây là API minh họa **thực sự close tham số**. Không dùng kiểu này nếu `owned` là `System.out` hoặc một stream do caller vẫn cần dùng.

### 13.2. Chọn trách nhiệm của helper theo tầng

Một helper để **định dạng bytes** không cần quyết định đóng kết nối. Một tầng quản lý **connection/file lifetime** mới nên sở hữu close. Cách tách trách nhiệm:

```text
Owner:
  - Tạo OutputStream
  - Quy định vòng đời
  - Đóng OutputStream ở cuối

Helper:
  - Nhận borrowed OutputStream hoặc PrintStream
  - Ghi phần được giao
  - Flush khi contract cho phép
  - Không close underlying resource

Optional adapter:
  - Ngăn helper/wrapper đóng shared quá sớm
  - Owner vẫn giữ tham chiếu đến resource thật
```

Cấu trúc này giảm lỗi khi thay transport (file, socket, HTTP response, console) mà không cần sửa mọi helper.

## 14. Các lỗi phổ biến và cách sửa

| Lỗi | Tại sao sai? | Cách sửa |
| --- | --- | --- |
| `try (PrintStream ps = new PrintStream(System.out))` | Đóng wrapper sẽ đóng output dùng chung | Dùng `System.out` trực tiếp; không tự close |
| Helper nhận `OutputStream` rồi tự ý tạo/đóng `PrintStream` | Helper chiếm ownership không có hợp đồng | Tránh wrapper; hoặc dùng non-closing adapter |
| Adapter gọi `super.close()` | `FilterOutputStream.close()` đóng underlying | Override `close()` chỉ flush theo thiết kế |
| Chỉ test với `ByteArrayOutputStream` | `close()` của nó không vô hiệu hóa ghi | Dùng tracked stream thật sự reject after close |
| Bỏ `checkError()` cho luồng quan trọng | PrintStream có thể chỉ đặt error flag | Kiểm tra lỗi; cân nhắc OutputStream API |
| Hiểu `autoFlush=true` là “không cần quản lý close” | AutoFlush chỉ điều khiển flush | Ownership vẫn phải được định nghĩa |
| Dùng `print(String)` cho binary payload | Charset biến đổi text thành bytes | Dùng `writeBytes` với byte[] đúng |
| Dùng `writeBytes` cho text không xét charset | Raw bytes có thể không khớp consumer | Thống nhất encoding/protocol |
| Nhiều wrappers ghi đồng thời và đóng tùy ý | Close propagation, interleaving và buffering riêng | Một owner, phối hợp ghi và close |
| Không đóng shared stream bao giờ vì sợ đóng sớm | Có nguy cơ rò rỉ file/socket | Owner đóng cuối vòng đời hợp lệ |
| Catch `IOException` quanh `writeBytes` như thể nó ném checked | API không khai báo checked IOException | Dùng `checkError()` hoặc API báo lỗi khác |
| Xem `close()` là cách flush vô hại | Nó còn đóng underlying | Gọi `flush()` nếu chỉ muốn đẩy buffer |

### 14.1. Một bug dễ bị che bởi môi trường test

Nếu bạn viết:

```java
ByteArrayOutputStream bytes = new ByteArrayOutputStream();
PrintStream ps = new PrintStream(bytes);
ps.close();
bytes.write(42); // ByteArrayOutputStream vẫn cho phép ghi.
```

Điều này **không chứng minh `ps.close()` không gọi `bytes.close()`**. `ByteArrayOutputStream` được thiết kế cho phép hoạt động sau `close()`. Đừng lấy tình huống đặc biệt này làm contract chung cho file, socket và các luồng khác.

### 14.2. Một bug dễ bị che bởi kiểu `PrintStream`

Nếu method trên một `PrintStream` đã đóng được gọi:

```java
ps.writeBytes(new byte[] {1, 2, 3});
```

Không nhìn thấy checked exception **không chứng minh bytes đã ghi thành công**. Khi cần điều tra, kiểm tra `ps.checkError()` và trạng thái underlying stream. Tuy nhiên không nên thử tiếp tục dùng wrapper đã đóng như một workflow bình thường.

## 15. Bài tập tình huống

**Bài 1.** Một thư viện nhận `System.out` rồi làm:

```java
try (PrintStream p = new PrintStream(System.out)) {
    p.println("done");
}
```

**Hỏi:** Vì sao lời gọi `System.out.println("next")` trong phần khác có thể không còn hoạt động?

**Đáp án:** `PrintStream.close()` được gọi khi rời try, và nó đóng underlying stream — chính là `System.out` đã được wrapper bọc.

**Bài 2.** Caller mở file bằng `Files.newOutputStream` và chuyển stream đó cho helper. Helper có nên close không?

**Đáp án:** Nếu helper chỉ được **mượn**, không. Caller đóng file ở cuối lifecycle. Nếu contract có quy định **chuyển quyền sở hữu**, helper mới có trách nhiệm close.

**Bài 3.** `autoFlush=true` có ngăn `PrintStream.close()` đóng shared stream không?

**Đáp án:** Không. AutoFlush điều khiển flush khi ghi mảng byte/newline/println; không can thiệp close propagation.

**Bài 4.** Vì sao `new PrintStream(new NonClosingOutputStream(shared))` có thể dùng try-with-resources mà vẫn giữ shared mở?

**Đáp án:** `PrintStream.close()` gọi `close()` của adapter, nhưng adapter override chỉ flush và **không gọi `shared.close()`**. Owner vẫn giữ quyền đóng shared.

**Bài 5.** Nếu wrapper ghi thất bại do underlying ném `IOException`, `writeBytes` có buộc caller catch `IOException` không?

**Đáp án:** Không. Phương thức `writeBytes(byte[])` không khai báo checked IOException. Kiểm tra lỗi bằng `checkError()` hoặc dùng trực tiếp OutputStream API thích hợp.

**Bài 6.** Vì sao test ownership bằng `ByteArrayOutputStream` có thể cho cảm giác “mọi thứ vẫn ổn”?

**Đáp án:** `ByteArrayOutputStream.close()` không có tác dụng; test nên dùng tracked stream có flag close và từ chối ghi sau khi đóng.

**Bài 7.** Hai `PrintStream` cùng bọc một socket output, có thể mỗi stream đóng độc lập mà socket vẫn sống không?

**Đáp án:** Không theo mặc định. Đóng một wrapper sẽ đóng underlying stream, có thể làm connection không ghi tiếp được. Cần owner và quy tắc đóng rõ ràng, hoặc non-closing adapter phù hợp.

**Bài 8.** Muốn ghi một bản tin text UTF-8, nên dùng byte array đã encode hay `print(String)`?

**Đáp án:** Cả hai có thể phù hợp nếu **charset/protocol thống nhất**. `writeBytes` ghi raw bytes UTF-8 đã chuẩn bị, còn `print` mã hóa theo charset cấu hình của PrintStream. Không trộn hai cách không kiểm soát encoding.

**Bài 9.** Một API owned stream đã close wrapper nhưng method kế tiếp chỉ có `checkError() == false`. Điều đó chứng minh gì?

**Đáp án:** Không chứng minh caller còn được phép ghi; ownership/lifecycle vẫn kết thúc. `checkError` phản ánh error state, không thay thế contract vòng đời.

**Bài 10.** Khi nào nên bỏ `PrintStream` và dùng `OutputStream` trực tiếp?

**Đáp án:** Khi công việc chỉ là ghi raw bytes và bạn muốn `IOException` được báo trực tiếp, hoặc khi không cần tiện ích `print/println/printf`.

## 16. Checklist trước khi bọc một stream dùng chung

- [ ] Xác định tài nguyên **owned** hay **borrowed** và ghi rõ trong API docs.
- [ ] Tránh `try-with-resources` trực tiếp trên wrapper đóng một borrowed/shared stream.
- [ ] Biết `PrintStream.close()` sẽ flush **và** đóng underlying output stream.
- [ ] Với `System.out`/`System.err`, dùng trực tiếp nếu có thể; không đóng trong helper.
- [ ] Nếu buộc tạo PrintStream tạm, dùng **non-closing adapter** và thử nghiệm cơ chế `close()`.
- [ ] Không quên **owner thực sự** phải đóng resource thật ở cuối lifecycle.
- [ ] Dùng `PrintStream.writeBytes(byte[])` cho raw bytes; nhớ API có từ Java 14 và vẫn dùng được.
- [ ] Với text, chọn charset phù hợp; với binary, không tự động encode lại.
- [ ] Phân biệt `flush()`, `autoFlush` và `close()`; cái đầu không thay thế quyền đóng.
- [ ] Nếu cần báo lỗi đáng tin, xem `checkError()` và cân nhắc OutputStream/Files API.
- [ ] Test với stream theo dõi `close()` và từ chối ghi sau close, không chỉ `ByteArrayOutputStream`.
- [ ] Nếu có nhiều wrapper/thread, điều phối thứ tự ghi và close; adapter không tự đảm bảo concurrency.
- [ ] Không gọi `super.close()` trong close-shield adapter nếu muốn giữ shared mở.
- [ ] Với socket/framework output, tuân theo ownership/lifecycle của connection/container.
- [ ] Đảm bảo không giữ một wrapper đã đóng rồi dùng lại ở các nhánh xử lý khác.

## 17. Tài liệu chính thức và phạm vi phiên bản

1. [Oracle Java SE 26 — PrintStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/PrintStream.html): `writeBytes(byte[])` (since Java 14), `close()` đóng underlying, `flush()`, `autoFlush` và `checkError()`.
2. [Oracle Java SE 21 — PrintStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/PrintStream.html): xác nhận hành vi trên JDK LTS và việc `writeBytes` được giữ lại.
3. [Oracle Java SE 17 — FilterOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FilterOutputStream.html): `close()` mặc định đóng underlying, lý do non-closing adapter cần override.
4. [Oracle Java SE 17 — ByteArrayOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayOutputStream.html): `close()` không ảnh hưởng tới các method, tránh dùng làm bằng chứng cho close propagation.
5. [Oracle Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): vòng đời và quy tắc tự gọi `close()`.
6. [Oracle Java SE 17 — OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): `write`, `flush`, `close` và hành vi IOException.
7. [Oracle Java SE 17 — ProcessBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html): lập danh sách arguments thay vì ghép lệnh shell khi cần khởi chạy công cụ ngoài.
