# compare, compareTo, equals và hashCode — Java Core: Number và wrapper

## 1. Vì sao cùng là “so sánh số” mà Java có nhiều cách?

Java có nhiều kiểu số nguyên thủy (`byte`, `short`, `int`, `long`, `float`, `double`) và các lớp wrapper tương ứng (`Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`). Ngoài phép so sánh bằng toán tử `==`, người lập trình còn gặp:

- `Integer.compare(a, b)`, `Long.compare(a, b)`, `Double.compare(a, b)`…: **phương thức static** so sánh hai giá trị cùng kiểu primitive.
- `wrapperA.compareTo(wrapperB)`: **phương thức instance** so sánh thứ tự giữa các wrapper cùng lớp.
- `wrapperA.equals(other)`: **phương thức instance** quyết định hai đối tượng có được coi là cùng giá trị theo hợp đồng của lớp không.
- `wrapperA.hashCode()`: mã băm phù hợp với `equals` khi làm khóa trong `HashMap`, phần tử trong `HashSet`.
- Các toán tử `==`, `<`, `>`, `<=`, `>=`: so sánh **primitive** hoặc có thể kích hoạt unboxing khi toán hạng là wrapper.

Chúng có liên quan nhưng **không thay thế nhau một cách tùy tiện**. Ví dụ:

```java
Integer a = 9;
Long b = 9L;

System.out.println(a.equals(b)); // false
System.out.println(a.longValue() == b.longValue()); // true
```

`Integer.equals` không xem `Long` cùng lượng toán học là cùng kiểu đối tượng. Ngược lại, khi trích giá trị primitive và so sánh đúng kiểu, `9L == 9L` là true.

**Mục tiêu bài học:**

1. Phân biệt so sánh **giá trị**, **kiểu đối tượng**, **identity** và **thứ tự**.
2. Dùng đúng `compare` và `compareTo` cho signed integer, unsigned interpretation và floating point.
3. Hiểu `equals`/`hashCode`, hợp đồng bắt buộc và ảnh hưởng tới collection.
4. Xử lý đúng `Float`/`Double` với `NaN`, `+0.0` và `-0.0`.
5. Biết vì sao `==` trên wrapper không đáng dùng để so sánh giá trị đối tượng, đặc biệt với cache/boxing.
6. Tránh comparator bằng phép trừ, tránh so sánh “gần bằng epsilon” làm equality hoặc sắp xếp.
7. Đọc và kiểm thử các ví dụ Java 17+ với đầu ra có thể lặp lại.

**Phạm vi:** Number và các wrapper chuẩn Java, cách chúng tham gia so sánh/collection. `BigDecimal` và `BigInteger` chỉ được đưa vào để làm rõ trường hợp so sánh khác nhau trong họ `Number`, không biến bài này thành hướng dẫn tính toán thập phân chi tiết.

## 2. Kiểu primitive, wrapper và lớp `Number`

| Primitive | Wrapper | Họ kiểu trong Java | Comparable |
| --- | --- | --- | --- |
| `byte` | `Byte` | Kế thừa `Number` | `Comparable<Byte>` |
| `short` | `Short` | Kế thừa `Number` | `Comparable<Short>` |
| `int` | `Integer` | Kế thừa `Number` | `Comparable<Integer>` |
| `long` | `Long` | Kế thừa `Number` | `Comparable<Long>` |
| `float` | `Float` | Kế thừa `Number` | `Comparable<Float>` |
| `double` | `Double` | Kế thừa `Number` | `Comparable<Double>` |

`Number` là abstract class cung cấp cách **lấy giá trị dưới những kiểu số nhất định** qua `intValue()`, `longValue()`, `floatValue()`, `doubleValue()` và các phương thức chuyển đổi khác. Nó **không đưa ra một `compareTo` chung để so sánh mọi `Number`** và không quy định mọi subclass phải dùng chung một định nghĩa `equals`.

Điều đó có nghĩa:

```java
Number a = Integer.valueOf(5);
Number b = Double.valueOf(5.0);
```

Không thể đơn giản gọi `a.compareTo(b)` trên kiểu khai báo `Number`; `Number` không có `compareTo(Number)`. Nếu gọi `a.equals(b)`, dispatch tới `Integer.equals` và trả false. Cần xác định rõ chính sách so sánh khi nhận nhiều subclass `Number`; chuyển hết sang `double` cũng không tự an toàn vì có thể mất chính xác với số nguyên lớn hoặc `BigDecimal`.

### 2.1. Auto-boxing và unboxing

`Integer n = 9;` có thể được compiler chuyển thành thao tác boxing. `int x = n;` có thể được chuyển thành unboxing, tương đương lấy giá trị primitive. Khi có `null`:

```java
Integer missing = null;
// int x = missing; // runtime NullPointerException do unboxing
```

Các phương thức `compareTo` và `equals` cũng có quy tắc về null: `a.equals(null)` trả false nếu `a` khác null, trong khi `a.compareTo(null)` với `Integer a` không null thường ném `NullPointerException`. Nếu receiver `a` chính nó null, gọi method sẽ ném `NullPointerException`.

## 3. Bảng quyết định nhanh giữa các cách so sánh

| Mục đích | Cách dùng | Ghi chú |
| --- | --- | --- |
| Hai `int` có cùng giá trị? | `a == b` | Primitive equality |
| So thứ tự hai `int` không lo overflow? | `Integer.compare(a,b)` | Trả giá trị âm/0/dương |
| So thứ tự hai `long` | `Long.compare(a,b)` | Không dùng `(int)(a-b)` |
| So thứ tự hai wrapper cùng kiểu | `a.compareTo(b)` | Receiver/đối số phải có kiểu phù hợp |
| Hai wrapper có bằng theo hợp đồng lớp? | `a.equals(b)` | Null-safe nếu `a` chắc chắn khác null |
| Wrapper có thể null ở hai vế? | `Objects.equals(a,b)` | Trả true nếu hai tham chiếu đều null |
| Wrapper làm khóa hash? | `equals` đi cùng `hashCode` | Java wrappers đã có hợp đồng phù hợp |
| Sắp xếp dữ liệu số `double` | `Double.compare(a,b)` | Có quy tắc với NaN, signed zero |
| Diễn giải bit `int` dưới dạng không dấu | `Integer.compareUnsigned(a,b)` | Không thay bit, chỉ đổi thứ tự |
| Kiểm tra kết quả số thực nằm trong sai số? | Hàm `near(a,b,tolerance)` riêng | Không dùng làm `equals`/`compareTo` mặc định |

Cần phân biệt ý nghĩa `compare(a,b) < 0` với `compare(a,b) == -1`. Hợp đồng so sánh tổng quát chỉ bảo đảm **dấu của kết quả**, không bảo đảm luôn chỉ có `-1`, `0`, `1`. Ví dụ `Byte.compare((byte)-1, (byte)1)` có thể trả `-2` theo đặc tả phép trừ giá trị byte trong phương thức đó. Hãy viết `< 0`, `== 0`, `> 0`.

## 4. `compare`: phương thức static nhận primitive

Các lớp wrapper số có các phương thức so sánh static:

```java
int c1 = Integer.compare(9, 12);       // âm
int c2 = Long.compare(9L, 12L);        // âm
int c3 = Float.compare(9.0f, 12.0f);   // âm
int c4 = Double.compare(9.0, 12.0);    // âm
```

Dù tên thuộc lớp wrapper, đầu vào của các phương thức này là **primitive** (ví dụ `int,int` hoặc `double,double`) và kết quả là `int` biểu thị thứ tự.

Với `Byte`/`Short` cũng có `Byte.compare(byte,byte)`, `Short.compare(short,short)`. Các phương thức này hữu ích khi viết `Comparator` bằng lambda hoặc phương thức tham chiếu.

### 4.1. Không so sánh số nguyên bằng phép trừ

Đoạn mã sau có thể sai:

```java
// KHÔNG NÊN DÙNG:
Comparator<Integer> bad = (a, b) -> a - b;
```

Nếu `a=Integer.MAX_VALUE` và `b=-1`, hiệu số toán học vượt miền `int`; kết quả phép trừ `int` tràn, làm sai dấu thứ tự. Hãy dùng:

```java
Comparator<Integer> order = Integer::compare;
```

Hoặc:

```java
Comparator<Integer> order = Comparator.naturalOrder();
```

Đoạn `Comparator` cần import `java.util.Comparator` hoặc viết tên đầy đủ. Với `long`, tránh `return (int)(a-b);` vì vừa có nguy cơ `long` overflow vừa cắt xuống 32 bit; dùng `Long.compare(a,b)`.

### 4.2. Static compare trả thứ tự, không phải boolean

`Integer.compare(10,10)` trả số nguyên `0`. Nó **không** trả `true`; muốn hỏi bằng nhau thông qua compare, viết `Integer.compare(a,b)==0`, dù với primitive `int` thông thường `a==b` rõ hơn.

## 5. `compareTo`: hợp đồng Comparable của wrapper

Các wrapper triển khai `Comparable` cho **cùng loại đối tượng**. Ví dụ:

```java
Integer a = 9;
Integer b = 12;
System.out.println(a.compareTo(b)); // -1
```

Kết quả âm: `a` đứng trước `b`; kết quả 0: cùng vị trí theo natural ordering; kết quả dương: `a` đứng sau `b`.

`Integer.compareTo` nhận `Integer`; `Long.compareTo` nhận `Long`. Chúng **không** cho phép:

```java
Integer left = 9;
Long right = 9L;
// left.compareTo(right); // KHÔNG BIÊN DỊCH: Long không phải Integer
```

Tương tự, `Number` không có một natural ordering chung cho mọi subclass. `BigDecimal` và `BigInteger` có compareTo riêng của từng lớp.

### 5.1. Natural ordering và `Collections.sort`

Với một `List<Integer>`, có thể gọi `Collections.sort(list)` hoặc `list.sort(null)` để dùng natural ordering của `Integer`. Với một `List<Double>`, natural ordering của `Double` có quy tắc đặc biệt cho `NaN` và signed zero.

Đừng giả định rằng danh sách kiểu `List<Number>` trộn `Integer` với `Double` sẽ tự có một comparator đúng. Hãy chọn **mô hình dữ liệu đồng nhất** hoặc tự định nghĩa một thứ tự có hợp đồng rõ ràng.

### 5.2. `compareTo` và `equals` không luôn đồng nhất ở mọi loại Number

Các wrapper `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double` thiết kế natural ordering phù hợp với equality của chính lớp (đặc biệt `Float`/`Double` xử lý NaN/zero theo contract của wrapper).

Nhưng một subclass `Number` khác, như `BigDecimal`, có khác biệt:

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.compareTo(y)); // 0
System.out.println(x.equals(y));    // false
```

Hai `BigDecimal` bằng về **giá trị số** nhưng khác **scale**, nên `equals` trả false. Đoạn trên cần `import java.math.BigDecimal;`. Tình huống này cho thấy không thể khẳng định mọi đối tượng kế thừa `Number` có `compareTo()==0` đồng nghĩa `equals()==true`.

## 6. `equals`: bằng nhau theo hợp đồng lớp, không chỉ cùng con số

Với `Integer`:

```java
System.out.println(Integer.valueOf(9)
        .equals(Integer.valueOf(9))); // true

System.out.println(Integer.valueOf(9)
        .equals(Long.valueOf(9L)));   // false
```

`Integer.equals` yêu cầu đối tượng đối chiếu **là một `Integer`** và có cùng giá trị primitive `int`. `Long.equals` tương tự trong lớp `Long`. Vì thế `Integer.valueOf(9)` và `Long.valueOf(9)` không bằng theo `equals` dù cùng lượng toán học.

Một số ví dụ phân biệt:

| So sánh | Kết quả | Vì sao |
| --- | --- | --- |
| `Integer.valueOf(9).equals(Integer.valueOf(9))` | true | Cùng class, cùng giá trị |
| `Integer.valueOf(9).equals(Long.valueOf(9))` | false | Khác class |
| `Double.valueOf(9.0).equals(Float.valueOf(9.0f))` | false | Khác class |
| `Long.valueOf(9).equals(null)` | false | `equals(null)` |
| `Integer.valueOf(9).intValue() == 9` | true | Primitive int equality |
| `Integer.valueOf(9).longValue() == Long.valueOf(9L).longValue()` | true | Sau chuyển đổi phù hợp, primitive long equality |

**Không biến mọi `Number` thành `double` chỉ để so sánh.** `double` có 53 bit precision significand; nhiều giá trị `long` lớn hơn `2⁵³` không còn phân biệt chính xác. `BigDecimal.doubleValue()` cũng có thể làm tròn hoặc tràn sang vô cực, gây mất thông tin. Nếu domain thật sự cần so sánh giữa các loại `Number`, phải định nghĩa yêu cầu về miền/độ chính xác và chọn biểu diễn trung gian thích hợp.

### 6.1. `Objects.equals` chỉ xử lý null, không làm ép kiểu tương đương

`java.util.Objects.equals(a,b)` trả true nếu cả hai null; nếu một bên null thì false; nếu cả hai khác null thì sử dụng `a.equals(b)`.

`Objects.equals(Integer.valueOf(9), Long.valueOf(9))` vẫn false. Đây không phải phép “so sánh giá trị số tổng quát” mà là cách gọi `equals` an toàn khi có null.

## 7. `hashCode`: hợp đồng với `equals`

`hashCode` là phương thức từ `Object`. Với hai đối tượng `x`, `y`:

> Nếu `x.equals(y)` là true, thì **bắt buộc** `x.hashCode() == y.hashCode()`.

Chiều ngược lại **không bắt buộc**: hai đối tượng khác nhau vẫn có thể cùng hash, gọi là **hash collision**. Hash không phải mã định danh duy nhất và không bảo đảm tính bảo mật.

Các wrapper triển khai `hashCode` theo nội dung giá trị phù hợp `equals`:

- `Integer.hashCode(int value)` trả chính `int` đầu vào.
- `Long.hashCode(long value)` gộp các bit cao/thấp của `long` xuống `int`.
- `Float.hashCode(float value)` và `Double.hashCode(double value)` dựa trên biểu diễn bit phù hợp hợp đồng `equals`, gồm phân biệt signed zero và canonicalize NaN.
- `Byte` và `Short` dùng giá trị số tương ứng cho hash, theo quy tắc của từng API.

`Integer.hashCode(9)` là một **static method**, còn `Integer.valueOf(9).hashCode()` là **instance method**. Cả hai tạo hash tương ứng với cùng giá trị.

### 7.1. HashMap và HashSet

`HashMap`/`HashSet` dùng hash để tìm bucket ứng viên rồi dùng equality của khóa để xác định trùng hay không. Do đó:

```java
Set<Number> values = new HashSet<>();
values.add(Integer.valueOf(9));
values.add(Long.valueOf(9L));
System.out.println(values.size()); // 2
```

Cần import `java.util.Set` và `java.util.HashSet`; đoạn này là mảnh code đặt trong một phương thức. `Integer(9)` và `Long(9)` không bằng nhau theo `equals`, nên là hai phần tử khác nhau.

**Không dùng `hashCode` để kết luận hai đối tượng bằng nhau.** Hash giống chỉ là điều kiện kiểm tra nhanh, không thay `equals`.

**Không chọn hash ngẫu nhiên** cho một wrapper hoặc object bất biến. Nếu khóa tùy chỉnh có nhiều field, `equals` và `hashCode` phải dùng cùng ý niệm danh tính, tránh sửa field tham gia hash khi khóa đã được đưa vào map/set.

## 8. `==` trên wrapper: so tham chiếu hay unbox?

Khi cả hai toán hạng của `==` là **tham chiếu wrapper cùng loại** (ví dụ hai `Integer`), phép `==` có thể so **identity** của object, không phải nội dung. Vì Java boxing/valueOf có cache ở một số miền giá trị, kết quả có thể gây hiểu nhầm:

```java
Integer a = Integer.valueOf(42);
Integer b = Integer.valueOf(42);
boolean sameReference = (a == b); // true với Integer.valueOf trong miền -128..127

Integer c = Integer.valueOf(1000);
Integer d = Integer.valueOf(1000);
// c == d không nên được dùng làm kiểm tra giá trị: khả năng cache ngoài miền chuẩn tùy triển khai.
boolean sameValue = c.equals(d); // true
```

Để **so giá trị wrapper**, dùng `a.equals(b)` khi receiver chắc chắn không null, hoặc `Objects.equals(a,b)` khi có thể null. Để so primitive, unbox có chủ đích và xử lý null:

```java
Integer maybe = Integer.valueOf(42);
boolean equalsPrimitive = maybe != null && maybe.intValue() == 42;
```

### 8.1. Hai wrapper khác kiểu không dùng trực tiếp `==`

Hai tham chiếu thuộc hai lớp wrapper độc lập như `Integer` và `Long` **không thể trực tiếp so sánh với nhau bằng `==`**. Biểu thức này không được Java tự động unbox cả hai phía:

```java
Integer a = Integer.valueOf(9);
Long b = Long.valueOf(9L);
// boolean invalid = (a == b); // LỖI BIÊN DỊCH: incomparable types.
boolean sameNumericValue = a.longValue() == b.longValue(); // true.
boolean sameObjectValue = a.equals(b); // false: khác wrapper class.
```

Khi **một toán hạng là primitive**, ví dụ `a == 9L`, Java có thể unbox `Integer` thành `int` rồi widening lên `long` để so sánh. Nếu cả hai tham chiếu được khai báo là `Number`, phép `==` giữa chúng kiểm tra **cùng object** chứ không so sánh giá trị số. Khi muốn so sánh số của các wrapper khác kiểu, hãy chuyển đổi tường minh có bảo toàn miền và xử lý `null` trước khi gọi phương thức; `longValue()` phù hợp với cặp `Integer`/`Long`.

## 9. `Float`/`Double`: NaN và signed zero làm khác biệt rõ nhất

Số thực IEEE 754 có các giá trị đặc biệt mà số nguyên không có:

- `+0.0` và `-0.0`: hai mẫu bit khác nhau nhưng primitive `+0.0 == -0.0` là true.
- `NaN`: primitive `Double.NaN == Double.NaN` là false.
- `+Infinity`, `-Infinity`: vô cực có thứ tự số học tương ứng.

Với wrapper `Double`:

- `Double.compare(-0.0, +0.0)` trả số âm: **−0.0 đứng trước +0.0**.
- `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` trả false.
- `Double.compare(Double.NaN, Double.POSITIVE_INFINITY)` trả số dương: NaN đứng sau +Infinity.
- `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` trả true, dù primitive `NaN == NaN` false.

Các hành vi tương ứng cũng áp dụng cho `Float` ở độ rộng 32 bit.

### 9.1. Bảng đối chiếu thường dùng

| Biểu thức | Kết quả |
| --- | --- |
| `+0.0 == -0.0` | true |
| `Double.compare(-0.0,+0.0)` | giá trị âm (JDK trả -1) |
| `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` | false |
| `Double.NaN == Double.NaN` | false |
| `Double.compare(Double.NaN,Double.NaN)` | 0 |
| `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` | true |
| `Double.compare(Double.NaN,Double.POSITIVE_INFINITY)` | giá trị dương |
| `Double.hashCode(-0.0) == Double.hashCode(+0.0)` | false |

Vì sao wrapper có các lựa chọn này? `equals` của `Double` dựa trên `doubleToLongBits` để phân biệt ±0, và phương thức bit này **chuẩn hóa các mẫu NaN**. Natural ordering/`compare` được xác định nhất quán với equality của wrapper, phù hợp để làm khóa/sắp xếp theo semantics của `Double`.

**Đừng dùng dấu của số thực như điều kiện “thế nào cũng giống nhau vì zero”.** Signed zero có thể tác động đến phép chia, `Math.atan2`, `Math.min/max`. Nếu muốn gộp zero âm/dương cho một nghiệp vụ cụ thể, phải có chính sách chuẩn hóa riêng.

### 9.2. NaN không bằng chính nó dưới primitive `==`

`Double.NaN == Double.NaN` false là quy tắc của phép so sánh số thực primitive. Nhưng `Double.NaN` được bọc vào wrapper có hợp đồng `equals` khác, vốn cho phép các NaN được xem như một nhóm bằng nhau.

Đừng dùng `value == Double.NaN` để phát hiện NaN; dùng `Double.isNaN(value)` hoặc `Float.isNaN(value)`. Không dùng epsilon một cách tùy tiện để biến NaN thành một giá trị “gần bằng”.

### 9.3. Floating-point hash lấy bit đã canonicalize

`Double.hashCode(value)` dùng các bit tương thích với `Double.equals`, bao gồm canonicalize NaN. Nếu bạn tự viết `equals` trên raw bits bằng `doubleToRawLongBits` nhưng dùng `Double.hashCode` không xét khác biệt NaN payload, sự nhất quán “equal ⇒ same hash” vẫn có thể giữ, nhưng hai khái niệm equality/hash không mô tả hoàn toàn cùng tập thông tin; cần xem xét cẩn thận khi thiết kế khóa bit-level.

Một lựa chọn đơn giản khi muốn mô phỏng đúng wrapper là dùng `Double.doubleToLongBits` cho `equals` và `Double.hashCode` cho hash, thay vì tự cố gắng ghép logic signed zero/NaN từ các phép `==` riêng lẻ.

## 10. Chương trình chạy được A — `compare`, `compareTo`, `equals` và unsigned

Lưu thành **`WrapperComparison.java`**:

```java
public class WrapperComparison {
    public static void main(String[] args) {
        Integer a = Integer.valueOf(9);
        Integer b = Integer.valueOf(12);
        Long sameNumber = Long.valueOf(9L);

        System.out.println(Integer.compare(9, 12));
        System.out.println(a.compareTo(b));
        System.out.println(a.equals(Integer.valueOf(9)));
        System.out.println(a.equals(sameNumber));

        System.out.println(Integer.hashCode(9));
        System.out.println(Byte.compare((byte) -1, (byte) 1));

        System.out.println(Integer.compare(-1, 1));
        System.out.println(Integer.compareUnsigned(-1, 1));
        System.out.println(Long.compareUnsigned(-1L, 1L));
    }
}
```

Chạy với JDK 17+:

```bash
javac --release 17 WrapperComparison.java
java WrapperComparison
```

**Stdout chính xác:**

```text
-1
-1
true
false
9
-2
-1
1
1
```

Lưu ý:

1. `Integer.compare(9,12)` và `Integer(9).compareTo(Integer(12))` đều trả âm (ở trường hợp này là -1).
2. `Integer.equals` trả true với cùng `Integer(9)` nhưng false với `Long(9L)`.
3. `Integer.hashCode(9)` bằng 9.
4. `Byte.compare(-1,1)` trả `-2`; minh họa vì sao chỉ nên xét **dấu** của kết quả comparator, không yêu cầu luôn đúng `-1/0/1`.
5. Theo signed order, `-1` đứng trước `1`; theo unsigned interpretation của 32/64 bit, bit pattern toàn 1 lớn hơn 1. `compareUnsigned` không chuyển `int` thành một primitive unsigned mới.

## 11. Chương trình chạy được B — `Double`, NaN, signed zero và collection

Lưu thành **`FloatingWrapperComparison.java`**:

```java
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class FloatingWrapperComparison {
    public static void main(String[] args) {
        double positiveZero = +0.0;
        double negativeZero = -0.0;

        System.out.println(positiveZero == negativeZero);
        System.out.println(Double.compare(negativeZero, positiveZero));
        System.out.println(Double.valueOf(negativeZero)
                .equals(Double.valueOf(positiveZero)));

        System.out.println(Double.NaN == Double.NaN);
        System.out.println(Double.valueOf(Double.NaN)
                .equals(Double.valueOf(Double.NaN)));
        System.out.println(Double.compare(Double.NaN,
                Double.POSITIVE_INFINITY));

        Set<Double> hashed = new HashSet<>();
        hashed.add(positiveZero);
        hashed.add(negativeZero);
        hashed.add(Double.NaN);
        hashed.add(Double.NaN);
        System.out.println(hashed.size());

        TreeSet<Double> ordered = new TreeSet<>();
        ordered.add(positiveZero);
        ordered.add(negativeZero);
        ordered.add(Double.NaN);
        ordered.add(Double.NaN);
        System.out.println(ordered.size());
        System.out.println(ordered.first());
        System.out.println(ordered.last());
    }
}
```

Chạy:

```bash
javac --release 17 FloatingWrapperComparison.java
java FloatingWrapperComparison
```

**Stdout chính xác:**

```text
true
-1
false
false
true
1
3
3
-0.0
NaN
```

Giải thích:

- `primitive ==` coi hai signed zero bằng nhau; `Double.compare` và `Double.equals` phân biệt chúng.
- `NaN == NaN` false, trong khi `Double.equals` coi các NaN wrapper tương đương.
- `HashSet<Double>` dùng `equals`/`hashCode`, còn `TreeSet<Double>` dùng natural ordering; với những giá trị `Double` này, chúng đều giữ `+0.0`, `-0.0`, và một giá trị NaN, tổng `3` phần tử.
- `TreeSet.first()` là `-0.0`, `TreeSet.last()` là `NaN` theo thứ tự của `Double`; thứ tự duyệt `HashSet` không được dùng để suy ra natural ordering.

## 12. Chương trình chạy được C — boxing, null và `Objects.equals`

Lưu thành **`BoxingEquality.java`**:

```java
import java.util.Objects;

public class BoxingEquality {
    public static void main(String[] args) {
        Integer smallA = Integer.valueOf(42);
        Integer smallB = Integer.valueOf(42);
        Integer bigA = Integer.valueOf(1000);
        Integer bigB = Integer.valueOf(1000);

        System.out.println(smallA == smallB);
        System.out.println(bigA.equals(bigB));

        Integer missing = null;
        System.out.println(Objects.equals(missing, null));
        System.out.println(Objects.equals(missing, smallA));

        Integer n = Integer.valueOf(9);
        Long m = Long.valueOf(9L);
        System.out.println(n.equals(m));
        System.out.println(n.intValue() == m.longValue());
    }
}
```

Chạy:

```bash
javac --release 17 BoxingEquality.java
java BoxingEquality
```

**Stdout chính xác:**

```text
true
true
true
false
false
true
```

Đoạn code này **cố ý không in** `bigA == bigB`: việc cache ngoài vùng tối thiểu của `Integer.valueOf` có thể khác tùy triển khai/cấu hình, nên không đặt đầu ra đó làm hợp đồng portable. `equals` vẫn trả true với cùng nội dung số nguyên.

## 13. Lớp `Number` và so sánh hỗn hợp: tránh chuyển kiểu tùy tiện

Giả sử API nhận `Number x, Number y`. Có nhiều chính sách so sánh có thể đúng, nhưng phải chọn **một** dựa trên hợp đồng:

**Chính sách A — loại phải giống nhau:** chỉ chấp nhận cùng wrapper class và dùng `equals`. Hữu ích khi kiểu số mang ý nghĩa nghiệp vụ, chẳng hạn `int` là số đếm còn `double` là phép đo.

**Chính sách B — giá trị nguyên chính xác:** chỉ nhận các kiểu nguyên trong một miền xác định, chuyển sang `long` hoặc `BigInteger` với kiểm tra để so sánh, tránh làm tròn.

**Chính sách C — giá trị số thực theo độ chính xác được chấp nhận:** so sánh `doubleValue()` với tiêu chí phù hợp, đồng thời xử lý NaN/infinity. Nhưng không thích hợp nếu đầu vào chứa `BigDecimal` cực lớn hoặc số nguyên cần độ chính xác ngoài 53 bit.

**Chính sách D — sắp xếp kiểu số hỗn hợp:** phải định nghĩa thứ tự tổng quát cho loại, giá trị, NaN, ±Infinity, signed zero, những trường hợp không thể chuyển đổi chính xác. Thứ tự dựa trên kiểu trước rồi giá trị sau có thể phù hợp với một số domain, nhưng không đồng nghĩa thứ tự toán học giữa mọi `Number`.

**Cảnh báo:** ép tất cả `Number` sang `double` rồi gọi `Double.compare` có thể nhập nhằng những `long` lớn khác nhau. Ví dụ `9_007_199_254_740_992L` và `9_007_199_254_740_993L` có thể chuyển sang **cùng** giá trị `double` vì độ chính xác binary64 chỉ là 53 bit significand.

Nếu không có yêu cầu cụ thể cho so sánh nhiều lớp `Number`, giữ generic type nhất quán ngay từ API thường an toàn hơn.

## 14. Hợp đồng `Comparable` và `Comparator` khi đưa wrapper vào sort/map

Với `Comparable<T>`/`Comparator<T>`, dấu của kết quả phải mô tả thứ tự thỏa các quy tắc cơ bản: đối xứng dấu, tính bắc cầu và nhất quán khi so sánh bằng 0.

Một comparator hợp lệ cho dữ liệu đo kiểu `double` thường bắt đầu bằng:

```java
Comparator<Double> natural = Double::compare;
```

Một comparator hợp lệ cho đối tượng có field `double` có thể viết:

```java
Comparator<Sample> ordered =
        Comparator.comparingDouble(Sample::measurement)
                .thenComparingLong(Sample::id);
```

Trong đó `Sample` là một lớp/record có phương thức `measurement()` và `id()` phù hợp; đây là **mảnh mã**, không phải chương trình độc lập khi chưa định nghĩa `Sample`.

Tại sao có `thenComparingLong`? Khi hai `Sample` có cùng kết quả đo theo `Double.compare`, ứng dụng vẫn có thể muốn thứ tự phân biệt theo ID. Nhưng **Comparator.compare(a,b)==0 không buộc phải đồng nhất với a.equals(b) trong mọi tình huống**; nếu dùng làm khóa `TreeMap` hoặc `TreeSet`, sự không nhất quán với `equals` có thể làm hành vi khác kỳ vọng của `Map`/`Set`.

### 14.1. Tuyệt đối không biến epsilon thành comparator tùy tiện

Không viết:

```java
// Ý tưởng SAI:
int compare(double a, double b) {
    return Math.abs(a - b) <= 0.1 ? 0 : Double.compare(a, b);
}
```

Đây là mảnh method minh họa **không nên dùng**. Ba số `0.00`, `0.09` và `0.18` thỏa “0.00 gần 0.09”, “0.09 gần 0.18”, nhưng “0.00 không gần 0.18”. Quan hệ trả `0` không bắc cầu và vi phạm hợp đồng `Comparator`/`Comparable`.

Hãy tách **truy vấn số học gần bằng** khỏi **equality và ordering**:

```java
static boolean near(double a, double b, double tolerance) {
    if (!Double.isFinite(a) || !Double.isFinite(b)
            || !Double.isFinite(tolerance) || tolerance < 0) {
        return false; // một chính sách miền dữ liệu cụ thể
    }
    return Math.abs(a - b) <= tolerance;
}
```

Đây là một phương thức **truy vấn riêng** cho các số hữu hạn; không dùng làm `equals`/`compareTo`. Với thang giá trị rất rộng, cần cân nhắc relative tolerance, overflow của phép trừ và yêu cầu nghiệp vụ. Tolerance phải được xác định theo đơn vị đo, không tự lấy một epsilon cho mọi trường.

## 15. `equals` và `compareTo` của `BigDecimal` khác nhau

`BigDecimal` là subclass của `Number` với cách biểu diễn **unscaled value** và **scale**. Các ví dụ:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));      // false
System.out.println(a.compareTo(b));   // 0
```

Cần `import java.math.BigDecimal;`.

- `equals` của `BigDecimal` xét **giá trị cùng scale**: `2.0` có scale 1, `2.00` có scale 2.
- `compareTo` xét **giá trị số**: cả hai bằng 2 nên trả 0.
- `hashCode` của hai `BigDecimal` có thể khác, phù hợp với `equals` của lớp đó.
- `HashSet<BigDecimal>` có thể giữ cả `2.0` và `2.00`; `TreeSet<BigDecimal>` có natural ordering theo `compareTo` và có thể coi chúng là cùng vị trí trong cây.

Đây là ví dụ tiêu biểu về một natural ordering **không nhất quán với equals**; không áp dụng kết luận này cho mọi wrapper. Khi nghiệp vụ muốn “cùng số thập phân nhưng bỏ qua scale”, hãy định nghĩa một chính sách canonicalization minh bạch, cân nhắc cách `stripTrailingZeros` thay đổi scale và trường hợp zero. Không dùng `equals` mặc định rồi giả định nó giống `compareTo`.

### 15.1. Chương trình ngắn chứng minh khác biệt collection

Lưu thành **`DecimalCollectionIdentity.java`**:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.TreeSet;

public class DecimalCollectionIdentity {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println(a.equals(b));
        System.out.println(a.compareTo(b));

        HashSet<BigDecimal> hashed = new HashSet<>();
        hashed.add(a);
        hashed.add(b);
        System.out.println(hashed.size());

        TreeSet<BigDecimal> ordered = new TreeSet<>();
        ordered.add(a);
        ordered.add(b);
        System.out.println(ordered.size());
    }
}
```

Chạy:

```bash
javac --release 17 DecimalCollectionIdentity.java
java DecimalCollectionIdentity
```

**Stdout:**

```text
false
0
2
1
```

`HashSet` dùng `equals`/`hashCode`, `TreeSet` dùng `compareTo`. Nếu scale quan trọng cho nghiệp vụ, natural ordering của `BigDecimal` có thể **không** phù hợp làm chính sách loại trùng; lựa chọn cần dựa trên dữ liệu thực tế.

## 16. Những trường hợp đặc biệt cần kiểm tra khi wrapper được dùng làm khóa

### 16.1. Null

`Integer.compare(a,b)` nhận primitive nên nếu `a` hoặc `b` là wrapper null và được unbox sẽ ném `NullPointerException`. `Integer.compareTo(null)` cũng không định nghĩa null như một `Integer` hợp lệ.

Nếu collection cho phép null trong dữ liệu và cần sắp xếp, dùng `Comparator.nullsFirst` hoặc `Comparator.nullsLast` quanh comparator phù hợp, ví dụ:

```java
Comparator<Integer> byValueWithNull =
        Comparator.nullsLast(Integer::compare);
```

Đoạn này cần `import java.util.Comparator;`.

### 16.2. Signed zero và NaN

Nếu `+0.0` và `-0.0` phải có cùng danh tính nghiệp vụ, mặc định `Double.equals`/`Double.compare` **không** gom chúng. Có thể chuẩn hóa tại ranh giới:

```java
static double normalizeZero(double value) {
    return value == 0.0 ? 0.0 : value;
}
```

Nhưng dấu zero có thể ảnh hưởng phép chia và `Math.atan2`; chỉ chuẩn hóa khi phù hợp.

Với NaN, `Double.compare` đặt NaN lớn hơn các giá trị số khác và `Double.equals` canonicalize các mẫu NaN. Nếu NaN là giá trị dữ liệu lỗi, lựa chọn tốt hơn có thể là **không cho nó vào khóa**, thay vì mặc nhiên sắp sau infinity.

### 16.3. So sánh unsigned

`Integer.compare(-1,1)` và `Integer.compareUnsigned(-1,1)` cho thứ tự ngược nhau. Một trường dữ liệu chứa 32 bit nhưng được diễn giải unsigned theo giao thức phải dùng `compareUnsigned` khi thứ tự không dấu là yêu cầu; khi dùng `equals`/`hashCode` theo bit-pattern `Integer`, equality có thể vẫn đúng vì bit không đổi.

### 16.4. Immutable keys

Các wrapper chuẩn là bất biến. Nhưng nếu một object bao wrapper được tự viết và chứa field mutable quyết định `equals`/`hashCode`, sửa field đó sau khi đưa vào `HashMap`/`HashSet` có thể khiến việc tra cứu sai bucket. Giữ khóa bất biến hoặc quản lý cập nhật bằng xóa rồi chèn lại theo đúng chính sách.

## 17. Checklist chọn đúng API theo tình huống

- Khi dữ liệu là hai primitive `int`: dùng `==` cho bằng nhau, `Integer.compare` cho thứ tự.
- Khi dữ liệu là hai `Integer` non-null: dùng `equals` cho equality, `compareTo`/`Integer.compare` cho thứ tự.
- Khi wrapper có thể null: dùng `Objects.equals` hoặc comparator null-aware.
- Khi trộn `Integer` và `Long`: không tự coi `equals` là numeric equality xuyên kiểu; chọn miền/cách chuyển phù hợp.
- Khi xử lý `Double`: nhớ khác nhau giữa `==`, `equals` và `Double.compare` với `NaN`/signed zero.
- Khi so sánh dữ liệu nhị phân không dấu: dùng `compareUnsigned` theo nhu cầu.
- Khi sắp xếp: không trả hiệu số nguyên hoặc chênh lệch số thực ép thành `int`.
- Khi làm khóa `HashMap`: tuân thủ `equals`/`hashCode`; không dùng hash riêng lẻ làm kết luận bằng nhau.
- Khi làm khóa `TreeMap`: comparator hợp lệ, transitive và nhất quán; biết `compare==0` quyết định trùng khóa.
- Khi dùng `BigDecimal`: quyết định scale có phải một phần danh tính không.
- Khi đo gần bằng: dùng hàm riêng có tolerance/phạm vi rõ, không nhét vào `equals` hoặc comparator.

## 18. Bài tập kèm đáp án

### Bài 1 — `Integer` và `Long` cùng số

`Integer a = 9; Long b = 9L;`. `a.equals(b)` là gì, và tại sao?

**Đáp án:** false. `Integer.equals` đòi đối tượng bên phải là `Integer`; `Long` là class khác. `a.longValue() == b.longValue()` sẽ là true với dữ liệu này.

### Bài 2 — Static và instance compare

Viết hai cách so thứ tự hai giá trị 9 và 12 bằng `Integer`. Chúng trả kết quả gì?

**Đáp án:** `Integer.compare(9,12)` và `Integer.valueOf(9).compareTo(Integer.valueOf(12))` cùng trả số âm (ở đây là `-1`).

### Bài 3 — Hash collision

Nếu `x.hashCode() == y.hashCode()`, có đủ khẳng định `x.equals(y)` true không?

**Đáp án:** không. Hai đối tượng khác nhau có thể trùng hash; chỉ chiều `equals true ⇒ hash equal` là bắt buộc.

### Bài 4 — Byte.compare

Vì sao `Byte.compare((byte)-1,(byte)1)` có thể trả `-2` mà vẫn đúng?

**Đáp án:** API so sánh chỉ yêu cầu dấu âm/0/dương thể hiện thứ tự; không phải luôn trả đúng `-1,0,1`. `-2 < 0` phản ánh -1 nhỏ hơn 1.

### Bài 5 — Signed vs unsigned

Tính dấu của `Integer.compare(-1,1)` và `Integer.compareUnsigned(-1,1)`.

**Đáp án:** signed so sánh trả âm; unsigned so sánh trả dương. Cùng bit pattern của -1 được đọc là số unsigned 32-bit lớn nhất.

### Bài 6 — Cache/identity

Tại sao `Integer.valueOf(42) == Integer.valueOf(42)` có thể true, nhưng không nên dùng `==` để so giá trị hai `Integer` tùy ý?

**Đáp án:** `Integer.valueOf` cache các giá trị nhỏ trong miền được bảo đảm; `==` giữa hai `Integer` so identity tham chiếu. Với giá trị ngoài miền cache chuẩn, không có bảo đảm identity, trong khi `equals` vẫn so giá trị.

### Bài 7 — Signed zero

`Double.compare(-0.0,+0.0)` và `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` cho gì?

**Đáp án:** compare trả âm; equals trả false. Primitive `-0.0 == +0.0` lại true.

### Bài 8 — NaN

`Double.NaN == Double.NaN` và `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` cho gì?

**Đáp án:** false và true. Wrapper canonicalize NaN cho equality.

### Bài 9 — HashSet/TreeSet với Double

Thêm `+0.0`, `-0.0`, `Double.NaN` hai lần vào hai tập `HashSet<Double>` và `TreeSet<Double>`; mỗi tập có mấy phần tử?

**Đáp án:** 3. Cả hai đều phân biệt hai zero, nhưng hai NaN được coi tương đương theo `Double.equals` và natural ordering.

### Bài 10 — BigDecimal và scale

`new BigDecimal("2.0").compareTo(new BigDecimal("2.00"))` và `equals` cho gì?

**Đáp án:** 0 và false. `compareTo` xét giá trị số; `equals` còn xét scale.

### Bài 11 — Comparator bằng hiệu số

Vì sao `(a,b) -> a-b` không là lựa chọn an toàn cho `Comparator<Integer>`?

**Đáp án:** phép trừ `int` có thể overflow, khiến dấu của kết quả không còn phản ánh thứ tự. Dùng `Integer.compare(a,b)`.

### Bài 12 — Number hỗn hợp

Tại sao dùng `a.doubleValue() == b.doubleValue()` trên mọi `Number` là nguy hiểm?

**Đáp án:** mất chính xác với `long` lớn hơn miền biểu diễn nguyên chính xác của `double`, với `BigDecimal` có precision cao, và gây nhầm giữa NaN/signed zero nếu coi như một equality tổng quát. Phải xác định miền dữ liệu/hợp đồng trước khi chuyển.

### Bài 13 — Null

`Integer a = null;`. `Objects.equals(a,null)` trả gì? `a.compareTo(1)` thì sao?

**Đáp án:** true với `Objects.equals` vì cả hai null; gọi method trên receiver null gây `NullPointerException`.

### Bài 14 — Hash và cây với BigDecimal

Thêm `2.0` và `2.00` dưới dạng `BigDecimal` vào `HashSet` và `TreeSet`. Kết quả kích thước?

**Đáp án:** HashSet có 2, TreeSet có 1 theo default equality/natural ordering của `BigDecimal`.

## 19. Tài liệu Java SE 17 để đối chiếu

- [Java SE 17 Number API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Number.html): class trừu tượng cho các wrapper số.
- [Integer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `compare`, `compareUnsigned`, `compareTo`, `equals`, `hashCode`, `valueOf`.
- [Long API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): so sánh signed/unsigned và hash.
- [Byte API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html) và [Short API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Short.html): so sánh và promotion.
- [Float API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html) và [Double API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): signed zero/NaN và bit-based equality.
- [Object.equals/hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): hợp đồng equality và hash.
- [Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html) và [Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): natural ordering, comparator contract.
- [HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html), [TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html): tiêu chí trùng phần tử.
- [BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `compareTo` vs `equals` khi scale khác nhau.

**Kết luận:** dùng **`compare`/`compareTo`** để biểu đạt *thứ tự*, **`equals`** để biểu đạt *bằng nhau theo hợp đồng lớp*, và **`hashCode`** để hỗ trợ *tra cứu dựa trên equality*. Với wrapper số, luôn xem xét **kiểu**, **null**, **boxing identity**, **signed/unsigned**, **NaN**, **±0.0** và **scale** thay vì mặc nhiên coi “cùng lượng toán học” là cùng khóa Java.