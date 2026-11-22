# Chọn `BigDecimal` khi cần số thập phân chính xác trong Java 17

**Chủ đề:** Java 17  
**Chương:** Số thực  
**Bài học:** Chọn BigDecimal khi cần số thập phân chính xác

Khi xử lý tiền tệ, giá sản phẩm, thuế, chiết khấu, lãi suất hoặc dữ liệu cần giữ đúng giá trị thập phân, kiểu `float` và `double` có thể tạo ra sai số biểu diễn. Java cung cấp `java.math.BigDecimal` để biểu diễn và tính toán số thập phân với độ chính xác tùy ý, theo các quy tắc làm tròn do chương trình chỉ định.

Điều quan trọng không chỉ là đổi kiểu biến từ `double` sang `BigDecimal`. Muốn kết quả chính xác, cần **khởi tạo đúng cách**, giữ dữ liệu ở dạng thập phân trong suốt quá trình tính toán, lựa chọn thời điểm và quy tắc làm tròn, đồng thời xử lý đúng phép chia và so sánh.

Bài học này tập trung vào:

- Vì sao số thực nhị phân có thể không biểu diễn chính xác một số thập phân quen thuộc.
- Cách tạo `BigDecimal` từ chuỗi, số nguyên và giá trị `double`.
- Ý nghĩa của `precision`, `scale`, tính bất biến và các phép toán.
- Sự khác nhau giữa `equals()` và `compareTo()`.
- Cách chia, đặt số chữ số thập phân và chọn `RoundingMode`.
- Cách sử dụng `BigDecimal` trong tiền tệ, nhập liệu và cơ sở dữ liệu.

`BigDecimal` đã tồn tại từ các phiên bản Java đầu tiên và được sử dụng bình thường trên Java 17. Đây là API chuẩn trong package `java.math`, không phải tính năng preview.

## 1. Vì sao `double` không luôn chính xác với số thập phân?

Máy tính biểu diễn `float` và `double` theo hệ nhị phân. Tương tự như phân số `1/3` có biểu diễn thập phân vô hạn `0.3333...`, nhiều phân số có biểu diễn nhị phân vô hạn.

Ví dụ, số thập phân `0.1` không thể được biểu diễn chính xác bằng một số hữu hạn bit theo định dạng dấu phẩy động nhị phân. Giá trị lưu trữ thực tế là một số nhị phân rất gần `0.1`.

```java
public class FloatingPointExample {
    public static void main(String[] args) {
        double a = 0.1;
        double b = 0.2;

        System.out.println(a + b);
        System.out.println((0.1 + 0.2) == 0.3);
    }
}
```

Kết quả thường thấy:

```text
0.30000000000000004
false
```

Đây không phải lỗi ngẫu nhiên của Java. Nó là hệ quả của cách biểu diễn số dấu phẩy động theo chuẩn IEEE 754. `double` vẫn hoạt động đúng theo quy tắc của kiểu số đó; vấn đề nằm ở việc **một số giá trị thập phân không có biểu diễn nhị phân hữu hạn**.

### 1.1. Sai số có thể tích lũy

Một phép tính riêng lẻ có thể chỉ lệch rất nhỏ, nhưng nhiều phép cộng, trừ, nhân hoặc so sánh lặp lại có thể khiến sai số ảnh hưởng đến kết quả nghiệp vụ.

Ví dụ một hệ thống cộng giá trị nhiều dòng:

```java
double total = 0.0;

for (int i = 0; i < 10; i++) {
    total += 0.1;
}

System.out.println(total);
```

Kết quả có thể không đúng chính xác giá trị thập phân kỳ vọng là `1.0`. Khi hệ thống phải đối soát tiền, số dư, hóa đơn hoặc báo cáo, việc sai lệch ở nhiều bước là rủi ro cần tránh.

### 1.2. Khi nào sai số dấu phẩy động không phải vấn đề?

Không phải chương trình nào cũng cần `BigDecimal`. `double` phù hợp với nhiều bài toán khoa học, đồ họa, mô phỏng, xử lý tín hiệu và tính toán mà sai số gần đúng được chấp nhận.

Ví dụ, khi mô phỏng vị trí của một vật thể, độ chính xác tương đối và hiệu năng có thể quan trọng hơn việc mọi giá trị thập phân có biểu diễn chính xác tuyệt đối.

Hãy chọn theo yêu cầu của miền dữ liệu:

| Nhu cầu | Kiểu thường phù hợp | Lý do |
|---|---|---|
| Giá sản phẩm, số tiền, thuế, chiết khấu | `BigDecimal` hoặc số nguyên đơn vị nhỏ nhất | Cần kiểm soát chính xác giá trị thập phân và quy tắc làm tròn |
| Tỷ lệ, lãi suất, số lượng thập phân cần đối soát | `BigDecimal` | Kiểm soát precision, scale và rounding |
| Đồ họa, mô phỏng vật lý, tính toán gần đúng | `double` | Hiệu năng tốt và mô hình gần đúng thường phù hợp |
| Chỉ số, số đếm nguyên | `int` hoặc `long` | Không cần số thập phân |
| Tiền có đơn vị nhỏ nhất cố định và phép tính đơn giản | Có thể dùng `long` lưu đơn vị nhỏ nhất | Tránh dấu phẩy động, nhưng cần tự quản lý scale và quy tắc nghiệp vụ |

**Nguyên tắc:** Dùng `BigDecimal` khi độ chính xác thập phân là một phần của yêu cầu nghiệp vụ. Không cần dùng nó cho mọi phép tính số học.

## 2. `BigDecimal` biểu diễn số thập phân như thế nào?

`BigDecimal` biểu diễn một giá trị bằng một số nguyên không giới hạn độ dài (unscaled value) và một số scale:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Ví dụ:

| Biểu diễn | Unscaled value | Scale | Giá trị |
|---|---:|---:|---:|
| `123.45` | 12345 | 2 | \(12345 \times 10^{-2}\) |
| `7.00` | 700 | 2 | \(700 \times 10^{-2}\) |
| `0.001` | 1 | 3 | \(1 \times 10^{-3}\) |
| `1200` | 1200 | 0 | \(1200 \times 10^0\) |
| `1.2E+3` | 12 | -2 | \(12 \times 10^2\) |

Scale không nhất thiết luôn không âm. Một số có dạng khoa học như `1.2E+3` có thể có scale âm.

### 2.1. Precision là gì?

`precision()` trả về số chữ số của unscaled value, bỏ qua dấu âm và không tính số mũ như một chữ số.

```java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("123.4500");

System.out.println(amount.precision()); // 7
System.out.println(amount.scale());     // 4
```

Ở đây:

- Unscaled value là `1234500`, gồm 7 chữ số.
- Scale là 4, nghĩa là có 4 chữ số ở bên phải dấu thập phân.
- Giá trị số học vẫn là `123.45`.

### 2.2. Scale không phải giới hạn số chữ số có nghĩa

```java
BigDecimal a = new BigDecimal("123.45");
BigDecimal b = new BigDecimal("0.001");
BigDecimal c = new BigDecimal("1000");

System.out.println(a.scale()); // 2
System.out.println(b.scale()); // 3
System.out.println(c.scale()); // 0
```

Scale cho biết vị trí thập phân trong biểu diễn. Precision cho biết số chữ số của phần unscaled. Hai khái niệm này khác nhau.

Trong hệ thống tiền tệ, một cột cơ sở dữ liệu kiểu `DECIMAL(19, 2)` thường có precision 19 và scale 2. Đây là ràng buộc lưu trữ của schema; `BigDecimal` bản thân không giới hạn ở 19 chữ số.

## 3. Khởi tạo `BigDecimal` đúng cách

Cách tạo `BigDecimal` quyết định dữ liệu đầu vào có chính xác hay không. Đây là phần rất quan trọng.

### 3.1. Ưu tiên constructor nhận `String` cho dữ liệu thập phân

```java
BigDecimal price = new BigDecimal("19.99");
BigDecimal taxRate = new BigDecimal("0.08");
BigDecimal quantity = new BigDecimal("2.5");
```

`String` được phân tích theo biểu diễn thập phân, nên `new BigDecimal("0.1")` biểu diễn chính xác số thập phân 0.1.

Đây thường là lựa chọn tốt khi dữ liệu đến từ:

- Form nhập liệu.
- File CSV hoặc cấu hình.
- JSON có token số thập phân.
- Cơ sở dữ liệu kiểu `DECIMAL`/`NUMERIC`.
- Quy tắc nghiệp vụ được mô tả bằng chuỗi thập phân.

Nếu chuỗi không phải biểu diễn số hợp lệ, constructor ném `NumberFormatException`:

```java
BigDecimal value = new BigDecimal("12,50"); // NumberFormatException
```

`BigDecimal(String)` không tự hiểu dấu phẩy theo locale. Với input chuẩn API thường dùng dấu chấm làm dấu thập phân: `"12.50"`.

### 3.2. Dùng `BigDecimal.valueOf(long)` cho số nguyên

```java
BigDecimal cents = BigDecimal.valueOf(1250);
BigDecimal count = BigDecimal.valueOf(3);

System.out.println(cents); // 1250
System.out.println(count); // 3
```

Phương thức này thuận tiện để tạo `BigDecimal` từ `long` hoặc `int` đã chính xác.

### 3.3. Tránh `new BigDecimal(double)` với số thập phân cần chính xác

Đoạn sau thường gây bất ngờ:

```java
BigDecimal wrong = new BigDecimal(0.1);

System.out.println(wrong);
```

Giá trị nhận được là biểu diễn thập phân chính xác của **giá trị double nhị phân đã được lưu**, chứ không phải số thập phân lý tưởng `0.1`. Kết quả có thể là:

```text
0.1000000000000000055511151231257827021181583404541015625
```

Constructor không làm sai dữ liệu; nó phản ánh chính xác giá trị đầu vào `double`. Nhưng đầu vào đó đã không phải chính xác số thập phân `0.1`.

### 3.4. Nếu đã có double, dùng `BigDecimal.valueOf(double)`

```java
BigDecimal decimal = BigDecimal.valueOf(0.1);

System.out.println(decimal); // 0.1
```

`BigDecimal.valueOf(double)` sử dụng biểu diễn chuỗi chuẩn của `Double.toString(double)` rồi tạo `BigDecimal` từ chuỗi đó. Vì vậy, nó thường cho kết quả thập phân dễ dự đoán hơn constructor nhận `double`.

Tuy nhiên, cần hiểu giới hạn:

- Nó **không khôi phục thông tin đã mất** trong các phép tính `double` trước đó.
- Nó dùng cách biểu diễn thập phân ngắn gọn của giá trị double, không chứng minh rằng toàn bộ phép tính trước đó là chính xác theo nghiệp vụ.
- Nếu đầu vào ban đầu là số thập phân do người dùng nhập, tốt nhất hãy giữ chuỗi đó và tạo `BigDecimal` trực tiếp.

Ví dụ:

```java
double calculated = 0.1 + 0.2;

BigDecimal fromDouble = BigDecimal.valueOf(calculated);
BigDecimal fromText = new BigDecimal("0.3");

System.out.println(fromDouble); // 0.30000000000000004
System.out.println(fromText);   // 0.3
```

`valueOf` không thể biến một kết quả double đã lệch thành đúng giá trị nghiệp vụ ban đầu.

### 3.5. So sánh các cách khởi tạo

| Cách tạo | Ví dụ | Khuyến nghị |
|---|---|---|
| Chuỗi thập phân | `new BigDecimal("0.1")` | **Ưu tiên** khi dữ liệu gốc là số thập phân |
| Số nguyên | `BigDecimal.valueOf(100L)` | Tốt khi đầu vào là số nguyên chính xác |
| double bằng `valueOf` | `BigDecimal.valueOf(0.1)` | Dùng khi nguồn bắt buộc là double và muốn biểu diễn chuỗi chuẩn của nó |
| Constructor double | `new BigDecimal(0.1)` | Tránh cho dữ liệu thập phân nghiệp vụ |

### 3.6. Khai báo hằng số

```java
private static final BigDecimal ZERO = BigDecimal.ZERO;
private static final BigDecimal ONE = BigDecimal.ONE;
private static final BigDecimal HUNDRED = BigDecimal.valueOf(100);

private static final BigDecimal TAX_RATE = new BigDecimal("0.08");
```

Các hằng `ZERO`, `ONE`, `TEN` có sẵn trong API. Với tỷ lệ thập phân, dùng chuỗi để biểu diễn đúng ý định.

## 4. Các phép toán cơ bản

`BigDecimal` cung cấp phương thức cho các phép toán thay vì dùng toán tử `+`, `-`, `*` hoặc `/`.

| Phép toán | Phương thức | Ví dụ |
|---|---|---|
| Cộng | `add()` | `a.add(b)` |
| Trừ | `subtract()` | `a.subtract(b)` |
| Nhân | `multiply()` | `a.multiply(b)` |
| Chia chính xác | `divide()` | `a.divide(b)` |
| Chia có làm tròn | `divide(divisor, scale, roundingMode)` | `a.divide(b, 2, RoundingMode.HALF_UP)` |
| Lấy số dư | `remainder()` | `a.remainder(b)` |
| Đổi scale | `setScale()` | `a.setScale(2, RoundingMode.HALF_UP)` |
| So sánh số học | `compareTo()` | `a.compareTo(b)` |

Ví dụ:

```java
BigDecimal a = new BigDecimal("12.50");
BigDecimal b = new BigDecimal("2.25");

System.out.println(a.add(b));      // 14.75
System.out.println(a.subtract(b)); // 10.25
System.out.println(a.multiply(b)); // 28.1250
```

### 4.1. Cộng và trừ giữ độ chính xác

```java
BigDecimal total = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));

System.out.println(total); // 0.3
```

Không có sai số biểu diễn nhị phân như phép cộng `double` tương ứng.

Kết quả của phép cộng/trừ không tự làm tròn về hai chữ số thập phân. Scale của kết quả phụ thuộc vào scale của các toán hạng; cần áp dụng quy tắc làm tròn của nghiệp vụ nếu cần.

### 4.2. Nhân có thể tạo nhiều chữ số thập phân

```java
BigDecimal unitPrice = new BigDecimal("19.99");
BigDecimal quantity = new BigDecimal("2.5");

BigDecimal total = unitPrice.multiply(quantity);

System.out.println(total); // 49.975
```

Phép nhân chính xác không tự làm tròn về hai chữ số. Nếu nghiệp vụ yêu cầu kết quả tiền tệ có scale 2, cần quyết định rõ thời điểm và cách làm tròn:

```java
BigDecimal rounded = total.setScale(2, RoundingMode.HALF_UP);

System.out.println(rounded); // 49.98
```

### 4.3. Không dùng toán tử số học trực tiếp

Không thể viết:

```java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("2.30");

// Không hợp lệ:
// BigDecimal total = a + b;
```

Dùng `a.add(b)`. Java không định nghĩa toán tử `+` cho đối tượng `BigDecimal`.

## 5. `BigDecimal` là immutable

`BigDecimal` là đối tượng **bất biến**. Mọi phép toán trả về một đối tượng mới; chúng không sửa đối tượng ban đầu.

```java
BigDecimal amount = new BigDecimal("10.00");

amount.add(new BigDecimal("5.00"));

System.out.println(amount); // 10.00
```

Dòng `amount.add(...)` không thay đổi `amount`. Nếu muốn giữ kết quả, phải gán lại:

```java
amount = amount.add(new BigDecimal("5.00"));

System.out.println(amount); // 15.00
```

Tương tự với `setScale`:

```java
BigDecimal price = new BigDecimal("12.345");

price.setScale(2, RoundingMode.HALF_UP);
System.out.println(price); // 12.345

price = price.setScale(2, RoundingMode.HALF_UP);
System.out.println(price); // 12.35
```

Đây là một lỗi phổ biến khi mới dùng `BigDecimal`: gọi phương thức nhưng không lưu giá trị trả về.

## 6. Phân biệt `equals()` và `compareTo()`

Đây là một trong những khác biệt quan trọng nhất khi làm việc với `BigDecimal`.

- `equals()` so sánh **giá trị và scale**.
- `compareTo()` so sánh **giá trị số học**, bỏ qua khác biệt scale.

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));        // false
System.out.println(a.compareTo(b));    // 0
System.out.println(a.compareTo(b) == 0); // true
```

`2.0` và `2.00` cùng biểu diễn giá trị số học 2, nhưng có scale lần lượt là 1 và 2. Vì `equals` xét cả scale, kết quả là `false`.

### 6.1. So sánh lớn hơn, nhỏ hơn

Không dùng các toán tử `>`, `<` hoặc `==` cho hai đối tượng `BigDecimal`:

```java
BigDecimal balance = new BigDecimal("100.00");
BigDecimal limit = new BigDecimal("50.00");

if (balance.compareTo(limit) > 0) {
    System.out.println("Số dư lớn hơn hạn mức");
}
```

Kết quả `compareTo`:

| Kết quả | Ý nghĩa |
|---:|---|
| Số âm | Giá trị bên trái nhỏ hơn bên phải |
| 0 | Hai giá trị số học bằng nhau |
| Số dương | Giá trị bên trái lớn hơn bên phải |

Không nên phụ thuộc vào giá trị âm/dương cụ thể ngoài dấu và số 0.

### 6.2. Ảnh hưởng trong Set và Map

Vì `equals()` và `hashCode()` xét scale, hai giá trị `2.0` và `2.00` là hai khóa khác nhau trong `HashMap` hoặc hai phần tử khác nhau trong `HashSet`:

```java
var values = new java.util.HashSet<BigDecimal>();
values.add(new BigDecimal("2.0"));
values.add(new BigDecimal("2.00"));

System.out.println(values.size()); // 2
```

Ngược lại, cấu trúc dựa trên thứ tự như `TreeSet` mặc định sử dụng `compareTo`:

```java
var sorted = new java.util.TreeSet<BigDecimal>();
sorted.add(new BigDecimal("2.0"));
sorted.add(new BigDecimal("2.00"));

System.out.println(sorted.size()); // 1
```

Vì `compareTo` trả về 0, `TreeSet` xem hai giá trị là cùng một phần tử theo thứ tự tự nhiên.

**Thực hành:** Nếu miền nghiệp vụ xem `2.0` và `2.00` là cùng một giá trị, dùng `compareTo(...) == 0` cho phép so sánh. Nếu dùng làm khóa, cần thống nhất chuẩn hóa scale trước khi đưa vào collection hoặc thiết kế comparator/equals phù hợp.

### 6.3. Có thể chuẩn hóa scale khi cần

```java
BigDecimal normalizedA = new BigDecimal("2.0").stripTrailingZeros();
BigDecimal normalizedB = new BigDecimal("2.00").stripTrailingZeros();

System.out.println(normalizedA.equals(normalizedB)); // true
```

Nhưng `stripTrailingZeros()` có thể tạo scale âm. Ví dụ `new BigDecimal("1000").stripTrailingZeros()` có thể có biểu diễn `1E+3`. Khi cần xuất chuỗi không dùng ký hiệu khoa học, cân nhắc `toPlainString()`.

## 7. Chia và vấn đề số thập phân vô hạn

Phép chia là điểm cần quan tâm đặc biệt. Một số kết quả có biểu diễn thập phân hữu hạn:

```java
BigDecimal a = new BigDecimal("1");
BigDecimal b = new BigDecimal("4");

System.out.println(a.divide(b)); // 0.25
```

Nhưng `1 / 3` có biểu diễn thập phân vô hạn:

```java
BigDecimal a = BigDecimal.ONE;
BigDecimal b = new BigDecimal("3");

System.out.println(a.divide(b)); // ArithmeticException
```

`BigDecimal.divide(divisor)` yêu cầu kết quả chính xác nếu không cung cấp quy tắc làm tròn. Nếu thương có biểu diễn thập phân vô hạn, Java không thể trả về một `BigDecimal` hữu hạn chính xác, nên ném `ArithmeticException`.

### 7.1. Chia với scale và rounding mode

Khi nghiệp vụ cho phép giới hạn số chữ số thập phân, chỉ định scale và cách làm tròn:

```java
BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("3"),
        2,
        RoundingMode.HALF_UP
);

System.out.println(result); // 0.33
```

Đọc các tham số:

- Số chia: `3`.
- Scale kết quả: `2`, tức hai chữ số ở bên phải dấu thập phân.
- Rounding mode: `HALF_UP`.

### 7.2. Chia theo MathContext

Có thể giới hạn số chữ số có nghĩa bằng `MathContext`:

```java
import java.math.MathContext;
import java.math.RoundingMode;

MathContext context = new MathContext(5, RoundingMode.HALF_UP);

BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("3"),
        context
);

System.out.println(result); // 0.33333
```

Khác với scale:

- `scale = 2` đặt số chữ số sau dấu thập phân là 2.
- `precision = 5` trong `MathContext` giới hạn tổng số chữ số có nghĩa là 5.

Ví dụ `12345.6` với precision 5 sẽ được làm tròn theo 5 chữ số có nghĩa, không phải 5 chữ số sau dấu thập phân.

### 7.3. Chia chính xác khi có thể, làm tròn khi nghiệp vụ yêu cầu

Không nên chọn scale và rounding mode chỉ để tránh exception. Hãy xác định:

- Kết quả được lưu ở đơn vị nào?
- Cần bao nhiêu chữ số thập phân?
- Làm tròn ở từng dòng, ở tổng hóa đơn hay chỉ khi hiển thị?
- Quy tắc làm tròn được quy định bởi hợp đồng, chuẩn kế toán hay nghiệp vụ nào?

Nếu yêu cầu là chính xác tuyệt đối và phép chia có kết quả hữu hạn, có thể dùng `divide(divisor)`. Nếu kết quả vô hạn hoặc cần giới hạn scale, phải chọn quy tắc làm tròn rõ ràng.

## 8. Các chế độ làm tròn `RoundingMode`

`java.math.RoundingMode` xác định cách chuyển giá trị có nhiều chữ số hơn scale đích về số chữ số cần thiết.

Các chế độ chuẩn Java 17:

| Chế độ | Quy tắc |
|---|---|
| `UP` | Làm tròn ra xa 0 nếu cần bỏ chữ số |
| `DOWN` | Cắt về phía 0 |
| `CEILING` | Làm tròn về phía dương vô cùng |
| `FLOOR` | Làm tròn về phía âm vô cùng |
| `HALF_UP` | Gần nhất; trường hợp đúng giữa thì ra xa 0 |
| `HALF_DOWN` | Gần nhất; trường hợp đúng giữa thì về phía 0 |
| `HALF_EVEN` | Gần nhất; trường hợp đúng giữa chọn kết quả có chữ số cuối chẵn |
| `UNNECESSARY` | Yêu cầu không được làm tròn; nếu cần làm tròn thì ném exception |

### 8.1. Ví dụ với `HALF_UP` và `HALF_EVEN`

```java
BigDecimal a = new BigDecimal("2.345");
BigDecimal b = new BigDecimal("2.355");

System.out.println(a.setScale(2, RoundingMode.HALF_UP));   // 2.35
System.out.println(b.setScale(2, RoundingMode.HALF_UP));   // 2.36

System.out.println(a.setScale(2, RoundingMode.HALF_EVEN)); // 2.34
System.out.println(b.setScale(2, RoundingMode.HALF_EVEN)); // 2.36
```

Với `HALF_EVEN`:

- `2.345` nằm chính giữa `2.34` và `2.35`; chữ số cuối của `2.34` là 4 (chẵn), nên chọn `2.34`.
- `2.355` nằm giữa `2.35` và `2.36`; chữ số cuối của `2.36` là 6 (chẵn), nên chọn `2.36`.

`HALF_EVEN` thường được gọi là *banker's rounding*, nhưng không phải mọi hệ thống tài chính đều áp dụng nó. Phải dùng quy tắc nghiệp vụ cụ thể.

### 8.2. Làm tròn số âm

Các quy tắc hướng về 0, ra xa 0 và hướng dương/âm vô cùng khác nhau:

```java
BigDecimal value = new BigDecimal("-1.231");

System.out.println(value.setScale(2, RoundingMode.DOWN));    // -1.23
System.out.println(value.setScale(2, RoundingMode.UP));      // -1.24
System.out.println(value.setScale(2, RoundingMode.CEILING));  // -1.23
System.out.println(value.setScale(2, RoundingMode.FLOOR));    // -1.24
```

- `DOWN` hướng về 0.
- `UP` hướng ra xa 0.
- `CEILING` hướng tới số lớn hơn theo trục số.
- `FLOOR` hướng tới số nhỏ hơn theo trục số.

Đừng diễn giải `CEILING` là “luôn tăng trị tuyệt đối”; với số âm, kết quả có thể ít âm hơn.

### 8.3. `UNNECESSARY` để kiểm tra scale

Khi dữ liệu phải có tối đa hai chữ số thập phân và không được phép làm tròn, dùng `UNNECESSARY`:

```java
BigDecimal valid = new BigDecimal("12.30")
        .setScale(2, RoundingMode.UNNECESSARY);

BigDecimal invalid = new BigDecimal("12.345")
        .setScale(2, RoundingMode.UNNECESSARY); // ArithmeticException
```

Đây là cách hữu ích để phát hiện đầu vào vượt quá scale quy định thay vì âm thầm làm tròn.

### 8.4. `setScale` không tự sửa đối tượng

```java
BigDecimal amount = new BigDecimal("10.999");

BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP);

System.out.println(amount);  // 10.999
System.out.println(rounded); // 11.00
```

Vì `BigDecimal` immutable, kết quả làm tròn phải được lưu vào biến mới hoặc gán trở lại biến.

## 9. Scale và hiển thị kết quả

`BigDecimal` lưu cả giá trị và scale. Hai giá trị có thể bằng nhau về mặt số học nhưng có cách hiển thị khác nhau.

```java
BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");

System.out.println(a.toString()); // 10.0
System.out.println(b.toString()); // 10.00
```

Điều này hữu ích khi scale thể hiện số chữ số thập phân có ý nghĩa trong nghiệp vụ, ví dụ số tiền hiển thị hai chữ số sau dấu thập phân.

### 9.1. `setScale` để chuẩn hóa số chữ số thập phân

```java
BigDecimal amount = new BigDecimal("10");

BigDecimal twoDecimals = amount.setScale(2);

System.out.println(twoDecimals); // 10.00
```

Nếu chỉ thêm số 0 ở cuối mà không cần thay đổi giá trị, `setScale(2)` có thể dùng mà không chỉ định rounding mode. Nhưng nếu cần loại bỏ chữ số có ý nghĩa, Java sẽ ném `ArithmeticException` nếu không có quy tắc làm tròn.

```java
BigDecimal amount = new BigDecimal("10.125");

// Ném ArithmeticException vì phải bỏ chữ số mà không có rounding mode:
amount.setScale(2);
```

### 9.2. `toString()` và `toPlainString()`

```java
BigDecimal value = new BigDecimal("1E+3");

System.out.println(value.toString());      // 1E+3
System.out.println(value.toPlainString()); // 1000
```

- `toString()` có thể dùng ký hiệu khoa học khi phù hợp.
- `toPlainString()` tạo chuỗi thập phân không dùng exponent.
- `toEngineeringString()` dùng ký hiệu khoa học theo quy tắc engineering.

Khi hiển thị tiền tệ, thường cần scale cố định và định dạng locale, chứ không chỉ gọi `toString()`.

### 9.3. `stripTrailingZeros()` có thể làm scale thay đổi

```java
BigDecimal value = new BigDecimal("1000.00");
BigDecimal stripped = value.stripTrailingZeros();

System.out.println(stripped); // có thể in 1E+3
System.out.println(stripped.scale()); // -3
```

`stripTrailingZeros()` bỏ các số 0 không cần thiết ở cuối và có thể đưa scale xuống số âm. Nếu hệ thống cần luôn giữ hai chữ số tiền tệ, đừng gọi nó một cách tùy tiện ở đường hiển thị.

## 10. Ví dụ nghiệp vụ: tính tiền hàng và thuế

Giả sử một đơn hàng có:

- Đơn giá: `19.99`.
- Số lượng: `3`.
- Thuế suất minh họa: `8%`.

Tính subtotal, thuế và tổng tiền bằng `BigDecimal`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class InvoiceCalculation {
    public static void main(String[] args) {
        BigDecimal unitPrice = new BigDecimal("19.99");
        BigDecimal quantity = BigDecimal.valueOf(3);
        BigDecimal taxRate = new BigDecimal("0.08");

        BigDecimal subtotal = unitPrice.multiply(quantity);

        BigDecimal tax = subtotal
                .multiply(taxRate)
                .setScale(2, RoundingMode.HALF_UP);

        BigDecimal total = subtotal.add(tax)
                .setScale(2, RoundingMode.HALF_UP);

        System.out.println("Subtotal: " + subtotal.toPlainString());
        System.out.println("Tax: " + tax.toPlainString());
        System.out.println("Total: " + total.toPlainString());
    }
}
```

Kết quả:

```text
Subtotal: 59.97
Tax: 4.80
Total: 64.77
```

Phép nhân subtotal chính xác: `19.99 × 3 = 59.97`. Thuế chưa làm tròn là `59.97 × 0.08 = 4.7976`; đặt scale 2 theo `HALF_UP` cho ra `4.80`.

Đây là ví dụ minh họa kỹ thuật. Hệ thống thực tế phải tuân theo chính sách thuế và quy tắc làm tròn được áp dụng cho từng loại giao dịch; có nơi làm tròn từng dòng, có nơi cộng các dòng trước rồi mới làm tròn.

### 10.1. Làm tròn từng dòng và làm tròn ở tổng có thể khác nhau

Giả sử có nhiều dòng nhỏ. Hai chính sách sau có thể tạo kết quả khác:

1. Làm tròn từng dòng rồi cộng.
2. Cộng giá trị chính xác của tất cả dòng rồi làm tròn một lần.

```java
BigDecimal line1 = new BigDecimal("0.005");
BigDecimal line2 = new BigDecimal("0.005");

BigDecimal eachRounded =
        line1.setScale(2, RoundingMode.HALF_UP)
        .add(line2.setScale(2, RoundingMode.HALF_UP));

BigDecimal totalRounded =
        line1.add(line2).setScale(2, RoundingMode.HALF_UP);

System.out.println(eachRounded); // 0.02
System.out.println(totalRounded); // 0.01
```

Kết quả khác nhau:

- Mỗi dòng `0.005` được làm tròn thành `0.01`, tổng là `0.02`.
- Tổng chính xác `0.010` được làm tròn thành `0.01`.

Không có một chính sách đúng cho mọi miền nghiệp vụ. Cần thống nhất thời điểm làm tròn trong thiết kế và kiểm thử.

## 11. Nhập số thập phân theo locale

`BigDecimal(String)` dùng dấu chấm làm dấu thập phân theo cú pháp số của nó. Nhưng người dùng có thể nhập theo locale:

- Locale Việt Nam thường dùng dấu phẩy làm dấu thập phân và dấu chấm phân tách hàng nghìn theo quy ước định dạng.
- Locale US thường dùng dấu chấm làm dấu thập phân và dấu phẩy phân tách hàng nghìn.

Không nên tự thay dấu phẩy/dấu chấm một cách tùy tiện, vì chuỗi `"1.234"` có thể mang ý nghĩa khác nhau tùy locale.

Dùng `NumberFormat`/`DecimalFormat` với `setParseBigDecimal(true)` khi cần phân tích dữ liệu theo locale:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.util.Locale;

public class LocalizedNumberInput {
    public static void main(String[] args) throws ParseException {
        NumberFormat numberFormat =
                NumberFormat.getNumberInstance(Locale.GERMANY);

        DecimalFormat decimalFormat = (DecimalFormat) numberFormat;
        decimalFormat.setParseBigDecimal(true);

        BigDecimal amount =
                (BigDecimal) decimalFormat.parse("1.234,56");

        System.out.println(amount.toPlainString()); // 1234.56
    }
}
```

Trong ứng dụng thực tế, cần xử lý trường hợp parse chỉ đọc một phần chuỗi hoặc đầu vào sai định dạng theo yêu cầu giao diện. Với API trao đổi dữ liệu chuẩn, quy ước dấu chấm thập phân như JSON thường đơn giản hơn; hãy giữ nguyên token số thập phân và chuyển trực tiếp thành `BigDecimal` bằng thư viện phù hợp.

## 12. Dùng `BigDecimal` với cơ sở dữ liệu

Trong cơ sở dữ liệu quan hệ, kiểu `DECIMAL` hoặc `NUMERIC` thường được dùng cho số thập phân chính xác với precision và scale được khai báo.

Ví dụ schema:

```sql
CREATE TABLE product_price (
    product_id BIGINT PRIMARY KEY,
    price DECIMAL(19, 2) NOT NULL
);
```

Trong JDBC, dùng `setBigDecimal` và `getBigDecimal`:

```java
import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

static void updatePrice(
        PreparedStatement statement,
        long productId,
        BigDecimal price
) throws SQLException {
    statement.setBigDecimal(1, price);
    statement.setLong(2, productId);
    statement.executeUpdate();
}

static BigDecimal readPrice(ResultSet resultSet) throws SQLException {
    return resultSet.getBigDecimal("price");
}
```

Đoạn code giả định SQL statement có placeholder theo đúng thứ tự tham số. Trong hệ thống thực tế, luôn dùng parameterized statement; không nối chuỗi giá trị vào SQL.

### 12.1. Khớp scale với schema

Nếu cột là `DECIMAL(19, 2)`, ứng dụng cần quyết định cách xử lý giá trị có nhiều hơn hai chữ số thập phân:

```java
BigDecimal input = new BigDecimal("12.345");

BigDecimal amountForStorage =
        input.setScale(2, RoundingMode.HALF_UP);
```

Một số hệ quản trị có quy tắc làm tròn hoặc từ chối khi chuyển vào cột. Đừng phụ thuộc vào hành vi ngầm của database; hãy xác định quy tắc trong tầng nghiệp vụ và bảo đảm schema tương ứng.

### 12.2. Không dùng kiểu FLOAT/DOUBLE cho số tiền cần chính xác

Nếu cột dữ liệu lưu giá trị tiền bằng kiểu dấu phẩy động gần đúng, việc đọc về `BigDecimal` không tự khôi phục được dữ liệu thập phân ban đầu. Cần chọn kiểu lưu trữ chính xác như `DECIMAL`/`NUMERIC` từ đầu nếu yêu cầu nghiệp vụ cần điều đó.

## 13. Cách thiết kế hàm và API với `BigDecimal`

### 13.1. Nhận và trả `BigDecimal` xuyên suốt

```java
static BigDecimal calculateDiscount(
        BigDecimal price,
        BigDecimal rate
) {
    return price.multiply(rate);
}
```

Nếu hệ thống đã dùng `BigDecimal`, hãy duy trì kiểu này qua các lớp dịch vụ và repository. Chuyển qua `double` rồi chuyển ngược lại có thể đưa sai số nhị phân vào chuỗi tính toán.

### 13.2. Kiểm tra null và giá trị âm theo nghiệp vụ

`BigDecimal` không tự quyết định một giá trị âm có hợp lệ hay không. Ví dụ, giá sản phẩm thường không âm nhưng khoản điều chỉnh hoặc hoàn tiền có thể có dấu âm.

```java
static BigDecimal requireNonNegative(BigDecimal value) {
    if (value == null) {
        throw new IllegalArgumentException("value is required");
    }
    if (value.signum() < 0) {
        throw new IllegalArgumentException("value must be non-negative");
    }
    return value;
}
```

`signum()` trả về:

- `-1` nếu giá trị âm.
- `0` nếu bằng 0.
- `1` nếu giá trị dương.

Hàm trên chỉ minh họa validation. Quy tắc cho từng loại dữ liệu cần theo miền nghiệp vụ.

### 13.3. Không dùng `doubleValue()` để so sánh chính xác

```java
BigDecimal amount = new BigDecimal("0.10");

// Không nên nếu mục tiêu là so sánh thập phân chính xác:
if (amount.doubleValue() == 0.10) {
    // ...
}
```

Chuyển sang `double` đưa dữ liệu trở lại mô hình gần đúng. Hãy dùng `compareTo`:

```java
if (amount.compareTo(new BigDecimal("0.10")) == 0) {
    // Giá trị số học bằng 0.10
}
```

### 13.4. Giữ quy tắc làm tròn ở một nơi có chủ ý

Thay vì để từng lớp tự làm tròn tùy ý, có thể định nghĩa quy tắc:

```java
static final int MONEY_SCALE = 2;
static final RoundingMode MONEY_ROUNDING = RoundingMode.HALF_UP;

static BigDecimal normalizeMoney(BigDecimal amount) {
    return amount.setScale(MONEY_SCALE, MONEY_ROUNDING);
}
```

Tên `MONEY_ROUNDING` ở đây chỉ là ví dụ. Một sản phẩm có thể có quy tắc khác theo đồng tiền, loại giao dịch, quốc gia, hợp đồng hoặc yêu cầu kế toán. Không nên mặc định mọi loại tiền đều có hai chữ số thập phân.

## 14. Khi nào không nên chọn `BigDecimal`?

`BigDecimal` giải quyết nhu cầu độ chính xác thập phân, nhưng có chi phí và giới hạn riêng:

- Đối tượng thường tốn bộ nhớ và chi phí xử lý lớn hơn kiểu primitive `double`.
- Phép toán cần tạo đối tượng mới do tính immutable.
- Phải chủ động quản lý scale, precision và rounding.
- Không có `NaN` hoặc vô cực như số dấu phẩy động; dữ liệu không hữu hạn cần mô hình riêng.
- Nếu miền dữ liệu chỉ cần số nguyên, `long` hoặc `int` đơn giản hơn.

### 14.1. Dùng số nguyên đơn vị nhỏ nhất trong trường hợp phù hợp

Một hệ thống chỉ xử lý số tiền theo đơn vị nhỏ nhất cố định có thể lưu `long`:

```java
long priceInCents = 1999;
long quantity = 3;
long totalInCents = priceInCents * quantity;

System.out.println(totalInCents); // 5997
```

Cách này có ưu điểm là nhanh và tránh sai số dấu phẩy động. Nhưng cần quản lý:

- Đơn vị lưu là cent, đồng, xu hay đơn vị nhỏ nhất khác.
- Tràn số khi nhân/cộng.
- Chuyển đổi tỷ giá và tỷ lệ thập phân.
- Quy tắc chia, làm tròn và đơn vị tiền khác nhau.

Khi cần tính toán tỷ lệ, lãi suất hoặc quy đổi với nhiều chữ số thập phân, `BigDecimal` thường linh hoạt hơn.

### 14.2. Dùng `double` trong mô hình gần đúng

Ví dụ tính khoảng cách, đồ họa hoặc mô phỏng:

```java
double distance = Math.sqrt(x * x + y * y);
```

Không cần đổi mọi phép tính này sang `BigDecimal` nếu yêu cầu là kết quả gần đúng theo mô hình số dấu phẩy động.

**Chọn kiểu dữ liệu theo ý nghĩa dữ liệu**, không theo suy nghĩ rằng một kiểu luôn tốt hơn kiểu còn lại.

## 15. Những lỗi thường gặp

### Lỗi 1. Khởi tạo từ double

```java
BigDecimal price = new BigDecimal(0.1);
```

Cách này lấy chính xác giá trị nhị phân của double. Với số thập phân nghiệp vụ, dùng:

```java
BigDecimal price = new BigDecimal("0.1");
```

### Lỗi 2. Quên gán lại kết quả phép toán

```java
BigDecimal total = new BigDecimal("10.00");
total.add(new BigDecimal("5.00")); // Kết quả bị bỏ qua
```

Sửa:

```java
total = total.add(new BigDecimal("5.00"));
```

### Lỗi 3. Dùng `equals` khi muốn so sánh số học

```java
new BigDecimal("1.0").equals(new BigDecimal("1.00")); // false
```

Dùng `compareTo(...) == 0` nếu khác biệt scale không quan trọng.

### Lỗi 4. Chia không chỉ định làm tròn

```java
BigDecimal.ONE.divide(new BigDecimal("3")); // ArithmeticException
```

Nếu nghiệp vụ chấp nhận giới hạn scale:

```java
BigDecimal.ONE.divide(new BigDecimal("3"), 4, RoundingMode.HALF_UP);
```

### Lỗi 5. Gọi `setScale` mà không lưu kết quả

```java
amount.setScale(2, RoundingMode.HALF_UP);
```

Phải lưu giá trị trả về vì `BigDecimal` immutable.

### Lỗi 6. Nhầm precision với scale

`precision` là số chữ số có nghĩa của unscaled value; `scale` xác định vị trí thập phân. `setScale(2)` không có nghĩa “giữ hai chữ số có nghĩa”.

### Lỗi 7. Làm tròn ở nhiều tầng không có chính sách

Một lớp làm tròn từng dòng, lớp khác làm tròn tổng, lớp giao diện lại định dạng thêm lần nữa có thể tạo chênh lệch. Hãy xác định rõ nơi và thời điểm làm tròn.

### Lỗi 8. Chuyển qua double giữa quá trình

`BigDecimal -> double -> BigDecimal` có thể đưa sai số nhị phân trở lại. Hãy giữ `BigDecimal` xuyên suốt đường tính toán nếu cần độ chính xác thập phân.

### Lỗi 9. Dùng scale mặc định của hệ thống để định dạng tiền

Không phải loại tiền nào cũng có hai chữ số thập phân. Quy tắc số chữ số phụ thuộc đơn vị tiền và nghiệp vụ. Đừng mặc định `setScale(2)` cho mọi giá trị tài chính.

## 16. Ví dụ thực hành tổng hợp

Bài toán: tính số tiền sau chiết khấu. Đầu vào gồm giá gốc, số lượng và tỷ lệ chiết khấu; kết quả cần hai chữ số thập phân theo quy tắc `HALF_UP` của ví dụ.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DiscountCalculator {

    private static final int MONEY_SCALE = 2;
    private static final RoundingMode ROUNDING = RoundingMode.HALF_UP;

    static BigDecimal calculate(
            String unitPriceText,
            long quantity,
            String discountRateText
    ) {
        BigDecimal unitPrice = new BigDecimal(unitPriceText);
        BigDecimal discountRate = new BigDecimal(discountRateText);
        BigDecimal count = BigDecimal.valueOf(quantity);

        if (unitPrice.signum() < 0 || discountRate.signum() < 0
                || discountRate.compareTo(BigDecimal.ONE) > 0
                || quantity < 0) {
            throw new IllegalArgumentException("Invalid input");
        }

        BigDecimal subtotal = unitPrice.multiply(count);
        BigDecimal discount = subtotal.multiply(discountRate);

        return subtotal.subtract(discount)
                .setScale(MONEY_SCALE, ROUNDING);
    }

    public static void main(String[] args) {
        BigDecimal result = calculate("19.99", 3, "0.10");
        System.out.println(result.toPlainString()); // 53.97
    }
}
```

Giải thích:

1. Giá đơn vị `19.99` được đọc trực tiếp từ chuỗi thập phân.
2. Số lượng `3` chuyển từ `long` sang `BigDecimal` bằng `valueOf`.
3. Subtotal là `59.97`.
4. Tỷ lệ giảm `0.10` nghĩa là 10%; discount là `5.997`.
5. Số tiền sau giảm là `53.973`.
6. Áp dụng `setScale(2, HALF_UP)` cho kết quả `53.97`.

Mã giả định đầu vào đã được kiểm tra cú pháp và chính sách làm tròn được phép dùng cho nghiệp vụ. Trong sản phẩm thực tế, cần kiểm tra giới hạn quantity, đơn giá, tỷ lệ và quy tắc tiền tệ theo domain.

## 17. Bài tập tự luyện

**Bài 1.** Kết quả của đoạn mã là gì?

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
System.out.println(a.add(b));
```

**Đáp án:** `0.3`. Hai toán hạng được tạo từ chuỗi thập phân chính xác.

**Bài 2.** Vì sao hai biểu thức sau khác nhau?

```java
new BigDecimal(0.1)
new BigDecimal("0.1")
```

**Đáp án:** Biểu thức đầu nhận giá trị double nhị phân đã gần đúng rồi biểu diễn chính xác giá trị đó. Biểu thức thứ hai phân tích trực tiếp số thập phân `0.1`.

**Bài 3.** Giá trị nào được in ra?

```java
BigDecimal amount = new BigDecimal("12.345");
amount.setScale(2, RoundingMode.HALF_UP);
System.out.println(amount);
```

**Đáp án:** `12.345`. `setScale` trả về một đối tượng mới; kết quả không được gán lại.

**Bài 4.** So sánh:

```java
BigDecimal a = new BigDecimal("5.0");
BigDecimal b = new BigDecimal("5.00");
```

**Đáp án:** `a.equals(b)` là `false`, nhưng `a.compareTo(b) == 0` là `true`.

**Bài 5.** Điều gì xảy ra?

```java
BigDecimal.ONE.divide(new BigDecimal("8"));
```

**Đáp án:** Phép chia có kết quả thập phân hữu hạn `0.125` nên phép chia chính xác có thể thành công mà không cần rounding mode.

**Bài 6.** Điều gì xảy ra?

```java
BigDecimal.ONE.divide(new BigDecimal("6"));
```

**Đáp án:** Kết quả thập phân vô hạn tuần hoàn; phép chia chính xác không có quy tắc làm tròn ném `ArithmeticException`.

**Bài 7.** Cần kiểm tra giá trị có thể biểu diễn chính xác với hai chữ số thập phân mà không làm tròn. Dùng gì?

**Đáp án:** `amount.setScale(2, RoundingMode.UNNECESSARY)`. Nếu cần làm tròn, Java ném `ArithmeticException`.

**Bài 8.** Một hệ thống tính tổng các khoản tiền bằng `double`, sau đó tạo `BigDecimal.valueOf(total)`. Cách này có đảm bảo chính xác nghiệp vụ không?

**Đáp án:** Không. Sai số có thể đã xuất hiện trong các phép tính `double` trước đó. Hãy tạo `BigDecimal` từ đầu vào thập phân ban đầu và giữ kiểu này trong suốt quá trình tính.

## 18. Ghi nhớ và tài liệu tham khảo chính thức

**Những nguyên tắc cần nhớ:**

1. Dùng `BigDecimal` khi cần số thập phân chính xác và kiểm soát được quy tắc làm tròn.
2. Ưu tiên `new BigDecimal("...")` cho đầu vào thập phân; dùng `BigDecimal.valueOf(long)` cho số nguyên.
3. Tránh `new BigDecimal(double)` khi mong muốn giá trị thập phân lý tưởng.
4. `BigDecimal` immutable; luôn sử dụng giá trị trả về từ `add`, `multiply`, `setScale` và các phương thức khác.
5. `equals` xét scale; `compareTo` so sánh giá trị số học.
6. `divide` không có rounding mode chỉ thành công khi thương có biểu diễn thập phân hữu hạn.
7. `scale` là số chữ số ở bên phải dấu thập phân; `precision` là số chữ số có nghĩa của unscaled value.
8. Quy tắc làm tròn phải đến từ yêu cầu nghiệp vụ; không tự chọn tùy tiện.
9. Giữ `BigDecimal` xuyên suốt tầng nhập liệu, nghiệp vụ và lưu trữ nếu cần độ chính xác.
10. Dùng `DECIMAL`/`NUMERIC` và JDBC `setBigDecimal`/`getBigDecimal` khi làm việc với dữ liệu thập phân chính xác trong cơ sở dữ liệu.

### Tài liệu chính thức

- [JDK 17 API — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): constructor, phép toán, scale, precision, rounding, equals và compareTo.
- [JDK 17 API — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): ý nghĩa các chế độ làm tròn.
- [JDK 17 API — MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): giới hạn precision và rounding mode cho phép toán.
- [JLS 17 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): đặc điểm kiểu số dấu phẩy động và giá trị biểu diễn.
- [JDK 17 API — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): các phương thức bind tham số JDBC, gồm `setBigDecimal`.
- [JDK 17 API — ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): đọc giá trị kiểu `BigDecimal` qua `getBigDecimal`.

**Nguyên tắc lựa chọn:** Nếu giá trị thập phân phải được giữ chính xác theo dữ liệu đầu vào và quy tắc nghiệp vụ, hãy dùng `BigDecimal` từ đầu đến cuối. Chọn scale và rounding mode có chủ ý, không chuyển qua `double` giữa đường, và dùng `compareTo` khi cần so sánh số học.
