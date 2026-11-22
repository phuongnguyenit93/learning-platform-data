# Integer.parseInt, Long.parseLong và cơ số trong Java

## 1. Từ chuỗi ký tự đến giá trị số nguyên

Dữ liệu nhập qua biểu mẫu, tệp cấu hình, lệnh terminal hay API thường là `String`. Chuỗi `"123"` chứa ba ký tự, còn số `123` là một giá trị nguyên có thể cộng, trừ, so sánh hoặc dùng làm chỉ số. Trong Java:

- `Integer.parseInt(String s)` đọc chuỗi số **có dấu, cơ số 10** và trả về `int`.
- `Long.parseLong(String s)` cũng đọc chuỗi số có dấu, cơ số 10 nhưng trả về `long`, có miền giá trị rộng hơn.
- `Integer.parseInt(String s, int radix)` và `Long.parseLong(String s, int radix)` đọc chuỗi theo **cơ số do người gọi lựa chọn**.

```java
int count = Integer.parseInt("123");
long distance = Long.parseLong("9000000000");
int binary = Integer.parseInt("101101", 2);

System.out.println(count);    // 123
System.out.println(distance); // 9000000000
System.out.println(binary);   // 45
```

Hai hàm trả về giá trị số nguyên thủy (`int` hoặc `long`), không giữ định dạng ban đầu như số `0` ở đầu hay việc viết chữ hoa/thường trong chuỗi hex. Khi `System.out.println` in một `int` hay `long` theo cách thông thường, kết quả được biểu diễn ở hệ thập phân, dù chuỗi ban đầu được parse ở cơ số khác.

## 2. Cơ số là gì?

Cơ số (`radix`) quy định có bao nhiêu giá trị chữ số và giá trị của mỗi vị trí. Ví dụ chuỗi `101101` ở cơ số 2 biểu thị:

\[
1\cdot 2^5 + 0\cdot 2^4 + 1\cdot 2^3 + 1\cdot 2^2 + 0\cdot 2^1 + 1\cdot 2^0 = 45.
\]

Nếu coi `"101101"` ở cơ số 10 thì giá trị khác hoàn toàn. Vì vậy, **biết chuỗi thôi chưa đủ; cần biết cơ số của chuỗi đó**.

Java cho phép `radix` từ `Character.MIN_RADIX` = 2 đến `Character.MAX_RADIX` = 36:

| Cơ số | Tên thường gặp | Chuỗi đầu vào | Lời gọi | Giá trị số |
| ---: | --- | --- | --- | ---: |
| 2 | Nhị phân | `"101101"` | `Integer.parseInt("101101", 2)` | 45 |
| 8 | Bát phân | `"+77"` | `Integer.parseInt("+77", 8)` | 63 |
| 10 | Thập phân | `"77"` | `Integer.parseInt("77", 10)` | 77 |
| 16 | Thập lục phân | `"7F"` | `Integer.parseInt("7F", 16)` | 127 |
| 36 | Cơ số 36 | `"z"` | `Integer.parseInt("z", 36)` | 35 |

Các cơ số đến 10 dùng chữ số `0`–`9` thích hợp. Ở cơ số lớn hơn 10, các chữ cái từ `a` đến `z` biểu diễn các giá trị từ 10 đến 35. Khi parse, chữ hoa và chữ thường tương đương: `Integer.parseInt("FF", 16)` và `Integer.parseInt("ff", 16)` đều là 255.

Một chữ số phải **nhỏ hơn cơ số**. Ví dụ `"19"` không hợp lệ ở cơ số 8 vì `9` không phải chữ số bát phân. Cơ số không hợp lệ như 1 hay 37 cũng dẫn đến `NumberFormatException`.

**Không truyền `radix` thì mặc định là 10**: `Integer.parseInt("010")` trả về 10, không tự chuyển sang hệ 8.

## 3. Dấu cộng, dấu trừ và chữ số

Một chuỗi nguyên có dấu có thể chứa `+` hoặc `-` ngay đầu:

```java
System.out.println(Integer.parseInt("42"));      // 42
System.out.println(Integer.parseInt("+42"));     // 42
System.out.println(Integer.parseInt("-42"));     // -42
System.out.println(Integer.parseInt("-0"));      // 0
System.out.println(Integer.parseInt("-1A", 16)); // -26
```

Trong `"-1A"` ở cơ số 16, phần chữ số `1A` biểu thị 26 ở hệ 10, dấu trừ biến giá trị thành -26. Ký tự dấu không được đứng giữa hoặc cuối số; `"+"` hoặc `"-"` đứng đơn độc cũng không phải đầu vào hợp lệ.

Với các số dương, dấu `+` là tùy chọn. Chuỗi `"-0"` sau khi parse là số nguyên `0`, vì kiểu `int` và `long` không có giá trị âm 0 riêng biệt.

Đối với số 16, các cách viết `"f"`, `"F"`, `"0f"` đều mô tả cùng giá trị 15, nhưng **cách viết của chuỗi đầu vào không được lưu trong giá trị số**.

## 4. Tiền tố 0x/0b và dấu gạch dưới không tự được hiểu

Trong **mã nguồn Java**, lập trình viên có thể viết các literal sau:

```java
int a = 0xFF;
int b = 0b1010;
int c = 1_000;
```

Nhưng chuỗi runtime `"0xFF"`, `"0b1010"`, `"1_000"` không được `parseInt` tự chấp nhận. Đây là khác biệt giữa **ngữ pháp literal số trong mã nguồn** và **định dạng văn bản đầu vào của API parse**.

Đúng:

```java
int a = Integer.parseInt("FF", 16);    // 255
int b = Integer.parseInt("1010", 2);  // 10
int c = Integer.parseInt("1000", 10); // 1000
```

Sai nếu gọi trực tiếp (các lời gọi minh họa dưới đây sẽ ném ngoại lệ):

```java
Integer.parseInt("0xFF", 16);
Integer.parseInt("0b1010", 2);
Integer.parseInt("1_000", 10);
```

Nếu hợp đồng dữ liệu cho phép tiền tố `0x`, hãy **kiểm tra tiền tố rồi loại nó trước khi parse**:

```java
String input = "0xFF";
if (input.startsWith("0x") || input.startsWith("0X")) {
    input = input.substring(2);
}
int result = Integer.parseInt(input, 16);
System.out.println(result); // 255
```

Đây là đoạn minh họa cho **đầu vào hex không âm**. Nếu dữ liệu có thể là `"-0xFF"`, phải thiết kế quy tắc xử lý dấu và tiền tố riêng, tránh cắt sai chuỗi. Java có `Integer.decode`/`Long.decode` nhận một số dạng tiền tố (và quy ước số 0 đầu cho bát phân), nhưng chúng có hợp đồng khác `parseInt(s, radix)`; không đổi API chỉ để tự suy đoán định dạng mà người dùng chưa yêu cầu.

## 5. int và long có giới hạn khác nhau

`int` là số nguyên có dấu 32 bit; `long` là số nguyên có dấu 64 bit:

| Kiểu | Nhỏ nhất | Lớn nhất |
| --- | ---: | ---: |
| `int` | -2,147,483,648 | 2,147,483,647 |
| `long` | -9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 |

Ví dụ:

```java
long validLong = Long.parseLong("9000000000");
System.out.println(validLong); // 9000000000
```

Chuỗi `"9000000000"` vượt giới hạn `int` nhưng nằm trong `long`. Nếu dùng `Integer.parseInt("9000000000")` sẽ nhận `NumberFormatException`, không phải kết quả cắt bớt các chữ số.

Ngay cả khi tất cả ký tự đều là chữ số hợp lệ, **giá trị vẫn phải nằm trong phạm vi kiểu đích**:

```java
int maxInt = Integer.parseInt("7fffffff", 16);
int minInt = Integer.parseInt("-80000000", 16);

long maxLong = Long.parseLong("7fffffffffffffff", 16);
long minLong = Long.parseLong("-8000000000000000", 16);
```

Kết quả lần lượt là `Integer.MAX_VALUE`, `Integer.MIN_VALUE`, `Long.MAX_VALUE` và `Long.MIN_VALUE`. Ngược lại, `Integer.parseInt("80000000", 16)` lỗi vì đó là giá trị dương 2,147,483,648, vượt `Integer.MAX_VALUE`.

`"ffffffff"` ở hệ 16 là giá trị dương 4,294,967,295 nếu không có dấu âm, vì vậy `Integer.parseInt("ffffffff", 16)` cũng lỗi; `parseInt` không tự diễn giải chuỗi này thành bit pattern `-1`.

### Khi long vẫn chưa đủ

`Long.parseLong` cũng kiểm tra miền có dấu 64 bit. Với số nguyên lớn hơn `Long.MAX_VALUE`, dùng `java.math.BigInteger` khi phù hợp:

```java
import java.math.BigInteger;

BigInteger huge = new BigInteger("FFFFFFFFFFFFFFFF", 16);
System.out.println(huge); // 18446744073709551615
```

Đây là đoạn minh họa dùng `import` riêng. `BigInteger` là đối tượng số nguyên độ lớn tùy ý, có các phương thức tính toán khác với toán tử của kiểu nguyên thủy.

## 6. NumberFormatException: nguyên nhân và cách xử lý

`Integer.parseInt` và `Long.parseLong` ném `NumberFormatException` nếu chuỗi không thể được diễn giải thành giá trị kiểu đích theo cơ số yêu cầu.

Các lỗi phổ biến:

| Đầu vào | Lời gọi | Vì sao lỗi |
| --- | --- | --- |
| `""` | `Integer.parseInt("")` | Không có chữ số. |
| `"+"` | `Integer.parseInt("+")` | Chỉ có dấu, không có chữ số. |
| `" 42 "` | `Integer.parseInt(" 42 ")` | Không tự xóa khoảng trắng. |
| `"12.5"` | `Integer.parseInt("12.5")` | Không nhận phần thập phân. |
| `"19"` | `Integer.parseInt("19", 8)` | Chữ số `9` không hợp lệ ở cơ số 8. |
| `"0xFF"` | `Integer.parseInt("0xFF", 16)` | Không tự hiểu `0x` là tiền tố. |
| `"1_000"` | `Integer.parseInt("1_000")` | Dấu gạch dưới không được chấp nhận từ chuỗi. |
| `"2147483648"` | `Integer.parseInt("2147483648")` | Tràn miền `int`. |
| `"10"` | `Integer.parseInt("10", 1)` | Cơ số ngoài khoảng 2–36. |

Ví dụ bắt lỗi ở ranh giới nhập liệu:

```java
String raw = "2147483648";

try {
    int value = Integer.parseInt(raw);
    System.out.println(value);
} catch (NumberFormatException ex) {
    System.out.println("Không phải số int hợp lệ");
}
```

Đầu ra là `Không phải số int hợp lệ`. Đây không phải cơ chế tự động biến đầu vào sai thành 0. Một chuỗi vượt miền `int` bị từ chối rõ ràng, giúp ứng dụng tránh âm thầm dùng giá trị khác với ý định.

`null` cũng không phải một giá trị số. Trước khi xử lý từ biểu mẫu hoặc API, nên phân biệt **thiếu trường**, **chuỗi rỗng**, **chuỗi không hợp lệ**, **số ngoài miền** và **số hợp lệ** theo nhu cầu nghiệp vụ.

Nếu dữ liệu quy định có thể có khoảng trắng thừa, có thể dùng `raw.strip()` (Java 11+) trước khi parse; còn nếu khoảng trắng là lỗi định dạng, nên báo lỗi thay vì tự sửa. Không viết `catch (NumberFormatException e) { return 0; }` một cách tùy tiện vì sẽ đánh đồng “0 hợp lệ” với “giá trị nhập sai”.

## 7. Chương trình Java 17+ chạy độc lập

Lưu vào tệp `ParseRadixDemo.java`:

```java
import java.math.BigInteger;

public class ParseRadixDemo {
    private static void expectFailure(String label, String input, int radix) {
        try {
            Integer.parseInt(input, radix);
            System.out.println(label + ": unexpectedly accepted");
        } catch (NumberFormatException ex) {
            System.out.println(label + ": NumberFormatException");
        }
    }

    public static void main(String[] args) {
        System.out.println("decimal int: " + Integer.parseInt("120"));
        System.out.println("decimal long: " + Long.parseLong("9000000000"));
        System.out.println("binary: " + Integer.parseInt("101101", 2));
        System.out.println("octal: " + Integer.parseInt("+77", 8));
        System.out.println("hex: " + Integer.parseInt("7F", 16));
        System.out.println("hex signed: " + Integer.parseInt("-1A", 16));
        System.out.println("base36: " + Integer.parseInt("z", 36));
        System.out.println("int min hex: " +
                Integer.parseInt("-80000000", 16));
        System.out.println("long max hex: " +
                Long.parseLong("7fffffffffffffff", 16));
        System.out.println("long min hex: " +
                Long.parseLong("-8000000000000000", 16));

        System.out.println("hex prefix removed: " +
                Integer.parseInt("0xFF".substring(2), 16));

        String source = "prefix7fSuffix";
        System.out.println("slice: " +
                Integer.parseInt(source, 6, 8, 16));
        System.out.println("back to hex: " +
                Integer.toString(255, 16));

        System.out.println("unsigned int hex: " +
                Integer.toUnsignedString(-1, 16));
        System.out.println("unsigned long parsed: " +
                Long.toUnsignedString(
                        Long.parseUnsignedLong("ffffffffffffffff", 16)));

        expectFailure("prefix direct", "0xFF", 16);
        expectFailure("int overflow", "2147483648", 10);
        expectFailure("bad digit", "19", 8);
        expectFailure("spaces", " 42 ", 10);
        expectFailure("underscore", "1_000", 10);
        expectFailure("radix", "10", 1);

        // Các Unicode escapes là chữ số Arabic-Indic 1, 2, 3.
        System.out.println("unicode digit: " +
                Integer.parseInt("\u0661\u0662\u0663", 10));

        System.out.println("big integer: " +
                new BigInteger("FFFFFFFFFFFFFFFF", 16));
    }
}
```

Biên dịch và chạy:

```bash
javac ParseRadixDemo.java
java ParseRadixDemo
```

Đầu ra:

```text
decimal int: 120
decimal long: 9000000000
binary: 45
octal: 63
hex: 127
hex signed: -26
base36: 35
int min hex: -2147483648
long max hex: 9223372036854775807
long min hex: -9223372036854775808
hex prefix removed: 255
slice: 127
back to hex: ff
unsigned int hex: ffffffff
unsigned long parsed: 18446744073709551615
prefix direct: NumberFormatException
int overflow: NumberFormatException
bad digit: NumberFormatException
spaces: NumberFormatException
underscore: NumberFormatException
radix: NumberFormatException
unicode digit: 123
big integer: 18446744073709551615
```

Trong chương trình, những chuỗi sai được truyền vào `expectFailure` để bắt ngoại lệ và tiếp tục chạy các ví dụ sau. Còn những chuỗi hợp lệ được chuyển thành giá trị và in ra, cho thấy một số có thể được đọc từ nhiều cơ số khác nhau nhưng vẫn biểu diễn như số nguyên bình thường.

Đặc biệt, `Integer.parseInt(source, 6, 8, 16)` đọc đoạn có chỉ số từ 6 (bao gồm) đến 8 (không bao gồm) của `"prefix7fSuffix"`, tức `"7f"` ở hệ 16 có giá trị 127.

## 8. Overload đọc một đoạn CharSequence

Từ Java 9, ngoài việc parse cả chuỗi, Java hỗ trợ các overload:

```text
Integer.parseInt(CharSequence s, int beginIndex, int endIndex, int radix)
Long.parseLong(CharSequence s, int beginIndex, int endIndex, int radix)
```

Ví dụ:

```java
String input = "id=7F;status=ok";
int value = Integer.parseInt(input, 3, 5, 16);
System.out.println(value); // 127
```

Đoạn `[3, 5)` là `"7F"`. Cách này có thể tránh tạo `substring` trung gian khi xử lý một phần bộ đệm văn bản hoặc `CharSequence`. Nhưng với chuỗi nhỏ, `substring(...)` rồi parse cũng hoàn toàn phù hợp nếu cách đó dễ đọc hơn.

Khi sử dụng chỉ số, cần phân biệt **chỉ số ngoài phạm vi** hoặc khoảng chỉ số sai (có thể gây `IndexOutOfBoundsException`) với **nội dung đoạn không phải số hợp lệ** (gây `NumberFormatException`). Nếu đầu vào không đáng tin cậy, phải kiểm tra cả hai khả năng.

## 9. Parse số không dấu: khác với parse có dấu

Một số định dạng dữ liệu lưu các số nguyên dưới dạng **bit pattern không dấu**. Đó là trường hợp riêng với `parseInt`/`parseLong` thông thường.

- `Integer.parseUnsignedInt(s, radix)` chấp nhận giá trị từ 0 đến \(2^{32}-1\).
- `Long.parseUnsignedLong(s, radix)` chấp nhận giá trị từ 0 đến \(2^{64}-1\).
- `Integer.toUnsignedString(value, radix)` và `Long.toUnsignedString(value, radix)` hiển thị bit pattern theo cách hiểu không dấu.

Ví dụ:

```java
int bits = Integer.parseUnsignedInt("ffffffff", 16);
System.out.println(bits); // -1 nếu in như signed int
System.out.println(Integer.toUnsignedString(bits));
// 4294967295

long longBits = Long.parseUnsignedLong("ffffffffffffffff", 16);
System.out.println(Long.toUnsignedString(longBits));
// 18446744073709551615
```

Java vẫn lưu `bits` trong kiểu `int` và `longBits` trong `long`; không có kiểu nguyên thủy `uint` hoặc `ulong`. Khi in hay tính toán có dấu, bit pattern trên có thể xuất hiện dưới dạng số âm. Nếu ứng dụng muốn xử lý không dấu, cần dùng các phép so sánh/chia và định dạng unsigned tương ứng, hoặc chọn `BigInteger` khi cần xử lý số lớn theo cách thông thường.

**Không dùng `parseUnsignedInt` chỉ để né một lỗi dữ liệu.** Chỉ dùng khi hợp đồng đầu vào thật sự quy định giá trị không dấu.

## 10. Chuyển ngược từ số sang chuỗi theo cơ số

Hướng `parseInt`/`parseLong` là **chuỗi → số**. Hướng ngược lại là `Integer.toString(value, radix)` hoặc `Long.toString(value, radix)`:

```java
int number = 255;

System.out.println(Integer.toString(number));     // 255
System.out.println(Integer.toString(number, 2));  // 11111111
System.out.println(Integer.toString(number, 8));  // 377
System.out.println(Integer.toString(number, 16)); // ff
System.out.println(Integer.toString(number, 36)); // 73
```

Với số âm, cần hiểu sự khác nhau giữa **giá trị có dấu** và **bit pattern**:

```java
System.out.println(Integer.toString(-1, 16));          // -1
System.out.println(Integer.toHexString(-1));           // ffffffff
System.out.println(Integer.toUnsignedString(-1, 16));  // ffffffff
```

`toString(-1, 16)` giữ cách hiểu số âm có dấu. `toHexString(-1)` và `toUnsignedString(-1, 16)` thể hiện 32 bit như một giá trị không dấu.

Phép chuyển số rồi chuyển ngược **không bảo toàn hình thức chuỗi đầu vào**:

```java
int n = Integer.parseInt("000A", 16);
System.out.println(Integer.toString(n, 16)); // a
```

Các số `0` dẫn đầu và chữ `A` viết hoa đã biến mất. Nếu đó là thông tin nghiệp vụ (mã định danh, trường số có độ rộng cố định), hãy giữ chuỗi gốc hoặc áp dụng format riêng.

## 11. Chữ số Unicode và kiểm tra đầu vào

Việc phân tích chữ số của Java sử dụng cơ chế xác định chữ số theo `Character.digit`. Một số chữ số Unicode ngoài dải ASCII cũng được chấp nhận, ví dụ:

```java
int n = Integer.parseInt("\u0661\u0662\u0663", 10);
System.out.println(n); // 123
```

Dãy escape tương ứng với ba chữ số Arabic-Indic 1, 2, 3. Điều này **không có nghĩa** mọi ký tự số trên thế giới đều được parser chấp nhận, hay parser tự xử lý dấu phân nhóm và dấu thập phân trong một locale.

Nếu định dạng giao thức bắt buộc chỉ chứa chữ số ASCII từ `'0'` đến `'9'`, cần kiểm tra chính sách đó riêng trước khi parse. Ngược lại, với nhập liệu quốc tế, không mặc định chỉ có chữ số ASCII hợp lệ. `Integer.parseInt` và `Long.parseLong` phân tích số nguyên theo cơ số, **không thay thế bộ phân tích số được địa phương hóa**.

## 12. Parse số và kiểm tra quy tắc nghiệp vụ

Một chuỗi parse thành `int` hợp lệ vẫn có thể không hợp lệ đối với ứng dụng. Ví dụ số cổng TCP phải nằm trong khoảng được hệ thống quy định, không phải mọi giá trị `int` đều là số cổng hợp lệ.

```java
static int parsePort(String raw) {
    final int port;
    try {
        port = Integer.parseInt(raw);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "Cổng phải là số nguyên hợp lệ", ex);
    }

    if (port < 1 || port > 65535) {
        throw new IllegalArgumentException(
                "Cổng phải nằm trong khoảng 1..65535");
    }
    return port;
}
```

Đây là **phương thức minh họa** đặt trong một lớp Java; nó không phải chương trình độc lập. Mã kiểm tra cú pháp/miền `int` qua `parseInt`, sau đó kiểm tra quy tắc nghiệp vụ của cổng trong đoạn 1–65535.

Ngoài ra, phân biệt `Integer.parseInt` (trả kiểu nguyên thủy `int`) với `Integer.valueOf` (trả đối tượng `Integer`), và `Long.parseLong` (trả `long`) với `Long.valueOf` (trả `Long`). Các overload chuỗi/cơ số có cùng ý nghĩa phân tích số nhưng khác loại kết quả. Nếu chỉ cần phép tính số nguyên thủy, `parseInt`/`parseLong` diễn đạt trực tiếp mục đích hơn.

## 13. Bài tập tự kiểm tra

Hãy dự đoán trước khi chạy:

| Biểu thức | Kết quả |
| --- | --- |
| `Integer.parseInt("0012")` | `12` |
| `Integer.parseInt("010", 10)` | `10` |
| `Integer.parseInt("010", 2)` | `2` |
| `Integer.parseInt("+7f", 16)` | `127` |
| `Integer.parseInt("Z", 36)` | `35` |
| `Integer.parseInt("19", 8)` | `NumberFormatException` |
| `Integer.parseInt("2147483648")` | `NumberFormatException` |
| `Long.parseLong("2147483648")` | `2147483648` |
| `Integer.parseInt("0x10", 16)` | `NumberFormatException` |
| `Integer.toString(31, 16)` | `"1f"` |
| `Integer.toString(-31, 16)` | `"-1f"` |

Thử tự xây dựng chức năng nhận hai chuỗi đầu vào: số dạng văn bản và một lựa chọn cơ số 2, 8, 10 hoặc 16. Parse thành `int`, bắt `NumberFormatException` để báo lỗi rõ ràng, sau đó in kết quả bằng `Integer.toString(value, 10)`. Kiểm thử số âm, chữ số sai cơ số, chuỗi trống, khoảng trắng, tiền tố `0x` và tràn miền. Sau đó mở rộng sang `long` để so sánh.

## 14. Ghi nhớ

- `Integer.parseInt(s)` và `Long.parseLong(s)` đọc số nguyên **có dấu theo hệ 10**; kiểu trả về lần lượt là `int` và `long`.
- Overload nhận `radix` hỗ trợ **cơ số 2–36**, giúp diễn giải nhị phân, bát phân, thập lục phân và các cơ số khác.
- Chữ số phải hợp lệ theo cơ số, và **giá trị phải nằm trong miền kiểu đích**; sai cú pháp, cơ số hoặc vượt phạm vi gây `NumberFormatException`.
- Dấu `+`, `-` đầu chuỗi được hỗ trợ; tiền tố `0x`/`0b`, gạch dưới, khoảng trắng, dấu phân nhóm hoặc phần thập phân không được parse trực tiếp.
- `Long.parseLong` có miền rộng hơn `Integer.parseInt`; số nguyên vượt `long` cần `BigInteger` hoặc mô hình dữ liệu khác.
- Với **bit pattern không dấu**, dùng các API `parseUnsignedInt`/`parseUnsignedLong` tương ứng; đừng lẫn ý nghĩa unsigned với signed.
- `Integer.toString(value, radix)` và `Long.toString(value, radix)` chuyển số trở lại chuỗi nhưng không phục hồi định dạng nguyên bản như các số `0` ở đầu.
