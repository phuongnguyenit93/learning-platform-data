# Trường hợp `MIN_VALUE` chia cho `-1` trong Java

## 1. Kết quả gây bất ngờ

Trong toán học, nếu `a` là số nguyên âm thì `a / -1` là số đối dương của `a`. Nhưng trong Java, **`Integer.MIN_VALUE / -1` vẫn bằng `Integer.MIN_VALUE`**, và **`Long.MIN_VALUE / -1L` vẫn bằng `Long.MIN_VALUE`**.

Đó là một trường hợp đặc biệt của **phép chia số nguyên có dấu**, được Java quy định rõ, không phải hành vi ngẫu nhiên của máy hoặc lỗi do JVM.

~~~java
int intResult = Integer.MIN_VALUE / -1;   // -2147483648
long longResult = Long.MIN_VALUE / -1L;  // -9223372036854775808
~~~

Đoạn trên là mã minh họa; phía dưới có các chương trình đầy đủ để biên dịch và chạy.

**Vì sao?** Giá trị số nguyên nhỏ nhất có độ lớn tuyệt đối lớn hơn số nguyên dương lớn nhất cùng kiểu một đơn vị:

| Kiểu | `MIN_VALUE` | `MAX_VALUE` | Giá trị toán học `MIN_VALUE / -1` |
|---|---:|---:|---:|
| `int` (32 bit) | −2.147.483.648 | 2.147.483.647 | **2.147.483.648** — vượt miền `int` |
| `long` (64 bit) | −9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 | **9.223.372.036.854.775.808** — vượt miền `long` |

Kết quả dương chính xác không thể chứa trong kiểu số nguyên ban đầu. Phép chia thông thường `/` của Java **không báo overflow**: với cặp toán hạng duy nhất gây tràn thương có dấu là `MIN_VALUE` và `-1`, kết quả được quy định bằng chính `MIN_VALUE`.

Điểm phân biệt cốt lõi:

- **Chia cho `0`:** phép chia nguyên phát sinh `ArithmeticException`.
- **Chia `MIN_VALUE` cho `-1`:** **không** phát sinh `ArithmeticException`; kết quả là `MIN_VALUE`.
- **Chia các giá trị nguyên còn lại cho `-1`:** kết quả đúng bằng số đối của giá trị bị chia, nằm trong miền kiểu đích.

## 2. Cơ chế: miền không đối xứng và phép chia nguyên

### 2.1. Tại sao miền số âm rộng hơn phía dương?

Java sử dụng biểu diễn số nguyên có dấu theo dạng **bù hai (*two's complement*)** với độ rộng cố định. Với `int` 32 bit, giá trị nhỏ nhất là `-2^31` và lớn nhất là `2^31 - 1`. Với `long` 64 bit, giá trị nhỏ nhất là `-2^63` và lớn nhất là `2^63 - 1`.

Vì vậy, kiểu `int` có thể lưu `-2147483648` nhưng **không thể** lưu `+2147483648`; kiểu `long` có thể lưu `-9223372036854775808` nhưng **không thể** lưu `+9223372036854775808`. Khi chia giá trị nhỏ nhất cho `-1`, thương toán học thuộc phía dương vượt quá `MAX_VALUE` đúng một đơn vị.

Ở mức bit, giá trị `Integer.MIN_VALUE` có mẫu `0x80000000`, còn `Long.MIN_VALUE` có mẫu `0x8000000000000000L`. Các mẫu này không đổi khi thực hiện phép lấy số đối trong độ rộng tương ứng, do số đối toán học không thể biểu diễn. Java quy định riêng cho phép chia tương ứng để bảo đảm kết quả nhất quán.

### 2.2. Quy tắc chia nguyên thông thường

Với toán hạng thuộc kiểu nguyên, toán tử `/`:

1. Tính thương nguyên và **loại phần lẻ về phía 0** (*truncate toward zero*), không tự làm tròn xuống theo nghĩa toán học.
2. Nếu số chia bằng `0`, ném `ArithmeticException`.
3. Nếu số bị chia là `Integer.MIN_VALUE` và số chia là `-1` trong phép toán kiểu `int`, trả `Integer.MIN_VALUE`. Trường hợp `long` tương ứng trả `Long.MIN_VALUE`.
4. Các phép chia nguyên khác trả kết quả nằm trong miền của kiểu kết quả và không ném lỗi chỉ vì kết quả có dấu âm.

Ví dụ:

| Phép tính kiểu `int` | Kết quả `/` | Giải thích |
|---|---:|---|
| `7 / 3` | `2` | Bỏ phần dư |
| `-7 / 3` | `-2` | Làm tròn về 0 |
| `7 / -3` | `-2` | Làm tròn về 0 |
| `-7 / -3` | `2` | Làm tròn về 0 |
| `Integer.MIN_VALUE / 1` | `Integer.MIN_VALUE` | Vẫn nằm trong miền |
| `Integer.MIN_VALUE / -1` | `Integer.MIN_VALUE` | **Tràn thương đặc biệt, không ném lỗi** |

**Lưu ý về kiểu:** Khi chia hai biến `byte`, `short` hoặc `char`, Java nâng toán hạng lên `int` theo *binary numeric promotion*. Các giá trị kiểu nhỏ được mở rộng rồi thực hiện chia trong `int`, nên **trường hợp tràn `MIN_VALUE / -1` chỉ đáng xét đối với phép chia mang kiểu tính toán `int` hoặc `long`**. Một biến `short` bằng `Short.MIN_VALUE` chia cho `-1` có thương `32768` hợp lệ trong `int`; gán kết quả ngược về `short` sẽ cần kiểm tra/ép kiểu riêng.

### 2.3. Không cần dấu âm đứng trong literal

`-1` trong biểu thức Java là toán tử âm một ngôi áp dụng lên literal `1`. Còn `Integer.MIN_VALUE` là hằng số `int` bằng `-2147483648`. Kết quả phép chia được xác định dựa trên **giá trị và kiểu toán hạng**, bất kể giá trị `-1` được tạo từ literal, biến, hoặc phương thức:

~~~java
int min = Integer.MIN_VALUE;
int divisor = -1;
int quotient = min / divisor; // Integer.MIN_VALUE
~~~

Đây là một đoạn minh họa; tình huống không thay đổi khi thay `divisor` bằng tham số truyền từ ngoài vào. Chính vì kết quả không ném exception, một phép chia như vậy có thể đi qua các nhánh xử lý thông thường mà ứng dụng không nhận ra overflow.

## 3. Chương trình Java 17+ minh họa trực tiếp

Tạo tệp `MinValueDivisionDemo.java`:

~~~java
public class MinValueDivisionDemo {
    public static void main(String[] args) {
        int minInt = Integer.MIN_VALUE;
        long minLong = Long.MIN_VALUE;

        System.out.println("intMin=" + minInt);
        System.out.println("intDiv=" + (minInt / -1));
        System.out.println("longMin=" + minLong);
        System.out.println("longDiv=" + (minLong / -1L));
        System.out.println("intRem=" + (minInt % -1));
        System.out.println("longRem=" + (minLong % -1L));
        System.out.println("normal=" + (-7 / 3));
        System.out.println("exactPositive=" + ((long) minInt / -1L));
    }
}
~~~

Dùng JDK 17 trở lên, chạy trong thư mục chứa tệp:

~~~bash
javac MinValueDivisionDemo.java
java MinValueDivisionDemo
~~~

Đầu ra:

~~~text
intMin=-2147483648
intDiv=-2147483648
longMin=-9223372036854775808
longDiv=-9223372036854775808
intRem=0
longRem=0
normal=-2
exactPositive=2147483648
~~~

Các dòng `intDiv` và `longDiv` thể hiện chính xác trường hợp ngoại lệ về **giá trị kết quả**. Hai dòng `intRem` và `longRem` cho biết phần dư là 0; một phần dư bằng 0 **không chứng minh thương không bị tràn**. Dòng `exactPositive` cho thấy mở rộng `int` sang `long` **trước khi chia** sẽ nhận thương chính xác 2.147.483.648.

## 4. Phần dư `%` và quan hệ với phép chia

Trong Java, phép chia lấy dư nguyên `a % b` có cùng trường hợp chia cho 0 gây `ArithmeticException`, nhưng:

~~~java
Integer.MIN_VALUE % -1  // 0
Long.MIN_VALUE % -1L    // 0L
~~~

Đó là kết quả **được quy định**, không phải dấu hiệu cho thấy phép chia an toàn. Với các phép chia không phải chia cho 0, số dư thỏa quan hệ:

`a == (a / b) * b + (a % b)`

Khi `a = Integer.MIN_VALUE` và `b = -1`, biểu thức này vẫn đúng theo **số học `int` có tràn**: thương mang giá trị `Integer.MIN_VALUE`; nhân thương với `-1` cũng tràn trở lại `Integer.MIN_VALUE`; cộng phần dư 0 không đổi. Không thể dùng quan hệ này mà tính bằng cùng kiểu `int` để phát hiện overflow.

Ngoài ra, dấu của số dư `%` trong Java đi theo số bị chia (*dividend*) hoặc bằng 0. Ví dụ `-7 % 3` bằng `-1`, đi cùng `-7 / 3` bằng `-2`. Đây là phần của phép chia làm tròn về 0, khác một số định nghĩa phép modulo trong toán học.

### Phân biệt `Math.floorDiv` và `/`

`Math.floorDiv(a, b)` làm tròn thương **về âm vô cùng** (*floor*), nên `Math.floorDiv(-7, 3)` bằng `-3` trong khi `-7 / 3` bằng `-2`. Nhưng `Math.floorDiv` **không loại bỏ trường hợp tràn**:

~~~java
Math.floorDiv(Integer.MIN_VALUE, -1) // Integer.MIN_VALUE
Math.floorMod(Integer.MIN_VALUE, -1) // 0
~~~

Vì vậy, dùng `Math.floorDiv` để thay đổi cách làm tròn là hợp lý khi bài toán cần quy tắc đó, **nhưng không được coi nó là phép chia có kiểm tra overflow**.

## 5. Vì sao đổi kiểu *sau* khi chia không giúp được?

Sự khác biệt giữa hai biểu thức sau là **thời điểm mở rộng kiểu**:

~~~java
int min = Integer.MIN_VALUE;

long tooLate = (long) (min / -1);
long safeForIntMin = ((long) min) / -1;
~~~

- `tooLate`: `min / -1` chạy trong kiểu `int` và trả `-2147483648`; sau đó cast sang `long` chỉ giữ lại kết quả đã tràn.
- `safeForIntMin`: `min` được chuyển thành `long` **trước phép chia**; `2147483648` nằm trong miền `long`, nên phép chia trả thương dương chính xác.

### Trường hợp `Long.MIN_VALUE`

Không tồn tại kiểu nguyên thủy Java nào rộng hơn `long`. Vì vậy, ép kiểu trong họ integer primitive không thể biểu diễn chính xác `Long.MIN_VALUE / -1L`. Khi thật sự cần thương toán học dương 9.223.372.036.854.775.808, dùng `BigInteger`:

~~~java
BigInteger exact = BigInteger.valueOf(Long.MIN_VALUE)
        .divide(BigInteger.valueOf(-1));
~~~

Đây là **đoạn minh họa**, giả sử đã import `java.math.BigInteger`. Trong `BigInteger`, kết quả không giới hạn ở 64 bit cố định (nhưng vẫn bị giới hạn bởi bộ nhớ và tài nguyên). Nếu hệ thống cuối cùng bắt buộc trả về `long`, phải thông báo lỗi hoặc có chính sách riêng; không thể nhét thương đó vào `long` mà giữ chính xác.

## 6. Phát hiện overflow thay vì nhận kết quả bị cuốn vòng

Khi API có yêu cầu phép chia **phải chính xác trong kiểu `int`**, hãy kiểm tra hai điều kiện trước khi dùng `/`:

1. Số chia `divisor == 0`: không có phép chia nguyên hợp lệ.
2. `dividend == Integer.MIN_VALUE && divisor == -1`: thương toán học không nằm trong miền `int`.

Với `long`, thay `Integer.MIN_VALUE` bằng `Long.MIN_VALUE` và dùng toán hạng `long`. Kiểm tra này bao phủ trường hợp thương chia nguyên vượt miền, vì chia một số nguyên cho trị tuyệt đối của số chia từ 1 trở lên không làm tăng trị tuyệt đối của số bị chia, ngoại trừ phép đổi dấu đối với `MIN_VALUE / -1`.

### Ví dụ độc lập: phép chia có kiểm tra

Tạo tệp `CheckedDivisionDemo.java`:

~~~java
public class CheckedDivisionDemo {
    public static int divideInt(int dividend, int divisor) {
        if (divisor == 0) {
            throw new ArithmeticException("division by zero");
        }
        if (dividend == Integer.MIN_VALUE && divisor == -1) {
            throw new ArithmeticException("int quotient overflow");
        }
        return dividend / divisor;
    }

    public static long divideLong(long dividend, long divisor) {
        if (divisor == 0L) {
            throw new ArithmeticException("division by zero");
        }
        if (dividend == Long.MIN_VALUE && divisor == -1L) {
            throw new ArithmeticException("long quotient overflow");
        }
        return dividend / divisor;
    }

    public static void main(String[] args) {
        System.out.println("12 / -3=" + divideInt(12, -3));
        System.out.println("-7 / 3=" + divideInt(-7, 3));

        try {
            divideInt(Integer.MIN_VALUE, -1);
        } catch (ArithmeticException ex) {
            System.out.println("intOverflow=" + ex.getMessage());
        }

        try {
            divideLong(Long.MIN_VALUE, -1L);
        } catch (ArithmeticException ex) {
            System.out.println("longOverflow=" + ex.getMessage());
        }

        try {
            divideInt(10, 0);
        } catch (ArithmeticException ex) {
            System.out.println("zeroDivisor=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac CheckedDivisionDemo.java
java CheckedDivisionDemo
~~~

Đầu ra:

~~~text
12 / -3=-4
-7 / 3=-2
intOverflow=int quotient overflow
longOverflow=long quotient overflow
zeroDivisor=division by zero
~~~

Phép kiểm tra tập trung ở **ranh giới thao tác số học**, giúp người gọi phân biệt phép chia cho 0 với overflow. Các thông điệp lỗi được đặt tường minh trong chương trình để đầu ra ổn định; không nên dựa vào chuỗi `ArithmeticException` mặc định của một JVM cụ thể để làm hợp đồng dữ liệu.

**Đừng dùng `Math.abs(divisor)` như cách kiểm tra duy nhất**: `Math.abs(Integer.MIN_VALUE)` cũng nhận kết quả âm `Integer.MIN_VALUE`, vì trị tuyệt đối dương vượt miền `int`. Tương tự, `Math.negateExact(Integer.MIN_VALUE)` có thể phát hiện việc phủ định vượt miền, nhưng gọi phủ định để thay cho phép chia với mọi loại số chia là không cần thiết; hãy kiểm tra chính xác điều kiện phép chia.

## 7. Khi cần phép chia chính xác bằng `BigInteger`

Nếu yêu cầu giữ lại thương toán học của phép chia `MIN_VALUE / -1`, chọn một kiểu đủ rộng **trước phép chia**:

- Với `int`: sử dụng `long` là đủ cho thương dương 2.147.483.648.
- Với `long`: sử dụng `BigInteger` để có thương dương 9.223.372.036.854.775.808.

Tạo tệp `ExactMinDivisionDemo.java`:

~~~java
import java.math.BigInteger;

public class ExactMinDivisionDemo {
    public static void main(String[] args) {
        int minInt = Integer.MIN_VALUE;
        long wideQuotient = ((long) minInt) / -1L;

        BigInteger minLong = BigInteger.valueOf(Long.MIN_VALUE);
        BigInteger exactQuotient =
                minLong.divide(BigInteger.valueOf(-1));

        System.out.println("wideIntQuotient=" + wideQuotient);
        System.out.println("exactLongQuotient=" + exactQuotient);

        try {
            System.out.println("asLong=" + exactQuotient.longValueExact());
        } catch (ArithmeticException ex) {
            System.out.println("asLong=out of range");
        }

        System.out.println("bigRemainder="
                + minLong.remainder(BigInteger.valueOf(-1)));
    }
}
~~~

~~~bash
javac ExactMinDivisionDemo.java
java ExactMinDivisionDemo
~~~

Đầu ra:

~~~text
wideIntQuotient=2147483648
exactLongQuotient=9223372036854775808
asLong=out of range
bigRemainder=0
~~~

`BigInteger.longValueExact()` ném `ArithmeticException` khi giá trị không còn vừa `long`. So với `longValue()` có thể cắt mất bit cao, phiên bản `Exact` phù hợp khi **mất thông tin không được phép**. Phép chia `BigInteger.divide` với các toán hạng nguyên sử dụng thương làm tròn về 0, tương ứng với cách làm tròn chia nguyên của Java trong những trường hợp thương có thể biểu diễn.

## 8. Hệ quả với logic nghiệp vụ và an toàn dữ liệu

Dù hiếm gặp, `MIN_VALUE / -1` đáng chú ý khi đầu vào là số nguyên bất kỳ do người dùng hoặc dịch vụ khác gửi tới. Nếu một phép chia xuất hiện trong tính toán giới hạn, quota, phân chia khối lượng, bộ đếm hoặc kiểm tra ngưỡng, **giá trị đáng lẽ dương nhưng lại âm** có thể làm sai nhánh điều kiện.

Ví dụ giả định:

~~~java
int quotient = amount / divisor;
if (quotient >= 0) {
    // Xử lý cho trường hợp không âm
}
~~~

Đây là **đoạn minh họa**. Nếu `amount == Integer.MIN_VALUE` và `divisor == -1`, nhánh trên sẽ không chạy, mặc dù thương toán học là số dương. Một kiểm tra `divisor != 0` là cần thiết nhưng **chưa đủ** để bảo đảm thương biểu diễn chính xác.

Khi thiết kế xử lý:

- Nếu API cho phép kết quả `int`/`long` cố định: kiểm tra và thông báo overflow trước khi chia.
- Nếu phép toán phải chính xác với mọi đầu vào trong miền `int`: nâng lên `long` trước khi chia (và quyết định kiểu kết quả trả ra).
- Nếu phải chính xác với mọi đầu vào trong miền `long`: sử dụng `BigInteger` cho phép tính/kết quả phù hợp.
- Nếu quy tắc làm tròn về âm vô cùng quan trọng: `Math.floorDiv` giải quyết **cách làm tròn**, nhưng vẫn cần kiểm tra riêng trường hợp tràn.

Khi viết test, kiểm tra **biên**, không chỉ các số đẹp: `MIN_VALUE / 1`, `MIN_VALUE / -1`, `MIN_VALUE % -1`, `MAX_VALUE / -1`, `0 / -1`, số chia `0` và một phép chia âm có phần dư như `-7 / 3`.

## 9. Những nhầm lẫn thường gặp

| Phát biểu | Đánh giá | Giải thích |
|---|---|---|
| “Chia `MIN_VALUE` cho `-1` sẽ ném `ArithmeticException`.” | Sai | Phép chia nguyên `/` trả `MIN_VALUE` theo đặc tả. |
| “`MIN_VALUE / -1` cho `MAX_VALUE`.” | Sai | Kết quả là **`MIN_VALUE`**, không phải giá trị dương lớn nhất. |
| “Phần dư bằng 0 có nghĩa phép chia không overflow.” | Sai | `MIN_VALUE % -1` bằng 0 dù thương tràn. |
| “Ép kết quả phép chia từ `int` sang `long` sẽ sửa overflow.” | Sai | Cần mở rộng **trước khi tính**. |
| “`Math.floorDiv` tự phát hiện tràn thương.” | Sai | Nó thay quy tắc làm tròn, không kiểm tra biên `MIN_VALUE / -1`. |
| “`BigInteger` bị tràn như `long` khi chia.” | Sai | Không bị giới hạn bởi độ rộng 64 bit; bị giới hạn bởi tài nguyên thực tế. |
| “Bảo vệ phép chia cho 0 là đủ để tính toán an toàn.” | Sai | Còn phải kiểm tra thương vượt miền nếu bài toán yêu cầu tính chính xác. |

## 10. Câu hỏi tự kiểm tra

1. Vì sao phép chia `Integer.MIN_VALUE / -1` có thương toán học không thể biểu diễn bằng `int`?
2. Java thực sự trả giá trị gì khi thực hiện phép chia đó? Có ném exception không?
3. `Long.MIN_VALUE / -1L` có cùng vấn đề không? Cần kiểu nào để biểu diễn thương dương chính xác?
4. Kết quả `Integer.MIN_VALUE % -1` bằng bao nhiêu? Có thể xem phép `%` là cơ chế phát hiện overflow không?
5. Hai biểu thức `(long) (Integer.MIN_VALUE / -1)` và `((long) Integer.MIN_VALUE) / -1` khác gì nhau?
6. `Math.floorDiv(-7, 3)` khác `-7 / 3` như thế nào? `Math.floorDiv(Integer.MIN_VALUE, -1)` có tự tránh overflow không?
7. Viết điều kiện tối thiểu để phép chia `int x / int y` trả thương chính xác hoặc phát sinh lỗi, không bao giờ âm thầm cuốn vòng ở biên.

**Đáp án gợi ý:** (1) Miền `int` không đối xứng, thiếu số dương `2147483648`. (2) Trả `Integer.MIN_VALUE`, không ném exception. (3) Có; dùng `BigInteger` nếu cần thương chính xác. (4) `0`; không. (5) Biểu thức thứ nhất tràn trước khi cast, biểu thức thứ hai được nâng lên `long` trước phép chia. (6) `-3` so với `-2`; `floorDiv` vẫn trả `MIN_VALUE` ở biên. (7) Kiểm tra `y == 0` và `x == Integer.MIN_VALUE && y == -1` trước khi dùng `x / y`.

**Ghi nhớ:** Trong phép chia số nguyên có dấu của Java, **`MIN_VALUE / -1` là trường hợp thương toán học vượt miền nhưng toán tử `/` vẫn trả chính `MIN_VALUE`**. Nếu kết quả phải chính xác, hãy **kiểm tra overflow hoặc mở rộng kiểu trước phép tính**; chia cho 0 là lỗi riêng biệt.