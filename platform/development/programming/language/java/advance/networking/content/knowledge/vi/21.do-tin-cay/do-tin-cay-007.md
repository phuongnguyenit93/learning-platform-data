# Đóng tài nguyên khi lỗi xảy ra giữa chừng và khôi phục cờ ngắt phù hợp

## Mục tiêu bài học

Trong lập trình mạng Java, một thao tác có thể thất bại **sau khi đã mở socket, stream, channel hoặc khởi tạo một vài tác vụ** nhưng trước khi xử lý xong dữ liệu. Nếu chỉ đóng tài nguyên ở nhánh thành công, ứng dụng sẽ rò file descriptor, socket, thread, buffer hoặc kết nối. Nếu xử lý `InterruptedException` bằng cách bỏ qua nó, các yêu cầu dừng tác vụ từ thread khác có thể bị mất và tiến trình shutdown trở nên khó đoán.

Bài này đặt hai quy tắc **độ tin cậy** cùng một chỗ:

1. **Resource ownership + cleanup:** tài nguyên nào đã được tạo thành công thì phải được giải phóng ở mọi đường thoát: thành công, lỗi I/O, lỗi parse, lỗi khi tạo tài nguyên tiếp theo, timeout hoặc bị hủy.
2. **Interrupt preservation:** khi một blocking operation ném `InterruptedException`, code nên **truyền tiếp ngoại lệ** nếu hợp đồng phương thức cho phép; nếu thực sự phải bắt và không truyền tiếp được, hãy **khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()`** rồi ngừng/hoàn trả control theo chính sách. Đừng nuốt tín hiệu và tiếp tục vòng lặp như chưa có gì.

Sau bài, bạn sẽ:

- Nắm `try-with-resources`, `AutoCloseable`/`Closeable`, cách Java **đóng theo thứ tự ngược** và tự dọn khi khối `try` ném lỗi.
- Biết trường hợp **tạo resource thứ hai thất bại** vẫn dọn resource đầu đã mở; tránh cấu trúc cấp phát nằm ngoài try/finally.
- Hiểu **primary exception**, **suppressed exceptions** khi cả body lẫn `close()` ném lỗi; đọc `Throwable.getSuppressed()` thay vì ghi đè nguyên nhân.
- Đóng socket/stream thật trên TCP loopback khi parser phát hiện frame sai giữa chừng, và kiểm chứng `isClosed()`.
- Phân biệt `Thread.currentThread().isInterrupted()` (không xóa cờ) với `Thread.interrupted()` (kiểm tra **và xóa** cờ).
- Hiểu những blocking methods như `CountDownLatch.await`, `Thread.sleep`, `Object.wait` thường **xóa cờ khi ném `InterruptedException`**.
- Viết mã Java 17+ thử nghiệm **dọn ServerSocket trước khi khôi phục interrupt flag**.
- Phân biệt tác động của interrupt lên `InterruptibleChannel`, `Selector`, socket cổ điển, `CompletableFuture` và `ExecutorService`.
- Thực hiện graceful shutdown với `shutdown`/`awaitTermination` và fallback `shutdownNow`, có thời hạn và giữ cờ ngắt đúng.
- Áp dụng checklist lỗi/cancel để tránh mất dữ liệu, bỏ orphan task hoặc tự retry thao tác mạng gây tác dụng phụ.

Bài gồm **bốn chương trình Java 17+ độc lập đã biên dịch/chạy**, dùng dữ liệu giả và loopback, không phụ thuộc Internet. Đây là nội dung cho mục **Độ tin cậy**; không biến yêu cầu dừng thread thành lời hứa rằng server xa chưa nhận request.

## 1. Vì sao “lỗi giữa chừng” nguy hiểm hơn lỗi trước khi bắt đầu?

Hãy xét một TCP handler:

~~~text
Chấp nhận kết nối ─► mở InputStream ─► đọc message ─► parse ─► ghi kết quả
         │                │                 │             │
         └────── nhiều tài nguyên đã được tạo / mượn ────┘
                                             └─ có thể lỗi
~~~

Nếu parser ném `IOException` ở bước thứ tư, các tài nguyên **đã tạo ở các bước trước** vẫn tồn tại trừ khi ứng dụng chủ động cleanup. Trong server chạy lâu, mỗi socket bị bỏ quên có thể tiêu tốn file descriptor, bộ đệm hệ điều hành và connection state; hàng nghìn lỗi nhỏ sẽ dẫn đến **resource exhaustion**.

Các đường thoát cần tính đến:

| Đường thoát | Ví dụ | Mối nguy nếu quên cleanup |
|---|---|---|
| Thành công | Đọc đủ frame và trả response | Socket/stream vẫn giữ dù request đã xong |
| Lỗi I/O | Peer reset, lỗi ghi, timeout | Socket tiếp tục mở hoặc task còn đợi |
| Lỗi protocol | Length prefix sai, JSON không hợp lệ | Bỏ dở frame, mất đồng bộ stream |
| Lỗi lúc cấp phát | File mở thành công nhưng socket tiếp theo không mở được | File descriptor đầu tiên bị rò |
| Lỗi trong callback | Exception từ task, listener, publisher | Future exceptional nhưng resource giữ nguyên |
| Interrupt | Worker đang `await`/`sleep` bị yêu cầu dừng | Nuốt interrupt, worker tiếp tục vô hạn |
| Lỗi lúc đóng | `close()` ném exception trong khi đã có lỗi chính | Mất dấu lỗi ban đầu nếu xử lý sai |
| Cạnh tranh shutdown | Thread khác đóng channel/socket đang dùng | Task nhận lỗi đóng bất đồng bộ, cần phân loại |

**Nguyên tắc sở hữu:** *Ai tạo ra tài nguyên thường chịu trách nhiệm đóng nó, trừ khi hợp đồng chuyển quyền sở hữu rõ ràng*. Nếu method chỉ **mượn** một `Socket` từ connection pool, không được tự đóng vì tưởng “đóng luôn cho sạch”. Nếu method nhận ownership của một accepted socket để phục vụ **duy nhất một client**, nó có thể dùng `try-with-resources` để đóng.

## 2. `AutoCloseable`, `Closeable` và try-with-resources

### 2.1. Những tài nguyên nào phù hợp?

- `java.lang.AutoCloseable`: interface có `close() throws Exception`, được hỗ trợ bởi cú pháp `try (resource)`. Không mọi implementation đều cam kết idempotent; đọc hợp đồng cụ thể.
- `java.io.Closeable`: interface kế thừa `AutoCloseable`, `close() throws IOException`. Ví dụ `InputStream`, `OutputStream`, `Reader`.
- `Socket`, `ServerSocket`, các `Channel`, `FileChannel` và nhiều stream là closeable; dùng `try-with-resources` thay vì thủ công trên mọi nhánh lỗi.
- `ExecutorService` của **Java 17** không phải một `AutoCloseable` để bạn tùy tiện đặt trong `try (pool)` như ở một số JDK mới hơn; nó phải được **shutdown** theo API executor và đợi nếu cần.

**Không phải mọi “tài nguyên” đều đóng bằng `close()`:** một `ExecutorService`, scheduled task, subscription hoặc future có chính sách lifecycle riêng. Một `CompletableFuture.cancel(true)` không tự thay thế việc đóng socket/stream bên ngoài.

### 2.2. TWR được biên dịch theo ý tưởng nào?

~~~java
try (InputStream in = Files.newInputStream(path)) {
    process(in);
}
~~~

Đây là **snippet**, cần import `java.io.*`, `java.nio.file.*`, và một hàm `process` do ứng dụng định nghĩa. Tương đương về **ý tưởng** với:

~~~java
InputStream in = Files.newInputStream(path);
try {
    process(in);
} finally {
    in.close();
}
~~~

Nhưng snippet `finally` thứ hai **không tái hiện đầy đủ** semantics quan trọng của try-with-resources khi **cả `process` và `close` cùng ném exception**. TWR còn giữ lỗi chính và đưa lỗi đóng vào `getSuppressed()`, thay vì có nguy cơ để close exception che mất exception của body.

TWR cũng xử lý **partial initialization** và **nhiều resources** đúng theo các quy tắc của Java Language Specification.

### 2.3. Thứ tự mở và đóng

~~~java
try (AutoCloseable a = openA();
     AutoCloseable b = openB();
     AutoCloseable c = openC()) {
    use(a, b, c);
}
~~~

Đây là mã **minh họa**: `openA/openB/openC/use` là các hàm giả định, không phải chương trình độc lập. Nếu cả ba tạo thành công:
- Mở theo thứ tự **A → B → C**.
- Đóng theo thứ tự **C → B → A** dù body thành công hay ném lỗi.

Nếu **B khởi tạo thất bại**:
- `C` không được khởi tạo.
- `A` **đã mở** nên phải được đóng.
- Ngoại lệ do khởi tạo B là lỗi chính; lỗi khi đóng A (nếu có) được **suppressed** theo semantics TWR.

Nhờ vậy, hãy bắt đầu `try (...)` **ngay khi nhận ownership**, thay vì tạo nhiều socket/stream bên ngoài rồi mới đến một lệnh `finally` dễ bỏ sót.

## 3. Primary exception và suppressed exception

### Khi body và close cùng thất bại

Ví dụ body ném `IOException("body failure")`; khi unwind, resource thứ hai và thứ nhất lại ném lỗi từ `close()`. Java ưu tiên:

1. **Primary exception:** lỗi body `body failure`.
2. **Suppressed #1:** close của resource **thứ hai** (đóng trước).
3. **Suppressed #2:** close của resource **thứ nhất** (đóng sau).

~~~text
body failure  ← primary
├── suppressed: close failure: second
└── suppressed: close failure: first
~~~

Đây là quy tắc **thông tin chẩn đoán**, không có nghĩa mọi close đều thành công. `getSuppressed()` rất hữu ích để tìm thứ tự sự cố khi kết nối/cả tài nguyên phụ cũng bị lỗi.

### Khi body thành công nhưng close thất bại

Nếu không có lỗi trong body, ngoại lệ của `close()` có thể trở thành **primary**. Với nhiều resources, lỗi close đầu tiên trở thành primary và các lỗi close tiếp theo được suppressed. Vì thế “tất cả request đã chạy xong” không có nghĩa cleanup hoàn toàn thành công.

### Không ghi đè lỗi body bằng một finally ném mới

Một bẫy:

~~~java
Socket socket = createSocket();
try {
    doNetworkWork(socket);
} finally {
    socket.close(); // Có thể ném IOException và che một lỗi đã xảy ra.
}
~~~

Đây là **snippet minh họa**, `createSocket`/`doNetworkWork` là hàm ứng dụng phải định nghĩa. Cách an toàn hơn khi bạn **sở hữu** socket:

~~~java
try (Socket socket = createSocket()) {
    doNetworkWork(socket);
}
~~~

TWR tự xử lý suppressed exceptions tốt hơn. Khi không thể dùng TWR vì ownership/lifecycle phức tạp, hãy viết `finally` cẩn thận, không nuốt hay thay lỗi chính, và ghi nhận lỗi cleanup riêng hoặc `addSuppressed` khi phù hợp.

## 4. Ví dụ A: lỗi trong body, lỗi khi đóng và lỗi giữa lúc mở resource

Chương trình **Java 17+ đầy đủ** sau mô phỏng tài nguyên có thể ném `IOException` khi đóng. Nó kiểm tra ba trường hợp:
- Body ném lỗi và **cả hai resources** cùng ném khi close.
- Khởi tạo resource thứ hai thất bại; resource đầu **vẫn được đóng**.
- Body thành công; cleanup vẫn diễn ra.

Lưu là **`ResourceFailureDemo.java`**:

~~~java
import java.io.IOException;

public class ResourceFailureDemo {
    static final class Tracked implements AutoCloseable {
        private final String name;
        private final boolean closeFails;

        private Tracked(String name, boolean closeFails) {
            this.name = name;
            this.closeFails = closeFails;
            System.out.println("open " + name);
        }

        static Tracked open(String name, boolean closeFails) {
            return new Tracked(name, closeFails);
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            if (closeFails) {
                throw new IOException("close failure: " + name);
            }
        }
    }

    static Tracked failAcquire() throws IOException {
        System.out.println("acquire second: fail");
        throw new IOException("acquire failed");
    }

    public static void main(String[] args) {
        try (Tracked first = Tracked.open("first", true);
             Tracked second = Tracked.open("second", true)) {
            System.out.println("body: fail");
            throw new IOException("body failure");
        } catch (IOException e) {
            System.out.println("primary: " + e.getMessage());
            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("suppressed: " + suppressed.getMessage());
            }
        }

        try (Tracked acquired = Tracked.open("acquired", true);
             Tracked missing = failAcquire()) {
            System.out.println("unreachable");
        } catch (IOException e) {
            System.out.println("acquire-primary: " + e.getMessage());
            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("acquire-suppressed: "
                    + suppressed.getMessage());
            }
        }

        try (Tracked success = Tracked.open("success", false)) {
            System.out.println("body: success");
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }
}
~~~

### Biên dịch, chạy

~~~bash
javac --release 17 -encoding UTF-8 ResourceFailureDemo.java
java ResourceFailureDemo
~~~

Stdout **đã được kiểm thử chính xác**:

~~~text
open first
open second
body: fail
close second
close first
primary: body failure
suppressed: close failure: second
suppressed: close failure: first
open acquired
acquire second: fail
close acquired
acquire-primary: acquire failed
acquire-suppressed: close failure: acquired
open success
body: success
close success
~~~

### Cần rút ra điều gì?

- **`close second` xảy ra trước `close first`:** resources bị đóng theo thứ tự đảo so với lúc mở.
- Lỗi body là **primary** dù cả hai `close()` ném lỗi; chúng hiện trong `getSuppressed()`, không bị mất.
- Khi `failAcquire()` ném, resource `acquired` được đóng tự động dù body còn chưa chạy.
- Nếu `close()` không ném lỗi, ta vẫn có đường cleanup bình thường sau body.
- Mã chỉ mô phỏng resource để output quyết định; kế tiếp sẽ dùng **TCP socket thật** trên loopback.

**Một quy tắc quan trọng:** đừng xử lý `getSuppressed()` như dấu hiệu “lỗi phụ không đáng quan tâm”. Lỗi đóng socket/file trong production có thể cần đo metrics/cảnh báo, nhưng **không được ghi đè thông tin lỗi chính**.

## 5. Ví dụ B: TCP socket gặp lỗi giữa lúc parse dữ liệu

Chương trình dưới đây mở **ServerSocket** trên loopback, tạo TCP client, chấp nhận connection thật, nhận một dòng `BAD` rồi cố kiểm tra nó có phải `OK` hay không. Vì frame không hợp lệ, parser ném `IOException` trước khi xử lý hoàn tất. Các socket và stream **vẫn phải được đóng**.

Không cần Internet, certificate hoặc chạy hai tiến trình riêng; tất cả trong **một JVM**, cổng do OS cấp tự động.

Lưu là **`SocketFailureDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class SocketFailureDemo {
    public static void main(String[] args) throws Exception {
        ServerSocket listener = null;
        Socket sender = null;
        Socket receiver = null;

        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {
            listener = server;
            try (Socket client = new Socket(
                    InetAddress.getByName("127.0.0.1"),
                    server.getLocalPort())) {
                sender = client;
                try (Socket accepted = server.accept();
                     BufferedReader input = new BufferedReader(
                         new InputStreamReader(
                             accepted.getInputStream(),
                             StandardCharsets.UTF_8))) {
                    receiver = accepted;
                    client.getOutputStream().write(
                        "BAD\n".getBytes(StandardCharsets.UTF_8));
                    client.getOutputStream().flush();
                    String frame = input.readLine();
                    if (!"OK".equals(frame)) {
                        throw new IOException("invalid frame: " + frame);
                    }
                }
            }
        } catch (IOException error) {
            System.out.println("request failed: " + error.getMessage());
        }

        System.out.println("sender closed: " + sender.isClosed());
        System.out.println("receiver closed: " + receiver.isClosed());
        System.out.println("listener closed: " + listener.isClosed());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 SocketFailureDemo.java
java SocketFailureDemo
~~~

Stdout đã quan sát được:

~~~text
request failed: invalid frame: BAD
sender closed: true
receiver closed: true
listener closed: true
~~~

### Phân tích ownership của ví dụ

- `ServerSocket server` thuộc main method. Khi rời outer `try`, listener được đóng.
- `Socket client` là phía chủ động kết nối, được mở **sau** listener và nằm trong TWR riêng.
- `Socket accepted` là kết quả `server.accept()`, tức một **kết nối đã chấp nhận** chứ không phải listener; nó được đóng bởi inner TWR.
- `BufferedReader input` bọc `accepted.getInputStream()` và được đóng theo TWR. Với những stream lấy từ `Socket`, đóng stream có thể đóng socket bên dưới; explicit TWR cho `accepted` vẫn làm rõ ownership và bảo vệ khi nguồn dữ liệu xử lý giữa chừng.
- Khi frame là `BAD`, `IOException` thoát khỏi inner block; resources được đóng trước khi catch ngoài cùng in lỗi.
- Ba biến `listener/sender/receiver` ở ngoài TWR trong demo chỉ để **kiểm tra `isClosed()` sau cleanup**; code production thông thường không cần giữ references tới socket đã đóng.

**Giới hạn:** ví dụ dùng `Socket` truyền thống với câu lệnh nối/accept trên loopback, không có socket read timeout vì dữ liệu `BAD\n` được gửi ngay trong cùng chương trình. Trong server thực cần `setSoTimeout`, input size/line length limits, framing/encoding validation, connection deadlines và giới hạn số client.

**Lỗi giữa chừng không phải tín hiệu retry bừa.** Parser fail vì frame không hợp lệ: trả protocol error/đóng connection theo policy. Việc tạo lại một socket rồi gửi cùng payload `BAD` vô hạn chỉ lãng phí tài nguyên.

## 6. Interrupt là tín hiệu hợp tác, không phải cách “giết” thread

Java interrupt là **cơ chế báo yêu cầu dừng/hủy** cho thread, không phải thao tác cưỡng chế cắt mọi công việc đang chạy. Gọi:

~~~java
worker.interrupt();
~~~

là yêu cầu đối với `worker`, **không** bảo đảm task lập tức kết thúc. Code đang thực thi CPU-bound phải chủ động kiểm tra trạng thái interrupt; code đang block trên một phương thức interruptible có thể được đánh thức theo hợp đồng phương thức ấy.

### Hai API kiểm tra cờ có tác dụng khác nhau

| Lệnh | Đối tượng được kiểm tra | Có tự xóa cờ? |
|---|---|---|
| `Thread.currentThread().isInterrupted()` | Thread hiện tại | **Không** |
| `worker.isInterrupted()` | Thread `worker` | **Không** |
| `Thread.interrupted()` | **Chỉ thread đang gọi** | **Có**, nó kiểm tra rồi xóa cờ |
| `Thread.currentThread().interrupt()` | Thread hiện tại | **Đặt lại cờ thành true** |

**Không dùng `Thread.interrupted()` chỉ để “log xem có bị ngắt chưa”** nếu bạn không muốn xóa tín hiệu. Một lần gọi `Thread.interrupted()` có thể khiến vòng lặp tiếp theo không thấy yêu cầu shutdown, trừ khi có interrupt mới hoặc bạn khôi phục cờ.

Ví dụ:

~~~java
boolean stillRequested = Thread.currentThread().isInterrupted();
~~~

Đây là phép đọc không phá hủy. Nếu đã chủ động sử dụng `Thread.interrupted()`, bạn phải hiểu rằng nó **consumes/clears** cờ theo tài liệu.

## 7. `InterruptedException`: tại sao phải khôi phục cờ?

Nhiều blocking calls khi bị interrupt sẽ:
1. Nhận thấy thread bị yêu cầu ngắt.
2. **Xóa interrupted status**.
3. Ném **`InterruptedException`** để caller ra quyết định.

Ví dụ `Thread.sleep`, `CountDownLatch.await`, `Object.wait`, `Thread.join` và `Future.get` có interruptible waiting semantics. Do đó, trong catch:

~~~java
try {
    latch.await();
} catch (InterruptedException interrupted) {
    System.out.println(Thread.currentThread().isInterrupted());
    // Với CountDownLatch.await bị interrupt, thường in false
}
~~~

Đây là **snippet** cần `latch` kiểu `CountDownLatch`. Dòng false không có nghĩa yêu cầu dừng đã “biến mất về nghiệp vụ”; exception **chính là tín hiệu** cần được tôn trọng.

### Hai chiến lược đúng (không áp dụng đồng thời một cách máy móc)

**Chiến lược A — truyền tiếp:** nếu method được phép `throws InterruptedException`, ưu tiên:

~~~java
void waitForSignal(CountDownLatch latch)
        throws InterruptedException {
    latch.await();
}
~~~

Không catch nên caller có thể xử lý. Thông thường **không cần tự restore flag trước khi rethrow** bởi exception được truyền lên như một tín hiệu ngắt rõ ràng. Để lớp trên quyết định hủy việc, restore cờ hoặc propagate cao hơn.

**Chiến lược B — không thể truyền checked exception:** khi method interface không cho `throws InterruptedException`:

~~~java
try {
    latch.await();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt(); // Bảo toàn yêu cầu dừng.
    return; // Hoặc throw một unchecked exception có cause.
}
~~~

Đây là snippet nằm trong một method trả `void` và có biến `latch`. Quan trọng: **đừng restore cờ rồi tiếp tục vòng lặp xử lý bình thường** nếu code không có chính sách tiếp tục sau interrupt; có thể gây một vòng lặp ném interrupt liên tục.

### Nếu cần wrap sang RuntimeException?

~~~java
try {
    latch.await();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Operation interrupted", interrupted);
}
~~~

Đây là snippet, cần `latch`. Exception giữ nguyên `cause` giúp debug; đồng thời cờ ngắt vẫn true để scheduler/caller khác biết yêu cầu dừng.

**Nếu khối đang sở hữu resources trong try-with-resources**, đặt catch bên ngoài `try (...)` để cleanup chạy **trước** khi quyết định restore flag/return/throw. Những close methods có thể phản ứng với interrupted status; quản lý thứ tự dọn tài nguyên và restore phù hợp với tài nguyên cụ thể.

## 8. Ví dụ C: cleanup ServerSocket trước khi restore interrupt flag

Chương trình sau mở **ServerSocket thật trên loopback** trong worker, báo đã sẵn sàng bằng `CountDownLatch` rồi **đợi vô hạn** trên một latch khác. Thread main đợi worker báo ready, gọi `worker.interrupt()`, sau đó join có timeout. Worker nhận `InterruptedException` từ `await()`, **TWR đóng ServerSocket trước khi bước vào catch**, ghi nhận flag đã clear, rồi khôi phục flag và thoát.

Dùng `AtomicBoolean`/`AtomicReference` để in kết quả quyết định **sau khi worker đã dừng**, không phụ thuộc thứ tự stdout của hai threads.

Lưu thành **`InterruptCleanupDemo.java`**:

~~~java
import java.net.InetAddress;
import java.net.ServerSocket;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class InterruptCleanupDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch waitForever = new CountDownLatch(1);
        AtomicBoolean flagBeforeRestore = new AtomicBoolean(true);
        AtomicBoolean flagAfterRestore = new AtomicBoolean(false);
        AtomicReference<ServerSocket> owned = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            try (ServerSocket listener = new ServerSocket(
                    0, 1, InetAddress.getByName("127.0.0.1"))) {
                owned.set(listener);
                ready.countDown();
                waitForever.await();
            } catch (InterruptedException interrupted) {
                // try-with-resources closed the ServerSocket before this catch.
                flagBeforeRestore.set(Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                flagAfterRestore.set(Thread.currentThread().isInterrupted());
            } catch (Exception unexpected) {
                failure.set(unexpected);
                ready.countDown();
            }
        }, "interrupt-demo-worker");

        worker.start();
        if (!ready.await(3, TimeUnit.SECONDS)) {
            worker.interrupt();
            throw new IllegalStateException("Worker did not become ready");
        }
        worker.interrupt();
        worker.join(3_000);
        if (worker.isAlive()) {
            waitForever.countDown();
            worker.interrupt();
            throw new IllegalStateException("Worker did not stop");
        }
        if (failure.get() != null) {
            throw new IllegalStateException(failure.get());
        }
        if (owned.get() == null) {
            throw new IllegalStateException("No ServerSocket created");
        }

        System.out.println("flag in catch before restore: "
            + flagBeforeRestore.get());
        System.out.println("flag after restore: "
            + flagAfterRestore.get());
        System.out.println("server socket closed: "
            + owned.get().isClosed());
    }
}
~~~

Biên dịch/chạy bằng Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 InterruptCleanupDemo.java
java InterruptCleanupDemo
~~~

Stdout thực tế:

~~~text
flag in catch before restore: false
flag after restore: true
server socket closed: true
~~~

### Vì sao ví dụ này không dùng `Thread.sleep` để đoán thời điểm?

`ready.countDown()` giúp main biết worker **đã mở ServerSocket** rồi mới gửi interrupt. Khi worker nhận interrupt ngay trước hoặc trong `waitForever.await()`, lời đợi vẫn nhận ra tín hiệu và ném `InterruptedException`. `worker.join(3_000)` giới hạn việc main chờ worker trong test; trường hợp thất bại được xử lý thay vì giữ process vô hạn.

**Thứ tự dọn:** worker rời `try (ServerSocket ...)` vì exception, socket được đóng, **sau đó** catch `InterruptedException` khôi phục cờ. Đây là kỹ thuật quan trọng cho cleanup khi hủy công việc network.

**Phân biệt yêu cầu dừng với kết quả của việc dừng:** `server socket closed: true` được kiểm chứng trong JVM, không chứng minh mọi request trước đây của một service đã commit dữ liệu hay clients ngoài đời đã nhận Close response. Trong production còn phải quản lý in-flight accepted sockets riêng, không chỉ listener.

### Khi task không được phép tự tạo Thread

Trong ứng dụng thực, thread thường do `ExecutorService` quản lý. Quy tắc vẫn vậy: khi task bị interrupt, dọn resources, không tiếp tục tạo request, truyền tiếp hoặc restore cờ phù hợp với API task. Đừng tắt tất cả worker pool chỉ vì **một** request bị lỗi cú pháp; phân biệt lỗi riêng của kết nối với shutdown toàn service.

## 9. Những loại I/O khác nhau phản ứng với interrupt khác nhau

**Không có một quy tắc duy nhất “mọi socket Java đều ném InterruptedException khi interrupt”.** Hợp đồng cụ thể của mỗi API quan trọng:

| API/hoạt động | Điều cần biết |
|---|---|
| `CountDownLatch.await()`, `Thread.sleep`, `Object.wait` | Interrupt thường dẫn tới `InterruptedException` và **cờ bị xóa** |
| `Future.get()` / `ExecutorService.awaitTermination` | Có thể ném `InterruptedException` trong lúc chờ, cần propagate/restore |
| `SocketChannel` / `FileChannel` thuộc `InterruptibleChannel` | Interrupt khi đang block có thể **đóng channel**, ném `ClosedByInterruptException` và **giữ cờ true** |
| Một thread khác gọi `channel.close()` lúc I/O đang block | Có thể nhận `AsynchronousCloseException`, không đồng nghĩa thread vừa bị interrupt |
| `Selector.select()` | Interrupt có thể làm select trả về nhanh với interrupted status **được đặt**, tương tự wakeup |
| `Socket` / `ServerSocket` truyền thống, JDK 17 | Không mặc định giả định `Thread.interrupt()` luôn ngắt `read/accept` ngay; dùng socket read timeout, đóng từ owner/controller hoặc API NIO thích hợp |
| `SocketTimeoutException` | Có thể là timeout do `setSoTimeout`; là subclass của `InterruptedIOException` nhưng **không** chứng minh thread đã bị interrupt |
| `InterruptedIOException` | I/O bị gián đoạn theo hợp đồng riêng, có `bytesTransferred` khi thích hợp; không mặc định giống `InterruptedException` |
| `CompletableFuture.cancel(true)` mặc định | Không trực tiếp quản lý/interrupt thread tính toán nền; tham số mayInterruptIfRunning **không có hiệu lực** trong base `CompletableFuture` |
| `HttpClient.sendAsync` (JDK implementation) | Future trả về có thể hỗ trợ yêu cầu hủy exchange; **không** coi cancellation là bằng chứng remote chưa xử lý request |

### `ClosedByInterruptException` là trường hợp quan trọng

Một NIO channel hỗ trợ `InterruptibleChannel` có thể bị **đóng** khi thread block trên nó bị interrupt. Java Javadoc cho `ClosedByInterruptException` nêu rõ status của thread lúc ấy vẫn được **đặt**.

Mã minh họa kiểu xử lý:

~~~java
try {
    channel.read(buffer);
} catch (ClosedByInterruptException interruptedIo) {
    // NIO đã đóng channel và cờ interrupt thường đang true.
    // Không tiếp tục đọc trên channel cũ.
    throw interruptedIo;
}
~~~

Đây là snippet cần `channel` kiểu `SocketChannel`/`FileChannel` phù hợp, `buffer` kiểu `ByteBuffer`, import `java.nio.channels.ClosedByInterruptException`. Không gọi `Thread.interrupted()` để “xóa cờ cho sạch” trước khi xử lý, vì như vậy có thể làm mất tín hiệu dừng.

### `AsynchronousCloseException` khác `ClosedByInterruptException`

Một thread A đọc channel; thread B quyết định đóng channel để dừng operation. A có thể nhận `AsynchronousCloseException` do **đóng từ thread khác**, không phải do interrupt status. Trong phân tích lỗi phải biết controller có đang shutdown hay không, tránh log “unexpected I/O error” thành incident nếu đây là đường dừng có chủ đích.

### `InterruptedIOException` không luôn là yêu cầu dừng thread

`SocketTimeoutException` kế thừa `InterruptedIOException`. Một `Socket.setSoTimeout(2000)` khiến read hết hạn có thể ném `SocketTimeoutException` mà **không ai gọi `Thread.interrupt()`**. Vì thế pattern:

~~~java
catch (InterruptedIOException e) {
    Thread.currentThread().interrupt();
}
~~~

**không đúng cho mọi tình huống**. Phải phân biệt read timeout với thực sự bị interrupt/cancel theo hợp đồng của API/operation, rồi mới quyết định restore interrupt. **Chỉ cần restore rõ ràng khi bạn đang catch `InterruptedException` đã xóa cờ, hoặc khi exception wrapping/contract đòi bảo toàn tín hiệu.**

## 10. Bị ngắt ≠ mất toàn bộ dữ liệu; cần chiến lược retry riêng

Hãy xét một client gửi frame TCP:

~~~text
client write request ──► server receive ──► server commit
        │                        │
        └─ timeout / cancellation xảy ra tại client
~~~

Client không nhận được ACK vì timeout/interrupt **không có nghĩa** server chưa xử lý request. Đặc biệt với POST tạo đơn hàng, nghiệp vụ tài chính hoặc message queue, retry vô điều kiện có thể gây **duplicate side effects**.

Một thiết kế đáng tin:
- Gắn **request/message ID** hoặc idempotency key theo hợp đồng server.
- Quản lý timeout ở tầng I/O và deadline end-to-end riêng.
- Phân loại lỗi có thể retry (transient) với lỗi permanent (invalid payload/auth).
- Nếu trạng thái remote không rõ, **query status** hoặc retry idempotent theo policy.
- Khi task bị interrupt vì shutdown, **không** bắt exception rồi bắt đầu retry kết nối như bình thường.
- Resource cleanup bảo đảm local socket/stream đóng, **không thay thế** distributed acknowledgment/transaction guarantee.

**Interrupt là tín hiệu hợp tác** nhằm giảm thời gian dừng, không phải transaction rollback hoặc một lệnh ép OS phải hủy tất cả network operations tức thì.

## 11. ExecutorService: shutdown/awaitTermination và cờ ngắt

Một server thực thường có worker pool cho nhiều kết nối. Khi shutdown có thứ tự, ta cần:
1. **Ngừng nhận/submit công việc mới**.
2. Gọi `executor.shutdown()` để không nhận task mới, cho tasks đã nhận hoàn tất.
3. Chờ với `awaitTermination(timeout, TimeUnit)`.
4. Nếu hết hạn, có thể gọi `shutdownNow()` để **cố interrupt tasks đang chạy và trả lại tasks chờ**.
5. Chờ một lần nữa có thời hạn nếu cần; nếu vẫn chưa dừng, báo rõ trạng thái.
6. Khi chính thread đang đợi bị `InterruptedException`, gọi `shutdownNow()` phù hợp và **khôi phục cờ** trước khi thoát.

**Khác với tài nguyên AutoCloseable:** `shutdownNow()` là **best effort**, các tasks không hợp tác có thể tiếp tục chạy. `isTerminated()` mới cho biết executor đã chấm dứt; `shutdown()` riêng lẻ không tự chờ.

### Ví dụ D: ExecutorShutdownDemo.java

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExecutorShutdownDemo {
    static void stop(ExecutorService pool) {
        pool.shutdown();
        try {
            if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                    System.out.println("pool: still running");
                }
            }
        } catch (InterruptedException interrupted) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<String> result = pool.submit(() -> "completed");
            System.out.println("task: " + result.get(3, TimeUnit.SECONDS));
        } finally {
            stop(pool);
        }
        System.out.println("pool terminated: " + pool.isTerminated());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 ExecutorShutdownDemo.java
java ExecutorShutdownDemo
~~~

Output đã kiểm thử:

~~~text
task: completed
pool terminated: true
~~~

### Những giới hạn của output

Trong demo, task nhanh và hợp tác nên `awaitTermination` trả true sớm, không in `pool: still running`. Không suy ra rằng pool mọi lúc đều dừng trong 3 giây: nếu task không kiểm tra interrupted status hoặc đang block trên API không hỗ trợ interrupt, `shutdownNow` có thể không hoàn tất đúng deadline.

**Tùy policy**, nếu shutdown còn pending sau grace period, bạn có thể:
- Ghi metrics/số thread còn sống và nâng cảnh báo.
- Đóng socket/channel do ứng dụng **sở hữu** để unblock I/O.
- Đảm bảo application shutdown không nhận task mới rồi thực hiện timeout global.
- Không tự gọi `System.exit()` như giải pháp mặc định của một library method.

Nếu `stop` bị interrupt, code đặt lại cờ ngắt. Caller có thể quan sát trạng thái ấy và quyết định không làm thêm công việc blocking.

## 12. Chọn đúng kiểu cancellation cho từng loại tài nguyên

| Đối tượng | Cách dừng an toàn theo policy | Điều **không được hứa** |
|---|---|---|
| Một `Socket` đã tạo và sở hữu | Đóng socket khi không còn dùng, đặt read timeout, xử lý exceptions | Thread.interrupt luôn lập tức unblock mọi old-style socket read |
| Một `ServerSocket` listener | `close()` làm accept đang block kết thúc theo contract | Chỉ đóng listener sẽ đóng mọi accepted sockets |
| `SocketChannel` / `FileChannel` | TWR, close khi hủy, quản lý `ClosedByInterruptException` | Có thể tiếp tục dùng channel sau khi bị interrupt làm đóng |
| `Selector` | `wakeup()`/`close()`, quản lý keys và trạng thái thread | Interrupt chỉ có một semantics duy nhất giống `await` |
| `InputStream`/`BufferedReader` | TWR và ownership rõ, giới hạn dữ liệu/timeouts | Gọi close luôn giải phóng một external service đúng nghiệp vụ |
| `CompletableFuture` | `cancel`/`orTimeout` theo hợp đồng + cleanup resource riêng | `cancel(true)` của base CF chắc chắn interrupt worker thread |
| `Future` từ `ExecutorService.submit` | `cancel(true)` có thể yêu cầu interrupt nếu task đang chạy, task phải hợp tác | Task đã rollback side effects hoặc đóng mọi socket |
| `ExecutorService` | `shutdown` → `awaitTermination` → `shutdownNow` nếu cần | `shutdownNow` đảm bảo ngừng tức thì |
| `HttpClient.sendAsync` | Dùng future cancellation theo implementation + request timeouts, đọc/đóng streaming body | Server xa chưa nhận request |
| Một borrowed connection từ pool | Trả lại/đánh dấu unusable theo pool contract | Tự `close` bất kỳ lúc nào cũng an toàn cho toàn pool |

**Vấn đề ownership không thể bỏ qua:** Một library method nhận `Socket` đã được caller quản lý không được quyết định `socket.close()` khi gặp lỗi trừ khi API đã quy định **chuyển ownership**. Ngược lại, method trực tiếp tạo socket rồi ném exception trước khi trả socket phải tự đóng nó.

## 13. Lỗi khi đóng và cách báo cáo/ghi log

Để debug production:
- Giữ **lỗi gốc** (ví dụ `IOException: bad frame`).
- Đọc `getSuppressed()` khi TWR có lỗi closing; không chỉ in `e.getMessage()` nếu cần RCA.
- Dùng stacktrace có trace/request ID không nhạy cảm. Không log access token, cookie, private key, raw payload bí mật.
- Phân loại lỗi network/timeout/shutdown expected, tránh alarm giả khi client đóng chủ động.
- Nếu close thất bại nhưng request thành công, quyết định có cần coi kết quả operation là lỗi hay cảnh báo **tùy tính chất tài nguyên** (đặc biệt flush/write durability).
- Đóng `OutputStream` có thể kích hoạt flush/close provider-specific; đừng cho rằng một exception close ở writer là “chỉ phụ, có thể bỏ qua” nếu cần bảo đảm dữ liệu đã được ghi.
- Với TCP, đóng socket không xác nhận peer đã lưu bytes vào database; ứng dụng cần protocol ACK.

### Vì sao không catch Exception rồi return thành công?

Ví dụ anti-pattern:

~~~java
try (Socket socket = connect()) {
    sendRequest(socket);
} catch (Exception ignored) {
    return true; // Sai: che mọi lỗi, kể cả mất kết nối.
}
~~~

Đây là **snippet sai có chủ đích**; `connect/sendRequest` là hàm giả định. Nó làm caller tin rằng request thành công dù TCP hoặc parse đã thất bại. Khi cần fallback, chỉ phục hồi các exception **được định nghĩa** và luôn báo rõ trạng thái/metrics.

### Vì sao không cứ close hai lần cho chắc?

`AutoCloseable.close()` không yêu cầu mọi implementation idempotent. Với `Socket` và nhiều stream JDK, lặp close có thể không gây lỗi, nhưng với resource tự viết, close có thể gây side effects, flush, deregister hoặc ném exception. Ownership rõ + TWR giúp mỗi owner chỉ có **một đường đóng**.

Nếu một buffered wrapper đã sở hữu stream bên dưới, đôi khi chỉ cần TWR cho wrapper là đủ. Nếu cần theo dõi cả socket và wrapper (như demo), hiểu rằng đóng wrapper có thể đóng socket; các loại JDK đó an toàn với cleanup lặp, nhưng đừng áp tổng quát cho custom resource.

## 14. Checklist khi bắt `InterruptedException` trong networking

Hãy tự hỏi theo thứ tự:

1. **Đây có thực sự là `InterruptedException`?** Hay là `SocketTimeoutException`, `InterruptedIOException`, `ClosedByInterruptException` hoặc `IOException` do peer/reset?
2. **Method có thể `throws InterruptedException` không?** Nếu có, thường **không cần catch**; giữ nguyên interrupt semantics cho caller.
3. **Resource ownership thuộc về ai?** Đóng các socket/streams/channels **đang sở hữu** trong TWR/finally; không đóng borrowed resource bừa.
4. **Nếu bắt vì không thể rethrow**, gọi `Thread.currentThread().interrupt()` trước khi return/throw unchecked, không nuốt tín hiệu.
5. **Không tiếp tục retry vòng lặp bình thường** khi shutdown đã được yêu cầu.
6. **Có pending futures/subscriptions không?** Hủy/cleanup theo contract riêng, không mặc định interrupt dọn hết.
7. **Có cần phản hồi/ACK nghiệp vụ không?** Đừng diễn giải interrupt/cancel như giao dịch server chưa thực thi.
8. **Có deadline và giới hạn I/O không?** Cấu hình socket read/connect timeout, total operation budget và graceful-stop deadline.
9. **Có logging an toàn không?** Giữ primary + suppressed/causes nhưng redaction bí mật.
10. **Đã test đường lỗi chưa?** Test partial acquire, throw trong body, throw trong close, interrupt đang await, close channel từ thread khác và resource count sau lỗi.

**Một công thức thực tế:**

~~~text
ACQUIRE resources with clearly defined ownership
          │
          ▼
WORK within try-with-resources
          │
   success / error / interrupt
          │
          ▼
CLOSE all acquired resources in reverse order
          │
          ▼
PROPAGATE primary exception and preserve suppressed errors
          │
          ▼
If catching InterruptedException without rethrow:
    RESTORE Thread.currentThread().interrupt()
          │
          ▼
RETURN/STOP; avoid launching new work after shutdown request
~~~

Đây là logic điều phối, không phải yêu cầu bắt mọi loại `IOException` rồi đặt interrupt flag.

## 15. Những bẫy gây rò tài nguyên và mất ngắt

| Sai lầm | Vì sao sai? | Cách sửa |
|---|---|---|
| Chỉ gọi `close` ở nhánh thành công | Lỗi I/O/parse bỏ qua cleanup | TWR ngay sau acquisition |
| Tạo hai resources bên ngoài `try` rồi cái thứ hai fail | Resource thứ nhất bị rò | Đặt cả hai trong TWR |
| Dùng `finally { resource.close(); }` đơn giản khi body đã lỗi | Close exception có thể che body exception | TWR, kiểm tra suppressed |
| Chỉ xem `getMessage()`, không xem `getSuppressed()` | Bỏ qua lỗi cleanup | Giữ primary và suppressed theo RCA |
| `catch (InterruptedException e) {}` | Mất tín hiệu dừng, liveness bug | Rethrow hoặc restore flag + stop |
| `catch (InterruptedException e) { continue; }` | Task lặp vô hạn sau yêu cầu dừng | Dừng/return/propagate |
| `Thread.interrupted()` dùng để logging | Xóa cờ ngắt | `isInterrupted()` |
| Sau `InterruptedException` nghĩ cờ vẫn true | Await/sleep thường clear cờ | Restore khi không rethrow |
| Gọi `Thread.currentThread().interrupt()` khi gặp mọi `IOException` | Timeout/reset không phải interrupt | Phân loại exception theo API |
| Cho rằng `SocketTimeoutException` chắc là thread interrupt | Nó là một timeout I/O | Xử lý timeout/retry theo policy |
| Nghĩ mọi blocking `Socket.read/accept` bị interrupt như `await` | Tùy API, JDK version và implementation | Dùng timeout/close/channels |
| Nghĩ `ClosedByInterruptException` không đóng channel | Channel có thể đã bị đóng | Tạo lại channel nếu tiếp tục |
| Sau `ClosedByInterruptException` gọi `Thread.interrupted()` để xóa cờ | Có thể mất yêu cầu dừng | Giữ cờ và propagate theo policy |
| Nghĩ `CompletableFuture.cancel(true)` luôn interrupt worker | Base CF không kiểm soát worker | Cancellation + cleanup riêng |
| Nghĩ `shutdownNow` bắt buộc mọi task dừng | Chỉ best effort | Task hợp tác, deadline/metrics |
| Đóng `ServerSocket` rồi tưởng accepted sockets cũng đóng | Listener và connections riêng | Theo dõi/đóng từng accepted socket |
| Gửi lại request sau timeout mà không idempotency | Có thể duplicate server effect | ACK/idempotency/status lookup |
| Tắt mọi worker pool vì một client gửi frame sai | Sai phạm vi lỗi | Per-connection cleanup |
| Reuse socket đã đóng | Closed resource không được mở lại | Tạo kết nối mới khi cần |
| Mất ownership giữa callback/future | Không ai chịu trách nhiệm cleanup | Xác định owner trước transfer |
| Ghi log token/raw payload bí mật lúc lỗi | Tạo rò rỉ mới trong RCA | Log trace ID + redact |
| Bỏ qua lỗi `OutputStream.close()` trong durability-critical flow | Dữ liệu có thể chưa flush/commit | Theo dõi kết quả close/flush và contract |
| Cho rằng cleanup = rollback | Server có thể đã nhận request | Protocol ACK và transaction policy |

## 16. Kiểm thử nhánh lỗi một cách quyết định

Đừng chỉ test “happy path” khi kết nối thành công. Một bộ test đáng tin nên có:

1. **Success:** 1–3 resources được tạo; mọi resource được đóng đúng một lần theo ownership.
2. **Body throws:** parser ném IOException; resources vẫn đóng theo thứ tự reverse.
3. **Acquisition failure:** resource A thành công, B ném; A phải đóng.
4. **Close failure:** body ném, close cũng ném; primary giữ nguyên và suppressed ghi được.
5. **Close-only failure:** body thành công, close ném; lỗi close không bị im lặng bỏ qua.
6. **Real TCP invalid payload:** nhận `BAD`, parser lỗi; accepted/socket/listener closed.
7. **Interrupt before await:** cờ được set trước khi vào await; vẫn phát hiện, exception và cleanup.
8. **Interrupt during await:** dùng `CountDownLatch` đồng bộ ready, gửi interrupt rồi xác minh flag restored và resources closed.
9. **Executor graceful success:** tasks hoàn tất, `shutdown` + `awaitTermination` trả true.
10. **Executor timeout:** task có khả năng chờ không giới hạn; `shutdownNow` yêu cầu interrupt, test có outer deadline không treo CI.
11. **Socket read timeout:** peer giữ connection nhưng không gửi dữ liệu; `setSoTimeout` làm read ném timeout và cleanup.
12. **Channel interruption:** NIO channel đang block bị interrupt; xác minh channel closed, interrupted status true và exception hợp đồng.
13. **Asynchronous channel close:** thread khác đóng channel; phân biệt từ việc interrupt worker.
14. **Future cancellation:** quan sát future state khác trạng thái thực của tác vụ/network resource.
15. **Server ACK ambiguity:** server đã commit nhưng client bị timeout; retry chỉ khi policy/idempotency phù hợp.

Với tests đa luồng, ưu tiên `CountDownLatch`, timeout và kiểm tra state thay vì `Thread.sleep` để hy vọng đúng timing. Đừng assert mọi hệ điều hành hoặc implementation sẽ trả **cùng một thông báo lỗi socket** khi có racing shutdown.

## 17. Bài tập thực hành

1. TWR với resources A, B, C sẽ đóng theo thứ tự nào nếu body ném IOException?
2. Nếu tạo A thành công nhưng B ném khi khởi tạo trong resource list, A có được đóng không?
3. Khi body ném và B.close, A.close cùng ném, primary exception là gì? Xem hai lỗi close bằng API nào?
4. Vì sao `try/finally` đơn giản có thể làm mất lỗi chính khi close cũng ném?
5. `Closeable` khác `AutoCloseable` ở chữ ký close như thế nào?
6. `SocketFailureDemo` tạo các loại socket nào? Vì sao khi parser nhận BAD cả ba đều báo closed?
7. Việc `reader.close()` có thể ảnh hưởng đến `accepted Socket` như thế nào?
8. Trong `InterruptCleanupDemo`, tại sao catch thấy flag false rồi lại restore thành true?
9. Nếu một method có `throws InterruptedException`, cách xử lý nào thường đơn giản và bảo toàn tín hiệu nhất?
10. Khi method không thể khai báo checked interrupt exception, nên làm gì trước khi return?
11. `Thread.currentThread().isInterrupted()` và `Thread.interrupted()` khác nhau như thế nào?
12. Có thể viết `catch (InterruptedException e) { continue; }` trong worker loop không? Vì sao?
13. Vì sao không nên đặt interrupt flag thành true cho mọi `SocketTimeoutException`?
14. Nếu một `SocketChannel` bị interrupt khi đang block, điều gì xảy ra với channel và cờ ngắt?
15. `ClosedByInterruptException` và `AsynchronousCloseException` khác nhau ở điều gì?
16. `CompletableFuture.cancel(true)` luôn interrupt worker đang xử lý không?
17. `ExecutorService.shutdownNow()` có cam kết chấm dứt mọi task ngay lập tức không?
18. `awaitTermination` bị interrupt; bạn có nên tiếp tục đợi mà không restore flag không?
19. Nếu listener `ServerSocket` đã đóng, accepted connections có tự đóng theo không?
20. Request POST bị timeout phía client sau khi gửi bytes; có thể kết luận server chưa tạo đơn không?
21. Khi nào một lỗi ở `OutputStream.close()` có thể có ý nghĩa dữ liệu chứ không chỉ cleanup?
22. Một method được đưa socket mượn từ connection pool, có được tự đóng ở catch theo mặc định không?
23. Nếu worker đã restore interrupt flag, rồi lập tức gọi một method block mới, có thể xảy ra điều gì?
24. Tại sao không test interrupt timing bằng nhiều lệnh `Thread.sleep(100)` rồi đoán?
25. Viết skeleton xử lý read request có deadline, TWR và phân loại IOException vs InterruptedException phù hợp.

**Đáp án gợi ý:**
(1) C→B→A; (2) có; (3) lỗi body primary, `getSuppressed()` chứa B/A close; (4) finally exception có thể che lỗi body; (5) `Closeable.close` khai báo IOException còn `AutoCloseable.close` khai báo Exception; (6) listener, sender, accepted; TWR đóng tất cả; (7) close stream có thể đóng socket; (8) `await` xóa cờ trước khi ném `InterruptedException`, catch restore; (9) rethrow; (10) `Thread.currentThread().interrupt()` rồi dừng/throw unchecked; (11) `isInterrupted` không clear, `Thread.interrupted` clear; (12) không, mất tín hiệu dừng; (13) timeout không nhất thiết có interrupt; (14) channel đóng, flag set, `ClosedByInterruptException`; (15) interrupted worker vs close từ thread khác; (16) không với base CF; (17) không, best effort; (18) không, restore khi phải catch; (19) không; (20) không, cần idempotency/status; (21) flush/durability; (22) không nếu không có transfer ownership; (23) có thể lại ném interrupt ngay/không chạy tiếp; (24) timing không quyết định; (25) tạo resource trong TWR, đặt timeout, phân loại lỗi, cleanup và propagate/restore interrupt đúng hợp đồng.

## 18. Tổng kết

- **Mọi resource đã nhận ownership phải có đường đóng** kể cả khi fail giữa chừng; `try-with-resources` là lựa chọn mặc định.
- **TWR đóng ngược thứ tự mở**, xử lý partial initialization và giữ close failures trong `getSuppressed()`, giúp không che lỗi body.
- **InterruptedException là tín hiệu dừng:** nếu có thể hãy truyền tiếp; nếu bắt và không truyền tiếp thì **restore `Thread.currentThread().interrupt()`**, thường sau cleanup, rồi ngừng công việc.
- **Đừng xóa cờ vô ý:** `Thread.interrupted()` clear cờ, `isInterrupted()` không.
- **Mỗi I/O API có semantics riêng:** NIO `ClosedByInterruptException` giữ interrupt flag và đóng channel; old socket, selector, timeout và async futures không thể dùng một giả định chung.
- **Executor shutdown phải có deadline**, cleanup và hợp tác của tasks; `shutdownNow()` chỉ best effort.
- **Cleanup local không thay application ACK/rollback server**, nhất là khi retry sau timeout/cancel.
- **Bốn chương trình Java 17 đã chạy thật**: suppressed exceptions/partial acquire, TCP parser failure, ServerSocket cleanup sau interrupt, và ExecutorService graceful shutdown.

### Tài liệu tham khảo

- [Oracle Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Oracle Java SE 17 — Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html)
- [Oracle Java SE 17 — Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)
- [Java Language Specification 17 — `14.20.3 try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3)
- [Oracle Java SE 17 — Thread.interrupt / isInterrupted / interrupted](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html)
- [Oracle Java SE 17 — InterruptedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InterruptedException.html)
- [Oracle Java SE 17 — InterruptibleChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptibleChannel.html)
- [Oracle Java SE 17 — ClosedByInterruptException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ClosedByInterruptException.html)
- [Oracle Java SE 17 — Socket and ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [Oracle Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Oracle Java SE 17 — CompletableFuture.cancel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
