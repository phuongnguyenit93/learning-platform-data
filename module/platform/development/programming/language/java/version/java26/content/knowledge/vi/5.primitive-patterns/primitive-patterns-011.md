# Kiểm thử giá trị biên, NaN, vô cực và số không có dấu

## 1. Mục tiêu

Primitive patterns cho phép dùng kiểu nguyên thủy trong pattern matching, kể cả với toán tử `instanceof` và `switch`. Điểm cần kiểm thử kỹ là phép chuyển đổi giữa hai kiểu số có giữ nguyên toàn bộ thông tin của giá trị hay không.

Bài thực hành tập trung vào các trường hợp dễ gây lỗi:

- Giá trị nằm đúng tại biên của `byte`, `int`, `long`, `float`.
- Giá trị ngay bên ngoài biên hoặc ngay sát biên.
- Số có phần thập phân và số không biểu diễn chính xác bằng kiểu đích.
- `NaN`, dương vô cực và âm vô cực.
- `+0.0` và `-0.0`, vốn bằng nhau khi dùng `==` nhưng vẫn mang dấu khác nhau.

Mục tiêu là biết cách tạo dữ liệu kiểm thử, đọc kết quả pattern matching và phân biệt phép kiểm tra chuyển đổi chính xác với phép ép kiểu thông thường.

## 2. Trạng thái tính năng và JDK dùng để thực hành

Primitive Types in Patterns, `instanceof`, and `switch` là tính năng preview:

| JDK | JEP | Trạng thái |
|---|---|---|
| JDK 23 | JEP 455 | Preview lần đầu |
| JDK 24 | JEP 488 | Preview lần thứ hai |
| JDK 25 | JEP 507 | Preview lần thứ ba |
| JDK 26 | JEP 530 | Preview lần thứ tư |
| JDK 27 | JEP 532 | Preview lần thứ năm |

Theo tài liệu Java SE 27, tính năng tiếp tục ở preview lần thứ năm và không có thay đổi đáng kể so với JDK 26. Tính đến 27/11/2026, JDK 27 là feature release mới hơn. Theo lộ trình Oracle, JDK 26 đã kết thúc vòng đời hỗ trợ vào tháng 09/2026; chỉ dùng bản này nếu nhà cung cấp JDK của bạn còn hỗ trợ. Khi thử nghiệm mới, hãy dùng JDK 27 với preview tương ứng.

Primitive patterns vẫn chưa phải cú pháp Java ổn định để đưa vào mã sản xuất cần tương thích dài hạn. Nếu ứng dụng chưa chấp nhận phụ thuộc vào preview, hãy dùng kiểm tra miền giá trị, `Double.isFinite`, `Double.isNaN`, các phép so sánh và xử lý chuyển đổi tường minh.

## 3. Pattern kiểm tra chuyển đổi chính xác

### 3.1. Pattern không thực hiện phép ép kiểu tùy ý

Một testing conversion được xem là chính xác nếu phép chuyển đổi không làm mất thông tin và không phát sinh ngoại lệ. Pattern chỉ khớp khi giá trị có thể chuyển sang kiểu đích một cách chính xác.

Ví dụ:

~~~java
double value = 42.0d;

if (value instanceof int number) {
    System.out.println("Có thể dùng int: " + number);
}
~~~

Giá trị `42.0d` khớp với pattern `int number` vì chuyển sang `int` cho kết quả 42 và không mất phần thông tin nào. Biến pattern `number` nhận giá trị đã chuyển đổi.

Ngược lại:

~~~java
double value = 42.5d;

if (value instanceof int number) {
    System.out.println("Giá trị int: " + number);
} else {
    System.out.println("Không thể chuyển chính xác sang int");
}
~~~

Pattern không khớp vì ép `42.5d` sang `int` sẽ bỏ phần thập phân. Không có `ClassCastException`; biểu thức `instanceof` chỉ trả về `false`.

Điều này khác với phép ép kiểu:

~~~java
double value = 42.5d;
int truncated = (int) value; // 42
~~~

Phép cast vẫn thực hiện và âm thầm làm mất phần thập phân. Primitive pattern được thiết kế để kiểm tra tính chính xác trước khi đưa giá trị đã chuyển đổi vào nhánh xử lý.

### 3.2. Thông tin có thể bị mất

Một phép chuyển đổi có thể mất một hoặc nhiều loại thông tin:

| Loại mất mát | Ví dụ |
|---|---|
| Độ lớn | `int 1000` chuyển sang `byte` thành `-24` |
| Độ chính xác | `double 0.1` chuyển sang `float` |
| Miền giá trị | `double 2147483648.0` chuyển sang `int` |
| Dấu | `-0.0d` chuyển sang kiểu nguyên |

Vì vậy, chỉ kiểm tra giá trị có nằm trong một khoảng số học là chưa đủ. Chẳng hạn, `0.1d` nằm trong miền của `float`, nhưng không thể biểu diễn chính xác bằng `float`.

## 4. Giá trị biên của kiểu nguyên

Với chuyển đổi thu hẹp từ `int` sang `byte`, pattern chỉ khớp khi giá trị nằm trong miền `-128..127`.

~~~java
static String asByte(int value) {
    if (value instanceof byte b) {
        return "byte chính xác: " + b;
    }
    return "ngoài miền byte";
}
~~~

| Giá trị nguồn | Kết quả pattern `byte b` | Giải thích |
|---:|---|---|
| `-129` | Không khớp | Nhỏ hơn `Byte.MIN_VALUE` |
| `-128` | Khớp | Đúng biên dưới |
| `-1` | Khớp | Nằm trong miền |
| `0` | Khớp | Không mất thông tin |
| `127` | Khớp | Đúng biên trên |
| `128` | Không khớp | Lớn hơn `Byte.MAX_VALUE` |

Có thể áp dụng cùng cách kiểm tra cho `short`, `char`, `int` và `long`. Lưu ý `char` là kiểu số nguyên không dấu 16 bit, có miền từ 0 đến 65.535; nó không có miền âm như `short`.

Ví dụ với biên của `int`:

~~~java
static boolean fitsInt(double value) {
    return value instanceof int number;
}
~~~

| Giá trị `double` | Khớp `int`? | Lý do |
|---:|---|---|
| `-2147483649.0` | Không | Nhỏ hơn `Integer.MIN_VALUE` |
| `-2147483648.0` | Có | Đúng biên dưới |
| `-2147483648.5` | Không | Có phần lẻ và nằm ngoài biên |
| `0.0` | Có | Chuyển chính xác thành 0 |
| `12.0` | Có | Số nguyên nằm trong miền |
| `12.5` | Không | Mất phần thập phân |
| `2147483647.0` | Có | Đúng biên trên |
| `2147483648.0` | Không | Vượt `Integer.MAX_VALUE` |

Một giá trị ở sát biên nhưng có phần lẻ vẫn không khớp. Ví dụ `Math.nextUp((double) Integer.MAX_VALUE)` lớn hơn biên trên một bước biểu diễn của `double`; cast sang `int` có thể cho ra một số nguyên trong miền, nhưng phép chuyển đổi đó không chính xác.

## 5. NaN và vô cực

### 5.1. NaN

`NaN` biểu diễn một kết quả số không hợp lệ theo IEEE 754, ví dụ phép chia số không cho số không:

~~~java
double nan = 0.0d / 0.0d;

System.out.println(nan);                 // NaN
System.out.println(nan == nan);          // false
System.out.println(Double.isNaN(nan));   // true
~~~

Không dùng `value == Double.NaN` để kiểm tra NaN. Theo quy tắc floating-point, NaN không bằng chính nó. Hãy dùng `Double.isNaN(value)` hoặc `Float.isNaN(value)`.

Khi kiểm tra primitive patterns:

- Chuyển `NaN` sang kiểu nguyên là không chính xác. Ví dụ `NaN instanceof int i` không khớp.
- Chuyển `NaN` sang kiểu floating-point khác được xem là chính xác theo quy tắc testing conversion. Ví dụ `Double.NaN instanceof float f` khớp.
- Một phép cast `(int) Double.NaN` trả về 0, nhưng pattern không khớp vì kết quả đó làm mất thông tin NaN.

### 5.2. Dương vô cực và âm vô cực

Có thể tạo vô cực bằng hằng số hoặc phép chia số khác không cho số không:

~~~java
double positiveInfinity = Double.POSITIVE_INFINITY;
double negativeInfinity = Double.NEGATIVE_INFINITY;

System.out.println(Double.isInfinite(positiveInfinity)); // true
System.out.println(Double.isInfinite(negativeInfinity)); // true
~~~

Quy tắc pattern:

| Chuyển đổi | Kết quả |
|---|---|
| `+Infinity` sang `int` hoặc `long` | Không chính xác |
| `-Infinity` sang `int` hoặc `long` | Không chính xác |
| `+Infinity` sang `float` hoặc `double` | Chính xác |
| `-Infinity` sang `float` hoặc `double` | Chính xác |

Cast vô cực sang kiểu nguyên sẽ bão hòa về giới hạn của kiểu đích. Ví dụ `(int) Double.POSITIVE_INFINITY` cho `Integer.MAX_VALUE`; đó không phải giá trị tương đương với vô cực, vì vậy primitive pattern từ chối phép chuyển đổi.

## 6. Số không có dấu: +0.0 và -0.0

IEEE 754 có hai cách biểu diễn số không:

- `+0.0`: số không dương.
- `-0.0`: số không âm.

Hai giá trị này có cùng độ lớn số học bằng 0, nhưng khác bit dấu. Sự khác biệt có thể ảnh hưởng đến phép chia, hàm toán học, thứ tự và phép chuyển đổi kiểu.

~~~java
double positiveZero = 0.0d;
double negativeZero = -0.0d;

System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0d / positiveZero);           // Infinity
System.out.println(1.0d / negativeZero);           // -Infinity
~~~

### 6.1. Vì sao -0.0 không khớp kiểu nguyên?

Khi chuyển `+0.0d` sang `int`, kết quả là 0 và không mất thông tin dấu. Vì vậy, phép chuyển đổi chính xác.

Khi chuyển `-0.0d` sang `int`, kết quả cũng là 0 nhưng dấu âm bị mất. Vì vậy, phép chuyển đổi được xem là không chính xác.

~~~java
double positiveZero = 0.0d;
double negativeZero = -0.0d;

System.out.println(positiveZero instanceof int p); // true
System.out.println(negativeZero instanceof int n); // false
~~~

Đây là trường hợp quan trọng khi kiểm tra giá trị biên: hai giá trị đều so sánh bằng 0 bằng `==`, nhưng primitive pattern cho kết quả khác nhau khi chuyển sang kiểu nguyên.

### 6.2. Chuyển -0.0 sang kiểu floating-point khác

Chuyển đổi giữa hai kiểu floating-point bảo toàn số không có dấu và được xem là chính xác:

~~~java
double negativeZero = -0.0d;

if (negativeZero instanceof float f) {
    System.out.println(Float.floatToRawIntBits(f));
    System.out.println(Float.floatToRawIntBits(-0.0f));
}
~~~

Có thể so sánh bit thô để xác nhận dấu:

~~~java
static boolean isNegativeZero(double value) {
    return Double.doubleToRawLongBits(value)
            == Double.doubleToRawLongBits(-0.0d);
}
~~~

Không nên chỉ dùng `value == 0.0d` nếu nghiệp vụ cần phân biệt hai dấu. Biểu thức đó trả về `true` cho cả `+0.0` và `-0.0`.

## 7. Kiểm thử số không, NaN và vô cực trong switch

JDK 26 cho phép `switch` nhận selector có kiểu `float`, `double`, `long`, `boolean` và các kiểu boxed tương ứng. Đây vẫn là một phần của preview JEP 530.

Có thể dùng guard `when` để phân loại giá trị:

~~~java
static String classify(double value) {
    return switch (value) {
        case double n when Double.isNaN(n) -> "NaN";
        case double n when n == Double.POSITIVE_INFINITY -> "+Infinity";
        case double n when n == Double.NEGATIVE_INFINITY -> "-Infinity";
        case double n when isNegativeZero(n) -> "-0.0";
        case double n when n == 0.0d -> "+0.0";
        case double n -> "finite non-zero";
    };
}
~~~

Trong ví dụ này, các nhánh có guard được kiểm tra theo thứ tự. Nhánh cuối `case double n` nhận mọi giá trị `double` còn lại. Guard `isNegativeZero` sử dụng bit dấu để tách `-0.0` khỏi `+0.0`.

### 7.1. Case constant phân biệt hai số không

Với case constant kiểu floating-point, `switch` sử dụng representation equivalence. Vì vậy, hai case sau là khác nhau:

~~~java
switch (value) {
    case -0.0d -> System.out.println("Âm không (-0.0)");
    case  0.0d -> System.out.println("Dương không (+0.0)");
    default -> System.out.println("Giá trị khác");
}
~~~

Điều này khác với toán tử `==`, vốn coi `-0.0d == 0.0d` là `true`.

Case constant NaN có quy tắc riêng: mọi bit pattern NaN đều được xem là tương đương cho mục đích so khớp case. Có thể viết:

~~~java
final double NAN = Double.NaN;

switch (value) {
    case NAN -> System.out.println("NaN");
    default -> System.out.println("Không phải NaN");
}
~~~

Không thể dùng nhiều case label để phân biệt payload của các NaN. Nếu cần chẩn đoán payload ở mức bit, hãy đọc `Double.doubleToRawLongBits(value)`; đừng dùng kết quả đó để suy ra rằng primitive pattern phân biệt các payload NaN.

## 8. Ví dụ thực hành hoàn chỉnh

Tạo file `PrimitiveBoundaryLab.java`. Chương trình kiểm tra chuyển đổi chính xác, giá trị biên, NaN, vô cực, hai số không và cách phân loại bằng switch.

~~~java
public class PrimitiveBoundaryLab {
    private static final long NEGATIVE_ZERO_BITS =
            Double.doubleToRawLongBits(-0.0d);

    private static boolean exactToByte(int value) {
        return value instanceof byte converted;
    }

    private static boolean exactToInt(double value) {
        return value instanceof int converted;
    }

    private static boolean exactToLong(double value) {
        return value instanceof long converted;
    }

    private static boolean exactToFloat(double value) {
        return value instanceof float converted;
    }

    private static boolean exactToDouble(float value) {
        return value instanceof double converted;
    }

    private static boolean negativeZeroPreserved(float value) {
        if (value instanceof double widened) {
            return Double.doubleToRawLongBits(widened)
                    == NEGATIVE_ZERO_BITS;
        }
        return false;
    }

    private static boolean negativeZeroPreserved(double value) {
        if (value instanceof float narrowed) {
            return Float.floatToRawIntBits(narrowed)
                    == Float.floatToRawIntBits(-0.0f);
        }
        return false;
    }

    private static boolean isNegativeZero(double value) {
        return Double.doubleToRawLongBits(value) == NEGATIVE_ZERO_BITS;
    }

    private static String classifyWithPatterns(double value) {
        return switch (value) {
            case double n when Double.isNaN(n) -> "NaN";
            case double n when n == Double.POSITIVE_INFINITY -> "+Infinity";
            case double n when n == Double.NEGATIVE_INFINITY -> "-Infinity";
            case double n when isNegativeZero(n) -> "-0.0";
            case double n when n == 0.0d -> "+0.0";
            case double n -> "finite non-zero";
        };
    }

    private static String classifyWithConstants(double value) {
        final double NEG_INF = Double.NEGATIVE_INFINITY;
        final double POS_INF = Double.POSITIVE_INFINITY;
        final double NAN = Double.NaN;

        return switch (value) {
            case NEG_INF -> "-Infinity";
            case -0.0d -> "-0.0";
            case 0.0d -> "+0.0";
            case POS_INF -> "+Infinity";
            case NAN -> "NaN";
            default -> "finite non-zero";
        };
    }

    private static void check(String name, boolean expected, boolean actual) {
        if (expected != actual) {
            throw new AssertionError(
                    name + ": expected " + expected + ", got " + actual
            );
        }
        System.out.println("PASS: " + name);
    }

    private static void check(
            String name,
            String expected,
            String actual
    ) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + ": expected " + expected + ", got " + actual
            );
        }
        System.out.println("PASS: " + name);
    }

    public static void main(String[] args) {
        double positiveZero = 0.0d;
        double negativeZero = -0.0d;
        double nan = Double.NaN;
        double positiveInfinity = Double.POSITIVE_INFINITY;
        double negativeInfinity = Double.NEGATIVE_INFINITY;

        // Số không có dấu khi chuyển sang kiểu nguyên.
        check("+0.0 -> int", true, exactToInt(positiveZero));
        check("-0.0 -> int", false, exactToInt(negativeZero));
        check("+0.0 == -0.0", true, positiveZero == negativeZero);

        // NaN và vô cực không thể chuyển chính xác sang kiểu nguyên.
        check("NaN -> int", false, exactToInt(nan));
        check("+Infinity -> int", false, exactToInt(positiveInfinity));
        check("-Infinity -> int", false, exactToInt(negativeInfinity));

        // Giá trị nguyên và biên của int.
        check("12.0 -> int", true, exactToInt(12.0d));
        check("12.5 -> int", false, exactToInt(12.5d));
        check("Integer.MIN_VALUE", true,
                exactToInt((double) Integer.MIN_VALUE));
        check("Integer.MAX_VALUE", true,
                exactToInt((double) Integer.MAX_VALUE));
        check("Above Integer.MAX_VALUE", false,
                exactToInt(2147483648.0d));
        check("Below Integer.MIN_VALUE", false,
                exactToInt(-2147483649.0d));

        // Biên long trong miền double.
        check("Long.MIN_VALUE represented as double", true,
                exactToLong(-0x1.0p63));
        check("2^63 is outside long", false,
                exactToLong(0x1.0p63));
        check("Largest double below 2^63", true,
                exactToLong(Math.nextDown(0x1.0p63)));

        // Biên byte.
        check("Byte.MIN_VALUE", true, exactToByte(-128));
        check("Byte.MAX_VALUE", true, exactToByte(127));
        check("Below byte range", false, exactToByte(-129));
        check("Above byte range", false, exactToByte(128));

        // Chuyển double sang float.
        check("1.5 -> float", true, exactToFloat(1.5d));
        check("0.1 -> float", false, exactToFloat(0.1d));
        check("Float.MAX_VALUE -> float", true,
                exactToFloat((double) Float.MAX_VALUE));
        check("Next double above Float.MAX_VALUE", false,
                exactToFloat(Math.nextUp((double) Float.MAX_VALUE)));
        check("Float.MIN_VALUE -> float", true,
                exactToFloat((double) Float.MIN_VALUE));
        check("Double.MIN_VALUE -> float", false,
                exactToFloat(Double.MIN_VALUE));

        // Giá trị đặc biệt khi chuyển giữa các kiểu floating-point.
        check("NaN -> float", true, exactToFloat(nan));
        check("+Infinity -> float", true,
                exactToFloat(positiveInfinity));
        check("-Infinity -> float", true,
                exactToFloat(negativeInfinity));
        check("-0.0 double -> float", true,
                exactToFloat(negativeZero));
        check("-0.0 double -> float preserves sign", true,
                negativeZeroPreserved(negativeZero));

        // Mọi giá trị float đều chuyển chính xác sang double.
        check("-0.0 float -> double preserves sign", true,
                negativeZeroPreserved(-0.0f));
        check("NaN float -> double", true, exactToDouble(Float.NaN));
        check("+Infinity float -> double", true,
                exactToDouble(Float.POSITIVE_INFINITY));

        // Switch pattern và switch case constant.
        check("Pattern switch -0.0", "-0.0",
                classifyWithPatterns(negativeZero));
        check("Pattern switch +0.0", "+0.0",
                classifyWithPatterns(positiveZero));
        check("Constant switch -0.0", "-0.0",
                classifyWithConstants(negativeZero));
        check("Constant switch +0.0", "+0.0",
                classifyWithConstants(positiveZero));
        check("Pattern switch NaN", "NaN", classifyWithPatterns(nan));
        check("Constant switch NaN", "NaN", classifyWithConstants(nan));
        check("Pattern switch +Infinity", "+Infinity",
                classifyWithPatterns(positiveInfinity));
        check("Pattern switch -Infinity", "-Infinity",
                classifyWithPatterns(negativeInfinity));

        double nanWithPayload = Double.longBitsToDouble(
                0x7ff8000000000001L
        );
        check("NaN payload matches NaN case", "NaN",
                classifyWithConstants(nanWithPayload));

        System.out.println("Tất cả kiểm tra đã hoàn tất.");
    }
}
~~~

### 8.1. Biên dịch và chạy

JDK 26:

~~~bash
javac --release 26 --enable-preview -d out PrimitiveBoundaryLab.java
java --enable-preview -cp out PrimitiveBoundaryLab
~~~

JDK 27:

~~~bash
javac --release 27 --enable-preview -d out PrimitiveBoundaryLab.java
java --enable-preview -cp out PrimitiveBoundaryLab
~~~

Preview phải được bật ở cả bước biên dịch và chạy. Không cần thêm module incubator. Nếu dùng IDE, hãy đặt language level tương ứng thành `26 (Preview)` hoặc `27 (Preview)`.

Nếu compiler báo lỗi ở pattern nguyên thủy, trước tiên xác nhận compiler và runtime cùng phiên bản, sau đó kiểm tra cờ `--enable-preview`. Không dùng `--release 25` cho mã chứa primitive patterns.

## 9. Những lỗi kiểm thử thường gặp

| Cách kiểm tra dễ sai | Vấn đề | Cách làm phù hợp |
|---|---|---|
| `value == Double.NaN` | Luôn trả về false | Dùng `Double.isNaN(value)` |
| `positiveZero == negativeZero` | Trả về true nên không phân biệt dấu | Dùng `Double.doubleToRawLongBits` hoặc switch case constants |
| Chỉ kiểm tra `value >= Integer.MIN_VALUE && value <= Integer.MAX_VALUE` | Không loại được phần thập phân, NaN hoặc vô cực đúng cách | Dùng primitive pattern để kiểm tra chuyển đổi chính xác |
| Cast rồi kiểm tra lại bằng cast ngược | Có thể che giấu mất mát thông tin | Dùng testing conversion qua pattern |
| Dùng `Double.isInfinite` để phát hiện mọi giá trị không hữu hạn | Bỏ sót NaN | Dùng `Double.isFinite` hoặc kết hợp `isNaN` và `isInfinite` |
| Chỉ kiểm thử số điển hình như 0, 1, 10 | Không phát hiện lỗi tại biên hoặc trường hợp đặc biệt | Kiểm tra MIN/MAX, giá trị liền kề, NaN, ±Infinity và ±0.0 |

Đặc biệt, không nên kiểm thử chuyển đổi `double -> float` chỉ bằng điều kiện nằm trong miền `Float.MIN_VALUE..Float.MAX_VALUE`. Một giá trị nằm trong miền vẫn có thể mất độ chính xác khi làm tròn.

## 10. Checklist thiết kế bộ kiểm thử

Khi kiểm thử primitive patterns cho dữ liệu floating-point, nên bao phủ tối thiểu:

- Số nguyên chính xác và số có phần lẻ.
- Giá trị đúng biên dưới và biên trên của kiểu đích.
- Giá trị ngay ngoài biên bằng `Math.nextUp` hoặc `Math.nextDown`.
- Số không dương và số không âm.
- NaN mặc định và NaN có payload khác nhau nếu ứng dụng xử lý dữ liệu ở mức bit.
- Dương vô cực và âm vô cực.
- Giá trị hữu hạn rất nhỏ có thể underflow khi chuyển sang `float`.
- Giá trị hữu hạn rất lớn có thể overflow thành vô cực khi chuyển sang `float`.
- Kết quả của pattern, giá trị pattern variable và hành vi của phép cast tương ứng.
- Biên dịch và chạy với đúng JDK preview đang thử nghiệm.

Nếu dữ liệu đến từ JSON, database, message broker hoặc API bên ngoài, hãy tạo test fixture cho các giá trị đặc biệt thay vì giả định mọi serializer đều có thể biểu diễn NaN hoặc Infinity. JSON chuẩn không có literal NaN và Infinity; adapter có thể từ chối, chuyển thành null hoặc mã hóa theo quy ước riêng.

## 11. Kết luận

Primitive patterns kiểm tra một phép chuyển đổi có chính xác hay không trước khi đưa giá trị vào nhánh xử lý. Với kiểu nguyên, điều này giúp tránh tràn miền hoặc đổi dấu. Với floating-point, cần chú ý độ chính xác, NaN, vô cực và dấu của số không.

Các trường hợp đáng nhớ:

- `+0.0` chuyển sang kiểu nguyên là chính xác; `-0.0` thì không vì mất dấu.
- NaN và vô cực không chuyển chính xác sang kiểu nguyên, nhưng chuyển giữa các kiểu floating-point được xem là chính xác theo quy tắc testing conversion.
- Chuyển `double` sang `float` có thể mất độ chính xác hoặc miền giá trị ngay cả khi số đó hữu hạn.
- Floating-point switch case phân biệt `-0.0` và `+0.0`; mọi NaN payload được xem là tương đương cho case matching.
- Primitive Types in Patterns vẫn là preview ở JDK 27. Chỉ sử dụng trong thử nghiệm có kiểm soát cho đến khi tính năng trở thành chính thức.

## Tài liệu tham khảo chính thức

- [JEP 530 — Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530)
- [JEP 532 — Primitive Types in Patterns, instanceof, and switch (Fifth Preview)](https://openjdk.org/jeps/532)
- [Primitive Types in Patterns, instanceof, and switch — Java SE 26](https://docs.oracle.com/en/java/javase/26/language/primitive-types-patterns-instanceof-switch.html)
- [Safe Casting with instanceof and switch — Java SE 26](https://docs.oracle.com/en/java/javase/26/language/safe-casting-instanceof-switch.html)
- [Switch Expressions and Statements — Java SE 26](https://docs.oracle.com/en/java/javase/26/language/switch-expressions-statements.html)
- [ExactConversionsSupport — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/runtime/ExactConversionsSupport.html)
- [Primitive Types in Patterns JLS Preview Specification — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/primitive-types-in-patterns-instanceof-switch-jls.html)
- [Java Language Changes by Release — Java SE 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

