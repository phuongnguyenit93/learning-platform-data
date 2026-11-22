# Bảng chia, lấy dư và làm tròn cho số âm trong Java

## 1. Mục tiêu tra cứu: cùng một số âm, nhiều quy tắc khác nhau

Với số dương, nhiều phép chia và làm tròn trông giống nhau. Nhưng khi xuất hiện số âm, ba khái niệm sau có thể dẫn đến các kết quả rất khác:

1. **Chia lấy thương nguyên theo hướng về 0** — phép `/` trên hai kiểu nguyên của Java.
2. **Chia lấy thương nguyên theo hướng về âm vô cực** — `Math.floorDiv`.
3. **Làm tròn một số thực/thập phân** — `Math.floor`, `Math.ceil`, `Math.round`, `Math.rint` hoặc `BigDecimal.setScale(..., RoundingMode)`.

Ví dụ:

~~~java
System.out.println(-7 / 3);                 // -2
System.out.println(-7 % 3);                 // -1
System.out.println(Math.floorDiv(-7, 3));   // -3
System.out.println(Math.floorMod(-7, 3));   // 2
~~~

Nếu cần chia thời gian thành bucket, tính chỉ số trang, quay vòng index, đối chiếu số dư nợ, hoặc dựng công thức làm tròn tài chính, nhầm các quy tắc này có thể gây lỗi biên nghiêm trọng. Bài tra cứu này tập trung vào **số âm**, nhưng đặt kết quả dương bên cạnh để tránh rút ra quy tắc sai.

**Bản đồ nhanh:**

| Muốn thực hiện | API / toán tử | Hướng chia hoặc làm tròn |
| --- | --- | --- |
| Chia `int` / `long`, bỏ phần lẻ | `a / b` | Thương nguyên về **0** |
| Lấy dư tương ứng thương về 0 | `a % b` | Dư cùng dấu **số bị chia** nếu khác 0 |
| Chia nguyên theo floor | `Math.floorDiv(a, b)` | Thương về **−∞** |
| Phần dư theo floor | `Math.floorMod(a, b)` | Dư cùng dấu **số chia** nếu khác 0 |
| Làm tròn xuống theo trục số | `Math.floor(x)` | Về **−∞**, trả `double` |
| Làm tròn lên theo trục số | `Math.ceil(x)` | Về **+∞**, trả `double` |
| Làm tròn gần nhất, điểm giữa về +∞ | `Math.round(x)` | Trả `int` nếu `float`, `long` nếu `double` |
| Làm tròn gần nhất, điểm giữa về số chẵn | `Math.rint(x)` | Trả `double` |
| Làm tròn decimal với chính sách rõ ràng | `BigDecimal.setScale(scale, mode)` | Do `RoundingMode` quyết định |

Không có một phương pháp gọi chung là “làm tròn xuống” đủ chính xác khi giá trị có thể âm. Hãy luôn hỏi “**xuống theo trục số**, hay **giảm độ lớn về 0**?”.

## 2. Chia số nguyên: `/` luôn cắt phần lẻ về 0

Khi cả hai toán hạng đều là các kiểu nguyên (`int`, `long`; `byte`/`short`/`char` sau numeric promotion), phép `/` cho thương **nguyên**. Java cắt phần thập phân về **0**, không dùng floor.

| Số bị chia `a` | Số chia `b` | Thương thực | `a / b` (Java) |
| ---: | ---: | ---: | ---: |
| `7` | `3` | `2.333…` | `2` |
| `-7` | `3` | `-2.333…` | `-2` |
| `7` | `-3` | `-2.333…` | `-2` |
| `-7` | `-3` | `2.333…` | `2` |
| `-1` | `3` | `-0.333…` | `0` |
| `-8` | `3` | `-2.666…` | `-2` |

Ở đây `-7 / 3 == -2`, **không phải −3**. Phần lẻ bị bỏ, dù điều đó khiến kết quả lớn hơn thương thực theo trục số.

Thứ tự toán hạng rất quan trọng: `-7 / 3` và `7 / -3` cùng ra `-2`, nhưng lấy dư đi kèm không giống nhau vì số bị chia khác dấu.

### `/` trên floating point không phải chia nguyên

~~~java
System.out.println(-7 / 3);     // -2, int
System.out.println(-7.0 / 3);   // -2.3333333333333335, double
System.out.println(-7 / 3.0);   // -2.3333333333333335, double
~~~

`-7.0 / 3` không bị cắt về 0: toán hạng `double` khiến phép chia dùng floating point. Kết quả thập phân hiển thị là xấp xỉ binary64, không phải một decimal vô hạn chính xác.

Nếu muốn làm tròn thương thành một số nguyên theo quy tắc khác, **đừng** chia nguyên rồi mới cast sang `double` hoặc gọi `Math.floor`. Phần lẻ đã mất và không thể khôi phục:

~~~java
double tooLate = Math.floor(-7 / 3);    // -2.0, vì -7 / 3 đã ra -2
double floorReal = Math.floor(-7.0 / 3); // -3.0
~~~

## 3. Toán tử `%`: số dư có dấu theo số bị chia

Với phép chia **nguyên**, Java dùng một thương cắt về 0; số dư từ `a % b` thỏa mãn:

\[
a = (a / b) \times b + (a \% b)
\]

Giả sử `b != 0` và không rơi vào góc tràn `MIN_VALUE / -1`. Khi số dư khác 0, dấu của nó cùng dấu `a` (số bị chia).

| `a` | `b` | `a / b` | `a % b` | Kiểm tra |
| ---: | ---: | ---: | ---: | --- |
| `7` | `3` | `2` | `1` | `2 × 3 + 1 = 7` |
| `-7` | `3` | `-2` | `-1` | `-2 × 3 − 1 = −7` |
| `7` | `-3` | `-2` | `1` | `-2 × -3 + 1 = 7` |
| `-7` | `-3` | `2` | `-1` | `2 × -3 − 1 = −7` |
| `-8` | `3` | `-2` | `-2` | `-2 × 3 − 2 = −8` |
| `-1` | `3` | `0` | `-1` | `0 × 3 − 1 = −1` |

**Cảnh báo:** `%` trong Java thường được gọi là “modulo”, nhưng về mặt dấu nó là **remainder theo phép chia cắt về 0**. Với `-7 % 3`, bạn nhận `-1`, không nhận `2` như modulo Euclid dương.

Không dùng trực tiếp `negativeIndex % listSize` để lập chỉ số danh sách nếu `negativeIndex` có thể âm: kết quả âm gây `IndexOutOfBoundsException` khi truy cập phần tử.

## 4. `Math.floorDiv` và `Math.floorMod`: chia theo âm vô cực

`Math.floorDiv(a,b)` chọn **thương nguyên không lớn hơn thương thực** (floor). `Math.floorMod(a,b)` trả số dư tương ứng sao cho:

\[
a = \operatorname{floorDiv}(a,b) \times b
    + \operatorname{floorMod}(a,b)
\]

Với `b > 0`, `floorMod(a,b)` nằm trong `[0,b)`. Với `b < 0`, số dư không bằng 0 có dấu **âm**, trùng dấu số chia. Vì vậy không nên tuyên bố `floorMod` “luôn không âm”: điều này chỉ đúng khi **số chia dương**.

| `a` | `b` | `a / b` | `a % b` | `floorDiv(a,b)` | `floorMod(a,b)` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| `7` | `3` | `2` | `1` | `2` | `1` |
| `-7` | `3` | `-2` | `-1` | `-3` | `2` |
| `7` | `-3` | `-2` | `1` | `-3` | `-2` |
| `-7` | `-3` | `2` | `-1` | `2` | `-1` |
| `8` | `3` | `2` | `2` | `2` | `2` |
| `-8` | `3` | `-2` | `-2` | `-3` | `1` |
| `1` | `3` | `0` | `1` | `0` | `1` |
| `-1` | `3` | `0` | `-1` | `-1` | `2` |

Ví dụ ứng dụng: lập index vòng tròn độ dài 5 từ một vị trí có thể âm:

~~~java
int size = 5;
int negativeOffset = -1;

System.out.println(negativeOffset % size);             // -1 (không dùng làm index)
System.out.println(Math.floorMod(negativeOffset, size)); // 4 (index hợp lệ)
~~~

Nếu `size <= 0` thì phải kiểm tra dữ liệu trước: size = 0 gây chia cho 0; size âm không phải kích thước hợp lệ của list và không cho miền index mong muốn.

### Không đánh đồng `floorDiv` với cast của chia thực

Ví dụ `(int) Math.floor((double) a / b)` có thể mất chính xác khi `long` lớn do chuyển sang `double`. `Math.floorDiv(long,long)` làm việc trực tiếp trên số nguyên, không cần binary64 trung gian và thường là lựa chọn đúng cho chia nguyên theo floor.

## 5. Các tình huống biên: số 0, MIN_VALUE và chia cho 0

- Chia nguyên hoặc lấy dư nguyên với số chia bằng 0 ném `ArithmeticException`.
- `Math.floorDiv` và `Math.floorMod` với số chia 0 cũng ném `ArithmeticException`.
- `0 / -3 == 0` và `0 % -3 == 0`, vì số bị chia bằng 0.
- `Integer.MIN_VALUE / -1` không nằm trong miền `int` vì thương toán học bằng 2147483648; Java cho kết quả wrap về `Integer.MIN_VALUE`. `Math.floorDiv(Integer.MIN_VALUE, -1)` cũng trả `Integer.MIN_VALUE` tại trường hợp đặc biệt này.
- Với `Long.MIN_VALUE / -1L`, vấn đề tương tự xảy ra trong miền `long`.

~~~java
System.out.println(Integer.MIN_VALUE / -1);              // -2147483648
System.out.println(Math.floorDiv(Integer.MIN_VALUE, -1)); // -2147483648
System.out.println(Integer.MIN_VALUE % -1);              // 0
~~~

Nếu chương trình cần phát hiện overflow chính xác tại chia cho -1, phải kiểm tra riêng `MIN_VALUE` và số chia `-1` (hoặc chọn miền số lớn hơn), không trông chờ `/` hay `Math.floorDiv` tự ném lỗi overflow.

**Lưu ý về công thức:** biểu thức chứng minh đồng nhất `(a / b) * b + (a % b)` cũng có thể chịu wrap do các phép nhân/cộng `int` trong những trường hợp biên. Khi lập lập luận toán học về chia và số dư, cần xét giới hạn biểu diễn của phép tính thực tế.

## 6. Floating point: `%` không giống `Math.IEEEremainder`

Toán tử `%` hỗ trợ cả `float` và `double`. Về cơ bản, nó trả số dư theo thương bị cắt về 0; phần dư có thể là số âm và khác với phần dư IEEE 754 kiểu “nearest integral quotient”.

Ví dụ:

~~~java
System.out.println(-7.0 % 4.0);                  // -3.0
System.out.println(Math.IEEEremainder(-7.0, 4.0)); // 1.0
~~~

`Math.IEEEremainder(x,y)` dùng thương nguyên **gần nhất** với `x/y`; trường hợp thương nằm đúng giữa hai số nguyên thì chọn **thương chẵn**. Nó **không** phải phép toán modulo dương, cũng không phải bản thay thế trực tiếp cho `%`.

| Biểu thức | Kết quả | Vì sao |
| --- | ---: | --- |
| `-7.0 % 4.0` | `-3.0` | Thương -1 khi cắt về 0; số dư -3 |
| `Math.IEEEremainder(-7.0,4.0)` | `1.0` | Thương gần nhất -2; dư +1 |
| `Math.IEEEremainder(6.0,4.0)` | `-2.0` | Thương 1.5, tie chọn thương chẵn 2 |
| `Math.IEEEremainder(-6.0,4.0)` | `2.0` | Thương -1.5, tie chọn thương chẵn -2 |

Phép chia floating point cho 0, các biểu thức với `NaN`, `±Infinity` và **âm 0.0** có những ngữ nghĩa IEEE đặc biệt. Chẳng hạn `-7.0 / 0.0` tạo vô cực âm và `-7.0 % 0.0` là `NaN`; ngược lại, phép chia nguyên cho 0 ném exception. Không tự viết logic xử lý chung cho hai kiểu số mà bỏ qua khác biệt này.

## 7. `Math.floor`, `Math.ceil`, `Math.round`, `Math.rint` với số âm

Cần tách **hướng trên trục số** khỏi “tăng/giảm độ lớn tuyệt đối”:

- `Math.floor(x)`: trả số nguyên gần nhất **không lớn hơn x**, ở dạng `double`.
- `Math.ceil(x)`: trả số nguyên gần nhất **không nhỏ hơn x**, ở dạng `double`.
- `Math.round(float)`: làm tròn thành `int` gần nhất, điểm giữa theo hướng **+∞**.
- `Math.round(double)`: làm tròn thành `long` gần nhất, điểm giữa theo hướng **+∞**.
- `Math.rint(double)`: trả `double` mang giá trị nguyên gần nhất; điểm giữa chọn giá trị **chẵn**.

Bảng với những số âm quan trọng:

| `x` | `Math.floor(x)` | `Math.ceil(x)` | `Math.round(x)` với `x` là `double` | `Math.rint(x)` |
| ---: | ---: | ---: | ---: | ---: |
| `-2.1` | `-3.0` | `-2.0` | `-2` | `-2.0` |
| `-2.4` | `-3.0` | `-2.0` | `-2` | `-2.0` |
| `-2.5` | `-3.0` | `-2.0` | `-2` | `-2.0` |
| `-2.6` | `-3.0` | `-2.0` | `-3` | `-3.0` |
| `-3.5` | `-4.0` | `-3.0` | `-3` | `-4.0` |
| `2.5` | `2.0` | `3.0` | `3` | `2.0` |

Đặc biệt:

~~~java
System.out.println(Math.round(-2.5)); // -2
System.out.println(Math.round(-3.5)); // -3
System.out.println(Math.rint(-2.5));  // -2.0
System.out.println(Math.rint(-3.5));  // -4.0
~~~

`Math.round(-2.5)` **không** làm tròn ra xa 0. Nếu muốn “điểm giữa thì xa 0”, hãy xem `BigDecimal` cùng `RoundingMode.HALF_UP` hoặc xây dựng quy tắc rõ ràng cho miền số cần dùng.

`Math.round` còn có các quy tắc riêng cho `NaN`, vô cực và giá trị ngoài miền `int`/`long` (có thể bão hòa ở biên). Đây không phải phép toán kiểm tra overflow tổng quát; tránh đưa kết quả `Math.round` thành bằng chứng rằng mọi số có thể được biểu diễn chính xác bằng kiểu nguyên đích.

## 8. `BigDecimal`: làm tròn thập phân chính xác với `RoundingMode`

Với giá trị decimal cần làm tròn theo chính sách nghiệp vụ, `BigDecimal` hữu ích vì biểu diễn chuỗi thập phân **chính xác**, không bắt buộc chuyển qua `double`.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal negative = new BigDecimal("-2.5");

System.out.println(negative.setScale(0, RoundingMode.HALF_UP));   // -3
System.out.println(negative.setScale(0, RoundingMode.HALF_DOWN)); // -2
System.out.println(negative.setScale(0, RoundingMode.HALF_EVEN)); // -2
~~~

### Bảng đủ tám chế độ với số âm

Các ví dụ dùng `new BigDecimal(value).setScale(0, mode)`, tức làm tròn về **hàng đơn vị**. `-2.4` không nằm giữa hai số nguyên; `-2.5` và `-3.5` nằm đúng giữa.

| `RoundingMode` | `-2.4` | `-2.5` | `-3.5` | `+2.5` | Quy tắc |
| --- | ---: | ---: | ---: | ---: | --- |
| `UP` | `-3` | `-3` | `-4` | `3` | Xa số 0 nếu cần loại chữ số |
| `DOWN` | `-2` | `-2` | `-3` | `2` | Về số 0 |
| `CEILING` | `-2` | `-2` | `-3` | `3` | Về dương vô cực |
| `FLOOR` | `-3` | `-3` | `-4` | `2` | Về âm vô cực |
| `HALF_UP` | `-2` | `-3` | `-4` | `3` | Gần nhất; điểm giữa xa 0 |
| `HALF_DOWN` | `-2` | `-2` | `-3` | `2` | Gần nhất; điểm giữa về 0 |
| `HALF_EVEN` | `-2` | `-2` | `-4` | `2` | Gần nhất; điểm giữa chọn chữ số được giữ là chẵn |
| `UNNECESSARY` | lỗi | lỗi | lỗi | lỗi | Cấm làm tròn mất giá trị |

“lỗi” ở `UNNECESSARY` nghĩa là `ArithmeticException` vì bốn đầu vào đều cần loại phần thập phân khác 0. `UNNECESSARY` vẫn hợp lệ nếu việc đổi scale không mất giá trị:

~~~java
System.out.println(new BigDecimal("-2.00")
        .setScale(0, RoundingMode.UNNECESSARY)); // -2
~~~

**Phân biệt bốn hướng:** với `-2.4`, `UP=-3` và `FLOOR=-3`; `DOWN=-2` và `CEILING=-2`. Nhưng sự trùng hợp này không còn đúng nếu đổi sang số dương: `UP(2.4)=3`, `FLOOR(2.4)=2`.

### Half-even không có nghĩa “mọi số âm đều về 0”

`HALF_EVEN(-2.5)=-2` nhưng `HALF_EVEN(-3.5)=-4`. Chỉ khi **hai ứng viên có khoảng cách bằng nhau** mới xét chữ số cuối của ứng viên nào là chẵn. Ở giá trị `-2.6`, mọi chế độ `HALF_*` chọn `-3` vì đó là ứng viên gần hơn.

## 9. `BigDecimal`: thương nguyên và remainder của số âm

`BigDecimal` **không hỗ trợ** toán tử `/` hoặc `%` trực tiếp giữa hai object. Thay vào đó:

- `a.divideToIntegralValue(b)`: phần **nguyên** của thương, theo hướng về 0.
- `a.remainder(b)`: phần còn lại sau phép chia dùng thương nguyên theo hướng về 0.
- `a.divideAndRemainder(b)`: trả đồng thời thương nguyên và dư.
- `a.divide(b, scale, mode)`: thương thập phân với scale và cách làm tròn đã chỉ định.

Ví dụ:

~~~java
BigDecimal a = new BigDecimal("-7");
BigDecimal b = new BigDecimal("3");

System.out.println(a.divideToIntegralValue(b).toPlainString()); // -2
System.out.println(a.remainder(b).toPlainString());              // -1
System.out.println(a.divide(b, 2, RoundingMode.HALF_UP));        // -2.33
~~~

Đặc biệt, `BigDecimal.remainder` không tự cung cấp modulo dương. Với `-7` và `3`, dư là `-1` giống dấu số bị chia. Nếu muốn một modulo trong khoảng không âm cho modulus dương `m`, cần quy định rõ và xây hàm riêng, ví dụ dùng `BigInteger.mod` cho số nguyên tùy ý.

`BigInteger` có cả `remainder` và `mod`, nhưng hai phương thức có ý nghĩa khác nhau:

~~~java
import java.math.BigInteger;

BigInteger x = BigInteger.valueOf(-7);
BigInteger m = BigInteger.valueOf(3);

System.out.println(x.remainder(m)); // -1
System.out.println(x.mod(m));       // 2
~~~

`BigInteger.mod` yêu cầu modulus **dương**, và ném `ArithmeticException` nếu modulus không dương. Khi hệ thống định nghĩa một vòng quay thời gian/index dương, `Math.floorMod` (kiểu nguyên) hoặc `BigInteger.mod` thường phù hợp hơn remainder có dấu.

## 10. Chương trình Java 17+ tra bảng và kiểm chứng

Tạo tệp `NegativeDivisionRoundingTable.java`. Chương trình in bảng chia nguyên/dư, các chế độ làm tròn thập phân và đối chiếu những phép Math quan trọng.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class NegativeDivisionRoundingTable {

    static String rounded(String raw, RoundingMode mode) {
        try {
            return new BigDecimal(raw).setScale(0, mode).toPlainString();
        } catch (ArithmeticException ex) {
            return "ERR";
        }
    }

    public static void main(String[] args) {
        System.out.println("a b / % floorDiv floorMod");
        int[][] values = {
                { 7, 3 }, { -7, 3 }, { 7, -3 }, { -7, -3 },
                { 8, 3 }, { -8, 3 }, { 1, 3 }, { -1, 3 }
        };
        for (int[] pair : values) {
            int a = pair[0];
            int b = pair[1];
            System.out.printf("%d %d %d %d %d %d%n",
                    a, b, a / b, a % b,
                    Math.floorDiv(a, b), Math.floorMod(a, b));
        }

        System.out.println("mode -2.4 -2.5 -3.5");
        for (RoundingMode mode : RoundingMode.values()) {
            System.out.printf("%s %s %s %s%n",
                    mode,
                    rounded("-2.4", mode),
                    rounded("-2.5", mode),
                    rounded("-3.5", mode));
        }

        System.out.println("round(-2.5)=" + Math.round(-2.5));
        System.out.println("round(-3.5)=" + Math.round(-3.5));
        System.out.println("rint(-3.5)=" + Math.rint(-3.5));
        System.out.println("floor(-2.4)=" + Math.floor(-2.4));
        System.out.println("ceil(-2.4)=" + Math.ceil(-2.4));

        BigDecimal a = new BigDecimal("-7");
        BigDecimal b = new BigDecimal("3");
        System.out.println("BigDecimal quotient="
                + a.divideToIntegralValue(b).toPlainString());
        System.out.println("BigDecimal remainder="
                + a.remainder(b).toPlainString());
        System.out.println("BigDecimal rounded quotient="
                + a.divide(b, 2, RoundingMode.HALF_UP).toPlainString());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac NegativeDivisionRoundingTable.java
java NegativeDivisionRoundingTable
~~~

Stdout:

~~~text
a b / % floorDiv floorMod
7 3 2 1 2 1
-7 3 -2 -1 -3 2
7 -3 -2 1 -3 -2
-7 -3 2 -1 2 -1
8 3 2 2 2 2
-8 3 -2 -2 -3 1
1 3 0 1 0 1
-1 3 0 -1 -1 2
mode -2.4 -2.5 -3.5
UP -3 -3 -4
DOWN -2 -2 -3
CEILING -2 -2 -3
FLOOR -3 -3 -4
HALF_UP -2 -3 -4
HALF_DOWN -2 -2 -3
HALF_EVEN -2 -2 -4
UNNECESSARY ERR ERR ERR
round(-2.5)=-2
round(-3.5)=-3
rint(-3.5)=-4.0
floor(-2.4)=-3.0
ceil(-2.4)=-2.0
BigDecimal quotient=-2
BigDecimal remainder=-1
BigDecimal rounded quotient=-2.33
~~~

Dòng `UNNECESSARY ERR ERR ERR` biểu diễn **những trường hợp bị từ chối làm tròn**. Trong chương trình thực tế, đừng bỏ qua hoàn toàn ngoại lệ: nên trả lỗi validation theo hợp đồng, hoặc để ngoại lệ đi lên nơi có trách nhiệm xử lý. `rounded` bắt ngoại lệ chỉ để bài học có bảng đầu ra thống nhất.

## 11. Hướng dẫn chọn phép toán theo tình huống

| Bài toán | Chọn | Vì sao |
| --- | --- | --- |
| Cắt phần lẻ của thương nguyên | `/` | Hướng về 0 |
| Dư đi kèm phép chia nguyên thông thường | `%` | `a = (a/b)*b + a%b` |
| Chia số nguyên thành bucket có thể âm | `Math.floorDiv` | Bucket theo floor, nhất quán với trục số |
| Quay vòng index với kích thước dương | `Math.floorMod` | Dư không âm khi modulus dương |
| Làm tròn xuống về số nguyên theo trục số | `Math.floor` | Với số âm đi xa 0 nếu có phần lẻ |
| Làm tròn lên về số nguyên theo trục số | `Math.ceil` | Với số âm tiến về 0 nếu có phần lẻ |
| Gần nhất, tie thiên về +∞ theo `Math.round` | `Math.round` | Khác HALF_UP ở số âm tie |
| Gần nhất, tie chọn chẵn ở floating point | `Math.rint` | Kết quả kiểu `double` |
| Làm tròn số tiền/decimal đến số chữ số xác định | `BigDecimal.setScale` | Chọn chính sách `RoundingMode` rõ ràng |
| Thương nguyên và dư BigDecimal | `divideToIntegralValue`, `remainder` | Ngữ nghĩa cắt về 0 |
| Modulo dương với số nguyên rất lớn | `BigInteger.mod` | Yêu cầu modulus dương |

**Ví dụ lập nhóm thời gian:** nếu mỗi nhóm ứng với 10 giây theo mốc 0 và một sự kiện có offset -1 giây, `-1 / 10 == 0` sẽ đưa sự kiện vào nhóm 0 theo truncation, trong khi `Math.floorDiv(-1,10) == -1` đưa vào nhóm âm đúng theo khoảng `[-10,0)`. Khi định nghĩa các khoảng liên tiếp theo floor, `floorDiv` tránh lỗi quanh mốc 0.

**Ví dụ số dư kế toán:** `-7 % 3 == -1` là số dư mang dấu của số bị chia; nếu quy tắc nghiệp vụ cần “số bù còn thiếu để đạt bội số” phải định nghĩa một đại lượng khác, không chỉ đổi dấu tùy tiện hoặc `Math.abs(remainder)`.

## 12. Sai lầm thường gặp

1. **Gọi `/` là floor division.** Với `-7/3`, Java ra `-2`, không phải `-3`.
2. **Cho rằng `%` luôn không âm.** `-7%3` ra `-1`.
3. **Cho rằng `floorMod` luôn không âm.** Điều này chỉ bảo đảm với **modulus dương**; `floorMod(7,-3)=-2`.
4. **Dùng cast sang `int` để làm floor.** `(int)-2.7 == -2` vì cast cắt về 0; `Math.floor(-2.7)=-3.0`.
5. **Dùng `Math.round` như `RoundingMode.HALF_UP`.** `Math.round(-2.5)=-2` nhưng `BigDecimal("-2.5").setScale(0, HALF_UP)=-3`.
6. **Đánh đồng `BigDecimal.remainder` và modulo không âm.** `BigDecimal(-7).remainder(3)` vẫn là `-1`.
7. **Quên kiểu của kết quả.** `Math.floor` và `Math.ceil` trả `double`, `Math.round(float)` trả `int`, `Math.round(double)` trả `long`, còn `BigDecimal.setScale` trả `BigDecimal`.
8. **Chia nguyên rồi muốn khôi phục phần lẻ bằng cast.** `(double)(-7/3)` vẫn là `-2.0`.
9. **Bỏ qua trường hợp chia cho 0 và MIN_VALUE/-1.** Các trường hợp này cần kiểm thử riêng; trong đó MIN_VALUE/-1 có thể wrap thay vì exception.
10. **Dùng `double` để làm tròn số tiền chính xác.** Một số decimal như 0.1 không được biểu diễn chính xác trong binary64; hãy dùng `new BigDecimal("...")` và chính sách `RoundingMode` theo yêu cầu nghiệp vụ.

## 13. Bài tập tra bảng

Không chạy code trước; điền kiểu và kết quả theo nguyên tắc rồi dùng chương trình nhỏ để kiểm tra:

| STT | Biểu thức | Kết quả dự đoán |
| ---: | --- | --- |
| 1 | `-11 / 4` | ? |
| 2 | `-11 % 4` | ? |
| 3 | `Math.floorDiv(-11, 4)` | ? |
| 4 | `Math.floorMod(-11, 4)` | ? |
| 5 | `11 % -4` | ? |
| 6 | `Math.floorMod(11, -4)` | ? |
| 7 | `(int) -2.9` | ? |
| 8 | `Math.floor(-2.9)` | ? |
| 9 | `Math.ceil(-2.9)` | ? |
| 10 | `Math.round(-2.5)` | ? |
| 11 | `Math.rint(-2.5)` | ? |
| 12 | `new BigDecimal("-2.5").setScale(0, HALF_UP)` | ? |
| 13 | `new BigDecimal("-2.5").setScale(0, HALF_EVEN)` | ? |
| 14 | `new BigInteger("-11").mod(new BigInteger("4"))` | ? |

Đáp án (ở các câu BigDecimal/BigInteger, cần import kiểu và enum):

| STT | Kết quả | Giải thích |
| ---: | --- | --- |
| 1 | `-2` (`int`) | Thương nguyên cắt về 0 |
| 2 | `-3` (`int`) | `-11 = (-2)×4 - 3` |
| 3 | `-3` (`int`) | Floor của -2.75 |
| 4 | `1` (`int`) | `-11 = (-3)×4 + 1` |
| 5 | `3` (`int`) | Dư `%` cùng dấu số bị chia 11 |
| 6 | `-1` (`int`) | Với modulus âm, `floorMod` trả dư âm |
| 7 | `-2` (`int`) | Cast floating point về int cắt về 0 |
| 8 | `-3.0` (`double`) | Floor theo âm vô cực |
| 9 | `-2.0` (`double`) | Ceiling theo dương vô cực |
| 10 | `-2` (`long`) | `Math.round(double)` tie về +∞ |
| 11 | `-2.0` (`double`) | Tie chọn số chẵn |
| 12 | `-3` (`BigDecimal`) | HALF_UP tie xa số 0 |
| 13 | `-2` (`BigDecimal`) | HALF_EVEN chọn 2 chẵn |
| 14 | `1` (`BigInteger`) | Modulo dương trong `[0,4)` |

**Tóm tắt dễ nhớ:** `/` và `%` trên số nguyên là **truncation toward zero**; `floorDiv`/`floorMod` là **floor-based division**; `Math.floor`, `Math.ceil`, `Math.round`, `Math.rint` có các chính sách khác nhau với số âm; `BigDecimal` cho phép chỉ định rõ mode và scale. Khi viết code xử lý số âm, chọn chính sách theo định nghĩa toán học/kinh doanh, không chọn chỉ vì tên method nghe có vẻ đúng.
