# floorDiv, floorMod và cách xử lý số âm trong Java

**Chủ đề:** Java 8 → Số học → floorDiv, floorMod và cách xử lý số âm.

Khi lập trình Java với **số nguyên âm**, kết quả của phép chia `/` và phép lấy dư `%` thường khác với cách phân chia theo **floor** trong toán học. Hai phương thức **`Math.floorDiv(x, y)`** và **`Math.floorMod(x, y)`** được đưa vào Java từ phiên bản **8** nhằm giải quyết nhu cầu chia thành các khoảng, gán chỉ số vòng tròn, phân nhóm giá trị âm, xử lý thời gian trước mốc 1970 và các thuật toán cần số dư mang dấu của **số chia**.

Điểm cần ghi nhớ ngay:

~~~java
System.out.println(-7 / 3);               // -2
System.out.println(-7 % 3);               // -1

System.out.println(Math.floorDiv(-7, 3)); // -3
System.out.println(Math.floorMod(-7, 3)); //  2
~~~

Các kết quả ở trên **đều đúng**, nhưng dựa trên **hai quy tắc chia khác nhau**:

- Toán tử **`/`** của Java với `int` và `long` lấy phần nguyên bằng cách **cắt về 0** (truncation toward zero).
- Toán tử **`%`** là phần dư đi kèm với phép chia đó; phần dư khác 0 có **cùng dấu với số bị chia** (`x`).
- **`Math.floorDiv(x, y)`** chọn thương nguyên bằng cách **làm tròn xuống âm vô cực**.
- **`Math.floorMod(x, y)`** lấy phần dư theo thương floor; phần dư khác 0 có **cùng dấu với số chia** (`y`).

**Đây là kiến thức hiện hành**: `Math.floorDiv` và `Math.floorMod` vẫn là API chính thức trong Java SE 26, không phải API đã bị bỏ hay lỗi thời. Bài sử dụng **Java 17+** cho các chương trình ví dụ độc lập, đồng thời chỉ rõ những overload/phương thức bổ sung sau Java 8 để tránh hướng dẫn sai phiên bản.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt chính xác `/`, `%`, `Math.floorDiv` và `Math.floorMod`.
2. Giải thích **truncation toward zero** và **rounding toward negative infinity** bằng trục số.
3. Tính đúng thương và dư trong **bốn trường hợp dấu**: `(+,+)`, `(-,+)`, `(+,-)`, `(-,-)`.
4. Dùng đẳng thức `x = floorDiv(x,y) * y + floorMod(x,y)` đúng với quy tắc số học Java.
5. Chứng minh với **`y > 0`** thì `floorMod(x, y)` nằm trong **`0` đến `y-1`**.
6. Giải thích với **`y < 0`**, `floorMod` có thể âm và **không** phải chỉ số mảng hợp lệ.
7. Chọn đúng overload `int/int`, `long/long`, `long/int`, biết khác biệt theo phiên bản.
8. Xử lý **chia cho 0** và trường hợp **`MIN_VALUE / -1`** bị tràn số nguyên.
9. Hiểu khi nào sử dụng `Math.floorDivExact` (Java 18+).
10. Áp dụng `floorMod` trong **circular index**, sharding, bucket và lịch chạy chu kỳ.
11. Áp dụng `floorDiv`/`floorMod` vào **milliseconds trước Unix epoch** mà không lệch bucket.
12. Tránh chuyển sang `double` rồi `Math.floor` khi cần thương nguyên chính xác cho `long`.
13. So sánh với `BigInteger.remainder` và `BigInteger.mod`.
14. Viết unit test theo các tính chất số học, không chỉ kiểm tra số dương.

## 2. Các khái niệm: số bị chia, số chia, thương và dư

Giả sử có hai số nguyên:

~~~text
x = -7       (dividend: số bị chia)
y =  3       (divisor: số chia; phải khác 0)

q = thương nguyên
r = phần dư
~~~

Ta muốn biểu diễn:

~~~text
x = q × y + r
~~~

Với **phép chia hướng về 0** của Java:

~~~text
-7 / 3 = -2
-7 % 3 = -1

-7 = (-2) × 3 + (-1)
~~~

Với **phép chia floor**:

~~~text
Math.floorDiv(-7, 3) = -3
Math.floorMod(-7, 3) =  2

-7 = (-3) × 3 + 2
~~~

Cả hai cách đều tái tạo được số bị chia. Sự khác biệt là **quy định chọn thương**; khi đổi thương, phần dư tương ứng cũng phải đổi.

### 2.1. Không nhầm phép chia nguyên với chia số thực

~~~java
int a = -7;
int b = 3;

System.out.println(a / b);           // -2
System.out.println((double) a / b);  // -2.3333333333333335
~~~

Phép chia hai `int` trả `int`; muốn số thực phải có toán hạng `double`. Nhưng **`Math.floorDiv` không phải phép chia double**. Nó nhận số nguyên, trả số nguyên, và xử lý chính xác quy tắc làm tròn floor trong miền giá trị theo hợp đồng API.

### 2.2. Floor nghĩa là gì?

Hàm toán học **floor(z)** trả số nguyên lớn nhất **không lớn hơn z**.

~~~text
floor( 2.7) =  2
floor( 2.0) =  2
floor(-2.0) = -2
floor(-2.3) = -3
floor(-2.7) = -3
~~~

Vì vậy:

~~~text
-7 / 3 theo số thực = -2.3333...
floor(-7 / 3)      = -3

7 / (-3) theo số thực = -2.3333...
floor(7 / -3)         = -3
~~~

**Làm tròn xuống** không đồng nghĩa với **bỏ phần thập phân**. Với số âm không nguyên, làm tròn xuống đi về **âm vô cực**, khác với cắt về 0.

## 3. Bảng kết quả đầy đủ cho bốn tổ hợp dấu

Đây là bảng quan trọng nhất của bài:

| `x` | `y` | `x / y` | `x % y` | `Math.floorDiv(x,y)` | `Math.floorMod(x,y)` |
|---:|---:|---:|---:|---:|---:|
| `7` | `3` | `2` | `1` | `2` | `1` |
| `-7` | `3` | `-2` | `-1` | `-3` | `2` |
| `7` | `-3` | `-2` | `1` | `-3` | `-2` |
| `-7` | `-3` | `2` | `-1` | `2` | `-1` |
| `-6` | `3` | `-2` | `0` | `-2` | `0` |
| `0` | `-3` | `0` | `0` | `0` | `0` |
| `1` | `-3` | `0` | `1` | `-1` | `-2` |
| `-1` | `3` | `0` | `-1` | `-1` | `2` |
| `-1` | `-3` | `0` | `-1` | `0` | `-1` |

### 3.1. Cùng dấu thì floorDiv và / thường giống nhau

Khi `x` và `y` cùng dấu và `y != 0`, thương thực không âm, nên cắt về 0 và floor cho cùng kết quả.

~~~text
7 / 3           = 2
floorDiv(7, 3)  = 2

-7 / -3         = 2
floorDiv(-7,-3) = 2
~~~

**Ngoại lệ số học biên cần tách riêng:** `Integer.MIN_VALUE / -1` và `Long.MIN_VALUE / -1` tạo thương toán học không biểu diễn được trong kiểu, dù đây là trường hợp hai toán hạng trái dấu. Mục overflow sẽ giải thích.

### 3.2. Khác dấu và thương không nguyên thì khác nhau

~~~text
-7 / 3             = -2
floorDiv(-7, 3)    = -3

7 / -3             = -2
floorDiv(7, -3)    = -3
~~~

Vì kết quả thực là một số âm không nguyên, làm tròn xuống trả số nhỏ hơn một đơn vị so với chia cắt về 0.

### 3.3. Nếu chia hết thì floorDiv và / trùng nhau

~~~text
-6 / 3             = -2
floorDiv(-6, 3)    = -2

6 / -3             = -2
floorDiv(6, -3)    = -2
~~~

Khi dư bằng 0, thương đã là số nguyên, nên hai cách làm tròn không tạo khác biệt.

### 3.4. Nếu cả hai âm thì phần dư âm

~~~text
Math.floorDiv(-7, -3) =  2
Math.floorMod(-7, -3) = -1

-7 = 2 × (-3) + (-1)
~~~

Điều này cho thấy **`floorMod` không luôn không âm**. Nó chỉ không âm khi **số chia dương**.

## 4. Ví dụ runnable: đối chiếu cả bốn phép toán

Lưu thành **`FloorDivisionBasicsDemo.java`**:

~~~java
public class FloorDivisionBasicsDemo {
    public static void main(String[] args) {
        int[][] pairs = {
                {7, 3},
                {-7, 3},
                {7, -3},
                {-7, -3},
                {-6, 3},
                {0, -3},
                {1, -3},
                {-1, 3},
                {-1, -3}
        };

        for (int[] pair : pairs) {
            int x = pair[0];
            int y = pair[1];

            System.out.println(
                    x + "," + y
                    + " -> /=" + (x / y)
                    + " %=" + (x % y)
                    + " floorDiv=" + Math.floorDiv(x, y)
                    + " floorMod=" + Math.floorMod(x, y));
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 FloorDivisionBasicsDemo.java
java FloorDivisionBasicsDemo
~~~

**Stdout đã kiểm tra với JDK:**

~~~text
7,3 -> /=2 %=1 floorDiv=2 floorMod=1
-7,3 -> /=-2 %=-1 floorDiv=-3 floorMod=2
7,-3 -> /=-2 %=1 floorDiv=-3 floorMod=-2
-7,-3 -> /=2 %=-1 floorDiv=2 floorMod=-1
-6,3 -> /=-2 %=0 floorDiv=-2 floorMod=0
0,-3 -> /=0 %=0 floorDiv=0 floorMod=0
1,-3 -> /=0 %=1 floorDiv=-1 floorMod=-2
-1,3 -> /=0 %=-1 floorDiv=-1 floorMod=2
-1,-3 -> /=0 %=-1 floorDiv=0 floorMod=-1
~~~

**Ý nghĩa từng nhóm:**

1. `7,3`: số dương thông thường, hai cách trùng.
2. `-7,3`: `/` cắt về 0 nên -2; floorDiv xuống -3, floorMod thành 2.
3. `7,-3`: phần dư của `%` là dương 1 theo số bị chia; floorMod là âm -2 theo số chia.
4. `-7,-3`: thương dương 2, phần dư âm -1.
5. `-6,3`: chia hết, cả hai số dư đều 0.
6. `0,-3`: 0 chia số khác 0 cho thương và dư 0.
7. `1,-3`: thương cắt về 0 là 0, floorDiv là -1.
8. `-1,3`: rất hữu ích để thử trước mốc 0; floorDiv=-1, floorMod=2.
9. `-1,-3`: thương thực dương nên floorDiv=0; dư floor âm -1.

Chương trình cố ý **không dùng phép chia cho 0**, vì cả `/`, `%`, `Math.floorDiv` và `Math.floorMod` trên số nguyên đều ném ArithmeticException trong trường hợp ấy.

## 5. Phép toán `/` và `%` trong Java tuân theo quy tắc nào?

Với `int` và `long`, Java dùng phép chia nguyên **truncation toward zero**.

~~~text
7 / 3   = 2
-7 / 3  = -2
7 / -3  = -2
-7 / -3 = 2
~~~

Phần dư `%` được định nghĩa để đi cùng thương `/`:

~~~text
(x / y) * y + (x % y) == x
~~~

Trong trường hợp số học thông thường, khi `x % y` khác 0, dấu của nó giống dấu của **x**, không phải y.

~~~text
-7 % 3  = -1
7 % -3  = 1
-7 % -3 = -1
~~~

**Đừng gọi `%` là modulo luôn trả số không âm.** Trong nhiều tài liệu toán và ngôn ngữ lập trình khác, từ "modulo" có quy tắc dư khác; trong Java, `%` chính xác hơn là **remainder operator** theo phép chia cắt về 0.

### 5.1. Vì sao `%` dễ làm hỏng chỉ số mảng?

~~~java
int index = -1 % 7;     // -1
int value = array[index]; // ArrayIndexOutOfBoundsException
~~~

Đây là **anti-pattern minh họa**; `array` cần được khai báo.

Khi cần giá trị từ 0 đến `length - 1` cho một mảng không rỗng, thay bằng:

~~~java
int index = Math.floorMod(-1, 7); // 6
~~~

Không nên dùng `%` khi `x` có thể âm mà yêu cầu đầu ra chắc chắn nằm trong tập chỉ số không âm.

## 6. Định nghĩa của floorDiv

Với số chia khác 0:

~~~text
q = Math.floorDiv(x, y)
  = floor(x / y) theo giá trị thương toán học chính xác
~~~

`floor` nghĩa là chọn số nguyên lớn nhất không lớn hơn kết quả chia thực.

**Không thực hiện phép toán bằng double trong định nghĩa trên** nếu code cần tính chính xác cho các giá trị `long` lớn. `Math.floorDiv` dùng arithmetic số nguyên theo hợp đồng, tránh vấn đề mất precision do ép `long` sang `double`.

### 6.1. Vì sao `floorDiv` khác `/` đúng lúc cần thiết?

Nếu hai số khác dấu và không chia hết:

~~~text
x / y                 : làm tròn kết quả âm về 0
Math.floorDiv(x, y)  : làm tròn kết quả âm về -∞
~~~

Ví dụ:

~~~text
-4 / 3                = -1
Math.floorDiv(-4, 3)  = -2
~~~

Nếu cùng dấu hoặc chia hết, kết quả thường trùng nhau.

### 6.2. Không nhầm với Math.floor(double)

~~~java
Math.floor(-7.0 / 3.0) // double -3.0
Math.floorDiv(-7, 3)   // int -3
~~~

`Math.floor(double)` làm việc với kiểu double và trả double. `Math.floorDiv` làm việc với `int`/`long` và trả kiểu nguyên tương ứng, phù hợp với logic bucket và modulo nguyên.

## 7. Định nghĩa và khoảng giá trị của floorMod

Oracle định nghĩa:

~~~text
r = Math.floorMod(x, y)
  = x - Math.floorDiv(x, y) * y
~~~

Vì vậy trong số học phù hợp kiểu, cặp thương/dư tuân theo:

~~~text
Math.floorDiv(x, y) * y
    + Math.floorMod(x, y)
    == x
~~~

### 7.1. Khi số chia dương

Nếu **`y > 0`** thì:

~~~text
0 <= Math.floorMod(x, y) < y
~~~

Điều này đúng với `x` âm, 0 hoặc dương:

~~~text
floorMod(-8, 7) = 6
floorMod(-1, 7) = 6
floorMod( 0, 7) = 0
floorMod( 8, 7) = 1
~~~

Vì thế `Math.floorMod(x, n)` là lựa chọn tự nhiên để ánh xạ số nguyên có thể âm vào **`0..n-1`**, miễn là `n > 0`.

### 7.2. Khi số chia âm

Nếu **`y < 0`** thì:

~~~text
y < Math.floorMod(x, y) <= 0
~~~

Ví dụ:

~~~text
Math.floorMod( 7, -3) = -2
Math.floorMod(-7, -3) = -1
Math.floorMod( 6, -3) =  0
~~~

**Như vậy không thể khẳng định `Math.floorMod` luôn trả kết quả dương.** Quy tắc đúng: phần dư khác 0 có **cùng dấu với số chia**, hoặc bằng 0.

### 7.3. Nếu số chia bằng ±1

Mọi số nguyên đều chia hết cho 1 và -1, nên:

~~~text
Math.floorMod(x,  1) = 0
Math.floorMod(x, -1) = 0
~~~

Thương có trường hợp tràn số khi x là `MIN_VALUE` và y là `-1` như mục riêng. Phần dư vẫn bằng 0 theo API.

### 7.4. Không dùng Math.abs(y) tùy tiện trong chứng minh

`Math.abs(Integer.MIN_VALUE)` vẫn bằng `Integer.MIN_VALUE` do overflow, tương tự với `Long.MIN_VALUE`. Vì vậy khi code phải xử lý toàn miền số nguyên, điều kiện dùng `Math.abs(y)` để kiểm tra khoảng dư có thể sai.

**Viết điều kiện theo dấu của y trực tiếp**:

~~~java
if (y > 0) {
    // 0 <= r && r < y
} else {
    // y < r && r <= 0
}
~~~

Giả sử đã kiểm tra `y != 0`.

## 8. Tự suy ra kết quả khi x âm, y dương

Chọn:

~~~text
x = -8
y = 7
~~~

Ta muốn một thương floor và một phần dư từ 0 tới 6:

~~~text
-8 = (-2) × 7 + 6
~~~

Nên:

~~~java
Math.floorDiv(-8, 7) == -2
Math.floorMod(-8, 7) == 6
~~~

Trong khi phép chia cắt về 0 là:

~~~text
-8 / 7 = -1
-8 % 7 = -1

-8 = (-1) × 7 + (-1)
~~~

**Nếu muốn “tuần số -2, ngày số 6 trong tuần”**, cặp floorDiv/floorMod phù hợp hơn cặp `/` và `%`.

Với số chia dương, floorMod mang tính chất **dư Euclid không âm**, thuận lợi cho indexing/bucketing.

## 9. Dấu của số dư: `%` so với `floorMod`

| Trường hợp | `%` khi khác 0 | `floorMod` khi khác 0 |
|---|---|---|
| `x > 0, y > 0` | Dương | Dương |
| `x < 0, y > 0` | Âm | Dương |
| `x > 0, y < 0` | Dương | Âm |
| `x < 0, y < 0` | Âm | Âm |

Nếu `x` chia hết cho `y`, cả hai phần dư đều là 0. Nếu hai số cùng dấu và không chia hết, `%` và floorMod trùng kết quả; nếu trái dấu và không chia hết, hai kết quả khác nhau.

### 9.1. Lưu ý về từ “modulo”

Nhiều thư viện và ngôn ngữ sử dụng phép mod có số dư luôn không âm khi modulus dương. Trong Java:

- `x % n` **không** bảo đảm không âm nếu `x` âm.
- `Math.floorMod(x, n)` bảo đảm **`0..n-1`** nếu **`n > 0`**.
- Với **`n < 0`**, `Math.floorMod` có thể âm, đúng theo dấu divisor.

**Chỉ dùng từ “mod luôn không âm” khi đã nêu điều kiện `n > 0`.**

## 10. Overload và lịch sử API vẫn có giá trị hiện nay

Các overload quan trọng của `Math`:

| Chữ ký | Kiểu trả về | Có từ |
|---|---|---|
| `Math.floorDiv(int x, int y)` | `int` | Java 8 |
| `Math.floorDiv(long x, long y)` | `long` | Java 8 |
| `Math.floorMod(int x, int y)` | `int` | Java 8 |
| `Math.floorMod(long x, long y)` | `long` | Java 8 |
| `Math.floorDiv(long x, int y)` | `long` | Java 9 |
| `Math.floorMod(long x, int y)` | `int` | Java 9 |
| `Math.floorDivExact(int x, int y)` | `int` | Java 18 |
| `Math.floorDivExact(long x, long y)` | `long` | Java 18 |

Các overload này vẫn có trong tài liệu **Java SE 26**.

### 10.1. Kiểu int

~~~java
int q = Math.floorDiv(-7, 3); // -3
int r = Math.floorMod(-7, 3); //  2
~~~

### 10.2. Kiểu long

~~~java
long q = Math.floorDiv(-7L, 3L); // -3
long r = Math.floorMod(-7L, 3L); //  2
~~~

### 10.3. Pha long/int

~~~java
long quotient = Math.floorDiv(-10L, 3);
int remainder = Math.floorMod(-10L, 3);
~~~

Các overload pha này có từ **Java 9**. Với project bị khóa ở Java 8, dùng overload **`(long,long)`** và chuyển kiểu có kiểm tra khi cần.

### 10.4. Kiểu trả về phải được hiểu

`Math.floorMod(long, int)` trả **int**, phù hợp vì dư có độ lớn nhỏ hơn số chia `int` (trong miền hợp lệ). `Math.floorMod(long,long)` trả **long**.

Khi đọc code có literal `3` và `3L`, chú ý overload nào được chọn:

~~~java
int a = Math.floorMod(-10L, 3);   // int
long b = Math.floorMod(-10L, 3L); // long
~~~

**Không có overload floorDiv/floorMod cho double hoặc BigDecimal**. Hai method này dành cho arithmetic nguyên `int`/`long`.

## 11. Ví dụ: overload int, long và pha kiểu

Lưu thành **`FloorDivOverloadsDemo.java`**:

~~~java
public class FloorDivOverloadsDemo {
    public static void main(String[] args) {
        int intQuotient = Math.floorDiv(-10, 3);
        int intRemainder = Math.floorMod(-10, 3);

        long longQuotient = Math.floorDiv(-10L, 3L);
        long longRemainder = Math.floorMod(-10L, 3L);

        long mixedQuotient = Math.floorDiv(-10L, 3);
        int mixedRemainder = Math.floorMod(-10L, 3);

        System.out.println("int=" + intQuotient
                + "," + intRemainder);

        System.out.println("long=" + longQuotient
                + "," + longRemainder);

        System.out.println("mixed=" + mixedQuotient
                + "," + mixedRemainder);
    }
}
~~~

~~~bash
javac -encoding UTF-8 FloorDivOverloadsDemo.java
java FloorDivOverloadsDemo
~~~

**Stdout:**

~~~text
int=-4,2
long=-4,2
mixed=-4,2
~~~

**Giải thích:** -10 chia 3 theo floor cho thương -4, dư 2 ở cả ba trường hợp. Khác nhau ở **chữ ký và kiểu trả về**, không phải nghĩa phép toán. Chương trình yêu cầu tối thiểu Java 9 vì dùng overload pha long/int; Java 17+ chạy trực tiếp.

## 12. Trường hợp đặc biệt: chia cho 0

Với số nguyên, cả hai toán tử và hai phương thức:

~~~java
x / 0
x % 0
Math.floorDiv(x, 0)
Math.floorMod(x, 0)
~~~

đều ném **ArithmeticException**.

### 12.1. Kiểm tra mẫu số có nghĩa nghiệp vụ

Trong hệ thống thực tế:

~~~java
static int normalizedIndex(int value, int size) {
    if (size <= 0) {
        throw new IllegalArgumentException(
                "size must be positive");
    }
    return Math.floorMod(value, size);
}
~~~

Đây là đoạn minh họa method Java. Kiểm tra `size > 0` không chỉ ngăn chia cho 0 mà còn loại mẫu số âm — cần thiết vì index mảng không thể âm.

### 12.2. Vì sao không chỉ bắt ArithmeticException?

Nếu `size` là độ dài mảng, một số âm là **input không hợp lệ** ngay cả khi `Math.floorMod(value, size)` có thể tính toán. Hãy validate contract ở biên, rồi để `Math.floorMod` xử lý trường hợp số bị chia âm.

### 12.3. Java exception message không phải API ổn định

Khi ném `ArithmeticException`, thông điệp lỗi cụ thể (ví dụ `"/ by zero"`) không nên là cơ sở cho logic nghiệp vụ. Bắt đúng kiểu exception hoặc validate trước bằng điều kiện rõ ràng.

## 13. Biên nguy hiểm: Integer.MIN_VALUE / -1

`int` có miền:

~~~text
Integer.MIN_VALUE = -2147483648
Integer.MAX_VALUE =  2147483647
~~~

Khi tính thương toán học:

~~~text
-2147483648 / -1 = +2147483648
~~~

Kết quả dương này **lớn hơn Integer.MAX_VALUE**, nên không thể biểu diễn trong `int`.

Trong Java integer arithmetic, trường hợp:

~~~java
Integer.MIN_VALUE / -1
~~~

**không ném ArithmeticException do overflow**. Kết quả là **Integer.MIN_VALUE** theo quy tắc tràn đặc biệt của phép chia nguyên.

`Math.floorDiv(Integer.MIN_VALUE, -1)` cũng trả **Integer.MIN_VALUE** theo hợp đồng. `Math.floorMod(Integer.MIN_VALUE, -1)` trả **0**, vì phép chia hết.

### 13.1. Long.MIN_VALUE có tình huống tương tự

~~~text
Long.MIN_VALUE  = -9223372036854775808
Long.MAX_VALUE  =  9223372036854775807
~~~

`Math.floorDiv(Long.MIN_VALUE, -1L)` trả `Long.MIN_VALUE` vì thương toán học dương vượt miền long.

### 13.2. Đừng hiểu trường hợp này là thương floor toán học chính xác

Đây là **ngoại lệ do tràn kiểu số nguyên**, không phải định nghĩa floor đã đổi. Nếu nghiệp vụ yêu cầu phát hiện mọi overflow, phải xử lý riêng.

### 13.3. Math.floorDivExact (Java 18+)

Java hiện đại có:

~~~java
Math.floorDivExact(Integer.MIN_VALUE, -1)
Math.floorDivExact(Long.MIN_VALUE, -1L)
~~~

Phương thức này **ném ArithmeticException** ở trường hợp overflow `MIN_VALUE / -1`, và cũng ném lỗi khi mẫu số bằng 0.

**Quan trọng về phiên bản:** `Math.floorDivExact` được bổ sung từ **Java 18**, nên ví dụ sử dụng nó **không compile trên Java 17**. Nếu dự án chạy Java 17, có thể kiểm tra biên trước khi dùng floorDiv, hoặc dùng `BigInteger` khi cần biểu diễn kết quả vượt miền long.

### 13.4. Đừng nhầm `floorDivExact` với toán tử `/`

`floorDivExact` vẫn dùng **floor rounding**, nhưng kiểm tra overflow. Còn `Math.divideExact` (cũng có từ Java 18) thực hiện **truncating quotient với kiểm tra overflow**, không thay thế floorDiv trong các thuật toán cần làm tròn về âm vô cực.

## 14. Ví dụ overflow và chia cho 0 trong Java 17+

Lưu thành **`FloorDivisionEdgeDemo.java`**:

~~~java
public class FloorDivisionEdgeDemo {
    public static void main(String[] args) {
        int min = Integer.MIN_VALUE;

        System.out.println("min=" + min);
        System.out.println("slash=" + (min / -1));
        System.out.println("floorDiv="
                + Math.floorDiv(min, -1));
        System.out.println("floorMod="
                + Math.floorMod(min, -1));

        long longMin = Long.MIN_VALUE;

        System.out.println("longFloorDiv="
                + Math.floorDiv(longMin, -1L));
        System.out.println("longFloorMod="
                + Math.floorMod(longMin, -1L));

        try {
            Math.floorDiv(12, 0);
        } catch (ArithmeticException ex) {
            System.out.println("zeroDiv=ArithmeticException");
        }

        try {
            Math.floorMod(12, 0);
        } catch (ArithmeticException ex) {
            System.out.println("zeroMod=ArithmeticException");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 FloorDivisionEdgeDemo.java
java FloorDivisionEdgeDemo
~~~

**Stdout:**

~~~text
min=-2147483648
slash=-2147483648
floorDiv=-2147483648
floorMod=0
longFloorDiv=-9223372036854775808
longFloorMod=0
zeroDiv=ArithmeticException
zeroMod=ArithmeticException
~~~

**Giải thích:** Toán tử `/` và floorDiv cùng có overflow đặc biệt với MIN_VALUE/-1. Các phương thức chia/lấy mod ném ArithmeticException nếu `y==0`. Ví dụ không phụ thuộc thông điệp exception.

### 14.1. Ví dụ riêng Java 18+: floorDivExact

Lưu thành **`FloorDivExactDemo.java`** và chỉ compile trên Java **18+**:

~~~java
public class FloorDivExactDemo {
    public static void main(String[] args) {
        try {
            Math.floorDivExact(Integer.MIN_VALUE, -1);
        } catch (ArithmeticException ex) {
            System.out.println("intOverflowDetected=true");
        }

        try {
            Math.floorDivExact(Long.MIN_VALUE, -1L);
        } catch (ArithmeticException ex) {
            System.out.println("longOverflowDetected=true");
        }

        System.out.println("normal="
                + Math.floorDivExact(-7, 3));
    }
}
~~~

~~~bash
javac -encoding UTF-8 FloorDivExactDemo.java
java FloorDivExactDemo
~~~

**Stdout:**

~~~text
intOverflowDetected=true
longOverflowDetected=true
normal=-3
~~~

Nếu project đang sử dụng Java 17, không đưa lời gọi `floorDivExact` vào code chính mà không nâng mức source/runtime. Nó là API hiện hành, nhưng **không thuộc Java 8/17 API surface**.

## 15. Tránh dùng Math.floor trên double để thay floorDiv(long,long)

Một công thức sai về độ chính xác:

~~~java
long quotient = (long) Math.floor(
        (double) x / (double) y);
~~~

Với `long` lớn, ép sang `double` có thể làm mất các bit thấp. Khi kết quả floor nằm gần ranh giới số nguyên, sai số chuyển đổi có thể làm lệch thương.

Ví dụ đã kiểm thử:

~~~java
long x = Long.MAX_VALUE;

long exact = Math.floorDiv(x, 2L);

long fromDouble =
        (long) Math.floor((double) x / 2.0);
~~~

Kết quả:

~~~text
exact      = 4611686018427387903
fromDouble = 4611686018427387904
~~~

`Long.MAX_VALUE` không thể biểu diễn chính xác bằng double. Phép chia số thực và ép về long có thể làm sai phần nguyên.

**Đừng ép int/long sang double chỉ để tự tạo floor division.** `Math.floorDiv` có đúng mục đích và hợp đồng số nguyên. Nếu cần kết quả vượt miền `long`, dùng BigInteger với chính sách chia phù hợp.

## 16. Ứng dụng 1 — chỉ số vòng tròn (circular index)

Giả sử có vòng 7 vị trí, các chỉ số hợp lệ:

~~~text
0 1 2 3 4 5 6
~~~

Bạn muốn ánh xạ mọi số nguyên (cả âm) vào vòng:

~~~text
-1 -> 6
-2 -> 5
-7 -> 0
-8 -> 6
 0 -> 0
 7 -> 0
 8 -> 1
~~~

Khi **số vị trí dương**, dùng:

~~~java
int normalized = Math.floorMod(index, size);
~~~

### 16.1. Vì sao `%` không đủ?

~~~java
int size = 7;

System.out.println(-1 % size);               // -1
System.out.println(Math.floorMod(-1, size)); //  6
~~~

`-1` không phải chỉ số mảng hợp lệ, còn `6` là vị trí cuối trong vòng có 7 phần tử.

### 16.2. Demo độc lập

Lưu thành **`CircularIndexDemo.java`**:

~~~java
public class CircularIndexDemo {
    static int normalize(int index, int size) {
        if (size <= 0) {
            throw new IllegalArgumentException(
                    "size must be positive");
        }
        return Math.floorMod(index, size);
    }

    public static void main(String[] args) {
        int size = 7;

        int[] inputs = {-10, -8, -1, 0, 7, 8, 22};

        for (int index : inputs) {
            System.out.println(index + " -> "
                    + normalize(index, size));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CircularIndexDemo.java
java CircularIndexDemo
~~~

**Stdout:**

~~~text
-10 -> 4
-8 -> 6
-1 -> 6
0 -> 0
7 -> 0
8 -> 1
22 -> 1
~~~

**Giải thích:** Nhờ `size=7>0`, `floorMod` luôn trả trong `0..6`. Với `index=-10`, `-10 = (-2)*7 + 4`, nên vị trí cuối cùng là 4.

### 16.3. Không dùng `Math.abs(index) % size`

Một cách viết dễ sai:

~~~java
int normalized = Math.abs(index) % size;
~~~

**Sai về semantics:** `-1` sẽ thành `1`, nhưng trong vòng 7 vị trí, ta muốn `6` nếu di chuyển lùi một bước từ 0.

**Sai ở MIN_VALUE:** `Math.abs(Integer.MIN_VALUE)` vẫn âm vì overflow, nên kết quả `% size` có thể âm.

**Nên dùng:** `Math.floorMod(index, size)` với `size>0`.

### 16.4. Mảng thật cần thêm điều kiện

Nếu `size = array.length`, mảng phải không rỗng. Math.floorMod không tự tạo ra phần tử cho mảng rỗng.

Với một số bài toán concurrency, **chỉ số hợp lệ không đồng nghĩa truy cập thread-safe**. Vòng dữ liệu chia sẻ cần đồng bộ hoặc cấu trúc concurrent thích hợp.

## 17. Ứng dụng 2 — phân nhóm số âm thành bucket

Giả sử muốn chia trục số nguyên thành các đoạn độ rộng 10:

~~~text
Bucket -2: -20 ... -11
Bucket -1: -10 ... -1
Bucket  0:   0 ...  9
Bucket  1:  10 ... 19
~~~

Định nghĩa bucket:

~~~java
int bucket = Math.floorDiv(value, 10);
int position = Math.floorMod(value, 10);
~~~

Với `value=-1`:

~~~text
bucket = -1
position = 9

-1 = (-1) * 10 + 9
~~~

Trong khi `/` và `%` cho:

~~~text
-1 / 10 = 0
-1 % 10 = -1
~~~

Nếu bạn gán `value=-1` vào bucket 0 thì nó bị xếp cùng `0..9`, không tương ứng các khoảng bắt đầu tại bội số 10.

### 17.1. Một bảng bucket

| value | floorDiv(value,10) | floorMod(value,10) |
|---:|---:|---:|
| `-21` | `-3` | `9` |
| `-20` | `-2` | `0` |
| `-11` | `-2` | `9` |
| `-10` | `-1` | `0` |
| `-1` | `-1` | `9` |
| `0` | `0` | `0` |
| `9` | `0` | `9` |
| `10` | `1` | `0` |
| `21` | `2` | `1` |

**Đặt bucket bằng floorDiv khi các bucket có ranh giới dựa trên bội số của width**, đặc biệt khi dữ liệu có thể âm.

### 17.2. Không nhầm “bucket số âm” với indexing

Giá trị **bucket** có thể âm, điều đó hoàn toàn hợp lý nếu nó là nhãn của một khoảng trên trục số. Giá trị **position** trong bucket với width dương thì không âm. Nếu cần đưa bucket ID vào mảng, phải normalize hoặc xây ánh xạ riêng theo yêu cầu.

## 18. Demo bucket một chiều

Lưu thành **`SignedBucketDemo.java`**:

~~~java
public class SignedBucketDemo {
    public static void main(String[] args) {
        int width = 10;
        int[] values = {
                -21, -20, -11, -10,
                -1, 0, 9, 10, 21
        };

        for (int value : values) {
            int bucket = Math.floorDiv(value, width);
            int position = Math.floorMod(value, width);

            System.out.println(
                    value + " -> bucket=" + bucket
                    + ",offset=" + position);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SignedBucketDemo.java
java SignedBucketDemo
~~~

**Stdout:**

~~~text
-21 -> bucket=-3,offset=9
-20 -> bucket=-2,offset=0
-11 -> bucket=-2,offset=9
-10 -> bucket=-1,offset=0
-1 -> bucket=-1,offset=9
0 -> bucket=0,offset=0
9 -> bucket=0,offset=9
10 -> bucket=1,offset=0
21 -> bucket=2,offset=1
~~~

**Giải thích:** Mỗi số được tách thành **bucket** và **vị trí không âm** trong bucket, luôn dùng cùng width dương.

### 18.1. Cẩn thận tính điểm bắt đầu bằng nhân

Để tính số bắt đầu bucket, có thể viết:

~~~java
long bucketStart =
        (long) bucket * width;
~~~

Nếu bucket/width là `int`, ép sang long trước khi nhân tránh overflow ở phép nhân int. Tuy nhiên, nếu đầu vào gốc là `long` toàn miền và width rất lớn, tích có thể vượt long; cần thiết kế overflow/BigInteger khi có yêu cầu.

## 19. Ứng dụng 3 — milliseconds âm và Unix epoch

Một vấn đề thực tế: milliseconds tính từ Unix epoch (`1970-01-01T00:00:00Z`) có thể **âm** nếu thời điểm trước 1970.

Giả sử:

~~~text
epochMillis = -1
millisPerHour = 3_600_000
~~~

Nếu dùng phép chia thông thường:

~~~text
-1 / 3_600_000 = 0
-1 % 3_600_000 = -1
~~~

Nó gán millisecond cuối **trước** epoch vào hour bucket 0, dễ khiến phân nhóm thời gian sai.

Với floorDiv/floorMod:

~~~text
Math.floorDiv(-1, 3_600_000) = -1
Math.floorMod(-1, 3_600_000) = 3_599_999
~~~

Tức timestamp `-1ms` nằm trong **giờ bucket -1**, ở vị trí **3.599.999ms** của bucket đó.

### 19.1. Demo độc lập

Lưu thành **`EpochBucketDemo.java`**:

~~~java
public class EpochBucketDemo {
    private static final long MILLIS_PER_HOUR =
            3_600_000L;

    public static void main(String[] args) {
        long[] timestamps = {
                -3_600_001L,
                -3_600_000L,
                -1L,
                0L,
                1L,
                3_600_001L
        };

        for (long epochMillis : timestamps) {
            long hourIndex = Math.floorDiv(
                    epochMillis, MILLIS_PER_HOUR);

            long withinHour = Math.floorMod(
                    epochMillis, MILLIS_PER_HOUR);

            System.out.println(
                    "t=" + epochMillis
                    + ",hour=" + hourIndex
                    + ",offset=" + withinHour);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 EpochBucketDemo.java
java EpochBucketDemo
~~~

**Stdout:**

~~~text
t=-3600001,hour=-2,offset=3599999
t=-3600000,hour=-1,offset=0
t=-1,hour=-1,offset=3599999
t=0,hour=0,offset=0
t=1,hour=0,offset=1
t=3600001,hour=1,offset=1
~~~

**Giải thích:**

- `-3_600_001` ms thuộc bucket -2 và nằm ở millisecond cuối của bucket đó.
- `-3_600_000` ms nằm đúng đầu bucket -1.
- `-1` ms nằm cuối bucket -1.
- `0` ms là đầu bucket 0.
- `3_600_001` ms nằm bucket 1, offset 1.

### 19.2. Không dùng điều này để tính giờ địa phương tùy ý

Ví dụ trên chỉ chia **epoch milliseconds thành các giờ dài đúng 3.600.000ms trên trục thời gian UTC/timestamp**. Nó **không** tự tính “giờ dân sự tại múi giờ địa phương” trong mọi tình huống, vì **DST**, múi giờ và lịch có quy tắc riêng.

Nếu cần ngày/giờ local thật, dùng API **java.time** (`Instant`, `ZoneId`, `ZonedDateTime`, `LocalDate`, `LocalTime`...) với quy tắc timezone chính xác.

**floorDiv/floorMod là công cụ số học**, không thay thế toàn bộ hệ thống ngày giờ.

## 20. Ứng dụng 4 — modulo dương trong sharding và hash partition

Một ứng dụng có N partitions (N dương) có thể gán khóa nguyên vào một partition:

~~~java
int partition = Math.floorMod(hash, partitionCount);
~~~

Với `hash < 0`, phương thức vẫn trả phần tử trong `0..partitionCount-1`.

### 20.1. Vì sao không dùng Math.abs(hash) % N?

`Integer.MIN_VALUE` là trường hợp `Math.abs` không cho số dương vì overflow. Khi hash function có thể trả toàn miền int, cách viết này có rủi ro chỉ số âm.

### 20.2. Mẫu method an toàn về miền chỉ số

~~~java
static int partitionOf(int hash, int partitionCount) {
    if (partitionCount <= 0) {
        throw new IllegalArgumentException(
                "partitionCount must be positive");
    }

    return Math.floorMod(hash, partitionCount);
}
~~~

Đây là đoạn minh họa Java.

**Tính hợp lệ của index không đồng nghĩa tính đúng của chiến lược sharding.** Bạn vẫn cần xem xét phân phối hash, tính ổn định khi partitionCount thay đổi, key ownership, đồng bộ giữa nodes và bảo mật. `Math.floorMod` chỉ cung cấp số dư có miền phù hợp.

### 20.3. Không nhầm hash partition với mật mã

`hashCode()` Java không phải cryptographic hash. Nếu định tuyến dữ liệu nhạy cảm hoặc chống đầu vào gây DoS, chọn hash function và kiến trúc phù hợp. floorMod không cung cấp khả năng chống collision hoặc đồng đều tuyệt đối.

## 21. Ứng dụng 5 — chu kỳ lặp, thứ và trạng thái luân phiên

Giả sử cần biểu diễn “vị trí trong chu kỳ 7 ngày”, trong đó ngày gốc là số 0 và chỉ số có thể âm để biểu diễn các ngày trước mốc.

~~~java
int position = Math.floorMod(dayOffset, 7);
~~~

Ví dụ:

~~~text
dayOffset -8 -> position 6
dayOffset -7 -> position 0
dayOffset -1 -> position 6
dayOffset  0 -> position 0
dayOffset  8 -> position 1
~~~

Khi cần đếm số chu kỳ đầy đủ:

~~~java
int cycle = Math.floorDiv(dayOffset, 7);
int position = Math.floorMod(dayOffset, 7);
~~~

Hai giá trị tuân theo:

~~~text
dayOffset = cycle * 7 + position
~~~

**Không tự đặt tên thứ Hai/Chủ Nhật cho các số này** nếu chưa xác định chuẩn đánh số, ngày mốc và múi giờ của domain. floorMod xử lý số học của offset, còn lịch/tuần thực tế có các quy tắc riêng.

## 22. Math.floorMod khác BigInteger.mod ra sao?

Với số lớn hơn long hoặc yêu cầu exact không overflow, Java có `BigInteger`.

Hai method có hành vi khác biệt:

~~~java
BigInteger a = BigInteger.valueOf(-7);
BigInteger m = BigInteger.valueOf(3);

a.remainder(m); // -1
a.mod(m);       //  2
~~~

- `BigInteger.remainder(...)` cho dư theo quy tắc tương tự phép chia nguyên hướng về 0.
- `BigInteger.mod(...)` yêu cầu **modulus dương** và trả số dư không âm.
- `Math.floorMod(x,y)` hỗ trợ cả số chia **dương lẫn âm**; khi số chia âm, phần dư có thể âm.

### 22.1. Mẫu số âm của BigInteger.mod

~~~java
BigInteger.valueOf(-7)
        .mod(BigInteger.valueOf(-3));
~~~

Ném **ArithmeticException** vì modulus không dương, theo hợp đồng `BigInteger.mod`.

**Không đánh đồng BigInteger.mod với Math.floorMod cho mọi dấu của y.** Chúng trùng cách chọn số dư khi modulus dương; điều kiện đối với mẫu số âm khác nhau.

### 22.2. Demo BigInteger

Lưu thành **`BigIntegerModuloDemo.java`**:

~~~java
import java.math.BigInteger;

public class BigIntegerModuloDemo {
    public static void main(String[] args) {
        BigInteger x = BigInteger.valueOf(-7);
        BigInteger positive = BigInteger.valueOf(3);
        BigInteger negative = BigInteger.valueOf(-3);

        System.out.println("remainder="
                + x.remainder(positive));
        System.out.println("mod=" + x.mod(positive));

        try {
            x.mod(negative);
        } catch (ArithmeticException ex) {
            System.out.println("negativeModulusRejected=true");
        }

        BigInteger tooLargeForInt =
                BigInteger.valueOf(Integer.MIN_VALUE).negate();

        System.out.println("positiveQuotient="
                + tooLargeForInt);
    }
}
~~~

~~~bash
javac -encoding UTF-8 BigIntegerModuloDemo.java
java BigIntegerModuloDemo
~~~

**Stdout:**

~~~text
remainder=-1
mod=2
negativeModulusRejected=true
positiveQuotient=2147483648
~~~

**Giải thích:** Kết quả toán học của `Integer.MIN_VALUE/-1` là `2147483648`, không biểu diễn được trong int nhưng BigInteger biểu diễn được.

### 22.3. Khi nào cần BigInteger?

- Đầu vào lớn hơn miền long.
- Cần tránh tràn số nguyên ở phép chia, nhân hoặc tính các ranh giới.
- Cần số học chính xác với kết quả vượt các primitive types.
- Cần modulo dương theo hợp đồng BigInteger.mod.

**Không tự chọn BigInteger cho mọi chỉ số mảng nhỏ**, vì primitive arithmetic đơn giản và hiệu quả hơn khi miền dữ liệu đã được kiểm soát.

## 23. Rủi ro overflow khi tự tính công thức

Hợp đồng toán học:

~~~text
r = x - floorDiv(x,y) * y
~~~

là cách hiểu tốt. Nhưng trong Java, nếu tự viết phép nhân/trừ bằng int, các intermediate expressions có thể overflow ngay cả khi kết quả cuối cùng hợp lệ.

Ví dụ với `Integer.MIN_VALUE` và `y=3`, thương floor nhân với 3 có thể thấp hơn `Integer.MIN_VALUE` trước khi cộng số dư. Java dùng two's-complement wraparound, nên tự viết công thức dễ gây nhầm trong code cần overflow detection.

**Ưu tiên trực tiếp `Math.floorMod(x,y)`** thay vì tự dựng:

~~~java
int r = x - Math.floorDiv(x, y) * y;
~~~

Nếu cần kiểm tra bất biến trên toàn miền `int`, có thể dùng `long` cho bước tái tạo trong test, **ngoại trừ trường hợp thương toán học không nằm trong kiểu** `MIN_VALUE / -1` cần xử lý riêng.

### 23.1. Vì sao Math.abs(y) có thể sai?

~~~java
Math.abs(Integer.MIN_VALUE)
Math.abs(Long.MIN_VALUE)
~~~

đều có thể giữ giá trị âm tương ứng vì trị tuyệt đối toán học vượt miền dương biểu diễn được. Khi cần kiểm tra bound hoặc chuẩn hóa mẫu số âm, **đừng chỉ dùng Math.abs mà quên biên MIN_VALUE**.

### 23.2. Chia hết vẫn có phần dư 0

Bất kể dấu của các toán hạng (với mẫu số không 0), phép chia hết có:

~~~text
x % y == 0
Math.floorMod(x, y) == 0
~~~

Điều này vẫn đúng trong trường hợp đặc biệt MIN_VALUE/-1, dù thương overflow trong kiểu primitive.

## 24. Kiểm thử tính chất số học bằng vòng lặp

Kiểm thử chỉ một cặp `-7,3` chưa đủ. Nên bao gồm:

- Hai số đều dương.
- Số bị chia âm, số chia dương.
- Số bị chia dương, số chia âm.
- Hai số đều âm.
- Zero dividend, nonzero divisor.
- Chia hết và chia không hết.
- `Integer.MIN_VALUE`/`Integer.MAX_VALUE`.
- Chia cho 0.
- `Integer.MIN_VALUE / -1` cần xử lý riêng trong mô hình toán học.

Với giá trị thông thường:

~~~text
q = Math.floorDiv(x, y)
r = Math.floorMod(x, y)

x == q * y + r
~~~

và:

~~~text
y > 0  => 0 <= r < y
y < 0  => y < r <= 0
~~~

### 24.1. Demo property test trên toàn miền dấu đại diện

Lưu thành **`FloorDivisionPropertyTest.java`**:

~~~java
public class FloorDivisionPropertyTest {
    private static void assertPair(int x, int y) {
        int q = Math.floorDiv(x, y);
        int r = Math.floorMod(x, y);

        if (x == Integer.MIN_VALUE && y == -1) {
            if (q != Integer.MIN_VALUE || r != 0) {
                throw new AssertionError("MIN/-1 behavior");
            }
            return;
        }

        // Dùng long để tránh overflow khi tính lại q*y.
        long reconstructed = (long) q * y + r;

        if (reconstructed != x) {
            throw new AssertionError(
                    "identity: " + x + "," + y);
        }

        boolean validRange = y > 0
                ? r >= 0 && r < y
                : r > y && r <= 0;

        if (!validRange) {
            throw new AssertionError(
                    "remainder range: " + x + "," + y);
        }
    }

    public static void main(String[] args) {
        int[] values = {
                Integer.MIN_VALUE,
                -100, -10, -7, -1,
                0, 1, 7, 10, 100,
                Integer.MAX_VALUE
        };

        int[] divisors = {
                Integer.MIN_VALUE,
                -9, -3, -1,
                1, 3, 9,
                Integer.MAX_VALUE
        };

        int checked = 0;

        for (int x : values) {
            for (int y : divisors) {
                assertPair(x, y);
                checked++;
            }
        }

        System.out.println("checked=" + checked);
        System.out.println("allPassed=true");
    }
}
~~~

~~~bash
javac -encoding UTF-8 FloorDivisionPropertyTest.java
java FloorDivisionPropertyTest
~~~

**Stdout:**

~~~text
checked=88
allPassed=true
~~~

**Giải thích:**

1. Có 11 số bị chia × 8 số chia (đều khác 0) = 88 cặp.
2. `q` và `r` lấy từ floorDiv/floorMod.
3. Dùng `long` để tái tạo `(long)q*y+r` mà không tràn trong phần lớn cặp int.
4. Trường hợp `Integer.MIN_VALUE,-1` được xử lý riêng vì thương toán học không biểu diễn được trong int.
5. Range được kiểm tra theo dấu **y**, không dùng Math.abs(y).
6. Nếu một bất biến bị vi phạm, chương trình ném AssertionError và không in `allPassed=true`.

**Tại sao không dùng `assert` của Java một cách tùy tiện?** Từ khóa `assert` bị tắt theo mặc định trừ khi chạy `-ea`; chương trình ở đây dùng AssertionError trực tiếp để kiểm thử luôn có hiệu lực.

### 24.2. Không tự suy mọi công thức đều đúng trong số học vô hạn

Khi primitive overflow, định nghĩa toán học và phép toán thực tế trong Java cần được phân biệt. Ví dụ `MIN_VALUE/-1` là trường hợp đặc biệt; tính bằng BigInteger có thể cho thương chính xác ngoài miền int. Hãy kiểm thử đủ biên thay vì chỉ áp một công thức số học thực cho mọi giá trị.

## 25. Đối chiếu với Math.ceilDiv (Java 18+)

Ngoài `floorDiv`, Java hiện đại có `Math.ceilDiv(...)` từ **Java 18** để tính thương làm tròn **lên dương vô cực**, và `Math.ceilMod(...)` đi kèm.

Ví dụ:

~~~text
floorDiv( 7, 3) = 2
ceilDiv( 7, 3)  = 3

floorDiv(-7, 3) = -3
ceilDiv(-7, 3)  = -2
~~~

**Không nhầm floor với ceil**. Khi bài toán cần “số trang/batch tối thiểu để chứa N phần tử dương”, có thể cần ceiling division, chứ không phải floorDiv.

**Các API ceilDiv/ceilMod không có trong Java 17**. Với Java 17, không dán trực tiếp ví dụ `Math.ceilDiv` vào source. Bài này tập trung `floorDiv/floorMod`, đều có từ Java 8 và vẫn được khuyến nghị dùng khi đúng semantics.

## 26. Cách chọn công cụ theo bài toán

| Bài toán | Cách thường phù hợp |
|---|---|
| Chia số nguyên, cắt về 0 | `x / y` |
| Lấy remainder có dấu của dividend | `x % y` |
| Chia ra bucket có thể âm theo bội số dương | `Math.floorDiv(x, width)` |
| Lấy vị trí 0..n-1 với n>0 và x có thể âm | `Math.floorMod(x, n)` |
| Chia milliseconds âm trước Unix epoch vào các khoảng cố định | `Math.floorDiv` + `Math.floorMod` |
| Tìm vị trí trong vòng circular/ring | `Math.floorMod(index, size)` với size>0 |
| Chọn partition theo hash có thể âm | `Math.floorMod(hash, partitionCount)` |
| Cần phát hiện overflow MIN_VALUE/-1 | `Math.floorDivExact` trên Java 18+ |
| Cần thương toán học vượt long | `BigInteger` |
| Cần modulo dương BigInteger | `BigInteger.mod` với modulus dương |
| Cần local date/time theo timezone thật | `java.time` với `ZoneId` |
| Cần phép chia làm tròn lên dương vô cực | `Math.ceilDiv` trên Java 18+ hoặc thuật toán tương đương phù hợp phiên bản |

**Không có phương thức nào đúng cho mọi yêu cầu.** Xác định trước **rounding mode**, **dấu của số dư**, **miền mẫu số** và **chính sách overflow**.

## 27. Những lỗi thường gặp

### Lỗi 1 — Nghĩ `/` của Java làm tròn xuống với số âm

`-7/3` là `-2`, không phải `-3`. `/` với int/long cắt về 0.

### Lỗi 2 — Nghĩ `%` luôn không âm

`-7%3` là `-1`. Nếu cần số dư không âm với mẫu số dương, dùng floorMod.

### Lỗi 3 — Dùng `%` làm index khi x có thể âm

`-1 % 7 = -1`, không hợp lệ cho mảng. `Math.floorMod(-1,7)=6`.

### Lỗi 4 — Dùng `Math.abs(x) % n` để sửa chỉ số

Đây không phải modulo tương đương về nghĩa; `-1` thành 1 thay vì n-1, và `MIN_VALUE` làm abs overflow.

### Lỗi 5 — Nghĩ floorMod luôn trả số dương

Nếu **y âm**, phần dư khác 0 của floorMod cũng âm.

### Lỗi 6 — Đưa size hoặc partitionCount âm

Nếu cần index, **size phải >0**, không chỉ khác 0.

### Lỗi 7 — Quên chia cho 0

`floorDiv(x,0)` và `floorMod(x,0)` đều ném ArithmeticException.

### Lỗi 8 — Tưởng `floorDiv(MIN_VALUE,-1)` ném overflow

Nó **trả MIN_VALUE** theo hợp đồng API. Dùng `floorDivExact` Java 18+ hoặc check biên nếu cần báo lỗi.

### Lỗi 9 — Dùng floorDivExact trong project Java 17 mà không kiểm tra version

`floorDivExact` ra đời ở Java 18; source target Java 17 không có method này.

### Lỗi 10 — Dùng Math.floor(double) để thay floorDiv(long,long)

`double` không biểu diễn chính xác mọi long. Kết quả nguyên có thể lệch gần biên.

### Lỗi 11 — Nhầm `floorDiv` với `ceilDiv`

floor làm tròn về -∞, ceil về +∞. `ceilDiv` là Java 18+ và dùng cho mục đích khác.

### Lỗi 12 — Tự dựng floorMod bằng phép nhân/trừ int khi có thể overflow

Công thức hiểu được, nhưng nếu bạn tự viết trung gian và kết hợp các cast sai, có thể gây lỗi. Dùng method chuẩn.

### Lỗi 13 — Kiểm tra range bằng Math.abs(Integer.MIN_VALUE)

`Math.abs(MIN_VALUE)` bị overflow. Kiểm tra trực tiếp theo dấu y.

### Lỗi 14 — Nhầm `%` của Java với Python-style modulo

Quy tắc của các ngôn ngữ có thể khác. Không chuyển thuật toán tính index âm theo thói quen từ ngôn ngữ khác mà không kiểm tra.

### Lỗi 15 — Đồng nhất Math.floorMod với BigInteger.mod khi divisor âm

BigInteger.mod yêu cầu modulus dương; Math.floorMod có thể tính với y âm.

### Lỗi 16 — Gộp thời gian theo `/` khi epochMillis âm

`-1/3600000` bằng 0, không đúng bucket trước epoch theo floor. Dùng floorDiv.

### Lỗi 17 — Dùng floorDiv để tự tính ngày địa phương qua DST

Các ngày trong timezone không luôn 24 giờ thực tế; dùng API java.time và ZoneId.

### Lỗi 18 — Dùng modulo index mà không xác nhận array không rỗng

`Math.floorMod(x,0)` vẫn lỗi; validate size > 0.

### Lỗi 19 — Nghĩ mã hash modulo đảm bảo phân bố đều hoặc bảo mật

floorMod chỉ chuẩn hóa miền số; không sửa chất lượng hash hay cơ chế phân phối.

### Lỗi 20 — Trộn int và long mà không hiểu overload

`Math.floorMod(long,int)` trả int trên Java 9+; `floorMod(long,long)` trả long. Chọn kiểu đúng và kiểm tra phiên bản.

### Lỗi 21 — Viết test chỉ có số dương

Không thấy khác biệt giữa `/` và floorDiv; phải có trường hợp trái dấu, chia hết, 0 và MIN_VALUE/-1.

### Lỗi 22 — Đọc đẳng thức floorDiv*y+floorMod như số học vô hạn trong mọi overflow

Cần hiểu primitive wraparound và ngoại lệ MIN_VALUE/-1; trong mô hình BigInteger, thương toán học là số lớn hơn miền int/long.

### Lỗi 23 — Viết kiểm tra invalid input chỉ dựa vào `%`

`x % n` cho kết quả âm khi x âm và không có vấn đề kiểu, nhưng không có nghĩa index âm được chấp nhận.

### Lỗi 24 — Không nêu đơn vị của width

Một bucket thời gian có thể dùng giây, milliseconds, microseconds. Trộn đơn vị cho kết quả sai dù floorDiv/floorMod hoạt động đúng.

## 28. Checklist production

- [ ] Đã xác định có thể có **số âm** ở cả dividend và divisor.
- [ ] Đã xác định **quy tắc làm tròn** muốn dùng: truncation hay floor.
- [ ] Đã xác định **dấu của remainder** muốn dùng.
- [ ] Nếu là chỉ số, divisor/size luôn **dương**.
- [ ] Có validation `y != 0` hoặc `size > 0` khi phù hợp.
- [ ] Biết `MIN_VALUE/-1` có thể overflow trong floorDiv thông thường.
- [ ] Nếu cần phát hiện overflow, chọn `floorDivExact` (Java 18+) hoặc check biên trên Java 17.
- [ ] Chọn overload `int/int`, `long/long` hoặc `long/int` đúng kiểu và phiên bản.
- [ ] Không dùng `Math.abs` để normalize mọi số nguyên không xét MIN_VALUE.
- [ ] Không ép `long` sang `double` để tính floor quotient chính xác.
- [ ] Nếu dùng modulus âm, hiểu phần dư floorMod có thể âm.
- [ ] Có test cả `(-,+)`, `(+,-)`, `(-,-)`, 0, chia hết và không chia hết.
- [ ] Nếu dùng bucket âm, hiểu bucket label có thể âm và offset bên trong bucket dương.
- [ ] Nếu dùng timestamp âm, phân biệt fixed-duration UTC buckets và civil timezone.
- [ ] Nếu dùng hash partition, có policy hash/stability/resize riêng.
- [ ] Nếu dùng BigInteger, xác định cần remainder kiểu truncating hay mod không âm.
- [ ] Nếu tính lại `q*y+r`, dùng kiểu rộng hơn hoặc BigInteger khi cần kiểm tra overflow.
- [ ] Tài liệu API chỉ dùng những method có trong JDK target thực tế.
- [ ] Không giả định thông điệp lỗi chia cho 0 là chuỗi cố định.
- [ ] Code review ghi rõ đơn vị đo và ý nghĩa của divisor.

## 29. Bài tập tự luyện

### Bài 1 — Bốn dấu

Tính `/`, `%`, `Math.floorDiv`, `Math.floorMod` cho các cặp `(11,4)`, `(-11,4)`, `(11,-4)`, `(-11,-4)`. Kiểm tra từng cặp bằng `x = q*y + r`.

### Bài 2 — Vòng 5 phần tử

Viết hàm `normalize(int index)` ánh xạ mọi số nguyên vào `0..4` với `Math.floorMod(index,5)`. Thử `-1`, `-5`, `-6`, `Integer.MIN_VALUE`.

### Bài 3 — Nhóm thành từng 10

Tạo các bucket rộng 10 trên trục số nguyên. Hỏi `-1`, `-10`, `-11`, `0`, `10` thuộc bucket nào? Offset trong bucket là bao nhiêu?

### Bài 4 — Mẫu số âm

Với `x=7` và `y=-3`, hãy giải thích vì sao `%` trả 1 còn `floorMod` trả -2. Vì sao không dùng floorMod với size=-3 để index mảng?

### Bài 5 — Chia hết

Nếu `x=-18,y=6`, hãy tính quotient và remainder theo cả hai chế độ. Vì sao kết quả trùng nhau?

### Bài 6 — Timestamp -1ms

Dùng `Math.floorDiv(-1L, 3_600_000L)` và `Math.floorMod(-1L, 3_600_000L)`. Giải thích ý nghĩa hour bucket và offset.

### Bài 7 — Biên MIN_VALUE

Dự đoán `Math.floorDiv(Integer.MIN_VALUE,-1)` và `Math.floorMod(Integer.MIN_VALUE,-1)`. Tại sao `floorDivExact` ném lỗi từ Java 18+?

### Bài 8 — Long precision

So sánh `Math.floorDiv(Long.MAX_VALUE,2)` với `(long)Math.floor((double)Long.MAX_VALUE/2)`. Giải thích hiện tượng sai khác.

### Bài 9 — BigInteger

Tính `BigInteger.valueOf(-7).remainder(BigInteger.valueOf(3))` và `.mod(...)`. Nếu modulus bằng -3 thì method mod xử lý thế nào?

### Bài 10 — Property tests

Viết test với x chạy từ -100 đến 100 và y từ -20 đến 20, bỏ y=0. Kiểm tra `q*y+r==x` trên long và khoảng dư theo dấu y.

### Bài 11 — Phân vùng theo hash

Với `partitionCount=5`, tính partition của các hash `-10,-6,-1,0,1,6`. Vì sao `Math.abs(hash)%5` là cách không tương đương?

### Bài 12 — API versions

Phân loại method nào có thể compile trên Java 8, 17, 18: `floorDiv(int,int)`, `floorMod(long,long)`, `floorMod(long,int)`, `floorDivExact(int,int)`, `ceilDiv(int,int)`.

## 30. Câu hỏi trắc nghiệm ngắn và đáp án

**1. `-7 / 3` trong Java int là bao nhiêu?** — `-2`, vì cắt về 0.

**2. `Math.floorDiv(-7,3)`?** — `-3`.

**3. `-7 % 3`?** — `-1`.

**4. `Math.floorMod(-7,3)`?** — `2`.

**5. `Math.floorDiv(7,-3)`?** — `-3`.

**6. `Math.floorMod(7,-3)`?** — `-2`.

**7. `Math.floorDiv(-7,-3)`?** — `2`.

**8. `Math.floorMod(-7,-3)`?** — `-1`.

**9. Khi nào `/` và floorDiv khác nhau?** — Khi hai toán hạng khác dấu và thương không nguyên, ngoài ngoại lệ overflow cần xét riêng.

**10. Khi nào `%` và floorMod khác nhau?** — Khi số dư khác 0 và hai toán hạng trái dấu.

**11. Dư của `%` mang dấu theo ai?** — Theo **số bị chia x** (nếu khác 0).

**12. Dư của floorMod mang dấu theo ai?** — Theo **số chia y** (nếu khác 0).

**13. floorMod với y>0 trả miền nào?** — `0 <= r < y`.

**14. floorMod với y<0 trả miền nào?** — `y < r <= 0`.

**15. floorMod có luôn không âm không?** — Không; chỉ bảo đảm điều đó với y dương.

**16. `Math.floorMod(-1,7)`?** — `6`.

**17. `Math.floorDiv(-1,7)`?** — `-1`.

**18. `Math.floorMod(-8,7)`?** — `6`.

**19. Có được dùng y=0?** — Không; ném ArithmeticException.

**20. `floorMod(x,-1)`?** — `0` với mọi x.

**21. `floorDiv(Integer.MIN_VALUE,-1)`?** — `Integer.MIN_VALUE` do overflow đặc biệt.

**22. `floorDivExact(Integer.MIN_VALUE,-1)`?** — Ném ArithmeticException trên Java 18+.

**23. `Math.abs(Integer.MIN_VALUE)` có dương không?** — Không; kết quả vẫn âm do overflow.

**24. API nào có từ Java 8?** — `Math.floorDiv(int,int)`, `Math.floorMod(int,int)`, các overload `(long,long)`.

**25. `Math.floorMod(long,int)` có từ Java nào?** — Java 9, trả int.

**26. `Math.floorDivExact` có từ Java nào?** — Java 18.

**27. Có nên ép long sang double để tính floor quotient exact không?** — Không, có thể mất precision.

**28. BigInteger.mod có chấp nhận modulus âm không?** — Không, yêu cầu dương.

**29. Trước Unix epoch 1ms thuộc hour bucket nào?** — `-1`, offset `3599999`ms trong ví dụ fixed-hour.

**30. `Math.floorMod` có tự xử lý timezone/DST không?** — Không; nó chỉ tính số học nguyên.

## 31. Tổng kết

**`Math.floorDiv` và `Math.floorMod` là những API Java 8 vẫn hiện hành, đặc biệt quan trọng khi số nguyên có thể âm.** Chúng giải quyết một nhóm lỗi phổ biến mà `/` và `%` không giải quyết theo semantics floor.

Các nguyên tắc cần nhớ:

1. **`/` cắt về 0**, `Math.floorDiv` làm tròn về **âm vô cực**.
2. **`%` mang dấu của số bị chia**, `Math.floorMod` mang dấu của **số chia** hoặc bằng 0.
3. Với **`y > 0`**, `Math.floorMod(x,y)` luôn nằm trong `0..y-1`, phù hợp cho circular index và partition.
4. Với **`y < 0`**, phần dư floor có thể âm; không dùng làm index mảng.
5. Cặp floorDiv/floorMod cho phép chia chính xác một giá trị thành **bucket** và **offset** kể cả với giá trị âm.
6. **Chia cho 0** ném ArithmeticException; validate số chia theo yêu cầu nghiệp vụ.
7. **`MIN_VALUE / -1`** là biên overflow đặc biệt: floorDiv thường trả MIN_VALUE; `floorDivExact` Java 18+ phát hiện và ném lỗi.
8. **Không dùng `Math.abs(x)%n`** để thay `floorMod(x,n)`; sai cả về ý nghĩa và biên MIN_VALUE.
9. **Không dùng Math.floor trên double để thay chia nguyên long**, vì có thể mất precision.
10. Dùng **java.time** cho ngày giờ/múi giờ thực tế; dùng floorDiv/floorMod cho bucket thời lượng cố định.
11. Với BigInteger, phân biệt **remainder** theo truncation và **mod** yêu cầu modulus dương.
12. Unit test phải có các trường hợp số âm, số chia âm, zero, chia hết, MIN_VALUE và overflow.

### Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — Math: floorDiv, floorMod, floorDivExact, ceilDiv và các overload](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html)
- [Oracle Java SE 26 — StrictMath: mô tả các phép floor division/modulo](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/StrictMath.html)
- [Oracle Java SE 26 — BigInteger: divide, remainder và mod](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigInteger.html)
- [Oracle Java SE 26 — Integer: MIN_VALUE/MAX_VALUE](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Integer.html)
- [Oracle Java SE 26 — Long: MIN_VALUE/MAX_VALUE](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Long.html)
- [Oracle Java SE 26 — Instant: Unix epoch và timestamp](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html)
- [Oracle Java SE 26 — ZonedDateTime và timezone rules](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html)
- [Java Language Specification, §15.17.2 và §15.17.3 — chia nguyên và remainder](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.17)
