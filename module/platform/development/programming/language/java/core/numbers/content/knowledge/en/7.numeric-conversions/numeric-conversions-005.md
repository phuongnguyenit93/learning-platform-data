# Ép `float` hoặc `double` sang số nguyên: cắt về phía 0 trong Java

## 1. Bản chất của phép ép kiểu

Trong Java, một giá trị `float` hoặc `double` có thể chứa phần thập phân, còn các kiểu số nguyên `byte`, `short`, `int`, `long` và `char` biểu diễn các giá trị nguyên trong miền hữu hạn. Khi ép kiểu số thực sang số nguyên bằng cú pháp `(T) expression`, Java thực hiện **narrowing primitive conversion** (chuyển đổi nguyên thủy thu hẹp).

Với một số thực **hữu hạn có phần nguyên biểu diễn được**, phép chuyển đổi loại bỏ phần lẻ bằng quy tắc **làm tròn về 0** (*round toward zero*, *truncation*):

- `(int) 7.9` bằng **7**.
- `(int) 7.1` bằng **7**.
- `(int) -7.9` bằng **-7**.
- `(int) -7.1` bằng **-7**.

Đây **không phải làm tròn tới số nguyên gần nhất**. Nó cũng không phải luôn “làm tròn xuống”: với số âm, `-7.9` chuyển thành `-7`, trong khi `Math.floor(-7.9)` là `-8.0`.

Điểm quan trọng khác: khi số thực là **NaN**, **vô cực**, hoặc có độ lớn vượt miền số nguyên đích, Java có các quy tắc riêng. Không thể chỉ nói “bỏ dấu chấm” hoặc “xóa phần thập phân” để giải thích mọi trường hợp.

## 2. Cú pháp và kiểu kết quả

Cú pháp:

```java
int n = (int) 12.75;      // 12
long m = (long) -12.75;   // -12
float f = 3.99f;
int fromFloat = (int) f;  // 3
double d = -3.99;
long fromDouble = (long) d; // -3
```

`(int)` và `(long)` là **toán tử ép kiểu tường minh** (*cast*). Biểu thức sau khi ép có kiểu tương ứng với tên kiểu được ghi trong dấu ngoặc. Java không tự động cho phép gán một `double` bất kỳ vào `int` mà không có cast:

```java
double value = 12.75;
// int invalid = value; // LỖI biên dịch: có nguy cơ mất phần lẻ
int valid = (int) value;
```

Về cú pháp, dấu ngoặc ở `(int) value` là một phần của cast, không phải lời gọi phương thức. Hãy đặt dấu ngoặc ngoài khi cần ép kết quả cả biểu thức:

```java
double a = 1.9;
double b = 2.9;

int castEach = (int) a + (int) b; // 1 + 2 = 3
int castSum = (int) (a + b);      // (int) 4.8 = 4
```

**Ép từng toán hạng rồi cộng** khác với **cộng số thực trước rồi ép kết quả**. Quyết định cách nào đúng phụ thuộc yêu cầu nghiệp vụ; không thể tùy tiện chuyển vị trí của cast.

## 3. Cắt về 0 khác `floor`, `ceil` và làm tròn gần nhất

Xem bảng đối chiếu với đầu vào là `double`:

| Giá trị đầu vào | `(int) x` | `Math.floor(x)` | `Math.ceil(x)` | `Math.round(x)` |
|---:|---:|---:|---:|---:|
| 3.8 | 3 | 3.0 | 4.0 | 4 |
| 3.2 | 3 | 3.0 | 4.0 | 3 |
| -3.8 | -3 | -4.0 | -3.0 | -4 |
| -3.2 | -3 | -4.0 | -3.0 | -3 |
| 2.5 | 2 | 2.0 | 3.0 | 3 |
| -2.5 | -2 | -3.0 | -2.0 | -2 |

Ý nghĩa:

- **Cast `(int) x`**: cắt về 0; kết quả kiểu `int`.
- **`Math.floor(x)`**: lấy số nguyên theo hướng **âm vô cực**; với đối số `double`, kết quả vẫn có kiểu `double`.
- **`Math.ceil(x)`**: lấy số nguyên theo hướng **dương vô cực**; với đối số `double`, kết quả vẫn có kiểu `double`.
- **`Math.round(double)`**: chọn số nguyên gần nhất, xử lý trường hợp đúng nửa theo hướng dương vô cực; trả về `long`. Với `float`, overload `Math.round(float)` trả về `int`.

Ví dụ `Math.round(-2.5)` bằng -2, còn `Math.round(2.5)` bằng 3. Cast cả hai cho -2 và 2 vì chỉ loại bỏ phần lẻ.

**Không dùng `Math.floor` để mô phỏng cast với số âm.** Nếu muốn hành vi của cast, viết cast và áp dụng kiểm tra NaN/miền giá trị khi cần. Nếu muốn quy tắc làm tròn cho tài chính, độ chính xác hoặc quy tắc nửa lên/nửa chẵn, hãy xác định rõ yêu cầu và chọn API thích hợp; cast không đáp ứng những yêu cầu làm tròn đó.

## 4. Ví dụ hoàn chỉnh: cắt phần lẻ về 0

Tạo file `TruncationDemo.java`:

```java
public class TruncationDemo {
    public static void main(String[] args) {
        double positive = 7.9;
        double negative = -7.9;

        System.out.println("(int) 7.9 = " + (int) positive);
        System.out.println("(int) -7.9 = " + (int) negative);
        System.out.println("(long) -7.9 = " + (long) negative);
        System.out.println("(int) -0.9 = " + (int) -0.9);
        System.out.println("(int) 0.9 = " + (int) 0.9);

        System.out.println("floor(-7.9) = " + Math.floor(negative));
        System.out.println("ceil(-7.9) = " + Math.ceil(negative));
        System.out.println("round(7.9) = " + Math.round(positive));
        System.out.println("round(-7.9) = " + Math.round(negative));

        double a = 1.9;
        double b = 2.9;
        System.out.println("cast each = " + ((int) a + (int) b));
        System.out.println("cast sum = " + (int) (a + b));
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac TruncationDemo.java
java TruncationDemo
```

Kết quả:

```text
(int) 7.9 = 7
(int) -7.9 = -7
(long) -7.9 = -7
(int) -0.9 = 0
(int) 0.9 = 0
floor(-7.9) = -8.0
ceil(-7.9) = -7.0
round(7.9) = 8
round(-7.9) = -8
cast each = 3
cast sum = 4
```

Một lưu ý về **-0.0**: `double` và `float` có cả giá trị +0.0 và -0.0, nhưng kiểu số nguyên Java không có hai loại số 0 như vậy. Ép `-0.0` sang `int` hoặc `long` đều cho **0**.

## 5. Quy tắc Java thực sự dùng khi chuyển sang số nguyên

Đặc tả ngôn ngữ Java (JLS, phần *Narrowing Primitive Conversion*) xác định việc chuyển từ `float`/`double` sang kiểu tích phân theo **hai bước**.

### Bước 1: chuyển sang `int` hoặc `long`

- Nếu kiểu đích cuối là `long`, bước đầu chuyển sang `long`.
- Nếu kiểu đích cuối là `byte`, `short`, `char` hoặc `int`, bước đầu chuyển sang `int`.

Quy tắc của bước này:

1. **NaN** → kết quả nguyên **0**.
2. **Số hữu hạn** → làm tròn về 0; nếu phần nguyên biểu diễn được trong kiểu trung gian, lấy phần nguyên đó.
3. **Quá lớn hoặc +Infinity** → dùng giá trị **lớn nhất** của `int` hoặc `long` tương ứng.
4. **Quá nhỏ hoặc -Infinity** → dùng giá trị **nhỏ nhất** của `int` hoặc `long` tương ứng.

Việc đưa kết quả về giá trị biên khi vượt miền thường gọi là **saturation/clamping**. Nó khác với quy tắc bỏ bit khi chuyển từ một kiểu nguyên lớn sang kiểu nguyên nhỏ.

### Bước 2: nếu đích là `byte`, `short` hoặc `char`

Kết quả `int` của bước đầu tiếp tục được **thu hẹp theo quy tắc chuyển số nguyên**: giữ các bit thấp tương ứng 8 hoặc 16 bit, rồi diễn giải theo kiểu đích. Vì thế kết quả **có thể quay vòng, đổi dấu**, chứ không bị kẹp trực tiếp trong miền `byte`/`short`.

Ví dụ:

```java
byte b = (byte) 130.9; // bước 1: int 130; bước 2: byte -126
short s = (short) 32768.7; // bước 1: int 32768; bước 2: short -32768
char c = (char) -1.9; // bước 1: int -1; bước 2: char code unit 65535
```

**Đừng nhầm hai kiểu thu hẹp:** ép số thực sang `int/long` có quy tắc làm tròn và giới hạn biên; ép một số `int` sang `byte/short/char` tiếp tục bằng việc giữ bit thấp.

## 6. Giá trị đặc biệt cần xác thực trước khi ép

Quy tắc cắt về 0 chỉ mô tả trường hợp số hữu hạn nằm trong miền. Với `NaN`, cast sang `int` hoặc `long` cho `0`; với `+Infinity`, `-Infinity` hoặc giá trị vượt miền, kết quả bị chặn ở biên tương ứng. Nếu đích là `byte`, `short` hoặc `char`, Java chuyển qua `int` trước, rồi giữ các bit thấp của kiểu đích; do đó không có quy tắc chặn trực tiếp về giới hạn `byte` hay `short`.

Ví dụ `(int) Double.NaN == 0` và `(byte) Double.POSITIVE_INFINITY == -1`. Những kết quả này chỉ là quy tắc cast, không chứng minh dữ liệu đầu vào hợp lệ. Khi API cần số nguyên từ phép đo, nên dùng `Double.isFinite` và kiểm tra miền trước khi cast. Bài tiếp theo khảo sát riêng các trường hợp `NaN`, vô cực và biên số thực bằng trace và ví dụ đầy đủ.

## 7. Mất độ chính xác có thể xảy ra **trước cả phép ép**

Kiểu `float` (32 bit) có khoảng 24 bit ý nghĩa nhị phân; `double` (64 bit) có khoảng 53 bit ý nghĩa. Không phải mọi số thập phân hay số nguyên lớn đều biểu diễn chính xác.

Ví dụ:

```java
float f = 16_777_217f;  // không lưu chính xác số này
int value = (int) f;     // 16777216
```

Số nguyên toán học **16_777_217** không biểu diễn chính xác bằng `float`; giá trị trong biến đã được làm tròn thành 16_777_216 **trước** khi ép. Phép `(int) f` chỉ chuyển **giá trị thực sự đang lưu**, không lấy lại chữ số đã mất.

Tương tự, nhiều phân số thập phân như `0.1` không biểu diễn chính xác bằng số thực nhị phân. Với phép ép số nguyên, điều này đặc biệt đáng lưu ý khi kết quả tính toán nằm sát một ranh giới nguyên.

```java
double value = 0.1 + 0.2;
System.out.println(value); // 0.30000000000000004
System.out.println((int) value); // 0
```

Không nên coi việc cast là cách sửa sai số dấu phẩy động. Khi cần giữ số chữ số thập phân và quy tắc làm tròn có kiểm soát (ví dụ tiền tệ), cân nhắc `BigDecimal` cùng nguồn dữ liệu và `RoundingMode` phù hợp.

## 8. Vì sao `Math.round` không giống ép kiểu?

Một chương trình có thể cần “lấy phần nguyên” theo nhiều nghĩa:

- **Bỏ phần lẻ về 0**: `(int) x` hoặc `(long) x`.
- **Lấy số nguyên không lớn hơn x**: `Math.floor(x)`.
- **Lấy số nguyên không nhỏ hơn x**: `Math.ceil(x)`.
- **Chọn số nguyên gần nhất**: `Math.round(x)` theo quy tắc của phương thức.

Các phương thức này không chỉ khác nhau với số âm; chúng còn có **kiểu trả về** và các quy tắc đặc biệt riêng.

Ví dụ:

```java
System.out.println((int) 2.9);       // 2
System.out.println(Math.round(2.9));  // 3
System.out.println((int) -2.9);      // -2
System.out.println(Math.round(-2.9)); // -3
System.out.println(Math.floor(-2.9)); // -3.0
System.out.println(Math.ceil(-2.9));  // -2.0
```

`Math.round(double)` trả `long`, nhưng `Math.round(float)` trả `int`; phương thức đó cũng có hành vi khi gặp NaN và vượt miền, nên **đừng thay kiểm tra tính hợp lệ bằng `round`**. Ngoài ra, kết quả `Math.floor`/`ceil` vẫn là kiểu số thực, chưa phải `int` hoặc `long`.

Nếu yêu cầu **từ chối mọi giá trị có phần lẻ**, cast đơn thuần là không đủ, vì nó cố ý bỏ phần lẻ. Dùng cách kiểm tra phù hợp trước khi chuyển.

## 9. Kiểm tra dữ liệu trước khi chuyển sang `int`

Giả sử một ứng dụng nhận `double` từ bên ngoài nhưng yêu cầu:

1. Giá trị phải là **hữu hạn** (không NaN, không vô cực).
2. Giá trị đầu vào phải **nằm trong miền số nguyên `int`**.
3. Chấp nhận phép **cắt phần lẻ về 0** theo quy tắc bài học.

Một phương thức kiểm tra tường minh:

```java
static int truncateFiniteInt(double value) {
    if (!Double.isFinite(value)
            || value < Integer.MIN_VALUE
            || value >= 2_147_483_648.0) {
        throw new IllegalArgumentException("outside int input range");
    }
    return (int) value;
}
```

Đây là **đoạn phương thức minh họa**, cần đặt trong một class Java. Mốc cận trên dùng `2_147_483_648.0` vì đó là **số đầu tiên lớn hơn `Integer.MAX_VALUE`** trong miền số nguyên; biểu diễn `(double) Integer.MAX_VALUE` bằng 2_147_483_647.0 là chính xác.

Phương thức này áp dụng **chính sách kiểm tra giá trị số thực gốc phải nằm trong miền `int`**, chứ không chỉ kiểm tra “sau khi cắt, số nguyên có thể biểu diễn được không”. Ví dụ `-2_147_483_648.5` nếu cast trực tiếp có thể ra `Integer.MIN_VALUE`, nhưng chính sách trên từ chối vì **giá trị đầu vào** nhỏ hơn cận dưới. Đây là lựa chọn kiểm tra rõ ràng và nghiêm ngặt cho API.

Nếu ứng dụng còn yêu cầu **không được có phần lẻ**, thêm:

```java
if (value != Math.rint(value)) {
    throw new IllegalArgumentException("fractional input");
}
```

Điều kiện này chỉ nên dùng **sau kiểm tra `Double.isFinite`**; `Math.rint` trả về giá trị `double` gần nhất theo kiểu làm tròn nửa về số chẵn, và so sánh bằng chỉ giúp kiểm tra giá trị đang lưu đã là số nguyên hay chưa. Nó **không chứng minh** văn bản đầu vào ban đầu không có phần thập phân, vì dữ liệu `double` có thể đã mất độ chính xác trước đó.

### Phiên bản runnable kèm kiểm tra

Tạo file `ValidatedTruncation.java`:

```java
public class ValidatedTruncation {
    static int truncateFiniteInt(double value) {
        if (!Double.isFinite(value)
                || value < Integer.MIN_VALUE
                || value >= 2_147_483_648.0) {
            throw new IllegalArgumentException("outside int input range");
        }
        return (int) value;
    }

    public static void main(String[] args) {
        System.out.println(truncateFiniteInt(15.9));
        System.out.println(truncateFiniteInt(-15.9));

        for (double value : new double[] {
                Double.NaN, Double.POSITIVE_INFINITY, 1.0e20
        }) {
            try {
                System.out.println(truncateFiniteInt(value));
            } catch (IllegalArgumentException e) {
                System.out.println("rejected");
            }
        }
    }
}
```

Chạy:

```bash
javac ValidatedTruncation.java
java ValidatedTruncation
```

Kết quả:

```text
15
-15
rejected
rejected
rejected
```

Với `long`, cần chú ý đặc biệt: **`(double) Long.MAX_VALUE` làm tròn thành \(2^{63}\)**, vốn **ngoài miền `long`**. Bởi vậy kiểm tra `value <= Long.MAX_VALUE` dưới phép so sánh số thực không bảo đảm ngăn chặn giới hạn trên. Với chính sách yêu cầu giá trị đầu vào nằm trong miền `long`, các cận hữu ích là:

```java
static long truncateFiniteLong(double value) {
    if (!Double.isFinite(value)
            || value < -0x1.0p63
            || value >= 0x1.0p63) {
        throw new IllegalArgumentException("outside long input range");
    }
    return (long) value;
}
```

`0x1.0p63` là literal **số thực dạng thập lục phân** của Java, có giá trị chính xác \(2^{63}\) ở kiểu `double`. Đây không phải literal số nguyên. Cận dưới \(-2^{63}\) là giá trị chính xác hợp lệ của `long`, còn cận trên \(2^{63}\) là giá trị đầu tiên bị loại khỏi miền.

## 10. Khi nào cần `BigDecimal` hoặc chuyển đổi chính xác?

Nếu dữ liệu ban đầu là **chuỗi thập phân** hoặc giá trị phải giữ chính xác phần thập phân (ví dụ số tiền), việc đọc vào `double` trước có thể làm mất chính xác. `BigDecimal` giúp biểu diễn các số thập phân theo decimal và kiểm soát chuyển đổi:

```java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("123.75");
int truncated = amount.intValue(); // 123, nhưng có thể mất phần lẻ
```

Đây là **đoạn mã minh họa** bên trong phương thức, không phải một tệp chạy độc lập. Nếu muốn **bắt lỗi khi có phần lẻ hoặc không vừa kiểu đích**, dùng:

```java
BigDecimal amount = new BigDecimal("123.75");
// int exact = amount.intValueExact(); // ném ArithmeticException
```

`intValueExact()` chỉ thành công khi giá trị là số nguyên chính xác nằm trong miền `int`; `longValueExact()` làm điều tương tự cho `long`. Với yêu cầu làm tròn trước khi chuyển, chọn `setScale(0, RoundingMode.XXX)` với chính sách rõ ràng rồi gọi phương thức chuyển phù hợp.

Nếu số nguyên có thể vượt miền `long`, `BigInteger` là một lựa chọn cho số nguyên độ lớn không cố định; `BigDecimal.toBigIntegerExact()` yêu cầu giá trị thập phân đúng là số nguyên. Không nên giả định cast từ `double` sang `long` sẽ tự mở rộng giới hạn lưu trữ.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `(int) -3.9` cho -3 chứ không -4 | Cast cắt về 0 | Dùng `Math.floor` nếu cần làm tròn xuống |
| `(int) 3.9` cho 3 chứ không 4 | Cast không làm tròn gần nhất | Dùng `Math.round` theo quy tắc thích hợp |
| `(int) Double.NaN` cho 0 | Quy tắc chuyển NaN của Java | Kiểm tra `Double.isNaN` hoặc `isFinite` trước |
| `(int) Double.POSITIVE_INFINITY` cho MAX | Giá trị vượt miền bị kẹp ở cận | Từ chối giá trị không hữu hạn nếu không hợp lệ |
| `(int) 1e20` vẫn có giá trị `int` | Cast bão hòa, không ném lỗi | Kiểm tra miền trước khi chuyển |
| `(byte) 130.9` thành -126 | Chuyển double → int 130 → giữ 8 bit | Kiểm tra cả miền `byte` nếu cần giá trị chính xác |
| `(byte) +Infinity` thành -1 | +Infinity → `Integer.MAX_VALUE` → 8 bit thấp | Hiểu quy trình hai bước và từ chối infinity |
| `(int) 16_777_217f` cho 16_777_216 | `float` đã mất chính xác từ trước | Sử dụng kiểu/định dạng phù hợp nguồn dữ liệu |
| `(int) a + (int) b` khác `(int)(a+b)` | Thời điểm cắt phần lẻ khác nhau | Đặt cast và ngoặc theo đúng yêu cầu |
| Kiểm tra `doubleValue <= Long.MAX_VALUE` không chắc chắn | `Long.MAX_VALUE` đổi sang double thành \(2^{63}\) | Dùng cận chính xác `value < 0x1.0p63` |
| Cast dùng để xác nhận “đầu vào là số nguyên” | Cast im lặng bỏ phần lẻ | Kiểm tra phần lẻ hoặc dùng `intValueExact` |

## 12. Bài tập tự kiểm tra

**Câu 1.** `(int) 8.99` và `(int) -8.99` bằng bao nhiêu?  
**Đáp án:** 8 và -8 vì cả hai đều cắt phần lẻ về 0.

**Câu 2.** `(int) -0.99` có bằng -1 không?  
**Đáp án:** Không. Kết quả là 0.

**Câu 3.** `(int) -2.7` khác `Math.floor(-2.7)` thế nào?  
**Đáp án:** Lần lượt là -2 và -3.0; `floor` làm tròn xuống, cast cắt về 0.

**Câu 4.** Vì sao `(int) Double.NaN` ra 0 nhưng `(int) Double.POSITIVE_INFINITY` ra 2_147_483_647?  
**Đáp án:** JLS quy định NaN thành số nguyên 0; vô cực dương thành giá trị tối đa của kiểu trung gian.

**Câu 5.** `(byte) 130.9` cho kết quả gì?  
**Đáp án:** -126. Đầu tiên cắt về 0 thành `int` 130, tiếp đó thu hẹp về `byte` bằng cách giữ 8 bit thấp.

**Câu 6.** Với `double a = 1.9, b = 2.9`, hai biểu thức `(int)a + (int)b` và `(int)(a+b)` cho gì?  
**Đáp án:** 3 và 4. Cast diễn ra ở hai thời điểm khác nhau.

**Câu 7.** Cast từ `double` sang `int` có ném ngoại lệ khi vượt miền không?  
**Đáp án:** Không. Nó cho cận MIN/MAX thích hợp; nếu cần từ chối dữ liệu, phải kiểm tra trước.

**Câu 8.** `float f = 16_777_217f; (int) f` có chắc bằng 16_777_217 không?  
**Đáp án:** Không. `float` làm tròn giá trị thành 16_777_216 trước khi cast.

**Câu 9.** Tại sao kiểm tra giá trị `double` với cận `Long.MAX_VALUE` cần cẩn thận?  
**Đáp án:** Vì `Long.MAX_VALUE` không biểu diễn chính xác dưới dạng `double` và được làm tròn thành \(2^{63}\), ngoài miền `long`. Cận trên an toàn theo chính sách đầu vào là `value < 0x1.0p63`.

**Câu 10.** Khi bắt buộc dữ liệu thập phân là một số nguyên chính xác, nên dùng gì?  
**Đáp án:** Với dữ liệu `BigDecimal`, dùng `intValueExact()` hoặc `longValueExact()`. Với `double`, kiểm tra tính hữu hạn, miền và có phần lẻ trước khi chuyển, đồng thời hiểu rằng giá trị có thể đã mất chính xác từ nguồn.

## 13. Ghi nhớ và tài liệu tham khảo

- **Trong miền hợp lệ và với số hữu hạn:** `float/double → int/long` bằng cast là **cắt về 0**, cả số dương lẫn số âm.
- **NaN → 0**, **+Infinity/quá lớn → MAX**, **-Infinity/quá nhỏ → MIN** của kiểu trung gian; không tự ném ngoại lệ.
- **Ép sang `byte/short/char` là hai bước:** sang `int` theo quy tắc số thực rồi tiếp tục thu hẹp kiểu số nguyên theo bit.
- **Thời điểm cast rất quan trọng:** `(int)a + (int)b` có thể khác `(int)(a+b)`.
- **Chọn chính sách chuyển đổi theo nhu cầu:** cắt phần lẻ, làm tròn, từ chối dữ liệu ngoài miền hoặc yêu cầu chuyển chính xác là bốn mục tiêu khác nhau.

Nguồn quy tắc ngôn ngữ: [Java Language Specification — Chapter 5, Conversions and Contexts, §5.1.3 Narrowing Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se26/html/jls-5.html).
