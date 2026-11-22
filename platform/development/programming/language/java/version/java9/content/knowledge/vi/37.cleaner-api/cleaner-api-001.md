# Phân biệt vòng đời đối tượng với vòng đời tài nguyên ngoài heap

Một object Java và tài nguyên mà object đó đại diện có thể có hai vòng đời khác nhau. Object wrapper nằm trên Java heap và được Garbage Collector (GC) quản lý. Tài nguyên ngoài heap như native memory, file descriptor, socket handle hoặc handle do thư viện native cấp phát cần được giải phóng theo hợp đồng riêng. Khi wrapper không còn được tham chiếu, điều đó không có nghĩa tài nguyên bên ngoài đã được giải phóng ngay.

`java.lang.ref.Cleaner` (có từ Java 9) cung cấp một cơ chế dự phòng để chạy cleanup action khi object đã trở nên phantom-reachable. Cleaner giúp giảm hậu quả khi code quên đóng tài nguyên, nhưng không thay thế việc đóng tường minh. Với tài nguyên cần giải phóng đúng thời điểm, hãy thiết kế `AutoCloseable` và dùng `try-with-resources`; Cleaner chỉ là lớp bảo vệ cuối cùng.

## 1. Hai vòng đời khác nhau

| Đối tượng Java | Tài nguyên ngoài heap |
|---|---|
| Được cấp phát trên heap và được GC theo dõi | Có thể nằm trong native memory hoặc do hệ điều hành/thư viện native quản lý |
| Có thể được thu gom khi không còn strong/soft/weak reference phù hợp | Không tự động được giải phóng chỉ vì wrapper Java không còn được dùng |
| Thời điểm GC thu gom không xác định | Cần API release/close tương ứng với tài nguyên |
| GC thu hồi vùng nhớ heap của object | Native allocator hoặc hệ điều hành thu hồi tài nguyên khi có thao tác giải phóng phù hợp |

Ví dụ, một class Java có thể chứa `long nativeHandle` trỏ đến vùng nhớ do thư viện C cấp phát. GC hiểu object Java và field nativeHandle là dữ liệu trên heap; GC không hiểu vùng nhớ mà con số đó đại diện. Nếu wrapper biến mất mà không gọi hàm native giải phóng, vùng nhớ ngoài heap có thể bị rò rỉ dù heap vẫn được thu gom bình thường.

Ngược lại, một object Java có thể vẫn còn sống trong heap sau khi tài nguyên nó đại diện đã được đóng. Vì vậy API cần xác định trạng thái đóng và từ chối các thao tác tiếp theo.

## 2. Cleaner hoạt động như thế nào?

Cleaner theo dõi một referent bằng cơ chế dựa trên phantom reference. Khi object đăng ký trở nên phantom-reachable, Cleaner lên lịch chạy action đã đăng ký trên thread nền của Cleaner.

Các thành phần chính:

- `Cleaner.create()` tạo một Cleaner dùng chung cho một nhóm resource.
- `cleaner.register(referent, action)` đăng ký object cần theo dõi và trả về một `Cleaner.Cleanable`.
- `Cleanable.clean()` kích hoạt action tường minh. Action được thực hiện tối đa một lần; gọi lại `clean()` không giải phóng tài nguyên lần thứ hai.
- Nếu chương trình không gọi `clean()`, Cleaner có thể chạy action sau khi referent trở nên phantom-reachable.

GC không bảo đảm thời điểm object trở nên phantom-reachable hoặc Cleaner chạy action. Action có thể được chạy muộn; tiến trình cũng có thể kết thúc trước khi action được thực hiện. Không dùng Cleaner làm cơ chế bảo đảm đóng file, trả connection pool, nhả lock hoặc hoàn tất transaction đúng hạn.

Khi gọi `Cleanable.clean()` tường minh, action được thực hiện ngay trong luồng gọi. Khi Cleaner phát hiện referent phantom-reachable, action được thực hiện ở thread nền. Hãy viết action ngắn, an toàn khi chạy đồng thời và không phụ thuộc thread cụ thể.

## 3. Đóng tường minh vẫn là đường chính

Thiết kế resource wrapper theo `AutoCloseable` để người gọi có thể dùng `try-with-resources`:

```java
try (NativeResource resource = new NativeResource(handle)) {
    resource.use();
}
// close() đã chạy trước khi thoát khỏi block.
```

Trong `close()`, có thể gọi `cleanable.clean()` để kích hoạt cùng action và gỡ đăng ký Cleaner. Việc này cho phép cả hai đường đều dùng chung một logic giải phóng:

1. Ứng dụng gọi `close()` → action chạy ngay → handle được giải phóng.
2. Ứng dụng quên gọi `close()` → wrapper trở nên phantom-reachable → Cleaner chạy action dự phòng.
3. Nếu cả hai đường cùng xảy ra gần nhau, `Cleanable` bảo đảm action chỉ chạy một lần.

Đây là mô hình phòng vệ: `close()` tạo tính xác định; Cleaner giúp hạn chế rò rỉ khi caller không tuân thủ hợp đồng.

## 4. Cleanup action không được giữ lại wrapper

Đây là quy tắc quan trọng nhất khi dùng Cleaner. Action được Cleaner giữ lại cho đến khi referent được thu gom. Nếu action giữ strong reference đến chính referent, referent không thể trở nên phantom-reachable và action sẽ không bao giờ được kích hoạt.

Tránh các cách sau:

```java
class NativeResource {
    private final Cleaner.Cleanable cleanable;

    NativeResource() {
        // Sai: lambda tham chiếu this nên giữ lại wrapper.
        cleanable = CLEANER.register(this, () -> release(this));
    }
}
```

Một non-static inner class cũng giữ tham chiếu ngầm đến instance bên ngoài. Lambda gọi field hoặc method của `this` cũng có thể capture wrapper.

Thay vào đó, dùng một state object độc lập, thường là static nested class, chỉ giữ những dữ liệu cần để giải phóng tài nguyên:

- Native handle hoặc địa chỉ cần release.
- Cờ trạng thái hoặc dữ liệu nhỏ cần cho cleanup.
- Không giữ wrapper, không giữ object graph có đường tham chiếu ngược về wrapper.
- Không giữ collection, callback hoặc lambda có thể capture wrapper.

## 5. Làm cleanup idempotent và an toàn khi tranh chấp

Cleanup có thể được gọi từ `close()` hoặc Cleaner thread. Thiết kế action để giải phóng tối đa một lần:

```java
private static final class State implements Runnable {
    private final AtomicLong handle;

    State(long handle) {
        this.handle = new AtomicLong(handle);
    }

    @Override
    public void run() {
        long value = handle.getAndSet(0);
        if (value != 0) {
            NativeApi.release(value);
        }
    }
}
```

`getAndSet(0)` lấy handle cũ và đặt trạng thái về giá trị sentinel trong một thao tác nguyên tử. Chỉ một thread nhận được handle khác 0; các lần gọi sau không release lại. Ví dụ giả định 0 có nghĩa là handle đã đóng. Nếu thư viện native cho phép handle 0 hợp lệ, hãy dùng cờ trạng thái riêng thay vì sentinel này.

Atomic state giúp tránh double-free, nhưng không tự bảo vệ một thao tác native đang chạy đồng thời với `close()`. Nếu `use()` và `close()` có thể chạy từ nhiều thread, wrapper phải điều phối vòng đời bằng lock, trạng thái hoặc cơ chế ownership phù hợp để không giải phóng handle trong khi một thao tác vẫn đang dùng nó.

## 6. Ví dụ hoàn chỉnh với Cleaner và try-with-resources

Ví dụ dưới đây mô phỏng một wrapper sở hữu native handle. `NativeApi` là phần giả lập để chương trình chạy độc lập; trong ứng dụng thật, `release()` sẽ gọi API JNI hoặc thư viện native tương ứng. Ví dụ tập trung vào quyền sở hữu và vòng đời, không giả vờ cấp phát native memory bằng một biến Java.

**Main.java**

```java
import java.lang.ref.Cleaner;
import java.lang.ref.Reference;
import java.util.concurrent.atomic.AtomicLong;

public class Main {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class NativeState implements Runnable {
        private final AtomicLong handle;

        NativeState(long handle) {
            this.handle = new AtomicLong(handle);
        }

        long currentHandle() {
            return handle.get();
        }

        @Override
        public void run() {
            long value = handle.getAndSet(0);
            if (value != 0) {
                NativeApi.release(value);
            }
        }
    }

    private static final class NativeResource implements AutoCloseable {
        private final NativeState state;
        private final Cleaner.Cleanable cleanable;

        NativeResource(long handle) {
            state = new NativeState(handle);
            cleanable = CLEANER.register(this, state);
        }

        void use() {
            synchronized (this) {
                long value = state.currentHandle();
                if (value == 0) {
                    throw new IllegalStateException("Resource is closed");
                }

                try {
                    NativeApi.use(value);
                } finally {
                    Reference.reachabilityFence(this);
                }
            }
        }

        @Override
        public void close() {
            synchronized (this) {
                cleanable.clean();
            }
        }
    }

    private static final class NativeApi {
        static void use(long handle) {
            System.out.println("using native handle: " + handle);
        }

        static void release(long handle) {
            // Stand-in for the native library release function.
            System.out.println("released native handle: " + handle);
        }
    }

    public static void main(String[] args) {
        try (NativeResource resource = new NativeResource(42)) {
            resource.use();
        }
        System.out.println("after try-with-resources");

        NativeResource resource = new NativeResource(99);
        resource.close();
        resource.close();
        System.out.println("close called twice safely");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all Main.java
java Main
```

Kết quả stdout:

```text
using native handle: 42
released native handle: 42
after try-with-resources
released native handle: 99
close called twice safely
```

Diễn giải:

1. `NativeResource` tạo state riêng chứa handle và đăng ký state làm cleanup action. State không tham chiếu ngược về wrapper.
2. `resource.use()` kiểm tra handle còn mở, thực hiện thao tác native giả lập và dùng `Reference.reachabilityFence(this)` để wrapper không bị xem là unreachable trước khi thao tác kết thúc.
3. Khi block `try-with-resources` kết thúc, `close()` gọi `cleanable.clean()` và release handle 42 ngay trong luồng hiện tại.
4. Resource thứ hai được đóng hai lần nhưng handle 99 chỉ được release một lần.
5. Nếu caller quên đóng resource, Cleaner có thể chạy cùng action sau khi wrapper trở nên phantom-reachable. Thời điểm của đường dự phòng này không xác định, nên ví dụ không dùng `System.gc()` để khẳng định stdout của nó.

`Reference.reachabilityFence()` có từ Java 9. Nó bảo đảm referent vẫn strongly reachable đến vị trí fence, hữu ích khi wrapper sở hữu native resource và code native đang dùng handle. Fence không thay thế đồng bộ giữa `use()` và `close()`; ví dụ dùng cùng monitor để hai thao tác tường minh không giải phóng handle giữa lúc đang sử dụng.

## 7. DirectByteBuffer và native memory

`ByteBuffer.allocateDirect(capacity)` tạo direct buffer có nội dung nằm ngoài Java heap. Bản thân đối tượng `ByteBuffer` vẫn là object Java trên heap; phần dữ liệu backing nằm trong native memory.

Điều này tạo ra hai vòng đời:

- GC quản lý wrapper `ByteBuffer`.
- Bộ nhớ native backing cần được thu hồi qua cơ chế quản lý nội bộ của implementation khi buffer không còn được dùng.

API `ByteBuffer` không cung cấp một phương thức `close()` công khai để giải phóng direct memory theo ý muốn. Không dựa vào thời điểm GC để điều tiết mức dùng native memory và không gọi các API nội bộ hoặc reflection để ép giải phóng buffer. Nếu ứng dụng cần kiểm soát vòng đời native memory một cách xác định, hãy chọn API có ownership và scope rõ ràng.

## 8. MemorySegment và Arena trên JDK 22 trở lên

Với ứng dụng mới chạy JDK 22+, Foreign Function & Memory API đã được chuẩn hóa. `Arena` cung cấp lifetime/scope cho native memory; đóng Arena sẽ giải phóng các segment do Arena quản lý và làm các segment đó không còn truy cập được.

Ví dụ:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(1024);
    segment.set(ValueLayout.JAVA_INT, 0, 42);

    int value = segment.get(ValueLayout.JAVA_INT, 0);
    System.out.println(value);
}
// Arena đã đóng; segment không còn được dùng.
```

`Arena.ofConfined()` phù hợp khi một thread sở hữu và sử dụng segment; `Arena.ofShared()` dành cho trường hợp cần truy cập từ nhiều thread theo hợp đồng của API. Cả hai đều có vòng đời tường minh qua `close()`. Đây là lựa chọn phù hợp hơn khi ứng dụng cần quản lý native memory theo scope rõ ràng, thay vì đợi GC và Cleaner quyết định thời điểm thu hồi.

Cleaner vẫn hữu ích cho wrapper native resource tự xây dựng hoặc làm fallback khi caller quên đóng. Nếu dùng FFM Arena, ưu tiên đóng Arena theo scope và không dùng Cleaner để thay thế việc đóng Arena đúng hạn.

## 9. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ wrapper được GC thì native memory được giải phóng ngay | Rò rỉ native memory hoặc file descriptor trong thời gian không xác định | Đóng tường minh; Cleaner chỉ làm fallback |
| Action capture `this` | Cleaner giữ referent sống, action không được chạy | Dùng static state object độc lập |
| Tạo Cleaner cho từng resource | Tạo nhiều thread và overhead không cần thiết | Dùng Cleaner dùng chung cho nhóm resource |
| Cleanup không idempotent | Double-free khi nhiều đường đóng cùng xảy ra | Dùng atomic state hoặc cơ chế one-shot |
| Dùng Cleaner cho transaction hoặc lock | Thời điểm cleanup không xác định, có thể gây lỗi nghiệp vụ | Commit/rollback và unlock tường minh trong `finally` |
| Gọi `System.gc()` để chờ cleanup | GC chỉ là yêu cầu/hint, không bảo đảm action chạy đúng hạn | Kiểm thử cleanup tường minh; kiểm thử GC chỉ mang tính best-effort |
| Cleanup làm I/O hoặc chờ lâu | Có thể làm chậm các cleanup action khác | Giữ action ngắn; chuyển công việc nặng sang cơ chế quản lý riêng |
| Cho phép use và close tranh chấp | Có thể dùng handle sau khi đã release | Điều phối ownership và đồng bộ hai thao tác |
| Dùng direct buffer như resource có `close()` | API không có hợp đồng close công khai | Cân nhắc FFM Arena trên JDK 22+ hoặc wrapper native có `AutoCloseable` |

Không dùng finalization để quản lý tài nguyên. Finalization đã bị deprecated for removal và không cung cấp thời điểm giải phóng xác định. Với code mới, hãy dùng `AutoCloseable`, try-with-resources, Cleaner làm fallback hoặc FFM Arena khi phù hợp.

## 10. Checklist thiết kế resource wrapper

- Wrapper có triển khai `AutoCloseable` và có `close()` tường minh không?
- Caller có thể dùng try-with-resources không?
- Cleaner action có độc lập, không capture `this` và không giữ object graph dẫn về referent không?
- Action có idempotent, thread-safe, ngắn và không block không?
- Native handle có được chuyển sang trạng thái closed trước khi release để tránh double-free không?
- `use()` và `close()` có được điều phối để tránh use-after-free không?
- Có cần `Reference.reachabilityFence(this)` sau đoạn gọi native không?
- Nếu release thất bại, đường close tường minh có cách báo lỗi cho caller không? Cleaner fallback có chính sách ghi nhận lỗi riêng không?
- Có đang dựa vào GC hoặc `System.gc()` để đáp ứng deadline tài nguyên không?
- Nếu dùng native memory mới trên JDK 22+, `Arena` có thể biểu diễn scope phù hợp hơn không?

Vòng đời của object Java và vòng đời của tài nguyên ngoài heap phải được thiết kế riêng. GC chỉ quản lý object trên heap; `Cleaner` có thể chạy action khi wrapper trở nên phantom-reachable nhưng thời điểm không xác định. Hãy đóng tài nguyên tường minh bằng `AutoCloseable` và try-with-resources, giữ cleanup state độc lập với wrapper, bảo vệ thao tác native bằng ownership/synchronization phù hợp, và dùng Arena/MemorySegment trên JDK 22+ khi cần lifetime native memory có scope rõ ràng.
