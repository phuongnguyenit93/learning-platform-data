# Thành phần language, script, region và variant trong Java `Locale`

## 1. Bản chất của `Locale`

`java.util.Locale` định danh ngôn ngữ, hệ chữ viết và quy ước vùng miền được dùng trong bản địa hóa (localization). Bốn thành phần quan trọng của mô hình là:

| Thành phần | Câu hỏi nó trả lời | Ví dụ | Getter Java |
|---|---|---|---|
| `language` | Dùng ngôn ngữ nào? | `vi`, `en`, `sr`, `zh` | `getLanguage()` |
| `script` | Viết bằng hệ chữ nào? | `Latn`, `Cyrl`, `Hans`, `Hant` | `getScript()` |
| `region` | Ưu tiên quy ước vùng nào? | `VN`, `US`, `TW`, `419` | `getCountry()` |
| `variant` | Có biến thể chuyên biệt nào? | `POSIX`, `rozaj` | `getVariant()` |

Các thành phần diễn tả những chiều khác nhau. Một ngôn ngữ có thể được viết bằng nhiều hệ chữ; một vùng có thể dùng nhiều ngôn ngữ; cùng một ngôn ngữ có thể có quy ước trình bày khác ở các vùng. `Locale` còn có **extensions** (ví dụ lịch hoặc hệ chữ số), nằm ngoài bốn thành phần trên.

`Locale` là một **định danh/ngữ cảnh** cho API, không phải kho bản dịch, không biểu diễn múi giờ và không suy ra vị trí địa lý thực tế của người dùng. Có một `Locale` hợp lệ cũng không bảo đảm hệ thống có bản dịch hoặc dữ liệu chuyên biệt cho locale đó.

## 2. BCP 47: Biểu diễn thành language tag

Thẻ ngôn ngữ IETF BCP 47 thường có dạng:

```text
language[-Script][-REGION][-variant...][-extension...]
```

Các subtag phân cách bằng dấu gạch nối `-`. Quy ước dễ đọc là language chữ thường (`en`), script viết hoa chữ đầu (`Latn`), region chữ hoa (`US`), variant thường viết chữ thường. Java chuẩn hóa một số trường khi xây dựng `Locale`; không dựa vào kiểu chữ để suy đoán nội dung.

| Language tag | Language | Script | Region | Variant | Ý nghĩa |
|---|---|---|---|---|---|
| `vi-VN` | `vi` | trống | `VN` | trống | Tiếng Việt tại Việt Nam |
| `en-US` | `en` | trống | `US` | trống | Tiếng Anh tại Hoa Kỳ |
| `en-GB` | `en` | trống | `GB` | trống | Tiếng Anh tại Anh |
| `sr-Latn-RS` | `sr` | `Latn` | `RS` | trống | Tiếng Serbia, chữ Latin, tại Serbia |
| `sr-Cyrl-RS` | `sr` | `Cyrl` | `RS` | trống | Tiếng Serbia, chữ Cyrillic, tại Serbia |
| `zh-Hant-TW` | `zh` | `Hant` | `TW` | trống | Tiếng Trung, chữ Hán phồn thể, tại Đài Loan |
| `en-US-POSIX` | `en` | trống | `US` | `POSIX` | Một biến thể POSIX |

Trường **không xuất hiện** thực sự là trường rỗng trong đối tượng, không phải giá trị mặc định được tự điền. `zh-TW` không khai báo script, dù ứng dụng có thể suy đoán từ dữ liệu văn hóa. Nếu chính hệ chữ là điều kiện chọn nội dung, nên dùng tag tường minh như `zh-Hant-TW`.

## 3. `language` — ngôn ngữ

`language` xác định ngôn ngữ được yêu cầu, thường sử dụng mã ISO 639 như `vi` (tiếng Việt), `en` (tiếng Anh), `fr` (tiếng Pháp), `ja` (tiếng Nhật), `zh` (tiếng Trung), `sr` (tiếng Serbia). Mã ngôn ngữ phổ biến có hai hoặc ba chữ cái; BCP 47 cho phép thêm các dạng cú pháp hợp lệ khác. `getLanguage()` trả về mã được chuẩn hóa chữ thường.

Điểm cốt lõi: **language không đồng nghĩa quốc gia**. `en` không mặc nhiên là `en-US`; `fr` không mặc nhiên là `fr-FR`. Language cũng không chỉ định script nếu script bị bỏ trống. Với ứng dụng chỉ cần chọn ngôn ngữ chung, `Locale.forLanguageTag("en")` có thể đủ. Nếu lựa chọn quy tắc ngày, tiền tệ hay cách viết cụ thể, cần xem thêm region/script.

## 4. `script` — hệ chữ viết

`script` dùng mã ISO 15924 gồm **bốn chữ cái**; các ví dụ gồm `Latn` (Latin), `Cyrl` (Cyrillic), `Hans` (Hán giản thể), `Hant` (Hán phồn thể) và `Arab` (Ả Rập). `getScript()` trả về mã với chữ đầu viết hoa khi trường này hiện diện.

Script có ý nghĩa thực tế khi cùng một language tồn tại ở nhiều hệ chữ:

- `sr-Latn` và `sr-Cyrl` đều là tiếng Serbia, nhưng sử dụng chữ Latin và Cyrillic.
- `zh-Hans` và `zh-Hant` đều có language `zh`, nhưng phân biệt hệ chữ Hán giản thể/phồn thể.

`Hans`/`Hant` là **script**, không phải region. Script cũng khác **encoding**: `Latn` không có nghĩa là UTF-8; việc mã hóa byte thuộc API khác (chẳng hạn `StandardCharsets.UTF_8`). Nếu chỉ so `getLanguage()` mà bỏ script, ứng dụng có thể phục vụ bộ chữ không phù hợp.

## 5. `region` — quốc gia hoặc khu vực

`region` thường là mã quốc gia ISO 3166-1 hai chữ cái (`VN`, `US`, `FR`, `TW`) hoặc mã khu vực UN M.49 ba chữ số (`001` là thế giới, `419` là Mỹ Latinh). Cấu trúc API Java có sự khác biệt tên gọi: `Locale.Builder.setRegion(...)` để đặt region, nhưng `Locale.getCountry()` để đọc nó. Với mã chữ, giá trị được chuẩn hóa chữ hoa; mã vùng số giữ nguyên.

`en-US` và `en-GB` cùng language nhưng khác region; `en-CA` và `fr-CA` cùng region nhưng khác language. Region hỗ trợ lựa chọn định dạng số, ngày tháng, tiền tệ và các quy ước địa phương, nhưng **không tự quyết định** toàn bộ dữ liệu. Kết quả còn tùy API, phiên bản JDK và dữ liệu locale/provider.

Không dùng region thay cho **múi giờ** hoặc **tiền tệ cố định**: một quốc gia có thể có nhiều múi giờ, còn các quy tắc tiền tệ có thể thay đổi. Dùng `java.time.ZoneId` và `java.util.Currency` khi nghiệp vụ cần định danh chuyên biệt.

## 6. `variant` — biến thể chuyên biệt

`variant` biểu thị biến thể cụ thể chưa được mô tả đầy đủ bằng language + script + region. `getVariant()` trả chuỗi rỗng khi không có variant.

BCP 47 yêu cầu mỗi subtag variant có **5–8 ký tự chữ/số**, hoặc **4 ký tự với ký tự đầu là số**. Có thể có nhiều variant. `POSIX` và `rozaj` là ví dụ có cú pháp phù hợp. `Locale.Builder.setVariant(...)` kiểm tra cú pháp và có thể ném `IllformedLocaleException` khi sai. Nó **không** tự xác thực mỗi mã có được đăng ký hay có ý nghĩa thực tế trong dữ liệu locale.

Ba ví dụ cần phân biệt:

- `en-US`: variant rỗng.
- `en-US-POSIX`: variant là `POSIX`.
- `en-US-u-nu-thai`: variant vẫn rỗng; phần `u-nu-thai` là **Unicode locale extension** chỉ hệ chữ số `thai`. Lấy bằng `getUnicodeLocaleType("nu")`.

Tương tự, `u-ca-japanese` chỉ lựa chọn hệ lịch thuộc extension, không phải variant. Không dùng variant để nhét ID người dùng, tenant, thông tin giờ hoặc cấu hình tùy ý. Constructor legacy `new Locale(language, country, variant)` có thể chứa variant không theo cú pháp BCP 47; việc chuyển ngược sang language tag có thể gây vấn đề tương thích. Với mã mới, ưu tiên `Locale.Builder` và các tag chuẩn.

## 7. Ví dụ Java 17+ chạy được: đọc đủ bốn thành phần

Tạo tệp `LocalePartsDemo.java`:

```java
import java.util.Locale;

public class LocalePartsDemo {
    public static void main(String[] args) {
        show(Locale.forLanguageTag("en-US"));
        show(Locale.forLanguageTag("sr-Latn-RS"));
        show(Locale.forLanguageTag("zh-Hant-TW"));

        Locale posix = new Locale.Builder()
                .setLanguage("en")
                .setRegion("US")
                .setVariant("POSIX")
                .build();
        show(posix);
    }

    private static void show(Locale locale) {
        System.out.printf(
                "tag=%s | language=%s | script=%s | region=%s | variant=%s%n",
                locale.toLanguageTag(),
                display(locale.getLanguage()),
                display(locale.getScript()),
                display(locale.getCountry()),
                display(locale.getVariant()));
    }

    private static String display(String value) {
        return value.isEmpty() ? "(trong)" : value;
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac LocalePartsDemo.java
java LocalePartsDemo
```

Đầu ra:

```text
tag=en-US | language=en | script=(trong) | region=US | variant=(trong)
tag=sr-Latn-RS | language=sr | script=Latn | region=RS | variant=(trong)
tag=zh-Hant-TW | language=zh | script=Hant | region=TW | variant=(trong)
tag=en-US-POSIX | language=en | script=(trong) | region=US | variant=POSIX
```

`(trong)` chỉ là ký hiệu do hàm `display` tự đặt để trình bày; các getter thực tế trả về `""` cho thành phần thiếu. Đặc biệt, getter region mang tên `getCountry()`, không có `getRegion()` tương ứng.

## 8. Tạo `Locale`, chuyển đổi và kiểm tra cú pháp

### Từ language tag BCP 47

```java
Locale locale = Locale.forLanguageTag("sr-Latn-RS");
String tag = locale.toLanguageTag(); // "sr-Latn-RS"
```

`forLanguageTag(...)` thích hợp để chuyển language tag hợp lệ thành `Locale`. Nhưng nó **không phải công cụ xác thực nghiêm ngặt**: khi gặp subtag sai, nó có thể bỏ qua phần không hợp lệ mà không ném ngoại lệ.

### Từ các trường riêng biệt

```java
Locale locale = new Locale.Builder()
        .setLanguage("sr")
        .setScript("Latn")
        .setRegion("RS")
        .build();

System.out.println(locale.toLanguageTag()); // sr-Latn-RS
```

`Builder` phù hợp khi biểu mẫu/cấu hình cung cấp từng thành phần. Nó kiểm tra cú pháp language, script, region, variant và extension; đối với chuỗi sai cú pháp, có thể ném `IllformedLocaleException`. Tuy nhiên, một tổ hợp **đúng cú pháp** vẫn có thể không có tài nguyên hay không được ứng dụng hỗ trợ.

Ví dụ đầy đủ về kiểm tra language tag với Builder, lưu `ValidateLocaleTag.java`:

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class ValidateLocaleTag {
    public static void main(String[] args) {
        String input = "sr-Latn-RS";

        try {
            Locale locale = new Locale.Builder()
                    .setLanguageTag(input)
                    .build();
            System.out.println(locale.toLanguageTag());
        } catch (IllformedLocaleException exception) {
            System.out.println("Language tag sai cu phap");
        }
    }
}
```

Chạy `javac ValidateLocaleTag.java` rồi `java ValidateLocaleTag`. Đầu ra:

```text
sr-Latn-RS
```

`Locale.Builder.setLanguageTag(...)` có thể phát hiện lỗi cú pháp, nhưng xác thực danh sách locale được hỗ trợ là chính sách riêng của ứng dụng. Nếu dữ liệu đầu vào là cả header `Accept-Language` với trọng số `q=...`, phải xử lý theo cú pháp negotiation thích hợp (chẳng hạn `Locale.LanguageRange`/`Locale.lookup`), không truyền toàn bộ header làm một language tag.

### Tại sao chọn `toLanguageTag()` thay vì `toString()`?

`Locale.toString()` sử dụng biểu diễn lịch sử của Java, có thể chứa dấu `_` và các phần script/extension theo cấu trúc không phải BCP 47. Khi lưu hoặc trao đổi locale với API, dùng `toLanguageTag()`; để đọc lại, dùng `forLanguageTag(...)` hoặc `Builder`. Không tự tách `toString()` theo dấu gạch dưới để suy ra đủ bốn thành phần.

## 9. Áp dụng trong bản địa hóa

Các thành phần khác nhau dẫn đến lựa chọn khác nhau:

| Nhu cầu | Thành phần liên quan | Ví dụ |
|---|---|---|
| Chọn văn bản dịch | Language và đôi khi script | `vi`; `sr-Latn` |
| Chọn đúng hệ chữ | Script | `sr-Latn` / `sr-Cyrl` |
| Chọn quy ước định dạng theo vùng | Language + region | `en-US` / `en-GB` |
| Nhận diện biến thể hiếm đã được định nghĩa | Variant | `sl-rozaj` |
| Chọn hệ số hoặc lịch | Unicode extension, không phải variant | `en-US-u-nu-thai`; `ja-JP-u-ca-japanese` |

Ví dụ API định dạng nhận locale làm tham số, lưu tệp `FormatWithLocale.java`:

```java
import java.text.NumberFormat;
import java.util.Locale;

public class FormatWithLocale {
    public static void main(String[] args) {
        Locale us = Locale.forLanguageTag("en-US");
        Locale fr = Locale.forLanguageTag("fr-FR");

        System.out.println(NumberFormat.getCurrencyInstance(us).format(1234.5));
        System.out.println(NumberFormat.getCurrencyInstance(fr).format(1234.5));
    }
}
```

Chạy `javac FormatWithLocale.java` rồi `java FormatWithLocale`. Dấu nhóm, dấu thập phân, ký hiệu tiền tệ và khoảng trắng có thể khác nhau theo JDK/provider/dữ liệu locale; vì vậy **không hardcode một stdout duy nhất** cho ví dụ này. `Locale` xác định yêu cầu ngữ cảnh, còn `NumberFormat` thực hiện định dạng.

`ResourceBundle` cũng dùng `Locale` để tìm bundle thích hợp. Khi tài nguyên của tổ hợp yêu cầu không tồn tại, cơ chế tìm kiếm có thể fallback sang ngôn ngữ/vùng ít cụ thể hơn, locale mặc định hoặc bundle gốc theo quy tắc của `ResourceBundle`. Đừng suy ra rằng một `Locale` hợp lệ sẽ có bản dịch đầy đủ; nên kiểm thử nội dung thực sự trả về sau fallback.

Một số API dùng default locale nếu không truyền đối tượng. Trong ứng dụng máy chủ xử lý nhiều người dùng, nên **truyền `Locale` tường minh cho từng lời gọi**. `Locale.setDefault(...)` thay đổi trạng thái mặc định toàn cục, có thể tác động đến luồng/request khác. Java còn phân biệt mặc định cho `Locale.Category.DISPLAY` và `Locale.Category.FORMAT`.

## 10. Lỗi phổ biến và cách tránh

1. **Nhầm `language` với `region`**: `en` là tiếng Anh, `US` là Hoa Kỳ; `en-US` chứa cả hai.
2. **Bỏ qua script**: `sr-Latn-RS` và `sr-Cyrl-RS` khác hệ chữ, dù language và region trùng nhau.
3. **Suy ra hệ chữ từ region**: `zh-TW` không khai báo `Hant`; dùng `zh-Hant-TW` khi yêu cầu phải rõ.
4. **Dùng region thay múi giờ**: region không xác định duy nhất `ZoneId`; xử lý múi giờ bằng API ngày giờ.
5. **Nhầm variant với extension**: `getVariant()` không trả `nu-thai`; dùng `getUnicodeLocaleType("nu")`.
6. **Dùng `en_US` như thẻ BCP 47**: tag chuẩn là `en-US`; legacy Java có thể dùng dấu `_` trong `toString()`.
7. **Coi `forLanguageTag` là validator**: phương thức có thể chấp nhận một phần chuỗi; dùng `Builder` và kiểm tra danh sách hỗ trợ nếu cần chặt chẽ.
8. **Coi `Builder` là validator ngữ nghĩa**: nó chỉ xác nhận dạng cú pháp hợp lệ, không chứng minh mã đã đăng ký hay có tài nguyên dịch.
9. **Thao tác default locale trong mỗi request**: dễ ảnh hưởng luồng khác; truyền locale tường minh.
10. **Dùng tên hiển thị làm ID**: `getDisplayName(...)` có thể thay đổi theo ngôn ngữ hiển thị/dữ liệu JDK; dùng đối tượng `Locale` và language tag để định danh.

## 11. Kiểm tra kiến thức

- `sr-Latn-RS` so với `sr-Cyrl-RS`: khác **script**.
- `en-US` so với `en-GB`: khác **region**.
- `zh-Hant-TW`: `language=zh`, `script=Hant`, `region=TW`, `variant=""`.
- `en-US-POSIX`: có **variant**; `en-US-u-nu-thai`: có **Unicode extension**, variant rỗng.
- Đọc region bằng `getCountry()`; lưu/truyền BCP 47 bằng `toLanguageTag()`.
- Chỉ khai báo các thành phần thực sự biết; khi tính năng phải phân biệt script/vùng/variant, khai báo chúng rõ ràng và kiểm thử cơ chế fallback.

**Tham khảo:** [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html) · [Java SE 17 — Locale.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html) · [IANA Language Subtag Registry](https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry).
