# ReferenceQueue và thời điểm thông báo đối tượng đã được xử lý tham chiếu

## 1. ReferenceQueue dùng để quan sát điều gì?

`java.lang.ref.ReferenceQueue<T>` là hàng đợi nhận **đối tượng tham chiếu** (`Reference`), không phải nhận object gốc (*referent*) đã được theo dõi. Khi một `WeakReference`, `SoftReference` hoặc `PhantomReference` được đăng ký với queue và GC nhận biết thay đổi reachability thích hợp, reference có thể được **clear** rồi **enqueue**; code Java dùng `poll()` hoặc `remove()` để **dequeue** đối tượng `Reference` ấy.

Cần phân biệt các sự kiện theo trình tự suy luận:

1. **Registration:** ứng dụng tạo `new WeakReference<>(referent, queue)` hoặc một loại reference thích hợp khác. Registration không đồng nghĩa enqueue.
2. **Reachability thay đổi:** object không còn đường tham chiếu mạnh (*strong reachability*) từ GC roots; tuy nhiên có thể vẫn chịu ảnh hưởng của soft/weak/phantom references.
3. **GC phát hiện:** garbage collector kiểm tra khả năng truy cập vào một thời điểm tùy collector và workload. Gán biến bằng `null` không khiến GC buộc phải chạy ngay.
4. **Clearing:** reference bị xử lý và không còn trả referent qua `get()`, tùy loại reference. Việc clearing và việc enqueue không nhất thiết là cùng một thao tác hoặc cùng một thời điểm.
5. **Enqueue:** reference object được đưa vào queue; một reference chưa đăng ký queue thì không tự xuất hiện tại đây.
6. **Dequeue:** application lấy reference đã được enqueue và đọc metadata của **reference object**, rồi cập nhật cache hoặc cleanup resource tương ứng.

~~~text
Strong references biến mất
           |
           v
GC có thể phát hiện reachability thay đổi
           |
           v
Xử lý/clear các Reference đã đăng ký
           |
           v
Đưa Reference object vào ReferenceQueue
           |
           v
Application poll() / remove()
           |
           v
Dọn cache entry, xử lý metadata, cleanup nếu phù hợp
~~~

**Điều một event KHÔNG chứng minh:** không bảo đảm GC đã trả RAM về OS, không chứng minh byte memory đã được tái sử dụng, không phải thông báo có object gốc còn truy cập được, không bảo đảm native resource đã được đóng, và **không có deadline** từ thời điểm object mất strong references đến lúc ứng dụng nhận event.

Cần nhớ thêm: `Reference.enqueue()` có thể được **chính application gọi thủ công**. Nếu queue có một entry, không thể chỉ nhìn entry đó mà kết luận chắc chắn event đến từ GC.

## 2. Reachability: strong, soft, weak và phantom

Java định nghĩa các mức truy cập object liên quan đến GC, từ mạnh tới yếu:

| Mức / loại | Cách hiểu đúng | Có lấy referent qua `get()`? |
| --- | --- | --- |
| Strong reference | Đường tham chiếu mạnh thông thường từ thread, static field hoặc cấu trúc reachable | Truy cập object trực tiếp |
| `SoftReference<T>` | Không ngăn GC clear khi memory demand/chính sách yêu cầu, có thể phù hợp cho memory-sensitive caches | Có trước khi bị clear |
| `WeakReference<T>` | Không giữ object sống chỉ vì có weak reference; GC xử lý khi referent chỉ còn weakly reachable | Có trước khi bị clear |
| `PhantomReference<T>` | Mức rất yếu dùng để nhận notification/cleanup, không cho chương trình khôi phục referent | **Không**: `get()` luôn `null` |

**Strong references** là điều kiện quan trọng: nếu một static map, thread, cache value hoặc biến local vẫn giữ object qua đường mạnh, object chưa thể được coi là weakly reachable chỉ vì bạn vừa tạo một `WeakReference` tới nó.

**SoftReference** cho GC nhiều lựa chọn hơn: không hứa cứ hết strong references là bị clear tức thì. Đối với production cache cần bounded memory, nên đặt size/TTL/eviction thay vì dựa vào soft reference như cơ chế giới hạn duy nhất.

**WeakReference** thích hợp theo dõi weak keys, canonicalization hoặc các đối tượng mà hệ thống không muốn giữ sống. Nó vẫn cần GC chạy và phát hiện reachability. `weak.get() == null` có thể được quan sát trước khi reference object được queue trả về.

**PhantomReference** thường dùng phối hợp cleanup sau khi GC xác định referent đã đến trạng thái phù hợp. `phantom.get() == null` **ngay từ lúc tạo**, ngay cả nếu referent còn được strong-reference. Vì vậy không sử dụng `get()` để xác định thời điểm phantom notification.

Một loại **reference object** bản thân nó vẫn là Java object; nếu ứng dụng bỏ reference object trước khi GC xử lý thì thông báo có thể bị mất. Hệ quả này cực kỳ quan trọng cho thiết kế.

## 3. Registration là một chiều: queue không giữ danh sách đăng ký

Xem ví dụ:

~~~java
ReferenceQueue<Object> queue = new ReferenceQueue<>();
Object value = new Object();
WeakReference<Object> weak = new WeakReference<>(value, queue);
~~~

- `value` là object gốc (*referent*).
- `weak` là `WeakReference` object; nó nắm liên hệ **yếu** tới `value`.
- `queue` là nơi nhận **weak**, nếu GC hoặc application enqueue weak.
- `queue.poll()` trả một `Reference<? extends Object>` hoặc `null`; không trả `value`.

Đặc tả package `java.lang.ref` nói rõ mối quan hệ của một reference đã đăng ký với queue là **một chiều**: queue không được hiểu như một registry tự giữ mạnh tất cả reference đã đăng ký.

Lối viết sau **không đáng tin** nếu muốn nhận event:

~~~java
new WeakReference<>(value, queue); // không giữ WeakReference object
~~~

Trong code thực, hãy giữ **reference object** ở collection/registry cho tới khi event được xử lý hoặc registration bị hủy. Nhưng **không** giữ referent bằng một strong field khác, nếu mục tiêu là để object đó có thể được GC.

~~~text
Strong registry ──> TrackedWeakReference ──weak──> key object
       |
       └──> metadata (ID, cache key, native handle nếu phù hợp)

Registry được phép giữ reference object.
Registry KHÔNG được vô tình giữ key object qua đường mạnh
nếu muốn key trở nên weakly reachable.
~~~

**Sai lầm:** một subclass `WeakReference<T>` chứa `final T original` sẽ giữ referent sống; constructor dùng `super(original, queue)` không thể vô hiệu hóa strong field ấy.

## 4. API của ReferenceQueue và Reference cần phân biệt

| API | Ý nghĩa | Điều KHÔNG được suy ra |
| --- | --- | --- |
| `queue.poll()` | Thử lấy một reference sẵn có **không chờ** | `null` không chứng minh referent còn sống |
| `queue.remove()` | Chờ và lấy reference khi xuất hiện | Có thể chờ vô hạn nếu không có event |
| `queue.remove(timeoutMillis)` | Chờ tối đa theo timeout; có thể trả `null` | Không buộc GC phải enqueue trong timeout |
| `ref.get()` | Lấy referent nếu API cho phép và chưa bị clear | `null` không chứng minh reference đã enqueue |
| `ref.clear()` | Clear reference do Java code yêu cầu | **Không tự enqueue** |
| `ref.enqueue()` | Thử enqueue bằng Java code và trả boolean | Event có thể **không do GC** tạo |
| `ref.refersTo(object)` | Hỏi reference còn chỉ tới đúng object ấy hay không | Không phải công cụ ép GC |
| `ref.isEnqueued()` | Trạng thái queue ở một thời điểm | **Deprecated Java 16+**, có race, không dùng làm cleanup protocol |
| `Reference.reachabilityFence(x)` | Giữ `x` strongly reachable tới điểm gọi | Không dọn GC, không enqueue |

Với `remove(long timeout)`:

- `timeout > 0`: chờ có giới hạn (milliseconds), trả `null` nếu không nhận được reference trong thời gian chờ.
- `timeout == 0`: **chờ vô hạn**, không phải non-blocking.
- Muốn thử mà không chờ: **`poll()`**.
- Một thread bị interrupt khi đang chờ có thể nhận `InterruptedException`; consumer phải quản lý shutdown đúng cách.

### `clear` khác `enqueue`

~~~text
ref.clear()
   |
   +-- ref.get() có thể thành null
   +-- queue KHÔNG tự có entry chỉ vì clear()

ref.enqueue()
   |
   +-- application yêu cầu thêm reference vào queue
   +-- có thể xảy ra khi object gốc còn strong
   +-- trong Java 17 thao tác này cũng clear reference
~~~

GC có thể clear reference ở một thời điểm rồi enqueue ở thời điểm khác. Không mặc định rằng một `weak.get() == null` phải kèm `queue.poll() != null` **ngay tức khắc**.

## 5. Ví dụ Java 17 chạy được, stdout xác định: manual enqueue

Ví dụ đầu **cố ý không chờ GC** để cô lập ngữ nghĩa API. Tạo file **`ReferenceQueueBasicsDemo.java`**:

~~~java
import java.lang.ref.PhantomReference;
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

public final class ReferenceQueueBasicsDemo {
    public static void main(String[] args) {
        ReferenceQueue<Object> queue = new ReferenceQueue<>();
        Object referent = new Object();

        WeakReference<Object> weak = new WeakReference<>(referent, queue);
        PhantomReference<Object> phantom =
                new PhantomReference<>(referent, queue);

        System.out.println("weakAlive=" + (weak.get() != null));
        System.out.println("phantomGetNull=" + (phantom.get() == null));
        System.out.println("initialQueueEmpty=" + (queue.poll() == null));

        weak.clear();
        System.out.println("weakCleared=" + (weak.get() == null));
        System.out.println("clearDidNotEnqueue=" + (queue.poll() == null));

        boolean manualWeak = weak.enqueue();
        Reference<?> first = queue.poll();
        System.out.println("manualWeakEnqueued=" + manualWeak);
        System.out.println("firstIsWeak=" + (first == weak));

        boolean manualPhantom = phantom.enqueue();
        Reference<?> second = queue.poll();
        System.out.println("manualPhantomEnqueued=" + manualPhantom);
        System.out.println("secondIsPhantom=" + (second == phantom));

        Reference.reachabilityFence(referent);
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 ReferenceQueueBasicsDemo.java
java ReferenceQueueBasicsDemo
~~~

**Stdout chính xác đã kiểm tra bằng JDK 21 với `--release 17`:**

~~~text
weakAlive=true
phantomGetNull=true
initialQueueEmpty=true
weakCleared=true
clearDidNotEnqueue=true
manualWeakEnqueued=true
firstIsWeak=true
manualPhantomEnqueued=true
secondIsPhantom=true
~~~

### Giải thích

1. `weak.get() != null` vì `referent` vẫn được giữ mạnh, đồng thời `reachabilityFence(referent)` đảm bảo không thể xem object là hết dùng trước điểm cuối.
2. Phantom `get()` luôn null; không có bằng chứng object đã bị GC.
3. Chỉ đăng ký reference với queue không enqueue.
4. `weak.clear()` làm weak `get()` thành null nhưng `poll()` vẫn null.
5. `weak.enqueue()` trả true và `poll()` trả đúng `weak` object.
6. `phantom.enqueue()` trả true và `poll()` trả đúng `phantom` object.
7. Hai lần enqueue là hành động **thủ công**, trong khi referent **chưa chết** theo nghĩa GC. Đây là lý do event không được tự động gọi là `OBJECT_COLLECTED`.

Vì ví dụ không phụ thuộc collector, nên stdout **không cần** `System.gc()` và không có vòng đợi bất định.

## 6. Ví dụ quan sát GC: không được hứa stdout cố định

Bài này có code Java 17 hoàn chỉnh, nhưng **chủ ý không viết một kết quả duy nhất**, vì lịch chạy GC thay đổi theo JVM. Tạo **`WeakQueueObservationDemo.java`**:

~~~java
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

public final class WeakQueueObservationDemo {
    private static WeakReference<byte[]> create(
            ReferenceQueue<byte[]> queue) {
        byte[] payload = new byte[1024 * 1024];
        return new WeakReference<>(payload, queue);
    }

    public static void main(String[] args)
            throws InterruptedException {
        ReferenceQueue<byte[]> queue = new ReferenceQueue<>();
        WeakReference<byte[]> ref = create(queue);

        System.gc(); // Yêu cầu, không phải cam kết GC
        Reference<? extends byte[]> event = queue.remove(1000);

        if (event == ref) {
            System.out.println("REFERENCE_ENQUEUED");
        } else {
            System.out.println("NO_EVENT_WITHIN_TIMEOUT");
        }

        System.out.println("cleared=" + (ref.get() == null));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 WeakQueueObservationDemo.java
java WeakQueueObservationDemo
~~~

Tùy GC, có ít nhất hai kết quả phân nhánh hợp lệ:

- **`REFERENCE_ENQUEUED`** nếu GC phát hiện và enqueue reference trong khoảng đợi.
- **`NO_EVENT_WITHIN_TIMEOUT`** nếu queue chưa có reference sau thời gian đã yêu cầu.

Dòng `cleared=` cũng là quan sát tại một thời điểm: có thể đã clear referent dù chưa enqueue; một số collector có thể chưa xử lý ref, cho nên không được khẳng định mọi lần đều `true`.

**`queue.remove(1000)` đặt thời gian chờ của chương trình, không đặt deadline GC.** `System.gc()` cũng không làm đổi điều này; JVM có thể bỏ qua yêu cầu explicit GC do flags hoặc chính sách.

### Tại sao tạo payload trong method riêng?

Sau khi method `create` trả, không còn một biến cục bộ trong `main` nắm trực tiếp `byte[]` payload. Caller chỉ giữ `WeakReference`, dễ quan sát việc GC xử lý. Nhưng chương trình vẫn không có quyền đòi collector chạy ngay, và những tối ưu reachability của runtime phải được hiểu theo semantics GC chứ không theo phạm vi chữ của biến Java.

## 7. Thời điểm chính xác: cleared, enqueued, dequeued và reclaimed

Một thứ tự **tư duy** hữu ích:

~~~text
t0: object và reference được tạo
t1: đường strong reachability cuối cùng có thể mất
t2: GC phát hiện trạng thái truy cập phù hợp
t3: GC clear reference
t4: GC enqueue reference (nếu đã đăng ký queue)
t5: application dequeue và xử lý

Không có SLA milliseconds bắt buộc t1 -> t2 -> t4 -> t5.
Một số sự kiện có thể cùng thời điểm hoặc không xảy ra
trong lifetime quan sát của tiến trình.
~~~

Đặc biệt:

- **`get() == null` không có nghĩa `isEnqueued() == true`**; chưa enqueue, đã dequeue hoặc clear thủ công đều có thể tạo khác biệt.
- **`poll() == null` không chứng minh object còn sống**; nó chỉ nói hiện không lấy được một entry trong queue.
- **`remove(timeout)` trả reference không khẳng định object đã bị deallocate ngay**; việc xử lý reference không là hóa đơn thu hồi byte RAM.
- **SoftReference** có thêm quyền quyết định của GC trước khi clear, theo memory demand.
- **PhantomReference** thông báo điều kiện phantom reachability phù hợp; `get()` luôn null và việc dọn native resource cần do code đúng quyền sở hữu thực hiện.
- **Manual `enqueue()`** phá giả định “event chỉ do GC”; cần tách event source nếu hệ thống cho phép enqueue thủ công.

Không xây nghiệp vụ cần SLA, giao dịch, locking hoặc resource closure bắt buộc đúng hạn dựa duy nhất vào một sự kiện GC/reference queue.

## 8. `poll()` theo đợt hay worker blocking?

### Poll opportunistic

Khi cache được truy cập, có thể dọn các stale references đang đợi:

~~~java
Reference<?> ref;
while ((ref = queue.poll()) != null) {
    // Dùng metadata của ref để xóa entry trong cache.
}
~~~

Đây là **mảnh code minh họa**, biến `queue` cần được định nghĩa theo dữ liệu cache thực. Cách này không tạo thread riêng; phù hợp một số caches với chi phí polling nhỏ. Nhưng nếu ứng dụng không bao giờ gọi cache nữa, việc cleanup dạng opportunistic có thể chưa diễn ra.

### Worker blocking với timeout

~~~java
while (!Thread.currentThread().isInterrupted()) {
    try {
        Reference<?> ref = queue.remove(500);
        if (ref != null) {
            // Xử lý reference đã dequeue; cleanup idempotent.
        }
    } catch (InterruptedException stop) {
        Thread.currentThread().interrupt();
        break;
    }
}
~~~

Đây cũng là **mảnh minh họa**, không phải chương trình độc lập. `remove(500)` giúp worker định kỳ kiểm tra trạng thái dừng. Với `remove()` không timeout, shutdown phải có cơ chế interrupt rõ.

Nguyên tắc:

- Consumer không nên busy-spin `while (queue.poll() == null) {}` liên tục, vì tốn CPU.
- Đừng tạo một worker non-daemon sống vĩnh viễn và ngăn JVM thoát.
- Khi processing exception xảy ra, không để một event làm chết toàn bộ worker; cần ghi log/giữ trạng thái theo chính sách.
- Nếu nhiều consumer cùng đọc queue, chỉ một consumer dequeue một reference, cần cấu trúc registry thread-safe.
- Sau dequeue, ứng dụng thường **xóa registration/reference object khỏi registry** để tránh leak metadata.

## 9. Dùng ID thay vì cố lấy referent đã bị clear

Khi `WeakReference` được GC clear, `weak.get()` thường trả null; bạn không thể trông chờ gọi `referent.close()` trên object đã không lấy được. Muốn biết cache entry nào cần dọn, lưu ID trên **reference object**.

Một phụ trợ minh họa:

~~~java
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

final class TrackedWeakRef<T> extends WeakReference<T> {
    final long id;

    TrackedWeakRef(T value, ReferenceQueue<? super T> queue, long id) {
        super(value, queue);
        this.id = id;
    }
}
~~~

Class này **không có main**; nó chỉ trình bày cách lưu ID độc lập với referent.

Một cache/registry có thể lưu `TrackedWeakRef` mạnh, lưu `id -> value/metadata` riêng, rồi khi dequeue nhận `TrackedWeakRef` đọc `id` để remove entry. Nếu value/metadata vô tình giữ lại key một cách mạnh, key có thể không bao giờ weakly reachable; điều này cần xét cụ thể.

**Chống ví dụ:**

~~~java
final class BadTrackedRef<T> extends WeakReference<T> {
    final T original; // mạnh, khiến referent vẫn reachable!

    BadTrackedRef(T value, ReferenceQueue<? super T> q) {
        super(value, q);
        original = value;
    }
}
~~~

Mặc dù extends `WeakReference`, field `original` làm hỏng mục đích theo dõi đối tượng theo reference yếu nếu instance BadTrackedRef còn được giữ.

Đối với `WeakHashMap`, hãy nhớ key là weak nhưng value có thể giữ lại key qua một đường mạnh khác. Không coi WeakHashMap như cam kết “mọi entry tự biến mất ngay khi bên ngoài ngừng dùng key”.

## 10. Vì sao PhantomReference thường dùng cho cleanup?

`PhantomReference<T>` được thiết kế để thông báo khi referent đã đủ điều kiện phantom reachability; ứng dụng không thể dùng `phantom.get()` lấy lại object gốc.

~~~text
Resource wrapper ───── owns ─────> Native handle H
       |
       +── PhantomReference<Resource>
                  |
                  +── Metadata độc lập: H, ID, cleanup state
                          |
                  GC enqueue ref khi phù hợp
                          |
                  Consumer đọc metadata
                          |
                  Giải phóng H nếu chưa được close
~~~

Muốn thiết kế kiểu này an toàn:

1. Metadata cleanup **không giữ strong reference tới Resource**; nếu giữ thì Resource không đạt điều kiện GC.
2. `H` phải còn hợp lệ tới khi consumer dọn nó.
3. Cleanup phải **idempotent**, kể cả nếu application đã explicit `close()`.
4. Native callbacks/async operations phải kết thúc trước khi free, nếu không use-after-free.
5. Reference object phải được giữ reachable cho tới khi event được nhận hoặc registration kết thúc.
6. Queue event không phải cam kết OS memory đã được hoàn trả trước khi cleanup action chạy.

Trong nhiều tình huống, dùng `java.lang.ref.Cleaner` dễ hơn tự quản PhantomReference+queue; nhưng **không có deadline cleanup tự động**.

## 11. Cleaner so với `close()` và `try-with-resources`

`Cleaner` (Java 9+) quản lý đăng ký và cleaning actions dựa trên một cơ chế reference thích hợp. Đây là lựa chọn hỗ trợ **fallback cleanup**, không phải thay thế cho **explicit resource ownership**.

Ví dụ Java 17 hoàn chỉnh **`CleanerOwnershipDemo.java`**:

~~~java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicBoolean;

public final class CleanerOwnershipDemo {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class CleanupState implements Runnable {
        private final AtomicBoolean closed = new AtomicBoolean();

        @Override
        public void run() {
            if (closed.compareAndSet(false, true)) {
                System.out.println("CLEANUP");
            }
        }
    }

    private static final class Resource implements AutoCloseable {
        private final Cleaner.Cleanable cleanable;

        Resource() {
            // Action không capture Resource/this.
            cleanable = CLEANER.register(this, new CleanupState());
        }

        @Override
        public void close() {
            cleanable.clean();
        }
    }

    public static void main(String[] args) {
        try (Resource r = new Resource()) {
            System.out.println("IN_USE");
        }
        System.out.println("DONE");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 CleanerOwnershipDemo.java
java CleanerOwnershipDemo
~~~

**Stdout cố định nhờ `try-with-resources` gọi `close()` chủ động:**

~~~text
IN_USE
CLEANUP
DONE
~~~

Nếu bỏ `close`, bạn **không được hứa** `CLEANUP` sẽ xuất hiện trước khi process kết thúc; collector và cleaner có thể chưa chạy. CleanupState trong ví dụ là một `Runnable` riêng **không giữ referent**; tạo `CLEANER.register(this, () -> this.close())` có thể tự giữ `this` sống, làm logic cleaner mất ý nghĩa.

Đối với resource quan trọng như connection, socket, file, native buffer có owner rõ, hãy đóng ngay khi hoàn tất. Cleaner có thể làm fallback cho trường hợp programmer quên close, nhưng không tạo safety guarantee cho mọi lỗi double-free/concurrency.

## 12. `Reference.reachabilityFence` và cửa sổ native lifetime

JIT compiler có thể thấy một object không còn được dùng trong các expression Java về sau và cho phép object hết strongly reachable **sớm hơn cuối lexical scope**. Trong JNI/native-resource code, điều này có thể nguy hiểm khi native work còn đang dùng một handle do wrapper quản lý.

`Reference.reachabilityFence(obj)` (Java 9+) giúp đảm bảo `obj` còn strongly reachable tới chỗ gọi:

~~~java
static void useNative(NativeResource resource) {
    try {
        resource.invokeNative();
    } finally {
        java.lang.ref.Reference.reachabilityFence(resource);
    }
}
~~~

Đây **không phải chương trình độc lập** vì `NativeResource` là kiểu mô tả cần có ở application thực. Fence chỉ nói về **lifetime/reachability** của Java object đến mốc đã định. Nó:

- Không phải lệnh gọi GC.
- Không enqueue ReferenceQueue.
- Không cấp phát/free bộ nhớ mới.
- Không thay cho synchronized/atomic để bảo vệ dữ liệu native giữa thread.
- Không cho phép dùng một native pointer sau khi owner đã explicit close/free.

Khi đọc `WeakReference.get()`, hãy lưu **một lần** kết quả thành local mạnh trước khi dùng:

~~~java
Object snapshot = weak.get();
if (snapshot != null) {
    System.out.println(snapshot.toString());
}
~~~

Đây là **mảnh minh họa**, cần biến `weak` được định nghĩa trong scope. Không nên kiểm tra `if (weak.get() != null)` rồi lại gọi `weak.get().method()` lần hai mà tưởng hai kết quả sẽ luôn giống nhau: GC có thể clear reference giữa hai lần đọc.

## 13. Sai lầm thường gặp và hậu quả

1. **“Queue chứa object gốc đã chết.”** Không, chứa **Reference object**.
2. **“Tạo Reference có queue thì queue có ngay event.”** Sai, registration không enqueue.
3. **“`ref.clear()` tự enqueue.”** Sai.
4. **“`ref.enqueue()` chứng minh GC đã chạy.”** Sai: có thể là manual enqueue.
5. **“`weak.get() == null` nghĩa là GC đã enqueue.”** Sai, clearing và enqueue khác nhau.
6. **“`queue.poll() == null` nghĩa là referent còn sống.”** Sai, chỉ nghĩa hiện chưa có entry sẵn.
7. **“`PhantomReference.get() == null` nghĩa object đã GC.”** Sai: luôn trả null.
8. **“`queue.remove(0)` không chờ.”** Sai, đây là chờ vô hạn.
9. **“`System.gc()` buộc event trong 1 giây.”** Sai, không có deadline.
10. **“Queue event xác nhận native memory đã free.”** Sai, cleanup cần bước riêng.
11. **“ReferenceQueue giữ mọi registration sống.”** Sai, cần registry giữ reference objects.
12. **“Subclass WeakReference có field `original` là vô hại.”** Sai, field mạnh ngăn GC referent.
13. **“Cleaner có SLA giống `close()`.”** Sai, timing phụ thuộc GC.
14. **“`isEnqueued()` là cơ chế cleanup tốt.”** Sai, deprecated vì racy.
15. **“`WeakHashMap` value giữ key vẫn không sao.”** Sai, strong back-reference có thể giữ key.
16. **“Thread xử lý queue có thể bỏ qua interrupt.”** Sai, cần shutdown protocol.
17. **“Soft reference chắc bị clear ngay khi bỏ strong refs.”** Sai, GC có quyền giữ tùy memory demand.
18. **“GC notification đủ cho việc release lock/commit transaction.”** Sai, resource quan trọng cần explicit lifecycle.

## 14. Checklist triển khai ReferenceQueue an toàn

- Chọn đúng **loại Reference** (soft/weak/phantom) cho ý nghĩa ứng dụng.
- Tạo reference với **queue phù hợp**, không mặc định queue tự quản danh sách registration.
- Giữ **Reference object** mạnh trong registry; tuyệt đối tránh lưu referent ở cleanup metadata nếu muốn referent eligible.
- Với event, chỉ dùng ID/handle độc lập để xóa entries hoặc cleanup; không cố lấy referent đã cleared.
- Cài consumer bằng `poll()` theo hoạt động cache hoặc `remove(timeout)` trong worker có shutdown/interruption.
- Xử lý race giữa explicit `close()` và event GC, bảo đảm cleanup idempotent.
- Dọn registration khỏi registry khi event đã xử lý để không giữ metadata vô hạn.
- Không dùng `System.gc()` hay `isEnqueued()` làm đồng hồ hoặc giao thức correctness.
- Với native resources, yêu cầu explicit ownership, try-with-resources và kiểm tra use-after-free/double-free.
- Khi cần observability, đo GC logs, reference queue backlog, số registrations đang giữ và tần suất cleanup; không chỉ đếm số object đã mất strong refs.
- Test nhánh **manual enqueue** bằng stdout xác định; test nhánh **GC** phải chấp nhận timeout/non-determinism.
- Đối chiếu phiên bản JDK: các API trong ví dụ biên dịch với `--release 17`.

## 15. Câu hỏi tự kiểm tra

1. `ReferenceQueue.poll()` trả gì? **Reference object hoặc null**, không phải object gốc.
2. `ref.clear()` có làm `queue.poll()` khác null tức thì không? **Không**.
3. `Reference.enqueue()` có thể được Java code tự gọi không? **Có**.
4. `weak.get() == null` có chứng minh đã dequeue reference không? **Không**.
5. `remove(0)` và `poll()` khác gì? **remove(0) chờ vô hạn, poll không chờ**.
6. Vì sao phải giữ chính `WeakReference` trong một registry? **Để không mất reference notification/metadata khi reference object trở nên unreachable**.
7. Tại sao registry không được giữ `T original` của referent? **Vì tạo strong path ngăn weak reachability**.
8. `PhantomReference.get()` trả object khi chưa được GC không? **Không, luôn null**.
9. GC có cam kết enqueue trong 500 ms sau khi object unreachable không? **Không**.
10. Enqueue event có phải native `free` đã hoàn tất không? **Không**.
11. Vì sao cần idempotent cleanup? **Vì có thể vừa explicit close vừa notification cleanup**.
12. `Cleaner` có đảm bảo chạy khi JVM exit bình thường trong mọi hoàn cảnh không? **Không có deadline bảo đảm**.
13. `Reference.reachabilityFence(x)` giữ x tới thời điểm nào? **Tới mốc lời gọi fence**.
14. `WeakHashMap` có thể bị giữ entry do value trỏ ngược key không? **Có**.
15. SoftReference khác WeakReference ở đâu? **GC có thể giữ soft referent lâu hơn theo memory-demand policy**.
16. Nếu cần release socket trước khi HTTP request trả kết quả, dùng queue hay explicit close? **Explicit close/try-with-resources**.
17. Nếu GC clear reference rồi application poll ngay chưa có event, đó có trái API không? **Không**, enqueue có thể diễn ra sau.
18. Nếu class wrapper đã bị GC phát hiện, có thể lấy object ấy từ PhantomReference để gọi close không? **Không**.

## 16. Tài liệu Java SE 17 đáng đọc

- `java.lang.ref` — các cấp reachability, notification, queue registration: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html
- `ReferenceQueue` — `poll`, `remove`, `remove(long)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html
- `Reference` — `get`, `clear`, `enqueue`, `refersTo`, `reachabilityFence`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html
- `WeakReference`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html
- `SoftReference`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/SoftReference.html
- `PhantomReference`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/PhantomReference.html
- `Cleaner`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html
- `WeakHashMap`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html

**Kết luận kỹ thuật:** ReferenceQueue là kênh **nhận những Reference objects đã enqueue**. Hãy tách rõ **mất strong reachability → GC phát hiện → clear reference → enqueue → application dequeue**, nhớ rằng các mốc **không có deadline**, và event có thể do **enqueue thủ công** chứ không phải GC. Để hệ thống đúng đắn, giữ reference object/metadata phù hợp nhưng không giữ mạnh referent, dùng queue cho **stale-entry cleanup và thông báo bổ trợ**; tài nguyên cần giải phóng đúng hạn phải có **explicit close và ownership rõ ràng**.
