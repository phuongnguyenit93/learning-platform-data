# `toBigInteger()` khác `toBigIntegerExact()`: chuyển `BigDecimal` sang số nguyên chính xác

## 1. Mục tiêu bài học

`BigDecimal` biểu diễn các giá trị thập phân có độ chính xác tùy ý; `BigInteger` biểu diễn số nguyên có độ lớn tùy ý. Khi chuyển từ `BigDecimal` sang `BigInteger`, Java cung cấp hai lựa chọn có **hợp đồng khác nhau**:

- `toBigInteger()`: **loại bỏ phần lẻ** của giá trị thập phân, đi về **0**, rồi trả về `BigInteger`. Phép chuyển đổi này có thể mất dữ liệu mà không báo lỗi.
- `toBigIntegerExact()`: chỉ chuyển đổi nếu giá trị có thể biểu diễn **chính xác bằng số nguyên**. Nếu có phần lẻ khác 0, ném `ArithmeticException`.

Đây là khác biệt về **chính sách xử lý dữ liệu**, không phải chỉ khác tên phương thức. Sau bài học, bạn có thể dự đoán kết quả với số dương/âm, phần lẻ, các số 0 cuối, scientific notation; viết kiểm tra đầu vào đúng yêu cầu nghiệp vụ; và tránh nhầm lẫn với `intValue()`, `intValueExact()`, `RoundingMode` hoặc `Math.floor`.

## 2. Hai phương thức trả về cùng kiểu, nhưng khác cách xử lý phần lẻ

Trong `java.math.BigDecimal` có các phương thức:

```java
public BigInteger toBigInteger();
public BigInteger toBigIntegerExact();
```

Cả hai trả về `java.math.BigInteger` có **độ lớn số nguyên tùy ý**, thay vì giới hạn ở 32 bit (`int`) hay 64 bit (`long`). Nhưng hãy chú ý đến phần lẻ:

| `BigDecimal` đầu vào | `toBigInteger()` | `toBigIntegerExact()` | Lý do |
|---|---:|---:|---|
| `12` | `12` | `12` | Vốn là số nguyên |
| `12.00` | `12` | `12` | Phần thập phân chỉ gồm 0 |
| `12.99` | `12` | **Ném `ArithmeticException`** | Có phần lẻ khác 0 |
| `-12.99` | `-12` | **Ném `ArithmeticException`** | Có phần lẻ khác 0 |
| `-0.75` | `0` | **Ném `ArithmeticException`** | Cắt phần lẻ về 0 |
| `0.000` | `0` | `0` | Giá trị số học bằng 0 |
| `1E+3` | `1000` | `1000` | Chính xác là một số nguyên |
| `1E-3` | `0` | **Ném `ArithmeticException`** | Chính xác là 0.001 |

**Điểm cốt lõi:** `Exact` có nghĩa “không làm mất phần thập phân có nghĩa”. Nó **không đòi hỏi scale của `BigDecimal` phải bằng 0**: `12.00` có scale 2 nhưng vẫn là giá trị nguyên 12 và chuyển đổi chính xác được.

## 3. Cơ chế: bỏ phần lẻ theo hướng 0 hay bảo toàn giá trị

### 3.1. `toBigInteger()` cắt về 0

Xét biểu thức `new BigDecimal("12.99").toBigInteger()`: kết quả là `12`. Phần `.99` biến mất; không có phép làm tròn đến số nguyên gần nhất.

Với giá trị âm, kết quả là `-12`, **không phải `-13`**:

```text
-13 ----- -12.99 ----- -12 ----- 0 ----- 12 ----- 12.99 ----- 13
                        ^                         ^
             toBigInteger(-12.99)       toBigInteger(12.99)
```

Đi về 0 khác với đi về âm vô cực:

- `toBigInteger(-12.99)` = `-12`: bỏ phần lẻ, hướng về 0.
- `Math.floor(-12.99)` = `-13.0`: lấy số nguyên theo hướng −∞.
- `Math.ceil(-12.99)` = `-12.0`: lấy số nguyên theo hướng +∞.

Mặc dù `toBigInteger()` và `Math.ceil()` cho cùng phần nguyên ở ví dụ số âm này, chúng **không phải hai phép toán tương đương** cho cả số dương và số âm.

Theo nghĩa số học, với `x` dương: `toBigInteger(x)` tương ứng `floor(x)`; với `x` âm: nó tương ứng `ceil(x)`; với `x` nguyên: giữ nguyên. Nếu muốn biểu đạt trực tiếp việc bỏ phần thập phân bằng một `RoundingMode`, tên tương ứng là `RoundingMode.DOWN` (hướng về 0), không phải `RoundingMode.FLOOR`.

### 3.2. `toBigIntegerExact()` không chấp nhận mất phần lẻ

`toBigIntegerExact()` chỉ trả về nếu chuyển đổi giữ nguyên **giá trị số học**. Ví dụ:

```java
new BigDecimal("42.000").toBigIntegerExact(); // BigInteger 42
new BigDecimal("-42.000").toBigIntegerExact(); // BigInteger -42
new BigDecimal("42.001").toBigIntegerExact(); // ArithmeticException
```

Hai số `42.000` và `-42.000` đều có scale 3 nhưng có phần thập phân bằng 0. Vì vậy, **không được kiểm tra `scale() == 0` làm điều kiện duy nhất** để quyết định có chuyển đổi chính xác được không.

Nếu có phần lẻ khác 0, Java ném `ArithmeticException` để lập trình viên có cơ hội xử lý trường hợp đầu vào không đáp ứng hợp đồng. Nếu ứng dụng cần chấp nhận số thập phân và cố ý làm tròn, phải lựa chọn chính sách làm tròn riêng; không nên dùng `toBigInteger()` như một bước làm tròn ngầm.

## 4. Chương trình Java hoàn chỉnh: kết quả từng trường hợp

**Tệp `BigDecimalToBigIntegerDemo.java`** (Java 17+):

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class BigDecimalToBigIntegerDemo {
    public static void main(String[] args) {
        String[] inputs = {
                "12.99",
                "-12.99",
                "12.000",
                "0.00",
                "1E+3",
                "1E-3"
        };

        for (String input : inputs) {
            BigDecimal amount = new BigDecimal(input);
            BigInteger truncated = amount.toBigInteger();

            System.out.print("input=" + amount.toPlainString()
                    + ", trunc=" + truncated + ", exact=");

            try {
                System.out.println(amount.toBigIntegerExact());
            } catch (ArithmeticException ex) {
                System.out.println("ArithmeticException");
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac BigDecimalToBigIntegerDemo.java
java BigDecimalToBigIntegerDemo
```

Kết quả:

```text
input=12.99, trunc=12, exact=ArithmeticException
input=-12.99, trunc=-12, exact=ArithmeticException
input=12.000, trunc=12, exact=12
input=0.00, trunc=0, exact=0
input=1000, trunc=1000, exact=1000
input=0.001, trunc=0, exact=ArithmeticException
```

Các dòng này cho thấy ba điều:

1. `toBigInteger()` **luôn cung cấp phần nguyên** của các giá trị bình thường trên; nó không cảnh báo việc mất `.99` hoặc `.001`.
2. `toBigIntegerExact()` thất bại **chỉ khi giá trị không nguyên** (hoặc không thể chuyển đổi chính xác vì giới hạn tài nguyên trong những trường hợp cực đoan), chứ không đơn thuần khi chuỗi chứa dấu chấm thập phân.
3. `toPlainString()` được dùng để hiển thị `1E+3` thành `1000`, `1E-3` thành `0.001`. Hai phương thức chuyển sang `BigInteger` luôn xuất ra số nguyên và không mang scale của đầu vào.

## 5. `Scale`, zero cuối và ký pháp khoa học có ảnh hưởng thế nào?

Một `BigDecimal` được mô tả bằng **unscaled value** và **scale**:

```text
giá trị = unscaledValue × 10^(-scale)

"12.000" => unscaledValue = 12000, scale = 3
"1E+3"  => unscaledValue = 1,     scale = -3
"1E-3"  => unscaledValue = 1,     scale = 3
```

Bài toán `toBigIntegerExact()` là xác định **giá trị số học cuối cùng có phải số nguyên hay không**, không phải tìm xem `scale` dương, âm hoặc bằng 0.

- Scale dương **vẫn có thể** chuyển chính xác nếu tất cả chữ số của phần lẻ đều là 0, ví dụ `12.000`.
- Scale bằng 0 là số nguyên đã biểu diễn trực tiếp, ví dụ `12`.
- Scale âm làm giá trị là bội số của một lũy thừa của 10, ví dụ `1E+3 = 1000`; nó vẫn nguyên.
- Scale dương với phần lẻ khác 0 sẽ làm `toBigIntegerExact()` thất bại, ví dụ `1E-3 = 0.001`.

**Không cần gọi `stripTrailingZeros()` trước `toBigIntegerExact()`.** Phương thức exact tự đánh giá tính nguyên của giá trị. Gọi `stripTrailingZeros()` có thể thay đổi scale và chuỗi hiển thị, nên chỉ dùng nếu nghiệp vụ thực sự cần chuẩn hóa biểu diễn.

Ví dụ `2.0` và `2.00` từ chuỗi có scale lần lượt 1 và 2. Cả hai chuyển sang cùng số nguyên `2` qua `toBigIntegerExact()` mà không mất **giá trị số học**. Tuy nhiên, kết quả `BigInteger` không còn nhớ đầu vào có một hay hai chữ số thập phân. “Exact” ở đây là exact về **giá trị**, không phải “giữ nguyên định dạng”.

## 6. `toBigInteger` khác cách làm tròn `setScale`

Nếu muốn làm tròn trước khi chuyển sang số nguyên, phải viết quy tắc rõ ràng:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal x = new BigDecimal("-12.99");

System.out.println(x.toBigInteger()); // -12
System.out.println(x.setScale(0, RoundingMode.DOWN));    // -12
System.out.println(x.setScale(0, RoundingMode.FLOOR));   // -13
System.out.println(x.setScale(0, RoundingMode.CEILING)); // -12
System.out.println(x.setScale(0, RoundingMode.HALF_UP)); // -13
```

Đoạn mã này là ví dụ minh họa bên trong một phương thức có thể chạy (cần đặt imports ở đầu tệp). Với `x = -12.99`:

| Cách xử lý | Kết quả | Quy tắc |
|---|---:|---|
| `x.toBigInteger()` | `-12` | Cắt về 0, bỏ phần lẻ |
| `x.setScale(0, DOWN)` | `-12` | Làm tròn về 0 |
| `x.setScale(0, FLOOR)` | `-13` | Làm tròn về −∞ |
| `x.setScale(0, CEILING)` | `-12` | Làm tròn về +∞ |
| `x.setScale(0, HALF_UP)` | `-13` | Làm tròn tới gần nhất, quy tắc HALF_UP khi cách đều |

Khi đã làm tròn bằng `setScale(0, mode)`, có thể gọi `toBigIntegerExact()` ở bước cuối: giá trị đã có scale 0, nên bước chuyển không tiếp tục bỏ phần lẻ. Ví dụ:

```java
BigInteger rounded = x.setScale(0, RoundingMode.FLOOR)
                      .toBigIntegerExact(); // -13
```

Ở đây việc làm tròn là **có chủ đích** và được biểu đạt rõ trong mã. Ngược lại, `toBigIntegerExact()` trực tiếp từ `-12.99` sẽ ném ngoại lệ.

**Sai lầm phổ biến:** Vì một số tài liệu gọi thao tác cắt phần lẻ là “round down”, người học dễ đồng nhất nó với `FLOOR`. Trong `RoundingMode` của Java, `DOWN` nghĩa là về **0**, còn `FLOOR` nghĩa là về **âm vô cực**. Kiểm tra với số âm sẽ làm lộ ngay sự khác biệt.

## 7. Phân biệt với `intValue()`, `longValue()` và bản `Exact`

Sau `toBigInteger...`, ta nhận một `BigInteger` tùy ý độ lớn. Nếu đích cuối cùng lại là `int` hoặc `long`, cần kiểm tra **hai loại rủi ro độc lập**:

1. **Có phần lẻ không?** Nếu có, phép đổi sang số nguyên có thể mất phần thập phân.
2. **Có vượt giới hạn kiểu đích không?** Nếu có, chuyển sang `int`/`long` có thể mất các bit cao.

Đó là lý do các phương thức exact khác cũng quan trọng:

| Phương thức từ `BigDecimal` | Mất phần lẻ được phép? | Kiểm tra giới hạn `int`/`long`? |
|---|---|---|
| `toBigInteger()` | Có | Không áp dụng: đích là `BigInteger` |
| `toBigIntegerExact()` | Không | Không áp dụng: đích là `BigInteger` |
| `intValue()` / `longValue()` | Có | Không, có thể mất bit cao |
| `intValueExact()` / `longValueExact()` | Không | Có; ném `ArithmeticException` nếu ngoài miền |

Ví dụ khi số nguyên vượt `int`:

**Tệp `BigIntegerRangeDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.BigInteger;

public class BigIntegerRangeDemo {
    public static void main(String[] args) {
        BigDecimal source = new BigDecimal("2147483648");
        BigInteger big = source.toBigIntegerExact();

        System.out.println("BigInteger=" + big);
        System.out.println("long=" + source.longValueExact());

        try {
            System.out.println("int=" + source.intValueExact());
        } catch (ArithmeticException ex) {
            System.out.println("intValueExact: ArithmeticException");
        }
    }
}
```

```bash
javac BigIntegerRangeDemo.java
java BigIntegerRangeDemo
```

```text
BigInteger=2147483648
long=2147483648
intValueExact: ArithmeticException
```

Giá trị `2_147_483_648` lớn hơn `Integer.MAX_VALUE` (`2_147_483_647`), nhưng vẫn vừa `long` và luôn có thể lưu bằng `BigInteger`. Dùng `toBigIntegerExact()` giúp tránh mất phần lẻ, nhưng **không tự động kiểm tra** giá trị có vừa `int` hoặc `long` khi chuyển tiếp; hãy dùng `big.intValueExact()` hoặc `big.longValueExact()` nếu cần.

## 8. Thực hành: kiểm tra số lượng phải là số nguyên

Giả sử hệ thống đọc một trường `quantity` từ dữ liệu thập phân. Yêu cầu: số lượng phải nguyên và không âm; tuyệt đối không cho phép `2.8` biến thành `2`.

**Tệp `WholeQuantityDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.Objects;

public class WholeQuantityDemo {
    public static BigInteger requireWholeQuantity(BigDecimal quantity) {
        Objects.requireNonNull(quantity, "quantity");

        if (quantity.signum() < 0) {
            throw new IllegalArgumentException("Quantity cannot be negative");
        }

        try {
            return quantity.toBigIntegerExact();
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "Quantity must be a whole number: " + quantity, ex);
        }
    }

    public static void main(String[] args) {
        BigDecimal[] values = {
                new BigDecimal("2.00"),
                new BigDecimal("2.8"),
                new BigDecimal("0"),
                new BigDecimal("-1.0")
        };

        for (BigDecimal value : values) {
            try {
                System.out.println(value + " -> "
                        + requireWholeQuantity(value));
            } catch (IllegalArgumentException ex) {
                System.out.println(value + " -> REJECTED");
            }
        }
    }
}
```

```bash
javac WholeQuantityDemo.java
java WholeQuantityDemo
```

```text
2.00 -> 2
2.8 -> REJECTED
0 -> 0
-1.0 -> REJECTED
```

Ở ví dụ này, việc bắt `ArithmeticException` có ý nghĩa: dữ liệu có phần lẻ vi phạm quy tắc nghiệp vụ nên được chuyển thành thông báo lỗi phù hợp. Không nên bắt rồi âm thầm thay bằng `toBigInteger()` vì sẽ biến một đầu vào không hợp lệ thành đầu vào “hợp lệ giả”.

Nếu hệ thống chỉ chấp nhận số lượng dương, bổ sung kiểm tra `quantity.signum() > 0`; nếu cần giới hạn tối đa, dùng `BigInteger.compareTo(maximum)` sau khi chuyển chính xác.

### Khi nào `toBigInteger()` là lựa chọn hợp lệ?

Trong một số bài toán, yêu cầu **cố ý bỏ phần thập phân**. Ví dụ, lấy phần nguyên của một phép đo đã xác định rõ quy tắc cắt về 0. Khi ấy `toBigInteger()` đúng yêu cầu; hãy đặt tên biến/hàm thể hiện rõ ý định, chẳng hạn `truncatedUnits`.

Còn với định danh, số lượng mặt hàng, số thứ tự, cấu hình giới hạn hoặc dữ liệu mà phần lẻ không hợp lệ, `toBigIntegerExact()` an toàn hơn vì thể hiện hợp đồng bằng mã và báo lỗi sớm.

## 9. Các trường hợp biên và lỗi thường gặp

### 9.1. Số âm gần 0

```java
BigDecimal x = new BigDecimal("-0.99");

System.out.println(x.toBigInteger()); // 0
// x.toBigIntegerExact() sẽ ném ArithmeticException.
```

Một giá trị âm có thể bị cắt về 0. Nếu hệ thống dựa vào dấu hoặc quy tắc chỉ số nhóm, mất thông tin dấu như vậy có thể gây lỗi logic.

### 9.2. Những số 0 cuối và scale khác nhau

```java
new BigDecimal("2.0").toBigIntegerExact();  // 2
new BigDecimal("2.00").toBigIntegerExact(); // 2
new BigDecimal("2.01").toBigIntegerExact(); // ArithmeticException
```

Tính exact dựa trên phần lẻ **có giá trị khác 0**, không phụ thuộc số chữ số đã nhập. `BigInteger` trả về không còn giữ scale.

### 9.3. Khởi tạo từ `double` có thể đưa vào sai số nhị phân

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal(0.1);
```

`a` biểu diễn chính xác `0.1` thập phân. `b` biểu diễn chính xác giá trị nhị phân của `double` gần 0.1, nên có nhiều chữ số phụ. **Không nên tạo `BigDecimal` từ `double` nếu cần giữ nguyên giá trị chữ số đầu vào.** Ưu tiên `BigDecimal(String)` cho dữ liệu thập phân hoặc cân nhắc `BigDecimal.valueOf(double)` khi đã có `double` và hiểu tính giới hạn của dữ liệu đó. Sau khi tạo đối tượng, phương thức chuyển đổi không thể khôi phục độ chính xác đã mất trước đó.

### 9.4. Đừng bỏ qua ngoại lệ

Ví dụ này đánh mất một validation quan trọng:

```java
// Cách không nên làm nếu quy tắc đòi hỏi một số nguyên chính xác:
try {
    return amount.toBigIntegerExact();
} catch (ArithmeticException ignored) {
    return amount.toBigInteger(); // Âm thầm cắt phần lẻ
}
```

Đây chỉ là minh họa đoạn thân một phương thức có biến `amount` kiểu `BigDecimal`. Nếu cần làm tròn, hãy xác định rounding mode rõ ràng và ghi nhận quyết định. Nếu cần từ chối, hãy phát sinh lỗi có ngữ cảnh.

### 9.5. Không lẫn ngoại lệ tính nguyên với `null` và dữ liệu không parse được

Nếu biến `BigDecimal` là `null`, gọi bất kỳ phương thức nào trong hai phương thức trên sẽ ném `NullPointerException`. Nếu chuỗi đầu vào không hợp lệ, `new BigDecimal(text)` ném `NumberFormatException` ngay lúc parse, trước khi đến giai đoạn chuyển `BigInteger`. Hai loại lỗi này khác với `ArithmeticException` do phần lẻ khác 0.

### 9.6. Giá trị rất lớn

`BigInteger` không giới hạn ở `Integer.MAX_VALUE` hay `Long.MAX_VALUE`, nhưng vẫn chịu giới hạn thực tế của bộ nhớ và dung lượng biểu diễn. Không coi “arbitrary precision” là “không bao giờ gặp giới hạn tài nguyên”. Cũng cần tránh chuyển tiếp về kiểu nguyên cố định mà không kiểm tra phạm vi.

## 10. Bài tập tự kiểm tra (có đáp án)

1. **`new BigDecimal("8.999").toBigInteger()` cho kết quả gì?**  
   `8`, vì cắt phần lẻ về 0.

2. **`new BigDecimal("-8.999").toBigInteger()` cho kết quả gì?**  
   `-8`, không phải `-9`: `toBigInteger()` không phải floor.

3. **`new BigDecimal("8.000").toBigIntegerExact()` có lỗi không?**  
   Không. Kết quả là `BigInteger` có giá trị `8`, dù scale đầu vào lớn hơn 0.

4. **`new BigDecimal("8.001").toBigIntegerExact()` làm gì?**  
   Ném `ArithmeticException` vì phần lẻ khác 0.

5. **`new BigDecimal("1E+5").toBigIntegerExact()` có phải lỗi vì viết theo ký pháp khoa học?**  
   Không. Kết quả là `100000`, một số nguyên chính xác.

6. **Giá trị `2.99` phải làm tròn lên thành `3` theo quy tắc nghiệp vụ. Dùng phương thức nào?**  
   `new BigDecimal("2.99").setScale(0, RoundingMode.CEILING).toBigIntegerExact()` (với số dương này cho `3`). `toBigInteger()` trực tiếp chỉ cho `2`.

7. **Giá trị `2147483648.00` là số nguyên chính xác nhưng vượt `int`. `toBigIntegerExact()` có thành công không?**  
   Có. Kết quả là `2147483648` dưới dạng `BigInteger`. Nhưng chuyển tiếp bằng `intValueExact()` sẽ ném `ArithmeticException`.

8. **Sự khác nhau giữa `toBigIntegerExact()` và `intValueExact()` là gì?**  
   Cả hai đều không cho phép mất phần lẻ; `intValueExact()` còn phải bảo đảm kết quả nằm trong miền `int`, còn `BigInteger` hỗ trợ số nguyên lớn tùy ý.

## 11. Tổng kết và chọn API

Hãy quyết định theo hợp đồng dữ liệu:

| Yêu cầu | Giải pháp |
|---|---|
| Cố ý bỏ phần lẻ, hướng về 0 | `decimal.toBigInteger()` |
| Chỉ chấp nhận giá trị nguyên chính xác | `decimal.toBigIntegerExact()` |
| Phải làm tròn theo chính sách cụ thể | `decimal.setScale(0, mode).toBigIntegerExact()` |
| Phải chuyển sang `int` chính xác | `decimal.intValueExact()` hoặc `decimal.toBigIntegerExact().intValueExact()` |
| Phải chuyển sang `long` chính xác | `decimal.longValueExact()` hoặc `decimal.toBigIntegerExact().longValueExact()` |

Quy tắc nhớ nhanh: **Không có `Exact`: chấp nhận cắt phần lẻ. Có `Exact`: không làm mất phần lẻ; nếu không thể giữ nguyên giá trị, báo lỗi.** Mọi trường hợp vẫn phải kiểm tra kiểu đích, khả năng null và giới hạn tài nguyên tương ứng.

Tham khảo Javadoc chính thức:

- [Java 21 — `BigDecimal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [Java 21 — `BigInteger`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html)
- [Java 21 — `RoundingMode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html)
