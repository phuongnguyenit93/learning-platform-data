# Kiểu của phép tính được xác định trước khi gán kết quả trong Java

## 1. Quy tắc quan trọng nhất

Trong Java, **kiểu của biểu thức và phép toán được xác định theo các toán hạng và quy tắc ngôn ngữ trước khi kết quả được gán cho biến đích**. Một biến đích có kiểu rộng hơn không thể làm phép tính đã xảy ra ở kiểu hẹp trở nên chính xác trở lại.

Ví dụ:

```java
int a = 50_000;
int b = 50_000;

long wrong = a * b;          // -1794967296, phép nhân được thực hiện bằng int.
long correct = (long) a * b; // 2500000000, phép nhân được thực hiện bằng long.
```

Về toán học, `50_000 × 50_000 = 2_500_000_000`. Giá trị này vượt `Integer.MAX_VALUE = 2_147_483_647` nhưng nằm trong miền `long`. Với `wrong`, phép nhân giữa **hai biến `int`** tạo ra kết quả `int` bị tràn rồi kết quả đó mới được chuyển sang `long` để gán. Với `correct`, một toán hạng được chuyển sang `long` **trước** khi nhân nên toàn bộ phép nhân dùng `long`.

Đừng nhầm hai câu hỏi:

1. **Phép toán diễn ra bằng kiểu nào?** Phụ thuộc kiểu của các toán hạng, toán tử và các quy tắc *numeric promotion*.
2. **Kết quả được lưu vào biến kiểu nào?** Phụ thuộc kiểu biến nhận và quy tắc chuyển đổi trong ngữ cảnh gán.

Kiểu của biến nhận chỉ được xét sau khi biểu thức bên phải có kết quả; nó **không mặc nhiên truyền ngược vào phép toán nhị phân đã được định kiểu**.

## 2. Từng bước Java đánh giá một phép gán số

Xét:

```java
int x = 50_000;
int y = 50_000;
long result = x * y;
```

Có thể hiểu tuần tự:

1. Trình biên dịch thấy `x` và `y` đều có kiểu `int`.
2. Toán tử `*` áp dụng *binary numeric promotion*: hai toán hạng vẫn là `int`, nên **kiểu biểu thức `x * y` là `int`**.
3. Khi thực thi, phép nhân `int` vượt giới hạn và giữ kết quả theo số học nguyên 32 bit của Java: `-1_794_967_296`.
4. Khi gán cho `result`, Java thực hiện chuyển đổi mở rộng `int → long`, giữ nguyên giá trị âm đã có.
5. Giá trị cuối cùng của `result` là `-1_794_967_296L`.

Với biểu thức `(long) x * y`, toán hạng trái được chuyển sang `long` ngay từ đầu. *Binary numeric promotion* chuyển toán hạng `y` sang `long`, do đó biểu thức nhân có kiểu `long` và nhận đúng `2_500_000_000L`.

**Điều chỉnh kiểu phải xảy ra trước phép toán có nguy cơ mất dữ liệu.**

## 3. Binary numeric promotion: quy tắc chọn kiểu cho phép toán

Các toán tử số nhị phân như `+`, `-`, `*`, `/`, `%` áp dụng quy tắc *binary numeric promotion*. Với toán hạng thuộc các kiểu số nguyên và số thực nguyên thủy, có thể đọc theo thứ tự ưu tiên:

| Kiểu xuất hiện trong hai toán hạng | Kiểu thường dùng để thực hiện phép toán |
| --- | --- |
| Có `double` | `double` |
| Không có `double`, có `float` | `float` |
| Không có `double`/`float`, có `long` | `long` |
| Còn lại: `byte`, `short`, `char`, `int` | `int` |

Ví dụ:

```java
byte small = 10;
short other = 20;
int sum = small + other;  // int, vì byte và short được nâng lên int.

int units = 7;
long multiplier = 3L;
long product = units * multiplier; // long.

float f = 1.5F;
int n = 2;
float floatingResult = f * n; // float.

double d = 1.25;
float another = 2.0F;
double wideFloating = d + another; // double.
```

**Hai chi tiết cần nhớ:**

- `char` cũng thuộc nhóm *integral* và được nâng lên `int` khi tham gia phần lớn phép số học thông thường, dù giá trị của nó không dấu.
- `boolean` không phải kiểu số, không tham gia *numeric promotion*. Phép `"total=" + 42` là **nối chuỗi** bằng `+`, là ngữ nghĩa khác với cộng hai số.

Bảng này mô tả phép toán số học thường gặp. Không nên áp dụng máy móc cho mọi toán tử: phép dịch bit `<<`, `>>`, `>>>` dùng **unary numeric promotion** cho từng toán hạng, và kiểu kết quả phụ thuộc kiểu đã nâng của toán hạng **bên trái**; phép so sánh số trả về `boolean`; toán tử điều kiện `?:` có những quy tắc định kiểu riêng. Điểm chung là từng biểu thức phải được phân tích theo toán tử của chính nó, thay vì dựa vào kiểu biến nhận cuối cùng.

## 4. Tràn số xảy ra trước khi mở rộng kiểu của kết quả

### 4.1. Phép cộng `int` vào `long`

```java
int max = Integer.MAX_VALUE;

long tooLate = max + 1;        // -2147483648
long onTime = (long) max + 1;  // 2147483648
long withLongLiteral = max + 1L; // 2147483648
```

Bên phải `max + 1` là phép cộng `int + int`; nó tràn tại `2_147_483_647 + 1`. Sau đó, chuyển sang `long` chỉ giữ lại giá trị âm đã tràn. Thêm `(long)` **vào toán hạng** hoặc dùng `1L` làm phép cộng diễn ra ở `long` ngay từ đầu.

### 4.2. Phép nhân với cast đặt sai vị trí

So sánh:

```java
int width = 50_000;
int height = 50_000;

long a = (long) (width * height); // Sai mục đích: int nhân trước, rồi cast.
long b = ((long) width) * height; // Đúng: long nhân từ đầu.
```

Dấu ngoặc trong `(long) (width * height)` khiến phép nhân diễn ra trước khi cast. Muốn tăng miền của phép toán, cần cast **một toán hạng**, không phải chỉ cast **kết quả biểu thức đã tính**.

### 4.3. Nâng lên `long` vẫn có giới hạn

Nếu kết quả thực sự vượt miền `long`, chỉ dùng `long` vẫn có thể tràn:

```java
long max = Long.MAX_VALUE;
long overflowed = max + 1L; // Long.MIN_VALUE.
```

Đừng dùng `double` như một bản thay thế mặc định cho số nguyên lớn cần tính chính xác: dù miền độ lớn của `double` lớn hơn `long`, nó có độ chính xác hữu hạn và có thể làm tròn các số nguyên lớn. Khi cần nguyên chính xác vượt 64 bit, dùng `BigInteger` và **chuyển từng toán hạng trước khi thực hiện phép tính lớn**.

## 5. Kiểu biểu thức còn quyết định phép chia nguyên và mất phần thập phân

Không chỉ tràn số: cùng nguyên tắc đánh giá trước khi gán còn gây ra kết quả khác khi chia.

```java
int numerator = 1;
int denominator = 2;

double wrong = numerator / denominator;           // 0.0
double correct = (double) numerator / denominator; // 0.5
double alsoCorrect = numerator / 2.0;             // 0.5
```

Trong `numerator / denominator`, cả hai toán hạng là `int`, nên Java **chia nguyên**, bỏ phần lẻ và nhận `0`; rồi mới mở rộng giá trị đó thành `0.0` khi gán cho `double`.

Với `(double) numerator / denominator`, phép chia đã chuyển sang kiểu `double` trước khi thực hiện nên kết quả là `0.5`. Điều này khác hẳn việc dùng `(double) (numerator / denominator)`, vì cast sau phép chia chỉ biến `0` thành `0.0`.

Tương tự, nếu bạn viết `float result = 1 / 2;`, kết quả là `0.0F`, không phải `0.5F`.

**Lưu ý:** phép chia số nguyên có mẫu bằng 0 gây `ArithmeticException`. Gán kết quả vào `double` không thể đổi ngoại lệ đã xảy ra trong phép chia `int / int` thành `Infinity`.

## 6. Các kiểu hẹp được nâng lên `int` dù biến nhận là `byte` hoặc `short`

Nhiều người nghĩ phép cộng hai `byte` tạo ra `byte`. Thực tế, khi dùng toán tử cộng thông thường, Java nâng chúng lên `int`:

```java
byte x = 10;
byte y = 20;
int sum = x + y; // Đúng: kiểu biểu thức là int.

// byte invalid = x + y; // Lỗi biên dịch: int không tự thu hẹp thành byte.
byte narrowed = (byte) (x + y); // Ép kiểu tường minh.
```

Cast có thể mất dữ liệu khi giá trị vượt miền `byte` ([-128, 127]):

```java
byte x = 100;
byte y = 30;
int exact = x + y;             // 130
byte narrowed = (byte) (x + y); // -126
```

Giá trị `130` không nằm trong miền `byte`; ép kiểu về `byte` giữ các bit thấp và diễn giải kết quả có dấu thành `-126`. Lưu kết quả vào `int` giữ được đúng `130`.

### Ngoại lệ: gán một biểu thức hằng khi biên dịch

Java cho phép một số phép gán từ **biểu thức hằng** kiểu `int` (và trong trường hợp quy định, kiểu hằng khác) sang `byte`/`short`/`char` mà không cần cast nếu giá trị hằng biểu diễn được trong kiểu đích:

```java
byte a = 10 + 20;      // Hợp lệ: biểu thức hằng int có giá trị 30.
byte b = 127;          // Hợp lệ: giá trị hằng trong miền byte.
// byte c = 100 + 30; // Lỗi: giá trị hằng 130 vượt miền byte.

int external = 20;
// byte d = 10 + external; // Lỗi: kết quả int, không phải biểu thức hằng.
```

Đây là **quy tắc chuyển đổi gán cho biểu thức hằng nằm trong miền**, không có nghĩa phép cộng `byte` bỗng được thực hiện bằng `byte`. Khi các toán hạng là biến thông thường và kết quả phụ thuộc runtime, đừng dựa vào ngoại lệ này.

## 7. Toán tử gán ghép và tăng/giảm: trường hợp cần đặc biệt chú ý

Các toán tử `+=`, `-=`, `*=`, `/=` và `%=` có quy tắc riêng, gồm **chuyển kiểu ngầm về kiểu bên trái**. Chẳng hạn `E1 += E2` về cơ bản tương đương với `E1 = (T) ((E1) + (E2))`, với `T` là kiểu của `E1`; tuy nhiên `E1` chỉ được đánh giá một lần.

```java
byte count = 100;

// count = count + 30; // Lỗi biên dịch: kết quả count + 30 là int.
count += 30;           // Hợp lệ: cộng dạng int, rồi ép hẹp lại byte.
System.out.println(count); // -126
```

Do đó, `count += 30` **không an toàn hơn** `count = (byte) (count + 30)` về mặt mất dữ liệu. Cú pháp ngắn hơn có thể che việc ép kiểu hẹp diễn ra âm thầm.

Các toán tử `++`, `--` cũng có quy tắc kiểu riêng và có thể áp dụng trên biến `byte`/`short`/`char`. Ví dụ, khi `byte value = 127; value++;`, biến `value` trở thành `-128` do vượt giới hạn. Đừng suy từ việc `value++` biên dịch được rằng `byte next = value + 1;` cũng phải biên dịch được.

## 8. Biểu thức con và thứ tự tính: một cast không cứu được toàn bộ biểu thức

Java định kiểu và đánh giá các biểu thức con theo cấu trúc cú pháp. Nếu một biểu thức con đã bị tràn ở `int`, chuyển một biểu thức *khác* sang `long` về sau không hồi phục dữ liệu.

```java
int a = 50_000, b = 50_000;
long factor = 2L;

long wrong = (a * b) * factor; // -3589934592
long correct = ((long) a * b) * factor; // 5000000000
```

Trong `(a * b) * factor`, `a * b` đã cho `-1_794_967_296` ở kiểu `int`. Khi nhân tiếp với `factor`, Java mới chuyển kết quả âm này sang `long`. Trong `correct`, phép nhân đầu dùng `long`, nên kết quả được giữ chính xác trước phép nhân tiếp theo.

Tương tự, `(long) (a * b)` cũng quá muộn; cần `(long) a * b` hoặc `a * (long) b` để mở rộng **trước phép nhân đầu**.

Với biểu thức phức tạp, nên tách các bước thành biến trung gian có kiểu rõ ràng:

```java
long area = (long) width * height;
long volume = area * depth;
```

Hai dòng trên giả định `width`, `height` và `depth` đã được khai báo; đó là đoạn minh họa, không phải chương trình độc lập. Cách tách này giúp xác định phép toán nào có thể vượt `long` và cần kiểm tra thêm.

## 9. Cách phát hiện tràn và giữ số nguyên chính xác

### 9.1. Dùng kiểu rộng phù hợp từ lúc thực hiện phép toán

Nếu chứng minh được kết quả nằm trong miền `long`, hãy **nâng một toán hạng** hoặc sử dụng literal `long` trước phép cộng/nhân:

```java
int quantity = 1_000_000;
int unitPrice = 25_000;
long total = (long) quantity * unitPrice; // 25000000000
```

Tất cả giá trị `int` đều chuyển chính xác sang `long`, nhưng **mỗi phép toán** vẫn cần kiểm soát phạm vi kết quả. Đặc biệt, `long` không phải kiểu nguyên không giới hạn.

### 9.2. Dùng phép toán kiểm tra tràn khi tràn là lỗi

Các hàm `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, `Math.negateExact` và `Math.toIntExact` có thể phát hiện những phép toán/chuyển đổi được chúng hỗ trợ không biểu diễn được kết quả. Khi tràn, chúng ném `ArithmeticException`.

```java
int a = 50_000, b = 50_000;

try {
    int product = Math.multiplyExact(a, b);
    System.out.println(product);
} catch (ArithmeticException ex) {
    System.out.println("Phép nhân int vượt miền giá trị");
}
```

Không phải mọi biểu thức nguyên đều tự ném ngoại lệ khi tràn. Chẳng hạn `a * b` thông thường chỉ *wrap around*; muốn phát hiện cần dùng API kiểm tra hoặc kiểm tra biên trước.

Lưu ý `Math.multiplyExact((long) a, b)` trả về `long` và cũng kiểm tra tràn đối với kiểu `long`. Nếu phép tính nằm trong miền `long`, dùng `long` ngay từ đầu là đủ.

### 9.3. Dùng `BigInteger` khi 64 bit không đủ

`BigInteger` biểu diễn số nguyên độ chính xác tùy ý trong giới hạn bộ nhớ/tài nguyên, với các phép toán qua phương thức:

```java
import java.math.BigInteger;

BigInteger x = BigInteger.valueOf(Long.MAX_VALUE);
BigInteger y = x.add(BigInteger.ONE);
System.out.println(y); // 9223372036854775808
```

Quan trọng là chuyển **toán hạng** trước khi tính:

```java
long max = Long.MAX_VALUE;
BigInteger correct = BigInteger.valueOf(max).add(BigInteger.ONE);
// BigInteger tooLate = BigInteger.valueOf(max + 1); // max + 1 đã tràn long.
```

`BigInteger` là lớp bất biến: `add`/`multiply` trả đối tượng kết quả mới. Không dùng các toán tử `+`, `*` để cộng/nhân hai đối tượng `BigInteger`.

## 10. Ví dụ Java 17+ chạy độc lập

Tạo tệp **`ExpressionTypeBeforeAssignment.java`**:

```java
import java.math.BigInteger;

public class ExpressionTypeBeforeAssignment {
    public static void main(String[] args) {
        int a = 50_000;
        int b = 50_000;

        long tooLate = a * b;
        long widenedBeforeMultiply = (long) a * b;
        long castAfterMultiply = (long) (a * b);

        System.out.println("int product then long = " + tooLate);
        System.out.println("long before multiply = " + widenedBeforeMultiply);
        System.out.println("cast after multiply = " + castAfterMultiply);

        int max = Integer.MAX_VALUE;
        long sumTooLate = max + 1;
        long sumCorrect = max + 1L;
        System.out.println("int sum then long = " + sumTooLate);
        System.out.println("long sum = " + sumCorrect);

        double dividedAsInt = 1 / 2;
        double dividedAsDouble = 1 / 2.0;
        System.out.println("int division then double = " + dividedAsInt);
        System.out.println("double division = " + dividedAsDouble);

        byte count = 100;
        count += 30;
        System.out.println("byte compound assignment = " + count);

        try {
            Math.multiplyExact(a, b);
        } catch (ArithmeticException ex) {
            System.out.println("checked int multiplication overflow");
        }

        BigInteger precise = BigInteger.valueOf(a)
                .multiply(BigInteger.valueOf(b));
        System.out.println("BigInteger product = " + precise);
    }
}
```

Biên dịch và chạy:

```bash
javac ExpressionTypeBeforeAssignment.java
java ExpressionTypeBeforeAssignment
```

Kết quả:

```text
int product then long = -1794967296
long before multiply = 2500000000
cast after multiply = -1794967296
int sum then long = -2147483648
long sum = 2147483648
int division then double = 0.0
double division = 0.5
byte compound assignment = -126
checked int multiplication overflow
BigInteger product = 2500000000
```

Đây là chương trình đầy đủ, không cần thư viện bên ngoài JDK. Phần `tooLate`/`castAfterMultiply` chỉ khác vị trí chuyển kiểu so với `widenedBeforeMultiply` nhưng kết quả khác hẳn. Hai phép chia cũng chứng minh rõ: kiểu đích `double` không biến phép chia `int / int` thành phép chia số thực.

## 11. Lỗi thường gặp và cách tự kiểm tra

| Nhận định hay gặp | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “Gán `int * int` vào `long` sẽ không tràn.” | Phép nhân `int` xảy ra trước khi gán. | `(long) a * b`. |
| “Cast toàn biểu thức sau cùng vẫn giữ được kết quả.” | Cast không thể hồi phục các bit đã mất. | Cast toán hạng trước phép tính gây tràn. |
| “Biến đích `double` làm `1 / 2` thành `0.5`.” | `1 / 2` là chia nguyên và cho `0` trước khi đổi sang `double`. | `1.0 / 2` hoặc `(double) 1 / 2`. |
| “Cộng hai `byte` luôn cho `byte`.” | Phép cộng nâng toán hạng lên `int`. | Nhận vào `int`, hoặc cast có kiểm tra miền. |
| “Phép `+=` không mất dữ liệu vì không cần cast.” | Gán ghép có ép kiểu hẹp ngầm. | Xét rõ phạm vi giá trị hoặc dùng kiểu rộng hơn. |
| “Chuyển một phép toán đã tràn sang `BigInteger` sẽ sửa đúng.” | `BigInteger.valueOf(a * b)` nhận giá trị nguyên thủy đã tràn. | `BigInteger.valueOf(a).multiply(BigInteger.valueOf(b))`. |
| “Bất cứ khi nào thấy toán tử `+` đều áp dụng bảng numeric promotion.” | `+` cũng có thể là nối chuỗi; các toán tử khác có quy tắc riêng. | Xác định toán tử và kiểu từng toán hạng/biểu thức con. |

Khi đọc một biểu thức dài, hãy xác định **kiểu của từng toán hạng**, **kiểu của từng phép toán**, **vị trí chuyển kiểu**, **giới hạn của kiểu đang tính** rồi mới nhìn tới **kiểu biến nhận kết quả**. Đặc biệt phải xét các cặp `int × int` gán `long`, `int / int` gán `double`, và phép gán ghép trên `byte`/`short`.

**Ghi nhớ:** *Kiểu biến nhận quyết định cách lưu kết quả đã tính; kiểu của biểu thức quyết định phép tính diễn ra thế nào.* Nếu cần giữ kết quả chính xác, chọn và chuyển kiểu **trước phép toán có nguy cơ tràn hoặc mất phần thập phân**, hoặc dùng phương thức kiểm tra tràn/kiểu số nguyên lớn.

**Tài liệu tham khảo:** [Java Language Specification §5.6 — Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.6), [§5.2 — Assignment Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.2), [§15.17 — Multiplicative Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.17), [§15.18 — Additive Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.18), [§15.26.2 — Compound Assignment Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.26.2).
