# `BigInteger.compareTo`, `equals`, `signum`, `abs` và `negate` trong Java

## 1. Mục tiêu và bối cảnh

`java.math.BigInteger` biểu diễn số nguyên có dấu với độ chính xác tùy ý (*arbitrary precision*). Giá trị không bị giới hạn trong 32 bit của `int` hoặc 64 bit của `long`; giới hạn thực tế là bộ nhớ, tài nguyên tính toán và giới hạn triển khai thư viện. Đây là một **kiểu đối tượng bất biến**, nên các phép tính không sửa đối tượng nguồn.

Năm phương thức trong bài trả lời năm câu hỏi cốt lõi:

| Phương thức | Câu hỏi | Kiểu kết quả |
| --- | --- | --- |
| `a.compareTo(b)` | `a` nhỏ hơn, bằng hay lớn hơn `b`? | `int` âm, `0`, hoặc dương |
| `a.equals(b)` | Hai đối tượng có cùng **giá trị `BigInteger`** không? | `boolean` |
| `a.signum()` | Giá trị là âm, bằng 0 hay dương? | `int` thuộc `-1`, `0`, `1` |
| `a.abs()` | Độ lớn không âm của `a` là gì? | `BigInteger` |
| `a.negate()` | Số đối của `a` là gì? | `BigInteger` |

Ví dụ ngắn, đặt trong một phương thức Java với `import java.math.BigInteger`:

```java
BigInteger a = new BigInteger("-123456789012345678901234567890");
BigInteger b = BigInteger.valueOf(42);

System.out.println(a.compareTo(b)); // -1: a nhỏ hơn b
System.out.println(a.signum());      // -1: a âm
System.out.println(a.abs());         // 123456789012345678901234567890
System.out.println(a.negate());      // 123456789012345678901234567890
System.out.println(a);               // Vẫn là số âm ban đầu
```

Cần phân biệt ba khái niệm: **thứ tự số học**, **bằng nhau về giá trị**, và **cùng tham chiếu đối tượng**. Trong phần lớn code nghiệp vụ, `compareTo`, `equals` và `signum` trả lời câu hỏi đúng; `==` không thay chúng được.

## 2. `compareTo(BigInteger)`: so thứ tự chính xác cả khi số rất lớn

Chữ ký API:

```java
public int compareTo(BigInteger val)
```

Kết quả mang **dấu** của quan hệ thứ tự:

\[
a.\mathrm{compareTo}(b)
\begin{cases}
< 0 & \text{khi } a < b,\\
= 0 & \text{khi } a = b,\\
> 0 & \text{khi } a > b.
\end{cases}
\]

Các ví dụ:

```java
BigInteger small = BigInteger.valueOf(-5);
BigInteger zero = BigInteger.ZERO;
BigInteger large = new BigInteger("99999999999999999999999999");

System.out.println(small.compareTo(zero) < 0); // true
System.out.println(large.compareTo(zero) > 0); // true
System.out.println(zero.compareTo(BigInteger.ZERO) == 0); // true
```

**Đừng dựa vào chính xác `-1` hoặc `1` như một hợp đồng tổng quát của `Comparable`.** Hợp đồng yêu cầu kết quả âm/0/dương; dùng `< 0`, `== 0`, `> 0`.

`compareTo` làm việc trực tiếp với `BigInteger`, không phải chuyển giá trị sang `int`, `long` hoặc `double`:

```java
BigInteger left = new BigInteger("9007199254740993");
BigInteger right = new BigInteger("9007199254740992");

System.out.println(left.compareTo(right) > 0); // true
```

Nếu chuyển cả hai sang `double`, các giá trị trên có thể cùng làm tròn thành một số, phá hỏng phép so sánh. `compareTo` giữ nguyên thứ tự toán học trên mọi giá trị `BigInteger` hợp lệ.

### So sánh chéo dấu và hai số âm

- Mọi số âm nhỏ hơn số 0, và số 0 nhỏ hơn mọi số dương.
- Với hai số âm, số có **giá trị tuyệt đối lớn hơn** thì lại **nhỏ hơn** theo thứ tự thông thường.

Ví dụ:

```java
BigInteger a = BigInteger.valueOf(-100);
BigInteger b = BigInteger.valueOf(-2);

System.out.println(a.compareTo(b) < 0); // true
System.out.println(a.abs().compareTo(b.abs()) > 0); // true
```

`-100 < -2` nhưng `|-100| > |-2|`.

### Không dùng phép trừ rồi ép về `int` để làm comparator

Sai lầm thường gặp:

```java
// Không dùng trong Comparator<BigInteger>:
int compareWrong(BigInteger a, BigInteger b) {
    return a.subtract(b).intValue();
}
```

Hiệu có thể lớn hơn miền `int`, khiến `intValue()` bỏ bit cao. Hai số khác nhau có thể tạo kết quả 0 hoặc sai dấu, phá vỡ thứ tự.

Cách đúng:

```java
int compareCorrect(BigInteger a, BigInteger b) {
    return a.compareTo(b);
}
```

Đây là phương thức minh họa trong một class Java; không phải hai chương trình độc lập. Trong thực tế có thể dùng trực tiếp `Comparator.naturalOrder()` hoặc `BigInteger::compareTo`.

### `min` và `max`

Hai tiện ích liên quan:

```java
BigInteger a = BigInteger.valueOf(-3);
BigInteger b = BigInteger.valueOf(2);

System.out.println(a.min(b)); // -3
System.out.println(a.max(b)); // 2
```

`min`/`max` lựa chọn giá trị theo thứ tự mà `compareTo` xác định. Không dùng chúng khi cần so sánh **độ lớn tuyệt đối**; lúc đó phải xét `abs()`.

## 3. `equals(Object)`: so giá trị, không so địa chỉ đối tượng

Chữ ký:

```java
public boolean equals(Object x)
```

`BigInteger.equals` trả `true` khi đối số là một `BigInteger` biểu diễn cùng số nguyên. Nó **không** quan tâm cách giá trị được tạo ra:

```java
BigInteger a = new BigInteger("42");
BigInteger b = BigInteger.valueOf(42);
BigInteger c = new BigInteger("0042");

System.out.println(a.equals(b)); // true
System.out.println(a.equals(c)); // true
```

Các chuỗi `"42"` và `"0042"` là cách viết khác nhau của cùng số nguyên 42, nên các đối tượng có cùng giá trị. `BigInteger` không lưu “số chữ số 0 ở đầu” như một thuộc tính số học có nghĩa.

### `==` chỉ so tham chiếu

```java
BigInteger a = new BigInteger("42");
BigInteger b = new BigInteger("42");

System.out.println(a.equals(b)); // true
System.out.println(a == b);      // false: ở đây tạo hai đối tượng riêng
```

Lời gọi `new BigInteger(String)` tạo đối tượng mới cho hai biến trong ví dụ, nên so tham chiếu nhận `false`. Nhưng **không suy ngược** rằng cùng giá trị luôn có tham chiếu khác nhau: các hằng và `valueOf` có thể tái sử dụng đối tượng.

```java
BigInteger x = BigInteger.valueOf(10);
BigInteger y = BigInteger.TEN;

System.out.println(x.equals(y)); // true
// Không dùng x == y làm quy tắc bằng nhau của số.
```

`BigInteger.valueOf` có thể cache các giá trị thường dùng. Đây là chi tiết hiệu năng/identity, không thay hợp đồng `equals`. Không dùng `System.identityHashCode` làm ID toán học.

### So sánh khác kiểu

```java
System.out.println(BigInteger.valueOf(42).equals(Long.valueOf(42L)));
// false
```

`BigInteger` và `Long` khác lớp, dù cùng biểu diễn số toán học 42. Nếu cần so sánh số nguyên dạng `long` với `BigInteger`, chuyển `long` thành `BigInteger` **mà không mất thông tin**:

```java
long input = 42L;
BigInteger value = new BigInteger("42");

boolean equal = value.equals(BigInteger.valueOf(input)); // true
```

Không ép một `BigInteger` lớn xuống `long` hoặc sang `double` để so nếu chưa xác minh miền; mất chính xác có thể khiến hai số khác nhau thành bằng nhau.

### `equals` và `compareTo` nhất quán với nhau

Đối với hai đối tượng `BigInteger` không `null`:

\[
a.equals(b) \iff a.compareTo(b) == 0.
\]

Đây là hợp đồng quan trọng khi dùng trong collection. Trong khi `BigDecimal` có thể coi `"2.0"` và `"2.00"` bằng nhau về thứ tự nhưng khác nhau theo `equals` do scale, `BigInteger` **không có scale decimal**: thứ tự tự nhiên của nó nhất quán với `equals`.

Nếu cần giữ định dạng nguyên thủy (ví dụ `"0042"` khác `"42"` về mã hồ sơ), hãy giữ chuỗi nguồn hoặc một ID dạng chuỗi phù hợp; `BigInteger.equals` cố ý xem chúng là cùng số.

## 4. `signum()`: lấy dấu mà không cần so với 0 nhiều lần

Chữ ký:

```java
public int signum()
```

Kết quả **chỉ là** `-1`, `0` hoặc `1`:

| Giá trị `BigInteger` | `signum()` | Ý nghĩa |
| --- | ---: | --- |
| Âm, chẳng hạn `-9` | `-1` | Nhỏ hơn 0 |
| Bằng 0 | `0` | Không âm, không dương |
| Dương, chẳng hạn `42` | `1` | Lớn hơn 0 |

Ví dụ:

```java
System.out.println(BigInteger.valueOf(-9).signum()); // -1
System.out.println(BigInteger.ZERO.signum());        // 0
System.out.println(BigInteger.valueOf(42).signum()); // 1
```

Khác với `compareTo`, `signum` không cần một đối tượng thứ hai. Dùng khi bạn chỉ quan tâm dấu:

```java
static String describe(BigInteger value) {
    return switch (value.signum()) {
        case -1 -> "NEGATIVE";
        case  0 -> "ZERO";
        case  1 -> "POSITIVE";
        default -> throw new AssertionError("Unexpected sign");
    };
}
```

Đoạn trên là phương thức trong một class Java 17 và giả sử `value != null`. `switch` này hợp lệ với JDK 17; các nhánh bao hết miền giá trị được `signum()` cam kết.

### `signum` khác kiểm tra parity

`signum()` không cho biết số chẵn/lẻ. Số `-8` và `-7` đều có `signum() == -1`. Muốn kiểm tra bit, dùng các phép như `testBit(0)` sau khi xác nhận cách diễn giải số âm phù hợp, hoặc `remainder(BigInteger.TWO)` theo quy tắc số học cần thiết.

### `BigInteger` không có số âm 0

```java
BigInteger zero = new BigInteger("-0");

System.out.println(zero);          // 0
System.out.println(zero.signum()); // 0
```

Khác `double`, `BigInteger` không có hai giá trị số 0 với bit dấu khác nhau. Chuỗi `"-0"` khi parse vẫn biểu diễn số nguyên 0, `signum()` trả 0. Nếu cần ghi nhận người dùng đã gõ dấu `-`, phải giữ chuỗi ban đầu; đó là thông tin **biểu diễn**, không phải giá trị số nguyên.

## 5. `abs()`: lấy trị tuyệt đối không overflow ở biên `long`

Chữ ký:

```java
public BigInteger abs()
```

Định nghĩa:

\[
|n| =
\begin{cases}
-n & n < 0,\\
n  & n \ge 0.
\end{cases}
\]

Ví dụ:

```java
BigInteger negative = new BigInteger("-12345678901234567890");
BigInteger magnitude = negative.abs();

System.out.println(magnitude); // 12345678901234567890
System.out.println(negative);  // -12345678901234567890
```

`abs()` trả giá trị không âm, **không thay đổi** `negative`. Với 0, kết quả là 0. Với số dương, kết quả có cùng giá trị với đầu vào; thư viện có thể trả lại chính đối tượng hoặc một đối tượng khác tùy tối ưu, nhưng code không được dựa vào identity đó.

### Khác biệt nổi bật với `Math.abs(Long.MIN_VALUE)`

Kiểu `long` có miền từ `-2^63` đến `2^63 - 1`. Giá trị tuyệt đối của `Long.MIN_VALUE` là `2^63`, **không vừa miền số dương `long`**:

```java
System.out.println(Math.abs(Long.MIN_VALUE));
// -9223372036854775808
```

Theo quy tắc số nguyên Java, kết quả vẫn âm ở trường hợp biên này.

Nếu trước tiên chuyển nguyên giá trị `long` sang `BigInteger`, trị tuyệt đối được giữ chính xác:

```java
BigInteger exactMagnitude =
        BigInteger.valueOf(Long.MIN_VALUE).abs();

System.out.println(exactMagnitude); // 9223372036854775808
```

**Đúng thứ tự là chuyển rồi `abs`**, không phải `BigInteger.valueOf(Math.abs(Long.MIN_VALUE))`, bởi phép `Math.abs(long)` có thể đã cho kết quả âm không mong muốn trước khi BigInteger nhận được giá trị.

Tình huống thực tế gồm kiểm tra độ lệch giá trị rất lớn, khoảng cách giữa số nguyên và các thuật toán nhận dữ liệu gần cận 64 bit.

### `abs` khác `signum`

`abs()` trả **toàn bộ độ lớn** như một `BigInteger`, còn `signum()` chỉ trả dấu như một `int`. Đừng dùng `abs().equals(BigInteger.ONE)` để kiểm tra dấu dương vì điều đó chỉ đúng cho số `1`, không đúng cho mọi số dương.

## 6. `negate()`: tạo số đối và giữ nguyên đối tượng nguồn

Chữ ký:

```java
public BigInteger negate()
```

Định nghĩa:

\[
\operatorname{negate}(n)=-n.
\]

Ví dụ:

```java
BigInteger original = BigInteger.valueOf(17);
BigInteger opposite = original.negate();

System.out.println(opposite); // -17
System.out.println(original); // 17
```

`negate()` không sửa `original`. Để đổi trạng thái của biến, phải gán kết quả:

```java
BigInteger balance = BigInteger.valueOf(17);
balance = balance.negate();

System.out.println(balance); // -17
```

Một số đẳng thức đúng về giá trị:

\[
-(-n)=n,\qquad -0=0,\qquad |-n|=|n|.
\]

Kiểm tra:

```java
BigInteger n = new BigInteger("-12345678901234567890");

System.out.println(n.negate().negate().equals(n)); // true
System.out.println(BigInteger.ZERO.negate());      // 0
System.out.println(n.negate().abs().equals(n.abs())); // true
```

Không suy từ `n.negate().negate().equals(n)` rằng `n.negate().negate() == n`; phương thức là phép toán giá trị, không có hợp đồng giữ identity.

### `negate()` của `Long.MIN_VALUE` không bị tràn như `long`

```java
long x = Long.MIN_VALUE;
System.out.println(-x); // -9223372036854775808: overflow của long

BigInteger bi = BigInteger.valueOf(x);
System.out.println(bi.negate()); // 9223372036854775808
```

Khi cần số đối chính xác của một giá trị âm cực tiểu, hãy chuyển sang `BigInteger` **trước** phép đổi dấu.

### `abs()` có phải chỉ là `negate()` không?

Không:

- Với `n > 0`, `n.abs()` vẫn dương, còn `n.negate()` âm.
- Với `n < 0`, hai kết quả có cùng giá trị dương.
- Với `n == 0`, cả hai cùng cho 0.

`abs` là **lấy độ lớn**, còn `negate` là **đổi dấu**. Đây là hai biến đổi khác nhau, không thay thế nhau cho dữ liệu dương.

## 7. Tính bất biến: phải nhận giá trị trả về

`BigInteger` không có toán tử `++`, `--`, `+` hay toán tử một ngôi `-` giống primitive. Các phép toán của nó là phương thức:

```java
BigInteger n = BigInteger.TEN;

// n++;      // Không biên dịch: BigInteger không phải kiểu số primitive
// n = -n;   // Không biên dịch
n = n.add(BigInteger.ONE);
n = n.negate();

System.out.println(n); // -11
```

Nếu bỏ qua kết quả của `add`, `negate` hoặc `abs`, giá trị cũ **không thay đổi**:

```java
BigInteger n = BigInteger.valueOf(-5);
n.abs();
System.out.println(n); // -5

n = n.abs();
System.out.println(n); // 5
```

Đây là lý do các hàm giúp biến đổi dãy `BigInteger` thường trả về một `BigInteger` mới về **mặt giá trị**. “Bất biến” không hứa mọi phép gọi luôn cấp phát một đối tượng mới; nó chỉ bảo đảm không sửa dữ liệu bên trong đối tượng đã có.

## 8. Kết hợp năm phương thức trong các mẫu code thực tế

### 8.1. Kiểm tra miền giá trị

Nếu người dùng nhập một số nguyên lớn `quantity` và chỉ chấp nhận giá trị từ `0` đến `max`:

```java
static boolean inRange(BigInteger quantity, BigInteger max) {
    if (quantity == null || max == null) {
        return false;
    }
    return quantity.signum() >= 0 && quantity.compareTo(max) <= 0;
}
```

Ở đây `signum() >= 0` kiểm tra không âm; `compareTo(max) <= 0` kiểm tra cận trên. **Không** ép `quantity` sang `long` chỉ để kiểm tra, vì phép ép có thể mất dữ liệu.

### 8.2. Khoảng cách tuyệt đối giữa hai số nguyên

Khoảng cách một chiều giữa `a` và `b`:

\[
d = |a-b|.
\]

```java
static BigInteger distance(BigInteger a, BigInteger b) {
    return a.subtract(b).abs();
}
```

Ví dụ:

```java
BigInteger a = new BigInteger("100000000000000000000");
BigInteger b = new BigInteger("99999999999999999995");

System.out.println(distance(a, b)); // 5
```

Lưu ý đây là **giá trị tuyệt đối của hiệu**, không phải hiệu của hai giá trị tuyệt đối:

\[
|a-b|\ \text{thường khác}\ |a|-|b|.
\]

Với `a = -5` và `b = 3`, `|a-b| = 8`, còn `|a|-|b| = 2`.

### 8.3. Chuẩn hóa theo dấu trong thuật toán

Một thuật toán có thể cần tách dấu và độ lớn:

```java
BigInteger input = new BigInteger("-12345678901234567890");

int sign = input.signum();
BigInteger magnitude = input.abs();

System.out.println(sign);      // -1
System.out.println(magnitude); // 12345678901234567890
```

Nếu sau này dựng lại số:

```java
BigInteger restored =
        sign < 0 ? magnitude.negate() : magnitude;

System.out.println(restored.equals(input)); // true
```

Với số 0, `sign == 0` và `magnitude == 0` về **giá trị**, vì `BigInteger` không có âm 0. Mẫu code này hữu ích trong các phép xử lý dấu riêng, nhưng đừng viết lại thuật toán thư viện khi một phương thức sẵn có đã đáp ứng đầy đủ.

### 8.4. Sắp xếp tự nhiên

`BigInteger` triển khai `Comparable<BigInteger>`, nên dùng comparator tự nhiên:

```java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;

List<BigInteger> values = new ArrayList<>(
        List.of(
                BigInteger.TEN,
                BigInteger.valueOf(-3),
                BigInteger.ZERO,
                BigInteger.valueOf(2)
        )
);

values.sort(BigInteger::compareTo);
System.out.println(values); // [-3, 0, 2, 10]
```

Thứ tự trên là **thứ tự số học**: `-3 < 0 < 2 < 10`. Nếu yêu cầu sắp theo độ lớn tuyệt đối, phải chỉ rõ cách giải quyết hòa (chẳng hạn `-3` và `3` có độ lớn bằng nhau).

Ví dụ comparator độ lớn:

```java
values.sort((left, right) -> left.abs().compareTo(right.abs()));
```

Comparator này xem `-3` và `3` như cùng thứ tự (kết quả compare 0) dù `equals` của chúng là `false`. Nếu dùng nó với `TreeSet`/`TreeMap`, điều đó có thể gây **mất sự phân biệt các khóa khác giá trị**. Muốn vừa ưu tiên độ lớn vừa giữ thứ tự tổng quát phù hợp với `equals`, thêm tie-breaker:

```java
values.sort(
        (left, right) -> {
            int order = left.abs().compareTo(right.abs());
            return order != 0 ? order : left.compareTo(right);
        }
);
```

### 8.5. Phân nhánh theo dấu cho bài toán nghiệp vụ

```java
static String status(BigInteger balance) {
    return switch (balance.signum()) {
        case -1 -> "DEBT";
        case 0 -> "SETTLED";
        case 1 -> "CREDIT";
        default -> throw new AssertionError();
    };
}
```

Đây chỉ là ví dụ minh họa thuật toán: cách diễn giải số âm là nợ, số dương là dư có phải khớp hợp đồng dữ liệu thực tế. `signum()` không tự biết ý nghĩa tài chính hay nghiệp vụ.

## 9. `equals`, `hashCode` và collection

`BigInteger.equals` kiểm tra giá trị và `hashCode` tuân thủ hợp đồng tương ứng. Vì thế có thể dùng `BigInteger` làm khóa cho `HashMap`/`HashSet`:

```java
import java.math.BigInteger;
import java.util.HashSet;
import java.util.Set;

Set<BigInteger> identifiers = new HashSet<>();
identifiers.add(new BigInteger("1234567890123456789012345"));

boolean present = identifiers.contains(
        new BigInteger("1234567890123456789012345")
);

System.out.println(present); // true
```

Hai lời gọi constructor có thể tạo hai đối tượng khác nhau về tham chiếu nhưng `HashSet` so khớp **giá trị**.

`TreeSet<BigInteger>` sử dụng thứ tự tự nhiên qua `compareTo`; vì thứ tự đó nhất quán với `equals`, nó có hành vi nhận diện giá trị đúng như mong đợi.

Không dùng `IdentityHashMap<BigInteger, ...>` cho key là số nếu mục tiêu là bằng nhau theo **giá trị**: `IdentityHashMap` cố ý sử dụng tham chiếu, khiến dữ liệu có cùng số có thể bị coi là các khóa khác nhau.

### Dấu âm không ảnh hưởng định danh như chuỗi nguồn

`new BigInteger("-0")`, `BigInteger.ZERO`, `new BigInteger("000")` đều bằng nhau về giá trị. Nếu một mã định danh dạng chuỗi yêu cầu giữ số 0 đứng đầu, không nên chuyển nó thành `BigInteger` rồi kỳ vọng `equals` phân biệt được chuỗi nguồn.

## 10. Null và kiểu dữ liệu: các ngoại lệ cần biết

`BigInteger` là kiểu **tham chiếu**, nên biến có thể nhận `null`:

```java
BigInteger missing = null;
// missing.signum(); // NullPointerException
// missing.abs();    // NullPointerException
// missing.negate(); // NullPointerException
```

`null` không có giá trị số. Phải quyết định cách xử lý:

```java
static boolean isZeroIfPresent(BigInteger value) {
    return value != null && value.signum() == 0;
}
```

`Objects.equals` hỗ trợ so đối tượng nullable:

```java
boolean same = java.util.Objects.equals(
        (BigInteger) null, (BigInteger) null
); // true vì cả hai tham chiếu đều null
```

Nhưng `Objects.equals(null, null)` không chứng minh tồn tại hai số 0. Nếu nghiệp vụ yêu cầu có hai số hợp lệ, hãy kiểm tra không `null` trước.

Các phương thức có đối số bắt buộc là `BigInteger` như `compareTo(null)` không có một giá trị số để so; trong Java 17, việc này gây `NullPointerException`. Nên validate ở ranh giới API:

```java
static int compareRequired(BigInteger a, BigInteger b) {
    java.util.Objects.requireNonNull(a, "a");
    java.util.Objects.requireNonNull(b, "b");
    return a.compareTo(b);
}
```

`equals(null)` thì trả `false` nếu receiver là `BigInteger` không `null`, theo hợp đồng `equals(Object)`. **Đừng đánh đồng** `equals(null)` với `compareTo(null)`.

### BigInteger không phải primitive và không auto-unbox

Không thể viết:

```java
BigInteger n = BigInteger.TEN;
// if (n > 0) {} // Không biên dịch
// int x = n;    // Không biên dịch
```

Muốn so với 0, dùng `n.signum() > 0` hoặc `n.compareTo(BigInteger.ZERO) > 0`. Muốn trích `long`, dùng `longValueExact()` nếu bắt buộc chính xác và vừa miền; không dùng `longValue()` tùy tiện với số cực lớn.

## 11. Ví dụ Java 17 hoàn chỉnh

Lưu dưới tên `BigIntegerComparisonDemo.java`:

```java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;

public class BigIntegerComparisonDemo {

    static BigInteger distance(BigInteger left, BigInteger right) {
        return left.subtract(right).abs();
    }

    static String describe(BigInteger value) {
        return switch (value.signum()) {
            case -1 -> "NEGATIVE";
            case 0 -> "ZERO";
            case 1 -> "POSITIVE";
            default -> throw new AssertionError();
        };
    }

    public static void main(String[] args) {
        BigInteger negative =
                new BigInteger("-123456789012345678901234567890");
        BigInteger positive = BigInteger.valueOf(42);

        System.out.println("compare negative to 42: "
                + negative.compareTo(positive));
        System.out.println("compare 42 to negative: "
                + positive.compareTo(negative));

        System.out.println("equals same value: "
                + new BigInteger("42").equals(positive));
        System.out.println("equals different type: "
                + positive.equals(Long.valueOf(42L)));

        System.out.println("negative signum: " + negative.signum());
        System.out.println("zero signum: " + BigInteger.ZERO.signum());
        System.out.println("positive signum: " + positive.signum());

        System.out.println("absolute negative: " + negative.abs());
        System.out.println("negated negative: " + negative.negate());
        System.out.println("original unchanged: " + negative);
        System.out.println("double negation equals: "
                + negative.negate().negate().equals(negative));

        System.out.println("abs min long: "
                + BigInteger.valueOf(Long.MIN_VALUE).abs());
        System.out.println("Math.abs min long: "
                + Math.abs(Long.MIN_VALUE));

        System.out.println("negative zero signum: "
                + new BigInteger("-0").signum());
        System.out.println("describe zero: "
                + describe(BigInteger.ZERO));

        System.out.println("distance: " + distance(
                new BigInteger("100000000000000000000"),
                new BigInteger("99999999999999999995")));

        List<BigInteger> values = new ArrayList<>(List.of(
                BigInteger.TEN,
                BigInteger.valueOf(-3),
                BigInteger.ZERO,
                BigInteger.valueOf(2)
        ));
        values.sort(BigInteger::compareTo);
        System.out.println("sorted: " + values);
    }
}
```

Chạy với JDK 17 hoặc mới hơn:

```bash
javac BigIntegerComparisonDemo.java
java BigIntegerComparisonDemo
```

Đầu ra:

```text
compare negative to 42: -1
compare 42 to negative: 1
equals same value: true
equals different type: false
negative signum: -1
zero signum: 0
positive signum: 1
absolute negative: 123456789012345678901234567890
negated negative: 123456789012345678901234567890
original unchanged: -123456789012345678901234567890
double negation equals: true
abs min long: 9223372036854775808
Math.abs min long: -9223372036854775808
negative zero signum: 0
describe zero: ZERO
distance: 5
sorted: [-3, 0, 2, 10]
```

Các giá trị trên làm rõ việc `compareTo` chỉ cần so dấu, `equals` so giá trị cùng kiểu, `signum` phân nhánh theo dấu, `abs` tính độ lớn chính xác vượt giới hạn `long`, còn `negate` trả số đối **mà không sửa đầu vào**.

## 12. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| `a == b` cho hai `BigInteger` | So tham chiếu; cùng giá trị vẫn có thể `false` | `a.equals(b)` |
| `compareTo(b) == 1` để kiểm tra lớn hơn | Dựa vào trị số thay vì dấu do hợp đồng `Comparable` | `compareTo(b) > 0` |
| `a.subtract(b).intValue()` làm comparator | Mất bit, sai dấu hoặc trả 0 ngoài ý muốn | `a.compareTo(b)` |
| Ép `BigInteger` sang `double` để so | Có thể mất chữ số của số nguyên lớn | So trực tiếp bằng `compareTo` |
| `Math.abs(Long.MIN_VALUE)` rồi gọi `valueOf` | Trị tuyệt đối kiểu `long` đã overflow | `BigInteger.valueOf(Long.MIN_VALUE).abs()` |
| `-someLong` rồi chuyển BigInteger | Số đối có thể overflow tại `Long.MIN_VALUE` | `BigInteger.valueOf(someLong).negate()` |
| `n.abs();` không gán kết quả | `BigInteger` bất biến; `n` không đổi | `n = n.abs();` |
| `n.negate();` không gán kết quả | Không thay đổi số đang lưu | `n = n.negate();` |
| Dùng `negate()` thay `abs()` cho số dương | Đổi thành số âm thay vì giữ không âm | Dùng đúng hàm theo mục tiêu |
| `value.signum()` khi `value == null` | `NullPointerException` | Kiểm tra `null` |
| Dùng `equals(null)` như `compareTo(null)` | Hai API có hành vi khác | `equals(null)` trả `false`; so thứ tự cần giá trị |
| Coi `BigInteger("-0")` khác `ZERO` | BigInteger không có âm 0 | Cả hai là số nguyên 0 |
| Tạo `TreeSet` với comparator chỉ dựa vào `abs` khi cần phân biệt `-a` và `a` | Comparator có thể trả 0 cho hai giá trị khác nhau | Thêm tie-breaker `compareTo` |
| Chọn `BigInteger` làm ID nhưng cần giữ số 0 ở đầu | Chuỗi `"0042"` và `"42"` thành cùng giá trị số | Lưu ID dưới dạng chuỗi nếu cú pháp có ý nghĩa |
| Coi `abs()` hoặc `negate()` luôn cấp phát instance mới | Identity không phải hợp đồng của phép biến đổi giá trị | Không so tham chiếu; dùng `equals` |
| Gọi `longValue()` để kiểm tra miền `long` | Có thể mất dữ liệu mà không báo lỗi | Dùng `longValueExact()` khi cần |

### Quy tắc chọn phương thức nhanh

- **Xếp thứ tự hai số:** `a.compareTo(b)`.
- **Kiểm tra bằng giá trị cùng kiểu:** `a.equals(b)`.
- **Kiểm tra âm, 0, dương:** `a.signum()`.
- **Lấy độ lớn không âm:** `a.abs()`.
- **Đổi dấu:** `a.negate()`.
- **Lấy độ lớn chênh lệch hai số:** `a.subtract(b).abs()`.

## 13. Bài tập có đáp án

**Bài 1.** Với `a = -5`, `b = -2`, `a.compareTo(b)` có dấu nào? Giá trị `a.abs().compareTo(b.abs())` có dấu nào?

**Đáp án:** `a.compareTo(b) < 0` vì `-5 < -2`. Trái lại `a.abs().compareTo(b.abs()) > 0` vì `5 > 2`. So thứ tự số khác so độ lớn.

**Bài 2.** Hai đối tượng được tạo bằng `new BigInteger("42")` riêng biệt có bằng nhau theo `equals` không? Cần dùng `==` không?

**Đáp án:** Có, `equals` là `true`; `==` giữa hai đối tượng vừa tạo riêng là `false`, và không phù hợp để kiểm tra cùng giá trị.

**Bài 3.** `BigInteger.ZERO.signum()` trả gì? `new BigInteger("-0").signum()` có khác không?

**Đáp án:** Cả hai trả `0`; `BigInteger` không có số 0 âm tách biệt.

**Bài 4.** Tại sao `BigInteger.valueOf(Long.MIN_VALUE).abs()` cho kết quả dương đúng, còn `Math.abs(Long.MIN_VALUE)` vẫn âm?

**Đáp án:** `long` không biểu diễn được số dương `2^63`, nên `Math.abs(long)` gặp cận biểu diễn. `BigInteger` không bị giới hạn ở 64 bit và giữ được `9223372036854775808`.

**Bài 5.** Nếu `n` là `BigInteger` âm, sau lệnh `n.negate();` mà không gán kết quả, `n` có đổi không?

**Đáp án:** Không. `BigInteger` bất biến; cần `n = n.negate()` để biến tham chiếu đến số đối.

**Bài 6.** `BigInteger.valueOf(42).equals(Long.valueOf(42L))` trả gì và vì sao?

**Đáp án:** `false`. `BigInteger.equals` yêu cầu đối tượng thuộc `BigInteger` và có cùng giá trị, không so chéo các lớp `Number` chỉ vì cùng giá trị toán học.

**Bài 7.** Viết biểu thức kiểm tra `BigInteger total` không âm, giả sử `total != null`.

**Đáp án:** `total.signum() >= 0` hoặc `total.compareTo(BigInteger.ZERO) >= 0`. Nếu đầu vào có thể `null`, kiểm tra `total != null` trước.

**Bài 8.** Vì sao không dùng `a.subtract(b).intValue()` làm hàm so thứ tự giữa hai số `BigInteger` rất lớn?

**Đáp án:** Phép trích `intValue()` có thể bỏ bit cao, làm dấu và độ lớn của hiệu bị sai; `compareTo` tính thứ tự chính xác trên toàn miền `BigInteger`.

**Bài 9.** Hai khóa `-7` và `7` sẽ ra sao trong `TreeSet<BigInteger>` nếu comparator chỉ là `(a,b) -> a.abs().compareTo(b.abs())`?

**Đáp án:** Comparator trả `0` cho hai khóa dù `equals` trả `false`. `TreeSet` có thể coi chúng là cùng phần tử theo comparator. Nếu cần giữ cả hai, thêm tie-breaker bằng `a.compareTo(b)` hoặc dùng thứ tự tự nhiên.

**Bài 10.** So sánh `n.abs()` và `n.negate()` với `n = 17`, `n = -17`, `n = 0`.

**Đáp án:** Với `17`, `abs = 17`, `negate = -17`; với `-17`, cả hai là `17`; với `0`, cả hai là `0`. Hai phương thức khác nhau về ý nghĩa dù đôi khi cùng kết quả.

**Ghi nhớ:** `compareTo` là thứ tự, `equals` là bằng nhau về giá trị, `signum` chỉ dấu, `abs` lấy độ lớn không âm, `negate` lấy số đối. Tất cả áp dụng trực tiếp cho `BigInteger` lớn mà không cần thu hẹp về primitive; hãy giữ tính bất biến, kiểm tra `null` và không dùng identity hay phép ép mất chính xác thay cho so sánh toán học.