# `AutoCloseable` trong Java: Tránh đóng ngoài ý muốn tài nguyên của bên gọi

## 1. Vấn đề: `close()` không đồng nghĩa với “đã dùng xong trong phương thức này”

Trong Java, nhiều đối tượng triển khai `AutoCloseable`, ví dụ `InputStream`, `OutputStream`, `Reader`, `Writer`, tài nguyên JDBC hoặc các tài nguyên tự định nghĩa. `try-with-resources` sẽ tự động gọi `close()` khi thoát khối. Đây là cách tốt để tránh rò rỉ **khi mã hiện tại có trách nhiệm sở hữu và đóng tài nguyên**.

Nhưng nếu phương thức **nhận một tài nguyên do bên gọi tạo ra và vẫn cần sử dụng sau lời gọi**, việc tự đóng nó có thể làm hỏng luồng xử lý.

```java
static void writeReport(OutputStream output) throws IOException {
    try (OutputStream managed = output) {
        managed.write("hello".getBytes(StandardCharsets.UTF_8));
    }
}
```

Đây là **phương thức minh họa** trong lớp có import `java.io.OutputStream`, `java.io.IOException` và `java.nio.charset.StandardCharsets`. Cách viết này khiến `output.close()` được gọi khi rời khối, vì `managed` và `output` cùng tham chiếu **một đối tượng**. Nếu bên gọi muốn ghi thêm sau `writeReport`, tài nguyên có thể đã không còn sử dụng được.

**Nguyên tắc quan trọng nhất: tài nguyên do bên nào sở hữu thì bên đó có trách nhiệm quyết định thời điểm đóng, trừ khi hợp đồng API nói rõ quyền sở hữu đã được chuyển giao.** Java không có cơ chế kiểm tra *ownership* kiểu tĩnh cho mọi `AutoCloseable`; người thiết kế API phải quy định và tuân thủ việc này.

Bài tập trung vào thực hành còn đúng với Java 17+ và các phiên bản hiện đại. `AutoCloseable` cùng `try-with-resources` xuất hiện từ Java 7; dạng `try (existingVariable)` được bổ sung từ Java 9 và vẫn được hỗ trợ ngày nay.

## 2. Phân biệt tài nguyên “mượn”, “sở hữu” và “đã chuyển quyền sở hữu”

| Quan hệ | Ai tạo hoặc quản lý vòng đời? | Phương thức nhận tài nguyên có được tự `close()`? |
| --- | --- | --- |
| **Borrowed / caller-owned**: mượn tài nguyên | Bên gọi vẫn sở hữu | **Không**, trừ khi hợp đồng nói khác |
| **Callee-owned**: tự mở trong phương thức | Phương thức hiện tại | **Có**, và nên đóng bằng `try-with-resources` |
| **Ownership transferred**: bên gọi bàn giao quyền sở hữu | Trách nhiệm được chuyển rõ ràng cho bên nhận | **Có**; tài nguyên được coi là hết quyền sử dụng ở bên gọi sau khi giao |
| **Shared/framework-managed**: do framework, pool hoặc thành phần khác quản lý | Chủ sở hữu do API quy định | Chỉ đóng hoặc trả về theo **hợp đồng** của framework, không tự suy đoán |

Ví dụ:

```java
// Bên gọi mở và vẫn cần stream sau thao tác:
OutputStream callerOwned = obtainOutput();
appendText(callerOwned, "first");
appendText(callerOwned, "second");
callerOwned.close();  // bên gọi quyết định lúc kết thúc
```

`obtainOutput()` và `appendText(...)` là các API minh họa. Với hợp đồng **borrowed**, `appendText` không được đóng `callerOwned`.

Ngược lại:

```java
// Phương thức tự tạo, tự sở hữu:
static void save(Path path, byte[] data) throws IOException {
    try (OutputStream output = Files.newOutputStream(path)) {
        output.write(data);
    }
}
```

Đây là **phương thức minh họa** có import `java.nio.file.Files`, `java.nio.file.Path`, `java.io.OutputStream` và `java.io.IOException`. `save` tự mở tài nguyên, nên nó **phải đóng tài nguyên dù ghi thành công hay thất bại**.

**Không xác định ownership theo cách “đối tượng có phải là `AutoCloseable` hay không”.** `AutoCloseable` nói đối tượng *có thể đóng*; nó không quy định **bên nào được phép đóng** trong một API cụ thể.

## 3. Vì sao `try-with-resources` có thể làm đóng tài nguyên của bên gọi?

### 3.1. Cơ chế của `try-with-resources`

```java
try (OutputStream managed = providedOutput) {
    managed.write(65);
}
```

Khi phần thân kết thúc, Java gọi `managed.close()` nếu tham chiếu khác `null`. Đây là việc đóng **đối tượng** chứ không chỉ “xóa tên biến managed”.

Biến `managed` chỉ là một tham chiếu khác tới `providedOutput`. Khối `try` không tạo một bản sao độc lập của stream. Hậu quả:

- `providedOutput` vẫn tồn tại ở scope bên gọi, nhưng có thể **đã đóng**.
- Bên gọi gọi tiếp `write()` hoặc `flush()` có thể nhận `IOException` hoặc hành vi không được API hỗ trợ.
- Nếu `close()` là thao tác commit, release connection, kết thúc frame hoặc trả connection về pool, tác động có thể lớn hơn việc “không ghi được nữa”.
- Dù phần thân `try` ném exception hoặc có `return`, Java vẫn tiến hành đóng resource đã đăng ký theo ngữ nghĩa `try-with-resources`.

`close()` của mỗi implementation có hợp đồng riêng; không nên mặc định nó vô hại hay có thể gọi lặp an toàn.

### 3.2. Java 9+ viết `try (providedOutput)` cũng sẽ đóng

```java
static void wrong(OutputStream providedOutput) throws IOException {
    try (providedOutput) {  // Java 9+; providedOutput là effectively final
        providedOutput.write(65);
    }
}
```

Dạng này không cần khai báo biến mới, nhưng **vẫn đăng ký chính đối tượng của bên gọi để tự đóng**. Nó không tự chuyển đổi hợp đồng borrowed thành owned.

**Quy tắc:** Với tài nguyên được truyền vào, **đừng đưa nó trực tiếp vào resource specification** của `try-with-resources` nếu phương thức không được trao trách nhiệm đóng.

### 3.3. Ngoại lệ bị ném không thay đổi ownership

Một người viết có thể nghĩ “chỉ cần `close()` trong `catch` để dọn khi lỗi”. Nhưng với tài nguyên borrowed, làm vậy vẫn xâm phạm quyền sở hữu:

```java
// Cách xử lý sai nếu output là tài nguyên do caller sở hữu:
try {
    output.write(data);
} catch (IOException e) {
    output.close(); // đóng dù caller vẫn có thể cần điều tra/thử lại
    throw e;
}
```

Tình huống lỗi không tự trao quyền đóng. Phương thức nên giữ đúng hợp đồng borrowed trên **cả đường thành công lẫn đường thất bại**; việc đóng và chính sách thử lại thuộc về bên sở hữu.

## 4. Lỗi đóng gián tiếp qua lớp wrapper

Không chỉ `try (stream)` mới có nguy cơ. Nhiều wrapper cũng **đóng tài nguyên được bọc** khi wrapper bị đóng.

Ví dụ:

```java
static void accidentallyClose(OutputStream borrowed) throws IOException {
    try (Writer writer = new OutputStreamWriter(
            borrowed, StandardCharsets.UTF_8)) {
        writer.write("Xin chào");
    }
}
```

Đây là **phương thức minh họa** có import `java.io.Writer`, `java.io.OutputStreamWriter`, `java.io.OutputStream` và `java.nio.charset.StandardCharsets`.

Tình huống thường xảy ra:

1. `borrowed` được bên gọi mở, quyền sở hữu vẫn ở bên gọi.
2. Phương thức tạo một `OutputStreamWriter` để chuyển ký tự sang byte.
3. `try-with-resources` đóng **writer**.
4. `writer.close()` cũng dẫn tới đóng **underlying output stream**.
5. Bên gọi bất ngờ nhận một stream đã đóng.

Với các lớp như `FilterOutputStream`, API chuẩn của Java nêu rõ `close()` thông thường gọi `flush()` rồi đóng stream bên dưới. Các wrapper khác như `BufferedWriter`, `InputStreamReader`, `BufferedReader`, `Scanner` cũng cần xem **hợp đồng `close()` của từng lớp**; đừng mặc định chỉ wrapper được đóng còn đối tượng nền vẫn mở.

Ví dụ đặc biệt đáng tránh:

```java
// CẢNH BÁO: Đừng làm như vậy nếu sau đó chương trình còn cần System.in.
try (java.util.Scanner scanner = new java.util.Scanner(System.in)) {
    System.out.println(scanner.nextLine());
}
// Scanner.close() có thể đóng nguồn đọc bên dưới nếu nguồn đó Closeable.
```

Đây là ví dụ **minh họa rủi ro**, không phải gợi ý để chạy trong ứng dụng tương tác. `System.in` thường là nguồn nhập chia sẻ của cả tiến trình. Cũng nên tránh đóng `System.out` hoặc `System.err` từ một phương thức tiện ích không sở hữu chúng.

**Điểm mấu chốt:** Quyền sở hữu cần được truy vết **xuyên qua chuỗi wrapper**, không chỉ dựa vào tham chiếu xuất hiện trực tiếp trong `try (...)`.

## 5. Mẫu đúng khi phương thức chỉ mượn tài nguyên

### 5.1. Dùng trực tiếp, không tự đóng

Khi thao tác đơn giản và không cần wrapper sở hữu tài nguyên phụ trợ:

```java
static void appendText(OutputStream borrowed, String text)
        throws IOException {
    borrowed.write(text.getBytes(StandardCharsets.UTF_8));
    // borrowed.flush(); // chỉ khi hợp đồng cho phép/yêu cầu flush
    // Không gọi borrowed.close().
}
```

Đây là **phương thức minh họa** có các import Java tương ứng.

- Phương thức viết dữ liệu, không đóng tài nguyên.
- Nếu `write` ném `IOException`, phương thức truyền lỗi cho bên gọi; **không tự đóng** stream trong `catch` hoặc `finally`.
- `flush()` và `close()` là hai thao tác khác nhau. Dù không đóng stream, `flush()` vẫn có thể ảnh hưởng buffering, hiệu năng và ranh giới giao thức, nên cần làm rõ hợp đồng API. Một API tiện ích có thể cho phép flush theo yêu cầu hoặc để bên gọi kiểm soát.
- Đừng tự động gọi `close()` để "đảm bảo dữ liệu đã ghi" nếu trách nhiệm đóng thuộc về bên gọi.

Đối với phương thức nhận `Reader`, `InputStream` hay `Writer`, nguyên tắc borrowed cũng tương tự: đọc/ghi theo hợp đồng, **không đóng resource do bên gọi sở hữu**.

### 5.2. Chỉ đóng những tài nguyên phương thức thực sự sở hữu

Một phương thức có thể nhận một stream borrowed, đồng thời tự mở một resource phụ khác. Khi đó, **chỉ đăng ký resource tự mở** trong `try-with-resources`:

```java
static void copyWithOwnedInput(Path file, OutputStream borrowedOutput)
        throws IOException {
    try (InputStream input = Files.newInputStream(file)) {
        input.transferTo(borrowedOutput);
    }
    // input do phương thức mở: đã đóng.
    // borrowedOutput do caller sở hữu: vẫn để mở.
}
```

Đây là **phương thức minh họa cho Java 17+** có import `java.nio.file.Files`, `java.nio.file.Path`, `java.io.InputStream`, `java.io.OutputStream` và `java.io.IOException`. `InputStream.transferTo(OutputStream)` không đóng các stream mà nó dùng; `try-with-resources` ở đây đóng **input** do phương thức mở. Bên gọi tự quyết định có flush/close `borrowedOutput` hay không.

Khi copy, **không được nhầm quyền quản lý file input với quyền quản lý output của caller**.

### 5.3. Nếu muốn nhận quyền sở hữu, đặt tên và hợp đồng cho rõ

```java
static void writeAndClose(OutputStream transferred, byte[] data)
        throws IOException {
    try (OutputStream owned = transferred) {
        owned.write(data);
    }
}
```

Phương thức này **chủ động đóng stream**, nên tên/hợp đồng phải thể hiện trách nhiệm ấy. Bên gọi không được kỳ vọng tiếp tục dùng stream sau khi phương thức hoàn tất.

Một API “transfer ownership” nên ghi rõ:

- Bên nào đóng tài nguyên, kể cả khi có exception.
- Bên gọi còn được phép truy cập tài nguyên sau khi chuyển quyền hay không.
- Nếu thao tác thất bại, quyền sở hữu có được trả lại hay vẫn do bên nhận chịu trách nhiệm đóng.
- Việc đóng có ảnh hưởng đến tài nguyên nền/connection pool/transaction hoặc những đối tượng khác không.

**Không nên chỉ dựa vào kiểu `OutputStream` hay `AutoCloseable` để làm người đọc đoán ra hợp đồng chuyển quyền.**

## 6. Khi cần wrapper: dùng “close shield” có kiểm soát

Giả sử bạn muốn tận dụng `OutputStreamWriter` để mã hóa Unicode, nhưng vẫn phải giữ stream bên dưới cho caller. Một chiến lược là **wrapper chặn hành động đóng stream nền** (*non-closing wrapper* hoặc *close shield*).

Ví dụ lớp đơn giản:

```java
static final class NonClosingOutputStream extends FilterOutputStream {
    NonClosingOutputStream(OutputStream delegate) {
        super(delegate);
    }

    @Override
    public void close() throws IOException {
        flush(); // chủ động flush, KHÔNG gọi super.close()
    }
}
```

Điểm khác với `FilterOutputStream` thông thường là `close()` **không gọi `super.close()` và không gọi `out.close()`**. Nó chỉ `flush()`, nên tài nguyên nền vẫn mở. **Việc flush cũng là một tác động lên stream của caller**; chỉ sử dụng chiến lược này khi hợp đồng cho phép flush khi wrapper kết thúc.

Cách dùng:

```java
static void appendTextWithWrapper(OutputStream borrowed, String text)
        throws IOException {
    try (Writer writer = new OutputStreamWriter(
            new NonClosingOutputStream(borrowed),
            StandardCharsets.UTF_8)) {
        writer.write(text);
    }
    // writer được đóng đúng trách nhiệm của nó;
    // NonClosingOutputStream không đóng borrowed.
}
```

Đây là các đoạn **thành phần/phương thức minh họa**, có định nghĩa hoàn chỉnh ở chương trình phần tiếp theo.

### Cần hiểu giới hạn của close shield

- Close shield giữ **việc đóng tài nguyên nền** khỏi lan truyền; nó không làm dữ liệu đã đọc/ghi được hoàn tác hoặc khôi phục vị trí stream.
- Khi dùng wrapper có buffering, việc đóng wrapper có thể **flush dữ liệu đệm** để hoàn tất đầu ra. Không thể thay việc đóng wrapper bằng “không làm gì” trong mọi trường hợp, vì một số lớp cần hoàn tất mã hóa/định dạng khi đóng.
- Wrapper tự định nghĩa chỉ phù hợp khi được kiểm thử kỹ. Nếu một thư viện đã cung cấp cơ chế close shield hoặc tùy chọn **leave-open** được hỗ trợ chính thức, nên dùng API đó và kiểm tra hợp đồng của nó.
- Một số lớp tài nguyên cần hành vi đóng thật để hoàn tất cấu trúc dữ liệu (ví dụ kết thúc định dạng có footer hoặc đóng tài nguyên phụ). **Không vô hiệu hóa `close()` bừa bãi**; chỉ chặn đóng **delegate do caller sở hữu**, còn cho phép các lớp phía trên kết thúc đúng hợp đồng.
- Close shield có thể cần thiết kế khác cho `InputStream`, `Reader`, `Writer` hoặc đối tượng không phải stream. Không nên dùng lớp minh họa `NonClosingOutputStream` như “giải pháp cho mọi `AutoCloseable`”.

### Lưu ý thêm với stream đầu vào

Đối với `BufferedReader` hoặc `BufferedInputStream`, giữ underlying stream mở **không bảo đảm** vị trí đọc được giữ nguyên: wrapper có thể đọc trước (*read-ahead*). Hãy ghi rõ phương thức sẽ tiêu thụ bao nhiêu dữ liệu và điều kiện caller có thể tiếp tục đọc, không chỉ ghi “không đóng”.

## 7. Chương trình Java 17+ đầy đủ: có bảo vệ, có lỗi và có so sánh

Chương trình sau chứng minh **ba hợp đồng**:

1. Phương thức mượn stream ghi dữ liệu, hoặc đóng một wrapper có close shield, nhưng không đóng stream của caller.
2. Phương thức được **chuyển quyền sở hữu** sẽ đóng stream.
3. Phương thức **sai** đóng `OutputStreamWriter` trên stream borrowed sẽ làm đóng cả stream của caller.

Tài nguyên giả `TrackingOutputStream` chủ động đếm số lần đóng và từ chối ghi sau khi bị đóng. Điều này quan trọng vì **không phải `OutputStream` cụ thể nào cũng ném lỗi khi ghi sau `close()`**; chẳng hạn một số stream trong bộ nhớ có hành vi đóng không tác động như tài nguyên hệ điều hành. Dùng test double có trạng thái giúp phát hiện lỗi ownership chính xác.

Lưu toàn bộ vào tệp **`CallerOwnedResourceDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;

public final class CallerOwnedResourceDemo {

    static final class TrackingOutputStream extends OutputStream {
        private final ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        private boolean closed;
        private int closeCalls;

        @Override
        public void write(int value) throws IOException {
            if (closed) {
                throw new IOException("already closed");
            }
            buffer.write(value);
        }

        @Override
        public void flush() throws IOException {
            if (closed) {
                throw new IOException("already closed");
            }
            buffer.flush();
        }

        @Override
        public void close() {
            closeCalls++;
            closed = true;
        }

        boolean isClosed() {
            return closed;
        }

        int closeCalls() {
            return closeCalls;
        }

        String text() {
            return buffer.toString(StandardCharsets.UTF_8);
        }
    }

    static final class NonClosingOutputStream extends FilterOutputStream {
        NonClosingOutputStream(OutputStream delegate) {
            super(delegate);
        }

        @Override
        public void close() throws IOException {
            flush(); // KHÔNG gọi super.close() hoặc out.close()
        }
    }

    static final class FailingOutputStream extends OutputStream {
        private boolean closed;

        @Override
        public void write(int value) throws IOException {
            throw new IOException("write failed");
        }

        @Override
        public void close() {
            closed = true;
        }

        boolean isClosed() {
            return closed;
        }
    }

    static void appendBorrowed(OutputStream borrowed, String text)
            throws IOException {
        borrowed.write(text.getBytes(StandardCharsets.UTF_8));
        borrowed.flush(); // Hợp đồng ví dụ cho phép flush; không close.
    }

    static void appendBorrowedWithWrapper(OutputStream borrowed, String text)
            throws IOException {
        try (Writer writer = new OutputStreamWriter(
                new NonClosingOutputStream(borrowed),
                StandardCharsets.UTF_8)) {
            writer.write(text);
        }
    }

    static void writeOwned(OutputStream owned, String text)
            throws IOException {
        try (OutputStream resource = owned) {
            resource.write(text.getBytes(StandardCharsets.UTF_8));
        }
    }

    static void writeWrongly(OutputStream borrowed) throws IOException {
        try (Writer writer = new OutputStreamWriter(
                borrowed, StandardCharsets.UTF_8)) {
            writer.write("Z");
        }
    }

    public static void main(String[] args) throws IOException {
        TrackingOutputStream caller = new TrackingOutputStream();

        appendBorrowed(caller, "A");
        appendBorrowedWithWrapper(caller, "B");

        System.out.println("borrowed.closed=" + caller.isClosed());
        System.out.println("borrowed.data=" + caller.text());

        appendBorrowed(caller, "C"); // Bên gọi vẫn có thể dùng tiếp.
        System.out.println("after.reuse=" + caller.text());

        caller.close(); // Chủ sở hữu tự đóng.
        System.out.println("caller.closeCalls=" + caller.closeCalls());

        FailingOutputStream failing = new FailingOutputStream();
        try {
            appendBorrowed(failing, "E");
        } catch (IOException e) {
            System.out.println("failure=" + e.getMessage());
        }
        System.out.println("failure.closed=" + failing.isClosed());

        TrackingOutputStream owned = new TrackingOutputStream();
        writeOwned(owned, "X"); // Quyền sở hữu đã chuyển cho hàm.
        System.out.println("owned.closed=" + owned.isClosed());
        System.out.println("owned.closeCalls=" + owned.closeCalls());

        TrackingOutputStream accidental = new TrackingOutputStream();
        writeWrongly(accidental); // Cố ý minh họa anti-pattern.
        System.out.println("wrong.closed=" + accidental.isClosed());
        System.out.println("wrong.data=" + accidental.text());

        try {
            appendBorrowed(accidental, "!");
        } catch (IOException e) {
            System.out.println("wrong.reuse=" + e.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac CallerOwnedResourceDemo.java
java CallerOwnedResourceDemo
```

**Stdout chính xác:**

```text
borrowed.closed=false
borrowed.data=AB
after.reuse=ABC
caller.closeCalls=1
failure=write failed
failure.closed=false
owned.closed=true
owned.closeCalls=1
wrong.closed=true
wrong.data=Z
wrong.reuse=already closed
```

### 7.1. Đọc kết quả theo trách nhiệm sở hữu

- `borrowed.closed=false`: sau khi phương thức borrowed và wrapper có close shield chạy xong, stream của caller **chưa đóng**.
- `borrowed.data=AB`: ghi trực tiếp và ghi qua `OutputStreamWriter` đều có dữ liệu.
- `after.reuse=ABC`: caller ghi tiếp được chữ C, chứng minh quyền sử dụng stream chưa bị phương thức con chấm dứt.
- `caller.closeCalls=1`: caller tự quyết định thời điểm đóng; trong test này chỉ một lần đóng xảy ra.
- `failure=write failed` và `failure.closed=false`: khi thao tác mượn stream ném lỗi, phương thức **truyền lỗi ra nhưng không đóng stream của caller**.
- `owned.closed=true` và `owned.closeCalls=1`: cách viết đúng khi hàm thực sự đã nhận quyền sở hữu.
- `wrong.closed=true`: đóng `OutputStreamWriter` không có close shield làm đóng luôn stream borrowed.
- `wrong.reuse=already closed`: test double từ chối dùng lại sau lần đóng ngoài ý muốn. Message này là **hành vi do `TrackingOutputStream` tự định nghĩa**, không phải thông báo bắt buộc cho mọi implementation `OutputStream`.

Điểm quan trọng là bộ minh họa xác nhận **cả đường thành công và đường thất bại**, không chỉ nhìn thấy đúng chuỗi dữ liệu.

## 8. Kiểm thử hợp đồng ownership trong dự án

### 8.1. Những kiểm tra nên có

| Tình huống | Nếu API nhận borrowed resource | Nếu API sở hữu resource |
| --- | --- | --- |
| Thành công | Resource vẫn mở; caller còn dùng được | Resource được đóng theo hợp đồng |
| Phương thức ném lỗi | Không đóng resource của caller | Resource đã mở được cleanup, exception giữ đúng |
| Có wrapper | Đóng wrapper **không đóng delegate** borrowed | Đóng wrapper và delegate nếu wrapper có quyền sở hữu delegate |
| Bị gọi nhiều lần | Không biến resource của caller thành closed giữa các lần | Mỗi resource đã transfer được đóng đúng cách |
| Có buffer | Flush theo hợp đồng, không tự quyết định đóng | Flush/close theo hợp đồng của resource |
| Caller tự đóng sau cùng | Đúng một nơi có trách nhiệm chấm dứt sử dụng | Caller không cố dùng lại resource đã transfer |

Trong unit test, một đối tượng giả có `closeCalls`, `isClosed` và khả năng mô phỏng exception giúp chứng minh hành vi. Hãy kiểm tra cả việc **không đóng** khi nhận borrowed resource; thiếu assertion này là một lỗi phổ biến trong test chỉ quan tâm đến kết quả trả về.

Ví dụ assertions minh họa:

```java
TrackingOutputStream source = new TrackingOutputStream();
appendBorrowed(source, "hello");

if (source.closeCalls() != 0 || source.isClosed()) {
    throw new AssertionError("Borrowed resource was closed");
}

source.write('!');
source.close();
if (source.closeCalls() != 1) {
    throw new AssertionError("Caller should close once");
}
```

Đây là **đoạn minh họa trong phạm vi lớp `CallerOwnedResourceDemo`**, không phải một chương trình độc lập. Trong dự án có JUnit Jupiter, có thể dùng `assertEquals(0, source.closeCalls())`, `assertFalse(source.isClosed())`, `assertDoesNotThrow(...)`, sau đó kiểm tra caller tự đóng. Cần test thêm **đường lỗi của borrowed resource**, vì mã dọn dẹp trong `catch`/`finally` rất dễ vô tình xâm phạm ownership.

### 8.2. Với stream thật, chỉ assert những gì API đảm bảo

Đừng sử dụng `ByteArrayOutputStream` thuần túy để chứng minh tài nguyên **chưa bị đóng**: `close()` của lớp này không ảnh hưởng đến việc gọi phương thức tiếp theo theo hợp đồng lớp. Một bài test chỉ thử ghi tiếp vào `ByteArrayOutputStream` có thể không phát hiện việc đã có lời gọi `close()` ngoài ý muốn.

Hãy dùng test double chủ động ghi nhận `close()`, hoặc kiểm tra trạng thái đã được API thật công bố. Khi kiểm thử tích hợp với file, socket hoặc connection, tránh phụ thuộc file người dùng, thời điểm tùy ý và chi tiết triển khai không được hợp đồng đảm bảo.

### 8.3. Đừng “để thử cho chắc” bằng cách đóng lần hai

`AutoCloseable.close()` không bắt buộc mọi implementation đều idempotent. Để chứng minh bên gọi có quyền đóng, chỉ cần kiểm chứng resource vẫn mở và **bên gọi có thể thực hiện thao tác hợp lệ**, rồi đóng một lần theo hợp đồng. Việc gọi `close()` ở cả callee lẫn caller không phải cách xử lý an toàn mặc định.

## 9. Các trường hợp đặc biệt cần quyết định rõ ownership

### 9.1. Resource được dùng chung

Một kết nối, stream đầu vào chuẩn, logger, hoặc resource nằm trong pool có thể được nhiều thành phần sử dụng. Một phương thức tiện ích không nên tự gọi `close()` chỉ vì nó biết đối tượng triển khai `AutoCloseable`.

Với kết nối do pool cung cấp, ý nghĩa của `close()` có thể là **trả kết nối về pool**, không phải đóng socket vật lý. Dù vậy, hành động này vẫn có thể làm tài nguyên **không còn được phép dùng từ tham chiếu của caller**. Phải theo hợp đồng sở hữu và thuê/trả của thư viện, không áp một quy tắc duy nhất cho mọi đối tượng.

### 9.2. Stream do framework cấp cho callback

Trong các callback web, job hoặc pipeline, framework có thể sở hữu request/response stream. Nếu một helper được truyền `OutputStream` của framework, helper thường nên xem nó là **borrowed** trừ khi framework yêu cầu ngược lại. Việc tự đóng stream có thể kết thúc response quá sớm, làm hỏng protocol framing hoặc cản trở thành phần khác ghi tiếp.

Tương tự, đừng tự động đăng ký `System.in`, `System.out` hoặc `System.err` vào `try-with-resources` trong những helper được gọi giữa vòng đời chương trình.

### 9.3. Chuyển ownership là một phần thiết kế API

Một API có thể quy định “sau khi gọi thành công, đối tượng này thuộc về thư viện”, nhưng cũng cần mô tả **tình huống thất bại**: nếu lời gọi ném exception trước khi nhận quyền sở hữu thì bên nào đóng? Nếu không quy định rõ, hai phía có thể cùng bỏ đóng (rò rỉ) hoặc cùng đóng (đóng lặp). Việc chuyển quyền sở hữu nên có một mốc và hậu quả dễ kiểm thử.

### 9.4. `flush()` không thay `close()` và cũng không phải vô hại

Đối với output stream, `flush()` thường đẩy dữ liệu đệm xuống tầng bên dưới, nhưng không nhất thiết đồng nghĩa dữ liệu đã bền vững trên đĩa. `close()` có thể thực hiện thêm cleanup và chấm dứt quyền sử dụng. Một phương thức borrowed có thể flush nếu hợp đồng cho phép, nhưng không nên gọi flush/close ở mọi nơi theo thói quen.

Nếu wrapper có encoder hoặc formatter, `close()` của wrapper có thể hoàn tất trạng thái riêng của wrapper. Khi thiết kế close shield, cần **đóng wrapper đúng cách** và chỉ chặn đóng **delegate của caller**, không vô hiệu hóa mọi công việc kết thúc của lớp wrapper.

## 10. Lỗi phổ biến và cách sửa

| Cách viết hoặc nhận định sai | Vấn đề | Cách đúng |
| --- | --- | --- |
| `try (OutputStream s = borrowed)` trong helper | Đăng ký borrowed để tự đóng | Chỉ dùng `try` với resource helper sở hữu |
| `try (borrowed)` trên Java 9+ | Cũng đóng cùng object của caller | Không đưa borrowed vào resource specification |
| `try (Writer w = new OutputStreamWriter(borrowed, UTF_8))` | `close()` của writer làm đóng stream nền | Dùng close shield hoặc API leave-open phù hợp |
| `catch (IOException e) { borrowed.close(); throw e; }` | Lỗi không chuyển quyền sở hữu | Truyền lỗi và để caller xử lý resource |
| `finally { borrowed.close(); }` | Đóng dù thành công hay thất bại | Chỉ đóng khi helper sở hữu/được transfer |
| “Thêm `AutoCloseable` nghĩa là helper có quyền đóng” | Interface không biểu diễn ownership | Xác định contract riêng, rõ ràng |
| “Đóng wrapper không bao giờ đóng delegate” | Nhiều wrapper có close cascading | Kiểm tra tài liệu `close()` của từng lớp |
| “Đóng cùng stream hai lần luôn an toàn” | Không có bảo đảm idempotence chung | Một owner, một trách nhiệm đóng |
| “Gọi `flush()` là tương đương `close()`” | Không giống nhau về lifecycle | Flush và close theo từng hợp đồng |
| “Test ghi tiếp bằng `ByteArrayOutputStream` là đủ” | Lớp này có `close()` gần như không tác động | Test double theo dõi lời gọi close |
| “Sau khi chuyển ownership, caller vẫn có quyền dùng lại” | Hợp đồng chuyển quyền đã thay đổi | Caller không dùng lại, trừ khi API cho phép |

## 11. Bài tập và đáp án

**Câu 1.** Phương thức nhận `OutputStream out` của caller, caller cần tiếp tục ghi sau khi phương thức trả về. Có nên viết `try (out)` không?  
**Đáp án:** Không. `try (out)` (Java 9+) gọi `out.close()` khi rời khối, trái hợp đồng borrowed.

**Câu 2.** Viết `try (OutputStream local = out)` có giải quyết được không?  
**Đáp án:** Không. `local` và `out` cùng trỏ tới một object, nên đóng `local` vẫn đóng tài nguyên bên gọi.

**Câu 3.** `OutputStreamWriter` đóng có thể ảnh hưởng tới underlying `OutputStream` không?  
**Đáp án:** Có. Đóng writer thường đóng stream nền. Nếu muốn stream của caller vẫn mở, cần thiết kế wrapper hoặc API có hợp đồng leave-open.

**Câu 4.** Nếu helper tự gọi `Files.newOutputStream(path)`, ai chịu trách nhiệm đóng?  
**Đáp án:** Helper, bởi nó đã tự mở và quản lý vòng đời resource đó, trừ khi chuyển ownership một cách tường minh sang thành phần khác.

**Câu 5.** Vì sao nên kiểm thử helper borrowed cả khi `write()` ném `IOException`?  
**Đáp án:** Vì `catch`/`finally` có thể chứa mã cleanup vô tình đóng tài nguyên của caller. Ngoại lệ không làm đổi hợp đồng ownership.

**Câu 6.** Non-closing wrapper luôn là cách giải quyết phù hợp cho mọi `AutoCloseable`?  
**Đáp án:** Không. Cần hiểu tác dụng của `close()` trên wrapper và delegate; một số resource cần close để hoàn tất định dạng, transaction hoặc cleanup nội bộ. Chỉ chặn đóng delegate khi hợp đồng cho phép.

**Câu 7.** Nếu tài nguyên borrowed đã được một phần mã khác đóng, helper có đảm bảo vẫn dùng được không?  
**Đáp án:** Không. Bảo đảm “helper không tự đóng” **không thay thế** việc caller và các thành phần khác phải quản lý vòng đời, đồng bộ sử dụng và tránh đóng khi còn tác vụ đang chạy.

## 12. Checklist rà soát API

- [ ] Đã xác định rõ tài nguyên là borrowed, owned hay transferred.
- [ ] Tên phương thức/tài liệu mô tả ai đóng tài nguyên và khi nào.
- [ ] Bên không sở hữu **không** gọi `close()` trực tiếp, trong `catch` hoặc `finally`.
- [ ] Không đưa borrowed resource vào `try-with-resources` dù bằng biến alias.
- [ ] Đã kiểm tra cascade của `close()` qua mọi wrapper được tạo.
- [ ] Nếu cần close shield, đã quyết định rõ chính sách flush và trách nhiệm đóng delegate.
- [ ] Đã test đường thành công: caller vẫn dùng được borrowed resource.
- [ ] Đã test đường lỗi: borrowed resource vẫn chưa bị helper đóng.
- [ ] Đã test trường hợp transfer ownership: resource được cleanup đúng.
- [ ] Đã tránh test giả tạo trên API có `close()` không quan sát được.
- [ ] Đã ghi rõ hành vi với stream chia sẻ/framework/connection pool.
- [ ] Không đóng lặp hoặc làm mất exception phục vụ chẩn đoán.

## 13. Kết luận và tài liệu chính thức

**Ghi nhớ:** `AutoCloseable` và `try-with-resources` là công cụ quản lý vòng đời tài nguyên, **không phải giấy phép để bất kỳ phương thức nào cũng đóng mọi tài nguyên nó nhận**. Hãy đóng resource mà mình sở hữu; chỉ đóng resource của caller khi **hợp đồng chuyển quyền sở hữu** nói rõ điều đó. Kiểm tra toàn bộ chuỗi wrapper vì `close()` của wrapper có thể đóng delegate, và kiểm thử **cả trường hợp thành công và thất bại** để bảo đảm helper không vô tình làm tài nguyên bên gọi hết hiệu lực.

Nguồn chuẩn vẫn được sử dụng:

- [Java Language Specification 17, `14.20.3 — `try`-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): quy tắc tự đóng tài nguyên và thời điểm đóng.
- [Java SE 17 API — `AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng đóng, exception và đặc điểm không bảo đảm idempotence.
- [Java SE 17 API — `FilterOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FilterOutputStream.html): `close()` mặc định flush và đóng stream bên dưới.
- [Java SE 17 API — `OutputStreamWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html): wrapper chuyển ký tự thành byte; thao tác đóng có thể ảnh hưởng underlying stream.
- [Java SE 17 API — `InputStream.transferTo(OutputStream)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html#transferTo(java.io.OutputStream)): phương thức copy và quy tắc không tự đóng các stream sử dụng.