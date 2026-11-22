# Dấu âm là toán tử chứ không phải một phần của literal

## 1. Phân biệt literal với dấu âm trong mã nguồn Java

Khi viết `-42`, người đọc thường gọi cả cụm là “literal số âm”. Đây là cách nói thuận tiện trong đời thường, nhưng **không chính xác ở cấp độ cú pháp Java**:

- `42` là một **integer literal** (literal số nguyên) có giá trị 42.
- `-` là **toán tử âm một ngôi** (*unary minus operator*).
- `-42` là **biểu thức** áp dụng toán tử `-` lên literal `42`; kết quả của biểu thức bằng −42.

Điểm quan trọng là **dấu trừ nằm ngoài token literal**. Khi Java phân tích mã nguồn, phần chữ số của số và toán tử `-` được nhận diện riêng; sau đó quy tắc biểu thức quyết định toán tử áp dụng vào toán hạng nào.

Ví dụ:

~~~java
int positive = 42;    // 42 là decimal integer literal
int negative = -42;   // toán tử - áp dụng lên literal 42
int difference = 10 - 3; // phép trừ hai ngôi, kết quả 7
int another = 10 - -3;   // trừ một số âm, kết quả 13
~~~

Đây là **đoạn minh họa**; muốn chạy độc lập phải đặt trong class và method thích hợp. Cùng một ký hiệu `-` có thể đảm nhiệm **hai vai trò**:

| Dạng | Vai trò `-` | Diễn giải |
|---|---|---|
| `-42` | Toán tử âm **một ngôi** | Lấy giá trị đối của 42 |
| `-value` | Toán tử âm **một ngôi** | Lấy giá trị đối của biến/biểu thức `value` |
| `left - right` | Phép trừ **hai ngôi** | Lấy `left` trừ `right` |
| `10 - -3` | Một phép trừ hai ngôi và một phép âm một ngôi | `10 - (-3) = 13` |
| `-(a + b)` | Phép âm một ngôi áp dụng lên biểu thức trong ngoặc | Lấy số đối của tổng |

Không cần nói “literal âm” để giải thích đúng chương trình: **literal có chữ số, còn dấu âm là toán tử trong biểu thức**.

## 2. Java tách token và tạo biểu thức như thế nào?

Quá trình hiểu `int x = -123;` có thể hình dung như sau:

1. **Phân tích từ vựng (lexical analysis):** nhận ra `int`, `x`, `=`, toán tử `-`, literal `123` và dấu `;`.
2. **Phân tích cú pháp (parsing):** xác định `-123` là một *unary expression*, khác với `x - 123` là một *binary expression*.
3. **Kiểm tra kiểu/đánh giá:** tìm kiểu toán hạng, thực hiện phép âm và gán kết quả hợp lệ vào biến `int`.

Literal số nguyên trong Java có nhiều cách viết: thập phân như `123`, nhị phân như `0b1111011`, bát phân như `0173`, hoặc thập lục phân như `0x7B`. **Dấu `-` đứng trước biểu thức, không thuộc cách ghi cơ số**:

~~~java
int decimal = -123;
int binary = -0b1111011;
int octal = -0173;
int hexadecimal = -0x7B;
~~~

Bốn biến trên đều có giá trị số nguyên **−123**, dù bốn literal không dấu dùng các cơ số khác nhau.

### Có thể dùng dấu cộng một ngôi

Java còn hỗ trợ toán tử `+` một ngôi. Ví dụ `+42` áp dụng *unary plus* lên literal `42` và vẫn cho giá trị 42; dấu `+` cũng **không thuộc literal**. Toán tử `+` một ngôi vẫn thực hiện *unary numeric promotion*, giống như toán tử âm một ngôi; vì thế không nên giả định nó giữ nguyên kiểu `byte`, `short` hay `char` trong mọi biểu thức.

### Toán tử âm và dấu trừ có thứ tự ưu tiên khác nhau

`-number` là toán tử một ngôi; `left - right` là phép trừ hai ngôi. Toán tử một ngôi liên kết chặt hơn các phép cộng/trừ hai ngôi trong biểu thức thông thường:

~~~java
int a = 2;
int b = 3;
int first = -a * b;      // (-a) * b, kết quả -6
int second = a - -b;     // a - (-b), kết quả 5
int third = -(a + b);    // -(2 + 3), kết quả -5
~~~

Đây là **đoạn minh họa**, không phải class độc lập. Ngoặc giúp tránh hiểu lầm, đặc biệt ở những biểu thức nhiều toán tử. Java **không có toán tử lũy thừa `^`**: ký hiệu `^` là XOR bit, nên `-2 ^ 2` không có nghĩa “âm hai bình phương”.

## 3. Bài toán ranh giới: `Integer.MIN_VALUE`

Một câu hỏi thú vị: `int` nhận giá trị từ **−2.147.483.648** đến **2.147.483.647**, vậy mã `-2147483648` được biên dịch thế nào nếu literal thập phân không có dấu `2147483648` vượt giá trị dương tối đa?

Java có **quy tắc đặc biệt trong cú pháp literal số nguyên thập phân**:

- Literal thập phân `2147483648` được **cho phép đúng trong ngữ cảnh làm toán hạng của toán tử âm một ngôi**.
- Do đó, biểu thức `-2147483648` hợp lệ và có giá trị `Integer.MIN_VALUE`.
- Literal `2147483648` **đứng riêng** là lỗi biên dịch; không thể gán nó vào `long` rồi kỳ vọng Java tự xử lý vì literal không có hậu tố `L`.
- Nếu cần số dương 2.147.483.648, viết `2147483648L` để đó là literal `long`.

Ví dụ hợp lệ:

~~~java
int min = -2147483648;
long aboveIntMax = 2147483648L;
int viaConstant = Integer.MIN_VALUE;
~~~

Ví dụ sau **cố ý không biên dịch**; chỉ minh họa lỗi và **không** nên đặt vào chương trình chạy:

~~~java
int invalid = 2147483648; // literal decimal int ngoài phạm vi ở ngữ cảnh này
long alsoInvalid = 2147483648; // thiếu hậu tố L cho literal
~~~

Quy tắc tương tự áp dụng cho `long` ở biên âm:

- `long min = -9223372036854775808L;` **hợp lệ**, bằng `Long.MIN_VALUE`.
- Literal thập phân `9223372036854775808L` chỉ được dùng trong ngữ cảnh toán hạng của toán tử âm một ngôi; đứng riêng là lỗi.
- `long beyond = 9223372036854775808L;` **không hợp lệ**. Nếu cần số nguyên dương lớn hơn `Long.MAX_VALUE`, dùng `BigInteger`.

Một chi tiết cần nhớ: phép **âm một ngôi không tự tạo ra kiểu rộng hơn**. `int value = -2147483648;` hợp lệ theo quy tắc ranh giới trên; nhưng phủ định `Integer.MIN_VALUE` **khi đang chạy** là một phép toán `int` thông thường và có thể tràn số. Hai tình huống cần phân biệt rõ.

## 4. Literal ở các cơ số khác có quy tắc bit riêng

Các literal nguyên **nhị phân, bát phân và thập lục phân** có thể mô tả mẫu bit có bit cao nhất bằng 1. Khi được dùng với kiểu `int` hoặc `long`, mẫu bit đó được hiểu theo cách biểu diễn bù hai (*two's complement*) của Java; do vậy một literal viết **không có dấu âm ở trước** vẫn có thể mang giá trị số nguyên âm.

Ví dụ:

~~~java
int hexMin = 0x8000_0000;    // Integer.MIN_VALUE
int allBits = 0xFFFF_FFFF;   // -1
long longMin = 0x8000_0000_0000_0000L; // Long.MIN_VALUE
~~~

Đây là **đoạn minh họa**. Không nên kết luận từ việc nhìn thấy chữ số `8` hoặc `F` rằng literal phải là “số dương”, hay từ việc không có `-` rằng giá trị runtime chắc chắn không âm.

Đặc biệt, `-0x80000000` vẫn cho `Integer.MIN_VALUE` do phép âm trên giá trị `int` nhỏ nhất tràn theo quy tắc số nguyên cố định, **không** tạo thành số dương 2.147.483.648. Nếu cần giá trị dương đó, viết `0x8000_0000L` hoặc `2147483648L`.

Tóm lại, phải tách **hình thức viết literal**, **kiểu của literal**, **mẫu bit**, và **toán tử áp dụng lên nó**. Cách biểu diễn bit không làm `-` trở thành một phần của token literal.

## 5. Ví dụ Java 17+ chạy độc lập: literal và toán tử dấu âm

Tạo tệp `MinusLiteralDemo.java`:

~~~java
public class MinusLiteralDemo {
    public static void main(String[] args) {
        int positive = 42;
        int negative = -42;
        int minInt = -2147483648;
        long bigPositive = 2147483648L;
        long minLong = -9223372036854775808L;

        int decimal = -123;
        int binary = -0b1111011;
        int octal = -0173;
        int hex = -0x7B;

        System.out.println("positive=" + positive);
        System.out.println("negative=" + negative);
        System.out.println("minInt=" + minInt);
        System.out.println("bigPositive=" + bigPositive);
        System.out.println("minLong=" + minLong);
        System.out.println("sameValue="
                + (decimal == binary && binary == octal && octal == hex));
        System.out.println("hexBits=" + 0x8000_0000);
        System.out.println("parseText=" + Integer.parseInt("-42"));
    }
}
~~~

Biên dịch/chạy với JDK 17 hoặc mới hơn:

~~~bash
javac MinusLiteralDemo.java
java MinusLiteralDemo
~~~

Kết quả chuẩn:

~~~text
positive=42
negative=-42
minInt=-2147483648
bigPositive=2147483648
minLong=-9223372036854775808
sameValue=true
hexBits=-2147483648
parseText=-42
~~~

Hai loại “dấu trừ” cũng xuất hiện ở các **ngữ cảnh khác nhau**: trong mã `-42` là toán tử một ngôi; trong chuỗi ký tự `"-42"`, dấu `-` chỉ là ký tự dữ liệu cho đến khi `Integer.parseInt` đọc chuỗi và diễn giải nó theo cú pháp số có dấu. Quy tắc tách token Java không áp dụng trực tiếp cho các ký tự bên trong chuỗi.

## 6. Âm một ngôi có thể làm thay đổi kiểu biểu thức

Trong Java, toán tử âm một ngôi thực hiện **unary numeric promotion**:

- Với `byte`, `short` và `char`, toán hạng được nâng lên `int`; kết quả của `-operand` có kiểu `int`.
- Với `int`, kết quả vẫn có kiểu `int`.
- Với `long`, `float`, `double`, kết quả có cùng kiểu tương ứng sau quy tắc promotion.

Vì vậy, ví dụ sau **không biên dịch** do gán một kết quả `int` về biến `byte` khi dùng biến thông thường:

~~~java
byte count = 7;
byte invalid = -count; // lỗi: biểu thức -count có kiểu int
~~~

Nếu `count` là biến mutable trong ví dụ, dù giá trị là 7 vẫn phải ép kiểu rõ ràng: `byte negated = (byte) -count;`. Còn `byte literalValue = -7;` **hợp lệ** vì `-7` là *constant expression* kiểu `int` có giá trị nằm trong phạm vi `byte`, được cho phép bởi quy tắc thu hẹp hằng số tại phép gán. Đây là khác biệt giữa **giá trị hằng khi biên dịch** và **phép toán trên biến khi chạy**.

`char` không dấu 16 bit nhưng `-letter` không biến thành “`char` âm”: nó có kiểu `int` và có thể nhận giá trị âm nếu mã của `letter` dương. Điều này phản ánh quy tắc promotion, không đổi bản chất của kiểu `char`.

### Ví dụ Java 17+ chạy độc lập: promotion và phép trừ

Tạo tệp `UnaryMinusPromotionDemo.java`:

~~~java
public class UnaryMinusPromotionDemo {
    public static void main(String[] args) {
        byte small = 7;
        char letter = 'A';

        int negativeByte = -small;
        int negativeCharCode = -letter;
        byte constantByte = -7;

        System.out.println("negativeByte=" + negativeByte);
        System.out.println("negativeCharCode=" + negativeCharCode);
        System.out.println("constantByte=" + constantByte);
        System.out.println("subtractNegative=" + (10 - -3));
        System.out.println("negativeGroup=" + -(2 + 3));
        System.out.println("signedResult=" + (-3 * 4));
    }
}
~~~

~~~bash
javac UnaryMinusPromotionDemo.java
java UnaryMinusPromotionDemo
~~~

Đầu ra:

~~~text
negativeByte=-7
negativeCharCode=-65
constantByte=-7
subtractNegative=13
negativeGroup=-5
signedResult=-12
~~~

Trong câu lệnh có `10 - -3`, dấu trừ thứ nhất là toán tử hai ngôi, dấu trừ thứ hai là toán tử một ngôi. Dấu cách/ngoặc làm ý định sáng rõ: tránh ghép các dấu `-` mơ hồ thành toán tử tăng/giảm như `--` trong các trường hợp khác.

## 7. Phủ định giá trị nhỏ nhất: tràn số là rủi ro thật

Kiểu `int` không đối xứng quanh 0: phía âm có **thêm một giá trị** (`Integer.MIN_VALUE = -2147483648`). Giá trị dương `2147483648` **không nằm trong miền `int`**. Bởi vậy:

~~~java
int min = Integer.MIN_VALUE;
int stillMin = -min; // tràn int: kết quả vẫn là Integer.MIN_VALUE
~~~

Ví dụ là đoạn minh họa. Phép âm số nguyên primitive **không tự ném exception** khi overflow. Kết quả `-Integer.MIN_VALUE` vẫn là `Integer.MIN_VALUE` do số học bù hai với độ rộng cố định. Tương tự, `-Long.MIN_VALUE` vẫn là `Long.MIN_VALUE`.

Có ba cách xử lý tùy bài toán:

1. **Cần phát hiện tràn:** gọi `Math.negateExact(int)` hoặc `Math.negateExact(long)`; sẽ ném `ArithmeticException` với giá trị nhỏ nhất.
2. **Cần giá trị đối chính xác rộng hơn `int`:** chuyển sang `long` **trước** khi đổi dấu, ví dụ `-(long) Integer.MIN_VALUE` có giá trị `2147483648L`.
3. **Cần giá trị đối chính xác rộng hơn `long`:** dùng `BigInteger.valueOf(Long.MIN_VALUE).negate()`, kết quả vượt miền `long`.

Dù viết `long after = -Integer.MIN_VALUE;`, phép âm vẫn có kiểu `int` và **đã tràn trước khi gán sang long**. Phải viết `long before = -(long) Integer.MIN_VALUE;`. Cũng cần cẩn thận với `Math.abs(Integer.MIN_VALUE)`: kết quả vẫn âm theo hợp đồng API; không coi `abs` là cách luôn chuyển thành số dương được.

### Ví dụ Java 17+ chạy độc lập: xử lý tràn

Tạo tệp `NegationOverflowDemo.java`:

~~~java
import java.math.BigInteger;

public class NegationOverflowDemo {
    public static void main(String[] args) {
        int min = Integer.MIN_VALUE;

        System.out.println("wrapped=" + (-min));
        System.out.println("lateWiden=" + (long) (-min));
        System.out.println("earlyWiden=" + (-(long) min));
        System.out.println("absMin=" + Math.abs(min));

        try {
            Math.negateExact(min);
        } catch (ArithmeticException ex) {
            System.out.println("negateExact=overflow");
        }

        BigInteger exact = BigInteger.valueOf(Long.MIN_VALUE).negate();
        System.out.println("bigInteger=" + exact);
    }
}
~~~

~~~bash
javac NegationOverflowDemo.java
java NegationOverflowDemo
~~~

Đầu ra chính xác:

~~~text
wrapped=-2147483648
lateWiden=-2147483648
earlyWiden=2147483648
absMin=-2147483648
negateExact=overflow
bigInteger=9223372036854775808
~~~

Mấu chốt nằm ở **kiểu của toán hạng tại thời điểm thực hiện toán tử âm**. Mở rộng kiểu sau khi kết quả đã tràn không sửa được phép toán trước đó.

## 8. Dấu âm với số thực và số 0 âm

Với `float` và `double`, phép âm một ngôi hoạt động theo ngữ nghĩa dấu phẩy động IEEE 754 mà Java hỗ trợ. Ví dụ `-1.25` là toán tử âm áp dụng lên literal `double` `1.25`; `-1.25f` áp dụng lên literal `float` `1.25f`. `-1.25e2` cho `-125.0`.

Một điều dễ bỏ qua: **floating-point có cả `+0.0` và `-0.0`**, trong khi kiểu số nguyên `int`/`long` chỉ có một giá trị 0. Vì vậy:

- `0.0 == -0.0` là `true` theo phép so sánh số học.
- `1.0 / 0.0` cho `Infinity`, nhưng `1.0 / -0.0` cho `-Infinity`.
- `-Double.NaN` vẫn là `NaN`; không xem NaN là số có thể so sánh bằng phép `==` thông thường.

Ví dụ Java 17+ độc lập, tạo tệp `FloatingMinusDemo.java`:

~~~java
public class FloatingMinusDemo {
    public static void main(String[] args) {
        double negativeZero = -0.0;

        System.out.println("negativeValue=" + (-1.25e2));
        System.out.println("zeroEqual=" + (0.0 == negativeZero));
        System.out.println("positiveInfinity=" + (1.0 / 0.0));
        System.out.println("negativeInfinity=" + (1.0 / negativeZero));
        System.out.println("negatedNaN=" + Double.isNaN(-Double.NaN));
        System.out.println("integerZero=" + (-0));
    }
}
~~~

~~~bash
javac FloatingMinusDemo.java
java FloatingMinusDemo
~~~

Đầu ra:

~~~text
negativeValue=-125.0
zeroEqual=true
positiveInfinity=Infinity
negativeInfinity=-Infinity
negatedNaN=true
integerZero=0
~~~

Đây là ví dụ cho thấy một dấu `-` đứng trước literal có thể ảnh hưởng tới biểu diễn giá trị và phép toán phía sau. Đừng suy luận rằng “phủ định số 0 luôn không để lại khác biệt” trong tính toán floating-point.

## 9. Khi dùng `BigInteger` và `BigDecimal`

Toán tử `-` một ngôi **không áp dụng trực tiếp cho đối tượng** `BigInteger` hoặc `BigDecimal`. Các lớp này cung cấp phương thức `negate()` và `abs()`.

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

public class BigNumberNegationDemo {
    public static void main(String[] args) {
        BigInteger count = new BigInteger("9223372036854775808");
        BigDecimal money = new BigDecimal("19.90");

        System.out.println("count=" + count.negate());
        System.out.println("money=" + money.negate().toPlainString());
    }
}
~~~

~~~bash
javac BigNumberNegationDemo.java
java BigNumberNegationDemo
~~~

Đầu ra:

~~~text
count=-9223372036854775808
money=-19.90
~~~

Dấu `-` trong chuỗi đầu vào (ví dụ `new BigDecimal("-19.90")`) là **nội dung văn bản được parser của lớp số giải thích**, khác với toán tử `-` của ngôn ngữ Java đứng ngoài biểu thức. `BigInteger.negate()` cho số đối chính xác trong giới hạn tài nguyên; `BigDecimal.negate()` giữ ngữ nghĩa số thập phân, gồm cả scale thích hợp của giá trị gốc.

## 10. Các lỗi nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “`-42` là một token literal duy nhất.” | `-` là unary operator; `42` là decimal integer literal. |
| “Không có `-` thì literal luôn là số dương.” | Literal nhị phân/bát phân/hex có mẫu bit cao bằng 1 có thể biểu diễn giá trị âm, ví dụ `0xFFFF_FFFF` là `-1` với `int`. |
| “`2147483648` không bao giờ xuất hiện trong source Java hợp lệ.” | Nó được dùng **đặc biệt** làm toán hạng cho unary minus trong `-2147483648`. |
| “Gán `-Integer.MIN_VALUE` vào `long` là an toàn.” | Phép âm tính ở `int` trước rồi mới mở rộng; cần cast `(long)` trước phép âm. |
| “`-byteValue` vẫn là `byte`.” | Unary numeric promotion tạo ra `int` với `byte`, `short`, `char`. |
| “`-0` và `-0.0` luôn như nhau.” | Số nguyên có một số 0; floating-point có hai giá trị 0 mang dấu khác nhau. |
| “Có thể dùng `-bigInteger`.” | Dùng `bigInteger.negate()`; toán tử một ngôi chỉ áp dụng trực tiếp cho kiểu số nguyên thủy. |
| “Mã text `"-42"` chứa toán tử unary minus.” | Trong chuỗi chỉ có ký tự; phép parse số là bước riêng. |

## 11. Tự kiểm tra

1. Trong `int a = -15;`, token literal là `-15` hay `15`? Ký hiệu `-` đóng vai trò gì?
2. Vì sao `int min = -2147483648;` hợp lệ, nhưng `int invalid = 2147483648;` không hợp lệ?
3. `0xFFFF_FFFF` là literal không có ký hiệu `-`; tại sao giá trị `int` của nó lại là `-1`?
4. Kiểu của `-small` là gì khi `small` được khai báo `byte`?
5. Vì sao `long x = -Integer.MIN_VALUE;` vẫn cho số âm, trong khi `long y = -(long) Integer.MIN_VALUE;` cho số dương?
6. Tại sao `0.0 == -0.0` là `true` mà phép chia `1.0 / 0.0` khác `1.0 / -0.0`?
7. Khi cần phủ định một số vượt miền `long`, nên chọn phương thức nào của `BigInteger`?

**Gợi ý đáp án:** (1) `15` là literal; `-` là unary minus. (2) Java có ngoại lệ cú pháp cho literal thập phân 2.147.483.648 làm toán hạng của unary minus. (3) Mẫu bit 32 bit toàn 1 tương ứng −1 trong biểu diễn số nguyên bù hai. (4) `int`. (5) Phép âm `int` tràn trước khi mở rộng; phải chuyển sang `long` trước. (6) `double` giữ dấu của zero, ảnh hưởng tới chia cho zero. (7) `BigInteger.negate()`.

**Ghi nhớ:** Trong mã Java, **dấu âm là toán tử của biểu thức, không phải một phần của literal số**. Nắm rõ điều này giúp hiểu thứ tự đánh giá biểu thức, ngữ nghĩa kiểu số, quy tắc ranh giới `Integer.MIN_VALUE`/`Long.MIN_VALUE` và tràn số khi phủ định.