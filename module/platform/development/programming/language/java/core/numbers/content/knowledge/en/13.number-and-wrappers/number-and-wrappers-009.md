# Wrapper khác kiểu không tự bằng nhau qua equals trong Java

Trong Java, các wrapper số như `Byte`, `Short`, `Integer`, `Long`, `Float` và `Double` đều kế thừa `Number`, nhưng **`equals(Object)` của mỗi wrapper đòi đối tượng còn lại thuộc đúng loại wrapper tương ứng**. Vì thế:

~~~java
Integer a = Integer.valueOf(42);
Long b = Long.valueOf(42L);

System.out.println(a.equals(b)); // false
~~~

Hai đối tượng biểu diễn cùng giá trị toán học 42, nhưng **không bằng nhau theo hợp đồng `Integer.equals`**. Đây là hành vi có chủ đích, không phải Java quên tự nâng kiểu. Bài học tập trung vào ranh giới giữa **bằng nhau theo kiểu đối tượng**, **bằng nhau theo số học**, **so sánh primitive**, và hệ quả trong collections.

## 1. Tại sao `Integer.equals(Long)` là false?

`Integer` lưu một giá trị `int`; `Long` lưu một giá trị `long`. Phương thức `Integer.equals(Object obj)` chỉ trả `true` khi `obj` là `Integer` có cùng giá trị `int`. Tương tự, `Long.equals` chỉ chấp nhận một `Long` có cùng giá trị `long`.

~~~java
Integer i = Integer.valueOf(42);
Long l = Long.valueOf(42L);
Double d = Double.valueOf(42.0);

boolean sameInteger = i.equals(Integer.valueOf(42)); // true
boolean integerVsLong = i.equals(l);                  // false
boolean longVsDouble = l.equals(d);                   // false
~~~

| Lời gọi | Kết quả | Vì sao? |
| --- | --- | --- |
| `Integer.valueOf(42).equals(Integer.valueOf(42))` | `true` | Cùng kiểu `Integer` và cùng `int` |
| `Integer.valueOf(42).equals(Long.valueOf(42L))` | `false` | `Long` không phải `Integer` |
| `Long.valueOf(42L).equals(Double.valueOf(42.0))` | `false` | `Double` không phải `Long` |
| `Double.valueOf(42.0).equals(Double.valueOf(42.0))` | `true` | Cùng kiểu `Double` và cùng giá trị |
| `Float.valueOf(42.0f).equals(Double.valueOf(42.0))` | `false` | Wrapper khác kiểu |

**Hợp đồng của `equals(Object)` khác phép so sánh các primitive có tự động widening.** Tham số của `equals` là `Object`, và Java không tự unbox/nâng kiểu hai đối tượng để so sánh giá trị số. Trong triển khai của các wrapper, logic kiểm tra loại trước khi xét giá trị.

Không dùng lập luận “cả hai đều là `Number`” để dự đoán `equals`: lớp cha `Number` **không định nghĩa một cơ chế equality số học chung** cho tất cả subclass. Đối tượng thực tế quyết định phương thức `equals` nào được chạy theo dynamic dispatch.

## 2. `==` giữa primitive và `equals` giữa wrapper khác nhau

### Hai primitive được nâng kiểu số học

~~~java
int x = 42;
long y = 42L;

System.out.println(x == y); // true
~~~

Với `int` và `long`, phép so sánh `==` áp dụng binary numeric promotion: `int` được widening thành `long`, sau đó so sánh hai primitive. Do vậy kết quả là `true`.

### Wrapper được so với primitive có thể bị unbox

~~~java
Integer wrapper = Integer.valueOf(42);
long primitive = 42L;

System.out.println(wrapper == primitive); // true
~~~

Vì một phía là primitive số, Java unbox `wrapper` thành `int`, rồi widening `int → long` để so sánh. Nếu `wrapper` là `null`, phép unboxing có thể ném `NullPointerException`.

### Hai wrapper khác kiểu không tự unbox để dùng `==`

Đoạn sau **cố ý không biên dịch**:

~~~java
Integer i = Integer.valueOf(42);
Long l = Long.valueOf(42L);

// boolean eq = i == l; // ERROR: incomparable types: Integer and Long
~~~

`i` và `l` đều có kiểu tham chiếu; trong trường hợp này, phép `==` không kích hoạt cùng chuỗi unboxing + widening như khi có một toán hạng primitive. Hai lớp wrapper độc lập `Integer` và `Long` không phải các kiểu tham chiếu có thể so sánh bằng `==` với nhau.

Nếu cả hai đều được khai báo là `Number` hoặc `Object` thì `==` giữa hai biến tham chiếu có thể biên dịch, nhưng kết quả lúc đó là **đồng nhất tham chiếu**, không phải so sánh giá trị số.

~~~java
Number a = Integer.valueOf(42);
Number b = Long.valueOf(42L);
boolean sameReference = a == b; // false
boolean sameByEquals = a.equals(b); // false
~~~

Ngay cả với **hai `Integer`**, `==` giữa hai tham chiếu chỉ kiểm tra xem đó có phải cùng một object hay không. Đừng dựa vào bộ đệm wrapper (`Integer.valueOf` có cache ở một miền giá trị) để suy luận rằng `==` là so sánh số. Hãy dùng `equals` nếu muốn equality theo kiểu wrapper hoặc unbox nếu thực sự muốn so sánh primitive và đã xử lý `null`.

## 3. `Number` và polymorphism không tự cung cấp equality xuyên kiểu

Một biến khai báo `Number` vẫn tham chiếu đến một object cụ thể như `Integer` hay `Long`:

~~~java
Number left = Integer.valueOf(42);
Number right = Long.valueOf(42L);

System.out.println(left.equals(right)); // false
~~~

Lời gọi `left.equals(right)` chạy implementation của `Integer.equals` vì object phía trái là `Integer`. Nó kiểm tra object phía phải có phải `Integer` không; kết quả là `false`. Java không nhìn thấy hai object cùng kế thừa `Number` rồi mặc định gọi `longValue()` để so sánh.

Điểm quan trọng: **kiểu tĩnh `Number` giúp truy cập các phép chuyển giá trị** như `intValue()`, `longValue()`, `doubleValue()`, nhưng không thiết lập khái niệm “cùng một số” thống nhất cho tất cả wrapper hoặc mọi subclass của `Number`.

Ngoài các wrapper, các lớp như `BigInteger` và `BigDecimal` cũng kế thừa `Number` và có hợp đồng `equals` riêng. Khi nhận tham số tổng quát `Number`, một phương thức phải chủ động quyết định mình muốn so sánh điều gì: cùng object, cùng kiểu và giá trị, hay cùng giá trị số học sau chuyển đổi có kiểm soát.

## 4. `Objects.equals` an toàn null nhưng không chuyển kiểu số

`Objects.equals(a, b)` là công cụ thuận tiện để so sánh object có thể null. Nó trả `true` nếu cùng tham chiếu (bao gồm cùng null); nếu chỉ `a` khác null thì gọi `a.equals(b)`. **Nó không normalize wrapper**, không chuyển `Integer` sang `Long`.

~~~java
Integer i = Integer.valueOf(42);
Long l = Long.valueOf(42L);

System.out.println(java.util.Objects.equals(i, l)); // false
System.out.println(java.util.Objects.equals(null, null)); // true
~~~

Dùng `Objects.equals` khi mục tiêu là **object equality** và cần tránh tự gọi `null.equals(...)`. Nếu mục tiêu là **numeric equivalence giữa nhiều kiểu khác nhau**, cần chính sách chuyển đổi và so sánh riêng. Đổi từ `i.equals(l)` sang `Objects.equals(i, l)` không giải quyết khác biệt kiểu.

## 5. Hệ quả trong `HashSet`, `HashMap` và khóa kiểu `Number`

Các collection băm dùng `equals` và `hashCode`. Vì `Integer(42)`, `Long(42)` và `Double(42.0)` không bằng nhau theo `equals`, chúng là **ba phần tử riêng** trong một tập `Set<Number>`:

~~~java
java.util.Set<Number> values = new java.util.HashSet<>();
values.add(Integer.valueOf(42));
values.add(Long.valueOf(42L));
values.add(Double.valueOf(42.0));

System.out.println(values.size()); // 3
~~~

Một `Map<Number, String>` cũng có thể giữ riêng các khóa `Integer.valueOf(42)` và `Long.valueOf(42L)`. Điều này tác động đến cache, thống kê, deduplication, ánh xạ ID và việc lấy giá trị: `map.get(42L)` không tương đương `map.get(42)` khi khóa được lưu bằng wrapper khác loại.

**Điều kiện thiết kế:** Nếu “ID 42” chỉ có một kiểu số hợp lệ, hãy chuẩn hóa **kiểu khóa lúc nhập**, ví dụ dùng `Long` cho toàn bộ khóa ID có miền `long` hoặc `BigInteger` nếu cần số nguyên rất lớn. Tránh tạo `Map<Number, ...>` rồi hy vọng các wrapper khác kiểu gộp về cùng một khóa.

Không tự viết `equals` cho object nghiệp vụ kiểu “đôi khi so sánh `Integer` với `Long` theo `doubleValue`” rồi giữ `hashCode` cũ: hai đối tượng được coi là bằng nhau bắt buộc có hash code tương ứng. Quy tắc nhất quán của `equals`/`hashCode` cần được duy trì.

## 6. Muốn so sánh *giá trị số* giữa hai wrapper thì làm thế nào?

Trước hết phải định nghĩa rõ **miền dữ liệu**. Không có một phép ép chung nào đúng cho mọi giá trị của `Number`.

### Trường hợp A — biết chắc cả hai là số nguyên primitive và vừa miền `long`

~~~java
Integer i = Integer.valueOf(42);
Long l = Long.valueOf(42L);

boolean sameNumericValue = i.longValue() == l.longValue(); // true
~~~

Cách này hợp lệ vì `Integer` và `Long` đều biểu diễn số nguyên chính xác trong phạm vi `long`. Nó cũng dùng được cho `Byte`/`Short`, khi đã kiểm soát các kiểu đầu vào. Nhưng **không áp dụng bừa bãi cho `BigInteger` vượt miền long hoặc số `Double` chứa phần thập phân**, vì các lời gọi `longValue()` tương ứng có thể làm mất thông tin.

Nếu cần chuẩn hóa nhiều wrapper số nguyên, có thể chuyển sang `BigInteger`:

~~~java
java.math.BigInteger fromInt =
        java.math.BigInteger.valueOf(Integer.valueOf(42).longValue());
java.math.BigInteger fromLong =
        java.math.BigInteger.valueOf(Long.valueOf(42L).longValue());

boolean equalIntegers = fromInt.equals(fromLong); // true
~~~

Với dữ liệu đã là `BigInteger`, giữ chính đối tượng đó; đừng chuyển nó về `long` rồi lại xây lại `BigInteger`.

### Trường hợp B — yêu cầu thập phân có độ chính xác và chính sách rõ

Nếu hệ thống nhận giá trị thập phân như `"42.0"` và `"42.00"`, `BigDecimal` cung cấp cả object equality và numeric comparison:

~~~java
java.math.BigDecimal x = new java.math.BigDecimal("42.0");
java.math.BigDecimal y = new java.math.BigDecimal("42.00");

boolean objectEqual = x.equals(y);   // false: khác scale
boolean numericEqual = x.compareTo(y) == 0; // true
~~~

`BigDecimal.equals` đòi **cùng giá trị và cùng scale**, còn `compareTo` so sánh giá trị số thập phân và bỏ qua scale khác nhau. Nếu cần key thập phân mà coi `42.0` và `42.00` giống nhau, hãy quy định chiến lược chuẩn hóa scale hoặc kiểu khóa từ đầu, và hiểu tác động lên `HashMap`/`TreeMap`. `BigDecimal` là một subclass của `Number` nhưng không phải wrapper primitive.

### Trường hợp C — số thực và giá trị gần bằng

`doubleValue()` giúp đưa nhiều `Number` về kiểu `double`, nhưng **không bảo toàn mọi giá trị số**. Ví dụ hai số nguyên `long` liền nhau ở vùng trên `2^53` có thể chuyển thành cùng một `double`:

~~~java
long a = 9_007_199_254_740_993L; // 2^53 + 1
long b = 9_007_199_254_740_992L; // 2^53

boolean equalAsLong = a == b; // false
boolean equalAsDouble = (double) a == (double) b; // true
~~~

Đổi cả hai sang `double` rồi `==` có thể báo bằng nhau sai. Tương tự, số cực lớn có thể thành vô cực, số rất nhỏ có thể bị làm tròn; NaN và ±0 có các quy tắc đặc biệt. Nếu bài toán hỗn hợp integer/floating cần so sánh **chính xác**, phải định nghĩa cách xử lý miền, dấu, NaN, vô cực, overflow và phương pháp chuyển đổi trước khi xây comparator.

Nếu nghiệp vụ chỉ cần “gần bằng” với dung sai, hãy viết một phép kiểm tra riêng cho dữ liệu hữu hạn, với tolerance hợp lý theo thang đo. **Không dùng phép so sánh gần bằng theo epsilon làm `equals`/comparator cho collection** nếu nó không bảo đảm bắc cầu và nhất quán.

## 7. Wrapper số thực còn có quy tắc riêng về NaN và số 0 có dấu

`Float.equals` và `Double.equals` cũng yêu cầu **cùng wrapper type**. Ngoài ra, chúng sử dụng quy tắc so sánh bit chuẩn hóa NaN:

- Hai object `Double` chứa NaN được `Double.equals` xem bằng nhau, dù toán tử primitive `Double.NaN == Double.NaN` là `false`.
- `Double.valueOf(+0.0).equals(Double.valueOf(-0.0))` là `false`, dù primitive `+0.0 == -0.0` là `true`.
- `Float.valueOf(Float.NaN).equals(Double.valueOf(Double.NaN))` là `false` vì **khác wrapper type**, dù cả hai đều biểu thị NaN.

~~~java
Double d1 = Double.valueOf(Double.NaN);
Double d2 = Double.valueOf(Double.NaN);
Float f = Float.valueOf(Float.NaN);

boolean sameDoubleNaNs = d1.equals(d2); // true
boolean floatVsDoubleNaN = f.equals(d1); // false
boolean signedZeroDifferent =
        Double.valueOf(0.0).equals(Double.valueOf(-0.0)); // false
~~~

Trong các thuật toán cần sắp xếp `Float`/`Double`, `Float.compare` và `Double.compare` định nghĩa thứ tự phù hợp với wrapper: NaN được coi bằng NaN trong `compare`, và `-0.0` đứng trước `+0.0`. Điều đó không tạo ra equality chung giữa `Float` với `Double`.

## 8. Ví dụ Java 17+ hoàn chỉnh

Lưu tệp tên `WrapperEquality.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class WrapperEquality {
    public static void main(String[] args) {
        Integer integer = Integer.valueOf(42);
        Long longValue = Long.valueOf(42L);
        Double doubleValue = Double.valueOf(42.0);
        Number left = integer;
        Number right = longValue;

        System.out.println("Integer.equals(Long) = "
                + integer.equals(longValue));
        System.out.println("Long.equals(Double) = "
                + longValue.equals(doubleValue));
        System.out.println("Integer.equals(Integer) = "
                + integer.equals(Integer.valueOf(42)));
        System.out.println("Objects.equals(Integer, Long) = "
                + Objects.equals(integer, longValue));
        System.out.println("Number.equals(Long) = "
                + left.equals(longValue));
        System.out.println("int == long = " + (42 == 42L));
        System.out.println("Integer == long = " + (integer == 42L));
        System.out.println("Number reference == = " + (left == right));

        Set<Number> numbers = new HashSet<>();
        numbers.add(integer);
        numbers.add(longValue);
        numbers.add(doubleValue);
        System.out.println("HashSet size = " + numbers.size());
        System.out.println("contains Long(42) = "
                + numbers.contains(Long.valueOf(42L)));

        long large = 9_007_199_254_740_993L;
        System.out.println("large as double = " + (double) large);
        System.out.println("large double == previous double = "
                + ((double) large == (double) (large - 1)));
        System.out.println("BigInteger exact compare = "
                + BigInteger.valueOf(large)
                .compareTo(BigInteger.valueOf(large - 1)));

        BigDecimal decimalA = new BigDecimal("42.0");
        BigDecimal decimalB = new BigDecimal("42.00");
        System.out.println("BigDecimal equals = "
                + decimalA.equals(decimalB));
        System.out.println("BigDecimal compareTo = "
                + decimalA.compareTo(decimalB));
        System.out.println("Double NaN equals NaN = "
                + Double.valueOf(Double.NaN)
                .equals(Double.valueOf(Double.NaN)));
        System.out.println("Float NaN equals Double NaN = "
                + Float.valueOf(Float.NaN)
                .equals(Double.valueOf(Double.NaN)));
        System.out.println("Double +0 equals -0 = "
                + Double.valueOf(+0.0).equals(Double.valueOf(-0.0)));
        System.out.println("Objects.equals(null, null) = "
                + Objects.equals(null, null));
    }
}
~~~

Biên dịch/chạy bằng Java 17 trở lên:

~~~bash
javac WrapperEquality.java
java WrapperEquality
~~~

Stdout:

~~~text
Integer.equals(Long) = false
Long.equals(Double) = false
Integer.equals(Integer) = true
Objects.equals(Integer, Long) = false
Number.equals(Long) = false
int == long = true
Integer == long = true
Number reference == = false
HashSet size = 3
contains Long(42) = true
large as double = 9.007199254740992E15
large double == previous double = true
BigInteger exact compare = 1
BigDecimal equals = false
BigDecimal compareTo = 0
Double NaN equals NaN = true
Float NaN equals Double NaN = false
Double +0 equals -0 = false
Objects.equals(null, null) = true
~~~

Mười chín dòng kết quả minh họa sự khác nhau giữa wrapper `equals` và primitive equality, hệ quả trong tập hợp, sai số của `doubleValue` và quy tắc riêng cho NaN/zero có dấu.

## 9. Những lỗi thường gặp khi xử lý wrapper khác kiểu

1. **Cho rằng hai wrapper cùng giá trị toán học luôn `equals`.** `Integer.valueOf(42).equals(Long.valueOf(42L))` là `false` vì type khác nhau.
2. **Dùng `Objects.equals` như phép chuẩn hóa số.** Nó chỉ bao bọc object equality và xử lý `null` an toàn.
3. **Thấy `Number` rồi dùng `Number.equals` như một hợp đồng số học chung.** `Number` không triển khai một equality xuyên các subclass.
4. **Dùng `==` giữa hai wrapper để đo giá trị.** Nếu hai tham chiếu cùng loại, đó thường là kiểm tra cùng object; nếu wrapper khác kiểu như `Integer` và `Long`, biểu thức có thể không biên dịch. Với một toán hạng primitive, unboxing có thể diễn ra và gây `NullPointerException` khi wrapper null.
5. **Gộp mọi `Number` về `doubleValue` để so sánh.** Với số nguyên lớn hơn `2^53`, hai số khác nhau có thể thành cùng một `double`, khiến kết luận sai.
6. **Lấy dữ liệu mixed numeric làm khóa `Map<Number, ...>` rồi mong truy vấn bằng wrapper khác kiểu trúng cùng entry.** Cần chuẩn hóa kiểu khóa theo đặc tả dữ liệu.
7. **Nhầm `BigDecimal.equals` với `BigDecimal.compareTo`.** `42.0` và `42.00` có giá trị số thập phân bằng nhau nhưng scale khác; `equals` trả `false` và `compareTo` trả 0.
8. **Cho rằng NaN của `Float` và NaN của `Double` bằng nhau theo `equals`.** Chúng là wrapper khác class nên `false`; ngay trong mỗi loại wrapper, quy tắc NaN/±0 cũng khác primitive.
9. **Tự sửa `equals` mà không cập nhật `hashCode`.** Điều này làm hỏng tính nhất quán khóa hash và có thể gây lỗi khó tái hiện.

## 10. Quy trình chọn phép so sánh

| Mục đích | Cách phù hợp | Chú ý |
| --- | --- | --- |
| Cùng kiểu wrapper và cùng giá trị theo wrapper | `Objects.equals(a, b)` hoặc `a.equals(b)` khi a không null | Khác kiểu wrapper vẫn `false` |
| Hai primitive cần numeric equality | `==` sau numeric promotion | NaN và signed zero có quy tắc đặc biệt |
| Hai wrapper nguyên nhỏ biết chắc miền `long` | So sánh `longValue()` sau khi xác minh kiểu và miền | Không dùng cho `BigInteger` quá lớn hoặc số thập phân |
| Số nguyên lớn chính xác | `BigInteger.equals`/`compareTo` | Giữ dữ liệu gốc chính xác |
| Số thập phân chính xác | `BigDecimal.compareTo == 0` nếu không quan tâm scale | Xác định hợp đồng scale và key |
| Sắp xếp số thực cùng loại | `Double.compare` / `Float.compare` | NaN và ±0 được xếp theo quy ước Java |
| Map/set cần đồng nhất ID | Chuẩn hóa kiểu khóa ở biên dữ liệu | Bảo đảm `equals` và `hashCode` cùng chính sách |

**Câu hỏi tự luyện:**

- `Integer.valueOf(8).equals(Long.valueOf(8L))` trả gì? Thế `8 == 8L`?
- Nếu `Number n = Integer.valueOf(8)`, `n.equals(Long.valueOf(8L))` có khác không?
- Vì sao một `HashSet<Number>` có thể chứa cả `Integer(8)` và `Long(8)`?
- Điều gì sai khi so sánh hai `long` khoảng `2^53` bằng cách ép cả hai sang `double`?
- `new BigDecimal("8.0").equals(new BigDecimal("8.00"))` và `compareTo` có cùng kết quả không?

**Đáp án:** (1) `false` và `true`. (2) Vẫn `false` vì implementation `Integer.equals` được chạy. (3) Chúng là hai phần tử không bằng nhau theo wrapper `equals`. (4) Phép ép có thể làm mất bit độ chính xác và gộp hai số khác nhau. (5) `equals` là `false`, còn `compareTo` bằng 0.

## Tài liệu tham khảo

- [Java SE 21 — Integer.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html#equals(java.lang.Object)).
- [Java SE 21 — Long.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html#equals(java.lang.Object)).
- [Java SE 21 — Number](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Number.html).
- [Java SE 21 — Objects.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)).
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).
- [Java Language Specification `15.21 — Equality Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.21).
