# `Math.floorDiv`, `Math.floorMod` và khác biệt với `/`, `%` trong Java

Với số nguyên dương, hai cách tính thương và phần dư thường cho cùng kết quả:

```java
System.out.println(7 / 3);                 // 2
System.out.println(7 % 3);                 // 1
System.out.println(Math.floorDiv(7, 3));   // 2
System.out.println(Math.floorMod(7, 3));   // 1
```

Nhưng khi có **số âm**, kết quả khác nhau. Java định nghĩa `/` trên số nguyên là phép **chia lấy thương làm tròn về 0** (*truncating division*), còn `Math.floorDiv` làm tròn thương **xuống âm vô cùng** (*floor division*). Tương ứng, `%` là phép **remainder** theo phép chia làm tròn về 0, còn `Math.floorMod` lấy phần dư theo phép chia floor.

Ví dụ quan trọng nhất:

```java
System.out.println(-7 / 3);                 // -2
System.out.println(-7 % 3);                 // -1
System.out.println(Math.floorDiv(-7, 3));   // -3
System.out.println(Math.floorMod(-7, 3));   // 2
```

Nếu bài toán xử lý chỉ số vòng, nhóm dữ liệu theo khoảng thời gian, tọa độ ô lưới hoặc số âm, chọn nhầm `%` và `floorMod` có thể gây sai logic dù chương trình biên dịch thành công.

## 1. Phân biệt “chia lấy thương” và “chia floor”

Cho hai số nguyên `x` và `y`, với `y != 0`:

- `x / y` lấy thương nguyên bằng cách **bỏ phần thập phân theo hướng về 0**.
- `Math.floorDiv(x, y)` lấy thương bằng cách **làm tròn xuống số nguyên nhỏ hơn hoặc bằng thương toán học**.

Ví dụ, thương toán học của `-7 / 3` là khoảng `-2.333…`. Làm tròn **về 0** được `-2`; làm tròn **xuống âm vô cùng** được `-3`.

| `x` | `y` | Thương toán học | `x / y` | `Math.floorDiv(x, y)` |
| ---: | ---: | ---: | ---: | ---: |
| 7 | 3 | 2,333… | 2 | 2 |
| −7 | 3 | −2,333… | −2 | −3 |
| 7 | −3 | −2,333… | −2 | −3 |
| −7 | −3 | 2,333… | 2 | 2 |
| −6 | 3 | −2 | −2 | −2 |
| −1 | 3 | −0,333… | 0 | −1 |

**Khi phép chia hết**, hai cách cho cùng thương. **Khi còn dư và hai toán hạng trái dấu**, `floorDiv` nhỏ hơn `/` đúng một đơn vị. Khi hai toán hạng cùng dấu, thương không âm nên làm tròn về 0 trùng với làm tròn xuống. Điều này áp dụng cho số nguyên trong miền biểu diễn thông thường, ngoại trừ trường hợp tràn `MIN_VALUE / -1` được nêu riêng ở phần 6.

Java thực hiện phép chia `int` và `long` hoàn toàn bằng số nguyên. Không cần, và thường không nên, chuyển sang `double` rồi gọi `Math.floor`: với `long` lớn hơn `2^53`, `double` có thể mất độ chính xác, khiến thương và ranh giới bucket sai.

## 2. Phân biệt `%` và `Math.floorMod`

Phần dư được xác định cùng với **cách làm tròn thương**.

Với phép chia thường của Java:

```text
q = x / y
r = x % y
x = q * y + r
```

Với phép chia floor:

```text
q = Math.floorDiv(x, y)
r = Math.floorMod(x, y)
x = q * y + r
```

Các đẳng thức trên mô tả quan hệ số học giữa thương và phần dư. Khi tự tính `q * y` bằng `int`/`long`, cần chú ý phép nhân có thể tràn trong trường hợp biên; đừng dùng phép tính lại này như một cách thay thế không kiểm tra cho `floorMod`. Trường hợp `MIN_VALUE / -1` còn có ngoại lệ tràn thương riêng.

### Bảng kết quả đầy đủ khi có dấu âm

| `x` | `y` | `x / y` | `x % y` | `floorDiv(x,y)` | `floorMod(x,y)` |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 7 | 3 | 2 | 1 | 2 | 1 |
| −7 | 3 | −2 | −1 | −3 | 2 |
| 7 | −3 | −2 | 1 | −3 | −2 |
| −7 | −3 | 2 | −1 | 2 | −1 |
| −6 | 3 | −2 | 0 | −2 | 0 |
| −1 | 3 | 0 | −1 | −1 | 2 |

Nhận xét hai quy tắc về dấu:

1. `x % y` có **cùng dấu với số bị chia `x`**, hoặc bằng 0. Vì thế `-7 % 3` bằng `-1`, không phải `2`.
2. `Math.floorMod(x, y)` có **cùng dấu với số chia `y`**, hoặc bằng 0. Vì thế `Math.floorMod(-7, 3)` bằng `2`, nhưng `Math.floorMod(7, -3)` bằng `-2`.

Đặc biệt, khi **`y > 0`**, giá trị `Math.floorMod(x, y)` luôn nằm trong khoảng **`0 <= r < y`**, ngay cả khi `x` âm. Đây là đặc tính thường cần cho index vòng hoặc phân nhóm theo modulo không âm.

Khi **`y < 0`**, giá trị `floorMod` thỏa **`y < r <= 0`**. Không nên gọi `floorMod` là “luôn không âm” nếu chưa bảo đảm **số chia dương**.

### Kiểm tra công thức với số âm

Với `x = -7`, `y = 3`:

- Phép chia thường: `q = -2` và `r = -1`, nên `-7 = (-2) * 3 + (-1)`.
- Phép chia floor: `q = -3` và `r = 2`, nên `-7 = (-3) * 3 + 2`.

Với `x = 7`, `y = -3`:

- Phép chia thường: `q = -2` và `r = 1`, nên `7 = (-2) * (-3) + 1`.
- Phép chia floor: `q = -3` và `r = -2`, nên `7 = (-3) * (-3) + (-2)`.

Cả hai mô hình nhất quán; điểm khác nhau là **quy tắc chọn thương** và do đó là **quy tắc chọn phần dư**.

## 3. Cơ chế tạo ra khác biệt

Với `x`, `y` là các số nguyên khác trường hợp chia cho 0:

- Nếu phép chia **hết**, cả hai mô hình có cùng thương, phần dư bằng 0.
- Nếu phép chia **còn dư và hai toán hạng cùng dấu**, thương toán học dương nên cắt về 0 cũng là làm tròn xuống; hai mô hình trùng nhau.
- Nếu phép chia **còn dư và hai toán hạng trái dấu**, thương toán học âm, có phần lẻ. `/` làm tròn lên về 0, còn `floorDiv` lấy giá trị nhỏ hơn một đơn vị; `floorMod` điều chỉnh phần dư tương ứng theo số chia.

Đặt `q0 = x / y` và `r0 = x % y`. Khi `r0 != 0` và `x`, `y` trái dấu, có thể mô tả về mặt toán học:

```text
qFloor = q0 - 1
rFloor = r0 + y
```

Nếu không thỏa điều kiện đó, `qFloor = q0` và `rFloor = r0`. Đây là lời giải thích cơ chế, không phải lời khuyên tự cài đặt phép chia floor trong mọi bối cảnh: Java có sẵn `Math.floorDiv`/`Math.floorMod`, rõ ràng hơn và xử lý những góc cạnh của số nguyên.

**Lưu ý về phép chia:** với số nguyên, `-1 / 3` là `0` chứ không phải số `-0.333…`. Java không giữ số lẻ trong kết quả `int`. Nếu viết `-1.0 / 3`, phép toán trở thành chấm động và có kết quả gần `-0.333…`; `Math.floorDiv` chỉ dành cho kiểu nguyên, không dùng với `double`.

## 4. API `Math.floorDiv` và `Math.floorMod`

Các overload thông dụng của `java.lang.Math` gồm:

```java
int q1 = Math.floorDiv(-7, 3);
long q2 = Math.floorDiv(-7L, 3L);
long q3 = Math.floorDiv(-7L, 3);

int r1 = Math.floorMod(-7, 3);
long r2 = Math.floorMod(-7L, 3L);
int r3 = Math.floorMod(-7L, 3);
```

Kết quả của `floorDiv(long, int)` là `long`, còn kết quả của `floorMod(long, int)` là `int` do độ lớn phần dư luôn nhỏ hơn độ lớn số chia. Các overload `int,int` cho `int` và `long,long` cho `long`.

**Không có overload tương đương cho `float` và `double`.** Nếu muốn làm việc với số thực, cần quy định bài toán làm tròn/phần dư chấm động riêng (ví dụ `Math.floor` hoặc `Math.IEEEremainder` có quy tắc khác). Không được áp dụng máy móc các luật số nguyên cho số thực có sai số biểu diễn.

Các phương thức `floorDiv` và `floorMod` có từ Java 8, nên dùng được trên Java 17+. Chúng không sửa biến đầu vào: trả về kết quả mới, giống các toán tử tính toán.

### Số chia bằng 0

Cả `/`, `%`, `Math.floorDiv` và `Math.floorMod` trên các kiểu nguyên đều ném `ArithmeticException` nếu **số chia bằng 0**:

```java
int size = 0;
// int invalid = 10 % size;            // Ném ArithmeticException khi chạy.
// int alsoInvalid = Math.floorMod(10, size); // Cũng ném ArithmeticException.
```

Không gọi modulo với kích thước collection rỗng hoặc số bucket bằng 0. Nếu giá trị `y` đến từ bên ngoài, kiểm tra `y != 0` trước, và với bài toán yêu cầu remainder không âm, kiểm tra mạnh hơn là `y > 0`.

## 5. Ứng dụng 1: chỉ số vòng và modulo không âm

Giả sử ta muốn đi lùi một bước trong vòng tròn 5 phần tử. Index hợp lệ là 0, 1, 2, 3, 4. Đi lùi từ vị trí 0 phải trở về 4.

```java
int capacity = 5;
int current = 0;

int wrong = (current - 1) % capacity;            // -1: không phải index hợp lệ.
int correct = Math.floorMod(current - 1, capacity); // 4.
```

Lý do: `%` giữ dấu của số bị chia `-1`. Còn `Math.floorMod(-1, 5)` chuẩn hóa về tập `[0, 4]`.

Với bộ đếm có thể âm hoặc vị trí logic cần quy về chỉ số vòng, điều kiện cần là **số chia dương**:

```java
static int wrapIndex(long logicalIndex, int capacity) {
    if (capacity <= 0) {
        throw new IllegalArgumentException("capacity must be positive");
    }
    return Math.floorMod(logicalIndex, capacity);
}
```

Đây là đoạn phương thức minh họa, không phải một chương trình độc lập. Overload `Math.floorMod(long, int)` trả `int`, nên hữu ích khi chỉ số logic dùng `long` nhưng mảng/buffer có `int capacity`.

Với `capacity = 5`, `wrapIndex(-1, 5)` trả 4; `wrapIndex(5, 5)` trả 0; `wrapIndex(-6, 5)` trả 4. Chỉ số vòng là một **ánh xạ theo modulo**. Nó không tự ngăn race condition hay kiểm soát chuyện ghi đè trong ring buffer đa luồng.

**Sai lầm khác:** dùng `Math.abs(index % capacity)` để tránh số âm. Với `index = -1`, `capacity = 5`, cách này cho 1, trong khi index vòng đúng là 4. Hơn nữa `Math.abs(Integer.MIN_VALUE)` vẫn âm do tràn. Hãy dùng `floorMod` khi cần dư không âm.

## 6. Ứng dụng 2: phân nhóm theo khoảng, bucket và thời gian âm

Giả sử một dòng thời gian được đo bằng số nguyên giây so với mốc 0. Mỗi bucket dài 60 giây và cần sắp xếp các thời điểm **trước** mốc 0.

Với thời điểm `t = -1`:

```java
long t = -1L;
long bucketWrong = t / 60;                  // 0: làm tròn về 0.
long bucketCorrect = Math.floorDiv(t, 60);  // -1: bucket [-60, -1].
int secondsIntoBucket = Math.floorMod(t, 60); // 59.
```

Theo mô hình bucket floor:

```text
t = bucketIndex * 60 + offset
-1 = (-1) * 60 + 59
```

Tức thời điểm −1 nằm trong bucket bắt đầu tại −60, offset 59 giây. Nếu dùng `t / 60`, thời điểm −1 bị xếp vào bucket 0, không đúng với các khoảng cố định dạng `[k*60, (k+1)*60)`.

Một số ví dụ với bucket dài 60:

| `t` (giây) | `t / 60` | `floorDiv(t,60)` | `t % 60` | `floorMod(t,60)` |
| ---: | ---: | ---: | ---: | ---: |
| 61 | 1 | 1 | 1 | 1 |
| 60 | 1 | 1 | 0 | 0 |
| 0 | 0 | 0 | 0 | 0 |
| −1 | 0 | −1 | −1 | 59 |
| −60 | −1 | −1 | 0 | 0 |
| −61 | −1 | −2 | −1 | 59 |

Quy tắc này phù hợp với việc chia tọa độ âm thành ô lưới, gom số nguyên vào dải độ rộng cố định, hay chia timestamp tương đối thành bucket (khi miền dữ liệu và hệ quy chiếu đã được xác định). Với dữ liệu thời gian thực, còn phải chú ý đơn vị milliseconds/nanoseconds, múi giờ, lịch và ranh giới thời gian; `floorDiv` chỉ giải quyết **phép chia số nguyên**, không giải quyết toàn bộ nghiệp vụ thời gian.

### Tọa độ ô lưới có thể âm

Giả sử chiều rộng mỗi ô là 10 đơn vị. Tọa độ `x = -1` phải nằm trong ô từ −10 đến −1:

```java
int cellWidth = 10;
int coordinate = -1;
int cellNumber = Math.floorDiv(coordinate, cellWidth); // -1
int offset = Math.floorMod(coordinate, cellWidth);     // 9
```

Nếu dùng `coordinate / cellWidth`, ô sẽ được xác định là 0, tạo sai lệch tại các tọa độ âm. Đây là một nguyên nhân phổ biến gây lỗi khi chia không gian có gốc tọa độ 0.

## 7. Góc cạnh quan trọng: tràn số nguyên nhỏ nhất chia cho −1

Java có một trường hợp đặc biệt: `Integer.MIN_VALUE` bằng `-2147483648`, trong khi số dương `2147483648` **không vừa kiểu `int`**. Vì vậy:

```java
int min = Integer.MIN_VALUE;
System.out.println(min / -1);                 // -2147483648
System.out.println(Math.floorDiv(min, -1));   // -2147483648
System.out.println(min % -1);                 // 0
System.out.println(Math.floorMod(min, -1));   // 0
```

Về toán học, thương đúng phải là `2147483648`. Java trả `Integer.MIN_VALUE` vì phép chia số nguyên xảy ra tình huống **overflow**; không ném ngoại lệ cho trường hợp này. `Math.floorDiv` cũng không tự phát hiện overflow đó. Tương tự, `Long.MIN_VALUE / -1L` và `Math.floorDiv(Long.MIN_VALUE, -1L)` trả `Long.MIN_VALUE`.

Điều này **không phủ nhận quy tắc floor** trong miền thông thường. Nó nhắc rằng ngay cả `floorDiv` vẫn trả một giá trị kiểu `int`/`long` hữu hạn, nên phép toán có thể mất kết quả toán học khi vượt miền biểu diễn.

Nếu nghiệp vụ phải tính thương chính xác trong trường hợp này, có thể mở rộng **trước phép chia**:

```java
long exactIntQuotient = (long) Integer.MIN_VALUE / -1;
// exactIntQuotient = 2147483648L.
```

Nếu toán hạng `long` có khả năng gặp `Long.MIN_VALUE / -1L` và cần kết quả nguyên chính xác lớn hơn `long`, cân nhắc `BigInteger` (với kiểm tra chia 0) hoặc kiểm tra riêng tình huống tràn.

Các cặp quan trọng khác cần nhớ:

- Với `x % y` và `floorMod(x, y)`, phép chia **hết** cho `y` luôn có dư 0 (khi `y != 0`).
- Với số chia dương, `floorMod(Integer.MIN_VALUE, 3)` vẫn là một giá trị trong `0..2`; không cần lấy trị tuyệt đối của số âm lớn.
- Nếu `y = Integer.MIN_VALUE`, số chia là âm; kết quả `floorMod` có thể âm. Đừng gọi `Math.abs(y)` để tự “biến thành modulus dương”, vì `Math.abs(Integer.MIN_VALUE)` bị tràn.

## 8. Tránh nhầm với “modulo” và phép toán của các API khác

Trong toán học, “modulo dương” thường được dùng để lấy đại diện của một lớp đồng dư trong khoảng `0..m-1` với `m > 0`. Trong Java, `%` là **remainder** theo phép chia cắt về 0; nó có thể âm. `Math.floorMod(x, m)` với `m > 0` phù hợp hơn với đại diện modulo không âm.

Một số tài liệu gọi `a % b` là “modulo” một cách thông tục. Khi đọc, hãy xem ví dụ với số âm và hợp đồng API trước khi suy ra phép toán nào được dùng.

### Liên hệ với `BigInteger`

`BigInteger.divide`/`remainder` áp dụng quy tắc lấy thương cắt về 0 và phần dư phù hợp. `BigInteger.mod(m)` trả kết quả không âm nhưng yêu cầu `m` **dương**; nếu modulus không dương, nó ném `ArithmeticException`. Nó không hoàn toàn thay thế `Math.floorMod` cho trường hợp số chia âm.

```java
// Đoạn minh họa trong nơi đã import java.math.BigInteger:
BigInteger x = BigInteger.valueOf(-7);
System.out.println(x.remainder(BigInteger.valueOf(3))); // -1
System.out.println(x.mod(BigInteger.valueOf(3)));       // 2
```

Nếu cần miền số nguyên lớn hơn `long`, chọn `BigInteger`; đừng chuyển một số `long` rất lớn qua `double` để thử làm tròn xuống.

## 9. Ví dụ Java 17+ chạy độc lập

Tạo tệp `FloorArithmeticDemo.java`:

```java
public class FloorArithmeticDemo {
    public static void main(String[] args) {
        int[][] pairs = {
                {7, 3}, {-7, 3}, {7, -3},
                {-7, -3}, {-6, 3}, {-1, 3}
        };

        for (int[] pair : pairs) {
            int x = pair[0];
            int y = pair[1];
            System.out.println(
                    "x=" + x + ", y=" + y
                            + " | /=" + (x / y)
                            + ", %=" + (x % y)
                            + ", floorDiv=" + Math.floorDiv(x, y)
                            + ", floorMod=" + Math.floorMod(x, y));
        }

        System.out.println("Circular index (-1, 5): " + Math.floorMod(-1, 5));
        System.out.println(
                "Bucket for -1 sec: q=" + Math.floorDiv(-1, 60)
                        + ", offset=" + Math.floorMod(-1, 60));

        int min = Integer.MIN_VALUE;
        System.out.println("MIN / -1: " + (min / -1));
        System.out.println("MIN floorDiv -1: " + Math.floorDiv(min, -1));
        System.out.println("MIN floorMod -1: " + Math.floorMod(min, -1));

        int modFromLong = Math.floorMod(-7L, 3);
        System.out.println("Long dividend, int divisor: " + modFromLong);

        try {
            Math.floorMod(10, 0);
        } catch (ArithmeticException ex) {
            System.out.println("Division by zero: ArithmeticException");
        }
    }
}
```

Biên dịch, chạy từ thư mục chứa tệp:

```bash
javac FloorArithmeticDemo.java
java FloorArithmeticDemo
```

Stdout:

```text
x=7, y=3 | /=2, %=1, floorDiv=2, floorMod=1
x=-7, y=3 | /=-2, %=-1, floorDiv=-3, floorMod=2
x=7, y=-3 | /=-2, %=1, floorDiv=-3, floorMod=-2
x=-7, y=-3 | /=2, %=-1, floorDiv=2, floorMod=-1
x=-6, y=3 | /=-2, %=0, floorDiv=-2, floorMod=0
x=-1, y=3 | /=0, %=-1, floorDiv=-1, floorMod=2
Circular index (-1, 5): 4
Bucket for -1 sec: q=-1, offset=59
MIN / -1: -2147483648
MIN floorDiv -1: -2147483648
MIN floorMod -1: 0
Long dividend, int divisor: 2
Division by zero: ArithmeticException
```

Chương trình thể hiện bốn kết hợp dấu của hai toán hạng, số chia hết, số bị chia gần 0, cách đưa chỉ số âm vào vòng và phân bucket âm. Nó cũng kiểm chứng overflow ở `Integer.MIN_VALUE / -1` và ngoại lệ khi số chia bằng 0.

## 10. Quy trình chọn toán tử cho bài toán thực tế

| Nhu cầu | Ưu tiên | Lý do |
| --- | --- | --- |
| Chia số nguyên và muốn thương **cắt về 0** | `/` | Đúng ngữ nghĩa phép chia nguyên mặc định Java |
| Phần dư theo phép chia cắt về 0; dấu theo số bị chia | `%` | Dùng khi hợp đồng yêu cầu remainder Java |
| Chia vào bucket/ô lưới số nguyên, có thể chứa giá trị âm | `Math.floorDiv` | Biên nhóm nhất quán với làm tròn xuống |
| Đưa index âm vào khoảng `0..size−1` với `size>0` | `Math.floorMod(index, size)` | Dư không âm khi modulus dương |
| Lấy offset không âm trong bucket độ rộng dương | `Math.floorMod(value, width)` | Offset thuộc `[0,width)` |
| Phép toán có thể vượt miền `int`/`long` | Kiểm tra miền, mở rộng kiểu trước, `BigInteger` nếu cần | `floorDiv` cũng chịu giới hạn miền kiểu trả về |
| Có số chia bằng 0 hoặc size không dương | Kiểm tra đầu vào và đưa ra lỗi rõ ràng | Tránh `ArithmeticException` bất ngờ và kết quả modulo không hợp đồng |

### Những lỗi thường gặp

1. **Tưởng `%` luôn cho số không âm.** `-7 % 3` là `-1`. Dùng `floorMod` với modulus dương khi cần `0..m-1`.
2. **Tưởng `floorMod` luôn không âm với mọi số chia.** `Math.floorMod(7, -3)` bằng `-2`. Kiểm tra `m > 0` nếu cần index.
3. **Tính `Math.abs(x % m)` để sửa chỉ số âm.** Giá trị thường sai hướng và `Math.abs(MIN_VALUE)` còn có thể tràn.
4. **Dùng `/` để phân bucket tọa độ/thời gian âm.** `-1 / 60` bằng 0, trong khi `floorDiv(-1,60)` bằng −1.
5. **Tự tính floor bằng `Math.floor((double)x / y)` cho mọi `long`.** Chuyển sang `double` có thể mất độ chính xác, đặc biệt với số rất lớn.
6. **Quên trường hợp `MIN_VALUE / -1`.** `floorDiv` không tự phát hiện tràn số nguyên này; nếu cần thương toán học chính xác, mở rộng kiểu hoặc dùng `BigInteger`.
7. **Dùng modulo với size bằng 0.** Cả `%` lẫn `floorMod` sẽ ném `ArithmeticException`. Đặt điều kiện size dương trước.

### Tự kiểm tra

1. Tính `-8 / 3`, `-8 % 3`, `Math.floorDiv(-8,3)` và `Math.floorMod(-8,3)`. Vì sao hai thương và hai phần dư khác nhau?
2. Với `Math.floorMod(8,-3)`, kết quả có không âm không? Đặc tính nào của số chia quyết định dấu phần dư?
3. Một ring buffer có 7 phần tử; vị trí logic là −2. `-2 % 7` và `Math.floorMod(-2,7)` khác nhau thế nào?
4. Timestamp có giá trị −61 giây, bucket width 60. Vì sao bucket phải là −2 với phương pháp floor?
5. `Math.floorDiv(Integer.MIN_VALUE,-1)` có trả thương toán học chính xác không? Làm sao xử lý khi bài toán cần kết quả 2147483648?
6. Hai toán tử `/`, `%` và hai phương thức floor có ném ngoại lệ chia cho 0 trên kiểu nguyên không?

**Ghi nhớ:** `/` và `%` là phép chia/phần dư số nguyên **làm tròn thương về 0**. `Math.floorDiv` và `Math.floorMod` dùng quy tắc **làm tròn thương xuống**. Với modulus dương, `floorMod` giúp đưa mọi số nguyên, kể cả số âm, vào khoảng phần dư không âm; với divisor âm, phần dư floor có thể âm. Chọn cách chia theo ngữ nghĩa bài toán và kiểm tra chia 0, miền kiểu số nguyên, cùng những trường hợp tràn.