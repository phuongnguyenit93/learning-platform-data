# Kiểm thử đóng chủ động mà không phụ thuộc thời điểm GC

Cleaner được bổ sung trong Java 9 để đăng ký một cleaning action chạy khi object trở nên phantom reachable. Tuy nhiên, thời điểm Garbage Collector phát hiện và xử lý object không được bảo đảm. Vì vậy, bài kiểm thử quản lý tài nguyên không nên chờ GC để chứng minh cleanup đã xảy ra.

Cách kiểm thử ổn định là kích hoạt cleanup bằng đường đóng chủ động: gọi \`AutoCloseable.close()\`, dùng try-with-resources hoặc gọi \`Cleaner.Cleanable.clean()\`. Sau lời gọi đó, kiểm tra trạng thái hoặc số lần giải phóng ngay trong test. Cleaner vẫn có thể làm lớp dự phòng nếu object bị bỏ quên, còn vòng đời tài nguyên thông thường phải được đóng một cách tường minh.

## 1. Phân biệt đóng chủ động và cleanup dự phòng

Có hai đường dẫn để cleaning action được gọi:

| Đường dẫn | Điều kiện | Ai kích hoạt |
|---|---|---|
| Đóng chủ động | Ứng dụng gọi \`close()\` hoặc \`Cleanable.clean()\` | Thread đang thực hiện lời gọi |
| Cleanup dự phòng | Object được đăng ký trở nên phantom reachable | Thread do Cleaner quản lý sau khi GC xử lý reachability |

Đóng chủ động là đường dẫn có thể kiểm thử xác định. Khi \`Cleanable.clean()\` được gọi, nó hủy đăng ký cleanable và gọi cleaning action. Action được gọi tối đa một lần, kể cả khi \`clean()\` được gọi nhiều lần.

Cleanup dự phòng phụ thuộc GC và lịch chạy thread Cleaner. Không có thời hạn cố định để action được gọi sau khi object không còn được sử dụng. Không nên viết unit test đòi hỏi GC phải chạy trong một khoảng thời gian cụ thể.

## 2. Cleaner không thay thế AutoCloseable

Với tài nguyên có vòng đời xác định, hãy ưu tiên:

- \`AutoCloseable\` để biểu diễn tài nguyên có thao tác đóng.
- try-with-resources để tự động gọi \`close()\` khi thoát scope.
- \`Cleaner\` làm lớp dự phòng cho trường hợp caller quên đóng tài nguyên.

Ví dụ:

~~~java
try (TrackedResource resource = new TrackedResource()) {
    resource.use();
}
~~~

Khi block kết thúc bình thường hoặc do exception, Java vẫn gọi \`close()\`. Cơ chế này không cần GC và không phụ thuộc thời điểm object được thu gom.

Nếu một API yêu cầu người dùng gọi \`close()\`, hãy ghi rõ hợp đồng đó. Cleaner không thể bảo đảm giải phóng tài nguyên đúng thời điểm để đáp ứng deadline, khóa file, transaction hoặc giới hạn số lượng handle.

## 3. Vai trò của Cleaner và Cleanable

Đăng ký object cùng cleaning action:

~~~java
Cleaner cleaner = Cleaner.create();
Cleaner.Cleanable cleanable = cleaner.register(
        resource,
        cleaningAction
);
~~~

- \`Cleaner.create()\` tạo Cleaner và thread daemon để xử lý các object đã phantom reachable.
- \`register(obj, action)\` đăng ký object cùng một Runnable.
- \`Cleanable\` đại diện cho đăng ký đó.
- \`Cleanable.clean()\` hủy đăng ký và gọi action.
- Action chỉ được gọi tối đa một lần. Sau khi đã clean chủ động, GC không gọi action lần thứ hai.

Nên dùng một Cleaner dùng chung trong library hoặc class quản lý tài nguyên, thay vì tạo một Cleaner mới cho mỗi resource. Mỗi Cleaner quản lý thread và hàng đợi cleaning action riêng.

## 4. Thiết kế cleaning action không giữ lại object

Quy tắc quan trọng nhất: cleaning action không được giữ tham chiếu trực tiếp hoặc gián tiếp tới object đã đăng ký. Nếu action giữ object, object sẽ không thể trở nên phantom reachable và cleanup dự phòng sẽ không được kích hoạt.

Không nên viết:

~~~java
cleaner.register(this, () -> this.releaseNativeResource());
~~~

Lambda này capture \`this\`. Cleaner giữ action, action giữ object, vì vậy object vẫn reachable.

Hãy đặt trạng thái giải phóng trong một static nested class:

~~~java
private static final class State implements Runnable {
    private final long nativeHandle;

    State(long nativeHandle) {
        this.nativeHandle = nativeHandle;
    }

    @Override
    public void run() {
        releaseNativeHandle(nativeHandle);
    }
}
~~~

Resource giữ State và Cleanable:

~~~java
private static final Cleaner CLEANER = Cleaner.create();

private final State state;
private final Cleaner.Cleanable cleanable;

TrackedResource(long nativeHandle) {
    state = new State(nativeHandle);
    cleanable = CLEANER.register(this, state);
}

@Override
public void close() {
    cleanable.clean();
}
~~~

Trong code thực tế, \`releaseNativeHandle\` là thao tác giải phóng handle hoặc tài nguyên bên ngoài. State không giữ Resource, không giữ callback capture Resource và không giữ một object khác có đường tham chiếu quay lại Resource.

Static nested class tránh tham chiếu ngầm tới instance bao ngoài. Một inner class không static, kể cả anonymous class, thường giữ tham chiếu tới outer instance và có thể ngăn cleanup dự phòng.

## 5. Làm cleaning action idempotent

Cleanup có thể được yêu cầu từ nhiều đường: caller gọi close, một thread khác gọi close, hoặc Cleaner xử lý object đã phantom reachable. Hãy bảo đảm tài nguyên chỉ được giải phóng một lần.

Dùng AtomicBoolean để bảo vệ trạng thái:

~~~java
private static final class State implements Runnable {
    private final AtomicBoolean closed = new AtomicBoolean();

    @Override
    public void run() {
        if (closed.compareAndSet(false, true)) {
            releaseNativeResource();
        }
    }
}
~~~

\`compareAndSet(false, true)\` chỉ cho một lần gọi chuyển trạng thái từ mở sang đóng. Những lần gọi sau không thực hiện release lần nữa.

Cleanable vốn đã bảo đảm cleaning action được gọi tối đa một lần khi \`clean()\` lặp lại. Trạng thái idempotent vẫn hữu ích để bảo vệ logic giải phóng, nhất là khi code có nhiều đường đóng hoặc trạng thái được chia sẻ.

Nếu thao tác release có thể thất bại, cần quyết định rõ chính sách lỗi. Exception ném ra từ cleaning action của Cleaner bị bỏ qua theo hợp đồng API. Vì vậy không dựa vào exception trong Runnable để báo lỗi đóng cho caller. Nếu \`close()\` phải trả lỗi cho người gọi, hãy thiết kế đường đóng chủ động có cơ chế báo lỗi tường minh và đường Cleaner dự phòng best-effort dùng chung trạng thái an toàn.

## 6. Test bằng hành động đóng tường minh

Một unit test có thể dùng bộ đếm thay cho native handle thật:

1. Tạo resource và đăng ký State.
2. Gọi \`close()\` hoặc thoát try-with-resources.
3. Kiểm tra bộ đếm giải phóng tăng đúng một.
4. Gọi close lần nữa.
5. Xác nhận bộ đếm không tăng thêm.

Test không cần gọi \`System.gc()\`, không chờ bằng \`Thread.sleep()\`, không polling WeakReference và không dựa vào lịch chạy Cleaner thread.

Với test try-with-resources, hãy kiểm tra cả đường thoát bình thường và đường thoát do exception. Cả hai đều phải gọi close. Nếu cần kiểm tra tính an toàn khi nhiều thread gọi close, có thể cho các thread gọi đồng thời và xác nhận action chỉ chạy một lần.

## 7. Ví dụ chạy được với Java 9+

Tạo file **CleanerExplicitCloseDemo.java**:

~~~java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class CleanerExplicitCloseDemo {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private final AtomicInteger releasedCount;
        private final AtomicBoolean closed = new AtomicBoolean();

        State(AtomicInteger releasedCount) {
            this.releasedCount = releasedCount;
        }

        @Override
        public void run() {
            if (closed.compareAndSet(false, true)) {
                releasedCount.incrementAndGet();
            }
        }

        boolean isClosed() {
            return closed.get();
        }
    }

    static final class TrackedResource implements AutoCloseable {
        private final State state;
        private final Cleaner.Cleanable cleanable;

        TrackedResource(AtomicInteger releasedCount) {
            state = new State(releasedCount);
            cleanable = CLEANER.register(this, state);
        }

        void use() {
            if (state.isClosed()) {
                throw new IllegalStateException("resource is closed");
            }
        }

        @Override
        public void close() {
            cleanable.clean();
        }
    }

    public static void main(String[] args) {
        AtomicInteger released = new AtomicInteger();

        try (TrackedResource resource = new TrackedResource(released)) {
            resource.use();
        }
        System.out.println("after try-with-resources: " + released.get());

        TrackedResource repeated = new TrackedResource(released);
        repeated.close();
        repeated.close();
        System.out.println("after repeated close: " + released.get());

        try {
            try (TrackedResource resource = new TrackedResource(released)) {
                resource.use();
                throw new IllegalStateException("simulated work failure");
            }
        } catch (IllegalStateException expected) {
            System.out.println("after exceptional exit: " + released.get());
        }

        if (released.get() != 3) {
            throw new AssertionError(
                    "Each resource must be released exactly once"
            );
        }
        System.out.println("explicit cleanup passed without GC");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CleanerExplicitCloseDemo.java
java CleanerExplicitCloseDemo
~~~

Kết quả stdout chính xác:

~~~text
after try-with-resources: 1
after repeated close: 2
after exceptional exit: 3
explicit cleanup passed without GC
~~~

Giải thích:

- Resource đầu tiên được đóng khi try-with-resources kết thúc bình thường.
- Resource thứ hai được đóng hai lần, nhưng action chỉ tăng bộ đếm một lần.
- Resource thứ ba được đóng khi block kết thúc do exception.
- Assertion xác nhận ba resource đều được giải phóng đúng một lần.
- Chương trình không gọi System.gc, không sleep và không chờ Cleaner thread.

Ví dụ dùng AtomicInteger để quan sát số lần cleanup. Trong ứng dụng thực tế, State có thể giữ native handle hoặc thông tin cần thiết để giải phóng tài nguyên, nhưng không được giữ Resource đã đăng ký.

## 8. Kiểm thử nhiều trường hợp đóng

Một bộ test thực tế nên bao gồm:

| Trường hợp | Hành động | Điều cần xác nhận |
|---|---|---|
| Đóng tường minh | Gọi close() | Action chạy đúng một lần |
| try-with-resources bình thường | Thoát block | close() được gọi |
| try-with-resources có exception | Ném exception trong block | close() vẫn được gọi |
| Đóng lặp lại | Gọi close() nhiều lần | Không giải phóng hai lần |
| Đóng đồng thời | Nhiều thread gọi close() | State vẫn idempotent |
| Dùng sau khi đóng | Gọi use() sau close | API từ chối thao tác |
| Cleanup action giữ referent | Kiểm tra thiết kế State | Không có đường tham chiếu ngược về Resource |

Các test trên đều có thể chủ động kích hoạt cleanup. Chúng không cần GC để quyết định thời điểm action chạy.

## 9. Không kiểm thử bằng cách ép GC

Tránh các mẫu test sau:

~~~java
System.gc();
Thread.sleep(1000);
assertTrue(cleanupHappened);
~~~

Lời gọi \`System.gc()\` chỉ là yêu cầu GC xem xét chạy; nó không bảo đảm object được thu gom ngay. Sleep cũng không biến một lịch chạy không xác định thành deadline. Polling WeakReference có thể làm test chậm và vẫn phụ thuộc collector, heap pressure, JIT và lịch thread.

Không nên kiểm tra Cleaner bằng cách đợi một khoảng thời gian tùy ý rồi khẳng định action phải chạy. Điều đó tạo test chập chờn giữa các máy và các lần chạy.

Nếu cần quan sát cleanup dự phòng trong một integration test, hãy xem đó là kiểm thử best-effort riêng và không dùng kết quả thời gian của nó làm điều kiện quyết định cho unit test quản lý tài nguyên. Đường đóng chủ động mới là hợp đồng mà ứng dụng có thể kiểm soát.

## 10. Lưu ý về thread và lỗi trong cleaning action

Cleaner mặc định tạo daemon thread để xử lý các object phantom reachable. Cleaning action chạy trên thread liên kết với Cleaner trong đường cleanup dự phòng; các action có thể chạy cạnh tranh với action khác.

Vì vậy action nên:

- Ngắn và không block.
- An toàn khi chạy đồng thời với các action khác.
- Không chờ thread ứng dụng hoặc giữ lock lâu.
- Không thực hiện I/O không giới hạn thời gian.
- Không ném exception với kỳ vọng exception được truyền về caller.
- Chỉ giữ state tối thiểu cần thiết để giải phóng tài nguyên.

Exception từ cleaning action bị Cleaner bỏ qua; các action khác không bị ảnh hưởng. Nếu cleanup thất bại cần được ghi nhận, action phải tự ghi log hoặc chuyển trạng thái lỗi qua một cơ chế phù hợp. Với close chủ động cần báo lỗi cho caller, cung cấp hợp đồng lỗi tường minh riêng.

Cleaner không bảo đảm cleaning action chạy trước khi JVM kết thúc. Không dùng Cleaner làm cơ chế duy nhất cho dữ liệu cần flush, transaction cần commit/rollback hoặc tài nguyên bắt buộc phải đóng trước một thời điểm xác định.

## 11. Reachability trong method đang sử dụng resource

Khi resource bọc native handle, cần chú ý object có thể trở nên không còn strongly reachable trước khi method dùng native handle kết thúc, nếu runtime xác định không còn cần tham chiếu tới object đó.

Trong code mức thấp, có thể dùng \`Reference.reachabilityFence(this)\` ở cuối thao tác để bảo đảm object còn strongly reachable đến vị trí đó:

~~~java
void useNativeResource() {
    try {
        nativeOperation(state.nativeHandle);
    } finally {
        Reference.reachabilityFence(this);
    }
}
~~~

Đây là kỹ thuật chuyên biệt cho resource có tác động khi bị thu hồi, không phải thứ cần thêm vào mọi method. Nó giúp tránh Cleaner chạy quá sớm trong một số mẫu tương tác với native resource.

## 12. Checklist

- Triển khai AutoCloseable cho resource có thao tác đóng tường minh.
- Dùng try-with-resources ở caller khi vòng đời resource có scope rõ ràng.
- Đăng ký Cleaner như cơ chế dự phòng.
- Gọi Cleanable.clean() trong close().
- Kiểm tra action chỉ chạy một lần sau nhiều lần close().
- Kiểm thử cả normal exit và exceptional exit.
- Dùng static nested State không giữ referent.
- Giữ cleaning action ngắn, thread-safe và không block.
- Không dựa vào exception của Runnable để báo lỗi close.
- Không gọi System.gc(), sleep hoặc polling trong unit test cleanup.
- Không yêu cầu Cleaner chạy trước khi JVM exit.
- Chỉ dùng reachabilityFence khi native-resource lifetime yêu cầu.

Cleaner là cơ chế dự phòng dựa trên phantom reachability, không phải bộ hẹn giờ giải phóng tài nguyên. Để kiểm thử đóng chủ động một cách ổn định, gọi close hoặc Cleanable.clean trực tiếp rồi xác nhận action hoàn tất đúng một lần. Cách này kiểm tra đúng hợp đồng quản lý tài nguyên mà không phụ thuộc thời điểm GC.

## Tài liệu tham khảo

- [Cleaner — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ref/Cleaner.html)
- [Cleaner.Cleanable — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ref/Cleaner.Cleanable.html)
- [AutoCloseable — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/AutoCloseable.html)
- [Reference.reachabilityFence — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object))
