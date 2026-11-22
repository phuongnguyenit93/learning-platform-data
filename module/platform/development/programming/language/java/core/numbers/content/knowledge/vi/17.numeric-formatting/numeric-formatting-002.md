# `toBinaryString`, `toHexString` và `toUnsignedString` trong Java

Khi cần hiển thị hoặc kiểm tra **biểu diễn của số nguyên**, Java cung cấp các phương thức tĩnh trong `Integer` và `Long`. Ba tên quan trọng nhất là **`toBinaryString`**, **`toHexString`** và **`toUnsignedString`**:

- `Integer.toBinaryString(int)`: tạo chuỗi **nhị phân** (cơ số 2) từ **mẫu bit 32 bit** của một `int`.
- `Integer.toHexString(int)`: tạo chuỗi **thập lục phân** (cơ số 16), chữ `a`–`f` viết thường, từ cùng mẫu bit.
- `Integer.toUnsignedString(int)`: tạo chuỗi **thập phân không dấu** (cơ số 10 mặc định), coi cùng 32 bit là số trong khoảng `0` đến `4_294_967_295`.

Ví dụ cùng một giá trị `int`:

```java
int value = -1;

System.out.println(Integer.toBinaryString(value));
// 11111111111111111111111111111111

System.out.println(Integer.toHexString(value));
// ffffffff

System.out.println(Integer.toUnsignedString(value));
// 4294967295
```

`value` vẫn là **`int -1`**, không tự biến thành kiểu số nguyên không dấu. Những phương thức này **đổi cách trình bày bit thành chuỗi**; chúng không sửa giá trị biến, không thay đổi bit trong bộ nhớ và không tạo kiểu primitive `uint`.

## 1. Hiểu đúng signed và unsigned trước khi định dạng

Java có các kiểu số nguyên primitive `byte` (8 bit), `short` (16 bit), `int` (32 bit) và `long` (64 bit), đều có dấu theo cách hiểu số nguyên thông thường. Riêng `char` là giá trị nguyên không dấu 16 bit phục vụ đơn vị mã UTF-16.

Với `int`, cùng **32 bit** có thể được diễn giải:

- **Có dấu (signed)** theo bù hai (*two's complement*): `-2_147_483_648` tới `2_147_483_647`.
- **Không dấu (unsigned)**: `0` tới `4_294_967_295`.

Ví dụ mẫu bit toàn `1`:

```text
Bit 32 bit:       11111111111111111111111111111111
Hex:              ffffffff
Signed int:       -1
Unsigned 32-bit:  4294967295
```

Đây **không phải ba giá trị được lưu riêng**. Chúng là **ba cách trình bày cùng mẫu bit**. Biểu thức `int x = -1;` tiếp tục hoạt động theo số học có dấu nếu viết `x + 1`, `x < 0` hoặc `x / 2`. Nếu nghiệp vụ muốn **so sánh/chia theo unsigned**, Java có các API như `Integer.compareUnsigned`, `divideUnsigned` và `remainderUnsigned`; chỉ việc gọi `toUnsignedString` không đổi nghĩa các phép toán về sau.

### Bảng nhanh với `Integer`

| Giá trị `int` | `toBinaryString` | `toHexString` | `toUnsignedString` |
| --- | --- | --- | --- |
| `0` | `0` | `0` | `0` |
| `10` | `1010` | `a` | `10` |
| `42` | `101010` | `2a` | `42` |
| `255` | `11111111` | `ff` | `255` |
| `-1` | 32 ký tự `1` | `ffffffff` | `4294967295` |
| `Integer.MIN_VALUE` | `1` và 31 ký tự `0` | `80000000` | `2147483648` |

Đối với số `int` không âm, chuỗi nhị phân và hex thường **bỏ các số 0 dẫn đầu**. Với số âm, bit dấu là 1 và biểu diễn bù hai 32 bit được thể hiện đầy đủ theo chiều rộng kiểu `int`. Đây là lý do `Integer.toBinaryString(-1)` dài 32 ký tự, còn `Integer.toBinaryString(1)` chỉ là `"1"`.

## 2. `Integer.toBinaryString(int)`: đọc mẫu bit ở cơ số 2

Cú pháp:

```java
String bits = Integer.toBinaryString(42); // "101010"
```

Các chữ số trong chuỗi chỉ gồm `0` và `1`; **không có tiền tố `0b`** và không có dấu âm tách rời. Phương thức mô tả mẫu bit của `int` như giá trị 32 bit không dấu rồi ghi bằng cơ số 2.

```java
System.out.println(Integer.toBinaryString(10)); // 1010
System.out.println(Integer.toBinaryString(-1));
// 11111111111111111111111111111111
```

Vì `int` có 32 bit, một giá trị âm như `-1` tương đương mẫu bù hai toàn bit 1. **Không đọc** chuỗi `111...111` thành số có dấu âm bằng cách nhìn chữ số đầu tiên rồi thêm dấu `-`; đây là chuỗi số nhị phân không dấu đại diện cho 32 bit gốc.

Đặc biệt:

```java
String minBits = Integer.toBinaryString(Integer.MIN_VALUE);
// "10000000000000000000000000000000"
```

Bit cao nhất bằng 1 còn các bit khác bằng 0. Với ngữ nghĩa signed, mẫu này là `-2^31`; với ngữ nghĩa unsigned, là `2^31`.

### Muốn chuỗi luôn đủ 32 bit?

`toBinaryString` không thêm zero dẫn đầu cho số dương. Nếu cần bản 32 bit cố định:

```java
int x = 42;
String bits = Integer.toBinaryString(x);
String padded = "0".repeat(32 - bits.length()) + bits;
// "00000000000000000000000000101010"
```

Cách viết này phù hợp Java 17+ và với một `int` bất kỳ có chuỗi nhị phân tối đa 32 ký tự. Khi giao thức nhị phân cần **số byte** chứ không phải ký tự `0`/`1`, hãy ghi byte thực qua `ByteBuffer` hoặc API I/O tương ứng; chuỗi nhị phân là cách **hiển thị phục vụ đọc/debug**, không phải định dạng dữ liệu nhị phân có hiệu suất tốt.

## 3. `Integer.toHexString(int)`: hiển thị hex dễ đọc

Hex (cơ số 16) nhóm **mỗi 4 bit thành một chữ số** từ `0` tới `9` và `a` tới `f`:

```java
int x = 42;

System.out.println(Integer.toHexString(x));   // 2a
System.out.println(Integer.toHexString(255)); // ff
System.out.println(Integer.toHexString(-1));  // ffffffff
```

Một `int` có tối đa 8 ký tự hex, vì `32 / 4 = 8`. Hex gọn hơn binary nên thường phù hợp khi quan sát bit masks, mã màu và địa chỉ/word dữ liệu.

**Lưu ý cú pháp:** Chuỗi trả về **không chứa `0x`**, không chứa dấu phân cách và dùng `a`–`f` viết thường. `"2a"` là chuỗi được hàm trả về; nếu muốn nhãn `0x` trong giao diện, ghép rõ ràng:

```java
String shown = "0x" + Integer.toHexString(42); // "0x2a"
```

Không nhầm **chuỗi trả về từ API** với literal Java:

```java
int sourceLiteral = 0x2A;       // literal int 42 trong mã Java
String displayed = Integer.toHexString(sourceLiteral); // "2a"
```

Với bit pattern 32 bit âm, ví dụ `-1`, `Integer.toHexString(-1)` cho `"ffffffff"` vì nó biểu diễn bit dưới dạng không dấu, **không cho `"-1"`**. Nếu cần viết số có dấu trong cơ số 16, xem `Integer.toString(value, 16)` ở mục 5.

### Hiển thị đủ 8 chữ số hex

`Integer.toHexString(42)` trả `"2a"`, không tự pad thành `"0000002a"`. Nếu định dạng báo cáo yêu cầu đúng 8 chữ số, có thể viết:

```java
int x = 42;
String padded = String.format("%08x", x); // "0000002a"
```

`String.format` hỗ trợ độ rộng và zero-padding. Với dữ liệu dùng trong giao thức hoặc hash, **độ rộng và dạng chữ hoa/chữ thường phải được quy định nhất quán**. Trong UI, có thể dùng `%08X` để in hex chữ hoa nếu đúng yêu cầu.

## 4. `Integer.toUnsignedString(int)`: đọc 32 bit như số không dấu

`Integer.toUnsignedString(value)` mặc định biểu diễn `int` như giá trị **unsigned 32 bit trong cơ số 10**:

```java
int x = -1;
String signed = Integer.toString(x);         // "-1"
String unsigned = Integer.toUnsignedString(x); // "4294967295"
```

Cùng 32 bit có cách đọc khác nhau theo mục tiêu. Quy tắc toán học cho `int x`:

- Nếu `x >= 0`, giá trị unsigned bằng `x`.
- Nếu `x < 0`, giá trị unsigned tương ứng là `x + 2^32` về mặt toán học (phải tính bằng kiểu đủ rộng).

Có thể quan sát tương đương qua widening rồi mask:

```java
int x = -1;
long u = Integer.toUnsignedLong(x); // 4294967295L
long alsoU = ((long) x) & 0xFFFF_FFFFL; // 4294967295L
```

`Integer.toUnsignedLong` mở rộng theo cách hiểu không dấu. **Không dùng `(long) x` đơn thuần** nếu muốn giải mã unsigned vì cast `int → long` có dấu sẽ giữ `-1L` cho `x = -1`.

Không có primitive `uint` trong Java. Do đó `toUnsignedString` chỉ trả `String` để hiển thị/trao đổi, còn dữ liệu gốc vẫn là `int`. Khi cần làm phép toán số học unsigned, phải dùng đúng API, không chỉ thay cách in.

## 5. Khác biệt với `toString(value, radix)` và overload radix

Đây là chỗ rất dễ nhầm. So sánh:

```java
int x = -1;

String signedHex = Integer.toString(x, 16);           // "-1"
String unsignedHex = Integer.toUnsignedString(x, 16); // "ffffffff"
String hexBits = Integer.toHexString(x);              // "ffffffff"
```

- `Integer.toString(int, radix)` xem giá trị như **số có dấu**, nên khi âm thêm dấu `-` và định dạng độ lớn.
- `Integer.toUnsignedString(int, radix)` xem **cùng 32 bit là unsigned**, rồi chuyển sang cơ số được chọn.
- `Integer.toBinaryString(int)` tương đương trình bày unsigned cơ số 2 của mẫu `int`.
- `Integer.toHexString(int)` tương đương trình bày unsigned cơ số 16 của mẫu `int`.
- `Integer.toOctalString(int)` cũng có hành vi tương tự cho cơ số 8, dù không phải API trọng tâm của bài.

```java
System.out.println(Integer.toUnsignedString(10, 8));  // "12"
System.out.println(Integer.toUnsignedString(31, 36)); // "v"
```

Overload `Integer.toUnsignedString(int, int)` nhận radix. Nên chủ động dùng radix hợp lệ từ `Character.MIN_RADIX` (**2**) đến `Character.MAX_RADIX` (**36**). Java dùng chữ cái Latin thường cho các chữ số từ 10 đến 35. Nếu muốn hex, dùng radix 16; nếu muốn binary, dùng radix 2. Trong mã tự xử lý chuỗi nguồn, kiểm tra radix thay vì mặc nhiên mong API sẽ cảnh báo mọi radix không hợp lệ theo cách bạn nghĩ.

Bảng đối chiếu các API:

| Lời gọi với `x = -1` | Kết quả | Cách hiểu |
| --- | --- | --- |
| `Integer.toString(x)` | `"-1"` | Signed, thập phân |
| `Integer.toString(x, 16)` | `"-1"` | Signed, hex có dấu trừ |
| `Integer.toUnsignedString(x)` | `"4294967295"` | Unsigned, thập phân |
| `Integer.toUnsignedString(x, 2)` | 32 chữ `1` | Unsigned, binary |
| `Integer.toBinaryString(x)` | 32 chữ `1` | Bit pattern, binary |
| `Integer.toUnsignedString(x, 16)` | `"ffffffff"` | Unsigned, hex |
| `Integer.toHexString(x)` | `"ffffffff"` | Bit pattern, hex |

**Ý nghĩa chính:** Khi giá trị nằm trong phần âm của `int`, chữ số hiển thị phụ thuộc việc chọn ngữ nghĩa **signed** hay **unsigned**.

## 6. Phiên bản `Long` và độ rộng 64 bit

`Long` cũng cung cấp:

- `Long.toBinaryString(long)`;
- `Long.toHexString(long)`;
- `Long.toUnsignedString(long)`;
- `Long.toUnsignedString(long, int radix)`.

Cùng nguyên tắc như `Integer`, nhưng làm việc với **64 bit**. Số không dấu lớn nhất theo 64 bit là **`2^64 - 1 = 18_446_744_073_709_551_615`**, vượt `Long.MAX_VALUE`.

```java
long value = -1L;

System.out.println(Long.toHexString(value));
// ffffffffffffffff (16 ký tự f)

System.out.println(Long.toUnsignedString(value));
// 18446744073709551615
```

`Long.toBinaryString(-1L)` trả 64 chữ `1`. Với `Long.MIN_VALUE`, mẫu hex là `8000000000000000`; diễn giải signed là `-2^63`, còn unsigned là `2^63`.

**Không ép số nguyên không dấu 64 bit lớn vào một kiểu `long` khác để lấy giá trị dương**, vì primitive `long` không có miền dương đủ lớn. Nếu cần làm việc với giá trị toán học trong miền unsigned 64 bit dưới dạng số không âm, có thể dùng `BigInteger` hoặc các phép unsigned chuyên dụng `Long.compareUnsigned`, `divideUnsigned`, `remainderUnsigned`; chọn cách phù hợp bài toán.

## 7. Bẫy `byte`/`short`: sign extension trước khi format

Ba phương thức `Integer.toBinaryString`, `Integer.toHexString` và `Integer.toUnsignedString` nhận `int`, **không có overload trực tiếp cho `byte` hay `short`**. Khi truyền `byte`/`short`, Java mở rộng chúng lên `int` trước khi gọi phương thức.

Với giá trị âm, widening primitive bảo toàn **giá trị có dấu**, có thể được nhìn thấy như **sign extension** (nhân bit dấu lên phần cao):

```java
byte b = -1;

String unexpected = Integer.toBinaryString(b);
// 11111111111111111111111111111111 (32 bit, không phải 8)

String eightBits = Integer.toBinaryString(b & 0xFF);
// 11111111

int unsignedByte = Byte.toUnsignedInt(b); // 255
```

Nếu muốn biểu diễn đúng **8 bit** của `byte`, mask bằng `0xFF` trước khi format. Với `short`, dùng `0xFFFF` để giữ 16 bit:

```java
short s = -1;

String sHex = Integer.toHexString(s & 0xFFFF); // "ffff"
String sBits = Integer.toBinaryString(s & 0xFFFF);
// "1111111111111111"
```

Nếu muốn một giá trị unsigned dễ tính toán, `Byte.toUnsignedInt` và `Short.toUnsignedInt` diễn đạt rõ ý định. Cũng có thể dùng `Byte.toUnsignedInt(b)` rồi `Integer.toUnsignedString(...)`. Mask là cách phổ biến khi làm bit field, network protocol hoặc giải mã byte có dấu thành giá trị trong `0..255`.

### Chú ý chiều rộng đầu ra

`Integer.toBinaryString(b & 0xFF)` vẫn loại **zero dẫn đầu** cho giá trị như `5` (sẽ thành `"101"`). Nếu bắt buộc đúng 8 bit, kết hợp mask với padding:

```java
byte b = 5;
String raw = Integer.toBinaryString(b & 0xFF); // "101"
String padded = "0".repeat(8 - raw.length()) + raw; // "00000101"
```

Tương tự, muốn đúng 4 ký tự hex cho `short`, có thể dùng `String.format("%04x", s & 0xFFFF)`. Việc **mask** xử lý chiều rộng bit, còn việc **padding** xử lý độ dài chuỗi hiển thị; hai bước này có nhiệm vụ khác nhau.

## 8. Chuyển chuỗi unsigned trở lại mẫu bit: `parseUnsignedInt`, `parseUnsignedLong`

Nếu một chuỗi unsigned vượt `Integer.MAX_VALUE` nhưng vẫn thuộc miền unsigned 32 bit, `Integer.parseInt` sẽ từ chối nó. Dùng `Integer.parseUnsignedInt` để đọc **mẫu bit 32 bit**:

```java
int bits = Integer.parseUnsignedInt("4294967295");

System.out.println(bits);                      // -1, signed interpretation
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
System.out.println(Integer.toHexString(bits)); // ffffffff
```

Hàm parser trả về **`int`**, không phải một loại `uint`. Điều quan trọng khi round-trip là giữ **mẫu bit**, dù biến `int` tạm thời có thể in signed là số âm.

Với cơ số 16:

```java
int b = Integer.parseUnsignedInt("ffffffff", 16); // bit pattern -1
String output = Integer.toHexString(b); // "ffffffff"
```

Các API `parseUnsignedInt` vẫn kiểm tra **chữ số hợp lệ và miền unsigned 32 bit**. Ví dụ chuỗi thập phân `"4294967296"` vượt miền không dấu sẽ gây `NumberFormatException`. Chúng không tự chấp nhận các prefix như `0x` trong overload cơ số 16, nên cần quy định/loại bỏ prefix theo hợp đồng đầu vào.

Với `long`, `Long.parseUnsignedLong("18446744073709551615")` trả mẫu bit tương ứng `-1L`, và `Long.toUnsignedString` hiển thị trở lại chuỗi số dương cực đại. Nếu cần lưu giá trị unsigned 64 bit dưới dạng số không âm cho phép toán tổng quát, cân nhắc `BigInteger`.

### Không nhầm parse số có dấu với parse mẫu bit

`Integer.parseInt("ffffffff", 16)` gây `NumberFormatException` do giá trị tích cực lớn hơn signed `int` (với chuỗi không có dấu trừ). `Integer.parseUnsignedInt("ffffffff", 16)` nhận vì nằm trong miền unsigned 32 bit, rồi cho mẫu `int` có dấu là `-1`. Đây là sự khác nhau về **miền phân tích**, không phải việc Java tự làm tràn mà không báo lỗi.

## 9. Ví dụ Java 17+ hoàn chỉnh

Tạo tệp `IntegerFormatsDemo.java`:

```java
public class IntegerFormatsDemo {
    public static void main(String[] args) {
        int number = 42;
        System.out.println("42 binary: " + Integer.toBinaryString(number));
        System.out.println("42 hex: " + Integer.toHexString(number));
        System.out.println("42 unsigned: " + Integer.toUnsignedString(number));

        System.out.println("-1 signed decimal: " + Integer.toString(-1));
        System.out.println("-1 unsigned decimal: " + Integer.toUnsignedString(-1));
        System.out.println("-1 binary: " + Integer.toBinaryString(-1));
        System.out.println("-1 hex: " + Integer.toHexString(-1));
        System.out.println("-1 signed hex: " + Integer.toString(-1, 16));
        System.out.println("-1 unsigned hex: " + Integer.toUnsignedString(-1, 16));

        int min = Integer.MIN_VALUE;
        System.out.println("MIN_VALUE unsigned: " + Integer.toUnsignedString(min));
        System.out.println("MIN_VALUE hex: " + Integer.toHexString(min));
        System.out.println("10 base 8: " + Integer.toUnsignedString(10, 8));
        System.out.println("31 base 36: " + Integer.toUnsignedString(31, 36));

        byte b = -1;
        System.out.println("byte -1 sign extended: " + Integer.toBinaryString(b));
        System.out.println("byte -1 masked: " + Integer.toBinaryString(b & 0xFF));
        System.out.println("byte -1 unsigned: " + Byte.toUnsignedInt(b));

        long big = -1L;
        System.out.println("long -1 unsigned: " + Long.toUnsignedString(big));
        System.out.println("long -1 hex: " + Long.toHexString(big));

        int parsed = Integer.parseUnsignedInt("4294967295");
        System.out.println("unsigned parsed bits: " + parsed);
        System.out.println("unsigned round trip: " + Integer.toUnsignedString(parsed));
        System.out.println("binary parse: " + Integer.parseUnsignedInt("11111111", 2));

        System.out.println("padded hex: " + String.format("%08x", number));
        System.out.println("padded binary: "
            + String.format("%8s", Integer.toBinaryString(number))
                .replace(' ', '0'));
    }
}
```

Biên dịch và chạy:

```bash
javac IntegerFormatsDemo.java
java IntegerFormatsDemo
```

Stdout đã kiểm chứng:

```text
42 binary: 101010
42 hex: 2a
42 unsigned: 42
-1 signed decimal: -1
-1 unsigned decimal: 4294967295
-1 binary: 11111111111111111111111111111111
-1 hex: ffffffff
-1 signed hex: -1
-1 unsigned hex: ffffffff
MIN_VALUE unsigned: 2147483648
MIN_VALUE hex: 80000000
10 base 8: 12
31 base 36: v
byte -1 sign extended: 11111111111111111111111111111111
byte -1 masked: 11111111
byte -1 unsigned: 255
long -1 unsigned: 18446744073709551615
long -1 hex: ffffffffffffffff
unsigned parsed bits: -1
unsigned round trip: 4294967295
binary parse: 255
padded hex: 0000002a
padded binary: 00101010
```

**Cách đọc chương trình:** Các dòng `42` minh họa cơ số; nhóm `-1` cho thấy cùng mẫu 32 bit có diễn giải signed/unsigned khác nhau; `MIN_VALUE` có bit cao nhất 1; nhóm `byte` giải thích sign extension và mặt nạ 8 bit; nhóm `long` hiển thị 64 bit; `parseUnsignedInt` round-trip về chuỗi unsigned; hai dòng cuối cho thấy định dạng **độ rộng cố định** không phải hành vi mặc định của `toBinaryString`/`toHexString`.

## 10. Những ứng dụng thực tế và cách chọn API

### Quan sát bit flags và masks

Khi kiểm tra một `int` gồm nhiều cờ bit, binary/hex giúp nhìn các vị trí bit đang bật:

```java
int flags = 0b1010_0101;
String hex = Integer.toHexString(flags);    // "a5"
String bits = Integer.toBinaryString(flags); // "10100101"
```

Để phân tích bit cụ thể, kết hợp toán tử `&`, `|`, `^`, `~`, `<<` và `>>>` trên giá trị nguyên. `toBinaryString` chỉ tạo **chuỗi hiển thị**, không thay thế phép toán bit.

### Giao diện hoặc log cần hiểu unsigned

Có hệ thống lưu số 32 bit trong `int` nhưng thực tế xem đó là **unsigned ID/counter**. Dùng `Integer.toUnsignedString` khi hiển thị để người dùng không nhìn thấy số âm không mong muốn. Tuy nhiên, nếu phép so sánh thứ tự của ID/counter cũng theo unsigned, dùng `Integer.compareUnsigned` thay vì `<` giữa hai `int`.

### Lưu trữ và giao thức nhị phân

`"ffffffff"` là **8 ký tự hex**, không phải bốn byte `0xFF`. Nếu giao thức cần thực sự gửi byte, phải chuyển bit pattern thành mảng byte (ví dụ `ByteBuffer.putInt` với byte order được chỉ định). `toHexString` hữu ích để debug nhưng tự nó **không quyết định endianness** (big-endian hay little-endian).

Ví dụ `0x12345678` có cùng chuỗi hex `"12345678"` dù khi serialize big-endian sẽ là các byte `12 34 56 78` và little-endian là `78 56 34 12`. Byte order được quyết định ở bước đọc/ghi byte, không bởi phương thức format số thành chuỗi.

### Chọn theo yêu cầu

| Cần gì? | API nên xem xét |
| --- | --- |
| Xem bit `int` theo nhị phân | `Integer.toBinaryString(value)` |
| Xem bit `int` bằng hex | `Integer.toHexString(value)` |
| Hiển thị `int` có dấu thập phân | `Integer.toString(value)` |
| Hiển thị `int` không dấu thập phân | `Integer.toUnsignedString(value)` |
| Hiển thị `int` không dấu với radix bất kỳ 2–36 | `Integer.toUnsignedString(value, radix)` |
| Làm việc với giá trị `long` | Các API `Long` tương ứng |
| Xem đúng 8 bit thấp của `byte` | Mask `value & 0xFF`, rồi format/pad |
| Parse lại unsigned 32/64 bit | `Integer.parseUnsignedInt` / `Long.parseUnsignedLong` |
| In hex luôn đủ chữ số | `String.format("%08x", intValue)` hoặc format thủ công |
| Xử lý giá trị unsigned trong phép tính | `compareUnsigned`, `divideUnsigned`, `remainderUnsigned`, hoặc kiểu rộng hơn |

Không nhất thiết mọi số âm đều phải in unsigned: với số dư nợ, nhiệt độ âm, độ lệch hay tọa độ có dấu, `Integer.toString` thường mới đúng ngữ nghĩa nghiệp vụ. Sử dụng `toUnsignedString` khi **dữ liệu thật sự mang ý nghĩa không dấu hoặc cần quan sát bit**.

## 11. Sai lầm thường gặp

1. **“`toBinaryString` trả integer nhị phân.”** Sai: trả `String`, không trả một giá trị primitive số mới.
2. **“`toHexString` luôn có tiền tố `0x`.”** Sai: kết quả chỉ gồm chữ số hex.
3. **“`toBinaryString(42)` luôn dài 32 ký tự.”** Sai: với số dương, zero đầu được bỏ; cần pad nếu giao thức yêu cầu.
4. **“`Integer.toBinaryString(-1)` trả `"-1"`.”** Sai: trả 32 bit `1` của số nguyên có dấu -1.
5. **“`toUnsignedString(-1)` biến `int` thành kiểu `uint`.”** Sai: biến vẫn là `int -1`, chỉ cách hiển thị đổi thành `4294967295`.
6. **“`Integer.toString(-1, 16)` giống `Integer.toHexString(-1)`.”** Sai: cái đầu trả `"-1"`, cái sau trả `"ffffffff"`.
7. **“Truyền `byte -1` vào `Integer.toBinaryString` sẽ trả 8 bit.”** Sai: `byte` được sign-extend thành `int`, nên cho 32 bit; mask `0xFF` để lấy 8 bit.
8. **“`String.format("%08x", x)` và `toHexString(x)` có cùng quy tắc padding.”** Sai: `%08x` yêu cầu độ rộng tối thiểu 8 và pad zero, còn `toHexString` không pad số dương.
9. **“Unsigned 64 bit luôn vừa `long` dưới dạng số dương.”** Sai: `2^64 - 1` vượt `Long.MAX_VALUE`; chỉ có thể giữ mẫu bit và diễn giải phù hợp.
10. **“`parseUnsignedInt` luôn trả số không âm khi `System.out.println(int)`.”** Sai: giá trị `int` có dấu có thể âm; dùng `toUnsignedString` khi in.
11. **“Chuỗi hex chứa ký tự `ff` là hai byte dữ liệu nhị phân.”** Sai: đó là hai ký tự; cần chuyển đổi thực sang byte nếu giao thức yêu cầu.
12. **“Đã gọi `toUnsignedString` thì toán tử `<` trên `int` sẽ so sánh không dấu.”** Sai: chỉ thao tác trên chuỗi hiển thị; phép so sánh `int` vẫn có dấu.
13. **“`Integer.parseInt("ffffffff", 16)` sẽ thành -1 vì chuỗi là mẫu bit.”** Sai: parser signed từ chuỗi không dấu trừ thấy số quá miền `int` và báo lỗi; dùng `parseUnsignedInt` để giải mã bit pattern.
14. **“Dùng hex luôn mô tả đúng thứ tự byte mạng.”** Sai: hex biểu diễn giá trị, còn endianness thuộc bước chuyển sang byte.

## 12. Câu hỏi tự kiểm tra

**1. `Integer.toBinaryString(10)` trả gì?** → `"1010"`.

**2. `Integer.toHexString(255)` trả gì?** → `"ff"` (không có `0x`).

**3. `Integer.toUnsignedString(-1)` cho giá trị nào?** → `"4294967295"`; biến gốc vẫn là `int -1`.

**4. Vì sao `Integer.toBinaryString(-1)` có 32 chữ `1`?** → `-1` biểu diễn bù hai bằng toàn bit 1 trong 32 bit.

**5. `Integer.toString(-1, 16)` khác `Integer.toHexString(-1)` như thế nào?** → Một bên là chuỗi số có dấu `"-1"`, bên kia là bit pattern hex `"ffffffff"`.

**6. Làm sao lấy chuỗi nhị phân của `byte -1` đúng 8 bit?** → Dùng `Integer.toBinaryString(b & 0xFF)`, với `b=-1` cho `"11111111"`; nếu `b` dương nhỏ, pad thêm zero.

**7. Làm sao in `int -1` theo unsigned 32 bit rồi parse lại giữ bit?** → `String s = Integer.toUnsignedString(-1); int raw = Integer.parseUnsignedInt(s);`; `raw` là mẫu `int -1`.

**8. `Long.toUnsignedString(-1L)` trả gì?** → `"18446744073709551615"`.

**9. `toHexString` có quyết định byte order khi ghi file không?** → Không; byte order được xác định ở bước serialize thành các byte.

**10. Khi nào không nên dùng `toUnsignedString`?** → Khi dữ liệu thật sự có ý nghĩa signed, ví dụ nợ âm hoặc nhiệt độ âm; hãy hiển thị theo ngữ nghĩa đúng.

**Ghi nhớ:** `toBinaryString` và `toHexString` biến **mẫu bit** `int`/`long` thành chuỗi cơ số 2/16, thường theo cách nhìn **không dấu**. `toUnsignedString` mặc định biểu diễn cùng mẫu bit ở **thập phân không dấu**, hoặc radix được chỉ định. Các hàm **không sửa bit, không tạo kiểu unsigned mới và không đổi ý nghĩa các phép toán khác**. Với `byte`/`short` âm, xử lý sign extension bằng mask trước khi format; với yêu cầu chiều rộng cố định, bổ sung padding.
