# NaN, Infinity và dấu trong đầu vào số thực Java

Khi nhận một chuỗi từ bàn phím, biểu mẫu, CSV, API hoặc tệp cấu hình, không thể mặc định rằng **phân tích (*parse*) thành công nghĩa là có một số hữu hạn, khác 0 và hợp lệ nghiệp vụ**. Trong Java, `Double.parseDouble` và `Float.parseFloat` chấp nhận một số giá trị đặc biệt của dấu phẩy động:

- `NaN` (*Not a Number*) — giá trị không phải số hữu hạn thông thường.
- `Infinity` — dương vô cực; `-Infinity` — âm vô cực.
- Dấu `+` và `-` ở đầu chuỗi, bao gồm `+0.0` và `-0.0`. Hai zero có cùng giá trị so sánh số học nhưng **khác bit dấu**.
- Những số rất lớn hoặc rất nhỏ có thể **tràn thành vô cực** hoặc **làm tròn thành zero** ngay cả khi chuỗi có cú pháp số hợp lệ.

Đề bài thuộc nhóm **phân tích số thực**, nên trọng tâm là **chuỗi đầu vào được chấp nhận thế nào, giá trị nào được tạo ra, và phải xác thực kết quả ra sao**, thay vì chỉ thảo luận phép toán với `NaN`/`Infinity` đã tồn tại.

## 1. Hai API parse cơ bản

Java cung cấp:

```java
double d = Double.parseDouble("12.5");
float f = Float.parseFloat("-3.25");
```

Hai phương thức `static` này trả primitive (`double` và `float`). Các wrapper `Double.valueOf(String)` và `Float.valueOf(String)` tạo **đối tượng wrapper** chứa giá trị tương ứng; quy tắc phân tích chuỗi cơ bản là tương đương.

| Cú pháp | Kiểu trả về | Với chuỗi sai cú pháp | Với tham số `null` |
| --- | --- | --- | --- |
| `Double.parseDouble(String)` | `double` | `NumberFormatException` | `NullPointerException` |
| `Float.parseFloat(String)` | `float` | `NumberFormatException` | `NullPointerException` |
| `Double.valueOf(String)` | `Double` | `NumberFormatException` | `NullPointerException` |
| `Float.valueOf(String)` | `Float` | `NumberFormatException` | `NullPointerException` |

`NumberFormatException` là lỗi **chuỗi không khớp cú pháp được hỗ trợ**. Ngược lại, nhiều giá trị **ngoài miền hữu hạn** vẫn có cú pháp hợp lệ và parse thành công thành vô cực hoặc zero. Vì vậy `try/catch (NumberFormatException ...)` chỉ giải quyết **một phần** xác thực dữ liệu.

## 2. Chuỗi đặc biệt `NaN`, `Infinity` và dấu

Trong ngữ pháp của các phương thức parse số thực, chuỗi `NaN` và `Infinity` dùng **đúng chữ hoa/chữ thường**; có thể có tiền tố dấu `+` hoặc `-`.

| Đầu vào | `Double.parseDouble` trả về | Lưu ý |
| --- | --- | --- |
| `"NaN"` | `NaN` | Không có giá trị số học hữu hạn |
| `"+NaN"` | `NaN` | Dấu không tạo NaN dương có thể so sánh được |
| `"-NaN"` | `NaN` | Không nên suy ra ngữ nghĩa dấu NaN từ dấu chuỗi |
| `"Infinity"` | `Infinity` | Dương vô cực |
| `"+Infinity"` | `Infinity` | Dương vô cực |
| `"-Infinity"` | `-Infinity` | Âm vô cực |
| `"infinity"` | Lỗi | Phân biệt chữ hoa/chữ thường |
| `"Inf"` | Lỗi | Không phải cách viết đặc biệt chuẩn của API |
| `"nan"` | Lỗi | Không phải `"NaN"` |
| `"∞"` | Lỗi | Không phải tên literal được parser này nhận |

```java
System.out.println(Double.parseDouble("NaN"));       // NaN
System.out.println(Double.parseDouble("-NaN"));      // NaN
System.out.println(Double.parseDouble("+Infinity")); // Infinity
System.out.println(Double.parseDouble("-Infinity")); // -Infinity
```

**Không nên coi `-NaN` là một số “âm” theo nghĩa toán học.** NaN không có thứ tự số học bình thường. Dấu trong đầu vào NaN không cung cấp một thuộc tính nghiệp vụ đáng tin; một số cách biểu diễn bit của NaN có thể có bit dấu, nhưng đây không phải quy tắc phân loại NaN âm/dương để ứng dụng dựa vào.

Các chuỗi trên có thể được parse thành **giá trị đặc biệt**; nếu API của bạn chỉ cho phép số hữu hạn, phải chủ động **từ chối** chúng sau parse hoặc xác thực cú pháp trước parse.

## 3. Dấu `+`/`-` với số bình thường và zero có dấu

Một dấu đứng trước giá trị số thập phân hợp lệ:

```java
double a = Double.parseDouble("+12.5"); // 12.5
double b = Double.parseDouble("-12.5"); // -12.5
double c = Double.parseDouble("+0.0");  // +0.0
double d = Double.parseDouble("-0.0");  // -0.0
```

Đáng chú ý, cả `"-0"` và `"-0.0"` đều parse thành **âm zero `double`**, dù `-0` không khác 0 khi dùng số nguyên primitive.

```java
double positiveZero = Double.parseDouble("+0");
double negativeZero = Double.parseDouble("-0");

System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0 / positiveZero);           // Infinity
System.out.println(1.0 / negativeZero);           // -Infinity
```

Hai zero bằng nhau theo toán tử `==` vì đó là **so sánh số học dấu phẩy động**, nhưng chia một số hữu hạn khác zero cho chúng có thể tạo vô cực trái dấu.

### Kiểm tra dấu zero ở mức bit

```java
long positiveBits = Double.doubleToRawLongBits(+0.0); // 0
long negativeBits = Double.doubleToRawLongBits(-0.0); // 0x8000000000000000

boolean differentBits = positiveBits != negativeBits; // true
```

Đối với `float`, dùng `Float.floatToRawIntBits`. **Không dùng điều kiện `x < 0.0` để nhận diện âm zero**; `-0.0 < 0.0` là `false`.

Khi không cần phân biệt signed zero trong nghiệp vụ, có thể chuẩn hóa `x == 0.0 ? 0.0 : x` một cách **có chủ đích**. Nhưng việc chuẩn hóa này làm mất thông tin bit dấu và có thể đổi dấu kết quả chia cho zero sau đó.

## 4. Dấu, dấu cách và ngữ pháp chuỗi

`parseDouble` nhận một số định dạng chuỗi rộng hơn dạng “số có dấu chấm” đơn giản:

```java
Double.parseDouble("  +1.5  "); // 1.5: bỏ whitespace ASCII ở đầu/cuối
Double.parseDouble(".5");       // 0.5
Double.parseDouble("5.");       // 5.0
Double.parseDouble("1e3");      // 1000.0
Double.parseDouble("-2.5E-2");  // -0.025
Double.parseDouble("0x1.8p1");  // 3.0: biểu diễn floating point hex
Double.parseDouble("1.25f");    // 1.25: hậu tố literal float vẫn được nhận
```

Những điều cần lưu ý:

- Parser chấp nhận **ký hiệu mũ thập phân** `e`/`E` và **literal floating-point hex** `0x...p...`. Khi nhận dữ liệu JSON/CSV có schema chặt, bạn có thể **không muốn cho phép** toàn bộ ngữ pháp của parser.
- Parser chấp nhận một số dấu cách đầu/cuối theo quy tắc tương đương `String.trim()` đối với ký tự ASCII/control `<= U+0020`; đừng đồng nhất với mọi loại Unicode whitespace.
- Chuỗi số thực **không cho phép dấu gạch dưới** như literal ở mã nguồn Java. `"1_000.0"` bị từ chối bởi `Double.parseDouble`, dù `1_000.0` là literal hợp lệ trong mã nguồn.
- `"1,5"` **không** trở thành 1.5 theo locale Việt Nam hay một locale khác. `Double.parseDouble` có ngữ pháp độc lập locale và dùng dấu chấm.
- Chuỗi rỗng, dấu đứng một mình, hai dấu liên tiếp hoặc chữ không thuộc ngữ pháp có thể gây `NumberFormatException`.

**Không tự ý bỏ dấu nội bộ, thay mọi dấu phẩy bằng dấu chấm hoặc xóa mọi khoảng trắng**: với định dạng đầu vào do bên ngoài định nghĩa, việc “sửa” dữ liệu trước parse có thể biến đầu vào sai thành đầu vào khác mà người gửi không định cung cấp.

## 5. Parse thành công vẫn có thể cho vô cực: overflow

Độ rộng của kiểu số thực là hữu hạn. Với `double`, giá trị hữu hạn lớn nhất xấp xỉ `1.7976931348623157E308`. Chuỗi số có số mũ lớn hơn có thể parse thành vô cực:

```java
double overflow = Double.parseDouble("1e400");
double negativeOverflow = Double.parseDouble("-1e400");

System.out.println(overflow);         // Infinity
System.out.println(negativeOverflow); // -Infinity
```

**Không có `NumberFormatException` trong hai trường hợp trên**, vì chuỗi đúng cú pháp số thực; kết quả toán học đã vượt miền hữu hạn `double`.

`float` có miền hữu hạn nhỏ hơn `double`:

```java
float f = Float.parseFloat("1e40");   // Infinity
double d = Double.parseDouble("1e40"); // 1.0E40 (hữu hạn)
```

Vì vậy chính cùng một chuỗi hợp lệ có thể cho kết quả khác nhau tùy kiểu parse. Nếu dữ liệu phải nằm trong một giới hạn cụ thể, hãy kiểm tra **kiểu đã chọn và giá trị sau parse**, không chỉ cú pháp.

## 6. Giá trị cực nhỏ có thể thành ±0.0: underflow

Ở phía số nhỏ, số thực rất gần 0 có thể làm tròn thành zero nếu độ lớn nhỏ hơn giá trị dương biểu diễn được ở định dạng đích:

```java
double tiny = Double.parseDouble("1e-4000"); // 0.0
double negativeTiny = Double.parseDouble("-1e-4000"); // -0.0
```

`Double.MIN_VALUE` trong Java là **số `double` dương nhỏ nhất lớn hơn 0**, không phải số âm lớn nhất về trị tuyệt đối. Với `float`, miền dưới chuẩn cũng khác; một giá trị còn đủ biểu diễn trong `double` có thể thành zero khi parse trực tiếp sang `float`.

**Quan trọng:** `Double.isFinite(negativeTiny)` vẫn là `true` vì `-0.0` là giá trị hữu hạn. Nếu nghiệp vụ bắt buộc bảo toàn sự khác biệt giữa đầu vào khác 0 và zero, **kiểm tra `isFinite` chưa đủ**. Cần chính sách từ chối underflow, dùng `BigDecimal` với đầu vào thập phân chính xác, hoặc quy định độ lớn đầu vào tối thiểu.

Không nên đồng nhất mọi kết quả zero với chuỗi `"0"`: `"-1e-4000"` khác 0 về toán học, nhưng được làm tròn thành `-0.0` ở kiểu `double`.

## 7. Phát hiện NaN, Infinity và số hữu hạn đúng cách

Các API chuyên dụng:

| API | `NaN` | `+Infinity` | `-Infinity` | Giá trị hữu hạn, kể cả ±0.0 |
| --- | --- | --- | --- | --- |
| `Double.isNaN(x)` | `true` | `false` | `false` | `false` |
| `Double.isInfinite(x)` | `false` | `true` | `true` | `false` |
| `Double.isFinite(x)` | `false` | `false` | `false` | `true` |

`Float.isNaN`, `Float.isInfinite` và `Float.isFinite` có hành vi tương ứng cho `float`.

```java
double x = Double.parseDouble("-Infinity");
System.out.println(Double.isInfinite(x)); // true
System.out.println(Double.isFinite(x));   // false

double y = Double.parseDouble("NaN");
System.out.println(Double.isNaN(y));     // true
System.out.println(Double.isFinite(y));  // false
```

**Đừng kiểm tra NaN bằng `x == Double.NaN`.** Phép so sánh primitive với NaN luôn `false`, kể cả `Double.NaN == Double.NaN`. Cách đúng là `Double.isNaN(x)`.

Việc có thể parse Infinity/NaN không có nghĩa chúng là dữ liệu hợp lệ của mọi hệ thống. Phần lớn hệ thống tính tổng tiền, lượng hàng hoặc tỷ lệ hữu hạn cần từ chối giá trị không hữu hạn. Trong tính toán khoa học, giá trị đặc biệt có thể được chấp nhận có kiểm soát. Hợp đồng dữ liệu phải nói rõ điều này.

## 8. Khi cần đầu vào chỉ gồm số thập phân hữu hạn

Một parser dùng trong nghiệp vụ thường có **hai tầng kiểm tra**:

1. **Kiểm tra ngữ pháp nguồn:** ứng dụng có cho phép `NaN`, `Infinity`, literal hex, hậu tố `f/d`, khoảng trắng, dấu `+`, dạng `.5` hay exponent không?
2. **Kiểm tra giá trị sau parse:** kết quả có hữu hạn không, có thuộc miền cho phép không, có làm tròn thành zero hoặc mất precision không?

Ví dụ helper **chỉ chấp nhận cú pháp thập phân ASCII** với dấu tùy chọn và exponent, sau đó bắt lỗi và từ chối số không hữu hạn:

```java
static double parseFiniteDecimal(String raw) {
    if (raw == null) {
        throw new IllegalArgumentException("Missing number");
    }

    String s = raw.trim();
    if (!s.matches("[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?")) {
        throw new IllegalArgumentException("Invalid decimal syntax");
    }

    double value = Double.parseDouble(s);
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Non-finite number");
    }
    return value;
}
```

Đây là **một method minh họa cần đặt bên trong class**, không phải chương trình độc lập. Nó cố ý **không** cho phép `NaN`, `Infinity`, cú pháp hex và hậu tố `f/d`. Chuỗi `"+12.5"` và `"1e3"` được phép; `"1,5"` không được phép.

**Giới hạn của helper:** nó vẫn có thể nhận `"1e-4000"` thành `0.0`. Điều đó đúng nếu hợp đồng chỉ yêu cầu **kết quả hữu hạn**, nhưng **không đủ** nếu phải giữ chính xác mọi đầu vào khác 0. Muốn từ chối underflow, so sánh với dữ liệu thập phân gốc bằng `BigDecimal` hoặc đặt quy tắc miền giá trị rõ ràng.

### Nếu cần giữ chính xác decimal gốc

```java
java.math.BigDecimal exact =
        new java.math.BigDecimal("1e-4000");
// Vẫn chứa số dương khác zero dưới dạng BigDecimal
```

`BigDecimal` không nhận trực tiếp `"NaN"` hoặc `"Infinity"` như một giá trị số decimal thông thường. Nếu domain là tiền hoặc số thập phân cần chính xác, hãy dùng `BigDecimal` tạo từ chuỗi hoặc một mô hình số nguyên đơn vị nhỏ nhất, cùng chính sách precision/scale và làm tròn theo hợp đồng.

## 9. Khác biệt giữa parse và định dạng theo locale

`Double.parseDouble("1.5")` cho 1.5 bất kể locale máy. Nhưng người dùng có thể nhập số theo quy tắc địa phương, chẳng hạn `"1,5"`, dấu phân tách nhóm hoặc ký tự số khác ASCII.

Nếu hợp đồng thật sự cho phép định dạng địa phương, có thể sử dụng `java.text.NumberFormat`/`DecimalFormat` theo `Locale` đã được chỉ rõ. Tuy nhiên, các API đó có quy tắc riêng cho dấu, grouping, ký tự đặc biệt, các giá trị NaN/Infinity và có thể **parse một phần chuỗi rồi dừng**. Ứng dụng nên dùng `ParsePosition` hoặc cơ chế tương đương để xác nhận **toàn bộ đầu vào đã được tiêu thụ**, thay vì xem parse trả một `Number` là đủ.

Ví dụ minh họa:

```java
java.text.NumberFormat parser =
        java.text.NumberFormat.getNumberInstance(java.util.Locale.GERMANY);
java.text.ParsePosition pos = new java.text.ParsePosition(0);
String input = "1,5";
Number result = parser.parse(input, pos);

boolean complete = result != null && pos.getIndex() == input.length();
// complete == true; result.doubleValue() == 1.5
```

Đây là **một đoạn method minh họa**, không phải chương trình độc lập. Dữ liệu tài chính vẫn cần chọn bộ parse decimal, grouping, scale và chính sách thập phân phù hợp; `NumberFormat` tự thân không đảm bảo mọi con số đều chính xác về nghiệp vụ.

## 10. Tránh để giá trị đặc biệt lan truyền âm thầm

Nếu chấp nhận NaN/Infinity ngoài ý muốn, các phép toán sau có thể tạo thêm kết quả không hữu hạn:

```java
double rate = Double.parseDouble("Infinity");
double cost = rate * 10.0; // Infinity

double undefined = Double.parseDouble("NaN");
double total = undefined + 100.0; // NaN
```

Các phép so sánh với NaN cũng dễ gây sai logic:

```java
double x = Double.NaN;
System.out.println(x > 0.0);  // false
System.out.println(x <= 0.0); // false
System.out.println(x == x);   // false
```

Nếu rule chỉ kiểm tra `x <= limit` để từ chối giá trị lớn, NaN có thể **đi qua kiểm tra** vì cả phép so sánh nhỏ hơn/lớn hơn thông thường với NaN đều false. Hãy kiểm tra `Double.isFinite(x)` trước các phép so sánh miền giá trị.

Khi truyền dữ liệu qua JSON hoặc cơ sở dữ liệu, không giả định mọi hệ thống sẽ tiếp nhận trực tiếp chuỗi hoặc giá trị đặc biệt `NaN`/`Infinity`. Giao thức và schema phải định nghĩa rõ cách biểu diễn hoặc từ chối chúng.

### `NaN` và dấu không phải lỗi dấu phẩy

Không nên “lọc sạch mọi ký tự không phải chữ số và dấu chấm” như một cách xác thực. Cách ấy có thể biến `"-Infinity"`, `"-1e-4000"` hoặc `"+1.5"` thành dữ liệu khác mà người dùng không nhập. Hãy áp dụng **ngữ pháp cho phép cụ thể**, sau đó kiểm tra miền giá trị.

## 11. Chương trình Java 17+ độc lập

Tạo file **`FloatingInputDemo.java`**:

```java
public class FloatingInputDemo {
    static double parseFiniteDecimal(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Missing number");
        }
        String s = raw.trim();
        if (!s.matches("[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?")) {
            throw new IllegalArgumentException("Invalid decimal syntax");
        }
        double value = Double.parseDouble(s);
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("Non-finite number");
        }
        return value;
    }

    static String status(String raw) {
        try {
            return Double.toString(parseFiniteDecimal(raw));
        } catch (IllegalArgumentException ex) {
            return "REJECTED";
        }
    }

    public static void main(String[] args) {
        System.out.println("nan=" + Double.parseDouble("NaN"));
        System.out.println("plusNan=" + Double.parseDouble("+NaN"));
        System.out.println("minusNan=" + Double.parseDouble("-NaN"));
        System.out.println("plusInfinity=" +
                Double.parseDouble("+Infinity"));
        System.out.println("minusInfinity=" +
                Double.parseDouble("-Infinity"));

        double plusZero = Double.parseDouble("+0");
        double minusZero = Double.parseDouble("-0");
        System.out.println("zeroEquals=" + (plusZero == minusZero));
        System.out.println("positiveReciprocal=" + (1.0 / plusZero));
        System.out.println("negativeReciprocal=" + (1.0 / minusZero));
        System.out.println("minusZeroBits=" +
                Long.toHexString(Double.doubleToRawLongBits(minusZero)));

        System.out.println("withWhitespace=" +
                Double.parseDouble("  +1.5  "));
        System.out.println("hexFloating=" +
                Double.parseDouble("0x1.8p1"));
        System.out.println("suffixFloat=" +
                Double.parseDouble("1.25f"));

        double large = Double.parseDouble("1e400");
        double tinyNegative = Double.parseDouble("-1e-4000");
        System.out.println("doubleOverflow=" + large);
        System.out.println("doubleUnderflow=" + tinyNegative);
        System.out.println("floatOverflow=" + Float.parseFloat("1e40"));
        System.out.println("doubleFinite=" +
                Double.isFinite(Double.parseDouble("1e40")));
        System.out.println("overflowIsFinite=" + Double.isFinite(large));
        System.out.println("nanDetected=" +
                Double.isNaN(Double.parseDouble("NaN")));
        System.out.println("underflowIsFinite=" +
                Double.isFinite(tinyNegative));

        System.out.println("validDecimal=" + status("+12.5"));
        System.out.println("validExponent=" + status("1e3"));
        System.out.println("rejectNan=" + status("NaN"));
        System.out.println("rejectInfinity=" + status("-Infinity"));
        System.out.println("rejectOverflow=" + status("1e400"));
        System.out.println("rejectComma=" + status("1,5"));
        System.out.println("rejectUnderscore=" + status("1_000.0"));
        System.out.println("rejectHex=" + status("0x1.8p1"));
        System.out.println("underflowAllowed=" + status("1e-4000"));
        System.out.println("nullInput=" + status(null));

        try {
            Double.parseDouble("infinity");
            System.out.println("lowercaseInfinity=ACCEPTED");
        } catch (NumberFormatException ex) {
            System.out.println("lowercaseInfinity=REJECTED");
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac FloatingInputDemo.java
java FloatingInputDemo
```

Kết quả chuẩn:

```text
nan=NaN
plusNan=NaN
minusNan=NaN
plusInfinity=Infinity
minusInfinity=-Infinity
zeroEquals=true
positiveReciprocal=Infinity
negativeReciprocal=-Infinity
minusZeroBits=8000000000000000
withWhitespace=1.5
hexFloating=3.0
suffixFloat=1.25
doubleOverflow=Infinity
doubleUnderflow=-0.0
floatOverflow=Infinity
doubleFinite=true
overflowIsFinite=false
nanDetected=true
underflowIsFinite=true
validDecimal=12.5
validExponent=1000.0
rejectNan=REJECTED
rejectInfinity=REJECTED
rejectOverflow=REJECTED
rejectComma=REJECTED
rejectUnderscore=REJECTED
rejectHex=REJECTED
underflowAllowed=0.0
nullInput=REJECTED
lowercaseInfinity=REJECTED
```

Các dòng `doubleOverflow`/`doubleUnderflow` cho thấy **đúng cú pháp không đủ bảo đảm giá trị nguồn được giữ nguyên**. `rejectInfinity` và `rejectOverflow` chứng minh việc áp dụng hợp đồng “chỉ nhận hữu hạn”; dòng `underflowAllowed` là giới hạn có chủ đích của helper — muốn tránh mất số rất nhỏ thì phải có kiểm tra bổ sung.

## 12. Lỗi phổ biến và checklist

| Hiểu nhầm | Giải thích đúng |
| --- | --- |
| “`Double.parseDouble` chỉ nhận số hữu hạn.” | Nhận `NaN`, `±Infinity` và các giá trị bị overflow thành Infinity. |
| “`NaN` phải viết không có dấu.” | `+NaN` và `-NaN` có thể được nhận nhưng kết quả vẫn là NaN, không có thứ tự số học. |
| “`infinity` hoặc `Inf` giống `Infinity`.” | Không; parser phân biệt chính xác cú pháp được định nghĩa. |
| “`-0` parse thành zero dương.” | Với parser số thực, có thể giữ âm zero, phân biệt ở bit và phép chia. |
| “Chỉ cần bắt `NumberFormatException` là có số hợp lệ.” | Chuỗi `1e400` đúng cú pháp vẫn tạo Infinity. |
| “Kiểm tra `Double.isFinite` bảo đảm không mất dữ liệu.” | Underflow có thể tạo zero hữu hạn; precision cũng có thể làm tròn. |
| “`Double.isNaN(x)` và `x == Double.NaN` tương đương.” | Không; phép `==` với NaN luôn false. |
| “`parseDouble` tự đọc số dấu phẩy theo locale.” | Không; parser dùng dấu chấm và ngữ pháp độc lập locale. |
| “Literal Java `1_000.0` và chuỗi `"1_000.0"` đều parse được.” | Literal trong mã nguồn cho phép underscore; parser chuỗi không. |
| “Nhìn `-Infinity` có thể suy ra lỗi xuất phát từ chia cho 0.” | Không; overflow và các phép tính khác cũng có thể tạo vô cực. |
| “Có thể tự xóa dấu và ký tự không phải số rồi parse.” | Có thể âm thầm làm sai nghĩa đầu vào; kiểm tra bằng ngữ pháp đúng và báo lỗi rõ. |

Checklist khi nhận dữ liệu số thực từ bên ngoài:

1. **Xác định định dạng hợp đồng**: cho phép dấu `+/-`, exponent, whitespace, số hex, hậu tố literal, grouping/locale, hay các giá trị đặc biệt?
2. **Chọn kiểu số thích hợp**: `float`, `double` hoặc `BigDecimal` nếu cần decimal chính xác.
3. **Kiểm tra `null`, cú pháp và khoảng cho phép** thay vì giả định parser xử lý toàn bộ.
4. **Nếu chỉ chấp nhận hữu hạn**, dùng `Double.isFinite`/`Float.isFinite` sau parse.
5. **Nếu phải giữ đầu vào khác 0**, phát hiện trường hợp underflow trở thành zero, ví dụ bằng kiểm tra miền hoặc đối chiếu decimal gốc.
6. **Nếu dấu zero có ý nghĩa**, đừng chuẩn hóa âm zero không chủ đích; nếu không có ý nghĩa, chuẩn hóa nhất quán và ghi rõ.
7. **Đừng để NaN vượt qua so sánh miền giá trị**: kiểm tra tính hữu hạn trước, vì các phép `<`, `>`, `<=`, `>=` với NaN đều false.
8. **Khi định dạng lại hoặc truyền sang hệ khác**, kiểm tra định nghĩa của giao thức đối với NaN/Infinity; không mặc định mọi JSON schema hay cơ sở dữ liệu đều cho phép.

**Ghi nhớ:** `Double.parseDouble` và `Float.parseFloat` phân tích **cú pháp dấu phẩy động**, không kiểm tra đầy đủ **hợp lệ nghiệp vụ**. `NaN`, `±Infinity`, `±0.0` và sự làm tròn do overflow/underflow là những kết quả cần xử lý có chủ đích.