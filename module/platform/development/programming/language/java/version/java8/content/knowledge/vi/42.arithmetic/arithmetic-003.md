# Java 8: parseUnsignedInt, parseUnsignedLong và toUnsignedString

## 1. Mục tiêu và vấn đề cần giải quyết

Java có các kiểu nguyên thủy `byte`, `short`, `int` và `long` mang **dấu**; Java 8 không cung cấp một kiểu primitive `uint`/`ulong` độc lập. Tuy vậy, nhiều định dạng tệp, giao thức mạng, bộ đếm, identifier hoặc giá trị bit-level cần hiểu **cùng một mẫu bit** theo nghĩa **không dấu** (*unsigned*). Từ Java 8, các lớp `Integer` và `Long` có nhóm phương thức xử lý cách hiểu không dấu này.

Ba tên trong chủ đề:

- **`Integer.parseUnsignedInt(String)`** và overload có `radix`: đọc một chuỗi số không dấu nằm trong miền **0 đến 2³² − 1**, trả về **`int` 32-bit** chứa các bit tương ứng.
- **`Long.parseUnsignedLong(String)`** và overload có `radix`: đọc một chuỗi không dấu nằm trong miền **0 đến 2⁶⁴ − 1**, trả về **`long` 64-bit** chứa các bit tương ứng.
- **`Integer.toUnsignedString(int)` / `Long.toUnsignedString(long)`**, cùng overload `radix`: diễn giải các bit của `int`/`long` theo nghĩa không dấu rồi xuất chuỗi số tương ứng.

Điểm quyết định: **parseUnsigned không tạo ra kiểu dữ liệu unsigned mới**. Nó đặt mẫu bit của số không dấu vào một biến `int`/`long` có dấu. Nếu bit cao nhất bằng 1, khi in trực tiếp bằng `System.out.println(value)`, biến ấy có thể trông **âm**. `toUnsignedString` diễn giải lại đúng mẫu bit và xuất giá trị không dấu dự kiến.

Ví dụ nhanh:

```java
int bits32 = Integer.parseUnsignedInt("4294967295");
System.out.println(bits32);                         // -1
System.out.println(Integer.toUnsignedString(bits32)); // 4294967295

long bits64 = Long.parseUnsignedLong("18446744073709551615");
System.out.println(bits64);                       // -1
System.out.println(Long.toUnsignedString(bits64)); // 18446744073709551615
```

Đây là snippet trong method với API `java.lang` (không cần import riêng). Hai biến chứa **32 bit toàn 1** và **64 bit toàn 1**; dấu âm chỉ là cách `int`/`long` thông thường diễn giải bit cao nhất.

**Ứng dụng thực tế:** đọc unsigned fields từ binary protocol, tạo/đọc các ID 32/64-bit, hiển thị checksum hoặc mask, chuyển đổi chuỗi hex/decimal, làm việc với dữ liệu từ hệ thống có kiểu uint32/uint64. Các API này có từ Java 8, vẫn được hỗ trợ trên JDK hiện đại — phù hợp yêu cầu không đưa kiến thức legacy đã lỗi thời vào bài.

## 2. Hai cách hiểu cùng một mẫu bit

Ví dụ 32 bit đều bằng 1:

```text
Bit pattern: 11111111111111111111111111111111
            |                              |
            bit cao nhất = 1             bit thấp nhất = 1

Giải thích int có dấu (two's complement): -1
Giải thích uint32 không dấu:           4,294,967,295 = 2^32 - 1
```

Đối với 64 bit, trường hợp tương tự: mẫu 64 bit toàn 1 được `long` có dấu hiểu là `-1L`, còn khi hiểu không dấu là `18,446,744,073,709,551,615 = 2⁶⁴ − 1`.

| Bề rộng | Kiểu Java lưu bit | Miền signed của kiểu | Miền unsigned cần biểu diễn |
| --- | --- | --- | --- |
| 32 bit | `int` | `-2,147,483,648` đến `2,147,483,647` | `0` đến `4,294,967,295` |
| 64 bit | `long` | `-9,223,372,036,854,775,808` đến `9,223,372,036,854,775,807` | `0` đến `18,446,744,073,709,551,615` |

Với `int`, một giá trị không dấu từ `0` đến `2³¹ − 1` vẫn là số không âm khi đọc như signed. Từ `2³¹` trở lên, cùng mẫu bit được Java hiển thị bằng số âm. Tương tự cho `long` từ `2⁶³` trở lên.

Ví dụ hai ngưỡng đầu tiên có bit dấu bằng 1:

```java
int i = Integer.parseUnsignedInt("2147483648");
long l = Long.parseUnsignedLong("9223372036854775808");

System.out.println(i);                      // -2147483648
System.out.println(l);                      // -9223372036854775808
System.out.println(Integer.toUnsignedString(i)); // 2147483648
System.out.println(Long.toUnsignedString(l));    // 9223372036854775808
```

**Không nên** coi `i < 0` hoặc `l < 0` là bằng chứng dữ liệu đầu vào âm và sai hợp đồng. Đó có thể là một unsigned value hoàn toàn hợp lệ ở nửa trên miền. Muốn xem nó dưới dạng không dấu thì cần dùng đúng API.

### 2.1. Cách biểu diễn không đồng nghĩa phép toán luôn không dấu

Phép `Integer.toUnsignedString(bits)` chỉ **format**; nó không đổi kiểu của biến `bits`. Sau khi parse, toán tử thông thường `<`, `>`, `/`, `%` vẫn tuân theo nghĩa **signed** của `int`/`long`. Nếu cần **so sánh**, **chia** hoặc **chia lấy dư** theo unsigned, dùng các API riêng như `compareUnsigned`, `divideUnsigned` và `remainderUnsigned`.

## 3. `Integer.parseUnsignedInt`: đọc uint32 từ chuỗi

Các chữ ký trong Java 8:

```java
public static int parseUnsignedInt(String s)
    throws NumberFormatException;

public static int parseUnsignedInt(String s, int radix)
    throws NumberFormatException;
```

Chữ ký thứ nhất hiểu `s` là số **thập phân**; chữ ký thứ hai dùng cơ số `radix` do caller chỉ định. Cơ số hợp lệ là **2 đến 36** (`Character.MIN_RADIX` tới `Character.MAX_RADIX`).

```java
int small = Integer.parseUnsignedInt("255");          // 255
int max = Integer.parseUnsignedInt("4294967295");     // bit-pattern -1
int maxHex = Integer.parseUnsignedInt("ffffffff", 16); // bit-pattern -1
int binary = Integer.parseUnsignedInt("11111111", 2); // 255
int octal = Integer.parseUnsignedInt("377", 8);       // 255

boolean sameBits = (max == maxHex);                   // true
```

`parseUnsignedInt` kiểm tra **miền unsigned**, không phải miền signed. Vì vậy chuỗi `"2147483648"` và `"4294967295"` **hợp lệ**, dù `Integer.parseInt` thông thường sẽ không chấp nhận chúng ở cơ số 10. Giá trị cao nhất hợp lệ chính xác là `2³² − 1`; `"4294967296"` bị từ chối.

### 3.1. Return type vẫn là `int`

```java
int maxUnsigned = Integer.parseUnsignedInt("4294967295");
System.out.println(maxUnsigned);  // -1
```

Đây là kết quả **đúng**, không phải phép parse bị lỗi hoặc bị mất 32 bit. `-1` có mẫu bit `0xffffffff`; nếu mong in lại `4294967295`, dùng:

```java
System.out.println(Integer.toUnsignedString(maxUnsigned));
// 4294967295
```

Nếu nghiệp vụ cần một **giá trị số không dấu dương để tính toán** mà không muốn dùng signed reinterpretation, có thể **mở rộng uint32 sang `long`** bằng `Integer.toUnsignedLong` (xem mục 8). Với uint64 thì không có kiểu primitive rộng hơn 64 bit trong Java 8; dùng `BigInteger` khi cần miền số học thông thường không dấu vượt `Long.MAX_VALUE`.

### 3.2. Dấu `+` được chấp nhận, dấu `-` bị từ chối

Theo contract, các chữ số được đánh giá bằng `Character.digit(char, radix)`; ở đầu chuỗi, **ASCII `+`** có thể xuất hiện nếu phía sau còn chữ số. **ASCII `-` không hợp lệ**, ngay cả với `"-0"` hoặc `"-1"`.

```java
Integer.parseUnsignedInt("+42");  // 42
// Integer.parseUnsignedInt("-1"); // NumberFormatException
// Integer.parseUnsignedInt("+");  // NumberFormatException
```

Điều này không mâu thuẫn với `Integer.toUnsignedString(-1)`: formatter được phép nhận `-1` như một **mẫu bit 32-bit**; parser lại chỉ chấp nhận **chuỗi biểu diễn một số không âm** trong miền uint32.

### 3.3. Bị từ chối khi tràn miền

```java
try {
    Integer.parseUnsignedInt("4294967296"); // 2^32
} catch (NumberFormatException expected) {
    // 2^32 nằm ngoài [0, 2^32 - 1].
}
```

Không có wrap-around im lặng trong `parseUnsignedInt` khi input thập phân vượt miền. Nếu bạn muốn cắt xuống 32 bit theo một giao thức có chủ đích, đó là **quy tắc chuyển đổi khác**; không dựa vào parse để tự bỏ bit cao.

## 4. `Long.parseUnsignedLong`: đọc uint64

Tương tự, Java 8 cung cấp:

```java
public static long parseUnsignedLong(String s)
    throws NumberFormatException;

public static long parseUnsignedLong(String s, int radix)
    throws NumberFormatException;
```

Khác với `Long.parseLong` chỉ hỗ trợ số signed tới `9,223,372,036,854,775,807`, bản unsigned nhận tới `18,446,744,073,709,551,615`. Kết quả được trả trong **`long` 64-bit**, không có kiểu primitive `ulong`.

```java
long max = Long.parseUnsignedLong("18446744073709551615");
long maxHex = Long.parseUnsignedLong("ffffffffffffffff", 16);
long boundary = Long.parseUnsignedLong("9223372036854775808");

System.out.println(max);                        // -1
System.out.println(max == maxHex);              // true
System.out.println(boundary);                   // -9223372036854775808
System.out.println(Long.toUnsignedString(max)); // 18446744073709551615
```

Giá trị lớn hơn một đơn vị:

```java
// Long.parseUnsignedLong("18446744073709551616");
// NumberFormatException: vượt giới hạn 2^64 - 1.
```

Đây là điểm rất quan trọng với mã định danh 64-bit từ hệ thống khác: đọc nó bằng `Long.parseLong` có thể thất bại dù đó là **uint64 hợp lệ**; đọc bằng `Long.parseUnsignedLong` rồi in trực tiếp kiểu signed có thể thấy số âm. Phải xác định **hợp đồng biểu diễn** trước khi đưa sang UI, JSON, database hoặc hệ thống khác.

### 4.1. Số không dấu không đồng nghĩa lưu được mọi giá trị như số dương trong `long`

```java
long bits = Long.parseUnsignedLong("18446744073709551615");
boolean signedNegative = bits < 0; // true

String safeDecimal = Long.toUnsignedString(bits);
// "18446744073709551615"
```

Nếu cần giữ giá trị này theo **ngữ nghĩa số nguyên toán học dương**, `BigInteger` phù hợp hơn:

```java
BigInteger mathematicalValue =
    new BigInteger(Long.toUnsignedString(bits));
// 18446744073709551615
```

Đây là snippet cần `import java.math.BigInteger;`. Không dùng `BigInteger.valueOf(bits)` với `bits == -1L` nếu muốn uint64: kết quả sẽ là **BigInteger -1** theo signed `long`, không phải `2⁶⁴ − 1`.

## 5. `toUnsignedString`: định dạng mẫu bit thành chuỗi unsigned

Bốn chữ ký trọng tâm (Java 8):

```java
public static String Integer.toUnsignedString(int i);
public static String Integer.toUnsignedString(int i, int radix);

public static String Long.toUnsignedString(long i);
public static String Long.toUnsignedString(long i, int radix);
```

Các dòng trên là **cách trình bày static API theo tên lớp**, không phải khai báo method thực sự đặt bên trong một class Java tự viết. Cả bốn nhận các bit của `int`/`long` và xuất chuỗi biểu diễn **không dấu** với cơ số yêu cầu. Không có dấu âm ở đầu.

```java
System.out.println(Integer.toUnsignedString(-1));       // 4294967295
System.out.println(Integer.toUnsignedString(-1, 16));   // ffffffff
System.out.println(Long.toUnsignedString(-1L));         // 18446744073709551615
System.out.println(Long.toUnsignedString(-1L, 16));     // ffffffffffffffff
```

Điều này khác `Integer.toString(-1)` và `Long.toString(-1L)`, vốn trả `"-1"` theo nghĩa signed.

### 5.1. Nếu không chỉ định radix, dùng cơ số 10

`Integer.toUnsignedString(i)` và `Long.toUnsignedString(l)` trả chuỗi thập phân. Khi truyền `radix`, dùng cơ số tương ứng:

```java
int value = 255;

Integer.toUnsignedString(value);     // "255"
Integer.toUnsignedString(value, 2);  // "11111111"
Integer.toUnsignedString(value, 8);  // "377"
Integer.toUnsignedString(value, 16); // "ff"
```

Với `radix = 16`, chữ cái thường là `a`–`f`. Đừng cho rằng kết quả được in hoa; nếu giao thức yêu cầu chữ hoa, chuẩn hóa riêng bằng `toUpperCase(Locale.ROOT)` hoặc định dạng cụ thể có kiểm thử.

### 5.2. Formatter không tự thêm leading zeros

`toUnsignedString` tạo biểu diễn **ngắn gọn**: không tự thêm đủ 8 ký tự hex cho uint32 hay 16 ký tự hex cho uint64.

```java
Integer.toUnsignedString(15, 16); // "f", không phải "0000000f"
Long.toUnsignedString(15L, 2);    // "1111", không phải chuỗi 64 bit
Integer.toUnsignedString(0, 2);   // "0"
```

Nếu một binary protocol hoặc report yêu cầu đủ **32/64 bit**, hãy padding đầu chuỗi theo **độ rộng và cơ số**. Ví dụ với số thập lục phân (độ rộng 8/16 ký tự):

```java
String hex32 = String.format("%08x", -1);   // "ffffffff"
String hex64 = String.format("%016x", -1L); // "ffffffffffffffff"
```

Đây là snippet dùng formatting của Java và nên kiểm thử với locale/quy tắc giao thức. Nếu chỉ muốn text uint32/uint64 dễ đọc, `toUnsignedString` rõ ý định và không thêm số 0 đầu.

### 5.3. Lưu ý radix không hợp lệ của formatter

Theo API, `toUnsignedString(value, radix)` sử dụng cơ số **10** khi tham số radix nhỏ hơn 2 hoặc lớn hơn 36. Điều này **khác** `parseUnsigned...(text,radix)`: parser ném `NumberFormatException` nếu radix không hợp lệ.

Đừng dựa vào fallback âm thầm của formatter để chấp nhận cấu hình cơ số sai. Ở boundary nhận dữ liệu, validate `radix` chủ động để mọi bước parse/format nhất quán.

## 6. Radix: các cơ số 2–36 và cách parse đúng

`radix` là cơ số của chuỗi, không phải “số bit” hay tùy chọn unsigned riêng. Một số ví dụ:

| Văn bản | Radix | Giá trị toán học | Lời gọi |
| --- | --- | --- | --- |
| `"255"` | 10 | 255 | `parseUnsignedInt("255")` |
| `"11111111"` | 2 | 255 | `parseUnsignedInt("11111111",2)` |
| `"377"` | 8 | 255 | `parseUnsignedInt("377",8)` |
| `"ff"` | 16 | 255 | `parseUnsignedInt("ff",16)` |
| `"FF"` | 16 | 255 | `parseUnsignedInt("FF",16)` |
| `"z"` | 36 | 35 | `parseUnsignedInt("z",36)` |
| `"ffffffff"` | 16 | 2³² − 1 | `parseUnsignedInt("ffffffff",16)` |
| `"ffffffffffffffff"` | 16 | 2⁶⁴ − 1 | `parseUnsignedLong("ffffffffffffffff",16)` |

Các chữ số tương ứng được nhận diện theo `Character.digit(c,radix)`; các chữ Latin có thể dùng chữ hoa/chữ thường cho cơ số trên 10. **Cơ số và miền số** đều được kiểm tra ở parse.

### 6.1. Không tự nhận tiền tố `0x`, `0b`, dấu `#`

Phương thức `parseUnsignedInt(s,16)` cần **chuỗi chữ số hex**, không tự cắt `"0x"`. Tương tự, không đưa `"0b1010"` trực tiếp vào parse radix 2 hoặc chuỗi `"#ff"` vào parse radix 16.

```java
Integer.parseUnsignedInt("ff", 16);    // 255
// Integer.parseUnsignedInt("0xff", 16); // NumberFormatException
// Integer.parseUnsignedInt("0b1010", 2); // NumberFormatException
```

Nếu giao thức của bạn **cho phép prefix**, chuẩn hóa **ở lớp nhận input** sau khi validate rõ format, rồi gọi parser với cơ số đã chọn. Không vô tình cho phép mọi kiểu prefix hoặc cắt bừa hai ký tự đầu.

### 6.2. Số 0 đầu không tự chọn bát phân

`Integer.parseUnsignedInt("010")` dùng radix 10 mặc định, nên trả **10**, không phải 8. Trong Java source, một literal số nguyên bắt đầu bằng 0 có thể có quy tắc octal riêng; nhưng **chuỗi parseUnsigned không phải source-code literal parser**.

```java
Integer.parseUnsignedInt("010");    // 10
Integer.parseUnsignedInt("010", 8); // 8
```

### 6.3. Dấu gạch dưới trong source literal không phải ký tự hợp lệ khi parse

Trong source Java, literal `1_000` được compiler chấp nhận như số 1000. Nhưng chuỗi `"1_000"` đưa vào `parseUnsignedInt` **không phải** định dạng số mặc định hợp lệ; nó ném `NumberFormatException`.

Nếu input cho phép separator, hãy đưa quy tắc loại bỏ separator vào validation riêng, tránh thay thế không kiểm soát khiến input sai vô tình trở thành hợp lệ.

## 7. Dấu, khoảng trắng, giới hạn và `NumberFormatException`

`parseUnsignedInt`/`parseUnsignedLong` ném **`NumberFormatException`** (unchecked, kế thừa `IllegalArgumentException`) khi chuỗi không biểu diễn được số unsigned hợp lệ trong radix yêu cầu.

Những lỗi tiêu biểu:

| Input | Parser | Kết quả |
| --- | --- | --- |
| `"4294967295"` | `Integer.parseUnsignedInt` | Hợp lệ, bit-pattern `-1` |
| `"4294967296"` | `Integer.parseUnsignedInt` | `NumberFormatException`: vượt uint32 |
| `"18446744073709551615"` | `Long.parseUnsignedLong` | Hợp lệ, bit-pattern `-1L` |
| `"18446744073709551616"` | `Long.parseUnsignedLong` | `NumberFormatException`: vượt uint64 |
| `"-1"` | Cả hai | `NumberFormatException`: âm không hợp lệ |
| `"+42"` | Cả hai | Hợp lệ, kết quả 42 |
| `"+"` | Cả hai | `NumberFormatException`: thiếu chữ số |
| `""` | Cả hai | `NumberFormatException` |
| `null` với overload String | Cả hai | `NumberFormatException` theo contract |
| `" 42 "` | Cả hai | `NumberFormatException` nếu không normalize |
| `"0xFF"` với radix 16 | Cả hai | `NumberFormatException`: prefix không được nhận |
| `"1_000"` với radix 10 | Cả hai | `NumberFormatException` |
| `"10"` với radix 1 | Cả hai | `NumberFormatException`: radix ngoài [2,36] |

### 7.1. Chuẩn hóa whitespace phải có chủ đích

`parseUnsignedInt(" 42 ")` không tự trim; nếu format của input cho phép khoảng trắng đầu/cuối, có thể dùng `trim()` trước khi parse:

```java
String input = " 42 ";
int value = Integer.parseUnsignedInt(input.trim()); // 42
```

`String.trim()` có từ Java 8. `String.strip()` được thêm trong Java 11 nên **không dùng trong code yêu cầu Java 8**. Không tự trim nếu input là một trường giao thức yêu cầu byte-for-byte canonical format: khoảng trắng có thể là lỗi cần được báo.

### 7.2. Dấu `+` có thể hợp lệ về cú pháp nhưng không hợp lệ theo domain

API cho phép `"+42"`, song một giao thức API có thể yêu cầu chuỗi canonical `"42"`, không có `+`, không có leading zeros, chỉ ASCII digits. Khi đó cần **domain validation** trước parse:

```java
static int parseCanonicalUint32(String s) {
    if (s == null || !s.matches("0|[1-9][0-9]*")) {
        throw new IllegalArgumentException("uint32 text is not canonical");
    }
    return Integer.parseUnsignedInt(s);
}
```

Đây là **method snippet Java 8**. Regex này cố ý chỉ nhận **ASCII decimal** và cấm số 0 đầu/dấu `+`; đó là **quy tắc ứng dụng**, không phải ràng buộc của `Integer.parseUnsignedInt`. Parser sau đó vẫn kiểm tra **range 32-bit**. Với dữ liệu từ người dùng không đáng tin, cũng nên giới hạn độ dài chuỗi trước khi validate để tránh đầu vào quá lớn.

### 7.3. Không dựa vào message của exception

Hãy catch theo **loại lỗi**, hoặc trả lỗi domain như `INVALID_UNSIGNED_INT`, `OUT_OF_RANGE` theo chính sách validate riêng. Không assert chính xác `NumberFormatException.getMessage()` trong unit test vì wording có thể thay đổi giữa các phiên bản JDK.

```java
try {
    int value = Integer.parseUnsignedInt(untrustedText);
    consumeUnsignedBits(value);
} catch (NumberFormatException error) {
    reportInvalidUnsignedInput();
}
```

Đây là snippet kiến trúc; `untrustedText`, `consumeUnsignedBits` và `reportInvalidUnsignedInput` do ứng dụng định nghĩa. Không in raw input chứa dữ liệu nhạy cảm lên log chỉ vì parse thất bại.

## 8. Từ uint32 bits sang `long` dương: `Integer.toUnsignedLong`

Với 32 bit, Java 8 có một cách **chuyển thành giá trị toán học dương** mà vẫn chỉ dùng kiểu primitive: `Integer.toUnsignedLong(int)`.

```java
int bits = Integer.parseUnsignedInt("4294967295");
long unsignedValue = Integer.toUnsignedLong(bits);

System.out.println(bits);          // -1
System.out.println(unsignedValue); // 4294967295
```

Vì miền uint32 tối đa `2³² − 1` **nhỏ hơn** `Long.MAX_VALUE`, mọi uint32 có thể được giữ dưới dạng `long` dương chính xác.

Tương đương về bit:

```java
long unsignedValue = bits & 0xffff_ffffL;
```

`0xffff_ffffL` là **literal 64-bit kiểu long**, vì vậy phép AND giữ 32 bit thấp và cho kết quả dương. Tuy nhiên, `Integer.toUnsignedLong(bits)` rõ ngữ nghĩa và dễ đọc hơn khi mục tiêu đúng là chuyển uint32 sang long.

### 8.1. Tránh cast có dấu

```java
int bits = Integer.parseUnsignedInt("4294967295");

long signedWidening = (long) bits;           // -1
long unsignedWidening = Integer.toUnsignedLong(bits); // 4294967295
```

Cast `(long) bits` thực hiện **sign extension** từ `int` sang `long`, nên tạo số âm. `Integer.toUnsignedLong` thực hiện mở rộng theo cách hiểu không dấu. Đây là bẫy phổ biến khi đọc trường uint32 rồi cộng/trừ với một `long` khác.

### 8.2. Khi tính toán uint32 có thể vượt 32 bit

Ví dụ cộng hai uint32 lớn nhất cần miền tới gần `2³³`, nên dùng `long`:

```java
int aBits = Integer.parseUnsignedInt("4294967295");
int bBits = Integer.parseUnsignedInt("4294967295");

long sum = Integer.toUnsignedLong(aBits)
    + Integer.toUnsignedLong(bBits);
// sum = 8589934590
```

Dùng `int sumBits = aBits + bBits;` sẽ giữ **32 bit thấp** sau overflow theo ngữ nghĩa Java; có thể đúng cho một số thuật toán **modulo 2³²**, nhưng **không** phải phép cộng toán học với kết quả không giới hạn.

## 9. Uint64 muốn có số dương thực: `BigInteger`

Với uint64, **không có primitive Java 8 nào biểu diễn dương hết miền 0…2⁶⁴ − 1**. Nếu cần số học toán học dương, lựa chọn chuẩn là `java.math.BigInteger`.

### 9.1. Từ một `long` chứa unsigned bits sang BigInteger

```java
long bits = Long.parseUnsignedLong("18446744073709551615");

BigInteger exact = new BigInteger(Long.toUnsignedString(bits));
BigInteger max = BigInteger.ONE.shiftLeft(64)
    .subtract(BigInteger.ONE);

boolean equal = exact.equals(max); // true
```

`Long.toUnsignedString` xuất **chuỗi decimal không dấu**; `new BigInteger(text)` nhận chuỗi decimal đó và có thể giữ số dương vượt `Long.MAX_VALUE`.

**Đừng viết:**

```java
long bits = -1L;
BigInteger wrong = BigInteger.valueOf(bits);
// wrong là -1, KHÔNG phải 18446744073709551615.
```

### 9.2. Đổi BigInteger trong miền uint64 thành long bits

Khi một BigInteger hợp lệ ở miền `[0, 2⁶⁴−1]` cần đóng gói thành bit-pattern long:

```java
static long toUnsignedLongBits(BigInteger value) {
    if (value == null || value.signum() < 0 || value.bitLength() > 64) {
        throw new IllegalArgumentException("Outside uint64 range");
    }
    return value.longValue();
}
```

Đây là **method snippet** cần `BigInteger`. Kiểm tra `signum` và `bitLength` bảo đảm giá trị thuộc miền; `longValue()` sau đó cố ý giữ **64 bit thấp**, kể cả khi kết quả signed là âm. **Không** gọi `longValueExact()` cho các uint64 lớn hơn `Long.MAX_VALUE`: method đó kiểm tra miền **signed long**, nên có thể ném `ArithmeticException` cho một uint64 hợp lệ.

### 9.3. BigInteger không tự giới hạn uint64

`new BigInteger("18446744073709551616")` vẫn là BigInteger hợp lệ, vì kiểu này hỗ trợ độ lớn tùy ý. Nếu cần miền uint64, phải **tự validate** `signum/bitLength` hoặc dùng `Long.parseUnsignedLong` để bắt overflow ngay từ chuỗi.

BigInteger phù hợp khi: cần cộng/trừ/nhân/chia dương vượt signed range, lưu giá trị thập phân lớn hoặc kiểm tra giới hạn của một payload. Nếu chỉ truyền lại một ID uint64 **nguyên bit**, lưu `long` bits và format bằng `Long.toUnsignedString` thường gọn và ít cấp phát hơn.

## 10. So sánh không dấu: `compareUnsigned`

Sau khi parse, cú pháp toán tử so sánh Java vẫn dùng **signed interpretation**:

```java
int maxBits = Integer.parseUnsignedInt("4294967295");
boolean signedLess = maxBits < 1; // true vì maxBits == -1

boolean unsignedGreater =
    Integer.compareUnsigned(maxBits, 1) > 0; // true
```

Một uint32 `4,294,967,295` rõ ràng **lớn hơn 1** theo toán học; `Integer.compareUnsigned` mới trả kết quả phù hợp miền không dấu. `Long.compareUnsigned` làm điều tương tự cho uint64:

```java
long maxBits = Long.parseUnsignedLong("18446744073709551615");
boolean largerUnsigned =
    Long.compareUnsigned(maxBits, 1L) > 0; // true
```

Cả hai phương thức có từ Java 8. Những lỗi dễ gặp:

- Sắp xếp `List<Integer>` chứa uint32 bits bằng `Comparator.naturalOrder()` sẽ dùng signed order, đưa những giá trị có bit dấu 1 về phía trước giá trị dương.
- Dùng `Math.max`/`Math.min` trên hai `long` unsigned bits có thể trả sai kết quả theo miền uint64.
- Dùng điều kiện `if (bits < 0) throw...` sẽ loại bỏ một nửa miền unsigned hợp lệ.
- Tham chiếu `Integer::compareUnsigned`/`Long::compareUnsigned` phù hợp khi sắp thứ tự các bit-pattern theo unsigned.

Ví dụ sắp xếp:

```java
List<Integer> values = Arrays.asList(1, -1, 0);
values.sort(Integer::compareUnsigned);
// Theo unsigned: [0, 1, -1]
// vì -1 có nghĩa 4294967295 ở phép so sánh này.
```

Đây là snippet cần `Arrays`, `List`; danh sách vẫn chứa `int` có dấu, chỉ **comparator** được đổi.

## 11. Chia và lấy dư không dấu

Java 8 còn có:

- `Integer.divideUnsigned(int dividend, int divisor)`
- `Integer.remainderUnsigned(int dividend, int divisor)`
- `Long.divideUnsigned(long dividend, long divisor)`
- `Long.remainderUnsigned(long dividend, long divisor)`

Không dùng toán tử `/` hay `%` mặc định nếu phép toán phải hiểu hai operand theo unsigned và ít nhất một operand có bit dấu bằng 1.

```java
long unsignedMaxBits = Long.parseUnsignedLong("18446744073709551615");

long quotient = Long.divideUnsigned(unsignedMaxBits, 10L);
long remainder = Long.remainderUnsigned(unsignedMaxBits, 10L);

System.out.println(Long.toUnsignedString(quotient));
// 1844674407370955161
System.out.println(Long.toUnsignedString(remainder));
// 5
```

Nếu divisor bằng 0 thì vẫn có `ArithmeticException` như quy tắc chia số nguyên. Nếu quotient mang bit dấu 1, format bằng `toUnsignedString` để xem kết quả đúng theo miền không dấu.

### 11.1. Modulo và tràn số

Phép cộng, trừ và nhân trên `int`/`long` trong Java giữ các bit thấp theo modulo `2³²`/`2⁶⁴` ở mức bit-pattern (không phải cảnh báo overflow). Trong thuật toán hashing, checksum hoặc bộ đếm modulo đây có thể là mục tiêu. Nhưng nếu yêu cầu **không được tràn** theo số học toán học, phải kiểm tra overflow và/hoặc dùng `long`/`BigInteger` tương ứng.

`Math.addExact`/`multiplyExact` kiểm tra overflow trong **miền signed**, không phải bộ kiểm tra uint32/uint64 overflow. Đừng dùng chúng làm validator unsigned khi chưa phân tích biên và miền.

### 11.2. Dịch bit phải: `>>` so với `>>>`

`>>` dịch phải **giữ dấu**; `>>>` dịch phải và chèn các bit 0 phía trái. Với dữ liệu được hiểu unsigned, `>>>` có thể cần cho thao tác bit-level:

```java
int allOnes = -1;
int signedShift = allOnes >> 1;   // -1
int logicalShift = allOnes >>> 1; // 2147483647
```

Đây không phải phương thức parse/format, nhưng là ví dụ cho việc **các toán tử Java vẫn có ngữ nghĩa riêng** sau khi bạn parse một chuỗi unsigned.

## 12. Round-trip: parse rồi format có mất dữ liệu không?

Một thuộc tính quan trọng là **bảo toàn mẫu bit** khi dùng cùng kiểu và cơ số hợp lệ:

```java
int original32 = Integer.parseUnsignedInt("4294967295");
String encoded32 = Integer.toUnsignedString(original32);
int decoded32 = Integer.parseUnsignedInt(encoded32);
boolean same32 = original32 == decoded32; // true

long original64 = Long.parseUnsignedLong("18446744073709551615");
String encoded64 = Long.toUnsignedString(original64);
long decoded64 = Long.parseUnsignedLong(encoded64);
boolean same64 = original64 == decoded64; // true
```

Việc `original32 == -1` và `original64 == -1L` không làm mất dữ liệu. Tất cả các bit đã được giữ và chuỗi định dạng unsigned có thể tái tạo lại cùng bit-pattern.

### 12.1. Round-trip không bảo toàn nguyên văn input text

`toUnsignedString` tạo biểu diễn **chuẩn hóa tối giản**, nên không lưu lại:

- Dấu `+` ban đầu.
- Leading zeros.
- Chữ hex in hoa.
- Ký tự phân cách tùy biến đã được xử lý ở lớp input.
- Prefix `0x` hay `0b` do ứng dụng đã cắt bỏ.

```java
int bits = Integer.parseUnsignedInt("0000", 16);
String canonical = Integer.toUnsignedString(bits, 16);
// canonical == "0", không phải "0000".
```

Nếu cần bảo tồn chuỗi gốc vì tính pháp lý, chữ ký điện tử hoặc giao thức giao tiếp, phải giữ **text nguyên văn** hoặc canonicalization contract riêng, không chỉ giữ bit-pattern.

### 12.2. Round-trip giữa các radix

```java
long bits = Long.parseUnsignedLong("ffffffffffffffff", 16);
String dec = Long.toUnsignedString(bits, 10);
String bin = Long.toUnsignedString(bits, 2);

System.out.println(dec);          // 18446744073709551615
System.out.println(bin.length()); // 64
```

Cùng một bit-pattern có thể được biểu diễn bằng decimal, hex hoặc binary. Khi parse một chuỗi ở radix 16 rồi xuất ở radix 10, **giá trị toán học unsigned** không đổi.

## 13. Những API tương tự dễ nhầm

| API | Có từ Java 8? | Cách hiểu input/output |
| --- | --- | --- |
| `Integer.parseInt(String)` | Có từ trước | Chuỗi số **signed int** |
| `Integer.parseUnsignedInt(String[,radix])` | Có | Chuỗi uint32 → int bits |
| `Integer.toString(int)` | Có từ trước | int bits được in theo **signed** |
| `Integer.toUnsignedString(int[,radix])` | Có | int bits được in theo **unsigned** |
| `Integer.toUnsignedLong(int)` | Có | uint32 bits → long dương chính xác |
| `Integer.compareUnsigned` | Có | So sánh int bits theo uint32 |
| `Integer.divideUnsigned/remainderUnsigned` | Có | Chia/lấy dư theo uint32 |
| `Long.parseLong(String)` | Có từ trước | Chuỗi số **signed long** |
| `Long.parseUnsignedLong(String[,radix])` | Có | Chuỗi uint64 → long bits |
| `Long.toString(long)` | Có từ trước | long bits được in theo **signed** |
| `Long.toUnsignedString(long[,radix])` | Có | long bits được in theo **unsigned** |
| `Long.compareUnsigned` | Có | So sánh theo uint64 |
| `Long.divideUnsigned/remainderUnsigned` | Có | Chia/lấy dư theo uint64 |
| `Integer.parseUnsignedInt(CharSequence,start,end,radix)` | **Java 9+** | Đọc một đoạn CharSequence, không dùng khi build Java 8 |
| `Long.parseUnsignedLong(CharSequence,start,end,radix)` | **Java 9+** | Tương tự, không dùng khi build Java 8 |

**Special Note:** Các API ở cột Java 8 đều vẫn được duy trì. Hai overload `CharSequence` là API hiện hành **được thêm ở Java 9**, nên chỉ đề cập để người học tránh nhầm khi đọc Javadoc hiện đại; chương trình runnable của bài chỉ dùng API từ Java 8.

### 13.1. `Integer.toHexString` và `Long.toHexString`

Hai hàm này cũng in các bit theo hướng unsigned ở **radix 16**. Trong nhiều trường hợp, `Integer.toHexString(bits)` tương đương `Integer.toUnsignedString(bits,16)` và `Long.toHexString(bits)` tương đương `Long.toUnsignedString(bits,16)` về text.

Chọn `toUnsignedString(bits, radix)` khi muốn một interface tổng quát cho cơ số 2,8,10,16,36; chọn `toHexString` khi ý định luôn chỉ là hex.

### 13.2. `Integer.decode`, `Long.decode` không thay thế `parseUnsigned`

`Integer.decode("0xff")` có thể hỗ trợ prefix theo contract của `decode`, nhưng kết quả vẫn bị giới hạn bởi **miền signed** của `int`. Nó không phải phương thức đọc toàn bộ uint32.

Tương tự `Long.decode` không tự hỗ trợ toàn bộ miền uint64 không dấu. Nếu input có prefix và cần uint64, hãy parse prefix có chủ đích rồi dùng `Long.parseUnsignedLong(digits,radix)`.

## 14. Chương trình Java 8 chạy được: biên, cơ số, lỗi và round-trip

Ví dụ sau chủ động **không dựa vào tài nguyên ngoài, locale, ngày giờ hay thread scheduling**, để toàn bộ stdout ổn định. Nó kiểm thử:

1. Mẫu bit uint32 tối đa và ngưỡng `2³¹`.
2. Mẫu bit uint64 tối đa và ngưỡng `2⁶³`.
3. Chuyển sang decimal, hex, binary, octal.
4. Phân biệt signed/unsigned comparisons.
5. Round-trip parse/format.
6. Chuyển uint32 sang long dương và uint64 sang BigInteger.
7. Chia/lấy dư theo unsigned.
8. Những input không hợp lệ: overflow, dấu âm, prefix hex, underscore, whitespace, ký tự sai cơ số và invalid radix.
9. Chuẩn hóa text hex có leading zeros/chữ hoa/chữ thường.

Tạo file **UnsignedParsingDemo.java**:

```java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.List;

public class UnsignedParsingDemo {
    private static void expectIntError(String input, int radix) {
        try {
            Integer.parseUnsignedInt(input, radix);
            System.out.println("int rejected " + input + ": false");
        } catch (NumberFormatException expected) {
            System.out.println("int rejected " + input + ": true");
        }
    }

    private static void expectLongError(String input, int radix) {
        try {
            Long.parseUnsignedLong(input, radix);
            System.out.println("long rejected " + input + ": false");
        } catch (NumberFormatException expected) {
            System.out.println("long rejected " + input + ": true");
        }
    }

    public static void main(String[] args) {
        int uint32Max = Integer.parseUnsignedInt("4294967295");
        System.out.println("uint32 signed bits: " + uint32Max);
        System.out.println("uint32 decimal: " + Integer.toUnsignedString(uint32Max));
        System.out.println("uint32 as long: " + Integer.toUnsignedLong(uint32Max));
        System.out.println("uint32 hex: " + Integer.toUnsignedString(uint32Max, 16));
        System.out.println("uint32 binary width: " +
            Integer.toUnsignedString(uint32Max, 2).length());

        int uint32Boundary = Integer.parseUnsignedInt("2147483648");
        System.out.println("uint32 boundary signed: " + uint32Boundary);
        System.out.println("uint32 boundary unsigned: " +
            Integer.toUnsignedString(uint32Boundary));
        System.out.println("int plus sign: " +
            Integer.toUnsignedString(Integer.parseUnsignedInt("+42")));
        System.out.println("int hex parse: " +
            Integer.toUnsignedString(Integer.parseUnsignedInt("ff00", 16), 16));
        System.out.println("int octal parse: " +
            Integer.toUnsignedString(Integer.parseUnsignedInt("377", 8)));
        System.out.println("int zero string: " + Integer.toUnsignedString(0, 2));
        System.out.println("int signed vs unsigned comparison: " +
            ((Integer.compare(uint32Max, 1) < 0) &&
             (Integer.compareUnsigned(uint32Max, 1) > 0)));

        long uint64Max = Long.parseUnsignedLong("18446744073709551615");
        System.out.println("uint64 signed bits: " + uint64Max);
        System.out.println("uint64 decimal: " + Long.toUnsignedString(uint64Max));
        System.out.println("uint64 hex: " + Long.toUnsignedString(uint64Max, 16));
        System.out.println("uint64 binary width: " +
            Long.toUnsignedString(uint64Max, 2).length());

        long uint64Boundary = Long.parseUnsignedLong("9223372036854775808");
        System.out.println("uint64 boundary signed: " + uint64Boundary);
        System.out.println("uint64 boundary unsigned: " +
            Long.toUnsignedString(uint64Boundary));
        System.out.println("long plus sign: " +
            Long.toUnsignedString(Long.parseUnsignedLong("+42")));
        System.out.println("long hex parse equals max: " +
            (Long.parseUnsignedLong("ffffffffffffffff", 16) == uint64Max));
        System.out.println("long signed vs unsigned comparison: " +
            ((Long.compare(uint64Max, 1L) < 0) &&
             (Long.compareUnsigned(uint64Max, 1L) > 0)));

        System.out.println("int round trip: " +
            (Integer.parseUnsignedInt(Integer.toUnsignedString(uint32Max))
                == uint32Max));
        System.out.println("long round trip: " +
            (Long.parseUnsignedLong(Long.toUnsignedString(uint64Max))
                == uint64Max));
        System.out.println("long decimal BigInteger: " +
            new BigInteger(Long.toUnsignedString(uint64Max))
                .equals(BigInteger.ONE.shiftLeft(64).subtract(BigInteger.ONE)));

        System.out.println("unsigned quotient of max by 10: " +
            Long.toUnsignedString(Long.divideUnsigned(uint64Max, 10L)));
        System.out.println("unsigned remainder of max by 10: " +
            Long.remainderUnsigned(uint64Max, 10L));

        expectIntError("4294967296", 10);
        expectIntError("-1", 10);
        expectIntError("0xFF", 16);
        expectIntError("1_000", 10);
        expectIntError(" 42 ", 10);
        expectIntError("A", 10);
        expectIntError("10", 1);
        expectLongError("18446744073709551616", 10);
        expectLongError("-1", 10);
        expectLongError("0xFF", 16);

        List<String> hexStrings = Arrays.asList("0000", "7f", "ff", "80000000");
        for (String value : hexStrings) {
            int bits = Integer.parseUnsignedInt(value, 16);
            String encoded = Integer.toUnsignedString(bits, 16);
            System.out.println("hex normalized " + value + ": " + encoded);
        }
    }
}
```

Biên dịch với JDK hiện đại nhưng giới hạn Java 8 APIs:

```bash
javac --release 8 -encoding UTF-8 UnsignedParsingDemo.java
java UnsignedParsingDemo
```

Trên **chính JDK 8**, dùng `javac -encoding UTF-8 UnsignedParsingDemo.java` (cờ `--release` được thêm sau Java 8). **Stdout đúng, đã kiểm thử:**

```text
uint32 signed bits: -1
uint32 decimal: 4294967295
uint32 as long: 4294967295
uint32 hex: ffffffff
uint32 binary width: 32
uint32 boundary signed: -2147483648
uint32 boundary unsigned: 2147483648
int plus sign: 42
int hex parse: ff00
int octal parse: 255
int zero string: 0
int signed vs unsigned comparison: true
uint64 signed bits: -1
uint64 decimal: 18446744073709551615
uint64 hex: ffffffffffffffff
uint64 binary width: 64
uint64 boundary signed: -9223372036854775808
uint64 boundary unsigned: 9223372036854775808
long plus sign: 42
long hex parse equals max: true
long signed vs unsigned comparison: true
int round trip: true
long round trip: true
long decimal BigInteger: true
unsigned quotient of max by 10: 1844674407370955161
unsigned remainder of max by 10: 5
int rejected 4294967296: true
int rejected -1: true
int rejected 0xFF: true
int rejected 1_000: true
int rejected  42 : true
int rejected A: true
int rejected 10: true
long rejected 18446744073709551616: true
long rejected -1: true
long rejected 0xFF: true
hex normalized 0000: 0
hex normalized 7f: 7f
hex normalized ff: ff
hex normalized 80000000: 80000000
```

### 14.1. Giải thích kết quả theo nhóm

- **12 dòng uint32 đầu:** `"4294967295"` là uint32 lớn nhất; `int` lưu tất cả bit 1 nên in signed là `-1`, còn `toUnsignedString`/`toUnsignedLong` đều hiển thị đúng số dương. `2147483648` là ranh giới làm bit dấu = 1; các phép so sánh signed và unsigned đưa kết quả trái ngược khi so với 1.
- **Các dòng uint64:** `"18446744073709551615"` tạo `long` bits `-1L`. Hex 16 chữ `f` và binary dài 64 bit. Ngưỡng `9223372036854775808` in signed thành `Long.MIN_VALUE`.
- **Round-trip:** parse/format không mất bit, dù biến signed có thể âm.
- **BigInteger:** biểu diễn toán học dương của uint64 max bằng `2⁶⁴ − 1`, không nhầm với `BigInteger.valueOf(-1L)`.
- **Chia unsigned:** khi chia uint64 max cho 10, thương là `1844674407370955161` và dư 5. Toán tử `/` thông thường trên `long -1L` sẽ không cho kết quả ấy.
- **Mười dòng input invalid:** parser trả `NumberFormatException`, test kiểm tra **loại exception**, không phụ thuộc message. Dấu `-` không được phép; prefix/underscore/space không được parser tự xử lý.
- **Các dòng canonical hex:** `0000` được format lại thành `0`; những chuỗi còn lại được chuẩn hóa bỏ số 0 không cần thiết. Việc format không giữ nguyên text đầu vào.

### 14.2. Vì sao không test giá trị bit lớn bằng `int` hoặc `long` literal dương?

Java source literal `4294967295` không tự trở thành `int` unsigned; viết thẳng một literal decimal int ngoài signed range có thể không compile. Dùng **chuỗi** với `parseUnsignedInt` hoặc một biểu thức bit-pattern đã biết như `-1`/`0xffff_ffff` khi giao thức cần giữ nguyên bit.

Tương tự, `18446744073709551615L` không phải literal `long` decimal dương hợp lệ. Dùng `Long.parseUnsignedLong("18446744073709551615")`, `-1L` cho all-ones bits, hoặc BigInteger tùy ngữ nghĩa.

## 15. Tích hợp thực tế với file nhị phân, JSON, database và API

### 15.1. ByteBuffer đọc raw 32/64-bit không quyết định sign business

Nếu giao thức nhị phân có trường uint32/uint64, một API như `ByteBuffer.getInt()`/`getLong()` có thể trả `int`/`long` với bit-pattern đúng. Khi chuyển sang decimal text, dùng `Integer.toUnsignedString`/`Long.toUnsignedString`; khi so sánh, dùng `compareUnsigned`.

```java
int rawUint32Bits = buffer.getInt();
String displayed = Integer.toUnsignedString(rawUint32Bits);
long positive32 = Integer.toUnsignedLong(rawUint32Bits);
```

Đây là snippet, cần `ByteBuffer buffer` được ứng dụng cung cấp và import `java.nio.ByteBuffer`. Cần chú ý **byte order** (big-endian/little-endian), offset, bounds và encoding theo đặc tả giao thức; unsigned formatting **không sửa lỗi sai endian**.

### 15.2. JSON number với uint64 có thể mất độ chính xác ở hệ khác

Một backend Java có thể nhận/trả uint64 tối đa bằng decimal string, nhưng nếu gửi JSON number cho một client JavaScript sử dụng kiểu `Number` IEEE-754, các số nguyên lớn hơn `2⁵³ − 1` có thể **không được biểu diễn chính xác**.

Với identifier uint64 yêu cầu bảo toàn tuyệt đối, thường nên dùng **chuỗi decimal** trong JSON cùng schema rõ, hoặc một giao thức có hỗ trợ số nguyên 64-bit nguyên bản và client xử lý đúng.

```json
{
  "counterId": "18446744073709551615"
}
```

Ví dụ trên dùng một **string** để tránh chuyển qua floating-point của client. Không tuyên bố mọi hệ thống JSON number đều mất chính xác: điều đó phụ thuộc parser/kiểu số của từng client. Nhưng với JavaScript `Number` mặc định, rủi ro là có thật.

### 15.3. Signed BIGINT trong database không tự là uint64

Một cột SQL `BIGINT` thường biểu diễn signed 64-bit; nếu muốn lưu `18446744073709551615` dưới dạng **số dương**, bạn có thể cần `DECIMAL(20,0)`, hỗ trợ unsigned của database cụ thể hoặc lưu decimal string/bytes theo schema.

Nếu lưu `long` bits `-1` trong signed BIGINT rồi truy vấn `ORDER BY`, thứ tự đó thường là **signed**, khác thứ tự uint64 mong muốn. Cần định nghĩa rõ contract storage, indexing, comparison và mapping ORM; không chỉ format đúng lúc xuất màn hình.

### 15.4. Chữ ký số, token và leading zeros

Nếu một identifier hoặc token được ký theo **text nguyên văn**, chuỗi `"00042"` và `"42"` có thể mang ý nghĩa khác về byte-level dù parse ra cùng một số. `toUnsignedString` sẽ chuẩn hóa về `"42"`. Không parse rồi format lại **trước khi xác thực chữ ký** nếu chuẩn chữ ký yêu cầu bảo toàn payload gốc.

### 15.5. Định dạng và validation phải thống nhất từ đầu tới cuối

Ở ranh giới API, hãy định nghĩa một trong các hợp đồng:

1. **Unsigned decimal canonical:** ASCII `0` hoặc chữ số không có 0 đầu, không dấu cộng, giới hạn miền uint32/uint64.
2. **Unsigned decimal lenient:** cho phép dấu `+` hoặc whitespace theo policy, sau đó chuẩn hóa.
3. **Hex unsigned:** chỉ ký tự hex, có/không prefix và độ rộng cố định được mô tả tường minh.
4. **Binary field:** đọc raw bytes với endian xác định, không parse text.

Đừng lẫn các hợp đồng khiến hệ thống này ghi `0xFFFFFFFF` còn hệ thống kia gọi `parseUnsignedLong("0xFFFFFFFF",16)` rồi ném exception.

## 16. Kiểm tra đầu vào, lỗi bảo mật và giới hạn hiệu năng

### 16.1. Dữ liệu không đáng tin cần có độ dài tối đa

Parser sẽ báo lỗi nếu số vượt miền, nhưng không có nghĩa nên chấp nhận một request string dài hàng chục megabyte rồi mới kiểm tra. Với một trường uint32/uint64, có thể đặt giới hạn ký tự theo **format đã định nghĩa**, ví dụ decimal canonical uint32 tối đa 10 chữ số, uint64 tối đa 20 chữ số.

**Lưu ý:** nếu domain cho phép hàng nghìn số 0 đầu hoặc prefix `+`, giới hạn 10/20 sẽ từ chối một số chuỗi mà parser vẫn có thể hiểu. Đó là lựa chọn **validation của API**, không phải quy tắc chung của `parseUnsigned...`.

### 16.2. Quy tắc Unicode của `Character.digit`

Javadoc diễn đạt chữ số được xác định bằng `Character.digit(char, radix)`. Vì vậy, không nên khẳng định `parseUnsigned...` chỉ chấp nhận **ASCII digits** trong mọi trường hợp. Nếu giao thức an toàn yêu cầu ASCII decimal/hex, hãy **kiểm tra ASCII ở boundary** bằng regex hoặc vòng kiểm tra ký tự được phép, rồi mới parse.

Cũng nên kiểm tra Unicode normalization nếu input người dùng có thể chứa nhiều dạng ký tự trông giống nhau. Đừng tự “normalize tất cả” khi điều đó có thể đổi định danh hoặc chữ ký đã được xác thực.

### 16.3. Tránh tạo BigInteger khi không cần

Nếu chỉ cần lưu, so sánh và format **uint32/uint64 bit-pattern**, các API `parseUnsigned...`/`compareUnsigned`/`toUnsignedString` đủ gọn. `BigInteger` là công cụ đúng khi cần số học dương **vượt signed primitive range**, nhưng tạo thêm object và có chi phí chuyển đổi. Dựa vào yêu cầu tính đúng và workload thực trước khi tối ưu.

### 16.4. Kết quả parse có thể âm không phải lỗi validation

Không viết:

```java
long bits = Long.parseUnsignedLong(input);
if (bits < 0) {
    throw new IllegalArgumentException("must be unsigned");
}
```

Đây là **anti-pattern**. Nó loại bỏ mọi uint64 lớn hơn `Long.MAX_VALUE` dù hoàn toàn hợp lệ. Muốn chặn miền tối đa nhỏ hơn uint64, hãy dùng `Long.compareUnsigned(bits,limitBits)` hoặc `BigInteger` theo chính sách.

## 17. Những lỗi hay gặp và cách sửa

1. **Coi giá trị `-1` sau parse là thất bại.** Sai: nó có thể là bit-pattern của uint32/uint64 tối đa. **Sửa:** dùng `toUnsignedString` hoặc phép so sánh không dấu.
2. **Dùng `Integer.parseInt("4294967295")`.** Sai miền signed. **Sửa:** dùng `parseUnsignedInt`.
3. **Dùng `Long.parseLong("18446744073709551615")`.** Sai miền signed. **Sửa:** dùng `parseUnsignedLong`.
4. **Dùng `Integer.toString(bits)` để hiển thị uint32.** Có thể xuất âm. **Sửa:** `Integer.toUnsignedString(bits)`.
5. **Dùng `Long.toString(bits)` để xuất uint64 ID.** Có thể xuất âm. **Sửa:** `Long.toUnsignedString(bits)`.
6. **Dùng `(long)intBits` để đổi uint32 thành long dương.** Cast signed sign-extends. **Sửa:** `Integer.toUnsignedLong(intBits)`.
7. **Tưởng `parseUnsignedLong` trả `BigInteger`.** Không; vẫn là `long` bits. **Sửa:** dùng BigInteger khi cần số học dương.
8. **Dùng `BigInteger.valueOf(-1L)` để đọc uint64 max.** Ra âm 1. **Sửa:** `new BigInteger(Long.toUnsignedString(bits))`.
9. **Dùng toán tử `<`/`>` để so sánh unsigned bits.** Sai khi bit dấu khác nhau. **Sửa:** `compareUnsigned`.
10. **Dùng toán tử `/`/`%` khi phải chia không dấu.** Sai kết quả. **Sửa:** `divideUnsigned`/`remainderUnsigned`.
11. **Gửi `"0xFF"` thẳng tới `parseUnsignedInt(s,16)`.** Prefix không được hỗ trợ. **Sửa:** validate/cắt prefix theo giao thức.
12. **Gửi `"1_000"` như một chuỗi số.** Java source literal khác text parsing. **Sửa:** input validation có policy separator.
13. **Tưởng `"010"` mặc định là bát phân.** Parser String default radix 10. **Sửa:** truyền radix 8 nếu yêu cầu.
14. **Gửi dấu âm `"-1"` để biểu diễn uint64 max.** Parser sẽ từ chối. **Sửa:** dùng chuỗi decimal unsigned tương ứng.
15. **Trả giá trị fallback 0 khi parse lỗi.** Gây nhầm dữ liệu không hợp lệ với uint32/uint64 thực sự bằng 0. **Sửa:** báo lỗi domain hoặc Result/Optional theo contract.
16. **Coi `NumberFormatException` là phép tự làm tròn/bao bit.** Parser kiểm tra overflow và từ chối. **Sửa:** nếu cần modulo, thiết kế chuyển đổi bit riêng.
17. **Dùng `longValueExact()` cho uint64 BigInteger lớn.** Nó kiểm tra miền signed. **Sửa:** validate `signum`/`bitLength` rồi dùng `longValue()` có chủ đích.
18. **Cho rằng `toUnsignedString` giữ leading zeros/prefix/chữ hoa.** Không. **Sửa:** giữ text gốc hoặc format/pad theo schema.
19. **Dùng overload `parseUnsignedInt(CharSequence,...)` khi compile `--release 8`.** API chỉ có từ Java 9. **Sửa:** dùng overload String/radix của Java 8.
20. **Lưu uint64 max vào số thực dấu phẩy động.** Có thể mất bit. **Sửa:** chuỗi decimal, BigInteger hoặc binary protocol giữ nguyên số nguyên.
21. **Lưu long bits vào signed DB rồi sort như uint64.** Có thể sai thứ tự. **Sửa:** schema và comparator phản ánh unsigned.
22. **Gọi `parseUnsignedInt(text,37)`.** Radix ngoài [2,36]. **Sửa:** validate cơ số trước.
23. **Dùng `String.strip()` trong source Java 8.** API chỉ có từ Java 11. **Sửa:** dùng `trim()` nếu policy cho phép.
24. **Giả định mọi ký tự số được parser nhận đều là ASCII.** Không đủ chắc theo `Character.digit`. **Sửa:** kiểm tra ASCII riêng nếu giao thức yêu cầu.
25. **Lấy overflow của `Math.addExact` làm overflow uint64.** `addExact` kiểm tra signed. **Sửa:** áp dụng kiểm tra unsigned thích hợp hoặc BigInteger.

## 18. Checklist thiết kế API uint32/uint64

- [ ] Dữ liệu được hiểu là **bit-pattern** hay một số nguyên toán học không âm?
- [ ] Miền là uint32, uint64 hay còn lớn hơn?
- [ ] Input là decimal, hex, binary, hoặc bytes?
- [ ] Có chấp nhận dấu `+`, leading zeros, whitespace, prefix hoặc Unicode digits không?
- [ ] Radix được xác định tại boundary và validate trong [2,36]?
- [ ] Parse dùng `Integer.parseUnsignedInt` / `Long.parseUnsignedLong` phù hợp bề rộng?
- [ ] Kiểm tra overflow dựa vào `NumberFormatException`, không dựa vào việc kết quả signed âm?
- [ ] Khi xuất UI/JSON, có dùng `toUnsignedString` để giữ unsigned decimal?
- [ ] Khi unsigned int cần tính toán dương, có dùng `Integer.toUnsignedLong`?
- [ ] Khi unsigned long cần BigInteger, có chuyển qua unsigned decimal string?
- [ ] Khi chuyển BigInteger về long bits, có kiểm tra `signum`/`bitLength`?
- [ ] Khi sort/compare, có dùng `compareUnsigned`?
- [ ] Khi chia/lấy dư, có dùng `divideUnsigned`/`remainderUnsigned`?
- [ ] Nếu cần fixed-width hex/binary, có thêm padding và chuẩn hóa case?
- [ ] Có tránh mất chính xác khi truyền JSON number cho JavaScript `Number`?
- [ ] Database có schema, sort/order và indexing phù hợp unsigned?
- [ ] Có test các điểm: 0, 1, 2³¹−1, 2³¹, 2³²−1, 2³², 2⁶³−1, 2⁶³, 2⁶⁴−1, 2⁶⁴?
- [ ] Có test dấu âm, dấu cộng, chuỗi trống, null, ký tự sai radix, separator và space?
- [ ] Có test vòng parse → format → parse ở mỗi radix dự kiến hỗ trợ?
- [ ] Có log lỗi input theo kiểu an toàn, không lộ ID/path/token nhạy cảm?

## 19. Tự luyện và lời giải

**1. `Integer.parseUnsignedInt("4294967295")` trả `-1` có sai không?**  
Không. `-1` là cách `int` signed giải thích 32 bit toàn 1. `Integer.toUnsignedString` xuất lại `4294967295`.

**2. Giá trị nào lớn nhất mà `parseUnsignedInt` chấp nhận?**  
`2³² − 1 = 4294967295`.

**3. `Long.parseUnsignedLong("18446744073709551615")` có hợp lệ không?**  
Có. Đây là `2⁶⁴ − 1`, trả `long` bit-pattern `-1L`.

**4. `Long.parseUnsignedLong("18446744073709551616")` làm gì?**  
Ném `NumberFormatException` vì vượt uint64.

**5. Lấy uint32 dương từ `int -1` nên dùng gì?**  
`Integer.toUnsignedLong(-1)` cho `4294967295L`.

**6. Lấy số toán học dương từ long bits `-1L` bằng BigInteger thế nào?**  
`new BigInteger(Long.toUnsignedString(-1L))`.

**7. `BigInteger.valueOf(-1L)` có biểu diễn uint64 max không?**  
Không, nó là số toán học âm 1.

**8. `parseUnsignedInt("ff",16)` bằng bao nhiêu?**  
255.

**9. `parseUnsignedInt("0xff",16)` có hợp lệ không?**  
Không. Parser này không tự nhận prefix `0x`.

**10. `parseUnsignedInt("010")` mặc định bằng mấy?**  
10, vì radix mặc định là 10; `parseUnsignedInt("010",8)` bằng 8.

**11. `parseUnsignedLong("-1")` có dùng để đọc uint64 max không?**  
Không. Dấu âm không được chấp nhận trong input unsigned.

**12. Dấu `+` ở đầu chuỗi có hợp lệ không?**  
Có thể có, nếu theo sau là chữ số hợp lệ; ví dụ `"+42"`.

**13. Nếu cần chỉ chấp nhận ASCII decimal canonical, API parse đã đủ chưa?**  
Chưa. Phải kiểm tra format domain riêng vì parser cho dấu `+` và dùng `Character.digit`.

**14. `Integer.toUnsignedString(15,16)` có trả `"0000000f"` không?**  
Không, nó trả `"f"`; nếu cần fixed width phải pad.

**15. `Long.toUnsignedString(-1L,16)` trả gì?**  
`"ffffffffffffffff"`.

**16. Vì sao `-1L < 1L` nhưng `Long.compareUnsigned(-1L,1L) > 0`?**  
Vì phép so đầu có nghĩa signed, phép so sau hiểu `-1L` là `2⁶⁴−1`.

**17. Chia uint64 max cho 10 dùng phép gì?**  
`Long.divideUnsigned(maxBits,10L)` và `Long.remainderUnsigned(maxBits,10L)`.

**18. Round-trip `Long.parseUnsignedLong(Long.toUnsignedString(bits)) == bits` có giữ bit-pattern không?**  
Có, với mọi long bit-pattern hợp lệ.

**19. Các overload nhận `CharSequence, beginIndex, endIndex, radix` có từ Java 8 không?**  
Không, chúng có từ Java 9. Code Java 8 dùng overload String.

**20. Một JSON ID uint64 lớn nên được truyền dạng nào cho client JavaScript cần giữ chính xác?**  
Thường nên dùng **chuỗi decimal** hoặc một serialization schema nguyên số phù hợp; không mặc định trông cậy vào `Number`.

## 20. Tài liệu chính thức và phiên bản API

Các API trọng tâm **có từ Java 8 và vẫn hiện hành**, không dựa trên kỹ thuật legacy đã lỗi thời:

- [`Integer` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html): `parseUnsignedInt`, `toUnsignedString`, `toUnsignedLong`, `compareUnsigned`, `divideUnsigned`, `remainderUnsigned`; cách xử lý radix, dấu cộng và miền uint32.
- [`Long` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Long.html): `parseUnsignedLong`, `toUnsignedString`, `compareUnsigned`, `divideUnsigned`, `remainderUnsigned`, giới hạn unsigned 64-bit.
- [`Integer` — Java 8 API](https://docs.oracle.com/javase/8/docs/api/java/lang/Integer.html): đối chiếu những overload đã có từ Java 8.
- [`Long` — Java 8 API](https://docs.oracle.com/javase/8/docs/api/java/lang/Long.html): xác nhận Java 8 hỗ trợ parse/format unsigned 64-bit.
- [`BigInteger` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigInteger.html): số học dương vượt `Long.MAX_VALUE`, `signum`, `bitLength` và chuyển đổi có kiểm soát.
- [`Character` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html): `MIN_RADIX`, `MAX_RADIX`, `digit`.
- [`ByteBuffer` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/ByteBuffer.html): đọc raw bits và kiểm soát byte order cho giao thức nhị phân.

**Tóm lại:** `parseUnsignedInt`/`parseUnsignedLong` chuyển chuỗi không dấu thành **bit-pattern 32/64-bit** trong `int`/`long`. `toUnsignedString` chuyển ngược bit-pattern thành **chuỗi số không dấu**. Tính đúng cần được duy trì khi **so sánh, chia, mở rộng kiểu, serialize và validate**, chứ không chỉ ở bước parse.
