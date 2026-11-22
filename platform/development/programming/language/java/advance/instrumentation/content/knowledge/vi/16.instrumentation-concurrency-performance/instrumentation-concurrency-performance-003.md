# Bảo vệ trạng thái chia sẻ mà không khóa kéo dài đường nạp lớp

**Java Instrumentation** thường được cài ở vị trí nhạy cảm: khi JVM chuẩn bị định nghĩa, redefine hoặc retransform một class, nó gọi `ClassFileTransformer.transform(...)`. Callback đó có thể chạy ngay trong đường **class loading**, nơi class loader, VM và nhiều thread khác đang phối hợp định nghĩa, liên kết và khởi tạo các lớp. Một agent muốn đếm số lần biến đổi, lưu cấu hình lọc, gom telemetry hoặc cache kết quả cần **trạng thái chia sẻ an toàn cho nhiều thread**; nhưng nếu bảo vệ state bằng một khóa lớn, giữ khóa trong lúc ghi log, truy cập mạng hoặc tải helper class thì chính agent có thể làm chậm hoặc khóa chéo đường nạp lớp.

Chủ đề bài này là **“Bảo vệ trạng thái chia sẻ mà không khóa kéo dài đường nạp lớp”**, thuộc nhóm *Đồng thời và hiệu năng*. Mục tiêu không phải tuyên bố mọi thao tác đều “lock-free”, mà là thiết kế để **callback không giữ khóa do agent tự tạo trong thời gian dài**, đồng thời vẫn có tính đúng đắn về memory visibility, atomic publication và thống kê khi nhiều lớp đang được load song song.

Cách tiếp cận thực tiễn:

- **Cấu hình đọc nhiều, cập nhật ít:** công bố một *immutable snapshot* qua `AtomicReference`.
- **Counter được nhiều callback cập nhật:** dùng `LongAdder` hoặc primitive atomics theo đúng tính chất cần đo; không dùng `count++` trên biến chia sẻ.
- **Tra cứu theo tên class:** tiền khởi tạo dữ liệu nhỏ, cố định trước lúc đăng ký transformer; nếu dùng `ConcurrentHashMap`, chỉ thực hiện những phép toán ngắn.
- **Telemetry phức tạp:** đưa ra khỏi callback, có giới hạn hàng đợi và backpressure/drop policy; không đồng bộ I/O dưới class-loading lock.
- **An toàn class loader:** không gọi lại loader để nạp chính lớp đang transform; tránh phụ thuộc vòng và không giữ `Class<?>`/`ClassLoader` mạnh vô thời hạn.
- **Kiểm chứng:** chạy nhiều thread nạp lớp song song, so sánh kết quả đếm sau khi các thread hoàn tất, thử update policy trong khi callback có thể đang chạy.

Một Java agent **biên dịch với `javac --release 17`** ở phần thực hành minh họa mẫu thiết kế này bằng `AtomicReference<Set<String>>`, `ConcurrentHashMap<String,LongAdder>` và hai thread nạp các lớp mục tiêu đồng thời.

## 1. Vì sao callback instrumentation là đường chạy nhạy cảm?

Với Java agent có `premain`:

~~~text
JVM khởi động
    |
    v
Agent được nạp, gọi premain(...)
    |
    +--> khởi tạo cấu hình, helper, counters
    |
    +--> instrumentation.addTransformer(...)
    |
Ứng dụng / framework / plugin yêu cầu class X
    |
    v
Class loader tìm class bytes / defineClass
    |
    v
JVM gọi transformer.transform(..., className, classfileBuffer)
    |      Có thể đang có khóa/thao tác class loading liên quan.
    |      Cùng transformer instance có thể xử lý nhiều class.
    |
    v
JVM xác minh và định nghĩa class từ bytes cuối
    |
    v
Code ứng dụng tiếp tục
~~~

Đặc tả `ClassFileTransformer` nêu rằng callback được gọi khi **load, redefine hoặc retransform**, trước khi class bytes cuối được xác minh/áp dụng. API không cam kết callback sẽ chỉ chạy trên một thread cố định hoặc các callback khác không xảy ra đồng thời. Vì vậy **không được giả định một instance transformer có quyền truy cập độc quyền các fields của nó**.

Cần lưu ý phạm vi của phát biểu về khóa: **không phải mọi lần `transform` trên mọi JVM đều giữ chính xác cùng một monitor**. Với `ClassLoader.loadClass(...)` mặc định, loader đồng bộ hóa trên khóa từ `getClassLoadingLock(name)` trong quá trình tải; parallel-capable class loaders có thể dùng khóa theo tên lớp, còn loader không parallel-capable thường khóa trên chính loader. JVMTI và đường redefine/retransform có cơ chế đồng bộ khác. Điểm thiết kế là **callback có thể nằm trên critical path của việc nạp lớp**, nên mọi chờ đợi trong đó có rủi ro lan rộng.

### Một lỗi nhỏ trong callback có thể khuếch đại

Nếu một callback mất 5 ms vì gọi logger đồng bộ, những class được định nghĩa nối tiếp bởi một loader có thể chịu thêm độ trễ. Nếu callback giữ một monitor toàn cục trong 5 ms và nhiều thread cùng chờ monitor ấy, độ trễ tổng thể có thể còn cao hơn. **Không phải overhead nào cũng tuyến tính**: lock contention, JIT warmup, scheduling và class loading của helper làm chi phí khó dự đoán.

Vì thế, đo hiệu năng của agent nên xét **p50/p95/p99 thời gian callback** và **thời gian startup/class-load của ứng dụng**, không chỉ tổng số event đã thu được.

## 2. Ba rủi ro khác nhau: data race, contention và deadlock

### 2.1. Data race làm sai trạng thái

Một ví dụ sai:

~~~java
private static long callbacks;

@Override
public byte[] transform(Module module, ClassLoader loader, String name,
        Class<?> old, java.security.ProtectionDomain domain, byte[] bytes) {
    callbacks++;  // SAI: phép đọc-cộng-ghi không atomic.
    return null;
}
~~~

Đây chỉ là **mảnh code minh họa trong ClassFileTransformer**, không phải chương trình độc lập. Nếu hai thread đồng thời thực hiện `callbacks++`, một cập nhật có thể bị mất. Đánh dấu `callbacks` là `volatile` **chỉ giải quyết visibility của đọc/ghi riêng lẻ**, không biến phép `++` thành atomic.

### 2.2. Dùng một monitor lớn có thể đúng số liệu nhưng nghẽn đường nạp lớp

Cách sau có thể tránh mất cập nhật, nhưng gây rủi ro về thời gian:

~~~java
private final Object globalLock = new Object();
private final java.util.Map<String, Long> counts = new java.util.HashMap<>();

void recordDangerously(String className) {
    synchronized (globalLock) {
        counts.merge(className, 1L, Long::sum);
        writeToRemoteMonitoringService(className); // SAI: I/O dưới lock.
    }
}
~~~

Đây là **mảnh code phản ví dụ**; `writeToRemoteMonitoringService(...)` là đại diện cho một tác vụ có thể chậm hoặc ném lỗi. Mọi callback muốn ghi thống kê có thể phải chờ cùng `globalLock`, kể cả khi chúng xử lý các class khác nhau.

Không phải từ khóa `synchronized` tự nó sai. **Khóa ngắn, phạm vi hẹp** đôi khi là giải pháp đúng cho cấu trúc cần một thao tác nguyên tử. Vấn đề là giữ monitor trên **đường nạp lớp trong khi chờ disk/network, logger, future, callback người dùng hoặc một class loader khác**.

### 2.3. Lock inversion: từ chậm thành deadlock

Xét hai khóa:

- `L`: khóa liên quan tới class loading của loader (hoặc thao tác JVM đang định nghĩa lớp).
- `M`: khóa của hệ thống telemetry do agent tạo.

Một chu trình chờ có thể xuất hiện:

~~~text
Thread A: giữ L trong lúc tải class X
           |
           +-- transform(X) muốn lấy M
                                  ^
                                  |
Thread B: giữ M trong lúc xử lý log
           |
           +-- gọi code cần tải X hoặc lớp khác qua L
                                  |
                     hai thread chờ nhau
~~~

Đây là **mô hình nguy cơ**, không phải cam kết tất cả JVM đều deadlock với đúng tên khóa đó. Một logger có thể tải class lần đầu, một serializer có thể nạp provider, hoặc một configuration manager có thể dùng plugin class loader. Nếu agent đang giữ monitor M rồi gọi các thành phần này, vòng phụ thuộc có thể trở nên khó chẩn đoán.

**Nguyên tắc an toàn hơn:** tránh thêm khóa toàn cục và lời gọi blocking vào callback; nếu cần công việc tốn thời gian, chuyển nó sang giai đoạn chuẩn bị hoặc consumer bất đồng bộ với giới hạn rõ ràng.

## 3. Chọn cấu trúc đồng thời đúng mục đích

| Yêu cầu | Công cụ phù hợp | Điều cần nhớ |
| --- | --- | --- |
| Một cờ bật/tắt, chỉ đọc tại callback | `volatile boolean` hoặc `AtomicBoolean` | `volatile` đủ cho một giá trị đơn; không tự bảo vệ nhiều fields liên quan |
| Cập nhật **cả bộ rule** và công bố nhất quán | `AtomicReference<ImmutablePolicy>` | Xây policy hoàn chỉnh trước, swap một reference |
| Counter tổng, nhiều thread cập nhật | `LongAdder` | Throughput tốt khi contention; `sum()` không phải atomic snapshot trong khi có update |
| Counter dùng để điều khiển giới hạn chính xác | `AtomicLong` với `compareAndSet` hoặc cấu trúc điều phối thích hợp | `LongAdder` không phù hợp để cấp số thứ tự/giới hạn nghiêm ngặt |
| Tra cứu metadata/counter theo class name | `ConcurrentHashMap<K,V>` | Tránh remapping function có I/O, lock hoặc class loading |
| Hàng đợi telemetry | Bounded queue với `offer`/drop policy | Không dùng `put` chờ vô hạn ở callback |
| Cache theo class loader có vòng đời động | Thiết kế key/reference phù hợp, có cleanup | Strong references có thể ngăn class unloading |
| Một thao tác đa-bước thực sự cần atomicity | Lock rất ngắn hoặc một immutable state object | Không giữ lock qua JDK/class-loader/user-code callbacks |

**Không có một lựa chọn vạn năng.** Ví dụ `LongAdder` rất tốt cho metrics nhưng không nên dùng để sinh “ID callback duy nhất” theo thứ tự toàn cục. `AtomicReference` rất tốt để công bố rule set mới nhưng không làm cho mọi thành phần bên trong object trở nên immutable nếu người viết vẫn sửa mutable collections sau khi công bố.

## 4. AtomicReference: công bố chính sách dưới dạng snapshot bất biến

Một transformer có thể phải cập nhật allowlist/denylist trong runtime. Nếu chia chính sách thành nhiều biến sửa riêng lẻ:

~~~java
volatile String packagePrefix = "demo/app/";
volatile boolean allowAlpha = true;
volatile boolean allowBeta = true;
~~~

thì callback có thể thấy **tổ hợp trung gian** trong lúc admin thread cập nhật các biến. Mỗi biến có thể visibility đúng nhưng **toàn bộ policy không phải một giao dịch**.

Mẫu tốt hơn:

~~~java
record Policy(java.util.Set<String> allowedClassNames, boolean enabled) {
    Policy {
        allowedClassNames = java.util.Set.copyOf(allowedClassNames);
    }
}

private static final java.util.concurrent.atomic.AtomicReference<Policy> POLICY =
        new java.util.concurrent.atomic.AtomicReference<>(
                new Policy(java.util.Set.of("demo/app/Alpha", "demo/app/Beta"), true));

static void replacePolicy(java.util.Set<String> allow, boolean enabled) {
    Policy next = new Policy(allow, enabled); // Chuẩn bị đầy đủ ngoài callback.
    POLICY.set(next);                         // Công bố một lần.
}
~~~

Đây là **mảnh code minh họa cần đặt trong class thích hợp**, không phải chương trình đầy đủ. Java `record` có từ Java 16, nên cú pháp phù hợp Java 17. Constructor phòng thủ dùng `Set.copyOf` tránh việc caller thay nội dung set sau khi công bố.

Trong transformer:

~~~java
Policy p = POLICY.get();  // Một snapshot nhất quán cho callback này.
if (!p.enabled() || !p.allowedClassNames().contains(className)) {
    return null;
}
// Tiếp tục xử lý nếu cần.
~~~

Lợi ích:

1. Mỗi callback đọc **một reference nhất quán** rồi dùng policy đó trong cả lượt.
2. Admin có thể tạo policy mới mà **không khóa toàn bộ callbacks**.
3. `AtomicReference.set/get` cung cấp các bảo đảm memory visibility cần thiết để publish cấu trúc đã chuẩn bị xong.
4. Khi admin thay policy giữa lúc callback đang chạy, callback được phép hoàn tất trên **snapshot cũ**. Nếu nghiệp vụ đòi hỏi “từ thời điểm T, không callback nào còn dùng policy cũ”, cần một giao thức quiescence/versioning phức tạp hơn; `AtomicReference` riêng lẻ không tạo hàng rào chờ các callback cũ kết thúc.

### Khi dùng AtomicReference.updateAndGet

Có thể xây trạng thái mới từ trạng thái cũ:

~~~java
POLICY.updateAndGet(old -> new Policy(
        java.util.Set.of("demo/app/Alpha"), old.enabled()));
~~~

**Chú ý:** hàm cập nhật trong một vòng CAS **có thể bị gọi lại** nếu cạnh tranh. Nó phải **thuần, ngắn, không làm side effect**, không gửi event telemetry hoặc tự nạp class. Với cấu hình phức tạp, xây sẵn snapshot rồi dùng `set` hoặc `compareAndSet` có kiểm soát ngoài callback.

## 5. LongAdder: đếm nhiều callback mà không khóa dài

`LongAdder` được thiết kế cho tình huống nhiều thread cùng tăng một counter; khi contention tăng, nó có thể phân tán cập nhật vào nhiều ô nội bộ. Điều này thường có throughput tốt hơn một `AtomicLong` duy nhất dưới tranh chấp cao, đánh đổi thêm bộ nhớ và việc đọc tổng phải cộng các ô.

Ví dụ:

~~~java
private static final java.util.concurrent.atomic.LongAdder CALLBACKS =
        new java.util.concurrent.atomic.LongAdder();

void callbackArrived() {
    CALLBACKS.increment();
}

long snapshotCount() {
    return CALLBACKS.sum();
}
~~~

Đây là **mảnh code độc lập về mặt thao tác counter**, nhưng muốn chạy cần đặt trong class. Nó không đòi hỏi `synchronized(globalLock)` do ứng dụng tạo.

### Điểm dễ bỏ qua: sum() không phải giao dịch

Javadoc `LongAdder.sum()` nói rõ kết quả **không phải atomic snapshot** nếu các thread khác đang update. Trong khi cập nhật diễn ra, tổng đọc được có thể chưa bao gồm một số cập nhật đúng thời điểm. Sau khi bạn **đợi các producer hoàn tất** bằng `Thread.join()` hoặc cơ chế đồng bộ phù hợp, có thể đọc chính xác các cập nhật đã hoàn tất trong giai đoạn đó.

Vì vậy:

- **Đúng mục đích:** `requestsSeen.sum()` để thống kê xu hướng hoặc hiển thị metrics.
- **Không đúng mục đích:** `if (requestsSeen.sum() < 100) allowRequest()` để bảo đảm không bao giờ có request thứ 101 dưới concurrent access.
- **Không nên reset khi đang update:** `sumThenReset()` hay `reset()` có ngữ nghĩa/race cần được hiểu; có thể dùng **thay accumulator theo epoch** hoặc cơ chế metrics phù hợp.

### Counter theo từng tên class

Javadoc khuyên có thể dùng `ConcurrentHashMap<String, LongAdder>` cho frequency map:

~~~java
counts.computeIfAbsent(className, key -> new LongAdder()).increment();
~~~

Đây là mẫu hợp lệ khi cần tạo counter theo key động, nhưng trên đường class loading nó còn có thể **phân bổ object mới và chạy mapping function**. Javadoc của `ConcurrentHashMap.computeIfAbsent` lưu ý một số cập nhật map có thể bị chặn trong lúc tính giá trị, nên hàm tính phải **ngắn và đơn giản**, **không sửa chính map** và không gọi code phức tạp.

Nếu chỉ có một tập class cố định, **tạo sẵn counter trước khi đăng ký transformer** rồi trong callback chỉ `get + increment` là lựa chọn dễ dự đoán hơn:

~~~java
counts.put("demo/app/Alpha", new LongAdder());
counts.put("demo/app/Beta", new LongAdder());
// Đăng ký transformer sau khi chuẩn bị xong.

LongAdder counter = counts.get(className);
if (counter != null) counter.increment();
~~~

Đây là **mảnh code**, cần biến `counts` được khởi tạo đúng kiểu. Không phải mọi phép `ConcurrentHashMap.get`/`LongAdder.increment` đều hoàn toàn wait-free trong mọi implementation, nhưng không có **monitor bao quanh toàn bộ callback do agent tự tạo**.

## 6. Pre-initialization: chuẩn bị helper trước khi vào class-loading callback

Ngay cả khi body transformer chỉ gọi `LongAdder.increment()`, lần đầu sử dụng một helper hoặc framework nào đó có thể khiến JVM cần tải/khởi tạo thêm lớp trong thời gian callback. Cách giảm nguy cơ:

1. Trong `premain`, khởi tạo counters, immutable policy, transformer implementation và dependency tối thiểu.
2. Nếu cần bytecode library, chuẩn bị những class/cấu trúc cần thiết trước khi đăng ký, tránh giữ một logger lazy initialization phức tạp trong callback.
3. Sau đó mới gọi `Instrumentation.addTransformer(...)`.
4. Callback lọc tên lớp sớm, **không tự nạp target class** và không gọi code ứng dụng.
5. Đưa báo cáo chi tiết sang giai đoạn khác hoặc thread consumer.

**Không có bảo đảm rằng việc “warm up” một vài helper sẽ loại bỏ hoàn toàn class loading ở mọi nhánh runtime**. Một thư viện có thể lazy-load service/provider ở thời điểm khác. Thiết kế an toàn hơn còn cần loại bỏ phụ thuộc vòng và giữ code callback tối thiểu.

### Helper package cần được loại khỏi phạm vi transform

Nếu bạn instrument tất cả class của ứng dụng và helper của chính agent cũng thuộc phạm vi đó, helper có thể bị instrument, sinh recursion hoặc class loading ngoài dự kiến. Nên có filter:

~~~java
if (className == null
        || className.startsWith("demo/agent/")
        || !className.startsWith("demo/app/")) {
    return null;
}
~~~

Đây là **mảnh code minh họa trong transformer**. `className` là JVM internal name (dấu `/`), không phải binary name có dấu `.`. Filter sớm giúp giảm chi phí trước mọi thao tác về counters, parser, logging.

## 7. Java agent đầy đủ JDK 17+: hai thread nạp lớp, counters không khóa dài

Ví dụ sau triển khai **một Java agent quan sát**. Nó không sửa bytecode; callback luôn trả `null`, nhưng làm đủ ba việc:

- Đếm số class có internal name bắt đầu bằng `demo/app/`.
- Với allowlist trong snapshot bất biến, tăng counter đã tạo sẵn cho từng class được phép.
- Ghi nhận class ngoài allowlist bằng `LongAdder SKIPPED`.

Ứng dụng tạo **hai thread**, cùng được giải phóng bởi một `CountDownLatch`, tải `demo.app.Alpha` và `demo.app.Beta`. Sau khi hai thread `join`, ứng dụng đổi policy qua `AtomicReference.set` và đọc thống kê.

**Thiết kế cố ý tránh:** `synchronized` trong callback, logging từng lần biến đổi, nạp lại class đích bằng loader trong callback, tạo counters bằng I/O trong mapping function, và cập nhật map lớn trong khi giữ class-loading lock.

### 7.1. Bố trí thư mục

~~~text
classloading-concurrency-demo/
├── agent-src/
│   └── demo/agent/LowContentionAgent.java
├── app-src/
│   └── demo/app/
│       ├── Alpha.java
│       ├── Beta.java
│       └── RunDemo.java
└── agent.mf
~~~

Các thư mục output `agent-bin/` và `app-bin/` được tạo bằng lệnh biên dịch. **Tách source agent và ứng dụng** để nhận ra method `premain` là entrypoint agent còn `RunDemo.main` là entrypoint ứng dụng.

### 7.2. agent-src/demo/agent/LowContentionAgent.java

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.LongAdder;

public final class LowContentionAgent {
    private static final String ALPHA = "demo/app/Alpha";
    private static final String BETA = "demo/app/Beta";
    private static final AtomicReference<Set<String>> POLICY =
            new AtomicReference<>(Set.of(ALPHA, BETA));
    private static final ConcurrentHashMap<String, LongAdder> PER_CLASS =
            new ConcurrentHashMap<>();
    private static final LongAdder SEEN_IN_PACKAGE = new LongAdder();
    private static final LongAdder SKIPPED = new LongAdder();

    public static void premain(String options, Instrumentation instrumentation) {
        PER_CLASS.put(ALPHA, new LongAdder());
        PER_CLASS.put(BETA, new LongAdder());
        // Initialize the callback class and its dependencies before registration.
        ClassFileTransformer transformer = new CounterTransformer();
        instrumentation.addTransformer(transformer);
        System.out.println("agentReady=true");
    }

    private static final class CounterTransformer implements ClassFileTransformer {
        @Override
        public byte[] transform(Module module, ClassLoader loader,
                String className, Class<?> classBeingRedefined,
                ProtectionDomain domain, byte[] classfileBuffer) {
            if (className == null || !className.startsWith("demo/app/")) {
                return null;
            }
            SEEN_IN_PACKAGE.increment();
            Set<String> policyAtEntry = POLICY.get();
            if (!policyAtEntry.contains(className)) {
                SKIPPED.increment();
                return null;
            }
            LongAdder counter = PER_CLASS.get(className);
            if (counter != null) {
                counter.increment();
            }
            return null;
        }
    }

    public static void replacePolicy(Set<String> newPolicy) {
        if (!Set.of(ALPHA, BETA).containsAll(newPolicy)) {
            throw new IllegalArgumentException("Only known classes allowed");
        }
        POLICY.set(Set.copyOf(newPolicy));
    }

    public static void report() {
        System.out.println("seenInPackage=" + SEEN_IN_PACKAGE.sum());
        System.out.println("alphaCallbacks=" + PER_CLASS.get(ALPHA).sum());
        System.out.println("betaCallbacks=" + PER_CLASS.get(BETA).sum());
        System.out.println("skippedCallbacks=" + SKIPPED.sum());
        System.out.println("activeRules=" + POLICY.get().size());
    }
}
~~~

**Giải thích những chi tiết có chủ đích:**

1. `POLICY` chứa `Set.of(ALPHA, BETA)` — một collection không thể sửa qua API thông thường. Callback lấy **reference snapshot** bằng `POLICY.get()`; không khóa global.
2. `PER_CLASS` đã có hai entries trước `addTransformer`. Với class được phép, callback chỉ `get(className)` rồi `LongAdder.increment()`, không chạy `computeIfAbsent` lúc đang định nghĩa class.
3. Hai bộ đếm `SEEN_IN_PACKAGE` và `SKIPPED` cũng dùng `LongAdder`; không có `long++` chia sẻ.
4. `className == null` được xử lý trước phép `startsWith`; đồng thời tránh phân tích class không thuộc phạm vi.
5. Không có `System.out.println` trong `transform(...)`. In stdout chỉ xảy ra trong `premain` và `report()`, ở những thời điểm tách khỏi callback của class đích.
6. `return null` giữ nguyên class bytes ở bước transformer. **Số callback không phải số class đã được thay code**.
7. `replacePolicy(...)` nhận policy mới ở thời điểm quản trị, xác minh tên được phép, tạo `Set.copyOf` rồi công bố bằng `POLICY.set(...)`. Việc này **không buộc các callback đang chạy phải chờ một monitor lớn**.
8. `report()` chỉ được gọi **sau khi hai thread nạp class đã `join`** trong demo, nên tổng đếm ổn định. Khi app vẫn đang tiếp tục nạp class, `LongAdder.sum()` chỉ phù hợp thống kê gần thời gian thực, không phải snapshot giao dịch.

Lưu ý việc dùng `ConcurrentHashMap<String,LongAdder>` là **hợp lý với số lượng keys có kiểm soát**. Nếu production agent ghi counter cho mọi class name bất kể phạm vi, map có thể tăng không giới hạn; phải đặt budget, TTL hoặc làm aggregate.

### 7.3. app-src/demo/app/Alpha.java

~~~java
package demo.app;

public final class Alpha {
    public static String message() {
        return "alpha";
    }
}
~~~

### 7.4. app-src/demo/app/Beta.java

~~~java
package demo.app;

public final class Beta {
    public static String message() {
        return "beta";
    }
}
~~~

Hai class mục tiêu không có liên kết trực tiếp với agent. `RunDemo` yêu cầu nạp chúng bằng **tên chuỗi**, tránh việc trình biên dịch biến biểu thức class literal thành phụ thuộc trực tiếp có thể làm class được resolve sớm hơn trong một số tình huống.

### 7.5. app-src/demo/app/RunDemo.java

~~~java
package demo.app;

import demo.agent.LowContentionAgent;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public final class RunDemo {
    private static final class LoaderTask implements Runnable {
        private final String name;
        private final CountDownLatch start;
        private final AtomicReference<String> answer;
        private final AtomicReference<Throwable> failure;

        LoaderTask(String name, CountDownLatch start,
                AtomicReference<String> answer,
                AtomicReference<Throwable> failure) {
            this.name = name;
            this.start = start;
            this.answer = answer;
            this.failure = failure;
        }

        @Override
        public void run() {
            try {
                start.await();
                Class<?> loaded = Class.forName(
                        name, true, RunDemo.class.getClassLoader());
                answer.set((String) loaded.getMethod("message").invoke(null));
            } catch (Throwable error) {
                failure.compareAndSet(null, error);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch start = new CountDownLatch(1);
        AtomicReference<String> a = new AtomicReference<>();
        AtomicReference<String> b = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread first = new Thread(new LoaderTask(
                "demo.app.Alpha", start, a, failure), "loader-alpha");
        Thread second = new Thread(new LoaderTask(
                "demo.app.Beta", start, b, failure), "loader-beta");
        first.start();
        second.start();
        start.countDown();
        first.join();
        second.join();
        if (failure.get() != null) {
            throw new AssertionError("Concurrent loading failed", failure.get());
        }

        System.out.println("alpha=" + a.get());
        System.out.println("beta=" + b.get());
        LowContentionAgent.replacePolicy(Set.of("demo/app/Alpha"));
        LowContentionAgent.report();
    }
}
~~~

Đây là một **driver thử nghiệm**, nên việc `Class.forName(name, true, ...)` trong **application thread** là yêu cầu class loading gốc được kiểm soát. Nó **không phải** `ClassFileTransformer` gọi loader để nạp lại chính target đang được transform. Hai `Thread` sử dụng chung latch để bắt đầu tương đối đồng thời, nhưng **không bảo đảm callback thực sự chạy chồng nhau trên mọi JVM**; nó tạo ra áp lực concurrent class loading và kiểm tra thread-safe behavior trong môi trường thử nghiệm.

`AtomicReference<Throwable> failure` cho phép mỗi task báo lỗi về thread chính thay vì chỉ in một uncaught exception trong thread con và để chương trình chính vẫn kết thúc với exit code 0. `join` cung cấp quan hệ happens-before thích hợp để main đọc kết quả các task và counters được các callbacks tương ứng cập nhật trước khi chúng kết thúc.

Việc đặt tên lớp lồng `LoaderTask` (thay vì lambda trong demo) làm danh sách class ứng dụng dễ hiểu hơn: package `demo.app` sẽ có callback cho `RunDemo`, `RunDemo$LoaderTask`, `Alpha` và `Beta`.

### 7.6. agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.LowContentionAgent
~~~

Đảm bảo **một dòng trống cuối manifest**. Demo chỉ quan sát class khi load và dùng `addTransformer(transformer)`; không cần manifest capability retransform/redefine. Nếu dùng `retransformClasses(...)` ở một bài khác, đó là capability riêng.

### 7.7. Biên dịch và chạy với JDK 17+

Từ thư mục gốc `classloading-concurrency-demo/`, thực hiện trong **Bash**:

~~~bash
mkdir -p agent-bin app-bin
javac --release 17 -d agent-bin agent-src/demo/agent/LowContentionAgent.java
javac --release 17 -cp agent-bin -d app-bin \
  app-src/demo/app/Alpha.java \
  app-src/demo/app/Beta.java \
  app-src/demo/app/RunDemo.java
jar --create --file agent.jar --manifest agent.mf -C agent-bin .
java -javaagent:agent.jar -cp app-bin demo.app.RunDemo
~~~

Trong **Windows PowerShell**, sử dụng lệnh không phụ thuộc nối dòng kiểu Bash:

~~~powershell
New-Item -ItemType Directory -Force -Path agent-bin, app-bin | Out-Null
javac --release 17 -d agent-bin agent-src/demo/agent/LowContentionAgent.java
javac --release 17 -cp agent-bin -d app-bin app-src/demo/app/Alpha.java app-src/demo/app/Beta.java app-src/demo/app/RunDemo.java
jar --create --file agent.jar --manifest agent.mf -C agent-bin .
java -javaagent:agent.jar -cp app-bin demo.app.RunDemo
~~~

`jar -C agent-bin .` đóng cả class lồng `LowContentionAgent$CounterTransformer.class`; nếu chỉ đóng file `LowContentionAgent.class` mà quên class lồng, agent sẽ thiếu implementation transformer.

### 7.8. Stdout chính xác đã kiểm chứng

Đoạn code đã được **biên dịch với `javac --release 17` và chạy trên Zulu OpenJDK 24**. Kết quả:

~~~text
agentReady=true
alpha=alpha
beta=beta
seenInPackage=4
alphaCallbacks=1
betaCallbacks=1
skippedCallbacks=2
activeRules=1
~~~

Giải thích theo nguyên nhân thay vì chỉ nhìn các con số:

| Dòng | Điều đã được xác minh |
| --- | --- |
| `agentReady=true` | Transformer được chuẩn bị/đăng ký trước khi driver chạy |
| `alpha=alpha` và `beta=beta` | Hai lớp ứng dụng được nạp, khởi tạo và gọi method thành công từ hai thread |
| `seenInPackage=4` | Bốn class có internal name bắt đầu `demo/app/` nhận callback trong kịch bản: driver, nested task, Alpha, Beta |
| `alphaCallbacks=1` | Callback cho `demo/app/Alpha` được phép và tăng đúng counter |
| `betaCallbacks=1` | Callback cho `demo/app/Beta` được phép và tăng đúng counter |
| `skippedCallbacks=2` | `RunDemo` và `RunDemo$LoaderTask` nằm ngoài allowlist nhưng vẫn trong package đếm |
| `activeRules=1` | Sau khi nạp hai lớp, policy được thay bằng snapshot mới chỉ cho phép Alpha |

**Không nên suy rộng `seenInPackage=4` thành quy tắc trên mọi JVM/app.** Đó là kết quả của cấu hình/demo trên môi trường đã kiểm chứng. Nếu class được load bằng nhiều loaders, có retransformation, một Java agent khác hoạt động hoặc driver được thay đổi, số callback có thể khác. Bất biến đáng tin hơn là **đếm không bị mất cập nhật do data race trong chính cấu trúc metrics** và quy tắc policy được áp dụng đúng trên từng invocation.

**Không khẳng định chương trình này là transformer thay bytecode:** nó luôn trả `null`. Đây là chương trình minh họa an toàn concurrency của callback và counters, không phải agent chèn tracing instructions.

## 8. Tại sao không in log ngay trong transform?

Một lệnh nhìn có vẻ vô hại:

~~~java
System.out.println("Transforming " + className);
~~~

có thể khiến callback phải format chuỗi, lấy khóa của stream, ghi console chậm và kéo theo việc khởi tạo helper. Trong ví dụ nhỏ, log đôi khi hữu ích; trong production với nhiều class-load threads, nó có thể tạo bottleneck ở console lock.

Đường dữ liệu đề xuất:

~~~text
transform callback:
    filter rất nhanh
    + counter.increment()
    + nếu cần, offer(event) vào bounded queue
    + trả null/byte[] ngay
                  |
                  v
worker telemetry:
    poll/consume queue
    format log / JSON
    ghi stdout, disk, metrics hoặc network
~~~

Một mảnh code minh họa hàng đợi có giới hạn:

~~~java
private static final java.util.concurrent.ArrayBlockingQueue<String> EVENTS =
        new java.util.concurrent.ArrayBlockingQueue<>(1024);
private static final java.util.concurrent.atomic.LongAdder DROPPED =
        new java.util.concurrent.atomic.LongAdder();

static void emitWithoutWaitingForCapacity(String event) {
    if (!EVENTS.offer(event)) {
        DROPPED.increment();
    }
}
~~~

Đây là **mảnh code**, cần đặt trong class và một consumer đọc queue ở thread khác. `offer` trả về ngay khi queue đầy **thay vì chờ có chỗ** như `put`, nhưng `ArrayBlockingQueue` vẫn có **khóa nội bộ ngắn** và có thể chịu lock contention. Nó **không phải wait-free queue**. Việc tạo chuỗi `event` cũng có allocation; nếu latency rất nhạy cảm, cân nhắc cấu trúc ít phân bổ hơn.

Nếu telemetry không thể mất event, cần chọn một trade-off khác (persist/buffer/backpressure) và chấp nhận rằng **không thể vừa bảo đảm không mất mọi event vừa hoàn toàn không chặn** khi consumer chậm mãi và bộ nhớ có giới hạn. Với observability trong class loading, chính sách **drop có đếm + cảnh báo** thường ít rủi ro hơn việc khóa đường nạp lớp để giữ đủ log.

## 9. Không dùng computeIfAbsent để làm việc nặng

`ConcurrentHashMap.computeIfAbsent` cung cấp cập nhật mapping có tính nguyên tử cho key. Tuy nhiên, Javadoc nhấn mạnh mapping function phải **ngắn và đơn giản** vì một số thao tác cập nhật khác có thể chờ trong lúc tính mapping.

Ví dụ **không nên làm**:

~~~java
counters.computeIfAbsent(className, key -> {
    loadFullConfigurationOverNetwork(); // SAI: I/O, có thể chặn.
    buildLargeBytecodeCache();          // SAI: việc nặng trong map operation.
    return new LongAdder();
});
~~~

Đây là **mảnh code phản ví dụ**; `loadFullConfigurationOverNetwork` và `buildLargeBytecodeCache` biểu thị những việc chậm, không phải API Java có sẵn.

Nếu các key được biết trước, hãy khởi tạo chúng trong `premain` như demo. Nếu key động và volume hữu hạn, mẫu `computeIfAbsent(key, k -> new LongAdder())` có thể chấp nhận được; vẫn cần tính chi phí cấp phát, kiểm soát số key và đảm bảo lambda không gọi class loader, không sửa lại chính map.

### Một race thường bị quên: dùng hai map tách rời

Giả sử một thread cập nhật `allowedClasses` và một thread khác cập nhật `counters` bằng hai bước không có công bố chung. Callback có thể thấy **allowlist mới nhưng chưa có counter tương ứng**. Trong demo, tập key hợp lệ cố định và counters được tạo trước, nên `PER_CLASS.get(className)` luôn tìm thấy counter cho tên trong allowlist hợp lệ.

Với policy động không giới hạn tên, một lựa chọn là đóng gói **policy và map counters** trong một immutable holder/reference được publish đồng thời, hoặc cấp phát counters trước rồi mới publish policy, và quản lý lược bỏ counters sao cho callback đang chạy không mất dữ liệu. Đừng xem `AtomicReference<Set<String>>` riêng lẻ giải quyết mọi vấn đề phối hợp nhiều cấu trúc.

## 10. Khóa rất ngắn đôi khi tốt hơn một mô hình lock-free phức tạp

Yêu cầu không phải “cấm tất cả synchronized”, mà là **không giữ khóa kéo dài đường nạp lớp**.

Ví dụ cập nhật một snapshot cấu hình phức tạp từ thread quản trị:

~~~java
synchronized (configUpdateLock) {
    // Chỉ tạo một tham chiếu trạng thái mới và đổi nó.
    currentConfig = preparedImmutableConfig;
}
~~~

Đây là **mảnh code minh họa**, yêu cầu biến đúng kiểu và bảo đảm visibility của `currentConfig` nếu callback đọc nó bên ngoài lock (ví dụ `volatile` hoặc `AtomicReference`). Việc chuẩn bị `preparedImmutableConfig` nên thực hiện **ngoài synchronized**. Quan trọng hơn, callback **không được phải lấy chính lock đó** để chỉ đọc policy mỗi class-load.

Nếu phải dùng lock trong callback để bảo vệ một cache không thể thay bằng cấu trúc concurrent, hãy:

1. Giữ vùng khóa chỉ bao quanh **thao tác O(1) nhỏ**, không I/O.
2. Không gọi code tùy biến/plugin dưới khóa.
3. Không nạp hoặc initialize class dưới khóa do agent tạo.
4. Xác định thứ tự khóa trong mọi đường, tránh lock inversion với class loaders.
5. Đo độ trễ callback và thời gian chờ, thiết lập cảnh báo.
6. Có phương án bỏ qua optional metric nếu lock không lấy được trong budget; không biến telemetry thành điều kiện sống còn của class loading.

## 11. ThreadLocal reentrancy guard: hữu ích nhưng không đủ

Một transformer có thể vô tình gây callback lồng nhau khi chính helper hoặc thư viện parser của nó cần class mới. Một guard theo thread đôi khi giúp phát hiện/giới hạn reentrancy:

~~~java
private static final ThreadLocal<Boolean> ACTIVE =
        ThreadLocal.withInitial(() -> false);

static byte[] guardedTransform(String name, byte[] input) {
    if (Boolean.TRUE.equals(ACTIVE.get())) {
        return null;  // Bỏ qua sự kiện lồng trên chính thread.
    }
    ACTIVE.set(true);
    try {
        return transformBytes(name, input);
    } finally {
        ACTIVE.remove();
    }
}
~~~

Đây là **mảnh minh họa**, cần định nghĩa `transformBytes(...)` và đặt trong class phù hợp. Khi transform nested invocation xảy ra trên cùng thread, nó trả `null`. Cần quyết định rõ rằng bỏ qua nested classes là chấp nhận được với chính sách instrument của bạn.

Nhưng guard **không giải quyết**:

- Deadlock giữa hai thread và hai class loaders.
- Shared-state race do callbacks ở những thread khác nhau.
- Callback nested xảy ra trên thread khác.
- Helper đã bị nạp/khởi tạo sai do side effect trước khi guard chạy.
- Leaks nếu `ThreadLocal` giữ references có vòng đời dài và không `remove()`.

**Không coi guard là lý do để gọi `loader.loadClass(target)` trong transformer.** Loại bỏ phụ thuộc vòng ngay từ thiết kế là ưu tiên cao hơn.

## 12. Cache theo ClassLoader: tranh chấp và memory leak

Khi nhiều plugin loaders cùng định nghĩa `com.example.Service`, một key chỉ là tên chuỗi **không đủ** để phân biệt class identity. Có thể cần một key gồm loader identity và class name/module. Nhưng nếu agent giữ:

~~~java
Map<ClassLoader, Map<String, Metadata>> perLoaderCache = new HashMap<>();
~~~

trong một singleton sống suốt đời JVM, các **strong references** tới loaders có thể ngăn chúng bị garbage-collected và ngăn class unloading sau khi plugin được gỡ.

Giải pháp tùy nhu cầu:

- Chỉ cache metadata **dạng value** không giữ reference vào loaded Class/loader khi không cần.
- Giới hạn số keys, kích thước và thời gian sống; làm cleanup.
- Khi cần weak keys, xem xét `WeakHashMap` được đồng bộ đúng hoặc cache library có weak-key semantics, và đảm bảo **value không giữ ngược strong reference tới key**.
- Với keys động, cân nhắc dùng stable ID trong registry có lifecycle rõ ràng; **identityHashCode** chỉ nên là thông tin diagnostic, không bảo đảm unique global ID.
- Không quét toàn bộ cache hay dọn dẹp nặng trong callback; thực hiện trên thread quản trị/consumer.

`ConcurrentHashMap<ClassLoader,...>` bảo đảm thread-safe operations, nhưng **không tự biến keys thành weak references**. Giảm contention mà gây memory leak vẫn là một agent không an toàn về vận hành.

## 13. Khi phối hợp với Retransformation/Redefinition

Demo đo **load-time** callback, nhưng cùng các nguyên tắc shared state vẫn áp dụng khi gọi `retransformClasses(...)` hoặc `redefineClasses(...)`.

Một số điểm khác biệt:

| Hoạt động | Tác động tới callback/counter |
| --- | --- |
| Load lần đầu | Transformer đăng ký trước đó được gọi; `classBeingRedefined` thường `null` |
| Redefine | Các transformers được gọi theo quy tắc nhóm; `classBeingRedefined` là class đã tồn tại |
| Retransform | Chỉ các transformer có `canRetransform=true` được gọi lại; kết quả của nhóm không có capability được tái áp dụng |
| Nhiều class trong một batch | Callback cho nhiều classes có thể đi qua nhiều thread/đường nội bộ; không dựa vào log toàn cục để suy luận strict order giữa classes |
| Một class định nghĩa lại nhiều lần | Counter callback có thể >1 cho cùng internal name; đó không nhất thiết là data race |

**Đừng dùng “đếm mỗi class đúng một lần” làm bất biến toàn JVM.** Demo đếm một lần cho Alpha/Beta vì mỗi class được định nghĩa một lần trong kịch bản; một ứng dụng với nhiều loaders, agents và retransforms có thể tạo nhiều callbacks cho cùng tên.

Nếu muốn đo “bao nhiêu unique loaded classes”, cần định nghĩa đúng identity (`Class<?>` sau khi đã load, loader + binary name theo ngữ cảnh) và lifecycle/retention. Nếu muốn đo “bao nhiêu lần transformer được gọi”, tăng counter trên **mỗi invocation** và cho phép >1 cho một class.

## 14. Bảo vệ kết quả nghiệp vụ và tránh lỗi telemetry làm hỏng class loading

Hợp đồng `ClassFileTransformer` cho phép callback trả `null` nếu không thay đổi; ngoại lệ do transformer ném ra không có nghĩa JVM tự dừng mọi transformer còn lại. Tuy nhiên, **không nên dùng việc ném exception làm một cách thông thường để bỏ qua instrumentation**: nó vẫn gây overhead, mất observability và che lỗi lập trình.

Thiết kế fail-open cho **telemetry tùy chọn**:

- Counters/queue có thể bỏ qua việc ghi event nếu bị quá tải.
- Không cho lỗi serializer/network phá callback.
- Không sửa mảng `classfileBuffer` mà JVM truyền vào.
- Không thay class bytes chỉ vì telemetry hỏng.
- Nếu bytecode transformation là chức năng bắt buộc, phân biệt lỗi làm bytes không an toàn với lỗi ghi metrics. Không tiếp tục phát bytes sai định dạng để “cố cứu” một lần biến đổi.
- Với lỗi cực đoan như `OutOfMemoryError`, JVM crash hoặc tài nguyên hệ thống bị cạn, không hứa mọi hook đều phục hồi được; chiến lược tốt nhất vẫn là **giảm allocation và phụ thuộc** trước khi đến tình huống đó.

Nên tách:

~~~text
mandatory bytecode correctness     optional telemetry
           |                            |
           v                            v
parse -> transform -> verify       metric.increment() / queue.offer()
           |                            |
           v                            +-- lỗi/drop: ghi nhận trong phạm vi an toàn
      return byte[]/null                |
                                        v
                             không thay kết quả nghiệp vụ
~~~

Một callback chậm, deadlock hoặc lỗi class loading do agent gây ra có thể làm ứng dụng không khởi động được dù class bytes vẫn đúng. Vì thế **tính đúng của bytecode** và **tính an toàn vận hành của callback** phải được kiểm thử riêng.

## 15. Benchmark và stress test nên đo gì?

Khi so sánh “trước agent” và “sau agent”, nên tách các phép đo:

| Chỉ số | Câu hỏi |
| --- | --- |
| Số callback theo nhóm class | Agent có vô tình vào quá nhiều classes không? |
| Thời gian callback p50/p95/p99 | Callback có nhiều outlier khi nhiều threads load không? |
| Class-loading latency | Thời gian định nghĩa lớp có tăng đáng kể không? |
| Startup latency | Ứng dụng có chậm khởi động khi agent bật không? |
| Lock contention/wait | Có callback nào chờ monitor của agent hoặc logger không? |
| Deadlocked threads | Có vòng chờ giữa agent locks và class-loader locks không? |
| Allocation per callback | Có tạo event/stack trace/chuỗi lớn trên đường nóng không? |
| Queue depth/dropped events | Consumer có theo kịp mức sự kiện không? |
| Loader/cache retention | Plugin loaders có unload được sau khi gỡ plugin không? |
| Correctness count | Tổng sau `join` có khớp số callbacks được kích hoạt không? |
| Chính sách update | Callback có thấy snapshot hợp lệ, không thấy set đang sửa dở không? |

### Bài test đồng thời có hệ thống

1. Khởi động JVM với agent và một tập class nhỏ, có expected outcome rõ ràng.
2. Tạo nhiều threads dùng latch/barrier bắt đầu tương đối đồng thời.
3. Mỗi thread tải hoặc yêu cầu define **những class riêng** (không chỉ gọi `loadClass` lặp cho cùng một class đã load).
4. So sánh counters **sau khi các threads hoàn tất**.
5. Thay policy nhiều lần qua snapshot bất biến, kiểm tra mỗi callback dùng **một policy hợp lệ**.
6. Cố tình làm telemetry consumer chậm hoặc queue đầy; xác nhận callback không chờ vô hạn.
7. Dùng custom non-parallel-capable/parallel-capable loaders trong test riêng khi có mô hình loader phức tạp.
8. Kiểm tra thread dump và JFR events nếu xuất hiện stall/lock contention.
9. Thử lifecycle tải/gỡ nhiều plugin loaders; kiểm tra memory retention.
10. Kiểm tra class bytes/method behavior nếu agent có biến đổi thật, không chỉ đếm callbacks.

**Một kết quả chạy nhanh trên một máy không chứng minh không thể deadlock.** Deadlock thường phụ thuộc interleaving hiếm, lazy initialization hoặc phiên bản thư viện. Stress test nên kết hợp static review của lock order với đo runtime.

## 16. Các lỗi phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `count++` trên biến global thường | Lost updates dưới concurrency | `LongAdder` cho metrics; `AtomicLong` cho counter chính xác |
| Chỉ thêm `volatile` vào `count++` | Vẫn không atomic | Dùng atomic update |
| `synchronized(globalLock)` bao cả network/logging | Callback chờ dài, nguy cơ lock inversion | Đưa I/O ra khỏi khóa/callback |
| Nạp helper/parser/logger lazy trong callback | Class-loading lồng nhau, reentrancy | Chuẩn bị helper trước registration, filter sớm |
| Gọi `loader.loadClass(className)` cho chính target | Phụ thuộc vòng hoặc sai runtime identity | Dùng `className` và `classfileBuffer` |
| Dùng `HashMap` mutable chia sẻ không đồng bộ | Race, đọc trạng thái bất nhất | `ConcurrentHashMap` hoặc immutable snapshot |
| Cập nhật hai biến policy độc lập | Callback có thể thấy cấu hình nửa cũ/nửa mới | Một immutable Policy qua `AtomicReference` |
| Sửa Set sau khi đã công bố | Callback thấy dữ liệu mutable/racy | `Set.copyOf` và bất biến sâu phù hợp |
| Gọi I/O trong `computeIfAbsent` | Một số map updates có thể bị chặn | Lambda cực ngắn, preseed keys nếu có thể |
| Dùng `LongAdder.sum()` để cấp phát quota cứng | Không có atomic snapshot | CAS/AtomicLong hoặc bộ phân phối có tính nguyên tử |
| Dùng queue không giới hạn | Memory tăng vô hạn khi consumer chậm | Bounded queue, drop/sampling/backpressure rõ ràng |
| Dùng `BlockingQueue.put` trong callback | Có thể chờ vô hạn nếu queue đầy | `offer` và xử lý drop, hiểu lock nội bộ |
| Gắn ThreadLocal guard nhưng vẫn load target | Guard không chữa deadlock đa thread | Xóa class-loading dependency; guard là lớp bảo vệ bổ sung |
| Cache `ClassLoader` bằng strong keys mãi | Class unloading bị cản | Weak keys/lifecycle + cleanup |
| Log mỗi class ở stdout dưới callback | Console lock, I/O và startup lag | Counter/queue, xuất log ngoài callback |
| Coi callback count là unique class count | Sai khi redefine/retransform/multi-loader | Định nghĩa metric và identity rõ ràng |
| Tin rằng `return null` nghĩa là “không làm gì toàn JVM” | Transformer khác có thể vẫn sửa bytes | Hiểu transformer chain và capability |
| Không kiểm thử helper visibility | `NoClassDefFoundError` khi code mới gọi helper | Bố trí helper/module đúng môi trường |
| Khóa cả quá trình build/verify bytecode | Contention lớn hơn cần thiết | Tách immutable inputs và caches, giảm phạm vi khóa |

## 17. Checklist code review cho transformer nhiều thread

- [ ] Callback filter `className`/scope sớm, null-safe.
- [ ] Không giữ monitor do agent tạo trong khi gọi logger, I/O, class loader, plugin code hoặc callback tùy biến.
- [ ] Không gọi `Class.forName(target)`/`loader.loadClass(target)` khi target đang được định nghĩa.
- [ ] Shared counters không dùng `++` không đồng bộ.
- [ ] Policy cập nhật bằng immutable snapshot được publish an toàn; callback đọc một snapshot.
- [ ] Các keys cố định/counters/helper được chuẩn bị trước khi đăng ký transformer khi thích hợp.
- [ ] Map mutation/remapping function không chứa I/O hay công việc nặng.
- [ ] Không giữ mạnh `Class<?>`/loader lâu hơn cần thiết.
- [ ] Optional telemetry bounded; có chiến lược khi đầy/hỏng, không chặn vô hạn class loading.
- [ ] Không sửa tại chỗ `classfileBuffer`.
- [ ] Phân biệt metrics về callback, class identity và class bytes đã được thay đổi.
- [ ] Kiểm thử concurrency, reentrancy, loader isolation, startup time và failure modes.

## 18. Bài tập tự kiểm tra

**Câu 1.** Hai thread đồng thời chạy `callbacks++` trên một `long` static. Thêm `volatile` có bảo đảm không mất cập nhật không?

**Câu 2.** Vì sao `LongAdder` thường phù hợp đếm số callbacks dưới contention, nhưng không phù hợp làm bộ cấp phát quota chính xác “chỉ 100 requests được nhận”?

**Câu 3.** Agent cập nhật `allowedPackages` và `excludedPackages` trong hai collection mutable riêng, không có đồng bộ. Callback có thể thấy tình trạng gì?

**Câu 4.** `AtomicReference<Policy>` nhận một object `Policy` chứa `HashSet`. Thread quản trị tiếp tục thêm phần tử vào cùng `HashSet` sau khi publish. Có còn an toàn không?

**Câu 5.** `computeIfAbsent(name, key -> slowRemoteCall())` trong `ClassFileTransformer.transform` có nguy hiểm không, dù map là `ConcurrentHashMap`?

**Câu 6.** `ArrayBlockingQueue.offer(event)` có bị chặn vô hạn vì queue đầy như `put(event)` không? Có thể khẳng định nó hoàn toàn lock-free không?

**Câu 7.** Một transformer dùng `ThreadLocal<Boolean>` để bỏ nested callback cùng thread. Nó có loại trừ deadlock giữa hai thread cùng giữ các loader locks khác nhau không?

**Câu 8.** Một chương trình đọc `LongAdder.sum()` trong lúc callback vẫn tăng counter. Có thể coi đó là atomic snapshot chính xác tại một thời điểm không?

**Câu 9.** Hai class có cùng binary name nhưng được định nghĩa bởi hai class loaders. Cache keyed duy nhất theo name có thể gây vấn đề gì?

**Câu 10.** Sau khi tháo một plugin loader, agent vẫn giữ nó trong `ConcurrentHashMap<ClassLoader,...>`. Có thể xảy ra hậu quả nào?

**Câu 11.** Trong demo, `seenInPackage=4` và `skippedCallbacks=2`. Hai lớp bị skip là những lớp nào? Tại sao Alpha và Beta có count 1?

**Câu 12.** Việc `Class.forName("demo.app.Alpha", ...)` được gọi trong `RunDemo.LoaderTask` có vi phạm quy tắc không load target trong transform callback không?

**Câu 13.** Nếu một transformer chỉ trả `null`, việc gọi nó có chứng minh class file đã được sửa không?

**Câu 14.** Nếu app update policy qua `AtomicReference.set(newPolicy)` trong khi một callback đã đọc snapshot cũ, callback đó bắt buộc đổi sang snapshot mới giữa lượt không?

**Câu 15.** Vì sao cần đo startup latency, lock wait và class-loader leaks ngoài việc kiểm tra counters đúng?

### Đáp án

1. **Không.** `volatile` bảo đảm visibility theo Java Memory Model nhưng `++` không phải thao tác atomic.
2. `LongAdder` tối ưu cập nhật phân tán và tổng thống kê, còn `sum()` không là atomic snapshot khi cập nhật đồng thời; quota cứng cần cơ chế atomic riêng.
3. Một tổ hợp **nửa cũ/nửa mới**, khiến scope lọc không nhất quán trong cùng một lần quan sát.
4. **Không.** Publish reference an toàn không biến `HashSet` mutable thành immutable; cần phòng thủ như `Set.copyOf` và không sửa object đã công bố.
5. **Có.** Mapping function có thể gây chờ một số map updates, thêm I/O/class loading vào đường đang tải class.
6. `offer` không chờ chỗ trống như `put`, nhưng `ArrayBlockingQueue` dùng khóa nội bộ; không thể gọi nó wait-free.
7. **Không.** Guard theo thread không giải được lock cycle giữa threads hoặc class loaders.
8. **Không.** Javadoc khẳng định `sum()` không phải atomic snapshot khi có cập nhật.
9. Gộp nhầm metadata/counter hoặc instrument sai runtime identity; cần loader identity/ngữ cảnh module.
10. Strong reference có thể ngăn class unloading, gây memory leak khi plugin được load/unload nhiều lần.
11. `RunDemo` và `RunDemo$LoaderTask` bị skip vì không thuộc allowlist; Alpha/Beta có một lần định nghĩa trong kịch bản.
12. **Không.** Đó là yêu cầu load từ application thread, không phải transformer tự load lại chính class đang được định nghĩa.
13. **Không.** `return null` nghĩa là transformer đó không đưa bytes thay thế.
14. **Không.** Callback có quyền hoàn tất dựa trên snapshot hợp lệ đã đọc lúc vào; cập nhật mới áp dụng cho các lượt đọc tiếp theo.
15. Vì callback có thể đúng về dữ liệu nhưng vẫn làm **chậm hoặc deadlock class loading** hay giữ references khiến loader không unload được.

## 19. Kết luận

**Không chọn giữa “thread-safe” và “nhanh” bằng cách bỏ một trong hai.** Hãy chọn đúng mô hình trạng thái:

- **Chính sách bất biến** được công bố qua `AtomicReference` giúp callback đọc cấu hình mà không lấy khóa quản trị.
- **Counters** dùng `LongAdder` hoặc atomic primitives thay vì biến đếm chia sẻ không an toàn.
- **Class metadata/counters theo key** dùng cấu trúc concurrent với thao tác ngắn, preseed khi thích hợp.
- **I/O, logging và thao tác tốn thời gian** không nằm trong vùng khóa hoặc callback của class loading; telemetry có budget rõ ràng.
- **Class loader/helper** không được tạo phụ thuộc vòng hoặc bị giữ reference vô thời hạn.
- **Stress test** và quan sát latency/lock contention là điều kiện cần để chứng minh thiết kế thực sự phù hợp production.

Một transformer đúng đắn phải **bảo toàn cả class bytes và tiến trình nạp lớp**, không chỉ “không bị data race”. Khi state được bảo vệ với phạm vi đồng bộ tối thiểu và những công việc nặng được chuyển ra ngoài critical path, agent có thể an toàn hơn khi JVM nạp nhiều lớp đồng thời.

## 20. Tài liệu kỹ thuật chính thức

- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback load/redefine/retransform, đầu vào `classfileBuffer`, return `null` và quy tắc không sửa mảng gốc.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): đăng ký transformer, capability và phối hợp redefine/retransform.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `getClassLoadingLock`, parallel-capable loaders và cảnh báo deadlock khi delegation không theo cây.
- [Java SE 21 — LongAdder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counter phân tán, `sum()` không là atomic snapshot và ví dụ frequency map.
- [Java SE 21 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): concurrent map và contract `computeIfAbsent` yêu cầu hàm tính ngắn, đơn giản.
- [Java SE 21 — AtomicReference](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): công bố snapshot, `get`, `set`, compare-and-set và update functions.
- [Java SE 21 — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded queue và phân biệt `offer` với `put`.
- [Java Language Specification 21 — Chapter 17 Threads and Locks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html): happens-before, synchronization, memory visibility và data races.
