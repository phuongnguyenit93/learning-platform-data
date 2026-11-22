# Chia số nguyên trong Java: Vì sao phần thập phân bị cắt về phía 0?

Khi **cả hai toán hạng của `/` đều là số nguyên**, Java thực hiện **phép chia số nguyên**. Kết quả là một số nguyên: phần phân số của thương toán học bị **loại bỏ theo hướng về 0** (*truncation toward zero*). Vì vậy:

- `7 / 3` → `2`, vì thương toán học là khoảng `2.333...`.
- `-7 / 3` → `-2`, vì thương toán học là khoảng `-2.333...`.
- `1 / 2` → `0`, không phải `0.5`.

Đây là quy tắc ngữ nghĩa của phép toán, **không phải lỗi thiếu độ chính xác hay lỗi làm tròn ngẫu nhiên**. Để tính thương có phần thập phân, phải làm cho **ít nhất một toán hạng** có kiểu số thực trước lúc thực hiện phép chia.

## 1. Phép `/` làm gì với các kiểu số nguyên?

Các kiểu tích phân nguyên thủy của Java gồm `byte`, `short`, `char`, `int` và `long`. Với biểu thức `a / b` mà cả hai đều thuộc nhóm số nguyên:

1. Java xác định kiểu tính toán bằng **binary numeric promotion**. `byte` và `short` được nâng lên ít nhất `int`. Nếu có một toán hạng `long` thì kết quả phép chia nguyên theo `long`.
2. Máy thực hiện phép chia số nguyên trên hai giá trị nguyên.
3. Thương toán học được **cắt phần phân số về 0**. Giá trị trả về có kiểu nguyên (`int` hoặc `long`); không có phần thập phân để giữ lại.

| Biểu thức | Thương toán học | Giá trị Java | Giải thích |
| --- | ---: | ---: | --- |
| `7 / 3` | `2.333...` | `2` | Bỏ phần sau dấu phẩy |
| `8 / 4` | `2` | `2` | Chia hết |
| `1 / 2` | `0.5` | `0` | Giá trị dương nhỏ hơn 1 bị cắt thành 0 |
| `-1 / 2` | `-0.5` | `0` | Phần phân số bị cắt về 0 |
| `-7 / 3` | `-2.333...` | `-2` | Hướng về 0, không xuống `-3` |
| `7 / -3` | `-2.333...` | `-2` | Thương âm bị cắt về 0 |
| `-7 / -3` | `2.333...` | `2` | Hai dấu âm cho thương dương |
| `10 / 2L` | `5` | `5L` | Có toán hạng `long` nên kiểu kết quả là `long` |

**Dấu của thương:** Nếu thương khác 0, hai toán hạng cùng dấu cho thương dương; trái dấu cho thương âm. Nếu độ lớn thương toán học nhỏ hơn 1, kết quả là `0`, Java không có hai giá trị `+0` và `-0` phân biệt đối với `int` hay `long`.

**“Cắt về 0” khác “làm tròn đến số gần nhất”:** `8 / 3` là `2` dù gần `3` hơn về số học; `-8 / 3` là `-2` dù thương toán học gần `-3` hơn. Phép `/` trên hai số nguyên **không thực hiện rounding-to-nearest**.

## 2. Vì sao `-7 / 3` là `-2` thay vì `-3`?

Có ba cách lấy một số nguyên từ `-2.333...`:

- **Truncation toward zero:** bỏ phần phân số theo hướng 0 → `-2`.
- **Floor (làm tròn xuống):** lấy số nguyên lớn nhất không vượt quá giá trị → `-3`.
- **Ceiling (làm tròn lên):** lấy số nguyên nhỏ nhất không nhỏ hơn giá trị → `-2`.

Với số dương `2.333...`, truncation và floor đều cho `2`, nên khác biệt thường chỉ lộ rõ khi kết quả âm.

Java dùng truncation đối với phép `/` số nguyên. Nếu cần phép chia theo **floor**, dùng `Math.floorDiv(a, b)`; ví dụ:

```java
int a = -7, b = 3;
int truncated = a / b;            // -2
int floored = Math.floorDiv(a, b); // -3
```

`Math.floorDiv` có các overload cho `int` và `long`. Hãy chọn quy tắc dựa trên nghiệp vụ: chia một khoản nợ, tính thứ tự các bucket có chỉ số âm và quy đổi khoảng thời gian âm có thể cần floor; tính thương nguyên thông thường có thể cần truncation. Không thay thế `/` bằng `Math.floorDiv` theo thói quen khi chưa xác định quy tắc làm tròn mong muốn.

## 3. Phép lấy dư `%` đi cùng với phép chia `/`

Trong phép chia nguyên, `%` lấy **số dư**, không phải phép toán “phần trăm”. Với số bị chia `a` và số chia `b != 0`, thương `q = a / b` và số dư `r = a % b` tuân theo quan hệ:

\[
a = q \times b + r
\]

cho các phép chia số nguyên thông thường. Java chọn `q` bằng cách cắt về 0, từ đó số dư `r` có các tính chất:

- `|r| < |b|` về mặt toán học khi `b != 0`.
- Nếu `r != 0`, **dấu của `r` giống dấu `a`** (số bị chia), không phụ thuộc vào dấu `b`.
- Nếu chia hết thì `r == 0`.

| `a` | `b` | `a / b` | `a % b` | Kiểm tra |
| ---: | ---: | ---: | ---: | --- |
| 7 | 3 | 2 | 1 | `7 = 2 * 3 + 1` |
| -7 | 3 | -2 | -1 | `-7 = (-2) * 3 - 1` |
| 7 | -3 | -2 | 1 | `7 = (-2) * (-3) + 1` |
| -7 | -3 | 2 | -1 | `-7 = 2 * (-3) - 1` |

Không nhầm `%` với modulo toán học luôn trả số không âm. Chẳng hạn `-7 % 3 == -1` trong Java, trong khi `Math.floorMod(-7, 3) == 2`. Với `b` dương, `Math.floorMod(a, b)` phù hợp khi cần chỉ số vòng lặp hoặc bucket nằm trong `0..b-1` kể cả lúc `a` âm.

**Ngoại lệ cần hiểu:** `Integer.MIN_VALUE / -1` và `Long.MIN_VALUE / -1L` không có thương toán học biểu diễn được trong chính kiểu đích. Java cho kết quả tràn số, xem mục 7; không được suy diễn mọi quy tắc miền của thương toán học sang trường hợp này mà không xét giới hạn kiểu.

## 4. Muốn có kết quả thập phân thì phải thay kiểu trước phép chia

Viết `double result = 1 / 2;` vẫn cho **`0.0`**, vì Java tính biểu thức `1 / 2` theo `int` trước khi chuyển kết quả sang `double`. Cần dùng literal dấu phẩy động hoặc ép toán hạng:

```java
double wrong = 1 / 2;          // 0.0: đã chia nguyên trước
double correctA = 1.0 / 2;     // 0.5: 1.0 là double
double correctB = (double) 1 / 2; // 0.5: đổi trước phép chia
double correctC = 1 / 2.0;     // 0.5: 2.0 là double
double tooLate = (double) (1 / 2); // 0.0: cast sau phép chia
```

Khi một toán hạng là `double`, phép chia số thực có thể tạo phần thập phân; nhưng `double` có độ chính xác nhị phân hữu hạn nên **không biểu diễn chính xác mọi phân số thập phân**. Câu “muốn kết quả có phần thập phân” khác với “muốn kết quả số thập phân chính xác tuyệt đối”. Với tiền tệ hoặc quy tắc làm tròn thập phân, cân nhắc `BigDecimal` và chính sách `RoundingMode` cụ thể.

Cẩn trọng khi ép `long` cực lớn sang `double`: giá trị nguyên có thể bị làm tròn vì phần trị `double` chỉ giữ 53 bit độ chính xác hiệu dụng. Nếu bài toán đòi thương nguyên và số dư chính xác của số cực lớn, không dùng chuyển sang `double` để giải quyết.

## 5. Kiểu kết quả, biểu thức và thứ tự phép tính

### `byte`, `short` vẫn chia theo `int`

```java
byte numerator = 7, denominator = 3;
int q = numerator / denominator;  // Đúng, q = 2
// byte invalid = numerator / denominator; // Lỗi biên dịch: kết quả là int
```

Các toán hạng `byte`/`short` được nâng thành `int`. Còn `long / int` cho kết quả kiểu `long`, nhưng **vẫn cắt về 0**:

```java
long q = 10_000_000_000L / 3;  // 3_333_333_333L
```

`long` chỉ mở rộng **miền giá trị**, không tự biến phép chia nguyên thành phép chia có phần thập phân.

### Các toán tử `*`, `/`, `%` cùng mức ưu tiên

Chúng kết hợp từ trái sang phải. Vì phép chia nguyên đã mất phần phân số nên thay đổi vị trí ngoặc có thể thay đổi kết quả:

```java
int a = 20 / 3 * 3;   // (20 / 3) * 3 = 6 * 3 = 18
int b = 20 * 3 / 3;   // (20 * 3) / 3 = 60 / 3 = 20
```

Ví dụ `b` hợp lệ vì `20 * 3` không vượt `int`. Với toán hạng lớn, **nhân trước chia** có thể overflow, nên không thể tự ý đổi công thức để “giữ độ chính xác” nếu chưa kiểm tra miền trung gian.

Trong ví dụ trung bình:

```java
int sum = 7, count = 2;
int averageTruncated = sum / count;      // 3
double averageDecimal = (double) sum / count; // 3.5
```

Xác định đầu ra mong muốn là thương nguyên hay giá trị thập phân trước khi chọn biểu thức.

## 6. Ví dụ chạy độc lập trên Java 17+

Lưu chương trình sau vào `IntegerDivisionDemo.java`:

```java
public class IntegerDivisionDemo {
    public static void main(String[] args) {
        System.out.println("7 / 3 = " + (7 / 3) + ", 7 % 3 = " + (7 % 3));
        System.out.println("-7 / 3 = " + (-7 / 3) + ", -7 % 3 = " + (-7 % 3));
        System.out.println("7 / -3 = " + (7 / -3) + ", 7 % -3 = " + (7 % -3));
        System.out.println("-7 / -3 = " + (-7 / -3) + ", -7 % -3 = " + (-7 % -3));

        System.out.println("1 / 2 = " + (1 / 2));
        System.out.println("double division = " + ((double) 1 / 2));
        System.out.println("cast after division = " + ((double) (1 / 2)));

        byte a = 7, b = 3;
        int quotient = a / b;
        System.out.println("byte division result = " + quotient);

        System.out.println("floorDiv(-7, 3) = " + Math.floorDiv(-7, 3));
        System.out.println("floorMod(-7, 3) = " + Math.floorMod(-7, 3));
        System.out.println("MIN / -1 = " + (Integer.MIN_VALUE / -1));
        System.out.println("MIN % -1 = " + (Integer.MIN_VALUE % -1));

        int zero = 0;
        try {
            System.out.println(7 / zero);
        } catch (ArithmeticException e) {
            System.out.println("integer division by zero: ArithmeticException");
        }
        System.out.println("long division = " + (10_000_000_000L / 3));
    }
}
```

Dùng JDK 17 trở lên để biên dịch và chạy:

```bash
javac IntegerDivisionDemo.java
java IntegerDivisionDemo
```

Stdout:

```text
7 / 3 = 2, 7 % 3 = 1
-7 / 3 = -2, -7 % 3 = -1
7 / -3 = -2, 7 % -3 = 1
-7 / -3 = 2, -7 % -3 = -1
1 / 2 = 0
double division = 0.5
cast after division = 0.0
byte division result = 2
floorDiv(-7, 3) = -3
floorMod(-7, 3) = 2
MIN / -1 = -2147483648
MIN % -1 = 0
integer division by zero: ArithmeticException
long division = 3333333333
```

**Điểm quan sát chính:** `/` và `%` nhất quán với dấu của toán hạng; cast **trước** phép chia khác cast **sau** phép chia; `Math.floorDiv`/`Math.floorMod` cho kết quả khác khi chia số âm; trường hợp `MIN_VALUE / -1` bị overflow; mẫu số bằng 0 ném ngoại lệ.

## 7. Hai trường hợp biên cần kiểm soát

### Chia nguyên cho 0

`int` và `long` không có giá trị infinity/NaN như các kiểu dấu phẩy động. Do đó `a / 0` hoặc `a % 0` ở thời điểm thực hiện phép toán gây **`ArithmeticException`**. Ví dụ:

```java
int divisor = 0;
int value = 5;
try {
    int result = value / divisor;
} catch (ArithmeticException ex) {
    System.out.println("Cannot divide integers by zero");
}
```

Khi nhận mẫu số từ đầu vào, **kiểm tra `divisor != 0` trước phép chia** rồi thông báo dữ liệu không hợp lệ hoặc xử lý theo quy định ứng dụng. Một giá trị mẫu số sai không nên bị thay ngầm thành 1 nếu nghiệp vụ không cho phép.

### `MIN_VALUE / -1`: thương không chứa được trong kiểu

`int` có miền `-2_147_483_648` đến `2_147_483_647`. Trị tuyệt đối toán học của `Integer.MIN_VALUE` là `2_147_483_648`, **vượt miền int**. Khi chia cho -1:

```java
int value = Integer.MIN_VALUE;
int q = value / -1; // -2147483648, do overflow số nguyên
int r = value % -1; // 0
```

Tương tự `Long.MIN_VALUE / -1L` trả về `Long.MIN_VALUE`. Đây là trường hợp đặc biệt **không ném ngoại lệ tự động**. Quy tắc cắt về 0 vẫn là ý tưởng xác định thương, nhưng **miền kiểu nguyên có giới hạn** khiến kết quả được biểu diễn theo quy tắc overflow.

Nếu không muốn chấp nhận tràn:

```java
int dividend = Integer.MIN_VALUE;
int divisor = -1;
if (divisor == -1 && dividend == Integer.MIN_VALUE) {
    throw new ArithmeticException("integer quotient overflows int");
}
int quotient = dividend / divisor;
```

Đoạn trên minh họa một nhánh guard, **không phải chương trình độc lập**. Khi dùng trong phương thức thật, kiểm tra mẫu số bằng 0 và giữ cách xử lý ngoại lệ thống nhất.

Một cách khác khi phép chia `int` có thể cần kết quả lớn hơn miền `int`: **chuyển số bị chia lên `long` trước phép chia**, ví dụ `(long) Integer.MIN_VALUE / -1 == 2_147_483_648L`. Với trường hợp `long` lớn hơn miền, cần `BigInteger` khi thật sự đòi kết quả nguyên chính xác.

## 8. Dùng `/` trong ứng dụng mà không làm sai nghiệp vụ

**Ví dụ 1: chia nhóm cố định.** Có 11 người, mỗi nhóm chứa tối đa 4 người; `11 / 4 == 2` là **hai nhóm đầy đủ**, còn `11 % 4 == 3` người dư. Nếu hỏi tổng nhóm cần chuẩn bị thì cần **3 nhóm**.

Với `total >= 0` và `size > 0`, cách tính tránh overflow trung gian của biểu thức `(total + size - 1) / size` là:

```java
int total = 11;
int size = 4;
int groups = total / size + (total % size == 0 ? 0 : 1); // 3
```

Công thức này chỉ áp dụng theo giả thiết tổng và kích thước không âm/dương như đã nêu; nếu dữ liệu âm, phải xác định lại ý nghĩa làm tròn và có thể dùng `Math.floorDiv` hoặc quy tắc nghiệp vụ khác.

**Ví dụ 2: tỷ lệ và phần trăm.** Nếu `completed = 1` và `total = 4`, biểu thức `completed / total * 100` cho **0**, vì `1 / 4` được cắt về 0 trước khi nhân. Nếu chỉ cần phần trăm nguyên và dữ liệu nằm trong miền phù hợp, có thể tính `(long) completed * 100 / total` để tránh tràn `int` trung gian rồi chủ động xử lý việc cắt phần lẻ. Nếu cần tỷ lệ thập phân, dùng `100.0 * completed / total` hoặc loại số thập phân có quy tắc làm tròn đáp ứng nghiệp vụ.

**Ví dụ 3: phân loại theo chỉ số âm.** Khi muốn gom các thời điểm hoặc tọa độ âm theo ô có độ rộng dương, `a / width` có thể đưa `-1` vào ô 0 vì cắt về 0. `Math.floorDiv(-1, width)` đưa nó vào ô -1 khi `width > 1`, phù hợp với cách chia trục số thành các khoảng theo floor.

Điều chung của ba ví dụ: trước khi chọn biểu thức, phải xác định yêu cầu là **thương nguyên cắt về 0**, **làm tròn xuống**, **làm tròn lên**, **thương số thực**, hay **phân nhóm có số dư**.

## 9. Sai lầm thường gặp

1. **“Biến nhận là `double` thì `1 / 2` sẽ ra `0.5`.”** Sai: Java tính `1 / 2` thành `int` bằng 0 rồi mới gán thành `0.0`.
2. **“`(double) (a / b)` khôi phục phần phân số.”** Sai: phép chia nguyên đã mất phần lẻ; cần `(double) a / b`.
3. **“Phép chia nguyên luôn làm tròn xuống.”** Sai với thương âm không nguyên: `-7 / 3 == -2`, còn `Math.floorDiv(-7,3) == -3`.
4. **“Số dư luôn không âm.”** Sai: `-7 % 3 == -1`. Nếu cần số dư không âm với mẫu số dương, cân nhắc `Math.floorMod`.
5. **“Dùng `long` sẽ giữ phần thập phân.”** Sai: `10L / 4` vẫn bằng `2L`; `long` chỉ mở rộng miền.
6. **“`byte / byte` trả về `byte`.”** Sai: các toán hạng được nâng lên `int`, kiểu biểu thức là `int`.
7. **“Đảo thứ tự nhân và chia không thay đổi kết quả.”** Sai khi phép chia nguyên cắt phần lẻ; và nhân trước có thể overflow.
8. **“Chia số nguyên cho 0 trả infinity.”** Sai: nó ném `ArithmeticException`, khác phép chia dấu phẩy động.
9. **“Chia `Integer.MIN_VALUE` cho -1 luôn báo lỗi tràn.”** Sai: kết quả là `Integer.MIN_VALUE` do overflow có quy tắc.
10. **“`a / b` tự cho số nguyên gần thương thật nhất.”** Sai: Java chọn hướng về 0. Nếu cần làm tròn theo miền nghiệp vụ, phải thể hiện quy tắc đó rõ ràng.

## 10. Tự kiểm tra

1. **`9 / 4` và `-9 / 4` cho bao nhiêu?** → `2` và `-2`, vì cắt phần phân số về 0.
2. **`9 % 4` và `-9 % 4` cho bao nhiêu?** → `1` và `-1`, số dư khác 0 theo dấu số bị chia.
3. **`double ratio = 3 / 2;` lưu giá trị nào?** → `1.0`. Muốn `1.5`, viết `double ratio = 3.0 / 2;`.
4. **Tại sao `Math.floorDiv(-9,4) == -3`?** → Floor lấy số nguyên lớn nhất không vượt quá `-2.25`, tức -3.
5. **`byte a = 8, b = 3;` thì biểu thức `a / b` thuộc kiểu nào?** → `int`.
6. **Nếu có 13 vật phẩm, mỗi thùng chứa 5, cần bao nhiêu thùng?** → `13 / 5 = 2` thùng đầy và còn `13 % 5 = 3`, nên cần **3** thùng nếu tất cả phải được chứa.

**Ghi nhớ:** `/` giữa hai toán hạng số nguyên cho **thương nguyên cắt về 0**. Hãy phân biệt quy tắc này với *floor* và *rounding to nearest*; nếu cần giá trị có phần thập phân, chuyển ít nhất một toán hạng sang loại số thích hợp **trước phép chia**. Dùng `%` để xử lý số dư, và kiểm tra mẫu số, miền kết quả cùng trường hợp `MIN_VALUE / -1` khi cần tính toán an toàn.
