# Quy ước xử lý null, NaN, vô cực và giá trị thiếu trong thiết kế dữ liệu số Java

## 1. Một con số không phải lúc nào cũng chỉ là một giá trị

Dữ liệu số đi qua API, form nhập liệu, cơ sở dữ liệu, tệp CSV, JSON, phép đo hoặc phép tính trong Java có thể ở nhiều trạng thái khác nhau. Trước khi chọn `int`, `double` hay `BigDecimal`, cần thống nhất **mỗi trạng thái mang ý nghĩa gì** và **ứng dụng phải xử lý ra sao**.

Ví dụ một cảm biến gửi dữ liệu nhiệt độ:

- `0.0`: thiết bị thực sự đo được 0 độ.
- `null`: không có giá trị được cung cấp trong một trường cho phép null.
- Trường bị **thiếu** trong JSON: phía gửi không đưa trường đó vào; không nhất thiết cùng nghĩa với trường được gửi rõ ràng là `null`.
- `"N/A"`: nguồn gửi chuỗi không có số; có thể là một marker "không áp dụng" hoặc dữ liệu sai, tùy hợp đồng.
- `Double.NaN`: giá trị số chấm động thuộc loại *Not a Number*; không đồng nghĩa với null.
- `Double.POSITIVE_INFINITY` hoặc `Double.NEGATIVE_INFINITY`: giá trị chấm động dương/âm vô cực, có thể xuất hiện từ một số phép toán hay quá trình parse.
- `-0.0`: số 0 âm theo IEEE 754; trong nhiều phép so sánh số học bằng `0.0` nhưng vẫn có khác biệt về biểu diễn và một số phép toán.

**Không có quy tắc phổ quát rằng null = NaN = Infinity = 0 = giá trị thiếu.** Chúng là những trạng thái khác nhau, và quyết định gộp chúng phải xuất phát từ nghiệp vụ.

Mục tiêu của bài này là thiết kế *hợp đồng dữ liệu số* (*numeric data contract*): quy tắc tiếp nhận, biểu diễn, kiểm tra hợp lệ, tính toán, tổng hợp, lưu trữ và xuất dữ liệu khi gặp giá trị đặc biệt.

## 2. Phân biệt các trạng thái quan trọng

| Trạng thái | Ví dụ | Trong Java | Ý nghĩa cần xác định |
|---|---|---|---|
| Số hữu hạn hợp lệ (*finite*) | `12.5`, `0.0`, `-0.0` | `double`, `Double`, `BigDecimal` | Giá trị đo/tính có thể dùng theo đơn vị và precision quy định |
| Thiếu giá trị (*missing*) | Không có trường, `null` theo contract | Wrapper `Double` có thể null; `OptionalDouble.empty()` | Chưa nhận dữ liệu hay không áp dụng? |
| Đầu vào không hợp lệ (*invalid*) | `"abc"` khi bắt buộc là số | Parse ném `NumberFormatException` | Báo lỗi, từ chối hoặc cách ly dữ liệu |
| NaN | `0.0 / 0.0` | `Double.NaN`, `Float.NaN` | Kết quả đặc biệt của số thực, **không** phải missing mặc định |
| Vô cực dương | `1.0 / 0.0` | `Double.POSITIVE_INFINITY` | Có cho phép theo miền bài toán không? |
| Vô cực âm | `-1.0 / 0.0` | `Double.NEGATIVE_INFINITY` | Có cho phép theo miền bài toán không? |
| Giá trị sentinel | `-9999` để chỉ dữ liệu thiếu | `int`/`long`/`double` | Chỉ an toàn nếu sentinel ngoài miền hợp lệ và contract rõ |
| Giá trị mặc định | `0` khi chưa nhập | Do ứng dụng tự tạo | Có phân biệt được "chưa nhập" với "thực sự bằng 0" không? |

Một ứng dụng có thể phân chia khác bảng này, nhưng **phải công bố và thực thi nhất quán**. Ví dụ trong đo lường khoa học, vô cực đôi khi được giữ để phân tích; trong nghiệp vụ tiền tệ, cả NaN lẫn Infinity phải bị từ chối.

### Trường thiếu và trường có giá trị null có giống nhau không?

Không nhất thiết. Xét hai payload minh họa:

~~~json
{"sensorId":"T-01"}
~~~

~~~json
{"sensorId":"T-01","temperature":null}
~~~

Payload thứ nhất không có khóa `temperature`; payload thứ hai có khóa nhưng giá trị là JSON `null`. Một thư viện deserialize vào DTO có thể biến cả hai thành trường Java `null`, vì vậy **mất khả năng phân biệt trạng thái** nếu không lưu thông tin về sự hiện diện của trường. Nếu API phân biệt "không cập nhật trường" và "xóa giá trị trường" (ví dụ partial update), lớp DTO hoặc bộ đọc phải giữ được sự khác biệt đó.

Tương tự, chuỗi rỗng `""`, chuỗi toàn khoảng trắng, marker `"NA"` và JSON `null` không tự động tương đương. Hãy viết quy tắc chuẩn hóa đầu vào cụ thể, có kiểm thử.

## 3. null và wrapper: có thể lưu, nhưng không thể unbox như một số

Các kiểu primitive `int`, `long`, `double` không thể nhận `null`. Nếu đầu vào thật sự có thể thiếu, lớp wrapper `Integer`, `Long`, `Double`, `BigDecimal` hoặc một kiểu mô hình hóa trạng thái phù hợp hơn.

~~~java
Double measurement = null; // Hợp lệ: chưa có giá trị.
double actual = 0.0;       // Hợp lệ: có giá trị số 0.
~~~

Điểm nguy hiểm là **unboxing tự động**:

~~~java
Double measurement = null;

// Có thể biên dịch, nhưng khi chạy sẽ ném NullPointerException:
// double x = measurement;
// double y = measurement + 1.0;
// boolean ok = measurement > 0.0;
~~~

Unboxing tương đương gọi `measurement.doubleValue()`. Vì receiver là null, chương trình không thể lấy giá trị primitive.

Phải chọn chính sách:

~~~java
Double measurement = null;

// Cách A: thiếu dữ liệu được hiểu là 0 (chỉ dùng khi nghiệp vụ cho phép).
double valueOrZero = measurement == null ? 0.0 : measurement;

// Cách B: bắt buộc có dữ liệu, thiếu thì từ chối.
double required = java.util.Objects.requireNonNull(
        measurement, "measurement is required");
~~~

Trong cách B, `requireNonNull` ném `NullPointerException` có thông điệp rõ khi dữ liệu null. Nếu API cần lỗi hợp đồng, có thể kiểm tra và ném exception nghiệp vụ (ví dụ `IllegalArgumentException`) ở ranh giới xử lý.

**Không nên thay mọi null bằng 0 theo thói quen**: thao tác đó khiến báo cáo "có 10 phép đo, một lần bằng 0" không thể phân biệt với "có 9 phép đo, một lần thiếu".

## 4. IEEE 754: NaN và hai dạng vô cực trong double/float

`double` và `float` trong Java theo mô hình số thực chấm động IEEE 754, nên có các giá trị đặc biệt mà `int`/`long` không có.

~~~java
double nan = 0.0 / 0.0;
double positiveInfinity = 1.0 / 0.0;
double negativeInfinity = -1.0 / 0.0;

System.out.println(nan);              // NaN
System.out.println(positiveInfinity); // Infinity
System.out.println(negativeInfinity); // -Infinity
~~~

Đây là phép chia **số thực** vì các toán hạng là `double`. Phân biệt với phép chia số nguyên:

~~~java
// int invalid = 1 / 0; // Biểu thức hằng bị compiler từ chối trong một số ngữ cảnh;
// với phép chia số nguyên tại runtime, chia cho 0 gây ArithmeticException.
~~~

Với các biến số nguyên và mẫu số bằng 0 ở runtime, phép chia ném `ArithmeticException`. Đừng kỳ vọng nó tạo ra `Infinity` như số thực.

### 4.1. Kiểm tra bằng API chính thức

~~~java
double v = Double.NaN;

System.out.println(Double.isNaN(v));      // true
System.out.println(Double.isInfinite(v)); // false
System.out.println(Double.isFinite(v));   // false
~~~

Quy tắc phân loại:

- `Double.isNaN(x)` đúng nếu x là NaN.
- `Double.isInfinite(x)` đúng nếu x là vô cực dương hoặc âm.
- `Double.isFinite(x)` đúng nếu x **không phải NaN và không phải vô cực**.
- `Float` có các phương thức kiểm tra tương tự cho `float`.

Một phép xác thực đầu vào `double` thường bắt đầu bằng:

~~~java
static double requireFinite(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Value must be finite");
    }
    return value;
}
~~~

Nếu miền hợp lệ còn có giới hạn (ví dụ phần trăm từ 0 đến 100), phải kiểm tra cả **độ hữu hạn** và **range**:

~~~java
static double requirePercent(double value) {
    if (!Double.isFinite(value) || value < 0.0 || value > 100.0) {
        throw new IllegalArgumentException("percent out of range");
    }
    return value;
}
~~~

### 4.2. NaN không so sánh như số thông thường

~~~java
double x = Double.NaN;

System.out.println(x == x);      // false
System.out.println(x != x);      // true
System.out.println(x < 100);     // false
System.out.println(x > 100);     // false
System.out.println(x >= 100);    // false
~~~

So sánh quan hệ `<`, `>`, `<=`, `>=` với NaN trả false; so sánh bằng `==` cũng false, kể cả khi so NaN với chính nó. Do đó **không** sử dụng `x == Double.NaN` để phát hiện NaN:

~~~java
double x = Double.NaN;
boolean wrong = x == Double.NaN; // false
boolean right = Double.isNaN(x); // true
~~~

Quy tắc đặc biệt này áp dụng cho phép so sánh primitive. `Double.equals` và `Double.compare` dùng những quy tắc phục vụ object equality/sắp xếp, không hoàn toàn giống `==` với primitive.

### 4.3. Vô cực không tự động nghĩa là lỗi parse

~~~java
double huge = Double.parseDouble("1e400");
System.out.println(huge);                 // Infinity
System.out.println(Double.isInfinite(huge)); // true
~~~

Chuỗi có cú pháp hợp lệ nhưng nằm ngoài phạm vi hữu hạn của `double` có thể được parse thành vô cực. Vì vậy `try/catch NumberFormatException` **chưa đủ** để bảo đảm bạn có một số hữu hạn hợp lệ. Sau parse, vẫn phải gọi `Double.isFinite` nếu nghiệp vụ không cho phép Infinity/NaN.

Java còn nhận chuỗi đặc biệt `"NaN"`, `"Infinity"` và `"-Infinity"` trong `Double.parseDouble`. Có cho phép các chuỗi này xuất hiện ở API của bạn hay không là một quyết định thiết kế, không phải mặc định rằng "parse thành công thì hợp lệ".

## 5. -0.0 và +0.0: gần giống về toán học, vẫn khác trong vài trường hợp

IEEE 754 có dấu cho số 0:

~~~java
double positiveZero = 0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0 / positiveZero);           // Infinity
System.out.println(1.0 / negativeZero);           // -Infinity
System.out.println(Double.compare(-0.0, 0.0));    // -1
~~~

- Phép so sánh primitive `==` coi hai dạng 0 bằng nhau.
- Phép lấy nghịch đảo phân biệt dấu nên cho hai vô cực khác nhau.
- `Double.compare` định nghĩa thứ tự có thể phân biệt `-0.0` và `+0.0`, phục vụ sắp xếp.
- `Double.valueOf(-0.0).equals(Double.valueOf(0.0))` trả false.

Trong nhiều ứng dụng kinh doanh, có thể chuẩn hóa `-0.0` về `+0.0` sau khi xác định rằng dấu của 0 **không có ý nghĩa nghiệp vụ**. Trong tính toán số hoặc khoa học, việc giữ dấu 0 có thể quan trọng.

Ví dụ chuẩn hóa tự nguyện:

~~~java
static double normalizeZero(double x) {
    return x == 0.0 ? 0.0 : x;
}
~~~

Hàm trên giữ mọi giá trị khác 0, bao gồm NaN/Infinity, nên **không** phải bộ lọc số hữu hạn; cần kiểm tra riêng `Double.isFinite` khi cần.

## 6. BigDecimal, BigInteger không có giá trị NaN hoặc Infinity

`BigDecimal` và `BigInteger` mô hình hóa số chính xác theo miền của chúng; chúng **không định nghĩa hằng NaN hay ±Infinity**. Giá trị thiếu vẫn có thể được biểu diễn ở mức **tham chiếu `null`**, nhưng không phải là một giá trị số bên trong đối tượng.

~~~java
import java.math.BigDecimal;

BigDecimal valid = new BigDecimal("123.45");

// Hai dòng sau gây NumberFormatException nếu được thực thi:
// BigDecimal invalidNaN = BigDecimal.valueOf(Double.NaN);
// BigDecimal invalidInfinity = BigDecimal.valueOf(Double.POSITIVE_INFINITY);
~~~

Khi chuyển từ `double` sang `BigDecimal`, nên kiểm tra đầu vào:

~~~java
static BigDecimal fromFiniteDouble(double source) {
    if (!Double.isFinite(source)) {
        throw new IllegalArgumentException("non-finite source");
    }
    return BigDecimal.valueOf(source);
}
~~~

Phương thức `BigDecimal.valueOf(double)` dùng biểu diễn thập phân từ `Double.toString(double)` và chỉ thích hợp khi yêu cầu chấp nhận ý nghĩa của giá trị `double` ban đầu. Đối với số tiền hoặc dữ liệu cần chính xác thập phân từ đầu, parse trực tiếp từ chuỗi là lựa chọn rõ ràng hơn:

~~~java
BigDecimal price = new BigDecimal("0.10");
~~~

Dùng `new BigDecimal(0.1)` sẽ lưu chính xác giá trị nhị phân của `double 0.1`, không phải chính xác 0,1 theo ý nghĩa thập phân. Đây là vấn đề về độ chính xác, **độc lập** với xử lý null/NaN/Infinity.

### Thiết kế phép chia

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal zero = BigDecimal.ZERO;

// one.divide(zero) -> ArithmeticException, không sinh Infinity.
~~~

`BigDecimal.divide` có thể ném `ArithmeticException` khi chia cho 0 hoặc khi yêu cầu biểu diễn thập phân chính xác của phân số vô hạn mà không cung cấp chế độ làm tròn. Không nên tự biến lỗi này thành `null` hoặc NaN nếu đặc tả không yêu cầu.

## 7. Giá trị thiếu: không nên dùng sentinel nếu có mô hình rõ hơn

Một hệ thống cũ có thể lưu số đo thiếu bằng `-1`, `-9999`, `Double.NaN` hoặc chuỗi `"N/A"`. Đó là **sentinel** — giá trị đặc biệt được quy ước thay cho trạng thái.

Rủi ro:

- Sentinel `-1` có thể trở thành giá trị hợp lệ khi miền dữ liệu thay đổi.
- Sentinel `0` trùng với số 0 thật.
- Sentinel NaN bị bỏ qua ở một số phép so sánh nhưng lan truyền sang các phép số học, dễ làm hỏng toàn bộ kết quả.
- Khi trộn nhiều nguồn dữ liệu, các sentinel khác nhau dễ bị hiểu sai.
- Sentinel có thể bị ghi qua hệ thống khác mà không còn metadata mô tả.

Nếu cần biểu diễn "có hoặc không có một số", Java có:

~~~java
import java.util.OptionalDouble;

OptionalDouble missing = OptionalDouble.empty();
OptionalDouble present = OptionalDouble.of(0.0);

System.out.println(missing.isPresent()); // false
System.out.println(present.isPresent()); // true
~~~

`OptionalDouble` biểu diễn **có hoặc không có** giá trị primitive; `OptionalDouble.of(Double.NaN)` vẫn là **có một giá trị NaN**, không phải rỗng:

~~~java
OptionalDouble nanPresent = OptionalDouble.of(Double.NaN);
System.out.println(nanPresent.isPresent()); // true
System.out.println(Double.isNaN(nanPresent.orElseThrow())); // true
~~~

Vì vậy, `OptionalDouble` **không thay thế chính sách kiểm soát NaN/Infinity**. Nó chỉ tách trạng thái vắng mặt khỏi trạng thái hiện diện. Với API hoặc DTO phức tạp, một kiểu `record`/sealed type/enum status có thể biểu đạt nhiều trạng thái hơn.

## 8. Đề xuất hợp đồng dữ liệu số nhất quán

Một quy tắc thiết kế hiệu quả là phân biệt rõ ít nhất bốn nhóm:

1. **FINITE**: đã parse thành công, là số hữu hạn, nằm trong miền cho phép và có đơn vị/precision hợp lệ.
2. **MISSING**: không nhận dữ liệu, theo đúng các marker mà hợp đồng quy định.
3. **INVALID**: có dữ liệu nhưng cú pháp hoặc giá trị không hợp lệ; cần báo lỗi hoặc cách ly.
4. **NON_FINITE**: đã parse thành `double` nhưng là NaN hoặc Infinity; xử lý theo chính sách riêng.

Nếu ứng dụng có nhu cầu phân tích kỹ thuật, nhóm NON_FINITE có thể được tách thành `NAN`, `POS_INFINITY` và `NEG_INFINITY`.

Điều này tránh sai lầm "mọi thứ parse không thành công hoặc không finite thì đổi thành 0".

### Ma trận chính sách cần quyết định

| Trường hợp | Ví dụ | Chính sách đề xuất khi chỉ chấp nhận số hữu hạn |
|---|---|---|
| Thiếu trường | JSON không có khóa | MISSING; báo dữ liệu thiếu, hoặc giữ trạng thái nếu optional |
| JSON null | `"temperature": null` | MISSING hoặc yêu cầu khác được công bố |
| Chuỗi trống | `""`, `" "` | Có thể MISSING nếu hợp đồng chấp nhận, không ngầm định |
| Chuỗi không parse được | `"hello"` | INVALID, thông báo lỗi |
| NaN | `"NaN"`, `0.0/0.0` | Từ chối hoặc lưu trạng thái NAN |
| Vô cực | `"Infinity"`, `1e400` | Từ chối hoặc lưu trạng thái vô cực |
| Số 0 | `"0"` | FINITE; không coi là missing |
| Số âm | `"-7.5"` | FINITE nếu miền cho phép; INVALID nếu đặc tả không cho âm |
| Số ngoài range | `250` cho phần trăm | INVALID, không âm thầm ép về 100 |
| Số hợp lệ nhưng sai đơn vị | `1000` mA khi API yêu cầu A | Chuẩn hóa bằng quy tắc đổi đơn vị hoặc từ chối |

Các ô "đề xuất" chỉ là ví dụ cho một hệ thống **chỉ nhận số hữu hạn**; ứng dụng thật phải ghi rõ dữ liệu nào được phép và trạng thái được giữ ở tầng nào. Đặc biệt với thao tác cập nhật một phần, phân biệt "không gửi trường" và "gửi null để xóa" có thể là yêu cầu bắt buộc.

### Định nghĩa rõ tại ranh giới

Hợp đồng nên trả lời:

- Chuỗi có được `trim()`, cho phép dấu cộng, ký hiệu mũ `E` hoặc khoảng trắng không?
- Có chấp nhận chuỗi `"NaN"`/`"Infinity"` không?
- Số ngoài miền hữu hạn thì từ chối, đánh dấu hay clamp? Không tự clamp nếu chưa có quy định.
- Null và field missing có khác nhau không?
- Giá trị thiếu có tham gia mẫu số của phép tính trung bình không?
- Lỗi parse có làm hỏng cả batch hay chỉ một bản ghi?
- Kết quả sẽ xuất qua JSON, cơ sở dữ liệu, CSV, giao thức nhị phân bằng biểu diễn nào?
- Nếu số tiền, precision/scale và RoundingMode là gì?

Một câu trả lời nhất quán cho các câu hỏi này quan trọng hơn lựa chọn một sentinel "tiện tay".

## 9. Ví dụ Java 17+: phân loại đầu vào mà không đánh đồng các trạng thái

Ví dụ sau mô phỏng một chính sách được định nghĩa cụ thể: `null` hoặc chuỗi chỉ chứa khoảng trắng được coi là `MISSING`; đầu vào không parse được là `INVALID`; NaN và mỗi loại vô cực được **giữ trạng thái riêng**; số hữu hạn mới được đưa vào phép tổng hợp.

Tạo tệp `NumericPolicyDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.DoubleSummaryStatistics;
import java.util.EnumMap;
import java.util.List;
import java.util.Locale;

public class NumericPolicyDemo {

    enum State {
        FINITE, MISSING, INVALID, NAN, POS_INFINITY, NEG_INFINITY
    }

    record Reading(State state, Double value) {}

    static Reading parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return new Reading(State.MISSING, null);
        }

        try {
            double v = Double.parseDouble(raw.trim());

            if (Double.isNaN(v)) {
                return new Reading(State.NAN, null);
            }
            if (v == Double.POSITIVE_INFINITY) {
                return new Reading(State.POS_INFINITY, null);
            }
            if (v == Double.NEGATIVE_INFINITY) {
                return new Reading(State.NEG_INFINITY, null);
            }
            return new Reading(State.FINITE, v);
        } catch (NumberFormatException ex) {
            return new Reading(State.INVALID, null);
        }
    }

    public static void main(String[] args) {
        String[] input = {
            "12.5", null, "NaN", "Infinity", "-Infinity",
            "0", "-0.0", "oops", " "
        };

        EnumMap<State, Integer> counts = new EnumMap<>(State.class);
        List<Reading> valid = new ArrayList<>();

        for (String raw : input) {
            Reading reading = parse(raw);
            counts.merge(reading.state(), 1, Integer::sum);

            if (reading.state() == State.FINITE) {
                valid.add(reading);
            }

            String label = raw == null ? "<null>" : "\"" + raw + "\"";
            String detail = reading.state() == State.FINITE
                    ? "(" + reading.value() + ")"
                    : "";
            System.out.println(label + " => " + reading.state() + detail);
        }

        DoubleSummaryStatistics stats = valid.stream()
                .mapToDouble(r -> r.value())
                .summaryStatistics();

        System.out.printf(Locale.ROOT,
                "finite count=%d sum=%.1f average=%.2f%n",
                stats.getCount(), stats.getSum(), stats.getAverage());
        System.out.println("missing count="
                + counts.getOrDefault(State.MISSING, 0));
        System.out.println("invalid count="
                + counts.getOrDefault(State.INVALID, 0));
        System.out.println("nan count="
                + counts.getOrDefault(State.NAN, 0));
        System.out.println("infinite count="
                + (counts.getOrDefault(State.POS_INFINITY, 0)
                + counts.getOrDefault(State.NEG_INFINITY, 0)));

        System.out.println("NaN == NaN: " + (Double.NaN == Double.NaN));
        System.out.println("Double.compare(-0.0, 0.0): "
                + Double.compare(-0.0, 0.0));
        System.out.println("1.0/0.0: " + (1.0 / 0.0));
        System.out.println("0.0/0.0: " + (0.0 / 0.0));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac NumericPolicyDemo.java
java NumericPolicyDemo
~~~

Kết quả:

~~~text
"12.5" => FINITE(12.5)
<null> => MISSING
"NaN" => NAN
"Infinity" => POS_INFINITY
"-Infinity" => NEG_INFINITY
"0" => FINITE(0.0)
"-0.0" => FINITE(-0.0)
"oops" => INVALID
" " => MISSING
finite count=3 sum=12.5 average=4.17
missing count=2
invalid count=1
nan count=1
infinite count=2
NaN == NaN: false
Double.compare(-0.0, 0.0): -1
1.0/0.0: Infinity
0.0/0.0: NaN
~~~

**Giải thích thiết kế:**

- `Reading.state` nói rõ trạng thái thay vì sử dụng một giá trị sentinel.
- `Reading.value` chỉ khác null đối với trạng thái `FINITE` theo quy tắc của hàm `parse`. Đây là invariant nội bộ của ví dụ; khi dùng trong production, có thể kiểm tra invariant trong constructor hoặc dùng các kiểu dữ liệu riêng biệt để không thể tạo tổ hợp sai như `FINITE + null`.
- `Double.parseDouble` chấp nhận cú pháp `NaN` và `Infinity`; vì vậy code kiểm tra ngay sau parse chứ không chỉ bắt exception.
- `"oops"` là `INVALID`, còn `null`/`" "` là `MISSING` bởi **chính sách của ví dụ**, không phải quy luật Java.
- Ba giá trị hữu hạn là 12.5, 0.0 và -0.0; trung bình là 12.5 / 3, hiển thị với hai chữ số thập phân thành 4.17. Số lần thiếu/không hợp lệ/không hữu hạn được **báo riêng**.
- Lambda `r -> r.value()` có unboxing từ `Double` sang `double`. Trong ví dụ, dữ liệu đã được lọc và do `parse` tạo ra nên chỉ các bản ghi `FINITE` có giá trị khác null mới được đưa vào. Nếu cho phép tạo `Reading` tùy ý ngoài bộ phân loại, cần cưỡng chế invariant để tránh NPE.

Đây là một mô hình minh họa, không phải chuẩn bắt buộc cho mọi dự án. Với nghiệp vụ chỉ chấp nhận số hữu hạn, có thể đơn giản hóa `State` còn `FINITE`, `MISSING`, `INVALID` rồi từ chối Non-finite tại ranh giới theo quy tắc được công bố.

## 10. Tổng hợp số: quyết định số nào được tính vào mẫu số

Giả sử nhận bốn bản ghi: `10.0`, `null`, `20.0`, `30.0`.

- Nếu bỏ qua bản ghi thiếu: trung bình là `(10 + 20 + 30) / 3 = 20`.
- Nếu thay null bằng 0: trung bình là `(10 + 0 + 20 + 30) / 4 = 15`.
- Nếu một bản ghi thiếu phải làm phép tính không hợp lệ: không xuất trung bình mà trả trạng thái lỗi.

Ba kết quả là ba **quy tắc nghiệp vụ khác nhau**. Không có một quy tắc mặc định đúng cho mọi báo cáo.

Một pipeline chỉ tổng hợp số hữu hạn:

~~~java
import java.util.List;

List<Double> readings = java.util.Arrays.asList(
        10.0, null, 20.0, Double.NaN, 30.0, Double.POSITIVE_INFINITY);

var stats = readings.stream()
        .filter(java.util.Objects::nonNull)
        .mapToDouble(Double::doubleValue)
        .filter(Double::isFinite)
        .summaryStatistics();

System.out.println(stats.getCount());   // 3
System.out.println(stats.getSum());     // 60.0
System.out.println(stats.getAverage()); // 20.0
~~~

Phép lọc `Objects::nonNull` ngăn NPE khi unbox. Phép lọc `Double::isFinite` loại NaN/Infinity khỏi **phép tính thống kê**. Nhưng nếu chỉ có thống kê cuối, ta không còn biết bao nhiêu bản ghi bị loại và vì lý do gì. Nếu số lượng thiếu/không hợp lệ quan trọng, phải đếm và lưu lý do riêng trước khi tính.

Đừng gọi `getAverage()` rồi khẳng định luôn có giá trị trung bình: với `DoubleSummaryStatistics`, hãy kiểm tra `getCount()` khi cần phân biệt tập rỗng. Với `DoubleStream.average()`, kết quả là `OptionalDouble`; stream rỗng cho `OptionalDouble.empty()`.

### Nếu không lọc NaN thì sao?

~~~java
double sum = java.util.stream.DoubleStream.of(
        10.0, Double.NaN, 20.0).sum();

System.out.println(Double.isNaN(sum)); // true
~~~

NaN có thể lan truyền khiến tổng/trung bình trở thành NaN. Đây không phải cơ chế đáng tin cậy để "tự bỏ qua dữ liệu thiếu": nó khiến kết quả bị nhiễm NaN, và nếu phía sau dùng phép so sánh thông thường, có thể sinh thêm lỗi logic.

Tương tự, có cả vô cực dương và vô cực âm trong một phép tổng sẽ tạo tình huống kết quả NaN. Một hệ thống nên quyết định trước rằng kết quả không hữu hạn được xem là lỗi, được lưu như trạng thái đặc biệt, hay được phép trong một loại phép tính khoa học.

## 11. Sắp xếp và so sánh: Double.compare không giống ==

Một số thư viện dùng `Double.compare`, comparator hoặc `Double.equals` thay vì toán tử so sánh primitive. Đây là khác biệt rất quan trọng trong thiết kế dữ liệu.

~~~java
double a = Double.NaN;
double b = Double.NaN;

System.out.println(a == b);                // false
System.out.println(Double.compare(a, b));  // 0
System.out.println(Double.valueOf(a).equals(Double.valueOf(b))); // true
~~~

`Double.compare` định nghĩa thứ tự tổng quát để phục vụ so sánh/sắp xếp; nó coi NaN bằng nhau trong phép compare và phân biệt hai dấu của số 0. NaN được xếp lớn hơn các giá trị `double` còn lại theo thứ tự này. Đây là **quy tắc sắp xếp của API**, không phải một mệnh đề rằng NaN bằng NaN trong số học IEEE 754.

Các hệ quả:

- Không dùng `x == Double.NaN` để lọc NaN; dùng `Double.isNaN(x)`.
- Không dựa vào `Double.compare` như phép so sánh số học thông thường khi dữ liệu chứa NaN và dấu của 0.
- Khi sắp xếp dữ liệu, hãy xác định liệu dữ liệu thiếu/NaN phải lên đầu, xuống cuối hay bị tách riêng; nếu cần thứ tự theo nghiệp vụ, viết comparator dựa trên trạng thái thay vì dựa hoàn toàn vào thứ tự mặc định.
- `DoubleStream.min()`/`max()` có xử lý NaN theo API; nếu đầu vào có NaN và muốn cực trị của số **hữu hạn**, lọc `Double.isFinite` trước.

Với `null`, `Comparator.naturalOrder()` không tự xử lý mọi trường hợp an toàn; có thể dùng `Comparator.nullsFirst(...)`/`nullsLast(...)` khi danh sách wrapper thật sự cho phép null và contract đã xác định vị trí của null. Tuy nhiên, một đối tượng có trạng thái riêng thường rõ hơn nếu cần phân biệt null, invalid và nhiều loại non-finite.

## 12. Lưu trữ và truyền qua JSON, CSV, cơ sở dữ liệu

### 12.1. JSON: null hợp lệ, NaN/Infinity không phải số JSON chuẩn

Cú pháp JSON chuẩn hỗ trợ `null` và các số hữu hạn theo cú pháp JSON; các token `NaN`, `Infinity`, `-Infinity` **không phải literal số hợp lệ** trong JSON chuẩn. Ví dụ:

~~~json
{"temperature": null}
~~~

là JSON hợp lệ. Nhưng chuỗi ký tự không đặt dấu nháy như:

~~~text
{"temperature": NaN}
~~~

không phải JSON chuẩn. Một thư viện có thể có tùy chọn không chuẩn hoặc chuyển các giá trị đặc biệt thành chuỗi, nhưng không nên dựa vào hành vi đó giữa các hệ thống.

Nếu ứng dụng cần truyền trạng thái không hữu hạn, cân nhắc mô hình có nhãn:

~~~json
{"temperature":{"state":"NAN","value":null}}
~~~

hoặc nếu hợp đồng chỉ cho phép số hữu hạn thì **từ chối trước khi serialize**. Tránh gửi `"NaN"` như một số rồi kỳ vọng client tự hiểu giống server; chuỗi `"NaN"` là một **string**, không phải JSON number.

### 12.2. CSV: cần quy ước từng cột

CSV không có kiểu null bẩm sinh. Một ô rỗng, `NA`, `NaN` hay `-9999` chỉ mang nghĩa khi có schema:

~~~text
timestamp,reading,status
2026-01-01T00:00:00Z,12.5,FINITE
2026-01-01T00:01:00Z,,MISSING
2026-01-01T00:02:00Z,,NAN
~~~

Tách cột `status` khỏi cột `reading` giúp phân biệt "giá trị thực sự là 0" với "không có giá trị" và "phép đo không hợp lệ". Với batch ingestion, cũng nên lưu dòng/số thứ tự lỗi để có thể truy vết.

### 12.3. Cơ sở dữ liệu: NULL không đồng nghĩa NaN

SQL `NULL` thường biểu diễn trạng thái unknown/absent theo ngữ nghĩa SQL, không phải số 0 hay NaN. Hành vi lưu NaN/Infinity phụ thuộc hệ quản trị cơ sở dữ liệu, driver JDBC và kiểu cột. Không giả định mọi hệ đều lưu được mọi giá trị IEEE 754.

Ví dụ khi đọc một cột nullable bằng JDBC `ResultSet.getDouble(...)`: nếu cột là SQL NULL, giá trị primitive trả về có thể là 0.0, và cần gọi `wasNull()` ngay sau phép đọc liên quan để phân biệt 0 thật với NULL. Có thể dùng API đọc đối tượng phù hợp driver và kiểm tra null tường minh.

Trong hệ thống có bản ghi trạng thái, nên quyết định schema ngay từ đầu: một cột số hữu hạn nullable, thêm cột trạng thái, hoặc một bảng lỗi riêng. Các quyết định này giúp tránh sentinel không được tài liệu hóa lan giữa các dịch vụ.

## 13. Null, NaN và missing trong API: thiết kế kết quả rõ ràng

Đối với một API đo lường, các câu hỏi thiết kế quan trọng gồm:

1. Trường số có **bắt buộc** không? Khi không có giá trị, server trả trạng thái riêng, `null`, bỏ trường hay lỗi?
2. Nếu nhận `NaN`/Infinity, server trả lỗi `400`/mã nghiệp vụ, lưu trạng thái đặc biệt hay chấp nhận?
3. Có cần phân biệt input sai cú pháp với input thiếu?
4. Nếu giá trị vượt range nhưng vẫn hữu hạn, trả INVALID hay có quy tắc điều chỉnh?
5. Khi tính trung bình, tổng, min/max, mẫu số và số bản ghi bị bỏ qua được công bố ra sao?
6. Việc làm tròn và định dạng thập phân diễn ra ở tầng nào, và có làm mất khác biệt giữa missing và 0 không?

Một kiểu miền rõ ràng có thể tách trạng thái khỏi giá trị, chẳng hạn `Reading(State status, Double finiteValue)`. Đối với ứng dụng cần bảo đảm **không thể có trạng thái FINITE với null**, nên áp dụng kiểm tra trong constructor hoặc dùng mô hình kiểu phân biệt với các lớp/record riêng cho mỗi trạng thái. Ví dụ Java 17 có `sealed interface` để mô hình hóa các trạng thái dữ liệu; không cần bắt mọi trường hợp dùng duy nhất `Double` nullable.

### Ghi lại lý do thay vì chỉ loại bản ghi

Nếu ingest 1.000 bản ghi và chỉ có 960 bản ghi hữu hạn, thống kê phải có khả năng nói 40 bản ghi còn lại thuộc nhóm thiếu, sai cú pháp, NaN hay vượt miền. Nếu chỉ làm `filter(Double::isFinite)` rồi trả một số trung bình, hệ thống có thể che khuất sự cố chất lượng dữ liệu.

Các chỉ số hữu ích: tổng số bản ghi, số hữu hạn, số missing, số invalid, số NaN, số vô cực, số ngoài range, tỷ lệ các nhóm theo nguồn. Không nên tự gộp chúng nếu các trạng thái có quy trình khắc phục khác nhau.

## 14. Kiểm thử ranh giới bắt buộc

Một tập test tối thiểu cho parser số hữu hạn có thể gồm:

| Đầu vào | Kỳ vọng nếu chọn chính sách ở mục 9 |
|---|---|
| `null` | MISSING |
| `""` và `" "` | MISSING |
| `"0"` | FINITE(0.0) |
| `"-0.0"` | FINITE(-0.0), giữ dấu nếu contract yêu cầu |
| `"12.5"` | FINITE(12.5) |
| `"NaN"` | NAN |
| `"Infinity"` | POS_INFINITY |
| `"-Infinity"` | NEG_INFINITY |
| `"1e400"` | POS_INFINITY do `double` overflow hữu hạn |
| `"abc"` | INVALID |
| `"-3.5"` | FINITE nếu miền nghiệp vụ cho phép âm |
| `"101"` ở trường phần trăm 0..100 | INVALID theo bước validation miền |
| JSON bỏ trường | MISSING hoặc khác `null` theo hợp đồng API |
| JSON trường `null` | MISSING hoặc yêu cầu riêng |

Các test phải đối chiếu **trạng thái và dữ liệu**, không chỉ tránh ném exception. Thêm các test round-trip qua JSON/CSV/database khi những tầng đó tham gia đường đi của dữ liệu.

Ví dụ JUnit (mã minh họa phụ thuộc JUnit 5, không biên dịch độc lập chỉ bằng JDK):

~~~java
// assertEquals(State.MISSING, NumericPolicyDemo.parse(null).state());
// assertEquals(State.NAN, NumericPolicyDemo.parse("NaN").state());
// assertEquals(State.INVALID, NumericPolicyDemo.parse("abc").state());
// assertEquals(State.POS_INFINITY, NumericPolicyDemo.parse("1e400").state());
~~~

Khi test số thực hữu hạn có làm tròn, phải chọn dung sai phù hợp thay vì dùng phép `==` cho mọi kết quả tính toán. Khi phân biệt `-0.0` và `+0.0` là yêu cầu, cần test theo bit hoặc `Double.compare`, không dùng duy nhất `==`.

## 15. Lỗi thiết kế phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách xử lý |
|---|---|---|
| "Null bằng 0" | Mất thông tin thiếu dữ liệu | Chọn default có chủ đích hoặc giữ trạng thái |
| "NaN chính là missing" | NaN là giá trị chấm động đặc biệt, có thể sinh bởi phép toán lỗi | Phân biệt NAN và MISSING khi cần |
| "Parse double thành công thì số hữu hạn" | `"NaN"`, `"Infinity"` và `"1e400"` vẫn parse được | Gọi `Double.isFinite` |
| Kiểm tra `x == Double.NaN` | Luôn false | `Double.isNaN(x)` |
| Gọi `mapToDouble(Double::doubleValue)` trên list có null | Auto-unboxing gây NPE | Kiểm tra/lọc null đúng chính sách |
| Coi `OptionalDouble.of(NaN)` là empty | Presence và tính hữu hạn khác nhau | Kiểm tra cả `isPresent` và `Double.isFinite` |
| Bỏ missing trong trung bình mà không nói rõ | Người đọc không biết mẫu số | Công bố công thức và số bản ghi được tính |
| Dùng sentinel có thể là số hợp lệ | Không phân biệt thực và thiếu | Status/nullable type được mô tả rõ |
| Gửi NaN/Infinity làm JSON number | Không hợp lệ theo JSON chuẩn | Chuyển thành trạng thái, chuỗi được đặc tả, hoặc từ chối |
| Cho BigDecimal nhận NaN | BigDecimal không hỗ trợ non-finite | Validate trước khi chuyển |
| Giả sử mọi database hỗ trợ NaN giống nhau | Driver/kiểu cột/hệ quản trị khác nhau | Xác minh contract của storage |
| Cho rằng `-0.0` hoàn toàn không khác `0.0` | Có thể khác khi chia và sắp xếp | Giữ hoặc chuẩn hóa dấu 0 có chủ đích |
| Chỉ kiểm tra giá trị cuối, không lưu lý do lỗi | Khó phát hiện suy giảm chất lượng nguồn | Thống kê missing/invalid/non-finite riêng |
| Dùng toán tử điều kiện với wrapper null và primitive | Có thể auto-unbox null gây NPE | Kiểm tra null và kiểu biểu thức |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `Double.NaN == Double.NaN` trả gì? Kiểm tra NaN đúng cách ra sao?

**Đáp án:** Trả `false`. Dùng `Double.isNaN(value)`.

**Câu 2.** `Double.parseDouble("1e400")` có nhất thiết ném `NumberFormatException` không?

**Đáp án:** Không. Nó có thể cho `Infinity` vì giá trị vượt phạm vi hữu hạn của `double`. Cần kiểm tra `Double.isFinite` sau parse.

**Câu 3.** `OptionalDouble.of(Double.NaN).isPresent()` là true hay false?

**Đáp án:** `true`. Optional có chứa một giá trị primitive NaN; NaN không đồng nghĩa với missing.

**Câu 4.** Có nên dùng `new BigDecimal("0")` để thay mọi `null` của cột số tiền không?

**Đáp án:** Chỉ khi hợp đồng xác nhận thiếu tiền được hiểu là 0. Thông thường phải phân biệt "không có dữ liệu" với "số tiền đúng bằng 0", rồi quyết định chính sách rõ ràng.

**Câu 5.** Trong bốn phép đo `10.0`, `null`, `20.0`, `30.0`, trung bình là 20 hay 15?

**Đáp án:** Nếu bỏ qua missing, trung bình là 20 trên ba phép đo hợp lệ. Nếu thay missing bằng 0, trung bình là 15 trên bốn bản ghi. Chính sách nghiệp vụ quyết định kết quả; không có mặc định đúng phổ quát.

**Câu 6.** Vì sao `Double.compare(-0.0, 0.0)` trả giá trị âm dù `-0.0 == 0.0` là true?

**Đáp án:** `Double.compare` sử dụng thứ tự cho giá trị `double` có phân biệt dấu của 0. Toán tử `==` tuân theo so sánh số học IEEE 754.

**Câu 7.** `BigDecimal.valueOf(Double.POSITIVE_INFINITY)` trả BigDecimal mang Infinity không?

**Đáp án:** Không. `BigDecimal` không có giá trị vô cực; chuyển non-finite vào `BigDecimal` không hợp lệ và gây `NumberFormatException`.

**Câu 8.** Khi serialize JSON, được ghi `{"x":NaN}` như một JSON number chuẩn không?

**Đáp án:** Không. JSON chuẩn không có literal số NaN/Infinity. Cần định nghĩa cách chuyển trạng thái hoặc từ chối theo contract.

**Câu 9.** Vì sao `List<Double>` chứa null, sau đó `mapToDouble(Double::doubleValue)` có thể ném NPE?

**Đáp án:** Mapping cần `double` primitive, nên cố unbox phần tử null. Phải xử lý null trước theo quy tắc nhập dữ liệu.

**Câu 10.** Tại sao chỉ trả giá trị trung bình sau khi lọc số không hữu hạn là chưa đủ cho giám sát chất lượng dữ liệu?

**Đáp án:** Không biết bao nhiêu giá trị bị loại và lý do nào. Nên trả/báo thêm số bản ghi missing, invalid, NaN, Infinity cùng mẫu số thực được dùng cho thống kê.

---

**Ghi nhớ:** Trong Java, `null`/missing mô tả sự hiện diện của dữ liệu; `NaN` và ±Infinity là các giá trị đặc biệt của `float`/`double`; `0` là một giá trị hợp lệ; `BigDecimal`/`BigInteger` chỉ đại diện cho số hữu hạn trong miền của chúng. **Thiết kế chính sách dữ liệu trước khi tính toán**: phân biệt trạng thái, kiểm tra finite/range, định nghĩa ý nghĩa của thiếu dữ liệu, kiểm soát phép tổng hợp và công bố cách serialize. Đừng để unboxing, phép lọc hay một giá trị sentinel tự quyết định nghiệp vụ thay bạn.