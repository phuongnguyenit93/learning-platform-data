# Chính sách số thập phân trong tính tiền và tính tổng

## 1. Chính sách quan trọng hơn một lời gọi setScale

Dùng `BigDecimal` giúp kiểm soát phép toán thập phân, nhưng không tự quyết định cách tính tổng đúng với yêu cầu của ứng dụng.

Một hệ thống còn phải thống nhất:

- Số tiền thuộc đơn vị tiền tệ nào.
- Giá đơn vị, số lượng và số tiền đã chốt được phép có scale bao nhiêu.
- Chế độ làm tròn nào được dùng.
- Làm tròn ở từng dòng, từng nhóm hay ở tổng cuối.
- Phần chênh lệch do chia phần được phân bổ như thế nào.
- Giá trị nào được lưu làm căn cứ cho các thao tác tiếp theo.

Nếu mỗi nơi tự gọi `setScale(2, HALF_UP)`, kết quả có thể không cộng khớp dù không hề có lỗi cú pháp Java.

Bài dùng đơn vị giả định `DEMO`, số tiền đã chốt có scale 2 và `HALF_UP` trong chương trình minh họa. Đây là cấu hình của ví dụ, không phải quy tắc chung cho mọi loại tiền hoặc mọi hệ thống thanh toán.

## 2. Tách bốn loại dữ liệu thường bị gom chung

| Dữ liệu | Vai trò | Điểm cần xác định |
|---|---|---|
| Giá đơn vị | Số tiền cho một đơn vị hàng hóa/dịch vụ | Có thể cần nhiều chữ số thập phân hơn số tiền thanh toán |
| Số lượng | Số đơn vị sử dụng | Có thể là số nguyên hoặc thập phân tùy miền bài toán |
| Tỷ lệ | Hệ số phần trăm, chiết khấu hoặc quy đổi | Đơn vị và cách biểu diễn riêng; không phải một số tiền |
| Số tiền đã chốt | Giá trị dùng để ghi nhận/thanh toán theo hợp đồng | Scale, bước làm tròn và thời điểm chốt phải rõ |

Ví dụ, giá đơn vị `0.145` và số lượng `3` cho số tiền chưa làm tròn `0.435`. Nếu làm tròn giá đơn vị về `0.15` trước khi nhân, kết quả lại thành `0.45`.

Do đó, “số tiền thanh toán có hai chữ số thập phân” không đồng nghĩa “mọi đầu vào có liên quan đều phải cắt về hai chữ số trước khi tính”.

Với tỷ lệ, cần thống nhất cách mã hóa: `0.10` biểu thị một phần mười; `10` là mười lần nếu đem nhân trực tiếp. Tên trường như `discountRate` nên đi cùng hợp đồng đơn vị cụ thể, tránh để hai phía tự hiểu khác nhau.

## 3. Xác định hợp đồng trước khi triển khai

Một chính sách có thể ghi rõ như sau:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Đơn vị | Các giá trị có cùng mã tiền tệ không? Có cho phép quy đổi không? |
| Scale đầu vào | Giá đơn vị, số lượng, tỷ lệ được lưu đến vị trí nào? |
| Scale số tiền chốt | Giữ số chữ số thập phân nào tại ranh giới ghi nhận? |
| Mode | Trường hợp đúng điểm giữa và số âm được xử lý ra sao? |
| Thời điểm | Làm tròn từng dòng, theo nhóm hay trên tổng? |
| Phép chia | Dùng scale/precision nào; có cho phép xấp xỉ không? |
| Phân bổ | Phần dư nhỏ nhất được giao cho ai; xử lý hòa bằng khóa ổn định nào? |
| Đảo giao dịch | Đảo số tiền đã ghi nhận hay tính lại từ dữ liệu gốc? |
| Truy vết | Có thể xác định phiên bản chính sách đã tạo ra kết quả không? |

Đừng dùng một biến `scale` duy nhất để đại diện cho mọi loại dữ liệu nếu chúng có yêu cầu khác nhau.

`Currency.getDefaultFractionDigits()` cung cấp số chữ số phần lẻ mặc định theo dữ liệu tiền tệ của Java; một số giá trị tiền tệ đặc biệt có thể trả về -1. Metadata đó không tự mô tả quy tắc làm tròn theo dòng, phân bổ hoặc bước thanh toán của ứng dụng. Xem [Java API: Currency](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Currency.html#getDefaultFractionDigits()).

Không suy ra tiền tệ từ ngôn ngữ giao diện, ký hiệu như `$` hoặc vị trí người dùng. Mô hình tiền cần gắn số tiền với đơn vị rõ ràng. Không cộng trực tiếp các giá trị khác đơn vị; việc quy đổi phải có tỷ lệ, hướng quy đổi, thời điểm và chính sách làm tròn riêng.

## 4. Dùng BigDecimal từ đầu luồng tính

### 4.1. Tạo từ dữ liệu thập phân rõ ràng

```java
BigDecimal unitPrice = new BigDecimal("12.345");
BigDecimal quantity = new BigDecimal("2.5");
BigDecimal rawAmount = unitPrice.multiply(quantity);
```

Đây là đoạn minh họa dùng trong một phương thức sau khi import `java.math.BigDecimal`. Kết quả chính xác là `30.8625`.

Tránh tạo một `double`, thực hiện chuỗi phép toán nhị phân rồi mới chuyển sang `BigDecimal` với kỳ vọng khôi phục toàn bộ ý nghĩa thập phân ban đầu.

Nếu đầu vào là văn bản, parse trực tiếp theo hợp đồng định dạng. Dữ liệu giao tiếp giữa các dịch vụ nên có cách mã hóa bảo toàn thập phân, chẳng hạn chuỗi số theo định dạng thống nhất hoặc số nguyên đơn vị nhỏ nhất kèm scale và đơn vị. Không phụ thuộc vào một bộ đọc JSON trung gian tự đổi mọi con số thành `double`.

### 4.2. Cộng và nhân chính xác khi chưa có yêu cầu giới hạn

`BigDecimal.add` và `multiply` không nhận `MathContext` thực hiện số học chính xác trong phạm vi biểu diễn/tài nguyên của kiểu này. Chúng không tự làm tròn về scale thanh toán.

```java
BigDecimal raw = unitPrice.multiply(quantity);
BigDecimal booked = raw.setScale(2, RoundingMode.HALF_UP);
```

Scale được áp dụng tại ranh giới đã chọn. Nếu cần precision trung gian vì phép chia hoặc giới hạn tính toán, phải quy định nó như một phần của chính sách, không thêm tùy tiện ở mọi phép cộng.

Hợp đồng tính toán chính xác, scale và các phép làm tròn được mô tả trong [Java API: BigDecimal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html).

### 4.3. Số đã chốt có thể được kiểm tra bằng UNNECESSARY

Khi nhận một số tiền đã được cam kết ở scale 2:

```java
BigDecimal accepted = incoming.setScale(2, RoundingMode.UNNECESSARY);
```

`3.4000` được chấp nhận thành `3.40`, còn `3.4001` gây `ArithmeticException`. Đây là kiểm tra khả năng biểu diễn chính xác, không phải kiểm tra số ký tự người dùng đã nhập.

Đừng dùng cách này để khẳng định mọi bước trước đó chưa mất thông tin. Nó chỉ xác nhận giá trị hiện tại phù hợp ranh giới nhận dữ liệu.

## 5. Làm tròn theo dòng và theo tổng cho kết quả khác nhau

Giả sử có ba dòng A, B, C, mỗi dòng có số tiền chưa làm tròn là `0.145`. Dùng scale 2 và `HALF_UP`.

### Chính sách chốt từng dòng

```text
A: 0.145 -> 0.15
B: 0.145 -> 0.15
C: 0.145 -> 0.15
Tổng các dòng đã chốt = 0.45
```

### Chính sách chốt trên tổng chưa làm tròn

```text
0.145 + 0.145 + 0.145 = 0.435
Chốt tổng ở scale 2 -> 0.44
```

Hai cách tính đều thực hiện đúng quy tắc đã chọn. Khác biệt nằm ở nơi đặt ranh giới làm tròn.

Nếu hợp đồng quy định tổng bằng tổng các dòng đã chốt, tổng phải được cộng từ các dòng đó. Không tính lại tổng từ dữ liệu chưa làm tròn rồi kỳ vọng luôn bằng nhau.

Nếu tổng được chốt độc lập trên dữ liệu chưa làm tròn, các giá trị dòng dùng để hiển thị hoặc ghi nhận có thể cần một quy tắc phân bổ để cộng khớp tổng. Không âm thầm cộng chênh lệch vào một dòng bất kỳ mà không có chính sách.

Một mô hình có nhiều nhóm cũng cần chỉ rõ ranh giới nhóm: chốt từng nhóm rồi cộng khác với cộng toàn bộ dữ liệu gốc rồi chốt. Điều này còn ảnh hưởng cách nhóm theo loại phí, loại dịch vụ hoặc kỳ tính.

Không có quy tắc phổ quát “luôn chỉ làm tròn ở cuối” áp dụng được cho mọi hợp đồng. Điều cần bảo đảm là thực hiện đúng những ranh giới đã được xác định.

## 6. Tính tổng: tránh làm tròn ngầm trong bộ tích lũy

Một phép cộng chính xác có thể viết bằng vòng lặp hoặc:

```java
BigDecimal total = amounts.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

Đoạn này giả định các phần tử đều khác null và cùng đơn vị. Nó không làm tròn ở mỗi bước cộng.

Nếu thay bộ tích lũy bằng “cộng rồi làm tròn ngay” hoặc dùng một `MathContext` có precision hữu hạn tại mỗi bước, thứ tự/nhóm phép cộng có thể ảnh hưởng kết quả.

Điều này đặc biệt đáng chú ý với tổng song song: không dùng một phép tích lũy có làm tròn tùy ý rồi giả định nó vẫn có tính kết hợp như phép cộng chính xác.

Các điểm cần thống nhất:

- Tổng dữ liệu rỗng là số 0; áp dụng scale chính sách ở ranh giới đầu ra nếu cần biểu diễn như `0.00`.
- Không dùng `null` để đại diện một giá trị tiền tệ bằng 0.
- Không chuyển từng giá trị sang `double` để dùng `mapToDouble().sum()`.
- Nếu cộng các số tiền đã chốt, giữ nguyên giá trị đã chốt của chúng.
- So sánh tổng về giá trị bằng `compareTo` khi khác scale không có ý nghĩa nghiệp vụ.

`BigDecimal` bất biến: `total.add(amount)` trả về đối tượng kết quả. Nếu không gán lại, biến `total` không tự tăng.

## 7. Chia một tổng thành nhiều phần mà không làm mất tổng

Bài toán chia đều `10.00` thành ba phần cho thấy vì sao làm tròn độc lập từng phần là chưa đủ:

```text
10.00 / 3 xấp xỉ 3.33
3.33 + 3.33 + 3.33 = 9.99
```

Thiếu `0.01` không phải lỗi độ chính xác của `BigDecimal`; đó là phần dư cần phân bổ.

### 7.1. Chia đều bằng số nguyên đơn vị nhỏ nhất

Trong ví dụ scale 2, đơn vị nhỏ nhất là `0.01`:

1. Kiểm tra tổng biểu diễn chính xác được ở scale 2.
2. Chuyển `10.00` thành 1000 đơn vị nhỏ nhất.
3. Chia nguyên: `1000 = 3 × 333 + 1`.
4. Mỗi phần nhận 333 đơn vị.
5. Còn dư 1 đơn vị, cấp cho người đầu theo thứ tự ổn định đã quy định.

Kết quả là `3.34, 3.33, 3.33`; tổng đúng `10.00`.

Với chia đều, các phần dư bằng nhau, nên quy tắc xử lý hòa quyết định ai nhận đơn vị thêm. Thứ tự A/B/C trong ví dụ là thứ tự đã được chọn rõ ràng. Trong ứng dụng, cần một khóa hoặc thứ tự ổn định có thể giải thích và tái hiện, không dùng thứ tự ngẫu nhiên của `HashMap`.

### 7.2. Chia theo trọng số

Với tổng không âm và các trọng số không âm có tổng lớn hơn 0, có thể thiết kế quy tắc phần dư lớn nhất:

1. Tính phần được nhận chính xác theo tỷ trọng, biểu diễn bằng phép chia số nguyên/tỷ số phù hợp.
2. Cấp phần nguyên số đơn vị nhỏ nhất cho từng bên.
3. Tính số đơn vị còn lại so với tổng đã chốt.
4. Cấp lần lượt cho các phần có số dư lớn nhất.
5. Nếu bằng nhau, dùng khóa ổn định để phân xử.

Nếu trọng số là số nguyên, có thể dùng thương và số dư của phép chia số nguyên để so sánh, tránh xấp xỉ tỷ lệ trung gian. Nếu trọng số là số thập phân, cần chuẩn hóa chúng thành tỷ lệ chính xác trước.

Đây là một chính sách phân bổ có thể chọn, không phải lựa chọn duy nhất. Chính sách phải nêu rõ tiêu chí, xử lý hòa và giới hạn đầu vào.

Với tổng âm, cần quy tắc riêng được định nghĩa rõ. Một cách thiết kế có thể là phân bổ trị tuyệt đối rồi đổi dấu toàn bộ, nhưng không nên ngầm coi thuật toán chỉ viết cho số không âm đã hỗ trợ đầy đủ số âm.

## 8. Chương trình chạy đầy đủ

Chương trình gồm một chính sách scale/mode, hai cách tính tổng, chia đều bảo toàn tổng và ví dụ bước làm tròn. Mọi giá trị trong phép cộng đều thuộc đơn vị giả định `DEMO`.

Lưu thành `DecimalMoneyPolicyDemo.java`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class DecimalMoneyPolicyDemo {
    record Policy(int amountScale, RoundingMode mode) {
        Policy {
            if (amountScale < 0) {
                throw new IllegalArgumentException("amountScale must be nonnegative");
            }
            Objects.requireNonNull(mode, "mode");
        }

        BigDecimal book(BigDecimal rawAmount) {
            return rawAmount.setScale(amountScale, mode);
        }

        BigDecimal acceptBooked(BigDecimal amount) {
            return amount.setScale(amountScale, RoundingMode.UNNECESSARY);
        }
    }

    record Line(String id, BigDecimal unitPrice, BigDecimal quantity) {
        BigDecimal rawAmount() {
            return unitPrice.multiply(quantity);
        }
    }

    private static BigDecimal sum(List<BigDecimal> amounts) {
        BigDecimal result = BigDecimal.ZERO;
        for (BigDecimal amount : amounts) {
            result = result.add(amount);
        }
        return result;
    }

    private static List<BigDecimal> splitEqualNonnegative(
            BigDecimal total, int scale, int parts) {
        if (scale < 0 || parts <= 0 || total.signum() < 0) {
            throw new IllegalArgumentException("invalid split parameters");
        }

        BigDecimal checked = total.setScale(scale, RoundingMode.UNNECESSARY);
        BigInteger units = checked.unscaledValue();
        BigInteger[] qr = units.divideAndRemainder(BigInteger.valueOf(parts));
        int extraUnits = qr[1].intValueExact();

        List<BigDecimal> result = new ArrayList<>();
        for (int i = 0; i < parts; i++) {
            BigInteger share = qr[0];
            if (i < extraUnits) {
                share = share.add(BigInteger.ONE);
            }
            result.add(new BigDecimal(share, scale));
        }

        if (sum(result).compareTo(checked) != 0) {
            throw new IllegalStateException("split does not preserve total");
        }
        return List.copyOf(result);
    }

    private static BigDecimal roundToStep(
            BigDecimal amount, BigDecimal step, int scale, RoundingMode mode) {
        if (scale < 0 || step.signum() <= 0) {
            throw new IllegalArgumentException("invalid step");
        }
        BigDecimal validStep = step.setScale(scale, RoundingMode.UNNECESSARY);
        BigDecimal count = amount.divide(validStep, 0, mode);
        return count.multiply(validStep).setScale(scale, RoundingMode.UNNECESSARY);
    }

    public static void main(String[] args) {
        Policy policy = new Policy(2, RoundingMode.HALF_UP);
        List<Line> lines = List.of(
                new Line("A", new BigDecimal("0.145"), BigDecimal.ONE),
                new Line("B", new BigDecimal("0.145"), BigDecimal.ONE),
                new Line("C", new BigDecimal("0.145"), BigDecimal.ONE)
        );

        List<BigDecimal> raw = new ArrayList<>();
        List<BigDecimal> booked = new ArrayList<>();
        System.out.println("unit=DEMO, scale=2, mode=HALF_UP");
        for (Line line : lines) {
            BigDecimal rawLine = line.rawAmount();
            BigDecimal bookedLine = policy.book(rawLine);
            raw.add(rawLine);
            booked.add(bookedLine);
            System.out.println(line.id() + ": raw=" + rawLine.toPlainString()
                    + ", booked=" + bookedLine.toPlainString());
        }

        System.out.println("sum booked lines=" + sum(booked).toPlainString());
        System.out.println("book raw total=" + policy.book(sum(raw)).toPlainString());

        List<BigDecimal> shares = splitEqualNonnegative(
                new BigDecimal("10.00"), 2, 3);
        System.out.println("equal shares A/B/C=" + shares);
        System.out.println("sum shares=" + sum(shares).toPlainString());
        System.out.println("accepted 3.4000="
                + policy.acceptBooked(new BigDecimal("3.4000")).toPlainString());
        try {
            policy.acceptBooked(new BigDecimal("3.4001"));
        } catch (ArithmeticException exception) {
            System.out.println("accepted 3.4001=ArithmeticException");
        }

        BigDecimal step = new BigDecimal("0.05");
        System.out.println("10.03 at step 0.05="
                + roundToStep(new BigDecimal("10.03"), step, 2,
                        RoundingMode.HALF_UP).toPlainString());
        BigDecimal originalBooked = policy.book(new BigDecimal("0.145"));
        System.out.println("original plus reversal="
                + originalBooked.add(originalBooked.negate()).toPlainString());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 DecimalMoneyPolicyDemo.java
java DecimalMoneyPolicyDemo
```

Stdout:

```text
unit=DEMO, scale=2, mode=HALF_UP
A: raw=0.145, booked=0.15
B: raw=0.145, booked=0.15
C: raw=0.145, booked=0.15
sum booked lines=0.45
book raw total=0.44
equal shares A/B/C=[3.34, 3.33, 3.33]
sum shares=10.00
accepted 3.4000=3.40
accepted 3.4001=ArithmeticException
10.03 at step 0.05=10.05
original plus reversal=0.00
```

Những giới hạn được đặt rõ trong chương trình:

- `splitEqualNonnegative` chỉ nhận tổng không âm, scale không âm và số phần dương.
- Tổng phải chuyển chính xác về scale đã chọn trước khi chia phần.
- Phần dư cấp theo chỉ số đầu danh sách; A/B/C là thứ tự người nhận của ví dụ.
- `BigInteger` dùng để xử lý số đơn vị nhỏ nhất mà không bị giới hạn bởi miền `long`.
- Phép kiểm tra cuối xác nhận tổng phân bổ bằng đúng tổng ban đầu về giá trị số học.

Các record trong ví dụ giúp nhìn rõ phép tính; chúng chưa phải mô hình tiền tệ hoàn chỉnh. Khi áp dụng thực tế cần gắn đơn vị, kiểm tra id, null, miền giá trị, tính hợp lệ của số lượng và giới hạn kích thước dữ liệu theo hợp đồng của ứng dụng.

## 9. Scale không diễn tả mọi bước làm tròn

Giữ hai chữ số sau dấu thập phân cho phép `10.01`, `10.02`, `10.03`... Nó không buộc số tiền phải là bội của `0.05`.

Nếu chính sách giả định yêu cầu các mức cách nhau `0.05`, cách tính là:

```text
số bước = làm tròn(amount / 0.05) về số nguyên
kết quả = số bước × 0.05
```

Với `10.03` và `HALF_UP`:

```text
10.03 / 0.05 = 200.6
số bước = 201
kết quả = 10.05
```

Phương thức `roundToStep` trong chương trình thực hiện phép toán này và kiểm tra bước biểu diễn chính xác được ở scale đã chọn. Ví dụ chỉ minh họa số học; việc một kênh hay loại tiền có yêu cầu bước như vậy phải là dữ liệu chính sách được xác định riêng.

Cần tránh làm tròn về scale thanh toán trước khi áp dụng bước nếu hợp đồng không yêu cầu, vì có thể tạo thêm một lần làm tròn. Thời điểm áp dụng bước cũng thuộc chính sách: cho từng dòng hay chỉ cho tổng thanh toán.

## 10. Số âm, hoàn trả và đảo giao dịch

Các chế độ theo hướng không có cùng ý nghĩa khi đổi dấu:

- `CEILING` hướng về dương vô cùng.
- `FLOOR` hướng về âm vô cùng.
- `UP` ra xa 0; `DOWN` về 0.

Chẳng hạn, scale 2 với `CEILING` biến `0.145` thành `0.15`, nhưng `-0.145` thành `-0.14`. Cộng hai kết quả không được 0.

Nếu yêu cầu là đảo chính xác một khoản đã ghi nhận, việc lấy số tiền đã ghi nhận rồi `negate()` bảo đảm giá trị đảo đối nhau. Tính lại khoản âm từ dữ liệu ban đầu bằng một chế độ theo hướng có thể không cho đúng số đối.

Điều này không có nghĩa mọi hoàn trả đều chỉ là đổi dấu. Một hoàn trả một phần, có phí hoặc dùng một chính sách khác là bài toán cần hợp đồng riêng. Phải phân biệt “đảo đúng bút toán đã lưu” với “tính một giao dịch mới”.

Chương trình minh họa trường hợp đảo đúng khoản đã chốt: `0.15 + (-0.15) = 0.00`.

## 11. Lưu trữ, giao tiếp và khả năng tái hiện

Một kết quả tính tiền cần giữ được ý nghĩa khi đi qua các lớp của hệ thống:

- Lưu kèm mã đơn vị và scale/định dạng theo hợp đồng, không chỉ một chuỗi đã gắn ký hiệu.
- Cấu hình cột thập phân trong cơ sở dữ liệu phải đủ precision và scale cần dùng; tránh để một tầng lưu trữ tự làm tròn ngoài chính sách.
- Nếu dùng số nguyên đơn vị nhỏ nhất, kiểm tra chuyển đổi chính xác; với `long` phải xét miền giá trị và tràn số.
- Giao tiếp giữa dịch vụ cần giữ được dữ liệu thập phân chính xác; không để bộ đọc trung gian vô tình dùng số dấu phẩy động nhị phân.
- Phân biệt giá trị dùng để tính với chuỗi hiển thị có dấu phân cách theo ngôn ngữ.
- Kết quả đã chốt phải gắn được với dữ liệu đầu vào và phiên bản chính sách đủ để giải thích/tái hiện.

Không cần lưu mọi giá trị trung gian trong mọi ứng dụng. Nhưng nếu lưu cả dữ liệu gốc và số tiền đã chốt, phải xác định rõ trường nào là căn cứ cho tính tổng, hoàn trả và đối soát; tránh mỗi nơi chọn một nguồn khác nhau.

Đổi mode hoặc thời điểm làm tròn là thay đổi hành vi nghiệp vụ. Không tự tính lại giao dịch lịch sử bằng cấu hình mới rồi coi kết quả mới tương đương số đã ghi nhận.

## 12. Các bất biến và trường hợp nên kiểm chứng

Một số điều kiện có thể kiểm tra tự động:

| Điều kiện | Mục đích |
|---|---|
| Tổng các phần phân bổ bằng tổng đã chốt | Không mất hoặc sinh thêm đơn vị nhỏ nhất |
| Mỗi phần biểu diễn được ở scale cho phép | Tránh phần chia còn quá nhiều chữ số |
| Cùng input, cùng chính sách và cùng khóa hòa cho cùng kết quả | Có thể tái hiện |
| Tổng không trộn nhiều đơn vị tiền tệ | Không cộng các đại lượng khác đơn vị |
| Đảo chính xác khoản đã chốt có tổng bằng 0 | Kiểm chứng thao tác đảo đã định nghĩa |
| Dữ liệu đã chốt không bị làm tròn thêm khi đi qua ranh giới nhận | Phát hiện chuyển đổi ngoài hợp đồng |

Các đầu vào đáng kiểm tra gồm:

- Ngay dưới, đúng và ngay trên điểm giữa.
- Số 0, tổng rỗng, giá trị âm nếu được hỗ trợ.
- Nhiều dòng rất nhỏ có tổng đáng kể.
- Số có phần nguyên lớn và phần thập phân dài.
- Tổng chia hết hoặc có dư; tổng nhỏ hơn số phần.
- Các trọng số bằng nhau và số dư bằng nhau.
- Nhiều biểu diễn cùng giá trị như `2.5`, `2.50`, `2.5000`.
- Chuyển qua lưu trữ/giao tiếp rồi đọc lại.

Khi có làm tròn trung gian, đừng tự yêu cầu “đổi thứ tự cộng vẫn phải giữ nguyên” nếu thuật toán đã làm mất tính kết hợp; nên thiết kế lại nơi làm tròn hoặc chứng minh vì sao việc nhóm/tính song song không ảnh hưởng hợp đồng.

## 13. Bài tập

1. Ba dòng đều bằng `0.145`, scale 2, `HALF_UP`. Tổng chốt từng dòng và tổng chốt từ số gốc bằng bao nhiêu?
2. Chia đều `0.02` thành ba phần theo thuật toán không âm trong bài, thứ tự A/B/C. Kết quả là gì?
3. Một đầu vào `5.6700` có được nhận bằng `setScale(2, UNNECESSARY)` không? `5.6701` thì sao?
4. Vì sao chỉ cấu hình scale 2 chưa thực hiện được bước làm tròn `0.05`?
5. Vì sao không nên dùng một `MathContext(2)` cho mọi phép cộng chỉ vì số tiền đầu ra có hai chữ số sau dấu thập phân?
6. Với một khoản đã ghi nhận, yêu cầu đảo chính xác khoản đó cần căn cứ vào số tiền nào?

Đáp án:

1. Tổng từng dòng là `0.45`; chốt từ tổng gốc là `0.44`.
2. `0.01, 0.01, 0.00`; tổng vẫn là `0.02`.
3. `5.6700` được nhận thành `5.67`; `5.6701` gây `ArithmeticException`.
4. Scale 2 vẫn cho mọi bội của `0.01`; yêu cầu bội của `0.05` là một điều kiện khác.
5. Precision 2 giới hạn tổng số chữ số có nghĩa, không phải số chữ số sau dấu thập phân; làm tròn tại mỗi phép cộng còn có thể thay đổi kết quả theo cách nhóm.
6. Số tiền thực tế đã được chốt và ghi nhận; đổi dấu giá trị đó cho trường hợp đảo chính xác, theo đúng hợp đồng đã định nghĩa.
