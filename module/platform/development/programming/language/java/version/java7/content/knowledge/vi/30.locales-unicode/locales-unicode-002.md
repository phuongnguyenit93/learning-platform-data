# Locale và Unicode trong Java: Tạo Locale bằng Locale.Builder

## 1. Khi nào cần tự tạo một Locale?

Một ứng dụng Java phục vụ người dùng ở nhiều quốc gia thường phải chọn **ngôn ngữ**, **vùng địa lý**, đôi khi cả **hệ chữ viết** và những **tùy chọn địa phương hóa** như lịch hoặc hệ chữ số. Ví dụ cùng một ứng dụng có thể nhận các yêu cầu:

- Giao diện tiếng Việt dành cho Việt Nam: `vi-VN`.
- Tiếng Trung phồn thể tại Đài Loan: `zh-Hant-TW`.
- Tiếng Tây Ban Nha cho khu vực Mỹ Latinh: `es-419`.
- Tiếng Thái tại Thái Lan với yêu cầu dùng lịch Phật giáo và hệ số Thái: `th-TH-u-ca-buddhist-nu-thai`.

Các chuỗi trên là **language tags** theo hệ quy ước **IETF BCP 47**. Khi ứng dụng xử lý chúng như các giá trị `String` tùy ý, dễ gặp các lỗi như viết nhầm dấu phân cách, nhập một region không đúng cú pháp, mất script trong quá trình chuyển đổi hoặc giả định rằng một tag hợp lệ chắc chắn được thư viện format hỗ trợ đầy đủ.

`java.util.Locale.Builder` giải quyết phần **xây dựng và kiểm tra tính đúng cú pháp của Locale**. Bạn có thể cấu hình từng thành phần bằng setter có kiểu, hoặc cung cấp nguyên một language tag; khi gọi `build()` sẽ nhận một `Locale` bất biến.

```java
import java.util.Locale;

Locale vietnam = new Locale.Builder()
        .setLanguage("vi")
        .setRegion("VN")
        .build();
```

Kết quả `vietnam.toLanguageTag()` là `"vi-VN"`.

**Ý nghĩa chính:** `Locale.Builder` là công cụ tạo **giá trị Locale well-formed** theo các quy tắc ngôn ngữ/tag. Nó **không** phải bộ dịch giao diện, không phải công cụ chuẩn hóa toàn bộ Unicode text và không đảm bảo mọi provider đều có dữ liệu format cho mọi tổ hợp tag hợp lệ.

`Locale.Builder` xuất hiện từ **Java 7** và vẫn là API hiện hành trong các JDK mới. Những ví dụ được kiểm thử bằng **JDK 17**, sử dụng các phương thức không bị deprecated. Bài chỉ tập trung vào những kiến thức còn giá trị trong ứng dụng Java hiện nay.

### Sau bài học, bạn có thể

1. Hiểu `language`, `script`, `region`, `variant`, extensions và cấu trúc BCP 47.
2. Xây Locale bằng chuỗi setter `setLanguage`/`setScript`/`setRegion`/`setVariant`.
3. Xây Locale từ toàn bộ language tag bằng `setLanguageTag`.
4. Sử dụng `setUnicodeLocaleKeyword`, `addUnicodeLocaleAttribute` và `setExtension`.
5. Phân biệt `clear()`, `clearExtensions()`, `setLocale` và thao tác xóa từng trường.
6. Phân biệt kiểm tra **well-formed syntax** với kiểm tra **ngữ nghĩa/khả năng hỗ trợ**.
7. Xử lý `IllformedLocaleException` và so sánh parser strict với `Locale.forLanguageTag`.
8. Hiểu `Locale` immutable, `Builder` mutable/reusable, cách normalize case và serialize.
9. Áp dụng Locale tường minh vào formatting mà không lệ thuộc `Locale.setDefault`.
10. Viết unit tests ổn định trên nhiều JDK, tránh assert text localized phụ thuộc dữ liệu CLDR.

## 2. Locale biểu diễn những gì?

`Locale` là một đối tượng định danh các quy tắc/ngữ cảnh địa phương hóa; các thành phần thường gặp:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Language | `vi`, `en`, `zh`, `th` | Ngôn ngữ; thường là mã ISO 639 |
| Script | `Latn`, `Hans`, `Hant` | Hệ chữ viết, thường là mã ISO 15924 |
| Region | `VN`, `US`, `TW`, `419` | Quốc gia/vùng, thường theo ISO 3166 hoặc UN M.49 |
| Variant | `rozaj` | Biến thể cụ thể, phải đúng cấu trúc BCP 47 nếu dùng Builder |
| Unicode locale attributes | `emoji` | Thuộc extension `u` và mang ý nghĩa theo hệ chuẩn liên quan |
| Unicode locale keyword | `ca=buddhist`, `nu=thai` | Tùy chọn lịch, numbering system... |
| Other extension | `x-demo-case` | Extension; `x` dành cho private use |

Một tag phổ biến có dạng:

```text
language[-Script][-REGION][-variant...][-extension...]
```

Đây là **khung tư duy**, không phải grammar đầy đủ của BCP 47. BCP 47 còn nhiều quy tắc về thứ tự subtags, extension singletons, private use, grandfathered/legacy tags và các chuyển đổi chuẩn hóa. Đừng cố thay `Locale.Builder` bằng một regex tự chế rồi khẳng định đã validate mọi tag.

### 2.1. Ví dụ đọc language tag

`zh-Hant-TW` bao gồm:

- `zh`: Chinese.
- `Hant`: Traditional Han script.
- `TW`: Taiwan region.

`th-TH-u-ca-buddhist-nu-thai` bao gồm:

- `th` và `TH`: ngôn ngữ Thái và vùng Thái Lan.
- `u`: Unicode locale extension.
- `ca-buddhist`: keyword calendar.
- `nu-thai`: keyword numbering system.

**Thứ tự của các Unicode keywords khi render có thể được chuẩn hóa**, vì thế nên dùng `toLanguageTag()` thay cho tự ghép chuỗi.

### 2.2. Locale không phải timezone, currency hoặc encoding

`Locale` là bối cảnh ngôn ngữ/vùng, **không** mang đầy đủ thông tin:

- Múi giờ cụ thể, ví dụ `Asia/Ho_Chi_Minh` → dùng `ZoneId`.
- Loại tiền tệ được áp dụng cho một giao dịch → dùng mã ISO currency và `Currency` rõ ràng.
- Encoding của bytes → dùng `StandardCharsets.UTF_8` hoặc charset phù hợp.
- Ngôn ngữ của một nội dung văn bản hỗn hợp → cần content metadata riêng.
- Quyền truy cập địa lý/pháp lý của tài khoản → cần authorization/business data.

Locale tạo bởi Builder hỗ trợ chọn cách format/display theo provider; không tự quyết định mọi yếu tố trên.

### 2.3. Đừng dùng Locale.toString làm language tag API

`Locale.toString()` thường biểu diễn các thành phần bằng dạng sử dụng underscore, phù hợp debugging và compatibility, nhưng **không phải** language-tag serializer mà giao thức web/API thường mong đợi.

Khi xuất dữ liệu BCP 47, dùng:

```java
String tag = locale.toLanguageTag();
```

Khi nhận BCP 47 string, dùng `Locale.Builder.setLanguageTag(tag).build()` nếu muốn strict validation, hoặc `Locale.forLanguageTag(tag)` nếu cố ý chọn parser lenient. Hai lựa chọn không thay thế hoàn toàn nhau.

## 3. Tại sao chọn Locale.Builder?

### 3.1. Cú pháp chainable

Các setters trả về chính `Locale.Builder`, cho phép cấu hình từng trường:

```java
Locale result = new Locale.Builder()
        .setLanguage("sr")
        .setScript("Latn")
        .setRegion("RS")
        .build();
```

Kết quả tag có dạng `sr-Latn-RS`.

### 3.2. Kiểm tra cú pháp sớm

Builder kiểm tra các giá trị được setter cấu hình theo quy tắc well-formed của `Locale`/BCP 47. Nếu đầu vào không hợp lệ về cú pháp, setter có thể ném `IllformedLocaleException`.

Ví dụ:

```java
new Locale.Builder().setLanguage("en_US");
```

Đây là đoạn cố tình sai. `"en_US"` không phải một **language subtag**: nó gồm language và region nối bằng underscore. `setLanguage` chỉ nhận language; phải dùng `setLanguage("en").setRegion("US")` hoặc `setLanguageTag("en-US")`.

### 3.3. Locale result immutable, Builder mutable

`Locale` là giá trị immutable và có thể được chia sẻ sau khi đã build. `Builder` giữ cấu hình đang thay đổi và có thể **tái sử dụng tuần tự**.

```java
Locale.Builder builder = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US");
Locale first = builder.build();
Locale second = builder.setRegion("GB").build();
```

Kết quả:

```text
first.toLanguageTag()  = en-US
second.toLanguageTag() = en-GB
```

Việc thay Builder cho lần build thứ hai **không** sửa Locale đã build lần thứ nhất. Tuy nhiên, **không share một Builder mutable giữa nhiều threads mà không đồng bộ hóa và mong mọi call an toàn**. Mỗi operation thường nên tạo Builder mới hoặc owner duy nhất.

### 3.4. Không phải validator business hoàn chỉnh

Một subtag có thể **well-formed về cú pháp** nhưng không phải mã đã đăng ký hay không được product hỗ trợ. Ví dụ một chuỗi đúng pattern hai chữ cái vẫn cần được kiểm tra có thuộc **allowlist locale thực sự được ứng dụng hỗ trợ** hay không.

Bên cạnh đó, JDK/CLDR locale providers có thể dùng dữ liệu/fallback khác nhau. Builder không chứng minh mọi formatting API sẽ tuân thủ keyword extension bạn vừa đặt.

**Kết luận:** Builder xác thực syntax, product validation kiểm tra supported locales/features, và formatter thực tế quyết định output.

## 4. Bảng API của Locale.Builder

Tất cả các phương thức sau vẫn thuộc API Java tiêu chuẩn:

| Phương thức | Mục đích | Lưu ý quan trọng |
| --- | --- | --- |
| `new Locale.Builder()` | Tạo Builder trống | Không tự chọn `Locale.getDefault()` |
| `setLanguage(String)` | Đặt language | Empty/null xóa language; cú pháp subtag được kiểm tra |
| `setScript(String)` | Đặt script | Thường 4 ký tự chữ; normalize dạng title case |
| `setRegion(String)` | Đặt region | 2 chữ hoặc 3 số; normalize chữ hoa |
| `setVariant(String)` | Đặt variant subtags | Cú pháp BCP 47 strict |
| `setLanguageTag(String)` | Reset toàn Builder theo BCP 47 tag | Strict; tag lỗi gây `IllformedLocaleException` |
| `setLocale(Locale)` | Reset Builder từ Locale hiện hữu | Kiểm tra các fields well-formed |
| `setExtension(char,String)` | Đặt/xóa extension `u`, `x` hoặc các extension khác | Set `u` có thể thay Unicode keywords trước đó |
| `setUnicodeLocaleKeyword(String,String)` | Đặt/xóa một key/type của extension `u` | Key/type được kiểm tra cú pháp; `null` type xóa key |
| `addUnicodeLocaleAttribute(String)` | Thêm attribute cho `u` | Trùng attribute được bỏ qua |
| `removeUnicodeLocaleAttribute(String)` | Bỏ attribute | So sánh không phân biệt hoa/thường |
| `clearExtensions()` | Xóa extensions | Giữ language, script, region, variant |
| `clear()` | Reset mọi fields/extension | Build ngay sau clear tương đương `Locale.ROOT` |
| `build()` | Tạo Locale | Locale bất biến, Builder vẫn có thể tiếp tục sửa |

### 4.1. Setter chỉ thay trường được chỉ định

`setLanguage("fr")` trên một Builder đã có region `US` không tự xóa region. Điều này khác với `setLanguageTag` và `setLocale`: **hai phương thức sau reset các trường từ input mới**, loại bỏ state cũ không được input mô tả.

Khi tái sử dụng Builder trong một luồng xử lý nhiều requests, dễ vô tình để sót region/Unicode keyword của request trước nếu chỉ thay `setLanguage`. Cách an toàn là **tạo Builder mới mỗi request** hoặc gọi `clear()` một cách có chủ đích trước khi cấu hình lại.

### 4.2. Các phương thức reset khác nhau

```java
Locale.Builder builder = new Locale.Builder()
        .setLanguageTag("en-US-u-ca-gregory");

Locale withoutExtensions =
        builder.clearExtensions().build();
```

`withoutExtensions.toLanguageTag()` bằng `"en-US"`: language/region được giữ, extension `u-ca-gregory` bị xóa.

Ngược lại:

```java
Locale empty = builder.clear().build();
```

`empty.equals(Locale.ROOT)` là `true` và `empty.toLanguageTag()` là `"und"`.

**`clear()` không có nghĩa quay về Locale mặc định của máy.** Nó tạo Builder không có language/region/script/variant/extensions.

### 4.3. Có thể xóa từng giá trị

Javadoc cho phép `setLanguage(null)`, `setScript("")`, `setRegion(null)` và `setVariant("")` xóa trường tương ứng. Với `setExtension('x', null)`, extension `x` được xóa. Với `setUnicodeLocaleKeyword("ca", null)`, keyword `ca` được xóa.

Điều này hữu ích khi điều chỉnh một Locale có nhiều components, nhưng đừng tận dụng null để “chấp nhận input lỗi im lặng”. Trong API nhận input từ người dùng, phân biệt **không cung cấp giá trị** và **giá trị có nhưng không hợp lệ**.

## 5. Đặt language với setLanguage

```java
Locale languageOnly = new Locale.Builder()
        .setLanguage("vi")
        .build();
```

Kết quả tag là `"vi"`. Không tự gán `"VN"` chỉ vì người dùng chọn tiếng Việt: một ngôn ngữ có thể được sử dụng tại nhiều vùng.

### 5.1. Language code và casing

BCP 47 thường dùng language subtag viết chữ thường: `vi`, `en`, `fr`. Builder có khả năng normalize casing. Đoạn:

```java
Locale normalized = new Locale.Builder()
        .setLanguage("VI")
        .setRegion("vn")
        .build();
```

cho `normalized.toLanguageTag() == "vi-VN"`.

**Đừng tự ép `language.toLowerCase()` theo Locale mặc định của máy** rồi lắp tag: một số quy tắc case mapping của ngôn ngữ tự nhiên có thể khác cách chuẩn hóa ASCII codes. Hãy giao normalization của subtags cho Builder/Locale.

### 5.2. Không truyền cả BCP 47 tag cho setLanguage

`setLanguage("zh-Hant-TW")` là sai về trách nhiệm. `setLanguage` chỉ đặt **language**; `setLanguageTag` mới nhận toàn bộ chuỗi.

Đúng:

```java
Locale chinese = new Locale.Builder()
        .setLanguageTag("zh-Hant-TW")
        .build();
```

Hoặc:

```java
Locale chinese = new Locale.Builder()
        .setLanguage("zh")
        .setScript("Hant")
        .setRegion("TW")
        .build();
```

Hai mẫu tạo Locale với ba fields tương ứng. `getLanguage()` trả `"zh"`, `getScript()` trả `"Hant"` và `getCountry()` trả `"TW"`.

### 5.3. Well-formed language chưa chắc có dữ liệu dịch

Builder không tải các bản dịch. Nếu UI cần tiếng Việt, phải có resource bundles/translations tương ứng hoặc fallback đã thiết kế. Một tag được Builder chấp nhận không có nghĩa host có đầy đủ localized messages cho tag đó.

## 6. Đặt script với setScript

Script phân biệt **hệ chữ viết**; ngôn ngữ và vùng đôi khi chưa đủ để chọn dạng hiển thị.

```java
Locale traditionalChinese = new Locale.Builder()
        .setLanguage("zh")
        .setScript("Hant")
        .setRegion("TW")
        .build();
```

Kết quả `"zh-Hant-TW"`. Nếu truyền `"hant"`, Builder normalize thành `"Hant"`.

Một script subtag well-formed thường gồm **4 chữ cái**, theo ISO 15924. `Latn`, `Hans`, `Hant` là những ví dụ phổ biến.

### 6.1. Khi nào cần script?

- Ngôn ngữ có nhiều hệ chữ viết như tiếng Trung hoặc tiếng Serbia.
- Bản dịch/resources hoặc font fallback phụ thuộc script.
- Dữ liệu liên quan tới transliteration/search phân biệt hệ chữ viết.

**Không dùng script để mô tả encoding.** `Latn` là script Latin; `UTF-8` là character encoding, chúng không phải cùng lớp thông tin.

### 6.2. setScript không tự dịch/chuyển chữ

`new Locale.Builder().setLanguage("zh").setScript("Hant")` không chuyển một `String` giản thể thành phồn thể. Nó chỉ định **ngữ cảnh** khi một API/resource bundle hỗ trợ script. Muốn transliteration, cần chức năng chuyển đổi văn bản riêng.

### 6.3. Cú pháp sai

`setScript("Lat")` là ví dụ không hợp lệ; nó không phải subtag script dài 4 chữ. Builder ném `IllformedLocaleException` ngay khi setter được gọi.

## 7. Đặt region với setRegion

Region thường là mã quốc gia **hai chữ cái** hoặc mã vùng **ba chữ số**:

```java
Locale v = new Locale.Builder()
        .setLanguage("vi")
        .setRegion("VN")
        .build();
```

`toLanguageTag()` trả `"vi-VN"`.

Ví dụ sử dụng mã vùng UN M.49:

```java
Locale latinAmerica = new Locale.Builder()
        .setLanguage("es")
        .setRegion("419")
        .build();
```

`toLanguageTag()` trả `"es-419"`.

### 7.1. Region không phải currency/timezone

Một mã vùng không mô tả đầy đủ currency của transaction, múi giờ người dùng hay yêu cầu pháp lý. Ví dụ người dùng có thể muốn giao diện `en-US` nhưng thanh toán bằng VND. Vì vậy khi format tiền, sử dụng amount và currency code rõ ràng, không chỉ suy currency từ Locale.

### 7.2. Region normalization

`setRegion("vn")` được Builder chuẩn hóa thành `VN`. `Locale.getCountry()` trả country/region code, không phải tên dịch `"Việt Nam"`.

Nếu cần tên hiển thị, có thể dùng `locale.getDisplayCountry(displayLocale)` — kết quả phụ thuộc locale provider và ngôn ngữ hiển thị, không dùng làm mã khóa dữ liệu.

### 7.3. Region sai cú pháp

`setRegion("VNM")` không hợp lệ đối với region subtag của Builder; ba chữ cái không phải mã vùng ba chữ số. Test thực tế đã xác nhận nó ném `IllformedLocaleException`.

Đừng dùng mã viết tắt tên quốc gia trong business data không đúng BCP 47 rồi hy vọng Builder tự chuyển sang mã chuẩn.

## 8. Đặt variant với setVariant

Variant mô tả một biến thể đã được mô tả bởi BCP 47, không phải ô chứa chuỗi tùy ý.

Ví dụ:

```java
Locale slovenianVariant = new Locale.Builder()
        .setLanguage("sl")
        .setRegion("SI")
        .setVariant("rozaj")
        .build();
```

`toLanguageTag()` cho `"sl-SI-rozaj"`.

Cú pháp BCP 47 cho **mỗi variant subtag** nhìn chung là:

- **5 đến 8 ký tự chữ/số**, hoặc
- **4 ký tự**, ký tự đầu phải là một chữ số.

Một variant có thể có nhiều subtags hợp lệ, được biểu diễn theo cấu trúc và cú pháp mà Builder kiểm tra.

### 8.1. Builder strict hơn các cách tạo Locale kiểu chung

Một số cách tạo Locale có thể giữ variant không well-formed, dẫn đến mất thông tin khi chuyển sang BCP 47. Builder **cố ý** từ chối variant sai cú pháp để `toLanguageTag()` có thể biểu diễn thông tin well-formed.

Ứng dụng mới nên ưu tiên Builder khi kết quả cần serialize đúng BCP 47. Nếu phải xử lý dữ liệu lịch sử không well-formed, hãy tách khâu migration/normalization thay vì âm thầm coi các variant cũ là hợp lệ.

### 8.2. Casing của variant

Builder normalize case của variant theo convention BCP 47. Đừng so sánh identity locale bằng những chuỗi thô có case tùy ý. Dùng `Locale.equals` hoặc tag canonical do `toLanguageTag()` trả khi bài toán đòi định danh theo language tag.

## 9. Xây dựng trực tiếp bằng setLanguageTag

Khi HTTP request hoặc database đã chứa một language tag hoàn chỉnh, không cần tách thủ công bằng `String.split("-")`:

```java
Locale locale = new Locale.Builder()
        .setLanguageTag("zh-Hant-TW")
        .build();
```

Đây là cách **strict**: nếu tag không well-formed, `setLanguageTag` ném `IllformedLocaleException`.

### 9.1. setLanguageTag reset builder state

```java
Locale.Builder builder = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US");

Locale parsed = builder
        .setLanguageTag("fr-CA")
        .build();
```

Kết quả là `fr-CA`, không phải một tổ hợp pha trộn `en-US` với `fr-CA`. `setLanguageTag` **thay thế toàn bộ state** để khớp tag được cung cấp.

**Lưu ý:** `setLanguageTag(null)` hoặc chuỗi rỗng reset Builder tương tự `clear()` theo Javadoc. Ở tầng API nhập dữ liệu, nên kiểm tra null/empty trước nếu hai trường hợp đó phải bị từ chối, thay vì để chúng hợp lệ mà tạo Locale.ROOT.

### 9.2. Vì sao không split dấu gạch ngang?

Nếu tự phân tích `zh-Hant-TW-u-nu-latn` thành các mảnh rồi gán phần thứ hai luôn là region, bạn sẽ nhầm `Hant` (script) thành country. BCP 47 còn có variant, extension và private use; việc parse theo vị trí cứng là không đúng.

Dùng `setLanguageTag` để parser chuyên trách nhận diện cú pháp. Nếu cần tách các thành phần sau parse:

```java
Locale locale = new Locale.Builder()
        .setLanguageTag("zh-Hant-TW-u-nu-latn")
        .build();

String language = locale.getLanguage(); // "zh"
String script = locale.getScript();     // "Hant"
String region = locale.getCountry();    // "TW"
String numbering = locale.getUnicodeLocaleType("nu"); // "latn"
```

### 9.3. So sánh strict Builder với Locale.forLanguageTag

`Locale.forLanguageTag(String)` **cũng còn được hỗ trợ**. Nhưng khác biệt quan trọng:

| Nhu cầu | `Locale.Builder.setLanguageTag` | `Locale.forLanguageTag` |
| --- | --- | --- |
| BCP 47 tag hợp lệ | Xây Locale | Xây Locale |
| Tag lỗi cú pháp ở phần sau | Ném `IllformedLocaleException` | Có thể bỏ phần lỗi và những gì theo sau |
| Dùng để chặn input tag sai | **Phù hợp** nếu muốn strict | Dễ vô tình nhận một phần |
| Dùng để parse lenient theo contract | Không phải lựa chọn lenient | Có thể phù hợp nếu rõ yêu cầu |
| Xử lý validation ngoài cú pháp | Vẫn cần | Vẫn cần |

Ví dụ:

```java
String malformedTag = "en-US-@";

Locale lenient = Locale.forLanguageTag(malformedTag);
Locale strict = new Locale.Builder()
        .setLanguageTag(malformedTag) // IllformedLocaleException
        .build();
```

Đây là đoạn **cố tình có lỗi**. Trên JDK 17 đã kiểm thử, `lenient.toLanguageTag()` trả `"en-US"`, còn setter strict ném `IllformedLocaleException`. Một backend cần **từ chối client tag không đúng** không nên âm thầm nuốt hậu tố bất hợp lệ mà không có chủ đích.

### 9.4. Xử lý lỗi parser

Một API nhận locale tag nên quyết định trước policy:

- Tag hợp lệ và thuộc danh sách ứng dụng hỗ trợ → chấp nhận.
- Tag hợp lệ nhưng không được hỗ trợ → chọn fallback có giải thích hoặc trả lỗi validation.
- Tag không well-formed → trả lỗi cú pháp rõ, không âm thầm thay bằng locale khác trừ khi business contract cho phép.
- Tag rỗng/null → theo chính sách sản phẩm, không vô tình cho phép `clear()` làm thành locale không xác định.
- Input quá dài → kiểm soát kích thước để bảo vệ API, không dựa vào Builder giải quyết mọi resource attack.

Không để exception message thô với dữ liệu nhạy cảm lộ ra trong response API.

## 10. BCP 47 well-formed khác với locale được hỗ trợ

Điểm phân biệt quan trọng:

1. **Well-formed syntax:** Tag tuân grammar của BCP 47 hoặc fields tuân syntactic restrictions của Builder.
2. **Registered/known code:** Subtags có ý nghĩa theo registry/standards hiện hành.
3. **Supported application locales:** Sản phẩm có resource bundles, bản dịch và UX hợp lệ cho tag đó.
4. **Supported locale provider features:** JDK/CLDR/ICU/provider cụ thể có format calendars/numbering systems/collation được yêu cầu không.
5. **User preference:** Người dùng muốn giao diện/ngày/giờ/số theo cấu hình đó hay chỉ là ngôn ngữ của một tài liệu.

`Locale.Builder` chủ yếu giải quyết **mục 1**. Nó không cam kết bốn mục còn lại.

### 10.1. Ví dụ thiết kế whitelist

Nếu ứng dụng chỉ hỗ trợ ba bản dịch:

```java
import java.util.Locale;
import java.util.Set;

Set<String> supportedTags = Set.of("vi-VN", "en-US", "fr-FR");

Locale selected = new Locale.Builder()
        .setLanguageTag(requestTag)
        .build();

if (!supportedTags.contains(selected.toLanguageTag())) {
    throw new IllegalArgumentException("Locale not supported");
}
```

Đây là **đoạn minh họa** trong method đã có `requestTag`. Trong thực tế cần policy fallback (ví dụ chọn language-only nếu vùng không được hỗ trợ), nhưng không nên giả định fallback cứ lấy prefix bằng `String.substring`.

### 10.2. Ngữ nghĩa không chỉ dựa vào case

Builder normalize case cho language/script/region và những thành phần extension liên quan. Nhưng **không nên thiết kế security check** chỉ bằng case-normalization rồi so sánh chuỗi free-form để cấp quyền truy cập. Locale là **sở thích hiển thị**, không phải identity/authorization.

### 10.3. Một locale không có duy nhất một display format

Ngay cả khi `Locale` giống nhau, kết quả ngày/tháng/số/tiền có thể khác do JDK version, CLDR data version, provider order, currency code, timezone và formatter options.

Vì vậy unit test Builder nên assert **components/tags/exception**, không ép output `DateTimeFormatter` hoặc `NumberFormat` thành một golden string có thể thay đổi qua cập nhật dữ liệu.

## 11. Unicode locale extensions: calendar, numbering và nhiều tùy chọn khác

BCP 47 có Unicode extension singleton **`u`**. Java cung cấp API cấu trúc thay vì bắt bạn tự ghép chuỗi:

```java
Locale thai = new Locale.Builder()
        .setLanguage("th")
        .setRegion("TH")
        .setUnicodeLocaleKeyword("ca", "buddhist")
        .setUnicodeLocaleKeyword("nu", "thai")
        .build();
```

Kết quả language tag:

```text
th-TH-u-ca-buddhist-nu-thai
```

`ca` là key cho calendar; `nu` là key cho numbering system theo Unicode locale extension conventions.

### 11.1. Đọc lại Unicode keyword

```java
String calendar = thai.getUnicodeLocaleType("ca");
String numbering = thai.getUnicodeLocaleType("nu");
```

Với ví dụ, `calendar.equals("buddhist")` và `numbering.equals("thai")` đều đúng.

Nếu keyword chưa được đặt, getter có thể trả `null`. Không nhầm `null` với chuỗi rỗng hoặc value được provider tự chọn làm default.

### 11.2. Vì sao không khẳng định format luôn áp dụng keywords?

`Locale` lưu metadata mong muốn. Một formatter/provider có thể hỗ trợ một số options và fallback các options không hỗ trợ. Việc `thai.getUnicodeLocaleType("nu")` trả `"thai"` không chứng minh **mọi API format** sẽ dùng chữ số Thái hoặc mọi ngày được chuyển sang lịch Phật giáo.

Integration test phải gọi **formatter thực tế được ứng dụng sử dụng**, kiểm tra output theo JDK/provider mục tiêu và có cơ chế fallback.

### 11.3. Keyword phải có key/type well-formed

`setUnicodeLocaleKeyword(key,type)` kiểm tra key và type:

- Key thường có **hai ký tự chữ/số**, ví dụ `ca` hoặc `nu`.
- Type phải tuân cấu trúc cho Unicode locale type, không phải chuỗi tự do.
- Key được normalize lowercase.
- `setUnicodeLocaleKeyword("calendar","gregory")` không hợp lệ vì key không phải subtag key hai ký tự; ném `IllformedLocaleException`.
- `setUnicodeLocaleKeyword("ca",null)` xóa keyword `ca`.

**Giá trị type “well-formed” không tự động là một lựa chọn có ngữ nghĩa được Java provider hỗ trợ.** Với hệ thống production, kiểm tra danh mục options thực tế có thể áp dụng.

### 11.4. Unicode keyword order canonical

Khi thêm `nu` trước `ca` hoặc `ca` trước `nu`, `toLanguageTag()` có thể đưa các key về thứ tự chuẩn. Không cần duy trì thứ tự người dùng nhập để tạo identity string.

Nếu cần lưu thứ tự người dùng thao tác UI, đó là dữ liệu riêng không phải property của `Locale`.

## 12. Unicode locale attributes

Bên cạnh key/type, Unicode extension có **attributes**:

```java
Locale withAttribute = new Locale.Builder()
        .setLanguageTag("en-US")
        .addUnicodeLocaleAttribute("emoji")
        .build();
```

`withAttribute.toLanguageTag()` trả `"en-US-u-emoji"`.

Kiểm tra:

```java
boolean hasEmoji = withAttribute
        .getUnicodeLocaleAttributes()
        .contains("emoji");
```

### 12.1. Thêm trùng không tạo hai phần giống nhau

`addUnicodeLocaleAttribute("emoji")` nếu attribute đã tồn tại thì không thêm một bản sao; Javadoc mô tả thao tác thêm idempotent đối với attribute đã có.

### 12.2. Xóa attribute

```java
Locale.Builder builder = new Locale.Builder()
        .setLanguageTag("en-US-u-emoji");

builder.removeUnicodeLocaleAttribute("EMOJI");
Locale removed = builder.build();
```

So sánh khi xóa attribute là **case-insensitive**. `removed` không còn `emoji`; nếu không có key/type nào khác trong extension, Unicode extension không còn nội dung.

Không dùng attribute tùy ý để “lưu mọi tùy chọn UI” nếu semantic standard không quy định. Các cấu hình riêng như dark mode, onboarding status hoặc account tier phải được lưu ở cấu trúc nghiệp vụ, không cài vào language tag của user.

### 12.3. Validation của attributes

Unicode locale attribute phải well-formed, không null. Truyền null vào `addUnicodeLocaleAttribute` ném `NullPointerException`; chuỗi sai cú pháp gây `IllformedLocaleException`. Validate từ UI trước khi gọi và xử lý riêng trường hợp thiếu/không hợp lệ.

## 13. setExtension: BCP 47 extensions và private use

`setExtension(char key,String value)` đặt hoặc xóa một extension:

```java
Locale custom = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setExtension('x', "demo-case")
        .build();
```

`custom.toLanguageTag()` bằng `"en-US-x-demo-case"`.

`x` là **private use extension**: các subtags này không mang ngữ nghĩa chung được tất cả ứng dụng hiểu. Nó chỉ hữu ích khi các hệ thống có thỏa thuận cụ thể về ý nghĩa; không dùng để cất dữ liệu bí mật hoặc thông tin cá nhân trong tag.

### 13.1. Unicode extension cũng là extension 'u'

`setExtension('u',"ca-buddhist-nu-thai")` có thể thiết lập Unicode extension từ chuỗi đúng cú pháp. Tuy nhiên, cách cấu trúc:

```java
builder.setUnicodeLocaleKeyword("ca", "buddhist");
builder.setUnicodeLocaleKeyword("nu", "thai");
```

thường rõ ý nghĩa hơn, dễ kiểm thử key/type hơn.

**Lưu ý lifecycle:** gọi `setExtension('u',value)` **thay thế** các Unicode locale keywords/attributes hiện tại bằng nội dung extension mới. Nó không đơn giản append thêm vào những keywords đã đặt trước.

### 13.2. Xóa extension

Nếu `value` là null hoặc rỗng, extension được loại bỏ. Ví dụ `setExtension('x',null)` xóa private use. `clearExtensions()` xóa **tất cả** extensions trong khi giữ language/script/region/variant.

### 13.3. Chú ý grammar của private use

`x` cho phép các subtags riêng có độ dài khác extension thông thường (1–8 ký tự chữ/số mỗi subtag). Builder vẫn kiểm tra cú pháp chứ không tự xác thực ý nghĩa nội dung private use.

Khi lưu locale vào database, ưu tiên giữ tag canonical và tránh dùng private-use data nếu các hệ thống downstream không có thỏa thuận rõ.

## 14. Các thao tác quản lý trạng thái Builder

Builder là mutable object. Bạn cần biết chính xác phương thức nào **giữ** hoặc **xóa** state:

| Hành động | Language/script/region/variant | Unicode/other extensions |
| --- | --- | --- |
| `setLanguage("fr")` | Thay language, giữ các trường khác | Giữ |
| `setRegion("CA")` | Thay region, giữ các trường khác | Giữ |
| `setLanguageTag("zh-Hant-TW")` | **Thay toàn bộ** theo tag | Thay toàn bộ theo tag |
| `setLocale(locale)` | **Thay toàn bộ** theo locale, kiểm tra cú pháp | Thay toàn bộ theo locale |
| `clearExtensions()` | Giữ | Xóa tất cả |
| `clear()` | Xóa tất cả | Xóa tất cả |
| `build()` | Không làm Builder rỗng | Không làm Builder rỗng |

### 14.1. setLocale nhận một Locale đã tồn tại

```java
Locale fromLibrary = new Locale.Builder()
        .setLanguageTag("en-US-u-ca-gregory").build();

Locale copied = new Locale.Builder()
        .setLocale(fromLibrary)
        .setRegion("GB")
        .build();
```

`copied` có language `en`, region `GB`, giữ Unicode keyword `ca=gregory` từ giá trị nguồn. `setLocale` còn kiểm tra xem các fields của Locale đầu vào có well-formed không. Nếu một Locale được tạo bằng cách khác với variant không đúng BCP 47, `setLocale` có thể ném `IllformedLocaleException`.

### 14.2. setLanguageTag và null/empty

Javadoc ghi rõ `setLanguageTag(null)` và `setLanguageTag("")` reset Builder tương tự `clear()`. Khi nhận một tùy chọn locale **bắt buộc** từ user, nên tự xử lý null/blank để tránh chọn `Locale.ROOT` ngoài ý muốn.

### 14.3. Tái sử dụng Builder có thể gây rò trạng thái giữa requests

Ví dụ lỗi:

```java
// Không chia sẻ cùng mutable Builder giữa các request khác nhau.
Locale.Builder shared = new Locale.Builder();
Locale a = shared.setLanguageTag("en-US-u-ca-gregory").build();
Locale b = shared.setRegion("GB").build();
```

`b` không chỉ là `en-GB`: nó vẫn có Unicode keyword `ca=gregory` từ state trước. Nếu muốn tạo locale mới độc lập, dùng `new Locale.Builder()` mỗi lần hoặc gọi `clear()` trước khi set các fields mới.

### 14.4. Locale đã build không bị ảnh hưởng

`Locale` bất biến nên:

```java
Locale.Builder builder = new Locale.Builder()
        .setLanguage("en").setRegion("US");

Locale oldLocale = builder.build();
Locale newLocale = builder.setRegion("GB").build();
```

Sau đó `oldLocale.toLanguageTag()` vẫn là `en-US`, không bị đổi theo Builder. Có thể cache Locale values, nhưng không tự kết luận mọi formatter object cũng thread-safe; xem contract của từng API.

## 15. Exceptions: lỗi nào xuất hiện ở đâu?

`IllformedLocaleException` là **unchecked exception** mở rộng `RuntimeException`; nó được các phương thức Builder ném khi một giá trị không thỏa yêu cầu cú pháp.

| Đầu vào | Lời gọi | Kết quả |
| --- | --- | --- |
| `"vi"` | `setLanguage` | Hợp lệ |
| `"en_US"` | `setLanguage` | `IllformedLocaleException` |
| `"Hant"` | `setScript` | Hợp lệ |
| `"Lat"` | `setScript` | `IllformedLocaleException` |
| `"VN"` | `setRegion` | Hợp lệ |
| `"VNM"` | `setRegion` | `IllformedLocaleException` |
| `"419"` | `setRegion` | Hợp lệ |
| `"rozaj"` | `setVariant` | Hợp lệ |
| `"en-US-@"` | `setLanguageTag` | `IllformedLocaleException` |
| `"calendar"` | `setUnicodeLocaleKeyword` key | `IllformedLocaleException` |
| `null` | `setLanguage` | Xóa trường language |
| `null` | `setLanguageTag` | Reset Builder |
| `null` key | `setUnicodeLocaleKeyword` | `NullPointerException` |
| `null` attribute | `addUnicodeLocaleAttribute` | `NullPointerException` |

### 15.1. Không bắt mọi RuntimeException và đoán input sai

Nếu service có lỗi do bug ở code khác, một catch `RuntimeException` quá rộng rồi trả “locale không hợp lệ” sẽ che lỗi thực. Bắt `IllformedLocaleException` ở **ranh giới input parsing**, và tách các lỗi application khác.

```java
static Locale parseStrict(String tag) {
    if (tag == null || tag.isBlank()) {
        throw new IllegalArgumentException("Locale tag required");
    }
    try {
        return new Locale.Builder().setLanguageTag(tag).build();
    } catch (java.util.IllformedLocaleException badTag) {
        throw new IllegalArgumentException("Invalid BCP 47 tag", badTag);
    }
}
```

Đây là **method minh họa** trong class có import `java.util.Locale`. Nó kiểm tra empty/blank trước, sau đó giữ cause. Chỉ trả thông báo an toàn ra public API; log nguyên input chỉ khi không có secrets và trong giới hạn dữ liệu phù hợp.

### 15.2. Error index

`IllformedLocaleException` có `getErrorIndex()` để hỗ trợ xác định vị trí lỗi trong input khi provider có thông tin đó. Không nên hardcode một vị trí index cụ thể cho mọi trường hợp và mọi JDK: dùng thông tin như một **diagnostic aid**, không làm business contract duy nhất.

### 15.3. Setters có thể kiểm tra tại thời điểm gọi

Đừng viết test chỉ đợi `build()` ném lỗi sau khi gọi `setLanguage("en_US")`: setter có thể ném `IllformedLocaleException` **ngay lập tức**. Test nên bao trùm lời gọi có nguy cơ sai:

```java
boolean rejected = false;
try {
    new Locale.Builder().setLanguage("en_US");
} catch (java.util.IllformedLocaleException expected) {
    rejected = true;
}
if (!rejected) throw new AssertionError("Expected syntax error");
```

### 15.4. Cú pháp đúng không có nghĩa mã ISO được chấp nhận bởi mọi business rule

Một số codes well-formed có thể không phải lựa chọn hợp lệ cho sản phẩm. Builder không truy vấn registry live để xác nhận tất cả ý nghĩa; ứng dụng phải quyết định supported languages, display resources và supported keyword types.

## 16. Locale liên quan đến Unicode, nhưng không tự chuẩn hóa văn bản

Đây là ranh giới quan trọng của chủ đề **Locale và Unicode**:

- `Locale.Builder` chuẩn hóa **các subtags của language tag** theo quy tắc locale.
- Nó **không** chuẩn hóa mọi chuỗi Unicode của người dùng sang NFC/NFD.
- Nó **không** tự làm case folding cho search keys của toàn hệ thống.
- Nó **không** chuyển ký tự giữa các scripts.
- Nó **không** tự giải quyết bài toán sắp xếp văn bản nhiều ngôn ngữ, so khớp dấu hay encoding.

Nếu cần Unicode normalization của text, `java.text.Normalizer` là công cụ khác. Nếu cần so sánh/sắp xếp theo locale, xem `java.text.Collator` và các lựa chọn provider; những vấn đề đó **tách khỏi** việc tạo Locale bằng Builder.

### 16.1. Locale-sensitive casing không phải BCP 47 casing

Một ví dụ nổi tiếng: cách đổi chữ hoa/thường trong ngôn ngữ tự nhiên có thể khác nhau theo locale, như tiếng Thổ Nhĩ Kỳ. Dùng `String.toLowerCase(locale)` cho text tự nhiên khi business yêu cầu locale-aware casing; dùng `Locale.ROOT` cho identifiers/protocol tokens khi cần quy tắc trung lập và đã hiểu tác động Unicode.

Nhưng đối với **BCP 47 locale subtag**, không cần tự gọi `toLowerCase` trên các thành phần nhập: Builder/Locale chịu trách nhiệm chuẩn hóa các trường.

### 16.2. Dùng getDisplayName cho UI, không cho storage IDs

`locale.getDisplayName(displayLocale)` tạo tên hiển thị theo dữ liệu địa phương hóa; nó có thể thay đổi khi JDK/CLDR được cập nhật. Khi lưu ID hoặc truyền qua API, dùng `toLanguageTag()` và business allowlist; không dùng display name làm khóa dữ liệu.

### 16.3. Unicode extension có thể tác động một số formatter

Các keywords `ca` và `nu` có thể được các locale-sensitive APIs xử lý khi provider hỗ trợ. Nhưng khác biệt hỗ trợ và dữ liệu CLDR có thể thay đổi theo release. **Đừng dùng việc tạo thành công `Locale` làm bằng chứng formatter đã chọn lịch/hệ số yêu cầu**; nếu đây là yêu cầu sản phẩm, kiểm thử end-to-end trên runtime mục tiêu.

## 17. Đưa Locale được build vào API format

### 17.1. NumberFormat

```java
import java.text.NumberFormat;
import java.util.Locale;

Locale locale = new Locale.Builder()
        .setLanguage("vi").setRegion("VN").build();

NumberFormat numbers = NumberFormat.getNumberInstance(locale);
String text = numbers.format(12345.67);
```

Đoạn minh họa này là Java hợp lệ trong một method. **Không gắn expected output cố định** cho mọi bản JDK vì locale provider/CLDR version có thể thay đổi dấu phân cách và quy ước.

`NumberFormat` là API có state mutable; không mặc định share cùng một instance giữa nhiều threads. Tạo formatter theo scope hoặc sử dụng synchronization/abstraction phù hợp.

### 17.2. DateTimeFormatter của java.time

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

Locale locale = new Locale.Builder()
        .setLanguage("vi").setRegion("VN").build();

DateTimeFormatter formatter = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.SHORT)
        .withLocale(locale);

String displayed = formatter.format(LocalDate.of(2026, 11, 4));
```

DateTimeFormatter được thiết kế immutable và thread-safe, tiện để reuse theo cấu hình; output định dạng localized vẫn phụ thuộc provider và locale data.

Nếu cần format một thời điểm tuyệt đối theo timezone của user, `DateTimeFormatter.withLocale` **không đặt timezone**. Kết hợp `ZoneId`/`ZonedDateTime` hoặc `withZone(zone)` khi appropriate.

### 17.3. Currency và Locale

`NumberFormat.getCurrencyInstance(locale)` có thể dùng default currency theo locale data, nhưng trong nghiệp vụ thanh toán phải có currency của **amount** riêng (ví dụ `Currency.getInstance("VND")` nếu giao dịch VND). Một người dùng giao diện `en-US` không đồng nghĩa mọi khoản tiền đều USD.

Đừng suy currency/tax rules/chuyển đổi FX từ Locale. Tách business currency code, exchange rate source, tax jurisdiction và display preference.

### 17.4. ResourceBundle và fallback

Có thể truyền Locale được build vào `ResourceBundle.getBundle(baseName,locale)`. Nhưng fallback behavior và resource-file naming phải phù hợp với bundle strategy; việc Build `zh-Hant-TW` thành công không chứng minh dự án có file translation tương ứng.

Một hệ thống nên có default locale fallback có chủ đích và test những ngôn ngữ mà sản phẩm thực sự hỗ trợ.

## 18. Chương trình Java 17+ độc lập đã kiểm thử

Dưới đây là một file **`LocaleBuilderDemo.java`** tự chạy, không cần dependency ngoài JDK. Nó kiểm tra:

1. Chuẩn hóa `VI`/`vn` thành `vi-VN`.
2. Thêm script `latn` và xác nhận Locale đã build không bị thay đổi.
3. Parse `zh-Hant-TW` bằng `setLanguageTag`.
4. Tạo mã vùng UN M.49 `es-419`.
5. Variant `sl-SI-rozaj`.
6. Unicode keyword calendar/numbering và thứ tự canonical.
7. Unicode attribute `emoji`.
8. Private-use extension `x-demo-case`.
9. `clearExtensions` giữ language/region nhưng xóa extension.
10. `clear` tạo Locale.ROOT có language tag `und`.
11. Năm inputs sai cú pháp bị `IllformedLocaleException`.
12. `Locale.forLanguageTag` lenient với một tag có hậu tố sai.
13. Đưa Locale tường minh vào `DateTimeFormatter`, kiểm tra output không rỗng thay vì cố định mẫu localized.
14. Xác minh Locale values độc lập/bất biến.
15. In `checks = PASS` chỉ khi mọi assertion đã qua.

### 18.1. Toàn bộ mã nguồn

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.IllformedLocaleException;
import java.util.Locale;
import java.util.Objects;

public final class LocaleBuilderDemo {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    private static boolean malformed(Runnable action) {
        try {
            action.run();
            return false;
        } catch (IllformedLocaleException expected) {
            return true;
        }
    }

    public static void main(String[] args) {
        Locale.Builder builder = new Locale.Builder()
                .setLanguage("VI")
                .setRegion("vn");
        Locale basic = builder.build();
        check("vi-VN".equals(basic.toLanguageTag()),
                "language/region casing");
        System.out.println("normalized = " + basic.toLanguageTag());

        Locale scripted = builder.setScript("latn").build();
        check("vi-Latn-VN".equals(scripted.toLanguageTag()),
                "script casing");
        check("vi-VN".equals(basic.toLanguageTag()),
                "previous Locale must remain unchanged");
        System.out.println("script = " + scripted.toLanguageTag());

        Locale chinese = new Locale.Builder()
                .setLanguageTag("zh-Hant-TW").build();
        check("Hant".equals(chinese.getScript())
                && "TW".equals(chinese.getCountry()),
                "parse script tag");
        System.out.println("language tag = " + chinese.toLanguageTag());

        Locale region = new Locale.Builder()
                .setLanguage("es").setRegion("419").build();
        check("es-419".equals(region.toLanguageTag()),
                "UN M.49 region");
        System.out.println("numeric region = " + region.toLanguageTag());

        Locale variant = new Locale.Builder()
                .setLanguage("sl").setRegion("SI")
                .setVariant("rozaj").build();
        check("sl-SI-rozaj".equals(variant.toLanguageTag()),
                "BCP47 variant");
        System.out.println("variant = " + variant.toLanguageTag());

        Locale unicode = new Locale.Builder()
                .setLanguage("th").setRegion("TH")
                .setUnicodeLocaleKeyword("ca", "buddhist")
                .setUnicodeLocaleKeyword("nu", "thai")
                .build();
        check("th-TH-u-ca-buddhist-nu-thai"
                .equals(unicode.toLanguageTag()),
                "Unicode keyword canonical order");
        check("buddhist".equals(
                    unicode.getUnicodeLocaleType("ca"))
                && "thai".equals(
                    unicode.getUnicodeLocaleType("nu")),
                "Unicode keyword retrieval");
        System.out.println(
                "Unicode keywords = " + unicode.toLanguageTag());

        Locale attribute = new Locale.Builder()
                .setLanguageTag("en-US")
                .addUnicodeLocaleAttribute("emoji")
                .build();
        check("en-US-u-emoji".equals(attribute.toLanguageTag())
                && attribute.getUnicodeLocaleAttributes()
                    .contains("emoji"), "Unicode attribute");
        System.out.println(
                "Unicode attribute = " + attribute.toLanguageTag());

        Locale privateUse = new Locale.Builder()
                .setLanguage("en").setRegion("US")
                .setExtension('x', "demo-case").build();
        check("en-US-x-demo-case".equals(
                    privateUse.toLanguageTag()),
                "private use extension");
        System.out.println(
                "private use = " + privateUse.toLanguageTag());

        Locale noExtensions = new Locale.Builder()
                .setLanguageTag("en-US-u-ca-gregory")
                .clearExtensions().build();
        check("en-US".equals(noExtensions.toLanguageTag()),
                "clear extensions but retain core subtags");
        System.out.println(
                "clearExtensions = " + noExtensions.toLanguageTag());

        Locale root = new Locale.Builder()
                .setLanguage("en").setRegion("US")
                .clear().build();
        check(Locale.ROOT.equals(root)
                && "und".equals(root.toLanguageTag()),
                "clear all fields");
        System.out.println("clear = " + root.toLanguageTag());

        check(malformed(() ->
                    new Locale.Builder().setLanguage("en_US"))
                && malformed(() ->
                    new Locale.Builder().setScript("Lat"))
                && malformed(() ->
                    new Locale.Builder().setRegion("VNM"))
                && malformed(() ->
                    new Locale.Builder().setLanguageTag("en-US-@"))
                && malformed(() ->
                    new Locale.Builder().setUnicodeLocaleKeyword(
                        "calendar", "gregory")),
                "Strict syntax checks");
        System.out.println("five invalid inputs rejected = true");

        Locale lenient = Locale.forLanguageTag("en-US-@");
        check("en-US".equals(lenient.toLanguageTag()),
                "forLanguageTag ignores malformed trailing material");
        System.out.println(
                "forLanguageTag lenient = " + lenient.toLanguageTag());

        DateTimeFormatter formatter = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(basic);
        String rendered = formatter.format(
                LocalDate.of(2026, 11, 4));
        check(!rendered.isBlank()
                && Objects.equals("vi", basic.getLanguage()),
                "locale passed to a formatter");
        System.out.println("explicit formatter locale = true");

        Locale independent = new Locale.Builder()
                .setLanguage("en").setRegion("US").build();
        check(!independent.equals(basic),
                "distinct requested locale");
        System.out.println("Locale objects immutable = true");
        System.out.println("checks = PASS");
    }
}
```

### 18.2. Cách biên dịch/chạy

Lưu file đúng tên `LocaleBuilderDemo.java` và chạy trong thư mục chứa file:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 LocaleBuilderDemo.java
java LocaleBuilderDemo
```

**Chương trình đã biên dịch và chạy trên Java 17, không có warning.** Stdout chính xác **15 dòng**:

```text
normalized = vi-VN
script = vi-Latn-VN
language tag = zh-Hant-TW
numeric region = es-419
variant = sl-SI-rozaj
Unicode keywords = th-TH-u-ca-buddhist-nu-thai
Unicode attribute = en-US-u-emoji
private use = en-US-x-demo-case
clearExtensions = en-US
clear = und
five invalid inputs rejected = true
forLanguageTag lenient = en-US
explicit formatter locale = true
Locale objects immutable = true
checks = PASS
```

Không in chuỗi ngày formatted cụ thể, vì locale provider/CLDR output có thể khác giữa những bản JDK. Demo chỉ kiểm tra Formatter nhận Locale hợp lệ và trả chuỗi không rỗng, không biến một pattern dữ liệu địa phương hóa thành unit contract cứng.

### 18.3. Mã demo xác minh gì?

- **Builder strict syntax**: năm inputs lỗi đều bị từ chối.
- **Case normalization**: language lower, script title case, region uppercase.
- **Bảo toàn component**: `Locale` đã build không bị thay khi Builder sửa tiếp.
- **BCP 47 round-trip ở ví dụ well-formed**: các tags được tạo và xuất lại bằng `toLanguageTag`.
- **Unicode extensions**: dùng cấu trúc keyword/attribute, không phải chuỗi lắp thủ công.
- **Private-use extension**: đặt bằng setter có validation.
- **Clear semantics**: `clearExtensions` khác `clear`.
- **Lenient-vs-strict**: `forLanguageTag` có thể bỏ phần input lỗi, Builder không bỏ qua.
- **Locale formatting injection**: truyền Locale một cách tường minh cho formatter.
- **Tính độc lập**: không gọi `Locale.setDefault`, không thay trạng thái toàn JVM.

### 18.4. Mã demo không xác minh gì?

Nó **không** khẳng định:

- Ứng dụng có resource bundles cho mọi tag.
- `th-TH-u-nu-thai` sẽ khiến mọi formatter in chữ số Thái.
- `ca-buddhist` được toàn bộ provider/calendar APIs áp dụng.
- Các currency/tax/timezone values được suy đúng chỉ từ locale.
- Mọi tổ hợp language/script/region well-formed đều có ý nghĩa đăng ký.
- Một username hay text Unicode đã được chuẩn hóa hoàn toàn.

Đây là các kiểm thử **tầng dịch vụ hoặc integration tests riêng** cần dữ liệu và provider thực.

## 19. Cách kiểm thử Builder ổn định

### 19.1. Unit tests nên tập trung vào kết quả cấu trúc

Chọn những assertions ổn định:

- `getLanguage()`, `getScript()`, `getCountry()`, `getVariant()`.
- `toLanguageTag()` của các ví dụ well-formed và canonical.
- `getUnicodeLocaleType("nu")`, `getUnicodeLocaleAttributes()`.
- `IllformedLocaleException` với giá trị sai cú pháp.
- `clear()`, `clearExtensions()`, `setLanguageTag()` reset state.
- `Locale` xây xong không đổi khi Builder thay sau đó.

Không cần mở một cửa sổ UI hay truy cập Internet để unit test việc tạo Locale.

### 19.2. Kiểm tra parser với dữ liệu boundary

Các trường hợp có giá trị học tập:

1. Language-only `"vi"`.
2. Language + region `"vi-VN"`.
3. Language + script + region `"zh-Hant-TW"`.
4. Numeric region `"es-419"`.
5. Unicode keywords `"th-TH-u-ca-buddhist-nu-thai"`.
6. Private-use extension `"en-US-x-demo-case"`.
7. Variant hợp lệ `"sl-SI-rozaj"`.
8. Invalid language `"en_US"`.
9. Invalid script `"Lat"`.
10. Invalid region `"VNM"`.
11. Invalid tag `"en-US-@"`.
12. Invalid Unicode locale keyword key `"calendar"`.
13. Null/blank policy của API nhận user input.
14. Tag well-formed nhưng không nằm trong supported locale allowlist.

### 19.3. Không assert localized output bằng một string duy nhất trên mọi JDK

Ví dụ text currency/date có thể đổi punctuation, spaces, currency name, symbol hoặc pattern khi CLDR được cập nhật. Nếu dự án cần snapshot/golden tests, hãy:

- Pin runtime JDK/provider và CLDR data trong test environment.
- Kiểm tra vùng/formatter cụ thể.
- Chấp nhận việc cập nhật golden snapshots theo thay đổi dữ liệu locale có chủ đích.
- Tách test cấu trúc Locale (ổn định) khỏi test behavior formatter (có dữ liệu external).

### 19.4. Không phụ thuộc vào JVM default Locale trong test

`Locale.getDefault()` có thể khác theo máy, OS, process settings hoặc test khác. Đặt Locale tường minh khi format/parsing; không dùng `Locale.setDefault` trên test chạy song song nếu không kiểm soát global state.

Ví dụ tốt:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.SHORT)
        .withLocale(locale);
```

Ở đây `locale` là đầu vào đã được parse/validate. Caller không bị phụ thuộc tùy tiện vào cấu hình OS của CI.

## 20. Những lỗi thường gặp khi tạo Locale

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| `setLanguage("vi-VN")` | Chỉ nhận language subtag | `setLanguageTag("vi-VN")` hoặc language + region |
| `setLanguage("en_US")` | Underscore không thuộc language subtag | Tách fields hoặc dùng BCP 47 tag |
| `setScript("Lat")` | Script subtag sai độ dài | Dùng mã script well-formed như `Latn` |
| `setRegion("VNM")` | Region 3 chữ cái sai cú pháp BCP 47 | `"VN"` hoặc mã M.49 nếu đúng |
| `setRegion("419")` bị cho là luôn sai | 3 chữ số M.49 hợp lệ | Cho phép region number khi phù hợp |
| Mặc định script có thể suy chắc từ language | Một language có nhiều script | Đặt script khi cần |
| Tưởng `setScript("Hant")` tự transliterate | Locale là metadata | Dùng text conversion riêng |
| Dùng `String.split("-")` tự parse mọi tag | Script/variant/extensions phức tạp | `setLanguageTag` |
| Mong `setLanguageTag` bỏ phần lỗi | Builder là strict | Bắt `IllformedLocaleException` |
| Dùng `forLanguageTag` rồi tin toàn input đúng | Có thể bỏ trailing invalid | Builder strict cho validation |
| Không xử lý null/empty tag | `setLanguageTag(null)` reset builder | Validate input theo product contract |
| Nghĩ `Locale.ROOT` là locale mặc định của máy | ROOT là locale không xác định | Fallback rõ, không dùng ROOT như user locale |
| Reuse Builder chỉ thay language | State script/region/extension còn lại | Builder mới hoặc clear |
| Share Builder mutable giữa requests | Race và rò cấu hình | Per-request Builder |
| Nghĩ `build()` reset Builder | Không tự reset | Clear nếu cần |
| Nghĩ build sau setRegion thay Locale trước | Locale immutable | Giữ các Locale values độc lập |
| So sánh `Locale.toString()` với BCP 47 tag | Biểu diễn không tương đương | `toLanguageTag()` |
| Tự lower-case tag bằng OS locale | Case conversion locale-sensitive | Builder chuẩn hóa |
| Dùng display name làm khóa dữ liệu | Display text đổi theo provider | Tag canonical + allowlist |
| Xem well-formed là đã được dịch | Builder không cấp translation resources | Bundle/support validation |
| Xem `u-ca` đảm bảo mọi calendar API áp dụng | Provider có thể không hỗ trợ | Test formatter/provider thực |
| Xem `u-nu` đảm bảo mọi số đều theo hệ đó | Không phải mọi API xử lý giống nhau | Test output mà sản phẩm dùng |
| Dùng locale để suy currency giao dịch | Currency khác display locale | Mã Currency của amount riêng |
| Dùng locale để suy timezone | Locale không phải ZoneId | `ZoneId` riêng |
| Dùng Builder để chuẩn hóa Unicode text | Builder chỉ quản lý locale tags | `Normalizer`/`Collator` khi cần |
| Catch mọi `RuntimeException` rồi trả input sai | Che bug không liên quan | Catch `IllformedLocaleException` đúng scope |
| Hardcode format pattern golden cross-JDK | CLDR/provider thay đổi | Test cấu trúc, pin data integration |
| Dùng `Locale.setDefault` trong test song song | Thay global process state | Truyền Locale tường minh |
| Dùng private-use extension chứa bí mật | Tag có thể log/transmit | Không lưu PII/secrets vào language tag |

## 21. Bài tập tự luyện kèm đáp án

### Bài 1 — Tạo Vietnamese locale

Tạo Locale cho tiếng Việt tại Việt Nam với Builder như thế nào?

**Đáp án:** `new Locale.Builder().setLanguage("vi").setRegion("VN").build()`; `toLanguageTag()` là `vi-VN`.

### Bài 2 — Language và tag

`setLanguage("vi-VN")` có đúng không?

**Đáp án:** Không. `setLanguage` chỉ nhận language subtag. Dùng `setLanguageTag("vi-VN")` hoặc tách `setLanguage`/`setRegion`.

### Bài 3 — Script

Tạo `zh-Hant-TW` không dùng `setLanguageTag` như thế nào?

**Đáp án:** `setLanguage("zh").setScript("Hant").setRegion("TW").build()`.

### Bài 4 — Casing

`setLanguage("VI").setRegion("vn")` sẽ xuất tag gì?

**Đáp án:** `vi-VN`, Builder chuẩn hóa casing.

### Bài 5 — Numeric region

`setLanguage("es").setRegion("419")` có hợp lệ không?

**Đáp án:** Có. Region có thể là ba chữ số UN M.49; tag `es-419`.

### Bài 6 — Region ba chữ

`setRegion("VNM")` có hợp lệ không?

**Đáp án:** Không; `IllformedLocaleException` vì region 3 chữ cái không đúng cú pháp Builder.

### Bài 7 — Variant

`setVariant("rozaj")` có đúng cú pháp không?

**Đáp án:** Có; variant subtag năm ký tự alphanumeric. Tag ví dụ `sl-SI-rozaj`.

### Bài 8 — Unsupported locale

Builder chấp nhận tag theo grammar. Có chắc ứng dụng có bản dịch tương ứng không?

**Đáp án:** Không. Phải kiểm tra supported locale list và resource bundle thực tế.

### Bài 9 — Unicode calendar

Đặt calendar key cho tiếng Thái lịch Phật giáo thế nào?

**Đáp án:** `setUnicodeLocaleKeyword("ca","buddhist")` với language/region thích hợp.

### Bài 10 — Unicode numbering

Đặt numbering system cho chữ số Thái?

**Đáp án:** `setUnicodeLocaleKeyword("nu","thai")`.

### Bài 11 — getUnicodeLocaleType

Nếu đã set `ca=buddhist`, gọi `getUnicodeLocaleType("ca")` trả gì?

**Đáp án:** `"buddhist"`.

### Bài 12 — Invalid keyword

`setUnicodeLocaleKeyword("calendar","gregory")` có hợp lệ không?

**Đáp án:** Không. Key phải theo Unicode locale keyword syntax, thông thường hai ký tự; `"calendar"` gây `IllformedLocaleException`.

### Bài 13 — Attribute

Làm sao tạo `en-US-u-emoji` bằng Builder?

**Đáp án:** `setLanguageTag("en-US").addUnicodeLocaleAttribute("emoji").build()`.

### Bài 14 — Private use

Dùng `setExtension('x',"demo-case")` tạo đoạn tag nào?

**Đáp án:** `x-demo-case` sau các subtags chính. Nó chỉ có ý nghĩa riêng nếu hệ thống thỏa thuận.

### Bài 15 — clearExtensions

Builder từ `en-US-u-ca-gregory` gọi `clearExtensions().build()` cho tag nào?

**Đáp án:** `en-US`, language/region vẫn giữ.

### Bài 16 — clear

Builder có language/region, gọi `clear().build()` cho gì?

**Đáp án:** `Locale.ROOT`, `toLanguageTag()` là `und`.

### Bài 17 — setLanguageTag reset

Builder đang có `en-US`, sau đó `setLanguageTag("fr-CA")`. Còn giữ region `US` không?

**Đáp án:** Không; `setLanguageTag` reset toàn state theo tag mới, kết quả `fr-CA`.

### Bài 18 — Build không reset

`Locale first=builder.build();` rồi `builder.setRegion("GB")`. First có đổi region không?

**Đáp án:** Không. Locale immutable; chỉ Builder mutable.

### Bài 19 — Strict parser

`new Locale.Builder().setLanguageTag("en-US-@")` tạo Locale nào?

**Đáp án:** Không tạo Locale; setter ném `IllformedLocaleException`.

### Bài 20 — Lenient parser

`Locale.forLanguageTag("en-US-@")` trong demo JDK 17 trả tag gì?

**Đáp án:** `en-US`, phần lỗi và theo sau bị bỏ. Đó là lý do không dùng lenient parser để chặn input sai cú pháp.

### Bài 21 — Locale.getDefault

Vì sao test nên dùng `DateTimeFormatter.withLocale(locale)` thay vì dựa vào default locale?

**Đáp án:** Vì default locale phụ thuộc process/máy và có thể bị thay bởi test khác; truyền explicit locale giúp ổn định input.

### Bài 22 — Date format golden

Builder tag `vi-VN` đúng. Có nên luôn assert format ngày phải là đúng một string cố định trên mọi JDK không?

**Đáp án:** Không. Pattern/CLDR provider có thể đổi; test riêng Locale components và pin runtime khi snapshot formatter output.

### Bài 23 — Currency

Người dùng dùng `en-US` nhưng thanh toán 100.000 VND. Locale có tự đổi currency của giao dịch sang USD không?

**Đáp án:** Không. Currency amount cần được truyền riêng, format locale là sở thích hiển thị.

### Bài 24 — Timezone

`new Locale.Builder().setLanguageTag("vi-VN").build()` có biết giờ ở Hà Nội không?

**Đáp án:** Không. Dùng `ZoneId` và thông tin thời điểm riêng.

### Bài 25 — Unicode normalization

Builder có tự đổi văn bản tiếng Việt đang ở NFD sang NFC không?

**Đáp án:** Không. Nó xử lý locale tags; dùng `java.text.Normalizer` khi cần text normalization.

### Bài 26 — Service support

`th-TH-u-ca-buddhist-nu-thai` hợp lệ. Có đảm bảo mọi formatter trên mọi JDK in lịch Phật giáo và chữ số Thái không?

**Đáp án:** Không. Phải kiểm tra provider/formatter thực tế; Builder chỉ lưu metadata và kiểm tra cú pháp.

### Bài 27 — setLocale

`setLocale(existingLocale)` có giữ nguyên Builder state cũ rồi merge không?

**Đáp án:** Không. Nó reset Builder theo Locale được cung cấp, có kiểm tra well-formed fields.

### Bài 28 — Null tag

`new Locale.Builder().setLanguageTag(null).build()` có tự ném NullPointerException không?

**Đáp án:** Không; theo Javadoc `setLanguageTag(null)` reset Builder. Nếu API yêu cầu tag không null, validate trước.

### Bài 29 — Language-only vs region

Nếu người dùng chỉ chọn tiếng Việt, có bắt buộc tự thêm `VN` không?

**Đáp án:** Không. `"vi"` là locale language-only hợp lệ; region nên dựa vào preference/use case, không tự suy chắc.

### Bài 30 — API serialization

Nên gửi cho client `locale.toString()` hay `locale.toLanguageTag()` khi field contract là BCP 47?

**Đáp án:** `toLanguageTag()` để xuất tag đúng kiểu BCP 47.

## 22. Checklist thực tế trước khi dùng Locale.Builder

- [ ] Xác định dữ liệu đầu vào là **language**, hay một **BCP 47 tag hoàn chỉnh**.
- [ ] Dùng `setLanguage` chỉ cho language, không truyền `vi-VN` vào đó.
- [ ] Dùng `setLanguageTag` nếu muốn strict parse toàn bộ tag.
- [ ] Catch `IllformedLocaleException` ở boundary input validation.
- [ ] Tự xử lý null/blank theo business policy trước khi gọi Builder.
- [ ] Biết `setLanguageTag(null)`/empty reset Builder.
- [ ] Đọc `getLanguage`, `getScript`, `getCountry`, `getVariant` khi cần.
- [ ] Đặt `script` khi tính năng thực sự cần phân biệt hệ chữ viết.
- [ ] Nhớ region có thể là 2 chữ **hoặc 3 chữ số** UN M.49.
- [ ] Với variant, tuân grammar BCP 47 strict.
- [ ] Dùng `setUnicodeLocaleKeyword` cho calendar/numbering preferences.
- [ ] Dùng `addUnicodeLocaleAttribute`/`removeUnicodeLocaleAttribute` nếu đúng semantic.
- [ ] Không lạm dụng private-use extension để nhét dữ liệu nghiệp vụ.
- [ ] Hiểu `setExtension('u',value)` thay Unicode keywords hiện tại.
- [ ] Hiểu Builder mutable và Locale immutable.
- [ ] Không share cùng Builder mutable giữa threads/requests.
- [ ] Dùng Builder mới hoặc `clear()` để tránh rò state giữa users.
- [ ] Phân biệt `clearExtensions()` với `clear()`.
- [ ] Phân biệt `setLocale`/`setLanguageTag` reset toàn bộ state với setters từng trường.
- [ ] Dùng `toLanguageTag()` khi lưu/truyền BCP 47 tags.
- [ ] Không dùng `toString`/display name như ngôn ngữ tag API.
- [ ] Kiểm tra supported locales ở tầng ứng dụng, không chỉ syntax.
- [ ] Test Unicode keyword support trên formatter/provider thực.
- [ ] Dùng explicit Locale cho formatter, không đổi default JVM tùy tiện.
- [ ] Không suy currency, timezone, encoding hoặc quyền truy cập từ locale.
- [ ] Tách text Unicode normalization/collation khỏi locale construction.
- [ ] Tránh expected localized output cố định xuyên các bản JDK/CLDR.
- [ ] Có test strict invalid, lenient parse, clear, extension, Builder reuse.
- [ ] Dùng API Java vẫn còn hiện hành; kiểm tra version nếu dùng phương thức mới.
- [ ] Biên dịch và chạy Java 17+ trước khi đưa code mẫu vào đào tạo.

## 23. Tài liệu Java và BCP 47 chính thức

- [Java SE 26 — Locale.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.Builder.html): API setter, kiểm tra cú pháp, `setLanguageTag`, `clear`, Unicode extensions, `setLocale` và `build`; `Locale.Builder` vẫn hiện hành.
- [Java SE 25 — Locale.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.Builder.html): hướng dẫn các setters và `IllformedLocaleException`; Builder được giới thiệu từ Java 7.
- [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): locale fields, BCP 47 tags, `forLanguageTag`, `toLanguageTag`, `getUnicodeLocaleType`.
- [Java SE 17 — IllformedLocaleException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IllformedLocaleException.html): ngoại lệ cú pháp và `getErrorIndex()`.
- [IETF RFC 5646 — Tags for Identifying Languages](https://www.rfc-editor.org/rfc/rfc5646): BCP 47 language tag syntax; lý do không tự parse tags bằng regex đơn giản.
- [Unicode TR35 — LDML / Unicode Locale Identifier](https://unicode.org/reports/tr35/): các keywords, attributes và locale data conventions.
- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): áp dụng `withLocale` khi format date/time.
- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): format số theo locale.
- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): phân biệt Unicode text normalization với locale construction.

## 24. Tóm tắt

**`Locale.Builder` tạo ra một `Locale` immutable, well-formed theo cú pháp locale/BCP 47**. Nó phù hợp khi cần xây locale từ các trường rõ ràng (`language`, `script`, `region`, `variant`) hoặc từ language tag hoàn chỉnh, nhất là khi bạn muốn phát hiện lỗi ngay bằng `IllformedLocaleException`.

Dùng `setLanguageTag` cho BCP 47 strict; `Locale.forLanguageTag` là lựa chọn lenient có thể bỏ phần tag lỗi. Dùng `setUnicodeLocaleKeyword` hoặc `addUnicodeLocaleAttribute` nếu thật sự cần mô tả calendar/numbering preferences, và nhớ rằng **dữ liệu provider** quyết định formatter hỗ trợ lựa chọn nào.

Đừng nhầm `Locale.Builder` với bộ dịch, timezone, currency, text normalization hay security validator. Chọn Locale có chủ đích, truyền vào formatter tường minh, quản lý Builder mutable theo scope, dùng `toLanguageTag()` cho API/storage và xây allowlist để bảo đảm ứng dụng thực sự hỗ trợ locale mà user chọn.

Những nguyên tắc trên vẫn phù hợp với **Java 17 và các JDK hiện đại**, dù `Locale.Builder` là tính năng bắt đầu từ Java 7.