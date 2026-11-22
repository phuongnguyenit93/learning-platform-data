# Phân biệt kiểm tra cú pháp với xác minh mã ngôn ngữ hoặc khu vực trong Java

## 1. Bài toán: một chuỗi giống mã locale có thật sự dùng được?

Khi chương trình nhận một locale từ cấu hình, hồ sơ người dùng hoặc tiêu đề HTTP (ví dụ `vi-VN`, `en-US`, `zh-Hant-TW`), có ít nhất **ba câu hỏi độc lập** cần trả lời:

1. **Cú pháp hợp lệ (well-formed):** Chuỗi có tuân theo cấu trúc thẻ ngôn ngữ BCP 47 hay không?
2. **Mã có được đăng ký/công nhận (registered/valid):** Các thành phần như ngôn ngữ, chữ viết, khu vực có thuộc bộ mã hoặc registry áp dụng hay không? Chúng có được kết hợp đúng các ràng buộc của registry không?
3. **Có được hỗ trợ trong ngữ cảnh sử dụng:** Runtime, thư viện, resource bundle và chính sản phẩm có đủ dữ liệu, bản dịch hoặc chính sách để phục vụ locale đó hay không?

Ba điều kiện không tương đương nhau. **Một locale được Java tạo thành công không chứng minh ngôn ngữ và khu vực tồn tại; một mã có thật không chứng minh ứng dụng đã hỗ trợ giao diện tương ứng.**

Ví dụ `xx-YY` có cấu trúc của một language tag (hai chữ cái cho ngôn ngữ, hai chữ cái cho khu vực). Trên Java 17, `Locale.Builder` chấp nhận cú pháp và có thể tạo `Locale`, nhưng tài liệu Java nêu đây là ví dụ **các subtag không đăng ký** trong IANA Language Subtag Registry. Ứng dụng tiếng Việt/tiếng Anh cũng không có lý do tự động cung cấp bản dịch cho nó.

## 2. Đọc cú pháp của một locale theo BCP 47

Thẻ ngôn ngữ thường dùng dấu gạch ngang `-` để ngăn các thành phần:

| Ví dụ | Phân tích | Ý nghĩa |
| --- | --- | --- |
| `vi` | language = `vi` | Tiếng Việt, không chỉ định khu vực |
| `vi-VN` | language = `vi`, region = `VN` | Tiếng Việt gắn khu vực Việt Nam |
| `en-US` | language = `en`, region = `US` | Tiếng Anh (Mỹ) |
| `sr-Latn-RS` | language = `sr`, script = `Latn`, region = `RS` | Tiếng Serbia, chữ Latin, Serbia |
| `zh-Hant-TW` | language = `zh`, script = `Hant`, region = `TW` | Tiếng Hoa, chữ phồn thể, Đài Loan |
| `en-US-u-nu-latn` | thêm Unicode extension `u` | Có chỉ dẫn về hệ chữ số Latin |

Đối với các trường mà `Locale.Builder.setLanguage`, `setScript`, `setRegion` chấp nhận, Java 17 mô tả các dạng well-formed cơ bản:

- **Language:** từ 2 đến 8 ký tự chữ cái ASCII; không phải cứ đúng số ký tự là đã có mã ngôn ngữ đăng ký.
- **Script:** đúng 4 ký tự chữ cái ASCII (ví dụ `Latn`, `Cyrl`).
- **Region:** 2 ký tự chữ cái ASCII hoặc 3 chữ số (ví dụ `VN`, `US`, `419`); region không bắt buộc là một quốc gia độc lập, vì còn có mã vùng UN M.49.
- **Variant, extension và thẻ lịch sử:** có quy tắc riêng theo BCP 47. Không thể kiểm tra đúng toàn bộ language tag bằng biểu thức chính quy đơn giản chỉ chấp nhận `xx-YY`.

Dấu `_` trong `en_US` thường xuất hiện ở dạng biểu diễn cũ của Java (ví dụ `Locale.toString()`); đầu vào chuẩn BCP 47 để dùng với `setLanguageTag` là `en-US`. Java chuẩn hóa kiểu chữ: language thành chữ thường, script có chữ đầu viết hoa, region thành chữ hoa. Vì vậy `vi-vn` được chuẩn hóa thành `vi-VN`; khác kiểu chữ **không** phải là mã không hợp lệ.

**Không nên đồng nhất khu vực với ngôn ngữ:** `en-VN` có thể biểu thị người dùng muốn tiếng Anh trong bối cảnh Việt Nam. Cũng không được suy ra locale từ quốc tịch, múi giờ hoặc đơn vị tiền tệ mà không có quy tắc nghiệp vụ.

## 3. Java kiểm tra được gì?

### 3.1. `Locale.Builder`: kiểm tra cấu trúc, không xác minh registry

`Locale.Builder` có các API thường dùng:

~~~java
Locale locale = new Locale.Builder()
        .setLanguage("sr")
        .setScript("Latn")
        .setRegion("RS")
        .build();

System.out.println(locale.toLanguageTag()); // sr-Latn-RS
~~~

Đoạn trên **chỉ minh họa** khi dùng trong một phương thức Java đã import `java.util.Locale`. Builder kiểm tra các trường và ném `IllformedLocaleException` khi cú pháp sai; nó **không** tra IANA để xác nhận một giá trị đã được đăng ký, không liên hệ mạng và không đảm bảo có bản dịch.

Để kiểm tra một chuỗi BCP 47 đầu vào, ưu tiên:

~~~java
Locale locale = new Locale.Builder()
        .setLanguageTag("vi-VN")
        .build();
~~~

Không cần tự tách từng phần nếu đầu vào là một language tag hoàn chỉnh. Dùng `getLanguage()`, `getScript()`, `getCountry()`, `toLanguageTag()` để truy cập kết quả đã chuẩn hóa.

### 3.2. `Locale.forLanguageTag`: giải mã dễ dãi, có thể làm mất lỗi

Khác với Builder, `Locale.forLanguageTag(text)` **bỏ subtag đầu tiên sai cú pháp và các subtag phía sau**, thay vì ném lỗi. Ví dụ:

~~~java
Locale lenient = Locale.forLanguageTag("en-US-@");
System.out.println(lenient.toLanguageTag()); // en-US
~~~

Do đó việc chỉ kiểm tra `Locale.forLanguageTag(input) != null` hoàn toàn **không có giá trị xác thực đầu vào**. Với dữ liệu do người dùng hoặc hệ thống bên ngoài gửi tới, việc âm thầm bỏ một phần mã có thể che lỗi cấu hình. Nếu mục tiêu là từ chối đầu vào sai cú pháp, dùng `new Locale.Builder().setLanguageTag(input).build()` và bắt `IllformedLocaleException`.

### 3.3. Constructor cũng không phải bộ xác minh

Các constructor Java 17 như `new Locale("en", "US")` tồn tại vì tương thích lịch sử; chúng không áp đặt cùng kiểm tra cú pháp như Builder. Không xem việc gọi constructor thành công là bằng chứng mã quốc gia/ngôn ngữ đã tồn tại.

### 3.4. Tạo được `Locale` không đồng nghĩa định dạng hay dịch thuật được hỗ trợ

`Locale.getAvailableLocales()` trả về hợp các locale được cài đặt bởi môi trường Java và các `LocaleServiceProvider`; nó không phải toàn bộ registry IANA và không phải danh sách locale mà ứng dụng cam kết hỗ trợ. Ngay cả khi một locale không có trong mảng này, một dịch vụ định dạng vẫn có thể thực hiện fallback hoặc sử dụng dữ liệu khác; ngược lại, có locale trong mảng cũng không chứng minh có resource bundle của ứng dụng.

Trong thiết kế thực tế hãy tách:
- **Cấu trúc:** Builder.
- **Mã đã đăng ký:** IANA Language Subtag Registry hoặc danh mục chuẩn cập nhật mà hệ thống chọn.
- **Dịch vụ và dữ liệu runtime:** từng API/provider/formatter cụ thể.
- **Ngôn ngữ sản phẩm:** danh sách locale được hỗ trợ và các bundle thực sự triển khai.

## 4. Ví dụ Java 17 hoàn chỉnh: ba kết quả xác thực khác nhau

Ví dụ dưới đây chạy độc lập, cho thấy `xx-YY` qua được bước cú pháp nhưng không nằm trong hai danh mục ISO 2 ký tự được truy vấn, và vẫn bị chính sách ứng dụng từ chối. Đặt mã trong file **`LocaleValidationDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.IllformedLocaleException;
import java.util.Locale;
import java.util.Set;

public class LocaleValidationDemo {
    private static final Set<String> SUPPORTED =
            Set.of("en-US", "vi-VN");

    // Bước 1: kiểm tra cấu trúc; bước 2: kiểm tra danh sách sản phẩm.
    static Locale requireSupportedLocale(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Missing locale");
        }

        final Locale parsed;
        try {
            parsed = new Locale.Builder()
                    .setLanguageTag(input)
                    .build();
        } catch (IllformedLocaleException e) {
            throw new IllegalArgumentException("Malformed locale tag", e);
        }

        // So sánh mã BCP 47 đã chuẩn hóa, không so sánh raw input.
        String canonical = parsed.toLanguageTag();
        if (!SUPPORTED.contains(canonical)) {
            throw new IllegalArgumentException("Unsupported locale: " + canonical);
        }
        return parsed;
    }

    public static void main(String[] args) {
        System.out.println("normalized: " +
                requireSupportedLocale("vi-vn").toLanguageTag());

        Locale syntacticallyValid = new Locale.Builder()
                .setLanguageTag("xx-YY").build();
        System.out.println("well-formed: " +
                syntacticallyValid.toLanguageTag());

        boolean isoLanguage = Arrays.asList(Locale.getISOLanguages())
                .contains("xx");
        boolean isoRegion = Arrays.asList(Locale.getISOCountries())
                .contains("YY");
        System.out.println("ISO language xx: " + isoLanguage);
        System.out.println("ISO region YY: " + isoRegion);

        System.out.println("lenient: " +
                Locale.forLanguageTag("en-US-@").toLanguageTag());

        try {
            new Locale.Builder().setLanguageTag("en-US-@").build();
            System.out.println("strict: accepted");
        } catch (IllformedLocaleException e) {
            System.out.println("strict: rejected");
        }

        try {
            requireSupportedLocale("xx-YY");
            System.out.println("application: accepted");
        } catch (IllegalArgumentException e) {
            System.out.println("application: rejected");
        }
    }
}
~~~

Biên dịch và chạy (Java 17 trở lên):

~~~bash
javac -encoding UTF-8 LocaleValidationDemo.java
java LocaleValidationDemo
~~~

Đầu ra:

~~~text
normalized: vi-VN
well-formed: xx-YY
ISO language xx: false
ISO region YY: false
lenient: en-US
strict: rejected
application: rejected
~~~

**Giải thích:**

- `vi-vn` hợp lệ về cấu trúc và được canonicalize thành `vi-VN`, nên vượt qua danh sách ứng dụng.
- `xx-YY` được Builder chấp nhận vì nó well-formed, dù `xx` không nằm trong danh mục mã ngôn ngữ ISO 639 hai chữ cái và `YY` không nằm trong danh mục mã quốc gia ISO 3166 hai chữ cái do Java trả về.
- `Locale.forLanguageTag("en-US-@")` âm thầm nhận phần `en-US`; Builder thì từ chối subtag `@`.
- Chính sách ứng dụng chỉ cho phép `en-US` và `vi-VN`, nên ngay cả locale **đúng cú pháp** như `xx-YY` vẫn bị từ chối.

Ở đây `SUPPORTED` là lựa chọn có chủ đích của **sản phẩm** để minh họa. Không suy ra danh sách được hỗ trợ từ `Locale.getAvailableLocales()` và cũng không dùng `ISO` để thay thế chính sách này.

## 5. Mã ISO và IANA: phạm vi khác nhau

Các API hữu ích trong Java 17:

| API | Kiểm tra/dữ liệu có thể sử dụng | Hạn chế |
| --- | --- | --- |
| `Locale.getISOLanguages()` | Mảng các mã ngôn ngữ **hai chữ cái** theo ISO 639 | Không chứa tất cả language subtag hợp lệ: nhiều ngôn ngữ dùng ba ký tự hoặc hình thức khác; có cả mã cũ và mới ở một số trường hợp |
| `Locale.getISOCountries()` | Mảng mã quốc gia **hai chữ cái** theo ISO 3166 | Không chứa các mã vùng số UN M.49 và không đại diện đầy đủ cho mọi region subtag BCP 47 |
| `Locale.getISOCountries(Locale.IsoCountryCode.PART1_ALPHA2)` | Tập mã quốc gia ISO 3166-1 alpha-2 | Cũng không phải danh sách mọi mã vùng có thể xuất hiện trong language tag |
| `Locale.getAvailableLocales()` | Danh sách locale mà runtime/provider thông báo đang cài đặt | Không phải bộ chuẩn ISO/IANA, không phải lời hứa ứng dụng đã dịch |
| `Locale.Builder.setLanguageTag(...)` | Phân tích và ràng buộc **cú pháp** BCP 47 | Không tự kiểm tra subtag đã đăng ký |

Nếu nghiệp vụ cần xác nhận **mã ngôn ngữ hoặc khu vực có thật**, cần xác định chuẩn chính xác:

- Đối với **language tag BCP 47**, dùng **IANA Language Subtag Registry**, lưu ý loại `language`, `extlang`, `script`, `region`, `variant`, các tag lịch sử và trường deprecation/preferred-value. Chuẩn không chỉ là hai mảng ISO.
- Đối với hệ thống chỉ nhận **mã ngôn ngữ ISO 639-1 hai chữ cái**, có thể kiểm tra chính danh mục đó, nhưng phải công bố rõ giới hạn để không loại nhầm những tag BCP 47 hợp lệ.
- Đối với hệ thống chỉ nhận **quốc gia ISO 3166-1 alpha-2**, dùng danh mục quốc gia; đừng hiểu `419` (mã khu vực số) là sai cú pháp BCP 47 chỉ vì không có trong `getISOCountries()`.
- Có thể tồn tại mã cũ, thay đổi tên hoặc quy định thay thế. Cần xác định chính sách đối với mã deprecated, tên thay thế và phiên bản dữ liệu registry; không giả định dữ liệu được đóng băng vĩnh viễn.

Không đủ để chỉ dùng regex, ví dụ `[a-z]{2}-[A-Z]{2}` rồi kết luận "mã hợp lệ": regex đó vừa chấp nhận `xx-YY` không đăng ký, vừa loại `zh-Hant-TW` hoặc `en` vốn là các tag có cấu trúc hợp lệ.

**Chú ý kỹ thuật:** `Locale.getISO3Language()`/`getISO3Country()` chuyển đổi dạng mã ở một số trường hợp và có thể ném `MissingResourceException`; chúng không phải dịch vụ kiểm định mọi subtag hoặc toàn bộ thẻ BCP 47.

## 6. Chuẩn hóa, kiểm tra registry và chính sách ứng dụng nên diễn ra theo thứ tự

Một pipeline đầu vào đáng tin cậy:

~~~text
Chuỗi đầu vào (cấu hình / người dùng / request)
       |
       v
Kiểm tra null / trống / giới hạn độ dài / kiểu dữ liệu
       |
       v
Phân tích nghiêm ngặt bằng Locale.Builder.setLanguageTag
       |-- sai cú pháp --> từ chối hoặc trả lỗi giải thích được
       v
Locale đã chuẩn hóa: toLanguageTag()
       |
       +--> [Khi nghiệp vụ đòi hỏi] kiểm tra IANA / ISO
       |       và chính sách mã cũ, script, vùng địa lý
       |
       v
Đối chiếu danh sách locale sản phẩm hỗ trợ
       |-- không hỗ trợ --> từ chối hoặc chọn fallback công khai
       v
Chọn resource bundle, formatter, locale cho từng request
       |
       v
Đầu ra bản địa hóa / dữ liệu cấu trúc
~~~

Nếu đầu vào đến từ client và không nằm trong các locale được hỗ trợ, có hai chính sách hợp lý tùy hợp đồng sản phẩm:

1. **Từ chối rõ ràng** với API/configuration yêu cầu locale chính xác: lỗi `invalid_locale` khi sai cú pháp, lỗi `unsupported_locale` khi cú pháp đúng nhưng sản phẩm không hỗ trợ.
2. **Thương lượng fallback** với nhu cầu hiển thị: ví dụ đề nghị `vi-VN` nhưng UI chỉ có `vi`, dùng thứ tự ưu tiên đã công bố. Đây là chức năng của adapter/presenter, phải quan sát và kiểm thử, không thay dữ liệu kinh doanh.

Không dùng `Locale.setDefault(...)` như cách xác thực hoặc chuyển locale theo từng request: đó là trạng thái mặc định của JVM và có thể ảnh hưởng request khác trong ứng dụng đa luồng. Truyền `Locale` đã chọn trực tiếp tới lớp định dạng hoặc lấy từ request context được quản lý an toàn.

## 7. Thế nào là "hỗ trợ" một locale?

Để kiểm tra sản phẩm thực sự hỗ trợ, hãy kiểm tra đúng thành phần đang dùng:

- **Bản dịch ứng dụng:** có `ResourceBundle` hoặc danh mục thông điệp cho locale cần thiết không? Có đủ khóa không? `ResourceBundle.getBundle` có thể fallback; việc gọi thành công **không chứng minh** bản dịch mong muốn tồn tại.
- **Số, tiền, ngày giờ:** `NumberFormat`, `DateTimeFormatter` và các provider có dữ liệu locale cần thiết không? Nếu thiếu dữ liệu đặc thù có thể xảy ra fallback.
- **Ngữ cảnh khu vực:** locale không xác định múi giờ, không tự cung cấp tỷ giá hoặc quy tắc thuế. `ZoneId` và `Currency` là những thông tin riêng.
- **Ngôn ngữ chính sách sản phẩm:** có phục vụ mọi region/script của một ngôn ngữ hay chỉ một số biến thể? Có chấp nhận `en` rồi chọn `en-US` hoặc `en-GB` hay yêu cầu exact match?
- **Hiển thị cuối:** người dùng có thật sự thấy bản dịch và định dạng phù hợp, hay đang xem toàn bộ nhãn fallback tiếng Anh?

Ví dụ: ứng dụng có `messages_en.properties` nhưng không có `messages_en_AU.properties`. Yêu cầu `en-AU` có thể được `ResourceBundle` giải quyết bằng fallback; quyết định có gắn nhãn sản phẩm là “hỗ trợ tiếng Anh (Úc)” hay không thuộc chính sách chất lượng bản dịch, không phải kết quả của Builder.

## 8. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `new Locale.Builder().setLanguage("zz")` chạy được nên `zz` là ngôn ngữ được công nhận | Builder kiểm tra hình dạng, không tra registry | Nếu cần, kiểm tra registry/nghiệp vụ riêng |
| `Locale.forLanguageTag(value)` không ném lỗi nên input chắc chắn hợp lệ | API này bỏ qua subtag sai và phần phía sau | Dùng Builder nghiêm ngặt cho input phải xác thực |
| `getISOLanguages()` không có mã ba chữ cái nên mã sai | API chỉ liệt kê mã hai chữ cái | Dùng chuẩn bao phủ loại mã cần chấp nhận |
| `getISOCountries()` không có `419` nên thẻ sai | UN M.49 region numeric không thuộc mảng alpha-2 | Xem xét đúng BCP 47 / UN M.49 |
| Locale nằm trong `getAvailableLocales()` nghĩa là ứng dụng có bản dịch | Mảng phản ánh runtime và provider, không phải bundle của sản phẩm | Kiểm thử bundle, nhãn UI, fallback |
| Dùng `Locale.toString()` làm chuẩn input BCP 47 | Ký hiệu `_` có thể không phải language tag | Dùng `toLanguageTag()` |
| Dùng mã locale để suy ra múi giờ hoặc tiền tệ | Một ngôn ngữ có nhiều vùng và tùy chọn người dùng | Truyền `ZoneId` / `Currency` độc lập |
| Tự thay `_` bằng `-` và tin rằng mọi chuỗi đều chuẩn | Legacy variant và extensions có nhiều quy tắc | Cần chính sách migration rõ ràng, kiểm tra lại bằng Builder |
| So sánh raw input với `"vi-VN"` | `vi-vn` khác cách viết nhưng hợp lệ | So sánh thẻ đã chuẩn hóa |

Không chỉ kiểm tra xem `getDisplayLanguage()` có trả về một tên đọc được: chuỗi hiển thị có thể fallback thành mã hoặc tên từ dữ liệu runtime và không phải bằng chứng registry hợp lệ.

## 9. Bộ tình huống kiểm thử nên có

- **Cú pháp hợp lệ, mã quen thuộc:** `vi-VN`, `en-US`, `sr-Latn-RS`; xác nhận thành phần được đọc đúng.
- **Cú pháp hợp lệ nhưng mã không được đăng ký:** `xx-YY`; Builder cho qua nhưng bước registry (nếu bắt buộc) hoặc allowlist sản phẩm có thể loại.
- **Cú pháp sai:** `en-US-@`, `en_ US` hoặc thẻ chứa ký tự bất thường; Builder phải từ chối.
- **Khác kiểu chữ:** `vi-vn` trở thành `vi-VN`; không báo sai chỉ vì khác hoa/thường.
- **Thẻ chỉ có ngôn ngữ:** `en`, `vi`; quyết định hỗ trợ theo chính sách, không mặc định thêm `US`/`VN`.
- **Thẻ có script/region/extension:** `zh-Hant-TW`, `en-US-u-nu-latn`; không dùng regex chỉ hai thành phần.
- **Rỗng, null, quá dài hoặc ngoài allowlist:** đưa ra lỗi rõ ràng, không chấp nhận chỉ vì kết quả parse có thể tạo `Locale.ROOT`.
- **Thiếu bản dịch hoặc thiếu khóa:** xác nhận hành vi fallback, log/metric hoặc lỗi theo yêu cầu sản phẩm.

Cần phân biệt test **cú pháp** (dựa trên hợp đồng API Builder), test **danh mục mã** (dựa trên snapshot/version của registry), và test **hỗ trợ sản phẩm** (dựa trên resource và cấu hình đang triển khai). Nếu kiểm thử đầu ra đã được format, dữ liệu locale của JDK/CLDR có thể khác giữa các bản Java: tập trung vào hành vi mong muốn hoặc ghim phiên bản provider khi so sánh nguyên văn.

## 10. Ghi nhớ để áp dụng

**Không có một hàm Java duy nhất tự động đảm bảo cả cú pháp, sự tồn tại của mã và hỗ trợ trong sản phẩm.**

- Dùng `Locale.Builder.setLanguageTag` khi cần **kiểm tra cấu trúc nghiêm ngặt** của language tag.
- Dùng **registry/chính sách tiêu chuẩn phù hợp** nếu bài toán bắt buộc xác nhận subtag ngôn ngữ/khu vực đã được ghi nhận.
- Dùng **allowlist cùng kiểm thử resource/formatter** để khẳng định giao diện hay dịch vụ **thật sự hỗ trợ** locale đó.
- Chọn hành vi từ chối/fallback có chủ đích và giữ giá trị nghiệp vụ độc lập với văn bản bản địa hóa.

**Tài liệu tham khảo:**

- Java SE 17, `java.util.Locale`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html
- Java SE 17, `Locale.Builder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html
- IANA Language Subtag Registry: https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry
- IETF BCP 47 (RFC 5646): https://www.rfc-editor.org/rfc/rfc5646
