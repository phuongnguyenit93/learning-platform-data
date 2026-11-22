# MIN_VALUE, MAX_VALUE, TYPE và các hằng theo từng lớp trong Java

## 1. Khái niệm

Java có sáu kiểu số nguyên thủy: byte, short, int, long, float, double. Các wrapper tương ứng là **Byte**, **Short**, **Integer**, **Long**, **Float** và **Double**, đều kế thừa lớp trừu tượng **Number**. Các lớp này cung cấp những hằng **public static final** để tra cứu giới hạn biểu diễn, số bit, số byte và kiểu nguyên thủy liên quan.

**Character**, **Boolean** cũng là wrapper nhưng không kế thừa Number. **Void** có TYPE đại diện cho void, dù void không chứa giá trị để tính toán.

~~~java
int smallest = Integer.MIN_VALUE;
int largest = Integer.MAX_VALUE;
Class<Integer> primitiveType = Integer.TYPE;
~~~

Các trường trên thuộc **lớp**, không cần khởi tạo đối tượng Integer. Điểm quan trọng nhất: ý nghĩa **MIN_VALUE** ở các wrapper nguyên **khác** với Float và Double.

## 2. Bảng hằng cơ bản

| Lớp | MIN_VALUE | MAX_VALUE | TYPE đại diện | SIZE (bit) | BYTES |
| --- | --- | --- | --- | ---: | ---: |
| Byte | −128 | 127 | byte.class | 8 | 1 |
| Short | −32768 | 32767 | short.class | 16 | 2 |
| Integer | −2147483648 | 2147483647 | int.class | 32 | 4 |
| Long | −9223372036854775808 | 9223372036854775807 | long.class | 64 | 8 |
| Float | 2^−149, **dương** | khoảng 3.4028235 × 10^38, dương hữu hạn | float.class | 32 | 4 |
| Double | 2^−1074, **dương** | khoảng 1.7976931348623157 × 10^308, dương hữu hạn | double.class | 64 | 8 |

Các số nguyên có dấu n bit dùng phạm vi **−2^(n−1)** đến **2^(n−1)−1**. Vì vậy Integer.MIN_VALUE âm hơn giá trị đối của Integer.MAX_VALUE một đơn vị.

Ngược lại, **Float.MIN_VALUE/Double.MIN_VALUE** là giá trị dương khác 0 **nhỏ nhất** theo định dạng IEEE 754, không phải giá trị âm hữu hạn nhỏ nhất. Hãy luôn đọc ý nghĩa của trường theo lớp chứa nó.

## 3. Byte, Short, Integer, Long và phép toán tràn

Byte và Short có MIN_VALUE/MAX_VALUE lần lượt là **−128/127** và **−32768/32767**. Chúng có kiểu trường **byte/short**, nhưng phép cộng thường nâng toán hạng thành int:

~~~java
byte b = Byte.MAX_VALUE;
int next = b + 1;                   // 128, kiểu int
byte wrapped = (byte) (b + 1);     // -128
// byte invalid = b + 1;           // lỗi biên dịch: int không tự thu hẹp về byte
~~~

Với Integer, phép cộng vẫn trong 32 bit nếu không có toán hạng long:

~~~java
int overflowed = Integer.MAX_VALUE + 1;       // -2147483648
long stillWrong = Integer.MAX_VALUE + 1;      // -2147483648L
long correct = (long) Integer.MAX_VALUE + 1;  // 2147483648L
~~~

Việc gán vào long **sau phép tính** không tránh overflow của int. Nếu cần báo lỗi khi tràn, dùng **Math.addExact**, **Math.subtractExact**, **Math.multiplyExact** hoặc **Math.negateExact**, tùy phép toán.

Hai tình huống biên của số nguyên có dấu:

~~~java
int min = Integer.MIN_VALUE;
int negated = -min;               // vẫn -2147483648
int absolute = Math.abs(min);     // vẫn -2147483648
long positive = -(long) min;      // 2147483648L
~~~

**−Integer.MIN_VALUE** không nằm trong miền int. Tương tự **−Long.MIN_VALUE** không nằm trong miền long. Nếu cần giá trị lớn hơn Long.MAX_VALUE, hãy dùng **BigInteger** để tính toán chính xác.

**Không dấu:** Integer.MAX_VALUE là cực đại **có dấu**. Cùng mẫu 32 bit toàn số 1 có giá trị int **−1**, nhưng **Integer.toUnsignedString(-1)** trả chuỗi **4294967295**. Tương tự, **Long.toUnsignedString(-1L)** trả **18446744073709551615**. Java không có primitive unsigned int/unsigned long riêng; đây là API diễn giải mẫu bit theo quy ước không dấu.

## 4. Float và Double: số normal, subnormal và infinity

| Hằng | Float (binary32) | Double (binary64) |
| --- | --- | --- |
| MIN_VALUE | 2^−149 ≈ 1.4 × 10^−45 | 2^−1074 ≈ 4.9 × 10^−324 |
| MIN_NORMAL | 2^−126 ≈ 1.17549435 × 10^−38 | 2^−1022 ≈ 2.2250738585072014 × 10^−308 |
| MAX_VALUE | ≈ 3.4028235 × 10^38 | ≈ 1.7976931348623157 × 10^308 |
| POSITIVE_INFINITY | +Infinity | +Infinity |
| NEGATIVE_INFINITY | −Infinity | −Infinity |
| NaN | Not a Number | Not a Number |
| MIN_EXPONENT | −126 | −1022 |
| MAX_EXPONENT | 127 | 1023 |

**MIN_NORMAL** là normal dương nhỏ nhất. **MIN_VALUE** là **subnormal dương nhỏ nhất**, nhỏ hơn MIN_NORMAL. Điều này giúp Java có gradual underflow: một kết quả nhỏ hơn normal nhỏ nhất chưa nhất thiết bị làm tròn ngay về 0.

Để lấy **số âm hữu hạn nhỏ nhất**, dùng **−Float.MAX_VALUE** hoặc **−Double.MAX_VALUE**. **NEGATIVE_INFINITY** còn nhỏ hơn mọi số hữu hạn nhưng bản thân không hữu hạn.

~~~java
float minPositive = Float.MIN_VALUE;       // dương khác 0
float mostNegativeFinite = -Float.MAX_VALUE;
boolean a = Float.MIN_VALUE > 0.0f;        // true
boolean b = Float.POSITIVE_INFINITY > Float.MAX_VALUE; // true
~~~

Kết quả quá lớn có thể overflow thành Infinity; một phép toán không xác định có thể tạo NaN. **NaN == NaN** trả false, vì vậy kiểm tra bằng **Float.isNaN/Double.isNaN**; dùng **isFinite** khi chỉ cho phép giá trị hữu hạn.

**MIN_EXPONENT/MAX_EXPONENT** nói về số mũ của miền normal hữu hạn, không có nghĩa subnormal không thể nhỏ đến 2^−149 hoặc 2^−1074.

Độ chính xác significand normal của float là **24 bit**, double là **53 bit**. Hai trường **Float.PRECISION** và **Double.PRECISION** được bổ sung từ **Java 19**; chúng **không có trong Java 17**, dù các con số 24 và 53 đã được đặc tả trước đó. Ví dụ dùng **javac --release 17** không được truy cập hai trường này.

## 5. TYPE khác với lớp wrapper

**Integer.TYPE** trỏ đến đối tượng Class đại diện primitive **int**, chính là **int.class**. **Integer.class** trỏ đến lớp **java.lang.Integer**:

~~~java
boolean same = Integer.TYPE == int.class;        // true
boolean different = Integer.TYPE == Integer.class; // false
boolean primitive = Integer.TYPE.isPrimitive();  // true
boolean wrapper = Integer.class.isPrimitive();    // false
~~~

Các trường TYPE tương ứng:

| Wrapper | TYPE |
| --- | --- |
| Byte | byte.class |
| Short | short.class |
| Integer | int.class |
| Long | long.class |
| Float | float.class |
| Double | double.class |
| Character | char.class |
| Boolean | boolean.class |
| Void | void.class |

Ví dụ trong reflection: **Math.class.getMethod("abs", Integer.TYPE)** tìm overload nhận primitive int; dùng Integer.class không khớp chữ ký primitive. Đoạn minh họa này cần xử lý **NoSuchMethodException** khi đặt trong mã có thể chạy.

**Integer.TYPE** không chứa số nguyên; nó chứa đối tượng Class. Ngược lại, **Integer.valueOf(42)** tạo/lấy wrapper chứa giá trị 42. Nếu gọi **getClass()** trên Integer object, kết quả là Integer.class chứ không phải Integer.TYPE.

## 6. SIZE và BYTES

~~~java
int a = Byte.SIZE;        // 8 bit
int b = Short.BYTES;      // 2 byte
int c = Integer.SIZE;     // 32 bit
int d = Long.BYTES;       // 8 byte
int e = Double.SIZE;      // 64 bit
~~~

**SIZE/BYTES mô tả độ rộng dữ liệu nguyên thủy**. Không suy rằng đối tượng Long trên heap chỉ tốn Long.BYTES = 8 byte: đối tượng còn header, alignment và các chi phí lưu trữ khác tùy JVM.

## 7. Character, Boolean và Void

**Character.MIN_VALUE = '\u0000'**, **Character.MAX_VALUE = '\uFFFF'**. Theo giá trị số nguyên, miền char là **0..65535**, không dấu, có **SIZE = 16**, **BYTES = 2**.

~~~java
char first = Character.MIN_VALUE;
char last = Character.MAX_VALUE;
int lastCodeUnit = (int) last; // 65535
~~~

Char là **một code unit UTF-16**, không phải mọi Unicode code point. **Character.MAX_CODE_POINT = 0x10FFFF** lớn hơn Character.MAX_VALUE; code point ngoài BMP được biểu diễn bằng cặp surrogate. Character còn có **MIN_RADIX = 2**, **MAX_RADIX = 36**, các hằng hỗ trợ thao tác cơ số/Unicode.

**Boolean.TRUE**, **Boolean.FALSE** là hằng đối tượng Boolean; **Boolean.TYPE == boolean.class**. Boolean **không có** MIN_VALUE, MAX_VALUE, SIZE hay BYTES, vì boolean không phải số nguyên.

**Void.TYPE == void.class** dùng trong reflection và mô tả kiểu trả về không chứa giá trị. Void cũng **không có** MIN_VALUE/MAX_VALUE hoặc SIZE/BYTES.

## 8. Number, BigInteger và BigDecimal

**Number** là lớp trừu tượng có các phương thức chuyển đổi số như intValue(), longValue(), doubleValue(); nó không ấn định miền số hay trường MIN_VALUE/MAX_VALUE/TYPE chung cho tất cả lớp con.

Hai lớp số quan trọng khác trong java.math:

- **BigInteger**: số nguyên độ chính xác tùy ý, có các hằng **ZERO**, **ONE**, **TWO** (Java 9+), **TEN**.
- **BigDecimal**: số thập phân biểu diễn bằng unscaled value và scale, có các hằng **ZERO**, **ONE**, **TEN**. **BigDecimal.TWO** không tồn tại trong Java 17; dùng BigDecimal.valueOf(2).

~~~java
java.math.BigInteger beyondLong =
        java.math.BigInteger.valueOf(Long.MAX_VALUE)
            .add(java.math.BigInteger.ONE);
java.math.BigDecimal zero = java.math.BigDecimal.ZERO;
~~~

Đừng gọi BigInteger.MAX_VALUE hay BigDecimal.MIN_VALUE: chúng không có miền giá trị cố định như primitive. Tính toán BigDecimal có thể cần **MathContext/RoundingMode** để diễn đạt độ chính xác và quy tắc làm tròn theo nghiệp vụ.

## 9. Ví dụ Java 17+ chạy độc lập

Lưu thành **WrapperConstantsDemo.java**:

~~~java
public class WrapperConstantsDemo {
    public static void main(String[] args) {
        System.out.println("Byte range: " + Byte.MIN_VALUE + " .. " + Byte.MAX_VALUE);
        System.out.println("Short range: " + Short.MIN_VALUE + " .. " + Short.MAX_VALUE);
        System.out.println("Integer range: " + Integer.MIN_VALUE + " .. " + Integer.MAX_VALUE);
        System.out.println("Long range: " + Long.MIN_VALUE + " .. " + Long.MAX_VALUE);

        System.out.println("Integer bits/bytes: " + Integer.SIZE + "/" + Integer.BYTES);
        System.out.println("Float exponents: " + Float.MIN_EXPONENT
                + " .. " + Float.MAX_EXPONENT);
        System.out.println("Double exponents: " + Double.MIN_EXPONENT
                + " .. " + Double.MAX_EXPONENT);

        System.out.println("Integer.TYPE == int.class: "
                + (Integer.TYPE == int.class));
        System.out.println("Integer.TYPE == Integer.class: "
                + (Integer.TYPE == Integer.class));
        System.out.println("Integer.TYPE name: " + Integer.TYPE.getName());
        System.out.println("Integer.class name: " + Integer.class.getName());
        System.out.println("Void.TYPE == void.class: "
                + (Void.TYPE == void.class));

        System.out.println("Character range: " + (int) Character.MIN_VALUE
                + " .. " + (int) Character.MAX_VALUE);
        System.out.println("Character bits/bytes: "
                + Character.SIZE + "/" + Character.BYTES);
        System.out.println("Boolean constants: "
                + Boolean.TRUE + "/" + Boolean.FALSE);

        System.out.println("Integer MAX + 1: " + (Integer.MAX_VALUE + 1));
        System.out.println("Byte MAX + 1: " + (Byte.MAX_VALUE + 1));
        System.out.println("Math.abs(Integer.MIN_VALUE): "
                + Math.abs(Integer.MIN_VALUE));
        System.out.println("Unsigned int max: "
                + Integer.toUnsignedString(-1));

        System.out.println("Float.MIN_VALUE: "
                + Float.toHexString(Float.MIN_VALUE));
        System.out.println("Float.MIN_NORMAL: "
                + Float.toHexString(Float.MIN_NORMAL));
        System.out.println("Double.MIN_VALUE: "
                + Double.toHexString(Double.MIN_VALUE));
        System.out.println("Double.MIN_NORMAL: "
                + Double.toHexString(Double.MIN_NORMAL));
        System.out.println("Float.MIN_VALUE > 0: "
                + (Float.MIN_VALUE > 0.0f));
        System.out.println("-Float.MAX_VALUE < Float.MIN_VALUE: "
                + (-Float.MAX_VALUE < Float.MIN_VALUE));
        System.out.println("Float infinity > MAX: "
                + (Float.POSITIVE_INFINITY > Float.MAX_VALUE));
        System.out.println("Float.isNaN: " + Float.isNaN(Float.NaN));
        System.out.println("NaN == NaN: " + (Float.NaN == Float.NaN));

        System.out.println("Integer extends Number: "
                + Number.class.isAssignableFrom(Integer.class));
        System.out.println("Character extends Number: "
                + Number.class.isAssignableFrom(Character.class));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 WrapperConstantsDemo.java
java WrapperConstantsDemo
~~~

Stdout:

~~~text
Byte range: -128 .. 127
Short range: -32768 .. 32767
Integer range: -2147483648 .. 2147483647
Long range: -9223372036854775808 .. 9223372036854775807
Integer bits/bytes: 32/4
Float exponents: -126 .. 127
Double exponents: -1022 .. 1023
Integer.TYPE == int.class: true
Integer.TYPE == Integer.class: false
Integer.TYPE name: int
Integer.class name: java.lang.Integer
Void.TYPE == void.class: true
Character range: 0 .. 65535
Character bits/bytes: 16/2
Boolean constants: true/false
Integer MAX + 1: -2147483648
Byte MAX + 1: 128
Math.abs(Integer.MIN_VALUE): -2147483648
Unsigned int max: 4294967295
Float.MIN_VALUE: 0x0.000002p-126
Float.MIN_NORMAL: 0x1.0p-126
Double.MIN_VALUE: 0x0.0000000000001p-1022
Double.MIN_NORMAL: 0x1.0p-1022
Float.MIN_VALUE > 0: true
-Float.MAX_VALUE < Float.MIN_VALUE: true
Float infinity > MAX: true
Float.isNaN: true
NaN == NaN: false
Integer extends Number: true
Character extends Number: false
~~~

Giải thích: Byte.MAX_VALUE + 1 đã được nâng thành int nên là 128; Integer.MAX_VALUE + 1 tràn int; Integer.TYPE là int.class; Float.MIN_VALUE vẫn dương và nhỏ hơn Float.MIN_NORMAL. Hex của float/double hiển thị mẫu giá trị dạng nhị phân với số mũ qua **toHexString**, thuận tiện kiểm tra số rất nhỏ.

## 10. Sử dụng đúng trong ứng dụng

| Mục tiêu | Hằng/API phù hợp |
| --- | --- |
| Kiểm tra phạm vi signed byte trước khi cast | Byte.MIN_VALUE / Byte.MAX_VALUE |
| Kiểm tra tràn phép cộng int | Math.addExact, kết hợp miền Integer.MIN_VALUE/MAX_VALUE |
| Tìm số dương khác 0 nhỏ nhất của double | Double.MIN_VALUE |
| Tìm số normal dương nhỏ nhất của double | Double.MIN_NORMAL |
| Tìm số âm hữu hạn nhỏ nhất của double | −Double.MAX_VALUE |
| Phân biệt NaN và infinity | Double.isNaN / Double.isFinite / Double.isInfinite |
| Lấy Class primitive cho reflection | Integer.TYPE, Long.TYPE hoặc primitive.class |
| Tính số byte primitive long | Long.BYTES |
| Biểu diễn nguyên lớn hơn Long.MAX_VALUE | BigInteger |
| Lấy số 0 thập phân chính xác | BigDecimal.ZERO |

Hãy kiểm tra rõ **miền đầu vào** của bài toán. Ví dụ, một giá trị tiền cần quy tắc thập phân; một trường 8 bit dữ liệu mạng có thể là byte không dấu 0..255, khác signed Byte.MIN_VALUE..MAX_VALUE. Chọn hằng dựa trên ý nghĩa dữ liệu thay vì tên hằng giống nhau.

## 11. Các nhầm lẫn cần tránh

| Sai lầm | Giải thích đúng |
| --- | --- |
| Float.MIN_VALUE là số float âm nhất | Đó là số **dương subnormal khác 0 nhỏ nhất** |
| Double.MIN_VALUE là normal nhỏ nhất | Normal nhỏ nhất là **Double.MIN_NORMAL** |
| Integer.MAX_VALUE là unsigned int cực đại | Nó là cực đại signed int |
| Integer.TYPE bằng Integer.class | TYPE là **int.class**; wrapper Class khác primitive Class |
| SIZE/BYTES đo kích thước đối tượng | Chúng đo độ rộng dữ liệu primitive |
| Character.MAX_VALUE là Unicode code point cực đại | Nó là UTF-16 code unit tối đa, 0xFFFF |
| Boolean có MIN_VALUE/MAX_VALUE | Boolean chỉ có hằng TRUE/FALSE/TYPE liên quan chủ đề |
| Number khai báo MAX_VALUE chung | Lớp Number không khai báo hằng miền đó |
| BigInteger có MAX_VALUE | BigInteger không có cực đại cố định như long |
| Float.PRECISION có sẵn trong Java 17 | Trường PRECISION được bổ sung từ Java 19 |
| Gán biểu thức int cho long sẽ tránh tràn int | Mở rộng trước khi tính hoặc dùng exact API |
| Math.abs(Integer.MIN_VALUE) luôn không âm | Nó giữ Integer.MIN_VALUE do không biểu diễn được số đối |

## 12. Bài tập tự kiểm tra

**Bài 1.** Byte.MAX_VALUE + 1 có giá trị và kiểu biểu thức gì?

**Đáp án:** **128**, kiểu int, vì numeric promotion.

**Bài 2.** Integer.MAX_VALUE + 1 và (long) Integer.MAX_VALUE + 1 khác nhau thế nào?

**Đáp án:** Phép đầu tràn về −2147483648; phép sau là 2147483648L.

**Bài 3.** Số float âm hữu hạn nhỏ nhất dùng hằng gì?

**Đáp án:** **−Float.MAX_VALUE**, không phải Float.MIN_VALUE.

**Bài 4.** Integer.TYPE == int.class và Integer.TYPE == Integer.class lần lượt trả gì?

**Đáp án:** **true** và **false**.

**Bài 5.** Tại sao Character.MAX_VALUE không bằng Character.MAX_CODE_POINT?

**Đáp án:** char là code unit UTF-16 16 bit, còn code point Unicode có thể lớn hơn 0xFFFF.

**Bài 6.** Có thể truy cập trực tiếp Float.PRECISION khi biên dịch bằng Java 17 không?

**Đáp án:** Không; trường này được thêm từ Java 19. Giá trị significand float vẫn là 24 bit theo đặc tả.

**Bài 7.** BigInteger có MIN_VALUE và MAX_VALUE giống Integer không?

**Đáp án:** Không; nó dùng biểu diễn số nguyên độ chính xác tùy ý, giới hạn thực tế phụ thuộc tài nguyên/triển khai.

## 13. Tài liệu đối chiếu

- [Byte API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html), [Short API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Short.html), [Integer API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html), [Long API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html).
- [Float API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html), [Double API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html).
- [Character API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html), [Boolean API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Boolean.html), [Void API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Void.html).
- [Number API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Number.html), [BigInteger API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html), [BigDecimal API Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).
- [Java Language Specification SE 17 — Primitive Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2) và [Conversions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html).
