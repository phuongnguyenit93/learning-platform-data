# HALF_EVEN và lựa chọn chữ số chẵn trong BigDecimal

## 1. Vì sao cần quy tắc HALF_EVEN?

Khi biểu diễn hoặc tính toán số thập phân với số chữ số giới hạn, đôi khi phải bỏ bớt chữ số. Thông thường ta làm tròn đến giá trị **gần số ban đầu nhất**. Tuy nhiên, có những giá trị nằm **chính xác giữa hai kết quả hợp lệ** (gọi là *halfway* hoặc *tie*): cần thêm quy tắc để chọn một phía.

**RoundingMode.HALF_EVEN** trong Java là quy tắc *round to nearest, ties to even*: **chọn kết quả gần nhất; nếu hai phía cách đều nhau, chọn kết quả có chữ số cuối được giữ lại là số chẵn** (0, 2, 4, 6, 8). Đây còn được gọi là *round half to even* hoặc *banker's rounding*.

Phạm vi: Java 17+, `java.math.BigDecimal`, `java.math.RoundingMode`, `java.math.MathContext`. Bài này giải thích chính xác chữ số nào phải chẵn, những trường hợp không thực sự là tie, xử lý số âm, khác biệt với HALF_UP/HALF_DOWN và lựa chọn thời điểm làm tròn trong ứng dụng.

## 2. Cơ chế: gần nhất trước, chẵn chỉ khi hòa

Giả sử làm tròn một giá trị đến số nguyên. Những giá trị có phần lẻ khác 0.5 được làm tròn về số nguyên gần hơn. Nếu phần lẻ bằng đúng 0.5, hai số nguyên gần nhất cách đều nhau nên HALF_EVEN chọn số chẵn:

| Số gốc | Hai kết quả gần nhất | HALF_EVEN | Lý do |
| --- | --- | ---: | --- |
| 2.4 | 2 và 3 | 2 | Khoảng cách đến 2 nhỏ hơn |
| 2.5 | 2 và 3 | 2 | Hòa; 2 chẵn |
| 3.5 | 3 và 4 | 4 | Hòa; 4 chẵn |
| 4.5 | 4 và 5 | 4 | Hòa; 4 chẵn |
| 5.5 | 5 và 6 | 6 | Hòa; 6 chẵn |
| -2.5 | -3 và -2 | -2 | Hòa; chữ số 2 chẵn |
| -3.5 | -4 và -3 | -4 | Hòa; chữ số 4 chẵn |
| 2.51 | 2 và 3 | 3 | Gần 3 hơn; không hòa |

**HALF_EVEN không có nghĩa “luôn làm tròn thành số nguyên chẵn”.** Khi giá trị không hòa, một kết quả có chữ số lẻ vẫn được chọn nếu nó gần hơn, như 2.51 → 3.

Khi cần giữ chữ số thập phân, tính chẵn/lẻ áp dụng cho **chữ số cuối cùng được giữ lại**, không phải phần nguyên. Nếu làm tròn 1.25 đến một chữ số thập phân, ta chọn giữa 1.2 và 1.3: 1.2 có chữ số hàng phần mười là 2 (chẵn), nên được chọn. Với 1.35, ta chọn 1.4 vì chữ số 4 chẵn.

### Kiểm tra tie chính xác

Với scale đích bằng 2, hai số thập phân kề nhau cách 0.01; điểm giữa cách mỗi phía 0.005.

- **1.005**: chính giữa 1.00 và 1.01 → 1.00 (hàng phần trăm là 0, chẵn).
- **1.015**: chính giữa 1.01 và 1.02 → 1.02 (chữ số 2, chẵn).
- **1.0050**: vẫn bằng 1.005, nên vẫn hòa → 1.00.
- **1.0051**: gần 1.01 hơn → 1.01, dù chữ số hàng phần trăm là 1 (lẻ).
- **1.0049**: gần 1.00 hơn → 1.00.

Nếu chữ số đầu tiên bị bỏ là 5 nhưng **phần bị bỏ sau chữ số 5 còn khác 0**, giá trị không nằm chính giữa. Đừng quyết định theo chẵn/lẻ trước khi xác định khoảng cách.

## 3. Dùng setScale(scale, RoundingMode.HALF_EVEN)

Trong BigDecimal, phương thức `setScale(int newScale, RoundingMode roundingMode)` tạo biểu diễn với scale yêu cầu. Scale bằng 0 tương ứng không có chữ số sau dấu thập phân; scale 1 giữ một chữ số; scale 2 giữ hai chữ số. Scale âm cho phép làm tròn đến hàng chục, hàng trăm.

Ví dụ, `x.setScale(2, RoundingMode.HALF_EVEN)` yêu cầu giữ đúng hai chữ số thập phân và dùng HALF_EVEN nếu phải bỏ các chữ số có giá trị. Nếu chỉ tăng scale như 1.2 → 1.200, không có giá trị nào bị bỏ, nên không thực hiện làm tròn theo nghĩa chọn gần nhất. BigDecimal là **immutable**: phương thức trả về giá trị, không sửa đối tượng gốc.

### Ví dụ Java 17: tie khi làm tròn số nguyên

Lưu dưới tên `HalfEvenIntegerDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class HalfEvenIntegerDemo {
    public static void main(String[] args) {
        String[] inputs = {
            "2.4", "2.5", "3.5", "4.5",
            "5.5", "-2.5", "-3.5", "2.51"
        };

        for (String input : inputs) {
            BigDecimal x = new BigDecimal(input);
            BigDecimal rounded = x.setScale(0, RoundingMode.HALF_EVEN);
            System.out.println(input + " -> " + rounded.toPlainString());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac HalfEvenIntegerDemo.java
java HalfEvenIntegerDemo
~~~

Đầu ra chính xác:

~~~text
2.4 -> 2
2.5 -> 2
3.5 -> 4
4.5 -> 4
5.5 -> 6
-2.5 -> -2
-3.5 -> -4
2.51 -> 3
~~~

Cặp 2.5/3.5 chứng minh HALF_EVEN không mặc định luôn làm tròn lên hay xuống. Hai giá trị âm chứng minh đây cũng không phải quy tắc luôn làm tròn về 0.

## 4. Trường hợp thập phân, dấu âm và chuyển nhớ

Với scale đích bằng 1, chữ số cuối được giữ lại nằm ở hàng phần mười. Tương tự, với scale đích bằng 2, xét hàng phần trăm. Những chữ số chẵn có thể nằm sau dấu thập phân, dù phần nguyên là số chẵn hay lẻ.

| Giá trị | Scale đích | Kết quả HALF_EVEN | Lý do |
| --- | ---: | --- | --- |
| 1.25 | 1 | 1.2 | Tie, chữ số 2 chẵn |
| 1.35 | 1 | 1.4 | Tie, chữ số 4 chẵn |
| 1.2500 | 1 | 1.2 | Số 0 phía sau không phá tie |
| 1.2501 | 1 | 1.3 | Lớn hơn điểm giữa; gần 1.3 |
| 1.2499 | 1 | 1.2 | Nhỏ hơn điểm giữa; gần 1.2 |
| -1.25 | 1 | -1.2 | Tie, chữ số 2 chẵn |
| -1.35 | 1 | -1.4 | Tie, chữ số 4 chẵn |
| 9.95 | 1 | 10.0 | Tie giữa 9.9 và 10.0; chữ số 0 chẵn |
| 8.235 | 2 | 8.24 | Tie giữa 8.23 và 8.24; 4 chẵn |
| 8.245 | 2 | 8.24 | Tie giữa 8.24 và 8.25; 4 chẵn |

Tạo `HalfEvenDecimalDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class HalfEvenDecimalDemo {
    static void show(String source) {
        BigDecimal number = new BigDecimal(source);
        System.out.println(source + " -> "
                + number.setScale(1, RoundingMode.HALF_EVEN).toPlainString());
    }

    public static void main(String[] args) {
        show("1.25");
        show("1.35");
        show("1.2500");
        show("1.2501");
        show("1.2499");
        show("-1.25");
        show("-1.35");
        show("9.95");
    }
}
~~~

~~~bash
javac HalfEvenDecimalDemo.java
java HalfEvenDecimalDemo
~~~

Đầu ra:

~~~text
1.25 -> 1.2
1.35 -> 1.4
1.2500 -> 1.2
1.2501 -> 1.3
1.2499 -> 1.2
-1.25 -> -1.2
-1.35 -> -1.4
9.95 -> 10.0
~~~

Với 9.95 → 10.0, hãy chú ý đến **chuyển nhớ**: việc tăng chữ số bên trái là hợp lệ. Khi giữ một chữ số lẻ, chữ số cuối của 10.0 là 0, thỏa mãn tiêu chí chẵn.

## 5. So sánh HALF_EVEN, HALF_UP và HALF_DOWN

Cả ba thuộc nhóm chọn số gần nhất khi không hòa. Khi chính xác hòa:

- **HALF_UP**: chọn phương án xa 0 hơn.
- **HALF_DOWN**: chọn phương án gần 0 hơn.
- **HALF_EVEN**: chọn phương án có chữ số cuối giữ lại chẵn.

| Giá trị → scale 0 | HALF_UP | HALF_DOWN | HALF_EVEN |
| --- | ---: | ---: | ---: |
| 2.5 | 3 | 2 | 2 |
| 3.5 | 4 | 3 | 4 |
| -2.5 | -3 | -2 | -2 |
| -3.5 | -4 | -3 | -4 |
| 2.6 | 3 | 3 | 3 |

Không nhầm **HALF_UP** với **UP**: `RoundingMode.UP` làm tròn ra xa 0 bất cứ khi nào bỏ phần có giá trị, kể cả không hòa. Tương tự, `RoundingMode.DOWN` làm tròn về 0 chứ không giống `HALF_DOWN`.

Tạo `HalfEvenModesDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class HalfEvenModesDemo {
    static void compare(String text) {
        BigDecimal x = new BigDecimal(text);
        String up = x.setScale(0, RoundingMode.HALF_UP).toPlainString();
        String down = x.setScale(0, RoundingMode.HALF_DOWN).toPlainString();
        String even = x.setScale(0, RoundingMode.HALF_EVEN).toPlainString();
        System.out.println(text + ": UP=" + up
                + ", DOWN=" + down + ", EVEN=" + even);
    }

    public static void main(String[] args) {
        compare("2.5");
        compare("3.5");
        compare("-2.5");
        compare("-3.5");
        compare("2.6");
    }
}
~~~

~~~bash
javac HalfEvenModesDemo.java
java HalfEvenModesDemo
~~~

Đầu ra:

~~~text
2.5: UP=3, DOWN=2, EVEN=2
3.5: UP=4, DOWN=3, EVEN=4
-2.5: UP=-3, DOWN=-2, EVEN=-2
-3.5: UP=-4, DOWN=-3, EVEN=-4
2.6: UP=3, DOWN=3, EVEN=3
~~~

Hai chế độ có thể cho kết quả trùng nhau trong một trường hợp riêng lẻ mà không có nghĩa tương đương. Hãy kiểm tra cả hai loại tie (chữ số cuối cũ chẵn/lẻ) và các giá trị không hòa.

## 6. HALF_EVEN cùng MathContext: phân biệt precision với scale

`setScale(2, HALF_EVEN)` giữ **hai chữ số sau dấu thập phân**. `MathContext(4, HALF_EVEN)` giữ tối đa **bốn chữ số có nghĩa** tính từ chữ số khác 0 đầu tiên. Đây là hai quy tắc giới hạn hoàn toàn khác nhau:

- 12.345 với scale 2 → 12.34.
- 12.345 với precision 4 → 12.34, tình cờ trùng vì chữ số có nghĩa thứ tư chính là hàng phần trăm.
- 123.45 với scale 2 → 123.45; với precision 4 → 123.4.
- 123.55 với precision 4 → 123.6: hai kết quả 123.5 và 123.6 cách đều 123.55, chữ số 6 chẵn.

`BigDecimal.round(MathContext)` làm tròn theo precision và rounding mode; các phép toán hỗ trợ `MathContext` cũng có thể làm tròn kết quả theo ngữ cảnh này. Precision 0 trong `MathContext.UNLIMITED` biểu thị không giới hạn số chữ số có nghĩa; quy tắc làm tròn không bị áp dụng chỉ vì precision. Nếu dùng `UNNECESSARY` mà thực sự cần loại bỏ chữ số có giá trị, Java ném `ArithmeticException`.

Tạo `HalfEvenPrecisionDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class HalfEvenPrecisionDemo {
    public static void main(String[] args) {
        BigDecimal first = new BigDecimal("12.345");
        BigDecimal second = new BigDecimal("12.355");
        BigDecimal large = new BigDecimal("123.45");
        MathContext mc = new MathContext(4, RoundingMode.HALF_EVEN);

        System.out.println("first scale 2  = "
                + first.setScale(2, RoundingMode.HALF_EVEN));
        System.out.println("second scale 2 = "
                + second.setScale(2, RoundingMode.HALF_EVEN));
        System.out.println("first prec 4   = " + first.round(mc));
        System.out.println("second prec 4  = " + second.round(mc));
        System.out.println("large prec 4   = " + large.round(mc));
    }
}
~~~

~~~bash
javac HalfEvenPrecisionDemo.java
java HalfEvenPrecisionDemo
~~~

Đầu ra:

~~~text
first scale 2  = 12.34
second scale 2 = 12.36
first prec 4   = 12.34
second prec 4  = 12.36
large prec 4   = 123.4
~~~

Chọn `setScale` khi có quy định số chữ số phần lẻ; chọn `MathContext` khi giới hạn số chữ số **có nghĩa** trong phép tính. Không đổi một API sang API còn lại chỉ vì đều hỗ trợ HALF_EVEN.

## 7. HALF_EVEN khi chia BigDecimal

Một số phép chia không thể biểu diễn thành số thập phân hữu hạn (ví dụ 1/3). `BigDecimal.divide(divisor)` có thể ném `ArithmeticException` khi không có kết quả thập phân hữu hạn chính xác. Có thể chỉ định scale và chế độ làm tròn trong overload `divide(divisor, scale, roundingMode)`.

Ví dụ: 1/8 = 0.125 nằm chính giữa 0.12 và 0.13 → 0.12 (2 chẵn). 3/8 = 0.375 nằm chính giữa 0.37 và 0.38 → 0.38 (8 chẵn).

Tạo `HalfEvenDivisionDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class HalfEvenDivisionDemo {
    public static void main(String[] args) {
        BigDecimal eight = new BigDecimal("8");
        BigDecimal first = BigDecimal.ONE.divide(
                eight, 2, RoundingMode.HALF_EVEN);
        BigDecimal second = new BigDecimal("3").divide(
                eight, 2, RoundingMode.HALF_EVEN);
        BigDecimal third = BigDecimal.ONE.divide(
                new BigDecimal("3"), 2, RoundingMode.HALF_EVEN);

        System.out.println("1 / 8 = " + first);
        System.out.println("3 / 8 = " + second);
        System.out.println("1 / 3 = " + third);
    }
}
~~~

~~~bash
javac HalfEvenDivisionDemo.java
java HalfEvenDivisionDemo
~~~

Đầu ra:

~~~text
1 / 8 = 0.12
3 / 8 = 0.38
1 / 3 = 0.33
~~~

1/3 được làm tròn về 0.33 vì gần 0.33 hơn 0.34, không phụ thuộc tính chẵn. Để biết cần giữ bao nhiêu chữ số và khi nào làm tròn, phải dựa vào yêu cầu đầu ra/nhất quán của nghiệp vụ.

## 8. Vì sao còn gọi là banker's rounding?

Nếu dữ liệu có rất nhiều giá trị dương rơi đúng điểm giữa, làm tròn luôn xa 0 theo HALF_UP có thể tạo xu hướng tăng tổng. HALF_EVEN chọn hướng lên hoặc xuống theo tính chẵn của chữ số cuối được giữ. Với phân bố các tie cân bằng, cách này **có thể làm giảm thiên lệch tích lũy**.

Ví dụ, xét bốn giá trị cần làm tròn thành số nguyên:

| Cách tính | Các giá trị | Tổng |
| --- | --- | ---: |
| Chưa làm tròn | 1.5, 2.5, 3.5, 4.5 | 12 |
| HALF_UP | 2, 3, 4, 5 | 14 |
| HALF_EVEN | 2, 2, 4, 4 | 12 |

Đây là minh họa, **không phải chứng minh HALF_EVEN luôn giữ nguyên tổng hoặc hoàn toàn không thiên lệch**. Kết quả tùy dữ liệu, đặc biệt khi tie tập trung về một nhóm chữ số. Tên gọi "banker's rounding" cũng không có nghĩa tất cả ngân hàng, chuẩn kế toán hay thuế đều bắt buộc dùng HALF_EVEN; phải theo quy định nghiệp vụ thực tế.

### Làm tròn từng khoản khác làm tròn tổng

Nếu có ba khoản 1.005 và cần số tiền hai chữ số lẻ:

- Làm tròn từng khoản HALF_EVEN: mỗi khoản 1.00; tổng bằng **3.00**.
- Cộng giá trị nguyên gốc rồi làm tròn một lần: 3.015 → **3.02**.

Tạo `HalfEvenTotalsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class HalfEvenTotalsDemo {
    public static void main(String[] args) {
        BigDecimal[] items = {
            new BigDecimal("1.005"),
            new BigDecimal("1.005"),
            new BigDecimal("1.005")
        };

        BigDecimal rawTotal = BigDecimal.ZERO;
        BigDecimal roundedEachTotal = BigDecimal.ZERO;

        for (BigDecimal item : items) {
            rawTotal = rawTotal.add(item);
            roundedEachTotal = roundedEachTotal.add(
                    item.setScale(2, RoundingMode.HALF_EVEN));
        }

        BigDecimal roundedAtEnd =
                rawTotal.setScale(2, RoundingMode.HALF_EVEN);

        System.out.println("raw total        = " + rawTotal);
        System.out.println("round each, sum  = " + roundedEachTotal);
        System.out.println("sum, round once  = " + roundedAtEnd);
    }
}
~~~

~~~bash
javac HalfEvenTotalsDemo.java
java HalfEvenTotalsDemo
~~~

Đầu ra:

~~~text
raw total        = 3.015
round each, sum  = 3.00
sum, round once  = 3.02
~~~

Cả hai phép làm tròn đều tuân thủ HALF_EVEN. Việc chọn **thời điểm làm tròn** (theo dòng, theo giao dịch hay theo tổng) ảnh hưởng kết quả và phải xác định rõ từ quy tắc nghiệp vụ. Hạn chế các lần làm tròn trung gian nếu không bắt buộc, để không mất độ chính xác cần cho phép tính sau.

## 9. Tránh tạo BigDecimal bằng double nếu cần tie thập phân chính xác

Nhiều số thập phân không biểu diễn chính xác trong hệ nhị phân của kiểu `double`. Vì vậy, `new BigDecimal(2.675)` tạo BigDecimal biểu diễn chính xác **giá trị double nhị phân đã nhận**, vốn hơi nhỏ hơn 2.675. Khi làm tròn về hai chữ số, số này gần 2.67 hơn; HALF_EVEN không chọn theo tie vì trên thực tế không có tie.

Ngược lại, `new BigDecimal("2.675")` giữ chính xác 2.675: nó ở chính giữa 2.67 và 2.68, nên HALF_EVEN chọn 2.68. `BigDecimal.valueOf(2.675)` dùng biểu diễn thập phân chuẩn của double nên cũng cho 2.68 trong ví dụ, nhưng cách đó không phục hồi được mọi độ chính xác đã mất từ dữ liệu trước đó.

Tạo `HalfEvenInputDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class HalfEvenInputDemo {
    public static void main(String[] args) {
        BigDecimal exact = new BigDecimal("2.675");
        BigDecimal fromDouble = new BigDecimal(2.675);
        BigDecimal viaValueOf = BigDecimal.valueOf(2.675);

        System.out.println("String  = "
                + exact.setScale(2, RoundingMode.HALF_EVEN));
        System.out.println("double  = "
                + fromDouble.setScale(2, RoundingMode.HALF_EVEN));
        System.out.println("valueOf = "
                + viaValueOf.setScale(2, RoundingMode.HALF_EVEN));
    }
}
~~~

~~~bash
javac HalfEvenInputDemo.java
java HalfEvenInputDemo
~~~

Đầu ra:

~~~text
String  = 2.68
double  = 2.67
valueOf = 2.68
~~~

Khi cần kiểm soát chữ số thập phân (đặc biệt các khoản tiền), hãy ưu tiên dữ liệu BigDecimal tạo từ chuỗi thập phân chính xác hoặc nguồn số nguyên được quy đổi rõ ràng, tránh đưa sai số nhị phân vào tie.

## 10. Những lỗi phổ biến

1. **Xem chữ số đầu tiên bị bỏ là 5 thì chắc chắn hòa.** Ví dụ 1.2501 có các chữ số khác 0 sau 5 nên phải chọn số gần hơn, tức 1.3 tại scale 1.
2. **Xét số chẵn trước khi xác định khoảng cách.** 2.51 → 3, dù 3 lẻ; lý do là gần nhất.
3. **Xét chẵn/lẻ của phần nguyên bất kể scale.** 1.25 → 1.2 tại scale 1 vì chữ số hàng phần mười là 2, không phải vì phần nguyên 1.
4. **Tưởng HALF_EVEN luôn làm tròn xuống.** 3.5 → 4, 1.35 → 1.4 và 9.95 → 10.0.
5. **Tưởng số âm luôn làm tròn về 0.** -3.5 → -4, còn -2.5 → -2.
6. **Nhầm HALF_UP với UP, HALF_DOWN với DOWN.** Hai chế độ không có HALF không yêu cầu tie mới làm tròn theo hướng.
7. **Nhầm precision với scale.** MathContext precision đếm chữ số có nghĩa; setScale quy định chữ số phần thập phân.
8. **Dùng `new BigDecimal(double)` cho hằng số decimal.** Giá trị nhị phân có thể khác rất nhỏ nhưng đủ làm kết quả ở ranh giới thay đổi.
9. **Làm tròn ở nhiều bước mà không có chính sách.** Tổng sau làm tròn từng khoản có thể khác làm tròn tổng một lần.
10. **Quên lưu giá trị trả về.** BigDecimal là immutable: `value.setScale(...)` không cập nhật `value`; dùng biến mới hoặc phép gán phù hợp.
11. **Dùng HALF_EVEN cho mọi số tiền theo quán tính.** Cần kiểm tra yêu cầu loại giao dịch, chuẩn báo cáo và quy định hiện hành của hệ thống.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Làm tròn `4.5` và `5.5` về scale 0 theo HALF_EVEN. Vì sao kết quả khác chiều?

**Đáp án:** 4 và 6. Cả hai là tie, nhưng hai cặp lân cận lần lượt là (4, 5) và (5, 6); chọn chữ số chẵn.

**Câu 2.** Làm tròn `8.235` và `8.245` về scale 2 theo HALF_EVEN.

**Đáp án:** Cả hai đều là 8.24: giá trị thứ nhất ở giữa 8.23 và 8.24, giá trị thứ hai ở giữa 8.24 và 8.25; chữ số cuối 4 là chẵn.

**Câu 3.** Vì sao `1.2500` → `1.2` còn `1.2501` → `1.3` ở scale 1?

**Đáp án:** 1.2500 bằng đúng 1.25 nên là tie; 1.2501 gần 1.3 hơn nên quy tắc gần nhất quyết định.

**Câu 4.** Với `new BigDecimal("12.345")`, `setScale(2, HALF_EVEN)` khác `round(new MathContext(2, HALF_EVEN))` ra sao?

**Đáp án:** Kết quả lần lượt là 12.34 và 12; cách thứ nhất giữ hai chữ số lẻ, cách thứ hai giữ hai chữ số có nghĩa.

**Câu 5.** HALF_EVEN có bảo đảm tổng đã làm tròn từng dòng bằng tổng gốc được làm tròn một lần?

**Đáp án:** Không. Ba giá trị 1.005 minh họa kết quả có thể là 3.00 hoặc 3.02 tùy thời điểm áp dụng quy tắc.

## 12. Ghi nhớ

- **HALF_EVEN chọn kết quả gần nhất; nếu hòa, chọn chữ số cuối được giữ lại là chẵn.**
- Chẵn/lẻ **chỉ giải quyết tie**, không thay thế quy tắc khoảng cách.
- Dùng `setScale(scale, RoundingMode.HALF_EVEN)` để kiểm soát chữ số sau dấu thập phân; dùng `MathContext` để kiểm soát chữ số có nghĩa.
- Nhận dữ liệu thập phân chính xác và chọn thời điểm làm tròn theo yêu cầu nghiệp vụ.
- HALF_EVEN có thể giảm xu hướng sai lệch khi xử lý nhiều tie cân bằng, nhưng không bảo đảm mọi kết quả tổng đều giống dữ liệu chưa làm tròn.

Tài liệu API chính thức: Java SE 17 `java.math.RoundingMode`, `java.math.BigDecimal` và `java.math.MathContext`.