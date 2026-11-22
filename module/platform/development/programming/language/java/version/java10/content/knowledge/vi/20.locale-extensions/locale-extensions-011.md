# Xử lý giá trị không được hỗ trợ theo hợp đồng API khi mở rộng Locale

> **Chủ đề Java 10 — Mở rộng Locale (JEP 314).** Java 10 mở rộng việc **sử dụng** các Unicode BCP 47 locale extensions `cu` (tiền tệ), `fw` (ngày bắt đầu tuần), `rg` (ghi đè vùng) và `tz` (múi giờ) trong các API i18n liên quan. Việc tạo được `Locale` chứa một khóa/giá trị **không có nghĩa** mọi API sẽ hiểu hoặc áp dụng nó. Bài này tập trung vào cách nhận biết và xử lý **giá trị không được hỗ trợ theo đúng hợp đồng từng API**: phân biệt lỗi cú pháp, khóa vắng mặt, giá trị đúng cú pháp nhưng không được nhận diện, fallback của provider và lỗi nghiệp vụ. Các API còn áp dụng trên JDK hiện đại; không cần dùng runtime Java 10 đã cũ.

## 1. Mục tiêu

Sau khi học, bạn có thể:

1. Phân biệt **locale tag hợp lệ về cú pháp (well-formed)**, **giá trị extension được công nhận về ngữ nghĩa**, và **khả năng áp dụng của một service cụ thể**.
2. Kể đúng bốn mở rộng được JEP 314 hỗ trợ từ Java 10: `cu`, `fw`, `rg`, `tz`; biết `ca` và `nu` đã có hỗ trợ từ trước đó.
3. Dùng `Locale.Builder` để kiểm tra **cú pháp** và phân biệt nó với `Locale.forLanguageTag` có thể bỏ qua phần sai cú pháp.
4. Xử lý đúng `Locale.getUnicodeLocaleType`: `null` khi không có keyword, chuỗi rỗng khi keyword có nhưng không có type, và ngoại lệ khi key tra cứu sai cú pháp.
5. Hiểu khi nào `Currency.getInstance(String)` ném `IllegalArgumentException`, khi nào `Currency.getInstance(Locale)` có thể trả `null` hoặc ném lỗi, và vì sao không được tự suy ra một đồng tiền hợp lệ từ mọi locale.
6. Dùng `WeekFields.of(Locale)` cho `fw` theo hợp đồng; quyết định khi nào phải kiểm tra giá trị được cho phép trước khi xây formatter/locale và chọn fallback tường minh.
7. Phân biệt xử lý của `DateTimeFormatter.localizedBy(locale)` so với `withLocale(locale)`; không xem chuỗi `tz` là IANA zone ID.
8. Thiết kế chính sách **REJECT / FALLBACK / BEST_EFFORT** theo nghiệp vụ, kiểm thử và log không phụ thuộc cấu hình CLDR/JDK của một máy.
9. Chạy chương trình Java độc lập với 18 dòng stdout xác định, trong đó có cả tình huống hợp lệ, không được hỗ trợ và ngoại lệ.

## 2. Bối cảnh Java 10: có extension chưa đủ để được hỗ trợ ở mọi service

IETF BCP 47 có dạng language tag như:

```text
en-US-u-cu-jpy
en-US-u-fw-mon
en-US-u-rg-gbzzzz
en-US-u-tz-usnyc
```

- `en-US`: ngôn ngữ tiếng Anh và vùng US trong locale cơ sở.
- `u`: Unicode locale extension.
- `cu-jpy`: yêu cầu loại tiền tệ JPY.
- `fw-mon`: yêu cầu ngày đầu tuần là thứ Hai.
- `rg-gbzzzz`: yêu cầu sử dụng vùng GB cho các dữ liệu locale mà API liên quan hỗ trợ ghi đè vùng.
- `tz-usnyc`: mã loại múi giờ trong Unicode locale extension; nó **không phải** chuỗi ID IANA `America/New_York`.

Theo OpenJDK **JEP 314**, từ Java 10 các service liên quan được nâng cấp để xét `cu`, `fw`, `rg`, `tz`. Những service được mô tả trong JEP có `Currency.getInstance`, `WeekFields.of`, `Calendar`, `DateFormat`, `NumberFormat`, `DateTimeFormatter.localizedBy` và các API định dạng khác. Điều quan trọng là **mỗi service chỉ quan tâm những extension có ý nghĩa đối với nó**.

| Unicode key | Ý nghĩa | Ví dụ | API liên quan được JEP 314 mô tả | Lưu ý khi giá trị không được hỗ trợ |
| --- | --- | --- | --- | --- |
| `cu` | Loại tiền tệ | `cu-jpy` | `Currency.getInstance(Locale)` | Kiểm tra mã tiền tệ hỗ trợ theo `Currency` và hợp đồng nghiệp vụ; đừng xem một tag có `cu` là bằng chứng đồng tiền sẽ được chọn |
| `fw` | Ngày bắt đầu tuần | `fw-mon` | `WeekFields.of(Locale)`, `Calendar` | Một type như `blorp` có thể đúng cú pháp BCP 47 nhưng không nằm trong tập ngày được biết; phải quyết định reject hoặc fallback |
| `rg` | Ghi đè vùng cho dữ liệu locale | `rg-gbzzzz` | `WeekFields`, `Currency`, `NumberFormat`, `DateTimeFormatter`... | Không đồng nhất `getCountry()` với vùng hiệu dụng của mọi service; giá trị `rg` cần tuân quy tắc Unicode/CLDR |
| `tz` | Loại múi giờ Unicode | `tz-usnyc` | `DateTimeFormatter.localizedBy`, `DateFormat` | Không phải mọi chuỗi trông giống mã múi giờ đều là type được nhận; cần validate theo registry/ứng dụng hoặc dùng `ZoneId.of` cho IANA zone ID |
| `ca` | Loại lịch | `ca-japanese` | Các formatter/calendar liên quan | Có thể chỉ một số loại lịch được service hỗ trợ; dùng hợp đồng cụ thể |
| `nu` | Hệ chữ số | `nu-thai` | `NumberFormat`, `DecimalStyle`... | Không kết luận mọi service phải sử dụng system số đã được tag mô tả |

**Phạm vi thời gian:** `Locale` và BCP 47 đã tồn tại trước Java 10. **Java 10 mở rộng việc tôn trọng các type `cu/fw/rg/tz` trong service**, chứ không phải từ Java 10 mới có phương thức `Locale.Builder` hay `getUnicodeLocaleType`.

## 3. Ba tầng kiểm tra: syntax, semantic support và behavior

Một thiết kế đúng cần đi qua ba câu hỏi khác nhau:

```text
Chuỗi đầu vào từ user/config
           |
           v
[1] Có đúng CÚ PHÁP BCP 47 không?
       | không: IllformedLocaleException hoặc reject
       v
[2] Key/type có ĐƯỢC ỨNG DỤNG/API HỖ TRỢ không?
       | không: reject / fallback có tài liệu hóa
       v
[3] Service cụ thể có ÁP DỤNG type đó không?
       | theo Javadoc, provider, CLDR, chính sách sản phẩm
       v
Trả kết quả cho người dùng / lưu cấu hình có trạng thái rõ ràng
```

### 3.1. Đúng cú pháp không đồng nghĩa một giá trị có thật trong registry

Một Unicode locale keyword có **key gồm hai ký tự chữ/số**; type gồm các subtag phù hợp cú pháp BCP 47. `Locale.Builder.setUnicodeLocaleKeyword(key,type)` kiểm tra hình dạng (well-formed) và chuẩn hóa chữ thường.

```java
var locale = new java.util.Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("fw", "blorp")
        .build();

System.out.println(locale.getUnicodeLocaleType("fw")); // blorp
```

`blorp` là một chuỗi **5 chữ cái** thỏa cấu trúc một Unicode type subtag, nên Builder có thể chấp nhận. Nhưng `blorp` **không** phải một trong các type ngày bắt đầu tuần được biết (`sun`, `mon`, `tue`, `wed`, `thu`, `fri`, `sat`).

**Kết luận:** việc `build()` thành công chỉ chứng minh điều kiện well-formed được Builder kiểm tra, không chứng minh `WeekFields` sẽ hiểu hoặc áp dụng `fw-blorp`. Nếu ứng dụng bắt buộc mỗi cấu hình `fw` phải có hiệu lực, nên tự xác thực tập giá trị được phép.

Một ví dụ nữa:

```java
var unknown = new java.util.Locale.Builder()
        .setLanguage("en")
        .setUnicodeLocaleKeyword("zz", "alpha")
        .build();

System.out.println(unknown.getUnicodeLocaleType("zz")); // alpha
```

`zz` là key **đúng cú pháp**, nhưng không phải một trong bốn key mà **JEP 314** nêu được thêm hỗ trợ trong các API của Java 10. `Locale` có thể **bảo toàn dữ liệu extension** mà không có cam kết tất cả các service JDK sẽ hành xử theo giá trị đó.

### 3.2. Đúng cú pháp nhưng không hỗ trợ: hai loại chính sách

**REJECT:** Khi người dùng nhập một giá trị nghiệp vụ bắt buộc phải chính xác (ví dụ đơn vị tiền cho thanh toán, cấu hình bắt đầu tuần theo spec), thông báo giá trị không hỗ trợ và yêu cầu sửa. Không được âm thầm thay một loại tiền sang loại khác mà không cho người dùng biết.

**FALLBACK:** Khi nhu cầu là hiển thị tiện lợi (ví dụ ngày đầu tuần trong giao diện), ứng dụng có thể cho phép quay về locale/giá trị đã cấu hình trước. Fallback phải tường minh, có thể kiểm thử và được thông báo nếu ảnh hưởng đến trải nghiệm.

**BEST_EFFORT:** Một số service i18n có cơ chế fallback của provider/JDK cho các locale không có dữ liệu chi tiết. Hợp đồng này **khác** với việc ứng dụng cam kết một preference đã được áp dụng. Nếu dùng best-effort, đừng hứa rằng mọi `u-...` có hiệu lực 100%.

Không có một quy tắc “cứ giá trị không hỗ trợ thì Java luôn ném exception” hay “Java luôn bỏ qua và trả mặc định” áp dụng chung cho mọi API.

### 3.3. Runtime và locale provider có thể khác nhau

Locale data do JDK và các `LocaleServiceProvider` cung cấp. Danh sách locale/type và cách định dạng có thể thay đổi theo phiên bản CLDR, JDK distribution, module `jdk.localedata`, thiết lập provider và cấu hình runtime.

Do đó:
- Không hardcode toàn bộ kết quả hiển thị ngày/tháng, tiền tệ hoặc múi giờ từ máy phát triển.
- Không kết luận mọi extension đều được áp dụng chỉ vì `Locale.getAvailableLocales()` chứa một locale cơ sở.
- Phân biệt **hợp đồng chuẩn** với **quan sát trên một JDK cụ thể**.
- Dùng kiểm thử tích hợp trên các runtime phải hỗ trợ khi có yêu cầu hiển thị chính xác ở nhiều quốc gia.

## 4. Kiểm tra cú pháp: `Builder` khác `forLanguageTag`

### 4.1. `Locale.Builder.setLanguageTag` phù hợp đầu vào cần validate nghiêm ngặt

```java
import java.util.IllformedLocaleException;
import java.util.Locale;

try {
    Locale locale = new Locale.Builder()
            .setLanguageTag("en-US-u-fw-!")
            .build();
} catch (IllformedLocaleException ex) {
    System.out.println("Invalid BCP 47 syntax");
}
```

Đoạn trên là mã minh họa **nằm trong một method**; nó bắt đúng `IllformedLocaleException` do tag có subtag `!` sai cú pháp. `Builder` phù hợp khi chuỗi đến từ file cấu hình cần được chấp nhận nguyên vẹn hoặc từ chối rõ ràng.

`setUnicodeLocaleKeyword("f","mon")` cũng ném `IllformedLocaleException` vì key `f` chỉ có một ký tự thay vì hai. `setUnicodeLocaleKeyword(null,"mon")` ném `NullPointerException`; không gộp tùy tiện vào một loại lỗi “unknown locale”.

### 4.2. `Locale.forLanguageTag` có thể chấp nhận **phần prefix**

```java
var parsed = java.util.Locale.forLanguageTag("en-US-u-fw-!");
System.out.println(parsed.toLanguageTag()); // en-US-u-fw (trên JDK đã kiểm thử)
```

Theo Javadoc, nếu language tag có subtag sai cú pháp, `forLanguageTag` **bỏ qua subtag sai đầu tiên và mọi subtag theo sau**, thay vì ném `IllformedLocaleException`. Vì vậy API này phù hợp với ngữ cảnh cần diễn giải tag lenient, nhưng **không phải bộ kiểm tra cú pháp đầy đủ để reject cấu hình sai**.

Cẩn thận: ví dụ còn giữ keyword `fw` với **type rỗng**, chứ không đơn giản là “bỏ hẳn mọi extension”. Không được tự khẳng định `forLanguageTag("en-US-u-fw-!")` luôn trở thành chính xác `en-US`; việc cắt bớt phần sai cần hiểu qua contract và dữ liệu thực tế.

### 4.3. Kiểm tra syntax không xác nhận registry hoặc dữ liệu locale

Ngay cả `new Locale.Builder().setLanguageTag("xx-YY").build()` có thể tạo `Locale` với cú pháp đúng, dù các mã `xx`, `YY` không nhất thiết là các mã được đăng ký/được cung cấp dữ liệu locale trên runtime.

Khi xây API quốc tế hóa có dữ liệu từ user, cần phân biệt:
- **Well-formed:** chuỗi có cấu trúc được Java chấp nhận.
- **Valid/registered:** subtag/extension type thuộc registry hoặc danh sách ứng dụng công nhận.
- **Service-supported:** API cụ thể xử lý loại giá trị này.
- **Business-allowed:** sản phẩm cho phép kiểu vùng/tiền/múi giờ này trong chức năng đang dùng.

Bốn thuộc tính đó liên quan nhưng **không tương đương**.

## 5. Đọc một keyword đúng: `null`, chuỗi rỗng và ngoại lệ

`Locale.getUnicodeLocaleType(String key)` có hợp đồng cụ thể:

| Tình huống | Kết quả | Ý nghĩa |
| --- | --- | --- |
| Locale có `fw-mon`, hỏi `"fw"` | `"mon"` | Keyword có type xác định |
| Locale **không có** `fw`, hỏi `"fw"` | `null` | Không có keyword |
| Locale có `fw` nhưng không có type, hỏi `"fw"` | `""` | Keyword hiện diện nhưng type rỗng |
| Hỏi key sai cú pháp như `"f"` | Ném `IllegalArgumentException` | Key phải có đúng hai ký tự chữ/số |
| Hỏi key `null` | Ném `NullPointerException` | Lỗi tham số tra cứu |

Ví dụ:

```java
var hasNoFw = new Locale.Builder()
        .setLanguage("en").setRegion("US").build();

var hasEmptyFw = new Locale.Builder()
        .setLanguage("en").setRegion("US")
        .setUnicodeLocaleKeyword("fw", "")
        .build();

System.out.println(hasNoFw.getUnicodeLocaleType("fw") == null); // true
System.out.println("".equals(
        hasEmptyFw.getUnicodeLocaleType("fw"))); // true
```

**Đừng kiểm tra mỗi `value != null` rồi coi đó là một type đã hỗ trợ.** Nếu domain yêu cầu ngày bắt đầu tuần tường minh, chuỗi rỗng cũng phải được xem là thiếu/không hợp lệ. Ngược lại, nếu keyword tùy chọn, giá trị `null` có thể có ý nghĩa **“để service chọn mặc định”**, không phải lỗi.

`Locale.getUnicodeLocaleKeys()` giúp liệt kê keyword đang có trong object nhưng không xác minh type có ý nghĩa với service. Nó không thay thế registry validation hay kiểm tra hợp đồng API.

## 6. `cu`: khi nào mã tiền tệ không được hỗ trợ?

### 6.1. Trường hợp được hỗ trợ

```java
var locale = new java.util.Locale.Builder()
        .setLanguage("en").setRegion("US")
        .setUnicodeLocaleKeyword("cu", "JPY")
        .build();

var currency = java.util.Currency.getInstance(locale);
System.out.println(currency.getCurrencyCode()); // JPY
```

`Locale.Builder` chuẩn hóa type thành chữ thường `jpy`. `Currency.getInstance(Locale)` nhận Unicode extension `cu` theo JEP 314 và trả currency tương ứng. `cu` có độ ưu tiên cao hơn tiền tệ suy từ `rg` nếu cùng xuất hiện, theo Javadoc của `Currency.getInstance(Locale)`.

### 6.2. Phân biệt hai overload của `Currency.getInstance`

**Overload nhận currency code:**

```java
Currency.getInstance("JPY"); // Một Currency có mã JPY.
Currency.getInstance("ZZZ"); // IllegalArgumentException nếu không hỗ trợ.
```

Theo Javadoc, `Currency.getInstance(String)` ném `IllegalArgumentException` nếu code **không phải mã ISO 4217 được hỗ trợ** và `NullPointerException` nếu tham số là null. Đây là cách hữu ích để xác thực code tiền tệ **có trong runtime** trước khi xây định dạng.

**Overload nhận Locale:**

```java
Currency.getInstance(locale);
```

Theo Javadoc, phương thức có thể **trả `null`** khi vùng lãnh thổ không có tiền tệ, hoặc ném `IllegalArgumentException` nếu country code của locale không được hỗ trợ. Nó có xem xét `cu` và `rg`, nhưng điều đó **không đảm bảo** mọi type `cu` đúng cú pháp đều tạo ra đồng tiền mà user mong muốn.

### 6.3. Type đúng cú pháp nhưng chưa được hỗ trợ

```java
var candidate = new Locale.Builder()
        .setLanguage("en").setRegion("US")
        .setUnicodeLocaleKeyword("cu", "zzzz")
        .build();

System.out.println(candidate.getUnicodeLocaleType("cu")); // zzzz
```

`zzzz` là một Unicode type subtag **đúng cấu trúc** (4 chữ cái). `Builder` không phải danh mục ISO 4217 và không ném lỗi chỉ vì `zzzz` không phải currency type hợp lệ. **Không** diễn dịch việc object giữ `cu=zzzz` là “Java đã chọn đồng tiền zzzz”. Với JDK cụ thể, service có thể bỏ qua một type không biết và dùng dữ liệu vùng; ứng dụng **không nên phụ thuộc vào kết quả fallback tình cờ**.

Nếu có giá trị code tiền tệ độc lập từ user, xác thực nó bằng `Currency.getInstance(String)` và chính sách domain. Ví dụ một hàm fallback tường minh nằm trong chương trình lab:

```java
static Currency chooseCurrency(String code, Currency fallback) {
    if (code == null || !code.matches("[a-zA-Z]{3}")) {
        return fallback;
    }
    try {
        return Currency.getInstance(code.toUpperCase(Locale.ROOT));
    } catch (IllegalArgumentException ex) {
        return fallback;
    }
}
```

**Lưu ý nghiệp vụ:** Fallback từ một currency code không hỗ trợ sang USD **chỉ hợp lệ nếu sản phẩm cho phép** (ví dụ lựa chọn hiển thị). Đối với thanh toán, tỷ giá, ledger hoặc giá hợp đồng, âm thầm đổi sang USD là sai nghiêm trọng. Khi đó nên **reject** và giữ nguyên mã gốc để người dùng sửa, hoặc áp dụng quy tắc đã được phê duyệt. `Currency` chỉ mô tả currency; nó không tự quy đổi giá tiền.

## 7. `fw`: ngày đầu tuần và hành vi với type không nhận diện

Các type ngày đầu tuần được định nghĩa trong dữ liệu Unicode bao gồm:

```text
sun, mon, tue, wed, thu, fri, sat
```

Một loại được hỗ trợ:

```java
var locale = java.util.Locale.forLanguageTag("en-US-u-fw-mon");
System.out.println(java.time.temporal.WeekFields
        .of(locale).getFirstDayOfWeek()); // MONDAY
```

Theo Javadoc `WeekFields.of(Locale)`, `fw` và `rg` có thể ảnh hưởng tới giá trị ngày đầu tuần, và `fw` có độ ưu tiên cao hơn ngày mặc định suy từ `rg`.

### 7.1. `blorp` là syntax-valid nhưng không phải day-of-week type

```java
var locale = new Locale.Builder()
        .setLanguageTag("en-US-u-fw-blorp")
        .build();

System.out.println(locale.getUnicodeLocaleType("fw")); // blorp
```

Ở đây không có lỗi cú pháp bắt buộc. Nhưng điều đó không làm `blorp` trở thành một ngày đầu tuần có nghĩa. Không nên viết test `assertThrows(IllformedLocaleException.class, ...)` cho trường hợp này. Nếu API cụ thể có fallback trên runtime hiện tại, fallback ấy **không phải** bằng chứng `blorp` được hiểu là một ngày hợp lệ.

### 7.2. Chọn hợp đồng ứng dụng: fallback tường minh

Một chính sách đơn giản:

```java
static final Set<String> WEEK_STARTS =
        Set.of("sun","mon","tue","wed","thu","fri","sat");

static Locale chooseWeekLocale(String tag, Locale fallback) {
    if (tag == null) return fallback;

    try {
        Locale candidate = new Locale.Builder()
                .setLanguageTag(tag).build();

        String fw = candidate.getUnicodeLocaleType("fw");
        if (fw != null && !WEEK_STARTS.contains(fw)) {
            return fallback;
        }
        return candidate;
    } catch (IllformedLocaleException ex) {
        return fallback;
    }
}
```

Hàm được định nghĩa đầy đủ trong chương trình runnable ở phần 10. Quy tắc này:
- **Chấp nhận** `fw=mon`...`sat`, nếu tag well-formed.
- **Trở về fallback** khi `fw` có type khác hoặc type rỗng.
- **Trở về fallback** khi tag sai cú pháp, chẳng hạn `en-US-u-fw-!`.
- **Giữ nguyên locale ứng viên** khi không có `fw` (nghĩa là để service sử dụng dữ liệu locale thông thường).

Đây là **chính sách do ứng dụng tự chọn**, không phải một ngoại lệ hoặc fallback “mặc định” do `Locale.Builder` tự triển khai. Với sản phẩm phải áp dụng ngày đầu tuần chính xác, phiên bản **reject** có thể hợp lý hơn; khi đó ném `IllegalArgumentException` với thông điệp miền thay cho `return fallback`.

### 7.3. Không tự thay thế mọi khía cạnh của một tuần

`WeekFields` bao gồm **ngày đầu tuần** và **số ngày tối thiểu của tuần đầu tiên**, không chỉ enum `DayOfWeek`. `fw` nhằm ghi đè ngày đầu tuần; khi muốn bộ quy tắc tuần cố định theo hợp đồng doanh nghiệp, bạn có thể tạo:

```java
var iso = java.time.temporal.WeekFields.ISO;
var explicit = java.time.temporal.WeekFields.of(
        java.time.DayOfWeek.MONDAY, 4);
```

Hai cách trên thể hiện quy tắc tuần ISO trong ví dụ, không phụ thuộc provider. Nếu user cần “tuần bắt đầu thứ Hai” nhưng có chính sách minimal days khác, phải chọn giá trị phù hợp — không mặc nhiên đặt `4` cho mọi khu vực.

## 8. `rg` và `tz`: type cần đúng **ngữ nghĩa**, không chỉ đúng mẫu ký tự

### 8.1. `rg`: region override không nhất thiết thay `Locale.getCountry()`

Một tag có thể là:

```java
Locale locale = Locale.forLanguageTag("en-US-u-rg-gbzzzz");
```

Đây là mã minh họa trong phương thức đã import `Locale`. `getCountry()` vẫn biểu thị trường **region** của Locale cơ sở (ở đây `US`), trong khi một số service như `WeekFields.of`, `NumberFormat`, `Currency` có thể dùng override `rg` theo hợp đồng.

Không xử lý bằng cách “thấy `rg-gbzzzz` thì sửa luôn country thành GB” trừ khi đó chính là mô hình nghiệp vụ được yêu cầu. BCP 47 language tag có ý nghĩa nhiều lớp: language/region xác định danh tính locale cơ sở, extension biểu thị tùy chọn cho từng service.

Một chuỗi `rg` trông có cấu trúc hợp lệ chưa chắc là giá trị registry/service đã nhận. Khi ứng dụng cần bảo đảm vùng hiệu dụng, kiểm tra theo Unicode CLDR/registry và danh sách vùng được hệ thống cho phép. Không coi `Locale.Builder` là validator tất cả các mã vùng đăng ký.

### 8.2. `tz`: Unicode time-zone type không phải ID IANA

Ví dụ:

```java
Locale locale = Locale.forLanguageTag("en-US-u-tz-usnyc");
```

`usnyc` là kiểu mã Unicode time-zone extension. Nó **khác hệ mã** với vùng giờ IANA `America/New_York`. Không suy đoán mọi `ZoneId` lấy được bằng cách cắt chuỗi `tz` rồi gọi `ZoneId.of`, hoặc ngược lại.

Đối với input người dùng vốn là ID IANA như `Asia/Ho_Chi_Minh`, lựa chọn rõ ràng hơn cho ứng dụng `java.time` thường là:

```java
import java.time.DateTimeException;
import java.time.ZoneId;

try {
    ZoneId zone = ZoneId.of(userZoneId);
    // Lưu zone hợp lệ theo chính sách ứng dụng.
} catch (DateTimeException ex) {
    // Reject hoặc yêu cầu chọn múi giờ khác.
}
```

Đây là đoạn minh họa trong phương thức có biến `userZoneId`. `ZoneId.of` kiểm tra ID múi giờ theo `ZoneRulesProvider` có sẵn, **không** xác thực trực tiếp cú pháp/type của Unicode `tz`. Đừng dùng mã IANA cho `tz` mà không chuyển đổi đúng hệ registry.

### 8.3. `localizedBy` khác `withLocale`

`DateTimeFormatter.localizedBy(locale)` được thêm ở Java 10, có thể áp dụng các lựa chọn `ca`, `nu`, `rg`, `tz` của locale vào chronology, decimal style, time zone và dữ liệu định dạng theo hợp đồng. `withLocale(locale)` chủ yếu đặt Locale dùng cho localized text/pattern; không mặc nhiên giống việc xử lý đầy đủ mọi override.

```java
var formatter = java.time.format.DateTimeFormatter
        .ofLocalizedDateTime(
                java.time.format.FormatStyle.MEDIUM)
        .localizedBy(locale);
```

Đây là đoạn minh họa với `locale` đã khai báo; **không cố định một chuỗi output** vì CLDR/provider và timezone data có thể khác giữa các JDK. Nếu cần múi giờ **phải chính xác**, hãy xác thực `ZoneId` riêng, tạo formatter với `withZone(zone)` theo contract và kiểm thử hành vi theo các phiên bản runtime cần hỗ trợ.

## 9. Locale provider, fallback và tính portable

### 9.1. Dữ liệu được cung cấp theo từng service

Một `Locale` là **đối tượng mô tả yêu cầu i18n**; nó không chứa toàn bộ dữ liệu định dạng của mọi nước, không tự cam kết mọi extension làm thay đổi mọi API. Các service có thể sử dụng:
- Dữ liệu CLDR trong JDK.
- Provider được cài đặt theo `java.util.spi`.
- Các locale candidate/fallback theo hợp đồng dịch vụ.

Mô hình này giải thích vì sao một `Locale` có thể được tạo thành công và `toLanguageTag()` vẫn giữ extension, nhưng một formatter/bộ tra cứu cụ thể không phản ánh một type không được hỗ trợ.

### 9.2. `LocaleServiceProvider.isSupportedLocale` có giới hạn quan trọng

Theo Javadoc `LocaleServiceProvider`, implementation mặc định của `isSupportedLocale(Locale)` so sánh các locale được cung cấp **mà bỏ qua extension**; provider muốn xét extension cần ghi đè để hỗ trợ đúng. Vì vậy:

```java
// Pseudocode minh họa provider, KHÔNG phải chương trình runnable.
boolean supported = provider.isSupportedLocale(locale);
```

Ngay cả kết quả `true` từ một provider **chưa đủ** để chứng minh từng Unicode key/type user yêu cầu được hỗ trợ bởi service và bản thân phiên bản provider cụ thể. Hãy kiểm tra contract của service và xét các key có ý nghĩa với API.

### 9.3. Không dùng `getAvailableLocales` làm một bảng xác nhận type hoàn chỉnh

`getAvailableLocales` của `NumberFormat`, `DateFormat` hoặc provider có thể mô tả locale cơ sở có dữ liệu, nhưng **không liệt kê đầy đủ tất cả biến thể Unicode type mà service sẽ áp dụng**. Không xây một validator “mọi type của `cu` đều hợp lệ nếu `en-US` có trong available locales”.

Với các giá trị nghiệp vụ hữu hạn, nên kiểm tra:
- Khóa nào sản phẩm cho phép (ví dụ `fw` chỉ có bảy ngày).
- Type nào được công nhận trong registry và runtime cụ thể.
- Service thực tế có áp dụng preference không.
- Có fallback được phép, reject hay phải báo warning.

### 9.4. Không dùng locale mặc định toàn cục cho từng request

`Locale.setDefault(...)` thay đổi locale mặc định cho toàn bộ JVM theo phạm vi API tương ứng; trong dịch vụ đa người dùng, nó không phải cơ chế an toàn để xử lý một yêu cầu có locale không hỗ trợ. Mỗi yêu cầu nên mang `Locale` của chính nó đến `NumberFormat`/`DateTimeFormatter`/`WeekFields` cần dùng.

Khi có fallback, trả một đối tượng kết quả hoặc ghi log “requested / effective / reason” để biết preference nào đã được bỏ qua, không âm thầm sửa default JVM.

## 10. Lab Java độc lập: 18 kết quả xác định

Chương trình này kiểm tra **ba tầng**: tạo Locale, kiểm tra type/key của extension, và xử lý nghiệp vụ nếu giá trị không được hỗ trợ. Nó không dựa vào tên tháng, số dạng CLDR hay time-zone alias của một runtime cụ thể, nên output được thiết kế ổn định.

### 10.1. Môi trường

Sử dụng một bản **JDK được nhà cung cấp hỗ trợ và còn cập nhật bảo mật**, chẳng hạn JDK 21 hoặc 25 LTS theo chính sách tổ chức. Các API dùng trong lab đều còn được hỗ trợ; `cu`/`fw` được JEP 314 bổ sung hỗ trợ trong các service từ Java 10.

```bash
java -version
javac -version
```

Lưu đúng tệp **`LocaleUnsupportedValuesLab.java`**:

```java
import java.util.Currency;
import java.util.IllformedLocaleException;
import java.util.Locale;
import java.util.Set;
import java.time.DayOfWeek;
import java.time.temporal.WeekFields;

public class LocaleUnsupportedValuesLab {
    private static final Set<String> SUPPORTED_WEEK_STARTS =
            Set.of("sun", "mon", "tue", "wed", "thu", "fri", "sat");

    // Chính sách của ứng dụng: tag sai hoặc fw không được công nhận
    // thì dùng fallback do caller cung cấp; không đoán fallback JDK.
    static Locale chooseWeekLocale(String tag, Locale fallback) {
        if (tag == null) {
            return fallback;
        }
        try {
            Locale candidate = new Locale.Builder()
                    .setLanguageTag(tag).build();
            String value = candidate.getUnicodeLocaleType("fw");
            if (value != null
                    && !SUPPORTED_WEEK_STARTS.contains(value)) {
                return fallback;
            }
            return candidate;
        } catch (IllformedLocaleException ex) {
            return fallback;
        }
    }

    // Ví dụ fallback để HIỂN THỊ. Không tự động đổi tiền
    // thanh toán/số dư/ledger sang USD ở hệ thống thật.
    static Currency chooseCurrency(String code, Currency fallback) {
        if (code == null || !code.matches("[a-zA-Z]{3}")) {
            return fallback;
        }
        try {
            return Currency.getInstance(
                    code.toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException ex) {
            return fallback;
        }
    }

    public static void main(String[] args) {
        Locale currencyLocale = new Locale.Builder()
                .setLanguage("en").setRegion("US")
                .setUnicodeLocaleKeyword("cu", "JPY").build();

        System.out.println("normalized cu: "
                + currencyLocale.getUnicodeLocaleType("cu"));
        System.out.println("cu currency code: "
                + Currency.getInstance(currencyLocale)
                        .getCurrencyCode());

        Locale monday =
                Locale.forLanguageTag("en-US-u-fw-mon");
        System.out.println("fw MONDAY: "
                + (WeekFields.of(monday).getFirstDayOfWeek()
                        == DayOfWeek.MONDAY));

        Locale unknownKey = new Locale.Builder()
                .setLanguage("en").setRegion("US")
                .setUnicodeLocaleKeyword("zz", "alpha")
                .build();

        System.out.println("unknown key retained: "
                + "alpha".equals(
                        unknownKey.getUnicodeLocaleType("zz")));
        System.out.println("absent fw is null: "
                + (unknownKey.getUnicodeLocaleType("fw") == null));

        Locale emptyFw = new Locale.Builder()
                .setLanguage("en").setRegion("US")
                .setUnicodeLocaleKeyword("fw", "").build();
        System.out.println("present fw empty: "
                + "".equals(
                        emptyFw.getUnicodeLocaleType("fw")));

        Locale unsupportedFw = new Locale.Builder()
                .setLanguageTag("en-US-u-fw-blorp").build();
        System.out.println("unsupported fw retained: "
                + "blorp".equals(
                        unsupportedFw.getUnicodeLocaleType("fw")));

        System.out.println("valid fw selected: "
                + chooseWeekLocale(
                        "en-US-u-fw-mon", Locale.US)
                        .toLanguageTag());
        System.out.println("unsupported fw fallback: "
                + chooseWeekLocale(
                        "en-US-u-fw-blorp", Locale.US)
                        .toLanguageTag());
        System.out.println("malformed fw fallback: "
                + chooseWeekLocale(
                        "en-US-u-fw-!", Locale.US)
                        .toLanguageTag());

        try {
            new Locale.Builder()
                    .setUnicodeLocaleKeyword("f", "mon");
        } catch (IllformedLocaleException ex) {
            System.out.println(
                    "bad key: IllformedLocaleException");
        }

        try {
            new Locale.Builder()
                    .setLanguageTag("en-US-u-fw-!");
        } catch (IllformedLocaleException ex) {
            System.out.println(
                    "bad tag: IllformedLocaleException");
        }

        System.out.println("lenient parser accepted prefix: "
                + Locale.forLanguageTag("en-US-u-fw-!")
                        .toLanguageTag());

        try {
            unknownKey.getUnicodeLocaleType("f");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "bad lookup key: IllegalArgumentException");
        }

        System.out.println("recognized code JPY: "
                + chooseCurrency(
                        "jpy", Currency.getInstance("USD"))
                        .getCurrencyCode());
        System.out.println("unknown code falls back: "
                + chooseCurrency(
                        "ZZZ", Currency.getInstance("USD"))
                        .getCurrencyCode());
        System.out.println("null code falls back: "
                + chooseCurrency(
                        null, Currency.getInstance("USD"))
                        .getCurrencyCode());

        Locale unknownCurrency = new Locale.Builder()
                .setLanguage("en").setRegion("US")
                .setUnicodeLocaleKeyword("cu", "zzzz").build();
        System.out.println("unknown cu retained: "
                + "zzzz".equals(
                        unknownCurrency.getUnicodeLocaleType("cu")));
    }
}
```

### 10.2. Biên dịch và chạy

```bash
javac LocaleUnsupportedValuesLab.java
java LocaleUnsupportedValuesLab
```

### 10.3. Stdout chính xác (18 dòng)

```text
normalized cu: jpy
cu currency code: JPY
fw MONDAY: true
unknown key retained: true
absent fw is null: true
present fw empty: true
unsupported fw retained: true
valid fw selected: en-US-u-fw-mon
unsupported fw fallback: en-US
malformed fw fallback: en-US
bad key: IllformedLocaleException
bad tag: IllformedLocaleException
lenient parser accepted prefix: en-US-u-fw
bad lookup key: IllegalArgumentException
recognized code JPY: JPY
unknown code falls back: USD
null code falls back: USD
unknown cu retained: true
```

Các dòng không in toàn bộ kết quả định dạng theo CLDR nên ổn định hơn việc chốt chuỗi tiền tệ, tên tuần hay tên múi giờ cho mọi JDK. `Currency` USD/JPY là các mã đã biết; ví dụ fallback USD là **chính sách minh họa** của ứng dụng.

### 10.4. Ý nghĩa của từng nhóm output

1. **`normalized cu: jpy`:** Builder chuẩn hóa chữ thường của type. **`cu currency code: JPY`:** `Currency.getInstance(locale)` áp dụng extension `cu` hợp lệ trong ví dụ.
2. **`fw MONDAY: true`:** `WeekFields.of(locale)` tôn trọng `fw-mon`, xác nhận hành vi của một service cụ thể, không chỉ kiểm tra tag có chứa chuỗi `mon`.
3. **`unknown key retained: true`:** Locale bảo toàn keyword đúng cú pháp `zz=alpha`; đây không phải lời xác nhận rằng mọi JDK API đều hỗ trợ `zz`.
4. **`absent fw is null: true`** so với **`present fw empty: true`:** phân biệt không có keyword và có keyword với type rỗng.
5. **`unsupported fw retained: true`:** type `blorp` được giữ lại dù không là một ngày được cho phép trong policy.
6. **`valid fw selected: en-US-u-fw-mon`:** helper bảo toàn locale khi type hợp lệ.
7. **`unsupported fw fallback: en-US`** và **`malformed fw fallback: en-US`:** helper có chính sách fallback rõ cho type không hỗ trợ và tag sai cú pháp. Đây **không** phải hành vi mặc định được áp đặt cho `Locale.Builder`.
8. **`bad key` và `bad tag`:** Builder ném `IllformedLocaleException` với cú pháp sai.
9. **`lenient parser accepted prefix: en-US-u-fw`:** `forLanguageTag` chỉ giữ prefix hợp lệ theo hợp đồng, không ném lỗi. Không được dùng nó để chứng minh toàn bộ input là hợp lệ.
10. **`bad lookup key: IllegalArgumentException`:** `getUnicodeLocaleType("f")` có key sai cấu trúc.
11. **`recognized code JPY: JPY`:** helper nhận code tiền tệ được hỗ trợ.
12. **`unknown code falls back: USD`, `null code falls back: USD`:** lựa chọn fallback **do chính helper định nghĩa**, không phải do `Currency.getInstance("ZZZ")` tự chọn USD.
13. **`unknown cu retained: true`:** một type đúng cấu trúc như `zzzz` vẫn có thể được lưu trong locale; đừng nhầm việc lưu trữ với lựa chọn currency đã được xác nhận.

## 11. Thiết kế API ứng dụng khi phải xử lý giá trị không hỗ trợ

### 11.1. Chọn hợp đồng đầu ra rõ ràng

Một API tiếp nhận cấu hình i18n có thể trả:

```text
Requested: en-US-u-fw-blorp
Status: UNSUPPORTED_VALUE
Effective: en-US
Reason: fw=blorp is not an allowed week-start type
Policy: FALLBACK_TO_CONFIGURED_LOCALE
```

Đây là **mẫu thông điệp nghiệp vụ**, không phải text mà Java JDK tự trả. Với policy REJECT, có thể trả lỗi cấu hình thay vì một effective locale.

Nếu ứng dụng phải lưu lựa chọn người dùng, nên giữ **raw requested tag** và **effective resolved settings** riêng biệt để hỗ trợ debug, cho phép re-evaluate sau khi nâng cấp runtime và không nhầm một lựa chọn bị bỏ qua với lựa chọn đã được áp dụng.

### 11.2. Không đặt một fallback giống nhau cho tất cả API

| Ngữ cảnh | Gợi ý chính sách | Vì sao |
| --- | --- | --- |
| Tiền tệ dùng để tính tiền, thanh toán, kế toán | **REJECT** code không nhận diện hoặc không thuộc danh sách sản phẩm cho phép | Fallback USD/JPY không được phép tự đổi nghĩa khoản tiền |
| Biểu tượng tiền hiển thị dạng xem trước | FALLBACK có chú thích, chỉ nếu business cho phép | Chỉ là định dạng; vẫn cần biết currency gốc |
| Ngày bắt đầu tuần trong UI lịch | FALLBACK sang locale đã cấu hình hoặc REJECT tùy sản phẩm | Giá trị lạ như `blorp` không có nghĩa dùng được |
| Múi giờ nghiệp vụ cho lịch hẹn | **REJECT** ID không hợp lệ, hoặc yêu cầu chọn lại | Sai giờ gây hậu quả thực tế; nên kiểm tra `ZoneId` |
| Format số/ngày cho nội dung ít quan trọng | BEST_EFFORT được phép nếu đã tài liệu hóa | Locale provider có cơ chế candidate fallback |
| Khóa extension không biết như `zz` | Ignore/REJECT tùy hợp đồng API của ứng dụng | Một service không có nghĩa vụ diễn giải tất cả keys |

Không “trả `Locale.ROOT` mặc định” nếu đó không phải fallback phù hợp, vì `ROOT` là locale trung tính có thể không phản ánh ngôn ngữ người dùng. Fallback nên là một lựa chọn **được cấu hình hoặc phê duyệt**, không phải một biến JVM global có thể đổi bất ngờ.

### 11.3. Nên tách validation của locale khỏi validation của currency

```java
Locale request = new Locale.Builder()
        .setLanguageTag(requestedTag)
        .build();

Currency moneyCurrency =
        Currency.getInstance(requestedCurrencyCode);
```

Hai dòng minh họa nằm trong phương thức có input đã khai báo và exception handling. Dòng đầu validate **cú pháp tag**; dòng thứ hai validate **currency code được JVM hỗ trợ**. Khi loại tiền ảnh hưởng đến nghiệp vụ, nguồn chân lý của currency phải được thiết kế riêng thay vì chỉ nhìn vào `Locale.getUnicodeLocaleType("cu")`.

### 11.4. Khi cần phản hồi lỗi thay vì fallback, dùng exception đúng tầng

Có thể quy đổi:
- `IllformedLocaleException` → “language tag/key/type sai cú pháp”.
- `IllegalArgumentException` từ `Currency.getInstance(String)` → “currency code không được hỗ trợ”.
- `null` từ `Currency.getInstance(Locale)` → “vùng không có currency theo dữ liệu hiện tại”; đây không phải exception.
- Keyword không có trong `getUnicodeLocaleType` → “không được yêu cầu” nếu optional.
- Keyword có type lạ → “không được ứng dụng hỗ trợ” nếu allowlist không chứa.
- `DateTimeException` từ `ZoneId.of` → “time zone ID không được nhận”.
- Kết quả service fallback nhưng không đúng preference bắt buộc → “không thể đáp ứng preference” theo hợp đồng ứng dụng, **không** coi là success silent.

Không bắt mọi `RuntimeException` rồi luôn trả locale mặc định, vì điều đó có thể che lỗi lập trình và khiến service trả dữ liệu sai không thể truy vết.

## 12. Kiểm thử hành vi có và không được hỗ trợ

### 12.1. Test cú pháp

- Input `en-US-u-fw-mon` → `new Locale.Builder().setLanguageTag(...)` không ném lỗi.
- Input `en-US-u-fw-!` → `IllformedLocaleException`.
- Gọi `setUnicodeLocaleKeyword("f","mon")` → `IllformedLocaleException` vì key ngắn.
- Gọi `getUnicodeLocaleType("f")` → `IllegalArgumentException` vì lookup key sai cú pháp.
- `forLanguageTag` với input sai chỉ mang ý nghĩa **lenient parser**, test nó riêng.

### 12.2. Test semantic values

- `fw=mon` nằm trong allowlist bảy ngày.
- `fw=blorp` là syntax-valid, nhưng ứng dụng phải reject/fallback.
- `fw=""` và `fw=null` có ý nghĩa khác nhau; không lẫn vắng mặt với type rỗng.
- `cu=jpy` là type có thể được service hiểu; `cu=zzzz` chỉ đúng hình thức, không được nhận diện như một đồng tiền hợp lệ của sản phẩm.
- Với `rg`/`tz`, kiểm tra registry/dữ liệu theo yêu cầu, không chỉ `startsWith("u-rg-")`.

### 12.3. Test hợp đồng từng service

- Với `Currency.getInstance("JPY")`, kiểm tra `getCurrencyCode().equals("JPY")`.
- Với code không được hỗ trợ như `"ZZZ"`, bắt `IllegalArgumentException` ở overload nhận chuỗi.
- Với `WeekFields.of(Locale.forLanguageTag("en-US-u-fw-mon"))`, kiểm tra `getFirstDayOfWeek()==MONDAY`.
- Với locale hiếm hoặc locale data thiếu, không khóa cứng một chuỗi tên tháng/ngày hoặc cách nhóm số phụ thuộc CLDR.
- Với time zone do user nhập, kiểm tra `ZoneId.of` và hành vi thực tế của formatter, không suy từ mỗi presence của `tz`.

### 12.4. Test fallback do ứng dụng định nghĩa

Test helper `chooseWeekLocale` bằng cách đưa `Locale.US` làm fallback:
- Known `en-US-u-fw-mon` → giữ tag.
- Unsupported `en-US-u-fw-blorp` → trả `en-US`.
- Malformed `en-US-u-fw-!` → trả `en-US`.

Test helper `chooseCurrency`:
- `"jpy"` → `JPY`.
- `"ZZZ"` → USD fallback.
- `null` → USD fallback.

Những test này độc lập với việc thử đoán JDK hiện tại có tự bỏ qua type nào hay không. **Đó là test chính sách ứng dụng**, không phải cố ép implementation JDK làm giống kỳ vọng của test.

### 12.5. Test tích hợp trên nhiều runtime

Với ứng dụng toàn cầu, cần ma trận runtime/JDK distributions/CLDR data theo môi trường mà sản phẩm cam kết. Những yếu tố dễ khác là:
- Tên vùng, cách ghi tiền tệ, tên tháng/ngày.
- Kết quả với locale/provider hiếm.
- Mapping Unicode `tz` type sang zone data.
- Những type Unicode/CLDR mới được cập nhật giữa phiên bản JDK.
- Các JDK runtime images được `jlink` rút gọn module dữ liệu locale.

Không biến sự khác nhau hợp lệ của dữ liệu địa phương hóa thành lỗi unit test “bắt buộc mọi JDK in cùng một chuỗi định dạng”. Unit test nên khóa **hợp đồng và chính sách**; integration tests kiểm chứng **dữ liệu locale trên runtime cụ thể**.

## 13. Lỗi phổ biến và cách sửa

| Lỗi phổ biến | Hậu quả | Cách sửa |
| --- | --- | --- |
| `Locale.Builder.build()` thành công nên coi mọi `fw/tz/cu` có hiệu lực | Type có thể chỉ well-formed | Kiểm tra semantic allowlist và service contract |
| Cho rằng `Locale.forLanguageTag` luôn reject cú pháp sai | Nó có thể bỏ phần sai và phần theo sau | Dùng `Builder.setLanguageTag` khi cần strict validation |
| Cho rằng `setUnicodeLocaleKeyword("fw","blorp")` phải ném exception | `blorp` đúng cú pháp Unicode type | Validate bảy type hợp lệ ở tầng ứng dụng |
| Coi `getUnicodeLocaleType("fw")==null` như type rỗng | Vắng mặt và type rỗng khác nhau | Kiểm tra riêng `null` / `""` |
| Nghĩ `getUnicodeLocaleType("zz")` trả type tức là provider hỗ trợ `zz` | `Locale` có thể lưu key chưa có service xử lý | Xem docs của service và registry |
| Nghĩ `getAvailableLocales` liệt kê mọi Unicode key/type được áp dụng | Nó chủ yếu mô tả locale dữ liệu, không phải toàn bộ keyword combinations | Kiểm tra service-specific support |
| Bắt `IOException` cho `Currency.getInstance("ZZZ")` | Lỗi này là `IllegalArgumentException`, không phải I/O | Bắt đúng ngoại lệ và policy miền |
| Gọi `Currency.getInstance(Locale)` rồi luôn dereference | Có thể trả `null` với vùng không có currency | Xử lý null theo API contract |
| Âm thầm chuyển unknown currency thành USD ở tính toán tiền | Sai nghĩa số tiền, có thể gây lỗi tài chính | Reject hoặc dùng một quy tắc nghiệp vụ đã được phê duyệt |
| Dùng `Locale.getCountry()` để kết luận `rg` không có tác dụng | `rg` có thể tác động dữ liệu của service mà không đổi trường country | Kiểm tra API nhận Locale và hiệu ứng thực tế |
| Đưa `America/New_York` làm type `tz` mà không đổi hệ mã | Unicode tz type không trùng IANA Zone ID | Dùng mapping/registry đúng; `ZoneId.of` cho ID IANA |
| Dùng `DateTimeFormatter.withLocale` thay `localizedBy` rồi mong tự chọn zone từ `tz` | Hai API có hợp đồng khác | Dùng `localizedBy` khi cần xử lý extension, hoặc `withZone` với ZoneId explicit |
| Set `Locale.setDefault` ở mỗi HTTP request | Thay trạng thái dùng chung của JVM, dễ race | Truyền locale riêng theo request |
| So sánh output định dạng chính xác giữa mọi JDK | CLDR/provider dữ liệu có thể thay đổi | Test hành vi hợp đồng + integration theo JDK mục tiêu |
| Bắt `RuntimeException` rồi silent fallback | Che lỗi lập trình và lỗi cấu hình | Bắt loại exception được docs nêu, log lý do |
| Trả fallback mà không lưu requested input | Không truy vết được giá trị bị bỏ qua | Lưu requested/effective/reason riêng |

## 14. Bài tập (có đáp án)

### Bài 1 — Suy luận Builder

```java
Locale locale = new Locale.Builder()
        .setLanguageTag("en-US-u-fw-blorp")
        .build();
```

**Hỏi:** Có bắt buộc ném `IllformedLocaleException` không?

**Đáp án:** Không. `blorp` đúng dạng một type subtag về cú pháp. Nhưng đó không phải type ngày đầu tuần thuộc tập `sun`...`sat`. Kiểm tra ý nghĩa ở tầng service hoặc ứng dụng trước khi sử dụng.

### Bài 2 — Cú pháp sai thật

`new Locale.Builder().setUnicodeLocaleKeyword("f", "mon")` sẽ ra sao?

**Đáp án:** Ném `IllformedLocaleException` vì Unicode locale keyword key phải có hai ký tự chữ/số.

### Bài 3 — Parser có chấp nhận một prefix không?

`Locale.forLanguageTag("en-US-u-fw-!")` có phải API strict validation trả lỗi?

**Đáp án:** Không. API có thể bỏ từ subtag sai cú pháp đầu tiên trở đi và trả một Locale đại diện cho phần hợp lệ. Dùng `Builder.setLanguageTag` nếu cần reject toàn bộ input sai.

### Bài 4 — Vắng mặt so với rỗng

`getUnicodeLocaleType("fw")` trả `null` hay `""` trong hai trường hợp: không có keyword `fw` và có `fw` nhưng không có type?

**Đáp án:** Không có keyword → `null`; keyword có nhưng type rỗng → `""`. Đừng coi chúng tương đương khi policy yêu cầu ngày đầu tuần explicit.

### Bài 5 — Tiền tệ từ chuỗi

`Currency.getInstance("ZZZ")` có tự trả USD để fallback không?

**Đáp án:** Không. Với mã không được hỗ trợ, overload chuỗi ném `IllegalArgumentException`. Việc trả USD trong lab là do helper `chooseCurrency` định nghĩa, không phải fallback tự động của overload này.

### Bài 6 — Tiền tệ từ locale

`Currency.getInstance(locale)` có luôn trả một object không null?

**Đáp án:** Không. Javadoc cho phép trả `null` đối với vùng không có tiền tệ; cũng có thể ném `IllegalArgumentException` cho country code không được hỗ trợ. Cần xử lý theo overload cụ thể.

### Bài 7 — Locale đã chứa `cu=zzzz`

Một `Locale` tạo thành công với `cu=zzzz`. Có chứng minh `Currency.getInstance(locale)` phải trả currency tên `ZZZZ` không?

**Đáp án:** Không. Builder kiểm tra cú pháp keyword; `zzzz` không đồng nghĩa mã ISO 4217 được hỗ trợ. Xác thực code độc lập và theo contract nghiệp vụ.

### Bài 8 — Ngày đầu tuần

`WeekFields.of(Locale.forLanguageTag("en-US-u-fw-mon")).getFirstDayOfWeek()` bằng gì?

**Đáp án:** `MONDAY`, theo hỗ trợ `fw`. Đừng suy từ default US mà bỏ qua override `fw`.

### Bài 9 — `fw` và `rg` cùng có mặt

Nếu cả `fw` và `rg` xuất hiện, giá trị ngày đầu tuần do `fw` hay vùng mới suy ra được ưu tiên trong `WeekFields.of(Locale)`?

**Đáp án:** Javadoc quy định `fw` ghi đè ngày đầu tuần mặc định theo `rg`. Những thành phần khác của week definition vẫn cần xem dữ liệu locale/service.

### Bài 10 — Type timezone

`"usnyc"` trong `u-tz-usnyc` và `"America/New_York"` trong `ZoneId.of` là cùng định dạng mã?

**Đáp án:** Không. Một bên là Unicode locale time-zone type, bên kia là vùng giờ IANA. Dùng API/mapping đúng cho từng mục đích; `ZoneId.of` không phải validator trực tiếp cho type `tz`.

### Bài 11 — Chiến lược fallback

User nhập `fw=blorp`. Ứng dụng đặt chính sách “nếu không hỗ trợ, sử dụng `Locale.US`”. Kết quả nào cần test?

**Đáp án:** Test rằng helper phát hiện `blorp` không thuộc tập bảy ngày và trả `Locale.US`. Không dựa vào chuyện JDK hiện tại có bỏ qua `blorp` hay không.

### Bài 12 — Tiền tệ trong checkout

User nhập loại tiền không được hỗ trợ ở bước tạo đơn hàng. Có nên silent fallback USD như lab không?

**Đáp án:** Không, trừ khi có một quy tắc nghiệp vụ rõ và được chấp nhận. Với giao dịch, nên reject, yêu cầu người dùng chọn lại hoặc làm theo currency thực sự của giá/đơn hàng; không tự thay nghĩa khoản tiền.

### Bài 13 — `getAvailableLocales`

`NumberFormat.getAvailableLocales()` chứa `en-US`. Có thể suy luận mọi type `nu`, `rg` và `cu` mà user gắn vào `en-US` đều được service nhận không?

**Đáp án:** Không. Danh sách available locales không phải bảng đầy đủ các keyword/type được hỗ trợ. Phải xem Javadoc và runtime/provider cụ thể.

### Bài 14 — Kiểm thử portable

Một test yêu cầu `DateTimeFormatter.localizedBy(en-US-u-tz-...)` in đúng cùng tên múi giờ và kiểu ngày trên mọi JDK. Có chắc hợp lý không?

**Đáp án:** Không, vì dữ liệu locale, zone và CLDR có thể khác giữa phiên bản/provider. Test những điều contract bảo đảm, và dùng integration tests trên các runtime tổ chức hỗ trợ khi yêu cầu hiển thị cụ thể.

## 15. Checklist trước khi đưa vào production

- [ ] Xác định rõ input là **BCP 47 tag**, **Unicode keyword type**, **ISO 4217 currency code** hay **IANA ZoneId**; không trộn hệ mã.
- [ ] Đọc `Locale.Builder.setLanguageTag` để kiểm tra cú pháp input yêu cầu strict.
- [ ] Không dùng `Locale.forLanguageTag` như công cụ reject mọi tag sai cấu trúc.
- [ ] Phân biệt key/type đúng cú pháp với type có ý nghĩa trong Unicode/CLDR registry.
- [ ] Nhớ Java 10/JEP 314 thêm `cu`, `fw`, `rg`, `tz` vào các service có liên quan, **không phải hỗ trợ mọi extension trong mọi API**.
- [ ] Phân biệt `null` và `""` từ `getUnicodeLocaleType`.
- [ ] Đọc riêng contract của `Currency.getInstance(String)` và `Currency.getInstance(Locale)`.
- [ ] Xác thực currency code theo ISO/runtime và chính sách nghiệp vụ trước khi dùng vào số tiền.
- [ ] Với `fw`, kiểm tra giá trị trong bảy mã ngày nếu cần bảo đảm hiệu lực.
- [ ] Với `rg` và `tz`, dùng dữ liệu registry/mapping phù hợp; không lấy `getCountry` hay `ZoneId.of` làm validator mọi loại extension.
- [ ] Biết `WeekFields.of` tôn trọng `fw`/`rg` theo Javadoc và `fw` ưu tiên khi có cả hai.
- [ ] Dùng `DateTimeFormatter.localizedBy` khi thực sự cần locale extensions ảnh hưởng chronology/decimal style/zone; không coi `withLocale` là tương đương.
- [ ] Không dùng `Locale.setDefault` để phục vụ locale từng request trong server nhiều người dùng.
- [ ] Định nghĩa **REJECT/FALLBACK/BEST_EFFORT** theo ý nghĩa chức năng, không để hành vi tình cờ của provider quyết định.
- [ ] Lưu requested, effective và reason khi fallback để debug/audit.
- [ ] Viết tests tách cú pháp, semantic value, service behavior, business policy và portability.
- [ ] Chạy `LocaleUnsupportedValuesLab.java` và đối chiếu **18 dòng stdout**.

## 16. Kết luận

Khi làm việc với mở rộng Locale trong Java 10+, **“Locale chứa một Unicode extension” chỉ có nghĩa là dữ liệu yêu cầu đã được biểu diễn**, không tự cam kết giá trị ấy được nhận diện và có hiệu lực với mọi API. Cách xử lý đúng là: **kiểm tra cú pháp → xác thực type theo lĩnh vực → kiểm tra hợp đồng service → áp dụng reject/fallback/best-effort có chủ đích → kiểm thử trên môi trường cần hỗ trợ**.

Đối với `cu`, `fw`, `rg` và `tz` của JEP 314, sự khác biệt này đặc biệt quan trọng. Java có nhiều cách báo trạng thái không hỗ trợ: `IllformedLocaleException` khi tag sai cú pháp, `IllegalArgumentException` ở một số phép tra cứu, `null` ở một số API, hoặc fallback theo dữ liệu locale provider. **Không có một quy tắc ngoại lệ/fallback duy nhất cho mọi extension.** Hiểu đúng từng API giúp ứng dụng quốc tế hóa vừa đúng kỹ thuật, vừa không âm thầm đổi nghĩa yêu cầu của người dùng.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 314 — Additional Unicode Language-Tag Extensions](https://openjdk.org/jeps/314): Java 10 mở rộng hỗ trợ `cu`, `fw`, `rg`, `tz` cho các service được liệt kê.
- [Oracle Java SE 25 — Locale](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html): BCP 47, Unicode extensions, `getUnicodeLocaleType`, `forLanguageTag`, `getCountry`.
- [Oracle Java SE 25 — Locale.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.Builder.html): cú pháp và `IllformedLocaleException`, `setLanguageTag`, `setUnicodeLocaleKeyword`.
- [Oracle Java SE 25 — Currency](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Currency.html): hai overload `getInstance`, `cu`/`rg`, mã không hỗ trợ và kết quả `null`.
- [Oracle Java SE 25 — WeekFields](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/WeekFields.html): `fw`/`rg`, thứ tự ưu tiên và `DayOfWeek`.
- [Oracle Java SE 25 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html): `localizedBy(Locale)` (Since: 10) so với `withLocale(Locale)`.
- [Oracle Java SE 25 — LocaleServiceProvider](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): dữ liệu provider, `isSupportedLocale` và extension.
- [Oracle Java SE 25 — ZoneId](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZoneId.html): IANA-style zone IDs và `DateTimeException`.
- [Oracle — Internationalization Enhancements in JDK 10](https://docs.oracle.com/javase/10/intl/internationalization-enhancements-jdk-10.htm): danh sách bốn Unicode extensions được mở rộng từ JDK 10.