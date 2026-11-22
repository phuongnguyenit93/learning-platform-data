# `BigDecimal`: Precision khác Scale trong Java

## 1. Hiểu đúng hai thuộc tính quan trọng nhất

Trong Java, `java.math.BigDecimal` biểu diễn số thập phân **chính xác theo hệ cơ số 10** bằng một số nguyên không giới hạn độ dài cố định (*unscaled value*) và một số nguyên `scale`. `BigDecimal` không tự đồng nghĩa với “có vô hạn độ chính xác trong mọi phép chia”: cách làm tròn và độ chính xác kết quả phải được kiểm soát khi phép tính không có biểu diễn thập phân hữu hạn hoặc khi ứng dụng quy định số chữ số.

Hai khái niệm rất dễ bị nhầm:

- **Precision (`precision()`):** số chữ số thập phân trong giá trị nguyên không scale, tính từ chữ số khác 0 đầu tiên; với giá trị nguyên không scale bằng 0, precision được định nghĩa là **1**.
- **Scale (`scale()`):** số mũ thập phân dùng để đặt dấu chấm theo quy tắc `unscaledValue × 10^(-scale)`. `scale` có thể **dương, bằng 0 hoặc âm**. Với cách viết decimal thông thường không có ký hiệu số mũ, scale dương thường tương ứng với số chữ số sau dấu thập phân được giữ trong biểu diễn.

Ví dụ:

```java
BigDecimal amount = new BigDecimal("123.4500");

System.out.println(amount.precision());     // 7
System.out.println(amount.scale());         // 4
System.out.println(amount.unscaledValue()); // 1234500
```

Số `123.4500` có bảy chữ số có ý nghĩa trong phần nguyên chưa scale: `1`, `2`, `3`, `4`, `5`, `0`, `0`; dấu thập phân đứng trước bốn chữ số cuối, nên `scale = 4`.

**Điểm nhớ:** `precision` không phải “số chữ số sau dấu phẩy”; `scale` không phải “độ chính xác tổng thể”. Chúng mô tả **hai thuộc tính khác nhau** của một giá trị `BigDecimal`.

## 2. Mô hình toán học: `unscaledValue × 10^(-scale)`

Về mặt khái niệm, một `BigDecimal` mang:

\[
\text{value}=\text{unscaledValue}\times 10^{-\text{scale}}.
\]

Ở đây `unscaledValue()` trả `BigInteger`; `scale()` trả `int`. Mô hình decimal tách riêng **hệ số nguyên có dấu** và **vị trí dấu thập phân**.

Ví dụ:

| Cách tạo | Unscaled value | Scale | Giá trị decimal |
| --- | ---: | ---: | --- |
| `new BigDecimal("123.4500")` | `1234500` | `4` | `123.4500` |
| `new BigDecimal("0.0012300")` | `12300` | `7` | `0.0012300` |
| `new BigDecimal("1000")` | `1000` | `0` | `1000` |
| `new BigDecimal("1E+3")` | `1` | `-3` | `1000` |
| `new BigDecimal("1.20E+3")` | `120` | `-1` | `1200` |
| `new BigDecimal("0.000")` | `0` | `3` | `0.000` |

Ví dụ `new BigDecimal("1E+3")`:

\[
1\times10^{-(-3)}=1\times10^3=1000.
\]

Do đó, scale âm **không phải lỗi** và cũng không có nghĩa số âm: nó biểu thị hệ số nguyên cần được nhân với một lũy thừa dương của 10.

### `precision()` đếm như thế nào?

Precision thường là số chữ số decimal của **trị tuyệt đối unscaled value**, bỏ qua các chữ số 0 vô nghĩa ở đầu. Với `1234500`, precision bằng 7; với `12300`, precision bằng 5. Các số 0 ở cuối **vẫn được tính** nếu tồn tại trong unscaled representation.

Đối với `0`, Java quy định precision là 1, không phải 0:

```java
System.out.println(new BigDecimal("0").precision());     // 1
System.out.println(new BigDecimal("0.000").precision()); // 1
```

Dù biểu diễn `"0.000"` có ba chữ số thập phân phía sau dấu chấm, unscaled value bằng 0 và precision vẫn bằng 1. Không lấy số chữ số trong chuỗi ban đầu để suy ra `precision()` một cách máy móc.

## 3. Các ví dụ đối chiếu Precision và Scale

Hãy đọc đồng thời `precision()`, `scale()` và `unscaledValue()` thay vì dựa vào cách số được in trên màn hình.

| Chuỗi đầu vào | `precision()` | `scale()` | `unscaledValue()` | Giải thích |
| --- | ---: | ---: | ---: | --- |
| `"123.4500"` | 7 | 4 | 1234500 | Hai số 0 cuối được giữ trong unscaled |
| `"0.0012300"` | 5 | 7 | 12300 | Các số 0 trước chữ số 1 không tăng precision |
| `"1000"` | 4 | 0 | 1000 | Bốn chữ số có nghĩa theo biểu diễn |
| `"1E+3"` | 1 | -3 | 1 | Cùng giá trị 1000, scale âm |
| `"1.20E+3"` | 3 | -1 | 120 | Cùng giá trị 1200, ba chữ số unscaled |
| `"0"` | 1 | 0 | 0 | Precision của zero là 1 |
| `"0.00"` | 1 | 2 | 0 | Scale giữ hai chữ số decimal của biểu diễn |
| `"-0.000"` | 1 | 3 | 0 | `BigDecimal` không có số âm 0 tách biệt |

Mã Java để tự khảo sát (đặt bên trong một phương thức hoặc trong JShell):

```java
for (String text : new String[] {
        "123.4500", "0.0012300", "1000",
        "1E+3", "1.20E+3", "0", "0.00"
}) {
    BigDecimal x = new BigDecimal(text);
    System.out.printf(
            "%s -> unscaled=%s, precision=%d, scale=%d%n",
            text, x.unscaledValue(), x.precision(), x.scale());
}
```

`BigDecimal` ghi nhớ giá trị và scale, **không ghi nhớ nguyên xi mọi ký tự chuỗi đầu vào**. Ví dụ `"1.2300E+4"` tạo giá trị `12300` có `scale = 0` và `precision = 5`; cách viết chuỗi nguồn không nhất thiết được giữ để phát lại cùng cú pháp.

### Vì sao precision có thể nhỏ hơn số chữ số hiển thị?

Chuỗi `"0.0012300"` có nhiều ký tự và nhiều số 0 trước chữ số khác 0 đầu tiên. `precision()` không đếm các số 0 dẫn đầu của phần trị decimal. Nó đếm các chữ số của `unscaledValue=12300`, nên trả 5, trong khi `scale=7`.

Với cách viết số mũ, `"1E+3"` có `precision=1` nhưng in dạng decimal đầy đủ là `"1000"` gồm bốn ký tự chữ số. Precision không phải độ dài của `toPlainString()`.

## 4. Hai giá trị bằng nhau nhưng precision và scale khác nhau

`BigDecimal` phân biệt **bằng nhau về giá trị số học** và **bằng nhau theo biểu diễn có scale**.

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.compareTo(b)); // 0
System.out.println(a.equals(b));    // false
```

Cả hai đều biểu diễn số toán học 2, nhưng:

| Biến | Unscaled | Precision | Scale |
| --- | ---: | ---: | ---: |
| `a = "2.0"` | 20 | 2 | 1 |
| `b = "2.00"` | 200 | 3 | 2 |

`compareTo` cho `0` vì hai **giá trị số học** bằng nhau. `equals` trả `false` vì `BigDecimal.equals` yêu cầu cùng giá trị và cùng scale (nên cũng cần có unscaled tương ứng).

Điều này khác `BigInteger`, nơi `compareTo()==0` và `equals` nhất quán với nhau về giá trị.

### Hậu quả với `HashSet` và `TreeSet`

```java
Set<BigDecimal> hash = new HashSet<>();
hash.add(new BigDecimal("2.0"));
hash.add(new BigDecimal("2.00"));

System.out.println(hash.size()); // 2
```

`HashSet` dùng `equals`/`hashCode`, nên nhận hai đối tượng có scale khác nhau làm phần tử khác nhau.

```java
Set<BigDecimal> tree = new TreeSet<>();
tree.add(new BigDecimal("2.0"));
tree.add(new BigDecimal("2.00"));

System.out.println(tree.size()); // 1
```

`TreeSet` dùng thứ tự tự nhiên thông qua `compareTo`; hai số có giá trị toán học bằng nhau được xem là cùng khóa theo thứ tự đó. Không dùng `BigDecimal` làm khóa collection mà chưa quyết định nghiệp vụ muốn phân biệt scale hay chỉ phân biệt giá trị.

### Không dùng `==` để so hai đối tượng BigDecimal

`==` giữa hai tham chiếu `BigDecimal` chỉ so identity, không phải giá trị số. Dùng `compareTo(...) == 0` để kiểm tra cùng giá trị **không phân biệt scale**, hoặc `equals` nếu scale cũng phải khớp. `BigDecimal.ZERO`, `BigDecimal.ONE`, `BigDecimal.TEN` là các hằng tiện ích chứ không biến `BigDecimal` thành primitive.

## 5. `setScale` thay đổi vị trí thập phân; `MathContext` giới hạn precision

Hai API này phục vụ hai mục đích khác nhau.

### 5.1. `setScale(int, RoundingMode)`

`setScale` yêu cầu **scale mục tiêu**:

```java
BigDecimal x = new BigDecimal("123.4500");

BigDecimal y = x.setScale(2, RoundingMode.UNNECESSARY);
BigDecimal z = x.setScale(6);

System.out.println(y); // 123.45
System.out.println(z); // 123.450000
```

Kết quả:

| Giá trị | Precision | Scale |
| --- | ---: | ---: |
| `x = 123.4500` | 7 | 4 |
| `y = 123.45` | 5 | 2 |
| `z = 123.450000` | 9 | 6 |

`setScale(6)` thêm các số 0 cuối cho phù hợp biểu diễn; **giá trị toán học không đổi**. Giảm scale có thể cần bỏ chữ số có ý nghĩa; khi đó phải chọn `RoundingMode` hoặc chấp nhận `ArithmeticException` nếu dùng chế độ `UNNECESSARY`.

Ví dụ:

```java
BigDecimal price = new BigDecimal("12.345");

System.out.println(price.setScale(2, RoundingMode.HALF_UP)); // 12.35
// price.setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException: sẽ phải làm tròn
```

Từ Java 17, còn overload `setScale(int)` mặc định yêu cầu không được mất thông tin do làm tròn. Với thao tác giảm scale có thể mất chữ số, nên **truyền rõ `RoundingMode`** theo chính sách nghiệp vụ.

`setScale` không phải “đặt tổng số chữ số có nghĩa”; nó quy định **số mũ thập phân của biểu diễn**. Ở scale âm, bước làm tròn tương ứng hàng chục, hàng trăm... chứ không còn là giữ các chữ số sau dấu thập phân.

### 5.2. `MathContext` giới hạn số chữ số có nghĩa

`MathContext` cấu hình **precision tối đa của kết quả** và cách làm tròn dùng trong các phép tính có nhận context:

```java
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);
BigDecimal result = new BigDecimal("123.4500").round(mc);

System.out.println(result);             // 123
System.out.println(result.precision()); // 3
System.out.println(result.scale());     // 0
```

Ở đây `MathContext(3, HALF_UP)` có nghĩa dùng **tối đa ba chữ số có nghĩa**, **không phải** ba chữ số sau dấu thập phân. Vì vậy `123.4500` làm tròn thành `123` với `scale=0`, chứ không phải `123.450`.

Đối chiếu:

```java
BigDecimal x = new BigDecimal("123.4500");
System.out.println(x.setScale(3, RoundingMode.HALF_UP)); // 123.450
System.out.println(x.round(new MathContext(3, RoundingMode.HALF_UP))); // 123
```

Hai kết quả khác nhau vì câu hỏi khác nhau:

- `setScale(3, ...)` → muốn biểu diễn **ba vị trí thập phân**.
- `round(MathContext(3, ...))` → muốn kết quả có **tối đa ba chữ số có nghĩa**.

Không thay một cái bằng cái kia trong tính tiền, tính giá, đo lường hoặc số liệu khoa học khi hợp đồng nói rõ yêu cầu.

### 5.3. Precision 0 của `MathContext` không phải precision 0 của BigDecimal

`MathContext.UNLIMITED.getPrecision()` trả `0`: trong **ngữ cảnh tính toán**, precision 0 là **không giới hạn precision theo context**.

```java
System.out.println(MathContext.UNLIMITED.getPrecision()); // 0
System.out.println(BigDecimal.ZERO.precision());           // 1
```

Điều đó **không** có nghĩa có một số `BigDecimal` hợp lệ với `precision() == 0` vì bằng 0. Hai API dùng số 0 với **ý nghĩa khác nhau**.

Một phép chia như `1 / 3` không có biểu diễn thập phân hữu hạn: ngay cả khi không giới hạn precision, phép chia chính xác không thể kết thúc trong số chữ số hữu hạn. Nó sẽ cần quy tắc làm tròn hoặc ném ngoại lệ; “unlimited” không biến số thập phân vô hạn thành dữ liệu lưu hữu hạn.

## 6. Rounding có thể đổi cả precision lẫn scale

Làm tròn theo số chữ số có nghĩa có thể phát sinh **carry**, làm thay đổi số mũ và scale theo cách khó đoán nếu chỉ đếm chữ số từ chuỗi.

```java
BigDecimal x = new BigDecimal("999.9");
BigDecimal rounded = x.round(new MathContext(3, RoundingMode.HALF_UP));

System.out.println(rounded);             // 1.00E+3
System.out.println(rounded.precision()); // 3
System.out.println(rounded.scale());     // -1
```

Giá trị kết quả toán học là 1000, nhưng biểu diễn là `unscaled=100`, `scale=-1`, precision 3. Nếu chuyển thành `"1000"` để in thì có bốn ký tự chữ số, **không làm precision tự thành 4**.

Ví dụ thứ hai:

```java
BigDecimal x = new BigDecimal("0.0012345");
BigDecimal y = x.round(new MathContext(3, RoundingMode.HALF_UP));

System.out.println(y); // 0.00123
```

Ở đây ba chữ số có nghĩa là `1`, `2`, `3` dù chuỗi hiển thị chứa nhiều số 0 ở đầu; `scale` của kết quả là 5.

### RoundingMode quyết định điều gì?

`RoundingMode.HALF_UP` làm tròn phần nửa theo hướng tăng độ lớn (xa 0); `HALF_EVEN` chọn chữ số chẵn khi đúng điểm giữa, thường dùng trong phép làm tròn giảm thiên lệch tích lũy; `DOWN` bỏ phần bị loại về phía 0; `UNNECESSARY` yêu cầu không cần làm tròn.

Ví dụ với số dương:

```java
BigDecimal x = new BigDecimal("1.235");
System.out.println(x.setScale(2, RoundingMode.HALF_UP));   // 1.24
System.out.println(x.setScale(2, RoundingMode.HALF_EVEN)); // 1.24
```

Hai chế độ trùng nhau trong ví dụ vì chữ số cuối được giữ là `3` trước dấu nửa? Hãy xem chính xác quy tắc: khi làm tròn `1.235` còn hai chữ số lẻ, chữ số bị loại đầu tiên là `5`, chữ số giữ cuối là `3` (lẻ), vì vậy `HALF_EVEN` cũng làm tròn lên `1.24`. Với `1.245`, `HALF_UP` cho `1.25` còn `HALF_EVEN` cho `1.24` vì chữ số giữ cuối `4` là chẵn.

Không giả định `HALF_UP` hay `HALF_EVEN` là đúng tuyệt đối cho mọi nghiệp vụ; quy tắc kế toán hoặc khoa học của hệ thống phải quyết định.

## 7. `stripTrailingZeros()`: cùng giá trị, biểu diễn mới

Phương thức `stripTrailingZeros()` loại bỏ các số 0 ở cuối trong unscaled representation bằng cách thay đổi scale phù hợp, giữ nguyên **giá trị số học**.

```java
BigDecimal x = new BigDecimal("123.4500");
BigDecimal y = x.stripTrailingZeros();

System.out.println(y);             // 123.45
System.out.println(y.precision()); // 5
System.out.println(y.scale());     // 2
```

Với số có nhiều chữ số 0 hàng đơn vị:

```java
BigDecimal x = new BigDecimal("1000.00");
BigDecimal y = x.stripTrailingZeros();

System.out.println(y);             // 1E+3
System.out.println(y.precision()); // 1
System.out.println(y.scale());     // -3
```

Đây là biến đổi có giá trị học tập lớn: **scale có thể trở thành âm ngay cả khi chuỗi đầu vào hoàn toàn không có ký hiệu số mũ**.

### Trường hợp zero

```java
BigDecimal x = new BigDecimal("0.000");
BigDecimal y = x.stripTrailingZeros();

System.out.println(y);             // 0
System.out.println(y.precision()); // 1
System.out.println(y.scale());     // 0
```

Một số zero có scale dương có thể được chuẩn hóa về `BigDecimal.ZERO` với scale 0. Vì vậy, nếu ứng dụng phải giữ `0.000` để thể hiện độ phân giải của thiết bị đo, **không** tự gọi `stripTrailingZeros()` trước khi lưu trữ dữ liệu đại diện.

### Có thể dùng để so sánh không?

Có thể chủ động chuẩn hóa một quy tắc biểu diễn cụ thể khi muốn dùng `BigDecimal` làm khóa dựa trên giá trị:

```java
BigDecimal canonical = value.stripTrailingZeros();
```

Nhưng **đừng áp dụng vô điều kiện** cho giá tiền, tiền tệ, phép đo hoặc dữ liệu cần giữ scale. Nếu dùng chuẩn hóa, các thành phần hệ thống phải thống nhất quy tắc, cách xử lý số 0, chuỗi output và scale âm. Chỉ cần kiểm tra hai số có cùng giá trị toán học thì `compareTo` thường rõ ràng hơn.

## 8. Phép cộng, nhân, chia: precision và scale thay đổi thế nào?

Các phép `BigDecimal` có kết quả `BigDecimal` bất biến. Scale trong phép tính **không nhất thiết** bằng scale của toán hạng hay precision mà người dùng mong muốn.

### 8.1. Phép cộng và trừ không `MathContext`

Với các phép cộng/trừ chính xác không context, preferred scale là **scale lớn hơn** của hai toán hạng:

```java
BigDecimal a = new BigDecimal("1.20");  // scale 2
BigDecimal b = new BigDecimal("3.004"); // scale 3

BigDecimal sum = a.add(b);
System.out.println(sum);         // 4.204
System.out.println(sum.scale()); // 3
```

Precision của kết quả được suy ra từ giá trị unscaled thực tế, **không đơn giản là tổng precision của hai toán hạng**.

### 8.2. Phép nhân không `MathContext`

Preferred scale của phép nhân chính xác là **tổng scale** hai toán hạng:

```java
BigDecimal a = new BigDecimal("1.20"); // scale 2
BigDecimal b = new BigDecimal("3.0");  // scale 1

BigDecimal product = a.multiply(b);
System.out.println(product);         // 3.600
System.out.println(product.scale()); // 3
```

Dù giá trị toán học là 3.6, biểu diễn giữ scale theo phép nhân chính xác và có precision tương ứng với chữ số unscaled.

### 8.3. Phép chia có thể cần quy tắc làm tròn

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");
```

Phép chia chính xác `one.divide(three)` ném `ArithmeticException` vì kết quả decimal 1/3 vô hạn tuần hoàn. Hai cách giới hạn khác nhau:

```java
BigDecimal byScale =
        one.divide(three, 2, RoundingMode.HALF_UP);
BigDecimal byPrecision =
        one.divide(three, new MathContext(3, RoundingMode.HALF_UP));

System.out.println(byScale);     // 0.33
System.out.println(byPrecision); // 0.333
```

Kết quả đầu có **scale = 2**, precision = 2; kết quả sau có **precision = 3**, scale = 3.

Với các phép có `MathContext`, Java áp dụng preferred scale và quy tắc làm tròn của API, nên scale kết quả có thể khác với công thức scale của phép chính xác, đặc biệt khi phải làm tròn hoặc rút gọn chữ số. Nếu quy trình cuối phải giữ cố định 2 chữ số thập phân, hãy `setScale(2, ...)` theo hợp đồng tại bước thích hợp, thay vì coi `MathContext(2)` đồng nghĩa với `scale=2`.

## 9. Đọc/ghi `BigDecimal`: đừng làm mất scale ngoài ý muốn

### 9.1. Tạo từ chuỗi decimal thay vì `double` tùy tiện

Nếu mục tiêu là giữ đúng decimal `"0.1"` và scale 1:

```java
BigDecimal exact = new BigDecimal("0.1");
System.out.println(exact.precision()); // 1
System.out.println(exact.scale());     // 1
```

Cách khác:

```java
BigDecimal displayValue = BigDecimal.valueOf(0.1);
```

`BigDecimal.valueOf(double)` dùng dạng decimal từ `Double.toString` của giá trị nhị phân đã có; với `0.1`, thường tạo kết quả `0.1`, scale 1.

Còn:

```java
BigDecimal binaryExact = new BigDecimal(0.1);
System.out.println(binaryExact);
// 0.1000000000000000055511151231257827021181583404541015625
```

`new BigDecimal(double)` phản ánh **chính xác giá trị nhị phân của `double`**, vốn không bằng số decimal toán học 0.1. Không dùng constructor từ `double` một cách vô thức khi nhập tiền hoặc số decimal từ người dùng. Nếu đầu vào đã trải qua các phép toán `double` làm mất dữ liệu trước đó, `valueOf(double)` cũng không thể khôi phục bản gốc.

### 9.2. `toString()` có thể xuất dạng số mũ

```java
BigDecimal x = new BigDecimal("1E+3");

System.out.println(x.toString());      // 1E+3
System.out.println(x.toPlainString()); // 1000
```

Cả hai mô tả cùng **giá trị toán học**, nhưng khi parse chuỗi `"1000"` bằng `new BigDecimal`, scale sẽ là 0, **không giữ scale -3** như bản gốc `1E+3`. `toString()` của `BigDecimal` có biểu diễn decimal canonical có thể khôi phục lại đúng unscaled value và scale khi parse trở lại; `toPlainString()` phục vụ hiển thị decimal không số mũ, không hứa giữ scale âm sau round-trip.

Nếu lưu dữ liệu mà **scale là một phần quan trọng của schema**, hãy chọn định dạng serialization và database type bảo toàn scale theo hợp đồng, thay vì chỉ hiển thị `toPlainString()` rồi kỳ vọng mọi metadata được khôi phục.

### 9.3. Làm việc với tiền tệ

Ví dụ:

```java
BigDecimal amount = new BigDecimal("12.3");
BigDecimal currencyValue = amount.setScale(2, RoundingMode.UNNECESSARY);

System.out.println(currencyValue); // 12.30
```

Ở đây `precision` từ 3 thành 4 sau khi thêm số 0 cuối, nhưng **giá trị toán học không thay đổi**. Giữ `scale=2` là yêu cầu biểu diễn tiền với hai chữ số thập phân, **không** phải yêu cầu chỉ giữ hai chữ số chính xác.

Nếu giá trị ban đầu cần làm tròn, phải dùng `setScale(2, roundingMode)` theo quy tắc nghiệp vụ. Không áp dụng `stripTrailingZeros()` cho dữ liệu tiền cần xuất `"12.30"`; nó sẽ bỏ số 0 sau cùng và thay đổi scale.

## 10. Ví dụ Java 17 hoàn chỉnh

Tạo tệp `PrecisionVsScaleDemo.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class PrecisionVsScaleDemo {
    private static void describe(String label, BigDecimal value) {
        System.out.println(label + " = " + value
                + " | unscaled=" + value.unscaledValue()
                + " | precision=" + value.precision()
                + " | scale=" + value.scale());
    }

    public static void main(String[] args) {
        describe("amount", new BigDecimal("123.4500"));
        describe("small", new BigDecimal("0.0012300"));
        describe("integer", new BigDecimal("1000"));
        describe("scientific", new BigDecimal("1E+3"));
        describe("zero", new BigDecimal("0.000"));

        BigDecimal x = new BigDecimal("123.4500");
        describe("scale2", x.setScale(2, RoundingMode.UNNECESSARY));
        describe("scale6", x.setScale(6));
        describe("precision3",
                x.round(new MathContext(3, RoundingMode.HALF_UP)));

        BigDecimal carried = new BigDecimal("999.9")
                .round(new MathContext(3, RoundingMode.HALF_UP));
        describe("carry", carried);

        BigDecimal stripped = new BigDecimal("1000.00")
                .stripTrailingZeros();
        describe("stripped", stripped);

        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        System.out.println("equals 2.0 / 2.00: " + a.equals(b));
        System.out.println("compare 2.0 / 2.00: " + a.compareTo(b));

        BigDecimal byScale = BigDecimal.ONE.divide(
                new BigDecimal("3"), 2, RoundingMode.HALF_UP);
        BigDecimal byPrecision = BigDecimal.ONE.divide(
                new BigDecimal("3"),
                new MathContext(3, RoundingMode.HALF_UP));
        describe("divideScale2", byScale);
        describe("dividePrecision3", byPrecision);

        System.out.println("UNLIMITED context precision: "
                + MathContext.UNLIMITED.getPrecision());
        System.out.println("ZERO value precision: "
                + BigDecimal.ZERO.precision());

        BigDecimal inScientific = new BigDecimal("1E+3");
        System.out.println("scientific toString: "
                + inScientific.toString());
        System.out.println("scientific toPlainString: "
                + inScientific.toPlainString());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac PrecisionVsScaleDemo.java
java PrecisionVsScaleDemo
```

Đầu ra:

```text
amount = 123.4500 | unscaled=1234500 | precision=7 | scale=4
small = 0.0012300 | unscaled=12300 | precision=5 | scale=7
integer = 1000 | unscaled=1000 | precision=4 | scale=0
scientific = 1E+3 | unscaled=1 | precision=1 | scale=-3
zero = 0.000 | unscaled=0 | precision=1 | scale=3
scale2 = 123.45 | unscaled=12345 | precision=5 | scale=2
scale6 = 123.450000 | unscaled=123450000 | precision=9 | scale=6
precision3 = 123 | unscaled=123 | precision=3 | scale=0
carry = 1.00E+3 | unscaled=100 | precision=3 | scale=-1
stripped = 1E+3 | unscaled=1 | precision=1 | scale=-3
equals 2.0 / 2.00: false
compare 2.0 / 2.00: 0
divideScale2 = 0.33 | unscaled=33 | precision=2 | scale=2
dividePrecision3 = 0.333 | unscaled=333 | precision=3 | scale=3
UNLIMITED context precision: 0
ZERO value precision: 1
scientific toString: 1E+3
scientific toPlainString: 1000
```

**Đọc kết quả theo ba cột:** `unscaled`, `precision` và `scale` là thông tin biểu diễn; số decimal được in có thể dùng số mũ. Một số phép có thể thay scale và precision mà **không thay giá trị toán học**, trong khi phép làm tròn có thể thay cả giá trị toán học.

## 11. Lỗi thường gặp

1. **Nghĩ `precision()` là số chữ số sau dấu thập phân.** `new BigDecimal("123.4500")` có precision 7, scale 4.
2. **Nghĩ scale luôn không âm.** `"1E+3"` có scale -3; `stripTrailingZeros()` còn có thể tạo scale âm từ số viết thông thường.
3. **Đếm các số 0 ở đầu để suy precision.** Với `"0.0012300"`, precision là 5 chứ không phải độ dài chuỗi chữ số.
4. **Nghĩ số 0 có precision 0.** Mọi giá trị `BigDecimal` bằng 0 có precision được định nghĩa là 1.
5. **Nhầm `MathContext(2)` với `setScale(2)`.** Một bên giới hạn số chữ số có nghĩa; bên kia xác định vị trí thập phân.
6. **Tin `MathContext.UNLIMITED.getPrecision() == 0` nghĩa kết quả BigDecimal có precision 0.** Số 0 ở `MathContext` là mã “không giới hạn precision”.
7. **Giảm scale mà không chọn `RoundingMode`.** Nếu cần bỏ chữ số khác 0, `setScale` không có rounding có thể ném `ArithmeticException`.
8. **Dùng `equals` để kiểm tra bằng nhau về số mà bỏ qua scale.** `"2.0"` và `"2.00"` có `compareTo == 0` nhưng `equals == false`.
9. **Dùng `BigDecimal` làm khóa `HashSet` và `TreeSet` mà không hiểu khác biệt.** `HashSet` dựa vào `equals`; `TreeSet` dựa vào `compareTo`.
10. **Gọi `stripTrailingZeros` mà vẫn kỳ vọng giữ `"12.30"` hoặc `"0.000"`.** Kết quả có thể đổi scale và cách viết.
11. **Nghĩ `BigDecimal` không bao giờ cần làm tròn.** Phép chia 1/3 phải có context hoặc quy tắc làm tròn; nếu yêu cầu chính xác không thể có kết quả decimal hữu hạn thì `divide` exact ném lỗi.
12. **Dùng `new BigDecimal(0.1)` để nhập decimal 0.1 chính xác.** Constructor này phản ánh giá trị nhị phân của double, không phải nguồn decimal toán học.
13. **Dùng `toPlainString()` rồi parse lại và kỳ vọng giữ scale âm.** `1E+3` thành `"1000"` sẽ được parse với scale 0.
14. **Cho rằng mọi chữ số 0 cuối đều không có ý nghĩa nghiệp vụ.** Trong đo lường và báo cáo, trailing zeros có thể biểu đạt quy tắc độ phân giải; không chuẩn hóa mất chúng khi cần giữ.
15. **Cố đo precision bằng `value.toString().replace(...)`.** Dạng số mũ, dấu âm, số 0 đầu, scale âm làm cách đếm ký tự sai. Dùng `precision()` API.
16. **Dùng `BigDecimal` như thể nó là primitive mutable.** Nó bất biến; mọi `setScale`, `round`, `stripTrailingZeros`, `add`... trả kết quả phải được giữ khi cần.
17. **Dùng scale để suy chắc mức độ chính xác của phép đo.** Scale là thuộc tính biểu diễn, không phải chứng cứ rằng nguồn có sai số nhỏ hay đã được kiểm định đến số chữ số đó.
18. **Cho rằng precision luôn bằng đúng giới hạn của MathContext.** Một kết quả có thể có ít chữ số hơn ngưỡng nếu phép tính không cần đủ số chữ số hoặc các chữ số cuối bị rút gọn theo quy tắc API.

## 12. Bài tập và lời giải

**Câu 1.** `new BigDecimal("123.4500")` có precision và scale bằng bao nhiêu?

**Đáp án:** Precision 7 và scale 4; unscaled value là 1234500.

**Câu 2.** `new BigDecimal("0.0012300")` có bao nhiêu chữ số precision? Tại sao scale lại là 7?

**Đáp án:** Precision 5 vì unscaled value là 12300; scale 7 vì có bảy chữ số sau dấu chấm trong biểu diễn đầu vào.

**Câu 3.** `new BigDecimal("1E+3")` và `new BigDecimal("1000")` có bằng nhau không theo `equals` và theo `compareTo`?

**Đáp án:** `compareTo` cho 0 vì cùng giá trị số 1000; `equals` cho `false` vì scale -3 và scale 0 khác nhau.

**Câu 4.** Một ứng dụng cần hiển thị `12.3` thành `12.30`. Có nên dùng `MathContext(2)` không?

**Đáp án:** Không. Dùng `setScale(2, RoundingMode.UNNECESSARY)` để có scale 2 khi không cần làm tròn. `MathContext(2)` giới hạn hai chữ số có nghĩa, không phải hai số thập phân.

**Câu 5.** Vì sao `new BigDecimal("1000.00").stripTrailingZeros()` có thể in ra `"1E+3"`?

**Đáp án:** Phép chuẩn hóa bỏ các số 0 cuối trong unscaled representation, giữ giá trị 1000 nhưng đổi unscaled về 1 và scale thành -3, nên biểu diễn canonical có dạng số mũ.

**Câu 6.** Với `new BigDecimal("999.9").round(new MathContext(3, HALF_UP))`, kết quả precision/scale là gì?

**Đáp án:** Kết quả là `1.00E+3`, precision 3, scale -1. Phần carry khi làm tròn đổi cả cách đặt dấu decimal lẫn unscaled value.

**Câu 7.** Tại sao `BigDecimal.ZERO.precision()` là 1 nhưng `MathContext.UNLIMITED.getPrecision()` là 0?

**Đáp án:** `precision()` của số 0 dùng quy tắc BigDecimal: 1. `MathContext` dùng giá trị cấu hình 0 để biểu thị precision không giới hạn; hai API có nghĩa khác nhau.

**Câu 8.** Hai cách tính `1 / 3`:

```java
BigDecimal a = BigDecimal.ONE.divide(
        new BigDecimal("3"), 2, RoundingMode.HALF_UP);
BigDecimal b = BigDecimal.ONE.divide(
        new BigDecimal("3"), new MathContext(3, RoundingMode.HALF_UP));
```

Kết quả là gì?

**Đáp án:** `a = 0.33` (scale 2, precision 2); `b = 0.333` (scale 3, precision 3).

**Câu 9.** Nếu muốn giữ nguyên scale của một `BigDecimal` với scale âm khi serialization rồi parse lại, có nên dùng `toPlainString` không?

**Đáp án:** Không nên nếu yêu cầu round-trip giữ nguyên unscaled value và scale. `toPlainString` của `1E+3` in `"1000"` và parse lại có scale 0; dùng cách serialization có hợp đồng giữ scale, ví dụ chuỗi canonical từ `toString()` khi phù hợp.

**Câu 10.** `BigDecimal("0.000")` có `precision = 3` không? Sau `stripTrailingZeros` thì sao?

**Đáp án:** Không: precision = 1, scale = 3. Sau khi strip, giá trị 0 được chuẩn hóa về scale = 0 và precision vẫn = 1.

**Tóm tắt:** `BigDecimal` lưu `unscaledValue × 10^(-scale)`. `precision` cho biết số chữ số có nghĩa trong unscaled representation (zero có precision 1); `scale` quyết định vị trí dấu thập phân và có thể âm. Dùng `setScale` cho số vị trí decimal theo hợp đồng, dùng `MathContext` cho giới hạn chữ số có nghĩa, và nhớ rằng `equals` phân biệt scale còn `compareTo` so giá trị số.