# BigInteger: `intValue`, `longValue` khác `intValueExact`, `longValueExact` như thế nào?

Trong Java Core, `java.math.BigInteger` biểu diễn **số nguyên có dấu với độ chính xác tùy ý**, có thể lớn hơn rất nhiều so với giới hạn 32 bit của `int` và 64 bit của `long`. Khi đưa một giá trị `BigInteger` vào API chỉ chấp nhận kiểu nguyên thủy, người học phải chọn rõ **có cho phép mất dữ liệu hay không**.

Cặp phương thức dễ nhầm:

- **`intValue()` / `longValue()`:** chuyển về kiểu hẹp bằng cách **giữ các bit thấp**. Nếu giá trị quá lớn hoặc quá nhỏ, kết quả có thể bị mất bit cao, đổi dấu, hoặc về 0; phương thức **không thông báo lỗi tràn phạm vi**.
- **`intValueExact()` / `longValueExact()`:** yêu cầu giá trị số nguyên **phải nằm trọn trong phạm vi** của kiểu đích. Nếu không thể biểu diễn chính xác, chúng ném **`ArithmeticException`**, không âm thầm cắt bit.

Ví dụ quan trọng:

```java
BigInteger n = new BigInteger("4294967296"); // 2^32.
int unsafe = n.intValue();           // 0: 32 bit thấp đều bằng 0.
long safeLong = n.longValueExact();  // 4294967296L: vẫn nằm trong long.
// int impossible = n.intValueExact(); // Ném ArithmeticException.
```

Đây là mảnh mã có thể đặt trong phương thức của một lớp đã import `java.math.BigInteger`. Bài học đi sâu cơ chế **thu hẹp bit theo bù hai**, biên `Integer.MIN_VALUE/MAX_VALUE`, `Long.MIN_VALUE/MAX_VALUE`, số âm, `2^32`, `2^64`, cách dùng các phương thức `Exact` và cách thiết kế API không âm thầm mất dữ liệu.

## 1. Vì sao phải chuyển `BigInteger` sang `int` hoặc `long`?

`BigInteger` cung cấp phép tính nguyên có độ chính xác tùy ý như `add`, `subtract`, `multiply`, `pow`, `shiftLeft` và hỗ trợ các số vượt xa `long`. Nhưng nhiều API Java khác nhận `int` hoặc `long`:

- Chỉ số, số lượng, kích thước, tham số của một số thư viện yêu cầu `int`.
- Thời gian, giá trị đếm hoặc số byte với miền đủ rộng thường dùng `long`.
- Các giao thức có trường 32 bit hoặc 64 bit cố định bắt buộc chọn một kiểu, phạm vi và quy tắc overflow.
- Cơ sở dữ liệu có cột `INTEGER`/`BIGINT` có giới hạn mà bạn phải tuân thủ.

**Chuyển kiểu không làm thay đổi giá trị trong đối tượng `BigInteger` gốc.** Nó chỉ tạo một kết quả nguyên thủy. Nếu kết quả bị mất bit, dữ liệu chính xác vẫn còn trong đối tượng `BigInteger`, nhưng biến `int`/`long` nhận kết quả sẽ mang **giá trị khác**.

```java
BigInteger big = BigInteger.ONE.shiftLeft(64);
long narrowed = big.longValue(); // 0L
System.out.println(big);         // 18446744073709551616: đối tượng không đổi.
```

Đừng coi việc “chuyển thành công” là bằng chứng số vừa phạm vi. Hai phương thức `intValue()` và `longValue()` được thiết kế để có thể **cắt ngắn có chủ ý**, không phải parser hoặc validator phạm vi.

## 2. Bốn phương thức quan trọng và hợp đồng

| Phương thức | Kết quả | Ngoài phạm vi kiểu đích | Dùng khi |
| --- | --- | --- | --- |
| `BigInteger.intValue()` | `int` 32 bit | Giữ **32 bit thấp**, có thể đổi giá trị và dấu; không báo tràn | Chủ ý lấy low 32 bits |
| `BigInteger.longValue()` | `long` 64 bit | Giữ **64 bit thấp**, có thể đổi giá trị và dấu; không báo tràn | Chủ ý lấy low 64 bits |
| `BigInteger.intValueExact()` | `int` 32 bit | Ném **`ArithmeticException`** | Cần chuyển đúng từng đơn vị trong phạm vi signed int |
| `BigInteger.longValueExact()` | `long` 64 bit | Ném **`ArithmeticException`** | Cần chuyển đúng từng đơn vị trong phạm vi signed long |

Tất cả là **phương thức thực thể** gọi trên đối tượng `BigInteger`. Hai phương thức có hậu tố `Exact` là API của lớp `BigInteger`, không phải phương thức có sẵn của mọi biến khai báo kiểu `Number`.

```java
BigInteger value = BigInteger.valueOf(42);
int a = value.intValue();          // 42
int b = value.intValueExact();     // 42
long c = value.longValue();        // 42L
long d = value.longValueExact();   // 42L
```

**Trong miền biểu diễn được**, cả hai biến thể của cùng kiểu trả **cùng một kết quả**. Sự khác biệt bộc lộ khi giá trị vượt giới hạn signed 32/64 bit.

## 3. Phạm vi số nguyên có dấu phải thuộc lòng

Các giới hạn cố định trong Java:

| Kiểu | Số bit | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: | ---: |
| `int` | 32 | `-2^31 = -2147483648` | `2^31 - 1 = 2147483647` |
| `long` | 64 | `-2^63 = -9223372036854775808` | `2^63 - 1 = 9223372036854775807` |
| `BigInteger` | Tùy ý | Không có giới hạn `int`/`long` | Chỉ giới hạn tài nguyên và giới hạn triển khai liên quan |

Với `intValueExact()`, điều kiện hợp lệ là:

```text
Integer.MIN_VALUE <= value <= Integer.MAX_VALUE
```

Với `longValueExact()`:

```text
Long.MIN_VALUE <= value <= Long.MAX_VALUE
```

Nếu một `BigInteger` vượt **chỉ phạm vi int** mà vẫn thuộc phạm vi `long`, thì `intValueExact()` thất bại nhưng **`longValueExact()` vẫn thành công**. Ví dụ `2^31` hoặc `2^32` là các số `long` hợp lệ, nhưng không phải `int` có dấu hợp lệ.

Tránh dùng `Integer.MAX_VALUE` và `Long.MAX_VALUE` như thể đó là giá trị dương có độ lớn lớn nhất mà Java nói chung lưu được. Chúng là giới hạn **của kiểu primitive có dấu tương ứng**.

## 4. `intValue()`: 32 bit thấp, không kiểm tra tràn

Ý nghĩa của `intValue()` có thể hiểu theo **bù hai 32 bit**: lấy phần còn lại của giá trị nguyên theo `2^32`, rồi diễn giải mẫu bit theo kiểu `int` signed.

Đặt:

```text
r = value mod 2^32, với 0 <= r < 2^32
```

Khi đó:

```text
intValue(value) =
    r                 nếu 0 <= r < 2^31
    r - 2^32          nếu 2^31 <= r < 2^32
```

Ví dụ:

```java
BigInteger a = BigInteger.valueOf(Integer.MAX_VALUE).add(BigInteger.ONE);
// a = 2147483648 = 2^31.
int narrowedA = a.intValue(); // -2147483648 = Integer.MIN_VALUE.

BigInteger b = BigInteger.ONE.shiftLeft(32);
// b = 4294967296 = 2^32.
int narrowedB = b.intValue(); // 0.
```

Tại `2^31`, 32 bit thấp là `0x80000000`, được `int` xem là số âm nhỏ nhất. Tại `2^32`, 32 bit thấp toàn 0, nên kết quả là 0. **Đây không phải phép bão hòa về `Integer.MAX_VALUE` hay một exception**.

Bảng minh họa:

| `BigInteger` gốc | `intValue()` | `intValueExact()` |
| ---: | ---: | --- |
| 123 | 123 | 123 |
| 2147483647 | 2147483647 | 2147483647 |
| 2147483648 | **-2147483648** | `ArithmeticException` |
| -2147483648 | -2147483648 | -2147483648 |
| -2147483649 | **2147483647** | `ArithmeticException` |
| 4294967295 | **-1** | `ArithmeticException` |
| 4294967296 | **0** | `ArithmeticException` |
| -4294967296 | **0** | `ArithmeticException` |

Dòng `-2147483649 → 2147483647` cho thấy **giá trị âm nhỏ hơn `Integer.MIN_VALUE`** cũng có thể đổi thành dương sau khi giữ bit thấp.

## 5. `longValue()`: giữ 64 bit thấp, quy tắc tương tự

Với `long`, thay 32 bằng 64:

```text
r = value mod 2^64, với 0 <= r < 2^64

longValue(value) =
    r                 nếu 0 <= r < 2^63
    r - 2^64          nếu 2^63 <= r < 2^64
```

Đây là mô hình toán học của việc giữ **64 bit thấp**, rồi diễn giải theo bù hai signed `long`.

```java
BigInteger a = BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);
// a = 9223372036854775808 = 2^63.
long narrowedA = a.longValue(); // Long.MIN_VALUE.

BigInteger b = BigInteger.ONE.shiftLeft(64);
// b = 18446744073709551616 = 2^64.
long narrowedB = b.longValue(); // 0L.
```

Hai biến thể `longValue` và `longValueExact` cũng khác nhau ở biên âm. `Long.MIN_VALUE - 1` trở thành `Long.MAX_VALUE` khi cắt 64 bit thấp, chứ không gây lỗi khi gọi `longValue()`.

| `BigInteger` gốc | `longValue()` | `longValueExact()` |
| ---: | ---: | --- |
| 9223372036854775807 | 9223372036854775807 | 9223372036854775807 |
| 9223372036854775808 | **-9223372036854775808** | `ArithmeticException` |
| -9223372036854775808 | -9223372036854775808 | -9223372036854775808 |
| -9223372036854775809 | **9223372036854775807** | `ArithmeticException` |
| 18446744073709551615 | **-1** | `ArithmeticException` |
| 18446744073709551616 | **0** | `ArithmeticException` |

**Điều cần nhớ:** `longValue()` không phải cách an toàn để chuyển một số nguyên quá lớn thành đại diện gần nhất trong miền `long`. Nó là chuyển đổi **low 64 bits**, có thể làm thay đổi hẳn giá trị.

## 6. Một số vừa `long` nhưng không vừa `int`

Xét `4294967296 = 2^32`:

```java
BigInteger n = new BigInteger("4294967296");

int a = n.intValue();           // 0: mất toàn bộ bit có nghĩa phía trên 32 bit.
long b = n.longValue();         // 4294967296L.
long c = n.longValueExact();    // 4294967296L.
// n.intValueExact();           // ArithmeticException.
```

Vì số này có thể lưu chính xác trong `long`, **không cần chuyển nó thành 0 chỉ để ép vào `int`**. Nếu API nhận `long`, dùng `longValueExact()`. Nếu API bắt buộc `int`, cần một **chính sách rõ**: từ chối, chia nhỏ công việc, hoặc phân trang; không âm thầm truyền 0.

Kết quả âm thầm về 0 đặc biệt nguy hiểm với các trường như **số bản ghi cần xử lý**, **giới hạn bộ nhớ**, **độ dài file**, **số lượng đơn hàng** hoặc **định danh**. Một giá trị cực lớn sau cắt bit có thể trở thành 0, âm hoặc số nhỏ nhưng trông hợp lệ.

## 7. `intValueExact()`: chuyển có kiểm tra signed 32 bit

`BigInteger.intValueExact()` chỉ thành công khi giá trị đã nằm trong **`[-2^31, 2^31-1]`**. Nếu ngoài miền, ném `ArithmeticException`.

```java
BigInteger a = BigInteger.valueOf(123);
int ok = a.intValueExact(); // 123.

BigInteger b = BigInteger.valueOf(Integer.MAX_VALUE).add(BigInteger.ONE);
// int wrong = b.intValueExact(); // ArithmeticException.
```

Điều này bao gồm **tràn dương lẫn tràn âm**. Không phải chỉ số dương lớn mới gây lỗi: `Integer.MIN_VALUE - 1` cũng vượt phạm vi `int`.

Hãy dùng khi việc có một giá trị sai dù chỉ một đơn vị là không thể chấp nhận, ví dụ nhập `BigInteger` vào trường `int` của một thư viện hoặc chuyển kết quả tính chính xác sang hệ thống giới hạn 32 bit.

Có thể xử lý ngoại lệ:

```java
static int requireInt(BigInteger value) {
    try {
        return value.intValueExact();
    } catch (ArithmeticException ex) {
        throw new IllegalArgumentException(
                "Value outside signed 32-bit range", ex);
    }
}
```

Đây là **phương thức ví dụ** đặt bên trong lớp có import `BigInteger`. Tùy hệ thống, bạn có thể giữ nguyên `ArithmeticException`, chuyển thành exception của nghiệp vụ hoặc trả một kiểu kết quả có mã lỗi. Đừng bắt exception rồi **quay về `intValue()`**, vì như vậy mất toàn bộ lợi ích kiểm tra tràn.

## 8. `longValueExact()`: chuyển có kiểm tra signed 64 bit

`BigInteger.longValueExact()` tương tự nhưng kiểm tra miền lớn hơn: **`[-2^63, 2^63-1]`**.

```java
BigInteger x = BigInteger.valueOf(Long.MAX_VALUE);
long ok = x.longValueExact(); // Long.MAX_VALUE.

BigInteger tooLarge = BigInteger.ONE.shiftLeft(63);
// long broken = tooLarge.longValueExact(); // ArithmeticException.
```

Đối với `2^63`, `longValue()` sẽ trả `Long.MIN_VALUE`; `longValueExact()` ném ngoại lệ. Với `-2^63` (chính `Long.MIN_VALUE`) thì phiên bản exact **vẫn thành công**, vì đó là biên dưới hợp lệ.

Nếu giá trị lớn hơn cả 64 bit và hệ thống thực sự cần giữ **số nguyên chính xác**, hãy tiếp tục giữ kiểu `BigInteger` trong API, dùng thư viện/cột dữ liệu phù hợp hoặc thiết kế cách lưu nhiều phần. Không nên giả định `long` đủ rộng chỉ vì dữ liệu “hiếm khi lớn”.

## 9. Phương thức `Exact` kiểm tra giá trị, không kiểm tra chuỗi biểu diễn

`BigInteger` lưu **giá trị số nguyên**, không giữ lại nguyên văn chuỗi đầu vào. Hai chuỗi như `"+00042"` và `"42"` khi được parse hợp lệ đều tạo giá trị 42; `intValueExact()` trả 42 trong cả hai trường hợp.

```java
BigInteger a = new BigInteger("42");
BigInteger b = new BigInteger("+00042");
System.out.println(a.equals(b)); // true.
System.out.println(b.intValueExact()); // 42.
```

Do đó `intValueExact()` **không phải** validator format đầu vào, và nó cũng không phát hiện được số 0 đầu, dấu cộng dư hoặc vi phạm quy tắc của một mã định danh. Nếu đầu vào phải giữ chính xác những ký tự như số 0 đầu, có thể đó là **mã** chứ không phải số cần tính toán; hãy giữ `String` và kiểm tra schema riêng.

Tương tự, chữ `Exact` không có nghĩa phương thức sẽ tự kiểm tra điều kiện nghiệp vụ “số phải không âm” hoặc “số lượng <= 1000”: một `int` âm vẫn có thể biểu diễn chính xác và được trả về bình thường.

## 10. `intValue()` không giống ép `BigInteger` bằng toán tử cast

Trong Java, `BigInteger` là **đối tượng**, không phải primitive `long` hoặc `int`. Bạn không thể viết:

```java
BigInteger big = BigInteger.ONE.shiftLeft(32);
// int value = (int) big; // Không biên dịch: BigInteger không thể cast trực tiếp sang int.
```

Cần gọi một trong các phương thức chuyển đổi:

```java
int lowBits = big.intValue(); // Chủ ý mất bit cao.
long checked = big.longValueExact(); // Yêu cầu chính xác.
```

Mô hình cắt bit của `BigInteger.intValue()` giống **ép hẹp số nguyên nguyên thủy** theo low-order bits về mặt kết quả, nhưng cú pháp và kiểu nguồn hoàn toàn khác. Đừng coi `BigInteger` là lớp bọc cho `long` có thể ép bằng cast thông thường.

Ngoài ra, phương thức `BigInteger.longValue()` **không tự gọi `intValueExact()` hay `longValueExact()`**. Nếu bạn muốn phát hiện mất dữ liệu, phải chọn **phiên bản Exact** một cách tường minh.

## 11. Số âm và cách hoạt động của các bit thấp

Số âm BigInteger có ngữ nghĩa bù hai khi thực hiện các phép toán bit. Khi ép hẹp về 32/64 bit, **không lấy trị tuyệt đối rồi cắt**, mà lấy mẫu bit thấp của **giá trị signed**.

Ví dụ:

```java
BigInteger a = BigInteger.ONE.shiftLeft(32).negate(); // -4294967296.
int bits32 = a.intValue(); // 0.
long whole64 = a.longValueExact(); // -4294967296.
```

Vì `-2^32` chia hết cho `2^32`, 32 bit thấp đều bằng 0. Điều này không biến giá trị gốc thành zero; chỉ có **phần thông tin được chuyển vào `int`** là zero.

Một ví dụ sát cận âm:

```java
BigInteger x = BigInteger.valueOf(Integer.MIN_VALUE)
        .subtract(BigInteger.ONE); // -2147483649.
int narrowed = x.intValue(); // 2147483647.
```

Bản `int` cho một số dương lớn mặc dù gốc âm. Điều này có thể phá logic nghiệp vụ như:

```java
int amount = someBigInteger.intValue();
if (amount > 0) {
    // Có thể vào nhánh dù giá trị BigInteger gốc âm và quá nhỏ.
}
```

Khi giá trị đóng vai trò **độ dài, số lượng, số tiền hoặc giá trị không âm**, nên dùng `intValueExact()` kết hợp kiểm tra **điều kiện >= 0** trước hoặc sau (vì exact chỉ kiểm tra phạm vi, không kiểm tra domain).

## 12. `2^32`, `2^64` và quy luật “về 0”

Hai mốc biên trực quan nhất cho chuyển đổi low bits:

```java
BigInteger p32 = BigInteger.ONE.shiftLeft(32);
BigInteger p64 = BigInteger.ONE.shiftLeft(64);

System.out.println(p32.intValue());  // 0.
System.out.println(p32.longValue()); // 4294967296.

System.out.println(p64.intValue());  // 0.
System.out.println(p64.longValue()); // 0.
```

Tại `2^32`, **32 bit thấp** đều bằng 0, trong khi 64 bit thấp vẫn mang thông tin của `2^32`. Tại `2^64`, cả hai phần thấp 32/64 bit đều bằng 0.

Ngược lại:

```java
BigInteger p64MinusOne = BigInteger.ONE.shiftLeft(64)
        .subtract(BigInteger.ONE);

System.out.println(p64MinusOne.longValue()); // -1.
```

Mẫu 64 bit thấp toàn 1 được kiểu `long` **có dấu** hiểu là -1. Dù một số nguyên dương có thể in `longValue() == -1`, nó không có nghĩa BigInteger “mất dấu” trong phép tính gốc; đây là **cách diễn giải signed của một mẫu bit**.

## 13. Giá trị cực lớn vẫn có thể tạo một kết quả nhỏ

Một BigInteger có thể cực kỳ lớn nhưng khi cắt lấy low 32/64 bits lại thành số nhỏ. Ví dụ:

```java
BigInteger huge = BigInteger.ONE.shiftLeft(100)
        .add(BigInteger.valueOf(123));

System.out.println(huge.intValue());  // 123.
System.out.println(huge.longValue()); // 123.
```

Lý do: `2^100` chia hết cho `2^64`, nên **64 bit thấp** của `2^100 + 123` chỉ còn 123. Đây là minh họa mạnh cho thấy kết quả `intValue()` hoặc `longValue()` **trông hợp lý** không chứng minh chúng phản ánh giá trị thật.

Nếu sau chuyển đổi chương trình kiểm tra `result <= limit` mà không kiểm tra phạm vi **trước đó**, một đầu vào cực lớn có thể trở thành một số nhỏ nằm dưới hạn mức. Dùng phiên bản `Exact` khi **giá trị cần được bảo toàn**, đặc biệt ở các đường đi kiểm tra giới hạn, cấp phát và định tuyến công việc.

## 14. So với `Math.toIntExact(long)`

JDK có phương thức:

```java
int narrowed = Math.toIntExact(someLong);
```

Nó dùng để kiểm tra một giá trị **đã là `long`** có vừa signed `int` không. Không thể truyền trực tiếp `BigInteger` vào `Math.toIntExact`.

Hai cách sau có ý nghĩa khác nhau:

```java
BigInteger big = new BigInteger("4294967296");

// Cách đúng nếu cần BigInteger -> int exact:
// int safe = big.intValueExact(); // ArithmeticException.

// Cách vòng qua long với kiểm tra:
// long first = big.longValueExact(); // Thành công vì 2^32 vừa long.
// int second = Math.toIntExact(first); // ArithmeticException.
```

Với giá trị ngoài signed 64 bit, **phải gọi `longValueExact()`** ở bước đầu. Nếu thay `longValueExact()` bằng `longValue()`, dữ liệu đã bị cắt, và `Math.toIntExact` chỉ kiểm tra giá trị **sau khi bị hỏng**, không khôi phục được giá trị gốc.

Ví dụ nguy hiểm:

```java
BigInteger p64 = BigInteger.ONE.shiftLeft(64);
long brokenLong = p64.longValue(); // 0.
int seemsFine = Math.toIntExact(brokenLong); // 0, KHÔNG có exception.
```

`Math.toIntExact` đúng với đầu vào `long 0`, nhưng đó đã là dữ liệu sai nếu mục tiêu là biểu diễn chính xác `BigInteger 2^64`. Khi nguồn vốn là `BigInteger`, dùng **`intValueExact()` trực tiếp** vừa rõ vừa an toàn.

## 15. So với `byteValueExact()` và `shortValueExact()`

Bên cạnh signed int/long, `BigInteger` cũng có các phương thức chuyển hẹp:

```java
byte a = BigInteger.valueOf(127).byteValueExact(); // 127.
short b = BigInteger.valueOf(32767).shortValueExact(); // 32767.

// BigInteger.valueOf(128).byteValueExact();   // ArithmeticException.
// BigInteger.valueOf(32768).shortValueExact(); // ArithmeticException.
```

Các giới hạn áp dụng:

| Kiểu | Miền signed |
| --- | --- |
| `byte` | -128..127 |
| `short` | -32768..32767 |
| `int` | -2147483648..2147483647 |
| `long` | -9223372036854775808..9223372036854775807 |

Ngược lại, `byteValue()` và `shortValue()` cũng có thể cắt bit khi thu hẹp. Nếu đang parse một trường giao thức có độ rộng cố định, cần phân biệt:

- **Giá trị có dấu** theo phạm vi của kiểu primitive Java.
- **Mẫu bit unsigned** của trường, ví dụ unsigned byte 0..255 hoặc unsigned int 0..2^32-1.

Một giá trị `BigInteger 255` **không vừa signed byte**, nên `byteValueExact()` phải ném exception. Nếu protocol thật sự muốn ghi byte `FF` với ý nghĩa **unsigned 255**, đó là phép **mã hóa unsigned có kiểm tra dải khác**, không phải chuyển exact sang signed `byte`.

## 16. Trường hợp dữ liệu unsigned: không nhầm với signed exact

Java `int` và `long` là kiểu nguyên **có dấu**. `BigInteger.intValueExact()` không có nhiệm vụ cho phép unsigned 32 bit đến `2^32-1`; nó chỉ cho phép signed int tới `2^31-1`.

Ví dụ:

```java
BigInteger unsigned32Max = new BigInteger("4294967295");
int lowBits = unsigned32Max.intValue(); // -1.
long positive = unsigned32Max.longValueExact(); // 4294967295L.
```

Ở đây:

- Nếu cần **giá trị dương chính xác**, giữ BigInteger hoặc chuyển sang `long` bằng `longValueExact()`.
- Nếu cần **mẫu 32 bit** của một trường unsigned, có thể dùng `intValue()` **sau khi xác thực** rằng giá trị nằm trong `0..2^32-1`; phía nhận phải dùng API unsigned như `Integer.toUnsignedLong` hoặc `Integer.toUnsignedString` để diễn giải.
- **Không** dùng `intValueExact()` làm bộ kiểm tra phạm vi unsigned 32 bit, vì +4294967295 hợp lệ unsigned nhưng không vừa signed int.

Tương tự, BigInteger `2^64-1` khi gọi `longValue()` trả -1, nhưng `longValueExact()` ném lỗi, bởi đó không phải signed `long` hợp lệ. Nếu một protocol lưu unsigned 64 bit, cần kiểm tra riêng `0..2^64-1` và định nghĩa rõ cách xử lý **bit pattern long** hoặc giữ kiểu `BigInteger`.

## 17. Đoạn mã kiểm tra signed/unsigned rõ ràng

Với giá trị signed `BigInteger` cần đưa vào `int`:

```java
static int requireSignedInt(BigInteger value) {
    return value.intValueExact();
}
```

Với một trường **unsigned 32 bit** cần giữ mẫu bit trong `int`:

```java
static int requireUnsignedIntBits(BigInteger value) {
    BigInteger max = BigInteger.ONE.shiftLeft(32).subtract(BigInteger.ONE);
    if (value.signum() < 0 || value.compareTo(max) > 0) {
        throw new ArithmeticException("outside unsigned 32-bit range");
    }
    return value.intValue(); // Có chủ đích: chỉ lấy 32 bit thấp.
}
```

Hai phương thức này là **mảnh mã trong lớp Java**, không phải API có sẵn. Bản unsigned **kiểm tra trước khi cắt bit**, vì sau khi cắt sẽ không còn đủ thông tin để biết giá trị ban đầu có quá lớn hay quá nhỏ không.

Đây là trường hợp điển hình mà `intValue()` **đúng** nếu và chỉ nếu:

1. Mục tiêu thật sự là biểu diễn **32 bit** chứ không phải giá trị signed int.
2. Miền unsigned đã được kiểm tra rõ ràng.
3. Hệ thống sử dụng kết quả theo **ngữ nghĩa unsigned**, không vô tình so sánh với 0 bằng cách signed.

Không nên áp dụng chiến lược unsigned cho số lượng công việc, chỉ số mảng hoặc số tiền chỉ vì muốn tránh exception — những miền đó thường yêu cầu **giá trị signed không âm và vừa phạm vi cụ thể**.

## 18. Kiểm tra trước bằng `compareTo` khi cần thông báo nghiệp vụ

Nếu muốn phân biệt “quá nhỏ” và “quá lớn”, thay vì bắt `ArithmeticException` có thể kiểm tra trực tiếp:

```java
static int requireIntWithMessage(BigInteger value) {
    BigInteger min = BigInteger.valueOf(Integer.MIN_VALUE);
    BigInteger max = BigInteger.valueOf(Integer.MAX_VALUE);
    if (value.compareTo(min) < 0) {
        throw new IllegalArgumentException("below Integer.MIN_VALUE");
    }
    if (value.compareTo(max) > 0) {
        throw new IllegalArgumentException("above Integer.MAX_VALUE");
    }
    return value.intValueExact();
}
```

Đây là một phương thức minh họa, có thể đặt trong lớp đã import `BigInteger`. Trong ứng dụng thực, có thể lưu `min`/`max` thành hằng số static final để tái sử dụng.

**Vì sao vẫn dùng `intValueExact()` sau kiểm tra?** Nó thể hiện rõ tính bất biến cần giữ: phương thức chỉ trả về một `int` nếu giá trị phù hợp. Sau khi đã kiểm tra bằng `compareTo`, `intValue()` cũng cho cùng kết quả, nhưng dùng `Exact` là cách diễn đạt ngữ nghĩa API ít gây nhầm.

Đừng thay điều kiện range bằng `value.bitLength() <= 31` mà chưa phân tích số âm và biên, bởi `BigInteger.bitLength()` có quy tắc riêng đối với giá trị âm. So sánh trực tiếp với `Integer.MIN_VALUE/MAX_VALUE` rõ ràng và khó sai hơn.

## 19. Exception không phải lúc nào cũng là lỗi cần sửa bằng cách bỏ kiểm tra

Hai phương thức `Exact` **ném `ArithmeticException` một cách có chủ đích**. Khi điều đó xảy ra, bạn nên xem lại:

- **Nguồn dữ liệu:** dữ liệu nhập có đúng miền bài toán không?
- **Kiểu đích:** yêu cầu `int`/ `long` là bắt buộc hay có thể giữ `BigInteger`?
- **Giới hạn nghiệp vụ:** một số nguyên tuy vừa `long` nhưng có thể vẫn vượt quota/tài nguyên.
- **Cách biểu diễn:** dữ liệu là số signed hay unsigned bit pattern?
- **Phản hồi cho caller:** nên trả mã lỗi, exception nghiệp vụ hay yêu cầu cung cấp giá trị nhỏ hơn?

Mã tránh dùng:

```java
static int dangerousFallback(BigInteger x) {
    try {
        return x.intValueExact();
    } catch (ArithmeticException ex) {
        return x.intValue(); // SAI nếu yêu cầu là chuyển chính xác.
    }
}
```

Nếu nghiệp vụ có chủ đích cần **wrap modulo 2^32**, hãy chọn `intValue()` ngay từ đầu và giải thích. Nếu nghiệp vụ muốn **clamp/saturate** vào `Integer.MIN_VALUE/MAX_VALUE`, hãy viết chính sách giới hạn riêng sau so sánh; `intValue()` **không thực hiện saturation**.

## 20. Chương trình Java 17+ chạy độc lập

Tạo tệp **`BigIntegerConversionDemo.java`**:

```java
import java.math.BigInteger;

public class BigIntegerConversionDemo {
    private static String exactInt(BigInteger value) {
        try {
            return Integer.toString(value.intValueExact());
        } catch (ArithmeticException ex) {
            return "ArithmeticException";
        }
    }

    private static String exactLong(BigInteger value) {
        try {
            return Long.toString(value.longValueExact());
        } catch (ArithmeticException ex) {
            return "ArithmeticException";
        }
    }

    private static void show(String label, BigInteger value) {
        System.out.println(label + " value=" + value);
        System.out.println(label + " int=" + value.intValue()
                + ", intExact=" + exactInt(value));
        System.out.println(label + " long=" + value.longValue()
                + ", longExact=" + exactLong(value));
    }

    public static void main(String[] args) {
        show("small", BigInteger.valueOf(123));
        show("intMax", BigInteger.valueOf(Integer.MAX_VALUE));
        show("intOver", BigInteger.valueOf(Integer.MAX_VALUE).add(BigInteger.ONE));
        show("intUnder", BigInteger.valueOf(Integer.MIN_VALUE).subtract(BigInteger.ONE));
        show("twoPow32", BigInteger.ONE.shiftLeft(32));
        show("minusTwoPow32", BigInteger.ONE.shiftLeft(32).negate());
        show("longMax", BigInteger.valueOf(Long.MAX_VALUE));
        show("longOver", BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE));
        show("longUnder", BigInteger.valueOf(Long.MIN_VALUE).subtract(BigInteger.ONE));
        show("twoPow64", BigInteger.ONE.shiftLeft(64));
        show("twoPow64MinusOne", BigInteger.ONE.shiftLeft(64).subtract(BigInteger.ONE));
        show("twoPow100Plus123", BigInteger.ONE.shiftLeft(100).add(BigInteger.valueOf(123)));

        BigInteger outsideInt = new BigInteger("4294967295");
        boolean fitsInt = outsideInt.compareTo(BigInteger.valueOf(Integer.MIN_VALUE)) >= 0
                && outsideInt.compareTo(BigInteger.valueOf(Integer.MAX_VALUE)) <= 0;
        System.out.println("fitsInt=" + fitsInt);
        System.out.println("mathToIntExactError="
                + exactMathToInt(BigInteger.ONE.shiftLeft(32).longValueExact()));
        System.out.println("bigIntegerUnchanged="
                + BigInteger.ONE.shiftLeft(64).equals(new BigInteger("18446744073709551616")));
    }

    private static String exactMathToInt(long value) {
        try {
            return Integer.toString(Math.toIntExact(value));
        } catch (ArithmeticException ex) {
            return "ArithmeticException";
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 BigIntegerConversionDemo.java
java BigIntegerConversionDemo
```

Stdout chính xác (đã biên dịch và chạy với Java 17):

```text
small value=123
small int=123, intExact=123
small long=123, longExact=123
intMax value=2147483647
intMax int=2147483647, intExact=2147483647
intMax long=2147483647, longExact=2147483647
intOver value=2147483648
intOver int=-2147483648, intExact=ArithmeticException
intOver long=2147483648, longExact=2147483648
intUnder value=-2147483649
intUnder int=2147483647, intExact=ArithmeticException
intUnder long=-2147483649, longExact=-2147483649
twoPow32 value=4294967296
twoPow32 int=0, intExact=ArithmeticException
twoPow32 long=4294967296, longExact=4294967296
minusTwoPow32 value=-4294967296
minusTwoPow32 int=0, intExact=ArithmeticException
minusTwoPow32 long=-4294967296, longExact=-4294967296
longMax value=9223372036854775807
longMax int=-1, intExact=ArithmeticException
longMax long=9223372036854775807, longExact=9223372036854775807
longOver value=9223372036854775808
longOver int=0, intExact=ArithmeticException
longOver long=-9223372036854775808, longExact=ArithmeticException
longUnder value=-9223372036854775809
longUnder int=-1, intExact=ArithmeticException
longUnder long=9223372036854775807, longExact=ArithmeticException
twoPow64 value=18446744073709551616
twoPow64 int=0, intExact=ArithmeticException
twoPow64 long=0, longExact=ArithmeticException
twoPow64MinusOne value=18446744073709551615
twoPow64MinusOne int=-1, intExact=ArithmeticException
twoPow64MinusOne long=-1, longExact=ArithmeticException
twoPow100Plus123 value=1267650600228229401496703205499
twoPow100Plus123 int=123, intExact=ArithmeticException
twoPow100Plus123 long=123, longExact=ArithmeticException
fitsInt=false
mathToIntExactError=ArithmeticException
bigIntegerUnchanged=true
```

Các dòng đáng chú ý:

1. **`small` và `intMax`**: trong miền signed int, cả bốn phương thức trả giá trị tương thích với kích thước kiểu đích.
2. **`intOver`**: +2147483648 trở thành -2147483648 với `intValue()`, nhưng `intValueExact()` báo lỗi; `longValueExact()` vẫn thành công.
3. **`intUnder`**: -2147483649 trở thành +2147483647 khi bị cắt xuống int; phương thức exact từ chối.
4. **`twoPow32`, `minusTwoPow32`**: giá trị gốc ±4294967296 cho `intValue() == 0`, dù vẫn vừa signed long.
5. **`longOver`, `longUnder`**: một bước ngoài giới hạn 64 bit gây chuyển đổi wrap-around ở `longValue()`, trong khi `longValueExact()` ném exception.
6. **`twoPow64`**: BigInteger (2^{64}) có `intValue() == 0` và `longValue() == 0`, không phải vì số gốc là zero.
7. **`twoPow64MinusOne`**: giá trị unsigned 64 bit tối đa cho `longValue() == -1`; phương thức exact từ chối vì ngoài signed long.
8. **`twoPow100Plus123`**: một BigInteger hơn 30 chữ số có `intValue()` và `longValue()` đều bằng 123, cho thấy kết quả bị cắt có thể trông hợp lệ.
9. **`fitsInt=false`**, **`mathToIntExactError=ArithmeticException`** và **`bigIntegerUnchanged=true`**: minh họa range check, API `Math.toIntExact` và tính bất biến của BigInteger.

Trong ví dụ, hàm `exactInt` và `exactLong` **bắt ArithmeticException để in kết quả kiểm thử**. Ứng dụng thật thường cần truyền lỗi hoặc xử lý nó theo quy tắc nghiệp vụ thay vì biến thành chuỗi. Cả chương trình chỉ dùng thư viện chuẩn JDK 17.

## 21. Phân biệt những phương thức khác có chữ “Exact”

Java có nhiều API gắn hậu tố `Exact`, nhưng không nên gộp chúng thành cùng một hành vi:

| API | Nhiệm vụ |
| --- | --- |
| `BigInteger.intValueExact()` | Chuyển BigInteger sang signed int **có kiểm tra dải** |
| `BigInteger.longValueExact()` | Chuyển BigInteger sang signed long **có kiểm tra dải** |
| `Math.toIntExact(long)` | Chuyển **long** sang int với kiểm tra dải |
| `Math.addExact(int,long...)` | Nhóm phương thức cộng primitive có kiểm tra overflow theo overload cụ thể |
| `Math.multiplyExact(...)` | Nhân primitive có kiểm tra overflow |
| `BigDecimal.intValueExact()` | Chuyển **số thập phân** sang int, kiểm tra cả khả năng biểu diễn nguyên chính xác và dải |
| `BigDecimal.longValueExact()` | Chuyển số thập phân sang long, cũng không cho mất phần lẻ |

Với `BigInteger`, **không tồn tại phần thập phân** để phải làm tròn khi chuyển sang `int` hoặc `long`; chỉ cần kiểm tra miền giá trị. Với `BigDecimal`, `intValueExact` còn có thể lỗi khi giá trị như `1.5` không phải số nguyên, dù trị tuyệt đối rất nhỏ. Đây là một khác biệt quan trọng nếu hệ thống dùng biến kiểu `Number` hoặc hoán đổi giữa BigInteger và BigDecimal.

Ví dụ:

```java
BigInteger a = new BigInteger("1");
int x = a.intValueExact(); // 1, hợp lệ.

java.math.BigDecimal b = new java.math.BigDecimal("1.5");
// b.intValueExact() ném ArithmeticException vì không thể bỏ .5 một cách exact.
```

Hậu tố `Exact` cần được hiểu theo **hợp đồng của từng API**, không phải như lời hứa rằng mọi phép toán phía sau cũng chính xác.

## 22. Kiểm thử biên cần có

Để chắc rằng chương trình không cắt dữ liệu ngoài ý muốn, nên kiểm thử ít nhất:

| Test value | Kỳ vọng `intValueExact` | Kỳ vọng `longValueExact` |
| --- | --- | --- |
| 0, 1, -1 | Thành công | Thành công |
| `Integer.MAX_VALUE` | Thành công | Thành công |
| `Integer.MAX_VALUE + 1` | **Lỗi** | Thành công |
| `Integer.MIN_VALUE` | Thành công | Thành công |
| `Integer.MIN_VALUE - 1` | **Lỗi** | Thành công |
| `Long.MAX_VALUE` | **Lỗi** | Thành công |
| `Long.MAX_VALUE + 1` | **Lỗi** | **Lỗi** |
| `Long.MIN_VALUE` | **Lỗi** | Thành công |
| `Long.MIN_VALUE - 1` | **Lỗi** | **Lỗi** |
| `2^64`, `2^100+123` | **Lỗi** | **Lỗi** |

Sau đó test hành vi **`intValue()`/`longValue()` cắt bit** theo đúng policy. Không cần khẳng định nó “gần” giá trị gốc; phép chuyển là modulo theo số bit chứ không phải phép lấy gần nhất.

Với dữ liệu từ giao thức unsigned, thêm test **trường signed dương/âm** và **trường bit pattern unsigned**, ví dụ `2^32-1` hoặc `2^64-1`. Đảm bảo các tầng nhận và gửi thống nhất về độ rộng bit và cách diễn giải dấu.

## 23. Một số tình huống ứng dụng

### A. Số lượng hoặc kích thước

Một endpoint nhận `BigInteger` cho số bản ghi. Nếu gọi `intValue()` trên `2^32`, kết quả 0 có thể khiến chương trình tưởng không có bản ghi để xử lý. Với yêu cầu một số lượng vừa signed `int` và không âm:

```java
static int validCount(BigInteger number) {
    if (number.signum() < 0) {
        throw new IllegalArgumentException("negative count");
    }
    return number.intValueExact();
}
```

**Hai kiểm tra** có hai trách nhiệm: `signum() >= 0` cho ngữ nghĩa số lượng; `intValueExact()` cho khả năng lưu vào kiểu đích.

### B. ID và số nguyên độ dài lớn

Nếu ID lớn hơn signed 64 bit, ép bằng `longValue()` có thể làm hai ID **khác nhau** có cùng 64 bit thấp, tạo va chạm sau chuyển đổi. Nếu ID phải duy nhất, không được dùng phép cắt bit; giữ **`BigInteger`** hoặc dùng `String`/kiểu cơ sở dữ liệu đủ rộng theo thiết kế. Khi giới hạn API chỉ cho `long`, dùng `longValueExact()` để từ chối giá trị không phù hợp.

### C. Mã hóa trường 32 bit unsigned

Một giao thức mô tả trường 32 bit không dấu. Giá trị `4294967295` hợp lệ, nhưng `intValueExact()` không thể biểu diễn thành signed int dương. Có thể chủ động tạo mẫu 32 bit với `intValue()` **sau khi kiểm tra miền unsigned** và khi ghi/đọc phải dùng API unsigned. Sự chuyển đổi này không giống chuyển kiểu số nguyên có dấu exact.

### D. Tính toán nhiều bước

Nếu đang tính một tích có thể vượt `long`:

```java
BigInteger result = BigInteger.valueOf(Long.MAX_VALUE)
        .multiply(BigInteger.valueOf(2));
// Giữ BigInteger trong toàn bộ chuỗi tính toán.
```

Hãy **trì hoãn việc thu hẹp** cho tới boundary thật sự cần primitive, rồi chọn `longValueExact()` nếu không chấp nhận mất dữ liệu. Chuyển sớm sang `longValue()` có thể hủy kết quả chính xác mà BigInteger đã giúp duy trì.

## 24. Những nhầm lẫn thường gặp

| Nhầm lẫn | Sự thật | Cách làm đúng |
| --- | --- | --- |
| `intValue()` tự kiểm tra quá phạm vi | Nó chỉ lấy **32 bit thấp**, không ném lỗi tràn | Dùng `intValueExact()` nếu cần bảo toàn |
| `longValue()` đủ lớn cho mọi BigInteger | Long chỉ 64 bit có dấu | Dùng `longValueExact()` hoặc giữ BigInteger |
| Cắt số lớn sẽ lấy `Integer.MAX_VALUE` | Không có saturation; có thể trả âm/0 | Dùng chính sách clamp riêng nếu cần |
| `2^32` chuyển thành int vẫn là số lớn dương | 32 bit thấp là 0 | Dùng long/BigInteger |
| `2^64` chuyển thành long được 2^64 | 64 bit thấp bằng 0 | `longValueExact()` ném lỗi |
| `intValueExact()` kiểm tra số không âm | Nó chỉ kiểm tra signed range | Kết hợp `signum()` cho miền không âm |
| Chỉ số dương mới bị wrap | Số âm ngoài miền cũng đổi thành số dương hoặc 0 | Test cả hai biên signed |
| `Math.toIntExact(big.longValue())` luôn đủ an toàn | `longValue()` có thể đã cắt bit | Dùng `big.intValueExact()` trực tiếp |
| `intValue()` trả 123 nghĩa BigInteger bằng 123 | Có thể là `2^100+123` | Phân biệt giá trị gốc với low bits |
| `intValueExact()` bảo đảm số chữ số/format input | Nó chỉ kiểm tra giá trị | Validate `String` đầu vào riêng |
| `longValueExact()` thích hợp cho unsigned `2^64-1` | Signed long không chứa được giá trị này | Xác thực unsigned và dùng quy ước bit-pattern |
| Chuyển sang `double` rồi ép int/long sẽ chính xác hơn | Double còn có sai số làm tròn và giới hạn | Tránh floating-point khi cần số nguyên exact |
| Catch `ArithmeticException` rồi gọi `intValue()` | Âm thầm bỏ qua lỗi quan trọng | Trả lỗi có nghĩa hoặc đổi kiểu đích |

## 25. Tự kiểm tra kiến thức

1. **Sự khác biệt ngắn gọn giữa `intValue()` và `intValueExact()` là gì?** Bản thường giữ 32 bit thấp, có thể mất dữ liệu; bản exact từ chối số ngoài signed int bằng `ArithmeticException`.
2. **`BigInteger("4294967296").intValue()` trả gì?** 0, vì `2^32` có 32 bit thấp bằng 0.
3. **Với cùng BigInteger `2^32`, `longValueExact()` có thành công không?** Có, trả `4294967296L` vì số này vừa signed long.
4. **`BigInteger.valueOf(Integer.MAX_VALUE).add(BigInteger.ONE).intValue()` trả gì?** `Integer.MIN_VALUE`, tức `-2147483648`.
5. **`BigInteger.valueOf(Integer.MIN_VALUE).subtract(BigInteger.ONE).intValue()` trả gì?** `Integer.MAX_VALUE`, tức `2147483647`.
6. **`BigInteger.ONE.shiftLeft(64).longValue()` trả gì?** 0, vì `2^64` có 64 bit thấp bằng 0.
7. **`BigInteger.ONE.shiftLeft(64).longValueExact()` ra sao?** Ném `ArithmeticException` vì `2^64` vượt signed long.
8. **`BigInteger("18446744073709551615").longValue()` cho gì?** -1, vì 64 bit thấp toàn 1.
9. **`longValueExact()` có ném lỗi với `Long.MIN_VALUE` không?** Không. Đây là giới hạn dưới hợp lệ của signed long.
10. **Có thể dùng `intValueExact()` để kiểm tra giá trị thuộc `0..2^32-1` không?** Không; nó chỉ kiểm tra signed int. Unsigned cần validator miền riêng.
11. **Một số cực lớn có `intValue() == 123` có nghĩa nó bằng 123 không?** Không. `2^100+123` cũng trả 123 khi chỉ lấy 32 bit thấp.
12. **`Math.toIntExact(big.longValue())` có luôn an toàn cho BigInteger không?** Không; bước `longValue()` có thể mất dữ liệu trước khi `Math.toIntExact` nhìn thấy kết quả.
13. **Để giảm nguy cơ mất dữ liệu khi chuyển BigInteger cho API nhận long, nên dùng gì?** `longValueExact()`; nếu lỗi, xử lý hoặc thay đổi thiết kế để giữ BigInteger.
14. **Exact chỉ đảm bảo phạm vi hay cả quy tắc nghiệp vụ?** Chỉ bảo đảm giá trị số nằm trong phạm vi signed của kiểu đích. Số không âm, quota và cú pháp input phải kiểm tra riêng.

**Ghi nhớ:** với `BigInteger`, **`intValue()` và `longValue()` là phép lấy các bit thấp**; nếu số quá phạm vi, kết quả có thể thay đổi mạnh mà **không có ngoại lệ**. Ngược lại, **`intValueExact()` và `longValueExact()` yêu cầu biểu diễn chính xác toàn bộ giá trị trong signed 32/64 bit**, nếu không sẽ **ném `ArithmeticException`**. Khi cần bảo toàn giá trị của số nguyên lớn trong hệ thống thật, ưu tiên API `Exact`, kiểm tra phạm vi nghiệp vụ và chỉ cố ý cắt bit khi chính hợp đồng dữ liệu yêu cầu.
