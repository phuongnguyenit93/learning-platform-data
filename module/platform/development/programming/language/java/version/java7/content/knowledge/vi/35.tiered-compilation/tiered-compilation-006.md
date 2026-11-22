# Phân biệt tối ưu của JVM với bảo đảm của ngôn ngữ Java trong JIT phân tầng

**Chủ đề:** JIT phân tầng (Tiered Compilation)  
**Bài học:** Phân biệt tối ưu của JVM với bảo đảm của ngôn ngữ  
**Môi trường:** Java 17+; trọng tâm là HotSpot JVM và các quy tắc Java vẫn có hiệu lực hiện nay.

Cùng một chương trình Java có thể được chạy bằng trình thông dịch bytecode, bằng mã máy do JIT biên dịch ở nhiều tầng, hoặc bằng một phiên bản mã máy được tối ưu lại sau khi JVM thu thập thêm dữ liệu. **Cách thực thi có thể thay đổi, còn những hành vi mà Java bảo đảm cho chương trình phải được giữ nguyên.**

Ví dụ, HotSpot có thể inline một lời gọi phương thức, bỏ cấp phát đối tượng không thoát ra ngoài, loại bỏ kiểm tra ranh giới mảng mà nó chứng minh luôn đúng, hoặc thay mã máy khi một giả định không còn hợp lệ. Những việc đó **không cho phép** làm sai quy tắc tràn số nguyên, thứ tự tác dụng phụ có thể quan sát, ngoại lệ bắt buộc, object identity hay quan hệ happens-before của Java Memory Model (JMM).

## 1. Hai lớp cần phân biệt

| Lớp | Quy định điều gì? | Ví dụ |
|---|---|---|
| **Java Language Specification (JLS)** | Ngữ nghĩa biểu thức, toán tử, đánh giá, ngoại lệ, thread và JMM mà chương trình Java được quyền dựa vào | Tràn `int` theo hai's-complement; thứ tự đánh giá toán hạng từ trái sang phải; quy tắc `volatile`, `synchronized` |
| **Java Virtual Machine Specification (JVMS)** | Định dạng class file, bytecode, cách thực thi có ý nghĩa đúng, xác minh và các trách nhiệm của JVM | Bytecode phải có tác dụng tương đương với ngữ nghĩa quy định |
| **Java SE API contracts** | Hành vi được API công khai hứa hẹn | `Math.addExact` báo `ArithmeticException` khi tràn; `AtomicInteger.incrementAndGet` tăng nguyên tử |
| **Cách triển khai HotSpot** | Lựa chọn interpreter/JIT, tier, inlining, escape analysis, compiled-code cache, heuristics, deoptimization | Một method có thể được biên dịch C1/C2 hoặc không được biên dịch; không có cam kết về số lần gọi trước khi tối ưu |
| **Hiệu năng thực tế** | Phụ thuộc JDK, CPU, tải, warmup, cấu hình và profile lúc chạy | Latency, throughput, mức cấp phát, thời gian compiler; **không** phải kết quả được JLS cố định |

**Ranh giới quan trọng:** kết quả hợp lệ được xác định bởi hợp đồng Java; đường đi để tạo ra kết quả đó là lựa chọn của JVM. JLS/JVMS không bắt buộc một chương trình phải chạy qua HotSpot, C1 hay C2; một runtime Java hợp lệ có thể chọn cách thực thi khác.

Không nên dùng mệnh đề “JIT được quyền thay đổi code tùy ý” mà bỏ phần điều kiện: nó chỉ được thực hiện những biến đổi **tương thích với mọi hành vi mà đặc tả cho phép quan sát**, bao gồm cả các trường hợp có đồng bộ đa luồng.

## 2. Vai trò của JIT phân tầng trong HotSpot

**Tiered compilation** kết hợp thực thi ban đầu với việc thu thập thông tin runtime và biên dịch phương thức thường xuyên được dùng:

1. **Interpreter:** bắt đầu thực thi bytecode, có thể thu thập thông tin về đường nhánh, lời gọi và tần suất thực hiện.
2. **Các mức biên dịch nhanh (thường là C1):** tạo mã máy tương đối nhanh, có thể tiếp tục gắn profiling để phục vụ quyết định tiếp theo.
3. **Biên dịch tối ưu sâu hơn (thường là C2):** sử dụng profile để làm các tối ưu tốn thời gian hơn cho những đường chạy được xem là có lợi.
4. **Thay đổi động:** khi profile thay đổi, class mới xuất hiện, giả định không còn đúng hoặc compiler cần thay code, JVM có thể biên dịch lại, **deoptimize** về mã ít tối ưu hơn, rồi tiếp tục thực thi đúng.

Trong cấu hình HotSpot C1/C2 phổ biến, có thể gặp các mức chẩn đoán **0 = interpreter**, **1–3 = các kiểu mã C1/profiling**, **4 = C2**. Đây là thông tin **triển khai để quan sát**, không phải API của ngôn ngữ hay bảo đảm mọi method luôn đi qua 0 → 1 → 2 → 3 → 4. Một method có thể nhảy mức, bị thay thế, không đủ nóng để biên dịch hoặc chạy theo một con đường khác tùy JVM/JDK/cờ.

**On-Stack Replacement (OSR)** cho phép một vòng lặp đang chạy lâu chuyển sang phiên bản mã đã biên dịch mà không đợi method kết thúc rồi mới gọi lại. `-XX:+PrintCompilation` có thể hiển thị dấu `%` ở những mục OSR; việc có hay không có OSR là chi tiết thực thi.

**Deoptimization** là phần thiết yếu của tối ưu có giả định: ví dụ profile từng thấy duy nhất một kiểu đối tượng ở vị trí gọi method; JIT có thể tạo đường đi nhanh với guard, nhưng khi kiểu khác xuất hiện nó phải quay về đường đúng hoặc tái biên dịch. Không được biến “trước đây chỉ thấy kiểu A” thành “kiểu B vĩnh viễn bị cấm”.

### Minh họa ý tưởng

```text
Bytecode Java
     |
     v
Interpreter + profiling
     |
     +--> mã biên dịch sớm / thêm profiling (thường C1)
     |                  |
     |                  v
     +------------> mã tối ưu sâu (thường C2)
                            |
              giả định bị phá vỡ / profile thay đổi
                            |
                            v
                    guard, deoptimization,
                    chạy đường hợp lệ / recompile
```

Mục tiêu là rút ngắn thời gian khởi động và đạt throughput tốt khi ứng dụng chạy lâu. **Không có bảo đảm tốc độ sẽ tăng ở mọi method**; compilation cũng tiêu tốn CPU/bộ nhớ, và hành vi phụ thuộc workload.

## 3. Những tối ưu JVM có thể làm nhưng không hứa sẽ làm

| Tối ưu thường gặp | Ý tưởng | Điều không được kết luận |
|---|---|---|
| **Method inlining** | Đưa logic lời gọi vào caller để giảm call overhead và mở cơ hội tối ưu liên phương thức | “Method nhỏ chắc chắn luôn được inline.” |
| **Constant folding / propagation** | Tính trước giá trị có thể chứng minh bất biến | “JIT được đổi kết quả tràn số hoặc tác dụng phụ.” |
| **Dead-code elimination** | Bỏ tính toán không tạo khác biệt có thể quan sát | “Code không được dùng vẫn là benchmark đo công việc thực.” |
| **Escape analysis / scalar replacement** | Phân tích object không thoát ra ngoài, có thể giữ dữ liệu dưới dạng scalar và bỏ allocation vật lý | “Mỗi `new` chắc chắn có heap allocation”; hoặc ngược lại “JIT chắc chắn xóa `new`.” |
| **Bounds/null-check elimination** | Bỏ kiểm tra khi có bằng chứng nhánh đó không thể gây lỗi | “Có thể bỏ ngoại lệ bắt buộc trên đường chạy thực sự bị lỗi.” |
| **Loop optimization** | Unroll, hoist tính toán bất biến, gộp bước xử lý hợp lệ | “Có thể đổi thứ tự side effect tùy ý.” |
| **Devirtualization/speculative inlining** | Chọn đường nhanh theo kiểu đối tượng đang quan sát, kèm guard khi cần | “Các kiểu chưa từng thấy sẽ bị xử lý sai.” |
| **Lock elimination/coarsening** | Bỏ hoặc gộp khóa khi chứng minh không thay đổi đồng bộ quan sát được | “Bỏ khóa là an toàn với mọi đối tượng shared.” |
| **Intrinsics / SIMD khi thích hợp** | Thay một thao tác API/loop bằng chuỗi lệnh máy tối ưu tương đương | “Sẽ có đúng một loại chỉ thị CPU trên mọi hệ thống.” |

**Lợi ích tối ưu là tùy chọn; bảo đảm ngữ nghĩa là bắt buộc.** Ngay cả khi một object không thật sự xuất hiện trên heap nhờ escape analysis, các kết quả quan sát được qua Java vẫn phải nhất quán với chương trình được đặc tả.

## 4. Những bảo đảm ngôn ngữ JIT phải tôn trọng

### 4.1. Tràn số nguyên là ngữ nghĩa xác định

`int` có 32 bit signed, `long` có 64 bit signed. Cộng, trừ, nhân nguyên thủy có thể tràn và dùng kết quả theo quy tắc số nguyên Java, không tự động báo lỗi. Ví dụ:

```java
int wrapped = Integer.MAX_VALUE + 1;  // Integer.MIN_VALUE
int exact = Math.addExact(40, 2);       // 42
// Math.addExact(Integer.MAX_VALUE, 1) -> ArithmeticException
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Compiler có thể **constant-fold** phép cộng đầu tiên; kết quả vẫn phải là `-2147483648`. Không suy luận như ngôn ngữ khác rằng signed integer overflow cho phép compiler tự chọn hành vi. Nếu nghiệp vụ không cho tràn, sử dụng `Math.addExact`, kiểm tra phạm vi hoặc kiểu số phù hợp.

### 4.2. Thứ tự đánh giá và side effects có thể quan sát

Các toán hạng của toán tử Java được đánh giá **trái sang phải**, kèm ngoại lệ cụ thể của short-circuit/conditional expressions về việc có đánh giá hay không. JIT có thể sắp xếp lại tính toán nội bộ **nếu kết quả và các side effects có thể quan sát vẫn đúng như đặc tả**.

```java
// Minh họa bên trong một method:
// left(events) thêm 'L', trả 2; right(events) thêm 'R', trả 3.
int result = left(events) + right(events);
// events phải là "LR", result phải là 5.
```

Không thể đổi thành hành vi quan sát được `"RL"` chỉ để sử dụng pipeline CPU hiệu quả hơn. Tuy nhiên, với các phép toán thuần không có side effect, compiler có nhiều không gian biến đổi hợp lệ.

### 4.3. Ngoại lệ và kiểm tra an toàn

Khi chương trình thực sự truy cập mảng ngoài chỉ số, dereference null, chia số nguyên cho 0 hoặc gọi API hứa sẽ ném lỗi trong điều kiện cụ thể, runtime phải thể hiện đúng hành vi tương ứng. JIT có thể **loại bỏ kiểm tra dư thừa** nếu chứng minh đường chạy không thể vi phạm điều kiện; không thể âm thầm trả giá trị hợp lệ trong trường hợp lẽ ra phải ném ngoại lệ.

Ví dụ một vòng lặp có `i` luôn nằm trong `0..array.length-1` có thể không cần bounds check cho mọi phần tử, nhưng `array[array.length]` vẫn phải thất bại nếu thực sự được thực thi.

### 4.4. Dấu phẩy động có quy tắc, không tùy tiện áp dụng đại số thực

Từ Java 17, biểu thức floating-point được đánh giá theo **ngữ nghĩa strict thống nhất** của Java. Trong thực thi IEEE 754 có rounding, infinity, NaN, signed zero; nhiều phép biến đổi đúng về số thực nhưng **không tương đương** ở double/float.

```java
double x = 8.0e307;
double a = 4.0 * x * 0.5; // Infinity
double b = 2.0 * x;       // 1.6E308 (finite)
```

Compiler không thể tự thay `4.0 * x * 0.5` bằng `2.0 * x` trong trường hợp này vì kết quả khác nhau. Tương tự, `NaN == NaN` là `false`, và phép so sánh/biến đổi phải giữ quy tắc Java. Tránh dựa vào việc JIT “tăng tốc” bằng cách thay đổi quy tắc FP; nếu bài toán cần dung sai số học, thiết kế riêng phép so sánh có sai số.

### 4.5. Object identity và thứ tự khởi tạo

JIT có thể gộp/loại allocation mà nó chứng minh không tạo khác biệt được quan sát, nhưng không được biến hai tham chiếu thực sự phải trỏ cùng đối tượng thành hai đối tượng khác nhau, hoặc làm sai giá trị trường `final` đã được công bố đúng cách. `a == b`, các phương thức/constructor có side effect, thứ tự class initialization và ngoại lệ có thể quan sát vẫn bị ràng buộc bởi ngữ nghĩa Java.

Ví dụ `new Pair(...)` trong chương trình thực hành có thể được tối ưu nhờ escape analysis và inlining, nhưng Java **không hứa** rằng allocation chắc chắn bị loại. Không dùng số lần gọi constructor như phép đo trực tiếp số lần allocation vật lý khi compiler được quyền tối ưu.

## 5. Java Memory Model: tối ưu hợp lệ trong chương trình đa luồng

Đây là phần dễ nhầm nhất khi so sánh JIT và ngôn ngữ. **JMM** (`JLS 17`) quy định các kết quả có thể xảy ra do đọc/ghi shared variables và các quan hệ **happens-before**. JIT và CPU được phép sắp xếp lại một số thao tác nội bộ **trong phạm vi mô hình đó**.

- **Program order** tạo quan hệ happens-before giữa các hành động trong cùng thread theo các quy tắc JMM.
- **`volatile`:** ghi vào biến volatile synchronizes-with một lần đọc biến volatile đó theo thứ tự đồng bộ thích hợp; dữ liệu được viết trước khi publish có thể được nhìn thấy khi thread khác đọc flag đúng cách.
- **`synchronized`:** unlock một monitor synchronizes-with lock tiếp theo trên **cùng** monitor; đồng thời bảo đảm mutual exclusion khi giữ khóa.
- **`Thread.start()` và `Thread.join()`:** tạo những quan hệ happens-before được đặc tả.
- **`AtomicInteger`:** cung cấp thao tác cập nhật nguyên tử theo contract API và các hiệu ứng bộ nhớ tương ứng.

Minh họa publish bằng flag volatile (hai đoạn là **code ở hai thread khác nhau**, không phải chương trình độc lập):

```java
// Shared fields:
static int data;
static volatile boolean ready;

// Thread ghi:
data = 42;
ready = true;

// Thread đọc:
if (ready) {
    // Khi đã thấy true từ lần publish phù hợp,
    // phải thấy data == 42, nếu không có write cạnh tranh khác.
    assert data == 42;
}
```

**Giới hạn quan trọng:** `volatile` bảo đảm visibility và ordering phù hợp, nhưng `volatileCount++` là **read + add + write**, không phải một phép tăng nguyên tử. Với nhiều thread đồng thời, dùng `AtomicInteger.incrementAndGet()`, `LongAdder` (khi bài toán cần thống kê tổng hợp với đánh đổi tương ứng) hoặc khóa đúng cách. `volatile` cũng không biến một thuật toán có data race thành tự động an toàn.

Nếu code **thiếu đồng bộ** giữa các truy cập xung đột, không được dựa vào việc “máy tôi luôn in giá trị đúng”, “`-Xint` thì đúng” hoặc “debug mode thì đúng”. Những hành vi may rủi của chương trình có data race **không phải bảo đảm của Java**, và tối ưu JIT có thể làm lộ lỗi đã tồn tại. Không có nghĩa compiler được phép vi phạm JMM: vấn đề nằm ở việc chương trình không có happens-before cần thiết.

## 6. Chương trình Java 17+ đối chiếu ngữ nghĩa ở interpreter và JIT

Tệp **`JitContractDemo.java`** bên dưới chủ động kiểm tra nhiều hợp đồng Java trong cùng một chương trình. Vòng lặp `calculate(...)` tạo cơ hội cho runtime tối ưu khi chạy lâu, và `Pair` có thể là ứng viên cho inlining/escape analysis. **Không dùng việc tối ưu xảy ra hay không làm điều kiện PASS**.

`seed` và `observed` là `volatile`. Vòng lặp liên tục đọc seed, và kết quả được publish qua `observed` để phần tính toán có đường sử dụng rõ ràng. Tuy nhiên, `volatile` **không phải** giải pháp benchmark tổng quát, và kết quả chạy nhanh/chậm không được kiểm tra trong bài.

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class JitContractDemo {
    private static volatile int seed = 7;
    private static volatile long observed;

    private record Pair(int left, int right) {}

    static int calculate(int n) {
        Pair pair = new Pair(n * 31, n ^ 0x5a);
        return pair.left() + pair.right();
    }

    static int left(StringBuilder events) {
        events.append('L');
        return 2;
    }

    static int right(StringBuilder events) {
        events.append('R');
        return 3;
    }

    public static void main(String[] args) throws InterruptedException {
        long sum = 0;
        for (int i = 0; i < 500_000; i++) {
            sum += calculate((i + seed) & 31);
        }
        observed = sum;
        if (sum != 280_000_000L) {
            throw new AssertionError("Wrong checksum: " + sum);
        }

        int overflow = Integer.MAX_VALUE + 1;
        if (overflow != Integer.MIN_VALUE) {
            throw new AssertionError("Broken int overflow");
        }
        boolean exactThrows = false;
        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException e) {
            exactThrows = true;
        }
        if (!exactThrows) throw new AssertionError("Expected ArithmeticException");

        StringBuilder events = new StringBuilder();
        int value = left(events) + right(events);
        if (!events.toString().equals("LR") || value != 5) {
            throw new AssertionError("Evaluation order changed");
        }

        double x = 8.0e307;
        boolean floatingPoint = Double.isInfinite(4.0 * x * 0.5)
                && Double.isFinite(2.0 * x);
        if (!floatingPoint) throw new AssertionError("Floating point changed");

        AtomicInteger count = new AtomicInteger();
        Runnable increment = () -> {
            for (int i = 0; i < 10_000; i++) count.incrementAndGet();
        };
        Thread first = new Thread(increment);
        Thread second = new Thread(increment);
        first.start();
        second.start();
        first.join();
        second.join();
        if (count.get() != 20_000) {
            throw new AssertionError("Lost atomic updates");
        }

        System.out.println("SUM=" + observed);
        System.out.println("INT_OVERFLOW=" + overflow);
        System.out.println("ADD_EXACT_THROWS=" + exactThrows);
        System.out.println("ORDER=" + events + "/" + value);
        System.out.println("FLOAT_RULES=" + floatingPoint);
        System.out.println("ATOMIC_COUNT=" + count.get());
    }
}
```

**Biên dịch và chạy** từ thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 JitContractDemo.java

# Chạy với cơ chế mặc định của HotSpot (thường bật tiered JIT):
java JitContractDemo

# Chạy bằng interpreter, không dùng JIT:
java -Xint JitContractDemo

# Xem thêm dòng chẩn đoán các phương thức được JIT biên dịch:
java -XX:+PrintCompilation JitContractDemo
```

Trong cả hai cách chạy **không bật diagnostic logging**, stdout của **chương trình** là chính xác:

```text
SUM=280000000
INT_OVERFLOW=-2147483648
ADD_EXACT_THROWS=true
ORDER=LR/5
FLOAT_RULES=true
ATOMIC_COUNT=20000
```

Với `-XX:+PrintCompilation`, HotSpot sẽ in thêm nhiều dòng thông tin compiler; những dòng đó **không cố định** về thứ tự, số lần hay tier. Ví dụ một số dấu hiệu có thể xuất hiện trong môi trường HotSpot C1/C2 (chỉ để minh họa cách đọc):

```text
...  3  JitContractDemo::calculate (...)
...  4  JitContractDemo::calculate (...)
...     JitContractDemo::calculate (...) made not entrant
...  %  4  JitContractDemo::main @ ...
```

Dấu `3`/`4` trong output kiểu này thường biểu diễn tier; `%` là ký hiệu OSR và `made not entrant` có thể xuất hiện khi phiên bản mã không còn được lựa chọn để bắt đầu các lời gọi mới. Không lấy sự xuất hiện chính xác của bất kỳ dòng nào làm điều kiện test: các quyết định này phụ thuộc version HotSpot, profile và cấu hình.

**Cách hiểu từng phép kiểm tra trong demo:**

1. **`SUM`:** các phép tính `calculate` phải giữ kết quả dù JVM có inline phương thức, loại `Pair` allocation hay vectorize một phần tính toán. Giá trị `280000000` kiểm tra tính đúng ở mức Java, không kiểm tra có escape analysis hay không.
2. **`INT_OVERFLOW` / `ADD_EXACT_THROWS`:** cộng `int` thường wrap, còn `Math.addExact` chủ động phát hiện tràn. JIT phải giữ hai kết quả này khác nhau.
3. **`ORDER`:** hai hàm thay đổi `StringBuilder` phải có thứ tự quan sát `LR`, bất kể cách sắp xếp lệnh máy bên dưới.
4. **`FLOAT_RULES`:** overflow FP của `4.0*x*0.5` và tính hữu hạn của `2.0*x` không được gộp làm một biểu thức cho kết quả sai.
5. **`ATOMIC_COUNT`:** hai thread mỗi thread tăng 10.000 lần trên `AtomicInteger` và chờ qua `join()`; tổng phải là `20000`. Điều này không có nghĩa tăng một biến `volatile int` cũng an toàn tương đương.
6. **Không đo thời gian:** tốc độ khác nhau không phải thất bại ngữ nghĩa. Để đo hiệu năng cần thiết kế benchmark riêng, không lấy thời gian chương trình nhỏ làm tiêu chuẩn tối ưu JVM.

Nếu cần xem sự khác nhau giữa tiered và non-tiered trên **HotSpot**, tùy chọn `-XX:-TieredCompilation` có thể vô hiệu hóa **tiering**. Nó **không có nghĩa** chạy interpreter-only và không phải cú pháp Java language. `-Xint` mới là lựa chọn để chạy trong interpreter cho thí nghiệm so sánh như trên.

## 7. Phân tích một tối ưu giả định: inlining và deoptimization

Giả sử chương trình có:

```java
interface Calculator {
    int calculate(int x);
}

static int call(Calculator c, int x) {
    return c.calculate(x);
}
```

Đây là **đoạn minh họa API**, chưa có `main` hoặc class thực thi đầy đủ. Khi profile runtime chỉ thấy một implementation của `Calculator`, HotSpot có thể tối ưu lời gọi theo kiểu đó, thậm chí inline code và dùng guard. Nếu sau này một implementation khác được truyền vào, VM cần đi qua đường dự phòng đúng hoặc deoptimize/tái biên dịch.

Hai kết luận phải tách bạch:

- **JVM được lựa chọn:** có hay không devirtualization, inline sâu tới đâu, dùng profile gì, lúc nào deoptimize. Những điều này thay đổi theo tải và JDK.
- **Ngôn ngữ yêu cầu:** `call(c, x)` phải áp dụng đúng dynamic dispatch cho instance thực tế theo quy tắc Java; không được giữ kết quả sai chỉ vì profile cũ.

Điều này cũng đúng với **branch prediction**, **null-check hoisting** và **escape analysis**: tối ưu có thể dựa trên điều kiện đã được chứng minh hoặc canh giữ, nhưng không thể biến dữ liệu mới hợp lệ thành hành vi sai.

## 8. Test và benchmark: phải đo điều gì?

### Kiểm thử tính đúng (correctness)

Đầu tiên kiểm tra **nghĩa vụ của chương trình**. Test theo giá trị biên và các trường hợp có side effects:

| Loại test | Cần kiểm tra |
|---|---|
| Toán tử | `int/long` overflow, chia cho zero, dịch bit, signed zero/NaN/Infinity |
| Thứ tự | Side effects từ toán hạng, short-circuit, exception path |
| Object | Alias, `==`, reference và class initialization; không dựa vào địa chỉ vật lý |
| Exception | Null, bounds, cast, API có `ArithmeticException` |
| Đồng bộ | `volatile` publication, khóa chung, atomic operations, `start()/join()` |
| Hotness | Cùng kết quả khi chạy lạnh/nóng, bằng interpreter, bằng JIT |
| Đa hình | Gọi qua interface với nhiều implementation, thêm kiểu mới sau giai đoạn warmup |

Đối với chương trình đa luồng, thiết kế các thử nghiệm có đồng bộ hợp lệ, không cố “xác nhận hành vi” bằng cách đợi một race hiếm xuất hiện. Test chạy đúng nhiều lần không chứng minh code data-race-free; cần review happens-before và dùng công cụ kiểm thử concurrency phù hợp.

### Đo hiệu năng (performance)

Khi muốn biết inlining, escape analysis hoặc tiered JIT có cải thiện throughput không, đo bằng công cụ chuẩn như **JMH (Java Microbenchmark Harness)**, dùng **warmup**, nhiều lượt đo, fork độc lập, và kiểm tra benchmark tránh dead-code elimination/constant folding ngoài mục tiêu. Không đo một lần `System.nanoTime()` quanh vòng lặp rồi tuyên bố Java/JIT có guarantee hiệu năng.

Các biến số phải ghi lại: phiên bản JDK/VM, CPU, OS, cờ JVM, heap, tải nền, fork, thời gian warmup và cách tiêu thụ kết quả. Các phép benchmark hợp lệ không được giả định số lần JIT compile, tier hay thời gian pause giống nhau giữa các máy.

Đừng xem `-XX:+PrintCompilation` như profiler chi tiết về “đã thực sự chạy nhanh hơn bao nhiêu”. Nó chỉ cho tín hiệu compiler hoạt động; profiling bằng JFR hoặc các công cụ đo phù hợp nếu muốn điều tra thực tế.

## 9. Những hiểu nhầm thường gặp

| Khẳng định sai | Cách hiểu đúng |
|---|---|
| “JIT có quyền bỏ kiểm tra mảng nên truy cập ngoài biên sẽ không lỗi.” | Chỉ bỏ kiểm tra đã chứng minh dư thừa; đường truy cập ngoài biên thật phải giữ ngoại lệ. |
| “Method chạy đủ 10.000 lần chắc chắn lên C2.” | Không có ngưỡng compilation cố định do ngôn ngữ bảo đảm. |
| “`-XX:-TieredCompilation` tắt JIT hoàn toàn.” | Chỉ tắt cơ chế nhiều tầng của HotSpot; `-Xint` là interpreter-only. |
| “`new` luôn luôn cấp phát một object thật trên heap.” | Một object không escape có thể được tối ưu bằng scalar replacement; không bảo đảm sẽ xảy ra. |
| “Tối ưu có thể thay `(4*x)*0.5` thành `2*x` vì đại số bằng nhau.” | Với floating-point, rounding/overflow có thể làm kết quả khác; JLS giới hạn biến đổi. |
| “Nếu `volatile++` lúc test vẫn ra đúng thì nó nguyên tử.” | `volatile` không làm read-modify-write thành atomic; cần atomic operation/lock. |
| “HotSpot từng chỉ thấy class A nên được trả sai khi gặp class B.” | Tối ưu có guard/deopt/fallback để giữ đúng dynamic dispatch. |
| “`made not entrant` nghĩa là chương trình bị lỗi.” | Đây có thể là trạng thái lifecycle của compiled code, không phải lỗi nghiệp vụ. |
| “Interpreter đúng, JIT sai là bình thường.” | Hai đường chạy đều phải giữ hành vi hợp lệ theo Java; khác biệt thường là race không có đồng bộ, phụ thuộc môi trường, hoặc bug cần điều tra. |
| “Nhìn thời gian chạy là biết JIT đã inline method.” | Thời gian chịu nhiều ảnh hưởng; cần profile/log/chứng cứ phù hợp, không suy từ một số đo. |

## 10. Checklist hoàn thành bài

- [ ] Phân biệt **hợp đồng Java (JLS/JVMS/API/JMM)** với **chiến lược tối ưu HotSpot**.
- [ ] Giải thích interpreter, C1, C2, tiering, OSR và deoptimization ở mức không coi chúng là ràng buộc ngôn ngữ.
- [ ] Liệt kê tối ưu có thể xảy ra (inlining, constant folding, escape analysis, bounds-check elimination) và nêu điều kiện bảo toàn ngữ nghĩa.
- [ ] Kiểm thử chính xác `int` overflow, ngoại lệ bắt buộc, thứ tự side effects, floating-point và đồng bộ `AtomicInteger`.
- [ ] Chạy mã ví dụ bằng `java` và `java -Xint`, xác minh **sáu dòng stdout giống nhau**.
- [ ] Biết đọc `-XX:+PrintCompilation` như log chẩn đoán, không dùng tier/thời điểm biên dịch làm assertion.
- [ ] Biết phân biệt bài test correctness và benchmark throughput/latency; sử dụng JMH khi phải đo tối ưu.
- [ ] Nhận diện `volatile` visibility khác với tính atomic của phép `++` và biết xử lý data race bằng happens-before.

**Tài liệu tham khảo hiện hành:** [JLS 25 — Chapter 15, Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html), [JLS 25 — Chapter 17, Threads and Locks / Java Memory Model](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html), [Oracle Java SE 25 — HotSpot Performance Enhancements / Tiered Compilation](https://docs.oracle.com/en/java/javase/25/vm/java-hotspot-virtual-machine-performance-enhancements.html), [Java SE 25 — java command options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html), [OpenJDK JMH](https://github.com/openjdk/jmh). Nội dung tập trung vào ngữ nghĩa Java và cơ chế HotSpot/JIT vẫn được hỗ trợ; không dựa vào cờ hoặc hành vi đã lỗi thời.