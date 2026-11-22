# Pattern matching có thay thế mọi tối ưu không? (Java 21)

## 1. Câu trả lời ngắn và mục tiêu học tập

**Không. Pattern matching trong Java là công cụ diễn đạt và kiểm tra cấu trúc dữ liệu an toàn, rõ ràng hơn; nó không tự thay thế việc lựa chọn thuật toán, cấu trúc dữ liệu, tổ chức I/O, giảm cấp phát, tối ưu truy vấn hay đo đạc hiệu năng.**

Ví dụ thay:

```java
if (value instanceof String) {
    String text = (String) value;
    return text.strip();
}
```

bằng:

```java
if (value instanceof String text) {
    return text.strip();
}
```

giúp loại bỏ thao tác cast thủ công và tránh việc biến `text` bị sử dụng sai đường đi của chương trình. Nhưng từ hai đoạn trên không thể suy ra bản thứ hai **luôn chạy nhanh hơn**, tiêu thụ ít bộ nhớ hơn, hay đã giải quyết mọi nút thắt.

Trong Java 21, pattern matching còn xuất hiện trong `switch` và record patterns:

```java
return switch (value) {
    case String s when s.isBlank() -> "blank";
    case String s -> "text:" + s.strip();
    case Integer n -> "number:" + n;
    case null -> "null";
    default -> "other";
};
```

Đây là **một cách mô tả nhánh điều khiển rõ ràng**, không phải cam kết rằng JVM tạo ra mã máy tối ưu nhất cho mọi dữ liệu.

Sau bài học, bạn có thể:

- Phân biệt lợi ích về **readability/type safety** với những cải thiện hiệu năng **đã đo được**.
- Hiểu tương tác giữa `javac`, bytecode, HotSpot/JIT và cách trình biên dịch tối ưu theo điều kiện runtime.
- Nhận diện chi phí từ `when` guard, record deconstruction/accessor, regex, allocation, bộ nhớ, I/O và cấu trúc dữ liệu.
- Biết tại sao đổi thuật toán có thể mang lại lợi ích lớn hơn đổi cú pháp.
- Thiết kế thí nghiệm **JMH** và đo hệ thống thật mà không ngộ nhận kết quả.
- Chứng minh bản refactor giữ nguyên hành vi trước khi so hiệu năng.

**Phiên bản:** `instanceof` patterns chuẩn từ Java 16; pattern matching cho `switch` (JEP 441) và record patterns (JEP 440) chuẩn từ Java 21. Các ví dụ đầy đủ dùng `javac --release 21`, không cần preview.

## 2. Pattern matching tối ưu điều gì trong mã nguồn?

Pattern matching chủ yếu giúp trình bày các phép kiểm tra và tách giá trị theo kiểu/cấu trúc:

1. **Type pattern:** `obj instanceof String s` kiểm tra đối tượng là `String` rồi bind biến `s`.
2. **Pattern switch:** `case String s -> ...` phân loại các giá trị theo pattern, có thể thêm `when` để lọc bằng điều kiện nghiệp vụ.
3. **Record pattern:** `case Point(var x, var y) -> ...` tách component của một record, có thể lồng với record khác.
4. **Flow scoping:** biến pattern chỉ khả dụng trên đường đi mà compiler chứng minh việc match thành công.

Các lợi ích thường quan sát được khi review: ít cast lặp, ít nhánh lồng nhau, ranh giới kiểu tường minh, lỗi dominance hoặc thiếu nhánh có thể được compiler phát hiện. **Đây là lợi ích chất lượng thiết kế và tính đúng đắn**, không phải bằng chứng hiệu năng tự thân.

Hai câu cần phân biệt:

- "Mã mới **ngắn hơn/dễ đọc hơn**" — có thể xác nhận từ source và review.
- "Mã mới **nhanh hơn/ít allocation hơn**" — cần đo trên workload đại diện, sau khi bảo đảm hai bản cho kết quả và side effects tương đương.

Nếu không có benchmark, câu đúng thường là: *Pattern giúp mô tả bài toán rõ hơn; hiệu năng có thể tương đương, tốt hơn hoặc kém hơn tùy cách dùng, workload và JVM.*

## 3. Từ cú pháp Java đến tốc độ chạy: còn nhiều lớp

Một chương trình Java thường đi qua các lớp:

```text
Mã Java -> javac -> bytecode (.class)
                  -> JVM/HotSpot -> interpreter/JIT -> mã máy
                  -> CPU, bộ nhớ, GC, hệ điều hành, I/O
```

Pattern matching là cú pháp/semantics ở **tầng ngôn ngữ**. `javac` biên dịch thành bytecode hợp lệ; HotSpot có thể profiling, inline method, tối ưu check/cast, khử một số allocation hoặc chuyên biệt đường thực thi nóng. Kết quả phụ thuộc phiên bản JDK, JVM flags, loại dữ liệu, lịch sử warm-up và nội dung phương thức.

### 3.1. "Bớt cast" không tự đồng nghĩa "bớt chi phí CPU"

Đoạn legacy:

```java
if (value instanceof Integer) {
    Integer number = (Integer) value;
    return number + 1;
}
```

và đoạn refactor:

```java
if (value instanceof Integer number) {
    return number + 1;
}
```

đều có yêu cầu kiểm tra kiểu và đọc giá trị để tính toán. JVM có thể khai thác cùng thông tin kiểu của nhánh `instanceof` ở cả hai cách. Không thể lấy số dòng mã làm thước đo chu kỳ CPU hay khẳng định loại bỏ hoàn toàn một instruction cast ở runtime.

**Điểm học tập:** Bytecode có thể khác và JIT có thể tối ưu; sự tương đồng về semantics không bảo đảm instruction count bằng nhau trong mọi hoàn cảnh. Đừng tuyên bố thắng lợi chỉ dựa vào việc xóa một cast bằng cú pháp mới.

### 3.2. `switch` có pattern không mặc nhiên nhanh hơn chuỗi `if/else`

```java
static String classify(Object value) {
    if (value instanceof String s) return "string";
    if (value instanceof Integer n) return "integer";
    return "other";
}
```

và:

```java
static String classifySwitch(Object value) {
    return switch (value) {
        case String s -> "string";
        case Integer n -> "integer";
        case null -> "other";
        default -> "other";
    };
}
```

có thể cho cùng kết quả trên miền input đã xác định. Tuy nhiên, cách JVM triển khai điều phối nhánh, mức inline, distribution của các loại giá trị và profile của chương trình có thể khác nhau. **Không có quy tắc chung** rằng một kiểu câu lệnh luôn nhanh hơn kiểu kia.

Đừng quên tương đương `null`: `instanceof` với `null` trả `false`, còn `switch` theo pattern muốn dùng fallback cũ thường cần `case null`. Nếu lỡ đổi exception hay kết quả, benchmark đang so **hai chương trình làm công việc khác nhau**.

## 4. Chi phí của nhánh, guard và thứ tự kiểm tra

Một pattern có thể match nhiều kiểu/chỗ trong cấu trúc. Trong `switch`, Java xét các nhãn `case` theo logic lựa chọn nhánh; guard `when` chỉ được đánh giá khi pattern tương ứng match.

```java
return switch (value) {
    case String s when s.isBlank() -> "blank";
    case String s when expensiveBusinessRule(s) -> "special";
    case String s -> "normal";
    case null -> "null";
    default -> "other";
};
```

`expensiveBusinessRule(s)` là helper boolean giả định. Ví dụ này minh họa cú pháp, không phải một chương trình độc lập.

### 4.1. Guard có thể là phần tốn thời gian nhất

Nếu một guard gọi regex, tra cứu cấu trúc dữ liệu lớn, API bên ngoài hoặc đọc dữ liệu từ đĩa, chi phí đó có thể **lớn hơn rất nhiều** chi phí kiểm tra kiểu. Thay `if (x instanceof String)` bằng `case String s` không làm guard tự biến thành phép toán rẻ.

Trong code được kiểm soát, có thể đặt một kiểm tra **rẻ và an toàn** trước kiểm tra đắt, để khai thác `&&` short-circuit:

```java
case String s when !s.isBlank() && isEligibleByRules(s) -> "eligible";
```

Nhưng **không đảo thứ tự tùy tiện** nếu rule có side effect, ném exception hoặc tính trạng thái khác. Bảo toàn hành vi quan trọng hơn tối ưu suy đoán.

### 4.2. Thứ tự case không chỉ ảnh hưởng performance

Đặt nhánh type pattern rộng trước nhánh subtype hẹp có thể bị compiler từ chối vì **dominance**:

```java
// CỐ Ý SAI trong Java 21:
return switch (value) {
    case CharSequence c -> "sequence";
    case String s -> "string"; // bị dominated
    default -> "other";
};
```

Đặt `String` trước `CharSequence` mới hợp lệ. Trong những cấu trúc có guards, thay đổi thứ tự có thể làm thay đổi **kết quả nghiệp vụ**. Tối ưu thứ tự case phải ưu tiên nghĩa đúng và quy tắc dominance, sau đó mới đo hiệu năng.

### 4.3. Phân bố dữ liệu rất quan trọng

Một workload gồm 99% `String` và 1% `Integer` có hành vi nhánh khác workload phân bố đều giữa nhiều kiểu. Branch prediction và profiling của JVM/CPU có thể tác động đến thời gian chạy. Benchmark chỉ dùng một kiểu input cố định **không đại diện** nếu production có nhiều kiểu xuất hiện với tần suất khác.

Không áp đặt một "thứ tự case tối ưu" cố định cho mọi hệ thống. Hãy giữ trật tự đúng và dễ hiểu, kiểm tra với phân bố input thực tế, và chỉ đổi thiết kế khi bằng chứng đủ mạnh.

## 5. Record patterns: tiện lợi có thể mang thêm accessor work

Record pattern không chỉ kiểm tra kiểu ngoài; nó còn **đọc component qua accessor** để match mẫu lồng nhau.

```java
record Point(int x, int y) {}
record Box(Point point) {}

boolean justType = obj instanceof Box;
boolean nested = obj instanceof Box(Point(var x, var y));
```

Cả hai đoạn là minh họa trong phạm vi có biến `obj` và record đã khai báo. Nhánh thứ hai cần truy cập component `Box.point()` rồi deconstruct `Point`; nhánh đầu chỉ cần kiểm tra kiểu `Box`. Vậy nếu chỉ muốn biết `obj` có phải `Box` hay không, nested pattern là **công việc không cần thiết về mặt biểu đạt**.

### 5.1. Custom accessor và side effect

Java cho phép record override accessor:

```java
record Metered(int value) {
    static int reads;
    @Override public int value() {
        reads++;
        return value;
    }
}
record Envelope(Metered measurement) {}
```

Khi dùng:

```java
static boolean typeOnly(Object input) {
    return input instanceof Envelope;
}

static boolean deconstruct(Object input) {
    return input instanceof Envelope(Metered(var n)) && n >= 0;
}
```

Với `new Envelope(new Metered(7))`:

- `typeOnly` trả true và không cần gọi `Metered.value()`.
- `deconstruct` đọc nested value, nên `Metered.value()` có thể chạy; trong demo, counter tăng một lần.
- Nếu `measurement == null`, nested `Metered(...)` không match, vì **record pattern không match null**.
- Nếu accessor có side effect hoặc ném exception, việc đổi type check thành deconstruction có thể đổi semantics và chi phí.

Không nên kết luận record pattern luôn "chậm"; khi nghiệp vụ **cần** component, deconstruction là cách biểu đạt phù hợp và JVM có thể tối ưu trường hợp thông thường. Điểm chính là **tránh tách dữ liệu không sử dụng**, và không tự suy ra cấu trúc ngắn hơn luôn có ít thao tác hơn.

### 5.2. Null semantics còn quan trọng hơn tốc độ

`null instanceof Box(Point(var x, var y))` là `false`, nhưng component reference `null` và nested type patterns có quy tắc match riêng. Khi chuyển từ `if` sang `switch` hoặc từ type pattern sang nested record pattern, test `null` ở selector và từng cấp record để tránh thay đổi behavior hoặc gây ngoại lệ. **Benchmark phải được thực hiện trên code đúng.**

## 6. Allocation, GC và escape analysis

Sử dụng pattern matching **không tự xóa** các object vốn được tạo bởi phần logic bên trong nhánh. Ví dụ:

```java
case String s -> new StringBuilder(s).reverse().toString();
```

Về mặt mã nguồn, vẫn có logic tạo `StringBuilder` và kết quả chuỗi. JVM có thể tối ưu một phần trong những trường hợp cụ thể, nhưng không có cam kết của ngôn ngữ rằng tất cả allocation sẽ biến mất. Nếu code nằm trên hot path, cần kiểm tra **allocation rate**, **GC pressure** và bộ nhớ thực tế.

Một số nguồn allocation thường đáng kiểm tra:

- Chuỗi trung gian do concat/format/regex.
- Tạo collection tạm, boxing/unboxing, wrapper object.
- Tạo matcher hoặc exception liên tục trong nhánh có tần suất lớn.
- Object mapping/serialization, DTO và records mới.
- Lazy vs eager computation khi các guard có chi phí khác nhau.

**Phân biệt record pattern và record construction:** `case Point(var x, var y)` phân rã một object `Point` đã tồn tại; riêng hành động match **không mặc nhiên xây một `Point` mới**. Nhưng code trong nhánh có thể tạo object mới, hoặc runtime thực hiện công việc khác tùy JIT. Không tính số allocation chỉ bằng cách đếm dấu ngoặc trong pattern.

### 6.1. Escape analysis không phải lời hứa

HotSpot có thể thực hiện escape analysis và scalar replacement ở một số trường hợp. Hiệu quả phụ thuộc việc method có được inline không, object có "escape" qua API khác không, profiling và phiên bản runtime. Không thể kết luận từ việc dùng record pattern rằng allocation đã được khử; đo bằng công cụ profiling/benchmark thích hợp.

## 7. Ví dụ thực dụng: tái sử dụng compiled regex thay vì đổi cú pháp

So sánh hai cách kiểm tra cùng quy tắc mã định danh "hai chữ in hoa và ba chữ số":

```java
static boolean slowRegex(String text) {
    return text != null && text.matches("[A-Z]{2}[0-9]{3}");
}
```

và:

```java
private static final java.util.regex.Pattern CODE_PATTERN =
        java.util.regex.Pattern.compile("[A-Z]{2}[0-9]{3}");

static boolean cachedRegex(String text) {
    return text != null && CODE_PATTERN.matcher(text).matches();
}
```

Java API xác định `String.matches(regex)` có kết quả tương đương `Pattern.matches(regex, string)`. Dùng `Pattern` biên dịch sẵn giúp **tránh việc biên dịch lại biểu thức chính quy ở mỗi lần gọi**, là tối ưu cần cân nhắc khi regex cố định và gọi nhiều lần.

**Không suy diễn** từ đó rằng cách thứ hai luôn nhanh hơn cho mọi input/quy mô: xây dựng `Matcher` vẫn có chi phí; JIT, số lần gọi, cache và dữ liệu ảnh hưởng kết quả. Hãy benchmark khi performance thực sự quan trọng.

`Pattern` sau khi biên dịch là bất biến và có thể chia sẻ an toàn; `Matcher` là đối tượng có trạng thái và **không được chia sẻ đồng thời** giữa các thread nếu không đồng bộ thích hợp. Vì vậy thường tạo matcher mới cho từng lần dùng, không cố dùng một `static Matcher` để "loại allocation" rồi sinh race condition.

**Mối liên hệ với pattern matching:** Việc đặt code kiểm tra regex trong `case String s when ...` vẫn có cùng chi phí nghiệp vụ cần xem xét. Cải thiện có thể nằm ở **tái sử dụng regex** chứ không phải thay `if` bằng `switch`.

## 8. Tối ưu thuật toán và cấu trúc dữ liệu quan trọng hơn thay syntax

Giả sử cần phát hiện phần tử trùng trong một danh sách. Dùng vòng lặp so từng cặp:

```java
static boolean quadraticDuplicate(List<String> values) {
    for (int i = 0; i < values.size(); i++) {
        for (int j = i + 1; j < values.size(); j++) {
            if (java.util.Objects.equals(values.get(i), values.get(j))) {
                return true;
            }
        }
    }
    return false;
}
```

Với `ArrayList`/danh sách có truy cập chỉ số O(1), thuật toán này có thể cần số phép so sánh tăng theo **O(n²)** trong trường hợp xấu nhất không có phần tử trùng. Không có pattern `instanceof`/`switch` nào tự đổi độ phức tạp đó.

Một cách khác:

```java
static boolean hashedDuplicate(List<String> values) {
    return new java.util.HashSet<>(values).size() != values.size();
}
```

Với `hashCode`/`equals` đúng hợp đồng và phân bố hash phù hợp, cách dùng `HashSet` thường có **thời gian trung bình O(n)** để xây tập và kiểm tra kích thước, đổi lại bộ nhớ phụ **O(n)**. Đây là tối ưu về **thuật toán và cấu trúc dữ liệu**, độc lập với pattern matching.

**Những điều kiện cần lưu ý:**

- Cả hai cách trong ví dụ dùng tính bằng nhau theo `equals` và đều có thể xử lý phần tử `null` (HashSet cho phép null).
- Phải chọn định nghĩa "trùng" đúng nghiệp vụ: theo identity, theo một trường khóa, không phân biệt chữ hoa/thường, hay theo một comparator? Không phải mọi chiến lược đều tương đương.
- Với danh sách rất nhỏ, chi phí tạo `HashSet` có thể vượt lợi ích giảm so sánh; cần đo.
- Hiệu năng trung bình của hashing phụ thuộc số lượng phần tử, chất lượng hash và runtime; đây **không phải cam kết tệ nhất O(n)** cho mọi kiểu dữ liệu.
- Với danh sách có `get(i)` không hằng thời gian (ví dụ `LinkedList`), phép phân tích chi phí của bản vòng lặp cần tính cả độ phức tạp truy cập vị trí.
- Nếu các phần tử hoặc hash có thể bị mutate trong lúc xét, việc dùng Set phải có hợp đồng bất biến/đồng bộ rõ ràng.

Đây là lý do **tối ưu đúng hướng** thường bắt đầu bằng câu hỏi: "Dữ liệu được truy cập như thế nào?" hơn là "Có cách viết `case` đẹp hơn không?".

## 9. Các tối ưu khác mà pattern matching không thể thay thế

| Nút thắt thực tế | Vì sao pattern không giải quyết được | Hướng xử lý cần đánh giá |
| --- | --- | --- |
| Truy vấn cơ sở dữ liệu lặp theo từng phần tử | Pattern chỉ phân loại dữ liệu sau khi nhận; không cắt số round trip | Batch query, index, lọc ở DB, tránh N+1 |
| Đọc/ghi tệp hoặc HTTP chậm | Chi phí I/O và mạng cao hơn thao tác kiểm tra kiểu trong nhiều ứng dụng | Batching, timeout, pooling, cache có kiểm soát |
| Thuật toán lồng nhiều vòng | Độ phức tạp tăng theo dữ liệu | Đổi thuật toán/cấu trúc dữ liệu, index/hash |
| Cấp phát object quá nhiều | Pattern không tự làm kết quả không cần object | Profile allocation, giảm dữ liệu trung gian |
| GC pause hoặc heap pressure | Điều phối nhánh không thay chính sách giữ object | Kiểm tra lifetime, heap, GC log và allocation |
| Lock contention | Switch không tự loại bỏ tranh chấp thread | Thu hẹp critical section, đo lock, thiết kế concurrency |
| Cache miss và locality kém | Record pattern không thay layout đối tượng | Chọn cấu trúc dữ liệu/locality theo workload |
| Regex/JSON parsing lặp | Pattern vẫn gọi helper nặng | Precompile/reuse parser phù hợp, cache kết quả hợp lệ |
| Chuyển đổi dữ liệu nhiều lần | Dùng `case` không ngăn mapping/serialization lặp | Thiết kế pipeline, giảm bước thừa |
| Tạo exception như một đường kiểm tra thường xuyên | Pattern không tự xử lý toàn bộ API contract | Tối ưu control flow khi nghiệp vụ cho phép, giữ semantics |

**Ưu tiên theo bằng chứng:** Với một API có latency cao, điều đầu tiên nên xác định là thời gian đang ở DB, network, CPU, GC hay contention. Nếu 90% thời gian nằm trong external I/O, việc tranh luận giữa `instanceof` và `switch` thường không tác động nhiều đến latency đầu-cuối, dù vẫn có giá trị về readability.

## 10. Đo hiệu năng đúng cách: benchmark không phải stopwatch một lần

### 10.1. Tại sao vòng `System.nanoTime()` tự viết dễ sai?

Ví dụ đáng nghi:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    classifyFixedObject();
}
long elapsed = System.nanoTime() - start;
```

Trong đoạn này, `classifyFixedObject()` là helper giả định. Thí nghiệm có thể bị ảnh hưởng bởi:

- JVM chưa warm-up đủ, phương thức chưa được JIT compile.
- **Dead-code elimination:** nếu kết quả không được dùng, JVM có thể bỏ tính toán không có side effect.
- **Constant folding:** đầu vào cố định có thể được tối ưu khác với workload production.
- GC, turbo boost, CPU frequency, background processes, thermal state.
- Một lần đo không có độ phân tán hoặc confidence interval.
- Benchmark trộn cả khởi tạo dữ liệu và phần muốn đo.
- Cùng bytecode nhưng profile nhánh khác nhau theo lượt chạy.

Đo như vậy có thể hữu ích để chẩn đoán sơ bộ, nhưng **không đủ để tuyên bố một thay đổi nhanh hơn một tỷ lệ cụ thể**.

### 10.2. Dùng JMH cho microbenchmark

**JMH (Java Microbenchmark Harness)** của OpenJDK là công cụ chuyên đo mã Java/JVM ở mức nano/micro/milli, hỗ trợ warm-up, forks, iterations, chế độ đo và cơ chế hạn chế một số bẫy optimizer.

Ví dụ khung benchmark so sánh **cùng logic phân loại** của hai phương thức `legacy` và `modern` trong file đầy đủ ở phần 12:

```java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
public class DispatchBenchmark {
    @Param({"string", "integer", "point", "other"})
    public String type;

    private Object input;

    @Setup(Level.Trial)
    public void setup() {
        input = switch (type) {
            case "string" -> " java ";
            case "integer" -> 42;
            case "point" -> new PatternOptimizationDemo.Point(3, 4);
            default -> new Object();
        };
    }

    @Benchmark
    public String legacy() {
        return PatternOptimizationDemo.legacy(input);
    }

    @Benchmark
    public String patterns() {
        return PatternOptimizationDemo.modern(input);
    }
}
```

**Lưu ý quan trọng:** Đây là **một lớp JMH minh họa**, không chạy độc lập bằng lệnh `javac` JDK thuần. Cần tạo project benchmark JMH có dependency và annotation processor theo hướng dẫn chính thức, đồng thời đưa mã `PatternOptimizationDemo` vào classpath. Mục tiêu là chỉ cách thiết kế input/two implementations, không công bố kết quả nanosecond chưa đo.

Khung này đo **từng loại input riêng**. Nếu production có phân bố hỗn hợp, cần benchmark thêm dữ liệu hỗn hợp đại diện, tránh tự kết luận từ một nhóm đồng nhất. Kết quả trả về được JMH dùng như một giá trị quan sát được, nhưng vẫn cần kiểm tra bẫy constant folding, dead-code elimination và sự thay đổi semantics. Tham khảo các JMH Samples trước khi đưa vào CI.

### 10.3. Các điều kiện so sánh công bằng

Một benchmark đáng tin cho legacy cast và pattern matching cần:

1. **Cùng hợp đồng kết quả:** cả hai phân loại như nhau, giữ `null`, ngoại lệ, guard, whitespace, thứ tự nhánh.
2. **Cùng workload:** kiểu dữ liệu, kích thước, phân bố nhánh, chuỗi blank, record nested và tần suất gọi.
3. **Cùng môi trường:** CPU, RAM, JDK/JVM vendor/version, heap/GC flags, OS, tần số CPU có ảnh hưởng.
4. **Warm-up và forks:** không chỉ lấy thời gian của lần gọi đầu tiên; tách các lượt chạy độc lập khi cần.
5. **Không đo phí setup không liên quan:** tạo dữ liệu ngoài vùng đo, trừ khi chi phí tạo dữ liệu là một phần bài toán thực.
6. **Nhiều mẫu:** đọc sai số, phân tán, outliers; tránh kết luận từ chênh lệch nhỏ trong nhiễu.
7. **Quan sát allocation/GC:** hai phương án có thể gần bằng CPU nhưng khác cấp phát.
8. **Profile trước và sau:** dùng Java Flight Recorder (JFR), profiler, GC logs hoặc hệ quan sát sẵn có để xác định đúng hotspot.
9. **Kiểm tra theo version:** kết quả ở JDK 21 không tự áp dụng cho JDK hoặc kiến trúc CPU khác.
10. **Đo production-level:** các chỉ số latency p50/p95/p99, throughput, error rate, CPU/GC phải phản ánh trải nghiệm đầu-cuối, không chỉ nanoseconds của một helper.

**Không tạo số liệu minh họa giả thành số đo thật.** Nếu chưa chạy JMH hay profiling, chỉ mô tả giả thuyết và kế hoạch xác minh.

## 11. Cách xây dựng quy trình tối ưu thực tế

Một quy trình hợp lý thường theo thứ tự:

### Bước 1 — Xác định mục tiêu có thể đo

Ví dụ: giảm p95 latency của endpoint theo điều kiện tải xác định, giảm CPU thời gian cao điểm hoặc giảm allocation rate của một hot path. Không dùng chỉ tiêu chung chung "code gọn hơn" thay cho mục tiêu hiệu năng.

### Bước 2 — Ghi nhận baseline

Ghi workload, phiên bản code/JDK, hệ thống, output, các exception quan trọng và số liệu trước thay đổi. Nếu không có baseline, khó biết cải tiến nào tạo hiệu quả hoặc thay đổi nào làm hỏng behavior.

### Bước 3 — Profiling và chọn đúng hotspot

Dùng profiler/JFR để xác nhận thời gian nằm ở đâu. Với hệ thống xử lý dữ liệu, tìm vòng lặp, collection operations, regex, serialization, lock hoặc I/O. Đừng giả định hotspot là nhánh `instanceof` chỉ vì nó nhìn có vẻ dài.

### Bước 4 — Tối ưu một nguyên nhân có bằng chứng

Ví dụ: tái sử dụng compiled regex, đổi thuật toán phát hiện trùng, giảm số DB round trip, tránh cấp phát trung gian. Có thể refactor bằng pattern matching để giúp code rõ hơn, nhưng **nên tách PR/cam kết** nếu muốn đo tác động của một tối ưu thật.

### Bước 5 — Test tương đương trước khi benchmark

Giữ nguyên input/output, `null`, exception, side effect và thứ tự nhánh. Nếu một thay đổi nghiệp vụ được phép, ghi nhận/test riêng trước khi so hiệu năng.

### Bước 6 — Microbenchmark và kiểm tra hệ thống

JMH giúp kiểm tra giả thuyết CPU-level với input thích hợp. Load test/integration/production metrics giúp kiểm tra hiệu quả đầu-cuối. Khi hai kết quả khác nhau, cần hiểu vì sao chứ không chọn số đẹp hơn.

### Bước 7 — Theo dõi sau triển khai, sẵn sàng rollback

So sánh latency, throughput, CPU, GC, error rate trên cửa sổ thời gian/tải đại diện. Nếu tối ưu đổi tài nguyên lấy độ trễ (ví dụ thêm HashSet làm tăng memory), đánh giá trade-off theo yêu cầu hệ thống. Nếu có regression, revert hoặc khôi phục logic đã xác nhận.

## 12. Chương trình Java 21 hoàn chỉnh: ba nhóm kiểm chứng

Tạo tệp **`PatternOptimizationDemo.java`** dưới đây. Chương trình **không phải benchmark tốc độ**: nó kiểm tra ba ý tưởng có ý nghĩa trước khi đo:

- **Refactor cú pháp:** `legacy(Object)` dùng `instanceof` + cast; `modern(Object)` dùng pattern `switch`. Cả hai phải trả cùng kết quả với cùng input.
- **Tối ưu riêng biệt:** `slowRegex` và `cachedRegex` kiểm tra cùng regex; chỉ khác cách chuẩn bị `Pattern`.
- **Khác biệt thuật toán:** phát hiện trùng bằng O(n²) so với dựa vào `HashSet` với chi phí trung bình O(n), so kết quả.
- **Record deconstruction:** đo lượt gọi accessor để thấy việc match sâu có thể thực hiện thêm công việc.

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.regex.Pattern;

public class PatternOptimizationDemo {
    record Point(int x, int y) {}
    record Metered(int value) {
        static int reads;
        @Override public int value() {
            reads++;
            return value;
        }
    }
    record Envelope(Metered measurement) {}

    private static final Pattern CODE_PATTERN =
            Pattern.compile("[A-Z]{2}[0-9]{3}");

    static String legacy(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            return text.isBlank() ? "blank" : "text:" + text.strip();
        }
        if (value instanceof Integer) {
            Integer number = (Integer) value;
            return number >= 0 ? "non-negative:" + number : "negative:" + number;
        }
        if (value instanceof Point) {
            Point point = (Point) value;
            return "point:" + point.x() + "," + point.y();
        }
        return "other";
    }

    static String modern(Object value) {
        return switch (value) {
            case String text when text.isBlank() -> "blank";
            case String text -> "text:" + text.strip();
            case Integer number when number >= 0 -> "non-negative:" + number;
            case Integer number -> "negative:" + number;
            case Point(var x, var y) -> "point:" + x + "," + y;
            case null -> "other";
            default -> "other";
        };
    }

    static boolean slowRegex(String text) {
        return text != null && text.matches("[A-Z]{2}[0-9]{3}");
    }

    static boolean cachedRegex(String text) {
        return text != null && CODE_PATTERN.matcher(text).matches();
    }

    static boolean typeOnly(Object input) {
        return input instanceof Envelope;
    }

    static boolean deconstruct(Object input) {
        return input instanceof Envelope(Metered(var n)) && n >= 0;
    }

    static boolean quadraticDuplicate(List<String> values) {
        for (int i = 0; i < values.size(); i++) {
            for (int j = i + 1; j < values.size(); j++) {
                if (Objects.equals(values.get(i), values.get(j))) {
                    return true;
                }
            }
        }
        return false;
    }

    static boolean hashedDuplicate(List<String> values) {
        return new HashSet<>(values).size() != values.size();
    }

    public static void main(String[] args) {
        Object[] values = {
            " java ", "", "  ", 9, -2, new Point(3, 4),
            new Point(-1, 5), new StringBuilder("abc"), null
        };
        for (Object value : values) {
            String expected = legacy(value);
            String actual = modern(value);
            if (!expected.equals(actual)) {
                throw new AssertionError("classification mismatch: " + value);
            }
            System.out.println(actual);
        }
        System.out.println("PARITY PASS: " + values.length);

        String[] codes = { "AB123", "XY999", "ab123", "AB12", "AB1234", null };
        for (String code : codes) {
            boolean expected = slowRegex(code);
            boolean actual = cachedRegex(code);
            if (expected != actual) {
                throw new AssertionError("regex mismatch: " + code);
            }
            System.out.println("regex " + code + "=" + actual);
        }
        System.out.println("REGEX PARITY PASS: " + codes.length);

        Envelope valid = new Envelope(new Metered(7));
        System.out.println("type only=" + typeOnly(valid) + ", reads=" + Metered.reads);
        System.out.println("deconstruct=" + deconstruct(valid) + ", reads=" + Metered.reads);
        System.out.println("missing nested=" + deconstruct(new Envelope(null))
                + ", reads=" + Metered.reads);
        System.out.println("negative=" + deconstruct(new Envelope(new Metered(-1)))
                + ", reads=" + Metered.reads);

        List<List<String>> duplicateSamples = List.of(
            List.of("A", "B", "C"),
            List.of("A", "B", "A"),
            Arrays.asList(null, "X", null),
            List.of("A"),
            List.of()
        );
        for (int i = 0; i < duplicateSamples.size(); i++) {
            List<String> sample = duplicateSamples.get(i);
            boolean expected = quadraticDuplicate(sample);
            boolean actual = hashedDuplicate(sample);
            if (expected != actual) {
                throw new AssertionError("duplicate mismatch: " + sample);
            }
            System.out.println("duplicates " + i + "=" + actual);
        }
        System.out.println("DUPLICATES PARITY PASS: " + duplicateSamples.size());
        System.out.println("ALL CHECKS PASSED");
    }
}
```

**Biên dịch và chạy:** từ thư mục có file bằng JDK 21+.

```bash
javac --release 21 PatternOptimizationDemo.java
java PatternOptimizationDemo
```

**Kết quả stdout chính xác:**

```text
text:java
blank
blank
non-negative:9
negative:-2
point:3,4
point:-1,5
other
other
PARITY PASS: 9
regex AB123=true
regex XY999=true
regex ab123=false
regex AB12=false
regex AB1234=false
regex null=false
REGEX PARITY PASS: 6
type only=true, reads=0
deconstruct=true, reads=1
missing nested=false, reads=1
negative=false, reads=2
duplicates 0=false
duplicates 1=true
duplicates 2=true
duplicates 3=false
duplicates 4=false
DUPLICATES PARITY PASS: 5
ALL CHECKS PASSED
```

### 12.1. Giải thích kết quả

- **`PARITY PASS: 9`:** chín input cho kết quả giống nhau giữa mã legacy và pattern switch, bao gồm `null`, `StringBuilder`, số nguyên âm và record `Point`. Không có số liệu runtime ở đây nên **không thể tuyên bố bản nào nhanh hơn**.
- **`REGEX PARITY PASS: 6`:** sáu mẫu mã định danh cho kết quả tương đương giữa `String.matches` và matcher từ `Pattern` biên dịch trước. Test chỉ chứng minh tính đúng đắn trên các ca này; muốn xác minh hiệu quả của cache phải đo với số lần gọi và dữ liệu thực tế.
- **`type only=true, reads=0`:** chỉ kiểm tra Envelope, không deconstruct `Metered`.
- **`deconstruct=true, reads=1`:** nested record pattern đọc component `Metered.value()` một lần trong ca này.
- **`missing nested=false, reads=1`:** nested record bằng `null` không match, không tăng lượt đọc accessor.
- **`negative=false, reads=2`:** record vẫn được deconstruct, sau đó guard `n >= 0` thất bại; accessor vẫn đã chạy.
- **`DUPLICATES PARITY PASS: 5`:** hai thuật toán phát hiện trùng đồng ý trên các danh sách thông thường, có phần tử trùng, có `null`, một phần tử và rỗng. Sự khác nhau về độ phức tạp không được suy ra từ output; nó đến từ cấu trúc vòng lặp so với hashing và cần benchmark để đánh giá hằng số chi phí.

**Cảnh báo về tính đúng đắn:** Nếu input có cấu trúc hoặc hành vi khác ví dụ (custom `equals/hashCode` sai hợp đồng, cấu trúc mutable, kiểu con đặc biệt, exception của accessor), cần test riêng. Mục tiêu ví dụ là **minh họa cách suy nghĩ**, không khẳng định hai cách luôn tương đương trên mọi đối tượng có thể có.

## 13. Thiết kế kiểm thử trước khi kết luận tối ưu

Tối ưu sai hành vi là regression, ngay cả khi nó làm benchmark nhanh hơn. Cần kiểm tra ít nhất:

| Nhóm | Dữ liệu / tình huống | Kỳ vọng |
| --- | --- | --- |
| Type match thông thường | String, Integer, Point | Cùng output/nhánh |
| String blank/whitespace | `""`, `"  "`, `" java "` | Cùng normalizing rule |
| Số biên | 0, -1, số lớn | Không đổi nhánh/overflow behavior |
| Selector null | `null` | Cùng fallback hoặc exception được phê duyệt |
| Khác kiểu | StringBuilder, Object | Không bị thay bởi nhánh type quá rộng |
| Guard true/false | Dữ liệu qua/không qua guard | Cùng thứ tự lựa chọn nhánh |
| Nested null | Envelope(null), record component null | Không vô tình deconstruct/null-dereference |
| Custom accessor | Có counter/exception | Kiểm tra side effects nếu hợp đồng phụ thuộc |
| Regex hợp lệ/sai | Chuỗi đúng/sai định dạng, null | Hai cách trả cùng boolean |
| Collection rỗng, một phần tử, trùng, null | Danh sách đại diện | Hai thuật toán chọn cùng kết quả |
| Quy mô dữ liệu | Nhỏ, vừa, lớn | Đo latency/allocations sau khi correctness PASS |
| Môi trường JDK | Java 21 và runtime thật | Build + test trên cấu hình target |

Nên có **unit tests** và **differential tests** cho hai phiên bản, đồng thời benchmark tải hỗn hợp đại diện. Với hiệu năng, nêu rõ giả thuyết cần chứng minh: *"trên hệ thống X, phân bố đầu vào Y, code mới giảm CPU p95 mà không tăng GC hoặc lỗi"* thay vì *"dùng pattern sẽ nhanh hơn"*.

Nếu hiệu năng của logic chỉ phụ thuộc ít input, có thể benchmark riêng để hiểu chi phí từng loại; nhưng cũng phải đo end-to-end với dữ liệu/hành vi production.

## 14. Các ngộ nhận phổ biến

### Ngộ nhận 1 — "Pattern luôn nhanh hơn cast"

Không có cam kết ngôn ngữ như vậy. Mã legacy có `instanceof` + cast có thể được JIT tối ưu rất tốt. Pattern giúp tránh cast thủ công và rõ scope, nhưng hiệu năng phải đo.

### Ngộ nhận 2 — "Mọi `switch` expression đều hiệu quả hơn `if/else`"

Không nhất thiết. Khi `switch` thêm guard, record deconstruction hoặc allocation, tổng công việc có thể khác. Nếu hành vi giống nhau, benchmark mới trả lời được câu hỏi cụ thể.

### Ngộ nhận 3 — "Dùng `record Point(var x, var y)` sẽ làm mất toàn bộ object allocation"

Record pattern **không phải** một cơ chế tự động áp dụng scalar replacement cho mọi object. Nó đọc cấu trúc của object đã có. JIT có thể tối ưu trong các trường hợp nhất định, không bảo đảm cho tất cả.

### Ngộ nhận 4 — "Đổi sang pattern không cần profiling"

Nếu mục tiêu là hiệu năng, profiling vẫn là bước để xác định hotspot. Pattern matching là công cụ viết mã, không phải profiler.

### Ngộ nhận 5 — "Benchmark trong main với `nanoTime` một lần là đủ"

Đó là phép đo dễ bị warm-up, dead-code elimination và noise ảnh hưởng. JMH và hệ đo đầu-cuối phù hợp hơn khi cần kết luận đáng tin.

### Ngộ nhận 6 — "Precompile regex luôn giúp mọi lời gọi nhanh hơn một tỷ lệ cố định"

Tái sử dụng `Pattern` tránh compile regex lặp, nhưng có chi phí tạo matcher, khởi tạo, cách dùng và ảnh hưởng JIT. Không có một con số thắng lợi chung.

### Ngộ nhận 7 — "Tăng tốc CPU là đủ, không cần test null và exception"

Có thể vô tình đổi kết quả `null` khi chuyển `instanceof` sang `switch`. Nếu semantics khác, kết quả benchmark không còn so sánh cùng bài toán.

### Ngộ nhận 8 — "Mã có ít dòng hơn nghĩa là ít cấp phát hơn"

Một dòng `stream.map(...).collect(...)` hoặc `case String s -> expensiveTransform(s)` vẫn có thể tạo nhiều object và thực hiện công việc lớn. Đếm đối tượng, profile heap và kiểm tra thuật toán thay vì chỉ đếm dòng.

### Ngộ nhận 9 — "Cứ dùng HashSet thì luôn tối ưu"

HashSet đánh đổi memory và chi phí hashing để giảm kiểm tra tuyến tính lặp. Với input nhỏ, một vòng lặp đơn giản có thể phù hợp hơn. Nếu so sánh khác nghĩa hoặc hashCode không đúng, Set còn làm sai kết quả.

### Ngộ nhận 10 — "JIT sẽ tự sửa mọi thuật toán O(n²)"

JIT có thể tối ưu nhiều thao tác mức thấp nhưng không có lời hứa sẽ thay một thuật toán so từng cặp bằng một HashSet theo ý nghĩa nghiệp vụ. Chọn đúng thuật toán vẫn là trách nhiệm của người thiết kế.

## 15. Checklist cho performance review

- [ ] Phân biệt **mục tiêu readability/type safety** và **mục tiêu performance**.
- [ ] Đã xác nhận code chạy trên source/release JDK đích; record/switch patterns Java 21 không cần preview.
- [ ] Có baseline và mục tiêu đo được (latency, throughput, CPU, allocation, GC, error rate).
- [ ] Có profiler/JFR hoặc bằng chứng xác định hotspot thực tế.
- [ ] Pattern switch và mã legacy có cùng behavior với `null`, wrong type, guard, thứ tự case.
- [ ] Không có nhánh dominated, switch expression exhaustive và không vô tình đổi ngoại lệ.
- [ ] Record deconstruction chỉ đọc component thật sự cần; custom accessor đã được đánh giá.
- [ ] Không thay short-circuit hoặc kéo computation có side effect ra khỏi guard.
- [ ] Đã xét allocation, collection tạm, regex, I/O, DB, lock và chi phí chuyển đổi dữ liệu.
- [ ] Với cấu trúc dữ liệu lớn, đã so độ phức tạp thuật toán trước khi tối ưu micro.
- [ ] Có regression/differential tests trước khi đo, không điều chỉnh expected output chỉ để test xanh.
- [ ] Benchmark dùng input/branch distribution đại diện, warm-up, forks, iterations và hạn chế dead-code elimination.
- [ ] Kết quả đo ghi rõ JDK/OS/hardware/config và số liệu phân tán; không báo mức nhanh hơn khi chưa đo.
- [ ] Có đo end-to-end (p95/p99, throughput, memory/GC) nếu mục tiêu là ứng dụng production.
- [ ] Có review trade-off CPU/memory/độ phức tạp code và kế hoạch rollback nếu kết quả xấu.

**Tiêu chí DONE:** Code dễ hiểu và đúng hợp đồng; hiệu năng được đánh giá từ **số liệu phù hợp với workload và môi trường**, không từ cú pháp pattern matching. Nếu không phát hiện cải thiện có ý nghĩa, vẫn có thể giữ refactor vì lợi ích readability/type safety, nhưng **không ghi nhận một tối ưu performance chưa được chứng minh**.

## 16. Câu hỏi tự kiểm tra

**1. Pattern matching có thay thế việc chọn thuật toán tốt không?**  
Không. Pattern giúp kiểm tra/tách giá trị, còn độ phức tạp thuật toán và tổ chức dữ liệu vẫn phải thiết kế riêng.

**2. Vì sao `instanceof String s` không chắc nhanh hơn `instanceof String` rồi cast?**  
JVM/JIT có thể tối ưu cách cũ dựa trên cùng thông tin kiểu; không có cam kết tốc độ chỉ từ số dòng hoặc cú pháp.

**3. `case String s when expensiveRule(s)` có tự làm `expensiveRule` rẻ hơn không?**  
Không. Guard là lời gọi/biểu thức thực tế, vẫn tiêu tốn thời gian và có thể tạo side effect.

**4. `case Box(Point(var x,var y))` có cần đọc component không?**  
Có. Nested record pattern deconstruct dữ liệu; nếu chỉ cần biết kiểu ngoài, type pattern có thể đủ.

**5. Cache `Pattern` giúp tối ưu phần nào?**  
Tránh biên dịch regex lặp lại cho một quy tắc cố định; vẫn cần matcher và phải đo với workload thật.

**6. Có nên dùng chung một `static Matcher` cho mọi thread không?**  
Không. `Matcher` có trạng thái và không thread-safe. Có thể chia sẻ compiled `Pattern`, còn matcher nên thuộc từng lần xử lý hoặc có chính sách đồng bộ rõ ràng.

**7. Vì sao JMH tốt hơn chỉ `nanoTime()` trong một vòng lặp?**  
JMH hỗ trợ warm-up/forks/iterations và những cơ chế giúp tránh các bẫy JVM; dù vậy, vẫn phải tự thiết kế benchmark hợp lệ.

**8. Vì sao đổi vòng lặp O(n²) sang HashSet thường quan trọng hơn đổi `if` sang `switch`?**  
Vì nó thay cách tăng số lượng thao tác theo kích thước dữ liệu, không chỉ thay cách viết control flow; đổi lại cần bộ nhớ và hashing.

**9. Khi nào refactor pattern vẫn đáng làm nếu benchmark không nhanh hơn?**  
Khi nó cải thiện type safety, dễ đọc và bảo trì, không đổi hành vi và chi phí hiệu năng chấp nhận được. Hãy gọi đúng là refactor về chất lượng mã.

**10. Tại sao cần kiểm tra `null` trước khi so performance của `if instanceof` và `switch`?**  
Vì `instanceof` không match `null` nhưng pattern switch thường cần `case null` để giữ fallback; nếu không, code có thể ném NPE và không còn tương đương.

**11. Một benchmark JMH cho `String` có đủ để kết luận với `Point`, `Integer` và các trường hợp hỗn hợp không?**  
Không. Profiling/JIT/branch behavior và công việc trong các case khác nhau; cần đại diện đúng phân bố input.

**12. Cần báo cáo gì nếu chưa đo thực tế?**  
Nêu giả thuyết, thay đổi mã, ảnh hưởng lý thuyết (ví dụ độ phức tạp trung bình), test parity và kế hoạch benchmark; **không báo số liệu hay mức tăng tốc chưa kiểm chứng**.

## Tham khảo chính thức

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java SE 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [Oracle Java SE 21 — String.matches](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#matches(java.lang.String))
- [Oracle Java SE 21 — java.util.regex.Pattern](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html)
- [Oracle Java SE 21 — java.util.regex.Matcher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Matcher.html)
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh)
- [Oracle JDK — Java Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/)
- [JLS SE 21 §14.30.2 — Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2)
