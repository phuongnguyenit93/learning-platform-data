# `floorDiv` và `floorMod` với toán hạng `long`, `int`

Từ Java 9, `java.lang.Math` có thêm các overload nhận một toán hạng `long` và một toán hạng `int`: `floorDiv(long, int)` và `floorMod(long, int)`. Chúng đặc biệt hữu ích khi tử số hoặc chỉ số là `long`, còn số chia là `int`, chẳng hạn chia số lượng lớn thành nhóm hoặc tính vị trí trong một mảng có kích thước kiểu `int`.

`floorDiv` thực hiện phép chia nguyên làm tròn xuống phía âm vô cùng (floor). `floorMod` trả về phần dư tương ứng với phép chia đó. Hai phương thức giúp xử lý đúng các trường hợp có số âm, nơi toán tử `/` và `%` của Java cho kết quả khác.

## 1. Khác biệt giữa phép chia nguyên thông thường và floor division

Với hai toán hạng nguyên, toán tử `/` của Java cắt phần thập phân về phía 0 (truncation toward zero). `Math.floorDiv` làm tròn thương xuống số nguyên nhỏ hơn hoặc bằng thương toán học.

Ví dụ với `-7` và `3`:

```java
System.out.println(-7 / 3);
System.out.println(Math.floorDiv(-7, 3));
```

Kết quả:

```text
-2
-3
```

`-7 / 3` cắt về 0 nên bằng `-2`; `floorDiv(-7, 3)` làm tròn xuống nên bằng `-3`. Khi thương là số nguyên chính xác, hai cách cho cùng kết quả. Khác biệt xuất hiện khi phép chia không hết và thương âm.

## 2. Các overload và kiểu trả về

`Math` cung cấp các overload sau:

| Phương thức | Kiểu trả về | Ghi chú |
| --- | --- | --- |
| `floorDiv(int x, int y)` | `int` | Phép chia floor với hai toán hạng `int`; có từ Java 8. |
| `floorDiv(long x, int y)` | `long` | Overload hỗn hợp được bổ sung từ Java 9. |
| `floorDiv(long x, long y)` | `long` | Phép chia floor với hai toán hạng `long`. |
| `floorMod(int x, int y)` | `int` | Phần dư floor với hai toán hạng `int`; có từ Java 8. |
| `floorMod(long x, int y)` | `int` | Overload hỗn hợp được bổ sung từ Java 9; phần dư luôn vừa kiểu `int`. |
| `floorMod(long x, long y)` | `long` | Phần dư floor với hai toán hạng `long`. |

Điểm cần nhớ là hai overload hỗn hợp không có cùng kiểu trả về: `floorDiv(long, int)` trả về `long`, còn `floorMod(long, int)` trả về `int`.

```java
long quotient = Math.floorDiv(-7L, 3);
int remainder = Math.floorMod(-7L, 3);
```

Không cần ép kiểu thủ công cho hai kết quả này. Kiểu trả về đã được xác định trong chữ ký của overload Java 9.

## 3. Quy tắc chọn overload

Java chọn overload dựa trên kiểu tĩnh của các đối số tại thời điểm biên dịch:

- `int, int` chọn `floorDiv(int, int)` hoặc `floorMod(int, int)`.
- `long, int` chọn overload hỗn hợp Java 9 `floorDiv(long, int)` hoặc `floorMod(long, int)`.
- `long, long` chọn overload nhận hai `long`.
- `int, long` không có overload chuyên biệt tương ứng; đối số `int` được mở rộng thành `long`, nên chọn overload `long, long`.

Ví dụ:

```java
int a = 7;
long b = 3L;

int r1 = Math.floorMod(a, 3);       // int, int -> int
long r2 = Math.floorMod(a, b);      // int, long -> long, long
int r3 = Math.floorMod(7L, 3);      // long, int -> int (Java 9+)
long r4 = Math.floorMod(7L, 3L);    // long, long -> long
```

Chữ `L` trong literal có ý nghĩa: `7` là `int`, còn `7L` là `long`. Overload được chọn theo kiểu đối số, không dựa trên giá trị số của chúng.

### Khác biệt với Java 8

Trước Java 9, khi gọi `Math.floorMod(longValue, intValue)`, đối số `int` được mở rộng thành `long` và overload `floorMod(long, long)` được dùng, nên kết quả có kiểu `long`. Java 9 bổ sung `floorMod(long, int)` trả về `int`, phù hợp với miền giá trị của phần dư theo số chia `int`.

Vì vậy, mã gán trực tiếp `Math.floorMod(longValue, intValue)` vào biến `int` cần API Java 9 trở lên. Nếu dự án còn biên dịch với Java 8, phải giữ kiểu kết quả `long` hoặc nâng mức API đích.

## 4. Ý nghĩa của `floorDiv`

`Math.floorDiv(x, y)` trả về thương nguyên được làm tròn xuống. Với `y` khác `0`, có thể hiểu là:

\[q = \lfloor x / y \rfloor\]

Ví dụ:

| `x` | `y` | `x / y` trong Java | `floorDiv(x, y)` |
| ---: | ---: | ---: | ---: |
| 7 | 3 | 2 | 2 |
| -7 | 3 | -2 | -3 |
| 7 | -3 | -2 | -3 |
| -7 | -3 | 2 | 2 |
| 6 | -3 | -2 | -2 |

Với số âm, cần chú ý chiều làm tròn. `floorDiv(7, -3)` là `-3` vì thương toán học xấp xỉ `-2,333...` và số nguyên floor của nó là `-3`.

## 5. Ý nghĩa của `floorMod`

`Math.floorMod(x, y)` trả về phần dư tương ứng với `floorDiv`. Với `y` khác `0`, trong các trường hợp thương biểu diễn được:

\[x = floorDiv(x, y) \times y + floorMod(x, y)\]

Phần dư có cùng dấu với số chia `y`, hoặc bằng `0`. Vì vậy:

- Nếu `y > 0`, phần dư nằm trong khoảng `0 <= r < y`.
- Nếu `y < 0`, phần dư nằm trong khoảng `y < r <= 0`.

Ví dụ:

| `x` | `y` | `x % y` trong Java | `floorMod(x, y)` |
| ---: | ---: | ---: | ---: |
| 7 | 3 | 1 | 1 |
| -7 | 3 | -1 | 2 |
| 7 | -3 | 1 | -2 |
| -7 | -3 | -1 | -1 |

Với `-7` và `3`, `floorDiv` trả `-3`, nên phần dư là `-7 - (-3 * 3) = 2`. Phần dư `2` có cùng dấu với số chia dương `3`.

### So sánh `%` và `floorMod`

Toán tử `%` tính phần dư dựa trên phép chia cắt về 0. Vì thế phần dư khác `0` có cùng dấu với số bị chia. `floorMod` dùng thương floor, nên phần dư khác `0` có cùng dấu với số chia.

```java
System.out.println(-7 % 3);
System.out.println(Math.floorMod(-7, 3));

System.out.println(7 % -3);
System.out.println(Math.floorMod(7, -3));
```

Kết quả:

```text
-1
2
1
-2
```

Không thay `%` bằng `floorMod` một cách máy móc nếu chương trình đang dựa vào quy tắc phần dư cũ. Hãy chọn phép toán theo quy ước dấu mà nghiệp vụ cần.

## 6. Vì sao overload `long, int` hữu ích?

Trong nhiều API, dữ liệu tích lũy hoặc vị trí có thể cần kiểu `long`, trong khi kích thước nhóm, số bucket hoặc độ dài mảng vẫn là `int`.

Ví dụ, một số thứ tự bản ghi rất lớn cần ánh xạ vào một bucket trong mảng có số bucket kiểu `int`:

```java
long recordNumber = -7L;
int bucketCount = 3;

long groupNumber = Math.floorDiv(recordNumber, bucketCount);
int bucketIndex = Math.floorMod(recordNumber, bucketCount);
```

`floorDiv(long, int)` giữ thương ở kiểu `long`, còn `floorMod(long, int)` trả trực tiếp chỉ số phần dư kiểu `int`. Khi `bucketCount` dương, `bucketIndex` luôn thuộc `[0, bucketCount)`.

Điều kiện quan trọng: `bucketCount` phải lớn hơn `0` nếu dùng kết quả như một chỉ số mảng. Nếu bằng `0`, phép chia ném `ArithmeticException`; nếu âm, phần dư có thể âm nên không phù hợp làm chỉ số mảng.

## 7. Ví dụ hoàn chỉnh chạy với Java 9 trở lên

Chương trình sau thể hiện kiểu trả về của các overload `int, int`, `long, int` và `long, long`; đồng thời kiểm tra số chia âm, chia cho 0 và trường hợp tràn đặc biệt.

```java
public class Main {
    public static void main(String[] args) {
        int intQuotient = Math.floorDiv(-7, 3);
        int intRemainder = Math.floorMod(-7, 3);
        System.out.printf("int,int: floorDiv=%d, floorMod=%d%n",
            intQuotient, intRemainder);

        long mixedQuotient = Math.floorDiv(-7L, 3);
        int mixedRemainder = Math.floorMod(-7L, 3);
        System.out.printf("long,int: floorDiv=%d, floorMod=%d%n",
            mixedQuotient, mixedRemainder);

        long longQuotient = Math.floorDiv(-7L, 3L);
        long longRemainder = Math.floorMod(-7L, 3L);
        System.out.printf("long,long: floorDiv=%d, floorMod=%d%n",
            longQuotient, longRemainder);

        long negativeDivisorQuotient = Math.floorDiv(7L, -3);
        int negativeDivisorRemainder = Math.floorMod(7L, -3);
        System.out.printf("long,int negative divisor: floorDiv=%d, floorMod=%d%n",
            negativeDivisorQuotient, negativeDivisorRemainder);

        try {
            Math.floorDiv(1L, 0);
        } catch (ArithmeticException ex) {
            System.out.println("zero divisor rejected");
        }

        System.out.println("int overflow quotient: "
            + Math.floorDiv(Integer.MIN_VALUE, -1));
        System.out.println("int overflow remainder: "
            + Math.floorMod(Integer.MIN_VALUE, -1));
    }
}
```

Lưu thành `Main.java`, sau đó biên dịch và chạy bằng JDK 9 trở lên:

```bash
javac --release 9 Main.java
java Main
```

Stdout chính xác:

```text
int,int: floorDiv=-3, floorMod=2
long,int: floorDiv=-3, floorMod=2
long,long: floorDiv=-3, floorMod=2
long,int negative divisor: floorDiv=-3, floorMod=-2
zero divisor rejected
int overflow quotient: -2147483648
int overflow remainder: 0
```

## 8. Chia cho 0 và trường hợp tràn số

Cả `floorDiv` và `floorMod` đều ném `ArithmeticException` khi số chia bằng `0`. Kiểm tra số chia trước nếu API của bạn cần trả về một lỗi nghiệp vụ khác.

Một trường hợp đặc biệt là giá trị nhỏ nhất chia cho `-1`: thương toán học vượt quá miền biểu diễn của kiểu số nguyên tương ứng.

```java
Math.floorDiv(Integer.MIN_VALUE, -1);
Math.floorMod(Integer.MIN_VALUE, -1);

Math.floorDiv(Long.MIN_VALUE, -1);
Math.floorMod(Long.MIN_VALUE, -1);
```

Do kết quả thương không biểu diễn được, `floorDiv` trả về giá trị nhỏ nhất của kiểu (`Integer.MIN_VALUE` hoặc `Long.MIN_VALUE`) theo hành vi tràn của phép chia nguyên Java. Phần dư tương ứng là `0`. Nếu miền nghiệp vụ không chấp nhận tình huống này, hãy kiểm tra riêng trước khi thực hiện phép chia.

Không nên suy luận rằng `floorDiv` phát hiện mọi trường hợp tràn và ném exception; hành vi của trường hợp nhỏ nhất chia `-1` là ngoại lệ đặc biệt được quy định cho phép chia nguyên.

## 9. Ứng dụng thực tế

### Chia dữ liệu thành các nhóm

Với một vị trí hoặc số thứ tự kiểu `long`, có thể tính nhóm theo kích thước nhóm kiểu `int`:

```java
long position = 1_000_000_005L;
int pageSize = 100;

long pageNumber = Math.floorDiv(position, pageSize);
int offset = Math.floorMod(position, pageSize);
```

Ví dụ này phù hợp khi `position` có thể âm theo quy ước dữ liệu. Nếu vị trí phải không âm, nên xác thực điều kiện đó theo hợp đồng API.

### Tính chỉ số vòng lặp

Để ánh xạ một số thứ tự `long` vào một mảng có kích thước dương `int`, `floorMod` giúp kết quả luôn không âm:

```java
long sequence = -7L;
int capacity = 5;
int slot = Math.floorMod(sequence, capacity);
```

Với `capacity > 0`, `slot` luôn nằm từ `0` đến `capacity - 1`, kể cả khi `sequence` âm. Cách này hữu ích cho vòng đệm (circular buffer), bucket hoặc vị trí quay vòng.

Không gọi phép tính này khi `capacity` bằng `0`; và không dùng capacity âm nếu kết quả được dùng làm chỉ số.

## 10. Lỗi thường gặp

1. **Dùng `/` khi cần làm tròn xuống.** Với thương âm không nguyên, `/` cắt về 0; dùng `Math.floorDiv` nếu hợp đồng yêu cầu floor.
2. **Dùng `%` khi cần phần dư cùng dấu với số chia.** `%` theo quy tắc chia cắt về 0; dùng `Math.floorMod` cho quy tắc floor.
3. **Nghĩ `floorMod(long, int)` trả về `long`.** Overload Java 9 này trả về `int`; còn `floorMod(long, long)` trả về `long`.
4. **Bỏ qua kiểu literal.** `7` là `int`, `7L` là `long`; kiểu đối số quyết định overload.
5. **Cho rằng có overload `(int, long)`.** Không có overload chuyên biệt này; `int` được mở rộng thành `long` và overload `(long, long)` được chọn.
6. **Giả định phần dư luôn không âm.** `floorMod` trả phần dư cùng dấu với số chia; nếu số chia âm, phần dư có thể âm.
7. **Không kiểm tra số chia bằng 0.** Cả hai phương thức đều ném `ArithmeticException` khi số chia bằng `0`.
8. **Bỏ qua `MIN_VALUE / -1`.** Thương không biểu diễn được và trả về giá trị MIN của kiểu; phần dư là `0`.
9. **Dùng `floorMod` với capacity không dương làm chỉ số mảng.** Hãy xác thực capacity lớn hơn `0` trước khi dùng kết quả làm chỉ số.
10. **Dùng `Math.floor(x / y)` với hai toán hạng nguyên.** Phép chia nguyên đã cắt về 0 trước khi `Math.floor` nhận kết quả; dùng trực tiếp `Math.floorDiv`.

## 11. Ghi nhớ

1. `floorDiv` làm tròn thương xuống phía âm vô cùng; `/` của Java cắt thương về 0.
2. `floorMod` là phần dư tương ứng với `floorDiv`; phần dư cùng dấu với số chia hoặc bằng `0`.
3. Java 9 bổ sung `floorDiv(long, int)` trả về `long` và `floorMod(long, int)` trả về `int`.
4. Overload được chọn theo kiểu tĩnh của đối số; `int, long` được mở rộng thành `long, long`.
5. Số chia bằng `0` gây `ArithmeticException`.
6. `MIN_VALUE` chia `-1` tạo thương tràn về `MIN_VALUE`, phần dư bằng `0`.
7. Với capacity dương kiểu `int`, `floorMod(longValue, capacity)` là cách hữu ích để tính chỉ số vòng lặp kiểu `int`.