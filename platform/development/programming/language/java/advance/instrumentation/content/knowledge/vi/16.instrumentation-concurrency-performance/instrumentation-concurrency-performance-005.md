# Giới hạn cấp phát, phân tích bytecode và ghi log trong callback `ClassFileTransformer`

## 1. Vì sao callback là vị trí nhạy cảm về hiệu năng?

Khi Java agent đăng ký `ClassFileTransformer`, JVM có thể gọi `transform(...)` cho **rất nhiều class definitions** trong quá trình startup hoặc nạp lớp động. Transformer còn có thể tham gia `redefineClasses` hoặc `retransformClasses` tùy capability. JVM cần xử lý kết quả của callback trước khi hoàn tất đường định nghĩa/cập nhật class tương ứng: công việc đồng bộ trong callback vì thế có thể cộng trực tiếp vào độ trễ class loading, startup, hot deploy hoặc việc cập nhật class.

Một callback chỉ thêm vài phép kiểm tra rẻ thường không đáng kể. Nhưng nếu **mọi class** đều phải:

- Tạo `ClassReader`/`ClassWriter`, parse constant pool và toàn bộ method instructions;
- Clone mảng `classfileBuffer` dù không thực sự thay gì;
- Ghép chuỗi log, lấy stack trace và ghi ra `System.out`/file/network;
- Gọi reflection hoặc `Class.forName` để lấy metadata;
- Chờ một synchronized logger, global lock, cache hoặc queue đầy;
- Giữ `Class<?>`, `ClassLoader` hoặc full byte arrays trong cache không có giới hạn;

thì overhead có thể tích lũy theo **hàng nghìn hoặc hàng chục nghìn lần callback**, kéo theo nhiều allocation, GC và contention. Tệ hơn, transformer có thể khởi động class loading đệ quy hoặc deadlock ngay trên đường nạp class của JVM.

**Mục tiêu học tập:** xây callback theo đường xử lý **lọc rẻ → chỉ phân tích khi match → chỉ tạo output khi có thay đổi → trả `null` nếu no-op → xuất log ngoài callback**. Đồng thời phải xử lý concurrent invocations, reentrancy, error policy, object lifetime và cách đo đạc chính xác.

Bài thuộc mục **Đồng thời và hiệu năng**, áp dụng Java Instrumentation trên **JDK 17+**. Ví dụ cuối bài biên dịch/chạy bằng JDK 17, không yêu cầu thư viện ngoài.

## 2. Hợp đồng API trước khi tối ưu

### 2.1. Hai overload của `ClassFileTransformer`

Trong Java 17, callback có dạng legacy 5 tham số:

```java
default byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

và dạng từ Java 9 có thêm `Module`:

```java
default byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

Đây là chữ ký minh họa, cần import `java.security.ProtectionDomain`. Vì cả hai overload đều có default implementation, `ClassFileTransformer` không phải functional interface; hãy dùng class hoặc anonymous class override method, **không dùng lambda** cho interface này trên JDK 17.

Những input quan trọng:

- `className`: JVM internal name, ví dụ `com/example/Service`; trong một số callback đặc biệt có thể là `null`.
- `module`: module của class được transform, không phải module của agent.
- `loader`: **defining class loader**; `null` nếu bootstrap loader.
- `classBeingRedefined`: `null` khi class load mới; khác `null` cho redefine **và** retransform.
- `classfileBuffer`: bytes hiện tại trong chuỗi transformer; **không sửa trực tiếp mảng này**.

Điều kiện `classBeingRedefined != null` **không** tự phân biệt được redefine với retransform. Trên retransform, transformer `canRetransform=false` có thể được JVM tái áp output cũ mà không gọi lại callback; khi muốn đếm các phase, phải hiểu lifecycle registration.

### 2.2. `return null` là no-op chuẩn

Một mẫu fast path đúng:

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> redef,
        ProtectionDomain domain,
        byte[] bytes) {

    if (!"demo/Target".equals(className)) {
        return null;
    }

    return rewriteSelectedClass(bytes);
}
```

Đây là **đoạn minh họa**, vì `rewriteSelectedClass` chưa định nghĩa; phần ví dụ Java 17 đầy đủ ở dưới có đủ các tệp chạy được.

Theo hợp đồng API:

- Trả `null` nếu **không làm phép biến đổi nào**. JVM sẽ dùng input hiện tại như output hiệu dụng.
- Nếu sửa, trả **mảng `byte[]` mới chứa class file hợp lệ**.
- Không chỉnh `classfileBuffer` tại chỗ.
- Không trả mảng rỗng `new byte[0]` để báo no-op.
- Nếu transformer ném exception, các transformer khác vẫn được gọi theo hợp đồng; exception không bảo đảm class loading bị chặn.
- Output khi redefine/retransform phải phù hợp giới hạn JVMTI về thay đổi class đã nạp.

**Hệ quả hiệu năng:** với class không liên quan hoặc không có thay đổi, việc `return null` tránh được bản sao classfile cùng writer/serialization không cần thiết.

## 3. Phân rã chi phí theo giai đoạn

```text
JVM -> transform(...)
        |
        v
 [1] kiểm tra tên/module/loader + policy
        |
        +---- không match ----------> return null
        |
        v
 [2] guard reentrancy nếu cần
        |
        v
 [3] phân tích bytes/metadata cần thiết
        |
        +---- không cần sửa --------> return null
        |
        v
 [4] tạo byte[] / writer mới
        |
        v
 [5] rewrite hợp lệ; cập nhật metric nhẹ
        |
        v
 return new byte[]
        |
        v
 Xuất metrics/log bởi đường KHÁC ngoài callback
```

Các nguồn chi phí không giống nhau:

| Loại | Nguồn overhead | Chiến lược |
| --- | --- | --- |
| Allocation | Clone `byte[]`, parser/visitor, strings, logger events | Khởi tạo có điều kiện, no-op `null`, cache có vòng đời |
| CPU | Duyệt constant pool/method instructions, tính frames | Filter sớm, parse đúng mức cần, benchmark |
| Latency | File/network/console I/O, khóa, queue đầy | Không blocking trên callback, dùng bounded export |
| Class loading | Reflection, logger initialization, helper class dependency | Warm-up helper, không `Class.forName` trong callback |
| Concurrency | Mutable parser dùng chung, global `synchronized` | Per-call local state, immutable config, counters thread-safe |
| Retention | Cache `Class<?>`/`ClassLoader`/`byte[]` không giới hạn | Bounded cache, eviction, weak-key policy phù hợp |
| Correctness | Bytes hỏng, sai frames, chèn trùng hook | Verify, input bất biến, test idempotence |

**Không có giới hạn thời gian/cấp phát mặc định trong Javadoc Java SE.** Mỗi sản phẩm phải đặt ngân sách theo startup SLO, class count, phân bố kích thước classfile, agent ownership, JVM và khả năng chấp nhận overhead.

### 3.1. Vì sao fast path quan trọng?

Giả sử chỉ 1 trong 1.000 class trúng rule. Nếu tạo reader cho cả 1.000 class trước khi lọc, 999 parser vô ích vẫn chạy. Nếu kiểm tra `"demo/Target".equals(className)` trước, phần lớn callback kết thúc mà không xem bất kỳ byte nào.

Tỉ lệ 1/1.000 chỉ là **ví dụ minh họa**, không phải số liệu của JVM nào. Nhưng nguyên tắc vẫn đúng: **tối ưu nhánh phổ biến trước khi tối ưu nhánh hiếm**.

Nếu policy cần lọc theo annotation thì phải đọc metadata, nhưng vẫn có thể lọc trước bằng package/module/class loader; sau đó chỉ thăm attributes cần thiết. Không nhất thiết phải duyệt method instructions hoặc tính lại stack maps chỉ để kiểm tra annotation.

## 4. Hạn chế cấp phát trong callback

### 4.1. Những cấp phát tránh được

Các anti-pattern:

```java
// Sai nếu không sửa gì: clone toàn bộ bytes trên mọi callback.
return classfileBuffer.clone();

// Sai: build string kể cả khi debug logging không cần thiết.
String message = "Inspecting " + className
        + " loader=" + loader;
logDebug(message);

// Sai nếu gọi mọi lần: duyệt hết bytecode trước khi lọc.
Reader reader = new Reader(classfileBuffer);
if (!wanted(className)) {
    return null;
}
```

Đây là **pseudo-code**, các symbol `logDebug`, `Reader`, `wanted` chưa định nghĩa. Nó chỉ minh họa kiểu overhead không cần thiết.

Phiên bản tốt hơn về mặt quyết định:

```java
if (!wanted(className)) {
    return null;
}

if (!requiresChange(classfileBuffer)) {
    return null;
}

// Chỉ cấp phát output ở nhánh thay đổi.
byte[] output = classfileBuffer.clone();
applyChange(output);
return output;
```

Đây cũng là **pseudo-code**, chưa có parser/writer cụ thể. Trong bytecode thực, thay đổi length, constant pool, instruction offset hoặc frames đòi hỏi thư viện hiểu cấu trúc JVM; **không patch raw offsets tùy tiện**.

### 4.2. Chọn dữ liệu cần cache

Có thể tái sử dụng **cấu hình bất biến**, matcher đã biên dịch, set tên method, rule version, descriptors và metadata không phụ thuộc từng class. Nhưng cần cẩn thận:

- Không giữ `classfileBuffer` từ tất cả callback chỉ để “có thể debug sau”.
- Không dùng một instance mutable `ClassReader`/`ClassWriter` từ nhiều threads nếu implementation không thread-safe.
- Không lưu `ClassLoader` hoặc `Class<?>` làm strong key của cache tĩnh không giới hạn, vì có thể gây classloader leak.
- Không dùng riêng tên `className` để định danh class khi nhiều loaders có thể define cùng binary name.
- Không cache kết quả không đầy đủ hoặc stale sau redefinition/retransformation.

Nếu phải giữ metadata theo class, có thể xem `ClassValue`, weak keys hoặc cache gắn với lifecycle plugin/module, nhưng phải kiểm tra **value không giữ ngược lại loader**, thread safety và policy invalidation.

### 4.3. Counter không nhất thiết tạo ít allocation tuyệt đối

`LongAdder` thường tốt với nhiều thread cùng cập nhật, nhưng khi contention tăng nó có thể cấp phát cấu trúc `Cell` nội bộ. `ThreadLocal` cũng có thể tạo entries khi được dùng lần đầu trên thread.

Mục tiêu đúng là **tránh cấp phát không cần thiết trong nhánh phổ biến**, không hứa “zero allocation” khi JVM, JIT, counter và các thư viện vẫn có thể cấp phát theo trạng thái.

## 5. Giới hạn việc phân tích bytecode

### 5.1. Cần phân tích sâu tới đâu?

| Yêu cầu | Cần đọc gì? | Full instruction walk? |
| --- | --- | --- |
| Lọc theo tên class | `className` callback | Không |
| Lọc theo module/defining loader | `module`/`loader` callback | Không |
| Lọc theo class-file version | Header class file | Không |
| Xem danh sách method signatures | Class/method metadata | Không nhất thiết |
| Kiểm tra annotation | Attributes/metadata | Không nhất thiết |
| Chèn method-entry advice | Code attributes, instructions | Có |
| Bao phủ exceptional exits | Control flow + exception table | Có |
| Sinh/recompute stack maps | Control flow và hierarchy | Có thể phân tích sâu |

Trong Java 17, sử dụng thư viện bytecode như ASM/Byte Buddy cho rewriting phức tạp. Java Class-File API `java.lang.classfile` được chuẩn hóa từ **JDK 24**, không có trong JDK 17.

### 5.2. Tránh class loading ngoài ý muốn

Một lỗi điển hình:

```java
// Anti-pattern trong transform của class chưa được định nghĩa:
Class<?> target = Class.forName(
        className.replace('/', '.'),
        false,
        loader);
```

Mã này có thể kích hoạt loading/linking (dù `initialize=false`), nạp sai class qua loader khác hoặc recursion ngay khi chính target đang được định nghĩa. Thay vì vậy, dùng module/name/loader callback và metadata classfile; nếu cần hierarchy để tạo frames thì chọn nguồn classfile/resolver được kiểm soát.

**Không dùng reflection chỉ để xem class có annotation** khi parser classfile có thể đọc annotation attributes mà không define class vào JVM.

### 5.3. Giới hạn phân tích và thời gian

Nếu input không tin cậy hoặc có classfile bất thường, parser phải kiểm tra length/magic, constant-pool tags, offsets và giới hạn bộ nhớ trước khi allocation lớn. Không được coi ví dụ parser rút gọn trong bài là công cụ đọc mọi classfile có thể gặp.

Một soft time budget có thể giúp agent quan sát parser bị chậm, nhưng JVM **không có cơ chế tự động cắt ngang an toàn callback theo một deadline**. Khi quyết định bỏ qua, hãy dừng ở trạng thái mà vẫn có thể trả `null` hoặc output **hoàn chỉnh**; tuyệt đối không trả mảng byte đang rewrite dở.

## 6. Hạn chế ghi log trong callback

### 6.1. Vì sao `System.out.println` có thể gây chậm và recursion?

```java
System.out.println(
        "Transforming " + className + ", loader=" + loader);
```

Trong callback chạy cho nhiều class, dòng này có thể:

- Tạo strings/string builder và gọi custom `loader.toString()`.
- Ghi `PrintStream` đồng bộ; terminal/file có thể block hoặc bị backpressure.
- Tải thêm logger formatters, appenders, classes phụ trợ trong quá trình class loading.
- Gây khóa ngược với một class loader đang bị giữ khóa.
- Làm log storm, tốn disk/network và tăng footprint của agent.

Một logger ở level OFF **không loại được chi phí** nếu message đã được format trước `isDebugEnabled()`.

### 6.2. Mô hình log đề xuất

**Trong callback:** chỉ giữ counters hoặc các event tối thiểu đã được chọn, không tạo message dài.

**Ngoài callback:** tiến trình quản lý agent hoặc scheduled exporter tổng hợp counters, rate-limit và in log.

Ví dụ:

```java
private static final java.util.concurrent.atomic.LongAdder CHANGED =
        new java.util.concurrent.atomic.LongAdder();

// Bên trong callback, sau khi thật sự thay bytes:
CHANGED.increment();

// Bên ngoài callback, tại thời điểm xuất báo cáo:
String summary = "changed=" + CHANGED.sum();
```

Đây là **các đoạn minh họa**, chưa phải class độc lập. `LongAdder.sum()` phù hợp cho metrics, nhưng không phải snapshot atomic tuyến tính khi các threads vẫn cập nhật.

Nếu cần log từng lỗi cụ thể, dùng **bounded queue**, sampling hoặc rate limit. Queue đầy thì có chính sách **drop/coalesce**, không `BlockingQueue.put` có thể chờ mãi từ callback. Cần cân nhắc cả chi phí cấp phát event object và enqueue.

### 6.3. Chống logging recursion

Một logger khởi tạo lần đầu trong `transform` có thể load nhiều class phụ trợ; mỗi class phụ trợ lại kích hoạt transformer. Cách giảm rủi ro:

1. Khởi tạo helpers cần thiết và logging backend ngoài callback, trong giai đoạn `premain` nếu phù hợp.
2. Không instrument packages của chính agent/logger trừ khi có mục tiêu rõ ràng.
3. Dùng filter class trước mọi logging.
4. Gắn một reentrancy guard **sau filter** khi thật sự cần.
5. Không log stack trace vô hạn trong catch; đếm lỗi rồi xử lý theo fail policy.

Không hứa rằng preload toàn bộ helper sẽ loại bỏ hoàn toàn recursion: class loader/module/dependency graph và các agent khác vẫn có thể tương tác.

## 7. Đồng thời và trạng thái dùng chung

### 7.1. Callback không được giả định single-threaded

Class loading có thể diễn ra trên nhiều threads. Một transformer instance có thể xử lý nhiều class đồng thời; trạng thái mutable dùng chung phải được thiết kế an toàn:

- Tránh `synchronized transform(...)`, vì serialize đường class loading và có thể tăng deadlock risk.
- Không lưu `byte[] currentBuffer` hoặc parser mutable vào static field chung.
- Dùng biến local cho bytecode visitor, buffer và output của mỗi invocation.
- Cấu hình được thay qua **immutable snapshot** và `volatile` hoặc `AtomicReference` nếu agent có policy động.
- Chỉ dùng counters thread-safe hoặc queue có bound.
- Nếu cache theo class, xác định rõ loader/module namespace và version.

Javadoc `Instrumentation.removeTransformer` còn lưu ý: transformer **có thể nhận callback sau khi được remove** do class loading song song. Vì vậy callback không được truy cập tài nguyên đã đóng mà không có bảo vệ lifecycle.

### 7.2. `ThreadLocal` guard có phạm vi rõ ràng

Một guard cơ bản:

```java
private static final ThreadLocal<Boolean> ACTIVE =
        new ThreadLocal<>();

static boolean enter() {
    if (Boolean.TRUE.equals(ACTIVE.get())) {
        return false;
    }
    ACTIVE.set(Boolean.TRUE);
    return true;
}

static void leave() {
    ACTIVE.remove();
}
```

Snippet minh họa, không phải class Java độc lập. Khi đã `enter()` thành công, gọi `leave()` trong `finally`. Guard giúp chặn một dạng reentry **cùng thread**; nó không giải quyết vòng phụ thuộc giữa nhiều threads hoặc global locks.

`ThreadLocal` có chi phí trên từng thread và có thể giữ value quá lâu nếu quên `remove()`. Không lưu object của plugin hoặc classloader trong ThreadLocal gắn với executor thread dài hạn.

## 8. Demo Java 17: lọc sớm, clone có điều kiện, log ngoài callback

Demo dùng đúng **một Java agent** và **một class mục tiêu**. Agent chỉ sửa literal constant-pool UTF8 có 6 byte:

```text
"ORIGIN" -> "PATCH!"
```

Cả hai chuỗi đều gồm 6 byte ASCII, nên ví dụ có thể thay byte trong `CONSTANT_Utf8` mà **không đổi độ dài entry hoặc offsets**. Đây là bài thực hành minh họa allocation strategy, không phải bytecode patcher tổng quát. Để chèn method-entry advice, hãy dùng ASM/Byte Buddy với verifier/frames.

### 8.1. Cấu trúc

```text
fast-callback/
├── PerfAgent.java
├── FastTransformer.java
├── TargetService.java
├── DemoApp.java
└── agent.mf
```

Tất cả Java sources nằm ở default package để dễ chạy; target được load từ app JAR sau khi `premain` đăng ký transformer.

### 8.2. `PerfAgent.java`

```java
import java.lang.instrument.Instrumentation;

public final class PerfAgent {
    private PerfAgent() {
    }

    public static void premain(String args, Instrumentation inst) {
        // Khởi tạo class, counters và guard trước khi target load.
        inst.addTransformer(new FastTransformer(), false);
    }

    public static String metrics() {
        // Không xây chuỗi trong callback.
        return FastTransformer.metrics();
    }
}
```

### 8.3. `FastTransformer.java`

```java
import java.lang.instrument.ClassFileTransformer;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.LongAdder;

public final class FastTransformer implements ClassFileTransformer {
    private static final byte[] OLD =
            "ORIGIN".getBytes(StandardCharsets.US_ASCII);
    private static final byte[] NEW =
            "PATCH!".getBytes(StandardCharsets.US_ASCII);

    private static final LongAdder MATCHED = new LongAdder();
    private static final LongAdder CHANGED = new LongAdder();
    private static final LongAdder NO_OP = new LongAdder();
    private static final LongAdder FAILED = new LongAdder();
    private static final LongAdder TOTAL_NANOS = new LongAdder();

    // Chỉ dùng ở nhánh class trúng filter.
    private static final ThreadLocal<Boolean> ACTIVE =
            new ThreadLocal<>();

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] classfileBuffer) {

        // Fast path: không đụng tới bytes, timer, logger hoặc ThreadLocal.
        if (!"TargetService".equals(className)
                || classBeingRedefined != null) {
            return null;
        }

        MATCHED.increment();

        if (Boolean.TRUE.equals(ACTIVE.get())) {
            NO_OP.increment();
            return null;
        }

        ACTIVE.set(Boolean.TRUE);
        long start = System.nanoTime();

        try {
            byte[] changed = patch(classfileBuffer);
            if (changed == null) {
                NO_OP.increment();
                return null;
            }

            CHANGED.increment();
            return changed;
        } catch (RuntimeException error) {
            // Fail-open cho demo; sản phẩm thật cần policy rõ.
            FAILED.increment();
            return null;
        } finally {
            TOTAL_NANOS.add(System.nanoTime() - start);
            ACTIVE.remove();
        }
    }

    private static byte[] patch(byte[] input) {
        if (input.length < 10
                || (input[0] & 255) != 0xCA
                || (input[1] & 255) != 0xFE
                || (input[2] & 255) != 0xBA
                || (input[3] & 255) != 0xBE) {
            throw new IllegalArgumentException("Invalid class file");
        }

        int constantPoolCount = u2(input, 8);
        int p = 10;
        byte[] result = null;

        for (int i = 1; i < constantPoolCount; i++) {
            int tag = input[p++] & 255;

            switch (tag) {
                case 1 -> { // CONSTANT_Utf8
                    int n = u2(input, p);
                    p += 2;

                    if (n == OLD.length && equalsAt(input, p, OLD)) {
                        // Mảng mới chỉ được tạo khi thật sự sửa.
                        if (result == null) {
                            result = input.clone();
                        }
                        System.arraycopy(NEW, 0, result, p, NEW.length);
                    }
                    p += n;
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 -> p += 4;
                case 5, 6 -> { // Long/Double dùng 2 index.
                    p += 8;
                    i++;
                }
                case 7, 8, 16, 19, 20 -> p += 2;
                case 15 -> p += 3;
                default -> throw new IllegalArgumentException(
                        "Unsupported constant pool tag: " + tag);
            }
        }
        return result; // null = không sửa.
    }

    private static int u2(byte[] bytes, int at) {
        return ((bytes[at] & 255) << 8)
                | (bytes[at + 1] & 255);
    }

    private static boolean equalsAt(
            byte[] bytes, int at, byte[] pattern) {
        for (int i = 0; i < pattern.length; i++) {
            if (bytes[at + i] != pattern[i]) {
                return false;
            }
        }
        return true;
    }

    static String metrics() {
        return "[agent] matched=" + MATCHED.sum()
                + " changed=" + CHANGED.sum()
                + " noOp=" + NO_OP.sum()
                + " failed=" + FAILED.sum();
    }

    static long totalTransformNanos() {
        return TOTAL_NANOS.sum();
    }
}
```

**Điều đúng về hiệu năng và API của code:**

1. Non-target class đi thẳng qua `return null`: không clone, parse, log, timer hay touch ThreadLocal.
2. Các counters/constant arrays/guard được khởi tạo khi class `FastTransformer` khởi tạo lúc `premain`, không tạo lại mỗi target.
3. Chỉ nhánh target mới duyệt constant pool. Khi thấy literal cần sửa, một `input.clone()` được tạo, nguyên input không bị mutate.
4. Nếu target đã có `PATCH!` và không còn `ORIGIN`, `patch` trả `null`; hiệu ứng là no-op.
5. `TOTAL_NANOS` chỉ ghi duration từ sau filter/guard đến `finally`. Nó **không** đo toàn JVM class load/verification hoặc overhead của non-target fast paths.
6. `ThreadLocal` luôn `remove()` trong `finally`, giúp tránh giữ entry lâu trong thread; guard chỉ bảo vệ cùng thread.
7. `metrics()` ghép chuỗi **sau callback**, không ngay trong đường transform.
8. `FAILED` ghi nhận lỗi parser bằng `RuntimeException` và demo trả `null`; lỗi khác/chính sách security-critical cần xử lý riêng.

**Giới hạn quan trọng:** parser chỉ đủ cho class file `javac --release 17` hợp lệ của demo, không kiểm tra toàn bộ bounds/cp semantics và không dùng cho dữ liệu tùy ý. Code production phải dùng thư viện bytecode chuẩn, verify output và kiểm tra JVM/classfile version.

### 8.4. `TargetService.java`

```java
public final class TargetService {
    private TargetService() {
    }

    public static String value() {
        return "ORIGIN";
    }
}
```

Literal này xuất hiện trong constant pool, và agent thay đúng 6 ASCII bytes thành `PATCH!`.

### 8.5. `DemoApp.java`

```java
public final class DemoApp {
    private DemoApp() {
    }

    public static void main(String[] args) {
        // Nạp target sau khi premain đã đăng ký transformer.
        System.out.println("[app] value=" + TargetService.value());

        // Chỉ đến đây mới build và in chuỗi log/metrics.
        System.out.println(PerfAgent.metrics());
    }
}
```

### 8.6. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: PerfAgent

```

Đây là manifest của agent JAR. Cần dòng trống kết thúc main section; demo không dùng retransform/redefine nên không cần `Can-Retransform-Classes` hoặc `Can-Redefine-Classes`.

### 8.7. Chạy trên Linux/macOS/WSL (POSIX)

Mở terminal trong thư mục `fast-callback/`:

```bash
mkdir -p out

javac --release 17 -d out \
  PerfAgent.java FastTransformer.java TargetService.java DemoApp.java

jar --create --file perf-agent.jar --manifest agent.mf \
  -C out PerfAgent.class -C out FastTransformer.class

jar --create --file app.jar \
  -C out DemoApp.class -C out TargetService.class

java -javaagent:perf-agent.jar \
  -cp "perf-agent.jar:app.jar" DemoApp
```

**Stdout kỳ vọng**:

```text
[app] value=PATCH!
[agent] matched=1 changed=1 noOp=0 failed=0
```

Đây là các giá trị ổn định của demo khi JVM bình thường chỉ định nghĩa `TargetService` một lần và không có agent khác can thiệp. `TOTAL_NANOS` không được in vì giá trị nanosecond phụ thuộc JVM/JIT/host. Với môi trường nhiều agents hoặc custom loaders, counters có thể khác tùy số callback thực tế.

Nếu bỏ `-javaagent:perf-agent.jar` mà vẫn để agent JAR trên classpath, `TargetService.value()` trả `ORIGIN`; counters từ `FastTransformer` có thể đọc nhưng chưa có lần biến đổi nào nên đều bằng 0.

### 8.8. Windows PowerShell

```powershell
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -d out PerfAgent.java FastTransformer.java TargetService.java DemoApp.java
jar --create --file perf-agent.jar --manifest agent.mf -C out PerfAgent.class -C out FastTransformer.class
jar --create --file app.jar -C out DemoApp.class -C out TargetService.class

java -javaagent:perf-agent.jar -cp "perf-agent.jar;app.jar" DemoApp
```

Windows dùng dấu `;` trong classpath, POSIX dùng dấu `:`.

### 8.9. Kiểm tra các tính chất của demo

- **Đúng đối tượng:** chỉ `className = "TargetService"` và initial class load được xử lý.
- **Input bất biến:** `input` không bị sửa; output khác `null` được tạo bằng clone.
- **Không clone khi no-op:** `patch(input)` trả `null` nếu không thấy `ORIGIN`.
- **Tính xác định:** cùng input bytes trong demo và cùng rule, phép patch cho cùng output.
- **Chịu lặp lại:** khi đưa output đã patch qua hàm patch một lần nữa, không còn literal cũ nên output hiệu dụng giữ nguyên.
- **Báo lỗi:** parser lỗi RuntimeException thì tăng counter và trả null, không ghi stack trace trong callback.
- **Không logging hot path:** chuỗi `[agent] ...` được xây sau khi method target hoàn thành.
- **Chưa giải quyết mọi bài toán:** không minh họa ASM advice/frame recomputation, cũng không chứng minh class loading toàn JVM không có bất kỳ allocation nào.

## 9. Đo overhead đúng cách

### 9.1. Tách các tầng đo

Cần phân biệt:

1. **Callback exposure**: số lần JVM gọi transformer, kể cả no-op.
2. **Rule match**: số callback trúng bộ lọc.
3. **Parse/transform time**: CPU và allocation chỉ cho lớp trúng rule.
4. **JVM define/verify**: chi phí VM sau khi nhận output bytes.
5. **Runtime probe overhead**: chi phí của hook đã chèn khi method được ứng dụng gọi nhiều lần.
6. **Logging/export**: chi phí sink ngoài callback.

Timer trong callback **không** tự đo toàn startup time và **không** đo overhead của method advice lúc runtime. Nếu dùng `System.nanoTime()` trong mỗi callback để đo mọi class, chính timer cũng tạo overhead. Chỉ đo khi cần, sampling hoặc chỉ class match.

### 9.2. Bảng benchmark tối thiểu

| Biến thể | Muốn đo | Cần giữ cố định |
| --- | --- | --- |
| JVM không có agent | Baseline startup và class loading | JDK, app, options |
| Agent fast no-op | Chi phí registration/filter | Cùng tập classes |
| Agent parse-only | Chi phí bytecode reader | Cùng classfile fixtures |
| Agent rewrite | Thêm allocation/writer/frame cost | Cùng rule/output target |
| Agent per-class logging | Chi phí diagnostic (anti-pattern đối chứng) | Cùng log sink và volume |
| Agent aggregate logging | Chi phí counters/export | Cùng telemetry cadence |
| Concurrent plugin/class loading | Contention, throughput, p99 latency | Loaders, threads, hardware |

Phép đo đơn lẻ có thể bị JIT warm-up, disk cache, GC, class loader topology, logging sink và background workload ảnh hưởng. Hãy chạy nhiều lượt, phân tích distributions và quan sát **allocations, GC pauses, CPU, startup latency và tail latency**, không chỉ số nanosecond của một callback.

### 9.3. Công cụ quan sát

- **JFR:** class loading, allocation, CPU, GC events theo cấu hình recording.
- **JVM unified logging:** class loading/GC logs khi cần điều tra; bật có chọn lọc vì log cũng gây overhead.
- **Async-profiler hoặc profiler tương đương:** CPU/allocation hotspots theo runtime thực tế.
- **JMH:** benchmark thuật toán parse/transform độc lập sau warm-up, nhưng cần integration benchmark để biết tác động class loading thật.
- **Heap dump/classloader diagnostics:** tìm cache giữ `Class<?>`, `ClassLoader` hay output `byte[]` lâu dài.

Không đo `Instrumentation.getObjectSize(classfileBuffer)` rồi gọi đó là tổng chi phí của instrumentation: hàm chỉ cho ước lượng shallow size của object, không phải CPU, GC và Metaspace.

## 10. Lỗi và chính sách fail-open/fail-closed

Trong một agent quan sát thông thường, parser bị lỗi có thể chọn `return null` để tránh làm hỏng app. Ví dụ dùng `catch (RuntimeException)` và chỉ tăng `FAILED`. Nhưng với agent kiểm soát an ninh, bỏ điểm đo chưa chắc chấp nhận được: phải có policy rõ, test failure modes và quản lý alerting ngoài callback.

Không dùng `throw new IllegalClassFormatException(...)` làm một “công tắc chắc chắn từ chối class”: Javadoc nêu rằng exception của transformer được xử lý theo chuỗi và không bảo đảm load/redefine bị hủy. Không lạm dụng `catch (Throwable)` để nuốt `OutOfMemoryError`, `ThreadDeath` hoặc các lỗi VM nghiêm trọng.

Nếu muốn diagnostic lỗi đầy đủ, thu thập một sự kiện ngắn có bound trong callback (nếu còn đủ tài nguyên), rồi xử lý/format log sau. Đừng gọi `error.printStackTrace()` trực tiếp trên đường class loading.

## 11. Cần kiểm tra tính đúng đắn khi callback lặp

Một transformer nhanh nhưng tạo thêm hook sau mỗi lượt cũng có thể làm ứng dụng chậm dần.

- **Deterministic:** cùng classfile bytes + cùng policy snapshot → output hiệu dụng giống nhau.
- **Idempotent nếu được yêu cầu:** xử lý lại output không thêm hook, field, method hay wrapper không có chủ đích.
- **Repeat-safe:** counters/cache/lifecycle không gây double-counting sai mục tiêu hoặc giữ tài nguyên vô hạn.
- **Composable:** nhiều transformers chạy theo thứ tự; output trước trở thành input sau. Hai transformer idempotent riêng chưa chắc pipeline idempotent.
- **Class loader aware:** cùng binary name từ hai loaders không nhất thiết là cùng class identity.

`retransformClasses` không nhất thiết đưa output trước của chính transformer làm input cho callback mới; JVM sử dụng bytes nền và cơ chế reuse của transformers `canRetransform=false`. Vì vậy để test `T(T(B)) = T(B)`, cần unit test **gọi thuật toán thuần trên output của chính nó**; bổ sung integration test JVM cho retransform/redefine.

Một số tình huống cần thử:

- Class không match: luôn return null, không allocation byte[] từ chính rule.
- Class match nhưng đã instrument: no-op, không thêm hook lần thứ hai.
- Class match có bytes hỏng: policy fail-open/closed rõ và không log storm.
- Nhiều loaders cùng tên: scope/filter đúng.
- Hai threads transform song song: không dùng chung mutable visitor.
- Hủy đăng ký: callback in-flight không dùng resource đã đóng.
- Helper class load trong callback: không recursion/deadlock.

## 12. Anti-pattern về vòng đời và memory

### Lưu cả input bytes sau mỗi callback

```java
static final java.util.List<byte[]> HISTORY =
        new java.util.ArrayList<>();

static void keep(byte[] input) {
    HISTORY.add(input);
}
```

Đây là **anti-pattern minh họa**, không phải file Java độc lập. Khi class load nhiều, list không giới hạn sẽ giữ mỗi buffer lâu dài; mục tiêu chỉ ghi metric thì không cần.

### Map theo class loader không có eviction

```java
static final java.util.Map<ClassLoader, byte[]> CACHE =
        new java.util.concurrent.ConcurrentHashMap<>();
```

Strong keys có thể giữ plugin loader và class metadata reachable sau khi plugin được ứng dụng dỡ. Nếu cần cache, phải có lifecycle/TTL/size budget, kiểm tra cache value không giữ ngược loader và phân biệt module/class identity. Weak-key cache không giải quyết mọi leak nếu value giữ strong references về key.

### ThreadLocal không dọn

Nếu `ThreadLocal` chứa object thuộc plugin rồi thread pool sống mãi, loader plugin có thể bị giữ qua value. Với reentrancy guard, chỉ nên lưu flag/giá trị tối thiểu và dùng `remove()` trong `finally`.

### Unbounded queue cho event/log

Nếu callback nhanh hơn consumer, queue tăng theo class loading rate hoặc memory pressure. Phải có bounded capacity và chính sách drop/coalesce, không chờ blocking I/O từ callback.

## 13. Bảng chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Startup chậm dù ít class mục tiêu | Parse tất cả classes trước filter | Kiểm tra tên/module/loader trước khi đụng bytes |
| GC allocations tăng | Clone và tạo writer cả khi không thay đổi | `return null` cho no-op, clone chỉ khi cần |
| Class loading deadlock | Logging lock, reflection, synchronized callback hoặc classloading recursion | Giảm dependencies, tránh I/O/lock, guard có giới hạn |
| Ghi hàng nghìn dòng log trong startup | Log mọi class, build string trước level check | Counters, sampling, rate limit, external exporter |
| Race khi nhiều class load | Dùng chung mutable parser/writer | Local variables, immutable policy, thread-safe counters |
| Lỗi stack maps/`VerifyError` | Rewrite control flow mà không bảo toàn frames | Dùng library phù hợp, verify classfile JVM đích |
| `Class.forName` gây vòng tải class | Cố lấy metadata từ class đang define | Dùng callback metadata, bytecode parser và resolver phù hợp |
| Chương trình có nhiều loaders bị patch nhầm | Filter/cache chỉ dựa vào class name | Bổ sung namespace loader/module cho policy |
| Plugin unload rồi loader vẫn reachable | Cache giữ `ClassLoader` hoặc `Class<?>` mạnh | Bounded cache, lifecycle cleanup, heap-dump paths |
| Counter đổi khi đọc | `LongAdder.sum()` không atomic snapshot giữa updates | Dùng metric ước lượng; cần snapshot nhất quán thì đồng bộ riêng |
| Transformer trả exception nhưng class vẫn load | Hiểu sai contract transformer exception | Không dùng exception như cơ chế chặn class tuyệt đối |
| Callback ít nhưng startup vẫn chậm | Chỉ đo class match, bỏ sót VM/other callbacks | Đo baseline và end-to-end class loading |
| Gỡ transformer nhưng hook cũ vẫn chạy | `removeTransformer` không tự rollback class đã instrument | Cần redefine/retransform theo capability nếu muốn hoàn tác |
| Java 17 không nhận `java.lang.classfile` | API này chính thức từ JDK 24 | Dùng ASM/Byte Buddy hoặc nâng JDK |

## 14. Checklist trước production

1. Filter theo `className`/`module`/`loader` và policy snapshot **trước parser**.
2. Không tạo `ClassReader`/`ClassWriter` khi class không match.
3. Trả `null` nếu no-op; không clone hoặc mutate input.
4. Chỉ parse metadata/code đúng mức rule cần; đừng tính frames vô ích.
5. Không dùng `Class.forName`/reflection gây classloading ngoài ý muốn trong callback.
6. Không log per-class vô điều kiện; định dạng message ngoài callback.
7. Dùng bounded queue, sampling/rate limit, tránh I/O có thể block.
8. Dùng immutable config và local visitor/buffers; counters thread-safe.
9. Không `synchronized` cả callback qua global monitor.
10. Nếu dùng `ThreadLocal` guard, đặt sau fast filter, dọn ở `finally`.
11. Không giữ strong references tới class loader, Class objects hoặc byte arrays vô hạn.
12. Định nghĩa fail-open/fail-closed đúng mục tiêu; không nuốt VM fatal errors máy móc.
13. Verify classfile và test constructors, exception paths, class versions, frames.
14. Test lặp redefinition/retransformation cùng các transformers khác.
15. Đo baseline/no-op/parse/rewrite/logging/end-to-end startup trên workload thực.
16. Có cảnh báo performance budget, failure rate, memory retention và callback latency.
17. Thử trên JVM, classloaders/modules và hệ thống build/deploy mục tiêu.

## 15. Câu hỏi tự kiểm tra

**Câu 1:** Vì sao `return null` tốt hơn `return bytes.clone()` khi không sửa class?

**Đáp án:** `null` là no-op theo API và tránh allocation/copy bytes, trong khi không sửa input.

**Câu 2:** Có nên tạo parser cho mọi class rồi mới xét `className`?

**Đáp án:** Không nếu rule có thể lọc bằng tên/module/loader. Filter trước giúp nhánh phổ biến rẻ hơn.

**Câu 3:** Logger ở level OFF có hoàn toàn không allocation không?

**Đáp án:** Không nếu message đã được format trước khi kiểm tra level. Phải guard việc tạo message, ưu tiên không log trên fast path.

**Câu 4:** `ThreadLocal` guard có ngăn recursion qua mọi threads không?

**Đáp án:** Không. Nó chỉ giới hạn reentry cùng thread và không thay thế kiểm soát classloader dependencies/locks.

**Câu 5:** `changed.increment()` chứng minh JVM đã install bytes thành công chưa?

**Đáp án:** Chưa. Counter tăng trước khi JVM verify/link/define class. Cần kiểm thử kết quả thực thi.

**Câu 6:** Một transformer được `removeTransformer` có thể nhận callback nữa không?

**Đáp án:** Có thể do class loading đang diễn ra đồng thời. Code teardown phải chịu được in-flight callback.

**Câu 7:** Vì sao không được coi callback exception là phương thức chắc chắn chặn class load?

**Đáp án:** Contract vẫn cho phép gọi các transformers sau và tiếp tục thử load/redefine; cần cơ chế khác nếu có yêu cầu chính sách chặn.

**Câu 8:** Tối ưu allocation trong transform có đủ để tối ưu agent không?

**Đáp án:** Không. Vẫn còn CPU parse, JVM verification, classloader concurrency và overhead của probes được chèn trong các method khi ứng dụng chạy.

## 16. Tài liệu chuẩn

- [Oracle Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callbacks, `null`, không mutate `classfileBuffer`, lỗi và giới hạn redefine.
- [Oracle Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): add/remove transformer và semantics concurrent class loading.
- [Oracle Java SE 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, agent manifest và lifecycle.
- [Oracle Java SE 17 — `LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): concurrent counters.
- [Oracle Java SE 17 — `ThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): per-thread guard và `remove()`.
- [JVMS Java SE 17 — Chapter 4](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): classfile, constant pool, method Code và StackMapTable.

**Ghi nhớ:** Callback nhanh không có nghĩa bỏ kiểm tra. Hãy dùng **fast filter rẻ, no-op `null`, parser/writer có điều kiện, logging ngoài callback và concurrency-safe state**, sau đó đo chi phí thực tế trên JVM mục tiêu. Tối ưu hiệu năng phải đi cùng tính đúng đắn của bytecode và vòng đời class loaders.
