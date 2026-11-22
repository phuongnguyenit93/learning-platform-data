# Ý nghĩa của HALF_UP, HALF_DOWN và HALF_EVEN

## 1. Ba chế độ cùng chọn giá trị gần nhất

Khi giảm số chữ số của một số thập phân, ta phải chọn một giá trị nằm trên lưới kết quả cho phép. Nếu giữ hai chữ số sau dấu chấm, các kết quả liền nhau cách nhau 0.01: chẳng hạn 6.24 và 6.25. Nếu làm tròn về số nguyên, khoảng cách đó là 1.

`HALF_UP`, `HALF_DOWN` và `HALF_EVEN` đều ưu tiên kết quả gần giá trị ban đầu nhất. Chúng chỉ khác nhau khi giá trị ban đầu nằm chính giữa hai kết quả có thể chọn.

Ví dụ làm tròn về số nguyên:

- 6.2 gần 6 hơn 7: cả ba chế độ cho 6.
- 6.8 gần 7 hơn 6: cả ba chế độ cho 7.
- 6.5 cách 6 và 7 như nhau: cần một quy tắc phá hòa.

| Chế độ | Quy tắc khi nằm chính giữa |
| --- | --- |
| `HALF_UP` | Chọn phía xa 0 hơn |
| `HALF_DOWN` | Chọn phía gần 0 hơn |
| `HALF_EVEN` | Chọn kết quả có chữ số cuối được giữ lại là số chẵn |

Những định nghĩa này áp dụng cho cả số dương và số âm. Tên UP/DOWN ở đây nói về độ lớn so với 0 khi phá hòa; không nên hiểu chúng đơn giản là tăng/giảm giá trị trên trục số. Xem định nghĩa chính thức tại [RoundingMode API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/RoundingMode.html).

Trong Java hiện đại, dùng enum `java.math.RoundingMode` với `BigDecimal`. Các hằng kiểu `int` cũ như `BigDecimal.ROUND_HALF_UP` đã deprecated và không nên dùng trong mã mới.

## 2. HALF_UP: điểm giữa đi xa 0

Với số dương, hành vi thường trùng với quy tắc “từ 5 trở lên thì tăng” đã học ở trường. Nhưng cách diễn đạt chính xác hơn là: chọn gần nhất, nếu hòa thì chọn phía xa 0.

```text
 6.5 →  7
-6.5 → -7
```

`-6.5` thành `-7` dù `-7` nhỏ hơn trên trục số. Vì vậy `HALF_UP` không phải làm tròn về dương vô cùng.

Giữ hai chữ số sau dấu chấm:

```text
 6.245 →  6.25
-6.245 → -6.25
```

Trong cả hai trường hợp, độ lớn tăng thêm 0.005 tại điểm giữa. Nếu không ở điểm giữa, quy tắc gần nhất vẫn chi phối: `6.241` thành `6.24`, không phải `6.25`.

## 3. HALF_DOWN: điểm giữa đi về 0

`HALF_DOWN` chỉ chọn phía gần 0 khi hai kết quả cách đều nhau:

```text
 6.5 →  6
-6.5 → -6
```

Với hai chữ số sau dấu chấm:

```text
 6.245 →  6.24
-6.245 → -6.24
```

Chế độ này không phải luôn cắt bỏ phần dư. Ví dụ `6.2451` nằm gần `6.25` hơn `6.24`, nên `HALF_DOWN` vẫn cho `6.25`. Tương tự, `-6.2451` cho `-6.25`.

Đây là điểm dễ nhầm giữa `HALF_DOWN` và `DOWN`: `DOWN` hướng về 0 bất cứ khi nào cần bỏ phần khác 0; `HALF_DOWN` chỉ dùng hướng đó để phá hòa.

## 4. HALF_EVEN: chẵn ở vị trí cuối được giữ

Với `HALF_EVEN`, nếu đúng điểm giữa, hãy nhìn chữ số cuối của kết quả được giữ lại.

Giữ hai chữ số sau dấu chấm:

```text
6.245 → giữa 6.24 và 6.25 → chọn 6.24 vì 4 chẵn
6.255 → giữa 6.25 và 6.26 → chọn 6.26 vì 6 chẵn
```

Không phải kiểm tra xem toàn bộ số có phải số nguyên chẵn hay không. Với `6.24`, ta đang kiểm tra chữ số 4 ở hàng phần trăm.

Làm tròn về số nguyên là trường hợp đặc biệt: chữ số cuối được giữ nằm ở hàng đơn vị, nên có thể nói kết quả là số nguyên chẵn:

```text
6.5 → 6
7.5 → 8
```

Quy tắc tương tự cho số âm:

```text
-6.5 → -6
-7.5 → -8
```

`HALF_EVEN` có thể đi về 0 hoặc xa 0 tùy chữ số được giữ; không phải luân phiên theo số lần gọi. Hàm không ghi nhớ lần trước đã chọn hướng nào.

### “Có chữ số 5” chưa chắc là điểm giữa

Với mục tiêu hai chữ số sau dấu chấm:

| Đầu vào | Quan hệ với điểm giữa 6.245 | Kết quả của cả ba chế độ khi không hòa |
| --- | --- | --- |
| 6.2449 | Nhỏ hơn điểm giữa | 6.24 |
| 6.2450 | Đúng điểm giữa | Phụ thuộc chế độ |
| 6.2451 | Lớn hơn điểm giữa | 6.25 |

Cần xét toàn bộ phần bị bỏ. Chữ số đầu bị bỏ bằng 5 và mọi chữ số phía sau đều bằng 0 mới là trường hợp hòa. Đuôi `5000` và `5001` có ý nghĩa khác nhau.

## 5. Đọc bảng có cả số âm

Bảng sau làm tròn về số nguyên, tức `setScale(0, mode)`:

| Đầu vào | HALF_UP | HALF_DOWN | HALF_EVEN |
| --- | ---: | ---: | ---: |
| 6.4 | 6 | 6 | 6 |
| 6.5 | 7 | 6 | 6 |
| 6.6 | 7 | 7 | 7 |
| 7.5 | 8 | 7 | 8 |
| -6.4 | -6 | -6 | -6 |
| -6.5 | -7 | -6 | -6 |
| -6.6 | -7 | -7 | -7 |
| -7.5 | -8 | -7 | -8 |
| 0.5 | 1 | 0 | 0 |
| -0.5 | -1 | 0 | 0 |

`BigDecimal` không có giá trị âm 0 riêng biệt. Trong ví dụ cuối, kết quả của `HALF_DOWN` và `HALF_EVEN` được in là `0`.

Một cách tự kiểm tra dấu: với cùng scale và cùng một trong ba chế độ này, làm tròn số đối phải cho kết quả đối của kết quả ban đầu về mặt giá trị số. Nếu dự đoán `6.5 → 7` nhưng `-6.5 → -6` dưới `HALF_UP`, đó là dấu hiệu đang nhầm với hướng dương vô cùng.

## 6. Áp dụng bằng setScale và MathContext

### Yêu cầu số chữ số sau dấu chấm

```java
BigDecimal input = new BigDecimal("6.245");
BigDecimal rounded = input.setScale(2, RoundingMode.HALF_EVEN);
```

Đây là đoạn mã trong một phương thức, cần import `BigDecimal` và `RoundingMode`. `rounded` là `6.24`, còn `input` vẫn là `6.245`, vì `BigDecimal` bất biến.

`setScale(2, mode)` yêu cầu scale bằng 2. Giảm scale có thể làm mất thông tin; tăng scale như `new BigDecimal("6.2").setScale(2, mode)` chỉ thêm số 0, cho `6.20`, không có điểm giữa để phân xử.

### Yêu cầu tổng số chữ số có nghĩa

Có thể dùng cùng các chế độ với `MathContext`:

```java
BigDecimal input = new BigDecimal("2575");
BigDecimal rounded = input.round(new MathContext(3, RoundingMode.HALF_EVEN));
```

Đoạn này cần thêm import `java.math.MathContext`. Kết quả có giá trị `2580`: khi chỉ giữ ba chữ số có nghĩa, hai ứng viên là 2570 và 2580, chữ số cuối được giữ ở hàng chục là 7 hoặc 8. `HALF_EVEN` chọn 8.

Trong cùng ví dụ, `HALF_UP` cho 2580 và `HALF_DOWN` cho 2570. Không được nhìn chữ số 0 cuối chuỗi `2570` để kết luận ứng viên đã chẵn: số 0 đó nằm ngoài ba chữ số có nghĩa được giữ.

Với phép chia, có thể chỉ định cả scale lẫn chế độ, ví dụ `new BigDecimal("25").divide(new BigDecimal("8"), 2, RoundingMode.HALF_EVEN)` cho `3.12`: thương chính xác là `3.125`, điểm giữa của 3.12 và 3.13.

Việc chọn vị trí cần giữ và chọn cách phá hòa là hai quyết định riêng. Cùng một chế độ làm tròn nhưng scale hoặc precision khác nhau sẽ tạo ra lưới kết quả khác nhau.

## 7. Vì sao HALF_EVEN thường được cân nhắc cho nhiều phép tính?

Hãy xét hai đầu vào 6.5 và 7.5, làm tròn riêng từng số về số nguyên:

```text
Tổng chính xác:     6.5 + 7.5 = 14
HALF_UP:           7 + 8 = 15
HALF_DOWN:         6 + 7 = 13
HALF_EVEN:         6 + 8 = 14
```

Ở cặp dữ liệu này, `HALF_UP` đẩy cả hai số dương lên; `HALF_DOWN` kéo cả hai về 0. `HALF_EVEN` có một lần chọn mỗi hướng nên tổng sai số bằng 0.

Đây là một ví dụ về lý do chọn chẵn có thể hạn chế thiên lệch do nhiều điểm giữa cùng bị đẩy một hướng. Nó không bảo đảm tổng sai số bằng 0 trên mọi tập dữ liệu. Nếu các điểm giữa đều có chữ số giữ lại chẵn, chẳng hạn 6.5 và 8.5, `HALF_EVEN` đều chọn phía dưới và tổng bị giảm.

Do đó, không nên diễn giải “làm tròn về chẵn” thành “không có sai số” hoặc “luôn đúng hơn”. Mọi chế độ đều tuân theo chính sách riêng; tính phù hợp còn phụ thuộc dữ liệu và yêu cầu cụ thể.

Khi một đặc tả đã yêu cầu `HALF_UP`, dùng `HALF_EVEN` chỉ vì nghe có vẻ chính xác hơn sẽ làm kết quả sai đặc tả. Hãy xác định rõ:

- Cần giữ bao nhiêu chữ số, theo scale hay precision?
- Làm tròn tại từng bản ghi hay sau khi cộng tổng?
- Phá hòa theo quy tắc nào?
- Dữ liệu đầu vào đã được làm tròn ở hệ thống khác chưa?

Đây là các điều kiện kỹ thuật để tái lập phép tính. Tên gọi quen thuộc của một chế độ không thay thế được hợp đồng dữ liệu.

## 8. Chương trình hoàn chỉnh: bảng số, vị trí làm tròn và đầu vào

Lưu thành `HalfRoundingDemo.java`. Mã tương thích Java 17+ và không phụ thuộc thư viện ngoài JDK.

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class HalfRoundingDemo {
    private static BigDecimal decimal(String value) {
        return new BigDecimal(value);
    }

    private static void row(String value, int scale) {
        BigDecimal input = decimal(value);
        System.out.println(value + " | "
                + input.setScale(scale, RoundingMode.HALF_UP).toPlainString() + " | "
                + input.setScale(scale, RoundingMode.HALF_DOWN).toPlainString() + " | "
                + input.setScale(scale, RoundingMode.HALF_EVEN).toPlainString());
    }

    private static void show(String name, BigDecimal value) {
        System.out.println(name + "=" + value.toPlainString());
    }

    public static void main(String[] args) {
        System.out.println("input | HALF_UP | HALF_DOWN | HALF_EVEN");
        for (String value : new String[] {
                "6.4", "6.5", "6.6", "7.5",
                "-6.4", "-6.5", "-6.6", "-7.5", "0.5", "-0.5"
        }) {
            row(value, 0);
        }

        System.out.println("scale=2");
        for (String value : new String[] {
                "6.245", "6.255", "-6.245", "-6.255", "6.2450", "6.2451"
        }) {
            row(value, 2);
        }

        BigDecimal x = decimal("2575");
        for (RoundingMode mode : new RoundingMode[] {
                RoundingMode.HALF_UP,
                RoundingMode.HALF_DOWN,
                RoundingMode.HALF_EVEN
        }) {
            show("precision3." + mode, x.round(new MathContext(3, mode)));
        }

        BigDecimal source = decimal("2.4501");
        show("directScale1", source.setScale(1, RoundingMode.HALF_EVEN));
        show("viaScale2", source.setScale(2, RoundingMode.HALF_EVEN)
                .setScale(1, RoundingMode.HALF_EVEN));

        BigDecimal item = decimal("0.335");
        BigDecimal three = decimal("3");
        show("roundEach", item.setScale(2, RoundingMode.HALF_EVEN).multiply(three));
        show("roundTotal", item.multiply(three).setScale(2, RoundingMode.HALF_EVEN));

        show("fromString", decimal("2.675").setScale(2, RoundingMode.HALF_UP));
        show("fromDouble", new BigDecimal(2.675).setScale(2, RoundingMode.HALF_UP));
        show("fromValueOf", BigDecimal.valueOf(2.675).setScale(2, RoundingMode.HALF_UP));

        BigDecimal unchanged = decimal("6.245");
        unchanged.setScale(2, RoundingMode.HALF_UP);
        show("original", unchanged);
    }
}
```

Chạy:

```shell
javac --release 17 HalfRoundingDemo.java
java HalfRoundingDemo
```

Stdout:

```text
input | HALF_UP | HALF_DOWN | HALF_EVEN
6.4 | 6 | 6 | 6
6.5 | 7 | 6 | 6
6.6 | 7 | 7 | 7
7.5 | 8 | 7 | 8
-6.4 | -6 | -6 | -6
-6.5 | -7 | -6 | -6
-6.6 | -7 | -7 | -7
-7.5 | -8 | -7 | -8
0.5 | 1 | 0 | 0
-0.5 | -1 | 0 | 0
scale=2
6.245 | 6.25 | 6.24 | 6.24
6.255 | 6.26 | 6.25 | 6.26
-6.245 | -6.25 | -6.24 | -6.24
-6.255 | -6.26 | -6.25 | -6.26
6.2450 | 6.25 | 6.24 | 6.24
6.2451 | 6.25 | 6.25 | 6.25
precision3.HALF_UP=2580
precision3.HALF_DOWN=2570
precision3.HALF_EVEN=2580
directScale1=2.5
viaScale2=2.4
roundEach=1.02
roundTotal=1.00
fromString=2.68
fromDouble=2.67
fromValueOf=2.68
original=6.245
```

### Giải thích các kết quả dễ gây bất ngờ

**Làm tròn hai lần:** `2.4501` gần 2.5 hơn 2.4, nên làm tròn trực tiếp đến scale 1 cho 2.5. Qua scale 2 trước, số trở thành 2.45, đúng điểm giữa; bước tiếp theo dưới `HALF_EVEN` chọn 2.4. Bước đầu đã làm mất thông tin rằng giá trị ban đầu lớn hơn điểm giữa.

**Làm tròn từng phần và làm tròn tổng:** mỗi 0.335 được làm tròn thành 0.34, nhân 3 thành 1.02. Nhưng tổng chính xác là 1.005; làm tròn tổng về hai chữ số theo `HALF_EVEN` cho 1.00. Không thể chọn vị trí làm tròn tùy tiện rồi mong kết quả luôn giống nhau.

**Đầu vào double:** `new BigDecimal(2.675)` nhận đúng giá trị nhị phân đang có của `double`, vốn hơi nhỏ hơn số thập phân 2.675. Vì vậy kết quả 2.67 không phải lỗi của `HALF_UP`. Constructor chuỗi nhận chính xác 2.675 và cho 2.68. `valueOf(2.675)` dùng dạng chuỗi của `double` nên trong ví dụ này cũng cho 2.68; phương thức đó không có khả năng sửa mọi sai số đã phát sinh trong phép tính `double` trước đó.

**Bất biến:** không gán kết quả `setScale` thì biến `unchanged` vẫn giữ giá trị gốc. Quy tắc làm tròn đúng nhưng bỏ mất giá trị trả về vẫn tạo ra lỗi chương trình.

Thông tin về constructor, scale và các overload có tại [BigDecimal API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html).

## 9. Ranh giới phạm vi và lỗi cần tránh

- **Không nhầm HALF_UP với UP:** làm tròn 6.21 đến một chữ số sau dấu chấm, `HALF_UP` cho 6.2, còn `UP` cho 6.3.
- **Không nhầm HALF_DOWN với FLOOR:** làm tròn -6.5 về số nguyên, `HALF_DOWN` cho -6, còn `FLOOR` cho -7.
- **Không xét riêng chữ số đầu bị bỏ:** đuôi 5001 lớn hơn điểm giữa; `HALF_DOWN` không được kéo nó về 0.
- **Không nhìn nhầm chữ số chẵn:** với scale 2 xét hàng phần trăm; với precision 3 ở số 2575 xét hàng chục.
- **Không đổi chế độ để chữa đầu vào sai:** trước tiên kiểm tra số đã được tạo từ chuỗi chính xác hay từ một `double`.
- **Không làm tròn sớm chỉ để chuỗi trông ngắn:** chọn thời điểm làm tròn theo ý nghĩa tính toán; giữ giá trị gốc nếu những bước sau còn cần nó.
- **Không coi HALF_EVEN là bảo đảm tổng đúng:** vẫn cần kiểm tra sai số và trường hợp biên.
- **Không dùng chế độ làm tròn để xử lý chia cho 0:** lỗi đó vẫn gây `ArithmeticException`, không có kết quả hữu hạn để lựa chọn.

Khi viết kiểm thử, hãy bao phủ ít nhất: nhỏ hơn điểm giữa, đúng điểm giữa, lớn hơn điểm giữa, chữ số giữ lại chẵn/lẻ, số dương/âm và tình huống phát sinh nhớ sang hàng trước. Kiểm tra cả việc làm tròn tại nhiều bước nếu chương trình thực hiện như vậy.

Nếu chỉ quan tâm giá trị số, dùng `compareTo(expected) == 0`; nếu scale là một phần của yêu cầu đầu ra, hãy kiểm tra scale hoặc chuỗi mong muốn thêm. `BigDecimal.equals` xét cả giá trị và scale, nên 1.0 và 1.00 không bằng nhau theo `equals`.

## 10. Thực hành

1. Dự đoán kết quả của `8.345`, `8.355`, `-8.345` và `-8.355` khi giữ hai chữ số sau dấu chấm theo cả ba chế độ.
2. Vì sao `8.34501` và `8.34500` có thể cho kết quả khác nhau dưới `HALF_DOWN`? Hãy nói rõ hai ứng viên và khoảng cách.
3. Với `9.995` và scale 2, kết quả của mỗi chế độ là gì? Giải thích việc nhớ sang phần nguyên.
4. Viết một hàm nhận chuỗi thập phân, scale và `RoundingMode`, trả về chuỗi kết quả bằng `toPlainString()`; không chuyển qua `double`.
5. Thử tổng của 6.5 và 8.5 sau khi làm tròn từng số theo `HALF_EVEN`. So sánh với tổng chính xác để kiểm tra nhận định “luôn triệt tiêu sai số”.
6. Tạo một tình huống mà làm tròn trực tiếp khác làm tròn qua một scale trung gian. Giải thích số nào bị biến thành điểm giữa bởi bước đầu.

Gợi ý câu 3: `HALF_UP` cho `10.00`, `HALF_DOWN` cho `9.99`, `HALF_EVEN` cho `10.00`. Câu 5 cho tổng 14 thay vì 15. Kết quả giúp kiểm tra dự đoán; phần giải thích cần chỉ rõ quy tắc phá hòa và vị trí chữ số được giữ.
