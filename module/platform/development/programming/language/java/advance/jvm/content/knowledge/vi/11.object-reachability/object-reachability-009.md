# `System.gc()` là yêu cầu gợi ý và những giới hạn khi dùng nó để kiểm chứng

Trong Java, `System.gc()` **không phải lệnh đảm bảo thu hồi object ngay lập tức**. Đây là lời yêu cầu/gợi ý JVM dành công sức cho garbage collection. Việc JVM thực sự chạy collector lúc nào, chạy loại collection nào, có xử lý object cụ thể chưa, đã giải phóng bao nhiêu memory, và có trả pages về hệ điều hành không đều **không được bảo đảm bởi một lời gọi `System.gc()`**.

Bài học thuộc chủ đề **khả năng truy cập (reachability)**: muốn hiểu một object có thể bị GC hay không, trước hết phải xét đường tham chiếu từ **GC roots**. Việc gọi explicit GC request là một sự kiện khác hẳn với việc object mất strong references. Không được dùng `System.gc()` để thay thế phân tích root paths, xác minh tài nguyên đã `close()`, hay tạo assertion phụ thuộc GC timing.

## 1. Chính xác `System.gc()` có nghĩa gì?

```java
System.gc();
```

Đây là static method `void` của `java.lang.System`, không nhận đối số. Theo Java SE API, lời gọi **gợi ý JVM nỗ lực tái chế những object không còn được sử dụng để bộ nhớ chúng chiếm có thể sớm được tái dùng**. Cách JVM phản ứng là một quyết định của runtime.

Về bản chất API, nó tương đương yêu cầu:

```java
Runtime.getRuntime().gc();
```

Hai biểu thức không tạo ra một cơ chế “mạnh” và một cơ chế “yếu” riêng biệt. Chúng đều là **explicit GC request**.

| Phát biểu | Đúng/sai | Vì sao? |
| --- | --- | --- |
| `System.gc()` đề nghị VM xem xét thu gom rác | Đúng | Đây là ý định của API |
| Luôn có một Full GC đồng bộ | Sai | Collector/configuration có thể phản ứng khác hoặc bỏ qua |
| Sau lời gọi, mọi object eligible đều đã bị reclaim | Sai | Không có bảo đảm timing/phạm vi |
| Object còn strongly reachable có thể bị hủy vì request này | Sai | JVM phải giữ ngữ nghĩa chương trình |
| `WeakReference.get()` chắc chắn là `null` sau lời gọi | Sai | Còn strong paths, liveness và GC policy |
| JVM nhất định giải phóng RAM vật lý về OS | Sai | Heap committed và RSS có thể giữ nguyên |
| Lời gọi trả về boolean báo GC thành công | Sai | Return type `void` |
| Có thể dùng logs/MXBeans để quan sát VM đã phản ứng thế nào | Đúng | Nhưng kết quả chỉ chứng minh phạm vi điều đã quan sát |

**Quy tắc học tập:** `System.gc()` là *yêu cầu*, không phải *bằng chứng GC đã chạy*, càng không phải *bằng chứng object X đã chết*.

## 2. Reachability: một object là rác khi nào?

Các tracing garbage collectors xét **đồ thị object references** từ một tập **GC roots**. Những roots điển hình gồm references còn live trong execution frames, static/runtime class state phù hợp, JNI handles và các cấu trúc runtime có chức năng giữ sống object.

```text
  GC root 1 ──► A ──► C ──► D
  GC root 2 ──► B ──► C

  Không có root ──► E ◄─► F
```

Giả sử mọi mũi tên trên là **strong references**:

- A, B, C, D có thể lần tới từ root, vì thế thuộc tập strongly reachable.
- E và F trỏ lẫn nhau nhưng không có đường từ root đến chúng. Chu trình không tự giữ object sống: một tracing collector có thể reclaim chu trình không reachable.
- Nếu bỏ root 1 thì C/D vẫn reachable qua B. Mất **một** đường chưa đủ nếu còn đường khác.
- Một local variable được gán `null` không chứng minh không còn đường giữ sống qua field, static cache, ThreadLocal, listener hay JNI.

### Ba câu hỏi khác nhau

1. **Strongly reachable?** Có đường strong reference sống từ một root tới object trong ngữ cảnh đang xét?
2. **Eligible for reclamation?** Sau khi xét special-reference processing và các điều kiện VM, object có thể được thu hồi?
3. **Đã được thu hồi?** Collector đã thực hiện công việc reclaim/reuse tương ứng?

Object có thể eligible nhưng chưa được GC xử lý. Thậm chí khi đã reclaim, vùng heap vẫn có thể giữ **committed memory** để dùng cho allocation sau, nên process RSS không nhất thiết giảm.

### `null` không phải lệnh thu hồi

```java
Object a = new Object();
Object b = a;
a = null;
System.gc();
System.out.println(b != null); // true
```

Đây là đoạn đặt trong một method. Vì `b` còn được sử dụng và trỏ tới object, một collector đúng không thể làm object biến mất trước dòng `println`. Không có cách dùng `System.gc()` để “ép xóa” object còn cần cho ngữ nghĩa Java.

Ngay cả khi nguồn không còn `b`, JIT/VM có thể xác định **reference liveness** khác phạm vi lexical của biến; việc còn hoặc mất strong path phải suy từ toàn bộ runtime graph, không chỉ từ số dấu ngoặc của source.

## 3. JVM có thể không thực hiện explicit GC như bạn tưởng

Một số người gọi `System.gc()` rồi tìm một dòng “Full GC” trong logs. Nhưng phản ứng phụ thuộc:

- **JVM implementation** và release cụ thể: HotSpot, OpenJ9, những VM khác không phải luôn dùng cùng policy.
- **Garbage collector**: Serial, Parallel, G1, ZGC, Shenandoah hoặc collector được hỗ trợ khác.
- **Flags**: explicit GC bị vô hiệu hóa, được hướng tới concurrent cycle, hay xử lý theo mặc định.
- **Tải runtime**: allocation rate, heap occupancy, marking state và các pha concurrent đang diễn ra.
- **Quyết định hệ thống**: việc thu hồi những vùng bộ nhớ phù hợp, lịch của các GC threads và thời điểm kiểm tra metrics.

### Một số flags HotSpot đáng biết

| Cấu hình | Ý nghĩa |
| --- | --- |
| `-XX:+DisableExplicitGC` | Bỏ qua một số explicit GC requests như `System.gc()`; automatic GC vẫn hoạt động |
| `-XX:+ExplicitGCInvokesConcurrent` | Trên collector/configuration hỗ trợ, explicit request có thể dùng cơ chế concurrent |
| `-Xlog:gc*:info` | Ghi GC logs bằng unified logging trên HotSpot JDK 17+ |
| `-XX:+PrintFlagsFinal` | Quan sát flags và giá trị thực tế của JVM được chạy |

Không đưa các flags này vào production theo công thức duy nhất. Một JVM có thể không hỗ trợ flag HotSpot hoặc hỗ trợ với giới hạn khác. Luôn xác nhận `java --version` và chạy `java -XX:+PrintFlagsFinal -version` trước khi giải thích log hoặc sửa tuning.

### `DisableExplicitGC` không có nghĩa “tắt garbage collector”

Nếu HotSpot bỏ qua lời gọi `System.gc()`, nó **vẫn cần GC tự động** khi application tạo allocation pressure. Flag này không ngăn collector thu hồi object theo các chu kỳ thông thường. Nó chỉ ảnh hưởng đường explicit request phù hợp, không làm garbage collection vô hiệu hoàn toàn.

### “Full GC” không phải kết quả portable

Trên một số HotSpot collector/config, explicit GC có thể gây stop-the-world Full GC. Nhưng **không được đưa quy luật đó thành Java SE guarantee**. Một cấu hình khác có thể khởi động concurrent work hoặc không làm gì. Việc lựa chọn collector cần được đọc cùng log, không chỉ từ một câu gọi Java.

## 4. GC roots quyết định object còn sống, không phải `System.gc()`

Ví dụ:

```java
class Cache {
    static final java.util.List<Object> ITEMS =
            new java.util.ArrayList<>();

    static void add() {
        ITEMS.add(new byte[1024]);
    }
}
```

Đây là class minh họa có thể biên dịch. Nếu runtime class/static state còn live, mỗi phần tử trong `ITEMS` có strong path phù hợp:

```text
GC root / runtime class state
  → Cache.ITEMS
  → ArrayList.elementData
  → byte[] element
```

Gọi `System.gc()` nhiều lần cũng **không được** reclaim arrays khi đường giữ sống còn hợp lệ. Đây thường là lỗi quản lý lifecycle/cache, không phải “GC quá yếu”.

Các ví dụ khác về giữ sống ngoài ý muốn:

- Một `ThreadLocal` chưa được `remove()` trên worker thread pool tồn tại lâu.
- Listener được đăng ký mà không unregister.
- Callback/lambda capture object trong scheduled task.
- Queue giữ payloads quá lâu.
- JNI global reference chưa release.
- Class loader hoặc class metadata giữ cả đồ thị object/plugin.
- Static map không có eviction/TTL/size bounds.

Cách sửa là **cắt bớt strong references không còn cần thiết**, đặt giới hạn và quản lý lifecycle. `System.gc()` không tự biết object đã hết ý nghĩa nghiệp vụ.

## 5. Strong, soft, weak và phantom references khác nhau

Một phép thử dùng `WeakReference` có ý nghĩa khác với việc theo dõi ordinary strong references.

| Loại | Tác dụng về reachability | Hạn chế khi dùng để kiểm chứng |
| --- | --- | --- |
| Strong reference | Giữ object theo đường tham chiếu mạnh còn live | Source scope không đồng nhất hoàn toàn với VM liveness |
| `SoftReference<T>` | GC có thể clear referent theo chính sách, liên quan memory demand | Không cam kết clear sau một lần explicit GC |
| `WeakReference<T>` | Không giữ referent sống khi chỉ còn weakly reachable | `get()` có thể vẫn khác `null` sau `System.gc()` |
| `PhantomReference<T>` | Theo dõi giai đoạn thích hợp qua queue, thường dùng làm nền cho cleanup | `get()` **luôn trả `null`**, kể cả trước GC |
| `ReferenceQueue<T>` | Nhận các reference objects được enqueue theo luật API | Queue event không được bảo đảm xuất hiện ngay sau explicit request |

### Có những điểm rất dễ bị nhầm

- Một **`WeakReference` object** có thể vẫn strongly reachable, trong khi **referent** của nó không còn được giữ mạnh.
- `weak.get()==null` chứng minh weak reference **không còn trả referent tại thời điểm đó**. Nó **không chứng minh** chính lời gọi `System.gc()` đã làm việc này: application có thể gọi `weak.clear()`, hoặc GC khác đã thực hiện.
- `weak.get()!=null` không chứng minh object đang leak. Có thể GC chưa chạy, hoặc còn strong/soft references theo luật runtime.
- `PhantomReference.get()` luôn `null`; không thể dùng giá trị này làm bài test đã reclaim.
- Việc clearing và enqueuing có những chi tiết xử lý riêng. `queue.poll()==null` không chứng minh referent vẫn sống.

Nếu cần chắc chắn file/socket/native handle được đóng, dùng `AutoCloseable` và `try-with-resources`; không xây logic resource cleanup dựa vào GC timing.

## 6. Ví dụ Java 17+ chạy được: strong path và weak reference

Chương trình sau minh họa **hai kết quả chắc chắn khi còn strong path** và **hai quan sát không được bảo đảm khi bỏ strong path**. Không có assertion dựa vào GC scheduling.

Tạo file `ExplicitGcDemo.java`:

```java
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

public class ExplicitGcDemo {
    private static volatile Object held;

    public static void main(String[] args) {
        ReferenceQueue<Object> queue = new ReferenceQueue<>();
        Object payload = new byte[1024];
        held = payload;

        WeakReference<Object> weak = new WeakReference<>(payload, queue);

        System.out.println("start");
        System.out.println("strongly held: " + (weak.get() == payload));

        System.gc(); // Gợi ý, không phải lệnh buộc reclaim.

        System.out.println("after hint while held: "
                + (weak.get() == payload));

        // Giữ tham chiếu payload sống tới vị trí này.
        Reference.reachabilityFence(payload);

        held = null;
        payload = null;
        // Không còn strong path được lập trình cố ý trong source.

        System.gc();

        boolean cleared = weak.get() == null;
        boolean enqueued = queue.poll() != null;

        System.out.println("weak cleared: " + cleared);
        System.out.println("queue observed: " + enqueued);
        System.out.println("end");
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac -encoding UTF-8 ExplicitGcDemo.java
java ExplicitGcDemo
```

**Những dòng luôn có mặt theo thứ tự, với giá trị ổn định:**

```text
start
strongly held: true
after hint while held: true
```

Sau ba dòng trên, chương trình in tiếp:

```text
weak cleared: <true-or-false>
queue observed: <true-or-false>
end
```

`<true-or-false>` **là placeholder giải thích**: mỗi vị trí được chương trình in thành literal `true` hoặc `false`, phụ thuộc collector, timing và reference processing. Đây không phải bộ stdout cố định duy nhất.

**Giải thích:**

1. `payload` và static `held` cùng giữ object trong giai đoạn đầu, nên GC phải bảo toàn referent; `weak.get()==payload` đúng.
2. Lời gọi `System.gc()` đầu tiên không được phá hủy object đang còn strongly reachable.
3. `Reference.reachabilityFence(payload)` biểu thị ranh giới bảo toàn strong reachability đến điểm đó.
4. Sau khi xóa hai strong paths cố ý, object **có thể** trở thành weakly reachable; nhưng Java không cam kết GC đã clear weak referent trước dòng kiểm tra.
5. `queue.poll()` chỉ quan sát việc enqueue tới thời điểm hỏi, không đồng nghĩa “GC cycle đã hoàn tất”.
6. `weak.get()` có thể tạm tạo strong reference khi trả referent khác `null`; bản thân phép đo có thể ảnh hưởng liveness ở khoảng thời gian rất ngắn.

**Không sửa chương trình thành một vòng lặp vô hạn gọi `System.gc()` cho tới khi `weak.get()==null`.** Thí nghiệm đó có thể không kết thúc khi explicit GC bị bỏ qua, còn root paths hoặc chỉ vì VM chưa xử lý referent.

## 7. Chạy cùng ví dụ với GC logs và flags

Trên HotSpot JDK 17+:

```bash
java -Xlog:gc*:info ExplicitGcDemo
java -XX:+DisableExplicitGC -Xlog:gc*:info ExplicitGcDemo
```

Ở lần đầu, JVM có thể log một GC event có nguyên nhân liên quan `System.gc()`, tùy collector và cấu hình. Ở lần thứ hai, HotSpot được yêu cầu bỏ qua explicit GC requests phù hợp; tuy nhiên GC **tự động** do allocation pressure hoặc các lý do khác vẫn có thể xuất hiện.

Một dạng log minh họa **không cố định**:

```text
[info][gc] ... Pause Full (System.gc()) ...
```

Dấu `...` trong ví dụ không phải offset/timing cố định. Một số collectors dùng concurrent work hoặc format/cause khác. **Không viết unit test assert rằng stdout/log luôn phải chứa đúng dòng này.**

### Kết quả logs chứng minh điều gì?

- Có event được ghi rõ nguyên nhân explicit GC: JVM trên môi trường ấy đã ghi nhận/làm công việc liên quan request.
- Không có event: có thể request bị bỏ qua, VM xử lý khác hoặc event không được bật dưới tag/level đang quan sát.
- Heap “before/after” thay đổi: có công việc GC/memory accounting được đo, **không xác định chắc chắn object duy nhất nào đã reclaim**.
- Log có “Pause Full”: phản ánh loại event được JVM ghi ở lần chạy đó, không chứng minh mọi collector luôn Full GC khi gặp `System.gc()`.

**So sánh giữa hai runs không hoàn toàn giống hệt nhau**: JIT warm-up, thread scheduling, heap sizes và tiến trình allocation đều có thể khác. Để đánh giá performance, cần lặp lại nhiều lần với workload, flags và môi trường kiểm soát.

## 8. GC logs và Java Management APIs: quan sát có giới hạn

Java cung cấp `GarbageCollectorMXBean` để đọc tên collector và các thống kê như số lần/thời gian thu gom, khi implementation hỗ trợ.

Tạo file `GcCounterDemo.java`:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.List;

public class GcCounterDemo {
    private static void show(String label) {
        List<GarbageCollectorMXBean> beans =
                ManagementFactory.getGarbageCollectorMXBeans();

        System.out.println(label);
        for (GarbageCollectorMXBean bean : beans) {
            System.out.println(bean.getName() + ": count="
                    + bean.getCollectionCount()
                    + ", time(ms)=" + bean.getCollectionTime());
        }
    }

    public static void main(String[] args) {
        show("before");
        System.gc();
        show("after");
        System.out.println("request completed");
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 GcCounterDemo.java
java GcCounterDemo
```

**Dạng output:**

```text
before
<các dòng collector và số liệu thực tế>
after
<các dòng collector và số liệu thực tế>
request completed
```

Hai dòng `<các dòng collector và số liệu thực tế>` là **mẫu giải thích**, không phải kết quả in nguyên văn; collector names và counts phụ thuộc JVM. Có bean trả `-1` nếu một thông số không được hỗ trợ.

**Không có quy tắc “`System.gc()` được gọi một lần thì tổng collection count tăng đúng một”.** Các JVM/collectors có định nghĩa collection event, pha concurrent và metrics khác nhau. VM cũng có thể thực hiện GC vì lý do không liên quan giữa hai lần đo.

Nếu mục tiêu là xem các event chi tiết hơn, dùng GC unified logging hoặc Java Flight Recorder (JFR) theo policy của môi trường. Nếu mục tiêu là tìm **đường giữ sống** của object, dùng heap dump/profiler thay vì chỉ GC counters.

## 9. Tại sao đo bộ nhớ trước/sau `System.gc()` dễ sai?

Mẫu phổ biến:

```java
Runtime r = Runtime.getRuntime();
long before = r.totalMemory() - r.freeMemory();
System.gc();
long after = r.totalMemory() - r.freeMemory();
System.out.println("delta=" + (before - after));
```

Đây là **đoạn trong method**, không phải chương trình độc lập. `delta` ở đây **không phải kích thước chính xác của object muốn kiểm tra**.

Những nguồn sai lệch:

- GC có thể chưa chạy, chạy từ trước hoặc chạy vì một nguyên nhân khác.
- Các Java/JVM threads khác có thể allocate thêm objects giữa hai snapshots.
- Compiler/JIT có thể tối ưu bỏ những allocations không quan sát được, qua escape analysis hoặc scalar replacement.
- VM có thể commit hoặc uncommit heap pages theo policy khác thời điểm object reclamation.
- `Runtime.totalMemory()` và `freeMemory()` đo theo mô hình heap của VM, **không đồng nghĩa retained size của một object graph**.
- Collector có thể thu hồi nhiều objects không liên quan, làm delta không đại diện riêng cho object X.

### Các thước đo khác nhau

| Chỉ số | Điều đo |
| --- | --- |
| Heap used | Bộ nhớ heap đang được dùng theo metric JVM |
| Heap committed | Phần heap JVM đã committed |
| Heap maximum / reserved | Giới hạn hoặc không gian ảo VM cho phép sử dụng theo cấu hình |
| Process RSS | Các trang RAM resident OS gán cho process, gồm nhiều vùng ngoài Java heap |
| Shallow object size | Bộ nhớ của chính object, không đi theo các references |
| Retained size | Bộ nhớ có thể trở nên reclaimable khi mất object dominator phù hợp |

Object đã bị GC reclaim không có nghĩa process phải trả các pages ngay về OS. JVM thường giữ vùng heap đã committed để cấp phát lại nhanh. Do đó **RSS không giảm** không đủ để nói “GC không có tác dụng”.

Muốn đo shallow size của object, cân nhắc Java Object Layout (JOL) hoặc `Instrumentation.getObjectSize` (có giới hạn implementation). Muốn đo retained size, dùng heap profiler/dominator tree.

## 10. Vì sao `ReferenceQueue` cũng không tạo lịch GC?

`ReferenceQueue` nhận các reference objects khi chúng được VM enqueue theo các luật reference processing. Nó hữu ích khi ứng dụng muốn quan sát và xử lý một sự kiện, nhưng không bảo đảm sự kiện đã xảy ra ngay sau `System.gc()`.

```java
ReferenceQueue<Object> queue = new ReferenceQueue<>();
Object obj = new Object();
WeakReference<Object> weak = new WeakReference<>(obj, queue);
obj = null;
System.gc();

// Không có bảo đảm queue.poll() đã khác null tại đây.
boolean received = queue.poll() != null;
```

Đây là **đoạn code minh họa đặt trong method**, cần import `java.lang.ref.*` nếu muốn biên dịch. Ngoài GC timing, chính phép phân tích liveness và những reference còn ở nơi khác cũng ảnh hưởng việc object eligible.

### Đừng dùng `PhantomReference.get()` làm cờ “đã GC”

```java
ReferenceQueue<Object> q = new ReferenceQueue<>();
Object object = new Object();
PhantomReference<Object> p = new PhantomReference<>(object, q);
System.out.println(p.get() == null); // true, ngay cả trước GC
```

Đoạn này yêu cầu import `java.lang.ref.*` và thuộc một method. `PhantomReference.get()` **luôn trả `null`** theo API, vì vậy không phản ánh object đã thu hồi hay chưa. Khi cần cleanup theo API, dùng `ReferenceQueue` / Cleaner thích hợp với những giới hạn về timing, không tự suy luận từ `get()`.

## 11. `Reference.reachabilityFence` giải quyết một bài toán khác

JIT có thể xác định object không còn cần dùng ở thời điểm sớm hơn cuối method hoặc cuối lexical scope. Khi object quản lý một native handle, có tình huống native operation vẫn cần tài nguyên gắn với object nhưng VM không còn thấy object phải sống nếu thiếu một lời bảo đảm thích hợp.

Java 9+ hỗ trợ:

```java
Reference.reachabilityFence(object);
```

Phương thức này cho phép giữ mạnh object **ít nhất tới điểm gọi fence**, khi cần bảo đảm reachability cho đoạn code phía trước. Nó **không** ép GC chạy, không biến `System.gc()` thành đồng bộ và không bảo đảm object sẽ chết ngay sau fence.

Ví dụ minh họa (chưa chạy độc lập vì cần khai báo `NativeApi`):

```java
final class NativeResource {
    final long handle;

    NativeResource(long handle) {
        this.handle = handle;
    }

    void use() {
        NativeApi.perform(handle);
        java.lang.ref.Reference.reachabilityFence(this);
    }
}
```

Khi tài nguyên phải đóng một cách có thứ tự, nên ưu tiên `AutoCloseable`, `close()` và `try-with-resources`. Fence phục vụ một ràng buộc reachability; **không thay thế resource lifecycle**.

## 12. `System.gc()` không đảm bảo chạy finalizers/Cleaners

**Finalization** là cơ chế Java lịch sử, được deprecated for removal vì không đáng tin và có vấn đề về an toàn/hiệu năng. `System.gc()` không bảo đảm finalizers chạy đúng lúc; `System.runFinalization()` cũng không phải “nút đóng hết file handles”.

- Finalizer có thể không chạy trước khi process thoát.
- Finalizer có thể giữ/sống lại object trong những trường hợp legacy.
- Cleaner dựa vào GC/reference processing nên thời điểm chạy cũng **không xác định**.
- Resource file/socket/database connection cần close theo lifecycle của chương trình, không chờ heap pressure.
- Gọi GC thường xuyên có thể tạo pause mà vẫn không đóng tài nguyên đang bị giữ bởi reference mạnh.

Ví dụ dùng API chuẩn để đóng tài nguyên:

```java
import java.io.BufferedReader;
import java.nio.file.Files;
import java.nio.file.Path;

class ReadFileExample {
    static String firstLine(Path path) throws Exception {
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            return reader.readLine();
        }
    }
}
```

Đây là **class minh họa có method**, chưa có `main`. `try-with-resources` gọi `close()` khi ra khỏi block theo ngữ nghĩa Java, bất kể `System.gc()` có chạy hay không.

## 13. Testing: đừng viết assertion phụ thuộc GC timing

Assertion sau **không đáng tin**:

```java
WeakReference<Object> weak = new WeakReference<>(new Object());
System.gc();
assert weak.get() == null;
```

Đoạn này đặt trong một method có import phù hợp. Nó có thể thất bại ngay cả khi application và JVM hoàn toàn đúng. Lý do: explicit request có thể bị bỏ qua hoặc collector chưa clear reference ở thời điểm assert. Chạy với `-XX:+DisableExplicitGC` làm sự thiếu chắc chắn càng rõ.

### Kiểm chứng hành vi ứng dụng có thể xác định

Nếu mục tiêu là đảm bảo một resource được close, viết test dựa trên **hành vi tường minh**, ví dụ:

```java
final class Resource implements AutoCloseable {
    private boolean closed;

    @Override
    public void close() {
        closed = true;
    }

    boolean isClosed() {
        return closed;
    }
}
```

Trong method test:

```java
Resource resource = new Resource();
resource.close();
if (!resource.isClosed()) {
    throw new AssertionError("resource was not closed");
}
```

Không cần `System.gc()`; test chỉ phụ thuộc contract của `Resource.close()`.

### Nếu bắt buộc kiểm tra yếu tố GC ở integration tests

1. Chạy test trong **JVM process riêng** để không ảnh hưởng suite khác.
2. Ghi rõ JVM version/vendor/collector/flags.
3. Giữ references/referents đúng vòng đời, tránh test fixture giữ mạnh object.
4. Dùng timeout có giới hạn và chấp nhận kết quả **inconclusive về timing** nếu không thấy GC.
5. Không tạo vòng lặp vô hạn gọi `System.gc()`.
6. Không dùng kết quả không xảy ra GC trong timeout để kết luận chương trình leak.
7. Kết hợp `ReferenceQueue` với GC logs khi cần, ghi ranh giới chứng minh của từng phép đo.

**Đặc biệt:** trong vòng lặp `weak.get()!=null`, mỗi lần gọi `get()` trả referent khác null sẽ tạo một temporary strong reference. Điều đó có thể làm liveness khó dự đoán hơn; tránh dùng polling theo cách làm thay đổi đối tượng đang quan sát.

## 14. Các công cụ có giá trị hơn khi debug “GC không dọn object”

Một số công cụ trên HotSpot JDK 17:

```bash
java --version
java -XX:+PrintFlagsFinal -version
jcmd -l
jcmd PID GC.heap_info
jcmd PID GC.class_histogram
```

`PID` là placeholder: thay bằng PID thật từ `jcmd -l`. `jcmd PID help` giúp xem JVM cụ thể hỗ trợ lệnh nào. Heap histogram/dump có thể tốn thời gian và gây pause, nhất là trên production; luôn cân nhắc quyền truy cập, lưu lượng và dữ liệu nhạy cảm.

### Chọn công cụ theo câu hỏi

| Câu hỏi | Công cụ hữu ích | Giới hạn |
| --- | --- | --- |
| VM có ghi nhận explicit GC request? | `-Xlog:gc*`, JFR GC events | Không chứng minh object riêng đã reclaimed |
| Tần suất/thời gian GC thế nào? | `GarbageCollectorMXBean`, logs, JFR | Không cho retaining path của object |
| Object nào giữ object X sống? | Heap dump, **Paths to GC Roots** | Snapshot, cần hiểu reference strength |
| Có một static cache giữ data không? | Heap analyzer + dominator tree | Thấy retaining paths, vẫn phải xác minh logic nghiệp vụ |
| Mức heap used/committed/RSS ra sao? | MXBeans, OS monitoring, NMT | Các chỉ số không được đồng nhất |
| Một object chiếm bao nhiêu byte shallow? | JOL, Instrumentation | Không cho GC timing |
| Tài nguyên đã đóng chưa? | Explicit close, API state, test doubles | Không nên dùng GC làm oracle |

Với **memory leak** do một root path ngoài ý muốn, “chạy GC mạnh hơn” không phải cách sửa. Tìm root path và cắt reference không cần giữ mới là hướng đúng.

## 15. `System.gc()` và hiệu năng: tại sao không gọi sau mỗi request?

Collector thường có policy về heap occupancy, allocation rate, generations/regions, time budgets và phases đang diễn ra. Application không đủ bối cảnh nội bộ để chọn một collection point tối ưu sau mỗi request.

Lặp explicit GC quá thường xuyên có thể:

- Tăng pauses và latency p95/p99 khi VM chọn một dạng collection tốn kém.
- Tiêu thụ CPU/memory bandwidth của GC threads.
- Làm nhiễu warm-up/JIT benchmark hoặc những tác vụ có độ trễ chặt.
- Không mang lại gì nếu VM bỏ qua requests hoặc live-set vẫn còn root paths mạnh.
- Khiến nhóm phát triển hiểu nhầm vấn đề leak/resource management đã được giải quyết.

**Không khẳng định một lời gọi luôn chậm** — collector có thể bỏ qua hoặc xử lý concurrent. Nhưng gọi một cách mù quáng trong production là lựa chọn cần số liệu thực nghiệm chứng minh.

Nếu app liên tục gần OutOfMemoryError, hãy xem allocation rate, retaining paths, cache/queue sizes, heap limits, native memory và công cụ profiling. Đổi thứ tự GC requests mà không sửa cấu trúc giữ sống thường không giải quyết vấn đề.

## 16. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`System.gc()` luôn thu gom ngay.” | Đây là request, collector tùy JVM/flags |
| “Mọi `System.gc()` đều là Full GC.” | Không phải cam kết Java SE |
| “Bỏ strong reference thì GC sẽ chạy ngay.” | Reachability và lịch collector là hai việc khác |
| “`System.gc()` xóa cả object vẫn có strong root path.” | Collector phải giữ object còn cần cho chương trình |
| “`WeakReference.get()==null` chứng minh explicit GC đã thành công.” | Có thể clear bằng cách khác; chỉ nói về weak reference tại thời điểm đọc |
| “`WeakReference.get()!=null` chứng minh object leak.” | Có thể GC chưa chạy hoặc còn đường sống hợp lệ |
| “`PhantomReference.get()==null` nghĩa object đã chết.” | `get()` luôn trả null |
| “`ReferenceQueue.poll()==null` chứng minh object đang sống.” | Enqueue có timing riêng |
| “Sau `System.gc()` RSS phải giảm.” | JVM có thể giữ committed pages |
| “Heap used delta chính là size object X.” | Delta gồm nhiều objects và tác động runtime khác |
| “`-XX:+DisableExplicitGC` ngắt GC tự động.” | Automatic GC vẫn hoạt động |
| “Finalizer chắc chắn chạy sau explicit GC.” | Không đảm bảo; finalization là legacy |
| “GC thay được `close()`.” | Resource cleanup cần lifecycle tường minh |
| “Mọi local trong scope là root tới hết method.” | JIT liveness có thể ngắn hơn lexical scope |
| “`System.gc()` làm test weak cache deterministic.” | GC timing là bất định |
| “Gọi explicit GC nhiều lần sửa memory leak.” | Strong root paths vẫn giữ object |

## 17. Bài tập kèm đáp án

**Bài 1.** Có `Object a = new Object(); Object b = a; a = null;` rồi `System.gc()`. Sau đó `System.out.println(b != null)` in gì?  
**Đáp án:** `true`. `b` còn tham chiếu object khi được dùng.

**Bài 2.** JVM chạy `-XX:+DisableExplicitGC`, GC logs không báo event ngay sau `System.gc()`. Có phải GC hỏng?  
**Đáp án:** Không. Explicit request có thể bị bỏ qua; VM vẫn tự GC khi cần.

**Bài 3.** `weak.get()` khác `null` sau `System.gc()`. Có phải object chắc chắn leak?  
**Đáp án:** Không. Có thể còn strong path hoặc chưa xử lý weak reference.

**Bài 4.** `weak.get()==null` có chứng minh RSS giảm không?  
**Đáp án:** Không. Weak reference clearing và memory accounting/OS pages là các sự kiện khác nhau.

**Bài 5.** `PhantomReference.get()` trả `null` ngay sau constructor. Có phải referent đã reclaimed?  
**Đáp án:** Không. API luôn trả null.

**Bài 6.** Gọi explicit GC sau mỗi request làm latency cao. Có nên tăng số lần gọi cho sạch hơn?  
**Đáp án:** Không; điều tra root cause, đo pause/tải và cân nhắc bỏ explicit requests.

**Bài 7.** Static `List<byte[]>` giữ một triệu phần tử. `System.gc()` có phải cách giảm retained heap?  
**Đáp án:** Không. Cần loại bỏ/giới hạn references khi không cần.

**Bài 8.** `GarbageCollectorMXBean` count tăng một lần. Có chắc GC reclaim object X?  
**Đáp án:** Không. Count phản ánh collection events theo collector, không báo một object identity cụ thể.

**Bài 9.** Sau GC, heap used giảm nhưng process RSS không giảm. Có bắt buộc xem là lỗi?  
**Đáp án:** Không. JVM có thể giữ committed heap để tái sử dụng.

**Bài 10.** Muốn test file resource được đóng, nên làm gì?  
**Đáp án:** Dùng `try-with-resources`/`close()` và assert hành vi tường minh; không chờ `System.gc()`.

**Bài 11.** Vì sao compiler liveness khiến test dùng `System.gc()` khó đoán?  
**Đáp án:** VM có thể xác định reference không cần giữ tới hết scope; còn temporary references hoặc tối ưu allocation làm kết quả khác kỳ vọng.

**Bài 12.** `Reference.reachabilityFence(x)` có ép GC ngay sau đó không?  
**Đáp án:** Không. Nó giữ object mạnh tới vị trí cần thiết, không điều khiển lịch GC.

**Bài 13.** Cần biết tại sao một object chưa chết dù gọi explicit GC nhiều lần, dùng công cụ nào?  
**Đáp án:** Heap dump/profiler để xem **Paths to GC Roots**, static refs, ThreadLocals, listeners, queues, JNI handles.

**Bài 14.** `Runtime.getRuntime().gc()` có stronger guarantee hơn `System.gc()`?  
**Đáp án:** Không. Cùng ý nghĩa explicit GC request, không bảo đảm thu hồi.

**Bài 15.** Gọi `System.gc()` xong return bình thường có nghĩa toàn bộ GC đã hoàn tất?  
**Đáp án:** Không có guarantee portable về kiểu GC và thời điểm hoàn tất toàn bộ công việc.

## 18. Checklist kiểm chứng an toàn

- [ ] Xác định rõ đang hỏi: **GC request có được xử lý**, hay **object còn reachable**, hay **resource đã close**?
- [ ] Ghi JVM vendor, version, garbage collector và flags của tiến trình.
- [ ] Không assert GC timing hay `WeakReference` clearing sau một lời gọi.
- [ ] Hiểu `WeakReference`, `PhantomReference` và `ReferenceQueue` có semantics khác nhau.
- [ ] Kiểm tra hidden strong paths qua static fields, ThreadLocal, listeners, JNI.
- [ ] Dùng GC logs/JFR/MXBeans nếu kiểm tra collector behavior.
- [ ] Dùng heap dump và Paths to GC Roots nếu kiểm tra retaining paths.
- [ ] Không đánh đồng heap used, committed, reserved, RSS và retained size.
- [ ] Có timeout nếu thí nghiệm reference enqueue; không đợi vô hạn.
- [ ] Không gọi explicit GC như phương thức quản lý resource.
- [ ] Dùng test deterministic cho logic ứng dụng và lifecycle.
- [ ] Tránh tuning production dựa trên một lần chạy, một collector hoặc một bản JDK.

## 19. Tổng kết và tài liệu chuẩn

**`System.gc()` chỉ là lời gợi ý đối với JVM**, không phải một primitive đồng bộ để đo object lifetime, ép chạy Full GC, khẳng định weak reference bị clear, hoặc buộc hệ điều hành nhận lại bộ nhớ.

- Muốn hiểu **tại sao object sống**, tìm **strong paths tới GC roots**.
- Muốn biết **collector phản ứng với explicit request thế nào**, dùng GC logs/JFR/MXBeans của JVM và flags đang chạy.
- Muốn kiểm tra **memory leak**, dùng root-path/retained-size analysis, không ép GC lặp lại.
- Muốn bảo đảm **resource cleanup**, dùng API đóng tường minh.
- Muốn quan sát weak/soft/phantom references, chấp nhận **timing không được bảo đảm** và semantics khác nhau của từng loại reference.

**Tài liệu đối chiếu:**

1. Java SE 17 — `System.gc()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#gc()
2. Java SE 17 — `Runtime.gc()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html#gc()
3. Java SE 17 — `java.lang.ref` package, định nghĩa các mức reachability: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html
4. Java SE 17 — `Reference.reachabilityFence`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html
5. Oracle JDK 17 — Garbage Collection Tuning Guide: https://docs.oracle.com/en/java/javase/17/gctuning/
6. Oracle JDK 17 — `java` command/flags: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
7. OpenJDK JEP 421 — Deprecate Finalization for Removal: https://openjdk.org/jeps/421

**Ghi nhớ:** nếu một bài kiểm thử có tiền đề “gọi `System.gc()` rồi object X chắc chắn biến mất”, tiền đề ấy sai. Hãy biến bài kiểm thử thành **kiểm chứng điều Java thực sự bảo đảm**, và dùng explicit GC chỉ như một tín hiệu quan sát trong thí nghiệm JVM có điều kiện rõ ràng.