# Java 10 — Khóa `rg` để ghi đè vùng trong `Locale`

## 1. Mục tiêu

Ứng dụng có thể cần giữ ngôn ngữ, thông tin locale cơ sở của người dùng nhưng áp dụng **một số mặc định theo vùng khác**. Ví dụ, giao diện vẫn là tiếng Anh và `Locale` cơ sở `en-US`, trong khi quy tắc tiền tệ, ngày đầu tuần hay mẫu ngày được chọn theo Vương quốc Anh.

Java 10, thông qua **OpenJDK JEP 314 — Additional Unicode Language-Tag Extensions**, bổ sung hỗ trợ Unicode locale key **`rg` (region override)** trong các API quốc tế hóa tiêu chuẩn có liên quan.

Ví dụ:

```text
en-US-u-rg-gbzzzz
|____| |_________|
locale  Unicode locale extension
cơ sở  rg: lấy một số mặc định theo vùng GB
```

Trong `en-US-u-rg-gbzzzz`, các thuộc tính ngôn ngữ `en` và vùng cơ sở `US` vẫn còn nguyên. Dữ liệu khu vực được **một số API hỗ trợ `rg`** lấy theo GB. Đây **không phải** lệnh sửa `Locale.getCountry()` thành `GB`.

Bài học tập trung vào:

1. Cú pháp `-u-rg-<region>zzzz` theo Unicode BCP 47/LDML;
2. Hai cách tạo locale bằng `Locale.forLanguageTag` và `Locale.Builder`;
3. Phân biệt **region cơ sở** và **region override**;
4. Những loại hành vi thực tế được `rg` tác động, nhất là `Currency`, `WeekFields` và định dạng ngày;
5. Thứ tự ưu tiên khi đồng thời có `cu` hoặc `fw`;
6. Validation, CLDR/provider và các giới hạn quan trọng;
7. Ví dụ chạy độc lập, lệnh biên dịch, stdout đã kiểm chứng và bài tập.

**Nguyên tắc phiên bản:** `rg` được các thư viện liên quan hỗ trợ từ **Java 10** và vẫn hữu ích trên JDK hiện đại. Bài chỉ sử dụng các kiến thức còn áp dụng; mọi ví dụ độc lập đã được biên dịch với `javac --release 10`.

## 2. `Locale` biểu diễn những gì?

`java.util.Locale` là một ngữ cảnh về ngôn ngữ, script, region và các tùy chọn quốc tế hóa. Một thẻ ngôn ngữ BCP 47 có thể gồm:

```text
language[-Script][-REGION][-variants...][-u-key-type...]
```

Ví dụ:

| Thẻ | Ý nghĩa |
|---|---|
| `en-US` | Tiếng Anh, region cơ sở US |
| `en-GB` | Tiếng Anh, region cơ sở GB |
| `vi-VN` | Tiếng Việt, region cơ sở VN |
| `en-US-u-rg-gbzzzz` | Tiếng Anh/US là cơ sở; đề xuất dùng GB cho những mặc định vùng được hỗ trợ |
| `en-GB-u-rg-uszzzz` | Tiếng Anh/GB là cơ sở; đề xuất dùng US cho những mặc định vùng được hỗ trợ |
| `en-US-u-cu-eur-fw-sun-rg-gbzzzz` | Locale cơ sở en-US; dùng vùng GB nhưng chọn tường minh EUR và Sunday |

Một `Locale` **không** xác thực GPS, IP, quốc tịch, nơi cư trú hoặc đơn vị tiền tệ thực của giao dịch. Nó là **ngữ cảnh để những thư viện có khả năng quốc tế hóa chọn cách xử lý mặc định**.

### 2.1. Ba yếu tố khác nhau

Xét:

```java
Locale locale = Locale.forLanguageTag("en-US-u-rg-gbzzzz");
```

Mảnh code cần import `java.util.Locale` và nằm trong phương thức.

| Câu hỏi | Kết quả | API |
|---|---|---|
| Ngôn ngữ cơ sở là gì? | `en` | `locale.getLanguage()` |
| Region cơ sở là gì? | `US` | `locale.getCountry()` |
| Có Unicode key `rg` không? | Có | `locale.getUnicodeLocaleKeys()` |
| Giá trị của `rg` là gì? | `gbzzzz` | `locale.getUnicodeLocaleType("rg")` |
| Thẻ đầy đủ là gì? | `en-US-u-rg-gbzzzz` | `locale.toLanguageTag()` |

**Kết luận:** `Locale.getCountry()` **không** trả vùng ghi đè. Nếu code của bạn cần biết cấu hình `rg`, hãy đọc `getUnicodeLocaleType("rg")` hoặc chính thẻ BCP 47. Nếu code cần vùng gốc của locale, sử dụng `getCountry()`.

Không nên thay `en-US-u-rg-gbzzzz` bằng `en-GB` chỉ vì hai locale này đôi khi cho cùng mặc định tiền tệ hoặc ngày đầu tuần. Chúng khác **vùng cơ sở** và có thể dẫn đến kết quả khác trong những dịch vụ không dùng `rg`.

## 3. Bối cảnh lịch sử: JEP 314 bổ sung gì ở Java 10?

Java hỗ trợ BCP 47 và Unicode locale extension từ trước Java 10. Những khóa về calendar (`ca`) và numbering system (`nu`) đã có hỗ trợ trong một số API từ các JDK trước.

**JEP 314, phát hành cùng JDK 10**, mở rộng việc hỗ trợ bốn khóa:

| Khóa Unicode | Nghĩa | Ví dụ |
|---|---|---|
| `cu` | Currency type | `u-cu-eur` |
| `fw` | First day of week | `u-fw-mon` |
| **`rg`** | **Region override** | `u-rg-gbzzzz` |
| `tz` | Time-zone preference trong các API có hỗ trợ | `u-tz-...` |

Điểm mới **không phải** class `Locale` hay method `Locale.Builder` được tạo ra lần đầu. Điểm mới là **các service có liên quan thực sự diễn giải `rg`** khi chọn dữ liệu địa phương theo vùng.

JEP 314 liệt kê những API tiêu biểu dùng `rg`:

- `Currency.getInstance(Locale)`;
- `WeekFields.of(Locale)`;
- `Calendar.getFirstDayOfWeek()` và `getMinimalDaysInFirstWeek()` khi dùng locale có extension;
- `DateFormat.get...Instance(...)` và `DateFormatSymbols.getInstance(Locale)`;
- `NumberFormat.get...Instance(Locale)` và `DecimalFormatSymbols.getInstance(Locale)`;
- `DateTimeFormatter.localizedBy(Locale)`;
- `DateTimeFormatterBuilder.getLocalizedDateTimePattern(...)`;
- `DecimalStyle.of(Locale)`.

Đừng suy rằng **mọi** API nhận `Locale` đều áp dụng `rg`. `rg` là một tùy chọn **cho các dịch vụ locale-sensitive được hỗ trợ**, không phải một lệnh thay toàn bộ thuộc tính của đối tượng.

## 4. Cú pháp của `rg`: tại sao có `zzzz`?

Một giá trị dành cho **toàn vùng** được biểu diễn theo dạng thông dụng:

```text
<region-code>zzzz
```

Ví dụ:

```text
gbzzzz = GB + zzzz
uszzzz = US + zzzz
```

Unicode CLDR/LDML định nghĩa `rg` bằng một region/subdivision identifier thích hợp. Với yêu cầu vùng ở cấp quốc gia hay lãnh thổ toàn phần, hậu tố `zzzz` thường được dùng để chỉ **toàn vùng**.

Cấu trúc thẻ:

```text
en-US-u-rg-gbzzzz
en-US  : ngôn ngữ và vùng cơ sở
-u-    : singleton mở Unicode locale extension
rg     : khóa region override
gbzzzz : type của khóa rg, vùng GB ở cấp toàn vùng
```

**Không nên viết `rg-gb`** rồi kỳ vọng mọi thư viện hiểu đây là request override toàn GB. Dạng `rg-gbzzzz` là cách biểu diễn chuẩn thông dụng. `zzzz` không phải time zone, không phải mã ngôn ngữ và cũng không phải chuỗi trang trí tùy ý.

### 4.1. Có phân biệt hoa/thường không?

Thẻ BCP 47 không phân biệt hoa/thường ở những subtags liên quan. `Locale` chuẩn hóa extension key và type sang chữ thường:

```java
Locale loc = Locale.forLanguageTag("en-US-u-rg-GBZZZZ");
System.out.println(loc.getUnicodeLocaleType("rg"));
// gbzzzz
```

Đây là mảnh code cần import `Locale`. Khi lưu cấu hình, nên dùng thẻ canonical do `toLanguageTag()` trả về để giảm lỗi xử lý chuỗi.

### 4.2. Vùng ba chữ số và tính hợp lệ ngữ nghĩa

Unicode/IETF cũng có những region subtags dạng số. Tuy vậy, **một chuỗi có hình thức đúng không đồng nghĩa là mã vùng hợp lệ hoặc provider có dữ liệu**.

- Xác thực syntax trước;
- Kiểm tra mã vùng thuộc tập được chuẩn/ứng dụng hỗ trợ;
- Không tự nhận mọi chuỗi hai chữ cái hay ba chữ số là region hợp lệ;
- Phân biệt mã vùng thường (*regular region*) với macroregion, special-use code hoặc vùng không được hỗ trợ;
- Khi sản phẩm chỉ phục vụ một danh sách vùng, dùng allowlist nghiệp vụ.

`Locale.Builder` giúp kiểm tra một số giới hạn **cú pháp**, không phải trình kiểm tra đầy đủ tính hợp lệ địa lý theo CLDR hay điều kiện kinh doanh.

## 5. Hai cách tạo Locale có region override

### 5.1. Dùng `Locale.forLanguageTag`

```java
Locale base = Locale.forLanguageTag("en-US");

Locale withUkRegionalDefaults =
        Locale.forLanguageTag("en-US-u-rg-gbzzzz");
```

Đây là mảnh code trong một phương thức, cần import `java.util.Locale`.

- `base`: mặc định US.
- `withUkRegionalDefaults`: vẫn en-US, nhưng thêm type `rg-gbzzzz` để những API hỗ trợ lấy quy tắc vùng GB.

### 5.2. Dùng `Locale.Builder.setUnicodeLocaleKeyword`

```java
Locale withUkRegionalDefaults = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("rg", "gbzzzz")
        .build();
```

`Locale.Builder` và `setUnicodeLocaleKeyword` đã có từ trước, nhưng Java 10 mới bổ sung việc hỗ trợ `rg` trong các API được JEP 314 nêu.

Lợi ích của Builder:
- Cấu hình ngôn ngữ, region, extension theo từng trường;
- Dễ ghép thêm các preference khác;
- Không phải nối trực tiếp một thẻ BCP 47 bằng các thao tác chuỗi thiếu validation;
- Có thể dùng `setLocale(existingLocale)` để kế thừa locale cơ sở trước khi thêm `rg`.

### 5.3. Cách đọc metadata sau khi tạo

```java
System.out.println(withUkRegionalDefaults.toLanguageTag());
// en-US-u-rg-gbzzzz

System.out.println(withUkRegionalDefaults.getLanguage());
// en

System.out.println(withUkRegionalDefaults.getCountry());
// US

System.out.println(
        withUkRegionalDefaults.getUnicodeLocaleType("rg"));
// gbzzzz
```

Đây là mảnh code trong method có biến đã khai báo. Những kết quả này có thể kiểm tra **trực tiếp**, không phụ thuộc việc CLDR chọn một ký hiệu tiền hay pattern ngày cụ thể.

## 6. Chương trình chạy được 1: locale cơ sở US, mặc định khu vực GB

Lưu file **`RegionOverrideDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.time.temporal.WeekFields;
import java.util.Currency;
import java.util.Locale;

public class RegionOverrideDemo {
    public static void main(String[] args) {
        Locale us = Locale.forLanguageTag("en-US");
        Locale usWithUkRegionRules =
                Locale.forLanguageTag("en-US-u-rg-gbzzzz");

        Locale viaBuilder = new Locale.Builder()
                .setLanguage("en")
                .setRegion("US")
                .setUnicodeLocaleKeyword("rg", "gbzzzz")
                .build();

        System.out.println("tag="
                + usWithUkRegionRules.toLanguageTag());
        System.out.println("language="
                + usWithUkRegionRules.getLanguage());
        System.out.println("baseCountry="
                + usWithUkRegionRules.getCountry());
        System.out.println("rgType="
                + usWithUkRegionRules.getUnicodeLocaleType("rg"));
        System.out.println("builderEquivalent="
                + viaBuilder.equals(usWithUkRegionRules));

        System.out.println("usCurrency="
                + Currency.getInstance(us).getCurrencyCode());
        System.out.println("overriddenCurrency="
                + Currency.getInstance(usWithUkRegionRules)
                        .getCurrencyCode());

        System.out.println("usFirstDay="
                + WeekFields.of(us).getFirstDayOfWeek());
        System.out.println("overriddenFirstDay="
                + WeekFields.of(usWithUkRegionRules)
                        .getFirstDayOfWeek());

        LocalDate day = LocalDate.of(2024, 12, 5);
        String usShortDate =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                        .localizedBy(us).format(day);
        String overriddenShortDate =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                        .localizedBy(usWithUkRegionRules).format(day);

        System.out.println("datePatternDiffers="
                + !usShortDate.equals(overriddenShortDate));
    }
}
```

Lệnh:

```bash
javac --release 10 RegionOverrideDemo.java
java RegionOverrideDemo
```

**Stdout đã kiểm chứng trên JDK hiện đại có đầy đủ dữ liệu locale US/GB:**

```text
tag=en-US-u-rg-gbzzzz
language=en
baseCountry=US
rgType=gbzzzz
builderEquivalent=true
usCurrency=USD
overriddenCurrency=GBP
usFirstDay=SUNDAY
overriddenFirstDay=MONDAY
datePatternDiffers=true
```

Giải thích từng dòng:

1. `tag=en-US-u-rg-gbzzzz`: region override được lưu trong thẻ.
2. `language=en` và `baseCountry=US`: **Locale cơ sở không bị thay đổi**.
3. `rgType=gbzzzz`: kiểm tra trực tiếp Unicode keyword.
4. `builderEquivalent=true`: hai cách tạo Locale cho kết quả bằng nhau về cấu trúc.
5. `usCurrency=USD` nhưng `overriddenCurrency=GBP`: `Currency.getInstance(locale)` có áp dụng `rg` khi lấy mặc định tiền tệ.
6. `WeekFields` của US bắt đầu Sunday, của GB bắt đầu Monday trong bộ dữ liệu đã kiểm thử.
7. `DateTimeFormatter.localizedBy(locale)` sử dụng những dữ liệu theo vùng tương ứng nên mẫu ngày có thể khác. Ví dụ không hard-code chuỗi ngày cụ thể vì mẫu địa phương có thể được cập nhật.

**Lưu ý:** test ngày chỉ in `datePatternDiffers=true` cho dữ liệu/runtime đã thử, **không** khẳng định toàn bộ ký tự của một mẫu ngày sẽ không bao giờ thay đổi giữa các bản CLDR. Muốn kiểm tra định dạng chính xác theo hợp đồng riêng của sản phẩm, nên cố định pattern hoặc quy trình xuất dữ liệu.

## 7. Vì sao `rg` tác động `Currency`, `WeekFields` và định dạng ngày?

Một số quy tắc locale được lưu **chủ yếu theo vùng** thay vì theo ngôn ngữ. Ví dụ:
- Đơn vị tiền tệ mặc định của vùng;
- Ngày đầu tuần và số ngày tối thiểu của tuần đầu năm;
- Một số pattern ngày/giờ và biểu tượng;
- Các mặc định khác được CLDR đưa vào phạm vi `rg`.

JEP 314 mở rộng những Java API liên quan để chúng xét `rg`.

| Nhóm | API thường dùng | Điều được `rg` ảnh hưởng |
|---|---|---|
| Mặc định tiền tệ | `Currency.getInstance(Locale)` | Vùng dùng để xác định currency code |
| Định dạng tiền/số | `NumberFormat.getCurrencyInstance(Locale)`, `DecimalFormatSymbols.getInstance(Locale)` | Một số dữ liệu định dạng/ký hiệu theo vùng |
| Tuần | `WeekFields.of(Locale)` | Ngày đầu tuần, số ngày tối thiểu của tuần đầu năm |
| Calendar | `Calendar.getInstance(Locale)` rồi getter quy tắc tuần | Một số quy tắc theo vùng |
| Ngày/giờ địa phương | `DateFormat`, `DateTimeFormatter.localizedBy(Locale)` | Một số mẫu định dạng locale-specific |
| Ký hiệu số/ngày | `DecimalStyle.of(Locale)`, `DateFormatSymbols` | Các giá trị locale-sensitive được hỗ trợ |

**Giới hạn:** bảng nói về **các vùng dữ liệu được JDK hỗ trợ**, không phải “mọi hành vi của mọi formatter đều bị `rg` chi phối”. Một class hoặc provider có thể bỏ qua extension mà nó không hỗ trợ.

### 7.1. Currency mặc định khác currency của giao dịch

Nếu giao dịch thực tế là **100 USD**, việc tạo:

```java
var style = java.text.NumberFormat.getCurrencyInstance(
        Locale.forLanguageTag("en-US-u-rg-gbzzzz"));
String display = style.format(100);
```

**không** đổi 100 USD thành 100 GBP theo tỷ giá. Formatter chỉ áp dụng những quy ước định dạng và mặc định currency của locale, **không phải một dịch vụ chuyển đổi tỷ giá**.

Ở các nghiệp vụ tài chính, hãy lưu **amount và ISO currency code thực sự** riêng, định dạng theo currency thực, và chỉ quy đổi khi có tỷ giá/logic nghiệp vụ được chấp thuận. Region override không thay thế những thông tin đó.

### 7.2. Quy tắc tuần khác thời điểm thực tế

`WeekFields.of(locale).getFirstDayOfWeek()` trả thông tin về **quy tắc một tuần lịch**, không đổi ngày thực tế của một `Instant`. Nếu vùng khác dùng Monday thay cho Sunday, cách nhóm số tuần hoặc hiển thị lịch có thể thay đổi; dữ liệu timestamp ban đầu không bị sửa.

### 7.3. DateTimeFormatter và locale data

Ví dụ mảnh Java trong một phương thức:

```java
Locale us = Locale.forLanguageTag("en-US");
Locale ukRules = Locale.forLanguageTag(
        "en-US-u-rg-gbzzzz");

var date = java.time.LocalDate.of(2024, 12, 5);

String usDate =
        java.time.format.DateTimeFormatter
                .ofLocalizedDate(java.time.format.FormatStyle.SHORT)
                .localizedBy(us).format(date);

String ukRuleDate =
        java.time.format.DateTimeFormatter
                .ofLocalizedDate(java.time.format.FormatStyle.SHORT)
                .localizedBy(ukRules).format(date);
```

`rg` có thể tác động tới pattern được chọn. Tuy nhiên, không nên assert cố định toàn bộ `usDate`/`ukRuleDate` trên các JDK khác nhau nếu mẫu CLDR có thể cập nhật. Nếu output phải ổn định cho JSON/CSV/protocol, dùng một định dạng canonical do ứng dụng quy định thay vì pattern bản địa mặc định.

## 8. Thứ tự ưu tiên: `cu` và `fw` có thể ghi đè kết quả mặc định từ `rg`

Một người dùng có thể muốn:

- Ngôn ngữ/vùng cơ sở **en-US**;
- Region defaults **GB**;
- Currency **EUR** dù mặc định GB là GBP;
- Ngày đầu tuần **Sunday** dù mặc định GB là Monday.

Thẻ BCP 47:

```text
en-US-u-cu-eur-fw-sun-rg-gbzzzz
```

Ở đây:
- `rg-gbzzzz` chọn vùng GB làm nguồn mặc định cho các loại dữ liệu liên quan;
- `cu-eur` là **currency preference tường minh**, được ưu tiên hơn mặc định suy ra từ `rg` ở những API hỗ trợ `cu`;
- `fw-sun` là **first-day-of-week preference tường minh**, được ưu tiên hơn mặc định vùng GB ở những API hỗ trợ `fw`;
- `en-US` giữ vai trò locale cơ sở.

Nguyên tắc không phải “`rg` luôn thắng mọi khóa khác”, mà là: **`rg` cung cấp giá trị mặc định theo vùng; tùy chọn chuyên biệt được đặt tường minh có thể ưu tiên hơn mặc định đó**. Cần xem Javadoc cho từng API nếu kết hợp các Unicode key khác.

## 9. Chương trình chạy được 2: phối hợp `rg`, `cu`, `fw`

Lưu file **`RegionOverridePriorityDemo.java`**:

```java
import java.time.temporal.WeekFields;
import java.util.Currency;
import java.util.Locale;

public class RegionOverridePriorityDemo {
    public static void main(String[] args) {
        Locale base =
                Locale.forLanguageTag("en-US-u-rg-gbzzzz");

        Locale explicit =
                Locale.forLanguageTag(
                    "en-US-u-cu-eur-fw-sun-rg-gbzzzz");

        System.out.println("baseCurrency="
                + Currency.getInstance(base).getCurrencyCode());
        System.out.println("baseWeekStart="
                + WeekFields.of(base).getFirstDayOfWeek());

        System.out.println("explicitTag=" + explicit.toLanguageTag());
        System.out.println("explicitCountry=" + explicit.getCountry());
        System.out.println("explicitRegion="
                + explicit.getUnicodeLocaleType("rg"));

        System.out.println("explicitCurrency="
                + Currency.getInstance(explicit).getCurrencyCode());
        System.out.println("explicitWeekStart="
                + WeekFields.of(explicit).getFirstDayOfWeek());
    }
}
```

```bash
javac --release 10 RegionOverridePriorityDemo.java
java RegionOverridePriorityDemo
```

**Stdout đã kiểm thử:**

```text
baseCurrency=GBP
baseWeekStart=MONDAY
explicitTag=en-US-u-cu-eur-fw-sun-rg-gbzzzz
explicitCountry=US
explicitRegion=gbzzzz
explicitCurrency=EUR
explicitWeekStart=SUNDAY
```

Giải thích:

1. Chỉ đặt `rg-gbzzzz`: ví dụ dùng GBP và Monday của vùng GB.
2. Thêm `cu-eur`: `Currency.getInstance(explicit)` lấy EUR.
3. Thêm `fw-sun`: `WeekFields.of(explicit)` dùng Sunday.
4. Dù có ba Unicode key, `getCountry()` vẫn là `US`; các phần tùy chỉnh không thay vùng cơ sở.
5. `toLanguageTag()` chuẩn hóa biểu diễn các key trong extension; có thể dùng thẻ này cho cấu hình i18n mà hai phía thống nhất cùng cú pháp.

**Không lạm dụng:** nếu currency của một đơn hàng là JPY, đừng đổi thành EUR chỉ vì locale có `cu-eur`. Currency của domain vẫn phải do dữ liệu giao dịch cung cấp.

## 10. Tạo region override động từ cấu hình

Nếu cấu hình nhận `"GB"` hoặc `"US"`, có thể viết helper để gắn đúng hậu tố `zzzz` và tránh nối chuỗi không được kiểm soát.

```java
static Locale withRegionOverride(Locale base, String region) {
    if (region == null
            || !java.util.regex.Pattern.matches(
                "(?:[A-Za-z]{2}|[0-9]{3})", region)) {
        throw new IllegalArgumentException("region syntax");
    }

    String type = region.toLowerCase(Locale.ROOT) + "zzzz";
    return new Locale.Builder()
            .setLocale(base)
            .setUnicodeLocaleKeyword("rg", type)
            .build();
}
```

Đây là method minh họa trong class, cần import `Locale`. `Locale.ROOT` giúp xử lý ASCII region code độc lập ngôn ngữ và locale mặc định.

**Giới hạn validation:** regex trên chỉ xác minh độ dài/hình thức một mã region; nó **không** xác nhận mã đã được đăng ký trong BCP 47/CLDR, vùng có dữ liệu hoặc ứng dụng cho phép cấu hình vùng đó. Trong production cần bổ sung validation semantic và allowlist phù hợp.

`Locale.Builder` có thể báo `IllformedLocaleException` khi cú pháp không hợp lệ; đồng thời có những chuỗi cú pháp hợp lệ nhưng không mang nghĩa region được hỗ trợ. Do đó **việc build thành công không đủ làm chứng cứ `rg` đã được mọi service áp dụng**.

## 11. Chương trình chạy được 3: build `rg` và xác thực

Lưu file **`RegionOverrideValidationDemo.java`**:

```java
import java.time.temporal.WeekFields;
import java.util.Currency;
import java.util.Locale;
import java.util.regex.Pattern;

public class RegionOverrideValidationDemo {

    static Locale withRegionOverride(Locale base, String region) {
        if (region == null
                || !Pattern.matches(
                    "(?:[A-Za-z]{2}|[0-9]{3})", region)) {
            throw new IllegalArgumentException("region syntax");
        }

        String type = region.toLowerCase(Locale.ROOT) + "zzzz";
        return new Locale.Builder()
                .setLocale(base)
                .setUnicodeLocaleKeyword("rg", type)
                .build();
    }

    public static void main(String[] args) {
        Locale locale = withRegionOverride(Locale.US, "GB");

        System.out.println("overrideTag=" + locale.toLanguageTag());
        System.out.println("baseStillUS="
                + locale.getCountry().equals("US"));
        System.out.println("overrideIsGB="
                + locale.getUnicodeLocaleType("rg").equals("gbzzzz"));
        System.out.println("currencyIsGBP="
                + Currency.getInstance(locale).getCurrencyCode()
                        .equals("GBP"));
        System.out.println("firstDayIsMonday="
                + WeekFields.of(locale).getFirstDayOfWeek()
                        .toString().equals("MONDAY"));

        try {
            withRegionOverride(Locale.US, "G");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidSyntaxRejected=true");
        }
    }
}
```

```bash
javac --release 10 RegionOverrideValidationDemo.java
java RegionOverrideValidationDemo
```

**Stdout đã kiểm thử:**

```text
overrideTag=en-US-u-rg-gbzzzz
baseStillUS=true
overrideIsGB=true
currencyIsGBP=true
firstDayIsMonday=true
invalidSyntaxRejected=true
```

Đây là ví dụ về ba kiểu kiểm tra:

1. **Cấu trúc Locale:** quốc gia cơ sở US không đổi, type của `rg` được lưu là `gbzzzz`.
2. **Hành vi locale-sensitive:** tiền tệ và ngày đầu tuần theo vùng GB trong runtime đã thử.
3. **Cấu hình:** một mã vùng có syntax sai như `"G"` bị từ chối có chủ đích ngay tại ranh giới input.

Không nên suy từ chương trình rằng regex là trình xác thực region code đầy đủ hoặc mọi locale data provider đều có sẵn mọi vùng.

## 12. `rg` không thay timezone, vị trí người dùng hay quốc tịch

Một nhầm lẫn thường gặp là “region override GB sẽ tự đổi đồng hồ của JVM sang giờ London”. Điều đó **không đúng**.

`rg` không gọi `TimeZone.setDefault(...)` hoặc thay `ZoneId.systemDefault()`. Nó cũng không chuyển đổi thời điểm đã lưu.

```java
Locale preferredFormats =
        Locale.forLanguageTag("en-US-u-rg-gbzzzz");
java.time.ZoneId londonZone =
        java.time.ZoneId.of("Europe/London");
```

Đây là mảnh code trong method. Hai biến giải quyết hai việc khác nhau:

- `preferredFormats`: yêu cầu lấy một số mặc định định dạng theo vùng GB, giữ locale cơ sở en-US.
- `londonZone`: xác định quy tắc múi giờ, có xử lý daylight-saving time (DST) khi được sử dụng trong phép tính/hiển thị thời gian.

Nếu ứng dụng muốn hiển thị `Instant` theo giờ London, phải dùng `ZoneId`/`ZonedDateTime` hoặc API thời gian có hỗ trợ rõ ràng. Java 10 cũng hỗ trợ khóa Unicode `tz` trong **một số API** qua JEP 314, nhưng `tz` **không phải `rg`**.

Không dùng `rg` để:
- Xác thực người dùng sống tại vùng nào;
- Kiểm tra quyền giao dịch dựa trên khu vực pháp lý;
- Quy đổi tỷ giá tiền tệ;
- Xác định GPS, IP, timezone hay điều kiện thuế;
- Thay `ResourceBundle` locale cơ sở trong mọi tình huống;
- Thay đổi toàn JVM bằng cách gọi `Locale.setDefault(...)`.

**Thiết kế tốt:** truyền một `Locale` tường minh vào đúng formatter/service cần dùng. Đừng thay đổi default locale toàn tiến trình chỉ để một màn hình dùng quy tắc vùng khác, vì điều đó dễ ảnh hưởng luồng khác.

## 13. CLDR, locale data provider và độ ổn định

Region-specific defaults đến từ dữ liệu locale, thường thông qua CLDR. Java cung cấp những cơ chế locale data provider; khi đóng gói runtime tùy chỉnh bằng `jlink`, dữ liệu vùng có thể còn bị lược bỏ theo module và cấu hình.

Những điều có thể thay đổi theo môi trường:

- Phiên bản JDK/CLDR;
- Pattern ngày ngắn hay dài;
- Biểu tượng currency, ký tự khoảng trắng, dấu phân cách số;
- Dữ liệu mặc định tuần/các vùng cụ thể;
- Các vùng được provider thực tế hỗ trợ;
- Sự tương tác giữa nhiều Unicode extension keywords.

**JEP 314 xác định những API mở rộng hỗ trợ**, nhưng không bắt các phiên bản JDK mãi sử dụng cùng một tập dữ liệu định dạng cho mọi quốc gia.

### 13.1. Kiểm thử cái gì là ổn định?

Ưu tiên kiểm tra:

```java
Locale loc = Locale.forLanguageTag("en-US-u-rg-gbzzzz");

boolean keepsBaseCountry = "US".equals(loc.getCountry());
boolean storesRegionOverride =
        "gbzzzz".equals(loc.getUnicodeLocaleType("rg"));
boolean setsCurrency =
        "GBP".equals(java.util.Currency.getInstance(loc)
                .getCurrencyCode());
```

Đây là mảnh code trong method có import `Locale`. Hai điều kiện đầu nói về **cấu trúc Locale**, không phụ thuộc phiên bản CLDR. Điều kiện cuối kiểm tra **dữ liệu locale US/GB do runtime hỗ trợ**, cần chạy trong môi trường có dữ liệu tương ứng.

Khi cần so sánh chuỗi tiền hoặc ngày chính xác từng ký tự, nên cố định JDK/provider hoặc formatter pattern theo hợp đồng sản phẩm. Không đặt test cứng với output của mọi `NumberFormat.getCurrencyInstance(...)` trên mọi JDK nếu biểu tượng và dấu cách có thể cập nhật.

### 13.2. Định dạng trao đổi dữ liệu máy khác định dạng giao diện

`rg` hữu ích cho **giao diện người dùng**, nhưng một API/CSV/JSON cần dữ liệu ổn định thường nên sử dụng:

- ISO 8601 cho ngày/giờ theo giao thức;
- `Instant` và thông tin zone phù hợp nếu cần;
- ISO 4217 currency code + amount riêng;
- Các con số có định dạng canonical;
- Các tiêu chuẩn riêng của hệ thống nhận/gửi dữ liệu.

Không lấy một currency/date string tùy thuộc Locale để làm khóa dữ liệu, làm chữ ký request hoặc làm biểu diễn kế toán duy nhất.

## 14. Lỗi phổ biến và cách sửa

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “`rg` làm `getCountry()` từ US thành GB.” | `getCountry()` luôn trả region **cơ sở**. |
| “`en-US-u-rg-gbzzzz` giống hệt `en-GB`.” | Chúng khác thông tin cơ sở và các service không hỗ trợ `rg` có thể xử lý khác. |
| “`rg-gb` là cú pháp chuẩn để ghi đè toàn GB.” | Dùng `rg-gbzzzz` cho vùng ở cấp toàn vùng. |
| “Builder nhận mã hai chữ cái là mã vùng chắc chắn hợp lệ.” | Kiểm tra cú pháp không thay kiểm tra giá trị được công nhận. |
| “`rg` có thể đổi ngôn ngữ en thành ngôn ngữ khác.” | Không: nó không đổi language subtag. |
| “Tất cả các API dùng `Locale` đều tự hỗ trợ `rg`.” | Chỉ các service có triển khai hỗ trợ. |
| “`rg` bao trùm cả preference `cu-eur` và `fw-sun`.” | Tùy chọn chuyên biệt tường minh có thể ưu tiên ở API hỗ trợ. |
| “`rg-gbzzzz` tự đặt `ZoneId.systemDefault()` sang London.” | Không. Timezone xử lý riêng. |
| “Currency formatter có thể đổi USD thật thành GBP theo tỷ giá.” | Không. Đó là quy ước trình bày, không phải đổi tiền. |
| “`Locale.Builder` là class mới của Java 10.” | Builder đã có trước; phần mới là hỗ trợ thêm extension trong các service liên quan. |
| “Định dạng ngày/tiền từ CLDR không bao giờ đổi.” | Dữ liệu locale có thể thay đổi giữa các JDK/provider. |
| “Locale có region GB là xác nhận người dùng đang ở GB.” | Locale là preference, không phải dữ liệu vị trí đáng tin cậy. |

## 15. Hướng dẫn review code

- [ ] Phân biệt region cơ sở và `rg` chưa?
- [ ] Giá trị của `rg` đúng cú pháp `<region>zzzz` chưa?
- [ ] Mã vùng có được kiểm tra ngữ nghĩa/allowlist, không chỉ regex?
- [ ] Có giữ nguyên ngôn ngữ và region gốc khi chỉ muốn đổi region-specific defaults?
- [ ] Class/API đang gọi có nằm trong nhóm hỗ trợ `rg` không?
- [ ] Test có dùng `getUnicodeLocaleType("rg")` để xác minh extension?
- [ ] Có xử lý preference `cu`, `fw` tường minh với đúng ưu tiên không?
- [ ] Có dùng `Locale` tường minh thay vì đổi default cho toàn JVM không?
- [ ] Có nhầm `rg` với timezone hoặc currency thực của giao dịch không?
- [ ] Chuỗi format có bị hard-code theo một phiên bản CLDR cụ thể mà không kiểm soát runtime không?
- [ ] Nếu giao tiếp máy, có sử dụng định dạng canonical thay vì dạng hiển thị locale-dependent không?
- [ ] Runtime có dữ liệu locale cần thiết (khi dùng image JDK tùy chỉnh) không?

Nhận xét review phù hợp:

> “Yêu cầu giữ en-US làm locale cơ sở nhưng dùng quy tắc ngày/tiền của GB. `Locale.forLanguageTag("en-GB")` sẽ đổi region cơ sở. Nên dùng `en-US-u-rg-gbzzzz`; kiểm tra `getCountry()` vẫn là US và `Currency`/`WeekFields` nhận dữ liệu vùng GB.”

Nhận xét sai:

> “Khi đặt `rg-gbzzzz` hãy tự động đổi mọi số tiền USD của khách thành GBP.”

Region override không quyết định tỷ giá hay loại tiền giao dịch.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `rg` có nghĩa gì?

**Đáp án:** Region override trong Unicode locale extension; một số default values theo vùng được lấy từ region khác.

**Câu 2.** `Locale.forLanguageTag("en-US-u-rg-gbzzzz").getCountry()` cho gì?

**Đáp án:** `US`.

**Câu 3.** `getUnicodeLocaleType("rg")` trong ví dụ là gì?

**Đáp án:** `gbzzzz`.

**Câu 4.** Vì sao `rg` có hậu tố `zzzz`?

**Đáp án:** Đây là dạng region identifier thông dụng theo Unicode dùng để chỉ **toàn vùng** trong region override.

**Câu 5.** Có thể dùng `rg` để đổi ngôn ngữ `en` thành `fr` không?

**Đáp án:** Không. Ngôn ngữ nằm trong phần locale cơ sở.

**Câu 6.** `Currency.getInstance(...)` có thể trả currency nào với `en-US-u-rg-gbzzzz`?

**Đáp án:** GBP theo mặc định vùng GB trong runtime có locale data phù hợp.

**Câu 7.** Ngày đầu tuần có thể thay như thế nào?

**Đáp án:** Từ Sunday (US) sang Monday (GB) trong `WeekFields.of(Locale)` với dữ liệu vùng tương ứng.

**Câu 8.** Nếu thêm `cu-eur` vào tag có `rg-gbzzzz`, currency của `Currency.getInstance` là gì?

**Đáp án:** EUR theo preference currency tường minh trong API hỗ trợ.

**Câu 9.** Nếu thêm `fw-sun`, ngày đầu tuần có nhất định là Monday không?

**Đáp án:** Không. `fw-sun` có thể yêu cầu Sunday trong `WeekFields`.

**Câu 10.** `rg` có thay `ZoneId.systemDefault()` không?

**Đáp án:** Không; timezone là thiết lập khác.

**Câu 11.** Cú pháp tốt có đảm bảo locale provider có dữ liệu vùng đó không?

**Đáp án:** Không. Cần validation và xem runtime locale data.

**Câu 12.** `Locale.Builder.setUnicodeLocaleKeyword(...)` mới xuất hiện trong Java 10?

**Đáp án:** Không. Java 10 mở rộng hỗ trợ các key như `rg` trong những API i18n có liên quan.

**Câu 13.** Có nên so sánh toàn bộ kết quả formatter currency/ngày theo byte trên mọi JDK?

**Đáp án:** Không, trừ khi hệ thống cố định dữ liệu CLDR/provider. Các pattern và ký hiệu có thể đổi.

**Câu 14.** `rg` có xác thực người dùng sống tại GB không?

**Đáp án:** Không. Đây là một locale preference.

**Câu 15.** Muốn test đúng tính năng, nên dùng loại kiểm tra nào?

**Đáp án:** Kiểm tra cấu trúc Locale (`getCountry`, `getUnicodeLocaleType`), sau đó kiểm tra dịch vụ hỗ trợ (`Currency.getCurrencyCode`, `WeekFields`) trong môi trường có locale data thích hợp.

## 17. Tài liệu chính thức

- [OpenJDK JEP 314 — Additional Unicode Language-Tag Extensions](https://openjdk.org/jeps/314): tính năng đã phát hành trong **Java 10**, gồm `cu`, `fw`, **`rg`**, `tz` và các API liên quan.
- [Oracle Java SE 10 — Internationalization Enhancements in JDK 10](https://docs.oracle.com/javase/10/intl/internationalization-enhancements-jdk-10.htm): tổng quan về các Unicode language-tag extensions mới được hỗ trợ.
- [Oracle Java SE 21 — `Locale`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): cú pháp BCP 47, getCountry, Unicode extension, language tags.
- [Oracle Java SE 21 — `Locale.Builder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.Builder.html): `setUnicodeLocaleKeyword(...)`, `setLocale(...)`, validation cú pháp.
- [Oracle Java SE 21 — `Currency`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Currency.html): currency mặc định theo locale.
- [Oracle Java SE 21 — `WeekFields`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/WeekFields.html): ngày đầu tuần và tuần đầu năm.
- [Oracle Java SE 21 — `DateTimeFormatter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): `localizedBy(Locale)` và định dạng ngày/giờ.
- [Unicode CLDR/UTS #35 — Region Override](https://www.unicode.org/reports/tr35/): `rg`, giá trị vùng và phạm vi của các dữ liệu theo region.
- [Unicode CLDR BCP47 variant.xml](https://github.com/unicode-org/cldr/blob/main/common/bcp47/variant.xml): khai báo key `rg` trong CLDR.
- [RFC 5646 — BCP 47 language tags](https://www.rfc-editor.org/rfc/rfc5646): cấu trúc thẻ ngôn ngữ.

**Ghi nhớ:** `rg` được hỗ trợ từ Java 10 trong các dịch vụ i18n tương ứng. Ví dụ `en-US-u-rg-gbzzzz` **giữ nguyên locale cơ sở en-US** nhưng yêu cầu những **mặc định vùng được hỗ trợ** theo GB. `getCountry()` vẫn là `US`; `getUnicodeLocaleType("rg")` là `gbzzzz`. Khi có `cu` hoặc `fw` tường minh, chúng có thể ưu tiên hơn mặc định từ `rg`. Không dùng `rg` để thay timezone, đổi tỷ giá, xác thực vùng địa lý hoặc tạo dữ liệu trao đổi máy phụ thuộc CLDR.