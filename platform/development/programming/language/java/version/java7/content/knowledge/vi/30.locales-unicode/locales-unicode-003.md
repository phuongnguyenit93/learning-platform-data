# Chuyển đổi Locale với forLanguageTag và toLanguageTag (Java 17+)

## 1. Mục tiêu

Trong ứng dụng đa ngôn ngữ, ta thường nhận một chuỗi biểu thị **ngôn ngữ, hệ chữ viết, vùng lãnh thổ và các tùy chọn địa phương hóa**, chẳng hạn `vi-VN`, `en-US` hoặc `zh-Hant-TW`. Java dùng `java.util.Locale` để mang những thông tin đó vào các API xử lý văn bản, số, ngày giờ, tài nguyên giao diện.

Hai phương thức cần nắm vững:

- `Locale.forLanguageTag(String languageTag)`: **phân tích thẻ ngôn ngữ IETF BCP 47** rồi tạo đối tượng `Locale`.
- `locale.toLanguageTag()`: **biểu diễn một `Locale` thành chuỗi thẻ ngôn ngữ BCP 47 hợp cú pháp**.

Ví dụ ngắn:

~~~java
import java.util.Locale;

Locale locale = Locale.forLanguageTag("vi-VN");
String tag = locale.toLanguageTag();

System.out.println(locale.getLanguage()); // vi
System.out.println(locale.getCountry());  // VN
System.out.println(tag);                  // vi-VN
~~~

Đoạn trên là **fragment phải đặt trong một method Java**. Đây là API có từ Java 7 và **vẫn được hỗ trợ trong Java 17+**; ví dụ đầy đủ có thể biên dịch và chạy ở phần 7.

Sau bài học, bạn có thể đọc/ghi BCP 47 đúng cách, hiểu việc chuẩn hóa chữ hoa–chữ thường, chọn giữa phân tích dễ dãi và kiểm tra cú pháp nghiêm ngặt, xử lý Unicode locale extensions và tránh các giả định sai về round-trip.

## 2. Thẻ ngôn ngữ BCP 47 là gì?

**BCP 47** là định dạng thẻ ngôn ngữ dùng dấu **gạch ngang `-`** để phân tách các thành phần (*subtag*). Trong các trường hợp thường gặp:

~~~text
language[-Script][-REGION][-variant...][-extension...]
   vi       (không có script)  VN
   zh             Hant         TW
   en             (không)      US      -u-ca-gregory
~~~

Các thành phần quan trọng:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Language | Mã ngôn ngữ, thường là ISO 639 | `vi`, `en`, `ja`, `zh` |
| Script | Hệ chữ viết (ISO 15924), có 4 chữ cái | `Latn`, `Cyrl`, `Hant`, `Hans` |
| Region | Quốc gia/vùng (2 chữ cái hoặc mã vùng số theo chuẩn) | `VN`, `US`, `TW`, `419` |
| Variant | Biến thể ngôn ngữ theo quy tắc BCP 47 | `de-CH-1901` |
| Extension | Tùy chọn mở rộng, thường dùng Unicode extension `u` | `en-US-u-nu-thai` |
| Private use | Phần do các bên tự quy ước, tiền tố `x` | `en-x-company` |

Ví dụ:

- `vi-VN`: tiếng Việt tại Việt Nam.
- `en-US`: tiếng Anh tại Hoa Kỳ.
- `zh-Hant-TW`: tiếng Trung, chữ Hán phồn thể, vùng Đài Loan.
- `sr-Latn-RS`: tiếng Serbia viết chữ Latin, vùng Serbia.
- `en-US-u-ca-gregory-nu-latn`: tiếng Anh–Mỹ kèm tùy chọn lịch Gregorian và chữ số Latin ở dạng Unicode locale extension.

**Đừng nhầm định dạng BCP 47 với `Locale.toString()`**: `toString()` có biểu diễn kỹ thuật riêng của Java, thường dùng dấu gạch dưới `_`. Đối với URL, API, cấu hình hay dữ liệu cần trao đổi, nên dùng **`toLanguageTag()`** thay vì `toString()`.

Một thẻ ngôn ngữ **không mô tả bảng mã ký tự của chuỗi văn bản**. `vi-VN` không đồng nghĩa với “UTF-8”; encoding, chuẩn hóa Unicode (`NFC/NFD`) và lựa chọn `Locale` là các vấn đề khác nhau.

## 3. `Locale.forLanguageTag(String)`: chuỗi → Locale

### Cú pháp và ý nghĩa

~~~java
public static Locale forLanguageTag(String languageTag)
~~~

Ví dụ:

~~~java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale traditionalChinese =
        Locale.forLanguageTag("zh-Hant-TW");

System.out.println(vietnamese.getLanguage());   // vi
System.out.println(vietnamese.getCountry());    // VN
System.out.println(traditionalChinese.getScript());  // Hant
~~~

Đây là các fragment minh họa trong method. `getLanguage()` trả mã ngôn ngữ; `getScript()` là mã hệ chữ viết; `getCountry()` là vùng lãnh thổ (tên method là `getCountry` vì lịch sử API, nhưng thẻ BCP 47 có thể dùng mã vùng số).

`forLanguageTag` giải mã thẻ theo các quy tắc của `Locale`, chuẩn hóa một số trường về dạng thông dụng:

- Language thành **chữ thường**, ví dụ `EN` → `en`.
- Script thành **chữ cái đầu viết hoa**, ví dụ `hANT` → `Hant`.
- Region thành **chữ hoa** với mã hai chữ cái, ví dụ `us` → `US`.
- Extensions chuẩn hóa về chữ thường và theo thứ tự được định nghĩa khi biểu diễn.
- Variant có các quy tắc và trường hợp tương thích riêng; không nên hứa rằng tất cả chuỗi sẽ được bảo toàn nguyên dạng.

Vì vậy:

~~~java
Locale loc = Locale.forLanguageTag("ZH-hant-tw");
System.out.println(loc.toLanguageTag()); // zh-Hant-TW
~~~

Hai biểu diễn khác chữ hoa–thường có thể tương đương về thông tin locale. Nếu cần so sánh locale, hãy so sánh **đối tượng/thuộc tính được chuẩn hóa**, không dùng so sánh chuỗi thẻ đầu vào có phân biệt hoa–thường.

### `forLanguageTag` có phân tích *lenient*

Điểm thường gây lỗi: **`forLanguageTag` không từ chối mọi thẻ sai cú pháp**. Theo tài liệu Java SE 17, khi gặp subtag không hợp lệ, phương thức **bỏ qua subtag sai đầu tiên và tất cả phần theo sau nó**.

~~~java
Locale parsed = Locale.forLanguageTag("en-US-@");
System.out.println(parsed.toLanguageTag()); // en-US
~~~

Thẻ gốc có `@` sai cú pháp, nhưng phần `en-US` phía trước vẫn được giữ lại. Nếu đầu vào đến từ HTTP/API và bạn cần **phát hiện lỗi chính xác**, không nên dùng `forLanguageTag` như một bộ xác thực nghiêm ngặt.

Trường hợp sai dấu phân cách:

~~~java
Locale wrong = Locale.forLanguageTag("en_US");
System.out.println(wrong.toLanguageTag()); // und
~~~

`en_US` không phải thẻ BCP 47 dùng dấu `-`. Ở ví dụ này, Java không phân tích được phần ngôn ngữ hợp lệ và biểu diễn kết quả dưới dạng `und` (*undetermined*). **Đừng tự động thay mọi dấu `_` thành `-` nếu dữ liệu không có hợp đồng rõ ràng**; hãy thống nhất định dạng BCP 47 ngay ở ranh giới hệ thống.

### Cách xử lý `null`

~~~java
Locale.forLanguageTag(null); // ném NullPointerException
~~~

Dòng trên chỉ minh họa hành vi lỗi, không nên chạy trực tiếp khi không có `try/catch`. Ứng dụng cần tự quy định chính sách với đầu vào `null`, chuỗi rỗng, tag không xác định hoặc không được hỗ trợ. Không âm thầm chọn locale mặc định cho mọi đầu vào sai nếu điều đó khiến hệ thống đổi ngôn ngữ ngoài mong muốn.

## 4. `locale.toLanguageTag()`: Locale → chuỗi

### Cú pháp và ý nghĩa

~~~java
public String toLanguageTag()
~~~

Ví dụ:

~~~java
Locale locale = new Locale.Builder()
        .setLanguage("sr")
        .setScript("Latn")
        .setRegion("RS")
        .build();

System.out.println(locale.toLanguageTag()); // sr-Latn-RS
~~~

`Locale.Builder` là API công khai hiện hành để tạo `Locale` có các thành phần BCP 47, bao gồm script và extensions.

**Khác với `toString()`**, `toLanguageTag()` trả một thẻ BCP 47 hợp cú pháp phù hợp cho trao đổi dữ liệu. Nó có thể **chuẩn hóa, chuyển đổi hoặc bỏ qua** thành phần không thể biểu diễn theo quy tắc BCP 47 (đặc biệt nếu `Locale` đã được xây từ dữ liệu cũ không hợp cú pháp).

Một số kết quả quan trọng:

| Đối tượng hoặc đầu vào | Kết quả `toLanguageTag()` | Điều cần hiểu |
| --- | --- | --- |
| `Locale.forLanguageTag("vi-VN")` | `vi-VN` | Tag cơ bản |
| `Locale.forLanguageTag("EN-us")` | `en-US` | Chuẩn hóa chữ hoa/thường |
| `Locale.forLanguageTag("ZH-hant-tw")` | `zh-Hant-TW` | Chuẩn hóa language/script/region |
| `new Locale.Builder().setLanguage("sr").setScript("Latn").setRegion("RS").build()` | `sr-Latn-RS` | Xây locale từ các trường rõ ràng |
| `Locale.ROOT` | `und` | Locale gốc không chỉ định ngôn ngữ |
| `Locale.forLanguageTag("en_US")` | `und` | Dấu `_` làm đầu vào BCP 47 sai cú pháp trong ví dụ này |

`und` là subtag BCP 47 có nghĩa **không xác định ngôn ngữ**. Khi `Locale` có language rỗng (ví dụ `Locale.ROOT`), `toLanguageTag()` tạo ra `und`. Ngược lại, `Locale.forLanguageTag("und")` ánh xạ mã ngôn ngữ về chuỗi rỗng. Điều đó **không phải lỗi encoding**.

### Biểu diễn được không có nghĩa là mã đã đăng ký

Javadoc chỉ hứa `toLanguageTag` tạo ra chuỗi **well-formed** theo cú pháp BCP 47; không hứa mọi subtag đã đăng ký trong IANA registry. Một hệ thống có thể tạo mã trông hợp cú pháp nhưng không đại diện ngôn ngữ/vùng đã đăng ký hoặc được dịch vụ địa phương hóa hỗ trợ.

Tách ba khái niệm:

1. **Syntactically well-formed**: đúng cấu trúc ký tự, dấu phân cách, độ dài của subtag.
2. **Registered/recognized**: ngôn ngữ, script, region, variant thực sự được đăng ký/nhận diện.
3. **Supported by service**: thư viện định dạng và bộ tài nguyên có dữ liệu cần thiết cho locale đó.

`forLanguageTag` và `Locale.Builder` không thay thế bộ danh sách locale mà ứng dụng của bạn thực sự hỗ trợ.

## 5. Chuẩn hóa và round-trip: không phải lúc nào cũng đối xứng

Hai cách chuyển đổi thường được ghép lại:

~~~java
Locale parsed = Locale.forLanguageTag(inputTag);
String normalizedTag = parsed.toLanguageTag();

Locale again = Locale.forLanguageTag(normalizedTag);
~~~

Với thẻ thông dụng hợp cú pháp, quá trình trên thường mang tính ổn định:

~~~java
Locale a = Locale.forLanguageTag("EN-us");
Locale b = Locale.forLanguageTag(a.toLanguageTag());

System.out.println(a.toLanguageTag()); // en-US
System.out.println(a.equals(b));       // true
~~~

Tuy nhiên, **Java SE 17 nói rõ rằng không bảo đảm `toLanguageTag()` và `forLanguageTag()` round-trip cho mọi trường hợp**. Có những chuỗi đầu vào chưa hợp cú pháp bị cắt đuôi; có những locale cũ có variant không thể biểu diễn nguyên dạng; có những quy tắc chuyển đổi phục vụ tương thích.

Vì thế, phải phân biệt:

- **String round-trip:** `inputTag.equals(parsed.toLanguageTag())` **không được bảo đảm**. Ngay `EN-us` thành `en-US` đã khác chuỗi.
- **Locale object round-trip:** `Locale.forLanguageTag(locale.toLanguageTag()).equals(locale)` cũng **không phải bảo đảm tuyệt đối** với mọi nguồn `Locale`.
- **Use-case thông thường:** dùng tag đã chuẩn hóa để lưu/trao đổi sau khi xác định input đúng dạng và thuộc danh sách được hỗ trợ.

Nếu hệ thống cần lưu chính xác từng ký tự chuỗi người dùng đã nhập vì mục đích kiểm toán, **lưu cả bản gốc riêng**. Không dùng `toLanguageTag()` như hàm bảo toàn byte.

## 6. Unicode locale extensions: ví dụ lịch và chữ số

BCP 47 cho phép các extension. `Locale` hỗ trợ Unicode locale extension bắt đầu bằng `u`; một số **key/type** thường gặp:

| Key | Ý nghĩa thường dùng | Ví dụ |
| --- | --- | --- |
| `ca` | Loại lịch | `ca-buddhist`, `ca-gregory` |
| `nu` | Hệ chữ số | `nu-thai`, `nu-latn` |
| `co` | Quy tắc sắp xếp/collation | `co-phonebk` |
| `hc` | Chu kỳ giờ | `hc-h12`, `hc-h23` |

Tag có extension:

~~~text
zh-Hant-TW-u-ca-buddhist-nu-thai
│   │   │  │  │            └── Chữ số Thai
│   │   │  │  └── Kiểu lịch Buddhist
│   │   │  └── Unicode locale extension
│   │   └── Vùng TW
│   └── Script Hant
└── Language zh
~~~

Truy cập từng trường bằng API có kiểu:

~~~java
Locale detailed = Locale.forLanguageTag(
        "ZH-hant-tw-u-nu-thai-ca-buddhist");

System.out.println(detailed.toLanguageTag());
// zh-Hant-TW-u-ca-buddhist-nu-thai

System.out.println(detailed.getUnicodeLocaleType("ca"));
// buddhist

System.out.println(detailed.getUnicodeLocaleType("nu"));
// thai
~~~

Hai key trong chuỗi nhập có thứ tự `nu` rồi `ca`, nhưng khi xuất ra, Java sắp xếp key theo thứ tự chuẩn `ca` rồi `nu`. Đây là ví dụ cho thấy **cùng ý nghĩa nhưng khác biểu diễn chuỗi**.

Các API liên quan:

- `getExtension(Locale.UNICODE_LOCALE_EXTENSION)`: trả chuỗi nội dung extension `u` (hoặc `null` nếu vắng).
- `getUnicodeLocaleKeys()`: trả tập key Unicode locale đang có.
- `getUnicodeLocaleType("ca")`: trả type tương ứng hoặc `null` nếu không có key.
- `Locale.Builder.setUnicodeLocaleKeyword("nu", "latn")`: xây/sửa một key Unicode locale có kiểm tra cú pháp.

**Lưu ý:** việc một tag mang `u-ca-*` hoặc `u-nu-*` **không bảo đảm** mọi formatter, provider hoặc runtime sẽ áp dụng chính xác tùy chọn đó. Hành vi thực tế phụ thuộc API địa phương hóa và dữ liệu có sẵn trong JDK, thư viện hoặc ứng dụng.

## 7. Chương trình Java 17+ chạy độc lập

Ví dụ bên dưới chứng minh: chuyển đổi hai chiều, chuẩn hóa chữ hoa–thường, script/region, Unicode locale extensions, xử lý dữ liệu sai cú pháp và trường hợp `Locale.ROOT`. Không cần dependency ngoài JDK.

Tạo file **`LocaleTagDemo.java`**:

~~~java
import java.util.Locale;
import java.util.IllformedLocaleException;

public class LocaleTagDemo {
    public static void main(String[] args) {
        Locale vietnamese = Locale.forLanguageTag("vi-VN");
        System.out.println("vi: " + vietnamese.toLanguageTag());

        Locale complex = Locale.forLanguageTag(
                "ZH-hant-tw-u-nu-thai-ca-buddhist");
        System.out.println("normalized: " + complex.toLanguageTag());
        System.out.println("language: " + complex.getLanguage());
        System.out.println("script: " + complex.getScript());
        System.out.println("region: " + complex.getCountry());
        System.out.println(
                "calendar: " + complex.getUnicodeLocaleType("ca"));
        System.out.println(
                "numbers: " + complex.getUnicodeLocaleType("nu"));

        Locale fromBuilder = new Locale.Builder()
                .setLanguage("sr")
                .setScript("Latn")
                .setRegion("RS")
                .build();
        System.out.println("builder: " + fromBuilder.toLanguageTag());

        // forLanguageTag bỏ đoạn sai cú pháp và phần theo sau.
        Locale lenient = Locale.forLanguageTag("en-US-@");
        System.out.println("lenient: " + lenient.toLanguageTag());

        // Builder có thể báo lỗi nếu tag sai cú pháp.
        try {
            new Locale.Builder().setLanguageTag("en-US-@");
            System.out.println("strict: accepted");
        } catch (IllformedLocaleException expected) {
            System.out.println("strict: rejected");
        }

        System.out.println("root: " + Locale.ROOT.toLanguageTag());

        // Trường hợp cụ thể này round-trip thành công;
        // không suy ra mọi Locale đều như vậy.
        System.out.println("round-trip: " +
                Locale.forLanguageTag(complex.toLanguageTag())
                        .equals(complex));

        // BCP 47 dùng dấu -, không phải dấu _.
        System.out.println("underscore: " +
                Locale.forLanguageTag("en_US").toLanguageTag());
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+** tại thư mục chứa file:

~~~bash
javac --release 17 LocaleTagDemo.java
java LocaleTagDemo
~~~

`stdout`:

~~~text
vi: vi-VN
normalized: zh-Hant-TW-u-ca-buddhist-nu-thai
language: zh
script: Hant
region: TW
calendar: buddhist
numbers: thai
builder: sr-Latn-RS
lenient: en-US
strict: rejected
root: und
round-trip: true
underscore: und
~~~

Giải thích:

1. `vi-VN` được chuyển vào `Locale` và xuất ra cùng dạng BCP 47.
2. `ZH-hant-tw-u-nu-thai-ca-buddhist` được chuẩn hóa về chữ hoa–thường và sắp key extension, không đơn thuần sao chép chuỗi gốc.
3. `getLanguage`, `getScript`, `getCountry` cho kết quả `zh`, `Hant`, `TW`.
4. `getUnicodeLocaleType` đọc đúng `ca=buddhist` và `nu=thai`.
5. `Locale.Builder` tạo `sr-Latn-RS` từ các trường riêng.
6. `forLanguageTag` chấp nhận phần hợp cú pháp của `en-US-@` và cho kết quả `en-US`; `Builder` từ chối cùng chuỗi và ném `IllformedLocaleException`.
7. `Locale.ROOT` không có ngôn ngữ cụ thể nên được biểu diễn thành `und`.
8. Round-trip với `complex` ở đây trả `true`. Chương trình **không** kiểm chứng hay tuyên bố round-trip luôn đúng cho mọi `Locale`.
9. Chuỗi `en_US` sai định dạng BCP 47 trong ví dụ này nên nhận `und`.

Output ở đây gồm các thông tin parse/tag của Java API, không phải tên ngôn ngữ hay kết quả định dạng số/ngày có thể phụ thuộc dữ liệu locale của từng runtime.

## 8. Khi cần kiểm tra cú pháp nghiêm ngặt: Locale.Builder

Nếu API của bạn nhận thẻ từ người dùng và **cần từ chối** thẻ sai cú pháp thay vì lặng lẽ cắt bỏ, dùng:

~~~java
import java.util.IllformedLocaleException;
import java.util.Locale;

static Locale parseStrictLanguageTag(String rawTag) {
    if (rawTag == null || rawTag.isBlank()) {
        throw new IllegalArgumentException("Thiếu language tag");
    }

    try {
        return new Locale.Builder()
                .setLanguageTag(rawTag)
                .build();
    } catch (IllformedLocaleException ex) {
        throw new IllegalArgumentException(
                "Language tag sai cú pháp: " + rawTag, ex);
    }
}
~~~

Đây là **một phương thức có thể đặt trong class ứng dụng**, không phải chương trình Java độc lập. `String.isBlank()` có trong Java 17. Khác `forLanguageTag`, `Locale.Builder.setLanguageTag` thông thường ném `IllformedLocaleException` đối với thẻ sai cú pháp.

Cũng có thể tạo locale từ từng trường bằng `Builder`:

~~~java
Locale serbian = new Locale.Builder()
        .setLanguage("sr")
        .setScript("Latn")
        .setRegion("RS")
        .build();
~~~

**Quan trọng:** `Builder` xác minh cú pháp, không khẳng định tất cả subtag đã đăng ký trong IANA Language Subtag Registry hoặc mọi locale thực sự được ứng dụng hỗ trợ. Nếu UI chỉ hỗ trợ `vi-VN`, `en-US`, `ja-JP` thì **cần thêm danh sách cho phép riêng** sau bước parse.

Ví dụ thiết kế khi nhận locale từ request:

~~~java
// Phần bên trong endpoint đã có method parseStrictLanguageTag.
Locale requested = parseStrictLanguageTag(rawTag);

if (!SUPPORTED_LOCALES.contains(requested)) {
    throw new IllegalArgumentException("Locale chưa được hỗ trợ");
}
~~~

Đây chỉ là **fragment minh họa**; `rawTag` và `SUPPORTED_LOCALES` do ứng dụng cung cấp. Nên định nghĩa `SUPPORTED_LOCALES` là một tập `Locale` được quản lý cố định, không lấy từ tất cả locale trên máy. Đừng dùng cách parse nghiêm ngặt như một cơ chế phân quyền bảo mật: locale là dữ liệu cấu hình/cách trình bày, còn quyền truy cập phải được kiểm tra riêng.

### Bảng lựa chọn parser

| Nhu cầu | Cách phù hợp | Vì sao |
| --- | --- | --- |
| Đọc thẻ BCP 47 hợp lệ từ nguồn tin cậy | `Locale.forLanguageTag(tag)` | Đơn giản, trả một `Locale` |
| Chuẩn hóa thẻ thành dạng trao đổi | `Locale.forLanguageTag(tag).toLanguageTag()` | Nhận chuỗi chuẩn hóa với giả định đầu vào phù hợp |
| Từ chối cú pháp sai thay vì tự cắt phần đuôi | `new Locale.Builder().setLanguageTag(tag).build()` | Báo `IllformedLocaleException` |
| Xây locale từ language/script/region/extensions | `Locale.Builder` | Cấu trúc rõ ràng, có kiểm tra cú pháp |
| Giới hạn các ngôn ngữ sản phẩm hỗ trợ | Parse rồi kiểm tra tập locale được cho phép | Cú pháp hợp lệ không đồng nghĩa ứng dụng có bản dịch |
| Phân tích nguyên `Accept-Language` có trọng số `q` | `Locale.LanguageRange.parse(...)` và cơ chế chọn phù hợp | Header là một **danh sách**, không phải một language tag đơn |
| Cần giữ chuỗi đầu vào chính xác để audit | Lưu bản gốc riêng | Chuẩn hóa có thể đổi chuỗi |

## 9. Liên hệ với ứng dụng đa ngôn ngữ và Unicode

### 9.1. Truyền Locale vào API địa phương hóa

Sau khi có `Locale`, ta truyền nó tới API cần thực hiện định dạng/hiển thị:

~~~java
import java.text.NumberFormat;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

Locale locale = Locale.forLanguageTag("vi-VN");

NumberFormat numberFormat = NumberFormat.getNumberInstance(locale);
String amount = numberFormat.format(1234567.89);

DateTimeFormatter dateFormatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                .withLocale(locale);
~~~

Đây là **fragment minh họa** (phải đặt trong method), không có stdout được cam kết: kết quả định dạng và tài nguyên có thể thay đổi theo JDK/provider/CLDR và lựa chọn ứng dụng. Lưu ý `DateTimeFormatter` hoạt động trên các kiểu ngày/giờ Java Time thích hợp, không phải tự tạo múi giờ từ `Locale`. **Locale và time zone là hai khái niệm riêng**.

Trong ứng dụng web, tốt hơn nên truyền `Locale` theo từng request hoặc context thay vì gọi `Locale.setDefault(...)` cho mỗi người dùng: default locale là trạng thái dùng chung trong JVM và dễ gây rò yêu cầu giữa các luồng.

### 9.2. `Accept-Language` không phải một tag đơn

Header HTTP có thể như:

~~~text
Accept-Language: vi-VN, en-US;q=0.8, en;q=0.7
~~~

Chuỗi phần sau dấu hai chấm **không phải một thẻ BCP 47 đơn**. Đừng gọi:

~~~java
// Sai ý nghĩa: header chứa danh sách có trọng số.
Locale.fromLanguageTag("vi-VN, en-US;q=0.8");
~~~

Dòng trên là **phản ví dụ về ý định API**, không phải code chạy: trong Java 17 **không có** `Locale.fromLanguageTag`. API chính xác là `Locale.forLanguageTag` nhưng **cũng không được truyền cả header vào đó**. Khi xử lý danh sách ưu tiên, dùng `Locale.LanguageRange.parse(...)` để phân tích phần giá trị header, rồi `Locale.lookup(...)` hoặc `Locale.filter(...)` để chọn locale từ tập hỗ trợ. Cơ chế HTTP framework cũng có thể làm phần này.

### 9.3. Locale không thay thế Unicode normalization

`Locale.forLanguageTag("vi-VN")` chỉ chọn thông tin locale; nó **không chuyển** ký tự tiếng Việt sang dạng Unicode NFC, không sửa nội dung UTF-8 và không đổi code point của một chuỗi bất kỳ.

Nếu bài toán là so sánh Unicode có các dạng tổ hợp khác nhau, hãy dùng API phù hợp như `java.text.Normalizer` theo yêu cầu xử lý văn bản; nếu bài toán là in số/ngày/chuỗi theo văn hóa địa phương, dùng `Locale` như tham số cho formatter. Tránh trộn hai việc này.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `en_US` thành `und` | Dùng dấu `_`, không phải BCP 47 `-` | Chuẩn hóa giao thức đầu vào sang `en-US` từ nguồn tin cậy |
| `EN-us` được in thành `en-US` | `Locale` chuẩn hóa case | So sánh ý nghĩa thay vì đòi giữ nguyên ký tự |
| `forLanguageTag("en-US-@")` trả `en-US` | Parser bỏ phần sai và phía sau | Dùng `Locale.Builder.setLanguageTag` nếu cần từ chối cú pháp sai |
| `Builder` chấp nhận một mã lạ về mặt ý nghĩa | Builder kiểm tra cú pháp, không kiểm tra registry hoặc gói bản dịch | Thêm kiểm tra tập locale được ứng dụng hỗ trợ |
| `toLanguageTag()` không bằng chuỗi gốc | Normalization, extension sorting, chuyển đổi tương thích | Lưu raw input riêng nếu cần giữ chính xác |
| `Locale.ROOT.toLanguageTag()` trả `und` | Không xác định language | Xử lý `und`/empty language như một trạng thái được quy định |
| Bị mất extension khi dùng cách biểu diễn khác | `toString()` không phải format trao đổi BCP 47 | Lưu/trao đổi qua `toLanguageTag()` và parse bằng `forLanguageTag` |
| Áp `ca-buddhist` nhưng output formatter không như mong đợi | Provider/API không hỗ trợ đầy đủ tùy chọn | Test trên JDK/provider thực tế và chọn formatter thích hợp |
| Thay `Locale.setDefault` trong từng request | Default dùng chung cho toàn JVM | Truyền `Locale` tường minh cho request/formatter |
| `NullPointerException` khi parse | Gọi `forLanguageTag(null)` | Kiểm tra null ở biên hệ thống |
| Dùng toàn bộ `Accept-Language` làm một thẻ | Header là danh sách ngôn ngữ và `q` | Dùng `Locale.LanguageRange` hoặc cơ chế HTTP framework |
| Nghĩ tag cho biết UTF-8/UTF-16 | Locale và encoding là hai khái niệm khác | Xử lý charset/Unicode normalization riêng |

## 11. Checklist triển khai đúng

1. Quy định dữ liệu trao đổi dùng **BCP 47**, dấu `-`, ví dụ `vi-VN`, không dùng chuỗi debug `Locale.toString()`.
2. Chọn `Locale.forLanguageTag(tag)` khi chỉ cần parse từ nguồn đáng tin và có thể chấp nhận quy tắc lenient.
3. Chọn `Locale.Builder.setLanguageTag(tag)` khi cần từ chối thẻ sai cú pháp; xử lý `IllformedLocaleException` rõ ràng.
4. Không đồng nhất **well-formed** với **registered** hoặc **có bản dịch/tài nguyên**; kiểm tra danh sách locale hỗ trợ của sản phẩm.
5. Trước khi so sánh/lưu, hiểu rằng `toLanguageTag()` có thể chuẩn hóa case và sắp xếp extension.
6. Không cam kết round-trip tuyệt đối cho mọi đối tượng `Locale` hay mọi chuỗi nhập.
7. Sử dụng `getLanguage`/`getScript`/`getCountry` và `getUnicodeLocaleType` nếu logic cần từng thành phần, thay vì tự cắt chuỗi bằng vị trí dấu `-`.
8. Không đưa cả HTTP `Accept-Language` (với dấu phẩy/`q`) vào `forLanguageTag`; dùng parser dành cho language ranges.
9. Truyền `Locale` tường minh cho formatter trong từng request; không đổi global default để phục vụ từng người dùng.
10. Tách việc chọn locale khỏi mã hóa ký tự, Unicode normalization và thiết lập múi giờ.
11. Kiểm thử với JDK, provider và danh sách ngôn ngữ thực tế được ứng dụng hỗ trợ.

**Ghi nhớ:**

~~~text
BCP 47 String --Locale.forLanguageTag--> Locale
Locale         --locale.toLanguageTag-->  BCP 47 String

Ví dụ:
"ZH-hant-tw" -> Locale -> "zh-Hant-TW"
"en-US-@"    -> Locale -> "en-US"      (parser lenient!)
Locale.ROOT  ------------> "und"
~~~

`forLanguageTag` và `toLanguageTag` là cặp API tiện lợi để **diễn giải và biểu diễn thẻ ngôn ngữ**, nhưng **không phải bộ xác thực toàn diện và không phải phép bảo toàn nguyên vẹn mọi chuỗi/Locale**.

## Tài liệu tham khảo Java hiện hành

- [Java SE 17 — java.util.Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): `forLanguageTag`, `toLanguageTag`, cấu trúc locale, Unicode extensions, quy tắc chuẩn hóa và giới hạn round-trip.
- [Java SE 17 — Locale.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html): tạo locale well-formed, `setLanguageTag`, `setLanguage`, `setScript`, `setRegion` và `setUnicodeLocaleKeyword`.
- [Java SE 17 — Locale.LanguageRange](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.LanguageRange.html): xử lý danh sách ưu tiên ngôn ngữ có trọng số.
- [IETF RFC 5646 — Tags for Identifying Languages](https://www.rfc-editor.org/rfc/rfc5646): quy tắc chuẩn BCP 47.
