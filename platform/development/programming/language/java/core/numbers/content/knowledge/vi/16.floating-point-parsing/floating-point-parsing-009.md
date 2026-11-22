# Kiểm tra giá trị hữu hạn và miền dữ liệu sau khi parse trong Java

## 1. Vì sao parse thành công chưa có nghĩa dữ liệu hợp lệ?

Khi chương trình nhận số thực từ form, file cấu hình, CSV hoặc API, bước đầu thường là `Double.parseDouble(String)` hay `Float.parseFloat(String)`. Tuy nhiên **chuyển đổi chuỗi thành công chỉ chứng tỏ chuỗi được chấp nhận theo cú pháp số thực Java**; nó không đảm bảo kết quả phù hợp với miền dữ liệu, ý nghĩa nghiệp vụ hoặc yêu cầu về độ chính xác.

Ví dụ:

~~~java
double normal = Double.parseDouble("12.5");
double nan = Double.parseDouble("NaN");
double inf = Double.parseDouble("Infinity");
double overflow = Double.parseDouble("1e309");
double tiny = Double.parseDouble("1e-400");
~~~

Các lời gọi trên đều có thể hoàn thành **không ném `NumberFormatException`**. Nhưng:

- `normal` bằng 12,5 và hữu hạn.
- `nan` mang giá trị `NaN` (*Not a Number*).
- `inf` và `overflow` mang giá trị `+Infinity`.
- `tiny` bằng `0.0` do kết quả thập phân khác 0 quá nhỏ để biểu diễn dưới dạng `double`.

Do vậy, quy trình tin cậy là **đọc chuỗi → parse → kiểm tra tính hữu hạn → kiểm tra miền nghiệp vụ → kiểm tra thêm các điều kiện độ chính xác nếu cần → sử dụng**. Bài học tập trung vào từng bước và những lỗi khó thấy trong mã Java 17+.

## 2. Hai phương thức parse số thực thông dụng

| API | Trả về | Miền biểu diễn | Phản ứng với chuỗi sai cú pháp |
| --- | --- | --- | --- |
| `Double.parseDouble(text)` | `double` primitive | IEEE 754 binary64 | Ném `NumberFormatException` |
| `Float.parseFloat(text)` | `float` primitive | IEEE 754 binary32 | Ném `NumberFormatException` |
| `Double.valueOf(text)` | `Double` wrapper | Tương tự `double` | Ném `NumberFormatException` |
| `Float.valueOf(text)` | `Float` wrapper | Tương tự `float` | Ném `NumberFormatException` |

Ví dụ:

~~~java
double a = Double.parseDouble("3.14");
float b = Float.parseFloat("3.14");
Double wrapped = Double.valueOf("3.14");
~~~

Đây là đoạn minh họa đặt trong một phương thức, không phải một chương trình Java hoàn chỉnh. `parseDouble` và `parseFloat` trả **primitive**; `valueOf` trả **wrapper**. Dù dùng API nào, dữ liệu ngoài miền nghiệp vụ hoặc `NaN`/`Infinity` vẫn cần kiểm tra riêng.

`NumberFormatException` chỉ nói rằng quá trình chuyển chuỗi thất bại vì cú pháp; không nên coi việc **không** bắt được ngoại lệ này là một xác nhận dữ liệu “sạch”.

### Những chuỗi Java có thể parse được

~~~java
System.out.println(Double.parseDouble("-12.5"));  // -12.5
System.out.println(Double.parseDouble("1e3"));    // 1000.0
System.out.println(Double.parseDouble("0x1.8p2")); // 6.0
System.out.println(Double.parseDouble("NaN"));    // NaN
System.out.println(Double.parseDouble("-Infinity")); // -Infinity
~~~

`0x1.8p2` là số thực hexadecimal: `1.8` hệ 16 nhân `2²` nên bằng 6.0. Điều đó cho thấy `Double.parseDouble` chấp nhận **nhiều hơn cú pháp số thập phân đơn giản**.

Trong Java, các dạng `"NaN"` và `"Infinity"` là chuỗi đặc biệt được chấp nhận, nhưng chúng **không phải số hữu hạn**. Nếu API của bạn chỉ cho phép số thập phân thường, hãy đặt chính sách định dạng đầu vào riêng; đừng nhầm “parser Java chấp nhận” với “API nghiệp vụ cho phép”.

## 3. Giá trị hữu hạn, Infinity và NaN

Có ba nhóm kết quả quan trọng sau khi parse:

| Nhóm | Ví dụ | `Double.isFinite(x)` | `Double.isNaN(x)` | `Double.isInfinite(x)` |
| --- | --- | --- | --- | --- |
| Hữu hạn | `0.0`, `-0.0`, `12.5`, `Double.MAX_VALUE` | `true` | `false` | `false` |
| Không phải số | `Double.NaN` | `false` | `true` | `false` |
| Vô cực | `Double.POSITIVE_INFINITY`, `Double.NEGATIVE_INFINITY` | `false` | `false` | `true` |

Dùng `Double.isFinite(x)` để chấp nhận **chỉ số hữu hạn**:

~~~java
double parsed = Double.parseDouble("NaN");

if (!Double.isFinite(parsed)) {
    throw new IllegalArgumentException("Giá trị phải hữu hạn");
}
~~~

Với `float`, dùng `Float.isFinite(value)`, `Float.isNaN(value)`, `Float.isInfinite(value)`. Những phương thức này hoạt động với giá trị primitive, không phụ thuộc vào cách chuỗi đầu vào được viết.

**Lưu ý:** `Double.isFinite` trả `true` với `0.0`, `-0.0` và cả các số `subnormal` rất nhỏ. Nó chỉ loại `NaN` và `±Infinity`; không có nghĩa số nằm trong phạm vi hợp lệ hoặc được chuyển đổi mà không mất thông tin.

## 4. Trường hợp overflow: parse hợp lệ nhưng cho Infinity

`double` có giá trị hữu hạn lớn nhất là `Double.MAX_VALUE`, xấp xỉ `1.7976931348623157E308`. `float` có giới hạn thấp hơn, `Float.MAX_VALUE` xấp xỉ `3.4028235E38`.

~~~java
double farTooLarge = Double.parseDouble("1e309");
float tooLargeFloat = Float.parseFloat("1e39");

System.out.println(farTooLarge); // Infinity
System.out.println(tooLargeFloat); // Infinity
System.out.println(Double.isFinite(farTooLarge)); // false
System.out.println(Float.isFinite(tooLargeFloat)); // false
~~~

Kết quả không phải `NumberFormatException`. Chuỗi có cú pháp số thực hợp lệ, nhưng giá trị vượt miền biểu diễn và được làm tròn thành vô cực.

Nếu ứng dụng chấp nhận một số dương hữu hạn trong miền từ 0 đến 100 thì `"1e309"` phải bị từ chối, dù đã parse thành công. Nếu dữ liệu không được phép là vô cực, **bắt `NumberFormatException` là chưa đủ**.

Một số âm có độ lớn cực lớn như `"-1e309"` có thể cho `-Infinity`. `Double.isFinite` loại cả hai dấu.

## 5. Underflow, subnormal và giá trị 0 sau khi parse

Ở đầu gần số 0, hệ dấu phẩy động có giới hạn biểu diễn:

- `Double.MIN_NORMAL` là số `double` *normal* dương nhỏ nhất, khoảng `2.2250738585072014E-308`.
- `Double.MIN_VALUE` là **số `double` dương khác 0 nhỏ nhất**, khoảng `4.9E-324`, thuộc nhóm *subnormal*.
- Số dương nhỏ hơn cả `Double.MIN_VALUE` có thể bị làm tròn về `0.0`; số âm tương ứng có thể thành `-0.0`.

~~~java
double subnormal = Double.parseDouble("4.9e-324");
double tiny = Double.parseDouble("1e-400");
double negativeTiny = Double.parseDouble("-1e-400");

System.out.println(subnormal == Double.MIN_VALUE); // true
System.out.println(tiny); // 0.0
System.out.println(negativeTiny); // -0.0
System.out.println(Double.isFinite(tiny)); // true
~~~

Đặc biệt, `"1e-400"` về mặt toán học là số **dương khác 0**, nhưng khi lưu vào `double` trở thành **0.0**. Vì `0.0` vẫn hữu hạn, `isFinite` không phát hiện được sự mất giá trị này.

**Không đánh đồng hai câu hỏi:**

1. Giá trị `double` cuối cùng có hữu hạn không?
2. Giá trị số trong chuỗi gốc có được bảo toàn đủ chính xác khi chuyển sang `double` không?

Câu hỏi thứ hai không thể luôn trả lời chỉ bằng một `double` đã parse xong. Nếu yêu cầu tuyệt đối không biến một giá trị thập phân khác 0 thành 0, cần kiểm tra chuỗi đầu vào hoặc dùng kiểu có độ chính xác phù hợp trước khi chuyển.

## 6. Kiểm tra miền dữ liệu sau khi xác nhận hữu hạn

Giả sử API nhận nhiệt độ trong phạm vi từ −40°C đến 85°C, gồm cả hai đầu mút. Phép kiểm tra cơ bản:

~~~java
double value = Double.parseDouble(text);

if (!Double.isFinite(value)) {
    throw new IllegalArgumentException("Nhiệt độ phải là số hữu hạn");
}
if (value < -40.0 || value > 85.0) {
    throw new IllegalArgumentException("Nhiệt độ ngoài [-40, 85]");
}
~~~

Đoạn này là phần **minh họa trong một phương thức**, nơi `text` đã được cung cấp trước. Thứ tự kiểm tra không phải trang trí: kiểm tra tính hữu hạn trước khiến chính sách từ chối `NaN`/`Infinity` minh bạch.

### Vì sao chỉ kiểm tra x < min || x > max là chưa đủ?

Mọi phép so sánh thứ tự `<`, `>`, `<=`, `>=` với `NaN` đều cho `false`. Vì vậy:

~~~java
double value = Double.NaN;
boolean outside = value < -40.0 || value > 85.0;

System.out.println(outside); // false
~~~

Nếu chỉ viết `if (outside) reject`, chương trình sẽ **chấp nhận nhầm NaN**. Đây là lỗi validation rất quan trọng khi parse dữ liệu số thực.

Có thể thiết kế `if (!Double.isFinite(value) || value < min || value > max) reject`. Biểu thức sử dụng `||` đánh giá ngắn mạch; viết riêng bước kiểm tra thường dễ đọc và dễ báo lỗi nguyên nhân hơn.

### Biên đóng và biên mở

Tùy yêu cầu nghiệp vụ:

- `min <= value && value <= max`: miền đóng, nhận hai biên.
- `min < value && value < max`: miền mở, không nhận hai biên.
- `value > 0`: nhận giá trị dương thực sự, từ chối `0.0` và `-0.0`.
- `value >= 0`: nhận cả `0.0` và `-0.0` vì hai số 0 so sánh bằng nhau theo toán tử số học.

Kiểm tra hữu hạn **không thay thế** bước chọn miền đóng/mở, yêu cầu số nguyên hay quy tắc với số 0.

## 7. Hàm parseFiniteInRange thực tế trên Java 17

Một thiết kế đơn giản có thể tái sử dụng:

~~~java
static double parseFiniteInRange(String text, double min, double max) {
    if (!Double.isFinite(min) || !Double.isFinite(max) || min > max) {
        throw new IllegalArgumentException("Invalid finite bounds");
    }
    if (text == null) {
        throw new IllegalArgumentException("Missing numeric text");
    }

    final double value;
    try {
        value = Double.parseDouble(text);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Malformed numeric text", ex);
    }

    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Value must be finite");
    }
    if (value < min || value > max) {
        throw new IllegalArgumentException("Value outside bounds");
    }
    return value;
}
~~~

Phương thức này là **một method ở cấp lớp**, chưa phải chương trình chạy độc lập. Nó thể hiện bốn hợp đồng:

1. Miền cấu hình phải là hai giá trị hữu hạn và `min <= max`.
2. Chuỗi đầu vào không được `null`.
3. Văn bản phải parse được theo `Double.parseDouble`.
4. Kết quả parse phải hữu hạn và nằm trong miền đóng `[min, max]`.

`IllegalArgumentException` là lựa chọn thông báo lỗi ở ranh giới API; bạn cũng có thể định nghĩa exception riêng nếu hệ thống cần phân loại lỗi cấu hình/validation. Cần chú ý `NumberFormatException` chính là một lớp con của `IllegalArgumentException`, vì vậy mã gọi có thể bắt chung nếu muốn hiển thị một thông báo lỗi thống nhất.

### Mẫu Java cho Float

~~~java
static float parseFiniteFloat(String text, float min, float max) {
    if (!Float.isFinite(min) || !Float.isFinite(max) || min > max) {
        throw new IllegalArgumentException("Invalid bounds");
    }
    if (text == null) {
        throw new IllegalArgumentException("Missing numeric text");
    }

    final float value;
    try {
        value = Float.parseFloat(text);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Malformed float text", ex);
    }
    if (!Float.isFinite(value) || value < min || value > max) {
        throw new IllegalArgumentException("Float outside valid range");
    }
    return value;
}
~~~

Đây là ví dụ thay thế khi kiểu lưu trữ bắt buộc là `float`. Không tự parse sang `double` rồi ép `(float)` nếu bạn muốn biết chính xác hệ quả chuyển đổi ngay ở kiểu đích; nếu phải ép, hãy kiểm tra lại kết quả `float` sau ép.

## 8. Chương trình Java 17+ hoàn chỉnh

Lưu thành tệp `FiniteParseDemo.java`:

~~~java
public class FiniteParseDemo {
    static double parseFiniteInRange(String text, double min, double max) {
        if (!Double.isFinite(min) || !Double.isFinite(max) || min > max) {
            throw new IllegalArgumentException("Invalid finite bounds");
        }
        if (text == null) {
            throw new IllegalArgumentException("Missing numeric text");
        }

        final double value;
        try {
            value = Double.parseDouble(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Malformed numeric text", ex);
        }
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("Value must be finite");
        }
        if (value < min || value > max) {
            throw new IllegalArgumentException("Value outside bounds");
        }
        return value;
    }

    public static void main(String[] args) {
        System.out.println("normal=" +
                parseFiniteInRange("37.5", 0.0, 100.0));
        System.out.println("negative zero=" +
                parseFiniteInRange("-0.0", 0.0, 100.0));

        String[] rejected = {
            "NaN", "Infinity", "-Infinity", "1e309", "101", "not-a-number"
        };
        for (String text : rejected) {
            try {
                parseFiniteInRange(text, 0.0, 100.0);
                System.out.println("accepted=" + text);
            } catch (IllegalArgumentException ex) {
                System.out.println("rejected=" + text);
            }
        }

        System.out.println("underflow=" +
                parseFiniteInRange("1e-400", 0.0, 100.0));
        System.out.println("float overflow finite=" +
                Float.isFinite(Float.parseFloat("1e39")));
        System.out.println("subnormal=" +
                (Double.parseDouble("4.9e-324") == Double.MIN_VALUE));
        System.out.println("hex float=" +
                Double.parseDouble("0x1.8p2"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 FiniteParseDemo.java
java FiniteParseDemo
~~~

Stdout:

~~~text
normal=37.5
negative zero=-0.0
rejected=NaN
rejected=Infinity
rejected=-Infinity
rejected=1e309
rejected=101
rejected=not-a-number
underflow=0.0
float overflow finite=false
subnormal=true
hex float=6.0
~~~

Đọc kết quả đúng:

- `"37.5"` là số hữu hạn thuộc `[0, 100]` nên được chấp nhận.
- `"-0.0"` vẫn thuộc miền đóng này vì theo phép so sánh số học `-0.0 == +0.0`. Nếu dấu zero có nghĩa nghiệp vụ, cần kiểm tra riêng.
- `"NaN"`, `"Infinity"` và `"1e309"` được parser chấp nhận dưới dạng giá trị dấu phẩy động đặc biệt nhưng bị validation từ chối.
- `"101"` là số hữu hạn nhưng **ngoài miền** nên bị từ chối.
- `"not-a-number"` không đúng cú pháp parse, được chuyển thành lỗi validation.
- `"1e-400"` cho `0.0` và **vẫn được chấp nhận** vì logic ở đây chỉ yêu cầu *hữu hạn* và *trong [0, 100]*. Đây là điểm cần bổ sung nếu nghiệp vụ yêu cầu bảo toàn mọi giá trị dương nhỏ.
- `Float.parseFloat("1e39")` trả Infinity nên `Float.isFinite` trả false.
- `"4.9e-324"` được làm tròn thành số subnormal dương nhỏ nhất; số thực hexadecimal `0x1.8p2` bằng 6.0.

## 9. Khi nào cần từ chối underflow thành zero?

Giả sử bạn xử lý xác suất **bắt buộc lớn hơn 0**. Khi đó:

~~~java
double probability = Double.parseDouble("1e-400");
if (!Double.isFinite(probability) ||
        probability <= 0.0 || probability > 1.0) {
    throw new IllegalArgumentException("Probability must be in (0, 1]");
}
~~~

Đoạn trên từ chối đầu vào vì kết quả đã thành 0.0, đúng với hợp đồng “giá trị `double` cuối cùng phải lớn hơn 0”. Tuy nhiên, nếu mục tiêu là lưu **mọi xác suất decimal dương khác 0** dù rất nhỏ, `double` không đủ miền biểu diễn.

### Dùng BigDecimal nếu phải giữ giá trị decimal nhỏ chính xác

~~~java
java.math.BigDecimal exact = new java.math.BigDecimal("1e-400");
double narrowed = exact.doubleValue();

System.out.println(exact.signum() > 0); // true
System.out.println(narrowed);           // 0.0
~~~

`BigDecimal` giữ giá trị decimal trong ví dụ này; ép về `double` khiến nó mất thông tin. Việc dùng `BigDecimal` cần quyết định từ **trước khi parse** dữ liệu thành `double` — không thể dùng `BigDecimal.valueOf(0.0)` để khôi phục giá trị `1e-400` ban đầu.

Nếu bắt buộc dùng `double` nhưng muốn phát hiện chính sách “đầu vào decimal khác 0 không được thành 0”, có thể parse `BigDecimal` từ chuỗi ở bước đầu, kiểm tra `signum()` rồi so với kết quả `doubleValue()`. Điều này phải đi kèm định nghĩa định dạng được chấp nhận: `BigDecimal` không hỗ trợ chuỗi `NaN`/`Infinity` giống `Double.parseDouble`.

## 10. Không nên chỉ dựa vào Double.isFinite khi kiểm tra độ chính xác

Một số hữu hạn vẫn có thể mất chữ số đáng kể khi parse:

~~~java
double rounded = Double.parseDouble("9007199254740993");
System.out.println(rounded == 9007199254740992.0); // true
~~~

`9007199254740993 = 2⁵³ + 1` không thể biểu diễn chính xác bằng binary64 và được làm tròn thành `9007199254740992`. `Double.isFinite(rounded)` vẫn trả true.

Nếu trường dữ liệu là mã định danh, số nguyên đếm được, số tiền hoặc lượng decimal yêu cầu chính xác tuyệt đối, hãy dùng loại dữ liệu phù hợp:

- `long` hoặc `BigInteger` cho số nguyên (tùy miền và quy tắc kiểm tra).
- `BigDecimal` cho số decimal cần độ chính xác thập phân.
- `double`/`float` khi chấp nhận mô hình dấu phẩy động xấp xỉ và đã quy định tolerance.

**Không nhầm tính hữu hạn với tính chính xác.** Đây là hai trục kiểm tra độc lập: một số có thể hữu hạn nhưng bị làm tròn; một chuỗi có thể parse hợp lệ nhưng tạo Infinity; một số có thể hữu hạn, chính xác theo kiểu `double` nhưng vẫn ngoài miền nghiệp vụ.

## 11. Kiểm tra chuỗi đầu vào: null, rỗng, whitespace và định dạng

`Double.parseDouble`/`Float.parseFloat` có quy tắc cú pháp riêng. Trên Java 17, parser chấp nhận whitespace đầu/cuối được loại như `String.trim()` trước khi phân tích, nhưng không chấp nhận các dấu gạch dưới dùng trong literal mã nguồn:

~~~java
System.out.println(Double.parseDouble(" 12.5 ")); // 12.5
// Double.parseDouble("1_000"); // Ném NumberFormatException.
~~~

Điểm này dẫn tới lựa chọn thiết kế:

- Nếu hệ thống cho phép người dùng thêm khoảng trắng, có thể chấp nhận theo hành vi parser.
- Nếu hệ thống đòi định dạng chặt như “chỉ chữ số thập phân, dấu chấm và dấu âm” hoặc cấm hex, NaN, suffix, phải **xác thực cú pháp** theo hợp đồng riêng.
- Nếu dữ liệu có thể là `null`, phải kiểm tra trước; `Double.parseDouble(null)` ném `NullPointerException`, không phải `NumberFormatException`.
- Với chuỗi rỗng hoặc sai dạng, bắt `NumberFormatException` và cung cấp thông báo lỗi phù hợp.

Không nên áp dụng regex tự chế thiếu kiểm thử rồi cho rằng đã bao phủ mọi định dạng Unicode, số mũ, dấu hoặc dạng thập phân. Xác định đúng grammar của API và dùng parser phù hợp.

### Không dùng locale để suy đoán dấu thập phân

`Double.parseDouble("12.5")` dùng dấu chấm theo cú pháp Java, không tự hiểu chuỗi dùng dấu phẩy decimal theo ngôn ngữ của người dùng. Trong ứng dụng đa ngôn ngữ, cần chuẩn hóa dữ liệu có quy tắc hoặc dùng `NumberFormat` phù hợp với locale và yêu cầu parse *toàn chuỗi*. Dù dùng phương thức nào, bước **kiểm tra hữu hạn và miền** vẫn cần được thực hiện sau khi có kết quả số.

## 12. Miền hợp lệ: từ yêu cầu nghiệp vụ đến điều kiện Java

Bảng ví dụ (các giới hạn minh họa, không áp đặt cho mọi hệ thống):

| Trường | Miền giả định | Kiểm tra |
| --- | --- | --- |
| Phần trăm | 0 đến 100, gồm hai đầu | `isFinite(x) && x >= 0 && x <= 100` |
| Xác suất | 0 đến 1, gồm hai đầu | `isFinite(x) && x >= 0 && x <= 1` |
| Xác suất bắt buộc dương | Lớn hơn 0, đến 1 | `isFinite(x) && x > 0 && x <= 1` |
| Nhiệt độ thiết bị | −40 đến 85 | `isFinite(x) && x >= -40 && x <= 85` |
| Khối lượng sản phẩm | Lớn hơn 0, không vượt max | `isFinite(x) && x > 0 && x <= max` với max hữu hạn đã xác thực |
| Điểm tọa độ / vector | Miền do định nghĩa nghiệp vụ | Xác thực từng thành phần và tính hợp lệ tổng thể |

Các biểu thức trên **không thể dùng nguyên xi** nếu `x` hoặc `max` là wrapper có thể bằng `null`: phải có null guard trước khi unbox.

Ngoài miền số học, cần kiểm tra quy tắc nghiệp vụ khác, như số phải là số nguyên, độ phân giải đo, giới hạn tổng các thành phần, ràng buộc liên trường và đơn vị. Ví dụ giá trị `37.5` có thể hợp lệ với nhiệt độ nhưng không phù hợp cho “số lượng thiết bị nguyên”.

### Về ±0.0

`Double.parseDouble("-0.0")` là số **hữu hạn**, và `-0.0 == 0.0` là true. Nếu nghiệp vụ yêu cầu không cho “âm” ở mức bit, `value >= 0` không phân biệt được `-0.0`; có thể kiểm tra dấu bằng `Double.doubleToRawLongBits(value)` hoặc dùng chính sách chuẩn hóa về `0.0`. Chỉ xử lý dấu zero riêng khi thực sự có ý nghĩa; đa số bài toán đếm/đo thông thường không cần.

## 13. Lỗi validation thường gặp

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| Chỉ bắt `NumberFormatException` | `"NaN"`, `"Infinity"`, `"1e309"` parse được | Thêm `Double.isFinite`/`Float.isFinite` |
| Chỉ kiểm tra `x < min || x > max` | `NaN` không thỏa so sánh thứ tự, có thể lọt qua | Kiểm tra `isFinite` trước |
| Nghĩ `isFinite` nghĩa là nằm trong miền | `1e100` hữu hạn nhưng có thể ngoài giới hạn nghiệp vụ | Kiểm tra range độc lập |
| Nghĩ `isFinite` đảm bảo chính xác | Số hữu hạn có thể bị làm tròn | Chọn kiểu dữ liệu và kiểm tra precision phù hợp |
| Dùng `Double.MIN_VALUE` làm số âm nhỏ nhất | Đây là **số dương khác 0** nhỏ nhất | Dùng `-Double.MAX_VALUE` cho cận hữu hạn âm về độ lớn |
| Tự coi `0.0` sau parse luôn là số 0 chính xác của text | `1e-400` có thể bị làm tròn thành 0.0 | Kiểm tra chuỗi decimal gốc khi cần |
| Dùng `value >= 0` để cấm `-0.0` | Hai zero so sánh bằng nhau | Quy định cách kiểm tra dấu zero nếu cần |
| Dùng `Double.parseDouble(null)` trong catch NumberFormatException | `null` gây `NullPointerException` | Null guard |
| Dùng `Float.parseFloat` với miền của double | `float` có miền và precision khác | Xác thực theo kiểu lưu thực tế |
| Không xác thực min/max truyền vào validator | Bounds NaN/Infinity có thể làm logic sai | Kiểm tra cả hai bound hữu hạn và `min <= max` |
| Dùng `double` cho tiền hoặc ID nguyên lớn rồi dựa vào isFinite | Mất độ chính xác dù hữu hạn | `BigDecimal`, `BigInteger` hoặc `long` |
| Bỏ qua locale/đơn vị | Chuỗi khác định dạng hoặc khác thang đo | Quy định grammar, locale và đơn vị tường minh |

## 14. Cách xây dựng validation có thể kiểm thử

Một bộ kiểm thử nên có ít nhất các nhóm:

**Cú pháp:** `"12.5"`, `"-12.5"`, `"abc"`, `""`, `null`, khoảng trắng đầu/cuối, ký tự phân tách số không hợp lệ.

**Giá trị đặc biệt:** `"NaN"`, `"Infinity"`, `"-Infinity"` và một số lớn tạo Infinity như `"1e309"`.

**Miền dữ liệu:** ở đúng min/max, sát phía trong, sát phía ngoài, số âm, số 0 và số vượt giới hạn.

**Biên biểu diễn:** `"1e-400"` thành 0.0, số subnormal nhỏ nhất, `Double.MAX_VALUE`, giá trị lớn hơn `MAX_VALUE` và số có nhiều chữ số cần làm tròn.

**Ngữ nghĩa:** giá trị cần dương nghiêm ngặt, cấm NaN, yêu cầu giá trị nguyên, phân biệt dữ liệu thiếu với số 0, dữ liệu decimal yêu cầu chính xác.

Gợi ý các assertion khi đã có phương thức `parseFiniteInRange`:

~~~java
assert parseFiniteInRange("0", 0, 100) == 0.0;
assert parseFiniteInRange("100", 0, 100) == 100.0;
assert Double.doubleToRawLongBits(
        parseFiniteInRange("-0.0", 0, 100)) ==
        Double.doubleToRawLongBits(-0.0);

// Các trường hợp NaN, Infinity, "101", "abc" phải bị từ chối.
// Với test framework, dùng assertThrows(...) để kiểm tra exception.
~~~

Đây là các câu lệnh minh họa bên trong một phương thức. Từ khóa `assert` của Java chỉ được thực thi khi chạy JVM với `-ea`; với kiểm thử tự động nên dùng assertion của framework như JUnit 5. Các trường hợp chờ exception cần có testcase riêng; không nên suy từ việc thử “happy path” rằng mọi đầu vào sai đều được xử lý.

## 15. Câu hỏi tự kiểm tra

**1.** `Double.parseDouble("NaN")` có ném `NumberFormatException` không?

**Đáp án:** Không. Nó trả `Double.NaN`; phải dùng `Double.isNaN` hoặc `!Double.isFinite` để từ chối theo chính sách chỉ nhận số hữu hạn.

**2.** `Double.parseDouble("1e309")` và `Double.parseDouble("1e-400")` cho những giá trị nào?

**Đáp án:** Theo binary64, trường hợp đầu cho `Infinity` do vượt miền; trường hợp sau cho `0.0` do giá trị quá nhỏ. Cả hai chuỗi có cú pháp số hợp lệ.

**3.** Tại sao `if (x < 0 || x > 100) reject` không đủ nếu x do parse sinh ra?

**Đáp án:** Nếu `x` là `NaN`, cả hai điều kiện đều false, khiến mã không reject. Thêm `Double.isFinite(x)` trước khi so sánh.

**4.** `Double.isFinite(0.0)` và `Double.isFinite(Double.MIN_VALUE)` bằng gì?

**Đáp án:** Cả hai là true. Zero và subnormal dương nhỏ nhất đều là số hữu hạn.

**5.** Nếu đầu vào là xác suất dương `"1e-400"` mà chương trình phải lưu **giá trị decimal khác 0**, chỉ dùng `double` được không?

**Đáp án:** Không. Chuỗi đó bị làm tròn về 0.0 khi chuyển sang binary64. Dùng biểu diễn phù hợp như `BigDecimal` hoặc một mô hình xác suất/logarithm chuyên dụng tùy ứng dụng.

**6.** Nếu parse ra 101 trong khi miền hợp lệ là `[0, 100]`, có cần quan tâm `NumberFormatException` không?

**Đáp án:** Parse đã thành công và 101 là số hữu hạn. Đây là **lỗi miền nghiệp vụ**; cần kiểm tra sau parse và báo lỗi phù hợp.

**7.** Khi cần ngăn `-0.0` nhưng cho phép `0.0`, có dùng `value >= 0` được không?

**Đáp án:** Không, vì `-0.0 == 0.0` theo phép so sánh primitive. Cần kiểm tra dấu zero bằng bit hoặc chuẩn hóa đầu vào theo chính sách rõ ràng.

## 16. Ghi nhớ và nguồn tham khảo

- `Double.parseDouble`/`Float.parseFloat` giải quyết **chuyển cú pháp chuỗi sang floating point**, không tự kiểm tra tính hữu hạn, miền nghiệp vụ hoặc độ chính xác.
- `Double.isFinite`/`Float.isFinite` loại `NaN` và `±Infinity`, nhưng không loại zero hoặc subnormal.
- Kiểm tra **miền số** sau tính hữu hạn, với min/max và đầu mút được quy định rõ; nếu không, `NaN` có thể qua một bộ lọc chỉ dùng dấu so sánh.
- Phải hiểu overflow thành Infinity, underflow thành ±0.0 và rounding của số rất lớn/nhỏ. Không dùng dấu “parse thành công” làm bằng chứng không mất dữ liệu.
- Chọn `double` cho tính toán xấp xỉ theo thiết kế, hoặc dùng `BigDecimal`/`BigInteger`/`long` theo yêu cầu biểu diễn chính xác.

Tài liệu chính thức của Java:

- [Java SE 17 — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): `parseDouble`, `isFinite`, `isNaN`, `isInfinite` và các giá trị biên.
- [Java SE 17 — Float](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html): `parseFloat`, `isFinite` và miền binary32.
- [JLS 17 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): NaN, Infinity, normal/subnormal, signed zero.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): số decimal chính xác với độ chính xác tùy ý.
