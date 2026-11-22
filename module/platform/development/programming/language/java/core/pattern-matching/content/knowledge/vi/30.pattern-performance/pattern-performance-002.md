# Chi phí accessor trong record pattern

## 1. Record pattern gọn hơn nhưng không phải “miễn phí”

Từ Java 21, **record pattern** cho phép kiểm tra kiểu record và phân rã các component trong cùng một biểu thức. Ví dụ:

```java
record Point(int x, int y) {}

static int sum(Object value) {
    if (value instanceof Point(int x, int y)) {
        return x + y;
    }
    return 0;
}
```

Đây là đoạn minh họa hợp lệ khi đặt cùng khai báo record, không phải một lớp chương trình độc lập. Khi `value` là `Point`, Java kiểm tra cấu trúc và lấy dữ liệu hai component để ràng buộc `x`, `y`.

Điểm quan trọng về hiệu năng: **record pattern không đọc trực tiếp component bằng phép thuật không có chi phí**. Theo đặc tả Java 21, giá trị mỗi component trong quá trình phân rã record được xác định bằng cách **gọi accessor tương ứng**. Với `Point`, đó là `x()` và `y()`. Vì vậy, đằng sau cú pháp:

```java
value instanceof Point(int x, int y)
```

có thể hình dung các thao tác liên quan đến việc xác định đối tượng có đúng kiểu record, lấy giá trị component qua accessor và so khớp các pattern con.

Tuy nhiên, không được kết luận rằng cách viết bằng record pattern **luôn chậm hơn** code gọi accessor thủ công. Khi accessor chỉ trả về field và mã chạy đủ nóng, JIT có thể inline hoặc tối ưu những lời gọi đó. Chi phí thực tế tùy vào **accessor**, **hình dạng pattern**, **số lần khớp**, **guard**, dữ liệu đầu vào và tối ưu của JVM.

Bài này trả lời bốn câu hỏi:

1. Accessor được gọi khi nào trong record pattern?
2. Vì sao accessor tùy chỉnh hoặc pattern lặp lại có thể làm tăng chi phí?
3. Khi nào nên dùng record pattern, type pattern hoặc biến cục bộ?
4. Làm sao đo đúng thay vì tối ưu theo cảm giác?

## 2. Accessor trong record là gì?

Record khai báo một tập component cố định:

```java
record Product(String code, int price) {}
```

Java cung cấp các phương thức accessor có tên tương ứng với component:

```java
Product product = new Product("P-1", 150);
String code = product.code();
int price = product.price();
```

Với một record đơn giản, accessor được tạo tự động có hành vi trả về field tương ứng. Record cũng cho phép tác giả **tự khai báo accessor** phù hợp với kiểu trả về của component:

```java
record NormalizedName(String raw) {
    public String raw() {
        return raw == null ? "" : raw.strip();
    }
}
```

Đây là ví dụ minh họa của accessor tùy chỉnh. Giá trị nhận qua `raw()` có thể khác cách biểu diễn field ban đầu. Quan trọng hơn, accessor tùy chỉnh có thể thực hiện thêm thao tác: tính toán, định dạng, kiểm tra, ghi số lần gọi, thậm chí ném exception.

Vì record pattern gọi accessor để xác định component, việc thay một pattern đơn giản bằng pattern phân rã có thể kéo theo **chi phí của logic accessor**. Điều này đúng ngay cả khi cú pháp bên ngoài chỉ dài thêm vài ký tự.

**Khuyến nghị:** thiết kế accessor của record đơn giản, ổn định, hạn chế tác dụng phụ và các thao tác tốn tài nguyên. Việc phải đọc file, gọi API từ xa hoặc thao tác cơ sở dữ liệu trong accessor thường là dấu hiệu trách nhiệm đặt sai chỗ, không phải điều nên mặc nhiên chấp nhận chỉ vì record pattern sẽ gọi nó.

## 3. So sánh type pattern và record pattern

### 3.1. Type pattern: chỉ kiểm tra kiểu và ràng buộc object

```java
if (value instanceof Product product) {
    System.out.println(product.code());
}
```

Ở đây, `instanceof Product product` là **type pattern**, không phải record pattern. Bản thân phép kiểm tra kiểu không cần phân rã tất cả component của `Product`. Accessor `code()` chỉ được gọi khi phần thân gọi nó.

### 3.2. Record pattern: phân rã component

```java
if (value instanceof Product(String code, int price)) {
    System.out.println(code);
}
```

Ở đây là **record pattern**. Để khớp mẫu, Java lấy các component theo hợp đồng của record và so khớp chúng với các component pattern. Chúng ta chỉ dùng `code` sau đó, nhưng pattern vẫn liệt kê cả `price` do cấu trúc record có hai component.

Với record có nhiều component và accessor tùy chỉnh tốn chi phí, việc phân rã tất cả component chỉ để dùng một giá trị có thể không phải lựa chọn tốt nhất. Type pattern với lời gọi accessor cần thiết có thể dễ kiểm soát hơn:

```java
if (value instanceof Product product) {
    String code = product.code();
    System.out.println(code);
}
```

**Không có kết luận tuyệt đối về tốc độ.** Nếu các accessor đều là getter rất nhỏ và JVM có thể inline tốt, chênh lệch giữa hai cách có thể không đáng kể. Nếu một accessor thực hiện công việc nặng, chênh lệch có thể rất rõ. Hãy nhìn vào **logic phải thực hiện**, không chỉ số lượng dấu ngoặc.

## 4. Khi một switch thử nhiều record pattern có guard

Hãy xét biểu thức phân loại:

```java
return switch (value) {
    case Product(String code, int price) when price >= 100 ->
            "Giá cao: " + code;
    case Product(String code, int price) ->
            "Giá thấp: " + code;
    case null ->
            "Không có sản phẩm";
    default ->
            "Không phải sản phẩm";
};
```

Đây là đoạn minh họa trong một phương thức trả về `String`, với `value` đã khai báo.

Nếu đối tượng là `Product` và `price >= 100`, case đầu được chọn. Nhưng nếu `price < 100`:

1. Record pattern của case đầu khớp, nên guard `price >= 100` được đánh giá rồi trả về `false`.
2. Java tiếp tục xem xét case tiếp theo.
3. Case `Product(String code, int price)` thứ hai lại thực hiện việc khớp record để chọn nhánh `Giá thấp`.

Với accessor có tác dụng phụ có thể quan sát, các lần so khớp riêng biệt này có thể dẫn đến **lời gọi accessor lặp lại**. Một số cách tối ưu có thể làm giảm chi phí thực thi trong trường hợp getter thuần túy, nhưng không nên dựa vào giả định JVM sẽ loại bỏ công việc có tác dụng phụ hoặc những lời gọi mà kết quả có thể thay đổi.

Nếu chỉ cần phân loại theo giá, viết một type pattern và tính giá **một lần** trong block có thể minh bạch hơn:

```java
return switch (value) {
    case Product product -> {
        int price = product.price();
        String code = product.code();
        yield price >= 100
                ? "Giá cao: " + code
                : "Giá thấp: " + code;
    }
    case null -> "Không có sản phẩm";
    default -> "Không phải sản phẩm";
};
```

Đây cũng là đoạn minh họa, không phải tệp chạy độc lập. Cách thứ hai diễn đạt rõ rằng **chúng ta cố ý chỉ đọc mỗi component cần thiết một lần** trong phần thân case. Nó không có nghĩa cứ nhìn thấy hai record pattern là phải đổi ngay: giữ bản dễ đọc hơn khi benchmark không chứng minh lợi ích thực tế và accessor đã đủ rẻ.

## 5. Accessor tùy chỉnh khiến chi phí trở nên quan sát được

Record có thể khai báo accessor đếm số lần đọc:

```java
record Metered(int units, String label) {
    private static int accessCount;

    public int units() {
        accessCount++;
        return units;
    }

    static void reset() {
        accessCount = 0;
    }

    static int calls() {
        return accessCount;
    }
}
```

Đây là mã Java 21 minh họa, giả định record được khai báo trong phạm vi cho phép. Biến đếm được dùng để quan sát **số lần accessor `units()` được gọi**, không đo nanosecond.

Với hai case của cùng record:

```java
static String repeatedPattern(Object input) {
    return switch (input) {
        case Metered(int units, var label) when units >= 10 ->
                "EXPRESS " + label;
        case Metered(int units, var label) ->
                "STANDARD " + label;
        case null -> "NONE";
        default -> "OTHER";
    };
}
```

Nếu `Metered` có `units = 5`, case đầu khớp record nhưng guard sai; case thứ hai được thử tiếp. Trong ví dụ có accessor đếm lần, `units()` được gọi ở cả hai lần khớp nên bộ đếm tăng **2**. Với `units = 12`, case đầu được chọn ngay nên bộ đếm tăng **1**.

Cách chỉ kiểm tra kiểu rồi dùng accessor có kiểm soát:

```java
static String typePattern(Object input) {
    return switch (input) {
        case Metered value -> {
            int units = value.units();
            yield (units >= 10 ? "EXPRESS " : "STANDARD ")
                    + value.label();
        }
        case null -> "NONE";
        default -> "OTHER";
    };
}
```

Mã trên đọc `units()` **một lần** khi đối tượng là `Metered`, rồi dùng biến cục bộ để ra quyết định. Trong một hệ thống thực, nếu accessor có logic đắt đỏ, việc lưu giá trị đã đọc có thể vừa rõ nghĩa vừa giảm công việc lặp lại.

**Quan trọng:** bộ đếm `static` trong ví dụ không thread-safe. Nó chỉ phục vụ chương trình minh họa chạy tuần tự; không dùng cách đo này để kết luận hiệu năng trong ứng dụng đa luồng. Các lần gọi accessor có tác dụng phụ là điều nên nhận diện, không phải kỹ thuật đáng khuyến khích trong thiết kế record thông thường.

## 6. Nested record patterns: chi phí tích lũy theo cấu trúc

Giả sử domain có record lồng nhau:

```java
record Address(String city, String street) {}
record Customer(String id, Address address) {}
record Order(String code, Customer customer, int total) {}
```

Một pattern sâu:

```java
if (input instanceof Order(
        var code,
        Customer(var id, Address(var city, var street)),
        var total)) {
    System.out.println(code + ": " + city);
}
```

Java phải xử lý cấu trúc `Order`, `Customer` và `Address` để xác định có khớp toàn bộ record pattern hay không. Quá trình này dùng accessor tại những cấp record được phân rã. Nếu có nhiều cấp, nhiều component, accessor phức tạp hoặc trường hợp khớp thất bại thường xuyên, công việc có thể đáng kể hơn một type pattern chỉ lấy đúng giá trị cần dùng.

Cách khác, khi chỉ cần thành phố:

```java
if (input instanceof Order order) {
    Customer customer = order.customer();
    if (customer != null && customer.address() != null) {
        String city = customer.address().city();
        System.out.println(order.code() + ": " + city);
    }
}
```

Đoạn minh họa trên vẫn có thể **gọi `customer.address()` hai lần**, vì vậy chưa chắc tốt hơn! Nếu accessor `address()` đắt hoặc có side effect, có thể lưu tạm:

```java
if (input instanceof Order order) {
    Customer customer = order.customer();
    if (customer != null) {
        Address address = customer.address();
        if (address != null) {
            String city = address.city();
            System.out.println(order.code() + ": " + city);
        }
    }
}
```

Ở phiên bản này, mỗi lời gọi `order.customer()`, `customer.address()` và `address.city()` được viết **một lần**. Đây là một lý do để chọn tách nhỏ logic khi cấu trúc quá sâu. Tuy vậy, trong code thực, hãy ưu tiên tính đúng đắn, xử lý `null` và tính dễ đọc; chỉ tối ưu sau khi xác định accessor thực sự gây chi phí đáng kể.

Ngoài chi phí, cần nhớ **selector `null` không khớp record pattern**. Nếu một record lồng bắt buộc phải khớp nhưng component tại vị trí đó là `null`, pattern lồng thất bại. Cách viết bằng type pattern cùng guard/check `null` phải giữ nguyên hành vi nếu được dùng để refactor.

## 7. Accessor ném exception: không phải guard false

Một khía cạnh dễ bị bỏ qua là accessor **có thể ném exception**, đặc biệt khi được tự khai báo.

Theo **Java Language Specification 21, mục 14.30.2**, nếu lời gọi accessor để khớp record pattern kết thúc đột ngột bằng exception, việc so khớp record pattern kết thúc đột ngột bằng **`MatchException`**, có `cause` là lỗi gốc.

Ví dụ:

```java
record Fragile(int value) {
    public int value() {
        throw new IllegalStateException("Accessor failed");
    }
}
```

Khi chạy:

```java
static String inspectFragile(Object input) {
    return switch (input) {
        case Fragile(int value) -> "VALUE=" + value;
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

Nếu input là `new Fragile(9)`, bản thân đối tượng đã khớp kiểu `Fragile`, nhưng khi record pattern gọi `value()` thì accessor ném `IllegalStateException`. Quá trình matching ném `MatchException` có nguyên nhân là `IllegalStateException`. **Java không coi exception từ accessor như kết quả pattern false để tự động rơi sang `default`.**

So sánh:

```java
static String accessDirectly(Object input) {
    if (input instanceof Fragile fragile) {
        return "VALUE=" + fragile.value();
    }
    return "OTHER";
}
```

Ở đây `Fragile fragile` chỉ là **type pattern**. Lời gọi `fragile.value()` là lời gọi phương thức thông thường trong thân `if`, nên exception được ném trực tiếp theo quy tắc method invocation (với ví dụ này là `IllegalStateException`), không phải exception bọc bởi record-pattern matching.

**Hàm ý:** Trước khi thay code đọc accessor thủ công bằng record pattern, cần xác định accessor có custom logic hoặc có thể ném exception không. Refactor có thể giữ giá trị thành công nhưng **thay đổi loại exception bề mặt**, ảnh hưởng xử lý lỗi và test. Trong domain model lành mạnh, getter/accessor thuần túy, ổn định sẽ giúp cả pattern và API dễ sử dụng hơn.

## 8. Chương trình Java 21 chạy hoàn chỉnh

Tạo tệp **`RecordAccessorCostDemo.java`**:

```java
public class RecordAccessorCostDemo {
    record Metered(int units, String label) {
        private static int accessCount;

        public int units() {
            accessCount++;
            return units;
        }

        static void reset() {
            accessCount = 0;
        }

        static int calls() {
            return accessCount;
        }
    }

    record Fragile(int value) {
        public int value() {
            throw new IllegalStateException("Accessor failed");
        }
    }

    static String repeatedPattern(Object input) {
        return switch (input) {
            case Metered(int units, var label) when units >= 10 ->
                    "EXPRESS " + label;
            case Metered(int units, var label) ->
                    "STANDARD " + label;
            case null -> "NONE";
            default -> "OTHER";
        };
    }

    static String typePattern(Object input) {
        return switch (input) {
            case Metered metered -> {
                int units = metered.units();
                yield (units >= 10 ? "EXPRESS " : "STANDARD ")
                        + metered.label();
            }
            case null -> "NONE";
            default -> "OTHER";
        };
    }

    static String inspectFragile(Object input) {
        return switch (input) {
            case Fragile(int value) -> "VALUE=" + value;
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    static String accessDirectly(Object input) {
        if (input instanceof Fragile fragile) {
            return "VALUE=" + fragile.value();
        }
        return "OTHER";
    }

    public static void main(String[] args) {
        Metered low = new Metered(5, "A");
        Metered high = new Metered(12, "B");

        Metered.reset();
        System.out.println("record low: " + repeatedPattern(low));
        System.out.println("record calls: " + Metered.calls());

        Metered.reset();
        System.out.println("record high: " + repeatedPattern(high));
        System.out.println("record calls: " + Metered.calls());

        Metered.reset();
        System.out.println("type low: " + typePattern(low));
        System.out.println("type calls: " + Metered.calls());

        Metered.reset();
        System.out.println("other: " + repeatedPattern("not metered"));
        System.out.println("other calls: " + Metered.calls());

        try {
            inspectFragile(new Fragile(9));
        } catch (MatchException ex) {
            System.out.println("record exception: "
                    + ex.getClass().getSimpleName());
            System.out.println("record cause: "
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            accessDirectly(new Fragile(9));
        } catch (IllegalStateException ex) {
            System.out.println("direct exception: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên** (không cần `--enable-preview`):

```bash
javac -encoding UTF-8 RecordAccessorCostDemo.java
java RecordAccessorCostDemo
```

Kết quả chuẩn:

```text
record low: STANDARD A
record calls: 2
record high: EXPRESS B
record calls: 1
type low: STANDARD A
type calls: 1
other: OTHER
other calls: 0
record exception: MatchException
record cause: IllegalStateException
direct exception: IllegalStateException
```

Giải thích kết quả:

- **Record pattern, units = 5:** mẫu `Metered` khớp ở case đầu, accessor `units()` tăng bộ đếm, guard `units >= 10` sai. Java xét tiếp case `Metered` thứ hai, gọi lại accessor và trả `STANDARD A`. Số lần đọc là **2**.
- **Record pattern, units = 12:** case đầu khớp và guard đúng; không cần thử case tiếp theo. Số lần đọc là **1**.
- **Type pattern, units = 5:** case `Metered metered` chỉ kiểm tra kiểu; phần thân gọi `metered.units()` đúng một lần, rồi dùng biến cục bộ để phân loại. Số lần đọc là **1**.
- **Đầu vào khác kiểu:** `"not metered"` không khớp hai case `Metered`, nên accessor `units()` không bị gọi; kết quả là `OTHER`, bộ đếm là **0**.
- **Accessor ném lỗi trong record pattern:** `inspectFragile` tạo `MatchException` với `cause` `IllegalStateException`. Một guard hay `default` không biến lỗi này thành “không khớp”.
- **Accessor gọi trực tiếp:** `accessDirectly` ném `IllegalStateException` trực tiếp vì đây là lời gọi phương thức thông thường, không nằm trong quá trình record-pattern matching.

Ví dụ sử dụng bộ đếm chỉ để **chứng minh hành vi gọi accessor**. Nó không đo thời gian và không chứng minh rằng record pattern “chậm gấp hai” trong ứng dụng thực. Số lời gọi quan sát được và chi phí CPU thực tế là hai đại lượng khác nhau. Một accessor phức tạp có side effect còn có thể ảnh hưởng tính đúng đắn khi bị gọi nhiều lần, không chỉ hiệu năng.

## 9. Benchmark đúng: đừng lấy một lần System.nanoTime làm bằng chứng

Với accessor tự động chỉ trả về field, JVM có thể inline; một benchmark thiếu warm-up dễ so sánh **bytecode chưa tối ưu** với **mã máy đã tối ưu** và tạo kết luận sai.

Không nên tin vào mẫu đo kiểu:

```java
long start = System.nanoTime();
// Gọi hàm một lần.
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
```

Đây là đoạn đo minh họa, không phải benchmark đáng tin cho chênh lệch rất nhỏ. Thời gian thu được gồm nhiều yếu tố như độ phân giải đồng hồ, quá trình khởi động, nhiễu hệ thống, JIT, GC và chi phí xung quanh.

Đối với phép đo nghiêm túc, cân nhắc **JMH (Java Microbenchmark Harness)**:

1. Dùng **cùng workload**, cùng phân phối subtype, cùng dữ liệu cho phiên bản record pattern và type pattern.
2. Đặt đầu vào trong `@State` hoặc cơ chế tương đương của JMH; tránh việc benchmark đo chủ yếu việc tạo object.
3. Có **warm-up**, **measurement iterations**, và nhiều fork khi thích hợp.
4. Dùng `Blackhole` hoặc trả kết quả benchmark để tránh *dead-code elimination*.
5. So sánh cả getter đơn giản, getter tùy chỉnh có tính toán thực và các trường hợp guard false/true.
6. Kiểm tra cả throughput và latency nếu liên quan đến yêu cầu sản phẩm; quan sát GC/allocation khi có công việc tạo đối tượng.
7. Đánh giá độ biến thiên, độ tin cậy của kết quả và impact thực tế, không chỉ nhìn một con số ở máy phát triển.

Ví dụ **khung ý tưởng JMH** dưới đây **không phải tệp chạy độc lập**: cần dependency và plugin/cấu hình JMH phù hợp với build:

```java
@State(Scope.Thread)
public class AccessorBenchmark {
    Object input = new Product("P-1", 150);

    @Benchmark
    public Object recordPattern() {
        return input instanceof Product(var code, var price)
                ? code : null;
    }

    @Benchmark
    public Object typePattern() {
        return input instanceof Product product
                ? product.code() : null;
    }
}
```

Mã trên giả định `Product` được khai báo và có `org.openjdk.jmh.annotations` phù hợp. Mục đích là chỉ ra hai tác vụ tương đương cần đo trên cùng đầu vào. Nếu logic hai bên khác nhau (một bên parse chuỗi, một bên chỉ trả field), phép đo không còn giúp trả lời “record pattern có overhead bao nhiêu”.

**Ưu tiên đo trên workload thực tế:** nếu profiling cho thấy việc phân rã record chỉ chiếm tỷ lệ nhỏ so với I/O, network hoặc xử lý nghiệp vụ, chỉnh sửa pattern có thể không mang lại lợi ích đáng kể dù số lần accessor giảm.

## 10. Khi nào nên tối ưu code?

| Tình huống | Quyết định nên cân nhắc | Vì sao |
| --- | --- | --- |
| Record nhỏ, accessor mặc định và chỉ có một case | Giữ record pattern rõ nghĩa. | Có thể được JIT inline; ít lý do để tối ưu thủ công. |
| Hai hoặc nhiều case của cùng record với guard lần lượt sai | Kiểm tra việc phân rã lặp, benchmark khi cần. | Có thể lặp lời gọi accessor trên các lần match. |
| Chỉ cần một component trong record có nhiều component | Cân nhắc type pattern và gọi getter cần thiết. | Tránh phân rã component không phục vụ tác vụ. |
| Accessor tự khai báo thực hiện tính toán nặng | Tách trách nhiệm hoặc cache giá trị theo hợp đồng. | Giảm công việc phụ thuộc vào số lần khớp. |
| Nested record pattern nhiều tầng | Kiểm tra cấu trúc và các accessor bên trong. | Chi phí có thể tăng theo dữ liệu thực tế và độ sâu phân rã. |
| Accessor có tác dụng phụ hoặc có thể ném exception | Thiết kế lại accessor, viết test hành vi rõ. | Có thể ảnh hưởng tính đúng đắn và bề mặt exception. |
| Thời gian chủ yếu ở I/O/DB/network | Tối ưu bottleneck được profiler xác nhận. | Đổi cú pháp pattern có thể không đáng kể. |

Lưu ý thêm: việc **cache dữ liệu** không đồng nghĩa cache bừa kết quả cho mọi input. Nếu giá trị accessor được thiết kế phụ thuộc trạng thái bên ngoài, việc lưu kết quả có thể thay đổi hành vi. Một record thông thường nên là giá trị ổn định và minh bạch; nếu getter không ổn định, hãy giải quyết ở thiết kế API trước khi xem xét tốc độ.

## 11. Những sai lầm thường gặp

### 11.1. “Record pattern chỉ là instanceof nhanh hơn”

Không chính xác. `instanceof Product product` chỉ là type pattern kiểm tra kiểu và ràng buộc object; `instanceof Product(var code, var price)` là record pattern, còn phân rã component bằng accessor. Hai cách có ý nghĩa và lượng công việc khác nhau.

### 11.2. “Đếm hai lời gọi nghĩa là chậm hai lần”

Không chính xác. Nếu getter được inline và không có chi phí đáng kể, hai lời gọi có thể rẻ; nếu accessor parse, allocate hoặc đồng bộ, chi phí lại khác. Bộ đếm có side effect còn làm workload khác một getter thuần túy; không nên dùng nó làm benchmark thời gian.

### 11.3. “Mọi accessor của record đều chỉ trả field”

Không đúng. Record có thể có explicit accessor với logic do người viết cung cấp. Cần hiểu contract của accessor khi dùng record pattern trong một đoạn code nhạy cảm về hiệu năng hoặc exception.

### 11.4. “Guard false nghĩa là không hề tốn accessor”

Không đúng. Với một record pattern, guard `when` được xét **sau khi pattern khớp**, nên accessor đã có thể được gọi để lấy component trước khi guard trả false. Nếu pattern không khớp từ kiểm tra kiểu, accessor của record đó không được gọi.

### 11.5. “Exception từ accessor tương đương pattern không khớp”

Sai. Một accessor ném lỗi khi record pattern đang matching khiến matching kết thúc đột ngột bằng `MatchException` có nguyên nhân gốc; không phải nhảy sang `default`. Nên có unit test cho hành vi lỗi khi accessor không bảo đảm thuần túy.

### 11.6. “Lấy component bằng var luôn loại trừ null”

Không đúng. Với component tham chiếu, `var` trong record pattern có thể ràng buộc giá trị `null`. Cần kiểm tra null trước khi gọi phương thức trên biến ấy. Trong khi đó, **giá trị selector `null` không khớp một record pattern**; hai tình huống khác nhau.

### 11.7. “Cứ tối ưu getter là code nhanh hơn”

Không nhất thiết. Chi phí đáng kể có thể nằm ở tạo object, thao tác mạng, truy vấn, lock hoặc thuật toán. Hãy profiling để biết phần nào thực sự nóng, rồi chỉ tối ưu phần gây ảnh hưởng.

## 12. Bài tập và câu hỏi tự kiểm tra

Cho record:

```java
record Report(String id, int score, String note) {}
```

**Câu 1.** Nếu chỉ cần biết `id` và pattern có ba component, nên chọn:

```java
if (input instanceof Report(var id, var score, var note)) {
    System.out.println(id);
}
```

hay:

```java
if (input instanceof Report report) {
    System.out.println(report.id());
}
```

**Đáp án:** Cả hai có thể hợp lệ. Nếu chỉ dùng `id` và các accessor khác có chi phí đáng kể, type pattern có thể dễ kiểm soát lượng công việc hơn. Nếu record đơn giản và record pattern giúp truyền đạt mục đích, khác biệt hiệu năng có thể không đáng kể; cần đo trên dữ liệu thực tế.

**Câu 2.** Với:

```java
case Report(var id, var score, var note) when score >= 80 -> "PASS";
case Report(var id, var score, var note) -> "RETRY";
```

đầu vào có `score = 79` sẽ đi qua điều gì?

**Đáp án:** Pattern đầu có thể khớp rồi guard sai; Java tiếp tục xét pattern thứ hai. Những accessor cần thiết cho mỗi lần phân rã có thể được gọi lặp lại. Nếu accessor có công việc đắt, cân nhắc một type pattern và đọc component một lần trong block.

**Câu 3.** Nếu explicit accessor `score()` ném `IllegalStateException` trong lúc record pattern đang khớp, `default` có nhận đầu vào đó không?

**Đáp án:** Không. Lỗi accessor làm pattern matching kết thúc đột ngột; theo Java 21, `MatchException` được ném với `cause` là lỗi gốc. Đây không phải kết quả “pattern không khớp”.

**Câu 4.** Một phép đo `System.nanoTime()` duy nhất cho thấy record pattern chậm hơn type pattern 20%. Có đủ để đổi toàn bộ code không?

**Đáp án:** Chưa. Phải kiểm soát JIT warm-up, loại trừ dead-code elimination, dùng workload tương đương, nhiều lần đo và đánh giá mức độ quan trọng thực tế. JMH và profiler phù hợp hơn cho quyết định hiệu năng.

## 13. Tổng kết và tài liệu nền

**Ghi nhớ:** Record pattern là cú pháp kiểm tra kiểu và **phân rã record thông qua accessor**, không phải một phép đọc field không chi phí. Accessor mặc định thường rất nhỏ và có thể được JVM tối ưu. Chi phí cần chú ý khi **accessor tùy chỉnh tốn tài nguyên**, **pattern lặp lại sau guard false**, **nhiều cấp record lồng nhau** hoặc **exception/side effect** làm thay đổi hành vi. Giữ code dễ đọc, lấy dữ liệu một lần khi có lý do cụ thể, và **đo bằng benchmark/profiler** trước khi tối ưu.

Tài liệu chính thức để tra cứu ngữ nghĩa:

- **Java Language Specification 21, `14.30.2 – Pattern Matching:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2
- **JEP 440 – Record Patterns (Java 21):** https://openjdk.org/jeps/440
- **Oracle Java – Record Patterns:** https://docs.oracle.com/en/java/javase/21/language/record-patterns.html

Bài viết áp dụng các cú pháp record patterns và pattern matching for `switch` đã chính thức từ **Java 21**; các ví dụ chương trình chính dùng JDK 21 trở lên và không cần chế độ preview.
