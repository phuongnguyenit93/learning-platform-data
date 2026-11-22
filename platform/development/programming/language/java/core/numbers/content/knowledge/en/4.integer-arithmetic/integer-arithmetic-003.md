# Toán tử `%` và dấu của số dư trong Java

Trong Java, `%` là **toán tử lấy phần dư** (*remainder operator*). Với phép toán số nguyên, nó đi cùng phép chia `/` **làm tròn thương về 0** (*truncation toward zero*). Vì vậy, phần dư có thể **âm** khi số bị chia âm. Chẳng hạn:

```java
System.out.println(7 % 3);     //  1
System.out.println(-7 % 3);    // -1
System.out.println(7 % -3);    //  1
System.out.println(-7 % -3);   // -1
```

Các dòng này là mảnh mã minh họa đặt trong `main`. Điểm cần nhớ: với số nguyên Java, **phần dư khác 0 có cùng dấu với số bị chia (toán hạng bên trái)**, không nhất thiết cùng dấu với số chia bên phải. Nếu muốn kết quả **không âm** theo một chu kỳ có kích thước dương, thường nên dùng `Math.floorMod(x, modulus)`.

Bài học thuộc phần **Số học nguyên** của module **Java core – numbers**. Nội dung đi từ cơ chế `/` và `%` đến lỗi với số âm, cách dùng `Math.floorMod`, tình huống thực tế và kiểm thử biên.

## 1. Phần dư được xác định như thế nào?

Cho hai số nguyên `a` và `b` với `b != 0`. Trong phép toán số nguyên Java:

- `q = a / b`: thương nguyên được tính bằng phép chia **bỏ phần lẻ theo hướng 0**.
- `r = a % b`: phần dư đi kèm phép chia đó.
- Hệ thức toán học tương ứng là `a = q × b + r`. Trong code Java có độ rộng nguyên cố định, việc tự tính `q * b + r` còn phải xét tràn số ở biểu thức trung gian.

Ví dụ với hai số dương:

```text
7 / 3 = 2
7 % 3 = 1

7 = 2 × 3 + 1
```

Với số bị chia âm:

```text
-7 / 3 = -2      (cắt phần lẻ của -2,333... về 0)
-7 % 3 = -1

-7 = (-2) × 3 + (-1)
```

Nếu lấy thương bằng phép **làm tròn xuống** (*floor*), kết quả sẽ khác với phép chia nguyên Java khi thương toán học âm và không nguyên:

```text
floor(-7 / 3) = -3
-7 = (-3) × 3 + 2
```

Đó là lý do toán tử `%` và `Math.floorMod` có thể cho **hai kết quả khác nhau**.

### Quy tắc dấu chính xác

Với số nguyên và số chia khác 0:

1. Phần dư bằng 0 hoặc cùng dấu với **số bị chia**.
2. Giá trị tuyệt đối của phần dư **nhỏ hơn giá trị tuyệt đối của số chia** khi xét về mặt toán học.
3. Việc đổi dấu số chia **không làm đổi phần dư** nếu số bị chia giữ nguyên và cùng miền có thể biểu diễn.

Quy tắc thứ hai không yêu cầu gọi `Math.abs` trong code: `Math.abs(Integer.MIN_VALUE)` vẫn âm vì giá trị dương tương ứng không biểu diễn được trong `int`. Đây là lý do nên diễn đạt điều kiện về **độ lớn toán học**, không dùng công thức kiểm thử tùy tiện `Math.abs(r) < Math.abs(b)` cho mọi đầu vào.

## 2. Bảng bốn tổ hợp dấu bắt buộc phải hiểu

| Số bị chia `a` | Số chia `b` | `a / b` | `a % b` | Kiểm tra `a = q × b + r` |
| ---: | ---: | ---: | ---: | --- |
| `7` | `3` | `2` | `1` | `7 = 2 × 3 + 1` |
| `-7` | `3` | `-2` | `-1` | `-7 = -2 × 3 - 1` |
| `7` | `-3` | `-2` | `1` | `7 = (-2) × (-3) + 1` |
| `-7` | `-3` | `2` | `-1` | `-7 = 2 × (-3) - 1` |

Số chia âm **không kéo dấu phần dư về âm**. Hãy nhìn toán hạng bên trái: `7 % -3 == 1`; `-7 % -3 == -1`.

Với phép chia hết, phần dư bằng 0 bất kể dấu:

```java
12 % 3     // 0
-12 % 3    // 0
12 % -3    // 0
-12 % -3   // 0
```

Vì vậy, `n % d == 0` vẫn là phép kiểm tra chia hết hợp lệ cho số nguyên âm và số chia âm, miễn là `d != 0`.

## 3. Tại sao toán tử % không luôn trả kết quả dương?

Nhiều tài liệu toán học định nghĩa phép **modulo theo môđun dương** sao cho kết quả nằm trong `0, 1, ..., m-1` với `m > 0`. Quy ước ấy rất tiện cho toán học rời rạc và chỉ số vòng. Nhưng Java định nghĩa `%` cho số nguyên theo **phép chia cắt về 0**, do vậy:

```java
int remainder = -1 % 5;  // -1; KHÔNG phải 4
```

Trong toán học theo môđun 5, `-1` và `4` thuộc cùng lớp đồng dư. Tuy nhiên “đồng dư” là quan hệ toán học, còn `%` trong Java trả **một đại diện cụ thể** theo quy tắc phần dư. Muốn đại diện không âm khi môđun dương, hãy chọn `Math.floorMod`.

Hai khái niệm không nên trộn lẫn:

| Nhu cầu | Biểu thức Java | Kết quả với `-7` và `3` |
| --- | --- | --- |
| Phần dư của chia nguyên cắt về 0 | `-7 % 3` | `-1` |
| Phần dư theo phép chia làm tròn xuống | `Math.floorMod(-7, 3)` | `2` |
| Thương của chia nguyên cắt về 0 | `-7 / 3` | `-2` |
| Thương của chia nguyên làm tròn xuống | `Math.floorDiv(-7, 3)` | `-3` |

Không có phép nào “sai”; chúng trả lời **hai quy ước khác nhau**. Sai sót xảy ra khi thuật toán cần kết quả trong miền không âm nhưng người viết dùng `%` trên một số có thể âm.

## 4. Math.floorMod: lựa chọn cho chỉ số vòng và môđun dương

Java cung cấp `Math.floorMod(int x, int y)` và `Math.floorMod(long x, long y)`, cùng một số overload khác. Phương thức này kết hợp với `Math.floorDiv` theo phép chia **làm tròn xuống**, không cắt về 0:

```java
Math.floorDiv(-7, 3); // -3
Math.floorMod(-7, 3); //  2

Math.floorDiv(7, 3);  //  2
Math.floorMod(7, 3);  //  1
```

Với **môđun dương** `m > 0`, `Math.floorMod(x, m)` luôn trả một số nguyên trong phạm vi **từ 0 đến `m - 1`**, kể cả khi `x` âm.

| `x` | `m` | `x % m` | `Math.floorMod(x, m)` |
| ---: | ---: | ---: | ---: |
| `8` | `5` | `3` | `3` |
| `-1` | `5` | `-1` | `4` |
| `-8` | `5` | `-3` | `2` |
| `-10` | `5` | `0` | `0` |
| `-11` | `5` | `-1` | `4` |

**Lưu ý với số chia âm:** `Math.floorMod` **không cam kết trả số không âm** nếu `m` âm. Phần dư khác 0 theo floor division có cùng dấu với **số chia**. Ví dụ:

```java
7 % -3;                //  1
Math.floorMod(7, -3);  // -2
Math.floorDiv(7, -3);  // -3
```

Vì vậy, khi sử dụng `floorMod` để tạo chỉ số `0..n-1`, hãy **bảo đảm `n > 0`**. Với danh sách hoặc mảng rỗng, `n = 0` là lỗi thiết kế chỉ số, không phải trường hợp `floorMod` có thể xử lý.

### Tránh tự viết công thức chuẩn hóa thiếu an toàn

Một mẹo thường gặp là:

```java
int normalized = (x % m + m) % m;
```

Nếu `m > 0` và các phép toán diễn ra trong kiểu nguyên có độ rộng cố định, **biểu thức `x % m + m` có thể tràn** khi `x % m` đã dương. Ví dụ, với `x = 2_147_483_646` và `m = 2_147_483_647`, phép cộng trung gian `2_147_483_646 + 2_147_483_647` tràn `int`, làm kết quả có thể sai.

Dùng:

```java
int normalized = Math.floorMod(x, m);
```

Khi `m > 0`, cách này trực tiếp thể hiện quy tắc cần dùng và tránh phép cộng dễ tràn ở công thức tự chế.

## 5. Tình huống thực tế: chỉ số của bộ đệm vòng

Giả sử một bộ đệm vòng có `capacity = 5`, và thuật toán có bước lùi một vị trí từ index 0. Kết quả mong muốn là index 4.

Đoạn sau **sai** khi `currentIndex == 0`:

```java
int capacity = 5;
int currentIndex = 0;
int previousIndex = (currentIndex - 1) % capacity; // -1
// buffer[previousIndex] sẽ gây ArrayIndexOutOfBoundsException.
```

Sử dụng `Math.floorMod`:

```java
int capacity = 5;
int currentIndex = 0;
int previousIndex = Math.floorMod(currentIndex - 1, capacity); // 4
```

Quy tắc này hữu ích cho lịch tuần hoàn, vị trí quay vòng và số bước âm. Tuy nhiên có hai điều phải xét:

- **Kích thước phải dương:** `capacity > 0`. Không thể lấy phần dư với 0.
- **Biểu thức đầu vào cũng có thể tràn:** nếu `currentIndex` hoặc `offset` có thể rất lớn, phép `currentIndex + offset` có thể tràn **trước khi** gọi `floorMod`. Có thể chuyển phép cộng sang `long` trong phạm vi đảm bảo, hoặc thiết kế cách cộng môđun không làm tràn.

Ví dụ với `int` index, offset `int` và kích thước dương đã kiểm tra:

```java
static int wrappedIndex(int current, int offset, int capacity) {
    if (capacity <= 0) {
        throw new IllegalArgumentException("capacity must be positive");
    }
    long position = (long) current + offset;
    return (int) Math.floorMod(position, (long) capacity);
}
```

Đây là phương thức minh họa cần đặt trong một class. Vì tổng của hai `int` luôn nằm trong miền `long`, phép cộng ở đây không tràn. Phần dư nằm trong `0..capacity-1` nên việc cast kết quả về `int` an toàn. Nếu API định nghĩa `current` phải nằm trong `0..capacity-1`, vẫn nên xác thực riêng điều kiện đó.

## 6. Tình huống thực tế: tính chẵn lẻ và kiểm tra chia hết

Một phép kiểm tra phổ biến là:

```java
boolean isEven = value % 2 == 0;
boolean isOdd = value % 2 != 0;
```

Cả hai đúng đối với `int` âm và dương. **Đừng viết `value % 2 == 1` như cách kiểm tra số lẻ tổng quát:** `-3 % 2` bằng `-1`, nên `-3 % 2 == 1` là `false` dù `-3` là số lẻ.

Ví dụ:

| `value` | `value % 2` | `value % 2 != 0` |
| ---: | ---: | --- |
| `4` | `0` | `false` |
| `5` | `1` | `true` |
| `-4` | `0` | `false` |
| `-5` | `-1` | `true` |

Nếu hệ thống chỉ nhận số nguyên không âm, kiểm tra đầu vào trước là một lựa chọn hợp lý. Nhưng **phép kiểm tra số lẻ đúng cho mọi số nguyên** là `value % 2 != 0`, không cần loại trừ số âm chỉ để bảo vệ phép kiểm tra.

### Tách chữ số cuối của số nguyên âm

`-123 % 10` bằng `-3`, nên phép `value % 10` không tự cho một chữ số trong `0..9` nếu `value` có thể âm. Khi cần phần dư dương theo cơ số 10 để lập thuật toán số học môđun, `Math.floorMod(value, 10)` cho `7` đối với `-123`; **đó không phải chữ số 3 của trị tuyệt đối**.

Nếu mục tiêu là chữ số đơn vị của **độ lớn tuyệt đối**, phải nêu ý nghĩa đó và xử lý `Integer.MIN_VALUE` cẩn thận; đừng áp dụng `Math.abs(value)` vô điều kiện. Có thể nâng lên `long` trước rồi lấy độ lớn:

```java
int value = Integer.MIN_VALUE;
long magnitude = Math.abs((long) value);
long lastDigit = magnitude % 10; // 8
```

Cách tính đúng phải dựa trên câu hỏi “chữ số của trị tuyệt đối” hay “đại diện môđun không âm”.

## 7. Chia cho 0 và các giá trị biên

Với số nguyên, `a / 0` và `a % 0` đều gây `ArithmeticException` khi được đánh giá. Đừng dùng `%` như một phép kiểm tra an toàn nếu số chia lấy từ input chưa được xác thực.

```java
static boolean divisibleBy(int value, int divisor) {
    if (divisor == 0) {
        throw new IllegalArgumentException("divisor must not be zero");
    }
    return value % divisor == 0;
}
```

Phương thức trên xử lý số chia âm, số bị chia âm và cả trường hợp `Integer.MIN_VALUE % -1 == 0`.

### Trường hợp đặc biệt: Integer.MIN_VALUE / -1

Đây là ca biên quan trọng vì `Integer.MIN_VALUE = -2_147_483_648` và giá trị dương `2_147_483_648` không biểu diễn được bằng `int`.

```java
int x = Integer.MIN_VALUE;
int quotient = x / -1;  // Integer.MIN_VALUE, thương toán học bị tràn int
int remainder = x % -1; // 0
```

Quy tắc Java cho phép thương trong phép chia nguyên thường tràn ở trường hợp đặc biệt này, nhưng **phần dư vẫn bằng 0**. Đừng suy ra rằng mọi phép chia số nguyên sẽ ném ngoại lệ khi tràn. Nếu cần thương toán học chính xác, hãy mở rộng toán hạng trước khi chia:

```java
long quotient = (long) Integer.MIN_VALUE / -1; // 2147483648L
```

Khi tự kiểm tra hệ thức `a == (a / b) * b + a % b` trong code kiểu `int`, cần lưu ý tràn của phép nhân/thương. Hệ thức là công cụ lý giải về số học, nhưng biểu thức kiểm thử cũng phải được thiết kế phù hợp với phạm vi biểu diễn.

## 8. Kiểu của biểu thức % và quy tắc chuyển kiểu

Với các toán hạng nguyên thủy, toán tử `%` áp dụng **binary numeric promotion**:

- `byte`, `short` và `char` thường được nâng lên `int` trước khi tính.
- Nếu một toán hạng có kiểu `long`, biểu thức số nguyên thường được nâng lên `long`.
- Kết quả có kiểu sau promotion, không tự co về kiểu ban đầu của biến.

Ví dụ:

```java
byte small = -7;
int remainder = small % 3; // -1, kiểu biểu thức là int
// byte invalid = small % 3; // Không biên dịch: biểu thức int sang byte.
long large = -7L;
long longRemainder = large % 3; // -1L
```

Toán tử `%` cũng được Java định nghĩa với `float`/`double`, nhưng phần dư dấu phẩy động còn có các trường hợp `NaN`, vô cực và số 0 có dấu. **Bài học này tập trung vào phần dư số nguyên**; không lấy kết luận về lỗi chia cho 0 của integer áp lên `double` hoặc xem `%` floating point là cùng quy tắc xử lý ngoại lệ.

## 9. BigInteger: remainder và mod mang hai quy ước khác nhau

Khi số nguyên vượt phạm vi `long`, `java.math.BigInteger` cung cấp hai phương thức cần phân biệt:

- `remainder(divisor)`: phần dư theo cách chia cắt về 0, giống dấu của toán tử `%` với số nguyên âm.
- `mod(modulus)`: chọn đại diện môđun **không âm**, nhưng **yêu cầu modulus dương**; giá trị môđun 0 hoặc âm gây `ArithmeticException`.

```java
BigInteger negative = new BigInteger("-7");
BigInteger three = BigInteger.valueOf(3);

BigInteger remainder = negative.remainder(three); // -1
BigInteger modulo = negative.mod(three);          //  2
```

Đây là mảnh mã cần `import java.math.BigInteger;`. `BigInteger` bất biến và không dùng toán tử `%` trực tiếp giữa hai đối tượng `BigInteger`; hãy dùng phương thức. Với `BigInteger`, cũng kiểm tra rõ 0 ở tham số chia và giới hạn tài nguyên cho dữ liệu đầu vào lớn.

Sự phân biệt `BigInteger.remainder` so với `BigInteger.mod` cho thấy vì sao việc ghi rõ “phần dư” hay “modulo không âm” trong tài liệu API là quan trọng, đặc biệt khi chuyển thuật toán từ `int` sang kiểu số nguyên lớn.

## 10. Chương trình Java 17+ chạy độc lập

Lưu đoạn sau thành **`RemainderSignDemo.java`**. Chương trình in kết quả của bốn tổ hợp dấu, so sánh `%` với `Math.floorMod`, kiểm tra chẵn lẻ âm, minh họa chỉ số vòng, ca biên `Integer.MIN_VALUE` và `BigInteger`.

```java
import java.math.BigInteger;

public class RemainderSignDemo {
    public static void main(String[] args) {
        int[][] pairs = {
            {7, 3},
            {-7, 3},
            {7, -3},
            {-7, -3}
        };

        for (int[] pair : pairs) {
            int a = pair[0];
            int b = pair[1];
            System.out.printf(
                    "%d / %d = %d, %% = %d, floorDiv = %d, floorMod = %d%n",
                    a, b, a / b, a % b,
                    Math.floorDiv(a, b), Math.floorMod(a, b));
        }

        System.out.println("wrapped-index=" + Math.floorMod(-1, 5));
        System.out.println("odd-negative=" + (-5 % 2 != 0));
        System.out.println("negative-remainder=" + (-123 % 10));
        System.out.println("divisible-negative=" + (-12 % 3 == 0));
        System.out.println(
                "min-divisor-remainder=" + (Integer.MIN_VALUE % -1));

        BigInteger minusSeven = new BigInteger("-7");
        BigInteger three = BigInteger.valueOf(3);
        System.out.println(
                "big-remainder=" + minusSeven.remainder(three));
        System.out.println("big-mod=" + minusSeven.mod(three));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac RemainderSignDemo.java
java RemainderSignDemo
```

Stdout chính xác:

```text
7 / 3 = 2, % = 1, floorDiv = 2, floorMod = 1
-7 / 3 = -2, % = -1, floorDiv = -3, floorMod = 2
7 / -3 = -2, % = 1, floorDiv = -3, floorMod = -2
-7 / -3 = 2, % = -1, floorDiv = 2, floorMod = -1
wrapped-index=4
odd-negative=true
negative-remainder=-3
divisible-negative=true
min-divisor-remainder=0
big-remainder=-1
big-mod=2
```

Ở dòng thứ hai, `-7 / 3` cắt thương về 0 nên `-2` và phần dư `-1`; `floorDiv(-7,3)` là `-3` nên `floorMod` là `2`. Ở dòng thứ ba, số chia âm khiến `floorMod(7,-3)` là `-2`, chứng minh không thể giả định nó luôn không âm. Hai dòng cuối cho thấy `BigInteger.remainder` và `BigInteger.mod` đi theo hai quy ước khác nhau.

## 11. Sai lầm thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Nghĩ `a % b` luôn không âm | Dấu của phần dư số nguyên khác 0 theo dấu `a` | Dùng `Math.floorMod(a, b)` khi yêu cầu `b > 0` và miền `0..b-1` |
| Kiểm tra lẻ bằng `n % 2 == 1` | Số lẻ âm cho phần dư `-1` | Dùng `n % 2 != 0` |
| Dùng `(index - 1) % length` rồi truy cập mảng | Với index 0 tạo chỉ số `-1` | Kiểm tra `length > 0` rồi dùng `Math.floorMod` |
| Cộng `(x % m + m) % m` mặc định an toàn | Có thể tràn tại phép cộng | Dùng `Math.floorMod(x, m)` |
| Tưởng đổi dấu số chia sẽ đổi dấu phần dư | Với `%`, dấu phụ thuộc số bị chia | Lập bảng bốn tổ hợp dấu để kiểm tra |
| Gọi `Math.floorMod(x, negativeM)` rồi giả định không âm | Khi số chia âm, kết quả khác 0 cũng âm | Xác thực modulus dương trước khi dùng làm chỉ số |
| Bỏ qua số chia 0 | `%` nguyên với số chia 0 ném `ArithmeticException` | Validate divisor hoặc size trước phép toán |
| Dùng `Math.abs(x)` không kiểm tra biên | `Math.abs(Integer.MIN_VALUE)` vẫn âm | Nâng lên `long` trước khi lấy trị tuyệt đối khi cần |
| Mong `BigInteger.remainder` luôn dương | Phương thức trả phần dư theo phép chia cắt về 0 | Dùng `BigInteger.mod` với modulus dương |
| Thử nghiệm chỉ với số dương | Không phát hiện lỗi dấu của phần dư | Thêm số bị chia âm, số chia âm, số 0 và giá trị biên |

### Lưu ý về biến đổi công thức

Đối với `m > 0`, có thể chứng minh về mặt toán học rằng `x` và `Math.floorMod(x,m)` đồng dư môđun `m`. Tuy nhiên, khi tối ưu các biểu thức chứa `+`, `-` hoặc `*` trên `int`/`long`, vẫn phải xét tràn số **trước** bước lấy modulo. Không phải mọi đẳng thức số học nguyên vô hạn đều giữ nguyên ý nghĩa khi đánh giá với kiểu nguyên có độ rộng cố định.

Ví dụ, một thuật toán tính `(a + b) % m` trong `int` có thể sai nếu `a + b` đã tràn. `Math.floorMod(a + b, m)` cũng **không sửa được** giá trị trung gian bị tràn; cần nâng kiểu hoặc dùng thuật toán cộng môđun an toàn theo phạm vi đầu vào.

## 12. Câu hỏi và bài tập tự luyện

1. Không chạy Java, tính `11 % 4`, `-11 % 4`, `11 % -4`, `-11 % -4`. Với mỗi trường hợp hãy tính `/` và kiểm tra hệ thức chia lấy thương và dư.
2. Vì sao `-17 % 5` bằng `-2` nhưng `Math.floorMod(-17, 5)` bằng `3`? Hãy giải thích bằng sự khác nhau giữa “cắt về 0” và “làm tròn xuống”.
3. Một mảng độ dài 7 dùng chỉ số từ 0 đến 6. Viết hàm lấy phần tử trước và sau khi đang ở index 0 hoặc 6. Kiểm tra hành vi với offset âm và dương, đồng thời xử lý mảng rỗng.
4. Viết hàm `isOdd(int value)` đúng cho cả `Integer.MIN_VALUE`, số 0 và số âm. Tại sao `value % 2 == 1` chưa đạt?
5. So sánh kết quả `Math.floorMod(7, -3)` và `7 % -3`. Vì sao một thuật toán cần phần dư không âm nên quy định số chia dương?
6. Thiết kế kiểm thử cho parser nhận `divisor` từ JSON hoặc CLI, bảo đảm không bao giờ thực hiện `%` với 0. Bạn sẽ xử lý lỗi đầu vào dưới dạng ngoại lệ hay thông báo xác thực?
7. Với `BigInteger(-7)`, so sánh `remainder(3)`, `mod(3)` và thao tác `mod(-3)`. Phương thức nào yêu cầu modulus dương và vì sao?
8. Kiểm thử công thức `(x % m + m) % m` khi `x = 2_147_483_646`, `m = 2_147_483_647`. Tìm chỗ tràn và thay bằng một phép gọi `Math.floorMod`.

## 13. Ghi nhớ

- **`%` số nguyên Java là phần dư của chia cắt về 0**, vì thế nếu khác 0 nó có cùng dấu với **số bị chia**.
- **`-7 % 3 == -1`**, còn **`Math.floorMod(-7, 3) == 2`**. Chọn theo quy ước mà thuật toán cần.
- Dùng **`Math.floorMod(x, m)` với `m > 0`** khi muốn chỉ số vòng hoặc đại diện môđun trong `0..m-1`; kiểm tra `m` không phải 0.
- Để kiểm tra số lẻ cho mọi số nguyên, dùng **`n % 2 != 0`**; để kiểm tra chia hết, dùng **`n % d == 0`** sau khi bảo đảm `d != 0`.
- Phép modulo **không tự ngăn tràn** ở biểu thức đầu vào, và `Math.floorMod` với số chia âm không bảo đảm trả giá trị không âm.
- Với số nguyên tùy ý, `BigInteger.remainder` và `BigInteger.mod` thể hiện hai quy tắc khác nhau.

Hiểu đúng **dấu của phần dư** giúp tránh lỗi âm thầm trong tính chỉ số, xử lý chu kỳ và các thuật toán số nguyên. Hãy chọn phép toán theo yêu cầu của bài toán trước khi viết biểu thức.
