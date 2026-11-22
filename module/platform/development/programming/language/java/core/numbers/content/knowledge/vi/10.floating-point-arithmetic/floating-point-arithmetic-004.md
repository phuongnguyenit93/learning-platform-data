# Toán tử `%` khác `Math.IEEEremainder` trong Java

Java hỗ trợ **hai phép lấy phần dư trên số dấu phẩy động với hai quy tắc khác nhau**:

- Toán tử **`%`** lấy phần dư từ phép chia có thương **cắt phần lẻ về 0** (*truncation toward zero*), gần với hàm `fmod` của C.
- **`Math.IEEEremainder(double, double)`** lấy phần dư từ phép chia có thương được làm tròn đến **số nguyên gần nhất**; nếu đúng giữa hai số nguyên, chọn **số nguyên chẵn** (*ties to even*) theo định nghĩa IEEE 754.

Chúng có thể cho hai kết quả **khác dấu**, dù cùng nhận một cặp số thực.

```java
double x = 7.0;
double y = 2.0;

System.out.println(x % y);                  // 1.0
System.out.println(Math.IEEEremainder(x,y)); // -1.0
```

Cả hai kết quả đều hợp lý **theo quy tắc thương riêng**. `7 / 2 = 3.5`; nếu cắt về 0, thương nguyên là 3 và dư là `7 - 2*3 = 1`. Nếu chọn thương nguyên gần nhất với quy tắc hòa chọn số chẵn, thương là 4 và dư là `7 - 2*4 = -1`.

Bài học tập trung vào cách hiểu, API đúng, dấu của phần dư, trường hợp IEEE 754 đặc biệt, các bẫy khi dùng cho góc/chu kỳ, và cách kiểm chứng kết quả trên Java 17+.

## 1. Hai khái niệm khác nhau: remainder từ thương nào?

Gọi `x` là **số bị chia** (*dividend*), `y` là **số chia** (*divisor*) và giả sử cả hai hữu hạn, `y != 0`. Về mặt toán học, một phần dư được mô tả bởi:

```text
r = x - y * q
```

Điểm khác biệt nằm ở cách chọn **số nguyên `q`**.

### `x % y`: thương cắt về 0

Với toán hạng chấm động, toán tử `%` của Java xác định thương nguyên khái niệm:

```text
q = trunc(x / y)
r = x - q * y
```

`trunc` loại bỏ phần lẻ theo hướng về 0. Ví dụ:

- `7 / 2 = 3.5`: `q = 3`, `r = +1`.
- `-7 / 2 = -3.5`: `q = -3`, `r = -1`.
- `7 / -2 = -3.5`: `q = -3`, `r = +1`.
- `-7 / -2 = 3.5`: `q = 3`, `r = -1`.

**Nếu khác 0, phần dư `%` mang dấu của `x`**, không phải dấu của `y`. Giá trị tuyệt đối của dư nhỏ hơn `|y|` khi hai toán hạng hữu hạn và số chia khác 0.

### `Math.IEEEremainder`: thương nguyên gần nhất, hòa chọn chẵn

Phương thức `Math.IEEEremainder(x, y)` dùng:

```text
q = số nguyên gần nhất với thương toán học x / y;
    nếu hai số nguyên cách đều, chọn số nguyên chẵn.
r = x - q * y
```

Với `7 / 2 = 3.5`, hai số nguyên 3 và 4 cùng cách 0.5. Số 4 **chẵn**, vậy `q = 4` và `r = -1`. Với `5 / 2 = 2.5`, hai ứng viên là 2 và 3, nên chọn `q = 2` và `r = +1`.

Điểm cần nhấn mạnh: “số nguyên chẵn” nói về **thương `q`**, **không** nói về phần dư. Đây không phải làm tròn theo kiểu “0.5 luôn lên”.

> Các công thức trên giải thích **ngữ nghĩa toán học**. Không nên tự mô phỏng phép `%` hoặc `IEEEremainder` bằng biểu thức chấm động `x - y * (...)` vì phép chia và phép nhân trung gian có thể làm tròn hoặc overflow, khiến kết quả khác API được định nghĩa. Hãy gọi đúng toán tử/phương thức.

## 2. Bảng so sánh với số dương và âm

| `x` | `y` | `trunc(x/y)` | `q` gần nhất (ties-even) | `x % y` | `Math.IEEEremainder(x,y)` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 7 | 2 | 3 | 4 | 1 | −1 |
| 5 | 2 | 2 | 2 | 1 | 1 |
| 3 | 2 | 1 | 2 | 1 | −1 |
| −7 | 2 | −3 | −4 | −1 | 1 |
| 7 | −2 | −3 | −4 | 1 | −1 |
| −7 | −2 | 3 | 4 | −1 | 1 |
| 6 | 4 | 1 | 2 | 2 | −2 |
| −6 | 4 | −1 | −2 | −2 | 2 |
| 8 | 3 | 2 | 3 | 2 | −1 |

Trong bảng này, tất cả số là những số nguyên nhỏ được biểu diễn **chính xác** dưới dạng `double`, nên bảng không lẫn vấn đề sai số của literal thập phân.

Các trường hợp dễ nhầm:

- **`5.0 % 2.0 == Math.IEEEremainder(5.0,2.0)`:** cả hai bằng 1, vì ties-even chọn thương 2.
- **`7.0 % 2.0 != Math.IEEEremainder(7.0,2.0)`:** 1 khác −1, vì ties-even chọn thương 4.
- **`6.0 % 4.0` bằng 2, còn `Math.IEEEremainder(6.0,4.0)` bằng −2:** thương 1.5 nằm giữa 1 và 2, nên IEEE chọn 2.
- **Đổi dấu số chia** có thể đổi dấu thương nhưng không tự làm đổi dấu phần dư trong ví dụ tương ứng: các kết quả được quyết định bởi quy tắc chọn thương và dấu của số bị chia.

Để học nhanh, chỉ cần nhớ `7.0` và `2.0`: nó đủ làm phản ví dụ cho nhận định “cả hai đều là modulo nên như nhau”.

## 3. Vì sao tên “IEEEremainder” không có nghĩa “phần dư luôn dương”?

Với `%` trên chấm động, nếu kết quả khác 0, dấu theo **số bị chia `x`**. Nhưng với `Math.IEEEremainder`, phần dư có thể dương **hoặc âm**, không phụ thuộc riêng vào dấu của `x` hay `y`.

Khi `x`, `y` hữu hạn và `y != 0`:

- Phần dư của `%` có độ lớn **nhỏ hơn** `|y|`.
- Phần dư của `IEEEremainder` có độ lớn **không lớn hơn một nửa** `|y|` theo quan hệ toán học của thương làm tròn gần nhất.
- Ở đúng vị trí nửa chu kỳ, dấu kết quả `IEEEremainder` được quyết định gián tiếp bởi **ties-to-even của thương**, nên có thể xuất hiện cả `+|y|/2` và `-|y|/2` tùy trường hợp.

Ví dụ:

```java
System.out.println(Math.IEEEremainder(5.0, 2.0)); // 1.0
System.out.println(Math.IEEEremainder(7.0, 2.0)); // -1.0
```

Cả hai giá trị có cùng độ lớn 1.0 nhưng **khác dấu** dù `x` và `y` đều dương. Do đó, `Math.IEEEremainder` **không phù hợp để tự động tạo index từ 0 đến n−1**.

Cụm từ *remainder* trong API không đồng nghĩa với quy ước “modulo không âm”. Khi thiết kế dữ liệu, phải nêu rõ phần dư thuộc khoảng nào và số chia có được âm không.

## 4. Hòa ở nửa đơn vị: ties-to-even khác `Math.round`

Quy tắc hòa của `Math.IEEEremainder` tương thích với nguyên tắc làm tròn về số nguyên gần nhất, chọn số chẵn. Java cung cấp `Math.rint(double)` theo quy tắc chọn số nguyên gần nhất với ties-to-even, nhưng **không** được coi `Math.IEEEremainder` đơn giản là `x - Math.rint(x/y) * y` trên mọi đầu vào.

```java
System.out.println(Math.rint(2.5));  // 2.0
System.out.println(Math.round(2.5)); // 3
```

`Math.round` là API **khác**: với trường hợp nằm đúng giữa hai số nguyên, nó chọn hướng về **dương vô cực** theo quy tắc của phương thức này. Còn `Math.rint(2.5)` chọn 2 vì 2 chẵn. `Math.rint(3.5)` chọn 4 vì 4 chẵn.

Cẩn thận: phép chia `x/y` tính trước bằng `double` có thể bị làm tròn thành giá trị khác thương toán học thật, hoặc overflow thành vô cực khi `x` rất lớn và `y` cực nhỏ. Phép nhân `q*y` cũng có thể làm tròn. Vì thế, dùng `Math.rint` để **minh họa quy tắc ties-even**, nhưng dùng `Math.IEEEremainder` khi cần chính xác **ngữ nghĩa IEEE remainder**.

### Còn `Math.floor` và `Math.floorMod`?

- `Math.floor(double)` trả giá trị `double` là số nguyên toán học lớn nhất không vượt đối số; đây không phải phép lấy phần dư.
- `Math.floorMod` nhận đối số **nguyên** (`int`/`long`), **không có overload nhận `double`**. Với modulo nguyên dương, nó tạo phần dư không âm kể cả khi số bị chia âm.
- `Math.IEEEremainder` dùng thương **gần nhất** chứ **không** dùng `floor` hay `trunc`.

Ba cách chọn thương (*truncation*, *floor*, *nearest-ties-even*) là ba quy tắc khác nhau; chỉ dùng chúng thay thế nhau khi bạn chứng minh kết quả đáp ứng hợp đồng bài toán.

## 5. Trường hợp đặc biệt: zero, NaN và Infinity

Dấu phẩy động của Java có các giá trị `NaN`, `+Infinity`, `-Infinity`, `+0.0` và `-0.0`. Kết quả của `%` **khác đáng kể** với phép `%` số nguyên khi chia cho 0.

| Tình huống dấu phẩy động | `x % y` | `Math.IEEEremainder(x,y)` |
| --- | --- | --- |
| Bất kỳ toán hạng nào là `NaN` | `NaN` | `NaN` |
| `x` là ±Infinity, `y` hữu hạn khác 0 | `NaN` | `NaN` |
| `y` là `+0.0` hoặc `-0.0` | `NaN` | `NaN` |
| `x` hữu hạn, `y` là ±Infinity | Trả đúng `x` | Trả đúng `x` |
| `x` bằng `+0.0` hoặc `-0.0`, `y` hữu hạn khác 0 | Trả zero cùng dấu với `x` | Trả zero cùng dấu với `x` |
| Kết quả khác 0, hai toán hạng hữu hạn | Dấu theo `x` | Dấu tùy thương làm tròn gần nhất |
| Kết quả đúng bằng 0 | Zero cùng dấu với `x` | Zero cùng dấu với `x` |

`Math.IEEEremainder` là phương thức nhận và trả `double`. Không có overload `IEEEremainder(float,float)`: nếu truyền hai `float`, Java mở rộng chúng sang `double` và phương thức trả `double`.

### Chia cho 0 là `NaN`, không phải `ArithmeticException`

```java
double a = 7.0 % 0.0;
double b = Math.IEEEremainder(7.0, 0.0);
System.out.println(Double.isNaN(a)); // true
System.out.println(Double.isNaN(b)); // true
```

Khác với:

```java
// int invalid = 7 % 0; // Phép % số nguyên chia cho 0 không hợp lệ;
// với số chia nguyên bằng 0 ở runtime, Java ném ArithmeticException.
```

Với toán hạng dấu phẩy động, `%` không ném ngoại lệ runtime do zero divisor. `NaN` cũng không so sánh bằng chính nó theo `==`, nên kiểm tra bằng `Double.isNaN`.

### Zero âm vẫn mang dấu

```java
double r1 = -4.0 % 2.0;
double r2 = Math.IEEEremainder(-4.0, 2.0);

System.out.println(r1); // -0.0
System.out.println(r2); // -0.0
```

Dù `-0.0 == +0.0` là `true`, chúng có mẫu bit dấu khác nhau. Nếu định dạng dữ liệu/giao thức cần bảo toàn zero âm, có thể kiểm tra `Double.doubleToRawLongBits`.

Không dùng `Math.abs` để kết luận mọi phần dư giờ có nghĩa modulo mong muốn: trị tuyệt đối của dư âm có thể cho một vị trí **khác hẳn** vị trí tương đương trong chu kỳ.

## 6. Kiểu của biểu thức: `float`, `double` và numeric promotion

Toán tử `%` có thể dùng với `int`, `long`, `float` hoặc `double`. Đối với phép toán có các toán hạng khác kiểu, Java áp dụng **binary numeric promotion**. Ví dụ:

```java
float a = 7.0f;
float b = 2.0f;

float floatRemainder = a % b; // Kết quả phép % là float.
double ieeeRemainder = Math.IEEEremainder(a, b); // Hai float được mở rộng lên double.
```

Giá trị ở ví dụ là `floatRemainder == 1.0f` và `ieeeRemainder == -1.0`. Khi có `double` ở một toán hạng của `%`, phép toán được tính với `double`:

```java
float x = 7.0f;
double y = 2.0;
double mixed = x % y; // Kết quả double.
```

Với số thập phân không biểu diễn chính xác trong binary32/binary64, dữ liệu đã được làm tròn **trước khi gọi phương thức** hoặc thực hiện toán tử. Vì thế, một phép tính tưởng là “x % 0.1” có thể cho phần dư nhỏ không mong muốn do bản thân `0.1` là giá trị nhị phân gần đúng.

Muốn khẳng định kết quả đúng, phải tách hai vấn đề:

1. **Quy tắc lấy thương**: truncate hay nearest-ties-even?
2. **Biểu diễn các toán hạng**: `float`/`double` có lưu chính xác các số đầu vào không?

`Math.IEEEremainder` giải quyết quy tắc thứ nhất, **không** biến mọi giá trị `double` thành thập phân chính xác.

## 7. Ví dụ chạy độc lập trên Java 17+

Lưu mã dưới tên `RemainderComparisonDemo.java`:

```java
public class RemainderComparisonDemo {
    public static void main(String[] args) {
        double[][] samples = {
                {7, 2}, {5, 2}, {3, 2},
                {-7, 2}, {7, -2}, {-7, -2},
                {6, 4}, {-6, 4}, {8, 3}
        };

        for (double[] sample : samples) {
            double x = sample[0];
            double y = sample[1];
            System.out.println(x + " % " + y + " = " + (x % y)
                    + " | IEEE = " + Math.IEEEremainder(x, y));
        }

        System.out.println("rint(2.5) = " + Math.rint(2.5));
        System.out.println("round(2.5) = " + Math.round(2.5));

        System.out.println("zero divisor with % -> NaN: "
                + Double.isNaN(7.0 % 0.0));
        System.out.println("zero divisor with IEEE -> NaN: "
                + Double.isNaN(Math.IEEEremainder(7.0, 0.0)));
        System.out.println("infinite dividend -> NaN: "
                + Double.isNaN(Math.IEEEremainder(
                        Double.POSITIVE_INFINITY, 2.0)));

        System.out.println("finite % infinity = "
                + (5.0 % Double.POSITIVE_INFINITY));
        System.out.println("finite IEEE infinity = "
                + Math.IEEEremainder(5.0, Double.POSITIVE_INFINITY));

        System.out.println("signed zero from %: " + (-4.0 % 2.0));
        System.out.println("signed zero from IEEE: "
                + Math.IEEEremainder(-4.0, 2.0));
        System.out.println("negative zero detected: "
                + (Double.doubleToRawLongBits(
                        Math.IEEEremainder(-4.0, 2.0)) == Long.MIN_VALUE));

        float floatRemainder = 7.0f % 2.0f;
        double ieeeRemainder = Math.IEEEremainder(7.0f, 2.0f);
        System.out.println("float remainder = " + floatRemainder
                + ", IEEE returns double = " + ieeeRemainder);
    }
}
```

Lệnh biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 RemainderComparisonDemo.java
java RemainderComparisonDemo
```

Kết quả stdout:

```text
7.0 % 2.0 = 1.0 | IEEE = -1.0
5.0 % 2.0 = 1.0 | IEEE = 1.0
3.0 % 2.0 = 1.0 | IEEE = -1.0
-7.0 % 2.0 = -1.0 | IEEE = 1.0
7.0 % -2.0 = 1.0 | IEEE = -1.0
-7.0 % -2.0 = -1.0 | IEEE = 1.0
6.0 % 4.0 = 2.0 | IEEE = -2.0
-6.0 % 4.0 = -2.0 | IEEE = 2.0
8.0 % 3.0 = 2.0 | IEEE = -1.0
rint(2.5) = 2.0
round(2.5) = 3
zero divisor with % -> NaN: true
zero divisor with IEEE -> NaN: true
infinite dividend -> NaN: true
finite % infinity = 5.0
finite IEEE infinity = 5.0
signed zero from %: -0.0
signed zero from IEEE: -0.0
negative zero detected: true
float remainder = 1.0, IEEE returns double = -1.0
```

Chương trình cho thấy: các kết quả khác dấu với cùng dữ liệu, quy tắc ties-to-even, xử lý zero divisor/infinity, zero âm và sự khác biệt kiểu trả về khi gọi `Math.IEEEremainder` với `float`.

## 8. Chọn API nào trong bài toán thực tế?

### Trường hợp A — Phần dư theo chia cắt về 0

Chọn **`%`** khi hợp đồng mong muốn dấu của phần dư đi theo số bị chia, gần với cách tính remainder nguyên của Java.

Ví dụ, tính phần dư của độ dài dịch chuyển `-7.0` theo quãng `2.0`:

```java
double offset = -7.0 % 2.0; // -1.0
```

Đây là cách tính hợp lệ nếu logic của bạn cần **phần dư có dấu theo dịch chuyển**. Nhưng nó **không phải** tọa độ index modulo luôn không âm.

### Trường hợp B — Sai lệch có độ lớn gần 0 nhất trong miền chu kỳ

Chọn **`Math.IEEEremainder`** khi muốn một phần dư nằm gần 0 hơn, chẳng hạn trong một quy ước **hiệu pha có dấu** hoặc sai lệch chu kỳ được đo theo khoảng đối xứng xung quanh 0. Với modulus hữu hạn khác 0, độ lớn phần dư không quá nửa modulus.

```java
double angle = 350.0;
double signedRemainder = Math.IEEEremainder(angle, 360.0);
// -10.0, vì chọn thương 1 thay vì 0.
```

Đây có thể là cách thuận tiện để biểu diễn độ lệch góc ngắn nhất quanh điểm 0. Nhưng ở chính **nửa chu kỳ** (±180 độ với chu kỳ 360), kết quả có thể là +180 hoặc −180 tùy thương làm tròn và vị trí ban đầu; hãy quy định rõ muốn khoảng `[-180,180]`, `[-180,180)` hay `(-180,180]` và chuẩn hóa đường biên nếu cần.

`Math.IEEEremainder` cũng không tự bảo đảm giá trị hữu hạn khi đầu vào là NaN/Infinity hoặc chu kỳ bằng 0. Kiểm tra dữ liệu đầu vào tại ranh giới nghiệp vụ.

### Trường hợp C — Index vòng không âm

Nếu đang đánh chỉ số mảng/list, thường nên dùng số **nguyên**, với `Math.floorMod`:

```java
int size = 5;
int index = Math.floorMod(-1, size); // 4
```

`Math.floorMod` không có overload cho `double`. Nếu dữ liệu của bạn thực chất là index nguyên, đừng chuyển sang `double` để dùng `IEEEremainder`.

Với góc hoặc pha chấm động cần chuẩn hóa về `[0,period)`, có thể bắt đầu bằng phép `%` rồi điều chỉnh khi phần dư âm, nhưng phải cân nhắc việc cộng `period` có thể làm tròn ở biên. Ví dụ minh họa cho **đầu vào hữu hạn, chu kỳ dương**, không phải công thức bảo đảm độ chính xác tuyệt đối:

```java
double value = -10.0;
double period = 360.0;
double r = value % period;
if (r < 0.0) r += period;
if (r >= period) r = 0.0; // Chặn trường hợp làm tròn lên đúng period.
System.out.println(r); // 350.0
```

Nếu cần chuẩn hóa góc với quy tắc chính xác tại boundary, viết test rõ cho ±0, bội số chu kỳ, nửa chu kỳ, dữ liệu rất lớn và trường hợp gần đường biên. Không tự áp dụng `Math.abs(value % period)`, vì `Math.abs(-10.0 % 360.0)` là 10.0 chứ **không phải** vị trí tương đương 350.0.

### Trường hợp D — Số tiền hoặc số thập phân chính xác

Nếu bài toán dùng tiền hoặc số thập phân cần quy tắc chính xác, cả `%` trên `double` lẫn `Math.IEEEremainder` đều **không** giải quyết việc nhị phân không biểu diễn chính xác `0.1`.

Có thể dùng `BigDecimal`:

```java
java.math.BigDecimal amount = new java.math.BigDecimal("7.5");
java.math.BigDecimal step = new java.math.BigDecimal("2.0");
java.math.BigDecimal r = amount.remainder(step); // 1.5
```

`BigDecimal.remainder` có hợp đồng riêng dựa trên quotient theo hướng về 0, **không phải** IEEE remainder gần nhất. Nó làm việc theo biểu diễn thập phân chính xác nhưng vẫn cần kiểm tra divisor khác 0 và xác định chính sách scale/precision của phép tính.

## 9. Các lỗi phổ biến

| Nhầm lẫn | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Cho rằng `x % y` và `Math.IEEEremainder(x,y)` là một phép toán | Sai dấu và biên khi thương có phần lẻ | Xác định quy tắc truncate hay nearest-ties-even |
| Cho rằng `IEEEremainder` luôn trả số không âm | `IEEEremainder(7,2) == -1` | Dùng API phù hợp khoảng kết quả nghiệp vụ |
| Nhầm ties-to-even với `Math.round` | Hòa 2.5 được xử lý khác | Hiểu thương IEEE là nearest, ties-even |
| Tự tính `x - Math.rint(x / y) * y` thay phương thức | Phép toán trung gian có thể làm tròn/overflow | Gọi `Math.IEEEremainder` trực tiếp |
| Dùng `IEEEremainder` làm index mảng | Dư có thể âm, đồng thời là `double` | Dùng `Math.floorMod` cho index nguyên |
| Gọi `Math.floorMod` với `double` | Không biên dịch | Dùng overload kiểu nguyên hoặc thiết kế lại chuẩn hóa thực |
| Mong `7.0 % 0.0` ném `ArithmeticException` | Kết quả thực tế là `NaN` | Kiểm tra divisor và `Double.isNaN` |
| Quên số 0 có dấu | `-0.0` có bit dấu âm dù bằng `+0.0` theo `==` | Chỉ kiểm tra raw bits nếu nghiệp vụ cần |
| Dùng `float` để gọi `IEEEremainder` và giả định kết quả `float` | Phương thức trả `double` | Khai báo `double` và cân nhắc chuyển hẹp nếu cần |
| Chọn `%` vì muốn chuẩn hóa góc về `[0,360)` | Số âm vẫn cho phần dư âm | Điều chỉnh có kiểm tra và test đường biên |
| Cho rằng “IEEE” đồng nghĩa với decimal exact | Không thay đổi việc lưu binary64 | Dùng `BigDecimal` nếu bài toán cần thập phân chính xác |
| Đọc `Math.IEEEremainder` như phép chia lấy thương | Đây là **phần dư**, không phải quotient | Sử dụng `/`, `floorDiv` hoặc thuật toán quotient đúng nhu cầu |

## 10. Bộ kiểm thử tối thiểu và câu hỏi ôn tập

Khi thay một phép tính remainder bằng API khác, nên kiểm tra ít nhất các nhóm:

1. **Thương nguyên chẵn/lẻ và trường hợp hòa:** `(5.0,2.0)`, `(7.0,2.0)`, `(6.0,4.0)`.
2. **Dấu của hai toán hạng:** `(-7.0,2.0)`, `(7.0,-2.0)`, `(-7.0,-2.0)`.
3. **Bội số chính xác và zero âm:** `(-4.0,2.0)`, `(+0.0,3.0)`, `(-0.0,3.0)`.
4. **Giá trị đặc biệt:** một toán hạng NaN, dividend Infinity, divisor ±0, divisor Infinity.
5. **Giới hạn thực tế của ứng dụng:** số rất lớn/rất nhỏ, số thập phân nhị phân xấp xỉ, nửa chu kỳ và sát đường biên.

Tự trả lời:

- Vì sao `7.0 % 2.0` bằng 1.0 nhưng `Math.IEEEremainder(7.0,2.0)` bằng −1.0?
- Vì sao `Math.IEEEremainder(5.0,2.0)` lại bằng +1.0? Vai trò của thương chẵn là gì?
- Nếu cần luôn có phần dư trong `[0,n)` với `n` nguyên dương, nên chọn `%`, `IEEEremainder` hay `floorMod`?
- Java xử lý `7.0 % 0.0` khác `7 % 0` như thế nào?
- Vì sao `Math.rint(x/y)` chỉ giúp hiểu quy tắc mà chưa phải một cách tự cài đặt IEEE remainder đáng tin cho mọi `double`?
- Với góc 350 độ và chu kỳ 360 độ, `Math.IEEEremainder` cho kết quả bao nhiêu? Tại sao cần quy ước biên ±180?
- Khi một hàm nhận `float` nhưng gọi `Math.IEEEremainder`, kiểu trả về thực sự là gì?
- Với dữ liệu thập phân chính xác, vì sao chuyển sang `BigDecimal.remainder` cũng là thay đổi **hợp đồng phép toán**, không đơn thuần thay đổi số bit?

## 11. Tài liệu chính thức

- [Java Language Specification, `15.17.3 — Remainder Operator % (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.3): `%` nguyên và dấu phẩy động; quy tắc truncate, dấu của phần dư và các trường hợp đặc biệt.
- [`Math.IEEEremainder` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#IEEEremainder(double,double)): định nghĩa quotient gần nhất, ties-to-even, số 0 có dấu và xử lý NaN/Infinity.
- [`Math.rint` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#rint(double)): làm tròn về số nguyên gần nhất, hòa chọn số chẵn.
- [`Math.floorMod` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#floorMod(int,int)): phép modulo dành cho kiểu nguyên.

**Kết luận:** `%` và `Math.IEEEremainder` không phải hai cách viết của một phép toán. `%` tính phần dư từ thương **cắt về 0**, nên dấu của kết quả khác 0 theo số bị chia. `Math.IEEEremainder` tính phần dư từ thương nguyên **gần nhất, hòa chọn chẵn**, nên có thể cho dư trái dấu số bị chia. Chọn phép toán theo **khoảng giá trị và chính sách làm tròn** của bài toán; kiểm tra NaN, Infinity, divisor bằng zero và dữ liệu gần biên trước khi đưa vào hệ thống thực tế.