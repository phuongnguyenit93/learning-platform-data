# `Integer.toString`, `Long.toString` và `radix` trong Java

Java lưu các giá trị `int` và `long` dưới dạng số nguyên nhị phân có dấu. Khi chương trình cần hiển thị ra màn hình, ghi log, trao đổi dữ liệu hoặc xuất văn bản theo hệ 2, 8, 10, 16..., ta phải **định dạng giá trị số thành `String`**. `Integer.toString` và `Long.toString` là hai API cơ bản thực hiện việc này.

```java
int number = 42;

System.out.println(Integer.toString(number));      // 42
System.out.println(Integer.toString(number, 2));   // 101010
System.out.println(Integer.toString(number, 8));   // 52
System.out.println(Integer.toString(number, 16));  // 2a
```

Cả bốn kết quả là các **chuỗi khác nhau biểu diễn cùng giá trị số nguyên 42**. Tham số `radix` quyết định **cơ số khi chuyển thành chữ số**, không biến đổi giá trị gốc của biến và không tạo thêm tiền tố như `0x`. Với số âm, còn có sự khác biệt quan trọng giữa định dạng **giá trị có dấu** bằng `toString(value, radix)` và định dạng **mẫu bit không dấu** bằng `toHexString`, `toBinaryString` hay `toUnsignedString`.

Bài này tập trung vào hợp đồng của hai phương thức, các cơ số hợp lệ, âm/dương và giá trị biên, mối quan hệ với parser, những cách định dạng có tiền tố/độ rộng, và các lỗi thường gặp khi lưu hoặc truyền số.

## 1. Giá trị số khác với cách viết số

Giả sử chương trình có:

```java
int a = 42;
int b = 0x2A;
int c = 0b101010;
int d = 052;
```

Trong Java source, compiler hiểu bốn **integer literal** theo cơ số 10, 16, 2 và 8. Nhưng tất cả biến ở đây đều chứa giá trị số học **42**. Một biến `int` **không lưu ký ức** rằng nó được gán bằng literal hex hay binary.

`Integer.toString(a, 16)`, `Integer.toString(b, 16)`, `Integer.toString(c, 16)` và `Integer.toString(d, 16)` đều trả `"2a"`. Phương thức không tìm lại cú pháp literal ban đầu: nó nhận **giá trị**, sau đó xây chuỗi chữ số theo cơ số yêu cầu.

### Các khái niệm cần phân biệt

| Khái niệm | Ví dụ | Giai đoạn và tác dụng |
| --- | --- | --- |
| Numeric literal | `0x2A`, `0b101010`, `42` | Cú pháp mã nguồn, do compiler phân tích |
| Primitive numeric value | `int value = 42;` | Giá trị số học được thao tác khi chạy |
| Numeric formatting | `Integer.toString(value, 16)` | Tạo `String` biểu diễn giá trị theo cơ số 16 |
| Numeric parsing | `Integer.parseInt("2a", 16)` | Đọc `String` theo cơ số và tạo giá trị `int` |
| Unsigned bit formatting | `Integer.toHexString(-1)` | Diễn giải mẫu 32 bit theo cách không dấu |

**Định dạng và phân tích là hai chiều khác nhau.** Không nên dùng `parseInt` khi mục tiêu là *hiển thị* số; cũng không dùng `toString` để *kiểm tra* một chuỗi đầu vào.

## 2. Các overload quan trọng

`Integer` và `Long` nằm trong `java.lang` nên không cần import riêng.

| API | Tham số | Kiểu trả về | Ý nghĩa |
| --- | --- | --- | --- |
| `Integer.toString(int value)` | Một `int` | `String` | Biểu diễn thập phân có dấu |
| `Integer.toString(int value, int radix)` | Giá trị và cơ số | `String` | Biểu diễn có dấu trong cơ số yêu cầu |
| `Long.toString(long value)` | Một `long` | `String` | Biểu diễn thập phân có dấu |
| `Long.toString(long value, int radix)` | Giá trị và cơ số | `String` | Biểu diễn có dấu trong cơ số yêu cầu |

```java
int count = -42;
long distance = 4_294_967_296L;

String a = Integer.toString(count);       // "-42"
String b = Integer.toString(count, 16);   // "-2a"
String c = Long.toString(distance);       // "4294967296"
String d = Long.toString(distance, 16);   // "100000000"
```

Phân biệt tên lớp theo kiểu dữ liệu: `Long.toString` nhận `long` và xử lý được miền rộng hơn `int`. Bạn **không** thể kỳ vọng gọi `Integer.toString((int) someLong)` giữ nguyên một giá trị `long` vượt giới hạn `int`, bởi thông tin có thể mất ở **phép cast trước lời gọi**.

Các phương thức trên là `static`: dùng `Integer.toString(...)` hoặc `Long.toString(...)`. Không cần tạo `new Integer(...)`/`new Long(...)` để định dạng.

### `String.valueOf` và nối chuỗi là gì?

`String.valueOf(42)`, `Integer.toString(42)` và `"" + 42` thường cho chuỗi `"42"` theo hệ 10. Nhưng:

- `String.valueOf(int)`/`String.valueOf(long)` không có tham số `radix`.
- `Integer.toString(value, radix)` diễn đạt rõ ý muốn chọn hệ cơ số khác.
- `Integer.valueOf(int)` lại **tạo/lấy đối tượng wrapper `Integer`**, không phải tạo chuỗi.
- `Integer.toString()` gọi trên **đối tượng wrapper** là phương thức instance không tham số; còn `Integer.toString(int)` là phương thức static. Đừng nhầm chữ ký.

Trong mã muốn hiển thị binary/hex một cách tường minh, chọn `toString(value, radix)` hoặc API chuyên biệt phù hợp ngữ nghĩa có dấu/không dấu.

## 3. `radix`: cơ số 2 đến 36

`radix` là cơ số dùng để diễn đạt một số bằng các chữ số. Với hai overload nhận radix của `Integer.toString` và `Long.toString`, các giá trị hợp lệ là:

```java
Character.MIN_RADIX // 2
Character.MAX_RADIX // 36
```

Java dùng các ký tự chữ số:

```text
0 1 2 3 4 5 6 7 8 9 a b c ... z
```

- Với radix 2: `0`, `1`.
- Với radix 8: `0` đến `7`.
- Với radix 10: `0` đến `9`.
- Với radix 16: `0` đến `9` và `a` đến `f`.
- Với radix 36: `0` đến `9` và `a` đến `z`.

Các chữ cái trong chuỗi do hai phương thức tạo ra là **chữ thường** (`a..z`).

```java
System.out.println(Integer.toString(42, 2));   // 101010
System.out.println(Integer.toString(42, 8));   // 52
System.out.println(Integer.toString(42, 10));  // 42
System.out.println(Integer.toString(42, 16));  // 2a
System.out.println(Integer.toString(35, 36));  // z
```

**Không có radix 1, 0, 37 hay −2** trong API này. Một điểm không hiển nhiên: `toString(value, radix)` **không ném `NumberFormatException` khi radix ngoài 2–36**; thay vào đó, nó **dùng thập phân (radix 10)** theo hợp đồng JDK.

```java
System.out.println(Integer.toString(255, 1));  // 255, fallback radix 10
System.out.println(Long.toString(255L, 37));   // 255, fallback radix 10
```

Vì cơ số sai có thể bị che khuất, một ứng dụng nhận `radix` từ người dùng nên **tự kiểm tra phạm vi**:

```java
static String formatStrictRadix(int value, int radix) {
    if (radix < Character.MIN_RADIX || radix > Character.MAX_RADIX) {
        throw new IllegalArgumentException("radix must be from 2 to 36");
    }
    return Integer.toString(value, radix);
}
```

Đây là hàm minh họa cần đặt trong class. Nó xây dựng chính sách **báo lỗi rõ ràng khi radix sai**, chặt hơn lựa chọn fallback thập phân của `Integer.toString`.

### `radix` không làm đổi số

Một số nguyên `42` vẫn là `42` dù được hiển thị `101010`, `52` hay `2a`. Chỉ chuỗi kết quả khác. Muốn đưa chuỗi trở về giá trị, parser phải biết đúng cơ số tương ứng:

```java
int original = 42;
String encoded = Integer.toString(original, 16);  // "2a"
int decoded = Integer.parseInt(encoded, 16);      // 42
```

Nếu `Integer.parseInt("2a")` được gọi không có radix 16, nó sẽ ném `NumberFormatException` vì parser mặc định thập phân và ký tự `a` không hợp lệ trong radix 10.

## 4. Các trường hợp số 0, số dương và số âm

### Giá trị 0

```java
System.out.println(Integer.toString(0));       // "0"
System.out.println(Integer.toString(0, 2));    // "0"
System.out.println(Long.toString(0L, 36));     // "0"
```

Số 0 luôn có biểu diễn chuỗi `"0"` trong các radix hợp lệ; không có chuỗi rỗng hoặc dấu âm.

### Số âm: dấu `-` đi trước các chữ số

```java
System.out.println(Integer.toString(-42));      // -42
System.out.println(Integer.toString(-42, 2));   // -101010
System.out.println(Integer.toString(-42, 16));  // -2a
System.out.println(Long.toString(-42L, 36));    // -16
```

`Integer.toString(-42, 16)` trả **`"-2a"`**, không trả chuỗi mẫu bit 32-bit của số âm. Phần chữ số `2a` biểu diễn **độ lớn 42**, còn `-` diễn đạt dấu. Vì vậy hai chuỗi:

- `Integer.toString(-1, 16)` → `"-1"`;
- `Integer.toHexString(-1)` → `"ffffffff"`;

đều liên quan đến cùng giá trị `int -1` nhưng **khác quy ước hiển thị**.

### Giá trị biên `MIN_VALUE` có được xử lý đúng?

```java
System.out.println(Integer.toString(Integer.MIN_VALUE));
// -2147483648
System.out.println(Long.toString(Long.MIN_VALUE));
// -9223372036854775808
```

`Integer.MIN_VALUE` bằng `-2^31`, `Long.MIN_VALUE` bằng `-2^63`. Giá trị dương tương ứng không biểu diễn được trong cùng kiểu signed. Các phương thức `toString` của JDK **xử lý đúng** hai giá trị này. Không tự cài đặt formatter bằng cách lấy `Math.abs(value)` trước rồi đổi cơ số mà quên tràn:

```java
System.out.println(Math.abs(Integer.MIN_VALUE));
// -2147483648: vẫn âm vì overflow.
```

Nếu cần tự triển khai thuật toán chuyển chữ số, phải xử lý MIN_VALUE bằng kỹ thuật an toàn như làm việc trên giá trị âm hoặc mở rộng kiểu trước. Với nhu cầu ứng dụng bình thường, dùng phương thức JDK có sẵn đơn giản hơn.

## 5. So sánh định dạng signed với biểu diễn mẫu bit

`Integer.toString(value, radix)` và `Long.toString(value, radix)` chuyển **giá trị có dấu** thành chữ số theo cơ số đã chọn. Với số âm, chúng đặt dấu trừ trước phần độ lớn: `Integer.toString(-42,16)` là `"-2a"`. Trong khi đó, `Integer.toHexString(-42)` là `"ffffffd6"`: nó diễn giải **mẫu 32 bit không dấu** của cùng biến.

```java
System.out.println(Integer.toString(-1,16)); // -1
System.out.println(Integer.toHexString(-1)); // ffffffff
System.out.println(Long.toString(-1L,16));   // -1
```

Không dùng hai kiểu chuỗi này thay nhau khi cần round-trip. Chọn `toString(value, radix)` cho giá trị signed; chọn nhóm `toBinaryString`/`toHexString` và `toUnsignedString` khi thực sự cần nhìn bit pattern. Quy tắc sign extension, hiển thị full-width 32/64 bit, `parseUnsignedInt`/`parseUnsignedLong` và giới hạn `byte`/`short` là trọng tâm bài kế tiếp.

## 6. Biểu diễn unsigned là một hợp đồng riêng

Đối với `int -1`, `Integer.toUnsignedString(-1)` trả `"4294967295"`; với cơ số 16, `Integer.toUnsignedString(-1,16)` trả `"ffffffff"`. Mẫu bit vẫn giữ nguyên, chỉ cách đọc thay đổi. `Integer.parseUnsignedInt("ffffffff",16)` trả lại cùng bit pattern, mà nếu in như signed `int` sẽ thấy `-1`.

```java
String text = Integer.toUnsignedString(-1, 16);
int decodedBits = Integer.parseUnsignedInt(text, 16);
System.out.println(decodedBits == -1); // true
```

Đừng đưa chuỗi unsigned có giá trị lớn hơn `Integer.MAX_VALUE` vào `Integer.parseInt` theo signed. Tại ranh giới API, cần quy định rõ signedness, radix và chiều rộng bit. Bài `toBinaryString, toHexString và toUnsignedString` đi sâu về các quy tắc này.

## 7. Định dạng không tự có `0x`, `0b`, `#` hay hậu tố

`Integer.toString(42,16)` trả `"2a"` chứ không trả `"0x2a"`. `Long.toString(42L,2)` trả `"101010"` chứ không có `"0b"`. Formatter cũng **không tự thêm** underscore phân nhóm, chữ `L`, chữ hoa, ký hiệu `#` hoặc độ rộng cố định.

```java
String digits = Integer.toString(42, 16); // "2a"
String shown = "0x" + digits;             // "0x2a"
```

Nếu chuỗi đầu ra phục vụ **giao thức máy-máy**, tránh thêm tiền tố trang trí khi giao thức chỉ yêu cầu digits. Nếu phục vụ UI hoặc log, tiền tố có thể hữu ích để người đọc biết radix.

### Đặt dấu âm và tiền tố đúng vị trí

Cách ngây thơ:

```java
String wrong = "0x" + Integer.toString(-42,16);
// "0x-2a" — không phải cú pháp chuẩn mà Integer.decode chấp nhận.
```

Nếu bạn thiết kế một định dạng signed hex tương thích với `Integer.decode`, đặt dấu **trước** tiền tố:

```java
static String signedHexWithPrefix(int value) {
    String digits = Integer.toString(value, 16);
    if (digits.startsWith("-")) {
        return "-0x" + digits.substring(1);
    }
    return "0x" + digits;
}
```

```java
System.out.println(signedHexWithPrefix(-42)); // -0x2a
System.out.println(Integer.decode("-0x2a"));  // -42
```

Đây là phương thức minh họa đặt trong class. Cách dùng `substring(1)` trên dấu có sẵn tránh phải tính `-value`, vì `-Integer.MIN_VALUE` có thể tràn. Tuy nhiên nó áp dụng cho **giá trị signed**, không phải quy ước bitmask unsigned. Với bitmask, `"0x" + Integer.toHexString(value)` thường diễn đạt tốt hơn.

## 8. Viết chữ hoa, thêm số 0 đầu và độ rộng cố định

Các kết quả `toString(value,radix)` có dạng tối giản: không thêm số 0 đầu, và dùng chữ thường. Nếu một định dạng yêu cầu **ít nhất 8 chữ số hex**, bạn phải bổ sung quy tắc riêng.

```java
int value = 42;
String padded = String.format(java.util.Locale.ROOT, "%08x", value);
System.out.println(padded); // 0000002a
```

`String.format` dùng các quy tắc của `Formatter`, ở đây:

- `%x`: định dạng hexadecimal chữ thường.
- `%X`: định dạng hexadecimal chữ hoa.
- `8`: độ rộng tối thiểu 8 ký tự.
- `0`: điền chữ số 0 ở bên trái cho đủ độ rộng.
- `Locale.ROOT`: lựa chọn ổn định cho việc định dạng không phụ thuộc ngôn ngữ vùng.

```java
System.out.println(String.format(java.util.Locale.ROOT,"%08X", 42));
// 0000002A
```

**Bẫy:** `%08x` không có nghĩa “cắt xuống 8 ký tự”. Độ rộng là **tối thiểu**, không phải giới hạn tối đa. Nếu giá trị cần nhiều chữ số hơn, formatter không tự bỏ những chữ số quan trọng.

Ngoài ra, với **số nguyên âm** và `%x`, quy ước Formatter có thể dùng biểu diễn unsigned bit pattern. Không nhầm nó với `Integer.toString(-42,16)` dạng `"-2a"`.

### Nếu muốn chính xác 8 chữ số hex cho một `int`?

`Integer.toHexString(value)` sinh tối đa 8 chữ số hex cho mẫu 32 bit, nhưng thường không padding các số nhỏ. Có thể kết hợp `String.format("%08x", value)` khi muốn hiển thị toàn bộ word 32 bit. Với `long`, thường dùng `%016x` để hiển thị 16 chữ số hex của word 64 bit.

### Không làm mất số 0 đầu của dữ liệu định danh

Một chuỗi như `"00042"` có thể là mã hồ sơ, không đơn thuần là biểu diễn số học của 42. Chuyển nó bằng:

```java
int n = Integer.parseInt("00042");
String restored = Integer.toString(n); // "42", mất ba số 0 đầu.
```

Không có cách nào để `Integer.toString` suy ra độ rộng ban đầu của chuỗi vì biến số `int` đã **không lưu** số 0 đầu. Nếu cần giữ đúng định danh, giữ `String` và validate theo schema. Nếu độ rộng cố định là thuộc tính nghiệp vụ, định dạng lại với chiều rộng đã biết.

## 9. Parse và format có thể là hai chiều thuận nghịch, với điều kiện

Với một radix hợp lệ `2..36` và một giá trị `int`, cặp sau khôi phục giá trị gốc:

```java
int original = -42;
int radix = 16;
String text = Integer.toString(original, radix);
int restored = Integer.parseInt(text, radix);

System.out.println(text);                // -2a
System.out.println(restored == original); // true
```

Tương tự cho `long`:

```java
long original = 4_294_967_296L;
String text = Long.toString(original, 16); // "100000000"
long restored = Long.parseLong(text, 16);
```

Các cặp là `toString`/`parseInt` và `Long.toString`/`Long.parseLong`, **không phải** tự động thêm dấu `0x` hay ký tự phân nhóm. Nếu muốn format bit pattern unsigned, phải dùng cặp unsigned thích hợp.

### Những điều phá vỡ round trip

| Nguyên nhân | Ví dụ | Kết quả |
| --- | --- | --- |
| Parse sai radix | Format `42` radix 16 → `"2a"`, parse radix 10 | `NumberFormatException` |
| Tự thêm tiền tố rồi parseInt | `"0x2a"` với radix 16 | Parser không tự bỏ `0x` |
| Dùng bitstring unsigned và parser signed | `"ffffffff"` → `parseInt(...,16)` | Vượt miền `int` signed |
| Sử dụng cast thu hẹp trước format | `(int) 4_294_967_296L` | Mất giá trị trước khi `toString` chạy |
| Quên ký hiệu dấu | Đổi `"-2a"` thành `"2a"` | Giá trị âm bị đổi thành dương |
| Dùng radix sai ngoài phạm vi mà không validate | `toString(255,1)` | Silent fallback sang `"255"` hệ 10 |
| Cho rằng định dạng giữ khoảng trắng/zero đầu | `"00042"` → parse → `toString` | Chỉ còn `"42"` |

Một giao thức số nguyên nên **quy định radix, signedness, tiền tố, chữ hoa/chữ thường, độ rộng, quy tắc số 0 đầu và phạm vi giá trị**. Một phương thức formatter đơn lẻ không thay thế được tài liệu định dạng.

## 10. Lưu ý về Unicode digits và chữ hoa/chữ thường

`Integer.toString(value, radix)` và `Long.toString(value, radix)` dùng bảng chữ số ASCII dạng `0..9a..z`, phù hợp cho giao thức không phụ thuộc locale.

Trong khi đó `Integer.parseInt(text, radix)` và `Long.parseLong(text, radix)` sử dụng quy tắc chữ số dựa trên `Character.digit` nên có thể nhận một số ký tự chữ số Unicode được JDK hỗ trợ, cũng như chữ hoa `A..Z` với radix phù hợp. **Ngôn ngữ formatter chuẩn và tập input parser chấp nhận không nhất thiết giống hệt nhau.**

```java
System.out.println(Integer.toString(255,16)); // ff
System.out.println(Integer.parseInt("FF",16)); // 255
System.out.println(Integer.parseInt("ff",16)); // 255
```

Nếu giao thức bắt buộc **chỉ ASCII, chỉ lowercase**, đừng nghĩ `parseInt` tự làm validator cho cả schema. Hãy kiểm tra tập ký tự và chuẩn hóa theo chính sách của giao thức.

Việc dùng `toString` thông thường **không phụ thuộc `Locale`** để chọn ký tự chữ số. Nếu bạn cần hiển thị số theo quy tắc văn hóa như phân nhóm hàng nghìn hoặc dấu số thập phân địa phương, hãy dùng `NumberFormat`/`Formatter` đúng mục đích. `Integer.toString` có lợi khi cần chuỗi máy-máy đơn giản, nhất quán.

## 11. Trường hợp `Long.MIN_VALUE` và miền giá trị dài hơn `int`

`long` là số nguyên signed 64 bit, có miền `-9_223_372_036_854_775_808` tới `9_223_372_036_854_775_807`. Khi giá trị vượt `int`, chọn `Long.toString` để giữ nguyên giá trị.

```java
long large = 4_294_967_296L; // 2^32
System.out.println(Long.toString(large));    // 4294967296
System.out.println(Long.toString(large,16)); // 100000000
```

`Integer.toString` không chấp nhận `long` trực tiếp nếu chưa chuyển kiểu:

```java
// Integer.toString(large); // Lỗi biên dịch: long không tự thu hẹp thành int.
String wrong = Integer.toString((int) large); // "0": đã mất bit cao.
```

Với `Long.MIN_VALUE`, `Long.toString` bảo đảm trả chuỗi signed đúng `"-9223372036854775808"`. Cũng như `int`, không tự áp dụng `Math.abs(Long.MIN_VALUE)` rồi mong ra số dương cùng kiểu, vì `Math.abs(Long.MIN_VALUE)` vẫn âm do overflow.

Với số nguyên còn lớn hơn `long`, chọn `java.math.BigInteger`. `BigInteger.toString(int radix)` cũng hỗ trợ biểu diễn theo cơ số 2..36, nhưng có hợp đồng riêng; đừng ép về `longValue()` chỉ để dùng `Long.toString` vì khi đó có thể mất thông tin.

## 12. Chương trình độc lập Java 17+

Tạo tệp `RadixFormatDemo.java`:

```java
import java.util.Locale;

public class RadixFormatDemo {
    public static void main(String[] args) {
        int n = -42;
        long large = 4_294_967_296L;

        System.out.println("Integer default: " + Integer.toString(n));
        System.out.println("Long default: " + Long.toString(large));
        System.out.println("42 base 2: " + Integer.toString(42, 2));
        System.out.println("42 base 8: " + Integer.toString(42, 8));
        System.out.println("42 base 16: " + Integer.toString(42, 16));
        System.out.println("-42 base 16: " + Integer.toString(-42, 16));
        System.out.println("35 base 36: " + Integer.toString(35, 36));
        System.out.println("255 base 16: " + Integer.toString(255, 16));
        System.out.println("255 invalid radix 1: "
                + Integer.toString(255, 1));
        System.out.println("long 4294967296 base 16: "
                + Long.toString(large, 16));

        System.out.println("int -1 toHexString: "
                + Integer.toHexString(-1));
        System.out.println("int -1 toString base 16: "
                + Integer.toString(-1, 16));
        System.out.println("unsigned -1 base 10: "
                + Integer.toUnsignedString(-1));
        System.out.println("unsigned -1 base 16: "
                + Integer.toUnsignedString(-1, 16));
        System.out.println("unsigned long -1 base 16: "
                + Long.toUnsignedString(-1L, 16));

        System.out.println("zero base 36: " + Long.toString(0L, 36));
        System.out.println("Integer.MIN_VALUE base 10: "
                + Integer.toString(Integer.MIN_VALUE));
        System.out.println("Long.MIN_VALUE base 10: "
                + Long.toString(Long.MIN_VALUE));

        System.out.println("Signed parse radix 16: "
                + Integer.parseInt(Integer.toString(-42, 16), 16));
        System.out.println("Unsigned parse hex: "
                + Integer.parseUnsignedInt(
                        Integer.toUnsignedString(-1, 16), 16));
        System.out.println("Padded hex: "
                + String.format(Locale.ROOT, "%08x", 42));
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac --release 17 RadixFormatDemo.java
java RadixFormatDemo
```

Stdout đã được kiểm chứng:

```text
Integer default: -42
Long default: 4294967296
42 base 2: 101010
42 base 8: 52
42 base 16: 2a
-42 base 16: -2a
35 base 36: z
255 base 16: ff
255 invalid radix 1: 255
long 4294967296 base 16: 100000000
int -1 toHexString: ffffffff
int -1 toString base 16: -1
unsigned -1 base 10: 4294967295
unsigned -1 base 16: ffffffff
unsigned long -1 base 16: ffffffffffffffff
zero base 36: 0
Integer.MIN_VALUE base 10: -2147483648
Long.MIN_VALUE base 10: -9223372036854775808
Signed parse radix 16: -42
Unsigned parse hex: -1
Padded hex: 0000002a
```

Ví dụ thể hiện định dạng `int`/`long` ở các radix thông dụng, sự chuyển về radix 10 khi tham số sai, số âm signed so với mẫu bit hex không dấu, giá trị biên, round trip signed/unsigned và độ rộng hex cố định. Các chuỗi stdout phản ánh giá trị thực tế của JDK chứ không suy đoán từ ký hiệu `0x` trong source.

## 13. Một số tình huống áp dụng

### A. Hiển thị flags và bitmask

Khi debug trạng thái cờ, bạn thường quan tâm **bit pattern** hơn giá trị signed. Ví dụ:

```java
int flags = 0xA5000001;
String bitsHex = Integer.toHexString(flags); // a5000001
String allBitsHex = String.format(Locale.ROOT, "%08x", flags);
```

Nếu dùng `Integer.toString(flags,16)`, vì bit dấu bằng 1, chuỗi sẽ bắt đầu bằng dấu `-` cùng chữ số thể hiện độ lớn signed, không phải word hex 8 chữ số của mẫu bit. Hãy xác định rõ log cần **signed value** hay **raw bit pattern**.

### B. Xây mã định danh ngắn theo radix 36

Đối với **số nguyên không âm** đã có sẵn:

```java
int id = 35;
String compact = Integer.toString(id, 36); // "z"
```

Cơ số 36 có thể tạo chữ ngắn hơn thập phân với số lớn, nhưng đó chỉ là **cách biểu diễn**. Nó không tạo tính bảo mật, không tăng entropy và không bảo đảm mã duy nhất ngoài giá trị nguồn. Nếu phải giữ chữ hoa, độ rộng hoặc check digit, đó là quy tắc bổ sung của giao thức.

### C. Lưu giá trị số vào file hoặc JSON

Khi giao thức quy định số nguyên thập phân, `Integer.toString(value)` và `Long.toString(value)` sinh chuỗi ổn định không có dấu phân nhóm hàng nghìn. Nhưng trong JSON, kiểu **number** và **string** khác nhau: ghi `"42"` là dữ liệu chuỗi, còn ghi `42` là token số. Đừng quyết định sơ đồ dữ liệu chỉ dựa trên kết quả formatter.

Với số `long` vượt độ chính xác nguyên liên tiếp của JavaScript `Number` (2^53), một số hệ thống lựa chọn **truyền string decimal** để tránh mất chính xác ở phía nhận; đây là quyết định hợp đồng giữa các hệ, không phải thiếu sót của `Long.toString`.

### D. Đọc/ghi hex trên hai hệ thống

Nếu bên gửi dùng `Integer.toHexString` cho bitmask và bên nhận dùng `Integer.parseInt`, lỗi có thể xuất hiện khi bit cao nhất bằng 1. Với một mẫu 32-bit không dấu, dùng `Integer.parseUnsignedInt(text,16)` phía nhận; với long 64-bit, dùng `Long.parseUnsignedLong` khi đúng schema. Thêm tiền tố hoặc padding nếu giao thức yêu cầu, nhưng bên nhận phải hiểu đúng tiền tố và độ rộng.

## 14. Lỗi thường gặp

| Sai lầm | Vì sao sai | Hướng khắc phục |
| --- | --- | --- |
| Cho rằng `radix` thay đổi giá trị `int` | Nó chỉ thay cách biểu diễn thành chuỗi | Phân biệt numeric value và formatting |
| Tưởng `toString(value,16)` tự trả `"0x..."` | Nó chỉ sinh chữ số cùng dấu nếu âm | Thêm prefix có chủ đích hoặc dùng formatter |
| Mong kết quả hexadecimal viết hoa | `toString` dùng `a..z` | `toUpperCase(Locale.ROOT)` hoặc `%X` khi phù hợp |
| Dùng radix 1/37 và chờ exception | `toString` fallback radix 10 | Validate radix nếu input có thể sai |
| Nhầm `Integer.toString(-1,16)` và `Integer.toHexString(-1)` | `"-1"` khác `"ffffffff"` | Chọn signed vs bit-pattern format |
| Parse `"ffffffff"` bằng `parseInt(...,16)` | Vượt `Integer.MAX_VALUE` signed | `parseUnsignedInt(...,16)` |
| Parse `"2a"` bằng radix 10 | Chữ `a` không hợp lệ | Chuyển đúng radix 16 |
| Đọc `"0x2a"` bằng `parseInt(...,16)` | Parser không tự hiểu prefix | `decode` hoặc strip prefix sau validation |
| Dùng `Integer.toString((int) longValue)` | Cast có thể mất dữ liệu trước format | `Long.toString(longValue,radix)` |
| Tự dùng `Math.abs(MIN_VALUE)` để format âm | `abs` có thể overflow | Dùng API JDK đúng |
| Cho rằng `toString` tự padding để đủ độ rộng | Kết quả tối giản, không padding | `Formatter`/`String.format` |
| Dùng `toString` cho mã giữ số 0 đầu | Không thể phục hồi độ rộng gốc sau parse | Giữ `String` hoặc schema độ rộng |
| Cho rằng toString tạo chuỗi “bảo mật” | Radix 36 chỉ là biểu diễn | Thiết kế mã có bảo mật riêng |
| Tưởng mọi `String` do `toString` tạo ra đều có thể parse radix bất kỳ | Cần đúng radix và signedness | Lưu metadata cơ số trong giao thức |
| Nhầm `Integer.valueOf` với `Integer.toString` | Một hàm trả wrapper, một hàm trả `String` | Xem chữ ký và kiểu trả về |
| Dùng `Integer.parseInt` khi giá trị vượt `int` | Out of range sẽ báo lỗi | Chọn `Long.parseLong` hoặc `BigInteger` |

## 15. Tự kiểm tra

1. `Integer.toString(42,16)` trả chuỗi gì? Có tự thêm `0x` không?
2. `Integer.toString(-42,16)` và `Integer.toHexString(-42)` giống hay khác nhau? Giải thích theo signed value và bit pattern.
3. Vì sao `Integer.toString(255,1)` không ném exception mà trả `"255"`? Nếu một API cần báo lỗi radix sai, bạn nên làm gì?
4. `Long.toString(4_294_967_296L,16)` trả gì? Vì sao không thể dùng `Integer.toString((int) 4_294_967_296L,16)` để giữ cùng giá trị?
5. Hai lời gọi `Integer.toUnsignedString(-1)` và `Integer.toString(-1)` tạo kết quả nào? Mẫu bit ban đầu có thay đổi không?
6. Nếu nhận được `"ffffffff"` như word hex 32-bit, bạn nên dùng `parseInt` hay `parseUnsignedInt`? Vì sao?
7. Định dạng radix 36 của 35 là gì? Nó có tạo mã duy nhất, bí mật hoặc có độ dài cố định không?
8. Khi nào nên dùng `String.format(Locale.ROOT,"%08x", value)` thay vì `Integer.toString(value,16)`?
9. Vì sao `"00042"` không thể được khôi phục nguyên dạng bằng `Integer.parseInt` rồi `Integer.toString`? Tình huống nào cần giữ `String`?
10. Viết phép kiểm tra round trip signed từ `int` sang cơ số 2, 8, 10, 16 và trở lại `int`.
11. Nếu formatter dùng radix 16 nhưng parser mặc định radix 10, chuyện gì xảy ra với `"2a"`?
12. Nếu ứng dụng nhận `radix` từ input người dùng, vì sao nên validate trong `2..36` thay vì dựa vào fallback của `toString`?
13. Vì sao `Integer.toString(value,16)` trả chữ thường? Làm thế nào tạo uppercase mà không phụ thuộc locale?
14. Khi lưu một bitmask có thể âm trong signed `int`, format và parse thế nào để giữ nguyên 32 bit?

## 16. Tài liệu chính thức

- [Java SE 17 — `Integer.toString(int, int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#toString(int,int)): radix 2..36, chữ số `0..9a..z`, dấu âm và fallback radix 10.
- [Java SE 17 — `Long.toString(long, int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html#toString(long,int)): cùng nguyên tắc định dạng signed trên 64 bit.
- [Java SE 17 — `Integer.toUnsignedString`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#toUnsignedString(int,int)): diễn giải unsigned của 32 bit.
- [Java SE 17 — `Integer.toHexString`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#toHexString(int)): chuỗi hex không dấu của mẫu `int`.
- [Java SE 17 — `Integer.parseInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#parseInt(java.lang.String,int)): phân tích chuỗi có dấu theo radix.
- [Java SE 17 — `Formatter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html): các quy tắc `%x`/`%X`, padding, width và định dạng văn bản.

**Kết luận:** `Integer.toString` và `Long.toString` là API chuyển **giá trị số nguyên** thành **chuỗi chữ số theo radix**; chúng không làm đổi giá trị, không tự thêm prefix, không padding và trả chữ thường ở cơ số trên 10. Với số âm, `toString(value,radix)` dùng **dấu trừ**, còn `toHexString`/`toBinaryString`/`toUnsignedString` phù hợp khi cần **biểu diễn mẫu bit theo nghĩa không dấu**. Hãy quy định rõ signedness, radix và quy tắc giao thức khi định dạng hoặc parse ngược, đồng thời validate radix để tránh fallback thập phân không mong muốn.