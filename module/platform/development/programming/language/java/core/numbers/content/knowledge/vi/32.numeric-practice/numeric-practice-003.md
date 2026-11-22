# Đọc ghi số theo nhiều cơ số và dạng không dấu trong Java

## 1. Mục tiêu: cùng giá trị, nhiều cách biểu diễn

Một con số có thể được **đọc từ chuỗi** hoặc **xuất thành chuỗi** theo nhiều cơ số: nhị phân (base 2), bát phân (base 8), thập phân (base 10), thập lục phân (base 16), hoặc các cơ số từ 2 đến 36. Đồng thời, Java có `int` và `long` **có dấu** nhưng không có kiểu nguyên primitive `unsigned int`/`unsigned long` riêng.

Bởi vậy, khi xử lý bit mask, địa chỉ, protocol, checksum, ID từ hệ thống khác hoặc trường nhị phân trong tệp, cần phân biệt ba thứ:

1. **Giá trị toán học**: ví dụ số dương 4.294.967.295.
2. **Mẫu bit lưu trong bộ nhớ**: ví dụ 32 bit toàn `1`.
3. **Cách diễn giải và trình bày**: cùng mẫu 32 bit đó là `-1` theo `int` có dấu, nhưng là `4294967295` theo diễn giải không dấu.

Trong bài này, “đọc” chủ yếu có nghĩa **parse văn bản hoặc lấy các bit từ dữ liệu**; “ghi” có nghĩa **format ra văn bản hoặc chuyển lại thành biểu diễn bit phù hợp**. Cách làm đúng phụ thuộc giao thức: nó quy định cơ số, độ rộng bit, dấu, leading zeros, byte order và cách xử lý dữ liệu không hợp lệ.

## 2. Cơ số (radix) và giá trị chữ số

Trong hệ cơ số `r`, mỗi chữ số ở vị trí thứ `k` đóng góp `digit × r^k`. Ví dụ:

\[
(1010)_2=1\cdot2^3+0\cdot2^2+1\cdot2^1+0=10.
\]

Và:

\[
(\text{FF})_{16}=15\cdot16+15=255.
\]

Bảng cơ bản:

| Giá trị thập phân | Nhị phân (2) | Bát phân (8) | Hex (16) |
| ---: | ---: | ---: | --- |
| 10 | `1010` | `12` | `A` |
| 15 | `1111` | `17` | `F` |
| 16 | `10000` | `20` | `10` |
| 255 | `11111111` | `377` | `FF` |
| 256 | `100000000` | `400` | `100` |

Java cho phép radix **2..36** trong `Integer.parseInt`, `Long.parseLong` và nhiều API chuyển đổi. Chữ số `0`–`9` có giá trị 0–9; các chữ `a`–`z` (hoặc `A`–`Z`) có giá trị 10–35 trong quá trình parse. Ví dụ `z` trong base 36 biểu diễn 35.

Cơ số là **quy tắc đọc chuỗi**, không thay đổi giá trị số nguyên sau khi parse. Sau:

~~~java
int x = Integer.parseInt("FF", 16);
// x == 255
~~~

`x` không “mang cơ số 16” trong kiểu `int`; nó chỉ lưu số 255. Khi cần hiển thị hex, phải format nó thành chuỗi hex.

## 3. Đọc số có dấu: parseInt, parseLong và BigInteger

### 3.1. Parse từ văn bản với radix được chỉ định

~~~java
int binary = Integer.parseInt("1010", 2); // 10
int octal = Integer.parseInt("377", 8);  // 255
int hex = Integer.parseInt("FF", 16);    // 255
int base36 = Integer.parseInt("z", 36);  // 35

long large = Long.parseLong("7FFFFFFFFFFFFFFF", 16);
// 9223372036854775807L == Long.MAX_VALUE
~~~

Có thể truyền số có dấu bằng `+` hoặc `-` ở đầu:

~~~java
int a = Integer.parseInt("-FF", 16); // -255
int b = Integer.parseInt("+1010", 2); // 10
~~~

Tuy nhiên `Integer.parseInt("FFFFFFFF", 16)` **ném `NumberFormatException`**: chuỗi hex dương ấy biểu diễn 4.294.967.295, nằm ngoài phạm vi `int` có dấu. Nó **không** tự coi `FFFFFFFF` là `-1`. Muốn diễn giải mẫu bit theo kiểu unsigned, dùng `parseUnsignedInt` (phần 5).

Điểm cốt lõi: API parse signed đang cố đọc **giá trị toán học có dấu** trong miền `int` hoặc `long`, không phải tự nhận một chuỗi bit bù hai.

### 3.2. Prefix 0x/0b không mặc định được parseInt nhận

~~~java
Integer.parseInt("FF", 16);       // 255
Integer.parseInt("0xFF", 16);     // NumberFormatException
Integer.parseInt("0b1010", 2);   // NumberFormatException
Integer.decode("0xFF");          // 255
Integer.decode("#FF");           // 255
Integer.decode("0377");          // 255: tiền tố 0 thể hiện bát phân
~~~

`parseInt(text, radix)` yêu cầu các chữ số hợp lệ của radix đã cho, ngoại trừ dấu `+`/`-` được hỗ trợ; không tự xử lý các prefix literal `0x`, `0b`. `Integer.decode`/`Long.decode` có quy tắc nhận diện `0x`, `0X`, `#` hoặc tiền tố `0` cho bát phân, nhưng **không được xem là parser tổng quát cho literal nhị phân `0b`**.

Với định dạng text theo một protocol, cách dễ kiểm soát nhất là xác thực prefix riêng (nếu có), xác định radix, rồi parse phần chữ số bằng đúng API. Đặc biệt cẩn trọng với các số có leading zero: `Integer.parseInt("010",10) == 10`, còn `Integer.decode("010") == 8`.

### 3.3. Cú pháp literal trong source code khác văn bản runtime

Khi viết Java trực tiếp:

~~~java
int binaryLiteral = 0b1010; // 10
int hexLiteral = 0xFF;      // 255
int octalLiteral = 0377;   // 255: cú pháp octal cũ
int grouped = 1_000_000;   // 1000000
~~~

Các prefix và dấu gạch dưới được **Java compiler xử lý trong mã nguồn**. Điều đó không có nghĩa `Integer.parseInt("0b1010",2)` hoặc `Integer.parseInt("1_000_000",10)` sẽ nhận. Các chuỗi nhập có dấu `_` phải được validate theo schema trước khi loại dấu phân nhóm; không xóa bừa ký tự bất hợp lệ của dữ liệu bên ngoài.

### 3.4. BigInteger cho giá trị vượt miền int/long

~~~java
import java.math.BigInteger;

BigInteger huge = new BigInteger("FFFFFFFFFFFFFFFF", 16);
// 18446744073709551615, lớn hơn Long.MAX_VALUE

BigInteger base36 = new BigInteger("Z", 36);
// 35

String backToHex = huge.toString(16);
// "ffffffffffffffff"
~~~

`BigInteger(String, radix)` hữu ích khi **giá trị toán học** vượt 64 bit hoặc khi phải kiểm soát thao tác chính xác trên số nguyên lớn. `BigInteger` hỗ trợ số âm, nên `new BigInteger("-FF",16)` cho -255. Nó không tự gán quy ước “unsigned 64-bit” cho mọi giá trị: ứng dụng vẫn phải kiểm tra phạm vi hợp đồng khi cần.

## 4. Ghi số có dấu theo nhiều cơ số

Dùng `Integer.toString(value, radix)`, `Long.toString(value, radix)`:

~~~java
int n = 255;

String binary = Integer.toString(n, 2); // "11111111"
String octal = Integer.toString(n, 8);  // "377"
String decimal = Integer.toString(n, 10); // "255"
String hex = Integer.toString(n, 16);   // "ff"
String base36 = Integer.toString(35, 36); // "z"
~~~

Các hàm chuyên biệt cũng có:

~~~java
Integer.toBinaryString(255); // "11111111"
Integer.toOctalString(255);  // "377"
Integer.toHexString(255);    // "ff"

Long.toBinaryString(255L);  // "11111111"
Long.toHexString(255L);     // "ff"
~~~

**Phân biệt số âm:** `Integer.toString(-1,16)` trả `"-1"` (một số âm theo base 16), còn `Integer.toHexString(-1)` trả `"ffffffff"`, tức **mẫu bit 32 bit** diễn giải không dấu. Đây là hai mục tiêu format khác nhau.

Nếu giao diện cần ký tự `A`–`F` viết hoa, có thể dùng `toUpperCase(Locale.ROOT)` trên chuỗi hex hoặc formatter thích hợp:

~~~java
String upperHex = Integer.toHexString(255)
        .toUpperCase(java.util.Locale.ROOT); // "FF"
~~~

Lưu ý độ rộng: `Integer.toHexString(5)` cho `"5"`, không tự thêm `00000005`. Nếu cần 8 chữ số cho 32 bit, định dạng riêng hoặc padding với kiểm tra độ dài, ví dụ:

~~~java
String hex32 = String.format(java.util.Locale.ROOT,
        "%08X", 5); // "00000005"
~~~

`%X` trong `Formatter` là **thập lục phân**, không phải nhị phân. Đừng dùng `%b` để in binary: trong Java `Formatter`, `%b` là conversion boolean (giá trị true/false theo quy tắc), không phải base 2.

## 5. Đọc và ghi int không dấu (unsigned 32-bit)

Java không có kiểu primitive `uint32` riêng. Đối với giá trị unsigned 32-bit `0..4294967295`, bạn có thể dùng **`int` như container 32 bit**, rồi dùng các API unsigned khi cần diễn giải.

### 5.1. Đọc mẫu 32 bit bằng parseUnsignedInt

~~~java
int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
// bits == -1 khi nhìn như int signed.
// Nhưng 32 bit toàn 1 tương ứng unsigned 4294967295.
~~~

`Integer.parseUnsignedInt(text, radix)` nhận giá trị nguyên **không âm** trong `[0, 2^32 - 1]` của radix, rồi trả `int` chứa đúng 32 bit. Vì `int` là có dấu nên kết quả có thể âm.

- `Integer.parseUnsignedInt("FFFFFFFF",16)` cho `-1`.
- `Integer.parseUnsignedInt("80000000",16)` cho `Integer.MIN_VALUE`.
- `Integer.parseUnsignedInt("100000000",16)` ném `NumberFormatException` vì lớn hơn 32 bit.
- Chuỗi với dấu trừ như `"-1"` không phải giá trị unsigned hợp lệ; đừng dùng nó để biểu diễn `0xFFFFFFFF`.

### 5.2. Ghi dưới dạng unsigned

~~~java
int bits = -1;

String signed = Integer.toString(bits); // "-1"
String unsignedDec = Integer.toUnsignedString(bits); // "4294967295"
String unsignedHex = Integer.toUnsignedString(bits, 16); // "ffffffff"
String unsignedBin = Integer.toUnsignedString(bits, 2);
// 32 ký tự '1'
~~~

`Integer.toHexString(bits)` cũng biểu diễn mẫu bit theo hex không dấu, nên với `-1` cho `"ffffffff"`. Nhưng `Integer.toString(bits,16)` khác: `"-1"`.

Muốn tính toán số học không dấu 32 bit trong miền số dương có thể biểu diễn được, chuyển sang `long`:

~~~java
int rawBits = -1;
long unsignedValue = Integer.toUnsignedLong(rawBits);
// 4294967295L
~~~

Vì `long` có 64 bit, toàn bộ miền unsigned 32 bit đều vừa trong miền **signed long**. Đây là phương án thuận tiện khi cần so, cộng hoặc xuất một trường `uint32`, miễn là tiếp tục quản lý overflow có thể xảy ra khi các giá trị cộng nhân lớn hơn `Long.MAX_VALUE`.

### 5.3. So sánh và chia không dấu

Cùng bit `-1` theo signed là số nhỏ hơn `1`, nhưng theo unsigned là `4294967295` (lớn hơn 1):

~~~java
int bits = -1;

int signedCompare = Integer.compare(bits, 1); // < 0
int unsignedCompare = Integer.compareUnsigned(bits, 1); // > 0

int quotient = Integer.divideUnsigned(bits, 2); // 2147483647
int remainder = Integer.remainderUnsigned(bits, 2); // 1
~~~

`compareUnsigned` trả số âm/0/dương theo quy tắc so sánh, **không hứa luôn trả đúng -1 hoặc 1 trong mọi triển khai**. Kiểm tra quan hệ `< 0`, `== 0`, `> 0` thay vì phụ thuộc một trị số cụ thể.

Các phép cộng/trừ/nhân primitive vẫn xử lý các bit theo modulo \(2^{32}\). Nếu hợp đồng muốn **báo lỗi khi phép toán unsigned vượt 2^32-1**, hãy mở rộng lên `long` trước khi tính và so phạm vi, hoặc dùng `BigInteger` khi phép tính có thể lớn hơn `long`. Không coi phép `a + b` thông thường tự phát hiện tràn unsigned.

## 6. Đọc và ghi long không dấu (unsigned 64-bit)

Miền unsigned 64 bit:

\[
0 \le u \le 2^{64}-1=18446744073709551615.
\]

Miền signed long lại chỉ đến `9223372036854775807`. Vì vậy **không thể biểu diễn toàn bộ unsigned 64 bit thành một giá trị `long` dương**.

### 6.1. Giữ mẫu bit bằng long

~~~java
long bits = Long.parseUnsignedLong("18446744073709551615");
// bits == -1L khi xem là long signed

String unsignedDec = Long.toUnsignedString(bits);
// "18446744073709551615"

String unsignedHex = Long.toUnsignedString(bits, 16);
// "ffffffffffffffff"
~~~

`Long.parseUnsignedLong` chấp nhận giá trị không âm trong phạm vi 64 bit và trả đúng mẫu bit. Chuỗi lớn hơn, như `"18446744073709551616"`, ném `NumberFormatException`.

`Long.parseLong("18446744073709551615")` **không** thành công: đó là giá trị dương vượt `Long.MAX_VALUE`. Nếu muốn lưu nguyên văn giá trị dương thay vì chỉ bit pattern, chọn `BigInteger`.

### 6.2. Diễn giải giá trị unsigned 64 bit dưới dạng BigInteger dương

~~~java
long bits = -1L;

java.math.BigInteger unsigned =
        new java.math.BigInteger(Long.toUnsignedString(bits));
// 18446744073709551615

String hex = unsigned.toString(16);
// "ffffffffffffffff"
~~~

Đây là cách dễ hiểu: đổi bit pattern thành chuỗi decimal unsigned, rồi parse thành `BigInteger` dương. Có các cách hiệu quả hơn dựa trên hai nửa 32 bit hoặc byte array với `new BigInteger(1, bytes)`, nhưng phải cẩn trọng **độ rộng, thứ tự byte và dấu**.

Ví dụ kiểm tra phạm vi khi cần chuyển ngược về unsigned long:

~~~java
BigInteger maxUnsignedLong = BigInteger.ONE.shiftLeft(64)
        .subtract(BigInteger.ONE);

BigInteger candidate = new BigInteger("18446744073709551615");

if (candidate.signum() < 0
        || candidate.compareTo(maxUnsignedLong) > 0) {
    throw new IllegalArgumentException("Out of uint64 range");
}

// longValue() trả 64 bit thấp (có thể âm khi nhìn theo long signed).
long storageBits = candidate.longValue();
String roundTrip = Long.toUnsignedString(storageBits);
~~~

Ở đây `longValue()` chỉ an toàn **theo hợp đồng lưu bit pattern** và **sau khi đã kiểm tra** candidate nằm trong `[0,2^64-1]`. Nó không diễn giải unsigned lớn thành long dương. `longValueExact()` lại sẽ ném lỗi với các giá trị unsigned lớn hơn `Long.MAX_VALUE`, dù chúng hợp lệ trong uint64.

### 6.3. Các phép so và chia unsigned long

~~~java
long allOnes = -1L;

boolean greaterThanOne =
        Long.compareUnsigned(allOnes, 1L) > 0; // true

long q = Long.divideUnsigned(allOnes, 2L);
// Khi xem signed long: 9223372036854775807

long r = Long.remainderUnsigned(allOnes, 2L); // 1
~~~

Các toán tử so sánh `<`, `>` trên primitive `long` dùng **signed semantics**, không phù hợp để so các giá trị unsigned có bit dấu bật. Nếu dữ liệu đến từ protocol định nghĩa uint64, ưu tiên `Long.compareUnsigned`, `divideUnsigned`, `remainderUnsigned` và `toUnsignedString` để xử lý đúng.

## 7. Byte và short không dấu: đọc tệp nhị phân

Một byte trong Java (`byte`) có dấu, miền `-128..127`, nhưng một trường `uint8` của tệp nhị phân có miền `0..255`.

~~~java
byte raw = (byte) 0xFF; // raw == -1 khi xem là byte signed

int unsignedByte = Byte.toUnsignedInt(raw); // 255
int masked = raw & 0xFF; // 255
~~~

Phép `& 0xFF` loại bit dấu đã được sign-extend khi chuyển `byte` sang `int`. `Byte.toUnsignedInt` thể hiện mục tiêu rõ ràng hơn. Với `short` unsigned 16 bit có `Short.toUnsignedInt(rawShort)`, miền `0..65535`.

Với `DataInputStream`:

~~~java
// in là DataInputStream hợp lệ đã mở:
int u8 = in.readUnsignedByte();  // 0..255
int u16 = in.readUnsignedShort(); // 0..65535, byte order big-endian
~~~

Đây là snippet nằm trong một phương thức có biến `DataInputStream in`; có thể phát sinh `IOException`, bao gồm EOF. Với `ByteBuffer`, phải quy định `ByteOrder.BIG_ENDIAN` hay `LITTLE_ENDIAN` theo format, rồi `getInt()`/`getLong()` lấy các bit và dùng API unsigned để diễn giải. **Endian** quyết định cách ghép byte thành số nhiều byte, còn **signed/unsigned** quyết định cách đọc giá trị sau khi đã ghép: đây là hai vấn đề khác nhau.

### 7.1. Đầu ra hex cố định độ rộng

Trong một protocol, mỗi byte thường hiển thị bằng **hai chữ số hex**, mỗi số 32 bit là **tám chữ số hex**, mỗi số 64 bit là **16 chữ số hex**. Ví dụ:

~~~java
byte b = (byte) 0x0A;

String byteHex = String.format(java.util.Locale.ROOT,
        "%02X", Byte.toUnsignedInt(b)); // "0A"

String intHex = String.format(java.util.Locale.ROOT,
        "%08X", 5); // "00000005"
~~~

Padding có thể quan trọng để khôi phục chính xác độ rộng của tệp/giao thức. `Integer.toHexString(5)` trả `"5"`, làm mất thông tin “8 chữ số” nếu bên nhận đang mong đợi trường 32 bit fixed-width. Ngược lại, padding không làm tăng độ chính xác toán học; nó chỉ là quy ước biểu diễn.

## 8. Chương trình Java 17+ hoàn chỉnh

Chương trình sau thể hiện cả signed parse/format lẫn unsigned parse/format, nâng unsigned int lên long, so/chia không dấu, BigInteger cho uint64 và các lỗi đầu vào. Tạo file **`RadixUnsignedDemo.java`**:

~~~java
import java.math.BigInteger;
import java.util.Locale;

public class RadixUnsignedDemo {
    public static void main(String[] args) {
        int value = Integer.parseInt("FF", 16);

        System.out.println("hex FF -> dec: " + value);
        System.out.println("255 -> binary: " + Integer.toString(value, 2));
        System.out.println("255 -> octal: " + Integer.toString(value, 8));
        System.out.println("35 -> base36: " + Integer.toString(35, 36));
        System.out.println("decode 0xFF: " + Integer.decode("0xFF"));

        int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
        System.out.println("int signed storage: " + bits);
        System.out.println("int unsigned dec: "
                + Integer.toUnsignedString(bits));
        System.out.println("int unsigned hex: "
                + Integer.toUnsignedString(bits, 16));
        System.out.println("int unsigned as long: "
                + Integer.toUnsignedLong(bits));
        System.out.println("int compareUnsigned to 1: "
                + Integer.compareUnsigned(bits, 1));
        System.out.println("int divideUnsigned by 2: "
                + Integer.divideUnsigned(bits, 2));
        System.out.println("int remainderUnsigned by 2: "
                + Integer.remainderUnsigned(bits, 2));

        long longBits = Long.parseUnsignedLong(
                "18446744073709551615");
        System.out.println("long signed storage: " + longBits);
        System.out.println("long unsigned dec: "
                + Long.toUnsignedString(longBits));
        System.out.println("long unsigned hex: "
                + Long.toUnsignedString(longBits, 16));
        System.out.println("unsigned long BigInteger: "
                + new BigInteger(Long.toUnsignedString(longBits)));

        System.out.println("hex padded: "
                + String.format(Locale.ROOT, "%08X", bits));
        System.out.println("byte unsigned: "
                + Byte.toUnsignedInt((byte) 0xFF));
        System.out.println("binary padded: "
                + String.format(Locale.ROOT, "%8s",
                        Integer.toBinaryString(5)).replace(' ', '0'));

        try {
            Integer.parseInt("FFFFFFFF", 16);
        } catch (NumberFormatException ex) {
            System.out.println("signed hex overflow: NumberFormatException");
        }

        try {
            Integer.parseUnsignedInt("100000000", 16);
        } catch (NumberFormatException ex) {
            System.out.println("unsigned int overflow: NumberFormatException");
        }

        try {
            Long.parseUnsignedLong("18446744073709551616");
        } catch (NumberFormatException ex) {
            System.out.println("unsigned long overflow: NumberFormatException");
        }
    }
}
~~~

Chạy:

~~~bash
javac RadixUnsignedDemo.java
java RadixUnsignedDemo
~~~

Kết quả:

~~~text
hex FF -> dec: 255
255 -> binary: 11111111
255 -> octal: 377
35 -> base36: z
decode 0xFF: 255
int signed storage: -1
int unsigned dec: 4294967295
int unsigned hex: ffffffff
int unsigned as long: 4294967295
int compareUnsigned to 1: 1
int divideUnsigned by 2: 2147483647
int remainderUnsigned by 2: 1
long signed storage: -1
long unsigned dec: 18446744073709551615
long unsigned hex: ffffffffffffffff
unsigned long BigInteger: 18446744073709551615
hex padded: FFFFFFFF
byte unsigned: 255
binary padded: 00000101
signed hex overflow: NumberFormatException
unsigned int overflow: NumberFormatException
unsigned long overflow: NumberFormatException
~~~

Bảng giải thích nhanh:

| Dòng chương trình | Điều được kiểm chứng |
| --- | --- |
| `hex FF -> dec: 255` | Parse hex chuyển sang giá trị số, không “giữ radix” trong biến |
| `int signed storage: -1` | `FFFFFFFF` lưu thành mẫu bit 32 bit toàn 1 |
| `int unsigned dec: 4294967295` | Cùng bit được format theo miền unsigned 32 bit |
| `int unsigned as long: 4294967295` | `long` đủ rộng giữ uint32 dưới dạng số dương |
| `long signed storage: -1` | uint64 lớn nhất không vừa signed long dương |
| `unsigned long BigInteger: 18446744073709551615` | `BigInteger` lưu giá trị dương đầy đủ |
| Các dòng `NumberFormatException` | Parser chặn giá trị vượt miền đã định, không tự wrap khi đọc text |
| `hex padded`, `binary padded` | Cơ số và độ rộng trình bày là hai chính sách riêng |

Đầu ra là deterministic vì bài không sinh ngẫu nhiên, và đoạn ví dụ dùng các API chuẩn của Java 17. Đừng thay `Long.parseUnsignedLong` bằng `Long.parseLong` ở ví dụ max uint64: signed long sẽ ném lỗi vượt miền.

## 9. Round-trip: đọc–ghi không đổi giá trị hoặc mẫu bit

### 9.1. Round-trip signed

Đối với một `int x` và cơ số hợp lệ từ 2 đến 36:

~~~java
int x = -255;
int radix = 16;

String text = Integer.toString(x, radix); // "-ff"
int parsed = Integer.parseInt(text, radix); // -255
~~~

Chuỗi signed phản ánh **giá trị toán học** của `x`.

### 9.2. Round-trip unsigned theo bit pattern

~~~java
int originalBits = -1;
int radix = 16;

String wireText = Integer.toUnsignedString(originalBits, radix);
// "ffffffff"

int restoredBits = Integer.parseUnsignedInt(wireText, radix);
// -1, cùng bit pattern với originalBits

boolean sameBits = restoredBits == originalBits; // true
~~~

Với `long`, thay bằng `Long.toUnsignedString` và `Long.parseUnsignedLong`. Đây là round-trip của **bit pattern**, không phải bảo đảm giá trị signed hiển thị dương.

Có thể viết test thuộc tính:

~~~java
for (int radix = Character.MIN_RADIX;
        radix <= Character.MAX_RADIX; radix++) {
    int value = -123456789;
    String text = Integer.toUnsignedString(value, radix);
    int reconstructed = Integer.parseUnsignedInt(text, radix);
    if (reconstructed != value) {
        throw new AssertionError("Mismatch at radix " + radix);
    }
}
~~~

Đoạn code được đặt trong một phương thức hợp lệ. Để kiểm thử rộng hơn, chọn các biên `0`, `1`, `-1`, `Integer.MIN_VALUE`, `Integer.MAX_VALUE` và nhiều giá trị ngẫu nhiên cố định seed. Cần nhớ `MIN_RADIX=2` và `MAX_RADIX=36`.

### 9.3. Leading zeros, chữ hoa và tính canonical

Đọc hai chuỗi `"000A"` và `"a"` với radix 16 đều được giá trị 10, nhưng format theo `Integer.toString(10,16)` trở lại thường là `"a"`, **không phục hồi chính xác độ rộng/chữ hoa ban đầu**.

Nếu yêu cầu truyền dữ liệu dưới dạng đúng 4 ký tự hex viết hoa, phải lưu hoặc quy định riêng **fixed width = 4**, **case = uppercase**, **prefix = không có**, và chính sách kiểm tra đầu vào. Parse/format số học không thể tự giữ các đặc điểm về bố cục văn bản đã bị bỏ qua.

Nếu định dạng sử dụng `0x`, `0b` hoặc các dấu phân nhóm, parser phải tách/validate chúng một cách rõ ràng. Đừng trộn “chuỗi giá trị” với “định dạng hiển thị” mà không có hợp đồng.

## 10. Kiểm thử và chẩn đoán dữ liệu đầu vào

### 10.1. Những trường hợp phải xác thực

Các API `parseInt`, `parseLong`, `parseUnsignedInt`, `parseUnsignedLong` có thể ném `NumberFormatException` khi:

- Chuỗi có chữ số không hợp lệ với radix: ví dụ `"2"` trong base 2, `"G"` trong base 16.
- Giá trị vượt miền có dấu/không dấu tương ứng.
- Không có chữ số cần parse, chẳng hạn chuỗi rỗng.
- Có prefix mà API không nhận, ví dụ `"0xFF"` với `parseInt(...,16)`.
- Dấu trừ xuất hiện trong dữ liệu unsigned không âm theo contract.
- Radix ở ngoài khoảng hỗ trợ (với các parser có tham số radix).

`null` cũng không phải một chuỗi số hợp lệ; tùy overload/JDK, API có thể báo `NumberFormatException` hoặc lỗi liên quan. Ở ranh giới ứng dụng, nên kiểm tra null rõ ràng trước khi parse để có thông báo xác thực dễ hiểu thay vì phụ thuộc message nội bộ của thư viện.

Ví dụ:

~~~java
static int parseHexUnsigned32(String input) {
    if (input == null || !input.matches("[0-9A-Fa-f]{1,8}")) {
        throw new IllegalArgumentException("Expected 1..8 hex digits");
    }
    return Integer.parseUnsignedInt(input, 16);
}
~~~

Đây là một **phương thức** cần đặt trong lớp Java. Nó cố ý chỉ nhận ASCII hex không prefix, không khoảng trắng, không dấu âm và tối đa 8 chữ số. Tùy định dạng của bạn, có thể cần yêu cầu **đúng 8 chữ số** thay vì 1..8.

Lưu ý một số API parse của Java nhận ký tự chữ số Unicode theo `Character.digit`; nếu protocol yêu cầu ASCII nghiêm ngặt, tự validate alphabet trước. Không được mặc định rằng “parse thành công” đã đồng nghĩa đầu vào có đúng tập ký tự mà giao thức quy định.

### 10.2. Format phải phản ánh kiểu và độ rộng

Với số `-1`:

| Phương thức | Chuỗi |
| --- | --- |
| `Integer.toString(-1, 16)` | `-1` |
| `Integer.toHexString(-1)` | `ffffffff` |
| `Integer.toUnsignedString(-1)` | `4294967295` |
| `Long.toString(-1L, 16)` | `-1` |
| `Long.toHexString(-1L)` | `ffffffffffffffff` |
| `Long.toUnsignedString(-1L)` | `18446744073709551615` |

Nếu gửi một trường 32-bit dưới dạng 64-bit hex, thêm các số `f` có thể làm người nhận tưởng giá trị lớn hơn. Đảm bảo **độ rộng 32/64**, **signedness** và **radix** khớp với schema. Đừng lấy `toHexString` của một `long` đã sign-extend từ `int` rồi kỳ vọng luôn nhận đúng 8 ký tự.

### 10.3. Endian và unsigned là hai tầng khác nhau

Ví dụ hai byte `01 00`:

- Big-endian 16 bit: `0x0100 = 256`.
- Little-endian 16 bit: `0x0001 = 1`.

Cả hai đều có thể được diễn giải dưới dạng unsigned 16-bit sau khi ghép. Nếu đọc từ `ByteBuffer`, chọn `order(ByteOrder.LITTLE_ENDIAN)` hoặc `order(ByteOrder.BIG_ENDIAN)` theo giao thức, rồi sử dụng `Short.toUnsignedInt` hoặc các hàm tương ứng. Không sửa lỗi byte order bằng `toUnsignedString`; nó chỉ thay cách **diễn giải dấu**, không tráo thứ tự byte.

## 11. Các lỗi phổ biến

1. **Tưởng Java có primitive uint32/uint64 riêng.** Không có; dùng `int`/`long` làm bit container với API unsigned, hoặc dùng `long`/`BigInteger` cho giá trị dương cần giữ.
2. **Đọc `FFFFFFFF` bằng `Integer.parseInt(...,16)`.** Nó vượt int signed; muốn 32 bit toàn 1 dùng `parseUnsignedInt`.
3. **Dùng `Long.parseLong` cho max uint64.** `18446744073709551615` vượt signed long; dùng `parseUnsignedLong` hoặc `BigInteger`.
4. **Cho rằng `parseInt("0xFF",16)` nhận prefix.** Không; `decode` có quy tắc riêng hoặc tách prefix rồi parse.
5. **Nhầm cú pháp literal với parser runtime.** `0b1010`, `1_000` có thể hợp lệ trong Java source, không tự hợp lệ trong chuỗi parse.
6. **Dùng `Integer.toString(-1,16)` để xuất mẫu bit.** Nó cho `-1`; dùng `toHexString`/`toUnsignedString` để hiển thị bit không dấu.
7. **So hai uint32 lưu trong int bằng `>`/ `<`.** Khi bit dấu bật, quan hệ signed khác unsigned; dùng `compareUnsigned`.
8. **Chia uint64 bằng toán tử `/` trên long.** Khi giá trị bit pattern có dấu âm, kết quả signed không phù hợp; dùng `Long.divideUnsigned`.
9. **Chuyển uint64 sang BigInteger bằng `BigInteger.valueOf(bits)` khi bits âm.** Điều đó tạo BigInteger âm; muốn unsigned dương dùng `new BigInteger(Long.toUnsignedString(bits))` hoặc xây từ bytes có signum dương.
10. **Dùng `intValueExact`/ `longValueExact` để lấy bit pattern của uint64 lớn.** Chúng từ chối giá trị vượt miền signed, dù có thể hợp lệ theo unsigned. Kiểm tra miền unsigned trước rồi chỉ lấy 64 bit thấp theo hợp đồng.
11. **Quên leading zeros.** Parser không tự giữ số chữ số ban đầu; format fixed-width nếu giao thức cần.
12. **Nhầm chữ hoa/thường của hex với khác giá trị.** Parser radix 16 nhận cả A–F/a–f, nhưng output canonical có thể chỉ chữ thường.
13. **Tưởng xử lý unsigned tự xử lý byte order.** Không; endian được quyết định trong bước ghép/đọc byte.
14. **Mặc định parse thành công nghĩa là chuẩn hóa input đã đúng.** Có thể cần kiểm ASCII, prefix, dấu, khoảng trắng, độ rộng và format cố định.
15. **Dùng phép cộng primitive như thể tự báo overflow unsigned.** Nó có thể wrap; nếu không được phép wrap thì so phạm vi bằng kiểu rộng hơn/`BigInteger`.
16. **Dùng `%b` của `String.format` để xuất nhị phân.** `%b` thuộc boolean formatting; dùng `Integer.toBinaryString`.
17. **Quên ranh giới giữa mã hóa bit và giá trị toán học.** Cùng `-1` có thể có ý nghĩa khác nhau theo độ rộng và signedness; hãy nêu chúng trong API.

## 12. Câu hỏi luyện tập có đáp án

**Câu 1.** Giá trị của `Integer.parseInt("101101",2)` là bao nhiêu?

**Đáp án:** 45, vì `32+8+4+1=45`.

**Câu 2.** `Integer.parseInt("FF",16)` và `Integer.parseUnsignedInt("FF",16)` có khác nhau không?

**Đáp án:** Không, cùng trả int 255. Khác biệt xuất hiện với giá trị có bit dấu bật hoặc vượt phạm vi int signed; ví dụ `FFFFFFFF`.

**Câu 3.** Tại sao `Integer.parseUnsignedInt("FFFFFFFF",16)` trả `-1`?

**Đáp án:** Phương thức giữ mẫu 32 bit toàn `1` trong một `int` có dấu; cùng bit đó diễn giải signed là -1, unsigned là 4294967295.

**Câu 4.** Muốn lấy giá trị uint32 dương từ `int raw = -1;` thì dùng gì?

**Đáp án:** `long u = Integer.toUnsignedLong(raw);` cho `4294967295L`.

**Câu 5.** Muốn giữ nguyên giá trị dương của unsigned long lớn nhất dưới dạng số học, dùng kiểu nào?

**Đáp án:** `BigInteger`, ví dụ `new BigInteger("18446744073709551615")`. `Long.parseUnsignedLong` chỉ giữ mẫu 64 bit trong `long` (signed view là -1).

**Câu 6.** Vì sao `Integer.toString(-1,16)` khác `Integer.toHexString(-1)`?

**Đáp án:** Hàm đầu biểu diễn **số signed -1** là `"-1"`; hàm thứ hai biểu diễn **mẫu 32-bit không dấu** là `"ffffffff"`.

**Câu 7.** Có nên dùng `Integer.decode("010")` để đọc chuỗi decimal `010` từ người dùng?

**Đáp án:** Không nếu contract yêu cầu decimal; `decode("010")` hiểu octal và cho 8. Dùng `parseInt("010",10)` để có 10.

**Câu 8.** Một protocol cần đúng bốn chữ số hex uppercase cho một trường 16 bit có giá trị 10. Đầu ra chuẩn là gì?

**Đáp án:** `000A`. `Integer.toHexString(10)` chỉ cho `"a"`; dùng định dạng có padding và uppercase.

**Câu 9.** `Long.compareUnsigned(-1L,1L) > 0` đúng hay sai?

**Đáp án:** Đúng, vì `-1L` có 64 bit toàn `1`, được hiểu là `2^64-1` trong so sánh unsigned.

**Câu 10.** Trong tệp, byte `0xFF` đọc thành `byte -1`. Làm thế nào để tính số lượng 255?

**Đáp án:** `Byte.toUnsignedInt(raw)` hoặc `raw & 0xFF` cho int 255.

## 13. Tài liệu chính thức

- [`Integer` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `parseInt`, `parseUnsignedInt`, `toUnsignedString`, `toUnsignedLong`, `compareUnsigned`, `divideUnsigned` và `decode`.
- [`Long` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): `parseUnsignedLong`, `toUnsignedString`, `compareUnsigned`, `divideUnsigned`.
- [`BigInteger` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): parse/format đa cơ số và tính toán số nguyên lớn.
- [`Byte` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html): `toUnsignedInt` và diễn giải byte không dấu.
- [`DataInputStream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readUnsignedByte`, `readUnsignedShort`.

**Ghi nhớ:** Chọn rõ **radix để parse/format**, **độ rộng bit**, **signed hay unsigned** và **quy tắc output**. Với unsigned 32-bit, dùng `int` làm mẫu bit và `Integer.toUnsignedLong` khi cần số dương; với unsigned 64-bit, dùng `long` giữ bit và `BigInteger` khi cần giá trị toán học dương lớn hơn `Long.MAX_VALUE`. Chú ý prefix, leading zeros, endian và lỗi vượt phạm vi khi đọc từ bên ngoài.
