# Thứ tự đóng callback, đối tượng bản địa, bộ nhớ và thư viện

Khi Java gọi C/C++ qua JNI hoặc Foreign Function & Memory API (FFM), việc `close()` một đối tượng Java không tự bảo đảm rằng phía native đã ngừng sử dụng địa chỉ callback, con trỏ đối tượng hay bộ nhớ. Một callback có thể đang chạy trên luồng khác trong lúc Java bắt đầu dọn dẹp. Giải phóng sai thứ tự có thể dẫn đến *use-after-free*, *double-free*, deadlock hoặc crash toàn bộ JVM.

Mục tiêu của bài này là xác định **ai sở hữu từng tài nguyên, ai còn có thể truy cập nó, điều kiện nào chứng minh tài nguyên đã hết được sử dụng**, rồi thiết kế một giao thức shutdown có thể kiểm chứng. Nguyên tắc xuyên suốt: **ngừng nguồn phát sinh công việc → hủy đăng ký và chờ callback đang chạy kết thúc → giải phóng những đối tượng phụ thuộc → trả bộ nhớ → giải phóng thư viện sau cùng**, có điều chỉnh theo hợp đồng của API native thực tế.

## 1. Phân biệt bốn loại tài nguyên

| Tài nguyên | Ví dụ | Ai thường sở hữu? | Chỉ được giải phóng khi |
| --- | --- | --- | --- |
| Đăng ký callback và con trỏ hàm callback | `register_listener(handle, fn, user_data)`; FFM `Linker.upcallStub(...)`; JNI gọi ngược vào Java | Đăng ký do thư viện native quản lý; stub và tham chiếu Java do cầu nối quản lý | Native không thể bắt đầu callback mới **và** mọi callback đang sử dụng stub/context đã kết thúc |
| Đối tượng bản địa (native object/handle) | `NativeSession*`, `JNI jlong handle`, con trỏ C++ | Thư viện cấp phát hoặc wrapper nhận ownership | Không còn lệnh Java, callback hay luồng native nào truy cập; hàm hủy còn tồn tại |
| Bộ nhớ ngoài heap | `malloc`/`free`, `MemorySegment`, buffer đưa cho thư viện | Có thể do Java arena, thư viện C hoặc đối tượng native quản lý | Tất cả bên giữ con trỏ/slice/view đã ngừng đọc hoặc ghi; giải phóng đúng allocator |
| Thư viện native | `.so`, `.dll`, `.dylib`, địa chỉ hàm trong thư viện | JNI class loader hoặc FFM `SymbolLookup.libraryLookup` gắn với `Arena` | Không còn code, destructor, worker thread, callback hay function pointer cần chạy từ thư viện |

**Ownership không thể đoán từ tên hàm.** `create()` có thể trả handle mà caller phải `destroy()`, hoặc trả handle tham chiếu do library giữ. `get_buffer()` có thể trả borrowed pointer chỉ tồn tại đến lần gọi tiếp theo; `take_buffer()` có thể chuyển ownership. Đọc tài liệu C ABI về “owned/borrowed/transferred”, allocator tương ứng, thread affinity, và việc unregister có chờ callback đang chạy hay không. Một con trỏ có mặt trong Java không đồng nghĩa Java có quyền `free` nó.

Ví dụ phiên làm việc native có quan hệ phụ thuộc:

```text
Native library L (cung cấp register/unregister/destroy/free)
    ├── Native session H
    │     ├── giữ con trỏ tới buffer B (do Java cấp phát)
    │     └── đăng ký callback R
    │             ├── upcall stub S (được cấp bởi callback Arena)
    │             └── user_data/context U (Java/JNI hoặc native)
    └── worker thread T có thể gọi R(S, U) bất đồng bộ
```

Điều kiện hợp lệ phải là `lifetime(B) >= lần dùng B cuối cùng của H/T`, `lifetime(S,U) >= callback cuối cùng`, và `lifetime(L) >= lần gọi cuối tới hàm của L`. Dấu `>=` ở đây biểu diễn thứ tự thời gian, không phải phép toán trên con trỏ. Nếu destructor của `H` còn gọi callback, thì `S/U` phải sống **qua cả thời điểm destructor kết thúc**. Vì vậy không áp đặt một thứ tự đóng cứng nhắc mà chưa biết hợp đồng C API.

## 2. “Không còn đăng ký” khác “không còn callback đang chạy”

Giả sử luồng A thực hiện `unregister_callback(h)`, trong khi luồng B đã lấy địa chỉ callback và sắp gọi `fn(user_data)`. Có ba tình huống API thường gặp:

1. `unregister` chỉ ngăn sự kiện mới nhưng **không chờ** callback đã được lập lịch: phải có thêm `stop + join/drain` hoặc cơ chế đồng bộ của thư viện.
2. `unregister` là hàm *synchronous quiescence*: khi trả về, thư viện cam kết không còn callback đang chạy hay có thể bắt đầu; khi đó có thể đóng stub/context ngay sau đó.
3. `destroy(h)` tự hủy đăng ký và chờ callback: chỉ áp dụng thứ tự do API đó bảo đảm, đồng thời giữ stub, user data và bộ nhớ còn sống cho đến khi `destroy` trả về.

Không thể tự coi `unregister` thuộc trường hợp 2. Biến `AtomicBoolean stopping` phía Java chỉ làm callback Java bỏ qua công việc; nó **không ngăn** thư viện C nhảy vào địa chỉ function pointer đã được giải phóng. Bộ đếm `inFlight` ở Java cũng có một khe hở nếu callback native đã được phát nhưng chưa kịp tăng bộ đếm. Cần một **hàng rào từ phía nguồn phát**: native ngừng tạo callback mới, hủy đăng ký theo đúng API và bảo đảm mọi callback đã phát được hoàn tất hoặc join.

Trạng thái shutdown có thể biểu diễn:

```text
RUNNING ── stop accepting operations ──> QUIESCING
QUIESCING ── unregister + drain/join ──> QUIESCENT
QUIESCENT ── destroy handles + free memory ──> RELEASED
RELEASED ── release/unload library when supported ──> CLOSED
```

Các trạng thái phải được bảo vệ bằng synchronization/atomic thích hợp. Không cho lệnh mới mượn handle sau khi chuyển sang `QUIESCING`; lệnh đã bắt đầu phải kết thúc trước khi `destroy`. Đây là **một hàng rào khác** với hàng rào callback: cần chặn đồng thời cả Java-to-native *downcalls* và native-to-Java *upcalls*.

## 3. Giao thức shutdown đề xuất, từng bước

### Bước 1 — Đóng cổng nhận công việc mới

Đánh dấu phiên là `CLOSING` bằng state machine, lock hoặc CAS; từ chối lệnh Java mới mượn native handle, chặn đăng ký listener mới, hủy timer/producer do Java sở hữu. Dùng primitive bảo đảm *happens-before* (ví dụ khóa, `AtomicReference`) để các luồng quan sát trạng thái nhất quán. Một cờ `volatile` đơn lẻ chưa đủ nếu còn thao tác “kiểm tra rồi mượn handle” cần diễn ra nguyên tử.

Nếu callback tự gọi `close()`, không được để `close()` chờ chính callback đó kết thúc; thực hiện chuyển trạng thái và ủy nhiệm cleanup cho một luồng khác hoặc thiết kế close không đợi ngay bên trong callback.

### Bước 2 — Yêu cầu native ngừng phát callback

Gọi API thích hợp như `stop_events`, `disable_notifications`, `unregister_callback`. Không giữ Java monitor mà callback cần lấy trong lúc gọi API có thể chờ hoặc gọi ngược vào Java; nếu không, close giữ khóa, native đợi callback, callback đợi khóa sẽ deadlock.

Hợp đồng cần trả lời rõ:
- Sau khi unregister trả về có thể còn callback bắt đầu mới không?
- Callback đang chạy có được phép gọi ngược vào `unregister/destroy` không?
- `unregister/destroy` có thể gọi callback cuối cùng một cách đồng bộ không?
- Worker thread nào sẽ được join, và có thể join từ chính thread đó không?
- Context `user_data` được native giữ đến thời điểm nào?

Nếu câu trả lời chưa rõ, **chưa có điều kiện an toàn** để free stub/context. Cần đọc tài liệu API, bổ sung `stopAndDrain` trong lớp C bridge hoặc thay đổi giao thức sở hữu.

### Bước 3 — Chờ mọi công việc còn chạy rời khỏi native

Đợi native thread/queue/worker dừng và các callback đang chạy kết thúc. Đợi cả những Java downcall đã mượn handle. Khi dùng counter/refcount, việc tăng phải nằm trong vùng loại trừ với thao tác stop; không “check state → rời lock → tăng counter” vì close có thể nhìn thấy 0 và giải phóng trước khi counter tăng.

Với timeout, **không** tự giải phóng con trỏ chỉ vì hết thời gian chờ. Nếu thư viện chưa chứng minh quiescence, báo shutdown thất bại, cô lập session và ưu tiên giữ tài nguyên còn sống (có thể rò rỉ có kiểm soát) hơn gây use-after-free. Thiết kế cơ chế hủy cứng chỉ khi nhà cung cấp API bảo đảm an toàn.

### Bước 4 — Hủy native object khi phụ thuộc còn sống

Sau khi không còn truy cập đồng thời, gọi đúng `native_destroy(handle)` hoặc `release_handle` theo ownership. Mọi buffer mà destructor đọc, callback/context mà destructor còn gọi, và chính thư viện chứa destructor phải tiếp tục tồn tại **cho đến khi destroy hoàn thành**.

Nếu đối tượng native tự sở hữu buffer, destructor có thể đã free buffer: **không gọi `free` lần nữa**. Nếu buffer do Java sở hữu và chỉ được object mượn, giữ buffer cho đến sau khi destroy. Nếu object độc lập buffer, hai tài nguyên có thể giải phóng theo thứ tự khác; quyết định dựa trên đồ thị phụ thuộc thực tế.

### Bước 5 — Giải phóng callback stub, context và bộ nhớ ngoài heap

Khi chắc chắn native sẽ không gọi lại:
- FFM: đóng `Arena` sở hữu `upcallStub`, các `MemorySegment` và vùng dữ liệu tương ứng ở đúng thời điểm. `Arena.close()` **không idempotent**; không đóng hai lần hoặc từ sai luồng với arena confined.
- JNI: xóa `NewGlobalRef` bằng `DeleteGlobalRef` **sau** khi callback/native worker dùng xong; không giữ `JNIEnv*` rồi sử dụng trên luồng khác. Giải phóng `malloc` bằng `free` và bộ nhớ C++ bằng cơ chế tương ứng của chủ sở hữu.
- Native handle, pointer, stub và memory view trong Java nên được đánh dấu không còn hợp lệ ngay trong wrapper; đừng cung cấp lại con trỏ đã free cho API khác.

Chú ý: đóng arena khiến truy cập qua `MemorySegment` thuộc scope đó không còn hợp lệ, nhưng **không thể thu hồi** mọi raw pointer C đã sao chép ra ngoài Java. Safety của FFM không thay thế việc đồng bộ với mã native bất đồng bộ.

### Bước 6 — Giải phóng thư viện sau cùng, nếu mô hình nạp cho phép

Một hàm `destroy/free/unregister` vẫn cần mã máy nằm trong thư viện. Unload thư viện trước khi chúng hoàn tất sẽ khiến lời gọi hàm hoặc callback nhảy vào mã đã tháo nạp.

- **FFM từ Java 22:** `SymbolLookup.libraryLookup(path, libraryArena)` gắn lifetime thư viện với arena; hãy giữ `libraryArena` sống lâu hơn mọi arena chứa callback/data và mọi đối tượng/downcall sử dụng các biểu tượng của thư viện. Đóng `libraryArena` cuối cùng. Nếu thư viện đã được nơi khác nạp/giữ, việc thực tế giải phóng module của hệ điều hành còn phụ thuộc reference count và nền tảng.
- **JNI qua `System.loadLibrary` / `System.load`:** không có cặp `System.unloadLibrary` công khai để gọi như close tài nguyên thường lệ. Thư viện gắn với class loader và có thể được unload khi loader không còn được giữ; `JNI_OnUnload` không phải thời điểm shutdown phiên làm việc đáng tin cậy, và không nên thực hiện callback Java tùy ý từ hook này.
- **Process-wide library hoặc static link:** đôi khi không có unload chủ động. Vẫn đóng session, callback, handle và bộ nhớ; ghi rõ thư viện tồn tại đến khi process kết thúc.

## 4. Hai kiểu phụ thuộc làm đảo thứ tự cục bộ

**Trường hợp A — Callback được gắn vào session, destructor cần buffer:**

```text
stop accepting → native.stop → unregister + drain
→ destroy(session) → release callback stub/context
→ free(sessionBuffer) → unload library
```

Nếu `destroy(session)` có thể gọi callback cuối cùng, phải giữ stub/context cho tới sau `destroy`, dù đã ngăn callback bất đồng bộ. Nếu destructor không bao giờ gọi callback và không dùng context nữa, có thể giải phóng stub/context ngay sau unregister + drain. Hai lựa chọn phải dựa trên tài liệu native.

**Trường hợp B — Native object sở hữu buffer, tự unregister trong destructor:**

```text
stop accepting → native.stopAndJoin
→ destroy(session)  [unregister + free buffer theo hợp đồng]
→ release Java GlobalRef/upcall stub
→ unload library
```

Không free riêng buffer đã được destructor sở hữu. Nếu API không cung cấp `stopAndJoin` và `destroy` không bảo đảm chờ callback, phải bổ sung bước đồng bộ trong bridge, không tự suy diễn destructor là hàng rào quiescence.

Một quy tắc hữu ích là **tháo phụ thuộc theo thứ tự ngược chiều tạo lập**, nhưng một đối tượng async chỉ đủ điều kiện tháo khi mọi tác vụ đang sử dụng nó đã kết thúc; thứ tự khởi tạo đơn thuần không chứng minh điều đó.

## 5. Lỗi race và deadlock thường gặp

| Sai lầm | Điều có thể xảy ra | Cách sửa |
| --- | --- | --- |
| Đóng `callbackArena` ngay sau `unregister` bất đồng bộ | Native vẫn gọi địa chỉ stub cũ; crash JVM | Native unregister + drain/join có bảo đảm |
| Free buffer trước `destroy(handle)` | Destructor hoặc worker đọc vùng nhớ đã free | Destroy/stop việc dùng buffer trước, theo ownership |
| `dlclose` trước khi gọi `destroy/free` | Con trỏ hàm trỏ vào thư viện đã unload | Thư viện đóng sau mọi lời gọi native cuối cùng |
| `AtomicBoolean closed` rồi close ngay | Callback đã được phát nhưng chưa vào phần Java tăng counter | Đặt hàng rào quiescence ở nguồn callback và đợi in-flight |
| Giữ `synchronized` lock trong `unregisterAndJoin` | Callback phải lấy cùng lock để hoàn tất: deadlock | Chuyển trạng thái dưới lock, nhả lock trước khi chờ |
| Gọi `close()` từ callback và đợi `inFlight == 0` | Tự chờ chính callback đang chạy | Đẩy cleanup sang thread điều phối, xử lý reentrancy |
| Giữ `JNIEnv*` trong field dùng trên thread khác | JNI interface thread-local không hợp lệ | Lưu `JavaVM*`; attach/detach đúng luồng |
| Xóa `GlobalRef` khi callback còn dùng | Truy cập tham chiếu Java không còn được bảo đảm sống | Xóa sau native drain, dùng lifetime rõ ràng |
| Để exception thoát khỏi FFM upcall target | Có thể làm JVM kết thúc đột ngột | Bắt, log và chuyển thành error code phù hợp ABI |
| Gọi `Arena.close()` hai lần/sai thread | `IllegalStateException` / `WrongThreadException` | Wrapper idempotent, một chủ sở hữu close, đúng arena |

**Đường đi ngược nguy hiểm:** `close` giữ khóa M → gọi `unregister` → native đợi callback → callback gọi Java và đợi M. Không có thời gian chờ nào biến chu trình khóa này thành an toàn. Hãy rời vùng khóa trước khi chờ callback và tránh gọi ngược `close` bên trong callback.

## 6. Mẫu Java 17+ chạy được: mô phỏng shutdown có callback đang hoạt động

Mẫu sau chỉ **mô phỏng** native worker bằng Java thread để kiểm chứng thứ tự. Nó không đăng ký callback JNI/FFM thật; trong ứng dụng, `unregisterAndDrain()` phải được hiện thực bằng hợp đồng API C tương ứng và bảo đảm không còn callback mới. `CountDownLatch` làm cho callback đang chạy chắc chắn hoàn tất trước khi giả lập hủy handle.

Tạo file `ShutdownOrderDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class ShutdownOrderDemo {
    private final CountDownLatch entered = new CountDownLatch(1);
    private final CountDownLatch release = new CountDownLatch(1);
    private volatile boolean accepting = true;
    private Thread callbackThread;

    void startOneCallback() {
        callbackThread = new Thread(() -> {
            if (!accepting) {
                return;
            }
            entered.countDown();
            try {
                release.await(); // mô phỏng callback đang xử lý
                System.out.println("callback: completed");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "native-callback-sim");
        callbackThread.start();
    }

    void awaitCallbackStarted() throws InterruptedException {
        entered.await();
    }

    void stopAccepting() {
        accepting = false;
        System.out.println("1. stop accepting");
    }

    void unregisterAndDrain() throws InterruptedException {
        System.out.println("2. unregister and drain");
        release.countDown();
        callbackThread.join(); // đợi callback thoát hẳn
    }

    void destroyHandle() {
        System.out.println("3. destroy native handle");
    }

    void freeMemory() {
        System.out.println("4. free native memory");
    }

    void unloadLibrary() {
        System.out.println("5. unload library (if supported)");
    }

    public static void main(String[] args) throws InterruptedException {
        ShutdownOrderDemo demo = new ShutdownOrderDemo();
        demo.startOneCallback();
        demo.awaitCallbackStarted();

        demo.stopAccepting();
        demo.unregisterAndDrain();
        demo.destroyHandle();
        demo.freeMemory();
        demo.unloadLibrary();
    }
}
```

Biên dịch và chạy:

```bash
javac ShutdownOrderDemo.java
java ShutdownOrderDemo
```

Stdout (theo thứ tự xác định nhờ `await` và `join`):

```text
1. stop accepting
2. unregister and drain
callback: completed
3. destroy native handle
4. free native memory
5. unload library (if supported)
```

**Điểm cần nhìn:** trước khi in dòng 3, `join` đã trả về, nên luồng callback mô phỏng đã kết thúc. Mẫu không thể hiện native ownership hay khả năng có callback mới sau unregister; đó là những bảo đảm phải lấy từ thư viện native thật. Không sao chép `accepting` + `join` như một thuật toán an toàn tổng quát cho mọi C API.

## 7. FFM Java 22+: lifetime của upcall stub, MemorySegment và thư viện

FFM được hoàn thiện thành API chính thức trong JDK 22 (`java.lang.foreign`). `Linker.upcallStub(target, descriptor, arena)` tạo function pointer có lifetime gắn với `arena`; `MemorySegment` do arena quản lý không thể truy cập hợp lệ sau khi arena đóng. `Arena.ofConfined()` chỉ được truy cập/đóng bởi thread sở hữu; `Arena.ofShared()` cho phép nhiều thread truy cập nhưng **không tự làm cho native callback protocol trở nên thread-safe**. `Arena.global()` không đóng được chủ động. `Arena.ofAuto()` phụ thuộc GC nên không phù hợp với yêu cầu shutdown chính xác.

Ví dụ FFM dưới đây chạy trên **JDK 22+**, tạo upcall stub và buffer nhưng **không đưa con trỏ cho thư viện native**. Nó chỉ minh họa vòng đời arena; nếu đăng ký stub với thư viện thật, phải thực hiện `unregister + drain` trước khi đóng `callbackArena`.

Tạo file `FfmArenaOrderDemo.java`:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class FfmArenaOrderDemo {
    public static void onEvent(int value) {
        try {
            // Thực tế: xử lý sự kiện; tuyệt đối không để lỗi thoát qua ABI.
            if (value < 0) {
                throw new IllegalArgumentException("negative event");
            }
        } catch (Throwable error) {
            System.err.println("callback error: " + error.getMessage());
        }
    }

    public static void main(String[] args) throws Throwable {
        Arena libraryArena = Arena.ofShared();
        Arena dataArena = Arena.ofShared();
        Arena callbackArena = Arena.ofShared();

        try {
            MethodHandle target = MethodHandles.lookup().findStatic(
                FfmArenaOrderDemo.class,
                "onEvent",
                MethodType.methodType(void.class, int.class));

            MemorySegment stub = Linker.nativeLinker().upcallStub(
                target,
                FunctionDescriptor.ofVoid(ValueLayout.JAVA_INT),
                callbackArena);

            MemorySegment data = dataArena.allocate(ValueLayout.JAVA_LONG);
            data.set(ValueLayout.JAVA_LONG, 0, 42L);
            System.out.println("data=" + data.get(ValueLayout.JAVA_LONG, 0));

            // Stub chưa hề được đăng ký: không có callback in-flight.
            // Trong ứng dụng thật: register(stub, data), rồi stop/unregister/drain.
            if (stub.address() == 0) {
                throw new AssertionError("unexpected null stub");
            }
        } finally {
            callbackArena.close();
            System.out.println("callback arena closed");
            dataArena.close();
            System.out.println("data arena closed");
            libraryArena.close();
            System.out.println("library arena closed");
        }
    }
}
```

Lệnh chạy cho code trên (JDK 22+):

```bash
javac FfmArenaOrderDemo.java
java --enable-native-access=ALL-UNNAMED FfmArenaOrderDemo
```

Stdout dự kiến:

```text
data=42
callback arena closed
data arena closed
library arena closed
```

`libraryArena` trong ví dụ là arena trống, **không hề nạp một thư viện**. Khi tích hợp thật, có thể tạo lookup bằng `SymbolLookup.libraryLookup(path, libraryArena)`, lấy downcall handle và giữ thư viện sống cho đến sau các native destructor. Việc đóng arena thư viện phải đứng sau mọi cuộc gọi dùng symbol của thư viện. `System.loadLibrary` thuộc mô hình JNI/class loader riêng; đóng `libraryArena` trống không unload thư viện đã nạp bằng JNI.

Trong FFM, nếu Java gọi downcall đang giữ segment từ shared arena, đóng arena đồng thời có thể ném `IllegalStateException`; đây **không** phải cơ chế dừng callback chạy không được quản lý. Với callback target, không để exception Java vượt qua upcall boundary: API `Linker` quy định exception không được xử lý có thể khiến JVM kết thúc đột ngột. Callback nên bắt lỗi, ghi log/metrics, mã hóa trạng thái lỗi thành giá trị trả về đúng C ABI và giữ công việc ngắn.

## 8. JNI: luồng native, GlobalRef và thời điểm unload

Với JNI, Java wrapper thường giữ một `long nativeHandle`, còn C giữ `jobject` từ `NewGlobalRef` để callback có thể gọi Java. Cần phân biệt:

- `JNIEnv*` chỉ hợp lệ với **luồng hiện tại**. Native worker tạo ngoài JVM cần lấy `JavaVM*`, gọi `AttachCurrentThread` khi cần JNI và `DetachCurrentThread` trước khi luồng kết thúc; không chia sẻ `JNIEnv*` giữa các luồng.
- `jobject` local reference không được lưu để sử dụng ngoài lifetime của lời gọi JNI đã tạo nó. Nếu callback bất đồng bộ cần Java object sống lâu hơn, tạo `NewGlobalRef` và xóa đúng một lần bằng `DeleteGlobalRef` sau khi các callback đã dừng.
- Khi C giữ `JavaVM*`, global ref, worker và class loader, có thể tạo vòng tham chiếu làm thư viện không unload được. Đừng dùng GC hay `finalize` như điểm điều phối shutdown.
- `JNI_OnUnload` gắn với vòng đời nạp thư viện/class loader, được gọi trong ngữ cảnh không định trước; chỉ nên làm cleanup bảo thủ. Đóng session, unregister listener, join native worker và xóa GlobalRef bằng API chủ động trước đó.
- Java 17 có thể dùng JNI; còn cú pháp `Arena`, `Linker`, `MemorySegment` nêu trên cần JDK 22+ và không thể đem nguyên xi biên dịch với Java 17.

Mẫu logic C/JNI **minh họa, không phải chương trình độc lập** (tên hàm `native_*` phụ thuộc thư viện của bạn):

```c
/* Pseudocode cho một session. Không giả định unregister tự drain. */
void close_session(JNIEnv *env, Session *s) {
    native_stop_new_events(s);
    native_unregister_callback(s);
    native_join_callback_workers(s); /* chỉ trả về khi callback in-flight = 0 */
    native_destroy_object(s->handle); /* còn giữ buffer/library hợp lệ */
    if (s->listener_global != NULL) {
        (*env)->DeleteGlobalRef(env, s->listener_global);
        s->listener_global = NULL;
    }
    native_free_owned_buffer(s->buffer); /* chỉ nếu session thật sự sở hữu */
    /* library unload được điều phối sau mọi session và lời gọi native */
}
```

Nếu `native_destroy_object` còn phát callback, phải giữ `listener_global`, callback function pointer và context cho đến sau lời gọi này. Khi C API không tách được stop/unregister/destroy, bridge phải thực thi đúng thứ tự và bảo đảm quiescence theo hợp đồng của nó. Một hàm C tên `native_join_callback_workers` chỉ có nghĩa khi thực sự đợi **mọi** nguồn phát callback liên quan, kể cả callback đã nằm trong queue.

## 9. Thiết kế wrapper có một chủ sở hữu và xử lý lỗi close

Wrapper nên có ownership rõ: một session sở hữu handle và arena tương ứng; những đối tượng chỉ *borrow* handle không được tự đóng nó. Có thể thiết kế `AutoCloseable` và state `OPEN → CLOSING → CLOSED`, để nhiều lần gọi `close()` đồng thời chỉ có một luồng thật sự cleanup. Tuy nhiên trạng thái chỉ là một phần: code phải đợi các downcall đang giữ handle rồi mới destroy, và native phải bảo đảm ngừng callback.

Khi nhiều bước cleanup có thể ném lỗi, không bỏ qua hậu quả của bước trước. Ghi nhận lỗi đầu tiên, tiếp tục những bước độc lập **đã đủ điều kiện an toàn**, gắn lỗi sau bằng suppressed exception; bước phụ thuộc vào shutdown thành công **không được chạy liều**. Ví dụ, nếu `unregisterAndDrain` thất bại mà callback vẫn có thể chạy, không tiếp tục free stub/buffer để “dọn sạch bằng mọi giá”. Báo trạng thái đóng chưa hoàn tất và cách xử lý sự cố.

`try-with-resources` tự đóng theo thứ tự ngược khai báo. Nó hữu ích với tài nguyên đồng bộ và có ownership rõ, nhưng nếu JNI/FFM đã đăng ký callback bất đồng bộ, chỉ nhờ thứ tự `close()` của arena là chưa đủ. Cần một `close` có logic stop/drain trước khi các arena bị đóng. Không dùng `Cleaner`/GC làm cơ chế ngừng native worker; Cleaner chỉ là tuyến thu hồi dự phòng và không bảo đảm thời điểm.

Khi một thư viện dùng chung cho nhiều session, phải đóng **tất cả** session trước khi unload thư viện, thường bằng reference count hoặc owner cấp module/process. Một session đơn lẻ không được unload thư viện đang phục vụ session khác.

## 10. Cách kiểm thử thứ tự giải phóng

1. **Một callback đang chạy:** dùng latch/barrier cho callback tạm dừng, gọi `close` ở thread khác; xác minh `destroy/free/unload` chưa chạy trước khi callback kết thúc.
2. **Đăng ký sát thời điểm close:** cho các thread đồng thời register, call native và close nhiều lần; xác minh không có lệnh nào dùng handle sau destroy và chỉ một lần release.
3. **Callback lồng nhau / reentrant close:** callback gọi API của session hoặc yêu cầu close; xác minh không deadlock, không tự join chính luồng callback.
4. **Unregister thất bại / timeout:** kiểm tra không free tài nguyên còn bị native sử dụng; ghi lỗi rõ và có đường xử lý cô lập hoặc dọn lại khi an toàn.
5. **Destructor phát callback cuối:** xác minh context/stub/GlobalRef còn sống cho đến lúc destructor trả về.
6. **Nhiều session chung thư viện:** đóng từng session theo thứ tự bất kỳ, xác minh thư viện còn nạp khi session cuối sử dụng nó.
7. **Đo native:** build C/C++ có AddressSanitizer khi khả thi, dùng kiểm tra JNI (`-Xcheck:jni` trên JVM hỗ trợ), chạy stress shutdown và ghi nhật ký các mốc `STOP/UNREGISTER/DRAIN/DESTROY/FREE/UNLOAD`; không coi việc chạy thành công một lần là bằng chứng hết race.

Dấu hiệu đáng chú ý là crash ngẫu nhiên trong callback stub, `SIGSEGV/EXCEPTION_ACCESS_VIOLATION` khi stop, lỗi double free, native thread còn sống sau close, `WrongThreadException` với confined arena hoặc `IllegalStateException` khi đóng arena còn bị dùng. Thread dump giúp tìm vòng chờ khóa; native debugger và sanitizer giúp kiểm chứng nguồn sử dụng địa chỉ đã free.

## 11. Checklist trước khi đưa bridge vào production

- Có bảng ownership cho **mỗi** handle, buffer, callback stub, `user_data` và thư viện; biết allocator/hàm free tương ứng.
- Biết chính xác API `unregister` có bảo đảm **quiescence** hay chỉ ngừng đăng ký mới; có phương án drain/join cho trường hợp thứ hai.
- Tất cả Java downcall mới bị chặn; downcall đã bắt đầu đã kết thúc trước khi destroy.
- Callback Java/native không còn chạy, không thể bắt đầu mới; không có callback đợi khóa bị close giữ.
- Native destructor đã hoàn tất trong lúc buffer, callback context và thư viện còn hợp lệ.
- Stub `Arena`, `GlobalRef` và bộ nhớ chỉ được trả bởi owner, đúng một lần; không có borrowed pointer bị free nhầm.
- Thư viện chỉ được unload khi không còn session hoặc hàm cần dùng đến mã của nó; với JNI chấp nhận lifecycle của class loader thay vì mong unload tức thời.
- Lỗi shutdown và timeout không dẫn đến giải phóng thiếu điều kiện; đã có test race, reentrancy và shutdown lặp.

**Kết luận:** an toàn không được quyết định bởi thứ tự gọi tên hàm `close/free/dlclose` đơn thuần. Tài nguyên chỉ được giải phóng sau khi **nguồn tạo công việc đã ngừng**, **mọi người dùng còn hoạt động đã rời đi**, và **những đối tượng phụ thuộc đã được hủy đúng ownership**. Callback và native worker là điểm cần chứng minh quiescence trước tiên; thư viện chứa các hàm cleanup là tài nguyên phải sống lâu nhất.

### Tài liệu tham khảo

- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454).
- [Oracle JDK 22 — Foreign Function and Memory API](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html).
- [JDK 25 — `Linker` (upcall stub và ràng buộc callback)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html).
- [JDK 25 — `Arena` (scope, threading và close)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html).
- [JDK 22 — `SymbolLookup` (lifetime thư viện và lookup)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- [JNI Specification — Invocation API, `AttachCurrentThread` và `JNI_OnUnload`](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/invocation.html).
