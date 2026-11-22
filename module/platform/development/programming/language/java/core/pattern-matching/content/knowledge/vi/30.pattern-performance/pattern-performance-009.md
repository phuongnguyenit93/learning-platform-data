# Đánh đổi hiệu năng với khả năng đọc trong Java Pattern Matching

**Chủ đề:** Java Core Pattern Matching — Hiệu năng. Bài tập trung vào việc lựa chọn giữa `if-else`, `instanceof` type patterns, `switch` với record patterns và polymorphism trong **Java 21 trở lên**. Type patterns cho `instanceof` đã ổn định từ Java 16; record patterns (JEP 440) và pattern matching for `switch` (JEP 441) chính thức từ Java 21.

## 1. Đặt đúng câu hỏi: dễ đọc và nhanh có luôn đối lập không?

Khi gặp chuỗi phân nhánh theo kiểu dữ liệu, chúng ta có thể viết cùng một nghiệp vụ bằng nhiều cách:

- `instanceof` rồi cast thủ công theo kiểu Java cũ;
- `instanceof T value` để kiểm tra và ràng buộc type pattern;
- `switch` expression với type pattern hoặc record pattern;
- gọi phương thức polymorphic trên đối tượng, nếu hành vi thuộc về subtype.

Mục tiêu của tối ưu không phải làm đoạn code ngắn nhất, cũng không phải mặc định rằng cấu trúc dùng pattern mới sẽ chạy nhanh hơn. Một phương án tốt phải thỏa **tính đúng**, **khả năng bảo trì**, **đặc tính hiệu năng thực tế** và **khả năng kiểm thử**. Trong phần lớn trường hợp, rõ ràng và đúng đắn nên là mặc định; chỉ đánh đổi độ rõ ràng khi có dữ liệu đo cho thấy một đường chạy nóng thật sự cần tối ưu.

Đọc code dễ hơn cũng có giá trị kỹ thuật: phát hiện sớm nhánh thiếu, guard sai, null không được xử lý hoặc thay đổi không được cập nhật khi thêm subtype. Chi phí của những lỗi đó có thể lớn hơn vài nanosecond tiết kiệm được từ một micro-optimization chưa đo lường.

**Nguyên tắc:** Pattern matching là **công cụ diễn đạt và kiểm tra kiểu**. Nó không phải cam kết về thông lượng, latency, bộ nhớ hay tốc độ nhanh hơn mọi cách viết khác.

## 2. Các cách phân nhánh biểu diễn cùng nghiệp vụ

Xét một kiểu thao tác đóng:

~~~java
sealed interface Operation permits Add, Multiply, Reset {}

record Add(int left, int right) implements Operation {}
record Multiply(int left, int right) implements Operation {}
record Reset() implements Operation {}
~~~

Ta cần tính kết quả:

- Add trả tổng hai số.
- Multiply trả tích hai số.
- Reset trả 0.
- Đầu vào null trả -1 theo hợp đồng minh họa.

Tùy kiểu dữ liệu và lịch sử dự án, có ba cách thực hiện.

### 2.1. `instanceof` và cast thủ công

~~~java
static int legacy(Operation operation) {
    if (operation instanceof Add) {
        Add a = (Add) operation;
        return a.left() + a.right();
    } else if (operation instanceof Multiply) {
        Multiply m = (Multiply) operation;
        return m.left() * m.right();
    } else if (operation instanceof Reset) {
        return 0;
    }
    return -1;
}
~~~

Cách này hợp lệ nhưng lặp lại kiểm tra kiểu và cast. Người bảo trì phải kiểm tra xem cast có khớp với điều kiện `instanceof` không. `instanceof` trả false đối với null nên null rơi vào `return -1`.

### 2.2. Type patterns trong `instanceof`

~~~java
static int typed(Operation operation) {
    if (operation instanceof Add a) {
        return a.left() + a.right();
    } else if (operation instanceof Multiply m) {
        return m.left() * m.right();
    } else if (operation instanceof Reset) {
        return 0;
    }
    return -1;
}
~~~

**Ưu điểm đọc hiểu:** Biến `a` và `m` được ràng buộc ngay khi kiểm tra đúng kiểu; không còn ép kiểu thủ công. Đây thường là lựa chọn ít rủi ro khi muốn refactor một chuỗi if-else cũ và giữ nguyên hình dạng luồng điều khiển.

**Về tốc độ:** Việc bỏ cú pháp cast không tự chứng minh rằng thời gian chạy giảm. Trình biên dịch và JVM có thể đã tối ưu phần cast dư thừa trong mã cũ. Muốn kết luận cần đo các phiên bản trong cùng điều kiện, không suy từ số dòng Java nguồn.

### 2.3. `switch` expression với record patterns

~~~java
static int switched(Operation operation) {
    return switch (operation) {
        case Add(int left, int right) -> left + right;
        case Multiply(int left, int right) -> left * right;
        case Reset() -> 0;
        case null -> -1;
    };
}
~~~

`switch` tập hợp mọi biến thể vào một biểu thức trả kết quả. Record pattern như `Add(int left, int right)` vừa kiểm tra kiểu record, vừa trích các component. Nhờ `Operation` là sealed interface và cả ba subtype được bao phủ, không cần `default`. Nhánh `case null` bảo toàn chính sách null của hai bản if-else.

**Lợi ích về bảo trì:** Nếu thêm subtype permitted mới rồi biên dịch lại, `switch` expression thiếu case sẽ tạo lỗi exhaustiveness. Hai bản if-else vẫn có thể lặng lẽ trả -1 cho subtype đó. Đây là điểm đáng cân nhắc ngay cả khi benchmark cho thấy hai cách có tốc độ gần như nhau.

**Về tốc độ:** `switch` không được Java bảo đảm nhanh hơn `if-else`. Kết quả phụ thuộc loại selector, tập case, phiên bản JDK, tối ưu JIT, phân bố đầu vào và phần công việc bên trong từng nhánh.

## 3. Chương trình Java 21 hoàn chỉnh: kiểm tra tương đương hành vi

Ví dụ này **không tự nhận là benchmark hiệu năng**. Nó là bước đầu quan trọng hơn: xác nhận ba cách viết thực hiện cùng một hợp đồng trên nhiều tình huống.

Lưu toàn bộ vào tệp **PatternTradeoffDemo.java**:

~~~java
public class PatternTradeoffDemo {
    sealed interface Operation permits Add, Multiply, Reset {}

    record Add(int left, int right) implements Operation {}
    record Multiply(int left, int right) implements Operation {}
    record Reset() implements Operation {}

    static int legacy(Operation operation) {
        if (operation instanceof Add) {
            Add a = (Add) operation;
            return a.left() + a.right();
        } else if (operation instanceof Multiply) {
            Multiply m = (Multiply) operation;
            return m.left() * m.right();
        } else if (operation instanceof Reset) {
            return 0;
        }
        return -1;
    }

    static int typed(Operation operation) {
        if (operation instanceof Add a) {
            return a.left() + a.right();
        } else if (operation instanceof Multiply m) {
            return m.left() * m.right();
        } else if (operation instanceof Reset) {
            return 0;
        }
        return -1;
    }

    static int switched(Operation operation) {
        return switch (operation) {
            case Add(int left, int right) -> left + right;
            case Multiply(int left, int right) -> left * right;
            case Reset() -> 0;
            case null -> -1;
        };
    }

    public static void main(String[] args) {
        Operation[] operations = {
            new Add(2, 3),
            new Multiply(4, 5),
            new Reset(),
            null,
            new Add(-1, 1)
        };

        for (Operation operation : operations) {
            int before = legacy(operation);
            int withTypePatterns = typed(operation);
            int withSwitch = switched(operation);

            if (before != withTypePatterns || before != withSwitch) {
                throw new AssertionError("Different behavior");
            }

            System.out.println(
                    before + " | " + withTypePatterns + " | " + withSwitch);
        }
    }
}
~~~

Biên dịch và chạy với **JDK 21 hoặc mới hơn**:

~~~bash
javac PatternTradeoffDemo.java
java PatternTradeoffDemo
~~~

Kết quả chính xác:

~~~text
5 | 5 | 5
20 | 20 | 20
0 | 0 | 0
-1 | -1 | -1
0 | 0 | 0
~~~

**Diễn giải:** Cả ba cách đều trả kết quả giống nhau cho Add, Multiply, Reset, null và Add có toán hạng âm. Mỗi hàng là các giá trị **legacy | typed | switched**, không phải đơn vị thời gian hoặc điểm hiệu năng.

Vì đầu vào null xuất hiện trong mảng, chương trình dùng `Operation[]` thay vì `List.of(...)` (vốn không cho phép phần tử null). Việc không có `default` trong switched vẫn hợp lệ vì selector là sealed Operation và nhánh null được xử lý tường minh.

Đây là kiểm tra hành vi cho các mẫu đã thử, **không chứng minh mọi trạng thái đều tương đương**, và đặc biệt không chứng minh phương án nào nhanh hơn. Khi refactor mã thật, nên thêm test về ngoại lệ, guard, side effects và subtype tương lai.

## 4. Chi phí thực thi thực sự nằm ở đâu?

Mã nguồn chỉ mô tả logic; JVM HotSpot có bộ thông dịch, trình biên dịch JIT và nhiều tối ưu phụ thuộc profile. Vì thế, không nên gán một chi phí cố định chỉ từ hình dạng biểu thức Java.

### 4.1. Kiểm tra kiểu và cast

`instanceof` kiểm tra một object có phù hợp với kiểu hay không. Type pattern có thêm cơ chế ràng buộc biến trong source code, không đồng nghĩa tạo một object mới. Cast sau kiểm tra kiểu ở bản legacy cũng không đồng nghĩa nhất thiết có thêm một lần kiểm tra runtime đầy đủ sau khi JVM tối ưu.

Trong một hàm được gọi nhiều lần, JIT có thể tận dụng thông tin kiểu đã học. Khả năng tối ưu phụ thuộc cách code được biên dịch, mức độ polymorphic của đầu vào và các điều kiện trong hàm.

### 4.2. Record pattern và truy cập component

`case Add(int left, int right)` cần lấy hai component từ đối tượng Add thông qua cơ chế deconstruction của record. **Không có yêu cầu tạo record mới** chỉ vì pattern đó xuất hiện. Tuy nhiên, matching vẫn có các thao tác kiểm tra kiểu và truy cập component; với record pattern lồng nhau, việc trích xuất có thể sâu hơn.

Nếu record có accessor tùy chỉnh, accessor có thể chứa logic hoặc tác dụng phụ. Do đó, đừng khẳng định mọi deconstruction đều miễn phí, cũng đừng tự suy rằng việc dùng record pattern chắc chắn tạo allocation. Cần xem bytecode/profile và đo trên dữ liệu thật.

### 4.3. Switch dispatch và chuỗi if-else

Một chuỗi if-else kiểm tra từng điều kiện theo thứ tự, nhưng JIT có thể thay đổi cách thực thi tối ưu miễn giữ đúng ngữ nghĩa. Switch với pattern có cơ chế lựa chọn nhánh riêng, không mặc nhiên tương đương với switch trên integer hay enum ở mức mã máy.

Hiệu quả phụ thuộc vào **đầu vào phổ biến**. Nếu 99% giá trị là Add và nhánh Add đứng đầu, một chuỗi if-else ngắn có thể hoạt động tốt. Nếu đầu vào đa dạng, có nhiều subtype và nhiều nhánh, chi phí có thể thay đổi. Không có một ngưỡng số case cố định khiến switch luôn nhanh hơn.

### 4.4. Điều kiện khi khớp case

Một guard như:

~~~java
// Chỉ minh họa nhánh switch cho record Add.
case Add(int left, int right) when left > 0 && right > 0 ->
        left + right;
case Add(int left, int right) ->
        0;
~~~

thực hiện thêm phép so sánh và có nhánh dự phòng. Guard có thể giúp code thể hiện quy tắc rõ hơn nhưng không tự động làm code nhanh hơn. Đồng thời, case cụ thể có guard phải đứng trước case tổng quát để tránh dominance.

Nếu cùng một kiểm tra đắt tiền được lặp ở nhiều guard, có thể cân nhắc chuẩn hóa dữ liệu hoặc tách phương thức mang tên rõ. Nhưng chỉ tối ưu khi test đã xác nhận rằng kết quả, thứ tự kiểm tra và hành vi ngoại lệ không thay đổi.

### 4.5. Công việc bên trong case thường quan trọng hơn

Nếu một case thực hiện truy vấn database, phân tích JSON lớn, đọc file hay gọi mạng, chi phí điều phối phân nhánh có thể nhỏ so với I/O. Trong trường hợp ấy, ưu tiên thời gian truy vấn, batching, cache hợp lệ hoặc giảm số cuộc gọi có thể đem lại tác động lớn hơn thay cú pháp `instanceof` thành `switch`.

Ngược lại, trong một hàm xử lý hàng triệu sự kiện nhỏ mỗi giây, phân nhánh và truy cập component có thể là phần đáng đo. **Chỉ có profile mới cho biết đường chạy nào thực sự nóng.**

## 5. Khả năng đọc có những lợi ích hiệu năng gián tiếp nào?

Một code path dễ hiểu giúp người phát triển tối ưu **đúng chỗ**:

| Tiêu chí | if-else với type pattern | Switch với type/record pattern |
| --- | --- | --- |
| Hai hoặc ba kiểm tra độc lập | Thường rất dễ đọc | Có thể hơi dư cấu trúc |
| Phân loại nhiều subtype và cùng trả giá trị | Có thể dài hoặc lặp return | Các nhánh đặt cùng một nơi, dễ rà soát |
| Mỗi subtype có dữ liệu record cần trích | Dùng accessor sau khi ràng buộc biến | Record pattern diễn đạt shape trực tiếp |
| Cần giữ null giống if-else cũ | `instanceof` tự false cho null | Cần quyết định `case null` tường minh |
| Miền kiểu sealed, muốn bắt thiếu subtype | Không tự bắt buộc đầy đủ | Switch expression không default kiểm tra exhaustiveness |
| Logic mỗi nhánh dài/nhiều side effect | Có thể tách hàm/giữ if-else | Nên tách body thành phương thức chuyên trách |
| Đường chạy nóng đã benchmark khác biệt | Có thể là lựa chọn phù hợp | Có thể là lựa chọn phù hợp |
| Tối ưu mà chưa đo đạc | Không kết luận nhanh hơn | Không kết luận nhanh hơn |

Việc **exhaustive switch** bắt compiler nhắc khi thêm subtype có giá trị vì ngăn lỗi vận hành và giảm gánh nặng code review. Ngược lại, việc dồn record pattern lồng quá sâu vào một case duy nhất có thể khiến lập luận về logic trở nên khó. Độ rõ ràng, khả năng phát hiện lỗi và tốc độ thực thi phải được cân đối theo hoàn cảnh.

## 6. Khi nào polymorphism rõ hơn switch?

Giả sử mọi subtype của Operation đều có trách nhiệm tính giá trị **từ chính dữ liệu của nó**. Có thể thiết kế interface có hành vi:

~~~java
// Minh họa thiết kế thay thế; không ghép với mã ở mục 3.
sealed interface Calculable permits Sum, Product {
    int evaluate();
}

record Sum(int left, int right) implements Calculable {
    @Override
    public int evaluate() {
        return left + right;
    }
}

record Product(int left, int right) implements Calculable {
    @Override
    public int evaluate() {
        return left * right;
    }
}
~~~

Caller chỉ cần **value.evaluate()**. Điều này có thể hợp lý nếu `evaluate` là hành vi cốt lõi của từng kiểu và thường thêm subtype mới hơn là thêm thao tác mới.

Trong khi đó, nếu cùng dữ liệu phải được xử lý bằng nhiều operation độc lập (ví dụ audit, báo cáo, chuyển đổi, tính điểm), các consumer dùng switch trên sealed hierarchy có thể rõ hơn, tránh đặt mọi nhu cầu bên ngoài vào domain model.

**Về hiệu năng:** lời gọi polymorphic không mặc nhiên chậm. JIT có thể tối ưu hoặc inline lời gọi dựa trên profile, nhưng cũng không có bảo đảm luôn tốt hơn switch. Đừng thay một thiết kế domain rõ ràng bằng hàng loạt switch chỉ để tránh một lời gọi method ảo mà chưa có số liệu.

## 7. Microbenchmark đúng cách: đo trước khi kết luận

Đo trực tiếp một vòng lặp Java bằng `System.nanoTime()` rồi lấy một kết quả duy nhất là cách dễ cho kết luận sai. JVM cần **warmup** và có thể biên dịch lại mã khi đã thu thập profile; GC, scheduler, tối ưu dead-code elimination, constant folding và biến thiên của phân bố dữ liệu làm thời gian thay đổi đáng kể.

Đối với so sánh `legacy`, `typed` và `switched`, công cụ phổ biến là **JMH (Java Microbenchmark Harness)**. JMH là thư viện riêng, **không nằm sẵn trong JDK**; muốn chạy cần cấu hình dependency/annotation processor và benchmark project.

Một thiết kế thử nghiệm có ý nghĩa:

1. **Cố định hành vi:** ba phương án trả cùng giá trị cho cùng input; chạy kiểm thử trước benchmark.
2. **Sinh dữ liệu trước vùng đo:** đừng tính luôn chi phí `new Add(...)`, tạo mảng, println hay tạo String nếu mục tiêu chỉ là chi phí phân nhánh.
3. **Dùng nhiều phân bố subtype:** ví dụ 90% Add, cân bằng ba subtype và dữ liệu gây guard false; mỗi phân bố cho một kết quả khác nhau.
4. **Warmup, measurement, forks:** chạy nhiều lần độc lập để tránh đánh giá quá cao một kết quả tình cờ.
5. **Ngăn compiler loại bỏ công việc:** trả kết quả cho benchmark framework hoặc dùng `Blackhole` phù hợp.
6. **Chọn metric đúng:** throughput hoặc average time, đồng thời xem allocation, GC và CPU profile nếu chúng ảnh hưởng hệ thống.
7. **Kiểm soát môi trường:** cùng phiên bản JDK, JVM flags, phần cứng, cấu hình GC và tải nền; không so các lần chạy trên cấu hình khác nhau.
8. **Báo phân tán kết quả:** xem sai số/khoảng tin cậy; chênh lệch nhỏ có thể nằm trong nhiễu đo.

### Khung JMH minh họa

Đoạn sau là **mã minh họa phụ thuộc thư viện JMH**, không phải chương trình độc lập chỉ cần JDK. Nó dùng các phương thức của class `PatternTradeoffDemo` ở mục 3; cần project đã cấu hình JMH. Mẫu dữ liệu được tạo trong setup thay vì tạo ở mỗi lần đo.

~~~java
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class PatternBenchmark {
    private PatternTradeoffDemo.Operation[] samples;
    private int index;

    @Setup(Level.Trial)
    public void setup() {
        samples = new PatternTradeoffDemo.Operation[] {
            new PatternTradeoffDemo.Add(2, 3),
            new PatternTradeoffDemo.Multiply(4, 5),
            new PatternTradeoffDemo.Reset()
        };
        index = 0;
    }

    private PatternTradeoffDemo.Operation next() {
        PatternTradeoffDemo.Operation sample = samples[index];
        index = (index + 1) % samples.length;
        return sample;
    }

    @Benchmark
    public int legacy() {
        return PatternTradeoffDemo.legacy(next());
    }

    @Benchmark
    public int typed() {
        return PatternTradeoffDemo.typed(next());
    }

    @Benchmark
    public int switched() {
        return PatternTradeoffDemo.switched(next());
    }
}
~~~

Cách bố trí này chỉ là **khung thử nghiệm**. Phần `next()` và phép modulo là chi phí chung được đo kèm với dispatch; benchmark rất nhỏ có thể bị phần chi phí chung làm mờ chênh lệch. Phải thiết kế baseline và thử nhiều mẫu phân bố trước khi suy ra hiệu năng của hệ thống thật. Một benchmark tốt không chỉ “chạy được”: nó phải đo đúng giả thuyết.

**Không có con số thời gian cố định trong bài này** vì chỉ một con số chạy trên máy khác không phản ánh JDK, phần cứng, tải thực tế hay độ phức tạp của case tại ứng dụng.

## 8. Những lỗi phổ biến khi đo pattern matching

### 8.1. So các đoạn code không tương đương

Ví dụ, bản switch kiểm tra thêm guard còn bản if-else không kiểm tra; hoặc bản record pattern trích hai component trong khi bản cũ chỉ kiểm tra kiểu. Kết quả thời gian khi đó không chỉ phản ánh cú pháp phân nhánh.

**Cách tránh:** test hành vi giống nhau và bảo đảm cùng logic, cùng input, cùng tác dụng phụ trước khi đo.

### 8.2. Dùng chỉ một đối tượng cố định

~~~java
// Không phải benchmark đáng tin:
Operation input = new Add(2, 3);
for (int i = 0; i < 1_000_000; i++) {
    switched(input);
}
~~~

Mã này rất dễ bị optimizer tối ưu hoặc kết quả không được sử dụng. Nó cũng đại diện cho một nhánh duy nhất chứ không phản ánh hệ thống có nhiều subtype. Nếu cần đo nhánh Add riêng, hãy định nghĩa benchmark cố ý dành cho nhánh đó; nếu cần đánh giá workload thực, phải dùng dữ liệu có phân bố hợp lý.

### 8.3. So thời gian bằng một lần chạy

Một lần `nanoTime` trước và sau vòng lặp có thể chứa chi phí khởi động, JIT, GC hoặc tác động của tiến trình khác. Một kết quả duy nhất không đủ cơ sở để tuyên bố phương án nào thắng.

### 8.4. Bỏ quên allocation và bộ nhớ

Nếu một phương án trong case tạo String, collection hoặc đối tượng trung gian, chi phí của chúng có thể lấn át dispatch. Khi mục tiêu chỉ là so sánh pattern, loại phần công việc không tương đương. Khi mục tiêu là end-to-end, **giữ** các allocation thực tế và đo cả GC vì đó chính là chi phí hệ thống quan tâm.

### 8.5. Nhầm kết quả microbenchmark với kết quả ứng dụng

Một hàm có thể nhanh hơn một ít trong microbenchmark nhưng không cải thiện latency end-to-end nếu thời gian chủ yếu dùng cho I/O. Ngược lại, một hàm rất nhỏ trong đường chạy xử lý hàng tỷ bản ghi có thể đáng quan tâm. Cần dùng profiler để xác nhận độ nóng và thử nghiệm tích hợp dưới tải gần thực tế.

## 9. Guard, mẫu lồng và khả năng đọc

Pattern matching rất linh hoạt, nhưng diễn đạt mọi điều kiện trong một case duy nhất không phải lúc nào cũng tốt.

~~~java
// Phác thảo khi chọn nhánh Add: guard phải đứng trước case tổng quát.
case Add(int left, int right) when left > 0 && right > 0 ->
        left + right;
case Add(int left, int right) ->
        0;
~~~

Ở đây hai case khác nhau có **ý nghĩa nghiệp vụ**. Nhánh có guard chỉ khớp khi cả hai số dương, nên cần case không guard để bao phủ Add còn lại.

Nếu điều kiện dài, có nhiều lời gọi method hoặc side effects, nên cân nhắc tách:

~~~java
// Đoạn trích: giả định Operation, Add đã được khai báo.
static int checkedAdd(Add add) {
    return add.left() > 0 && add.right() > 0
            ? add.left() + add.right()
            : 0;
}

static int calculate(Operation operation) {
    return switch (operation) {
        case Add add -> checkedAdd(add);
        case Multiply(var left, var right) -> left * right;
        case Reset() -> 0;
        case null -> -1;
    };
}
~~~

Khi đó `switch` tập trung vào **lựa chọn subtype**, còn checkedAdd diễn đạt **quy tắc nghiệp vụ** bằng một tên có nghĩa. Điều này không mặc nhiên chậm hơn: JVM có thể inline method nhỏ trong những điều kiện phù hợp, nhưng việc inline và chi phí thực tế phải được đo, không thể khẳng định tuyệt đối.

Tương tự, record pattern lồng sâu như `Route(Start(...), End(...))` có thể giúp code ngắn, nhưng khi có nhiều lớp lồng hoặc kiểm tra null phức tạp, tên biến và phương thức tách riêng thường dễ review hơn. Đừng đặt “ít token nguồn” lên trên khả năng giải thích logic.

## 10. Lựa chọn theo đặc điểm bài toán

Một cách ra quyết định thực tế:

| Tình huống | Ưu tiên ban đầu | Điều cần đo nếu là hot path |
| --- | --- | --- |
| Hai subtype, vài điều kiện đơn giản | `instanceof` type patterns | Kiểm tra nhánh và phân bố đầu vào |
| Nhiều subtype của sealed hierarchy cùng trả giá trị | `switch` expression exhaustive | Dispatch, deconstruction, branch behavior |
| Cần phân rã record rõ ràng | Record patterns có độ sâu vừa phải | Chi phí accessor/guard và allocation liên quan |
| Hành vi thuộc tự nhiên về từng subtype | Polymorphism | Profile khả năng inline/dispatch và số call |
| Một case làm I/O nặng | Cách viết rõ ràng, tách dịch vụ | I/O, batching, timeout, serialization |
| Logic nhiều nhánh với side effects | Phương thức có tên hoặc switch statement | End-to-end latency và correctness |
| Thay đổi subtype thường xuyên | Xem lợi ích exhaustive switch so với polymorphism | Chi phí bảo trì và regression, không chỉ CPU |
| Kết quả đo nhiễu hoặc chênh rất nhỏ | Giữ phiên bản dễ đọc nhất | Tăng chất lượng benchmark trước khi quyết định |

Các lựa chọn không loại trừ nhau. Một method có thể dùng **switch với type pattern** thay vì record pattern; một nhánh switch có thể gọi **phương thức polymorphic**; và một hệ thống có thể dùng sealed hierarchy ở boundary trong khi entity có hành vi riêng bên trong.

## 11. Quy trình tối ưu dựa trên bằng chứng

Trước khi đổi một đoạn code dễ hiểu thành một biểu thức khó đọc hơn với mục tiêu tăng hiệu năng:

1. **Định nghĩa vấn đề:** cần giảm CPU, throughput, p95/p99 latency hay allocation? Gắn mục tiêu với một yêu cầu thực.
2. **Đo tổng thể và profile:** xác nhận phần phân nhánh thực sự chiếm tỷ trọng đáng kể; nếu không, tối ưu chỗ khác có thể hiệu quả hơn.
3. **Khóa hành vi hiện tại bằng test:** kiểm tra từng subtype, null, giá trị biên của guard, exception và side effects.
4. **Tạo ít nhất một phiên bản rõ ràng:** lựa chọn type pattern hoặc switch phù hợp ngữ nghĩa, không tối ưu bằng trực giác.
5. **Benchmark đúng cách:** dùng JMH cho microbenchmark và thử dưới workload đại diện cho ứng dụng.
6. **Phân tích nhiều chỉ số:** cân đối throughput, latency, GC/allocation, mức độ phức tạp và khả năng bảo trì.
7. **Chỉ chấp nhận đánh đổi khi có lợi ích đáng kể và lặp lại được:** ghi nhận JDK, môi trường và kết quả; tránh quyết định từ số đo đơn lẻ.
8. **Giữ regression test:** refactor nhằm tối ưu vẫn phải giữ kết quả và hợp đồng lỗi.
9. **Đánh giá lại khi nâng cấp JDK hoặc workload thay đổi:** tối ưu compiler/JIT và phân bố subtype có thể khiến kết quả cũ không còn đúng.

Lưu ý về mục tiêu đo: nếu chỉ kiểm tra *dispatch*, benchmark không nên vô tình đo việc tạo dữ liệu và in ra console. Nếu mục tiêu là trải nghiệm end-to-end, lại không nên loại bỏ công việc thật của hệ thống.

## 12. Những hiểu lầm cần tránh

**“Pattern matching luôn nhanh hơn cast.”** Không có bảo đảm. Lợi ích thường rõ rệt nhất là an toàn kiểu và giảm lặp mã.

**“Switch luôn chạy nhanh hơn if-else.”** Không có bảo đảm. Tốc độ phụ thuộc kiểu selector, nhánh, dữ liệu và JVM; cần benchmark.

**“Record pattern tạo bản sao record.”** Không phải là hệ quả bắt buộc của record pattern. Nó giải cấu trúc đối tượng đang được khớp; không có lý do tự động kết luận sẽ tạo một record mới.

**“Sealed giúp mọi trường hợp nhanh hơn.”** Sealed đem lại một tập subtype có thể phân tích tĩnh, hỗ trợ exhaustiveness và một số cơ hội tối ưu, nhưng không tự quy định hiệu năng runtime.

**“Không có default thì null tự được xử lý.”** Không. Một switch exhaustive theo subtype vẫn cần chính sách null phù hợp; nếu không có case null, null có thể dẫn tới NullPointerException.

**“Viết gọn hơn nghĩa là dễ đọc hơn.”** Một record pattern nhiều cấp với guard dài có thể khó hiểu hơn một phương thức riêng có tên tốt.

**“Nếu microbenchmark nhanh thì chắc chắn production nhanh.”** Không. Cần kiểm tra tỷ lệ thời gian thực của code path trong ứng dụng và điều kiện workload đại diện.

**“Có thể bỏ test vì compiler đã kiểm tra exhaustive.”** Compiler không biết kết quả phép toán hoặc nghiệp vụ đúng hay sai. Test vẫn cần cho guard, số âm, overflow nếu quan trọng, null và tác dụng phụ.

## 13. Checklist code review

- [ ] Các phương án có trả **kết quả tương đương** trên cùng miền dữ liệu không?
- [ ] Dạng phân nhánh hiện tại có **dễ hiểu** hơn cho người bảo trì không?
- [ ] Nếu chuyển từ `instanceof` sang `switch`, null có đổi hành vi không?
- [ ] Các nhánh subtype có đầy đủ, không bị dominance và có xử lý guard false đúng không?
- [ ] Có record pattern lồng sâu hoặc accessor có chi phí/side effect cần chú ý không?
- [ ] Có dùng default che thiếu subtype mới trong sealed hierarchy không?
- [ ] Nếu được gọi rất nhiều lần, đã profile để xác nhận đây là **hot path** chưa?
- [ ] Benchmark đã warmup, dùng input đại diện, ngăn dead-code elimination, có nhiều forks và báo sai số chưa?
- [ ] Có đo allocation, GC, latency end-to-end nếu các chỉ số đó mới thực sự quan trọng không?
- [ ] Có tránh một tối ưu nhỏ khiến code khó đọc, khó test và dễ sai hơn không?

**Kết luận:** Trong Java Pattern Matching, hãy ưu tiên **mã rõ, kiểm tra kiểu an toàn và hành vi được chứng minh**. `instanceof` type patterns thường phù hợp refactor nhỏ; `switch` exhaustive mạnh về tính đầy đủ của sealed hierarchy; record patterns thuận tiện khi cần deconstruction; polymorphism phù hợp hành vi gắn với subtype. Chỉ đánh đổi khả năng đọc lấy tốc độ khi **profile và benchmark trong điều kiện phù hợp** cho thấy lợi ích đáng kể, tái lập được và đủ để bù chi phí bảo trì.