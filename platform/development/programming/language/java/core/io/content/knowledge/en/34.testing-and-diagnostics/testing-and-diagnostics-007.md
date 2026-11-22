# Kiểm tra tài nguyên được đóng khi có lỗi trong Java I/O

## 1. Vì sao một chương trình đúng kết quả vẫn có thể bị rò rỉ tài nguyên?

Chương trình Java I/O thường mở **file stream, reader/writer, channel, socket, ZIP archive, directory stream** hoặc các tài nguyên giữ file descriptor/handle của hệ điều hành. Nếu một exception xảy ra giữa chừng mà tài nguyên không được giải phóng, hệ quả có thể là:

- File descriptor/socket handle không được trả lại; hệ thống xuất hiện lỗi như “Too many open files”.
- File bị giữ mở, gây khó khăn cho đổi tên/xóa trên một số hệ điều hành.
- Buffer đầu ra chưa được flush/finalize; dữ liệu ZIP/GZIP thiếu trailer hoặc metadata.
- Kết nối mạng vẫn mở, giữ tài nguyên phía client và server.
- Directory stream hoặc stream đọc file tiếp tục giữ handle dù business logic đã ngừng dùng.
- Trong hệ thống xử lý nhiều request, lỗi hiếm có thể tích lũy thành leak nghiêm trọng.

**Kiểm tra tài nguyên được đóng khi có lỗi** nghĩa là viết test buộc chương trình đi qua các nhánh lỗi, sau đó quan sát **ai chịu trách nhiệm close, close được gọi mấy lần, theo thứ tự nào, và exception nào được giữ lại**.

Đây không chỉ là “thêm `finally`”. Java hiện đại ưu tiên **`try-with-resources`** cho các đối tượng `AutoCloseable`, nhưng ta vẫn cần kiểm thử hợp đồng sở hữu và xử lý những tình huống phức tạp.

Mục tiêu sau bài:

1. Nắm đúng semantics của `try-with-resources` với normal exit, exception, `return`, `break` và lỗi khi mở tài nguyên.
2. Kiểm tra tài nguyên được close kể cả khi `read`/`write` ném `IOException`.
3. Hiểu primary exception và **suppressed exceptions** phát sinh từ `close()`.
4. Xây test double/fault injection đo lệnh đóng và thứ tự đóng, không phụ thuộc lỗi I/O ngẫu nhiên.
5. Nhận diện giới hạn của test double: `close()` được gọi không tự chứng minh OS handle thực sự đã được giải phóng.
6. Áp dụng cho stream wrappers, `FileChannel`, `ZipFile`, `DirectoryStream` và `Files.lines()/walk()/list()`.

## 2. Phân biệt close, flush và giải phóng thật sự

Ba khái niệm thường bị trộn:

| Khái niệm | Hợp đồng chính | Cách quan sát/test |
|---|---|---|
| `flush()` | Đẩy dữ liệu được buffer sang tầng tiếp theo theo hợp đồng của stream/writer | Fake output ghi nhận `flush`, kiểm tra dữ liệu đã tới underlying stream |
| `close()` | Kết thúc vòng đời tài nguyên; tùy API có thể flush/finalize trước khi giải phóng | Spy/tracker đánh dấu close, integration test kiểm tra trạng thái tài nguyên |
| Độ bền dữ liệu (durability) | Byte đã được đảm bảo lưu ổn định theo hợp đồng ứng dụng | Dùng API tương ứng như `FileChannel.force(...)`, chính sách filesystem và kiểm thử riêng |

`OutputStream.close()`/`Writer.close()` thường hoàn tất xử lý buffer của lớp đó trước khi đóng stream bên dưới. Nhưng **đóng không đồng nghĩa tất cả dữ liệu chắc chắn đã durable trên thiết bị**, cũng không đồng nghĩa peer mạng đã xác nhận xử lý.

Đối với kiểm thử close, nên xác định chính xác bất biến:

> Nếu một phương thức **sở hữu** một tài nguyên đã mở thành công, thì trên mọi đường thoát của phương thức — kể cả khi phát sinh lỗi — tài nguyên đó phải được yêu cầu đóng đúng hợp đồng.

“Đã yêu cầu đóng” là mức kiểm thử unit với spy. “Handle không còn giữ mở” có thể cần integration test theo OS/API. “Lưu dữ liệu bền” lại là yêu cầu khác.

## 3. \`AutoCloseable\`, \`Closeable\` và chủ sở hữu tài nguyên

`AutoCloseable` khai báo:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

`java.io.Closeable` mở rộng `AutoCloseable`, khai báo `close() throws IOException` và theo hợp đồng `Closeable`, gọi close trên đối tượng đã đóng không gây hiệu ứng mới. Nhưng **`AutoCloseable` thuần không bắt buộc close phải idempotent**; Javadoc khuyến khích implementer làm vậy nếu có thể.

Một số tài nguyên thường gặp:

| API | Tài nguyên | Ai nên đóng? |
|---|---|---|
| `FileInputStream`, `FileOutputStream` | File stream | Code tạo/mượn theo hợp đồng ownership |
| `BufferedInputStream`, `BufferedReader` | Wrapper và nguồn bên dưới | Thông thường đóng outer wrapper, nguồn bên dưới cũng được đóng |
| `InputStreamReader`, `OutputStreamWriter` | Bridge byte ↔ char và stream bên dưới | Thông thường chủ sở hữu của outer bridge |
| `FileChannel`, `SocketChannel`, `ServerSocketChannel` | File/socket channel | Thành phần đang sở hữu channel |
| `ZipFile`, `ZipInputStream` | ZIP container/stream | Thành phần mở ZIP |
| `DirectoryStream<Path>` | Directory handle | Thành phần gọi `Files.newDirectoryStream` |
| `Stream<String>` từ `Files.lines` | Open file stream | Code gọi `Files.lines` |
| `Stream<Path>` từ `Files.list`/`Files.walk` | Directory handles | Code tạo file-based stream |

**Ownership phải rõ ràng.** Nếu phương thức nhận một `InputStream` do caller truyền vào, có hai thiết kế hợp lệ nhưng không tương đương:

- **Callee owns:** phương thức nhận trách nhiệm đóng stream kể cả khi lỗi, phải nêu trong API contract.
- **Caller owns:** phương thức chỉ đọc/ghi và không đóng stream; caller sẽ đóng ở scope lớn hơn.

Không có quy tắc “hễ có InputStream là cứ close” trong mọi hoàn cảnh. Ví dụ nhiều API không nên tự đóng `System.in` hoặc stream dùng chung.

## 4. \`try-with-resources\`: nền tảng bảo vệ khi có exception

Cú pháp Java 17:

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    in.transferTo(out);
}
~~~

Đây là mã minh họa, cần `java.io.*`, `java.nio.file.*` và `Path source, target` đã xác định. Với một resource được khởi tạo thành công trong header, Java tự gọi `close()` khi thoát khỏi `try`, dù:

- Block chạy thành công tới cuối.
- Có `return` từ trong block.
- Có `break`/`continue` rời khỏi scope.
- Block ném `IOException`, `RuntimeException` hoặc `Error`.
- `catch`/`finally` đi sau cần xử lý kết quả.

### 4.1. Thứ tự tạo và đóng

Các resource trong header được **khởi tạo từ trái sang phải** và **đóng từ phải sang trái**.

~~~java
try (Tracked first = open("first");
     Tracked second = open("second")) {
    runBusinessLogic();
}
~~~

Đây là mã mô hình, `Tracked` và hai hàm factory tự định nghĩa. Logic:

~~~text
open first
open second
body
close second
close first
~~~

Nếu `runBusinessLogic()` thất bại, cả hai close vẫn được gọi theo thứ tự ngược. Nếu `close second` cũng ném lỗi, Java **vẫn cố close first**.

### 4.2. Nếu resource thứ hai không mở được?

Giả sử mở `first` thành công nhưng biểu thức khởi tạo `second` ném exception:

~~~text
open first   -> thành công
open second  -> ném IOException
close first  -> thực hiện tự động
body         -> KHÔNG chạy
~~~

Đây là một nhánh phải có trong test. Mã `try-with-resources` bảo đảm các resource **đã hoàn tất khởi tạo trước đó** được close. Nhưng nếu **constructor/factory của một resource tự nó cấp phát một native handle rồi ném trước khi trả về object**, header chưa nhận được resource đó; constructor/factory cần tự cleanup phần tài nguyên mở dở của nó.

### 4.3. Resource null

Biểu thức resource có thể cho ra `null`. Java không gọi `close()` trên resource `null`; tuy nhiên, dùng null để ngụ ý không có tài nguyên thường làm contract khó hiểu hơn và cần kiểm tra rõ khi API cho phép.

### 4.4. Biến đã tồn tại trong try-with-resources

Từ Java 9, biến local/field `final` hoặc **effectively final** có thể được đưa vào header:

~~~java
InputStream opened = Files.newInputStream(source);
try (opened) {
    consume(opened);
}
~~~

Đây là minh họa, cần `consume` được định nghĩa. Nó phù hợp khi phải khởi tạo trước một bước nhưng vẫn trao ownership của biến cho try-with-resources. Không sử dụng resource sau scope đã đóng.

## 5. Exception trong body và exception trong close: ai được ném?

Đây là điểm quan trọng nhất khi kiểm thử nhánh lỗi.

Giả sử:

1. `read()` ném `IOException("read-failed")`.
2. Khi cleanup, `close()` cũng ném `IOException("close-failed")`.

Với `try-with-resources`:

- Exception từ phần xử lý (`read-failed`) vẫn là **primary exception** được ném cho caller.
- Exception do close (`close-failed`) được gắn vào primary dưới dạng **suppressed exception**.
- Caller có thể xem chúng bằng `Throwable.getSuppressed()`.

~~~java
try (InputStream in = openFailingStream()) {
    consume(in); // có thể throw IOException("read-failed")
} catch (IOException ex) {
    System.err.println("Primary: " + ex);
    for (Throwable suppressed : ex.getSuppressed()) {
        System.err.println("During close: " + suppressed);
    }
}
~~~

Đây là **đoạn mã minh họa**, cần định nghĩa `openFailingStream()` và `consume(...)`. Không đánh đồng `Throwable.getCause()` với `getSuppressed()`:

| API | Thể hiện |
|---|---|
| `getCause()` | Nguyên nhân của một exception được bọc/chuỗi hóa bằng cause |
| `getSuppressed()` | Những exception bổ sung bị giữ lại khi xử lý/cleanup exception chính |
| `addSuppressed(...)` | Cho phép code tự đính exception cleanup, nhưng `try-with-resources` đã làm sẵn |

### Nếu block chạy bình thường mà close lỗi?

Trong trường hợp không có lỗi body, exception từ close là lỗi được ném ra. Nếu có **nhiều resource close đều lỗi**, exception từ resource đóng trước (resource ở bên phải header) là primary, và những close failures kế tiếp trở thành suppressed.

### Nếu cả open và close lỗi?

Nếu resource B không khởi tạo được nhưng A đã mở, exception từ khởi tạo B được giữ là primary; lỗi từ việc đóng A được đưa vào suppressed. Điều này bảo tồn thông tin về **lý do ban đầu làm quy trình thất bại**, thay vì để cleanup che mất nguyên nhân.

### Vì sao finally tự viết dễ sai?

Một cách dễ làm mất lỗi gốc:

~~~java
InputStream in = open();
try {
    doWork(in);         // ném IOException A
} finally {
    in.close();         // ném IOException B
}
~~~

Đây là phản ví dụ nếu chưa có suppressed handling: caller có thể chỉ nhận B, trong khi A đã bị che. `try-with-resources` có xử lý ưu tiên exception theo đặc tả ngôn ngữ; dùng nó thay vì viết lại logic này từ đầu.

## 6. Chiến lược kiểm thử: chủ động tiêm lỗi ở từng bước

Muốn bảo đảm close hoạt động khi lỗi, không nên chờ filesystem hoặc mạng tình cờ trục trặc. Hãy tạo **test double** hoặc fault-injection fixture mô phỏng lỗi ở từng điểm.

Một ma trận kiểm thử tối thiểu:

| Tình huống | Điều cần xác nhận |
|---|---|
| Xử lý thành công | Resource đã mở được đóng đúng một lượt sở hữu |
| `read` ném lỗi | Close được gọi; caller nhận lỗi read |
| `write` ném lỗi | Close được gọi; caller nhận lỗi write |
| `return` sớm | Close xảy ra trước khi return hoàn tất |
| `break`/`continue` rời scope | Close xảy ra khi thoát scope |
| Mở resource thứ hai lỗi | Resource thứ nhất vẫn được đóng |
| Hai resource cùng hoạt động | Đóng ngược thứ tự mở |
| `close` tự ném lỗi | Lỗi được truyền đúng; vẫn thử đóng các resource còn lại |
| Body + `close` cùng lỗi | Body là primary, close nằm trong suppressed |
| Wrapper gặp lỗi đọc | Đóng wrapper sẽ đóng nguồn theo ownership |
| Một resource bị close hai lần | Không phụ thuộc may mắn; xác định hợp đồng và kiểm tra số lượt |
| Hủy/timeout async I/O | Kiểm tra chính sách cancel và giải phóng khi mọi operation đã được giải quyết |

Nên phân biệt ba loại kiểm tra:

1. **Contract test tại unit level:** tài nguyên fake/spy xác nhận `close()` được gọi và ngoại lệ đúng.
2. **Integration test:** mở file/socket/ZIP thật, chạy fault scenario, kiểm tra hoạt động đóng qua API/OS.
3. **Diagnostic/soak test:** chạy nhiều lần lỗi để theo dõi file descriptors, memory, thread/socket count trong thời gian dài.

Không cần dùng một OS-specific lỗi “file đang mở không xóa được” làm **bằng chứng duy nhất**. Linux thường cho xóa tên một file ngay cả khi handle còn mở; Windows có quy tắc share/locking khác. Test portable nên dùng spy và xác nhận trạng thái theo API phù hợp.

## 7. Chương trình Java 17+ hoàn chỉnh kiểm tra bốn nhánh lỗi

Ví dụ dưới đây tự chứa tất cả fixture, không yêu cầu JUnit hoặc file thực trên đĩa. Nó mô phỏng:

- Lỗi trong body và lỗi `close` đồng thời.
- Hai resource được đóng **ngược** thứ tự mở.
- Thất bại khi mở resource thứ hai.
- `BufferedInputStream` đang đọc ném lỗi và vẫn đóng stream bên dưới.
- `return` sớm từ method nhưng resource vẫn được đóng.

**Tên tệp: `CloseOnFailureDemo.java`**

~~~java
import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

public class CloseOnFailureDemo {

    static final class Tracked implements AutoCloseable {
        final String name;
        final List<String> events;
        final boolean failClose;
        boolean closed;

        Tracked(String name, List<String> events, boolean failClose) {
            this.name = name;
            this.events = events;
            this.failClose = failClose;
            events.add("open:" + name);
        }

        @Override
        public void close() throws IOException {
            events.add("close:" + name);
            closed = true;

            if (failClose) {
                throw new IOException("close-" + name);
            }
        }
    }

    static Tracked failAcquire(List<String> events)
            throws IOException {
        events.add("acquire:failed");
        throw new IOException("acquire-failed");
    }

    static final class FailingInput extends InputStream {
        int closeCalls;

        @Override
        public int read() throws IOException {
            throw new IOException("read-failed");
        }

        @Override
        public void close() {
            closeCalls++;
        }
    }

    static String earlyReturn(List<String> events)
            throws IOException {
        try (Tracked r = new Tracked(
                "early", events, false)) {
            return "done";
        }
    }

    public static void main(String[] args) throws Exception {
        List<String> events = new ArrayList<>();

        try (Tracked first =
                     new Tracked("first", events, false);
             Tracked second =
                     new Tracked("second", events, true)) {

            events.add("body");
            throw new IOException("work-failed");

        } catch (IOException ex) {
            if (!"work-failed".equals(ex.getMessage())
                    || ex.getSuppressed().length != 1
                    || !"close-second".equals(
                            ex.getSuppressed()[0].getMessage())) {
                throw new AssertionError(
                        "Exception hierarchy incorrect");
            }

            System.out.println("primary=" + ex.getMessage());
            System.out.println("suppressed=" +
                    ex.getSuppressed()[0].getMessage());
        }

        System.out.println("close-order=" + events);

        List<String> acquisitionEvents = new ArrayList<>();
        try (Tracked held =
                     new Tracked("held", acquisitionEvents, false);
             Tracked unused = failAcquire(acquisitionEvents)) {

            throw new AssertionError("Not reached");

        } catch (IOException ex) {
            System.out.println(
                    "acquisition=" + ex.getMessage());
        }

        System.out.println(
                "acquisition-trace=" + acquisitionEvents);

        FailingInput raw = new FailingInput();

        try (BufferedInputStream wrapped =
                     new BufferedInputStream(raw)) {
            wrapped.read();

        } catch (IOException ex) {
            System.out.println(
                    "read-failure=" + ex.getMessage());
        }

        System.out.println(
                "wrapped-close-calls=" + raw.closeCalls);

        List<String> early = new ArrayList<>();
        System.out.println(
                "early-return=" + earlyReturn(early));
        System.out.println(
                "early-return-closed=" +
                        early.contains("close:early"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CloseOnFailureDemo.java
java CloseOnFailureDemo
~~~

**Stdout đã chạy kiểm tra với JDK:**

~~~text
primary=work-failed
suppressed=close-second
close-order=[open:first, open:second, body, close:second, close:first]
acquisition=acquire-failed
acquisition-trace=[open:held, acquire:failed, close:held]
read-failure=read-failed
wrapped-close-calls=1
early-return=done
early-return-closed=true
~~~

### Vì sao từng dòng quan trọng?

**`primary=work-failed`:** body ném IOException trước; đây là lỗi chính. `close()` lỗi không thay thế nó.

**`suppressed=close-second`:** resource `second` ném IOException khi close; Java vẫn giữ nguyên lỗi body và ghi nhận lỗi cleanup riêng.

**`close-order=...`:** resource được mở theo `first` rồi `second`, nhưng đóng theo `second` rồi `first`. Cả hai close được thử dù second ném lỗi.

**`acquisition=acquire-failed`:** `failAcquire` ném lỗi ở giai đoạn header; body không chạy, lỗi khởi tạo thứ hai được giữ.

**`acquisition-trace=...close:held`:** dù resource thứ hai không tạo được, `held` đã khởi tạo trước vẫn được đóng.

**`read-failure=read-failed`:** stream fake ném lỗi từ `read`. Đây là fault injection, không phải phải gây lỗi file thật.

**`wrapped-close-calls=1`:** `try-with-resources` đóng `BufferedInputStream`, và wrapper đóng `FailingInput` đúng một lần. Trong ví dụ, chỉ outer wrapper được khai báo là resource sở hữu để không phải close nguồn hai lần.

**`early-return-closed=true`:** dù method `earlyReturn` return một chuỗi, `Tracked.close` vẫn được gọi trước khi hoàn tất return.

### Giới hạn của test double

Trong demo, `Tracked.close()` đặt `closed=true` *trước khi* cố ý ném IOException. Điều này chỉ mô phỏng một hợp đồng do fixture định nghĩa. Với tài nguyên thực, `close()` ném lỗi có thể làm trạng thái hậu đóng phụ thuộc API/provider. Không tự kết luận **mọi native handle đã được giải phóng** chỉ vì spy nhận được `close()`.

Tương tự, kết quả `wrapped-close-calls=1` kiểm tra hành vi wrapper của ví dụ. Nếu production code vô tình giữ một tham chiếu khác tới cùng resource và gọi close tiếp, unit test ở riêng scope này không thể tự phát hiện mọi owner bên ngoài. Test cần dựng đúng cấu trúc sở hữu của ứng dụng.

## 8. Thiết kế test unit bằng spy và fault injection

### 8.1. Spy ghi lại số lần và thứ tự close

Một fake resource đơn giản:

~~~java
final class CloseSpy implements AutoCloseable {
    int closeCalls;
    boolean failOnClose;

    @Override
    public void close() throws IOException {
        closeCalls++;
        if (failOnClose) {
            throw new IOException("close failed");
        }
    }
}
~~~

Đây là một class minh họa với import `java.io.IOException`. Nếu class thật nhận resource từ caller, có thể inject `CloseSpy` thông qua một interface/factory thay vì dùng tài nguyên hệ điều hành thật. **Đừng chỉ assert `closeCalls >= 1` khi hợp đồng yêu cầu đúng một owner**; hãy assert đúng giá trị và kiểm tra không double-close vô ý.

### 8.2. Một hàm có hợp đồng ownership rõ ràng

~~~java
static void processOwned(InputStream in) throws IOException {
    try (in) {
        byte[] buffer = new byte[4096];
        while (in.read(buffer) != -1) {
            // Xử lý byte đã đọc.
        }
    }
}
~~~

Đây là một hàm minh họa cho **callee owns**. Test có thể truyền `InputStream` fake có `read(byte[],off,len)` cố ý ném lỗi sau n byte, rồi assert close vẫn được gọi.

Nếu giao diện yêu cầu **caller owns**, hàm cần khác:

~~~java
static void processBorrowed(InputStream in) throws IOException {
    byte[] buffer = new byte[4096];
    while (in.read(buffer) != -1) {
        // Chỉ dùng, KHÔNG tự đóng.
    }
}
~~~

Trong trường hợp borrowed, unit test nên xác nhận callee **không close**, còn caller phải đóng ở scope sở hữu ngoài. Không trộn hai hợp đồng.

### 8.3. Inject lỗi sau khi đã xử lý một phần

Để phát hiện leak xuất hiện khi tiến trình đã xử lý dữ liệu nhưng chưa hoàn thành, fake có thể:

- Cho phép `read()` thành công N lần rồi ném IOException ở lần N+1.
- Cho phép `write(...)` nhận một phần dữ liệu rồi ném lỗi.
- Gây lỗi parse sau khi stream được mở.
- Gây lỗi trong callback xử lý record/file entry.
- Gây lỗi khi finish ZIP/GZIP hoặc flush/close.

Test nên assert **bảo toàn exception gốc, số lần close, và cleanup của mọi resource đã được khởi tạo**, không chỉ kiểm tra method có ném IOException.

### 8.4. JUnit 5 — ví dụ assertThrows

Nếu project đã có JUnit Jupiter, một test có thể viết:

~~~java
@Test
void closesOwnedInputAfterReadFailure() {
    FailingInputStream fake = new FailingInputStream();

    IOException thrown = assertThrows(
            IOException.class,
            () -> service.processOwned(fake));

    assertEquals("read-failed", thrown.getMessage());
    assertEquals(1, fake.closeCalls());
}
~~~

Đây là **mã minh họa JUnit 5, không biên dịch độc lập**: `FailingInputStream`, `service` và phương thức của nó là fixture do project cung cấp; cần dependency/import Jupiter. Khai báo rõ test nhằm tránh nhầm nó với source Java SE 17 tự chạy. Không dùng assertions giả định nếu fake có cache đặc biệt làm thay đổi số lượt `read` thực tế.

## 9. Stream wrapper và đóng nguồn bên dưới

Các wrapper thường chuyển tiếp `close()` tới stream bên dưới. Ví dụ:

~~~java
InputStream raw = Files.newInputStream(path);
try (BufferedInputStream buffered = new BufferedInputStream(raw)) {
    consume(buffered);
}
~~~

Đây là mã minh họa với `Path path` và `consume(...)` được định nghĩa. Chủ sở hữu outer wrapper chịu trách nhiệm đóng; khi `BufferedInputStream.close()`, nó đóng underlying input.

Một cách nhiều người viết:

~~~java
try (InputStream raw = Files.newInputStream(path);
     BufferedInputStream buffered = new BufferedInputStream(raw)) {
    consume(buffered);
}
~~~

Điều này có thể dẫn đến **hai lần thử close raw**: đầu tiên do `buffered.close()`, sau đó TWR gọi `raw.close()` trong thứ tự ngược. Với `Closeable` implementations chuẩn, close thường idempotent, nhưng **không nên mặc định mọi wrapper/resource tùy biến chấp nhận double-close an toàn**. Trong code rõ ownership, thường chỉ cần outermost wrapper trong resource header, hoặc dùng một thiết kế chuyển ownership có kiểm soát.

### Reader/Writer và charset bridge

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    return reader.readLine();
}
~~~

Đây là mã minh họa bên trong method trả `String`, có `Path path`. `readLine` có thể trả null hay ném IOException; cả hai đường đi đều đóng reader.

`BufferedWriter` và `OutputStreamWriter` có thể tạo lỗi trong `flush/close` do bước encode và ghi byte. Vì vậy kiểm thử **write-time failure** và **close-time failure** đều quan trọng, nhất là với định dạng có trailer/finalization.

### Trường hợp wrapper không sở hữu underlying

Không phải mọi wrapper trong framework đều tự động được phép đóng stream bên dưới. Có API xây wrapper “close shield” để chặn close tới stream dùng chung. Nếu stream được **mượn** từ caller, wrapper hoặc factory phải thể hiện rõ **close có lan xuống nguồn hay không**. Test ownership ở lớp này để tránh vừa leak vừa vô tình đóng tài nguyên mà caller còn dùng.

## 10. Kiểm tra resource API khác nhau của Java NIO

### 10.1. FileChannel / SeekableByteChannel

`FileChannel` là `AutoCloseable`; khi read/write ném IOException, code phải đóng channel:

~~~java
try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ)) {
    ByteBuffer buffer = ByteBuffer.allocate(8192);
    while (channel.read(buffer) != -1) {
        buffer.clear();
    }
}
~~~

Đây là mã minh họa cho cách quản lý tài nguyên, không phải parser dữ liệu; khi dùng buffer có `remaining` bằng 0, `read` có thể trả 0 và logic trong ví dụ phải bảo đảm buffer được `clear()`. Trong production, cần xử lý no-progress đúng từng loại channel, không busy loop vô hạn.

Kiểm thử nên bảo đảm `channel.close()` được gọi nếu đoạn đọc/parse ném IOException. `Channel.isOpen()` cho phép kiểm tra trạng thái API sau close ở integration test. Nhưng thông tin “không còn handle trong OS” có thể cần quan sát độc lập khi vấn đề nằm ở native resources.

### 10.2. SocketChannel / ServerSocketChannel

Socket có thể lỗi ở `connect`, `accept`, `read`, `write` hoặc lúc close. Test cần xác định ai sở hữu accepted socket và listener:

- Đóng listener **không được giả định** là tự đóng mọi socket đã được accept.
- Khi accept thành công, mỗi accepted socket cần có cleanup path.
- Trên lỗi xử lý một client, không vô tình đóng toàn bộ listener nếu server còn tiếp tục phục vụ.
- Dùng loopback + port 0 cho integration test; đặt deadline để test không treo vô hạn.

Đo close với spy channel thường cần abstraction bởi các class channel có contract riêng; không nên tạo fake bằng cách override tùy tiện method final/native nếu test không phản ánh implementation thật.

### 10.3. ZipFile và ZipInputStream

ZIP là ví dụ quan trọng vì stream có thể lỗi **trong lúc giải nén** hoặc khi kiểm tra CRC:

~~~java
try (ZipFile zip = new ZipFile(zipPath.toFile())) {
    ZipEntry entry = zip.getEntry("data.txt");
    if (entry == null) {
        throw new IOException("Missing entry");
    }

    try (InputStream content = zip.getInputStream(entry)) {
        // Read / parse / validate content; exception có thể xảy ra.
    }
}
~~~

Đây là mã minh họa có `Path zipPath`. Khi exception xuất hiện, TWR đóng entry stream và ZipFile theo scope. Với `ZipInputStream`, đặt nó trong TWR và theo dõi việc đóng underlying stream nếu wrapper sở hữu nguồn đó. Với `ZipOutputStream` hoặc `GZIPOutputStream`, `close` có thể hoàn tất cấu trúc nén; đừng quên thử nhánh lỗi khi finalizing metadata.

### 10.4. DirectoryStream, Files.list, Files.walk và Files.lines

Không phải `Stream<T>` nào cũng giữ OS resource, nhưng **Stream do những Files API này trả về có thể giữ file/directory handle**. Cần đóng rõ:

~~~java
try (Stream<Path> paths = Files.list(directory)) {
    paths.forEach(System.out::println);
}
~~~

~~~java
try (Stream<Path> paths = Files.walk(directory)) {
    long count = paths.filter(Files::isRegularFile).count();
}
~~~

~~~java
try (Stream<String> lines = Files.lines(
        logFile, StandardCharsets.UTF_8)) {
    long count = lines.filter(line -> line.contains("ERROR"))
                      .count();
}
~~~

Đây là những đoạn minh họa, cần `java.nio.file.*`, `java.nio.charset.*`, `java.util.stream.Stream` và các biến `directory`/`logFile`. Chúng chưa phải các method độc lập và giá trị count chỉ là ví dụ sử dụng, không in output.

**Lưu ý:** `Stream.count()`/`findFirst()`/`forEach()` là terminal operation, nhưng **không thay cho `close()`** của file-backed stream. Nếu pipeline ném `UncheckedIOException` trong lúc iteration, TWR vẫn đóng stream.

### 10.5. Files.copy và API tự quản lý nguồn

Nếu API nhận `InputStream` từ caller, không mặc định nó sẽ đóng stream. Ví dụ `Files.copy(InputStream, Path, ...)` không thay thế scope sở hữu của input stream; caller cần đặt input vào TWR khi mình là owner.

Đừng suy luận quyền sở hữu chỉ vì phương thức đọc tới EOF; **EOF không đồng nghĩa đã close**.

## 11. Thử nghiệm lỗi ở giai đoạn khởi tạo: chỗ dễ leak

Một resource factory có thể gồm nhiều bước:

~~~java
Resource openResource(Path path) throws IOException {
    InputStream in = Files.newInputStream(path);
    // Bước khởi tạo khác có thể ném lỗi tại đây.
    return new Resource(in);
}
~~~

Đây là mã giả, `Resource` là type ứng dụng tự định nghĩa. Nếu bước giữa hai dòng thất bại trước khi object trả về, caller không nhận được `Resource` để close. Cần thiết kế factory chịu trách nhiệm cleanup của phần đã mở:

~~~java
Resource openResource(Path path) throws IOException {
    InputStream in = Files.newInputStream(path);
    boolean transferred = false;
    try {
        Resource resource = initializeOwnedResource(in);
        transferred = true; // Ownership chuyển sang resource trả về.
        return resource;
    } finally {
        if (!transferred) {
            in.close();
        }
    }
}
~~~

Đây là **mã minh họa**, không biên dịch độc lập vì `Resource` và `initializeOwnedResource(...)` do ứng dụng định nghĩa. Nó thể hiện ownership transfer, nhưng nếu cả khởi tạo và cleanup lỗi, block `finally` trên có thể **che mất lỗi khởi tạo**; production cần dùng nested try-with-resources hoặc thu thập suppressed exception để giữ nguyên nguyên nhân. Cách tốt hơn là giảm số bước manual transfer và đặt tài nguyên đã mở vào scope TWR càng sớm càng tốt.

Ví dụ kiểu cleanup rõ hơn bằng TWR:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    // Các bước chuẩn bị hoàn toàn tiêu thụ in trong scope này.
    return parseData(in);
}
~~~

Đoạn này minh họa khi `parseData` trả kết quả **không cần giữ stream**. Nếu `parseData` cần trả object sở hữu chính `in`, không thể đóng `in` trước return: phải thiết kế ownership transfer riêng.

### Kiểm thử khởi tạo mở dở

- Lỗi trước khi open: không có gì phải close.
- Open A thành công, open B thất bại: A phải close.
- Factory mở file rồi parse header lỗi: file phải close.
- Wrapper constructor lỗi sau khi đã nhận nguồn: factory/caller phải biết ai đang sở hữu nguồn và cleanup.
- Resource trả về thành công nhưng caller từ chối: caller phải close theo hợp đồng.

Không nên chỉ kiểm thử exception tại một vị trí; chính **điểm xảy ra lỗi** quyết định những tài nguyên nào đã tồn tại.

## 12. Test double không đủ để xác minh handle thật

Spy đo lời gọi Java rất hữu ích, nhưng có các giới hạn:

- `closeCalls==1` xác nhận method `close` được gọi trên fake, chưa chứng minh file descriptor được kernel trả lại.
- Spy không kiểm tra kernel buffer, delayed write, flush hoặc corruption.
- Một wrapper của thư viện khác có thể sở hữu thêm resource ngoài phạm vi fake.
- Lỗi đồng thời (thread khác đang đọc khi close) có thể tạo trạng thái và exception không xuất hiện ở unit test tuần tự.

### Integration test có giá trị gì?

Với file thực:

1. Dùng `Files.createTempFile` hoặc `Files.createTempDirectory` để có vùng test riêng.
2. Mở resource thật qua code production.
3. Tiêm lỗi parse/processing thay vì dựa vào lỗi thiết bị ngẫu nhiên.
4. Sau khi method kết thúc với exception, kiểm tra `isOpen()` (nếu API hỗ trợ), đọc/ghi lại file qua handle mới và cleanup tệp tạm.
5. Nếu cần, dùng OS-level tools để xem số descriptor trước/sau nhiều lần test.

**Không dùng khả năng xóa file như tiêu chí chung xuyên nền tảng**. Một số hệ điều hành cho unlink file đang mở, nên `Files.deleteIfExists` thành công **không chứng minh** handle đã close.

### Stress/soak test

Lỗi leak nhỏ khó nhìn thấy trong một lần chạy. Thử 1.000–10.000 lượt “open → lỗi đọc → cleanup” trong môi trường có quota phù hợp và quan sát:

- Số file handles/sockets.
- Số thread/task còn giữ resource.
- Thời gian và memory qua thời gian.
- Số request lỗi và số exception bị suppressed.
- Tình trạng directory stream, ZIP reader còn mở.

Kết luận dựa vào xu hướng ổn định và môi trường xác định, không dựa vào số cố định từ một OS/JDK khác. Mỗi test phải có cleanup riêng dù assertion thất bại.

## 13. Lỗi close trong hệ thống bất đồng bộ và nhiều thread

Với `AsynchronousFileChannel`, `AsynchronousSocketChannel` và các executor xử lý I/O, kết thúc một method chưa chắc kết thúc tất cả operation đang pending.

Cần xác định lifecycle:

~~~text
OPEN
  |
  +--> SUBMITTED OPERATIONS
  |          |
  |          +--> COMPLETED / FAILED / CANCELLED
  |
  +--> SHUTDOWN REQUEST
                |
         ngừng submit mới
                |
         chờ/giải quyết pending I/O theo contract
                |
             close channel
                |
             CLOSED
~~~

Một số API cho phép close channel trong khi operation đang pending; operation có thể kết thúc bất thường như `AsynchronousCloseException`. Unit test chỉ quan sát “close đã gọi ngay khi method throw” sẽ **không đủ** nếu trách nhiệm đóng thuộc một component chạy background; cần kiểm tra trạng thái shutdown sau khi các task/handler đã được giải quyết.

### Tránh flaky test bằng Thread.sleep

Không nên viết:

~~~java
startAsyncOperation();
Thread.sleep(200); // đoán operation đã xong
assertTrue(isClosed());
~~~

Đây là **phản ví dụ** không tự chạy. Sử dụng `CountDownLatch`, `CompletableFuture`, `Future.get(timeout, unit)` hoặc synchronization rõ ràng với **deadline** để chờ sự kiện close. Timeout là giới hạn cho test, không phải bằng chứng operation chắc chắn đã xong khi hết thời gian.

### Trường hợp thread bị interrupt

Java `try-with-resources` vẫn cleanup khi scope thoát vì exception do interrupt, nhưng bản thân API close có hợp đồng và ngoại lệ riêng. Với `AutoCloseable` tùy biến, Javadoc khuyến cáo không dùng `InterruptedException` làm lỗi close vì có thể gây hành vi khó dự đoán khi exception bị suppressed. Trong logic xử lý `InterruptedException`, cần quyết định có phục hồi interrupt flag và dừng theo chính sách ứng dụng hay không.

## 14. Thiết kế API dễ kiểm thử việc close

Một component I/O dễ test thường có các đặc điểm:

- **Constructor/factory inject được resource** hoặc resource factory, để mô phỏng lỗi đọc/ghi/close.
- **Hợp đồng owner rõ ràng**: ai tạo, ai dùng, ai đóng, ai chuyển ownership.
- **Không dùng global singleton cho stream mutable** nếu không thực sự cần chia sẻ.
- **Có giới hạn scope**: mở resource sát lúc dùng và close sớm khi không còn cần.
- **Không nuốt IOException**: lỗi body và lỗi cleanup được propagate/log theo chính sách.
- **Không phụ thuộc GC/finalizer/Cleaner làm cơ chế release chính**: chúng không cho thời điểm close xác định.
- **Không chỉ kiểm tra happy path**; thử lỗi khởi tạo, partial read/write, parser, close và return sớm.

Một phân tách điển hình:

~~~java
// Core logic làm việc trên stream do caller cho mượn:
static Result parse(InputStream borrowed) throws IOException {
    // Parse; không close borrowed.
    return decode(borrowed);
}

// Boundary nhận ownership của file stream:
static Result parseFile(Path path) throws IOException {
    try (InputStream owned = Files.newInputStream(path)) {
        return parse(owned);
    }
}
~~~

Đây là **mã minh họa**, `Result` và `decode` thuộc ứng dụng. Thiết kế này cho phép unit test `parse` bằng fake input và kiểm tra `parseFile` quản lý vòng đời tài nguyên mở từ filesystem. Không cần mock API static `Files.newInputStream` cho mọi test.

### Kiểm thử với các phương thức có trách nhiệm đóng rõ

Nếu một API có tham số `InputStream stream` và trách nhiệm **caller owns**, test nên khẳng định stream **vẫn open sau khi method kết thúc** (kể cả lỗi). Trái lại boundary `parseFile` phải khẳng định file stream được đóng khi bất kỳ lỗi nào xảy ra. Hai assertion khác nhau đều có thể đúng vì ownership khác nhau.

## 15. Vì sao kiểm thử close cần xét cả lỗi trong finally?

Khi bắt buộc phải dùng `finally` thủ công vì không có `AutoCloseable` phù hợp hoặc ownership phức tạp:

1. Giữ được exception gốc.
2. Không bỏ sót các resource cần cleanup nếu một close thất bại.
3. Không close tài nguyên mà method không sở hữu.
4. Không bỏ qua phần khởi tạo chưa hoàn tất.
5. Không giấu các suppressed exceptions trong logging/monitoring.
6. Tránh double-close resource có semantics không idempotent.

Với nhiều tài nguyên, tự viết chính xác tất cả trường hợp này khá dễ sai; **ưu tiên try-with-resources** bất cứ khi nào phù hợp. Nếu phải tự tổng hợp exception, có thể đính lỗi cleanup vào primary bằng `addSuppressed`, nhưng phải cẩn thận không tự suppress chính nó hoặc nhận null.

### Khi nào cần catch và khi nào không?

**Đơn giản và thường đủ:**

~~~java
try (InputStream in = Files.newInputStream(path)) {
    return parse(in);
}
~~~

Nếu caller hiểu IOException, không cần catch chỉ để log rồi throw lại. Nếu ứng dụng cần bổ sung ngữ cảnh, hãy preserve cause:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    return parse(in);
} catch (IOException ex) {
    throw new IOException("Cannot parse: " + path, ex);
}
~~~

Hai đoạn là **mã minh họa trong method trả giá trị parser**, `parse` cần được định nghĩa. Với exception được bọc, lỗi suppressed vẫn nằm trên exception nguyên nhân `ex`; công cụ log nên duyệt cause và suppressed để không bỏ mất lỗi close.

**Không nên:**

~~~java
catch (IOException ex) {
    return null; // nuốt lỗi, caller tưởng đọc thành công
}
~~~

Đây là phản ví dụ. Nuốt IOException khiến tài nguyên có thể đã được đóng nhưng dữ liệu đầu ra/flow logic không còn đáng tin. Nếu sản phẩm có fallback hợp lệ, phải thể hiện bằng return type rõ nghĩa thay vì biến lỗi thành thành công mơ hồ.

## 16. Checklist cuối cùng cho test và code review

Trước khi coi một đường I/O đã có cleanup đúng, kiểm tra:

- [ ] Xác định **resource owner** cho từng stream/channel/wrapper.
- [ ] Tất cả resource mở thành công nằm trong scope `try-with-resources` hoặc cleanup tương đương.
- [ ] Khi lỗi ở bước mở thứ hai, resource đầu vẫn đóng.
- [ ] Khi lỗi `read`, `write`, parse hoặc callback, cleanup vẫn chạy.
- [ ] Khi `return`/`break` hoặc early exit, cleanup chạy đúng.
- [ ] Nhiều resource đóng **ngược thứ tự**, một close lỗi không cản close những resource khác.
- [ ] Exception trong body là primary và lỗi close nằm ở `getSuppressed()`.
- [ ] Wrapper đóng underlying theo đúng ownership; không double-close resource không idempotent.
- [ ] File-backed streams từ `Files.lines/list/walk` được đóng ngay cả khi terminal operation ném lỗi.
- [ ] Fake/spy xác nhận **đã gọi close**; integration test kiểm tra thực tế cần thiết.
- [ ] Không suy luận đã release OS handle chỉ từ khả năng xóa file.
- [ ] Async tasks có deadline và synchronization để kiểm tra completion/close, không dùng sleep cố định.
- [ ] Exception và suppressed được log/propagate đủ để chẩn đoán.
- [ ] Test fixtures tự giải phóng tài nguyên ngay cả khi assertion thất bại.

## 17. Các lỗi thường gặp

1. **“Đã tới EOF là stream tự đóng.”** Sai: `read() == -1` không thay `close()`.
2. **“GC sẽ tự thu hồi file handle kịp thời.”** Không có thời điểm xác định; phải close.
3. **“Chỉ cần close ở happy path.”** Sai: error path còn dễ leak hơn.
4. **“Mỗi tài nguyên khai báo TWR đóng theo thứ tự mở.”** Sai: đóng theo thứ tự **ngược**.
5. **“Nếu open resource thứ hai thất bại thì first không được đóng.”** Sai với first đã khởi tạo thành công trong header.
6. **“Nếu close thứ hai ném lỗi, Java bỏ close thứ nhất.”** Sai: các resource đã mở vẫn được thử đóng.
7. **“Lỗi close luôn đè lên lỗi read.”** Sai với TWR; lỗi close được suppressed nếu đã có primary.
8. **“getCause và getSuppressed là một.”** Sai: cause chain và lỗi bổ sung khác nhau.
9. **“Spy.closeCalls==1 bảo đảm không còn OS descriptor.”** Sai: cần test thực/instrumentation theo mục tiêu.
10. **“Gọi close hai lần mọi AutoCloseable đều an toàn.”** Sai: AutoCloseable không yêu cầu idempotent.
11. **“Đóng BufferedInputStream không ảnh hưởng underlying stream.”** Thông thường wrapper đóng nguồn, cần hiểu ownership.
12. **“Một terminal operation trên Files.lines tự close stream.”** Sai: file-backed stream cần close.
13. **“Constructor/factory ném lỗi trước khi return sẽ luôn được TWR tự cleanup bên trong.”** Sai: phần tài nguyên mở dở chưa trao cho TWR phải do factory tự xử lý.
14. **“File xóa được chứng minh stream đã đóng.”** Sai trên OS có unlink semantics cho file đang mở.
15. **“Thread.sleep(100) là đủ để test close async.”** Không xác định; dùng synchronization và deadline.
16. **“close() không thể ném IOException.”** Sai: đặc biệt output flush/finalization có thể lỗi.
17. **“catch rồi return null là cách xử lý lỗi I/O an toàn.”** Thường làm mất ngữ cảnh và tạo thành công giả.
18. **“Đóng listener cũng tự đóng mọi accepted channel.”** Không nên giả định, mỗi channel cần ownership riêng.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Trong TWR có hai resource A, B. Body ném `IOException("read")`, còn `B.close()` ném `IOException("close")`. Exception caller thấy là gì?

**Đáp án:** `"read"` là primary; `"close"` nằm trong `getSuppressed()`. Java vẫn thử đóng A.

**Câu 2.** Resource A mở thành công nhưng khởi tạo B ném IOException. A có close không?

**Đáp án:** Có, nếu A là resource đã khởi tạo thành công trong header TWR. Body không chạy và exception khởi tạo B là primary.

**Câu 3.** Nếu method `return` bên trong TWR, close chạy trước hay sau khi method đã hoàn tất return?

**Đáp án:** Close chạy khi rời scope trước khi method hoàn tất trả kết quả. Nếu close ném exception, nó có thể khiến phương thức hoàn tất bằng exception thay vì return bình thường.

**Câu 4.** Tại sao unit test dùng CloseSpy vẫn cần một số integration test?

**Đáp án:** Spy kiểm tra lời gọi close theo contract của fake; không kiểm tra đầy đủ native handles, output finalization hay các resource bên trong implementation thật.

**Câu 5.** Tại sao `Files.lines(path).count()` không đủ để đảm bảo file đã đóng?

**Đáp án:** Terminal operation xử lý các phần tử, không cam kết đóng file-backed stream. Dùng TWR cho stream trả về.

**Câu 6.** Một service dùng `BufferedInputStream` bọc `System.in`. Service có nên mặc định đóng wrapper khi xong không?

**Đáp án:** Không thể quyết định nếu chưa biết ownership. Đóng wrapper thường đóng nguồn bên dưới; với `System.in` dùng chung, phải thiết kế borrowed ownership hoặc close-shield rõ ràng.

**Câu 7.** Close handler của một object có thể ném IOException. Unit test nên kiểm tra gì ngoài `closeCalls`?

**Đáp án:** Kiểm tra primary/suppressed exception, thứ tự close của các resource khác và phương thức có propagate lỗi đúng contract hay không.

**Câu 8.** Nếu một callback I/O bất đồng bộ đang pending và code yêu cầu shutdown, khi nào có thể kết luận cleanup hoàn tất?

**Đáp án:** Sau khi chính sách cancel/completion và đóng channel/resource đã được xác nhận bằng signal/synchronization có deadline; không thể suy luận chỉ từ việc method request shutdown trả về.

### Tài liệu chính thức Java 17

- [JLS `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3)
- [AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html)
- [Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed())
- [Files — lines, list, walk](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [BufferedInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html)
- [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html)
- [ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html)
