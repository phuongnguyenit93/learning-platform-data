# NumberFormat.parse có thể chỉ đọc phần đầu của chuỗi trong Java

## Mục tiêu bài học

Khi người dùng nhập số, `java.text.NumberFormat` có thể chuyển văn bản theo quy ước của một `Locale` thành `Number`. Tuy nhiên, điểm quan trọng là **parse thành công không có nghĩa toàn bộ chuỗi đầu vào đã được đọc**. Parser có thể nhận một tiền tố hợp lệ rồi dừng ở ký tự tiếp theo không khớp.

Ví dụ: với kiểu số tiếng Anh Mỹ, `"1,234.50USD"` có thể được parse thành `1234.50`, còn phần `"USD"` bị bỏ lại. Điều này hoàn toàn khác với yêu cầu một trường dữ liệu **chỉ được chứa số**.

Sau bài học, bạn có thể:

- Phân biệt `NumberFormat.parse(String)` với `NumberFormat.parse(String, ParsePosition)`.
- Dùng `ParsePosition.getIndex()` kiểm tra parser đã tiêu thụ **hết** input hay mới chỉ đọc một tiền tố.
- Hiểu hành vi thất bại của hai overload, `ParseException`, kết quả `null` và `getErrorIndex()`.
- Chỉ ra vì sao ngay cả khi parser đọc hết chuỗi, cú pháp dấu nhóm vẫn có thể không đáp ứng yêu cầu kiểm tra nghiêm ngặt.
- Tách quy trình parse số theo locale của **giao diện người dùng** khỏi việc parse dữ liệu **API, database hoặc định dạng trao đổi**.
- Thiết kế hàm kiểm tra đầu vào, kiểu số và miền giá trị đúng nhu cầu nghiệp vụ.

Bài tập trung vào `NumberFormat.parse`, đặc biệt là việc dừng ở **đầu chuỗi hợp lệ**. Những quy tắc kiểm tra rộng hơn được dùng để giải thích tại sao phải đánh giá kết quả parse thay vì tin rằng một lời gọi không ném lỗi là đủ.

## 1. Vì sao parser chỉ cần đọc được tiền tố?

`NumberFormat` là lớp trừu tượng đại diện các bộ định dạng và phân tích số theo ngôn ngữ/vùng. Trong ứng dụng có dữ liệu đầu vào dành cho con người, parser cần nhận các chữ số và ký hiệu phù hợp với locale; ví dụ:

- Với `Locale.US`, `1,234.50` thường có nghĩa một nghìn hai trăm ba mươi bốn phẩy năm.
- Với `Locale.GERMANY`, giá trị tương đương thường được viết là `1.234,50`.
- Với một số locale khác, dấu nhóm có thể là khoảng trắng hoặc ký tự không ngắt dòng và bộ chữ số có thể khác ASCII.

Khi parser gặp phần đầu phù hợp, nó có thể dừng tại vị trí không còn nhận ra một phần của số. Điều này có ích trong một **bộ phân tích lớn hơn**: ví dụ đọc số lượng trước rồi xử lý đơn vị ở phần còn lại. Nhưng nếu trường form hoặc API cần một số duy nhất thì phần dư là dữ liệu không hợp lệ.

```text
Đầu vào:  1,234.50USD
          └──────┘└─┘
           parse     phần dư
           được
Kết quả số: 1234.50
```

Hãy luôn đặt câu hỏi: **“Parser đã đọc bao nhiêu ký tự?”** chứ không chỉ **“Parser có trả về số không?”**

## 2. Hai overload quan trọng của NumberFormat.parse

### parse(String)

```java
NumberFormat format = NumberFormat.getNumberInstance(Locale.US);
Number result = format.parse("1,234.50USD");
```

Đây là đoạn minh họa trong một phương thức có xử lý hoặc khai báo `java.text.ParseException` và import `java.text.NumberFormat`, `java.util.Locale`.

Lời gọi có thể thành công và `result` nhận giá trị số của phần đầu `1,234.50`. **Hợp đồng API không yêu cầu tiêu thụ mọi ký tự** của `source`. Khi không thể bắt đầu parse, overload này ném `ParseException`; đừng nhầm với “bỏ qua phần dư”.

### parse(String, ParsePosition)

```java
ParsePosition pos = new ParsePosition(0);
Number value = format.parse("1,234.50USD", pos);
```

Đoạn minh họa này cần thêm import `java.text.ParsePosition` và đã có `format`. Ở đây:

- `new ParsePosition(0)` yêu cầu bắt đầu parse từ index 0.
- `value` là `Number` nếu parser nhận một phần số hợp lệ.
- `pos.getIndex()` là vị trí tiếp theo **sau đoạn đã được parse thành công**.
- `pos.getErrorIndex()` cho biết vị trí lỗi khi quá trình parse thất bại; mặc định thường là `-1` khi không ghi nhận lỗi.

Với chuỗi `"1,234.50USD"` theo `Locale.US`, index kết thúc là 8 trên tổng 11 ký tự. Như vậy **3 ký tự `USD` còn lại**.

### Bảng so sánh

| Điều kiện | `parse(String)` | `parse(String, ParsePosition)` |
| --- | --- | --- |
| Parse được một tiền tố | Có thể trả `Number` dù còn suffix | Trả `Number`, cung cấp index sau phần được đọc |
| Không parse được từ vị trí đầu | Ném `ParseException` | Trả `null`, có thể ghi `errorIndex` |
| Muốn biết có đọc hết input không | Không trực tiếp cho biết vị trí kết thúc | Kiểm tra `position.getIndex() == input.length()` |
| Có thể bắt đầu từ vị trí khác 0 | Không, parse từ đầu chuỗi | Có, bằng `ParsePosition(startIndex)` |
| Dùng để xác thực cả chuỗi | Không đủ nếu dùng riêng | Cần kiểm tra kết quả, index và các điều kiện khác |

**Không nên dựa vào `parse(String)` như bộ kiểm tra cho một chuỗi phải chỉ gồm số.** Đây là lỗi logic thường gặp trong form nhập tiền, số lượng hoặc nhập CSV.

## 3. Ví dụ Java 17+ chạy độc lập

Tạo tệp `NumberParsePrefixDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

public class NumberParsePrefixDemo {
    private static void check(DecimalFormat format, String input) {
        ParsePosition pos = new ParsePosition(0);
        Number value = format.parse(input, pos);

        boolean full = value != null
                && pos.getIndex() == input.length();

        System.out.println("[" + input + "] -> "
                + (value == null ? "INVALID" : value)
                + ", index=" + pos.getIndex()
                + "/" + input.length()
                + ", full=" + full);
    }

    public static void main(String[] args) throws ParseException {
        DecimalFormat us = (DecimalFormat)
                NumberFormat.getNumberInstance(Locale.US);
        us.setParseBigDecimal(true);

        check(us, "1,234.50");
        check(us, "1,234.50USD");
        check(us, "1234.50x");
        check(us, "1,23,4.50");
        check(us, "not-a-number");

        System.out.println("simple parse: "
                + us.parse("1,234.50USD"));

        try {
            us.parse("not-a-number");
        } catch (ParseException ex) {
            System.out.println("simple parse failed");
        }

        us.setParseIntegerOnly(true);
        ParsePosition pos = new ParsePosition(0);
        Number integer = us.parse("123.45", pos);

        System.out.println("integer-only: " + integer
                + ", index=" + pos.getIndex());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 NumberParsePrefixDemo.java
java NumberParsePrefixDemo
```

Stdout với cấu hình trong ví dụ:

```text
[1,234.50] -> 1234.50, index=8/8, full=true
[1,234.50USD] -> 1234.50, index=8/11, full=false
[1234.50x] -> 1234.50, index=7/8, full=false
[1,23,4.50] -> 1234.50, index=9/9, full=true
[not-a-number] -> INVALID, index=0/12, full=false
simple parse: 1234.50
simple parse failed
integer-only: 123, index=3
```

Giải thích các dòng quan trọng:

1. `1,234.50` được parse hết nên `full=true`.
2. `1,234.50USD` chỉ tiêu thụ 8 trong 11 ký tự; `parse(String)` vẫn trả số nếu gọi bằng overload đơn giản.
3. `1234.50x` dừng trước chữ `x`, trả số cho phần hợp lệ.
4. `1,23,4.50` có cách nhóm chữ số không đúng quy ước en-US thông thường nhưng parser `DecimalFormat` vẫn có thể chấp nhận và đọc hết. **Full consumption không đồng nghĩa strict syntax**.
5. `not-a-number` không bắt đầu bằng cú pháp số tương ứng nên overload có `ParsePosition` trả `null`.
6. `setParseIntegerOnly(true)` cho phép parser dừng trước dấu thập phân ở `123.45`, trả `123` và index 3. Tùy chọn này không tự kiểm tra “toàn bộ chuỗi là số nguyên”.

Ví dụ chủ động dùng `Locale.US`, không phụ thuộc vào default locale của JVM. `setParseBigDecimal(true)` giúp `DecimalFormat` trả `BigDecimal` cho các số hữu hạn thông thường trong ví dụ, giữ phần chữ số thập phân đã parse thay vì đi qua `double`. Nhưng nó **không làm parser nghiêm ngặt hơn về cú pháp dấu nhóm hoặc phần dư**.

## 4. Dùng ParsePosition đúng cách

`ParsePosition` là đối tượng mutable giữ thông tin về vị trí trong `String`:

```java
ParsePosition pos = new ParsePosition(0);
Number value = formatter.parse(input, pos);

if (value == null) {
    // Không thể parse từ vị trí yêu cầu.
}
if (value != null && pos.getIndex() != input.length()) {
    // Chỉ đọc được một phần; input còn ký tự chưa tiêu thụ.
}
```

Đây là đoạn minh họa trong một phương thức có `formatter` kiểu `NumberFormat` và `input` kiểu `String` đã được khai báo.

### Index là vị trí trong chuỗi Java, không phải số chữ số

`getIndex()` đếm theo vị trí của `String` (UTF-16 code units), tương tự `String.length()`. Nó **không** cho biết số chữ số thập phân của kết quả, và không phải một giá trị tiền tệ. Nếu chuỗi có ký tự Unicode đặc biệt, không nên suy từ index ra số lượng ký tự người dùng nhìn thấy.

Trong kiểm tra “đã đọc hết”, việc so sánh `pos.getIndex() == input.length()` phù hợp vì cả hai dùng cùng cách đánh chỉ số trên `String`.

### parse từ vị trí khác 0

Bạn có thể đọc một số ở giữa input:

```java
String input = "qty=42kg";
ParsePosition pos = new ParsePosition(4);
Number quantity = NumberFormat
        .getIntegerInstance(Locale.US)
        .parse(input, pos);
```

Đây là đoạn minh họa trong một phương thức. Vị trí 4 là ký tự `4` sau `qty=`. Parser có thể đọc `42` và dừng ở index 6, trước `kg`. Điều này phù hợp khi **một parser cấp cao hơn** chịu trách nhiệm phân tích prefix `qty=`, đơn vị `kg` và toàn bộ cấu trúc.

Nhưng trong hàm chỉ có nhiệm vụ nhận một số, bắt đầu ở index 0 và yêu cầu đọc hết thường là hợp lý hơn.

### Error index và sự khác nhau giữa lỗi với phần dư

Khi `parse` thất bại ngay từ vị trí bắt đầu, kết quả của overload có `ParsePosition` thường là `null`; `getErrorIndex()` hỗ trợ xác định vị trí không khớp.

Ví dụ:

```java
ParsePosition pos = new ParsePosition(0);
Number bad = NumberFormat
        .getNumberInstance(Locale.US)
        .parse("abc", pos);

System.out.println(bad == null);
System.out.println(pos.getIndex());
System.out.println(pos.getErrorIndex());
```

Trong một phương thức có import thích hợp, stdout với formatter mặc định của `Locale.US` là:

```text
true
0
0
```

Ngược lại, nếu parser đọc `123` rồi gặp chữ `a` trong `123abc`, đó có thể là **kết quả parse một phần**, không phải trường hợp parser trả `null`. Hãy dùng `getIndex()` để phát hiện phần chưa đọc. Đừng chỉ hỏi `getErrorIndex()` có giá trị nào đó rồi coi mọi trường hợp còn suffix đều là lỗi được tự báo.

Đặc biệt, đối tượng `ParsePosition` có thể được dùng để tiếp tục đọc các thành phần tiếp theo. Nếu dùng lại, hãy chủ động đặt index/error index khi bắt đầu phân tích mới theo nhu cầu, thay vì giả định nó luôn ở vị trí 0.

## 5. Kiểm tra đã tiêu thụ toàn bộ đầu vào

Khi cần một ô nhập chứa **duy nhất một số** không có tiền tố/hậu tố khác, điều kiện cơ bản là:

```java
ParsePosition pos = new ParsePosition(0);
Number result = formatter.parse(raw, pos);

boolean fullyParsed = result != null
        && pos.getIndex() == raw.length();
```

Đây là **điều kiện cần**, không phải toàn bộ hệ thống kiểm tra đầu vào.

Có hai cách xử lý whitespace hợp lý, miễn là được nêu rõ trong hợp đồng:

- **Strict input:** không cho phép khoảng trắng đầu/cuối, nên `"123 "` sẽ bị coi là chưa parse hết; `" 123"` có thể không parse được ngay từ đầu.
- **Cho phép trim có chủ đích:** nếu form cho phép khoảng trắng bao quanh, kiểm tra `raw != null` rồi dùng `raw.strip()` trước khi parse. Việc loại bỏ whitespace phải là quyết định thiết kế, không phải “sửa” tùy tiện một chuỗi mang ý nghĩa khác.

Không nên tự động xóa mọi khoảng trắng giữa các nhóm chữ số. Một số locale dùng khoảng trắng (có thể là ký tự không ngắt dòng) làm dấu phân nhóm; thay đổi tùy tiện có thể tạo giá trị khác hoặc che lỗi nhập.

### Hàm parse đầy đủ cho đầu vào UI

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public final class LocalizedNumberInput {
    private LocalizedNumberInput() {}

    public static BigDecimal parseDecimal(
            String raw, Locale locale) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("A number is required");
        }

        DecimalFormat formatter = (DecimalFormat)
                NumberFormat.getNumberInstance(locale);
        formatter.setParseBigDecimal(true);

        ParsePosition pos = new ParsePosition(0);
        Number parsed = formatter.parse(raw, pos);

        if (!(parsed instanceof BigDecimal)
                || pos.getIndex() != raw.length()) {
            throw new IllegalArgumentException(
                    "Invalid number: incomplete parse");
        }
        return (BigDecimal) parsed;
    }
}
```

Đây là một lớp tiện ích có thể biên dịch thành `LocalizedNumberInput.java` trên JDK 17+, nhưng không có `main` để chạy độc lập. Hàm cố ý **không trim**: một chuỗi có whitespace dư sẽ bị từ chối nếu parser không tiêu thụ hết.

Tuy nhiên, hàm này mới kiểm tra:

1. Chuỗi tồn tại và không chỉ gồm whitespace.
2. Parser có trả về giá trị decimal phù hợp hay không.
3. Parser có đọc hết chuỗi hay không.

Hàm **chưa đảm bảo** nhóm chữ số đúng hoàn toàn, số có precision/scale trong giới hạn, không âm, hoặc tuân theo quy tắc tiền tệ của ứng dụng. Các kiểm tra đó phải được bổ sung tùy hợp đồng. Đừng gọi một helper chỉ so sánh index là “strict parser cho mọi locale”.

## 6. Ngay cả parse hết chuỗi vẫn có thể chấp nhận grouping sai

Điểm tinh tế nhất của chủ đề là phân biệt hai câu hỏi:

- **Full consumption:** toàn bộ chuỗi đã được parser nhận và không còn suffix.
- **Strict lexical validation:** từng ký tự và cấu trúc dấu nhóm của chuỗi đúng quy tắc input đã công bố.

`DecimalFormat` có khả năng parse theo cú pháp dấu nhóm **tương đối linh hoạt**. Với định dạng số US, nhóm phân cách thông thường là ba chữ số: `1,234.50`. Nhưng parser có thể vẫn chấp nhận:

```text
1,23,4.50
```

và trả về `1234.50`, đồng thời báo đã tiêu thụ hết chuỗi.

Đây là minh họa quan trọng: `position.getIndex() == raw.length()` **không chứng minh** dấu nhóm hợp lệ theo mẫu giao diện mà người dùng được hướng dẫn.

Nếu sản phẩm đòi cú pháp nghiêm ngặt, hãy định nghĩa rõ quy tắc:

- Có cho phép dấu phân nhóm hay không?
- Có bắt buộc từng nhóm đúng độ dài hay không?
- Có chấp nhận dấu `+` hoặc `-` không?
- Có cho phép ký pháp mũ không?
- Dấu thập phân nào hợp lệ cho locale được yêu cầu?
- Có cho phép khoảng trắng Unicode ở đầu, cuối hoặc giữa nhóm không?
- Có chấp nhận số ngoài phạm vi hoặc số có quá nhiều chữ số thập phân không?

Một chiến lược đơn giản cho hệ thống nhập liệu kỹ thuật là **không cho phép grouping** và dùng một ngữ pháp input riêng đã được công bố. Khi đó có thể kiểm tra bằng regex/syntax parser phù hợp rồi chuyển sang `BigDecimal`. Nhưng nếu sản phẩm muốn hỗ trợ dấu nhóm thực của nhiều locale, không nên tự tạo một regex ASCII rồi tuyên bố áp dụng đúng cho tất cả ngôn ngữ; cần cơ chế và test phù hợp với các quy tắc Unicode/locale.

### Vì sao không thể chỉ kiểm tra format lại cho giống input?

Ý tưởng “parse xong, format lại rồi so sánh với chuỗi ban đầu” có hạn chế:

- Formatter có thể làm tròn hoặc đặt số chữ số thập phân khác input.
- Formatter có thể tự thêm/bỏ dấu phân nhóm.
- Dấu âm, các ký tự nhóm hoặc chữ số Unicode có thể được chuẩn hóa.
- Có nhiều biểu diễn đầu vào hợp lệ cùng chỉ một giá trị (`1`, `1.0`, `01` tùy hợp đồng).

So sánh ngược chỉ hợp lý nếu ứng dụng **cố ý chọn một dạng canonical duy nhất** và chấp nhận từ chối mọi biến thể khác. Nó không phải phép kiểm tra chung cho mọi trường nhập số được quốc tế hóa.

## 7. Locale quyết định ý nghĩa ký tự

Cùng một chuỗi có thể bị hiểu khác nhau:

| Đầu vào | `Locale.US` | `Locale.GERMANY` |
| --- | --- | --- |
| `1,234` | Thường biểu thị một nghìn hai trăm ba mươi bốn | Thường biểu thị một phẩy hai ba bốn |
| `1.234` | Thường biểu thị một phẩy hai ba bốn | Thường biểu thị một nghìn hai trăm ba mươi bốn |
| `1,234.50` | Cách viết điển hình cho `1234.50` | Có thể parse một tiền tố, không nên coi là giá trị 1234.50 |
| `1.234,50` | Có thể parse một tiền tố `1.234` | Cách viết điển hình cho `1234.50` |

Đây là minh họa theo các quy ước locale quen thuộc; hành vi từng chuỗi phải được kiểm thử với formatter và JDK/provider mà ứng dụng sử dụng.

**Không đoán locale từ dấu phẩy/dấu chấm** khi hợp đồng chưa chỉ rõ. Ví dụ, `1,234` có thể được hiểu là 1234 hoặc 1.234. Một chương trình tự thay `,` thành `.` có thể khiến số tiền bị giảm 1.000 lần.

Nên xác định locale từ cấu hình người dùng, ngữ cảnh form hoặc quy ước được công bố trước khi parse. Ở API máy-với-máy, nên bỏ phụ thuộc locale và dùng schema số cố định.

### Default locale cũng có thể thay đổi kết quả

`NumberFormat.getNumberInstance()` không truyền locale sử dụng mặc định định dạng thích hợp của JVM. Default có thể khác giữa môi trường phát triển, máy CI và production, thậm chí có thể bị ứng dụng khác trong cùng JVM thay đổi qua `Locale.setDefault`.

Khi xử lý một request, hãy truyền `Locale` tường minh cho formatter của request đó. Đừng gọi `Locale.setDefault` mỗi khi người dùng chuyển ngôn ngữ; đây là trạng thái dùng chung cấp JVM và có thể ảnh hưởng các request khác.

## 8. setParseIntegerOnly không có nghĩa validate số nguyên

Phương thức `NumberFormat.setParseIntegerOnly(true)` được dùng để yêu cầu parser chỉ nhận phần số nguyên trong khi phân tích. Nó không nhất thiết từ chối toàn bộ chuỗi có phần thập phân; ngược lại, parser có thể dừng trước dấu thập phân.

Ví dụ theo `Locale.US`:

```java
NumberFormat integers =
        NumberFormat.getIntegerInstance(Locale.US);

ParsePosition pos = new ParsePosition(0);
Number number = integers.parse("123.45", pos);

System.out.println(number);
System.out.println(pos.getIndex());
```

Đây là đoạn minh họa trong một phương thức có các import tương ứng. Stdout:

```text
123
3
```

Nếu trường dữ liệu chỉ được nhập số nguyên, bạn phải kiểm tra `pos.getIndex() == input.length()`. Nếu cần số nguyên trong phạm vi xác định, kiểm tra cả range và kiểu kết quả.

Đừng hiểu `NumberFormat.getIntegerInstance` là bộ kiểm tra cú pháp số nguyên hoàn chỉnh cho mọi đầu vào không đáng tin.

## 9. BigDecimal, kiểu Number và giới hạn precision

`NumberFormat.parse` có kiểu trả về `Number`, không phải luôn `Double` hay `Long`. Kết quả phụ thuộc formatter, tùy chọn và giá trị. `DecimalFormat#setParseBigDecimal(true)` là một lựa chọn khi cần đọc chuỗi thập phân thành `BigDecimal`.

```java
DecimalFormat format = (DecimalFormat)
        NumberFormat.getNumberInstance(Locale.US);
format.setParseBigDecimal(true);
Number number = format.parse("123.450", new ParsePosition(0));
```

Đây là đoạn minh họa trong một phương thức. Khi muốn giữ độ chính xác decimal, đọc dạng số được hỗ trợ thay vì luôn chuyển kết quả qua `doubleValue()`, vì bước chuyển sang floating-point nhị phân có thể mất chính xác.

Tuy nhiên, **kiểu giá trị chính xác không tự khiến parser đọc hết hoặc kiểm tra grouping chặt**. Việc trả về `BigDecimal` chỉ giải quyết một phần yêu cầu về biểu diễn số.

Những kiểm tra cần tách riêng gồm:

1. **Cú pháp đầu vào** (đúng grammar).
2. **Full consumption** (không có phần dư).
3. **Precision/scale** (số chữ số tổng và số chữ số sau dấu thập phân).
4. **Miền giá trị** (không âm, không vượt hạn mức, v.v.).
5. **Đơn vị** (tiền tệ, tỷ lệ, khối lượng).
6. **Quy tắc làm tròn** khi nghiệp vụ cần.

Ví dụ tiền tệ: sau khi parse `"123.456"` theo locale, nghiệp vụ có thể cần từ chối nếu chỉ chấp nhận hai chữ số thập phân. Đừng âm thầm format lại thành `123.46` rồi lưu, trừ khi hợp đồng **cho phép và quy định cách làm tròn**.

### parse format number và currency khác nhau

`NumberFormat.getNumberInstance(locale)` được thiết kế cho số thường, `getPercentInstance(locale)` cho phần trăm và `getCurrencyInstance(locale)` cho định dạng tiền tệ. Chúng có thể dùng pattern và ký hiệu khác nhau. Một chuỗi có dấu tiền tệ không nên được parse như số thường rồi lặng lẽ bỏ hậu tố/tiền tố.

Nếu người dùng nhập `"100 USD"`, cần xác định ứng dụng muốn:

- Một **trường số riêng** `100` và một **trường currency riêng** `USD`.
- Hay một đầu vào kết hợp có grammar rõ ràng được bộ parser chuyên dụng nhận dạng đầy đủ.

Không được phép chỉ lấy `100` bằng prefix parse rồi bỏ `USD` mà không kiểm tra currency, đặc biệt với dữ liệu giao dịch.

## 10. Giao diện người dùng và giao thức trao đổi cần parser khác nhau

Một form UI đa ngôn ngữ có thể chấp nhận `1.234,50` cho người dùng Đức, nhưng JSON hoặc dữ liệu CSV tích hợp thường cần **format số được ghi hợp đồng riêng**, không phụ thuộc locale của người dùng.

### Luồng xử lý thích hợp

```text
Input của người dùng + Locale cụ thể
                |
       Parse theo Locale
                |
  Kiểm tra hết chuỗi + grammar
                |
  Kiểm tra miền giá trị/scale
                |
     BigDecimal / Number
            /       \
           v         v
  Hiển thị theo   Lưu hoặc trao đổi
  Locale người    theo schema ổn định
      dùng
```

Với dữ liệu từ REST API, CSV import hoặc message queue, parser phải theo schema của kênh đó. Ví dụ một hợp đồng JSON number không dùng dấu phân nhóm và có dấu thập phân `.`; không nên lấy locale mặc định JVM để phân tích JSON number.

```json
{"quantity": 1234.5}
```

Đây là JSON hợp lệ có trường `quantity` kiểu number. Ngược lại, `{"quantity": 1,234.5}` **không phải** một JSON number đơn lẻ hợp lệ; dấu phẩy phân nhóm ở đây sẽ vi phạm cú pháp của object JSON.

Nếu API dùng decimal string để giữ chính xác giá trị (ví dụ tiền), hãy công bố trường đó là kiểu chuỗi decimal theo grammar ổn định; nó không phải “bất kỳ chuỗi số đang hiển thị ở UI”.

### Đừng tự sửa đầu vào mơ hồ

Một anti-pattern:

```java
String standardized = raw.replace(",", "").replace(" ", "");
double value = Double.parseDouble(standardized);
```

Đây là đoạn minh họa **không nên áp dụng**. Với người dùng nhập `"1,23"` vì dùng dấu phẩy thập phân, chương trình biến nó thành `123` thay vì `1.23`. Việc bỏ nhóm không thể làm bằng chuỗi thay thế không xét ngữ cảnh.

Nếu nguồn dữ liệu luôn dùng grammar máy đọc cố định, hãy validate theo grammar đó rồi parse trực tiếp. Nếu nguồn là UI, xác định locale và xử lý ký hiệu của locale bằng một parser phù hợp, kèm validation nghiệp vụ.

## 11. Thiết kế API nhận đầu vào có kiểm soát

Một hàm parse an toàn hơn cần mô tả đúng phạm vi bảo đảm của nó. Chẳng hạn có thể dùng mã sau như bước đầu nhận decimal nhập từ form, **không tuyên bố rằng nó kiểm tra được mọi cấu trúc grouping hợp lệ**:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public final class PriceInput {
    private PriceInput() {}

    public static BigDecimal parseLocalized(
            String input, Locale locale) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Input is empty");
        }

        if (input.length() > 64) {
            throw new IllegalArgumentException("Input is too long");
        }

        DecimalFormat parser = (DecimalFormat)
                NumberFormat.getNumberInstance(locale);
        parser.setParseBigDecimal(true);

        ParsePosition pos = new ParsePosition(0);
        Number parsed = parser.parse(input, pos);

        if (!(parsed instanceof BigDecimal)
                || pos.getIndex() != input.length()) {
            throw new IllegalArgumentException(
                    "Invalid numeric input or trailing characters");
        }

        BigDecimal value = (BigDecimal) parsed;
        if (value.signum() < 0) {
            throw new IllegalArgumentException(
                    "Negative value is not allowed");
        }
        if (value.scale() > 2) {
            throw new IllegalArgumentException(
                    "Too many fractional digits");
        }
        return value;
    }
}
```

Đây là lớp có thể biên dịch thành `PriceInput.java` trên Java 17+, nhưng không có phương thức `main` để chạy trực tiếp.

Chú ý:

- Giới hạn 64 ký tự, không âm và tối đa 2 chữ số thập phân là **ví dụ về chính sách ứng dụng**, không phải luật chung của NumberFormat.
- Hàm không tự bỏ whitespace. Chuỗi có phần dư thường bị từ chối qua kiểm tra vị trí.
- Hàm chưa phát hiện mọi kiểu **dấu nhóm không hợp lệ**. Nếu ứng dụng cho phép grouping nhưng bắt buộc nhóm chữ số chuẩn, cần thêm bộ kiểm tra phù hợp.
- Nếu nghiệp vụ muốn từ chối cả giá trị không được viết bằng ký tự ASCII chuẩn, cần thêm quy tắc; parser locale vốn có thể chấp nhận ký tự số của locale.
- Nếu currency của giao dịch có đơn vị nhỏ nhất khác hai chữ số, đừng mặc định tất cả đồng tiền đều dùng scale 2.
- Tạo formatter/parser riêng cho mỗi lần xử lý hoặc quản lý thread safety; các thể hiện `NumberFormat` thường có trạng thái mutable, không nên chia sẻ không đồng bộ giữa nhiều luồng.

Một hàm ghi rõ giới hạn của mình tốt hơn một hàm đặt tên `strictParse` nhưng âm thầm chấp nhận grammar lỏng.

## 12. Kiểm thử những trường hợp nào?

Một bộ kiểm thử cho đầu vào số theo locale nên bao gồm:

| Nhóm | Ca kiểm thử | Điều cần kiểm tra |
| --- | --- | --- |
| Hợp lệ | `1,234.50` với `Locale.US` | Đúng giá trị và tiêu thụ hết chuỗi |
| Hợp lệ | `1.234,50` với `Locale.GERMANY` | Đúng giá trị theo locale đã chọn |
| Suffix | `1,234.50USD` | Phát hiện chỉ parse phần đầu |
| Suffix | `123.45abc` | Phát hiện index nhỏ hơn length |
| Prefix lạ | `abc123` | Không nhận được số từ vị trí 0 |
| Whitespace | `123 ` và ` 123` | Theo chính sách trim/không trim |
| Grouping bất thường | `1,23,4.50` với `Locale.US` | Không nhầm full parse thành strict grammar |
| Phần thập phân | `123.456` khi scale tối đa 2 | Kiểm tra thang đo, không chỉ parse thành công |
| Âm và giới hạn | `-1`, số cực lớn | Kiểm tra phạm vi nghiệp vụ |
| Khác locale | `1,234` với US/Germany | Không hiểu nhầm thập phân và phân nhóm |
| Chỉ số nguyên | `123.45` với parse-integer-only | Không chấp nhận phần dư như số nguyên hoàn chỉnh |
| Decimal chính xác | Giá trị nhiều chữ số | Không làm mất precision qua `double` không cần thiết |
| Ký tự Unicode | Chữ số/dấu nhóm không ASCII | Kiểm tra đúng với formatter/provider và font/UI |

Nếu đầu vào ảnh hưởng đến tiền, hạn mức hoặc đơn vị, hãy ghi test cho **một con số có thể bị nhân/chia 100 hoặc 1.000 khi hiểu nhầm dấu**, vì đó là lỗi có tác động thực tế nghiêm trọng.

### Đảm bảo test không phụ thuộc môi trường JVM

Đừng viết test với `NumberFormat.getInstance()` không tham số rồi kỳ vọng mọi máy cùng dấu nhóm/thập phân. Chọn `Locale` tường minh, ví dụ `Locale.US` hoặc `Locale.GERMANY`.

Đừng đặt các thông điệp hoặc chỉ số lỗi cụ thể theo một provider JDK mà không có lý do: dữ liệu locale/provider có thể thay đổi giữa phiên bản Java. Test nên tập trung vào **hợp đồng parse đã quy định** và những hành vi được API đảm bảo.

## 13. Các lỗi phổ biến

| Sai lầm | Vấn đề | Cách làm đúng |
| --- | --- | --- |
| `format.parse(input)` không ném exception nên cho rằng input hợp lệ toàn bộ | Overload đơn giản có thể dừng sau tiền tố số | Dùng `ParsePosition` và kiểm tra index cuối |
| Chỉ kiểm tra `parsed != null` | Có thể còn suffix bị bỏ | Kiểm tra `pos.getIndex() == input.length()` |
| Chỉ kiểm tra `pos.getErrorIndex()` | Kết quả parse một phần có thể không phải lỗi do parser báo | Kiểm tra phần dư bằng getIndex |
| Full consumption nghĩa là grouping đúng chuẩn | DecimalFormat có thể parse dấu nhóm linh hoạt | Kiểm tra grammar nếu sản phẩm cần nghiêm ngặt |
| Dùng `getIntegerInstance` để “validate số nguyên” | Có thể đọc phần nguyên rồi dừng trước dấu thập phân | Kiểm tra index và miền số nguyên |
| Dùng `setParseBigDecimal(true)` để “bắt mọi lỗi” | Chỉ thay kiểu/độ chính xác của kết quả parse | Tách validation cú pháp và giá trị |
| Gọi parse bằng default locale không rõ ràng | Cùng chuỗi có thể mang ý nghĩa khác nhau | Truyền locale tường minh |
| Tự thay `,` bằng `.` hoặc xóa dấu nhóm | Có thể đổi giá trị 1.000 lần | Xác định grammar nguồn, parse theo đúng quy tắc |
| Parse chuỗi đã thêm `USD` mà không kiểm tra currency | Bỏ qua đơn vị tiền giao dịch | Dùng trường currency riêng hoặc parser chuyên dụng |
| Cho phép trailing text trong trường chỉ nhận số | Có thể lưu giá trị sai hoặc chấp nhận input độc hại | Kiểm tra full consumption và schema |
| Parse giao thức JSON bằng NumberFormat | Giao thức có ngữ pháp riêng | Dùng JSON parser và kiểu số theo schema |
| Dùng chung một NumberFormat mutable trong nhiều luồng | Có thể phát sinh lỗi đồng thời | Dùng instance riêng hoặc đồng bộ |

## 14. Bài tập tự kiểm tra

**Bài 1 — phần dư.** Cho `Locale.US` và input `"1,234.50USD"`. Hãy tạo `ParsePosition(0)`, gọi `parse`, xác định giá trị, index và số ký tự chưa được đọc. Vì sao `parse(String)` không ném lỗi trong tình huống này?

**Bài 2 — kiểm tra cả chuỗi.** Viết hàm nhận một `String` và `Locale`, trả về `Number` chỉ khi parser có kết quả và `pos.getIndex() == input.length()`. Hàm đó đã là strict parser cho mọi loại grouping chưa? Vì sao?

**Bài 3 — số nguyên.** Vì sao `getIntegerInstance(Locale.US).parse("123.45", pos)` có thể nhận `123`? Cần thêm điều kiện nào để từ chối input chứa phần thập phân?

**Bài 4 — locale mơ hồ.** `"1,234"` có ý nghĩa khác nhau thế nào trong locale US và Đức? Tại sao không nên dựa vào ký tự `,` rồi tự quyết định nghĩa của nó?

**Bài 5 — precision.** Khi parse số tiền có nhiều chữ số thập phân, lợi ích của `DecimalFormat#setParseBigDecimal(true)` là gì? Nó có tự làm cho parsing chặt về cú pháp hoặc miền giá trị không?

**Bài 6 — QA.** Hãy viết tập test cho `"123.45abc"`, `"abc123"`, `"123 "`, `"1,23,4.50"` và `"123.456"` với chính sách tối đa hai chữ số thập phân. Nêu riêng lỗi **phần dư**, **không thể parse**, **grouping** và **scale**.

## 15. Kết luận

`NumberFormat.parse` được thiết kế để **nhận số theo quy ước của một locale**, và có thể chỉ đọc **tiền tố hợp lệ** của đầu vào. Overload `parse(String)` có thể trả số dù còn ký tự phía sau; muốn biết chính xác phần đã đọc, dùng `parse(String, ParsePosition)`.

Điều kiện `parsed != null && pos.getIndex() == input.length()` giúp từ chối đầu vào không được đọc hết, nhưng đó mới là **kiểm tra full consumption**, không phải bảo đảm toàn bộ dấu nhóm, kiểu số và miền giá trị đều hợp lệ. Với input của người dùng, hãy xác định locale, grammar, range và scale rõ ràng. Với dữ liệu trao đổi giữa máy, dùng schema số cố định thay vì parser hiển thị theo locale.

**Nguyên tắc cốt lõi:** *Parse được một phần ≠ input hợp lệ; parse hết chuỗi ≠ mọi quy tắc nghiệp vụ đều đã được kiểm tra.*

### Tài liệu API tham khảo

- [`NumberFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
- [`DecimalFormat` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html)
- [`ParsePosition` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html)
