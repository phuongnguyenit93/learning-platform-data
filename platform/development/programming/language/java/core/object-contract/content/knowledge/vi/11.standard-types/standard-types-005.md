# BigDecimal.equals() xét cả giá trị và scale

## Mục tiêu học tập

Trong Java, hai `BigDecimal` có thể biểu diễn **cùng giá trị số học** nhưng **không bằng nhau theo `equals(Object)`**. Nguyên nhân là `BigDecimal.equals()` xét **cả giá trị và `scale`**, trong khi `compareTo()` xác định thứ tự theo giá trị số học. Sự khác biệt này ảnh hưởng trực tiếp tới `hashCode()`, `HashSet`, `HashMap`, `TreeSet`, việc kiểm tra kết quả phép tính và thiết kế đối tượng chứa tiền hoặc số thập phân.

Sau bài này, bạn có thể giải thích và dự đoán chính xác kết quả của `equals`, `compareTo`, `hashCode`; chọn phép so sánh đúng mục đích; xử lý những thay đổi do `stripTrailingZeros()` và `setScale()`; kiểm tra trường hợp số không, mảng/collection chứa `BigDecimal`; và thiết kế khóa dùng quy tắc bằng nhau theo giá trị số nếu ứng dụng cần.

## 1. Một BigDecimal gồm unscaled value và scale

Một số thập phân `BigDecimal` được biểu diễn bằng một **số nguyên không chia tỷ lệ** (`unscaledValue`, kiểu `BigInteger`) và một **scale** (kiểu `int`). Giá trị số học của nó là:

```text
giá trị = unscaledValue × 10^(-scale)
```

Ví dụ:

| Biểu diễn | `unscaledValue()` | `scale()` | Giá trị số học |
| --- | ---: | ---: | ---: |
| `new BigDecimal("2")` | `2` | `0` | `2` |
| `new BigDecimal("2.0")` | `20` | `1` | `2` |
| `new BigDecimal("2.00")` | `200` | `2` | `2` |
| `new BigDecimal("0.00")` | `0` | `2` | `0` |
| `new BigDecimal("1E+3")` | `1` | `-3` | `1000` |

Vì vậy, **scale không chỉ nói về phần thập phân được hiển thị**: nó là một thành phần trong biểu diễn số. Scale **có thể âm**; ví dụ `1E+3` có `scale() == -3`. Hai `BigDecimal` khác scale có thể cùng giá trị số học.

Giá trị `2.0` và `2.00` thể hiện khác biệt rõ ràng:

```text
2.0  = 20  × 10^(-1)
2.00 = 200 × 10^(-2)

Giá trị số học giống nhau: 2
Biểu diễn (unscaled value, scale) khác nhau:
(20, 1) so với (200, 2)
```

Phân biệt **biểu diễn** và **giá trị số học** là chìa khóa của bài học.

## 2. `equals()` so sánh biểu diễn; `compareTo()` so sánh giá trị số

Theo hợp đồng của `BigDecimal`:

- `a.equals(b)` trả về `true` khi `b` là `BigDecimal` có **cùng giá trị số học và cùng scale**. Ví dụ `2.0` bằng `2.0`, nhưng **không bằng** `2.00` theo `equals`.
- `a.compareTo(b) == 0` xác nhận **hai giá trị số học bằng nhau**, kể cả khác scale. `2.0` và `2.00` có `compareTo` bằng `0`.
- `compareTo` trả số âm, `0`, hoặc số dương tùy giá trị `a` nhỏ hơn, bằng hoặc lớn hơn `b`. Không nên dựa vào độ lớn chính xác của số âm/dương trả về.
- `a.equals(null)` trả `false`. `a.compareTo(null)` ném `NullPointerException`; đối số cần là `BigDecimal` không `null`.
- `equals` chỉ công nhận đối tượng `BigDecimal` thích hợp; không coi `String "2.0"` hoặc `Integer 2` là bằng một `BigDecimal`.

Đặt cạnh nhau:

| So sánh | Kết quả | Giải thích |
| --- | --- | --- |
| `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` | `false` | Scale lần lượt `1` và `2` |
| `new BigDecimal("2.0").compareTo(new BigDecimal("2.00")) == 0` | `true` | Cùng giá trị số `2` |
| `new BigDecimal("2").equals(new BigDecimal("2.0"))` | `false` | Scale `0` so với `1` |
| `new BigDecimal("0.0").equals(new BigDecimal("0.00"))` | `false` | Hai số không nhưng scale khác |
| `new BigDecimal("0.00").compareTo(BigDecimal.ZERO) == 0` | `true` | Hai giá trị đều là số không |
| `new BigDecimal("2.0").equals(new BigDecimal("2.0"))` | `true` | Cùng biểu diễn theo quy tắc `equals` |

Đây là trường hợp đặc biệt được tài liệu Java mô tả là **natural ordering không nhất quán với equals**: hai giá trị có `compareTo == 0` chưa chắc có `equals == true`. Không tự động thay thế một phương thức bằng phương thức còn lại.

## 3. Ví dụ chạy được: nhìn thấy đầy đủ hai quan hệ bằng nhau

Lưu chương trình Java 17+ vào **`BigDecimalEqualityDemo.java`**:

```java
import java.math.BigDecimal;

public class BigDecimalEqualityDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        BigDecimal c = new BigDecimal("2.0");

        System.out.println("a: " + a.toPlainString());
        System.out.println("b: " + b.toPlainString());
        System.out.println("a scale: " + a.scale());
        System.out.println("b scale: " + b.scale());
        System.out.println("a unscaled: " + a.unscaledValue());
        System.out.println("b unscaled: " + b.unscaledValue());

        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a.compareTo(b) == 0: "
                + (a.compareTo(b) == 0));
        System.out.println("a.equals(c): " + a.equals(c));

        BigDecimal zeroOne = new BigDecimal("0.0");
        BigDecimal zeroTwo = new BigDecimal("0.00");
        System.out.println("zeroOne.equals(zeroTwo): "
                + zeroOne.equals(zeroTwo));
        System.out.println("zeroOne.compareTo(zeroTwo) == 0: "
                + (zeroOne.compareTo(zeroTwo) == 0));

        BigDecimal difference = b.subtract(a);
        System.out.println("difference: "
                + difference.toPlainString());
        System.out.println("difference.equals(ZERO): "
                + difference.equals(BigDecimal.ZERO));
        System.out.println("difference.compareTo(ZERO) == 0: "
                + (difference.compareTo(BigDecimal.ZERO) == 0));
    }
}
```

Biên dịch và chạy:

```bash
javac BigDecimalEqualityDemo.java
java BigDecimalEqualityDemo
```

**Đầu ra chính xác:**

```text
a: 2.0
b: 2.00
a scale: 1
b scale: 2
a unscaled: 20
b unscaled: 200
a.equals(b): false
a.compareTo(b) == 0: true
a.equals(c): true
zeroOne.equals(zeroTwo): false
zeroOne.compareTo(zeroTwo) == 0: true
difference: 0.00
difference.equals(ZERO): false
difference.compareTo(ZERO) == 0: true
```

Phân tích hai chi tiết quan trọng:

1. `b.subtract(a)` là phép trừ `2.00 - 2.0`. Kết quả có **giá trị số học 0**, nhưng scale là `2` nên `toPlainString()` hiển thị `0.00`. `BigDecimal.ZERO` có scale `0`; bởi thế `difference.equals(BigDecimal.ZERO)` trả `false`.
2. Muốn hỏi “kết quả có bằng **số không** không?”, dùng `difference.signum() == 0` hoặc `difference.compareTo(BigDecimal.ZERO) == 0`. `signum()` trả `-1`, `0` hoặc `1` theo dấu số học, không phụ thuộc scale.

**Không hiểu sai:** `equals` của `BigDecimal` không phải “lỗi”. Nó có một **hợp đồng cụ thể**, trong đó scale có ý nghĩa. Lỗi xuất hiện khi ứng dụng cần bằng nhau theo giá trị số nhưng lại dùng `equals` mà không nhận ra sự khác biệt.

## 4. Vì sao `hashCode()` cũng phân biệt scale?

`BigDecimal.hashCode()` nhất quán với `BigDecimal.equals()`: nếu hai `BigDecimal` bằng nhau theo `equals` thì hash của chúng phải bằng nhau. Vì `equals` coi `2.0` và `2.00` là **khác nhau**, mã băm của chúng **được phép** khác nhau; triển khai Java tạo ra hash khác nhau cho cặp này.

Có thể nghĩ theo mô hình:

```text
equals(BigDecimal):
  tham gia so sánh: giá trị số học + scale

hashCode(BigDecimal):
  phải tương thích với mọi thành phần quyết định equals
```

**Không suy luận chiều ngược:** `a.hashCode() == b.hashCode()` không chứng minh `a.equals(b)`. Va chạm mã băm là hợp lệ.

Sự khác biệt này tác động đến các cấu trúc như `HashSet` hoặc `HashMap` vì chúng dùng cả `hashCode` và `equals` khi xác định phần tử/khóa tương ứng. Nếu đặt `new BigDecimal("2.0")` làm khóa rồi tra cứu bằng `new BigDecimal("2.00")`, chúng không phải cùng một khóa theo ngữ nghĩa của `HashMap`.

### 4.1. `HashSet` và `TreeSet` không đưa ra cùng một kết quả

`HashSet` dựa vào `equals/hashCode`; `TreeSet` với thứ tự tự nhiên dựa vào `compareTo` để nhận biết hai phần tử tương đương trong quá trình sắp xếp/tìm kiếm.

Lưu vào **`BigDecimalCollectionsDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class BigDecimalCollectionsDemo {
    public static void main(String[] args) {
        BigDecimal twoOneDecimal = new BigDecimal("2.0");
        BigDecimal twoTwoDecimals = new BigDecimal("2.00");
        BigDecimal twoThreeDecimals = new BigDecimal("2.000");

        Set<BigDecimal> hashSet = new HashSet<>();
        hashSet.add(twoOneDecimal);
        hashSet.add(twoTwoDecimals);

        Set<BigDecimal> treeSet = new TreeSet<>();
        treeSet.add(twoOneDecimal);
        treeSet.add(twoTwoDecimals);

        System.out.println("hashSet size: " + hashSet.size());
        System.out.println("treeSet size: " + treeSet.size());
        System.out.println("hashSet contains 2.000: "
                + hashSet.contains(twoThreeDecimals));
        System.out.println("treeSet contains 2.000: "
                + treeSet.contains(twoThreeDecimals));
        System.out.println("2.0 equals 2.00: "
                + twoOneDecimal.equals(twoTwoDecimals));
        System.out.println("2.0 compares as 2.00: "
                + (twoOneDecimal.compareTo(twoTwoDecimals) == 0));
    }
}
```

Chạy:

```bash
javac BigDecimalCollectionsDemo.java
java BigDecimalCollectionsDemo
```

**Đầu ra chính xác:**

```text
hashSet size: 2
treeSet size: 1
hashSet contains 2.000: false
treeSet contains 2.000: true
2.0 equals 2.00: false
2.0 compares as 2.00: true
```

**Vì sao?**

- `hashSet.add(2.0)` và `hashSet.add(2.00)` giữ hai phần tử khác nhau: `equals` trả `false`.
- `treeSet.add(2.0)` rồi `treeSet.add(2.00)` chỉ có một phần tử theo thứ tự tự nhiên: `compareTo` trả `0`.
- `treeSet.contains(2.000)` cũng trả `true` vì giá trị số tương đương theo bộ so sánh của cây, dù `2.000` không `equals` với phần tử `2.0` bên trong.

Điều này là một đặc điểm đã được ghi nhận của `BigDecimal`. Theo hợp đồng chung của `Set`, việc bộ so sánh không nhất quán với `equals` có thể tạo ra hành vi gây bất ngờ. `TreeMap` với thứ tự tự nhiên có sự khác biệt tương tự so với `HashMap`.

**Quy tắc sử dụng:** Trước khi chọn `HashSet`, `TreeSet`, `HashMap` hoặc `TreeMap`, hãy quyết định ứng dụng coi “cùng số nhưng khác scale” là **một** hay **hai** giá trị khác nhau. Đừng đổi loại collection rồi giả định các khóa sẽ được xử lý y hệt.

## 5. Khi nào cần `equals`, khi nào cần `compareTo`?

Chọn theo **ý nghĩa cần kiểm tra**:

| Nhu cầu | Cách làm phù hợp | Lý do |
| --- | --- | --- |
| Hai `BigDecimal` có cùng biểu diễn số và scale? | `a.equals(b)` | Scale là một phần điều kiện |
| Hai `BigDecimal` bằng nhau về giá trị số? | `a.compareTo(b) == 0` | Bỏ qua khác biệt scale |
| Kiểm tra giá trị số bằng 0? | `a.signum() == 0` | Không bị ảnh hưởng bởi `0`, `0.0`, `0.00` |
| Kiểm tra số lớn hơn ngưỡng? | `a.compareTo(threshold) > 0` | So thứ tự số |
| Kiểm tra số nhỏ hơn hoặc bằng ngưỡng? | `a.compareTo(threshold) <= 0` | So thứ tự số |
| Tra cứu khóa `HashMap<BigDecimal, ...>`? | Chuẩn hóa khóa từ đầu hoặc thống nhất scale | `HashMap` dùng `equals/hashCode` |
| So sánh một giá trị chỉ để hiển thị bao nhiêu chữ số thập phân? | Đọc `scale()`, kết hợp định dạng phù hợp | Bằng nhau về số không nói lên yêu cầu hiển thị |

Ví dụ:

```java
BigDecimal actual = new BigDecimal("100.00");
BigDecimal expected = new BigDecimal("100.0");

// Kiểm tra giá trị toán học:
boolean sameAmount = actual.compareTo(expected) == 0; // true

// Kiểm tra biểu diễn gồm cả scale:
boolean sameRepresentation = actual.equals(expected); // false
```

Đây là **đoạn minh họa** để nhúng trong một phương thức hoặc một chương trình có `import java.math.BigDecimal;`.

**Lưu ý `null`:** `actual.compareTo(expected)` đòi cả hai tham chiếu hợp lệ. Nếu dữ liệu có thể `null`, hãy quyết định rõ `null` có ý nghĩa gì trong miền nghiệp vụ, rồi kiểm tra trước. Không mặc định `null` là số không.

## 6. `stripTrailingZeros()`: chuẩn hóa để so sánh theo giá trị

`stripTrailingZeros()` trả về một `BigDecimal` có cùng giá trị số học sau khi loại các chữ số `0` không cần thiết ở cuối phần unscaled decimal representation. Ví dụ:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.stripTrailingZeros()); // 2
System.out.println(b.stripTrailingZeros()); // 2
```

Hai kết quả đã chuẩn hóa có cùng biểu diễn theo `equals`. Trong nhiều trường hợp, có thể chuẩn hóa ngay tại biên hệ thống nếu cần **một đại diện duy nhất cho mỗi giá trị số học**.

Tuy nhiên, có **hai điều quan trọng**:

1. Chuẩn hóa có thể đổi `scale`, kể cả về **số âm**. `new BigDecimal("1000.00").stripTrailingZeros()` có thể được in là `1E+3` với scale `-3`, thay vì `1000.00`. Khi cần chuỗi thập phân không dùng lũy thừa, dùng `toPlainString()`; khi cần số chữ số cố định, chọn quy tắc `setScale`/định dạng riêng.
2. `new BigDecimal("0.000").stripTrailingZeros()` chuẩn hóa thành `BigDecimal.ZERO` (scale `0`). Điều này hữu ích khi chuẩn hóa số không nhưng có thể bỏ thông tin về độ chính xác/scale ban đầu.

Vì thế, **không sử dụng `stripTrailingZeros` nếu scale gốc mang ý nghĩa cần giữ**, chẳng hạn số chữ số thập phân được người dùng nhập hoặc quy định hiển thị trong một giao thức dữ liệu.

### 6.1. Ví dụ chuẩn hóa có thể chạy

**Tệp `BigDecimalNormalizationDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalNormalizationDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        BigDecimal normalizedA = a.stripTrailingZeros();
        BigDecimal normalizedB = b.stripTrailingZeros();

        System.out.println("normalized equal: "
                + normalizedA.equals(normalizedB));
        System.out.println("normalized a: " + normalizedA.toString());
        System.out.println("normalized a scale: "
                + normalizedA.scale());

        BigDecimal large =
                new BigDecimal("1000.00").stripTrailingZeros();
        System.out.println("large normalized: " + large.toString());
        System.out.println("large normalized scale: "
                + large.scale());
        System.out.println("large plain: " + large.toPlainString());

        BigDecimal zero =
                new BigDecimal("0.000").stripTrailingZeros();
        System.out.println("normalized zero scale: " + zero.scale());

        BigDecimal aligned =
                new BigDecimal("2.0").setScale(2);
        System.out.println("aligned: " + aligned.toPlainString());
        System.out.println("aligned equals b: " + aligned.equals(b));

        BigDecimal rounded =
                new BigDecimal("2.005").setScale(
                        2, RoundingMode.HALF_UP);
        System.out.println("rounded: " + rounded.toPlainString());
    }
}
```

```bash
javac BigDecimalNormalizationDemo.java
java BigDecimalNormalizationDemo
```

**Đầu ra chính xác:**

```text
normalized equal: true
normalized a: 2
normalized a scale: 0
large normalized: 1E+3
large normalized scale: -3
large plain: 1000
normalized zero scale: 0
aligned: 2.00
aligned equals b: true
rounded: 2.01
```

`stripTrailingZeros()` giữ **giá trị số** nhưng có thể đổi biểu diễn. `setScale(2)` của `2.0` thêm một chữ số 0 thập phân mà không đổi giá trị, nên `2.00.equals(2.00)` là `true`. Ngược lại, đưa `2.005` về scale `2` buộc làm tròn: ví dụ dùng `RoundingMode.HALF_UP` để có `2.01`.

**Cẩn thận với `setScale` không có chế độ làm tròn:** `new BigDecimal("2.005").setScale(2)` gây `ArithmeticException` vì cần loại bỏ phần giá trị khác 0 mà không được làm tròn. Đây là đặc điểm nhằm tránh âm thầm mất dữ liệu. Chỉ đặt scale mục tiêu sau khi thống nhất chính sách làm tròn theo nghiệp vụ.

## 7. Đối tượng chứa BigDecimal: chọn chính sách equals/hashCode nhất quán

Vấn đề không chỉ xuất hiện khi so trực tiếp hai `BigDecimal`. Nếu một lớp nghiệp vụ có trường `BigDecimal amount`, bạn phải quyết định **scale có tham gia định nghĩa bằng nhau của lớp chứa hay không**.

### Phương án A: scale có ý nghĩa

Nếu muốn phân biệt `2.0` và `2.00` (ví dụ giữ biểu diễn gốc là một phần dữ liệu), có thể để `equals` của lớp chứa dùng `amount.equals(other.amount)`, còn `hashCode` dùng `amount.hashCode()` hoặc `Objects.hash(...)` với trường tương ứng. Khi đó các khóa ở hai scale khác nhau sẽ được coi là khác nhau.

### Phương án B: chỉ giá trị số học có ý nghĩa

Nếu muốn `2.0` và `2.00` là **một khóa**, `equals` của lớp chứa có thể dùng `compareTo() == 0`. Nhưng **hashCode phải chuẩn hóa cùng quan hệ đó**.

Cách sai điển hình:

```java
// Sai nếu equals dùng compareTo == 0:
@Override
public int hashCode() {
    return amount.hashCode();
}
```

Vì `amount.hashCode()` vẫn xét scale, hai đối tượng được lớp chứa coi là bằng nhau có thể có hash khác nhau. Điều này vi phạm hợp đồng `equals/hashCode`.

Một cách đúng là dùng giá trị đã `stripTrailingZeros()` cho phần hash.

### 7.1. Chương trình hoàn chỉnh: khóa bằng nhau theo giá trị số

**Tệp `NumericAmountKeyDemo.java`:**

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class NumericAmountKeyDemo {
    static final class AmountKey {
        private final BigDecimal amount;

        AmountKey(BigDecimal amount) {
            this.amount = Objects.requireNonNull(amount);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof AmountKey other)) {
                return false;
            }
            return amount.compareTo(other.amount) == 0;
        }

        @Override
        public int hashCode() {
            return amount.stripTrailingZeros().hashCode();
        }
    }

    public static void main(String[] args) {
        AmountKey first = new AmountKey(new BigDecimal("2.0"));
        AmountKey second = new AmountKey(new BigDecimal("2.00"));
        AmountKey third = new AmountKey(new BigDecimal("2.000"));
        AmountKey different =
                new AmountKey(new BigDecimal("3.00"));

        System.out.println("first.equals(second): "
                + first.equals(second));
        System.out.println("hashes equal: "
                + (first.hashCode() == second.hashCode()));
        System.out.println("first.equals(different): "
                + first.equals(different));

        Set<AmountKey> amounts = new HashSet<>();
        amounts.add(first);
        amounts.add(second);
        System.out.println("set size: " + amounts.size());
        System.out.println("set contains third: "
                + amounts.contains(third));
    }
}
```

```bash
javac NumericAmountKeyDemo.java
java NumericAmountKeyDemo
```

**Đầu ra chính xác:**

```text
first.equals(second): true
hashes equal: true
first.equals(different): false
set size: 1
set contains third: true
```

Ở đây `AmountKey` xác định bình đẳng **theo giá trị số**, không theo scale. Hai số bằng nhau theo `compareTo` được `stripTrailingZeros` đưa về cùng biểu diễn chuẩn, nên mã băm có cùng kết quả. Vì `BigDecimal` bất biến và trường `amount` là `final`, khóa không thay đổi giá trị sau khi được tạo.

**Lưu ý nghiệp vụ:** Nếu khóa tiền tệ cần gồm cả **mã đơn vị tiền** (VD: VND, USD), chỉ so `BigDecimal` là chưa đủ: `2 USD` không bằng `2 VND`. Khi đó, quy tắc `equals` và `hashCode` phải kết hợp cả số tiền theo chính sách đã chọn **và** đơn vị tiền.

## 8. Scale là dữ liệu hữu ích, không phải “rác” cần loại bỏ

Nhiều hệ thống thực sự muốn giữ scale:

- Một đầu vào `2.00` có thể ngụ ý người nhập cung cấp số đến **hai chữ số thập phân**.
- Hệ thống kế toán hoặc quy tắc giá có thể yêu cầu hiển thị đúng **hai chữ số sau dấu thập phân**.
- Kết quả của phép tính `BigDecimal` có thể giữ scale theo quy tắc của phép toán, nên hai kết quả bằng nhau về số học chưa chắc cùng scale.
- Khi cần trao đổi dữ liệu, `toString()` và `toPlainString()` có cách biểu diễn khác nhau; lựa chọn định dạng/scale cần dựa trên giao thức, không dựa vào `equals`.

Đừng áp dụng “chuẩn hóa mọi `BigDecimal`” một cách máy móc. Hãy tách **giá trị toán học** khỏi **quy định độ chính xác, làm tròn và hiển thị**.

Trong phép tính và kiểm thử, luôn tự hỏi đang cần kiểm tra điều nào:

```text
Câu hỏi A: Số này có bằng số kia?
    → compareTo == 0

Câu hỏi B: Hai BigDecimal có cùng scale/biểu diễn?
    → equals

Câu hỏi C: Số này có bằng không?
    → signum == 0

Câu hỏi D: Cần chính xác hai chữ số thập phân?
    → chính sách setScale/rounding/format của nghiệp vụ
```

`equals` và `compareTo` không có nhiệm vụ thay thế cho phép làm tròn hay định dạng.

## 9. Bẫy từ cách khởi tạo BigDecimal

Khác biệt giữa constructor từ chuỗi và từ số `double` có thể khiến bài toán so sánh khó hiểu hơn.

```java
BigDecimal fromText = new BigDecimal("0.1");
BigDecimal fromDouble = new BigDecimal(0.1);
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
```

- `fromText` biểu diễn chính xác số thập phân `0.1` (scale `1`).
- Số dấu phẩy động nhị phân `double 0.1` không thể biểu diễn chính xác `0.1` thập phân; `new BigDecimal(0.1)` tạo ra giá trị chính xác của **giá trị nhị phân `double` ấy**, không phải đúng `0.1`.
- `BigDecimal.valueOf(0.1)` sử dụng biểu diễn chuỗi chuẩn của `double` để tạo `BigDecimal`, nên trường hợp này có giá trị và scale phù hợp với `new BigDecimal("0.1")`.

Ví dụ kiểm tra ngắn (đặt trong phương thức `main` có import `BigDecimal`):

```java
System.out.println(fromText.equals(fromDouble));  // false
System.out.println(fromText.compareTo(fromDouble) == 0); // false
System.out.println(fromText.equals(fromValueOf)); // true
```

**Điểm phân biệt:** Trường hợp `2.0` và `2.00` khác nhau **chỉ bởi scale** nhưng cùng giá trị số. Còn `new BigDecimal(0.1)` với `new BigDecimal("0.1")` có thể **khác cả giá trị số**, nên `compareTo` cũng không trả `0`. Khi dữ liệu tiền/giá có nguồn gốc từ số thập phân, ưu tiên tạo từ chuỗi thập phân hoặc một luồng chuyển đổi decimal đã được kiểm soát.

## 10. Lỗi phổ biến và cách sửa

| Cách viết hoặc giả định | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| `actual.equals(new BigDecimal("0"))` để hỏi kết quả số có bằng không | `0.00` không `equals` với `0` | Dùng `actual.signum() == 0` hoặc `compareTo(ZERO) == 0` |
| `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` phải `true` | `equals` xét scale | Dùng `compareTo == 0` nếu chỉ cần giá trị |
| `HashMap<BigDecimal, V>` sẽ coi `2.0` và `2.00` là cùng khóa | HashMap dùng `equals/hashCode` | Chuẩn hóa khóa hoặc dùng wrapper nhất quán |
| Dùng `TreeSet<BigDecimal>` rồi kỳ vọng hành vi như `HashSet` | TreeSet dùng `compareTo` | Chọn cấu trúc theo định nghĩa bằng nhau mong muốn |
| Wrapper `equals` dùng `compareTo` nhưng `hashCode` dùng `amount.hashCode()` | Có thể vi phạm hợp đồng | Hash giá trị được chuẩn hóa |
| Gọi `stripTrailingZeros()` và kỳ vọng scale luôn không âm | Kết quả có thể `1E+3` với scale `-3` | Xác định rõ chính sách chuẩn hóa và định dạng |
| `setScale(2)` luôn an toàn | Nếu cần làm tròn sẽ ném ngoại lệ | Chọn `RoundingMode` theo yêu cầu |
| `new BigDecimal(0.1)` tương đương số thập phân `0.1` | Đầu vào `double` có sai số biểu diễn | Tạo từ chuỗi thập phân hoặc quy trình chuyển đổi phù hợp |

## 11. Tự kiểm tra

**Câu 1.** Cho:

```java
BigDecimal x = new BigDecimal("5.0");
BigDecimal y = new BigDecimal("5.00");
```

Dự đoán `x.equals(y)`, `x.compareTo(y) == 0` và `x.scale()`, `y.scale()`.

**Đáp án:** `false`, `true`; scale lần lượt `1` và `2`.

**Câu 2.** Cho `BigDecimal result = new BigDecimal("0.000");`. Kiểm tra nào diễn đạt rõ ràng rằng giá trị số học bằng không?

**Đáp án:** `result.signum() == 0` (hoặc `result.compareTo(BigDecimal.ZERO) == 0`). `result.equals(BigDecimal.ZERO)` trả `false` vì scale khác.

**Câu 3.** `new BigDecimal("1000.00").stripTrailingZeros()` có thể có scale nào và hiển thị ra sao qua `toString()`?

**Đáp án:** Scale `-3` và chuỗi `1E+3`. `toPlainString()` cho `1000`, nhưng không giữ biểu diễn `1000.00` ban đầu.

**Câu 4.** Hai khóa bọc `BigDecimal` dùng `compareTo == 0` trong `equals`. Vì sao không thể mặc định trả `amount.hashCode()`?

**Đáp án:** Vì hai số cùng giá trị khác scale có thể có `BigDecimal.hashCode()` khác nhau. Wrapper coi chúng bằng nhau nhưng hash lại khác, vi phạm hợp đồng; cần dùng hash đã chuẩn hóa hoặc chính sách khác nhất quán.

**Câu 5.** Sau khi thêm `2.0` và `2.00` vào `HashSet<BigDecimal>` và `TreeSet<BigDecimal>` (thứ tự tự nhiên), số phần tử ở mỗi set là bao nhiêu?

**Đáp án:** `HashSet` có `2`, `TreeSet` có `1`, vì hai cấu trúc sử dụng hai quan hệ tương đương khác nhau cho trường hợp này.

**Câu 6.** Nếu nghiệp vụ **phải giữ đúng 2 chữ số thập phân** cho một số tiền, dùng `stripTrailingZeros()` trên dữ liệu nguồn có phù hợp không?

**Đáp án:** Không phải lựa chọn mặc định. Nó có thể làm mất scale cần giữ. Hãy xác định và áp dụng quy tắc scale, làm tròn và hiển thị theo nghiệp vụ.

## Tổng kết

**`BigDecimal.equals()` xét cả giá trị số học và scale; `BigDecimal.compareTo() == 0` xét giá trị số học.** Vì vậy `2.0` và `2.00` so bằng `equals` là `false` nhưng so bằng `compareTo` là `true`. `hashCode` tương thích với `equals` nên các cấu trúc hash có thể coi chúng là hai khóa khác nhau; cấu trúc sorted theo `compareTo` lại coi chúng tương đương. Khi muốn so giá trị số, dùng `compareTo` hoặc `signum`; khi muốn lưu khóa số học với hash, chuẩn hóa hay xây wrapper có `equals/hashCode` đồng bộ. Luôn cân nhắc scale có phải dữ liệu quan trọng của miền nghiệp vụ trước khi thay đổi nó.
