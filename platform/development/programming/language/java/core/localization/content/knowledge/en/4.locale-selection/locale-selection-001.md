# Danh sách locale được ứng dụng hỗ trợ

Một ứng dụng đa ngôn ngữ cần công bố rõ **những locale mà chính ứng dụng hỗ trợ**. Danh sách này khác với danh sách locale mà Java/JDK có thể xử lý. Ví dụ, JDK có thể định dạng số theo `fr-FR`, nhưng nếu sản phẩm chưa dịch màn hình và thông báo sang tiếng Pháp thì không nên tự động đưa `fr-FR` vào bộ lựa chọn ngôn ngữ của ứng dụng.

Trong ngữ cảnh **chọn locale**, “được hỗ trợ” là một **cam kết của sản phẩm**: ứng dụng biết cách phục vụ người dùng bằng ngôn ngữ, quy ước hiển thị và tài nguyên tương ứng ở mức đã định nghĩa. `java.util.Locale` chỉ mô tả ngôn ngữ/vùng; đối tượng đó không tự chứng minh mức độ hoàn thiện của ứng dụng.

## 1. Ba khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ai quyết định? |
| --- | --- | --- |
| Locale có thể biểu diễn | Mã ngôn ngữ/vùng hợp lệ được mô tả bằng `Locale`, ví dụ `vi-VN`, `en-US` hoặc `zh-Hant-TW` | Cú pháp language tag và API `Locale` |
| Locale mà JDK/provider có dữ liệu | Locale có dữ liệu định dạng cho những dịch vụ mà runtime hỗ trợ; ví dụ số, ngày, tên tháng hoặc ký hiệu | JDK, các locale service provider và dữ liệu CLDR/khác |
| **Locale ứng dụng hỗ trợ** | Tập locale sản phẩm đã chọn phát hành, có quy tắc chọn/fallback, bản dịch và kiểm thử phù hợp | **Chính ứng dụng/đội phát triển** |

Ví dụ: một website chỉ phát hành giao diện tiếng Việt và tiếng Anh Mỹ có thể khai báo `vi-VN` và `en-US` là hai locale được hỗ trợ, dù `Locale.getAvailableLocales()` trả về nhiều locale khác. Việc runtime biết định dạng ngày Pháp **không tạo ra bản dịch** “Đăng nhập”, thông báo lỗi hoặc email bằng tiếng Pháp cho website.

Một sản phẩm có thể định nghĩa rõ những mức độ hỗ trợ khác nhau, chẳng hạn hỗ trợ đầy đủ giao diện và định dạng, hoặc chỉ hỗ trợ định dạng. Khi nói “danh sách locale được hỗ trợ” cho bộ chọn ngôn ngữ, cần chọn một **hợp đồng nhất quán**, tránh đưa vào danh sách những locale chỉ có một phần tính năng mà không thông báo cho người dùng.

## 2. `Locale.getAvailableLocales()` không phải danh sách lựa chọn của ứng dụng

Java cung cấp:

~~~java
Locale[] runtimeLocales = Locale.getAvailableLocales();
~~~

Phương thức trên trả về các locale mà môi trường chạy có dữ liệu cho **các dịch vụ phụ thuộc locale của Java**. Kết quả phụ thuộc phiên bản JDK và cấu hình locale provider; nó không phải danh mục “ngôn ngữ đã dịch” của ứng dụng.

Những API chuyên biệt, ví dụ `NumberFormat.getAvailableLocales()` hoặc `DateFormat.getAvailableLocales()`, cho biết phạm vi locale được các dịch vụ đó hỗ trợ. Chúng cũng **không chứng minh** rằng mọi màn hình hay nội dung nghiệp vụ của ứng dụng đã có bản dịch.

Hãy tránh cách xây menu sau:

~~~java
// KHÔNG dùng làm nguồn duy nhất cho menu ngôn ngữ của sản phẩm.
Locale[] choices = Locale.getAvailableLocales();
~~~

Nếu làm vậy, người dùng có thể chọn một locale mà phần định dạng số hoạt động nhưng giao diện lại chuyển sang ngôn ngữ mặc định vì không có bản dịch. Danh sách còn có thể thay đổi khi nâng cấp runtime, trong khi cam kết hỗ trợ sản phẩm chưa thay đổi.

**Nguyên tắc:** runtime có thể hỗ trợ **nhiều hơn** ứng dụng; ứng dụng cũng cần tự kiểm soát các locale mà mình công bố, kể cả khi một số định dạng được xử lý bởi thư viện khác JDK.

## 3. Khai báo danh sách hỗ trợ tường minh

Với một hệ thống nhỏ, có thể cấu hình locale được hỗ trợ ngay trong mã hoặc đọc từ cấu hình triển khai. Hãy dùng mã **BCP 47 language tag** làm định danh ổn định, ví dụ `vi-VN`, `en-US` và `en-GB`. Không dùng tên hiển thị như “English”, “Tiếng Việt” làm khóa: tên hiển thị có thể được dịch hoặc thay đổi theo locale.

Tạo tệp `SupportedLocalesDemo.java`:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class SupportedLocalesDemo {
    private static final Locale DEFAULT_LOCALE =
            Locale.forLanguageTag("vi-VN");

    private static final List<Locale> SUPPORTED_LOCALES = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("en-GB")
    );

    private static final Set<Locale> SUPPORTED_LOOKUP =
            Set.copyOf(SUPPORTED_LOCALES);

    public static void main(String[] args) {
        System.out.println("Supported locales:");
        for (Locale locale : SUPPORTED_LOCALES) {
            System.out.println("- " + locale.toLanguageTag());
        }

        System.out.println("Default: " + DEFAULT_LOCALE.toLanguageTag());
        System.out.println("fr-FR supported: " +
                SUPPORTED_LOOKUP.contains(Locale.forLanguageTag("fr-FR")));
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac SupportedLocalesDemo.java
java SupportedLocalesDemo
~~~

Kết quả chính xác:

~~~text
Supported locales:
- vi-VN
- en-US
- en-GB
Default: vi-VN
fr-FR supported: false
~~~

Ở đây, `List` giữ **thứ tự hiển thị** trong menu, còn `Set` hỗ trợ tra cứu thành viên. Không duyệt `Set.copyOf(...)` để mong có thứ tự ổn định; thứ tự duyệt của set này không được bảo đảm. `DEFAULT_LOCALE` phải nằm trong danh sách hỗ trợ, và có thể kiểm tra điều đó khi khởi động ứng dụng.

Danh sách có thể nằm trong cấu hình thay vì mã nguồn, chẳng hạn:

~~~yaml
# Ví dụ cấu hình của ứng dụng; không phải cú pháp cấu hình tự động của JDK.
localization:
  default-locale: vi-VN
  supported-locales:
    - vi-VN
    - en-US
    - en-GB
~~~

Ứng dụng phải tự đọc, kiểm tra và chuyển các chuỗi này thành `Locale`. Java không tự phát hiện danh sách sản phẩm hỗ trợ chỉ từ khóa `supported-locales` trong YAML. Khi triển khai, nên xác minh không có locale trùng nhau sau chuẩn hóa, mọi locale có dữ liệu cần thiết và locale mặc định là một phần của tập hỗ trợ.

### Vì sao vừa dùng `List` vừa dùng `Set`?

- `List<Locale>`: dùng khi cần thứ tự cụ thể (ví dụ tiếng Việt trước, tiếng Anh Mỹ sau).
- `Set<Locale>`: dùng khi kiểm tra liệu một lựa chọn chính xác có thuộc danh sách.
- `Map<String, Locale>`: hữu ích nếu dữ liệu đến từ language tag trong cấu hình/API; khóa có thể dùng dạng chuẩn hóa từ `toLanguageTag()`.

Nếu menu cần tên hiển thị, có thể dùng `locale.getDisplayName(displayLocale)`, nhưng đây là tên do dữ liệu runtime cung cấp. Để đạt văn phong sản phẩm nhất quán, ứng dụng vẫn có thể khai báo nhãn do mình biên tập như “Tiếng Việt” hoặc “English (US)”. Không dùng nhãn làm định danh hoặc thay thế language tag.

## 4. Kiểm tra một locale do người dùng chọn

Ứng dụng thường nhận locale từ hồ sơ người dùng, URL, cookie, truy vấn hoặc bộ chọn trên giao diện. Không nên chuyển thẳng mọi chuỗi nhận được thành “được hỗ trợ”.

Hai vấn đề phải được tách ra:

1. **Cú pháp:** đầu vào có phải language tag phù hợp không?
2. **Chính sách:** locale hợp lệ đó có nằm trong danh sách mà ứng dụng công bố không?

`Locale.forLanguageTag(...)` có cách xử lý khoan dung với một số đầu vào sai định dạng: nó có thể bỏ qua phần không hợp lệ thay vì luôn báo lỗi. Khi cần kiểm tra nghiêm ngặt, dùng `Locale.Builder.setLanguageTag(...)` và bắt `IllformedLocaleException`.

Tạo `LocaleSelectionDemo.java`:

~~~java
import java.util.IllformedLocaleException;
import java.util.List;
import java.util.Locale;

public class LocaleSelectionDemo {
    private static final Locale DEFAULT_LOCALE =
            Locale.forLanguageTag("vi-VN");

    private static final List<Locale> SUPPORTED = List.of(
            DEFAULT_LOCALE,
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("en-GB")
    );

    static Locale selectExact(String languageTag) {
        if (languageTag == null || languageTag.isBlank()) {
            return DEFAULT_LOCALE;
        }

        try {
            Locale candidate = new Locale.Builder()
                    .setLanguageTag(languageTag.trim())
                    .build();

            return SUPPORTED.contains(candidate)
                    ? candidate
                    : DEFAULT_LOCALE;
        } catch (IllformedLocaleException e) {
            return DEFAULT_LOCALE;
        }
    }

    public static void main(String[] args) {
        System.out.println(selectExact("en-US").toLanguageTag());
        System.out.println(selectExact("fr-FR").toLanguageTag());
        System.out.println(selectExact("en_US").toLanguageTag());
    }
}
~~~

~~~bash
javac LocaleSelectionDemo.java
java LocaleSelectionDemo
~~~

Kết quả chính xác:

~~~text
en-US
vi-VN
vi-VN
~~~

- `en-US` hợp lệ và được công bố hỗ trợ nên được giữ nguyên.
- `fr-FR` là locale có thể biểu diễn nhưng chưa được sản phẩm hỗ trợ; chính sách ví dụ chọn `vi-VN`.
- `en_US` dùng dấu gạch dưới không đúng dạng BCP 47 mà ví dụ chấp nhận; builder báo lỗi và ứng dụng fallback.

Đây là **chính sách khớp chính xác (exact match)**. Nó phù hợp với lựa chọn cụ thể trong menu. Nó chưa làm thương lượng ngôn ngữ nâng cao và không tự xem `en`, `en-US`, `en-GB` là một lựa chọn tương đương.

Để API phân biệt rõ “đầu vào sai” với “locale hợp lệ nhưng chưa được hỗ trợ”, trong ứng dụng thực tế có thể trả về một kiểu kết quả có trạng thái hoặc lỗi xác thực riêng, thay vì luôn âm thầm fallback. Lựa chọn này phụ thuộc hợp đồng API và trải nghiệm người dùng.

## 5. Chuẩn hóa tag, vùng, script và extensions

`Locale` bao gồm ngôn ngữ, vùng, script, variant và Unicode extensions. Một vài ví dụ:

| Tag | Ý nghĩa |
| --- | --- |
| `en` | Tiếng Anh, chưa chỉ định vùng |
| `en-US` | Tiếng Anh trong ngữ cảnh Mỹ |
| `en-GB` | Tiếng Anh trong ngữ cảnh Anh |
| `zh-Hans-CN` | Tiếng Trung, chữ giản thể, vùng Trung Quốc |
| `zh-Hant-TW` | Tiếng Trung, chữ phồn thể, vùng Đài Loan |
| `sr-Latn-RS` | Tiếng Serbia, chữ Latin, vùng Serbia |
| `en-US-u-nu-arab` | Tiếng Anh/Mỹ kèm extension đề nghị hệ chữ số Ả Rập |

**Cần tránh hai cực đoan:** đòi mọi request giống hệt tag cấu hình trong mọi trường hợp, hoặc tự động gộp mọi tag có cùng ngôn ngữ. Đối với một ứng dụng cần phân biệt `zh-Hans` và `zh-Hant`, bỏ script có thể chọn sai hệ chữ. Đối với tiếng Anh, người dùng có thể kỳ vọng mẫu ngày khác giữa `en-GB` và `en-US`.

`Locale.equals(...)` so sánh cả các thành phần liên quan, bao gồm extensions. Vì vậy `en-US-u-nu-arab` không nhất thiết là phần tử bằng `en-US` trong `Set<Locale>`. Nếu sản phẩm muốn cho phép “ngôn ngữ giao diện en-US nhưng bộ chữ số khác”, nên tách **locale nội dung được hỗ trợ** khỏi **tùy chọn định dạng**, kiểm tra extension được phép và cấu hình formatter riêng. Không tự bỏ mọi extension hoặc tự nhận hỗ trợ mọi tùy chọn.

Lưu tag theo dạng chuẩn do `toLanguageTag()` tạo ra; sử dụng `Locale.Builder` để kiểm tra cú pháp đầu vào có yêu cầu chặt chẽ. Nếu cần giới hạn đúng danh sách công bố, hãy so với tập tag/`Locale` đã được chuẩn hóa, không so trực tiếp với tên hiển thị.

## 6. Chọn locale từ HTTP `Accept-Language`

Trình duyệt có thể gửi header như:

~~~http
Accept-Language: fr-CA, en-GB;q=0.9, en-US;q=0.8
~~~

Đây là **danh sách ưu tiên** có trọng số `q` (mặc định là `1.0`), không phải một locale duy nhất. Java cung cấp `Locale.LanguageRange.parse(...)` và `Locale.lookup(...)` dựa trên cơ chế language range/lookup của RFC 4647 để chọn ứng viên phù hợp trong tập hỗ trợ.

Tạo `LocaleNegotiationDemo.java`:

~~~java
import java.util.List;
import java.util.Locale;

public class LocaleNegotiationDemo {
    private static final Locale DEFAULT_LOCALE =
            Locale.forLanguageTag("vi-VN");

    private static final List<Locale> SUPPORTED = List.of(
            DEFAULT_LOCALE,
            Locale.forLanguageTag("en-US"),
            Locale.forLanguageTag("en-GB")
    );

    static Locale negotiate(String header) {
        if (header == null || header.isBlank()) {
            return DEFAULT_LOCALE;
        }

        try {
            List<Locale.LanguageRange> preferences =
                    Locale.LanguageRange.parse(header);

            Locale match = Locale.lookup(preferences, SUPPORTED);
            return match != null ? match : DEFAULT_LOCALE;
        } catch (IllegalArgumentException e) {
            return DEFAULT_LOCALE;
        }
    }

    public static void main(String[] args) {
        System.out.println(negotiate(
                "fr-CA, en-GB;q=0.9, en-US;q=0.8").toLanguageTag());
        System.out.println(negotiate(
                "fr-CA, fr;q=0.9").toLanguageTag());
    }
}
~~~

~~~bash
javac LocaleNegotiationDemo.java
java LocaleNegotiationDemo
~~~

Kết quả chính xác:

~~~text
en-GB
vi-VN
~~~

Trong request đầu, `fr-CA` có mức ưu tiên cao nhất nhưng không có trong tập hỗ trợ; `en-GB` là lựa chọn tiếp theo phù hợp. Trong request thứ hai không có ứng viên phù hợp, `Locale.lookup(...)` trả về `null` và ứng dụng áp dụng `DEFAULT_LOCALE`.

### `lookup` không phải phép chọn locale “gần nhất” bất kỳ

Cơ chế lookup tìm theo dải ngôn ngữ và quy tắc thu hẹp language range của RFC 4647. Đừng mặc định rằng khi chỉ hỗ trợ `en-GB` thì request `en-US` chắc chắn sẽ tự được đổi thành `en-GB`. Nếu sản phẩm muốn fallback rõ ràng theo cùng ngôn ngữ, cần thiết kế chính sách và kiểm thử cụ thể.

Java còn có `Locale.filter(...)` để lấy **nhiều** locale phù hợp với language ranges. Khi ứng dụng cần **một** locale cho request, `lookup` thường gần mục đích hơn. Sự khác nhau giữa lọc danh sách và chọn một mục là một quyết định sản phẩm, không phải hai tên khác nhau cho cùng thao tác.

Header là dữ liệu do client cung cấp; hệ thống production nên giới hạn độ dài, số mục và xử lý trường hợp malformed. Đoạn mẫu tập trung minh họa API lookup, chưa triển khai các giới hạn đầu vào hay chính sách bảo vệ tài nguyên đó.

## 7. Chính sách thứ tự ưu tiên và fallback của ứng dụng

Một chính sách lựa chọn thực tế có thể được mô tả như sau:

1. **Lựa chọn tường minh hiện tại** của người dùng, nếu hợp lệ và thuộc tập hỗ trợ.
2. **Ngôn ngữ đã lưu trong hồ sơ**, nếu người dùng đã đăng nhập và vẫn được hỗ trợ.
3. **Thương lượng từ `Accept-Language`** khi chưa có lựa chọn rõ ràng.
4. **Locale mặc định của ứng dụng** đã khai báo, ví dụ `vi-VN`.

Thứ tự này chỉ là một ví dụ: ứng dụng có thể chọn thứ tự khác tùy hợp đồng sản phẩm, nhưng cần nhất quán. Đừng dùng `Locale.getDefault()` của JVM như lựa chọn ngôn ngữ cho mọi khách truy cập trên một server dùng chung; JVM default phản ánh môi trường chạy và có thể thay đổi, không nhất thiết phản ánh sở thích của từng người dùng.

Một sơ đồ logic phù hợp:

~~~text
Request / cấu hình người dùng
    |
    +-- Có lựa chọn tường minh hợp lệ, được hỗ trợ? --> Dùng lựa chọn đó
    |
    +-- Có lựa chọn đã lưu, được hỗ trợ? ------------> Dùng lựa chọn đã lưu
    |
    +-- Accept-Language có ứng viên phù hợp? --------> Dùng locale được lookup
    |
    +-- Không ---------------------------------------> Locale mặc định sản phẩm
    |
    v
Dùng locale đã chọn để lấy bản dịch và định dạng đầu ra
~~~

**Không đồng nhất fallback** của ứng dụng với fallback nội bộ của `ResourceBundle` hay locale provider của formatter. Nếu không kiểm soát, màn hình có thể hiển thị bản dịch ở một ngôn ngữ nhưng định dạng ngày ở một locale khác. Hãy quyết định locale hiệu lực tại một lớp chính sách rõ ràng và truyền nó qua các thành phần liên quan.

Ví dụ cần fallback đặc biệt `fr-CA → fr-FR` nếu thiếu bản dịch Canada? Hãy khai báo một quy tắc có chủ ý, đánh giá ảnh hưởng tới ngôn ngữ, ngày tháng và tiền tệ. Không nên suy ra từ chữ `fr` rằng mọi quy ước vùng của Pháp đều phù hợp với Canada. Có thể dùng **locale giao diện** riêng cho ngôn ngữ bản dịch và **locale định dạng** riêng theo vùng/sở thích người dùng khi sản phẩm cần phân biệt.

## 8. Danh sách hỗ trợ và `ResourceBundle`: kiểm chứng bản dịch

Nếu sản phẩm công bố `vi-VN`, `en-US`, `en-GB`, các bundle có thể được tổ chức như sau:

~~~text
src/main/resources/
  Messages.properties
  Messages_vi.properties
  Messages_en.properties
  Messages_en_GB.properties
~~~

Tên bundle này là **ví dụ tổ chức tài nguyên**, không có nghĩa mọi tổ hợp tag đều cần một file trùng chính xác. `ResourceBundle` tìm ứng viên dựa trên locale và có cơ chế fallback. Chẳng hạn yêu cầu `en-GB` có thể lấy khóa từ `Messages_en_GB.properties`, từ `Messages_en.properties`, hoặc bundle gốc nếu không có bản dịch đặc thù cho vùng.

Điều này tiện cho tái sử dụng bản dịch, nhưng cũng có thể **che giấu thiếu sót**. Nếu `Messages_en_GB.properties` có ít khóa, ứng dụng vẫn có thể trả ra chuỗi từ bundle cấp cao hơn. Nếu sản phẩm yêu cầu mọi nội dung tiếng Anh Anh được rà soát, việc `ResourceBundle.getBundle(...)` trả về thành công chưa đủ chứng minh chất lượng.

Khi kiểm tra sẵn sàng phát hành từng locale, nên có tiêu chí rõ:

- Các thông điệp giao diện, lỗi, biểu mẫu, email và luồng quan trọng đã có bản dịch hoặc fallback được duyệt.
- Các khóa thông điệp, placeholders (ví dụ `{0}`), biểu thức số nhiều/giới tính nếu có được kiểm tra phù hợp với cơ chế i18n đang dùng.
- Định dạng ngày, số, tiền, tên riêng và nội dung nghiệp vụ hiển thị đúng ngữ cảnh người dùng.
- Giao diện đáp ứng độ dài chuỗi khác nhau; có kiểm thử bố cục khi ngôn ngữ thay đổi.
- Bộ chọn ngôn ngữ và URL/route lưu lựa chọn theo tag ổn định.
- Nếu một bản dịch chưa sẵn sàng, locale đó không được công bố như hỗ trợ đầy đủ.

**Lưu ý:** `Locale`, `ResourceBundle` và `NumberFormat` giải quyết các nhu cầu khác nhau. Có bản dịch giao diện không đồng nghĩa mọi loại tiền hay cách diễn đạt nghiệp vụ đều tự được xử lý; ngược lại, có định dạng số theo locale không đồng nghĩa có bản dịch giao diện.

## 9. Duy trì danh sách hỗ trợ trong hệ thống thực tế

### Dữ liệu cấu hình và giao diện API

Nếu frontend và backend cùng tham gia chọn locale, nên có một nguồn cấu hình sản phẩm rõ ràng: chẳng hạn endpoint công bố danh sách locale hỗ trợ, locale mặc định, nhãn hiển thị và trạng thái hỗ trợ. Có thể biểu diễn dưới dạng dữ liệu:

~~~json
{
  "defaultLocale": "vi-VN",
  "supportedLocales": [
    {"tag": "vi-VN", "label": "Tiếng Việt"},
    {"tag": "en-US", "label": "English (US)"},
    {"tag": "en-GB", "label": "English (UK)"}
  ]
}
~~~

Đây là **ví dụ thiết kế API**, không phải định dạng trả về có sẵn của JDK. Nếu dùng danh sách từ cấu hình, cả backend và frontend nên áp dụng cùng chính sách về locale hiệu lực để tránh giao diện chọn một giá trị nhưng server lại dùng giá trị khác.

Với ứng dụng web lưu bản dịch hoặc kết quả HTML vào cache, locale hiệu lực thường phải là một phần khóa cache; nếu cache công khai thay đổi nội dung theo `Accept-Language`, cần xem xét header `Vary: Accept-Language` theo thiết kế HTTP của dịch vụ. Lựa chọn ngôn ngữ của người dùng qua cookie/hồ sơ có thể cần chiến lược cache riêng để tránh phục vụ nhầm nội dung giữa người dùng.

### Kiểm thử danh sách và lựa chọn

Một ma trận kiểm thử tối thiểu cho ví dụ hỗ trợ `vi-VN`, `en-US`, `en-GB`:

| Tình huống | Kết quả kỳ vọng |
| --- | --- |
| Chọn chính xác `en-US` | Giữ `en-US` |
| Chọn chính xác `en-GB` | Giữ `en-GB` |
| Chọn `fr-FR` nhưng không hỗ trợ | Fallback hoặc lỗi xác thực theo hợp đồng, không âm thầm công bố là hỗ trợ |
| Tag sai định dạng `en_US` | Xử lý như đầu vào không hợp lệ |
| Không có lựa chọn và không có header | Dùng `vi-VN` mặc định |
| Header `fr-CA, en-GB;q=0.9` | Với tập ví dụ, lookup chọn `en-GB` |
| Header chỉ có ngôn ngữ không hỗ trợ | Dùng chính sách fallback |
| Đổi phiên bản JDK | Danh sách sản phẩm không tự mở rộng theo runtime |
| Tài nguyên một locale bị thiếu khóa | Kiểm thử phát hiện hoặc fallback đã được phê duyệt |

Có thể thêm kiểm thử để chắc chắn các locale không trùng nhau sau chuẩn hóa, locale mặc định luôn thuộc danh sách hỗ trợ, tất cả tag hợp lệ theo BCP 47 và các trang quan trọng có bản dịch thích hợp.

### Thay đổi danh sách theo thời gian

Khi bổ sung locale mới, cần phát hành bản dịch và kiểm thử trước khi bật tùy chọn trên UI; khi gỡ locale, cần xử lý những hồ sơ người dùng trước đây đã lưu tag đó. Hãy chọn fallback có chủ đích, giải thích trong UX nếu cần, thay vì để ứng dụng ngẫu nhiên hiển thị bản dịch theo JVM default.

Nếu hỗ trợ ngôn ngữ ở một mức độ giới hạn (beta, chỉ một khu vực, chỉ trang đọc), nên biểu diễn rõ phạm vi công bố để danh sách hỗ trợ không hứa vượt khả năng thực tế.

## 10. Lỗi thường gặp

1. **Đưa toàn bộ `Locale.getAvailableLocales()` vào menu.** Dữ liệu runtime không chứng minh ứng dụng có bản dịch và kiểm thử tương ứng.
2. **Đếm số bundle và coi đó là số locale hỗ trợ.** Một bundle cấp ngôn ngữ có thể phục vụ nhiều tag vùng; một số bundle lại mới được dịch một phần.
3. **So sánh trực tiếp chuỗi đầu vào với tên hiển thị.** Tên “English (United States)” có thể thay đổi theo ngôn ngữ hiển thị; hãy dùng language tag chuẩn.
4. **Cho rằng `en` và `en-US` luôn bằng nhau.** Chúng khác mức cụ thể; chỉ gộp khi chính sách hỗ trợ cho phép.
5. **Bỏ script khi khớp locale.** Có thể chọn sai hệ chữ, nhất là với ngôn ngữ có nhiều cách viết.
6. **Coi `Locale.lookup(...)` là thuật toán chuyển mọi ngôn ngữ sang locale cùng ngôn ngữ gần nhất.** Nó tuân quy tắc language range/lookup, và có thể trả về `null`.
7. **Dùng `Locale.setDefault(...)` theo từng request.** Đó là trạng thái mặc định chia sẻ trong JVM, không thích hợp để điều khiển ngôn ngữ riêng cho nhiều người dùng đồng thời.
8. **Mặc định rằng bản dịch fallback là đầy đủ.** Bundle gốc có thể khiến chương trình không lỗi nhưng trộn ngôn ngữ; cần chính sách và kiểm thử chất lượng.
9. **Coi `Accept-Language` mạnh hơn lựa chọn tường minh.** Header có thể chỉ là cài đặt mặc định của trình duyệt, không phản ánh lựa chọn mới nhất của người dùng.
10. **Không đồng bộ frontend/backend.** Người dùng nhìn thấy một locale trong menu nhưng phản hồi API hoặc thông báo lỗi lại dùng locale khác.

## 11. Áp dụng từng bước trong một dự án Java

Khi xây tính năng chọn ngôn ngữ, có thể dùng quy trình:

1. **Xác định phạm vi hỗ trợ sản phẩm**: ngôn ngữ UI, định dạng, thông báo email, trợ giúp và những luồng bắt buộc.
2. **Khai báo danh sách có thứ tự và locale mặc định**: dùng BCP 47 language tag; không sinh trực tiếp từ locale có sẵn của JDK.
3. **Xác thực cấu hình khi khởi động**: tag hợp lệ, không trùng, locale mặc định có trong danh sách và tài nguyên thiết yếu sẵn sàng.
4. **Xây một hàm chọn locale có thể kiểm thử**: ưu tiên lựa chọn tường minh và hồ sơ, dùng thương lượng header khi cần, fallback rõ ràng.
5. **Truyền locale hiệu lực tới lớp trình bày**: formatter nhận locale cụ thể; dịch câu chữ lấy từ nguồn i18n; múi giờ và tiền tệ xử lý theo yêu cầu riêng.
6. **Kiểm thử khi phát hành và khi nâng JDK**: chú ý dấu phân cách, khoảng trắng Unicode, mẫu ngày, bản dịch thiếu, tính nhất quán của UI và API.

**Tự kiểm tra:**

- Tại sao một ứng dụng chỉ có tiếng Việt và tiếng Anh không nên đưa mọi locale từ `Locale.getAvailableLocales()` vào menu? — Vì khả năng định dạng của runtime không chứng minh ứng dụng đã hỗ trợ ngôn ngữ giao diện đó.
- Khi người dùng chọn `fr-FR` nhưng danh sách chỉ có `vi-VN` và `en-US`, ứng dụng nên làm gì? — Áp dụng chính sách rõ ràng: báo không hỗ trợ hoặc chọn fallback được công bố.
- `Locale.lookup(...)` trả về `null` nói lên điều gì? — Không tìm được ứng viên trong danh sách theo language ranges; ứng dụng phải quyết định bước tiếp theo.
- Vì sao `ResourceBundle.getBundle(...)` thành công vẫn chưa chứng minh bản dịch đầy đủ? — Do fallback có thể lấy khóa từ bundle chung hoặc gốc.
- Vì sao nên có một tập locale hỗ trợ riêng thay vì phụ thuộc phiên bản JDK? — Để cam kết sản phẩm, menu và kiểm thử không biến động ngoài ý muốn khi đổi runtime.

**Ghi nhớ:** **Danh sách locale được ứng dụng hỗ trợ là quyết định có chủ đích của sản phẩm.** Dùng `Locale` để biểu diễn tag, dùng danh sách đã khai báo để kiểm tra lựa chọn, dùng lookup khi cần thương lượng ngôn ngữ, và xác thực rằng bản dịch/định dạng thực sự đáp ứng phạm vi hỗ trợ đã hứa.