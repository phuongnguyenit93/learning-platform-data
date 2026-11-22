# CEILING và FLOOR: làm tròn về dương vô cực và âm vô cực trong Java

## 1. Mục tiêu và bối cảnh

Khi làm việc với số thực hoặc số thập phân, “làm tròn” không phải lúc nào cũng có nghĩa là tìm số nguyên gần nhất. Đôi khi yêu cầu nghiệp vụ là **chọn giá trị nhỏ nhất không thấp hơn số gốc** hoặc **chọn giá trị lớn nhất không vượt quá số gốc**. Đây chính là hai hướng làm tròn **CEILING** (về dương vô cực) và **FLOOR** (về âm vô cực).

Sau bài này, bạn có thể:

- Giải thích chính xác hai hướng làm tròn trên trục số, kể cả với số âm.
- Dùng `Math.ceil(double)` và `Math.floor(double)` để làm tròn đến giá trị nguyên dưới dạng `double`.
- Dùng `BigDecimal.setScale(..., RoundingMode.CEILING/FLOOR)` để giữ số chữ số thập phân mong muốn.
- Phân biệt `Math.ceilDiv` và `Math.floorDiv` với phép chia số nguyên `/`; chọn đúng API trong bài toán đếm trang, nhóm chỉ số.
- Nhận diện sai lầm về dấu âm, số thực nhị phân, kiểu trả về và trường hợp biên.

## 2. Định nghĩa chính xác

Với số thực hữu hạn `x`:

- **Ceiling**: `ceil(x)` là **số nguyên nhỏ nhất lớn hơn hoặc bằng `x`**. Trên trục số, kết quả hướng về **+∞**.
- **Floor**: `floor(x)` là **số nguyên lớn nhất nhỏ hơn hoặc bằng `x`**. Trên trục số, kết quả hướng về **−∞**.

Về mặt toán học, chúng thỏa:

```text
floor(x) <= x <= ceil(x)

Ví dụ trên trục số:
...  -4     -3     -2     -1      0      1      2      3 ...
         ^ -2.7 nằm giữa -3 và -2
           floor(-2.7) = -3      ceil(-2.7) = -2
```

Kết quả với các ví dụ tiêu biểu:

| x | CEILING | FLOOR | Giải thích |
|---:|---:|---:|---|
| `2.7` | `3` | `2` | `3` ở phía +∞, `2` ở phía −∞ |
| `2.0` | `2` | `2` | Đã nguyên nên giữ nguyên |
| `-2.7` | `-2` | `-3` | `-2` lớn hơn `-2.7`; `-3` nhỏ hơn |
| `-2.0` | `-2` | `-2` | Đã nguyên nên giữ nguyên |
| `0.2` | `1` | `0` | Hai hướng khác nhau |
| `-0.2` | `0`* | `-1` | *Với `double`, `Math.ceil(-0.2)` tạo `-0.0` |

**Điểm dễ nhầm nhất:** “CEILING luôn tăng phần trị tuyệt đối” là sai. Với `-2.7`, đi về +∞ là đi **sang phải** tới `-2`, tức trị tuyệt đối giảm. “FLOOR là bỏ phần thập phân” cũng sai với số âm: bỏ phần thập phân của `-2.7` cho `-2`, trong khi `floor(-2.7) = -3`.

## 3. Làm tròn đến số nguyên bằng `Math.ceil` và `Math.floor`

Java cung cấp hai hàm tĩnh:

```java
public static double Math.ceil(double a);
public static double Math.floor(double a);
```

Cả hai nhận `double` và **trả về `double`**, dù với đầu vào hữu hạn thông thường giá trị kết quả bằng một số nguyên toán học. Điều này **không đồng nghĩa** kết quả tự động trở thành kiểu `int` hoặc `long`.

Chương trình độc lập sau chạy được với Java 17+:

**Tệp `CeilingFloorDemo.java`**

```java
import java.util.Locale;

public class CeilingFloorDemo {
    public static void main(String[] args) {
        double[] values = {2.7, 2.0, -2.7, -2.0, -0.25, 0.0, -0.0};

        for (double x : values) {
            System.out.printf(
                    Locale.ROOT,
                    "x=%s | ceil=%s | floor=%s%n",
                    x, Math.ceil(x), Math.floor(x));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac CeilingFloorDemo.java
java CeilingFloorDemo
```

Kết quả:

```text
x=2.7 | ceil=3.0 | floor=2.0
x=2.0 | ceil=2.0 | floor=2.0
x=-2.7 | ceil=-2.0 | floor=-3.0
x=-2.0 | ceil=-2.0 | floor=-2.0
x=-0.25 | ceil=-0.0 | floor=-1.0
x=0.0 | ceil=0.0 | floor=0.0
x=-0.0 | ceil=-0.0 | floor=-0.0
```

Hai đặc điểm đáng chú ý:

1. `Math.ceil` không phải “luôn cộng một”: nếu `x` đã là số nguyên thì giữ nguyên.
2. IEEE 754 có hai biểu diễn zero: `+0.0` và `-0.0`. Chúng so sánh bằng nhau với `==`, nhưng có bit dấu khác nhau; `Math.ceil(-0.25)` cho `-0.0`, không phải `+0.0`.

### Các trường hợp biên của số thực

Theo hợp đồng API:

- Với `Double.NaN`, hai hàm đều trả `NaN`.
- Với `Double.POSITIVE_INFINITY` hoặc `Double.NEGATIVE_INFINITY`, trả chính giá trị vô cực đó.
- Với `+0.0` hoặc `-0.0`, giữ nguyên dấu zero.
- Nếu đầu vào đã là giá trị `double` nguyên về mặt toán học, trả lại chính nó.
- Nhiều số `double` rất lớn không còn biểu diễn được phần lẻ; làm tròn không khôi phục được những chữ số đã mất trước đó.

Một phép kiểm tra riêng:

```java
public class SpecialValues {
    public static void main(String[] args) {
        System.out.println(Math.ceil(Double.NaN));
        System.out.println(Math.floor(Double.POSITIVE_INFINITY));
        System.out.println(Math.ceil(Double.NEGATIVE_INFINITY));
        System.out.println(Double.doubleToRawLongBits(Math.ceil(-0.25))
                == Double.doubleToRawLongBits(-0.0));
    }
}
```

```bash
javac SpecialValues.java
java SpecialValues
```

```text
NaN
Infinity
-Infinity
true
```

## 4. Phân biệt với `Math.round`, ép kiểu và làm tròn theo trị tuyệt đối

Bốn phép xử lý này trả lời những câu hỏi khác nhau:

| Cách xử lý | `2.7` | `-2.7` | Ý nghĩa |
|---|---:|---:|---|
| `Math.ceil(x)` | `3.0` | `-2.0` | Số nguyên nhỏ nhất ≥ x |
| `Math.floor(x)` | `2.0` | `-3.0` | Số nguyên lớn nhất ≤ x |
| `Math.round(x)` | `3` | `-3` | Số nguyên gần nhất; trường hợp cách đều chọn hướng +∞ |
| `(int) x` | `2` | `-2` | Cắt phần thập phân, hướng về 0, kèm quy tắc chuyển kiểu |

Ví dụ nhấn mạnh sự khác biệt ở số âm:

```java
public class RoundingComparison {
    public static void main(String[] args) {
        double x = -2.3;
        System.out.println(Math.ceil(x));
        System.out.println(Math.floor(x));
        System.out.println(Math.round(x));
        System.out.println((int) x);
    }
}
```

```bash
javac RoundingComparison.java
java RoundingComparison
```

```text
-2.0
-3.0
-2
-2
```

Với số `-2.3`, CEILING là `-2.0`, FLOOR là `-3.0`; `Math.round` chọn số gần nhất `-2`; ép kiểu cắt phần lẻ ra `-2`. Sự trùng kết quả ở ví dụ này không có nghĩa các phép toán tương đương.

**Lưu ý khi ép kết quả về kiểu nguyên:** Chuyển `double` sang `int` hoặc `long` có thể làm mất phạm vi và thông tin đặc biệt. Java chuyển `NaN` thành `0`, và giá trị ngoài miền số nguyên được bão hòa đến biên kiểu đích. Vì vậy, nếu cần số nguyên lưu trữ, hãy kiểm tra `Double.isFinite(x)`, miền giá trị và quy tắc yêu cầu trước khi ép kiểu. Không dùng phép ép kiểu như một cách kiểm tra dữ liệu đầu vào.

## 5. Làm tròn ở chữ số thập phân: `BigDecimal` và `RoundingMode`

`Math.ceil`/`Math.floor` làm tròn đến giá trị nguyên. Nếu phải làm tròn tới **2 chữ số sau dấu thập phân**, **hàng chục**, hoặc một mức `scale` bất kỳ, dùng `BigDecimal.setScale(int, RoundingMode)`:

- `RoundingMode.CEILING`: chọn giá trị biểu diễn được gần nhất theo hướng **+∞** khi bỏ chữ số.
- `RoundingMode.FLOOR`: chọn giá trị biểu diễn được gần nhất theo hướng **−∞** khi bỏ chữ số.

Ở `scale = 2`, các điểm hợp lệ cách nhau `0.01`; ở `scale = 0`, các điểm hợp lệ là số nguyên; ở `scale = -1`, các điểm hợp lệ là bội số của 10. Hai mode áp dụng nhất quán bất kể số dương hay số âm.

| Giá trị gốc | Scale | CEILING | FLOOR |
|---:|---:|---:|---:|
| `12.341` | 2 | `12.35` | `12.34` |
| `-12.341` | 2 | `-12.34` | `-12.35` |
| `12.300` | 2 | `12.30` | `12.30` |
| `121` | −1 | `130` | `120` |
| `-121` | −1 | `-120` | `-130` |

Chương trình độc lập:

**Tệp `DecimalCeilingFloor.java`**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalCeilingFloor {
    public static void main(String[] args) {
        for (String input : new String[]{"12.341", "-12.341"}) {
            BigDecimal value = new BigDecimal(input);
            BigDecimal ceiling = value.setScale(2, RoundingMode.CEILING);
            BigDecimal floor = value.setScale(2, RoundingMode.FLOOR);

            System.out.println(input + " -> CEILING=" + ceiling
                    + ", FLOOR=" + floor);
        }

        BigDecimal value = new BigDecimal("-121");
        System.out.println("To tens: CEILING="
                + value.setScale(-1, RoundingMode.CEILING).toPlainString()
                + ", FLOOR="
                + value.setScale(-1, RoundingMode.FLOOR).toPlainString());
    }
}
```

```bash
javac DecimalCeilingFloor.java
java DecimalCeilingFloor
```

```text
12.341 -> CEILING=12.35, FLOOR=12.34
-12.341 -> CEILING=-12.34, FLOOR=-12.35
To tens: CEILING=-120, FLOOR=-130
```

### Những điều cần nhớ với `BigDecimal`

1. **Tạo từ chuỗi thập phân:** ưu tiên `new BigDecimal("12.341")` hoặc chuỗi đầu vào đã kiểm tra. `new BigDecimal(0.1)` đưa vào biểu diễn nhị phân không chính xác của `double`, nên có thể làm đổi kết quả ở ngưỡng làm tròn. Nếu bắt đầu từ `double` và chấp nhận cách biểu diễn decimal theo `Double.toString`, `BigDecimal.valueOf(double)` thường phù hợp hơn constructor nhận `double`.
2. **`BigDecimal` là bất biến:** `setScale` trả về một giá trị mới; hãy gán kết quả. Bản gốc không tự thay đổi.
3. **`scale` khác `precision`:** `setScale(2, ...)` giữ 2 chữ số *sau dấu thập phân*, không phải 2 chữ số có nghĩa. `MathContext` quản lý precision (số chữ số có nghĩa), có thể chọn cùng rounding mode nhưng khác bài toán.
4. **`CEILING` khác `UP` và `FLOOR` khác `DOWN`:** `UP` hướng **ra xa 0**; `DOWN` hướng **về 0**. Chẳng hạn với `-1.231` làm tròn scale 2: CEILING = `-1.23`, FLOOR = `-1.24`, UP = `-1.24`, DOWN = `-1.23`.
5. **Số có giá trị 0:** `BigDecimal` không có cách lưu dấu `-0.0` như IEEE 754. `new BigDecimal("-0.001").setScale(2, RoundingMode.CEILING)` cho `0.00`.

## 6. Chia số nguyên theo hướng: `Math.ceilDiv` và `Math.floorDiv`

Nếu bài toán bắt đầu bằng **hai số nguyên**, không cần chuyển sang `double` để chia rồi gọi `Math.ceil`/`Math.floor`. Java có:

- `Math.floorDiv(a, b)`: thương nguyên làm tròn về −∞ (có từ Java 8 cho `int`/`int`).
- `Math.ceilDiv(a, b)`: thương nguyên làm tròn về +∞ (có từ Java 18).
- Phép chia nguyên `a / b`: bỏ phần lẻ của thương, hướng về 0.

So sánh các dấu:

| a | b | `a / b` | `Math.ceilDiv(a,b)` | `Math.floorDiv(a,b)` |
|---:|---:|---:|---:|---:|
| 8 | 3 | 2 | 3 | 2 |
| −8 | 3 | −2 | −2 | −3 |
| 8 | −3 | −2 | −2 | −3 |
| −8 | −3 | 2 | 3 | 2 |
| 9 | 3 | 3 | 3 | 3 |

Chương trình sau yêu cầu **Java 18+** (khuyến nghị Java 21):

**Tệp `IntegerCeilingFloor.java`**

```java
public class IntegerCeilingFloor {
    public static void main(String[] args) {
        int[][] samples = {{8, 3}, {-8, 3}, {8, -3}, {-8, -3}};

        for (int[] sample : samples) {
            int a = sample[0];
            int b = sample[1];
            System.out.println(a + "/" + b + ": trunc=" + (a / b)
                    + ", ceil=" + Math.ceilDiv(a, b)
                    + ", floor=" + Math.floorDiv(a, b));
        }
    }
}
```

```bash
javac IntegerCeilingFloor.java
java IntegerCeilingFloor
```

```text
8/3: trunc=2, ceil=3, floor=2
-8/3: trunc=-2, ceil=-2, floor=-3
8/-3: trunc=-2, ceil=-2, floor=-3
-8/-3: trunc=2, ceil=3, floor=2
```

**Các giới hạn cần kiểm tra:** chia cho `0` gây `ArithmeticException`. Với `Integer.MIN_VALUE / -1` (hoặc `Long.MIN_VALUE / -1`), thương toán học vượt miền kiểu nguyên: các phiên bản `ceilDiv`/`floorDiv` thông thường có quy tắc tràn số đặc biệt. Nếu yêu cầu phát hiện tràn số, dùng `Math.ceilDivExact`/`Math.floorDivExact` (Java 18+) hoặc chọn kiểu/thuật toán an toàn hơn. Đừng thực hiện `Math.ceil((double) a / b)` rồi ép nguyên một cách máy móc: chuyển sang `double` có thể mất độ chính xác ở số nguyên lớn.

### Khi nào dùng `ceilMod` và `floorMod`?

Từ Java 18, `Math.ceilMod(a,b)` đi cặp với `ceilDiv(a,b)`; `Math.floorMod(a,b)` đi cặp với `floorDiv(a,b)`. Chúng thỏa đồng nhất thức số học theo miền `int`/`long` tương ứng (xét quy tắc số nguyên Java):

```text
a = ceilDiv(a,b) * b + ceilMod(a,b)
a = floorDiv(a,b) * b + floorMod(a,b)
```

Với `a = -8`, `b = 3`: `floorDiv = -3`, `floorMod = 1`; `ceilDiv = -2`, `ceilMod = -2`. Phép dư `%` theo chia cắt về 0 cho `-8 % 3 = -2` và không thay thế `floorMod` được trong những bài toán cần chỉ số modulo không âm khi `b > 0`.

## 7. Ứng dụng thực tế

### 7.1. Số trang tối thiểu để chứa toàn bộ bản ghi

Có `totalItems >= 0` bản ghi, mỗi trang tối đa `pageSize > 0`. Số trang cần thiết là ceiling của thương. Với Java 18+:

```java
public class PaginationExample {
    public static int pageCount(int totalItems, int pageSize) {
        if (totalItems < 0 || pageSize <= 0) {
            throw new IllegalArgumentException("Invalid pagination arguments");
        }
        return Math.ceilDiv(totalItems, pageSize);
    }

    public static void main(String[] args) {
        System.out.println(pageCount(21, 10));
        System.out.println(pageCount(20, 10));
        System.out.println(pageCount(0, 10));
    }
}
```

```bash
javac PaginationExample.java
java PaginationExample
```

```text
3
2
0
```

Lý do: 21 phần tử chiếm 2 trang đầy và 1 trang lẻ; làm tròn lên để không bỏ sót phần tử. Với dữ liệu lớn vượt `int`, cân nhắc overload `long`.

### 7.2. Chia nhóm khi chỉ số có thể âm

Giả sử chia trục thời gian thành các ô rộng 60 đơn vị, với gốc là 0. Chỉ số `-1` thuộc ô `[-60, 0)`, nên mã ô phải là `-1`, không phải `0`:

```java
System.out.println(-1 / 60);                 // 0: cắt về 0
System.out.println(Math.floorDiv(-1, 60));   // -1: đúng ô [-60, 0)
System.out.println(Math.floorDiv(61, 60));   // 1: đúng ô [60, 120)
```

Đây là ví dụ **minh họa đoạn mã**; đặt trong phương thức (ví dụ `main`) để chạy. `Math.floorDiv` hữu ích khi nhóm số nguyên cả phía trước và phía sau mốc 0.

### 7.3. Quy tắc làm tròn đơn vị tiền hoặc khối lượng

Nếu chính sách yêu cầu chọn **mức thanh toán không thấp hơn số tiền tính toán**, có thể dùng `RoundingMode.CEILING` tại `scale` được quy định. Nếu yêu cầu chọn **mức không vượt quá giá trị**, dùng `RoundingMode.FLOOR`. Với giá trị âm, kết quả vẫn luôn theo đúng hướng trên trục số. Trước khi áp dụng vào hệ thống thật, phải xác định rõ quy tắc cho hoàn tiền, tiền âm, đơn vị tiền và quy định nghiệp vụ; không suy ra “luôn làm tròn lên tiền” một cách chung chung.

## 8. Các lỗi phổ biến và cách tránh

| Sai lầm | Vì sao sai | Cách đúng |
|---|---|---|
| Cho rằng `ceil(-2.7) == -3` | Nhầm hướng +∞ với xa 0 | `Math.ceil(-2.7) == -2.0` |
| Cho rằng `floor(-2.7) == -2` | Nhầm với phép cắt phần lẻ | `Math.floor(-2.7) == -3.0` |
| Dùng `(int) (a / b)` để tính số trang | Phép chia nguyên đã loại phần dư | `Math.ceilDiv(a,b)` với `a >= 0, b > 0` |
| Dùng `Math.ceil(x * 100) / 100` cho mọi khoản tiền | Phép nhân/chia `double` có sai số nhị phân | Dùng `BigDecimal` từ nguồn thập phân chính xác và `setScale(2, mode)` |
| Nhầm `CEILING` với `UP` | Với số âm, hướng về +∞ lại gần 0 | Chọn theo yêu cầu “về +∞” hay “ra xa 0” |
| Quên kiểu trả về của `Math.ceil` | Kết quả là `double`, có NaN/vô cực/−0.0 | Giữ `double` hoặc kiểm tra trước khi đổi kiểu |
| Quên kiểm tra `pageSize > 0` | Chia nguyên cho zero gây lỗi | Validate đầu vào trước `ceilDiv` |
| Tin rằng `Math.ceil` sửa được sai số đã tồn tại | Thông tin có thể đã mất khi tạo `double` | Dùng `BigDecimal`/kiểu dữ liệu đúng từ nguồn |

**Mẹo tự kiểm:** Với giá trị hữu hạn và kết quả có nghĩa, CEILING không được nhỏ hơn đầu vào; FLOOR không được lớn hơn đầu vào. Riêng cách so sánh số thực NaN cần được xử lý riêng vì mọi phép so sánh thứ tự với `NaN` đều cho `false`.

## 9. Bài tập tự kiểm tra có lời giải

1. `Math.ceil(-4.01)` và `Math.floor(-4.01)` là bao nhiêu?  
   **Đáp án:** `-4.0` và `-5.0`. CEILING đi về +∞, FLOOR đi về −∞.
2. `new BigDecimal("-5.301").setScale(2, RoundingMode.CEILING)` và `FLOOR` trả gì?  
   **Đáp án:** `-5.30` và `-5.31`. Khoảng cách giá trị ở scale 2 là 0.01.
3. Có 31 bản ghi, mỗi trang tối đa 10. Cần bao nhiêu trang?  
   **Đáp án:** `Math.ceilDiv(31, 10) == 4` (Java 18+).
4. Tại sao `Math.floorDiv(-1, 10) == -1` nhưng `-1 / 10 == 0`?  
   **Đáp án:** Phép thứ nhất lấy floor của thương `-0.1`, phép thứ hai cắt thương về 0.
5. `Math.ceil(-0.25) == 0.0` có đúng không?  
   **Đáp án:** Đúng khi so sánh bằng `==`, nhưng kết quả có biểu diễn `-0.0`, khác bit dấu so với `+0.0`.

## 10. Ghi nhớ và tham khảo

Hãy bắt đầu từ **hướng của kết quả trên trục số**, sau đó chọn API theo loại dữ liệu:

- Số thực cần làm tròn tới giá trị nguyên dưới dạng `double`: `Math.ceil` hoặc `Math.floor`.
- Số thập phân cần kiểm soát chữ số sau dấu phẩy, đặc biệt các giá trị chính xác theo hệ thập phân: `BigDecimal.setScale(scale, RoundingMode.CEILING/FLOOR)`.
- Thương của hai số nguyên: `Math.ceilDiv` hoặc `Math.floorDiv` (kiểm tra phiên bản Java, trường hợp 0 và tràn số).

Tài liệu API chính thức:

- [Java 21 — `java.lang.Math`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
- [Java 21 — `java.math.RoundingMode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html)
- [Java 21 — `java.math.BigDecimal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
