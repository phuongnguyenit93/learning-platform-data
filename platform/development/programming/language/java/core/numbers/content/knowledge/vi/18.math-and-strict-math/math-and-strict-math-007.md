# ceil, floor, rint và round trong Java: bốn cách làm tròn dễ nhầm

## 1. Mục tiêu

Java cung cấp nhiều phương thức liên quan đến làm tròn trong hai lớp `java.lang.Math` và `java.lang.StrictMath`. Bốn tên thường gặp nhất là `ceil`, `floor`, `rint` và `round`. Chúng **không tương đương**, dù đôi khi cùng trả một kết quả.

Sau bài học, bạn sẽ có thể:

- Giải thích hướng làm tròn của từng phương thức bằng định nghĩa toán học.
- Phân biệt quy tắc xử lý số nằm **đúng giữa hai số nguyên**: `rint` dùng *ties to even*, còn `round` ưu tiên số nguyên **về phía dương** khi có hai lựa chọn cách đều.
- Dự đoán kết quả với số âm, `-0.0`, giá trị rất lớn, `NaN` và `Infinity`.
- Chọn phương thức đúng theo **kiểu trả về**: `ceil`/`floor`/`rint` trả `double`; `round(float)` trả `int` và `round(double)` trả `long`.
- Biết khi nào cần `BigDecimal` và `RoundingMode` thay vì áp dụng `Math.round` cho các giá trị tài chính.
- Tránh mất thông tin khi ép kiểu, chuyển đổi số và làm tròn nhiều bước.

Các ví dụ chính chạy trên **Java 17+**, không dùng preview. Phần lớn quy tắc cũng áp dụng cho `StrictMath` tương ứng.

## 2. Trước tiên: làm tròn tới số nguyên là gì?

Giả sử có một số thực `x` và ta muốn nhận một giá trị nguyên gần hoặc liên quan tới `x`. Có nhiều quy tắc hợp lý nhưng **phải xác định quy tắc trước khi tính**.

Ví dụ số `2.7`:

- Số nguyên lớn hơn hoặc bằng nhỏ nhất là 3.
- Số nguyên nhỏ hơn hoặc bằng lớn nhất là 2.
- Số nguyên gần nhất là 3.

Ví dụ số `-2.7`:

- Số nguyên lớn hơn hoặc bằng nhỏ nhất là **−2**.
- Số nguyên nhỏ hơn hoặc bằng lớn nhất là **−3**.
- Số nguyên gần nhất là **−3**.

Đây là lý do các cách nói chung như “làm tròn lên” hoặc “làm tròn xuống” rất dễ gây hiểu nhầm với **số âm**. Trong Java, hãy dùng các định nghĩa hình thức:

| Phương thức | Quy tắc chính | Kết quả toán học với 2.7 | Với −2.7 |
| --- | --- | --- | --- |
| `Math.ceil(x)` | Số nguyên nhỏ nhất **≥ x** | 3 | −2 |
| `Math.floor(x)` | Số nguyên lớn nhất **≤ x** | 2 | −3 |
| `Math.rint(x)` | Số nguyên gần nhất; hòa thì chọn **chẵn** | 3 | −3 |
| `Math.round(x)` | Số nguyên gần nhất; hòa thì chọn phía **+∞** | 3 | −3 |

Bảng trên nói về **giá trị toán học**. Về kiểu Java, ba phương thức đầu trả giá trị nguyên **ở dạng `double`**, ví dụ `3.0`; `Math.round(double)` trả số nguyên primitive `long`, ví dụ `3L`.

## 3. Math.ceil(double): hướng về dương vô cực

`Math.ceil(double a)` trả về giá trị `double` bằng số nguyên toán học **nhỏ nhất không bé hơn** đối số.

\[
\operatorname{ceil}(x)=\min\{n\in\mathbb Z:n\ge x\}
\]

~~~java
System.out.println(Math.ceil(2.1));  // 3.0
System.out.println(Math.ceil(2.9));  // 3.0
System.out.println(Math.ceil(-2.1)); // -2.0
System.out.println(Math.ceil(-2.9)); // -2.0
System.out.println(Math.ceil(3.0));  // 3.0
~~~

Các đoạn ngắn như trên được đặt bên trong một phương thức; chương trình độc lập có trong phần 10.

**Điểm cần nhớ:** đối với số âm, `ceil` có thể làm **giảm độ lớn tuyệt đối**, vì hướng làm tròn là hướng tới `+∞`, không phải “ra xa số 0”.

Ví dụ `-2.9` nằm giữa `-3` và `-2`; số nguyên nhỏ nhất không bé hơn `-2.9` là `-2`.

### Zero có dấu

Java `double` phân biệt `+0.0` và `-0.0`. Theo hợp đồng `Math.ceil`, đối số âm lớn hơn `-1.0` nhưng nhỏ hơn `0.0` cho kết quả **`-0.0`**:

~~~java
System.out.println(Math.ceil(-0.3)); // -0.0
System.out.println(Math.ceil(+0.3)); // 1.0
~~~

Dù `-0.0 == 0.0` là true, dấu của zero có thể quan sát khi in hoặc lấy nghịch đảo (`1.0 / -0.0` là `-Infinity`). Nếu ứng dụng không quan tâm tới dấu zero, có thể chuẩn hóa sau khi làm tròn một cách có chủ đích.

## 4. Math.floor(double): hướng về âm vô cực

`Math.floor(double a)` trả về số nguyên toán học **lớn nhất không vượt quá** đối số, nhưng kiểu kết quả vẫn là `double`.

\[
\operatorname{floor}(x)=\max\{n\in\mathbb Z:n\le x\}
\]

~~~java
System.out.println(Math.floor(2.1));  // 2.0
System.out.println(Math.floor(2.9));  // 2.0
System.out.println(Math.floor(-2.1)); // -3.0
System.out.println(Math.floor(-2.9)); // -3.0
System.out.println(Math.floor(-0.0)); // -0.0
~~~

Với số âm, `floor` thường làm **tăng độ lớn tuyệt đối**, vì nó đi về `-∞`. Ví dụ `floor(-2.1) == -3.0`, không phải `-2.0`.

### floor khác ép kiểu nguyên

Ép `double` sang `int` hoặc `long` (trong miền thông thường) loại bỏ phần thập phân theo hướng **về 0**, không phải về âm vô cực:

~~~java
double x = -2.9;
System.out.println((int) x);       // -2
System.out.println(Math.floor(x)); // -3.0
~~~

Nếu bạn cần chia một trục tọa độ âm thành các ô dạng `floor(x / cellSize)`, sự khác biệt này đặc biệt quan trọng. Dùng ép kiểu nguyên khi thực sự cần bỏ phần thập phân theo hướng 0; dùng `floor` khi muốn lấy biên dưới toán học.

**Chú ý:** ép kiểu số thực thành `int`/`long` còn có các quy tắc riêng cho `NaN` và giá trị vượt miền. Không thay thế `floor` bằng phép cast nếu muốn giữ đúng quy tắc toán học và xử lý giá trị đặc biệt.

## 5. Math.rint(double): số nguyên gần nhất, hòa thì chọn chẵn

`Math.rint(double a)` trả `double` là giá trị nguyên gần nhất với đối số. Nếu có **hai giá trị nguyên cách đều**, nó chọn giá trị **chẵn** (*round half to even*, còn gọi là *ties to even* hoặc *banker's rounding*).

~~~java
System.out.println(Math.rint(2.3));  // 2.0
System.out.println(Math.rint(2.7));  // 3.0
System.out.println(Math.rint(2.5));  // 2.0
System.out.println(Math.rint(3.5));  // 4.0
System.out.println(Math.rint(-2.5)); // -2.0
System.out.println(Math.rint(-3.5)); // -4.0
~~~

Vì 2 và 4 là số chẵn, các điểm giữa `2.5` và `3.5` được xử lý khác nhau. Với số âm, `-2` và `-4` vẫn là các số chẵn theo khái niệm số nguyên.

### Tại sao chọn số chẵn khi hòa?

Chọn chẵn làm giảm xu hướng sai lệch một phía khi rất nhiều trường hợp **đúng giữa** hai số nguyên được làm tròn. Nhưng điều đó **không đảm bảo** tổng một tập dữ liệu bất kỳ sẽ không có sai số hoặc không có bias: độ phân bố dữ liệu và cách thực hiện phép tính vẫn quan trọng.

Ví dụ, với các giá trị đúng nửa nguyên liên tiếp:

| Đầu vào | Hai ứng viên gần nhất | Kết quả `rint` |
| --- | --- | --- |
| 1.5 | 1 hoặc 2 | 2.0 |
| 2.5 | 2 hoặc 3 | 2.0 |
| 3.5 | 3 hoặc 4 | 4.0 |
| 4.5 | 4 hoặc 5 | 4.0 |
| −1.5 | −2 hoặc −1 | −2.0 |
| −2.5 | −3 hoặc −2 | −2.0 |
| −3.5 | −4 hoặc −3 | −4.0 |

### rint trả double, không phải int hoặc long

~~~java
double nearest = Math.rint(2.5); // 2.0
// int n = Math.rint(2.5);       // lỗi biên dịch: double không tự thành int
~~~

Nếu cần `int`, hãy kiểm tra tính hữu hạn và miền trước khi chuyển:

~~~java
double nearest = Math.rint(input);
if (!Double.isFinite(nearest)
        || nearest < Integer.MIN_VALUE
        || nearest > Integer.MAX_VALUE) {
    throw new IllegalArgumentException("Rounded value outside int range");
}
int count = (int) nearest;
~~~

Đây là đoạn minh họa bên trong một phương thức có biến `input`. Kiểm tra trên đảm bảo kết quả hữu hạn và trong miền `int`; yêu cầu miền nghiệp vụ (ví dụ `count >= 0`) vẫn phải kiểm tra riêng.

### Điểm đặc biệt của −0.5

`Math.rint(-0.5)` trả **`-0.0`** theo quy tắc hòa chọn số nguyên chẵn (0) và giữ dấu zero. Không nên chuyển ngay kết quả sang `int` rồi cho rằng chưa có khác biệt về dấu:

~~~java
System.out.println(Math.rint(-0.5)); // -0.0
~~~

## 6. Math.round(float) và Math.round(double): gần nhất, hòa hướng dương

Khác ba phương thức trước, `Math.round` có **hai overload**:

~~~java
int roundedFloat = Math.round(2.5f);
long roundedDouble = Math.round(2.5);
~~~

Chữ ký:

| Overload | Tham số | Kiểu trả về |
| --- | --- | --- |
| `Math.round(float a)` | `float` | `int` |
| `Math.round(double a)` | `double` | `long` |

Quy tắc là chọn số nguyên gần nhất; **nếu hai số nguyên cách đều**, chọn số nguyên hướng về **dương vô cực**.

~~~java
System.out.println(Math.round(2.5));   // 3 (long)
System.out.println(Math.round(3.5));   // 4 (long)
System.out.println(Math.round(-2.5));  // -2 (long)
System.out.println(Math.round(-3.5));  // -3 (long)
System.out.println(Math.round(-0.5));  // 0 (long)
~~~

Đối với `-2.5`, hai số nguyên cách đều là `-3` và `-2`. Số ở **hướng dương hơn** là `-2`, do đó `Math.round(-2.5) == -2L`.

**Đừng mô tả `Math.round` đơn giản là “làm tròn half away from zero”.** Với số âm đúng nửa, `Math.round` chọn hướng `+∞` nên `-2.5` thành `-2` chứ không phải `-3`.

### round khác rint tại tie

~~~java
System.out.println(Math.rint(2.5));  // 2.0 (double)
System.out.println(Math.round(2.5)); // 3 (long)

System.out.println(Math.rint(-0.5));  // -0.0 (double)
System.out.println(Math.round(-0.5)); // 0 (long)
~~~

Khi chọn phương thức, luôn xem cả **quy tắc hòa** lẫn **kiểu dữ liệu đầu ra**.

## 7. Bảng so sánh các trường hợp dễ nhầm

Các ô trong ba cột `ceil`/`floor`/`rint` dùng biểu diễn `double`; cột `round` dùng `long`.

| `x` | `ceil(x)` | `floor(x)` | `rint(x)` | `round(x)` |
| ---: | ---: | ---: | ---: | ---: |
| 2.1 | 3.0 | 2.0 | 2.0 | 2 |
| 2.5 | 3.0 | 2.0 | 2.0 | 3 |
| 3.5 | 4.0 | 3.0 | 4.0 | 4 |
| −2.1 | −2.0 | −3.0 | −2.0 | −2 |
| −2.5 | −2.0 | −3.0 | −2.0 | −2 |
| −3.5 | −3.0 | −4.0 | −4.0 | −3 |
| −0.5 | −0.0 | −1.0 | −0.0 | 0 |
| 0.0 | 0.0 | 0.0 | 0.0 | 0 |
| −0.0 | −0.0 | −0.0 | −0.0 | 0 |

Kết luận từ bảng:

1. `ceil`/`floor` luôn theo **hướng trên/dưới toán học**, không phải hướng xa/gần zero.
2. `rint` và `round` thường cùng kết quả nếu không đúng điểm giữa.
3. Khi đúng điểm giữa, `rint` chọn số chẵn; `round` chọn phía dương.
4. `round` luôn trả một giá trị primitive **nguyên** nên không bảo toàn được `-0.0`.
5. Nếu đầu vào không phải một số hữu hạn hoặc đã quá lớn, phải xét thêm các quy tắc ở phần 8.

## 8. NaN, Infinity, signed zero và giá trị vượt miền

### 8.1. ceil, floor và rint giữ các giá trị đặc biệt

Đối với `Math.ceil`, `Math.floor` và `Math.rint`:

- Nếu tham số là `NaN`, kết quả là `NaN`.
- Nếu tham số là `+Infinity` hoặc `-Infinity`, kết quả là chính infinity đó.
- Nếu tham số là `+0.0` hoặc `-0.0`, kết quả giữ zero với dấu tương ứng.
- Nếu đã là số nguyên toán học dưới dạng `double`, không có phần thập phân để làm tròn; giá trị giữ nguyên.

~~~java
System.out.println(Math.ceil(Double.NaN));              // NaN
System.out.println(Math.floor(Double.POSITIVE_INFINITY)); // Infinity
System.out.println(Math.rint(Double.NEGATIVE_INFINITY));  // -Infinity
System.out.println(Math.floor(-0.0));                   // -0.0
~~~

Những phương thức này có thể trả `double` với giá trị rất lớn lớn hơn giới hạn `long` mà không cần ép về số nguyên, do bản thân kiểu trả về vẫn là `double`.

### 8.2. round chuyển sang kiểu số nguyên có miền hữu hạn

`Math.round(double)` trả `long`; `Math.round(float)` trả `int`. Chúng có các quy tắc được định nghĩa rõ khi đầu vào không thể làm tròn vào miền số nguyên đích:

- `NaN` → `0` (kiểu `int` hoặc `long` tùy overload).
- `+Infinity` hoặc giá trị quá lớn về phía dương → `Integer.MAX_VALUE` / `Long.MAX_VALUE`.
- `-Infinity` hoặc giá trị quá lớn về phía âm → `Integer.MIN_VALUE` / `Long.MIN_VALUE`.
- `-0.0` → `0` (không giữ được dấu zero).

~~~java
System.out.println(Math.round(Double.NaN));             // 0
System.out.println(Math.round(Double.POSITIVE_INFINITY)); // 9223372036854775807
System.out.println(Math.round(Double.NEGATIVE_INFINITY)); // -9223372036854775808
System.out.println(Math.round(Float.POSITIVE_INFINITY)); // 2147483647
System.out.println(Math.round(Float.NEGATIVE_INFINITY)); // -2147483648
~~~

**Rủi ro:** `Math.round` **không báo lỗi** nếu gặp `NaN` hoặc số vượt miền; nó có thể trả về 0 hoặc cực trị của kiểu nguyên. Nếu 0, `Integer.MAX_VALUE` hoặc `Long.MAX_VALUE` là các giá trị hợp lệ trong nghiệp vụ, bạn có thể vô tình chấp nhận số sai mà không phát hiện.

Với dữ liệu người dùng/cấu hình, nên kiểm tra `Double.isFinite` hoặc `Float.isFinite`, giới hạn miền và kiểm tra quy tắc làm tròn trước khi lưu kết quả.

### 8.3. Mất độ chính xác trước khi làm tròn

`double` có khoảng 53 bit precision có nghĩa. Những số nguyên lớn hơn `2^53` không phải lúc nào cũng được biểu diễn chính xác, nên `Math.round` **không thể khôi phục** chữ số đã mất khi chuỗi decimal hoặc phép toán bị làm tròn sang binary64 trước đó.

~~~java
double input = Double.parseDouble("9007199254740993");
System.out.println(input);          // 9.007199254740992E15
System.out.println(Math.round(input)); // 9007199254740992
~~~

Nếu dữ liệu cần là một số nguyên chính xác, ưu tiên `Long.parseLong` hoặc `BigInteger` từ **chuỗi gốc**, không parse sang `double` rồi round.

## 9. ceil/floor/rint và ép kiểu: mục đích hoàn toàn khác

Ép kiểu Java từ `double` sang `int`/`long` thực hiện chuyển đổi về miền số nguyên; với các giá trị hữu hạn có phần thập phân trong miền thông thường, phần thập phân bị cắt **về 0**.

~~~java
double positive = 2.8;
double negative = -2.8;

System.out.println((int) positive);  // 2
System.out.println((int) negative);  // -2
System.out.println(Math.floor(negative)); // -3.0
System.out.println(Math.ceil(negative));  // -2.0
~~~

Không nên dùng `(int) Math.ceil(x)` khi không biết miền x; kết quả `ceil` vẫn là `double` và bước cast có thể xử lý cực trị/NaN bằng quy tắc conversion riêng, làm mất thông tin. Nếu muốn kết quả `int` từ một phép round, hãy validate tính hữu hạn, miền và ngữ nghĩa trước.

### Chọn floor cho chỉ số ô trên trục âm

Giả sử bạn chia mặt phẳng thành các ô chiều rộng 10, và ô chứa `x` được đánh số bằng `floor(x / 10)`:

~~~java
double coordinate = -1.0;
int cell = (int) Math.floor(coordinate / 10.0);
System.out.println(cell); // -1
~~~

Nếu thay bằng `(int) (coordinate / 10.0)`, bạn nhận 0, sai ý nghĩa vùng ở phía âm. Ví dụ này có miền nhỏ được kiểm soát; với tọa độ ngoài miền int, cần kiểm tra trước khi cast.

## 10. Chương trình Java 17+ đầy đủ, có kết quả chính xác

Tạo tệp `RoundingMethodsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class RoundingMethodsDemo {
    private static void compare(double x) {
        System.out.println(
                "x=" + x +
                " ceil=" + Math.ceil(x) +
                " floor=" + Math.floor(x) +
                " rint=" + Math.rint(x) +
                " round=" + Math.round(x));
    }

    public static void main(String[] args) {
        compare(2.5);
        compare(3.5);
        compare(-2.5);
        compare(-3.5);
        compare(-0.5);

        System.out.println("round(float)=" + Math.round(2.5f));
        System.out.println("round(double)=" + Math.round(2.5));
        System.out.println("rint(2.5)=" + Math.rint(2.5));

        System.out.println("round(NaN)=" + Math.round(Double.NaN));
        System.out.println("round(+Infinity)=" +
                Math.round(Double.POSITIVE_INFINITY));
        System.out.println("round(-Infinity)=" +
                Math.round(Double.NEGATIVE_INFINITY));

        System.out.println("ceil(-0.3)=" + Math.ceil(-0.3));
        System.out.println("strict rint=" + StrictMath.rint(2.5));

        BigDecimal tie = new BigDecimal("-2.5");
        System.out.println("HALF_UP=" +
                tie.setScale(0, RoundingMode.HALF_UP));
        System.out.println("HALF_EVEN=" +
                tie.setScale(0, RoundingMode.HALF_EVEN));
    }
}
~~~

Biên dịch trên Java 17:

~~~bash
javac --release 17 RoundingMethodsDemo.java
java RoundingMethodsDemo
~~~

Stdout:

~~~text
x=2.5 ceil=3.0 floor=2.0 rint=2.0 round=3
x=3.5 ceil=4.0 floor=3.0 rint=4.0 round=4
x=-2.5 ceil=-2.0 floor=-3.0 rint=-2.0 round=-2
x=-3.5 ceil=-3.0 floor=-4.0 rint=-4.0 round=-3
x=-0.5 ceil=-0.0 floor=-1.0 rint=-0.0 round=0
round(float)=3
round(double)=3
rint(2.5)=2.0
round(NaN)=0
round(+Infinity)=9223372036854775807
round(-Infinity)=-9223372036854775808
ceil(-0.3)=-0.0
strict rint=2.0
HALF_UP=-3
HALF_EVEN=-2
~~~

Giải thích:

1. Với `2.5`, `rint` trả 2.0 do chọn chẵn; `round` trả 3 vì hướng dương ở điểm hòa.
2. Với `-3.5`, `rint` trả −4.0 (chẵn), trong khi `round` trả −3 (phía dương).
3. Với `-0.5`, `ceil` và `rint` giữ dấu zero âm; `round` trả số nguyên 0.
4. `Math.round(double)` có kiểu `long` và không biểu diễn `NaN`/`Infinity`; kết quả được quy định là 0 hoặc giới hạn tương ứng.
5. `StrictMath.rint(2.5)` có cùng quy tắc ties-to-even.
6. `RoundingMode.HALF_UP` làm tròn điểm giữa **ra xa 0**, nên −2.5 thành −3; `RoundingMode.HALF_EVEN` chọn chẵn nên −2.5 thành −2.

Đây là chương trình độc lập dùng `Math`, `StrictMath` và `BigDecimal` trên Java 17. Nó không dựa trên locale hoặc cấu hình hệ điều hành cho cách in số trong các biểu thức trên.

## 11. StrictMath so với Math đối với bốn phương thức này

Hai lớp đều nằm trong `java.lang` nên không cần thêm import:

~~~java
double a = Math.ceil(-1.2);
double b = StrictMath.ceil(-1.2);

double c = Math.rint(2.5);
double d = StrictMath.rint(2.5);

long e = Math.round(-2.5);
long f = StrictMath.round(-2.5);
~~~

`StrictMath` được thiết kế với yêu cầu kết quả tính toán có thể tái lập chặt chẽ trên nhiều nền tảng, đặc biệt quan trọng với nhiều hàm toán học phức tạp. Tuy nhiên, đối với **ceil, floor, rint và round**, các quy tắc kết quả đã được API xác định rõ; không có “chính sách làm tròn bí mật” khác nhau giữa `Math` và `StrictMath` trong các ví dụ này.

| Tên | Math | StrictMath | Khác biệt cần chú ý |
| --- | --- | --- | --- |
| `ceil(double)` | Có | Có | Cùng định nghĩa về +∞ |
| `floor(double)` | Có | Có | Cùng định nghĩa về −∞ |
| `rint(double)` | Có | Có | Cùng ties-to-even |
| `round(float)` | Có | Có | Cùng kiểu `int` và ties-to-positive-infinity |
| `round(double)` | Có | Có | Cùng kiểu `long` và ties-to-positive-infinity |

Không nên đoán rằng `StrictMath` “luôn chậm hơn” hoặc “luôn chính xác hơn” trong mọi môi trường. Hiệu năng phụ thuộc JDK/JVM/phần cứng, và các hàm làm tròn này đã có ngữ nghĩa được định nghĩa cụ thể. Chọn API theo yêu cầu hệ thống và đo bằng benchmark đại diện nếu tốc độ là vấn đề.

## 12. Làm tròn số thập phân: tránh lạm dụng Math.round

Một cách viết thường thấy để làm tròn hai chữ số thập phân:

~~~java
double x = 1.005;
double result = Math.round(x * 100.0) / 100.0;
~~~

Cách làm này **không đảm bảo** kết quả decimal như người dùng kỳ vọng:

- Nhiều số thập phân không được biểu diễn chính xác bằng `double`.
- Phép nhân `x * 100.0` cũng có thể làm tròn, nên một giá trị tưởng như ở điểm hòa không thực sự bằng đúng điểm hòa trong binary64.
- Với độ lớn rất lớn, nhân hệ số có thể overflow.
- Với số âm đúng điểm hòa, quy tắc `Math.round` là ties to +∞, không phải làm tròn nửa ra xa 0 như nhiều chính sách tài chính.
- Kết quả cuối vẫn là `double`, nên định dạng hiển thị hai chữ số không có nghĩa dữ liệu được lưu với precision decimal cố định.

Nếu yêu cầu **decimal chính xác**, hãy parse trực tiếp từ chuỗi decimal thành `BigDecimal` rồi chọn `RoundingMode`.

~~~java
BigDecimal price = new BigDecimal("1.005");
BigDecimal halfUp = price.setScale(2, RoundingMode.HALF_UP);
BigDecimal halfEven = price.setScale(2, RoundingMode.HALF_EVEN);

System.out.println(halfUp);   // 1.01
System.out.println(halfEven); // 1.00
~~~

Lưu ý `new BigDecimal("1.005")` giữ đúng giá trị decimal `1.005`. Ngược lại, `new BigDecimal(1.005)` tạo `BigDecimal` từ giá trị binary64 xấp xỉ đã có, có thể gây kết quả làm tròn khác. Nếu dữ liệu nguồn là chuỗi người dùng nhập, hãy dùng chuỗi gốc.

## 13. Các chế độ BigDecimal so với Math

Các chế độ `RoundingMode` liên quan:

| Chế độ | Hành vi ở giá trị không nguyên | Ví dụ 2.5 | Ví dụ −2.5 |
| --- | --- | --- | --- |
| `CEILING` | Hướng `+∞` | 3 | −2 |
| `FLOOR` | Hướng `-∞` | 2 | −3 |
| `DOWN` | Hướng **về 0** | 2 | −2 |
| `UP` | Hướng **xa 0** | 3 | −3 |
| `HALF_UP` | Gần nhất; hòa thì **xa 0** | 3 | −3 |
| `HALF_DOWN` | Gần nhất; hòa thì **về 0** | 2 | −2 |
| `HALF_EVEN` | Gần nhất; hòa thì chọn giá trị **chẵn** | 2 | −2 |
| `UNNECESSARY` | Từ chối nếu cần làm tròn | Lỗi | Lỗi |

Đây là bảng khi làm tròn tới **scale 0** bằng `BigDecimal.setScale(0, mode)`.

### Điều tương ứng và khác biệt

- `Math.ceil(x)` có hướng tương đương `RoundingMode.CEILING` (nhưng kiểu dữ liệu và biểu diễn khác).
- `Math.floor(x)` có hướng tương đương `RoundingMode.FLOOR`.
- `Math.rint(x)` gần với quy tắc `HALF_EVEN` ở mức giá trị nguyên.
- `Math.round(x)` **không có một tên `RoundingMode` độc lập tương đương cho cả số dương lẫn số âm**: khi hòa, nó luôn ưu tiên **+∞**, trong khi `HALF_UP` ưu tiên **xa 0**.

Hãy chọn chính sách làm tròn theo yêu cầu nghiệp vụ như quy định thuế, hóa đơn, thống kê hay xử lý tín hiệu, không chọn chỉ vì tên phương thức dễ nhớ.

## 14. Không phải mọi đầu vào double đều có “phần thập phân” có ý nghĩa

Ở các độ lớn rất lớn, khoảng cách giữa các giá trị `double` biểu diễn được có thể là **2, 4, 8 hoặc nhiều hơn**, nên mọi giá trị gần đó đã là số nguyên toán học theo biểu diễn binary64. `Math.ceil`, `Math.floor` hay `Math.rint` sẽ không tự thêm độ chính xác.

Ví dụ:

~~~java
double large = 1e20;
System.out.println(Math.rint(large) == large); // true
~~~

Tuy `large` đã là giá trị nguyên toán học trong binary64, nó **vượt miền `long`**. Do vậy:

~~~java
System.out.println(Math.round(1e20)); // 9223372036854775807
~~~

Kết quả trên là **`Long.MAX_VALUE`**, không phải `100000000000000000000`, vì `Math.round(double)` chỉ trả `long`.

Điểm mấu chốt: “đã làm tròn thành số nguyên” và “có thể lưu trong kiểu số nguyên đích” là **hai câu hỏi khác nhau**.

## 15. Rounding trong tính toán và rounding khi hiển thị

Nếu mục tiêu chỉ là **hiển thị** 2 chữ số thập phân, định dạng bằng `NumberFormat`/`DecimalFormat` hoặc `String.format` theo locale và rounding mode đã chọn có thể phù hợp hơn thay đổi giá trị tính toán.

Ví dụ với `BigDecimal`:

~~~java
BigDecimal amount = new BigDecimal("12.345");
String display = amount.setScale(2, RoundingMode.HALF_EVEN).toPlainString();
System.out.println(display); // 12.34
~~~

Nếu xử lý tiền, dùng `BigDecimal` hoặc lưu số nguyên đơn vị nhỏ nhất là một lựa chọn thiết kế phổ biến. **Không làm tròn ở mỗi bước tính trung gian** trừ khi yêu cầu nghiệp vụ bắt buộc; làm tròn lặp nhiều lần có thể tích lũy sai số.

Nếu chỉ hiển thị, giữ giá trị tính toán nội bộ với độ chính xác phù hợp và định dạng ở điểm xuất dữ liệu. Nếu API quy định “số thập phân hai chữ số” thực sự là thuộc tính dữ liệu, phải kiểm soát `scale`/kiểu biểu diễn ở ranh giới nhập và lưu.

## 16. Những lỗi thường gặp

| Nhầm lẫn | Vấn đề | Cách xử lý |
| --- | --- | --- |
| “ceil luôn tăng trị tuyệt đối” | Với số âm, ceil hướng tới +∞, có thể làm gần 0 hơn | Hiểu định nghĩa `ceil(x) >= x` |
| “floor là cắt phần thập phân” | Với số âm, `floor(-2.8)=-3` nhưng cast cho −2 | Chọn `floor` hoặc cast đúng mục đích |
| “rint và round giống nhau” | Khác tie rule và kiểu trả về | `rint` ties-even; `round` ties +∞ |
| “round là half-away-from-zero” | `round(-2.5)=-2` | Dùng `BigDecimal.HALF_UP` khi cần xa 0 |
| “round trả double” | `round(float)` trả int, `round(double)` trả long | Kiểm tra đúng overload |
| “rint trả int” | `rint` trả double | Chuyển có kiểm tra miền |
| “round(NaN) ném lỗi” | Trả 0, có thể che dữ liệu sai | Kiểm tra `isFinite` trước |
| “round(Infinity) ném lỗi” | Trả cực trị của int/long | Kiểm tra miền trước |
| “ceil/floor/rint(NaN) thành 0” | Trả NaN | Kiểm tra giá trị đặc biệt |
| “−0.0 giống hệt +0.0” | `==` true nhưng bit dấu khác | Chọn có bảo toàn dấu zero không |
| “Math.round giúp parse số nguyên lớn” | `double` có thể mất chữ số trước | Parse `long`/`BigInteger` từ chuỗi |
| “nhân 100 rồi round luôn chính xác decimal” | Sai số binary64/overflow | Dùng `BigDecimal(String)` và `setScale` |
| “HALF_UP giống Math.round cho số âm” | HALF_UP đi xa 0, Math.round ưu tiên +∞ | Kiểm tra chính sách ở điểm hòa |
| “Math và StrictMath có quy tắc tie khác nhau” | Hai API cùng ngữ nghĩa làm tròn đã công bố | Đọc hợp đồng của từng phương thức |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Kết quả của `Math.ceil(-4.2)` và `Math.floor(-4.2)`?

**Đáp án:** `-4.0` và `-5.0`. Ceil đi tới +∞; floor đi tới −∞.

**Câu 2.** Vì sao `Math.rint(2.5)` là `2.0`, trong khi `Math.round(2.5)` là `3`?

**Đáp án:** `rint` chọn số **chẵn** ở điểm hòa; `round` chọn số nguyên về phía **+∞** ở điểm hòa. Ngoài ra `rint` trả double, `round(double)` trả long.

**Câu 3.** `Math.round(-2.5)` có bằng `-3` như `HALF_UP` không?

**Đáp án:** Không. `Math.round(-2.5)` bằng `-2`, còn `new BigDecimal("-2.5").setScale(0, HALF_UP)` bằng `-3`.

**Câu 4.** Vì sao `Math.round(Double.NaN)` nguy hiểm nếu dùng để xử lý dữ liệu đầu vào?

**Đáp án:** Nó trả `0L` thay vì báo lỗi, có thể che giấu một giá trị không hợp lệ. Kiểm tra `Double.isFinite` trước khi làm tròn.

**Câu 5.** Vì sao `Math.round(1e20)` không trả nguyên giá trị toán học \(10^{20}\)?

**Đáp án:** `Math.round(double)` trả `long`, nhưng \(10^{20}\) vượt `Long.MAX_VALUE`, nên kết quả bị giới hạn về `Long.MAX_VALUE`.

**Câu 6.** Dữ liệu decimal `"1.005"` cần làm tròn hai chữ số thập phân với `HALF_UP`. Nên dùng gì?

**Đáp án:** `new BigDecimal("1.005").setScale(2, RoundingMode.HALF_UP)` cho `1.01`; không dựa vào `Math.round(x*100)/100` nếu cần precision decimal.

**Câu 7.** Kết quả `Math.rint(-0.5)` và `Math.round(-0.5)`?

**Đáp án:** `-0.0` (double) và `0` (long). `rint` có thể giữ dấu zero; `round` trả kiểu nguyên không có zero âm.

## 18. Tóm tắt và tài liệu tham khảo

Hãy nhớ bốn câu ngắn:

1. **`ceil`:** tới số nguyên **bên trên** theo trục số (`+∞`).
2. **`floor`:** tới số nguyên **bên dưới** theo trục số (`-∞`).
3. **`rint`:** số nguyên gần nhất, **hòa chọn chẵn**, trả `double`.
4. **`round`:** số nguyên gần nhất, **hòa chọn phía dương**, trả `int` hoặc `long`.

Đối với dữ liệu nghiêm ngặt, kiểm tra `NaN`/`Infinity`, miền của kiểu đích và yêu cầu chính xác **trước** khi làm tròn. Với số decimal cần quy tắc làm tròn rõ và chính xác, ưu tiên `BigDecimal` cùng `RoundingMode`. Không nhầm làm tròn **giá trị tính toán** với định dạng **chuỗi hiển thị**.

Nguồn chính thức:

- [Java SE 17 — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): định nghĩa `ceil`, `floor`, `rint`, `round` và xử lý số đặc biệt.
- [Java SE 17 — StrictMath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html): các phương thức tương ứng và tính tái lập.
- [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): `HALF_UP`, `HALF_EVEN`, `CEILING`, `FLOOR` và các chế độ khác.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `setScale` và độ chính xác decimal.
- [JLS Java SE 17 — Floating-Point Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): độ chính xác, NaN, infinity và signed zero.
