# Ưu tiên đóng tài nguyên tường minh trong luồng xử lý chính

## 1. Cleaner dùng để làm gì?

`Cleaner` được bổ sung trong Java 9, thuộc package `java.lang.ref`. Nó quản lý các đối tượng đã đăng ký cùng những cleaning action tương ứng. Khi đối tượng được đăng ký trở thành *phantom reachable*, Cleaner nhận thông báo qua cơ chế `PhantomReference` và `ReferenceQueue`, sau đó có thể chạy action để giải phóng tài nguyên còn sót lại.

Cleaner hữu ích cho những class quản lý tài nguyên ngoài heap như:

- File descriptor, file channel hoặc handle của hệ điều hành.
- Native memory hoặc tài nguyên được cấp phát qua JNI.
- Handle đến một đối tượng native mà GC Java không tự giải phóng theo vòng đời mong muốn.
- Tài nguyên cần một phương án dự phòng nếu caller quên gọi `close()`.

Cleaner là cơ chế cleanup dự phòng khi object không còn được sử dụng. Nó không thay thế việc đóng tài nguyên tường minh. Nếu ứng dụng biết thời điểm hoàn tất công việc, hãy đóng tài nguyên ngay tại thời điểm đó.

## 2. Luôn ưu tiên AutoCloseable và try-with-resources

Với tài nguyên có vòng đời xác định, class nên triển khai `AutoCloseable` hoặc `Closeable` và cung cấp `close()`:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    // đọc dữ liệu
}
~~~

Khi thoát khỏi khối `try`, Java tự gọi `close()`, kể cả khi thân khối kết thúc do exception. Cách này giải phóng tài nguyên kịp thời và cho phép lỗi đóng tài nguyên được báo về caller theo quy tắc exception của try-with-resources.

Thứ tự ưu tiên trong thiết kế:

1. **Đóng tường minh:** gọi `close()` khi không còn cần tài nguyên.
2. **Try-with-resources:** để ngôn ngữ tự gọi `close()` ở cuối phạm vi sử dụng.
3. **Cleaner:** làm phương án dự phòng nếu object bị bỏ quên và trở nên phantom reachable.

Không chờ GC để giải phóng file, socket, lock hoặc native memory trong luồng xử lý chính. GC không có deadline và không cam kết chạy vào một thời điểm cụ thể.

## 3. Cách Cleaner hoạt động

Tạo một Cleaner:

~~~java
private static final Cleaner CLEANER = Cleaner.create();
~~~

Đăng ký object và cleaning action:

~~~java
Cleaner.Cleanable cleanable = CLEANER.register(object, action);
~~~

Trong đó:

- `object` là referent được theo dõi.
- `action` là một `Runnable` chứa thông tin cần thiết để giải phóng tài nguyên.
- `register` trả về `Cleaner.Cleanable`, đại diện cho đăng ký và action đó.

Cleaner sử dụng phantom reachability. Khi object không còn strongly reachable, Cleaner có thể xử lý đăng ký tương ứng và chạy action. Ứng dụng không thể lấy lại referent từ phantom reference để gọi phương thức trên object đã mất; action phải tự giữ trạng thái/tài nguyên cần cleanup.

Cleaning action được gọi tối đa một lần:

- Khi Cleaner phát hiện object đã phantom reachable.
- Hoặc sớm hơn nếu code gọi `cleanable.clean()` tường minh.

Sau khi `clean()` được gọi, đăng ký được hủy và action được thực thi. Gọi `clean()` nhiều lần không chạy action lặp lại.

## 4. Vì sao cleaning action không được giữ tham chiếu đến object đăng ký?

Đây là điều kiện quan trọng nhất khi dùng Cleaner.

Giả sử object `ManagedResource` đăng ký một action. Nếu action giữ tham chiếu mạnh đến chính `ManagedResource`, đồ thị tham chiếu sẽ tạo thành đường đi:

~~~text
Cleaner
  └── Cleaning action
        └── ManagedResource
~~~

Object vẫn strongly reachable qua action, vì vậy nó không thể trở thành phantom reachable. Cleaner sẽ không bao giờ nhận được tín hiệu để chạy action tự động.

Các lỗi thường gặp:

- Dùng non-static inner class làm `Runnable`; inner class giữ tham chiếu ngầm đến outer instance.
- Dùng anonymous class và truy cập field của object cần cleanup.
- Dùng lambda tham chiếu `this`, gọi instance method hoặc đọc field của object được đăng ký.
- Đưa chính object đăng ký vào một state object mà Cleaner giữ.

Giải pháp là tách trạng thái cleanup ra một static nested class. State chỉ giữ resource handle và dữ liệu cần thiết để giải phóng tài nguyên, tuyệt đối không giữ owner object.

~~~java
private static final class State implements Runnable {
    private final FileChannel channel;

    State(FileChannel channel) {
        this.channel = channel;
    }

    @Override
    public void run() {
        // Chỉ sử dụng channel và state riêng.
        // Không truy cập ManagedResource.this.
    }
}
~~~

Một lambda vẫn có thể dùng nếu chắc chắn không capture owner hoặc biến cục bộ đang giữ owner. Với cleanup code quan trọng, static nested class thường dễ kiểm tra hơn.

## 5. Thiết kế class quản lý tài nguyên đúng cách

Một class quản lý tài nguyên bằng Cleaner thường có ba thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| Static Cleaner dùng chung | Theo dõi các object và điều phối cleanup |
| State implements Runnable | Giữ resource handle, trạng thái đóng và cleanup logic |
| Cleanable của từng object | Hủy đăng ký và chạy action khi close hoặc khi object phantom reachable |

Quy trình khởi tạo:

1. Mở tài nguyên thật, ví dụ `FileChannel`.
2. Tạo state chứa tài nguyên đó.
3. Đăng ký `this` cùng state với Cleaner.
4. Lưu `Cleanable` để có thể chủ động hủy đăng ký khi đóng.

Quy trình đóng tường minh:

1. Đóng resource trong state.
2. Đánh dấu state đã đóng để thao tác cleanup có tính idempotent.
3. Gọi `cleanable.clean()` để hủy đăng ký.
4. Nếu Cleaner gọi action sau đó, action nhìn thấy state đã đóng và không làm gì thêm.

State cần được thiết kế an toàn khi cleanup được gọi từ nhiều đường đi. Dùng `synchronized`, `AtomicBoolean` hoặc cơ chế trạng thái tương đương để bảo đảm tài nguyên chỉ được đóng một lần.

## 6. Xử lý exception trong explicit close và cleaning action

Có khác biệt quan trọng giữa hai đường cleanup:

- **Explicit close:** caller chủ động gọi `close()`; nếu đóng tài nguyên thất bại, nên báo lỗi phù hợp cho caller.
- **Cleaner fallback:** action được chạy bởi cơ chế Cleaner; exception ném ra từ cleaning action bị bỏ qua và không được chuyển về caller ban đầu.

Vì vậy, state có thể cung cấp một phương thức đóng có checked exception. `close()` gọi trực tiếp phương thức đó để giữ khả năng báo lỗi, sau đó gọi `cleanable.clean()` trong `finally` để hủy đăng ký. `Runnable.run()` gọi lại phương thức đóng nhưng bắt và ghi nhận lỗi, không để exception thoát khỏi cleaning action.

Ví dụ:

~~~java
@Override
public void close() throws IOException {
    try {
        state.closeExplicitly();
    } finally {
        cleanable.clean();
        Reference.reachabilityFence(this);
    }
}

@Override
public void run() {
    try {
        closeExplicitly();
    } catch (IOException ex) {
        // Ghi nhận lỗi cleanup dự phòng.
    }
}
~~~

Không dựa vào exception từ Cleaner để báo lỗi cho code đang dùng tài nguyên. Nếu caller cần biết việc đóng có thành công hay không, caller phải gọi `close()` tường minh.

## 7. Cleaner thread và yêu cầu đối với cleaning action

`Cleaner.create()` tạo một Cleaner có daemon thread để xử lý các object phantom reachable và gọi cleaning action. Có thể tạo Cleaner với `ThreadFactory` riêng nếu use case cần kiểm soát việc tạo thread.

Các cleaning action nên tuân thủ:

- **Nhanh:** chỉ giải phóng tài nguyên và cập nhật state cần thiết.
- **Không block lâu:** action chặn có thể làm trì hoãn những action khác dùng cùng Cleaner.
- **Thread-safe:** action có thể chạy đồng thời với các action khác; state của từng resource phải tự bảo vệ.
- **Độc lập:** không gọi ngược vào object đã được đăng ký hoặc dựa vào application context có vòng đời không phù hợp.
- **Không ném exception ra ngoài:** Cleaner bỏ qua exception từ action; hãy xử lý hoặc ghi log trong action.

Nếu một cleanup cần chờ mạng, đợi thread khác hoặc thực hiện công việc nghiệp vụ dài, đừng đưa toàn bộ quy trình đó vào Cleaner action. Hãy thiết kế luồng đóng tường minh để caller kiểm soát và nhận được kết quả.

## 8. Giữ object sống trong khi đang sử dụng tài nguyên

Một tối ưu của JVM có thể khiến object không còn được xem là cần thiết ngay cả khi một instance method vẫn đang chạy. Nếu Cleaner đóng native resource trong lúc method vẫn dùng resource đó, có thể xảy ra race: cleanup đóng resource trước, method tiếp tục truy cập resource đã đóng.

`Reference.reachabilityFence(object)` bảo đảm object vẫn strongly reachable cho đến vị trí fence trong luồng thực thi.

Ví dụ:

~~~java
int read(ByteBuffer target) throws IOException {
    try {
        return state.channel.read(target);
    } finally {
        Reference.reachabilityFence(this);
    }
}
~~~

Fence nên đặt sau thao tác cuối cùng cần resource. Nó không kích hoạt GC, không tự cleanup và cũng không thay thế synchronization. Nó chỉ bảo đảm object không bị coi là unreachable trước vị trí fence.

Khi class dùng Cleaner để quản lý native resource, hãy xem xét reachability fence trong các method sử dụng resource được giữ qua state, đặc biệt khi tối ưu JIT có thể kết thúc lifetime của owner trước khi thao tác native hoàn tất.

## 9. Ví dụ Java chạy được: AutoCloseable kết hợp Cleaner

Ví dụ dưới đây bọc một `FileChannel`. Caller sử dụng `try-with-resources` để đóng tài nguyên đúng thời điểm. Cleaner là phương án dự phòng nếu một instance bị bỏ quên. State là static nested class, không giữ tham chiếu đến `ManagedFile`.

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

public class CleanerResourceDemo {
    private static final class ManagedFile implements AutoCloseable {
        private static final Cleaner CLEANER = Cleaner.create();

        private final State state;
        private final Cleaner.Cleanable cleanable;

        ManagedFile(Path path) throws IOException {
            state = new State(FileChannel.open(path, StandardOpenOption.READ));
            cleanable = CLEANER.register(this, state);
        }

        int read(ByteBuffer target) throws IOException {
            try {
                return state.channel.read(target);
            } finally {
                Reference.reachabilityFence(this);
            }
        }

        @Override
        public void close() throws IOException {
            try {
                state.closeExplicitly();
            } finally {
                cleanable.clean();
                Reference.reachabilityFence(this);
            }
        }

        private static final class State implements Runnable {
            private final FileChannel channel;
            private boolean closed;

            State(FileChannel channel) {
                this.channel = channel;
            }

            synchronized void closeExplicitly() throws IOException {
                if (!closed) {
                    channel.close();
                    closed = true;
                    System.out.println("resource closed");
                }
            }

            @Override
            public void run() {
                try {
                    closeExplicitly();
                } catch (IOException ex) {
                    System.err.println("Cleaner cleanup failed: " + ex);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("cleaner-demo", ".txt");
        try {
            Files.write(path, "hello".getBytes(StandardCharsets.UTF_8));
            try (ManagedFile file = new ManagedFile(path)) {
                ByteBuffer buffer = ByteBuffer.allocate(5);
                file.read(buffer);
                buffer.flip();
                System.out.println("read = "
                        + StandardCharsets.UTF_8.decode(buffer));
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Lưu mã nguồn trong `CleanerResourceDemo.java`, sau đó biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:all CleanerResourceDemo.java
java CleanerResourceDemo
~~~

Kết quả:

~~~text
read = hello
resource closed
~~~

Ví dụ cũng biên dịch và chạy được trên Java 9:

~~~bash
javac --release 9 -Xlint:all CleanerResourceDemo.java
java CleanerResourceDemo
~~~

Trong đường chạy bình thường, `try-with-resources` gọi `close()` trước khi thoát khối. `close()` đóng channel và gọi `cleanable.clean()` để hủy đăng ký. Action được gọi tối đa một lần; khi action chạy, state đã đóng nên không đóng channel lần thứ hai.

Ví dụ kiểm tra đường explicit close. Nó không cố chứng minh Cleaner tự chạy sau GC, vì thời điểm GC và xử lý phantom reference không có bảo đảm xác định. Trong ứng dụng thật, không dùng `System.gc()` để đồng bộ hoặc kiểm thử thời điểm cleanup.

## 10. Chọn dùng Cleaner riêng hay chia sẻ Cleaner?

Một Cleaner có thể quản lý nhiều đăng ký. API không yêu cầu mỗi resource phải tạo một Cleaner riêng.

Thông thường, một thư viện có thể dùng một Cleaner static dùng chung cho các instance cùng loại. Cách này tránh tạo nhiều daemon thread không cần thiết. Chỉ tạo Cleaner riêng khi use case thực sự cần vòng đời hoặc chính sách thread độc lập.

Nếu Cleaner object trở thành phantom reachable, Cleaner có thể kết thúc sau khi các cleaning action đang chờ đã hoàn tất. Vì vậy, Cleaner dùng chung nên được giữ bởi một field static hoặc một owner có vòng đời đủ dài.

Overload `Cleaner.create(ThreadFactory)` cho phép tùy chỉnh cách tạo thread. ThreadFactory phải cung cấp thread mới phù hợp để chạy cleanup. Không dùng overload này chỉ để thay đổi tên thread nếu không có nhu cầu vận hành rõ ràng.

## 11. Cleaner, try-with-resources và finalization

| Cơ chế | Khi nào cleanup | Đặc điểm |
|---|---|---|
| `AutoCloseable.close()` | Khi caller đóng | Tường minh, có thể báo lỗi |
| `try-with-resources` | Khi rời khỏi block | Tự động đóng và xử lý exception |
| `Cleaner` | Khi object phantom reachable hoặc cleanable được gọi | Dự phòng, không xác định thời điểm GC |
| `finalize()` | Cơ chế finalization cũ | Deprecated for removal, không dùng cho thiết kế mới |

`Object.finalize()` đã deprecated for removal từ Java 9. Finalization có vấn đề về hiệu năng, bảo mật, khả năng dự đoán và độ tin cậy. Hãy dùng `AutoCloseable`/try-with-resources cho cleanup tường minh và Cleaner khi cần fallback sau khi object không còn reachable.

Cleaner là API hiện hành, nhưng vai trò của nó vẫn là post-mortem cleanup. Đừng chuyển code từ finalizer sang Cleaner rồi tiếp tục dựa vào GC để đóng tài nguyên trong luồng xử lý chính.

## 12. Những lỗi thường gặp

- **Chỉ dựa vào Cleaner để đóng file hoặc socket:** cleanup có thể bị trì hoãn vô thời hạn khi GC chưa xử lý object.
- **Cleaning action capture owner:** object không thể phantom reachable, action tự động không chạy.
- **Dùng non-static inner class làm State:** inner class giữ tham chiếu ngầm đến outer object.
- **Không gọi cleanable.clean() khi close tường minh:** đăng ký vẫn tồn tại cho đến khi Cleaner xử lý object, dù resource đã được đóng.
- **Không làm cleanup idempotent:** nhiều đường cleanup có thể cạnh tranh; resource có thể bị đóng lặp hoặc state không nhất quán.
- **Để exception thoát khỏi action:** Cleaner bỏ qua exception; caller không nhận được lỗi cleanup.
- **Block trong action:** có thể trì hoãn các action khác trên cùng Cleaner.
- **Tạo Cleaner cho từng object:** tăng số thread và overhead không cần thiết.
- **Quên reachabilityFence:** Cleaner có thể cleanup resource khi method vẫn đang dùng state của object.
- **Dùng System.gc() để đợi cleanup:** không có bảo đảm thời điểm GC hay action hoàn tất.
- **Dùng finalize():** finalization đã deprecated for removal; không đưa vào code mới.
- **Cho rằng cleanup luôn chạy khi JVM thoát:** Cleaner không bảo đảm action hoàn tất trong quá trình `System.exit`.

## 13. Checklist khi review class quản lý tài nguyên

1. Tài nguyên có được đóng tường minh qua `AutoCloseable` hoặc `Closeable` không?
2. Caller có thể sử dụng try-with-resources không?
3. Cleaner chỉ là phương án dự phòng khi object phantom reachable chứ?
4. State có phải static nested class và không giữ referent không?
5. Cleaning action có ngắn, không block và thread-safe không?
6. `close()` có báo lỗi cho caller, còn Cleaner action có tự xử lý exception không?
7. State có bảo đảm idempotence khi explicit close và fallback cleanup không?
8. Các method dùng native resource có cần `Reference.reachabilityFence(this)` không?
9. Cleaner dùng chung có được giữ sống trong suốt vòng đời thư viện không?
10. Có tránh phụ thuộc `System.gc()`, `System.exit` hoặc finalization không?

## 14. Tài liệu tham khảo

- [Cleaner — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/ref/Cleaner.html)
- [Cleaner — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/Cleaner.html)
- [Cleaner.Cleanable — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ref/Cleaner.Cleanable.html)
- [AutoCloseable — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html)
- [Reference.reachabilityFence — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/Reference.html)
- [Object.finalize — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html)