# Phân biệt `setScale` với `round(MathContext)` trong Java BigDecimal

## 1. Hai cách làm tròn phục vụ hai câu hỏi khác nhau

Khi tính số thập phân trong Java, `java.math.BigDecimal` có hai phương thức thường bị nhầm là tương đương:

```java
BigDecimal resultA = value.setScale(2, RoundingMode.HALF_UP);
BigDecimal resultB = value.round(new MathContext(2, RoundingMode.HALF_UP));
```

Cùng dùng số `2` và chế độ `HALF_UP`, nhưng **ý nghĩa của số 2 hoàn toàn khác nhau**:

- `setScale(2, ...)` đặt **scale = 2**, tức có hai chữ số sau dấu thập phân trong biểu diễn thập phân chuẩn của số. Nếu cần, giá trị được làm tròn; nếu đang thiếu chữ số, các số 0 được thêm vào.
- `round(new MathContext(2, ...))` giới hạn kết quả còn **tối đa hai chữ số có nghĩa** (*precision*). Vị trí dấu thập phân sẽ tùy độ lớn của số.

Hãy bắt đầu với một ví dụ cụ thể:

```java
BigDecimal x = new BigDecimal("123.4567");
BigDecimal a = x.setScale(2, RoundingMode.HALF_UP); // 123.46
BigDecimal b = x.round(new MathContext(2, RoundingMode.HALF_UP)); // 1.2E+2, giá trị 120
```

`a` giữ hai chữ số **sau dấu chấm**, còn `b` giữ hai chữ số **có nghĩa tính từ chữ số đầu tiên khác 0**. Do đó `setScale(2)` tuyệt đối không thể thay bằng `MathContext(2)` nếu đặc tả yêu cầu “hiển thị hai chữ số thập phân”.

| Tiêu chí | `setScale(newScale, mode)` | `round(MathContext)` |
|---|---|---|
| Tham số đếm chữ số | `newScale`: vị trí dấu thập phân | `MathContext.precision`: tổng chữ số có nghĩa tối đa |
| Quan tâm đến độ lớn số? | Scale được ấn định dù số lớn hay nhỏ | Vị trí làm tròn thay đổi theo độ lớn số |
| Có thể thêm số 0 ở cuối? | Có, khi tăng scale | Không có mục tiêu đệm đủ chữ số sau dấu thập phân |
| Có thể thay đổi scale? | Có: trả kết quả với **scale đúng bằng** `newScale` nếu thành công | Có thể: scale của kết quả phụ thuộc precision và việc làm tròn |
| Số chữ số có nghĩa của kết quả | Không bị giới hạn bởi `newScale` | Không vượt `precision` dương (theo biểu diễn kết quả) |
| Ứng dụng thường gặp | Tiền có hai số thập phân, làm tròn đến 0,001, định dạng đầu ra | Chia số, tính toán gần đúng, quy định số chữ số có nghĩa trong kết quả |

Cả hai đều là thao tác **trả về `BigDecimal`**; đối tượng gốc là bất biến và không tự thay đổi.

## 2. Nền tảng: `scale()` và `precision()` đo những gì?

Với `BigDecimal`, giá trị toán học được tính theo công thức:

```text
value = unscaledValue × 10^(-scale)
```

`scale()` lưu số mũ thập phân theo cách biểu diễn nội bộ; `precision()` đếm số chữ số trong unscaled value (không tính dấu). Những chữ số 0 ở cuối của dạng nhập có thể ảnh hưởng đến hai thuộc tính này.

```java
BigDecimal n = new BigDecimal("123.4500");
System.out.println(n.precision()); // 7
System.out.println(n.scale());     // 4
```

- `123.4500` chứa **bảy chữ số** trong unscaled value `1234500`.
- Có **bốn chữ số sau dấu chấm** nên scale là 4.
- `new BigDecimal("123.45")` có cùng giá trị toán học nhưng precision 5 và scale 2.
- `new BigDecimal("1E+3")` có giá trị 1000, precision 1, scale -3.

Bảng này giúp thấy tại sao hai lối làm tròn khác nhau:

| Số nhập từ chuỗi | Precision | Scale | `setScale(2, HALF_UP)` | `round(MathContext(2, HALF_UP))` |
|---|---:|---:|---|---|
| `123.456` | 6 | 3 | `123.46` | `1.2E+2` (120) |
| `12.345` | 5 | 3 | `12.35` | `12` |
| `0.001234` | 4 | 6 | `0.00` | `0.0012` |
| `1.2` | 2 | 1 | `1.20` | `1.2` |
| `9.995` | 4 | 3 | `10.00` | `10` (thường biểu diễn dưới dạng `1.0E+1`) |

**Chú ý hàng cuối:** khi kết quả làm tròn vượt qua ngưỡng `9...9`, số có thể đổi độ lớn. Với context precision 2, đối tượng có thể dùng dạng khoa học để giữ đúng hai chữ số có nghĩa. Vì thế đừng dùng số chữ số của chuỗi `toPlainString()` làm cách xác định precision: `1.2E+2` và `120` có thể biểu diễn cùng một đối tượng nhưng khác cách in.

## 3. `setScale`: yêu cầu độ phân giải thập phân cố định

Có hai overload phổ biến:

```java
BigDecimal x = new BigDecimal("12.3456");

BigDecimal a = x.setScale(2, RoundingMode.HALF_UP); // 12.35
BigDecimal b = x.setScale(4);                       // 12.3456, không cần làm tròn
```

`setScale(int newScale, RoundingMode roundingMode)` luôn trả kết quả có `scale() == newScale`, trừ khi không thể thực hiện và ném ngoại lệ.

- **Giảm scale:** bỏ bớt vị trí thập phân, cần làm tròn nếu các chữ số bị loại không đều là 0. Ví dụ `12.3456 → 12.35` với scale 2 và `HALF_UP`.
- **Tăng scale:** giữ nguyên giá trị số và thêm số 0 vào phần thập phân. `new BigDecimal("1.2").setScale(4)` cho `1.2000`; precision mới là 5 và scale mới là 4.
- **Giữ scale:** không cần đổi giá trị, kết quả tiếp tục là biểu diễn có scale đó.
- **Scale âm:** hợp lệ, nghĩa là làm tròn theo chục, trăm, nghìn... Ví dụ `new BigDecimal("1234").setScale(-2, RoundingMode.HALF_UP)` có giá trị `1200`, thường được in bằng ký pháp mũ.

`setScale(int newScale)` không có đối số rounding mode: nếu việc đổi scale buộc bỏ chữ số khác 0, nó ném `ArithmeticException`. Không nên nghĩ overload này ngầm dùng `HALF_UP`:

```java
new BigDecimal("5.200").setScale(2); // 5.20: chỉ bỏ số 0
// new BigDecimal("5.205").setScale(2); // ArithmeticException
```

Đây là hành vi hữu ích khi cần phát hiện sai lệch thay vì tự động làm tròn. Khi cần xác định chế độ, hãy truyền `RoundingMode` tường minh.

### Vì sao `setScale` không giới hạn precision?

```java
BigDecimal value = new BigDecimal("123456789.12345");
BigDecimal twoDecimals = value.setScale(2, RoundingMode.HALF_UP);
// 123456789.12: vẫn có 11 chữ số có nghĩa.
```

Hai chữ số sau dấu chấm không đồng nghĩa hai chữ số có nghĩa. Hơn nữa, đệm số 0 để tăng scale có thể **tăng** precision theo biểu diễn mà không thay đổi giá trị toán học.

## 4. `round(MathContext)`: giới hạn chữ số có nghĩa

`MathContext` kết hợp hai thông tin:

```java
MathContext mc = new MathContext(4, RoundingMode.HALF_UP);
int p = mc.getPrecision();                 // 4
RoundingMode m = mc.getRoundingMode();     // HALF_UP
```

`value.round(mc)` làm tròn để kết quả dùng tối đa `p` chữ số có nghĩa. Chữ số 0 đứng trước chữ số khác 0 đầu tiên không “ăn” precision. Vị trí dấu chấm sẽ thay đổi theo độ lớn số:

```java
MathContext mc = new MathContext(4, RoundingMode.HALF_UP);

new BigDecimal("12345.67").round(mc);   // 1.235E+4 (giá trị 12350)
new BigDecimal("12.34567").round(mc);   // 12.35
new BigDecimal("0.001234567").round(mc); // 0.001235
```

Nếu đối tượng **đã có precision không vượt giới hạn**, phương thức không cần làm tròn; nó không chủ động thêm số 0 để đủ p chữ số. Ví dụ `new BigDecimal("1.2").round(new MathContext(4))` vẫn là `1.2`, không phải `1.200`.

Một vài điểm cần nhớ:

1. `new MathContext(4)` dùng mặc định `RoundingMode.HALF_UP`; có thể truyền mode để giao tiếp rõ yêu cầu.
2. Precision **0** trong `MathContext` nghĩa là không giới hạn precision; `MathContext.UNLIMITED` là context có precision 0. Khi đó `round(mc)` không làm tròn vì giới hạn chữ số.
3. `MathContext.DECIMAL32`, `DECIMAL64`, `DECIMAL128` lần lượt dùng precision 7, 16, 34 và mode `HALF_EVEN`. Chúng giới hạn phép toán thập phân khi được truyền vào, không biến dữ liệu thành `float`/`double`.
4. `MathContext` không đặt chính sách toàn cục. `a.add(b)` tiếp tục tính không giới hạn precision dù trước đó bạn đã gọi `a.round(mc)`; muốn áp dụng cho phép cộng phải gọi `a.add(b, mc)`.

### `MathContext` trong phép tính, khác với làm tròn kết quả đã có

Các phép toán như `add`, `subtract`, `multiply`, `divide` có overload nhận `MathContext`:

```java
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);
BigDecimal a = new BigDecimal("10.1234");
BigDecimal b = new BigDecimal("1.2345");

BigDecimal exact = a.add(b);     // 11.3579
BigDecimal rounded = a.add(b, mc); // 11.4
```

`round(mc)` xử lý một **đối tượng kết quả hiện có**, còn `add(b, mc)` yêu cầu phép cộng tạo kết quả theo precision được chỉ định. Đối với phép chia tạo thập phân vô hạn, cấp context ngay trong phép toán còn giúp xác định điểm dừng biểu diễn:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal byPrecision = one.divide(
    three, new MathContext(4, RoundingMode.HALF_UP)
); // 0.3333: 4 chữ số có nghĩa

BigDecimal byScale = one.divide(
    three, 2, RoundingMode.HALF_UP
); // 0.33: 2 chữ số sau dấu chấm

// one.divide(three); // ArithmeticException: 1/3 không có biểu diễn hữu hạn.
```

Đặc biệt, `MathContext.UNLIMITED` **không** khắc phục phép chia `1 / 3`: precision 0 yêu cầu kết quả chính xác, mà `1 / 3` có khai triển thập phân vô hạn. Muốn chia ra giá trị xấp xỉ hữu hạn thì phải chọn precision hoặc scale và mode thích hợp.

## 5. RoundingMode chung nhưng đơn vị làm tròn khác nhau

Cả hai API dùng `RoundingMode`, nhưng vị trí làm tròn do **scale** hoặc **precision** quyết định.

| Mode | Quy tắc chung | Ví dụ làm tròn `2.5` về số nguyên |
|---|---|---|
| `UP` | Xa số 0 khi có phần bị bỏ khác 0 | `3` |
| `DOWN` | Về số 0 | `2` |
| `CEILING` | Về +∞ | `3` |
| `FLOOR` | Về −∞ | `2` |
| `HALF_UP` | Gần nhất, đúng giữa thì xa 0 | `3` |
| `HALF_DOWN` | Gần nhất, đúng giữa thì về 0 | `2` |
| `HALF_EVEN` | Gần nhất, đúng giữa thì giữ chữ số cuối chẵn | `2` |
| `UNNECESSARY` | Yêu cầu chính xác; lỗi nếu phải bỏ chữ số có ảnh hưởng giá trị | `ArithmeticException` |

Với số âm, `CEILING` và `FLOOR` khác với `UP`/`DOWN`: `-2.5` làm tròn về số nguyên theo `CEILING` là `-2`, còn theo `FLOOR` là `-3`. `HALF_EVEN` không phải “luôn xuống”: `2.5 → 2` nhưng `3.5 → 4`.

Ví dụ minh họa hai loại ràng buộc:

```java
BigDecimal x = new BigDecimal("12.345");
BigDecimal scaled = x.setScale(2, RoundingMode.HALF_EVEN); // 12.34
BigDecimal significant = x.round(
    new MathContext(4, RoundingMode.HALF_EVEN)
); // 12.34
```

Hai kết quả có thể tình cờ bằng nhau. Điều này **không** chứng minh hai API tương đương: `new BigDecimal("123.456").setScale(2, HALF_EVEN)` là `123.46`, còn `round(MathContext(4, HALF_EVEN))` là `123.5`.

## 6. Chương trình Java 17+ hoàn chỉnh: so sánh và kết quả thật

Tạo file `ScaleVsContextDemo.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class ScaleVsContextDemo {
    public static void main(String[] args) {
        BigDecimal x = new BigDecimal("123.4567");
        MathContext mc = new MathContext(4, RoundingMode.HALF_UP);
        System.out.println("setScale(2): " + x.setScale(2, RoundingMode.HALF_UP).toPlainString());
        System.out.println("round(4): " + x.round(mc).toPlainString());

        BigDecimal small = new BigDecimal("0.00123456");
        System.out.println("small scale(4): " + small.setScale(4, RoundingMode.HALF_UP).toPlainString());
        System.out.println("small round(4): " + small.round(mc).toPlainString());

        BigDecimal padded = new BigDecimal("1.2").setScale(4, RoundingMode.UNNECESSARY);
        System.out.println("padded: " + padded.toPlainString()
                + ", precision=" + padded.precision()
                + ", scale=" + padded.scale());

        BigDecimal value = new BigDecimal("1.249");
        System.out.println("direct: " + value.setScale(1, RoundingMode.HALF_UP).toPlainString());
        System.out.println("two steps: " + value.round(new MathContext(3, RoundingMode.HALF_UP))
                .setScale(1, RoundingMode.HALF_UP).toPlainString());

        BigDecimal three = new BigDecimal("3");
        System.out.println("divide precision: " + BigDecimal.ONE.divide(three, mc).toPlainString());
        System.out.println("divide scale: " + BigDecimal.ONE.divide(three, 2, RoundingMode.HALF_UP).toPlainString());
        System.out.println("exact scale: " + new BigDecimal("2.500")
                .setScale(2, RoundingMode.UNNECESSARY).toPlainString());

        try {
            new BigDecimal("2.501").setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("rounding required: ArithmeticException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ScaleVsContextDemo.java
java ScaleVsContextDemo
```

Kết quả chuẩn:

```text
setScale(2): 123.46
round(4): 123.5
small scale(4): 0.0012
small round(4): 0.001235
padded: 1.2000, precision=5, scale=4
direct: 1.2
two steps: 1.3
divide precision: 0.3333
divide scale: 0.33
exact scale: 2.50
rounding required: ArithmeticException
```

Đây là hai góc nhìn rõ nhất:

- Với số lớn `123.4567`, scale 2 vẫn giữ toàn bộ phần nguyên và hai chữ số lẻ; precision 4 chỉ giữ bốn chữ số có nghĩa, nên `123.5`.
- Với số nhỏ `0.00123456`, scale 4 chỉ giữ đến chữ số ở vị trí `10^-4`, nên `0.0012`; precision 4 đếm từ chữ số 1 đầu tiên nên `0.001235`.

`toPlainString()` được dùng để hiển thị không có ký pháp mũ; nó không đổi giá trị hay precision của đối tượng.

## 7. Không làm tròn hai lần một cách vô thức

Hai đường xử lý cùng đầu vào có thể cho **giá trị khác nhau** nếu làm tròn trung gian:

```java
BigDecimal original = new BigDecimal("1.249");

BigDecimal direct = original.setScale(1, RoundingMode.HALF_UP);
// 1.2

BigDecimal twoStages = original
        .round(new MathContext(3, RoundingMode.HALF_UP)) // 1.25
        .setScale(1, RoundingMode.HALF_UP);              // 1.3
```

Giải thích:

1. Đường trực tiếp xét `1.249`: gần `1.2` hơn `1.3`, nên được `1.2`.
2. Đường hai bước làm tròn `1.249` thành `1.25` (ba chữ số có nghĩa). Khi giảm scale về 1, `1.25` là trường hợp đúng giữa; `HALF_UP` chọn `1.3`.

Hiện tượng này gọi là *double rounding*. Nếu nghiệp vụ chỉ yêu cầu làm tròn **kết quả cuối** đến hai chữ số sau dấu chấm, hãy áp dụng `setScale(2, mode)` ở bước cuối phù hợp, không tùy tiện chèn một `round(MathContext)` có precision thấp trước đó. Nếu cần làm tròn trung gian vì chia vô hạn, hãy chọn precision làm việc đủ lớn và kiểm tra sai số cũng như quy tắc nghiệp vụ.

Ngược lại, có những bài toán thật sự yêu cầu từng bước phải được làm tròn (ví dụ theo đơn vị giao dịch, từng dòng thuế, quy chuẩn đo lường). Khi đó phải tôn trọng đúng **thời điểm** làm tròn đã được quy định. Chọn API không thể tách rời cách xác định điểm làm tròn.

## 8. Khi làm việc với tiền, tỷ lệ, đo lường và hiển thị

### Trường hợp A: số tiền cuối phải có hai chữ số thập phân

Ví dụ nghiệp vụ giả định cần làm tròn `HALF_UP` về 0,01 đơn vị tiền tệ:

```java
BigDecimal net = new BigDecimal("19.99");
BigDecimal rate = new BigDecimal("0.0825");

BigDecimal taxExact = net.multiply(rate); // 1.649175
BigDecimal tax = taxExact.setScale(2, RoundingMode.HALF_UP); // 1.65
```

`setScale(2, ...)` phù hợp vì yêu cầu nói rõ **hai vị trí sau dấu thập phân**. `MathContext(2, ...)` không thể bảo đảm điều này: `1.649175` về hai chữ số có nghĩa thành `1.6` (có giá trị và số chữ số thập phân khác).

Quy tắc làm tròn tiền phụ thuộc hợp đồng và pháp luật áp dụng; `HALF_UP` trong ví dụ chỉ là giả định kỹ thuật.

### Trường hợp B: chia ra tỷ lệ cần độ chính xác làm việc

```java
MathContext working = new MathContext(16, RoundingMode.HALF_EVEN);
BigDecimal total = new BigDecimal("100.00");
BigDecimal count = new BigDecimal("3");

BigDecimal unit = total.divide(count, working); // xấp xỉ 33.33333333333333
BigDecimal shown = unit.setScale(2, RoundingMode.HALF_UP); // 33.33
```

Ở đây hai API giải quyết **hai bước khác nhau**: context cho phép phép chia tạo kết quả gần đúng có 16 chữ số có nghĩa; `setScale(2)` chuẩn hóa độ phân giải của kết quả dùng để hiển thị. Nếu hệ thống cần phân bổ tổng số tiền chính xác cho nhiều đơn vị, làm tròn đơn giá rồi nhân trở lại có thể tạo phần dư; nghiệp vụ cần quy tắc phân bổ phần dư riêng.

### Trường hợp C: đo lường theo chữ số có nghĩa

Một thiết bị cung cấp kết quả `0.000987654` và quy trình báo cáo yêu cầu **ba chữ số có nghĩa**:

```java
BigDecimal reading = new BigDecimal("0.000987654");
BigDecimal reported = reading.round(
    new MathContext(3, RoundingMode.HALF_EVEN)
); // 0.000988
```

`setScale(3)` ở đây sẽ cho `0.001`, mất hầu hết độ chi tiết; nó không biểu đạt yêu cầu chữ số có nghĩa. Dù vậy, quy định đo lường có thể yêu cầu cả chữ số có nghĩa, chữ số chắc chắn và cách xử lý độ không đảm bảo: chỉ context chưa bao quát toàn bộ phép đo.

## 9. Những ngoại lệ và chi tiết dễ bỏ sót

### 9.1. `RoundingMode.UNNECESSARY`: chỉ được đổi biểu diễn nếu vẫn chính xác

```java
new BigDecimal("2.500").setScale(2, RoundingMode.UNNECESSARY);
// 2.50: bỏ số 0 không đổi giá trị

// new BigDecimal("2.501").setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException: cần bỏ chữ số 1 có ảnh hưởng giá trị
```

Tương tự, `round(new MathContext(p, UNNECESSARY))` chỉ thành công nếu giảm precision mà không làm thay đổi giá trị. Ví dụ từ `2.500` xuống precision 2 có thể thành `2.5`, nhưng từ `2.501` xuống precision 2 thì không thể chính xác.

### 9.2. Cùng giá trị số, khác `equals`

```java
BigDecimal a = new BigDecimal("1.2");
BigDecimal b = a.setScale(2); // 1.20

boolean sameObjectValueAndScale = a.equals(b); // false
boolean sameNumericValue = a.compareTo(b) == 0; // true
```

`BigDecimal.equals` xét cả **giá trị và scale**; `compareTo` so sánh giá trị số. Khi test chức năng có quy tắc biểu diễn (ví dụ yêu cầu đúng hai chữ số lẻ), kiểm tra cả `scale()` hoặc chuỗi đầu ra. Khi chỉ so sánh giá trị toán học, `compareTo() == 0` có thể thích hợp hơn.

### 9.3. Dạng mũ và số 0 cuối

Một số phép `round(MathContext)` trả ra đối tượng có scale âm hoặc ký pháp mũ:

```java
BigDecimal y = new BigDecimal("12345")
        .round(new MathContext(2, RoundingMode.HALF_UP));
// y.toString(): "1.2E+4"
// y.toPlainString(): "12000"
// y.precision(): 2
```

`toPlainString()` là lựa chọn hiển thị dạng thường, nhưng không phải công cụ giới hạn số chữ số thập phân. Trước khi in cho người dùng theo định dạng cố định, hãy xác định scale hoặc dùng định dạng được chỉ rõ bởi đặc tả.

### 9.4. Tránh chuyển thẳng `double` vào `BigDecimal`

```java
BigDecimal exactDecimal = new BigDecimal("0.1");
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
BigDecimal fromDouble = new BigDecimal(0.1);
```

`new BigDecimal(0.1)` lưu chính xác giá trị nhị phân `double` được truyền vào, vốn không biểu diễn đúng `0.1`. Nếu sau đó áp dụng `round(MathContext)`, bạn có thể che bớt chữ số nhiễu nhưng không giải quyết đúng nguồn dữ liệu. Với đầu vào thập phân cần kiểm soát, nên parse từ chuỗi hoặc `BigDecimal.valueOf` với sự hiểu biết về dữ liệu nguồn.

### 9.5. Không có context ngầm định cho mọi phép toán

```java
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);
BigDecimal x = new BigDecimal("9.999");
BigDecimal rounded = x.round(mc); // 10.0
BigDecimal plusExact = x.add(BigDecimal.ONE); // 10.999: không nhận context
BigDecimal plusRounded = x.add(BigDecimal.ONE, mc); // 11.0
```

Kết quả của một lệnh gọi không tự xác lập “precision mặc định” cho những lệnh khác. Khi thiết kế service tính toán, hãy truyền context rõ ràng hoặc đưa nó vào API nghiệp vụ phù hợp.

## 10. Bảng quyết định nhanh

| Yêu cầu phát biểu | Cách dùng phù hợp | Lý do |
|---|---|---|
| “Giữ đúng hai chữ số sau dấu thập phân” | `setScale(2, mode)` | Scale cố định là 2 |
| “Làm tròn đến hàng chục” | `setScale(-1, mode)` | Scale -1 tương ứng bội số của 10 |
| “Làm tròn thành bốn chữ số có nghĩa” | `round(new MathContext(4, mode))` | Precision cố định là 4 |
| “Chia 1/3 lấy sáu chữ số có nghĩa” | `divide(divisor, new MathContext(6, mode))` | Phép chia thập phân vô hạn cần precision và mode |
| “Chia 1/3 lấy sáu chữ số sau dấu chấm” | `divide(divisor, 6, mode)` | Phép chia dùng scale cố định |
| “Chỉ chấp nhận cắt bớt số 0 dư, không được mất giá trị” | `setScale(target, UNNECESSARY)` | Ném lỗi khi phải làm tròn không chính xác |
| “Giữ đủ precision trung gian rồi hiển thị hai chữ số lẻ” | `divide(..., workingContext)` rồi `setScale(2, mode)` | Hai công đoạn có hai mục tiêu khác nhau |

Không áp dụng máy móc cả hai phương thức cho mọi giá trị: mỗi lần làm tròn đều có thể mất thông tin. Quy trình tốt cần ghi rõ độ chính xác làm việc, đơn vị đầu ra, chế độ làm tròn và thời điểm làm tròn.

## 11. Tự kiểm tra và đáp án

**Câu 1.** Cho `x = new BigDecimal("0.00056789")`. So sánh `x.setScale(5, HALF_UP)` và `x.round(new MathContext(3, HALF_UP))`.

**Đáp án:** `setScale(5)` cho `0.00057`; context precision 3 cho `0.000568`. Scale đếm vị trí sau dấu chấm; precision đếm từ chữ số 5 đầu tiên khác 0.

**Câu 2.** Tại sao `new BigDecimal("1.20").setScale(4)` có precision lớn hơn trước?

**Đáp án:** kết quả `1.2000` chứa năm chữ số trong unscaled value và scale bằng 4, trong khi `1.20` có precision 3 và scale 2. Giá trị toán học vẫn bằng nhau.

**Câu 3.** Nếu nhận `12345.678` và yêu cầu làm tròn đến hàng trăm, dùng API gì?

**Đáp án:** `setScale(-2, mode)`, vì hàng trăm tương ứng scale -2. Ví dụ với `HALF_UP` cho giá trị 12300. Có thể nhận kết quả tương ứng bằng context trong một số trường hợp, nhưng context biểu đạt số chữ số có nghĩa, không trực tiếp biểu đạt đơn vị hàng trăm với mọi đầu vào.

**Câu 4.** `new BigDecimal("1.249")` làm tròn trực tiếp về một chữ số sau dấu thập phân so với `round(MathContext(3, HALF_UP))` rồi `setScale(1, HALF_UP)` có giống nhau không?

**Đáp án:** không. Trực tiếp được `1.2`; hai bước được `1.3` do double rounding.

**Câu 5.** Nếu mục tiêu là phát hiện mọi thay đổi giá trị khi hạ scale, nên dùng gì?

**Đáp án:** `setScale(targetScale, RoundingMode.UNNECESSARY)`; nếu phải bỏ chữ số khác 0, phương thức ném `ArithmeticException`.

**Ghi nhớ cốt lõi:** `setScale` trả lời **“bao nhiêu chữ số thập phân?”**; `round(MathContext)` trả lời **“bao nhiêu chữ số có nghĩa?”**. Cùng `RoundingMode`, khác vị trí làm tròn. Xác định nhu cầu trước khi chọn API, và luôn chú ý thứ tự các bước tính để tránh làm tròn hai lần.
