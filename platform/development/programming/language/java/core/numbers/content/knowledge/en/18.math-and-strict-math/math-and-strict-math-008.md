# `nextUp`, `nextDown`, `nextAfter` và `ulp` trong Java

Khi làm việc với `float` và `double`, giữa hai số thực gần nhau không phải lúc nào cũng tồn tại một giá trị dấu phẩy động có thể biểu diễn. Java cung cấp bốn phương thức trong `Math` và `StrictMath` để tìm **giá trị biểu diễn liền kề** và **khoảng cách ở độ chính xác máy**:

- `nextUp(x)`: giá trị biểu diễn kế tiếp theo hướng dương vô cực.
- `nextDown(x)`: giá trị biểu diễn kế tiếp theo hướng âm vô cực.
- `nextAfter(start, direction)`: giá trị biểu diễn kế tiếp tính từ `start` theo hướng của `direction`.
- `ulp(x)`: kích thước một *unit in the last place* (ULP) tại `x`.

Chúng phục vụ kiểm thử biên, nghiên cứu sai số và thuật toán số; **không** phải các hàm “cộng một chút bất kỳ” hoặc làm tròn số thập phân để hiển thị.

## 1. Vì sao cần số biểu diễn liền kề?

Java sử dụng định dạng nhị phân IEEE 754 cho hai kiểu dấu phẩy động phổ biến:

| Kiểu | Độ dài | Số bit có nghĩa hữu hiệu | Ví dụ về ULP tại `1.0` |
|---|---:|---:|---|
| `float` | 32 bit | 24 bit | `2^-23` ≈ `1.1920929e-7` |
| `double` | 64 bit | 53 bit | `2^-52` ≈ `2.220446049250313e-16` |

Một tập hữu hạn các mẫu bit không thể biểu diễn mọi số thực. Ví dụ: `1.0` là giá trị `double` chính xác, nhưng số `double` lớn hơn nó ngay lập tức là:

```text
1.0
↓ giá trị double kế tiếp
0x1.0000000000001p0  =  1.0000000000000002 (dạng thập phân được làm ngắn khi in)
```

Ở đây `0x...p...` là ký pháp số dấu phẩy động nhị phân dạng thập lục phân của Java: phần sau `p` là lũy thừa của **2**, không phải 10. `Double.toHexString(...)` cho phép quan sát các bước biểu diễn chính xác hơn việc in dạng thập phân thông thường.

Khoảng cách giữa hai số liền kề **không cố định** trên toàn miền: quanh số có độ lớn lớn hơn, các bước thường lớn hơn; quanh số nhỏ, các bước nhỏ hơn, xuống tới **subnormal**. Bởi vậy, giả định rằng luôn có thể dùng `x + 1e-15` để tới số tiếp theo là sai: phép cộng có thể không đổi `x`, nhảy qua nhiều giá trị, hoặc tạo kết quả không phù hợp với kiểu dữ liệu.

> Trong bài này, “liền kề” nghĩa là **không có số `float`/`double` có thể biểu diễn ở giữa** theo thứ tự số học. Nó không có nghĩa là hai số nguyên hoặc hai số thập phân liên tiếp.

## 2. API và nguyên tắc chọn hướng

Các overload chính của `java.lang.Math`:

```java
public static double nextUp(double d);
public static float  nextUp(float f);

public static double nextDown(double d);
public static float  nextDown(float f);

public static double nextAfter(double start, double direction);
public static float  nextAfter(float start, double direction);

public static double ulp(double d);
public static float  ulp(float f);
```

`StrictMath` cũng cung cấp các phương thức tương ứng với cùng ý nghĩa. Điểm dễ bỏ qua là overload `nextAfter(float, double)` nhận **`direction` kiểu `double`** nhưng **trả `float`**: giá trị *start* quyết định lưới số biểu diễn được bước qua.

Với giá trị bắt đầu hữu hạn và không ở trường hợp biên:

| Lời gọi | Cách hiểu |
|---|---|
| `Math.nextUp(x)` | Một bước sang phải trên trục số |
| `Math.nextDown(x)` | Một bước sang trái trên trục số |
| `Math.nextAfter(x, y)`, với `y > x` | Một bước từ `x` về phía `y`, tương tự `nextUp(x)` |
| `Math.nextAfter(x, y)`, với `y < x` | Một bước từ `x` về phía `y`, tương tự `nextDown(x)` |
| `Math.nextAfter(x, y)`, với `x == y` | Trả chính `direction` (chi tiết quan trọng khi hai số 0 khác dấu) |
| `Math.ulp(x)` | Độ lớn ULP tại `x`, luôn không âm với đầu vào hữu hạn |

`nextAfter(start, direction)` **không nhảy thẳng tới `direction`**; nó di chuyển đúng một bước trên lưới giá trị thuộc kiểu của `start`, trừ khi hai giá trị đã bằng nhau theo phép so sánh số học (hoặc gặp `NaN`/biên đặc biệt).

### Phân biệt `nextAfter` và `nextUp`/`nextDown`

```java
double x = 1.0;

Math.nextAfter(x, 2.0); // Cùng kết quả với Math.nextUp(x)
Math.nextAfter(x, 0.0); // Cùng kết quả với Math.nextDown(x)
Math.nextAfter(x, x);   // 1.0: đã tới hướng đích
```

Đây là **đoạn minh họa**, không phải lớp Java độc lập. Khi chỉ cần hướng cố định, `nextUp`/`nextDown` thể hiện mục đích trực tiếp hơn; khi hướng phụ thuộc đích, `nextAfter` cho phép biểu đạt thuật toán tổng quát.

## 3. Chương trình Java 17+ chạy và kiểm chứng

Tạo tệp `FloatingNeighborsDemo.java` với nội dung:

```java
public class FloatingNeighborsDemo {
    public static void main(String[] args) {
        double x = 1.0;
        System.out.println("nextUp(1.0): " + Double.toHexString(Math.nextUp(x)));
        System.out.println("nextDown(1.0): " + Double.toHexString(Math.nextDown(x)));
        System.out.println("nextAfter(1.0, 2.0): " + Double.toHexString(Math.nextAfter(x, 2.0)));
        System.out.println("nextAfter(1.0, 0.0): " + Double.toHexString(Math.nextAfter(x, 0.0)));
        System.out.println("ulp(1.0): " + Double.toHexString(Math.ulp(x)));
        System.out.println("gap above: " + Double.toHexString(Math.nextUp(x) - x));
        System.out.println("gap below: " + Double.toHexString(x - Math.nextDown(x)));
        System.out.println("nextUp(-0.0): " + Double.toHexString(Math.nextUp(-0.0)));
        System.out.println("nextDown(+0.0): " + Double.toHexString(Math.nextDown(+0.0)));
        System.out.println("nextAfter(+0.0, -0.0): " + Double.toHexString(Math.nextAfter(+0.0, -0.0)));
        System.out.println("ulp(0.0): " + Double.toHexString(Math.ulp(0.0)));
        System.out.println("nextUp(MAX_VALUE): " + Math.nextUp(Double.MAX_VALUE));
        System.out.println("nextDown(+INFINITY) == MAX_VALUE: "
                + (Math.nextDown(Double.POSITIVE_INFINITY) == Double.MAX_VALUE));
        float f = 1.0f;
        System.out.println("nextAfter(1.0f, 2.0): " + Float.toHexString(Math.nextAfter(f, 2.0)));
        System.out.println("ulp(1.0f): " + Float.toHexString(Math.ulp(f)));
        System.out.println("NaN: " + Double.isNaN(Math.nextUp(Double.NaN)));
        System.out.println("StrictMath agrees: " + (StrictMath.nextUp(x) == Math.nextUp(x)));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 FloatingNeighborsDemo.java
java FloatingNeighborsDemo
```

Stdout đã được đối chiếu bằng cách biên dịch và chạy chương trình:

```text
nextUp(1.0): 0x1.0000000000001p0
nextDown(1.0): 0x1.fffffffffffffp-1
nextAfter(1.0, 2.0): 0x1.0000000000001p0
nextAfter(1.0, 0.0): 0x1.fffffffffffffp-1
ulp(1.0): 0x1.0p-52
gap above: 0x1.0p-52
gap below: 0x1.0p-53
nextUp(-0.0): 0x0.0000000000001p-1022
nextDown(+0.0): -0x0.0000000000001p-1022
nextAfter(+0.0, -0.0): -0x0.0p0
ulp(0.0): 0x0.0000000000001p-1022
nextUp(MAX_VALUE): Infinity
nextDown(+INFINITY) == MAX_VALUE: true
nextAfter(1.0f, 2.0): 0x1.000002p0
ulp(1.0f): 0x1.0p-23
NaN: true
StrictMath agrees: true
```

**Điểm quan trọng từ kết quả:**

1. Kết quả `nextUp(1.0)` là số `double` liền trên `1.0`; `nextDown(1.0)` là số liền dưới. `nextAfter` đưa ra cùng hai số nếu hướng đích lần lượt ở trên hoặc dưới.
2. `ulp(1.0)` bằng bước **phía trên** tại `1.0`, nhưng bước **phía dưới** chỉ bằng một nửa (vì `1.0` là lũy thừa chính xác của 2, nằm ở ranh giới hai vùng bước).
3. `nextUp(-0.0)` và `nextDown(+0.0)` đi tới hai giá trị subnormal nhỏ nhất khác 0, lần lượt dương và âm.
4. `nextAfter(+0.0, -0.0)` trả `-0.0` dù phép so sánh `+0.0 == -0.0` là `true`; cách ghi bằng hex giúp nhìn thấy dấu.
5. Ở biên trên hữu hạn, bước kế tiếp của `Double.MAX_VALUE` theo chiều tăng là `+Infinity`.
6. Overload `float` đi trên lưới 32 bit nên bước quanh `1.0f` lớn hơn bước của `double`.

## 4. Hiểu chính xác `ulp(x)`

ULP là đơn vị có trọng số của chữ số cuối trong biểu diễn dấu phẩy động tại độ lớn đang xét. Trong miền **normal**, bước thường có dạng:

- `double`, có độ chính xác 53 bit: khoảng `2^(e - 52)`;
- `float`, có độ chính xác 24 bit: khoảng `2^(e - 23)`,

với `e` là số mũ nhị phân của khoảng giá trị đang xét. Ở vùng số **subnormal**, độ giãn cách cố định ở mức nhỏ nhất của định dạng.

Ví dụ:

```java
Math.ulp(1.0);     // double: 2^-52
Math.ulp(2.0);     // double: 2^-51
Math.ulp(1.0f);    // float: 2^-23
Math.ulp(2.0f);    // float: 2^-22
Math.ulp(0.0);     // Double.MIN_VALUE (số double dương nhỏ nhất khác 0)
Math.ulp(0.0f);    // Float.MIN_VALUE  (số float dương nhỏ nhất khác 0)
```

Đây là các biểu thức minh họa; để kiểm tra đầu ra có thể in bằng `Double.toHexString` hoặc `Float.toHexString`.

### `ulp(x)` không luôn bằng `nextUp(x) - x`

Một ngộ nhận dễ gây lỗi kiểm thử là áp dụng đẳng thức `Math.ulp(x) == Math.nextUp(x) - x` với **mọi** `x`. Ở ranh giới các lũy thừa của 2 hoặc khi đổi dấu, khoảng cách liền kề hai bên có thể khác nhau.

Ví dụ với `x = 1.0`:

| Đại lượng | Kết quả chính xác |
|---|---|
| `Math.ulp(1.0)` | `2^-52` |
| `Math.nextUp(1.0) - 1.0` | `2^-52` |
| `1.0 - Math.nextDown(1.0)` | `2^-53` |

Với `x = -1.0`, tình huống đảo chiều: đi về phía `+∞` tiến gần 0 hơn và có bước `2^-53`, còn đi về phía `-∞` có bước `2^-52`; trong khi `Math.ulp(-1.0)` vẫn bằng `2^-52`. Do đó nếu thuật toán cần **khoảng cách ở một hướng cụ thể**, dùng hai hàm láng giềng để đo khoảng cách ở hướng đó, kết hợp xử lý các giá trị đặc biệt.

Không lấy `ulp(x)` làm “sai số tuyệt đối bảo đảm” của mọi phép tính. Sai số phụ thuộc phép toán, thuật toán, độ lớn các toán hạng, tình trạng mất chữ số có nghĩa và số bước tính. Một ULP có thể hữu ích cho việc đo sai khác biểu diễn, nhưng quy tắc chấp nhận sai số phải đến từ yêu cầu của bài toán.

### Vì sao không có một epsilon cố định?

`Math.ulp(0.0)` bằng `Double.MIN_VALUE`, cực nhỏ; trong khi `Math.ulp(1.0)` lớn hơn nhiều, còn `Math.ulp(1e20)` lại lớn hơn nữa. Ngay cả `Math.ulp(1.0)` cũng không có ý nghĩa là mọi phép tính đều có sai số tối đa đúng từng ấy.

Trong kiểm thử số học, việc so sánh theo sai số tuyệt đối, sai số tương đối hoặc số ULP phải cân nhắc miền dữ liệu và các trường hợp 0, vô cực, `NaN`, tràn/thiếu độ lớn. Đừng áp dụng một `epsilon` cố định chỉ vì nó có tên quen thuộc.

## 5. Những biên đặc biệt phải kiểm thử

`float` và `double` có hai số 0 (`+0.0`, `-0.0`), hai vô cực, `NaN` và các giá trị subnormal. Vì vậy không thể suy luận mọi trường hợp chỉ bằng bảng số thực thông thường.

| Đầu vào | Kết quả hoặc hành vi |
|---|---|
| `Math.nextUp(+0.0)` hoặc `Math.nextUp(-0.0)` | `Double.MIN_VALUE` |
| `Math.nextDown(+0.0)` hoặc `Math.nextDown(-0.0)` | `-Double.MIN_VALUE` |
| `Math.nextAfter(+0.0, -0.0)` | `-0.0` (trả đúng `direction`) |
| `Math.nextAfter(-0.0, +0.0)` | `+0.0` (trả đúng `direction`) |
| `Math.nextUp(Double.MAX_VALUE)` | `Double.POSITIVE_INFINITY` |
| `Math.nextDown(-Double.MAX_VALUE)` | `Double.NEGATIVE_INFINITY` |
| `Math.nextDown(Double.POSITIVE_INFINITY)` | `Double.MAX_VALUE` |
| `Math.nextUp(Double.NEGATIVE_INFINITY)` | `-Double.MAX_VALUE` |
| `Math.nextUp(Double.POSITIVE_INFINITY)` | `Double.POSITIVE_INFINITY` |
| `Math.nextDown(Double.NEGATIVE_INFINITY)` | `Double.NEGATIVE_INFINITY` |
| `Math.nextAfter(Double.NaN, 1.0)` | `NaN` |
| `Math.nextAfter(1.0, Double.NaN)` | `NaN` |
| `Math.ulp(Double.NaN)` | `NaN` |
| `Math.ulp(Double.POSITIVE_INFINITY)` | `Double.POSITIVE_INFINITY` |

Với overload `float`, thay các hằng tương ứng bằng `Float.MIN_VALUE`/`Float.MAX_VALUE` và dùng kết quả kiểu `float`. Đừng nhầm tên `Double.MIN_VALUE`: đây là **số dương nhỏ nhất khác 0** có thể biểu diễn bằng `double`, **không phải số âm nhỏ nhất**. Số `double` hữu hạn âm có độ lớn lớn nhất là `-Double.MAX_VALUE`.

### Số 0 có dấu và `nextAfter`

`+0.0 == -0.0` là `true` trong phép so sánh số học của Java, nhưng dạng bit và một vài hành vi số học của chúng khác nhau. Khi `start` và `direction` bằng nhau, đặc tả `nextAfter` trả chính tham số `direction`, vì vậy:

```java
double result = Math.nextAfter(+0.0, -0.0);
boolean negativeZero =
        Double.doubleToRawLongBits(result) == Double.doubleToRawLongBits(-0.0);
// negativeZero == true
```

Đoạn này là mã minh họa đặt trong phương thức. Nếu dùng `== 0.0` để kiểm tra kết quả, bạn **không thể phân biệt** hai dấu 0. Muốn quan sát bit, dùng `Double.doubleToRawLongBits`, `Float.floatToRawIntBits` hoặc biểu diễn hex thích hợp.

### Subnormal và giới hạn nhỏ nhất

Với `double`:

- `Double.MIN_NORMAL` là số **normal dương nhỏ nhất** (xấp xỉ `2.225e-308`).
- `Double.MIN_VALUE` là số **subnormal dương nhỏ nhất khác 0** (xấp xỉ `4.9e-324`).
- `Math.nextUp(0.0) == Double.MIN_VALUE`.
- `Math.nextDown(Double.MIN_VALUE)` trả `+0.0` vì giá trị có thể biểu diễn gần hơn theo hướng giảm là số 0.
- `Math.ulp(0.0)` và `Math.ulp(Double.MIN_VALUE)` bằng `Double.MIN_VALUE`.

Đây là lý do các giá trị rất nhỏ không có cùng số chữ số có nghĩa hữu hiệu như các giá trị normal. Khi đi qua ranh giới normal/subnormal, phải kiểm thử vì độ chính xác tương đối thay đổi.

## 6. `Math` và `StrictMath` khác nhau thế nào trong bài này?

Các phương thức `nextUp`, `nextDown`, `nextAfter` và `ulp` đều có trên `Math` và `StrictMath` với cùng quy tắc xử lý giá trị lân cận. Bạn có thể viết:

```java
double a = Math.nextAfter(1.0, 2.0);
double b = StrictMath.nextAfter(1.0, 2.0);
// a và b cùng là giá trị double liền trên 1.0
```

Đây là mã minh họa dùng trong lớp/phương thức. `StrictMath` thường được nhắc tới khi quan tâm tính tái lập kết quả của các phép toán số học; tuy nhiên với **bốn phép bước trên lưới biểu diễn** đang học, quy tắc biên và kiểu trả về là trọng tâm. Đừng suy rộng từ nhóm hàm này sang mọi hàm lượng giác hoặc hàm siêu việt mà chưa đọc hợp đồng API cụ thể.

## 7. Ứng dụng thực tế

### 7.1. Kiểm thử sát ranh giới của điều kiện

Giả sử quy tắc yêu cầu một giá trị `double` phải **nhỏ hơn hoặc bằng** `limit`:

```java
static boolean withinLimit(double value, double limit) {
    return value <= limit;
}
```

Đây là phương thức minh họa. Với `limit = 1.0`, một bộ kiểm thử biên có thể dùng ba giá trị:

```java
double limit = 1.0;
boolean below = withinLimit(Math.nextDown(limit), limit); // true
boolean exact = withinLimit(limit, limit);                // true
boolean above = withinLimit(Math.nextUp(limit), limit);  // false
```

Từng giá trị kiểm thử là một điểm có thể biểu diễn được; không cần đoán “một số rất nhỏ” để cộng/trừ. Khi `limit` là vô cực, `NaN` hoặc có thể phát sinh overflow, cần định nghĩa thêm kỳ vọng và test riêng.

### 7.2. Bước về một mốc đích

Nếu cần biết **bước đầu tiên** từ một số `double` về phía mốc:

```java
double current = 1.0;
double target = 2.0;
double step = Math.nextAfter(current, target);
// step == Math.nextUp(current)
```

Một bước của `nextAfter` thường rất nhỏ; đừng dùng nó để duyệt tùy ý từ `1.0` đến `2.0`. Giữa hai giá trị này có số lượng cực lớn các số `double`, và thuật toán duyệt từng số có thể quá chậm. Nếu thực sự cần lặp, phải có giới hạn số bước, điều kiện kết thúc và xử lý `NaN`, vô cực, trường hợp không tiến triển.

### 7.3. Đo mức chênh trên lưới số

`ulp(...)` có thể giúp diễn giải mức độ sai khác gần một tham chiếu, ví dụ quan sát sự khác biệt giữa `1.0` với số `double` ngay phía trên:

```java
double baseline = 1.0;
double observed = Math.nextUp(baseline);

double delta = observed - baseline;
double oneUlpAtBaseline = Math.ulp(baseline);
// delta == oneUlpAtBaseline, đúng cho baseline = 1.0
```

Ở ví dụ cụ thể này, sai khác đúng một ULP tại `baseline`; với giá trị ở biên lũy thừa hai hoặc số âm, không mặc định rằng sai khác hai láng giềng theo **mọi hướng** đều bằng `ulp(baseline)`. Muốn đo khoảng cách ULP chính xác cho số ở miền rộng, thường phải so sánh biểu diễn bit đã chuẩn hóa theo thứ tự và xử lý `NaN`, signed zero cũng như vô cực.

## 8. Các lỗi thường gặp

**Nhầm 1 — `Math.nextUp(x)` là `x + Math.ulp(x)` trong mọi trường hợp.** Công thức cộng có thể hữu ích cho một số điểm, nhưng thất bại ở các biên như vô cực, `NaN`, và không mô tả nhất quán khoảng cách theo hướng trái/phải. Dùng trực tiếp `nextUp` khi mục tiêu là tìm láng giềng phía trên.

**Nhầm 2 — `nextAfter(start, direction)` trả luôn `direction`.** Khi hai số khác nhau, nó chỉ tiến **một giá trị biểu diễn**; tham số `direction` quyết định hướng di chuyển.

**Nhầm 3 — `Math.nextAfter(1.0f, 2.0)` hoạt động theo bước của `double`.** Overload có `start` kiểu `float` trả về `float`, vì vậy kết quả sát `1.0f` theo bước `float`. Phải kiểm tra kiểu toán hạng đầu tiên và chữ `f` ở literal.

**Nhầm 4 — `Float.MIN_VALUE` là số âm nhỏ nhất.** Nó là số dương khác 0 nhỏ nhất; phía âm liền dưới 0 là `-Float.MIN_VALUE`. Số hữu hạn âm có độ lớn lớn nhất là `-Float.MAX_VALUE`.

**Nhầm 5 — Bỏ qua `+0.0` và `-0.0`.** Phép so sánh `==` coi chúng bằng nhau nhưng `nextAfter(+0.0, -0.0)` trả giá trị đích `-0.0`. Cần kiểm thử bằng raw bits nếu dấu 0 là điều kiện quan trọng.

**Nhầm 6 — Xem `ulp(x)` như ngưỡng chính xác cho mọi phép toán.** `ulp` là thuộc tính của miền số biểu diễn, không phải bảo đảm chất lượng của một thuật toán. Với so sánh gần đúng, cần quy tắc tolerance theo bài toán.

**Nhầm 7 — Tạo hướng bằng phép tính đã bị làm tròn về `start`.** Ví dụ biểu thức `1.0 + 1e-20` được tính bằng `double` thành `1.0`, nên `Math.nextAfter(1.0, 1.0 + 1e-20)` trả `1.0` thay vì bước lên. Nếu mục tiêu đơn giản là số biểu diễn liền trên `1.0`, gọi `Math.nextUp(1.0)`.

**Nhầm 8 — Dùng bước biểu diễn để thay thế làm tròn theo quy tắc tài chính.** `ulp` liên quan độ chính xác nhị phân, không phải số chữ số sau dấu thập phân. Khi cần quy tắc thập phân, cân nhắc `BigDecimal`/`RoundingMode` theo đặc tả nghiệp vụ.

## 9. Câu hỏi tự kiểm tra

Hãy tự đoán trước khi chạy trong JShell hoặc một lớp Java:

1. `Math.nextUp(-0.0)` là gì?
2. `Math.nextDown(Double.POSITIVE_INFINITY)` là gì?
3. `Math.nextAfter(1.0, 1.0)` có di chuyển không?
4. Tại sao `Math.nextUp(1.0) - 1.0` khác `1.0 - Math.nextDown(1.0)`?
5. Tại sao `Math.nextAfter(1.0f, 2.0)` có bước lớn hơn `Math.nextAfter(1.0, 2.0)`?
6. `Math.ulp(Double.NaN)` có phải một số thực hữu hạn dùng làm tolerance không?

**Đáp án:** (1) `Double.MIN_VALUE`; (2) `Double.MAX_VALUE`; (3) không, trả `1.0`; (4) `1.0` nằm đúng ranh giới nhị phân, khoảng cách hai bên là `2^-52` và `2^-53`; (5) `float` có 24 bit chính xác hữu hiệu, `double` có 53 bit; (6) không, kết quả là `NaN`.

## Ghi nhớ

- `nextUp`/`nextDown`: láng giềng theo hướng cố định trên trục số; `nextAfter`: láng giềng về phía mục tiêu.
- Lưới của **kiểu `float` hoặc `double`** quyết định bước, và overload `float` của `nextAfter` nhận hướng kiểu `double`.
- `ulp(x)` cho biết đơn vị bước tại độ lớn `x`; không tự đồng nhất với khoảng cách theo **mọi hướng**.
- Phải kiểm thử signed zero, subnormal, giá trị hữu hạn lớn nhất, vô cực và `NaN`.
- Để nhìn rõ từng giá trị, dùng `Double.toHexString(...)`, `Float.toHexString(...)` và các hàm raw-bit khi cần phân biệt dấu 0.