# Finalization và quản lý tài nguyên bằng cơ chế đóng tường minh

Trong quá trình nâng cấp và di chuyển ứng dụng Java, một trong những rủi ro khó nhận thấy là việc giải phóng tài nguyên được gắn với garbage collection (GC). Mã cũ đôi khi đặt thao tác đóng file, giải phóng bộ nhớ native hoặc trả kết nối trong phương thức `finalize()` và kỳ vọng JVM sẽ tự gọi khi đối tượng không còn được tham chiếu. Kỳ vọng này không đủ để bảo đảm tài nguyên được giải phóng đúng lúc, đúng thứ tự hoặc thậm chí chắc chắn được giải phóng.

Java hiện đại khuyến khích quản lý vòng đời tài nguyên theo cơ chế **đóng tường minh**: lớp sở hữu tài nguyên triển khai `AutoCloseable` hoặc `Closeable`; nơi sở hữu vòng đời gọi `close()`, thường qua `try-with-resources`. Với native resource, `Cleaner` hoặc reference-processing có thể đóng vai trò dự phòng, nhưng không thay thế việc đóng có kiểm soát.

Bài này tập trung vào việc nhận diện phụ thuộc vào finalization, lựa chọn cách quản lý tài nguyên phù hợp, chuyển mã cũ sang cơ chế đóng tường minh và tổ chức kiểm thử trong một đợt Java Advance Compatibility Migration.

## 1. Phân biệt bộ nhớ Java và tài nguyên ngoài heap

GC của Java chủ yếu quản lý bộ nhớ heap chứa các đối tượng Java. Khi một đối tượng không còn có thể truy cập, JVM có thể thu hồi phần bộ nhớ heap của nó vào thời điểm phù hợp. **Điều đó không đồng nghĩa mọi tài nguyên liên quan đến đối tượng đã được giải phóng.**

Ví dụ về tài nguyên cần quản lý vòng đời:

| Tài nguyên | Vì sao cần giải phóng? | Cơ chế thường dùng |
|---|---|---|
| File descriptor, input/output stream | Hệ điều hành giới hạn số handle; file có thể bị khóa | `close()`, `try-with-resources` |
| Socket và kết nối mạng | Chiếm kết nối, descriptor và trạng thái protocol | `Socket.close()` hoặc API tương đương |
| JDBC connection, statement, result set | Chiếm connection pool, cursor và tài nguyên phía server | `AutoCloseable` / `try-with-resources` |
| Direct/native memory | Bộ nhớ ngoài heap có vòng đời khác object Java | API có owner rõ ràng; `Arena.close()` khi phù hợp |
| Native handle JNI | Đối tượng của hệ điều hành hoặc thư viện C/C++ cần lệnh release riêng | Wrapper `AutoCloseable` gọi hàm native release |
| Zip/JAR filesystem, directory stream | Có thể giữ descriptor, mapping hoặc trạng thái mở | Đóng đối tượng sở hữu |
| Thread pool và task executor | Giữ thread hoặc công việc đang chạy | Shutdown/close có phối hợp |
| Lock hoặc transaction | Cần kết thúc theo nghiệp vụ và thứ tự xác định | `unlock()` / commit / rollback trong `finally` |

Không phải đối tượng Java nào cũng phải được đóng. `String`, collection, phần lớn POJO và array thông thường do GC quản lý. Việc xây dựng cơ chế `close()` giả cho mọi đối tượng làm mã phức tạp không cần thiết. Hãy tập trung vào đối tượng thật sự **sở hữu** tài nguyên cần release.

### 1.1. Một ví dụ lỗi do dựa vào GC

Giả sử ứng dụng xử lý hàng nghìn file và không đóng stream:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

static byte[] readFile(Path path) throws IOException {
    InputStream input = Files.newInputStream(path);
    return input.readAllBytes(); // Stream không được đóng
}
```

Ứng dụng có thể chạy ổn trong thử nghiệm nhỏ, vì stream cuối cùng không còn được tham chiếu và một số implementation có cơ chế dọn dẹp nội bộ. Nhưng sau nhiều vòng xử lý, số file descriptor có thể tăng nhanh hơn GC có thể thu hồi hoặc dọn dẹp. Hệ thống có thể báo lỗi không mở được file hoặc chạm giới hạn handle.

Sửa bằng `try-with-resources`:

```java
static byte[] readFile(Path path) throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        return input.readAllBytes();
    }
}
```

Bây giờ stream được đóng khi khối `try` kết thúc, kể cả khi `readAllBytes()` ném exception.

## 2. Finalization là gì và vì sao cần loại bỏ phụ thuộc?

### 2.1. Cơ chế `finalize()` truyền thống

Trong Java cũ, một lớp có thể ghi đè phương thức `Object.finalize()` để yêu cầu JVM chạy code dọn dẹp trước khi thu hồi đối tượng. Ví dụ kiểu cũ:

```java
class LegacyNativeResource {
    private long nativeHandle;

    @Override
    @SuppressWarnings("deprecation")
    protected void finalize() throws Throwable {
        try {
            if (nativeHandle != 0L) {
                releaseNative(nativeHandle);
                nativeHandle = 0L;
            }
        } finally {
            super.finalize();
        }
    }

    private static native void releaseNative(long handle);
}
```

Đây là **mẫu cần migration**, không phải mẫu để áp dụng trong mã mới. Phương thức `finalize()` không được gọi ngay khi biến ra khỏi scope; GC quyết định lúc nào một đối tượng có thể được xử lý. Trong một số tình huống JVM có thể kết thúc trước khi finalizer chạy.

Các vấn đề chính:

- **Không xác định thời điểm:** quá nhiều file hoặc native handle có thể bị giữ lâu dù đối tượng Java không còn được dùng.
- **Không bảo đảm chạy:** JVM không cam kết finalizer luôn được thực thi trước khi tiến trình kết thúc.
- **Chi phí GC và độ trễ:** đối tượng có finalizer cần quy trình xử lý riêng, làm việc thu hồi phức tạp hơn.
- **Thứ tự không xác định:** finalizer của hai đối tượng liên quan không nhất thiết chạy theo thứ tự mà logic giải phóng yêu cầu.
- **Khó xử lý lỗi:** exception trong finalizer không cung cấp đường truyền lỗi đáng tin cậy về nơi sử dụng tài nguyên.
- **Rủi ro an toàn và tính đúng đắn:** object resurrection và việc chạy code trên đối tượng chưa hoặc không còn ở trạng thái hợp lệ có thể tạo ra hành vi khó kiểm soát.

Không nên dùng `System.gc()`, `System.runFinalization()` hoặc tạo nhiều object để “ép” finalizer chạy. Những lời gọi này không tạo hợp đồng giải phóng tài nguyên tin cậy.

### 2.2. Vòng đời finalization trong các bản Java

Finalization đã bị cảnh báo từ lâu; `Object.finalize()` được đánh dấu deprecated từ Java 9. JEP 421 tiếp tục deprecate finalization **for removal** trong lộ trình JDK 18, nhấn mạnh việc di chuyển sang giải phóng có kiểm soát. Các bản JDK có thể cung cấp tùy chọn vô hiệu hóa finalization nhằm giúp phát hiện sự phụ thuộc; khả năng và cú pháp tùy chọn cần được đối chiếu với bản JDK đang chạy.

Khi chuyển JDK, không được suy luận rằng vì mã vẫn biên dịch thì finalization vẫn là hợp đồng được hỗ trợ lâu dài. Một dependency cũ có thể còn ghi đè `finalize()` mà ứng dụng không biết.

### 2.3. Phân biệt finalization với `final` và `finally`

Ba khái niệm dễ bị nhầm:

- **`finalize()`:** hook dọn dẹp cũ liên quan đến GC; không nên dùng để quản lý tài nguyên mới.
- **`final`:** modifier giúp hạn chế gán lại biến, override method hoặc kế thừa lớp tùy vị trí; không có tác dụng tự đóng tài nguyên.
- **`finally`:** khối code chạy khi thoát khỏi `try` theo quy tắc exception thông thường; có thể dùng để đóng tài nguyên thủ công nhưng `try-with-resources` thường rõ ràng hơn.

Ví dụ `finally` truyền thống:

```java
InputStream input = Files.newInputStream(path);
try {
    consume(input);
} finally {
    input.close();
}
```

Mẫu này gần với giải phóng xác định thời điểm hơn `finalize()`, nhưng còn rủi ro exception khi `close()` che mất exception gốc. `try-with-resources` xử lý vấn đề đó thuận tiện hơn.

## 3. `AutoCloseable`, `Closeable` và `try-with-resources`

### 3.1. Hợp đồng của `AutoCloseable`

`AutoCloseable` được giới thiệu từ Java 7, khai báo phương thức `close()`. Một đối tượng triển khai interface này có thể khai báo trong phần resource của `try-with-resources`:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

`java.io.Closeable` kế thừa `AutoCloseable` và có hợp đồng `close()` ném `IOException`, phù hợp các lớp I/O. Cả hai interface đều cho phép `try-with-resources` xử lý đóng tự động.

Chọn interface theo loại resource:

| Tình huống | Interface gợi ý |
|---|---|
| Stream và resource I/O có lỗi liên quan I/O | `Closeable` |
| Transaction, native session, scope hoặc resource bất kỳ | `AutoCloseable` |
| API đã có type kế thừa một trong hai interface | Giữ contract hiện có; tránh tạo interface đóng mới không cần thiết |

Phương thức `close()` của một lớp có thể thu hẹp checked exception bằng cách khai báo ngoại lệ cụ thể hơn hoặc không khai báo checked exception. Thiết kế API nên thống nhất semantics: việc đóng có thể thất bại không, đóng nhiều lần được không, và method nào còn hợp lệ sau khi đóng.

### 3.2. `try-with-resources` đóng ngay khi rời scope

Ví dụ sử dụng hai resource:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static void copyText(Path source, Path target) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(source, StandardCharsets.UTF_8);
         BufferedWriter writer =
                 Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {

        String line;
        while ((line = reader.readLine()) != null) {
            writer.write(line);
            writer.newLine();
        }
    }
}
```

Khi khối kết thúc, Java đóng resource theo **thứ tự ngược với thứ tự khai báo**: `writer` trước, rồi `reader`. Nếu khởi tạo resource thứ hai thất bại, resource thứ nhất đã tạo thành công vẫn được đóng.

Phạm vi resource phải tương ứng với vùng code có quyền sở hữu nó. Không dùng object sau khi scope đã đóng.

### 3.3. Java 9 cho phép sử dụng biến resource đã khai báo

Từ Java 9, `try-with-resources` cho phép khai báo resource bên ngoài rồi tham chiếu vào phần resource nếu biến là `final` hoặc effectively final:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static String firstLine(Path path) throws IOException {
    BufferedReader reader = Files.newBufferedReader(path);

    try (reader) {
        return reader.readLine();
    }
}
```

Cơ chế này hữu ích khi migration code có bước khởi tạo riêng, nhưng cần bảo đảm scope và owner rõ ràng. Sau khối `try`, không tiếp tục sử dụng `reader` vì nó đã đóng.

### 3.4. Exception và suppressed exceptions

Giả sử quá trình đọc thất bại, đồng thời `close()` cũng ném exception. Với `try-with-resources`, exception trong body thường được giữ làm exception chính; lỗi khi đóng được đính kèm vào `getSuppressed()`.

```java
try (AutoCloseable resource = acquireResource()) {
    performOperation(resource);
} catch (Exception error) {
    System.err.println("Primary error: " + error);

    for (Throwable suppressed : error.getSuppressed()) {
        System.err.println("Close error: " + suppressed);
    }

    throw error;
}
```

Trong logging production, nên ghi cả exception chính và suppressed exceptions để không bỏ sót lỗi khi cleanup. Tránh ghi đè exception chính bằng một exception mới chỉ chứa thông báo chung. Với nhiều resource, thứ tự đóng đảo ngược và nhiều close error có thể được đính kèm.

### 3.5. Tự xây dựng lớp có thể đóng

Một wrapper đơn giản có thể quản lý một resource I/O:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class FileReaderSession implements AutoCloseable {
    private final InputStream input;
    private boolean closed;

    public FileReaderSession(Path path) throws IOException {
        this.input = Files.newInputStream(
            Objects.requireNonNull(path, "path")
        );
    }

    public int read() throws IOException {
        if (closed) {
            throw new IllegalStateException("Session is closed");
        }
        return input.read();
    }

    @Override
    public void close() throws IOException {
        if (!closed) {
            closed = true;
            input.close();
        }
    }
}
```

Sử dụng:

```java
try (FileReaderSession session = new FileReaderSession(path)) {
    System.out.println(session.read());
}
```

Ví dụ đơn giản này giả định resource không được dùng đồng thời từ nhiều thread. Nếu `read()` và `close()` có thể chạy đồng thời, một cờ boolean không đủ để bảo đảm an toàn; cần quy định thread confinement hoặc thiết kế đồng bộ hóa phù hợp.

## 4. Quyền sở hữu tài nguyên: ai chịu trách nhiệm đóng?

Một trong những lỗi phổ biến sau khi chuyển khỏi finalization là có nhiều nơi cùng nghĩ rằng nơi khác sẽ gọi `close()`.

### 4.1. Ownership phải đi cùng vòng đời

Có thể phân biệt ba vai trò:

- **Owner:** tạo hoặc nhận chuyển giao quyền sở hữu, chịu trách nhiệm đóng đúng một lần theo contract.
- **Borrower:** được phép sử dụng resource trong phạm vi xác định, nhưng không tự đóng nếu không được giao quyền.
- **Factory/provider:** tạo resource và công bố rõ consumer có cần đóng hay không.

Ví dụ factory trả về stream:

```java
static InputStream openConfig(Path path) throws IOException {
    return Files.newInputStream(path);
}
```

Caller nhận resource mới và phải đóng:

```java
try (InputStream input = openConfig(path)) {
    loadConfiguration(input);
}
```

Ngược lại, một method chỉ mượn stream không nên tự đóng nếu contract không cho phép:

```java
static int countBytes(InputStream borrowed) throws IOException {
    int count = 0;
    while (borrowed.read() != -1) {
        count++;
    }
    return count;
}
```

Ở ví dụ sau, caller vẫn sở hữu stream và quyết định đóng. Việc “đóng giúp” bất ngờ có thể phá hỏng chuỗi xử lý phía sau.

### 4.2. Không trả về tài nguyên đã đóng

Đây là lỗi thường gặp:

```java
static InputStream incorrect(Path path) throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        return input; // Trả về handle đã đóng!
    }
}
```

Nếu muốn caller đọc stream, trả trực tiếp và ghi rõ trách nhiệm đóng. Nếu muốn method sở hữu hoàn toàn việc đọc, trả về dữ liệu đã được đọc trước khi scope kết thúc.

### 4.3. Tài nguyên được chia sẻ và vòng đời ứng dụng

Không thể áp dụng `try-with-resources` cho mọi shared resource tại mỗi lời gọi. Ví dụ, connection pool hoặc client dùng chung thường sống suốt vòng đời service. Cần có owner ở cấp ứng dụng (lifecycle manager, dependency-injection container hoặc service coordinator), đóng khi service shutdown có kiểm soát.

Quan trọng là **quyền đóng chỉ có một nơi điều phối**, dù nhiều thành phần cùng mượn tài nguyên. Nếu một request đóng nhầm HTTP client chia sẻ, các request khác có thể thất bại.

### 4.4. Tài nguyên bất đồng bộ

Với xử lý bất đồng bộ, scope của task có thể dài hơn scope method đã tạo resource. Không được đóng ngay sau khi submit nếu task còn dùng resource:

```java
// Sai: task có thể dùng stream sau khi khối try kết thúc.
try (InputStream input = Files.newInputStream(path)) {
    executor.submit(() -> process(input));
}
```

Có hai hướng an toàn:

1. Worker task tự mở và đóng resource trong scope của nó.
2. Owner điều phối bảo đảm resource chỉ được đóng khi tất cả task liên quan đã hoàn tất, có cơ chế cancellation và shutdown rõ ràng.

Nếu dùng callback hoặc reactive stream, cần ghi rõ người sở hữu subscription, kết nối và cancel token. Việc tài nguyên đi qua nhiều thread không làm GC trở thành cơ chế cleanup đáng tin cậy.

## 5. Migration từ `finalize()` sang đóng tường minh

### 5.1. Ví dụ mã trước migration

Giả sử lớp cũ giữ một native handle:

```java
public class LegacySession {
    private long handle;

    public LegacySession() {
        handle = NativeApi.open();
    }

    public void send(byte[] payload) {
        NativeApi.send(handle, payload);
    }

    @Override
    @SuppressWarnings("deprecation")
    protected void finalize() throws Throwable {
        try {
            NativeApi.release(handle);
        } finally {
            super.finalize();
        }
    }
}
```

Ở đây `NativeApi` là lớp giả định mô tả JNI binding. Mẫu này có thể giữ native handle rất lâu và không cung cấp cách đóng theo nghiệp vụ.

### 5.2. Chuyển sang `AutoCloseable`

Phiên bản mới quản lý handle tường minh:

```java
import java.util.concurrent.atomic.AtomicLong;

public final class NativeSession implements AutoCloseable {
    private final AtomicLong handle;

    public NativeSession() {
        long acquired = NativeApi.open();
        if (acquired == 0L) {
            throw new IllegalStateException(
                "Native session could not be opened"
            );
        }
        this.handle = new AtomicLong(acquired);
    }

    public void send(byte[] payload) {
        long current = handle.get();
        if (current == 0L) {
            throw new IllegalStateException("Session is closed");
        }
        NativeApi.send(current, payload);
    }

    @Override
    public void close() {
        long previous = handle.getAndSet(0L);
        if (previous != 0L) {
            NativeApi.release(previous);
        }
    }
}
```

Sử dụng:

```java
try (NativeSession session = new NativeSession()) {
    session.send(payload);
}
```

`AtomicLong.getAndSet(0L)` giúp một lần gọi `close()` chiếm quyền release handle và các lần đóng tiếp theo không giải phóng cùng handle thêm lần nữa. Đây là một ví dụ về tính **idempotent**.

Tuy nhiên, `send()` và `close()` có thể race nếu được gọi từ các thread khác nhau. Thread có thể đọc được handle trước khi thread khác release. Với native handle thật, cần thiết kế lifetime đồng bộ: giới hạn mỗi session trong một thread, dùng khóa, reference count có kiểm soát hoặc cơ chế đếm thao tác đang chạy. Không coi `AtomicLong` một mình là đủ để bảo vệ mọi use-after-free.

Ngoài ra, hàm `NativeApi.release` có thể ném exception. Hợp đồng `close()` cần quy định lỗi đó được lan truyền, ghi nhận hay chuyển thành exception nào; tránh để handle ở trạng thái có thể dùng lại sau khi đã cố gắng release.

### 5.3. Khởi tạo thất bại một phần

Một wrapper native phức tạp có thể cấp phát nhiều handle trong constructor. Nếu bước thứ hai thất bại, đối tượng chưa được tạo hoàn chỉnh nên caller không thể gọi `close()` trên nó. Constructor phải dọn dẹp các resource đã cấp phát trước khi ném lỗi.

Ví dụ nguyên tắc:

```java
static NativeBundle openBundle() {
    long primary = NativeApi.openPrimary();

    try {
        long secondary = NativeApi.openSecondary(primary);
        return new NativeBundle(primary, secondary);
    } catch (RuntimeException | Error failure) {
        NativeApi.releasePrimary(primary);
        throw failure;
    }
}
```

Nếu cleanup cũng có thể ném lỗi, cần giữ exception gốc và bổ sung lỗi cleanup bằng suppressed exception khi thích hợp. Code trên minh họa hướng ownership; class và native methods là các thành phần giả định của ví dụ, không phải API có sẵn trong JDK.

### 5.4. Tiến hóa API để caller có thời gian chuyển đổi

Khi lớp cũ là public API, thay đổi yêu cầu caller gọi `close()` là thay đổi hợp đồng hành vi. Có thể thực hiện theo giai đoạn:

1. Bổ sung `AutoCloseable` hoặc một factory trả về resource có khả năng đóng, giữ constructor cũ trong giai đoạn chuyển tiếp nếu bắt buộc.
2. Viết rõ trong Javadoc rằng caller sở hữu resource và phải đóng.
3. Cập nhật mọi caller nội bộ sang `try-with-resources`.
4. Bổ sung logging/metrics phát hiện resource leak có kiểm soát.
5. Khuyến nghị consumer bên ngoài nâng phiên bản và sửa code.
6. Chạy integration test với ứng dụng tiêu thụ thực tế.
7. Loại bỏ dependency vào finalization khi toàn bộ caller được cập nhật.

Không nên xóa finalizer mà chưa có đường giải phóng mới trong public API. Ngược lại, không nên giữ finalizer vĩnh viễn như cách bù cho những caller không gọi `close()`; cần có lộ trình loại bỏ hoặc phương án fallback không phụ thuộc vào finalization.

## 6. `Cleaner`: cơ chế dự phòng cho tài nguyên native

### 6.1. Cleaner làm được gì?

`java.lang.ref.Cleaner` (Java 9+) cho phép đăng ký một cleaning action chạy sau khi đối tượng được đăng ký trở thành phantom reachable, hoặc khi ứng dụng gọi `Cleanable.clean()`. Cleaner hỗ trợ một hướng thay thế finalization để dọn dẹp dự phòng tài nguyên ngoài heap.

Nhưng Cleaner **không bảo đảm thời điểm** và cũng không bảo đảm action sẽ chạy trước khi JVM dừng. Vì vậy, với file, socket, connection hoặc native handle cần release kịp thời, hãy tiếp tục dùng `close()` và `try-with-resources` làm đường chính. Cleaner phù hợp làm “lưới an toàn” khi caller quên đóng, chứ không phải cơ chế quản lý vòng đời nghiệp vụ.

### 6.2. Mẫu Cleaner kết hợp `AutoCloseable`

Mẫu sau giữ cleaning state tách khỏi đối tượng owner để tránh việc action vô tình giữ tham chiếu mạnh đến chính owner:

```java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicLong;

public final class NativeBuffer implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private final AtomicLong address;

        State(long address) {
            this.address = new AtomicLong(address);
        }

        @Override
        public void run() {
            long previous = address.getAndSet(0L);
            if (previous != 0L) {
                NativeApi.freeMemory(previous);
            }
        }
    }

    private final State state;
    private final Cleaner.Cleanable cleanable;

    public NativeBuffer(long bytes) {
        long address = NativeApi.allocateMemory(bytes);
        if (address == 0L) {
            throw new IllegalStateException("Allocation failed");
        }

        this.state = new State(address);
        this.cleanable = CLEANER.register(this, state);
    }

    public long address() {
        long current = state.address.get();
        if (current == 0L) {
            throw new IllegalStateException("Buffer is closed");
        }
        return current;
    }

    @Override
    public void close() {
        cleanable.clean();
    }
}
```

`NativeApi` là lớp giả định đại diện cho native allocator; ví dụ không phải trình quản lý bộ nhớ đầy đủ và không giải quyết việc một thread đang dùng địa chỉ khi thread khác gọi `close()`.

Điểm chính của thiết kế:

- `State` là một object riêng, không giữ tham chiếu mạnh tới `NativeBuffer`.
- `Cleaner.register(this, state)` đăng ký cleaning action với owner.
- `close()` gọi `cleanable.clean()` để release **ngay tại đường xử lý tường minh**.
- `AtomicLong.getAndSet(0L)` giúp tránh gọi free hai lần khi action đã chạy.
- Nếu caller quên đóng và owner trở thành phantom reachable, Cleaner *có thể* thực hiện action sau đó.

### 6.3. Những giới hạn của Cleaner

Không nên dùng Cleaner để:

- Commit hoặc rollback một transaction dựa trên outcome của nghiệp vụ.
- Bảo đảm socket hoặc file được đóng ngay khi request kết thúc.
- Giữ SLA về thời gian giải phóng connection pool.
- Thực hiện thao tác cần thứ tự đóng nhiều tài nguyên liên quan.
- Chạy logic phức tạp phụ thuộc vào service khác đã có thể shutdown.
- Chuyển exception cleanup về caller để xử lý nhất quán.

Cleaning action chạy trên thread quản lý Cleaner và không nên phụ thuộc vào UI, request context hoặc thread-local state. Nếu action giữ owner làm referent vẫn reachable, action có thể không bao giờ được kích hoạt tự động. Nếu action ném exception, khả năng quan sát lỗi thường kém hơn đường gọi `close()` trực tiếp.

Đối với resource quan trọng, phương pháp tốt hơn là kiểm soát ownership và đo leak thay vì trông chờ Cleaner chữa lỗi thiết kế.

## 7. `ReferenceQueue`, phantom reference và các trường hợp đặc biệt

Java có các loại reference như weak, soft và phantom reference cùng `ReferenceQueue`. Chúng phục vụ quản lý khả năng reachability và các cơ chế liên quan đến GC.

`PhantomReference` có thể được dùng để biết một đối tượng đã đạt mức phantom reachability và điều phối cleanup cho một resource bên ngoài. Tuy nhiên, xây dựng một bộ quản lý reference đúng đắn đòi hỏi:

- Giữ `PhantomReference` ở nơi có thể truy cập cho đến khi được xử lý.
- Có queue consumer và cơ chế shutdown.
- Tách metadata cleanup khỏi object referent.
- Xử lý tính đồng thời, hủy đăng ký và idempotence.
- Chấp nhận rằng tiến trình có thể kết thúc trước khi queue được xử lý.

Đa số ứng dụng nên dùng `Cleaner` nếu cần fallback thay vì tự xây reference queue. Đặc biệt, không dùng weak reference để thay thế hành động đóng tài nguyên: weak reference chỉ ảnh hưởng reachability, không cung cấp resource-lifecycle contract.

## 8. Các API Java dễ bỏ sót `close()`

### 8.1. `Files.lines`, `Files.list`, `Files.walk`

Một số method của `java.nio.file.Files` trả về `Stream` gắn với resource hệ điều hành. Terminal operation như `count()` hoặc `forEach()` **không tự động đóng stream**. Hãy bọc stream trong `try-with-resources`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countNonEmptyLines(Path path) throws IOException {
    try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
```

Với duyệt directory:

```java
static long countJavaFiles(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths
            .filter(Files::isRegularFile)
            .filter(path -> path.toString().endsWith(".java"))
            .count();
    }
}
```

Nếu trả stream ra ngoài, caller phải là owner và chịu trách nhiệm đóng. Đừng đóng stream trong method rồi trả stream đã bị invalid cho caller.

### 8.2. JDBC resource

Một mô hình an toàn với JDBC:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

static int countActiveUsers(DataSource dataSource)
        throws SQLException {

    String sql = "SELECT COUNT(*) FROM users WHERE active = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setBoolean(1, true);

        try (ResultSet rows = statement.executeQuery()) {
            rows.next();
            return rows.getInt(1);
        }
    }
}
```

Với connection pool, `Connection.close()` thường trả connection về pool thay vì đóng TCP connection vật lý ngay lập tức; chi tiết tùy implementation. Caller vẫn phải gọi `close()` khi xong việc để tránh làm cạn pool.

Đối với transaction, cần phân biệt đóng connection với commit hoặc rollback. Nên điều phối transaction bằng code rõ ràng hoặc transaction manager, bảo đảm rollback khi thao tác thất bại. Đừng trông chờ `close()` luôn ngầm commit hay rollback theo cách nghiệp vụ cần.

### 8.3. `ExecutorService` và thread pool

Trong Java hiện đại, `ExecutorService` hỗ trợ `close()` và có thể dùng với `try-with-resources` trong những release phù hợp. Nhưng đóng executor không giống đóng file: nó liên quan đến vòng đời công việc và có thể chờ task hoàn thành.

Với executor sống suốt đời ứng dụng, owner ở cấp service cần quản lý shutdown, cancellation, timeout và xử lý task chưa hoàn tất. Không đóng executor ngay sau khi submit nếu task được thiết kế chạy bất đồng bộ lâu hơn scope hiện tại.

### 8.4. Resource từ thư viện bên thứ ba

Các SDK client, HTTP client, database session, file-system provider, compression library và native binding có thể có API đóng riêng. Không được giả định mọi resource đều triển khai `AutoCloseable`.

Khi nâng phiên bản thư viện, kiểm tra release note về vòng đời:

- Một factory trước đây trả resource dùng chung nay có thể trả resource thuộc sở hữu caller.
- Một method `close()` có thể chuyển từ no-op sang giải phóng socket hoặc worker thread.
- Một client có thể cần gọi `shutdown()`, `dispose()` hoặc `release()` thay vì `close()`.
- Một API tạo lazy stream có thể đòi caller đóng sau khi terminal operation.
- Một framework DI có thể tự đóng bean khi application context dừng; caller không nên đóng thủ công giữa request.

Đọc hợp đồng ownership của đúng phiên bản dependency, thay vì suy ra từ tên class.

## 9. Foreign Function & Memory API và resource scope

Java 21 cung cấp Foreign Function & Memory API ở trạng thái preview; đến Java 22 API trở thành chính thức. Các lần nâng cấp giữa những release này cần kiểm tra thay đổi API khi ứng dụng dùng FFM.

Với API chính thức, `Arena` quản lý vòng đời của vùng nhớ:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ArenaExample {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(
                ValueLayout.JAVA_LONG
            );

            segment.set(ValueLayout.JAVA_LONG, 0, 123L);

            long value = segment.get(ValueLayout.JAVA_LONG, 0);
            System.out.println(value);
        }
    }
}
```

Khi arena đóng, các segment được cấp phát trong scope đó không còn hợp lệ để truy cập theo contract API. Cách này thể hiện rõ resource lifetime và giảm việc tự quản lý địa chỉ native bằng số nguyên.

Một số loại arena có lifetime khác nhau, ví dụ shared arena cho phép truy cập từ nhiều thread nhưng vẫn cần đóng có kiểm soát; automatic arena có lifetime do reachability/GC quyết định. Khi cần release tài nguyên đúng thời điểm, ưu tiên arena có thể đóng tường minh thay vì dựa vào automatic cleanup.

Không chia sẻ `MemorySegment` vượt ra ngoài vòng đời arena. Nếu một async task cần segment, owner phải giữ arena hợp lệ cho đến khi task kết thúc và phối hợp việc đóng.

## 10. Thiết kế `close()` đúng trong hệ thống thực tế

### 10.1. Idempotence và trạng thái đóng

Thông thường, gọi `close()` nhiều lần không nên giải phóng cùng native pointer hai lần. `Closeable` mô tả hành vi đóng lặp không có tác dụng; với `AutoCloseable` nói chung, idempotence là khuyến nghị quan trọng nhưng không phải mọi implementation đều bảo đảm.

Một lớp quản lý state nên xác định:

- `OPEN`: resource sẵn sàng sử dụng.
- `CLOSING`: quá trình release đã bắt đầu; method sử dụng mới không được cấp phép.
- `CLOSED`: release hoàn tất hoặc handle không còn hợp lệ.

Trong code concurrent, cần chọn cơ chế khóa hoặc state machine phù hợp. Chỉ đặt `closed = true` không tự giải quyết race condition với thao tác I/O đang chạy.

### 10.2. Thứ tự đóng resource phụ thuộc nhau

Nếu resource B sử dụng resource A, thông thường đóng B trước A. `try-with-resources` đóng theo thứ tự ngược nên có thể khai báo resource nền tảng trước, wrapper sau:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(sql);
     ResultSet results = statement.executeQuery()) {

    while (results.next()) {
        consume(results);
    }
}
```

Theo thứ tự này, ResultSet được đóng trước, rồi statement và connection. Đây là một lợi ích đáng kể so với việc dựa vào finalizer có thứ tự không xác định.

### 10.3. Hành vi khi đóng thất bại

`close()` có thể ném checked hoặc unchecked exception. Cần quyết định:

- Lỗi đóng có làm thao tác nghiệp vụ bị đánh dấu thất bại không?
- Resource có thể thử đóng lại không?
- Nếu đã release một phần, trạng thái object là gì?
- Có cần log, metric hoặc alert để phát hiện leak không?
- Khi nhiều resource cùng lỗi, exception nào được giữ làm primary?

Với file output, lỗi flush/close có thể đồng nghĩa dữ liệu chưa được ghi đầy đủ. Không nên âm thầm bỏ qua. Với một connection pool, lỗi trả connection có thể cần metric nhưng không nhất thiết làm lại transaction đã commit. Chính sách phụ thuộc hợp đồng từng resource.

### 10.4. Đóng không đồng nghĩa commit, unlock hoặc cancel

Một số resource không phải `AutoCloseable` dù vẫn cần release có thứ tự. `Lock` cần `unlock()` trong `finally`, transaction cần commit/rollback theo outcome, subscription cần cancel, còn job cần điều phối kết thúc.

Ví dụ dùng lock:

```java
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

Không cố biến mọi thao tác cleanup thành `AutoCloseable` nếu abstraction đó làm mất semantics của commit, rollback hoặc ownership. Cơ chế đóng tường minh là nguyên tắc; interface cụ thể phải phù hợp resource.

## 11. Rà soát codebase khi migration

### 11.1. Dấu hiệu cần tìm

Trong source code và dependency, ưu tiên nhận diện:

- Override của `finalize()` hoặc lời gọi `super.finalize()`.
- `System.runFinalization()` và code mong đợi GC giải phóng tài nguyên.
- `System.gc()` được gọi như một “biện pháp đóng tài nguyên”.
- `Cleaner` hoặc `ReferenceQueue` tự viết.
- File/socket/JDBC resource được tạo nhưng không có đường `close()`.
- `Files.lines`, `Files.list`, `Files.walk` được dùng mà thiếu try-with-resources.
- Wrapper native giữ `long handle`, `ByteBuffer`, pointer hoặc file descriptor.
- Factory trả resource có ownership không rõ.
- Async task dùng resource có lifetime ngắn hơn task.
- Resource toàn cục bị đóng từ request hoặc transaction cục bộ.

Có thể dùng tìm kiếm văn bản làm bước đầu:

```shell
rg -n "finalize\\s*\\(|runFinalization\\s*\\(" src
rg -n "System\\.gc\\s*\\(" src
rg -n "Files\\.(lines|list|walk|find)\\s*\\(" src
rg -n "newInputStream|newOutputStream|getConnection" src
rg -n "Cleaner|PhantomReference|ReferenceQueue" src
```

Tìm kiếm chuỗi không thay thế phân tích luồng dữ liệu. Một resource có thể được đóng ở framework lifecycle, trong wrapper, hoặc qua một method khác; cũng có thể được mở gián tiếp bởi SDK. Hãy xác định ownership trước khi sửa.

### 11.2. Lập bảng inventory

| Vị trí | Resource | Owner hiện tại | Cơ chế cleanup | Rủi ro | Hướng migration |
|---|---|---|---|---|---|
| ImportService | InputStream | Method gọi | Không đóng | Cạn file descriptor | Try-with-resources |
| LegacyNativeBridge | Native handle | Object có finalizer | finalize | Leak và shutdown không xác định | AutoCloseable + Cleaner fallback |
| DataRepository | JDBC Connection | Request | Đóng ở một số nhánh | Cạn connection pool | Try-with-resources/transaction manager |
| ReportExporter | Files.lines Stream | Caller không rõ | Terminal operation | Descriptor bị giữ | Chuyển ownership hoặc trả dữ liệu |
| SharedClientFactory | HTTP client dùng chung | Application | Request đóng nhầm | Lỗi liên request | Lifecycle owner cấp ứng dụng |

Bảng trên minh họa cách ghi nhận; tên class không đại diện cho repository cụ thể. Mục tiêu là làm rõ nơi tạo, nơi sử dụng cuối cùng và nơi đóng resource.

## 12. Lộ trình migration có kiểm soát

### Giai đoạn 1: Đo baseline

Trước khi sửa code, thu thập:

- Phiên bản JDK và vendor thực tế.
- Số file descriptor/handle đang mở.
- Tỷ lệ dùng connection pool và timeout chờ connection.
- Native memory và direct buffer usage.
- Thread count, executor queue và hoạt động shutdown.
- Lỗi I/O, connection leak warning và GC pressure.
- Test hiện có cho startup, shutdown, cancellation và exception path.

Baseline giúp nhận biết migration có thực sự giảm giữ tài nguyên hay không và phát hiện hành vi mới ngoài ý muốn.

### Giai đoạn 2: Xác định owner và contract

Với mỗi resource, chọn một owner duy nhất và quy định:

1. Ai tạo hoặc nhận resource?
2. Ai được sử dụng và trong bao lâu?
3. Ai chịu trách nhiệm đóng?
4. Có được chia sẻ giữa thread hoặc request không?
5. Nếu constructor hoặc operation thất bại thì resource được đóng ở đâu?
6. Có cần cơ chế fallback khi caller quên đóng không?

Không viết wrapper cleanup trước khi trả lời được những câu hỏi này.

### Giai đoạn 3: Thay finalizer bằng API đóng

- Với local resource, chuyển sang `try-with-resources`.
- Với wrapper sở hữu native handle, thêm `AutoCloseable` và method `close()` rõ ràng.
- Với shared client, đóng ở application lifecycle.
- Với async resource, giữ owner sống cho đến khi task kết thúc.
- Với native memory, cân nhắc FFM Arena có phạm vi đóng tường minh.
- Với legacy finalizer, bỏ code phụ thuộc vào GC sau khi đường đóng đã bao phủ tất cả caller; chỉ cân nhắc Cleaner fallback nếu có yêu cầu phù hợp.

### Giai đoạn 4: Cập nhật consumer và tài liệu API

Sửa caller, ví dụ từ:

```java
LegacySession session = new LegacySession();
session.send(payload);
// Không có thao tác đóng
```

sang:

```java
try (NativeSession session = new NativeSession()) {
    session.send(payload);
}
```

Trong Javadoc, nêu rõ type implement `AutoCloseable`, bên nào sở hữu việc đóng và object có còn dùng được sau `close()` hay không.

Đối với thư viện public, thêm ghi chú migration để consumer không quên sửa call sites. Nếu cần thời gian chuyển tiếp, sử dụng deprecation và release note để mô tả thời điểm thay đổi hợp đồng.

### Giai đoạn 5: Kiểm thử trong môi trường đích

Chạy lại unit và integration test trên JDK đích, tập trung vào:

- Đường đi thành công.
- Exception trong body.
- Exception trong `close()`.
- Khởi tạo thất bại một phần.
- Đóng lặp.
- Truy cập sau khi đóng.
- Concurrent use và close.
- Cancellation/timeout.
- Shutdown có task đang chạy.
- Dữ liệu ghi ra file có flush/close thành công.

Nếu tổ chức cần xác minh không còn phụ thuộc finalization, cân nhắc chạy trong cấu hình JVM có finalization bị vô hiệu hóa **nếu runtime hỗ trợ**, đồng thời đối chiếu tùy chọn với JDK/vendor cụ thể. Kết quả test phải dựa trên khả năng đóng tường minh chứ không chỉ vào việc một flag được chấp nhận.

### Giai đoạn 6: Rollout và quan sát

Triển khai tăng dần. Theo dõi file descriptor, connection pool, native memory, CPU/GC, latency và lỗi shutdown. Nếu leak tăng, xác định resource owner và đường exception thay vì thêm lời gọi `System.gc()`.

Giữ khả năng rollback khi nâng JDK và thay thư viện native cùng lúc, nhưng cần bảo đảm thay đổi dữ liệu hoặc protocol không ngăn được rollback. Với API public, truyền đạt rõ contract `close()` đến các consumer trước khi loại bỏ hành vi cũ.

## 13. Ví dụ kiểm thử vòng đời resource

Có thể viết một fake resource để kiểm tra `try-with-resources` đóng cả khi code ném exception:

```java
import java.util.concurrent.atomic.AtomicInteger;

final class TrackedResource implements AutoCloseable {
    private final AtomicInteger closeCount;

    TrackedResource(AtomicInteger closeCount) {
        this.closeCount = closeCount;
    }

    void work() {
        throw new IllegalStateException("Operation failed");
    }

    @Override
    public void close() {
        closeCount.incrementAndGet();
    }
}
```

Đoạn sử dụng:

```java
AtomicInteger closes = new AtomicInteger();

try (TrackedResource resource = new TrackedResource(closes)) {
    resource.work();
} catch (IllegalStateException expected) {
    // Xử lý lỗi của operation.
}

if (closes.get() != 1) {
    throw new AssertionError("Resource was not closed exactly once");
}
```

Kiểm thử này xác minh property về vòng đời mà không cần gọi GC. Đối với resource thật, bổ sung test tích hợp đo file descriptor, kiểm tra native memory, xác nhận connection được trả về pool hoặc dùng mock/spy để kiểm tra lệnh release.

Không cần viết test dựa vào `System.gc()` rồi chờ finalizer chạy; loại test đó dễ không ổn định và chứng minh sai hợp đồng. Với Cleaner fallback, có thể kiểm tra hành vi khi gọi `Cleanable.clean()` tường minh nhưng không dựa vào thời gian GC để xác nhận tính đúng đắn nghiệp vụ.

## 14. Sai lầm thường gặp

**Chỉ thay `finalize()` bằng `Cleaner`.** Cleaner cũng không bảo đảm thời điểm chạy. Hãy thêm `close()` và chuyển caller sang ownership rõ ràng; dùng Cleaner nếu cần fallback.

**Nghĩ `try-with-resources` chỉ dùng cho file.** JDBC, native Arena, resource scope và nhiều đối tượng khác cũng có thể triển khai `AutoCloseable`.

**Đóng resource trong method được gọi nhưng không sở hữu nó.** Borrower tự đóng có thể làm hỏng caller và các thành phần khác. Ghi rõ owner.

**Trả resource ra ngoài sau khi đã đóng.** Dẫn đến lỗi truy cập và bug khó phát hiện. Nếu trả resource, chuyển giao quyền đóng.

**Dùng terminal operation rồi quên đóng file-backed stream.** `Stream.count()` hay `forEach()` không đồng nghĩa đóng `Files.lines` hoặc `Files.walk`.

**Dựa vào `final` để ngăn leak.** `final` chỉ giới hạn thay đổi reference, không tự release resource.

**Bỏ qua exception của `close()`.** Có thể che mất việc file output chưa được flush hoặc kết nối không được trả về pool.

**Giả định đóng lặp luôn an toàn.** Cần đọc contract `AutoCloseable` của type cụ thể và xây idempotence cho wrapper native nếu cần.

**Chỉ xử lý single-thread và bỏ qua race giữa sử dụng với đóng.** Cần thread confinement hoặc đồng bộ vòng đời.

**Dùng GC như một timer.** GC không thể thay thế timeout, cancellation hoặc shutdown logic của ứng dụng.

## 15. Checklist trước khi hoàn tất migration

### Mã nguồn và API

- [ ] Đã kiểm kê override `finalize()` và các lời gọi hỗ trợ finalization.
- [ ] Đã xác định resource nào cần đóng tường minh.
- [ ] Đã ghi rõ owner, borrower và thời điểm chuyển giao ownership.
- [ ] Đã bổ sung `AutoCloseable`/`Closeable` ở lớp sở hữu resource phù hợp.
- [ ] Đã chuyển local resource sang `try-with-resources`.
- [ ] Không trả về object đã đóng hoặc đóng nhầm resource dùng chung.

### Native resource và fallback

- [ ] Native handle được release theo lệnh gọi `close()` có chủ đích.
- [ ] Có cơ chế tránh double-free khi đóng lặp.
- [ ] Đã giải quyết race giữa operation và close nếu có concurrency.
- [ ] Đã xử lý cleanup khi constructor thất bại một phần.
- [ ] `Cleaner` chỉ là fallback và không giữ tham chiếu mạnh tới owner.
- [ ] Không phụ thuộc vào GC để commit, rollback hoặc đóng đúng hạn.

### Kiểm thử và vận hành

- [ ] Test đường thành công, exception, cancellation và shutdown.
- [ ] Test lỗi trong `close()` và kiểm tra suppressed exceptions khi phù hợp.
- [ ] Đã xác minh file-backed stream, JDBC connection và SDK client được đóng.
- [ ] Có số liệu về file descriptor, connection pool và native memory.
- [ ] Đã rà soát cơ chế finalization theo JDK/vendor đích.
- [ ] Có release note và hướng dẫn consumer nếu public API thay đổi.

## Kết luận

Finalization không phải hợp đồng đáng tin cậy để giải phóng tài nguyên. Bộ nhớ Java được GC quản lý, nhưng file descriptor, socket, JDBC connection, native handle và những tài nguyên bên ngoài heap cần vòng đời rõ ràng. Cách tiếp cận hiện đại là đặt trách nhiệm đóng vào owner, triển khai `AutoCloseable` hoặc `Closeable`, rồi dùng `try-with-resources` hoặc lifecycle manager để gọi `close()` theo thời điểm xác định.

Trong Java Advance Compatibility Migration, hãy tìm các phụ thuộc vào `finalize()`, sửa ownership trước khi thay cơ chế cleanup, xử lý đúng lỗi và concurrency, và kiểm tra ứng dụng trên JDK đích. `Cleaner` có thể bảo vệ một số trường hợp quên đóng, nhưng độ tin cậy và tính đúng đắn phải đến từ đường đóng tường minh và được xác minh qua kiểm thử vòng đời tài nguyên.

