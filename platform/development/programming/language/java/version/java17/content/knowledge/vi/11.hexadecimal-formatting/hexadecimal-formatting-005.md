# Định dạng giá trị nguyên bằng `toHexDigits` trong Java 17

## 1. Mục tiêu của bài học

Hệ thập lục phân (hexadecimal, cơ số 16) thường được dùng để biểu diễn byte, bit mask, mã màu, địa chỉ, dữ liệu nhị phân và giá trị nguyên trong lúc debug. Trong Java 17, lớp `java.util.HexFormat` cung cấp các phương thức `toHexDigits` để chuyển trực tiếp giá trị primitive nguyên thành chuỗi chữ số hexadecimal.

Ví dụ:

~~~java
import java.util.HexFormat;

HexFormat hex = HexFormat.of();

System.out.println(hex.toHexDigits((byte) 0x2A)); // 2a
System.out.println(hex.toHexDigits(0x2A));        // 0000002a
~~~

Hai lời gọi có kết quả độ dài khác nhau vì kiểu đầu vào khác nhau:

- `byte` có 8 bit, nên biểu diễn đầy đủ cần 2 chữ số hex.
- `int` có 32 bit, nên biểu diễn đầy đủ cần 8 chữ số hex.

`toHexDigits` không phải phép đổi một số thành dạng thập phân, cũng không tự thêm tiền tố `0x`. Nó biểu diễn **các bit của giá trị nguyên theo nhóm bốn bit (nibble)** thành chữ số hex.

Sau bài học, người học cần:

1. Sử dụng `HexFormat.of().toHexDigits(...)` cho `byte`, `short`, `int` và `long`.
2. Giải thích vì sao kết quả mặc định có độ rộng cố định theo kiểu primitive.
3. Hiểu overload nhận `digits` và tác động của việc chỉ lấy một số chữ số hex.
4. Phân biệt biểu diễn bit của số âm theo two's complement với biểu diễn số nguyên có dấu thập phân.
5. Phân biệt `toHexDigits`, `Integer.toHexString`/`Long.toHexString` và `formatHex(byte[])`.
6. Chọn đúng cách định dạng cho dữ liệu nhị phân, kiểm tra kết quả và xử lý trường hợp cần round-trip.

**Phạm vi phiên bản:** `HexFormat` được bổ sung trong Java 17; các ví dụ ở đây dùng API chuẩn Java SE 17, không cần bật preview.

## 2. Cơ sở: một chữ số hex biểu diễn bốn bit

Hệ hexadecimal có 16 ký hiệu:

~~~text
Giá trị:  0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15
Ký hiệu: 0 1 2 3 4 5 6 7 8 9  A  B  C  D  E  F
~~~

Mỗi chữ số hex biểu diễn đúng một **nibble** (4 bit). Hai chữ số hex biểu diễn một byte (8 bit):

~~~text
Hex:      A     5
Binary: 1010  0101
       └─ 4 bit ─┘
~~~

Ví dụ:

- `0x0F` là `0000 1111` (15 ở hệ thập phân).
- `0x10` là `0001 0000` (16 ở hệ thập phân).
- `0xFF` là `1111 1111` (255 nếu hiểu như byte không dấu).
- `0x1234` gồm bốn chữ số hex, tương ứng 16 bit.

Trong Java, các kiểu nguyên primitive có dấu:

| Kiểu | Độ rộng | Số chữ số hex để biểu diễn đủ bit |
|---|---:|---:|
| `byte` | 8 bit | 2 |
| `short` | 16 bit | 4 |
| `int` | 32 bit | 8 |
| `long` | 64 bit | 16 |

Số chữ số hex bằng số bit chia cho 4. Khi định dạng giá trị primitive, `HexFormat.toHexDigits` tạo chuỗi theo độ rộng của kiểu, kể cả khi giá trị dương có thể viết ngắn hơn.

Ví dụ, số nguyên `10` có thể viết thành `a` nếu chỉ cần dạng ngắn nhất, nhưng giá trị `int` có đủ 32 bit được biểu diễn thành `0000000a` bởi `toHexDigits(int)`.

## 3. API `java.util.HexFormat` trong Java 17

`HexFormat` là lớp tiện ích bất biến dùng để định dạng và phân tích dữ liệu hexadecimal. Tạo một instance với:

~~~java
HexFormat hex = HexFormat.of();
~~~

Instance mặc định sử dụng chữ số hex viết thường. Có thể yêu cầu chữ hoa:

~~~java
HexFormat upper = HexFormat.of().withUpperCase();
System.out.println(upper.toHexDigits(0x2A)); // 0000002A
~~~

Các instance `HexFormat` là immutable và thread-safe; có thể tạo một formatter cấu hình sẵn rồi dùng lại.

### 3.1. Các overload `toHexDigits`

Java 17 cung cấp các overload cho bốn kiểu nguyên:

| Kiểu đầu vào | Định dạng đầy đủ | Overload chọn số chữ số |
|---|---|---|
| `byte` | `toHexDigits(byte value)` | `toHexDigits(byte value, int digits)` |
| `short` | `toHexDigits(short value)` | `toHexDigits(short value, int digits)` |
| `int` | `toHexDigits(int value)` | `toHexDigits(int value, int digits)` |
| `long` | `toHexDigits(long value)` | `toHexDigits(long value, int digits)` |

Overload không có `digits` trả về số chữ số cố định theo độ rộng kiểu:

~~~java
HexFormat hex = HexFormat.of();

System.out.println(hex.toHexDigits((byte) 10));  // 0a
System.out.println(hex.toHexDigits((short) 10)); // 000a
System.out.println(hex.toHexDigits(10));         // 0000000a
System.out.println(hex.toHexDigits(10L));        // 000000000000000a
~~~

Không cần tự thêm các số 0 ở đầu; đó là đặc điểm của dạng biểu diễn đủ độ rộng.

### 3.2. Không có overload riêng cho mọi kiểu

`HexFormat.toHexDigits` không cung cấp overload cho `char`, `boolean`, `float`, `double` hoặc `BigInteger`. Nếu cần biểu diễn một giá trị thuộc các kiểu này, cần xác định ý nghĩa mong muốn trước khi chuyển:

- Với `char`, có thể định dạng code unit dưới dạng số nguyên 16 bit.
- Với `float`/`double`, nếu cần xem bit pattern IEEE 754 thì dùng API chuyển đổi bit như `Float.floatToIntBits` hoặc `Double.doubleToLongBits`, rồi định dạng số nguyên tương ứng.
- Với `BigInteger`, dùng API riêng của nó như `toString(16)` khi cần biểu diễn độ dài tùy ý; phải tự quyết định cách xử lý dấu và padding.

Không ép kiểu tùy tiện một số thực sang `int` rồi gọi `toHexDigits` nếu mục tiêu là xem bit pattern của số thực; phép ép kiểu số học và chuyển đổi bit là hai việc khác nhau.

## 4. Định dạng theo độ rộng của kiểu primitive

### 4.1. `byte`: hai chữ số hex

~~~java
HexFormat hex = HexFormat.of();

byte value = 42;
System.out.println(hex.toHexDigits(value)); // 2a
~~~

Giá trị `byte` có 8 bit. Một chữ số hex chỉ biểu diễn được 4 bit, nên cần hai chữ số để biểu diễn đủ byte.

Ví dụ với bit pattern:

~~~java
byte data = (byte) 0xA5;
System.out.println(data);                    // -91 (byte có dấu)
System.out.println(hex.toHexDigits(data));   // a5
~~~

Đây là điểm rất quan trọng: giá trị thập phân khi in ra là `-91`, nhưng bit pattern của byte là `1010 0101`, được viết thành `a5`. `toHexDigits` biểu diễn bit pattern theo độ rộng của kiểu, không in dấu trừ.

### 4.2. `short`: bốn chữ số hex

~~~java
short value = (short) 0x1234;
System.out.println(hex.toHexDigits(value)); // 1234
~~~

Với giá trị âm:

~~~java
short minusOne = -1;
System.out.println(hex.toHexDigits(minusOne)); // ffff
~~~

`short` có 16 bit; `-1` có bit pattern toàn bit 1 trong biểu diễn two's complement 16 bit.

### 4.3. `int`: tám chữ số hex

~~~java
int value = 0x1234ABCD;
System.out.println(hex.toHexDigits(value)); // 1234abcd
~~~

Với số nhỏ:

~~~java
System.out.println(hex.toHexDigits(15)); // 0000000f
~~~

Với số âm:

~~~java
System.out.println(hex.toHexDigits(-1)); // ffffffff
~~~

Kết quả `ffffffff` biểu diễn 32 bit của `int -1`, không phải một chuỗi có dấu âm.

### 4.4. `long`: mười sáu chữ số hex

~~~java
long value = 0x0123456789ABCDEFL;
System.out.println(hex.toHexDigits(value)); // 0123456789abcdef
~~~

Với `long -1L`:

~~~java
System.out.println(hex.toHexDigits(-1L)); // ffffffffffffffff
~~~

Độ rộng cố định giúp so sánh và đọc bit pattern dễ dàng, đặc biệt khi làm việc với mask 64 bit, ID nhị phân hoặc dữ liệu từ giao thức.

## 5. Ý nghĩa của số chữ số trong overload `toHexDigits(value, digits)`

Overload có `digits` cho phép lấy một số chữ số hex xác định từ giá trị. Số chữ số phải nằm trong phạm vi từ 1 đến độ rộng tối đa của kiểu:

| Kiểu | Giá trị `digits` hợp lệ |
|---|---|
| `byte` | 1 đến 2 |
| `short` | 1 đến 4 |
| `int` | 1 đến 8 |
| `long` | 1 đến 16 |

Nếu `digits` nhỏ hơn độ rộng đầy đủ, các chữ số hex **cao hơn bị bỏ đi**, chỉ giữ lại các chữ số thấp nhất.

Ví dụ:

~~~java
HexFormat hex = HexFormat.of();

int value = 0x12345678;
System.out.println(hex.toHexDigits(value));    // 12345678
System.out.println(hex.toHexDigits(value, 4)); // 5678
System.out.println(hex.toHexDigits(value, 2)); // 78
System.out.println(hex.toHexDigits(value, 1)); // 8
~~~

Đây là **cắt phần cao**, không phải tự động làm tròn và cũng không phải kiểm tra giá trị có vừa với số chữ số hay không.

### 5.1. Overload `digits` với giá trị âm

~~~java
int value = -1;

System.out.println(hex.toHexDigits(value));    // ffffffff
System.out.println(hex.toHexDigits(value, 2)); // ff
~~~

Khi giữ hai chữ số thấp nhất của bit pattern `int -1`, kết quả là `ff`.

Tương tự:

~~~java
System.out.println(hex.toHexDigits((byte) -1, 1)); // f
System.out.println(hex.toHexDigits((short) -1, 2)); // ff
~~~

Không dùng overload cắt chữ số để thay cho validation. Ví dụ, nếu ID phải nằm trong khoảng 0 đến 65535, việc gọi `toHexDigits(id, 4)` với một `int` lớn hơn sẽ âm thầm bỏ phần cao và có thể tạo ra chuỗi trùng với ID khác. Hãy kiểm tra miền giá trị trước khi định dạng.

### 5.2. Giá trị `digits` không hợp lệ

Nếu `digits` nhỏ hơn 1 hoặc lớn hơn số chữ số tối đa của kiểu, API ném `IllegalArgumentException`.

~~~java
hex.toHexDigits(10, 0); // IllegalArgumentException
hex.toHexDigits(10, 9); // IllegalArgumentException: int tối đa 8 digits
~~~

Nên kiểm tra hoặc cố định `digits` từ cấu hình đã được xác thực. Không truyền một số chữ số bất kỳ do người dùng nhập mà không kiểm tra.

## 6. Thứ tự chữ số và biểu diễn two's complement

### 6.1. Chữ số được xuất từ cao xuống thấp

Với giá trị:

~~~java
int value = 0x12345678;
~~~

Kết quả `12345678` được đọc từ nibble có trọng số cao nhất đến nibble có trọng số thấp nhất:

~~~text
Giá trị int: 0x12345678
Nibbles:     1 2 3 4 5 6 7 8
Trọng số:    cao             thấp
Chuỗi:       "12345678"
~~~

Đây là thứ tự chữ số của giá trị nguyên. Nó không tự mô tả byte order của một mảng byte trong bộ nhớ hoặc giao thức. Khi chuyển nguyên sang byte array, phải xác định rõ big-endian hay little-endian.

### 6.2. Số âm không được viết bằng dấu trừ

Số nguyên Java có dấu được lưu theo biểu diễn two's complement với độ rộng cố định. Ví dụ:

~~~java
System.out.println(hex.toHexDigits((byte) -1));  // ff
System.out.println(hex.toHexDigits((short) -1)); // ffff
System.out.println(hex.toHexDigits(-1));         // ffffffff
System.out.println(hex.toHexDigits(-1L));        // ffffffffffffffff
~~~

Các kết quả có số lượng chữ số khác nhau vì kiểu dữ liệu có độ rộng khác nhau. Đây là biểu diễn các bit của giá trị, không phải chuỗi số nguyên âm dạng `-1`.

### 6.3. Giá trị dương và số 0 có padding

~~~java
System.out.println(hex.toHexDigits((byte) 1));  // 01
System.out.println(hex.toHexDigits((short) 1)); // 0001
System.out.println(hex.toHexDigits(1));         // 00000001
System.out.println(hex.toHexDigits(1L));        // 0000000000000001
~~~

Padding giúp mỗi giá trị cùng kiểu có cùng độ rộng. Điều này hữu ích khi đọc dump nhị phân hoặc so sánh các trường có kích thước cố định.

## 7. Chữ hoa, chữ thường và tiền tố

Mặc định, `HexFormat.of()` sử dụng chữ số a–f viết thường:

~~~java
HexFormat lower = HexFormat.of();
HexFormat upper = HexFormat.of().withUpperCase();

System.out.println(lower.toHexDigits(0xABCD)); // 0000abcd
System.out.println(upper.toHexDigits(0xABCD)); // 0000ABCD
~~~

Có thể kiểm tra cấu hình:

~~~java
System.out.println(lower.isUpperCase()); // false
System.out.println(upper.isUpperCase()); // true
~~~

### 7.1. `toHexDigits` không tự thêm `0x`

~~~java
String digits = hex.toHexDigits(0x2A);
System.out.println(digits);        // 0000002a
System.out.println("0x" + digits); // 0x0000002a
~~~

Nếu cần tiền tố, thêm nó một cách tường minh hoặc sử dụng API định dạng mảng byte phù hợp. Không giả định rằng `withPrefix("0x")` sẽ thay đổi kết quả của `toHexDigits`; prefix/delimiter/suffix là cấu hình dùng cho định dạng từng byte trong `formatHex`.

### 7.2. Tạo formatter theo cấu hình

~~~java
HexFormat upper = HexFormat.of().withUpperCase();
HexFormat colonSeparated = HexFormat.ofDelimiter(":");
~~~

Các cấu hình `withUpperCase()`, `withDelimiter(...)`, `withPrefix(...)` và `withSuffix(...)` trả về formatter đã cấu hình; chúng không sửa instance cũ. Các tùy chọn delimiter/prefix/suffix chủ yếu hữu ích khi định dạng **mảng byte** bằng `formatHex`.

## 8. Phân biệt `toHexDigits`, `Integer.toHexString` và `formatHex`

Ba API có liên quan nhưng phục vụ mục đích khác nhau.

| API | Đầu vào | Kết quả | Mục đích |
|---|---|---|---|
| `HexFormat.toHexDigits(int)` | Một giá trị primitive | 8 chữ số hex | Biểu diễn đủ 32 bit của giá trị `int` |
| `Integer.toHexString(int)` | Một giá trị `int` | Chuỗi hex không padding ở đầu đối với số dương; số âm thể hiện bit pattern 32 bit | Chuyển số nguyên sang dạng hex gọn |
| `Long.toHexString(long)` | Một giá trị `long` | Dạng hex gọn hoặc đủ bit cho số âm | Chuyển số nguyên dài sang dạng hex |
| `HexFormat.formatHex(byte[])` | Một dãy byte | Chuỗi hex của các byte, có thể có delimiter/prefix/suffix | Biểu diễn dữ liệu nhị phân |

Ví dụ:

~~~java
int value = 42;

System.out.println(HexFormat.of().toHexDigits(value)); // 0000002a
System.out.println(Integer.toHexString(value));        // 2a
~~~

Hai kết quả đều mô tả giá trị 42 theo hệ 16 nhưng có độ rộng khác nhau. Chọn theo hợp đồng đầu ra:

- Nếu cần biểu diễn đủ 32 bit: dùng `toHexDigits(int)`.
- Nếu cần dạng số nguyên ngắn nhất: dùng `Integer.toHexString(int)`.
- Nếu cần chuyển một mảng byte thành chuỗi hex: dùng `formatHex(byte[])`.

### 8.1. Ví dụ với mảng byte

~~~java
byte[] data = {0x01, 0x02, (byte) 0xAB};

HexFormat plain = HexFormat.of();
HexFormat separated = HexFormat.ofDelimiter(":").withUpperCase();

System.out.println(plain.formatHex(data));     // 0102ab
System.out.println(separated.formatHex(data)); // 01:02:AB
~~~

`formatHex` xử lý từng byte trong mảng. Nó không giống `toHexDigits(int)`, vốn định dạng một giá trị nguyên theo độ rộng kiểu.

### 8.2. Prefix và delimiter cho từng byte

~~~java
byte[] data = {0x01, 0x02, 0x0A};

HexFormat format = HexFormat.of()
        .withPrefix("0x")
        .withDelimiter(" ")
        .withUpperCase();

System.out.println(format.formatHex(data)); // 0x01 0x02 0x0A
~~~

Trong chuỗi này, prefix được thêm cho từng byte. Đây là quy ước hữu ích cho dump byte có phân cách; không nên nhầm nó với một tiền tố chung cho một số nguyên được định dạng bằng `toHexDigits`.

## 9. Chuyển giá trị nguyên sang byte array

`toHexDigits(int)` biểu diễn giá trị nguyên thành chuỗi hex theo thứ tự nibble. Nếu cần biểu diễn **các byte của một số nguyên** để trao đổi qua mạng hoặc ghi file, phải chọn byte order rõ ràng.

Ví dụ dùng `ByteBuffer`:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.HexFormat;

int value = 0x12345678;

byte[] bigEndian = ByteBuffer.allocate(Integer.BYTES)
        .order(ByteOrder.BIG_ENDIAN)
        .putInt(value)
        .array();

byte[] littleEndian = ByteBuffer.allocate(Integer.BYTES)
        .order(ByteOrder.LITTLE_ENDIAN)
        .putInt(value)
        .array();

HexFormat hex = HexFormat.of();
System.out.println(hex.formatHex(bigEndian));   // 12345678
System.out.println(hex.formatHex(littleEndian)); // 78563412
~~~

Hai byte array khác thứ tự, dù cùng biểu diễn một giá trị `int`. Định dạng `toHexDigits(value)` cho ra chuỗi chữ số `12345678`, không tự quyết định thứ tự byte trong giao thức.

Khi làm việc với binary protocol, file format hoặc phần cứng, hãy theo đặc tả về endian. Không suy luận byte order chỉ từ việc chuỗi hex của số nguyên được in từ trái sang phải.

## 10. Round-trip: định dạng rồi phân tích ngược

Với một primitive nguyên, `toHexDigits` chỉ định dạng thành chuỗi; nó không có phương thức `parseHexDigits` tương ứng trên `HexFormat` cho primitive. Cần chọn API parse đúng kiểu.

### 10.1. Parse `int` và `long`

~~~java
int value = 0x1234ABCD;
String digits = HexFormat.of().toHexDigits(value);

int parsed = Integer.parseUnsignedInt(digits, 16);
System.out.println(parsed == value); // true
~~~

Tại sao dùng `parseUnsignedInt`? Chuỗi `toHexDigits(int)` có thể bắt đầu bằng chữ số hex cao từ `8` đến `f`, khi đó giá trị 32 bit được hiểu theo bit pattern unsigned có thể vượt `Integer.MAX_VALUE`. `parseUnsignedInt` đọc đủ 32 bit và trả về cùng bit pattern trong kiểu `int` có dấu.

Với `long`:

~~~java
long value = 0xFEDCBA9876543210L;
String digits = HexFormat.of().toHexDigits(value);

long parsed = Long.parseUnsignedLong(digits, 16);
System.out.println(parsed == value); // true
~~~

Các hàm parse unsigned không làm kiểu `int` hoặc `long` trở thành kiểu unsigned mới; chúng cho phép parse toàn bộ miền bit rồi giữ kết quả trong primitive có dấu.

### 10.2. Parse `byte` và `short`

`Byte.parseByte` và `Short.parseShort` nhận giá trị số có dấu theo miền của kiểu. Nếu chuỗi hex biểu diễn bit pattern có bit cao nhất bằng 1, giá trị unsigned của chuỗi vượt miền dương của kiểu, nên cần parse qua kiểu rộng hơn hoặc xử lý byte:

~~~java
byte original = (byte) 0xA5;
String digits = HexFormat.of().toHexDigits(original);

int parsedBits = Integer.parseInt(digits, 16);
byte restored = (byte) parsedBits;

System.out.println(digits);               // a5
System.out.println(restored == original); // true
~~~

Ở đây `Integer.parseInt("a5", 16)` cho 165; ép về byte giữ 8 bit thấp, tái tạo bit pattern ban đầu.

Đối với `short`, cách tương tự:

~~~java
short original = (short) 0xF234;
String digits = HexFormat.of().toHexDigits(original);

short restored = (short) Integer.parseInt(digits, 16);
System.out.println(restored == original); // true
~~~

Chỉ ép kiểu sau khi đã kiểm soát chuỗi hex và số chữ số; không dùng cách này để chấp nhận dữ liệu đầu vào tùy ý mà bỏ qua validation.

### 10.3. Parse mảng byte bằng `HexFormat.parseHex`

`formatHex(byte[])` có phương thức parse tương ứng:

~~~java
HexFormat hex = HexFormat.of();
byte[] bytes = {(byte) 0x80, 0x01, 0x2A};

String encoded = hex.formatHex(bytes);
byte[] decoded = hex.parseHex(encoded);

System.out.println(encoded); // 80012a
System.out.println(java.util.Arrays.equals(bytes, decoded)); // true
~~~

Nếu đã cấu hình delimiter, prefix hoặc suffix, hãy dùng formatter tương ứng để parse chuỗi theo đúng định dạng. Không giả định chuỗi có dấu phân cách bất kỳ đều được parse bởi formatter mặc định.

## 11. Kiểm tra dữ liệu trước khi định dạng

### 11.1. Định dạng đủ độ rộng không kiểm tra nghiệp vụ

`toHexDigits(int)` chấp nhận mọi giá trị `int`, kể cả số âm. Nếu trường nghiệp vụ chỉ chấp nhận số không âm, cần kiểm tra trước:

~~~java
static String formatId(int id) {
    if (id < 0) {
        throw new IllegalArgumentException("id must be non-negative");
    }
    return HexFormat.of().toHexDigits(id);
}
~~~

Không dựa vào số chữ số để suy ra dữ liệu hợp lệ.

### 11.2. Cắt chữ số có thể làm mất thông tin

~~~java
int first = 0x12345678;
int second = 0xABCDEF78;

String a = HexFormat.of().toHexDigits(first, 2);  // 78
String b = HexFormat.of().toHexDigits(second, 2); // 78
~~~

Hai giá trị khác nhau tạo ra cùng kết quả vì chỉ giữ hai chữ số thấp. Đây là lý do không nên dùng overload `digits` để định dạng định danh duy nhất nếu không có kiểm tra miền.

### 11.3. Không trộn byte signed và unsigned

Java `byte` có miền `-128..127`, trong khi byte trong giao thức thường được diễn giải là giá trị không dấu `0..255`. `toHexDigits(byte)` biểu diễn đúng 8 bit, không cần chuyển sang unsigned trước:

~~~java
byte raw = (byte) 0xFE;
System.out.println(raw); // -2
System.out.println(HexFormat.of().toHexDigits(raw)); // fe
System.out.println(Byte.toUnsignedInt(raw)); // 254
~~~

Khi cần số nguyên không dấu để tính toán, dùng `Byte.toUnsignedInt(raw)`; khi cần biểu diễn byte thành hai chữ số hex, dùng `toHexDigits(raw)`.

## 12. Ví dụ tổng hợp chạy trên Java 17

Chương trình dưới đây định dạng các kiểu nguyên, thể hiện số âm, uppercase, cắt chữ số và chuyển đổi byte order:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.HexFormat;

public class Main {
    public static void main(String[] args) {
        HexFormat lower = HexFormat.of();
        HexFormat upper = HexFormat.of().withUpperCase();

        byte byteValue = (byte) 0xA5;
        short shortValue = (short) 0x1234;
        int intValue = 0x12345678;
        long longValue = 0x0123456789ABCDEFL;

        System.out.println(lower.toHexDigits(byteValue));  // a5
        System.out.println(lower.toHexDigits(shortValue)); // 1234
        System.out.println(lower.toHexDigits(intValue));   // 12345678
        System.out.println(lower.toHexDigits(longValue));  // 0123456789abcdef

        System.out.println(upper.toHexDigits(0xABCDEF));   // 00ABCDEF
        System.out.println(lower.toHexDigits(0x12345678, 4)); // 5678
        System.out.println(lower.toHexDigits(-1));         // ffffffff

        byte[] bytes = ByteBuffer.allocate(Integer.BYTES)
                .order(ByteOrder.BIG_ENDIAN)
                .putInt(intValue)
                .array();
        System.out.println(lower.formatHex(bytes));        // 12345678
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 -encoding UTF-8 Main.java
java Main
~~~

Đầu ra minh họa:

~~~text
a5
1234
12345678
0123456789abcdef
00ABCDEF
5678
ffffffff
12345678
~~~

Lưu ý: `0xABCDEF` có sáu chữ số hex có nghĩa, nhưng kiểu `int` cần đủ tám chữ số, nên kết quả có hai số 0 ở đầu: `00ABCDEF`. Dùng ví dụ này để thấy cấu hình uppercase chỉ đổi chữ `a..f` thành `A..F`, không đổi độ rộng.

## 13. Các lỗi thường gặp

### 13.1. Mong kết quả không có số 0 ở đầu

~~~java
HexFormat.of().toHexDigits(10); // 0000000a
~~~

Đây là kết quả đúng: overload `int` trả đủ tám chữ số. Nếu cần dạng ngắn nhất, dùng `Integer.toHexString(10)` hoặc định dạng theo hợp đồng khác.

### 13.2. Nghĩ rằng số âm được thêm dấu trừ

~~~java
HexFormat.of().toHexDigits(-1); // ffffffff
~~~

Đây là bit pattern 32 bit của `int -1`, không phải chuỗi `-1`.

### 13.3. Dùng `digits` để yêu cầu padding

`toHexDigits(value, digits)` không phải phương thức yêu cầu độ dài tùy ý lớn hơn độ rộng kiểu. `digits` chỉ nằm trong phạm vi cho phép và khi nhỏ hơn độ rộng thì các nibble cao bị loại.

### 13.4. Nhầm `toHexDigits(int)` với định dạng một byte

~~~java
int value = 0xA5;
System.out.println(HexFormat.of().toHexDigits(value));    // 000000a5
System.out.println(HexFormat.of().toHexDigits(value, 2)); // a5
System.out.println(HexFormat.of().toHexDigits((byte) value)); // a5
~~~

Chọn kiểu đầu vào thể hiện đúng độ rộng trường dữ liệu.

### 13.5. Nghĩ `withPrefix` áp dụng cho `toHexDigits`

Prefix, delimiter và suffix dùng khi định dạng mảng byte bằng `formatHex`. `toHexDigits` trả chuỗi chữ số cho một primitive. Nếu cần `0x`, thêm tường minh:

~~~java
String display = "0x" + HexFormat.of().toHexDigits(42);
~~~

### 13.6. Nhầm thứ tự chữ số với endian

`toHexDigits(0x12345678)` trả `12345678`; khi chuyển giá trị thành byte array little-endian, `formatHex` có thể trả `78563412`. Xác định byte order từ đặc tả dữ liệu, không từ tên phương thức.

### 13.7. Dùng cho số thực mà không chuyển bit pattern

`toHexDigits` không có overload `double`. Nếu muốn xem bit pattern của `double`, dùng `Double.doubleToLongBits(value)` hoặc `Double.doubleToRawLongBits(value)` tùy có cần giữ raw NaN payload hay không, rồi định dạng `long`. Chuyển `double` trực tiếp sang `long` bằng cast là phép chuyển đổi giá trị số, không phải xem bit pattern.

## 14. Bài tập thực hành

### Bài 1 — Độ rộng theo kiểu

Dự đoán kết quả:

~~~java
HexFormat hex = HexFormat.of();
System.out.println(hex.toHexDigits((byte) 1));
System.out.println(hex.toHexDigits((short) 1));
System.out.println(hex.toHexDigits(1));
System.out.println(hex.toHexDigits(1L));
~~~

**Đáp án:**

~~~text
01
0001
00000001
0000000000000001
~~~

Giải thích theo độ rộng 8, 16, 32 và 64 bit.

### Bài 2 — Chọn các chữ số thấp

Với `int value = 0xCAFEBABE`, hãy gọi `toHexDigits(value, 4)`.

**Đáp án:** `babe`; bốn chữ số cao `cafe` bị loại.

### Bài 3 — Số âm

Hãy dự đoán:

~~~java
hex.toHexDigits((byte) -1)
hex.toHexDigits((short) -1)
hex.toHexDigits(-1)
hex.toHexDigits(-1L)
~~~

**Đáp án:** `ff`, `ffff`, `ffffffff`, `ffffffffffffffff`. Mỗi kết quả thể hiện bit pattern two's complement với độ rộng của kiểu.

### Bài 4 — Chữ hoa và prefix

Tạo formatter chữ hoa, định dạng `0x00ABCDEF`, rồi tạo chuỗi có tiền tố `0x`.

~~~java
HexFormat upper = HexFormat.of().withUpperCase();
String result = "0x" + upper.toHexDigits(0x00ABCDEF);
System.out.println(result); // 0x00ABCDEF
~~~

### Bài 5 — Phân biệt số nguyên và byte array

Với `int value = 0x12345678`, định dạng giá trị bằng `toHexDigits`, sau đó chuyển thành bốn byte big-endian và định dạng bằng `formatHex`. Giải thích vì sao cả hai chuỗi có thể giống nhau trong big-endian, nhưng khác nhau khi byte order là little-endian.

### Bài 6 — Round-trip

Định dạng một `int` bất kỳ bằng `toHexDigits`, parse lại bằng `Integer.parseUnsignedInt(text, 16)`, rồi kiểm tra `==` với giá trị ban đầu. Thử cả số âm để hiểu vì sao cần parse unsigned.

## 15. Tiêu chí hoàn thành

Người học nắm vững bài khi có thể:

1. Giải thích một chữ số hex biểu diễn 4 bit và hai chữ số hex biểu diễn một byte.
2. Gọi đúng overload `HexFormat.toHexDigits` cho `byte`, `short`, `int`, `long`.
3. Dự đoán độ dài mặc định: 2, 4, 8, 16 chữ số.
4. Giải thích số âm được biểu diễn theo bit pattern two's complement, không có dấu trừ.
5. Sử dụng `digits` trong phạm vi hợp lệ và nhận ra việc chọn ít chữ số sẽ bỏ các nibble cao.
6. Chọn lowercase/uppercase và hiểu `toHexDigits` không tự thêm prefix.
7. Phân biệt `toHexDigits`, `Integer.toHexString` và `formatHex(byte[])`.
8. Phân biệt thứ tự chữ số hex với byte order của dữ liệu nhị phân.
9. Định dạng và parse lại giá trị nguyên/byte array với kiểu parse và kiểm tra miền phù hợp.
10. Biên dịch ví dụ bằng JDK 17, không cần preview.

## 16. Tài liệu chính thức

- [Java SE 17 API — `HexFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): các overload `toHexDigits`, `formatHex`, `parseHex`, cấu hình uppercase, prefix, delimiter và suffix.
- [Java SE 17 API — `Integer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `toHexString`, `parseUnsignedInt` và các phép chuyển đổi số nguyên.
- [Java SE 17 API — `Long`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): `toHexString` và `parseUnsignedLong`.
- [Java SE 17 API — `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): chuyển số nguyên sang byte array với thứ tự byte được xác định.

**Ghi nhớ:** `toHexDigits` định dạng bit pattern của một giá trị nguyên theo độ rộng primitive: 2/4/8/16 chữ số cho byte/short/int/long. Overload `digits` chỉ lấy các chữ số thấp và có thể làm mất thông tin. Dùng `formatHex` cho mảng byte, `toHexString` cho dạng số nguyên gọn, và luôn xác định rõ byte order khi dữ liệu được trao đổi dưới dạng bytes.
