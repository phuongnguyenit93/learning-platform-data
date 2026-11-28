# Thực hành đánh giá cache và lựa chọn reflection hoặc MethodHandle bằng bằng chứng trên JDK đang dùng

## 1. Mục tiêu và phạm vi

Một framework xử lý nhiều đối tượng thường phải xác định rồi gọi method theo cấu hình: bộ ánh xạ dữ liệu, hệ thống plugin, thư viện serialization, dependency injection hoặc dispatcher. Nếu tìm method mỗi lần gọi, ứng dụng có thể tốn chi phí tra cứu metadata. Nhưng khi đã cache, liệu `Method.invoke()` hay `MethodHandle.invokeExact()` nhanh hơn? **Không có câu trả lời đúng cho mọi JDK, call site và workload.**

Bài thuộc chương **Reflection và hiệu năng** trong module `JAVA_VERSION_JAVA18`. Module xem xét các thay đổi từ Java 18 vẫn hữu ích trên JDK hiện đại, đồng thời yêu cầu kiểm chứng hành vi Reflection, MethodHandle trên phiên bản JDK đang dùng. Điểm xuất phát là JEP 416 của JDK 18: Core Reflection được triển khai lại dựa trên method handles. Vì vậy, các nhận định hiệu năng từ thời triển khai Reflection cũ không nên được áp dụng máy móc cho JDK hiện nay.

Sau bài học, bạn có thể:

- Phân biệt **chi phí tra cứu method**, **chi phí chuẩn bị lời gọi** và **chi phí gọi nhiều lần**.
- Thiết kế phép đo cho direct call, cached `Method`, cached `MethodHandle` và lookup mỗi lần.
- Dùng JMH để hạn chế sai lệch do JIT compilation, dead-code elimination và thiếu warmup.
- Hiểu lợi ích cũng như rủi ro của cache với `static final`, cache instance và class loader động.
- Xem xét signature, boxing/unboxing, exception và quyền truy cập khi so sánh hai API.
- Ghi kết quả có JDK/vendor/VM flags, đơn vị, số fork, warmup và mức biến động.
- Đưa ra quyết định triển khai dựa trên **bằng chứng đo tại môi trường thực**, không dựa vào khẩu hiệu.

**Giới hạn:** bài cung cấp chương trình benchmark và quy trình đo, không bịa số liệu `ns/op` cho JDK chưa được chạy. Người học phải thực thi trên JVM và phần cứng mục tiêu để điền kết quả.

## 2. Cần hiểu đúng JEP 416 trước khi so sánh

Từ JDK 18, JEP 416 tái triển khai `java.lang.reflect.Method`, `Constructor` và `Field` bằng cơ chế `java.lang.invoke`. Đây chủ yếu là thay đổi cách JDK triển khai nội bộ, không phải thay đổi hợp đồng public API buộc ứng dụng bỏ Reflection.

Hệ quả về hiệu năng:

- Không thể giả định Core Reflection hiện tại luôn đi qua một cơ chế native cũ tách biệt hoàn toàn với MethodHandle.
- Khi đối tượng `Method` hoặc `Field` được giữ ở vị trí có thể được JIT coi là hằng, chẳng hạn `static final` trong một số tình huống, tối ưu hóa có thể khác đáng kể so với metadata nằm ở field biến động.
- `MethodHandle` là tham chiếu gọi có kiểu cụ thể; `invokeExact` có thể phù hợp với JIT nếu call site ổn định, nhưng vẫn phụ thuộc kiểu, mức đa hình, cách lưu handle và workload.
- Không có bảo đảm API rằng mọi lời gọi cached `MethodHandle` phải nhanh hơn mọi lời gọi cached `Method`.

JEP 416 **không** phải lý do sử dụng một công tắc quay lại cách triển khai Reflection cũ. Các workaround lịch sử cho những phiên bản JDK chuyển tiếp không phải nền tảng tối ưu hóa hiện đại. Thực hành đúng là đo lại trên JDK đang chạy.

### Sơ đồ chi phí

~~~text
Yêu cầu thực tế
    |
    v
Xác định declaring class, tên và chữ ký
    |
    +-- Discovery: getMethod / getDeclaredMethod / Lookup.findVirtual
    |
    v
Kiểm tra quyền và chuẩn bị cơ chế gọi
    |
    +-- Cache Method hoặc MethodHandle theo khóa hợp lệ
    |
    v
Lặp lời gọi tới cùng method
    |
    +-- Method.invoke(...)
    +-- MethodHandle.invokeExact(...) hoặc invoke(...)
    |
    v
Kiểm tra kết quả, độ trễ, allocation, exception, correctness
~~~

Nếu một method chỉ được gọi **một lần**, chi phí chuẩn bị có thể chi phối tổng thời gian. Nếu cùng method được gọi **hàng triệu lần**, chi phí mỗi lần gọi và khả năng JIT tối ưu có thể quan trọng hơn. Phải đo đúng cơ cấu của ứng dụng.

## 3. Phân loại chi phí trước khi benchmark

| Chi phí | Ví dụ | Nên đo thế nào |
| --- | --- | --- |
| Tra cứu metadata | `clazz.getMethod("compute", long.class)` | Benchmark riêng đường lookup; không trộn với baseline cached rồi kết luận về invoke. |
| Tạo MethodHandle | `lookup.findVirtual(...)` | Tách khỏi đường gọi steady-state hoặc đo end-to-end nếu mỗi request đều tạo handle. |
| Gọi thực tế | `Method.invoke`, `MethodHandle.invokeExact` | Lookup hoàn tất trước phép đo. |
| Chuyển đổi giá trị | Boxing/unboxing khi `Method.invoke` trả về `Object`; `asType` khi thích nghi MethodHandle | Ghi rõ kiểu tham số và return, so sánh đường đi giống ứng dụng. |
| Kiểm tra quyền | Access checks khi tạo handle và theo hợp đồng Reflection | Dùng cùng mức truy cập hợp lệ; không đo thủ thuật phá JPMS. |
| Hạ tầng ứng dụng | Key construction, map lookup, logging, dispatch, validation | Đo riêng và đo thêm end-to-end để thấy tỷ lệ chi phí thực. |

Một benchmark chỉ so sánh lệnh invoke **không** chứng minh rằng chuyển toàn bộ framework sang MethodHandle giúp nhanh hơn. Ngược lại, nếu mỗi request đang dùng `getDeclaredMethod`, cache metadata có thể tạo khác biệt lớn dù chọn API gọi nào.

## 4. Điều kiện cần kiểm soát để có kết quả đáng tin

JVM tối ưu mạnh sau khi mã đã chạy đủ nhiều lần. Vì vậy, một đoạn `System.nanoTime()` chạy vài vòng trong `main` dễ cho kết quả sai:

~~~java
// Không dùng mẫu này để kết luận hiệu năng.
long start = System.nanoTime();
for (int i = 0; i < 1_000; i++) {
    method.invoke(target, i);
}
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
~~~

Các vấn đề có thể gặp:

1. Warmup chưa đủ để HotSpot biên dịch code nóng.
2. JIT có thể khử lời gọi hoặc tính toán nếu kết quả không được sử dụng.
3. Measurement trộn thời gian khởi tạo, lookup, JIT compilation và GC.
4. Tần số CPU, scheduler, thermal throttling và hoạt động nền làm nhiễu kết quả.
5. Benchmark quá nhỏ có thể đo cả phần overhead của vòng lặp/harness.
6. Các lần thử ở cùng JVM có thể chia sẻ profile, code cache hoặc trạng thái GC.
7. Chỉ đọc một số trung bình không cho biết độ ổn định giữa các lần chạy.

**Dùng JMH (Java Microbenchmark Harness)** để thiết kế benchmark JVM có warmup, measurement và fork rõ ràng. JMH giúp kiểm soát nhiều lỗi phổ biến, nhưng không thay thế việc suy nghĩ đúng về workload.

## 5. Chuẩn bị môi trường và lưu vết cấu hình

Trước khi chạy JMH, ghi lại phiên bản Java và JVM:

~~~sh
java -version
javac -version
java -XshowSettings:vm -version
~~~

Lưu thêm:

- JDK vendor, version đầy đủ, patch/build và kiến trúc CPU.
- Hệ điều hành, số core, môi trường vật lý/container và mức giới hạn CPU/memory.
- VM flags thực sự dùng; có `-Xms`, `-Xmx` hoặc tùy chọn GC khác mặc định hay không.
- Phiên bản JMH, số forks, warmup iterations, measurement iterations và threads.
- Mục tiêu đo: throughput hay average time, `ns/op` hay `ops/s`.
- Dữ liệu đầu vào, loại method, độ phức tạp method và hình dạng call site.

Khi so sánh hai bản JDK, giữ workload, phần cứng và cách đo tương đương. Nếu framework chạy với nhiều thread hoặc nhiều class loader, cũng cần benchmark các yếu tố đó; chỉ đo single-thread sẽ bỏ sót contention hoặc tính đa hình.

## 6. Tạo dự án benchmark với JMH

Cách đơn giản theo hướng dẫn chính thức của OpenJDK JMH là tạo dự án Maven độc lập bằng archetype:

~~~sh
mvn archetype:generate -DinteractiveMode=false \
  -DarchetypeGroupId=org.openjdk.jmh \
  -DarchetypeArtifactId=jmh-java-benchmark-archetype \
  -DgroupId=org.sample \
  -DartifactId=reflection-cache-bench \
  -Dversion=1.0
~~~

Lệnh được trình bày theo cú pháp shell Linux/macOS; trên Windows PowerShell hãy viết thành một dòng hoặc dùng ký tự nối dòng của PowerShell.

Sau khi tạo dự án, thêm tệp `src/main/java/org/sample/ReflectionCacheBenchmark.java`. Archetype cung cấp dependency và annotation processor của JMH để tạo benchmark runner. **Chỉ thêm `jmh-core` mà không cấu hình annotation processor chưa đủ** để dự án JMH hoạt động đúng.

Build và chạy:

~~~sh
cd reflection-cache-bench
mvn clean verify
java -jar target/benchmarks.jar ReflectionCacheBenchmark
~~~

Nếu Maven hoặc JDK trên máy chưa có sẵn, hãy chuẩn bị theo quy trình của dự án. Không thay đổi JDK đang dùng để đạt số đẹp: mục tiêu là đo **trên JVM thực sự sẽ triển khai**.

## 7. Benchmark: direct, cached reflection và cached MethodHandle

Ví dụ cố ý dùng một method public nhận/trả về `long`, cùng target và cùng giá trị đầu vào. So sánh nhiều đường gọi nhưng dùng chung nghiệp vụ.

Tệp `src/main/java/org/sample/ReflectionCacheBenchmark.java`:

~~~java
package org.sample;

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
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
public class ReflectionCacheBenchmark {

    public static final class Calculator {
        public long compute(long value) {
            return Long.rotateLeft(value * 31 + 17, 7);
        }
    }

    private static final Method STATIC_METHOD;
    private static final MethodHandle STATIC_HANDLE;

    static {
        try {
            STATIC_METHOD =
                    Calculator.class.getMethod("compute", long.class);
            STATIC_HANDLE = MethodHandles.lookup().findVirtual(
                    Calculator.class,
                    "compute",
                    MethodType.methodType(long.class, long.class));
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private final Calculator target = new Calculator();

    @Param({"13", "97"})
    public long input;

    private Method stateMethod;
    private MethodHandle stateHandle;

    @Setup(Level.Trial)
    public void prepare() {
        stateMethod = STATIC_METHOD;
        stateHandle = STATIC_HANDLE;
    }

    @Benchmark
    public long direct() {
        return target.compute(input);
    }

    @Benchmark
    public long reflectionCachedStaticFinal() throws Exception {
        return (long) STATIC_METHOD.invoke(target, input);
    }

    @Benchmark
    public long reflectionCachedInState() throws Exception {
        return (long) stateMethod.invoke(target, input);
    }

    @Benchmark
    public long reflectionLookupEachCall() throws Exception {
        Method method =
                Calculator.class.getMethod("compute", long.class);
        return (long) method.invoke(target, input);
    }

    @Benchmark
    public long handleCachedStaticFinal() throws Throwable {
        return (long) STATIC_HANDLE.invokeExact(target, input);
    }

    @Benchmark
    public long handleCachedInState() throws Throwable {
        return (long) stateHandle.invokeExact(target, input);
    }

    @Benchmark
    public long handleLookupEachCall() throws Throwable {
        MethodHandle handle = MethodHandles.lookup().findVirtual(
                Calculator.class,
                "compute",
                MethodType.methodType(long.class, long.class));
        return (long) handle.invokeExact(target, input);
    }
}
~~~

### Giải thích thiết kế

- `direct` là baseline: lời gọi Java trực tiếp. Nó không phải một lựa chọn thay thế luôn khả thi nếu tên method chỉ được biết ở runtime.
- `reflectionCachedStaticFinal` cache một `Method` tĩnh, cho JIT một vị trí metadata ổn định.
- `reflectionCachedInState` đọc `Method` từ state của benchmark, mô phỏng metadata không nằm trực tiếp trong field hằng tĩnh. Đây **không** phải mô hình đầy đủ của cache động.
- `reflectionLookupEachCall` cố ý tra cứu metadata mỗi lần để thấy tác động tiềm năng của lookup.
- `handleCachedStaticFinal` dùng `MethodHandle` đã tạo trước, đúng chữ ký `(Calculator, long)long`.
- `handleCachedInState` gọi handle lấy từ state của benchmark.
- `handleLookupEachCall` tạo/tra cứu handle trong hot path, phản ánh cách dùng thường cần tránh nếu method ổn định.

Mọi benchmark trả về `long`, để JMH tiêu thụ kết quả và hạn chế dead-code elimination. `@Param` tạo nhiều giá trị đầu vào để bài đo không chỉ xử lý một literal cố định.

**Không diễn giải sai:** ngay cả benchmark có tên “lookupEachCall” cũng có thể được JIT tối ưu hóa phần lookup khi class và tên method là hằng. Nếu muốn đo metadata discovery thực sự động trong framework, cần thêm kịch bản với tập class/name/signature thay đổi và cache-miss rate theo phân bố thật.

### Tại sao `invokeExact` phải có kiểu chính xác?

`STATIC_HANDLE.type()` tương đương:

~~~text
(Calculator,long)long
~~~

Lời gọi:

~~~java
long answer = (long) STATIC_HANDLE.invokeExact(target, input);
~~~

phải khớp kiểu receiver, tham số và return tại call site. Bỏ cast return hoặc truyền `Object` thay vì `Calculator` có thể gây `WrongMethodTypeException`. `MethodHandle.invoke` cho phép một số chuyển đổi bằng cơ chế `asType`; điều đó có thể thay đổi kết quả đo. Khi ứng dụng thực sự dùng `invoke` với chuyển đổi, hãy benchmark chính đường đó, không lấy `invokeExact` làm đại diện.

## 8. Chạy benchmark, thu kết quả và kiểm tra tính hợp lệ

Lệnh minh họa chạy riêng bài benchmark và ghi kết quả JSON:

~~~sh
java -jar target/benchmarks.jar ReflectionCacheBenchmark \
  -rf json -rff target/reflection-cache-results.json
~~~

Cấu hình warmup/measurement/fork trong annotation được JMH sử dụng; các tùy chọn dòng lệnh có thể ghi đè khi cần. Chạy `java -jar target/benchmarks.jar -h` để xem khả năng của phiên bản JMH đã cài.

Đối với benchmark có `Mode.AverageTime`, đơn vị `ns/op` càng thấp thường càng tốt cho cùng semantics và cùng workload. `Score Error` và khoảng biến thiên giữa fork cũng quan trọng; nếu hai kết quả gần nhau trong sai số, **không nên khẳng định một bên thắng**.

Mẫu bảng ghi kết quả **để người học điền sau khi chạy**, không phải số liệu đo sẵn:

| Kịch bản | JDK / VM | ns/op | Score error | B/op (nếu đo GC profiler) | Ghi chú |
| --- | --- | ---: | ---: | ---: | --- |
| Direct call | ... | ... | ... | ... | Baseline tối ưu của Java source |
| Method cached static final | ... | ... | ... | ... | Metadata hằng |
| Method cached in state | ... | ... | ... | ... | Metadata qua state |
| Method lookup mỗi lần | ... | ... | ... | ... | Discovery và invocation |
| MethodHandle cached static final | ... | ... | ... | ... | Exact signature |
| MethodHandle cached in state | ... | ... | ... | ... | Handle qua state |
| MethodHandle lookup mỗi lần | ... | ... | ... | ... | Lookup + invocation |

Đo allocation nếu cần:

~~~sh
java -jar target/benchmarks.jar ReflectionCacheBenchmark \
  -prof gc -rf json -rff target/reflection-cache-gc.json
~~~

`gc.alloc.rate.norm` là một trong các phép đo quan trọng để xác định boxing hoặc mảng đối số tạo ra lượng cấp phát đáng kể hay không. Không chỉ nhìn `ns/op` rồi kết luận API nào phù hợp cho hệ thống tải cao.

### Cần benchmark thêm kịch bản thực tế

Kết quả trên chỉ phản ánh method `compute(long)` rất ngắn trong một class cụ thể. Để lựa chọn cho ứng dụng, nên bổ sung các trường hợp:

1. Method có logic thật (validation, dữ liệu, I/O), để đo tỷ trọng overhead.
2. Nhiều kiểu receiver, nhiều method, call site đa hình.
3. Tham số là `Object`, primitive, array, varargs hoặc kiểu cần ép đổi.
4. Cache hit/miss theo phân bố thực tế; cold start và steady-state tách riêng.
5. Nhiều thread truy cập cache với contention hoặc cache miss đồng thời.
6. Module/class loader khác nhau, nhất là framework plugin hoặc ứng dụng modular.
7. Lỗi invocation/exception nếu đây là một phần đường đi thường gặp.
8. Nếu service nhạy cảm với tail latency, đo thêm mẫu độ trễ bằng `Mode.SampleTime` hoặc công cụ end-to-end tương ứng; `AverageTime` không tự cung cấp kết luận p99 của request.

## 9. Cache đúng cái gì, ở đâu và trong bao lâu?

Có ít nhất ba lớp cache khác nhau:

| Đối tượng cache | Ví dụ | Lợi ích | Rủi ro |
| --- | --- | --- | --- |
| Tra cứu Reflection | `Method`, `Constructor`, `Field` | Tránh lặp `getDeclaredMethod`/`getMethod` và duyệt metadata | Khóa sai, bỏ sót overload; class loader leak |
| MethodHandle đã chuẩn bị | `MethodHandle` từ `findVirtual` hoặc `unreflect` | Tránh lặp lookup, tạo/adapt handle | Call site sai `MethodType`; rò rỉ capability truy cập |
| Dispatcher hoặc lời gọi đã thích nghi | `MethodHandle.asType`, `bindTo`, combinators | Tránh xây chuỗi thích nghi mỗi request | Khóa gắn nhầm receiver, dữ liệu, quyền và ngữ cảnh |

### Khóa cache phải phản ánh danh tính method

Đừng cache chỉ theo tên `"compute"` nếu class có overload. Một khóa thường cần:

- `Class<?>` của declaring hoặc lookup class; đối tượng `Class` đã mang danh tính class loader.
- Tên method và danh sách kiểu tham số runtime theo đúng thứ tự.
- Return type nếu công cụ cần nhận diện method theo JVM descriptor hoặc phân biệt bridge method.
- Loại thao tác: instance/static, constructor, field getter/setter.
- Ngữ cảnh quyền truy cập và `MethodHandles.Lookup` khi điều này ảnh hưởng cách tạo handle.

Không dùng một chuỗi ghép `className + "#" + methodName` làm khóa duy nhất cho môi trường đa class loader. Hai class cùng tên do hai loader khác nhau có thể là hai type hoàn toàn khác nhau.

### Cache Method có thể không tương đương cache kết quả xử lý

Một số framework phải duyệt annotation, phân tích generic, tạo adapter hoặc validation. Phần chi phí lớn đôi khi nằm ở **metadata parsing** chứ không phải `Method.invoke`. Cache kết quả phân tích (ví dụ mapping schema → accessor) có thể hiệu quả hơn việc chỉ cache raw `Method`. Hãy dùng profiling để xác định chỗ tốn thời gian.

## 10. Ví dụ cache theo ClassValue

Khi dùng plugin hoặc class loader có thể được dỡ bỏ, `static Map<Class<?>, Method>` trong một class sống rất lâu có thể giữ tham chiếu mạnh đến `Class`, làm việc giải phóng class loader khó khăn.

Nếu mỗi class cần tra cứu **một chữ ký cố định**, `ClassValue` là một lựa chọn cache theo từng `Class`:

~~~java
import java.lang.reflect.Method;

public final class MethodCache {
    private MethodCache() {
    }

    private static final ClassValue<Method> COMPUTE = new ClassValue<>() {
        @Override
        protected Method computeValue(Class<?> type) {
            try {
                return type.getMethod("compute", long.class);
            } catch (NoSuchMethodException exception) {
                throw new IllegalArgumentException(
                        "Missing public compute(long) on " + type.getName(),
                        exception);
            }
        }
    };

    public static Method getComputeMethod(Class<?> type) {
        return COMPUTE.get(type);
    }
}
~~~

`ClassValue` tổ chức giá trị gắn với từng `Class`, thuận tiện hơn một static map mạnh khi tính đến vòng đời class loader. Ví dụ này chỉ dùng cho method public `compute(long)`. Nó không cấp quyền đặc biệt để truy cập private method, không chọn overload khác và không tự xác nhận return type.

Đối với tập method động, có thể lưu một cấu trúc accessor-map theo `ClassValue`, với khóa chứa tên/chữ ký thích hợp và kiểm soát race khi khởi tạo. Đừng cache một `Method` đã gọi `setAccessible(true)` để chia sẻ tùy tiện với code không tin cậy: metadata/handle được cấp quyền có thể làm rò rỉ năng lực truy cập.

### ClassValue không xóa mọi vấn đề cache

Cache vẫn cần quy ước về:

- Chính sách khi không tìm thấy method (negative cache hay báo lỗi).
- Kích thước map trên mỗi class nếu số method rất lớn.
- Khóa phân biệt constructor, method, field và return type khi cần.
- Hành vi đồng thời và duplicate initialization.
- Quyền truy cập khi module thay đổi cấu hình ở môi trường chạy.
- Khả năng bộ nhớ bị giữ qua các tham chiếu khác trong ứng dụng.

Nếu số lượng class cố định và vòng đời ứng dụng đơn giản, cache `static final` cũng có thể hoàn toàn phù hợp. Chọn độ phức tạp cache theo mô hình tải và vòng đời thực tế.

## 11. Khi nào nên chọn Reflection?

`java.lang.reflect.Method` vẫn hợp lý khi:

- Ứng dụng cần khám phá class/method/annotation/parameter lúc runtime.
- Tập chữ ký động, nhiều overload và thao tác mô tả metadata quan trọng hơn tốc độ invoke thuần.
- Đường gọi không cực nóng hoặc phần nghiệp vụ chiếm gần hết thời gian.
- Codebase/framework đã dùng Reflection ổn định, dễ bảo trì, dễ chẩn đoán.
- Benchmark cho thấy cached Reflection đạt yêu cầu latency/throughput.
- Chuyển sang MethodHandle sẽ kéo theo nhiều adapter, thay đổi exception contract hoặc phức tạp hóa bảo mật.

Ưu điểm thực tế của Reflection là API thuận tiện với metadata và lời gọi động: `Method.invoke(target, Object...)` chấp nhận một danh sách đối số dạng `Object` và xử lý boxing/unboxing theo hợp đồng Reflection. Đổi lại, method trả primitive được bọc thành wrapper, còn ngoại lệ của target thường nằm trong `InvocationTargetException`.

Không nên đổi sang MethodHandle chỉ vì tên API nghe có vẻ “gần JVM hơn”. Khi đã có cached `Method` và workload đủ tốt, thay đổi không tạo lợi ích có ý nghĩa cũng là một kết quả kỹ thuật hợp lệ.

## 12. Khi nào nên chọn MethodHandle?

`MethodHandle` thường đáng thử khi:

- Có một tập method/constructor/field được xác định trước, được gọi rất nhiều lần.
- Chữ ký tại call site rõ ràng và ổn định.
- Có thể lưu handle đã được lookup/adapt trước vòng lặp nóng.
- Có nhu cầu kết hợp các thao tác `bindTo`, `asType`, `filterArguments` hoặc combinator khác để tạo dispatcher.
- Bài đo JMH và benchmark end-to-end trên JDK mục tiêu cho thấy lợi ích đủ lớn để bù độ phức tạp.

MethodHandle không phải cùng API với Reflection. `invokeExact` yêu cầu kiểu của call site khớp **chính xác** với `MethodHandle.type()`; sai kiểu có thể ném `WrongMethodTypeException`. `invoke` cho phép một số chuyển đổi, nhưng việc thích nghi có chi phí và semantics riêng.

Ngoại lệ target từ MethodHandle thường truyền trực tiếp theo hợp đồng `invoke`, không nhất thiết được bọc như `Method.invoke`. Khi thay API gọi, hãy kiểm thử lại quy tắc exception mapping của framework; đừng vô tình thay đổi kiểu ngoại lệ mà client nhìn thấy.

### Chú ý quyền truy cập

`Lookup.findVirtual`, `findSpecial` hoặc `privateLookupIn` tuân theo quy tắc truy cập Java/JPMS. MethodHandle kiểm tra quyền khi tạo handle; Reflection có các kiểm tra và cơ chế `AccessibleObject` theo hợp đồng của nó.

Không được giả định MethodHandle là cách vượt `exports`/`opens` hoặc strong encapsulation. Nếu dùng private lookup xuyên module, package đích phải được mở cho caller theo quy tắc module. Handle đã được tạo có thể mang năng lực gọi member; không chuyển nó cho code không tin cậy nếu việc gọi đó vượt quyền mà code ấy đáng được có.

## 13. Đừng biến benchmark thành lỗi về semantics

Hai đường gọi phải thực hiện **cùng một hành vi** trước khi so hiệu năng:

| Khác biệt | Nguy cơ so sánh sai | Cách kiểm soát |
| --- | --- | --- |
| `Method.invoke` trả `Object`; MH có `long` | Boxing được tính cho một bên, không bên kia | Nếu đó là API thực, giữ đúng; đồng thời đo allocation và ghi rõ ngữ cảnh |
| `invokeExact` so với `invoke` | Một bên không có chuyển đổi, bên kia có adapter | Benchmark đường mà ứng dụng thực sự sử dụng |
| MethodHandle được cache, Method lookup mỗi request | So sánh khác chiến lược cache | So sánh cả cached-vs-cached và lookup-vs-lookup |
| Target method khác nhau | Kết quả số không thể đối chiếu | Dùng cùng class, cùng method và input |
| Cached metadata trong `static final` vs map động | Khác khả năng tối ưu JIT | Tách các case và đặt tên rõ |
| Public method vs private reflection | Khác access check và JPMS | Dùng cấu hình quyền hợp lệ như production |
| Exception có/không có | Một benchmark đo đường lỗi | Đo riêng success path và error path |
| Single receiver vs hàng chục receiver | Khác mức đa hình tại call site | Thêm kịch bản đa hình theo workload thực |

Trong benchmark mẫu, direct call có lợi thế compiler biết method ngay từ source. Đây là baseline tham chiếu, không phải một lựa chọn có thể áp dụng cho hệ thống chỉ biết method ở runtime.

## 14. Đọc kết quả và ra quyết định có điều kiện

Sau khi chạy JMH, hãy trả lời theo thứ tự:

1. **Đúng chức năng chưa?** Hai đường gọi phải trả cùng kết quả và giữ đúng exception contract.
2. **Bottleneck ở đâu?** Lookup, invoke, adapter, GC, cache contention hay công việc bên trong target method?
3. **Có bằng chứng ổn định không?** Kết quả lặp lại qua fork, error interval nhỏ và hướng chênh lệch nhất quán?
4. **Mức chênh lệch có ý nghĩa ở cấp ứng dụng không?** Một vài nanosecond trong method hiếm khi gọi có thể không ảnh hưởng end-to-end.
5. **Chi phí vận hành có đáng không?** Code phức tạp hơn, cache key, class unloading, exception mapping và security cần được tính đến.
6. **JDK sản xuất là JDK nào?** Đo lại trên đúng vendor/version và VM flags; không dùng kết quả ở một JDK để áp cho JDK khác.

### Ma trận quyết định

| Quan sát thực nghiệm | Lựa chọn có cơ sở |
| --- | --- |
| Lookup mỗi lần tốn đáng kể; cached Method và cached MH đều đạt yêu cầu | Cache metadata trước; giữ Reflection nếu đơn giản và đủ nhanh. |
| Cached MH ổn định tốt hơn, có lợi ích thực tế ở workload nóng | Cân nhắc MH cho hot path với kiểu ổn định; thêm correctness regression tests. |
| Cached Reflection ngang hoặc tốt hơn trên JDK đang dùng | Tiếp tục Reflection; không tối ưu theo định kiến. |
| Phần lớn thời gian nằm trong target method hoặc I/O | Tập trung tối ưu nghiệp vụ/I/O; thay API gọi có thể không đáng. |
| Cache map gây contention hoặc memory leak | Thiết kế lại vòng đời/key/bộ nhớ trước khi đổi API invoke. |
| Hiệu năng đổi mạnh giữa hai bản JDK | Cố định môi trường triển khai, cập nhật benchmark baseline và điều tra JIT/profiler. |
| Chênh lệch nhỏ hơn hoặc tương đương noise | Chưa đủ bằng chứng để kết luận; đo lại hoặc ưu tiên thiết kế đơn giản. |

Không nên công bố “nhanh hơn N lần” nếu chưa có số đo cùng điều kiện, sai số và phương pháp lặp lại.

## 15. Quan sát tối ưu bằng profiler và tình huống production

JMH giúp cô lập phần chi phí, còn profiler và metric sản xuất trả lời liệu chi phí ấy có quan trọng trong hệ thống thật.

Có thể thu thập:

- CPU profile và hotspot của `getMethod`, `Method.invoke`, lookup và adapter.
- Allocation profile: `Object[]`, wrapper của primitive, đối tượng metadata/cache entry.
- GC activity, tail latency, throughput và độ ổn định dưới concurrency.
- Cache hit rate và miss rate; kích thước cache theo class loader.
- Số lượng method signature thực sự xuất hiện và tỷ lệ reuse.
- Mức thay đổi của JIT khi chạy với nhiều type receiver khác nhau.

Bài toán dispatch ở môi trường plugin có thể phát sinh hàng nghìn kiểu target, trong khi benchmark mẫu chỉ có một kiểu. Hãy dựng workload gần thực tế, phân bố số lần gọi và số class để quyết định. Nếu tối ưu cho throughput, đo ở số threads phù hợp; nếu tối ưu request latency, bổ sung benchmark end-to-end, đừng chỉ lấy `ns/op` của một method nhỏ.

## 16. Lỗi thường gặp khi tối ưu Reflection

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `System.nanoTime()` trong vòng lặp ngắn | JIT/warmup làm sai kết quả | Dùng JMH với fork, warmup, measurement |
| Không sử dụng giá trị trả về | JIT có thể loại bỏ công việc | Return kết quả hoặc dùng `Blackhole` của JMH |
| So Method lookup mỗi lần với MH cached | Không công bằng | Đo đồng thời cached và lookup cho cả hai |
| Cache chỉ theo tên method | Sai với overload và class loader | Khóa đủ declaring class, signature và ngữ cảnh |
| Cache class toàn cục vô hạn | Giữ class loader sống quá lâu | Cân nhắc `ClassValue`, vòng đời và evict policy |
| Dùng MH sai `MethodType` | `WrongMethodTypeException` | Kiểm tra `handle.type()` và call-site descriptor |
| Giả định JEP 416 bảo đảm MH nhanh hơn | Quyết định sai theo JDK/workload | Đo trên JDK mục tiêu |
| So `Method.invoke` với code target khác | Không biết chênh lệch do đâu | Dùng cùng target method/input |
| Chỉ xem `ns/op`, không xem allocation | Bỏ sót áp lực GC | Đo `-prof gc` và end-to-end |
| Bỏ qua JPMS khi tạo private handle | `IllegalAccessException` hoặc fail lookup | Cấu hình `exports`/`opens` đúng quyền |
| Không xem error bar và số fork | Kết luận từ noise | Lặp đo, phân tích sai số và ổn định |

## 17. Bài tập thực hành

### Bài tập 1: Chạy benchmark cơ sở

Tạo dự án JMH, chép `ReflectionCacheBenchmark` và chạy trên JDK bạn đang dùng. Ghi `java -version`, vendor, CPU, số forks, warmup, measurement và `ns/op` cho bảy đường gọi. Không dự đoán bên thắng trước khi chạy.

### Bài tập 2: Cache có ích ở đâu?

So sánh `reflectionLookupEachCall` với `reflectionCachedStaticFinal`, rồi so sánh `handleLookupEachCall` với `handleCachedStaticFinal`. Giải thích chênh lệch nào có thể đến từ lookup, chênh lệch nào có thể đến từ tối ưu JIT và boxing.

### Bài tập 3: Metadata cố định và metadata từ state

So sánh `reflectionCachedStaticFinal` với `reflectionCachedInState`; tương tự với MethodHandle. Nếu số khác nhau, giải thích vai trò của vị trí metadata đối với JIT. Nếu bằng nhau, ghi nhận kết quả thay vì cố suy diễn rằng benchmark bị lỗi.

### Bài tập 4: Thay đổi độ phức tạp target

Thay `Calculator.compute` bằng một hàm có logic dài hơn nhưng không có I/O. Chạy lại và so sánh tỷ lệ chi phí gọi đối với tổng thời gian. Sau đó thử workload sát nghiệp vụ hơn và giải thích vì sao overhead gọi có thể bị chìm.

### Bài tập 5: Đo phân bổ bộ nhớ

Chạy benchmark với `-prof gc`. Ghi `gc.alloc.rate.norm` cho từng đường. Thử phương thức nhận nhiều tham số primitive và so sánh Reflection với MH exact. Phân biệt allocation thực tế do lời gọi với allocation do test harness.

### Bài tập 6: Cache trong framework động

Thiết kế cache cho một dispatcher dùng `ClassLoader` plugin khác nhau và các method overload. Xác định khóa, nơi lưu, điều kiện cache hit/miss và vòng đời. Giải thích khi nào `ClassValue` phù hợp hơn static map.

### Bài tập 7: Đổi JDK hoặc VM flags

Giữ nguyên workload/JMH configuration và đo trên hai phiên bản JDK mục tiêu nếu môi trường cho phép. Không trộn số liệu từ hai máy khác nhau rồi xem chênh lệch là do JDK. Ghi đầy đủ điều kiện chạy.

### Bài tập 8: Viết quyết định kiến trúc

Viết một đoạn ADR ngắn gồm: bối cảnh, các phương án `Method.invoke`/`MethodHandle`, benchmark config, số đo và sai số, rủi ro chuyển đổi, lựa chọn cuối, điều kiện đo lại khi nâng JDK. Nếu chưa có số liệu, ghi **chưa đủ bằng chứng** thay vì công bố kết luận.

## 18. Ghi nhớ

- **JDK 18 (JEP 416) đưa Core Reflection lên cơ chế method handles.** Không dựa vào mô hình triển khai Reflection cũ để dự đoán hiệu năng hôm nay.
- **Tách chi phí lookup khỏi chi phí invocation.** Benchmark cached-vs-cached và lookup-vs-lookup trước khi ra quyết định.
- **JMH là công cụ phù hợp cho microbenchmark JVM.** Có warmup, measurement, fork và cách tiêu thụ kết quả; vẫn phải thiết kế workload đúng.
- **`static final` và cache động có đặc tính tối ưu khác nhau.** Không dùng một benchmark hằng để đại diện tất cả framework động.
- **Reflection và MethodHandle khác semantics, không chỉ tốc độ.** Chú ý kiểu lời gọi, boxing, exception và quyền truy cập module.
- **Cache có vòng đời.** Khóa đúng signature/class loader và tránh giữ class loader không cần thiết.
- **Không có người thắng mặc định.** Lựa chọn dựa trên kết quả có thể lặp lại trên JDK triển khai, khả năng bảo trì và tác động thực tế.
- **Chưa chạy benchmark thì chưa có bằng chứng hiệu năng.** Tài liệu hướng dẫn đo không được viết thành khẳng định về con số thực nghiệm.

## Tài liệu chính thống

- [OpenJDK — JEP 416: Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416).
- [Oracle — JDK 18 Release Notes, JEP 416](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html).
- [OpenJDK — JMH project và README hướng dẫn chạy benchmark](https://github.com/openjdk/jmh).
- [Java SE 27 — MethodHandle API, invokeExact/invoke/asType](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandle.html).
- [Java SE 27 — MethodHandles.Lookup API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html).
- [Java SE 27 — Method.invoke](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Method.html).
- [Java SE 27 — ClassValue API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ClassValue.html).

