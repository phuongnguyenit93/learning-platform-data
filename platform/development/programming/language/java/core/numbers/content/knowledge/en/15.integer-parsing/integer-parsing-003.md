# Radix, dấu cộng hoặc trừ và phạm vi hợp lệ khi phân tích số nguyên trong Java

Khi nhận một số nguyên dưới dạng `String`, Java phải trả lời ba câu hỏi độc lập: **chuỗi dùng hệ cơ số nào (radix)?**, **dấu đứng ở đâu và có hợp lệ không?**, **giá trị toán học có nằm trong phạm vi của kiểu đích không?** Đọc đúng các ký tự vẫn chưa đủ: một chuỗi chỉ gồm chữ số hợp lệ có thể bị từ chối vì tràn phạm vi. Bài này tập trung vào `Integer.parseInt`, `Long.parseLong` và các lựa chọn phù hợp khi dữ liệu không còn là số nguyên có dấu thông thường.

## 1. Radix là gì?

Radix (cơ số) quyết định tập chữ số được phép dùng và giá trị của từng vị trí. Với chuỗi các chữ số \(d_k\dots d_1d_0\) trong cơ số \(r\), phần trị tuyệt đối là:

\[
|n|=\sum_{i=0}^{k} d_i r^i,\qquad 0\le d_i<r.
\]

Ví dụ, `"1A"` ở hệ 16 có giá trị \(1\times16+10=26\); `"101101"` ở hệ 2 có giá trị \(32+8+4+1=45\). Cùng một chuỗi `"10"` có giá trị 2 trong hệ 2, 10 trong hệ 10, và 16 trong hệ 16.

Trong các phương thức parse có tham số `radix`, Java hỗ trợ cơ số **từ 2 đến 36**, tương ứng `Character.MIN_RADIX` và `Character.MAX_RADIX`. Chữ số `0`–`9` mang giá trị 0–9; chữ cái `a`–`z` hoặc `A`–`Z` mang giá trị 10–35 khi cơ số đủ lớn. Do đó `F` hợp lệ ở hệ 16, còn `G` không hợp lệ ở hệ 16 (nhưng hợp lệ ở hệ 17 trở lên).

| Radix | Ký tự điển hình | Ví dụ và giá trị thập phân |
| --- | --- | --- |
| 2 (binary) | `0`, `1` | `101101` → 45 |
| 8 (octal) | `0`–`7` | `17` → 15 |
| 10 (decimal) | `0`–`9` | `17` → 17 |
| 16 (hexadecimal) | `0`–`9`, `A`–`F` | `7F` → 127 |
| 36 | `0`–`9`, `A`–`Z` | `Z` → 35 |

API cơ bản:

```java
int decimal = Integer.parseInt("255");       // mặc định radix 10
int binary  = Integer.parseInt("11111111", 2); // 255
int hex     = Integer.parseInt("ff", 16);      // 255
long big    = Long.parseLong("7fffffffffffffff", 16); // Long.MAX_VALUE
```

`Integer.parseInt(String)` **luôn dùng hệ 10**. `Integer.parseInt(String, int)` dùng chính xác cơ số được truyền; Java không tự suy ra radix từ tiền tố hay từ số 0 đứng đầu.

## 2. Dấu cộng, dấu trừ và cú pháp chuỗi

Với cách viết ASCII thông thường, dạng hợp lệ của `parseInt`/`parseLong` là:

```text
[+|-]? <ít nhất một chữ số hợp lệ trong radix>
```

- Dấu `+` hoặc `-` là **tùy chọn** và chỉ được đứng ở ký tự đầu tiên. `"+7F"` (radix 16) cho 127; `"-7F"` cho -127; `"-"` và `"+"` đơn lẻ không hợp lệ.
- Dấu chỉ tác động lên giá trị của toàn bộ dãy chữ số. `"-101"` (radix 2) là **-5**, không phải một mẫu bit two's complement tự động được diễn giải thành số âm.
- `"0"`, `"+0"` và `"-0"` đều phân tích thành giá trị số 0. Số 0 đứng đầu được chấp nhận nhưng **không biến chuỗi thành hệ 8**: `Integer.parseInt("010")` cho 10.
- Khoảng trắng, dấu phẩy, dấu chấm, dấu gạch dưới và ký tự thừa không được tự bỏ qua: `" 42"`, `"42 "`, `"1_000"`, `"1,000"` và `"42L"` đều không hợp lệ với `parseInt`.
- `Integer.parseInt("0xFF", 16)` và `Integer.parseInt("0b1010", 2)` đều thất bại vì `x`/`b` trong các chuỗi này không phải chữ số hợp lệ tại vị trí tương ứng. Nếu tự chọn radix, chỉ truyền phần chữ số như `"FF"` và `"1010"`.
- Chữ cái thường/hoa tương đương ở các radix chứa chữ cái: `"aF"` và `"Af"` trong hệ 16 đều là 175.
- Radix ngoài đoạn 2–36, chữ số có giá trị lớn hơn hoặc bằng radix, chuỗi rỗng và `null` đều dẫn đến `NumberFormatException` ở `Integer.parseInt(String, int)`.

**Chi tiết Unicode:** `parseInt` dùng logic chữ số dựa trên `Character.digit(char, radix)`, vì thế một số ký tự chữ số Unicode ngoài ASCII cũng có thể được chấp nhận. Nếu giao thức dữ liệu chỉ cho phép `[0-9A-Za-z]` hoặc chỉ chữ số ASCII, cần **kiểm tra định dạng riêng trước khi parse**. Không suy diễn rằng `parseInt` đồng nghĩa với một bộ kiểm tra ASCII nghiêm ngặt.

### Bảng các tình huống thường gây nhầm lẫn

| Lời gọi | Kết quả | Giải thích |
| --- | --- | --- |
| `Integer.parseInt("+101", 2)` | `5` | Dấu cộng hợp lệ ở đầu |
| `Integer.parseInt("-101", 2)` | `-5` | Dấu âm áp lên trị số |
| `Integer.parseInt("077")` | `77` | Mặc định vẫn là hệ 10 |
| `Integer.parseInt("077", 8)` | `63` | Đã yêu cầu hệ 8 |
| `Integer.parseInt("7f", 16)` | `127` | `f` = 15 |
| `Integer.parseInt("2", 2)` | Lỗi | `2` không phải chữ số hệ 2 |
| `Integer.parseInt("0xFF", 16)` | Lỗi | Không tự nhận tiền tố `0x` |
| `Integer.parseInt("--5")` | Lỗi | Chỉ cho phép một dấu ở đầu |
| `Integer.parseInt("1_000")` | Lỗi | Dấu `_` không được parse từ chuỗi |
| `Integer.parseInt(" 5 ")` | Lỗi | Không tự `trim()` |

Không nên vô điều kiện gọi `trim()`/`strip()` chỉ để “làm cho parse thành công”. Hãy quyết định rõ hợp đồng đầu vào: với dữ liệu người dùng có thể cho phép khoảng trắng ở hai đầu; với mã định danh hoặc dữ liệu máy cần giữ chặt định dạng gốc.

## 3. Phạm vi giá trị: đúng chữ số vẫn có thể bị từ chối

`int` và `long` của Java là số nguyên **có dấu**. Radix chỉ thay đổi cách biểu diễn, **không thay đổi phạm vi chứa được**.

| Kiểu | Độ rộng | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | --- | --- | --- |
| `byte` | 8 bit | -128 | 127 |
| `short` | 16 bit | -32 768 | 32 767 |
| `int` | 32 bit | -2 147 483 648 | 2 147 483 647 |
| `long` | 64 bit | -9 223 372 036 854 775 808 | 9 223 372 036 854 775 807 |

Về toán học, một kiểu số nguyên có dấu rộng \(w\) bit có miền \([-2^{w-1},\,2^{w-1}-1]\). Do đó **biên âm có trị tuyệt đối lớn hơn biên dương 1 đơn vị**.

Những ví dụ then chốt của `Integer.parseInt`:

```java
Integer.parseInt("2147483647");       // hợp lệ: Integer.MAX_VALUE
Integer.parseInt("-2147483648");      // hợp lệ: Integer.MIN_VALUE

Integer.parseInt("2147483648");       // NumberFormatException
Integer.parseInt("-2147483649");      // NumberFormatException

Integer.parseInt("7fffffff", 16);     //  2147483647, hợp lệ
Integer.parseInt("-80000000", 16);    // -2147483648, hợp lệ
Integer.parseInt("80000000", 16);     // NumberFormatException
Integer.parseInt("-80000001", 16);    // NumberFormatException
```

`"80000000"` trong hệ 16 có giá trị **dương** 2 147 483 648, vượt `int` có dấu. Java không tự bọc vòng (wrap) thành -2 147 483 648 khi gọi `parseInt`; đây là lỗi phạm vi. Tương tự, chuỗi 64-bit lớn hơn `Long.MAX_VALUE` không thể parse bằng `Long.parseLong` thông thường dù các chữ số hoàn toàn hợp lệ.

Về cơ chế, parser phải kiểm tra tràn trong lúc nhân giá trị tích lũy với radix rồi thêm chữ số tiếp theo. JDK có thể tích lũy ở phía âm để xử lý an toàn cả `Integer.MIN_VALUE`, vì giá trị `2147483648` không biểu diễn được bằng `int` dương. Đây là lý do không nên tự viết parser bằng phép tính `int result = result * radix + digit` rồi chỉ kiểm tra phạm vi ở cuối: phép tính có thể đã tràn trước khi kiểm tra.

Đối với `byte` và `short`, dùng `Byte.parseByte`/`Short.parseShort`; chúng áp dụng miền tương ứng. Parse vào `int` rồi ép kiểu `(byte)` hoặc `(short)` có thể âm thầm mất dữ liệu:

```java
Byte.parseByte("128");  // NumberFormatException: quá 127
byte lost = (byte) Integer.parseInt("128"); // -128 vì bị thu hẹp kiểu
```

Khi cần từ chối dữ liệu ngoài phạm vi, hãy dùng parser đúng kiểu hoặc kiểm tra biên trước khi chuyển kiểu.

## 4. Phân biệt chuỗi runtime, literal Java và tự nhận diện tiền tố

Ba cơ chế thường bị lẫn:

1. **Literal trong mã nguồn** do trình biên dịch Java đọc: `10` (thập phân), `010` (bát phân), `0x10` (thập lục phân), `0b10` (nhị phân). Từ Java 7, literal còn có thể chứa `_` ở các vị trí hợp lệ, ví dụ `1_000`.
2. **`Integer.parseInt(text, radix)`** đọc một chuỗi runtime với radix đã định. Nó không áp dụng cú pháp literal: `"010"` với radix 10 là 10 và `"1_000"` không hợp lệ.
3. **`Integer.decode(text)`** nhận diện một số tiền tố theo quy tắc riêng: `0x`/`0X` hoặc `#` cho hệ 16, số `0` đứng đầu (với nhiều hơn một chữ số) cho hệ 8, còn lại dùng hệ 10. Có thể có `+`/`-` **trước tiền tố**, ví dụ `"-0x2A"` → -42; đặt dấu sau tiền tố như `"0x-2A"` không hợp lệ.

Ví dụ:

```java
Integer.parseInt("010");     // 10
Integer.parseInt("010", 8);  // 8
Integer.decode("010");       // 8
Integer.decode("0x10");      // 16
Integer.decode("#10");       // 16
Integer.decode("-0x2A");     // -42
Integer.decode("08");        // NumberFormatException: 8 không thuộc hệ 8
```

Chọn `decode` khi **đặc tả đầu vào thực sự cho phép** kiểu tiền tố trên. Với dữ liệu cần hệ 10 nhất quán, nên dùng `parseInt(text, 10)` để tránh việc `"010"` bất ngờ mang nghĩa hệ 8. `decode` cũng chịu giới hạn `int` có dấu; nó không giải quyết lỗi tràn.

Một khác biệt tinh tế: `0xFFFFFFFF` viết trực tiếp như một literal `int` có thể biểu diễn mẫu bit -1 theo quy tắc literal của Java, nhưng `Integer.parseInt("FFFFFFFF", 16)` vẫn từ chối vì đây là chuỗi biểu diễn **giá trị dương** 4 294 967 295, vượt `Integer.MAX_VALUE`.

## 5. Khi chuỗi biểu diễn một giá trị unsigned hoặc số lớn

Trong Java, kiểu nguyên thủy `int` và `long` vẫn lưu theo dạng có dấu. Nếu đặc tả dữ liệu là số nguyên **không dấu** (unsigned), dùng API parse unsigned tương ứng, rồi diễn giải kết quả cho đúng:

```java
int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
// bits == -1 nếu nhìn như int có dấu, nhưng bit pattern là 0xFFFFFFFF

long unsignedValue = Integer.toUnsignedLong(bits); // 4294967295
String decimal = Integer.toUnsignedString(bits);   // "4294967295"
String hex = Integer.toUnsignedString(bits, 16);    // "ffffffff"
```

`Integer.parseUnsignedInt` cho miền số học 0 đến \(2^{32}-1\), còn `Long.parseUnsignedLong` cho 0 đến \(2^{64}-1\). Giá trị trả về vẫn là `int`/`long` nguyên thủy, vì vậy các giá trị có bit dấu bật sẽ hiển thị như số âm nếu dùng `System.out.println(bits)` hoặc các phép toán signed thông thường.

`Integer.parseUnsignedInt("-1", 10)` không hợp lệ: dấu âm không phù hợp với miền unsigned. Sau khi parse, dùng các API có chữ `Unsigned` khi cần so sánh, chia hoặc định dạng theo ngữ nghĩa unsigned (`Integer.compareUnsigned`, `Integer.divideUnsigned`, `Integer.toUnsignedString`...). Với `long` unsigned vượt `Long.MAX_VALUE`, muốn xử lý như một số dương lớn trong tính toán thường dùng `BigInteger`, chẳng hạn:

```java
BigInteger maxUnsignedLong =
        new BigInteger("FFFFFFFFFFFFFFFF", 16); // 18446744073709551615
```

Khi số có thể lớn hơn miền `int`, `long` hoặc `unsigned long`, dùng `java.math.BigInteger(String value, int radix)`. `BigInteger` vẫn yêu cầu chuỗi chữ số hợp lệ với radix và dấu ở đầu; nó không tự chấp nhận `"0x"` khi đã truyền radix 16. Không có giới hạn cố định 32/64 bit như kiểu nguyên thủy, nhưng vẫn phải để ý giới hạn bộ nhớ/tài nguyên với đầu vào quá dài.

### Chọn API theo hợp đồng đầu vào

| Đầu vào cần đọc | API nên dùng | Điều cần ghi nhớ |
| --- | --- | --- |
| Số có dấu hệ 10 trong miền 32 bit | `Integer.parseInt(text)` | Không chấp nhận tiền tố hoặc phân cách |
| Số có dấu hệ 2–36 trong miền 32 bit | `Integer.parseInt(text, radix)` | Dấu đầu chuỗi, kiểm tra radix và tràn |
| Số có dấu trong miền 64 bit | `Long.parseLong(text, radix)` | Giới hạn của `long` |
| Văn bản cho phép `0x`, `#`, số 0 đầu | `Integer.decode(text)` | `010` trở thành hệ 8 |
| Số không dấu 32 bit | `Integer.parseUnsignedInt(text, radix)` | Kết quả là `int` chứa bit pattern |
| Số không dấu 64 bit | `Long.parseUnsignedLong(text, radix)` | Kết quả là `long` chứa bit pattern |
| Số nguyên tùy độ lớn | `new BigInteger(text, radix)` | Không giới hạn cố định 32/64 bit |

## 6. Chương trình Java 17+ hoàn chỉnh có thể chạy

Lưu thành **`RadixParsingDemo.java`**:

```java
import java.math.BigInteger;

public class RadixParsingDemo {
    public static void main(String[] args) {
        show("101101", 2);
        show("+7f", 16);
        show("-80000000", 16);
        show("80000000", 16);
        show("2", 2);

        System.out.println("decode -0x2A = " + Integer.decode("-0x2A"));
        System.out.println("parseInt 010 = " + Integer.parseInt("010"));
        System.out.println("decode 010 = " + Integer.decode("010"));

        int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
        System.out.println("uint bits = " + bits);
        System.out.println("uint value = " + Integer.toUnsignedLong(bits));

        BigInteger beyondInt = new BigInteger("100000000", 16);
        System.out.println("big = " + beyondInt);
        System.out.println("format = " + Integer.toString(255, 16));
    }

    private static void show(String input, int radix) {
        try {
            int value = Integer.parseInt(input, radix);
            System.out.println("\"" + input + "\" base " + radix + " -> " + value);
        } catch (NumberFormatException ex) {
            // Thông báo tự định nghĩa để ví dụ không phụ thuộc cách JDK diễn đạt lỗi.
            System.out.println("\"" + input + "\" base " + radix + " -> INVALID");
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 RadixParsingDemo.java
java RadixParsingDemo
```

Stdout kỳ vọng:

```text
"101101" base 2 -> 45
"+7f" base 16 -> 127
"-80000000" base 16 -> -2147483648
"80000000" base 16 -> INVALID
"2" base 2 -> INVALID
decode -0x2A = -42
parseInt 010 = 10
decode 010 = 8
uint bits = -1
uint value = 4294967295
big = 4294967296
format = ff
```

Trong ví dụ, `show()` phân biệt dữ liệu hợp lệ với dữ liệu sai chữ số hoặc vượt phạm vi bằng cách bắt `NumberFormatException`. Cả `"80000000"` (sai phạm vi signed int) và `"2"` trong hệ 2 (sai chữ số) đều bị từ chối; nếu ứng dụng cần thông báo chính xác nguyên nhân, phải kiểm tra thêm định dạng, radix và phạm vi theo quy tắc nghiệp vụ. Không nên dựa vào nguyên văn thông báo lỗi của JDK để phân loại vì thông báo có thể khác giữa các phiên bản.

## 7. Thiết kế lớp nhập liệu tin cậy

Để xử lý đầu vào từ biểu mẫu, CSV, giao thức mạng hoặc tệp cấu hình:

1. **Xác định hợp đồng trước:** hệ cơ số cố định hay có tiền tố? Có cho phép dấu `+`? Có chấp nhận âm? Có chấp nhận số 0 đầu, khoảng trắng, chữ số Unicode, phân cách hàng nghìn không? Có giới hạn độ dài không?
2. **Chuẩn hóa có chủ đích:** chỉ `strip()` khoảng trắng khi hợp đồng cho phép. Nếu phải chấp nhận ký hiệu như `0x`, hãy nhận diện, bỏ tiền tố và chọn radix theo quy tắc của giao thức; hoặc dùng `decode` nếu quy tắc của nó trùng khớp.
3. **Kiểm tra radix và cú pháp:** radix thuộc 2–36. Nếu chỉ chấp nhận ASCII hex có dấu, ví dụ có thể kiểm tra chuỗi bằng `[+-]?[0-9A-Fa-f]+`; với radix khác cần kiểm tra giá trị từng chữ số tương ứng (hoặc để parser kiểm tra).
4. **Dùng parser đúng miền số:** parse vào `int`/`long` khi miền ứng dụng phù hợp; dùng unsigned API cho đại lượng không dấu; dùng `BigInteger` khi cần biểu diễn vượt 64 bit.
5. **Xử lý lỗi rõ ràng:** bắt `NumberFormatException` ở biên nhập liệu, thông báo giá trị không hợp lệ cho người dùng hoặc trả lỗi có cấu trúc. Không âm thầm đổi lỗi thành `0` vì sẽ lẫn với dữ liệu `"0"` thật.
6. **Giới hạn tài nguyên:** với đầu vào không tin cậy, giới hạn độ dài trước khi parse, nhất là trước khi tạo `BigInteger`; tránh cấp phát/kiểm tra khối dữ liệu khổng lồ không cần thiết.

Một helper giữ nguyên chính sách “ASCII hex có thể có dấu, không có tiền tố”, rồi ủy quyền kiểm tra phạm vi cho `parseInt`:

```java
static int parseAsciiHexSignedInt(String text) {
    if (text == null || !text.matches("[+-]?[0-9A-Fa-f]+")) {
        throw new IllegalArgumentException("Yêu cầu chuỗi hex ASCII có thể có dấu");
    }
    return Integer.parseInt(text, 16);
}
```

Đoạn helper này **không phải một chương trình chạy độc lập**: đặt nó bên trong một class phù hợp. Regex kiểm tra **cú pháp ASCII**, còn `Integer.parseInt` kiểm tra **giá trị có vừa `int` signed hay không**. `IllegalArgumentException` do helper ném ra dành cho cú pháp; `NumberFormatException` của parser vẫn dùng cho tràn phạm vi. Vì `String.matches` sẽ biên dịch regex mỗi lần gọi, với đường xử lý lặp thường xuyên có thể khai báo trước một `Pattern` và dùng `matcher(text).matches()`.

Nếu hợp đồng đầu vào cho phép Unicode digits theo Java, không nên dùng regex ASCII như trên. Nếu hợp đồng bắt buộc radix 10 và giới hạn 0–100, kiểm tra phạm vi nghiệp vụ sau khi parse (`0 <= value && value <= 100`) ngoài phạm vi kỹ thuật của `int`.

## 8. Các lỗi thường gặp và cách tự kiểm tra

- **Nhầm radix với phạm vi:** đổi từ radix 10 sang 16 không làm `int` chứa được số lớn hơn; nó chỉ thay cách viết.
- **Nhầm dấu âm với bit dấu:** `"-FF"` là -255, còn `"FFFFFFFF"` là số dương 4 294 967 295 về mặt văn bản; muốn đọc mẫu bit unsigned, dùng `parseUnsignedInt`.
- **Tưởng tiền tố luôn được hiểu:** `parseInt("0xFF", 16)` không hợp lệ, nhưng `decode("0xFF")` hợp lệ.
- **Áp dụng luật literal cho String:** `1_000` hợp lệ trong mã Java, còn `"1_000"` không thể parse trực tiếp.
- **Coi mọi số có số 0 đầu là octal:** chỉ cách diễn giải như `decode` (và một số literal) có quy tắc đó; `parseInt("010")` vẫn là 10.
- **Cắt dữ liệu qua cast:** `(byte) 128` thành -128; đây không phải kiểm tra phạm vi.
- **Tin rằng chữ số đúng luôn parse được:** `"2147483648"` chỉ chứa ký tự hợp lệ hệ 10 nhưng vẫn vượt `int`.
- **Bắt `Exception` quá rộng hoặc dùng mặc định 0:** đánh mất nguyên nhân và làm hỏng ý nghĩa dữ liệu.

Tự đối chiếu nhanh trước khi gọi parser: **radix ∈ [2,36] → dấu (nếu có) chỉ đứng đầu → còn ít nhất một chữ số → mọi chữ số thuộc radix → giá trị nằm trong miền kiểu đích**. Sau đó mới quyết định số nguyên đang là signed, unsigned hay cần `BigInteger`. Chuỗi đầu vào, cách hiển thị bit và miền giá trị là ba vấn đề khác nhau; tách chúng giúp tránh hầu hết lỗi phân tích số nguyên trong Java.