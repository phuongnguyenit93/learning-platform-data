# Phân biệt vô hiệu hóa chức năng, gỡ transformer và kết thúc tiến trình

## 1. Ba thao tác cùng được gọi là “tắt agent” nhưng không tương đương

Trong triển khai Java instrumentation, yêu cầu “tắt agent” rất dễ bị hiểu sai. Có ít nhất ba cấp độ tác động hoàn toàn khác nhau:

1. **Vô hiệu hóa chức năng (feature disable):** giữ agent/helper và bytecode đã instrument trong JVM, nhưng chuyển các hook sang nhánh **không thực hiện tác vụ đo đạc** hoặc giảm mức độ thu thập.
2. **Gỡ transformer (unregister):** gọi `Instrumentation.removeTransformer(transformer)` để dừng áp dụng **transformer được đăng ký đó** cho các lớp/định nghĩa sẽ xử lý về sau; **không tự hoàn tác bytecode của lớp đã load**.
3. **Kết thúc tiến trình JVM (process termination):** ứng dụng ngừng chạy. Các thread, lớp runtime, agent và bộ nhớ của tiến trình biến mất khi JVM thực sự kết thúc; đây là **hành động ở cấp tiến trình**, không phải một cách an toàn để “tắt riêng agent” trong ứng dụng đang phục vụ.

Một thao tác thứ tư thường bị nhầm với ba thao tác trên là **hoàn tác biến đổi lớp đã nạp** bằng `retransformClasses` hoặc `redefineClasses` khi được hỗ trợ và đã chuẩn bị đúng bytes. Hoàn tác bytecode là **một công việc chủ động khác**, không phải hiệu ứng mặc định của `removeTransformer`.

Ví dụ agent chèn lời gọi `Probe.hit()` ở entry của `PaymentService.pay()`:

~~~text
PaymentService.pay()                  [class đã được transform]
    |
    +-- Probe.hit() ----------------> kiểm tra cờ enabled
    |
    +-- logic nghiệp vụ

disable feature:
    Probe.hit() vẫn còn trong bytecode
    nhưng hàm trả về sớm, không ghi event

remove transformer:
    lớp PaymentService đã load vẫn còn Probe.hit()
    class mới không đi qua transformer vừa gỡ
    (ngoại trừ callback đã chạy đồng thời)

shutdown JVM:
    cả ứng dụng và agent trong JVM ấy ngừng tồn tại
~~~

Đây là **sơ đồ khái niệm**, không phải một chương trình có thể chạy ngay. Hãy chọn đúng cấp độ theo mục tiêu: giảm overhead, dừng instrument lớp mới, hoàn nguyên class, hay dừng ứng dụng.

## 2. Bảng so sánh nhanh

| Tiêu chí | Tắt bằng cờ/điều kiện | `removeTransformer` | JVM thật sự kết thúc |
| --- | --- | --- | --- |
| JVM tiếp tục chạy? | **Có** | **Có** | **Không** |
| Lớp đã biến đổi tự trở về bytecode gốc? | **Không** | **Không** | Không còn lớp runtime trong tiến trình đó |
| Hook chèn trong bytecode đã load còn tồn tại? | **Có** | **Có** | Không còn tiến trình để thực thi hook |
| Các class mới còn đi qua transformer đang đăng ký? | Có thể, tùy cờ đặt ở helper hay transformer | Không qua transformer **đã gỡ** sau khi gỡ ổn định | Không có class load mới trong JVM đã dừng |
| Agent/helper class còn được load? | Thường **có** | Thường **có** | Mất cùng tiến trình |
| Thread/exporter/static counter hiện có còn chạy? | Tùy logic disable/cleanup | **Có thể tiếp tục** | Bị kết thúc theo vòng đời JVM |
| Có thể bật lại nhanh không? | **Có**, nếu thiết kế cờ an toàn | Cần đăng ký lại transformer và xử lý các class theo mục tiêu | Phải khởi động tiến trình JVM mới |
| Có cần quyền retransformation? | **Không** để đổi cờ runtime | **Không** để unregister | **Không** để exit |
| Nguy cơ chính | Hook vẫn tốn overhead; in-flight events; config visibility | Lầm tưởng rollback; race với class loading; helper vẫn sống | Mất availability, event pending, shutdown không sạch |

**Tính đúng đắn quan trọng:** “Tắt” có thể là **không phát sự kiện nữa**, **không sửa class mới nữa**, **không chạy mã agent nữa**, hoặc **chấm dứt JVM**. Đây là bốn mục tiêu khác nhau. Trước khi thao tác, phải nêu chính xác cần bảo đảm điều nào.

## 3. Vô hiệu hóa chức năng trong runtime: cờ đọc nhanh tại hook

Một phương án thường dùng trong agent chạy lâu là giữ một cờ `volatile` hoặc `AtomicBoolean`. Hook kiểm tra cờ **trước khi** tạo payload, lấy stack trace, serialize hoặc enqueue dữ liệu.

~~~java
import java.util.concurrent.atomic.AtomicLong;

public final class Probe {
    private static volatile boolean enabled = true;
    private static final AtomicLong hits = new AtomicLong();

    private Probe() { }

    public static void setEnabled(boolean value) {
        enabled = value;
    }

    public static void onEnter() {
        if (!enabled) {
            return;  // Không tạo record hoặc gọi exporter.
        }
        hits.incrementAndGet();
    }

    public static long hits() {
        return hits.get();
    }
}
~~~

Đây là **một class Java độc lập**, có thể biên dịch trên Java 17+, nhưng để quan sát hook thật còn cần **một method khác gọi `Probe.onEnter()`** (hoặc agent chèn lời gọi). Ví dụ đầy đủ có Java agent và helper thực tế nằm ở mục 7.

**Ý nghĩa:**

- `volatile enabled` bảo đảm **visibility** cho lần đọc/ghi cờ giữa thread theo Java Memory Model; tránh một thread nhìn mãi giá trị cũ bị cache mà không có quan hệ đồng bộ.
- `AtomicLong` chỉ là ví dụ counter; ở tải cao, `LongAdder` có thể phù hợp cho số đếm tổng hợp nhưng không tạo snapshot nguyên tử nhiều counter.
- Việc tắt **không xóa lời gọi `Probe.onEnter()`** trong bytecode đã được instrument.
- Cờ có thể chuyển lại `true` để ghi nhận từ những invocation sau; không cần retransform chỉ để bật/tắt nhánh logic.

### 3.1. Cờ đặt trong helper và cờ đặt trong transformer khác nhau

**Cờ runtime trong helper:**

~~~text
Class được instrument từ trước:
  method -> Probe.onEnter() -> if (!enabled) return
Tắt enabled:
  method vẫn gọi Probe.onEnter(), nhưng helper bỏ phần ghi.
~~~

**Cờ kiểm soát transform:**

~~~java
@Override
public byte[] transform(
        ClassLoader loader, String className, Class<?> redefinedClass,
        java.security.ProtectionDomain domain, byte[] classfileBuffer) {
    if (!transformEnabled) {
        return null;
    }
    // Kiểm tra className/loader, rồi tạo bytecode đã instrument.
    return transformSelectedClass(classfileBuffer);
}
~~~

Đây là **mảnh code trong `ClassFileTransformer`**, không chạy độc lập: `transformEnabled` và `transformSelectedClass` là thành phần do agent định nghĩa. Khi `transformEnabled=false`, transformer có thể bỏ qua **những lần callback tiếp theo**, nhưng class đã được instrument trước đó **không tự trở về nguyên bản**.

**Đặc biệt:** nếu một method đã chèn lời gọi helper từ trước, chỉ tắt cờ **trong transformer** không làm lời gọi đã chèn ấy ngừng phát event. Thường cần **cả runtime gate trong helper** (để dừng ghi ngay với lớp cũ) và chính sách transformer phù hợp (để không chèn thêm trên lớp mới).

### 3.2. Không đồng nghĩa dừng tức thì mọi việc đang thực hiện

Giả sử thread A đã đọc `enabled=true` và bắt đầu xây event; thread B ngay sau đó đổi cờ thành `false`. Event **đang xử lý** có thể vẫn được hoàn thành. `volatile` bảo đảm visibility cho các lần đọc theo thứ tự bộ nhớ, nhưng **không hủy công việc đã đi qua điểm kiểm tra**.

Nếu cần ranh giới vận hành mạnh hơn, phải thiết kế trạng thái `RUNNING → QUIESCING → DISABLED`, theo dõi số scope đang thực thi, ngừng tiếp nhận event mới, đợi một thời hạn, rồi flush/drop dữ liệu còn lại. **Chờ tất cả scope vô hạn** trong thread nghiệp vụ cũng nguy hiểm nếu có method treo.

Khi ghi cờ ở một hệ thống nhiều loader, còn phải chú ý **class identity**: mỗi loader có thể định nghĩa **một bản helper `Probe`** với static flag riêng. Tắt `Probe.enabled` ở loader A không tự đổi bản ở loader B. Thiết kế điều khiển cần biết helper được định nghĩa ở đâu.

### 3.3. Hook “no-op” vẫn có chi phí

Một call instruction vào helper, branch kiểm tra cờ, đọc volatile, khả năng class init và stack/bookkeeping vẫn có chi phí. JIT có thể tối ưu một phần tùy trường hợp, nhưng **không được hứa overhead bằng 0**. Với những method có tần suất cực cao, hãy benchmark độ trễ/throughput khi bật và khi tắt, sau warmup JIT.

Khi flag off, đừng tiếp tục tạo stack trace/JSON/arguments trước khi kiểm tra flag:

~~~java
// Không tốt nếu ghi stack trace rất tốn kém trước khi biết enabled.
String expensive = captureStackTrace();
if (enabled) exporter.send(expensive);

// Ưu tiên check sớm:
if (!enabled) return;
String payload = captureStackTrace();
exporter.send(payload);
~~~

Đây là **mảnh code trong helper** có `captureStackTrace`, `exporter` và cờ đã khai báo; chỉ nhằm minh họa **thứ tự giảm overhead**.

## 4. Gỡ transformer: dừng cơ chế biến đổi trong tương lai, không rollback class cũ

API chuẩn Java 17:

~~~java
boolean removed = instrumentation.removeTransformer(transformer);
~~~

Đây là **mảnh code trong Java agent** có sẵn `Instrumentation instrumentation` và **chính object `ClassFileTransformer`** đã đăng ký. `removed=true` nghĩa tìm thấy và gỡ một registration. `removed=false` nghĩa transformer đó không được tìm thấy trong danh sách đang đăng ký.

Theo Javadoc Java 17:

- `addTransformer(transformer)` hoặc `addTransformer(transformer, canRetransform)` đăng ký transformer để xử lý các class definitions theo hợp đồng.
- `removeTransformer(transformer)` **hủy một registration**; nếu cùng instance được đăng ký nhiều lần, API gỡ **bản đăng ký gần nhất phù hợp**. Vì vậy đừng cố ý đăng ký lặp nếu không cần.
- Các class definitions **sau khi gỡ ổn định** sẽ không được gửi tới transformer đó.
- **Có thể còn callback đến sau khi `removeTransformer` trả về** do class loading đa luồng đang diễn ra. Transformer phải được viết phòng thủ với khả năng này.
- API **không xóa các bytes đã được áp dụng vào các class đã load** và không dừng các worker/thread/logger/helper của agent.

Nguồn: [Java 17 — Instrumentation.removeTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#removeTransformer(java.lang.instrument.ClassFileTransformer)).

### 4.1. Gỡ transformer khác với “disable transformer”

Có hai cách ngăn future transform:

~~~text
A. Transformer vẫn đăng ký, callback vào -> thấy flag false -> return null.
B. removeTransformer -> các class definitions tương lai không gọi nó
   (trừ callback in-flight có thể vẫn xuất hiện).
~~~

A có thể dễ bật lại bằng cờ nhưng vẫn có overhead callback/matcher. B ngừng registration đó nhưng muốn bật lại phải `addTransformer`. Cả hai **đều không sửa ngược các class đã biến đổi**.

### 4.2. `removeTransformer` không unload agent JAR, helper hay static state

Khi một transformer được gỡ:

- `premain` không “chạy ngược”, không có lifecycle callback mặc định tên `unloadAgent`.
- Các class của agent đã load không đột nhiên biến mất.
- Mọi `AtomicLong`/`LongAdder`, worker pool, daemon thread, shutdown hook và registry của agent phải được **quản lý vòng đời riêng**.
- Các method đã được weave vẫn có thể gọi `AgentHelper.onEnter`.
- Nếu exporter vẫn chạy, nó có thể tiêu thụ tài nguyên dù không còn event mới.
- Với nhiều transformer/agent khác đăng ký, chỉ **registration được gỡ** bị ảnh hưởng; không gỡ tất cả.

Không viết một nút UI “Uninstall agent” mà bên trong chỉ gọi `removeTransformer` rồi báo đã “hoàn nguyên mọi thay đổi”. Đây là cách diễn đạt sai về hiệu lực.

## 5. Vì sao class đã biến đổi vẫn giữ bytecode cũ sau `removeTransformer`?

Class file được transform khi JVM định nghĩa lớp được cài thành **định nghĩa runtime của lớp**. Khi unregister transformer, JVM không nhận yêu cầu sửa lại class đã được định nghĩa. Cho nên, nếu `ServiceA` đã được instrument từ trước, những lần gọi method sau đó vẫn chạy định nghĩa đã được áp dụng (trừ khi có thao tác biến đổi khác).

~~~text
Lúc load ServiceA:
    original bytes
        |
        +-- transformer T: tạo instrumented bytes
        v
    JVM định nghĩa ServiceA có hook

removeTransformer(T):
    registry không còn T
    ServiceA đã nạp vẫn có hook

Lúc load ServiceB sau remove:
    original bytes
        |
        +-- không có T
        v
    JVM định nghĩa ServiceB không nhận biến đổi từ T
~~~

Đây là **sơ đồ đặc tính**, không khẳng định `ServiceB` sẽ hoàn toàn không bị transform bởi **các transformer khác** vẫn đăng ký. Tương tự, nếu `ServiceA` có helper call trước khi instrument, việc gỡ T cũng không xóa một lời gọi được viết từ source.

### 5.1. Tái biến đổi để hoàn tác: thao tác có điều kiện, không phải mặc định

Trong một số môi trường có thể thử:

~~~java
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(targetClass)) {
    inst.retransformClasses(targetClass);
}
~~~

Đây là **mảnh code trong agent**, cần các biến `inst` và `targetClass`. Kết quả **không được hứa là bytecode ban đầu** nếu còn transformer khác, class đã được redefine, hoặc có các output của transformer không retransform-capable cần replay.

Theo Javadoc, khi retransform:

1. JVM bắt đầu từ **initial class-file bytes** (không nhất thiết trùng từng byte với file nguồn; constant pool/layout có thể khác).
2. Các transformer còn tham gia nhưng đăng ký với `canRetransform=false` có thể được **áp dụng lại output trước đó** mà không gọi `transform` lần nữa.
3. Các transformer `canRetransform=true` còn tham gia được gọi theo hợp đồng.
4. Bytes kết quả được verify và cài làm định nghĩa mới nếu hợp lệ.

Vì vậy **chỉ gỡ một transformer rồi retransform** có thể khôi phục lớp trong điều kiện thử nghiệm đơn giản, nhưng **không bảo đảm** gỡ mọi loại instrumentation của agent khác. Muốn rollback production, phải hiểu **toàn chuỗi transformer**, capabilities, class modifiability, các thay đổi đã tích lũy và cách lưu/khôi phục bytes có độ tin cậy.

Đối với `redefineClasses`, agent phải cung cấp bytes `ClassDefinition` tương thích theo ràng buộc JVM; không phải “tự lấy source và compile lại” là luôn được.

### 5.2. Những giới hạn khi retransform/redefine

- `isRetransformClassesSupported()` là **capability tùy chọn** của JVM/agent; ở Java agent startup có thể cần `Can-Retransform-Classes: true` trong manifest. Hỏi flag ngay trong JVM đang chạy.
- `isModifiableClass(clazz)` kiểm tra **từng class cụ thể**; global support không đủ.
- JVM hạn chế nhiều thay đổi schema (thêm/xóa method/field, đổi class hierarchy, các modifier nhất định); đừng đổi hook tùy tiện rồi yêu cầu retransform class đã load.
- **Stack frame đang thực thi có thể tiếp tục chạy bytecode của phiên bản cũ**; các lời gọi mới dùng định nghĩa được cập nhật. Không dùng kết quả của một lần retransform để khẳng định không còn bất kỳ frame cũ nào trong JVM ngay lập tức.
- Class initializer `<clinit>` không tự chạy lại chỉ vì retransform; giá trị các static fields vẫn còn, nên state agent/helper hoặc side effects trước đó không được xóa.
- Nếu đang có transformer khác và native agent, class loader và module constraints có thể tạo thêm giới hạn.
- Một call `retransformClasses` có thể ném `UnmodifiableClassException`, `UnsupportedOperationException`, `ClassFormatError` hoặc lỗi liên kết/verify tùy điều kiện; xử lý chứ không giả định restore thành công.

**Hệ quả:** “Đã gỡ bytecode” là một tuyên bố đòi hỏi **readback/kiểm thử runtime**, không thể suy chỉ từ `removeTransformer()==true`.

## 6. Kết thúc tiến trình JVM: cấp độ mạnh nhất nhưng ảnh hưởng cả ứng dụng

Java có:

~~~java
System.exit(0);                         // Bắt đầu trình tự shutdown JVM.
Runtime.getRuntime().halt(1);          // Cưỡng bức dừng JVM, không chạy shutdown hooks.
~~~

Đây là hai **lời gọi API** để so sánh; **không chạy cả hai liên tiếp** trong cùng chương trình vì lời gọi đầu sẽ không trả về bình thường. Ví dụ `halt(1)` chỉ mang tính minh họa và **không nên chạy trong ứng dụng đang phục vụ** để tắt telemetry.

Theo Javadoc `Runtime.exit` / `System.exit`:

- `System.exit(code)` khởi động trình tự shutdown JVM; theo thông lệ `0` là kết thúc thành công, khác 0 báo kết thúc bất thường.
- JVM khởi chạy các shutdown hooks đã đăng ký theo **thứ tự không xác định**, và các hook có thể chạy **đồng thời**. Sau khi hook kết thúc, JVM dừng.
- Shutdown hook không phải nơi làm việc vô hạn: cần timeout/flush deadline, tránh deadlock, tránh phụ thuộc mù quáng vào dịch vụ khác đang shutdown.
- `Runtime.halt(code)` dừng cưỡng bức, **không khởi chạy shutdown hooks** và không đợi chúng hoàn tất nếu shutdown đã bắt đầu.
- **OS kill cưỡng bức**, crash native, OOME nghiêm trọng và sự cố hạ tầng có thể khiến JVM dừng mà **không có bảo đảm hook sẽ chạy**.

Tài liệu: [Java 17 — Runtime.exit, halt, addShutdownHook](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html).

**Không dùng `System.exit` như “nút tắt agent” trong một service đang chạy**, trừ khi yêu cầu thật sự là **dừng service/JVM** theo quy trình vận hành có phê duyệt. Nó sẽ ngừng cả nghiệp vụ, không chỉ telemetry.

### 6.1. Dừng agent sạch khác với dừng JVM

Một agent có thể cung cấp phương thức `close()` hoặc endpoint quản trị theo mô hình:

~~~text
RUNNING
    |
    v
QUIESCING:
   - tắt cờ để ngừng nhận record mới
   - gỡ transformer để không weave lớp mới
   - chờ giới hạn thời gian cho callback/scope còn xử lý
   - flush exporter tới deadline
   - dừng worker pool, timer, listener, unregister metrics/MBean
   - dọn ThreadLocal/context nếu thuộc quyền kiểm soát
    |
    v
DISABLED (JVM vẫn chạy, class đã instrument có thể còn)
    |
    +-- có chính sách khôi phục bytecode thì retransform riêng
    +-- cần trạng thái class sạch chắc chắn thì rolling restart JVM
~~~

Đây là **workflow mẫu**, không phải API Java agent tự động có sẵn. Việc gỡ transformer không hoàn tác shutdown hook đã đăng ký; nếu cần gỡ hook của mình trước khi JVM bắt đầu shutdown, có thể gọi `Runtime.removeShutdownHook(thread)` khi còn hợp lệ. Cũng không thể ép các thread khác đã chạy hook phải ngừng ngay.

Nếu một telemetry exporter có hàng đợi bounded, tắt producer và flush có deadline để giảm mất dữ liệu; nhưng **không hứa exactly-once/durable delivery** chỉ vì `flush()` trả thành công, nếu exporter/backend không có hợp đồng bền vững tương ứng.

## 7. Ví dụ Java 17 chạy thật: toggle → remove → load class mới → retransform → exit

Bài thực hành dùng **Java agent thật** qua `-javaagent`. Một transformer sửa **một chuỗi literal có độ dài cố định** trong constant pool của hai class mẫu để minh họa class-file bytes đã thay đổi. Một helper có `volatile enabled` quyết định có tăng bộ đếm hay không.

**Giới hạn được nói rõ:** thay `CONSTANT_Utf8` `"ORIGINAL"` thành `"CHANGED!"` (đều dài 8 byte ASCII) là **thủ thuật kiểm thử chỉ dùng trên input đã kiểm soát**, **không phải bytecode-weaving tổng quát** và không chứng minh khả năng chèn hook vào method bất kỳ. Lời gọi `FeatureSwitch.mark()` trong hai target được viết **sẵn trong source** để mô phỏng một hook đã được chèn từ trước. Ví dụ kiểm chứng **vòng đời và tính độc lập của ba hành động**, không trình bày demo như transformer tự động chèn bytecode `mark()`.

### 7.1. Cấu trúc thư mục

~~~text
lifecycle-demo/
  agent-src/demo/agent/
    FeatureSwitch.java
    LifecycleAgent.java
  app-src/demo/app/
    TargetEarly.java
    TargetLate.java
    DemoApp.java
  manifest.mf
  agent-classes/        (sinh khi biên dịch)
  app-classes/          (sinh khi biên dịch)
  agent.jar             (sinh khi đóng JAR)
~~~

### 7.2. `FeatureSwitch.java` — gate runtime còn tồn tại sau khi remove

~~~java
package demo.agent;

import java.util.concurrent.atomic.AtomicInteger;

public final class FeatureSwitch {
    public static volatile boolean enabled = true;
    private static final AtomicInteger HITS = new AtomicInteger();

    private FeatureSwitch() { }

    public static void mark() {
        if (enabled) {
            HITS.incrementAndGet();
        }
    }

    public static int hits() {
        return HITS.get();
    }
}
~~~

Ở đây `enabled=false` làm `mark` bỏ cập nhật; class `FeatureSwitch` và method `mark` **không bị gỡ** khỏi JVM. Với production, có thể tối ưu đường fast-path, loại bỏ logger/reentrancy, và thêm trạng thái vòng đời rõ hơn.

### 7.3. `LifecycleAgent.java` — transformer và API điều khiển

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;

public final class LifecycleAgent {
    private static Instrumentation instrumentation;
    private static ClassFileTransformer transformer;
    private static final AtomicInteger TRANSFORMS = new AtomicInteger();

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        transformer = new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String className,
                    Class<?> redefined, ProtectionDomain protection,
                    byte[] data) {
                if (!"demo/app/TargetEarly".equals(className)
                        && !"demo/app/TargetLate".equals(className)) {
                    return null;
                }
                TRANSFORMS.incrementAndGet();
                return patchConstantForTest(data);
            }
        };
        inst.addTransformer(transformer, true);
        Runtime.getRuntime().addShutdownHook(new Thread(
                () -> System.out.println("shutdownHook=ran")));
        System.out.println("agent=installed");
    }

    public static int seen() {
        return TRANSFORMS.get();
    }

    public static boolean remove() {
        return instrumentation.removeTransformer(transformer);
    }

    public static boolean canRestore(Class<?> type) {
        return instrumentation.isRetransformClassesSupported()
                && instrumentation.isModifiableClass(type);
    }

    public static void restore(Class<?> type) throws Exception {
        instrumentation.retransformClasses(type);
    }

    // Chỉ cho demo: sửa một CONSTANT_Utf8 cùng số byte.
    // Không dùng cách này làm transformer production tổng quát.
    private static byte[] patchConstantForTest(byte[] original) {
        byte[] out = original.clone();
        byte[] oldValue = "ORIGINAL".getBytes(StandardCharsets.US_ASCII);
        byte[] newValue = "CHANGED!".getBytes(StandardCharsets.US_ASCII);
        int count = u2(out, 8);
        int offset = 10;
        boolean changed = false;

        for (int i = 1; i < count; i++) {
            int tag = out[offset++] & 0xff;
            switch (tag) {
                case 1: {
                    int length = u2(out, offset);
                    offset += 2;
                    if (length == oldValue.length
                            && Arrays.equals(Arrays.copyOfRange(
                                    out, offset, offset + length), oldValue)) {
                        System.arraycopy(newValue, 0, out, offset, length);
                        changed = true;
                    }
                    offset += length;
                    break;
                }
                case 3: case 4:
                    offset += 4;
                    break;
                case 5: case 6:
                    offset += 8;
                    i++;
                    break;
                case 7: case 8: case 16: case 19: case 20:
                    offset += 2;
                    break;
                case 9: case 10: case 11: case 12: case 17: case 18:
                    offset += 4;
                    break;
                case 15:
                    offset += 3;
                    break;
                default:
                    throw new IllegalArgumentException("cp tag=" + tag);
            }
        }
        return changed ? out : null;
    }

    private static int u2(byte[] data, int offset) {
        return ((data[offset] & 0xff) << 8)
                | (data[offset + 1] & 0xff);
    }
}
~~~

**Bình luận kỹ thuật:**

- Transformer chỉ áp dụng cho đúng hai internal names; các class agent, JDK, helper và logger không bị xử lý.
- `addTransformer(transformer, true)` đăng ký transformer **có hỗ trợ callback khi retransform**, nếu manifest và JVM cho phép. Đây là **khả năng của transformer**, không có nghĩa mọi class đều modifiable.
- `patchConstantForTest` duyệt constant pool theo `tag` và chỉ sửa UTF-8 entry **khớp chính xác** với literal thử nghiệm. Nó hiểu độ dài cơ bản của các tag cần thiết cho class-file JDK 17; không phải parser production, không kiểm chứng mọi class-file invariants hay multi-release/JDK mới.
- Thay chuỗi có cùng byte length giúp minh họa một biến đổi không đổi schema method/field. Dùng ASM/Byte Buddy/Class-File API thích hợp cho bytecode transformations thật.
- `TRANSFORMS` đếm **callback phù hợp**, không phải mọi lớp trong JVM hay số method calls.
- `Runtime.addShutdownHook` có một hook in dòng kết thúc để minh họa graceful exit; **không** đại diện cho hệ thống flush exporter thực tế.
- Khi nhiều thread load class đồng thời, việc `removeTransformer` trả về không tạo bảo đảm “đã hết mọi callback trong mọi thread”; Javadoc nêu rõ có thể nhận callback muộn.

### 7.4. Hai class target đều có cùng marker ban đầu

**Tệp `app-src/demo/app/TargetEarly.java`:**

~~~java
package demo.app;

import demo.agent.FeatureSwitch;

public final class TargetEarly {
    public static String work() {
        FeatureSwitch.mark(); // Mô phỏng hook đã có trong method.
        return "ORIGINAL";
    }
}
~~~

**Tệp `app-src/demo/app/TargetLate.java`:**

~~~java
package demo.app;

import demo.agent.FeatureSwitch;

public final class TargetLate {
    public static String work() {
        FeatureSwitch.mark();
        return "ORIGINAL";
    }
}
~~~

Cả hai class đều trả literal `"ORIGINAL"` nếu không chịu tác động transformer. Lời gọi `FeatureSwitch.mark()` đã có sẵn, vì vậy **khi helper disabled**, code có thể vẫn thực hiện instruction gọi `mark`, nhưng bên trong helper không tăng counter.

### 7.5. `DemoApp.java` — dùng chính các class trước/sau khi gỡ

~~~java
package demo.app;

import demo.agent.FeatureSwitch;
import demo.agent.LifecycleAgent;

public final class DemoApp {
    public static void main(String[] args) throws Exception {
        System.out.println("early.first=" + TargetEarly.work());
        System.out.println("hits.afterFirst=" + FeatureSwitch.hits());
        System.out.println("transforms.beforeRemove=" + LifecycleAgent.seen());

        FeatureSwitch.enabled = false;
        System.out.println("early.disabled=" + TargetEarly.work());
        System.out.println("hits.whenDisabled=" + FeatureSwitch.hits());

        System.out.println("removed=" + LifecycleAgent.remove());
        System.out.println("early.afterRemove=" + TargetEarly.work());
        System.out.println("transforms.afterRemove=" + LifecycleAgent.seen());

        // Late được tìm bằng tên sau remove, tránh tham chiếu trực tiếp sớm.
        Class<?> late = Class.forName("demo.app.TargetLate");
        System.out.println("late.afterRemove="
                + late.getMethod("work").invoke(null));
        System.out.println("transforms.afterLate=" + LifecycleAgent.seen());

        FeatureSwitch.enabled = true;
        System.out.println("early.reenabled=" + TargetEarly.work());
        System.out.println("hits.reenabled=" + FeatureSwitch.hits());

        System.out.println("canRestore="
                + LifecycleAgent.canRestore(TargetEarly.class));
        if (LifecycleAgent.canRestore(TargetEarly.class)) {
            LifecycleAgent.restore(TargetEarly.class);
            System.out.println("early.afterRetransform="
                    + TargetEarly.work());
        }
        System.out.println("transforms.final=" + LifecycleAgent.seen());
        System.out.println("process=exiting");
        System.exit(0);
        System.out.println("unreachable");
    }
}
~~~

**Điểm then chốt:** `TargetEarly` được nạp khi transformer còn đăng ký, còn `TargetLate` được tìm bằng `Class.forName` **sau khi gỡ**. Vì chương trình thử có một thread và không có callback concurrent liên quan, điều này cho phép thấy sự khác biệt rõ ràng. Trong production, class loading là concurrent và không có giao ước “mọi thread đều dừng ngay sau lệnh remove”.

### 7.6. Agent manifest và lệnh chạy

**Tệp `manifest.mf`:**

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.LifecycleAgent
Can-Retransform-Classes: true

~~~

Dòng trống cuối là phần kết thúc main section của manifest. `Can-Retransform-Classes: true` là cần cho ví dụ cố gắng dùng `addTransformer(..., true)` và retransform; nó **không có nghĩa JVM nào cũng hỗ trợ** khả năng này.

Trên Linux/macOS, từ thư mục `lifecycle-demo`:

~~~bash
mkdir -p agent-classes app-classes
javac --release 17 -d agent-classes \
  agent-src/demo/agent/FeatureSwitch.java \
  agent-src/demo/agent/LifecycleAgent.java

jar --create --file agent.jar --manifest manifest.mf \
  -C agent-classes .

javac --release 17 -cp agent.jar -d app-classes \
  app-src/demo/app/TargetEarly.java \
  app-src/demo/app/TargetLate.java \
  app-src/demo/app/DemoApp.java

java -javaagent:agent.jar -cp "app-classes:agent.jar" demo.app.DemoApp
~~~

Trên **Windows PowerShell**, hai tên đường dẫn classpath cách nhau bằng dấu chấm phẩy thay vì dấu hai chấm. Các lệnh compile có thể chạy từng dòng, không sử dụng ký tự tiếp dòng `\` của Bash:

~~~powershell
New-Item -ItemType Directory -Force agent-classes, app-classes | Out-Null
javac --release 17 -d agent-classes agent-src/demo/agent/FeatureSwitch.java agent-src/demo/agent/LifecycleAgent.java
jar --create --file agent.jar --manifest manifest.mf -C agent-classes .
javac --release 17 -cp agent.jar -d app-classes app-src/demo/app/TargetEarly.java app-src/demo/app/TargetLate.java app-src/demo/app/DemoApp.java
java -javaagent:agent.jar -cp "app-classes;agent.jar" demo.app.DemoApp
~~~

Yêu cầu **JDK 17+ đầy đủ** có `javac`/`jar` và JVM hỗ trợ retransform. Không cần dynamic attach hay thư viện ngoài JDK.

### 7.7. Kết quả đã kiểm thử trên OpenJDK 21 với `--release 17`

~~~text
agent=installed
early.first=CHANGED!
hits.afterFirst=1
transforms.beforeRemove=1
early.disabled=CHANGED!
hits.whenDisabled=1
removed=true
early.afterRemove=CHANGED!
transforms.afterRemove=1
late.afterRemove=ORIGINAL
transforms.afterLate=1
early.reenabled=CHANGED!
hits.reenabled=2
canRestore=true
early.afterRetransform=ORIGINAL
transforms.final=1
process=exiting
shutdownHook=ran
~~~

Đây là **stdout chính xác** đã được đối chiếu bằng việc biên dịch toàn bộ class với `javac --release 17`, đóng agent JAR và chạy `java -javaagent:...` trên OpenJDK 21/HotSpot. Với JVM không hỗ trợ retransformation hoặc class không modifiable, chương trình phải chọn chính sách khác; cấu hình này cố ý có manifest yêu cầu capability và có thể không khởi động tương đương trên mọi VM.

### 7.8. Đọc kết quả theo từng thao tác

- `early.first=CHANGED!`: `TargetEarly` được biến đổi ở lần load đầu tiên; class runtime không còn trả marker `ORIGINAL`.
- `hits.afterFirst=1`: helper đang enabled, nên hook gọi từ `TargetEarly.work()` tăng counter.
- `early.disabled=CHANGED!` nhưng `hits.whenDisabled=1`: **tắt helper chỉ thay đổi hành vi hook**, không hoàn nguyên nội dung class.
- `removed=true`: `Instrumentation.removeTransformer` gỡ registration trong demo.
- `early.afterRemove=CHANGED!`: **class đã load giữ biến đổi** dù transformer đã gỡ.
- `late.afterRemove=ORIGINAL` và `transforms.afterLate=1`: trong demo một luồng, `TargetLate` được load sau khi gỡ nên không nhận patch của transformer này.
- `early.reenabled=CHANGED!`, `hits.reenabled=2`: bật lại cờ khiến **hook còn trong code** hoạt động; không cần đăng ký lại transformer.
- `canRestore=true` và `early.afterRetransform=ORIGINAL`: trong điều kiện demo chỉ có transformer này, sau khi gỡ và yêu cầu retransform, JVM dùng lớp định nghĩa mới không chịu patch.
- `transforms.final=1`: transformer đã unregister không còn callback trong lần retransform của ví dụ.
- `process=exiting` rồi `shutdownHook=ran`: `System.exit(0)` bắt đầu shutdown; dòng `unreachable` không xuất hiện.

**Điều không thể kết luận từ demo:** retransform trên mọi ứng dụng production đều hoàn nguyên đúng bytecode nguyên bản; flag off loại bỏ mọi overhead; remove bảo đảm không còn callback đang chạy; hay shutdown hook chắc chắn chạy nếu process bị `SIGKILL`/crash.

## 8. Dừng biến đổi lớp mới nhưng vẫn giữ chức năng lớp cũ: có khi là đúng chủ đích

Không phải luôn phải rollback. Một số tình huống:

| Mục tiêu | Thao tác hợp lý | Điều cần chấp nhận |
| --- | --- | --- |
| Muốn giảm lượng telemetry ngay vì backend quá tải | Tắt gate trong helper/exporter, tăng drop counter nếu cần | Bytecode hook vẫn tồn tại; event in-flight |
| Muốn không chèn probe vào class load tiếp theo | Tắt matcher hoặc gỡ transformer | Class đã load còn instrumented |
| Muốn tạm bật lại telemetry nhanh | Giữ helper/runtime gate và thay đổi cờ | Có overhead hook khi disabled |
| Muốn agent không nhận class-load callbacks nữa | `removeTransformer` | Helper/worker/static state không tự được gỡ |
| Muốn giảm overhead của lớp đã instrument | Có thể cân nhắc retransform/redefine để hoàn nguyên, nếu hợp lệ | JVM capability, rủi ro verification, schema, agent khác |
| Muốn trạng thái code/class loader chắc chắn sạch qua lần triển khai | Rolling restart JVM với cấu hình/agent mới | Có tác động availability và operational coordination |
| Muốn dừng service khỏi hệ thống | Graceful shutdown rồi process exit | Tắt toàn bộ ứng dụng trong JVM |
| Muốn dừng riêng một agent đang attach trong JVM | Thiết kế một control plane/`close()` riêng | Không có API Java chuẩn tổng quát “unload this javaagent” |

Khi đòi hỏi “disable hoàn toàn”, phải yêu cầu định nghĩa **SLO/tiêu chí kiểm chứng**: không event mới, không callback mới, không hook bytecode, không agent thread, hay không agent classes còn load? Một số mục tiêu có thể đạt bằng cờ/remove, một số cần retransform, và mục tiêu “không còn agent classes trong JVM” thường thực tế nhất qua **khởi động JVM mới** mà không nạp agent đó.

## 9. Tình huống đồng thời và bộ nhớ: tính nhất quán không phải tức thời

### 9.1. Giao thức chuyển trạng thái nên có mốc rõ ràng

Ví dụ state machine điều khiển từ endpoint quản trị:

~~~text
RUNNING
  |
  | request-disable
  v
QUIESCING (ngăn sự kiện mới; còn callback/scope đang xử lý)
  |
  | drain tới deadline, unregister, stop worker
  v
DISABLED
  |
  | request-enable, khởi động lại worker nếu cần
  v
RUNNING
~~~

Nếu mỗi thread gọi `FeatureSwitch.mark` đều đọc cờ volatile trước khi làm việc, các lời gọi **mới đi qua check sau cập nhật** nhìn được trạng thái phù hợp với đồng bộ của volatile. Nhưng những callback đã vượt qua check vẫn có thể hoàn tất; deadline/quiescence phải quan sát thêm counter active scopes hoặc queue depth.

Đừng đặt `synchronized` bao quanh toàn bộ method nghiệp vụ chỉ để tắt telemetry “ngay lập tức” nếu nó phá throughput và gây deadlock. Nếu cần tính chất tuyến tính hóa mạnh, hãy thiết kế điểm chuyển trạng thái và cái giá phải trả một cách có chủ đích.

### 9.2. Callback transformer có thể vào sau khi gỡ

Javadoc cảnh báo về class loading nhiều thread. Vì vậy một transformer tốt nên dùng một cờ terminal/volatile để từ chối công việc không còn hợp lệ ngay cả trong callback muộn:

~~~java
private volatile boolean registeredAndActive = true;

@Override
public byte[] transform(
        ClassLoader loader, String name, Class<?> type,
        java.security.ProtectionDomain domain, byte[] bytes) {
    if (!registeredAndActive) {
        return null;
    }
    // Chỉ làm phần transform đã được phép và kiểm soát reentrancy.
    return transformAllowedClass(name, bytes);
}
~~~

Đây là **mảnh code trong một class implements `ClassFileTransformer`**; `transformAllowedClass` do ứng dụng định nghĩa. Khi disable/unregister, đặt cờ false và gỡ transformer; code callback đang xử lý trước khi thấy cờ vẫn có thể hoàn tất.

**Không dùng một Boolean không `volatile`/không đồng bộ** làm control plane trong môi trường nhiều thread rồi giả định mọi thread nhận thấy thay đổi tức thì.

### 9.3. Các phiên bản bytecode có thể tồn tại song song trong quá trình retransform

Khi `retransformClasses` thành công, **active stack frames** của method đã thay đổi có thể tiếp tục dùng bytecode phiên bản cũ, còn những invocation mới nhận bytecode mới. Đây là hành vi được Javadoc nhắc tới; không phải dấu hiệu “removeTransformer thất bại”.

Nếu cần cam kết không còn hook nào đang thực thi, hãy đợi scope hoàn tất hoặc lựa chọn restart JVM ở mốc rollout. Tránh thao tác với frames đang chạy bằng assumptions không được JVM bảo đảm.

## 10. Resource cleanup: gỡ transformer không dọn worker và queue

Agent có thể đã tạo:

- Một queue bounded chứa event chưa export.
- Executor/daemon worker, scheduler, HTTP client, native handle.
- `ThreadLocal` context và cache theo class loader.
- Metrics registry, JMX MBean, shutdown hook.
- File/JAR resources, buffered output và kết nối network.

`removeTransformer` không gọi `close()` trên những thành phần này. Một cơ chế dừng có thể là:

~~~java
public void stop() {
    enabled = false;
    instrumentation.removeTransformer(transformer);
    exporter.stopAccepting();
    exporter.flushUntilDeadline();
    exporter.close();
}
~~~

Đây là **pseudocode Java của một service sở hữu các trường** `enabled`, `instrumentation`, `transformer` và `exporter`; các phương thức exporter là do thư viện/ứng dụng thiết kế, không phải API chuẩn của `Instrumentation`.

**Thứ tự cần kiểm tra:** khi đã ngừng nhận telemetry, có thể còn event in-flight. Nếu đóng exporter trước khi helper ngừng tạo event, hệ thống có thể phát exception từ hook/đánh mất dữ liệu ngoài dự kiến. Cần chính sách rõ: drop có counter, flush tới deadline, hoặc durable spool. Tránh bắt lỗi broad rồi làm business method thất bại vì telemetry.

Nếu có nhiều transformer, mỗi transformer cần registration handle và owner riêng; không gọi `removeTransformer` cho object mà module khác đang sử dụng mà chưa có thỏa thuận lifecycle.

### 10.1. Shutdown hook không phải kênh giao dịch đảm bảo

Hook có thể giúp flush **best effort**, nhưng:

- Các hook JVM không có thứ tự chạy được bảo đảm và chạy đồng thời.
- Hooks có thể bị deadlock nếu cần dịch vụ đã shutdown.
- JVM bị cưỡng bức dừng có thể bỏ qua hook.
- Backends/exporters có thể không nhận record kịp trong thời hạn OS cho phép.
- Gọi `System.exit` ngay trong hook có thể gây hành vi không mong muốn trong shutdown sequence.

Với dữ liệu audit bắt buộc, dùng transactional/durable logging theo yêu cầu nghiệp vụ; không thay bằng một shutdown hook và buffer in-memory.

## 11. Vận hành trong container, server và rolling deployment

### 11.1. “Process đã chết” có nghĩa telemetry sẽ biến mất mãi?

Không nhất thiết. Một container orchestrator, service manager hoặc process supervisor có thể **tự khởi động lại** JVM với cùng `-javaagent` hoặc `JAVA_TOOL_OPTIONS`. Khi đó agent sẽ lại chạy `premain` trong JVM mới. Vì vậy muốn tắt agent **qua các lần khởi động**, phải sửa **cấu hình triển khai** (startup flags, agent JAR, sidecar settings, environment hoặc attachment policy), rồi rollout đúng quy trình.

**Ví dụ khác nhau:**

~~~text
Tắt runtime:
  /admin/telemetry = off
  -> JVM hiện tại còn sống, toggle enabled

Gỡ transformer:
  agentController.unregister()
  -> JVM sống, lớp cũ còn đã biến đổi

Rolling restart bỏ agent:
  sửa JVM startup args, restart từng instance
  -> JVM mới không nạp agent theo cấu hình đã thay
~~~

Đây là **quy trình vận hành mô tả**, không phải endpoint chuẩn của JDK. Một deployment có thể có nhiều instance; tắt ở một instance không tự áp dụng tới các instance khác.

### 11.2. Dynamic attach và tháo agent

`agentmain` có thể được gọi khi Java agent được nạp động theo khả năng JVM/cấu hình. Nhưng Java `Instrumentation` **không cung cấp một phương thức chung “unload agent JAR và undo mọi thay đổi”**. Một agent muốn có nút deactivate phải **tự cung cấp** control endpoint/command, hủy registration và cleanup helper/resources. Với native JVMTI agent, lifecycle và khả năng unload là một cơ chế khác; không lấy quy tắc một phía áp cho mọi loại agent.

Một số trạng thái JVM không thể đảm bảo đảo ngược hoàn toàn trong cùng process (class identity, loaded classes, static initialization, side effects đã xảy ra). **Restart có kiểm soát** thường là ranh giới đáng tin cậy nhất nếu yêu cầu “trở về một JVM chưa từng nạp agent”.

## 12. Chẩn đoán một lần “tắt” có thực sự đạt mục tiêu không?

Tránh chỉ kiểm tra một dòng `removed=true` rồi đóng incident. Nên tách các câu hỏi:

| Câu hỏi | Kiểm chứng phù hợp |
| --- | --- |
| Cờ runtime có chuyển về false không? | Đọc AtomicBoolean/volatile qua API quản trị và quan sát hook counter |
| Hook đã load còn phát event không? | Gọi một method đã instrument trong test, so event/counter trước–sau |
| Transformer có được unregister không? | `removeTransformer` trả true/false và ownership registry |
| Callback còn xảy ra sau remove? | Count callback của một class load **mới**, lưu ý in-flight races |
| Lớp cũ còn bytecode đã sửa? | Kiểm tra hành vi hoặc class bytes theo cơ chế tin cậy; thử trên đúng loaded Class |
| Có thể retransform để rollback không? | `isRetransformClassesSupported` + `isModifiableClass` + kết quả/exception thực tế |
| Helper/exporter còn thread sống không? | Thread/worker/queue/JMX/metrics diagnostics |
| Queue có record pending khi shutdown không? | Queue depth, exporter in-flight, retry buffer, flush result/deadline |
| JVM thật sự chấm dứt? | Process exit status, supervisor/container health và log lifecycle |
| Agent có còn xuất hiện sau restart? | Kiểm tra startup flags/JVM args và rollout config, không chỉ PID cũ |

Những điều **không nên dùng làm bằng chứng duy nhất**:

- “Không còn log”: có thể do sampling, exporter down, log level hoặc lỗi mất event.
- “Bộ đếm bằng 0”: có thể chưa có request, không phải bytecode đã gỡ.
- “`removeTransformer` trả true”: chỉ nói về registration, không phải runtime class rollback.
- “`retransformClasses` không ném lỗi”: cần xác minh class đã có trạng thái mong muốn và không bị transformer khác tác động.
- “Chạy `System.exit`”: có thể tiến trình chưa dừng vì hook treo, hoặc supervisor đã restart JVM mới.

## 13. Lỗi triển khai thường gặp

| Ngộ nhận | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Tắt cờ là tự xóa lời gọi hook khỏi bytecode | Overhead vẫn còn, lớp vẫn instrumented | Tách **no-op** và **rollback class** |
| Gỡ transformer để hoàn tác toàn bộ class cũ | Class đã load tiếp tục mang biến đổi | Cần retransform/redefine có điều kiện hoặc restart |
| Gỡ transformer có nghĩa helper/exporter đã được unload | Worker/thread/cache vẫn sống | Tự stop/flush/close |
| Chỉ dùng cờ trong transformer để vô hiệu hook lớp cũ | Class cũ vẫn gọi helper | Cổng runtime trong helper hoặc rollback |
| Dùng Boolean không volatile cho shared config | Thread có thể thấy dữ liệu không nhất quán | `volatile`/`AtomicBoolean`/đồng bộ |
| Cho rằng remove xong tuyệt đối không callback | Concurrent load đã bắt đầu có thể gọi muộn | Transformer kiểm tra cờ và quản lý in-flight |
| Đăng ký một transformer instance hai lần, remove một lần | Còn registration trùng | Tránh đăng ký lặp; theo dõi ownership |
| Gọi retransform mà không hỏi global/per-class capability | Exception, class không modifiable | `isRetransformClassesSupported` và `isModifiableClass` |
| Nghĩ retransform luôn trả về bytes file gốc y hệt | Có transformer khác, replay, layout khác | Nắm chuỗi transform và verify kết quả |
| Nghĩ retransform reset static counter/`<clinit>` | State cũ còn trong JVM | Dọn state riêng nếu cần |
| Nghĩ retransform cập nhật ngay active frame | Frame cũ có thể đang chạy | Quiescence hoặc restart có kiểm soát |
| Dùng `System.exit` để tắt riêng agent | Cả ứng dụng bị dừng | Dùng lifecycle API của agent; exit chỉ khi dừng service |
| Dùng `Runtime.halt` để flush/close | Không chạy shutdown hooks | Graceful stop với deadline nếu cần |
| Để flush vô hạn trong hook shutdown | JVM có thể kẹt khi exit | Deadline và fallback policy |
| Bỏ agent ở một container nhưng chưa đổi rollout config | Supervisor khởi động lại với agent | Quản lý deployment config |
| Cho rằng class loader của agent tự được GC khi unregister | References/static/threads còn giữ loader | Dọn caches/threads/registries, chú ý classloader |
| Ghi biến cấu hình vào nhiều bản helper khác loader | Chỉ một nhóm target thực sự disabled | Tổ chức helper loader/bridge và config thống nhất |
| Xóa agent JAR khỏi ổ đĩa trong lúc JVM chạy để “unload” | Không thay runtime classes đang nạp | Quản lý đúng lifecycle, rolling restart |
| Không đo in-flight events khi disable | Thấy một vài event “đi sau lệnh tắt” rồi tưởng race lỗi | Ghi rõ semantics và quan sát quiescence |
| Dùng constant-pool patch demo làm bytecode-weaving production | Có thể phá class file hoặc cập nhật entry không mong muốn | Dùng library/API bytecode chuẩn và verifier |

## 14. Checklist kiểm thử trước khi đưa vào sản xuất

**A. Feature toggle**

- [ ] Với một class đã instrument, bật → hook ghi event/counter như dự kiến.
- [ ] Tắt → các invocation mới không tạo payload/không gửi event, counter không tăng.
- [ ] Bật lại → cùng class đã load hoạt động theo cờ mới, không cần transform lần nữa.
- [ ] Nhiều thread đọc cờ đúng visibility; xử lý in-flight scopes và nested calls.
- [ ] Kiểm tra helper ở các class loaders khác nhau không mang flag bất đồng bộ ngoài dự định.
- [ ] Đo overhead khi disabled; không hứa zero overhead.

**B. Gỡ transformer**

- [ ] `removeTransformer` trả boolean chính xác với đúng instance.
- [ ] Đếm callback trước/sau khi load một class mới có chủ đích.
- [ ] Test race với class loading concurrent; transformer phản ứng an toàn với callback muộn.
- [ ] Class cũ không tự rollback; nếu muốn rollback cần test riêng.
- [ ] Không đăng ký trùng một transformer trong cùng lifecycle; hoặc có cơ chế gỡ đầy đủ từng registration.
- [ ] Không ảnh hưởng transformer/agent khác.

**C. Rollback và shutdown**

- [ ] Hỏi capability JVM và modifiability của class trước retransform.
- [ ] Test class đã load, class chưa load, active method frame và side effect.
- [ ] Kiểm tra bytes mới có hợp lệ với VM/module/loader; không đổi schema bị cấm.
- [ ] Rà soát các non-retransformable transformers còn đăng ký và output replay.
- [ ] Stop exporter với timeout, kiểm tra dropped/pending/in-flight records.
- [ ] Kiểm thử `System.exit(0)` trong tiến trình **thử riêng**, không dùng production host.
- [ ] Kiểm tra shutdown hook chạy trong đường shutdown bình thường và **không bảo đảm** với forced kill.
- [ ] Kiểm tra trạng thái agent khi JVM mới khởi động theo deployment config.
- [ ] Có rollout/rollback plan nếu startup agent thay đổi ở cụm nhiều instance.

## 15. Câu hỏi tự kiểm tra

1. Nếu bytecode đã chèn `Probe.onEnter()` từ hôm qua, hôm nay đặt `enabled=false` thì instruction gọi `Probe.onEnter()` có biến mất không?
2. Khác biệt giữa cờ trong **helper** và cờ trong **transformer** là gì?
3. `removeTransformer(t)` trả `true` xác nhận điều gì, và **không** xác nhận điều gì?
4. Vì sao `removeTransformer` có thể vẫn đi kèm callback xuất hiện sau khi lời gọi trả về?
5. Nếu đăng ký **cùng một transformer instance hai lần**, một lần `removeTransformer` có đủ không?
6. Vì sao `TargetEarly` trong demo vẫn trả `CHANGED!` sau khi gỡ transformer?
7. Vì sao `TargetLate` lại trả `ORIGINAL` trong cùng lần chạy thử?
8. Khi bật lại cờ `enabled=true` sau remove, tại sao hook của class cũ vẫn tăng counter?
9. Điều kiện nào cần kiểm tra trước khi gọi `retransformClasses(TargetEarly.class)`?
10. Vì sao ví dụ có thể restore bằng retransform mà không thể suy ra mọi hệ thống production cũng restore được?
11. Nếu method đang chạy lúc retransform, bytecode cũ có thể tiếp tục được dùng ở đâu?
12. Vì sao retransform không đặt lại static counter hoặc chạy lại `<clinit>`?
13. `System.exit(0)` khác `Runtime.halt(1)` ở shutdown hooks như thế nào?
14. Vì sao một JVM dừng xong agent có thể lại xuất hiện khi container/service restart?
15. Nếu yêu cầu “không còn bất cứ class agent nào trong process”, vì sao remove transformer thường chưa đáp ứng mục tiêu?
16. Khi agent có bounded telemetry queue, thứ tự disable/drain/close cần cân nhắc gì?
17. Lời gọi `FeatureSwitch.mark()` trong source demo có phải do transformer tự chèn không? Nếu không, demo đang chứng minh điều gì?
18. Nếu remove xong vẫn còn log, những nguyên nhân nào không liên quan lỗi `removeTransformer`?

**Ghi nhớ:** **Vô hiệu hóa chức năng** đổi hành vi của helper/hook, **gỡ transformer** dừng một registration để class definitions mới không đi qua nó, còn **kết thúc JVM** chấm dứt cả tiến trình ứng dụng. Không thao tác nào trong hai thao tác đầu **tự động hoàn tác** class đã instrument. Hoàn nguyên bytecode đòi một kế hoạch retransform/redefine có điều kiện và QA; dọn worker/exporter cần lifecycle riêng. Khi mục tiêu là “JVM chưa từng nạp agent”, một restart có kiểm soát với startup config mới đáng tin cậy hơn việc gọi `removeTransformer`.

### Tài liệu tham khảo chính thức

- [Java 17 — Instrumentation: addTransformer, removeTransformer, retransformClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java 17 — ClassFileTransformer và callback lifecycle](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Java 17 — java.lang.instrument: manifest, premain, agentmain](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Java 17 — Runtime: exit, halt và shutdown hooks](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html)
- [Java 17 — AtomicBoolean, volatile và Java concurrency memory effects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html)
