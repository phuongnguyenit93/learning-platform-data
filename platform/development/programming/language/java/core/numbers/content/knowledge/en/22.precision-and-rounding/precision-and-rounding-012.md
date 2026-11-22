# Không mặc định `Math.round` tương đương mọi chế độ `HALF_UP`

## 1. Điều cần nhớ

Trong Java, **`Math.round` không phải tên gọi khác của `RoundingMode.HALF_UP`**. Hai cơ chế đều có thể cho kết quả giống nhau trong nhiều trường hợp, nhưng **khác nhau ở điểm đúng nửa khi giá trị âm**, khác loại dữ liệu đầu vào/đầu ra, cách xử lý độ chính xác và các giá trị đặc biệt.

- `Math.round(float)` trả về `int`; `Math.round(double)` trả về `long`. Nó chọn **số nguyên gần nhất**, và nếu nằm đúng giữa hai số nguyên thì chọn số lớn hơn, tức **hướng về dương vô cực** (`+∞`).
- `RoundingMode.HALF_UP` là quy tắc làm tròn dùng với những API như `BigDecimal.setScale`, `divide` hoặc `MathContext`. Nó chọn kết quả gần nhất; nếu **đúng nửa**, chọn kết quả **xa số 0 hơn**.
- `Math.round(-1.5) == -1` nhưng `new BigDecimal("-1.5").setScale(0, RoundingMode.HALF_UP)` cho `-2`. Đây là phản ví dụ đủ để bác bỏ kết luận hai cơ chế tương đương.

Mục tiêu là chọn **quy tắc nghiệp vụ** trước rồi mới chọn API, thay vì nhìn một vài ví dụ dương và suy rộng cho mọi đầu vào.

## 2. Quy tắc ở điểm đúng nửa: khác nhau chính xác ở đâu?

Xét số cần làm tròn đến số nguyên, hai số nguyên lân cận có khoảng cách bằng nhau ở đầu vào `n + 0.5`.

Với `Math.round`, tại điểm đúng nửa Java chọn số nguyên lớn hơn về mặt số học. Ví dụ `-2` lớn hơn `-3`, nên `Math.round(-2.5)` cho `-2`.

Với `HALF_UP`, “UP” trong tên của `RoundingMode` **không có nghĩa tăng giá trị về `+∞`**. Nó có nghĩa **tăng độ lớn tuyệt đối, tức đi xa số 0** khi gặp đúng nửa. Do đó `-2.5` thành `-3`.

| Giá trị đầu vào | `Math.round(double)` | `BigDecimal.setScale(0, HALF_UP)` | Nhận xét |
| ---: | ---: | ---: | --- |
| `2.4` | `2` | `2` | Cả hai chọn số gần nhất. |
| `2.5` | `3` | `3` | Đúng nửa dương: trùng kết quả. |
| `1.5` | `2` | `2` | Đúng nửa dương: trùng kết quả. |
| `0.5` | `1` | `1` | Đúng nửa dương: trùng kết quả. |
| `-0.5` | `0` | `-1` | Đúng nửa âm: **khác**. |
| `-1.5` | `-1` | `-2` | Đúng nửa âm: **khác**. |
| `-2.5` | `-2` | `-3` | Đúng nửa âm: **khác**. |
| `-2.4` | `-2` | `-2` | Không đúng nửa: cùng chọn số gần nhất. |

Các đầu vào `.5` trong bảng biểu diễn chính xác được bằng `double`, nên khác biệt này thực sự đến từ **chính sách xử lý điểm hòa**, không phải sai số dấu phẩy động.

Không thể giải thích `Math.round(x)` bằng “luôn làm tròn lên” vì `Math.round(2.1) == 2`, cũng không thể nói nó luôn làm tròn về phía số 0 vì `Math.round(-1.6) == -2`. Quy tắc đầy đủ là: **số nguyên gần nhất; nếu hòa, chọn số lớn hơn**.

Một cách nhớ đơn giản: với các đầu vào hữu hạn mà kết quả trong miền biểu diễn và không vướng chi tiết độ chính xác của phép cộng dấu phẩy động, quy tắc `Math.round` giống làm tròn đến số nguyên gần nhất với điểm hòa hướng về `+∞`. Không nên tự thay toàn bộ hiện thực bằng công thức dấu phẩy động `(long)Math.floor(x + 0.5)`: phép cộng `x + 0.5` còn chịu làm tròn nhị phân, và ép kiểu/giới hạn miền giá trị có những quy tắc riêng.

## 3. Phân biệt các `RoundingMode` dễ nhầm

Để so sánh cho công bằng, đặt cùng mục tiêu **scale = 0** trong `BigDecimal` (không còn chữ số thập phân):

| Chế độ | Quy tắc ở điểm đúng nửa | `2.5` | `-2.5` |
| --- | --- | ---: | ---: |
| `HALF_UP` | Xa số 0 | `3` | `-3` |
| `HALF_DOWN` | Về số 0 | `2` | `-2` |
| `HALF_EVEN` | Chọn láng giềng chẵn | `2` | `-2` |
| `UP` | Xa số 0 với mọi phần lẻ khác 0 | `3` | `-3` |
| `DOWN` | Về số 0 với mọi phần lẻ khác 0 | `2` | `-2` |
| `CEILING` | Hướng `+∞` | `3` | `-2` |
| `FLOOR` | Hướng `-∞` | `2` | `-3` |

Chú ý `CEILING` cũng không phải cách thay thế tổng quát cho `Math.round`: `CEILING` biến `2.1` thành `3`, còn `Math.round(2.1)` trả `2`. Tương tự, `FLOOR` không phải phép làm tròn gần nhất vì `Math.floor(-1.1) == -2.0`.

`HALF_EVEN` chỉ chọn số chẵn khi đúng nửa: `2.5 → 2`, `3.5 → 4`, `-2.5 → -2`, `-3.5 → -4`. Nó không cùng quy tắc với `Math.round`, và `Math.rint(double)` dù có xử lý điểm hòa theo số nguyên chẵn thì **trả `double`**, có thể giữ dấu của số 0, đồng thời vẫn chịu hạn chế biểu diễn nhị phân.

Từ “làm tròn lên” trong hội thoại thường mơ hồ: có thể chỉ `UP` (xa số 0), `CEILING` (về `+∞`) hoặc `HALF_UP` (chỉ xử lý điểm nửa). Trong mã, hãy dùng **tên chế độ cụ thể** thay cho cụm từ chung chung.

## 4. Khác biệt về API và kiểu dữ liệu

### 4.1. `Math.round` trả về kiểu nguyên cố định

Hai overload chuẩn là:

~~~java
int nearestInt = Math.round(2.5f);    // float -> int
long nearestLong = Math.round(2.5d);  // double -> long
~~~

`Math.round` không nhận `RoundingMode` hay số chữ số sau dấu phẩy. Nó làm tròn về **số nguyên**, không có phiên bản `Math.round(x, 2)` chuẩn nào trong JDK để làm tròn hai chữ số thập phân.

Việc trả về `int`/`long` cũng có hệ quả về **tràn miền giá trị**: kết quả vượt giới hạn sẽ bị chặn ở cực trị tương ứng, không thể mang mọi chữ số của đầu vào. Đây không phải là một phép kiểm tra số học chính xác hoặc một cơ chế báo lỗi vượt phạm vi.

### 4.2. `BigDecimal` có thể làm tròn ở scale hoặc precision

~~~java
BigDecimal amount = new BigDecimal("-2.5");
BigDecimal asInteger = amount.setScale(0, RoundingMode.HALF_UP);
// -3: trả về BigDecimal mới, amount không đổi.

BigDecimal price = new BigDecimal("12.345");
BigDecimal cents = price.setScale(2, RoundingMode.HALF_UP);
// 12.35: chính xác hai chữ số sau dấu phẩy.
~~~

`setScale(2, ...)` là yêu cầu **hai chữ số thập phân** (scale 2). Trong khi đó:

~~~java
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);
BigDecimal result = new BigDecimal("123.45").round(mc);
// 123: giữ 3 chữ số có nghĩa, không phải 3 chữ số sau dấu phẩy.
~~~

`MathContext` giới hạn **chữ số có nghĩa của kết quả**, nên `round(mc)` với precision 3 không tương đương `setScale(3, ...)`, cũng không tương đương `Math.round`.

Ở ví dụ nguồn decimal, ưu tiên `new BigDecimal("...")` để giữ chính xác giá trị văn bản. Khi đầu vào đã ở kiểu `double`, `BigDecimal.valueOf(value)` chuyển theo biểu diễn thập phân chuẩn của `Double.toString(value)`; đó là giá trị dựa trên **double đã có**, không phục hồi được thông tin đã mất trong các phép tính trước đó. `new BigDecimal(value)` lại biểu diễn chính xác giá trị nhị phân của `double`, có thể tạo ra chuỗi thập phân dài ngoài dự kiến.

## 5. Chương trình Java 17+ chạy được và đầu ra

Tạo file `RoundingComparison.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class RoundingComparison {
    public static void main(String[] args) {
        double[] examples = {
                2.5, -2.5, 2.4, -2.4,
                1.5, -1.5, 0.5, -0.5
        };

        for (double value : examples) {
            BigDecimal decimal = BigDecimal.valueOf(value);

            System.out.println(value
                    + " | Math.round=" + Math.round(value)
                    + " | HALF_UP=" + decimal.setScale(0, RoundingMode.HALF_UP)
                    + " | HALF_EVEN=" + decimal.setScale(0, RoundingMode.HALF_EVEN));
        }

        System.out.println("float -> int: " + Math.round(2.5f));
        System.out.println("double -> long: " + Math.round(2.5d));

        System.out.println("NaN: " + Math.round(Double.NaN));
        System.out.println("+Infinity: " + Math.round(Double.POSITIVE_INFINITY));
        System.out.println("-Infinity: " + Math.round(Double.NEGATIVE_INFINITY));
        System.out.println("large: " + Math.round(1e30));

        double scaled = 1.005 * 100;
        System.out.println("scaled = " + scaled);
        System.out.println("scaled Math.round = " + Math.round(scaled) / 100.0);

        System.out.println("decimal HALF_UP = "
                + new BigDecimal("1.005")
                    .setScale(2, RoundingMode.HALF_UP).toPlainString());
        System.out.println("decimal HALF_EVEN = "
                + new BigDecimal("1.005")
                    .setScale(2, RoundingMode.HALF_EVEN).toPlainString());

        System.out.println("rint 2.5=" + Math.rint(2.5)
                + ", rint -1.5=" + Math.rint(-1.5));
    }
}
~~~

Chạy:

~~~bash
javac RoundingComparison.java
java RoundingComparison
~~~

Kết quả:

~~~text
2.5 | Math.round=3 | HALF_UP=3 | HALF_EVEN=2
-2.5 | Math.round=-2 | HALF_UP=-3 | HALF_EVEN=-2
2.4 | Math.round=2 | HALF_UP=2 | HALF_EVEN=2
-2.4 | Math.round=-2 | HALF_UP=-2 | HALF_EVEN=-2
1.5 | Math.round=2 | HALF_UP=2 | HALF_EVEN=2
-1.5 | Math.round=-1 | HALF_UP=-2 | HALF_EVEN=-2
0.5 | Math.round=1 | HALF_UP=1 | HALF_EVEN=0
-0.5 | Math.round=0 | HALF_UP=-1 | HALF_EVEN=0
float -> int: 3
double -> long: 3
NaN: 0
+Infinity: 9223372036854775807
-Infinity: -9223372036854775808
large: 9223372036854775807
scaled = 100.49999999999999
scaled Math.round = 1.0
decimal HALF_UP = 1.01
decimal HALF_EVEN = 1.00
rint 2.5=2.0, rint -1.5=-2.0
~~~

**Đọc output:** Bốn hàng `-2.5`, `-1.5`, `-0.5` và `0.5` cho thấy chính sách làm tròn khác nhau. Dòng `0.5` còn giúp phân biệt `HALF_UP` với `HALF_EVEN`. `Math.rint` là ví dụ bổ sung về quy tắc “tie to even”; khác cả kiểu trả về so với `Math.round`.

## 6. Điểm khó: nhị phân `double` khiến “.5” tưởng tượng không đúng .5

Các số thập phân như `0.1`, `1.005` thường **không có biểu diễn chính xác bằng `double`**. Vì vậy kết quả của phép nhân, phép chia trước khi làm tròn có thể nằm hơi lệch phía trên hoặc dưới điểm hòa thập phân mà mắt thường thấy.

Một cách viết phổ biến để lấy hai chữ số sau dấu phẩy:

~~~java
double rounded = Math.round(1.005 * 100) / 100.0;
~~~

Chương trình ở trên cho thấy:

~~~text
scaled = 100.49999999999999
scaled Math.round = 1.0
decimal HALF_UP = 1.01
~~~

`1.005 * 100` dưới dạng `double` tạo `100.49999999999999`, **nhỏ hơn 100.5**, nên `Math.round` trả `100` và sau chia là `1.0`. Ngược lại `new BigDecimal("1.005")` giữ chính xác đầu vào thập phân, nên `setScale(2, HALF_UP)` trả `1.01`. Đây là **hai vấn đề tách biệt**:

1. **Quy tắc hòa nửa:** `Math.round` chọn hướng `+∞`; `HALF_UP` chọn xa số 0.
2. **Biểu diễn đầu vào:** phép tính `double` có thể khiến một điểm hòa thập phân không còn thực sự ở đúng nửa.

Không thể kết luận mọi biểu thức `Math.round(value * 100) / 100.0` đều sai: nó có thể phù hợp khi kết quả gần đúng kiểu `double` là chấp nhận được, phạm vi nhỏ và quy tắc ở điểm nửa đã được thỏa thuận. Nhưng với giá tiền hoặc quy định làm tròn thập phân, cách này thường không diễn đạt đúng hợp đồng nghiệp vụ, chưa kể nguy cơ tràn `int`/`long` nếu nhân hệ số lớn.

Khi dùng `BigDecimal` cho tiền hoặc định lượng thập phân theo hợp đồng, hãy xác định rõ: **đầu vào từ đâu, bao nhiêu chữ số sau dấu phẩy, làm tròn theo mode nào, và ở bước nào**. Ví dụ:

~~~java
BigDecimal amount = new BigDecimal("1.005");
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP);
// 1.01
~~~

Nếu phép toán trước đó đã làm việc trên `double` và bị mất chính xác, chỉ chuyển sang `BigDecimal` ở bước cuối **không bảo đảm** khôi phục giá trị thập phân ban đầu.

## 7. `NaN`, vô cực, số rất lớn và số âm bằng 0

Tài liệu Java quy định các trường hợp đặc biệt cho `Math.round`:

- Đầu vào `NaN` → `0`.
- `Math.round(double)` với `+Infinity` hoặc giá trị quá lớn dương → `Long.MAX_VALUE`; với `-Infinity` hoặc quá lớn âm → `Long.MIN_VALUE`.
- `Math.round(float)` áp dụng tương tự với `Integer.MAX_VALUE` và `Integer.MIN_VALUE`.
- `Math.round(-0.0)` trả số nguyên `0`; kiểu nguyên không giữ dấu của zero.

Đây là **giá trị trả về theo đặc tả**, không phải ngoại lệ và cũng không chứng minh rằng đầu vào hợp lệ cho nghiệp vụ. Ví dụ, `Math.round(Double.NaN) == 0` có thể làm mất tín hiệu dữ liệu lỗi nếu bạn coi `0` là một số bình thường.

Đầu vào cần làm tròn chính xác sang `long`? Với `BigDecimal`, sau khi làm tròn theo mode đã chọn, `longValueExact()` ném `ArithmeticException` nếu giá trị không thể biểu diễn chính xác dưới dạng `long`. Có thể kiểm tra rõ `Double.isFinite(value)` trước khi đưa `double` qua pipeline. Hãy chọn rõ chính sách xử lý vô cực, `NaN` và quá miền thay vì dựa ngầm vào cơ chế chặn của `Math.round`.

## 8. Chọn phương án theo yêu cầu

| Yêu cầu | API thường phù hợp | Điểm cần xác nhận |
| --- | --- | --- |
| Giá trị `float`/`double` sang số nguyên gần nhất, đúng nửa hướng `+∞` | `Math.round(value)` | Nhận `int` hoặc `long`; kiểm tra `NaN`, vô cực và quá miền nếu dữ liệu yêu cầu. |
| Thập phân đúng nửa **xa số 0** | `BigDecimal.setScale(scale, HALF_UP)` | Scale và cách tạo `BigDecimal` phải phản ánh đầu vào mong muốn. |
| Thập phân đúng nửa về số 0 | `setScale(scale, HALF_DOWN)` | Khác `Math.round` ở điểm nửa dương. |
| Thập phân đúng nửa chọn chữ số chẵn | `setScale(scale, HALF_EVEN)` | Dùng khi hợp đồng nghiệp vụ cho phép; không mặc định cho mọi ứng dụng. |
| Mọi phần lẻ đều làm tròn về `+∞` | `CEILING` hoặc `Math.ceil` theo kiểu đầu vào | Khác làm tròn đến số gần nhất. |
| Làm tròn đến 2 chữ số **sau dấu phẩy** | `setScale(2, mode)` | Không nhầm với `MathContext(2, mode)` chỉ 2 chữ số có nghĩa. |
| Cần giữ chữ số có nghĩa tối đa theo phép toán thập phân | `MathContext(precision, mode)` | Precision khác scale; không tương đương `Math.round`. |
| Phải phát hiện làm tròn ngoài yêu cầu | `setScale(scale, UNNECESSARY)` | Ném ngoại lệ nếu loại bỏ chữ số khác 0. |

Trường hợp chuyển từ decimal đã làm tròn về kiểu nguyên:

~~~java
BigDecimal input = new BigDecimal("-2.5");
long result = input.setScale(0, RoundingMode.HALF_UP).longValueExact();
// result == -3L
~~~

Đoạn này phải nằm trong lớp/phương thức hợp lệ có các import của `java.math`; đây là **đoạn minh họa**, không phải chương trình độc lập.

## 9. Checklist review và lỗi thường gặp

1. **Chỉ thử số dương** như `1.5`, `2.5` rồi kết luận `Math.round == HALF_UP`. Phải thử ít nhất `-0.5`, `-1.5`, `-2.5`.
2. **Hiểu “UP” là hướng số lớn hơn.** `HALF_UP` đi xa số 0 khi đúng nửa; `CEILING` mới là hướng `+∞`.
3. **Viết `Math.round(x * 100) / 100` và tưởng kết quả hai chữ số thập phân kiểu decimal.** `/ 100` với hai toán hạng nguyên có thể còn chia nguyên; `/ 100.0` cho `double`, vẫn có sai số nhị phân.
4. **Cho rằng `Math.round` nhận mọi độ chính xác.** Nó chỉ làm tròn `float`/`double` sang `int`/`long`.
5. **Bỏ qua `NaN`, vô cực hoặc tràn miền.** API trả 0/các cực trị thay vì báo lỗi, có thể che khuất dữ liệu bất thường.
6. **Dùng `new BigDecimal(double)` vô điều kiện.** Constructor này phản ánh đúng giá trị nhị phân của `double`, không nhất thiết là chuỗi thập phân người dùng nhìn thấy.
7. **So `Math.round` với `setScale(2)` rồi quy khác biệt cho rounding mode.** Phải đồng nhất đích làm tròn (ở ví dụ đầu bài là scale 0) trước khi so sánh.
8. **Làm tròn ở mỗi bước không có chủ đích.** Kết quả có thể khác khi chỉ làm tròn một lần ở cuối; cần quy định rõ thời điểm làm tròn.
9. **Nhầm `Math.rint` là `Math.round`.** Cả hai nhận `double`, nhưng `rint` trả `double` và chọn số chẵn ở điểm hòa, `round` trả `long` và chọn về `+∞` ở điểm hòa.

## 10. Bài tập tự kiểm tra

**Bài 1.** Dự đoán `Math.round(-3.5)` và `new BigDecimal("-3.5").setScale(0, HALF_UP)`.

**Đáp án:** `-3` và `-4`. Đầu vào cách đều `-3` và `-4`, nhưng chọn hướng khác nhau.

**Bài 2.** Hai biểu thức này có luôn tương đương không?

~~~java
Math.round(x)
BigDecimal.valueOf(x).setScale(0, RoundingMode.HALF_UP)
~~~

**Đáp án:** Không. Chúng khác ở các giá trị âm đúng nửa; ngoài ra khác loại kết quả và xử lý giá trị đặc biệt, miền số, precision/biểu diễn.

**Bài 3.** Tại sao `Math.round(1.005 * 100) / 100.0` có thể ra `1.0`, còn `new BigDecimal("1.005").setScale(2, HALF_UP)` ra `1.01`?

**Đáp án:** Phép nhân trên `double` tạo `100.49999999999999`, nhỏ hơn điểm nửa `100.5`; còn chuỗi thập phân trong `BigDecimal` giữ giá trị `1.005` chính xác.

**Bài 4.** Muốn làm tròn `-2.5` về `-2` theo quy tắc chọn số nguyên gần nhất và hòa về phía `+∞`, gọi API nào?

**Đáp án:** `Math.round(-2.5d)`. Nếu muốn trình bày quy tắc cho decimal, có thể tính bằng `BigDecimal` với một giải pháp đặt mode phù hợp theo điều kiện; không được mặc định gọi `HALF_UP`.

## 11. Tài liệu Java để đối chiếu

- [`Math.round(float)`, `Math.round(double)` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#round(double)): định nghĩa số nguyên gần nhất và trường hợp hòa hướng `+∞`; các trường hợp đặc biệt.
- [`RoundingMode` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): mô tả `HALF_UP`, `HALF_DOWN`, `HALF_EVEN`, `UP`, `DOWN`, `CEILING` và `FLOOR`.
- [`BigDecimal` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `setScale`, `round`, `valueOf` và `longValueExact`.

**Ghi nhớ:** `Math.round` = gần nhất, **hòa về `+∞`**; `HALF_UP` = gần nhất, **hòa xa số 0**. Với số âm ở điểm `.5`, kết quả thường khác. Hãy kiểm soát thêm kiểu dữ liệu và biểu diễn nhị phân trước khi dùng một phép làm tròn để thay thế phép khác.
