# Kiểm tra toàn bộ đầu vào khi phân tích dữ liệu bản địa hóa trong Java

## 1. Vấn đề: parse thành công không đồng nghĩa cả chuỗi hợp lệ

Trong ứng dụng có dữ liệu số/ngày theo `Locale`, một tình huống nguy hiểm là **parser đọc được tiền tố hợp lệ, nhưng bỏ lại phần dư mà ứng dụng không kiểm tra**.

Ví dụ với bộ định dạng số kiểu Hoa Kỳ:

```text
Đầu vào:       1,234.50kg
Phần được đọc: 1,234.50
Phần dư:             kg
```

`NumberFormat.parse("1,234.50kg")` có thể trả `1234.5` thay vì ném lỗi, bởi API parse của các lớp `java.text.Format` thường cho phép phân tích từ đầu chuỗi cho đến khi không nhận dạng được thêm. Đây là hành vi tiện lợi khi phân tích một phần nội dung nhưng **không phù hợp nếu ô nhập liệu bắt buộc chỉ chứa một số**.

Quy tắc then chốt:

> **Một đầu vào hợp lệ hoàn toàn cần hai điều kiện:** parser tạo được kết quả và **vị trí kết thúc parse bằng độ dài chuỗi đầu vào được phép chấp nhận**.

Đối với các bộ phân tích `java.text` hỗ trợ `ParsePosition`, dùng:

```java
ParsePosition position = new ParsePosition(0);
Number number = numberFormat.parse(input, position);
boolean fullyParsed =
        number != null && position.getIndex() == input.length();
```

Nhưng còn một tầng khác: **tiêu thụ hết chuỗi chỉ là điều kiện cần**, chưa đủ để đảm bảo ngữ pháp nghiêm ngặt, phạm vi giá trị hợp lệ, độ chính xác hoặc chính sách của nghiệp vụ. Ví dụ parser có thể chấp nhận cách phân nhóm chữ số không chuẩn, dù đã đọc hết ký tự.

## 2. Ba kết quả phân tích cần phân biệt

Khi gọi `NumberFormat.parse(String, ParsePosition)` hoặc API tương tự, hãy phân loại:

| Trạng thái | Giá trị trả về | `position.getIndex()` | Ý nghĩa |
|---|---|---|---|
| Thành công toàn bộ | Khác `null` | `input.length()` | Parser tiêu thụ hết chuỗi |
| Thành công một phần | Khác `null` | Nhỏ hơn `input.length()` | Có phần dư chưa được kiểm tra |
| Thất bại | `null` | Thường không tiến khỏi vị trí bắt đầu | Không tạo được giá trị |

Ví dụ trên `NumberFormat` dùng `Locale.US`:

| Input | Giá trị parse được | Index kết thúc | Độ dài | Kết luận theo full-consumption |
|---|---:|---:|---:|---|
| `1,234.50` | `1234.5` | 8 | 8 | Chấp nhận |
| `1,234.50kg` | `1234.5` | 8 | 10 | Từ chối |
| `12.5kg` | `12.5` | 4 | 6 | Từ chối |
| `12.5 ` | `12.5` | 4 | 5 | Từ chối nếu không cho phép khoảng trắng cuối |
| `abc12` | `null` | 0 | 5 | Từ chối |
| `1,23` | `123` | 4 | 4 | Tiêu thụ hết nhưng cú pháp grouping có thể không hợp chính sách |

Hàng cuối cùng nhắc lại giới hạn của cách kiểm tra: một số `NumberFormat` **không validate vị trí grouping theo cách nghiêm ngặt**. Do đó `1,23` có thể thành `123` trong `Locale.US` mà không còn ký tự dư. Nếu sản phẩm bắt buộc grouping ba chữ số chính xác, cần kiểm tra thêm một quy tắc cụ thể.

## 3. Vì sao parse(String) không đủ để kiểm tra?

`NumberFormat` có overload tiện lợi:

```java
Number value = numberFormat.parse(input);
```

Overload này ném `ParseException` khi parser **không thể bắt đầu phân tích thành giá trị**, nhưng nó có thể chấp nhận một **tiền tố hợp lệ** và bỏ phần còn lại. Nó không buộc bạn kiểm tra vị trí kết thúc.

Ví dụ:

```java
NumberFormat formatter =
        NumberFormat.getNumberInstance(Locale.US);

System.out.println(formatter.parse("12.5kg"));
```

In ra:

```text
12.5
```

Trong khi:

```java
formatter.parse("abc12");
```

ném `ParseException` vì không phân tích được số ở ngay vị trí bắt đầu.

Vì vậy, dùng `try/catch(ParseException)` xung quanh `parse(String)` vẫn **chưa phải một phép kiểm tra “đọc hết chuỗi”**.

Mẫu thiết kế thường được chọn là `parse(input, ParsePosition)` cùng kiểm tra vị trí kết thúc, đặc biệt khi dữ liệu đến từ biểu mẫu web, dữ liệu nhập tay, CSV, tin nhắn giao thức hoặc nội dung người dùng chưa được kiểm tra.

## 4. ParsePosition: index và errorIndex có nghĩa gì?

`java.text.ParsePosition` lưu trạng thái của parser qua hai chỉ số chính:

- `getIndex()`: vị trí **sau ký tự cuối cùng đã phân tích thành công**. Nếu gọi parser từ `new ParsePosition(0)`, index này thể hiện số UTF-16 code units đã tiêu thụ.
- `getErrorIndex()`: vị trí gặp lỗi nếu parser không thể phân tích; mặc định `-1` nghĩa là **không có chỉ số lỗi được ghi nhận**.

Một đoạn phân tích:

```java
String input = "12.5kg";
ParsePosition position = new ParsePosition(0);

Number value = formatter.parse(input, position);
```

Sau đó, kết quả đã kiểm chứng:

```text
value      = 12.5
index      = 4
errorIndex = -1
length     = 6
```

**Đừng kiểm tra chỉ `errorIndex == -1` để kết luận đầu vào hợp lệ.** Đầu vào `12.5kg` đã parse được một phần, không có lỗi được ghi nhận và vẫn có phần dư.

Cần xét đồng thời:

```java
value != null && position.getIndex() == input.length()
```

Khi parser thất bại ngay từ đầu, `getErrorIndex()` giúp xác định vị trí lỗi nếu có. Với chuỗi không parse được `"abc12"` trong ví dụ US, giá trị `null`, `getIndex() == 0`, `getErrorIndex() == 0`.

### Chỉ số là UTF-16, không phải số ký tự người dùng nhìn thấy

`ParsePosition` dùng index của `String` Java. Với Unicode, `input.length()` đếm UTF-16 code units, không phải byte UTF-8 hoặc số grapheme. Điều kiện `position.getIndex() == input.length()` **đúng loại chỉ số cần so sánh**; đừng thay `length()` bằng số code points rồi so trực tiếp.

### Luôn khởi tạo ParsePosition mới khi kiểm tra

`ParsePosition` là đối tượng có trạng thái và có thể bắt đầu ở index khác 0. Khi validate toàn bộ chuỗi, thường dùng `new ParsePosition(0)` cho **mỗi lần kiểm tra**. Nếu cố tình phân tích từ giữa chuỗi, các chỉ số phải được diễn giải theo vị trí bắt đầu đó; không coi kết quả từ giữa là “đọc toàn bộ”.

## 5. Ví dụ Java 17+ hoàn chỉnh: từ chối mọi phần dư

Tạo tệp `FullNumberParseDemo.java`:

```java
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class FullNumberParseDemo {
    public static Number parseFully(
            NumberFormat formatter,
            String input) throws ParseException {

        Objects.requireNonNull(formatter, "formatter");
        Objects.requireNonNull(input, "input");

        ParsePosition position = new ParsePosition(0);
        Number result = formatter.parse(input, position);

        if (result == null ||
                position.getIndex() != input.length()) {
            int errorOffset = position.getErrorIndex() >= 0
                    ? position.getErrorIndex()
                    : position.getIndex();

            throw new ParseException(
                    "Input was not fully parsed", errorOffset);
        }

        return result;
    }

    public static void main(String[] args) {
        NumberFormat formatter =
                NumberFormat.getNumberInstance(Locale.US);

        for (String input : List.of(
                "1,234.50",
                "1,234.50kg",
                "12.5",
                "12.5 ",
                "abc12",
                "1,23")) {

            try {
                Number value = parseFully(formatter, input);
                System.out.println(
                        "[" + input + "] -> ACCEPT " + value);
            } catch (ParseException exception) {
                System.out.println(
                        "[" + input + "] -> REJECT at " +
                        exception.getErrorOffset());
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac FullNumberParseDemo.java
java FullNumberParseDemo
```

Kết quả:

```text
[1,234.50] -> ACCEPT 1234.5
[1,234.50kg] -> REJECT at 8
[12.5] -> ACCEPT 12.5
[12.5 ] -> REJECT at 4
[abc12] -> REJECT at 0
[1,23] -> ACCEPT 123
```

Giải thích chính xác từng loại kết quả:

1. `1,234.50` được đọc hết và trả về số `1234.5`.
2. `1,234.50kg` chỉ đọc phần số ở tám ký tự đầu; hai chữ `kg` còn dư nên phải từ chối.
3. `12.5` được đọc hết.
4. `12.5 ` còn **một khoảng trắng cuối**; vì chính sách của hàm là “không dư bất cứ ký tự nào”, nó bị từ chối.
5. `abc12` không có tiền tố số hợp lệ, parser trả `null` và `getErrorIndex()` là 0.
6. `1,23` được parser US chấp nhận hết như `123`; điều này chứng minh **full consumption không đồng nghĩa strict grouping**.

Trong ví dụ, `ParseException.getErrorOffset()` với đầu vào chỉ được parse một phần là vị trí dừng parse do chúng ta chủ động truyền vào constructor. Đây là **thông tin do hàm kiểm tra tự tạo**, không phải lỗi mà `NumberFormat` tự động ném cho phần dư.

Hàm này dùng `Objects.requireNonNull` để phản hồi rõ ràng khi API bị gọi với tham số `null`; bạn có thể thay bằng chính sách validation khác nếu hợp đồng ứng dụng yêu cầu.

## 6. Phân biệt trường hợp parser không tiến và parser đọc thiếu

Một hàm kiểm tra đầy đủ nên kiểm tra **giá trị không `null`** trước khi chỉ dựa vào chỉ số:

```java
ParsePosition pos = new ParsePosition(0);
Number number = formatter.parse(input, pos);

boolean valid = number != null && pos.getIndex() == input.length();
```

Đừng chỉ viết:

```java
boolean valid = pos.getIndex() == input.length();
```

Nếu đầu vào rỗng, `input.length() == 0` và `pos.getIndex()` có thể vẫn bằng 0 dù parser không tạo giá trị nào, gây sai validation.

Tương tự, nếu parser không ghi `errorIndex` nhưng trả về một value được phân tích từng phần, vẫn phải kiểm tra vị trí kết thúc. `getErrorIndex()` là **thông tin hỗ trợ debug**, không phải lá cờ khẳng định toàn bộ đầu vào hợp lệ.

Trong ứng dụng thực tế, thông báo lỗi người dùng thường không nên chứa toàn bộ chuỗi nhạy cảm. Có thể trả kiểu lỗi “Giá trị số không hợp lệ” và ghi chỉ số lỗi ở kênh log nội bộ phù hợp.

## 7. Khoảng trắng: từ chối hay chuẩn hóa một cách chủ động?

Nhiều form cho phép người dùng nhập `" 12.5 "` rồi tự loại whitespace hai đầu. Một validator **không được tự ý quyết định** thay người dùng; phải có chính sách rõ.

### Chính sách A — Input chính xác

Dùng nguyên chuỗi:

```java
Number number = parseFully(formatter, raw);
```

`"12.5 "` bị từ chối vì có phần dư. Khoảng trắng ở đầu `" 12.5"` có thể khiến parser không bắt đầu được.

### Chính sách B — Cho phép khoảng trắng hai đầu

Chuẩn hóa **trước khi parse**:

```java
String normalized = raw.strip();
Number number = parseFully(formatter, normalized);
```

`String.strip()` dựa vào quy tắc whitespace của Java, khác `trim()` theo chi tiết Unicode; không nên giả định mọi loại khoảng trắng Unicode đều được loại bỏ. Sau chuẩn hóa, phải dùng **`normalized.length()`**, không dùng độ dài của `raw` để so với parse index.

Nếu dữ liệu có khoảng trắng đặc biệt thuộc định dạng số ở locale đó (ví dụ ký tự khoảng trắng không ngắt dùng làm grouping separator), việc xóa khoảng trắng **bên trong** chuỗi có thể làm hỏng input. Chỉ chuẩn hóa những gì chính sách thật sự cho phép; không xóa mọi dấu cách bằng `replace(" ", "")` rồi coi đó là parse nghiêm ngặt.

### Chính sách C — Chấp nhận đơn vị nhưng phải xử lý đơn vị

Nếu đầu vào hợp lệ là `"12.5kg"`, không thể dùng `parseFully` trên cả chuỗi để lấy số mà vẫn chấp nhận nó. Thay vào đó, cần **cú pháp có chủ đích**: tách/parse cả phần số lẫn đơn vị, kiểm tra đơn vị có nằm trong danh sách cho phép và chắc chắn không còn dữ liệu dư.

Ví dụ chỉ chấp nhận `kg` và `g` sẽ khác hoàn toàn với việc bỏ qua mọi thứ sau con số. Việc bỏ phần dư một cách mù quáng làm mất nghĩa của đơn vị và có thể gây lỗi nghiệp vụ.

## 8. Toàn bộ chuỗi không có nghĩa parser đã kiểm tra đúng hình thức

Một câu hỏi quan trọng: vì sao `"1,23"` vẫn được `NumberFormat.getNumberInstance(Locale.US)` parse thành `123` và tiêu thụ hết bốn ký tự?

Do `NumberFormat` / `DecimalFormat` có thể có **quy tắc parse tương đối linh hoạt** đối với grouping. Nó giúp chấp nhận một số input trong giao diện người dùng, nhưng không tự thực thi mọi ràng buộc cú pháp bạn mong muốn, chẳng hạn dấu phẩy phải xuất hiện đúng mỗi nhóm ba chữ số.

Tùy hợp đồng ứng dụng, cần thêm validation:

- Có cho phép dấu nhóm không? Nếu có, vị trí nhóm phải chính xác thế nào?
- Dấu âm có được phép không? Có chấp nhận dấu cộng?
- Có cho phép chữ số khác ASCII hay không?
- Cho phép tối đa bao nhiêu chữ số thập phân?
- Có cho phép ký hiệu tiền tệ/phần trăm không?
- Có chấp nhận chữ số `0` đầu, số âm 0, giá trị `NaN` hoặc vô cực không?
- Sau parse, giá trị có nằm trong miền nghiệp vụ không?

**Ví dụ cú pháp thập phân máy/ASCII chủ động, không dùng grouping**:

```java
boolean validText =
        input.matches("[0-9]+(?:\\.[0-9]{1,2})?");
```

Đoạn này chỉ chấp nhận một hoặc nhiều chữ số ASCII, theo sau tùy chọn là dấu chấm và một hoặc hai chữ số thập phân. `String.matches(...)` khớp **toàn bộ** chuỗi theo regex. Nó không cho dấu âm, dấu nhóm hoặc chữ số ở các hệ khác; điều đó là **giới hạn có chủ đích**, không phải grammar của mọi locale.

Sau bước kiểm tra grammar trên, nếu đầu vào thực sự là một chuỗi thập phân canonical (không có grouping), có thể chuyển trực tiếp:

```java
java.math.BigDecimal amount = new java.math.BigDecimal(input);
```

Đối với **đầu vào được bản địa hóa** theo `Locale`, không áp regex ASCII như một chuẩn toàn cầu. Hãy kết hợp parser theo locale, kiểm tra tiêu thụ hết và validation grammar/giá trị theo chính sách cụ thể. Không nên khẳng định “đã dùng ParsePosition thì chắc chắn đầu vào đúng chuẩn”.

## 9. Locale ảnh hưởng cả dấu thập phân và kết quả parse

Cùng một chuỗi có thể mang ý nghĩa khác nhau tùy ngôn ngữ/vùng:

- `Locale.US` thường biểu diễn `1234.5` dưới dạng `1,234.5`.
- `Locale.GERMANY` thường biểu diễn tương ứng là `1.234,5`.

Ví dụ đối chiếu:

| Locale parser | Input | Giá trị parse | Kết thúc index | Kết luận |
|---|---|---:|---:|---|
| `en-US` | `1,234.50` | `1234.5` | 8/8 | Parse hết |
| `en-US` | `1.234,50` | `1.234` | 5/8 | Còn dư |
| `de-DE` | `1.234,50` | `1234.5` | 8/8 | Parse hết |
| `de-DE` | `1,234.50` | `1.234` | 5/8 | Còn dư |

Những kết quả này được quan sát với bộ dữ liệu locale/JDK dùng cho ví dụ; các ký hiệu có thể phụ thuộc cấu hình locale, đặc biệt với locale khác hoặc dữ liệu Unicode mới.

Vì thế, ứng dụng không nên định dạng bằng một locale rồi parse bằng locale khác. Nếu giao diện cho biết người dùng đang nhập theo `vi-VN`, hãy xây dựng parser theo locale/hợp đồng đầu vào đó. Nếu API máy-máy định nghĩa dấu chấm decimal cố định, hãy dùng grammar canonical cho giao thức thay vì đoán locale theo hệ điều hành của máy chủ.

Một câu hỏi hay khi debug: “Đầu vào này có hợp lệ không?” phải đi kèm “**Hợp lệ theo locale và grammar nào?**”.

## 10. BigDecimal: bảo toàn biểu diễn thập phân không thay thế full consumption

`NumberFormat.parse(...)` thường trả về `Number` có thể là `Long`, `Double` hoặc kiểu khác tùy formatter/input. Với số tiền hoặc dữ liệu decimal cần độ chính xác, có thể cấu hình một `DecimalFormat` chuyên biệt:

```java
DecimalFormat formatter = new DecimalFormat(
        "#,##0.###",
        DecimalFormatSymbols.getInstance(Locale.US));
formatter.setParseBigDecimal(true);
```

Khi đó, với những số thập phân hữu hạn thông thường, parser có thể trả `BigDecimal`. Ví dụ `1,234.50` được parse thành đối tượng `BigDecimal` có chuỗi `1234.50`, giữ được phần decimal theo mức dữ liệu parser đọc.

**Nhưng `setParseBigDecimal(true)` không buộc parse tiêu thụ hết đầu vào.** `"1,234.50kg"` vẫn có thể trả `BigDecimal("1234.50")` với index 8/10. Nó cũng không khiến grouping tự nhiên trở nên nghiêm ngặt.

Ngoài ra, một số giá trị đặc biệt như `NaN` hoặc dấu vô cực có thể được trả dưới dạng `Double` dù bật `setParseBigDecimal(true)`. Nếu nghiệp vụ đòi hỏi duy nhất `BigDecimal` hữu hạn, kiểm tra kiểu đầu ra và miền dữ liệu rõ ràng.

Một cách giải quyết tốt là chia quy trình thành các bước:

1. Chọn đúng `Locale` và `DecimalFormatSymbols`.
2. Định nghĩa grammar được hỗ trợ, precision/scale và dấu nhóm.
3. Parse với `ParsePosition` từ index 0.
4. Từ chối nếu parse không tạo giá trị hoặc chưa tiêu thụ hết.
5. Kiểm tra kiểu, dấu, precision, scale, min/max theo nghiệp vụ.
6. Chỉ sau đó đưa giá trị vào tính toán.

Hãy giữ phân biệt **kiểu dữ liệu**, **cú pháp văn bản** và **giá trị hợp lệ**: kiểm tra một khía cạnh không thay thế hai khía cạnh còn lại.

## 11. Ngày tháng: setLenient(false) vẫn có thể bỏ phần dư

Vấn đề không chỉ có ở số. Các API legacy `java.text.DateFormat` / `SimpleDateFormat` cũng hỗ trợ `ParsePosition`.

Ví dụ với pattern `dd/MM/yyyy`:

- `28/02/2026` là ngày hợp lệ theo pattern.
- `28/02/2026abc` có **tiền tố ngày hợp lệ**, phần `abc` vẫn còn.
- `31/02/2026` không phải ngày hợp lệ trong lịch thông thường.

`setLenient(false)` giúp từ chối ngày không tồn tại, nhưng **không bảo đảm parser đã tiêu thụ toàn bộ chuỗi**.

### Ví dụ Java 17+ hoàn chỉnh

Lưu thành `FullDateParseDemo.java`:

```java
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.util.Locale;

public class FullDateParseDemo {
    public static void main(String[] args) {
        SimpleDateFormat formatter =
                new SimpleDateFormat("dd/MM/yyyy", Locale.ROOT);
        formatter.setLenient(false);

        for (String raw : new String[] {
                "28/02/2026",
                "28/02/2026abc",
                "31/02/2026"
        }) {
            ParsePosition pos = new ParsePosition(0);
            Object date = formatter.parse(raw, pos);

            boolean valid = date != null &&
                    pos.getIndex() == raw.length();

            System.out.printf(
                    "%s -> valid=%s index=%d error=%d%n",
                    raw, valid, pos.getIndex(), pos.getErrorIndex());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac FullDateParseDemo.java
java FullDateParseDemo
```

Đầu ra:

```text
28/02/2026 -> valid=true index=10 error=-1
28/02/2026abc -> valid=false index=10 error=-1
31/02/2026 -> valid=false index=0 error=10
```

Chúng ta cần **cả hai loại kiểm tra**:

- `setLenient(false)` giúp kiểm tra tính hợp lệ của giá trị ngày.
- `pos.getIndex() == raw.length()` giúp kiểm tra không còn văn bản dư.

Mặc dù ví dụ dùng `SimpleDateFormat` để minh họa `ParsePosition`, ứng dụng mới nên cân nhắc `java.time.LocalDate` và `DateTimeFormatter`. `LocalDate.parse(text, formatter)` thông thường yêu cầu parse toàn bộ văn bản, và có thể kết hợp `ResolverStyle.STRICT` cho quy tắc ngày nghiêm ngặt. Khi dùng pattern cho năm trong trường hợp strict, nên hiểu sự khác nhau giữa `yyyy` (year-of-era) và `uuuu` (proleptic year), chẳng hạn `dd/MM/uuuu` là một lựa chọn rõ ràng. Không trộn kết quả parse theo `SimpleDateFormat` và `DateTimeFormatter` mà bỏ qua khác biệt về resolver/style.

## 12. Một phương thức tiện ích tái sử dụng: hợp đồng lỗi rõ ràng

Hàm `parseFully` có thể trả `Number` hoặc ném `ParseException`. Với hệ thống backend, bạn có thể biểu diễn lỗi thành loại có ý nghĩa nghiệp vụ, ví dụ `INVALID_NUMBER` hoặc `TRAILING_CHARACTERS`.

Khi giữ `ParsePosition`, bạn có thể tách lỗi:

```java
ParsePosition pos = new ParsePosition(0);
Number value = formatter.parse(input, pos);

if (value == null) {
    // Không phân tích được tiền tố tại vị trí bắt đầu.
} else if (pos.getIndex() < input.length()) {
    // Có số hợp lệ ở đầu nhưng còn ký tự dư.
} else {
    // Parse đã tiêu thụ hết; tiếp tục kiểm tra nghiệp vụ.
}
```

Đây là **mảnh code**, giả định các biến `formatter` và `input` đã được khai báo. `ParsePosition` cung cấp index để xác định phần dư:

```java
String remainder = input.substring(pos.getIndex());
```

Trong ví dụ `12.5kg`, `remainder` là `kg`. Chỉ dùng dữ liệu này để tạo thông báo hỗ trợ người dùng hoặc debug nếu phù hợp; không tự động bỏ phần dư rồi đưa số vào hệ thống mà không có chính sách.

Nếu parser hỗ trợ token hóa nhiều trường liên tiếp trong một chuỗi, có thể chủ động cập nhật `ParsePosition` và tiếp tục parse; khi đó một lần parse thành công một phần không phải lỗi, **miễn là ứng dụng sau cùng có bước kiểm tra toàn bộ đầu vào đã được xử lý đúng theo grammar**. Với trường nhập **một số duy nhất**, kiểm tra hết chuỗi phải xảy ra ngay sau lần parse đó.

## 13. Những bẫy bảo mật và tính toàn vẹn dữ liệu

Chấp nhận tiền tố hợp lệ có thể gây các loại lỗi:

- **Bỏ qua đơn vị đo:** `12kg` bị hiểu thành `12` trong trường không quy định đơn vị.
- **Bỏ qua ký hiệu/ký tự tiền tệ:** chuỗi có ký hiệu bất ngờ bị cắt, gây nhầm cách hiểu.
- **Còn payload sau số:** `100;DROP...` được chấp nhận như `100` nếu ứng dụng chỉ kiểm tra parse thành công; dù parser không tự thực thi payload, nó có thể che giấu dữ liệu sai ở những bước tiếp theo.
- **Sai số học do locale:** dấu `,` và `.` có ý nghĩa khác giữa các locale; parse một phần có thể lặng lẽ cho ra giá trị sai.
- **Mất precision:** số vượt giới hạn miền nghiệp vụ hoặc bị chuyển sang `double` dù dự định dùng decimal chính xác.
- **Phân tích không nhất quán:** một tầng dùng `Locale.US`, tầng khác dùng default locale của JVM.

Một chính sách validation tốt nên xác định **miền đầu vào** và **chuỗi nguồn có thể chấp nhận**, chứ không chỉ dựa vào việc parser “đã trả được một giá trị”.

Bên cạnh full-consumption, cân nhắc giới hạn độ dài input để tránh tải không cần thiết và validation miền giá trị (số âm, precision, scale, range). Đừng gửi nguyên input nhạy cảm vào log lỗi; có thể ghi chỉ số lỗi, loại lỗi và request ID phù hợp.

## 14. Các lỗi phổ biến cần tránh

1. **Chỉ bắt `ParseException` từ `parse(String)` rồi kết luận toàn bộ đầu vào hợp lệ.** Overload này có thể nhận tiền tố hợp lệ.
2. **Chỉ kiểm tra `result != null`.** Kết quả khác `null` vẫn có thể còn suffix.
3. **Chỉ kiểm tra `errorIndex == -1`.** Parser thường không coi phần dư là lỗi nội bộ.
4. **Chỉ so `index == length` mà quên `result != null`.** Input rỗng có thể khiến index và length đều bằng 0.
5. **Cắt phần dư để “sửa” đầu vào.** Chỉ được bỏ phần dư nếu nó được grammar định nghĩa rõ và đã xử lý.
6. **Trim/strip sau parse và so sai độ dài.** Nếu normalize, làm trước và so với độ dài chuỗi sau normalize.
7. **Coi full consumption là strict grouping.** `1,23` có thể vẫn được chấp nhận như `123` ở US.
8. **Tin rằng `setParseBigDecimal(true)` buộc parse toàn bộ.** Nó thay kiểu giá trị, không thay chính sách tiêu thụ hết.
9. **Coi `setLenient(false)` của SimpleDateFormat thay thế kiểm tra phần dư.** Nó chỉ kiểm soát việc diễn giải ngày.
10. **Dùng locale mặc định tình cờ của JVM.** Parser phải theo locale/hợp đồng input thực tế.
11. **So index ParsePosition với byte length hoặc code-point count.** Index Java dùng UTF-16.
12. **Tái sử dụng ParsePosition mà quên trạng thái.** Tạo mới tại index 0 cho mỗi giá trị độc lập.
13. **Bỏ qua ký hiệu/đơn vị bất ngờ vì “đã đọc được số”.** Dữ liệu nghiệp vụ cần được validate hoàn chỉnh.
14. **Không kiểm tra kiểu số/precision/range.** Tiêu thụ hết chỉ là điều kiện cú pháp ở tầng parser.

## 15. Bộ ca kiểm thử cần có

Đối với một trường nhập số theo `Locale.US`:

| Input | Hành vi mong muốn với chính sách “một số và không dư” |
|---|---|
| `123` | Chấp nhận |
| `123.45` | Chấp nhận |
| `1,234.50` | Chấp nhận nếu grouping được phép |
| `1,234.50abc` | Từ chối vì suffix |
| `123.45 ` | Từ chối nếu không cho khoảng trắng cuối |
| ` 123.45` | Từ chối nếu không cho khoảng trắng đầu |
| `abc123` | Từ chối vì không parse được từ đầu |
| Chuỗi rỗng | Từ chối |
| `1,23` | Từ chối **nếu** grammar yêu cầu nhóm ba chữ số chuẩn; không chỉ dựa trên ParsePosition |
| `1.234,50` | Từ chối hoặc xử lý theo locale khác có chủ đích; không đoán |
| Số quá lớn | Từ chối theo miền nghiệp vụ nếu vượt giới hạn |
| Số có quá nhiều decimals | Từ chối/round theo chính sách, không tự mất precision |

Đối với date, thử ngày hợp lệ, ngày không tồn tại và ngày hợp lệ kèm suffix. Đối với các hệ thống nhiều locale, thêm ca cho dấu thập phân/grouping, chữ số quốc tế, ký hiệu tiền tệ và whitespace đặc biệt.

## 16. Tự kiểm tra kiến thức

**Câu 1.** `NumberFormat.parse("12.5kg")` có thể thành công không?

**Đáp án:** Có; nó có thể trả `12.5` vì parse được tiền tố. Phải dùng `ParsePosition` để phát hiện `kg` còn dư.

**Câu 2.** `getErrorIndex() == -1` có chứng minh toàn bộ input đã được tiêu thụ không?

**Đáp án:** Không. Với `12.5kg`, error index có thể là `-1` dù `getIndex()==4` nhỏ hơn `length()==6`.

**Câu 3.** Điều kiện cốt lõi cho parser trả `Number` là gì?

**Đáp án:** `number != null && position.getIndex() == input.length()`, với `ParsePosition` khởi tạo tại 0 và chính sách không cho phép dư ký tự.

**Câu 4.** `1,23` được parser US đọc thành `123`, index bằng length. Có đủ để xác nhận grouping chuẩn US không?

**Đáp án:** Không. Cần validation grammar riêng nếu yêu cầu dấu phẩy phải chia đúng nhóm ba chữ số.

**Câu 5.** Có thể `strip()` trước parse không?

**Đáp án:** Có, **nếu chính sách cho phép whitespace đầu/cuối**. Khi đó so index với độ dài **chuỗi đã strip**, không phải chuỗi gốc.

**Câu 6.** `SimpleDateFormat.setLenient(false)` có từ chối `28/02/2026abc` chỉ vì suffix không?

**Đáp án:** Không nhất thiết. Nó có thể đọc ngày hợp lệ và còn `abc`; vẫn phải so `ParsePosition.getIndex()` với độ dài input.

**Câu 7.** Nếu ứng dụng chấp nhận input `12.5kg` như đại lượng có đơn vị thì phải làm gì?

**Đáp án:** Định nghĩa grammar có phần số và đơn vị, parse/validate cả hai thành phần và từ chối ký tự ngoài grammar; không coi đơn vị là phần dư được phép bỏ qua.

## 17. Ghi nhớ

**Parse thành công một phần không phải validation thành công.** Với các parser `java.text` dùng `ParsePosition`, hãy kiểm tra kết quả khác `null` **và** `getIndex()` bằng `input.length()` (sau chuẩn hóa đã được cho phép). Khi đã xác nhận không còn dữ liệu dư, tiếp tục kiểm tra đúng `Locale`, quy tắc grouping, miền giá trị và độ chính xác. Nguyên tắc “phân tích **toàn bộ** đầu vào theo grammar đã định nghĩa” giúp tránh các lỗi âm thầm khi bản địa hóa số/ngày và xử lý dữ liệu người dùng.

**Tham khảo chính thức:** [Java SE 17 — ParsePosition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html) · [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) · [Java SE 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html) · [Java SE 17 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html).
