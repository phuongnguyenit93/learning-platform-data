# asin, acos, atan và atan2 trong Java — Math và StrictMath

## 1. Bạn sẽ học gì?

Khi biết **sin, cos, tan** của một góc, làm sao tìm lại góc ấy? Khi biết tọa độ `(x, y)` của một điểm, làm sao tìm góc phương vị mà **không nhầm góc phần tư**?

Java cung cấp bốn hàm lượng giác ngược quan trọng:

- `Math.asin(x)`: **arc sine**, tìm một góc có sin bằng `x`.
- `Math.acos(x)`: **arc cosine**, tìm một góc có cos bằng `x`.
- `Math.atan(x)`: **arc tangent**, tìm một góc có tan bằng `x`.
- `Math.atan2(y, x)`: tìm góc từ trục `+x` đến vector `(x, y)`, có xét **dấu của cả hai tọa độ** để nhận biết góc phần tư.

Cả bốn đều có phiên bản tương ứng trên `StrictMath`. Bài này thuộc **Java Core — Numbers / Math và StrictMath**, sử dụng Java 17 trở lên.

Hoàn thành bài học, bạn cần:

1. Nêu đúng **đầu vào hợp lệ, khoảng giá trị đầu ra và đơn vị radian** của từng hàm.
2. Hiểu tại sao phép toán ngược không khôi phục mọi góc ban đầu: các hàm trả **giá trị chính (principal value)**.
3. Phân biệt `atan(y / x)` với `atan2(y, x)`, nhớ **tham số y đứng trước x**.
4. Biết cách đổi radian ↔ degree bằng `Math.toRadians` và `Math.toDegrees`.
5. Xử lý `NaN`, ±Infinity và **signed zero** theo hợp đồng API; hiểu góc ở đường biên ±π.
6. So sánh giới hạn chính xác của `Math` và yêu cầu tái lập kết quả của `StrictMath`.
7. Viết mã hình học, kiểm tra miền đầu vào và xây dựng test cho bốn góc phần tư.

Kiến thức chuẩn bị: kiểu `double`, số thực IEEE 754, tọa độ Descartes, sin/cos/tan và ý nghĩa của `Math.PI`.

## 2. Lượng giác ngược không có nghĩa đảo hàm trên toàn trục thực

Trên một vòng tròn, nhiều góc khác nhau có cùng giá trị sin hoặc cos. Chẳng hạn:

```text
sin(π / 6) = 1 / 2
sin(5π / 6) = 1 / 2
sin(π / 6 + 2π) = 1 / 2
```

Không có cách chọn **duy nhất** góc gốc chỉ từ giá trị `sin`. Vì vậy, mỗi hàm lượng giác ngược chọn một **khoảng giá trị chính**.

| Hàm Java | Ý nghĩa | Miền đầu vào thông thường | Khoảng kết quả chính (radian) |
| --- | --- | --- | --- |
| `asin(v)` | Góc có sin = `v` | `−1 ≤ v ≤ 1` | `[−π/2, +π/2]` |
| `acos(v)` | Góc có cos = `v` | `−1 ≤ v ≤ 1` | `[0, π]` |
| `atan(v)` | Góc có tan = `v` | Mọi số thực hữu hạn; ±∞ cũng được xử lý | `[−π/2, +π/2]`, tiệm cận hai đầu |
| `atan2(y,x)` | Góc vector `(x,y)` tính từ trục `+x` | Hai tọa độ thực, có quy tắc IEEE 754 cho giá trị đặc biệt | `[−π, +π]` |

**Đơn vị trả về luôn là radian**, không phải độ, và **kiểu trả về là primitive `double`**. Java cung cấp `Math.asin(double)`, `Math.acos(double)`, `Math.atan(double)` và `Math.atan2(double,double)`. Truyền `float` hoặc `int` vào các method này thường được widening sang `double`; không có bộ overload riêng `asin(float)` trả `float` trong `Math` của Java 17.

Lưu ý các đầu mút của `atan` với đối số hữu hạn: nó không đạt chính xác ±π/2 theo toán học cho một giá trị hữu hạn, nhưng trong biểu diễn floating point kết quả có thể được làm tròn tới mẫu `double` gần π/2. Khi đối số ±Infinity, Java trả kết quả gần nhất với ±π/2 theo hợp đồng API.

## 3. Đổi độ và radian trước khi tính

Một vòng tròn có `360° = 2π` radian. Công thức:

```text
radian = degree × π / 180
degree = radian × 180 / π
```

Java có hai helper chuẩn:

```java
double radians = Math.toRadians(30.0);
double degrees = Math.toDegrees(Math.PI / 6);
```

Chúng trả `double`, và phép chuyển có thể có **sai số làm tròn**; không khẳng định mọi độ lớn đều đổi qua lại tuyệt đối chính xác ở mức bit.

Ví dụ:

```java
System.out.println(Math.toDegrees(Math.asin(0.5))); // 30.000000000000004 có thể xuất hiện
```

Trong phần chương trình bên dưới, sẽ dùng `printf(Locale.US, "%.1f%n", ...)` để **chủ động hiển thị một chữ số thập phân**, tránh hiểu nhầm cách in số gần 30 là kết quả không đúng.

**Bẫy phổ biến:** `Math.asin(0.5)` là khoảng `0.5235987756` **radian**, không phải `30.0` degree. `Math.asin(30)` không phải phép tính “asin của 30°”; đây là đối số **ngoài miền** của hàm asin.

## 4. Math.asin: arc sine, chọn góc trong [−π/2, π/2]

Ký hiệu toán học `arcsin(v)` hoặc `sin⁻¹(v)` mô tả **một góc có sin bằng v**. Đây là hàm lượng giác ngược, **không phải** giá trị `1/sin(v)`.

Với `v` trong `[−1,1]`, `Math.asin(v)` cho góc chính trong `[−π/2,π/2]`:

| v | Góc chính radian | Góc theo degree |
| ---: | --- | ---: |
| −1 | −π/2 | −90° |
| −0.5 | −π/6 | −30° |
| 0 | 0 | 0° |
| 0.5 | π/6 | 30° |
| 1 | π/2 | 90° |

Ví dụ:

```java
double angle = Math.asin(0.5);
System.out.printf(java.util.Locale.US, "%.1f%n",
        Math.toDegrees(angle)); // 30.0
```

**Điểm quan trọng:** `Math.asin(Math.sin(theta))` không luôn bằng `theta`. Nếu `theta` ở góc phần tư II, `sin(theta)` có thể trùng với một góc góc phần tư I, và `asin` sẽ trả kết quả trong khoảng `[−90°,90°]`. Ví dụ `sin(150°)≈0.5`; `asin(0.5)` trả `30°` chứ không phải `150°`.

### 4.1. Đầu vào ngoài miền và NaN

Nếu `|v| > 1` hoặc `v` là NaN, `Math.asin(v)` trả **NaN**, không ném `IllegalArgumentException` chỉ vì miền số học không hợp lệ.

```java
System.out.println(Double.isNaN(Math.asin(1.01))); // true
System.out.println(Double.isNaN(Math.asin(Double.NaN))); // true
```

`Math.asin(Double.POSITIVE_INFINITY)` và `Math.asin(Double.NEGATIVE_INFINITY)` cũng trả NaN vì độ lớn vượt 1.

Nếu input lẽ ra là tỉ số nằm `[−1,1]` nhưng phép tính do rounding ra `1.0000000000000002`, có thể bạn cần chính sách xử lý sai số. **Không tự động ép mọi input về [−1,1]**: clamp có thể che giấu dữ liệu sai như `5.0`; nếu nghiệp vụ cho phép clamp trong dung sai đã định, phải kiểm tra cách giá trị ra khỏi miền trước khi clamp.

### 4.2. Signed zero

`Math.asin(+0.0)` trả `+0.0`; `Math.asin(-0.0)` trả `-0.0`. Hai số so sánh bằng nhau theo toán tử primitive `==`, nhưng có bit dấu khác nhau. Nếu cần kiểm thử dấu zero, dùng `Double.doubleToRawLongBits` thay vì chỉ `==`.

## 5. Math.acos: arc cosine, chọn góc trong [0, π]

`Math.acos(v)` trả góc chính trong `[0,π]` với `cos(angle) = v`:

| v | Góc chính radian | Degree |
| ---: | --- | ---: |
| 1 | 0 | 0° |
| 0.5 | π/3 | 60° |
| 0 | π/2 | 90° |
| −0.5 | 2π/3 | 120° |
| −1 | π | 180° |

Ví dụ:

```java
double angle = Math.acos(0.5);
System.out.printf(java.util.Locale.US, "%.1f%n",
        Math.toDegrees(angle)); // 60.0
```

**Miền đầu vào là [−1,1]**, giống `asin`; nếu ngoài miền hoặc NaN, kết quả NaN. `Math.acos(1.0)` trả **+0.0** theo hợp đồng API. Với `Math.acos(-1.0)`, kết quả là giá trị `double` gần nhất với π.

Tính chất toán học hữu ích:

```text
acos(v) + asin(v) ≈ π/2  (v ∈ [−1,1])
```

Ký hiệu `≈` là có thể lệch một lượng nhỏ do làm tròn floating point. Không nên kiểm tra tổng bằng chính xác `Math.PI/2` ở mọi input.

### 5.1. Vì sao acos không thay thế atan2 để tìm hướng?

`acos(x/r)` chỉ trả góc trong `[0,π]`, không cho biết tọa độ `y` nằm **phía trên hay phía dưới** trục x. Nếu chỉ biết cos, góc `+60°` và `−60°` có cùng cosine. Từ một vector `(x,y)`, cách trực tiếp để biết dấu và góc phần tư là `atan2(y,x)`.

## 6. Math.atan: arc tangent của một tỉ số

`Math.atan(v)` là góc chính có tan bằng `v`; khoảng giá trị gần `(−π/2,π/2)` cho đối số hữu hạn. Điểm khác `asin`/`acos`: `atan` **không giới hạn input vào [−1,1]**.

Một số mốc:

| v | Kết quả radian | Degree |
| --- | --- | --- |
| −∞ | gần −π/2 | −90° |
| −1 | −π/4 | −45° |
| −0.0 | −0.0 | −0.0° |
| 0.0 | 0.0 | 0.0° |
| 1 | π/4 | 45° |
| +∞ | gần +π/2 | +90° |

Ví dụ:

```java
System.out.println(Math.atan(1.0)); 
// 0.7853981633974483 trên JDK được kiểm thử

System.out.println(Math.atan(Double.POSITIVE_INFINITY));
// 1.5707963267948966 trên JDK được kiểm thử
```

`Math.atan(Double.NaN)` trả NaN. `Math.atan(-0.0)` bảo toàn zero âm.

### 6.1. Khi đảo tangens, mất thông tin góc phần tư

Vì `tan(theta + π) = tan(theta)`, `atan` không thể khôi phục thông tin theta thuộc phần tư nào. Hơn nữa, khi dùng tỉ số `y/x`, bạn mất dấu riêng của `x`/`y`, đặc biệt nếu `x=0`.

Ví dụ hai vector `(1,1)` và `(−1,−1)` cùng có tỉ số `y/x = 1` nên:

```java
Math.atan(1.0 / 1.0);      // gần +45°
Math.atan(-1.0 / -1.0);    // gần +45° (không phải -135°)
```

Nhưng góc hướng từ trục +x của vector `(−1,−1)` là `−135°` theo quy ước của `atan2`. Đó là lý do không dùng một mình `atan(y/x)` cho góc vector tổng quát.

## 7. Math.atan2(y, x): biết góc phần tư từ cả hai tọa độ

Phương thức:

```java
double theta = Math.atan2(y, x);
```

Nhận **tọa độ y đầu tiên, tọa độ x thứ hai**. Đây là một quy ước cố định của Java (cũng xuất hiện trong nhiều thư viện toán học), dễ bị viết ngược do ta quen ghi điểm `(x,y)`.

Với vector `(x,y)` khác gốc tọa độ, góc chính thường nằm trong `[−π,+π]`:

```text
                          y+
                           ^
                 QII       |       QI
                  +135°    |    +45°
                           |
          x− --------------+--------------> x+
                           |
                  −135°    |    −45°
                 QIII      |       QIV
                           v
                          y−
```

Ví dụ bốn góc phần tư, in degree tới một chữ số:

| Tọa độ (x,y) | Cách gọi đúng | Góc |
| --- | --- | ---: |
| (1,1) | `atan2(1,1)` | +45° |
| (−1,1) | `atan2(1,−1)` | +135° |
| (−1,−1) | `atan2(−1,−1)` | −135° |
| (1,−1) | `atan2(−1,1)` | −45° |

`Math.atan2` xử lý góc phần tư dù `x` âm. Nếu chỉ dùng `Math.atan(y/x)`, góc thường bị đưa về khoảng ±90° và thiếu thông tin để phân biệt QI với QIII, QII với QIV.

### 7.1. Không thay atan2 bằng atan(y/x) khi x = 0

`x = 0` khiến biểu thức `y/x` có thể tạo ±Infinity hoặc NaN theo IEEE 754 (hoặc ném `ArithmeticException` nếu thao tác chia là integer). Với `atan2`, hai tọa độ được đưa vào trực tiếp nên có quy tắc cụ thể:

```java
System.out.println(Math.atan2(1.0, 0.0));
// 1.5707963267948966 ~ +90°

System.out.println(Math.atan2(-1.0, 0.0));
// -1.5707963267948966 ~ -90°
```

Khi `x` và `y` quá lớn hoặc quá nhỏ, phép chia `y/x` riêng lẻ còn có thể overflow/underflow và làm mất thông tin về tỷ lệ; `atan2` là API chuẩn để xử lý cặp tọa độ, không bắt buộc tạo tỉ số trung gian.

### 7.2. Cách diễn giải góc trên hình học

Trong hệ tọa độ toán học thông thường, trục `+x` hướng phải và `+y` hướng lên; góc dương quay **ngược kim đồng hồ**. Nhưng trên nhiều hệ tọa độ màn hình, `y` tăng khi đi **xuống dưới**. Lúc đó một vector pixel `(dx,dy)` truyền vào `atan2(dy,dx)` có chiều góc dương hướng xuống, dễ bị người dùng cảm nhận như quay thuận chiều kim đồng hồ.

Hãy **xác định hệ trục trước khi diễn giải dấu góc**. Nếu muốn chuyển tọa độ màn hình có y hướng xuống về tọa độ toán học y hướng lên, một cách trong trường hợp trục không bị biến đổi khác là `Math.atan2(-dy, dx)`.

### 7.3. Giới hạn principal angle và chuẩn hóa góc

`atan2` trả góc chính `[−π,+π]`, không tự trả giá trị trong `[0,2π)`. Nếu cần góc từ 0° đến nhỏ hơn 360°, quy tắc thông thường là cộng `2π` cho giá trị âm:

```java
double angle = Math.atan2(y, x);
if (angle < 0.0) {
    angle += 2.0 * Math.PI;
}
```

Đây là **mảnh code** cho góc hữu hạn thông thường. Nếu `angle` bằng `-0.0`, điều kiện `angle < 0.0` là false; nếu nghiệp vụ cần chuẩn hóa bit dấu của zero, hãy bổ sung quy tắc `angle == 0.0 ? 0.0 : angle`. Nếu `angle` là `NaN`, phép so sánh `angle < 0.0` false và NaN vẫn giữ nguyên, cần kiểm tra đầu vào riêng.

Do phép làm tròn ở ranh giới ±π/2π, có thể cần chuẩn hóa thêm ở điểm gần `2π` nếu yêu cầu đầu ra **chắc chắn nhỏ hơn 2π**. Không dùng vòng lặp trừ 2π thiếu điều kiện với một số NaN/Infinity; nên định nghĩa rõ miền dữ liệu và điều kiện chuẩn hóa.

## 8. Bảng quyết định: hàm nào phù hợp?

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Biết `sin(theta)` và cần một góc chính | `asin(s)`, xác thực `s ∈ [−1,1]` |
| Biết `cos(theta)` và cần góc từ 0 đến π | `acos(c)`, xác thực `c ∈ [−1,1]` |
| Biết riêng giá trị `tan(theta)` và chỉ cần góc chính | `atan(t)` |
| Biết điểm/vector `(x,y)` và cần hướng/góc phần tư | **`atan2(y,x)`** |
| Cần kết quả ở degree | `Math.toDegrees(angleRadians)` |
| Cần xử lý input đang ở degree cho sin/cos/tan | `Math.toRadians(degrees)` trước |
| Cần tính toán có yêu cầu bit-reproducible về thư viện lượng giác | Xem `StrictMath` và hợp đồng JDK cụ thể |

Phân biệt **lấy góc từ tọa độ** với **lấy độ dài vector**. Nếu cần bán kính `r = √(x²+y²)`, API thích hợp là `Math.hypot(x,y)`; góc lấy bằng `atan2(y,x)`. `atan2` tự nó chỉ trả góc, không trả độ lớn vector.

## 9. Chương trình Java đầy đủ A — bốn hàm cơ bản

Tạo tệp **`InverseTrigBasics.java`**:

```java
import java.util.Locale;

public class InverseTrigBasics {
    public static void main(String[] args) {
        System.out.printf(Locale.US, "asin(0.5) = %.1f deg%n",
                Math.toDegrees(Math.asin(0.5)));
        System.out.printf(Locale.US, "acos(0.5) = %.1f deg%n",
                Math.toDegrees(Math.acos(0.5)));
        System.out.printf(Locale.US, "atan(1)   = %.1f deg%n",
                Math.toDegrees(Math.atan(1.0)));
        System.out.printf(Locale.US, "atan2(1,1) = %.1f deg%n",
                Math.toDegrees(Math.atan2(1.0, 1.0)));

        System.out.println(Double.isNaN(Math.asin(1.01)));
        System.out.println(Double.isNaN(Math.acos(-1.01)));
    }
}
```

Chạy với JDK 17+:

```bash
javac --release 17 InverseTrigBasics.java
java InverseTrigBasics
```

**Stdout** (formatter US với một chữ số phần lẻ):

```text
asin(0.5) = 30.0 deg
acos(0.5) = 60.0 deg
atan(1)   = 45.0 deg
atan2(1,1) = 45.0 deg
true
true
```

Giải thích: đối số `0.5` hợp lệ với `asin` và `acos`; `atan(1)` cho π/4; `atan2(1,1)` là vector góc 45°. Các đối số `1.01` và `−1.01` vượt miền của `asin`/`acos` nên trả NaN, được kiểm tra bằng `Double.isNaN`.

Không khẳng định giá trị nội bộ luôn là **30.0 radian** chỉ vì formatter in `30.0 deg`: kết quả đã được **đổi radian sang degree** và trình bày với một chữ số phần lẻ.

## 10. Chương trình Java đầy đủ B — bốn góc phần tư

Tạo **`Atan2Quadrants.java`**:

```java
import java.util.Locale;

public class Atan2Quadrants {
    private static void show(double x, double y) {
        double angleDegrees = Math.toDegrees(Math.atan2(y, x));
        System.out.printf(Locale.US,
                "(x=%4.1f, y=%4.1f) -> %6.1f deg%n",
                x, y, angleDegrees);
    }

    public static void main(String[] args) {
        show( 1.0,  1.0);
        show(-1.0,  1.0);
        show(-1.0, -1.0);
        show( 1.0, -1.0);
    }
}
```

Chạy:

```bash
javac --release 17 Atan2Quadrants.java
java Atan2Quadrants
```

**Stdout:**

```text
(x= 1.0, y= 1.0) ->   45.0 deg
(x=-1.0, y= 1.0) ->  135.0 deg
(x=-1.0, y=-1.0) -> -135.0 deg
(x= 1.0, y=-1.0) ->  -45.0 deg
```

Chú ý chữ ký `show(x,y)` dùng thứ tự tọa độ quen thuộc, nhưng bên trong gọi `Math.atan2(y,x)`. Đây là cách đặt tên rõ ràng để tránh truyền sai thứ tự.

### 10.1. Vì sao công thức atan(y/x) trả sai QIII?

Với `x=-1`, `y=-1`:

```java
double byRatio = Math.toDegrees(Math.atan(y / x));
// khoảng +45°, đánh mất góc phần tư

double byVector = Math.toDegrees(Math.atan2(y, x));
// khoảng -135°, đúng hướng của vector
```

Đây là **mảnh code** cần khai báo `x`, `y` trước khi biên dịch. Trong ứng dụng thực tế, ưu tiên `atan2` khi đã có tọa độ, không thử sửa bằng cách cộng π tự phát trong từng nhánh if khi API chuẩn xử lý được.

## 11. Signed zero: hai mẫu zero có thể dẫn tới hai góc khác nhau

IEEE 754 có `+0.0` và `-0.0`. Chúng bằng nhau theo primitive `==`, nhưng có bit dấu khác nhau. `asin` và `atan` giữ dấu zero của đối số; `atan2` dùng dấu zero để chọn phía đường biên góc.

Bảng quy tắc `atan2(y,x)` tại trục tọa độ:

| y | x | `Math.atan2(y,x)` |
| --- | --- | --- |
| `+0.0` | `+1.0` | `+0.0` |
| `-0.0` | `+1.0` | `-0.0` |
| `+0.0` | `-1.0` | `+π` gần nhất |
| `-0.0` | `-1.0` | `-π` gần nhất |
| `+1.0` | `+0.0` | `+π/2` gần nhất |
| `-1.0` | `+0.0` | `-π/2` gần nhất |

**Rất quan trọng:** `Math.atan2(+0.0, -1.0)` và `Math.atan2(-0.0, -1.0)` trả hai góc khác dấu, xấp xỉ +π và −π. Chúng là hai phía của **branch cut** ở trục x âm.

### 11.1. atan2(0,0) không mặc nhiên là NaN

Trong toán học, hướng của vector zero tại gốc tọa độ không được xác định theo góc hình học. Nhưng Java `Math.atan2` vẫn có **quy tắc floating-point xác định** cho ±0 ở hai tọa độ:

```java
System.out.println(Math.atan2(+0.0, +0.0)); // 0.0
System.out.println(Math.atan2(-0.0, +0.0)); // -0.0
System.out.println(Math.atan2(+0.0, -0.0)); // gần +pi
System.out.println(Math.atan2(-0.0, -0.0)); // gần -pi
```

**Không đồng nhất “API trả một giá trị” với “vector có hướng hình học hợp lệ”.** Nếu ứng dụng không chấp nhận vector zero, hãy kiểm tra từ đầu:

```java
if (x == 0.0 && y == 0.0) {
    throw new IllegalArgumentException("Zero vector has no direction");
}
double angle = Math.atan2(y, x);
```

Đây là **mảnh code minh họa**; đặt trong method có khai báo `x`, `y`. Điều kiện `== 0.0` nhận cả zero dương và zero âm. Nếu đầu vào có thể chứa NaN hoặc Infinity, cần định nghĩa thêm chính sách hữu hạn.

## 12. Vô cực và NaN: hành vi của từng phương thức

`Math`/`StrictMath` xử lý các giá trị đặc biệt theo hợp đồng Java, không cần được bao ngoài bằng `try/catch` cho `ArithmeticException` trong các trường hợp domain số thực thông thường.

| Trường hợp | Kết quả |
| --- | --- |
| `Math.asin(1.1)` | NaN (vượt miền) |
| `Math.acos(-1.1)` | NaN (vượt miền) |
| `Math.asin(Double.NaN)` | NaN |
| `Math.acos(Double.POSITIVE_INFINITY)` | NaN |
| `Math.atan(Double.NaN)` | NaN |
| `Math.atan(Double.POSITIVE_INFINITY)` | gần +π/2 |
| `Math.atan(Double.NEGATIVE_INFINITY)` | gần −π/2 |
| `Math.atan2(Double.NaN, 1.0)` | NaN |
| `Math.atan2(1.0, Double.NaN)` | NaN |
| `Math.atan2(1.0, +0.0)` | gần +π/2 |
| `Math.atan2(-1.0, +0.0)` | gần −π/2 |

Với cả hai tọa độ vô cực, `atan2` có thêm quy tắc đặc biệt, không thể suy đơn giản từ tỷ số vô cực/vô cực (vốn là NaN):

| y | x | Góc |
| --- | --- | --- |
| +∞ | +∞ | +π/4 |
| +∞ | −∞ | +3π/4 |
| −∞ | +∞ | −π/4 |
| −∞ | −∞ | −3π/4 |

Điều này là một ví dụ khác cho thấy **`atan2(y,x)` không phải lời gọi `atan(y/x)` đơn thuần**.

### 12.1. Vì sao không so NaN bằng ==?

`NaN == NaN` trả false theo primitive floating-point equality, kể cả khi cùng tham chiếu tới giá trị `Double.NaN` sau unbox. Để phát hiện giá trị không hợp lệ:

```java
double result = Math.acos(1.1);

if (Double.isNaN(result)) {
    System.out.println("outside domain");
}
```

Muốn ràng buộc cả vô cực, dùng `Double.isFinite(result)` trong Java 17. Nếu nhận đầu vào từ người dùng, thông báo nguyên nhân phù hợp: `acos(1.1)` do vượt miền, còn `atan2(Double.NaN,1)` do tọa độ không phải một số hợp lệ.

### 12.2. Dấu zero có thể bị mất ở những bước khác

Nếu trước `atan2` bạn tính tỉ số `y/x`, việc chia hoặc các phép toán khác có thể làm tròn, overflow, underflow hoặc thay đổi dấu zero. Do đó, truyền trực tiếp các tọa độ cho `atan2` giúp bảo toàn nhiều thông tin cần thiết về dấu/góc hơn so với tự tính `atan(y/x)`.

## 13. Chương trình Java đầy đủ C — những trường hợp đặc biệt

Lưu **`InverseTrigEdges.java`**:

```java
public class InverseTrigEdges {
    public static void main(String[] args) {
        System.out.println(Double.isNaN(Math.asin(1.01)));
        System.out.println(Double.isNaN(Math.acos(-1.01)));

        System.out.println(Math.asin(-0.0));
        System.out.println(Math.atan(-0.0));
        System.out.println(Math.acos(1.0));

        System.out.println(Math.atan2(+0.0, -1.0));
        System.out.println(Math.atan2(-0.0, -1.0));
        System.out.println(Math.atan2(+0.0, +1.0));
        System.out.println(Math.atan2(-0.0, +1.0));

        System.out.println(Math.atan2(1.0, +0.0));
        System.out.println(Math.atan2(-1.0, +0.0));

        System.out.println(Math.atan2(+0.0, +0.0));
        System.out.println(Double.isNaN(
                Math.atan2(Double.NaN, 1.0)));
    }
}
```

Chạy:

```bash
javac --release 17 InverseTrigEdges.java
java InverseTrigEdges
```

**Stdout trên JDK được kiểm thử:**

```text
true
true
-0.0
-0.0
0.0
3.141592653589793
-3.141592653589793
0.0
-0.0
1.5707963267948966
-1.5707963267948966
0.0
true
```

Các mốc đặc biệt như ±0, ±π, ±π/2, NaN được nêu trong hợp đồng API. Khi dùng `Math` trên các JDK/nền tảng khác nhau, **không nên lấy mọi chữ số thập phân của các góc không đặc biệt làm cam kết bit-for-bit**. `StrictMath` được định nghĩa chặt hơn cho một số hàm để tăng khả năng tái lập kết quả giữa các implementation.

## 14. Math so với StrictMath: trùng chức năng nhưng khác mức cam kết tái lập

Java cung cấp cả:

```java
double a = Math.asin(0.5);
double b = StrictMath.asin(0.5);

double c = Math.acos(0.5);
double d = StrictMath.acos(0.5);

double e = Math.atan(1.0);
double f = StrictMath.atan(1.0);

double g = Math.atan2(1.0, -1.0);
double h = StrictMath.atan2(1.0, -1.0);
```

Cả hai lớp dùng **radian**, cùng ý nghĩa toán học và cùng kiểu trả về `double`. Điểm khác không phải `Math` “sai”, mà là **chính sách đảm bảo kết quả theo thuật toán**.

### 14.1. Math: độ chính xác đủ theo đặc tả, implementation được linh hoạt

Java SE 17 `Math.asin`/`acos`/`atan` quy định sai số trong **1 ulp** của kết quả toán học chính xác, với yêu cầu **semi-monotonic**. `Math.atan2` cho phép sai số trong **2 ulp** và có yêu cầu semi-monotonic theo hợp đồng API.

`ulp` là “unit in the last place”, nói khái quát là khoảng cách giữa các giá trị floating-point biểu diễn được quanh một số. Sai số trong 1–2 ulp là một ràng buộc có ý nghĩa với binary64, **không phải** “sai số cố định nhỏ hơn 0.000001 radian cho mọi giá trị” hay “luôn làm tròn chính xác nhất”.

Các implementation của `Math` được phép sử dụng thuật toán hoặc chỉ thị tối ưu phù hợp với nền tảng, miễn là thỏa hợp đồng chính xác và special cases.

### 14.2. StrictMath: nhắm đến kết quả dễ tái lập hơn

Theo tài liệu Java SE 17, một số hàm của `StrictMath` (bao gồm các hàm lượng giác đang học) được ràng buộc theo thuật toán **fdlibm 5.3** (Freely Distributable Math Library) được mô tả trong API, để hỗ trợ kết quả **bit-for-bit phù hợp giữa các implementation Java tuân chuẩn**.

Điều đó không có nghĩa:

- Kết quả `StrictMath` biểu diễn số thực toán học bằng **độ chính xác vô hạn**.
- Mọi hàm của `StrictMath` đều có cùng cơ chế fdlibm hoặc cùng chính sách làm tròn trong mọi trường hợp.
- `Math.asin(x)` **phải luôn khác** `StrictMath.asin(x)`: trên nhiều JDK chúng có thể cho chính cùng bit.
- Dùng `StrictMath` làm phép so sánh `==` của những kết quả tính toán có tính ổn định tuyệt đối cho mọi thuật toán cộng/trừ/nhân/chia khác: những phép toán trung gian vẫn có rounding.

**Hướng chọn:** với ứng dụng thông thường cần hàm toán học có độ chính xác bảo đảm bởi JDK, `Math` là lựa chọn trực tiếp. Khi hệ thống yêu cầu kết quả lượng giác dễ đối chiếu **bit-for-bit giữa các implementation** cho cùng đầu vào (kiểm thử hồi quy, mô phỏng xác định có quy định), xem xét `StrictMath` và tài liệu phiên bản đích.

### 14.3. strictfp không thay thế StrictMath

Trong Java 17, ngữ nghĩa floating-point expression luôn được đánh giá nghiêm ngặt theo JLS, và modifier `strictfp` đã trở nên không cần thiết cho mục đích ép strict evaluation của phép toán primitive. Nhưng điều đó **không biến** `Math` thành các hàm fdlibm của `StrictMath`. Câu hỏi về **thuật toán thư viện tính asin/acos/atan/atan2** khác câu hỏi về **precision của các phép toán primitive**.

## 15. Chương trình Java đầy đủ D — cùng API ở Math và StrictMath

Tạo tệp **`MathVersusStrictMath.java`**:

```java
import java.util.Locale;

public class MathVersusStrictMath {
    static void show(String name, double math, double strict) {
        System.out.printf(Locale.US,
                "%s -> Math: %.6f, StrictMath: %.6f%n",
                name, math, strict);
    }

    public static void main(String[] args) {
        show("asin", Math.asin(0.5), StrictMath.asin(0.5));
        show("acos", Math.acos(0.5), StrictMath.acos(0.5));
        show("atan", Math.atan(1.0), StrictMath.atan(1.0));
        show("atan2", Math.atan2(1.0, -1.0),
                StrictMath.atan2(1.0, -1.0));
    }
}
```

Chạy:

```bash
javac --release 17 MathVersusStrictMath.java
java MathVersusStrictMath
```

**Stdout (làm tròn hiển thị tới 6 chữ số lẻ):**

```text
asin -> Math: 0.523599, StrictMath: 0.523599
acos -> Math: 1.047198, StrictMath: 1.047198
atan -> Math: 0.785398, StrictMath: 0.785398
atan2 -> Math: 2.356194, StrictMath: 2.356194
```

**Cách hiểu:** ví dụ cho cùng chữ số thập phân sau khi format **không chứng minh** hai kết quả giống hệt nhau ở mọi bit hoặc mọi đầu vào. Muốn đánh giá tính tái lập thật sự, cần so sánh raw bits `Double.doubleToRawLongBits` trên tập input đại diện và nhiều JDK/kiến trúc được hỗ trợ. Đừng xây dựng một bài kiểm thử bắt buộc `Math` và `StrictMath` luôn bit-equal khi hợp đồng không đòi điều ấy.

## 16. Ứng dụng: hướng của chuyển động, tọa độ và vector

Giả sử một vật đi từ `(x1,y1)` tới `(x2,y2)` trên hệ trục Descartes. Vector chuyển động:

```text
dx = x2 - x1
dy = y2 - y1
theta = atan2(dy, dx)
```

Ví dụ một chuyển động từ `(1,2)` tới `(−2,5)`:

```java
double x1 = 1.0;
double y1 = 2.0;
double x2 = -2.0;
double y2 = 5.0;

double dx = x2 - x1; // -3
double dy = y2 - y1; // +3

double heading = Math.atan2(dy, dx); // QII
System.out.printf(java.util.Locale.US,
        "%.1f degrees%n", Math.toDegrees(heading));
// 135.0 degrees
```

Đoạn này **minh họa một phương thức** (hoặc khối bên trong `main`), không phải một file Java đầy đủ riêng. Góc +135° đúng vì dx âm và dy dương.

### 16.1. Vector length ≠ angle

`Math.hypot(dx,dy)` cho độ lớn vector. Nó tránh một số nguy cơ overflow/underflow trung gian so với tự tính `Math.sqrt(dx*dx + dy*dy)`.

```java
double length = Math.hypot(dx, dy);
double angle = Math.atan2(dy, dx);
```

Hai kết quả lần lượt là **độ dài** và **góc**. Nếu vector bằng zero, độ dài bằng 0 nhưng hướng thường không được định nghĩa trong bài toán hình học, dù `atan2` của Java vẫn trả giá trị theo signed-zero inputs.

### 16.2. Chuẩn hóa nếu domain muốn [0,360)

`Math.toDegrees(Math.atan2(dy,dx))` trả gần `[−180,180]`. Nếu muốn hướng từ 0 đến nhỏ hơn 360 độ:

```java
double angleDeg = Math.toDegrees(Math.atan2(dy, dx));
if (angleDeg < 0.0) {
    angleDeg += 360.0;
}
```

Điều này phù hợp với input hữu hạn trong tình huống thông thường. Với signed zero và các điểm ranh giới −180/+180, quy ước chính xác cần được mô tả và kiểm thử. Nếu hệ tọa độ màn hình dùng y tăng xuống dưới, chiều góc cũng phải được điều chỉnh trước khi hiển thị.

## 17. Những lỗi thường gặp khi dùng inverse trig

| Sai lầm | Điều gì xảy ra | Cách đúng |
| --- | --- | --- |
| Cho rằng `asin(0.5)` trả `30` | Kết quả là **radian** | Dùng `toDegrees` khi cần degree |
| Gọi `asin(30)` với ý nghĩa 30° | 30 ngoài miền [−1,1] → NaN | Phân biệt giá trị sin với góc |
| Dùng `acos(1.0001)` rồi mong 0 | Đối số vượt miền → NaN | Xác thực input; clamp chỉ theo chính sách sai số |
| Dùng `atan(y/x)` tìm góc phần tư | Mất dấu riêng x,y | Dùng `atan2(y,x)` |
| Gọi `atan2(x,y)` | Đổi nhầm tham số | Hàm **atan2(y,x)** |
| Dùng `atan2(0,0)` như hướng vector hợp lệ | API trả số theo signed zero nhưng hình học không có hướng duy nhất | Kiểm tra vector zero nếu cần |
| Bỏ qua zero âm | Có thể đổi ±π ở branch cut | Bảo toàn signed zero hoặc chuẩn hóa có chủ đích |
| So NaN bằng `== Double.NaN` | Luôn false | `Double.isNaN` |
| Gán `Math.atan(1.0)` trực tiếp cho `float` | Type trả `double`, cần cast và có thể mất precision | Dùng `double` nếu không có yêu cầu đặc biệt |
| Coi `asin(sin(t))==t` luôn đúng | Sin có tính tuần hoàn, asin chỉ trả principal value | Xem miền và điều kiện duy nhất |
| Gán “Math lúc nào cũng nhanh hơn StrictMath” | Hiệu năng phụ thuộc JDK/hardware | Benchmark trên môi trường thật |
| Coi `StrictMath` luôn chính xác tuyệt đối | Vẫn là `double` có rounding | Hiểu fdlibm và precision |
| So kết quả góc bằng `==` với số thập phân hiển thị | Sai số biểu diễn/rounding | Chọn tolerance theo đơn vị và độ chính xác bài toán |

Một bẫy tinh tế là **dùng sin và cos được tính từ góc rồi đảo lại**: `Math.atan2(Math.sin(theta), Math.cos(theta))` trả **phiên bản chuẩn hóa của theta về góc chính**, không bảo đảm đúng theta gốc nếu theta ngoài `[−π,π]`. Các sai số floating point cũng có thể xuất hiện gần ranh giới và tại bội của π.

## 18. Thiết kế kiểm thử đúng cho toán học dấu phẩy động

**Không kiểm tra mọi giá trị bằng một epsilon cố định không có ngữ cảnh.** Nếu ứng dụng chấp nhận sai số về góc là 0,01 độ, hãy đổi các giá trị cần kiểm tra sang degree hoặc đổi dung sai sang radian, đồng thời xác định cách so sánh tại đường biên ±180°.

Các bài kiểm thử nên gồm:

1. Giá trị chuẩn: `asin(0.5)` ≈ 30°, `acos(0.5)` ≈ 60°, `atan(1)` ≈ 45°.
2. Hai biên miền: `asin(−1)`, `asin(1)`, `acos(−1)`, `acos(1)`.
3. Ngoài miền: `asin(1.01)`, `acos(−1.01)` → NaN.
4. Bốn góc phần tư: `atan2(±1, ±1)`.
5. Trục tọa độ: `atan2(±0.0, ±1.0)` và `atan2(±1.0, ±0.0)`.
6. Gốc tọa độ: xác định chính sách xử lý zero vector.
7. Giá trị đặc biệt: ±Infinity, NaN.
8. Tọa độ rất lớn/rất nhỏ: không tự chia `y/x` hoặc bình phương mất kiểm soát.
9. Ranh giới ±π: quan sát branch cut và quy ước chuẩn hóa góc.
10. Đối chiếu `Math` và `StrictMath` theo yêu cầu tái lập thực sự, không dựa trên chuỗi đã làm tròn.

### 18.1. Khoảng cách góc phải tính theo vòng tròn khi cần

Hai góc `179.9°` và `−179.9°` cách nhau **0.2° theo hướng ngắn nhất**, không phải gần 359.8° như phép trừ số thập phân thông thường. Khi cần so **hướng trên vòng tròn**, hãy định nghĩa phép tính chênh lệch góc có chuẩn hóa mod 360°/2π.

Một công thức hữu ích cho độ lệch góc principal trong radian là:

```java
static double angleDistance(double a, double b) {
    return Math.abs(Math.atan2(
            Math.sin(a - b), Math.cos(a - b)));
}
```

Đây là **mảnh phương thức** cần đặt trong một class; nó hữu ích cho góc hữu hạn bình thường nhưng phép trừ `a-b` với số cực lớn/Infinity có thể tràn hoặc tạo NaN, và kết quả vẫn chịu rounding. Nếu hệ thống xử lý góc rất lớn hoặc đặc biệt, chuẩn hóa góc cẩn thận trước và xác thực `Double.isFinite`.

## 19. Bài tập tự luyện có đáp án

### Bài 1 — Đọc đúng ý nghĩa hàm

`Math.asin(0.5)` trả khoảng bao nhiêu radian và bao nhiêu độ?

**Đáp án:** gần `0.5235987756` radian, tương đương `30°`. Dùng `Math.toDegrees` nếu muốn kết quả độ.

### Bài 2 — Góc của acos

`Math.acos(0.5)` và `Math.acos(-1.0)` tương ứng bao nhiêu độ?

**Đáp án:** `60°` và `180°`. `acos` trả góc chính trong `[0°,180°]`.

### Bài 3 — Góc của atan

`Math.atan(1.0)` tương ứng bao nhiêu độ?

**Đáp án:** `45°`, tức gần π/4 radian.

### Bài 4 — Giá trị ngoài miền

`Math.asin(2.0)` và `Math.acos(-2.0)` ném exception hay cho gì?

**Đáp án:** trả `NaN`; kiểm tra bằng `Double.isNaN`. Không có góc thực mà sin/cos bằng ±2.

### Bài 5 — Bốn góc phần tư

Với tọa độ `(x,y) = (−1,1)` và `(−1,−1)`, gọi `atan2` thế nào, kết quả góc gì?

**Đáp án:** `Math.atan2(1,-1)` ≈ +135°; `Math.atan2(-1,-1)` ≈ −135°. `y` là tham số đầu tiên.

### Bài 6 — Vì sao không dùng atan(y/x)?

Với vector `(−1,−1)`, `atan(y/x)` có thể trả khoảng `+45°`, còn `atan2(y,x)` trả `−135°`. Tại sao?

**Đáp án:** phép chia mất dấu riêng của hai tọa độ: `(−1)/(−1) = +1`, giống tỉ số của vector `(1,1)`. `atan2` vẫn thấy x âm và y âm nên chọn QIII.

### Bài 7 — Signed zero trên trục x âm

`atan2(+0.0,-1.0)` và `atan2(-0.0,-1.0)` là góc gì?

**Đáp án:** gần +π và −π. Dấu zero quyết định phía branch cut.

### Bài 8 — Zero vector

`Math.atan2(0.0,0.0)` có cho NaN không? Có nên xem đó là hướng hình học hợp lệ không?

**Đáp án:** theo Java, cho `+0.0` với hai zero dương. Nhưng vector (0,0) không có hướng xác định, nên ứng dụng cần kiểm tra riêng nếu yêu cầu vector khác 0.

### Bài 9 — Infinity

`Math.atan(Double.POSITIVE_INFINITY)` và `Math.atan(Double.NEGATIVE_INFINITY)` tiến đến góc nào?

**Đáp án:** gần +π/2 và −π/2; theo contract Java, trả giá trị double gần nhất với hai mốc đó.

### Bài 10 — Hai tọa độ infinity

`Math.atan2(Double.POSITIVE_INFINITY,Double.NEGATIVE_INFINITY)` gần góc bao nhiêu?

**Đáp án:** +3π/4 = 135°. `atan(y/x)` không thay thế được vì `Infinity / -Infinity` là NaN.

### Bài 11 — Math và StrictMath

Có được khẳng định `Math.atan2(y,x) == StrictMath.atan2(y,x)` với **mọi** giá trị không? Vì sao?

**Đáp án:** không nên khẳng định như vậy. `Math` cho phép implementation linh hoạt trong giới hạn chính xác; `StrictMath` có ràng buộc thuật toán fdlibm để hỗ trợ tái lập bit cho một số method.

### Bài 12 — Radian/degree

Viết một biểu thức Java để lấy góc độ của vector `(x,y)`.

**Đáp án:** `Math.toDegrees(Math.atan2(y,x))`. Nếu muốn góc trong [0,360), thêm chuẩn hóa theo yêu cầu và kiểm tra signed zero/ràng buộc biên.

### Bài 13 — Góc principal

Vì sao `asin(sin(150°))` không cho 150°?

**Đáp án:** `sin(150°)=sin(30°)`, trong khi `asin` chỉ trả góc trong [−90°,90°], nên kết quả chính là gần 30°; phải đổi 150° sang radian trước khi gọi sin.

### Bài 14 — Tọa độ màn hình

Trên màn hình, y tăng hướng xuống. Khi rê chuột sang phải và xuống, `atan2(dy,dx)` trả góc dương hay âm? Muốn góc dương theo chiều ngược kim đồng hồ toán học phải làm gì?

**Đáp án:** nếu dx>0 và dy>0 thì `atan2(dy,dx)` trả góc dương trong góc phần tư I của hệ tọa độ số truyền vào; trên màn hình, nó trông như hướng xuống-phải. Muốn quy ước y hướng lên, dùng `atan2(-dy,dx)` nếu không có biến đổi tọa độ khác.

### Bài 15 — Kiểm tra độ chính xác

Nếu ứng dụng cần so góc ở gần +180° và −180°, vì sao `Math.abs(a-b)` có thể đánh giá sai “gần nhau”?

**Đáp án:** khoảng góc quanh vòng tròn có tính chu kỳ. Hai hướng ±179.9° chỉ chênh 0.2° theo cung ngắn; cần chuẩn hóa chênh lệch góc modulo 360° hoặc 2π theo contract của ứng dụng.

## 20. Checklist và tài liệu tham khảo

- [ ] Tôi nhớ `asin` và `acos` nhận đối số trong [−1,1], còn `atan` nhận số thực ngoài khoảng đó.
- [ ] Tôi biết khoảng kết quả chính của từng hàm và đơn vị **radian**.
- [ ] Tôi hiểu `asin(sin(theta))`, `acos(cos(theta))`, `atan(tan(theta))` không luôn khôi phục theta gốc.
- [ ] Tôi luôn viết `atan2(y,x)` khi có tọa độ, **không đảo tham số**.
- [ ] Tôi không dùng `atan(y/x)` thay cho `atan2` khi cần phân biệt góc phần tư và xử lý x=0.
- [ ] Tôi kiểm tra input của `asin`/`acos` thay vì âm thầm che giấu dữ liệu sai.
- [ ] Tôi biết `asin`/`atan` bảo toàn signed zero; `atan2` có quy tắc cho ±0 ở các trục.
- [ ] Tôi biết `atan2(0,0)` có output theo IEEE 754 nhưng vector zero có thể bị coi là không hợp lệ theo nghiệp vụ.
- [ ] Tôi kiểm tra `Double.isNaN`/`Double.isFinite` với input và output phù hợp.
- [ ] Tôi phân biệt yêu cầu chính xác 1 ulp/2 ulp của `Math` với ràng buộc fdlibm của `StrictMath`.
- [ ] Tôi tự viết được ví dụ vector dx/dy và đổi kết quả sang độ.
- [ ] Tôi kiểm thử bốn phần tư, trục tọa độ, ±π, signed zero, NaN và infinity.
- [ ] Tôi hiểu bài toán góc trên **vòng tròn** khác so sánh hai số thực trên một trục thẳng.
- [ ] Tôi đã chạy các chương trình Java 17+ và đối chiếu stdout.

**Tài liệu chính thức Java SE 17:**

- [Math API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `asin`, `acos`, `atan`, `atan2`, `toDegrees`, `toRadians`, đặc tả về ulp và special cases.
- [StrictMath API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html): các hàm tương ứng, quy tắc fdlibm và tính tái lập.
- [Double API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): `NaN`, ±Infinity, signed zero, `doubleToRawLongBits`.
- [JLS 17 `4.2.3 Floating-Point Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): số thực Java.
- [JLS 17 `15.4 Floating-Point Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.4): precision, rounding và ngữ nghĩa biểu thức trong Java 17.

**Kết luận:** `asin`, `acos`, `atan` tìm **góc chính** từ giá trị lượng giác, còn `atan2(y,x)` tìm **hướng vector dựa trên cả hai tọa độ**. Trong code hình học Java, hãy ưu tiên `atan2` khi có x/y, nhớ radian, xem xét signed zero/NaN và chọn `Math` hay `StrictMath` theo đúng yêu cầu về độ chính xác và tái lập.