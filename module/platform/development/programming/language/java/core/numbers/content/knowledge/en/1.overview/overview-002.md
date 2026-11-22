# Phân biệt giá trị toán học, kiểu dữ liệu và cách lưu trữ trong Java

Trong lập trình số, ba khái niệm thường bị trộn lẫn: **giá trị toán học** (con số ta muốn mô tả), **kiểu dữ liệu** (những giá trị và phép toán chương trình cho phép) và **cách biểu diễn/lưu trữ** (các bit hoặc cấu trúc dữ liệu máy tính dùng để mã hóa giá trị). Phân biệt ba tầng này giúp giải thích vì sao `0.1 + 0.2` không ra đúng `0.3`, vì sao `int` tràn số, và vì sao hai số trông giống nhau vẫn có hành vi khác nhau trong Java.

## 1. Ba tầng cần phân biệt

| Tầng | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Giá trị toán học | Ta đang nói đến đại lượng nào, độc lập với máy tính? | Số nguyên 42; phân số 1/3; số thực 0,1; số âm −5 |
| Kiểu dữ liệu | Java cho phép miền giá trị và phép toán nào? | `int`, `long`, `double`, `BigInteger`, `BigDecimal` |
| Biểu diễn/lưu trữ | Giá trị được mã hóa bằng gì và có chính xác không? | `int` có 32 bit bù hai; `double` dùng nhị phân dấu phẩy động; `BigDecimal` dùng số nguyên không tỉ lệ và scale |

Ví dụ, **42** là một giá trị toán học. Những cách viết sau có thể cùng mang giá trị số học 42 nhưng thuộc kiểu/biểu diễn khác nhau:

```java
int a = 42;
long b = 42L;
double c = 42.0;
BigInteger d = new BigInteger("42");
BigDecimal e = new BigDecimal("42.00");
```

`a` và `b` là số nguyên chính xác trong miền hữu hạn, `c` là số chấm động nhị phân (42 là một số nguyên nhỏ biểu diễn chính xác được), `d` là số nguyên có độ lớn tùy ý trong giới hạn tài nguyên, còn `e` biểu diễn thập phân chính xác với **unscaled value = 4200**, **scale = 2**. Trong `BigDecimal`, `42.00` và `42.0` bằng nhau về **giá trị số học** nhưng khác **scale**, điều ảnh hưởng đến `equals()`.

> Ghi nhớ: cách **hiển thị** số bằng ký tự (`"42"`, `"42.00"`) là một tầng khác. Một chuỗi văn bản chưa tự động là một giá trị kiểu số.

## 2. Miền giá trị và cách mã hóa của số nguyên nguyên thủy

Java quy định kích thước và khoảng giá trị cho các kiểu nguyên có dấu:

| Kiểu | Độ rộng logic | Khoảng giá trị (bao gồm hai đầu) |
| --- | ---: | --- |
| `byte` | 8 bit | −128 đến 127 |
| `short` | 16 bit | −32.768 đến 32.767 |
| `int` | 32 bit | −2.147.483.648 đến 2.147.483.647 |
| `long` | 64 bit | −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |

Với kiểu số nguyên có dấu rộng `n` bit, khoảng là `−2^(n−1)` đến `2^(n−1)−1`, vì có hữu hạn `2^n` mẫu bit. Java dùng **bù hai (two's complement)** để biểu diễn số nguyên có dấu. Ví dụ ở 8 bit: `0000_0101` diễn tả +5, còn `1111_1011` diễn tả −5. Cùng dãy bit chỉ có ý nghĩa số học sau khi gắn với **quy tắc diễn giải và độ rộng**.

`char` là kiểu nguyên 16 bit **không dấu**, có miền `0` đến `65535`, dùng cho đơn vị mã UTF-16. `char` không phải kiểu dành cho tính toán số thông thường, và một ký tự Unicode có thể cần hai `char`. Java không có kiểu nguyên nguyên thủy không dấu độc lập như `unsigned int` của C; các hàm như `Integer.toUnsignedLong` và `Integer.divideUnsigned` chỉ **diễn giải thao tác** trên mẫu bit của `int` theo nghĩa không dấu.

### Tràn số không làm giá trị toán học thay đổi, mà làm kết quả biểu diễn khác đi

```java
int max = Integer.MAX_VALUE;
System.out.println(max + 1);             // -2147483648
System.out.println(Math.addExact(max, 1)); // ném ArithmeticException
```

Giá trị toán học `2_147_483_647 + 1` là `2_147_483_648`, nhưng kết quả `int` thông thường vòng qua giá trị nhỏ nhất do phép toán số nguyên chỉ giữ 32 bit kết quả. Java **không tự ném exception** cho `+`, `-`, `*` tràn số nguyên. Dùng `Math.addExact`, `subtractExact`, `multiplyExact` hoặc chuyển sang `long`/`BigInteger` trước phép toán khi cần kiểm soát tràn.

Chú ý: ép kiểu **sau khi phép nhân `int` đã tràn** không khôi phục được kết quả đúng:

```java
int x = 1_000_000_000;
long wrong = (long) (x * 3); // -1294967296: nhân int trước
long right = (long) x * 3;   // 3000000000: nhân long
```

Khi ép hẹp từ `int` sang `byte`, Java chỉ giữ 8 bit thấp; `(byte) 130` cho `-126`, không phải một giá trị số học 130 có thể nằm trong `byte`. Ngược lại, gán `byte b = 130;` là lỗi biên dịch vì hằng nguyên không vừa kiểu đích.

## 3. Kiểu chấm động là phép xấp xỉ nhị phân có quy tắc riêng

`float` (32 bit) và `double` (64 bit) dùng định dạng IEEE 754 **binary32/binary64**, với bit dấu, số mũ và phần trị (*significand*). Độ chính xác hữu hạn: khoảng **7 chữ số thập phân có nghĩa** cho `float` và **15–16 chữ số** cho `double`; đây là ước lượng sử dụng, không phải số chữ số sau dấu phẩy cố định.

Nhiều phân số thập phân như `0.1` không thể viết hữu hạn bằng cơ số 2. Java lưu một số nhị phân gần nhất, vì vậy:

```java
System.out.println(0.1 + 0.2);       // 0.30000000000000004
System.out.println(0.1 + 0.2 == 0.3); // false
System.out.println(0.5 + 0.25);      // 0.75
```

`0.5 = 1/2` và `0.25 = 1/4` có biểu diễn nhị phân hữu hạn nên chính xác ở đây; `0.1` và `0.2` thì không. **In ra `0.1` không có nghĩa là bit trong `double` lưu đúng phân số toán học 1/10**: `Double.toString` chọn chuỗi thập phân ngắn có thể phân tích trở lại cùng giá trị `double`.

Đừng kiểm tra gần đúng bằng `==` khi sai số làm tròn có thể xuất hiện. Với phép đo có sai số, cân nhắc dung sai tuyệt đối/tương đối theo miền bài toán, chẳng hạn:

```java
static boolean nearlyEqual(double a, double b, double absTol, double relTol) {
    if (Double.doubleToLongBits(a) == Double.doubleToLongBits(b)) return true;
    if (!Double.isFinite(a) || !Double.isFinite(b)) return false;
    double diff = Math.abs(a - b);
    return diff <= Math.max(absTol, relTol * Math.max(Math.abs(a), Math.abs(b)));
}
```

Hàm này là **chính sách so sánh cho trường hợp có dung sai**, không phải định nghĩa bằng nhau cho mọi bài toán. Chọn `absTol` và `relTol` từ yêu cầu đo lường, không lấy một epsilon cố định cho mọi độ lớn. Nếu cần giá trị tiền tệ/thập phân chính xác, ưu tiên `BigDecimal`.

### Các trường hợp đặc biệt của số chấm động

- `Double.POSITIVE_INFINITY`/`NEGATIVE_INFINITY` có thể xuất hiện do phép tính chấm động tràn độ lớn, hoặc chia số hữu hạn khác 0 cho ±0.0; không phải là số thực hữu hạn.
- `Double.NaN` biểu diễn kết quả không xác định theo IEEE 754; `Double.NaN == Double.NaN` trả `false`. Kiểm tra bằng `Double.isNaN(x)`.
- `+0.0` và `-0.0` so sánh bằng `==` nhưng dấu của chúng có thể ảnh hưởng đến phép tính như `1.0 / -0.0` cho `-Infinity`.
- Với `double`, mọi số nguyên có trị tuyệt đối **không vượt quá `2^53`** đều biểu diễn chính xác, nhưng không phải tất cả số nguyên lớn hơn ngưỡng đó. `double` có thể có phạm vi độ lớn rộng hơn `long` mà vẫn mất chi tiết đơn vị.

## 4. `BigInteger` và `BigDecimal`: độ chính xác được quyết định bởi mô hình dữ liệu

### `BigInteger`: số nguyên chính xác, không giới hạn bởi 32/64 bit

`BigInteger` giữ giá trị nguyên bằng cấu trúc nhiều từ máy, có thể chứa số vượt `Long.MAX_VALUE` và dùng các phương thức `add`, `multiply`, `divide`, `mod`. Độ lớn thực tế bị giới hạn bởi bộ nhớ, hiệu năng và giới hạn triển khai; đối tượng là **immutable**.

```java
BigInteger beyondLong = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE);
System.out.println(beyondLong); // 9223372036854775808
```

### `BigDecimal`: số thập phân theo `unscaledValue × 10^(−scale)`

Hai thành phần cốt lõi là **một số nguyên tùy ý** và **scale**, không phải một giá trị nhị phân `double` được “in đẹp”:

```java
BigDecimal amount = new BigDecimal("12.30");
System.out.println(amount.unscaledValue()); // 1230
System.out.println(amount.scale());         // 2
System.out.println(amount);                 // 12.30
```

Tạo `BigDecimal` từ chuỗi thập phân khi nguồn là chuỗi/money decimal:

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
System.out.println(a.add(b)); // 0.3
```

**Tránh `new BigDecimal(0.1)` nếu muốn biểu diễn đúng số thập phân 0.1**: constructor nhận chính giá trị nhị phân `double` đã được làm tròn, nên kết quả chứa các chữ số xấp xỉ kéo dài. `BigDecimal.valueOf(0.1)` thông qua biểu diễn thập phân chuẩn của `double` và thường phù hợp hơn, nhưng nếu dữ liệu đầu vào ban đầu là văn bản thập phân thì giữ chuỗi gốc vẫn rõ ràng nhất.

`BigDecimal` chính xác cho các phép cộng/trừ/nhân trên những số thập phân hữu hạn đã biểu diễn, nhưng **chia có thể tạo khai triển vô hạn**: `BigDecimal.ONE.divide(new BigDecimal("3"))` ném `ArithmeticException` nếu không cung cấp chính sách làm tròn. Cần chọn `scale`/`RoundingMode` hoặc `MathContext`:

```java
BigDecimal oneThird = BigDecimal.ONE.divide(
        new BigDecimal("3"), 2, RoundingMode.HALF_UP);
System.out.println(oneThird); // 0.33
```

`equals()` của `BigDecimal` xét cả giá trị lẫn scale: `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là `false`. `compareTo()` so sánh giá trị số học và trả `0` trong trường hợp này. Việc loại bỏ zero dư bằng `stripTrailingZeros()` có thể đổi scale/biểu diễn; trong khóa của `HashMap`/`HashSet` phải chú ý hợp đồng `equals/hashCode`.

## 5. Literal, phép toán và ép kiểu có thể thay đổi kết quả

### Viết literal đúng kiểu

| Biểu thức | Kiểu mặc định / giá trị | Ghi chú |
| --- | --- | --- |
| `42` | `int` | Hằng nguyên thập phân mặc định là `int` nếu vừa |
| `42L` | `long` | `L` nên viết hoa, nhất là với số 1 |
| `42.0`, `1e3` | `double` | Hằng dấu phẩy động mặc định là `double` |
| `42.0f` | `float` | Hậu tố `f` hoặc `F` |
| `0b101010`, `0x2A` | `int` có giá trị 42 | Nhị phân và thập lục phân chỉ là cách viết literal |
| `1_000_000` | `int` có giá trị 1.000.000 | Dấu gạch dưới là cú pháp, không lưu trong giá trị |
| `"42"` | `String` | Văn bản, không tự động là số |

Chú ý literal `010` trong Java là **bát phân** (giá trị 8), không phải mười; đặt số 0 đầu literal nguyên dễ gây nhầm lẫn. Ký tự `-` trong `-42` là toán tử dấu âm, không phải “bit dấu” trong cú pháp literal.

### Kiểu của toán hạng quyết định phép toán

```java
System.out.println(1 / 2);          // 0: chia số nguyên
System.out.println(1.0 / 2);        // 0.5: phép chia double
System.out.println(5 / 2 * 2);      // 4: phần lẻ đã mất sau chia
System.out.println((double) 5 / 2); // 2.5: đổi trước phép chia
```

Các toán hạng `byte`, `short` và `char` thường được **promote** lên `int` trước phép toán số học. Ví dụ `byte a = 1, b = 2; byte c = a + b;` không biên dịch vì `a + b` có kiểu `int`, dù giá trị toán học 3 vừa `byte`. Gán sang kiểu hẹp cần conversion hợp lệ hoặc cast tường minh và chấp nhận khả năng mất dữ liệu.

Ép `double` sang `int` **cắt bỏ phần thập phân hướng về 0** khi giá trị trong khoảng cho phép; NaN được chuyển về 0, các giá trị vượt miền được bão hòa về biên tương ứng. Vì thế `(int) 3.9` là 3 còn `(int) -3.9` là −3; đây không phải làm tròn đến số nguyên gần nhất.

**Auto-boxing** (`int` ↔ `Integer`) thay đổi việc dùng primitive thành đối tượng wrapper, không mở rộng miền giá trị của số. Với đối tượng, `==` so sánh danh tính tham chiếu; dùng `equals` nếu so sánh giá trị wrapper, và chú ý `null` khi unboxing.

## 6. Nói về “lưu trữ” mà không nhầm với vị trí trong bộ nhớ

- Một biến primitive kiểu `int` mô tả một giá trị 32 bit theo quy tắc Java; kiểu `double` dùng biểu diễn 64 bit. Điều này **không đồng nghĩa** với lời hứa rằng một biến luôn chiếm đúng 4/8 byte trên stack: bố cục stack frame, thanh ghi, alignment và tối ưu JIT là chi tiết triển khai JVM.
- Với `BigInteger`/`BigDecimal`, biến tham chiếu trỏ đến đối tượng có trạng thái cần thiết; đối tượng còn có overhead, có thể dùng mảng nội bộ, và được quản lý bởi JVM/GC. Không thể suy ra tổng bộ nhớ chỉ từ số chữ số của chuỗi hiển thị.
- Mẫu bit, kiểu và cách hiển thị phải được tách riêng: ví dụ các bit thấp `1111_1111` có thể đọc là `255` nếu là byte không dấu trong một giao thức, hoặc `-1` nếu diễn giải kiểu `byte` Java. Một ký tự `'9'` có mã Unicode khác số nguyên `9`.
- Chuyển đổi qua JSON, CSV, cơ sở dữ liệu hoặc giao thức mạng cần đặc tả **loại số, miền giá trị, độ chính xác, đơn vị và quy tắc làm tròn**; một chuỗi `"9007199254740993"` có thể mất chính xác nếu trung gian chuyển qua số `double`.

## 7. Ví dụ Java 17+ chạy độc lập

Lưu vào `NumericLayersDemo.java`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class NumericLayersDemo {
    public static void main(String[] args) {
        int integer = 42;
        double floating = 42.0;
        BigDecimal decimal = new BigDecimal("42.00");

        System.out.println("int: " + integer);
        System.out.println("double: " + floating);
        System.out.println("BigDecimal: " + decimal);
        System.out.println("0.1 + 0.2 = " + (0.1 + 0.2));
        System.out.println("1 / 2 = " + (1 / 2));
        System.out.println("1.0 / 2 = " + (1.0 / 2));
        System.out.println("int overflow = " + (Integer.MAX_VALUE + 1));
        System.out.println("decimal sum = "
                + new BigDecimal("0.1").add(new BigDecimal("0.2")));
        System.out.println("beyond long = "
                + BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE));
        System.out.println("rounded third = "
                + BigDecimal.ONE.divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP));
        System.out.println("same numeric value = "
                + (decimal.compareTo(new BigDecimal("42.0")) == 0));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac NumericLayersDemo.java
java NumericLayersDemo
```

Output:

```text
int: 42
double: 42.0
BigDecimal: 42.00
0.1 + 0.2 = 0.30000000000000004
1 / 2 = 0
1.0 / 2 = 0.5
int overflow = -2147483648
decimal sum = 0.3
beyond long = 9223372036854775808
rounded third = 0.33
same numeric value = true
```

Mỗi dòng thể hiện sự khác nhau giữa **giá trị mong muốn**, **quy tắc tính của kiểu** và **khả năng biểu diễn**. `double` biểu diễn chính xác `42` nhưng không biểu diễn chính xác `0.1`; `BigDecimal` giữ được thập phân 0.1 khi xây dựng từ chuỗi; `int` không thể biểu diễn `MAX_VALUE+1`; `BigInteger` làm được.

## 8. Chọn kiểu từ yêu cầu của bài toán

| Nhu cầu | Lựa chọn thường phù hợp | Điều cần kiểm tra |
| --- | --- | --- |
| Đếm, chỉ số, số lượng trong miền nhỏ | `int` | Tràn khi cộng/nhân, kể cả ở trung gian |
| Số nguyên lớn hơn miền `int`, timestamp/đơn vị phù hợp | `long` | Vẫn hữu hạn; kiểm tra đơn vị và tràn |
| Số nguyên lớn tùy ý (mật mã, tổ hợp, số lớn) | `BigInteger` | Chi phí CPU/bộ nhớ, đối tượng immutable |
| Đo đạc/khoa học, tính toán chấp nhận sai số chấm động | `double`; đôi khi `float` khi ràng buộc tài nguyên | NaN, infinity, làm tròn, dung sai |
| Tiền tệ/quy tắc decimal cụ thể, giá trị thập phân cần chính xác | `BigDecimal` hoặc số nguyên ở đơn vị nhỏ nhất theo hợp đồng | Scale, rounding, phép chia, định dạng, đơn vị tiền |
| Dữ liệu số từ chuỗi ngoài hệ thống | Parse có kiểm tra miền và định dạng | Không coi cách hiển thị là kiểu; tránh chuyển qua `double` khi cần decimal chính xác |

### Những lỗi phổ biến cần tự kiểm tra

1. **Nhầm số hiển thị với số được lưu:** `System.out.println(0.1)` cho “0.1” nhưng `double` lưu một xấp xỉ nhị phân.
2. **Chọn kiểu theo số chữ số nhìn thấy:** `double` chứa giá trị rất lớn nhưng không giữ chính xác mọi số nguyên 64 bit.
3. **Chỉ cast ở kết quả:** `(long) (a * b)` không cứu được phép nhân `int` đã tràn.
4. **Tưởng `BigDecimal` tự khắc phục đầu vào sai:** xây dựng từ `new BigDecimal(0.1)` đã nhận xấp xỉ `double`; hãy giữ dữ liệu decimal gốc.
5. **Quên phép toán điều khiển bởi kiểu:** `1 / 2` bằng 0; `byte + byte` ra `int`.
6. **Nhầm “exact” với vô hạn:** `BigDecimal` tính thập phân hữu hạn chính xác trong nhiều phép toán nhưng chia 1/3 phải chỉ định làm tròn; `BigInteger` chính xác nhưng chịu giới hạn tài nguyên.
7. **Khẳng định cứng vị trí stack/heap hoặc số byte đối tượng:** kích thước logic của primitive được Java định nghĩa; bố trí bộ nhớ vật lý do JVM quyết định.

## 9. Tự kiểm tra mức hiểu

- Vì sao `42`, `42.0` và `new BigDecimal("42.00")` có thể biểu diễn cùng giá trị toán học nhưng không cùng kiểu, scale và phép toán?
- Với `int` 32 bit, tại sao `Integer.MAX_VALUE + 1` âm trong khi số nguyên toán học không âm?
- Tại sao `0.5` biểu diễn chính xác bằng binary64 nhưng `0.1` thì không? Khi nào chọn `double`, khi nào chọn `BigDecimal`?
- Tại sao `BigDecimal("1.0").equals(BigDecimal("1.00"))` khác `compareTo() == 0`? Tại sao điều này quan trọng khi dùng làm khóa?
- Nếu chuỗi đầu vào là `"9007199254740993"`, chọn `long`, `double` hay `BigInteger` để giữ nguyên giá trị và vì sao?

**Nguyên tắc ứng dụng:** bắt đầu từ **miền giá trị toán học và yêu cầu độ chính xác**, chọn **kiểu và phép toán** đáp ứng yêu cầu đó, rồi xác minh **biểu diễn, chuyển đổi, tràn số và hiển thị** ở từng ranh giới dữ liệu.