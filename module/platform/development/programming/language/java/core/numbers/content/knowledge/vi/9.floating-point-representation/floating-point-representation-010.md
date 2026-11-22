# `floatToIntBits`, `doubleToLongBits` và các biến thể `raw` trong Java

`Float.floatToIntBits`, `Float.floatToRawIntBits`, `Double.doubleToLongBits` và `Double.doubleToRawLongBits` cho phép **xem mẫu bit biểu diễn của một giá trị dấu phẩy động** trong Java. Đây là thao tác trên **cách mã hóa IEEE 754**, không phải phép chuyển giá trị số học sang số nguyên. Sự khác biệt giữa bản thường và bản `raw` đặc biệt quan trọng với **NaN và payload NaN**.

Ví dụ với `float`:

```java
float x = 1.0f;

int bits = Float.floatToIntBits(x);  // 0x3F800000 (1065353216)
int number = (int) x;               // 1: chuyển giá trị bằng cast
```

Cả hai biểu thức đều trả về `int`, nhưng **không cùng ý nghĩa**: `bits` giữ mẫu 32 bit của số `1.0f`; `number` là phần nguyên số học của giá trị `1.0f`. Để hiểu và sử dụng chính xác bốn API, cần phân biệt layout bit, NaN chuẩn hóa, `raw`, phép khôi phục mẫu bit và giới hạn của việc lưu/truyền dữ liệu.

## 1. Bốn API chính và hai API đi ngược

| API | Tham số | Kết quả | Xử lý NaN |
| --- | --- | --- | --- |
| `Float.floatToIntBits(float)` | `float`, 32 bit | `int` chứa mẫu bit 32 bit | **Chuẩn hóa mọi NaN** thành `0x7FC00000` |
| `Float.floatToRawIntBits(float)` | `float`, 32 bit | `int` chứa mẫu bit 32 bit | Trả **mẫu bit raw** của giá trị đang được biểu diễn |
| `Double.doubleToLongBits(double)` | `double`, 64 bit | `long` chứa mẫu bit 64 bit | **Chuẩn hóa mọi NaN** thành `0x7FF8000000000000L` |
| `Double.doubleToRawLongBits(double)` | `double`, 64 bit | `long` chứa mẫu bit 64 bit | Trả **mẫu bit raw** của giá trị đang được biểu diễn |

Hai API khôi phục tương ứng:

- `Float.intBitsToFloat(int bits)`: diễn giải **32 bit đã cho** thành một giá trị `float`.
- `Double.longBitsToDouble(long bits)`: diễn giải **64 bit đã cho** thành một giá trị `double`.

Chúng không phải phép chuyển số học từ `int` sang `float` hoặc `long` sang `double`:

```java
float arithmetic = (float) 0x3F800000;         // Chuyển số nguyên lớn thành float
float decoded = Float.intBitsToFloat(0x3F800000); // 1.0f

double arithmetic2 = (double) 0x3FF0000000000000L;
double decoded2 = Double.longBitsToDouble(0x3FF0000000000000L); // 1.0
```

Với `intBitsToFloat`/`longBitsToDouble`, **cùng chuỗi bit** được diễn giải theo định dạng dấu phẩy động; không thực hiện phép chia, nhân hay làm tròn số nguyên sang số thực như cast thông thường.

## 2. Layout IEEE 754 của `float` và `double`

Java sử dụng định dạng dấu phẩy động nhị phân theo IEEE 754 cho `float` và `double`. Giá trị biểu diễn gồm **bit dấu, trường số mũ và trường phần trị (fraction)**:

| Thành phần | `float` (binary32) | `double` (binary64) |
| --- | ---: | ---: |
| Tổng bit | 32 | 64 |
| Bit dấu | 1 | 1 |
| Bit exponent | 8 | 11 |
| Bit fraction | 23 | 52 |
| Bias của exponent | 127 | 1023 |

Minh họa vị trí bit, từ trái sang phải (bit có trọng số cao đến thấp):

```text
float  (32 bit): S EEEEEEEE FFFFFFFFFFFFFFFFFFFFFFF
                 1    8               23

double (64 bit): S EEEEEEEEEEE FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
                 1      11                         52
```

- **Dấu (`S`):** `0` dương, `1` âm.
- **Exponent:** với giá trị normal hữu hạn, exponent lưu số mũ có bias; với exponent bằng toàn bit `1`, mẫu bit chỉ vô cực hoặc NaN.
- **Fraction:** các bit phần trị. Với giá trị normal có bit dẫn ẩn, độ chính xác hiệu dụng là 24 bit cho `float` và 53 bit cho `double`. Với subnormal, quy tắc phần trị khác (không có bit dẫn 1 ẩn).

Ví dụ `float 1.0f` có dấu 0, exponent lưu 127 và fraction 0. Mẫu bit đầy đủ là `0x3F800000`. `double 1.0` có mẫu `0x3FF0000000000000L`.

Các mẫu tiêu biểu:

| Giá trị | Bit `float` | Bit `double` |
| --- | --- | --- |
| `+0.0` | `0x00000000` | `0x0000000000000000` |
| `-0.0` | `0x80000000` | `0x8000000000000000` |
| `+1.0` | `0x3F800000` | `0x3FF0000000000000` |
| `+Infinity` | `0x7F800000` | `0x7FF0000000000000` |
| `-Infinity` | `0xFF800000` | `0xFFF0000000000000` |
| NaN **chuẩn hóa bởi API thường** | `0x7FC00000` | `0x7FF8000000000000` |

Đây là các mã hexa của mẫu bit, **không phải** literal Java có kiểu `float`/`double`. Lưu `0x3F800000` vào `int` rồi cast thành `float` sẽ cho giá trị lớn khoảng một tỷ, không phải `1.0f`; muốn tái diễn giải phải dùng `Float.intBitsToFloat`.

## 3. `floatToIntBits` và `doubleToLongBits` hoạt động thế nào?

Hai phương thức `Float.floatToIntBits` và `Double.doubleToLongBits` chuyển giá trị sang một số nguyên **cùng độ rộng bit**:

```java
int floatBits = Float.floatToIntBits(1.0f);    // 0x3F800000
long doubleBits = Double.doubleToLongBits(1.0); // 0x3FF0000000000000L
```

Chúng bảo toàn các bit của giá trị **không phải NaN**, bao gồm:

- `+0.0` và `-0.0`: số học so sánh bằng nhau, nhưng bit dấu khác nhau nên kết quả bits khác nhau.
- `+Infinity` và `-Infinity`: exponent toàn 1, fraction toàn 0, dấu khác nhau.
- Số hữu hạn normal và subnormal: mã hóa của chúng được trả trong `int`/`long`.
- Số âm: bit cao nhất bằng 1; vì `int` và `long` có dấu, kết quả khi **in dạng thập phân có thể là số âm**. Điều này không làm thay đổi chuỗi bit.

**Riêng NaN**, API thường trả một mẫu chuẩn duy nhất: `Float.floatToIntBits(...)` trả `0x7FC00000` và `Double.doubleToLongBits(...)` trả `0x7FF8000000000000L` với mọi NaN. Do đó, nếu có nhiều NaN mang payload khác nhau, dùng API thường sẽ **không giữ sự khác biệt về payload**.

Lợi ích của chuẩn hóa là tạo biểu diễn **xác định** khi so sánh hoặc tạo hash dựa trên bit của giá trị NaN theo ngữ nghĩa wrapper. Điều này không đồng nghĩa với việc các phép so sánh primitive `==` giữa NaN trở thành đúng; Java vẫn có quy tắc `Double.NaN == Double.NaN` là `false`.

## 4. Biến thể `raw` khác gì với bản thường?

Các API `Float.floatToRawIntBits` và `Double.doubleToRawLongBits` trả lại mẫu bit của giá trị hiện tại **mà không chuẩn hóa mọi NaN về một mẫu canonical**. Với NaN chứa payload, điểm khác biệt có thể quan sát:

```java
float nanWithPayload = Float.intBitsToFloat(0x7FC01234);
int raw = Float.floatToRawIntBits(nanWithPayload);    // 0x7FC01234 trong ví dụ
int normal = Float.floatToIntBits(nanWithPayload);    // 0x7FC00000

double nan64 = Double.longBitsToDouble(0x7FF8000000001234L);
long raw64 = Double.doubleToRawLongBits(nan64);       // 0x7FF8000000001234L trong ví dụ
long normal64 = Double.doubleToLongBits(nan64);      // 0x7FF8000000000000L
```

Payload NaN nằm trong phần fraction khi exponent toàn 1 và fraction khác 0. Các phép tính dấu phẩy động có thể sinh hoặc truyền NaN; một số hệ thống sử dụng payload để ghi thông tin trạng thái. Tuy nhiên, **không nên dùng payload NaN như một kênh dữ liệu đáng tin cậy trên mọi đường đi**.

**Giới hạn quan trọng với NaN signaling:** Trên một số nền tảng, `Float.intBitsToFloat` hoặc `Double.longBitsToDouble` khi đưa mẫu *signaling NaN* vào giá trị số thực có thể khiến nó được **quiet hóa** (*quieting*), làm đổi một số bit. Vì vậy không được cam kết mọi mẫu NaN raw sẽ round-trip bit-perfect qua mọi phép toán, tham số, tối ưu hóa hoặc JVM. Trong ví dụ kiểm thử, các mẫu `0x7FC01234` và `0x7FF8000000001234L` là các **quiet NaN** có payload; API `raw` giữ mẫu đúng trong lần chạy được minh họa. Nếu yêu cầu bảo toàn **mọi mẫu bit NaN đầu vào** trong file/giao thức, lưu và vận chuyển chúng dưới dạng `int`/`long` hoặc mảng byte, và chỉ diễn giải thành `float`/`double` khi thực sự cần tính toán.

Với giá trị **không phải NaN**, kết quả của API `raw` và API thường là như nhau.

## 5. Vì sao `+0.0` và `-0.0` bằng nhau nhưng mã bit khác nhau?

IEEE 754 có **hai mẫu bit của số 0**:

```java
double plus = 0.0;
double minus = -0.0;

boolean numericEqual = (plus == minus);  // true
boolean bitEqual = Double.doubleToLongBits(plus)
                 == Double.doubleToLongBits(minus); // false
```

Với `double`, `+0.0` là `0x0000000000000000L`, `-0.0` là `0x8000000000000000L`. Với `float`, chúng là `0x00000000` và `0x80000000`. Bit dấu tạo sự khác biệt mặc dù phép so sánh giá trị `==` đánh giá bằng nhau.

Sự khác biệt đôi khi có nghĩa toán học: `1.0 / +0.0` sinh `+Infinity`, còn `1.0 / -0.0` sinh `-Infinity`. API bit hữu ích khi cần xác nhận dấu của zero trong phép tính hoặc khi giải mã dữ liệu nhị phân.

**Đừng dùng so sánh bit một cách máy móc để thay mọi so sánh số thực.** So sánh giá trị, so sánh theo `Float.compare`/`Double.compare`, và so sánh bit thô là ba yêu cầu khác nhau. Ví dụ, primitive `NaN == NaN` là false, trong khi wrapper `Double.equals` được thiết kế theo phép so sánh bit canonical; signed zero cũng được wrapper phân biệt. Hãy chọn quy tắc theo nghiệp vụ.

## 6. Khôi phục bit: `intBitsToFloat` và `longBitsToDouble`

Hai hàm “đảo” lấy **các bit nguyên** rồi tạo giá trị số thực:

```java
int bits32 = 0x3F800000;
float restored32 = Float.intBitsToFloat(bits32); // 1.0f

long bits64 = 0x3FF0000000000000L;
double restored64 = Double.longBitsToDouble(bits64); // 1.0
```

Với các giá trị `float`/`double` **không phải NaN**, có quan hệ round-trip bit quan trọng:

```java
int bits = Float.floatToIntBits(3.5f);
float again = Float.intBitsToFloat(bits); // 3.5f

long longBits = Double.doubleToLongBits(-0.0);
double again64 = Double.longBitsToDouble(longBits); // -0.0
```

Nếu bắt đầu từ một **mẫu bit NaN tùy ý**, đi qua API thường sẽ chuẩn hóa NaN, nên *bit round-trip* có thể khác. Ngay cả với `raw`, các caveat về signaling NaN và những phép toán trung gian vẫn phải được lưu ý.

Nên phân biệt **round-trip giá trị** và **round-trip chuỗi bit**:

- Với số hữu hạn, mục tiêu tái tạo đúng giá trị thường trùng với việc giữ mẫu bit.
- Với `+0.0` và `-0.0`, cùng so sánh bằng về số học nhưng bit khác; cần xác định mục tiêu có bảo toàn dấu zero không.
- Với NaN, kết quả “vẫn là NaN” chưa chứng minh được payload hoặc mọi bit ban đầu đều được giữ.

## 7. In bit đúng cách: hex và phép dịch không dấu

Do `Float.floatToIntBits` trả `int` có dấu, những mẫu có bit cao bằng 1 có thể in ra số nguyên âm. Ví dụ `Float.floatToIntBits(-0.0f)` là mẫu `0x80000000`, tương ứng với `Integer.MIN_VALUE` nếu in thập phân.

In hexa giúp xem đúng độ rộng:

```java
int bits32 = Float.floatToIntBits(-0.0f);
System.out.printf("0x%08X%n", bits32);   // 0x80000000

long bits64 = Double.doubleToLongBits(-0.0);
System.out.printf("0x%016X%n", bits64);  // 0x8000000000000000
```

Nếu muốn tách trường `float`:

```java
int bits = Float.floatToRawIntBits(1.0f);
int sign = (bits >>> 31) & 1;
int exponent = (bits >>> 23) & 0xFF;
int fraction = bits & 0x7FFFFF;
// sign = 0, exponent = 127, fraction = 0
```

Với `double`:

```java
long bits = Double.doubleToRawLongBits(1.0);
long sign = (bits >>> 63) & 1L;
long exponent = (bits >>> 52) & 0x7FFL;
long fraction = bits & 0xFFFFFFFFFFFFFL;
// sign = 0, exponent = 1023, fraction = 0
```

Dùng `>>>` (dịch phải **không dấu**, bổ sung bit 0 ở bên trái) khi phân tích trường bit, đặc biệt cho mẫu có bit dấu 1. Dùng đúng literal kiểu `long` (`1L`, `0x7FFL`) khi thao tác với 64 bit.

Đừng nhầm **bit của giá trị số thực** với chuỗi ký tự thập phân của nó. Số `0.1` không có biểu diễn nhị phân hữu hạn chuẩn xác; API trả về mẫu `double` thực tế, không phải mã chữ số “0”, “.”, “1”.

## 8. Chương trình hoàn chỉnh Java 17+ về canonical và raw

Tạo tệp `FloatingBitsDemo.java`:

```java
public class FloatingBitsDemo {
    static String fhex(int bits) {
        return String.format("0x%08X", bits);
    }

    static String dhex(long bits) {
        return String.format("0x%016X", bits);
    }

    public static void main(String[] args) {
        float f = 1.0f;
        System.out.println("float 1.0 bits: " + fhex(Float.floatToIntBits(f)));
        System.out.println("float -0.0 bits: " + fhex(Float.floatToIntBits(-0.0f)));
        System.out.println("float +0.0 bits: " + fhex(Float.floatToIntBits(0.0f)));
        System.out.println("int cast of 1.0f: " + (int) f);
        System.out.println("float NaN canonical: " + fhex(Float.floatToIntBits(Float.NaN)));

        float payloadFloat = Float.intBitsToFloat(0x7FC01234);
        System.out.println("float NaN raw: " + fhex(Float.floatToRawIntBits(payloadFloat)));
        System.out.println("float NaN normalized: " + fhex(Float.floatToIntBits(payloadFloat)));
        System.out.println("float restored 1.0: " + Float.intBitsToFloat(0x3F800000));
        System.out.println("float raw isNaN: " + Float.isNaN(payloadFloat));

        double d = 1.0;
        System.out.println("double 1.0 bits: " + dhex(Double.doubleToLongBits(d)));
        System.out.println("double -0.0 bits: " + dhex(Double.doubleToLongBits(-0.0)));
        System.out.println("double +0.0 bits: " + dhex(Double.doubleToLongBits(0.0)));
        System.out.println("double NaN canonical: " + dhex(Double.doubleToLongBits(Double.NaN)));

        double payloadDouble = Double.longBitsToDouble(0x7FF8000000001234L);
        System.out.println("double NaN raw: " + dhex(Double.doubleToRawLongBits(payloadDouble)));
        System.out.println("double NaN normalized: " + dhex(Double.doubleToLongBits(payloadDouble)));
        System.out.println("double restored 1.0: "
            + Double.longBitsToDouble(0x3FF0000000000000L));
        System.out.println("+0.0 == -0.0: " + (0.0 == -0.0));
        System.out.println("bits equal? "
            + (Double.doubleToLongBits(0.0) == Double.doubleToLongBits(-0.0)));
    }
}
```

Biên dịch và chạy:

```bash
javac FloatingBitsDemo.java
java FloatingBitsDemo
```

Stdout của chương trình (dùng ví dụ quiet NaN payload):

```text
float 1.0 bits: 0x3F800000
float -0.0 bits: 0x80000000
float +0.0 bits: 0x00000000
int cast of 1.0f: 1
float NaN canonical: 0x7FC00000
float NaN raw: 0x7FC01234
float NaN normalized: 0x7FC00000
float restored 1.0: 1.0
float raw isNaN: true
double 1.0 bits: 0x3FF0000000000000
double -0.0 bits: 0x8000000000000000
double +0.0 bits: 0x0000000000000000
double NaN canonical: 0x7FF8000000000000
double NaN raw: 0x7FF8000000001234
double NaN normalized: 0x7FF8000000000000
double restored 1.0: 1.0
+0.0 == -0.0: true
bits equal? false
```

**Giải thích:** Các dòng `1.0` đối chiếu mã IEEE 754 đã biết; `int cast` chứng minh bit conversion không phải numeric cast; các dòng `-0.0` so sánh bit dấu; các cặp `NaN raw` và `NaN normalized` cho thấy việc giữ hoặc chuẩn hóa payload; `intBitsToFloat`/`longBitsToDouble` khôi phục `1.0`. Dấu khác nhau của ±0 không làm phép `==` số học đổi từ true sang false, nhưng các mẫu `long` khác nhau.

## 9. Khi truyền bit ra file/network: byte order là một bước riêng

`floatToIntBits`/`doubleToLongBits` trả về **một giá trị `int`/`long` chứa đúng mẫu bit**, chưa biến nó thành mảng byte hoặc quyết định thứ tự byte của giao thức. Khi serialize, cần xác định:

1. Muốn **chuẩn hóa mọi NaN** hay cần giữ raw payload?
2. Định dạng truyền yêu cầu **big-endian** hay **little-endian**?
3. Bên nhận có giải mã bằng đúng độ rộng 32/64 bit và cùng quy tắc NaN không?
4. Dữ liệu có thể chứa `-0.0`, Infinity hay subnormal không, và những giá trị này có được phép theo hợp đồng dữ liệu không?

Ví dụ sử dụng `ByteBuffer` để tạo biểu diễn big-endian hoặc little-endian của **mẫu 32 bit**:

```java
int bits = Float.floatToIntBits(1.0f); // 0x3F800000

byte[] bigEndian = java.nio.ByteBuffer.allocate(4)
    .order(java.nio.ByteOrder.BIG_ENDIAN)
    .putInt(bits)
    .array(); // 3F 80 00 00

byte[] littleEndian = java.nio.ByteBuffer.allocate(4)
    .order(java.nio.ByteOrder.LITTLE_ENDIAN)
    .putInt(bits)
    .array(); // 00 00 80 3F
```

Đây là **mảnh mã minh họa** trong phương thức. Hãy chỉ định byte order theo giao thức thay vì mặc định suy diễn từ kiến trúc CPU. `ByteBuffer.putFloat`/`getFloat` và `putDouble`/`getDouble` cũng có API cho dữ liệu số thực; cần hiểu quy tắc biểu diễn/canonical NaN của chúng nếu có yêu cầu bảo toàn payload đặc biệt.

Nếu mục tiêu là bảo toàn **mọi byte thô** của thông điệp nhận được, tốt nhất tiếp tục giữ mảng byte hoặc các mẫu `int`/`long` gốc. Việc chuyển chúng thành giá trị số thực, thực hiện phép toán rồi chuyển lại có thể thay đổi NaN payload, hoặc thay đổi cả giá trị khi tính toán.

## 10. Dùng các API này để làm gì?

| Bài toán | Cách phù hợp | Lưu ý |
| --- | --- | --- |
| Debug dấu, exponent, fraction | `floatToRawIntBits`/`doubleToRawLongBits` + bit masks | Nhớ in hexa và dịch `>>>` |
| Kiểm tra `+0.0` vs `-0.0` | `floatToIntBits`/`doubleToLongBits` | Numeric `==` cho true |
| Tái tạo `float`/`double` từ mẫu 32/64 bit | `intBitsToFloat`/`longBitsToDouble` | Đây là diễn giải bit, không phải numeric cast |
| Hash/so sánh theo NaN canonical | `floatToIntBits`/`doubleToLongBits` | Tương thích với việc chuẩn hóa NaN |
| Quan sát NaN payload đang có | Biến thể `raw` | Không hứa mọi payload signaling tồn tại qua mọi phép toán |
| Lưu/truyền bit pattern chính xác | `int`/`long` hoặc `byte[]`, byte order rõ ràng | Tránh làm trung gian bằng phép tính số thực nếu phải bảo toàn bit |
| Chuyển giá trị số thực thành số nguyên | `(int) value`, `(long) value` hoặc chuyển có kiểm tra | Không dùng `floatToIntBits`/`doubleToLongBits` thay thế |

Phân biệt **biểu diễn số** với **giá trị toán học** cũng giúp xử lý các câu hỏi như “vì sao hai số cùng bằng 0 lại khác hash hoặc khác mã bit?” hoặc “vì sao NaN đọc ra vẫn là NaN nhưng payload thay đổi sau khi lưu?”.

## 11. Các sai lầm thường gặp

1. **“`Float.floatToIntBits(x)` tương đương `(int) x`.”** Sai: hàm trả mẫu 32 bit IEEE 754; cast chuyển giá trị toán học và có quy tắc cắt/biên riêng.
2. **“`Double.doubleToLongBits(x)` luôn giữ nguyên mọi NaN payload.”** Sai: hàm chuẩn hóa mọi NaN.
3. **“Bản `raw` cam kết bit-perfect round-trip mọi signaling NaN qua mọi JVM.”** Sai: quá trình chuyển mẫu signaling NaN thành giá trị `float`/`double` có thể quiet hóa NaN.
4. **“`+0.0` và `-0.0` có cùng bit vì `==` trả true.”** Sai: bit dấu khác nhau.
5. **“Hex `0x80000000` trả về `int` âm nên chắc chắn đã bị overflow.”** Sai: đó là mẫu bit 32 bit, và `int` diễn giải bit cao như bit dấu.
6. **“`Float.intBitsToFloat(0x3F800000)` giống cast `(float) 0x3F800000`.”** Sai: một bên đọc IEEE 754 thành `1.0f`, một bên chuyển số nguyên lớn sang số thực.
7. **“`raw` có thể khôi phục NaN payload sau khi `floatToIntBits` đã chuẩn hóa.”** Sai: bit payload bị mất tại bước chuẩn hóa.
8. **“Chuyển sang `int`/`long` tự quyết định byte order.”** Sai: thứ tự byte chỉ xuất hiện khi serialize thành byte.
9. **“Mẫu NaN bất kỳ đều có thể xử lý như một số thực hữu hạn.”** Sai: NaN không so sánh/hoạt động như giá trị hữu hạn bình thường.
10. **“Dùng bit equality thay cho so sánh số học ở mọi nơi.”** Sai: bit equality cố ý phân biệt ±0 và có cách xử lý NaN khác primitive `==`.

## 12. Tự kiểm tra

- `Float.floatToIntBits(1.0f)` trả gì? **Mẫu `0x3F800000`**, không phải `1`.
- `(int) 1.0f` trả gì? **`1`**, do đây là numeric conversion.
- `Float.floatToIntBits(-0.0f)` và `Float.floatToIntBits(0.0f)` có bằng nhau không? **Không**, vì bit dấu khác nhau.
- `Float.floatToIntBits(Float.intBitsToFloat(0x7FC01234))` có bắt buộc trả `0x7FC01234` không? **Không**. Vì đó là NaN, bản thường trả canonical `0x7FC00000`.
- API nào dùng để quan sát NaN payload còn trong giá trị hiện tại? **`Float.floatToRawIntBits` hoặc `Double.doubleToRawLongBits`**.
- `Double.longBitsToDouble(0x3FF0000000000000L)` cho bao nhiêu? **`1.0`**.
- Nếu phải truyền mẫu bit NaN **chính xác tuyệt đối** giữa hai hệ thống, nên làm gì? **Giữ nguyên `int`/`long` hoặc `byte[]` và quy định byte order**, tránh đưa qua các phép tính có thể chuẩn hóa/quiet hóa NaN.

**Ghi nhớ:** `floatToIntBits` và `doubleToLongBits` đọc mẫu IEEE 754 nhưng **canonical hóa NaN**; các biến thể `raw` quan sát mẫu bit NaN hiện có **không chủ động canonical hóa**. `intBitsToFloat` và `longBitsToDouble` giải mã ngược. Đây là **bit conversion**, khác hoàn toàn với `(int)`/`(long)` hay cast số học; muốn bảo toàn payload và binary protocol, phải kiểm soát nơi lưu bit, cách serialize và các giới hạn khi xử lý NaN.
