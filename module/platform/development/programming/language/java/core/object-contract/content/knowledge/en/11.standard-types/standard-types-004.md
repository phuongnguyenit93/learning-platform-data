# Phân biệt `==` trên số thực với `equals()` của lớp bao `Double` và `Float`

## 1. Đang so sánh giá trị nguyên thủy hay đối tượng?

Trong Java, `double` và `float` là **kiểu nguyên thủy**; `Double` và `Float` là **lớp bao** (wrapper). Hai biểu thức sau trông giống nhau nhưng dựa vào quy tắc khác nhau:

```java
double a = 1.5;
double b = 1.5;
boolean primitiveEqual = (a == b);           // true
boolean wrapperEqual = Double.valueOf(a)
        .equals(Double.valueOf(b));          // true
```

Đây là **đoạn mã minh họa**, không phải chương trình Java độc lập. Kết quả trên tình cờ cùng là `true`; cách đánh giá biểu thức mới là điểm cần phân biệt:

- **`a == b` với hai toán hạng số nguyên thủy:** Java thực hiện phép so sánh số theo quy tắc số thực của IEEE 754; với `float` và `double` trộn nhau, phép nâng kiểu số (`binary numeric promotion`) được áp dụng trước khi so sánh.
- **`x.equals(y)` với `x` là `Double` hoặc `Float`:** gọi phương thức trên đối tượng `x` và kiểm tra giá trị theo quy tắc của lớp bao, bao gồm xử lý đặc biệt cho `NaN` và `+0.0`/`-0.0`. Đối số phải thuộc **đúng lớp bao** (`Double` đối với `Double.equals`, `Float` đối với `Float.equals`).
- **`x == y` với hai biến tham chiếu `Double` (hoặc hai `Float`):** so sánh **cùng tham chiếu đối tượng hay không**, không dùng `equals()` và không tự bỏ hộp khi cả hai toán hạng đều là tham chiếu.

Điều này dẫn tới ba câu hỏi khác nhau: hai **giá trị nguyên thủy** có bằng nhau theo `==` không; hai **đối tượng bao** có bằng nhau theo `equals()` không; và hai **tham chiếu** có trỏ đúng cùng đối tượng không.

## 2. `NaN`: `==` là `false`, nhưng `Double.equals()` có thể là `true`

`NaN` (Not a Number) đại diện kết quả không xác định của một số phép toán số thực như `0.0 / 0.0`. Với toán tử `==` trên số thực nguyên thủy:

```java
double x = Double.NaN;
System.out.println(x == x);                         // false
System.out.println(Double.valueOf(x).equals(
        Double.valueOf(Double.NaN)));               // true
```

Theo quy tắc so sánh số thực, **bất cứ so sánh bằng `==` nào có toán hạng `NaN` đều trả về `false`**, kể cả so sánh một biến với chính nó. Muốn phát hiện NaN, dùng `Double.isNaN(value)` hoặc `Float.isNaN(value)`.

Trong khi đó, `Double.equals(Object)` quy định **hai giá trị `Double` mang NaN được coi là bằng nhau**, kể cả các mẫu bit NaN khác nhau. `Float.equals(Object)` cũng coi các `Float` NaN bằng nhau.

Đây là lựa chọn có chủ ý để lớp bao dùng được với hợp đồng `equals()` (đặc biệt tính phản xạ) và các tập hợp/bảng băm. `Double.doubleToLongBits` và `Float.floatToIntBits` chuẩn hóa các mẫu bit NaN cho mục đích so sánh này.

## 3. Số không có dấu: `+0.0 == -0.0` nhưng wrapper `equals()` là `false`

IEEE 754 biểu diễn **hai dấu cho số không**. Khi so sánh số nguyên thủy:

```java
double positive = +0.0;
double negative = -0.0;
System.out.println(positive == negative);           // true
System.out.println(Double.valueOf(positive)
        .equals(Double.valueOf(negative)));         // false
```

Với `==`, `+0.0` và `-0.0` được coi là bằng nhau. Với `Double.equals()`, hai biểu diễn có **bit dấu khác nhau** nên không bằng nhau. `Float.equals()` áp dụng cách phân biệt tương tự cho `+0.0f` và `-0.0f`.

Đừng nhầm quy tắc này với `NaN`: `Double.equals()` **gộp tất cả NaN thành cùng giá trị bằng nhau**, nhưng **phân biệt dấu của số không**. Quy tắc đối với `Float` là tương tự.

## 4. Bảng đối chiếu hành vi

Giả sử mỗi phép `equals()` dùng hai đối tượng cùng lớp bao (`Double` hoặc `Float`) chứa các giá trị tương ứng:

| Trường hợp | `==` giữa giá trị nguyên thủy | `equals()` giữa lớp bao cùng kiểu |
| --- | --- | --- |
| `1.5` và `1.5` | `true` | `true` |
| `1.5` và `2.0` | `false` | `false` |
| `Double.NaN` và `Double.NaN` | `false` | `true` |
| `+0.0` và `-0.0` | `true` | `false` |
| `Double.POSITIVE_INFINITY` và chính nó | `true` | `true` |
| `Float.NaN` và `Float.NaN` | `false` | `true` |
| `+0.0f` và `-0.0f` | `true` | `false` |

Không có phép so sánh nào trong bảng này sử dụng `==` giữa **hai tham chiếu wrapper**: nếu đổi toán hạng thành `Double`/`Double`, ý nghĩa `==` chuyển sang đồng nhất đối tượng.

## 5. Chương trình Java 17+ chạy độc lập

Lưu toàn bộ đoạn mã vào tệp **`FloatingEqualityDemo.java`**:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class FloatingEqualityDemo {
    public static void main(String[] args) {
        double plusZero = +0.0;
        double minusZero = -0.0;
        double nan1 = Double.NaN;
        double nan2 = 0.0 / 0.0;

        Double boxedPlusZero = Double.valueOf(plusZero);
        Double boxedMinusZero = Double.valueOf(minusZero);
        Double boxedNaN1 = Double.valueOf(nan1);
        Double boxedNaN2 = Double.valueOf(nan2);

        System.out.println("double zeros ==: " + (plusZero == minusZero));
        System.out.println("Double.equals zeros: "
                + boxedPlusZero.equals(boxedMinusZero));
        System.out.println("double NaN ==: " + (nan1 == nan2));
        System.out.println("Double.equals NaN: "
                + boxedNaN1.equals(boxedNaN2));

        float floatPlusZero = +0.0f;
        float floatMinusZero = -0.0f;
        System.out.println("float zeros ==: "
                + (floatPlusZero == floatMinusZero));
        System.out.println("Float.equals zeros: "
                + Float.valueOf(floatPlusZero).equals(Float.valueOf(floatMinusZero)));
        System.out.println("float NaN ==: " + (Float.NaN == Float.NaN));
        System.out.println("Float.equals NaN: "
                + Float.valueOf(Float.NaN).equals(Float.valueOf(Float.NaN)));

        System.out.println("primitive double/float ==: " + (1.0d == 1.0f));
        System.out.println("cross-type wrapper equals: "
                + Double.valueOf(1.0).equals(Float.valueOf(1.0f)));
        System.out.println("Objects.equals same Double: "
                + Objects.equals(Double.valueOf(1.5), Double.valueOf(1.5)));

        Set<Double> values = new HashSet<>();
        values.add(boxedNaN1);
        values.add(boxedNaN2);
        values.add(boxedPlusZero);
        values.add(boxedMinusZero);
        System.out.println("HashSet<Double> size: " + values.size());

        System.out.println("decimal ==: " + (0.1 + 0.2 == 0.3));
        System.out.println("decimal close: "
                + (Math.abs((0.1 + 0.2) - 0.3) < 1e-9));

        Double missing = null;
        System.out.println("Objects.equals(null, null): "
                + Objects.equals(missing, null));
        try {
            System.out.println(missing == 0.0);
        } catch (NullPointerException ex) {
            System.out.println("null Double == double: NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac FloatingEqualityDemo.java
java FloatingEqualityDemo
```

Kết quả:

```text
double zeros ==: true
Double.equals zeros: false
double NaN ==: false
Double.equals NaN: true
float zeros ==: true
Float.equals zeros: false
float NaN ==: false
Float.equals NaN: true
primitive double/float ==: true
cross-type wrapper equals: false
Objects.equals same Double: true
HashSet<Double> size: 3
decimal ==: false
decimal close: true
Objects.equals(null, null): true
null Double == double: NullPointerException
```

`HashSet<Double>` lưu ba phần tử vì **hai NaN được coi là trùng nhau theo `equals()`**, còn `+0.0` và `-0.0` là hai giá trị khác nhau trong hợp đồng lớp `Double`. Lớp bao bảo đảm `hashCode()` tương ứng với `equals()`, vì vậy phép tra cứu trong bộ sưu tập dựa trên băm vẫn nhất quán.

Ví dụ `decimal close: true` minh họa so sánh xấp xỉ với một sai số nhỏ trong **tình huống số hữu hạn có độ lớn nhỏ**; `1e-9` chỉ là ngưỡng mẫu, không phải giá trị đúng cho mọi bài toán.

## 6. Ba bẫy khi dùng `==` với lớp bao

### a. Hai wrapper: so sánh tham chiếu

```java
Double first = Double.valueOf(1.25);
Double second = Double.valueOf(1.25);
boolean sameObject = (first == second);  // không nên giả định true/false
boolean sameValue = first.equals(second); // true
```

Vì cả `first` và `second` là `Double`, phép `==` trên đây kiểm tra **cùng đối tượng**. Không nên phụ thuộc vào việc factory/autoboxing có tái sử dụng một đối tượng hay không. Tương tự đối với `Float`.

### b. Một wrapper và một nguyên thủy: Java tự tháo hộp

```java
Double boxed = Double.valueOf(1.25);
double primitive = 1.25;
boolean equal = (boxed == primitive);     // true, boxed được unbox
```

Khi một vế là `Double` và vế kia là `double`, biểu thức so sánh số cần giá trị nguyên thủy; Java thực hiện **unboxing** đối với vế lớp bao. Nếu `boxed == null`, unboxing sẽ ném `NullPointerException`; `null` không tự được coi là `0.0`.

### c. `Double.equals(Float)` luôn là `false`

```java
System.out.println(1.0d == 1.0f); // true: hai nguyên thủy, nâng kiểu
System.out.println(Double.valueOf(1.0).equals(Float.valueOf(1.0f)));
// false: Double.equals chỉ chấp nhận đối tượng Double
```

`Double.equals(Object)` không thực hiện chuyển `Float` thành `Double` trước khi so sánh, và `Float.equals(Object)` cũng không tự chuyển từ `Double`. Trong khi đó, `==` trên hai số nguyên thủy khác kiểu dùng quy tắc nâng kiểu số. Với các số không biểu diễn chính xác như `0.1f`, nâng kiểu vẫn có thể dẫn tới kết quả khác mong đợi do sai số biểu diễn.

## 7. So sánh gần đúng và so sánh dùng làm khóa

Phép so sánh `==` trên số nguyên thủy hỏi **hai giá trị biểu diễn có bằng nhau theo quy tắc số thực Java không**. Nó không hiểu sai số từ phép tính trước đó. Ví dụ `0.1 + 0.2` và `0.3` khác nhau một lượng nhỏ do biểu diễn nhị phân nên `==` trả `false`.

Nếu yêu cầu nghiệp vụ là **gần bằng** trong tính toán số học, có thể xét một ngưỡng sai số phù hợp:

```java
boolean close = Math.abs(a - b) <= tolerance;
```

Đoạn trên giả định `a`, `b` là các số hữu hạn; nếu có `NaN`, vô cực, nhiều bậc độ lớn khác nhau hoặc cả giá trị sát số không, cần thiết kế kiểm tra riêng (ví dụ phân biệt các trường hợp đặc biệt, kết hợp ngưỡng tuyệt đối/tương đối). Không dùng ngưỡng tùy ý để thay thế `equals()`/`hashCode()` cho khóa bảng băm: phép gần bằng thông thường có thể **không bắc cầu** (A gần B, B gần C nhưng A không gần C), vi phạm yêu cầu của quan hệ bằng nhau.

Ngược lại, khi dùng `Double`/`Float` trong `HashMap`, `HashSet` hoặc so sánh đối tượng giá trị, `equals()` có các quy tắc ổn định và tương thích với hash: `NaN` bằng NaN, `+0.0` khác `-0.0`. Với các ứng dụng cần thứ tự sắp xếp, `Double.compare(a, b)` và `Float.compare(a, b)` đưa ra thứ tự đầy đủ hơn so với `==`/`<` trên số nguyên thủy, bao gồm thứ tự đối với NaN và hai loại zero; không diễn giải `Double.compare` đơn thuần là `a == b`.

`Objects.equals(x, y)` giúp so sánh **hai tham chiếu có thể `null`** mà không tự gây NPE: hai `null` trả `true`, một `null` trả `false`, còn khi khác `null`, nó dựa vào `x.equals(y)`. Nếu cả hai là lớp `Double`, các quy tắc NaN/zero nói trên vẫn áp dụng.

## 8. Lỗi phổ biến và cách kiểm tra nhanh

| Cách hiểu/viết sai | Cách xử lý |
| --- | --- |
| Dùng `==` giữa hai `Double` rồi cho rằng so sánh giá trị | Chọn `equals()` hoặc `Objects.equals()` khi cần giá trị wrapper |
| Nghĩ `Double.NaN == Double.NaN` là `true` | `NaN` không bằng chính nó dưới `==` nguyên thủy; dùng `Double.isNaN` để kiểm tra NaN |
| Nghĩ `+0.0` và `-0.0` luôn được coi là một | Phân biệt: `==` trên số nguyên thủy là `true`, wrapper `equals()` là `false` |
| Bỏ qua unboxing `Double` có thể `null` | Kiểm tra `null` trước phép so sánh số hoặc dùng `Objects.equals()` theo đúng ngữ nghĩa cần thiết |
| Trộn `Double` và `Float` trong `equals()` mong chúng tự quy về một kiểu | Chuyển về cùng kiểu và xác định rõ quy tắc so sánh |
| So sánh kết quả tính dấu phẩy động bằng `==` khi nghiệp vụ yêu cầu gần bằng | Chọn tiêu chí sai số theo miền giá trị, đơn vị và điều kiện biên; xử lý NaN/vô cực riêng |

## 9. Tự kiểm tra kiến thức

1. `double d = Double.NaN; d == d` trả gì? **`false`**, vì `NaN` không bằng chính nó dưới phép `==` số thực.
2. `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` trả gì? **`true`**, vì `Double.equals()` coi hai NaN bằng nhau.
3. `+0.0d == -0.0d` và `Double.valueOf(+0.0d).equals(Double.valueOf(-0.0d))` lần lượt là gì? **`true` và `false`**.
4. `Double x = null; x == 0.0` có trả `false` không? **Không**; Java unbox `x` và ném `NullPointerException`.
5. Hai biến `Double` chứa `1.0`, dùng `x == y` có phải luôn `true`? **Không**; `==` giữa hai tham chiếu hỏi có cùng đối tượng hay không.

**Ghi nhớ:** `==` trên `double`/`float` so sánh giá trị số thực nguyên thủy; `Double.equals`/`Float.equals` là quan hệ bằng nhau của đối tượng lớp bao, **coi NaN bằng NaN nhưng phân biệt `+0.0` với `-0.0`**. Và khi cả hai toán hạng là wrapper, `==` lại so sánh **tham chiếu**, không thay thế `equals()`.