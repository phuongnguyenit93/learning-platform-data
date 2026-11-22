# Quy tắc làm tròn, đơn vị đo và kiểm tra tương thích khi tính toán

Trong một hệ thống bán hàng, phép tính `100000 + 50000` có vẻ đơn giản. Nhưng nếu hai giá trị là tiền ở hai loại tiền tệ khác nhau, phép cộng không còn hợp lệ. Nếu `100000` là đồng Việt Nam và `50000` là đô la Mỹ, cộng trực tiếp hai số sẽ tạo ra kết quả không có ý nghĩa. Tương tự, không thể cộng 2 mét với 3 kilogram, và cũng không thể tùy ý làm tròn mọi kết quả về hai chữ số thập phân.

Trong Domain-Driven Design (DDD), **Value Object** giúp biểu diễn những giá trị có ý nghĩa và quy tắc riêng như `Money`, `Length`, `Weight`, `Quantity`, `Percentage` hoặc `Temperature`. Khi các phép tính được đặt trên những kiểu giá trị này, mô hình có thể kiểm tra đơn vị, currency, độ chính xác và chính sách làm tròn trước khi tạo kết quả.

Độ chính xác không chỉ là vấn đề kỹ thuật. Cách làm tròn thuế, phí, giá bán, khối lượng tính cước hoặc thời lượng có thể ảnh hưởng đến quyền lợi khách hàng và kết quả kinh doanh. Vì vậy, quy tắc phải xuất phát từ domain, được xác nhận với chuyên gia và được thực thi nhất quán.

Sau bài học này, bạn có thể:

- Phân biệt độ chính xác (*precision*) và số chữ số thập phân (*scale*).
- Chọn và giải thích các chế độ làm tròn phổ biến.
- Xác định thời điểm và phạm vi áp dụng làm tròn trong một quy trình nghiệp vụ.
- Biểu diễn tiền và đại lượng đo bằng Value Object.
- Kiểm tra tính tương thích của currency, đơn vị và thứ nguyên trước khi tính toán.
- Thiết kế phép chuyển đổi đơn vị và tỷ giá có quy tắc rõ ràng.

## 1. Vì sao phép tính cần hiểu ngữ nghĩa của giá trị?

Một kiểu số như `int`, `long`, `double` hoặc `BigDecimal` chỉ biểu diễn giá trị số. Bản thân nó không cho biết số đó là tiền, số lượng sản phẩm, chiều dài, tỷ lệ phần trăm hay thời gian. Khi mọi đại lượng đều được truyền dưới dạng số, chương trình có thể thực hiện những phép tính hợp lệ về cú pháp nhưng sai về nghiệp vụ.

Ví dụ:

```java
BigDecimal total = price.add(weight);
```

Nếu `price` là tiền và `weight` là kilogram, trình biên dịch vẫn chấp nhận phép cộng vì cả hai cùng là `BigDecimal`. Nhưng kết quả không có ý nghĩa. Tương tự, phép cộng hai khoản tiền khác currency cũng không thể thực hiện trực tiếp.

Value Object đưa ngữ nghĩa vào kiểu dữ liệu:

```text
Money(100000, VND) + Money(50000, USD)  -> không tương thích
Length(2, METER) + Mass(3, KILOGRAM)    -> không tương thích
Length(2, METER) + Length(30, CM)       -> có thể tính sau khi đổi cùng đơn vị
Money(100000, VND) + Money(50000, VND)  -> hợp lệ nếu policy cho phép
```

Một phép tính đúng cần kiểm tra ít nhất ba điều:

1. **Loại giá trị:** hai toán hạng có cùng ý nghĩa domain hoặc có quan hệ toán học hợp lệ không?
2. **Đơn vị:** currency, đơn vị đo hoặc thứ nguyên có tương thích không?
3. **Quy tắc số học:** độ chính xác, làm tròn, giới hạn và thời điểm áp dụng có đúng policy không?

## 2. Precision và scale khác nhau thế nào?

Hai khái niệm thường bị nhầm lẫn khi xử lý số thập phân là *precision* và *scale*.

- **Precision** là tổng số chữ số có nghĩa được biểu diễn.
- **Scale** là số chữ số ở bên phải dấu thập phân trong biểu diễn `BigDecimal`.

Với `BigDecimal`, scale cũng có thể âm, chẳng hạn một giá trị được biểu diễn theo bội số của 10. Vì vậy, mô tả “số chữ số bên phải dấu thập phân” là cách hiểu phổ biến khi scale không âm, không phải toàn bộ khả năng biểu diễn của kiểu này.

Ví dụ với `123.450`:

| Giá trị | Precision | Scale |
|---|---:|---:|
| `123.450` | 6 | 3 |
| `123.45` | 5 | 2 |
| `123` | 3 | 0 |
| `0.0012` | 2 | 4 |

Scale không cho biết số chữ số có nghĩa. `0.0012` có scale 4 nhưng precision chỉ là 2. Precision và scale cũng không đồng nghĩa với độ chính xác nghiệp vụ: một số có thể được lưu đến 8 chữ số thập phân nhưng dữ liệu đầu vào chỉ chính xác đến 2 chữ số.

Trong Java, `BigDecimal` giữ cả giá trị số và scale. Ví dụ:

```java
BigDecimal a = new BigDecimal("12.5");
BigDecimal b = new BigDecimal("12.50");

System.out.println(a.compareTo(b) == 0); // true: cùng giá trị số
System.out.println(a.equals(b));         // false: scale khác nhau
```

`compareTo()` so sánh giá trị số, còn `equals()` xét cả giá trị và scale. Điều này quan trọng khi dùng `BigDecimal` bên trong Value Object. Nếu domain xem `12.5` và `12.50` là cùng một khoản tiền, mô hình cần chuẩn hóa scale hoặc định nghĩa equality phù hợp với quy tắc đó.

### Không dùng scale cố định cho mọi đại lượng

Không phải mọi tiền tệ đều có cùng số chữ số thập phân; cũng không phải mọi phép tính tiền đều nên làm tròn ngay theo số chữ số hiển thị. Một số currency có đơn vị nhỏ nhất bằng 1, một số có đơn vị nhỏ nhất bằng 0,01 hoặc 0,001. Ngoài ra, phép tính tỷ lệ, thuế, phân bổ chiết khấu hoặc quy đổi tỷ giá có thể cần giữ nhiều chữ số trung gian hơn trước khi làm tròn kết quả cuối.

Vì vậy, cần phân biệt:

- **Scale lưu trữ:** số chữ số thập phân mà cấu trúc dữ liệu có thể giữ.
- **Scale tính toán:** độ chính xác cần thiết trong các bước trung gian.
- **Scale thanh toán/ghi nhận:** độ chính xác cuối cùng mà nghiệp vụ hoặc quy định yêu cầu.
- **Scale hiển thị:** số chữ số được trình bày trên giao diện hoặc chứng từ.

Bốn mức này có thể giống nhau trong một use case đơn giản, nhưng không nên mặc định luôn giống nhau.

Trong database, kiểu `DECIMAL(p, s)` hoặc `NUMERIC(p, s)` thường dùng `p` làm precision và `s` làm scale. Ví dụ `DECIMAL(19, 4)` cho phép tối đa 19 chữ số, trong đó có 4 chữ số ở phần thập phân. Đây là giới hạn lưu trữ; nó không tự xác định cách tính thuế, làm tròn thanh toán hay định dạng giao diện.

## 3. Làm tròn là quyết định nghiệp vụ

Làm tròn (*rounding*) chuyển một giá trị có nhiều chữ số thành giá trị ở độ chính xác được chọn. Có nhiều cách làm tròn và chúng cho kết quả khác nhau ở những trường hợp biên.

Ví dụ, làm tròn `2.5` đến số nguyên có thể cho kết quả 3 hoặc 2 tùy chế độ. Với số âm, sự khác nhau càng dễ bị bỏ qua nếu chỉ kiểm tra số dương.

### Các chế độ làm tròn phổ biến

| Chế độ | Ý nghĩa | Ví dụ làm tròn đến số nguyên |
|---|---|---|
| `UP` | Làm tròn ra xa 0 khi phải bỏ chữ số khác 0 | `2.1 -> 3`, `-2.1 -> -3` |
| `DOWN` | Cắt phần dư, tiến về 0 | `2.9 -> 2`, `-2.9 -> -2` |
| `CEILING` | Làm tròn về phía dương vô cùng | `2.1 -> 3`, `-2.1 -> -2` |
| `FLOOR` | Làm tròn về phía âm vô cùng | `2.1 -> 2`, `-2.1 -> -3` |
| `HALF_UP` | Chọn gần nhất; trường hợp đúng nửa thì ra xa 0 | `2.5 -> 3`, `-2.5 -> -3` |
| `HALF_DOWN` | Chọn gần nhất; trường hợp đúng nửa thì về 0 | `2.5 -> 2`, `-2.5 -> -2` |
| `HALF_EVEN` | Chọn gần nhất; trường hợp đúng nửa thì chọn số có chữ số cuối chẵn | `2.5 -> 2`, `3.5 -> 4` |
| `UNNECESSARY` | Không cho phép mất độ chính xác; nếu phải làm tròn thì báo lỗi | `2.5 -> lỗi` khi làm tròn đến số nguyên |

Trong Java, các chế độ này được biểu diễn bằng `java.math.RoundingMode`.

### Ví dụ với HALF_UP và HALF_EVEN

```java
BigDecimal a = new BigDecimal("2.5");
BigDecimal b = new BigDecimal("3.5");

a.setScale(0, RoundingMode.HALF_UP);   // 3
b.setScale(0, RoundingMode.HALF_UP);   // 4

a.setScale(0, RoundingMode.HALF_EVEN); // 2
b.setScale(0, RoundingMode.HALF_EVEN); // 4
```

`HALF_EVEN` còn được gọi là làm tròn về số chẵn gần nhất (*banker's rounding*). Trong một số chuỗi phép tính, cách này giảm xu hướng luôn đẩy các trường hợp đúng nửa về cùng một phía. Nhưng không thể kết luận nó luôn phù hợp với nghiệp vụ tài chính. Hợp đồng, quy định, chuẩn kế toán hoặc chính sách của doanh nghiệp có thể yêu cầu `HALF_UP`, `DOWN` hay một quy tắc riêng.

### Kiểm tra cả số âm

Đừng chỉ viết test với số dương. `CEILING` và `FLOOR` có ý nghĩa khác nhau đối với số âm:

```java
new BigDecimal("-2.1").setScale(0, RoundingMode.CEILING); // -2
new BigDecimal("-2.1").setScale(0, RoundingMode.FLOOR);   // -3
```

Ví dụ, số âm có thể xuất hiện trong bút toán điều chỉnh, hoàn tiền hoặc khoản chênh lệch. Chọn sai chế độ có thể làm kết quả lệch theo hướng không mong muốn.

## 4. Làm tròn ở đâu trong một quy trình?

Không chỉ chế độ làm tròn, **thời điểm làm tròn** cũng ảnh hưởng đến kết quả. Một phép tính có thể làm tròn ở từng dòng, ở từng nhóm hoặc chỉ một lần trên tổng.

Giả sử có ba dòng thuế, mỗi dòng có số tiền chính xác là `0.335` và cần làm tròn đến hai chữ số thập phân bằng `HALF_UP`:

- Làm tròn từng dòng: `0.335 -> 0.34`; tổng ba dòng là `1.02`.
- Cộng trước rồi làm tròn: `0.335 × 3 = 1.005`; làm tròn tổng thành `1.01`.

Hai kết quả chênh nhau `0.01`. Không có một lựa chọn toán học chung có thể thay thế chính sách nghiệp vụ. Doanh nghiệp cần xác định cách tính thuế theo dòng hàng, theo hóa đơn, theo nhóm thuế hay theo quy định áp dụng.

Một quy trình tính tiền có thể có các mốc:

1. Giữ độ chính xác đủ cao khi tính đơn giá, tỷ lệ, chiết khấu và thuế.
2. Áp dụng quy tắc phân bổ nếu cần chia tổng tiền cho nhiều dòng.
3. Làm tròn tại đúng ranh giới được policy quy định.
4. Lưu số tiền đã ghi nhận để hóa đơn, thanh toán và báo cáo dùng cùng kết quả.
5. Trình bày theo quy tắc hiển thị mà không tự ý thay đổi giá trị đã ghi nhận.

Không nên làm tròn ở mọi bước chỉ vì giao diện hiển thị hai chữ số. Việc làm tròn sớm có thể tích lũy sai số; ngược lại, giữ quá nhiều chữ số đến bước cuối cũng không đúng nếu quy định yêu cầu làm tròn từng dòng.

### Làm tròn kết quả và làm tròn hiển thị

Giả sử hệ thống lưu kết quả tính là `12.34567`, nhưng màn hình hiển thị `12.35`. Nếu chỉ phục vụ xem, có thể định dạng khi trình bày mà không thay đổi dữ liệu gốc. Nếu đây là số tiền phải thu, phải áp dụng policy ghi nhận và lưu kết quả đã làm tròn theo quy định.

Hãy phân biệt rõ:

- `roundForSettlement`: làm tròn để xác định khoản tiền phải thanh toán.
- `formatForDisplay`: định dạng để người dùng đọc.

Không nên dùng cùng một hàm chung tên `round()` cho cả hai mục đích mà không thể hiện policy.

## 5. Money là Value Object có currency và chính sách làm tròn

Tiền không chỉ là một số thập phân. Một khoản tiền tối thiểu phải có:

- **Amount:** giá trị số.
- **Currency:** loại tiền tệ.

Trong một số domain, Money còn cần quy tắc về scale, rounding, giới hạn, đơn vị nhỏ nhất hoặc cách quy đổi.

### Phép cộng và trừ

Chỉ cộng hoặc trừ trực tiếp hai khoản tiền khi currency tương thích:

```text
Money(100000, VND) + Money(50000, VND) = Money(150000, VND)
Money(100, USD) - Money(25, USD)       = Money(75, USD)
Money(100, USD) + Money(50, EUR)       = không hợp lệ
```

Nếu cần cộng khác currency, phải có bước quy đổi tường minh với tỷ giá, nguồn tỷ giá, thời điểm hiệu lực và chính sách làm tròn. Không nên âm thầm lấy một currency làm currency kết quả.

### Phép nhân và chia

Có thể nhân Money với một hệ số không có đơn vị, chẳng hạn thuế suất hoặc số lượng. Kết quả cần được xử lý theo scale và rounding policy của use case.

```text
Money(100000, VND) × Rate(0.10) = Money(10000, VND)
Money(120000, VND) ÷ 3         = giá trị cần policy phân bổ/làm tròn
```

Chia một khoản tiền cho nhiều phần thường tạo số dư lẻ. Domain phải quyết định phần dư được phân bổ cho dòng nào, giữ lại ở tài khoản nào hoặc xử lý ra sao. Không nên để lỗi sai số hoặc cách chia của thư viện tự quyết định kết quả nghiệp vụ.

### Currency fraction digits không phải policy duy nhất

Java `Currency.getDefaultFractionDigits()` cung cấp số chữ số thập phân mặc định theo dữ liệu currency. Đây là thông tin hữu ích để định dạng hoặc kiểm tra một số giao dịch, nhưng không đủ để quyết định toàn bộ phép tính.

Ví dụ, VND thường được hiển thị và thanh toán theo đơn vị nguyên, nhưng một mô hình có thể cần giữ phần thập phân trong bước phân bổ hoặc tính giá nội bộ trước khi tổng hợp. Một currency có hai chữ số mặc định cũng không có nghĩa mọi phép tính trung gian đều phải làm tròn ở scale 2.

Hãy để policy của domain xác định scale và rounding mode cho từng mục đích: giá niêm yết, thuế, phí, thanh toán, hoàn tiền, quy đổi và hiển thị.

## 6. Value Object cho tỷ lệ, thuế và phần trăm

Phần trăm là một nguồn nhầm lẫn phổ biến. `10%` có thể được biểu diễn bằng `10`, `0.10` hoặc `1000` basis points. Nếu không thống nhất, phép nhân có thể sai gấp 100 hoặc 10.000 lần.

Một cách biểu diễn rõ ràng là dùng `Rate` với quy ước giá trị thập phân:

```text
Rate(0.10) = 10%
Rate(0.075) = 7.5%
```

Hoặc dùng basis points nếu domain thường làm việc với các bước 0,01%:

```text
100 basis points = 1%
750 basis points = 7.5%
```

Không nên trộn hai quy ước trong cùng một kiểu dữ liệu. Tên kiểu và factory method cần thể hiện đơn vị đầu vào, chẳng hạn `Rate.fromDecimal(0.10)` hoặc `Rate.fromBasisPoints(1000)`.

### Tính thuế

Giả sử giá tính thuế là `250000 VND`, thuế suất là `8%`:

```text
Tax = 250000 × 0.08 = 20000 VND
```

Nếu kết quả có phần thập phân, policy phải xác định làm tròn theo từng dòng hay theo tổng, scale nào và chế độ nào. Với nhiều mức thuế, miễn giảm hoặc thời điểm hiệu lực, `TaxRate` và `TaxPolicy` có thể là các khái niệm riêng trong domain.

Không nên dùng một hằng số `0.08` rải rác khắp code. Một Value Object `Rate` hoặc policy có tên giúp người đọc biết đây là thuế suất, chiết khấu hay tỷ lệ phân bổ.

## 7. Đơn vị đo và thứ nguyên

Đơn vị đo (*unit of measure*) cho biết một đại lượng đang được biểu diễn theo cách nào. Thứ nguyên (*dimension*) mô tả loại đại lượng, chẳng hạn chiều dài, khối lượng, thời gian, thể tích hoặc nhiệt độ.

Ví dụ:

| Đại lượng | Đơn vị | Ví dụ |
|---|---|---|
| Chiều dài | mét (m), centimet (cm), inch (in) | `Length(2, METER)` |
| Khối lượng | kilogram (kg), gram (g) | `Mass(1.5, KILOGRAM)` |
| Thể tích | lít (L), milliliter (mL) | `Volume(500, MILLILITER)` |
| Thời gian | giây (s), phút (min), giờ (h) | `Duration(30, MINUTE)` |
| Nhiệt độ | độ Celsius (°C), Fahrenheit (°F), Kelvin (K) | `Temperature(25, CELSIUS)` |
| Diện tích | mét vuông (m²), centimet vuông (cm²) | `Area(12, SQUARE_METER)` |

Một đại lượng có thể được biểu diễn bằng nhiều đơn vị cùng thứ nguyên. 2 mét và 30 centimet đều là chiều dài nên có thể đổi về cùng đơn vị để cộng. 2 mét và 3 kilogram thuộc hai thứ nguyên khác nhau nên không thể cộng.

### Quy tắc tương thích khi cộng và trừ

Phép cộng và trừ thường yêu cầu cùng thứ nguyên và cùng hệ đơn vị sau khi chuẩn hóa:

```text
2 m + 30 cm = 2.30 m
1.5 kg + 250 g = 1.75 kg
2 m + 3 kg = không hợp lệ
```

Có thể cho phép cộng hai đơn vị khác nhau nếu chúng cùng thứ nguyên và có quy tắc chuyển đổi xác định. Nhưng không nên tự động chuyển đổi khi đơn vị thuộc những hệ hoặc quy ước khác nhau mà chưa rõ ý nghĩa.

### Phép nhân và chia tạo thứ nguyên mới

Không phải mọi phép toán đều yêu cầu cùng thứ nguyên:

- Chiều dài × chiều dài → diện tích.
- Diện tích × chiều dài → thể tích.
- Khối lượng ÷ thể tích → khối lượng riêng.
- Quãng đường ÷ thời gian → tốc độ.
- Tiền ÷ số lượng → đơn giá trên một đơn vị.

Những phép tính này cần kiểu kết quả biểu diễn đúng thứ nguyên mới. Nếu tất cả đều trả về `BigDecimal`, code sẽ mất thông tin quan trọng về đơn vị.

## 8. Chuyển đổi đơn vị phải tường minh

Để cộng hoặc so sánh hai đại lượng cùng thứ nguyên, có thể chuyển chúng về một đơn vị chuẩn trong domain. Ví dụ, chiều dài được chuẩn hóa về mét, khối lượng về kilogram hoặc thời gian về giây.

Với chuyển đổi tuyến tính:

```text
1 m = 100 cm
1 km = 1000 m
1 kg = 1000 g
1 h = 60 min = 3600 s
```

Nếu đơn vị nguồn có giá trị `v` và hệ số chuyển đổi sang đơn vị chuẩn là `f`, giá trị chuẩn được tính là `v × f`. Khi đổi ngược, cần chia cho hệ số tương ứng.

Một chuyển đổi có thể chính xác hoặc tạo số thập phân vô hạn. Ví dụ, đổi một số lượng inch sang centimet theo hệ số 2,54 có thể biểu diễn chính xác bằng decimal hữu hạn. Nhưng các chuyển đổi như Fahrenheit sang Celsius có phép chia 9 và có thể tạo số thập phân lặp. Khi đó cần một policy precision và rounding.

### Nhiệt độ là ví dụ không chỉ nhân với hệ số

Chuyển đổi Celsius sang Fahrenheit cần cả hệ số và độ lệch:

\[
F = C \times \frac{9}{5} + 32
\]

Vì vậy, không thể mô hình mọi phép đổi đơn vị bằng một hệ số nhân. Một số đơn vị có công thức affine hoặc quy tắc riêng. Cần dùng converter theo loại đại lượng và xác định độ chính xác khi chia.

### Không làm tròn quá sớm khi đổi đơn vị

Nếu một phép chuyển đổi được dùng cho quyết định chính xác, hãy giữ precision trung gian đủ cao rồi mới áp dụng rounding policy tại ranh giới được domain xác định. Nếu chuyển đổi chỉ phục vụ hiển thị, có thể định dạng kết quả mà không thay đổi giá trị chuẩn.

## 9. Java Value Object cho Money

Ví dụ sau minh họa cách giữ amount và currency cùng nhau, kiểm tra currency khi cộng và yêu cầu policy khi làm tròn.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount is required");
        Objects.requireNonNull(currency, "currency is required");
        // Chuẩn hóa biểu diễn để 10.0 và 10.00 có cùng dạng số.
        amount = amount.stripTrailingZeros();
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money subtract(Money other) {
        requireSameCurrency(other);
        return new Money(amount.subtract(other.amount), currency);
    }

    public Money multiply(BigDecimal factor) {
        Objects.requireNonNull(factor, "factor is required");
        return new Money(amount.multiply(factor), currency);
    }

    public Money round(int scale, RoundingMode mode) {
        return new Money(amount.setScale(scale, mode), currency);
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other, "other is required");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency mismatch");
        }
    }
}
```

Đây là Value Object minh họa. Trong ứng dụng thực tế, có thể cần giới hạn amount, hỗ trợ policy scale riêng, kiểm soát số âm, định nghĩa phép chia và quy tắc equality theo domain. `stripTrailingZeros()` giúp chuẩn hóa biểu diễn số cho ví dụ này, nhưng không thay thế policy làm tròn hoặc quy tắc lưu trữ.

Một policy có thể được biểu diễn riêng:

```java
import java.math.RoundingMode;
import java.util.Objects;

public record MoneyRoundingPolicy(int scale, RoundingMode mode) {
    public MoneyRoundingPolicy {
        Objects.requireNonNull(mode);
    }
}
```

Application/domain service có thể chọn policy theo use case: tính thuế, thanh toán, hoàn tiền hoặc hiển thị. Không nên để `Money` tự đoán quy tắc nghiệp vụ dựa trên tên currency nếu domain có policy riêng.

### Tạo BigDecimal đúng cách

Không nên tạo `BigDecimal` từ literal `double` như sau:

```java
new BigDecimal(0.1); // Có thể giữ biểu diễn nhị phân xấp xỉ của double
```

Hãy tạo từ chuỗi thập phân hoặc dữ liệu decimal chính xác:

```java
new BigDecimal("0.1");
BigDecimal.valueOf(0.1); // Chuyển từ biểu diễn thập phân của double
```

Với dữ liệu tài chính, đọc chuỗi decimal từ request/database thường là cách rõ ràng nhất. `BigDecimal` tránh sai số nhị phân của `double`, nhưng không tự chọn scale hoặc rounding policy cho domain.

Một điểm cần chú ý là phép chia có thể tạo ra số thập phân vô hạn. Chẳng hạn `1 / 3` không có biểu diễn thập phân hữu hạn. Gọi `divide()` mà không chỉ định scale hoặc `MathContext` có thể ném `ArithmeticException`. Hãy chọn rõ precision và rounding mode cho phép chia:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal third = BigDecimal.ONE.divide(
    new BigDecimal("3"), 8, RoundingMode.HALF_EVEN
); // 0.33333333
```

## 10. Java Value Object cho chiều dài và đơn vị

Ví dụ sau chuẩn hóa chiều dài về mét. Việc cộng luôn thực hiện trên giá trị chuẩn; việc hiển thị theo đơn vị khác được thực hiện qua phương thức chuyển đổi.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

enum LengthUnit {
    METER("1"),
    CENTIMETER("0.01"),
    KILOMETER("1000"),
    INCH("0.0254");

    private final BigDecimal metersPerUnit;

    LengthUnit(String metersPerUnit) {
        this.metersPerUnit = new BigDecimal(metersPerUnit);
    }

    BigDecimal toMeters(BigDecimal value) {
        return value.multiply(metersPerUnit);
    }

    BigDecimal fromMeters(BigDecimal meters, int scale, RoundingMode mode) {
        return meters.divide(metersPerUnit, scale, mode);
    }
}

public record Length(BigDecimal meters) {
    public Length {
        Objects.requireNonNull(meters);
        meters = meters.stripTrailingZeros();
    }

    public static Length of(BigDecimal value, LengthUnit unit) {
        Objects.requireNonNull(unit);
        return new Length(unit.toMeters(value));
    }

    public Length add(Length other) {
        return new Length(meters.add(other.meters));
    }

    public Length subtract(Length other) {
        return new Length(meters.subtract(other.meters));
    }

    public BigDecimal in(LengthUnit unit, int scale, RoundingMode mode) {
        return unit.fromMeters(meters, scale, mode);
    }
}
```

Ví dụ sử dụng:

```java
Length total = Length.of(new BigDecimal("2"), LengthUnit.METER)
    .add(Length.of(new BigDecimal("30"), LengthUnit.CENTIMETER));

BigDecimal centimeters = total.in(
    LengthUnit.CENTIMETER, 2, RoundingMode.UNNECESSARY
); // 230.00
```

Ví dụ này chọn mét làm đơn vị chuẩn và chỉ làm tròn khi chuyển đổi/hiển thị. Trong domain thực tế, cần xác định giới hạn giá trị, độ chính xác đo, cách xử lý số âm và việc có cho phép đơn vị khác hệ hay không.

Không nên tạo một `Quantity` chung chỉ chứa `BigDecimal value` và `String unit` rồi cho mọi nơi tự cộng. Các kiểu riêng như `Length`, `Mass`, `Volume` hoặc một generic type có kiểm soát dimension giúp ngăn nhầm đơn vị ngay trong API.

## 11. Kiểm tra tương thích theo phép toán

Không phải phép toán nào cũng yêu cầu cùng đơn vị. Quy tắc cần được xác định theo thứ nguyên và ý nghĩa của kết quả.

| Phép toán | Điều kiện tương thích | Kiểu kết quả ví dụ |
|---|---|---|
| Length + Length | Cùng thứ nguyên; chuyển về đơn vị chuẩn | Length |
| Mass - Mass | Cùng thứ nguyên; chuyển về đơn vị chuẩn | Mass |
| Money + Money | Cùng currency hoặc có conversion tường minh | Money |
| Length × Length | Đơn vị có thể nhân theo quy tắc dimension | Area |
| Mass ÷ Volume | Cùng hệ quy đổi phù hợp | Density |
| Money ÷ Quantity | Quantity khác 0 và có đơn vị xác định | UnitPrice hoặc MoneyPerUnit |
| Money × Rate | Rate không có thứ nguyên hoặc có ý nghĩa tỷ lệ rõ | Money |
| Temperature + Temperature | Không phải phép toán thông thường trong mọi domain | Cần xác định ý nghĩa vật lý/nghiệp vụ |

Nhiều phép toán có vẻ hợp lệ về mặt số học nhưng không hợp lệ về mặt domain. Ví dụ, cộng hai nhiệt độ tuyệt đối có thể không có ý nghĩa; cộng một độ chênh nhiệt độ vào nhiệt độ tuyệt đối thì có. Nếu domain làm việc với nhiệt độ, có thể cần phân biệt `Temperature` và `TemperatureDelta`.

### Kiểm tra currency khi quy đổi

Không nên viết:

```java
Money total = usd.add(eur); // Không hợp lệ nếu chưa quy đổi
```

Một thao tác quy đổi cần thông tin rõ:

- Currency nguồn và đích.
- Tỷ giá và chiều áp dụng tỷ giá.
- Nguồn cung cấp tỷ giá.
- Thời điểm hoặc ngày hiệu lực.
- Precision trung gian và rounding policy.
- Mục đích quy đổi: báo cáo, báo giá, thanh toán hay quyết toán.

Ví dụ, `100 USD` đổi sang VND không chỉ là phép nhân với một con số bất kỳ. Tỷ giá có thể thay đổi theo thời gian, nguồn và loại giao dịch. Một `ExchangeRate` hoặc dịch vụ domain có thể biểu diễn những thông tin này.

## 12. Đơn vị trong các quy tắc nghiệp vụ thực tế

### Khối lượng tính cước

Một đơn vị vận chuyển có thể tính phí theo khối lượng thực hoặc khối lượng quy đổi theo kích thước kiện hàng. Công thức có thể dùng:

\[
\text{Volumetric Weight} = \frac{L \times W \times H}{\text{Divisor}}
\]

Trong đó chiều dài, chiều rộng và chiều cao phải cùng hệ đơn vị; divisor có đơn vị tương ứng để kết quả ra kilogram hoặc đơn vị khối lượng quy định. Nếu một giá trị là centimet còn giá trị khác là mét, phép nhân trực tiếp sẽ sai.

Policy còn có thể yêu cầu làm tròn lên theo bậc 0,5 kg hoặc 1 kg. Đây là quy tắc tính cước của domain, không phải cách định dạng số. Ví dụ, `2.1 kg` có thể được tính cước thành `2.5 kg` nếu hợp đồng vận chuyển quy định làm tròn lên từng nửa kilogram.

### Số lượng hàng hóa

Số lượng có thể là số nguyên đối với sản phẩm đếm được như chiếc áo hoặc quyển sách. Nhưng hàng hóa cân đo như gạo, vải hoặc nhiên liệu có thể cần số thập phân và đơn vị cụ thể.

`Quantity(1, PIECE)` và `Quantity(1, KILOGRAM)` không thể thay thế nhau. Với hàng bán theo cân, domain cần xác định độ chính xác cân, đơn vị gốc, dung sai và cách làm tròn khi tính tiền.

### Thời lượng và tính phí theo thời gian

Một dịch vụ có thể tính phí theo phút, giờ hoặc ngày. `Duration(90, MINUTE)` tương đương `Duration(1.5, HOUR)` nếu quy tắc domain dùng giờ 60 phút. Tuy nhiên, thời gian tính phí có thể làm tròn lên từng 15 phút hoặc tính tròn theo ngày lịch. Không nên dùng phép đổi đơn vị vật lý để thay thế policy tính phí.

Ví dụ, thời lượng thực tế 61 phút có thể được tính là 2 giờ nếu hợp đồng quy định làm tròn lên theo giờ. Một hệ thống khác có thể tính chính xác theo phút. Cả hai đều có thể đúng trong domain tương ứng.

## 13. Kiểm tra đầu vào và giới hạn hợp lệ

Value Object nên bảo vệ những quy tắc hợp lệ cơ bản của giá trị. Ví dụ:

- Money cần currency hợp lệ và có thể giới hạn giá trị âm tùy ngữ cảnh.
- Quantity có thể phải lớn hơn 0 khi đặt hàng, nhưng cho phép số âm trong một bút toán điều chỉnh.
- Percentage có thể nằm trong khoảng 0 đến 1 hoặc 0 đến 100 tùy cách biểu diễn.
- Length có thể không âm trong một số use case.
- Duration có thể cho phép số âm nếu biểu diễn chênh lệch thời gian có hướng, nhưng không nếu là thời lượng dịch vụ.

Không nên đặt một validation toàn cục nếu các ngữ cảnh có quy tắc khác nhau. Ví dụ, `Money` dùng cho khoản hoàn có thể cho phép amount âm để biểu diễn bút toán, trong khi `PaymentRequest` có thể yêu cầu số tiền dương. Quy tắc nên nằm ở Value Object hoặc hành vi phù hợp với ý nghĩa domain, không áp đặt tùy tiện cho mọi use case.

## 14. Quy trình thiết kế một phép tính an toàn

Khi thêm một phép tính vào domain model, hãy đi qua các bước sau:

**Bước 1: Xác định ý nghĩa của từng toán hạng.** Giá trị là tiền, tỷ lệ, số lượng, khối lượng, chiều dài hay thời gian?

**Bước 2: Xác định thứ nguyên và đơn vị.** Hai giá trị có cùng dimension không? Nếu khác đơn vị, quy tắc chuyển đổi là gì?

**Bước 3: Xác định miền giá trị hợp lệ.** Có cho phép số âm, zero, null hoặc giá trị vượt giới hạn không?

**Bước 4: Xác định precision trung gian.** Phép nhân/chia có thể tạo số thập phân lặp không? Cần giữ bao nhiêu chữ số để tránh sai lệch đáng kể?

**Bước 5: Xác định rounding policy.** Chế độ nào, scale nào và làm tròn ở từng dòng hay trên tổng?

**Bước 6: Xác định thời điểm ghi nhận.** Kết quả nào được lưu như sự thật nghiệp vụ? Giá trị nào chỉ dùng để hiển thị?

**Bước 7: Đặt phép tính vào đúng nơi.** Quy tắc có thể thuộc Value Object, Entity/Aggregate hoặc Domain Service tùy trách nhiệm và dữ liệu cần thiết.

**Bước 8: Kiểm thử trường hợp biên.** Bao gồm số âm, số đúng nửa, giá trị rất nhỏ/lớn, currency khác nhau, đơn vị khác nhau và phép chia không hết.

## 15. Kiểm thử quy tắc làm tròn và tương thích

Đừng chỉ kiểm tra một ví dụ thông thường. Một bộ test có ích nên bao gồm:

| Nhóm | Trường hợp cần kiểm tra |
|---|---|
| Rounding tie | `2.5`, `3.5`, `-2.5` với các mode phù hợp |
| Giá trị sát biên | `2.499`, `2.500`, `2.501` khi làm tròn đến số nguyên |
| Scale | `10`, `10.0`, `10.00` và equality của Value Object |
| Currency | Cộng cùng currency, cộng khác currency, quy đổi có tỷ giá |
| Unit conversion | Mét–centimet, kilogram–gram, đơn vị không tương thích |
| Phép chia | Chia hết, chia lặp vô hạn, chia cho zero |
| Giá trị âm | Hoàn tiền, điều chỉnh và `CEILING`/`FLOOR` |
| Phân bổ | Làm tròn từng dòng so với làm tròn tổng |
| Giới hạn | Giá trị lớn nhất, nhỏ nhất, quantity zero hoặc âm |

Ví dụ test với JUnit:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import org.junit.jupiter.api.Test;

class RoundingPolicyTest {
    @Test
    void halfEvenRoundsTiesToEven() {
        assertEquals(new BigDecimal("2"),
            new BigDecimal("2.5").setScale(0, RoundingMode.HALF_EVEN));
        assertEquals(new BigDecimal("4"),
            new BigDecimal("3.5").setScale(0, RoundingMode.HALF_EVEN));
    }

    @Test
    void additionRejectsDifferentCurrencies() {
        Money usd = new Money(new BigDecimal("10"), Currency.getInstance("USD"));
        Money eur = new Money(new BigDecimal("5"), Currency.getInstance("EUR"));

        assertThrows(IllegalArgumentException.class, () -> usd.add(eur));
    }
}
```

Test minh họa cần các import và cấu hình JUnit phù hợp với project. Trong bộ test thực tế, hãy kiểm tra cả kết quả nghiệp vụ lẫn việc phép tính không tương thích bị từ chối.

## 16. Những sai lầm thường gặp

**Dùng `double` cho tiền hoặc đại lượng cần decimal chính xác.** Số dấu phẩy động nhị phân có thể không biểu diễn chính xác nhiều phân số thập phân. Dùng `BigDecimal` hoặc kiểu decimal phù hợp và quy định cách tạo giá trị.

**Làm tròn tất cả về hai chữ số.** Currency, thuế, tỷ lệ, khối lượng và đơn vị đo có policy khác nhau. Scale phải đến từ domain.

**Làm tròn sau mỗi phép tính.** Điều này có thể tích lũy sai lệch. Chỉ làm tròn tại ranh giới được policy xác định.

**Không phân biệt làm tròn và cắt phần dư.** `DOWN` tiến về 0, trong khi `FLOOR` tiến về âm vô cùng. Hai chế độ khác nhau với số âm.

**Cộng tiền khác currency.** Cần quy đổi tường minh với tỷ giá và thời điểm hiệu lực.

**Cộng các đại lượng khác thứ nguyên.** `Length` và `Mass` không thể cộng dù cùng được lưu bằng `BigDecimal`.

**Dùng một kiểu `Quantity` không có đơn vị.** Giá trị `10` không cho biết là 10 chiếc, 10 kilogram hay 10 lít.

**Dùng hệ số đổi đơn vị nhưng quên độ lệch.** Một số phép đổi như Celsius–Fahrenheit không chỉ nhân với một hệ số.

**Để giao diện quyết định quy tắc tính.** Định dạng hiển thị không nên thay đổi số tiền hoặc đại lượng đã được domain ghi nhận.

**Dùng `Currency.getDefaultFractionDigits()` làm policy duy nhất.** Metadata currency hữu ích nhưng không thay thế quy tắc tính toán của từng nghiệp vụ.

## 17. Bài tập tự kiểm tra

Một cửa hàng bán cà phê theo kilogram, tính phí giao hàng theo khối lượng quy đổi và áp dụng thuế suất phần trăm. Một đơn có ba dòng hàng. Hệ thống nhận giá trị từ nhiều nguồn và phải tạo hóa đơn.

Hãy trả lời:

1. Nên dùng những Value Object nào để biểu diễn tiền, thuế suất, khối lượng và kích thước kiện hàng?
2. Có thể cộng `1.2 kg` với `300 g` không? Cần chuyển đổi như thế nào?
3. Có thể cộng `1.2 kg` với `300 ml` không? Vì sao?
4. Nếu thuế của từng dòng có nhiều chữ số thập phân, doanh nghiệp cần xác định policy làm tròn nào?
5. Nếu tổng thuế được tính khác với tổng các dòng thuế đã làm tròn, cần xử lý phần chênh lệch thế nào?
6. Nếu phí vận chuyển được làm tròn lên từng 0,5 kg, đó là quy tắc hiển thị hay nghiệp vụ?
7. Nếu khách thanh toán bằng USD trong khi giá bán được ghi bằng VND, cần những thông tin nào để quy đổi?

Gợi ý:

- Dùng `Money(amount, currency)`, `Rate`, `Mass`, `Length` và các Value Object có đơn vị rõ ràng.
- `1.2 kg + 300 g` hợp lệ sau khi đổi `300 g` thành `0.3 kg`, kết quả là `1.5 kg`.
- `kg` và `ml` là khối lượng và thể tích, không thể cộng trực tiếp. Nếu cần suy ra khối lượng từ thể tích, phải có mật độ phù hợp với loại hàng và điều kiện đo.
- Làm tròn thuế theo dòng hay tổng phải theo policy và quy định áp dụng. Cần test để tránh chênh lệch không giải thích được.
- Làm tròn khối lượng tính cước lên từng 0,5 kg là quy tắc tính phí nếu nó ảnh hưởng số tiền khách phải trả.
- Quy đổi USD/VND cần tỷ giá, nguồn, thời điểm hiệu lực, chiều tỷ giá, scale trung gian và rounding policy.

## Kết luận

Các phép tính trong domain cần hiểu ngữ nghĩa của giá trị, đơn vị và quy tắc số học. `BigDecimal` giúp biểu diễn số thập phân chính xác hơn `double`, nhưng không tự quyết định precision, scale hoặc cách làm tròn. Những quyết định đó phải được mô hình hóa thành policy phù hợp với nghiệp vụ.

Value Object như `Money`, `Rate`, `Length`, `Mass` và `Duration` giúp đưa currency, thứ nguyên, đơn vị và giới hạn hợp lệ vào kiểu dữ liệu. Khi cộng, trừ, nhân, chia hoặc quy đổi, hệ thống có thể kiểm tra tính tương thích trước khi tính. Hãy xác định rõ nơi làm tròn, giữ đủ precision trung gian, kiểm thử trường hợp biên và lưu kết quả đã ghi nhận theo đúng policy. Nhờ đó, các phép tính trở nên dễ hiểu, nhất quán và có thể giải thích trong suốt vòng đời hệ thống.
