# Warmup, nhiều JVM fork, loại bỏ kết quả không dùng và ảnh hưởng của constant folding

> **Phạm vi:** Bài thuộc chương **Reflection và hiệu năng** của module `JAVA_VERSION_JAVA18`. Java 18 giới thiệu JEP 416, tái triển khai core reflection dựa trên method handles. Hợp đồng công khai của `Method.invoke`, `Constructor.newInstance`, `Field.get/set` vẫn hữu ích trên JDK hiện đại, nhưng muốn đánh giá chi phí của chúng phải đo đúng. Bài tập trung vào bốn điều kiện căn bản của microbenchmark Java: **warmup**, **nhiều JVM fork**, **đảm bảo kết quả tính toán được sử dụng**, và **tránh kết luận sai do constant folding**. Ví dụ sử dụng JMH (Java Microbenchmark Harness), không dựa vào API nội bộ hoặc cách tối ưu hóa đã lỗi thời.

## 1. Vì sao một vòng lặp đo nanosecond dễ gây hiểu lầm?

Một phép thử hấp dẫn là chạy hàng triệu lần `Method.invoke`, lấy `System.nanoTime()` ở đầu và cuối, rồi chia cho số lần gọi:

~~~java
long started = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    method.invoke(target, 42);
}
long average = (System.nanoTime() - started) / 1_000_000L;
~~~

Mã trên **không đủ** để khẳng định một lời gọi reflection tốn bao nhiêu nanosecond. Một số lý do:

- JVM có thể còn ở giai đoạn **class loading**, thông dịch, thu thập hồ sơ thực thi hoặc biên dịch JIT khi vòng lặp bắt đầu.
- Trong cùng tiến trình, các lần đo sau thừa hưởng code đã biên dịch, dữ liệu cache và trạng thái bộ nhớ từ các lần đo trước.
- Nếu kết quả của lời gọi không ảnh hưởng đến hành vi quan sát được, trình tối ưu hóa có thể loại bỏ hoặc rút gọn công việc. Khả năng loại bỏ phụ thuộc ngữ nghĩa lời gọi và thông tin JIT chứng minh được; không phải mọi lời gọi phản chiếu đều tự động biến mất.
- Đối số cố định như `42` có thể giúp compiler/JIT dự đoán giá trị và **constant fold** hoặc hoist các phép tính thuần.
- Chi phí tạo mảng `Object...`, boxing/unboxing, lookup `Method`, gọi phương thức đích và ghi nhận kết quả dễ bị trộn lẫn.
- GC, lập lịch thread, tần số CPU, tải nền và hoạt động khởi tạo JDK có thể khiến một lần chạy đơn lẻ lệch đáng kể.
- Phép chia nguyên ở cuối làm mất phần thập phân; sai số đo ngắn cũng có thể chiếm tỉ lệ lớn so với thao tác cần đo.

`System.nanoTime()` hữu ích khi đo các khoảng thời gian phù hợp, nhưng một timer chính xác **không tự tạo nên benchmark đúng**. Cần thiết kế cả cách chạy, đầu vào, đầu ra và cách diễn giải.

### 1.1. Phải xác định mình đo cái gì

Các câu hỏi khác nhau cần các bài đo khác nhau:

| Câu hỏi | Phạm vi cần đo |
|---|---|
| Mất bao lâu để **tìm phương thức** từ metadata? | `Class.getMethod(...)` hoặc `getDeclaredMethod(...)` |
| Mất bao lâu để **gọi phương thức đã tìm được**? | `Method.invoke` với `Method` được cache trước khi đo |
| Mất bao lâu để tạo đối tượng qua reflection? | `Constructor.newInstance`, với constructor đã tìm từ trước |
| Tốn bao nhiêu cho tác vụ ứng dụng thực? | Bao gồm lookup/cache, chuyển đổi kiểu, gọi nghiệp vụ, xử lý kết quả theo đường đi thật |
| Reflection khác direct call hay `MethodHandle` ra sao? | Cùng chức năng, cùng dữ liệu đầu vào, công khai rõ khác biệt adapter và boxing |

Một phép đo **lookup + invoke** không nên gắn nhãn là chi phí riêng của `Method.invoke`. Trước khi xem con số, cần biết benchmark đang đo đường đi nào.

## 2. Warmup: cho JVM quan sát tải trước khi thu kết quả

HotSpot JVM thường bắt đầu thực thi code bằng cách thông dịch và có thể biên dịch các đoạn mã hay chạy bằng JIT. Cách tổ chức này cho phép JIT dùng thông tin thực thi để tối ưu hóa, ví dụ inlining, specialization và tối ưu vòng lặp.

Các hoạt động có thể xảy ra khi một benchmark mới bắt đầu:

1. Nạp, liên kết và khởi tạo các lớp liên quan.
2. Tìm và khởi tạo metadata reflection hoặc method-handle adapters khi cần.
3. Ghi nhận loại receiver và tần suất các nhánh trong luồng gọi.
4. Chuyển từ interpreted code sang mã máy đã được biên dịch.
5. Thực hiện GC hoặc mở rộng/điều chỉnh tài nguyên runtime theo tải.

**Warmup** là các lần chạy có chủ đích để những hoạt động ban đầu không bị trộn một cách tùy tiện vào số liệu đo trạng thái ổn định (*steady state*).

~~~text
JVM fork được khởi động
         |
         v
  Khởi tạo benchmark/state
         |
         v
  Warmup iterations         (không tính vào điểm đo chính)
         |  -> JIT profile / compile / cache / GC
         v
  Measurement iterations    (thu số liệu chính)
         |
         v
  Kết thúc fork; có thể chạy JVM fork khác
~~~

Trong JMH, có thể cấu hình:

~~~java
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
~~~

Nghĩa là với mỗi trường hợp benchmark tương ứng, JMH dành năm iteration warmup (mỗi iteration khoảng một giây), rồi đo năm iteration (mỗi iteration khoảng một giây). Độ dài này là **ví dụ cấu hình**, không phải số lần bắt buộc hoặc bảo đảm mọi phương thức đã đạt steady state.

**Cần phân biệt:**

- **Warmup iteration:** một khoảng JMH chạy phép đo để làm nóng JVM, không đóng góp vào kết quả chính.
- **Measurement iteration:** một khoảng JMH thu dữ liệu được dùng tính điểm.
- **Số phép gọi bên trong iteration:** JMH điều phối theo cấu hình và throughput; không mặc định bằng một lần gọi phương thức.
- **JVM fork:** một tiến trình JVM mới, có trạng thái JIT/heap/class loading độc lập với tiến trình benchmark khác.

### Làm sao biết warmup đã đủ?

Không có một con số iterations phù hợp mọi máy/JDK/tác vụ. Hãy thử tăng hoặc giảm warmup trong cùng điều kiện, quan sát sự ổn định của thời gian đo theo iteration và độ biến động giữa các fork. Với code phức tạp, lớp nạp trễ hoặc nhiều nhánh, có thể cần thời gian dài hơn. Nếu hiệu năng thay đổi theo thời gian dài do cache, GC hoặc hành vi workload, đừng tự động coi một khoảng đo là steady state.

Đối với trường hợp muốn biết **cold-start latency**, thời gian khởi tạo mới là đối tượng cần nghiên cứu; không được dùng kết quả sau warmup để tuyên bố đó là chi phí khởi động. Hãy xây dựng thí nghiệm cold-start riêng.

## 3. Nhiều JVM fork: tách trạng thái giữa các lần thử

Nếu cùng một JVM chạy `directCall`, tiếp theo `reflectiveCall`, sau đó `methodHandleCall`, các benchmark có thể ảnh hưởng lẫn nhau thông qua JIT profile, heap, cache và những tài nguyên đã khởi tạo. Thay đổi thứ tự chạy có thể cho kết quả khác.

**Fork** trong JMH tạo JVM con độc lập cho mỗi lần lặp thử ở cấp tiến trình. Ví dụ:

~~~java
@Fork(value = 3, warmups = 1)
~~~

Trong cấu hình này:

- `value = 3`: ba **measurement forks** riêng biệt cho benchmark tương ứng.
- `warmups = 1`: một **warmup fork** bổ sung, không đóng góp vào thống kê chính của các measurement forks.
- Trong mỗi measurement fork, vẫn có các **warmup iterations** được cấu hình bằng `@Warmup`.

Đây là hai cấp làm nóng khác nhau: **warmup fork** là JVM riêng; **warmup iteration** chạy bên trong một fork. Không nhầm `@Fork(warmups = ...)` với `@Warmup(iterations = ...)`.

| Mức chạy | Điều gì được đặt lại? | Dữ liệu có góp vào điểm cuối? |
|---|---|---|
| Warmup iteration trong một fork | Vẫn giữ JVM/process hiện tại, state theo vòng đời JMH | Không |
| Measurement iteration trong một fork | Giữ JVM/process hiện tại, JMH đo theo cấu hình | Có |
| Measurement fork kế tiếp | Khởi động JVM mới; JIT profile, heap, runtime state của fork trước không truyền trực tiếp sang | Có |
| Warmup fork (nếu dùng) | JVM riêng, chạy warmup trước measurement forks | Không |

Nhiều fork giúp giảm phụ thuộc vào **một trạng thái JVM tình cờ**. Tuy nhiên chúng không loại bỏ nhiễu hệ điều hành hay phần cứng: các fork vẫn chạy trên cùng máy và có thể gặp tải nền, nhiệt độ hoặc tần số CPU khác nhau.

### Sử dụng thống kê đúng mức

Báo cáo nên có số fork, số warmup/measurement iterations, số thread, JDK, JVM flags, phần cứng và đơn vị. Khi số liệu dao động lớn, không nên chọn fork nhanh nhất rồi tuyên bố đó là kết quả đại diện. Xem độ phân tán, khoảng bất định mà JMH báo và các điểm bất thường; tăng độ dài thử nghiệm khi cần trước khi so sánh chênh lệch rất nhỏ.

**Quan trọng:** Fork là mô hình phù hợp để đo chi phí một tác vụ sau warmup trên nhiều JVM độc lập. Nếu mục tiêu là tác động của nhiều process đồng thời trong sản xuất, phải thiết kế workload tổng thể riêng; benchmark JMH fork tuần tự không tự mô phỏng toàn bộ môi trường production.

## 4. Dead-code elimination: phải dùng kết quả để giữ công việc cần đo

Một đoạn code không tạo ra ảnh hưởng quan sát được có thể bị compiler hoặc JIT tối ưu đi nếu việc loại bỏ vẫn giữ ngữ nghĩa chương trình. Đây là **dead-code elimination (DCE)**.

Ví dụ không đáng tin:

~~~java
@Benchmark
public void wrong() {
    int result = 10 * 20;
    // result không bao giờ được sử dụng.
}
~~~

Benchmark này có thể trở thành gần như không có việc gì để đo. Đối với gọi một phương thức thuần và dễ inline, rủi ro tương tự:

~~~java
@Benchmark
public void alsoWrong() {
    pureCalculation(7); // Bỏ qua giá trị trả về.
}
~~~

Nếu JIT chứng minh lời gọi không có side effect đáng quan sát, nó có thể loại bỏ phép tính. Nhưng với lời gọi có I/O, ghi state hoặc exception/khởi tạo có thể quan sát được, không thể khẳng định JIT được phép loại bỏ toàn bộ chỉ vì kết quả trả về không dùng.

### 4.1. Trả kết quả từ phương thức `@Benchmark`

Cách đơn giản cho phép đo một kết quả đơn lẻ:

~~~java
@Benchmark
public int better(Inputs state) {
    return pureCalculation(state.input);
}
~~~

JMH tạo mã harness sử dụng kết quả trả về để hạn chế DCE. Đây là lý do nhiều ví dụ JMH **trả một giá trị** thay vì khai báo `void` rồi bỏ kết quả.

### 4.2. Sử dụng `Blackhole`

Khi benchmark có nhiều kết quả hoặc cần tiêu thụ dữ liệu ngay trong phương thức, dùng `org.openjdk.jmh.infra.Blackhole`:

~~~java
@Benchmark
public void calculate(Inputs state, Blackhole blackhole) {
    int result = pureCalculation(state.input);
    blackhole.consume(result);
}
~~~

`Blackhole.consume` được JMH thiết kế để tiêu thụ giá trị trong benchmark mà không biến I/O hoặc lưu trữ kết quả vào một collection ngày càng lớn thành phần chi phí chính. Không dùng `System.out.println`, ghi file hoặc logging trong vòng đo chỉ nhằm “buộc dùng kết quả”; tác dụng phụ đó có thể áp đảo thao tác đang nghiên cứu.

**Lưu ý:** Trả kết quả hoặc dùng `Blackhole` giảm rủi ro DCE, nhưng **không bảo đảm** JIT không còn tối ưu hóa nào khác. Nếu kết quả là hằng số, JIT vẫn có thể **constant fold** phép tính trước khi giá trị được tiêu thụ.

## 5. Constant folding: benchmark có thể chỉ đo một hằng số

**Constant folding** là tối ưu hóa tính trước biểu thức từ các đầu vào mà compiler/JIT biết chắc. Ví dụ:

~~~java
static int score(int x) {
    return x * 31 + 7;
}

@Benchmark
public int misleading() {
    return score(42);
}
~~~

Nếu JIT inline `score`, nó có thể xác định luôn kết quả `42 * 31 + 7`. Benchmark khi đó có thể đo một đường đi đã được rút gọn, không phản ánh chi phí của phép tính với đầu vào runtime thay đổi.

Với reflection, tình huống tương tự có thể xảy ra khi:

- Phương thức đích thuần, target/đầu vào đủ ổn định để JIT suy ra kết quả.
- `Method` hoặc `MethodHandle` được cache và JIT có thể tối ưu hóa qua nhiều lớp adapter.
- Một mảng dữ liệu hoặc cấu trúc immutable có giá trị được biết rõ tại thời điểm tối ưu hóa.
- Vòng lặp tự viết gọi đi gọi lại cùng đối số hằng, khiến một phần phép tính bị **loop invariant code motion** (đưa ra ngoài vòng lặp).

Dù Java cho phép `Method.invoke` ném lỗi hoặc thực hiện kiểm tra kiểu/quyền, **không nên coi các lớp API reflection là rào chắn tối ưu hóa đáng tin cậy**. JEP 416 còn khiến việc tối ưu hóa liên quan method handles và metadata của các thành viên thường xuyên dùng trở thành vấn đề cần đo thực tế.

### 5.1. Cách chuẩn bị đầu vào khó bị biến thành hằng

Một cách phù hợp hơn cho phép đo *throughput* của một phương thức thuần là chuẩn bị dữ liệu trong `@State`, rồi đọc lần lượt trong mỗi invocation:

~~~java
@State(Scope.Thread)
public static class Inputs {
    @Param({"17", "41"})
    public int seed;

    private final int[] values = new int[1024];
    private int cursor;

    @Setup(Level.Trial)
    public void setup() {
        java.util.SplittableRandom random =
                new java.util.SplittableRandom(seed);
        for (int i = 0; i < values.length; i++) {
            values[i] = random.nextInt();
        }
    }

    public int next() {
        return values[(cursor++) & (values.length - 1)];
    }
}
~~~

Đặc điểm:

- Dữ liệu được sinh **ở runtime** trong `@Setup`, bên ngoài đường đo.
- Nhiều giá trị đầu vào khác nhau khiến kết quả không còn là một biểu thức duy nhất với literal `42`.
- `cursor` thay đổi qua các lần gọi, nên đường đi cần đọc dữ liệu theo thứ tự chạy.
- `@Param` tạo các **trường hợp benchmark riêng** cho từng seed; nó không tự thay đầu vào ở từng invocation.
- Dùng kích thước mảng lũy thừa của hai giúp phép `& (length - 1)` xoay vòng chỉ số cho số nguyên đã tăng; đây là lựa chọn minh họa, không phải yêu cầu JMH.

**Đánh đổi:** Đọc mảng và cập nhật chỉ số có chi phí. Khi so sánh direct/reflection/method handle, cần dùng **cùng một chiến lược lấy đầu vào** ở các phương án và ghi rõ kết quả đo bao gồm phần cung cấp đầu vào. Đừng tự động trừ chi phí `next()` bằng hai con số benchmark riêng: phép trừ các số đo có nhiễu dễ tạo ra kết luận thiếu tin cậy.

Không có kỹ thuật duy nhất chống mọi tối ưu hóa. Nếu workload production chủ yếu dùng một input cố định thì constant folding có thể phản ánh chính hiệu quả thực tế; nếu production xử lý input thay đổi liên tục, benchmark với literal cố định sẽ không đại diện.

## 6. Ví dụ JMH so sánh direct call, reflection và MethodHandle

Ví dụ minh họa **cùng một phép tính đích**, **cùng luồng dữ liệu runtime**, và cache metadata trước khi đo. Có thể đặt file `ReflectionPerformanceBenchmark.java` vào source của một dự án JMH đã cấu hình đúng annotation processor. JMH là thư viện benchmark OpenJDK bên ngoài Java SE; phải khai báo dependency và annotation processing tương ứng để biên dịch/chạy.

~~~java
package example.bench;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.util.SplittableRandom;
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

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(value = 3, warmups = 1)
public class ReflectionPerformanceBenchmark {

    public static final class Worker {
        public int compute(int value) {
            return Integer.rotateLeft(value * 31, 5) ^ 0x4A3B;
        }
    }

    @State(Scope.Thread)
    public static class BenchState {
        @Param({"17", "41"})
        public int seed;

        public final Worker worker = new Worker();
        public Method reflectedMethod;
        public MethodHandle methodHandle;

        private final int[] arguments = new int[1024];
        private int cursor;

        @Setup(Level.Trial)
        public void setup() throws ReflectiveOperationException {
            reflectedMethod = Worker.class.getMethod(
                    "compute", int.class);

            methodHandle = MethodHandles.publicLookup().findVirtual(
                    Worker.class,
                    "compute",
                    MethodType.methodType(int.class, int.class)
            );

            SplittableRandom random = new SplittableRandom(seed);
            for (int i = 0; i < arguments.length; i++) {
                arguments[i] = random.nextInt();
            }
        }

        public int nextArgument() {
            return arguments[(cursor++) & (arguments.length - 1)];
        }
    }

    @Benchmark
    public int direct(BenchState state) {
        return state.worker.compute(state.nextArgument());
    }

    @Benchmark
    public int reflection(BenchState state) throws Throwable {
        // Cache Method từ @Setup: đo invocation đã lookup.
        return (int) state.reflectedMethod.invoke(
                state.worker, state.nextArgument());
    }

    @Benchmark
    public int methodHandle(BenchState state) throws Throwable {
        // Call-site invokeExact: (Worker, int) -> int.
        return (int) state.methodHandle.invokeExact(
                state.worker, state.nextArgument());
    }
}
~~~

### 6.1. Vì sao ví dụ dùng cấu trúc này?

| Chi tiết | Ý nghĩa với phép đo |
|---|---|
| `@State(Scope.Thread)` | Mỗi benchmark thread có state riêng, tránh cùng ghi `cursor` |
| `@Param({"17", "41"})` | Chạy riêng từng giá trị seed; dễ kiểm tra độ phụ thuộc dữ liệu |
| `@Setup(Level.Trial)` | Chuẩn bị metadata và dữ liệu trước khi tính thời gian invocation |
| `reflectedMethod` được cache | Tách chi phí tra cứu `getMethod` khỏi lời gọi reflection |
| `methodHandle` được cache | Tách lookup handle khỏi `invokeExact` |
| `nextArgument()` ở cả ba benchmark | Cùng cách đọc dữ liệu runtime, hạn chế input cố định |
| Trả `int` | JMH sử dụng kết quả benchmark, giảm nguy cơ DCE |
| `@Fork`, `@Warmup`, `@Measurement` | Tách JVM, giai đoạn làm nóng và giai đoạn đo |

**Giải thích về kiểu đối số:** `Method.invoke` nhận `Object...`, nên `int` từ `nextArgument()` được boxing thành `Integer` ở vị trí gọi rồi có thể được unbox khi truyền đến `compute(int)`. Kết quả `int` của phương thức đích cũng được boxing trước khi `invoke` trả `Object`. Trong khi đó, `MethodHandle.invokeExact` có signature được kiểm tra tại call site; dòng mã đang dùng đúng dạng `(Worker, int) -> int`. Ba đường gọi có ngữ nghĩa và overhead khác nhau, nên kết quả **không chỉ** phản ánh một thao tác dispatch thuần.

**Giải thích về dữ liệu:** `Integer.rotateLeft` là API Java được hỗ trợ lâu dài. Kết quả phép tính là một `int`, không ghi vào trạng thái chung. Giá trị đầu vào được tạo trong setup và đọc tại runtime. JMH trả kết quả về harness thay vì dùng `println` trong vòng đo.

### 6.2. Chạy phép đo

Sau khi cấu hình và build một dự án JMH sao cho tạo ra benchmark executable JAR (thường là `target/benchmarks.jar` khi dùng bộ khung Maven JMH), có thể chạy:

~~~shell
java -jar target/benchmarks.jar ReflectionPerformanceBenchmark
~~~

Lệnh trên áp dụng các annotation cấu hình mặc định trong source. Nếu muốn thay đổi thông số để khảo sát sự ổn định:

~~~shell
java -jar target/benchmarks.jar ReflectionPerformanceBenchmark -f 3 -wi 5 -i 5 -w 1s -r 1s -t 1
~~~

Các lựa chọn chính:

| Tham số | Ý nghĩa |
|---|---|
| `-f 3` | Ba measurement forks; mỗi fork là JVM riêng |
| `-wi 5` | Năm warmup iterations trong fork |
| `-i 5` | Năm measurement iterations trong fork |
| `-w 1s` | Thời lượng mỗi warmup iteration |
| `-r 1s` | Thời lượng mỗi measurement iteration |
| `-t 1` | Một thread cho benchmark được chạy |
| `-prof gc` | Có thể thêm để thu thông tin GC/allocation nếu môi trường hỗ trợ profiler JMH tương ứng |

Lệnh chỉ là **hướng dẫn tự chạy** sau khi cài JMH và build dự án; STEP 4 không yêu cầu thực thi JMH/Gradle/Maven hoặc khẳng định sẵn bất kỳ số đo cụ thể nào.

### 6.3. Cách đọc kết quả

Chế độ `AverageTime` với `NANOSECONDS` thường cho đầu ra dạng:

~~~text
Benchmark                                  (seed)  Mode  Cnt   Score    Error  Units
ReflectionPerformanceBenchmark.direct         17  avgt   ...    ...      ...  ns/op
ReflectionPerformanceBenchmark.reflection     17  avgt   ...    ...      ...  ns/op
ReflectionPerformanceBenchmark.methodHandle   17  avgt   ...    ...      ...  ns/op
~~~

Các dấu `...` là **chỗ trống**, không phải kết quả đo thực tế. Cần xem toàn bộ log, thống kê giữa các forks và thời gian theo iteration. `ns/op` nghĩa là thời gian trung bình báo cáo cho một lần benchmark operation theo cấu hình, **không** tự có nghĩa mỗi lần gọi Java đích bên trong sản phẩm đều mất đúng số nanosecond đó.

Nếu benchmark `direct` mất phần lớn thời gian đọc mảng và cập nhật `cursor`, chênh lệch dispatch có thể bị che lấp. Nếu benchmark `reflection` bao gồm boxing và adapter, đó là chi phí **đường gọi reflection thực tế trong ví dụ**. Đừng chuyển chênh lệch này thành tuyên bố rằng mọi ứng dụng sẽ nhanh/chậm hơn cùng tỉ lệ.

## 7. Constant folding còn có thể đến từ đâu?

### 7.1. Literal, `static final` và phương thức thuần

~~~java
private static final int FIXED = 42;

@Benchmark
public int constantArgument() {
    return WorkerMath.compute(FIXED);
}
~~~

Nếu `WorkerMath.compute` thuần và được inline, `FIXED` có thể khiến phần lớn phép tính trở thành hằng. `final` và hằng biên dịch không tự gây sai, nhưng có thể làm benchmark không đại diện cho luồng input của ứng dụng.

### 7.2. Vòng lặp tự viết có thể bị dời phép tính ra ngoài

~~~java
long start = System.nanoTime();
int sum = 0;
for (int i = 0; i < 1_000_000; i++) {
    sum += pureCompute(5);
}
long elapsed = System.nanoTime() - start;
System.out.println(sum + " " + elapsed);
~~~

Ngay cả khi `sum` được in ra nên không biến mất hoàn toàn, compiler/JIT có thể tối ưu hóa phần tính `pureCompute(5)` hoặc biến đổi vòng lặp theo ngữ nghĩa cho phép. **Dùng kết quả cuối không đồng nghĩa từng vòng đã thực hiện chi phí như ở mã nguồn.** Trong JMH, hãy biểu diễn một operation phù hợp hoặc dùng cơ chế batch rõ ràng và kiểm soát tính hợp lệ của phép đo.

### 7.3. Metadata reflection được cache ở đâu cũng có thể ảnh hưởng

JEP 416 cho biết một số trường hợp reflection hoạt động tốt hơn khi các đối tượng `Method`, `Constructor` hoặc `Field` giữ ở những nơi JIT có thể nhận ra tính ổn định (ví dụ trường `static final`). Nếu benchmark cache trong một mutable instance field, dạng tối ưu hóa có thể khác với một `static final Method` tại runtime.

Do đó, **hai tình huống hợp lệ nhưng đo các cách dùng khác nhau**:

- `Method` được lookup một lần rồi giữ trong state của một framework.
- `Method` được khai báo `static final`, khởi tạo một lần và tái sử dụng.

Nếu muốn so sánh ảnh hưởng vị trí cache, hãy tạo **hai benchmark riêng**, giữ cùng target/công việc/đầu vào, và ghi rõ giả thiết. Không lấy số liệu chỉ từ một cách cache để kết luận rằng mọi lời gọi reflection trên mọi JDK có cùng hiệu năng.

### 7.4. Dữ liệu `@Param` không tự giải quyết mọi vấn đề

`@Param({"17","41"})` tạo nhiều cấu hình benchmark. Với từng cấu hình, tham số có thể giữ nguyên suốt trial. Nếu công việc chỉ là `compute(state.seed)` trên một hàm thuần, JIT vẫn có thể tối ưu theo một đầu vào ổn định. Vì vậy ví dụ mục 6 vừa dùng `@Param` để đổi bộ dữ liệu, vừa dùng mảng nhiều giá trị và con trỏ cập nhật lúc chạy.

## 8. Phân biệt benchmark lookup, invocation và workflow thật

Một lỗi phổ biến khác không liên quan trực tiếp tới warmup là dùng chung một tên benchmark cho các công việc khác nhau:

~~~java
// Bao gồm chi phí tìm Method trong mỗi operation.
@Benchmark
public Object lookupAndInvoke(BenchState state)
        throws ReflectiveOperationException {
    Method method = Worker.class.getMethod("compute", int.class);
    return method.invoke(state.worker, state.nextArgument());
}
~~~

Trường hợp này đo **lookup + invoke**. Benchmark `reflection` ở mục 6 đo **invoke với metadata được cache trước**. Không thể khẳng định chênh lệch giữa hai số là đúng chi phí lookup độc lập trong mọi điều kiện, vì tối ưu hóa, allocation và tác động của việc ghép thao tác có thể khác nhau.

Đề xuất xác định kịch bản thực:

| Kịch bản ứng dụng | Benchmark phù hợp |
|---|---|
| Framework khởi động, quét metadata rồi dùng cùng method nhiều lần | Cache metadata trong `@Setup`, đo invocation ở steady state; đo startup riêng nếu cần |
| Công cụ xử lý từng class mới trong một batch | Đo cả metadata lookup/validation của batch theo mô hình gần thực tế |
| Route gọi rất thường xuyên, ít metadata thay đổi | Đo đường dispatch đã cache, cùng kiểu đối số production |
| Đường khởi tạo plugin với class loading và reflection | Đo end-to-end initialization hoặc startup; không suy từ microbenchmark invocation |
| Ứng dụng cần SLA latency | Xem phân vị latency, GC/tail behavior và workload thực; average ns/op không đủ |

Cần phân biệt thao tác **trong** vòng đo với thao tác **trong** `@Setup`. Nếu ứng dụng mỗi request đều lookup method thì chuyển lookup ra setup có thể đánh giá quá lạc quan; nếu ứng dụng cache metadata một lần, đưa lookup vào từng invocation lại đánh giá khác với đường đi thật.

## 9. Nhiễu còn lại sau khi dùng JMH

JMH giúp giảm nhiều lỗi benchmark thường gặp, nhưng không thể biến mọi kết quả thành một chân lý phổ quát:

- **JDK/JVM flags:** tiered compilation, GC, heap, access checks và khả năng JIT tối ưu có thể khác giữa các JDK được hỗ trợ và cấu hình.
- **Hardware và hệ điều hành:** số lõi, tần số, chế độ tiết kiệm năng lượng, nhiệt độ, container CPU quota, tải nền.
- **Đặc điểm target:** public/private, static/instance, độ lớn và khả năng inline của method, số tham số, primitive/reference, boxing/varargs.
- **Kiểu cache metadata:** tra cứu mới mỗi lần, mutable field, final field, static final field.
- **Độ biến thiên đầu vào:** random runtime, dữ liệu thực, tính phụ thuộc nhánh và memory locality.
- **Allocation/GC:** `Method.invoke` có đường gọi object-based; mức allocation thực phải đo thay vì chỉ suy từ source.
- **Độ dài đo:** quá ngắn có thể mang nhiễu; quá dài vẫn có thể thay đổi do nhiệt/GC/thao tác khác trên máy.

Một lần chạy ổn định không bảo đảm là **đúng workload**. Nên ghi chú cấu hình thí nghiệm ngay cạnh biểu đồ và số liệu.

### 9.1. Không dùng vòng benchmark để in log hoặc kiểm tra assert

~~~java
@Benchmark
public int calculation(BenchState state) {
    int result = state.worker.compute(state.nextArgument());
    // Không println/assert/log ở mỗi invocation.
    return result;
}
~~~

Kiểm thử tính đúng của `Worker.compute` nên là một bước độc lập. Trong benchmark, JMH tiêu thụ return value; nếu cần nhiều kết quả dùng `Blackhole` phù hợp. `assert` mặc định có thể bị tắt và việc bật assert có thể thay đổi workload. Nếu thêm kiểm tra để bảo vệ invariant, phải ghi rõ chi phí và ý nghĩa.

### 9.2. Cẩn thận với so sánh thứ tự đơn lẻ

Đừng đưa ra nhận xét như “method handle luôn nhanh hơn reflection” hoặc “JEP 416 khiến reflection nhanh hơn X lần” chỉ từ một bảng. JEP 416 là thay đổi triển khai, còn tốc độ phụ thuộc method được gọi, cách lưu metadata, trạng thái JIT, JDK và môi trường. Kết quả một benchmark chỉ khẳng định điều nó thật sự đo trong cấu hình được báo cáo.

## 10. Quy trình thiết kế thí nghiệm có thể kiểm chứng

Các bước dưới đây hữu ích khi phải trả lời câu hỏi “trên JDK hiện tại, lời gọi động nào phù hợp hơn cho đường xử lý của ứng dụng?”:

1. **Định nghĩa câu hỏi:** so chi phí invocation đã cache, chi phí lookup, hay thời gian workflow thật; chọn một đơn vị đo thống nhất.
2. **Giữ đúng hành vi:** các phương án direct/reflection/method handle phải tính cùng một kết quả nghiệp vụ, sử dụng receiver và kiểu đối số hợp lệ.
3. **Tạo dữ liệu runtime:** dùng `@State`, `@Param` hoặc dataset phản ánh sản phẩm; rà soát literal và giá trị không đổi làm JIT rút gọn.
4. **Đảm bảo kết quả được dùng:** trả từ `@Benchmark` hoặc sử dụng `Blackhole`. Không log trong phép đo.
5. **Tách setup và đo:** chuẩn bị metadata trong `@Setup` nếu câu hỏi chỉ là invoke đã cache; đo startup/lookup bằng phép thử riêng khi cần.
6. **Warmup đủ:** chọn warmup iterations và thời lượng phù hợp, quan sát độ ổn định.
7. **Đo nhiều JVM fork:** so độ phân tán giữa các tiến trình độc lập, không dựa vào một fork nhanh nhất.
8. **Giữ môi trường nhất quán:** ghi lại JDK, JVM flags, core/thread, heap, hệ điều hành, cách đặt dữ liệu và cấu hình JMH.
9. **Đánh giá sai số:** đọc số liệu theo iteration và fork, xem bất định, kiểm tra GC/allocation nếu liên quan.
10. **Diễn giải có giới hạn:** báo cáo kết quả đo cho workload đã định nghĩa, rồi kiểm tra tác động end-to-end trước khi thay đổi kiến trúc.

### Mẫu báo cáo nên có

| Hạng mục | Thông tin cần điền |
|---|---|
| Mục đích | Ví dụ: so `direct`, cached `Method.invoke`, cached `MethodHandle.invokeExact` |
| JDK | Distribution, phiên bản, kiến trúc JVM, JVM flags |
| Máy thử | CPU, RAM, hệ điều hành, tải nền/giới hạn container |
| Kích thước và nguồn dữ liệu | Dataset, seed, cách sinh/chọn input |
| JMH | Phiên bản JMH, mode, đơn vị, thread, time/iteration |
| Warmup | Iterations, duration, warmup forks (nếu có) |
| Measurement | Iterations, duration, measurement forks |
| Kết quả | Điểm, bất định/biến động, allocation/GC nếu đo |
| Ý nghĩa | Thao tác nào được đo và khác biệt so với production |
| Giới hạn | Ví dụ: overhead đọc mảng, boxing, kiểu cache `Method` |

Không ghi một con số throughput hoặc latency tự đoán vào báo cáo. Nếu chưa chạy JMH, mô tả đây là **thiết kế benchmark** và cung cấp lệnh thực thi, không coi kết quả dự kiến là dữ liệu đã quan sát.

## 11. Câu hỏi tự kiểm tra và bài tập

1. Tại sao lấy `System.nanoTime()` quanh một vòng lặp triệu lần rồi chia không đủ để kết luận chi phí `Method.invoke`?
2. Warmup iteration khác warmup fork ra sao? Mỗi loại ảnh hưởng gì đến JVM và dữ liệu báo cáo?
3. Vì sao hai phép đo trong cùng JVM có thể không độc lập dù dùng `System.nanoTime()` riêng?
4. Điều gì có thể xảy ra nếu phương thức `@Benchmark` tính toán nhưng bỏ hoàn toàn giá trị trả về?
5. JMH dùng kết quả được `@Benchmark` trả về như thế nào để giảm nguy cơ DCE? Khi nào nên dùng `Blackhole`?
6. Vì sao trả một giá trị từ benchmark **không đủ** để loại trừ constant folding?
7. `@Param({"17","41"})` có làm dữ liệu thay đổi mỗi lần invocation không? Vai trò của `nextArgument()` trong ví dụ là gì?
8. Khi so sánh ba phương án ở mục 6, chi phí nào đến từ việc sử dụng `Object...` của `Method.invoke`?
9. Nếu chuyển `getMethod(...)` từ `@Setup` vào `@Benchmark`, câu hỏi thí nghiệm đã thay đổi thế nào?
10. Tại sao có thể đo riêng trường hợp `Method` được cache bằng `static final` thay vì chỉ benchmark một mutable field?
11. Vì sao không nên lấy một fork nhanh nhất hoặc một điểm `ns/op` để khẳng định mọi JDK đều có cùng tỷ lệ hiệu năng?
12. Hãy chạy benchmark JMH trong một dự án được cấu hình đúng. Thử đổi warmup và fork, xem độ phân tán; sau đó so phiên bản luôn dùng literal `42` với phiên bản dùng runtime dataset. Ghi rõ những gì thay đổi và tránh đưa ra kết luận nếu sai số lớn.

**Ghi nhớ:** Một phép đo reflection đáng tin phải xác định rõ workload, **warmup** trước khi đo steady state, thu kết quả trên **nhiều JVM fork**, **tiêu thụ kết quả** để hạn chế dead-code elimination và **kiểm tra khả năng constant folding** do dữ liệu hoặc metadata quá ổn định. JMH giúp thực hiện những bước này có hệ thống, nhưng người viết benchmark vẫn phải bảo đảm phép đo phản ánh đúng đường gọi ứng dụng. JEP 416 không thay thế yêu cầu kiểm chứng trên JDK và cấu hình thực tế đang sử dụng.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416).
- [OpenJDK Java Microbenchmark Harness (JMH) — dự án và tài liệu hướng dẫn](https://github.com/openjdk/jmh).
- [Java SE 25: `Method.invoke` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html).
- [Java SE 25: `MethodHandle.invokeExact` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html).
- [Java SE 25: `System.nanoTime` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()).

