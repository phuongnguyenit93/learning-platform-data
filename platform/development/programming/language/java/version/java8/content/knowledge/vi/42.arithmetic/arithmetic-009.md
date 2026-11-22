# Java số học: `sum`, `min`, `max` dùng như toán tử hàm

**Chủ đề cha:** Số học. **Đề bài:** Hiểu và dùng đúng các phương thức tĩnh `sum`, `min`, `max` của `Integer`, `Long`, `Double` và `Float` như các **hàm nhận hai toán hạng**. Trọng tâm là method reference (`Integer::sum`, `Long::max`, `Double::min`…), functional interface `IntBinaryOperator`/`LongBinaryOperator`/`DoubleBinaryOperator`/`BinaryOperator<T>`, `Stream.reduce`, toán tử gộp trong `Map.merge`/`Collectors.toMap` và `Arrays.parallelPrefix`; chọn identity đúng, tránh lỗi với tập rỗng, tràn số nguyên và số thực dấu phẩy động.

**Phạm vi phiên bản:** Những phương thức tĩnh `sum`/`min`/`max` trên các wrapper số nguyên/thực được bổ sung từ **Java 8**, hiện vẫn là API chuẩn được hỗ trợ. Tất cả ví dụ Java độc lập trong bài biên dịch bằng **JDK 17+**. Mục đích là nắm các cơ chế còn áp dụng trong Java hiện hành, không sử dụng API lỗi thời.

> **Tóm tắt:** `Integer::sum` là cách viết ngắn của hàm hai tham số `(a,b) -> a+b`; `Integer::min` là `(a,b) -> Math.min(a,b)`; `Integer::max` tương đương `(a,b) -> Math.max(a,b)`. Chúng **không tự duyệt collection, không giữ trạng thái, không tạo thread**. Chính `reduce`, `merge` hay `parallelPrefix` gọi toán tử đó để tích lũy/gộp. Chọn **đúng kiểu**, **đúng identity** và hiểu **ngữ nghĩa số học** quyết định kết quả; method reference chỉ là cú pháp truyền một thao tác vào nơi cần callback.

## 1. Hàm hai ngôi: Từ cú pháp thường tới method reference

Nếu hai giá trị `a`, `b` đều là `int`, Java có thể tính:

```java
int add = a + b;
int smaller = Math.min(a, b);
int larger = Math.max(a, b);
```

Đây là **đoạn minh họa trong một phương thức**; `a` và `b` cần được khai báo.

Từ Java 8, có thêm các phương thức tĩnh:

```java
int add = Integer.sum(a, b);
int smaller = Integer.min(a, b);
int larger = Integer.max(a, b);
```

Ba lời gọi trả kết quả giống các phép tương ứng. Lợi thế lớn của phương thức tĩnh không nằm ở tốc độ tính `a + b`, mà ở khả năng **truyền tham chiếu phương thức**:

```java
IntBinaryOperator addOperator = Integer::sum;
IntBinaryOperator minOperator = Integer::min;
IntBinaryOperator maxOperator = Integer::max;
```

Lúc này `addOperator`, `minOperator`, `maxOperator` là các **đối tượng hàm** có thể đưa cho API nhận `IntBinaryOperator`.

Đồng nghĩa với:

```java
IntBinaryOperator addOperator = (left, right) -> left + right;
IntBinaryOperator minOperator =
        (left, right) -> Math.min(left, right);
IntBinaryOperator maxOperator =
        (left, right) -> Math.max(left, right);
```

**Không phải closure chứa một accumulator:** `Integer::sum` **không nhớ** các giá trị trước đó; mỗi lần được gọi nó tính kết quả từ đúng hai toán hạng hiện tại. `IntStream.reduce` mới là nơi quản lý chuỗi các phép gộp.

### 1.1. Chữ ký mà compiler dựa vào

| Wrapper | `sum` | `min` | `max` | Kiểu kết quả |
| --- | --- | --- | --- | --- |
| `Integer` | `static int sum(int,int)` | `static int min(int,int)` | `static int max(int,int)` | `int` |
| `Long` | `static long sum(long,long)` | `static long min(long,long)` | `static long max(long,long)` | `long` |
| `Double` | `static double sum(double,double)` | `static double min(double,double)` | `static double max(double,double)` | `double` |
| `Float` | `static float sum(float,float)` | `static float min(float,float)` | `static float max(float,float)` | `float` |

Cả bốn wrapper đều có các phương thức này trong Java hiện hành. Không tồn tại một bộ `Byte::sum` hay `Short::sum` tương tự; với `byte`/`short`, phép số học Java thường được **numeric promotion** lên `int`, nên có thể chuyển sang `IntStream`/`IntBinaryOperator` tùy yêu cầu.

**Lưu ý về `Math`:** `Math.min`/`Math.max` cũng có các overload cho kiểu nguyên thủy; hai cách đều hợp lệ. `Integer::sum` giúp tham chiếu rõ phép cộng kiểu `int`, còn `Math::addExact` là phép cộng **kiểm tra overflow**, **không** cùng hành vi như `Integer::sum`.

### 1.2. Ý nghĩa của `::`

`Integer::sum` **không gọi** `sum` ngay tại vị trí viết. Nó là method-reference expression được compiler ghép với một **target functional interface**. Ví dụ:

```java
IntBinaryOperator op = Integer::sum;

int result = op.applyAsInt(7, 5); // 12
```

Đây là mã trong phương thức. Nếu viết `Integer.sum(7,5)`, phép tính xảy ra ngay; nếu viết `Integer::sum`, hàm được **truyền để gọi sau**.

Thông thường không thể viết `var op = Integer::sum;` vì method reference cần target type để suy luận kiểu hàm (Java 17 vẫn yêu cầu ngữ cảnh phù hợp). Hãy khai báo `IntBinaryOperator`, `BinaryOperator<Integer>` hoặc truyền trực tiếp cho method có tham số functional interface rõ ràng.

## 2. Các functional interface thích hợp

| Interface | Phương thức trừu tượng | Dạng dữ liệu | Ví dụ |
| --- | --- | --- | --- |
| `IntBinaryOperator` | `int applyAsInt(int,int)` | Hai `int`, trả `int` | `Integer::sum` |
| `LongBinaryOperator` | `long applyAsLong(long,long)` | Hai `long` | `Long::min` |
| `DoubleBinaryOperator` | `double applyAsDouble(double,double)` | Hai `double` | `Double::max` |
| `BinaryOperator<T>` | `T apply(T,T)` | Hai object cùng kiểu `T` | `Integer::sum` khi `T=Integer` |
| `BiFunction<T,U,R>` | `R apply(T,U)` | Hai kiểu đầu vào có thể khác | Có thể nhận tham chiếu phương thức tương thích |

Các primitive-specialized interfaces hạn chế **boxing/unboxing**, nhất là khi tính trên mảng số lớn hoặc primitive streams. `BinaryOperator<Integer>` hoạt động với object `Integer`; các phương thức `Integer.sum(int,int)` vẫn có thể được thích nghi qua unboxing đầu vào và boxing kết quả.

Ví dụ:

```java
import java.util.function.BinaryOperator;
import java.util.function.IntBinaryOperator;

IntBinaryOperator primitive = Integer::sum;
BinaryOperator<Integer> boxed = Integer::sum;

int x = primitive.applyAsInt(2, 3);
Integer y = boxed.apply(2, 3);
```

**Đây là đoạn bên trong class/method** (không đặt `import` trong thân method khi dùng thực tế). Kết quả `x == 5` và `y == 5`.

### 2.1. Không nhầm BinaryOperator với Comparator

`BinaryOperator<Integer> max = Integer::max` trả **một giá trị lớn hơn** trong hai giá trị. `Comparator<Integer>` thì trả một `int` **âm/0/dương** để thể hiện quan hệ thứ tự giữa hai object. Hai giao diện có chữ ký logic khác nhau dù cả hai có thể nhận hai đầu vào.

`Integer::compare` phù hợp với `Comparator<Integer>`; `Integer::max` phù hợp với `BinaryOperator<Integer>` hoặc `IntBinaryOperator`. Không thay thế ngẫu nhiên.

### 2.2. Method reference không đồng nghĩa hoàn toàn với mọi lambda có side effect

`Integer::sum` không có side effect và không giữ mutable state. Một lambda như `(a,b) -> { counter++; return a+b; }` **không tương đương về tính an toàn**, đặc biệt khi đưa vào parallel stream. Các accumulator của `reduce` phải đáp ứng contract stateless/non-interfering/associative; side effect dùng biến chung có thể gây race và kết quả phụ thuộc lịch chạy.

Nếu chỉ cần phép cộng, min, max trên số nguyên thủy, phương thức có sẵn thường rõ ý và dễ kiểm tra hơn một callback tự viết.

## 3. Ví dụ Java 17+: Các toán tử primitive và boxed

Tạo file **`ArithmeticOperatorsDemo.java`**:

```java
import java.util.function.BinaryOperator;
import java.util.function.DoubleBinaryOperator;
import java.util.function.IntBinaryOperator;
import java.util.function.LongBinaryOperator;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class ArithmeticOperatorsDemo {
    public static void main(String[] args) {
        int[] numbers = {8, -3, 5, 10};

        IntBinaryOperator sum = Integer::sum;
        IntBinaryOperator min = Integer::min;
        IntBinaryOperator max = Integer::max;

        System.out.println("Integer sum: "
                + IntStream.of(numbers).reduce(0, sum));
        System.out.println("Integer min: "
                + IntStream.of(numbers).reduce(
                        Integer.MAX_VALUE, min));
        System.out.println("Integer max: "
                + IntStream.of(numbers).reduce(
                        Integer.MIN_VALUE, max));

        LongBinaryOperator longSum = Long::sum;
        System.out.println("Long sum: "
                + LongStream.of(2_000_000_000L,
                        2_000_000_000L)
                        .reduce(0L, longSum));

        DoubleBinaryOperator doubleSum = Double::sum;
        System.out.println("Double sum: "
                + DoubleStream.of(3.5, -2.0, 4.25)
                        .reduce(0.0, doubleSum));

        BinaryOperator<Integer> boxedMax = Integer::max;
        System.out.println("Boxed max: "
                + boxedMax.apply(9, 12));

        System.out.println("Float sum: "
                + Float.sum(1.25f, 2.50f));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 ArithmeticOperatorsDemo.java
java ArithmeticOperatorsDemo
```

**Stdout xác định:**

```text
Integer sum: 20
Integer min: -3
Integer max: 10
Long sum: 4000000000
Double sum: 5.75
Boxed max: 12
Float sum: 3.75
```

**Phân tích:**

- Tổng `8 + (-3) + 5 + 10 = 20`.
- Min là `-3`; max là `10`.
- Hai số `2_000_000_000L` được cộng thành `4_000_000_000L`, vượt `int` nhưng còn trong `long`.
- Tổng `3.5 - 2.0 + 4.25 = 5.75` là giá trị có thể biểu diễn chính xác trong ví dụ nhỏ này.
- `BinaryOperator<Integer>` nhận hai `Integer`, còn `IntBinaryOperator` dùng `int`. Cả hai có thể dùng `Integer::max` đúng ngữ cảnh.
- `Float::sum` cũng là API hiện hành; dòng cuối gọi trực tiếp `Float.sum` để cho thấy overload `float` tồn tại.

**Đây là ví dụ về hợp đồng toán tử và reducer**, không phải benchmark chứng minh method reference nhanh hơn lambda. Compiler/runtime có thể tối ưu khác nhau, nên chọn theo độ rõ nghĩa và kiểu dữ liệu phù hợp trước.

## 4. `reduce`: Operator, identity và tính kết hợp

`IntStream.reduce(identity, op)` ghép nhiều phần tử thành một kết quả bằng hàm hai ngôi `op`. Khi stream có phần tử `x1, x2, x3`, cách hiểu tuần tự điển hình của tổng là:

```text
result = identity
result = op(result, x1)
result = op(result, x2)
result = op(result, x3)
...
```

Tuy nhiên **Stream API không bắt buộc mọi reduction được thực thi tuần tự**, đặc biệt khi gọi `parallel()`. Vì thế cần các tính chất đại số:

1. **Associative:** `op(op(a,b),c)` phải có kết quả tương thích với `op(a,op(b,c))`.
2. **Identity:** `op(identity,x) == x` cho mọi `x` của miền giá trị, và theo hợp đồng hai chiều của phép toán.
3. **Stateless/non-interfering:** Hàm không dựa vào hoặc sửa dữ liệu shared mutable ngoài stream.
4. **Kiểu dữ liệu và ngữ nghĩa đúng:** Phép cộng có thể overflow hoặc trôi sai số, dù code đúng kiểu.

`sum`, `min`, `max` trên `int` là các phép gộp hợp lý, miễn là chấp nhận ngữ nghĩa overflow của `int`. Với số thực `double`, phép cộng **không kết hợp tuyệt đối** do rounding; xem phần riêng để không hứa các kết quả bit-for-bit giống nhau khi song song.

### 4.1. Chọn identity đúng

| Phép toán | Kiểu | Identity phù hợp cho `reduce(identity, op)` |
| --- | --- | --- |
| Tổng | `int` | `0` |
| Tổng | `long` | `0L` |
| Tổng | `double` | Thông thường `0.0` về giá trị số học; chú ý dấu `±0.0` |
| Min | `int` | `Integer.MAX_VALUE` |
| Max | `int` | `Integer.MIN_VALUE` |
| Min | `long` | `Long.MAX_VALUE` |
| Max | `long` | `Long.MIN_VALUE` |
| Min | `double` | `Double.POSITIVE_INFINITY` |
| Max | `double` | `Double.NEGATIVE_INFINITY` |
| Min/Max | `float` | `Float.POSITIVE_INFINITY` / `Float.NEGATIVE_INFINITY` |

Vì sao min không dùng 0? Với tập các số dương `[4,7,2]`, gọi `reduce(0,Integer::min)` sẽ trả **0**, mặc dù **0 không xuất hiện** trong dữ liệu. Identity đúng là `Integer.MAX_VALUE`, vì `min(MAX_VALUE,x)==x` với mọi giá trị `int`.

Vì sao max không dùng 0? Với tập toàn âm `[-7,-2,-5]`, `reduce(0,Integer::max)` sẽ trả **0** dù max thực tế là `-2`. Identity đúng là `Integer.MIN_VALUE`.

### 4.2. Min và max là các phép có tính idempotent

`min(x,x)==x` và `max(x,x)==x`. Ngoài tính kết hợp, min/max còn có tính **giao hoán** đối với `int/long`: `min(a,b)==min(b,a)`. Những tính chất đó làm chúng phù hợp cho phép gộp kết quả từ nhiều partition.

`sum` giao hoán trên toán học số nguyên, nhưng `int/long` của Java có overflow. Với phép cộng thường, kết quả là **wrap-around theo độ rộng bit cố định**, nên phép cộng vẫn có tính kết hợp theo số học modulo tương ứng; dù vậy kết quả có thể **không bằng tổng toán học chính xác**. Không biến tính chất kỹ thuật của wrap-around thành lý do dùng `Integer::sum` cho kế toán cần kết quả không tràn.

### 4.3. Reduce có identity và không có identity

```java
int total = IntStream.of(4, 7, 2)
        .reduce(0, Integer::sum); // 13

OptionalInt minimum = IntStream.of(4, 7, 2)
        .reduce(Integer::min);    // Có giá trị 2

OptionalInt nothing = IntStream.empty()
        .reduce(Integer::min);    // OptionalInt.empty()
```

Đây là mã trong method (import `OptionalInt` và `IntStream` nếu cần). Overload `reduce(IntBinaryOperator)` không yêu cầu identity, trả `OptionalInt` vì stream có thể **rỗng**.

**Khuyến nghị:** Khi làm min/max trên dữ liệu có thể rỗng, `IntStream.min()`/`max()` hoặc `reduce(Integer::min/max)` trả `OptionalInt` thường **diễn đạt tốt hơn** so với dùng sentinel `MAX_VALUE`/`MIN_VALUE` rồi đoán stream rỗng.

## 5. Tập rỗng: Không đánh đồng "không có dữ liệu" với một giá trị số

Đây là điểm nghiệp vụ dễ sai:

- Tổng của tập rỗng theo định nghĩa reducer có identity 0 là **0**.
- Min/max của tập rỗng **không có phần tử để chọn**, nên các terminal operations chuẩn `IntStream.min`/`max` trả `OptionalInt.empty()`.
- `reduce(Integer.MAX_VALUE, Integer::min)` trên tập rỗng trả `Integer.MAX_VALUE` **theo hợp đồng identity**, không phải "minimum thực sự" của một tập không có dữ liệu.
- Tương tự `reduce(Double.POSITIVE_INFINITY, Double::min)` trả `+Infinity` cho tập rỗng; đây là **sentinel**, không phải một minimum phát hiện từ dữ liệu.

Nếu dữ liệu có thể chứa thật `Integer.MAX_VALUE` hoặc `Double.POSITIVE_INFINITY`, chỉ nhìn giá trị sentinel **không thể phân biệt** tập rỗng với tập có phần tử tương ứng.

### 5.1. Chọn API trực tiếp khi đơn giản hơn

`IntStream` có `sum()`, `min()`, `max()`, `summaryStatistics()`. Nếu chỉ cần một tổng, viết `data.sum()` thường rõ ràng hơn `data.reduce(0,Integer::sum)`. Method reference đặc biệt có ích khi **API khác** cần một toán tử gộp được truyền vào, hoặc khi bạn đang học cách biểu diễn generic reduction.

Không thể dùng **cùng một đối tượng stream** cho cả ba terminal operations; muốn ba kết quả, tạo stream mới hoặc dùng `summaryStatistics` khi phù hợp.

### 5.2. Java 17+ runnable: Identity đúng và sai

Tạo file **`ReductionIdentityDemo.java`**:

```java
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;

public class ReductionIdentityDemo {
    public static void main(String[] args) {
        int[] positive = {4, 7, 2};
        int[] negative = {-7, -2, -5};

        System.out.println("Wrong min with zero: "
                + IntStream.of(positive)
                        .reduce(0, Integer::min));
        System.out.println("Correct min: "
                + IntStream.of(positive)
                        .reduce(Integer.MAX_VALUE, Integer::min));

        System.out.println("Wrong max with zero: "
                + IntStream.of(negative)
                        .reduce(0, Integer::max));
        System.out.println("Correct max: "
                + IntStream.of(negative)
                        .reduce(Integer.MIN_VALUE, Integer::max));

        System.out.println("Empty sum: "
                + IntStream.empty()
                        .reduce(0, Integer::sum));
        System.out.println("Empty min present: "
                + IntStream.empty().min().isPresent());
        System.out.println("Empty reduce min present: "
                + IntStream.empty()
                        .reduce(Integer::min).isPresent());
        System.out.println("Empty double min identity: "
                + DoubleStream.empty()
                        .reduce(Double.POSITIVE_INFINITY,
                                Double::min));
        System.out.println("Empty double max identity: "
                + DoubleStream.empty()
                        .reduce(Double.NEGATIVE_INFINITY,
                                Double::max));
    }
}
```

Chạy:

```bash
javac --release 17 ReductionIdentityDemo.java
java ReductionIdentityDemo
```

**Stdout:**

```text
Wrong min with zero: 0
Correct min: 2
Wrong max with zero: 0
Correct max: -2
Empty sum: 0
Empty min present: false
Empty reduce min present: false
Empty double min identity: Infinity
Empty double max identity: -Infinity
```

**Ý nghĩa:** Hai dòng `Wrong` là **lỗi cố ý** để chứng minh identity sai làm thay đổi kết quả. `OptionalInt` giữ được sự khác biệt giữa "có min" và "không có phần tử". Nếu muốn cung cấp giá trị mặc định cho tập rỗng, hãy quyết định **ở tầng nghiệp vụ**, ví dụ `orElse(fallback)`, và giải thích fallback đó là chính sách của ứng dụng chứ không phải min từ dữ liệu.

## 6. Khi truyền vào Stream, không cần tự viết vòng lặp gộp

Một số cách tính tổng `int` cùng mang ý nghĩa:

```java
int a = IntStream.of(1, 2, 3).sum();

int b = IntStream.of(1, 2, 3)
        .reduce(0, Integer::sum);

int c = IntStream.of(1, 2, 3)
        .reduce(0, (x, y) -> x + y);
```

Cả ba đều trả 6. `sum()` ngắn gọn nhất cho yêu cầu chỉ tính tổng; `reduce` cho thấy cách truyền toán tử hai ngôi.

Tương tự:

```java
OptionalInt a = IntStream.of(1, 2, 3).min();
OptionalInt b = IntStream.of(1, 2, 3)
        .reduce(Integer::min);

OptionalInt c = IntStream.of(1, 2, 3).max();
OptionalInt d = IntStream.of(1, 2, 3)
        .reduce(Integer::max);
```

Về mặt kết quả trên dữ liệu không có side effects, từng cặp tương ứng có cùng giá trị.

### 6.1. So sánh primitive stream và boxed stream

| Kịch bản | Dạng đơn giản | Đặc điểm |
| --- | --- | --- |
| Mảng `int[]` | `Arrays.stream(a).sum()` | `IntStream`, không boxing từng phần tử |
| `List<Integer>` | `list.stream().mapToInt(Integer::intValue).sum()` | Chuyển từ object stream sang primitive |
| `Stream<Integer>` | `stream.reduce(0,Integer::sum)` | `BinaryOperator<Integer>`, có thể boxing |
| Cần min int và xét rỗng | `IntStream.min()` | Trả `OptionalInt` |
| Cần max đối tượng theo thuộc tính | `stream.max(Comparator.comparing(...))` | Không dùng `Integer::max` cho object tùy ý |

Với object có thuộc tính số, dùng `Comparator` để chọn **object**, không dùng `Integer::max` rồi mất các field khác.

### 6.2. Ví dụ boxed và primitive

```java
int boxedSum = Stream.of(2, 3, 4)
        .reduce(0, Integer::sum); // 9

int primitiveSum = IntStream.of(2, 3, 4)
        .reduce(0, Integer::sum); // 9

Integer boxedMax = Stream.of(2, 3, 4)
        .reduce(Integer::max)
        .orElseThrow();           // 4

int primitiveMax = IntStream.of(2, 3, 4)
        .max().orElseThrow();     // 4
```

Đây là mã trong phương thức; import `java.util.stream.*`. `orElseThrow()` phù hợp vì các stream ở đây có phần tử; với tập rỗng, cần chính sách xử lý Optional.

## 7. `Integer::sum` và vấn đề overflow

`Integer.sum(a,b)` chỉ cộng như `a+b`. Nó **không kiểm tra overflow**. Với `int`:

```java
int wrapped = Integer.sum(Integer.MAX_VALUE, 1);
// -2147483648, do wrap-around 32-bit.
```

Nếu nghiệp vụ đòi tổng toán học chính xác, wrap-around là dữ liệu sai. Các cách xử lý:

1. **Widen trước khi cộng**: với phần tử `int` nhưng tổng có thể lớn hơn int, dùng `asLongStream()` hoặc `mapToLong`, rồi `Long::sum`.
2. **Checked addition**: `Math.addExact(int,int)`/`Math.addExact(long,long)` ném `ArithmeticException` khi phép cộng tràn.
3. **BigInteger**: khi tổng có thể vượt `long`, dùng `BigInteger::add` trên `Stream<BigInteger>` với `BigInteger.ZERO`.
4. **Domain validation**: kiểm tra số phần tử, giới hạn dải giá trị và policy khi overflow, không âm thầm ép về kiểu nhỏ.

**Cẩn thận:** `Long.sum` cũng có thể overflow nếu vượt phạm vi `long`. Việc widen từ int sang long chỉ giải quyết khi tổng thật sự vừa trong long.

### 7.1. Widen phải xảy ra trước phép cộng bị tràn

Đúng:

```java
long total = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .reduce(0L, Long::sum);
// 2147483648
```

Sai về ý nghĩa:

```java
long wrong = (long) IntStream.of(
        Integer.MAX_VALUE, 1).reduce(0, Integer::sum);
// -2147483648 rồi mới chuyển sang long.
```

Một phép cast `(long)` sau khi `int` đã overflow **không phục hồi** các bit đã mất.

### 7.2. Checked addition không thay thế BigInteger trong mọi tình huống

`Math::addExact` có thể dùng như `IntBinaryOperator`:

```java
int checked = IntStream.of(1_000, 2_000)
        .reduce(0, Math::addExact); // 3000
```

Nếu một phép cộng trung gian overflow, exception được ném. Tuy nhiên với phép reduce song song, thứ tự nhóm phần tử có thể khác nhau. Có các tập dữ liệu **tổng cuối vừa kiểu** nhưng một cách nhóm trung gian lại overflow; vì vậy checked addition có thể phát hiện overflow theo **thứ tự thực thi**, chứ không là lời hứa rằng chỉ tổng toán học cuối mới được xét.

Nếu yêu cầu chính xác không phụ thuộc cách grouping, dùng `BigInteger` hoặc một giải pháp số học có kiểm tra miền đầu vào, không đổi tất cả phép cộng thành `Math.addExact` rồi mặc định tương đương tổng toán học tùy thứ tự.

## 8. Java 17+ runnable: Wrap-around, widen và checked sum

Tạo file **`ArithmeticOverflowDemo.java`**:

```java
import java.math.BigInteger;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ArithmeticOverflowDemo {
    public static void main(String[] args) {
        int wrapped = IntStream.of(Integer.MAX_VALUE, 1)
                .reduce(0, Integer::sum);

        long widened = IntStream.of(Integer.MAX_VALUE, 1)
                .asLongStream()
                .reduce(0L, Long::sum);

        BigInteger exact = Stream.of(
                        Integer.MAX_VALUE, 1, 1)
                .map(BigInteger::valueOf)
                .reduce(BigInteger.ZERO, BigInteger::add);

        boolean overflowDetected = false;
        try {
            IntStream.of(Integer.MAX_VALUE, 1)
                    .reduce(0, Math::addExact);
        } catch (ArithmeticException ex) {
            overflowDetected = true;
        }

        System.out.println("int wrapped: " + wrapped);
        System.out.println("widened long: " + widened);
        System.out.println("BigInteger exact: " + exact);
        System.out.println("Checked overflow: "
                + overflowDetected);
    }
}
```

Chạy:

```bash
javac --release 17 ArithmeticOverflowDemo.java
java ArithmeticOverflowDemo
```

**Stdout:**

```text
int wrapped: -2147483648
widened long: 2147483648
BigInteger exact: 2147483649
Checked overflow: true
```

**Phân tích:** Trong phép int đầu, `MAX_VALUE + 1` vượt miền 32-bit, wrap về `MIN_VALUE`. Với long, tổng `2147483648` còn hợp lệ; với BigInteger, thêm một phần tử 1 nữa tạo `2147483649` chính xác. `Math.addExact` phát hiện overflow và ném exception như đã dự kiến.

**Đừng nhầm hiệu năng:** BigInteger cấp phát object và có chi phí cao hơn primitive; chỉ dùng khi miền dữ liệu/độ chính xác yêu cầu. Đừng vì muốn tránh boxing mà chấp nhận số liệu nghiệp vụ sai.

## 9. Min/max của double: NaN, infinity và ±0.0

`Double.min` và `Double.max` về hành vi tương đương `Math.min`/`Math.max` trên `double`. Chúng **không** chỉ là phép so sánh ngây thơ:

```java
double smaller = a < b ? a : b;
```

Dòng trên là **mã minh họa** nhưng không mô phỏng đúng mọi trường hợp `NaN` và `-0.0`.

### 9.1. Quy tắc IEEE 754 cần nhớ

- Nếu **một toán hạng là NaN**, `Double.min`/`Double.max` trả NaN.
- Giữa `+0.0` và `-0.0`, min là **-0.0**, max là **+0.0**.
- `Double.POSITIVE_INFINITY` lớn hơn mọi số hữu hạn; `Double.NEGATIVE_INFINITY` nhỏ hơn mọi số hữu hạn.
- `Double.sum` dùng cộng dấu phẩy động thông thường, có quy tắc infinity, NaN, rounding của Java.
- `Float.min/max/sum` có ngữ nghĩa tương ứng trên kiểu `float`, với độ chính xác thấp hơn `double`.

Trong Java, `-0.0 == +0.0` là true khi dùng `==`, nhưng hai giá trị **khác nhau về raw sign bit**, dễ nhận ra qua phép nghịch đảo: `1.0 / -0.0` là `-Infinity`, còn `1.0 / +0.0` là `Infinity`.

### 9.2. Không bỏ NaN âm thầm bằng một quy tắc ngây thơ

Nếu dữ liệu có NaN, `Double::min` và `Double::max` sẽ lan truyền NaN. Một ứng dụng có thể chọn policy **bỏ qua NaN**, **từ chối input**, hoặc **báo metric dữ liệu không hợp lệ**, nhưng phải diễn đạt policy rõ trước khi reduce.

Nếu tự filter:

```java
double minFiniteOrNonNaN = values
        .filter(v -> !Double.isNaN(v))
        .min()
        .orElseThrow();
```

Đây là đoạn trong một phương thức với `values` là **một `DoubleStream` chưa được sử dụng**. Kết quả có thể vẫn là `±Infinity`; filter này chỉ bỏ NaN. Nếu yêu cầu **chỉ số hữu hạn**, dùng thêm `Double.isFinite(v)`. Khi tất cả phần tử bị lọc, `orElseThrow()` sẽ ném do tập rỗng; ứng dụng phải xử lý phù hợp.

### 9.3. Identity double min/max

`Double.POSITIVE_INFINITY` là identity của `Double::min`; `Double.NEGATIVE_INFINITY` là identity của `Double::max` trên cách gộp này, với NaN được lan truyền. Nhưng một kết quả Infinity sau reduce có identity **không chứng minh** có dữ liệu thực. Nếu cần phân biệt absent, dùng overload không identity của `reduce` để nhận `OptionalDouble` hoặc `DoubleStream.min()/max()`.

## 10. Phép cộng số thực không kết hợp tuyệt đối

Trên toán học thực, `(a+b)+c == a+(b+c)`. Với IEEE 754 `double`, rounding ở mỗi phép cộng khiến đẳng thức này có thể **không đúng**.

Chọn:

```text
a = 1e16
b = -1e16
c = 1.0
```

- `Double.sum(Double.sum(a,b),c)`: trước hết `a+b = 0.0`, rồi +1.0 → **1.0**.
- `Double.sum(a, Double.sum(b,c))`: `b+1.0` không giữ nổi phần 1 ở độ lớn đó, vẫn gần `-1e16`; cộng lại với `a` → **0.0**.

Đó là lý do phép `Double::sum` **không đáp ứng tính kết hợp bit-for-bit** mà một reducer song song thường cần để cho ra kết quả hoàn toàn giống nhau giữa mọi cách partition.

**Không kết luận "parallel stream bị lỗi".** Scheduler được phép gộp theo thứ tự khác; giới hạn nằm ở số học dấu phẩy động. Nếu nghiệp vụ đòi tính tái lập chính xác, phải chọn thuật toán tổng, thứ tự xử lý, miền dữ liệu và mức độ song song thích hợp.

### 10.1. `DoubleStream.sum()` không luôn tương đương `reduce(0,Double::sum)`

Tài liệu `DoubleStream.sum` nêu rõ phép sum có thể dùng **compensated summation** hoặc cách gộp khác để cải thiện sai số. Vì vậy không mặc định:

```java
stream.sum()
```

và

```java
stream.reduce(0.0, Double::sum)
```

luôn cho cùng các bit kết quả. Đây là **hai đoạn minh họa**, biến `stream` là một DoubleStream dùng **một lần**; trong thực tế phải tạo hai stream riêng để so sánh.

### 10.2. Identity zero và signed zero

Với phép cộng double, `+0.0` là identity **theo giá trị số học thông thường**, nhưng IEEE 754 có phân biệt dấu zero: ví dụ cộng `+0.0` với `-0.0` có thể tạo `+0.0` thay vì giữ `-0.0`. Nếu chương trình yêu cầu giữ sign bit của zero, cần xử lý rõ, không dựa vào reduce với identity để bảo toàn tất cả đặc tính bit-level.

Một số hệ thống tính toán chấp nhận sai khác nhỏ; một số hệ thống ledger, signature, scientific reproducibility thì không. Không có phương thức `sum` duy nhất đáp ứng mọi hợp đồng độ chính xác.

## 11. Java 17+ runnable: NaN, signed zero và thứ tự cộng

Tạo file **`FloatingOperatorsDemo.java`**:

```java
import java.util.stream.DoubleStream;

public class FloatingOperatorsDemo {
    public static void main(String[] args) {
        double negativeZero = -0.0;
        double positiveZero = +0.0;

        System.out.println("Min signed zero: "
                + Double.min(positiveZero, negativeZero));
        System.out.println("Max signed zero: "
                + Double.max(positiveZero, negativeZero));
        System.out.println("Min reciprocal: "
                + 1.0 / Double.min(
                        positiveZero, negativeZero));
        System.out.println("Max reciprocal: "
                + 1.0 / Double.max(
                        positiveZero, negativeZero));

        System.out.println("Min with NaN: "
                + Double.min(Double.NaN, 4.0));
        System.out.println("Max with NaN: "
                + Double.max(Double.NaN, 4.0));

        double a = 1e16;
        double b = -1e16;
        double c = 1.0;

        System.out.println("Left grouped: "
                + Double.sum(Double.sum(a, b), c));
        System.out.println("Right grouped: "
                + Double.sum(a, Double.sum(b, c)));

        System.out.println("Empty min identity: "
                + DoubleStream.empty()
                        .reduce(Double.POSITIVE_INFINITY,
                                Double::min));
        System.out.println("Empty max identity: "
                + DoubleStream.empty()
                        .reduce(Double.NEGATIVE_INFINITY,
                                Double::max));
        System.out.println("Empty min optional: "
                + DoubleStream.empty()
                        .reduce(Double::min).isPresent());
    }
}
```

Chạy:

```bash
javac --release 17 FloatingOperatorsDemo.java
java FloatingOperatorsDemo
```

**Stdout:**

```text
Min signed zero: -0.0
Max signed zero: 0.0
Min reciprocal: -Infinity
Max reciprocal: Infinity
Min with NaN: NaN
Max with NaN: NaN
Left grouped: 1.0
Right grouped: 0.0
Empty min identity: Infinity
Empty max identity: -Infinity
Empty min optional: false
```

**Ý nghĩa:** Các kết quả về signed zero, NaN và nhóm phép cộng là tính chất số học, không phải scheduler. Ví dụ gọi từng phép trực tiếp để stdout ổn định. Trong parallel reduction thực tế, cách nhóm có thể khác và có thể cho kết quả bit-level khác. Nên test bằng dung sai/thuật toán thích hợp nếu yêu cầu chấp nhận sai số, hoặc chọn cách tính exact nếu không chấp nhận.

## 12. `Map.merge`: Dùng sum/min/max để gộp theo khóa

`Map.merge(key, value, remappingFunction)` nhận một `BiFunction` để gộp **giá trị cũ** với **giá trị mới đi vào** khi khóa đã tồn tại.

Ví dụ:

```java
Map<String, Integer> scores = new HashMap<>();

scores.merge("java", 1, Integer::sum);
scores.merge("java", 1, Integer::sum); // "java" -> 2
```

Đây là đoạn trong method, import `java.util.Map` và `HashMap`.

Với `Integer::max`:

```java
scores.merge("java", 10, Integer::max);
// Giữ giá trị lớn hơn giữa old và 10.
```

Với `Integer::min`:

```java
scores.merge("java", 3, Integer::min);
// Giữ giá trị nhỏ hơn giữa old và 3.
```

### 12.1. Callback merge KHÔNG chạy khi khóa absent

Nếu `key` chưa có mapping hoặc đang map tới null trong một `Map` cho phép null, `merge` có thể gắn trực tiếp `value` mà **không gọi callback**. Vì vậy:

```java
scores.merge("new", 10, Integer::min);
```

trên khóa absent sẽ lưu **10**, không dùng một identity toàn cục nào như Integer.MAX_VALUE. Đây là cơ chế **gộp hai giá trị khi cùng khóa**, khác với `Stream.reduce(identity, op)` trên toàn tập.

### 12.2. Không gộp kiểu sai

`Map<String, Long>` cần `Long::sum` chứ không nên ép `Integer::sum` rồi cast. `Map<String, Double>` có thể dùng `Double::max`, nhưng phải hiểu NaN, -0.0 và precision.

**Bản chất thread safety phụ thuộc loại map:** `HashMap.merge` không an toàn khi nhiều thread cùng sửa map mà không đồng bộ. `ConcurrentHashMap.merge` có contract cập nhật **nguyên tử theo khóa** và yêu cầu callback ngắn, không sửa chính map; method reference thuần như `Integer::sum` rất phù hợp. Tuy nhiên, toàn phép gộp nhiều khóa **không** thành giao dịch nguyên tử.

### 12.3. Ví dụ tính thống kê theo nhãn

- Đếm mỗi sự kiện: `map.merge(category, 1, Integer::sum)`.
- Điểm cao nhất của một nhóm: `map.merge(category, score, Integer::max)`.
- Giá thấp nhất của một nhóm: `map.merge(category, price, Integer::min)`.

Khi dữ liệu có thể vượt `Integer.MAX_VALUE`, cần chọn `Long` hoặc cấu trúc chính xác hơn. Khi nhóm có giá trị missing/null, phải xác định policy trước khi merge, thay vì mong `Integer::min` hiểu null.

## 13. `Collectors.toMap`: Dùng toán tử để giải quyết khóa trùng

`Collectors.toMap(keyMapper, valueMapper, mergeFunction)` nhận toán tử gộp khi **hai phần tử nguồn sinh cùng key**.

```java
Map<String, Integer> best = rows.stream()
        .collect(Collectors.toMap(
                Row::key,
                Row::score,
                Integer::max));
```

Đây là **đoạn minh họa trong class** có kiểu `Row` và biến `rows` giả định; không phải chương trình độc lập. Ý nghĩa là với cùng key, giữ **score lớn nhất**.

### 13.1. Phải hiểu dữ liệu trùng key

Nếu không truyền merge function mà dữ liệu sinh khóa trùng, `Collectors.toMap` có thể ném `IllegalStateException`. Đó là một lỗi hợp đồng thường gặp khi tổ chức dữ liệu từ stream.

`Integer::sum`/`min`/`max` là các merge functions rõ nghĩa và có tính kết hợp phù hợp cho kiểu `int`. Với parallel stream, các kết quả gộp khi duplicate keys phải độc lập với side effect của callback. Dùng `TreeMap::new` như supplier để có thứ tự key ổn định khi **in ra demo**, không có nghĩa `Collectors.toMap` mặc định luôn trả TreeMap.

### 13.2. Bản chất `toMap` không phải `groupingBy`

`Collectors.groupingBy(keyMapper)` gom toàn bộ các giá trị cùng key thành danh sách (theo collector được chọn), còn `toMap(..., Integer::max)` chỉ giữ **một giá trị** đại diện là max. Nếu muốn nhiều số đo như min/max/sum/count cùng lúc, có thể dùng `IntSummaryStatistics` làm downstream collector hoặc một record state kết hợp, thay vì quét/boxing nhiều lần không cần thiết.

## 14. Java 17+ runnable: Merge và Collectors

Tạo file **`ArithmeticMapMergeDemo.java`**:

```java
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ArithmeticMapMergeDemo {
    public static void main(String[] args) {
        Map<String, Integer> merged = new TreeMap<>();

        merged.merge("java", 3, Integer::sum);
        merged.merge("java", 4, Integer::sum);
        merged.merge("java", 5, Integer::max);
        merged.merge("go", 6, Integer::min);
        merged.merge("go", 2, Integer::min);

        System.out.println("Merge: " + merged);

        Map<String, Integer> maxima = Stream.of(
                        "a:3", "b:5", "a:7", "b:1")
                .map(line -> line.split(":"))
                .collect(Collectors.toMap(
                        parts -> parts[0],
                        parts -> Integer.parseInt(parts[1]),
                        Integer::max,
                        TreeMap::new));

        System.out.println("toMap max: " + maxima);

        System.out.println("Boxed sum: "
                + Stream.of(2, 3, 4)
                        .reduce(0, Integer::sum));
        System.out.println("Boxed max: "
                + Stream.of(2, 3, 4)
                        .reduce(Integer::max)
                        .orElseThrow());
    }
}
```

Chạy:

```bash
javac --release 17 ArithmeticMapMergeDemo.java
java ArithmeticMapMergeDemo
```

**Stdout:**

```text
Merge: {go=2, java=7}
toMap max: {a=7, b=5}
Boxed sum: 9
Boxed max: 4
```

**Giải thích:**

1. `java` được cộng 3 và 4 thành 7, sau đó gộp max với 5 vẫn là 7.
2. `go` có giá trị đầu 6, sau đó min với 2 tạo 2.
3. `Collectors.toMap` gặp key `a` hai lần nên giữ max của 3/7 là 7; key `b` giữ max của 5/1 là 5.
4. `TreeMap` sắp thứ tự key để stdout ổn định, **không phải** vì phép merge yêu cầu dữ liệu có thứ tự.
5. `Stream<Integer>.reduce` có thể nhận `Integer::sum` và `Integer::max` qua `BinaryOperator<Integer>`.

## 15. `Arrays.parallelPrefix`: Tính tổng/min/max lũy tích

`Arrays.parallelPrefix(int[], IntBinaryOperator)` tính **prefix accumulation tại mỗi chỉ số**. Mỗi phần tử sau phép biến đổi là kết quả gộp tất cả phần tử từ đầu mảng đến vị trí đó.

Ví dụ với mảng:

```text
Input: [2, 5, -1, 3]

prefix sum: [2, 7, 6, 9]
prefix min: [2, 2, -1, -1]
prefix max: [2, 5, 5, 5]
```

Khác với `IntStream.reduce` (một kết quả tổng hợp), `parallelPrefix` **sửa mảng tại chỗ** để chứa các kết quả ở **mọi tiền tố**. Hàm gộp phải không có side effects và phù hợp tính kết hợp; số thực `double` có thể cho kết quả khác phép duyệt tuần tự do rounding.

### 15.1. Không tái dùng mảng đã bị thay

Nếu muốn so sánh prefix sum, min, max trên **cùng dữ liệu gốc**, hãy tạo ba mảng độc lập hoặc `clone()` trước khi gọi, vì mỗi lời gọi `parallelPrefix` **mutate chính mảng**.

### 15.2. Phạm vi chỉ số

Các overload nhận `fromIndex, toIndex` dùng khoảng **[fromIndex, toIndex)** (đầu bao gồm, cuối không bao gồm). Khi tính prefix trên một vùng con, phép tích lũy bắt đầu từ phần tử đầu **trong vùng đó**, phần ngoài vùng giữ nguyên.

### 15.3. Vì sao không dùng cho phép trừ?

Phép trừ không kết hợp: `(10-3)-2=5` nhưng `10-(3-2)=9`. Vì `parallelPrefix` có thể phân nhóm kết quả, một toán tử như `(a,b)->a-b` **không phù hợp contract associative**. `Integer::sum/min/max` trên `int` lại thích hợp khi chấp nhận giới hạn overflow đã nói.

## 16. Java 17+ runnable: Ba kiểu parallel prefix

Tạo file **`ParallelPrefixOperatorsDemo.java`**:

```java
import java.util.Arrays;

public class ParallelPrefixOperatorsDemo {
    public static void main(String[] args) {
        int[] sumPrefix = {2, 5, -1, 3};
        int[] minPrefix = {8, 3, 6, 2};
        int[] maxPrefix = {2, 7, 1, 9};

        Arrays.parallelPrefix(sumPrefix, Integer::sum);
        Arrays.parallelPrefix(minPrefix, Integer::min);
        Arrays.parallelPrefix(maxPrefix, Integer::max);

        System.out.println("Sum prefix: "
                + Arrays.toString(sumPrefix));
        System.out.println("Min prefix: "
                + Arrays.toString(minPrefix));
        System.out.println("Max prefix: "
                + Arrays.toString(maxPrefix));
    }
}
```

Chạy:

```bash
javac --release 17 ParallelPrefixOperatorsDemo.java
java ParallelPrefixOperatorsDemo
```

**Stdout:**

```text
Sum prefix: [2, 7, 6, 9]
Min prefix: [8, 3, 3, 2]
Max prefix: [2, 7, 7, 9]
```

**Cách tính:** 
- Sum: `2`, `2+5=7`, `7-1=6`, `6+3=9`.
- Min: `min(8) = 8`; `min(8,3)=3`; `min(3,6)=3`; `min(3,2)=2`.
- Max: `max(2)=2`; `max(2,7)=7`; `max(7,1)=7`; `max(7,9)=9`.

Việc API có chữ "parallel" không bảo đảm mảng nhỏ dùng nhiều thread; implementation có thể chọn xử lý tuần tự khi kích thước nhỏ. Demo nhằm minh họa **ý nghĩa prefix**, không đo speedup.

## 17. Parallel reduce: Vì sao toán tử thuần và associative quan trọng?

`parallel()` cho phép stream chia input thành nhiều phần, tính reduction một phần rồi gộp kết quả. Với `Integer::sum/min/max`, việc không có side effect giúp giảm nguy cơ data race. Mỗi task có thể gộp một nhóm rồi các nhóm tiếp tục được gộp.

Ví dụ:

```java
int result = IntStream.rangeClosed(1, 10_000)
        .parallel()
        .reduce(0, Integer::sum);
```

Kết quả là `50_005_000`, nằm trong phạm vi int; toán tử cộng int phù hợp khi không overflow ảnh hưởng ý nghĩa nghiệp vụ.

**Không làm như sau:**

```java
int[] total = {0};

IntStream.rangeClosed(1, 10_000)
        .parallel()
        .forEach(value -> total[0] += value);
```

Đây là **phản ví dụ**, không phải code an toàn. Các worker có thể cùng ghi `total[0]` mà không đồng bộ; `+=` là read-modify-write, có thể mất cập nhật. `reduce` phù hợp hơn vì API quản lý việc gộp các kết quả cục bộ theo hợp đồng.

### 17.1. Vì sao `Integer::max` dễ song song hóa?

`max` trên `int`:
- **Associative:** max(max(a,b),c) = max(a,max(b,c)).
- **Commutative:** max(a,b) = max(b,a).
- **Idempotent:** max(a,a) = a.
- **Không có state bên ngoài.**

Các tính chất giúp kết quả không phụ thuộc thứ tự gộp. Tương tự `min`. Với `Integer::sum`, cần nhớ overflow wrap-around, nhưng phép cộng int vẫn kết hợp theo modulo 2^32.

### 17.2. Sum double và kết quả song song

`Double::sum` **không kết hợp bitwise**. Vì thế khi stream parallel, kết quả double có thể khác một phép vòng lặp tuần tự. `DoubleStream.sum()` còn có thể sử dụng kỹ thuật compensated summation và thứ tự không được định nghĩa để cải thiện sai số.

Không bảo đảm hai cách cho kết quả bit-for-bit giống nhau:

```java
double a = DoubleStream.of(values)
        .parallel().reduce(0.0, Double::sum);

double b = DoubleStream.of(values)
        .parallel().sum();
```

Đây là **đoạn trong phương thức**, với `values` là `double[]`. Sử dụng hai stream riêng đúng, nhưng không nên assert `Double.doubleToLongBits(a) == Double.doubleToLongBits(b)` cho mọi input.

### 17.3. Khi nào tự dùng reduce?

Nếu chỉ cần sum, min, max trên primitive stream, các terminal methods chuẩn thường ngắn và được thiết kế chuyên biệt. `reduce(..., Integer::sum)` hữu ích khi:
- Muốn truyền một toán tử thống nhất vào API tổng quát.
- Có rule gộp riêng nhưng vẫn thỏa contract.
- Tích hợp với `Map.merge`/`Collectors.toMap`/`Arrays.parallelPrefix`.
- Muốn phân tích, kiểm thử tính kết hợp và identity của một phép gộp.

Không dùng `reduce` chỉ để thay mọi API chuẩn cho "đẹp" nếu làm code khó hiểu hơn.

## 18. Java 17+ runnable: Parallel reduction đúng

Tạo file **`ParallelArithmeticReduceDemo.java`**:

```java
import java.util.stream.IntStream;

public class ParallelArithmeticReduceDemo {
    public static void main(String[] args) {
        int sum = IntStream.rangeClosed(1, 10_000)
                .parallel()
                .reduce(0, Integer::sum);

        int min = IntStream.rangeClosed(1, 10_000)
                .parallel()
                .reduce(Integer::min)
                .orElseThrow();

        int max = IntStream.rangeClosed(1, 10_000)
                .parallel()
                .reduce(Integer::max)
                .orElseThrow();

        System.out.println("Parallel sum: " + sum);
        System.out.println("Parallel min: " + min);
        System.out.println("Parallel max: " + max);
    }
}
```

Chạy:

```bash
javac --release 17 ParallelArithmeticReduceDemo.java
java ParallelArithmeticReduceDemo
```

**Stdout:**

```text
Parallel sum: 50005000
Parallel min: 1
Parallel max: 10000
```

Vì input là dải `1..10000` và không có overflow, kết quả không phụ thuộc cách partition hay thứ tự worker. Không dựa vào việc một parallel stream phải nhanh hơn sequential stream với 10.000 số; CPU, granularity và scheduler thực tế có thể khiến overhead lớn hơn lợi ích.

## 19. Kết hợp sum/min/max cho thống kê: Không duyệt một stream ba lần

Nếu muốn **count, sum, min, max, average** của một nguồn số nguyên, `IntSummaryStatistics` có thể gom trong **một terminal operation**:

```java
IntSummaryStatistics stats =
        IntStream.of(4, 7, 2).summaryStatistics();

long count = stats.getCount(); // 3
long sum = stats.getSum();     // 13
int min = stats.getMin();      // 2
int max = stats.getMax();      // 7
double average = stats.getAverage();
```

Đây là đoạn trong method, import `java.util.IntSummaryStatistics` và `java.util.stream.IntStream`.

**Lưu ý:**

- `IntSummaryStatistics.getSum()` trả `long`, nên giảm nguy cơ overflow so với `IntStream.sum()` trên int; nhưng `long` vẫn có thể overflow với dải quá lớn.
- Với **dữ liệu rỗng**, `getMin()` có thể là `Integer.MAX_VALUE` và `getMax()` có thể là `Integer.MIN_VALUE` theo trạng thái ban đầu; hãy kiểm tra `getCount()` trước khi coi chúng là minimum/maximum thật.
- `IntSummaryStatistics` là object accumulator có state; khi dùng trong collector có cơ chế kết hợp riêng theo contract, không tự đồng thời gọi `accept` lên **cùng một instance** từ nhiều thread mà không đồng bộ.
- `DoubleSummaryStatistics` có tính chất số học floating point; không dùng cho ledger tiền cần precision exact.

### 19.1. Đọc tên `min/max` không đủ để biết null/empty semantics

Các API khác nhau có thể dùng:
- `OptionalInt.empty()` để biểu diễn không có phần tử.
- Sentinel identity (`MAX_VALUE`/`MIN_VALUE`).
- Exception nếu không có dữ liệu.
- Giá trị mặc định do caller chọn.

Khi thiết kế API public, hãy ghi rõ điều kiện empty và miền giá trị; đừng lấy sentinel rồi ghi vào database như một số đo thật.

## 20. Lỗi phổ biến khi dùng `sum/min/max` như hàm

1. **Nghĩ `Integer::sum` tự lưu biến tích lũy:** nó chỉ nhận hai toán hạng và trả kết quả, reduce/merge mới quản lý việc lặp.
2. **Nhầm `Integer::sum` với `Integer.sum(...)`:** method reference khác lời gọi thực thi ngay.
3. **Dùng `var op = Integer::sum` không có target functional type:** compiler cần biết interface hàm.
4. **Dùng `IntUnaryOperator` cho `Integer::sum`:** sum có hai tham số, cần `IntBinaryOperator`.
5. **Dùng `DoubleBinaryOperator` cho `Long::sum`:** không tương thích kiểu, phải chọn đúng wrapper/interface.
6. **Dùng `BinaryOperator<Integer>` cho dữ liệu primitive lớn mà không xét boxing:** cân nhắc `IntBinaryOperator`/`IntStream`.
7. **Dùng `Integer::compare` để lấy max/min:** Comparator trả kết quả so sánh, không trả một trong hai giá trị.
8. **Dùng `reduce(0,Integer::min)` với toàn số dương:** min có thể thành 0 giả.
9. **Dùng `reduce(0,Integer::max)` với toàn số âm:** max có thể thành 0 giả.
10. **Dùng sentinel làm câu trả lời với tập rỗng:** identity trả về nhưng không có phần tử.
11. **Dùng `orElseThrow` cho min/max khi tập có thể rỗng mà không có policy:** exception có thể ngoài ý muốn.
12. **Gọi `sum`, `min`, `max` trên cùng một `IntStream` instance:** terminal operation chỉ được dùng một lần.
13. **Dùng `Integer::sum` cho tổng lớn không xét overflow:** int wrap-around.
14. **Cast sang long sau khi đã reduce int:** dữ liệu đã overflow không được phục hồi.
15. **Dùng `Long::sum` và nghĩ không bao giờ overflow:** long vẫn có giới hạn 64-bit.
16. **Dùng `Math::addExact` mà nghĩ kết quả reduce parallel nhất thiết phụ thuộc chỉ vào tổng cuối:** grouping trung gian có thể ném exception.
17. **Dùng `Double::sum` và khẳng định tính kết hợp tuyệt đối:** IEEE 754 rounding làm kết quả khác cách nhóm.
18. **Khẳng định `DoubleStream.sum() == reduce(0.0,Double::sum)` bit-for-bit:** API có thể dùng compensated sum.
19. **Đưa NaN vào `Double::min/max` rồi mong nó bị bỏ qua:** NaN được lan truyền.
20. **Dùng toán tử điều kiện `a<b?a:b` thay cho `Double::min` mà bỏ qua NaN và signed zero:** không tương đương trong mọi case.
21. **Giả định `+0.0` và `-0.0` giống nhau hoàn toàn:** sign bit có ý nghĩa.
22. **Dùng `Float::sum` cho phép đo cần nhiều chữ số chính xác:** float có precision hạn chế.
23. **Dùng `Integer::max` để lấy object có score cao nhất:** nó trả integer, không trả entity; cần Comparator cho object.
24. **Dùng `Map.merge` mà quên callback không chạy khi absent:** incoming value được chèn trực tiếp.
25. **Dùng `HashMap.merge` từ nhiều thread và tin nó atomic:** HashMap không thread-safe; CHM có contract riêng theo khóa.
26. **Gộp nhiều key trong CHM rồi nghĩ là một transaction:** tính atomic không trải qua nhiều key.
27. **Dùng `Collectors.toMap` với key trùng mà không có merge function:** có thể ném IllegalStateException.
28. **Dùng `Collectors.toMap` và mong thứ tự iteration mặc định cố định:** chọn supplier/order nếu test cần.
29. **Dùng một lambda gộp có side effect trong parallel reduce:** có thể race, vi phạm stateless/non-interfering contract.
30. **Dùng phép trừ trong `Arrays.parallelPrefix` rồi kỳ vọng thứ tự tính tuần tự:** trừ không associative.
31. **Gọi nhiều phép prefix trên cùng mảng rồi nghĩ mọi phép xuất phát từ input gốc:** `parallelPrefix` mutate mảng.
32. **Tưởng phép prefix luôn cần nhiều worker:** mảng nhỏ có thể xử lý tuần tự.
33. **Tự xây `(a,b)-> a+b` với logic giữ trạng thái thừa:** method ref thuần ngắn và dễ kiểm tra.
34. **Tưởng method reference nhanh hơn lambda trong mọi runtime:** cần benchmark đo thật.
35. **Không kiểm tra empty trước khi dùng `IntSummaryStatistics.getMin/getMax`:** giá trị mặc định có thể chỉ là sentinel.
36. **Dùng `Double::sum` cho số tiền:** nên biểu diễn đơn vị nguyên/BigDecimal và có policy rounding đúng domain.
37. **Không xác định giới hạn dải số trước khi chọn int/long/double/BigInteger:** mỗi kiểu có semantic khác nhau.
38. **Tin hoạt động parallel luôn nhanh hơn sequential:** scheduling overhead và kích thước dữ liệu có thể chi phối.

## 21. Checklist thiết kế và review

- [ ] Tôi đang xử lý **hai giá trị** hay **một tập số**? Phương thức tĩnh hai tham số và API reduce có vai trò khác nhau.
- [ ] Loại dữ liệu là `int`, `long`, `float` hay `double`? Có chọn wrapper/operator đúng không?
- [ ] Nếu dùng primitive stream, có ưu tiên `IntBinaryOperator`/`LongBinaryOperator`/`DoubleBinaryOperator` khi phù hợp?
- [ ] Nếu chỉ cần sum/min/max, API `sum()/min()/max()` có rõ hơn một reduce thủ công?
- [ ] Nếu dùng `reduce(identity, op)`, identity có thật sự đúng cho **mọi giá trị trong miền** không?
- [ ] Nếu min/max có thể rỗng, có dùng Optional hoặc kiểm tra count rõ?
- [ ] Nếu tính tổng số nguyên, có kiểm tra overflow và lựa chọn int/long/BigInteger/Math.addExact đúng yêu cầu?
- [ ] Nếu dùng `Double::sum` trên parallel stream, có hiểu kết quả có thể khác thứ tự nhóm vì rounding?
- [ ] Nếu dùng `Double::min/max`, đã quyết định policy cho NaN, signed zero, infinity?
- [ ] Nếu đòi so sánh bitwise double, có kiểm tra sign zero và NaN đúng chưa?
- [ ] Nếu dùng `Map.merge`, hiểu callback chỉ chạy khi key đã có mapping?
- [ ] Nếu dùng collector toMap, hiểu duplicate key và merge semantics?
- [ ] Nếu dùng ConcurrentHashMap, có hiểu tính nguyên tử **theo khóa** và callback không được sửa map?
- [ ] Nếu dùng `Arrays.parallelPrefix`, toán tử có associative, side-effect-free không?
- [ ] Có clone mảng trước khi thử các toán tử khác nhau?
- [ ] Nếu cần nhiều chỉ số trong một lần duyệt, đã cân nhắc `summaryStatistics()` chưa?
- [ ] Có test giá trị âm/toàn dương, tập rỗng, MAX/MIN, overflow, NaN, ±0.0, infinity?
- [ ] Có test parallel reduce theo bất biến toán học thay vì đòi thứ tự thread?
- [ ] Code có giữ nguyên dữ liệu đầu vào, không lạm dụng mutable shared accumulator trong parallel stream?
- [ ] Đã kiểm tra stdout ví dụ trên JDK phù hợp, không nhầm một snippet cần scope với chương trình độc lập?

## 22. Bộ kiểm thử Java 17+ không cần `-ea`

Tạo file **`ArithmeticOperatorChecks.java`**. Dùng hàm `check` tự ném `AssertionError` nếu sai, không phụ thuộc cờ bật Java assertions:

```java
import java.util.Arrays;
import java.util.OptionalInt;
import java.util.function.IntBinaryOperator;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;

public class ArithmeticOperatorChecks {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        IntBinaryOperator sum = Integer::sum;
        IntBinaryOperator min = Integer::min;
        IntBinaryOperator max = Integer::max;

        check(sum.applyAsInt(2, 3) == 5, "sum function");
        check(min.applyAsInt(2, 3) == 2, "min function");
        check(max.applyAsInt(2, 3) == 3, "max function");
        System.out.println("Function references: PASS");

        int[] data = {8, -3, 5, 10};
        check(IntStream.of(data)
                .reduce(0, sum) == 20, "int sum");
        check(IntStream.of(data)
                .reduce(Integer.MAX_VALUE, min) == -3,
                "int min");
        check(IntStream.of(data)
                .reduce(Integer.MIN_VALUE, max) == 10,
                "int max");
        System.out.println("Identity: PASS");

        OptionalInt missing = IntStream.empty()
                .reduce(Integer::min);
        check(missing.isEmpty(), "empty min");
        check(IntStream.empty()
                .reduce(0, Integer::sum) == 0,
                "empty sum");
        System.out.println("Empty streams: PASS");

        check(Integer.sum(Integer.MAX_VALUE, 1)
                == Integer.MIN_VALUE, "wrap around");
        check(IntStream.of(Integer.MAX_VALUE, 1)
                .asLongStream()
                .reduce(0L, Long::sum)
                == 2_147_483_648L, "widen before sum");
        System.out.println("Overflow awareness: PASS");

        check(Double.isNaN(
                Double.min(Double.NaN, 2.0)),
                "NaN min");
        check(1.0 / Double.min(+0.0, -0.0)
                == Double.NEGATIVE_INFINITY,
                "signed zero min");
        check(1.0 / Double.max(+0.0, -0.0)
                == Double.POSITIVE_INFINITY,
                "signed zero max");
        System.out.println("Floating point: PASS");

        int[] prefix = {2, 5, -1, 3};
        Arrays.parallelPrefix(prefix, Integer::sum);
        check(Arrays.equals(prefix,
                new int[]{2, 7, 6, 9}),
                "parallel prefix");
        System.out.println("Parallel prefix: PASS");

        int parallel = IntStream.rangeClosed(1, 10_000)
                .parallel()
                .reduce(0, Integer::sum);
        check(parallel == 50_005_000, "parallel reduce");
        System.out.println("Parallel reduction: PASS");

        check(!DoubleStream.empty()
                .reduce(Double::max).isPresent(),
                "empty double max");
        System.out.println("OptionalDouble: PASS");
        System.out.println("All checks: PASS");
    }
}
```

Chạy:

```bash
javac --release 17 ArithmeticOperatorChecks.java
java ArithmeticOperatorChecks
```

**Stdout:**

```text
Function references: PASS
Identity: PASS
Empty streams: PASS
Overflow awareness: PASS
Floating point: PASS
Parallel prefix: PASS
Parallel reduction: PASS
OptionalDouble: PASS
All checks: PASS
```

**Tính xác định:** Không dựa vào tên worker, thread ID hay thứ tự thực thi của parallel stream. Kết quả `int` test nằm trong phạm vi không overflow ở đoạn song song; `Double.min/max` được kiểm tra bằng quy tắc NaN và signed zero. Những trường hợp rỗng được kiểm tra qua Optional thay vì đánh đồng sentinel với giá trị thật.

## 23. Câu hỏi ôn tập

1. `Integer::sum` có phải một accumulator tự lưu tổng trước đó không?
2. `Integer.sum(a,b)` và `Integer::sum` khác nhau ở điểm nào?
3. Nếu một API yêu cầu `IntBinaryOperator`, vì sao `Integer::sum` phù hợp?
4. `BinaryOperator<Integer>` và `IntBinaryOperator` khác nhau về boxing thế nào?
5. Khi nào nên ưu tiên `IntStream.sum()` thay cho `reduce(0,Integer::sum)`?
6. Identity đúng cho `Integer::min` và `Integer::max` là gì?
7. Vì sao `reduce(0,Integer::min)` cho tập toàn số dương có thể sai?
8. Tại sao `IntStream.min()` trả `OptionalInt` thay vì int?
9. `reduce(Integer::min)` khi rỗng trả gì?
10. `Double::min` chọn gì giữa `+0.0` và `-0.0`?
11. `Double::max` có bỏ qua NaN không?
12. Có thể khẳng định `Double::sum` là associative bit-for-bit trên mọi double không?
13. `DoubleStream.sum()` luôn cho cùng bit pattern với `reduce(0,Double::sum)` không?
14. `Integer::sum` có phát hiện overflow không?
15. Chuyển sang long **sau** một tổng int bị tràn có sửa được lỗi không?
16. Nếu phép cộng vượt long, có thể dùng kiểu chính xác nào?
17. Khi gọi `Map.merge` trên key absent, callback `Integer::sum` có chạy không?
18. Dùng `Collectors.toMap` với key trùng mà không merge function có thể xảy ra gì?
19. `Arrays.parallelPrefix` khác `IntStream.reduce` về số kết quả và việc thay đổi input?
20. Vì sao không dùng phép trừ làm toán tử cho `parallelPrefix`?
21. Một mapper/reducer có side effect lên shared ArrayList có an toàn trong parallel stream không?
22. Vì sao `IntSummaryStatistics.getMin` có thể gây hiểu lầm khi count=0?
23. `Integer::compare` có thay thế trực tiếp `Integer::max` như `IntBinaryOperator` để tính max không?
24. Nếu muốn chọn object có price lớn nhất thay vì chỉ trả number, cần dùng phương thức nào?
25. Khi dùng `Double::min/max` để xử lý dữ liệu khoa học, những trường hợp biên nào phải test?

**Gợi ý đáp án:** (1) Không, là hàm thuần hai toán hạng. (2) Lời gọi tính ngay vs tham chiếu truyền cho callback. (3) Chữ ký int,int→int khớp. (4) BinaryOperator dùng object, có thể box/unbox; IntBinaryOperator dùng primitive. (5) Khi chỉ cần tổng đơn giản. (6) `MAX_VALUE` cho min, `MIN_VALUE` cho max. (7) Identity 0 nhỏ hơn mọi phần tử nên kéo min về 0. (8) Vì có thể rỗng. (9) `OptionalInt.empty()`. (10) `-0.0`. (11) Không, NaN được lan truyền. (12) Không. (13) Không. (14) Không. (15) Không, phải widen trước. (16) `BigInteger`. (17) Không, incoming value được chèn trực tiếp. (18) Ném IllegalStateException. (19) Prefix sửa mảng và cho mọi kết quả lũy tích; reduce trả một kết quả. (20) Phép trừ không kết hợp. (21) Không, có thể data race. (22) Giá trị min mặc định là sentinel, không phải phần tử thật. (23) Không, compare trả quan hệ thứ tự chứ không trả max. (24) `Stream.max(Comparator.comparing(...))`. (25) NaN, ±0.0, ±Infinity, tập rỗng, rounding và thứ tự gộp.

**Kết luận:** `Integer::sum`, `Long::sum`, `Double::sum`, `Integer::min/max` và các biến thể tương ứng là các **toán tử hàm hai ngôi** rất tiện cho `reduce`, `Map.merge`, `Collectors.toMap` và `Arrays.parallelPrefix`. Sử dụng chúng đúng đòi hỏi nhận diện **kiểu dữ liệu**, **identity**, **tập rỗng**, **tính kết hợp**, **tràn số nguyên** và **quy tắc IEEE 754**. Với bài toán tổng/min/max nguyên thủy đơn giản, terminal methods chuyên dụng của Stream thường rõ hơn; với API cần callback, method reference biểu diễn quy tắc gộp ngắn, thuần và dễ kiểm thử. Không xem method reference là phép đồng bộ hay công cụ bảo vệ dữ liệu ngoài map/stream.

## Tài liệu chính thức Java — API còn áp dụng

- `Integer` — static `sum`, `min`, `max` (Since Java 8): https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Integer.html
- `Long` — static `sum`, `min`, `max`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Long.html
- `Double` — static `sum`, `min`, `max`; NaN/signed zero: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Double.html
- `Float` — static `sum`, `min`, `max`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Float.html
- `IntBinaryOperator`, `LongBinaryOperator`, `DoubleBinaryOperator`, `BinaryOperator`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/IntBinaryOperator.html
- `IntStream`, `LongStream`, `DoubleStream` — reduce, sum, min, max, Optional, numerical behavior: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html và https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/DoubleStream.html
- `java.util.stream` — reduction/associativity/statelessness/parallelism: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html
- `Map.merge`, `ConcurrentHashMap.merge` — gộp giá trị theo khóa: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html và https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html
- `Collectors.toMap` — xử lý duplicate keys với merge function: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html
- `Arrays.parallelPrefix` — phép tính lũy tích song song: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html
- `Math.addExact` và `BigInteger.add` — cộng có phát hiện tràn / số nguyên độ lớn không giới hạn thực tế: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html và https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigInteger.html
