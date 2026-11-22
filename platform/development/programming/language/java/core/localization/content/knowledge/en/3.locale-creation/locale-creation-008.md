# Locale.equals(), stripExtensions() và giới hạn của toString() khi lưu trữ

## 1. Mục tiêu và bối cảnh

`java.util.Locale` mô tả ngôn ngữ, hệ chữ viết, vùng lãnh thổ, biến thể và các extension có thể tác động đến hành vi bản địa hóa. Khi xử lý nhiều `Locale`, ba thao tác dễ nhầm lẫn là:

- **`equals(Object)`:** kiểm tra hai đối tượng `Locale` có cùng toàn bộ danh tính locale hay không.
- **`stripExtensions()`:** tạo biểu diễn locale **không còn extension**, vẫn giữ language, script, country và variant.
- **`toString()`:** xuất biểu diễn văn bản truyền thống của Java, thuận tiện để nhìn nhanh nhưng **không phải định dạng trao đổi/lưu trữ BCP 47**.

Để lưu trữ, trao đổi thẻ ngôn ngữ với hệ thống khác, sử dụng **`toLanguageTag()`** và phục hồi bằng `Locale.forLanguageTag(...)` hoặc `Locale.Builder.setLanguageTag(...)`, với kiểm tra dữ liệu đầu vào phù hợp.

Ví dụ:

```text
en-US                   language=en, region=US
en-US-u-nu-thai         cùng language/region nhưng có Unicode extension nu=thai
sr-Latn-RS              language=sr, script=Latn, region=RS
sr-Cyrl-RS              language=sr, script=Cyrl, region=RS
```

Hai locale có cùng ngôn ngữ và vùng **chưa chắc bằng nhau** nếu script, variant hoặc extension khác nhau.

## 2. `equals(Object)` so sánh những gì?

`Locale.equals(Object)` trả về `true` nếu đối tượng kia cũng là `Locale` và có cùng các thành phần định danh: **language, script, country/region, variant và extensions**. Đây là phép so sánh toàn bộ danh tính locale, không phải so sánh "gần giống" hoặc đo mức độ tương thích ngôn ngữ.

| Locale thứ nhất | Locale thứ hai | `equals` | Lý do |
| --- | --- | --- | --- |
| `en-US` | `en-US` | `true` | Các thành phần tương đương |
| `en-US` | `en-GB` | `false` | Region khác |
| `sr-Latn-RS` | `sr-Cyrl-RS` | `false` | Script khác |
| `en-US` | `en-US-u-nu-thai` | `false` | Extension khác |
| `en-US-u-nu-thai` | `en-US-u-ca-buddhist` | `false` | Cùng language/region, extension khác |
| `EN-us-u-NU-thai` | `en-US-u-nu-thai` | `true` sau khi parse | Thẻ không phân biệt hoa/thường; `Locale` chuẩn hóa dạng hợp lệ |

**Lưu ý:** bảng áp dụng cho các đối tượng tạo bằng `Locale.forLanguageTag(...)`, không khẳng định có thể dùng phép so sánh chuỗi nguyên bản để thay `equals`. Ví dụ, `"EN-us".equals("en-US")` trong Java trả `false` vì `String.equals` phân biệt chữ hoa/thường, còn các `Locale` tạo từ hai thẻ đó có thể bằng nhau.

Vì `equals` kiểm tra đầy đủ định danh nên `Locale` có thể dùng làm key cho `HashMap`/`HashSet`; phương thức `hashCode()` tuân theo cùng quy ước. Nhưng nếu bài toán cần gom theo ngôn ngữ hoặc vùng, hãy **chọn tiêu chí gom nhóm riêng**, thay vì mong `equals` bỏ qua những thành phần không quan tâm.

Ví dụ phân biệt ba câu hỏi:

- "**Có cùng chính xác locale không?**" → `a.equals(b)`.
- "**Có cùng language không?**" → so sánh `a.getLanguage()` với `b.getLanguage()` (cần hiểu rằng cùng language chưa chắc cùng script/nội dung).
- "**Có cùng identity nếu bỏ qua extension không?**" → `a.stripExtensions().equals(b.stripExtensions())`, **chỉ** khi nghiệp vụ cho phép bỏ qua extension.

## 3. `stripExtensions()` loại bỏ phần nào?

BCP 47 có các extension, ví dụ:

- `en-US-u-nu-thai`: extension `u`, khóa Unicode `nu` có giá trị `thai` (hệ chữ số Thái).
- `en-US-u-ca-buddhist`: extension `u`, khóa `ca` có giá trị `buddhist` (lựa chọn lịch Phật giáo).
- `ja-JP-u-ca-japanese`: extension yêu cầu hệ lịch Nhật.

`stripExtensions()` loại bỏ **toàn bộ extension** (kể cả Unicode extension và các nhóm extension khác). Nó **không** bỏ language, script, region hay variant.

```text
en-US-u-nu-thai       --stripExtensions()--> en-US
zh-Hant-TW-u-nu-hanidec --stripExtensions()--> zh-Hant-TW
sr-Latn-RS            --stripExtensions()--> sr-Latn-RS
```

Đầu vào là `Locale`, đầu ra cũng là `Locale`. `Locale` là immutable nên lời gọi **không sửa đối tượng ban đầu**. Nếu không có extension, Java có thể trả về chính instance hiện tại; **không** viết logic nghiệp vụ dựa trên việc so sánh hai tham chiếu bằng `==`. Hãy dùng `equals` để kiểm tra giá trị.

Quan trọng: `stripExtensions()` không có nghĩa là "tổng quát hóa hoàn toàn" hoặc "đưa về locale ngôn ngữ gốc". Ví dụ `sr-Latn-RS` và `sr-RS` vẫn khác nhau sau khi strip vì script `Latn` vẫn hiện diện. Để khái quát theo ngôn ngữ phải xác định quy tắc riêng, có thể sử dụng `getLanguage()`, và chấp nhận mất các sắc thái khác.

### Khi nào nên dùng?

Trong một hệ thống mà **khóa tra cứu tài nguyên chỉ quan tâm language/script/region/variant**, việc strip extension trước khi tra cứu có thể là chính sách chủ ý. Ví dụ nội dung bản dịch có thể không phân biệt lựa chọn số chữ Thái hay số Latin, trong khi thành phần định dạng số thì vẫn cần phân biệt.

### Khi nào không nên dùng?

Đừng strip một locale ngay trước khi định dạng lịch, số hoặc tiền tệ nếu extension liên quan là cấu hình mà người dùng thực sự yêu cầu. Việc loại bỏ `u-nu-thai` hoặc `u-ca-buddhist` có thể làm mất ý định lựa chọn hệ chữ số/lịch; mức độ ảnh hưởng thực tế phụ thuộc API/provider hỗ trợ extension nào.

Cần chú ý khác biệt giữa hai tiêu chí: **bằng nhau sau khi bỏ extension** và **thay thế nhau an toàn ở mọi nơi**. Kết quả thứ nhất không đảm bảo kết quả thứ hai.

## 4. Ví dụ Java 17+: `equals` và `stripExtensions`

Tạo file `LocaleEqualityDemo.java`:

```java
import java.util.Locale;

public class LocaleEqualityDemo {
    public static void main(String[] args) {
        Locale base = Locale.forLanguageTag("en-US");
        Locale thaiDigits = Locale.forLanguageTag("en-US-u-nu-thai");
        Locale buddhistCalendar =
                Locale.forLanguageTag("en-US-u-ca-buddhist");

        System.out.println(base.equals(thaiDigits));
        System.out.println(thaiDigits.stripExtensions().equals(base));
        System.out.println(thaiDigits.getUnicodeLocaleType("nu"));
        System.out.println(
                thaiDigits.stripExtensions().getUnicodeLocaleType("nu"));
        System.out.println(thaiDigits.equals(buddhistCalendar));
        System.out.println(thaiDigits.equals(
                Locale.forLanguageTag("EN-us-u-NU-thai")));

        Locale latin = Locale.forLanguageTag("sr-Latn-RS");
        Locale cyrillic = Locale.forLanguageTag("sr-Cyrl-RS");

        System.out.println(latin.equals(cyrillic));
        System.out.println(latin.stripExtensions().equals(
                Locale.forLanguageTag("sr-RS")));
        System.out.println(latin.toString());
        System.out.println(latin.toLanguageTag());
    }
}
```

Chạy:

```bash
javac LocaleEqualityDemo.java
java LocaleEqualityDemo
```

Đầu ra chính xác:

```text
false
true
thai
null
false
true
false
false
sr_RS_#Latn
sr-Latn-RS
```

Giải thích lần lượt:

1. `base` khác `thaiDigits` vì `thaiDigits` có extension `u-nu-thai`.
2. Khi bỏ extension, `thaiDigits` còn `en-US` và bằng `base`.
3. `getUnicodeLocaleType("nu")` trả về `thai` trước khi strip; sau strip trả `null` vì không còn keyword `nu`.
4. Hai locale có extension khác nhau (`nu` so với `ca`) không bằng nhau.
5. Parse `EN-us-u-NU-thai` cho cùng định danh với `en-US-u-nu-thai`.
6. Script Latin và Cyrillic khác nhau; strip không xóa script.
7. Cùng `latin`, `toString()` trả `sr_RS_#Latn` theo biểu diễn Java, còn `toLanguageTag()` trả `sr-Latn-RS` theo BCP 47.

**Lưu ý về kiểm chứng:** giá trị `null` hiển thị ở stdout do `System.out.println(String)` nhận kết quả `null`, không phải chuỗi literal `"null"` được lưu làm locale keyword.

## 5. Tại sao `toString()` không phù hợp làm định dạng lưu trữ?

`Locale.toString()` xuất chuỗi theo quy tắc lịch sử của Java: thường ngăn cách language, country và variant bằng dấu gạch dưới `_`, và biểu diễn script/extensions có thể chứa `#`. Một số ví dụ:

| Đối tượng `Locale` | `toString()` | `toLanguageTag()` |
| --- | --- | --- |
| `Locale.US` | `en_US` | `en-US` |
| `Locale.forLanguageTag("sr-Latn-RS")` | `sr_RS_#Latn` | `sr-Latn-RS` |
| `Locale.forLanguageTag("zh-Hant-TW-u-nu-hanidec")` | `zh_TW_#Hant_u-nu-hanidec` | `zh-Hant-TW-u-nu-hanidec` |

Các chuỗi `en_US` hay `sr_RS_#Latn` là biểu diễn riêng theo API `toString`; chúng **không phải** BCP 47 language tag. Đưa chúng trực tiếp vào `Locale.forLanguageTag` có thể bị xem là sai cú pháp và mất thông tin, vì parser này mong đợi tag dạng `en-US` với dấu `-`.

Ba giới hạn thực tế:

1. **Không phải hợp đồng trao đổi chuẩn:** nếu API bên ngoài mong BCP 47, chuỗi từ `toString` không đáp ứng.
2. **Không có cặp parse toàn năng tương ứng:** Java không cung cấp hợp đồng chung "đưa mọi kết quả `toString` vào `forLanguageTag` để khôi phục nguyên vẹn". `forLanguageTag` được thiết kế cho BCP 47, không phải để đọc chuỗi legacy.
3. **Dễ sai khi tự tách hoặc thay dấu:** script, variant và extensions làm chuỗi legacy phức tạp hơn `language_COUNTRY`. Không dùng `replace('_', '-')` làm parser/chuyển đổi tổng quát.

`toString()` vẫn hữu ích cho debug/log nếu người đọc biết đó là biểu diễn Java. Nhưng một chuỗi được ghi xuống cơ sở dữ liệu, JSON, URL, message queue hoặc gửi sang hệ thống khác nên có **schema rõ ràng**: nếu trường đó là BCP 47 language tag, ghi bằng `toLanguageTag()`.

### Minh họa rủi ro mất dữ liệu

Tạo `LocaleStorageDemo.java`:

```java
import java.util.Locale;

public class LocaleStorageDemo {
    public static void main(String[] args) {
        Locale original =
                Locale.forLanguageTag("zh-Hant-TW-u-nu-hanidec");

        String legacy = original.toString();
        String tag = original.toLanguageTag();

        System.out.println(legacy);
        System.out.println(tag);
        System.out.println(
                Locale.forLanguageTag(legacy).toLanguageTag());

        Locale restored = new Locale.Builder()
                .setLanguageTag(tag)
                .build();
        System.out.println(original.equals(restored));
        System.out.println(original.stripExtensions().toLanguageTag());
        System.out.println(
                original.equals(original.stripExtensions()));
    }
}
```

Chạy:

```bash
javac LocaleStorageDemo.java
java LocaleStorageDemo
```

Đầu ra:

```text
zh_TW_#Hant_u-nu-hanidec
zh-Hant-TW-u-nu-hanidec
und
true
zh-Hant-TW
false
```

`und` đại diện cho language "undetermined" khi xuất tag; ở đây xuất hiện vì `forLanguageTag` không chấp nhận chuỗi legacy có `_` là thẻ BCP 47 hợp lệ. Phần `true` chứng minh thẻ `toLanguageTag()` của ví dụ này được phục hồi bằng `Builder.setLanguageTag()` mà vẫn giữ script, region và Unicode extension. Sau `stripExtensions()`, tag chỉ còn `zh-Hant-TW` nên không còn bằng `original`.

**Phạm vi bảo đảm:** ví dụ dùng một `Locale` BCP 47 hợp lệ ngay từ đầu. Các `Locale` legacy được dựng bằng API cũ với variant không phù hợp ngữ pháp BCP 47 có thể không round-trip hoàn toàn qua `toLanguageTag`/`forLanguageTag`. Khi thiết kế schema mới, nên ưu tiên các locale hợp lệ theo BCP 47; khi di chuyển dữ liệu cũ, kiểm tra từng trường hợp thay vì giả định mọi chuỗi đều chuyển đổi không mất mát.

## 6. Quy trình lưu và phục hồi locale thực tế

Dùng trường tên rõ ràng như `localeTag`, `languageTag` với giá trị ví dụ `"vi-VN"` hoặc `"en-US-u-nu-thai"`. Lưu thẻ sau khi chuẩn hóa bằng `toLanguageTag()`; phục hồi bằng builder nếu cần **từ chối đầu vào sai cú pháp**.

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class LocaleInputDemo {
    static Locale parseTag(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Missing language tag");
        }
        try {
            return new Locale.Builder()
                    .setLanguageTag(input.trim())
                    .build();
        } catch (IllformedLocaleException ex) {
            throw new IllegalArgumentException(
                    "Invalid language tag", ex);
        }
    }

    public static void main(String[] args) {
        Locale locale = parseTag("EN-us-u-nu-thai");
        String stored = locale.toLanguageTag();
        Locale loaded = parseTag(stored);

        System.out.println(stored);
        System.out.println(locale.equals(loaded));

        try {
            parseTag("en_US");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

```bash
javac LocaleInputDemo.java
java LocaleInputDemo
```

```text
en-US-u-nu-thai
true
Invalid language tag
```

Trong luồng này, `Builder.setLanguageTag` kiểm tra **cú pháp tag**. Nó không bảo đảm mọi mã ngôn ngữ đều thuộc một tập nghiệp vụ cho phép, cũng không bảo đảm các tài nguyên ngôn ngữ hay extension đều được runtime hỗ trợ. Ứng dụng có thể kiểm tra thêm danh sách `supportedLocales` khi cần.

**Phân biệt parser:**

- `Locale.forLanguageTag(tag)` **dễ dãi**: gặp subtag sai có thể bỏ subtag lỗi và toàn bộ phần sau mà không ném lỗi.
- `Locale.Builder.setLanguageTag(tag)` **nghiêm ngặt** với cú pháp malformed: ném `IllformedLocaleException`.
- Cả hai không phải bộ xác minh đầy đủ sự tồn tại của locale trong mọi registry hay khả năng hỗ trợ của ứng dụng.

Trong chương trình thực tế, chỉ sử dụng `stripExtensions()` để xây khóa **riêng** cho một trường hợp có chủ đích. Nếu muốn giữ lựa chọn lịch/chữ số người dùng khi lưu, đừng strip trước khi ghi `localeTag`.

## 7. Lựa chọn phép so sánh theo nghiệp vụ

| Câu hỏi | Mẫu API | Điều cần chấp nhận |
| --- | --- | --- |
| Hai lựa chọn locale có hoàn toàn trùng không? | `a.equals(b)` | Script/variant/extension khác đều bị phân biệt |
| Hai locale có cùng phần chính khi bỏ mọi extension không? | `a.stripExtensions().equals(b.stripExtensions())` | Extension đã bị cố ý bỏ qua |
| Hai locale có cùng ngôn ngữ không? | `a.getLanguage().equals(b.getLanguage())` | Region, script, variant, extension không được xét |
| Có cần giữ cấu hình số/lịch trong khóa cache formatter không? | Giữ `Locale` đầy đủ làm key | Extension có thể ảnh hưởng kết quả định dạng |
| Cần gửi locale dưới dạng chuỗi cho API? | `locale.toLanguageTag()` | Chuỗi là BCP 47, không phải `toString()` |
| Cần xem nhanh đối tượng trong log? | `locale.toString()` | Chỉ dùng làm thông tin chẩn đoán |

Ví dụ, cache tên bản dịch theo ngôn ngữ có thể chủ đích bỏ qua extension; ngược lại, cache formatter với hai lựa chọn `en-US` và `en-US-u-nu-thai` cần cân nhắc giữ extension trong khóa vì việc bỏ qua có nguy cơ dùng nhầm cấu hình số. Có thể không phải mọi provider đều xử lý `nu`, nhưng quyết định key phải dựa trên hợp đồng định dạng của chương trình.

Nếu muốn một cơ chế fallback như "`en-US-u-nu-thai` → `en-US` → `en`", hãy xây và ghi rõ chính sách fallback của ứng dụng hoặc sử dụng API quản lý tài nguyên có hỗ trợ fallback tương ứng. **`stripExtensions()` không tự thực hiện cả chuỗi fallback** đó: nó chỉ trả về một đối tượng không có extension.

## 8. Những lỗi thường gặp

| Lỗi | Vì sao sai | Khắc phục |
| --- | --- | --- |
| `Locale.forLanguageTag("en_US")` | `_` không phải dấu phân tách subtag BCP 47; có thể ra `und` | Dùng `en-US` trong dữ liệu BCP 47 |
| `a.equals(b)` khi chỉ muốn so ngôn ngữ | `equals` xét tất cả thành phần | So sánh `getLanguage()` theo yêu cầu |
| `stripExtensions()` rồi nghĩ đã bỏ script/region | Hàm chỉ bỏ extensions | Xử lý từng thành phần qua getter |
| Bỏ extension trước khi lưu mọi locale | Làm mất thông tin như `nu`, `ca` | Lưu tag đầy đủ với `toLanguageTag()` |
| Lưu `toString()` và parse lại bằng `forLanguageTag` | Không phải định dạng đồng nhất | Lưu BCP 47 `toLanguageTag()` |
| Tự chuyển `_` thành `-` trên mọi chuỗi legacy | Variant/script/extensions có thể bị hiểu sai | Di trú dữ liệu theo schema biết trước |
| Dùng `==` để so hai `Locale` | `==` kiểm tra cùng tham chiếu | Dùng `equals` |
| Xem equality của `Locale` là quy tắc chọn bản dịch | Bằng nhau không phải "cùng tài nguyên" | Xác định chính sách resource/fallback |

## 9. Tự kiểm tra

1. `en-US` có bằng `en-US-u-nu-thai` theo `equals` không? **Không**, vì một bên có extension `nu`.
2. `en-US-u-nu-thai` sau `stripExtensions()` tạo tag gì? **`en-US`**.
3. `sr-Latn-RS` và `sr-Cyrl-RS` có trở nên bằng nhau sau strip không? **Không**, script khác nhau và không bị loại bỏ.
4. Nếu cần lưu locale trong JSON để một hệ thống khác đọc, chọn `toString` hay `toLanguageTag`? **`toLanguageTag`**, lưu trường với hợp đồng BCP 47.
5. `Locale.forLanguageTag(locale.toString())` có khôi phục chắc chắn mọi locale không? **Không**. `toString()` có cú pháp riêng, chẳng hạn `sr_RS_#Latn`.
6. Khi có locale dùng Unicode extension `u-ca-buddhist`, có nên strip extension trước khi cache mọi formatter không? **Không mặc định**; chỉ bỏ nếu nghiệp vụ chứng minh extension không ảnh hưởng kết quả.

## Tài liệu tham khảo

- [Java SE 21 — java.util.Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): `equals`, `hashCode`, `stripExtensions`, `toString`, `toLanguageTag`, `forLanguageTag`.
- [Java SE 21 — Locale.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.Builder.html): `setLanguageTag`, `build`.
- [RFC 5646 — Tags for Identifying Languages](https://www.rfc-editor.org/rfc/rfc5646): cú pháp và ý nghĩa BCP 47.
