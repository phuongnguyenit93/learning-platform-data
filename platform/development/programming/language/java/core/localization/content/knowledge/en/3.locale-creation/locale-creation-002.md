# Locale.forLanguageTag() và toLanguageTag(): chuyển đổi ngôn ngữ BCP 47 trong Java

Trong Java, `Locale` mô tả ngữ cảnh ngôn ngữ/vùng của dữ liệu và giao diện. Khi nhận locale từ cấu hình, URL, hồ sơ người dùng hoặc giao thức khác, ứng dụng thường biểu diễn nó bằng **thẻ ngôn ngữ BCP 47**, ví dụ `vi-VN`, `en-US`, `zh-Hans-CN`. Hai phương thức liên quan trực tiếp là:

- `Locale.forLanguageTag(String languageTag)`: phân tích một thẻ ngôn ngữ BCP 47 thành đối tượng `Locale`.
- `locale.toLanguageTag()`: xuất một `Locale` dưới dạng chuỗi thẻ ngôn ngữ BCP 47 chuẩn hóa theo quy tắc Java.

Cần hiểu cả chiều chuyển đổi, vì **chuỗi thẻ sau khi xuất không nhất thiết giống từng ký tự với chuỗi đã nhập**. Ngoài ra, `forLanguageTag` phân tích theo kiểu khoan dung trước những thành phần sai cú pháp; ứng dụng yêu cầu kiểm tra đầu vào nghiêm ngặt phải chọn cách khác.

## 1. Thẻ BCP 47 biểu diễn những thành phần nào?

BCP 47 là quy ước nhận diện ngôn ngữ và các biến thể liên quan, dùng dấu gạch nối `-` giữa những thành phần (subtag). Trong Java, các phần thường gặp là:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Language | `vi`, `en`, `zh`, `sr` | Ngôn ngữ |
| Script | `Latn`, `Cyrl`, `Hans`, `Hant` | Hệ chữ |
| Region | `VN`, `US`, `CN`, `419` | Vùng lãnh thổ/khu vực |
| Variant | `rozaj` | Biến thể ngôn ngữ |
| Extension | `u-ca-buddhist`, `u-nu-thai` | Tùy chọn bổ sung, ví dụ hệ lịch, hệ chữ số |
| Private use | `x-acme` | Phần mở rộng riêng theo quy ước của hệ thống |

Một thẻ phổ biến có cấu trúc gần đúng:

~~~text
language[-Script][-REGION][-variant...][-extension...][-x-private...]
~~~

Đây là **mô hình đọc nhanh**, không phải ngữ pháp BCP 47 đầy đủ; một số thành phần có quy tắc độ dài, thứ tự, tổ hợp và khả năng lặp riêng. Java nhận thẻ có cú pháp hợp lệ theo các quy tắc được API hỗ trợ.

Ví dụ:

- `vi-VN`: tiếng Việt tại Việt Nam.
- `en-US`: tiếng Anh tại Hoa Kỳ.
- `zh-Hans-CN`: tiếng Trung, chữ giản thể, vùng Trung Quốc.
- `sr-Latn-RS`: tiếng Serbia, chữ Latin, vùng Serbia.
- `th-TH-u-ca-buddhist-nu-thai`: tiếng Thái tại Thái Lan, kèm các tùy chọn Unicode locale về calendar (`ca`) và numbering system (`nu`).

**Không nhầm lẫn:** region `VN` không phải múi giờ `Asia/Ho_Chi_Minh`; script `Latn` không phải charset UTF-8; thông tin `u-ca-...` cũng không tự buộc mọi API định dạng phải thực thi một hệ lịch nào đó. Mỗi thư viện sử dụng các phần thẻ phù hợp với khả năng của nó.

## 2. Từ chuỗi sang Locale với forLanguageTag()

Chữ ký:

~~~java
public static Locale forLanguageTag(String languageTag)
~~~

Cách dùng thông thường:

~~~java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
Locale serbianLatin = Locale.forLanguageTag("sr-Latn-RS");

String language = vietnamese.getLanguage(); // "vi"
String country = vietnamese.getCountry();   // "VN"
String script = serbianLatin.getScript();    // "Latn"
~~~

Các ví dụ trên là đoạn mã đặt trong chương trình đã import `java.util.Locale`. `forLanguageTag` xử lý **một** thẻ BCP 47, không phải một danh sách thẻ hay toàn bộ giá trị header HTTP `Accept-Language`.

### Trích xuất các phần của Locale

Sau khi phân tích, có thể đọc:

- `getLanguage()`: mã ngôn ngữ; ví dụ `"vi"`.
- `getScript()`: mã hệ chữ; ví dụ `"Hans"`.
- `getCountry()`: mã vùng, tên phương thức lịch sử là `Country`; ví dụ `"CN"`.
- `getVariant()`: phần biến thể, nếu có.
- `getExtension(char key)`: nội dung một extension; ví dụ `'u'`.
- `getUnicodeLocaleType(String key)`: giá trị khóa Unicode locale, ví dụ `"buddhist"` ứng với `"ca"`.
- `getUnicodeLocaleKeys()`: tập khóa Unicode đã cấu hình.

Các phương thức trên đọc thông tin nhận diện; chúng không tự chuyển đổi ngôn ngữ của một câu văn. Muốn hiển thị tên ngôn ngữ hoặc vùng theo ngôn ngữ khác, có thể dùng `getDisplayLanguage(displayLocale)` và `getDisplayCountry(displayLocale)`; muốn dịch nội dung, cần tài nguyên hoặc dịch vụ bản địa hóa riêng.

### Phân tích không phụ thuộc chữ hoa/thường

Theo quy tắc của `Locale`, thành phần ngôn ngữ thường được chuẩn hóa thành chữ thường, script thành chữ đầu hoa, region thành chữ hoa, extension thành chữ thường.

~~~java
Locale locale = Locale.forLanguageTag("ZH-hans-cn");
System.out.println(locale.getLanguage()); // zh
System.out.println(locale.getScript());   // Hans
System.out.println(locale.getCountry());  // CN
~~~

Trường hợp thông thường trên cho cùng đối tượng locale về mặt ý nghĩa với thẻ `zh-Hans-CN`.

## 3. Từ Locale về chuỗi với toLanguageTag()

Chữ ký:

~~~java
public String toLanguageTag()
~~~

Ví dụ:

~~~java
Locale locale = Locale.forLanguageTag("vi-vn");
String tag = locale.toLanguageTag();  // "vi-VN"
~~~

Nên dùng `toLanguageTag()` khi cần lưu/trao đổi một thẻ BCP 47. **Không thay bằng `toString()`**: `Locale.toString()` giữ quy ước biểu diễn cũ để tương thích Java, thường có dấu gạch dưới, chẳng hạn `vi_VN`. Trong khi đó, thẻ BCP 47 là `vi-VN`.

| Biểu thức | Giá trị | Dùng khi nào? |
| --- | --- | --- |
| `Locale.forLanguageTag("vi-VN")` | Đối tượng `Locale` | Đọc cấu hình hoặc input BCP 47 |
| `locale.toLanguageTag()` | `"vi-VN"` | Lưu/gửi thẻ chuẩn BCP 47 |
| `locale.toString()` với `vi-VN` | `"vi_VN"` | Hiển thị/debug theo quy ước cũ, không coi là BCP 47 |
| `Locale.ROOT.toLanguageTag()` | `"und"` | Thẻ “undetermined” khi không có ngôn ngữ |

`und` là mã BCP 47 chỉ ngôn ngữ không xác định. `Locale.ROOT` có các trường ngôn ngữ, script, vùng trống nhưng `toLanguageTag()` trả `"und"`; đây không phải exception.

### Chuẩn hóa cú pháp và thứ tự extension

Ví dụ đầu vào có chữ hoa/thường chưa thống nhất và khóa Unicode extension theo thứ tự khác:

~~~java
Locale locale = Locale.forLanguageTag("th-TH-u-nu-thai-ca-buddhist");
String tag = locale.toLanguageTag();
// "th-TH-u-ca-buddhist-nu-thai"
~~~

Hai khóa `ca` và `nu` được đưa về thứ tự chuẩn trong đầu ra của Java. Nếu so sánh chuỗi gốc bằng `equals()`, chúng khác nhau, dù ý nghĩa locale được giữ trong phép chuyển đổi này.

## 4. Thế nào là round trip?

Một **round trip** thường bắt đầu từ chuỗi thẻ, tạo `Locale`, xuất chuỗi, rồi phân tích lại:

~~~java
String input = "ZH-hans-cn";
Locale first = Locale.forLanguageTag(input);
String normalizedTag = first.toLanguageTag();
Locale second = Locale.forLanguageTag(normalizedTag);

boolean sameLocale = first.equals(second); // true với ví dụ này
~~~

Phân biệt hai kiểu “giữ nguyên”:

1. **Giữ nguyên biểu diễn chữ:** `input.equals(normalizedTag)` có thể là `false`, bởi chữ hoa/thường, thứ tự extension hoặc alias đã chuẩn hóa.
2. **Giữ nguyên trạng thái locale có thể biểu diễn hợp lệ:** với thẻ hợp lệ thông thường, `first.equals(second)` là cách kiểm tra hợp lý sau round trip.

Không nên tuyên bố round trip luôn giữ nguyên mọi dữ liệu trong mọi trường hợp. Đặc biệt, một `Locale` tạo bằng constructor cũ với ngôn ngữ, vùng hoặc variant **không hợp cú pháp BCP 47** có thể chứa giá trị không thể xuất lại nguyên vẹn. `toLanguageTag()` sẽ cố tạo thẻ hợp lệ và có thể loại bỏ hoặc chuyển cách biểu diễn của những phần không phù hợp. Trong trường hợp cần lưu **đúng nguyên văn input** của người dùng phục vụ audit, lưu input riêng cùng thẻ đã chuẩn hóa.

### Alias và tương thích

Java có các quy tắc tương thích cho một số mã ngôn ngữ cũ và các thẻ đặc biệt. Chẳng hạn mã `iw`, `ji`, `in` được chuyển sang những mã mới tương ứng `he`, `yi`, `id` khi phân tích. Vì vậy `toLanguageTag()` là **biểu diễn có chuẩn hóa theo API**, không phải thao tác nối chuỗi gốc.

Khi ứng dụng dùng locale làm khóa cache, nên chuẩn hóa đầu vào bằng `Locale` và thống nhất chính sách khóa. Nếu yêu cầu hai cách ghi khác nhau tương đương, tránh dùng nguyên chuỗi người dùng chưa chuẩn hóa làm hai khóa độc lập.

## 5. Điều dễ bỏ sót: forLanguageTag() khoan dung với thẻ sai

`Locale.forLanguageTag()` không phải bộ kiểm tra tính hợp lệ nghiêm ngặt. Theo hợp đồng Java 17, khi gặp subtag **sai cú pháp**, phần sai đầu tiên và các subtag phía sau bị bỏ qua; API không ném `IllformedLocaleException` chỉ vì tình huống này.

Ví dụ có thể kiểm chứng:

~~~java
Locale parsed = Locale.forLanguageTag("en-US-@bad");
System.out.println(parsed.toLanguageTag()); // en-US
~~~

Phần `@bad` không hợp lệ nên bị bỏ. Hệ quả: ứng dụng có thể **vô tình chấp nhận một phần input không đúng** nếu chỉ kiểm tra xem phương thức có trả `Locale` hay không.

Một lỗi khác là dùng dấu gạch dưới:

~~~java
Locale parsed = Locale.forLanguageTag("en_US");
System.out.println(parsed.toLanguageTag()); // und trên Java 17
~~~

`"en_US"` là biểu diễn hay gặp từ `toString()` hoặc cấu hình cũ, **không phải thẻ BCP 47 hợp lệ**. Vì vậy đừng dựa vào `forLanguageTag()` để tự chuyển dấu gạch dưới thành dấu gạch nối. Nếu phải hỗ trợ cấu hình cũ, hãy định nghĩa bước chuyển đổi rõ ràng và kiểm thử, thay vì âm thầm thay mọi ký tự `_` mà không phân tích cấu trúc.

Ngoài ra, `forLanguageTag(null)` gây `NullPointerException`. Input chuỗi rỗng hoặc `und` không nên được ngầm coi là locale thật của người dùng; hãy có chính sách mặc định/phản hồi lỗi riêng khi bài toán bắt buộc phải biết ngôn ngữ.

## 6. Khi cần kiểm tra chặt: Locale.Builder.setLanguageTag()

`Locale.Builder` hỗ trợ kiểm tra **cú pháp** mạnh hơn. Trái với `forLanguageTag`, phương thức `setLanguageTag` ném `IllformedLocaleException` đối với thẻ sai cú pháp (ví dụ subtag chứa `@`).

~~~java
try {
    Locale locale = new Locale.Builder()
            .setLanguageTag("en-US-@bad")
            .build();
} catch (IllformedLocaleException ex) {
    // Từ chối thẻ không đúng cú pháp.
}
~~~

Đoạn trên cần `import java.util.Locale;` và `import java.util.IllformedLocaleException;`. Trong ứng dụng thực, cần xử lý input trống trước; `Locale.Builder.setLanguageTag(null)` hoặc chuỗi rỗng dùng để xóa trạng thái Builder chứ không có nghĩa tự động báo input bị thiếu.

**Giới hạn quan trọng:** `Builder` chủ yếu kiểm tra **well-formed syntax**, không xác nhận chắc chắn mọi mã ngôn ngữ/vùng có được đăng ký, được hệ thống của bạn hỗ trợ hay không. Một thẻ có cú pháp đúng vẫn có thể không có bản dịch, dữ liệu định dạng hoặc ý nghĩa phù hợp nghiệp vụ. Muốn chọn ngôn ngữ phục vụ thật sự, phải kiểm tra thêm danh sách locale được ứng dụng hỗ trợ và có quy tắc fallback.

Một quy trình đầu vào đáng tin cậy:

1. Kiểm tra chuỗi có tồn tại, không rỗng và đáp ứng giới hạn độ dài phù hợp.
2. Dùng `Locale.Builder().setLanguageTag(input).build()` nếu cần từ chối lỗi cú pháp.
3. Lấy `locale.toLanguageTag()` làm thẻ chuẩn hóa dùng nội bộ hoặc lưu trữ.
4. So với danh sách ngôn ngữ/vùng thực sự hỗ trợ; nếu không có, áp dụng fallback được công bố.
5. Khi cần giữ bằng chứng input gốc, lưu bản gốc ở trường khác.

Nếu nguồn đầu vào do hệ thống tin cậy sinh ra và đã được kiểm tra trước, `Locale.forLanguageTag()` thường gọn và phù hợp. Với cấu hình quản trị hoặc dữ liệu người dùng có yêu cầu sai là phải báo lỗi, ưu tiên Builder và kiểm tra nghiệp vụ.

## 7. Ví dụ Java 17+ độc lập: hai chiều, chuẩn hóa và lỗi đầu vào

Tạo tệp **`LanguageTagDemo.java`** với nội dung:

~~~java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class LanguageTagDemo {
    public static void main(String[] args) {
        Locale vietnamese = Locale.forLanguageTag("vi-vn");
        Locale chinese = Locale.forLanguageTag("ZH-hans-cn");
        Locale customized =
                Locale.forLanguageTag("th-TH-u-nu-thai-ca-buddhist");

        System.out.println("Vietnamese: "
                + vietnamese.toLanguageTag());
        System.out.println("Chinese: "
                + chinese.toLanguageTag());
        System.out.println("Script: " + chinese.getScript());
        System.out.println("Calendar: "
                + customized.getUnicodeLocaleType("ca"));
        System.out.println("Numbering: "
                + customized.getUnicodeLocaleType("nu"));
        System.out.println("With extensions: "
                + customized.toLanguageTag());
        System.out.println("Equivalent: "
                + vietnamese.equals(Locale.forLanguageTag("vi-VN")));
        System.out.println("Locale toString: " + vietnamese);
        System.out.println("Malformed lenient: "
                + Locale.forLanguageTag("en-US-@bad").toLanguageTag());
        System.out.println("Wrong separator: "
                + Locale.forLanguageTag("en_US").toLanguageTag());
        System.out.println("Root: " + Locale.ROOT.toLanguageTag());

        try {
            new Locale.Builder()
                    .setLanguageTag("en-US-@bad")
                    .build();
            System.out.println("Builder: accepted");
        } catch (IllformedLocaleException ex) {
            System.out.println("Builder: rejected");
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 LanguageTagDemo.java
java LanguageTagDemo
~~~

Kết quả (đã kiểm tra với mã nguồn biên dịch ở mức tương thích Java 17):

~~~text
Vietnamese: vi-VN
Chinese: zh-Hans-CN
Script: Hans
Calendar: buddhist
Numbering: thai
With extensions: th-TH-u-ca-buddhist-nu-thai
Equivalent: true
Locale toString: vi_VN
Malformed lenient: en-US
Wrong separator: und
Root: und
Builder: rejected
~~~

Phân tích theo từng nhóm:

- `vi-vn` và `ZH-hans-cn` được chuẩn hóa thành `vi-VN` và `zh-Hans-CN`.
- `getScript()` đọc `Hans`; `getUnicodeLocaleType("ca")` và `("nu")` đọc tùy chọn calendar/numbering dưới Unicode extension.
- `toLanguageTag()` sắp xếp các khóa `u` trong thẻ được xuất.
- Hai `Locale` có cùng giá trị sau chuẩn hóa có thể `equals()` bằng `true` ngay cả khi chữ trong thẻ input khác nhau.
- `toString()` biểu diễn `vi_VN` theo dạng cũ, khác `toLanguageTag()`.
- Parser khoan dung giữ `en-US` khi gặp `@bad`; Builder từ chối lỗi ấy.
- `en_US` không được hiểu như `en-US` trong parser BCP 47; `Locale.ROOT` xuất `und`.

Chương trình không phụ thuộc locale mặc định, múi giờ hay encoding của đầu ra để quyết định các chuỗi in trên, ngoài việc console cần hiển thị ký tự ASCII thông thường.

## 8. Ứng dụng trong cấu hình và giao tiếp hệ thống

### Lưu lựa chọn ngôn ngữ trong hồ sơ người dùng

Ví dụ người dùng chọn tiếng Việt:

~~~java
String requestedTag = "vi-vn";
Locale locale = new Locale.Builder()
        .setLanguageTag(requestedTag)
        .build();

String canonicalTag = locale.toLanguageTag(); // "vi-VN"
~~~

Đây là **đoạn mã minh họa** trong một lớp/phương thức đã import `java.util.Locale`. Khi lưu cấu hình, dùng `canonicalTag` để giữ một cách ghi nhất quán, nhưng cần thêm bước kiểm tra xem ứng dụng có hỗ trợ `vi-VN` không. `toLanguageTag()` không tự cấp cho ứng dụng một bộ bản dịch.

### Đầu vào HTTP Accept-Language không phải một language tag

Ví dụ header:

~~~http
Accept-Language: vi-VN,vi;q=0.9,en-US;q=0.7
~~~

Đây là **danh sách các lựa chọn có trọng số ưu tiên**, không phải một thẻ duy nhất. Không truyền nguyên chuỗi này vào `Locale.forLanguageTag()` và kỳ vọng Java tự thương lượng ngôn ngữ. Có thể dùng `Locale.LanguageRange.parse(header)` rồi `Locale.lookup(...)` / `Locale.filter(...)` với danh sách locale được ứng dụng hỗ trợ, hoặc dùng cơ chế locale resolution của framework.

Ví dụ minh họa ý tưởng trong một phương thức có import `java.util.List` và `java.util.Locale`:

~~~java
List<Locale> supported = List.of(
        Locale.forLanguageTag("vi-VN"),
        Locale.forLanguageTag("en-US"));
List<Locale.LanguageRange> priorities =
        Locale.LanguageRange.parse("vi-VN,vi;q=0.9,en-US;q=0.7");
Locale selected = Locale.lookup(priorities, supported);
// Có thể null nếu không có thẻ phù hợp: tự chọn fallback.
~~~

Thứ tự và trọng số ảnh hưởng kết quả thương lượng; khi hệ thống thực sự chỉ hỗ trợ hai ngôn ngữ, nên kiểm thử cả tình huống không tìm thấy kết quả, fallback và trường hợp tag chung (`vi`) so với tag vùng (`vi-VN`).

### Không đồng nhất locale với định dạng thực tế

Thẻ `th-TH-u-ca-buddhist` bộc lộ sở thích về kiểu lịch, nhưng việc API cụ thể có dùng extension này hay không phụ thuộc vào API và nhà cung cấp dữ liệu địa phương hóa. `LocalDate` thông thường vẫn là ngày theo lịch ISO. Cũng tương tự, `vi-VN` không tự chọn `ZoneId` Việt Nam, charset UTF-8 hoặc phông chữ hiển thị. Mỗi yêu cầu kỹ thuật cần cấu hình riêng.

### Đồng nhất đầu vào giữa API, cơ sở dữ liệu và cache

Một chiến lược ổn định là chấp nhận tag hợp lệ, chuẩn hóa bằng `toLanguageTag()`, kiểm tra danh sách hỗ trợ, rồi dùng giá trị đã chuẩn hóa nhất quán trong hồ sơ, cache và URL. Tuy nhiên, **chuẩn hóa BCP 47 không phải cùng khái niệm với thương lượng ngôn ngữ**: yêu cầu `en-GB` không đương nhiên đồng nghĩa nội dung `en-US`; hai locale có thể chia sẻ ngôn ngữ nhưng khác tập quán định dạng. Quyết định fallback thuộc nghiệp vụ.

## 9. Những lỗi phổ biến

| Lỗi | Vì sao sai | Cách phòng tránh |
| --- | --- | --- |
| Dùng `Locale.toString()` để lưu language tag | Trả dạng cũ như `en_US` | Dùng `toLanguageTag()` |
| Dùng `forLanguageTag("en_US")` | Dấu `_` không thuộc cú pháp BCP 47 | Dùng `"en-US"`; có kế hoạch migrate config cũ |
| So sánh nguyên chuỗi `"vi-vn"` và `"vi-VN"` | Khác chữ hoa/thường nhưng tương đương sau parse | Chuẩn hóa trước khi dùng làm khóa |
| Giả định parser ném lỗi với mọi thẻ sai | `forLanguageTag` bỏ phần sai và phần sau | Builder + xác thực nghiệp vụ |
| Cho rằng Builder kiểm tra ngôn ngữ có thật | Chủ yếu kiểm tra đúng cú pháp | Kiểm tra danh mục hỗ trợ/registry khi cần |
| Gửi toàn bộ `Accept-Language` vào `forLanguageTag` | Header là danh sách có trọng số | Dùng `LanguageRange` hoặc framework |
| Tin rằng `Locale` tự dịch văn bản | Locale chỉ mô tả ngữ cảnh | Dùng message bundles hoặc bản dịch |
| Tin rằng `toLanguageTag` luôn giữ nguyên input byte-for-byte | Có chuẩn hóa và quy tắc tương thích | Lưu input gốc riêng nếu cần audit |
| Đặt `Locale.setDefault` trong từng request | Trạng thái mặc định là toàn tiến trình | Truyền `Locale` trực tiếp tới formatter |

## 10. Bài tập và câu hỏi tự kiểm tra

**Bài 1.** Giải thích ý nghĩa từng phần của `sr-Latn-RS`. Khi chạy `Locale.forLanguageTag(...).getScript()`, dự kiến nhận gì?

**Đáp án:** `sr` là tiếng Serbia, `Latn` là hệ chữ Latin, `RS` là vùng Serbia; `getScript()` trả `"Latn"`.

**Bài 2.** Vì sao `Locale.forLanguageTag("en-US-@bad")` vẫn có thể trả một `Locale` có language `en` và region `US`?

**Đáp án:** Parser khoan dung bỏ subtag đầu tiên sai cú pháp và phần còn lại. Nó không bảo đảm kiểm tra nghiêm ngặt toàn bộ chuỗi.

**Bài 3.** Một API nhận `"ZH-hans-cn"`, rồi trả `"zh-Hans-CN"`. Có nhất thiết là API làm mất locale không?

**Đáp án:** Không. Đây là chuẩn hóa chữ hoa/thường theo thành phần. Cần so sánh trạng thái locale đã phân tích, không đòi hỏi chuỗi input giữ nguyên từng ký tự.

**Bài 4.** Khi nào dùng `new Locale.Builder().setLanguageTag(value).build()` thay vì `Locale.forLanguageTag(value)`?

**Đáp án:** Khi đầu vào phải được từ chối nếu sai cú pháp. Vẫn cần kiểm tra danh sách locale được ứng dụng hỗ trợ và lựa chọn fallback.

**Bài 5.** Có nên dùng `locale.toString()` gửi cho một hệ thống đòi thẻ IETF BCP 47?

**Đáp án:** Không. Phải dùng `locale.toLanguageTag()`, ví dụ `vi-VN` thay cho `vi_VN`.

## Tham khảo chính thức

- [Java SE 17 — java.util.Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): hợp đồng `forLanguageTag`, `toLanguageTag`, cấu trúc thẻ và quy tắc tương thích.
- [Java SE 17 — Locale.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Builder.html): `setLanguageTag` và `IllformedLocaleException`.
- [RFC 5646 — Tags for Identifying Languages](https://www.rfc-editor.org/rfc/rfc5646): nền tảng cú pháp BCP 47.

**Ghi nhớ:** `forLanguageTag` chuyển **thẻ BCP 47 → Locale** và có thể bỏ phần sai cú pháp; `toLanguageTag` chuyển **Locale → thẻ BCP 47 đã chuẩn hóa**. Muốn ràng buộc nghiêm ngặt, dùng `Locale.Builder` kèm chính sách hỗ trợ locale và fallback của ứng dụng.
