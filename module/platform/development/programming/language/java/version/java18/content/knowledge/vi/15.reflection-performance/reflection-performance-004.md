# Tách chi phí tìm metadata, kiểm tra quyền, tạo adapter và thực thi đích khi đánh giá hiệu năng

## 1. Vì sao cần tách các loại chi phí?

Trong chương **Reflection và hiệu năng** của module `JAVA_VERSION_JAVA18`, mục tiêu không chỉ là biết `Method.invoke()` nhanh hay chậm. Khi một thư viện dùng Reflection API hoặc `MethodHandle` để gọi phương thức, tổng thời gian quan sát được có thể bao gồm nhiều công việc khác nhau:

- **Tìm metadata**: xác định `Class`, `Method`, `Field` hoặc `Constructor` ứng với tên và chữ ký cần dùng.
- **Xác nhận quyền truy cập**: kiểm tra caller có thể thực hiện thao tác hay không, hoặc thử bật truy cập sâu trong phạm vi JPMS cho phép.
- **Chuẩn bị adapter**: tạo và điều chỉnh `MethodHandle`, bind receiver, chuyển đổi kiểu tham số/trả về, hay tạo đối tượng gọi trung gian phù hợp với framework.
- **Thực thi đích**: thực hiện lời gọi thực tế, bao gồm dispatch, đóng/mở hộp giá trị, chuyển đổi đối số và chính logic của phương thức đích.

Nếu đưa tất cả vào một vòng lặp đo thời gian, kết quả không cho biết chi phí đến từ đâu. Đặc biệt, một phương thức được gọi hàng triệu lần qua adapter tái sử dụng có đặc điểm khác hẳn một phương thức chỉ gọi một lần nhưng phải tra cứu và chuẩn bị từ đầu.

Java 18 giới thiệu **JEP 416 — Reimplement Core Reflection with Method Handles**: phần triển khai nội bộ của các API reflection cốt lõi được xây dựng trên method handles. Thay đổi này không đồng nghĩa mọi phép gọi reflection và method handle có chi phí bằng nhau, cũng không bảo đảm một cách gọi luôn thắng trên mọi phiên bản JDK. Đối tượng `Method`, `MethodHandle`, điểm gọi, cách giữ tham chiếu, tối ưu JIT và công việc đích vẫn quyết định kết quả thực tế.

> Phạm vi kiến thức: các API `java.lang.reflect`, `java.lang.invoke`, module access và quy trình benchmark dưới đây vẫn được áp dụng trên các JDK hiện đại. Không sử dụng API nội bộ, cơ chế reflection cũ đã bị thay thế, hoặc số liệu benchmark từ JDK đời trước làm kết luận cho phiên bản hiện tại.

## 2. Sơ đồ vòng đời của một lời gọi động

```text
       Một lần khi khởi tạo                      Mỗi lần xử lý yêu cầu
┌──────────────────────────────┐          ┌──────────────────────────────┐
│ 1. Tìm metadata              │          │ 4. Thực thi đích             │
│    getMethod / getField      │          │    Method.invoke()           │
│    phân giải chữ ký          │          │    MethodHandle.invokeExact()│
├──────────────────────────────┤          │    kiểm tra/chuyển đổi cần có │
│ 2. Kiểm tra/cấu hình quyền   │          │    chạy logic ứng dụng       │
│    canAccess                 │          └──────────────────────────────┘
│    trySetAccessible (nếu cần)│                       ▲
├──────────────────────────────┤                       │
│ 3. Tạo/cấu hình adapter      │                       │ dùng lại
│    unreflect / findVirtual   │                       │
│    asType / bindTo           │───────────────────────┘
└──────────────────────────────┘
```

Một pipeline tối ưu thường chuẩn bị dữ liệu một lần khi cấu hình mapping, sau đó **tái sử dụng** đối tượng `Method` hoặc `MethodHandle` đã được kiểm tra. Nhưng không phải mọi hệ thống đều có vòng đời như vậy: framework quét lớp lúc khởi động cần đo **thời gian khởi tạo**, trong khi bộ chuyển đổi dữ liệu xử lý hàng triệu bản ghi cần đo **throughput và độ trễ thực thi lặp lại**.

Bốn phần ở sơ đồ là **nhóm công việc để thiết kế phép đo**, không phải bốn thao tác nội bộ cố định mà mọi JDK luôn thực hiện theo thứ tự ấy. Chẳng hạn `Method.invoke()` có thể thực hiện kiểm tra truy cập trong chính đường gọi; không thể đo `canAccess()` bên ngoài rồi khẳng định đã tách chính xác thời gian kiểm tra nội bộ bằng phép trừ.

## 3. Nhận diện từng giai đoạn

| Giai đoạn | Ví dụ API | Khi thường phát sinh | Cần phân biệt |
|---|---|---|---|
| Tìm metadata | `Class.getMethod()`, `getDeclaredMethod()`, `getDeclaredFields()` | Khởi tạo mapping hoặc mỗi lần gọi nếu thiết kế không cache | Tìm theo tên/chữ ký khác với liệt kê và lọc hàng loạt |
| Kiểm tra/cấu hình quyền | `canAccess(receiver)`, `trySetAccessible()` | Khởi tạo hoặc tại điểm gọi, tùy cách sử dụng | Kiểm tra quyền và **thay đổi trạng thái access override** là hai việc khác nhau |
| Tạo adapter | `Lookup.unreflect()`, `findVirtual()`, `MethodHandle.asType()`, `bindTo()` | Khởi tạo, hoặc lặp lại nếu không giữ adapter | Tạo mới, chuyển kiểu và bind receiver có thể khác chi phí |
| Gọi đích | `Method.invoke()`, `MethodHandle.invokeExact()`, mã Java thông thường | Mỗi lần xử lý | Kết quả gồm overhead gọi **và** công việc của target |
| Chuyển đổi dữ liệu | Boxing/unboxing, cast, spread/collect arguments | Có thể ở mỗi lần gọi | Thường dễ bị gộp nhầm vào “overhead reflection” |

Một `Method` đã được tìm và cache có thể vẫn phải áp dụng quy tắc kiểm tra quyền khi được gọi. `setAccessible(true)` và `trySetAccessible()` không phải mẹo tăng tốc dùng được cho mọi thành viên: chúng thay trạng thái truy cập với giới hạn do ngôn ngữ Java và hệ thống module áp đặt. Bật truy cập sâu không hợp lệ có thể bị từ chối; lựa chọn API công khai hoặc module `opens` thích hợp phải dựa trên nhu cầu thiết kế, không chỉ trên số benchmark.

### 3.1. Tìm metadata

Một ví dụ về **tìm theo chữ ký cụ thể**:

```java
Method method = Report.class.getMethod("score", long.class);
```

Khác với công việc **quét và chọn**:

```java
for (Method candidate : Report.class.getDeclaredMethods()) {
    if (candidate.getName().equals("score")) {
        // Còn phải đối chiếu parameter types và điều kiện khác.
    }
}
```

Hai hoạt động có cùng đích cuối nhưng khối lượng xử lý khác nhau. Khi benchmark, phải ghi rõ có tìm theo tên/chữ ký, duyệt toàn bộ tập metadata, đọc annotation, chuẩn hóa tên hay xây bảng ánh xạ hay không.

Không suy ra rằng `Class.getMethod(...)` luôn truy xuất một cache “miễn phí”: hành vi và cách cache nội bộ không phải hợp đồng về chi phí không đổi giữa các bản JDK.

### 3.2. Kiểm tra quyền truy cập

```java
Method method = Report.class.getMethod("score", long.class);
boolean accessibleNow = method.canAccess(new Report());
```

`canAccess(...)` chỉ trả lời **caller hiện tại có thể truy cập thành viên trong trạng thái hiện tại không**. Nó không gọi phương thức đích và không cung cấp con số đại diện đầy đủ cho mọi kiểm tra bên trong `invoke(...)`.

```java
Method privateMethod = Report.class.getDeclaredMethod("internalScore");
boolean enabled = privateMethod.trySetAccessible();
if (!enabled) {
    // Chọn API công khai hoặc cấu hình module hợp lệ.
}
```

Với `trySetAccessible()`, kết quả lần đầu có thể khác phép gọi lặp lại sau khi đã bật cờ. Benchmark gọi liên tục trên cùng một `Method` có thể chủ yếu đo **trạng thái đã được bật**, không đo thao tác khởi tạo ban đầu. Hãy tách phép đo một lần theo lifecycle và phép đo lặp cho lookup/hot path.

### 3.3. Tạo adapter

`MethodHandle` biểu diễn một lời gọi có kiểu phương thức rõ ràng. Có thể tìm handle bằng `MethodHandles.Lookup.findVirtual(...)`, hoặc chuyển một `Method` đã có bằng `Lookup.unreflect(...)` trong phạm vi quyền truy cập hợp lệ:

```java
Method method = Report.class.getMethod("score", long.class);

MethodHandle exact = MethodHandles.lookup().unreflect(method);
// Kiểu MethodHandle: (Report, long)long

MethodType genericType = MethodType.methodType(
        Object.class, Object.class, Object.class);

MethodHandle adapter = exact.asType(genericType);
// Kiểu adapter: (Object, Object)Object
```

Trong `adapter`, phép gọi có thể cần cast receiver từ `Object` về `Report`, unbox `Long` thành `long` và box kết quả `long` thành `Long`. Đây là các chi phí khác với tìm metadata. Bước `asType(...)` có thể tạo hoặc tái sử dụng adapter tùy thực thi; không được mặc định mỗi lần gọi luôn tạo một đối tượng mới.

Một adapter không cùng kiểu tham số với kiểu đích còn có thể thay đổi đường tối ưu hóa của JIT. Khi so sánh adapter `(Object,Object)Object` với lời gọi trực tiếp `(Report,long)long`, phải ghi rõ sự khác nhau về boxing và cast, thay vì quy toàn bộ chênh lệch cho “reflection”.

### 3.4. Thực thi đích

```java
long value = 42L;

// Gọi Java thông thường.
long a = report.score(value);

// Reflection đã cache Method.
long b = (Long) method.invoke(report, value);

// MethodHandle có kiểu chính xác.
long c = (long) exact.invokeExact(report, value);

// Adapter Object -> Object.
Object d = adapter.invokeExact(
        (Object) report, (Object) Long.valueOf(value));
```

Các biến `report`, `method`, `exact` và `adapter` được khởi tạo như ví dụ phía trên. `Method.invoke(...)` nhận đối số theo varargs `Object...`, có thể kéo theo boxing và mảng đối số trong những tình huống nhất định; các tối ưu JIT có thể thay đổi chi phí thực tế. `invokeExact(...)` yêu cầu kiểu tại điểm gọi khớp chính xác `MethodType`; kiểu trả về ở biểu thức và các phép cast tường minh cũng quan trọng.

Lời gọi trong benchmark có thể nhanh hơn hoặc chậm hơn một hướng khác tùy target, mức tối ưu, kiểu dữ liệu và việc inlining có xảy ra hay không.

## 4. Ví dụ tự chứa về cách đặt ranh giới đo

Đoạn mã sau minh họa **phân chia trách nhiệm** giữa phần khởi tạo và phần gọi. Nó không phải một benchmark thống kê; mục tiêu là nhìn thấy rõ những thao tác nào cần chuyển ra khỏi hot path.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public final class CachedInvocation {
    public static final class Report {
        public long score(long input) {
            return input * 31 + 7;
        }
    }

    private final Method reflected;
    private final MethodHandle exact;
    private final MethodHandle generic;

    public CachedInvocation() throws ReflectiveOperationException {
        // Giai đoạn 1: tìm metadata.
        reflected = Report.class.getMethod("score", long.class);

        // Giai đoạn 2: điều kiện truy cập ở thời điểm chuẩn bị.
        if (!reflected.canAccess(new Report())) {
            throw new IllegalAccessException("score is not accessible");
        }

        // Giai đoạn 3: tạo và cache các dạng lời gọi.
        exact = MethodHandles.lookup().unreflect(reflected);
        generic = exact.asType(MethodType.methodType(
                Object.class, Object.class, Object.class));
    }

    // Giai đoạn 4: không lặp lại lookup hay tạo adapter.
    public long invokeByMethod(Report target, long input)
            throws ReflectiveOperationException {
        return (Long) reflected.invoke(target, input);
    }

    public long invokeByExactHandle(Report target, long input)
            throws Throwable {
        return (long) exact.invokeExact(target, input);
    }

    public Object invokeByGenericAdapter(Report target, long input)
            throws Throwable {
        return (Object) generic.invokeExact(
                (Object) target, (Object) Long.valueOf(input));
    }

    public static void main(String[] args) throws Throwable {
        CachedInvocation caller = new CachedInvocation();
        Report report = new Report();

        System.out.println(caller.invokeByMethod(report, 5L));
        System.out.println(caller.invokeByExactHandle(report, 5L));
        System.out.println(caller.invokeByGenericAdapter(report, 5L));
    }
}
```

Kết quả mong đợi:

```text
162
162
162
```

Ở đây `canAccess(new Report())` hợp lệ vì `score` là phương thức instance công khai của lớp công khai, cùng môi trường truy cập phù hợp. Đối với member không công khai hoặc package trong named module, việc chuẩn bị có thể thất bại do quy tắc quyền truy cập; không được giả định `trySetAccessible()` luôn thành công.

Lớp ví dụ cũng cho thấy **tái sử dụng không đồng nghĩa cùng overhead gọi**. Dù cả `Method` và `MethodHandle` đều được cache, dạng đối số của `Method.invoke(...)` khác kiểu chính xác của `invokeExact(...)`. Hãy đo đường gọi đúng với cách sử dụng trong sản phẩm.

## 5. Thiết kế benchmark JMH tách pha

Một phép đo nghiêm túc thường dùng **JMH (Java Microbenchmark Harness)** để xử lý warmup, fork, trạng thái benchmark và tiêu thụ kết quả. JMH là công cụ benchmark riêng, **không phải API có sẵn trong JDK**; dự án cần khai báo `jmh-core` và annotation processor `jmh-generator-annprocess` với các phiên bản tương thích.

Ví dụ benchmark sau dùng các API Java hiện đại; giả định các dependency JMH đã được cài vào một dự án riêng. Đây là một *thiết kế đo để chạy thử và điều chỉnh theo môi trường thực tế*, không phải con số đo sẵn.

```java
package demo;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 8)
@Fork(3)
public class ReflectionPhasesBenchmark {

    public static final class Report {
        public long score(long x) {
            return x * 31L + 7L;
        }
    }

    @Param({"7", "1009"})
    public long input;

    private Report report;
    private Method cachedMethod;
    private MethodHandle cachedExact;
    private MethodHandle cachedGeneric;

    @Setup(Level.Trial)
    public void setup() throws ReflectiveOperationException {
        report = new Report();
        cachedMethod = Report.class.getMethod("score", long.class);
        cachedExact = MethodHandles.lookup().unreflect(cachedMethod);
        cachedGeneric = cachedExact.asType(MethodType.methodType(
                Object.class, Object.class, Object.class));
    }

    // 1. Tìm metadata: không thực thi target.
    @Benchmark
    public Method lookupMetadata() throws NoSuchMethodException {
        return Report.class.getMethod("score", long.class);
    }

    // 2. Kiểm tra quyền tường minh, không thực thi target.
    @Benchmark
    public boolean checkAccess() {
        return cachedMethod.canAccess(report);
    }

    // 3a. Chuẩn bị handle từ Method đã được tìm.
    @Benchmark
    public MethodHandle unreflectCachedMethod()
            throws IllegalAccessException {
        return MethodHandles.lookup().unreflect(cachedMethod);
    }

    // 3b. Thử tạo / tái sử dụng adapter cho kiểu tổng quát.
    @Benchmark
    public MethodHandle adaptCachedHandle() {
        MethodType type = MethodType.methodType(
                Object.class, Object.class, Object.class);
        return cachedExact.asType(type);
    }

    // 4a. Baseline với lời gọi Java thông thường.
    @Benchmark
    public long directCall() {
        return report.score(input);
    }

    // 4b. Hot path dùng Method đã cache.
    @Benchmark
    public long cachedReflectionCall()
            throws ReflectiveOperationException {
        return (Long) cachedMethod.invoke(report, input);
    }

    // 4c. Hot path dùng MethodHandle có kiểu chính xác.
    @Benchmark
    public long cachedExactHandleCall() throws Throwable {
        return (long) cachedExact.invokeExact(report, input);
    }

    // 4d. Hot path dùng adapter dạng Object.
    @Benchmark
    public Object cachedGenericHandleCall() throws Throwable {
        return (Object) cachedGeneric.invokeExact(
                (Object) report, (Object) Long.valueOf(input));
    }

    // Cố ý gộp lookup + invocation để thấy hệ quả của
    // thiết kế tìm metadata trên từng request.
    @Benchmark
    public long lookupAndCall() throws ReflectiveOperationException {
        Method method = Report.class.getMethod("score", long.class);
        return (Long) method.invoke(report, input);
    }
}
```

### Đọc các phương pháp trong benchmark

| Phương pháp | Nội dung chủ yếu được đo | Không nên kết luận |
|---|---|---|
| `lookupMetadata` | Tra cứu metadata theo tên và chữ ký | Không phải toàn bộ chi phí khởi động framework quét annotation |
| `checkAccess` | Lời gọi `canAccess` trên một member public đã cache | Không đo chính xác thời gian kiểm tra nội bộ trong mọi lần `invoke` |
| `unreflectCachedMethod` | Chuyển `Method` có sẵn sang handle hợp lệ | Không bao gồm tìm metadata ban đầu |
| `adaptCachedHandle` | Gọi `asType` cho một kiểu yêu cầu đã xác định | Không chắc đại diện cho lần tạo adapter đầu tiên; runtime có thể cache kết quả |
| `directCall` | Baseline với đường gọi thông thường và target | JIT có thể inline target |
| `cachedReflectionCall` | `Method.invoke` trên metadata đã cache, có boxing/kiểm tra cần thiết | Không phải overhead “thuần reflection” độc lập target |
| `cachedExactHandleCall` | `invokeExact` trên handle đã cache | Không bảo đảm nhanh hơn reflection ở mọi JDK |
| `cachedGenericHandleCall` | Adapter với chuyển đổi `Object` và boxing | Không so sánh đồng dạng kiểu với `directCall` |
| `lookupAndCall` | Thiết kế lookup + gọi ở từng operation | Không phải chi phí hot path của ứng dụng đã cache `Method` |

**Một phép đo không nhất thiết đại diện cho một “chi phí thuần”.** Chẳng hạn kết quả `cachedReflectionCall` gồm phương thức đích, truyền đối số, xử lý kiểu và chi phí của cơ chế gọi. Nếu lấy thời gian này trừ `directCall`, phần chênh lệch chỉ là **một quan sát trong điều kiện benchmark**; nó không phải hằng số “overhead reflection” có thể đem áp dụng mọi nơi. Hai đường gọi có thể được JIT tối ưu hóa khác nhau, bao gồm inlining, escape analysis và loại bỏ allocation.

`@State(Scope.Thread)` giúp mỗi luồng benchmark có trạng thái riêng, tránh benchmark đo nhầm tranh chấp đồng bộ giữa các luồng. Nếu thực tế dùng cache chung hoặc xử lý đồng thời, hãy thiết kế thêm trường hợp `Scope.Benchmark` và benchmark đa luồng tương ứng. Đừng tự suy luận khả năng mở rộng đa luồng chỉ từ benchmark đơn luồng.

### Kiểm tra quyền và adapter khi khởi tạo: đo riêng thời gian lạnh

`checkAccess` trong JMH chỉ đo `canAccess` trên `Method` đã tồn tại; `adaptCachedHandle` có thể tận dụng adapter đã được tạo trong warmup hoặc bộ nhớ đệm nội bộ. Muốn đo **cold setup**, hãy làm một thí nghiệm khác:

1. Khởi chạy JVM mới và ghi nhận thời gian chuẩn bị metadata, quyền truy cập và adapter ở **lần tạo đầu tiên**.
2. Đo trên nhiều JVM fork độc lập, khống chế cùng JDK, module path, classpath và trạng thái cấu hình.
3. Không trộn số liệu có class loading, initialization hoặc I/O vào nhãn “chỉ metadata lookup” nếu các phần đó chưa được đo riêng.
4. Báo cáo riêng tổng thời gian cấu hình một bộ adapter thực tế, số thành viên xử lý, mức phân tán thời gian và cấu hình JVM.
5. Với `trySetAccessible()`, phân biệt lần thử đầu tiên, trường hợp trả `false` và lần gọi lại sau khi thành công; không gom chúng thành một trường hợp “kiểm tra quyền” đồng nhất.

Nếu dùng JMH cho one-shot setup, cần cấu hình phép đo hợp lý (ví dụ `Mode.SingleShotTime` và fork JVM mới) và ghi rõ thời điểm class loading/initialization. Trong nhiều dự án, đo **thời gian khởi tạo toàn bộ component** bằng dấu mốc ứng dụng/JFR, kết hợp profile các bước thành phần, hữu ích hơn cố đo một đối tượng adapter đơn lẻ ở mức nanosecond.

## 6. Cách diễn giải chi phí khởi tạo và chi phí lặp lại

Giả sử đường gọi A và B có các đại lượng:

- `S_A`, `S_B`: tổng thời gian chuẩn bị metadata, quyền và adapter, **chỉ tính khi khởi tạo**.
- `C_A`, `C_B`: chi phí trung bình của một lần gọi (bao gồm logic đích) khi hệ thống đã ở trạng thái ổn định.
- `N`: số lần gọi sử dụng cùng một cấu hình.

Một mô hình dự toán đơn giản:

```text
T_A(N) ≈ S_A + N × C_A
T_B(N) ≈ S_B + N × C_B
```

Nếu B tốn nhiều setup hơn (`S_B > S_A`) nhưng có chi phí gọi thấp hơn (`C_B < C_A`), số lần gọi để thu hồi chi phí chuẩn bị tăng thêm, theo mô hình tuyến tính, là:

```text
N > (S_B - S_A) / (C_A - C_B)
```

Đây là **mô hình để ra quyết định**, không phải công thức tính chính xác CPU time của mọi ứng dụng. Warmup JIT, GC, phân bổ đối tượng, độ lệch giữa các request và contention khiến dữ liệu thực tế không luôn tuyến tính. Khi chọn giải pháp, cần báo cáo cả thời gian khởi động, throughput, latency (nhất là p95/p99) và allocation; một tối ưu giúp throughput tốt hơn có thể làm startup chậm hơn.

### Ví dụ tính toán giả định

Giả sử **dữ liệu minh họa**, không phải số đo từ JDK:

| Phương án | Chuẩn bị một lần | Mỗi lần gọi ổn định |
|---|---:|---:|
| A: reflection đã cache | 5 µs | 100 ns |
| B: adapter kiểu cụ thể đã cache | 25 µs | 60 ns |

Ở đây chi phí chuẩn bị thêm là 20 µs và tiết kiệm mỗi lần gọi là 40 ns. Theo mô hình đơn giản, điểm hòa vốn vào khoảng **500 lần gọi** (`20.000 / 40`). Nhưng nếu một adapter chỉ được dùng vài lần, đầu tư tạo adapter có thể không đáng; nếu dùng hàng triệu lần, hiệu năng hot path mới trở thành trọng tâm. Những con số giả định này không được dùng để khẳng định tốc độ thực tế của Reflection hay MethodHandle.

## 7. Các bẫy benchmark làm sai kết luận

### 7.1. Đo lookup và call chung nhưng đặt tên “reflection invoke”

```java
// Trộn tìm metadata và thực thi:
Method m = Report.class.getMethod("score", long.class);
return (Long) m.invoke(report, input);
```

Nếu production chỉ tra cứu `Method` khi khởi tạo, benchmark trên đo quá nhiều công việc cho đường gọi thật. Ngược lại, nếu production đang tra cứu theo từng request, benchmark chỉ gọi `cachedMethod.invoke(...)` lại đánh giá thấp tổng chi phí.

**Cách xử lý:** giữ ít nhất hai trường hợp riêng: **lookup + call** và **cached call**; sau đó đo lookup độc lập. Cùng logic đích, cùng đối số, cùng cấu hình quyền.

### 7.2. Dùng `System.nanoTime()` bao một lời gọi rồi kết luận

Độ phân giải đồng hồ, nhiễu lịch CPU, warmup JIT và các tối ưu hóa chạy cùng lúc có thể lớn hơn chênh lệch giữa hai cách gọi. Một kết quả đơn lẻ như “x ns” không đủ cơ sở để chọn kiến trúc.

**Cách xử lý:** dùng harness có warmup/fork và báo phân tán số liệu. Với chức năng quan trọng, đo thêm tình huống end-to-end và phân tích profile thực tế.

### 7.3. Target quá nhỏ hoặc bị tối ưu mất

Một target chỉ trả hằng số có thể bị JIT inline, constant-fold hoặc loại bỏ nếu kết quả không được quan sát. Tương tự, nếu chỉ benchmark `getMethod()` mà không dùng đối tượng trả về, compiler có thể tối ưu khác dự kiến.

**Cách xử lý:** đưa giá trị thay đổi có kiểm soát vào target, trả kết quả từ `@Benchmark` hoặc đưa vào `Blackhole`, và giữ workload phản ánh công việc thật. Tuy vậy, một benchmark có target rất nhỏ vẫn hữu ích để đánh giá một số dạng overhead — miễn là ghi đúng phạm vi.

### 7.4. So sánh các đường gọi với kiểu dữ liệu khác nhau

`Method.invoke(...)` nhận `Object...` và trả `Object`; `MethodHandle.invokeExact(...)` có thể có kiểu primitive chính xác; adapter `asType` kiểu tổng quát còn có thêm cast/boxing. Kết luận “A nhanh hơn B” có thể thực chất là “A ít boxing hơn B”.

**Cách xử lý:** đo tối thiểu hai nhóm:

- **Cùng kiểu và cùng khả năng cache** để tìm hiểu cơ chế gọi.
- **Đúng kiểu adapter mà ứng dụng đang dùng** để đo overhead thực tế của kiến trúc.

Luôn báo kiểu `MethodType`, cách truyền đối số và việc có `Object[]` hay không.

### 7.5. Dựa vào một JDK hoặc một cách giữ handle

JEP 416 liên quan đến chi tiết triển khai của Core Reflection và cách JIT nhìn thấy các đối tượng reflection. Cùng một chương trình có thể biểu hiện khác khi tham chiếu `Method`/`MethodHandle` được giữ trong trường ổn định, trong collection có thay đổi, hoặc được tra cứu lại liên tục. Các tối ưu nội bộ cũng tiến triển qua phiên bản JDK.

**Cách xử lý:** kiểm chứng trên **JDK thực sự triển khai**, chế độ chạy và cấu hình thực; không suy diễn thứ tự hiệu năng cố định từ benchmark của JDK 18 cho mọi JDK mới hơn.

### 7.6. Bỏ qua quyền truy cập và module

Benchmark trong classpath với member `public` không đại diện cho framework chạy trên module path, phải dùng `privateLookupIn(...)` hoặc `trySetAccessible()` trong package được mở. Việc tra metadata thành công không đồng nghĩa thao tác gọi hợp lệ.

**Cách xử lý:** mô phỏng đúng cấu hình `exports`/`opens`, quyền của caller và loại member. Không được giảm quyền kiểm soát truy cập trong sản phẩm chỉ vì benchmark nhanh hơn.

### 7.7. Chỉ báo một giá trị trung bình

Trung bình thời gian một thao tác không mô tả được phần đuôi độ trễ do class loading, lazy initialization, lần đầu tạo adapter, GC hoặc tranh chấp. Nếu pipeline tạo mapping lúc khởi động, chậm vài trăm milliseconds có thể ảnh hưởng trực tiếp đến thời gian sẵn sàng của dịch vụ ngay cả khi hot path rất nhanh.

**Cách xử lý:** phân biệt benchmark micro với số liệu startup, allocation, tải đa luồng và p95/p99 latency đo ở cấp ứng dụng.

## 8. Phương pháp đo nhất quán trên JDK hiện đại

Một quy trình thực dụng:

1. **Chọn workload đại diện.** Xác định loại member (method/constructor/field), public hay private, số lượng member, kiểu đối số và tần suất gọi.
2. **Phác họa lifecycle.** Chỉ rõ chỗ gọi `getDeclaredMethod`, `canAccess`/`trySetAccessible`, `unreflect`/`asType` và `invoke`; ghi chú thành phần được cache.
3. **Kiểm chứng tính đúng đắn.** Các phương án phải trả cùng giá trị và xử lý cùng ngoại lệ; đừng benchmark một adapter sai chữ ký hoặc khác semantics.
4. **Đo setup riêng.** Báo thời gian tìm metadata, xác nhận quyền và tạo adapter theo một JVM/lượt khởi tạo; kiểm tra class loading.
5. **Đo hot path riêng.** Dùng JMH với warmup, các fork JVM độc lập, input không hằng và kết quả được tiêu thụ.
6. **So sánh dạng gọi tương xứng.** Giữ giống nhau target, dữ liệu, đối tượng receiver và điều kiện cache; ghi rõ boxing/conversion còn tồn tại.
7. **Đo ở cấp ứng dụng.** Kiểm tra allocation, throughput, latency và startup bằng công cụ quan sát như JDK Flight Recorder nếu cần; tối ưu cục bộ không bảo đảm cải thiện trải nghiệm tổng thể.
8. **Ghi lại điều kiện chạy.** JDK vendor/version, JVM flags, hệ điều hành, CPU, số luồng, heap, classpath/module path, JMH mode/forks, số lần đo, sai số/phân tán và nguồn của các số liệu.
9. **Quyết định theo ngữ cảnh.** Nếu metadata chỉ tra một lần, việc cache thường là lựa chọn thiết kế rõ ràng; chỉ thay đường gọi bằng `MethodHandle` hoặc adapter khác khi đo chứng minh lợi ích phù hợp với nhu cầu.
10. **Lặp lại sau khi nâng JDK.** Tối ưu JIT/Reflection có thể thay đổi; bảo vệ hợp đồng API bằng test và hiệu năng bằng phép đo tái lập, không bằng giả định cố định.

### Mẫu bảng báo cáo kết quả

| Thí nghiệm | Đo được gì | Đơn vị phù hợp | Điều kiện cần ghi |
|---|---|---|---|
| Discovery riêng | Thời gian `getMethod`/quét metadata | µs mỗi mapping hoặc ns mỗi lookup | Số member, loại lookup, warm/cold |
| Access setup riêng | Thời gian xác minh/cấu hình quyền | µs mỗi mapping | Public/private, module `opens`, cờ đã bật chưa |
| Adapter setup riêng | Thời gian `unreflect`/`asType`/`bindTo` | µs mỗi adapter | Kiểu handle, có tái sử dụng/cache không |
| Cached invocation | Thời gian lời gọi lặp | ns/op, ops/s | Target, input, kiểu args, JDK/JIT |
| Full initialization | Thời gian chuẩn bị mọi mapping | ms cho component | Class loading, số mapping, dependency |
| Tải dịch vụ | Latency/throughput/allocation | p95/p99, req/s, B/op | Số luồng, workload, GC, máy chạy |

Không điền “giá trị điển hình” vào bảng nếu chưa có kết quả từ một môi trường đo xác định. Số đo thực tế mới cho phép kết luận đường gọi nào phù hợp.

## 9. Câu hỏi tự kiểm tra

1. Vì sao `getMethod(...).invoke(...)` trong cùng một phép đo không phản ánh chính xác chi phí thực thi của một `Method` đã cache?
2. `canAccess(...)` và `trySetAccessible()` có đo cùng một hoạt động không? Vì sao benchmark `trySetAccessible` lặp lại trên cùng `Method` dễ gây hiểu nhầm?
3. Khi `MethodHandle` có kiểu `(Report,long)long` được `asType` thành `(Object,Object)Object`, những phép chuyển đổi nào có thể được thêm vào đường gọi?
4. Tại sao không thể xem `cachedReflectionCall - directCall` là một hằng số overhead reflection cho mọi workload?
5. Nếu chi phí tạo adapter tăng nhưng mỗi lần gọi nhanh hơn, tần suất sử dụng adapter ảnh hưởng thế nào đến thời gian tổng?
6. Sau khi nâng JDK, vì sao phải chạy lại benchmark thay vì dùng nguyên thứ tự hiệu năng từng quan sát trên JDK 18?

**Ghi nhớ:** Để đánh giá Reflection và MethodHandle đúng, trước hết phải xác định đang đo **tìm metadata**, **kiểm tra/cấu hình quyền**, **chuẩn bị adapter** hay **gọi đích**. Cache và đo riêng chi phí setup khi thích hợp, đo hot path trong môi trường được kiểm soát, rồi đối chiếu với startup và hành vi thực tế của ứng dụng trên JDK đang sử dụng.
