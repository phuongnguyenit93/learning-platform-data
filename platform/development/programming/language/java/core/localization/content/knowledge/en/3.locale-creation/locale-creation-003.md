# Locale.Builder và kiểm tra tính hợp lệ của cú pháp trong Java

## Mục tiêu

Khi cần tạo một `Locale` từ những phần như ngôn ngữ, hệ chữ viết, vùng và phần mở rộng, `java.util.Locale.Builder` cho phép khai báo rõ từng thành phần và phát hiện **lỗi cú pháp** ngay lúc xây dựng. Bài học này tập trung vào cách dùng Builder đúng, cách đọc language tag theo BCP 47, ý nghĩa và giới hạn của việc kiểm tra hợp lệ, cùng cách xử lý đầu vào không đáng tin cậy.

Sau bài học, bạn có thể:

- Tạo `Locale` bằng `Locale.Builder` từ các thành phần riêng hoặc một language tag.
- Hiểu các phương thức `setLanguage`, `setScript`, `setRegion`, `setVariant` và các phương thức extension.
- Giải thích khi nào `IllformedLocaleException` được ném, cách xử lý lỗi, và vì sao `Locale.forLanguageTag` có hành vi khác.
- Phân biệt **hợp lệ về cú pháp** với **mã ngôn ngữ có ý nghĩa**, **locale được JDK hỗ trợ** và **locale ứng dụng cho phép**.
- Viết bộ kiểm tra đầu vào có chủ đích trước khi sử dụng locale trong một hệ thống đa ngôn ngữ.

## 1. Vị trí của Builder trong mô hình Locale

`Locale` là định danh mô tả những quy ước ngôn ngữ/vùng mà một tác vụ muốn sử dụng. Nó không chứa sẵn nội dung dịch, dữ liệu định dạng ngày hay quy định múi giờ. `Locale` là đối tượng **bất biến**: sau khi tạo, các thành phần của nó không bị sửa trực tiếp.

`Locale.Builder` là công cụ **có thể thay đổi trạng thái** để chuẩn bị những thành phần ấy:

```text
Language / Script / Region / Variant / Extensions
                    |
                    v
          Locale.Builder (mutable)
                    |
                 build()
                    v
             Locale (immutable)
```

Bạn có thể gọi nhiều setter trên cùng Builder, sau đó gọi `build()` để nhận một `Locale`. Thay đổi Builder và gọi `build()` lần nữa cho ra một `Locale` mới; đối tượng đã tạo trước đó giữ nguyên giá trị.

Builder cũng giúp phát hiện các thành phần sai **dạng cú pháp** ngay khi gọi setter hoặc khi đặt cả language tag. Ngoại lệ `IllformedLocaleException` biểu thị chuỗi hoặc thành phần không đúng quy tắc cú pháp của Locale/BCP 47. Cần lưu ý: Builder kiểm tra **hình thức biểu diễn**, không kiểm chứng rằng ứng dụng đã có bản dịch hay JDK có quy tắc định dạng đầy đủ cho locale đó.

## 2. Các thành phần được kiểm tra

Language tag thông dụng dùng cú pháp BCP 47 với dấu gạch nối `-`, chẳng hạn `vi-VN`, `en-US`, `sr-Latn-RS`, `zh-Hant-TW`.

| Thành phần | Ý nghĩa | Dạng thông dụng được Builder chấp nhận | Ví dụ |
| --- | --- | --- | --- |
| Language | Mã ngôn ngữ | 2–8 chữ cái ASCII | `vi`, `en`, `sr` |
| Script | Hệ chữ | Đúng 4 chữ cái ASCII | `Latn`, `Cyrl`, `Hant` |
| Region | Quốc gia/vùng | 2 chữ cái ASCII hoặc 3 chữ số | `VN`, `US`, `419` |
| Variant | Biến thể | Subtag 5–8 ký tự chữ/số hoặc 4 ký tự bắt đầu bằng chữ số; có thể có nhiều subtag | `POSIX` |
| Extensions | Thông tin bổ sung | Theo cấu trúc extension của BCP 47, gồm key và chuỗi subtag phù hợp | `u-nu-latn` |

Đây là **quy tắc về dạng chuỗi**, không phải lời hứa rằng mọi mã có dạng hợp lệ đều đã được đăng ký, được dịch hoặc được mọi provider hỗ trợ. Ví dụ, một language code gồm các chữ cái có thể vượt qua bước kiểm tra hình thức nhưng vẫn không thuộc danh sách locale được sản phẩm triển khai.

Builder chuẩn hóa cách viết các thành phần trong định danh xuất ra. `toLanguageTag()` là cách lấy language tag phù hợp khi lưu cấu hình/giao tiếp; không nên sử dụng chuỗi `toString()` theo kiểu có dấu gạch dưới làm đầu vào BCP 47.

### Các phương thức chính

| Phương thức | Tác dụng |
| --- | --- |
| `setLanguage("vi")` | Đặt mã ngôn ngữ |
| `setScript("Latn")` | Đặt hệ chữ |
| `setRegion("VN")` | Đặt vùng |
| `setVariant("POSIX")` | Đặt biến thể |
| `setExtension('u', "nu-latn")` | Đặt extension theo singleton và giá trị |
| `setUnicodeLocaleKeyword("nu", "latn")` | Đặt một Unicode locale keyword, ở đây là hệ chữ số |
| `setUnicodeLocaleAttribute("...")` | Thêm thuộc tính Unicode locale hợp lệ |
| `setLanguageTag("sr-Latn-RS")` | Đọc và đặt toàn bộ Builder từ language tag |
| `setLocale(existingLocale)` | Đặt Builder theo một `Locale` hiện có |
| `clearExtensions()` | Xóa các extension, giữ các thành phần cơ bản |
| `clear()` | Xóa trạng thái Builder về rỗng |
| `build()` | Tạo một `Locale` bất biến |

`setLanguageTag(...)` và `setLocale(...)` là các thao tác **thiết lập lại nội dung Builder theo đầu vào**; đừng coi chúng là phép bổ sung một trường vào trạng thái cũ. Các setter riêng cho ngôn ngữ/script/vùng phù hợp hơn khi muốn thay từng phần.

Các setter kiểm tra và chuẩn hóa phần đầu vào theo quy tắc tương ứng. Chẳng hạn, script `"Latin"` có năm chữ cái nên không hợp lệ cho `setScript`; region `"USA"` có ba chữ cái nên không hợp lệ cho `setRegion`, trong khi mã vùng gồm ba **chữ số** như `"419"` đúng về dạng.

## 3. Ví dụ Java 17+ chạy độc lập

Ví dụ sau kết hợp xây dựng các thành phần tường minh, Unicode locale keyword và kiểm tra language tag. Đồng thời nó minh họa sự khác biệt giữa Builder kiểm tra chặt và `Locale.forLanguageTag` đọc linh hoạt.

Lưu thành tệp `LocaleBuilderDemo.java`:

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class LocaleBuilderDemo {

    private static void check(String tag) {
        try {
            Locale locale = new Locale.Builder()
                    .setLanguageTag(tag)
                    .build();

            System.out.println(tag + " => " + locale.toLanguageTag());
        } catch (IllformedLocaleException ex) {
            System.out.println(tag + " => INVALID");
        }
    }

    public static void main(String[] args) {
        Locale serbianLatin = new Locale.Builder()
                .setLanguage("sr")
                .setScript("Latn")
                .setRegion("RS")
                .build();

        Locale englishLatinDigits = new Locale.Builder()
                .setLanguage("en")
                .setRegion("US")
                .setUnicodeLocaleKeyword("nu", "latn")
                .build();

        System.out.println(serbianLatin.toLanguageTag());
        System.out.println(englishLatinDigits.toLanguageTag());

        check("vi-VN");
        check("en-US-@");

        Locale flexible = Locale.forLanguageTag("en-US-@");
        System.out.println(flexible.toLanguageTag());
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 LocaleBuilderDemo.java
java LocaleBuilderDemo
```

Stdout:

```text
sr-Latn-RS
en-US-u-nu-latn
vi-VN => vi-VN
en-US-@ => INVALID
en-US
```

Phân tích:

1. `setLanguage("sr")`, `setScript("Latn")`, `setRegion("RS")` kết hợp thành `sr-Latn-RS`. Các trường vẫn riêng biệt trong `Locale`; phần ngôn ngữ không bao gồm `-RS`.
2. `setUnicodeLocaleKeyword("nu", "latn")` tạo Unicode extension `u-nu-latn`. Nó **mô tả yêu cầu** dùng hệ chữ số Latin; API định dạng cụ thể quyết định có áp dụng keyword này hay không.
3. `setLanguageTag("vi-VN")` được Builder chấp nhận vì đúng cú pháp.
4. Dấu `@` không hợp lệ trong language tag `en-US-@`, nên `setLanguageTag` ném `IllformedLocaleException` và nhánh `catch` in `INVALID`.
5. `Locale.forLanguageTag("en-US-@")` không ném ngoại lệ tương tự mà phân tích phần hợp lệ ở đầu, trả về locale với tag `en-US`. Vì vậy **không được dùng `forLanguageTag` một mình làm hàm xác thực cú pháp nghiêm ngặt**.

Hai cách tạo đối tượng trả lời các nhu cầu khác nhau: Builder phù hợp khi cần báo đầu vào sai; `forLanguageTag` phù hợp khi chấp nhận cách phân tích linh hoạt. Chúng không có chung hợp đồng lỗi đầu vào.

## 4. IllformedLocaleException xuất hiện khi nào?

`IllformedLocaleException` là ngoại lệ **không cần khai báo trong `throws`**. Nó có thể phát sinh ngay tại một setter khi giá trị không đúng dạng, chứ không nhất thiết đợi `build()`.

Ví dụ các trường hợp sai cú pháp:

```java
new Locale.Builder().setLanguage("v");
new Locale.Builder().setScript("Latin");
new Locale.Builder().setRegion("USA");
new Locale.Builder().setLanguageTag("en_US");
```

Đây là **các biểu thức minh họa lỗi**, không phải chương trình chạy độc lập. Mỗi dòng được đặt độc lập sẽ ném `IllformedLocaleException` cho giá trị đã đưa vào:

- `"v"` là mã ngôn ngữ chỉ có một chữ cái.
- `"Latin"` có năm chữ cái trong khi mã script gồm bốn.
- `"USA"` là ba chữ cái trong khi mã vùng được phép là hai chữ cái hoặc ba chữ số.
- `"en_US"` dùng dấu gạch dưới của kiểu biểu diễn cũ, không phải dấu `-` trong language tag BCP 47.

Khi xây dựng các thành phần bằng chuỗi đến từ bên ngoài, hãy đặt cả chuỗi gọi setter và `build()` trong `try/catch`. Thí dụ:

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class ValidateLocale {
    public static void main(String[] args) {
        String suppliedTag = "en_US";

        try {
            Locale result = new Locale.Builder()
                    .setLanguageTag(suppliedTag)
                    .build();
            System.out.println("ACCEPTED: " + result.toLanguageTag());
        } catch (IllformedLocaleException ex) {
            System.out.println("INVALID TAG");
        }
    }
}
```

Lưu là `ValidateLocale.java` rồi chạy `javac ValidateLocale.java` và `java ValidateLocale`. Stdout là:

```text
INVALID TAG
```

`IllformedLocaleException#getErrorIndex()` có thể hỗ trợ chỉ ra vị trí lỗi trong một đầu vào không hợp lệ. Tuy nhiên, **đừng tự dựa vào con số cố định** trong thông điệp lỗi cho mọi setter và mọi môi trường; hãy giữ thông báo cho người dùng ở mức ứng dụng, chẳng hạn “language tag không hợp lệ”.

Không nên bắt `Exception` rộng rồi âm thầm dùng locale mặc định: cách làm đó che mất lỗi dữ liệu. Nên xử lý riêng lỗi cú pháp và áp dụng fallback theo chính sách sản phẩm một cách rõ ràng.

## 5. Builder so với Locale.forLanguageTag

Hai cách dưới đây cùng có thể xây dựng `Locale` từ một tag BCP 47 hợp lệ:

```java
Locale strict = new Locale.Builder()
        .setLanguageTag("zh-Hant-TW")
        .build();

Locale flexible = Locale.forLanguageTag("zh-Hant-TW");
```

Đây là đoạn minh họa trong một phương thức. Hai đối tượng đều biểu thị `zh-Hant-TW`. Khác biệt nổi bật nằm ở **đầu vào sai cú pháp**:

| Tình huống | `new Locale.Builder().setLanguageTag(tag).build()` | `Locale.forLanguageTag(tag)` |
| --- | --- | --- |
| Tag hợp lệ `vi-VN` | Chấp nhận, tạo locale | Chấp nhận, tạo locale |
| Tag có phần dư sai `en-US-@` | Ném `IllformedLocaleException` | Có thể giữ phần prefix hợp lệ `en-US` |
| Ứng dụng chưa hỗ trợ ngôn ngữ | Vẫn có thể tạo locale nếu cú pháp hợp lệ | Vẫn có thể tạo locale nếu cú pháp hợp lệ |
| Cần từ chối chuỗi sai cú pháp | Phù hợp | Không đủ nếu dùng riêng |

Điểm cần nhớ: **không có exception** từ `forLanguageTag` **không có nghĩa đầu vào nguyên bản hợp lệ**. Việc lấy `locale.toLanguageTag()` rồi thấy kết quả đẹp cũng không chứng minh dữ liệu đã được kiểm tra, vì đầu vào có thể bị lược phần sai.

Trong một số trường hợp, `setLanguageTag` có thể chuẩn hóa hoặc xử lý các language tag đã được quy định đặc biệt trong BCP 47; vì thế kiểm tra cú pháp không nhất thiết có nghĩa `input.equals(locale.toLanguageTag())`. Không nên bắt buộc hai chuỗi giống hệt nhau như một quy tắc xác thực phổ quát: khác biệt về chữ hoa/thường, cách biểu diễn chuẩn và canonicalization là hợp lệ.

## 6. Tạo từ các thành phần thay vì tự ghép chuỗi

Giả sử người dùng chọn ngôn ngữ `zh`, hệ chữ `Hant` và vùng `TW` trong ba trường khác nhau. Đừng ghép chuỗi rồi cố suy luận lại khi xuất hiện lỗi; Builder cho phép kiểm tra chính phần nào sai:

```java
Locale locale = new Locale.Builder()
        .setLanguage(languageCode)
        .setScript(scriptCode)
        .setRegion(regionCode)
        .build();
```

Đây là **đoạn minh họa trong phương thức** với ba biến đầu vào đã có: `languageCode`, `scriptCode`, `regionCode`. Có thể bắt `IllformedLocaleException` và báo trường nhập tương ứng, hoặc kiểm tra từng trường riêng để trả lỗi chính xác hơn.

Các trường có thể để trống khi không áp dụng. Chẳng hạn, locale `en` chỉ cần language; không nên tự lấp `US` nếu người dùng chưa chọn vùng. Ngược lại, khi một API cụ thể cần quy ước vùng, ứng dụng phải giải quyết vùng theo chính sách riêng thay vì ngầm giả định mọi người dùng nói tiếng Anh đều ở Hoa Kỳ.

### Builder có trạng thái; kết quả build là bất biến

```java
Locale.Builder builder = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US");

Locale first = builder.build();
builder.setRegion("GB");
Locale second = builder.build();

System.out.println(first.toLanguageTag());   // en-US
System.out.println(second.toLanguageTag());  // en-GB
```

Đoạn minh họa này đặt trong một phương thức; hai chuỗi `// en-US` và `// en-GB` là kết quả tương ứng. Sửa Builder không làm thay đổi `first`. Vì Builder là đối tượng có thể sửa, tránh chia sẻ cùng một Builder cho nhiều luồng để xây dựng locale đồng thời. Có thể chia sẻ `Locale` đã tạo vì bản thân nó bất biến.

Nếu tái sử dụng Builder, cần hiểu những phương thức dọn trạng thái:

- `clearExtensions()` chỉ bỏ extension và thuộc tính/keyword Unicode; các phần language, script, region, variant vẫn giữ.
- `clear()` đặt Builder trở lại trạng thái rỗng.
- `setLanguageTag(...)` thiết lập toàn bộ thành phần theo tag mới; không giả định nó chỉ thay một phần.

Nếu không cần tái sử dụng, cách đơn giản là khởi tạo một Builder mới cho mỗi định danh.

## 7. Kiểm tra extension đúng cách

Ngoài language/script/region/variant, BCP 47 còn có extension. Unicode locale extension thường bắt đầu bằng `u`, ví dụ:

```text
en-US-u-nu-latn
        |  |  |
        u  nu latn
        |  |  +-- loại hệ chữ số
        |  +----- Unicode keyword "numbering system"
        +-------- Unicode locale extension
```

Với Builder, đặt keyword bằng API chuyên dụng giúp tránh tự ghép sai cú pháp:

```java
Locale locale = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("nu", "latn")
        .build();

System.out.println(locale.toLanguageTag()); // en-US-u-nu-latn
System.out.println(locale.getUnicodeLocaleType("nu")); // latn
```

Đây là đoạn minh họa trong một phương thức. `setUnicodeLocaleKeyword` yêu cầu key và type đúng dạng. Builder có thể ném `IllformedLocaleException` khi cấu trúc không hợp lệ. Nếu người dùng chọn nhiều tùy chọn Unicode, các keyword được biểu diễn trong extension `u` của cùng locale. Việc sắp xếp chuẩn khi xuất tag do Java thực hiện; không cần tự ghép bằng chuỗi.

Đừng đánh đồng **extension đúng cú pháp** với **API thực sự hỗ trợ extension**. Ví dụ, yêu cầu hệ chữ số `nu-latn` không tự thay đổi mọi phép tính hay mọi định dạng; mỗi formatter/provider quyết định cách xử lý. Các keyword mang yêu cầu về quy ước, không phải chức năng xử lý đa ngôn ngữ đã được cài đặt sẵn cho mọi thư viện.

Các extension tùy ý qua `setExtension` đòi cấu trúc hợp lệ riêng. Khi có API chuyên dụng như `setUnicodeLocaleKeyword`, ưu tiên API đó vì thể hiện ý định rõ hơn.

## 8. Cú pháp hợp lệ khác khả năng sử dụng

Giả sử `new Locale.Builder().setLanguageTag(tag).build()` thành công. Kết luận hợp lệ duy nhất ở bước này là **tag có dạng cú pháp được Builder chấp nhận**.

Có ít nhất bốn lớp kiểm tra khác nhau:

1. **Cú pháp (well-formed):** các phần và cách ghép language tag đúng BCP 47. Builder có thể kiểm tra lớp này.
2. **Ý nghĩa/đăng ký mã:** mã có thực sự là ngôn ngữ, hệ chữ, vùng hoặc biến thể đã được quy định phù hợp cho bài toán hay không. Builder không phải cơ sở dữ liệu xác minh mọi mã đã đăng ký và mọi tổ hợp có ý nghĩa.
3. **Dữ liệu được JDK/API hỗ trợ:** có dữ liệu định dạng, so sánh, tên hiển thị… phù hợp hay không. Kết quả phụ thuộc provider và phiên bản dữ liệu. API có thể fallback.
4. **Chính sách ứng dụng:** sản phẩm có tài nguyên dịch, luật định dạng riêng và quyền chọn ngôn ngữ đó hay không. Đây là quyết định thuộc ứng dụng.

Ví dụ sản phẩm chỉ có `vi` và `en-US` thì tag `de-DE` có thể hoàn toàn hợp lệ về cú pháp nhưng **không nằm trong tập ngôn ngữ giao diện được hỗ trợ**. Cần từ chối hoặc resolve về một lựa chọn được công bố rõ ràng, không mặc nhiên coi `build()` thành công là đã có bản dịch tiếng Đức.

Ngoài ra, `Locale` không xác định múi giờ (`ZoneId`), không xác nhận người dùng đang ở quốc gia nào và không quyết định đơn vị tiền tệ của giao dịch. Kiểm tra Builder không thể dùng để xác thực các thông tin ấy.

## 9. Quy trình kiểm tra một language tag từ bên ngoài

Giả sử HTTP API nhận thuộc tính cấu hình `"locale": "vi-VN"`. Quy trình an toàn, dễ kiểm thử:

1. **Xác định hợp đồng đầu vào.** Nếu API yêu cầu một BCP 47 language tag duy nhất, hãy cấm giá trị rỗng, chuỗi quá dài hoặc chuỗi nhiều phần tử ngay ở lớp request theo quy định sản phẩm. Chọn rõ có chấp nhận khoảng trắng ngoài cùng hay không; tránh tự “sửa” chuỗi một cách âm thầm.
2. **Kiểm tra cú pháp bằng Builder.** Gọi `setLanguageTag(value)` trong `try/catch (IllformedLocaleException)`; báo lỗi đầu vào nếu cú pháp không hợp lệ.
3. **Áp dụng danh sách hỗ trợ.** So khớp locale đã phân tích với tập locale mà ứng dụng cung cấp, ví dụ `vi` và `en-US`. Nếu có cơ chế fallback, ghi rõ trường hợp nào được chuyển sang locale gần nhất.
4. **Giữ cả yêu cầu và kết quả khi cần.** `requestedLocale` có thể khác `resolvedLocale` nếu sản phẩm có fallback. Không ghi đè yêu cầu gốc mà làm mất dấu nguyên nhân.
5. **Truyền locale vào API cần dùng.** Ví dụ `ResourceBundle`, `NumberFormat`, `DateTimeFormatter` hoặc `Collator`. Không gọi `Locale.setDefault` cho từng request trong ứng dụng đa người dùng.

Có thể viết hàm kiểm tra cú pháp với hợp đồng rõ ràng:

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

public final class LocaleInput {
    private LocaleInput() {}

    public static Locale parseStrict(String rawTag) {
        if (rawTag == null || rawTag.isBlank()) {
            throw new IllegalArgumentException("Locale tag is required");
        }
        if (rawTag.length() > 128) {
            throw new IllegalArgumentException("Locale tag is too long");
        }

        try {
            return new Locale.Builder()
                    .setLanguageTag(rawTag)
                    .build();
        } catch (IllformedLocaleException ex) {
            throw new IllegalArgumentException("Malformed locale tag", ex);
        }
    }
}
```

Đây là lớp tiện ích có thể biên dịch độc lập thành `LocaleInput.java`, nhưng không có `main` để chạy trực tiếp. Giới hạn 128 ký tự ở đây chỉ là **ví dụ về chính sách của một ứng dụng**, không phải giới hạn chuẩn của BCP 47 hay `Locale.Builder`. Hàm chỉ trả `Locale` sau khi kiểm tra cú pháp và quy định đầu vào tối thiểu; **chưa kiểm tra whitelist, tài nguyên dịch hoặc mức hỗ trợ của JDK**. Lớp gọi phải thực hiện bước đó nếu cần.

Lưu ý `rawTag.isBlank()` loại bỏ chuỗi chỉ gồm khoảng trắng, nhưng không tự xóa các khoảng trắng đầu/cuối của chuỗi khác. Nếu hợp đồng đầu vào yêu cầu tag nguyên dạng, cách xử lý này nhất quán: chuỗi `" vi-VN "` sẽ bị bộ phân tích từ chối thay vì tự động sửa. Nếu muốn cho phép trim, cần ghi thành chính sách rõ ràng, test cả input trước và sau chuẩn hóa.

### Đừng dùng setLanguageTag để phân tích Accept-Language trực tiếp

Header HTTP `Accept-Language` có thể chứa danh sách ưu tiên như `vi-VN,vi;q=0.9,en-US;q=0.7`. Đây **không phải một language tag**. `Locale.Builder.setLanguageTag(header)` không phải bộ phân tích header có weight `q`.

Java có `Locale.LanguageRange.parse(...)` và các phương thức `Locale.lookup(...)`, `Locale.filter(...)` để hỗ trợ đàm phán locale theo danh sách ưu tiên. Sau bước đàm phán, ứng dụng vẫn cần dùng danh sách locale thực tế đã phát hành và quy tắc fallback của sản phẩm.

## 10. Lỗi phổ biến và cách tránh

| Lỗi | Vì sao sai | Cách làm phù hợp |
| --- | --- | --- |
| Dùng `new Locale.Builder().setLanguage("en-US")` | `setLanguage` nhận riêng mã ngôn ngữ, không nhận cả tag | Dùng `setLanguageTag("en-US")` hoặc `setLanguage("en").setRegion("US")` |
| Đưa `en_US` vào `setLanguageTag` | Dấu gạch dưới không phải dấu phân cách BCP 47 | Dùng `en-US` nếu dữ liệu nguồn thật sự biểu thị tiếng Anh/Hoa Kỳ |
| Dùng `forLanguageTag` để validate chặt | API có thể lược phần không hợp lệ mà không ném lỗi | Dùng Builder hoặc một bộ kiểm tra có hợp đồng phù hợp |
| Nghĩ `build()` thành công nghĩa là đã có bản dịch | Builder chỉ kiểm tra cú pháp thành phần | Kiểm tra danh sách locale/tài nguyên sản phẩm hỗ trợ |
| Nghĩ `getAvailableLocales()` là whitelist của ứng dụng | Tập locale JDK/provider và tập ngôn ngữ sản phẩm khác nhau | Duy trì tập hỗ trợ ứng dụng độc lập |
| Dùng `toString()` làm BCP 47 tag | Biểu diễn kiểu cũ có thể dùng dấu gạch dưới | Dùng `toLanguageTag()` |
| Dùng một Builder dùng chung giữa các request | Builder có trạng thái thay đổi và không thiết kế để chia sẻ đồng thời | Tạo Builder cục bộ theo tác vụ |
| Xây cả tag bằng nối chuỗi tùy tiện | Dễ đặt sai thứ tự/định dạng các phần | Dùng setter tương ứng hoặc `setLanguageTag` cho tag có sẵn |
| Lấy `getErrorIndex()` làm logic nghiệp vụ chính | Không phải mọi lỗi đều thích hợp để dựa vào chỉ số cố định | Dùng ngoại lệ làm tín hiệu từ chối và cung cấp thông báo rõ ràng |
| Thay `Locale.setDefault` theo user | Default JVM là trạng thái dùng chung | Truyền `Locale` tường minh qua request context |
| Dùng locale để suy múi giờ hay loại tiền đơn hàng | Đó là những khái niệm độc lập | Lấy `ZoneId`/`Currency` từ cấu hình hoặc dữ liệu nghiệp vụ |

## 11. Bài tập tự kiểm tra

**Tình huống A.** Bạn nhận `"sr-Latn-RS"`. Hãy tạo locale bằng hai cách: `new Locale.Builder().setLanguageTag(...)` và các setter riêng `setLanguage`/`setScript`/`setRegion`. Kiểm tra cả hai `toLanguageTag()` đều trả `sr-Latn-RS`.

**Tình huống B.** Một khách hàng gửi `"en_US"`. Hãy thử Builder và bắt `IllformedLocaleException`. Nếu sản phẩm nhận tag BCP 47, phản hồi sai cú pháp thay vì lặng lẽ coi dấu `_` là `-`. Nếu đang chuyển đổi một định dạng legacy đã được tài liệu hóa, hãy xây một lớp chuyển đổi tường minh và kiểm thử riêng.

**Tình huống C.** Builder chấp nhận `"de-DE"` nhưng ứng dụng chỉ có tài nguyên `"vi"` và `"en-US"`. Đây là lỗi **hỗ trợ ngôn ngữ**, không phải lỗi cú pháp; quyết định reject hay fallback phải nằm ở lớp chính sách ứng dụng.

**Tình huống D.** Hãy tạo `en-US-u-nu-latn` bằng `setUnicodeLocaleKeyword("nu", "latn")`, rồi đọc lại bằng `getUnicodeLocaleType("nu")`. Kết quả là `latn`. Giải thích vì sao giá trị đó không tự buộc mọi API Java đổi hệ chữ số.

## 12. Kết luận kiến thức

`Locale.Builder` là công cụ đúng khi cần **kiến tạo một Locale từ thành phần rõ ràng hoặc xác thực cú pháp BCP 47 theo cách chặt chẽ**. Các setter kiểm tra dạng giá trị và có thể ném `IllformedLocaleException` ngay trong lúc đặt dữ liệu; `build()` tạo một `Locale` bất biến. Ngược lại, `Locale.forLanguageTag` phân tích linh hoạt và có thể giữ lại phần đầu hợp lệ của một tag sai, nên không đủ để validate đầu vào nghiêm ngặt.

Kiểm tra cú pháp luôn chỉ là **bước đầu**: một locale hợp lệ chưa nói gì chắc chắn về mã được đăng ký, dữ liệu provider hỗ trợ, bản dịch hiện có hay lựa chọn được sản phẩm cho phép. Tách rõ những lớp kiểm tra này giúp ứng dụng đa ngôn ngữ phản hồi lỗi dễ hiểu, có fallback nhất quán và tránh lẫn yêu cầu văn hóa với dữ liệu thực tế.
