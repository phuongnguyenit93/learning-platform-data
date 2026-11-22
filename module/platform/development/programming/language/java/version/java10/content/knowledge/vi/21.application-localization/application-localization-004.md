# Vùng ghi đè `rg` và các quy ước theo vùng trong ứng dụng Java

## 1. Vì sao cần “region override”?

Một ứng dụng có thể cần **ngôn ngữ hiển thị** khác với **những quy ước thường dùng ở khu vực**. Ví dụ, người dùng muốn giao diện bằng tiếng Anh kiểu Hoa Kỳ, nhưng lại muốn một số mặc định theo vùng áp dụng như ở Vương quốc Anh: tiền tệ mặc định bảng Anh hoặc quy ước tuần bắt đầu vào thứ Hai.

Nếu chỉ dùng `Locale.forLanguageTag("en-US")`, dữ liệu địa phương hóa thường được lấy theo tiếng Anh, vùng Hoa Kỳ. Nếu đổi hoàn toàn sang `Locale.forLanguageTag("en-GB")`, bạn cũng đổi thành phần vùng cơ sở của Locale. Nhưng có một lựa chọn thứ ba: **giữ Locale gốc và thêm vùng ghi đè**.

~~~java
Locale regional = Locale.forLanguageTag("en-US-u-rg-gbzzzz");
~~~

Locale này vẫn có:

- Ngôn ngữ cơ sở: `en` — tiếng Anh.
- Region cơ sở: `US` — Hoa Kỳ.
- Unicode locale extension: `rg=gbzzzz` — yêu cầu **dùng các mặc định thuộc phạm vi vùng GB** ở những dịch vụ hỗ trợ `rg`.

`rg` là viết tắt của **Region Override**, một key thuộc **Unicode locale extension** trong thẻ ngôn ngữ BCP 47. Java **10** bổ sung hỗ trợ cho key `rg` trong những API địa phương hóa liên quan; hỗ trợ này vẫn tồn tại trong Java hiện đại.

**Điểm cần nhớ nhất:** `rg` **không đổi `Locale.getCountry()` từ `US` thành `GB`**. Nó chỉ điều chỉnh **cách tra cứu một số giá trị mặc định theo vùng**. Đây không phải cách khai báo người dùng đang ở nước nào hay cách xác định quốc tịch, thuế, pháp luật, địa chỉ giao hàng, múi giờ thực tế.

### Mục tiêu học tập

Sau bài này bạn có thể:

1. Đọc và tạo đúng tag `en-US-u-rg-gbzzzz` hoặc xây bằng `Locale.Builder`.
2. Giải thích sự khác biệt giữa **region cơ sở** và **region override**.
3. Biết API nào hỗ trợ `rg`: `Currency`, `NumberFormat`, `DecimalFormatSymbols`, `WeekFields`, các định dạng ngày/giờ tương ứng.
4. Phân biệt quy tắc **mặc định suy ra từ `rg`** với lựa chọn **tường minh** như `cu` cho tiền tệ hay `fw` cho ngày đầu tuần.
5. Hiểu vì sao không phải mọi chi tiết định dạng đều đổi: ngôn ngữ, cách hiển thị ký hiệu, dấu phân cách có thể còn phụ thuộc locale cơ sở và nguồn dữ liệu.
6. Dùng `rg` mà không sửa `Locale` mặc định toàn JVM, không gán nhầm giá trị nghiệp vụ.
7. Chạy ví dụ Java 17+ và viết kiểm thử không phụ thuộc hoàn toàn vào mẫu định dạng CLDR của một bản JDK.

## 2. Bối cảnh phiên bản: Java 10 bổ sung những gì?

`java.util.Locale` đã hỗ trợ language tag theo **IETF BCP 47** từ trước Java 10. Điều mới của **Java 10** không phải là tạo ra BCP 47 hay phương thức `Locale.forLanguageTag`, mà là mở rộng khả năng **các dịch vụ JDK hiểu và áp dụng các Unicode locale key** được quy định trong Unicode LDML/CLDR.

Những key được tài liệu Internationalization của JDK 10 nêu rõ:

| Key | Tên | Vai trò |
| --- | --- | --- |
| `cu` | Currency type | Chọn loại tiền tệ rõ ràng, ví dụ `jpy`. |
| `fw` | First day of week | Chỉ định ngày đầu tuần, ví dụ `sun` hoặc `mon`. |
| **`rg`** | **Region override** | Dùng vùng thay thế cho **một số giá trị mặc định theo vùng**. |
| `tz` | Time zone | Chỉ định múi giờ bằng Unicode locale extension được API hỗ trợ. |

Những key khác như `ca` (calendar) và `nu` (numbering system) đã được hỗ trợ trước đó trong các API tương ứng. Java hiện đại vẫn dùng `rg`; không cần tìm một API “mới thay thế `rg`” để làm chức năng này.

**Không nhầm ngày ra đời của API:**

- `Locale.forLanguageTag` và `Locale.Builder` có trước Java 10.
- `Currency.getInstance(Locale)` có trước Java 10, nhưng JDK 10 mở rộng cách xử lý `rg`/`cu`.
- `WeekFields.of(Locale)` có trước Java 10, nhưng các extension như `rg`/`fw` có ý nghĩa trong Java 10+.
- `DateTimeFormatter.localizedBy(Locale)` là phương thức **từ Java 10**, áp dụng localized values từ các extension của Locale.
- `Locale.of(...)` xuất hiện ở các phiên bản mới hơn Java 17; ví dụ trong bài dùng `forLanguageTag`/`Builder` để chạy trên **Java 17+**.

## 3. Giải mã tag `en-US-u-rg-gbzzzz`

~~~text
en-US-u-rg-gbzzzz
│  │  │ │  └────── gbzzzz: vùng GB với hậu tố zzzz
│  │  │ └───────── rg: Unicode key "region override"
│  │  └─────────── u: Unicode locale extension
│  └────────────── US: vùng cơ sở
└───────────────── en: ngôn ngữ cơ sở
~~~

Ý nghĩa:

- `en-US` định danh phần Locale cơ sở là tiếng Anh, vùng Hoa Kỳ.
- `-u-` mở đầu **Unicode extension** trong BCP 47.
- `-rg-` là key **region override**.
- `gbzzzz` chỉ định **GB** làm vùng dùng để lấy một số region defaults; `zzzz` là hậu tố tiêu chuẩn dùng cho **toàn bộ vùng**.

Cú pháp phổ biến cho toàn bộ vùng:

~~~text
language[-Script][-REGION]-u-rg-<region-code>zzzz
~~~

Trong đó `<region-code>` thường là mã vùng **hai chữ cái** hợp lệ, ví dụ `us`, `gb`, `jp`, `vn`. UTS #35 còn có những quy tắc khác cho các mã vùng phù hợp và subdivision; ứng dụng không nên tự suy đoán rằng mọi chuỗi trông giống mã vùng đều được tất cả provider hỗ trợ.

Một số ví dụ:

| Language tag | Cách đọc |
| --- | --- |
| `en-US` | English, vùng cơ sở US, không có `rg`. |
| `en-GB` | English, vùng cơ sở GB. |
| `en-US-u-rg-gbzzzz` | English/US cơ sở; dùng một số mặc định theo vùng GB. |
| `en-GB-u-rg-uszzzz` | English/GB cơ sở; dùng một số mặc định theo vùng US. |
| `fr-FR-u-rg-uszzzz` | French/FR cơ sở; dùng một số region defaults của US. |
| `vi-VN-u-rg-jpzzzz` | Vietnamese/VN cơ sở; yêu cầu một số mặc định theo vùng JP. |

**Chữ hoa/chữ thường:** Thẻ BCP 47 không phân biệt case ở những thành phần này. Java chuẩn hóa dạng language tag theo các quy tắc của `Locale`. Khi đọc bằng `getUnicodeLocaleType("rg")`, ví dụ thường nhận chuỗi `"gbzzzz"`.

**Không viết `en-US-rg-GB`:** thiếu `u` và hậu tố vùng đúng nghĩa. `rg` là Unicode **extension key**, không phải một region subtag thứ hai đặt tùy ý trong BCP 47.

## 4. `rg` không thay `getCountry()` — khác biệt quan trọng nhất

~~~java
import java.util.Locale;

// Trong một phương thức:
Locale regional = Locale.forLanguageTag("en-US-u-rg-gbzzzz");

System.out.println(regional.getLanguage());             // en
System.out.println(regional.getCountry());              // US
System.out.println(regional.getUnicodeLocaleType("rg"));// gbzzzz
~~~

Ba lời gọi hỏi **ba thông tin khác nhau**:

1. `getLanguage()`: ngôn ngữ trong Locale cơ sở.
2. `getCountry()`: mã vùng **cơ sở**, không tự đổi khi đặt `rg`.
3. `getUnicodeLocaleType("rg")`: giá trị yêu cầu ghi đè vùng, nếu có.

Nhờ vậy, một ứng dụng có thể giữ metadata định danh locale **en-US** và chỉ đề xuất các mặc định theo vùng **GB** cho những hoạt động hỗ trợ extension.

**Không được suy luận:**

~~~java
// SAI VỀ Ý NGHĨA:
String actualResidence = regional.getUnicodeLocaleType("rg");
~~~

`rg` là **tùy chọn trình bày/địa phương hóa** chứ không phải bằng chứng vị trí địa lý thực, quốc tịch, quyền cư trú, IP, quốc gia thanh toán hoặc địa chỉ nhận hàng.

Nếu cần country cho logic thuế, pháp lý, KYC hoặc shipping, hãy dùng **trường dữ liệu nghiệp vụ được xác minh**. Không dùng locale preference để quyết định các thuộc tính đó.

## 5. Hai cách tạo Locale có `rg`

### 5.1. Cách 1 — `Locale.forLanguageTag`

~~~java
Locale regional = Locale.forLanguageTag("en-US-u-rg-gbzzzz");
~~~

Phù hợp khi nhận thẻ BCP 47 đã được chuẩn hóa hoặc lưu một cấu hình dạng text. Giải pháp này ngắn, dễ truyền qua API và có thể kết hợp nhiều Unicode extension.

Lưu ý `Locale.forLanguageTag` **không phải công cụ xác thực đầy đủ các preference nghiệp vụ**. Một language tag có thể đúng cú pháp nhưng chứa vùng/giá trị không được một provider hỗ trợ, hoặc có phần sai bị parser xử lý theo quy tắc của mình. Với đầu vào bên ngoài, cần kiểm tra các key/value được phép và khả năng hỗ trợ thực tế.

### 5.2. Cách 2 — `Locale.Builder`

~~~java
Locale regional = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("rg", "gbzzzz")
        .build();
~~~

Cách này thích hợp khi các thành phần ngôn ngữ, vùng cơ sở và vùng preference đến từ các trường dữ liệu khác nhau.

Cũng có thể bắt đầu từ Locale có sẵn:

~~~java
Locale base = Locale.forLanguageTag("en-US");

Locale regional = new Locale.Builder()
        .setLocale(base)
        .setUnicodeLocaleKeyword("rg", "gbzzzz")
        .build();
~~~

`Builder` giúp phát hiện **một số lỗi cú pháp** sớm bằng `IllformedLocaleException` khi input không hợp lệ về cấu trúc. Tuy nhiên, đúng cú pháp **không đồng nghĩa** vùng ghi đè được mọi dịch vụ địa phương hóa chấp nhận hoặc có đầy đủ dữ liệu CLDR.

### 5.3. Kiểm tra kết quả sau khi tạo

~~~java
Locale fromTag = Locale.forLanguageTag("en-US-u-rg-gbzzzz");
Locale fromBuilder = new Locale.Builder()
        .setLanguage("en")
        .setRegion("US")
        .setUnicodeLocaleKeyword("rg", "gbzzzz")
        .build();

System.out.println(fromTag.equals(fromBuilder)); // true
~~~

`Locale` là đối tượng giá trị bất biến: Builder tạo ra một Locale mới, **không sửa Locale cơ sở** và cũng không tự thay `Locale.getDefault()`.

Có thể đọc `toLanguageTag()` để truyền thẻ chuẩn hóa, nhưng đừng suy luận từ việc tag chứa `rg` rằng mọi API đã áp dụng extension. Muốn biết tính năng có hiệu lực, phải kiểm tra **hợp đồng của từng API tiêu thụ Locale**.

## 6. Hỗ trợ thực tế: những API nào phản ứng với `rg`?

Trong Java 10+ và các JDK hiện đại, `rg` được một số dịch vụ dùng để lựa chọn những mặc định theo vùng:

| API | Điều `rg` có thể ảnh hưởng | Điều không được mặc nhiên kết luận |
| --- | --- | --- |
| `Currency.getInstance(locale)` | Đồng tiền mặc định cho vùng ghi đè. | Không chứng minh giao dịch phải thanh toán bằng đồng tiền đó. |
| `NumberFormat.getCurrencyInstance(locale)` | Đồng tiền mặc định/các quy tắc định dạng liên quan theo provider. | Không quyết định giá trị tiền hoặc thuế; không bảo đảm cùng chuỗi trên mọi JDK. |
| `NumberFormat.getInstance(locale)` | Dữ liệu locale theo vùng mà provider hỗ trợ. | Không thay toàn bộ ký hiệu/syntax của ngôn ngữ cơ sở. |
| `DecimalFormatSymbols.getInstance(locale)` | Những giá trị symbols thuộc phạm vi region override. | Không mặc nhiên đổi mọi dấu phân cách thập phân theo country ghi đè. |
| `WeekFields.of(locale)` | Ngày đầu tuần và các quy ước tuần áp dụng theo vùng. | Không thay múi giờ hoặc LocalDate gốc. |
| `Calendar.getInstance(locale)` | Quy ước tuần trong một API vẫn hỗ trợ. | Không nên dùng Calendar làm API ngày giờ ưu tiên cho code mới. |
| `DateTimeFormatter.localizedBy(locale)` | Localized settings gồm region/calendar/decimal style/timezone **trong phạm vi các extension tương ứng**. | Không tự thay đổi `ZoneId` của ứng dụng chỉ vì có `rg`. |
| `java.text.DateFormat` | Một số mặc định calendar/date formatting theo vùng. | Không cam kết mọi pattern locale giống nhau ở các bản dữ liệu CLDR. |
| `DecimalStyle.of(locale)` | Các ký hiệu số được dịch vụ hỗ trợ lấy từ locale. | Không thay đổi đơn vị của số hoặc chuyển đổi đơn vị đo. |

**Phân biệt tiêu chuẩn và triển khai:** JavaDoc nhiều lớp nêu hỗ trợ `rg`, nhưng không hứa mọi **key/type**, provider, cặp ngôn ngữ–vùng hay mọi giá trị locale data được xử lý theo một cách giống nhau. Ứng dụng có thể chạy trên JDK/CLDR/provider khác với môi trường phát triển; hãy kiểm thử các trường hợp quan trọng.

### 6.1. Không có một “công tắc đổi vùng cho toàn bộ Java”

`rg` chỉ có hiệu lực khi **API cụ thể hiểu extension**. Nó không làm các API thuần túy như `String.length()`, `Math.max()`, `Path.of()` hay API mạng tự thay hành vi theo vùng.

Ngay cả trong nhóm địa phương hóa, một phần ký hiệu đến từ **ngôn ngữ** còn các mặc định khác đến từ **region**. Vì vậy một locale `fr-FR-u-rg-uszzzz` có thể vẫn hiển thị dấu thập phân theo tiếng Pháp trong một JDK/provider cụ thể; không được coi điều đó là “rg không hoạt động”.

## 7. Ví dụ 1 — tiền tệ mặc định từ vùng ghi đè

~~~java
import java.util.Currency;
import java.util.Locale;

Locale base = Locale.forLanguageTag("en-US");
Locale regional = Locale.forLanguageTag("en-US-u-rg-gbzzzz");

System.out.println(Currency.getInstance(base).getCurrencyCode());     // USD
System.out.println(Currency.getInstance(regional).getCurrencyCode());// GBP
~~~

Trong dữ liệu JDK hiện hành:

- `en-US` mặc định gắn với US dollar (**USD**).
- `en-US-u-rg-gbzzzz` yêu cầu region defaults của GB, nên `Currency.getInstance` trả đồng **GBP**.
- `regional.getCountry()` vẫn trả **US**.

Ví dụ trực tiếp chứng minh **region override là preference lookup**, không phải thao tác đổi quốc gia cơ sở.

### 7.1. Định dạng giá trị tiền

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;

var currencyFormat = NumberFormat.getCurrencyInstance(regional);
String display = currencyFormat.format(new BigDecimal("1234.50"));
~~~

Trên JDK 24 thử nghiệm với dữ liệu CLDR mặc định, `display` là `£1,234.50`. Tuy nhiên, **chữ tiền tệ, vị trí ký hiệu, khoảng trắng, pattern số và quy tắc hiển thị** có thể thay đổi theo locale data/provider/JDK. Không lưu chuỗi `display` làm giá trị tiền gốc, không coi nó là định dạng trao đổi dữ liệu bất biến.

### 7.2. Giao dịch phải dùng Currency tường minh

Nếu người dùng **trả tiền thật bằng USD**, không được chỉ vì preference `rg=GB` mà tự chuyển giao dịch sang GBP. Cần giữ **currency code** của chính giao dịch trong domain model, ví dụ `Currency.getInstance("USD")`.

~~~java
var format = NumberFormat.getCurrencyInstance(regional);
format.setCurrency(Currency.getInstance("USD"));

String shownUsd = format.format(new BigDecimal("1234.50"));
~~~

`setCurrency` điều chỉnh đối tượng formatter để dùng currency được chọn; nếu yêu cầu chính xác số chữ số thập phân hoặc quy tắc nghiệp vụ, cần kiểm tra thêm fraction digits và cấu hình tương ứng, không suy luận chỉ từ `Locale`.

**Quy tắc:** `rg` hữu ích để chọn **mặc định hiển thị**; currency của giao dịch, phép đổi tỷ giá và quy định tài chính là dữ liệu/chính sách **riêng**.

## 8. Ví dụ 2 — ngày đầu tuần và quy ước tuần

Quy ước lịch khác nhau giữa các vùng. `WeekFields.of(Locale)` là API hiện đại trong `java.time.temporal` dùng để tra ngày đầu tuần và số ngày tối thiểu trong tuần đầu tiên của năm.

~~~java
import java.time.temporal.WeekFields;
import java.util.Locale;

Locale us = Locale.forLanguageTag("en-US");
Locale ukRules = Locale.forLanguageTag("en-US-u-rg-gbzzzz");

System.out.println(WeekFields.of(us).getFirstDayOfWeek());      // SUNDAY
System.out.println(WeekFields.of(ukRules).getFirstDayOfWeek()); // MONDAY
~~~

Trên JDK 24 thử nghiệm:

- US có tuần bắt đầu vào **Sunday**, minimal days of first week là **1**.
- GB có tuần bắt đầu vào **Monday**, minimal days of first week là **4**.
- `rg=gbzzzz` đưa quy ước tuần theo GB vào một locale cơ sở `en-US`.

`WeekFields.of(ukRules).getMinimalDaysInFirstWeek()` trong ví dụ trả **4**. Đây là quy tắc định nghĩa tuần; nó có thể ảnh hưởng **week-of-year** và **week-based-year** gần ranh giới năm, nên rất quan trọng trong báo cáo tuần.

### 8.1. `fw` ghi đè ngày đầu tuần do `rg` suy ra

~~~java
Locale chosenWeek = Locale.forLanguageTag(
        "en-US-u-fw-sun-rg-gbzzzz"
);

System.out.println(
        WeekFields.of(chosenWeek).getFirstDayOfWeek()
); // SUNDAY
~~~

Vì `fw=sun` là chỉ định ngày đầu tuần **tường minh**, nó được ưu tiên hơn mặc định ngày đầu tuần suy ra từ `rg=GB`.

Điều này **không có nghĩa** các quy tắc tuần còn lại như số ngày tối thiểu trong tuần đầu năm đều đổi về US. `fw` tập trung vào **first day of week**, còn các thông số khác vẫn được tra theo phạm vi locale/region tương ứng.

### 8.2. Tính tuần theo dữ liệu nghiệp vụ phải nhất quán

Nếu UI dùng `rg` để hiển thị lịch nhưng backend đang dùng một quy tắc tuần cố định (ví dụ ISO week), bạn có thể có hai số tuần khác nhau gần đầu/cuối năm.

Khi **định nghĩa báo cáo** đã quy định cụ thể: “một tuần luôn bắt đầu thứ Hai và dùng quy tắc ISO”, nên khai báo logic đó tường minh qua `WeekFields.ISO` hoặc `WeekFields.of(DayOfWeek.MONDAY, 4)` thay vì suy ra từ preference hiển thị thay đổi theo từng người dùng.

Khi mục tiêu là lịch **phù hợp quy ước của người dùng**, `WeekFields.of(userLocale)` với `rg` lại là cách diễn đạt đúng.

## 9. Ví dụ 3 — định dạng ngày theo vùng, nhưng giữ ngôn ngữ

`java.time.format.DateTimeFormatter` hỗ trợ formatter được địa phương hóa:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

Locale base = Locale.forLanguageTag("en-US");
Locale regional = Locale.forLanguageTag("en-US-u-rg-gbzzzz");

var date = LocalDate.of(2024, 12, 31);
var shortDate = DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT);

System.out.println(shortDate.localizedBy(base).format(date));
System.out.println(shortDate.localizedBy(regional).format(date));
~~~

**Kết quả đã quan sát trên JDK 24, CLDR mặc định:**

~~~text
12/31/24
31/12/2024
~~~

Cùng một `LocalDate` được hiển thị theo hai quy ước ngày khác nhau. Với `rg=GB`, ngày-tháng-năm được trình bày theo pattern phù hợp hơn với dữ liệu vùng GB, trong khi **ngôn ngữ cơ sở của Locale vẫn là `en`**.

**Không đóng đinh** rằng mọi JDK sẽ in đúng hai pattern này. CLDR và provider có thể cập nhật pattern, cách dùng zero-padding hoặc độ dài năm. Trong kiểm thử nghiệp vụ, chú trọng **ý nghĩa dữ liệu** và định dạng có hợp đồng ổn định nếu phải trao đổi giữa hệ thống.

### 9.1. `localizedBy(Locale)` khác `withLocale(Locale)`

`DateTimeFormatter.localizedBy(locale)` (từ Java 10) có hợp đồng áp dụng các giá trị được địa phương hóa từ các Unicode extension như `ca`, `nu`, `rg`, `tz` vào formatter. `withLocale(locale)` chủ yếu đặt Locale dùng cho tra cứu text/pattern về sau.

Theo JavaDoc, `withLocale` lưu Locale được truyền mà **không tự xử lý tất cả localized settings ngay tại thời điểm gọi**; nếu Locale có extension, một số phần có thể được dùng về sau. `localizedBy` còn có thể làm thay đổi **chronology, decimal style hoặc timezone** của formatter theo extension phù hợp.

Vì vậy **không xem hai phương thức là hoàn toàn đồng nghĩa**; với mục tiêu rõ ràng là áp dụng `rg` cùng các thiết lập theo vùng vào một formatter, hãy kiểm tra `localizedBy` và đặc tả của formatter cụ thể.

### 9.2. `rg` không phải timezone

Một locale **không tự xác định chính xác múi giờ của người dùng**. Hoa Kỳ, Vương quốc Anh hoặc nhiều quốc gia khác có lịch sử/định nghĩa múi giờ và daylight saving riêng; mã quốc gia không thay cho `ZoneId`.

~~~java
import java.time.ZoneId;

ZoneId displayZone = ZoneId.of("Europe/London");
~~~

Nếu cần chuyển một `Instant` sang ngày/giờ địa phương, hãy dùng **ZoneId tường minh** hoặc chính sách timezone đã được xác định, thay vì suy ra nó từ `rg`.

Unicode locale key `tz` là một key **riêng** có thể được những API hỗ trợ hiểu; không nhầm nó với `rg`. `rg` chỉ cung cấp region defaults trong phạm vi được hỗ trợ, không có quyền tự di chuyển đồng hồ hệ thống hoặc tự sửa `ZoneId.systemDefault()`.

## 10. Ví dụ 4 — vì sao dấu thập phân có thể không đổi?

Một sai lầm là hiểu “region override” như câu lệnh **biến tất cả dữ liệu locale thành dữ liệu của nước khác**.

Xét:

~~~java
import java.text.DecimalFormatSymbols;
import java.util.Locale;

Locale french = Locale.forLanguageTag("fr-FR");
Locale frenchWithUsRules =
        Locale.forLanguageTag("fr-FR-u-rg-uszzzz");

System.out.println(
        DecimalFormatSymbols.getInstance(french).getDecimalSeparator()
);
System.out.println(
        DecimalFormatSymbols.getInstance(frenchWithUsRules).getDecimalSeparator()
);
~~~

**Trên JDK 24, cả hai dòng đều in dấu phẩy `,`.**

Lý do: chỉ những thông tin thuộc phạm vi **region-specific defaults** mà dịch vụ thực sự tra theo `rg` mới bị điều chỉnh. Nhiều quy ước số/ký hiệu vẫn có thể đến từ dữ liệu của ngôn ngữ cơ sở hoặc kết quả fallback. Ở đây tiếng Pháp vẫn có ảnh hưởng tới dấu thập phân.

**Kết luận:** `rg=uszzzz` không có nghĩa `fr-FR-u-rg-uszzzz` trở thành `en-US` về mọi thứ. Vùng ghi đè **không thay thế language**, không bắt buộc mọi separator trở thành dấu chấm.

Nếu yêu cầu nghiệp vụ nói rõ “dấu thập phân phải là dấu chấm” hoặc “số trao đổi phải dùng ASCII và dấu chấm”, hãy định nghĩa **định dạng máy** tường minh, không dùng `rg` như một phương pháp ép tất cả ký hiệu.

### 10.1. Định dạng dữ liệu để máy đọc phải ổn định

Khi truyền số qua API, JSON hoặc dữ liệu cần parse chặt chẽ, không lấy output của một `NumberFormat` phụ thuộc locale làm chuỗi trao đổi mặc định. Sử dụng định dạng đã được quy định trong giao thức/chuẩn dữ liệu.

Đối với UI, `NumberFormat` rất hữu ích; đối với lưu trữ tiền, tính toán hay giao thức, dùng kiểu số và trường currency code rõ ràng. **Localize presentation**, không nhập nhằng locale presentation với serialization.

## 11. Thứ tự ưu tiên giữa `rg` và các Unicode locale key khác

`rg` thường cung cấp **mặc định ngầm** cho vùng thay thế. Nếu Locale đồng thời có một lựa chọn **tường minh cho cùng thuộc tính**, API tương ứng có thể cho lựa chọn tường minh đó ưu tiên.

| Tình huống | Ví dụ BCP 47 | Thứ tự ưu tiên khi API hỗ trợ |
| --- | --- | --- |
| Chỉ có `rg` | `en-US-u-rg-gbzzzz` | Region defaults của GB thay cho US ở các mục được hỗ trợ. |
| `cu` + `rg` | `en-US-u-cu-jpy-rg-gbzzzz` | **JPY** được chọn tường minh, không phải GBP ngầm từ GB. |
| `fw` + `rg` | `en-US-u-fw-sun-rg-gbzzzz` | **Sunday** được chọn làm first day, thay cho Monday suy từ GB. |
| `nu` + `rg` | Ví dụ locale có `nu` và `rg` | Numbering system tường minh ưu tiên hơn hệ đếm ngầm suy từ vùng. |
| `ca` + `rg` | Ví dụ locale có `ca` và `rg` | Calendar type tường minh ưu tiên hơn mặc định theo vùng trong API hỗ trợ. |
| `tz` + `rg` | Key timezone được chỉ định riêng | Không dùng `rg` để thay một timezone được xác định rõ. |

### 11.1. Kiểm chứng precedence của `cu`

~~~java
Locale currencyOverride = Locale.forLanguageTag(
        "en-US-u-cu-jpy-rg-gbzzzz"
);

System.out.println(
        java.util.Currency.getInstance(currencyOverride).getCurrencyCode()
); // JPY
~~~

Mặc dù `rg=GB` thường dẫn tới GBP, `cu=JPY` thể hiện lựa chọn tiền tệ cụ thể nên được ưu tiên.

**Không đánh đồng** “người dùng chọn JPY để hiển thị” với “một khoản tiền được chuyển đổi tự động từ GBP sang JPY”. `Currency`/`NumberFormat` điều chỉnh loại tiền/ký hiệu sử dụng; quy đổi giá trị tiền đòi một phép tính tỷ giá riêng.

### 11.2. Kiểm chứng precedence của `fw`

~~~java
Locale weekOverride = Locale.forLanguageTag(
        "en-US-u-fw-sun-rg-gbzzzz"
);

System.out.println(
        java.time.temporal.WeekFields.of(weekOverride)
                .getFirstDayOfWeek()
); // SUNDAY
~~~

`fw=sun` thắng ngày đầu tuần ngầm từ GB. Nguyên tắc tổng quát: **đừng sử dụng `rg` để phủ định một preference tường minh cụ thể mà user đã chọn**.

## 12. Chương trình Java 17+ đầy đủ, biên dịch và chạy được

Ví dụ này cố ý so sánh cả **mặc định theo vùng** và **điều không đổi**. Nó không thay `Locale` mặc định toàn JVM. Những con số ở phần định dạng được gắn với bộ dữ liệu của JDK kiểm thử thay vì coi là luật chung không đổi.

Tạo file **`RegionOverrideDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.time.temporal.WeekFields;
import java.util.Currency;
import java.util.Locale;

public class RegionOverrideDemo {
    public static void main(String[] args) {
        Locale base = Locale.forLanguageTag("en-US");
        Locale regional = Locale.forLanguageTag("en-US-u-rg-gbzzzz");
        Locale explicitCurrency =
                Locale.forLanguageTag("en-US-u-cu-jpy-rg-gbzzzz");
        Locale explicitWeek =
                Locale.forLanguageTag("en-US-u-fw-sun-rg-gbzzzz");

        Locale built = new Locale.Builder()
                .setLanguage("en")
                .setRegion("US")
                .setUnicodeLocaleKeyword("rg", "gbzzzz")
                .build();

        System.out.println("language=" + regional.getLanguage());
        System.out.println("base country=" + regional.getCountry());
        System.out.println("rg=" + regional.getUnicodeLocaleType("rg"));
        System.out.println("builder equivalent=" + regional.equals(built));
        System.out.println("currency base=" +
                Currency.getInstance(base).getCurrencyCode());
        System.out.println("currency rg=" +
                Currency.getInstance(regional).getCurrencyCode());
        System.out.println("currency cu wins=" +
                Currency.getInstance(explicitCurrency).getCurrencyCode());
        System.out.println("week base=" +
                WeekFields.of(base).getFirstDayOfWeek());
        System.out.println("week rg=" +
                WeekFields.of(regional).getFirstDayOfWeek());
        System.out.println("week fw wins=" +
                WeekFields.of(explicitWeek).getFirstDayOfWeek());
        System.out.println("week rg minimal days=" +
                WeekFields.of(regional).getMinimalDaysInFirstWeek());

        LocalDate date = LocalDate.of(2024, 12, 31);
        DateTimeFormatter shortDate =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT);
        System.out.println(
                "date base=" + shortDate.localizedBy(base).format(date));
        System.out.println(
                "date rg=" + shortDate.localizedBy(regional).format(date));
        NumberFormat currency = NumberFormat.getCurrencyInstance(regional);
        System.out.println("formatter currency=" +
                currency.getCurrency().getCurrencyCode());
        System.out.println("money rg=" +
                currency.format(new BigDecimal("1234.50")));

        Locale french = Locale.forLanguageTag("fr-FR");
        Locale frenchWithUsRules =
                Locale.forLanguageTag("fr-FR-u-rg-uszzzz");
        System.out.println("fr decimal=" +
                DecimalFormatSymbols.getInstance(french).getDecimalSeparator());
        System.out.println("fr rg decimal=" +
                DecimalFormatSymbols.getInstance(frenchWithUsRules)
                        .getDecimalSeparator());
        System.out.println("fr base country=" +
                frenchWithUsRules.getCountry());
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 RegionOverrideDemo.java
java RegionOverrideDemo
~~~

**Stdout đã kiểm chứng bằng JDK 24 với locale data/provider mặc định:**

~~~text
language=en
base country=US
rg=gbzzzz
builder equivalent=true
currency base=USD
currency rg=GBP
currency cu wins=JPY
week base=SUNDAY
week rg=MONDAY
week fw wins=SUNDAY
week rg minimal days=4
date base=12/31/24
date rg=31/12/2024
formatter currency=GBP
money rg=£1,234.50
fr decimal=,
fr rg decimal=,
fr base country=FR
~~~

### 12.1. Đọc từng phần của stdout

- **`language=en`**: extension không đổi ngôn ngữ cơ sở.
- **`base country=US`**: `getCountry()` không trả vùng ghi đè GB.
- **`rg=gbzzzz`**: `Locale` giữ metadata override dưới Unicode locale keyword `rg`.
- **`builder equivalent=true`**: tạo bằng language tag hay bằng Builder cho Locale có cùng nội dung.
- **`currency base=USD` / `currency rg=GBP`**: API Currency áp dụng giá trị region default.
- **`currency cu wins=JPY`**: key `cu` ghi đè tiền tệ ngầm từ `rg`.
- **`week base=SUNDAY` / `week rg=MONDAY`**: dữ liệu quy ước tuần thay theo vùng.
- **`week fw wins=SUNDAY`**: `fw` ghi đè first-day mặc định từ `rg`.
- **`week rg minimal days=4`**: mô tả một phần quy tắc tuần GB trên dữ liệu kiểm thử.
- **`date base` / `date rg`**: pattern ngày từ dữ liệu locale khác nhau, cùng `LocalDate`.
- **`formatter currency=GBP` / `money rg=£1,234.50`**: format tiền theo locale áp dụng region override.
- **`fr decimal=,` và **`fr rg decimal=,`**: ghi đè vùng không bắt mọi dấu thập phân sang dấu chấm.
- **`fr base country=FR`**: region cơ sở không đổi dù `rg=US`.

**Phạm vi ổn định:** `getCountry()`, `getUnicodeLocaleType("rg")` và việc Builder tạo Locale tương đương dựa trên metadata rõ ràng. Các quy tắc currency/week dựa trên dữ liệu và chính sách được JavaDoc hỗ trợ. **Mẫu ngày, chữ tiền tệ, ký hiệu số, grouping và thậm chí dữ liệu vùng có thể cập nhật theo CLDR và JDK**. Đây là stdout đúng trên môi trường đã thử, không phải lời hứa byte-for-byte cho mọi phiên bản JDK.

## 13. Tình huống ứng dụng thực tế

### 13.1. Người dùng nói tiếng Anh US nhưng muốn lịch và hiển thị theo UK

Yêu cầu:

- Language UI: English (US).
- First day of week: quy tắc GB.
- Default currency display: GBP.
- Country of residence/shipping: **không tự suy luận** từ các lựa chọn này.

Có thể lưu cấu hình:

~~~text
languageTag = en-US
regionPreference = GB
currencyPreference = not explicitly set
firstDayPreference = not explicitly set
~~~

Tại tầng presentation, xây:

~~~java
Locale uiLocale = new Locale.Builder()
        .setLanguageTag("en-US")
        .setUnicodeLocaleKeyword("rg", "gbzzzz")
        .build();
~~~

Sau đó truyền `uiLocale` rõ ràng cho `Currency.getInstance`, `NumberFormat`, `WeekFields`, `DateTimeFormatter.localizedBy` theo mục đích.

Nếu người dùng chọn **JPY** và **Sunday** rõ ràng, cấu hình có thể thêm `cu-jpy` và `fw-sun`; khi ấy các lựa chọn tường minh được ưu tiên trong API tương ứng.

### 13.2. Tách ngôn ngữ hiển thị và dữ liệu địa chỉ

Một API backend có thể nhận cả:

~~~text
displayLocale = en-US-u-rg-gbzzzz
shippingCountry = VN
paymentCurrency = USD
timeZoneId = Asia/Ho_Chi_Minh
~~~

Đây là các trường **khác ý nghĩa**:

- `displayLocale`: phục vụ cách trình bày dữ liệu.
- `shippingCountry`: country nghiệp vụ phải lấy từ thông tin địa chỉ chính thức.
- `paymentCurrency`: đồng tiền cụ thể của giao dịch.
- `timeZoneId`: múi giờ cụ thể dùng để chuyển thời điểm.

Cấu trúc này tránh bug “UI đang chọn GBP thì hệ thống đổi luôn đồng tiền thanh toán” hoặc “region override GB thì backend tự cho rằng khách ở GB”.

### 13.3. Không thay `Locale.setDefault` trong từng HTTP request

Trong một ứng dụng server phục vụ nhiều người dùng, làm như sau dễ tạo lỗi do chia sẻ trạng thái toàn JVM:

~~~java
// PHẢN MẪU trong ứng dụng nhiều request:
Locale.setDefault(userLocale);
var formatter = NumberFormat.getCurrencyInstance();
~~~

`Locale.setDefault` thay trạng thái mặc định của JVM, có thể làm những request khác ảnh hưởng lẫn nhau. **Thực hành nên dùng:** truyền Locale theo từng thao tác:

~~~java
var formatter = NumberFormat.getCurrencyInstance(userLocale);
~~~

`Locale` bất biến nên có thể chia sẻ như giá trị. Nhưng `NumberFormat` và các formatter kiểu `java.text` là đối tượng mutable, không nên dùng cùng một instance chưa được bảo vệ từ nhiều luồng. `DateTimeFormatter` của `java.time` là immutable/thread-safe, phù hợp hơn cho mã ngày giờ mới.

### 13.4. Không bắt người dùng phải chọn region khi không cần

Nếu sản phẩm không cần quy ước vùng khác với locale cơ sở, có thể dùng `en-US`, `vi-VN` hoặc locale phù hợp mà **không thêm `rg`**. `rg` là một **khả năng tùy chỉnh** chứ không phải trường bắt buộc của mọi Locale.

Thêm `rg` tùy tiện làm cấu hình phức tạp, khiến người đọc khó hiểu tại sao country không khớp currency và week rules. Dùng khi có yêu cầu rõ ràng “language/base locale giữ nguyên, region defaults cần khác”.

## 14. Dữ liệu CLDR, provider và tính khác nhau giữa các JDK

Các quy tắc theo vùng không phải toàn bộ được hard-code trong `java.util.Locale`. Dữ liệu địa phương hóa của JDK và các `LocaleServiceProvider` liên quan cung cấp những tài nguyên mà các formatter tra cứu.

Những yếu tố cần lưu ý:

1. **Phiên bản JDK/CLDR**: định dạng ngày/giờ, tên vùng, ký hiệu tiền, cách nhóm số và một số quy ước có thể thay đổi khi dữ liệu cập nhật.
2. **Locale data có trong runtime image**: các runtime được đóng gói tùy chỉnh bằng `jlink` có thể lược bỏ những locale data không dùng. Không giả định mọi image đều có cùng phạm vi dữ liệu.
3. **Locale provider**: các provider khác nhau có thể dùng nguồn dữ liệu và hành vi hỗ trợ extension khác nhau.
4. **Lựa chọn vùng**: việc tồn tại `rg` trên Locale không chứng minh một region code lạ có dữ liệu hợp lệ ở mọi API.
5. **Fallback**: nếu thiếu dữ liệu locale chi tiết, JDK/provider có thể fallback đến parent locale hoặc vùng khác theo quy tắc của dịch vụ.

**Hệ quả kiểm thử:** Không viết unit test yêu cầu toàn bộ chuỗi `"31/12/2024"` hoặc `"£1,234.50"` ở mọi JVM trừ khi bạn **cố định JDK, provider, dữ liệu locale** hoặc chủ động áp đặt pattern của ứng dụng.

Với bài toán cần hợp đồng string ổn định để trao đổi hệ thống, dùng `DateTimeFormatter.ISO_LOCAL_DATE` hoặc một format do giao thức quy định, thay vì bản địa hóa theo CLDR.

### 14.1. Chọn vùng hợp lệ và hỗ trợ

BCP 47/Unicode định nghĩa cú pháp và các tập giá trị hợp lệ. Tuy nhiên, **`Locale.forLanguageTag` nhận được tag** không có nghĩa:

- Mã vùng là quốc gia/thị trường đang có thật theo nghiệp vụ.
- Vùng có đầy đủ dữ liệu CLDR được JDK dùng.
- Mọi Java API đều tôn trọng `rg`.
- Người dùng có quyền đổi region preference tùy ý trong một chức năng cần kiểm soát pháp lý.

Nếu input đến từ HTTP query/header hoặc hồ sơ user, nên kiểm tra allowlist phù hợp với sản phẩm:

~~~java
static Locale withSupportedRegion(
        Locale base, String selectedRegion) {

    String region = java.util.Objects.requireNonNull(selectedRegion)
            .toUpperCase(Locale.ROOT);

    if (!java.util.Set.of("US", "GB", "JP", "VN").contains(region)) {
        throw new IllegalArgumentException("Unsupported preference region");
    }

    return new Locale.Builder()
            .setLocale(base)
            .setUnicodeLocaleKeyword(
                    "rg", region.toLowerCase(Locale.ROOT) + "zzzz")
            .build();
}
~~~

Đây là **minh họa quy tắc allowlist của một ứng dụng**, không phải danh sách vùng mà Java chỉ hỗ trợ bấy nhiêu. Phương thức cần nằm trong class Java thích hợp. Với sản phẩm khác, bộ mã vùng phải được xác định theo danh sách thị trường và nhu cầu thực tế.

**Không chỉ dùng regex để khẳng định “vùng hợp lệ”**: regex kiểm tra cấu trúc, không xác nhận region được đăng ký, tính sẵn có của dữ liệu CLDR hoặc quyền dùng chức năng.

## 15. `rg`, `sd` và mã vùng cơ sở: không nên đánh đồng

Trong Unicode locale identifier, có những khái niệm liên quan vùng:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Region subtag cơ sở | Định danh vùng chính của Locale | `US` trong `en-US`. |
| `rg` | Yêu cầu vùng thay thế cho các mặc định theo vùng của dịch vụ hỗ trợ | `gbzzzz` trong `en-US-u-rg-gbzzzz`. |
| `sd` | Unicode subdivision (phân vùng dưới cấp quốc gia), phục vụ phạm vi dữ liệu khác | Một số giá trị dạng `usca`. |
| `tz` | Lựa chọn timezone thông qua Unicode extension mà một số API hiểu | Key riêng, không đồng nhất `rg`. |

Không tự biến một code subdivision thành `rg` hoặc từ `rg` suy ra một thành phố, tỉnh, bang cụ thể. UTS #35 có quy định chi tiết về các mã vùng và subdivision; mức độ hỗ trợ trong Java SE của từng API không nhất thiết giống nhau.

Đối với ứng dụng Java đa nền tảng, mẫu dễ đọc và dễ kiểm chứng nhất để ghi đè **toàn vùng** là mã region phù hợp kèm `zzzz`, ví dụ `gbzzzz`, `uszzzz`.

## 16. Giới hạn về quy ước đo lường và quy tắc địa phương

Theo CLDR/Unicode, một vùng có thể ảnh hưởng đến mặc định như:

- Tiền tệ.
- Quy ước tuần, ngày đầu tuần.
- Kiểu hiển thị ngày/giờ và một số pattern liên quan.
- Hệ đo lường, khổ giấy hoặc gợi ý đơn vị trong hệ thống địa phương hóa có hỗ trợ.

Nhưng **không được suy ra rằng Java SE cung cấp API chuẩn tự chuyển đổi mọi đơn vị đo lường chỉ từ `rg`**. Ví dụ, một số lượng được lưu là `5 miles` không tự chuyển thành km vì người dùng đổi region preference. Conversion cần giá trị, đơn vị nguồn/đích và quy tắc nghiệp vụ phù hợp.

Tương tự, một UI dùng `rg=GB` không thể tự động quyết định:

- Thuế VAT.
- Ngày nghỉ pháp định của nước đó.
- Ngưỡng chiết khấu hoặc giá hàng hóa.
- Định dạng số chứng minh thư/giấy tờ.
- Địa chỉ/điện thoại hợp lệ của người dùng.
- Quy tắc lịch hoạt động một doanh nghiệp.

Những nghiệp vụ này cần **nguồn dữ liệu và mô hình riêng**, không phải chỉ từ `Locale`.

## 17. Cách kiểm thử `rg` mà không tạo test mong manh

### 17.1. Kiểm thử metadata của Locale

~~~java
Locale locale = Locale.forLanguageTag("en-US-u-rg-gbzzzz");

assert "en".equals(locale.getLanguage());
assert "US".equals(locale.getCountry());
assert "gbzzzz".equals(locale.getUnicodeLocaleType("rg"));
~~~

Đây là các điều kiện liên quan trực tiếp đến cấu trúc Locale. Bật assertions bằng `java -ea YourClass` nếu dùng `assert` trong một chương trình Java.

### 17.2. Kiểm thử tác động hỗ trợ `rg`

~~~java
var region = Locale.forLanguageTag("en-US-u-rg-gbzzzz");
var currency = Currency.getInstance(region);
var firstDay = WeekFields.of(region).getFirstDayOfWeek();

System.out.println(currency.getCurrencyCode());
System.out.println(firstDay);
~~~

Trong môi trường đã được cấu hình/kiểm thử JDK 24 với dữ liệu CLDR mặc định, kết quả là:

~~~text
GBP
MONDAY
~~~

Đây là những hành vi hợp với ví dụ và JavaDoc. Nhưng **không gộp mọi locale-sensitive API vào cùng một giả định** và đừng suy rộng sang vùng không hỗ trợ.

### 17.3. Không hard-code toàn bộ mẫu định dạng vào unit test đa JDK

Nếu phải kiểm thử chuỗi ngày hoặc tiền được format, có thể:

- Dùng integration test trên **runtime đã cố định** (JDK, CLDR/provider nếu môi trường cho phép).
- Đối chiếu những thuộc tính nghiệp vụ như currency code, hoặc kiểm tra round-trip format/parse khi API cho phép.
- Tránh dùng kết quả `toString` của đối tượng locale/formatter làm hợp đồng API để giao tiếp máy.
- Với output cố định theo giao thức, dùng định dạng ISO/pattern tường minh thay cho localize mặc định.

Một test chạy trên JDK 17 không nhất thiết phải có **chuỗi hiển thị** y hệt JDK 24, mặc dù cả hai đều áp dụng `rg` đúng theo dữ liệu riêng.

## 18. Những sai lầm thường gặp

| Ngộ nhận | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “`rg` làm `Locale.getCountry()` thành country ghi đè.” | Country cơ sở là field riêng. | Đọc region override bằng `getUnicodeLocaleType("rg")`. |
| “`rg=GB` chứng minh user đang ở GB.” | Đây là preference trình bày. | Dùng thông tin vị trí/địa chỉ được xác minh riêng. |
| “`en-US-u-rg-gbzzzz` giống hệt `en-GB`.” | Base locale vẫn `en-US`, fallback/text có thể khác. | Phân biệt language/region cơ sở với region defaults. |
| “Mọi API Java đều hiểu `rg`.” | Chỉ những API locale-sensitive hỗ trợ extension mới áp dụng. | Kiểm tra JavaDoc của từng API. |
| “Có `rg` thì DecimalFormatSymbols luôn đổi tất cả separator.” | Nhiều ký hiệu còn phụ thuộc language/locale data. | Không coi `rg` như phép thay thế toàn bộ Locale. |
| “Muốn GBP thì phải chuyển country cơ sở thành GB.” | `rg` có thể chọn region defaults mà vẫn giữ country US. | Tạo `en-US-u-rg-gbzzzz`. |
| “Nếu có `rg`, `cu` không còn hiệu lực.” | `cu` tường minh được ưu tiên hơn tiền tệ ngầm. | Dùng `cu` khi người dùng đã chọn currency. |
| “`fw` bị `rg` ghi đè.” | `fw` tường minh ưu tiên first day. | Giữ `fw` nếu có user preference riêng. |
| “`rg` tự đổi múi giờ.” | Region không phải một `ZoneId` cụ thể. | Tách `ZoneId`/`tz` theo API và business policy. |
| “`Locale.forLanguageTag` xác nhận region code đúng nghiệp vụ.” | Parse tag không kiểm chứng policy/support đầy đủ. | Validate syntax, allowlist, locale data. |
| “Dùng `Locale.setDefault` trong mỗi request là tiện.” | Trạng thái JVM global ảnh hưởng request khác. | Truyền Locale rõ ràng vào formatter. |
| “Định dạng số/tiền từ CLDR dùng được làm serialization cố định.” | Pattern/ký hiệu thay theo JDK/provider. | Dùng định dạng trao đổi có contract riêng. |
| “Đặt `rg` là đã chuyển đổi tỷ giá, đơn vị đo hoặc thuế.” | `rg` chỉ là preference lookup theo vùng. | Tính toán/conversion và luật riêng. |
| “`NumberFormat` shared không cần đồng bộ vì Locale immutable.” | Formatter `java.text` mutable. | Tạo formatter riêng hoặc quản lý thread safety. |
| “Ngày giờ locale theo GB = giờ hiện tại ở London.” | Locale và timezone khác nhau. | Dùng `ZoneId.of("Europe/London")` khi đó là nhu cầu thật. |
| “Mọi JDK hiện đại in cùng pattern ngày.” | CLDR/provider cập nhật. | Kiểm thử tại môi trường mục tiêu, không khóa pattern ngầm. |

## 19. Bài tập thực hành có đáp án

**Câu 1.** Với:

~~~java
Locale x = Locale.forLanguageTag("en-US-u-rg-gbzzzz");
~~~

`x.getCountry()` trả gì? `x.getUnicodeLocaleType("rg")` trả gì?

**Đáp án:** `getCountry()` trả `"US"`; `getUnicodeLocaleType("rg")` trả `"gbzzzz"`. Đó là hai thuộc tính khác nhau.

**Câu 2.** `Currency.getInstance(x)` dùng đồng tiền nào theo dữ liệu region defaults của ví dụ?

**Đáp án:** **GBP** (bảng Anh), vì `rg` yêu cầu lấy mặc định theo vùng GB. Điều này không nói số tiền trong cơ sở dữ liệu đã được quy đổi từ USD sang GBP.

**Câu 3.** Nếu đổi `x` thành `Locale.forLanguageTag("en-GB")`, có hoàn toàn tương đương không?

**Đáp án:** Không. `en-GB` có region **cơ sở** GB; `en-US-u-rg-gbzzzz` vẫn là `en-US` với một số region defaults lấy theo GB. Một số kết quả locale-sensitive có thể giống nhưng không được khẳng định hai Locale là cùng giá trị.

**Câu 4.** Đoán:

~~~java
Locale x = Locale.forLanguageTag("en-US-u-cu-jpy-rg-gbzzzz");
String code = Currency.getInstance(x).getCurrencyCode();
~~~

**Đáp án:** `"JPY"`. `cu=jpy` là chỉ định tiền tệ tường minh, được ưu tiên hơn mặc định GBP do `rg=GB`.

**Câu 5.** Đoán ngày đầu tuần:

~~~java
Locale x = Locale.forLanguageTag("en-US-u-fw-sun-rg-gbzzzz");
var day = WeekFields.of(x).getFirstDayOfWeek();
~~~

**Đáp án:** `SUNDAY` vì `fw=sun` tường minh. `rg=GB` vẫn có thể ảnh hưởng những region defaults khác.

**Câu 6.** Tại sao trên JDK 24, `fr-FR-u-rg-uszzzz` vẫn cho dấu thập phân `,` trong ví dụ?

**Đáp án:** `rg` không thay toàn bộ locale data thành `en-US`. Một số quy ước còn phụ thuộc tiếng Pháp và fallback của provider. Điều này không phủ định ý nghĩa region override.

**Câu 7.** Nếu cần hiển thị ngày của `LocalDate.of(2024,12,31)` theo region defaults GB nhưng giữ `en-US`, có thể làm gì?

**Đáp án:** Tạo `Locale.forLanguageTag("en-US-u-rg-gbzzzz")`, dùng `DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT).localizedBy(locale)`. Trên môi trường JDK 24 đã kiểm chứng, kết quả là `31/12/2024`; pattern cụ thể phụ thuộc dữ liệu locale JDK.

**Câu 8.** `rg=GB` có đủ để xác định timezone hiện tại của user không?

**Đáp án:** Không. Múi giờ là một thuộc tính riêng; phải có `ZoneId` hợp lệ hoặc chính sách xác định timezone. Không coi region override là tọa độ địa lý hay location permission.

**Câu 9.** Có nên dùng `Locale.setDefault(userLocale)` trong mỗi HTTP request để áp dụng `rg` không?

**Đáp án:** Không nên. Default Locale là trạng thái chia sẻ toàn JVM, dễ gây ảnh hưởng giữa các request. Truyền Locale riêng vào API formatting.

**Câu 10.** Nếu thanh toán ghi `paymentCurrency="USD"` nhưng UI preference `rg=GB`, giao dịch có tự chuyển thành GBP không?

**Đáp án:** Không. Tiền tệ giao dịch và tỷ giá là domain data; `rg` chỉ chọn mặc định/định dạng ở các API hỗ trợ. Phải giữ code và phép tính giao dịch riêng.

**Câu 11.** Một user gửi region preference `"ZZ"`. `new Locale.Builder().setUnicodeLocaleKeyword("rg","zzzzzz")` có chứng minh đây là vùng hợp lệ không?

**Đáp án:** Không. Parser/Builder chủ yếu xử lý cú pháp BCP 47, không chứng minh giá trị có dữ liệu CLDR hợp lệ hoặc được business hỗ trợ. Phải kiểm tra tập mã vùng và các quy tắc chấp nhận của ứng dụng.

**Câu 12.** Vì sao test so sánh string ngày `"12/31/24"` hoặc `"31/12/2024"` trên mọi JDK có thể mong manh?

**Đáp án:** Các pattern định dạng phụ thuộc JDK/CLDR/provider, có thể thay đổi mà API vẫn hoạt động đúng. Unit/integration tests nên kiểm tra hợp đồng và cố định runtime nếu phải khẳng định toàn bộ chuỗi.

## 20. Checklist khi dùng `rg` trong ứng dụng

- [ ] Tôi hiểu **`rg` là region override**, một Unicode locale extension được Java 10+ hỗ trợ.
- [ ] Tôi dùng thẻ đúng kiểu `en-US-u-rg-gbzzzz` hoặc `Locale.Builder`.
- [ ] Tôi phân biệt **`getCountry()`** với **`getUnicodeLocaleType("rg")`**.
- [ ] Tôi không dùng `rg` làm bằng chứng nơi cư trú, quốc tịch, thuế, shipping hoặc địa chỉ.
- [ ] Tôi biết API nào thực sự hỗ trợ `rg` và đã đọc JavaDoc liên quan.
- [ ] Tôi cho **`cu`, `fw`, `nu`, `ca`** ưu tiên khi API hỗ trợ và người dùng đã chọn tường minh.
- [ ] Tôi không dùng `rg` để suy diễn timezone; `ZoneId` được quản lý riêng.
- [ ] Tôi không tin rằng `rg` thay toàn bộ ngôn ngữ/dấu phân cách/pattern dữ liệu.
- [ ] Tôi dùng `WeekFields` cho quy ước tuần và `java.time` cho date/time mới.
- [ ] Tôi dùng `DateTimeFormatter.localizedBy` khi cần áp dụng localized settings từ extension.
- [ ] Tôi không làm thay `Locale.setDefault` trong mỗi request.
- [ ] Tôi quản lý thread safety của `NumberFormat`, không suy từ tính immutable của Locale.
- [ ] Tôi dùng currency code thật của giao dịch, không lấy mặc định từ locale để tính toán tiền.
- [ ] Tôi kiểm tra region preferences đầu vào và tập locale data có sẵn trong runtime.
- [ ] Tôi biết kết quả format chịu tác động CLDR/provider/JDK; không hard-code string hiển thị làm hợp đồng trao đổi.
- [ ] Tôi đã kiểm thử ít nhất base locale, region override và các explicit overrides như `cu`/`fw`.

## 21. Nguồn tham khảo chính thức (còn áp dụng)

1. [Oracle — Internationalization Enhancements in JDK 10](https://docs.oracle.com/javase/10/intl/internationalization-enhancements-jdk-10.htm): từ Java 10 hỗ trợ thêm `cu`, `fw`, **`rg`** và `tz` cho các dịch vụ liên quan.
2. [OpenJDK — JEP 314: Additional Unicode Language-Tag Extensions](https://openjdk.org/jeps/314): mục tiêu hỗ trợ các Unicode locale extension theo CLDR.
3. [Java SE 25 — `Locale`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html): BCP 47, `forLanguageTag`, Unicode locale key/type, cấu trúc language/region và `Locale.Builder`.
4. [Java SE 25 — `Currency.getInstance(Locale)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Currency.html#getInstance(java.util.Locale)): hỗ trợ `rg` và `cu`, thứ tự ưu tiên currency type.
5. [Java SE 25 — `NumberFormat`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/NumberFormat.html): tiền tệ, các Unicode extension liên quan và tính locale-sensitive.
6. [Java SE 25 — `DecimalFormatSymbols`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/DecimalFormatSymbols.html): ký hiệu số, region override và dữ liệu locale.
7. [Java SE 25 — `WeekFields.of(Locale)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/temporal/WeekFields.html#of(java.util.Locale)): hành vi `rg` và `fw` cho tuần.
8. [Java SE 25 — `DateTimeFormatter.localizedBy`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html#localizedBy(java.util.Locale)): localized values từ `ca`, `nu`, `rg`, `tz`; phương thức từ Java 10.
9. [Java SE 25 — `DecimalStyle.of(Locale)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DecimalStyle.html#of(java.util.Locale)): numbering system và region override theo dữ liệu hỗ trợ.
10. [Unicode UTS #35 — Region Override](https://unicode.org/reports/tr35/): định nghĩa `rg` và hậu tố `zzzz` trong Unicode locale identifier; phạm vi những mặc định theo vùng.
11. [Unicode UTS #35 — Territory-Based Preferences](https://unicode.org/reports/tr35/tr35-info.html): vùng ảnh hưởng tới tiền tệ, quy ước tuần, lịch, chu kỳ giờ và một số lựa chọn vùng khác.
12. [Oracle — Supported Locales in JDK 26](https://www.oracle.com/java/technologies/javase/jdk26-supported-locales.html): danh sách Unicode extension vẫn được JDK hỗ trợ và sự phụ thuộc dữ liệu CLDR.

**Tóm tắt:** `rg` cho phép một Locale giữ **ngôn ngữ và region cơ sở** trong khi yêu cầu **một số giá trị mặc định theo vùng khác** ở các API hỗ trợ. Trong Java 10+, `en-US-u-rg-gbzzzz` vẫn có `getCountry() == "US"`, nhưng có thể dùng **GBP** và quy ước tuần GB; lựa chọn tường minh như `cu` và `fw` được ưu tiên trong phạm vi tương ứng. **Không** biến region override thành thông tin vị trí thực, múi giờ, loại tiền giao dịch hoặc một quy tắc thay thế toàn bộ dữ liệu locale.