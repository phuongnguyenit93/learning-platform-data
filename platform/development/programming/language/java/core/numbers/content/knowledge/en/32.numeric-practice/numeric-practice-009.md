# Thực hành: Parse và format cùng một giá trị số theo nhiều Locale trong Java

Trong hệ thống có người dùng ở nhiều quốc gia, **một giá trị số học có thể được viết thành những chuỗi rất khác nhau**. Ví dụ cùng giá trị một triệu hai trăm ba mươi tư nghìn năm trăm sáu mươi bảy phẩy tám mươi chín:

| Locale | Ví dụ chuỗi hiển thị | Dấu nhóm hàng nghìn | Dấu thập phân |
|---|---|---|---|
| `en-US` (Mỹ) | `1,234,567.89` | `,` | `.` |
| `de-DE` (Đức) | `1.234.567,89` | `.` | `,` |
| `fr-FR` (Pháp) | `1 234 567,89` | khoảng trắng hẹp không ngắt (`U+202F`) trong cấu hình CLDR thông dụng | `,` |
| `vi-VN` (Việt Nam) | `1.234.567,89` | `.` | `,` |

Trong đó, dấu cách của ví dụ Pháp có thể rất khó phân biệt bằng mắt với dấu cách thường. Quy ước locale của nền tảng có thể được cập nhật theo phiên bản dữ liệu CLDR/JDK và cấu hình nhà cung cấp locale. Không nên sao chép cứng một chuỗi được format rồi giả định nó bất biến giữa mọi môi trường.

**Mục tiêu thực hành:** bắt đầu từ **một** `BigDecimal`, format theo bốn locale, parse ngược bằng đúng locale, so sánh giá trị số học, đồng thời nhận biết vì sao parse với sai locale, parse một phần hoặc format đã làm tròn có thể làm thay đổi nghĩa của dữ liệu.

## 1. Phân biệt giá trị số học và chuỗi trình bày

`BigDecimal` mang giá trị thập phân; `Locale` quyết định quy ước trình bày và phân tích chuỗi theo ngôn ngữ/vùng. `Locale` không biến `1234567.89` thành một số học khác.

```java
BigDecimal amount = new BigDecimal("1234567.89");
```

Giá trị trên có thể format ra `1,234,567.89` trong `en-US`, `1.234.567,89` trong `de-DE`. Hai chuỗi không giống nhau, nhưng khi được parse theo đúng quy ước chúng đều có thể cho lại cùng giá trị số học.

Chuỗi hiển thị dành cho **con người** khác biểu diễn trao đổi giữa máy với máy. Với một trường decimal truyền bằng chuỗi trong giao thức, nếu giao thức yêu cầu định dạng trung lập như `1234567.89`, hãy dùng `toPlainString()` và `new BigDecimal(String)` theo đúng hợp đồng thay vì dựa vào locale đang cài ở hệ điều hành.

**Quan trọng:** `BigDecimal.toString()` hay `toPlainString()` không tự thay dấu thập phân thành dấu phẩy theo ngôn ngữ. Muốn format/parse theo locale, dùng công cụ tương ứng trong `java.text` hoặc một API khác có quy tắc được thiết kế tường minh.

## 2. Bộ API cần dùng trong Java 17+

Những lớp chính:

- `Locale` (`java.util.Locale`): định danh quy tắc ngôn ngữ/vùng như `Locale.US`, `Locale.GERMANY`, `Locale.FRANCE` và `Locale.forLanguageTag("vi-VN")`.
- `NumberFormat` (`java.text.NumberFormat`): factory cho việc format và parse giá trị số theo locale. `getNumberInstance(locale)` dành cho số thông thường; `getCurrencyInstance(locale)` phục vụ định dạng tiền tệ với các quy tắc khác.
- `DecimalFormat` (`java.text.DecimalFormat`): cung cấp cấu hình scale hiển thị, dấu nhóm, `RoundingMode` và đặc biệt `setParseBigDecimal(true)` để parse thành `BigDecimal` khi thích hợp.
- `DecimalFormatSymbols`: các ký hiệu như dấu thập phân, dấu nhóm, chữ số và ký hiệu số âm của một locale.
- `ParsePosition`: vị trí bắt đầu và kết thúc parse. Dùng để biết parser đã **tiêu thụ hết chuỗi** hay chỉ đọc một tiền tố hợp lệ.
- `BigDecimal`: đại diện chính xác cho giá trị decimal, thuận tiện cho các phép tính thập phân cần kiểm soát làm tròn.

Ví dụ lấy bộ formatter:

```java
Locale locale = Locale.GERMANY;
NumberFormat generic = NumberFormat.getNumberInstance(locale);
```

`NumberFormat` có kiểu trừu tượng. Các locale JDK phổ biến thường trả về `DecimalFormat` từ `getNumberInstance`; muốn dùng `setParseBigDecimal(true)`, chương trình nên kiểm tra kiểu trả về thay vì ép kiểu mà không nêu giả định.

```java
NumberFormat generic = NumberFormat.getNumberInstance(locale);
if (!(generic instanceof DecimalFormat format)) {
    throw new IllegalStateException(
            "DecimalFormat required for locale " + locale);
}
format.setParseBigDecimal(true);
```

Đây là ví dụ về cú pháp pattern matching cho `instanceof`, dùng được từ Java 17.

## 3. Format một BigDecimal theo từng Locale

Đối với bài thực hành có đúng hai vị trí thập phân, có thể cấu hình:

```java
DecimalFormat f =
        (DecimalFormat) NumberFormat.getNumberInstance(Locale.US);

f.setGroupingUsed(true);
f.setMinimumFractionDigits(2);
f.setMaximumFractionDigits(2);
f.setRoundingMode(RoundingMode.HALF_UP);

String display = f.format(new BigDecimal("1234567.89"));
// "1,234,567.89" với quy ước en-US phổ biến
```

Các lệnh có ý nghĩa khác nhau:

| Cấu hình | Ý nghĩa |
|---|---|
| `setGroupingUsed(true)` | Cho phép dấu phân nhóm chữ số như nghìn/triệu |
| `setMinimumFractionDigits(2)` | Hiển thị ít nhất hai chữ số phần thập phân; có thể thêm số 0 |
| `setMaximumFractionDigits(2)` | Không hiển thị quá hai chữ số phần thập phân; có thể **làm tròn** |
| `setRoundingMode(HALF_UP)` | Chọn cách làm tròn tại giới hạn phần thập phân |
| `setParseBigDecimal(true)` | Khi parse qua `DecimalFormat`, ưu tiên kết quả `BigDecimal` thay vì `Double`/`Long` |

**Cảnh báo:** định dạng để hiển thị có thể thay đổi giá trị số học khi giới hạn chữ số. Chẳng hạn `1.005` sẽ hiển thị thành `1.01` với cấu hình hai chữ số và `HALF_UP`. Không được suy ngược rằng chuỗi hiển thị luôn tái tạo đầy đủ giá trị số học gốc.

Nên xác định scale/mode theo quy tắc hiển thị hoặc nghiệp vụ đã phê duyệt. Đừng mặc định mọi số trong mọi miền đều cần hai chữ số.

### Locale khác nhau có dấu phân cách khác nhau

Giả sử sử dụng bốn formatter:

```java
NumberFormat us =
        NumberFormat.getNumberInstance(Locale.US);
NumberFormat de =
        NumberFormat.getNumberInstance(Locale.GERMANY);
NumberFormat fr =
        NumberFormat.getNumberInstance(Locale.FRANCE);
NumberFormat vi =
        NumberFormat.getNumberInstance(Locale.forLanguageTag("vi-VN"));
```

Không nên tự thay dấu trong một chuỗi `en-US` bằng `String.replace(",", ".")` rồi tiếp tục thay `"."` thành `","`. Dễ thay nhầm cả dấu nhóm và dấu thập phân, xử lý sai ký hiệu âm, khoảng trắng đặc biệt và chữ số của các hệ viết khác. Hãy để `NumberFormat` sử dụng ký hiệu của đúng locale.

## 4. Parse đúng Locale và giữ độ chính xác BigDecimal

Để parse chuỗi có dấu nhóm theo một locale, hãy dùng formatter được tạo từ **locale của nguồn dữ liệu**. Ví dụ:

```java
DecimalFormat german =
        (DecimalFormat) NumberFormat.getNumberInstance(Locale.GERMANY);
german.setParseBigDecimal(true);

Number value = german.parse("1.234.567,89");
// Với cấu hình này, value là BigDecimal mang giá trị 1234567.89
```

Đoạn trên có thể ném `ParseException` và phải đặt trong phương thức khai báo/ứng xử với ngoại lệ. Chương trình hoàn chỉnh ở phần sau dùng `ParsePosition` để kiểm tra hết chuỗi.

**Vì sao `setParseBigDecimal(true)` quan trọng?** Nếu không cấu hình, `NumberFormat.parse` trả về `Number` và một triển khai có thể trả `Long` hoặc `Double` tùy dữ liệu. `Double` là kiểu nhị phân gần đúng, có thể mất độ chính xác decimal. `DecimalFormat#setParseBigDecimal(true)` giúp giữ số decimal từ chuỗi được parse thành `BigDecimal` phù hợp với yêu cầu thực hành.

Ngay cả khi formatter đang được cấu hình hiển thị tối đa hai chữ số, thao tác parse là **một hoạt động riêng**: cần kiểm tra chuỗi đầu vào, các ký hiệu được nhận diện và giới hạn của API, không được đồng nhất tính hợp lệ của chuỗi với cấu hình hiển thị.

### Parse một phần là một bẫy rất phổ biến

Ví dụ chuỗi `"1,234.50foo"` trong `en-US`:

```java
DecimalFormat us =
        (DecimalFormat) NumberFormat.getNumberInstance(Locale.US);
us.setParseBigDecimal(true);

ParsePosition pos = new ParsePosition(0);
Number parsed = us.parse("1,234.50foo", pos);

// parsed = 1234.50 nhưng pos.getIndex() = 8,
// trong khi chiều dài chuỗi đầu vào là 11.
```

Nếu chỉ kiểm tra `parsed != null`, dữ liệu dư `foo` có thể bị bỏ qua. Do đó, để kiểm tra chuỗi đã được parse **hết**, cần:

```java
if (parsed == null || pos.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid number for locale");
}
```

Kiểm tra hết chuỗi **không làm NumberFormat trở thành trình phân tích nghiêm ngặt mọi cú pháp**. Một số formatter khá dễ dãi về vị trí nhóm chữ số; tùy yêu cầu, ứng dụng có thể cần kiểm tra pattern được phép, các ký tự Unicode, số chữ số, khoảng giá trị và quy tắc nghiệp vụ. Khi cần chuỗi **đúng một dạng trình bày chuẩn**, có thể format lại giá trị đã parse rồi so sánh với đầu vào sau khi áp dụng chính sách chuẩn hóa được định nghĩa rõ.

## 5. Không tự đoán Locale từ dấu phẩy/dấu chấm

Chuỗi `"1,234"` rất dễ gây nhầm:

| Locale parse | Cách hiểu hợp lệ theo quy ước phổ biến | Giá trị |
|---|---|---:|
| `en-US` | Dấu phẩy là dấu nhóm | 1234 |
| `de-DE` | Dấu phẩy là dấu thập phân | 1.234 |

Cả hai lần parse có thể tiêu thụ **toàn bộ** chuỗi và không báo lỗi, nhưng cho hai giá trị khác nhau! Vì vậy, điều kiện “parse hết chuỗi” là cần thiết cho dữ liệu chặt chẽ, nhưng **không chứng minh locale được chọn là đúng**.

Một số lời khuyên:

1. **Biết locale của nguồn**: từ lựa chọn của người dùng, hồ sơ locale của form, định dạng file nhập, hợp đồng API hoặc cột metadata.
2. **Không tự đoán chỉ từ IP/quốc gia của máy chủ**: ngôn ngữ trình bày và nguồn dữ liệu có thể khác nhau.
3. **Dữ liệu trao đổi giữa hệ thống nên có định dạng chuẩn**: ví dụ giá trị decimal ASCII không có dấu nhóm và dùng dấu chấm, theo hợp đồng rõ ràng.
4. Nếu nhập dữ liệu từ nhiều locale trong cùng một đợt, **lưu thông tin locale theo nguồn**, hoặc dùng bước xác nhận/cấu hình nhập rõ ràng.
5. Nếu dữ liệu mơ hồ, **không silently chọn** một locale để “thành công bằng mọi giá”; yêu cầu xác nhận hoặc dùng định dạng được đặc tả.

### Chuỗi Pháp và dấu cách Unicode

`fr-FR` có thể dùng khoảng trắng hẹp không ngắt `U+202F` để nhóm nghìn. Nó khác `U+0020` (dấu cách thường) và `U+00A0` (khoảng trắng không ngắt). Một đầu vào nhìn giống `"1 234 567,89"` chưa chắc chứa đúng code point mà formatter mong đợi.

Nếu parse thất bại hoặc chỉ parse tiền tố, kiểm tra code point thực tế thay vì chỉ nhìn trên màn hình. Đừng tùy tiện xóa **mọi** khoảng trắng trước khi parse: bạn có thể làm cho dữ liệu sai cú pháp trở nên hợp lệ hoặc vô tình xóa những ký tự mang nghĩa.

## 6. Chương trình Java 17+ độc lập: format và parse qua bốn locale

Tạo tệp `LocaleNumberDemo.java`. Chương trình dùng **một** `BigDecimal` chính xác, format theo `en-US`, `de-DE`, `fr-FR`, `vi-VN` rồi parse ngược. Các khoảng trắng Unicode đặc biệt được chuyển thành nhãn hiển thị để kết quả trong terminal dễ phân biệt.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.List;
import java.util.Locale;

public class LocaleNumberDemo {

    private static DecimalFormat decimalFor(Locale locale) {
        NumberFormat numberFormat =
                NumberFormat.getNumberInstance(locale);
        if (!(numberFormat instanceof DecimalFormat df)) {
            throw new IllegalStateException(
                    "DecimalFormat required: " + locale);
        }
        df.setGroupingUsed(true);
        df.setMinimumFractionDigits(2);
        df.setMaximumFractionDigits(2);
        df.setRoundingMode(RoundingMode.HALF_UP);
        df.setParseBigDecimal(true);
        return df;
    }

    private static BigDecimal parseFully(
            String input, Locale locale) {
        if (input == null) {
            throw new IllegalArgumentException("Null input");
        }
        DecimalFormat df = decimalFor(locale);
        ParsePosition position = new ParsePosition(0);
        Number number = df.parse(input, position);

        if (!(number instanceof BigDecimal decimal)
                || position.getIndex() != input.length()) {
            throw new IllegalArgumentException(
                    "Invalid number for " + locale.toLanguageTag());
        }
        return decimal;
    }

    private static String visible(String formatted) {
        return formatted.replace("\u202F", "<NNBSP>")
                .replace("\u00A0", "<NBSP>");
    }

    private static String tryParse(String input, Locale locale) {
        try {
            return parseFully(input, locale).toPlainString();
        } catch (IllegalArgumentException ex) {
            return "REJECTED";
        }
    }

    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("1234567.89");
        List<Locale> locales = List.of(
                Locale.US,
                Locale.GERMANY,
                Locale.FRANCE,
                Locale.forLanguageTag("vi-VN"));

        System.out.println("Original: " + original.toPlainString());

        for (Locale locale : locales) {
            DecimalFormat formatter = decimalFor(locale);
            String shown = formatter.format(original);
            BigDecimal parsed = parseFully(shown, locale);

            System.out.println(locale.toLanguageTag()
                    + " | " + visible(shown)
                    + " | " + parsed.toPlainString()
                    + " | sameValue="
                    + (parsed.compareTo(original) == 0));
        }

        System.out.println("Wrong locale: "
                + tryParse("1.234,50", Locale.US));
        System.out.println("Trailing text: "
                + tryParse("1,234.50foo", Locale.US));

        System.out.println("Ambiguous en-US: "
                + parseFully("1,234", Locale.US).toPlainString());
        System.out.println("Ambiguous de-DE: "
                + parseFully("1,234", Locale.GERMANY).toPlainString());

        BigDecimal needsRounding = new BigDecimal("1.005");
        String rounded = decimalFor(Locale.US).format(needsRounding);
        BigDecimal afterRoundTrip = parseFully(rounded, Locale.US);

        System.out.println("Original 1.005: "
                + needsRounding.toPlainString());
        System.out.println("Formatted 1.005: " + rounded);
        System.out.println("Parsed after format: "
                + afterRoundTrip.toPlainString());
        System.out.println("Same after rounding: "
                + (needsRounding.compareTo(afterRoundTrip) == 0));
    }
}
```

Biên dịch và chạy:

```bash
javac LocaleNumberDemo.java
java LocaleNumberDemo
```

Một kết quả tham chiếu theo dữ liệu locale CLDR phổ biến của JDK:

```text
Original: 1234567.89
en-US | 1,234,567.89 | 1234567.89 | sameValue=true
de-DE | 1.234.567,89 | 1234567.89 | sameValue=true
fr-FR | 1<NNBSP>234<NNBSP>567,89 | 1234567.89 | sameValue=true
vi-VN | 1.234.567,89 | 1234567.89 | sameValue=true
Wrong locale: REJECTED
Trailing text: REJECTED
Ambiguous en-US: 1234
Ambiguous de-DE: 1.234
Original 1.005: 1.005
Formatted 1.005: 1.01
Parsed after format: 1.01
Same after rounding: false
```

`<NNBSP>` trong stdout là **nhãn do phương thức `visible` tạo**, không phải chuỗi format thực tế. Thực tế `fr-FR` thường dùng ký tự Unicode `U+202F` ở vị trí đó; một môi trường dùng ký hiệu nhóm khác có thể in nhãn/chuỗi khác. Bảng kết quả cần được đối chiếu với locale provider/JDK đang chạy, còn các nguyên tắc về chọn locale, parse hết chuỗi và làm tròn vẫn không đổi.

**Phân tích kết quả:**

- Trong bốn vòng lặp, cùng `BigDecimal("1234567.89")` tạo các chuỗi địa phương hóa khác nhau. Parse bằng **đúng locale** cho lại giá trị decimal bằng nhau về số học.
- Parse `"1.234,50"` theo `en-US` chỉ đọc được một tiền tố theo cách hiểu của Mỹ; `parseFully` phát hiện chưa đọc hết và từ chối.
- `"1,234.50foo"` có một tiền tố số hợp lệ nhưng phần đuôi `foo` không hợp lệ, cũng bị từ chối.
- `"1,234"` được parse hoàn toàn theo cả Mỹ và Đức mà thành **hai số khác nhau**. Hệ thống phải biết đúng locale của input.
- Với `1.005`, formatter giới hạn **hai chữ số sau dấu** và dùng `HALF_UP` nên phát ra `1.01`. Parse chuỗi hiển thị không thể khôi phục chữ số thứ ba đã bị bỏ.

## 7. Phân biệt round-trip về giá trị, về scale và về chuỗi

Một “round-trip” có thể nhắm đến ba mục tiêu:

1. **Giá trị toán học bằng nhau**: `original.compareTo(parsed) == 0` với `BigDecimal`. Hữu ích khi scale không mang nghĩa nghiệp vụ.
2. **Giá trị và scale trùng nhau**: `original.equals(parsed)`. Hữu ích khi cách biểu diễn thập phân cũng quan trọng.
3. **Chuỗi nhập và chuỗi format lại giống nhau**: `input.equals(formatter.format(parsed))`. Đây là điều kiện kiểm tra **dạng biểu diễn chuẩn** theo formatter, mạnh hơn việc parse hết chuỗi nhưng cũng có thể từ chối các cách nhập hợp lệ khác như không có dấu nhóm.

Ví dụ:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
```

Phần scale không chỉ là kiểu trình bày: với `BigDecimal.equals()`, scale có tham gia so sánh. Nếu chương trình chỉ cần số học bằng nhau, dùng `compareTo() == 0`; nếu scale là một phần của hợp đồng, hãy kiểm tra scale.

**Chú ý với validation canonical:** formatter có thể chủ động thêm số 0, thêm dấu nhóm hoặc chuyển dấu/kiểu chữ số, vì vậy so sánh chuỗi raw với chuỗi chuẩn phải là quyết định được nêu trong UX/API. Không ép người nhập phải dùng đúng mọi dấu nhóm và khoảng trắng nếu yêu cầu thực tế cho phép nhiều cách nhập hợp lệ.

## 8. Khi nào parse là đủ, khi nào cần thêm validation?

`DecimalFormat.parse` là bộ phân tích số địa phương hóa, **không phải bộ kiểm tra toàn bộ quy tắc nghiệp vụ của form**. Một giá trị parse thành công vẫn có thể không hợp lệ vì những lý do khác.

Một pipeline đáng tin cậy thường có:

1. **Nguồn locale xác định rõ:** lấy từ ngữ cảnh input; không dùng `Locale.getDefault()` một cách ngầm nếu xử lý dữ liệu từ nhiều người dùng.
2. **Parse theo locale:** dùng đúng formatter và `setParseBigDecimal(true)` khi cần decimal exact.
3. **Kiểm tra cú pháp:** parse phải tiêu thụ hết chuỗi, sau đó áp dụng yêu cầu về ký hiệu, dấu nhóm, số chữ số, ký tự được phép hoặc format canonical tùy trường hợp.
4. **Kiểm tra miền giá trị:** không âm, lớn hơn 0, không vượt giới hạn, không có phần thập phân nếu là số lượng nguyên, v.v.
5. **Chính sách lượng hóa:** nếu cần làm tròn đến đơn vị nào, phải quy định scale/mode và thời điểm áp dụng. Formatter giao diện **không tự quyết định** quy tắc lưu trữ.
6. **Lưu/trao đổi dạng trung lập:** lưu giá trị decimal hoặc chuỗi máy theo hợp đồng, giữ thông tin locale/đơn vị nếu cần tái hiện input hay audit.

### Ví dụ validation số lượng nguyên

```java
BigDecimal parsed = parseFully("1.234", Locale.GERMANY);
// Với de-DE, đây là 1234 theo dấu nhóm.

int quantity = parsed.intValueExact();
// Thành công nếu giá trị nguyên và vừa miền int.
```

Nếu một người nhập `"1,234"` theo `de-DE`, kết quả lại là `1.234` và `intValueExact()` sẽ ném `ArithmeticException` do phần lẻ. Cả hai hành vi đều hợp lý theo định dạng Đức nhưng cần đúng mục đích trường nhập.

Khi parse tiền tệ, `getCurrencyInstance(locale)` có thể format kèm ký hiệu tiền nhưng **locale trình bày không phải mã tiền tệ đáng tin cậy để tự suy ra nghĩa của khoản tiền**; ví dụ đơn vị ISO 4217 hoặc mã tiền thực tế nên nằm trong dữ liệu theo hợp đồng.

### Format dữ liệu với vai trò trình bày

Một phép tính thập phân có thể giữ nhiều chữ số để tính toán và chỉ định dạng ít chữ số trên UI. Nếu sau đó lấy chuỗi UI đã làm tròn đem parse lại rồi dùng cho phép tính tiếp, bạn đã làm mất thông tin. Tránh coi chuỗi được format là **bản gốc** cho luồng tính toán nếu không có quyết định nghiệp vụ rõ ràng.

## 9. Thread safety, hiệu năng và lựa chọn API

`NumberFormat`/`DecimalFormat` là những lớp **có trạng thái, mutable và nói chung không an toàn để chia sẻ giữa nhiều luồng mà không đồng bộ hóa**. Khi xử lý nhiều request song song:

- Không giữ một `static DecimalFormat` dùng chung cho toàn bộ yêu cầu rồi liên tục thay locale, pattern, rounding và parse flags trên nó.
- Có thể tạo một formatter riêng theo lượt dùng, theo luồng hoặc áp dụng kỹ thuật cache an toàn với trạng thái bất biến/copy phù hợp.
- `Locale` là mô tả quy ước; bản thân lựa chọn `Locale` không thay thế việc quản lý formatter.
- Cấu hình formatter rõ ràng và kiểm thử hành vi với JDK/locale provider của môi trường triển khai.

Nếu chỉ cần trao đổi số decimal giữa các dịch vụ, `BigDecimal.toPlainString()`/`new BigDecimal(String)` hoặc định dạng JSON numeric theo hợp đồng thường đơn giản hơn việc tạo formatter địa phương hóa ở tầng transport. Chỉ dùng parsing locale tại ranh giới **nhập chuỗi dành cho con người**.

## 10. Lỗi thường gặp

1. **Dùng `Double.parseDouble("1.234,56")` để đọc số Đức.** API này không hiểu dấu nhóm/thập phân theo locale đó; cần parse theo locale hoặc định dạng máy chuẩn.
2. **Dùng `NumberFormat.getInstance()` không truyền locale.** Kết quả phụ thuộc default locale của tiến trình, dễ thay đổi giữa máy dev, máy test và production.
3. **Dựa vào `NumberFormat.parse` mà không kiểm tra phần dư.** Parser có thể chỉ đọc tiền tố hợp lệ và bỏ qua ký tự phía sau.
4. **Parse bằng sai locale nhưng vẫn ra số.** Chuỗi `"1,234"` là ví dụ nguy hiểm: hai locale hiểu thành hai giá trị hoàn toàn khác nhau.
5. **Cho rằng parse hết chuỗi tương đương validation nghiêm ngặt.** Vẫn cần kiểm tra pattern/miền dữ liệu nếu nghiệp vụ yêu cầu.
6. **Không bật `setParseBigDecimal(true)` khi cần decimal exact.** Kết quả `Number` có thể là kiểu khác, gây mất độ chính xác trong phép tính tiếp.
7. **Format rồi parse lại mà kỳ vọng mọi chữ số được bảo toàn.** Formatter có thể làm tròn bằng `setMaximumFractionDigits`.
8. **Dùng chuỗi `fr-FR` với dấu cách thường thay vì dấu Unicode đúng.** Bằng mắt khó phân biệt; cần kiểm tra code point thực tế.
9. **Cố tự thay dấu chấm/phẩy thủ công.** Có thể thay cả dấu nhóm và dấu thập phân, hoặc không xử lý âm/Unicode.
10. **Chia sẻ `DecimalFormat` mutable giữa các luồng.** Cấu hình và kết quả có thể bị can thiệp đồng thời.
11. **Hiểu locale là đơn vị tiền.** Cần quản lý currency code, đơn vị và chính sách số học độc lập với định dạng hiển thị.
12. **Không kiểm thử với nhiều JDK/provider.** Ký hiệu locale thay đổi theo dữ liệu chuẩn, nên tránh hard-code những ký tự không được hợp đồng đảm bảo.

## 11. Tự kiểm tra

**Câu 1.** Cùng giá trị `1234.5` hiển thị khác nhau như thế nào trong `en-US` và `de-DE`?  
**Đáp án:** Ví dụ phổ biến: `1,234.50` và `1.234,50` nếu bật grouping và buộc hiển thị hai vị trí thập phân.

**Câu 2.** `"1,234"` được hiểu giống nhau trong Mỹ và Đức không?  
**Đáp án:** Không. `en-US` thường parse thành `1234`, `de-DE` thành `1.234`. Cần biết locale của input, không thể suy ra chỉ từ kết quả parse thành công.

**Câu 3.** Vì sao cần `ParsePosition` thay vì chỉ kiểm tra `NumberFormat.parse` không ném lỗi?  
**Đáp án:** Parser có thể đọc một tiền tố hợp lệ rồi bỏ qua phần đuôi. `position.getIndex() == input.length()` giúp xác nhận đã tiêu thụ hết chuỗi.

**Câu 4.** Parse hết chuỗi có bảo đảm người dùng viết dấu nhóm theo đúng mẫu mong muốn không?  
**Đáp án:** Không hoàn toàn; `NumberFormat` có thể tương đối dễ dãi. Nếu hợp đồng cần cú pháp canonical, phải có kiểm tra bổ sung.

**Câu 5.** Vì sao nên bật `DecimalFormat#setParseBigDecimal(true)` trong bài toán tính toán decimal chính xác?  
**Đáp án:** Để parse thành `BigDecimal` thay vì phải chấp nhận một kết quả `Double` gần đúng hoặc `Long` tùy giá trị.

**Câu 6.** Format `1.005` bằng `HALF_UP` và tối đa hai chữ số, sau đó parse lại, có được giá trị gốc không?  
**Đáp án:** Không. Chuỗi hiển thị là `1.01`; chữ số đã bị làm tròn không thể được phục hồi.

**Câu 7.** Vì sao dấu cách trong số kiểu Pháp đôi khi không parse được dù trông giống mẫu?  
**Đáp án:** Có các ký tự khoảng trắng Unicode khác nhau như `U+0020`, `U+00A0` và `U+202F`. Phải dùng đúng quy ước của formatter hoặc một bước chuẩn hóa được đặc tả.

**Câu 8.** Khi truyền giá trị decimal giữa hai microservice, nên dùng locale của máy chủ để format chuỗi giao thức không?  
**Đáp án:** Không, trừ khi giao thức quy định như vậy. Nên dùng định dạng số trung lập, không có dấu nhóm, với dấu thập phân/mã đơn vị đã được xác định rõ.

**Ghi nhớ:** `format(value, locale)` tạo cách **trình bày**; `parse(text, locale)` diễn giải chuỗi theo **locale của nguồn**. Để tránh sai dữ liệu, hãy giữ `BigDecimal` làm giá trị gốc, chọn đúng locale, kiểm tra parse tiêu thụ hết chuỗi và xác định rõ khi nào được phép làm tròn.
