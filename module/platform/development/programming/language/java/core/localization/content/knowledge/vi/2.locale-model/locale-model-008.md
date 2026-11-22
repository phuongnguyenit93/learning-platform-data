# Vì sao tạo được `Locale` không có nghĩa mọi dịch vụ đều hỗ trợ?

## 1. Vấn đề cốt lõi: `Locale` là yêu cầu, không phải giấy chứng nhận hỗ trợ

Trong Java, ta có thể tạo một đối tượng `Locale` chỉ với một thẻ ngôn ngữ hợp lệ về mặt cấu trúc:

```java
Locale locale = Locale.forLanguageTag("zz-ZZ");
```

`zz-ZZ` ở đây là mã minh họa cho một lựa chọn ngôn ngữ/vùng không phổ biến, không đại diện cho thị trường đã được ứng dụng triển khai. Java vẫn có thể tạo và giữ thẻ này. Nhưng từ đó **không thể kết luận** rằng Java, thư viện giao diện, hệ thống thông báo, dữ liệu tiền tệ hoặc chính ứng dụng đã có tài nguyên cho lựa chọn ấy.

Đây là điểm cần phân biệt trong mô hình `Locale`:

- **Biểu diễn yêu cầu:** tạo `Locale`, lấy `getLanguage()`, `getCountry()`, `toLanguageTag()` và truyền vào API.
- **Có triển khai/dữ liệu:** từng dịch vụ (định dạng số, ngày, so sánh chữ, phân tách từ, resource bundle...) có bộ dữ liệu và nhà cung cấp locale riêng.
- **Có khả năng hoạt động nhờ fallback:** dịch vụ có thể trả về kết quả dùng quy tắc chung hoặc một locale khác, ngay cả khi không có dữ liệu riêng cho locale yêu cầu.
- **Đúng với thị trường và người dùng:** bản dịch, ngữ pháp, ký hiệu, quy tắc địa phương và các ca giao diện đã được kiểm chứng. Đây là một mức đảm bảo cao hơn việc gọi API thành công.

**Kết luận của hiện tượng:** `new Locale(...)` (cách cũ), `Locale.forLanguageTag(...)` hay `Locale.Builder` chỉ tạo **đối tượng mô tả locale**; chúng không tự tải bản dịch, không kiểm tra đủ dịch vụ và không bắt ứng dụng hỗ trợ locale đó.

## 2. Vì sao Java cho tạo locale chưa được hỗ trợ?

### 2.1. Đối tượng `Locale` lưu định danh, không lưu toàn bộ dữ liệu địa phương

Một `Locale` có thể mang:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Language | `vi` | Ngôn ngữ |
| Script | `Latn`, `Hant` | Hệ chữ khi cần phân biệt |
| Region | `VN`, `US` | Quốc gia/vùng |
| Variant | Một biến thể hợp lệ | Thông tin biến thể bổ sung |
| Extension | Ví dụ `u-nu-latn` | Yêu cầu bổ sung theo chuẩn BCP 47, mức hỗ trợ tùy dịch vụ |

`Locale.forLanguageTag("vi-VN")` tạo mô tả tiếng Việt tại Việt Nam; `Locale.forLanguageTag("zz-ZZ")` vẫn có thể tạo một mô tả hợp lệ về mặt cú pháp. Không thao tác nào trong hai thao tác đó bảo đảm có tệp dịch, quy tắc phân loại chữ, dữ liệu vùng hay thiết kế giao diện tương ứng.

`Locale.Builder` có thể phát hiện **lỗi cú pháp** bằng `IllformedLocaleException`, nhưng cũng không chứng minh **có dịch vụ hỗ trợ**. `Locale.forLanguageTag` xử lý các phần không đúng cú pháp theo quy tắc phân tích thẻ ngôn ngữ; vì vậy đừng dùng việc hàm không ném exception làm phép kiểm tra “locale này đã được hỗ trợ”.

Ví dụ:

```java
Locale requested = Locale.forLanguageTag("zz-ZZ");
System.out.println(requested.toLanguageTag()); // zz-ZZ
```

Kết quả cho biết Java giữ được định danh yêu cầu. Nó không chứng minh đã có bản dịch `zz`.

### 2.2. “Hỗ trợ” phụ thuộc dịch vụ và bộ dữ liệu

Các dịch vụ locale-sensitive trong Java không bắt buộc có cùng danh sách locale. Chẳng hạn:

| Dịch vụ/API | Cung cấp gì? | Vì sao có thể khác dịch vụ khác? |
| --- | --- | --- |
| `NumberFormat` | Cách trình bày/phân tích số, phần trăm, tiền | Cần dữ liệu ký hiệu và mẫu định dạng số |
| `DateFormat` / `DateTimeFormatter` | Mẫu, tên tháng, tên thứ, quy tắc hiển thị ngày/giờ | Cần dữ liệu ngày/giờ và có cơ chế fallback riêng |
| `Collator` | Thứ tự so sánh chuỗi phù hợp ngôn ngữ | Cần quy tắc sắp xếp chữ |
| `BreakIterator` | Ranh giới ký tự, từ, câu, dòng | Cần quy tắc phân đoạn văn bản |
| `ResourceBundle` | Thông điệp do ứng dụng/thư viện cung cấp | Phụ thuộc các bundle hiện có trên classpath/module và fallback của chúng |
| `Currency` | Thông tin mã/đồng tiền liên quan đến vùng, khi xác định được | Phụ thuộc dữ liệu tiền tệ và vùng, không phải kho bản dịch |

Một locale có thể có khả năng định dạng số nhưng **không có bản dịch ứng dụng**; có bundle dịch nhưng chưa được kiểm thử việc sắp xếp từ hay hiển thị lịch. Ngay trong Java, dữ liệu có thể đến từ những locale-data provider khác nhau, bao gồm dữ liệu CLDR của JDK và các provider mở rộng qua SPI, tùy phiên bản/cấu hình/runtime.

Không nên hiểu “hàm chạy thành công” là “dịch vụ có dữ liệu chuẩn riêng cho đúng locale”. Đặc biệt, việc API lặng lẽ áp dụng quy tắc dự phòng có thể che giấu thiếu dữ liệu.

## 3. Kiểm tra khả năng được công bố theo từng API

Nhiều API cung cấp `getAvailableLocales()`, ví dụ `NumberFormat`, `DateFormat`, `Collator`, `BreakIterator`. Hãy hỏi **đúng dịch vụ** mà ứng dụng sắp dùng thay vì chỉ nhìn danh sách locale toàn JVM.

Tạo tệp **`LocaleAvailabilityDemo.java`**:

```java
import java.text.BreakIterator;
import java.text.Collator;
import java.text.DateFormat;
import java.text.NumberFormat;
import java.util.Arrays;
import java.util.Locale;

public class LocaleAvailabilityDemo {
    private static boolean advertised(Locale[] locales, Locale requested) {
        return Arrays.asList(locales).contains(requested);
    }

    public static void main(String[] args) {
        Locale requested = Locale.forLanguageTag("zz-ZZ");
        System.out.println("requested: " + requested.toLanguageTag());

        System.out.println("number: " + advertised(
                NumberFormat.getAvailableLocales(), requested));
        System.out.println("date: " + advertised(
                DateFormat.getAvailableLocales(), requested));
        System.out.println("collation: " + advertised(
                Collator.getAvailableLocales(), requested));
        System.out.println("word-boundary: " + advertised(
                BreakIterator.getAvailableLocales(), requested));

        NumberFormat formatter = NumberFormat.getNumberInstance(requested);
        System.out.println("formatted: " + formatter.format(1234567.5));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 LocaleAvailabilityDemo.java
java -cp . LocaleAvailabilityDemo
```

Dòng đầu có kết quả xác định:

```text
requested: zz-ZZ
```

Các dòng còn lại phụ thuộc phiên bản JDK, cấu hình locale provider và những provider được cài đặt trong runtime, nên **không có stdout cố định áp dụng cho mọi máy**. Với một runtime không công bố hỗ trợ `zz-ZZ`, có thể thấy `false` ở các dòng kiểm tra, nhưng lời gọi `getNumberInstance(requested).format(...)` vẫn có thể tạo ra chuỗi số do dùng dữ liệu dự phòng.

### Cách hiểu đúng kết quả

- `true` nghĩa là dịch vụ **công bố** locale ấy trong tập do API trả về. Nó không chứng minh bản dịch giao diện của bạn đã tồn tại hoặc mọi quy tắc văn hóa đã đúng.
- `false` nghĩa là locale ấy **không có trong danh sách được công bố của API đó**. Nó không nhất thiết đồng nghĩa mọi lời gọi định dạng với locale đó sẽ thất bại; dịch vụ có thể fallback.
- Kết quả của `NumberFormat` **không được suy ra** từ `DateFormat` hoặc `Collator`.
- `Locale.getAvailableLocales()` trả về danh sách locale cài đặt/được cung cấp ở phạm vi runtime; **không phải danh sách bản dịch mà ứng dụng có**, và cũng không phải kiểm thử đầy đủ cho từng nghiệp vụ.

Một kiểm tra `Arrays.asList(...).contains(requested)` như trên so khớp **chính xác đối tượng locale**, thích hợp để khảo sát API. Trong ứng dụng thực tế, việc lựa chọn `vi-VN` khi chỉ có `vi` là một **chính sách matching/fallback** riêng, không thể chỉ dựa vào phép `contains` này.

## 4. `ResourceBundle`: có thể trả về thông điệp mà vẫn không có bản dịch đúng locale

`ResourceBundle` đọc tài nguyên do ứng dụng/thư viện đóng gói, tách biệt với tập locale sẵn có của `NumberFormat` hay `Collator`.

Giả sử dự án chỉ cung cấp:

**`labels.properties`** (gói gốc):

```properties
welcome=Hello
```

**`labels_vi.properties`**:

```properties
welcome=Xin chào
```

Và chương trình **`BundleFallbackDemo.java`**:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleFallbackDemo {
    public static void main(String[] args) {
        show("vi-VN");
        show("fr-FR");
    }

    private static void show(String languageTag) {
        Locale requested = Locale.forLanguageTag(languageTag);
        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);
        ResourceBundle bundle =
                ResourceBundle.getBundle("labels", requested, control);

        System.out.printf("%s -> %s (bundle: %s)%n",
                requested.toLanguageTag(),
                bundle.getString("welcome"),
                bundle.getLocale().toLanguageTag());
    }
}
```

Lưu ba tệp cùng thư mục và chạy trên classpath bằng JDK 17+:

```bash
javac -encoding UTF-8 BundleFallbackDemo.java
java -cp . BundleFallbackDemo
```

Với đúng ba tệp ở ví dụ, đầu ra:

```text
vi-VN -> Xin chào (bundle: vi)
fr-FR -> Hello (bundle: und)
```

**Giải thích chi tiết:**

- Người dùng yêu cầu `vi-VN`; không có `labels_vi_VN.properties` nhưng có `labels_vi.properties`, nên lời chào tiếng Việt được chọn. `getLocale()` trả về `vi`: locale của bundle thực sự được nạp, không nhất thiết trùng locale đã yêu cầu.
- Người dùng yêu cầu `fr-FR`; không có bundle tiếng Pháp, nên lấy `labels.properties` gốc với `Locale.ROOT`. `Locale.ROOT.toLanguageTag()` là `und` (“undetermined”). Lời gọi thành công nhưng thông điệp **vẫn là tiếng Anh**.
- `getNoFallbackControl(...)` trong ví dụ tắt nhánh thử **default locale của JVM** để kết quả rõ ràng; nó vẫn cho phép dùng **bundle gốc**. Với cơ chế `getBundle` mặc định, tập ứng viên còn có thể xét default locale theo thuật toán của `ResourceBundle`.
- Trên JDK 17, resource bundle `.properties` được đọc bằng UTF-8 theo quy tắc hiện hành (có cơ chế tương thích dữ liệu cũ). Vì vậy có thể lưu trực tiếp dấu tiếng Việt như ví dụ; cần bảo đảm công cụ đóng gói giữ nguyên nội dung/encoding.

Điều tương tự xảy ra khi bundle có một số khóa nhưng thiếu những khóa khác: `getString` có thể lấy giá trị từ bundle cha. Nếu không tìm thấy khóa ở toàn bộ chuỗi phân giải, Java ném `MissingResourceException`. Do đó cần kiểm tra **độ phủ khóa và chất lượng dịch**, không chỉ kiểm tra `getBundle` có trả về đối tượng.

Một chương trình có thể có tài nguyên `labels_vi.properties` ngay cả khi dịch vụ bên thứ ba không hỗ trợ quy tắc riêng cho `vi-VN`. Ngược lại, runtime có thể định dạng số tiếng Pháp nhưng ứng dụng không có bất kỳ thông điệp tiếng Pháp nào.

## 5. Fallback là tính năng hữu ích nhưng dễ làm ta kết luận sai

Có nhiều lớp fallback độc lập:

```text
Thẻ người dùng yêu cầu: vi-VN / fr-FR / ...
           |
           +--> Matching locale mà sản phẩm cam kết hỗ trợ
           |       -> ví dụ hỗ trợ vi, en; chọn fallback en
           |
           +--> ResourceBundle
           |       -> bản dịch biến thể/vùng -> ngôn ngữ -> bundle gốc
           |       -> có thể thử default locale theo Control
           |
           +--> NumberFormat / DateFormat / Collator / ...
                   -> nhà cung cấp dữ liệu của từng dịch vụ
                   -> quy tắc dự phòng riêng của runtime
```

Sơ đồ thể hiện **các nhánh độc lập**, không phải một thứ tự thực thi duy nhất của Java. Một `ResourceBundle` lấy được câu tiếng Anh và một `NumberFormat` tạo được chuỗi số **không chứng minh** rằng sản phẩm đang hỗ trợ đầy đủ `fr-FR`.

Một số API còn có thể không phân giải được dữ liệu vùng cụ thể hoặc ném lỗi cho đầu vào không phù hợp. Đừng giả định tất cả API đều fallback, hay đều fallback về cùng một locale. Đặc biệt:

- `NumberFormat.getCurrencyInstance(locale)` dùng quy tắc format theo locale; nó **không đổi đơn vị tiền tệ hoặc tỷ giá** của dữ liệu giao dịch.
- `Currency.getInstance(locale)` có điều kiện về thông tin vùng và dữ liệu mã tiền; chỉ tạo được `Locale` không bảo đảm suy ra được tiền tệ.
- `DateTimeFormatter.ofLocalizedDate(...).withLocale(locale)` cần dữ liệu mẫu định dạng. Chọn locale **không** chọn múi giờ; múi giờ phải được xác định riêng bằng `ZoneId`.
- `Collator` có thể dùng quy tắc chung nếu thiếu dữ liệu chuyên biệt. Kết quả sắp xếp chạy được không đủ để kết luận đúng yêu cầu từ điển của ngôn ngữ.
- Các extension Unicode trong BCP 47 (như lựa chọn hệ chữ số) chỉ có hiệu lực ở những API/provider thực sự hiểu và áp dụng chúng.

## 6. Định nghĩa rõ “locale được hỗ trợ” của chính ứng dụng

Đối với sản phẩm, “supported locale” nên là **cam kết cụ thể** với từng tính năng, thay vì chỉ là “Java chấp nhận language tag”.

Ví dụ, ứng dụng chỉ phát hành giao diện tiếng Việt và tiếng Anh:

```java
import java.util.Locale;
import java.util.Set;

public class SupportedLocaleDemo {
    private static final Set<String> SUPPORTED =
            Set.of("vi", "en");

    public static void main(String[] args) {
        Locale requested = Locale.forLanguageTag("fr-FR");
        String language = requested.getLanguage();

        Locale selected = SUPPORTED.contains(language)
                ? requested
                : Locale.forLanguageTag("en");

        System.out.println("requested: " + requested.toLanguageTag());
        System.out.println("selected: " + selected.toLanguageTag());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SupportedLocaleDemo.java
java -cp . SupportedLocaleDemo
```

Đầu ra:

```text
requested: fr-FR
selected: en
```

Ví dụ chỉ minh họa chính sách hỗ trợ **theo language**. Trong sản phẩm thực tế, `en-US` và `en-GB` hoặc `zh-Hans` và `zh-Hant` có thể cần xem như các locale riêng; việc rút xuống `getLanguage()` không luôn phù hợp. Hãy dùng một danh sách locale hỗ trợ thực tế cùng một chính sách matching có định nghĩa rõ; có thể sử dụng `Locale.LanguageRange` với `Locale.lookup`/`Locale.filter` khi thương lượng các thẻ ngôn ngữ theo BCP 47 và HTTP `Accept-Language`.

Một danh sách hỗ trợ đáng tin nên trả lời được:

1. **Thông điệp:** bản dịch đã đủ khóa, được duyệt, có fallback minh bạch hay chưa?
2. **Số/ngày/giờ:** dữ liệu provider nào được dùng, định dạng được kiểm thử theo locale và phiên bản runtime nào?
3. **Sắp xếp, tìm kiếm và chia từ:** tính năng có thực sự cần quy tắc ngôn ngữ cụ thể, và đã kiểm thử chưa?
4. **Tiền tệ, múi giờ, đơn vị đo:** phần nào do locale gợi ý, phần nào phải là lựa chọn hoặc dữ liệu nghiệp vụ riêng?
5. **Giao diện:** đã thử văn bản dài, dấu tiếng Việt, chữ phải-sang-trái khi cần, font, đọc màn hình và thông báo lỗi chưa?

| Trạng thái | Điều thực sự có thể khẳng định |
| --- | --- |
| `Locale.forLanguageTag(tag)` trả về đối tượng | Java biểu diễn/phân tích được định danh theo khả năng của API |
| `SomeService.getAvailableLocales()` chứa locale | Dịch vụ đó công bố locale trong runtime hiện tại |
| Lời gọi định dạng không ném lỗi | Có kết quả; có thể đã dùng fallback |
| `ResourceBundle.getBundle` trả về bundle | Tìm thấy bundle theo cơ chế phân giải; chưa chắc đúng locale yêu cầu |
| QA bản dịch và định dạng theo locale đạt | Tính năng đã được kiểm chứng trong phạm vi kiểm thử cụ thể |
| Ứng dụng quảng bá hỗ trợ locale | Nên là cam kết dựa trên các phép kiểm tra và giới hạn được công bố |

## 7. Cách kiểm thử để không bị fallback che lỗi

Với mỗi locale ứng dụng dự kiến hỗ trợ, nên kiểm tra các nhóm ca sau:

- **Đúng bản dịch:** những khóa quan trọng xuất hiện bằng ngôn ngữ mong muốn; không rơi về bundle gốc ngoài chính sách cho phép. Kiểm tra `bundle.getLocale()` khi cần phát hiện fallback toàn bundle; riêng trường hợp thiếu từng khóa phải kiểm thử bằng độ phủ nội dung/giá trị.
- **Khóa chưa dịch:** hệ thống hiển thị nội dung dự phòng có kiểm soát, hoặc báo thiếu bản dịch ở bước kiểm thử/build; không để lộ tên khóa hay thông báo lẫn ngôn ngữ ngoài ý muốn.
- **Định dạng locale:** đối chiếu mẫu số, ngày, phần trăm/tiền tệ, tên tháng và thứ trên JDK/locale-provider đã chọn. Tránh cố định snapshot cho mọi JDK nếu dữ liệu CLDR có thể được cập nhật.
- **Giá trị biên:** số âm, số rất lớn, số thập phân, ngày chuyển năm, ngày/giờ gần thời điểm đổi múi giờ, ngôn ngữ có dấu hoặc script khác.
- **Dịch vụ độc lập:** định dạng số thành công không thay thế kiểm thử `Collator` và `BreakIterator` nếu ứng dụng sử dụng chúng.
- **Locale không được hỗ trợ:** yêu cầu `zz-ZZ` hoặc một thẻ hợp lệ nằm ngoài danh sách sản phẩm; xác nhận ứng dụng chọn fallback dự kiến, không thông báo nhầm rằng locale ấy đã được hỗ trợ đầy đủ.
- **Môi trường:** cố định hoặc ghi nhận phiên bản JDK, cấu hình locale provider, timezone, tập tài nguyên và dependency. Dữ liệu giữa các bản JDK/CLDR có thể thay đổi.

### Những sai lầm dễ gặp

| Sai lầm | Vì sao sai? | Cách làm đúng |
| --- | --- | --- |
| “Tạo `Locale` không lỗi thì ngôn ngữ này được hỗ trợ” | `Locale` chỉ lưu định danh | Kiểm tra khả năng của từng dịch vụ và độ phủ sản phẩm |
| “Có trong `Locale.getAvailableLocales()` là có bản dịch” | Dữ liệu runtime khác tài nguyên ứng dụng | Kiểm tra bundle, khóa dịch và QA |
| “`format()` ra chữ là đã đúng locale” | Kết quả có thể xuất phát từ fallback | Kiểm thử kết quả thực tế và provider |
| “Có `messages_fr.properties` là mọi dịch vụ đều hỗ trợ `fr-FR`” | Bundle chỉ giải quyết thông điệp | Kiểm thử số, ngày, chữ, quy tắc nghiệp vụ riêng |
| “API nào cũng trả về cùng danh sách locale” | Mỗi API/provider có phạm vi khác nhau | Dùng `getAvailableLocales()` của đúng API |
| “`Locale` xác định luôn múi giờ/đơn vị tiền” | Đây là các dữ kiện khác nhau | Quản lý `ZoneId`, mã tiền và nghiệp vụ độc lập |
| “Fallback không báo lỗi thì không cần kiểm tra” | Fallback có thể che bản dịch bị thiếu | Kiểm thử locale thực dùng và định nghĩa fallback rõ ràng |

## 8. Ghi nhớ

- **Tạo được `Locale` chỉ chứng minh có đối tượng mô tả yêu cầu.** Nó không tự bổ sung dữ liệu, dịch văn bản hoặc chứng minh mọi dịch vụ Java hỗ trợ locale đó.
- **Hỗ trợ thuộc về từng API/provider và từng phần của sản phẩm.** `NumberFormat`, `DateFormat`, `Collator`, `BreakIterator` và `ResourceBundle` có phạm vi khác nhau.
- **Fallback có thể khiến lời gọi thành công dù thiếu hỗ trợ trực tiếp.** Muốn biết đang dùng bản dịch nào, cần quan sát locale/tài nguyên thực được chọn và kiểm thử nội dung.
- **Ứng dụng phải tự định nghĩa danh sách locale hỗ trợ, chính sách lựa chọn/fallback và bộ kiểm thử.** Không suy ra cam kết sản phẩm từ việc `Locale.forLanguageTag` nhận một thẻ.
