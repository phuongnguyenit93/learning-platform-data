# Thẻ ngôn ngữ BCP 47 và dấu phân cách trong Java

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Đọc và viết thẻ ngôn ngữ (language tag) theo BCP 47, chẳng hạn `vi-VN`, `en-US`, `zh-Hant-TW`.
- Phân biệt dấu gạch nối `-` của BCP 47 với dấu gạch dưới `_` trong cách hiển thị `Locale` kiểu cũ và tên file resource bundle.
- Chuyển đổi, chuẩn hóa, kiểm tra cú pháp thẻ ngôn ngữ bằng `java.util.Locale`.
- Xử lý đúng dữ liệu locale đến từ URL, cấu hình, HTTP và tránh nhầm cú pháp hợp lệ với locale được ứng dụng hỗ trợ.

Bài thuộc chủ đề **Mô hình Locale** của Java Core. `Locale` mô tả ngôn ngữ và các quy ước khu vực được ưu tiên; bản thân nó không phải múi giờ, bản dịch hay tập dữ liệu định dạng.

## 2. BCP 47 biểu diễn những gì?

**BCP 47** là chuẩn thẻ nhận diện ngôn ngữ (được mô tả chủ yếu trong RFC 5646). Một thẻ gồm nhiều **subtag** ghép bằng **dấu gạch nối ASCII `-` (hyphen-minus)**, theo thứ tự có quy tắc.

| Ví dụ | Cách đọc |
| --- | --- |
| `vi` | Tiếng Việt, chưa chỉ định vùng |
| `vi-VN` | Tiếng Việt ở Việt Nam |
| `en-US` | Tiếng Anh ở Hoa Kỳ |
| `en-GB` | Tiếng Anh ở Vương quốc Anh |
| `zh-Hans-CN` | Tiếng Trung, chữ giản thể, vùng Trung Quốc |
| `zh-Hant-TW` | Tiếng Trung, chữ phồn thể, vùng Đài Loan |
| `sr-Latn-RS` | Tiếng Serbia, chữ Latin, vùng Serbia |
| `es-419` | Tiếng Tây Ban Nha, vùng 419 (Mỹ Latinh và Caribe) |
| `th-TH-u-nu-thai` | Tiếng Thái ở Thái Lan, yêu cầu hệ chữ số Thái qua Unicode extension |

Với các thẻ thông dụng, cấu trúc dễ nhớ là:

```text
language[-Script][-REGION][-variant...][-extension...][-x-privateuse...]
```

Các thành phần chính:

1. **Language**: thường là mã ISO 639 gồm hai hoặc ba chữ cái, ví dụ `vi`, `en`, `ja`; trường ngôn ngữ của Java còn hỗ trợ các mã chữ cái dài hơn theo quy tắc tương ứng.
2. **Script**: bốn chữ cái (ISO 15924), ví dụ `Latn`, `Cyrl`, `Hans`, `Hant`. Script nói về hệ chữ viết; **không** phải quốc gia.
3. **Region**: hai chữ cái (thường mã ISO 3166-1) hoặc ba chữ số (UN M.49), ví dụ `VN`, `US`, `419`.
4. **Variant**: biến thể ngôn ngữ với quy tắc subtag riêng (thường 5–8 ký tự chữ/số, hoặc bốn ký tự bắt đầu bằng chữ số), ví dụ `sl-rozaj-biske`.
5. **Extension**: nhóm bắt đầu bằng một ký tự đơn, ví dụ `-u-` trong `en-US-u-ca-gregory-nu-latn`; `ca` đề cập lịch, `nu` đề cập hệ chữ số.
6. **Private use**: bắt đầu bằng `-x-`; thông tin riêng của hệ thống, cần thỏa thuận giữa bên phát và bên nhận để có ý nghĩa.

Đây là **mẫu tóm tắt cho trường hợp thường gặp**, không phải toàn bộ ngữ pháp RFC 5646 (chuẩn còn có extlang và một số thẻ kế thừa/grandfathered). Đừng tự dựng trình phân tích BCP 47 chỉ từ mẫu tóm tắt đó.

**Quy ước chữ hoa/thường:** `language` viết thường, `Script` viết hoa chữ đầu, `REGION` viết hoa; ví dụ `zh-Hant-TW`. Các subtag của BCP 47 về cơ bản không phân biệt hoa/thường, vì thế `EN-us` và `en-US` cùng nhận diện một thẻ; cách viết chuẩn hóa giúp lưu trữ và so sánh nhất quán.

## 3. Dấu `-` và `_`: ba ngữ cảnh cần tách biệt

| Ngữ cảnh | Giá trị ví dụ | Quy tắc |
| --- | --- | --- |
| Thẻ ngôn ngữ BCP 47 (API, cấu hình, HTTP) | `vi-VN`, `zh-Hant-TW` | Phân tách subtag bằng **`-`** |
| `Locale.toString()` của Java (biểu diễn lịch sử) | `vi_VN`, `en_US`; có thể có thêm phần script/variant/extension | Thường dùng **`_`**; **không** phải chuỗi BCP 47 |
| Hậu tố tên file `ResourceBundle` | `messages_vi_VN.properties` | Dấu **`_`** là quy ước đặt tên file Java, không phải thẻ gửi ra HTTP |

Không truyền `en_US` thẳng cho API yêu cầu BCP 47. Đặc biệt, `Locale.forLanguageTag("en_US")` **không** tự chuyển dấu `_` thành `-`: dấu `_` làm phần đầu không hợp lệ, có thể dẫn tới locale rỗng (`toLanguageTag()` trả `und`). Mặt khác, không lấy `Locale.toString()` làm dữ liệu trao đổi nếu đối tác yêu cầu thẻ BCP 47; chuỗi legacy có thêm quy tắc cho script, variant và extension.

Nếu cần tạo BCP 47 từ đối tượng Java, dùng **`locale.toLanguageTag()`**. Nếu cần tạo đối tượng từ BCP 47, dùng **`Locale.forLanguageTag(tag)`** hoặc `Locale.Builder.setLanguageTag(tag)`.

Với dữ liệu cũ có dạng `language_REGION`, chỉ chuyển đổi khi **đã biết rõ schema đầu vào**: tách các trường được định nghĩa riêng (`language`, `region`, `script`...) rồi đưa vào `Locale.Builder`; không dùng `replace('_', '-')` như bộ chuẩn hóa tổng quát cho mọi chuỗi `Locale.toString()`.

## 4. Java 17+: API quan trọng

| API | Công dụng và hành vi cần nhớ |
| --- | --- |
| `Locale.forLanguageTag(String)` | Đọc thẻ BCP 47 theo cách **dễ dãi**: gặp subtag sai cú pháp thì bỏ subtag đó và các subtag sau nó; không ném `IllformedLocaleException` trong tình huống này |
| `new Locale.Builder().setLanguageTag(String).build()` | Đọc **nghiêm ngặt**: thẻ sai cú pháp sẽ ném `IllformedLocaleException`; phù hợp khi kiểm tra dữ liệu người dùng |
| `locale.toLanguageTag()` | Xuất thẻ BCP 47 với quy tắc chuẩn hóa của Java; đây là API để trao đổi thẻ |
| `locale.getLanguage()`, `getScript()`, `getCountry()`, `getVariant()` | Lấy thành phần của đối tượng thay vì tự cắt chuỗi theo vị trí |
| `locale.getUnicodeLocaleType("nu")` | Đọc giá trị Unicode extension tương ứng (ví dụ `thai`) |
| `locale.toString()` | Biểu diễn theo truyền thống Java; dùng để chẩn đoán/legacy, không thay `toLanguageTag()` |

Cú pháp đúng **chưa đủ** để bảo đảm ngôn ngữ/vùng đó có dữ liệu định dạng, bản dịch hoặc được sản phẩm hỗ trợ. `Locale.Builder` kiểm tra dạng cú pháp, **không tra cứu toàn bộ mã trong IANA Language Subtag Registry**. Muốn giới hạn tập locale ứng dụng hỗ trợ, kiểm tra thêm theo danh sách ứng dụng.

## 5. Ví dụ chạy được: đọc, xuất và phát hiện lỗi dấu phân cách

Tạo file `LanguageTagsDemo.java`:

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class LanguageTagsDemo {
    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-vn");
        Locale zh = Locale.forLanguageTag("zh-Hant-TW");
        Locale th = Locale.forLanguageTag("th-TH-u-nu-thai");

        System.out.println(vi.toLanguageTag());
        System.out.println(vi.getLanguage());
        System.out.println(vi.getCountry());
        System.out.println(zh.toLanguageTag());
        System.out.println(zh.getScript());
        System.out.println(th.getUnicodeLocaleType("nu"));

        System.out.println(Locale.US.toString());
        System.out.println(Locale.US.toLanguageTag());

        // Dấu '_' không hợp lệ trong thẻ BCP 47.
        System.out.println(Locale.forLanguageTag("en_US").toLanguageTag());

        // Parser dễ dãi giữ tiền tố hợp lệ trước subtag sai.
        System.out.println(Locale.forLanguageTag("en-US-invalid_thing").toLanguageTag());

        try {
            new Locale.Builder().setLanguageTag("en_US").build();
            System.out.println("valid tag");
        } catch (IllformedLocaleException ex) {
            System.out.println("invalid tag");
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac LanguageTagsDemo.java
java LanguageTagsDemo
```

Đầu ra:

```text
vi-VN
vi
VN
zh-Hant-TW
Hant
thai
en_US
en-US
und
en-US
invalid tag
```

Giải thích:

- `vi-vn` chuẩn hóa thành `vi-VN`; các hàm getter lấy `vi` và `VN`.
- `zh-Hant-TW` tách được script `Hant`; `-u-nu-thai` chứa Unicode locale keyword `nu` với giá trị `thai`.
- Cùng một `Locale.US` có `toString() = en_US` nhưng `toLanguageTag() = en-US`. Đây là **hai định dạng khác nhau**.
- Với `en_US`, `forLanguageTag` không sửa dấu phân cách: kết quả tương đương locale ngôn ngữ chưa xác định, thẻ xuất thành `und`.
- Với `en-US-invalid_thing`, parser giữ `en-US` rồi bỏ đoạn không hợp lệ. `Builder` thay vào đó phát hiện lỗi; code bắt ngoại lệ thay vì để đầu vào bị sửa âm thầm.

## 6. Tạo thẻ bằng các trường thay vì ghép chuỗi thủ công

Khi dữ liệu là các trường riêng, `Locale.Builder` giúp đặt đúng thành phần và đúng dấu phân cách:

```java
import java.util.Locale;

public class LocalePartsDemo {
    public static void main(String[] args) {
        Locale locale = new Locale.Builder()
                .setLanguage("sr")
                .setScript("Latn")
                .setRegion("RS")
                .build();

        System.out.println(locale.toLanguageTag());
        System.out.println(locale.getLanguage());
        System.out.println(locale.getScript());
        System.out.println(locale.getCountry());
    }
}
```

```bash
javac LocalePartsDemo.java
java LocalePartsDemo
```

```text
sr-Latn-RS
sr
Latn
RS
```

Một cách ứng dụng điều này khi chuyển dữ liệu legacy có schema rõ ràng: nhận hai trường `language = "en"` và `region = "US"`, gọi `setLanguage("en").setRegion("US")`, rồi dùng `toLanguageTag()` để xuất `en-US`. Không cần tự ghép dấu gạch nối và đoán vị trí script/region.

## 7. Dùng tag ngoài thực tế: nhận đầu vào và kiểm tra hỗ trợ

Ví dụ ứng dụng chỉ công bố ba locale `vi-VN`, `en-US`, `ja-JP`. Trước tiên kiểm tra cú pháp bằng builder, sau đó **so sánh với danh sách được hỗ trợ**; tất cả trường hợp trống, sai cú pháp hoặc không được hỗ trợ dùng mặc định `vi-VN`.

Tạo file `SupportedLocaleDemo.java`:

```java
import java.util.IllformedLocaleException;
import java.util.Locale;
import java.util.Set;

public class SupportedLocaleDemo {
    private static final String DEFAULT_TAG = "vi-VN";
    private static final Set<String> SUPPORTED =
            Set.of("vi-VN", "en-US", "ja-JP");

    static Locale resolve(String input) {
        if (input == null || input.isBlank()) {
            return Locale.forLanguageTag(DEFAULT_TAG);
        }
        try {
            Locale candidate = new Locale.Builder()
                    .setLanguageTag(input.trim())
                    .build();
            return SUPPORTED.contains(candidate.toLanguageTag())
                    ? candidate
                    : Locale.forLanguageTag(DEFAULT_TAG);
        } catch (IllformedLocaleException ex) {
            return Locale.forLanguageTag(DEFAULT_TAG);
        }
    }

    public static void main(String[] args) {
        System.out.println(resolve("vi-VN").toLanguageTag());
        System.out.println(resolve("EN-us").toLanguageTag());
        System.out.println(resolve("en_US").toLanguageTag());
        System.out.println(resolve("fr-FR").toLanguageTag());
    }
}
```

```bash
javac SupportedLocaleDemo.java
java SupportedLocaleDemo
```

```text
vi-VN
en-US
vi-VN
vi-VN
```

Ở đây `EN-us` được chuẩn hóa thành `en-US`. `en_US` sai cú pháp BCP 47; `fr-FR` có cú pháp đúng nhưng chưa được ứng dụng hỗ trợ. Hai trường hợp đều rơi về mặc định theo **chính sách ví dụ**. Ứng dụng khác có thể trả HTTP 400, yêu cầu người dùng chọn lại hoặc áp dụng quy tắc fallback theo ngôn ngữ; đó là quyết định sản phẩm, không phải hành vi bắt buộc của BCP 47.

Trong HTTP, các giá trị tag như `vi-VN` có thể xuất hiện ở `Content-Language` hoặc là một phần danh sách `Accept-Language`. **Cả chuỗi** `Accept-Language: vi-VN,vi;q=0.9,en;q=0.7` là danh sách có trọng số, **không phải một BCP 47 tag**: phải phân tích cú pháp header/danh sách trước khi đưa từng tag vào `Locale`. Java cung cấp `Locale.LanguageRange.parse(...)` để làm việc với danh sách preference; không đưa nguyên chuỗi đó cho `Locale.forLanguageTag(...)`.

## 8. Lưu ý khi lưu trữ, so sánh và fallback

- Lưu định danh trao đổi bằng `toLanguageTag()` sau khi đã kiểm tra đầu vào. Nếu hỗ trợ legacy, chuyển ở ranh giới nhận dữ liệu, ghi rõ schema tương thích.
- So sánh chuỗi nên dùng dạng chuẩn hóa; `en`, `en-US` và `en-GB` là các mức xác định khác nhau. Đừng mặc định chúng có cùng dữ liệu hay cùng bản dịch.
- Nếu cần ghép nội dung theo ngôn ngữ, dùng cơ chế fallback của ứng dụng hoặc `ResourceBundle`; tên file như `messages_vi_VN.properties` có dấu `_` theo quy tắc đặt tên bundle, nhưng API `Locale` vẫn nhận `vi-VN`.
- Unicode extension như `u-ca-buddhist` hay `u-nu-thai` thể hiện yêu cầu về lịch/hệ chữ số. Việc bộ định dạng cụ thể có áp dụng extension hay không còn phụ thuộc API, provider và dữ liệu locale; không suy luận rằng mọi thư viện đều hỗ trợ.
- Thẻ ngôn ngữ **không mang múi giờ**. Không suy ra `Asia/Ho_Chi_Minh` chỉ từ `vi-VN`; thời gian cần `ZoneId` độc lập.
- `und` là subtag "undetermined" (ngôn ngữ không xác định) khi xuất BCP 47; khi parse vào `Locale`, `getLanguage()` có thể là chuỗi rỗng. Nó không có nghĩa là tiếng Anh hay tiếng Việt mặc định.

## 9. Lỗi thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Gửi `en_US` cho API đòi BCP 47 | Tag sai cú pháp; parser dễ dãi có thể cho `und` | Gửi `en-US` |
| Dùng `locale.toString()` để lưu/gửi thẻ | Gặp ký pháp legacy với `_`, và có thể có các đoạn đặc biệt | Dùng `locale.toLanguageTag()` |
| Nghĩ `forLanguageTag` luôn báo lỗi | Có thể bỏ đuôi sai mà không thông báo | Dùng `Locale.Builder.setLanguageTag` nếu phải từ chối tag sai |
| Nghĩ builder bảo đảm tên ngôn ngữ tồn tại/được hỗ trợ | Chỉ kiểm tra well-formed, không bảo đảm registry hoặc dữ liệu UI | Kiểm tra danh sách locale ứng dụng |
| Dựng tag bằng nối chuỗi vị trí cố định | Lẫn script/region/variant/extension | Dùng `Locale.Builder` và getter |
| Đổi toàn bộ `_` thành `-` với mọi chuỗi legacy | Có thể diễn giải sai variant/extension | Chỉ chuyển theo schema được biết rõ |
| Xem quốc gia quyết định ngôn ngữ hoặc múi giờ | Chọn sai nội dung/vùng giờ | Tách language, region và `ZoneId` |

## 10. Tự kiểm tra

1. `zh-Hant-TW` có các phần nào? **Đáp án:** language `zh`, script `Hant`, region `TW`.
2. Chuỗi nào hợp lệ khi truyền vào `Locale.forLanguageTag` như một BCP 47 tag: `pt-BR` hay `pt_BR`? **Đáp án:** `pt-BR`; dấu phân cách subtag là `-`.
3. Tại sao không dùng riêng `Locale.forLanguageTag` để xác thực input? **Đáp án:** có thể âm thầm bỏ subtag sai và phần phía sau, làm mất thông tin; builder nghiêm ngặt hơn.
4. `Locale.US.toString()` và `Locale.US.toLanguageTag()` khác nhau thế nào? **Đáp án:** lần lượt là `en_US` và `en-US`.
5. `ja-JP-u-ca-japanese` có nghĩa mọi thư viện Java buộc phải định dạng lịch Nhật không? **Đáp án:** không; extension diễn đạt yêu cầu, việc hỗ trợ thuộc về API/provider.

## Tài liệu tham khảo

- [RFC 5646 — Tags for Identifying Languages](https://www.rfc-editor.org/rfc/rfc5646)
- [Java SE 21 — `java.util.Locale`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Java SE 21 — `Locale.Builder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.Builder.html)
