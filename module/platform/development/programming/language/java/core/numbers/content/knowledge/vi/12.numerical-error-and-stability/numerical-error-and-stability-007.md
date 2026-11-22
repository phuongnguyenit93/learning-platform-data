# Không làm tròn sau mọi phép tính nếu hợp đồng không yêu cầu

Trong Java, **làm tròn số không phải là công việc nên tự động thêm sau mọi phép toán**. Một chương trình có thể cần độ chính xác để tính toán nội bộ, rồi mới làm tròn đến một đơn vị được quy định khi quyết toán, ghi sổ hoặc hiển thị. Làm tròn quá sớm có thể làm mất thông tin và khiến tổng cuối khác với phép tính giữ độ chính xác rồi chỉ làm tròn tại điểm chốt.

Nhưng cũng không thể khẳng định **chỉ làm tròn cuối luôn đúng**: nếu hợp đồng hoặc quy định yêu cầu mỗi dòng hóa đơn, từng giao dịch, từng phần phân bổ phải được làm tròn độc lập, những điểm đó là ranh giới nghiệp vụ bắt buộc.

Bài học phân biệt ba khái niệm: **làm tròn nhị phân cố hữu** của `float`/`double`; **làm tròn thập phân chủ động** bằng `BigDecimal`, `Math.round` và `RoundingMode`; và **định dạng kết quả để hiển thị**. Cách quyết định đúng là đọc hợp đồng tính toán: làm tròn **giá trị nào, vào lúc nào, đến bao nhiêu chữ số, bằng quy tắc nào**?

## 1. Làm tròn mỗi khoản và làm tròn tổng có thể khác nhau

Giả sử hai khoản đều bằng `0.015`, và ta phải làm tròn về **hai chữ số thập phân** theo quy tắc `HALF_UP`.

**Phương án A — chốt từng khoản trước khi cộng:**

```text
0.015 -> 0.02
0.015 -> 0.02
Tổng = 0.04
```

**Phương án B — cộng trước, chốt tổng sau:**

```text
0.015 + 0.015 = 0.030
round(0.030, 2) = 0.03
```

Cùng dữ liệu, cùng scale, cùng rounding mode nhưng chênh `0.01`. Nếu **mỗi khoản là nghĩa vụ thanh toán độc lập** được ghi nhận ở `0.02`, tổng `0.04` có thể đúng. Nếu **hai khoản chỉ là thành phần trung gian của một nghĩa vụ chung** và yêu cầu chốt một lần, `0.03` phù hợp. Không thể tự chọn cách nào nếu hợp đồng chưa xác định.

Ví dụ Java dùng `BigDecimal` chính xác từ chuỗi:

```java
BigDecimal amount = new BigDecimal("0.015");

BigDecimal roundedEach = amount.setScale(2, RoundingMode.HALF_UP);
BigDecimal sumRoundedLines = roundedEach.add(roundedEach); // 0.04

BigDecimal sumThenRound = amount.add(amount)
        .setScale(2, RoundingMode.HALF_UP); // 0.03
```

Các đoạn code ngắn trong bài giả định đã có `import java.math.BigDecimal;` và `import java.math.RoundingMode;`, đặt trong một method. Chương trình độc lập đầy đủ nằm ở phần 9.

## 2. Đừng nhầm làm tròn thập phân chủ động với precision nhị phân

Java `double` có phần trị khoảng 53 bit, `float` khoảng 24 bit. Phần lớn phân số thập phân như `0.1` không có biểu diễn nhị phân hữu hạn, nên giá trị lưu trữ và mỗi phép toán số thực có thể chịu làm tròn **kể cả khi ta không hề gọi hàm round**.

```java
double value = 0.1 + 0.2;
System.out.println(value); // 0.30000000000000004
```

Vì vậy khuyến cáo “không làm tròn sau mọi phép tính” nghĩa là **không tự ép kết quả sau mỗi bước về số chữ số thập phân tùy chọn**, chứ không phải máy tính có thể loại bỏ sai số IEEE 754.

Việc viết:

```java
double value = 0.1 + 0.2;
String displayed = String.format(java.util.Locale.US, "%.2f", value);
// displayed là chuỗi "0.30"; value vẫn là 0.30000000000000004
```

chỉ **định dạng chuỗi**. Nó không sửa giá trị `value`. Nếu lưu chuỗi đã định dạng rồi parse ngược để tính tiếp, chương trình đã âm thầm đưa một bước làm tròn vào dữ liệu.

### Vì sao làm tròn mọi bước không “sửa” số thực?

- Có phép toán đã mất độ chính xác **trước** khi bước làm tròn thập phân diễn ra.
- Làm tròn theo scale nhỏ sau mỗi bước lại xóa thêm thông tin.
- Các bước sau có thể cộng dồn phần chênh mới.
- `double` chứa giá trị nhị phân; kết quả `Math.round(x * 100) / 100.0` vẫn mang kiểu `double` và không nhất thiết biểu diễn chính xác bội số `0.01`.

Chỉ dùng phép làm tròn thập phân khi đó **thực sự là một phần của yêu cầu**, không phải vì muốn số in ra đẹp hơn.

## 3. Scale, precision và rounding mode trong `BigDecimal`

`BigDecimal` phân biệt:

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Scale** | Vị trí dấu thập phân, thường tương ứng số chữ số sau dấu chấm khi scale không âm | `12.345` có scale 3 |
| **Precision** | Tổng chữ số có nghĩa của hệ thập phân | `12.345` có precision 5 |
| **Rounding mode** | Chính sách quyết định khi phải bỏ chữ số có nghĩa | `HALF_UP`, `HALF_EVEN`, `DOWN` ... |

`setScale(2, RoundingMode.HALF_UP)` yêu cầu **hai chữ số sau dấu chấm**. `round(new MathContext(4, HALF_UP))` yêu cầu **bốn chữ số có nghĩa**:

```java
BigDecimal x = new BigDecimal("123.4567");

BigDecimal byScale = x.setScale(2, RoundingMode.HALF_UP);
// 123.46

BigDecimal byPrecision = x.round(
        new java.math.MathContext(4, RoundingMode.HALF_UP));
// 123.5
```

Hai thao tác không thay thế nhau. `MathContext(2)` **không** có nghĩa làm tròn mọi giá trị đến 2 chữ số sau dấu thập phân.

Các mode phổ biến:

| Mode | Ý nghĩa | Ví dụ scale 2 |
| --- | --- | --- |
| `HALF_UP` | Trường hợp đúng giữa hai khả năng, làm tròn ra xa 0 | `2.345 -> 2.35` |
| `HALF_EVEN` | Trường hợp đúng giữa, chọn chữ số cuối giữ lại chẵn | `2.345 -> 2.34`; `2.355 -> 2.36` |
| `DOWN` | Bỏ phần dư về phía 0 | `-2.349 -> -2.34` |
| `FLOOR` | Hướng về âm vô cực | `-2.341 -> -2.35` |
| `CEILING` | Hướng về dương vô cực | `-2.341 -> -2.34` |
| `UNNECESSARY` | Không cho phép mất chữ số có nghĩa; nếu cần làm tròn thì ném `ArithmeticException` | `2.340 -> 2.34` hợp lệ; `2.345` bị từ chối |

**Không có một mode đúng cho mọi nghiệp vụ.** Cần biết quy định đối với số âm, điểm giữa, tiền tệ, thuế, đo lường và từng ranh giới quyết toán.

## 4. Dùng `BigDecimal` khi cần tính decimal chính xác

Đối với phép cộng, trừ và nhân, `BigDecimal` tạo từ chuỗi cùng API không truyền `MathContext` có thể giữ kết quả thập phân chính xác (trong giới hạn tài nguyên).

```java
BigDecimal a = new BigDecimal("0.015");
BigDecimal b = new BigDecimal("0.015");
BigDecimal sum = a.add(b); // 0.030
BigDecimal settled = sum.setScale(2, RoundingMode.HALF_UP); // 0.03
```

Không nên tạo decimal chính xác từ literal `double` bằng constructor:

```java
BigDecimal exactDecimal = new BigDecimal("0.1");
BigDecimal fromTextRepresentation = BigDecimal.valueOf(0.1);
BigDecimal fromBinaryApproximation = new BigDecimal(0.1);
```

`new BigDecimal(0.1)` thể hiện **chính xác số nhị phân xấp xỉ 0.1 đang nằm trong `double`**, chứ không phải đúng số thập phân `0.1`. Dùng chuỗi thập phân hoặc số nguyên kèm scale nếu dữ liệu gốc thuộc mô hình decimal.

### Phép chia là ngoại lệ quan trọng

`1/3` không có biểu diễn thập phân hữu hạn, nên `BigDecimal.ONE.divide(BigDecimal.valueOf(3))` ném `ArithmeticException` nếu không chỉ định cách xử lý. Có thể dùng:

```java
BigDecimal third = BigDecimal.ONE.divide(
        BigDecimal.valueOf(3), 6, RoundingMode.HALF_UP);
// 0.333333
```

Phép chia này buộc phải chọn precision/scale làm việc và sẽ có sai số. **Làm tròn trung gian có thể cần thiết** khi kết quả không biểu diễn hữu hạn. Mục tiêu là chọn độ chính xác làm việc đủ cho yêu cầu và không tiếp tục thu hẹp tùy tiện sau mọi phép cộng/nhân.

Cũng cần chú ý truyền `MathContext` có precision hữu hạn vào mỗi phép `add`/`multiply` có thể **chủ động làm tròn ngay ở các bước đó**, khác với việc dùng API không truyền context.

## 5. Làm tròn đơn giá trước hay thành tiền dòng trước?

Giả sử đơn giá chính xác là `0.335`, số lượng là `3`, mode `HALF_UP` và đích là scale 2.

**Chốt đơn giá trước:**

```text
round(0.335, 2) = 0.34
0.34 * 3 = 1.02
```

**Tính thành tiền dòng trước:**

```text
0.335 * 3 = 1.005
round(1.005, 2) = 1.01
```

Trong Java:

```java
BigDecimal price = new BigDecimal("0.335");
BigDecimal quantity = BigDecimal.valueOf(3);

BigDecimal totalFromUnit = price.setScale(2, RoundingMode.HALF_UP)
        .multiply(quantity); // 1.02

BigDecimal totalFromLine = price.multiply(quantity)
        .setScale(2, RoundingMode.HALF_UP); // 1.01
```

Nếu hợp đồng định nghĩa **đơn giá được chốt ở 0.34**, phép nhân theo đơn giá đã chốt có thể là đúng. Nếu hợp đồng định nghĩa đơn giá gốc 0.335 dùng để tính **thành tiền dòng** rồi mới làm tròn, kết quả là 1.01.

Điểm quan trọng là phân biệt **giá trị trung gian**, **giá trị đã được quyết toán** và **giá trị chỉ định dạng để hiển thị**. Khi một khoản đã chốt theo quy định, tổng về sau phải dựa trên dữ liệu đã chốt nếu hợp đồng yêu cầu, chứ không tự tính lại một cách khác.

## 6. Những trường hợp cần làm tròn giữa chừng

Khuyến cáo này **không cấm làm tròn có mục đích**. Ví dụ:

- **Dòng hóa đơn độc lập:** nếu thuế từng dòng phải được làm tròn, tổng thuế theo quy định có thể là tổng **thuế các dòng đã chốt**.
- **Giao dịch được thanh toán độc lập:** mỗi khoản đã chuyển thực tế là một nghĩa vụ ở đơn vị tiền tệ nhỏ nhất. Không thể tính lại từ các số tiền “chưa làm tròn” rồi ghi đè lịch sử giao dịch.
- **Chia tổng tiền thành nhiều phần:** từng phần phải nằm trên lưới đơn vị thanh toán; cần giải quyết khoản dư để bảo toàn tổng.
- **Dữ liệu đo lường:** ở lúc tiếp nhận kết quả từ thiết bị có độ phân giải cố định, làm tròn/lượng tử hóa có thể là một phần của phép đo.
- **Thuật toán có phép lượng tử hóa được đặc tả:** nếu mỗi vòng lặp được yêu cầu làm tròn, bỏ bước ấy sẽ thay đổi thuật toán.

Ví dụ chia `10.00` thành ba khoản ở scale 2: `10 / 3` cho 3.333...; làm tròn từng khoản thành `3.33` rồi cộng sẽ chỉ được `9.99`. Một chính sách bảo toàn tổng có thể phân bổ thành `3.34 + 3.33 + 3.33 = 10.00`. Cần đặc tả ai nhận phần dư, phương thức phân bổ và cách xử lý khoản âm.

**Ranh giới nghiệp vụ** quan trọng hơn số lượng bước tính hoặc cảm giác rằng “số tiền chỉ có hai chữ số sau dấu chấm”.

## 7. `Math.round` không tự động tương đương một quy tắc kế toán

Một mẹo thường thấy:

```java
double x = 12.345;
double twoPlaces = Math.round(x * 100.0) / 100.0;
```

Nó có những hạn chế:

- `x` và phép nhân `x*100` có thể đã là các xấp xỉ nhị phân.
- `Math.round(double)` trả `long` và quy tắc điểm giữa hướng về dương vô cực: `Math.round(1.5)` là 2, nhưng `Math.round(-1.5)` là -1.
- Với giá trị cực lớn hoặc NaN/vô cực, bước chuyển thành `long` có hành vi giới hạn riêng.
- `twoPlaces` vẫn là `double`; biểu diễn nhị phân không đảm bảo đúng mọi bội của 0.01.
- Nếu đặt mẹo này ở **mọi bước trung gian**, bạn lại làm mất thêm thông tin.

```java
System.out.println(Math.round(1.5));  // 2
System.out.println(Math.round(-1.5)); // -1
```

Trong khi `new BigDecimal("-1.5").setScale(0, RoundingMode.HALF_UP)` cho -2. Hai API không cùng quy tắc tại điểm giữa âm. Quy định nghiệp vụ cần nêu rõ chế độ làm tròn, thay vì dùng “round” như một khái niệm mơ hồ.

Nếu chỉ cần in, `String.format` trả chuỗi, không thay đổi biến. Nếu cần decimal chính xác có thể tính tiếp, chọn mô hình decimal thích hợp từ đầu.

## 8. Hoãn làm tròn chưa đủ để bảo đảm ổn định số học

Ngay cả khi không thêm phép làm tròn decimal, `double` vẫn có các rủi ro: mất chữ số có nghĩa, sai số tích lũy và kết quả phụ thuộc thứ tự phép toán.

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

double first = (a + b) + c; // 1.0
double second = a + (b + c); // 0.0
```

Toán học thực cho cùng kết quả 1, nhưng `b + c` làm mất đóng góp 1 ở mức khoảng 1e16 vì precision `double` không đủ. Đây là **tính không kết hợp của số học dấu phẩy động**.

Khi yêu cầu nghiêm ngặt, cần cân nhắc thuật toán ổn định số, thứ tự cộng, phương pháp bù sai số, `BigDecimal` hoặc kiểu khác thích hợp. **Tránh làm tròn sớm** chỉ là một nguyên tắc giữ thông tin, không thay thế thiết kế thuật toán số.

## 9. Chương trình Java 17+ hoàn chỉnh

Lưu nội dung dưới đây thành **`RoundingBoundaryDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;

public class RoundingBoundaryDemo {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("0.015");
        BigDecimal each = amount.setScale(2, RoundingMode.HALF_UP);
        System.out.println("roundEach=" + each.add(each).toPlainString());
        System.out.println("roundTotal=" +
                amount.add(amount).setScale(2, RoundingMode.HALF_UP));

        BigDecimal unit = new BigDecimal("0.335");
        BigDecimal quantity = BigDecimal.valueOf(3);
        System.out.println("unitRounded=" +
                unit.setScale(2, RoundingMode.HALF_UP)
                        .multiply(quantity).toPlainString());
        System.out.println("lineRounded=" +
                unit.multiply(quantity)
                        .setScale(2, RoundingMode.HALF_UP).toPlainString());

        System.out.println("halfUpTie=" +
                new BigDecimal("2.345").setScale(2, RoundingMode.HALF_UP));
        System.out.println("halfEvenTie=" +
                new BigDecimal("2.345").setScale(2, RoundingMode.HALF_EVEN));
        System.out.println("halfEvenOther=" +
                new BigDecimal("2.355").setScale(2, RoundingMode.HALF_EVEN));

        try {
            new BigDecimal("2.345").setScale(2, RoundingMode.UNNECESSARY);
            System.out.println("unnecessary=missed");
        } catch (ArithmeticException ex) {
            System.out.println("unnecessary=detected");
        }

        try {
            BigDecimal.ONE.divide(BigDecimal.valueOf(3));
            System.out.println("divideExact=unexpected");
        } catch (ArithmeticException ex) {
            System.out.println("divideExact=requiresRounding");
        }

        BigDecimal third = BigDecimal.ONE.divide(
                BigDecimal.valueOf(3), 6, RoundingMode.HALF_UP);
        System.out.println("third=" + third.toPlainString());
        System.out.println("thirdTimesThree=" +
                third.multiply(BigDecimal.valueOf(3)).toPlainString());
        System.out.println("thirdAtBoundary=" +
                third.multiply(BigDecimal.valueOf(3))
                        .setScale(2, RoundingMode.HALF_UP).toPlainString());

        double binarySum = 0.1 + 0.2;
        System.out.println("binarySum=" + binarySum);
        System.out.println("display=" +
                String.format(Locale.US, "%.2f", binarySum));
        System.out.println("rawValue=" + binarySum);

        System.out.println("mathRoundPositive=" + Math.round(1.5));
        System.out.println("mathRoundNegative=" + Math.round(-1.5));

        double first = (1e16 + -1e16) + 1.0;
        double second = 1e16 + (-1e16 + 1.0);
        System.out.println("associationFirst=" + first);
        System.out.println("associationSecond=" + second);
    }
}
```

Dùng JDK 17 trở lên:

```bash
javac RoundingBoundaryDemo.java
java RoundingBoundaryDemo
```

Kết quả mong đợi:

```text
roundEach=0.04
roundTotal=0.03
unitRounded=1.02
lineRounded=1.01
halfUpTie=2.35
halfEvenTie=2.34
halfEvenOther=2.36
unnecessary=detected
divideExact=requiresRounding
third=0.333333
thirdTimesThree=0.999999
thirdAtBoundary=1.00
binarySum=0.30000000000000004
display=0.30
rawValue=0.30000000000000004
mathRoundPositive=2
mathRoundNegative=-1
associationFirst=1.0
associationSecond=0.0
```

Kết quả `roundEach` và `roundTotal` khác nhau dù quy tắc scale/mode giống nhau. Hai ví dụ đơn giá chứng minh lựa chọn ranh giới rất quan trọng. `display=0.30` không làm thay đổi `rawValue`, và hai dòng association là ví dụ độc lập về sai số thuật toán dấu phẩy động.

## 10. Cách mô tả hợp đồng làm tròn cho ứng dụng

Một đặc tả tốt cần trả lời:

| Câu hỏi | Thông tin cần quy định |
| --- | --- |
| Đầu vào là decimal chính xác hay số đo xấp xỉ? | Chuỗi decimal, số nguyên đơn vị nhỏ nhất, float/double đo lường |
| Đơn vị và miền giá trị là gì? | Đồng, xu, phần trăm, đơn vị vật lý, khoảng hợp lệ |
| Giá trị được **chốt** là gì? | Đơn giá, từng dòng, từng khoản thuế, tổng hóa đơn, khoản thanh toán |
| Ranh giới làm tròn ở đâu? | Sau mỗi khoản, sau tổng, khi trả kết quả hay khi hiển thị |
| Dùng scale và mode nào? | `scale=2`, `HALF_UP` hoặc quy tắc khác |
| Tổng phải bảo toàn theo các khoản đã chốt không? | Cách cộng/phân phối phần dư |
| Phép chia vô hạn thập phân xử lý thế nào? | Precision làm việc, rounding mode và chính sách sai số |
| Giá trị nào được lưu để đối soát? | Bản ghi quyết toán và (nếu cần) giá trị gốc phục vụ kiểm toán |

Một luồng điển hình là: **kiểm tra dữ liệu → tính với precision phù hợp → chỉ làm tròn tại ranh giới có ý nghĩa → lưu giá trị đã chốt → định dạng hiển thị**. Các phép tính sau phải dùng giá trị đã chốt nếu hợp đồng yêu cầu. Đừng vô tình parse dữ liệu hiển thị đã làm tròn rồi dùng làm nguồn tính mới.

## 11. Các lỗi phổ biến và checklist

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Round sau mọi phép tính làm kết quả chính xác hơn.” | Có thể làm tổng sai khác và mất dữ liệu trung gian. |
| “Round một lần cuối bao giờ cũng đúng.” | Sai nếu từng dòng hoặc giao dịch có nghĩa vụ chốt độc lập. |
| “Không gọi `Math.round` thì `double` không bao giờ bị làm tròn.” | Sai, số thực nhị phân hữu hạn vốn chịu roundoff. |
| “`String.format("%.2f", x)` sửa `x`.” | Sai, trả chuỗi định dạng. |
| “`setScale(2)` giống `MathContext(2)`.” | Sai, scale khác số chữ số có nghĩa. |
| “`BigDecimal` tự chia chính xác được 1/3.” | Sai, cần precision/rounding hoặc xử lý exception. |
| “Dùng `new BigDecimal(0.1)` là lấy thập phân 0.1 chính xác.” | Sai, nó lấy giá trị nhị phân xấp xỉ đã nằm trong `double`. |
| “`Math.round` luôn giống `HALF_UP`.” | Sai, nhất là tie âm. |
| “Ba khoản `3.33` cộng lại bằng `10.00`.” | Sai, tổng `9.99`; cần phân bổ phần dư theo hợp đồng. |
| “Không round sớm bảo đảm tính toán không sai số.” | Sai, cần xét thuật toán và precision của kiểu dữ liệu. |

Trước khi viết một phép làm tròn mới, hãy tự hỏi: **(1)** yêu cầu nào bắt buộc nó, **(2)** giá trị nào phải được chốt, **(3)** scale/mode nào được áp dụng, **(4)** tổng dùng bản gốc hay các khoản đã chốt, **(5)** có cần bảo toàn tổng/đối soát không, và **(6)** đây là phép tính hay chỉ là định dạng hiển thị?

**Kết luận:** Đừng làm tròn sau mọi phép tính chỉ vì muốn kết quả “gọn”. Hãy làm tròn **đúng ranh giới được quy định**, bằng **kiểu số và rounding mode phù hợp**. Khi cần thiết, giữ precision nội bộ để tránh mất thông tin; khi hợp đồng yêu cầu chốt từng khoản, phải thực hiện và bảo toàn chính những khoản đã chốt đó.