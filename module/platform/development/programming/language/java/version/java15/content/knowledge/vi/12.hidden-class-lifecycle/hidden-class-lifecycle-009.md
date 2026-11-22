# Kiểm thử khả năng giải phóng hidden class bằng nhiều nguồn quan sát (Java 15+)

> **Chủ đề cha: Vòng đời lớp ẩn.** Java 15 cung cấp `MethodHandles.Lookup.defineHiddenClass()` để định nghĩa *hidden class*. Mặc định, một hidden class **có thể được dỡ (unload) ngay cả khi defining class loader vẫn còn sống**, nếu không còn tham chiếu mạnh giữ class đó. Với tùy chọn `ClassOption.STRONG`, vòng đời dỡ lớp bị ràng buộc với defining loader như lớp thông thường. Tuy nhiên, **“đủ điều kiện để unload” không đồng nghĩa “chắc chắn unload trong thời gian thử nghiệm”**. Bài này xây một phép thử có đối chứng và phối hợp **`WeakReference` + `ReferenceQueue`, log JVM, JFR, và MXBean** để đọc kết quả đúng bản chất.

Các API và công cụ trình bày dưới đây vẫn được hỗ trợ trong Java hiện đại. Mã nguồn dùng Java 17+; phần minh họa được biên dịch với `javac --release 17` và chạy thực tế trên JDK 24.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **class có thể được unload**, **class trở nên unreachable**, **`Class<?>` mirror bị GC**, và **sự kiện class unload thực sự của JVM**.
2. Giải thích khác biệt vòng đời giữa hidden class mặc định và hidden class dùng `ClassOption.STRONG`.
3. Tránh việc phép thử tự giữ hidden class sống bởi `Class<?>`, `Lookup`, `MethodHandle`, instance, cache hoặc biến trên stack.
4. Tạo **ba nhóm đối chứng**: weak không giữ, weak cố ý giữ, và strong hidden class.
5. Quan sát tham chiếu bằng `WeakReference<Class<?>>` và `ReferenceQueue<Class<?>>`, rồi đối chiếu với `-Xlog:class+unload=info`.
6. Bật và đọc sự kiện JFR `jdk.ClassUnload`, biết rằng event này có thể không được bật trong cấu hình ghi mặc định.
7. Đọc `ClassLoadingMXBean.getUnloadedClassCount()` như **tín hiệu tổng hợp**, không nhầm nó với bằng chứng về một class cụ thể.
8. Viết kết luận QA có căn cứ, chấp nhận kết quả `NOT_OBSERVED` khi GC chưa xảy ra, thay vì giả định mọi `System.gc()` đều dẫn tới unload.

## 1. Mô hình vòng đời hidden class cần hiểu trước khi kiểm thử

### 1.1. Hidden class mặc định: quan hệ yếu với defining loader

`MethodHandles.Lookup.defineHiddenClass(bytes, initialize)` định nghĩa một hidden class mới. Theo hợp đồng của API, **mặc định hidden class có thể được unload ngay cả khi defining class loader còn reachable**. Điều này khác lớp Java thông thường: một lớp thường có quan hệ mạnh với defining class loader và thông thường không bị unload riêng khi loader còn sống.

Ví dụ:

~~~java
// Đoạn minh họa nằm trong một phương thức có quyền phù hợp.
MethodHandles.Lookup lookup =
    MethodHandles.lookup().defineHiddenClass(classBytes, false);
Class<?> hiddenType = lookup.lookupClass();

System.out.println(hiddenType.isHidden()); // true
~~~

`Lookup` trả về giữ quan hệ với hidden class. Nếu bạn còn giữ `lookup` hoặc `hiddenType` ở một trường static/cache có vòng đời dài, hidden class vẫn có thể reachable **dù không còn instance nào đang được dùng**.

**Không dùng `Class.forName(hiddenType.getName())` để kiểm tra đã unload chưa.** Hidden class vốn **không discoverable qua binary name**, ngay cả khi còn sống. Thất bại của `Class.forName()` không chứng minh lớp đã unload.

### 1.2. `ClassOption.STRONG`: đối chứng kiểm thử

~~~java
// Đoạn minh họa; classBytes là class-file bytes hợp lệ
// thuộc cùng package với lookup class.
MethodHandles.Lookup lookup =
    MethodHandles.lookup().defineHiddenClass(
        classBytes, false,
        MethodHandles.Lookup.ClassOption.STRONG);
~~~

`STRONG` quy định hidden class có **quan hệ mạnh với defining loader**, tương tự một class thông thường. Khi loader còn reachable, class này không unload riêng chỉ vì ứng dụng bỏ biến `Class<?>`.

Bởi vậy, một phép thử có chất lượng nên giữ defining loader còn sống, rồi so sánh:

| Nhóm | Cách định nghĩa | Root cố ý giữ? | Kỳ vọng về vòng đời |
| --- | --- | --- | --- |
| **W — weak/no pin** | `defineHiddenClass(bytes, false)` | Không | Có **khả năng** được unload khi không còn tham chiếu mạnh |
| **P — weak/pinned** | Giống W | Có: giữ `Lookup` ở biến static | Không được unload chừng nào root còn giữ; sau khi bỏ root thì có thể unload |
| **S — strong** | Thêm `ClassOption.STRONG` | Không giữ `Class<?>` trực tiếp | Không unload riêng khi defining loader vẫn reachable |

Trong mỗi nhóm, `Class<?>` và các đối tượng liên quan phải được tạo bằng một **phương thức helper trả về chỉ dữ liệu quan sát**, không trả về cả `Lookup`/`Class<?>` của W và S. Nếu vô tình giữ các tham chiếu ấy, thí nghiệm sẽ kiểm tra **cache của bạn**, không phải chính sách unloading của JVM.

### 1.3. Điều gì có thể giữ class còn reachable?

Một số đối tượng/vùng nhớ có thể tạo chuỗi tham chiếu mạnh đến hidden class:

- `Class<?>` được lưu trong field static, instance field, map, list hoặc cache.
- `MethodHandles.Lookup` có lookup class là hidden class.
- `MethodHandle`, `VarHandle`, `MethodType` hoặc call site chứa tham chiếu tới hidden class.
- Instance thực của hidden class còn sống; đối tượng đó cần giữ class metadata thích hợp cho hoạt động runtime.
- Stack frame, local variable còn *live*, thread-local hoặc callback vẫn giữ instance/handle/class.
- Một framework cache bytecode-generated type qua key/value có vòng đời dài.
- `ClassOption.STRONG` gắn class với vòng đời của defining loader, ngay cả nếu bạn đã bỏ các biến `Class<?>` trong ứng dụng.

Ngược lại, **chỉ giữ chuỗi runtime name** từ `getName()` không phải là giữ `Class<?>`: tên chỉ là dữ liệu `String`, không bảo đảm có thể tìm lại hidden class. Giữ `byte[]` class-file template cũng không tự giữ **hidden class đã định nghĩa**, dù có thể giữ bộ nhớ heap dành cho bytes.

**Lưu ý:** Đây là mô hình về *reachability*. Đừng kết luận chỉ từ “tôi đã gán một biến bằng `null`”: JIT, method handles, call sites, biến tạm, test framework và các tham chiếu khác đều có thể ảnh hưởng. Thiết kế helper cô lập đối tượng là cần thiết.

## 2. Vì sao phải dùng nhiều nguồn quan sát?

Một quan sát riêng lẻ thường không trả lời đủ câu hỏi “hidden class này đã unload chưa?”:

| Nguồn | Điều có thể nhìn thấy | Điều **không** chứng minh được nếu đứng một mình |
| --- | --- | --- |
| `WeakReference<Class<?>>.get() == null` | `Class` mirror không còn reachable qua strong references tại thời điểm kiểm tra | Không mô tả đầy đủ lịch sử sự kiện unload JVM; GC không có hạn chót |
| `ReferenceQueue.poll()` trả đúng weak reference | GC đã đưa reference tương ứng vào queue | Không có event không đồng nghĩa còn reachable; queue có thể chưa được xử lý/đã bị đọc |
| Unified logging `-Xlog:class+unload=info` | JVM thông báo unload một class, kèm runtime name và thời điểm | Không thấy log có thể do cấu hình, timing hoặc class chưa unload |
| JFR `jdk.ClassUnload` | Sự kiện unload do JVM ghi khi **event được bật và recording chạy** | Không thấy event khi chưa bật hoặc recording không bao phủ thời gian |
| `ClassLoadingMXBean.getUnloadedClassCount()` | Tổng số class unload từ khi JVM khởi động | Không chỉ ra class cụ thể; có thể gồm lớp khác |
| Dump/summary class-loader từ công cụ chẩn đoán | Bối cảnh loader/một số thống kê | Không thay thế bằng chứng cho một hidden class cụ thể |

**Nguyên tắc đối chiếu:** Theo dõi **tên runtime của chính class** (dù suffix do VM sinh), thời gian tạo/GC/unload, trạng thái weak reference và event/log. Không lấy `getUnloadedClassCount()` tăng 1 làm bằng chứng duy nhất rằng *đúng hidden class vừa tạo* đã unload: JVM có thể dỡ nhiều class khác.

### 2.1. “Được phép unload” khác “đã unload”

- `defineHiddenClass(bytes, false)` **không ra lệnh** JVM unload class ngay khi một method kết thúc.
- `System.gc()` chỉ là **đề nghị** GC thực hiện thu gom; JVM có thể bỏ qua hoặc hành xử khác tùy collector và cấu hình.
- Class unloading thường liên quan các GC cycle phù hợp, chính sách collector, áp lực bộ nhớ và các references còn sống.
- Một thời gian chờ hết mà weak reference chưa bị xóa là **chưa quan sát được unload**, không tự động là lỗi của JDK.
- `STRONG` không có nghĩa class tồn tại **vĩnh viễn**: nó gắn với defining loader; khi loader không còn reachable, class vẫn có thể được unload theo quy tắc chung.

Trong CI, test mang tính **smoke/observability** có thể báo `OBSERVED`/`NOT_OBSERVED` thay vì fail khi không có unload trong thời hạn ngắn. Nếu sản phẩm phải bảo đảm giới hạn tài nguyên, cần stress/soak testing với điều kiện và bộ đo xác định hơn.

## 3. Thiết kế một thí nghiệm có đối chứng

Chúng ta tạo **ba hidden classes riêng biệt từ cùng một mẫu `.class`**. Từng lần gọi `defineHiddenClass()` định nghĩa một runtime class khác nhau; vì thế các runtime names nhận suffix khác nhau. Trong chương trình:

1. Đọc class-file bytes của nested class `Template` từ resource do `javac` tạo ra.
2. Gọi `defineHiddenClass()` trong helper để tạo các biến local `Lookup`/`Class<?>`, nhưng trả về **chỉ** runtime name dạng `String`, cờ `isHidden` và `WeakReference<Class<?>>` với `ReferenceQueue`.
3. Với nhóm P, chủ động cất `Lookup` vào `static volatile Object pinnedLookup`; với nhóm W và S, **không** cất reference mạnh.
4. Giữ app class loader sống trong suốt `main`. Điều này tạo đối chứng cho nhóm S.
5. Đề nghị GC một số lần có giới hạn; sau đó đọc trạng thái references và queue.
6. Bỏ `pinnedLookup`, đề nghị GC tiếp, đọc lại.
7. Đọc tổng số class unload từ `ClassLoadingMXBean`.
8. Chạy với unified logging để có bằng chứng **theo tên class**.

### 3.1. Ví dụ hoàn chỉnh — weak, pinned và STRONG

**Tệp:** `src/demo/lifecycle/HiddenUnloadingProbe.java`. Chạy được trên Java 17+, chỉ cần JDK.

~~~java
package demo.lifecycle;

import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodHandles.Lookup.ClassOption;
import java.lang.management.ManagementFactory;
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

public class HiddenUnloadingProbe {
    static class Template {}

    // Root cố ý để chứng minh một Lookup có thể giữ class sống.
    static volatile Object pinnedLookup;

    // Không chứa Class<?>/Lookup/MethodHandle strong reference.
    record Probe(String name, boolean hidden,
                 WeakReference<Class<?>> ref,
                 ReferenceQueue<Class<?>> queue) {}

    static Probe define(byte[] bytes, boolean strong, boolean pin)
            throws IllegalAccessException {
        MethodHandles.Lookup base = MethodHandles.lookup();

        MethodHandles.Lookup lookup = strong
                ? base.defineHiddenClass(
                    bytes, false, ClassOption.STRONG)
                : base.defineHiddenClass(bytes, false);

        Class<?> type = lookup.lookupClass();

        if (pin) {
            pinnedLookup = lookup; // Chỉ nhóm P được giữ mạnh.
        }

        ReferenceQueue<Class<?>> queue = new ReferenceQueue<>();
        return new Probe(
                type.getName(),
                type.isHidden(),
                new WeakReference<>(type, queue),
                queue);
    }

    static void tryGc(int attempts) throws InterruptedException {
        for (int i = 0; i < attempts; i++) {
            System.gc();      // Chỉ là hint, không bảo đảm GC.
            Thread.sleep(50); // Chờ có giới hạn.
        }
    }

    static boolean wasEnqueued(Probe probe) {
        Reference<? extends Class<?>> ref;
        boolean seen = false;
        while ((ref = probe.queue().poll()) != null) {
            if (ref == probe.ref()) {
                seen = true;
            }
        }
        return seen;
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes;
        try (InputStream in = Template.class.getResourceAsStream(
                "HiddenUnloadingProbe$Template.class")) {
            if (in == null) {
                throw new IllegalStateException("Missing class bytes");
            }
            bytes = in.readAllBytes();
        }

        long unloadedBefore = ManagementFactory
                .getClassLoadingMXBean().getUnloadedClassCount();

        Probe weak   = define(bytes, false, false); // Nhóm W
        Probe pinned = define(bytes, false, true);  // Nhóm P
        Probe strong = define(bytes, true, false);  // Nhóm S

        System.out.println("threeHidden="
                + (weak.hidden() && pinned.hidden()
                && strong.hidden()));
        System.out.println("uniqueRuntimeNames="
                + (!weak.name().equals(pinned.name())
                && !weak.name().equals(strong.name())));

        // In tên để đối chiếu với file JVM unload log.
        System.out.println("weakRuntimeName=" + weak.name());
        System.out.println("pinnedRuntimeName=" + pinned.name());
        System.out.println("strongRuntimeName=" + strong.name());

        tryGc(12);

        System.out.println("whilePinned.pinnedAlive="
                + (pinned.ref().get() != null));
        System.out.println("whileLoaderAlive.strongAlive="
                + (strong.ref().get() != null));
        System.out.println("weakClearedObserved="
                + (weak.ref().get() == null));
        System.out.println("weakEnqueuedObserved="
                + wasEnqueued(weak));

        // Gỡ root do chính test tạo ra.
        pinnedLookup = null;

        tryGc(12);

        System.out.println("afterRelease.pinnedClearedObserved="
                + (pinned.ref().get() == null));
        System.out.println("afterRelease.pinnedEnqueuedObserved="
                + wasEnqueued(pinned));
        System.out.println("afterRelease.strongAlive="
                + (strong.ref().get() != null));

        long unloadedAfter = ManagementFactory
                .getClassLoadingMXBean().getUnloadedClassCount();
        System.out.println("aggregateUnloadedDelta="
                + (unloadedAfter - unloadedBefore));
    }
}
~~~

**Biên dịch:** Từ thư mục chứa `src`:

~~~bash
javac --release 17 -encoding UTF-8 -d out \
  src/demo/lifecycle/HiddenUnloadingProbe.java
~~~

Trên Windows PowerShell, hãy dùng một dòng tương đương:

~~~powershell
javac --release 17 -encoding UTF-8 -d out src/demo/lifecycle/HiddenUnloadingProbe.java
~~~

**Chạy kèm log class unloading** (một dòng, JDK 17+):

~~~bash
java -Xlog:class+unload=info:file=class-unload.log:uptime,level,tags -cp out demo.lifecycle.HiddenUnloadingProbe
~~~

`class-unload.log` là tệp được JVM tạo trong thư mục làm việc. Tên file và cú pháp `-Xlog` áp dụng cho HotSpot/OpenJDK hiện đại; nếu JVM khác không hỗ trợ cùng log tags, kiểm tra tài liệu của VM đó thay vì dựa vào một option không được hỗ trợ.

### 3.2. Kết quả của **một lần chạy thực tế** trên JDK 24

Kết quả dưới đây là **mẫu quan sát**, không phải bộ giá trị mọi VM đều phải in giống nhau. Hậu tố `0x...` do VM tự sinh sẽ khác, còn các trạng thái đã quan sát được GC có thể khác theo collector/timing.

~~~text
threeHidden=true
uniqueRuntimeNames=true
weakRuntimeName=demo.lifecycle.HiddenUnloadingProbe$Template/0x00000210fe001800
pinnedRuntimeName=demo.lifecycle.HiddenUnloadingProbe$Template/0x00000210fe001c00
strongRuntimeName=demo.lifecycle.HiddenUnloadingProbe$Template/0x00000210fe002000
whilePinned.pinnedAlive=true
whileLoaderAlive.strongAlive=true
weakClearedObserved=true
weakEnqueuedObserved=true
afterRelease.pinnedClearedObserved=true
afterRelease.pinnedEnqueuedObserved=true
afterRelease.strongAlive=true
aggregateUnloadedDelta=2
~~~

Trong đúng lần chạy đó, JVM log còn xuất hiện:

~~~text
[0.166s][info][class,unload] unloading class demo.lifecycle.HiddenUnloadingProbe$Template/0x00000210fe001800 0x00000210fe001800
[0.810s][info][class,unload] unloading class demo.lifecycle.HiddenUnloadingProbe$Template/0x00000210fe001c00 0x00000210fe001c00
~~~

**Cách đọc:**

- `threeHidden=true` xác nhận cả ba class được định nghĩa là hidden. Đây là mệnh đề ổn định với mẫu class-file hợp lệ.
- `uniqueRuntimeNames=true` cho biết ba runtime classes độc lập; không dùng địa chỉ hậu tố làm ID dài hạn.
- `whilePinned.pinnedAlive=true` cho thấy khi `pinnedLookup` còn giữ `Lookup`, class của nhóm P vẫn reachable.
- `whileLoaderAlive.strongAlive=true` và `afterRelease.strongAlive=true` cho thấy nhóm S chưa được dỡ khi defining loader còn sống. Nó là **đối chứng** về chính sách `STRONG`.
- `weakClearedObserved=true` + `weakEnqueuedObserved=true` là tín hiệu từ Java references: mirror `Class<?>` của W đã được thu gom/đưa vào queue.
- Sau khi bỏ `pinnedLookup`, nhóm P cũng được quan sát bị xóa/queued. Đây là dấu hiệu cho thấy chính root của test từng ngăn P được giải phóng.
- `aggregateUnloadedDelta=2` cho thấy tổng số class unload đã tăng 2 trong cửa sổ quan sát. Con số này **không tự xác nhận** class nào; hai dòng JVM log có **runtime names tương ứng** mới là bằng chứng riêng cho W và P.

**Nếu kết quả khác:** Hoàn toàn có thể thấy `weakClearedObserved=false`, `weakEnqueuedObserved=false`, `afterRelease.pinnedClearedObserved=false` và `aggregateUnloadedDelta=0` trong khoảng thử ngắn. Đó là **chưa quan sát được unload**, cần xem lại điều kiện GC, root còn giữ, log được bật chưa, chứ không tự tuyên bố API sai.

### 3.3. Tại sao helper `define(...)` phải trả về `Probe` thay vì `Class<?>`?

Phép thử sau **không phù hợp** để chứng minh unload khi local vẫn giữ class:

~~~java
// Đoạn minh họa sai mục đích kiểm thử.
Class<?> hidden = lookup.defineHiddenClass(bytes, false).lookupClass();
WeakReference<Class<?>> ref = new WeakReference<>(hidden);
System.gc();
System.out.println(ref.get() == null);
~~~

Biến `hidden` (và `lookup` nếu còn sống) có thể tạo strong root ngay trong stack frame của test. Dù JIT được phép xác định biến đã hết live range, không nên phụ thuộc vào tối ưu hóa cụ thể.

Ở ví dụ chính, helper tạo `Lookup`/`Class<?>` và chỉ trả về:
- **Tên String** để đối chiếu log.
- **Cờ boolean** được tính lúc class còn sống.
- **Weak reference** và queue không làm tăng strong reachability đến referent.

Nhóm P cố ý giữ `Lookup` trong static field; nhóm W/S không giữ. Cấu trúc này giúp phân biệt sự cố root với hành vi unloading.

### 3.4. Vì sao `ReferenceQueue` là nguồn quan sát riêng?

Khi tạo:

~~~java
// Minh họa, đặt trong một method khi đã có Class<?> type.
ReferenceQueue<Class<?>> q = new ReferenceQueue<>();
WeakReference<Class<?>> r = new WeakReference<>(type, q);
~~~

`r.get() == null` là trạng thái referent đã bị clear. `q.poll()` giúp quan sát việc reference được đưa vào queue sau khi GC xử lý. Cần giữ **chính đối tượng `WeakReference`** đủ lâu để đọc trạng thái queue, nhưng không giữ referent `type` trong cache.

**Không đánh đồng**:
- `r.get() == null`: tham chiếu yếu đã bị clear.
- `r.isEnqueued()`: API cũ không cần dùng; đọc queue bằng `poll()`/`remove(timeout)` phù hợp hơn.
- `q.poll() == null`: không có phần tử chờ tại thời điểm poll; không phải chứng minh class vẫn còn sống.

`ReferenceQueue.poll()` lấy phần tử ra khỏi queue. Nếu nhiều thành phần cùng đọc queue, một consumer khác có thể đã lấy mất event. Trong mẫu, một queue riêng cho từng probe và chỉ một nơi đọc giúp kết quả rõ ràng.

### 3.5. Vì sao `ClassLoadingMXBean` chỉ là tín hiệu tổng hợp?

API `ManagementFactory.getClassLoadingMXBean().getUnloadedClassCount()` trả về **tổng số class đã unload** theo báo cáo runtime, không tách theo hidden class W/P/S. Nếu một library, lambda-generated class hay lớp khác unload cùng thời điểm, delta có thể lớn hơn số class mà test tạo.

Dùng nó để:
- Nhìn xu hướng trong một khoảng thời gian/so sánh workload.
- Phát hiện JVM có báo cáo hoạt động class unloading hay không.
- Đối chiếu **ở mức hệ thống** với log/JFR.

Không dùng nó làm điều kiện `assertEquals(2, unloadedDelta)` trong unit test thông thường; dễ flake do runtime và các class khác.

## 4. JVM Unified Logging: bằng chứng trực tiếp theo runtime name

`-Xlog:class+unload=info` là lựa chọn logging hiện hành trên HotSpot/OpenJDK. Không cần dùng các tên flag tracing cũ; chúng không phải lựa chọn được khuyến nghị trong JVM hiện đại.

### 4.1. Chạy với log ra console

~~~bash
java -Xlog:class+unload=info -cp out demo.lifecycle.HiddenUnloadingProbe
~~~

JVM có thể in các dòng gắn nhãn `[class,unload]` bên cạnh stdout của ứng dụng. Khi output dài, dùng log file để tránh nhầm lẫn.

### 4.2. Chạy với file riêng và thời gian

~~~bash
java -Xlog:class+unload=info:file=class-unload.log:uptime,level,tags -cp out demo.lifecycle.HiddenUnloadingProbe
~~~

Một dòng dạng:

~~~text
[0.810s][info][class,unload] unloading class demo.lifecycle.HiddenUnloadingProbe$Template/0x00000210fe001c00 0x00000210fe001c00
~~~

thể hiện VM đã ghi nhận **class unload event** theo runtime name. Nó quan trọng hơn việc chỉ so tổng số class unload.

**Cách đối chiếu đúng:**

1. Ghi ra `weakRuntimeName`, `pinnedRuntimeName`, `strongRuntimeName` **trước** đợt GC.
2. Sau lần chạy, tìm runtime name riêng của W và P trong log.
3. Kiểm tra thời điểm: P nên chưa unload trong giai đoạn root còn giữ, nếu điều kiện chương trình hoạt động như thiết kế; P có thể unload sau khi gỡ root.
4. Với S, khi defining loader còn sống, **không kỳ vọng** thấy class này unload riêng trong phép thử.
5. Không trộn kết quả từ **lần chạy khác**, vì suffix runtime thay đổi.

**Không thấy dòng `class,unload` không phải bằng chứng class vẫn sống** nếu không chắc chắn logging đã bật, VM hỗ trợ tags, có GC phù hợp, và tất cả roots đã được bỏ.

## 5. JFR: nguồn sự kiện unload độc lập với text log

Java Flight Recorder (JFR) cung cấp event `jdk.ClassUnload`. Đây là nguồn có cấu trúc để lưu sự kiện về class được unload, có thể phân tích cùng thời gian và dữ liệu JVM khác. **Không được giả định event này luôn được bật trong cấu hình recording mặc định.** Mã ví dụ dưới đây gọi `Recording.enable("jdk.ClassUnload")` rõ ràng trước khi bắt đầu.

### 5.1. Ví dụ JFR hoàn chỉnh

**Tệp:** `src/demo/lifecycle/HiddenJfrProbe.java`. Cần JDK 17+ với module `jdk.jfr` có sẵn (các bản JDK thông dụng cung cấp module này). Chương trình chạy độc lập, không phụ thuộc `HiddenUnloadingProbe`.

~~~java
package demo.lifecycle;

import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.ref.WeakReference;
import java.nio.file.Path;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;
import jdk.jfr.consumer.RecordedEvent;

public class HiddenJfrProbe {
    static class Template {}

    static WeakReference<Class<?>> create(byte[] bytes) throws Exception {
        Class<?> type = MethodHandles.lookup()
                .defineHiddenClass(bytes, false).lookupClass();
        return new WeakReference<>(type);
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes;
        try (InputStream in = Template.class.getResourceAsStream(
                "HiddenJfrProbe$Template.class")) {
            if (in == null) {
                throw new IllegalStateException("Missing template");
            }
            bytes = in.readAllBytes();
        }

        // Truyền vị trí file .jfr bằng dòng lệnh.
        Path out = Path.of(args[0]);
        boolean reclaimed;

        try (Recording recording = new Recording()) {
            // Phải bật cụ thể event; không dựa vào profile mặc định.
            recording.enable("jdk.ClassUnload");
            recording.start();

            WeakReference<Class<?>> ref = create(bytes);
            for (int i = 0; i < 15 && ref.get() != null; i++) {
                System.gc();
                Thread.sleep(90);
            }

            reclaimed = ref.get() == null;
            Thread.sleep(400);  // Cho phép event được ghi trong cửa sổ.
            recording.stop();
            recording.dump(out);
        }

        long all = 0;
        long matches = 0;
        for (RecordedEvent event : RecordingFile.readAllEvents(out)) {
            if (event.getEventType().getName().equals("jdk.ClassUnload")) {
                all++;
                String name = event.getClass("unloadedClass").getName();

                // Không dựa vào ký tự phân tách suffix của JFR.
                if (name.contains("HiddenJfrProbe$Template")) {
                    matches++;
                }
            }
        }

        System.out.println("referenceClearedObserved=" + reclaimed);
        System.out.println("classUnloadEvents=" + all);
        System.out.println("matchingHiddenEvents=" + matches);
    }
}
~~~

**Biên dịch và chạy:**

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/lifecycle/HiddenJfrProbe.java
java -cp out demo.lifecycle.HiddenJfrProbe hidden-unload.jfr
jfr print --events jdk.ClassUnload hidden-unload.jfr
~~~

Ví dụ stdout đã quan sát khi chạy trên JDK 24:

~~~text
referenceClearedObserved=true
classUnloadEvents=1
matchingHiddenEvents=1
~~~

Đây chỉ là **một lần quan sát**; nếu JVM chưa unload trong khoảng thử hoặc recording không thể ghi sự kiện, số event có thể bằng 0. Phần kiểm tra dạng `contains("HiddenJfrProbe$Template")` dùng để minh họa việc chọn event liên quan; nếu một ứng dụng phát sinh nhiều lớp tên gần giống, cần phối hợp runtime name, defining loader, thời gian và các trường event khác để tránh ghép nhầm.

Một đoạn output từ `jfr print` trên JDK 24 có dạng:

~~~text
jdk.ClassUnload {
  unloadedClass = demo.lifecycle.HiddenJfrProbe$Template.0x0000022477007400 (classLoader = null)
  definingClassLoader = N/A
  eventThread = "VM Thread"
}
~~~

Sự biểu diễn tên của JFR ở ví dụ trên chứa `.0x...`, còn `Class.getName()`/unified log có thể thể hiện `/0x...`. **Không so nguyên văn hai định dạng tên nếu chưa hiểu quy ước hiển thị của từng nguồn**; dùng phần tên nền, suffix và ngữ cảnh thời gian/loader phù hợp.

### 5.2. Cách đọc JFR đúng

- `jdk.ClassUnload` phải được **enabled** trước khi unload xảy ra.
- Recording phải còn hoạt động trong đúng cửa sổ quan sát.
- Event `unloadedClass` chỉ ra class được JVM báo unload, là nguồn đối chiếu ở cấp sự kiện.
- `RecordedEvent.getClass("unloadedClass")` trả thông tin class **được ghi nhận trong recording**, không nạp lại runtime class đã unload vào ứng dụng.
- JFR có thể thêm chi phí quan sát và không buộc JVM GC/unload. Nó là **thiết bị quan sát**, không phải cơ chế ép giải phóng.
- Nếu dùng các tệp cấu hình `.jfc` thay cho `Recording.enable(...)`, kiểm tra cài đặt `jdk.ClassUnload` cụ thể trong profile; không suy đoán từ tên `default` hoặc `profile`.

## 6. Kết hợp các nguồn thành một kết luận có căn cứ

### 6.1. Bảng kết luận khuyến nghị

| Weak reference / queue | Log/JFR `ClassUnload` của đúng runtime class | Kết luận |
| --- | --- | --- |
| Clear + queue nhận đúng ref | Có event/unload log khớp tên và cửa sổ | **Đã quan sát class unload**; các nguồn củng cố nhau |
| Clear hoặc queued | Chưa thấy event | Có bằng chứng về **GC/reachability**, nhưng thiếu xác nhận unload từ JVM; kiểm tra config/timing |
| Chưa clear | Có event khớp tên | **Mâu thuẫn cần điều tra**: nhầm runtime name/lần chạy, reference/loader, ghi log hoặc logic test |
| Chưa clear | Không có event | **Chưa quan sát được unload**; không kết luận API lỗi |
| Nhóm P còn pin, hoặc nhóm S với loader còn sống | Không có event | Đúng kỳ vọng của đối chứng, nhưng vẫn cần kiểm tra test thực sự giữ root/loader |
| Tổng `getUnloadedClassCount()` tăng | Không có thông tin riêng theo class | **Chỉ biết số lượng chung tăng**; không đủ bằng chứng cho class mục tiêu |

`ReferenceQueue` và `WeakReference` thường biến đổi rất gần nhau trong một GC cycle, nhưng đừng coi chúng là hai phép đo hoàn toàn độc lập về nội bộ JVM. Giá trị của việc đối chiếu là nhóm tín hiệu từ **Java reference processing** so với **JVM unload log/JFR event**. MXBean bổ sung số liệu hệ thống.

### 6.2. Một báo cáo thử nghiệm tốt nên ghi gì?

Không nên chỉ báo “PASS vì `System.gc()` xong rồi”. Một báo cáo có thể chứa:

~~~text
JDK: 24 (HotSpot), Java source compatibility: 17
Mode: default weak hidden class
Runtime name: demo.lifecycle.HiddenUnloadingProbe$Template/0x...
Strong root: none by test design
Defining loader: application loader remains reachable
WeakReference cleared: observed
ReferenceQueue enqueue: observed
JVM class+unload log: matching class observed
JFR jdk.ClassUnload: observed in JFR run when enabled
MXBean unloaded count: increased (aggregate only)
Conclusion: class unloading observed in this execution
~~~

Dòng runtime name trong báo cáo là **mẫu biểu diễn**; thay bằng đúng chuỗi máy của bạn in ra, không sử dụng lại hậu tố từ lần chạy khác.

Đối với phép thử chưa ghi nhận unload, kết luận nên là `NOT_OBSERVED_WITHIN_WINDOW`, kèm collector/JDK/flags, thời lượng, root chính, logging/JFR settings và bước điều tra tiếp. Đừng viết `PASS: JVM never unloads hidden class` dựa trên một lần chạy chưa thấy event.

## 7. Xây test ít flaky hơn

### 7.1. Cô lập class được kiểm thử

- Dùng helper `define(...)` để local `Lookup` và `Class<?>` hết phạm vi rồi mới đề nghị GC; không trả về strong reference cho nhóm W/S.
- Nếu có method handle đến constructor/phương thức của hidden class, nó có thể giữ class reachable: phải bỏ handle/cache/call site khi đo khả năng unload.
- Nếu có một instance của hidden class còn sống, đừng mong thấy class đã unload khi instance còn cần đến class.
- Ghi tên vào `String` để đối chiếu log nhưng không lưu `Class<?>` vào map chỉ vì muốn log.
- Thận trọng với `ThreadLocal`, worker thread đang chạy, callback, lambda cache và static field trong test harness.

### 7.2. Có đối chứng dương và âm

**Đối chứng chống thu gom (P):** Giữ `Lookup` trong `static volatile Object pinnedLookup`. Khi root còn giữ, weak ref tới hidden class đó vẫn nên quan sát là alive; sau khi gỡ root, nó có thể được clear.

**Đối chứng STRONG (S):** Thêm `ClassOption.STRONG`. Khi app loader còn reachable, không mong class này unload riêng. Nhóm này phân biệt chính sách **STRONG** với mặc định, không phải phép đo “class unload nhanh hơn”.

**Nhóm cần kiểm thử (W):** Không giữ root mạnh theo thiết kế. Nếu JVM thấy class unreachable và thực hiện GC/unload phù hợp, bạn có thể ghi nhận weak ref clear và sự kiện class unload.

Nếu P đã bị clear **trước** khi gỡ root, phải điều tra logic test: có thật đang giữ đúng `Lookup` không, có đang so đúng weak reference không, có ghi nhận log giữa các run nhầm lẫn không?

### 7.3. Bounded wait và GC là gợi ý, không phải contract

Chương trình sử dụng 12 lần `System.gc()` và mỗi lần ngủ 50 ms để tạo **cửa sổ đo có giới hạn**. Đây là kỹ thuật thí nghiệm, **không phải yêu cầu sản phẩm và không bảo đảm unload**.

Trong môi trường có `-XX:+DisableExplicitGC`, lời gọi `System.gc()` có thể không làm điều bạn nghĩ; một số collector/cấu hình xử lý full GC hoặc class unloading khác nhau. Không viết test unit bắt buộc `weakClearedObserved=true` trên mọi máy/CI, vì nó có thể flaky.

Nếu cần nghiên cứu sâu:
- Chạy workload đủ dài trên một JVM riêng để giảm nhiễu.
- Sử dụng collector và JVM flags đã ghi lại, không thay đổi giữa các nhóm so sánh.
- Giữ cùng phiên bản runtime/JDK khi đo hồi quy.
- Phân biệt **heap** dùng cho object/bytes/weak refs với **native/metaspace** và class metadata.
- Dùng số liệu theo xu hướng trong nhiều lần và log/JFR để kiểm tra việc unload có thật.
- Đặt tiêu chí pass/fail theo *mức tài nguyên ổn định của workload* và *không còn reference giữ class* thay vì kỳ vọng thời điểm GC cố định.

### 7.4. Thay đổi lớp được tạo có thể làm sai thí nghiệm

- `defineHiddenClass()` yêu cầu lookup có full privilege access; class-file bytes phải mô tả class cùng package của lookup class.
- Mỗi lần define tạo **runtime class mới**, ngay cả khi bytes giống hệt nhau.
- Định nghĩa thêm một class **có tên thường** bằng loader mới rồi bỏ loader là thí nghiệm về **class-loader unloading**, không cùng giả thuyết với weak hidden class khi defining loader vẫn sống.
- Thêm `ClassOption.STRONG` đổi chính sách unload; đừng dùng trong nhóm W.
- Thêm `NESTMATE` liên quan quyền truy cập nest; không phải cách buộc hidden class unload.
- Thay đổi việc khởi tạo (`initialize=true/false`) có thể ảnh hưởng timing, static state và reachability, nhưng không đổi bản chất mặc định-vs-STRONG. Khi so sánh, giữ cấu hình nhất quán.

## 8. Những lỗi thường gặp

### Lỗi 1 — Cho rằng `Class.forName(hidden.getName())` ném lỗi nghĩa là class đã bị unload

Không đúng. Hidden class vốn không thể tra cứu theo binary name thông thường ngay khi đang sống. Kiểm tra lifecycle phải dùng reference processing và sự kiện unload.

### Lỗi 2 — Giữ `Lookup` hoặc `MethodHandle` rồi chờ class unload

Các đối tượng này có thể giữ class reachable. Đặt quá trình tạo trong helper, xóa/cắt các roots không cần thiết, tránh các static cache giữ lâu.

### Lỗi 3 — Dùng `STRONG` mà vẫn mong class unload trong khi application loader còn sống

`ClassOption.STRONG` ràng buộc class với defining loader. Đây là đối chứng về vòng đời, không phải chế độ thử unload độc lập.

### Lỗi 4 — Xem `System.gc()` là mệnh lệnh đồng bộ hoàn tất class unloading

`System.gc()` không cung cấp thời hạn hay cam kết class sẽ unload; GC có thể bỏ qua hint. Dùng timeout hợp lý và kết luận “not observed” khi chưa có bằng chứng.

### Lỗi 5 — Chỉ đọc `WeakReference.get()` một lần ngay sau khi tạo class

Đối tượng có thể còn reachable từ stack frame, GC chưa chạy hoặc chưa xử lý refs. Không dùng một phép đọc tức thì làm tiêu chuẩn tuyệt đối.

### Lỗi 6 — Dùng `ReferenceQueue.poll() == null` làm bằng chứng class còn sống

Queue trống có thể do chưa enqueue, đã bị consumer khác đọc, hoặc GC chưa xử lý. Đọc cả weak ref và queue, dùng queue riêng cho probe.

### Lỗi 7 — Coi `ClassLoadingMXBean` tăng nghĩa là đúng hidden class mục tiêu đã unload

MXBean trả số lượng **tổng hợp**. Cần đối chiếu tên runtime trong `class+unload` log hoặc sự kiện JFR.

### Lỗi 8 — Bật JFR rồi mặc định nghĩ `jdk.ClassUnload` đang được ghi

Event cụ thể có thể bị tắt bởi recording settings; hãy `recording.enable("jdk.ClassUnload")` hoặc xác minh cấu hình `.jfc` trước khi kết luận.

### Lỗi 9 — So sánh suffix `0x...` giữa các lần JVM chạy

Suffix do VM cấp, không phải persistent ID. Dùng runtime name được in **trong chính lần chạy đó** và đối chiếu time window.

### Lỗi 10 — Xem absence of log là proof of survival

Không có log có thể do không bật `-Xlog`, class chưa đủ điều kiện, GC chưa chạy hoặc VM không xuất event đúng cửa sổ.

### Lỗi 11 — Cho rằng một hidden class bị unload thì app loader đã unload

Hidden class mặc định có thể unload khi app loader vẫn sống. Đó chính là đặc tính cần kiểm thử; loader unloading là bài toán khác.

### Lỗi 12 — Trộn các tín hiệu “heap giảm”, “metaspace giảm”, “class unload”

Đó là các số đo khác nhau; JVM có thể giữ vùng nhớ dự trữ hoặc chưa trả về OS ngay sau unload. Đừng đòi quá trình dỡ class làm RSS giảm tức thì.

### Lỗi 13 — Dùng `finalize()` hoặc finalize của instance để đo class unloading

Finalization là cơ chế không đáng tin cậy/đã không còn phù hợp để xây test lifecycle hiện đại. Dùng `java.lang.ref`, log JVM và JFR thay vì finalizer.

## 9. Bài tập thực hành

**Bài 1 — Ý nghĩa của hai nhóm W và S.**  
Bạn giữ defining loader sống. Nhóm W định nghĩa hidden class mặc định; nhóm S dùng `ClassOption.STRONG`. Sau GC, W có thể unload còn S không. Điều này nói lên điều gì?

**Đáp án:** Mặc định, hidden class có thể unload độc lập với defining loader nếu không còn strong roots; tùy chọn `STRONG` buộc vòng đời unload theo loader như lớp thông thường.

**Bài 2 — Lỗi do test tự giữ root.**  
Bạn lưu `MethodHandles.Lookup` trên hidden class vào static map để debug rồi thấy `weakRef.get() != null`. Bạn nên sửa gì trước khi kết luận JVM không unload?

**Đáp án:** Bỏ/cắt strong reference đó (và các references qua `Class<?>`/instance/handle khác), đưa hoạt động tạo class vào helper, sau đó quan sát lại với log/JFR.

**Bài 3 — Tại sao không nên viết `assertTrue(weakRef.get() == null)` ngay sau `System.gc()`?**

**Đáp án:** GC và class unloading không có cam kết thời gian; tham chiếu có thể còn live, collector không thực hiện class unloading trong lần gọi đó. Trong CI nên phân loại not observed, hoặc có test chuyên dụng có điều kiện runtime được kiểm soát.

**Bài 4 — `getUnloadedClassCount()` tăng 4 nhưng log không thấy tên hidden class của bạn. Có thể kết luận nó đã unload?**

**Đáp án:** Không. Số liệu MXBean tổng hợp toàn JVM, có thể đến từ những lớp khác. Cần dữ liệu theo class hoặc kiểm tra instrumentation và time window.

**Bài 5 — JFR recording đã chạy, nhưng `jfr print --events jdk.ClassUnload` không có event. Bạn kiểm tra gì?**

**Đáp án:** Xác minh `jdk.ClassUnload` có được bật trước thời điểm unload hay không; recording có bao phủ đúng khoảng đo không; có class thật sự unload không; JVM/JDK và collector; đối chiếu unified log và weak-ref queue.

**Bài 6 — Bạn thấy `weakClearedObserved=true` và dòng JVM log có đúng runtime name nhóm W. Mức kết luận hợp lý?**

**Đáp án:** Có bằng chứng phối hợp từ Java reference processing và JVM rằng **hidden class mục tiêu đã được unload trong lần chạy này**. Không suy ra mọi run đều có timing tương tự.

**Bài 7 — Class đã unload nhưng RSS của tiến trình chưa giảm. Có trái với kết quả?**

**Đáp án:** Không nhất thiết. JVM có thể giữ committed/reserved memory, cơ chế quản lý metaspace và cấp phát native không bắt buộc trả từng vùng nhớ về hệ điều hành ngay khi một class unload.

## 10. Checklist trước khi báo cáo kết quả

- [ ] Xác nhận class được tạo là hidden bằng `isHidden()`; mỗi probe có runtime name riêng.
- [ ] Nhóm W không giữ `Class<?>`, `Lookup`, `MethodHandle` hoặc instance qua strong roots còn live.
- [ ] Nhóm P có một root chủ động và được gỡ đúng thời điểm.
- [ ] Nhóm S dùng `ClassOption.STRONG`, defining loader được giữ reachable trong cửa sổ thử.
- [ ] Có thời lượng chờ giới hạn; ghi JDK version, collector, tùy chọn GC và class unloading.
- [ ] Đọc weak reference và reference queue của **đúng probe**.
- [ ] Bật `-Xlog:class+unload=info` và lưu tên runtime của class mục tiêu để đối chiếu.
- [ ] Nếu dùng JFR, bật rõ event `jdk.ClassUnload` trước khi GC/unload.
- [ ] Đọc `ClassLoadingMXBean` như thông tin tổng hợp, không dùng thay bằng chứng theo class.
- [ ] Kết luận phân biệt **OBSERVED**, **NOT_OBSERVED_WITHIN_WINDOW** và **BLOCKED_BY_STRONG_REFERENCE**, không khẳng định GC bảo đảm xảy ra.
- [ ] Không dùng phép thử này như một security boundary cho bytecode không tin cậy. Hidden class vẫn thực thi mã bytecode trong tiến trình.

## Ghi nhớ

- **Mặc định:** hidden class có thể unload dù defining loader còn sống, nếu không còn strong references.
- **`STRONG`:** class đi theo vòng đời loader; không unload riêng trong khi loader reachable.
- **Không có hành động “unload ngay” bảo đảm:** `System.gc()` chỉ là hint, GC và unload phụ thuộc JVM/collector/reachability.
- **Kiểm thử có đối chứng:** weak không pin, weak có pin và STRONG giúp phát hiện test tự giữ lớp.
- **Bằng chứng nhiều nguồn:** `WeakReference` + `ReferenceQueue` cho thấy referent bị GC; `-Xlog:class+unload` và `jdk.ClassUnload` cho thấy sự kiện JVM theo class; MXBean cho xu hướng tổng thể.
- **Kết luận chính xác:** “đã quan sát unload trong lần chạy này” khác hoàn toàn “sẽ unload trong N mili-giây trên mọi máy”.

## Tài liệu tham khảo hiện hành

- [JDK 25 API — `MethodHandles.Lookup#defineHiddenClass`: unload behavior và `STRONG`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [JDK 25 API — `MethodHandles.Lookup.ClassOption.STRONG`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html)
- [OpenJDK — JEP 371: Hidden Classes](https://openjdk.org/jeps/371)
- [JDK 25 — `WeakReference` và `ReferenceQueue`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/package-summary.html)
- [JDK 25 — `ClassLoadingMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html)
- [JDK 25 — `java` command / Unified Logging (`-Xlog`)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [JDK 25 — JFR `Recording` API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [JDK 25 — JFR `RecordingFile` API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
