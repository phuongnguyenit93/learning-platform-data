# Ảnh hưởng của dữ liệu bản địa hóa được cung cấp bởi JDK (Java 10+)

## 1. Vì sao cùng một `Locale` có thể cho kết quả định dạng khác nhau?

Khi viết ứng dụng Java cho nhiều ngôn ngữ và quốc gia, chúng ta thường truyền một `java.util.Locale` vào bộ định dạng:

```java
var locale = java.util.Locale.forLanguageTag("vi-VN");
var number = java.text.NumberFormat.getNumberInstance(locale);
System.out.println(number.format(1234567.5));
```

Đoạn trên biểu đạt rõ: **định dạng số cho người dùng ưu tiên tiếng Việt tại Việt Nam**. Nhưng `Locale.forLanguageTag("vi-VN")` **không chứa một bản sao cố định của toàn bộ quy tắc định dạng số**. Nó chủ yếu biểu diễn *định danh/ưu tiên bản địa hóa*. Các mẫu định dạng, ký hiệu, tên tháng, quy tắc đầu tuần, tên tiền tệ và nhiều chuỗi hiển thị khác được những dịch vụ của JDK lấy từ **dữ liệu bản địa hóa (locale data)**.

Điểm quan trọng của bài là: **mã nguồn, đầu vào và `Locale` có thể giữ nguyên, nhưng chuỗi kết quả có thể thay đổi khi JDK, bộ dữ liệu CLDR, cấu hình locale provider hoặc runtime image thay đổi.** Điều này không nhất thiết là bug; nhiều khi đó là kết quả của việc cập nhật quy ước địa phương.

Ví dụ, trên một JDK có dữ liệu CLDR phù hợp:

```text
en-US: 1,234,567.5
vi-VN: 1.234.567,5
```

Các chuỗi trên là **minh họa cho sự khác biệt định dạng theo vùng**; không phải lời hứa rằng mọi phiên bản JDK, mọi provider và mọi cấu hình sẽ tạo đúng từng dấu phân cách trong suốt tương lai.

Bài này giúp bạn hiểu:

- `Locale` cung cấp **thông tin gì** và phần nào được **dữ liệu JDK quyết định**.
- CLDR là gì, vì sao **JEP 252** và **JEP 314** có ý nghĩa khi học Java 10.
- Những API chịu ảnh hưởng như `NumberFormat`, `DateTimeFormatter`, `Currency`, `WeekFields`, `Locale.getDisplayName`.
- Vai trò của các nguồn `CLDR`, `HOST`, `SPI`, module `jdk.localedata` và runtime được tạo bởi `jlink`.
- Cách nâng cấp JDK mà không biến **chuỗi hiển thị cho người dùng** thành một giao thức dữ liệu cứng và dễ vỡ.
- Cách kiểm thử sự khác biệt bằng chương trình Java 17+ và quản lý rủi ro theo phiên bản.

**Special Note của module:** Chỉ các cơ chế Java **vẫn còn áp dụng hiện nay** được khuyến nghị. Các cấu hình dữ liệu locale đã bị loại bỏ sẽ được nhắc đến chỉ để **tránh sử dụng**, không xem là giải pháp hiện hành.

## 2. Phân biệt `Locale`, locale data và locale-sensitive service

Ba lớp khái niệm thường bị nhập làm một:

| Lớp | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **Định danh bản địa hóa** | `Locale.forLanguageTag("vi-VN")` | Diễn đạt ngôn ngữ, script, region và Unicode locale extensions; là một đối tượng Java |
| **Nguồn dữ liệu bản địa hóa** | Dữ liệu **Unicode CLDR** tích hợp trong JDK | Cung cấp quy tắc/ký hiệu/mẫu tên và định dạng theo ngôn ngữ, vùng |
| **API áp dụng dữ liệu** | `NumberFormat`, `DateTimeFormatter`, `Currency`, `WeekFields` | Dùng Locale và locale data để format, parse hoặc xác định một quy tắc |

Sơ đồ:

```text
             Locale("vi-VN-u-fw-mon")
                         |
                         v
         Locale-sensitive Java API
       /           |              \
NumberFormat  DateTimeFormatter  WeekFields
       \           |              /
        \          v             /
        Locale data do JDK/provider cung cấp
             (CLDR, HOST, SPI...)
                         |
                         v
       Chuỗi hiển thị / quy tắc được chọn
```

### 2.1. `Locale` không phải bảng dữ liệu CLDR

`Locale` chứa các trường như:

- language: `vi`, `en`, `ja`;
- script: `Latn`, `Cyrl`;
- region: `VN`, `US`, `JP`;
- các extension, ví dụ Unicode `-u-fw-mon` hoặc `-u-cu-eur`.

`Locale` là một đối tượng **immutable**. Các phương thức `getLanguage()`, `getCountry()`, `toLanguageTag()` cho biết định danh đã lưu. Nhưng chúng **không tự trả về** quy tắc phân cách hàng nghìn, cách gọi tên tháng hoặc mọi giá trị được một formatter sử dụng.

Ví dụ:

```java
var locale = java.util.Locale.forLanguageTag("vi-VN");
System.out.println(locale.getLanguage());    // vi
System.out.println(locale.getCountry());     // VN
System.out.println(locale.toLanguageTag());  // vi-VN
```

Những kết quả đó tương đối ổn định theo hợp đồng `Locale`; còn `NumberFormat.getInstance(locale).format(...)` phụ thuộc thêm vào dữ liệu và implementation của service.

### 2.2. Locale data không chỉ là bản dịch

Ngoài từ/ngữ như tên thứ và tên tháng, locale data có thể bao gồm:

- mẫu ngày, giờ, số và tiền tệ;
- dấu thập phân, dấu nhóm chữ số, ký hiệu phần trăm;
- dạng biểu diễn tiền tệ và tên tiền tệ theo ngôn ngữ;
- quy tắc đầu tuần và số ngày tối thiểu trong tuần đầu tiên;
- tên ngôn ngữ/quốc gia được bản địa hóa;
- quy tắc vùng liên quan tới các Unicode locale extensions.

**Không phải mọi service trong JDK đều dùng cùng một tập dữ liệu hoặc cùng provider.** Ví dụ, danh sách locale được hỗ trợ cho `NumberFormat` không nhất thiết giống mọi service khác. Các thuật toán phân đoạn văn bản và sắp xếp có ngoại lệ về nguồn dữ liệu trong từng JDK. Không nên tuyên bố “CLDR điều khiển toàn bộ hành vi bản địa hóa của mọi class Java”.

## 3. CLDR và mối liên hệ với Java 10

**CLDR (Common Locale Data Repository)** là dự án dữ liệu bản địa hóa của Unicode Consortium, cung cấp dữ liệu dùng trong nhiều hệ sinh thái phần mềm. Các bản JDK hiện đại tích hợp dữ liệu CLDR để triển khai nhiều dịch vụ locale-sensitive trong Java.

### 3.1. JEP 252: CLDR trở thành nguồn dữ liệu mặc định từ Java 9

**JEP 252 — Use CLDR Locale Data by Default** được triển khai từ **JDK 9**. Thay đổi này có nghĩa những API chịu ảnh hưởng bắt đầu ưu tiên bộ dữ liệu CLDR, thay vì bộ dữ liệu JDK cũ được duy trì để tương thích với các bản trước.

Điều này liên quan trực tiếp đến code Java 10: **Java 10 đã chạy trong thời kỳ CLDR được dùng mặc định**. Do đó khi chuyển một ứng dụng cũ sang Java 10, cùng một đoạn code định dạng ngày/giờ/số có thể cho đầu ra khác Java 8.

Những khác biệt có thể gặp:

- ký hiệu thập phân hoặc dấu nhóm số;
- dấu cách thường so với ký tự khoảng trắng Unicode khác;
- cách viết ngày/tháng hoặc dấu phân cách ngày;
- viết hoa, viết tắt, tên vùng/tiền tệ;
- các mẫu locale-sensitive dùng khi **parse** chuỗi ngày hoặc số.

**Không nên dùng thay đổi dữ liệu thành lý do “hard-code” mọi chuỗi hiển thị.** CLDR được cập nhật nhằm phản ánh quy ước địa phương tốt hơn. Thay vì phụ thuộc một đầu ra cũ, hãy lựa chọn rõ đâu là **UI locale** và đâu là **định dạng dữ liệu máy tính**.

### 3.2. JEP 314: Java 10 mở rộng hỗ trợ Unicode locale extensions

**JEP 314 — Additional Unicode Language-Tag Extensions** được giao trong **JDK 10**. Nó tăng mức hỗ trợ những Unicode locale keywords trong các API liên quan:

| Key | Tác dụng | API tiêu biểu |
| --- | --- | --- |
| `cu` | Currency type | `Currency.getInstance(Locale)` |
| `fw` | First day of week | `WeekFields.of(Locale)` |
| `rg` | Region override | `Currency`, `NumberFormat`, `WeekFields` và các dịch vụ áp dụng dữ liệu vùng |
| `tz` | Time zone | `DateFormat` và các bộ định dạng thời gian hỗ trợ |

Hai key `ca` (calendar) và `nu` (numbering system) đã có hỗ trợ trong những API liên quan **trước Java 10**.

Đây là **hai câu chuyện khác nhau**:

- **JEP 252**: thay đổi **nguồn dữ liệu locale mặc định**, có từ Java 9.
- **JEP 314**: mở rộng cách một số API **diễn giải Unicode locale extensions**, có từ Java 10.

Ví dụ:

```java
var euro = java.util.Locale.forLanguageTag("en-US-u-cu-eur");
var ukRegion = java.util.Locale.forLanguageTag("en-US-u-rg-gbzzzz");
var monday = java.util.Locale.forLanguageTag("en-US-u-fw-mon");

System.out.println(
        java.util.Currency.getInstance(euro).getCurrencyCode());    // EUR
System.out.println(
        java.util.Currency.getInstance(ukRegion).getCurrencyCode()); // GBP
System.out.println(
        java.time.temporal.WeekFields.of(monday).getFirstDayOfWeek());
// MONDAY
```

Đây là các lệnh minh họa trong phương thức và có thể chạy với import hoặc fully qualified class tương ứng. Chương trình đầy đủ ở phần 11.

Với `rg-gbzzzz`, `Locale.getCountry()` vẫn là `US` nếu tag cơ sở là `en-US`; một **service** có thể dùng region override `GB` để lấy dữ liệu liên quan. **Không nhầm việc override dữ liệu với việc sửa thuộc tính region của object `Locale`.**

### 3.3. Không đồng nhất “Java hỗ trợ một keyword” với “mọi API đều hỗ trợ”

`Locale.forLanguageTag(...)` có thể lưu một extension `-u-...` hợp cú pháp, nhưng một formatter chỉ có trách nhiệm áp dụng những key mà hợp đồng của nó công bố.

Ví dụ, `fw-mon` liên quan ngày bắt đầu tuần và `WeekFields`; nó không khiến `Currency.getInstance` trả một loại tiền khác. `cu-eur` có thể ảnh hưởng tiền tệ nhưng không tự đổi múi giờ máy chủ. Bản thân `Locale` **không xác nhận mọi type Unicode có dữ liệu thực thi**.

## 4. Vì sao dữ liệu CLDR khác nhau giữa các bản JDK?

JDK có thể tích hợp những phiên bản CLDR khác nhau. Theo bảng trong Javadoc `LocaleServiceProvider` của Java SE 27:

| Bản JDK | Phiên bản CLDR dùng trong bản phát hành tương ứng |
| --- | --- |
| JDK 10 | CLDR 29 |
| JDK 11 | CLDR 33 |
| JDK 17 | CLDR 39 |
| JDK 21 | CLDR 43 |
| JDK 25 | CLDR 47 |
| JDK 26 | CLDR 48 |
| JDK 27 | CLDR 48.2 |

Bảng này là **ảnh chụp thông tin phiên bản tính tới thời điểm tài liệu Java 27**, không phải quy tắc rằng tất cả các bản cập nhật về sau sẽ mãi dùng cùng một phiên bản CLDR. Khi cần kiểm tra một môi trường cụ thể, xem release notes/Javadoc của **chính bản JDK đang triển khai**.

### 4.1. Những thay đổi dễ ảnh hưởng tới kết quả

CLDR có thể cập nhật:

- dữ liệu locale mới và độ bao phủ cho các vùng;
- tên ngôn ngữ, quốc gia, thành phố hoặc múi giờ;
- mẫu ngày/giờ, ký hiệu AM/PM, cách dùng khoảng trắng;
- nhóm chữ số, dấu phân cách, số lượng chữ số hoặc ký hiệu tiền tệ;
- quy tắc đầu tuần và thông tin lịch liên quan.

Ví dụ mang tính thực tế: một bản cập nhật CLDR có thể thay khoảng trắng thông thường bằng **narrow no-break space** (U+202F) trong một chuỗi định dạng ngày/giờ. Chúng có thể **nhìn gần giống nhau** trên màn hình nhưng **không bằng nhau** khi so theo `String.equals` hoặc parse bằng một biểu thức kỳ vọng ký tự khoảng trắng cũ.

Một test kiểu:

```java
// Mong đợi chính xác một chuỗi format bản địa hóa,
// bao gồm cả ký hiệu phân cách và dấu cách:
assertEquals("...", formatter.format(date));
```

chỉ là **minh họa dạng kiểm thử**, không phải ví dụ có thể chạy độc lập. Nó dễ trở nên mong manh nếu sử dụng output CLDR làm một hợp đồng chuỗi vĩnh viễn. Nếu cần kiểm tra exact output của UI, hãy cố định môi trường thử nghiệm (phiên bản JDK/provider/locale) và cập nhật snapshots có chủ đích khi nâng runtime.

### 4.2. JDK 27 là ví dụ rằng dữ liệu còn tiếp tục được cập nhật

JDK 27 (phát hành tháng 9 năm 2026) tích hợp **CLDR 48.2**. Release notes ghi nhận thay đổi dữ liệu có thể tác động **Date/Time/Number formats**, bên cạnh dữ liệu địa phương mới hoặc các bản sửa.

Vì vậy, đừng dựa vào lập luận: “Mã Java 10 vẫn biên dịch nên chuỗi được format trên Java 27 chắc chắn y hệt Java 10”. **API compatibility** không đồng nghĩa **data compatibility** đối với mọi chuỗi phụ thuộc bản địa hóa.

## 5. Các nguồn locale data trong JDK hiện đại

JDK có thể sử dụng nhiều **locale service providers**. Với Oracle JDK 27, tài liệu công bố ba nguồn chính:

| Provider | Nguồn dữ liệu | Khi nào phù hợp |
| --- | --- | --- |
| `CLDR` | Dữ liệu Unicode CLDR tích hợp trong JDK | **Mặc định** cho các dịch vụ có hỗ trợ; phù hợp với yêu cầu i18n thông thường |
| `HOST` | Cài đặt locale của hệ điều hành chủ | Khi ứng dụng có chủ đích muốn phản ánh tùy chỉnh từ OS và provider/platform hỗ trợ |
| `SPI` | `LocaleServiceProvider` do ứng dụng/thư viện triển khai | Khi có yêu cầu dùng dữ liệu bản địa hóa tùy chỉnh được cung cấp đúng cơ chế SPI |

**Lưu ý về `HOST`:** phạm vi hỗ trợ phụ thuộc nền tảng. Tài liệu Oracle JDK 27 nêu `HOST` trên Windows và macOS; đừng suy ra một ứng dụng chạy trên Linux luôn có provider này với hành vi tương đương.

### 5.1. Cấu hình `java.locale.providers`

Thuộc tính hệ thống `java.locale.providers` quy định **thứ tự ưu tiên nguồn dữ liệu**, ví dụ:

```bash
java "-Djava.locale.providers=CLDR" LocaleDataDemo
```

Với JDK 27, **mặc định tương đương `CLDR`**. Lệnh trên có ý nghĩa minh họa rõ lựa chọn, nhưng không bắt buộc khi bạn đã chấp nhận thiết lập mặc định.

Nếu ứng dụng có cài đặt nhà cung cấp SPI riêng:

```bash
java "-Djava.locale.providers=SPI,CLDR" YourApplication
```

`YourApplication` ở đây là **tên class minh họa cho ứng dụng có thật**, không phải class trong chương trình ví dụ. Lệnh chỉ thành công khi ứng dụng, đường dẫn class/module và service provider được cấu hình phù hợp.

Với `SPI,CLDR`: JDK tìm dịch vụ thích hợp trong `SPI` trước; nếu không có nhà cung cấp phù hợp cho yêu cầu đó, có thể tiếp tục tìm trong `CLDR`. Cấu hình **không** đồng nghĩa “toàn bộ API bắt buộc cùng một provider” hay “`SPI` luôn thay thế mọi định dạng”.

**Thiết lập provider ở thời điểm khởi động JVM.** Không dùng `System.setProperty("java.locale.providers", ...)` giữa lúc chương trình đang hoạt động rồi kỳ vọng tất cả formatter đã tạo hoặc dữ liệu cached sẽ tự tái cấu hình.

### 5.2. Không đề xuất `JRE`/`COMPAT` trong ứng dụng hiện hành

Các bản JDK cũ từng có provider tương thích dữ liệu locale trước CLDR mang tên `JRE` / `COMPAT`. **JDK 23 đã loại bỏ dữ liệu legacy đó**. Việc chỉ định `java.locale.providers=JRE` hoặc `COMPAT` **không còn là phương án khôi phục dữ liệu cũ trong JDK 23+**.

Nếu dự án phụ thuộc hành vi locale cũ, hướng hiện đại là:

- xác định đầu ra/pattern nào là **hợp đồng nghiệp vụ thực sự**;
- dùng formatter với **quy tắc explicit** cho những định dạng cần cố định;
- cung cấp một **locale service provider tùy chỉnh** nếu cần một hệ thống i18n riêng;
- chạy kiểm thử tương thích trên runtime mục tiêu.

**Không khuyên người học dùng công tắc đã bị loại bỏ như cách giải quyết lâu dài.**

### 5.3. Provider selection không phải lựa chọn Locale

`java.locale.providers=CLDR` chỉ chọn **nguồn dữ liệu ưu tiên**. Nó không biến mọi request thành `Locale.US` hoặc `Locale.VIETNAM`. Người gọi vẫn cần truyền một `Locale` phù hợp cho service.

Tương tự, `Locale.setDefault(...)` thay đổi default Locale của quá trình theo phạm vi nhất định; đó không phải là cách chọn phiên bản CLDR. Trong ứng dụng server nhiều người dùng, hãy **truyền Locale explicit theo request** thay vì đổi default chung cho mọi request.

## 6. Locale data ảnh hưởng tới những API nào?

### 6.1. `NumberFormat` và `DecimalFormatSymbols`

`NumberFormat.getNumberInstance(locale)` dùng dữ liệu như dấu thập phân, nhóm chữ số, cách hiển thị số. `NumberFormat.getCurrencyInstance(locale)` kết hợp thêm quy ước tiền tệ phù hợp.

```java
var us = java.text.NumberFormat.getNumberInstance(
        java.util.Locale.US);
var vn = java.text.NumberFormat.getNumberInstance(
        java.util.Locale.forLanguageTag("vi-VN"));

System.out.println(us.format(1234567.5));
System.out.println(vn.format(1234567.5));
```

Những chuỗi cụ thể nên xem là **đầu ra quan sát được trên runtime đang dùng**. Dấu phân cách có thể thay đổi khi provider hoặc CLDR nâng cấp. Nếu cần phân tích kỹ ký tự vô hình, có thể in từng Unicode code point của chuỗi định dạng thay vì chỉ nhìn bằng mắt.

`DecimalFormatSymbols.getInstance(locale)` cung cấp các ký hiệu như dấu thập phân, dấu nhóm số hoặc biểu tượng số; nó cũng chịu ảnh hưởng nguồn dữ liệu locale. Nếu thiết kế giao thức muốn một dấu `.` cố định, **không dùng output `NumberFormat` bản địa hóa làm định dạng máy tính**.

### 6.2. `DateTimeFormatter` với định dạng bản địa hóa

`java.time.format.DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)` chọn mẫu ngày theo locale.

```java
var date = java.time.LocalDate.of(2026, 11, 7);
var formatter = java.time.format.DateTimeFormatter
        .ofLocalizedDate(java.time.format.FormatStyle.LONG)
        .withLocale(java.util.Locale.forLanguageTag("vi-VN"));

String displayed = formatter.format(date);
```

Đoạn mã là minh họa trong một phương thức với import hoặc tên đầy đủ tương ứng.

Một bản JDK có thể hiển thị ngày này bằng một cụm từ tiếng Việt; bản khác có thể sửa cách viết, dấu cách hoặc mẫu. `Locale` vẫn là `vi-VN`. **Chính formatter + dữ liệu JDK** quyết định output.

Đừng dùng định dạng hiển thị dài này làm khóa dữ liệu, input API hay lưu trữ vĩnh viễn nếu bạn cần chuỗi ổn định giữa các bản runtime. Với một ngày ISO, dùng:

```java
String machine = java.time.format.DateTimeFormatter
        .ISO_LOCAL_DATE.format(date);
// "2026-11-07"
```

`ISO_LOCAL_DATE` dùng quy tắc ISO phù hợp cho dữ liệu máy tính, không phải tên tháng địa phương phụ thuộc CLDR.

### 6.3. `Currency` và ý nghĩa vùng

`Currency.getInstance(locale)` có thể xác định currency mặc định theo vùng, hoặc áp dụng các Unicode extensions phù hợp như `cu` và `rg`.

```java
var currencyLocale = java.util.Locale.forLanguageTag(
        "en-US-u-cu-eur");
var regionLocale = java.util.Locale.forLanguageTag(
        "en-US-u-rg-gbzzzz");

System.out.println(
        java.util.Currency.getInstance(currencyLocale)
                .getCurrencyCode()); // EUR
System.out.println(
        java.util.Currency.getInstance(regionLocale)
                .getCurrencyCode()); // GBP
```

Khi cần chính xác mã tiền tệ của một giao dịch, **lưu mã ISO currency của giao dịch** (ví dụ EUR) thay vì chỉ lưu Locale và mỗi lần chạy suy lại currency mặc định từ vùng. Dữ liệu quốc gia/tiền tệ thực tế có thể thay đổi theo thời gian; `Locale` không phải mô hình kế toán.

### 6.4. `WeekFields` và quy tắc đầu tuần

`java.time.temporal.WeekFields.of(locale)` dùng dữ liệu tuần theo vùng, đồng thời có thể áp dụng Unicode extension `fw` và `rg`.

```java
var mondayLocale = java.util.Locale.forLanguageTag(
        "en-US-u-fw-mon");

System.out.println(
        java.time.temporal.WeekFields
                .of(mondayLocale).getFirstDayOfWeek());
// MONDAY
```

Nếu yêu cầu nghiệp vụ luôn bắt đầu tuần thứ Hai, bạn có thể định nghĩa trực tiếp:

```java
var fixed = java.time.temporal.WeekFields.of(
        java.time.DayOfWeek.MONDAY, 4);
```

Lời gọi này đặt **Monday** và **4 ngày tối thiểu trong tuần đầu**, không tự suy từ dữ liệu locale. Chỉ nên dùng thông số `4` nếu nó thực sự phù hợp hợp đồng của ứng dụng.

### 6.5. `Locale.getDisplayName` và tên địa phương

`getDisplayLanguage`, `getDisplayCountry`, `getDisplayName` và các API tên hiển thị phụ thuộc dữ liệu locale và **Locale dùng để hiển thị**.

```java
var target = java.util.Locale.forLanguageTag("vi-VN");
String label = target.getDisplayName(
        java.util.Locale.forLanguageTag("en-US"));
```

`label` có thể được dùng trong giao diện chọn ngôn ngữ, nhưng **không phải khóa định danh ổn định**. Một bản CLDR mới có thể sửa tên hiển thị, cách viết hoặc bản dịch. Hãy lưu `target.toLanguageTag()` làm mã định danh; render tên bằng dữ liệu locale khi hiển thị.

### 6.6. Phân biệt locale data với quy tắc timezone

Một JDK còn có **IANA time-zone database (tzdb)** dùng cho quy tắc offset và daylight saving time, bên cạnh CLDR cho một số **tên hiển thị và quy ước theo locale**.

- `ZoneId` và `ZoneRules` liên quan đến quy tắc thời gian theo múi giờ.
- Một formatter có thể lấy tên hiển thị múi giờ theo locale data.
- Bản JDK update có thể thay **tzdb** độc lập với thay đổi **CLDR**.

Không quy tất cả mọi thay đổi về giờ mùa hè cho CLDR; cần phân biệt **quy tắc thời gian thực** với **cách dịch/tên hiển thị**.

## 7. Module `jdk.localedata` và ảnh hưởng của runtime image

Từ khi Java dùng module system (Java 9+), dữ liệu locale được phân bổ theo module. Tài liệu JDK 27 nêu:

- `java.base` chứa phần dữ liệu nền tảng tối thiểu, bao gồm US English và các parent locales liên quan.
- `jdk.localedata` chứa nhiều dữ liệu locale khác.
- Với **JDK đầy đủ**, những dữ liệu thích hợp thường sẵn có.
- Một **runtime image tùy biến** được tạo bởi `jlink` có thể không chứa toàn bộ dữ liệu locale hoặc chỉ giữ một tập locale cần thiết.

### 7.1. Tại sao chạy trong container/runtime tối giản có thể khác máy phát triển?

Giả sử bạn thử `vi-VN` trên máy lập trình với JDK đầy đủ, nhưng deploy bằng một runtime image chỉ chứa dữ liệu en-US. Các API bản địa hóa **có thể phải fallback** thay vì sử dụng những quy tắc chi tiết mà bạn đã thấy trên máy phát triển.

Ví dụ về cách tạo runtime image có chủ đích bao gồm dữ liệu địa phương cần thiết:

```bash
jlink --add-modules java.base,jdk.localedata \
      --include-locales vi,en \
      --output runtime-i18n
```

Lệnh trên minh họa **môi trường shell POSIX** (dấu `\` cuối dòng để nối lệnh); trên Windows cần viết cùng một dòng hoặc dùng cú pháp xuống dòng của shell tương ứng. `jlink` cần một JDK đầy đủ và các module tương ứng.

**Đừng sao chép một cấu hình `--include-locales` của dự án khác mà không kiểm tra** những Locale thực tế của ứng dụng. Việc lọc dữ liệu nhằm tối ưu runtime size phải đi kèm kiểm thử đủ các ngôn ngữ/vùng được hỗ trợ.

Nếu muốn tránh cú pháp shell khác nhau, viết trên một dòng:

```bash
jlink --add-modules java.base,jdk.localedata --include-locales vi,en --output runtime-i18n
```

Đây là ví dụ thao tác deployment để giải thích module data; nó **không** thay thế quy trình build/packaging đầy đủ của dự án.

### 7.2. Kiểm tra dịch vụ, không chỉ kiểm tra tag

`Locale.forLanguageTag("vi-VN")` vẫn có thể tạo object `Locale` ngay cả khi runtime thiếu dữ liệu `vi-VN` cho một service. **Parse được tag không chứng minh locale data đầy đủ đang có trong image.**

Muốn điều tra:

- xem danh sách module trong runtime image;
- kiểm tra `jdk.localedata` có được đóng gói theo thiết kế hay không;
- đọc tài liệu locale được hỗ trợ của chính bản JDK;
- kiểm tra `NumberFormat.getAvailableLocales()` hoặc API `getAvailableLocales()` của **dịch vụ cụ thể**;
- chạy một formatter thực với `vi-VN` và xác nhận đầu ra được mong đợi trên deployment target.

`Locale.getAvailableLocales()` không thay thế kiểm thử từng service nếu ứng dụng dùng nhiều loại formatter và SPI.

## 8. Khác biệt khi thay đổi provider: lựa chọn có tác động thế nào?

Giả sử có cùng một Locale:

```java
var locale = java.util.Locale.forLanguageTag("fr-FR");
```

Nhưng hai môi trường cấu hình khác nhau:

- Môi trường A dùng provider `CLDR` của JDK.
- Môi trường B ưu tiên provider `HOST` trên một OS hỗ trợ hoặc `SPI` do ứng dụng cung cấp.

Cả hai đều có `locale.toLanguageTag()` là `fr-FR`, nhưng đầu ra định dạng **có thể khác**, vì dữ liệu và quy tắc đến từ hai provider khác nhau.

### 8.1. Kiểm tra khả năng hỗ trợ của provider

Lớp `java.util.spi.LocaleServiceProvider` là cơ chế chuẩn cho các locale-sensitive service providers. Một ứng dụng có thể triển khai SPI phù hợp và cấu hình thứ tự tra cứu.

**Không suy đoán** rằng tên provider một mình quyết định mọi đầu ra: nếu service/locale yêu cầu không được provider đó hỗ trợ, JDK có thể tiếp tục tra cứu trong những provider tiếp theo. Phải kiểm thử **API, Locale và dữ liệu** thực tế.

### 8.2. Cách cô lập vấn đề khi nâng JDK

Nếu định dạng khác sau khi nâng JDK, kiểm tra tuần tự:

1. **Phiên bản JDK** và release notes: có nâng CLDR hoặc tzdb không?
2. **Locale thực sự được truyền**: ngôn ngữ, script, region, Unicode extensions có thay đổi không?
3. **Provider preference**: có `java.locale.providers` hay SPI/HOST được cấu hình không?
4. **Runtime image**: có đầy đủ `jdk.localedata` và locale cần dùng không?
5. **Đúng API nào thay đổi?** Số, ngày, currency, first weekday hay display name?
6. **Điều gì cần giữ ổn định?** UI copy được phép đổi theo dữ liệu mới, hay chuỗi đó là định dạng API bắt buộc cố định?

Chỉ sau khi phân biệt các tầng này mới quyết định điều chỉnh code, chọn provider khác, khai báo pattern cố định hay cập nhật kiểm thử.

## 9. Định dạng hiển thị không nên trở thành định dạng lưu trữ

### 9.1. Đầu ra dành cho con người

Ví dụ:

```java
NumberFormat displayNumber =
        NumberFormat.getNumberInstance(userLocale);

String label = displayNumber.format(amount);
```

Đây là đoạn mã **trong phương thức**, giả định `userLocale` là `Locale`, `amount` là kiểu số phù hợp. Output phục vụ giao diện người dùng, nên chấp nhận thay đổi khi quy ước địa phương được cập nhật, sau khi QA phù hợp.

### 9.2. Đầu ra dành cho hệ thống khác

Nếu một ứng dụng gửi số tiền qua REST/JSON/CSV hoặc lưu trong cơ sở dữ liệu, cần một định dạng **được giao thức quy định**, không lệ thuộc locale data. Ví dụ:

- Với ngày ISO: dùng `DateTimeFormatter.ISO_LOCAL_DATE` cho `LocalDate`.
- Với thời điểm trên trục thời gian: dùng `Instant` cùng cách serializing được chuẩn hóa, ví dụ ISO-8601 có offset/UTC phù hợp.
- Với số: dùng JSON number hoặc representation decimal có ký hiệu đã được giao thức xác định, **không lấy thẳng chuỗi `NumberFormat` hiển thị của user**.
- Với tiền tệ: lưu **currency code** cùng amount/scale và các quy tắc nghiệp vụ, không chỉ lưu ký hiệu `$`/`€` phụ thuộc locale.

`Locale.ROOT` có thể hữu ích trong vài thao tác không muốn theo locale người dùng, **nhưng đừng coi mọi formatter localized với `Locale.ROOT` là một giao thức serialization cố định**. Khi hợp đồng yêu cầu chuỗi chính xác, chọn formatter/pattern/kiểu dữ liệu được đặc tả tường minh.

### 9.3. Vì sao parsing cũng bị ảnh hưởng?

Nếu bạn lưu giá trị như một chuỗi bản địa hóa ở JDK cũ rồi parse bằng localized formatter của JDK mới, sự thay đổi trong mẫu ngày hoặc ký tự phân cách có thể làm parser không chấp nhận chuỗi cũ. Đây là một rủi ro được Oracle Migration Guide cảnh báo.

**Giải pháp:** chuyển định dạng lưu trữ sang dạng không phụ thuộc locale, hoặc bảo trì một parser tương thích ngược được định nghĩa rõ cho dữ liệu lịch sử. Không xem một chuỗi formatted dành cho UI là file format lâu dài chỉ vì nó đọc được ở thời điểm hiện tại.

## 10. Khi nào dùng `Locale` explicit và khi nào dùng default?

### 10.1. Cách gọi không truyền Locale

```java
var format = java.text.NumberFormat.getNumberInstance();
```

Kiểu gọi này dùng **default locale thuộc `Locale.Category.FORMAT`**. Nó có thể được xác định từ môi trường hoặc cấu hình runtime, vì vậy test/deployment khác nhau có thể cho output khác nhau.

### 10.2. Truyền Locale theo request

```java
var format = java.text.NumberFormat.getNumberInstance(
        java.util.Locale.forLanguageTag("vi-VN"));
```

Cách này **loại bỏ phụ thuộc vào default Locale khi chọn định danh**, nhưng **không loại bỏ phụ thuộc vào CLDR/provider**. Nói cách khác, explicit Locale là **điều kiện cần** cho hành vi dễ dự đoán, chứ chưa phải bảo đảm output byte-for-byte mãi mãi không đổi.

### 10.3. Không sửa default toàn JVM để phục vụ một người dùng

`Locale.setDefault(...)` thay đổi trạng thái chung của runtime theo phạm vi method. Nếu server xử lý song song request của nhiều người dùng với ưu tiên khác nhau, đặt default locale trước từng request có thể gây ảnh hưởng lẫn nhau.

**Cách thiết kế tốt:** mang `Locale` như một giá trị của ngữ cảnh request và truyền vào những API cần nó. Khi cần lựa chọn provider, cấu hình ở mức deployment JVM, không dùng default Locale để giả lập provider.

## 11. Chương trình Java 17+ hoàn chỉnh và kết quả kiểm thử

Đoạn dưới đây chủ động kiểm tra **hai nhóm đầu ra**:

- **Đầu ra dựa trên API có hành vi được xác định rõ**, như language tag, mã currency theo extension, `WeekFields`, formatter ISO.
- **Chuỗi định dạng bản địa hóa** phụ thuộc JDK/CLDR, dùng để quan sát nhưng **không yêu cầu mọi JDK phải in giống hoàn toàn**.

Lưu toàn bộ mã sau vào **`LocaleDataDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.time.temporal.WeekFields;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public class LocaleDataDemo {
    public static void main(String[] args) {
        Locale vietnam = Locale.forLanguageTag("vi-VN");
        Locale us = Locale.forLanguageTag("en-US");
        Locale euro = Locale.forLanguageTag("en-US-u-cu-eur");
        Locale region = Locale.forLanguageTag("en-US-u-rg-gbzzzz");
        Locale week = Locale.forLanguageTag("en-US-u-fw-mon");

        System.out.println("tag=" + vietnam.toLanguageTag());
        System.out.println("language=" + vietnam.getLanguage());
        System.out.println("country=" + vietnam.getCountry());
        System.out.println("keywordCU=" + euro.getUnicodeLocaleType("cu"));
        System.out.println("baseRegion=" + region.getCountry());
        System.out.println("currencyFromCU=" +
                Currency.getInstance(euro).getCurrencyCode());
        System.out.println("currencyFromRG=" +
                Currency.getInstance(region).getCurrencyCode());
        System.out.println("weekStart=" +
                WeekFields.of(week).getFirstDayOfWeek());

        NumberFormat usNumbers = NumberFormat.getNumberInstance(us);
        NumberFormat vnNumbers = NumberFormat.getNumberInstance(vietnam);
        String usText = usNumbers.format(1234567.5);
        String vnText = vnNumbers.format(1234567.5);
        System.out.println("usNumber=" + usText);
        System.out.println("viNumber=" + vnText);
        System.out.println("numberTextDiffers=" +
                !usText.equals(vnText));

        LocalDate date = LocalDate.of(2026, 11, 7);
        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(vietnam);
        String dateText = formatter.format(date);
        System.out.println("viDate=" + dateText);
        System.out.println("sameRuntimeDateRoundTrip=" +
                LocalDate.parse(dateText, formatter).equals(date));

        System.out.println("machineDate=" +
                DateTimeFormatter.ISO_LOCAL_DATE.format(date));
        System.out.println("formatLocaleIsExplicit=" +
                !vietnam.equals(Locale.ROOT));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 LocaleDataDemo.java
java LocaleDataDemo
```

Nếu muốn **chọn rõ nguồn CLDR** trên JDK có hỗ trợ:

```bash
java "-Djava.locale.providers=CLDR" LocaleDataDemo
```

**Stdout thực tế đã kiểm chứng trên OpenJDK Zulu 24.0.2, provider CLDR:**

```text
tag=vi-VN
language=vi
country=VN
keywordCU=eur
baseRegion=US
currencyFromCU=EUR
currencyFromRG=GBP
weekStart=MONDAY
usNumber=1,234,567.5
viNumber=1.234.567,5
numberTextDiffers=true
viDate=7 tháng 11, 2026
sameRuntimeDateRoundTrip=true
machineDate=2026-11-07
formatLocaleIsExplicit=true
```

**Quan trọng:** `usNumber`, `viNumber`, `viDate` và trong một số môi trường cả kết quả `numberTextDiffers` là **quan sát trên runtime thử nghiệm**, **không** phải chuỗi output cố định được đặc tả cho mọi CLDR version/provider. Ví dụ minh họa cho mục tiêu của bài: định dạng phụ thuộc dữ liệu JDK.

### 11.1. Phân tích kết quả

1. `tag=vi-VN`, `language=vi` và `country=VN` là các thuộc tính của `Locale`; chúng không cho biết dấu phân cách số.
2. `keywordCU=eur` là giá trị Unicode extension đã lưu. `currencyFromCU=EUR` là kết quả khi **Currency API áp dụng key `cu`**.
3. `baseRegion=US` nhưng `currencyFromRG=GBP` chứng minh **region override `rg`** được service hiểu mà không làm thay đổi `getCountry()`.
4. `weekStart=MONDAY` là kết quả `WeekFields.of` theo `fw-mon`.
5. `usNumber` và `viNumber` được tạo bởi **cùng một kiểu API** nhưng Locale khác nhau. Dấu ngăn cách thập phân và nhóm số trong output phản ánh dữ liệu locale do runtime lựa chọn.
6. `viDate` được tạo bằng `ofLocalizedDate(FormatStyle.LONG)`; người dùng nhận được cách trình bày phù hợp locale đang dùng. Chuỗi có thể đổi trong phiên bản CLDR khác.
7. `sameRuntimeDateRoundTrip=true`: formatter và parser được dùng **trong cùng runtime/provider**, với cùng cấu hình. Kết quả này không chứng minh một chuỗi đã lưu từ nhiều năm trước luôn parse được sau nâng JDK.
8. `machineDate=2026-11-07`: `ISO_LOCAL_DATE` cho định dạng ISO của một `LocalDate`, phù hợp hơn nếu hệ thống muốn chuỗi không lệ thuộc dữ liệu địa phương.
9. `formatLocaleIsExplicit=true` chỉ xác nhận ví dụ đã tạo Locale `vi-VN` cụ thể, không lấy `Locale.ROOT` làm định danh.

### 11.2. Vì sao không dùng một loạt chuỗi `assertEquals` cứng?

Mục tiêu i18n thường là **chọn đúng Locale và đáp ứng hợp đồng định dạng**, không phải khóa mọi ký tự output trong một bản CLDR. Test chỉ so toàn bộ chuỗi có thể thất bại sau bản cập nhật JDK hợp lệ dù ứng dụng không sửa.

Ngược lại, với dữ liệu API nội bộ yêu cầu định dạng cố định, test nên **cố định theo đặc tả**, ví dụ `ISO_LOCAL_DATE`. Nếu một UI bắt buộc có exact phrase/symbol, hãy đưa yêu cầu đó thành hợp đồng explicit và thử nghiệm trên đúng runtime được triển khai.

## 12. Chiến lược kiểm thử và nâng cấp JDK

### 12.1. Phân loại điều gì bắt buộc cố định

| Dữ liệu hoặc mục tiêu | Kiểm thử nên tập trung | Có nên hard-code output locale-sensitive? |
| --- | --- | --- |
| `Locale.toLanguageTag()` | Tag, language, region, extension hợp lệ | Có thể test theo hợp đồng chuẩn hóa |
| `Currency.getInstance` với `cu-eur` | Currency code được chọn đúng | Thường test code; không mặc định test mọi ký hiệu hiển thị |
| `WeekFields.of` với `fw-mon` | First day là `MONDAY` | Test hành vi theo extension |
| `NumberFormat` trên UI | Locale phù hợp, khả năng hiển thị/parse, dữ liệu hợp lệ | Chỉ khóa exact chuỗi nếu yêu cầu rõ và môi trường được kiểm soát |
| `DateTimeFormatter.ofLocalizedDate` | Hỗ trợ locale, format/parse theo thiết kế, kiểm thử tương thích | Tránh coi mẫu hiện tại là định dạng lưu trữ bất biến |
| Ngày/giờ trao đổi giữa hệ thống | ISO-8601 hoặc contract riêng | **Có**, nếu format là contract của protocol |
| Runtime image tối giản | Đủ module/locale cần hỗ trợ | Test trên image thực tế |

### 12.2. Test theo tập Locale đại diện

Với ứng dụng đa ngôn ngữ, chọn các nhóm có quy ước khác nhau:

- ngôn ngữ và vùng chính của sản phẩm, ví dụ `vi-VN`;
- vùng dùng dấu phân cách khác, ví dụ `en-US`;
- một locale khác hệ lịch hoặc chữ số nếu sản phẩm hỗ trợ;
- các Unicode extensions mà ứng dụng chấp nhận, như `fw`, `cu`, `rg` hoặc `tz`;
- trường hợp runtime thiếu một locale hoặc provider có fallback (nếu ứng dụng có custom runtime).

Kiểm thử cả **format và parse**, không chỉ format. Lưu ý rằng đối với các chuỗi UI cũ, test parse ngược **trên cùng JDK** là chưa đủ để phát hiện lỗi tương thích khi người dùng nâng cấp.

### 12.3. Chẩn đoán output có ký tự trắng “giống nhau nhưng khác nhau”

Nếu hai chuỗi nhìn gần giống nhưng `String.equals` trả `false`, có thể in Unicode code points:

```java
String text = formatter.format(value);
text.codePoints().forEach(
        codePoint -> System.out.printf("U+%04X ", codePoint));
```

Đây là đoạn mã **minh họa trong phương thức** với `formatter` và `value` đã tồn tại, phù hợp kiểu dữ liệu. Nó giúp phát hiện khác biệt `U+0020` (space), `U+00A0` (no-break space), `U+202F` (narrow no-break space), hoặc sự thay đổi dấu phân cách.

Không “sửa” output bằng cách xóa mọi Unicode whitespace một cách vô điều kiện: có thể làm sai nội dung hoặc tách từ của ngôn ngữ khác. Cần hiểu **contract mà ứng dụng muốn đảm bảo**.

### 12.4. Lưu ý về dữ liệu thời gian và tiền tệ

Ngay cả khi pattern hiển thị không đổi, dữ liệu **time zone** hoặc **currency** được cập nhật qua các bản JDK có thể ảnh hưởng kết quả. Hãy kiểm tra release notes và dữ liệu source tương ứng trước khi quy trách nhiệm cho một API.

Nếu ứng dụng liên quan kế toán, hóa đơn hoặc giao dịch lịch sử, **không suy lại dữ liệu kinh doanh từ Locale hiện tại** khi nghiệp vụ yêu cầu lưu giá trị đã chốt. Ví dụ, lưu currency code và số tiền của giao dịch, không chỉ lưu region của người dùng.

## 13. Lỗi thường gặp

**Lỗi 1 — Nghĩ `Locale.forLanguageTag("vi-VN")` chứa toàn bộ định dạng tiếng Việt.**  
Sai. Locale chứa định danh; dữ liệu thực tế đến từ các providers của runtime.

**Lỗi 2 — Nghĩ JEP 252 và JEP 314 là một.**  
Sai. JEP 252 (JDK 9) ưu tiên CLDR mặc định; JEP 314 (JDK 10) mở rộng hỗ trợ bốn Unicode locale keys trong những API liên quan.

**Lỗi 3 — Coi output một JDK là tiêu chuẩn bất biến.**  
Sai. CLDR được cập nhật. Dấu phân cách, khoảng trắng, tên hiển thị, pattern ngày và cách hiển thị tiền tệ có thể thay đổi.

**Lỗi 4 — Dùng `Locale.ROOT` và tin mọi output sẽ không thay đổi theo CLDR.**  
Sai. `ROOT` hữu ích trong một số trường hợp trung lập locale, nhưng một formatter vẫn có thể dựa vào dữ liệu/implementation. Với protocol, dùng định dạng được đặc tả rõ.

**Lỗi 5 — Dùng `COMPAT`/`JRE` để chữa formatting trên JDK 27.**  
Sai. Các provider dữ liệu legacy này đã bị loại bỏ từ JDK 23; không đề xuất làm giải pháp hiện hành.

**Lỗi 6 — Coi mọi API JDK đều đọc cùng nguồn CLDR.**  
Sai. Có các SPI/host providers và ngoại lệ theo từng service. Xem Javadoc của API và tài liệu supported locales cho bản JDK.

**Lỗi 7 — Thấy `Locale.forLanguageTag` tạo thành công rồi cho rằng image có đầy đủ locale data.**  
Sai. Runtime tùy biến có thể thiếu `jdk.localedata` hoặc thiếu locale cần thiết; `Locale` vẫn có thể biểu diễn tag.

**Lỗi 8 — Gọi `Locale.setDefault` mỗi khi có request mới.**  
Sai về thiết kế server đa người dùng: default mang tính toàn tiến trình theo phạm vi; nên truyền Locale explicit.

**Lỗi 9 — Dùng chuỗi ngày/số bản địa hóa để lưu hay trao đổi dữ liệu giữa service.**  
Sai nếu contract đòi ổn định. Chọn ISO/JSON/decimal representation theo đặc tả.

**Lỗi 10 — Cho rằng Unicode extension luôn đổi mọi dịch vụ.**  
Sai. `cu` liên quan currency, `fw` liên quan đầu tuần, `tz` liên quan một số dịch vụ thời gian. Chỉ API có hỗ trợ mới áp dụng.

**Lỗi 11 — Xem việc nâng JDK chỉ là kiểm tra biên dịch.**  
Sai. Cần kiểm thử **hành vi phụ thuộc dữ liệu**, nhất là format/parse và output hiển thị.

**Lỗi 12 — Nhầm CLDR với tzdb.**  
CLDR mô tả nhiều quy tắc bản địa hóa và tên hiển thị; tzdb điều khiển quy tắc múi giờ thực tế. Hai nguồn có thể được nâng cấp riêng.

## 14. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** Tại sao hai máy cùng chạy `NumberFormat.getInstance(Locale.forLanguageTag("vi-VN"))` có thể hiển thị khác nhau?  
**Đáp án:** Vì kết quả phụ thuộc vào dữ liệu locale và provider/runtime; phiên bản JDK, CLDR, HOST/SPI hoặc module locale data có thể khác.

**Câu 2.** JEP 252 và JEP 314 có điểm khác nhau chính nào?  
**Đáp án:** JEP 252 khiến CLDR thành nguồn mặc định từ JDK 9; JEP 314 bổ sung xử lý `cu`, `fw`, `rg`, `tz` trong những API liên quan từ JDK 10.

**Câu 3.** `Locale.forLanguageTag("en-US-u-rg-gbzzzz").getCountry()` trả gì?  
**Đáp án:** `US`. Region override `GB` được những dịch vụ phù hợp sử dụng, không thay đổi country cơ sở của object Locale.

**Câu 4.** Nếu cần đầu tuần luôn là thứ Hai, bạn chỉ cần dựa vào `WeekFields.of(userLocale)` không?  
**Đáp án:** Không nhất thiết. Có thể dùng Unicode extension `fw-mon` hoặc dựng `WeekFields.of(DayOfWeek.MONDAY, minimalDays)` theo đúng quy tắc nghiệp vụ.

**Câu 5.** `java.locale.providers=COMPAT,CLDR` có còn là hướng xử lý thích hợp cho ứng dụng dùng JDK 27 không?  
**Đáp án:** Không. Dữ liệu locale legacy `COMPAT/JRE` đã được gỡ từ JDK 23. Nên dùng CLDR hiện hành, formatter explicit hoặc SPI tùy biến nếu có yêu cầu hợp lệ.

**Câu 6.** Nếu một image `jlink` không có dữ liệu vi-VN, `Locale.forLanguageTag("vi-VN")` có bắt buộc ném exception không?  
**Đáp án:** Không. Nó tạo descriptor Locale, còn mỗi service có thể fallback/không cung cấp mức dữ liệu mong đợi. Cần kiểm thử image và API thực tế.

**Câu 7.** Có thể dùng `DateTimeFormatter.ISO_LOCAL_DATE` thay cho localized LONG date khi lưu ngày gửi qua API không?  
**Đáp án:** Có, nếu contract là ngày ISO dạng `yyyy-MM-dd`. Nó phù hợp với giao tiếp máy tính hơn một mẫu ngày theo Locale, vốn có thể đổi khi CLDR cập nhật.

**Câu 8.** Vì sao `NumberFormat.getNumberInstance(Locale.US)` không phải bảo đảm output vĩnh viễn bằng `"1,234.5"` cho mọi JDK?  
**Đáp án:** Locale cố định danh tính vùng, nhưng data/provider dùng trong formatter vẫn có thể thay đổi theo phiên bản và cấu hình. Muốn exact output, phải đặc tả và kiểm thử theo contract phù hợp.

**Câu 9.** Hai chuỗi ngày khác nhau duy nhất ở `U+0020` và `U+202F` có thể dẫn đến vấn đề gì?  
**Đáp án:** `String.equals` thất bại, regex hoặc parser kỳ vọng dấu cách cũ có thể không nhận. Cần phân biệt quy tắc format UI và format lưu trữ.

**Câu 10.** Tại sao không nên lưu mỗi `Locale` để suy lại loại tiền tệ của hóa đơn nhiều năm sau?  
**Đáp án:** Currency mapping và dữ liệu vùng có thể thay đổi, và Locale không diễn đạt quyết định kế toán của giao dịch. Lưu currency code đã chọn cùng số tiền và các metadata nghiệp vụ cần thiết.

## 15. Ghi nhớ

1. **`Locale` là định danh/ưu tiên; locale data của JDK quyết định nhiều chi tiết hiển thị.** Một Locale cố định chưa đủ để đảm bảo chuỗi format byte-for-byte mãi không đổi.
2. **JEP 252 / JDK 9** đưa CLDR thành nguồn mặc định; **JEP 314 / JDK 10** mở rộng hỗ trợ `cu`, `fw`, `rg`, `tz`.
3. **CLDR tiếp tục thay đổi theo JDK**: JDK 10 dùng CLDR 29, còn JDK 27 dùng CLDR 48.2 theo tài liệu tương ứng. Nâng JDK cần kiểm thử locale-sensitive formatting và parsing.
4. Provider `CLDR` là mặc định; `HOST` và `SPI` có phạm vi sử dụng cụ thể. **`COMPAT/JRE` đã bị gỡ từ JDK 23**, không còn là cấu hình dữ liệu locale nên đề xuất.
5. **`jdk.localedata` và cấu hình `jlink`** ảnh hưởng đến độ bao phủ dữ liệu locale trong runtime tùy biến.
6. **UI** nên format theo Locale của người dùng; **dữ liệu máy tính** nên dùng contract độc lập với mẫu hiển thị bản địa hóa, như ISO-8601/JSON và currency code.
7. **Test theo hành vi và ranh giới phiên bản**: không phụ thuộc tên tháng, dấu cách Unicode hoặc dấu phân cách của một bản CLDR nếu chúng không nằm trong hợp đồng nghiệp vụ cố định.
8. Phân biệt **CLDR** với **tzdb**, provider selection với Locale selection, và tag hợp cú pháp với dịch vụ thực sự hỗ trợ.

## Tài liệu chính thức còn áp dụng

- OpenJDK **JEP 252 — Use CLDR Locale Data by Default** (JDK 9): https://openjdk.org/jeps/252
- OpenJDK **JEP 314 — Additional Unicode Language-Tag Extensions** (JDK 10): https://openjdk.org/jeps/314
- Java SE 27 API — `Locale`: cấu trúc BCP 47, Locale data và các dịch vụ bản địa hóa: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Locale.html
- Java SE 27 API — `LocaleServiceProvider`: thứ tự providers và bảng phiên bản CLDR theo JDK: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/spi/LocaleServiceProvider.html
- Oracle JDK 27 Release Notes — **CLDR 48.2**, các thay đổi Date/Time/Number: https://www.oracle.com/java/technologies/javase/27-relnote-issues.html
- Oracle JDK 27 — Supported Locales, `CLDR`/`HOST`/`SPI` và `jdk.localedata`: https://wwwcmsapi.oracle.com/java/technologies/javase/jdk27-suported-locales.html
- Java SE 27 API — `NumberFormat` và `DateTimeFormatter`: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/NumberFormat.html ; https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Java SE 27 API — `Currency` và `WeekFields`: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Currency.html ; https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/temporal/WeekFields.html
- Oracle Java SE Migration Guide — thay đổi internationalization, CLDR và gỡ locale provider legacy từ JDK 23: https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html
- Unicode Consortium — CLDR Releases: https://cldr.unicode.org/index/downloads
