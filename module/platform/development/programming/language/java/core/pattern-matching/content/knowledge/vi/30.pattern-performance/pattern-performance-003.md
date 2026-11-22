# Pattern `switch` và số lượng nhánh: hiểu hiệu năng, đo đúng và tối ưu đúng

## 1. Vấn đề đặt ra

Khi dùng **pattern matching for `switch`** trong Java 21, một phương thức có thể phân loại nhiều kiểu giá trị:

```java
static String kind(Object value) {
    return switch (value) {
        case String s -> "string";
        case Integer i -> "integer";
        case Long l -> "long";
        case Double d -> "double";
        case Boolean b -> "boolean";
        case null -> "null";
        default -> "other";
    };
}
```

Khi thêm nhiều `case`, câu hỏi thường gặp là: **“`switch` có 20 hay 50 nhánh có chậm hơn `switch` có 5 nhánh không?”** Câu trả lời chính xác là: **không thể kết luận chỉ bằng cách đếm số nhánh**.

Hiệu năng thực tế còn phụ thuộc vào:

- **Phân bố dữ liệu đầu vào**: tần suất rơi vào từng kiểu/nhánh, dữ liệu `null`, tỉ lệ `default`.
- **Bản chất nhãn `case`**: type pattern, constant label, record pattern, guard `when`, hoặc case tổng quát.
- **Thứ tự các pattern có thể cùng khớp**: Java chọn nhãn phù hợp đầu tiên theo ngữ nghĩa của `switch`.
- **Chi phí riêng của guard và thân nhánh**: gọi phương thức, đọc accessor, cấp phát, I/O, truy vấn dữ liệu.
- **Kiểu tĩnh của selector**: `Object`, enum, sealed interface, type generic...
- **`javac`, JVM, JIT, trạng thái warmup và call-site profile**: chiến lược hiện thực/tối ưu không được cố định bởi số dòng source.

Bài học này tập trung vào **hiệu năng liên quan số lượng và cấu trúc nhánh** của pattern `switch`, không nhằm thay thế toàn bộ kiến thức về cú pháp `switch`.

**Phiên bản:** Pattern matching for `switch` và record patterns chính thức từ **Java 21** (JEP 441, JEP 440). Các ví dụ dùng `javac --release 21` với JDK 21 trở lên.

## 2. Điều gì được Java bảo đảm, điều gì chỉ là chi tiết tối ưu?

Phải tách **ngữ nghĩa** khỏi **chiến lược thực thi**:

| Điều cần biết | Java bảo đảm gì? | Không được tự suy ra |
| --- | --- | --- |
| Nhiều `case` có thể khớp cùng selector | Chọn `case` phù hợp đầu tiên theo quy tắc matching/dominance | Mỗi `case` luôn tương ứng một phép `instanceof` được thực thi tuyến tính |
| Guard `when` | Chỉ đánh giá khi pattern trước nó khớp; guard sai thì tiếp tục tìm case thích hợp | Guard luôn được gọi một lần cho mọi input |
| Record pattern | Kiểm tra cấu trúc và giải cấu trúc component theo quy tắc Java | Truy cập component luôn miễn phí, hoặc luôn đắt hơn gọi accessor trực tiếp |
| Exhaustiveness | Compiler có thể kiểm tra đủ nhánh đối với sealed/enum/generic coverage | Exhaustiveness tự làm dispatch nhanh hơn |
| `default` | Tạo đường xử lý còn lại theo quy tắc chọn nhãn | `default` tự xử lý selector `null` |
| Số nhánh source | Cho biết độ phức tạp logic cần review | Thời gian chạy nhất thiết tỉ lệ thuận với N |

`switch` có thứ tự ngữ nghĩa nhưng trình biên dịch và JVM **có quyền tối ưu** cách chọn nhánh miễn giữ hành vi quan sát được. Vì thế những khẳng định kiểu **“20 case = 20 lần kiểm tra kiểu ở mọi lượt”**, **“tăng gấp đôi case = chậm gấp đôi”** hoặc **“pattern switch luôn nhanh hơn `if/else`”** đều không có cơ sở nếu chưa đo trên JDK và workload cụ thể.

Trong JDK 21, API [`java.lang.runtime.SwitchBootstraps`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/runtime/SwitchBootstraps.html) cung cấp bootstrap cho các `invokedynamic` call site liên quan chọn nhãn `switch` theo kiểu. Phương thức `typeSwitch` nhận selector, chỉ số bắt đầu tìm tiếp và các nhãn; nó trả về vị trí nhãn phù hợp, hoặc giá trị báo không có nhãn phù hợp. Đây là thông tin hữu ích khi đọc bytecode, **không phải bảo đảm JLS rằng mọi `switch` đều phải có cùng bytecode, cùng thuật toán hay cùng độ phức tạp** trên mọi JDK.

## 3. Số nhánh nhiều không đồng nghĩa số phép kiểm tra nhiều

Ví dụ cùng một selector kiểu `Object`, phương thức sau có bảy nhánh pattern kiểu:

```java
static int dispatch(Object value) {
    return switch (value) {
        case String s -> s.length();
        case Integer n -> n;
        case Long n -> n.intValue();
        case Double n -> n.intValue();
        case Float n -> n.intValue();
        case Character c -> c;
        case Boolean b -> b ? 1 : 0;
        case null -> -1;
        default -> 0;
    };
}
```

Phần `case String s` có thể được chọn với chuỗi mà không cần thực hiện logic của các nhánh `Long`, `Double`, `Float`... ở **mức ngữ nghĩa**. Việc JVM thực hiện bao nhiêu phép so sánh vật lý là chuyện khác, vì JIT có thể tối ưu hoặc kết hợp kiểm tra.

Bản thân việc tăng số case cũng có thể kéo theo **mã sinh ra lớn hơn, thêm nhãn, thêm logic guard**, nhưng tác động thực tế phụ thuộc quy mô và profile. Khi mã lớn đến mức ảnh hưởng đến inlining, instruction cache hoặc thời gian JIT, cần đo thay vì suy đoán.

Nếu `case` mới hầu như không bao giờ khớp với workload thường gặp, tác động có thể khác với việc thêm case xử lý một kiểu chiếm phần lớn request. **Phân bố kiểu đầu vào là một thành phần của benchmark**, không phải yếu tố phụ.

## 4. Ví dụ runnable: nhiều type pattern nhưng một kết quả xác định

Lưu vào `TypeSwitchDemo.java`:

```java
import java.util.List;

public class TypeSwitchDemo {
    record Point(int x, int y) {}

    static String classify(Object value) {
        return switch (value) {
            case String s -> "String:" + s;
            case Integer n -> "Integer:" + n;
            case Long n -> "Long:" + n;
            case Double d -> "Double:" + d;
            case Boolean b -> "Boolean:" + b;
            case Point(var x, var y) -> "Point:" + (x + y);
            case List<?> xs -> "List:" + xs.size();
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object[] values = {
            "x", 3, 4L, 2.5, true,
            new Point(2, 3), List.of(1, 2),
            null, new Object()
        };

        for (Object value : values) {
            System.out.println(classify(value));
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 21 TypeSwitchDemo.java
java TypeSwitchDemo
```

Stdout:

```text
String:x
Integer:3
Long:4
Double:2.5
Boolean:true
Point:5
List:2
null
other
```

Chương trình có nhiều nhãn khác nhau, gồm type pattern (`String`, `Integer`...), **record pattern** (`Point(var x, var y)`), một type pattern với **wildcard generic** (`List<?>`), `case null` và `default`.

Các nhánh có chi phí nội tại rất khác nhau: nối chuỗi để tạo output, cộng hai `int`, gọi `size()` trên collection... Nếu đem cả `classify` vào benchmark rồi thấy khác biệt giữa các input, **không thể tự quy toàn bộ khác biệt đó về vị trí case**. Chi phí của nhánh đang chạy đã khác.

**Lưu ý generic:** `case List<?> xs` chỉ xác nhận runtime là `List`; nó không kiểm tra type argument của từng phần tử. Đừng thay bằng raw `List` để “tối ưu” type erasure.

## 5. Thứ tự pattern: ưu tiên tính đúng trước khi nghĩ đến tốc độ

Các pattern có quan hệ kiểu cha–con có thể cùng nhận một object. Java có quy tắc **dominance** để ngăn nhánh chắc chắn không bao giờ tới.

Đoạn sau **cố ý không biên dịch**:

```java
static String wrong(Object value) {
    return switch (value) {
        case CharSequence seq -> "sequence";
        case String text -> "string"; // Bị case phía trên che.
        default -> "other";
    };
}
```

`String` implements `CharSequence`, nên nếu case `CharSequence` không có guard đứng trước, một giá trị `String` luôn bị case đó nhận. Compiler báo lỗi `case String` bị dominated.

Cách hợp lệ là đặt **kiểu chuyên biệt trước kiểu tổng quát**:

```java
static String correct(Object value) {
    return switch (value) {
        case String text -> "string";
        case CharSequence seq -> "sequence";
        default -> "other";
    };
}
```

Hai đoạn là **minh họa trong ngữ cảnh đã có class**, không phải hai tệp Java độc lập.

Không nên cố đảo kiểu tổng quát lên trước để “tăng cache hit” nếu việc đó làm sai logic hoặc bị compiler từ chối. Thứ tự cần thỏa **quan hệ subtype**, **dominance**, các hằng cụ thể và **nghĩa nghiệp vụ** trước tiên. Sau đó mới tối ưu nơi thật sự có vấn đề hiệu năng.

Với các kiểu không liên quan (`String` và `Integer`), đổi thứ tự có thể giữ nguyên kết quả, nhưng **không có cam kết rằng đổi thứ tự sẽ cải thiện throughput**: cần đo với phân bố thực tế, JDK thực tế.

## 6. Guard `when`: chi phí phát sinh ở nhánh nào?

Một guard chỉ được đánh giá khi **pattern tương ứng đã khớp**. Guard có thể đơn giản như `s.length() >= 4` hoặc tốn chi phí như một phương thức thực hiện regex, lookup hay tính toán phức tạp.

Lưu vào `GuardOrderDemo.java`:

```java
public class GuardOrderDemo {
    static int checks = 0;

    static boolean isLong(String text) {
        checks++;
        return text.length() >= 4;
    }

    static String classify(Object value) {
        return switch (value) {
            case String text when isLong(text) ->
                    "long:" + text;

            case String text ->
                    "short:" + text;

            case Integer number ->
                    "int:" + number;

            case Long number ->
                    "long-number:" + number;

            case null ->
                    "null";

            default ->
                    "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("java") + " checks=" + checks);
        System.out.println(classify("go") + " checks=" + checks);
        System.out.println(classify(7) + " checks=" + checks);
        System.out.println(classify(null) + " checks=" + checks);
    }
}
```

```bash
javac --release 21 GuardOrderDemo.java
java GuardOrderDemo
```

Stdout:

```text
long:java checks=1
short:go checks=2
int:7 checks=2
null checks=2
```

Đây là ví dụ **đếm lần guard được gọi**, không phải benchmark về thời gian. Với `"java"` và `"go"`, pattern `String` khớp, nên guard chạy; với `Integer` hoặc `null`, guard `isLong` không chạy. Giá trị `"go"` không thỏa guard nên được nhánh `String` tổng quát xử lý.

**Bài học về hiệu năng:**

- Guard nặng đặt trên nhánh có tần suất cao có thể tốn nhiều hơn cả việc chọn kiểu.
- Guard không phù hợp có thể khiến engine tiếp tục xét nhãn tiếp theo.
- Đặt guard chứa side effect trong code production thường làm `switch` khó hiểu, khó benchmark và khó bảo trì. `checks++` ở đây **chỉ là dụng cụ minh họa**.
- Hai guard có cùng kiểu nhưng kiểm tra điều kiện khác nhau cần giữ thứ tự và kết quả đúng như yêu cầu nghiệp vụ.

Nếu một case tổng quát không guard đứng trước case cụ thể, case cụ thể có thể bị dominated. Ngược lại, với pattern có guard mà compiler không chứng minh là luôn đúng, việc chọn nhánh phụ thuộc vào kết quả guard khi chạy.

## 7. Nhiều guard trong cùng kiểu: tối ưu logic thay vì cứ thêm `case`

Ví dụ:

```java
static String rate(Object value) {
    return switch (value) {
        case Integer n when n >= 100 -> "high";
        case Integer n when n >= 50 -> "medium";
        case Integer n when n >= 0 -> "low";
        case Integer n -> "negative";
        default -> "not-an-integer";
    };
}
```

Ở đây, với `Integer`, các guard được dùng để phân nhóm giá trị. Số nhánh tăng lên nhưng mục tiêu đầu tiên là **định nghĩa các miền không chồng chéo sai**. `n=120` phải là `"high"`; `n=70` là `"medium"`; `n=20` là `"low"`; `n=-2` là `"negative"`.

Nếu có hàng trăm ngưỡng, việc khai báo hàng trăm `case` có thể làm source khó đọc. Khi đó nên cân nhắc **thuật toán tìm kiếm/range table rõ ràng**, hoặc một nhánh `case Integer n` gọi helper phân loại. Chỉ chọn cấu trúc mới sau khi xem xét chi phí đọc bảng, locality, các ngưỡng động và kết quả benchmark.

Lưu ý: chuyển từ nhiều `case ... when` sang một helper là thay đổi cấu trúc chương trình. Cần kiểm thử các giá trị biên và giữ thứ tự ưu tiên để không vô tình đổi hành vi.

## 8. Record pattern: chi phí nằm cả ở việc giải cấu trúc

`switch` với record pattern vừa chọn subtype, vừa lấy component:

```java
record Price(long cents) {}
record Invoice(String id, Price price) {}

static String describe(Object value) {
    return switch (value) {
        case Invoice(var id, Price(var cents)) ->
                id + ":" + cents;

        case Invoice invoice ->
                "missing-price:" + invoice.id();

        default ->
                "other";
    };
}
```

Các đoạn trên là **mã minh họa đặt cùng trong một class/phạm vi**, không phải tệp độc lập.

Với `Invoice` chứa `Price`, JVM cần thực hiện việc matching và lấy component được pattern yêu cầu. Nếu `Price` component là `null`, pattern lồng `Price(var cents)` không khớp, nên nhánh `Invoice invoice` phía sau có thể chạy.

Về hiệu năng:

- Record pattern **không tự tạo bản sao** của record để giải cấu trúc.
- Java có thể phải **gọi accessor** của các component. Nếu accessor được viết lại với logic đắt tiền, chính logic ấy ảnh hưởng hiệu năng.
- Record pattern lồng nhiều tầng có thể tạo thêm matching/đọc component, đặc biệt khi gặp nhiều null hoặc dữ liệu không khớp ở tầng sâu.
- Tuy nhiên, cách viết tương đương bằng `instanceof` rồi gọi accessor thủ công **cũng có thể phải làm những công việc tương tự**. Không thể kết luận record pattern luôn nhanh/chậm hơn cách viết thủ công chỉ bằng cú pháp.

Nếu một pattern quá dài, hãy cân nhắc tách thành helper, hoặc dùng type pattern rồi xử lý component có kiểm soát. Việc tách chỉ đáng gọi là tối ưu hiệu năng khi đo được khác biệt trên workload thật.

## 9. Sealed hierarchy giúp kiểm soát nhánh, không bảo đảm tốc độ

`sealed` giới hạn các subtype trực tiếp được cho phép. Kết hợp với `switch` exhaustive có thể giữ source rõ ràng và buộc cập nhật khi có subtype mới.

Lưu vào `SealedRoutingDemo.java`:

```java
public class SealedRoutingDemo {
    sealed interface Event
            permits Created, Charged, Cancelled, Failed {}

    record Created(String id) implements Event {}
    record Charged(String id, long cents) implements Event {}
    record Cancelled(String id) implements Event {}
    record Failed(String id, String reason) implements Event {}

    static String route(Event event) {
        return switch (event) {
            case Created(var id) ->
                    "created:" + id;

            case Charged(var id, var cents) when cents >= 1000 ->
                    "large-charge:" + id;

            case Charged(var id, var cents) ->
                    "charge:" + id + ":" + cents;

            case Cancelled(var id) ->
                    "cancelled:" + id;

            case Failed(var id, var reason) ->
                    "failed:" + id + ":" + reason;

            case null ->
                    "null";
        };
    }

    public static void main(String[] args) {
        Event[] events = {
            new Created("O1"),
            new Charged("O2", 500),
            new Charged("O3", 1500),
            new Cancelled("O4"),
            new Failed("O5", "limit"),
            null
        };

        for (Event event : events) {
            System.out.println(route(event));
        }
    }
}
```

```bash
javac --release 21 SealedRoutingDemo.java
java SealedRoutingDemo
```

Stdout:

```text
created:O1
charge:O2:500
large-charge:O3
cancelled:O4
failed:O5:limit
null
```

Ở đây, `switch` không cần `default` vì đã xử lý toàn bộ subtype `Event` và bổ sung `case null`. Nếu sau này thêm subtype `Refunded`, compiler có thể yêu cầu cập nhật `switch` khi build lại.

Điểm này là **bảo đảm tính đầy đủ về thiết kế domain**. Nó không đồng nghĩa sealed hierarchy nhất thiết dispatch nhanh hơn interface mở hay `if/else`. Có thể sealed giúp một số tối ưu trong ngữ cảnh cụ thể, nhưng **không biến thuộc tính exhaustive thành một cam kết về thời gian thực thi**.

Khi thêm subtype, cả số nhánh và tần suất dữ liệu từng nhánh có thể thay đổi. Muốn so sánh trước/sau, cần **chuẩn hóa workload hoặc báo cáo rõ phân bố mới**.

## 10. So sánh `switch` với `if/else instanceof`: đừng so khác logic

Hai cách dưới đây tương đương về kết quả với những input thông thường đã nêu:

```java
static int byIf(Object value) {
    if (value instanceof String text) {
        return text.length();
    }
    if (value instanceof Integer number) {
        return number;
    }
    return 0;
}

static int bySwitch(Object value) {
    return switch (value) {
        case String text -> text.length();
        case Integer number -> number;
        default -> 0;
    };
}
```

Đây là **hai phương thức minh họa trong cùng class**, không phải tệp độc lập. Khi `value == null`, `byIf` trả `0`, còn `bySwitch` không có `case null` có thể ném `NullPointerException`! Vì vậy, muốn **tương đương đầy đủ** với `null`, phải thêm:

```java
case null -> 0;
```

vào `bySwitch` hoặc ràng buộc đầu vào không-null và chỉ benchmark các input hợp lệ theo hợp đồng.

Một benchmark công bằng phải đảm bảo cả hai phương thức:

- Chấp nhận cùng tập input.
- Trả cùng kết quả cho input có trong workload.
- Có cùng chính sách `null`, lỗi và validation.
- Làm cùng lượng công việc thật trong body của nhánh.

Nếu một bên tạo chuỗi còn bên kia chỉ trả số nguyên, kết quả đo **không phản ánh chênh lệch chi phí dispatch**. Nếu một bên thêm `default` và làm mất kiểm tra nghiệp vụ, đó cũng không còn là cùng logic.

## 11. Phân biệt pattern `switch`, enum `switch` và các hằng số

Một `switch` trên `enum` hoặc hằng `int`/`String` thường có điều kiện và khả năng tối ưu **khác** một pattern `switch` với các kiểm tra kiểu và guard. Chẳng hạn:

```java
enum State { NEW, RUNNING, DONE }

static int simple(State state) {
    return switch (state) {
        case NEW -> 1;
        case RUNNING -> 2;
        case DONE -> 3;
    };
}
```

Lúc so sánh hiệu năng, đừng lấy một `switch` trên enum đã có mã phân loại làm đối chứng “cùng vấn đề” với `switch(Object)` cần tự phân biệt runtime type. Hai bài toán có **thông tin kiểu đầu vào khác nhau**.

Nếu domain vốn đã mô tả tốt bằng enum hằng và không có payload theo biến thể, enum có thể là cấu trúc hợp lý. Nếu các biến thể có dữ liệu và hành vi khác nhau, sealed interface + records + pattern `switch` có thể giúp model an toàn kiểu hơn. Quyết định thiết kế không nên bị chi phối bởi một microbenchmark thiếu kiểm soát.

Ngoài ra, `case "READY"` (constant label) không giống `case String text` (type pattern): một cái phân loại **giá trị hằng**, cái kia nhận **mọi chuỗi**. Không xem chúng là những nhánh tương đương chỉ vì cùng dùng chữ `String`.

## 12. JIT, profile dữ liệu và vì sao benchmark ngắn dễ sai

JVM có thể quan sát kiểu selector trong quá trình thực thi rồi tối ưu mã nóng (*hot code*). Kết quả có thể đổi tùy:

- JDK vendor/phiên bản và cờ JVM.
- Mức độ warmup, thời điểm tiered compilation/JIT hoạt động.
- Tần suất của từng kiểu tại call site (*type profile*).
- Kích thước phương thức, khả năng inline helper và thân nhánh.
- Phân bố dữ liệu nóng/lạnh và hành vi branch prediction của CPU.
- GC, cấp phát tạm, cache, hệ điều hành và môi trường máy.

Vì vậy, vòng lặp thử kiểu:

```java
long started = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    dispatch("hello");
}
System.out.println(System.nanoTime() - started);
```

**Không đủ để kết luận** `switch` nhanh/chậm: call có thể bị inline, kết quả có thể bị loại bỏ nếu không được dùng, input chỉ có một kiểu, benchmark tự trộn chi phí lặp/thời gian, hoặc JVM chưa warmup.

Đối với microbenchmark Java, nên dùng **JMH (Java Microbenchmark Harness)** của OpenJDK để kiểm soát fork, warmup, measurement và tiêu thụ kết quả. Không có con số nanosecond “chuẩn chung” cho số lượng nhánh; số đo chỉ có ý nghĩa khi đi kèm môi trường và workload.

## 13. Thiết kế JMH benchmark so sánh 2 và 7 type patterns

Một thử nghiệm rõ nghĩa là giữ nguyên cùng input (`String` và `Integer`) nhưng thay đổi **số case bổ sung**. Trong thử nghiệm này, cả hai phương thức trả **cùng kết quả** đối với toàn bộ input được benchmark.

Mục tiêu không phải chứng minh tốc độ luôn tăng/giảm theo N; mà là trả lời: “Với workload hiện tại chỉ gồm `String`/`Integer`, thêm năm pattern cho các kiểu hiếm gặp làm thay đổi hiệu năng đo được hay không?”

Dưới đây là ví dụ **dùng trong dự án JMH đã cấu hình annotation processing**, không phải một class độc lập biên dịch chỉ với JDK. Đặt trong package `org.sample` của dự án JMH và cấu hình compiler target **Java 21**.

`BranchCountBenchmark.java`:

```java
package org.sample;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@Fork(2)
public class BranchCountBenchmark {
    @Param({"STRING_HEAVY", "INTEGER_HEAVY"})
    public String distribution;

    private Object[] inputs;
    private int index;

    @Setup(Level.Trial)
    public void setup() {
        inputs = new Object[1024];

        for (int i = 0; i < inputs.length; i++) {
            boolean useString =
                    distribution.equals("STRING_HEAVY")
                            ? i % 8 != 0
                            : i % 8 == 0;

            inputs[i] = useString
                    ? "word-" + i
                    : Integer.valueOf(i);
        }
    }

    private Object next() {
        return inputs[(index++) & (inputs.length - 1)];
    }

    @Benchmark
    public int twoPatterns() {
        return dispatch2(next());
    }

    @Benchmark
    public int sevenPatterns() {
        return dispatch7(next());
    }

    private static int dispatch2(Object value) {
        return switch (value) {
            case String text -> text.length();
            case Integer number -> number.intValue();
            default -> 0;
        };
    }

    private static int dispatch7(Object value) {
        return switch (value) {
            case String text -> text.length();
            case Integer number -> number.intValue();
            case Long number -> number.intValue();
            case Double number -> number.intValue();
            case Float number -> number.intValue();
            case Character ch -> ch;
            case Boolean flag -> flag ? 1 : 0;
            default -> 0;
        };
    }
}
```

**Điều kiện của thử nghiệm:**

- `inputs` được tạo ở `@Setup(Level.Trial)`, nằm ngoài phương thức đo.
- `@Param` thay đổi tần suất hai loại input, không thay đổi tính đúng.
- `@State(Scope.Thread)` tránh chia sẻ `index` giữa các thread benchmark trong một state dùng chung.
- Hai phương thức đều trả `int`, JMH sẽ quản lý cách tiêu thụ kết quả của benchmark method để hạn chế việc loại bỏ công việc.
- Các case bổ sung trong `dispatch7` **không khớp với input của thử nghiệm**. Vì vậy, kết quả chỉ đánh giá tác động của thêm case trong **workload chủ yếu đi vào hai case đầu**, không chứng minh về mọi trường hợp.
- Không có input `null`; hai `switch` có cùng hành vi đối với mọi input đang dùng. Nếu muốn benchmark `null`, bổ sung cùng một `case null` ở cả hai phương thức và vào workload.

**Thiết lập dự án:** theo hướng dẫn [JMH chính thức](https://github.com/openjdk/jmh), có thể tạo dự án từ archetype Maven:

```bash
mvn archetype:generate \
  -DinteractiveMode=false \
  -DarchetypeGroupId=org.openjdk.jmh \
  -DarchetypeArtifactId=jmh-java-benchmark-archetype \
  -DgroupId=org.sample \
  -DartifactId=branch-bench \
  -Dversion=1.0
```

Sau khi tạo dự án, cấu hình `maven-compiler-plugin` để code benchmark được biên dịch bằng **JDK 21+** và `release` là **21**. Ví dụ phần cấu hình plugin:

```xml
<configuration>
    <release>21</release>
</configuration>
```

Đây là **một đoạn cấu hình bên trong plugin Maven**, không phải file `pom.xml` hoàn chỉnh. Cần bảo đảm các thiết lập source/target khác của template không mâu thuẫn và dự án JMH vẫn có annotation processing đúng cấu hình.

Thêm class benchmark vào `src/main/java/org/sample/`, sau đó:

```bash
cd branch-bench
mvn clean verify
java -jar target/benchmarks.jar BranchCountBenchmark
```

Lệnh build/run cần Maven và dependency JMH; mã benchmark này **không được xác nhận đã chạy ở đây**. Mục tiêu là cung cấp một fixture rõ ràng để tự đo trên máy và JDK đích. Kết quả gồm thời gian/operation, sai số, fork và parameter; **không điền sẵn số giả định**.

## 14. Diễn giải benchmark cho đúng

Giả sử JMH trả số đo cho `twoPatterns` và `sevenPatterns`. Trước khi tuyên bố bản nào nhanh hơn, cần xem:

1. Cả hai có cho **kết quả giống nhau** trên toàn bộ input đã chọn không?
2. Thời gian/operation khác biệt bao nhiêu so với **error interval** và độ ổn định giữa các fork?
3. Có kết quả nhất quán ở `STRING_HEAVY` và `INTEGER_HEAVY` không, hay chênh lệch đổi chiều?
4. Có đủ warmup để JIT ổn định chưa? Có dấu hiệu GC hoặc hệ thống khác chiếm tài nguyên không?
5. Kết luận có giữ được khi thêm workload **kiểu ở gần cuối**, các trường hợp `default`, `null`, guard đúng/sai không?
6. Có đang so một phương thức thực sự làm nhiều công việc hơn ở body không?
7. Kết quả có tái lập trên **JDK phiên bản triển khai** không?

JMH đo microbenchmark trên JVM có thể không phản ánh toàn bộ độ trễ của request thật. Một service có thể bị chi phối bởi database, network hoặc JSON parsing; lúc ấy tối ưu một phép chọn kiểu vài nanosecond gần như không có tác động đến latency đầu-cuối.

**Thống kê nên ghi lại:** JDK/vendor/version, CPU, OS, chế độ JVM, số fork, warmup/measurement, phân bố input, đơn vị đo, estimate và độ bất định. Không chỉ lưu một số duy nhất rồi dùng làm quy tắc vĩnh viễn.

## 15. Khi muốn đo “nhánh ở cuối” hoặc “default”

Benchmark 2-vs-7 ở trên chỉ dùng hai type phổ biến. Để đánh giá trường hợp khác, thiết kế thêm fixture riêng:

- **Late-match:** input rơi vào một type pattern nằm gần cuối về mặt source; giữ logic output giống nhau khi thay đổi bố trí case không liên quan.
- **No-match:** input không khớp pattern nào và đi `default`.
- **Guard-hit:** input khớp type và guard đúng.
- **Guard-miss:** input khớp type nhưng guard sai, cần tìm case tiếp.
- **Record-nested:** input là record có component con khớp/không khớp hoặc `null`.
- **Polymorphic mix:** nhiều loại runtime xuất hiện cùng call site theo tỉ lệ thực tế.
- **Null:** chỉ đo khi API thực sự cho phép `null`, và cả các phương thức so sánh đều xử lý đúng như nhau.

**Không nên chỉ đổi input mà vẫn diễn giải benchmark là tác động thuần của số lượng case**. Thay đổi phân bố đầu vào có thể đổi chi phí body, chuỗi phân loại, branch prediction và profile JIT cùng lúc.

Nếu cần benchmark tách chi phí dispatch, có thể để mỗi nhánh trả một số nguyên nhỏ và đảm bảo cùng giá trị với cùng input giữa các phương án. Nếu cần benchmark end-to-end, hãy để logic nghiệp vụ thật trong nhánh, rồi phân tích riêng chi phí chọn case so với việc bên trong case.

## 16. Đọc bytecode: có ích cho chẩn đoán, không phải “bảng xếp hạng tốc độ”

Sau khi biên dịch một ví dụ Java 21, có thể xem:

```bash
javap -c -p TypeSwitchDemo
```

Lệnh này cần class đã được biên dịch trong thư mục hiện tại. Có thể thấy những cấu trúc liên quan `invokedynamic`/`SwitchBootstraps`, các nhánh bytecode và phép lấy component tùy kiểu `switch` và JDK.

Đọc bytecode có ích để đặt câu hỏi:

- `javac` sinh call site hoặc nhãn như thế nào?
- Guard được đánh giá ở đâu?
- Cách xử lý `null` nằm ở đâu?
- Có lời gọi accessor hoặc chuyển kiểu nào xuất hiện?
- Kích thước mã thay đổi ra sao khi thêm case?

Nhưng **bytecode không phải mã máy cuối cùng**: JIT có thể inline, loại bỏ, tái sắp xếp hoặc tối ưu các kiểm tra mà vẫn giữ ngữ nghĩa. Vì vậy, `javap` là công cụ giải thích cấu trúc, còn **JMH/profiler** mới cung cấp bằng chứng về hiệu năng trên JVM đang dùng.

Cũng không nên lấy thuật toán nội bộ của một bản JDK rồi áp đặt cho mọi bản sau. `SwitchBootstraps` là API runtime của một phiên bản triển khai, không phải công thức hiệu năng không đổi.

## 17. Những tối ưu đáng cân nhắc khi switch thực sự là điểm nóng

**1. Giữ điều kiện rẻ và không có side effects.** Guard chạy trên đường đi matching. Nếu một guard gọi I/O, regex nặng hoặc truy cập dữ liệu bên ngoài, chi phí đó thường đáng kiểm tra trước khi tối ưu thứ tự các case.

**2. Tách công việc nặng khỏi logic phân loại khi phù hợp.** Một method phân loại nhẹ rồi gọi helper chuyên trách có thể dễ profile và test hơn, nhưng cũng có thể làm thay đổi khả năng inline. Đo trước/sau.

**3. Giảm lặp accessor/parse không cần thiết.** Nếu nhiều nhánh dùng cùng kết quả tính toán, có thể tiền xử lý một lần **khi điều đó không làm công việc thừa cho các case khác**. Đừng đưa tính toán đắt ra trước toàn bộ `switch` nếu chỉ vài nhánh cần.

**4. Giữ kiểu tĩnh càng chính xác càng tốt.** Nếu selector vốn là sealed interface hoặc enum, đừng đổi thành `Object` rồi bổ sung hàng loạt type checks không cần thiết. Bảo toàn kiểu giúp compiler kiểm tra exhaustiveness và có thể giúp mã dễ tối ưu hơn, nhưng không có bảo đảm tăng tốc.

**5. Khi số lượng “case nghiệp vụ” quá nhiều và biến động:** cân nhắc kiến trúc lookup table, handler registry, enum mapping hoặc polymorphic dispatch **nếu phù hợp với domain**. Registry/map có chi phí lookup và allocation/indirection riêng; không mặc định nhanh hơn `switch`.

**6. Đừng dùng `default` chỉ để rút ngắn danh sách case của sealed hierarchy.** Nó có thể che thiếu xử lý subtype mới; tính đúng và khả năng tiến hóa domain quan trọng hơn vài dòng code.

**7. Kiểm tra đường đi `null` và lỗi.** Thêm `case null` chỉ khi chính sách API cần; không vô tình đổi hành vi `NullPointerException` khi refactor.

Không có tối ưu nào phía trên nên được tuyên bố là “nhanh hơn” trước khi benchmark chứng minh trong điều kiện phù hợp.

## 18. Các lỗi thường gặp

| Hiểu nhầm | Vì sao sai hoặc thiếu | Cách xử lý |
| --- | --- | --- |
| “N case thì luôn chạy N lần `instanceof`” | Không phải hợp đồng của JLS, JIT có thể tối ưu | Đo dưới workload và JVM mục tiêu |
| “Thêm case luôn làm chậm tuyến tính” | Phụ thuộc kiểu dữ liệu, case match, guard, mã sinh | So sánh bằng JMH |
| “Đưa type rộng lên đầu sẽ nhanh hơn” | Có thể dominated hoặc làm đổi kết quả | Giữ subtype cụ thể trước kiểu tổng quát |
| “Guard không đáng kể” | Guard có thể gọi code tốn chi phí | Profile chi phí guard, test đúng/sai |
| “Record pattern luôn là cú pháp miễn phí” | Matching có thể truy cập component/accessor | Đo đúng đường đi, không giả định |
| “Sealed `switch` exhaustive là tối ưu tốc độ” | Exhaustiveness là thuộc tính kiểm tra bao phủ | Xem đây là bảo đảm correctness, đo performance riêng |
| “`default` xử lý cả null” | `null` thường cần case riêng hoặc bị NPE | Test chính sách `null` |
| “So `switch(Object)` với `switch(enum)` là công bằng” | Khác kiểu selector, dữ liệu và công việc | Dùng đối chứng cùng bài toán |
| “Đo 1 triệu lượt bằng `nanoTime` là đủ” | Warmup/JIT/Dead-code elimination làm sai số | Dùng JMH, fork, nhiều input |
| “Có benchmark nhanh hơn là nên refactor ngay” | Tác động end-to-end có thể rất nhỏ | Profile production, cân nhắc độ phức tạp |
| “Có nhiều case nên thay ngay bằng `HashMap`” | Lookup map có overhead và nghĩa khác pattern | Thiết kế thử nghiệm tương đương trước khi đổi |
| “Số nhánh là chỉ số hiệu năng duy nhất” | Thân case, allocation, IO, input distribution quan trọng | Đo toàn đường đi và phân tách chi phí |

## 19. Checklist khi review pattern `switch` có nhiều nhánh

Trước khi quyết định tối ưu, hãy xác nhận:

- Bạn đang dùng **Java 21 hay phiên bản khác**? Benchmark có trùng JDK triển khai không?
- Selector có kiểu tĩnh cụ thể hay bị hạ thành `Object`?
- Các case có đúng thứ tự **dominance**, hằng số, guard và subtype không?
- Có guard nào đắt, gọi I/O, tạo object hoặc có tác dụng phụ không?
- Record pattern có accessor tùy biến hoặc nhiều tầng deconstruction không?
- Dữ liệu thường đi vào case nào? Có case hiếm hoặc `default` không?
- `null` được xử lý rõ ràng và giống nhau giữa các phương án so sánh chưa?
- Các phương án benchmark có **cùng nghĩa và cùng kết quả** trên tập input không?
- JMH có warmup, fork, measurement, input đa dạng và tiêu thụ kết quả không?
- Chênh lệch có ổn định, đủ lớn và còn ý nghĩa trong **profiling end-to-end** không?
- Việc đổi cấu trúc có làm mất tính exhaustive, che case mới hoặc làm code khó đọc hơn không?

**Kết luận:** Trong pattern `switch`, **số lượng nhánh là một biến cần đo, không phải công thức dự đoán hiệu năng**. Hãy dùng kiểu domain chính xác, bảo toàn thứ tự và hành vi matching, giữ guard hợp lý, rồi đo bằng JMH trên workload đại diện. Chỉ tối ưu cấu trúc khi kết quả đo cho thấy `switch` thực sự là nút thắt và lợi ích đủ lớn để đánh đổi độ phức tạp.

## Tham khảo chính thức

- [JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [Oracle Java SE 21 — Pattern Matching for `switch` (guard, dominance, type coverage)](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 JLS §14.11 — `switch` Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 JLS §15.28 — `switch` Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [Java SE 21 API — `SwitchBootstraps`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/runtime/SwitchBootstraps.html)
- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh)
