# So sánh pattern matching với polymorphic dispatch: hiệu năng và lựa chọn thiết kế (Java 21+)

## 1. Câu hỏi chính: nên dùng `switch` pattern hay gọi phương thức đa hình?

Trong Java, cùng một thao tác có thể được chọn theo **kiểu runtime** của đối tượng bằng hai lối thiết kế:

- **Polymorphic dispatch (điều phối đa hình)**: khai báo một phương thức trên interface/class cha; mỗi subtype cung cấp cách thực hiện và ta gọi `obj.method()`. JVM lựa chọn implementation thích hợp cho đối tượng nhận lời gọi.
- **Pattern matching dispatch**: đặt logic ở một hàm xử lý bên ngoài, dùng `switch (obj)` với `case Type(...)` hoặc `case Type variable`; Java chọn case theo kiểu/cấu trúc và điều kiện `when`, rồi thực thi logic tương ứng.

Hai cách không chỉ khác cú pháp. Chúng có sự đánh đổi về **vị trí đặt hành vi**, **khả năng mở rộng**, **số lượng bước kiểm tra kiểu**, **khả năng JIT tối ưu**, và chi phí phối hợp với các phép tính/đọc dữ liệu thật.

**Không có quy tắc chung rằng pattern luôn nhanh hơn polymorphism, hoặc ngược lại.** HotSpot có thể tối ưu cả hai; kết quả phụ thuộc vào kiểu đối tượng tại call site, số subtype xuất hiện, logic nhánh, dữ liệu, phiên bản JDK, thời gian warm-up và môi trường thực thi. Nếu không chạy benchmark đúng cách, phát biểu “A nhanh hơn B X%” không có cơ sở.

Bài dùng Java **21+** vì `record patterns` và `pattern matching for switch` đã ổn định từ Java 21. Ta sẽ viết hai cách có **ngữ nghĩa tương đương**, kiểm tra tính đúng trước và thiết kế phép đo bằng **JMH** (Java Microbenchmark Harness).

## 2. Hai mô hình dispatch nhìn từ code

Giả sử hệ thống nhận ba loại phép tính: giá trị cố định, phép cộng và phép nhân.

### Cách A — đa hình: hành vi nằm trong từng subtype

~~~java
sealed interface Operation permits Value, Add, Multiply {
    int viaMethod();
}

record Value(int number) implements Operation {
    public int viaMethod() { return number; }
}
record Add(int left, int right) implements Operation {
    public int viaMethod() { return left + right; }
}
record Multiply(int left, int right) implements Operation {
    public int viaMethod() {
        return left == 0 || right == 0 ? 0 : left * right;
    }
}
~~~

Khi gọi:

~~~java
Operation operation = new Add(2, 3);
int result = operation.viaMethod(); // 5
~~~

Nguồn gọi chỉ biết interface `Operation`. JVM phải thực hiện phương thức implementation tương ứng với **kiểu runtime của receiver**. Đây là dispatch động qua interface (trên bytecode thường là `invokeinterface`); không phải một chuỗi `instanceof` viết thủ công ở mã nguồn.

### Cách B — pattern switch: hành vi nằm trong hàm xử lý

~~~java
static int viaPattern(Operation operation) {
    return switch (operation) {
        case Value(var number) -> number;
        case Add(var left, var right) -> left + right;
        case Multiply(var left, var right)
                when left == 0 || right == 0 -> 0;
        case Multiply(var left, var right) -> left * right;
    };
}
~~~

Ở cách này:

1. `switch` chọn một case dựa trên subtype của `Operation`.
2. `record pattern` tách các component, ví dụ `Add(var left, var right)`.
3. Guard `when` kiểm tra điều kiện chỉ khi pattern tương ứng khớp.
4. Case trả kết quả của switch expression.

Vì `Operation` là `sealed` và đã liệt kê đủ ba subtype, switch expression có thể **exhaustive** mà không cần `default`. Case có guard cho `Multiply` đứng trước case tổng quát của cùng record để tránh dominance.

**Khác biệt thiết kế:** đa hình phân tán các nhánh hành vi vào từng subtype; pattern switch gom một phép xử lý vào một điểm điều phối. Chưa có thông tin nào trong hai đoạn mã tự chứng minh cách nào chạy nhanh hơn sau JIT.

## 3. So sánh ở góc độ JVM và JIT

### 3.1. Polymorphic dispatch không nhất thiết luôn tốn “một lần nhảy ảo” đắt đỏ

Ở mức bytecode, lời gọi qua interface thường dùng `invokeinterface`; lời gọi qua class có thể dùng `invokevirtual`. Tuy nhiên, khi JVM thực thi nóng (*hot path*), HotSpot có thể dựa vào profiling và phân tích kiểu để tối ưu:

- **Monomorphic call site:** đa số/chỉ một kiểu receiver được quan sát tại một điểm gọi. JIT có thể suy ra đích, thực hiện *devirtualization* và **inline** implementation.
- **Bimorphic call site:** thường gặp hai kiểu receiver. JVM có thể tối ưu một số tình huống dựa trên các kiểu nổi trội và profiling.
- **Megamorphic call site:** xuất hiện nhiều kiểu receiver. Khả năng inline từng target có thể bị hạn chế; nhưng mức độ ảnh hưởng vẫn tùy code, profile và JIT.

Nếu method đã được inline, chi phí dispatch nguồn gần như có thể biến mất khỏi đường nóng. Vì vậy nói “virtual call luôn chậm hơn một chuỗi type check” là không chính xác.

Các thuật ngữ mono/bi/mega mô tả **phân bố receiver tại call site** và độ đa dạng thực tế, không chỉ số subtype tồn tại trong code. Một interface có mười implementation vẫn có thể có call site monomorphic nếu luồng đó chỉ nhận một loại object.

### 3.2. Pattern switch cũng không có chi phí cố định

Với pattern switch, bytecode và cách HotSpot hạ thấp quá trình chọn case phụ thuộc vào compiler/JDK và cấu trúc pattern. Một implementation có thể dùng các kiểm tra kiểu, cơ chế bootstrap cho type switch, các nhánh điều kiện và lời gọi accessor để deconstruct record. **Đừng mặc định** Java luôn sinh một chuỗi `if (obj instanceof X)` nguyên xi, cũng đừng mặc định mọi switch pattern là bảng nhảy O(1).

JIT có thể inline quá trình lấy component hoặc tối ưu một số phép kiểm tra, nhưng lợi ích tùy trường hợp. Với **nested record patterns**, chi phí có thể đến từ việc đọc nhiều component và kiểm tra thêm kiểu/guard. Với `when`, cả pattern lẫn điều kiện phải được đánh giá theo luồng của case.

Ngược lại, một polymorphic method có thể cũng cần chính những kiểm tra/đọc component đó để tính cùng kết quả. **Chỉ so sánh công bằng khi hai biến thể làm cùng công việc**.

### 3.3. Tại sao “số case” không dự đoán được latency?

Hai switch có cùng số case vẫn có thể khác biệt vì:

- Nhánh **thường gặp** có được chọn sớm, bộ phân phối kiểu có được tối ưu hay không.
- Pattern gồm chỉ type test hay cần **deconstruction nhiều cấp**.
- Guard đơn giản hay phải gọi nhiều phương thức có side effect/chi phí cao.
- Phân bố input: 99% một subtype hay chia đều nhiều subtype.
- Chi phí nội bộ case: tính toán vài phép toán so với gọi I/O, parser hoặc xử lý collection.
- Việc cấp phát object và GC có nằm trong đường đo không.
- Khả năng compiler/JIT inline code, speculative optimization, deoptimization.
- JDK vendor, phiên bản JVM, CPU, warm-up, flags, tình trạng máy.

Khi nội dung xử lý là gọi database hoặc mạng, chênh lệch vài thao tác dispatch có thể không đáng kể so với I/O. Khi mỗi lời gọi chỉ làm phép toán đơn giản hàng trăm triệu lần, dispatch và khả năng inline mới có thể ảnh hưởng đáng kể.

## 4. So sánh công bằng ở mức thiết kế

| Tiêu chí | Polymorphic dispatch | Pattern matching dispatch |
| --- | --- | --- |
| Đặt hành vi | Trong class/record implement interface | Trong hàm `switch` hoặc handler bên ngoài |
| API gọi | `operation.viaMethod()` | `evaluate(operation)` |
| Thêm subtype | Subtype phải implement hành vi của interface; với sealed còn cần cập nhật permits | Với sealed exhaustive switch, code xử lý có thể phải thêm case |
| Thêm operation mới | Có thể phải thay interface và nhiều subtype | Thêm một hàm switch mới mà không cần sửa subtype hiện có |
| State/encapsulation | Hành vi có thể sử dụng state và invariant nội bộ | Logic bên ngoài thường cần accessor/component công khai |
| Type check trực tiếp | Code nguồn không cần case theo kiểu cho hành vi chính | Code nguồn công khai sự phân loại theo subtype |
| Record patterns, guard | Không cần để dispatch phương thức | Thuận tiện với record deconstruction, `when`, nested matching |
| Null input | Gọi method trên null gây NPE, trừ khi được kiểm tra trước | Switch reference selector null cũng NPE nếu thiếu `case null` |
| Hiệu năng | Có thể devirtualize/inline; phụ thuộc type profile | Có thể tối ưu chọn case/deconstruction; phụ thuộc workload/JIT |
| Test | Test implementation từng subtype và hành vi qua interface | Test từng pattern, guard true/false, null/nested cases |

**Không có hàng nào trong bảng là bảo đảm tốc độ.** Chúng mô tả cấu trúc và cơ hội tối ưu khác nhau, cần đo khi tối ưu hóa là yêu cầu quan trọng.

## 5. Kiểm tra tính đúng trước khi đo hiệu năng

Benchmark vô nghĩa nếu hai cách trả kết quả khác nhau hoặc một cách bỏ bớt validation. Trước khi đo, thống nhất:

- **Cùng input:** cùng tập đối tượng, cùng thứ tự và phân bố subtype.
- **Cùng phép tính:** ví dụ với `Multiply`, hai biến thể đều xử lý `left == 0 || right == 0` như nhau.
- **Cùng xử lý lỗi/null:** không được để một cách bỏ qua exception còn cách kia phải kiểm tra điều kiện.
- **Cùng số kết quả:** nếu một cách tính tổng 1024 phần tử, cách kia cũng phải tính 1024 phần tử.
- **Không đặt data setup vào một benchmark mà không đặt vào benchmark kia.**

Một phép đối chiếu thực tế nên dùng **assertion** để chứng minh hai hàm cho kết quả bằng nhau trên cùng mẫu input. Ví dụ ở mục 7 cho cả phép toán thường, zero short-circuit, số âm và null.

Đúng kết quả trên bộ input mẫu chưa phải chứng minh tương đương toán học cho mọi `int`; tuy nhiên đây là bước kiểm tra thiết yếu để loại lỗi cấu hình trước khi chạy JMH.

## 6. Null, exhaustiveness và side effects có thể làm hai cách lệch nghĩa

### 6.1. Null input

~~~java
Operation operation = null;

// Đa hình: operation.viaMethod() -> NullPointerException.
// Pattern switch không có case null -> NullPointerException.
~~~

Hai lời gọi đều có thể ném NPE nhưng **message, vị trí ném và stack trace không nhất thiết giống nhau**. Trong ví dụ hoàn chỉnh, ta dùng `Objects.requireNonNull(operation, "operation")` ở cả hai hàm để cùng công bố một tiền điều kiện.

Nếu một hàm trả kết quả mặc định cho null bằng `case null` còn hàm kia ném NPE, hai hàm **không tương đương**. Không được đưa chênh lệch đó vào benchmark như thể chỉ khác kỹ thuật dispatch.

### 6.2. Sealed và exhaustive switch

~~~java
sealed interface Operation permits Value, Add, Multiply {}
~~~

Nếu toàn bộ subtype được liệt kê trong pattern switch, compiler có thể kiểm tra exhaustiveness. Thêm một subtype mới khiến switch có thể không còn exhaustive và phải được cập nhật. Nhưng một interface chứa phương thức `viaMethod()` cũng buộc một subtype concrete mới phải implement phương thức đó. **Cả hai đều có loại kiểm tra compile-time**, chỉ khác vị trí đặt hành vi và điểm cần cập nhật.

Nếu dùng `default` trong switch để nuốt subtype mới, bạn có thể đánh mất tín hiệu compile-time quan trọng. Khi yêu cầu domain “mọi subtype phải được xử lý có chủ đích”, ưu tiên switch exhaustive trên sealed hierarchy nếu phù hợp.

### 6.3. Side effects

Nếu phương thức đa hình có log, mutation, caching, lazy-loading hoặc đọc đồng hồ, trong khi switch chỉ tính số thì **chưa phải cùng nghiệp vụ**. Record pattern có thể gọi accessor; accessor được tự định nghĩa có thể chứa hành vi, không phải lúc nào cũng là “đọc field miễn phí”.

Để đo riêng dispatch, ưu tiên dữ liệu đã khởi tạo, phép tính thuần và không I/O. Để đánh giá *end-to-end performance*, đo trong ngữ cảnh use case thật, nơi side effects là một phần bắt buộc của nghiệp vụ.

## 7. Chương trình Java 21+ hoàn chỉnh: cùng kết quả, hai cách dispatch

Lưu thành **`PatternVsDispatchDemo.java`**:

~~~java
import java.util.Objects;

public class PatternVsDispatchDemo {
    sealed interface Operation permits Value, Add, Multiply {
        int viaMethod();
    }

    record Value(int number) implements Operation {
        public int viaMethod() { return number; }
    }

    record Add(int left, int right) implements Operation {
        public int viaMethod() { return left + right; }
    }

    record Multiply(int left, int right) implements Operation {
        public int viaMethod() {
            return left == 0 || right == 0
                    ? 0 : left * right;
        }
    }

    static int viaPolymorphism(Operation operation) {
        Objects.requireNonNull(operation, "operation");
        return operation.viaMethod();
    }

    static int viaPattern(Operation operation) {
        Objects.requireNonNull(operation, "operation");
        return switch (operation) {
            case Value(var number) -> number;
            case Add(var left, var right) -> left + right;
            case Multiply(var left, var right)
                    when left == 0 || right == 0 -> 0;
            case Multiply(var left, var right) -> left * right;
        };
    }

    public static void main(String[] args) {
        Operation[] operations = {
            new Value(7), new Add(2, 3), new Multiply(4, 5),
            new Multiply(0, 9), new Multiply(8, 0),
            new Value(-3), new Add(-5, 1), new Multiply(-2, 3)
        };

        int totalVirtual = 0, totalPattern = 0;
        for (Operation operation : operations) {
            int virtualResult = viaPolymorphism(operation);
            int patternResult = viaPattern(operation);

            if (virtualResult != patternResult) {
                throw new AssertionError(operation + " -> "
                        + virtualResult + " != " + patternResult);
            }

            System.out.println(
                    operation.getClass().getSimpleName()
                    + ": " + virtualResult + " = " + patternResult);

            totalVirtual += virtualResult;
            totalPattern += patternResult;
        }

        System.out.println("Tổng: "
                + totalVirtual + " = " + totalPattern);

        try {
            viaPolymorphism(null);
        } catch (NullPointerException ex) {
            System.out.println("Virtual null: " + ex.getMessage());
        }

        try {
            viaPattern(null);
        } catch (NullPointerException ex) {
            System.out.println("Pattern null: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 21 trở lên:

~~~bash
javac --release 21 PatternVsDispatchDemo.java
java PatternVsDispatchDemo
~~~

Đầu ra:

~~~text
Value: 7 = 7
Add: 5 = 5
Multiply: 20 = 20
Multiply: 0 = 0
Multiply: 0 = 0
Value: -3 = -3
Add: -4 = -4
Multiply: -6 = -6
Tổng: 19 = 19
Virtual null: operation
Pattern null: operation
~~~

**Diễn giải:**

- `Value` trả component số nguyên; `Add` trả tổng; `Multiply` thực hiện guard/short-circuit cho tham số bằng zero.
- Ở `viaPolymorphism`, call site dùng `operation.viaMethod()`. Với từng record khác nhau, JVM chọn implementation tương ứng.
- Ở `viaPattern`, `switch` dùng record pattern; guard `when` được xét trước nhánh `Multiply` tổng quát.
- Cả hai trả cùng kết quả trên tám input, kể cả số âm, zero, và in tổng bằng 19.
- Cả hai thực hiện `Objects.requireNonNull` để công bố chính sách null giống nhau.
- Kết quả trên là **kiểm tra đúng/sai**, không phải số liệu về thời gian.

## 8. Vì sao không nên tự dùng `System.nanoTime()` trong một vòng lặp đơn giản?

Ví dụ chưa đủ tin cậy:

~~~java
long started = System.nanoTime();
for (int i = 0; i < 100_000; i++) {
    result += operation.viaMethod();
}
long elapsed = System.nanoTime() - started;
System.out.println(elapsed);
~~~

Các vấn đề:

1. HotSpot **warm-up** và profiling có thể thay đổi code máy sau nhiều lần thực thi; lần đo đầu không đại diện cho steady state.
2. Compiler có thể nhận ra công việc dư thừa, hằng số hoặc kết quả không được dùng rồi **constant fold / dead-code eliminate**.
3. `System.nanoTime()` chỉ đo khoảng thời gian, không cung cấp thiết kế thống kê, forks và kiểm soát lỗi benchmark.
4. GC, lịch của OS, CPU frequency, nhiệt độ máy và hoạt động nền tạo nhiễu.
5. Nếu tập đầu vào toàn một subtype, kết quả không đại diện cho call site hỗn hợp subtype.
6. Đặt việc cấp phát dữ liệu trong vòng lặp có thể khiến bạn đo allocation/GC thay vì chỉ dispatch.
7. Một lần chạy có thể may mắn nhanh hơn mà **không có ý nghĩa thống kê**.

Công cụ khuyến nghị là **JMH** của dự án OpenJDK. JMH giúp quản lý warm-up, measurement iterations, fork JVM, đối số/tham số benchmark và tiêu thụ kết quả. Tuy nhiên JMH **không tự động khiến thiết kế phép đo trở nên đúng**: test workload vẫn phải đại diện và benchmark code cần được review.

## 9. Thiết kế JMH: giữ nguyên phép tính và thay phân bố subtype

Để so sánh tương đối công bằng, benchmark nên:

- Khởi tạo các instance trước khi đo bằng `@Setup(Level.Trial)`.
- Cho **cả hai benchmark** duyệt cùng mảng `Operation[]` và tính cùng tổng.
- Trả về tổng để JMH sử dụng kết quả, giảm nguy cơ công việc bị loại bỏ.
- Thử nhiều phân bố **monomorphic** (một subtype), **bimorphic** (hai subtype), và **mixed** (ba subtype, xen kẽ zero/nonzero).
- Chọn cùng các tham số warm-up, measurement, fork và JVM cho hai phương thức.
- Thực hiện **correctness tests riêng**; kết quả JMH không thể thay assertion.
- Không đưa `System.out.println` hoặc cấp phát per-item vào vùng `@Benchmark`.

### Một benchmark self-contained

Trong project JMH có package `bench`, đặt file **`src/main/java/bench/PatternDispatchBenchmark.java`**:

~~~java
package bench;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 7, time = 1)
@Fork(3)
@State(Scope.Thread)
public class PatternDispatchBenchmark {
    sealed interface Op permits V, A, M {
        int eval();
    }

    record V(int n) implements Op {
        public int eval() { return n; }
    }

    record A(int x, int y) implements Op {
        public int eval() { return x + y; }
    }

    record M(int x, int y) implements Op {
        public int eval() {
            return x == 0 || y == 0 ? 0 : x * y;
        }
    }

    @Param({"mono", "bi", "mixed"})
    public String distribution;

    private Op[] inputs;

    @Setup(Level.Trial)
    public void prepare() {
        inputs = new Op[1024];

        for (int i = 0; i < inputs.length; i++) {
            inputs[i] = switch (distribution) {
                case "mono" -> new V(i);

                case "bi" -> (i & 1) == 0
                        ? new V(i) : new A(i, 1);

                case "mixed" -> switch (i & 3) {
                    case 0 -> new V(i);
                    case 1 -> new A(i, 1);
                    case 2 -> new M(i, 0);
                    default -> new M(i, 3);
                };

                default -> throw new IllegalArgumentException(
                        "Unknown distribution");
            };
        }
    }

    static int viaPattern(Op op) {
        return switch (op) {
            case V(var n) -> n;
            case A(var x, var y) -> x + y;
            case M(var x, var y) when x == 0 || y == 0 -> 0;
            case M(var x, var y) -> x * y;
        };
    }

    @Benchmark
    public int polymorphic() {
        int sum = 0;
        for (Op op : inputs) {
            sum += op.eval();
        }
        return sum;
    }

    @Benchmark
    public int patternSwitch() {
        int sum = 0;
        for (Op op : inputs) {
            sum += viaPattern(op);
        }
        return sum;
    }
}
~~~

Đoạn trên yêu cầu JMH dependency, annotation processor và build setup; **không** thể biên dịch chỉ bằng lệnh `javac` đối với một file không có JMH trên classpath. Nó là **ví dụ benchmark để chạy trong project JMH**, khác với chương trình Java hoàn chỉnh ở mục 7 đã được kiểm chứng bằng JDK.

Mỗi lần JMH gọi một phương thức `@Benchmark`, code bên trong duyệt **1024 phần tử**. Vì vậy đơn vị `ns/op` mà JMH in ra là **nanosecond cho một lần gọi benchmark method**, không đồng nghĩa nanosecond cho một lần dispatch riêng. Có thể chia sơ bộ cho 1024 để xem chi phí trung bình trên phần tử, nhưng con số này vẫn chứa chi phí vòng lặp, đọc mảng, cộng tổng và tối ưu chung, không phải “pure dispatch latency”.

**Quan trọng:** hai phương thức JMH cùng trả về tổng, nhưng JIT có quyền inline/biến đổi code khác nhau. Đó chính là phần đáng quan sát; không nên cố ép JVM tắt các tối ưu bình thường trừ khi bạn đang nghiên cứu một khía cạnh cụ thể.

## 10. Tạo JMH project bằng Maven và chạy benchmark

Theo hướng dẫn chính thức của OpenJDK, nên dùng **Maven archetype** JMH để có cấu hình build và annotation processor đúng, thay vì chỉ thêm `jmh-core` jar vào một project không có generator.

Ví dụ tạo project với JMH **1.37** (một phiên bản đã phát hành và có trên Maven Central):

~~~bash
mvn archetype:generate -DinteractiveMode=false \
  -DarchetypeGroupId=org.openjdk.jmh \
  -DarchetypeArtifactId=jmh-java-benchmark-archetype \
  -DarchetypeVersion=1.37 \
  -DgroupId=bench \
  -DartifactId=dispatch-bench \
  -Dversion=1.0-SNAPSHOT
~~~

Trên **PowerShell**, hãy viết lệnh thành **một dòng** hoặc dùng ký tự nối dòng PowerShell (backtick); dấu `\` cuối dòng ở trên là kiểu nối dòng cho Bash. Đặt Maven compiler release thành **21** trong `pom.xml` của project nếu cấu hình được tạo chưa dùng Java 21:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Đoạn XML chỉ minh họa các property cần có, không phải `pom.xml` độc lập. Nếu project dùng cấu hình compiler trong plugin riêng, chỉnh phiên bản nguồn tương ứng ở đúng chỗ để tính năng Java 21 được chấp nhận.

Đặt benchmark class vào package `bench` đúng như ví dụ ở mục 9, sau đó:

~~~bash
mvn clean package
java -jar target/benchmarks.jar PatternDispatchBenchmark
~~~

JMH sẽ chạy các phép đo cho mỗi giá trị `distribution` và hai benchmark methods. Thời gian thực thi có thể đáng kể vì cấu hình có warm-up, measurement và 3 forks. Đây là điều có chủ đích nhằm giảm nhiễu; không nên rút hết về một lần đo để kết luận.

Để xuất dữ liệu máy đọc được, có thể dùng:

~~~bash
java -jar target/benchmarks.jar PatternDispatchBenchmark \
  -rf json -rff results.json
~~~

Đối với PowerShell, hãy viết thành một dòng. Các lệnh và đường dẫn trên là cấu hình hướng dẫn; **bài này không đưa ra số liệu JMH giả định**.

## 11. Đọc báo cáo JMH sao cho đúng

Với `@BenchmarkMode(Mode.AverageTime)` và `@OutputTimeUnit(TimeUnit.NANOSECONDS)`, báo cáo thể hiện thời gian trung bình trên **một benchmark invocation**, đơn vị thường là `ns/op`. **Giá trị nhỏ hơn** nghĩa là thời gian mỗi invocation thấp hơn, nếu tất cả điều kiện so sánh tương đương.

Các thông tin phải nhìn cùng nhau:

- **Benchmark name**: `polymorphic` hay `patternSwitch`.
- **Parameter `distribution`**: `mono`, `bi` hoặc `mixed`. Không so sánh lệch phân bố.
- **Score**: thời gian trung bình `ns/op` của lần gọi benchmark method.
- **Error/CI**: sai số ước lượng và độ biến động (tùy chế độ báo cáo); chênh lệch rất nhỏ so với nhiễu chưa đủ làm cơ sở kết luận.
- **Fork/iterations/JDK**: điều kiện thực thi; cùng test nhưng JDK hoặc flags khác có thể có kết quả khác.
- **Nhiều run**: xem tính ổn định, không chỉ chọn một lượt có số đẹp.

Một **ví dụ hoàn toàn giả định** để luyện cách hiểu chênh lệch (không phải kết quả benchmark thực):

~~~text
Ví dụ giả định cho cùng phân bố:
polymorphic     1200 ns/op
patternSwitch   1260 ns/op
Khác nhau       60 ns cho mỗi lần duyệt 1024 phần tử
~~~

Ở đây patternSwitch cao hơn khoảng **5%** trên thước đo tổng mỗi invocation (60/1200). Nhưng chưa được kết luận đa hình nhanh hơn có ý nghĩa thống kê nếu chưa xem sai số, forks, dữ liệu và môi trường đo. Nếu chỉ đổi bộ test sang `mixed` hay nâng JDK, thứ tự có thể thay đổi.

Nếu có thể, đối chiếu benchmark micro với profiler/JFR và latency/throughput end-to-end của use case thật trước khi quyết định thay đổi kiến trúc vì hiệu năng.

## 12. Khi nào pattern switch có lợi về mặt thiết kế?

Pattern matching thường phù hợp khi:

1. **Kiểu dữ liệu khép kín**: sealed interface/record hierarchy nhỏ, được điều khiển bởi chính module của bạn.
2. **Một operation mới cần xử lý nhiều subtype**: thêm một hàm switch có thể gọn hơn việc sửa mọi subtype.
3. **Biến đổi/format/serialization/projection**: logic tự nhiên là “phân loại data theo cấu trúc rồi biến đổi”.
4. **Nested record patterns**: deconstruct dữ liệu có cấu trúc mà không cần cast nhiều cấp.
5. **Exhaustiveness**: muốn compiler nhắc khi thêm subtype mà một operation chưa xử lý đủ.

Ví dụ:

~~~java
sealed interface Payment permits Cash, Card {}
record Cash(int amount) implements Payment {}
record Card(int amount, String last4) implements Payment {}

static String label(Payment payment) {
    return switch (payment) {
        case Cash(var amount) -> "Cash: " + amount;
        case Card(var amount, var last4) -> "Card ****" + last4;
    };
}
~~~

Ví dụ này là một operation **format nhãn** theo subtype. Nó không chứng minh pattern switch nhanh hơn `payment.label()`. Lợi ích rõ ràng hơn nằm ở chỗ **thêm một operation trình bày dữ liệu** mà không phải thay các record dữ liệu.

Nếu dữ liệu xuất phát từ ngoài module và có thể thêm subtype không kiểm soát, sealed hierarchy và switch exhaustive có thể gây hạn chế cần tính toán trước.

## 13. Khi nào polymorphic dispatch có lợi về mặt thiết kế?

Đa hình thường phù hợp khi:

1. **Hành vi là một phần bản chất của đối tượng**: ví dụ chiến lược tính thuế, thuật toán nén, phương thức tính giá.
2. **Mỗi subtype giữ invariant/encapsulation riêng**, không muốn lộ chi tiết thực hiện cho một switch bên ngoài.
3. **Tập subtype mở rộng**, được cung cấp bởi plugin hoặc các module độc lập.
4. **Nhiều nơi gọi cùng một operation**: interface method là hợp đồng rõ ràng để các caller không lặp switch.
5. **Luồng xử lý chủ yếu là gọi hành vi**, không phải biến đổi cấu trúc dữ liệu từ ngoài.

Ví dụ:

~~~java
interface Discount {
    int apply(int price);
}

final class FixedDiscount implements Discount {
    public int apply(int price) {
        return Math.max(0, price - 100);
    }
}

final class PercentDiscount implements Discount {
    public int apply(int price) {
        return price * 90 / 100;
    }
}

static int discountedPrice(Discount discount, int price) {
    return discount.apply(price);
}
~~~

Ở ví dụ này, “cách tính giảm giá” là hợp đồng rõ ràng thuộc từng strategy. Một switch phân loại theo class cụ thể sẽ khiến code nhận biết các implementation và có thể làm giảm tính mở rộng.

Điểm lưu ý: interface method có thể được inline trên hot path; đừng thay bằng pattern matching chỉ vì cho rằng gọi interface luôn chậm.

## 14. Những lỗi benchmark thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đo một vòng lặp `nanoTime` duy nhất | Kết quả chịu JIT warm-up, noise, GC | Dùng JMH warm-up, measurement, forks |
| Benchmark chỉ có một subtype nhưng hệ thống thực tế có nhiều subtype | Kết quả ưu ái monomorphic call site | Đo nhiều `distribution` đại diện workload |
| Một cách thực hiện validation/caching, cách kia không | Đang so sánh công việc khác nhau | Chuẩn hóa ngữ nghĩa, assert output/exception |
| Tạo object trong một benchmark, nhưng ngoài phép đo ở benchmark kia | Đang đo allocation/GC không công bằng | Setup cùng dữ liệu trước benchmark |
| Không sử dụng kết quả tính | JIT có thể loại bỏ công việc | Return kết quả hoặc dùng JMH `Blackhole` |
| In log trong `@Benchmark` | I/O chi phối tổng thời gian | Không log trong vùng timed |
| So `ns/op` như nanosecond cho một phần tử | Mỗi invocation lặp qua 1024 phần tử | Ghi rõ đơn vị, chia có thận trọng và đọc overhead |
| Chỉ nhìn score, bỏ error và sự dao động | Chênh lệch nhỏ có thể là nhiễu | Xem variation, CI, nhiều forks/runs |
| Chỉ đo một JDK rồi khẳng định Java luôn thế | JIT/compiler/JDK có thể đổi | Ghi JDK/version/flags, đo lại trên môi trường đích |
| Thay kiến trúc vì microbenchmark nhỏ | Lợi ích có thể không đáng kể với end-to-end | Profile và đo use case thật |
| Bỏ qua path `null`/exception | Hai implementation có thể lệch hợp đồng | Test đúng hành vi và tiền điều kiện riêng |
| Tưởng sealed exhaustive đảm bảo nhanh | Đây là kiểm tra tính đầy đủ lúc compile | Đánh giá thiết kế và performance riêng |

## 15. Checklist quyết định cho dự án

Khi review một PR đổi `operation.viaMethod()` sang `switch (operation)`, hỏi theo thứ tự:

1. **Cùng ngữ nghĩa không?** Có test nhiều subtype, guard true/false, null, lỗi và biên không?
2. **Dữ liệu và extension model thế nào?** Sealed/record kiểu dữ liệu đóng hay interface mở cho plugin?
3. **Logic thuộc về ai?** Hành vi đóng gói trong subtype hay phép biến đổi bên ngoài subtype?
4. **Đây có thật là bottleneck?** Profile CPU/allocations trước khi tối ưu theo trực giác.
5. **Benchmark có công bằng?** Cùng work, input distribution, không I/O/allocations lệch, đủ warm-up/forks.
6. **Chênh lệch ổn định và đáng kể không?** Nhìn score, error, nhiều lần đo và cùng môi trường.
7. **Đổi thiết kế có đáng không?** Readability, maintainability, exhaustiveness và extension thường quan trọng hơn micro-optimization khi thời gian dispatch không chi phối.

**Kết luận thực hành:** nếu không có bằng chứng hiệu năng rõ, ưu tiên mô hình có trách nhiệm hành vi rõ ràng và dễ bảo trì. Chỉ đổi cách dispatch vì tốc độ khi benchmark đại diện và kết quả có ý nghĩa đối với use case thực tế.

## 16. Bài tập luyện tập

**Bài 1 — Thiết kế.** Cho `sealed interface Event permits Created, Deleted {}` và ba operation: format ra text, lưu audit, áp dụng quy tắc nghiệp vụ. Operation nào phù hợp để viết pattern switch bên ngoài, operation nào nên nằm trong service hoặc các subtype? Giải thích dựa trên encapsulation và extension.

**Bài 2 — Phân bố.** Một method gọi `work.eval()` 1 triệu lần, 99,9% receiver là `Value`. Một benchmark khác sử dụng `Value`, `Add`, `Multiply` theo tỷ lệ gần đều. Tại sao có thể cho kết quả tương đối khác nhau?

**Bài 3 — Benchmark.** Phân tích lỗi của vòng lặp `nanoTime` gọi `new Add(1,2).viaMethod()` mỗi lần trong khi pattern benchmark dùng một mảng `Add` đã khởi tạo. Hai đoạn có đo cùng công việc không?

**Bài 4 — Đơn vị.** JMH chạy một benchmark method xử lý mảng 1024 phần tử, hiển thị `2000 ns/op`. Có được nói mỗi dispatch tốn 2000 ns không? Nếu chỉ chia 1024 ra ~1,95 ns/item thì còn những chi phí nào bị trộn vào?

**Bài 5 — Correctness.** Trong ví dụ mục 7, nếu bỏ `when left == 0 || right == 0` nhưng vẫn dùng `left * right`, các kết quả `int` còn giống nhau không? Nếu giống, tại sao việc đổi biểu thức guard vẫn có thể ảnh hưởng microbenchmark và tại sao code phải thể hiện **cùng đường logic** trước khi đo?

**Gợi ý:**

- Bài 1: format ra text thường thuận tiện với pattern switch trên hierarchy đóng; nghiệp vụ và audit còn phụ thuộc context, transaction/ủy quyền nên cân nhắc service; không có một đáp án duy nhất cho mọi domain.
- Bài 2: JIT tối ưu call site theo type profile, và pattern switch có đường phân loại khác khi phân bố thay đổi.
- Bài 3: không, một benchmark đo cả cấp phát object/GC còn bên kia không; cần khởi tạo ngoài vùng đo hoặc cùng đo allocation.
- Bài 4: không, `ns/op` là cho **cả invocation**. Chia 1024 chỉ xấp xỉ chi phí trung bình gồm vòng lặp, đọc mảng, tính toán, dispatch và tối ưu chung.
- Bài 5: với phép nhân `int` thuần, nhân với zero vẫn ra zero nên kết quả có thể giống. Nhưng lượng điều kiện/đường đi và khả năng JIT tối ưu khác; benchmark phải quyết định rõ đang so sánh cùng thuật toán hay đang so sánh hai **cách viết nghiệp vụ khác nhau**.

## 17. Tóm tắt cuối bài

- **Polymorphic dispatch** đưa hành vi vào subtype và gọi `obj.method()`; HotSpot có thể devirtualize/inline tùy type profile.
- **Pattern dispatch** chọn nhánh bằng `switch`/record pattern/`when`; thuận tiện khi dữ liệu đóng và cần nhiều phép biến đổi bên ngoài.
- **Không** quy kết cách nào nhanh hơn chỉ dựa trên cú pháp, số subtype hoặc số case. Chi phí JIT, deconstruction, guard, inlining và workload có thể quyết định kết quả.
- Hãy **test correctness** trước, **benchmark JMH** với cùng dữ liệu và phép tính sau, rồi xác nhận ảnh hưởng bằng profile/end-to-end measurements.
- Nếu tốc độ không phải bottleneck, chọn thiết kế giúp bảo vệ invariant, giảm coupling và dễ mở rộng theo yêu cầu của dự án.

### Tài liệu tham khảo

- [OpenJDK — JMH project](https://openjdk.org/projects/code-tools/jmh/): cách tạo Maven benchmark, lý do dùng archetype và lưu ý pitfalls.
- [Oracle — Avoiding Benchmarking Pitfalls on the JVM](https://www.oracle.com/technical-resources/articles/java/architect-benchmarking.html): JIT, dead-code elimination, warm-up, JMH.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): type patterns, record patterns trong switch, guards và exhaustiveness (Java 21).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): deconstruction và nested record patterns.
- [Oracle Java 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): record patterns/switch pattern matching là tính năng ổn định.
- [OpenJDK HotSpot — C2 call optimization source](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/opto/doCall.cpp): code tối ưu/inline lời gọi theo receiver profile (chi tiết implementation không phải cam kết hiệu năng).
