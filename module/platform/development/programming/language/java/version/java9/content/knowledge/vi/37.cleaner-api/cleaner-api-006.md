# Giới hạn bảo đảm thời điểm chạy và khi JVM kết thúc của Cleaner

**Cleaner** trong package java.lang.ref là cơ chế dọn dẹp dự phòng dựa trên phantom reachability. API này có từ Java 9 và cho phép đăng ký một Runnable để giải phóng tài nguyên khi đối tượng được theo dõi không còn reachable. Tuy nhiên, Cleaner không cung cấp thời hạn chạy cố định và không bảo đảm action hoàn tất khi JVM kết thúc.

Điểm quan trọng là phân biệt hai điều: Cleaner có thể gọi action tối đa một lần, nhưng điều đó không có nghĩa action chắc chắn được gọi đúng một thời điểm hoặc luôn được chạy xong trước khi tiến trình thoát. Với tài nguyên cần giải phóng đúng lúc, ứng dụng phải chủ động đóng tài nguyên bằng close() hoặc try-with-resources; Cleaner chỉ là lớp bảo vệ cuối cùng khi code quên đóng.

## 1. Cleaner hoạt động khi nào?

Cleaner quản lý các đối tượng được đăng ký cùng cleaning action. Bên trong, Cleaner sử dụng PhantomReference và ReferenceQueue để nhận thông báo từ garbage collector khi đối tượng được theo dõi trở thành phantom reachable.

Luồng xử lý khái quát:

1. Ứng dụng tạo một Cleaner.
2. Ứng dụng gọi register(object, action) và nhận về Cleaner.Cleanable.
3. Đối tượng vẫn được sử dụng bình thường khi còn strong reachable.
4. Khi không còn strong, soft hoặc weak reference giữ đối tượng, garbage collector có thể xác định đối tượng đã phantom reachable.
5. Cleaner nhận thông báo qua reference queue và thực thi action trên thread của Cleaner.
6. Sau khi action chạy, Cleanable được xử lý và action không được gọi lần thứ hai.

Cleaner chỉ bắt đầu xử lý tự động sau khi đối tượng đạt phantom reachability. Việc một biến không còn được sử dụng trong mã nguồn chưa đủ để suy ra rằng action sẽ chạy ngay ở dòng kế tiếp. Thời điểm đối tượng trở thành phantom reachable do JVM và garbage collector quyết định.

## 2. Không có bảo đảm về thời điểm chạy

Cleaner không đặt deadline cho cleaning action. Java không quy định action phải chạy trong một số mili giây hoặc giây nhất định sau khi đối tượng không còn được sử dụng.

Thời điểm thực tế phụ thuộc vào nhiều yếu tố:

- Garbage collector chưa chạy hoặc chưa xác định đối tượng đã phantom reachable.
- Đối tượng vẫn còn một strong reference ở nơi khác.
- Một soft hoặc weak reference còn ảnh hưởng đến quá trình reachability.
- Thread của Cleaner chưa xử lý đến reference đang chờ.
- Cleaning action trước đó đang chạy lâu hoặc bị block.
- JVM đang bận với GC, scheduling hoặc các công việc khác.

Vì vậy, không nên dùng Cleaner để thực hiện một thao tác phải hoàn tất trước một deadline. Ví dụ, không nên chờ Cleaner đóng socket trước khi gửi phản hồi cuối cùng cho client, hoặc chờ Cleaner ghi dữ liệu trước khi báo rằng giao dịch đã hoàn tất.

Một cách hiểu đúng là: Cleaner cung cấp cơ hội dọn dẹp khi đối tượng đã phantom reachable, không cung cấp thời điểm dọn dẹp có thể dự đoán.

## 3. At-most-once không đồng nghĩa với guaranteed execution

Javadoc quy định cleaning action được gọi tối đa một lần khi đối tượng trở thành phantom reachable, trừ khi nó đã được gọi tường minh trước đó.

Cần phân biệt hai tính chất:

| Tính chất | Ý nghĩa |
|---|---|
| At-most-once | Một cleaning action không bị gọi lặp nhiều lần bởi cùng Cleanable |
| Guaranteed execution | Action chắc chắn được gọi và hoàn tất trong mọi tình huống |

Cleaner bảo đảm tính chất at-most-once theo hợp đồng API. Nó không bảo đảm guaranteed execution trong mọi tình huống, đặc biệt khi JVM đang kết thúc.

Cleanable.clean() hủy đăng ký và gọi cleaning action. Gọi clean() nhiều lần vẫn chỉ làm action được gọi tối đa một lần. Đây là cách chủ động kích hoạt cleanup khi ứng dụng đóng tài nguyên.

~~~java
Cleaner cleaner = Cleaner.create();

Cleaner.Cleanable cleanable = cleaner.register(
        resourceOwner,
        () -> releaseResource()
);

// Chủ động yêu cầu cleanup
cleanable.clean();

// Gọi lần nữa không làm action chạy lần thứ hai
cleanable.clean();
~~~

Đoạn trên chỉ minh họa API. Trong code thật, action không được capture hoặc giữ reference đến resourceOwner; nếu giữ reference đó, đối tượng sẽ không trở thành phantom reachable để Cleaner tự động xử lý.

## 4. Cleaner thread là daemon thread

Cleaner.create() tạo một thread daemon để xử lý các đối tượng phantom reachable và gọi cleaning action. Nếu dùng Cleaner.create(threadFactory), thread do factory cung cấp cũng được thiết lập thành daemon thread.

Daemon thread không giữ JVM sống chỉ vì thread đó còn hoạt động. Khi các non-daemon thread kết thúc, JVM có thể bắt đầu shutdown sequence dù Cleaner thread vẫn đang chờ hoặc đang thực hiện action.

Điều này giải thích vì sao Cleaner không phải cơ chế bảo đảm giải phóng tài nguyên trước khi ứng dụng thoát:

- Cleaner thread có thể vẫn còn việc khi JVM bắt đầu shutdown.
- JVM không đợi tất cả cleaning action hoàn tất chỉ vì Cleaner thread tồn tại.
- Khi JVM kết thúc, mọi thread bị ngăn thực thi thêm Java code, bao gồm daemon thread.
- Nếu action đang chạy dở, nó có thể không hoàn tất.

Cleaner thread chạy cho đến khi Cleaner itself trở thành phantom reachable và các cleaning action đã đăng ký hoàn tất. Vì vậy, nếu ứng dụng còn cần đăng ký hoặc xử lý cleanup, hãy giữ Cleaner ở một vị trí có vòng đời đủ dài, chẳng hạn một static field dùng chung trong thư viện.

## 5. Điều gì xảy ra khi gọi System.exit()?

System.exit(status) gọi Runtime.exit(status) và bắt đầu shutdown sequence của JVM. Theo Javadoc của Cleaner, hành vi của Cleaner trong thời gian System.exit() là implementation-specific. Không có bảo đảm cleaning action sẽ được gọi hay không.

Điều này có nghĩa:

- Một action đang chờ có thể không được bắt đầu.
- Một action đã bắt đầu có thể không kịp hoàn tất.
- Kết quả có thể khác nhau giữa các JVM hoặc phiên bản triển khai.
- Không được dựa vào Cleaner để flush dữ liệu, commit giao dịch hoặc đóng tài nguyên trước khi System.exit() trả quyền điều khiển cho hệ điều hành.

Shutdown hooks được đăng ký bằng Runtime.addShutdownHook() là một cơ chế khác. Trong shutdown sequence, các hook được khởi chạy theo thứ tự không xác định và chạy đồng thời với các thread còn sống, bao gồm daemon thread. Cleaner không được chuyển thành shutdown hook chỉ vì nó đang có action chờ.

Nếu cần đóng một tập tài nguyên đã biết trước khi ứng dụng thoát, hãy gọi close() trực tiếp trong luồng điều phối shutdown. Có thể dùng shutdown hook như lớp dự phòng cho việc đóng tài nguyên cấp ứng dụng trong quá trình shutdown bình thường, nhưng hook cũng không bảo đảm chạy khi JVM bị dừng cưỡng bức.

## 6. Runtime.halt() và tiến trình bị dừng cưỡng bức

Runtime.getRuntime().halt(status) kết thúc JVM ngay lập tức và không khởi chạy shutdown sequence. Nó không chờ shutdown hooks, Cleaner thread hoặc các action đang chạy.

Ngoài ra, JVM có thể bị kết thúc bởi hệ điều hành, ví dụ tín hiệu SIGKILL trên Unix hoặc TerminateProcess trên Windows. Trong trường hợp tiến trình bị abort như vậy, không có bảo đảm shutdown hook được chạy.

Có thể phân biệt các tình huống:

| Tình huống | Shutdown hook | Cleaner action |
|---|---|---|
| Các non-daemon thread kết thúc bình thường | JVM bắt đầu shutdown sequence | Không có bảo đảm action hoàn tất trước khi JVM dừng |
| Gọi System.exit() | Các hook được khởi chạy theo thứ tự không xác định | Hành vi implementation-specific, không có bảo đảm action được gọi |
| Gọi Runtime.halt() | Không khởi chạy shutdown sequence | Không được chờ action chạy |
| Hệ điều hành buộc tiến trình dừng hoặc JVM abort | Không có bảo đảm hook chạy | Không có bảo đảm cleanup action chạy hoặc hoàn tất |

Không thể biến Cleaner thành cơ chế lưu dữ liệu cuối cùng hoặc bảo đảm đóng tài nguyên trong mọi kiểu kết thúc tiến trình.

## 7. System.gc() và Thread.sleep() không tạo ra bảo đảm

System.gc() chỉ gợi ý JVM dành nỗ lực cho garbage collection. Javadoc mô tả đây là một yêu cầu best-effort, không phải lệnh buộc garbage collector phải chạy ngay hoặc buộc một đối tượng cụ thể trở thành phantom reachable.

Vì vậy, mẫu code sau không phải cách kiểm tra hợp lệ cho thời điểm Cleaner chạy:

~~~java
resource = null;
System.gc();
Thread.sleep(1000);
System.out.println("resource must be cleaned");
~~~

Đoạn code này có thể chạy mà action chưa được gọi. Thời gian sleep không tạo ra quan hệ bảo đảm với garbage collector hoặc Cleaner thread.

Không nên viết unit test yêu cầu Cleaner phải chạy sau một khoảng sleep cố định. Hãy kiểm tra phần cleanup tường minh qua Cleanable.clean() hoặc close(), còn automatic cleanup nên được xem là fallback có thời điểm không xác định.

## 8. Cleaning action không được giữ reference đến đối tượng cần dọn

Đây là điều kiện thiết yếu để automatic cleanup có thể xảy ra.

Action không được tham chiếu trực tiếp hoặc gián tiếp đến đối tượng đã đăng ký. Nếu action giữ reference đến owner, owner vẫn reachable và Cleaner không thể tự động kích hoạt action.

Một inner class hoặc anonymous class không static có thể giữ reference ngầm đến đối tượng bên ngoài. Lambda cũng có thể capture this nếu code truy cập field hoặc method của owner.

Không nên viết:

~~~java
class ResourceOwner {
    private final Cleaner.Cleanable cleanable;

    ResourceOwner() {
        cleanable = CLEANER.register(this, () -> closeInternal());
    }

    private void closeInternal() {
        // Release resource
    }
}
~~~

Lambda gọi closeInternal() của instance nên có thể capture ResourceOwner. Reference được giữ bởi cleaning action sẽ ngăn owner trở thành phantom reachable.

Hãy tách trạng thái tài nguyên ra một static nested class chỉ chứa dữ liệu cần để giải phóng tài nguyên:

~~~java
static final class State implements Runnable {
    private final FileChannel channel;

    State(FileChannel channel) {
        this.channel = channel;
    }

    @Override
    public void run() {
        try {
            channel.close();
        } catch (IOException ignored) {
            // Best-effort fallback cleanup
        }
    }
}
~~~

Sau đó đăng ký State làm action:

~~~java
private static final Cleaner CLEANER = Cleaner.create();

private final State state;
private final Cleaner.Cleanable cleanable;

ResourceOwner(FileChannel channel) {
    state = new State(channel);
    cleanable = CLEANER.register(this, state);
}
~~~

State là static nested class và không chứa reference đến ResourceOwner. Đây là cấu trúc thường dùng để tránh giữ owner sống ngoài ý muốn.

## 9. Action cần ngắn, không block và chịu được cạnh tranh

Cleaning action được chạy trên thread của Cleaner. Các action có thể được thực thi đồng thời với những action khác của cùng Cleaner hoặc với hoạt động ứng dụng.

Nếu một action block lâu, nó có thể làm chậm việc xử lý các action khác được đăng ký với cùng Cleaner. Javadoc khuyến nghị action thường nên thực hiện rất nhanh và không block.

Nên thiết kế action theo các nguyên tắc:

- Có thể được gọi tối đa một lần và vẫn an toàn nếu close() đã chạy trước đó.
- Dùng trạng thái atomic hoặc đồng bộ phù hợp để tránh giải phóng cùng tài nguyên hai lần.
- Không chờ vô hạn trên thread, lock hoặc network operation.
- Không thực hiện công việc kéo dài như retry network, upload file lớn hoặc chờ phản hồi bên ngoài.
- Xử lý lỗi bên trong action vì exception do action ném ra sẽ bị Cleaner bỏ qua.
- Không phụ thuộc vào UI thread, executor hoặc service khác có thể đã ngừng hoạt động.

Cleaner không truyền exception từ action trở lại nơi đã tạo đối tượng. Nếu cần báo lỗi cho caller khi close thất bại, hãy thực hiện thao tác close tường minh trong close() và để phương thức đó trả hoặc ném lỗi phù hợp.

## 10. Dùng AutoCloseable làm đường chính, Cleaner làm fallback

Mẫu thiết kế phù hợp là một lớp vừa triển khai AutoCloseable vừa đăng ký Cleaner:

1. Lớp sở hữu trạng thái tài nguyên.
2. Static nested State chứa dữ liệu đủ để giải phóng tài nguyên, không giữ owner.
3. Cleaner đăng ký owner cùng State.
4. close() giải phóng tài nguyên một cách tường minh.
5. close() gọi Cleanable.clean() để hủy đăng ký và bảo đảm action không bị gọi lặp.
6. Nếu người dùng quên close(), Cleaner có thể gọi State.run() sau khi owner phantom reachable.

Ví dụ dưới đây quản lý một FileChannel. AtomicBoolean bảo đảm đường đóng tường minh và đường Cleaner không đóng channel hai lần. Reference.reachabilityFence(this) giữ wrapper reachable đến khi thao tác ghi hoàn tất, tránh việc Cleaner đóng tài nguyên trong lúc method vẫn đang sử dụng nó.

~~~java
import java.io.IOException;
import java.lang.ref.Cleaner;
import java.lang.ref.Reference;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.atomic.AtomicBoolean;

public class CleanerLifetimeDemo {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private final FileChannel channel;
        private final AtomicBoolean closed = new AtomicBoolean();

        State(FileChannel channel) {
            this.channel = channel;
        }

        void closeExplicitly() throws IOException {
            if (!closed.compareAndSet(false, true)) {
                return;
            }
            try {
                channel.close();
            } catch (IOException exception) {
                closed.set(false);
                throw exception;
            }
        }

        boolean isClosed() {
            return closed.get();
        }

        @Override
        public void run() {
            try {
                closeExplicitly();
            } catch (IOException ignored) {
                // Cleaner actions are best-effort fallback cleanup.
            }
        }
    }

    private static final class ManagedFile implements AutoCloseable {
        private final State state;
        private final Cleaner.Cleanable cleanable;

        ManagedFile(Path path) throws IOException {
            FileChannel channel = FileChannel.open(
                    path,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);
            state = new State(channel);
            cleanable = CLEANER.register(this, state);
        }

        void write(String value) throws IOException {
            try {
                ByteBuffer buffer = StandardCharsets.UTF_8.encode(value);
                while (buffer.hasRemaining()) {
                    state.channel.write(buffer);
                }
            } finally {
                Reference.reachabilityFence(this);
            }
        }

        boolean isClosed() {
            return state.isClosed();
        }

        @Override
        public void close() throws IOException {
            try {
                state.closeExplicitly();
            } finally {
                try {
                    cleanable.clean();
                } finally {
                    Reference.reachabilityFence(this);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("cleaner-lifetime-", ".txt");
        try {
            ManagedFile resource = new ManagedFile(path);
            try (resource) {
                resource.write("hello");
                System.out.println("write completed");
            }
            System.out.println("explicit close completed");
            System.out.println("resource closed: " + resource.isClosed());
            System.out.println("file size: " + Files.size(path));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 9 trở lên:

~~~bash
javac --release 9 CleanerLifetimeDemo.java
java CleanerLifetimeDemo
~~~

Kết quả stdout:

~~~text
write completed
explicit close completed
resource closed: true
file size: 5
~~~

Ví dụ sử dụng try-with-resources để kiểm tra đường đóng tường minh. Nó không cố ép garbage collector chạy và không khẳng định automatic Cleaner fallback đã được kích hoạt; kiểm tra fallback theo thời gian cố định sẽ không đáng tin cậy.

## 11. Reference.reachabilityFence() và nguy cơ cleanup quá sớm

Trong một số lớp quản lý native resource, một method có thể lấy State hoặc native handle từ field rồi tiếp tục sử dụng handle. JIT có thể xác định rằng wrapper không còn được sử dụng sau khi field đã được đọc, dù method vẫn đang làm việc với handle đó.

Nếu wrapper trở thành phantom reachable quá sớm, Cleaner có thể chạy action và giải phóng native resource trong khi method chưa hoàn tất.

Reference.reachabilityFence(object) bảo đảm object vẫn strong reachable cho đến sau lời gọi fence. Vì vậy, có thể đặt nó trong finally ở cuối method cần bảo vệ:

~~~java
void performNativeOperation() {
    try {
        // Use native resource stored in this object
    } finally {
        Reference.reachabilityFence(this);
    }
}
~~~

API này có từ Java 9. Nó chỉ kiểm soát reachability của object; nó không khóa tài nguyên, không đồng bộ thread và không thay thế close().

Không cần đặt reachabilityFence() tùy tiện ở mọi method. Chỉ dùng khi tính đúng đắn phụ thuộc vào việc đối tượng không bị Cleaner xử lý trước khi thao tác với tài nguyên hoàn tất.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Mong Cleaner chạy ngay sau khi gán owner = null | GC có thể chưa chạy hoặc chưa phát hiện phantom reachability | Dùng close() nếu cần giải phóng đúng thời điểm |
| Gọi System.gc() rồi chờ một khoảng cố định | System.gc() chỉ là best-effort, sleep không bảo đảm Cleaner đã chạy | Không dùng thời gian chờ để kiểm soát cleanup |
| Dùng Cleaner để đảm bảo cleanup khi System.exit() | Hành vi Cleaner trong System.exit là implementation-specific | Đóng tài nguyên trước khi gọi exit |
| Nghĩ daemon Cleaner thread giữ JVM sống | Daemon thread không ngăn JVM kết thúc khi non-daemon threads đã kết thúc | Chủ động close trước shutdown |
| Dùng Runtime.halt() và mong cleanup chạy | halt() bỏ qua shutdown sequence và dừng thread ngay | Không dựa vào Cleaner hoặc shutdown hook trong trường hợp này |
| Cleaning action capture owner | Owner không trở thành phantom reachable | Dùng static nested State không giữ owner |
| Cleaning action block lâu | Các action khác cùng Cleaner có thể bị trì hoãn | Giữ action ngắn và không block |
| Cleaning action ném exception để báo lỗi | Cleaner bỏ qua exception từ action | Báo lỗi trong action bằng logger phù hợp; close() tường minh phải trả lỗi |
| Không bảo vệ đường close và Cleaner chạy cạnh tranh | Tài nguyên có thể bị đóng hai lần | Dùng trạng thái atomic/idempotent |
| Tạo Cleaner mới cho từng resource | Tạo nhiều daemon thread không cần thiết | Thường dùng một Cleaner dùng chung cho thư viện hoặc nhóm tài nguyên |
| Bỏ qua reachabilityFence khi cần | Cleaner có thể chạy khi method vẫn đang sử dụng native resource | Đặt Reference.reachabilityFence(this) trong finally khi cần |

## 13. Ghi nhớ

- Cleaner có từ Java 9 và dùng phantom reachability để kích hoạt cleaning action.
- Cleaner không bảo đảm thời điểm action chạy; GC và Cleaner thread có thể trì hoãn việc dọn dẹp.
- Action được gọi tối đa một lần, nhưng không có bảo đảm action được gọi hoặc hoàn tất khi JVM kết thúc.
- Cleaner.create() dùng daemon thread nên Cleaner không giữ JVM sống.
- Javadoc quy định hành vi Cleaner trong System.exit() là implementation-specific và không bảo đảm action được gọi.
- Runtime.halt() bỏ qua shutdown sequence; JVM có thể dừng tất cả thread ngay lập tức.
- System.gc() là best-effort, không phải cách buộc Cleaner chạy đúng lúc.
- Cleanable.clean() là cách chủ động yêu cầu action và chỉ gọi action tối đa một lần.
- Action không được giữ reference đến owner; dùng static nested State.
- Action nên ngắn, không block, thread-safe và xử lý lỗi bên trong.
- Dùng AutoCloseable và try-with-resources để giải phóng tài nguyên xác định; Cleaner chỉ là fallback.
- Dùng Reference.reachabilityFence() khi cần giữ wrapper reachable trong lúc method vẫn sử dụng tài nguyên.
- Không dựa vào finalization; finalization đã bị deprecated for removal trong các JDK hiện hành.

## Tài liệu tham khảo

- [Cleaner — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/ref/Cleaner.html)
- [Cleaner.Cleanable — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/ref/Cleaner.Cleanable.html)
- [Reference.reachabilityFence() — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/ref/Reference.html)
- [Runtime — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/Runtime.html)
- [System.gc() and System.exit() — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/System.html)
- [Cleaner — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ref/Cleaner.html)
- [Runtime shutdown and JVM termination — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.html)
