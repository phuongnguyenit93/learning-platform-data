# Chuyển mẫu bit trở lại giá trị `float` hoặc `double` trong Java

## 1. Hai việc khác nhau: đổi giá trị số và diễn giải lại bit

Một giá trị dấu phẩy động (*floating-point*) có thể được lưu dưới dạng mẫu bit theo IEEE 754. Để phục hồi **giá trị `float` hoặc `double` từ chính mẫu bit đó**, Java cung cấp hai phương thức:

- `Float.intBitsToFloat(int bits)`: xem 32 bit của một `int` như biểu diễn nhị phân của một `float`.
- `Double.longBitsToDouble(long bits)`: xem 64 bit của một `long` như biểu diễn nhị phân của một `double`.

Điểm quan trọng nhất: **diễn giải lại mẫu bit khác hoàn toàn với ép kiểu số học**.

```java
int bits = 0x3F80_0000; // 1065353216 nếu hiểu là int có dấu
float reconstructed = Float.intBitsToFloat(bits); // 1.0f
float converted = (float) bits; // giá trị số 1065353216 được đổi sang float
```

`Float.intBitsToFloat` lấy nguyên mẫu 32 bit `0x3F800000` và diễn giải theo IEEE 754, thu được **1.0**. Trong khi đó, `(float) bits` chuyển **giá trị số nguyên** 1_065_353_216 sang kiểu `float`. Hai phép toán có ý nghĩa khác nhau dù cùng xuất phát từ một biến `int`.

Đối với 64 bit, `Double.longBitsToDouble(bits)` khác `(double) bits` tương tự. Khi xử lý file nhị phân, giao thức mạng, log hex, kiểm thử hoặc phân tích bit, cần xác định dữ liệu đang là **bit pattern** hay **giá trị số nguyên cần chuyển đổi**.

## 2. Những API cần biết

| Mục đích | API Java | Kiểu đầu vào | Kiểu trả về |
|---|---|---|---|
| Bit pattern → `float` | `Float.intBitsToFloat(bits)` | `int`, 32 bit | `float` |
| Bit pattern → `double` | `Double.longBitsToDouble(bits)` | `long`, 64 bit | `double` |
| `float` → bit pattern nguyên bản | `Float.floatToRawIntBits(value)` | `float` | `int` |
| `double` → bit pattern nguyên bản | `Double.doubleToRawLongBits(value)` | `double` | `long` |
| `float` → bit pattern chuẩn hóa NaN | `Float.floatToIntBits(value)` | `float` | `int` |
| `double` → bit pattern chuẩn hóa NaN | `Double.doubleToLongBits(value)` | `double` | `long` |

Các phương thức `intBitsToFloat` và `longBitsToDouble` là `static`, có thể gọi trực tiếp từ tên lớp bao mà không tạo đối tượng `Float`/`Double`.

**Phân biệt hai họ phương thức đi từ giá trị sang bit:** phương thức có chữ `Raw` cố gắng trả về mẫu bit thực tế của giá trị, kể cả thông tin payload NaN khi biểu diễn cho phép. Phương thức không có `Raw` chuẩn hóa mọi NaN thành một mẫu NaN chuẩn:

- `Float.floatToIntBits(Float.NaN)` trả `0x7FC00000`.
- `Double.doubleToLongBits(Double.NaN)` trả `0x7FF8000000000000L`.

Vì NaN có nhiều biểu diễn bit, không nên mặc định một phép đi-về sẽ giữ **mọi bit NaN** trong mọi tình huống; phần này được giải thích kỹ hơn ở mục 7.

## 3. Cấu trúc biểu diễn IEEE 754 binary32 và binary64

Java `float` dùng **binary32**, còn `double` dùng **binary64** của IEEE 754:

| Thành phần | `float` (32 bit) | `double` (64 bit) |
|---|---:|---:|
| Bit dấu (*sign*) | 1 | 1 |
| Số bit số mũ (*exponent*) | 8 | 11 |
| Số bit phần phân số (*fraction/significand field*) | 23 | 52 |
| Độ lệch số mũ (*bias*) | 127 | 1023 |
| Tổng | 32 | 64 |

Cách bố trí từ bit cao xuống bit thấp:

```text
float (32 bit):
S | EEEEEEEE | FFFFFFFFFFFFFFFFFFFFFFF
1 |    8     |           23

double (64 bit):
S | EEEEEEEEEEE | FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
1 |     11      |                         52
```

Ở đây:

- **S**: dấu, bằng 0 khi số không âm và bằng 1 khi số âm.
- **E**: trường số mũ được lưu có độ lệch (*biased exponent*).
- **F**: trường phân số, lưu các bit sau dấu chấm của phần trị; số chuẩn hóa có **bit 1 ẩn** đứng trước phần phân số.

Với số **chuẩn hóa** (*normal*) có trường số mũ nằm giữa 0 và giá trị toàn bit 1, giá trị toán học là:

\[
(-1)^S \times \left(1+\frac{F}{2^p}\right) \times 2^{E-\text{bias}}
\]

Trong đó `p = 23` cho `float`, `p = 52` cho `double`, còn `F` là số nguyên không dấu do các bit phần phân số biểu diễn.

Với trường số mũ bằng **0**, công thức đổi thành số **dưới chuẩn** (*subnormal*) khi `F != 0`:

\[
(-1)^S \times \frac{F}{2^p} \times 2^{1-\text{bias}}
\]

Nếu `E = 0` và `F = 0`, kết quả là **+0.0 hoặc -0.0**, tùy bit dấu. Nếu `E` gồm toàn bit 1, cách diễn giải đặc biệt được mô tả ở mục 6: **vô cực** hoặc **NaN**.

**Lưu ý:** không phải mọi mẫu 32/64 bit đều biểu diễn một số thực hữu hạn. Mọi mẫu đều có thể được diễn giải bằng API, nhưng kết quả có thể là số hữu hạn, ±0.0, ±Infinity hoặc NaN.

## 4. Phân tích một mẫu bit `float` cụ thể

Xét `0x40400000`, gồm 32 bit:

```text
Hex:     0x40400000
Binary:  01000000 01000000 00000000 00000000
Fields:  0 | 10000000 | 10000000000000000000000
         S |     E    |           F
```

Tính theo từng trường:

1. Bit dấu `S = 0`, nên kết quả dương.
2. Trường số mũ nhị phân `10000000` bằng 128, số mũ thực là \(128 - 127 = 1\).
3. Phần phân số có bit đầu là 1 và còn lại là 0, nên \(F/2^{23} = 1/2\).
4. Phần trị chuẩn hóa là \(1 + 1/2 = 1.5\).
5. Giá trị cuối: \(1.5 \times 2^1 = 3.0\).

Trong Java:

```java
float value = Float.intBitsToFloat(0x4040_0000);
System.out.println(value); // 3.0
```

Đổi bit dấu thành 1 mà giữ nguyên số mũ và phân số cho `0xC0400000`, được **-3.0**:

```java
float negative = Float.intBitsToFloat(0xC040_0000);
System.out.println(negative); // -3.0
```

Đối với `double`, mẫu `0x4008000000000000L` cũng biểu diễn 3.0, nhưng phân bố bit và độ lệch số mũ khác:

```java
double d = Double.longBitsToDouble(0x4008_0000_0000_0000L);
System.out.println(d); // 3.0
```

Có thể thấy **giá trị số 3.0 có bit pattern khác nhau** trong `float` và `double`. Không thể đưa trực tiếp mẫu 32 bit dành cho `float` vào `Double.longBitsToDouble` rồi kỳ vọng lấy đúng cùng giá trị.

## 5. Ví dụ Java 17+: phục hồi giá trị từ mẫu bit

Tạo tệp `BitsToFloatingDemo.java`:

```java
public class BitsToFloatingDemo {
    public static void main(String[] args) {
        int oneBits = 0x3F80_0000;
        int threeBits = 0x4040_0000;
        int minusThreeBits = 0xC040_0000;
        long doubleThreeBits = 0x4008_0000_0000_0000L;

        System.out.println("float 1 = "
                + Float.intBitsToFloat(oneBits));
        System.out.println("float 3 = "
                + Float.intBitsToFloat(threeBits));
        System.out.println("float -3 = "
                + Float.intBitsToFloat(minusThreeBits));
        System.out.println("double 3 = "
                + Double.longBitsToDouble(doubleThreeBits));

        float reconstructed = Float.intBitsToFloat(oneBits);
        float numericCast = (float) oneBits;
        System.out.println("same as numeric cast? "
                + (reconstructed == numericCast));

        int recovered = Float.floatToRawIntBits(reconstructed);
        System.out.printf("recovered float bits = %08X%n", recovered);

        double pi = Double.longBitsToDouble(
                0x4009_21FB_5444_2D18L);
        System.out.println("double pi = " + pi);
        System.out.printf("double pi bits = %016X%n",
                Double.doubleToRawLongBits(pi));
    }
}
```

Biên dịch và chạy:

```bash
javac BitsToFloatingDemo.java
java BitsToFloatingDemo
```

Kết quả:

```text
float 1 = 1.0
float 3 = 3.0
float -3 = -3.0
double 3 = 3.0
same as numeric cast? false
recovered float bits = 3F800000
double pi = 3.141592653589793
double pi bits = 400921FB54442D18
```

Giá trị π ở đây là **xấp xỉ binary64 gần nhất**, không phải π toán học vô hạn chữ số. Dòng in bit cho thấy mẫu binary64 đã được phục hồi từ một giá trị hữu hạn bình thường.

## 6. Các mẫu đặc biệt: ±0.0, số dưới chuẩn, ±Infinity và NaN

Dịch nghĩa trường số mũ và phần phân số:

| Trường số mũ E | Phân số F | Giá trị |
|---|---|---|
| 0 | 0 | +0.0 hoặc -0.0 theo bit dấu |
| 0 | khác 0 | Số dưới chuẩn (*subnormal*) |
| Từ 1 đến giá trị gần toàn-1 | Bất kỳ | Số chuẩn hóa hữu hạn |
| Toàn-1 | 0 | +Infinity hoặc -Infinity |
| Toàn-1 | khác 0 | NaN (*Not a Number*) |

### 6.1. Các mẫu `float` quen thuộc

| Mẫu 32 bit | Ý nghĩa |
|---|---|
| `0x00000000` | +0.0f |
| `0x80000000` | -0.0f |
| `0x00000001` | Số dưới chuẩn dương nhỏ nhất |
| `0x00800000` | Số chuẩn hóa dương nhỏ nhất |
| `0x3F800000` | 1.0f |
| `0x7F800000` | +Infinity |
| `0xFF800000` | -Infinity |
| `0x7FC00000` | NaN chuẩn |

### 6.2. Các mẫu `double` tương ứng

| Mẫu 64 bit | Ý nghĩa |
|---|---|
| `0x0000000000000000L` | +0.0 |
| `0x8000000000000000L` | -0.0 |
| `0x0000000000000001L` | Số dưới chuẩn dương nhỏ nhất |
| `0x0010000000000000L` | Số chuẩn hóa dương nhỏ nhất |
| `0x3FF0000000000000L` | 1.0 |
| `0x7FF0000000000000L` | +Infinity |
| `0xFFF0000000000000L` | -Infinity |
| `0x7FF8000000000000L` | NaN chuẩn |

Dạng hex có hậu tố `L` là literal `long`, kể cả khi bit cao nhất là 1 khiến giá trị `long` mang dấu âm. `Double.longBitsToDouble` **chỉ xét toàn bộ 64 bit**, không coi giá trị số `long` âm là yêu cầu trả `double` âm. Dấu `double` được xác định từ bit dấu của chính mẫu IEEE 754.

### 6.3. Hai số 0 có cùng so sánh số học nhưng khác mẫu bit

```java
float plusZero = Float.intBitsToFloat(0x0000_0000);
float minusZero = Float.intBitsToFloat(0x8000_0000);

System.out.println(plusZero == minusZero); // true
System.out.println(1.0f / plusZero);       // Infinity
System.out.println(1.0f / minusZero);      // -Infinity
```

Dù `+0.0f == -0.0f` là `true` theo toán tử số học, bit pattern của chúng **không giống nhau**. Điều này quan trọng khi serialize chính xác, ký số theo byte, debug số học hoặc nghiên cứu dấu của giá trị 0.

### 6.4. Phân biệt NaN qua phép kiểm tra

`NaN` là kết quả không phải số, ví dụ `0.0 / 0.0` trong số học dấu phẩy động. Java có các phương thức:

- `Float.isNaN(value)` hoặc `Double.isNaN(value)`.
- `Float.isInfinite(value)` hoặc `Double.isInfinite(value)`.
- `Float.isFinite(value)` hoặc `Double.isFinite(value)`.

Một mẫu có số mũ toàn-1 và phân số khác 0 là NaN, bất kể bit dấu là 0 hay 1. Các bit phân số có thể chứa *NaN payload*, nhưng không nên coi đó là dữ liệu số bình thường.

## 7. Round-trip và vấn đề NaN payload

Với giá trị hữu hạn, ±0.0 và ±Infinity, hai phép chuyển đổi thường cho phép kiểm tra bit nguyên bản chính xác:

```java
int bits = 0xBF80_0000; // mẫu float -1.0
float value = Float.intBitsToFloat(bits);
int back = Float.floatToRawIntBits(value);

System.out.println(back == bits); // true
```

Với NaN, phải phân biệt **giá trị được phân loại là NaN** với **mọi bit payload có được bảo toàn không**:

1. `Float.intBitsToFloat(bits)` và `Double.longBitsToDouble(bits)` diễn giải mẫu bit theo IEEE 754.
2. `Float.floatToIntBits(value)` và `Double.doubleToLongBits(value)` **chuẩn hóa NaN** về một mẫu NaN chuẩn; không giữ payload gốc.
3. `floatToRawIntBits` và `doubleToRawLongBits` dành cho việc đọc bit nguyên bản đang có. Tuy vậy, một số cấu trúc phần cứng hoặc thao tác có thể **quiet** một *signaling NaN* khi mẫu bit được chuyển thành giá trị floating-point. Không thể cam kết bit-perfect round-trip cho **mọi mẫu NaN báo hiệu** trên mọi môi trường thực thi.

Bởi vậy, nếu mục tiêu là **lưu/truyền payload bit đúng tuyệt đối**, ví dụ lưu file nhị phân với một payload NaN cụ thể, giải pháp chắc chắn nhất là **giữ mẫu gốc ở `int`/`long` hoặc mảng byte** trong suốt quá trình truyền; chỉ gọi `intBitsToFloat` hoặc `longBitsToDouble` khi thực sự cần tính toán trên giá trị số.

Nếu mục tiêu chỉ là kiểm tra dữ liệu có phải NaN hay không, dùng `isNaN`; không cần so trực tiếp bit với một mẫu NaN duy nhất. Phép so sánh `NaN == NaN` cho `false` theo quy tắc dấu phẩy động.

### Ví dụ runnable cho NaN và zero

Lưu file `SpecialFloatingBitsDemo.java`:

```java
public class SpecialFloatingBitsDemo {
    public static void main(String[] args) {
        float plusZero = Float.intBitsToFloat(0x0000_0000);
        float minusZero = Float.intBitsToFloat(0x8000_0000);
        float plusInfinity = Float.intBitsToFloat(0x7F80_0000);
        float minusInfinity = Float.intBitsToFloat(0xFF80_0000);
        float nan = Float.intBitsToFloat(0x7FC0_0000);

        System.out.println("zeros equal = " + (plusZero == minusZero));
        System.out.printf("plus zero bits = %08X%n",
                Float.floatToRawIntBits(plusZero));
        System.out.printf("minus zero bits = %08X%n",
                Float.floatToRawIntBits(minusZero));
        System.out.println("1 / +0 = " + (1.0f / plusZero));
        System.out.println("1 / -0 = " + (1.0f / minusZero));
        System.out.println("positive infinity = " + plusInfinity);
        System.out.println("negative infinity = " + minusInfinity);
        System.out.println("is NaN = " + Float.isNaN(nan));
        System.out.println("NaN == NaN = " + (nan == nan));
        System.out.printf("canonical NaN bits = %08X%n",
                Float.floatToIntBits(nan));

        double tiny = Double.longBitsToDouble(1L);
        System.out.println("double smallest positive = " + tiny);
    }
}
```

Biên dịch và chạy:

```bash
javac SpecialFloatingBitsDemo.java
java SpecialFloatingBitsDemo
```

Kết quả:

```text
zeros equal = true
plus zero bits = 00000000
minus zero bits = 80000000
1 / +0 = Infinity
1 / -0 = -Infinity
positive infinity = Infinity
negative infinity = -Infinity
is NaN = true
NaN == NaN = false
canonical NaN bits = 7FC00000
double smallest positive = 4.9E-324
```

Mẫu `0x7FC00000` được dùng ở ví dụ là NaN chuẩn, nên kết quả của `floatToIntBits` là xác định. Ví dụ **không khẳng định** payload bất kỳ của signaling NaN sẽ giữ nguyên khi đưa qua giá trị `float`.

## 8. Chuyển chuỗi hex/binary nhập vào thành mẫu bit

Một công cụ debug thường hiển thị mẫu IEEE 754 dưới dạng chuỗi, chẳng hạn `"40400000"` hoặc `"4008000000000000"`. Cần **parse chuỗi thành `int`/`long` mang bit tương ứng**, rồi mới gọi API diễn giải mẫu.

Ví dụ:

```java
int floatBits = Integer.parseUnsignedInt("40400000", 16);
float a = Float.intBitsToFloat(floatBits); // 3.0f

long doubleBits = Long.parseUnsignedLong("4008000000000000", 16);
double b = Double.longBitsToDouble(doubleBits); // 3.0
```

Tại sao dùng `parseUnsignedInt`/`parseUnsignedLong`?

- Các mẫu 32 bit hoặc 64 bit có thể bật bit cao nhất.
- `Integer.parseInt("FF800000", 16)` không thể parse như một giá trị `int` dương có dấu, nhưng `Integer.parseUnsignedInt("FF800000", 16)` có thể lưu đúng **mẫu 32 bit** trong `int` (giá trị `int` có thể âm).
- Tương tự, `Long.parseUnsignedLong("FFF0000000000000", 16)` giữ đúng **64 bit**, dù giá trị `long` khi xem là số có dấu là âm.

```java
int negativeInfinityBits =
        Integer.parseUnsignedInt("FF800000", 16);
float negativeInfinity =
        Float.intBitsToFloat(negativeInfinityBits); // -Infinity
```

API parse không tự bỏ mọi tiền tố một cách tùy ý: ví dụ `Integer.parseUnsignedInt("0x40400000", 16)` không phải cú pháp hợp lệ vì chứa `0x`. Nếu dữ liệu nhận có tiền tố, hãy kiểm tra đầu vào rồi bỏ tiền tố theo định dạng quy ước trước khi parse.

Nếu nguồn là chuỗi nhị phân 32 bit, dùng `Integer.parseUnsignedInt(text, 2)`; với 64 bit dùng `Long.parseUnsignedLong(text, 2)`. Luôn xác thực độ dài, cơ số và định dạng khi đọc dữ liệu từ nguồn không đáng tin, tránh âm thầm chấp nhận số ký tự hoặc độ rộng không đúng giao thức.

### Ví dụ runnable: parse mẫu 32/64 bit

Tạo file `ParseFloatingBitsDemo.java`:

```java
public class ParseFloatingBitsDemo {
    public static void main(String[] args) {
        int floatBits = Integer.parseUnsignedInt("40400000", 16);
        long doubleBits = Long.parseUnsignedLong(
                "4008000000000000", 16);

        System.out.println("float: "
                + Float.intBitsToFloat(floatBits));
        System.out.println("double: "
                + Double.longBitsToDouble(doubleBits));

        int negativeInfBits =
                Integer.parseUnsignedInt("FF800000", 16);
        System.out.println("negative infinity: "
                + Float.intBitsToFloat(negativeInfBits));

        System.out.printf("roundtrip float: %08X%n",
                Float.floatToRawIntBits(
                        Float.intBitsToFloat(floatBits)));
        System.out.printf("roundtrip double: %016X%n",
                Double.doubleToRawLongBits(
                        Double.longBitsToDouble(doubleBits)));
    }
}
```

Chạy:

```bash
javac ParseFloatingBitsDemo.java
java ParseFloatingBitsDemo
```

Kết quả:

```text
float: 3.0
double: 3.0
negative infinity: -Infinity
roundtrip float: 40400000
roundtrip double: 4008000000000000
```

## 9. Byte order: khi mẫu bit nằm trong file hoặc gói mạng

Các API `Float.intBitsToFloat` và `Double.longBitsToDouble` nhận **sẵn một `int`/`long`**, không tự đọc byte hay quyết định thứ tự byte. Khi mẫu bit được truyền dưới dạng 4 hoặc 8 byte, phải ghép đúng theo **endianness**:

- **Big-endian**: byte trọng số cao đứng trước. Mẫu `0x3F800000` có các byte `3F 80 00 00`.
- **Little-endian**: byte trọng số thấp đứng trước. Mẫu `0x3F800000` có các byte `00 00 80 3F`.

Java NIO `ByteBuffer` hỗ trợ `ByteOrder.BIG_ENDIAN` và `ByteOrder.LITTLE_ENDIAN`. Khi gọi `getFloat()`/`getDouble()`, thư viện đọc byte theo thứ tự đã cấu hình và diễn giải chúng thành dấu phẩy động.

Ví dụ chạy được, file `FloatingByteOrderDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class FloatingByteOrderDemo {
    public static void main(String[] args) {
        byte[] bigEndian = {
                0x3F, (byte) 0x80, 0x00, 0x00
        };
        byte[] littleEndian = {
                0x00, 0x00, (byte) 0x80, 0x3F
        };

        float a = ByteBuffer.wrap(bigEndian)
                .order(ByteOrder.BIG_ENDIAN)
                .getFloat();
        float b = ByteBuffer.wrap(littleEndian)
                .order(ByteOrder.LITTLE_ENDIAN)
                .getFloat();

        System.out.println("big endian: " + a);
        System.out.println("little endian: " + b);
        System.out.println("same value: " + (a == b));
    }
}
```

Biên dịch và chạy:

```bash
javac FloatingByteOrderDemo.java
java FloatingByteOrderDemo
```

Kết quả:

```text
big endian: 1.0
little endian: 1.0
same value: true
```

Nếu cấu hình sai thứ tự byte, cùng bốn byte có thể tạo giá trị rất khác, dù chương trình không báo lỗi. Với `double`, cần đủ 8 byte và chọn order tương ứng. Ngoài ra, phải kiểm tra số byte còn lại, cấu trúc gói tin và phiên bản định dạng, vì `getFloat()`/`getDouble()` không tự biết bạn đang đọc đúng vị trí dữ liệu hay chưa.

## 10. Có thể tự tách ba trường bit để kiểm tra

Khi cần phân tích vì sao một bit pattern tạo ra giá trị nào, có thể dùng phép dịch logic `>>>` và AND theo bit `&` để tách dấu, số mũ, phân số.

### Float 32 bit

```java
int bits = 0x4040_0000;

int sign = (bits >>> 31) & 1;
int exponent = (bits >>> 23) & 0xFF;
int fraction = bits & 0x7F_FFFF;

// sign=0, exponent=128, fraction=0x400000
```

### Double 64 bit

```java
long bits = 0x4008_0000_0000_0000L;

long sign = (bits >>> 63) & 1L;
long exponent = (bits >>> 52) & 0x7FFL;
long fraction = bits & 0x000F_FFFF_FFFF_FFFFL;

// sign=0, exponent=1024, fraction=0x8000000000000
```

Đây là **những đoạn mã minh họa** cần đặt trong phương thức hoặc chương trình Java để chạy. Chúng hữu ích khi debug biểu diễn, nhưng trong chương trình thông thường hãy ưu tiên `Float.intBitsToFloat`/`Double.longBitsToDouble` vì các API này xử lý đúng cả số dưới chuẩn và những giá trị đặc biệt.

**Bẫy phổ biến khi tự tính công thức:** số dưới chuẩn không có bit 1 ẩn, số mũ được diễn giải khác trường hợp chuẩn hóa, và tất cả mẫu có `E` toàn-1 phải xử lý Infinity/NaN riêng. Chỉ áp dụng công thức của số chuẩn hóa cho mọi mẫu sẽ cho kết quả sai.

## 11. Những nhầm lẫn và lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `(float) bits` không ra giá trị từ IEEE 754 | Cast là đổi giá trị số, không phải reinterpret bit | Dùng `Float.intBitsToFloat(bits)` |
| `(double) bits` không đọc đúng mẫu 64 bit | Cast `long → double` là chuyển số học | Dùng `Double.longBitsToDouble(bits)` |
| Mẫu có bit dấu 1 hiển thị như `int/long` âm | Primitive integer có dấu, nhưng bit pattern vẫn nguyên | Giữ nguyên bit, dùng API diễn giải IEEE 754 |
| Parse chuỗi `FF800000` bằng `parseInt` bị lỗi | Vượt miền `int` có dấu ở dạng dương | Dùng `parseUnsignedInt(..., 16)` |
| `parseUnsignedInt("0x...",16)` báo lỗi | API parse không nhận tiền tố literal `0x` | Bỏ tiền tố sau khi xác thực |
| `+0.0 == -0.0` nhưng bit khác nhau | IEEE 754 có hai số 0 có dấu | So mẫu qua `floatToRawIntBits` nếu cần đúng bit |
| NaN round-trip mất payload | API không Raw chuẩn hóa NaN; signaling NaN có thể bị quiet | Giữ mẫu nguyên `int/long` nếu đòi bit-perfect |
| Diễn giải byte ra giá trị sai | Sai endian, sai offset hoặc sai độ rộng | Kiểm tra giao thức, `ByteOrder`, chiều dài dữ liệu |
| Tưởng `float` 64 bit | `float` dùng 32 bit, `double` dùng 64 bit | Chọn đúng API và độ rộng |
| Tự tách bit cho Infinity như số thường | `E` toàn-1 có quy tắc đặc biệt | Xử lý Infinity/NaN trước công thức |
| Kết quả mất precision dù bit đúng | Binary32/binary64 chỉ biểu diễn hữu hạn độ chính xác | Giữ nguyên định dạng nguồn hoặc chọn cách biểu diễn phù hợp |

## 12. Kiểm tra giá trị sau khi phục hồi

Nếu mẫu bit đến từ dữ liệu bên ngoài, bạn có thể **phục hồi đúng bit** nhưng kết quả lại là NaN hoặc Infinity mà nghiệp vụ không cho phép. Hãy kiểm tra sau khi diễn giải:

```java
static float requireFiniteFloat(int bits) {
    float value = Float.intBitsToFloat(bits);
    if (!Float.isFinite(value)) {
        throw new IllegalArgumentException("non-finite float");
    }
    return value;
}
```

Đây là **phương thức minh họa**, đặt trong class Java để sử dụng. Tương tự dùng `Double.isFinite(Double.longBitsToDouble(bits))` đối với `double`.

`isFinite` chấp nhận cả số dưới chuẩn và ±0.0; nó chỉ loại NaN và ±Infinity. Nếu nghiệp vụ không cho phép các trường hợp khác (ví dụ số âm, số dưới chuẩn, quá lớn/nhỏ về mặt ứng dụng), cần kiểm tra thêm các ràng buộc cụ thể.

Khi yêu cầu là kiểm tra dữ liệu **thô** mà không mất NaN payload, nên kiểm tra cấu trúc bit trên `int/long` trước khi chuyển thành `float/double`. Chẳng hạn kiểm tra exponent toàn-1 và fraction khác 0 để nhận diện NaN ngay trên mẫu gốc; cách này tránh dựa vào payload sau một số thao tác floating-point.

## 13. Bài tập tự kiểm tra

**Câu 1.** `Float.intBitsToFloat(0x3F800000)` bằng bao nhiêu?  
**Đáp án:** 1.0f, vì đó là mẫu binary32 của 1.

**Câu 2.** `(float) 0x3F800000` có bằng `Float.intBitsToFloat(0x3F800000)` không?  
**Đáp án:** Không. Phép cast chuyển **số nguyên** 1_065_353_216 thành `float`; phương thức kia diễn giải lại **32 bit** thành 1.0f.

**Câu 3.** `Double.longBitsToDouble(0x4008000000000000L)` bằng bao nhiêu?  
**Đáp án:** 3.0.

**Câu 4.** `0x7F800000` và `0xFF800000` biểu diễn gì khi được chuyển bằng `Float.intBitsToFloat`?  
**Đáp án:** +Infinity và -Infinity.

**Câu 5.** `0x00000001` là mẫu `float` nào?  
**Đáp án:** Số dưới chuẩn dương nhỏ nhất, xấp xỉ 1.4E-45.

**Câu 6.** Hai số `+0.0f` và `-0.0f` có bằng nhau qua `==` không? Mẫu bit có giống nhau không?  
**Đáp án:** `==` là true, nhưng bit khác: lần lượt `0x00000000` và `0x80000000`.

**Câu 7.** Vì sao `Float.floatToIntBits` không đủ để lưu chính xác một NaN payload tùy ý?  
**Đáp án:** Vì phương thức đó chuẩn hóa mọi NaN về mẫu NaN chuẩn. Nếu phải giữ đúng payload, cần làm việc với dữ liệu raw và chú ý signaling NaN có thể bị quiet.

**Câu 8.** Chuỗi hex `"FF800000"` nên đọc thế nào để phục hồi `float` -Infinity?  
**Đáp án:** `int bits = Integer.parseUnsignedInt("FF800000", 16); float value = Float.intBitsToFloat(bits);`.

**Câu 9.** Nếu file chứa byte `00 00 80 3F` để biểu diễn 1.0f thì đó là thứ tự nào?  
**Đáp án:** Little-endian. Dùng `ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)` khi đọc.

**Câu 10.** Tại sao không thể dùng công thức số chuẩn hóa cho bit pattern có exponent toàn 1?  
**Đáp án:** Exponent toàn-1 được dành cho Infinity (fraction bằng 0) và NaN (fraction khác 0), không phải số chuẩn hóa hữu hạn.

**Câu 11.** Muốn lấy bit pattern nguyên bản từ `double value`, dùng gì?  
**Đáp án:** `Double.doubleToRawLongBits(value)`. Nếu muốn mọi NaN chuẩn hóa thành một mẫu chung, dùng `Double.doubleToLongBits(value)`.

**Câu 12.** Nếu mục tiêu là kiểm tra bit pattern đã truyền qua mạng giữ nguyên 100% kể cả signaling NaN, có nên buộc nó đi qua `float` rồi mới so không?  
**Đáp án:** Không. Giữ và so trực tiếp các byte hoặc `int/long` gốc, vì trong một số môi trường signaling NaN có thể bị quiet khi đi qua giá trị dấu phẩy động.

## 14. Ghi nhớ

- **`Float.intBitsToFloat(int)`** diễn giải đúng 32 bit theo binary32; **`Double.longBitsToDouble(long)`** diễn giải đúng 64 bit theo binary64.
- **Cast `(float)`/`(double)` là đổi giá trị số**, khác với việc diễn giải lại mẫu bit.
- Mẫu IEEE 754 gồm **sign, exponent, fraction**; phải phân biệt giá trị chuẩn hóa, dưới chuẩn, ±0.0, ±Infinity và NaN.
- Với dữ liệu cần bảo toàn **mọi bit**, lưu giữ mẫu thô bằng `int/long` hoặc byte; chú ý chuẩn hóa hoặc quiet NaN.
- Khi đọc byte từ file/mạng, **endianness và độ rộng** phải đúng trước khi dùng API.
- Với đầu vào từ bên ngoài, phục hồi mẫu bit thành giá trị là một bước kỹ thuật; **kiểm tra finite và miền nghiệp vụ** là bước riêng.

Tài liệu chuẩn: [Float.intBitsToFloat — Java API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Float.html#intBitsToFloat(int)) và [Double.longBitsToDouble — Java API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html#longBitsToDouble(long)).
