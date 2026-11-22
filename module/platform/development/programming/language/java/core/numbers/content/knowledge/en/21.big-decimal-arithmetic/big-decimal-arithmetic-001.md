# `BigDecimal.add`, `subtract`, `multiply` và scale của kết quả trong Java

## 1. Vấn đề: cùng phép toán, vì sao số chữ số thập phân của kết quả khác nhau?

Trong Java, `BigDecimal` biểu diễn số decimal bằng một **unscaled value** kiểu `BigInteger` và một **scale** kiểu `int`. Khi cộng, trừ hoặc nhân, Java vừa tính **giá trị toán học**, vừa xác định **scale của kết quả** theo hợp đồng API.

Ví dụ:

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("1.20");  // scale 2
BigDecimal b = new BigDecimal("3.004"); // scale 3

System.out.println(a.add(b));      // 4.204
System.out.println(a.subtract(b)); // -1.804
System.out.println(a.multiply(b)); // 3.60480
```

Điều đáng chú ý là:

- Tổng `4.204` có **scale = 3**.
- Hiệu `-1.804` có **scale = 3**.
- Tích `3.60480` có **scale = 5**.

Với các phép **chính xác, không truyền `MathContext`**:

| Phép toán | Scale ưu tiên của kết quả |
| --- | --- |
| `a.add(b)` | `max(a.scale(), b.scale())` |
| `a.subtract(b)` | `max(a.scale(), b.scale())` |
| `a.multiply(b)` | `a.scale() + b.scale()` |

Trong ba phép được trình bày, công thức này mô tả *preferred scale* khi tính toán chính xác theo đặc tả `BigDecimal`. Khi dùng `MathContext` với giới hạn precision, phép làm tròn và việc biểu diễn kết quả có thể **thay đổi scale cuối**. Ngoài ra, scale có giới hạn kiểu `int`, nên phép tính trên scale cực trị có thể cần xử lý ngoại lệ.

**Điểm quan trọng nhất:** scale là thuộc tính **biểu diễn decimal**, không phải số lượng “độ chính xác tuyệt đối” của phép đo. Một kết quả có nhiều chữ số 0 cuối không có nghĩa dữ liệu nguồn đã trở nên chính xác hơn về vật lý hay nghiệp vụ.

## 2. Nhắc lại mô hình `unscaled × 10^-scale`

Một giá trị `BigDecimal` được xác định bằng:

\[
\text{value}=\text{unscaledValue}\times10^{-\text{scale}}.
\]

Ví dụ:

```java
BigDecimal x = new BigDecimal("12.340");

System.out.println(x.unscaledValue()); // 12340
System.out.println(x.scale());         // 3
System.out.println(x.precision());     // 5
```

Giá trị toán học là:

\[
12340\times 10^{-3}=12.340.
\]

`precision()` đếm chữ số của unscaled value (trường hợp unscaled bằng 0 thì precision là 1). `scale()` quyết định vị trí dấu thập phân. Hai khái niệm không thay thế nhau.

Một số ví dụ:

| Chuỗi | Unscaled value | Scale | Precision | Giá trị số |
| --- | ---: | ---: | ---: | --- |
| `"1.20"` | `120` | 2 | 3 | 1.2 |
| `"3.004"` | `3004` | 3 | 4 | 3.004 |
| `"0.10"` | `10` | 2 | 2 | 0.1 |
| `"0.2"` | `2` | 1 | 1 | 0.2 |
| `"1000"` | `1000` | 0 | 4 | 1000 |
| `"1E+3"` | `1` | -3 | 1 | 1000 |
| `"0.00"` | `0` | 2 | 1 | 0 |

`scale` có thể âm. Với `new BigDecimal("1E+3")`, unscaled là 1, scale là -3:

\[
1\times10^{-(-3)}=1000.
\]

Vì vậy không thể suy đoán scale chỉ bằng “đếm số sau dấu chấm” của mọi dạng chuỗi, nhất là khi có ký hiệu số mũ hoặc sau `stripTrailingZeros()`.

### Bất biến của `BigDecimal`

`BigDecimal` là đối tượng **immutable**:

```java
BigDecimal balance = new BigDecimal("1.20");
balance.add(new BigDecimal("3.00")); // Kết quả không được giữ

System.out.println(balance); // 1.20
```

Muốn cập nhật biến:

```java
balance = balance.add(new BigDecimal("3.00"));
System.out.println(balance); // 4.20
```

Phương thức trả một `BigDecimal` biểu diễn kết quả; nó không sửa đối tượng ban đầu. Điều này đúng với cả `add`, `subtract`, `multiply`, `setScale` và các phép biến đổi khác.

## 3. `add`: cộng chính xác và lấy scale lớn hơn

Chữ ký quan trọng:

```java
BigDecimal add(BigDecimal augend)
BigDecimal add(BigDecimal augend, MathContext mc)
```

Khi **không có `MathContext`**, phép cộng chính xác có scale ưu tiên:

\[
s_{\text{sum}}=\max(s_a,s_b).
\]

Lý do: để cộng hai số decimal ở hai vị trí dấu chấm khác nhau, có thể biểu diễn cả hai theo **cùng scale lớn hơn** (cùng đơn vị nhỏ hơn), rồi cộng unscaled values.

Ví dụ:

```java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("3.004");

BigDecimal sum = a.add(b);
System.out.println(sum);         // 4.204
System.out.println(sum.scale()); // 3
```

Phân tích:

\[
1.20=120\times10^{-2}=1200\times10^{-3}
\]

\[
3.004=3004\times10^{-3}.
\]

Vì `max(2,3)=3`, tổng là:

\[
(1200+3004)\times10^{-3}
=4204\times10^{-3}
=4.204.
\]

### Các số 0 cuối vẫn được giữ khi scale yêu cầu

```java
BigDecimal left = new BigDecimal("0.10");
BigDecimal right = new BigDecimal("0.2");

BigDecimal sum = left.add(right);

System.out.println(sum);         // 0.30
System.out.println(sum.scale()); // 2
```

Về toán học `0.3 = 0.30`, nhưng `BigDecimal` của phép cộng chính xác có scale 2 do số hạng `"0.10"` có scale 2.

Nếu cần kết quả hiển thị như `"0.30"` cho một định dạng hai chữ số lẻ, scale 2 có thể hữu ích. Tuy nhiên, đây là **quy tắc phép tính**, không phải bằng chứng rằng phép đo ban đầu chính xác tới hàng phần trăm.

### Cộng một số 0 không chắc giữ nguyên scale của số kia

```java
BigDecimal x = new BigDecimal("12.3"); // scale 1
BigDecimal zero = new BigDecimal("0.000"); // scale 3

BigDecimal result = x.add(zero);
System.out.println(result);         // 12.300
System.out.println(result.scale()); // 3
```

Dù giá trị toán học không thay đổi, scale tăng từ 1 lên 3. Không nên coi “cộng 0 thì đối tượng/scale luôn không đổi”; quy tắc của phép cộng vẫn áp dụng.

## 4. `subtract`: trừ chính xác cũng lấy scale lớn hơn

Chữ ký chính:

```java
BigDecimal subtract(BigDecimal subtrahend)
BigDecimal subtract(BigDecimal subtrahend, MathContext mc)
```

Không truyền context:

\[
s_{\text{difference}}=\max(s_a,s_b).
\]

Ví dụ:

```java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("3.004");

BigDecimal difference = a.subtract(b);

System.out.println(difference);         // -1.804
System.out.println(difference.scale()); // 3
```

Cơ chế vẫn là căn chỉnh các unscaled values về cùng scale:

\[
(1200-3004)\times10^{-3}=-1804\times10^{-3}=-1.804.
\]

### Kết quả âm không làm scale “âm”

```java
BigDecimal a = new BigDecimal("0.10");
BigDecimal b = new BigDecimal("0.2");

BigDecimal result = a.subtract(b);
System.out.println(result);         // -0.10
System.out.println(result.scale()); // 2
```

**Dấu âm của giá trị** và **dấu của scale** là hai vấn đề khác nhau. Kết quả `-0.10` là số âm với scale **dương** 2.

### Khi phép trừ tạo zero

```java
BigDecimal a = new BigDecimal("2.00");
BigDecimal b = new BigDecimal("-2.00");

BigDecimal sum = a.add(b);
System.out.println(sum);         // 0.00
System.out.println(sum.scale()); // 2
```

Tương tự với `new BigDecimal("2.00").subtract(new BigDecimal("2.00"))`, kết quả chính xác có giá trị zero và scale 2.

`BigDecimal` không có hai giá trị số 0 mang dấu âm/dương khác nhau như `double`. Nhưng hai số zero có scale khác nhau vẫn khác nhau theo `equals`, dù `compareTo` xác định chúng bằng nhau về số học.

## 5. `multiply`: nhân chính xác và cộng scale

Chữ ký:

```java
BigDecimal multiply(BigDecimal multiplicand)
BigDecimal multiply(BigDecimal multiplicand, MathContext mc)
```

Nếu không có context, với:

\[
a=u_a\times10^{-s_a},\qquad
b=u_b\times10^{-s_b}
\]

thì:

\[
ab=(u_a u_b)\times10^{-(s_a+s_b)}.
\]

Do đó:

\[
s_{\text{product}}=s_a+s_b.
\]

Ví dụ:

```java
BigDecimal a = new BigDecimal("1.20");  // scale 2
BigDecimal b = new BigDecimal("3.004"); // scale 3

BigDecimal result = a.multiply(b);

System.out.println(result);         // 3.60480
System.out.println(result.scale()); // 5
```

Unscaled values là 120 và 3004. Nhân chúng được 360480, scale tổng là `2+3=5`, do đó:

\[
360480\times10^{-5}=3.60480.
\]

Hai chữ số 0 sau cùng không phải lỗi tính toán. Chúng xuất hiện vì phép nhân chính xác **giữ scale ưu tiên bằng tổng scale**.

### Một ví dụ rõ hơn về chữ số 0 cuối

```java
BigDecimal x = new BigDecimal("1.20");
BigDecimal y = new BigDecimal("3.0");

BigDecimal product = x.multiply(y);

System.out.println(product);         // 3.600
System.out.println(product.scale()); // 3
```

Giá trị toán học bằng `3.6`, nhưng scale 3 vì `2+1=3`. Nếu mục tiêu là hiển thị tiền với hai chữ số lẻ, có thể áp dụng `setScale(2, ...)` tại ranh giới nghiệp vụ thích hợp; đừng giả định scale của tích luôn đúng số chữ số cần xuất.

### Nhân với số 0

```java
BigDecimal a = new BigDecimal("1.0");  // scale 1
BigDecimal zero = new BigDecimal("0.00"); // scale 2

BigDecimal product = a.multiply(zero);

System.out.println(product);         // 0.000
System.out.println(product.scale()); // 3
```

**Giá trị bằng 0** không làm scale tự trở thành 0. Phép nhân chính xác vẫn tuân theo tổng scale trong tình huống thường gặp này.

### Tăng số chữ số kết quả không có nghĩa precision đầu vào sai

Với `1.20 × 3.004`, tích có unscaled value sáu chữ số (`360480`) và precision 6. Đây là **chữ số của biểu diễn kết quả**, không phải một cam kết khoa học rằng tất cả sáu chữ số đều đáng tin nếu hai đầu vào vốn là số đo có sai số.

## 6. Scale âm: cộng/trừ và nhân vẫn tuân theo công thức

Một `BigDecimal` có thể có scale âm khi tạo từ dạng lũy thừa 10:

```java
BigDecimal thousand = new BigDecimal("1E+3"); // scale -3
BigDecimal amount = new BigDecimal("2.50");   // scale 2
```

### Cộng và trừ với scale âm

```java
BigDecimal sum = thousand.add(amount);
BigDecimal difference = thousand.subtract(amount);

System.out.println(sum);             // 1002.50
System.out.println(sum.scale());     // 2
System.out.println(difference);      // 997.50
System.out.println(difference.scale()); // 2
```

Scale ưu tiên là `max(-3,2)=2`. Để cộng/trừ chính xác, `1E+3` được căn chỉnh sang scale 2, tương đương unscaled value `100000`.

### Nhân với scale âm

```java
BigDecimal product = thousand.multiply(amount);

System.out.println(product);         // 2.50E+3
System.out.println(product.scale()); // -1
System.out.println(product.toPlainString()); // 2500
```

Scale tổng bằng `-3+2=-1`. Unscaled value của tích là `1×250=250`, nên:

\[
250\times10^{-(-1)}=2500.
\]

`toString()` có thể in dạng số mũ `2.50E+3`, còn `toPlainString()` in `2500`. Khi parse lại chuỗi plain `"2500"`, scale sẽ thường là 0, **không còn là -1**. Nếu scale phải được bảo toàn qua serialization, lựa chọn định dạng là một phần hợp đồng dữ liệu.

### `stripTrailingZeros()` còn có thể tạo scale âm

```java
BigDecimal raw = new BigDecimal("1000.00");
BigDecimal normalized = raw.stripTrailingZeros();

System.out.println(normalized);         // 1E+3
System.out.println(normalized.scale()); // -3
```

`stripTrailingZeros()` giữ nguyên giá trị toán học nhưng thay đổi scale. Đừng chuẩn hóa số tiền/đo lường như vậy khi scale hoặc trailing zeros có ý nghĩa báo cáo.

## 7. `MathContext`: quy tắc về scale còn đúng hoàn toàn không?

Có overload của `add`, `subtract`, `multiply` nhận `java.math.MathContext`:

```java
BigDecimal result = a.add(b, mc);
BigDecimal difference = a.subtract(b, mc);
BigDecimal product = a.multiply(b, mc);
```

`MathContext` bao gồm:

- **Precision**: giới hạn số chữ số có nghĩa của kết quả (không phải số vị trí sau dấu thập phân).
- **RoundingMode**: quy tắc làm tròn khi cần giảm số chữ số có nghĩa.

Khi có `MathContext` với precision hữu hạn, Java có thể làm tròn kết quả chính xác, dẫn đến scale thực tế **khác preferred scale** ban đầu.

Ví dụ:

```java
import java.math.MathContext;
import java.math.RoundingMode;

BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("3.004");

MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

System.out.println(a.add(b, mc));      // 4.20
System.out.println(a.subtract(b, mc)); // -1.80
System.out.println(a.multiply(b, mc)); // 3.60
```

Bảng đối chiếu:

| Phép | Không context | Scale chính xác | Có `MathContext(3, HALF_UP)` | Scale sau làm tròn |
| --- | --- | ---: | --- | ---: |
| `1.20 + 3.004` | `4.204` | 3 | `4.20` | 2 |
| `1.20 - 3.004` | `-1.804` | 3 | `-1.80` | 2 |
| `1.20 × 3.004` | `3.60480` | 5 | `3.60` | 2 |

Sự khác nhau này là **chủ đích của API**, không phải Java tự làm phép cộng/trừ/nhân sai. Khi context giới hạn ba chữ số có nghĩa, các số ở cuối bị làm tròn theo `RoundingMode`.

### Khi làm tròn gây carry

```java
BigDecimal left = new BigDecimal("999.9");
BigDecimal right = new BigDecimal("0.2");

BigDecimal rounded = left.add(
        right, new MathContext(3, RoundingMode.HALF_UP));

System.out.println(rounded);             // 1.00E+3
System.out.println(rounded.precision()); // 3
System.out.println(rounded.scale());     // -1
```

Tổng toán học chính xác là `1000.1`. Với ba chữ số có nghĩa, nó làm tròn thành giá trị 1000 được biểu diễn `1.00E+3`, scale -1. Khi có carry, scale có thể thay đổi đáng kể, kể cả trở thành âm.

### `MathContext.UNLIMITED`

`MathContext.UNLIMITED` có `getPrecision() == 0`; số 0 ở đây có nghĩa **không giới hạn precision bởi context**, không phải “precision của một số BigDecimal bằng 0”.

```java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("3.004");

System.out.println(a.add(b, MathContext.UNLIMITED)); // 4.204
System.out.println(a.multiply(b, MathContext.UNLIMITED)); // 3.60480
```

Đối với ba phép cộng/trừ/nhân, context không giới hạn không yêu cầu cắt chữ số; nhưng vẫn chịu giới hạn tài nguyên và scale biểu diễn. Riêng phép chia có thể tạo chuỗi decimal vô hạn như `1/3`, cần hợp đồng làm tròn phù hợp; không suy luận rằng `MathContext.UNLIMITED` luôn khiến phép chia trả một kết quả hữu hạn chữ số.

### Precision của kết quả không nhất thiết bằng chính xác số đặt trong context

`new MathContext(6)` có nghĩa **tối đa** sáu chữ số có nghĩa; nếu kết quả tự nhiên chỉ có ba chữ số có nghĩa, không phải lúc nào Java cũng đệm đủ thành sáu. Ngược lại, số unscaled nhiều chữ số có thể bị rút gọn đáng kể vì làm tròn.

Không lấy `MathContext.getPrecision()` rồi mặc định đó chính là `result.precision()` trên mọi phép tính.

## 8. `setScale` là bước chuẩn hóa kết quả, không phải thay cho MathContext

Nếu yêu cầu hiển thị hoặc lưu số có **đúng hai chữ số thập phân**, hãy dùng `setScale` sau khi xác định chính sách nghiệp vụ:

```java
import java.math.RoundingMode;

BigDecimal exact = new BigDecimal("1.20")
        .add(new BigDecimal("3.004"));

BigDecimal display = exact.setScale(2, RoundingMode.HALF_UP);

System.out.println(exact);   // 4.204
System.out.println(display); // 4.20
```

- `add` chính xác trả `4.204` với scale 3.
- `setScale(2, HALF_UP)` trả `4.20` với scale 2.

Bởi có chữ số bị loại, hai giá trị toán học khác nhau (`4.204` và `4.20`); đây là làm tròn được chỉ định rõ ràng, không phải phép cộng sai.

### Khi nào dùng `RoundingMode.UNNECESSARY`?

Nếu giảm scale mà không được phép mất thông tin:

```java
BigDecimal a = new BigDecimal("1.2300");
System.out.println(
        a.setScale(2, RoundingMode.UNNECESSARY)); // 1.23
```

Ở đây chỉ bỏ các số 0 ở cuối, nên không cần làm tròn giá trị toán học. Trái lại:

```java
BigDecimal x = new BigDecimal("1.234");
// x.setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException: cần bỏ chữ số 4 khác 0
```

Dùng `UNNECESSARY` khi muốn **phát hiện** vi phạm điều kiện độ phân giải thay vì âm thầm làm tròn. Với hệ thống tài chính, phí, thuế, thanh toán hoặc phép đo, `RoundingMode` phải tuân thủ chính sách nghiệp vụ và quy định có liên quan; không tự cho rằng `HALF_UP` đúng cho mọi trường hợp.

### Làm tròn ở từng bước hay ở bước cuối?

Đây là một quyết định quan trọng:

```java
BigDecimal sum = a.add(b);         // Giữ tổng chính xác
BigDecimal result = sum.setScale(2, RoundingMode.HALF_UP);
```

Trong nhiều bài toán, tính toán chính xác trước và làm tròn tại ranh giới xuất/lưu là phù hợp. Nhưng một số hợp đồng nghiệp vụ yêu cầu làm tròn từng dòng hóa đơn trước khi cộng. Hai cách **có thể khác kết quả**.

Ví dụ:

- Hai khoản `0.005` nếu làm tròn `HALF_UP` **từng khoản** đến hai chữ số: `0.01 + 0.01 = 0.02`.
- Nếu **cộng trước**: `0.005 + 0.005 = 0.010`, rồi làm tròn hai chữ số: `0.01`.

Không có một quy tắc duy nhất cho mọi hệ thống. Phải ghi rõ đơn vị nhỏ nhất, thời điểm làm tròn, độ chính xác và cách xử lý trường hợp nửa.

## 9. Scale và equality: `equals` khác `compareTo`

Do scale là một phần của biểu diễn `BigDecimal`, hai đối tượng có **cùng giá trị số học** có thể không bằng nhau theo `equals`:

```java
BigDecimal a = new BigDecimal("2.0");  // scale 1
BigDecimal b = new BigDecimal("2.00"); // scale 2

System.out.println(a.equals(b));     // false
System.out.println(a.compareTo(b));  // 0
```

`equals` yêu cầu giá trị và scale phù hợp; `compareTo` kiểm tra thứ tự giá trị toán học và không phân biệt số 0 cuối.

Hệ quả:

- `HashSet<BigDecimal>`/`HashMap<BigDecimal,...>` dùng `equals` và `hashCode`, nên có thể coi `2.0` và `2.00` là **hai khóa** khác nhau.
- `TreeSet<BigDecimal>`/`TreeMap<BigDecimal,...>` dựa vào `compareTo` tự nhiên, nên thường coi chúng là **cùng khóa về thứ tự**.
- `setScale` hay `stripTrailingZeros` có thể làm kết quả của `equals` thay đổi dù số học không đổi.

Nếu scale là thông tin quan trọng (ví dụ cố định 2 chữ số decimal), giữ scale và dùng `equals` theo yêu cầu schema. Nếu chỉ muốn xác định hai số đại diện cùng giá trị toán học, dùng `compareTo(...) == 0` hoặc xây dựng quy tắc canonical phù hợp.

### Kết quả của phép nhân và khóa collection

```java
BigDecimal p = new BigDecimal("1.20")
        .multiply(new BigDecimal("3.0")); // 3.600, scale 3
BigDecimal q = new BigDecimal("3.60");     // 3.60, scale 2

System.out.println(p.equals(q));    // false
System.out.println(p.compareTo(q)); // 0
```

Nếu dùng `p` làm khóa `HashMap` rồi truy vấn bằng `q`, việc không tìm thấy khóa có thể là **đúng theo `equals`** chứ không phải lỗi hashmap. Chọn quy tắc scale/canonical hóa dữ liệu ở ranh giới phù hợp.

## 10. Những trường hợp đặc biệt cần kiểm tra

### 10.1. Đầu vào dạng số mũ

`new BigDecimal("1E+3")` có scale -3; cộng với `2.50` lấy scale 2, nhân với `2.50` lấy scale -1. Đừng ép `scale` luôn không âm trong mã kiểm tra, và đừng giả định tổng scale lúc nhân là số chữ số sau dấu chấm theo dạng hiển thị.

### 10.2. Kết quả bằng 0

`0.00` và `0.000` bằng nhau theo `compareTo` nhưng khác `equals`; các phép toán chính xác vẫn có scale ưu tiên. Khi cần giữ dấu vết quy tắc độ phân giải của nguồn, đừng tự động thay mọi zero bằng `BigDecimal.ZERO` có scale 0.

### 10.3. Giới hạn scale kiểu `int`

`scale()` là `int`. Nếu tổng scale khi nhân vượt miền số nguyên `int`, hoặc có phép điều chỉnh scale vượt miền, Java có thể ném `ArithmeticException`. Một số chi tiết với kết quả bằng 0 và phương thức có context được xử lý riêng theo hợp đồng API; không nên tạo một công thức modulo hay cố ép kiểu để vượt hạn chế đó.

Dữ liệu được xây dựng từ các exponent cực đoan có thể dẫn tới thao tác căn chỉnh scale, cấp phát hoặc tính toán tốn kém. Với đầu vào không tin cậy, cần giới hạn số chữ số, exponent, precision và khối lượng công việc.

### 10.4. Dấu của số 0

`BigDecimal` không có khái niệm `+0.0` và `-0.0` tách biệt theo biểu diễn IEEE 754 như `double`. Nhập `new BigDecimal("-0.00")` biểu diễn số 0 có scale 2; các phép cộng/trừ/nhân tuân theo giá trị 0 và scale. Nếu dấu âm của nguyên văn đầu vào có ý nghĩa báo cáo, phải giữ chuỗi đầu vào riêng.

### 10.5. Đầu vào từ `double` có thể đã mất decimal nguồn

```java
BigDecimal good = new BigDecimal("0.1");
BigDecimal fromDouble = new BigDecimal(0.1);

System.out.println(good); // 0.1
System.out.println(fromDouble);
// 0.1000000000000000055511151231257827021181583404541015625
```

`new BigDecimal(double)` biểu diễn chính xác giá trị nhị phân đã có của `double`, không phải decimal chuỗi mà người dùng đã nhập. Với decimal nghiệp vụ, ưu tiên `new BigDecimal(String)`; `BigDecimal.valueOf(double)` dùng dạng decimal từ `Double.toString`, nhưng cũng không khôi phục sai số đã phát sinh trước đó trong luồng `double`.

Nếu muốn tính chính xác bằng `BigDecimal`, **đừng đưa dữ liệu qua `double` trước**, rồi hy vọng kết quả add/multiply sẽ tự sửa độ chính xác đã mất.

## 11. Demo Java 17 hoàn chỉnh

Lưu tệp `BigDecimalOperationsScaleDemo.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalOperationsScaleDemo {

    static void show(String label, BigDecimal x) {
        System.out.println(label + " = " + x
                + " | scale=" + x.scale()
                + " | precision=" + x.precision());
    }

    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.20");
        BigDecimal b = new BigDecimal("3.004");

        show("add", a.add(b));
        show("subtract", a.subtract(b));
        show("multiply", a.multiply(b));

        BigDecimal x = new BigDecimal("0.10");
        BigDecimal y = new BigDecimal("0.2");

        show("decimal add", x.add(y));
        show("decimal subtract", x.subtract(y));
        show("decimal multiply", x.multiply(y));

        BigDecimal thousand = new BigDecimal("1E+3");
        BigDecimal small = new BigDecimal("2.50");

        show("negative-scale add", thousand.add(small));
        show("negative-scale multiply", thousand.multiply(small));

        show("zero add", new BigDecimal("2.00")
                .add(new BigDecimal("-2.00")));
        show("zero multiply", new BigDecimal("1.0")
                .multiply(new BigDecimal("0.00")));

        MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

        show("context add", a.add(b, mc));
        show("context subtract", a.subtract(b, mc));
        show("context multiply", a.multiply(b, mc));
        show("context carry", new BigDecimal("999.9")
                .add(new BigDecimal("0.2"), mc));

        show("setScale2", a.add(b)
                .setScale(2, RoundingMode.HALF_UP));

        BigDecimal p = new BigDecimal("1.20")
                .multiply(new BigDecimal("3.0"));
        BigDecimal q = new BigDecimal("3.60");

        System.out.println("equals 3.600 / 3.60 = "
                + p.equals(q));
        System.out.println("compare 3.600 / 3.60 = "
                + p.compareTo(q));
    }
}
```

Biên dịch/chạy:

```bash
javac BigDecimalOperationsScaleDemo.java
java BigDecimalOperationsScaleDemo
```

Đầu ra trên Java 17:

```text
add = 4.204 | scale=3 | precision=4
subtract = -1.804 | scale=3 | precision=4
multiply = 3.60480 | scale=5 | precision=6
decimal add = 0.30 | scale=2 | precision=2
decimal subtract = -0.10 | scale=2 | precision=2
decimal multiply = 0.020 | scale=3 | precision=2
negative-scale add = 1002.50 | scale=2 | precision=6
negative-scale multiply = 2.50E+3 | scale=-1 | precision=3
zero add = 0.00 | scale=2 | precision=1
zero multiply = 0.000 | scale=3 | precision=1
context add = 4.20 | scale=2 | precision=3
context subtract = -1.80 | scale=2 | precision=3
context multiply = 3.60 | scale=2 | precision=3
context carry = 1.00E+3 | scale=-1 | precision=3
setScale2 = 4.20 | scale=2 | precision=3
equals 3.600 / 3.60 = false
compare 3.600 / 3.60 = 0
```

Kết quả giúp phân biệt:

- Các phép **chính xác không context** chọn scale dựa trên scale toán hạng.
- `MathContext` có thể làm tròn chữ số và thay đổi scale.
- `setScale` diễn đạt số vị trí decimal được yêu cầu bởi schema.
- Hai kết quả có cùng giá trị toán học vẫn có thể khác nhau theo `equals` vì scale.

## 12. Những lỗi phổ biến

| Sai lầm | Điều xảy ra | Cách làm phù hợp |
| --- | --- | --- |
| Cộng hai `BigDecimal` rồi giữ nguyên scale của toán hạng thứ nhất | Kết quả chính xác dùng `max(scaleA,scaleB)` | Kiểm tra `result.scale()`; chuẩn hóa khi cần |
| Nghĩ scale của tích cũng là `max(scaleA,scaleB)` | Phép nhân chính xác dùng **tổng scale** | `scaleA + scaleB` |
| Mong `1.20 * 3.0` in `3.6` | Scale 3 cho `3.600` | Chọn định dạng `setScale`/formatter theo nghiệp vụ |
| Gọi `a.add(b);` mà không gán | Đối tượng `a` bất biến | `a = a.add(b);` nếu muốn cập nhật biến |
| Coi MathContext precision 2 là scale 2 | Precision tính chữ số có nghĩa | `setScale(2, roundingMode)` để có hai vị trí decimal |
| Nghĩ context không ảnh hưởng scale | Làm tròn có thể làm scale thay đổi | Kiểm tra cả value, precision và scale |
| Dùng `RoundingMode.UNNECESSARY` khi cần làm tròn | Ném `ArithmeticException` | Chọn rounding policy hoặc từ chối dữ liệu |
| Làm tròn từng hạng và sau khi cộng mà không xét khác biệt | Hai luồng tính có thể khác kết quả | Quy định rõ thời điểm làm tròn |
| `p.equals(q)` kiểm tra cùng giá trị toán học | Hai giá trị có scale khác nhau sẽ không equals | `p.compareTo(q) == 0` nếu chỉ so giá trị |
| Chuẩn hóa `stripTrailingZeros` mọi lúc | Có thể mất trailing zeros/scale âm | Chỉ chuẩn hóa khi hợp đồng cho phép |
| Nghĩ scale của zero luôn 0 | `0.000` có scale 3 | Giữ scale theo schema hoặc chính sách |
| Cho rằng scale không thể âm | Dạng `"1E+3"` có scale -3 | Dùng đúng mô hình unscaled × 10^-scale |
| Dùng `double` rồi new `BigDecimal(double)` | Mang sai số nhị phân vào phép decimal | Parse nguồn decimal từ chuỗi |
| Giữ kết quả exact cộng/trừ/nhân rồi mặc định phù hợp tất cả cách hiển thị | Scale toán học không tự bằng scale xuất báo cáo | Định dạng theo đơn vị và yêu cầu của hệ thống |
| Tin kết quả `BigDecimal` không thể gây lỗi tài nguyên | Scale/precision quá lớn có thể vượt giới hạn | Validate kích thước và miền đầu vào |

## 13. Bài tập có đáp án

**Bài 1.** Tính giá trị và scale của `new BigDecimal("1.20").add(new BigDecimal("3.004"))`.

**Đáp án:** `4.204`, scale 3 vì `max(2,3)=3`.

**Bài 2.** Cùng hai toán hạng trên, kết quả của `subtract` và `multiply` là gì?

**Đáp án:** `subtract = -1.804` (scale 3); `multiply = 3.60480` (scale 5 do `2+3=5`).

**Bài 3.** Tại sao `"0.10" + "0.2"` lại ra `"0.30"` thay vì in `"0.3"`?

**Đáp án:** Phép cộng chính xác có preferred scale 2, do toán hạng thứ nhất có scale 2. Hai chuỗi cùng giá trị số học nhưng biểu diễn `BigDecimal` có scale khác nhau.

**Bài 4.** `new BigDecimal("1E+3").multiply(new BigDecimal("2.50"))` có scale nào?

**Đáp án:** Scale -1, vì `-3+2=-1`. Giá trị toán học là 2500, `toString()` có thể in `"2.50E+3"`.

**Bài 5.** Vì sao `new BigDecimal("1.0").multiply(new BigDecimal("0.00"))` có thể in `"0.000"`?

**Đáp án:** Dù tích bằng 0, phép nhân chính xác giữ tổng scale `1+2=3`.

**Bài 6.** Nếu ứng dụng yêu cầu tổng được hiển thị với đúng hai chữ số decimal, phương thức nào diễn đạt rõ hơn: `new MathContext(2)` hay `setScale(2, HALF_UP)`?

**Đáp án:** `setScale(2, HALF_UP)` quy định đúng hai vị trí decimal; `MathContext(2)` giới hạn hai chữ số có nghĩa, không phải hai vị trí sau dấu chấm.

**Bài 7.** Vì sao `a.add(b, new MathContext(3, HALF_UP))` có thể trả `4.20` thay vì `4.204`?

**Đáp án:** MathContext chỉ cho tối đa ba chữ số có nghĩa, khiến tổng chính xác được làm tròn; scale cuối thay từ 3 thành 2.

**Bài 8.** `BigDecimal("3.600").equals(BigDecimal("3.60"))` là gì? `compareTo` cho gì?

**Đáp án:** `equals` là `false` vì scale lần lượt 3 và 2; `compareTo` là 0 vì cùng giá trị toán học.

**Bài 9.** Nêu một tình huống mà làm tròn từng dòng rồi cộng khác với cộng trước rồi làm tròn.

**Đáp án:** Hai dòng `0.005`, làm tròn `HALF_UP` mỗi dòng đến hai chữ số được `0.01+0.01=0.02`; cộng chính xác trước thành `0.010`, làm tròn hai chữ số được `0.01`. Phải theo quy tắc nghiệp vụ.

**Bài 10.** Với `BigDecimal a = new BigDecimal("10.00"); a.subtract(BigDecimal.ONE);`, sau khi chạy biến `a` là bao nhiêu nếu không gán kết quả?

**Đáp án:** `10.00`. `BigDecimal` bất biến, nên gọi `subtract` mà bỏ qua giá trị trả về không thay đổi `a`.

**Tóm tắt:** Trong phép tính **chính xác không truyền context**, `add` và `subtract` chọn scale lớn hơn của hai toán hạng, `multiply` cộng hai scale. Đây là quy tắc **biểu diễn kết quả**; nếu thêm `MathContext`, kết quả có thể làm tròn và đổi scale. `setScale` phục vụ yêu cầu cố định vị trí decimal, còn `compareTo` và `equals` có ý nghĩa khác nhau khi scale khác nhau. Giữ tính bất biến, dữ liệu nguồn decimal chính xác và chọn chính sách làm tròn trước khi áp dụng vào nghiệp vụ.