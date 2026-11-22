# Integer, Long và biểu diễn số không dấu (Java 8+)

Java dùng `int` và `long` làm **kiểu số nguyên có dấu**, nhưng 32 hoặc 64 bit của chúng cũng thường dùng để mang những giá trị **unsigned** do giao thức mạng, định dạng nhị phân, database hoặc hệ thống khác quy định. **Từ Java 8**, `Integer` và `Long` có các phương thức chính thức để parse, in, so sánh, chia và lấy phần dư **theo cách diễn giải không dấu**, trong khi bản thân primitive vẫn là `int` hoặc `long` bình thường.

Điểm then chốt: **unsigned không phải một primitive mới trong Java**. Một bit pattern lưu trong `int` có thể hiển thị là số âm theo signed nhưng là số dương lớn theo unsigned. Các thao tác đúng cần giữ nguyên bit pattern và dùng API khớp với hợp đồng dữ liệu: `parseUnsignedInt`, `parseUnsignedLong`, `toUnsignedString`, `compareUnsigned`, `divideUnsigned`, `remainderUnsigned`, `Integer.toUnsignedLong`; dùng `BigInteger` khi cần một **giá trị số dương chính xác lớn hơn `Long.MAX_VALUE`**.

Bài học dùng kiến thức vẫn được hỗ trợ trong Java hiện đại, phân biệt rõ API có từ Java 8 với các overload ra mắt sau. Chương trình Java độc lập ở phần dưới đã được biên dịch bằng JDK 17 và có các phép kiểm thử biên 32/64-bit.

## 1. Phạm vi của `int`, `long`, `Integer` và `Long`

| Loại | Số bit | Miền **signed** | Miền **unsigned** của cùng bit |
| --- | --- | --- | --- |
| `int` | 32 | -2³¹ đến 2³¹−1 | 0 đến 2³²−1 |
| `long` | 64 | -2⁶³ đến 2⁶³−1 | 0 đến 2⁶⁴−1 |
| `Integer` | Wrapper của `int` | Cùng miền `int` | Có các static methods diễn giải unsigned |
| `Long` | Wrapper của `long` | Cùng miền `long` | Có các static methods diễn giải unsigned |

Các giá trị cần nhớ:

| Mốc | Giá trị decimal |
| --- | --- |
| `Integer.MIN_VALUE` | -2147483648 |
| `Integer.MAX_VALUE` | 2147483647 |
| unsigned 32-bit max | 4294967295 |
| `Long.MIN_VALUE` | -9223372036854775808 |
| `Long.MAX_VALUE` | 9223372036854775807 |
| unsigned 64-bit max | 18446744073709551615 |

`Integer.SIZE` = 32, `Long.SIZE` = 64, `Integer.BYTES` = 4 và `Long.BYTES` = 8. `Integer` và `Long` là wrapper object cho các primitive signed, **không phải class unsigned mới**. `Integer.compareTo` và `Long.compareTo` vẫn dùng thứ tự **signed**, dù cùng lớp có thêm các static helper unsigned.

### Hai ý nghĩa của một mẫu bit

~~~text
32 bit:     11111111 11111111 11111111 11111111
Hex:        FFFFFFFF
Signed:     -1
Unsigned:   4294967295

32 bit:     10000000 00000000 00000000 00000000
Hex:        80000000
Signed:     -2147483648
Unsigned:   2147483648
~~~

Trong biểu diễn bù hai, bit cao nhất có trọng số âm khi diễn giải signed. Nhưng bit trong bộ nhớ không gắn sẵn nhãn signed hoặc unsigned. Khi Java nhận bốn byte `FF FF FF FF`, nó có thể lưu trong `int` là `-1` mà **không mất bất cứ bit nào**.

~~~java
int bits = -1;
System.out.println(Integer.toString(bits));         // -1
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
System.out.println(Integer.toHexString(bits));      // ffffffff
~~~

Ba dòng này dùng **một bit pattern**, không thay đổi biến `bits`.

## 2. Các phương thức unsigned của Java 8

| API | Đầu ra | Mục đích |
| --- | --- | --- |
| `Integer.parseUnsignedInt(String)` | `int` | Đọc decimal trong 0..2³²−1 thành raw 32 bit |
| `Integer.parseUnsignedInt(String,int)` | `int` | Đọc theo radix |
| `Integer.toUnsignedString(int)` | `String` | In decimal unsigned32 |
| `Integer.toUnsignedString(int,int)` | `String` | In unsigned32 theo radix |
| `Integer.toUnsignedLong(int)` | `long` | Zero-extend 32→64 bit để có số không âm |
| `Integer.compareUnsigned(int,int)` | `int` | So sánh unsigned32 |
| `Integer.divideUnsigned(int,int)` | `int` | Thương chia nguyên unsigned32 |
| `Integer.remainderUnsigned(int,int)` | `int` | Phần dư unsigned32 |
| `Long.parseUnsignedLong(String)` | `long` | Đọc decimal 0..2⁶⁴−1 thành raw 64 bit |
| `Long.parseUnsignedLong(String,int)` | `long` | Đọc unsigned64 theo radix |
| `Long.toUnsignedString(long)` | `String` | In decimal unsigned64 |
| `Long.toUnsignedString(long,int)` | `String` | In unsigned64 theo radix |
| `Long.compareUnsigned(long,long)` | `int` | So sánh unsigned64 |
| `Long.divideUnsigned(long,long)` | `long` | Thương unsigned64 |
| `Long.remainderUnsigned(long,long)` | `long` | Phần dư unsigned64 |

Các phương thức trên có từ **Java 8** và vẫn được hỗ trợ. Không có keyword `uint` hoặc `ulong` trong Java. **Lưu ý phiên bản:** overload `parseUnsignedInt(CharSequence, beginIndex, endIndex, radix)` và phiên bản `Long` tương ứng có từ **Java 9**, không nên gọi khi dự án phải tương thích Java 8.

Không nhầm việc “có helper unsigned” với khả năng dùng `int` để lưu giá trị dương 4294967295 theo phép so sánh signed: raw `int` vẫn là `-1`.

## 3. `Integer.parseUnsignedInt` — đọc miền 32-bit đầy đủ

~~~java
int raw = Integer.parseUnsignedInt("4294967295");
// raw == -1 khi diễn giải signed.

String decimal = Integer.toUnsignedString(raw);
// "4294967295".
~~~

`parseUnsignedInt` kiểm tra chuỗi nằm trong miền unsigned32 và **trả bit pattern trong `int`**, kể cả khi bit cao nhất là 1. Vì thế kết quả có thể âm khi in bằng `System.out.println(raw)`.

So sánh:

~~~java
// Integer.parseInt("4294967295"): NumberFormatException.
int bits = Integer.parseUnsignedInt("4294967295");
// Thành công; bits == -1.
~~~

`Integer.parseInt` chỉ hỗ trợ miền **signed int**. Không giải quyết bài toán bằng cách parse số rất lớn rồi cast hẹp **trước khi** kiểm tra range: cast làm mất bit cao và có thể che lỗi.

### Hex và radix

~~~java
int high = Integer.parseUnsignedInt("80000000", 16);
System.out.println(high);                          // -2147483648
System.out.println(Integer.toUnsignedString(high)); // 2147483648

int max = Integer.parseUnsignedInt("FFFFFFFF", 16);
System.out.println(Integer.toUnsignedString(max, 16)); // ffffffff
~~~

Radix thường hợp lệ trong khoảng `2..36`. Đối số `String` của `parseUnsignedInt(s,16)` là **dãy chữ số**, không mặc định chấp nhận prefix `0x`. Nếu nguồn yêu cầu `0xFFFFFFFF`, ứng dụng nên xác thực và bỏ prefix theo schema trước khi gọi parse, không âm thầm xóa mọi ký tự bất kỳ.

## 4. `Long.parseUnsignedLong` — đọc 64-bit không dấu

Giới hạn unsigned64 là 18446744073709551615, **lớn hơn** `Long.MAX_VALUE`:

~~~java
long bits = Long.parseUnsignedLong("18446744073709551615");

System.out.println(bits);                       // -1
System.out.println(Long.toUnsignedString(bits)); // 18446744073709551615
~~~

Kiểu dữ liệu trả về vẫn là `long`. `Long.parseUnsignedLong` **không** tạo một số nguyên dương signed vượt quá giới hạn; nó bảo toàn 64 bit và để các helper unsigned diễn giải.

Bit cao nhất của long:

~~~java
long high = Long.parseUnsignedLong("9223372036854775808");

System.out.println(high);                       // -9223372036854775808
System.out.println(Long.toUnsignedString(high)); // 9223372036854775808
~~~

Với hệ 16:

~~~java
long max = Long.parseUnsignedLong("ffffffffffffffff", 16);
String hex = Long.toUnsignedString(max, 16);
// "ffffffffffffffff".
~~~

`Long.parseLong("18446744073709551615")` sẽ ném `NumberFormatException` vì chỉ nhận miền **signed long**. Cũng không được parse chuỗi `"-1"` với `parseUnsignedLong` rồi hy vọng Java hiểu là unsigned max: văn bản có dấu trừ là **không hợp lệ theo hợp đồng unsigned parser**.

## 5. Hiển thị số unsigned với `toUnsignedString`

| Raw bit pattern | Signed decimal | Unsigned decimal | Unsigned hex |
| --- | --- | --- | --- |
| `int -1` | `-1` | `4294967295` | `ffffffff` |
| `int Integer.MIN_VALUE` | `-2147483648` | `2147483648` | `80000000` |
| `long -1L` | `-1` | `18446744073709551615` | `ffffffffffffffff` |
| `long Long.MIN_VALUE` | `-9223372036854775808` | `9223372036854775808` | `8000000000000000` |

~~~java
int raw32 = -1;
String decimal32 = Integer.toUnsignedString(raw32);
String binary32 = Integer.toUnsignedString(raw32, 2);
String hex32 = Integer.toUnsignedString(raw32, 16);

long raw64 = -1L;
String decimal64 = Long.toUnsignedString(raw64);
String hex64 = Long.toUnsignedString(raw64, 16);
~~~

Hàm `toUnsignedString(...,radix)` không tự thêm `0x`/`0b` và không tự đảm bảo đủ số chữ số của một field nhị phân. Nếu một protocol quy định **8 hex digits cho u32** hoặc **16 hex digits cho u64**, cần padding bên ngoài theo format được công bố. Đừng dùng signed `Integer.toString(raw)` để serialize unsigned32 trong API, vì raw có bit dấu sẽ thành chữ số âm.

### `Long.toHexString` và `Integer.toHexString`

Các hàm `toHexString` cũng biểu diễn bit pattern dưới dạng hex không có tiền tố dấu âm. Nhưng trong code giao tiếp với domain unsigned, `toUnsignedString(raw,16)` cho người đọc thấy rõ **ý định diễn giải không dấu**. Cả hai là API còn hỗ trợ.

## 6. `Integer.toUnsignedLong`: zero-extension khác cast signed

~~~java
int raw = -1;

long signed = (long) raw;              // -1
long unsigned = Integer.toUnsignedLong(raw); // 4294967295
~~~

Cast `(long)raw` thực hiện **sign-extension**: kéo dài bit dấu ở phía trái. `Integer.toUnsignedLong(raw)` thực hiện **zero-extension**: các bit cao của `long` bằng 0, giữ 32 bit thấp của raw. Vì mọi unsigned32 đều không lớn hơn 4294967295, một `long` signed chứa được **toàn bộ miền dưới dạng số không âm**.

Tương đương về bit:

~~~java
long unsigned = raw & 0xFFFF_FFFFL;
// 4294967295.
~~~

Dù cách mask là hợp lệ, `Integer.toUnsignedLong` làm ngữ nghĩa rõ hơn và dễ review hơn. Đừng convert một operand sang long theo unsigned rồi so sánh với một operand raw int còn mang signed: hãy thống nhất quy ước chuyển đổi.

### Khi nào nên mở rộng u32 sang long?

- Dữ liệu giao thức dùng **unsigned 32-bit** và ứng dụng muốn tính toán như số dương.
- Một field sequence/counter trong binary format cần hiển thị decimal 0..4294967295.
- Một checksum 32-bit được lưu qua raw int rồi cần xuất API dưới dạng giá trị dương.
- Một kiểu DB/API numeric đủ rộng cho miền unsigned32 mà không muốn lưu raw int âm.

Ngược lại, nếu chỉ chuyển nguyên 32 bit qua binary protocol, có thể giữ raw int và dùng helper unsigned khi hiển thị/so sánh.

## 7. `Byte` và `Short`: mở rộng unsigned 8/16 bit

`byte` và `short` trong Java cũng là signed. Với byte `0xFF`, giá trị `byte` là -1; khi cast thẳng sang `int` sẽ giữ -1.

Java 8 có:

~~~java
byte rawByte = (byte) 0xFF;

int u8 = Byte.toUnsignedInt(rawByte);   // 255.
long u8Long = Byte.toUnsignedLong(rawByte); // 255.

short rawShort = (short) 0xFFFF;
int u16 = Short.toUnsignedInt(rawShort); // 65535.
long u16Long = Short.toUnsignedLong(rawShort); // 65535.
~~~

`Byte.toUnsignedInt` là cách đọc ngắn gọn hơn `rawByte & 0xFF`; tương tự với short. **`Byte.compareUnsigned` và `Short.compareUnsigned` ra mắt ở Java 9**, không dùng chúng trong dự án chỉ hỗ trợ Java 8; khi đó mở rộng sang `int` không âm rồi compare.

Những API này rất hữu ích khi làm việc với `byte[]` từ file, network, thiết bị hoặc binary protocol.

## 8. So sánh unsigned bằng `compareUnsigned`

~~~java
int x = -1; // unsigned: 4294967295.
int y = 1;

System.out.println(Integer.compare(x, y));         // -1
System.out.println(Integer.compareUnsigned(x, y)); // 1
~~~

Theo signed, -1 nhỏ hơn +1; theo unsigned, 4294967295 lớn hơn 1. `Integer.compareUnsigned(a,b)` và `Long.compareUnsigned(a,b)` cho quan hệ so sánh unsigned, trong đó số âm/0/số dương biểu diễn nhỏ hơn/bằng/lớn hơn. Đừng gắn logic với giả định **mọi comparator đều trả đúng một trong -1/0/1**, dù các ví dụ cụ thể ở đây cho giá trị đó.

~~~java
int first = Integer.parseUnsignedInt("4294967295");
int second = 1;

boolean signedLess = first < second; // true.
boolean unsignedGreater =
        Integer.compareUnsigned(first, second) > 0; // true.
~~~

Toán tử `<`, `>` và natural order của `Integer.compareTo`/`Long.compareTo` dùng **signed**. Nếu field đại diện u32/u64, phải dùng comparator unsigned nhất quán.

### Sắp xếp theo thứ tự unsigned

~~~java
List<Integer> values = new ArrayList<>(
        Arrays.asList(-1, 0, 1, Integer.MIN_VALUE));

values.sort(Integer::compareUnsigned);

String ordered = values.stream()
        .map(Integer::toUnsignedString)
        .collect(Collectors.joining(", "));
// 0, 1, 2147483648, 4294967295.
~~~

Với `List<Long>`, dùng `Long::compareUnsigned`. `Collections.sort(list)` hoặc `stream.sorted()` không có comparator sẽ dùng signed natural order.

### Sequence counter có wrap khác numeric order

Nếu counter 32-bit chạy từ unsigned 4294967295 về 0, `Integer.compareUnsigned(0,-1) < 0` vẫn đúng theo **thứ tự số học unsigned**. Nhưng “0 là sequence **mới hơn** vì counter vừa quay vòng” là quy tắc **giao thức riêng**. Chỉ so sánh unsigned không giải quyết wrap ordering; phải có thuật toán theo cửa sổ/cycle được đặc tả.

## 9. Chia và phần dư: `divideUnsigned`/`remainderUnsigned`

Toán tử `/` và `%` trong Java dùng **signed interpretation**. Nếu raw int là -1 nhưng ý nghĩa nguồn là unsigned max, cần:

~~~java
int raw32 = Integer.parseUnsignedInt("4294967295");

int q32 = Integer.divideUnsigned(raw32, 10);      // 429496729.
int r32 = Integer.remainderUnsigned(raw32, 10);  // 5.
~~~

Vì 4294967295 = 429496729 × 10 + 5, phép tính unsigned khớp giá trị toán học.

Với 64 bit:

~~~java
long raw64 = Long.parseUnsignedLong("18446744073709551615");

long q64 = Long.divideUnsigned(raw64, 10L);
long r64 = Long.remainderUnsigned(raw64, 10L);

// q64 = 1844674407370955161, r64 = 5.
~~~

**Thương và phần dư vẫn là raw `int`/`long`.** Nếu thương unsigned lớn hơn signed max, khi in trực tiếp nó vẫn có thể âm. Dùng `toUnsignedString` cho các giá trị muốn serialize theo nghĩa unsigned.

Chia cho 0 vẫn ném `ArithmeticException`:

~~~java
// Integer.divideUnsigned(10, 0) -> ArithmeticException.
// Long.remainderUnsigned(10L, 0L) -> ArithmeticException.
~~~

Không coi unsigned methods là cơ chế tránh chia cho 0.

## 10. Cộng, trừ, nhân và overflow

Java 8 không có các helper `Integer.addUnsigned`, `Long.multiplyUnsigned`. Lý do: trên cùng width, **cộng, trừ, nhân** ở tầng bit cho kết quả giống nhau **theo modulo 2³²/2⁶⁴**, bất kể các bit được hiểu signed hay unsigned. Cái khác là mong đợi khi **overflow**.

~~~java
int maxU32 = Integer.parseUnsignedInt("4294967295");
int next = maxU32 + 1;

System.out.println(Integer.toUnsignedString(next)); // 0.
~~~

Nó wrap theo modulo 2³². Nếu nghiệp vụ muốn **tổng toán học chính xác**, 0 là sai. Unsigned32 có thể nâng sang long:

~~~java
long exactU32Sum = Integer.toUnsignedLong(maxU32) + 1;
// 4294967296.
~~~

Với unsigned64 cần tổng có thể vượt 2⁶⁴−1, dùng `BigInteger`. `Math.addExact` kiểm **signed overflow**, không phải phương thức “unsigned exact addition” cho mọi domain.

### Nhận biết carry khi cộng unsigned32

~~~java
int sum = a + b;
boolean carry = Integer.compareUnsigned(sum, a) < 0;
~~~

Đây là snippet bên trong method có raw `int a` và `int b`. Với **hai operand unsigned32**, phép cộng modulo đã wrap nếu `sum` nhỏ hơn `a` khi so unsigned. Dù có thể dùng carry bit, cách dễ đọc hơn khi miền cho phép là chuyển từng u32 sang `long` và cộng.

### Overflow signed cũng là một vấn đề riêng

~~~java
int signedWrapped = Integer.MAX_VALUE + 1;
// Integer.MIN_VALUE.

int unsignedWrapped = Integer.parseUnsignedInt("4294967295") + 1;
// raw 0; unsigned display "0".
~~~

Hai đoạn cho phép toán trên cùng kiểu `int` nhưng ý nghĩa domain khác nhau. Nếu không được tràn, phải chọn kiểu rộng hơn hoặc kiểm trước **trước khi ghi ra dữ liệu kết quả**.

## 11. `>>`, `>>>`, mask và bit width

- `>>`: dịch phải arithmetic, lặp lại bit dấu ở phía trái.
- `>>>`: dịch phải logical, điền 0 ở phía trái.
- `<<`: dịch trái, các bit vượt width bị loại.
- `&`: bitwise AND, hữu ích để mask lấy bit.

~~~java
int raw = -1;

int arithmetic = raw >> 1; // -1.
int logical = raw >>> 1;    // 2147483647.
~~~

Với `long raw = -1L`, `raw >>> 1` cho `Long.MAX_VALUE`. Nhưng `>>>` **không tạo primitive unsigned mới**, cũng không thay thế việc diễn giải nguyên 64 bit bằng `Long.toUnsignedString`.

### Tách bốn byte từ raw int

~~~java
int bits = 0xAABBCCDD;

int b0 = (bits >>> 24) & 0xFF; // 170.
int b1 = (bits >>> 16) & 0xFF; // 187.
int b2 = (bits >>>  8) & 0xFF; // 204.
int b3 = bits & 0xFF;          // 221.
~~~

Chú ý **shift count**: Java chỉ dùng 5 bit thấp của khoảng dịch trên `int` (tương đương modulo 32), 6 bit thấp cho `long` (modulo 64). Vì vậy `1 << 32` với int thực tế tương đương `1 << 0`, không phải một phép dịch sang ngoài 32 bit. Validate shift distance nếu đến từ input không tin cậy.

Bit shift không tự xác định endian của byte array. Endianness là quy tắc riêng của giao thức hoặc định dạng binary.

## 12. Đọc unsigned từ `byte[]` bằng `ByteBuffer`

Một field 32-bit unsigned big-endian:

~~~java
byte[] packet = {
        (byte) 0x80, (byte) 0x00, (byte) 0x00, (byte) 0x00
};

int raw = ByteBuffer.wrap(packet)
        .order(ByteOrder.BIG_ENDIAN)
        .getInt();

long positive = Integer.toUnsignedLong(raw);
// 2147483648.
~~~

`ByteBuffer.getInt()` trả **raw int signed**, vì Java không có uint32. `Integer.toUnsignedLong` mới diễn giải raw int thành số không âm.

Cùng dãy byte nhưng đọc bằng `ByteOrder.LITTLE_ENDIAN` sẽ tạo bit pattern khác. Đừng dùng native byte order của máy khi giao thức đã quy định endian. Tránh dùng `(int)byteValue` để mong nhận 255 từ byte 0xFF: cast sign-extends thành -1, `Byte.toUnsignedInt` mới trả 255.

### `BigInteger` và byte array

Constructor `new BigInteger(byte[])` diễn giải dãy byte theo **signed two's complement**. Nếu muốn một **unsigned magnitude big-endian**:

~~~java
byte[] bytes = {(byte) 0xFF, (byte) 0xFF};

BigInteger positive = new BigInteger(1, bytes);
// 65535.

BigInteger signed = new BigInteger(bytes);
// -1.
~~~

Constructor có `signum=1` là một API chuẩn đang hỗ trợ. Nếu nguồn dùng little-endian, phải chuyển byte order theo hợp đồng **trước** khi tạo BigInteger; không mặc định mọi mảng byte đều là big-endian.

## 13. `BigInteger`: số nguyên chính xác vượt signed long

Một `long` signed không thể có giá trị dương 18446744073709551615. Nếu bài toán thật sự cần **số dương và phép toán chính xác** cho toàn bộ unsigned64, dùng `java.math.BigInteger`:

~~~java
long raw = Long.parseUnsignedLong("18446744073709551615");
BigInteger value = new BigInteger(Long.toUnsignedString(raw));

BigInteger plusOne = value.add(BigInteger.ONE);
// 18446744073709551616.
~~~

**Không dùng `BigInteger.valueOf(raw)`** khi raw long có bit dấu 1 và bạn muốn unsigned:

~~~java
long raw = -1L;

BigInteger wrong = BigInteger.valueOf(raw); // -1.
BigInteger correct = new BigInteger(Long.toUnsignedString(raw));
// 18446744073709551615.
~~~

Một số `BigInteger` có thể lớn hơn cả unsigned64; nếu schema giới hạn đúng 64 bit, cần validate:

~~~java
BigInteger maxU64 = BigInteger.ONE.shiftLeft(64)
        .subtract(BigInteger.ONE);

BigInteger value = new BigInteger("18446744073709551615");
boolean valid = value.signum() >= 0
        && value.compareTo(maxU64) <= 0;
// true.
~~~

`longValue()` của BigInteger không là phép chuyển “luôn chính xác”: khi thu hẹp một số lớn, các bit cao bị loại, có thể cho long âm. Chỉ convert khi ý định là lấy **raw low 64 bits** hoặc đã validate trong signed range.

## 14. Integer/Long trong Collections, Stream và wrapper

`List<Integer>` hay `List<Long>` chứa wrapper của **signed primitives**; autoboxing không làm chúng thành unsigned. `Collections.sort`, `Integer.compareTo`, `Long.compareTo`, `IntStream.sorted` và `LongStream.sorted` dùng signed order trừ khi có comparator/chiến lược rõ.

~~~java
List<Integer> values =
        Arrays.asList(-1, 0, 1, Integer.MIN_VALUE);

List<Integer> ordered = new ArrayList<>(values);
ordered.sort(Integer::compareUnsigned);

String output = ordered.stream()
        .map(Integer::toUnsignedString)
        .collect(Collectors.joining(", "));
// 0, 1, 2147483648, 4294967295.
~~~

Muốn tìm max unsigned:

~~~java
Optional<Integer> maximum = values.stream()
        .max(Integer::compareUnsigned);
~~~

`Optional` có thể rỗng nếu nguồn rỗng. Không gọi `max(Comparator.naturalOrder())` rồi coi là unsigned. Với `TreeSet`/`TreeMap` có thể truyền comparator unsigned ngay lúc khởi tạo nếu business cần thứ tự đó.

Khi dùng wrapper, nhớ `Integer`/`Long` có thể là `null`. Comparator method reference không tự xử lý null; chọn null policy trước. Đối với dữ liệu lớn, tránh boxing không cần thiết, nhưng cũng đừng thay comparator unsigned bằng primitive sort signed khi nó đổi ngữ nghĩa.

## 15. Ranh giới parser và lỗi dữ liệu

~~~java
Integer.parseUnsignedInt("4294967295"); // hợp lệ.
Long.parseUnsignedLong("18446744073709551615"); // hợp lệ.

// Các giá trị dưới đây ném NumberFormatException:
// Integer.parseUnsignedInt("4294967296");
// Long.parseUnsignedLong("18446744073709551616");
// Integer.parseUnsignedInt("-1");
~~~

**Parse unsigned kiểm tra miền**, không tự overflow về modulo để nhận bất kỳ decimal nào. Đầu vào cần validation:

- Chuỗi null, rỗng, toàn khoảng trắng.
- Dấu âm, ký tự không thuộc radix, radix ngoài 2..36.
- Giá trị vượt max unsigned đúng 1 hoặc nhiều đơn vị.
- Dấu cộng ASCII, leading zeros và cách viết hoa/thường trong hex theo quy tắc format đã thống nhất.
- Đầu vào quá dài có thể tiêu tốn tài nguyên; đặt giới hạn theo schema trước khi parse.
- Một số phương thức parse dùng `Character.digit`; nếu giao thức chỉ cho phép chữ số **ASCII**, cần validate thêm, không suy parse tự động chứng minh input chỉ là ASCII.

### Hex với prefix 0x

~~~java
String input = "0xFFFFFFFF";

if (!input.startsWith("0x")) {
    throw new IllegalArgumentException("Expected 0x prefix");
}
int raw = Integer.parseUnsignedInt(input.substring(2), 16);
// raw = -1 theo signed, unsigned = 4294967295.
~~~

Đây là chính sách prefix của ứng dụng; Java không tự coi `0x` là chữ số trong overload `parseUnsignedInt(String,int)`. Nếu cần hỗ trợ `0X`, spaces hoặc prefix khác, hãy định nghĩa và validate chúng rõ ràng.

## 16. Dữ liệu API/JSON/database và tính chính xác

### Unsigned32 → long cho JSON numeric

Mọi unsigned32 vừa trong signed long:

~~~java
long positive = Integer.toUnsignedLong(rawUnsigned32);
~~~

Nếu backend và schema JSON/DB đồng ý miền 0..4294967295, đây là cách rõ ràng. Không xuất raw signed int âm khi client đòi unsigned32 decimal.

### Unsigned64 và JavaScript Number

Unsigned64 max 18446744073709551615 lớn hơn miền số nguyên chính xác thường dùng của **JavaScript Number** (tới 2⁵³−1). Nếu ID phải round-trip 100%, dùng schema decimal **string** hoặc cơ chế hỗ trợ big integers đã được cả client/server thống nhất:

~~~json
{"unsigned64Id":"18446744073709551615"}
~~~

Phía Java dùng `Long.toUnsignedString(raw)` để tạo value decimal chính xác. JSON number không tự bảo đảm rằng mọi JavaScript client giữ được toàn bộ 64 bit. Không tự thay type một field API đã được công bố mà không version/schema migration.

### Database driver

Tùy hệ quản trị, cột numeric có unsigned hay không và JDBC driver ánh xạ ra `long`/`BigDecimal`/`BigInteger`/String khác nhau. Không suy `ResultSet.getLong()` luôn chứa được **giá trị số dương unsigned64** đầy đủ. Đọc schema/driver contract và test các giá trị biên cụ thể.

### Đừng “chữa” số âm bằng unsigned khi domain thật sự signed

Một tài khoản có số dư `-1` theo nghĩa thiếu tiền không phải unsigned max. Nếu gọi `Long.toUnsignedString(-1)`, kết quả 18446744073709551615 sẽ **che lỗi hoặc đảo nghĩa nghiệp vụ**. Chỉ diễn giải unsigned khi trường nguồn **được đặc tả là unsigned**.

## 17. Ứng dụng: checksum, sequence và giao thức nhị phân

- Một CRC32 là giá trị 32-bit không dấu về mặt thuật toán. `java.util.zip.CRC32.getValue()` trả `long` không âm trong miền 0..4294967295. Nếu nhận 4 byte raw vào `int`, `Integer.toUnsignedLong` giúp xuất decimal đúng.
- CRC32 là mã kiểm tra lỗi tình cờ, **không phải cơ chế xác thực mật mã**. Không dùng nó thay hash bảo mật/MAC/chữ ký.
- Với sequence có vòng quay modulo 2³² hoặc 2⁶⁴, `compareUnsigned` cho thứ tự số học nhưng không tự xác định bản ghi “mới hơn” khi qua điểm wrap; cần quy tắc giao thức.
- Với bit field từ network, byte order và mask phải theo protocol. Không dùng số unsigned làm offset/length để cấp phát trước khi kiểm tra miền và kích thước.
- Nếu một ID chỉ mang nghĩa **định danh opaque**, có thể dùng decimal String đã validate thay vì làm arithmetic không cần thiết.

## 18. Chương trình Java độc lập, có kiểm chứng

Tạo file **`UnsignedIntegerDemo.java`**. Mã chỉ dùng API có từ Java 8, có dữ liệu cố định, không phụ thuộc đồng hồ hay locale. Chương trình kiểm thử raw bit patterns, unsigned parsing/formatting, zero extension, unsigned sorting, phép chia dư, BigInteger, byte order, phép dịch và overflow.

~~~java
import java.math.BigInteger;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.*;
import java.util.stream.Collectors;

public final class UnsignedIntegerDemo {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        int u32 = Integer.parseUnsignedInt("4294967295");
        int high32 = Integer.parseUnsignedInt("80000000", 16);
        long u64 = Long.parseUnsignedLong("18446744073709551615");
        long high64 = Long.parseUnsignedLong("9223372036854775808");

        System.out.println("int signed: " + u32);
        System.out.println("int unsigned: " + Integer.toUnsignedString(u32));
        System.out.println("int toUnsignedLong: " + Integer.toUnsignedLong(u32));
        System.out.println("int cast to long: " + (long) u32);
        System.out.println("int unsigned hex: " + Integer.toUnsignedString(u32, 16));
        System.out.println("int high-bit signed: " + high32);
        System.out.println("int high-bit unsigned: " + Integer.toUnsignedString(high32));

        System.out.println("int signed compare(-1,1): " + Integer.compare(-1, 1));
        System.out.println("int unsigned compare(-1,1): " + Integer.compareUnsigned(-1, 1));
        System.out.println("int unsigned /10: " + Integer.divideUnsigned(u32, 10));
        System.out.println("int unsigned %10: " + Integer.remainderUnsigned(u32, 10));

        System.out.println("long signed: " + u64);
        System.out.println("long unsigned: " + Long.toUnsignedString(u64));
        System.out.println("long unsigned hex: " + Long.toUnsignedString(u64, 16));
        System.out.println("long high-bit signed: " + high64);
        System.out.println("long high-bit unsigned: " + Long.toUnsignedString(high64));
        System.out.println("long unsigned compare(-1,1): " + Long.compareUnsigned(-1L, 1L));
        System.out.println("long unsigned /10: " + Long.divideUnsigned(u64, 10L));
        System.out.println("long unsigned %10: " + Long.remainderUnsigned(u64, 10L));

        BigInteger unsigned64 = new BigInteger(Long.toUnsignedString(u64));
        BigInteger unsigned64Bytes = new BigInteger(1,
                new byte[] {-1,-1,-1,-1,-1,-1,-1,-1});
        BigInteger signed64Bytes = new BigInteger(
                new byte[] {-1,-1,-1,-1,-1,-1,-1,-1});
        System.out.println("unsigned long as BigInteger: " + unsigned64);
        System.out.println("unsigned byte array: " + unsigned64Bytes);
        System.out.println("signed byte array: " + signed64Bytes);

        System.out.println("byte unsigned: " + Byte.toUnsignedInt((byte) -1));
        System.out.println("short unsigned: " + Short.toUnsignedInt((short) -1));
        int fromNetwork = ByteBuffer.wrap(
                new byte[] {(byte) 0x80, 0, 0, 0})
                .order(ByteOrder.BIG_ENDIAN).getInt();
        System.out.println("network u32: " + Integer.toUnsignedLong(fromNetwork));

        System.out.println("arithmetic right shift: " + (-1 >> 1));
        System.out.println("logical right shift: " + (-1 >>> 1));

        List<Integer> values = new ArrayList<>(Arrays.asList(
                -1, 0, 1, Integer.MIN_VALUE));
        values.sort(Integer::compareUnsigned);
        String sorted = values.stream()
                .map(Integer::toUnsignedString)
                .collect(Collectors.joining(", "));
        System.out.println("unsigned sorted: [" + sorted + "]");

        int wrappedU32 = u32 + 1;
        BigInteger exactU32PlusOne = BigInteger.valueOf(
                Integer.toUnsignedLong(u32)).add(BigInteger.ONE);
        System.out.println("u32 wrapped +1: " + Integer.toUnsignedString(wrappedU32));
        System.out.println("u32 exact +1: " + exactU32PlusOne);

        boolean rejected32 = false;
        boolean rejected64 = false;
        boolean rejectedNegative = false;
        boolean signedOverflow = false;
        try {
            Integer.parseUnsignedInt("4294967296");
        } catch (NumberFormatException ex) {
            rejected32 = true;
        }
        try {
            Long.parseUnsignedLong("18446744073709551616");
        } catch (NumberFormatException ex) {
            rejected64 = true;
        }
        try {
            Integer.parseUnsignedInt("-1");
        } catch (NumberFormatException ex) {
            rejectedNegative = true;
        }
        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            signedOverflow = true;
        }
        System.out.println("out of range u32 rejected: " + rejected32);
        System.out.println("out of range u64 rejected: " + rejected64);
        System.out.println("negative text rejected: " + rejectedNegative);
        System.out.println("signed addExact overflow: " + signedOverflow);

        check(u32 == -1 && high32 == Integer.MIN_VALUE, "u32 bit pattern");
        check(Integer.toUnsignedLong(u32) == 4294967295L, "zero extend");
        check(Integer.compareUnsigned(-1, 1) > 0, "u32 compare");
        check(Integer.divideUnsigned(u32, 10) == 429496729, "u32 quotient");
        check(Integer.remainderUnsigned(u32, 10) == 5, "u32 remainder");
        check(u64 == -1L && high64 == Long.MIN_VALUE, "u64 bit pattern");
        check(Long.compareUnsigned(u64, 1L) > 0, "u64 compare");
        check(Long.divideUnsigned(u64, 10L) == 1844674407370955161L,
                "u64 quotient");
        check(Long.remainderUnsigned(u64, 10L) == 5L, "u64 remainder");
        check(unsigned64.equals(unsigned64Bytes), "big integer magnitude");
        check(signed64Bytes.equals(BigInteger.valueOf(-1L)), "signed bytes");
        check(sorted.equals("0, 1, 2147483648, 4294967295"), "sorting");
        check(fromNetwork == Integer.MIN_VALUE, "network raw value");
        check(wrappedU32 == 0 && exactU32PlusOne.equals(
                new BigInteger("4294967296")), "overflow");
        check(rejected32 && rejected64 && rejectedNegative && signedOverflow,
                "boundary checks");
        System.out.println("all checks passed");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 UnsignedIntegerDemo.java
java UnsignedIntegerDemo
~~~

**Stdout đầy đủ đã kiểm tra:**

~~~text
int signed: -1
int unsigned: 4294967295
int toUnsignedLong: 4294967295
int cast to long: -1
int unsigned hex: ffffffff
int high-bit signed: -2147483648
int high-bit unsigned: 2147483648
int signed compare(-1,1): -1
int unsigned compare(-1,1): 1
int unsigned /10: 429496729
int unsigned %10: 5
long signed: -1
long unsigned: 18446744073709551615
long unsigned hex: ffffffffffffffff
long high-bit signed: -9223372036854775808
long high-bit unsigned: 9223372036854775808
long unsigned compare(-1,1): 1
long unsigned /10: 1844674407370955161
long unsigned %10: 5
unsigned long as BigInteger: 18446744073709551615
unsigned byte array: 18446744073709551615
signed byte array: -1
byte unsigned: 255
short unsigned: 65535
network u32: 2147483648
arithmetic right shift: -1
logical right shift: 2147483647
unsigned sorted: [0, 1, 2147483648, 4294967295]
u32 wrapped +1: 0
u32 exact +1: 4294967296
out of range u32 rejected: true
out of range u64 rejected: true
negative text rejected: true
signed addExact overflow: true
all checks passed
~~~

### Đọc kết quả demo theo nhóm

1. `int signed` và `int unsigned` cho -1 và 4294967295 từ cùng bit pattern. Cast `(long)raw` giữ -1, còn `toUnsignedLong` zero-extend để được số dương đúng.
2. Với `80000000` hex, raw int là `Integer.MIN_VALUE`, nhưng unsigned là 2147483648.
3. `compareUnsigned(-1,1)` dương, trong khi signed compare âm; thương và dư của max32 chia 10 là 429496729 và 5.
4. Raw long -1 tương ứng unsigned64 max; `BigInteger` được xây từ unsigned decimal string và từ unsigned magnitude bytes đều cho đúng 18446744073709551615, nhưng constructor signed byte[] trả -1.
5. Byte `0xFF` cho 255 và short `0xFFFF` cho 65535 nhờ zero extension.
6. Bốn byte `80 00 00 00` big-endian có raw int âm nhưng unsigned long 2147483648.
7. Dịch phải signed và logical khác nhau; sort dùng comparator unsigned đặt các bit pattern đúng thứ tự 0, 1, 2147483648, 4294967295.
8. Unsigned32 max + 1 wrap về 0 trong raw int, nhưng `BigInteger` giữ tổng chính xác 4294967296.
9. Parser từ chối giá trị quá cận, input âm và phép `Math.addExact` phát hiện signed overflow. `all checks passed` chỉ xuất hiện sau khi **15 phép check** đều thành công.

## 19. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cho rằng Java có primitive `uint`/`ulong` | Không biên dịch | `int`/`long` raw + helper unsigned |
| Dùng `Integer.toString(-1)` để in u32 | In `-1` thay vì 4294967295 | `Integer.toUnsignedString` |
| Dùng `Long.toString(-1L)` để in u64 | In `-1` thay vì 18446744073709551615 | `Long.toUnsignedString` |
| Dùng `parseInt` để đọc unsigned32 max | `NumberFormatException` | `parseUnsignedInt` |
| Dùng `parseLong` để đọc unsigned64 max | `NumberFormatException` | `parseUnsignedLong` |
| Nghĩ kết quả `parseUnsignedLong` luôn dương signed | Raw long có thể âm | `toUnsignedString`/`BigInteger` |
| Cast raw int trực tiếp sang long để lấy unsigned32 | Sign-extension | `Integer.toUnsignedLong` |
| Dùng `BigInteger.valueOf(rawLong)` cho u64 có high bit 1 | Nhận số âm | Từ `Long.toUnsignedString` |
| Dùng `new BigInteger(bytes)` cho unsigned magnitude | Bit đầu có thể bị hiểu dấu âm | `new BigInteger(1,bytes)` |
| So sánh bằng `<` hoặc natural order | So signed | `compareUnsigned` |
| Dùng `Collections.sort` mặc định cho u32 raw | Thứ tự signed sai | Comparator unsigned |
| Chia `raw / 10` trên raw số âm | Chia signed | `divideUnsigned` |
| Lấy `raw % 10` cho unsigned raw âm | Phần dư signed | `remainderUnsigned` |
| Nghĩ thương unsigned luôn dương khi in trực tiếp | Thương raw có thể có bit dấu | `toUnsignedString(quotient)` |
| Coi `Math.addExact` là bộ kiểm tra unsigned overflow | Chỉ signed overflow | Kiểu đủ rộng hoặc carry/BigInteger |
| Dùng `>>>` rồi coi đó là biểu diễn unsigned đầy đủ | Chỉ dịch bit trên width cũ | `toUnsignedString` khi format |
| Quên quy tắc shift count modulo width | `1 << 32` khác kỳ vọng | Validate số bit dịch |
| Không kiểm byte order | Binary value bị đọc sai | `ByteOrder` theo protocol |
| Cast byte `0xFF` sang int rồi mong 255 | Nhận -1 | `Byte.toUnsignedInt` |
| Dùng `Byte.compareUnsigned` trong code Java 8 | Method từ Java 9 | Widen sang int rồi compare |
| Parse chuỗi `"-1"` bằng unsigned parser | `NumberFormatException` | Dùng unsigned decimal string |
| Parse quá cận rồi cast hẹp | Mất bit mà không báo lỗi | Parse và validate đúng width |
| Gửi unsigned64 max như JSON number cho JS Number | Có thể mất precision | Schema decimal string hoặc big-int-aware |
| Giả định comparator unsigned xử lý sequence wrap | Không xác định “mới hơn” theo vòng | Logic wrap-aware |
| Dùng unsigned để che dữ liệu âm lỗi | Đổi nghĩa domain | Chỉ unsigned khi schema xác nhận |
| In debug signed rồi suy rằng raw bits sai | Dữ liệu bit vẫn có thể đúng | Hiển thị cả signed, hex và unsigned |

## 20. Bài tập có đáp án

### Bài 1 — Một int, hai cách nhìn

`int raw = -1;` có signed/unsigned decimal gì?

**Đáp án:** `-1` và `4294967295`. Bit pattern là `0xFFFFFFFF`.

### Bài 2 — Parse max u32 rồi chuyển sang long

~~~java
int raw = Integer.parseUnsignedInt("4294967295");
long positive = Integer.toUnsignedLong(raw);
// positive = 4294967295.
~~~

Dùng cast `(long)raw` thì ra -1 vì sign-extension.

### Bài 3 — High bit

`Integer.parseUnsignedInt("80000000",16)` trả raw và unsigned gì?

**Đáp án:** Raw -2147483648; unsigned 2147483648.

### Bài 4 — So sánh -1 và 1

**Đáp án:** `Integer.compare(-1,1) < 0`, còn `Integer.compareUnsigned(-1,1) > 0`.

### Bài 5 — Chia unsigned32 max cho 10

**Đáp án:** `Integer.divideUnsigned(raw,10) = 429496729`; `Integer.remainderUnsigned(raw,10) = 5`.

### Bài 6 — Đọc unsigned64 max

**Đáp án:** `Long.parseUnsignedLong("18446744073709551615")` trả raw -1; `Long.toUnsignedString(raw)` tạo decimal gốc chính xác.

### Bài 7 — Cộng 1 mà không wrap

~~~java
long raw = Long.parseUnsignedLong("18446744073709551615");
BigInteger value = new BigInteger(Long.toUnsignedString(raw));
BigInteger exact = value.add(BigInteger.ONE);
// 18446744073709551616.
~~~

### Bài 8 — Byte 0xFF

**Đáp án:** `(int)((byte)0xFF)` là -1; `Byte.toUnsignedInt((byte)0xFF)` là 255.

### Bài 9 — Dịch bit

**Đáp án:** `-1 >> 1` cho -1; `-1 >>> 1` cho 2147483647.

### Bài 10 — Sắp xếp u32

List raw `[-1,0,1,Integer.MIN_VALUE]` sort unsigned thành dãy decimal **0, 1, 2147483648, 4294967295**.

~~~java
list.sort(Integer::compareUnsigned);
~~~

### Bài 11 — Overflow u32

`Integer.toUnsignedString(Integer.parseUnsignedInt("4294967295") + 1)` là gì?

**Đáp án:** `"0"` vì wrap modulo 2³². Nếu cần chính xác, chuyển sang long trước khi cộng.

### Bài 12 — Đọc network bytes

Dãy big-endian `80 00 00 00` là unsigned bao nhiêu?

**Đáp án:** Raw `Integer.MIN_VALUE`, sau `Integer.toUnsignedLong` bằng 2147483648.

### Bài 13 — JSON và unsigned64 max

**Đáp án:** Nếu client dùng JavaScript Number và cần round-trip chính xác, nên thống nhất decimal string trong schema thay vì dựa vào JSON number cực lớn.

### Bài 14 — Range validation

`Integer.parseUnsignedInt("4294967296")` và `Long.parseUnsignedLong("18446744073709551616")` trả gì?

**Đáp án:** Cả hai ném `NumberFormatException`, không wrap.

### Bài 15 — Sequence number wrap

Sau u32 max, sequence về 0. `compareUnsigned` có biết 0 “mới hơn” không?

**Đáp án:** Không. Đó là quy tắc vòng của giao thức, không phải unsigned numeric comparison.

## 21. Checklist khi đưa vào production

- [ ] Schema có xác định trường thực sự là u8/u16/u32/u64 không?
- [ ] Đã phân biệt raw bits, signed view, unsigned view và số học exact?
- [ ] Parse bằng `parseUnsignedInt/Long` đúng width và radix?
- [ ] Đã test min, max, high bit, bit toàn 1 và input vượt cận?
- [ ] Output decimal unsigned có dùng `toUnsignedString`?
- [ ] U32 → long có dùng `Integer.toUnsignedLong` thay vì cast?
- [ ] Byte/short raw có zero-extend đúng nghĩa?
- [ ] Unsigned64 lớn đã dùng `BigInteger` khi cần giá trị dương exact?
- [ ] Byte array unsigned dùng constructor magnitude với signum dương và endian đúng?
- [ ] Comparator sort/min/max dùng unsigned khi domain yêu cầu?
- [ ] Chia/phần dư dùng `divideUnsigned` và `remainderUnsigned`?
- [ ] Quotient raw có được format lại unsigned khi hiển thị?
- [ ] Overflow unsigned được phép wrap hay phải báo lỗi?
- [ ] `Math.addExact` có được hiểu đúng là signed overflow checker?
- [ ] Shift `>>`, `>>>` và mask đã được review bit width/shift distance?
- [ ] `ByteBuffer` dùng byte order theo protocol?
- [ ] API/JSON/DB có giữ chính xác unsigned64 và thống nhất schema với consumer?
- [ ] Nếu sequence wrap, đã có thuật toán wrap-aware?
- [ ] Không biến dữ liệu signed âm hợp lệ hoặc lỗi thành unsigned cực lớn ngoài ý định?
- [ ] API được dùng có từ đúng version Java mà dự án hỗ trợ?
- [ ] Chương trình mẫu và stdout đã được biên dịch/chạy kiểm chứng?

**Kết luận:** `Integer` và `Long` không cung cấp primitive unsigned mới; chúng giúp **diễn giải cùng bit pattern** theo đúng nghĩa dữ liệu. `parseUnsigned...` kiểm range văn bản; `toUnsignedString` in giá trị dương đầy đủ; `compareUnsigned`, `divideUnsigned` và `remainderUnsigned` làm phép toán không dấu. `Integer.toUnsignedLong` chuyển trọn u32 sang số long không âm; `BigInteger` cần thiết cho số học exact trên miền unsigned64 lớn. Điều quan trọng là giữ **một quy ước signed/unsigned nhất quán từ parser đến database và output**.

### Tài liệu Oracle chính thức còn được duy trì

- [`Integer` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Integer.html): `parseUnsignedInt`, `toUnsignedString`, `toUnsignedLong`, `compareUnsigned`, `divideUnsigned`, `remainderUnsigned`.
- [`Long` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Long.html): `parseUnsignedLong`, `toUnsignedString`, `compareUnsigned` và phép chia dư unsigned.
- [`Byte` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Byte.html): `Byte.toUnsignedInt` và `Byte.toUnsignedLong`.
- [`Short` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Short.html): `Short.toUnsignedInt` và `Short.toUnsignedLong`.
- [`BigInteger` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigInteger.html): arbitrary-precision integers, positive magnitude constructor.
- [`ByteBuffer` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/ByteBuffer.html): đọc binary theo byte order.
