# 12.4 VolatileCallSite và ngữ nghĩa công bố target mới

**Ngữ cảnh:** Java Advance → dynamic-runtime → 12. CallSite.

Trong Java `java.lang.invoke`, một `CallSite` là nơi chứa **`MethodHandle` đích (target)** để một điểm gọi động sử dụng. Đối với `VolatileCallSite`, target này mang **ngữ nghĩa bộ nhớ giống một biến `volatile`**. Khi thread A cài `MethodHandle` mới qua `setTarget`, thread B đang dùng `getTarget` hoặc gọi qua `dynamicInvoker` sẽ quan sát cập nhật theo quy tắc đồng bộ `volatile` của Java Memory Model (JMM). Đây là lý do tồn tại của `VolatileCallSite`: **thay đổi cách dispatch tại runtime với đảm bảo nhìn thấy cập nhật giữa các thread**, không cần thao tác `MutableCallSite.syncAll`.

Bài học giải thích cơ chế, API, thời điểm xảy ra volatile read/write, quan hệ *happens-before*, khác biệt giữa **live invoker** và **target snapshot**, quy tắc kiểu, giới hạn của công bố, cách kiểm chứng bằng Java 17 và các lỗi thường gặp.

## 1. `CallSite` giữ cái gì và tại sao phải công bố target?

Một `MethodHandle` mô tả một hành vi có chữ ký `MethodType`. `CallSite` là một **điểm liên kết** chứa target handle dùng để xử lý lời gọi. Một call site có thể phục vụ một hoặc nhiều điểm gọi `invokedynamic`, hoặc dùng độc lập qua `dynamicInvoker()`.

Ví dụ hệ thống routing ban đầu trỏ đến một handler:

```text
Caller  ->  live invoker  ->  callSite.target = handle V1
                                   |
                                   +-- V1("A") -> "first:A"
```

Khi cấu hình thay đổi, ta không muốn xây lại mọi chỗ gọi. Thay vì thế, writer thay `callSite.target`:

```text
                       writer thread
                            |
                   setTarget(handle V2)
                            |
                            v
Caller -> live invoker -> callSite.target = handle V2
                                              |
                                              +-- V2("A") -> "second:A"
```

**`VolatileCallSite` không cần sửa bytecode hay thay đối tượng invoker.** Đối tượng `MethodHandle` do `dynamicInvoker()` trả về vẫn có thể được cache ở caller; chính **đích thực tế bên dưới** sẽ được đọc theo trạng thái call site tại mỗi lời gọi theo ngữ nghĩa API.

Trong thực tế, các ứng dụng như plugin router, feature switch, policy dispatcher hoặc thay thế implementation động có thể xây một adapter như vậy. Nhưng điều kiện quan trọng là target mới **phải có cùng `MethodType`** và code quản lý trạng thái phải tôn trọng đồng bộ, lỗi, lifecycle.

## 2. Ba biến thể quan trọng của `CallSite`

| Loại | `target` thay đổi? | Ngữ nghĩa visibility khi đổi | Phương án sử dụng |
| --- | --- | --- | --- |
| `ConstantCallSite` | Không; `setTarget` ném `UnsupportedOperationException` | Target không đổi sau khi được khởi tạo hợp lệ | Liên kết cố định, không cần thay implementation |
| `MutableCallSite` | Có | Tương tự **field thường**, không mặc nhiên buộc thread khác sớm thấy target mới; `syncAll` giúp đồng bộ các call site được liệt kê | Thay đổi ít, muốn chủ động xác nhận hoặc gom cập nhật |
| `VolatileCallSite` | Có | `setTarget` như **volatile write**, `getTarget` như **volatile read**; live invoker dùng target hiện hành | Khi cần thread khác thấy cập nhật qua cơ chế `volatile` mà không gọi `syncAll` |

Không nên hiểu ba lớp này là ba mức "tốc độ" được xếp hạng tuyệt đối. Tính đúng đắn và yêu cầu memory visibility phải được chọn trước, hiệu năng chỉ đánh giá sau. `VolatileCallSite` có thể có chi phí truy cập volatile lớn hơn trong workload liên tục gọi; `MutableCallSite.syncAll` có thể đắt và được thiết kế cho việc đồng bộ/batching. Benchmark thật phụ thuộc JVM/JIT và tần suất đổi target.

### `VolatileCallSite` khác `MutableCallSite` ở chỗ nào?

`MutableCallSite.setTarget(newTarget)` cập nhật như ghi một biến thường. Theo Javadoc, thread khác **có thể tiếp tục dùng target cũ** nếu không có hành động đồng bộ phù hợp. Với `MutableCallSite`, `syncAll(MutableCallSite[] sites)` là một cơ chế làm cho các reader bỏ cached target cũ của những call site đã nêu. Đừng nhầm nó với phép cập nhật target hoặc một giao dịch đóng băng mọi thread: những lời gọi **đã bắt đầu** trên target cũ không bị thu hồi.

`VolatileCallSite` không có `syncAll` riêng: **bản thân mỗi lần `setTarget` là một volatile write**. Theo Javadoc, `getTarget` thực hiện volatile read và phải tuân thủ cập nhật theo mô hình bộ nhớ này. Dùng `MutableCallSite.syncAll` cho một `VolatileCallSite` là sai kiểu API; nó nhận mảng `MutableCallSite[]` chứ không nhận `VolatileCallSite[]`.

## 3. Những API cốt lõi và hợp đồng kiểu

### 3.1 Khởi tạo call site

Hai constructor phổ biến:

```java
// Có target ngay từ đầu:
VolatileCallSite readySite = new VolatileCallSite(initialHandle);

// Chưa cung cấp hành vi nghiệp vụ:
VolatileCallSite blankSite = new VolatileCallSite(
        MethodType.methodType(String.class, String.class));
```

Đây là **snippet minh họa** trong ngữ cảnh đã có `initialHandle` và import cần thiết. Với constructor nhận `MethodHandle`, kiểu của site lấy từ `initialHandle.type()` và handle đó là target ban đầu. Với constructor nhận `MethodType`, site có **target mặc định cùng kiểu nhưng ném `IllegalStateException` nếu bị gọi**, cho tới khi bạn thiết lập target thực tế.

Cả hai constructor đều từ chối `null`. Vì thế đừng xuất bản một `dynamicInvoker` cho consumer rồi quên `setTarget` nếu dùng constructor nhận `MethodType`: consumer có thể gặp `IllegalStateException` vì site chưa khởi tạo.

### 3.2 `type()` không thay đổi khi relink

`CallSite.type()` luôn trả về **một `MethodType` cố định**. Ví dụ:

```text
(String)String
```

Một lần gọi `setTarget` chỉ hợp lệ nếu `newTarget.type().equals(site.type())`. Lớp `VolatileCallSite` **không** tự overload resolution, boxing hoặc `asType` để ép handle có chữ ký khác. Nếu target mới kiểu `(Object)Object` hoặc `()int` thì không thể thay target kiểu `(String)String` bằng lệnh `setTarget` trực tiếp. Lúc đó `WrongMethodTypeException` được ném ngay khi cập nhật và target cũ vẫn còn.

Có thể chủ động thích nghi một handle qua `asType` theo những quy tắc chuyển đổi hợp lệ **trước** khi truyền nó vào `setTarget`:

```java
MethodHandle adapted = someHandle.asType(site.type());
site.setTarget(adapted);
```

Đoạn trên là **snippet** chứ không phải chương trình độc lập. `asType` chỉ hỗ trợ những chuyển đổi nó định nghĩa và có thể ném `WrongMethodTypeException`; không biến một method bất kỳ thành chữ ký bất kỳ. Khi thiết kế runtime router, nên xác nhận `type()` từ đầu và tạo tất cả version với cùng hợp đồng.

### 3.3 `setTarget`, `getTarget`, `dynamicInvoker`

| Thao tác | Hiệu ứng | Đặc trưng |
| --- | --- | --- |
| `site.setTarget(h2)` | Cài `h2` làm target mới | **Volatile write**; đòi cùng MethodType; `null` → `NullPointerException` |
| `site.getTarget()` | Lấy target tại thời điểm đọc | **Volatile read**; handle nhận được là một **snapshot reference** |
| `site.dynamicInvoker()` | Tạo một MethodHandle dispatch qua call site | **Live invoker**: lời gọi tiếp theo dùng target hiện hành, không cố định theo lúc lấy invoker |
| `site.type()` | Lấy chữ ký cố định | Không thay đổi trong suốt vòng đời call site |

**Một phân biệt quan trọng:**

```java
MethodHandle live = site.dynamicInvoker();
MethodHandle captured = site.getTarget();

site.setTarget(newHandle);
```

Đây là snippet với `site` đã được khởi tạo. `live` vẫn trỏ **đến call site** về mặt hành vi, nên lời gọi tiếp theo sẽ đi theo target hiện hành. Ngược lại, `captured` giữ **chính reference của một target handle đã đọc ra**; `captured.invokeExact(...)` không tự tìm target mới sau `setTarget`. Không nhầm `getTarget()` là cách tạo một live invoker.

## 4. `VolatileCallSite` và Java Memory Model

### 4.1 Ngữ nghĩa `volatile` của một lần công bố

Xét hai thread cùng thấy **một object `VolatileCallSite`**:

- Writer chuẩn bị dữ liệu, tạo target mới, rồi gọi `site.setTarget(newTarget)`.
- Reader gọi `site.getTarget()` hoặc `site.dynamicInvoker()`, trong đó việc lấy target có ngữ nghĩa volatile read.

Về bộ nhớ, `setTarget` hoạt động như **ghi vào biến volatile**, và `getTarget` hoạt động như **đọc biến volatile ấy**. Theo JMM, volatile write đến biến đó **synchronizes-with** các volatile read tiếp theo của cùng biến trong synchronization order; quan hệ program order và synchronizes-with kết hợp tạo quan hệ **happens-before**.

Điều này cho phép **công bố dữ liệu đã được chuẩn bị trước khi đổi target**:

```text
writer thread                               reader thread
-------------                               -------------
payload = "published";  [normal write]
             |
             v
site.setTarget(V2);     [volatile write]
                      -- synchronizes-with -->
                                           site.getTarget(); [volatile read]
                                           // quan sát V2
                                                     |
                                                     v
                                             read payload
                                             // thấy dữ liệu đã công bố
```

Giả sử reader nhận biết đã đọc đúng target `V2` do writer công bố, và không có writer khác gây thay đổi chồng chéo, các thao tác ghi trước `setTarget(V2)` được bảo vệ bởi quan hệ happens-before đối với thao tác đọc sau volatile read. Đây là cơ sở để công bố một cấu hình/target mới đã được chuẩn bị hoàn chỉnh.

**Cực kỳ quan trọng:** Bảo đảm này **không tự biến mọi field ở nơi khác thành volatile** hoặc làm mọi code của ứng dụng thread-safe. Nó công bố những trạng thái đã được ghi **trước** release/volatile write, tới reader quan sát qua acquire/volatile read tương ứng. Nếu bạn **tiếp tục thay đổi** một object mutable sau khi công bố mà không có đồng bộ khác, vẫn có thể xảy ra data race. Nên dùng cấu hình immutable, snapshot hoặc các cơ chế concurrency đúng cho state bên trong target.

### 4.2 Lựa chọn target là một điểm quyết định nguyên tử

Một call site giữ **một reference `MethodHandle`**. `setTarget` đổi reference theo volatile semantics; reader sẽ dùng một target cụ thể cho **một lần dispatch**. Nếu có hai version `V1` và `V2`, lời gọi cạnh thời điểm cập nhật có thể hợp lệ đi qua version cũ **hoặc** mới, tùy thứ tự đọc target và đổi target.

Hãy phân biệt:

- **Không "nửa target":** Một lần đọc không nhận một reference bị rách; target luôn là một `MethodHandle` hợp lệ nếu được thiết lập hợp lệ.
- **Không "tua lại" lời gọi cũ:** Nếu lời gọi đã chọn `V1` trước `setTarget(V2)`, nó có thể tiếp tục chạy hoặc hoàn thành dưới `V1` ngay cả sau khi writer đã công bố `V2`.
- **Không có cutover wall-clock tuyệt đối:** Quan hệ volatile được diễn đạt qua synchronization order, không phải đảm bảo mọi thread đang thực thi đồng thời lập tức dừng tại cùng một nanosecond.
- **Không có transaction đa call site:** Hai `VolatileCallSite` độc lập được setTarget lần lượt là hai volatile writes khác nhau; reader có thể thấy một site mới và site kia cũ.

Nếu yêu cầu một **chuyển đổi nghiệp vụ hoàn toàn nhất quán** giữa nhiều target hoặc nhiều tài nguyên, cần thiết kế thêm versioning, immutable configuration snapshot, coordination hoặc transaction ở tầng ứng dụng.

### 4.3 `dynamicInvoker` đọc target hiện hành như thế nào?

Theo hợp đồng `CallSite.dynamicInvoker()`, handle tạo ra tương đương ý tưởng:

```text
getTarget = callSite.getTarget()
return invokeExact(getTarget, arguments...)
```

Đây là **pseudocode**, không phải Java đầy đủ. Với `VolatileCallSite`, việc lấy target dùng volatile semantics. Vì thế **cache chính object `dynamicInvoker` là đúng**; adapter đó luôn trỏ về call site. Ngược lại, **cache kết quả `getTarget()` rồi gọi thẳng handle đó** là cố định version theo lúc đọc.

Bộ biên dịch JIT có thể tối ưu phần triển khai miễn sao **vẫn bảo toàn ngữ nghĩa quan sát** của volatile call site; chương trình không được dựa vào giả định JIT luôn thực hiện một kiểu memory instruction cụ thể hoặc target phải được giải qua một lần truy cập Java rõ ràng trong source.

## 5. Demo Java 17 hoàn chỉnh: cập nhật target và công bố xuyên thread

Tạo file **`VolatilePublicationDemo.java`** với nội dung sau. Chương trình có một luồng demo đơn giản trong `main` và một luồng reader kiểm chứng quan hệ công bố. Ví dụ chạy với **Java 17** và không cần dependency ngoài JDK.

```java
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VolatileCallSite;
import java.lang.invoke.WrongMethodTypeException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class VolatilePublicationDemo {
    static String payload;

    public static String first(String key) { return "first:" + key; }
    public static String second(String key) { return "second:" + key; }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType signature = MethodType.methodType(String.class, String.class);
        MethodHandle h1 = lookup.findStatic(VolatilePublicationDemo.class, "first", signature);
        MethodHandle h2 = lookup.findStatic(VolatilePublicationDemo.class, "second", signature);

        VolatileCallSite site = new VolatileCallSite(signature);
        MethodHandle live = site.dynamicInvoker();
        System.out.println("site.type=" + site.type());

        try {
            String ignored = (String) live.invokeExact("A");
        } catch (IllegalStateException expected) {
            System.out.println("uninitialized=IllegalStateException");
        }

        site.setTarget(h1);
        MethodHandle snapshot = site.getTarget();
        System.out.println("before=" + (String) live.invokeExact("A"));
        site.setTarget(h2);
        System.out.println("after=" + (String) live.invokeExact("A"));
        System.out.println("snapshot=" + (String) snapshot.invokeExact("A"));
        System.out.println("getTarget.isH2=" + (site.getTarget() == h2));

        try {
            site.setTarget(MethodHandles.constant(int.class, 7));
        } catch (WrongMethodTypeException expected) {
            System.out.println("badTarget=WrongMethodTypeException");
        }
        System.out.println("afterBadTarget=" + (String) live.invokeExact("A"));

        VolatileCallSite shared = new VolatileCallSite(h1);
        MethodHandle sharedInvoker = shared.dynamicInvoker();
        CountDownLatch readerStarted = new CountDownLatch(1);
        AtomicReference<String> observed = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread reader = new Thread(() -> {
            readerStarted.countDown();
            try {
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
                while (shared.getTarget() != h2) {
                    if (System.nanoTime() > deadline) {
                        throw new IllegalStateException("deadline exceeded");
                    }
                    Thread.onSpinWait();
                }
                observed.set(payload + "|" + (String) sharedInvoker.invokeExact("B"));
            } catch (Throwable t) {
                failure.set(t);
            }
        }, "reader");

        reader.start();
        readerStarted.await();
        payload = "published"; // normal write, before volatile setTarget
        shared.setTarget(h2);  // volatile write, publishes preceding write
        reader.join();
        if (failure.get() != null) throw new AssertionError(failure.get());
        System.out.println("reader=" + observed.get());
    }
}
```

Biên dịch và chạy từ thư mục chứa file trên:

```bash
javac --release 17 -encoding UTF-8 VolatilePublicationDemo.java
java VolatilePublicationDemo
```

**Stdout của chương trình khi chạy thành công:**

```text
site.type=(String)String
uninitialized=IllegalStateException
before=first:A
after=second:A
snapshot=first:A
getTarget.isH2=true
badTarget=WrongMethodTypeException
afterBadTarget=second:A
reader=published|second:B
```

Nếu môi trường thực thi bị dừng/đóng băng quá lâu khiến reader chạm deadline 5 giây trước khi thấy bản cập nhật, chương trình sẽ ném `AssertionError` chứa nguyên nhân; đây là **cơ chế phát hiện test bị treo**, không phải bằng chứng rằng JMM cam kết cập nhật phải hoàn tất trong 5 giây. Với một JVM được lên lịch bình thường, chương trình cho kết quả trên. Tránh thiết kế nghiệp vụ bắt buộc mọi thread phải chạy trong một khoảng thời gian wall-clock cứng chỉ vì `volatile` tồn tại.

### Giải thích từng dòng stdout

| Dòng output | Ý nghĩa |
| --- | --- |
| `site.type=(String)String` | Call site có một chữ ký cố định của target. |
| `uninitialized=IllegalStateException` | Constructor nhận `MethodType` cài một target tạm ném lỗi cho đến khi `setTarget`. |
| `before=first:A` | `dynamicInvoker` dispatch tới handle `first` đã cài. |
| `after=second:A` | Sau `setTarget(h2)`, cùng object `live` gọi target mới. |
| `snapshot=first:A` | Handle lấy từ `getTarget()` trước update vẫn gọi version cũ; không live-linked tới site. |
| `getTarget.isH2=true` | Một lần volatile read trả về đúng reference `h2`. |
| `badTarget=WrongMethodTypeException` | Handle `()int` không có cùng type với site `(String)String`. |
| `afterBadTarget=second:A` | Update bị từ chối không thay target đang hợp lệ. |
| `reader=published\|second:B` | Reader quan sát `h2` qua `getTarget`, thấy `payload` đã công bố trước đó, rồi live-invoke `second`. |

### Vì sao ví dụ thứ hai thực sự kiểm tra ý tưởng công bố?

Trong thread chính:

```java
payload = "published"; // field thường, không volatile
shared.setTarget(h2);  // volatile write
```

Trong thread đọc:

```java
while (shared.getTarget() != h2) {
    Thread.onSpinWait();
}
String value = payload;
```

Hai đoạn ở trên là **snippets trích từ chương trình hoàn chỉnh**, không phải ứng dụng độc lập. Khi volatile read từ `getTarget()` quan sát reference `h2` đã được writer ghi, giá trị `payload` được writer gán **trước `setTarget(h2)`** được công bố theo happens-before. Bởi vậy reader có quyền dựa vào giá trị đã công bố khi đọc `payload` sau vòng lặp.

`CountDownLatch readerStarted` chỉ được dùng để **bảo đảm reader đã bắt đầu** trước khi writer thực hiện update; nó **không được dùng như một tín hiệu sau khi publish** để thay thế minh chứng về volatile read. `AtomicReference` dùng để đưa kết quả/exception về main một cách an toàn; `Thread.join()` giúp main đợi kết thúc và in kết quả. `Thread.onSpinWait()` chỉ là gợi ý tối ưu chờ chủ động, **không** phải thao tác đồng bộ/happens-before.

**Quan trọng về thực hành:** Vòng spin ở đây nhằm làm rõ ngữ nghĩa API; trong sản phẩm thực tế, không nên polling vô hạn để đợi một `MethodHandle` đổi. Hãy dùng event, queue, latch, signal hoặc các cơ chế điều phối thích hợp; `VolatileCallSite` bảo đảm tính nhìn thấy target, không thay thế cơ chế scheduling/liveness.

## 6. `getTarget` snapshot khác `dynamicInvoker` live handle

Đây là bẫy quan trọng nhất khi thiết kế hot-swap.

```text
              lúc t0                          lúc t1
             -------                        -------
callSite.target = H1          ->        callSite.target = H2
                  |                                |
                  + getTarget()                    + setTarget(H2)
                       |
                 snapshot = H1

live = callSite.dynamicInvoker()

snapshot.invokeExact(...)  -> H1, H1, H1, ... (không tự refresh)
live.invokeExact(...)      -> H1 tại t0; H2 sau khi update được quan sát
```

Một `MethodHandle` lấy từ `getTarget` không trở thành "volatile method handle" có khả năng tự đổi chức năng: volatile semantics nằm ở **hành động đọc reference từ call site**, không dính vào đối tượng `MethodHandle` đã lấy.

Có hai lựa chọn có chủ đích:

1. **Live dispatch:** Tạo `MethodHandle invoker = site.dynamicInvoker()` một lần, dùng lại cho các lời gọi. Nếu site đổi target, invoker dùng target hiện hành theo ngữ nghĩa call site.
2. **Snapshot dispatch:** Lấy `MethodHandle current = site.getTarget()` và thực thi trực tiếp trên `current`. Mọi lệnh gọi bằng reference đó theo target đã chọn, cho đến khi code chủ động đọc lại `getTarget()`.

Snapshot có thể hữu ích khi một thao tác nghiệp vụ **cần giữ cùng một version qua nhiều lời gọi**, nhưng **không tự đảm bảo an toàn lifecycle** của version đó. Nếu version cũ cần được giải phóng, phải quản lý resource/in-flight work riêng. Đổi target không tự hủy method handle cũ đang bị giữ trong cache hoặc stack của thread khác.

### Không nhầm direct `invokeExact` với reflection `Method.invoke`

`MethodHandle.invokeExact` yêu cầu kiểu của call site khớp đúng `MethodType` của handle. Với target `(String)String`, code trong demo dùng:

```java
String answer = (String) live.invokeExact("A");
```

Nếu cố gọi với kiểu tham số/return không đúng, JVM có thể ném `WrongMethodTypeException` ở thời điểm invoke, dù target có tồn tại và `setTarget` đã hợp lệ. Đây là lỗi **khác** với `setTarget` nhận handle sai `MethodType`. `MethodHandle` cũng không tự bọc exception từ target thành `InvocationTargetException` như `java.lang.reflect.Method.invoke`.

## 7. Thiết kế cutover: bảo đảm gì và không bảo đảm gì?

| Câu hỏi | Kết luận chính xác |
| --- | --- |
| Writer cài `H2` thành công, các reader có cần `syncAll` để nhận update không? | **Không.** `VolatileCallSite` dùng volatile semantics ngay tại `setTarget/getTarget`. |
| Một lời gọi đã chọn `H1` có bị dừng hay đổi sang `H2` giữa chừng không? | **Không mặc nhiên.** Lời gọi đã đi vào `H1` có thể tiếp tục chạy trên `H1`. |
| Một lần đọc target có thể nhận "nửa reference H1, nửa H2" không? | **Không.** Target reference được đọc/ghi nguyên tử theo ngữ nghĩa volatile. |
| `setTarget(H2)` có thay tất cả object `MethodHandle` do `getTarget` đã trả trước đó không? | **Không.** Các snapshot reference còn trỏ đến version đã nhận. |
| Cài `H2` có tự làm trạng thái mutable nội bộ `H2` thread-safe không? | **Không.** Cần safe publication và đồng bộ cho các mutation sau khi publish. |
| Thay hai `VolatileCallSite` kế tiếp có là transaction nguyên tử không? | **Không.** Từng site có target riêng; reader có thể nhìn thấy tổ hợp version khác nhau. |
| Hai writer cùng `setTarget` có tự resolve xung đột theo version/business priority không? | **Không.** Các writes được sắp xếp trong synchronization order nhưng ứng dụng phải quản lý thứ tự cập nhật. |
| `VolatileCallSite` có đảm bảo mọi thread được CPU lên lịch trong X mili giây không? | **Không.** Đó là vấn đề scheduling, không phải quy tắc memory visibility. |
| Compiler có thể "đóng băng" live invoker ở target cũ mãi mãi không? | **Không được vi phạm** ngữ nghĩa của volatile call site; tối ưu phải bảo toàn khả năng quan sát update. |

### Cập nhật giữa chừng có thể trộn kết quả từ nhiều version

Giả sử một request gọi cùng dynamic invoker hai lần:

```text
request:
  resultA = live.invokeExact("A")    -> H1
            [writer sets H2]
  resultB = live.invokeExact("B")    -> H2
```

Đây là tình huống hợp lệ. Nếu nghiệp vụ **cần cả hai phép tính trong cùng một phiên bản**, caller nên **lấy snapshot target một lần** (hoặc snapshot object cấu hình duy nhất) và giữ nó xuyên suốt request. Điều này có thể đổi cách quan sát update: request đã bắt đầu có thể tiếp tục dùng version cũ. Thiết kế phải chọn consistency boundary phù hợp, thay vì dựa vào tính volatile cho tất cả trường hợp.

### Concurrent writers và versioning

Nếu có writer A công bố `H2` và writer B công bố `H3` gần như đồng thời, `VolatileCallSite` bảo đảm các thao tác volatile tuân theo thứ tự bộ nhớ, nhưng **không quyết định update nào là hợp lệ về nghiệp vụ**. `setTarget` không phải compare-and-set với expected version.

Ví dụ policy cần cập nhật một chiều từ version 10 → 11 → 12 không nên chỉ dựa vào hai thread gọi `setTarget`. Có thể dùng một thread điều phối cập nhật, lock, CAS trên bản mô tả trạng thái bên ngoài, hoặc version gate riêng, rồi mới công bố handle cuối. Tránh cách hiểu "target mới được ghi sau cùng theo đồng hồ của một thread" luôn có business priority cao nhất.

## 8. Công bố trạng thái đính kèm target một cách an toàn

### Tình huống tốt: target và dữ liệu đã hoàn thiện trước khi xuất bản

Một implementation mới của router có thể gắn kèm immutable config, bảng dispatch hoặc cấu trúc dữ liệu đã khởi tạo:

```text
Writer:
    newConfig = buildImmutableConfig()
    newHandle = createHandleBoundTo(newConfig)
    callSite.setTarget(newHandle)  // volatile publication

Reader:
    callSite.dynamicInvoker().invokeExact(...)
    // target được chọn thấy state đã chuẩn bị trước publication
```

Đây là **pseudocode**, không phải mã Java chạy độc lập. Quan hệ happens-before qua volatile target giúp công bố những write đã diễn ra trước đó. Nếu config immutable và target chỉ đọc cấu hình, việc hiểu/chứng minh tính đúng đắn thường đơn giản hơn.

### Tình huống nguy hiểm: mutate state sau publication

```text
Writer:
    callSite.setTarget(newHandle)
    mutableConfig.put("feature", true)  // ghi sau publication, không được bảo vệ chỉ bởi setTarget

Reader:
    callSite.dynamicInvoker().invokeExact(...)
    // không thể chỉ dựa vào volatile target để bảo đảm thấy mutation này
```

Không dùng việc đổi `MethodHandle` để thay thế mọi đồng bộ của dữ liệu. Nếu target truy cập `HashMap` mutable chia sẻ, nhiều thread cùng sửa mà không có lock/concurrent collection, data race vẫn xảy ra. Đối với nhiều trường hợp, chiến lược tốt nhất là **tạo config immutable hoàn chỉnh rồi công bố một target mới**; các update sau sẽ tạo version khác thay vì sửa version đã xuất bản.

### Memory visibility không đồng nghĩa business invariants

Ngay cả khi mọi reader thấy target mới đúng lúc đọc, hệ thống còn có các hợp đồng khác: tài nguyên của target còn hoạt động không, state cũ có còn request đang dùng không, việc đóng kết nối/giải phóng class loader đã an toàn chưa, policy rollback sẽ phản hồi ra sao? `VolatileCallSite` giải quyết **chọn và công bố reference target**, không quản lý lifecycle của logic nằm sau target.

## 9. `VolatileCallSite` trong kiến trúc `invokedynamic` và runtime adapter

Một `CallSite` có thể được trả bởi **bootstrap method** phục vụ `invokedynamic`, nhưng không bắt buộc phải viết bytecode `invokedynamic` mới dùng được nó. `dynamicInvoker()` chính là API thuận tiện để thử nghiệm và tích hợp trong code Java thông thường.

Một bootstrap method trả về `VolatileCallSite` cho JVM; điểm gọi liên kết đến site đó. Sau này runtime có thể `setTarget` để relink lời gọi. Khi có cập nhật xuyên thread, volatile semantics đảm bảo target mới được nhìn thấy theo JMM. Tuy nhiên bootstrap method phải trả site có `MethodType` chính xác với dynamic call site mà JVM yêu cầu; việc thay target về sau **không** được đổi chữ ký ấy.

**Phân biệt ba lớp hành vi:**

1. **Bootstrap/linkage:** tạo/định nghĩa call site cho một dynamic call site, quản lý tên và kiểu ban đầu.
2. **Relinking:** đổi `target` bằng `setTarget`, giữ nguyên `MethodType`.
3. **Invocation:** `dynamicInvoker`/`invokedynamic` lấy target hiện hành và gọi theo chữ ký; không cần tạo lại proxy hoặc biên dịch lại source Java.

Một JVM có thể biên dịch và tối ưu đường gọi phù hợp, nhưng không được sử dụng các tối ưu làm mất tính quan sát target mới của `VolatileCallSite`. Đây là lý do nên tin **hợp đồng Javadoc/JMM** thay vì phỏng đoán "JIT chắc chắn đã inline H1 nên setTarget không có tác dụng".

## 10. Lựa chọn giữa `VolatileCallSite` và `MutableCallSite`

### Chọn `VolatileCallSite` khi

- Muốn target mới được công bố theo **volatile semantics** cho những reader ở thread khác mà không có `syncAll`.
- Cập nhật tương đối thường xuyên và cần đường cập nhật đơn giản.
- Chấp nhận trade-off volatile synchronization trên đường dispatch, sau khi xác minh bằng benchmark.
- Hệ thống cần một **live selector** với ngữ nghĩa target hiện hành rõ ràng.

### Chọn `MutableCallSite` khi

- Không cần target mới nhất được mỗi reader nhận ngay theo volatile semantics tại từng lần gọi.
- Có thể gom nhiều cập nhật rồi gọi `MutableCallSite.syncAll(...)` để xác nhận sự lan truyền.
- Tần suất cập nhật thấp, đường đọc nóng quan trọng và đã đánh giá được độ trễ/cost của `syncAll`.
- Có một điểm quản lý relink tập trung, quản lý lock/version khi cần.

Snippet minh họa cập nhật `MutableCallSite`, **không phải chương trình độc lập**:

```java
MutableCallSite mutable = new MutableCallSite(initialHandle);
mutable.setTarget(replacementHandle);
MutableCallSite.syncAll(new MutableCallSite[]{mutable});
```

`initialHandle` và `replacementHandle` phải có cùng `MethodType`, và code cần import `java.lang.invoke.MutableCallSite`. `syncAll` không đổi target; nó giúp reader các site được liệt kê bỏ giá trị cũ đã cache theo hợp đồng API. Không thay thế `syncAll` bằng một `Thread.sleep` rồi kết luận mọi thread chắc chắn thấy cập nhật.

### Chọn `ConstantCallSite` khi

Không cần thay target sau khi liên kết. Đây là lựa chọn đơn giản về mặt semantics, không có mutation để công bố. `ConstantCallSite.setTarget` luôn ném `UnsupportedOperationException`. Nếu một hệ thống có hàng triệu lời gọi nhưng **không bao giờ** relink, không có lý do phải gánh khả năng thay target chỉ vì tính linh hoạt nghe hấp dẫn.

## 11. Những lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `IllegalStateException` khi lần đầu invoke | Tạo `new VolatileCallSite(MethodType)` nhưng chưa cài target thực tế | `setTarget` trước khi cho consumer invoke; hoặc dùng constructor nhận target |
| `WrongMethodTypeException` ngay ở `setTarget` | `newTarget.type()` khác `site.type()` | Kiểm tra chính xác return/parameter types; thích nghi hợp lệ trước khi set |
| `NullPointerException` tại `setTarget(null)` | Target bắt buộc là `MethodHandle` không null | Dùng một fallback handle hợp lệ nếu muốn "tắt" chức năng |
| Live invoker đã đổi nhưng code vẫn gọi V1 | Code giữ `site.getTarget()` snapshot thay vì `dynamicInvoker()` | Dùng live invoker hoặc chủ động đọc lại target |
| Update target có hiệu lực nhưng request đang chạy vẫn dùng V1 | Request đã vào V1 trước relink hoặc giữ snapshot V1 | Đây là hành vi hợp lệ; thiết kế cutover theo request/version |
| Một request thấy V1 ở bước đầu, V2 ở bước sau | Hai lần live invocation qua điểm đổi target | Lấy snapshot/version riêng nếu request đòi consistency |
| Data race với cấu hình target | Dữ liệu bị mutate sau `setTarget` hoặc không dùng đồng bộ riêng | Công bố immutable state trước relink; đồng bộ các mutation sau |
| Hai writer ghi trùng nhau gây rollback ngoài ý muốn | `setTarget` không kiểm tra expected version | Dùng coordinator/version gate hoặc serialization cập nhật |
| Test chỉ `sleep(100)` rồi đọc kết quả | Thời gian ngủ không tạo bằng chứng happens-before cho mọi logic | Dùng latch/queue, volatile read rõ ràng và xác minh thứ tự |
| Chọn `MutableCallSite` nhưng mong thấy update xuyên thread ngay | Field target của Mutable có ngữ nghĩa field thường | `syncAll` hoặc chọn Volatile theo yêu cầu visibility |
| Thử gọi `MutableCallSite.syncAll` cho Volatile | Sai class và không cần thiết | Dùng `VolatileCallSite.setTarget` trực tiếp |
| Target mới được chuẩn bị bằng code không thread-safe | Volatile target không sửa race nội bộ target | Bảo vệ state, ưu tiên immutable/safe publication |
| `invokeExact` ném `WrongMethodTypeException` dù setTarget thành công | Kiểu tĩnh của lời gọi không khớp `site.type()` | Đối chiếu MethodType và cast kết quả đúng |
| Gọi target cũ trong cache sau khi relink | Cache giữ direct handle | Nếu cần hot dispatch, cache `dynamicInvoker` thay vì snapshot |

### Cạm bẫy: kiểm tra `getTarget() == h2` chỉ là một phần của câu chuyện

Một lần in `true` xác nhận đúng reference `h2` **tại thời điểm read**. Nó **không** chứng minh tất cả thread đã hoàn thành mọi request cũ, không chứng minh các target đang dở không còn chạy, không kiểm tra target đã đảm bảo thread-safety hoặc việc đóng version cũ sẽ an toàn. Đây là lý do runtime có hot reload thường cần thêm **lifecycle protocol**.

## 12. Debug và kiểm thử đúng cấp độ

### 12.1 Kiểm tra kiểu, target và invoker

Trong code đang có `VolatileCallSite site` (snippet, **không độc lập**):

```java
MethodType expectedType = site.type();
MethodHandle current = site.getTarget();
MethodHandle live = site.dynamicInvoker();
System.out.println("site type=" + expectedType);
System.out.println("current target type=" + current.type());
System.out.println("invoker type=" + live.type());
```

Trước khi relink, log `newTarget.type()` và kiểm tra `equals(site.type())`. Nếu có wrapper/adapters, in kiểu **sau** `asType`, `filterArguments` hoặc `filterReturnValue` trước khi `setTarget`. Giữ log không chứa bí mật hoặc dữ liệu người dùng.

### 12.2 Kiểm thử target switching

Kiểm thử một thread cần xác minh ba hành vi khác nhau:

1. Tạo `dynamicInvoker` một lần khi H1 đang có hiệu lực; lời gọi trả kết quả H1.
2. Cài H2; dùng **cùng invoker**; lời gọi trả kết quả H2.
3. Target snapshot lấy trước relink vẫn trả kết quả H1.

Ví dụ mục 5 hiện thực đầy đủ ba trường hợp đó. Không nên chỉ gọi `site.getTarget().invokeExact(...)` trước và sau update rồi kết luận `dynamicInvoker` có tác dụng, bởi các lời gọi như vậy đang lấy snapshot mới mỗi lần và chưa chứng minh invoker cũ cập nhật động.

### 12.3 Kiểm thử memory publication

Tạo reader và writer thành **hai thread**, để writer ghi dữ liệu thường trước `setTarget(H2)`, reader đợi **qua volatile getTarget** cho đến khi thấy H2 rồi đọc dữ liệu. Không dùng một sự kiện đồng bộ **sau publication** để vô tình làm test pass vì latch thay vì vì volatile call site.

Trong demo, latch chỉ chứng minh reader bắt đầu trước writer cập nhật; vòng lặp `getTarget()` thực sự quan sát target mới. Việc reader đọc `payload` được đặt **sau** volatile read thành công, nên đây là một minh họa thực hành về quan hệ happens-before.

Lưu ý: Một lần test pass **không thể là chứng minh hình thức cho mọi scheduling và mọi JIT**, nhưng kết hợp test với Javadoc/JMM là cách xác thực hợp đồng. Đối với kiểm tra đồng thời nghiêm túc, nên có stress tests, test isolation, timeout hợp lý, và phân tích các khả năng interleaving chứ không dựa vào một lần chạy.

### 12.4 Khi có nhiều cập nhật

Dùng identifier/version rõ ràng cho mỗi `MethodHandle`. Nếu cần nguyên tắc "chỉ version mới hơn được cài", đừng dùng `setTarget` như một CAS đơn giản. Khi có rollback, xác định yêu cầu về request cũ, tài nguyên/cấu hình cũ, transaction, và cách theo dõi in-flight invocations. Một call site chỉ bảo đảm semantics của **target reference**, không thay thế **application-level governance**.

## 13. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** `VolatileCallSite.setTarget(newTarget)` tương đương với loại thao tác bộ nhớ nào?

**Đáp án:** Volatile write vào biến target của call site, có semantics phù hợp với JMM. `getTarget` là volatile read tương ứng.

**Câu 2.** Vì sao `VolatileCallSite` không cần `MutableCallSite.syncAll`?

**Đáp án:** Bởi mỗi `setTarget`/`getTarget` có volatile semantics, việc công bố giữa thread được đảm bảo bởi các thao tác volatile tương ứng. `syncAll` là API của `MutableCallSite` để xử lý target field có semantics thường.

**Câu 3.** Một caller giữ `MethodHandle saved = site.getTarget()`, sau đó thread khác cài target mới. `saved.invokeExact` tự chạy version mới không?

**Đáp án:** Không. `saved` là snapshot reference đến handle đã đọc. Hãy dùng `site.dynamicInvoker()` nếu muốn lời gọi theo target hiện hành.

**Câu 4.** Site có `type() = (String)String`. Gọi `setTarget` với handle `(String)Object` có hợp lệ nếu Object có thể chứa String không?

**Đáp án:** Không. `MethodType` phải khớp **chính xác**, gồm cả return type; `setTarget` sẽ ném `WrongMethodTypeException`. Nếu có chuyển đổi `asType` hợp lệ, hãy thích nghi handle trước khi cài.

**Câu 5.** Nếu một thread đã vào H1 trước khi site đổi sang H2, call H1 có bị hủy không?

**Đáp án:** Không. Update không đảo ngược hoặc tự dừng lời gọi đã bắt đầu. Các lời gọi mới chọn target theo thứ tự volatile read và updates.

**Câu 6.** Writer chuẩn bị immutable config, tạo handle trỏ đến config rồi `setTarget`. Reader thấy handle mới qua `getTarget`. Có thể dựa vào dữ liệu đã ghi trước setTarget không?

**Đáp án:** Có, với các điều kiện về quan hệ happens-before: write thường trước volatile write được công bố đến các read tiếp theo sau volatile read tương ứng. Không suy ra các mutation **sau publication** cũng tự được bảo vệ.

**Câu 7.** Cài target H2 vào hai `VolatileCallSite` liên tiếp có bảo đảm một reader chỉ thấy cả hai cũ hoặc cả hai mới không?

**Đáp án:** Không. Đây là hai volatile locations khác nhau, không phải một transaction. Cần công bố một snapshot điều phối chung nếu muốn trạng thái nhiều thành phần chuyển đồng bộ như một đơn vị nghiệp vụ.

**Câu 8.** Có thể dùng vòng `while (!updated) Thread.sleep(10)` để thay `VolatileCallSite.getTarget` và tuyên bố đã kiểm chứng semantics không?

**Đáp án:** Không. `sleep` không phải bằng chứng quan hệ happens-before của target. Phải quan sát đúng biến/đối tượng đồng bộ liên quan hoặc dùng quy tắc Java Memory Model thích hợp.

**Câu 9.** `new VolatileCallSite(MethodType)` ban đầu được invoke trước khi `setTarget` thì xảy ra gì?

**Đáp án:** Target mặc định có đúng MethodType nhưng ném `IllegalStateException` khi được gọi. Nên cài target hợp lệ trước khi công bố invoker cho code sử dụng.

**Câu 10.** Nếu target mới được cài nhưng caller vẫn thấy kết quả cũ từ một `MethodHandle` đã cache, nguyên nhân cần xem đầu tiên là gì?

**Đáp án:** Kiểm tra caller cache **`site.getTarget()`** (direct snapshot) hay **`site.dynamicInvoker()`** (live invoker). Sau đó xem liệu lời gọi đã bắt đầu trước relink và có đồng bộ/lifecycle nào khác không.

**Câu 11.** `setTarget` có thay thế được CAS và tự sắp xếp version updates giữa nhiều writers không?

**Đáp án:** Không. Nó là volatile write của target reference; ứng dụng cần coordinator, lock, version checking hoặc cơ chế atomic state khác để đáp ứng thứ tự nghiệp vụ.

**Câu 12.** Chỉ vì `VolatileCallSite` nhìn thấy handle mới thì mọi object mutable nằm bên trong handle sẽ thread-safe?

**Đáp án:** Không. Safe publication bảo vệ state được chuẩn bị trước công bố; mutation sau đó cần đồng bộ riêng. Ưu tiên immutable snapshot khi phù hợp.

**Câu 13.** `MutableCallSite.syncAll` có tự khởi động lại request đã bắt đầu dùng target cũ không?

**Đáp án:** Không. `syncAll` nhằm đồng bộ sự nhìn thấy target mới; nó không đảo ngược các lời gọi đang chạy dưới target cũ. Tương tự, `VolatileCallSite` cũng không phải stop-the-world.

**Câu 14.** Chi phí của `VolatileCallSite` có luôn thấp hơn `MutableCallSite` không?

**Đáp án:** Không có kết luận cố định. Volatile semantics có thể tăng chi phí trên đường đọc; `syncAll` cũng có chi phí khi cần đồng bộ. Chọn theo hợp đồng visibility trước, sau đó benchmark với khối lượng/tần suất update thực tế.

## 14. Tóm tắt

- **`VolatileCallSite` là call site có target mang ngữ nghĩa `volatile`.** `setTarget` là volatile write, `getTarget` là volatile read.
- **`dynamicInvoker` là live dispatcher.** Có thể cache invoker nhưng vẫn nhận target mới; `getTarget` trả một target snapshot tại lần đọc.
- **`MethodType` không đổi.** `setTarget` đòi handle cùng kiểu, `null` bị từ chối, mismatch gây `WrongMethodTypeException`.
- **Công bố dữ liệu:** write thường trước `setTarget(H2)` có thể được reader nhìn thấy sau volatile read quan sát H2, theo happens-before.
- **Không có stop-the-world:** lời gọi đã dùng H1 có thể tiếp tục; nhiều calls trong cùng request có thể qua hai versions nếu target đổi giữa chừng.
- **Không có transaction nhiều call sites hay quản lý version tự động.** Cần chiến lược ứng dụng riêng khi cập nhật đồng thời hoặc cần consistency xuyên request.
- **Khác `MutableCallSite`:** Mutable có semantics field thường và hỗ trợ `syncAll`; Volatile không cần `syncAll` vì write/read đã đồng bộ theo volatile rules.
- **Hiệu năng là trade-off:** volatile read/write có thể tốn thêm chi phí; benchmark và yêu cầu đúng đắn quyết định lựa chọn.

### Tài liệu Java SE 17 chính thức

- [Oracle Javadoc — `VolatileCallSite`: volatile target, `setTarget`, `getTarget`, `dynamicInvoker`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html)
- [Oracle Javadoc — `MutableCallSite`: semantics field thường và `syncAll`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html)
- [Oracle Javadoc — `CallSite`: target/MethodType invariant và liên kết `invokedynamic`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html)
- [JLS Java SE 17 `17.4: Java Memory Model, synchronization order và happens-before](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4)