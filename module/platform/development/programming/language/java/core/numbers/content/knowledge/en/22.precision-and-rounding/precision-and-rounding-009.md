# Đối chiếu các chế độ làm tròn với số dương và số âm trong Java

## 1. Mục tiêu và tình huống

Khi làm tròn số trong Java, lựa chọn chế độ làm tròn (`RoundingMode`) phải dựa trên **hướng làm tròn và quy tắc xử lý trường hợp nằm đúng giữa hai giá trị**, đặc biệt khi đầu vào có thể âm. Tên gọi như `UP`, `DOWN`, `CEILING` và `FLOOR` rất dễ bị hiểu sai nếu chỉ thử với số dương.

Sau bài này, bạn có thể:

- Giải thích chính xác tám giá trị của `java.math.RoundingMode`.
- Dự đoán kết quả làm tròn số **dương và âm**, tại điểm giữa (tie) lẫn không phải điểm giữa.
- Phân biệt `UP/DOWN` với `CEILING/FLOOR`, và ba quy tắc `HALF_UP`, `HALF_DOWN`, `HALF_EVEN`.
- Dùng `BigDecimal.setScale(...)`, `divide(...)` và `MathContext` đúng mục đích; phát hiện lúc nào làm tròn sẽ gây mất thông tin.
- Chọn chính sách làm tròn nhất quán cho tiền tệ, số đo, báo cáo và các phép tính theo yêu cầu nghiệp vụ.

Điều kiện quan trọng: **rounding chỉ xảy ra khi phải bỏ phần có nghĩa**. Nếu kết quả đã biểu diễn chính xác ở scale/precision được yêu cầu, mọi chế độ đều cho cùng giá trị; `UNNECESSARY` cũng hợp lệ.

## 2. Hai cách nhìn về hướng làm tròn

Xét việc làm tròn về số nguyên (`scale = 0`):

- **Tiến ra xa 0** (`UP`): `2.1 → 3` và `-2.1 → -3`. Độ lớn tuyệt đối tăng nếu có phần lẻ.
- **Tiến về 0** (`DOWN`): `2.9 → 2` và `-2.9 → -2`. Đây là phép *truncate* ở vị trí làm tròn.
- **Tiến về +∞** (`CEILING`): `2.1 → 3` nhưng `-2.1 → -2`. Số âm ít âm hơn là số **lớn hơn**.
- **Tiến về −∞** (`FLOOR`): `2.9 → 2` nhưng `-2.1 → -3`. Số âm âm hơn là số **nhỏ hơn**.

Do đó `UP` **không đồng nghĩa** với `CEILING`; `DOWN` **không đồng nghĩa** với `FLOOR`. Chúng trùng nhau ở một số đầu vào, nhưng khác nhau khi đảo dấu.

Với các chế độ bắt đầu bằng `HALF_`, Java ưu tiên kết quả **gần số gốc nhất**. Nếu một trong hai ứng viên gần hơn, cả `HALF_UP`, `HALF_DOWN` và `HALF_EVEN` đều chọn ứng viên đó. Sự khác biệt chỉ xuất hiện tại **điểm giữa chính xác**, chẳng hạn `2.5` nằm giữa `2` và `3` khi làm tròn đến số nguyên.

Hãy nhớ đơn vị vị trí làm tròn:

- `setScale(0, mode)`: làm tròn đến **hàng đơn vị**.
- `setScale(2, mode)`: làm tròn đến **2 chữ số sau dấu thập phân**, đơn vị bước là `0.01`.
- `setScale(-1, mode)`: làm tròn đến **hàng chục**, đơn vị bước là `10`. Scale âm hợp lệ.
- `new MathContext(4, mode)`: giới hạn **4 chữ số có nghĩa**, không phải 4 chữ số sau dấu thập phân.

## 3. Bảng đối chiếu đủ tám chế độ với số dương và âm

Bảng dưới đây xét `new BigDecimal(input).setScale(0, mode)`. Các đầu vào `±2.5` là **điểm giữa**; `±2.4` **không** phải điểm giữa.

| `RoundingMode` | `+2.5` | `-2.5` | `+2.4` | `-2.4` | Quy tắc |
| --- | ---: | ---: | ---: | ---: | --- |
| `UP` | `3` | `-3` | `3` | `-3` | Xa 0, hễ có chữ số phải bỏ |
| `DOWN` | `2` | `-2` | `2` | `-2` | Về 0, bỏ phần lẻ |
| `CEILING` | `3` | `-2` | `3` | `-2` | Về +∞ |
| `FLOOR` | `2` | `-3` | `2` | `-3` | Về −∞ |
| `HALF_UP` | `3` | `-3` | `2` | `-2` | Gần nhất; điểm giữa thì xa 0 |
| `HALF_DOWN` | `2` | `-2` | `2` | `-2` | Gần nhất; điểm giữa thì về 0 |
| `HALF_EVEN` | `2` | `-2` | `2` | `-2` | Gần nhất; điểm giữa thì chữ số giữ lại là chẵn |
| `UNNECESSARY` | lỗi | lỗi | lỗi | lỗi | Cấm làm tròn mất giá trị |

Trong bảng, “lỗi” nghĩa là `ArithmeticException` vì yêu cầu bỏ phần lẻ không bằng 0 nhưng chế độ `UNNECESSARY` cấm việc đó.

Cách đọc nhanh hai hàng dễ nhầm:

- `CEILING(-2.4) = -2` vì `-2` lớn hơn `-2.4`; `FLOOR(-2.4) = -3` vì `-3` nhỏ hơn `-2.4`.
- `UP(-2.4) = -3` vì `-3` xa 0 hơn; `DOWN(-2.4) = -2` vì `-2` gần 0 hơn.

Các chế độ `HALF_` cho cùng kết quả với `±2.4` vì các giá trị này gần `±2` hơn `±3`.

### Bảng bổ sung để phân biệt ba chế độ `HALF_`

Với `setScale(0, mode)`:

| Đầu vào | `HALF_UP` | `HALF_DOWN` | `HALF_EVEN` |
| --- | ---: | ---: | ---: |
| `2.5` | `3` | `2` | `2` |
| `-2.5` | `-3` | `-2` | `-2` |
| `3.5` | `4` | `3` | `4` |
| `-3.5` | `-4` | `-3` | `-4` |
| `4.5` | `5` | `4` | `4` |
| `-4.5` | `-5` | `-4` | `-4` |

`HALF_EVEN` chọn **ứng viên có chữ số cuối được giữ lại là chẵn** tại điểm giữa: `2.5 → 2` nhưng `3.5 → 4`; `-2.5 → -2` nhưng `-3.5 → -4`. “Even” xét **chữ số tại vị trí làm tròn**, không xét dấu của số gốc. Đây còn được gọi là *banker's rounding* và có thể giảm thiên lệch do liên tiếp gặp điểm giữa trong một số tập dữ liệu; điều đó không có nghĩa nó luôn phù hợp với mọi nghiệp vụ.

## 4. Từng chế độ hoạt động ra sao?

### `UP` — xa số 0

Khi kết quả không biểu diễn chính xác ở vị trí yêu cầu, `UP` làm tăng **độ lớn tuyệt đối**:

- `3.01 → 4`, `-3.01 → -4` khi `scale = 0`.
- `3.00 → 3`, `-3.00 → -3` vì phần bị bỏ chỉ gồm số 0.

Dùng khi yêu cầu làm tròn số lượng hoặc đơn vị theo hướng luôn đủ về mặt độ lớn, nhưng cần kiểm tra xem chính sách thực tế có phù hợp với số âm hay không.

### `DOWN` — về số 0

`DOWN` loại bỏ phần chữ số vượt quá độ chính xác yêu cầu:

- `3.99 → 3`, `-3.99 → -3` khi `scale = 0`.
- Không phải luôn là “làm tròn xuống dưới” theo trục số: với số âm, `-3` **lớn hơn** `-3.99`.

### `CEILING` — về dương vô cực

- `3.01 → 4`, `-3.01 → -3`.
- `CEILING` không có nghĩa “tăng chữ số” của mọi số; nó nghĩa **chọn ứng viên lớn hơn hoặc bằng đầu vào**.

### `FLOOR` — về âm vô cực

- `3.99 → 3`, `-3.01 → -4`.
- `FLOOR` không có nghĩa “giảm độ lớn tuyệt đối”; với số âm, kết quả có thể xa 0 hơn.

### `HALF_UP` — gần nhất, tie xa 0

- `2.49 → 2`, `2.50 → 3`; `-2.49 → -2`, `-2.50 → -3`.
- Đây là quy tắc thường gặp khi một đặc tả ghi “5 thì làm tròn lên”, nhưng **phải xác minh** quy tắc áp dụng cho số âm: `HALF_UP` làm tròn `-2.5` thành `-3`.

### `HALF_DOWN` — gần nhất, tie về 0

- `2.49 → 2`, `2.50 → 2`, `2.51 → 3`.
- `-2.49 → -2`, `-2.50 → -2`, `-2.51 → -3`.

`HALF_DOWN` không có nghĩa luôn về 0: khi khoảng cách lệch khỏi điểm giữa, nó vẫn chọn kết quả gần hơn.

### `HALF_EVEN` — gần nhất, tie về chữ số chẵn

- `2.5 → 2`, `3.5 → 4`, `-2.5 → -2`, `-3.5 → -4`.
- Với hai chữ số sau dấu thập phân: `1.245 → 1.24` vì chữ số hàng phần trăm **4** chẵn; `1.255 → 1.26` vì ứng viên có chữ số hàng phần trăm **6** chẵn.

Chính xác **nửa đơn vị** ở vị trí làm tròn mới là tie. Chẳng hạn `1.2451` làm tròn đến scale 2 sẽ là `1.25` với cả ba chế độ `HALF_` vì nó **lớn hơn** điểm giữa `1.245`, dù sau chữ số `5` còn chữ số khác 0.

### `UNNECESSARY` — bắt buộc không mất thông tin

- `new BigDecimal("2.00").setScale(0, UNNECESSARY)` thành `2`: bỏ các chữ số 0, **không** mất giá trị.
- `new BigDecimal("2.01").setScale(0, UNNECESSARY)` ném `ArithmeticException`.
- Dùng để thực thi bất biến: nếu giá trị không thể biểu diễn chính xác theo định dạng yêu cầu thì coi là lỗi đầu vào, không âm thầm làm tròn.

## 5. Chương trình Java 17+ chạy độc lập

Tạo tệp `SignedRoundingModesDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class SignedRoundingModesDemo {
    private static String round(String raw, int scale, RoundingMode mode) {
        try {
            return new BigDecimal(raw)
                    .setScale(scale, mode)
                    .toPlainString();
        } catch (ArithmeticException ex) {
            // "ERROR" biểu diễn trường hợp UNNECESSARY không cho phép làm tròn.
            return "ERROR";
        }
    }

    public static void main(String[] args) {
        String[] values = {"2.5", "-2.5", "2.4", "-2.4"};
        System.out.println("mode ` +2.5 ` -2.5 ` +2.4 ` -2.4");

        for (RoundingMode mode : RoundingMode.values()) {
            System.out.printf("%s ` %s ` %s ` %s ` %s%n",
                    mode,
                    round(values[0], 0, mode),
                    round(values[1], 0, mode),
                    round(values[2], 0, mode),
                    round(values[3], 0, mode));
        }

        System.out.println("HALF_EVEN (+3.5,-3.5): "
                + round("3.5", 0, RoundingMode.HALF_EVEN)
                + "; " + round("-3.5", 0, RoundingMode.HALF_EVEN));

        System.out.println("HALF_UP (+1.235,-1.235): "
                + round("1.235", 2, RoundingMode.HALF_UP)
                + "; " + round("-1.235", 2, RoundingMode.HALF_UP));

        System.out.println("HALF_EVEN (1.245,1.255): "
                + round("1.245", 2, RoundingMode.HALF_EVEN)
                + "; " + round("1.255", 2, RoundingMode.HALF_EVEN));

        System.out.println("CEILING/FLOOR (-1.231): "
                + round("-1.231", 2, RoundingMode.CEILING)
                + "; " + round("-1.231", 2, RoundingMode.FLOOR));

        System.out.println("HALF_EVEN tens (145,155): "
                + round("145", -1, RoundingMode.HALF_EVEN)
                + "; " + round("155", -1, RoundingMode.HALF_EVEN));

        System.out.println("UNNECESSARY exact: "
                + round("2.00", 0, RoundingMode.UNNECESSARY));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac SignedRoundingModesDemo.java
java SignedRoundingModesDemo
~~~

Stdout:

~~~text
mode ` +2.5 ` -2.5 ` +2.4 ` -2.4
UP ` 3 ` -3 ` 3 ` -3
DOWN ` 2 ` -2 ` 2 ` -2
CEILING ` 3 ` -2 ` 3 ` -2
FLOOR ` 2 ` -3 ` 2 ` -3
HALF_UP ` 3 ` -3 ` 2 ` -2
HALF_DOWN ` 2 ` -2 ` 2 ` -2
HALF_EVEN ` 2 ` -2 ` 2 ` -2
UNNECESSARY ` ERROR ` ERROR ` ERROR ` ERROR
HALF_EVEN (+3.5,-3.5): 4; -4
HALF_UP (+1.235,-1.235): 1.24; -1.24
HALF_EVEN (1.245,1.255): 1.24; 1.26
CEILING/FLOOR (-1.231): -1.23; -1.24
HALF_EVEN tens (145,155): 140; 160
UNNECESSARY exact: 2
~~~

Chương trình dùng các **chuỗi thập phân chính xác** và `BigDecimal.setScale`, tránh nhiễu từ biểu diễn nhị phân của `double`. Nó chủ động bắt `ArithmeticException` để minh họa `UNNECESSARY`; trong code nghiệp vụ, thường nên để lỗi này được xử lý theo chính sách validation, thay vì chỉ ghi “ERROR” chung chung.

Các phép tính kiểm chứng bằng Java: `HALF_EVEN` với `3.5/-3.5` cho `4/-4`, với `1.245/1.255` ở scale 2 cho `1.24/1.26`, với `145/155` ở scale -1 cho `140/160`. Số âm `-1.231` được làm tròn ở scale 2 thành `-1.23` theo `CEILING` và `-1.24` theo `FLOOR`.

## 6. Bên dưới `setScale`: scale, precision, tie và dấu

### Scale không đồng nhất với precision

Với `BigDecimal`, **scale** điều khiển số chữ số phía sau dấu thập phân theo biểu diễn `unscaledValue × 10^(-scale)`. **Precision** là tổng chữ số có nghĩa của biểu diễn.

Ví dụ:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

BigDecimal x = new BigDecimal("1234.567");

System.out.println(
        x.setScale(4, RoundingMode.HALF_UP).toPlainString()
); // 1234.5670: bốn chữ số SAU dấu thập phân

System.out.println(
        x.round(new MathContext(4, RoundingMode.HALF_UP)).toPlainString()
); // 1235: bốn chữ số CÓ NGHĨA
~~~

Đây là **đoạn minh họa các biểu thức Java**, có thể chạy trong `jshell` hoặc đặt vào phương thức `main`; không phải một tệp Java độc lập ở dạng trình bày này.

Khi `MathContext` yêu cầu `precision = 0`, ý nghĩa là không giới hạn precision, nên thao tác thông thường không buộc phải làm tròn vì giới hạn precision. `MathContext.UNLIMITED` cũng quy định `RoundingMode.HALF_UP` nhưng do precision không giới hạn, thông thường không dùng quy tắc đó để cắt chữ số.

### Tie tính theo vị trí cần giữ, không theo riêng chữ số 5

Làm tròn `scale = 2` có bước `0.01`, vì vậy:

| Dữ liệu | Hai ứng viên gần nhau | Kết quả `HALF_EVEN` |
| --- | --- | --- |
| `1.245` | `1.24` và `1.25` | `1.24` (4 chẵn) |
| `1.255` | `1.25` và `1.26` | `1.26` (6 chẵn) |
| `-1.245` | `-1.24` và `-1.25` | `-1.24` (4 chẵn) |
| `-1.255` | `-1.25` và `-1.26` | `-1.26` (6 chẵn) |
| `1.2451` | `1.24` và `1.25` | `1.25` (gần hơn) |

Không được áp dụng quy tắc `HALF_EVEN` kiểu “gặp chữ số 5 thì làm tròn về chẵn” một cách máy móc khi sau chữ số 5 vẫn có số khác 0. Chỉ khi phần bị bỏ **đúng bằng một nửa** đơn vị làm tròn mới xét tính chẵn/lẻ.

### Scale âm cũng có thể dùng để làm tròn

Muốn làm tròn về hàng chục, có thể gọi `setScale(-1, mode)`:

~~~java
BigDecimal first = new BigDecimal("145");
BigDecimal second = new BigDecimal("155");

System.out.println(
        first.setScale(-1, RoundingMode.HALF_EVEN).toPlainString()
); // 140
System.out.println(
        second.setScale(-1, RoundingMode.HALF_EVEN).toPlainString()
); // 160
~~~

Cả hai đều nằm đúng giữa hai bội số liên tiếp của 10. Với `145`, hàng chục `4` là chẵn, nên chọn `140`; với `155`, hàng chục `6` là chẵn, nên chọn `160`. `toPlainString()` dùng để in `140` hoặc `160` thay vì dạng có số mũ mà `toString()` có thể tạo khi scale âm.

## 7. Khi phép toán tự nó cần chế độ làm tròn

### Phép chia có thể không có khai triển thập phân hữu hạn

Không phải phép chia nào cũng biểu diễn được dưới dạng `BigDecimal` hữu hạn. Ví dụ `1 / 3` có khai triển vô hạn. Phép `divide(BigDecimal)` không kèm độ chính xác/chế độ làm tròn có thể ném `ArithmeticException` khi kết quả thập phân không kết thúc.

Hãy khai báo rõ độ chính xác của kết quả:

~~~java
BigDecimal one = new BigDecimal("1");
BigDecimal eight = new BigDecimal("8");

System.out.println(
        one.divide(eight, 2, RoundingMode.HALF_UP)
); // 0.13

System.out.println(
        one.negate().divide(eight, 2, RoundingMode.HALF_UP)
); // -0.13
~~~

Hai ví dụ làm tròn `±0.125` về scale 2, điểm giữa `±0.12` và `±0.13`. Chế độ `HALF_UP` chọn `±0.13` vì xa 0 hơn tại tie.

Lưu ý: `divide(BigDecimal divisor, int scale, RoundingMode mode)` làm tròn **theo scale**. Một overload khác là `divide(BigDecimal divisor, MathContext mc)`, làm tròn **theo precision** được khai báo trong `MathContext`. Với `divide` và `UNNECESSARY`, phép chia phải chính xác trong độ chính xác/scale cho phép, nếu không sẽ ném ngoại lệ.

### Tích lũy phép toán: làm tròn ở đâu?

Thực hiện một chuỗi tính toán có làm tròn **sau mỗi bước** có thể khác làm tròn **một lần ở bước cuối**. Ví dụ cụ thể:

- Làm tròn từng giá trị `0.125` về 2 chữ số bằng `HALF_UP` được `0.13`; ba giá trị đã làm tròn cộng lại là `0.39`.
- Cộng ba giá trị gốc trước: `0.125 + 0.125 + 0.125 = 0.375`; rồi làm tròn một lần về 2 chữ số bằng `HALF_UP` được `0.38`.

Không có cách nào luôn đúng cho mọi nghiệp vụ. Nếu yêu cầu là làm tròn **từng dòng hóa đơn**, kết quả có thể khác cách tính tổng chưa làm tròn rồi làm tròn khi kết toán. Quy tắc phải được xác định cùng với thứ tự phép toán; không được thay đổi tùy tiện khi tối ưu code.

## 8. Số âm và hệ sinh thái Java: những nhầm lẫn nguy hiểm

### `Math.round` không phải `BigDecimal` + `HALF_UP`

`Math.round(double)` là API khác với quy tắc ở `RoundingMode.HALF_UP`. Với giá trị chính xác có thể biểu diễn như `±2.5`:

~~~java
System.out.println(Math.round(2.5));  // 3
System.out.println(Math.round(-2.5)); // -2

System.out.println(
        new BigDecimal("-2.5").setScale(0, RoundingMode.HALF_UP)
); // -3
~~~

`Math.round(-2.5)` chọn `-2`, trong khi `HALF_UP` chọn `-3`. Khi chuyển đổi code từ `Math.round` sang `BigDecimal`, cần đối chiếu quy tắc tại số âm và tie, không chỉ kiểm tra số dương.

### Không tạo `BigDecimal` từ literal `double` nếu muốn thập phân chính xác

~~~java
BigDecimal exact = new BigDecimal("2.675");
BigDecimal fromDouble = new BigDecimal(2.675);

System.out.println(exact.setScale(2, RoundingMode.HALF_EVEN)); // 2.68
~~~

`2.675` không có biểu diễn nhị phân hữu hạn bằng `double`, nên `fromDouble` mang giá trị nhị phân đã được xấp xỉ rồi chuyển sang thập phân; khi làm tròn ở vị trí tie, kết quả có thể khác số thập phân bạn tưởng đã nhập. Dùng constructor từ `String` hoặc xử lý theo hợp đồng đầu vào; khi nhận sẵn `double` và muốn biểu diễn thập phân dựa trên `Double.toString`, cân nhắc `BigDecimal.valueOf(double)`.

### Dấu âm và số 0

`BigDecimal` không giữ một giá trị “âm 0” tách biệt theo nghĩa so sánh số học. Vì thế, làm tròn số âm rất nhỏ **về 0** có thể hiển thị `0`, không phải `-0`:

~~~java
System.out.println(
        new BigDecimal("-0.1").setScale(0, RoundingMode.CEILING)
); // 0

System.out.println(
        new BigDecimal("-0.1").setScale(0, RoundingMode.FLOOR)
); // -1
~~~

Không suy đoán dấu ban đầu từ kết quả đã được làm tròn về 0. Nếu nghiệp vụ cần phân biệt hướng thay đổi, lưu thông tin đó riêng.

## 9. Chọn chế độ theo yêu cầu nghiệp vụ

| Yêu cầu cụ thể | Cách triển khai phù hợp | Cần xác nhận thêm |
| --- | --- | --- |
| Làm tròn đối xứng gần nhất, điểm giữa xa 0 | `HALF_UP` | Quy định đối với giá trị âm và vị trí làm tròn |
| Làm tròn gần nhất, điểm giữa về 0 | `HALF_DOWN` | Quy tắc này có thực sự được hợp đồng yêu cầu không |
| Làm tròn gần nhất, điểm giữa về chữ số chẵn | `HALF_EVEN` | Có được phép áp dụng khi tính tổng/từng dòng không |
| Luôn chọn mức cao hơn trên trục số | `CEILING` | Phải áp dụng đúng cả với số âm |
| Luôn chọn mức thấp hơn trên trục số | `FLOOR` | Phải áp dụng đúng cả với số âm |
| Luôn tăng độ lớn tuyệt đối khi có phần bị bỏ | `UP` | Có ý định áp dụng đối xứng cho số âm không |
| Loại bỏ phần vượt quá vị trí làm tròn về phía 0 | `DOWN` | Có chấp nhận bỏ thông tin không |
| Dữ liệu bắt buộc chính xác ở scale cho trước | `UNNECESSARY` | Lỗi phải báo hay từ chối ở tầng nào |

Với tiền tệ và dữ liệu kế toán, **không tự áp đặt** `HALF_UP` hoặc `HALF_EVEN` chỉ vì nó phổ biến. Một quốc gia, chuẩn giao dịch, thuế, ngân hàng hoặc hệ thống có thể yêu cầu chính sách riêng cho từng phép tính. Quy định tối thiểu nên nêu rõ: vị trí làm tròn, mode, thời điểm làm tròn, cách cộng tổng và xử lý giá trị âm/hoàn tiền.

Với thống kê hoặc mô phỏng, `HALF_EVEN` có thể giảm độ lệch hướng của các trường hợp tie nếu các điều kiện dữ liệu phù hợp, nhưng nó **không sửa** mọi sai lệch do lấy mẫu, độ chính xác đầu vào hay thứ tự phép tính.

Với đầu vào buộc phải có hai chữ số thập phân chính xác, ví dụ thay vì âm thầm làm tròn `12.345`, có thể kiểm tra:

~~~java
BigDecimal submitted = new BigDecimal("12.345");
BigDecimal checked = submitted.setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException: sẽ phải làm tròn, nên giá trị không hợp lệ theo quy tắc này.
~~~

## 10. Lỗi thường gặp và checklist khi tự kiểm tra

1. **Nhầm `UP` thành “về +∞”.** `-2.4` theo `UP` ra `-3`, theo `CEILING` ra `-2`.
2. **Nhầm `DOWN` thành “về −∞”.** `-2.4` theo `DOWN` ra `-2`, theo `FLOOR` ra `-3`.
3. **Cho rằng mọi `HALF_` khác nhau trên mọi dữ liệu.** Với `±2.4`, cả ba đều ra `±2`; chúng chỉ khác nhau ở tie.
4. **Diễn giải `HALF_EVEN` là “nếu số gốc chẵn thì giữ nguyên”.** Nó xét chữ số giữ lại ở **vị trí đang làm tròn**: `3.5 → 4` là hợp lệ.
5. **Giả định `UNNECESSARY` luôn báo lỗi khi đổi scale.** Đổi `2.00` thành `2` là chính xác, nên không lỗi.
6. **Nhầm scale và precision.** `setScale(2, mode)` và `MathContext(2, mode)` quy định hai thứ khác nhau.
7. **Quên số âm trong kiểm thử.** Bộ kiểm thử tối thiểu cho mỗi mode nên có `+2.5`, `-2.5`, `+2.4`, `-2.4` và `±3.5`, đồng thời kiểm tra cả trường hợp không cần làm tròn.
8. **Sử dụng `double` khiến tie không còn chính xác.** Tạo `BigDecimal` từ chuỗi thập phân nếu đó là dữ liệu gốc.

### Bài tập tự kiểm tra

Không chạy chương trình ngay, hãy dự đoán kết quả trước:

1. `new BigDecimal("-7.1").setScale(0, FLOOR)` so với `...CEILING`?
2. `new BigDecimal("-7.5").setScale(0, HALF_UP)` so với `...HALF_DOWN`?
3. `new BigDecimal("6.5").setScale(0, HALF_EVEN)` và `new BigDecimal("7.5").setScale(0, HALF_EVEN)`?
4. `new BigDecimal("-2.345").setScale(2, HALF_EVEN)`?
5. `new BigDecimal("12.000").setScale(0, UNNECESSARY)` có ném lỗi không?
6. `new BigDecimal("145").setScale(-1, HALF_UP).toPlainString()` và `new BigDecimal("-145").setScale(-1, HALF_UP).toPlainString()`?

**Đáp án và lý do:**

1. `FLOOR = -8` (hướng −∞); `CEILING = -7` (hướng +∞).
2. `HALF_UP = -8` (tie xa 0); `HALF_DOWN = -7` (tie về 0).
3. `6.5 → 6` và `7.5 → 8` theo `HALF_EVEN` vì ứng viên được chọn có chữ số hàng đơn vị chẵn.
4. `-2.345 → -2.34`: hai ứng viên có cùng khoảng cách; chữ số hàng phần trăm `4` chẵn.
5. **Không lỗi**, kết quả `12`, vì bỏ các số 0 ở phần lẻ không đổi giá trị.
6. `145 → 150` và `-145 → -150` theo `HALF_UP` khi làm tròn hàng chục, vì cả hai là tie và phải chọn phía xa 0.

**Ghi nhớ:** Với giá trị âm, “lên/xuống” phải được định nghĩa theo **trục số** hay **khoảng cách đến 0**. Khi kết quả gần nhau như nhau, ba chế độ `HALF_` mới khác nhau. Hãy quyết định scale hoặc precision cùng chính sách mode, kiểm thử dấu âm và xử lý riêng yêu cầu không được mất độ chính xác.
