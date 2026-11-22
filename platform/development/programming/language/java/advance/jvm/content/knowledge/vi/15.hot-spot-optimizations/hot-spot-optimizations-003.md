# Gấp hằng, loại mã không cần thiết và tác động đến phép đo trong HotSpot JVM

## Mục tiêu

Khi lập trình Java, hai phiên bản mã có thể trông khác nhau nhưng sau tối ưu lại dẫn tới **cùng một chuỗi lệnh máy**. Ngược lại, một phép tính xuất hiện trong source và thậm chí trong bytecode có thể **không còn tồn tại** trong machine code sau JIT. Đây là lý do một microbenchmark ngây thơ có thể báo rằng một phép tính tốn gần như **0 ns**, hoặc thuật toán A nhanh hơn thuật toán B hàng trăm lần chỉ vì compiler nhận thấy kết quả của A không cần thiết.

Hai cơ chế trung tâm của bài học:

- **Constant folding (gấp hằng):** thay biểu thức mà kết quả đã biết bằng một giá trị cố định, khi phép biến đổi bảo toàn ngữ nghĩa Java. Ví dụ `6 * 7` có thể thành `42` ngay khi biên dịch source, hoặc một biểu thức với đầu vào thực tế được JIT biết có thể được tính trước trong optimized code.
- **Dead-code elimination (DCE, loại mã chết):** bỏ những phép tính, lệnh gán, nhánh, thậm chí object allocations mà không ảnh hưởng đến **hành vi chương trình được phép quan sát**. Nếu kết quả không được dùng và không có side effects/exception/ordering cần bảo toàn, JIT có thể loại bỏ phần công việc bạn tưởng đang đo.

Sau bài này bạn có thể:

1. Phân biệt **javac compile-time constant expressions** theo JLS với **runtime JIT constant propagation/folding** trong HotSpot.
2. Hiểu **dead assignments**, **unreachable branches**, **unused results**, **redundant checks** và sự tương tác với inlining, common-subexpression elimination, loop invariant code motion và escape analysis.
3. Nhận biết giới hạn do **exceptions, volatile accesses, synchronization, I/O, floating-point behavior, integer overflow, aliasing và Java Memory Model**.
4. Dùng `javap -c -p` để phân biệt mã bị `javac` xử lý từ trước và mã còn bytecode nhưng có thể được JIT tối ưu sau.
5. Tạo ví dụ Java 17+ chạy được có stdout xác định và mô tả điều gì **không thể** kết luận chỉ từ output.
6. Thiết kế benchmark với **JMH**, sử dụng `@State`, `@Param`, giá trị trả về hoặc `Blackhole` để hạn chế DCE/constant folding ngoài ý muốn.
7. Tránh những cách “chống tối ưu” làm thay đổi phép đo, chẳng hạn thêm `System.out.println` vào timed loop hoặc dùng volatile một cách máy móc.
8. Diễn giải kết quả benchmark theo **workload thật**, warmup, JIT tiering, dead-code elimination, allocation rate và các công cụ chẩn đoán.

## 1. Các tầng biến đổi từ Java source đến CPU

~~~text
Java source
    |
    | javac
    v
.class bytecode
    |
    | HotSpot interpreter / profiling
    v
JIT intermediate representation (C1/C2 theo build/chế độ)
    |
    +-- inlining
    +-- constant folding / constant propagation
    +-- branch simplification
    +-- dead-code elimination
    +-- loop optimizations
    +-- escape analysis / scalar replacement
    +-- machine-specific lowering/scheduling
    |
    v
Optimized machine code
    |
    v
Actual program behavior (phải phù hợp Java semantics)
~~~

Các giai đoạn không bắt buộc diễn ra một lần và theo đúng thứ tự giản lược ở trên. HotSpot có nhiều compiler passes, phase ordering và recompilation; một tối ưu có thể tạo điều kiện cho tối ưu khác. C1/C2 và các representation nội bộ không thuộc Java SE public API.

### Hai loại gấp hằng dễ nhầm

**Gấp hằng trong `javac`:**

~~~java
static final int ANSWER = 6 * 7;
static int getAnswer() {
    return ANSWER;
}
~~~

Đây là đoạn class-member minh họa, phải đặt trong một class. `ANSWER` là một **constant variable**: `final`, kiểu primitive, initialized bằng constant expression. `javac` có thể đặt giá trị 42 ngay trong code của method sử dụng nó. Thậm chí `getAnswer()` có thể có bytecode dạng tải hằng và `ireturn` mà không cần `getstatic ANSWER`.

**Gấp hằng ở HotSpot JIT:**

~~~java
static int multiply(int x) {
    return x * 7;
}

static int callWithKnownValue() {
    return multiply(6);
}
~~~

Đây là các method minh họa. Bytecode của caller vẫn có thể chứa `invokestatic multiply` và bytecode callee có phép nhân. Nhưng sau khi JIT inline `multiply(6)`, compiler có thể biết argument là 6, gấp phép nhân thành **42**. Java source không cần đánh dấu `x` là `final` để một JIT optimization nhận ra constant ở một call site cụ thể.

**Điểm mấu chốt:** xem `javap` thấy phép nhân không đồng nghĩa CPU bắt buộc chạy phép nhân; ngược lại `javap` chỉ là class-file bytecode, không phải machine code cuối cùng.

## 2. Constant expression theo JLS khác với mọi biểu thức mà JIT có thể tối ưu

JLS Java SE 17 §15.29 định nghĩa một tập biểu thức hằng của **primitive** hoặc **String**, sử dụng literals, phép toán được phép, casts và references đến constant variables. Điều này quyết định nhiều quy tắc ngôn ngữ, ví dụ compile-time constant variables, switch case labels, narrowing constant conversions và class initialization.

Ví dụ:

~~~java
static final int A = 40 + 2;
static final String LABEL = "J" + "VM";
static final int B = Integer.parseInt("42");
static final Integer C = 42;
static int D = 21 * 2;
~~~

Đây là **class fields minh họa**, không độc lập:
- `A` là constant variable primitive.
- `LABEL` là constant variable String.
- `B` là `final int` nhưng **không phải constant variable theo JLS**, vì initializer gọi method `Integer.parseInt` chứ không phải constant expression.
- `C` không phải constant variable theo JLS: kiểu `Integer` không phải primitive hay String.
- `D` không phải constant variable vì thiếu `final`, mặc dù initializer có dạng tính được tại compile time.
- **JIT vẫn có thể suy luận một số giá trị** từ B, C hoặc D nếu các điều kiện runtime đủ chặt, nhưng đó là **suy luận/tối ưu runtime**, không biến các fields này thành constant variables theo ngữ nghĩa JLS.

### Java constant variables có tác động tới binary compatibility

Nếu thư viện công khai:

~~~java
public static final int TIMEOUT = 30;
~~~

và một client được biên dịch dựa trên constant variable đó, mã client có thể chứa trực tiếp hằng **30** thay vì field read runtime. Sau này đổi thư viện sang `TIMEOUT=60` nhưng **không biên dịch lại client**, client có thể vẫn sử dụng 30. Đây là **constant inlining qua compile boundary**, không phải lỗi của JIT.

Nếu giá trị cần đổi mà clients luôn đọc lúc runtime, một API method/getter hoặc một field không thuộc constant-variable category có thể phù hợp hơn. Cũng cần xét initialization, access semantics và binary compatibility của API. Đừng dùng `static final` primitive constant làm “dynamic configuration”.

### Compile-time unreachable code khác JIT DCE

Một đoạn source có thể bị Java compiler từ chối do quy tắc **unreachable statements** theo JLS. Đó là **lỗi compile-time**. Trong khi đó, HotSpot DCE chủ yếu loại các nodes/instructions khỏi machine code sau khi source và bytecode đã hợp lệ; Java source vẫn biên dịch bình thường.

Không suy ra `javac` sẽ làm mọi tối ưu mà JIT làm, và không cho rằng JVM có quyền thay đổi ngữ nghĩa observable vì performance.

## 3. Ví dụ đầy đủ Java 17+: phân biệt folding và dead expression

Tạo file **`FoldingAndDceDemo.java`**:

~~~java
public class FoldingAndDceDemo {
    private static final int ANSWER = 6 * 7;

    private static final int RUNTIME_VALUE =
            Integer.parseInt("42");

    private static volatile int observed;

    static int compileTimeConstant() {
        return ANSWER;
    }

    static int runtimeField() {
        return RUNTIME_VALUE;
    }

    static int unusedArithmetic(int x) {
        int temporary = (x + 2) * (x + 2);
        return x + 1;
    }

    static int mayThrow(int divisor) {
        int unused = 100 / divisor;
        return 7;
    }

    static int visibleWrite(int x) {
        observed = x * 2;
        return 1;
    }

    public static void main(String[] args) {
        System.out.println("constant=" + compileTimeConstant());
        System.out.println("runtime=" + runtimeField());
        System.out.println("unused=" + unusedArithmetic(7));

        try {
            mayThrow(0);
            System.out.println("unexpected");
        } catch (ArithmeticException ex) {
            System.out.println("division=ArithmeticException");
        }

        visibleWrite(5);
        System.out.println("volatile=" + observed);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 FoldingAndDceDemo.java
java FoldingAndDceDemo
~~~

**Stdout chính xác:**

~~~text
constant=42
runtime=42
unused=8
division=ArithmeticException
volatile=10
~~~

Giải thích:

1. `ANSWER` thuộc compile-time constant-variable category. `javac` có thể đặt `42` vào bytecode của `compileTimeConstant`.
2. `RUNTIME_VALUE` được khởi tạo bằng method call, do đó không phải compile-time constant variable. `runtimeField` thông thường đọc field với `getstatic` trong bytecode, dù HotSpot runtime có thể tối ưu thêm khi phù hợp.
3. `unusedArithmetic(7)` khai báo một local `temporary` nhưng **không dùng nó** để tạo return value. HotSpot có thể loại toàn bộ việc tính `(x+2)*(x+2)` vì phép toán int ở đây không tạo side effects/exception observable.
4. `mayThrow(0)` có phép chia nguyên cho 0. Dù biến `unused` không được đọc, biểu thức vẫn **phải ném ArithmeticException**. JIT không được xóa một operation nếu việc xóa làm biến mất exception observable trong cùng ngữ cảnh.
5. `visibleWrite(5)` ghi vào một **volatile field** rồi main đọc lại, nên kết quả 10 phải được bảo toàn. Không được suy ra việc gán field volatile đã biến thành “dead store” vô hại.

### So sánh bytecode

~~~bash
javap -c -p FoldingAndDceDemo
~~~

Nhìn vào `compileTimeConstant`, thường gặp instruction đẩy trực tiếp 42 rồi `ireturn`. Trong `runtimeField`, thường gặp `getstatic RUNTIME_VALUE`. Trong `unusedArithmetic`, bytecode của `javac` có thể vẫn chứa phép nhân và `istore` local tạm. Trong `mayThrow`, thường gặp `idiv` — phép chia có thể ném exception.

**Không coi vị trí bytecode/constant-pool indexes là hằng số.** Compiler build khác nhau có thể cho output khác. `javap` **không đủ** để chứng minh C2 đã xóa phép tính khỏi machine code; nó chỉ cho thấy bước sau `javac`, trước tối ưu JIT.

## 4. Dead-code elimination: “không dùng kết quả” nghĩa gì?

Một phép tính có thể bị xóa khi **giá trị tạo ra không góp phần vào behavior observable**, và việc tính nó không mang side effects/exception/ordering nào buộc phải giữ.

~~~java
static void example(int x) {
    int a = x * 31;
    int b = a + 7;
    // Không ai dùng a hay b.
}
~~~

Đây là **method minh họa**. Một tối ưu phù hợp có thể loại các assignments và arithmetic instructions. Nếu benchmark gọi `example(123)` nhiều lần rồi đo thời gian, rất có thể phép “toán học” mong muốn đã không còn tồn tại ở mức machine code.

### Side effects và control-flow phải được bảo toàn

Các hoạt động thường cần xét:
- Ghi/đọc `volatile` theo Java Memory Model.
- Khóa monitor bằng `synchronized` và synchronization order.
- Thao tác I/O có tác động ra bên ngoài, ví dụ in console hoặc ghi file.
- Ghi bộ nhớ có thể được truy cập từ đường code khác hoặc threads khác theo semantics.
- Exceptions có thể quan sát, như `ArithmeticException`, `NullPointerException`, `ArrayIndexOutOfBoundsException`, một số errors tại những điểm phù hợp.
- Native calls hoặc JNI code có side effects.
- Object identity, locking, references thoát khỏi method, finalization/reference-processing constraints khi thích hợp.

**Không phải** tất cả những operation này đều buộc phải tồn tại nguyên vẹn từng machine instruction. JIT chỉ cần giữ **Java-level observable behavior**, có thể kết hợp/bỏ thao tác dư thừa nếu chứng minh hợp lệ.

### DCE khác compile-time dead branch pruning

~~~java
static int choose(int x) {
    if (x > 0) {
        return 1;
    }
    return 2;
}
~~~

Đây là method hợp lệ. Nếu JIT thấy caller luôn truyền x=5 và inline, nó có thể kết luận `x>0` luôn true tại **call site đã được specialized** và bỏ nhánh còn lại. Nhưng ở một caller tổng quát truyền x âm, compiler không được biến toàn method thành return 1 trừ khi guard/deoptimization bảo đảm semantics đúng.

**Constant propagation có thể mở đường cho DCE:** khi điều kiện được chứng minh true, nhánh false thành dead; từ đó các phép tính chỉ thuộc nhánh false cũng được loại.

## 5. Constant folding là phép thay tương đương, không phải “giản lược bất chấp ngữ nghĩa”

Ví dụ với số nguyên:

~~~java
static int zeroProduct(int x) {
    return x * 0 + 9;
}
~~~

Với `int`, phép nhân 0 luôn cho 0 theo quy tắc Java, kể cả khi x âm hoặc phép nhân khác có thể overflow. Vì vậy kết quả method này luôn bằng 9; compiler có thể gấp thành constant nếu không có side effect trong phần đọc x.

Nhưng với `double`:

~~~java
static double floatingZero(double x) {
    return x * 0.0d;
}
~~~

**Không được** biến thành literal `0.0d` với mọi x:
- `Double.POSITIVE_INFINITY * 0.0` là **NaN**.
- `-3.0d * +0.0d` là **-0.0d**.
- NaN propagation và signed zero phải được tôn trọng.
- Floating-point strict semantics của Java 17+ không cho phép những biến đổi làm mất kết quả observable này chỉ vì “nhân 0 thì bằng 0”.

### Ví dụ chạy được: số nguyên và dấu zero IEEE 754

Tạo file **`SemanticBoundaryDemo.java`**:

~~~java
public class SemanticBoundaryDemo {
    static int zeroInt(int x) {
        return x * 0 + 9;
    }

    static double zeroDouble(double x) {
        return x * 0.0d;
    }

    public static void main(String[] args) {
        System.out.println("int=" + zeroInt(Integer.MIN_VALUE));

        double infinityResult =
                zeroDouble(Double.POSITIVE_INFINITY);
        System.out.println("infinityNaN=" +
                Double.isNaN(infinityResult));

        double negativeZero = zeroDouble(-3.0d);
        System.out.println("negativeZeroBits=" +
                Long.toHexString(
                        Double.doubleToRawLongBits(negativeZero)));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 SemanticBoundaryDemo.java
java SemanticBoundaryDemo
~~~

**Stdout chính xác:**

~~~text
int=9
infinityNaN=true
negativeZeroBits=8000000000000000
~~~

Giá trị hex `8000000000000000` là bit pattern của **-0.0d** trong IEEE 754 double. Đây là lý do không dùng quy tắc đại số của số nguyên một cách máy móc cho phép toán floating point.

### Integer overflow cũng là một ranh giới

Java `int` arithmetic overflow theo quy tắc two's-complement wraparound đối với các phép toán thông thường; không được giả định kiểu số nguyên vô hạn. Phép biến đổi `(a+b)-b → a` có thể vẫn đúng theo modulo 2^32 cho int nhưng những đổi chỗ hay biến đổi với phép chia, shifts, compare, casts có thể khác. Compiler phải chứng minh đúng dưới Java rules, không dựa vào đại số thực rồi bỏ qua overflow.

## 6. Constant propagation và inlining làm benchmark “biến mất” thế nào?

Một phép tính có đầu vào không hằng tại source method vẫn có thể được JIT thấy hằng **sau khi inline**.

~~~java
static int expensive(int x) {
    int y = x;
    for (int i = 0; i < 10; i++) {
        y = y * 31 + i;
    }
    return y;
}

static int benchmarkLike() {
    return expensive(7);
}
~~~

Đây là **hai method minh họa**. Tại `benchmarkLike`, JIT có thể inline `expensive(7)`, biết trước x và loop bounds rồi fold/unroll/constant-propagate đủ để thu một kết quả cố định. Một phép đo rất nhanh lúc này phản ánh optimized **constant call site**, không phản ánh hiệu năng trên inputs production thay đổi.

Nếu đo `expensive(7)` một cách cố ý để đánh giá **chính caller có input hằng**, tối ưu là hợp lý. Nếu mục tiêu là đo phép tính với inputs không biết trước, benchmark sai về mô hình workload.

### Cách bảo vệ fairness khi input phải biến đổi

- Cung cấp input qua **`@State` fields** trong JMH để không chỉ truyền literal cố định.
- Dùng `@Param` để chạy nhiều tình huống đại diện.
- Nếu cần input distribution rộng hoặc thay đổi theo operation, quản lý dataset và indexing có kiểm soát.
- Không dùng `final int x=7` trong benchmark body nếu mục tiêu là đo dynamic-input path.
- **Không lạm dụng Random.nextInt() trong vùng đo** nếu mục tiêu chỉ là phép toán; chi phí RNG có thể áp đảo phép tính cần đo.
- Không cố “ẩn” dữ liệu bằng reflection/volatile/synchronized nếu production không chịu chi phí tương tự.

**Bài học:** JIT có nhiệm vụ tối ưu code thực thi, không phục vụ kỳ vọng rằng microbenchmark phải chạy nguyên mọi instruction trong source.

## 7. Loop-invariant code motion và loop elimination

Ngoài constant folding/DCE, JIT có thể **hoist** phép tính không đổi qua mỗi iteration ra ngoài vòng lặp (loop-invariant code motion) hoặc biến đổi loop khi semantics cho phép.

Ví dụ:

~~~java
static long sum(int n, int factor) {
    long total = 0L;
    for (int i = 0; i < n; i++) {
        int repeated = factor * factor;
        total += repeated;
    }
    return total;
}
~~~

Đây là method minh họa. `factor*factor` không phụ thuộc `i`; nếu không có exception/side effect cần giữ tại mỗi iteration, compiler có thể tính một lần rồi dùng trong loop. Đây là tối ưu **hợp lệ**, nhưng nếu bạn muốn đo “chi phí của phép nhân một triệu lần”, mã này không nhất thiết đo thứ bạn tưởng.

### Những trường hợp loop có thể rút gọn mạnh

~~~java
static long sumNumbers(int n) {
    long s = 0L;
    for (int i = 0; i < n; i++) {
        s += 1L;
    }
    return s;
}
~~~

Về mặt toán học, khi n không âm và không có side effects liên quan, kết quả bằng n. Compiler **có thể** nhận ra các mô hình đơn giản và thay đổi loop. Không hứa HotSpot **luôn** biến mọi loop thành công thức; các phép tối ưu phụ thuộc JDK, compiler, profile, loại dữ liệu, loop shape và constraints.

Đừng chỉnh benchmark đến mức vòng lặp chỉ kiểm tra compiler có nhận ra một đẳng thức hay không, trừ khi đó chính là mục tiêu nghiên cứu. Workload thật có data dependencies, branches, arrays và cache behavior cần được tái hiện.

### Loop body không có tác dụng quan sát

~~~java
static void pointless(int n) {
    for (int i = 0; i < n; i++) {
        int tmp = i * 17;
    }
}
~~~

Đây là code minh họa. Nếu JIT có thể loại loop mà vẫn giữ các ràng buộc Java có liên quan, code có thể trở nên gần như rỗng. Tuy nhiên không được khẳng định **mọi loop không side effects luôn có thể xóa mà không xét termination/safepoints/runtime constraints**. Những loop không kết thúc, ngoại lệ có thể xảy ra hoặc yêu cầu VM progress/safepoint có thể giới hạn transformation.

## 8. DCE không đồng nghĩa escape analysis, nhưng chúng phối hợp với nhau

Một đoạn code:

~~~java
static int calculate(int a, int b) {
    Pair pair = new Pair(a, b);
    return pair.left + pair.right;
}
~~~

Đây là method minh họa, cần định nghĩa class `Pair` có fields/constructor phù hợp. Với HotSpot, **escape analysis** có thể chứng minh `pair` không escape; **scalar replacement** có thể biểu diễn fields thành các scalar values và loại **allocation vật lý** khi semantics cho phép.

Đây không chỉ là xóa “lệnh `new` vì kết quả không dùng”: các field values **vẫn** đóng góp vào return value. Tối ưu giữ phép tính cần thiết và loại đại diện object trung gian.

| Cơ chế | Ví dụ công việc bị bớt | Vì sao đúng |
| --- | --- | --- |
| Constant folding | `6*7` thành `42` | Kết quả xác định, không mất behavior |
| Constant propagation | Truyền giá trị đã biết qua assignments/calls | Có thể chứng minh giá trị tại điểm dùng |
| Dead-code elimination | Xóa phép tính chỉ tạo result không dùng | Không có side effect/exception observable cần giữ |
| Common-subexpression elimination | Tái sử dụng kết quả biểu thức lặp lại | Dependencies/aliasing/side effects cho phép |
| Loop-invariant code motion | Đưa phép tính bất biến khỏi loop | Không thay đổi ordering/exception/side effects |
| Escape analysis/scalar replacement | Loại allocation của temporary object | Identity/escape không cần biểu diễn vật lý |
| Inlining | Thay method call bằng logic callee | Tạo điều kiện tối ưu qua method boundary |
| Branch pruning | Bỏ nhánh đã biết không thể xảy ra | Có guard/profile hoặc chứng minh từ input |

**Không nên** coi DCE và escape analysis là cùng một tối ưu chỉ vì cả hai có thể làm số allocations do profiler ghi nhận giảm.

### Object identity và synchronization giới hạn tối ưu

Nếu object được đưa ra global state, dùng làm lock, identity hash hoặc được JNI code quan sát, compiler phải bảo toàn behavior. Ngược lại, một object chỉ giữ hai numbers bên trong một method không nhất thiết cần tồn tại vật lý nếu không ai có thể phân biệt.

Trạng thái HotSpot có thể được phục hồi qua **deoptimization** nếu optimized assumptions không còn đúng; JIT phải bảo đảm tính đúng đắn cả khi cần quay về interpreter.

## 9. Những phép tính không được xóa vì ngoại lệ quan sát được

Xét:

~~~java
static int division(int denominator) {
    int ignored = 100 / denominator;
    return 7;
}
~~~

Với `denominator=0`, method **phải ném ArithmeticException**, không phải return 7. Kể cả `ignored` không bao giờ đọc, phép chia vẫn có observable exceptional behavior.

Các trường hợp tương tự:

~~~java
static int arrayRead(int[] array, int i) {
    int unused = array[i];
    return 7;
}

static int dereference(String text) {
    int unused = text.length();
    return 7;
}
~~~

Đây là method snippets. Nếu `array` null hoặc index ngoài biên, array read có thể ném `NullPointerException`/`ArrayIndexOutOfBoundsException`. Nếu `text` null, `text.length()` ném NPE. Compiler **không thể xóa bừa** những checks nếu người gọi có thể quan sát exception.

Nhưng ở một call site mà JIT chứng minh `array != null` và index hợp lệ, hoặc `text != null`, các checks có thể được loại bỏ/hoist theo conditions đó. **Tính đúng đắn được xét theo toàn bộ đường thực thi và các assumptions được bảo vệ**, không theo một statement tách rời.

### Thứ tự ngoại lệ cũng quan trọng

Java quy định evaluation order cho expressions và method calls. Đổi thứ tự hai phép tính có thể thay exception nào xảy ra trước hoặc thay side effects. JIT chỉ được reorder khi hành vi **được phép quan sát** vẫn phù hợp Java semantics. Điều này giải thích vì sao một phép toán nhìn có vẻ không được dùng vẫn có thể không thể xóa.

## 10. Volatile: “chống DCE” nhưng có thể đổi bài toán đang đo

Một mẹo thường thấy:

~~~java
static volatile long sink;

static void measuredOperation(int x) {
    long result = x * 31L;
    sink = result;
}
~~~

`volatile` field write mang semantics ordering/visibility; việc ghi làm kết quả “observable” hơn đối với optimizer. Nhưng **mỗi iteration giờ có volatile memory operation**, không còn đo thuần phép nhân nữa. Trên multi-core hardware và dưới contention, overhead của store/visibility/order có thể chi phối.

Do đó:
- Với **JMH** có thể ưu tiên `return result` cho benchmark method hoặc dùng **`Blackhole.consume(result)`**.
- Không thêm một `System.out.println` sau mỗi phép toán: console I/O chậm và rất biến thiên.
- Nếu production thật sự có volatile write, nó **thuộc workload** và phải đo.
- Một sink dùng chung còn có thể gây contention/false sharing, ảnh hưởng phép so sánh.
- Volatile field không phải “tắt toàn bộ constant folding”; compiler vẫn có thể fold phép toán tạo kết quả trước khi volatile write nếu đầu vào đã biết.

**Không có cách nào yêu cầu JIT làm công việc thừa chỉ để benchmark đẹp mà vẫn gọi đó là đo mã production**. Benchmark nên được thiết kế sao cho tính toán có ý nghĩa và input/output phản ánh workload.

## 11. JMH: kiểm soát DCE và constant folding

**JMH (Java Microbenchmark Harness)** là công cụ thuộc OpenJDK để viết microbenchmarks trên JVM. Nó hỗ trợ warmup, measurement iterations, forks, states, parameters, kết quả đo và cơ chế giảm một số bẫy JVM/compiler.

### Benchmark sai: kết quả bị bỏ đi

~~~java
@Benchmark
public void discarded() {
    expensive(42);
}
~~~

Đây là **fragment JMH minh họa**, cần imports/project JMH và method `expensive`. Nếu callee không có observable side effects và result bị bỏ qua, compiler có thể xóa phần lớn code sau inlining. Thời gian đo có thể gần như chỉ còn chi phí gọi/framework hay phép toán đã được tối ưu rỗng.

### Tốt hơn: return hoặc Blackhole

~~~java
@Benchmark
public int returned() {
    return expensive(value);
}

@Benchmark
public void consumed(Blackhole bh) {
    bh.consume(expensive(value));
}
~~~

Đây là **fragment JMH minh họa**; `value` cần thuộc JMH state. JMH tiêu thụ returned result hoặc `Blackhole.consume` để hạn chế DCE ở biên benchmark. Nhưng:

- **Return result không tự ngăn constant folding** nếu input vẫn là hằng.
- Blackhole không bảo đảm mọi instruction ở source còn tồn tại; JIT vẫn tối ưu hợp lệ những phần trung gian.
- Blackhole có overhead, vì vậy dùng theo đúng JMH contract.
- Không tự đặt tên một method `blackhole()` rồi giả định có hiệu lực như công cụ JMH.
- Nếu benchmark tạo một object nhưng chỉ consume một scalar field, escape analysis vẫn có thể loại object allocation vật lý; đó là tối ưu hợp lệ cho **đúng workload được đo**.

### @State và @Param giải quyết bẫy input hằng

Để không truyền literal cố định tại call site, tạo state với fields và nhận parameter từ JMH harness. Dùng các parameter values đại diện cho production, không luôn chọn cùng 7 nếu hệ thống chạy nhiều phân phối.

## 12. Ví dụ JMH đầy đủ (Java 17+) để nghiên cứu folding

Đặt file **`FoldingBench.java`** trong **một dự án JMH đã cấu hình thư viện JMH** ở package `org.example`:

~~~java
package org.example;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.infra.Blackhole;

import java.util.concurrent.TimeUnit;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
public class FoldingBench {
    @Param({"11", "17", "103"})
    public int input;

    static int transform(int x) {
        int result = x;
        for (int i = 0; i < 8; i++) {
            result = result * 31 + i;
        }
        return result;
    }

    @Benchmark
    public int stateInput() {
        return transform(input);
    }

    @Benchmark
    public int constantInput() {
        return transform(11);
    }

    @Benchmark
    public void blackholeInput(Blackhole bh) {
        bh.consume(transform(input));
    }
}
~~~

**Điều kiện biên dịch:** class này có dependencies `jmh-core` và JMH annotation processor từ **JMH Maven archetype** hoặc một dự án JMH được cấu hình tương đương. Không thể biên dịch độc lập bằng `javac FoldingBench.java` với Java SE thuần vì annotations/JMH runtime là thư viện ngoài JDK.

Một workflow thông dụng sau khi tạo project JMH bằng Maven archetype chính thức:
1. Dùng JDK 17+ và Maven tương thích.
2. Thêm file theo đúng package vào `src/main/java/org/example/FoldingBench.java`.
3. Tạo artifact bằng `mvn clean verify` từ thư mục dự án JMH đã có `pom.xml`.
4. Chạy JMH runner từ JAR của project:

~~~bash
mvn clean verify
java -jar target/benchmarks.jar FoldingBench -wi 5 -i 5 -f 2
~~~

Các options `-wi 5`, `-i 5`, `-f 2` là **ví dụ warmup iterations, measurement iterations, forks**. Nên xem `java -jar target/benchmarks.jar -h` để biết chi tiết theo JMH version. **Không đưa bảng kết quả đo “chính xác”** vì ns/op phụ thuộc CPU, JDK, optimization, load và noise.

### Cách đọc ba benchmark

- `stateInput`: input đọc từ non-final JMH state field. Điều đó làm việc chứng minh một hằng duy nhất khó hơn ở những điểm tối ưu thông thường và phản ánh nhiều @Param scenarios.
- `constantInput`: gọi `transform(11)` với literal. Đây là phép đo cho tình huống **input cố định**; JIT có thể inline/fold mạnh.
- `blackholeInput`: cùng dynamic-input path nhưng tiêu thụ kết quả bằng Blackhole. Đo overhead và so sánh với `stateInput` giúp hiểu cách JMH giữ result observable; không mặc định hai đường có nanoseconds bằng nhau.

**Một điều tinh tế:** `@Param` gán giá trị trước benchmark run, nhưng mỗi fork/iteration có thể thấy một giá trị ổn định; JIT vẫn có thể suy luận thêm nếu state và code shape cho phép. @State không là cam kết “không tối ưu gì”, mà là thiết kế hạn chế **benchmark vô tình chuyển thành một phép tính hằng**. Để đo inputs thay đổi từng operation, có thể dùng một array dataset và iterator/index state thích hợp.

### Tại sao không dùng một vòng lặp 100 triệu lần trong @Benchmark?

Nếu bạn đặt ngay một vòng for cố định và đo average time của toàn loop, JIT có thể unroll/hoist/fold mạnh, làm công việc bên trong không còn như kỳ vọng. Hơn nữa một JMH invocation có độ dài không đồng nhất với operation thực. Nếu cần đo một batch, xem JMH mechanisms như `@OperationsPerInvocation` hoặc batch size theo semantics phù hợp và document rõ measurement unit.

## 13. Bẫy benchmark: nguồn input đã biết và dead output

Bốn trường hợp hay gặp:

| Benchmark body | Rủi ro | Điều chỉnh |
| --- | --- | --- |
| `void bench(){ expensive(10); }` | Result bỏ đi, DCE có thể xóa | Trả result hoặc Blackhole |
| `int bench(){ return expensive(10); }` | Result được dùng nhưng input hằng, folding | Dùng JMH @State/@Param nếu cần dynamic input |
| `int bench(){ return expensive(state.value); }` | Hợp lý hơn, nhưng profile có thể vẫn chuyên biệt | Đảm bảo dataset/parameter distribution phản ánh production |
| `void bench(){ sink = expensive(value); }` với volatile sink | Volatile store làm workload khác | Tránh nếu chỉ muốn đo phép tính |
| `void bench(){ System.out.println(expensive(value)); }` | I/O áp đảo CPU, side effects ngoài mục tiêu | Không in trong timed section |
| `int bench(){ return cachedValue; }` | Đo field load/cache hit thay vì thuật toán | Tách setup/caching và định nghĩa mục tiêu |
| `Object bench(){ return new Tiny(); }` | Allocation có thể được optimize khác khi kết quả escape | Benchmark allocation semantics vs object construction/capture rõ ràng |

**Với một service thực tế**, việc result không được dùng đôi khi chính là bug benchmark; nhưng trong production logic, nếu kết quả **thật sự không cần**, JIT loại phép tính là một thành công tối ưu, không phải lỗi. Cần đo việc hệ thống **thực sự cần làm**.

## 14. JMH sample chính thức: JMHSample_08 và JMHSample_10

OpenJDK JMH có hai ví dụ tham khảo rất phù hợp:
- **`JMHSample_08_DeadCode`** minh họa một benchmark bỏ result bị tối ưu đi và cách trả về result/consume để hạn chế DCE.
- **`JMHSample_10_ConstantFold`** minh họa một phép tính có inputs là hằng bị fold và cách dùng **non-final instance fields trong JMH @State** để giảm bẫy.

Bài học từ cả hai: **chỉ giữ đầu ra chưa đủ nếu đầu vào vẫn là hằng; chỉ dùng input biến động cũng chưa đủ nếu output không được tiêu thụ**. Một benchmark có thể sai ở cả hai đầu.

Cần đọc mục tiêu của JMH API:
- `@Benchmark` đánh dấu method được harness đo.
- `@State(Scope.Thread)` tạo benchmark state theo thread.
- `@Param` cung cấp giá trị cấu hình của state.
- `Blackhole.consume` giúp result không bị optimizer bỏ đi một cách không mong muốn ở ranh giới benchmark.
- Return value của @Benchmark được JMH tiêu thụ thích hợp theo harness behavior.

Tài liệu nguồn:
- https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java
- https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java
- https://github.com/openjdk/jmh/blob/master/jmh-core/src/main/java/org/openjdk/jmh/infra/Blackhole.java

## 15. JMH vẫn có giới hạn: benchmark phải đại diện cho workload

Một microbenchmark chuẩn không đảm bảo kết quả dự đoán được latency trong ứng dụng web/server:
- JIT có thể inline code khác khi dùng từ application thật.
- Production có concurrency, lock contention, CPU throttling, GC, cache misses và I/O.
- Branch predictability và object lifetime khác benchmark input.
- Tối ưu có thể phụ thuộc call-site profile, type distribution, escape và steady-state warmup.
- Benchmark một method thuần số học không đại diện cho request xử lý JSON, network và database.
- Cách data được phân bố trong memory có thể chi phối cost hơn số phép nhân.

**Ưu tiên cả microbenchmark lẫn workload benchmark**:
1. Microbenchmark kiểm tra **một giả thuyết tối ưu** rõ ràng (ví dụ constant folding, branch elimination).
2. Macro/load test xác nhận **throughput, end-to-end p95/p99 và CPU/GC** của service thực.
3. Tất cả kết quả cần có **JDK exact build**, JVM flags, CPU quota/hardware, JMH version, forks, input distribution và error bars.

### Nhầm benchmark result với chi phí một câu lệnh

Nếu JMH báo dưới một nanosecond/op:
- Đó có thể là throughput amortization hoặc phép toán đã được fold.
- Có thể JMH tính “operation” khác với số instructions trực giác.
- CPU pipelining, vectorization và đo nhiều iterations cùng nhau có thể tạo ns/op nhỏ hơn độ trễ của một individual machine instruction.
- Đừng kết luận “CPU chạy 1 phép chia hết 0 ns”. Cần đọc mode, code shape, generated assembly/IR khi thực sự cần.

## 16. Các tối ưu hợp lệ khác gây nhầm lẫn khi đo

### Common subexpression elimination (CSE)

~~~java
int left = x * 31;
int right = x * 31;
return left + right;
~~~

Đây là snippet trong method, giả sử x là biến int. Compiler có thể chỉ tính `x*31` một lần và dùng lại kết quả. Nếu benchmark đặt hai phép nhân để đo “hai lần multiplication”, JIT có thể đo một phép nhân.

### Algebraic simplification

~~~java
int y = x + 0;
int z = y * 1;
return z;
~~~

Có thể đơn giản hóa thành return x. Không nói compiler phải giữ phép cộng/nhân vì source có hai operators.

### Branch folding

~~~java
if (false) {
    System.out.println("unreachable branch");
}
~~~

Đây là snippet. `javac` hoặc JIT có thể không cần thực thi nhánh không thể đạt. Tuy nhiên đừng đặt unreachable statements sau `return` nếu Java source sẽ không biên dịch theo reachability rules.

### Loop unrolling và vectorization

Một loop duyệt mảng nguyên số có thể được unroll hoặc vectorize bởi JIT nếu được hỗ trợ và các dependence/aliasing constraints cho phép. Khi đó việc “mỗi iteration có một phép toán scalar” không còn tương ứng một-một với machine instructions.

### Strength reduction

Thay một phép nhân/địa chỉ index bằng shift/lea hoặc arithmetic thích hợp là một optimization phụ thuộc target CPU. Không dùng số lượng operator trong source để suy runtime cycles.

### Escape analysis

Một object tạo trong loop nhưng không escape có thể được scalar-replace, làm allocation rate trong profiler thấp hơn số `new` expressions. Nếu mục tiêu là đo allocation/GC pressure, benchmark cần làm cho object **thực sự escape phù hợp production semantics**, không chỉ có chữ `new`.

## 17. Inlining và specialization theo profile có thể dẫn đến deoptimization

C2 có thể dùng observed type profiles để chuyên biệt hóa call path. Ví dụ một virtual call thường thấy cùng một receiver type có thể được inline với một guard. Khi một type khác xuất hiện, optimized assumption không còn hợp lệ.

Để vẫn đúng Java semantics, HotSpot có thể:
1. Guard runtime assumptions.
2. Thực thi optimized path khi assumption đúng.
3. Thực hiện deoptimization/uncommon trap hoặc đường fallback khi assumption không đúng.
4. Tiếp tục ở interpreter/compiled version phù hợp, có thể recompile sau đó.

**Điều này không làm folding/DCE sai.** Optimization chỉ được áp dụng trong miền điều kiện hợp lệ; guard/fallback bảo toàn behavior ngoài miền.

Dưới workload benchmark chỉ chứa một loại input/receiver, JIT có thể tạo specialized code mạnh. Trong production có nhiều loại và input distributions khác, branch prediction, guard miss và deoptimization overhead có thể thay đổi hiệu năng đáng kể. Vì vậy cần benchmark có **type diversity** và parameters đại diện.

## 18. Mối liên hệ với Java Memory Model và multithreading

JIT không được tự do xóa các operations có **happens-before/order semantics** theo Java Memory Model. Với `volatile`, synchronization, thread start/join hoặc atomic APIs, những ràng buộc quan sát được phải giữ.

Ví dụ:

~~~java
final class Shared {
    volatile boolean ready;
    int payload;

    void publish() {
        payload = 42;
        ready = true;
    }
}
~~~

Đây là class minh họa. Trong trường hợp thread khác đọc `ready` là true bằng volatile read phù hợp, Java Memory Model hỗ trợ visibility của những writes trước volatile write. JIT không thể xóa/reorder theo cách phá guarantee này.

**Nhưng** trong một single-threaded benchmark không có synchronization, compiler có thể optimize mạnh hơn. Đừng suy từ microbenchmark thiếu concurrency ra behavior của code chia sẻ giữa threads.

Một variable thông thường không phải volatile **không đồng nghĩa JVM được tự do trả kết quả sai trong mọi trường hợp**; sự khác biệt nằm trong ràng buộc Java Memory Model và các hành vi program được phép quan sát. Khi thiết kế benchmark concurrent, cần mô hình đúng data races, atomicity và synchronization thay vì tự suy luận JIT.

## 19. Dùng javap, PrintCompilation, JFR và assembly một cách thận trọng

### Bước 1: bytecode với javap

~~~bash
javac --release 17 FoldingAndDceDemo.java
javap -c -p FoldingAndDceDemo
~~~

Kiểm tra `compileTimeConstant` và `unusedArithmetic`. Nếu bytecode chứa arithmetic dư mà optimized run vẫn nhanh, điều đó **có thể** do JIT; cần thêm bằng chứng về generated code, không được kết luận chỉ từ timing.

### Bước 2: compilation events

~~~bash
java -XX:+PrintCompilation FoldingAndDceDemo
~~~

HotSpot có thể in compiler events, bao gồm library methods. **Không có log/compile ID/output thứ tự cố định** vì dependent JDK build, warmup, compiler queue và workload. Chương trình quá ngắn có thể không compile một số methods trước khi kết thúc.

### Bước 3: JFR

Có thể thu thông tin compiler/GC/CPU events với JFR theo JDK:

~~~bash
java -XX:StartFlightRecording=filename=jit-folding.jfr,dumponexit=true,settings=profile FoldingAndDceDemo
~~~

Recording có thể thiếu events nếu chương trình quá ngắn, và **JFR không trực tiếp chứng minh một expression đã được constant-fold**. JFR hữu ích để thấy JIT/CPU/GC context và tìm hotspots.

### Bước 4: generated machine code

Muốn chứng minh phép tính bị loại khỏi optimized code, cần dùng công cụ phù hợp để phân tích native instructions hoặc JIT compiler IR:
- HotSpot `-XX:+PrintAssembly` khi có disassembler/hsdis phù hợp, cùng các unlock flags tương ứng.
- JITWatch đọc compilation logs và hiển thị các quyết định compiler.
- Async profiler/perf disassembly với debug information nếu môi trường phù hợp.
- Ideal Graph Visualizer hoặc debug/JIT diagnostic facilities với môi trường hỗ trợ.

**Các công cụ này không phải lúc nào cũng cài sẵn hoặc hoạt động trên mọi JDK/platform**. Không viết lệnh `-XX:+PrintAssembly` như điều kiện bắt buộc để chạy code Java.

### LogCompilation để nghiên cứu deeper optimizer

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation -XX:LogFile=jit.xml FoldingAndDceDemo
~~~

Đây là HotSpot diagnostic option, XML format/version dependent. JITWatch có thể giúp xem inlining, compilation tiers, traps. Đừng nhầm compiler source IR với Java bytecode hoặc giả định source statement có một instruction tương ứng.

## 20. Vì sao timing bằng System.nanoTime() một lần dễ sai?

Một phép đo:

~~~java
long start = System.nanoTime();
// gọi work() nhiều lần
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
~~~

là **đoạn minh họa**, chưa đủ là benchmark đáng tin. Các nguồn sai lệch:

1. **Dead-code elimination:** nếu work result không dùng, work bị xóa.
2. **Constant folding:** nếu inputs known, kết quả có thể tính trước.
3. **JIT warmup/tiering:** vòng chạy đầu interpreter/C1, vòng sau C2, có OSR giữa chừng.
4. **Loop optimizations:** unrolling, LICM, vectorization, loop removal.
5. **Timer overhead/resolution:** phương thức đo có chi phí và noise.
6. **GC activity:** allocations hoặc logging gây pauses/churn.
7. **OS scheduling/CPU frequency:** thread bị preempt, thermal throttling.
8. **CPU caches/TLB:** dữ liệu nóng/lạnh khác nhau.
9. **Concurrent load:** nhiều tiến trình tranh CPU/memory bandwidth.
10. **Benchmark unit/normalization:** elapsed time của một loop không tự là latency của một operation trong ứng dụng.

Ngay cả khi lặp 100 lần và lấy median, nếu benchmark body bị fold/DCE thì bạn chỉ đo một workload đã bị tối ưu khác mục tiêu.

### Một checklist microbenchmark hợp lệ

- **Nêu giả thuyết:** đo phép nhân với runtime inputs hay đo input-hằng?
- **Đảm bảo input:** dùng state/datasets và tham số đủ đại diện.
- **Đảm bảo output được dùng:** return, Blackhole hoặc observable application semantics.
- **Không thêm artificial work áp đảo:** console I/O, random number generation, synchronization không có trong production.
- **Warmup/forks:** JMH giúp kiểm soát, đo nhiều lần.
- **JIT version/flags:** ghi JDK build, tiered mode và compiler version.
- **Compare like-for-like:** cùng dữ liệu, cùng correctness và tool settings.
- **Theo dõi CPU/GC:** không suy từ ns/op ra tổng hiệu năng service.
- **Kiểm chứng optimization:** khi nghi DCE/folding, xem compiler logs/assembly/IR phù hợp.
- **Báo variance:** không chỉ một con số đẹp nhất.

## 21. Bài tập tự kiểm tra

**Câu 1.** Với `static final int X = 6*7`, phần gấp hằng có thể xảy ra ở tầng nào?

**Đáp án:** `javac` có thể gấp ngay ở bytecode vì `X` là JLS constant variable; JIT còn có các dạng folding/propagation runtime khác.

**Câu 2.** `static final int Y = Integer.parseInt("42")` có phải compile-time constant variable?

**Đáp án:** **Không** theo JLS; initializer là method call, dù field được khai báo final.

**Câu 3.** Benchmark chỉ gọi `compute(10)` rồi bỏ result có hai nguy cơ nào?

**Đáp án:** **Constant folding** với input literal và **DCE** vì output không được dùng.

**Câu 4.** Return result trong JMH đã đủ ngăn gấp hằng chưa?

**Đáp án:** Chưa. JMH giữ output observable hơn, nhưng input literal vẫn có thể bị fold.

**Câu 5.** Vì sao không dùng `System.out.println` trong timed benchmark?

**Đáp án:** Console I/O có overhead lớn/biến động, đo nhầm in ra màn hình thay vì calculation.

**Câu 6.** Tại sao volatile sink có thể làm benchmark sai?

**Đáp án:** Nó thêm memory-ordering/visibility overhead và contention; là operation mới không nhất thiết có trong workload thật.

**Câu 7.** `int ignored = 100/x; return 7;` có luôn được phép loại phép chia không?

**Đáp án:** Không. Nếu x=0, phải ném `ArithmeticException`.

**Câu 8.** `return x*0+9;` có thể thành 9 khi x là int không?

**Đáp án:** Có nếu compiler chứng minh không có side effects phụ; integer multiplication by zero là 0 theo semantics.

**Câu 9.** `return x*0.0d;` có thể luôn thành +0.0d không?

**Đáp án:** Không. Infinity×0 là NaN và negative×positive zero có thể là -0.0.

**Câu 10.** Đọc `javap` thấy `imul` nghĩa CPU nhất thiết có lệnh nhân không?

**Đáp án:** Không. `javap` hiển thị bytecode; JIT có thể fold hoặc remove ở native level.

**Câu 11.** Một object được tạo bằng `new` không escape có nhất thiết tốn heap allocation trên optimized execution không?

**Đáp án:** Không. Escape analysis/scalar replacement có thể bỏ physical allocation khi giữ đúng semantics.

**Câu 12.** Vì sao @State non-final field tốt hơn một literal cố định trong constant-folding benchmark?

**Đáp án:** Đầu vào được lấy từ state thay vì hằng trực tiếp tại call site, giảm khả năng benchmark vô tình biến thành constant path; vẫn phải kiểm tra tối ưu/runtime.

**Câu 13.** Hoist một phép tính ra ngoài loop có làm sai Java không?

**Đáp án:** Nếu JIT chứng minh bảo toàn side effects, exception order và semantics, đó là tối ưu hợp lệ; nếu không chứng minh, không được hoist.

**Câu 14.** Một benchmark báo 0,2 ns/op có chắc CPU thực hiện operation trong 0,2 ns không?

**Đáp án:** Không. Cần xét loop amortization, compiler optimization, pipeline và measurement mode.

**Câu 15.** Nếu source có `new Object()` nhưng profiler không thấy allocation tương ứng, chắc profiler sai?

**Đáp án:** Không. JIT có thể loại allocation vật lý của object không escape/không quan sát được.

**Câu 16.** JMH benchmark có tốt sẽ dự đoán p99 REST API chính xác?

**Đáp án:** Không. Phải kiểm tra application workloads, I/O, concurrency, GC và tail latency.

## 22. Bản đồ ghi nhớ

~~~text
JAVA SOURCE
   |
   +--> JAVAC COMPILE-TIME
   |      constant expressions
   |      constant variables (final primitive/String)
   |      -> bytecode có thể chứa constant
   |
   v
HOTSPOT / INTERPRETER / JIT
   |
   +--> inlining + profile
   +--> constant propagation/folding
   +--> dead branch/code removal
   +--> loop invariant hoisting
   +--> scalar replacement / allocation elimination
   |
   v
MACHINE CODE (không 1-1 với source statements)
   |
   +--> phải bảo toàn Java semantics:
   |      exceptions, volatile/synchronization, I/O,
   |      floating-point, overflow, observable effects
   |
   v
BENCHMARK RISK
   |
   +-- input hằng?       -> code bị fold
   +-- output bỏ đi?      -> code bị DCE
   +-- input chưa đại diện? -> benchmark sai workload
   +-- volatile/print?    -> đo overhead mới
   |
   v
JMH @State + @Param + return/Blackhole
   |
   +-- warmup + forks + measurements
   +-- compiler logs / IR / assembly khi cần
   +-- verify correctness and production relevance
   |
   v
BENCHMARK ĐÁNG TIN HƠN
~~~

**Kết luận:** Folding và DCE là các tối ưu **đúng đắn và có lợi** của `javac`/HotSpot JIT, nhưng chúng có thể làm microbenchmark **không còn thực thi phần công việc người viết tưởng đang đo**. Hãy phân biệt constant expressions của JLS với runtime JIT optimization, không bỏ qua exceptions/side effects/IEEE 754, và kiểm soát **cả input lẫn output** trong benchmark bằng JMH. Mục tiêu của phép đo không phải giữ nguyên source instructions bằng mọi giá, mà là đại diện đúng **công việc thực tế của ứng dụng**.

## Tài liệu tham khảo

- [JLS Java SE 17 — §15.29 Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29).
- [JLS Java SE 17 — §4.12.4 final Variables, Constant Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4).
- [JLS Java SE 17 — §13.1 binary compatibility và constant variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.1).
- [JLS Java SE 17 — §15.7 Evaluation Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.7).
- [JLS Java SE 17 — §17.4 Java Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4).
- [OpenJDK Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/).
- [JMH — JMHSample_08_DeadCode](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java).
- [JMH — JMHSample_10_ConstantFold](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java).
- [JMH — Blackhole implementation/documentation](https://github.com/openjdk/jmh/blob/master/jmh-core/src/main/java/org/openjdk/jmh/infra/Blackhole.java).
- [Oracle JDK 17 — javap tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
- [Oracle JDK 17 — Java launcher and JIT diagnostic options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [OpenJDK HotSpot C2 optimizer source](https://github.com/openjdk/jdk/tree/master/src/hotspot/share/opto).
