# Vì sao `0.1` thường không được biểu diễn chính xác trong Java?

## 1. Hiện tượng: số trông đơn giản nhưng phép tính cho kết quả lạ

Trong Java, những phép tính quen thuộc sau có thể gây ngạc nhiên:

```java
double a = 0.1;
double b = 0.2;
double sum = a + b;

System.out.println(a);          // 0.1
System.out.println(sum);        // 0.30000000000000004
System.out.println(sum == 0.3); // false
```

Đây **không phải Java tính toán ngẫu nhiên**. Các kiểu `float` và `double` lưu số thực bằng **biểu diễn dấu phẩy động nhị phân hữu hạn**, thường theo chuẩn IEEE 754. Một số phân số thập phân, trong đó có `0.1`, **không có biểu diễn nhị phân hữu hạn**, nên phải được làm tròn thành giá trị biểu diễn được gần nhất.

Điểm quan trọng:

- `0.1` được viết chính xác theo **hệ thập phân**, nhưng không nhất thiết được lưu chính xác trong `double`.
- Lỗi xấp xỉ thường xuất hiện **ngay khi literal được chuyển thành giá trị dấu phẩy động**, trước cả phép cộng.
- Sau đó mỗi phép toán dấu phẩy động có thể cần làm tròn lần nữa. Vì vậy `0.1 + 0.2` không nhất thiết trùng mẫu bit với literal `0.3`.
- `System.out.println(0.1)` in `0.1` **không chứng minh bit lưu bên trong đúng bằng một phần mười toán học**.

Học cách phân biệt **giá trị toán học**, **giá trị nhị phân được lưu** và **chuỗi thập phân khi hiển thị** là chìa khóa để hiểu vấn đề.

## 2. Phân số trong hệ nhị phân khác phân số trong hệ thập phân

Trong hệ thập phân, mỗi chữ số sau dấu chấm ứng với lũy thừa âm của 10:

```text
0.1 (hệ 10) = 1 × 10^-1 = 1/10
0.25        = 2 × 10^-1 + 5 × 10^-2
            = 25/100 = 1/4
```

Trong hệ nhị phân, các chữ số sau dấu chấm tương ứng với lũy thừa âm của 2:

```text
0.1₂   = 1 × 2^-1 = 1/2  = 0.5₁₀
0.01₂  = 1 × 2^-2 = 1/4  = 0.25₁₀
0.001₂ = 1 × 2^-3 = 1/8  = 0.125₁₀
0.11₂  = 1/2 + 1/4       = 0.75₁₀
```

Một phân số hữu tỉ ở dạng tối giản `p/q` (với `q > 0`) có biểu diễn **nhị phân hữu hạn** khi và chỉ khi mẫu `q` là lũy thừa của 2, ví dụ `1`, `2`, `4`, `8`, `16`, ...

| Giá trị thập phân | Phân số tối giản | Có biểu diễn nhị phân hữu hạn? | Ví dụ biểu diễn |
| --- | --- | --- | --- |
| `0.5` | `1/2` | Có | `0.1₂` |
| `0.25` | `1/4` | Có | `0.01₂` |
| `0.125` | `1/8` | Có | `0.001₂` |
| `0.375` | `3/8` | Có | `0.011₂` |
| `0.1` | `1/10` | Không | Vô hạn tuần hoàn |
| `0.2` | `1/5` | Không | Vô hạn tuần hoàn |
| `0.3` | `3/10` | Không | Vô hạn tuần hoàn |

Tại sao `0.1` đặc biệt? Vì `1/10 = 1/(2 × 5)`. Mẫu số sau tối giản vẫn chứa **thừa số 5**, không thể biến thành lũy thừa thuần túy của 2. Do đó, không tồn tại **một dãy hữu hạn chữ số nhị phân** biểu diễn đúng `1/10`.

Quy tắc này là kiến thức về hệ cơ số, **không riêng Java**. Tương tự, `1/3` viết thành `0.33333...` vô hạn trong hệ thập phân; `1/10` viết thành một dãy vô hạn trong hệ nhị phân.

## 3. Biểu diễn nhị phân của `0.1` lặp vô hạn ra sao?

Nhân liên tiếp phần lẻ với 2 để lấy từng bit sau dấu chấm:

| Bước | Phần lẻ × 2 | Bit phần nguyên | Phần lẻ còn lại |
| --- | --- | ---: | --- |
| 1 | 0.1 × 2 = 0.2 | 0 | 0.2 |
| 2 | 0.2 × 2 = 0.4 | 0 | 0.4 |
| 3 | 0.4 × 2 = 0.8 | 0 | 0.8 |
| 4 | 0.8 × 2 = 1.6 | 1 | 0.6 |
| 5 | 0.6 × 2 = 1.2 | 1 | 0.2 |
| 6 | 0.2 × 2 = 0.4 | 0 | 0.4 |
| 7 | 0.4 × 2 = 0.8 | 0 | 0.8 |
| 8 | 0.8 × 2 = 1.6 | 1 | 0.6 |

Từ phần dư `0.2`, các bước lại lặp như trước. Vì thế:

```text
0.1₁₀ = 0.000110011001100110011001100110011...₂
        0.00011(0011)(0011)(0011)...₂
```

Đây là dãy **vô hạn**; `float` hoặc `double` không thể cất giữ vô số bit. Máy phải chọn một số nhị phân hữu hạn **gần `0.1` nhất** trong tập giá trị kiểu đó biểu diễn được.

Không nên hiểu rằng Java “cắt bỏ tùy tiện sau vài bit”. Biểu diễn dấu phẩy động sử dụng quy tắc làm tròn xác định; theo chế độ làm tròn mặc định, giá trị có thể biểu diễn gần nhất được chọn với quy tắc xử lý trường hợp hòa (*round to nearest, ties to even*).

## 4. `float` và `double` lưu bit như thế nào?

Trong Java, `float` tương ứng định dạng nhị phân 32 bit và `double` tương ứng định dạng nhị phân 64 bit. Với số hữu hạn chuẩn hóa (*normal*), giá trị được biểu diễn từ dấu, phần trị (*significand*) và số mũ cơ số 2.

| Thành phần | `float` / binary32 | `double` / binary64 |
| --- | ---: | ---: |
| Tổng số bit | 32 | 64 |
| Bit dấu | 1 | 1 |
| Bit trường số mũ | 8 | 11 |
| Bit phần phân số được lưu | 23 | 52 |
| Độ chính xác phần trị (kể cả bit `1` ẩn của số chuẩn hóa) | 24 bit | 53 bit |
| Chữ số thập phân có nghĩa gần đúng | 6–9 | 15–17 |

Lưu ý: con số **53 bit của `double`** không phải “53 chữ số thập phân”. Nó gồm 53 **chữ số nhị phân có nghĩa**. Số mũ quyết định độ lớn; số bit phần trị quyết định khả năng phân biệt các số gần nhau.

`double` có nhiều bit hơn `float`, nên xấp xỉ `0.1` **chính xác hơn**, nhưng **vẫn không bằng đúng `1/10`**.

### Giá trị `double` thực sự được lưu

Đối với literal `0.1` kiểu `double` trong Java:

```text
Dạng hexadecimal floating-point:
0x1.999999999999ap-4

Giá trị chính xác của mẫu bit đó:
3602879701896397 / 36028797018963968

Viết ở thập phân không làm tròn:
0.1000000000000000055511151231257827021181583404541015625
```

Phân số trên **lớn hơn `1/10` một chút**. Đây không phải “sai số xuất hiện vì `println`”; nó là giá trị số thật của mẫu bit đang lưu. Cách hiển thị mặc định thường ngắn hơn để dễ đọc.

Trong khi đó, literal `0.1f` kiểu `float` gần bằng:

```text
0.100000001490116119384765625
```

`float` có ít bit chính xác hơn, nên sai số biểu diễn có thể lớn hơn `double`.

## 5. Vì sao Java vẫn in `0.1` chứ không in cả dãy dài?

```java
double x = 0.1;
System.out.println(x);              // 0.1
System.out.println(Double.toHexString(x)); // 0x1.999999999999ap-4
```

`Double.toString` (được dùng khi `println` chuyển `double` thành chuỗi) chọn cách biểu diễn thập phân ngắn phù hợp với quy tắc định dạng của Java, có thể chuyển ngược về **cùng giá trị `double`**. Chuỗi `"0.1"` đủ để tái tạo mẫu bit của `double` đã làm tròn, nên không cần in toàn bộ chữ số của phân số nhị phân đó khi đổi chính xác sang cơ số 10.

Ba khái niệm phải tách riêng:

1. **Literal trong mã nguồn:** `0.1` là một ký hiệu thập phân hướng đến giá trị toán học một phần mười.
2. **Giá trị dấu phẩy động được lưu:** số nhị phân 64 bit gần nhất với một phần mười, nhưng không bằng đúng.
3. **Chuỗi khi in:** thường là chuỗi ngắn `"0.1"` để con người đọc và để chuyển ngược về đúng cùng mẫu bit.

Muốn nhìn thấy số thập phân đầy đủ tương ứng với giá trị được lưu, có thể dùng `new BigDecimal(x).toPlainString()`. Nhưng hành động này chỉ **phơi bày xấp xỉ nhị phân đã có**, không sửa nó thành số `0.1` toán học.

## 6. Vì sao `0.1 + 0.2 == 0.3` trả về `false`?

```java
System.out.println(0.1 + 0.2);      // 0.30000000000000004
System.out.println(0.3);            // 0.3
System.out.println(0.1 + 0.2 == 0.3); // false
```

Có **hai loại làm tròn** đáng chú ý:

1. Các literal `0.1`, `0.2`, `0.3` đều được chuyển thành các số nhị phân gần giá trị thập phân mong muốn.
2. Phép cộng hai giá trị `double` đã biểu diễn cũng tạo ra một kết quả được làm tròn thành mẫu bit `double` gần nhất.

Kết quả lưu của `0.1 + 0.2` là giá trị `double` **kế cận lớn hơn** giá trị `double` của literal `0.3`. Toán tử `==` so sánh **hai giá trị dấu phẩy động**, không kiểm tra xem hai biểu thức có “bằng nhau theo ý định thập phân” hay không.

Vì vậy không nên nói “Java hiểu rằng `0.1 + 0.2` là một số toán học khác `0.3`”. Phép cộng toán học vẫn chính xác bằng `0.3`; chính **cách xấp xỉ và làm tròn trong tập số biểu diễn được** khiến kết quả máy tính khác.

Một cách diễn đạt hữu ích:

```text
Giá trị lý tưởng: 0.1 + 0.2 = 0.3
Giá trị double:  fl(fl(0.1) + fl(0.2)) ≠ fl(0.3)
```

Trong đó `fl(x)` tượng trưng cho việc làm tròn số toán học thành giá trị `double` có thể biểu diễn.

## 7. Khi nào một số có thể được lưu chính xác?

**Không phải tất cả các số thập phân đều bị sai lệch.** Các phân số có mẫu tối giản là lũy thừa của 2 có thể có biểu diễn nhị phân hữu hạn, ví dụ:

```java
System.out.println(0.5 + 0.25 == 0.75); // true
System.out.println(0.125 + 0.25 == 0.375); // true
```

Các giá trị này đều có biểu diễn nhị phân ngắn và các phép tính ví dụ cũng cho kết quả biểu diễn chính xác. Tuy nhiên, **“biểu diễn nhị phân hữu hạn” chưa đủ đảm bảo mọi giá trị đều được lưu chính xác ở độ chính xác cố định**: nếu cần nhiều bit phần trị hơn 24 hoặc 53, số vẫn có thể làm tròn.

Ví dụ với số nguyên:

```java
long a = 9_007_199_254_740_992L; // 2^53.
long b = 9_007_199_254_740_993L; // 2^53 + 1.

System.out.println((double) a == (double) b); // true
```

Cả hai đều là **số nguyên** và dĩ nhiên có biểu diễn nhị phân hữu hạn, nhưng `double` không phân biệt được chúng tại độ lớn này: `2^53 + 1` làm tròn về `2^53`. Điều này cho thấy câu hỏi “số có viết hữu hạn trong hệ 2 không?” khác với câu hỏi “định dạng 64 bit có **đủ bit chính xác** cho số đó không?”.

**Quy tắc tổng quát:** để được biểu diễn chính xác trong một kiểu dấu phẩy động, số phải vừa có cấu trúc phù hợp với cơ số 2, vừa có phần trị và số mũ nằm trong giới hạn định dạng.

## 8. Tác hại thực tế: so sánh, tích lũy và ranh giới điều kiện

### 8.1. So sánh bằng tuyệt đối với kết quả phép tính

```java
double total = 0.1 + 0.2;

if (total == 0.3) {
    System.out.println("equal");
} else {
    System.out.println("different");
}
// Nhánh "different" được chạy.
```

Dùng `==` là hoàn toàn thích hợp trong những tình huống có **chủ ý so sánh mẫu giá trị** (chẳng hạn so sánh với chính cùng một giá trị đã lưu, hoặc đối chiếu những số nguyên nhỏ chuyển chính xác). Nhưng với các kết quả tính toán dấu phẩy động, `==` thường không thể thay cho khái niệm “gần nhau đủ để coi là bằng nhau” của bài toán.

Một kỹ thuật so sánh gần đúng:

```java
double a = 0.1 + 0.2;
double b = 0.3;
double tolerance = 1e-12;

boolean nearlyEqual = Math.abs(a - b) <= tolerance;
System.out.println(nearlyEqual); // true
```

**Không tồn tại một `tolerance` cố định phù hợp mọi trường hợp.** Ngưỡng phải đến từ đơn vị, miền giá trị và sai số được chấp nhận của bài toán. Với số rất lớn hoặc rất nhỏ, có thể cần ngưỡng tuyệt đối kết hợp ngưỡng tương đối; với `NaN`, vô cực và giá trị gần 0, phải xác định thêm cách xử lý riêng.

Nếu vấn đề yêu cầu so sánh **đúng từng chữ số thập phân** (ví dụ số tiền), việc chỉ tăng `tolerance` không đảm bảo đúng nghiệp vụ. Khi đó nên chọn cách biểu diễn thập phân chính xác từ đầu.

### 8.2. Cộng nhiều lần và sai số tích lũy

```java
double total = 0.0;
for (int i = 0; i < 10; i++) {
    total += 0.1;
}
System.out.println(total); // 0.9999999999999999
```

Vì mỗi phép cộng có thể làm tròn, lỗi nhỏ có thể tích lũy hoặc triệt tiêu tùy dữ liệu và thứ tự phép tính. Không nên suy luận rằng phép lặp cộng `0.1` mười lần **luôn** bằng chính xác `1.0` dưới kiểu `double`.

Với số lượng lớn giá trị thực trong khoa học hoặc thống kê, có thể cân nhắc thuật toán tổng ổn định hơn (ví dụ compensated summation/Kahan hoặc API tổng phù hợp), nhưng các thuật toán đó **giảm sai số**, không thay đổi sự thật rằng `0.1` không biểu diễn chính xác trong nhị phân hữu hạn.

### 8.3. Giới hạn và điều kiện vòng lặp

```java
double x = 0.0;
while (x < 1.0) {
    x += 0.1;
}
```

Ví dụ này chỉ minh họa bẫy thiết kế: lặp bằng cách cộng bước dấu phẩy động có thể khiến số vòng không như tính toán thập phân lý tưởng. Thường nên **lặp bằng biến đếm nguyên** và tính giá trị tương ứng:

```java
for (int i = 0; i <= 10; i++) {
    double x = i / 10.0;
    // Dùng x trong bài toán của bạn.
}
```

Cách lặp bằng bộ đếm nguyên giúp kiểm soát **số lần lặp**; nó không làm cho mọi `i / 10.0` trở thành thập phân biểu diễn chính xác.

## 9. Muốn tính chính xác theo hệ thập phân: dùng `BigDecimal` đúng cách

Đối với tiền, thuế, lãi suất với quy tắc làm tròn thập phân, hoặc dữ liệu cần đúng các chữ số thập phân, Java cung cấp `java.math.BigDecimal`. Nó biểu diễn giá trị bằng một **số nguyên không chia tỷ lệ (*unscaled value*) và một *scale* thập phân**, nên có thể biểu diễn **chính xác** `0.1`, `0.2` và `0.3` khi chúng được tạo từ đầu dưới dạng thập phân.

### Tạo từ chuỗi thập phân

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal expected = new BigDecimal("0.3");

BigDecimal sum = a.add(b);
System.out.println(sum);                   // 0.3
System.out.println(sum.equals(expected));  // true
```

Đây là phép cộng thập phân chính xác trên những giá trị đầu vào đã chọn. `BigDecimal` là đối tượng **bất biến**; phương thức `add` trả về đối tượng kết quả mới.

### Tránh bẫy `new BigDecimal(0.1)`

```java
BigDecimal fromLiteral = new BigDecimal(0.1);
BigDecimal fromString = new BigDecimal("0.1");

System.out.println(fromLiteral.equals(fromString)); // false
System.out.println(fromLiteral.toPlainString());
// 0.1000000000000000055511151231257827021181583404541015625
```

Constructor `new BigDecimal(double)` lưu **chính xác giá trị `double` đã được làm tròn**, không phải giá trị thập phân “ban đầu trong đầu người viết code”. Vì vậy nó phơi bày dãy số thập phân dài từ biểu diễn nhị phân.

Dùng `new BigDecimal("0.1")` khi đầu vào xác định theo chữ số thập phân. Nếu bắt buộc chuyển một `double` sang `BigDecimal` theo chuỗi thập phân ngắn thể hiện giá trị `double`, dùng `BigDecimal.valueOf(0.1)`:

```java
System.out.println(BigDecimal.valueOf(0.1)); // 0.1
```

Phân biệt: `BigDecimal.valueOf(double)` dựa trên cách chuyển `double` thành chuỗi thập phân. Nó **không thể khôi phục thông tin đầu vào hoặc sai số đã mất** nếu bạn thực hiện phép tính `double` trước khi chuyển:

```java
System.out.println(BigDecimal.valueOf(0.1 + 0.2)); // 0.30000000000000004
```

Do đó, nếu muốn tính toán thập phân chính xác, hãy tạo `BigDecimal` **trước khi tính**, thường từ chuỗi đã được kiểm tra hoặc từ số nguyên với scale rõ ràng.

### `BigDecimal` cũng có quy tắc riêng

- `BigDecimal("0.1").add(BigDecimal("0.2"))` theo cách viết minh họa không phải cú pháp Java hợp lệ: phải dùng `new BigDecimal("0.1")` cho từng toán hạng.
- Không dùng toán tử `+`, `-`, `*` trên các đối tượng `BigDecimal`; dùng `add`, `subtract`, `multiply`.
- Chia thập phân có thể tạo khai triển vô hạn: ví dụ `BigDecimal.ONE.divide(new BigDecimal("3"))` có thể ném `ArithmeticException` nếu không chỉ định ngữ cảnh làm tròn. Khi cần, sử dụng `MathContext` hoặc `divide(divisor, scale, RoundingMode)`.
- `equals` trên `BigDecimal` xét cả **giá trị và scale**: `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là `false`; `compareTo` cho kết quả `0` nếu chỉ cần so sánh giá trị số.

**Lưu ý thiết kế:** `BigDecimal` phù hợp với thập phân chính xác nhưng có chi phí đối tượng/tính toán và cần quy tắc scale/rounding rõ ràng. Với ứng dụng nhúng, tài chính hoặc tiền tệ cố định hai chữ số, **số nguyên theo đơn vị nhỏ nhất** (ví dụ cents) cũng là lựa chọn tốt nếu đã quy định miền giá trị và tránh tràn số.

## 10. Đừng nhầm với những vấn đề khác của `float`/`double`

Số thực dấu phẩy động còn có `NaN`, `Infinity`, `-Infinity`, số dưới chuẩn (*subnormal*), và hai mẫu bit `+0.0`/`-0.0`. Các khái niệm này quan trọng nhưng **không phải nguyên nhân trực tiếp** của hiện tượng `0.1 + 0.2`.

Đối với lỗi biểu diễn `0.1`, hãy ghi nhớ sự khác nhau giữa:

- **Sai số biểu diễn:** literal `0.1` không có biểu diễn nhị phân hữu hạn, nên kiểu dấu phẩy động lưu giá trị gần nhất.
- **Sai số làm tròn phép toán:** khi cộng, nhân, chia, kết quả toán học cũng có thể không biểu diễn được và cần làm tròn.
- **Sai số chuyển kiểu:** khi chuyển `double → float` hoặc số nguyên lớn sang kiểu dấu phẩy động, có thể mất thêm độ chính xác.
- **Quy tắc in ra chuỗi:** `println` thường chọn chuỗi ngắn có thể chuyển ngược đúng, không phải in toàn bộ giá trị thập phân chính xác của các bit.

Việc đổi `float` sang `double` **sau khi giá trị đã được làm tròn** cũng không tự khôi phục giá trị gốc:

```java
float a = 0.1f;
double promoted = a;
System.out.println(promoted); // 0.10000000149011612
```

Chuyển đổi mở rộng giữ lại **giá trị `float` thực sự đã lưu**. Nó không thay thế bằng giá trị `double` gần `0.1` nhất.

## 11. Ví dụ Java 17+ đầy đủ, chạy được

Tạo tệp **`WhyPointOneIsApproximate.java`**:

```java
import java.math.BigDecimal;

public class WhyPointOneIsApproximate {
    public static void main(String[] args) {
        double oneTenth = 0.1;
        double sum = 0.1 + 0.2;

        System.out.println("0.1 printed = " + oneTenth);
        System.out.println("0.1 hex = " + Double.toHexString(oneTenth));
        System.out.println("0.1 exact decimal = "
                + new BigDecimal(oneTenth).toPlainString());
        System.out.println("0.1 + 0.2 = " + sum);
        System.out.println("sum == 0.3 = " + (sum == 0.3));
        System.out.println("near 0.3 = "
                + (Math.abs(sum - 0.3) < 1e-12));

        float asFloat = 0.1f;
        double expandedFloat = asFloat;
        System.out.println("float 0.1 widened = " + expandedFloat);

        double total = 0.0;
        for (int i = 0; i < 10; i++) {
            total += 0.1;
        }
        System.out.println("0.1 added ten times = " + total);

        BigDecimal decimalSum = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("BigDecimal sum = " + decimalSum);
        System.out.println("BigDecimal.valueOf(0.1) = "
                + BigDecimal.valueOf(0.1));
        System.out.println("BigDecimal.valueOf(double sum) = "
                + BigDecimal.valueOf(sum));

        System.out.println("exact binary double equals decimal BigDecimal = "
                + new BigDecimal(0.1).equals(new BigDecimal("0.1")));

        System.out.println("1.0 equals 1.00 with BigDecimal = "
                + new BigDecimal("1.0").equals(new BigDecimal("1.00")));
        System.out.println("1.0 compares numerically to 1.00 = "
                + new BigDecimal("1.0").compareTo(new BigDecimal("1.00")));
    }
}
```

Biên dịch và chạy:

```bash
javac WhyPointOneIsApproximate.java
java WhyPointOneIsApproximate
```

Kết quả:

```text
0.1 printed = 0.1
0.1 hex = 0x1.999999999999ap-4
0.1 exact decimal = 0.1000000000000000055511151231257827021181583404541015625
0.1 + 0.2 = 0.30000000000000004
sum == 0.3 = false
near 0.3 = true
float 0.1 widened = 0.10000000149011612
0.1 added ten times = 0.9999999999999999
BigDecimal sum = 0.3
BigDecimal.valueOf(0.1) = 0.1
BigDecimal.valueOf(double sum) = 0.30000000000000004
exact binary double equals decimal BigDecimal = false
1.0 equals 1.00 with BigDecimal = false
1.0 compares numerically to 1.00 = 0
```

Ví dụ trên kiểm tra ba tầng khác nhau: **giá trị lưu**, **hành vi phép toán** và **cách biểu diễn kết quả thành chuỗi**. Đặc biệt, `new BigDecimal(0.1)` và `new BigDecimal("0.1")` khác nhau vì chúng được tạo từ **hai giá trị đầu vào khác bản chất**.

## 12. Lỗi phổ biến và cách suy nghĩ đúng

| Quan niệm chưa đúng | Giải thích đúng |
| --- | --- |
| “Máy lưu số 0.1 chính xác, chỉ có phép cộng gây lỗi.” | Literal `0.1` đã được làm tròn khi chuyển thành `float`/`double`. |
| “`println(0.1)` ra 0.1 nên giá trị lưu phải đúng một phần mười.” | Chuỗi hiển thị ngắn không phải bản khai triển thập phân đầy đủ của các bit. |
| “`double` có 64 bit nên chứa chính xác mọi phân số thập phân.” | Số bit là hữu hạn và dùng cơ số 2; `1/10` có khai triển nhị phân vô hạn. |
| “Tăng từ `float` sang `double` sẽ xóa mọi sai số.” | `double` có xấp xỉ tốt hơn; dữ liệu `float` đã làm tròn không tự trở lại giá trị gốc. |
| “Số thập phân nào cũng không biểu diễn chính xác.” | `0.5`, `0.25`, `0.125` có biểu diễn nhị phân hữu hạn và thường được lưu chính xác khi đủ miền/độ chính xác. |
| “`0.1 + 0.2 == 0.3` luôn phải true vì toán học đúng.” | Biểu thức Java thực hiện phép tính trên các giá trị `double` xấp xỉ rồi so sánh. |
| “Dùng `new BigDecimal(0.1)` sẽ có số thập phân chính xác 0.1.” | Nó giữ chính xác giá trị `double` đã xấp xỉ; dùng chuỗi `"0.1"` cho dữ liệu thập phân. |
| “Cứ tăng epsilon thật lớn thì mọi phép so sánh sẽ đúng.” | Ngưỡng lớn có thể coi các giá trị thực sự khác nhau là bằng nhau; phải dựa trên độ chính xác nghiệp vụ. |
| “`BigDecimal` không cần nghĩ đến làm tròn.” | Các phép chia thập phân vô hạn vẫn cần lựa chọn `MathContext`/`RoundingMode`. |

**Ghi nhớ:** `0.1 = 1/10` không có biểu diễn nhị phân hữu hạn vì mẫu tối giản chứa thừa số 5. `float` và `double` chỉ lưu được **xấp xỉ gần nhất** trong số bit hữu hạn; phép tính tiếp theo có thể làm tròn lần nữa. Dùng `double` khi bài toán chấp nhận sai số số thực và quản lý so sánh phù hợp; dùng `BigDecimal` **tạo từ chuỗi hoặc dữ liệu thập phân được kiểm soát** khi phải giữ giá trị thập phân chính xác.

**Tài liệu tham khảo:** [Java Language Specification §4.2.3 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3); [JLS §15.4 — FP-strict Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.4); [Java SE 21 Double API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html); [Java SE 21 BigDecimal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).
