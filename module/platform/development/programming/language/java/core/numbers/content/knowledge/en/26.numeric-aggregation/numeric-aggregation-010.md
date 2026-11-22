# Không trộn đơn vị, precision hoặc scale không được thống nhất

## 1. Vấn đề: phép tính đúng cú pháp có thể sai ý nghĩa

Trong Java, kiểu số như `BigDecimal` biết cộng, trừ, nhân, chia nhưng **không tự biết** các số đang biểu thị mét, centimet, USD, giây hay phần trăm. Nó cũng không tự biết hợp đồng nghiệp vụ đòi hỏi bao nhiêu chữ số có nghĩa, bao nhiêu chữ số sau dấu phẩy và làm tròn vào thời điểm nào.

Ba nguồn sai lệch thường gặp:

1. **Đơn vị không đồng nhất:** cộng `1.20 m + 30 cm` như `1.20 + 30 = 31.20`. Giá trị đúng phải quy đổi `30 cm = 0.30 m`, sau đó được `1.50 m`.
2. **Precision không đồng nhất:** một phép tính giữ kết quả đầy đủ, phép tiếp theo dùng `MathContext.DECIMAL32` chỉ giữ tối đa bảy chữ số có nghĩa. Sai số của bước làm tròn có thể lan đến kết quả cuối.
3. **Scale không đồng nhất:** `1.2`, `1.20` và `1.200` bằng nhau về giá trị toán học nhưng có scale khác nhau; `BigDecimal.equals`, lưu trữ hoặc hiển thị có thể xử lý chúng khác nhau.

Nguyên tắc xuyên suốt: **kiểm tra đại lượng và đơn vị, thống nhất chính sách tính toán, rồi chuẩn hóa kết quả tại ranh giới thích hợp**. Đừng dùng phép làm tròn hoặc ép kiểu chỉ để che đi dữ liệu nguồn sai đơn vị.

## 2. Không trộn đơn vị trước khi tổng hợp

Một số `42` không diễn đạt đầy đủ “42 mét”, “42 giây”, “42 USD” hay “42%”. Nếu phép cộng/trừ có ý nghĩa, các toán hạng phải cùng **loại đại lượng** và được đưa về **đơn vị tương thích** trước khi tính.

| Đầu vào | Phép tính sai | Cách quy đổi đúng |
| --- | --- | --- |
| `1.20 m` và `30 cm` | `1.20 + 30 = 31.20` | `1.20 m + 0.30 m = 1.50 m` |
| `2 kg` và `500 g` | `2 + 500 = 502` | `2 kg + 0.5 kg = 2.5 kg` |
| `2 phút` và `30 giây` | `2 + 30 = 32` | `120 s + 30 s = 150 s` |
| `15%` và tỷ lệ `0.10` | `15 + 0.10 = 15.10` | Nếu cùng cơ sở: `0.15 + 0.10 = 0.25 = 25%` |
| `10 USD` và `10 EUR` | `20` kèm một đơn vị tiền tệ tùy ý | Muốn cộng cần quy đổi theo tỷ giá được chọn, thời điểm và quy tắc làm tròn |

Ví dụ về phần trăm chỉ hợp lệ khi cùng mẫu số và việc cộng các tỷ lệ thật sự có ý nghĩa. Tỷ lệ 15% trên nhóm A và 10% trên nhóm B thường không thể cộng thẳng để ra 25% của toàn bộ tập khách hàng; phải xem quy mô, quan hệ của hai nhóm và mẫu số.

Không phải chuyển đổi đơn vị nào cũng là nhân một hằng số. Nhiệt độ tuyệt đối từ Celsius sang Kelvin có offset `+273.15`; độ chênh nhiệt độ lại có quy tắc ngữ nghĩa khác. Giá theo kilogram nhân với khối lượng tạo thành tiền và thay đổi **thứ nguyên**. Không nên viết một hàm `convert(value)` chung cho mọi loại dữ liệu mà bỏ qua ngữ nghĩa này.

### 2.1. Quy đổi chính xác bằng BigDecimal

Với đơn vị hệ thập phân, có thể dùng `BigDecimal` để không đi qua `double`:

~~~java
import java.math.BigDecimal;

BigDecimal meters = new BigDecimal("1.20");
BigDecimal centimeters = new BigDecimal("30");

BigDecimal centimetersAsMeters = centimeters.movePointLeft(2);
BigDecimal totalMeters = meters.add(centimetersAsMeters);
// Giá trị chính xác: 1.50 mét
~~~

`movePointLeft(2)` dịch dấu thập phân sang trái hai vị trí, nghĩa là chia giá trị cho 100. Nó phù hợp cho centimet → mét, không phải công thức tổng quát cho các đơn vị khác. Nếu hệ số đổi đơn vị hoặc phép chia tạo số thập phân vô hạn, chính sách precision/scale và rounding mode phải được quy định.

### 2.2. Đưa đơn vị vào kiểu dữ liệu

Nếu API nhận `BigDecimal left, BigDecimal right`, người gọi có thể truyền hai đại lượng bất kỳ. Một cách phòng tránh là bao gói giá trị cùng đơn vị: `record Length(BigDecimal amount, LengthUnit unit)`.

Khi đó, API cộng độ dài có thể chuyển mỗi đầu vào thành mét trước khi cộng. Với tiền, bản ghi `Money(amount, currency)` có thể từ chối phép cộng giữa USD và EUR. Điều này biến một lỗi âm thầm thành lỗi có thể phát hiện.

Ở ranh giới JSON, database hoặc file, cần truyền hoặc quy định đơn vị chính thức. Ví dụ một cột `value` chứa lúc thì mét, lúc thì centimet nhưng không có thông tin unit sẽ khiến bài toán tổng hợp khó có thể làm đúng.

## 3. Phân biệt precision và scale

Với `BigDecimal`, giá trị được biểu diễn theo công thức:

`giá trị = unscaledValue × 10^(-scale)`.

- **`precision()`:** số chữ số trong biểu diễn nguyên không chia tỷ lệ của `BigDecimal`, thường gọi là số chữ số có nghĩa **của biểu diễn**.
- **`scale()`:** số mũ điều chỉnh bằng lũy thừa 10; trong dạng thập phân thông thường là số chữ số sau dấu phẩy.
- **Precision của `MathContext`:** giới hạn **tổng số chữ số có nghĩa của kết quả** khi một phép toán áp context.
- **Rounding mode:** quy tắc xử lý chữ số phải loại bỏ khi cần làm tròn.

| Chuỗi đầu vào | `precision()` | `scale()` | Ghi chú |
| --- | ---: | ---: | --- |
| `"1.2"` | 2 | 1 | Hai chữ số |
| `"1.20"` | 3 | 2 | Bằng `1.2` về số học, khác biểu diễn |
| `"1.200"` | 4 | 3 | Có thêm số 0 cuối |
| `"123.4500"` | 7 | 4 | Hai số 0 cuối có trong biểu diễn |
| `"0.00120"` | 3 | 5 | Số 0 dẫn đầu không tăng precision |
| `"1E+3"` | 1 | -3 | Scale có thể âm, giá trị là 1000 |

`new MathContext(2, RoundingMode.HALF_EVEN)` giới hạn hai chữ số có nghĩa. `setScale(2, RoundingMode.HALF_EVEN)` đặt hai chữ số sau dấu phẩy. Hai thao tác **không tương đương**.

Đừng nhầm độ chính xác của phép đo với `BigDecimal.precision()`. Một máy đo báo `1.200 m` có thể hàm ý độ phân giải millimet, nhưng bản thân `BigDecimal` không biết sai số, độ tin cậy hay thiết bị đo. Nếu bài toán cần uncertainty/số chữ số có nghĩa theo quy ước đo lường, hãy lưu metadata tương ứng.

## 4. Scale khác nhau có thể gây sai lệch dù giá trị số bằng nhau

### 4.1. `equals` không giống `compareTo`

~~~java
BigDecimal x = new BigDecimal("1.20");
BigDecimal y = new BigDecimal("1.2");

boolean sameNumericValue = x.compareTo(y) == 0; // true
boolean sameRepresentation = x.equals(y);       // false
~~~

`compareTo` so giá trị toán học, `equals` xem cả giá trị và scale. Điều này tác động đến việc dùng `BigDecimal` làm khóa trong `HashMap` hoặc phần tử trong `HashSet`: `1.2` và `1.20` có thể được lưu thành hai khóa khác nhau. Không chuyển qua `double` để “sửa” việc so sánh, vì nó có thể mất precision.

### 4.2. Cộng chính xác không tự chuẩn hóa scale

~~~java
BigDecimal first = new BigDecimal("1.20");   // scale 2
BigDecimal second = new BigDecimal("0.300"); // scale 3

BigDecimal sum = first.add(second);
// sum.toPlainString(): "1.500"
// sum.precision(): 4
// sum.scale(): 3
~~~

Với cộng/trừ không truyền `MathContext`, scale ưu tiên là scale lớn hơn của hai toán hạng. Về số học, `1.500` và `1.50` bằng nhau; trong hợp đồng JSON hoặc quy định hiển thị chính xác hai chữ số sau dấu phẩy, chúng là hai biểu diễn khác nhau.

Với nhân không truyền context, scale ưu tiên thường là **tổng scale** của hai toán hạng; với phép chia exact, kết quả có thể không tồn tại ở dạng thập phân hữu hạn, chẳng hạn `1/3`. Không thể dùng một quy tắc scale giống hệt nhau cho mọi phép toán.

### 4.3. Chuẩn hóa bằng `setScale` có kiểm soát

~~~java
BigDecimal total = new BigDecimal("1.500");
BigDecimal normalized = total.setScale(2, RoundingMode.UNNECESSARY);
// 1.50: không mất giá trị toán học
~~~

`UNNECESSARY` yêu cầu không được làm tròn mất chữ số khác 0. Bỏ một chữ số `0` thừa khỏi `1.500` là chính xác nên thành công. Ngược lại:

~~~java
new BigDecimal("1.234").setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException: không thể giảm scale mà vẫn giữ nguyên giá trị
~~~

Khi nghiệp vụ **cho phép làm tròn**, chọn mode:

~~~java
new BigDecimal("1.005").setScale(2, RoundingMode.HALF_UP);   // 1.01
new BigDecimal("1.005").setScale(2, RoundingMode.HALF_EVEN); // 1.00
~~~

`HALF_UP` chọn xa số 0 khi đúng nửa. `HALF_EVEN` chọn chữ số cuối chẵn khi đúng nửa. Chúng không tự phù hợp với mọi quy định tính tiền hoặc thống kê. Nếu tăng scale, `setScale` thường thêm số 0 mà không đổi giá trị số.

`stripTrailingZeros()` có thể bỏ các số 0 cuối nhưng **thay đổi scale** và có thể tạo biểu diễn khoa học hoặc scale âm, ví dụ số 1000 có thể thành `1E+3`. Không nên gọi máy móc khi schema yêu cầu scale cố định.

## 5. Precision phải nhất quán với chính sách tính toán

### 5.1. MathContext chỉ ảnh hưởng tới phép toán có dùng nó

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

MathContext mc = new MathContext(7, RoundingMode.HALF_EVEN);
BigDecimal a = new BigDecimal("123456.789");
BigDecimal b = new BigDecimal("0.0012345");

BigDecimal exact = a.add(b);
BigDecimal bounded = a.add(b, mc);
~~~

`exact` giữ tổng chính xác, còn `bounded` làm tròn theo **7 chữ số có nghĩa**. Việc khai báo biến `mc` không tự đổi mọi phép toán về sau; bạn phải truyền context tới từng phép toán cần giới hạn.

| Context | Precision tối đa | Rounding mode |
| --- | ---: | --- |
| `MathContext.DECIMAL32` | 7 | `HALF_EVEN` |
| `MathContext.DECIMAL64` | 16 | `HALF_EVEN` |
| `MathContext.DECIMAL128` | 34 | `HALF_EVEN` |
| `MathContext.UNLIMITED` | Không giới hạn (giá trị precision là 0) | Lưu `HALF_UP`; không áp làm tròn do giới hạn precision |

`UNLIMITED` không làm cho thương `1/3` có biểu diễn hữu hạn: chia chính xác không có scale/mode thích hợp vẫn có thể ném `ArithmeticException`.

Nếu tầng xử lý A dùng `DECIMAL32` và tầng B dùng `DECIMAL128` hoặc không truyền context, kết quả có thể không nhất quán. Tạo một **chính sách số học cho từng đại lượng**, thay vì lựa chọn context khác nhau theo sở thích mỗi hàm.

### 5.2. Thời điểm làm tròn thay đổi kết quả

Xét:

~~~java
BigDecimal a = new BigDecimal("0.005");
BigDecimal b = new BigDecimal("0.005");

BigDecimal roundEach = a.setScale(2, RoundingMode.HALF_UP)
        .add(b.setScale(2, RoundingMode.HALF_UP)); // 0.02

BigDecimal roundSum = a.add(b)
        .setScale(2, RoundingMode.HALF_UP);       // 0.01
~~~

Nếu làm tròn từng phần, `0.005` thành `0.01` và tổng bằng `0.02`. Nếu cộng chính xác `0.010` rồi làm tròn kết quả, được `0.01`. Cả hai đều dùng cùng mode và cùng scale mục tiêu nhưng cho kết quả khác.

Đối với hóa đơn, phí, thuế hay báo cáo, quy định có thể yêu cầu làm tròn từng dòng hoặc tổng cộng cuối cùng. Vì vậy chính sách phải nói rõ **làm tròn giá trị nào và vào thời điểm nào**. Không có quy tắc “luôn làm tròn ở cuối” đúng cho mọi nghiệp vụ.

### 5.3. Tránh precision mất mát do đầu vào kiểu double

~~~java
BigDecimal exactDecimal = new BigDecimal("0.1");
BigDecimal fromBinaryDouble = new BigDecimal(0.1);
~~~

`new BigDecimal(0.1)` nhận giá trị nhị phân `double` đã được xấp xỉ trước đó, nên có thể có chuỗi thập phân dài ngoài dự kiến. `new BigDecimal("0.1")` nhận đúng giá trị thập phân đã định. `BigDecimal.valueOf(0.1)` thường dễ dùng hơn constructor nhận `double` nhưng không phục hồi chính xác những thông tin đã mất trong các phép tính dấu phẩy động trước đó.

Nếu đơn vị hoặc tỷ giá được mô tả bằng decimal chính xác, dùng chuỗi decimal hoặc dữ liệu decimal được xác thực. Khi phép đo vốn là float/double từ cảm biến, cần đánh giá mức sai số thật sự thay vì giả định chuyển sang `BigDecimal` tự sửa được sai số cảm biến.

## 6. Chương trình Java 17+ đầy đủ

Chương trình dưới đây biểu diễn cả một phép cộng **cố ý sai** vì thiếu chuyển đơn vị và cách xử lý đúng. Nó cũng kiểm tra precision/scale, rounding mode và điều kiện không cho cộng hai loại tiền khác nhau.

Tạo file `UnitPrecisionScaleDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public class UnitPrecisionScaleDemo {
    enum LengthUnit {
        METER, CENTIMETER
    }

    record Length(BigDecimal amount, LengthUnit unit) {
        public Length {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(unit, "unit");
        }

        BigDecimal inMeters() {
            return switch (unit) {
                case METER -> amount;
                case CENTIMETER -> amount.movePointLeft(2);
            };
        }
    }

    enum CurrencyCode {
        USD, EUR
    }

    record Money(BigDecimal amount, CurrencyCode currency) {
        public Money {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");
        }

        Money add(Money other) {
            if (currency != other.currency) {
                throw new IllegalArgumentException("Currency mismatch");
            }
            return new Money(amount.add(other.amount), currency);
        }
    }

    public static void main(String[] args) {
        Length a = new Length(new BigDecimal("1.20"), LengthUnit.METER);
        Length b = new Length(new BigDecimal("30"), LengthUnit.CENTIMETER);

        System.out.println("raw lengths (WRONG): "
                + a.amount().add(b.amount()));
        System.out.println("sum normalized: "
                + a.inMeters().add(b.inMeters())
                        .setScale(2, RoundingMode.UNNECESSARY)
                        .toPlainString()
                + " m");

        BigDecimal p = new BigDecimal("1.20");
        BigDecimal q = new BigDecimal("0.300");
        BigDecimal sum = p.add(q);

        System.out.println("raw sum: " + sum.toPlainString()
                + " (precision=" + sum.precision()
                + ", scale=" + sum.scale() + ")");
        System.out.println("display scale: "
                + sum.setScale(2, RoundingMode.UNNECESSARY)
                        .toPlainString());

        System.out.println("compareTo equal: "
                + (new BigDecimal("1.20").compareTo(
                        new BigDecimal("1.2")) == 0));
        System.out.println("equals equal: "
                + new BigDecimal("1.20").equals(
                        new BigDecimal("1.2")));

        try {
            new BigDecimal("1.234")
                    .setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("UNNECESSARY: ArithmeticException");
        }

        System.out.println("HALF_UP: "
                + new BigDecimal("1.005")
                        .setScale(2, RoundingMode.HALF_UP));
        System.out.println("HALF_EVEN: "
                + new BigDecimal("1.005")
                        .setScale(2, RoundingMode.HALF_EVEN));

        Money usdA = new Money(new BigDecimal("1.50"), CurrencyCode.USD);
        Money usdB = new Money(new BigDecimal("2.00"), CurrencyCode.USD);

        System.out.println("same currency: "
                + usdA.add(usdB).amount().toPlainString() + " USD");

        try {
            usdA.add(new Money(new BigDecimal("2.00"), CurrencyCode.EUR));
        } catch (IllegalArgumentException ex) {
            System.out.println("mixed currency: IllegalArgumentException");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac UnitPrecisionScaleDemo.java
java UnitPrecisionScaleDemo
~~~

Kết quả:

~~~text
raw lengths (WRONG): 31.20
sum normalized: 1.50 m
raw sum: 1.500 (precision=4, scale=3)
display scale: 1.50
compareTo equal: true
equals equal: false
UNNECESSARY: ArithmeticException
HALF_UP: 1.01
HALF_EVEN: 1.00
same currency: 3.50 USD
mixed currency: IllegalArgumentException
~~~

Đoạn `raw lengths` minh họa **hành vi sai cần tránh**; mã chỉ chạy được vì cả hai số được lấy ra từ record rồi cộng thủ công. `Length.inMeters()` mới là đường đi đúng để cộng các độ dài khác đơn vị. `Money.add` là phép cộng trong cùng đồng tiền, từ chối cặp tiền tệ khác nhau. Nếu thực sự muốn đổi ngoại tệ, cần phương thức chuyển đổi riêng có tỷ giá, thời điểm và quy tắc làm tròn đã xác định.

`setScale(2, UNNECESSARY)` trong ví dụ xác nhận kết quả mét có thể đưa về hai chữ số sau dấu phẩy **mà không mất giá trị**. Nếu có số đo đến millimet như `1.234 m`, phép chuẩn hóa ấy ném ngoại lệ; quyết định từ chối hay làm tròn phải dựa vào chính sách của dữ liệu đo.

## 7. Thống nhất chính sách tại ranh giới dữ liệu

### 7.1. Trên API và thông điệp

Một JSON rõ nghĩa có thể mang cả giá trị decimal và đơn vị:

~~~json
{
  "value": "125.50",
  "unit": "CENTIMETER"
}
~~~

Trường `value` dạng chuỗi giúp client và server không phải suy đoán cách biểu diễn nhị phân nếu contract yêu cầu decimal chính xác. Bên nhận kiểm tra tên đơn vị, phạm vi giá trị, độ phân giải cho phép và cách quy đổi sang đơn vị chuẩn.

Đừng tin tưởng rằng chữ số `0` cuối là metadata đủ để mô tả độ chính xác đo lường. Nếu bài toán cần độ sai số, sai số tuyệt đối/tương đối hoặc độ phân giải, cần quy định những thuộc tính ấy riêng.

### 7.2. Trong database

SQL `DECIMAL(p,s)` có giới hạn precision/scale lưu trữ theo schema, trong đó `p` và `s` thường biểu thị tổng chữ số và chữ số sau dấu thập phân. Các quy tắc cụ thể về phạm vi, xử lý tràn và làm tròn có thể khác theo hệ quản trị. Một cột `DECIMAL(12,2)` **không tương đương** với việc áp `new MathContext(12, ...)` trong Java, bởi `MathContext` giới hạn chữ số có nghĩa của phép toán và không đặt scale về 2.

Schema cần đồng thời nêu hoặc lưu đơn vị chuẩn và, nếu là tiền, mã tiền tệ. `1000` có thể nghĩa là 1000 gram hoặc 1000 kilogram; đặt scale 2 trong SQL không giải quyết sự nhập nhằng đó.

### 7.3. Khi hiển thị

Phân biệt dữ liệu tính toán và biểu diễn giao diện. Có thể dùng `toPlainString()` khi cần tránh biểu diễn khoa học của `BigDecimal.toString()`. Nếu hợp đồng hiển thị hai chữ số, chuẩn hóa **kết quả phục vụ hiển thị** thay vì làm mất độ phân giải dữ liệu gốc.

Một số hệ thống có chính sách làm tròn ở mức dòng hóa đơn, một số ở tổng cuối, hoặc cả hai ở các điểm khác nhau. Ghi rõ chính sách thành tài liệu và test. Khi thay đổi nó, cần đánh giá hiệu ứng lên dữ liệu cũ thay vì chỉ thay formatter.

## 8. Bảng kiểm khi thiết kế phép tổng hợp

| Câu hỏi | Quyết định cần có | Ví dụ |
| --- | --- | --- |
| Hai toán hạng có cùng đại lượng không? | Cấm trộn thứ nguyên | Không cộng mét với kilogram |
| Đơn vị chuẩn là gì? | Quy đổi trước khi tính | Centimet → mét, gram → kilogram |
| Đồng tiền nào? | Giữ mã tiền; tỷ giá phải tường minh | Không cộng USD với EUR trực tiếp |
| Precision trung gian bao nhiêu? | Chọn exact hay `MathContext` | Dùng `DECIMAL64` nếu được chấp nhận |
| Scale kết quả bao nhiêu? | Xác định theo loại dữ liệu | Mức tiền lưu 2 chữ số theo quy tắc riêng |
| Khi nào được làm tròn? | Xác định thời điểm | Mỗi dòng hay tổng cuối |
| Rounding mode nào? | Thỏa thuận rõ | `HALF_EVEN`, `HALF_UP`, `UNNECESSARY` |
| Mất dữ liệu có được phép không? | Làm tròn rõ ràng hoặc báo lỗi | `setScale(2, UNNECESSARY)` nếu cấm mất phần lẻ |
| Có cần độ tin cậy đo lường không? | Lưu metadata sai số riêng | `1.200 m ± 0.005 m` |

Khi cần lượng tiền theo đơn vị nhỏ nhất (cent), có thể biểu diễn bằng số nguyên sau khi **quy định rõ phép chuyển đổi và rounding policy**. Ví dụ 1 USD = 100 cent, nhưng không suy rộng giả định “mọi loại tiền đều có hai chữ số thập phân”.

Trong bài toán tỉ lệ và đơn vị đo, cần xem xét cả phạm vi số rất lớn/nhỏ, overflow của phép tính nền, phần dư khi chia, và cách áp precision để không làm tròn trung gian ngoài ý muốn.

## 9. Lỗi phổ biến

1. **Cộng giá trị mà bỏ nhãn đơn vị:** kết quả tính toán hợp lệ nhưng sai đại lượng.
2. **Cộng USD với EUR như cùng tiền tệ:** muốn quy đổi phải có tỷ giá, ngày hiệu lực và chính sách làm tròn.
3. **Dùng phần trăm như tỷ lệ thập phân:** 15% là 0.15; ngay cả khi đổi xong, chỉ cộng tỷ lệ khi mẫu số/cơ sở phù hợp.
4. **Nhầm precision và scale:** `MathContext(2)` không phải giữ hai chữ số sau dấu phẩy.
5. **Dùng `equals` khi cần so giá trị số:** `1.20` và `1.2` bằng nhau theo `compareTo` nhưng không bằng nhau theo `equals`.
6. **Làm tròn từng bước mà không có chính sách:** kết quả khác phép cộng chính xác rồi làm tròn sau cùng.
7. **Ép scale quá sớm:** có thể mất thông tin đo lường như millimet trong số mét.
8. **Dùng `new BigDecimal(double)` cho input decimal:** có thể đưa sai số nhị phân vào luồng tính toán.
9. **Gọi `stripTrailingZeros()` để chữa mọi chênh lệch scale:** có thể thay đổi scale/chuỗi hiển thị ngoài mong đợi.
10. **Giữ một scale áp cho mọi đại lượng:** tiền, khối lượng, thời gian, tỷ lệ có yêu cầu khác nhau.
11. **Tin precision nhiều tức là phép đo đáng tin:** precision của biểu diễn không nói lên sai số đo.
12. **Không kiểm tra unit/scale ở ranh giới API:** dữ liệu sai lan vào tổng hợp và khó truy nguyên.

## 10. Bài tập kiểm tra

**Câu 1.** Có `2.50 kg` và `750 g`. Tổng bằng bao nhiêu kilogram?

**Đáp án:** `750 g = 0.750 kg`, nên tổng exact là `3.250 kg`. Nếu hợp đồng yêu cầu scale 2 và không mất giá trị, có thể chuẩn hóa thành `3.25 kg` bằng `setScale(2, UNNECESSARY)`.

**Câu 2.** `new BigDecimal("12.0").equals(new BigDecimal("12.00"))` đúng hay sai? Muốn so giá trị số thì làm gì?

**Đáp án:** Sai vì scale khác nhau. Dùng `compareTo(...) == 0` để kiểm tra bằng nhau về giá trị số.

**Câu 3.** Cộng `0.005 + 0.005` rồi làm tròn tổng theo `HALF_UP` đến hai chữ số được bao nhiêu? Làm tròn mỗi phần trước thì sao?

**Đáp án:** Làm tròn tổng sau khi cộng exact được `0.01`. Làm tròn mỗi `0.005` thành `0.01` rồi cộng thành `0.02`.

**Câu 4.** API chấp nhận độ dài tối đa hai chữ số sau dấu thập phân của mét và nhận `1.234 m`. `setScale(2, UNNECESSARY)` có âm thầm đổi thành `1.23` không?

**Đáp án:** Không, nó ném `ArithmeticException` vì việc hạ scale sẽ mất chữ số khác 0. Muốn đổi sang centimet chính xác hay làm tròn đến centimet phải có yêu cầu rõ ràng.

**Câu 5.** Một giá trị `15` biểu thị 15%, còn giá trị `0.05` biểu thị tỷ lệ 5%. Kết quả cộng 20% được tính thế nào?

**Đáp án:** Đổi 15% về `0.15`; khi cùng cơ sở và được phép cộng tỷ lệ, tổng là `0.20` = 20%.

**Câu 6.** Vì sao `DECIMAL128` không thay thế chính sách hai chữ số sau dấu phẩy?

**Đáp án:** `DECIMAL128` giới hạn 34 chữ số có nghĩa và mặc định `HALF_EVEN`, không đặt scale bằng 2. Cần dùng `setScale(2, mode)` hoặc quy tắc trình bày phù hợp tại điểm được chỉ định.

## 11. Tài liệu Java chính thức

- [BigDecimal — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `precision()`, `scale()`, `setScale()`, `compareTo()`, `equals()`, `movePointLeft()`.
- [MathContext — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): giới hạn chữ số có nghĩa và rounding mode.
- [RoundingMode — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): quy tắc làm tròn.
- [Record declarations — JLS Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): mô hình dữ liệu record.

**Ghi nhớ:** Tổng hợp số đúng bắt đầu từ **cùng đại lượng, cùng đơn vị**, tiếp đến **chính sách precision của phép toán**, rồi **scale và rounding mode tại ranh giới đã quy định**. `BigDecimal` giúp tính toán decimal chính xác nhưng không tự hiểu đơn vị, đồng tiền, độ tin cậy phép đo hay quy tắc làm tròn của hệ thống.
