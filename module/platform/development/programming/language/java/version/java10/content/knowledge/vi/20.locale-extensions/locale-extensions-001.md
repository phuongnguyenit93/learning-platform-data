# Nhãn ngôn ngữ BCP 47 và phần mở rộng Unicode trong Java Locale (Java 10+)

## 1. Mục tiêu bài học

Một ứng dụng quốc tế hóa không chỉ cần biết người dùng muốn **ngôn ngữ nào**, mà còn có thể cần biết họ ưu tiên **hệ chữ số**, **lịch**, **đơn vị tiền tệ**, **ngày bắt đầu tuần**, **quy ước vùng** hoặc **múi giờ** nào.

Java biểu diễn những thông tin này bằng `java.util.Locale` cùng **nhãn ngôn ngữ BCP 47** (*language tag*). Ví dụ:

```text
vi-VN
en-Latn-US
ja-JP-u-ca-japanese
en-US-u-cu-eur-fw-mon
```

Nhãn đầu nói tiếng Việt tại Việt Nam. Nhãn thứ hai mô tả tiếng Anh, chữ Latin, vùng Hoa Kỳ. Hai nhãn còn lại có phần **`-u-`**: đó là **Unicode locale extension**, nơi đặt các tùy chọn bản địa hóa có cấu trúc.

**Đúng phạm vi Java 10:** Java đã hỗ trợ BCP 47 trong `Locale` từ **Java 7**, kể cả các khóa Unicode `ca` (calendar) và `nu` (numbering system). **OpenJDK JEP 314, phát hành trong Java 10**, bổ sung hỗ trợ bốn khóa `cu` (currency), `fw` (first day of week), `rg` (region override) và `tz` (time zone) trong những API Java phù hợp. Những cơ chế này **vẫn được dùng trong Java hiện hành**, không phải API đã lỗi thời.

Sau bài học, bạn có thể:

1. Phân tích cấu trúc nhãn BCP 47 mà không nhầm language, script, region với Unicode keyword.
2. Tạo và đọc `Locale` bằng `forLanguageTag`, `toLanguageTag`, `getUnicodeLocaleType` và `Locale.Builder`.
3. Hiểu chính xác bốn Unicode locale keys mà Java 10 mở rộng hỗ trợ, và API tiêu biểu thực sự đọc chúng.
4. Phân biệt **nhãn hợp cú pháp**, **keyword được lưu trong `Locale`** và **tùy chọn được một dịch vụ bản địa hóa áp dụng**.
5. Viết chương trình Java 17+ chạy được và kiểm chứng hành vi, tránh phụ thuộc `Locale.getDefault()` hoặc tên hiển thị khác nhau giữa JDK.

## 2. BCP 47 là gì?

**IETF BCP 47** là bộ chuẩn định danh ngôn ngữ, bao gồm RFC 5646 (*Tags for Identifying Languages*) và RFC 4647 (*Matching of Language Tags*). Trong Java, `Locale` hỗ trợ biểu diễn và trao đổi các nhãn ngôn ngữ theo BCP 47.

Một nhãn có thể gồm nhiều phần:

```text
language[-Script][-REGION][-variant...][-extension...]
```

Ví dụ:

```text
sr-Latn-RS
│   │    └─ region: RS (Serbia)
│   └────── script: Latn (chữ Latin)
└────────── language: sr (Serbian)
```

Các thành phần phổ biến:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Language | `vi`, `en`, `ja`, `sr` | Mã ngôn ngữ, thường từ ISO 639 |
| Script | `Latn`, `Cyrl`, `Hant` | Hệ chữ, thường mã ISO 15924 |
| Region | `VN`, `US`, `RS`, `TW` | Quốc gia/vùng theo mã được công nhận |
| Variant | `posix` hoặc variant được BCP 47 cho phép | Biến thể cụ thể, ít gặp hơn |
| Extension singleton | `u`, `x` | Mở đầu một nhóm thông tin mở rộng |
| Unicode keyword | `ca-gregory`, `nu-latn` | Cặp khóa–giá trị trong `-u-` |

**Dấu phân cách chuẩn của language tag là dấu gạch ngang `-`**, không phải dấu gạch dưới `_` trong một số cách hiển thị `Locale.toString()`. Nếu muốn lưu hoặc trao đổi language tag đúng mục đích, dùng `toLanguageTag()`.

### 2.1. Quy ước chữ hoa–chữ thường

`Locale` chuẩn hóa các phần quen thuộc:

- Language: thường viết thường, ví dụ `EN` → `en`.
- Script: chữ cái đầu viết hoa, ví dụ `latn` → `Latn`.
- Region: viết hoa, ví dụ `us` → `US`.
- Unicode extension keys và types: chuyển về chữ thường, ví dụ `NU-LATN` → `nu-latn`.

BCP 47 không dựa vào khác biệt hoa/thường để phân biệt nhãn. Vì vậy đừng tự viết logic nghiệp vụ dựa vào cách người dùng viết `EN-us` hay `en-US`; hãy parse và lấy `toLanguageTag()` khi cần dạng biểu diễn nhất quán.

### 2.2. `Locale` là descriptor, không phải bản dịch

Một `Locale` mô tả ưu tiên văn hóa/ngôn ngữ; nó **không chứa mọi bản dịch** hoặc đảm bảo tất cả thư viện sẽ xử lý từng extension. Dịch vụ như `Currency`, `NumberFormat`, `DateFormat`, `DateTimeFormatter` hay `WeekFields` mới là nơi **diễn giải những ưu tiên liên quan** khi tạo kết quả.

Ví dụ:

```java
var locale = java.util.Locale.forLanguageTag("vi-VN-u-fw-mon");
```

`locale` ghi rằng ngôn ngữ là tiếng Việt, vùng là Việt Nam và Unicode keyword `fw` yêu cầu thứ Hai là đầu tuần. Nhưng đoạn này **không tự thay đổi** `Locale.getDefault()`, lịch hệ thống hay cài đặt của mọi thư viện.

## 3. Unicode locale extension `-u-` hoạt động thế nào?

Theo Unicode CLDR/UTS #35, nhãn BCP 47 có thể chứa **Unicode locale extension** với singleton `u`. Trong extension đó, các **keyword** thường có cấu trúc:

```text
-u-<key>-<type>-<key>-<type>...
```

Ví dụ:

```text
en-US-u-ca-gregory-nu-latn
      │ │        │  └─ latn: chữ số theo hệ Latin
      │ └─────── │
      │ gregory: kiểu lịch Gregory
      │          └─ nu: keyword hệ chữ số
      └─ ca: keyword lịch
```

Đọc theo thứ tự:

- `en-US`: phần định danh ngôn ngữ/vùng cơ sở.
- `-u-`: bắt đầu Unicode locale extension.
- `ca-gregory`: ưu tiên kiểu lịch Gregorian.
- `nu-latn`: ưu tiên hệ chữ số Latin.

Một key Unicode thường gồm **hai ký tự chữ/số**, còn type có quy tắc hình thức riêng. Một số key có type dài hơn một subtag. Vì vậy **không nên parse bằng cách giả định cứ hai thành phần là một cặp**; sử dụng `Locale`/`Locale.Builder` để parse và truy vấn.

### 3.1. Các API truy vấn extension

`java.util.Locale` cung cấp:

```java
Locale locale = Locale.forLanguageTag(
        "en-US-u-ca-gregory-nu-latn");

locale.getLanguage();               // "en"
locale.getCountry();                // "US"
locale.getUnicodeLocaleType("ca");  // "gregory"
locale.getUnicodeLocaleType("nu");  // "latn"
locale.getExtension(Locale.UNICODE_LOCALE_EXTENSION);
locale.getUnicodeLocaleKeys();
locale.getUnicodeLocaleAttributes();
locale.toLanguageTag();
```

Đây là đoạn **minh họa trong một phương thức có `import java.util.Locale;`**.

- `getUnicodeLocaleType("ca")` trả về type của key `ca`; nếu key không có, thường trả `null`.
- `getUnicodeLocaleKeys()` cho biết tập key Unicode hiện có.
- `getExtension(Locale.UNICODE_LOCALE_EXTENSION)` lấy **giá trị của extension `u`**, không kèm ký tự `u-` ở đầu.
- `getUnicodeLocaleAttributes()` dành cho các attribute Unicode nếu có; **attribute** khác với cặp key–type.
- `toLanguageTag()` xây dựng lại nhãn BCP 47 ở dạng chuẩn hóa.

### 3.2. Thứ tự key được chuẩn hóa

`Locale` có thể sắp xếp Unicode keyword keys theo thứ tự chữ cái khi xuất thành language tag:

```java
var locale = java.util.Locale.forLanguageTag(
        "EN-latn-us-u-NU-LATN-CA-GREGORY");

System.out.println(locale.toLanguageTag());
```

Kết quả:

```text
en-Latn-US-u-ca-gregory-nu-latn
```

Input viết `nu` trước `ca`, nhưng output sắp `ca` trước `nu`. Sự chuẩn hóa này **không làm thay đổi ý nghĩa** của hai keyword. Khi so sánh các tùy chọn, nên dùng `Locale` và API của nó, không so chuỗi input chưa chuẩn hóa.

### 3.3. Extension `u` khác `x`

BCP 47 còn có singleton `x` cho **private use**. Ví dụ:

```text
en-US-x-example
```

Đó không phải Unicode locale keyword. `Locale.UNICODE_LOCALE_EXTENSION` chỉ tới `'u'`, không phải `'x'`. Không nhầm các tag chứa `-x-` với tag chứa `-u-`; thư viện chuẩn không có nghĩa vụ diễn giải arbitrary private-use subtags như lịch, tiền tệ hay múi giờ.

## 4. Các key Unicode quan trọng và đóng góp của Java 10

**OpenJDK JEP 314** có trọng tâm cụ thể, không phải “Java 10 mới hỗ trợ toàn bộ BCP 47”.

| Key | Ý nghĩa | Ví dụ type và language tag | Ghi chú phiên bản |
| --- | --- | --- | --- |
| `ca` | Calendar type | `ja-JP-u-ca-japanese`, `en-US-u-ca-gregory` | Đã được hỗ trợ trong các API liên quan trước Java 10 |
| `nu` | Numbering system | `th-TH-u-nu-thai`, `en-US-u-nu-latn` | Đã được hỗ trợ trước Java 10 |
| `cu` | Currency type | `en-US-u-cu-eur` | Java 10 mở rộng hỗ trợ |
| `fw` | First day of week | `en-US-u-fw-mon` | Java 10 mở rộng hỗ trợ |
| `rg` | Region override | `en-US-u-rg-gbzzzz` | Java 10 mở rộng hỗ trợ |
| `tz` | Time zone | `en-US-u-tz-usnyc` | Java 10 mở rộng hỗ trợ |

**Hãy phân biệt hai cấp độ hỗ trợ**:

1. `Locale` có thể **parse/lưu/trả lại** một Unicode keyword hợp cú pháp.
2. Một API bản địa hóa cụ thể **có thể hoặc không** diễn giải key/type đó để thay đổi hành vi.

JEP 314 bổ sung hỗ trợ thực tế của bốn key trong **những API có liên quan**, không bảo đảm mọi formatter của mọi nhà cung cấp hoặc mọi phiên bản xử lý mọi key Unicode trên thế giới. Locale data của JDK và các locale service provider có thể được cập nhật theo thời gian.

### 4.1. `cu`: chọn loại tiền tệ

```java
var euroLocale = java.util.Locale.forLanguageTag(
        "en-US-u-cu-eur");

var currency = java.util.Currency.getInstance(euroLocale);
System.out.println(currency.getCurrencyCode()); // EUR
```

Language/region cơ sở vẫn là `en-US`. Keyword `cu-eur` yêu cầu currency type là Euro trong API `Currency.getInstance(locale)`.

**Phân biệt:** `cu` không tự đổi ngôn ngữ, vùng `getCountry()` hay mọi định dạng văn bản. Nó là **tùy chọn tiền tệ** được những API liên quan diễn giải.

### 4.2. `fw`: chọn ngày bắt đầu tuần

```java
var locale = java.util.Locale.forLanguageTag(
        "en-US-u-fw-mon");

var fields = java.time.temporal.WeekFields.of(locale);
System.out.println(fields.getFirstDayOfWeek()); // MONDAY
```

`fw-mon` yêu cầu **Monday** là ngày đầu tuần. `WeekFields.of(locale)` là API có hợp đồng phản ánh tùy chọn này.

Một số vùng mặc định khác có thể bắt đầu tuần vào Chủ nhật hoặc Thứ hai. Nếu ứng dụng cần quy tắc cụ thể, dùng Unicode extension hoặc `WeekFields` được cấu hình tường minh, đừng dựa vào locale mặc định của máy đang chạy.

### 4.3. `rg`: ghi đè vùng dùng cho dữ liệu bản địa hóa

```java
var locale = java.util.Locale.forLanguageTag(
        "en-US-u-rg-gbzzzz");

System.out.println(locale.getCountry()); // US
System.out.println(
        java.util.Currency.getInstance(locale).getCurrencyCode());
// GBP
```

`rg-gbzzzz` là dạng **region override** yêu cầu dùng dữ liệu vùng Vương quốc Anh ở các dịch vụ có hỗ trợ. Cú pháp type `rg` với mã vùng `gb` có hậu tố `zzzz` theo Unicode locale identifier.

Điểm tinh tế:

- `locale.getCountry()` **vẫn là `"US"`**, vì thành phần region của language tag cơ sở chưa thay đổi.
- `Currency.getInstance(locale)` có thể áp dụng **`rg=GB`** và trả `GBP`.
- `rg` là hướng dẫn cho **các dịch vụ đọc locale data**, không phải phép thay tất cả các trường trong `Locale` hay biến object thành một `Locale.UK` mới.

Không viết mã tự cắt bỏ `zzzz` rồi gán nó vào `getCountry()`. Sử dụng đúng API xử lý `rg` cho nghiệp vụ liên quan.

### 4.4. `tz`: chỉ định múi giờ theo Unicode short ID

```java
var locale = java.util.Locale.forLanguageTag(
        "en-US-u-tz-usnyc");

var format = java.text.DateFormat.getDateTimeInstance(
        java.text.DateFormat.SHORT,
        java.text.DateFormat.SHORT,
        locale);

System.out.println(format.getTimeZone().getID());
// America/New_York
```

`tz-usnyc` là **Unicode/CLDR short time-zone ID**, biểu diễn múi giờ New York trong ví dụ. Nó **không phải** cùng cú pháp với zone ID IANA `America/New_York`.

Các API định dạng liên quan như `DateFormat.get*Instance` và `DateTimeFormatter.localizedBy(locale)` có thể dùng thông tin này. **Không tự hiểu rằng mọi API thời gian hoặc `ZoneId.systemDefault()` đã thay đổi** chỉ vì có một `Locale` mang `tz`. Nếu xử lý lịch hẹn/instant thực sự, hãy xác định một `ZoneId` thích hợp và quản lý rõ thời điểm/chuyển vùng giờ trong mô hình dữ liệu.

## 5. API nào đã được JEP 314 bổ sung hỗ trợ?

JEP 314 mô tả những tác động quan trọng sau:

| API tiêu biểu | Unicode keyword được xét trong JEP 314 |
| --- | --- |
| `java.text.DateFormat.get*Instance` | `ca`, `rg`, `tz` |
| `java.text.DateFormatSymbols.getInstance` | `rg` |
| `java.text.DecimalFormatSymbols.getInstance` | `rg` |
| `java.text.NumberFormat.get*Instance` | `nu`, `rg` |
| `java.time.format.DateTimeFormatter.localizedBy` | `ca`, `rg`, `tz` |
| `java.time.format.DateTimeFormatterBuilder.getLocalizedDateTimePattern` | `rg` |
| `java.time.format.DecimalStyle.of` | `nu`, `rg` |
| `java.time.temporal.WeekFields.of` | `fw`, `rg` |
| `java.util.Calendar` (first day/minimum days) | `fw`, `rg` |
| `java.util.Currency.getInstance` | `cu`, `rg` |

Bảng trên được trình bày theo **phạm vi thay đổi JEP 314**, không phải toàn bộ các API hỗ trợ Unicode extension trên mọi JDK. Tùy dịch vụ, dữ liệu locale từ nhà cung cấp có thể khác giữa các bản Java.

### 5.1. Một keyword được hiểu khác nhau trong các dịch vụ

Ví dụ `rg-gbzzzz` có thể ảnh hưởng đến:

- tiền tệ mặc định của vùng;
- quy tắc đầu tuần;
- một số mẫu định dạng số và ngày giờ theo vùng.

Nhưng **language** vẫn là `en`, **country cơ sở** vẫn là `US`. Đây là một sự khác biệt thiết kế quan trọng: **locale identifier** và **locale-sensitive service behavior** không phải cùng một trường dữ liệu.

### 5.2. Không ghép “mọi tùy chọn” thành một lệnh duy nhất rồi cho rằng đã được áp dụng

`Locale` có thể đồng thời chứa `cu`, `fw`, `rg`, `tz`. Tuy nhiên, mỗi API có trách nhiệm đọc những key liên quan tới nó. Ví dụ, `WeekFields.of` không có nhiệm vụ đổi currency; `Currency.getInstance` không điều khiển múi giờ.

Vì vậy, muốn kiểm thử từng tùy chọn, hãy gọi **API đúng phạm vi** và kiểm tra kết quả quan sát được, không chỉ kiểm tra `locale.getUnicodeLocaleType(...)`.

## 6. Tạo Locale từ BCP 47 bằng API chuẩn

### 6.1. `Locale.forLanguageTag(String)`

Đây là cách ngắn gọn khi nguồn đã là language tag:

```java
var locale = java.util.Locale.forLanguageTag(
        "vi-VN-u-fw-mon-nu-latn");
```

`locale` chứa language `vi`, region `VN` và hai Unicode keywords `fw`, `nu`. API này có từ Java 7 và vẫn là lựa chọn tốt khi parse tag BCP 47.

**Lưu ý về input sai cú pháp:** `Locale.forLanguageTag` **khá khoan dung**; nếu gặp subtag không hợp lệ, nó có thể bỏ subtag lỗi và các phần sau. Không dùng nó làm **validator nghiêm ngặt duy nhất** cho dữ liệu do client bên ngoài gửi nếu cần báo lỗi thay vì âm thầm cắt phần thông tin.

### 6.2. `Locale.Builder` để kiểm tra tính hợp cú pháp

Nếu muốn phát hiện sớm một tag sai cú pháp:

```java
var strict = new java.util.Locale.Builder()
        .setLanguageTag("vi-VN-u-fw-mon")
        .build();
```

`Builder.setLanguageTag` kiểm tra cú pháp, và có thể ném `IllformedLocaleException` khi nhãn không well-formed. Khác với `forLanguageTag`, Builder không chỉ bỏ đuôi lỗi rồi âm thầm tiếp tục.

Ví dụ hai cách xử lý cùng input:

```java
var lenient = java.util.Locale.forLanguageTag("en-US-@");
System.out.println(lenient.toLanguageTag()); // en-US

try {
    new java.util.Locale.Builder()
            .setLanguageTag("en-US-@")
            .build();
} catch (java.util.IllformedLocaleException ex) {
    System.out.println("strictBuilderRejected=true");
}
```

**Không nhầm strict syntax validation với semantic support:** Builder kiểm tra hình thức của BCP 47, **không xác nhận tất cả mã vùng, keyword hoặc type có được đăng ký và hỗ trợ đầy đủ bởi một nhà cung cấp dữ liệu locale**.

### 6.3. Tạo từng thành phần thay vì nối chuỗi thủ công

`Locale.Builder` còn hỗ trợ các setter:

```java
var locale = new java.util.Locale.Builder()
        .setLanguage("vi")
        .setRegion("VN")
        .setUnicodeLocaleKeyword("fw", "mon")
        .setUnicodeLocaleKeyword("nu", "latn")
        .build();

System.out.println(locale.toLanguageTag());
// vi-VN-u-fw-mon-nu-latn
```

Nếu có script, dùng `setScript("Latn")` hoặc mã phù hợp. Nếu muốn gỡ một Unicode keyword, `setUnicodeLocaleKeyword("fw", null)` trên Builder sẽ xóa keyword đó (không có nghĩa tạo một key với type literal `null`).

`Locale.Builder` giúp code tránh lỗi chèn dấu `-`, trùng singleton hoặc ghi sai vị trí keyword khi dựng một locale từ nhiều cấu hình.

### 6.4. `Locale` có tính bất biến

Đối tượng `Locale` là **immutable**. Khi tạo một Locale qua Builder và muốn bổ sung/thay đổi keyword, bạn tạo Locale mới, không sửa trực tiếp object cũ:

```java
var original = java.util.Locale.forLanguageTag(
        "vi-VN-u-nu-latn");

var extended = new java.util.Locale.Builder()
        .setLocale(original)
        .setUnicodeLocaleKeyword("fw", "mon")
        .build();
```

`original` vẫn giữ tag cũ; `extended` là Locale mang thêm `fw-mon`. Đây là cách phù hợp khi điều chỉnh cấu hình per-request, không cần thay đổi `Locale.getDefault()` của cả JVM.

### 6.5. `stripExtensions()` có tác dụng gì?

```java
var withExtensions = java.util.Locale.forLanguageTag(
        "vi-VN-u-fw-mon-nu-latn");
var base = withExtensions.stripExtensions();

System.out.println(base.toLanguageTag()); // vi-VN
```

`stripExtensions` trả Locale không còn extension, vẫn giữ những trường cơ bản tương ứng. Nó hữu ích khi một thuật toán thực sự chỉ cần language/script/region. Nhưng **đừng bỏ Unicode extensions chỉ để đơn giản hóa nếu ứng dụng đang cần giữ currency, calendar, numbering system hoặc time-zone preferences**.

## 7. BCP 47 hợp cú pháp không đồng nghĩa được áp dụng đầy đủ

### 7.1. Builder có thể chấp nhận key chưa được dịch vụ hiểu

Ví dụ:

```java
var opaque = java.util.Locale.forLanguageTag(
        "en-US-u-zz-abc");

System.out.println(
        opaque.getUnicodeLocaleType("zz")); // abc
```

Ở đây `zz` và `abc` có hình thức key–type chấp nhận được nên `Locale` có thể **giữ lại và trả lại** chúng. Điều đó **không** có nghĩa `NumberFormat`, `Currency` hoặc `DateFormat` sẽ hiểu `zz` là một yêu cầu hợp lệ nào đó.

Đây là sự phân biệt nền tảng:

1. **Well-formed:** tag thỏa ngữ pháp BCP 47 mà `Locale` chấp nhận.
2. **Registered/valid:** các subtag/key/type có đăng ký và phù hợp với tiêu chuẩn liên quan.
3. **Supported by a specific service:** thư viện và locale data thực sự áp dụng ý nghĩa của key/type ấy.

**Bước 1 không tự kéo theo bước 2 hoặc bước 3.**

### 7.2. Dữ liệu bản địa hóa thay đổi theo JDK/provider

Một bản Java có thể cung cấp quy tắc ngày giờ, tên vùng, các chuỗi dịch hoặc dữ liệu CLDR khác một bản khác. Vì vậy:

- Không cố định mọi đầu ra **`getDisplayName()`** theo một câu tiếng Anh cụ thể.
- Không khẳng định tất cả locale-sensitive formatters đều hiểu mọi Unicode keyword.
- Nếu ứng dụng yêu cầu một quy ước nghiêm ngặt độc lập locale data, hãy xây dựng cấu hình nghiệp vụ explicit, rồi kiểm thử trên runtime mục tiêu.
- Nếu một type không được hỗ trợ, dịch vụ có thể sử dụng quy tắc fallback của chính API đó thay vì báo lỗi lúc tạo `Locale`.

### 7.3. Đừng tự parse keyword bằng `split("-")`

Với một số Unicode locale keys, type có thể gồm **nhiều subtags**. Một chuỗi BCP 47 cũng có language, script, region, variant, nhiều extension và private-use phần khác.

Do đó, đừng viết thuật toán kiểu “tìm chữ `u` rồi cứ lấy lần lượt một key và một type” nếu muốn hỗ trợ BCP 47 tổng quát. Sử dụng:

```java
locale.getUnicodeLocaleType("ca");
locale.getUnicodeLocaleKeys();
locale.getExtension(Locale.UNICODE_LOCALE_EXTENSION);
```

và `Locale.Builder` để đặt keyword.

## 8. Không nhầm locale, default locale và HTTP language negotiation

### 8.1. Chỉ định Locale theo thao tác

Các factory như `NumberFormat.getInstance(locale)`, `DateFormat.getDateInstance(style, locale)` và `WeekFields.of(locale)` cho phép truyền **một Locale cụ thể**.

Ưu tiên truyền Locale của user/request vào nơi cần thiết thay vì gọi `Locale.setDefault(...)` trong một server đa người dùng. `setDefault` thay đổi trạng thái dùng chung của runtime, có thể làm các request khác ảnh hưởng nhau.

Nếu ứng dụng muốn một format cố định, hãy định nghĩa Locale/ký hiệu/zone rõ ràng. Ví dụ một request từ người dùng Việt Nam có thể mang ngôn ngữ `vi`, vùng `VN`, và lựa chọn đầu tuần riêng; không nên tự suy luận nó chỉ từ máy chủ đặt ở quốc gia nào.

### 8.2. Language tag không phải toàn bộ giá trị header `Accept-Language`

HTTP có thể gửi:

```text
Accept-Language: vi-VN, en-US;q=0.8, en;q=0.6
```

Đây là **danh sách ưu tiên với trọng số**, không phải một language tag đơn lẻ. Không đưa cả chuỗi sau dấu hai chấm vào `Locale.forLanguageTag(...)`.

Java có `Locale.LanguageRange.parse(...)` và các API `Locale.lookup`/`filter` cho matching theo RFC 4647. Một ứng dụng web còn có thể dùng cơ chế locale resolution của framework. Việc **chọn Locale tốt nhất từ danh sách ngôn ngữ** là bước riêng với việc **giải thích Unicode extension của Locale đã chọn**.

### 8.3. Locale không phải định danh người dùng hoặc địa chỉ

Một người dùng có thể chọn `en-US-u-cu-eur` nhưng sống ở vùng khác; `rg` là override cho dữ liệu bản địa hóa, không phải bằng chứng địa chỉ cư trú. `tz` là ưu tiên timezone trong một số API, không phải phép định vị vật lý. Đừng dùng language tag để suy ra thông tin cá nhân hay quốc gia thực tế của người sử dụng.

## 9. Chương trình Java 17+ độc lập, có kết quả kiểm chứng

Lưu toàn bộ mã sau vào file **`LocaleTagDemo.java`**:

```java
import java.text.DateFormat;
import java.time.temporal.WeekFields;
import java.util.Currency;
import java.util.IllformedLocaleException;
import java.util.Locale;

public class LocaleTagDemo {
    public static void main(String[] args) {
        var tag = Locale.forLanguageTag(
                "EN-latn-us-u-NU-LATN-CA-GREGORY");

        System.out.println("normalized=" + tag.toLanguageTag());
        System.out.println("language=" + tag.getLanguage());
        System.out.println("script=" + tag.getScript());
        System.out.println("country=" + tag.getCountry());
        System.out.println("calendar=" +
                tag.getUnicodeLocaleType("ca"));
        System.out.println("numbers=" +
                tag.getUnicodeLocaleType("nu"));
        System.out.println("unicodeExtension=" +
                tag.getExtension(Locale.UNICODE_LOCALE_EXTENSION));

        var regional = Locale.forLanguageTag(
                "en-US-u-cu-eur-fw-mon-rg-gbzzzz-tz-usnyc");
        System.out.println("regionalTag=" + regional.toLanguageTag());
        System.out.println("baseCountry=" + regional.getCountry());
        System.out.println("currencyKeyword=" +
                regional.getUnicodeLocaleType("cu"));
        System.out.println("firstWeekdayKeyword=" +
                regional.getUnicodeLocaleType("fw"));
        System.out.println("regionKeyword=" +
                regional.getUnicodeLocaleType("rg"));
        System.out.println("zoneKeyword=" +
                regional.getUnicodeLocaleType("tz"));

        System.out.println("currencyOverride=" +
                Currency.getInstance(
                        Locale.forLanguageTag(
                                "en-US-u-cu-eur")).getCurrencyCode());

        System.out.println("regionCurrency=" +
                Currency.getInstance(
                        Locale.forLanguageTag(
                                "en-US-u-rg-gbzzzz")).getCurrencyCode());

        System.out.println("weekStart=" +
                WeekFields.of(
                        Locale.forLanguageTag(
                                "en-US-u-fw-mon")).getFirstDayOfWeek());

        System.out.println("timezone=" +
                DateFormat.getDateTimeInstance(
                        DateFormat.SHORT, DateFormat.SHORT,
                        Locale.forLanguageTag(
                                "en-US-u-tz-usnyc"))
                        .getTimeZone().getID());

        var built = new Locale.Builder()
                .setLanguage("vi")
                .setRegion("VN")
                .setUnicodeLocaleKeyword("nu", "latn")
                .setUnicodeLocaleKeyword("fw", "mon")
                .build();
        System.out.println("builderTag=" + built.toLanguageTag());
        System.out.println("withoutExtensions=" +
                built.stripExtensions().toLanguageTag());
        System.out.println("builderWeekStart=" +
                WeekFields.of(built).getFirstDayOfWeek());

        var opaque = Locale.forLanguageTag("en-US-u-zz-abc");
        System.out.println("unrecognizedKey=" +
                opaque.getUnicodeLocaleType("zz"));

        var lenient = Locale.forLanguageTag("en-US-@");
        System.out.println("lenientTag=" + lenient.toLanguageTag());

        try {
            new Locale.Builder().setLanguageTag("en-US-@").build();
        } catch (IllformedLocaleException expected) {
            System.out.println("strictBuilderRejected=true");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 17 -encoding UTF-8 LocaleTagDemo.java
java LocaleTagDemo
```

**Stdout đã xác nhận với JDK trong môi trường thử nghiệm:**

```text
normalized=en-Latn-US-u-ca-gregory-nu-latn
language=en
script=Latn
country=US
calendar=gregory
numbers=latn
unicodeExtension=ca-gregory-nu-latn
regionalTag=en-US-u-cu-eur-fw-mon-rg-gbzzzz-tz-usnyc
baseCountry=US
currencyKeyword=eur
firstWeekdayKeyword=mon
regionKeyword=gbzzzz
zoneKeyword=usnyc
currencyOverride=EUR
regionCurrency=GBP
weekStart=MONDAY
timezone=America/New_York
builderTag=vi-VN-u-fw-mon-nu-latn
withoutExtensions=vi-VN
builderWeekStart=MONDAY
unrecognizedKey=abc
lenientTag=en-US
strictBuilderRejected=true
```

### Vì sao từng nhóm kết quả đúng?

1. **`normalized`, `language`, `script`, `country`**: Java parse các thành phần BCP 47 và chuẩn hóa hoa/thường cũng như thứ tự các Unicode keywords `ca` và `nu`.
2. **`calendar`, `numbers`, `unicodeExtension`**: những accessor của `Locale` trả thông tin **đã được lưu**, không phụ thuộc việc có gọi formatter hay chưa.
3. **`regionalTag` và các keyword**: cùng một Locale chứa bốn extension từ JEP 314 (`cu`, `fw`, `rg`, `tz`); `getCountry()` vẫn là `US`.
4. **`currencyOverride=EUR`**: `Currency.getInstance` hiểu `cu-eur`. **`regionCurrency=GBP`**: cùng API hiểu `rg-gbzzzz` để lấy tiền tệ mặc định của vùng GB.
5. **`weekStart=MONDAY`**: `WeekFields.of` áp dụng `fw-mon`.
6. **`timezone=America/New_York`**: `DateFormat` áp dụng short time-zone ID `usnyc` theo dữ liệu JDK thử nghiệm; timezone của JVM không bị thay đổi trên toàn hệ thống bởi ví dụ.
7. **`builderTag` và `withoutExtensions`**: Builder tạo tag canonical và `stripExtensions()` giữ lại phần ngôn ngữ/vùng cơ sở.
8. **`unrecognizedKey=abc`**: `Locale` có thể giữ một keyword hợp cú pháp ngay cả khi các dịch vụ không hiểu ý nghĩa của nó.
9. **`lenientTag=en-US`**: `forLanguageTag` bỏ đoạn lỗi `@`. **`strictBuilderRejected=true`**: Builder báo lỗi cú pháp bằng `IllformedLocaleException`.

Chương trình được thiết kế để **không dựa vào tên hiển thị phụ thuộc ngôn ngữ**. Tuy vậy, các giá trị phụ thuộc dữ liệu locale như currency/time-zone có thể chịu ảnh hưởng chính sách hỗ trợ của runtime/provider; kết quả trên đã được kiểm chứng bằng JDK 17+ với những key/type phổ biến.

## 10. Quy trình áp dụng cho ứng dụng thực tế

### Bước 1 — Nhận một language tag đúng ngữ cảnh

Ví dụ một cấu hình người dùng chọn:

```text
vi-VN-u-fw-mon-nu-latn
```

Không tự nối subtag sai thứ tự; khi các thành phần đến từ trường nhập riêng, dùng `Locale.Builder`. Với input đã là language tag, dùng `Locale.forLanguageTag` và cân nhắc `Builder.setLanguageTag` khi cần **từ chối cú pháp không hợp lệ**.

### Bước 2 — Giữ nguyên những keyword quan trọng

Sau khi parse, đọc các yêu cầu theo key:

```java
String numbering = locale.getUnicodeLocaleType("nu");
String firstWeekday = locale.getUnicodeLocaleType("fw");
```

Đoạn này giả định biến `locale` kiểu `Locale` đã tồn tại. Nếu keyword không có, accessor trả `null`; **đừng tự suy một giá trị luôn đúng cho mọi vùng**. Hãy dùng fallback theo yêu cầu của ứng dụng.

### Bước 3 — Truyền Locale tới API cần thiết

Ví dụ tạo formatter theo locale đã lựa chọn:

```java
var numberFormat = java.text.NumberFormat.getInstance(locale);
var weekFields = java.time.temporal.WeekFields.of(locale);
```

Nếu API không hỗ trợ một keyword cụ thể, việc nó **không đổi hành vi** có thể là phù hợp hợp đồng. Không tự viết test “cứ tag có `u-xx-yy` là formatter phải dùng `yy`”.

### Bước 4 — Kiểm tra đầu ra và ranh giới hỗ trợ

Trong test i18n, nên kiểm thử:

- `toLanguageTag` và `getUnicodeLocaleType` cho dữ liệu định danh;
- một API hỗ trợ rõ key đang dùng, ví dụ `Currency.getInstance` với `cu`;
- tình huống locale data/provider khác nhau khi đó là yêu cầu thực tế;
- input BCP 47 sai cú pháp; xác định chính sách chấp nhận hay từ chối;
- fallback khi key/type tồn tại nhưng không được dịch vụ hỗ trợ.

Nếu một thuộc tính có yêu cầu nghiệp vụ cứng, hãy truyền cấu hình tường minh cho API phù hợp và kiểm thử output theo phiên bản JDK/framework được hỗ trợ, thay vì chỉ tin rằng tag sẽ giải quyết mọi thứ.

## 11. Những lỗi thường gặp

**Lỗi 1 — Cho rằng Java 10 mới bắt đầu có BCP 47.**  
Sai. `Locale` hỗ trợ BCP 47 từ Java 7. JEP 314 (Java 10) **mở rộng hỗ trợ** `cu`, `fw`, `rg`, `tz` trong những API liên quan.

**Lỗi 2 — Nhầm `getCountry()` với `rg`.**  
`en-US-u-rg-gbzzzz` vẫn có country cơ sở `US`; region override được API như `Currency.getInstance` diễn giải để sử dụng dữ liệu vùng GB.

**Lỗi 3 — Dùng `Locale.toString()` làm language tag.**  
`toString()` dành chủ yếu cho biểu diễn/debug và dùng các dấu phân cách khác. `toLanguageTag()` là API khi cần chuẩn BCP 47.

**Lỗi 4 — Tin mọi key hợp cú pháp đều có tác dụng với mọi formatter.**  
Sai. `Locale` có thể lưu key/type chưa được một dịch vụ cụ thể hiểu. Cần tách syntax, registration và sự hỗ trợ của locale provider/API.

**Lỗi 5 — Parse Unicode keywords bằng cách split thô.**  
Có type nhiều subtag, attribute và các extension khác. Dùng `getUnicodeLocaleType` và `Locale.Builder` thay vì tự suy từ vị trí token.

**Lỗi 6 — Dùng `forLanguageTag` làm bộ validator nghiêm ngặt.**  
Nó có thể bỏ phần sai cú pháp. Nếu input cần từ chối khi malformed, dùng `Locale.Builder.setLanguageTag` và bắt `IllformedLocaleException`.

**Lỗi 7 — Coi `tz-usnyc` là `ZoneId` IANA.**  
`usnyc` là Unicode short time-zone ID. Trong mô hình thời gian, xử lý `ZoneId` thực tế riêng, không đổi cả JVM timezone chỉ từ một Locale.

**Lỗi 8 — Thay `Locale.setDefault` cho mọi request người dùng.**  
Default Locale là trạng thái dùng chung. Trong hệ thống nhiều user, nên truyền Locale explicit theo request vào formatter, currency và week fields.

**Lỗi 9 — Dùng cả chuỗi header `Accept-Language` như một language tag.**  
Header có danh sách ngôn ngữ và trọng số. Phải phân tích danh sách ưu tiên trước khi chọn từng Locale; có `Locale.LanguageRange` và cơ chế của framework.

**Lỗi 10 — Gắn identity hoặc vị trí thực tế cho nhãn `Locale`.**  
Language, region và Unicode overrides là **ưu tiên bản địa hóa**, không phải dữ liệu địa chỉ, định vị hay quốc tịch được xác minh.

## 12. Bài tập tự kiểm tra

**Câu 1.** `en-Latn-US-u-nu-latn-ca-gregory` gồm những phần nào?  
**Đáp án:** Language `en`, script `Latn`, region `US`; Unicode extension `u` có hai key/type: `nu=latn` và `ca=gregory`. `toLanguageTag` có thể chuẩn hóa thứ tự thành `ca` trước `nu`.

**Câu 2.** `Locale.forLanguageTag("en-US-u-cu-eur")` có làm `locale.getCountry()` thành một quốc gia châu Âu không?  
**Đáp án:** Không. Country cơ sở vẫn là `US`. `cu-eur` là tùy chọn tiền tệ mà API `Currency.getInstance` hỗ trợ.

**Câu 3.** `en-US-u-rg-gbzzzz` có country và region override nào?  
**Đáp án:** `getCountry()` là `US`; keyword `rg` là `gbzzzz`, dùng để override dữ liệu vùng cho những dịch vụ hỗ trợ như `Currency`.

**Câu 4.** `fw-mon` tác động tới API nào trong ví dụ Java?  
**Đáp án:** `WeekFields.of(locale).getFirstDayOfWeek()` cho `MONDAY` khi key/type được hỗ trợ.

**Câu 5.** Tại sao `Locale.forLanguageTag("en-US-@")` và Builder xử lý khác nhau?  
**Đáp án:** `forLanguageTag` có thể cắt bỏ đoạn malformed và trả `en-US`. `Locale.Builder.setLanguageTag` kiểm tra well-formed và ném `IllformedLocaleException`.

**Câu 6.** Nếu `getUnicodeLocaleType("zz")` trả `"abc"`, có nghĩa formatter phải có hành vi `zz` không?  
**Đáp án:** Không. API có thể lưu và trả một keyword hợp cú pháp mà không có dịch vụ nào hỗ trợ ý nghĩa của nó.

**Câu 7.** `tz-usnyc` có tự đổi `ZoneId.systemDefault()` cho mọi thread không?  
**Đáp án:** Không. `Locale` là descriptor. Những API như `DateFormat` có thể dùng timezone extension khi tạo formatter, không phải thay đổi múi giờ mặc định toàn hệ thống.

**Câu 8.** Vì sao cần phân biệt `Locale.forLanguageTag` và `Locale.LanguageRange.parse`?  
**Đáp án:** Phương thức đầu tạo Locale từ **một nhãn**; phương thức sau giúp xử lý **danh sách ưu tiên ngôn ngữ** như HTTP `Accept-Language`, sau đó mới chọn Locale phù hợp.

## 13. Tóm tắt

1. **BCP 47** mô tả nhãn ngôn ngữ có language, script, region, variant và extensions; Java `Locale` hỗ trợ từ Java 7.
2. **Unicode `-u-` extension** biểu diễn các thuộc tính và cặp keyword/type như `ca-gregory`, `nu-latn`.
3. **Java 10 / JEP 314** bổ sung việc áp dụng `cu` (currency), `fw` (first weekday), `rg` (region override), `tz` (time zone) trong các API liên quan. Đây là trọng tâm phiên bản Java 10 của bài.
4. Dùng `Locale.forLanguageTag` / `toLanguageTag` để trao đổi nhãn, `getUnicodeLocaleType` để truy vấn keyword, `Locale.Builder` để tạo hoặc kiểm tra cú pháp nghiêm ngặt.
5. **Tag hợp cú pháp không đồng nghĩa mọi keyword được mọi service hỗ trợ.** Một API chỉ cần hiểu những extension liên quan; locale data và provider có thể thay đổi.
6. `rg` không thay đổi `getCountry()`; `tz` không tự đổi timezone mặc định; `cu` không đổi ngôn ngữ; `fw` không phải lựa chọn tiền tệ.
7. Khi thiết kế ứng dụng đa ngôn ngữ, truyền **Locale tường minh theo request**, kiểm tra các quy tắc có ý nghĩa nghiệp vụ và tránh phụ thuộc output phụ thuộc dữ liệu JDK.

## Tài liệu tham khảo chính thức và còn áp dụng

- OpenJDK **JEP 314 — Additional Unicode Language-Tag Extensions** (Delivered in Java 10): https://openjdk.org/jeps/314
- Oracle **Java 10 Internationalization Enhancements** — bốn key `cu`, `fw`, `rg`, `tz`: https://docs.oracle.com/javase/10/intl/internationalization-enhancements-jdk-10.htm
- Java SE 26 API — `Locale`: BCP 47, Unicode `u` extension, `forLanguageTag`, `toLanguageTag`, `getUnicodeLocaleType`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html
- Java SE 26 API — `Locale.Builder`: `setLanguageTag`, `setUnicodeLocaleKeyword`, `build` và lỗi cú pháp: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.Builder.html
- Java SE 26 API — `Currency.getInstance(Locale)`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Currency.html
- Java SE 26 API — `WeekFields.of(Locale)`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/WeekFields.html
- Java SE 26 API — `DateFormat.getDateTimeInstance`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/DateFormat.html
- Unicode Consortium — UTS #35, Unicode Locale Identifier: https://unicode.org/reports/tr35/
- IETF RFC 5646 — Tags for Identifying Languages: https://www.rfc-editor.org/rfc/rfc5646
- IETF RFC 4647 — Matching of Language Tags: https://www.rfc-editor.org/rfc/rfc4647
