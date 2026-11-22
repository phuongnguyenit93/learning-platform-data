# Transformer có thể nhận lời gọi đồng thời từ nhiều luồng nạp lớp

> **Mục tiêu:** Hiểu vì sao một đối tượng `ClassFileTransformer` Java có thể phải xử lý **nhiều lời gọi `transform(...)` đang diễn ra đồng thời**, ngay khi ứng dụng có nhiều luồng nạp những lớp khác nhau. Biết thiết kế transformer **thread-safe** mà không khóa toàn bộ quá trình nạp lớp; phân biệt biến cục bộ với trạng thái chia sẻ, dùng `ConcurrentHashMap`, `LongAdder`, `AtomicInteger` đúng chỗ, phòng tránh race condition, deadlock, class-loader recursion và memory leak. Có một bài lab **Java 17+ chạy được** để quan sát hai luồng yêu cầu nạp class, tổng hợp kết quả an toàn và không giả định lịch trình thread cố định.

Bài thuộc nhóm **Đồng thời và hiệu năng** của Java Advanced Instrumentation. Chủ đề là **tính đồng thời tại callback biến đổi class**. Nó khác tính thread-safe của mã ứng dụng sau khi class đã được định nghĩa, và khác chuyện một class được nhiều luồng cùng sử dụng. Một transformer có thể xử lý nhiều **class files** trên nhiều thread; nếu nó dùng chung bộ nhớ không an toàn, output hoặc số liệu quan sát có thể sai ngay trong giai đoạn JVM nạp lớp.

## 1. Hình dung hai luồng cùng nạp class

Một JVM có thể có nhiều hoạt động nạp class:

- Luồng A khởi tạo endpoint, yêu cầu loader định nghĩa `com/example/OrderService`.
- Luồng B khởi động một tác vụ khác, yêu cầu loader định nghĩa `com/example/InvoiceService`.
- Một framework nạp proxy, lambda/hidden classes hoặc các plugin.
- Một công cụ khác yêu cầu redefine/retransform trong khi JVM còn hoạt động.

Nếu agent đã gọi:

```java
instrumentation.addTransformer(transformer, false);
```

thì khi JVM xử lý các định nghĩa class phù hợp, **cùng đối tượng `transformer`** được sử dụng để gọi `transform`. Không có hợp đồng chung rằng JVM sẽ tuần tự hóa **mọi callback** lên đối tượng ấy dưới **một khóa toàn cục**.

```text
Thread "loader-A"                         Thread "loader-B"
       │                                         │
       ▼                                         ▼
defineClass(OrderService)                defineClass(InvoiceService)
       │                                         │
       ▼                                         ▼
┌───────────────────────┐             ┌───────────────────────┐
│ transformer.transform │             │ transformer.transform │
│ input bytes cho A     │             │ input bytes cho B     │
└──────────┬────────────┘             └────────────┬──────────┘
           │                                       │
           └──────── cùng Java object ────────────┘
                           │
                 Shared state của agent?
```

Hai callback **có thể chồng lấn** về thời gian, tùy JVM, class loader, thời điểm scheduling và tên class. Không phải mọi JVM hay mọi test đều bắt buộc chạy hai callback đồng thời. Quy tắc thiết kế đúng là: **đừng dựa vào việc chúng luôn nối tiếp nhau**.

**Javadoc `Instrumentation.removeTransformer`** còn nhấn mạnh class loading mang tính đa luồng: callback đang diễn ra hoặc đã được lập lịch có thể xuất hiện **sau khi một transformer được gỡ đăng ký**. Vì vậy đồng thời ảnh hưởng cả xử lý callback lẫn vòng đời agent.

## 2. Callback `transform` được gọi khi nào?

Trong `java.lang.instrument.ClassFileTransformer`, Java 9+ cung cấp overload:

```java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

Đây là **chữ ký tham khảo**, không phải method hoàn chỉnh để biên dịch độc lập. Khi dùng Java 17+, hãy override trong một implementation hoặc anonymous class như ví dụ mục 8.

Các tình huống phù hợp:

| Loại hoạt động | Callback Java `canRetransform=false` | Callback Java `canRetransform=true` |
| --- | --- | --- |
| Nạp/định nghĩa class mới | Có thể được gọi | Có thể được gọi |
| `Instrumentation.redefineClasses` | Có thể được gọi | Có thể được gọi |
| `Instrumentation.retransformClasses` | **Không gọi lại**, JVM dùng output trước đó | Có thể được gọi |

“Có thể được gọi” nghĩa là transformer đã được đăng ký ở thời điểm xử lý và class definition áp dụng cho nó. Đây là **phân loại sự kiện**, không phải khẳng định callback nào cũng có công việc biến đổi thật.

Khi nhiều transformer cùng tham gia, JVM áp dụng chuỗi theo thứ tự bốn nhóm **Java incapable → JVMTI native incapable → Java capable → JVMTI native capable**. Trong một nhóm Java, thứ tự đăng ký quyết định thứ tự xử lý của **một định nghĩa class**. Điều đó **không hề biến các class khác nhau thành một hàng đợi callback tuần tự trên toàn JVM**.

Nếu `transform(...)` trả `null`, nó nói “không thay đổi bytes ở tầng hiện tại”. Nếu trả `byte[]` mới, callback sau sẽ nhận bytes mới. **Không sửa trực tiếp `classfileBuffer`**: Javadoc yêu cầu mảng input không được thay đổi.

## 3. Không nhầm khóa của class loader với khóa của transformer

JDK `ClassLoader` có cơ chế đồng bộ khi tìm/định nghĩa class. `loadClass(name, resolve)` thường sử dụng `getClassLoadingLock(name)`:

- Class loader **chưa đăng ký parallel capable** thường dùng chính object loader làm khóa. Khi đó một loader có thể tuần tự hóa nhiều yêu cầu nạp class.
- Class loader **parallel capable** có thể trả khóa riêng theo tên class. Những tên class khác nhau có cơ hội được nạp đồng thời.
- Nhiều **loader instances** riêng biệt có khóa riêng, ngay cả khi mỗi loader tự tuần tự hóa các lời gọi của chính nó.
- Lịch trình thực tế còn phụ thuộc JVM, dependency loading, initialization và các khóa khác.

Từ Java 7, custom loader có thể dùng `registerAsParallelCapable()` đúng quy tắc (trước khi tạo instance và các superclass thích hợp đã parallel capable) nếu muốn hỗ trợ nạp song song. **Không gọi nó chỉ để “chữa” một race trong transformer**: thread safety của transformer phải được xử lý độc lập.

```text
Loader L1 khóa A  ──> class C1 ──> transformer.transform(...)
Loader L2 khóa B  ──> class C2 ──> transformer.transform(...)
```

Dù L1 và L2 có kiểm soát riêng, chúng không bảo đảm hai lời gọi `transform` qua **cùng transformer object** bị loại trừ lẫn nhau. Một lỗi quen thuộc là nghĩ “JVM đã có class-loading lock nên mọi field của agent là an toàn”.

### Cùng một class có nhất thiết được load đồng thời nhiều lần?

Không nên diễn giải thành “hai thread trong cùng defining loader có thể định nghĩa cùng một binary name thành công hai lần”. JVM có các ràng buộc về class identity và loading/definition. Nhiều yêu cầu cùng tên có thể chờ nhau, cùng thấy class đã định nghĩa hoặc thất bại theo cơ chế loader. **Vấn đề của bài học là hai hoặc nhiều class khác nhau**, có thể thuộc loader khác nhau, cùng đi qua transformer.

Một tên class giống nhau từ hai **defining class loaders** khác nhau đại diện hai runtime types khác nhau. Nếu agent dùng cache chỉ theo `className`, nó có thể vô tình trộn kết quả của hai loader.

## 4. Mô hình race condition đơn giản nhất: field dùng chung

Giả sử transformer giữ một buffer biến đổi dưới dạng field:

```java
// Ví dụ SAI, không phải transformer độc lập.
private final java.io.ByteArrayOutputStream scratch =
        new java.io.ByteArrayOutputStream();

public byte[] transform(...) {
    scratch.reset();
    scratch.writeBytes(classfileBuffer);
    // ... dựng lại class bytes ...
    return scratch.toByteArray();
}
```

Đoạn trên **không biên dịch nguyên xi** vì dấu `...` đại diện các tham số/logic chưa khai báo. Nó dùng để chỉ ra **shared mutable state**.

Khi hai thread chạy cùng lúc:

```text
A: scratch.reset()
A: scratch.writeBytes(bytesA)
B: scratch.reset()
B: scratch.writeBytes(bytesB)
A: return scratch.toByteArray()  // có nguy cơ trả bytesB
```

Với `ByteArrayOutputStream`, các thao tác mutable không được thiết kế làm buffer chia sẻ không khóa giữa hai callback. Dù từng call luôn sinh bytes hợp lệ trong một thread, đa luồng có thể gây **corrupt bytecode**, lỗi verifier hoặc sự cố chỉ xuất hiện rất hiếm ở production.

**Cách đúng cho dữ liệu tạm:** Tạo đối tượng tại phạm vi lời gọi:

```java
// Minh họa bên trong transform(...).
java.io.ByteArrayOutputStream local =
        new java.io.ByteArrayOutputStream(classfileBuffer.length);
local.writeBytes(classfileBuffer);
byte[] candidate = local.toByteArray();

// Đây chưa phải transformation thật: chỉ tạo bản sao.
// Nếu không sửa bytecode, nên return null.
return null;
```

Mỗi callback có **`local` riêng**, không ghi đè dữ liệu của thread khác. Trong agent thật, ASM `ClassReader`, `ClassWriter`, visitor chain, cấu trúc phân tích method và offsets cũng nên được tạo riêng **cho mỗi lần transform**, trừ khi tài liệu thư viện bảo đảm một đối tượng cụ thể an toàn cho multi-thread.

### Các field đặc biệt nguy hiểm

- `byte[] workingBytes` tái sử dụng giữa các lượt callback.
- `ClassReader`/`ClassWriter` mutable giữ trong field.
- `HashMap<String, BytecodeModel>` bị cập nhật đồng thời.
- `SimpleDateFormat`, digest hoặc serializer có trạng thái mutable dùng chung mà không có hợp đồng thread safety.
- `StringBuilder` dùng chung để tạo method descriptors.
- `long calls++` trên field thường, không có atomic/synchronization.
- `ArrayList` dùng làm log buffer chung và bị append bởi nhiều thread.

Lỗi có thể biểu hiện thành `ConcurrentModificationException`, output sai, số lần gọi thiếu, exception bất thường hoặc class loading hang; **không phải lỗi nào cũng tái hiện được bằng một bài test ngắn**.

## 5. Mô hình dữ liệu an toàn: bất biến, local, concurrent

### 5.1. Biến cục bộ theo callback

Mặc định tốt nhất:

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {

    if (className == null
            || !className.startsWith("com/example/business/")) {
        return null;
    }

    // Dữ liệu tạm chỉ sống trong callback hiện tại.
    byte[] original = classfileBuffer;
    int inputLength = original.length;

    // myBytecodeLibraryTransform là hàm minh họa do agent tự viết.
    // Mỗi lần phải tạo writer/visitor riêng.
    byte[] output = myBytecodeLibraryTransform(original);

    return output;
}
```

**Đoạn code chỉ minh họa, không chạy độc lập** vì `myBytecodeLibraryTransform` không phải API JDK. Quan trọng hơn: `original` chỉ là một **tham chiếu** tới mảng input; đừng sửa mảng ấy tại chỗ. `output` phải là một mảng **mới**, biểu diễn class file hợp lệ, và các trạng thái builder cần được cách ly khỏi callback khác.

### 5.2. Cấu hình bất biến được công bố an toàn

Agent có thể cần thay đổi policy filter khi JVM chạy. Không nên vừa sửa các field `enabled`, `threshold`, `prefixes` trong một object mutable vừa để các callback đọc. Có thể dùng record bất biến và `AtomicReference`:

```java
// Minh họa trong lớp agent Java 17+.
record Config(boolean enabled, String prefix) { }

private final java.util.concurrent.atomic.AtomicReference<Config> config =
        new java.util.concurrent.atomic.AtomicReference<>(
                new Config(true, "com/example/business/"));

public byte[] transform(...) {
    Config snapshot = config.get();
    if (!snapshot.enabled()) {
        return null;
    }
    // Dùng cùng snapshot cho một lần transform.
}
```

Đây là **đoạn rời**, không phải method có đủ tham số. Ý nghĩa: mỗi callback đọc một `Config` đã được công bố an toàn, sau đó **không đổi giữa chừng** trong một lần xử lý. Agent quản trị thay cả record:

```java
config.set(new Config(false, "com/example/business/"));
```

`AtomicReference.set` có semantics visibility phù hợp. Nếu `Config` lại chứa một mutable `HashMap`, việc bản thân reference là atomic **không làm nội dung map tự thread-safe**. Bảo đảm object cấu hình **thực sự immutable** hoặc được bảo vệ đúng cách.

### 5.3. Counter dùng `LongAdder`

```java
private final java.util.concurrent.atomic.LongAdder calls =
        new java.util.concurrent.atomic.LongAdder();

// Bên trong transform:
calls.increment();
```

`LongAdder` hiệu quả cho tần suất update lớn với nhiều thread. Nhưng `calls.sum()` **không phải atomic snapshot** nếu có thread đang tăng, nên chỉ dùng theo ngữ nghĩa telemetry tổng hợp. Khi các worker đã kết thúc hoàn toàn (ví dụ `Future.get()` xong trong lab), không còn update đồng thời, tổng sẽ phản ánh các increments hoàn tất.

Nếu cần ID tăng tuần tự không trùng trên mỗi call, dùng `AtomicLong.getAndIncrement()` thay vì `LongAdder`. `LongAdder` không cấp số thứ tự cho từng event.

### 5.4. Bảng theo class dùng `ConcurrentHashMap`

```java
private final java.util.concurrent.ConcurrentHashMap<String,
        java.util.concurrent.atomic.LongAdder> counts =
        new java.util.concurrent.ConcurrentHashMap<>();

// Trong callback, sau khi lọc:
counts.computeIfAbsent(
        className, ignored ->
                new java.util.concurrent.atomic.LongAdder()
).increment();
```

Đây là mã minh họa trong một class agent có biến `className`. `computeIfAbsent` là API đồng thời hữu ích khi cập nhật histogram/tần suất. Tuy nhiên:

- Không làm việc nặng, I/O hoặc class loading phức tạp trong mapping function.
- Tránh đệ quy cập nhật lại cùng map bên trong mapping function.
- Dùng keys có kiểm soát cardinality; không ghi mọi hidden/generated class name vô hạn.
- Nếu class name có thể trùng giữa các loaders, key chỉ theo tên **không đủ** để mô tả danh tính runtime.
- Không giữ class loader/object/class ref trong map static vô hạn vì gây **class-loader leak** sau redeploy.

Trong lab chỉ theo dõi **hai internal class names đã biết**, nên số keys tối đa là 2, không có bài toán cardinality tăng vô hạn.

## 6. Đồng bộ `synchronized` có giải quyết được không?

Một phương án bảo vệ shared buffer là khóa toàn bộ `transform`:

```java
// Mẫu cần cân nhắc, không phải khuyến nghị mặc định:
public synchronized byte[] transform(...) {
    // Parse, transform, ghi log, tạo bytes...
}
```

Tính an toàn dữ liệu có thể cải thiện nhưng hậu quả về hiệu năng/nguy cơ deadlock lớn:

- Những yêu cầu nạp class **khác nhau** phải chờ nhau trên một khóa transformer toàn cục.
- Một callback cần resolve helper class trong lúc đang giữ monitor; thread khác có thể giữ class-loading lock và chờ monitor, tạo chu trình **AB–BA**.
- Nếu instrumentation của logging, class parser hoặc exporter cũng kích hoạt class loading, deadlock có thể khó tìm.
- Một callback chậm do I/O khiến hàng loạt class load xếp hàng, kéo dài startup và latency.

Đừng xem `synchronized` trên toàn callback là phương pháp duy nhất để đạt thread safety. **Ưu tiên mỗi call dùng local transform context**, cấu hình immutable, counters/maps concurrent, và khóa cực hẹp **chỉ khi thật sự cần**.

### Một chu trình deadlock khái niệm

```text
Thread A: giữ lock của transformer
    └── trong transform cần nạp Helper X
            └── chờ class-loading lock của loader L

Thread B: giữ class-loading lock của loader L
    └── nạp class khác, cần transformer lock
            └── chờ Thread A
```

**Đây là sơ đồ rủi ro**, không khẳng định tất cả loader/JVM sẽ tạo đúng chu trình ấy. Nếu thiết kế callback thu nhiều lock, phải xác định thứ tự khóa; không giữ monitor của agent khi đi vào thao tác có thể kích hoạt class loading, callback hoặc I/O không đoán trước.

## 7. Quy tắc đặc biệt: transformer đang ở trong class-loading path

Trong callback, một lời gọi Java tưởng như vô hại có thể làm loader phải nạp thêm class. Ví dụ:

```java
// Cảnh báo: đặt trong transform(...) có thể kích hoạt loading.
Class.forName("com.example.MissingHelper");
logger.debug("Transform " + className);
bytecodeLibrary.initializeAllPlugins();
```

Các dòng trên minh họa rủi ro (biến `logger` chưa khai báo), không phải code khuyên dùng. `Class.forName` còn có thể initialize class tùy overload; formatter/logging framework cũng có thể làm JVM nạp các class của chính nó.

Javadoc `ClassFileTransformer` cảnh báo đặc biệt khi biến đổi **core JDK classes** mà quá trình transform lại cần những classes ấy. Nếu quá trình transform class `C` phải load/resolve lại chính class `C`, JVM có thể ném `LinkageError` hoặc một subtype. Việc resolve lỗi có thể để lại failure được nhớ ở một symbolic reference của class khác, khiến lỗi xuất hiện về sau tại vị trí không gần callback.

Biện pháp phòng ngừa:

1. **Initialize trước** những cấu phần agent chắc chắn cần (nếu an toàn) trong `premain`/`agentmain`, tránh lazy load lần đầu trong callback.
2. **Loại trừ package của agent và helper** khỏi phạm vi transform.
3. **Không** gọi `Class.forName(className)` để “lấy class hiện tại” khi nó đang được JVM định nghĩa.
4. Thư viện bytecode nên parse từ mảng bytes đang có, không tự động đi qua class loader của ứng dụng để resolve mọi type nếu không cần.
5. Nếu cần hierarchy resolver, hiểu class-loader/module context và tránh recursion.
6. Giữ logging cực gọn; tránh đồng bộ gửi mạng ngay trong callback.
7. Không tạo thread hoặc block đợi một thread khác tải class mà chính callback đang giữ lock cần thiết.

### `ThreadLocal` có an toàn không?

`ThreadLocal` có thể tạo context riêng cho mỗi thread, nhưng không giải quyết tất cả:

- Thread được tái sử dụng để load nhiều class; state cũ có thể bị giữ lại nếu không reset.
- Một callback có thể **gọi lồng nhau** trên cùng thread (reentrancy), khiến một context dùng chung qua `ThreadLocal` bị ghi đè.
- Nếu `ThreadLocal` giữ object của custom class loader, nó có thể gây leak qua thread sống lâu.
- Cần `try/finally` và `remove()` đúng chỗ nếu dùng state tạm.

Với phần lớn transformer, **biến cục bộ per invocation** đơn giản hơn `ThreadLocal` và dễ chứng minh an toàn hơn. Dùng `ThreadLocal` khi profiling đã chỉ ra lợi ích và có kiểm tra reentrancy/lifecycle.

## 8. Bài lab Java 17+: hai thread nạp hai class, cùng transformer thống kê an toàn

Ta tạo **một Java agent** và **một application** sử dụng hai `ClassLoader` riêng. Hai thread được mở bằng `ExecutorService`, cùng chờ một `CountDownLatch`, rồi lần lượt yêu cầu nạp `TargetA` và `TargetB`.

Một transformer duy nhất lọc chính xác hai class này, tăng `LongAdder`, lưu tên vào `ConcurrentHashMap.newKeySet()` và dùng `AtomicInteger` theo dõi số callback đang hoạt động. **Transformer trả `null`**, nên không có bytecode nào bị sửa.

**Mục đích:** Đưa nhiều yêu cầu nạp class cùng đi vào một transformer object, kiểm chứng rằng shared statistics không mất dữ liệu và có thể quan sát concurrency khi JVM thực sự overlap. Lab **không tuyên bố** hai callback bắt buộc overlap ở mọi runtime/lịch trình thread.

### 8.1. Cấu trúc thư mục

```text
concurrent-transformer-demo/
├── agent.mf
├── agent-src/
│   └── demo/agent/ConcurrentAgent.java
├── app-src/
│   └── demo/app/Main.java
└── targets-src/
    └── demo/targets/
        ├── TargetA.java
        └── TargetB.java
```

Sau khi build:

```text
out/
├── agent/                      # class của Java agent
├── app/                        # class application
├── targets/                    # file .class được custom loader đọc
└── concurrent-agent.jar
```

**Không đặt `out/targets` vào runtime `-cp`**: nếu target classes xuất hiện ở classpath của application, parent delegation có thể nạp chúng theo đường khác với điều bài lab dự định kiểm chứng.

### 8.2. `targets-src/demo/targets/TargetA.java`

```java
package demo.targets;

public final class TargetA {
    public static String id() {
        return "A";
    }
}
```

### 8.3. `targets-src/demo/targets/TargetB.java`

```java
package demo.targets;

public final class TargetB {
    public static String id() {
        return "B";
    }
}
```

Mỗi target chỉ phụ thuộc `java.base`. Điều này quan trọng vì custom loader của lab lấy **platform loader làm parent**; không có ứng dụng hoặc thư viện ngoài nào cần resolve từ target classes.

### 8.4. `agent-src/demo/agent/ConcurrentAgent.java`

```java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public final class ConcurrentAgent {

    private static final LongAdder CALLBACKS = new LongAdder();

    // Set concurrent và bounded về mặt nội dung vì callback chỉ lưu A/B.
    private static final Set<String> NAMES =
            ConcurrentHashMap.newKeySet();

    private static final AtomicInteger ACTIVE = new AtomicInteger();
    private static final AtomicInteger PEAK = new AtomicInteger();

    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain domain,
                    byte[] classfileBuffer) {

                if (!"demo/targets/TargetA".equals(className)
                        && !"demo/targets/TargetB".equals(className)) {
                    return null;
                }

                int now = ACTIVE.incrementAndGet();
                PEAK.accumulateAndGet(now, Math::max);
                try {
                    CALLBACKS.increment();
                    NAMES.add(className);
                    // Không chia sẻ buffer hoặc writer mutable.
                    // Không cần sửa bytes trong thí nghiệm.
                    return null;
                } finally {
                    ACTIVE.decrementAndGet();
                }
            }
        }, false);

        System.out.println("agent: transformer registered");
    }

    public static long callbackCount() {
        return CALLBACKS.sum();
    }

    public static int distinctTargetCount() {
        return NAMES.size();
    }

    public static int activeCallbackCount() {
        return ACTIVE.get();
    }

    public static int maximumActiveCallbacks() {
        return PEAK.get();
    }
}
```

**Tại sao đúng về thread safety?**

- `CALLBACKS` là `LongAdder`, phù hợp với nhiều increment đồng thời.
- `NAMES` là set từ `ConcurrentHashMap.newKeySet()`; nhiều thread gọi `add` mà không làm hỏng cấu trúc.
- `ACTIVE.incrementAndGet()` và `decrementAndGet()` quản lý số callback đồng thời bằng thao tác atomic.
- `PEAK.accumulateAndGet(now, Math::max)` ghi lại số callback in-flight lớn nhất **mà probe này quan sát được**, không dựa vào một phép `if (now > old) old = now` dễ race.
- `finally` bảo đảm decrement ngay cả khi code trong `try` ném exception.
- Không có `byte[] working` dùng chung. Mỗi callback nhận `classfileBuffer` riêng và **không sửa** mảng ấy.
- Không gọi helper nặng hay I/O trong callback, giảm nguy cơ recursion và deadlock.
- Filter hai internal names từ đầu, nên mọi class JDK/helper khác được bỏ qua ngay.

**Điều lab không làm:** Không kiểm tra `PEAK>=2` như một điều kiện pass bắt buộc. Dù hai task được khởi động gần nhau, JVM **có thể tuần tự hóa** các pha nạp class hoặc OS có thể không scheduling để callback chồng lên nhau. `maximumActiveCallbacks()==1` trong một lần chạy không chứng minh transformer luôn single-threaded.

Nếu muốn quan sát, có thể tạm in:

```java
// Dòng minh họa đặt trong Main sau khi hai Future đã hoàn tất:
System.out.println(
        "agent: max-active=" + ConcurrentAgent.maximumActiveCallbacks());
```

Output có thể là `1` hoặc `2`, phụ thuộc môi trường và lịch trình. **Không dùng sự khác nhau này để kết luận đã có hoặc không có race trong code transformer**; trong production vẫn phải thiết kế thread-safe.

### 8.5. `app-src/demo/app/Main.java`

```java
package demo.app;

import demo.agent.ConcurrentAgent;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class Main {

    private static final class TargetLoader extends ClassLoader {
        private final Path root;

        TargetLoader(Path root) {
            // Parent không có class application/target của lab.
            super(ClassLoader.getPlatformClassLoader());
            this.root = root;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {

            // Không đọc class bất kỳ từ ổ đĩa.
            if (!"demo.targets.TargetA".equals(name)
                    && !"demo.targets.TargetB".equals(name)) {
                throw new ClassNotFoundException(name);
            }

            Path file = root.resolve(
                    name.replace('.', '/') + ".class");
            try {
                byte[] bytes = Files.readAllBytes(file);
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException e) {
                throw new ClassNotFoundException(name, e);
            }
        }
    }

    private static String loadAndCall(
            String binaryName, Path root, CountDownLatch start)
            throws Exception {

        // Hai worker chỉ bắt đầu load khi main thả latch.
        start.await();
        ClassLoader loader = new TargetLoader(root);
        Class<?> type = Class.forName(binaryName, true, loader);
        return (String) type.getMethod("id").invoke(null);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: Main <targets-class-root>");
        }

        Path root = Path.of(args[0]);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Callable<String> jobA = () -> loadAndCall(
                    "demo.targets.TargetA", root, start);
            Callable<String> jobB = () -> loadAndCall(
                    "demo.targets.TargetB", root, start);

            Future<String> a = pool.submit(jobA);
            Future<String> b = pool.submit(jobB);

            // Tạo cơ hội cho các class-load request chạy song song.
            start.countDown();

            String resultA = a.get(10, TimeUnit.SECONDS);
            String resultB = b.get(10, TimeUnit.SECONDS);

            System.out.println(
                    "app: values=" + resultA + "," + resultB);
            System.out.println(
                    "agent: callbacks=" + ConcurrentAgent.callbackCount());
            System.out.println(
                    "agent: distinct-targets=" +
                    ConcurrentAgent.distinctTargetCount());
            System.out.println(
                    "agent: active-after=" +
                    ConcurrentAgent.activeCallbackCount());
            System.out.println(
                    "agent: peak-positive=" +
                    (ConcurrentAgent.maximumActiveCallbacks() >= 1));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

**Kiểm tra thiết kế concurrency:**

1. App dùng một pool hai worker thay vì tạo thread mới trong transformer.
2. `CountDownLatch` giúp hai task bắt đầu gần nhau nhưng **không hứa** chạy song song đến callback trên mọi JVM.
3. Hai `TargetLoader` **là hai object khác nhau**; code trong callback vẫn dùng **một** transformer đã đăng ký với JVM.
4. `TargetLoader` chỉ tìm đúng hai class từ `out/targets`; các class JDK được parent `ClassLoader.getPlatformClassLoader()` xử lý.
5. `Class.forName(binaryName, true, loader)` định nghĩa/khởi tạo class mục tiêu; mỗi class `id()` không có side effect khác ngoài trả string.
6. Sau `Future.get(...)` của **cả hai** tasks, mọi callback cần thiết để load và gọi những target ấy đã hoàn tất. Đọc counter/số active lúc đó là hợp lý.
7. `a.get(10, TimeUnit.SECONDS)` và `b.get(...)` giúp test thất bại rõ khi loading kẹt; nó **không** bảo đảm một deadlock trong JVM biến mất. `shutdownNow()` yêu cầu worker dừng khi có thể, không thể giết thread đang mắc kẹt trong class loading bằng cách an toàn.
8. Không ghi các message từ bên trong callback để tránh biến thứ tự log interleaving thành “đáp án đúng” về scheduling.

### 8.6. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.ConcurrentAgent

```

Lab chỉ dùng `ClassFileTransformer` đăng ký với `canRetransform=false` và định nghĩa class mới. **Không cần** `Can-Retransform-Classes` hoặc `Can-Redefine-Classes`. Nếu thêm hai capability để thử nghiệm khác, phải tách rõ đó là phạm vi mới và kiểm tra JVM hỗ trợ, không coi chúng là tiền điều kiện của bài lab.

### 8.7. Biên dịch và chạy: Bash

Từ thư mục `concurrent-transformer-demo`:

```bash
mkdir -p out/agent out/app out/targets

# Compile agent trước.
javac -encoding UTF-8 -d out/agent \
    agent-src/demo/agent/ConcurrentAgent.java

# Đóng gói chỉ agent classes, không đóng gói target classes.
jar --create --file out/concurrent-agent.jar \
    --manifest agent.mf -C out/agent .

# Application cần agent API lúc compile vì gọi các thống kê của agent.
javac -encoding UTF-8 -cp out/agent -d out/app \
    app-src/demo/app/Main.java

# Hai target độc lập nằm ngoài runtime classpath.
javac -encoding UTF-8 -d out/targets \
    targets-src/demo/targets/TargetA.java \
    targets-src/demo/targets/TargetB.java

java -javaagent:out/concurrent-agent.jar \
    -cp out/agent:out/app \
    demo.app.Main out/targets
```

Không đặt `out/targets` trong `-cp`; nếu vô tình thêm, parent delegation có thể load target qua system loader thay vì `TargetLoader`, làm ví dụ đổi ý nghĩa. Classpath Unix-like dùng `:` khi có nhiều entries.

### 8.8. Biên dịch và chạy: Windows PowerShell

```powershell
New-Item -ItemType Directory -Force `
    -Path out/agent, out/app, out/targets | Out-Null

javac -encoding UTF-8 -d out/agent `
    agent-src/demo/agent/ConcurrentAgent.java

jar --create --file out/concurrent-agent.jar `
    --manifest agent.mf -C out/agent .

javac -encoding UTF-8 -cp out/agent -d out/app `
    app-src/demo/app/Main.java

javac -encoding UTF-8 -d out/targets `
    targets-src/demo/targets/TargetA.java `
    targets-src/demo/targets/TargetB.java

java -javaagent:out/concurrent-agent.jar `
    -cp "out/agent;out/app" `
    demo.app.Main out/targets
```

PowerShell dùng **backtick** khi xuống dòng, khác `\` ở Bash. Classpath Windows dùng `;`. Cần dùng JDK 17+ với `java`, `javac`, `jar` phù hợp. Agent JAR phải có `Premain-Class` hợp lệ và những class agent cần thiết; không đặt `TargetA/B` vào agent JAR.

### 8.9. Stdout dự kiến khi lab chạy bình thường

```text
agent: transformer registered
app: values=A,B
agent: callbacks=2
agent: distinct-targets=2
agent: active-after=0
agent: peak-positive=true
```

**Tại sao các dòng này có thể kỳ vọng ổn định?**

- Mỗi target class được yêu cầu định nghĩa **một lần** ở custom loader riêng và đều khớp filter.
- `CALLBACKS` tăng một lần cho mỗi callback đã được chọn.
- `NAMES` chỉ có hai tên và thêm an toàn đồng thời.
- Các `Future.get` hoàn tất trước khi in thống kê.
- `finally` của transformer đã giảm `ACTIVE` về 0 ở cuối mọi callback mục tiêu.
- `PEAK>=1` là đúng nếu đã có ít nhất một callback lọc trúng; không cần suy ra `PEAK==2`.

Nếu nhìn thấy thêm log từ JVM hoặc agent khác, đó là dữ liệu ngoài bài lab; bài lab giả định không có các công cụ khác ghi thêm stdout. Nếu class file thiếu hoặc path sai, `Future.get()` ném `ExecutionException` chứa nguyên nhân thay vì giả vờ các dòng thống kê đều thành công. Nếu JVM không hỗ trợ Java agent startup, chương trình không chạy được như chỉ dẫn.

**Thử kiểm tra concurrency thực:** Thêm dòng hiển thị `maximumActiveCallbacks()`; nếu thấy `2`, có bằng chứng **hai callback mục tiêu đã chồng lấn tại thời điểm đo**. Nếu thấy `1`, **không thể** suy ra callback luôn tuần tự trên các JVM; chỉ biết **lần thử này** không ghi nhận overlap. Có thể tăng số class/loader/task và lặp thử, nhưng không áp dụng `Thread.sleep` hay barrier bắt buộc ngay trong transformer production.

## 9. Vì sao ví dụ không dùng `HashMap`/`int++`?

Nếu dùng:

```java
// Không an toàn nếu nhiều callback cùng cập nhật:
private final java.util.Map<String, Integer> count = new java.util.HashMap<>();
private int total;
```

và ở callback:

```java
total++;
count.put(name, count.getOrDefault(name, 0) + 1);
```

thì:

- `total++` gồm đọc, cộng, ghi; nhiều thread có thể **lost update**.
- `HashMap` không cung cấp an toàn khi ghi đồng thời; cả cấu trúc map và kết quả có thể không nhất quán.
- `count.getOrDefault` rồi `put` không phải một thao tác nguyên tử; hai thread có thể cùng đọc giá trị cũ rồi ghi đè kết quả của nhau.
- `volatile int total` **không** biến `total++` thành phép cộng nguyên tử; `volatile` đảm bảo visibility/order phù hợp nhưng không gộp read-modify-write thành một atomic operation.

Thay bằng:

```java
private final java.util.concurrent.atomic.AtomicInteger total =
        new java.util.concurrent.atomic.AtomicInteger();

total.incrementAndGet();
```

hoặc `LongAdder` khi chỉ cần tổng tần suất. Với map histogram, dùng `ConcurrentHashMap<K,LongAdder>` và `computeIfAbsent(...).increment()` như phần 5.

### Khi nào `AtomicInteger` phù hợp hơn `LongAdder`?

- Dùng `AtomicInteger` nếu cần nhận giá trị **ngay sau phép tăng** (`incrementAndGet`) hoặc thực hiện compare-and-set.
- Dùng `LongAdder` cho bộ đếm tần suất cập nhật cao, khi `sum()` có thể không phải atomic snapshot trong lúc updates diễn ra.
- Không dùng `LongAdder.sumThenReset()` như phép **chốt sổ nguyên tử** khi nhiều transformer vẫn increment, vì update đồng thời với reset có thể khiến số liệu không được chia cửa sổ đúng.
- Với counter xuất metrics, ghi nhận process restart/reset nếu hệ giám sát tính rate từ số tích lũy.

## 10. Không nên cache transform output chỉ theo `className`

Một optimization dễ sai là:

```java
// Ví dụ kiến trúc chưa đủ điều kiện an toàn:
ConcurrentHashMap<String, byte[]> cache = new ConcurrentHashMap<>();
```

Tại sao key theo tên chưa đủ?

1. **Class loader:** `com/example/Widget` của plugin A và plugin B có thể là hai type khác nhau, source bytes khác.
2. **Module layer:** một binary name có thể có nhiều bối cảnh module/loader.
3. **Class-file version:** hai bản cùng tên có thể khác major version hoặc dependencies.
4. **Transformer configuration:** enabled/disabled rules, probe version, sampling mode có thể đổi.
5. **Input bytes:** redefine có thể đưa bytes mới cho cùng class; một key tên cũ có thể trả output stale.
6. **Reentrancy:** một cache miss có thể gọi hàm sinh bytes, hàm đó load class rồi lại đụng cache; mapping function không được recursion tùy ý.

Nếu thật sự cần cache, key cần mô tả đầy đủ input **và** context, giới hạn kích thước, tránh giữ mạnh classloader của ứng dụng. Đối với instrumentation vốn đã hoạt động trước JVM define class, **đừng dùng global cache** nếu chưa đo chứng minh nó cần thiết và có test trên redeploy, redefine, multi-loader.

### Không sửa `classfileBuffer` và trả lại cùng mảng

Javadoc yêu cầu mảng bytes đầu vào không được thay đổi. Một transformer nên:

```java
// Minh họa trong callback:
if (!shouldTransform(className)) {
    return null;
}
byte[] generated = generateNewClassFile(classfileBuffer);
return generated;
```

`shouldTransform` và `generateNewClassFile` là **hàm do agent tự cung cấp**, không phải API JDK. Nếu không sửa gì, hãy `return null`; nếu sửa, output phải là một **class file hợp lệ** với stack maps, metadata, method descriptors và control flow phù hợp. Kỹ thuật “dùng mảng input làm scratch để bớt allocation” có thể phá cả chaining của các transformer khác, kể cả khi agent chỉ có một thread.

## 11. Lock ordering, recursion và class initialization

Callback chạy trong quá trình class definition, trước khi JVM verify/apply class. Tại thời điểm đó:

- Một số class hoặc helper mà transformer muốn dùng **chưa hề được nạp**.
- Một class initializer có thể chạy khi tool vô tình tham chiếu static field/phương thức của class mới.
- Loader lock có thể đang được giữ.
- Logging/exporter có thể cần tải class khác và tạo ra chuỗi phụ thuộc.
- `ClassFileTransformer` có thể bị gọi lại trong một luồng loading khác, hoặc một callback khác của cùng agent xuất hiện ở thời điểm giao nhau.

Vì vậy không nên:

```text
transform(A):
    giữ monitor của agent
    gọi một network exporter đồng bộ
    chờ một worker nạp class B
    worker phải lấy monitor của agent để transform(B)
```

Đây là ví dụ **mô hình deadlock**, không phải chương trình chạy. Nguyên tắc tốt:

- **Không block** trong callback vì HTTP timeout, queue đầy hoặc chờ latch của code bên ngoài.
- Không giữ monitor quanh việc gọi class loader hoặc reflection nặng.
- Khởi tạo parser/formatter/helper trước khi nhiều application threads nạp class, khi việc đó an toàn.
- Filter package agent/helpers để tránh tự instrument.
- Không ghi log chứa toàn bộ class bytes, user data hoặc class name có cardinality quá lớn.
- Kiểm tra riêng bytecode output, đừng dựa vào việc transformer callback hoàn tất để tuyên bố JVM đã định nghĩa class.

### Reentrant callback và guard

Một `ThreadLocal<Boolean>` đôi khi dùng để đánh dấu “đang transform” trên cùng thread:

```java
// Minh họa ý tưởng, không phải transformer hoàn chỉnh:
private static final ThreadLocal<Boolean> IN_TRANSFORM =
        ThreadLocal.withInitial(() -> false);

if (IN_TRANSFORM.get()) {
    return null;
}
IN_TRANSFORM.set(true);
try {
    // Transformation không tự load những class bị nó đang xử lý.
} finally {
    IN_TRANSFORM.remove();
}
```

Guard như vậy **không** làm dữ liệu dùng chung giữa các thread tự an toàn, cũng không ngăn callback song song ở **hai thread khác nhau**. Nếu nested callback thực sự có thể xảy ra, thiết kế guard per thread phải xem xét `remove()` và state bên ngoài scope để không xóa nhầm state của outer callback. Một boolean đơn giản có thể chưa đủ với các trường hợp nesting phức tạp. **Ưu tiên filter và chuẩn bị dependencies an toàn trước**.

## 12. `removeTransformer` và thay đổi cấu hình khi callback đang chạy

Một giả định sai:

```text
removeTransformer(t) trả true
⇒ tất cả transform đang chạy đã dừng
⇒ an toàn xóa toàn bộ state/helper của t ngay
```

Javadoc không bảo đảm thế. Do tính chất multi-threaded class loading, transformer **có thể còn nhận callback** sau khi được remove. Một yêu cầu đã đi sâu vào pipeline có thể đang dùng object. Vì vậy:

- `removeTransformer` là thao tác **unregister cho sự kiện tương lai**, không phải một barrier chờ toàn bộ callback kết thúc.
- Không lập tức đóng/giải phóng mọi tài nguyên mà callback cũ có thể dùng rồi kỳ vọng callback không xảy ra nữa.
- Nếu cần ngừng chức năng, dùng **cờ `enabled` được công bố an toàn**, và callback đọc snapshot, có thể trả `null` nhanh.
- Nếu cần shutdown sạch, dùng một giao thức riêng để theo dõi **in-flight callbacks**, chờ có giới hạn ngoài callback khi an toàn, và quản lý tài nguyên theo lifecycle của agent.
- `AtomicInteger ACTIVE` ở lab là công cụ **đo**, không phải cơ chế đồng bộ dừng; kiểm tra `ACTIVE==0` một lần không bảo đảm callback mới không thể tới sau đó.
- Loại trừ bridge/helper khỏi biến đổi và giữ ABI ổn định nếu class đã instrument đang tiếp tục gọi helper sau khi transformer bị remove.

Đặc biệt, **gỡ transformer không hoàn nguyên bytecode** đã được JVM áp dụng. Một class đã instrument có thể tiếp tục gọi helper dù transformer không được đăng ký nữa.

## 13. Nếu có `retransformClasses` đồng thời với class loading

Với `Instrumentation.retransformClasses`, JVM nhận các `Class<?>` đã nạp và đưa chúng qua chuỗi tương ứng:

- Java transformer đăng ký `canRetransform=false` **không được gọi lại** trong retransform; output trước đó được tái dùng.
- Java transformer đăng ký `canRetransform=true` có callback mới cho những class retransform áp dụng.
- Với `redefineClasses`, cả capable và incapable đều có callback thích hợp.
- Những callbacks có thể xuất hiện gần thời điểm các thread khác đang nạp class mới hoặc agent khác đang xử lý loại sự kiện khác. Không dùng một global mutable writer cho cả class load/redefine/retransform.

Các trạng thái như `classBeingRedefined != null` chỉ cho biết class đã tồn tại; **không tự phân biệt** retransform với redefine. Nếu agent muốn ghi log event type, lấy ngữ cảnh từ chính tầng gọi API, không đoán dựa trên tham số callback.

**Phân biệt dữ liệu có thể chia sẻ:**

| Dữ liệu | Chính sách |
| --- | --- |
| Bộ bytes hiện tại của một callback | Local/read-only |
| Class model, bytecode writer/visitor | Local cho mỗi transform |
| Immutable config | Share qua final/atomic publication |
| Counters | `LongAdder`/`AtomicLong`, không `long++` |
| In-flight callbacks | `AtomicInteger` và lifecycle giao thức riêng |
| Per-class stats | `ConcurrentHashMap` với bounded keys |
| Class loader/class references | Tránh giữ mạnh lâu dài; có cleanup/weak strategy |
| Queue telemetry | Bounded/nonblocking nếu nằm trong hot path |
| Exporter HTTP và serializer nặng | Worker độc lập, không chạy đồng bộ trong transform |

## 14. Kiểm thử race condition thay vì chỉ kiểm thử happy path

Một lần chạy thấy `callbacks=2` không chứng minh mọi phép biến đổi dùng shared state đều an toàn. Cần test có chủ đích:

1. **Nhiều class khác nhau:** Nạp nhiều classes trong các threads/loader khác nhau.
2. **Cùng tên ở nhiều loader:** Đảm bảo không trộn output/counters nếu identity khác nhau.
3. **Đăng ký trước/sau:** Cài transformer trước khi nạp target; không đếm class load đã xảy ra trước registration.
4. **Load trong khi đổi config:** Sử dụng immutable snapshots, test toggling enabled/filters.
5. **Remove trong lúc load:** Không giả định callback dừng lập tức; phải có shutdown policy.
6. **Transformer throw:** Mọi shared-state counters/active phải được cleanup trong `finally`.
7. **Exporter chậm:** Không để callback block hoặc cố log từ khi class loader lock đang được giữ.
8. **Bytecode buffer độc lập:** So hashes/output của cùng input qua nhiều parallel runs.
9. **Reentrancy:** Dùng một helper có khả năng load class để thử guard/exclusion trong staging.
10. **JVM/JDK khác nhau:** Một lần không overlap không chứng minh trên JVM khác cũng tuần tự.

### Công cụ đo phù hợp

- Thread dumps/JFR để nhìn blocking, lock contention, class loading events và stack traces.
- JMH khi benchmark các hot-path operations của transformer helper (tách khỏi đầy đủ class loading).
- Stress tests với nhiều class/loader và repeated JVM restarts, không chỉ chạy một lần.
- Metrics có giới hạn: callback count, class transform latency, errors, queue drops, active/peak callbacks.
- Classfile verifier và runtime tests nếu transformer thật sự trả bytes mới.

Đừng ngẫu nhiên thêm `Thread.sleep()` trong production transformer để “dễ thấy overlap”; nó làm chậm startup và có thể đẩy JVM vào trạng thái timeout. Bài lab không bắt buộc overlap vì nó kiểm tra **cách viết an toàn**, không kiểm tra một guarantee lịch trình thread.

### Một tình huống test đặc biệt

Nếu muốn tái hiện lỗi shared buffer, hãy dùng một test riêng khởi chạy **nhiều luồng gọi một helper transform thuần túy** trên hai byte arrays khác nhau, so output hashes. Test này chứng minh tính thread-safe của helper/bytecode generation **dưới cách gọi nhân tạo**, nhưng không phải bằng chứng JVM đã gọi `ClassFileTransformer` đồng thời. Cần phân biệt rõ *unit stress* với *integration stress*.

## 15. Checklist thiết kế transformer thread-safe

1. **Filter class sớm:** Chỉ xử lý những class/package thực sự thuộc phạm vi.
2. **Input bất biến:** Không sửa `classfileBuffer` tại chỗ.
3. **Builder per invocation:** Không chia sẻ mutable ClassWriter/ClassReader/visitor/scratch buffer.
4. **Immutable config snapshot:** Một lần transform dùng một phiên bản policy ổn định.
5. **Concurrent counters đúng nghĩa:** `LongAdder` cho aggregate; `AtomicInteger/AtomicLong` cho giá trị cần atomic.
6. **Concurrent map có kiểm soát:** `computeIfAbsent` nhỏ, không recursion, không I/O.
7. **Không dùng global `HashMap` hoặc `ArrayList` mutable** nếu có writer đồng thời mà không có đồng bộ đúng.
8. **Hạn chế khóa:** Không `synchronized` toàn callback trừ khi thật sự chấp nhận serialization và đã phân tích lock order.
9. **Tránh class-loading recursion:** Exclude agent/helpers, kiểm tra các dependency được load bởi chính transformer.
10. **Không block network:** Dùng worker và bounded event queue nếu phải ghi telemetry.
11. **Không giữ classloader vô hạn:** Cẩn thận static map/cache trong agent bootstrap sống lâu.
12. **Quản lý remove/shutdown:** Callback có thể tới sau `removeTransformer`; state/resources phải có lifecycle đúng.
13. **Phân biệt load/redefine/retransform:** `canRetransform=false` không callback khi retransform nhưng vẫn callback khi redefine.
14. **Quan sát kết quả thực:** Callback được gọi không chứng minh bytes đã được JVM chấp nhận.
15. **Kiểm tra đầy đủ concurrency:** Multi-loader, multi-thread, config changes, exceptions, reentrancy và JVM versions.
16. **Không nhầm diagnostics với business invariants:** Counter `LongAdder.sum()` là metric, không phải transaction ledger.
17. **Đo overhead:** Allocation, CPU, startup, class loading latency, safepoint/GC và lock contention.
18. **Bảo toàn Java semantics:** Nếu sinh bytecode thật, kiểm tra method return/throw, stack maps, access/module và đúng class identity.
19. **Giữ đủ chẩn đoán khi lỗi:** Ghi class name/loader/category một cách giới hạn; không dump dữ liệu nhạy cảm.
20. **Có rollback:** Một lỗi instrumentation không nên buộc debug trong môi trường thiếu artifact gốc; chuẩn bị phương án restart/redefine được kiểm chứng.

## 16. Các lỗi thường gặp

| Dấu hiệu | Có thể do | Hướng xử lý |
| --- | --- | --- |
| Lúc chạy nhanh được, lúc `VerifyError` | Shared writer/buffer làm lẫn output class bytes | Tạo writer và buffer theo invocation, verify output |
| `callbacks` nhỏ hơn số class thực tế | Lost increments do `int++`, hoặc class bị filter/đăng ký muộn | Dùng atomic/LongAdder; kiểm tra chính xác phạm vi |
| `ConcurrentModificationException` trong map | `HashMap`/`ArrayList` bị update đồng thời | Dùng collection concurrent hoặc thiết kế immutable snapshots |
| Startup chậm khi nhiều class nạp | `synchronized transform`, I/O hoặc logging nặng | Thu nhỏ critical path, local context, tách exporter |
| JVM kẹt khi load một class | Chu trình loader lock + transformer monitor hoặc recursive load | Thread dump/JFR, loại bỏ lock nesting |
| `NoClassDefFoundError` lúc transform | Agent cố resolve helper/class chưa có, loader mismatch | Chuẩn bị dependency, loại trừ agent packages |
| `ClassCircularityError` | Recursive class loading qua transformer/helper | Tránh gọi lại class đang định nghĩa |
| Heap tăng sau hot redeploy | Static map giữ `Class<?>` hoặc `ClassLoader` cũ | Weak reference/eviction và lifecycle cleanup |
| Mất event dù counter callback đúng | Bounded queue drop hoặc exporter lỗi | Theo dõi accepted/dropped/exported riêng |
| `removeTransformer` rồi vẫn thấy callback | JVM multi-threaded class loading | Theo Javadoc có thể xảy ra; shutdown defensively |
| Không thấy overlap trong một lần test | Scheduling hoặc loader lock serializes workload | Không kết luận luôn single-thread; test nhiều cấu hình |
| Trùng probe sau redefine | Transformer không idempotent, cache output sai version | Kiểm tra bytes/schema và marker/probe placement |
| Sai class sau cache hit | Cache chỉ theo binary name, bỏ loader/config/input | Thiết kế key đầy đủ hoặc bỏ cache |
| `ThreadLocal` giữ state cũ | Thread reuse, thiếu `finally/remove` | Cleanup theo scope, ưu tiên local variables |
| Bytecode hợp lệ nhưng nghiệp vụ sai | Thay control flow, exception path hoặc helper semantics | Runtime integration tests và rollout có kiểm soát |

## 17. Câu hỏi tự kiểm tra

**1.** Vì sao cùng `ClassFileTransformer` có thể được nhiều thread gọi?  
**Đáp:** JVM có thể nạp nhiều class trên nhiều thread/loader; registration không tạo khóa toàn cục bảo đảm tất cả callbacks được tuần tự hóa.

**2.** Class loader không parallel capable có bảo đảm transformer của toàn JVM single-threaded không?  
**Đáp:** Không. Các loader **khác nhau** vẫn có thể tiến hành loading độc lập; một loader khác có thể parallel capable.

**3.** `long calls++` có an toàn khi hai callback đồng thời không?  
**Đáp:** Không. Nó là read-modify-write không nguyên tử; dùng `AtomicLong` hoặc `LongAdder` theo mục tiêu.

**4.** `volatile long calls` có sửa được lost update khi `calls++` không?  
**Đáp:** Không. `volatile` cải thiện visibility nhưng `++` vẫn không phải thao tác nguyên tử.

**5.** Vì sao không giữ một ASM ClassWriter trong field transformer?  
**Đáp:** Nó là mutable context của một class; hai callback có thể cùng ghi và trộn nội dung/labels/constant pool.

**6.** `ConcurrentHashMap.newKeySet()` khác `HashSet` ở đâu trong ví dụ?  
**Đáp:** Nó hỗ trợ thao tác `add` concurrent an toàn cho set tên class; `HashSet` mutable thường không an toàn khi nhiều writer đồng thời.

**7.** `LongAdder.sum()` có phải atomic snapshot khi các callback vẫn tăng không?  
**Đáp:** Không. Khi các callback đã hoàn tất (như sau `Future.get`), tổng thống kê ổn định.

**8.** `maximumActiveCallbacks()==1` trong một lần chạy có chứng minh JVM luôn serializes transformers không?  
**Đáp:** Không. Chỉ nói lần test đó không quan sát overlap; scheduler/loader/JVM có thể khác.

**9.** Vì sao `synchronized transform` có thể làm chậm startup?  
**Đáp:** Nó buộc mọi callback trên cùng object tranh một monitor, dù xử lý các class khác nhau.

**10.** `removeTransformer` có phải barrier bảo đảm callback không còn xảy ra?  
**Đáp:** Không. Javadoc cảnh báo callback có thể đến sau khi removal do multi-threaded class loading.

**11.** Một `ClassFileTransformer` luôn được gọi lại khi retransform nếu đăng ký `canRetransform=false`?  
**Đáp:** Không. Output của transformer incapable được tái dùng, callback không chạy; nhưng khi redefine, callback áp dụng vẫn chạy.

**12.** Tại sao `className` không đủ để định danh class trong cache?  
**Đáp:** Cùng tên có thể tồn tại ở nhiều defining loaders, module contexts và phiên bản bytes khác.

**13.** Có nên gọi `Class.forName(className)` ngay trong `transform` để biết class đang load?  
**Đáp:** Không. Nó có thể kích hoạt loading/initialization lặp, recursion hoặc linkage errors.

**14.** Dùng `ThreadLocal` có thay thế toàn bộ đồng bộ cho shared fields không?  
**Đáp:** Không. Nó chỉ cách ly state theo thread; còn reentrancy, lifecycle và shared fields cần giải quyết riêng.

**15.** Nếu transformer ném exception, có nên bỏ bước decrement active count?  
**Đáp:** Không. Đưa decrement vào `finally` để counters/lifecycle không bị sai.

**16.** Bài lab trả `null` có nghĩa JVM đã được instrument phương thức `id()` không?  
**Đáp:** Không. Callback chỉ quan sát và ghi stats; không thay class bytes.

**17.** Nếu code agent tạo bytes mới trong nhiều thread, nguyên tắc nào quan trọng nhất?  
**Đáp:** Mỗi invocation có bytecode builder và state tạm riêng; không sửa buffer input, output phải hợp lệ và không phụ thuộc shared mutable state không bảo vệ.

**18.** Khi queue telemetry đầy, có nên `put` và block trong callback không?  
**Đáp:** Thường không. Nó giữ lâu class-loading path và có thể gây latency/deadlock; dùng bounded nonblocking `offer` và drop policy nếu telemetry best effort.

**19.** Khi không cần cache output có nên dùng global map để “tăng hiệu năng” không?  
**Đáp:** Không. Cache thêm complexity, memory retention, stale state và loader identity bugs; chỉ làm sau đo lường và test.

**20.** Callback đã log thành công có nghĩa class đã được JVM verify/install?  
**Đáp:** Không. JVM kiểm tra/cài đặt bytes sau chuỗi transformer; cần quan sát kết quả thao tác và runtime behavior.

## 18. Tài liệu tham khảo chính thức

- [JDK 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): hợp đồng `transform`, callback trước khi JVM định nghĩa class, chaining, `null`, `IllegalClassFormatException`, lưu ý về class circularity.
- [JDK 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `removeTransformer` và cảnh báo callback có thể còn diễn ra sau removal do class loading đa luồng; redefine/retransform.
- [JDK 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `getClassLoadingLock` và `registerAsParallelCapable`.
- [JDK 17 — `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `newKeySet`, `computeIfAbsent` và thao tác concurrent.
- [JDK 17 — `LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counters có contention và giới hạn của `sum`.
- [JDK 17 — `AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic increment/decrement/accumulate.
- [JDK 17 — `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): phối hợp thời điểm các worker bắt đầu.
- [JDK 17 — `Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get` và bảo đảm memory visibility khi worker kết thúc.
- [JLS 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java memory model, visibility, happens-before và races.
- [JVMS 17 — Loading, Linking and Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class loading/definition, identity và loader constraints.

**Ghi nhớ:** Một transformer có thể xử lý các yêu cầu class loading **từ nhiều thread** trong cùng khoảng thời gian. Khóa của một class loader không bảo đảm callback trên **toàn JVM** được tuần tự. Giữ bytecode builder và scratch state **theo từng invocation**, dùng cấu hình **immutable snapshot**, bộ đếm/collections **concurrent** khi chia sẻ, tránh I/O và khóa dài trong callback, và test với nhiều class/loader/thread. Bài lab xác minh trạng thái đúng nhưng **không giả định** mọi lần chạy đều quan sát `PEAK==2`.