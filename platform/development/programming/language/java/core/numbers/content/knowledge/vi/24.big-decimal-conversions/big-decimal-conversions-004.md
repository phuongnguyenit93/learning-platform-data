# `BigDecimal.intValue()`, `longValue()` và phần dữ liệu có thể mất

## 1. Vì sao cần hiểu kỹ chuyển đổi từ BigDecimal sang số nguyên?

`BigDecimal` biểu diễn các số thập phân với độ chính xác tùy ý, trong khi `int` chỉ chứa được số nguyên có dấu 32 bit và `long` chỉ chứa được số nguyên có dấu 64 bit. Khi viết:

~~~java
BigDecimal value = new BigDecimal("123.99");

int a = value.intValue();   // 123
long b = value.longValue(); // 123
~~~

Java **không báo lỗi** dù phần `.99` đã biến mất. Hai phương thức này thực hiện **chuyển đổi thu hẹp có thể mất dữ liệu**, không phải phép làm tròn theo một quy tắc tài chính.

Thậm chí phần nguyên cũng có thể mất nếu nằm ngoài phạm vi kiểu đích:

~~~java
new BigDecimal("2147483648").intValue()  // -2147483648
new BigDecimal("4294967296").intValue()  // 0
~~~

Điều cần ghi nhớ:

- `intValue()` và `longValue()` **loại bỏ phần thập phân theo hướng về 0**; sau đó giới hạn vào số bit của kiểu đích. Chúng **không kiểm tra mất mát dữ liệu**.
- `intValueExact()` và `longValueExact()` **chỉ trả kết quả nếu giá trị là số nguyên chính xác và nằm trong phạm vi kiểu đích**; nếu không, chúng ném `ArithmeticException`.
- Nếu nghiệp vụ cho phép làm tròn, hãy **chọn rõ `RoundingMode` và làm tròn trước**, rồi dùng phương thức `...ValueExact()` để kiểm tra giới hạn.
- Việc chương trình biên dịch hoặc trả được `int`/`long` không chứng minh phép chuyển đổi đã giữ đúng giá trị ban đầu.

## 2. Hai nguồn mất dữ liệu độc lập

### 2.1. Mất phần thập phân: cắt về 0, không làm tròn

`intValue()` và `longValue()` bỏ phần không nguyên. Chúng chỉ giữ phần nguyên gần 0 nhất:

| BigDecimal đầu vào | `intValue()` | `longValue()` | Điều bị mất |
| --- | ---: | ---: | --- |
| `123.999` | `123` | `123` | `0.999` |
| `-123.999` | `-123` | `-123` | `-0.999` |
| `0.999` | `0` | `0` | Toàn bộ giá trị khác 0 |
| `-0.999` | `0` | `0` | Toàn bộ giá trị khác 0 |
| `1.000` | `1` | `1` | Không mất **giá trị số**; chỉ không giữ lại scale 3 |

Ví dụ, `new BigDecimal("-2.9").intValue()` là `-2`. Đây **không** phải `Math.floor(-2.9)` (kết quả `-3.0`), cũng **không** phải làm tròn đến số nguyên gần nhất. Chữ “truncate” là **loại bỏ phần thập phân về 0**.

`intValue()` và `longValue()` không nhận `RoundingMode`. Các mode như `HALF_UP`, `HALF_EVEN`, `DOWN`, `FLOOR` chỉ có tác dụng nếu bạn chủ động dùng API làm tròn như `setScale`.

### 2.2. Mất bit ở phần nguyên: số có thể đổi dấu hoặc thành 0

Phạm vi Java của hai kiểu:

| Kiểu | Số bit | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: | ---: |
| `int` | 32 | `-2147483648` | `2147483647` |
| `long` | 64 | `-9223372036854775808` | `9223372036854775807` |

Sau khi loại bỏ phần thập phân, nếu phần nguyên quá lớn hoặc quá nhỏ:

- `intValue()` giữ **32 bit thấp** của phần nguyên theo biểu diễn hai bù, rồi diễn giải kết quả thành `int` có dấu.
- `longValue()` giữ **64 bit thấp** và diễn giải thành `long` có dấu.
- Không có ngoại lệ chỉ vì vượt phạm vi; giá trị nhận được có thể hoàn toàn khác số ban đầu.

Ví dụ:

| Giá trị BigDecimal | `intValue()` | `longValue()` | Giải thích |
| --- | ---: | ---: | --- |
| `2147483647` | `2147483647` | `2147483647` | Trong phạm vi cả hai |
| `2147483648` | `-2147483648` | `2147483648` | Vượt `int`, nhưng vừa `long` |
| `4294967296` (= 2^32) | `0` | `4294967296` | 32 bit thấp đều bằng 0 |
| `9223372036854775807` | `-1` | `9223372036854775807` | Vừa `long`; 32 bit thấp bằng tất cả bit 1 |
| `9223372036854775808` (= 2^63) | `0` | `-9223372036854775808` | Vượt `long`, bit dấu bị diễn giải thành âm |
| `18446744073709551616` (= 2^64) | `0` | `0` | 64 bit thấp đều bằng 0 |

Ở đây nói “giữ bit thấp” là mô tả **kết quả theo đặc tả chuyển đổi**; không nên dựa vào một giả định về cấu trúc bộ nhớ bên trong `BigDecimal`.

Ví dụ `4294967296` thành `0` vì `4294967296 = 2^32`: khi chỉ giữ phần dư theo `2^32`, kết quả là 0. Số âm cũng có thể biến thành số dương: `new BigDecimal("-2147483649").intValue()` cho `2147483647`.

**Cắt phần thập phân và mất bit có thể xảy ra cùng lúc.** Một số như `4294967296.75` có thể mất `.75` trước, rồi chuyển phần nguyên `4294967296` thành `0` nếu dùng `intValue()`.

## 3. Hai phương thức an toàn hơn: intValueExact và longValueExact

API `BigDecimal` cung cấp:

~~~java
int exactInt = value.intValueExact();
long exactLong = value.longValueExact();
~~~

Chúng đòi hỏi **đồng thời cả hai điều kiện**:

1. **Giá trị toán học phải là số nguyên chính xác**: không được bỏ một phần thập phân khác 0.
2. **Giá trị nguyên phải nằm trong phạm vi** của `int` hoặc `long`.

Nếu bất kỳ điều kiện nào không đạt, `ArithmeticException` được ném. Không phải phép toán nào cũng thất bại chỉ vì `scale() > 0`:

~~~java
new BigDecimal("1.000").intValueExact(); // 1: phần lẻ có giá trị 0
new BigDecimal("1.001").intValueExact(); // ArithmeticException
~~~

`1.000` có scale 3, nhưng giá trị toán học là số nguyên 1. Vì vậy **đừng chỉ nhìn số chữ số sau dấu thập phân** để quyết định có thể chuyển chính xác hay không.

Bảng lựa chọn:

| Dữ liệu đầu vào | `intValueExact()` | `longValueExact()` |
| --- | --- | --- |
| `123` | `123` | `123` |
| `1.000` | `1` | `1` |
| `123.999` | `ArithmeticException` | `ArithmeticException` |
| `2147483648` | `ArithmeticException` | `2147483648` |
| `9223372036854775807` | `ArithmeticException` | `9223372036854775807` |
| `9223372036854775808` | `ArithmeticException` | `ArithmeticException` |

Nếu cần xử lý lỗi rõ ràng trong ứng dụng:

~~~java
BigDecimal input = new BigDecimal("123.99");

try {
    long converted = input.longValueExact();
    System.out.println(converted);
} catch (ArithmeticException ex) {
    System.out.println("Giá trị có phần lẻ hoặc vượt phạm vi long");
}
~~~

Đoạn mã này nằm trong một phương thức hoặc block thích hợp có import `java.math.BigDecimal`; đầu ra sẽ là dòng thông báo trong `catch`. Thông điệp exception cụ thể của JDK không nên dùng làm điều kiện nghiệp vụ, vì có thể khác nhau theo tình huống hoặc phiên bản.

## 4. Chương trình Java 17+ minh họa đầy đủ

Tạo file **`BigDecimalIntegerConversionDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalIntegerConversionDemo {
    public static void main(String[] args) {
        String[] samples = {
                "123.999",
                "-123.999",
                "2147483648",
                "4294967296",
                "9223372036854775808",
                "18446744073709551616",
                "1.000",
                "1.001"
        };

        for (String input : samples) {
            BigDecimal value = new BigDecimal(input);
            System.out.println(input
                    + " | int=" + value.intValue()
                    + " | long=" + value.longValue()
                    + " | intExact=" + exactInt(value)
                    + " | longExact=" + exactLong(value));
        }

        BigDecimal amount = new BigDecimal("12.75");
        System.out.println("truncate: " + amount.intValue());
        System.out.println("HALF_UP: "
                + amount.setScale(0, RoundingMode.HALF_UP).intValueExact());

        BigDecimal negative = new BigDecimal("-12.75");
        System.out.println("negative HALF_UP: "
                + negative.setScale(0, RoundingMode.HALF_UP).intValueExact());

        System.out.println("BigInteger trunc: "
                + new BigDecimal("1.999").toBigInteger());
    }

    private static String exactInt(BigDecimal value) {
        try {
            return Integer.toString(value.intValueExact());
        } catch (ArithmeticException ex) {
            return "ArithmeticException";
        }
    }

    private static String exactLong(BigDecimal value) {
        try {
            return Long.toString(value.longValueExact());
        } catch (ArithmeticException ex) {
            return "ArithmeticException";
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BigDecimalIntegerConversionDemo.java
java BigDecimalIntegerConversionDemo
~~~

Kết quả:

~~~text
123.999 | int=123 | long=123 | intExact=ArithmeticException | longExact=ArithmeticException
-123.999 | int=-123 | long=-123 | intExact=ArithmeticException | longExact=ArithmeticException
2147483648 | int=-2147483648 | long=2147483648 | intExact=ArithmeticException | longExact=2147483648
4294967296 | int=0 | long=4294967296 | intExact=ArithmeticException | longExact=4294967296
9223372036854775808 | int=0 | long=-9223372036854775808 | intExact=ArithmeticException | longExact=ArithmeticException
18446744073709551616 | int=0 | long=0 | intExact=ArithmeticException | longExact=ArithmeticException
1.000 | int=1 | long=1 | intExact=1 | longExact=1
1.001 | int=1 | long=1 | intExact=ArithmeticException | longExact=ArithmeticException
truncate: 12
HALF_UP: 13
negative HALF_UP: -13
BigInteger trunc: 1
~~~

**Cách đọc kết quả:** Cột `int` và `long` luôn hiển thị một giá trị nguyên, kể cả khi sai lệch nghiêm trọng. Hai cột `intExact` và `longExact` giúp nhìn rõ trường hợp nào không thể chuyển chính xác. `2147483648` là phép thử đặc biệt hữu ích: `intValue()` đổi thành số âm, `intValueExact()` báo lỗi, còn `longValueExact()` thành công vì vẫn vừa phạm vi 64 bit.

Đoạn chương trình bắt riêng `ArithmeticException` trong phương thức trợ giúp để minh họa toàn bộ các trường hợp trên một lần chạy. Trong mã nghiệp vụ, thường nên **để lỗi lan lên tầng kiểm tra dữ liệu** hoặc biến thành lỗi xác thực có thông tin đầu vào phù hợp, thay vì âm thầm trả giá trị mặc định.

## 5. Nếu nghiệp vụ thật sự cần làm tròn hoặc cắt bỏ phần lẻ

Chọn chính sách theo yêu cầu, sau đó tách rõ **bước xử lý phần thập phân** và **bước kiểm tra phạm vi số nguyên**.

### 5.1. Làm tròn theo quy tắc đã định

~~~java
BigDecimal amount = new BigDecimal("12.75");

int halfUp = amount
        .setScale(0, RoundingMode.HALF_UP)
        .intValueExact(); // 13
~~~

`setScale(0, HALF_UP)` là một lựa chọn nghiệp vụ: làm tròn đến số nguyên gần nhất và khi đúng nửa thì đi xa số 0. Khi đã tạo giá trị nguyên bằng phép làm tròn chủ động, `intValueExact()` tiếp tục bảo đảm nó nằm trong phạm vi `int`.

Không nên làm như sau nếu mục tiêu là tính số nguyên sau khi làm tròn:

~~~java
int wrongForRounding = new BigDecimal("12.75").intValue(); // 12, không phải 13
~~~

Ví dụ các mode cho `-12.75` khi scale 0:

| Mode | Kết quả |
| --- | ---: |
| `DOWN` | `-12` |
| `UP` | `-13` |
| `HALF_UP` | `-13` |
| `HALF_EVEN` | `-13` |
| `CEILING` | `-12` |
| `FLOOR` | `-13` |

Ở giá trị `-12.75`, nhiều mode tình cờ trả cùng số. Để phân biệt các mode tại điểm đúng nửa, thử cả `2.5` và `-2.5`. Ví dụ `HALF_EVEN` làm tròn `2.5` thành `2`, còn `HALF_UP` thành `3`.

### 5.2. Nếu cắt về 0 là quyết định có chủ ý, vẫn kiểm tra tràn

~~~java
BigDecimal quantity = new BigDecimal("-12.75");

long truncatedChecked = quantity
        .setScale(0, RoundingMode.DOWN)
        .longValueExact(); // -12
~~~

`RoundingMode.DOWN` có nghĩa là đi **về 0**, không phải luôn giảm giá trị. Kết quả làm tròn tới scale 0 được biểu diễn thành số nguyên, rồi `longValueExact()` kiểm tra phạm vi.

Cách này thích hợp khi bạn muốn giữ đúng chính sách bỏ phần thập phân **nhưng không chấp nhận chuyển sai vì tràn 64 bit**. Nếu muốn **cấm mọi phần lẻ khác 0**, không dùng `DOWN`: hãy gọi trực tiếp `longValueExact()`.

### 5.3. Với số nguyên lớn hơn long: dùng BigInteger

Nếu bài toán thật sự cần một số nguyên có thể lớn hơn `Long.MAX_VALUE`, đừng ép về `long`:

~~~java
BigDecimal huge = new BigDecimal("9223372036854775808");

java.math.BigInteger whole = huge.toBigIntegerExact();
// 9223372036854775808, không mất dữ liệu.
~~~

Phân biệt:

- `toBigInteger()`: bỏ phần lẻ (nếu có), không áp giới hạn 32/64 bit.
- `toBigIntegerExact()`: **từ chối** phần lẻ khác 0 bằng `ArithmeticException`, vẫn không giới hạn 32/64 bit như hai kiểu nguyên primitive.
- `toBigInteger().intValue()`: sau cùng vẫn **có thể mất các bit cao**. Đổi sang `BigInteger` không tự làm cho mọi phép ép về `int`/`long` trở nên an toàn.

Với dữ liệu đếm, kích thước, hoặc ID vốn phải là số nguyên, một lựa chọn khác là xử lý chuỗi đầu vào bằng `Integer.parseInt`, `Long.parseLong` hoặc `new BigInteger(text)`, theo đúng phạm vi và định dạng đầu vào. Không nhất thiết phải đi vòng qua `BigDecimal` nếu nghiệp vụ không chấp nhận số thập phân ngay từ đầu.

## 6. Giá trị hiển thị, precision, scale và chuyển đổi sang kiểu nguyên

Một `BigDecimal` có **precision** (số chữ số có nghĩa) và **scale** (số chữ số thập phân theo biểu diễn). `intValue()` và `longValue()` không chuyển hai thuộc tính đó thành kiểu nguyên; kết quả chỉ còn một số nguyên primitive.

Ví dụ:

~~~java
BigDecimal input = new BigDecimal("00123.4500");

System.out.println(input);          // 123.4500
System.out.println(input.scale());  // 4
System.out.println(input.intValue()); // 123
~~~

Dù nhập `00123.4500`, đối tượng `BigDecimal` không còn giữ các số 0 đứng trước trong cách `toString()` chuẩn. Sau khi gọi `intValue()`, chữ số lẻ `.4500` cũng mất. Không thể đảo ngược từ `123` để biết giá trị gốc từng là `123.45`, `123.99` hay `123.000`.

Đặc biệt:

~~~java
new BigDecimal("1.000").intValueExact(); // thành công: 1
new BigDecimal("1.001").intValueExact(); // lỗi: còn phần lẻ khác 0
~~~

Làm tròn khi tạo `BigDecimal` bằng `MathContext` cũng có thể **mất dữ liệu trước** khi gọi `intValueExact()`. Ví dụ nếu đầu vào `1.001` bị làm tròn thành `1.0` ở bước trước thì phương thức Exact ở bước sau chỉ biết kiểm tra giá trị **đang có**, không thể phát hiện phần lẻ đã bị loại. Do đó hãy kiểm tra tính hợp lệ trước bước làm tròn ngoài ý muốn.

## 7. Các lỗi phổ biến trong ứng dụng

**Sai lầm 1 — Đổi giá tiền sang `int` bằng `intValue()` rồi tưởng đã làm tròn.** Với `12.75`, kết quả là `12`, có thể gây sai lệch khi thống kê hoặc hạch toán. Định nghĩa rõ đơn vị (đồng, cent, hay đơn vị nhỏ nhất), chính sách làm tròn và thời điểm làm tròn. Nếu cần biểu diễn tiền theo đơn vị nhỏ nhất bằng số nguyên, hãy nhân theo đúng hệ số, làm tròn theo hợp đồng rồi dùng `longValueExact()` để kiểm tra.

**Sai lầm 2 — Kiểm tra `BigDecimal` không âm rồi tin phép chuyển sang `int` cũng không âm.** `2147483648` là số dương nhưng `intValue()` thành số âm do tràn phạm vi. Đối với dữ liệu không thể mất như ID hoặc giới hạn tài nguyên, dùng chuyển đổi Exact và kiểm tra miền hợp lệ của nghiệp vụ.

**Sai lầm 3 — Chỉ kiểm tra giá trị ≤ `Integer.MAX_VALUE`.** Ngoài giới hạn trên còn có giới hạn dưới và phần thập phân. Kiểm tra tay cũng dễ bỏ sót lỗi; `intValueExact()` giải quyết cả hai điều kiện cốt lõi.

**Sai lầm 4 — Tưởng `longValue()` an toàn vì `long` rất rộng.** Một `BigDecimal` vẫn có thể vượt 64 bit; `9223372036854775808` chuyển sang `long` thành `Long.MIN_VALUE`.

**Sai lầm 5 — Bắt mọi `ArithmeticException` rồi trả `0`.** `0` có thể là giá trị hợp lệ và che giấu trường hợp dữ liệu bị lỗi. Hãy phân biệt dữ liệu không nguyên hoặc ngoài miền theo yêu cầu nghiệp vụ và giữ thông tin lỗi hữu ích.

**Sai lầm 6 — Dùng `setScale(0, DOWN)` khi yêu cầu là không cho phép phần lẻ.** `DOWN` cố tình cắt phần lẻ; dùng `intValueExact()` hoặc `longValueExact()` trực tiếp nếu phần lẻ phải bị từ chối.

**Sai lầm 7 — Cho rằng chuyển từ `double` sang `BigDecimal` khôi phục giá trị gốc.** `new BigDecimal(double)` phản ánh chính xác giá trị nhị phân của `double`, có thể khác con số thập phân người dùng dự định. Khi đầu vào là văn bản decimal, ưu tiên parse từ chuỗi chính xác; đừng bỏ qua nguồn dữ liệu trước khi chọn phương thức chuyển kiểu.

**Sai lầm 8 — Dùng `longValue()` để kiểm tra số có vừa long không.** Phương thức này **luôn trả về một `long`** với giá trị có thể sai do cắt/tràn. Chính `longValueExact()` mới là phép kiểm tra chuyển đổi đầy đủ.

## 8. Checklist lựa chọn API

| Nhu cầu | Phương án | Có kiểm tra phần lẻ? | Có kiểm tra phạm vi int/long? |
| --- | --- | --- | --- |
| Chấp nhận cắt phần lẻ và nguy cơ mất bit | `intValue()` / `longValue()` | Không | Không |
| Chỉ nhận số nguyên vừa `int` | `intValueExact()` | Có | Có, 32 bit |
| Chỉ nhận số nguyên vừa `long` | `longValueExact()` | Có | Có, 64 bit |
| Làm tròn có chủ đích, rồi chuyển an toàn | `setScale(0, mode).intValueExact()` hoặc `...longValueExact()` | Làm tròn theo mode đã chọn | Có |
| Cắt phần lẻ nhưng không cho phép tràn | `setScale(0, DOWN).longValueExact()` | Chủ động cắt phần lẻ | Có |
| Giữ số nguyên chính xác, kể cả rất lớn | `toBigIntegerExact()` | Có | Không giới hạn vào 32/64 bit |
| Chấp nhận cắt phần lẻ thành BigInteger | `toBigInteger()` | Không | Không giới hạn vào 32/64 bit |

Trong code review, hãy tự hỏi: **phần thập phân có được phép bỏ đi không? Có quy tắc làm tròn nào bắt buộc không? Giá trị sau cùng có cần nằm đúng trong 32 hoặc 64 bit không?** Nếu một phép chuyển đổi sai cần được phát hiện, các phương thức `...ValueExact()` là lựa chọn mặc định phù hợp.

## 9. Câu hỏi luyện tập

**Câu 1.** `new BigDecimal("-7.99").intValue()` là bao nhiêu? Có phải làm tròn xuống không?

**Đáp án:** `-7`. Đây là cắt về 0; làm tròn theo `FLOOR` tới số nguyên sẽ là `-8`.

**Câu 2.** Vì sao `new BigDecimal("4294967296").intValue()` là `0` nhưng `longValue()` vẫn cho `4294967296`?

**Đáp án:** `4294967296 = 2^32` vượt phạm vi `int`; 32 bit thấp đều là 0. Giá trị đó vẫn nằm trong phạm vi `long`.

**Câu 3.** `new BigDecimal("4.000").intValueExact()` có ném lỗi không?

**Đáp án:** Không, kết quả là `4` vì giá trị toán học là số nguyên. Scale 3 không phải điều kiện thất bại; phần lẻ khác 0 mới là vấn đề.

**Câu 4.** Muốn biến `9.6` thành số nguyên `10` nhưng vẫn phát hiện tràn `int`, viết gì?

~~~java
int result = new BigDecimal("9.6")
        .setScale(0, RoundingMode.HALF_UP)
        .intValueExact();
~~~

**Câu 5.** `new BigDecimal("9223372036854775808").longValue()` có ném `ArithmeticException` không? `longValueExact()` thì sao?

**Đáp án:** `longValue()` không ném và trả `-9223372036854775808`. `longValueExact()` ném `ArithmeticException` vì giá trị dương đầu vào vượt `Long.MAX_VALUE`.

## 10. Tài liệu tham khảo

- [BigDecimal — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): mô tả `intValue()`, `longValue()`, `intValueExact()`, `longValueExact()`, `toBigInteger()` và `toBigIntegerExact()`.
- [RoundingMode — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): quy tắc làm tròn, đặc biệt `DOWN`, `HALF_UP`, `HALF_EVEN` và `UNNECESSARY`.
- [Integer và Long — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): hằng giới hạn kiểu số nguyên Java; với 64 bit tham khảo [Long](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html).

**Ghi nhớ:** `intValue()`/`longValue()` thuận tiện nhưng **có thể âm thầm mất phần lẻ và bit cao**. `intValueExact()`/`longValueExact()` giúp giữ nguyên hợp đồng dữ liệu bằng cách báo lỗi nếu số không nguyên hoặc không vừa kiểu đích. Làm tròn có chủ đích là **bước riêng biệt**, cần quy tắc nghiệp vụ rõ ràng.
