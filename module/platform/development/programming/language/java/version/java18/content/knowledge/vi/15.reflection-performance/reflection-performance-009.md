# Benchmark một đích cố định và nhiều đích thay đổi để phản ánh cách ứng dụng thực sự gọi

> **Chương:** Reflection và hiệu năng  
> **Module:** JAVA_VERSION_JAVA18 — học các thay đổi Java 18 còn áp dụng trên JDK hiện đại và kiểm chứng hợp đồng reflection, MethodHandle bằng thực nghiệm.  
> **Phạm vi:** Đo hiệu năng gọi phương thức trực tiếp, qua `java.lang.reflect.Method` và `java.lang.invoke.MethodHandle` trong hai kiểu tải: cùng một đích lặp đi lặp lại và nhiều đích được chọn liên tục. Không sử dụng thủ thuật hoặc API đã lỗi thời; mọi kết quả phải đo trên JDK và workload thực tế của ứng dụng.

## 1. Vì sao benchmark một method duy nhất có thể dẫn đến kết luận sai?

Giả sử một framework cần gọi các handler/plugin dựa theo loại thông điệp:

- **Ứng dụng A:** mọi request gọi cùng một handler, cùng một `Method`; JIT nhìn thấy một đích ổn định.
- **Ứng dụng B:** request luân phiên giữa nhiều plugin, mỗi plugin có lớp triển khai và `Method` riêng; đích tại cùng một call site thay đổi liên tục.

Một benchmark chỉ gọi đi gọi lại một `Method` cố định không nhất thiết dự đoán được hiệu năng khi ứng dụng phải chọn một phần tử từ bảng `Method[]` cho từng request. Ở tình huống thứ hai, JIT có thể khó chuyên biệt hóa/inlining hơn và code còn phải trả chi phí chọn đích.

**Câu hỏi đúng không phải chỉ là “reflection nhanh bao nhiêu ns/op?”, mà là “ứng dụng gọi theo phân bố đích nào và đã cache metadata ra sao?”**

## 2. Bối cảnh Java 18: JEP 416 thay đổi implementation, không đổi hợp đồng API

JEP 416 trong Java 18 tái triển khai Core Reflection dựa trên Method Handles. Các API quen thuộc như `Method.invoke`, `Constructor.newInstance` và `Field.get/set` vẫn giữ hợp đồng công khai, nhưng đường đi nội bộ có thể được JIT tối ưu theo những cách khác với JDK cũ.

JEP 416 lưu ý một điều kiện quan trọng cho hiệu năng: đối tượng `Method`, `Constructor` hoặc `Field` nằm trong vị trí có thể được JIT coi là hằng, chẳng hạn trường `static final`, thuận lợi cho constant folding; ngược lại, metadata lấy qua trường không cố định hoặc phần tử mảng có thể khó tối ưu hơn. Đây là **quan sát về khả năng tối ưu**, không phải cam kết “`static final` luôn nhanh hơn đúng X%” trên mọi JDK.

Hai mẫu code cần đo riêng:

~~~java
// Đích ổn định; metadata có cơ hội được JIT nhìn như hằng.
private static final Method CONSTANT_METHOD = lookupOnce();

// Đích được lấy động theo request; vị trí mảng thay đổi.
Method chosen = cachedMethods[requestType];
chosen.invoke(receiver, argument);
~~~

Không suy ra chỉ từ tên “MethodHandle” rằng `invokeExact` sẽ luôn nhanh hơn `Method.invoke`. Chi phí phụ thuộc dạng call site, độ ổn định của đích, kiểu tham số, boxing/unboxing, mức độ inlining và các adapter đã dùng.

## 3. Thiết kế thí nghiệm: hai trục độc lập

### 3.1. Trục A — cách gọi

| Cách gọi | API | Điều cần quan sát |
| --- | --- | --- |
| Direct | `receiver.compute(x)` | Mốc tham chiếu với dispatch bình thường của Java. |
| Cached reflection | `method.invoke(receiver, x)` | Chi phí reflection khi đã tìm và cache metadata. |
| Cached MethodHandle | `handle.invokeExact(receiver, x)` | Chi phí một handle đã tạo và được chuẩn hóa kiểu trước khi đo. |

MethodHandle trong bài được tạo một lần bằng `MethodHandles.Lookup.unreflect`, rồi `asType` một lần ở giai đoạn setup để có cùng kiểu gọi. Việc chuyển đổi kiểu handle trong setup **không** được tính vào mỗi lượt gọi.

### 3.2. Trục B — phân bố đích

| Kịch bản | Đích trong một call site | Ý nghĩa thực tế |
| --- | --- | --- |
| Fixed | Một instance, một `Method` hoặc một `MethodHandle` | Một route nóng, một adapter hoặc một getter lặp đi lặp lại. |
| Dynamic-1 | Chọn qua mảng nhưng chỉ một đích | Có chi phí lấy đích/đánh chỉ số dù tập mục tiêu chỉ có một phần tử. |
| Dynamic-2 | Chọn luân phiên giữa hai lớp triển khai | Mô phỏng ứng dụng có hai loại handler thường gặp. |
| Dynamic-8 | Chọn luân phiên giữa tám lớp triển khai | Mô phỏng registry/plugin có nhiều mục tiêu khác nhau. |
| Constant-field (đối chứng) | Metadata lưu ở `static final` | Thử riêng điều kiện có lợi cho constant folding được JEP 416 nhắc đến. |

Các cách chọn đích này **không giống mọi ứng dụng ngoài đời**. Nếu telemetry cho thấy 95% request thuộc một handler, hãy thêm một phân bố lệch 95/5 vào benchmark, thay vì chỉ dùng phân bố đều 1/2 hoặc 1/8.

### 3.3. Những biến phải giữ nhất quán

- Cùng JDK, JVM vendor, VM flags, máy tính, mức tải nền và số thread đo.
- Cùng chữ ký method đích và cùng phép toán nghiệp vụ cho ba cách gọi.
- Cùng danh sách receiver, cùng quy tắc chọn đích cho các phép đo dynamic.
- `Method` và `MethodHandle` được lookup **trước** khi đo trong các bài cached-call.
- Mỗi benchmark gọi một method đích đúng một lần; không ngầm đưa lookup hoặc tạo handle vào riêng một nhánh.
- Trả kết quả từ benchmark hoặc dùng `Blackhole.consume` để tránh dead-code elimination.

## 4. Dùng JMH, không dùng một vòng lặp System.nanoTime()

JMH (Java Microbenchmark Harness) của OpenJDK hỗ trợ warmup, vòng đo, fork JVM, cách tiêu thụ kết quả, thống kê và xử lý nhiều bẫy tối ưu hóa. JMH **không có sẵn trong JDK**; cần thêm dependency và annotation processor của JMH trong một dự án benchmark riêng.

Ví dụ:

~~~java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    method.invoke(receiver, 42);
}
long elapsed = System.nanoTime() - start;
~~~

Vòng lặp này không đủ để kết luận vì có thể thiếu warmup, bị constant folding, DCE, JIT inlining bất ngờ, tác động của GC hoặc tối ưu hóa vòng lặp. `System.nanoTime()` vẫn hữu ích để đo thời gian thực thi đầu-cuối của nghiệp vụ thật, nhưng không thay thế JMH khi muốn so sánh microbenchmark.

Thiết lập được khuyến nghị cho lần đo khởi đầu (chỉ là cấu hình thử nghiệm, không phải chuẩn cố định):

~~~java
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
@Threads(1)
~~~

JMH sẽ báo điểm đo và độ bất định thống kê; tránh công bố “nhanh hơn 10%” nếu khoảng sai số chồng lấn mạnh hoặc số fork/iteration quá ít.

## 5. Benchmark hoàn chỉnh: fixed, dynamic-1/2/8 và static-final

Tạo một dự án benchmark JMH riêng theo hướng dẫn chính thức. Đặt mã sau vào `src/main/java/example/bench/DispatchBenchmark.java`, điều chỉnh package nếu dự án sinh ra có cấu trúc khác.

Mã tương thích Java 18+ về API Java; cần dependency JMH để biên dịch phần annotation:

~~~java
package example.bench;

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
import org.openjdk.jmh.annotations.Threads;
import org.openjdk.jmh.annotations.Warmup;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
@Threads(1)
public class DispatchBenchmark {
    public interface Operation {
        int compute(int x);
    }

    // Tám lớp đích khác nhau, cùng chữ ký. Phép toán cố ý rất nhỏ
    // để quan sát overhead gọi; đây không phải workload CPU thực tế.
    public static final class Op0 implements Operation {
        public int compute(int x) { return x + 1; }
    }
    public static final class Op1 implements Operation {
        public int compute(int x) { return x + 2; }
    }
    public static final class Op2 implements Operation {
        public int compute(int x) { return x + 3; }
    }
    public static final class Op3 implements Operation {
        public int compute(int x) { return x + 4; }
    }
    public static final class Op4 implements Operation {
        public int compute(int x) { return x + 5; }
    }
    public static final class Op5 implements Operation {
        public int compute(int x) { return x + 6; }
    }
    public static final class Op6 implements Operation {
        public int compute(int x) { return x + 7; }
    }
    public static final class Op7 implements Operation {
        public int compute(int x) { return x + 8; }
    }

    private static final Operation CONSTANT_RECEIVER = new Op0();
    private static final Method CONSTANT_METHOD;
    private static final MethodHandle CONSTANT_HANDLE;

    static {
        try {
            CONSTANT_METHOD = Op0.class.getMethod("compute", int.class);
            CONSTANT_HANDLE = MethodHandles.lookup()
                    .unreflect(CONSTANT_METHOD)
                    .asType(MethodType.methodType(
                            int.class, Operation.class, int.class));
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    @State(Scope.Thread)
    public static class InvocationState {
        // Các giá trị thay đổi qua từng lượt; tránh benchmark chỉ
        // thực hiện một phép tính với đối số hằng.
        public int input = 17;
        public int cursor;

        // Chỉ dùng 1, 2, 8 để phép & (targetCount - 1) hợp lệ.
        @Param({"1", "2", "8"})
        public int targetCount;

        public Operation[] receivers;
        public Method[] methods;
        public MethodHandle[] handles;
        public Operation fixedReceiver;
        public Method fixedMethod;
        public MethodHandle fixedHandle;

        @Setup(Level.Trial)
        public void prepare() throws ReflectiveOperationException {
            receivers = new Operation[] {
                new Op0(), new Op1(), new Op2(), new Op3(),
                new Op4(), new Op5(), new Op6(), new Op7()
            };
            methods = new Method[receivers.length];
            handles = new MethodHandle[receivers.length];

            MethodHandles.Lookup lookup = MethodHandles.lookup();
            MethodType commonType = MethodType.methodType(
                    int.class, Operation.class, int.class);

            for (int i = 0; i < receivers.length; i++) {
                // Mỗi Method đại diện cho phương thức ở lớp đích i.
                methods[i] = receivers[i].getClass()
                        .getMethod("compute", int.class);

                // Chuyển một lần về (Operation, int) -> int;
                // không gọi asType trong phương thức @Benchmark.
                handles[i] = lookup.unreflect(methods[i])
                        .asType(commonType);
            }

            fixedReceiver = receivers[0];
            fixedMethod = methods[0];
            fixedHandle = handles[0];
        }

        public int nextIndex() {
            return cursor++ & (targetCount - 1);
        }
    }

    // Nhóm 1: một đích cố định. Đều đọc metadata/handle từ State.
    @Benchmark
    public int directFixed(InvocationState s) {
        return s.fixedReceiver.compute(++s.input);
    }

    @Benchmark
    public int reflectionFixed(InvocationState s)
            throws ReflectiveOperationException {
        return (Integer) s.fixedMethod.invoke(
                s.fixedReceiver, ++s.input);
    }

    @Benchmark
    public int methodHandleFixed(InvocationState s) throws Throwable {
        return (int) s.fixedHandle.invokeExact(
                s.fixedReceiver, ++s.input);
    }

    // Nhóm 2: cùng call site nhưng đích lấy từ mảng, độ đa dạng
    // của đích được điều chỉnh bởi @Param targetCount = 1/2/8.
    @Benchmark
    public int directDynamic(InvocationState s) {
        int i = s.nextIndex();
        return s.receivers[i].compute(++s.input);
    }

    @Benchmark
    public int reflectionDynamic(InvocationState s)
            throws ReflectiveOperationException {
        int i = s.nextIndex();
        return (Integer) s.methods[i].invoke(
                s.receivers[i], ++s.input);
    }

    @Benchmark
    public int methodHandleDynamic(InvocationState s) throws Throwable {
        int i = s.nextIndex();
        return (int) s.handles[i].invokeExact(
                s.receivers[i], ++s.input);
    }

    // Nhóm đối chứng: metadata trong static final.
    // Đo riêng khả năng JIT nhìn thấy đối tượng Method/MethodHandle
    // như một hằng; không ghép vào cùng nhóm State-cached.
    @Benchmark
    public int reflectionConstant(InvocationState s)
            throws ReflectiveOperationException {
        return (Integer) CONSTANT_METHOD.invoke(
                CONSTANT_RECEIVER, ++s.input);
    }

    @Benchmark
    public int methodHandleConstant(InvocationState s) throws Throwable {
        return (int) CONSTANT_HANDLE.invokeExact(
                CONSTANT_RECEIVER, ++s.input);
    }
}
~~~

### 5.1. Tại sao ví dụ này có ý nghĩa?

1. Cả ba lối gọi đều thực thi `compute(int)` với một đầu vào thay đổi qua các invocation.
2. `@State(Scope.Thread)` giữ `input` và `cursor` riêng cho mỗi JMH worker, tránh nhiễu do tranh chấp counter khi đo một thread.
3. `@Setup(Level.Trial)` tạo cache `Method[]`/`MethodHandle[]` trước khi đo.
4. `@Param({"1","2","8"})` thay đổi **số đích thực sự có thể được chọn** mà giữ nguyên source code của nhóm `Dynamic`.
5. Dùng tám lớp khác nhau thay vì tám object cùng class: nếu mọi `Method` trỏ cùng một implementation, benchmark sẽ không đại diện cho nhiều mục tiêu mã thực thi.
6. Hai benchmark `Constant` cho phép so `static final` với cache trong `@State`; đây là một đối chứng riêng, không phải biến thể tương đương của “nhiều đích”.
7. Kết quả `int` được trả cho JMH tiêu thụ, hạn chế dead-code elimination. Giá trị đích thay đổi theo `input` và lớp triển khai.

### 5.2. Giới hạn của mô hình mẫu

- `nextIndex()` dùng luân phiên đều và mặt nạ bit: chỉ đúng với các kích thước tập mục tiêu là lũy thừa của hai. Nếu sửa thành 3 hoặc 5, hãy thay bằng logic chọn chỉ số phù hợp.
- Nhóm `Fixed` không cần chọn chỉ số; nhóm `Dynamic` có chi phí chọn chỉ số, tải mảng và thay đổi đích. Đó là **chi phí có chủ đích** của workload, không phải chỉ overhead reflection.
- `Method.invoke` cần boxing tham số `int` và boxing kết quả trả về; `MethodHandle.invokeExact` dùng `int` ở kiểu gọi hiện tại. Vì vậy số đo là **chi phí của toàn bộ cơ chế gọi trong ví dụ**, không phải phép so sánh chỉ riêng một instruction JVM.
- Vì method đích chỉ cộng một số nhỏ, overhead dispatch chiếm tỉ trọng lớn. Khi công việc thật mất vài milliseconds, chênh lệch invoke theo nanoseconds có thể không quan trọng.
- `@State` không biến `fixedMethod` thành hằng `static final`. Đừng mặc định benchmark `reflectionFixed` được tối ưu giống `reflectionConstant`.

## 6. Chạy JMH đúng cách

OpenJDK khuyến nghị dùng Maven archetype JMH để bảo đảm annotation processing và generated harness được cấu hình đúng. Các lệnh dưới đây là **hướng dẫn**, không phải kết quả benchmark đã chạy:

~~~bash
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DgroupId=example.bench -DartifactId=reflection-bench -Dversion=1.0
cd reflection-bench
~~~

Chép `DispatchBenchmark.java` vào thư mục tương ứng với package; cấu hình Maven compiler để biên dịch với `--release 18` hoặc source/target phù hợp với JDK đang sử dụng. Dùng bản JMH ổn định phù hợp do Maven archetype hoặc dự án quản lý; JMH không phải API nền tảng của JDK.

~~~bash
mvn -DskipTests package
java -jar target/benchmarks.jar '.*DispatchBenchmark.*' -wi 5 -i 5 -f 3 -t 1
~~~

Một cách lưu kết quả máy đọc được:

~~~bash
java -jar target/benchmarks.jar '.*DispatchBenchmark.*' -rf json -rff results.json
~~~

Mỗi `@Param` tạo một tập trường hợp đo riêng; với tám phương thức `@Benchmark`, JMH sẽ tạo nhiều dòng kết quả. Lọc theo tên phương thức và `targetCount`, đồng thời ghi lại JDK vendor/version, JVM args, OS, CPU, cấu hình máy và lệnh đã chạy.

**Không điền sẵn số ns/op giả định.** Điểm số và sai số chỉ có ý nghĩa sau khi thực sự đo trên môi trường xác định. Chạy lại nhiều lần, đổi thứ tự kiểm tra nếu nghi ngờ nhiễu hoặc cạnh tranh tài nguyên.

## 7. Đọc kết quả bằng hai phép so sánh khác nhau

### 7.1. Trong cùng một phân bố đích, so cách gọi

Ví dụ với `targetCount = 8`:

| Nhóm | Benchmark | Điều cần so |
| --- | --- | --- |
| Direct | `directDynamic` | Chi phí dispatch Java thông thường + chọn đích. |
| Reflection | `reflectionDynamic` | Cached `Method.invoke` + chọn đích và chuyển đổi tham số/kết quả. |
| MethodHandle | `methodHandleDynamic` | Cached typed `invokeExact` + chọn đích. |

Nếu chỉ so `reflectionFixed` với `directDynamic`, ta đã thay đổi **cả cơ chế gọi lẫn phân bố đích**, nên không thể quy chênh lệch cho reflection.

### 7.2. Trong cùng một cách gọi, so phân bố đích

Ví dụ so `reflectionDynamic` giữa `targetCount = 1`, `2` và `8`. Ba lần đo đi qua cùng một phương thức benchmark, cùng logic chọn chỉ số; chỉ số lớp/Method có thể được lựa chọn tăng dần.

So `reflectionFixed` với `reflectionDynamic (targetCount = 1)` giúp quan sát thêm chi phí lựa chọn/lấy phần tử mảng ngay cả khi tập đích chỉ có một phần tử. Không lấy hiệu số hai score rồi mặc định đó là “chi phí đọc một phần tử mảng”: JIT có thể tối ưu hai code shape khác nhau.

### 7.3. Đối chứng constant-foldable

So riêng `reflectionConstant` với `reflectionFixed` và `methodHandleConstant` với `methodHandleFixed`. Đây là thay đổi **vị trí lưu metadata**, có thể tác động đến khả năng constant folding theo JEP 416. Không coi `static final` là proxy của workload trong đó ứng dụng liên tục tra một registry của nhiều method.

Một bảng báo cáo nên để trống cho đến khi có đo thực tế:

| Scenario | Kiểu gọi | JDK | Score (ns/op) | Error/CI | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| Fixed | Direct | … | … | … | State-cached receiver |
| Fixed | Reflection | … | … | … | State-cached Method |
| Fixed | MethodHandle | … | … | … | State-cached MH |
| Dynamic-1/2/8 | Direct | … | … | … | Đích chọn từ mảng |
| Dynamic-1/2/8 | Reflection | … | … | … | Method[] |
| Dynamic-1/2/8 | MethodHandle | … | … | … | MethodHandle[] |
| Constant | Reflection/MH | … | … | … | static final |

## 8. Làm benchmark giống ứng dụng thực tế hơn

Ví dụ trước kiểm tra tính đa hình của các mục tiêu cùng một chữ ký. Để phản ánh ứng dụng thật, cần xác định:

| Đặc điểm thực tế | Điều chỉnh benchmark |
| --- | --- |
| 90–99% request vào một handler | Dùng phân bố **skewed/hot** (ví dụ 95/5), thay vì vòng đều 1/8. |
| Handler được chọn theo key trên registry | Đưa bước lookup map vào một nhóm **end-to-end** riêng; giữ nhóm invoke-only để phân tích. |
| Có cache Method theo lớp, song tra cache có contention | Benchmark cả single-thread và nhiều thread với shared cache thật. |
| Chữ ký nhận Object/JSON, không phải int | Dùng loại tham số thật, tránh boxing giả tạo hoặc bỏ sót chi phí serialize. |
| Đích có thời gian xử lý lớn | Tăng độ phức tạp handler và đo thêm throughput/latency đầu-cuối. |
| Target có thay đổi thực theo thời gian | Cập nhật registry theo tần suất thực tế ở một nhóm benchmark riêng, không thay `Method[]` ở mọi nanosecond nếu ứng dụng ít thay đổi. |
| Handler throw exception ở tỷ lệ đáng kể | Có kịch bản exception riêng vì chi phí stack trace, catch và exception wrapping khác đường thành công. |

### 8.1. Phân bố nóng 95/5

Một biến thể đơn giản cho tám đích:

~~~java
// Trong State, cursor thay đổi giữa các invocation.
// 972/1024 lượt (~94,9%) chọn mục tiêu 0; phần còn lại
// được chia cho các mục tiêu 1..7.
int n = s.cursor++ & 1023;
int i = n < 972 ? 0 : 1 + ((n - 972) % 7);
Operation receiver = s.receivers[i];
Method method = s.methods[i];
return (Integer) method.invoke(receiver, ++s.input);
~~~

Nhánh này cho khoảng 95% lượt gọi vào mục tiêu 0 và 5% còn lại chia gần đều giữa các mục tiêu khác trong chu kỳ 1.024 lượt. Cần dùng cùng hàm chọn đích cho `direct`, `reflection` và `methodHandle` để giữ công bằng. Với hệ thống thật, thay các tỉ lệ minh họa bằng thống kê request đã thu thập được.

### 8.2. Tách invoke-only khỏi lookup + invoke

Hai kiểu workload hợp lệ nhưng trả lời hai câu hỏi khác nhau:

~~~java
// A. Metadata được cache theo đời ứng dụng; chỉ đo dispatch/invoke.
Method cached = methods[i];
Object result = cached.invoke(receiver, x);

// B. Ứng dụng thật lookup method cho từng request; đo cả pipeline.
Method lookedUp = receiver.getClass().getMethod("compute", int.class);
Object resultWithLookup = lookedUp.invoke(receiver, x);
~~~

Nếu ứng dụng có cache nhưng benchmark làm lookup mỗi vòng, bạn đã đo thêm một chi phí không tồn tại ở hot path thực tế. Nếu ứng dụng **không có cache**, chỉ báo cáo kết quả invoke-only cũng không phản ánh tổng chi phí vận hành.

## 9. Bẫy JMH dễ làm sai kết luận

| Bẫy | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Không warmup | Đang trộn interpreted, profiling và JIT compilation | Dùng warmup iterations và forks; giữ log VM/JIT khi phân tích chuyên sâu. |
| Chỉ một JVM fork | Kết quả dễ lệ thuộc trạng thái VM và code cache | Nhiều forks, báo score/error và phân bố phép đo. |
| Không dùng kết quả | JIT có thể xóa computation | Trả kết quả từ `@Benchmark` hoặc dùng `Blackhole`. |
| Dùng input hằng không đổi | JIT có thể constant-fold kết quả | Dùng dữ liệu `@State` có thay đổi hợp lý. |
| Lookup trong riêng nhánh reflection | So các công việc khác nhau | Tách benchmark metadata lookup và cached invocation. |
| Tạo `MethodHandle.asType` trong vòng đo | Đo thêm chi phí adapter creation | Chuẩn hóa handle một lần ở `@Setup` nếu thực tế cũng cache. |
| Dùng một lớp cho tất cả target | Call site vẫn chỉ có một implementation | Tạo nhiều lớp đích có code khác nhau, đúng workload. |
| Quên boxing trong `Method.invoke` | Chênh lệch có thể do conversion/GC chứ không chỉ dispatch | Báo rõ kiểu tham số và allocation rate; nếu cần, bổ sung kịch bản tham số reference. |
| Chỉ đo dynamic-8 rồi suy ra mọi ứng dụng | Phân bố đích thật có thể rất lệch | Đo fixed, 2, 8 và phân bố nóng theo telemetry. |
| Chạy đa luồng nhưng dùng state dùng chung không khóa | Race condition, cache contention, sai semantic | Dùng `Scope.Thread` khi đo từng luồng; benchmark concurrency riêng với state đúng. |
| Tin vào một con số tuyệt đối | Khác JVM, OS, CPU, flags, GC, load nền | Lưu đầy đủ môi trường và lặp lại đo. |

JMH Samples chính thức có ví dụ `DeadCode` và `ConstantFold` giải thích cụ thể vì sao “trả kết quả” và “không dùng input hằng” là cần thiết. Tuy nhiên, dùng JMH không tự động biến một workload không đại diện thành benchmark tốt.

## 10. Khi nào tối ưu reflection thực sự đáng làm?

Cần xem đóng góp của phần gọi method trong tổng latency:

~~~text
Tổng thời gian request
  = lựa chọn route/plugin
  + lookup/cache metadata
  + dispatch/invoke
  + xử lý nghiệp vụ
  + I/O mạng / cơ sở dữ liệu
  + serialization / logging / GC ...
~~~

Nếu handler mất hàng milliseconds để truy vấn database, thay `Method.invoke` bằng `MethodHandle` chỉ tiết kiệm vài nanoseconds (nếu benchmark có đo được) chưa chắc cải thiện đáng kể latency cuối-cuối. Ngược lại, với hàng triệu lần gọi method nhỏ trong serializer hoặc rule engine, chi phí dispatch có thể tích lũy đáng kể.

Quy trình ra quyết định:

1. Profiling ứng dụng thật để chứng minh invocation đang chiếm tỷ lệ đáng kể.
2. Ghi nhận phân bố đích, số lượng implementation, tỉ lệ cache hit và loại tham số.
3. Dựng JMH benchmark fixed/multi/skewed với cùng nghiệp vụ.
4. Kiểm tra score, độ bất định, allocation và khác biệt giữa các JDK mục tiêu.
5. Chọn giải pháp đơn giản nhất đáp ứng mục tiêu; kiểm tra lại end-to-end.

**Không thay toàn bộ reflection bằng MethodHandle chỉ vì một benchmark “fixed constant” có score đẹp.** JEP 416 đã thay đổi implementation bên dưới Core Reflection; lợi ích của việc viết lại ứng dụng phải được chứng minh trong workload thực.

## 11. Câu hỏi tự kiểm tra

1. Vì sao benchmark một `Method` cố định không dự đoán chắc hiệu năng của một plugin registry nhiều đích?
2. JEP 416 thay đổi những gì và không thay đổi những gì ở public reflection API?
3. Vì sao cần kịch bản `static final Method` riêng?
4. Khác biệt giữa `reflectionFixed` và `reflectionDynamic(targetCount=1)` là gì?
5. Vì sao `targetCount=2` và `targetCount=8` giúp quan sát tính đa hình của call site?
6. Vai trò của `@State(Scope.Thread)`, `@Param` và `@Setup(Level.Trial)` là gì?
7. Vì sao không tạo `MethodHandle.asType` trong phương thức `@Benchmark`?
8. Vì sao `Method.invoke` có thể tạo boxing mà `invokeExact` với `int` thì không?
9. Nếu ứng dụng có cache metadata, benchmark gọi `getMethod` mọi iteration sai ở đâu?
10. Vì sao phải tiêu thụ kết quả benchmark?
11. Khi nào cần phân bố đích 95/5 thay vì luân phiên đều?
12. Vì sao một chênh lệch nhỏ ở ns/op không tự động cải thiện latency request?

**Bài thực hành:** chạy `DispatchBenchmark` trên ít nhất hai JDK mà dự án hỗ trợ (ví dụ JDK 18 và một bản LTS hiện đại). So score của `reflectionDynamic` giữa 1/2/8 mục tiêu; làm tương tự với MethodHandle và direct call. Tiếp theo thêm kịch bản 95/5, ghi nhận kết quả và giải thích nguyên nhân khả dĩ nhưng không khẳng định khi chưa có profiler/JIT evidence. Cuối cùng đo riêng lookup+invoke và kiểm tra mức đóng góp của mỗi phần trong một request thực tế.

## Tài liệu tham khảo chính thức

- [OpenJDK — JEP 416: Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): ảnh hưởng implementation Java 18 và điều kiện metadata có thể constant-fold.
- [OpenJDK — JMH project/README](https://github.com/openjdk/jmh): cách tạo benchmark project chuẩn và các giới hạn của microbenchmark.
- [OpenJDK — JMH Samples: Dead Code](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java): dùng kết quả để hạn chế DCE.
- [OpenJDK — JMH Samples: Constant Folding](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java): vai trò của input từ `@State` và tối ưu hóa hằng.
- [Oracle JDK 18 — `Method.invoke`](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/lang/reflect/Method.html): hợp đồng reflection, tham số, boxing và exception.
- [Oracle JDK 18 — `MethodHandle.invokeExact`](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/lang/invoke/MethodHandle.html): kiểu chính xác của call site và method handle.
- [Oracle JDK 26 — `MethodHandle`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html): hợp đồng vẫn được hỗ trợ trên JDK hiện đại.
