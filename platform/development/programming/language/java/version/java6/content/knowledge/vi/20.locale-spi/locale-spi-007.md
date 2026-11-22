# Locale SPI: Phạm vi nguồn dữ liệu theo cấu hình JDK hiện hành

## Mục tiêu bài học

Một chương trình Java có thể hiển thị cùng một số tiền, ngày tháng hoặc tên quốc gia theo **những cách khác nhau** dù code gọi API không đổi, nếu JDK, dữ liệu Unicode CLDR, hệ điều hành, các service providers hoặc cấu hình runtime thay đổi.

Trong Java hiện đại, nguồn dữ liệu locale không phải một danh sách cố định độc lập với môi trường. **JDK 26** cung cấp cơ chế chọn nguồn theo thuộc tính `java.locale.providers`, có các giá trị **`CLDR`**, **`SPI`**, **`HOST`**. Ngoài ra, phạm vi locale còn bị ảnh hưởng bởi các module dữ liệu trong runtime image, đặc biệt `jdk.localedata`.

Sau bài này, bạn sẽ:

- Giải thích chính xác **locale data source** khác gì với **`Locale` object**, **default locale**, **locale-sensitive service**, **`ResourceBundle` của ứng dụng** và **time-zone rules**.
- Biết vai trò của `CLDR`, `SPI`, `HOST` trong JDK hiện hành; không phụ thuộc các nguồn dữ liệu cũ đã bị loại bỏ.
- Cấu hình **thứ tự ưu tiên** qua `-Djava.locale.providers=...` ngay khi khởi động JVM và hiểu việc “có mặt trong danh sách nguồn” không đồng nghĩa nguồn đó luôn được chọn.
- Hiểu phạm vi cụ thể của `LocaleServiceProvider`, `getAvailableLocales()`, `isSupportedLocale(...)`, candidate locales và fallback.
- Phân biệt **SPI cung cấp một dịch vụ cụ thể** như `NumberFormat` với việc bổ sung mọi dữ liệu cho toàn bộ `Locale`.
- Thử một `NumberFormatProvider` thật trong Java 17+, quan sát sự khác nhau giữa mặc định, `CLDR,SPI` và `SPI,CLDR` qua **ba JVM process riêng**.
- Nhận biết cách triển khai provider trên **classpath** bằng `META-INF/services` và trên **module path** bằng `provides`, không nhầm hai cơ chế.
- Giải thích tại sao thiếu `jdk.localedata` trong runtime image tạo bằng `jlink` có thể khiến ứng dụng thiếu dữ liệu locale dù bản JDK đầy đủ hỗ trợ.
- Kiểm thử và thiết kế migration khi JDK nâng phiên bản CLDR, thay đổi pattern ngày/giờ, phân tách số hoặc dữ liệu tiền tệ.

**Special Note được áp dụng:** bài chỉ tập trung vào các kiến thức **còn áp dụng ở JDK hiện đại**. `CLDR`, `SPI`, `HOST` là các nguồn hợp lệ theo tài liệu Oracle JDK 26; những tên provider lịch sử đã bị loại khỏi JDK được nhắc **chỉ để tránh cấu hình sai**, không hướng dẫn sử dụng lại.

## 1. Hiểu đúng “nguồn dữ liệu locale” là gì?

Java có nhiều API locale-sensitive:

```java
NumberFormat number = NumberFormat.getNumberInstance(Locale.FRANCE);
DateFormat date = DateFormat.getDateInstance(DateFormat.MEDIUM, Locale.FRANCE);
DecimalFormatSymbols symbols = DecimalFormatSymbols.getInstance(Locale.FRANCE);
String name = Locale.JAPAN.getDisplayCountry(Locale.FRENCH);
```

Đây là **đoạn minh họa trong một method**, cần import `java.text.*` và `java.util.Locale`; chương trình chạy đầy đủ nằm ở các mục sau.

Những API này cần dữ liệu để biết dấu phân cách số, ký hiệu, pattern, tên quốc gia hoặc các quy tắc hiển thị liên quan. Dữ liệu đó có thể xuất phát từ:

- **`CLDR`:** dữ liệu quốc tế hóa của Unicode Common Locale Data Repository được tích hợp vào JDK.
- **`SPI`:** các implementation `LocaleServiceProvider` bổ sung do ứng dụng hoặc thư viện triển khai, được runtime tìm theo service provider mechanism.
- **`HOST`:** một số thiết lập bản địa hóa do hệ điều hành cung cấp, nếu JDK/platform hỗ trợ.

`Locale.forLanguageTag("fr-FR")` chỉ tạo một **giá trị mô tả ngôn ngữ/khu vực**. Nó không tải các file CLDR, không kiểm tra provider, và **không chứng minh** mọi loại formatter của runtime đều có dữ liệu riêng cho `fr-FR`.

Cần tách bốn câu hỏi:

| Câu hỏi | Cơ chế |
| --- | --- |
| Người dùng yêu cầu locale nào? | `Locale`, BCP 47 language tags, locale mặc định hoặc locale explicit |
| Runtime tìm dữ liệu của dịch vụ nào? | Factory `NumberFormat`, `DateFormat`, `Locale` display names, v.v. |
| Các nguồn được tra theo thứ tự nào? | `java.locale.providers`: `CLDR`, `SPI`, `HOST` |
| Runtime image thật sự chứa dữ liệu nào? | Thành phần JDK/modules như `java.base`, `jdk.localedata` và các provider được đóng gói |

**Một lỗi thường gặp:** chương trình tạo được `new Locale...` hoặc `Locale.forLanguageTag(...)` rồi cho rằng JDK chắc chắn có đủ dữ liệu format cho locale đó. Khi thiếu dữ liệu, runtime có thể sử dụng candidate locale khác, parent hoặc root theo hợp đồng, chứ không nhất thiết báo lỗi.

## 2. Ba nguồn dữ liệu của JDK hiện hành

Theo Javadoc `java.util.spi.LocaleServiceProvider` và trang **JDK 26 Supported Locales**, JDK reference implementation hiện hành hỗ trợ ba nguồn sau:

| Tên | Dữ liệu đến từ đâu? | Phạm vi và giới hạn quan trọng |
| --- | --- | --- |
| **`CLDR`** | Unicode Common Locale Data Repository, tích hợp trong bản JDK | Nguồn **mặc định**. Phiên bản dữ liệu theo JDK; JDK 26 dùng CLDR 48. Không đồng nghĩa mọi locale/service đều có dữ liệu từ CLDR. |
| **`SPI`** | Provider classes của ứng dụng/thư viện, trong `java.text.spi` và `java.util.spi` | Chỉ cung cấp **những dịch vụ và locales mà provider triển khai**; cần có service registration và có `SPI` trong provider order. |
| **`HOST`** | Các thiết lập locale của hệ điều hành mà JDK tích hợp | Phụ thuộc **platform và JDK implementation**, chủ yếu liên quan cấu hình mặc định của người dùng, date/time/number/currency. Không phải cơ chế nạp mọi locale từ mọi hệ điều hành. |

Không nên tưởng “CLDR” là tên một class Java được nạp bằng `ServiceLoader` theo code ứng dụng. CLDR là nguồn dữ liệu tích hợp sẵn theo JDK distribution. Ngược lại, SPI yêu cầu **implementation và registration cụ thể**.

### 2.1. CLDR là mặc định

Ở JDK 26, khi không đặt `java.locale.providers`, hành vi mặc định **tương đương**:

```text
java.locale.providers=CLDR
```

Java chuyển sang dùng CLDR theo mặc định từ JDK 9; **JDK 26 dùng CLDR 48**. Phiên bản khác nhau có thể thay đổi patterns, symbols và locale coverage. Ví dụ số có thể đổi ký tự ngăn cách hàng nghìn; tháng/ngày có thể thay đổi cách viết và cách parse.

**Không khẳng định một output bản địa hóa là bất biến mãi mãi qua các bản JDK.** Với API lựa chọn format theo locale, dữ liệu là một phần của runtime và có vòng đời cập nhật riêng.

Theo tài liệu JDK 26, dữ liệu CLDR cho `BreakIterator` và `Collator` **không được JDK áp dụng theo cùng cách với các dữ liệu CLDR khác**. Vì vậy không nên diễn giải “CLDR default” thành “mọi locale service, kể cả segmentation/collation, đều dùng toàn bộ dữ liệu CLDR”. Xem Javadoc của từng API và tài liệu JDK distribution khi kết quả của hai dịch vụ này quan trọng.

### 2.2. SPI là bổ sung có phạm vi, không phải một bộ locale database tổng quát

`SPI` là tập các implementation cho từng lớp service cụ thể, ví dụ `NumberFormatProvider` hoặc `LocaleNameProvider`. Một `NumberFormatProvider` tùy chỉnh **không tự động** thay date patterns, timezone names hay country names.

Khi `SPI` nằm trước `CLDR`, một provider tự tạo có thể được chọn cho locale/service mà nó nhận hỗ trợ. Khi `CLDR` trước `SPI`, dữ liệu CLDR có thể thắng cho dịch vụ/locale mà CLDR hỗ trợ; SPI vẫn có thể được dùng khi CLDR không cung cấp dữ liệu tương ứng.

Vì vậy phải nêu **cả ba điều kiện**: (1) loại dịch vụ, (2) locale được yêu cầu, (3) provider order.

### 2.3. HOST có tính nền tảng, không phải nguồn đa locale phổ quát

Theo Oracle JDK 26, `HOST` phản ánh những customization trong settings của hệ điều hành cho default locales (`Locale.Category.FORMAT` và/hoặc `DISPLAY`). Oracle JDK 26 cung cấp HOST trên **Windows và macOS**; trên JDK/runtime image khác khả năng hỗ trợ có thể khác.

Ví dụ cách cấu hình:

```bash
java -Djava.locale.providers=HOST,CLDR -cp out demo.app.ProviderProbe false false
```

Dòng trên chỉ là **hình thức cấu hình để minh họa thứ tự HOST rồi CLDR**; **không phải một ca kiểm thử có stdout cố định** từ bài này, vì HOST phụ thuộc hệ điều hành và có thể cho hành vi khác với phép thử custom SPI. Bài kiểm thử lặp lại có kiểm soát được thực hiện với CLDR/SPI ở phần thực hành.

Không dùng `HOST` để kỳ vọng có thể yêu cầu mọi locale theo tùy chọn OS, hoặc để thay thế yêu cầu đóng gói `jdk.localedata`.

## 3. Cấu hình `java.locale.providers` chính xác

`java.locale.providers` là **system property** xác định thứ tự ưu tiên tìm dịch vụ locale. Giá trị là các tên provider **ngăn cách bằng dấu phẩy**.

Ví dụ:

```text
CLDR
SPI,CLDR
CLDR,SPI
HOST,CLDR
HOST,SPI,CLDR
```

Ý nghĩa điển hình:

- `CLDR`: dùng built-in CLDR; tương đương mặc định của JDK 26.
- `SPI,CLDR`: ưu tiên provider của ứng dụng khi có service cho locale đó, nếu không thì dùng CLDR.
- `CLDR,SPI`: ưu tiên CLDR, nhưng cho phép provider bổ sung những phần CLDR không đáp ứng.
- `HOST,CLDR`: ưu tiên các dịch vụ/locale có HOST support khi phù hợp, sau đó về CLDR.
- `HOST,SPI,CLDR`: kết hợp ba nguồn, với thứ tự có chủ ý.

**Không đặt `SPI` một mình một cách vô thức** nếu sản phẩm còn cần nguồn dữ liệu CLDR dự phòng. Việc không liệt kê CLDR có thể làm giảm dữ liệu dựa trên nguồn mặc định cho các dịch vụ mà custom provider không bao phủ.

### 3.1. Đặt tham số ngay khi chạy JVM

Bash:

```bash
java -Djava.locale.providers=SPI,CLDR -cp out demo.app.ProviderProbe true true
```

PowerShell:

```powershell
java '-Djava.locale.providers=SPI,CLDR' -cp out demo.app.ProviderProbe true true
```

**Đặt `-D...` trước class name hoặc `-jar`/`--module`** để launcher hiểu nó là system property. Với PowerShell, nên **quote toàn bộ argument** có dấu phẩy như ví dụ: nếu không, PowerShell có thể tách/parsing argument theo cách không đúng ý định.

`java.locale.providers` được đọc và **cache khi cơ sở locale provider của runtime khởi tạo**. Do đó không nên viết:

```java
System.setProperty("java.locale.providers", "SPI,CLDR");
// Sau khi locale services đã khởi tạo, không bảo đảm thay được provider order.
```

Việc set property từ code sau khi app đang chạy có thể **không có hiệu lực**. Cách kiểm thử đúng là **khởi động các JVM processes riêng**, mỗi process với một `-Djava.locale.providers=...` nhất quán.

### 3.2. Property không phải công tắc thay đổi `Locale.getDefault()`

Nguồn dữ liệu quyết định **bộ dữ liệu cho dịch vụ**, khác với việc chọn **locale nào**.

```java
Locale.forLanguageTag("vi-VN");            // Tạo Locale
Locale.getDefault(Locale.Category.FORMAT); // Locale default cho formatter
Locale.getDefault(Locale.Category.DISPLAY);// Locale default để hiển thị tên
```

Các dòng trên là các lời gọi/biểu thức minh họa trong method Java.

- `Locale.getDefault(Locale.Category.FORMAT)` liên quan mặc định cho formatting khi API không nhận `Locale` explicit.
- `Locale.getDefault(Locale.Category.DISPLAY)` liên quan hiển thị tên locale/country/language khi API không nhận locale hiển thị.
- `java.locale.providers` không đồng nghĩa một lệnh `Locale.setDefault(Locale.FRANCE)` và không đồng nghĩa `-Duser.language`/`-Duser.country`.
- Khi truyền `Locale.FRANCE` tường minh vào `NumberFormat.getNumberInstance`, chương trình yêu cầu locale đó, không tự thay bằng default locale chỉ vì property provider order có giá trị khác.

Với báo cáo, API công khai, parsing/formatting dữ liệu trao đổi, **nên truyền Locale tường minh** thay vì để mặc định theo user/máy chủ làm thay đổi kết quả giữa môi trường.

## 4. Phạm vi áp dụng theo từng loại dịch vụ

`LocaleServiceProvider` là lớp cơ sở cho nhiều SPI cụ thể. Javadoc Java SE 26 liệt kê những nhóm như:

| Service provider | Phạm vi |
| --- | --- |
| `java.text.spi.NumberFormatProvider` | Cung cấp các `NumberFormat` cho số, số nguyên, tiền tệ và phần trăm |
| `java.text.spi.DecimalFormatSymbolsProvider` | Ký hiệu phân cách và các symbols dùng cho decimal formatting |
| `java.text.spi.DateFormatProvider` | `DateFormat` cho ngày/giờ theo locale |
| `java.text.spi.DateFormatSymbolsProvider` | Tên tháng, ngày và symbols liên quan tới `DateFormat` |
| `java.text.spi.CollatorProvider` | Cung cấp `Collator` theo locale |
| `java.text.spi.BreakIteratorProvider` | Cung cấp `BreakIterator` theo locale |
| `java.util.spi.LocaleNameProvider` | Tên language/country/variant/script bản địa hóa |
| `java.util.spi.CurrencyNameProvider` | Tên/ký hiệu currency theo locale |
| `java.util.spi.TimeZoneNameProvider` | Tên múi giờ để hiển thị |
| `java.util.spi.CalendarDataProvider` | Một số dữ liệu calendar theo locale, chẳng hạn ngày đầu tuần |
| `java.util.spi.CalendarNameProvider` | Tên calendar fields theo locale |

Bảng mô tả **API đang tồn tại**, không phải lời khẳng định Java sẽ sử dụng mọi provider cho mọi API trong thư viện. Đọc contract cụ thể của factory cần sử dụng. Ví dụ một `NumberFormatProvider` không phải `DateFormatSymbolsProvider`, và việc service cung cấp tên quốc gia không có nghĩa nó kiểm soát các quy tắc số.

### 4.1. Không đánh đồng `java.util.spi` và `ResourceBundle`

`ResourceBundle` là cơ chế tìm **bundle tài nguyên ứng dụng** theo baseName/locale. Nó có các API `ResourceBundleProvider`, `ResourceBundleControlProvider` với hợp đồng riêng. Chúng **không đồng nhất** với danh sách các nguồn dữ liệu `CLDR/SPI/HOST` cho locale services.

Một application bundle như:

```properties
title=Hello
button.save=Save
```

không tự trở thành provider của `NumberFormat` khi chỉ đặt trong classpath. Ngược lại, đặt `-Djava.locale.providers=SPI,CLDR` cũng không tự động tạo các message bundle thiếu trong app.

**Không suy ra:** tất cả những gì có chữ “locale” hoặc “provider” trong tên API đều được cấu hình theo cùng một cách.

### 4.2. Dữ liệu biểu diễn tên múi giờ không phải quy tắc chuyển đổi thời gian

`TimeZoneNameProvider` liên quan **display names** của múi giờ. Tính toán UTC offset, daylight-saving transitions và timezone rules của `java.time` liên quan dữ liệu vùng thời gian (tzdb) và API `ZoneRulesProvider`.

Vì vậy đổi provider cho tên múi giờ không đồng nghĩa đổi toàn bộ quy tắc thời gian. Nếu nghiệp vụ tính đúng thời điểm, cần quản lý **IANA zone IDs, tzdb version và cách parse/format** riêng.

## 5. Provider order không đồng nghĩa provider coverage

Câu hỏi hay gặp: “Nếu cấu hình `CLDR,SPI` thì liệu SPI có bị vô hiệu hóa hoàn toàn?”

**Không.** Một provider có thể chỉ phục vụ một locale mà CLDR chưa có dữ liệu cho dịch vụ đó. Ví dụ giả lập provider `NumberFormat` cho:

```java
Locale.US
Locale.forLanguageTag("zz-ZZ")
```

Trong demo, `zz-ZZ` là **locale giả để kiểm thử**, không đại diện cho một ngôn ngữ/khu vực thực cần đưa vào sản phẩm. Nó được chọn để dễ quan sát việc provider bổ sung locale ngoài phạm vi CLDR thông thường.

Khi dùng `CLDR,SPI`:

- Đối với **`Locale.US`**, CLDR có dữ liệu `NumberFormat`, vì thế kết quả mặc định được ưu tiên; dấu `SPI:` của provider không xuất hiện.
- Đối với **`zz-ZZ`**, CLDR không có dữ liệu cụ thể, nên SPI được chọn nếu đã đăng ký và cho biết có hỗ trợ.
- `NumberFormat.getAvailableLocales()` có thể bao gồm `zz-ZZ`, cho thấy **service này** có dữ liệu được bổ sung từ SPI.

Khi dùng `SPI,CLDR`, provider cùng lúc có thể thắng cho cả `Locale.US` và `zz-ZZ`. Đó là **thay đổi ưu tiên**, không phải việc tạo thêm hay bớt mọi `Locale` của Java.

**Đặc biệt:** Chỉ gọi `Locale.getAvailableLocales()` hoặc `NumberFormat.getAvailableLocales()` để “liệt kê tất cả locale” không đủ để biết **provider nào đang thắng** hoặc **mức độ dữ liệu đã đầy đủ**. Những phương thức này thể hiện phạm vi hỗ trợ, không phải hệ thống provenance chi tiết cho từng field.

## 6. `getAvailableLocales`, `isSupportedLocale` và fallback

Mỗi `LocaleServiceProvider` phải triển khai:

```java
@Override
public Locale[] getAvailableLocales() {
    return new Locale[] {Locale.US};
}
```

`getAvailableLocales()` nêu tập locales mà provider có thể đáp ứng cho **dịch vụ cụ thể đó**. Không nên kê một locale chỉ vì mong thấy nó trong danh sách nếu implementation không có dữ liệu thích hợp.

`isSupportedLocale(Locale locale)` có default implementation: xét các locale đã khai báo, **bỏ qua extensions** khi so sánh. Nếu hỗ trợ Unicode locale extensions như numbering system `u-nu-thai` có ý nghĩa với implementation của bạn, hãy override `isSupportedLocale` đúng contract.

### 6.1. Candidate locale search

Nếu dịch vụ không đáp ứng một locale yêu cầu, runtime có thể thử các candidate locales gần hơn theo quy tắc tương tự `ResourceBundle.Control.getCandidateLocales`:

```text
Ví dụ ý tưởng: fr-CA -> fr -> ROOT
```

Đây là biểu diễn **khái quát**, không phải danh sách chính xác cho mọi script/variant/Unicode extension; algorithm thực tế được mô tả trong Javadoc. `Locale.ROOT` phải được runtime hỗ trợ để quá trình tìm kiếm kết thúc.

**Một điểm tinh tế:** Theo `LocaleServiceProvider`, khi một ứng viên locale được dùng để xác định provider có thể phục vụ yêu cầu, method tạo object/tên vẫn có thể được gọi với **requested Locale ban đầu**, kể cả extensions. Vì thế provider cần hiểu đúng contract; không đơn giản giả định nó luôn chỉ nhận đúng locale đã ghi trong danh sách.

### 6.2. Trường hợp các provider trả `null`

Provider của **localized names** có thể trả `null` cho một số tên mà nó không có, dù locale tương ứng nằm trong `getAvailableLocales()`. Runtime tiếp tục tìm kiếm tên theo quy tắc của dịch vụ. Đừng biến quy tắc này thành phát biểu rằng mọi provider factory cho số/ngày được phép trả `null` mà không gây ảnh hưởng — hãy đọc return contract của từng SPI.

### 6.3. Các locale có extensions

`Locale.forLanguageTag("en-US-u-nu-thai")` có Unicode extension `nu` chỉ numbering system. Không phải mọi provider hoặc JDK đều hỗ trợ mọi giá trị extension. Lựa chọn provider và ý nghĩa thực sự còn phụ thuộc phạm vi service, isSupportedLocale và dữ liệu sẵn có.

Nên có tests cho:

- Locale không có extensions, ví dụ `en-US`.
- Locale có numbering/currency/region extensions mà ứng dụng dùng.
- Locale không được provider hỗ trợ.
- Locale có variant hoặc script.
- Locale root và parent fallback.
- Một provider cung cấp localized name thiếu một số tên cụ thể.

## 7. Demo Java 17+ thực tế: NumberFormatProvider tùy chỉnh

Đây là một project **classpath/unnamed module** tự xây `NumberFormatProvider`. Cùng một mã `NumberFormat.getNumberInstance(Locale.US)` sẽ có kết quả khác nhau khi đổi `java.locale.providers` ở **JVM startup**.

Provider chủ động thêm chuỗi `SPI:` vào kết quả để chứng minh **đúng nguồn dữ liệu nào đã được chọn**. Trong sản phẩm thật, provider định dạng số phải đáp ứng format/parse/currency/percent đúng ngữ nghĩa; dấu prefix đặc biệt này chỉ dùng cho test.

### 7.1. Cây thư mục

```text
locale-spi-demo/
├── src/
│   └── demo/
│       ├── spi/
│       │   └── DemoNumberProvider.java
│       └── app/
│           └── ProviderProbe.java
├── services/
│   └── META-INF/
│       └── services/
│           └── java.text.spi.NumberFormatProvider
└── out/                         (tạo khi build)
```

### 7.2. Provider — `src/demo/spi/DemoNumberProvider.java`

```java
package demo.spi;

import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Locale;

public final class DemoNumberProvider extends NumberFormatProvider {
    private static final Locale CUSTOM = Locale.forLanguageTag("zz-ZZ");

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] {Locale.US, CUSTOM};
    }

    private static NumberFormat newFormat(Locale locale) {
        if (!(locale.equals(Locale.US) || locale.equals(CUSTOM))) {
            throw new IllegalArgumentException("Unsupported locale: " + locale);
        }
        return new DecimalFormat("'SPI:'0.0",
                DecimalFormatSymbols.getInstance(Locale.ROOT));
    }

    @Override
    public NumberFormat getNumberInstance(Locale locale) { return newFormat(locale); }

    @Override
    public NumberFormat getIntegerInstance(Locale locale) { return newFormat(locale); }

    @Override
    public NumberFormat getCurrencyInstance(Locale locale) { return newFormat(locale); }

    @Override
    public NumberFormat getPercentInstance(Locale locale) { return newFormat(locale); }
}
```

### Phân tích provider

- Kế thừa `NumberFormatProvider`, một subtype của `LocaleServiceProvider`.
- `getAvailableLocales()` công bố `Locale.US` và `zz-ZZ` cho **NumberFormat service**.
- Bốn factory methods được override vì `NumberFormatProvider` yêu cầu chúng.
- `newFormat` dùng `DecimalFormat` và `DecimalFormatSymbols.getInstance(Locale.ROOT)` để tạo output có prefix `SPI:`, không phụ thuộc dấu phân cách số của host locale.
- Bởi vì provider chỉ nhận chính xác `Locale.US` và `zz-ZZ` trong demo, những locale khác sẽ bị từ chối bằng `IllegalArgumentException` nếu factory này được gọi không đúng contract. Trong provider production, nên implement `isSupportedLocale` và factory nhất quán với ngữ nghĩa fallback/candidate locales và extensions thực tế.
- Dạng `'SPI:'0.0` có `'...'` để escape dấu hai chấm và text thành literal của `DecimalFormat`; phần `0.0` yêu cầu một chữ số thập phân. Không nên dùng prefix `SPI:` trong formatter để hiển thị tiền tệ thật.

**Chủ ý giới hạn:** Demo chỉ nhấn mạnh **lựa chọn nguồn dữ liệu**. `getCurrencyInstance` và `getPercentInstance` trả cùng pattern đơn giản, nên **không phải** formatter đúng nghiệp vụ tiền tệ hoặc tỷ lệ. Khi triển khai provider thật, các methods phải cung cấp hành vi phù hợp với loại format và locale; không sao chép mẫu test này vào UI tài chính.

### 7.3. Service configuration file

File **`services/META-INF/services/java.text.spi.NumberFormatProvider`** chỉ chứa dòng:

```text
demo.spi.DemoNumberProvider
```

Đây là quy tắc `ServiceLoader` của classpath:

- **Tên file** đúng fully qualified service type: `java.text.spi.NumberFormatProvider`.
- **Nội dung** là fully qualified implementation class: `demo.spi.DemoNumberProvider`.
- Khi chạy, file phải nằm ở **`out/META-INF/services/java.text.spi.NumberFormatProvider`**, cùng classpath với `.class`.
- Một JAR classpath tương đương cũng có thể chứa service file ở cùng đường dẫn trong JAR.
- Chỉ có file Java class mà không có service configuration file là **chưa đủ để runtime tự phát hiện** provider này trên classpath.

### 7.4. Chương trình kiểm chứng — `src/demo/app/ProviderProbe.java`

```java
package demo.app;

import java.text.NumberFormat;
import java.util.Arrays;
import java.util.Locale;

public final class ProviderProbe {
    private static void check(String label, boolean value) {
        if (!value) throw new AssertionError(label);
        System.out.println(label + "=true");
    }

    public static void main(String[] args) {
        boolean expectSpiUs = Boolean.parseBoolean(args[0]);
        boolean expectSpiVisible = Boolean.parseBoolean(args[1]);
        Locale custom = Locale.forLanguageTag("zz-ZZ");
        String us = NumberFormat.getNumberInstance(Locale.US).format(1234.5);
        check("spiForUs=" + expectSpiUs, us.startsWith("SPI:") == expectSpiUs);
        check("usTag", Locale.US.toLanguageTag().equals("en-US"));
        check("customVisible=" + expectSpiVisible,
                Arrays.asList(NumberFormat.getAvailableLocales())
                    .contains(custom) == expectSpiVisible);
        if (expectSpiVisible) {
            check("customUsesSpi",
                    NumberFormat.getNumberInstance(custom).format(12.5)
                            .equals("SPI:12.5"));
        }
        if (expectSpiUs) {
            check("usExactValue", us.equals("SPI:1234.5"));
        }
    }
}
```

### Vì sao `ProviderProbe` có hai arguments?

- `args[0]`: kỳ vọng SPI có **thắng cho `Locale.US`** hay không.
- `args[1]`: kỳ vọng locale riêng `zz-ZZ` **xuất hiện trong tập locales của NumberFormat** hay không.

Đây là **hai phép quan sát độc lập**. Khi ưu tiên `CLDR,SPI`, CLDR vẫn có thể định dạng `US`, nhưng `zz-ZZ` được bổ sung bởi SPI và xuất hiện trong `NumberFormat.getAvailableLocales`.

`check(...)` ném `AssertionError` nếu một điều kiện không đạt; stdout không được in “PASS” vô điều kiện. Mỗi lần chạy JVM riêng kiểm tra một cấu hình provider order từ lúc startup.

### 7.5. Chạy trên Windows PowerShell

Đứng ở thư mục `locale-spi-demo`:

```powershell
New-Item -ItemType Directory -Force out/META-INF/services | Out-Null

javac --release 17 -d out src/demo/spi/DemoNumberProvider.java src/demo/app/ProviderProbe.java

Copy-Item services/META-INF/services/java.text.spi.NumberFormatProvider out/META-INF/services/java.text.spi.NumberFormatProvider

# Mặc định: tương đương CLDR
java -cp out demo.app.ProviderProbe false false

# CLDR ưu tiên, vẫn tải SPI cho locale CLDR thiếu
java '-Djava.locale.providers=CLDR,SPI' -cp out demo.app.ProviderProbe false true

# SPI ưu tiên trước CLDR
java '-Djava.locale.providers=SPI,CLDR' -cp out demo.app.ProviderProbe true true
```

**PowerShell note:** Đặt `'-Djava.locale.providers=CLDR,SPI'` trong dấu nháy để PowerShell gửi đúng **một đối số JVM** có dấu phẩy. Khi chạy trong `cmd.exe` hoặc Bash, quy tắc quoting khác; xem phần tiếp theo.

### 7.6. Chạy trên Linux/macOS Bash

```bash
mkdir -p out/META-INF/services

javac --release 17 -d out \
  src/demo/spi/DemoNumberProvider.java \
  src/demo/app/ProviderProbe.java

cp services/META-INF/services/java.text.spi.NumberFormatProvider \
   out/META-INF/services/java.text.spi.NumberFormatProvider

java -cp out demo.app.ProviderProbe false false
java -Djava.locale.providers=CLDR,SPI -cp out demo.app.ProviderProbe false true
java -Djava.locale.providers=SPI,CLDR -cp out demo.app.ProviderProbe true true
```

### 7.7. Kết quả chính xác đã chạy trên OpenJDK 24

**Process 1 — không đặt property (CLDR mặc định):**

```text
spiForUs=false=true
usTag=true
customVisible=false=true
```

**Process 2 — `CLDR,SPI`:**

```text
spiForUs=false=true
usTag=true
customVisible=true=true
customUsesSpi=true
```

**Process 3 — `SPI,CLDR`:**

```text
spiForUs=true=true
usTag=true
customVisible=true=true
customUsesSpi=true
usExactValue=true
```

**Tổng cộng 12 assertions đã chạy và đạt** trên Windows OpenJDK 24, biên dịch bằng `javac --release 17`. Chúng không chỉ mô tả lý thuyết: provider class, SPI metadata, lookup và dữ liệu thực sự đã được kiểm tra trong ba JVM processes.

### 7.8. Phân tích kết quả

**Process 1: default**

`Locale.US` dùng formatter JDK thay vì provider demo; locale `zz-ZZ` không xuất hiện trong `NumberFormat.getAvailableLocales()` vì `SPI` chưa được đưa vào provider order.

**Process 2: CLDR,SPI**

CLDR tiếp tục thắng cho `en-US`. Tuy nhiên `zz-ZZ` được nhận diện từ SPI, nên `customVisible=true=true` và `customUsesSpi=true`. **Đây là bằng chứng coverage và priority là hai trục khác nhau.**

**Process 3: SPI,CLDR**

Provider được ưu tiên và định dạng `Locale.US` thành chính xác `SPI:1234.5`. Nó đồng thời xử lý locale giả `zz-ZZ`. Nếu SPI không đáp ứng một locale/service, CLDR vẫn là nguồn tiếp theo.

**Đừng dùng việc output khác nhau như lỗi “ngẫu nhiên”.** Nó là kết quả của cấu hình có chủ đích. Khi so sánh môi trường staging/production, ghi rõ property startup, JDK build và nơi deploy service provider.

### 7.9. Vì sao demo không dùng ngày tháng hoặc format của hệ điều hành để assert?

Output ngày/giờ và dấu ngăn cách có thể thay đổi theo CLDR version, timezone, default locale, JDK distribution hoặc HOST settings. Demo cố tình trả một chuỗi có `SPI:` và hai con số thập phân kiểm soát được, tránh các assertions mong manh dựa vào một mẫu bản địa hóa có thể đổi theo release.

Trong CI, có thể snapshot dữ liệu CLDR theo **JDK version được khóa**, nhưng phải biết rằng snapshot là kỳ vọng của toolchain cụ thể, không phải luật bất biến của Java API.

## 8. SPI khi đóng gói trong named module

Service provider không bắt buộc phải nằm trên classpath. `LocaleServiceProvider` Javadoc cho phép deployment trên **application module path**, với `provides` trong `module-info.java`.

Ví dụ tối giản, module provider:

```java
module demo.number.spi {
    provides java.text.spi.NumberFormatProvider
            with demo.spi.DemoNumberProvider;
}
```

Đặt `DemoNumberProvider` tại `src/demo.number.spi/demo/spi/DemoNumberProvider.java` và biên dịch cùng `module-info.java`. Không dùng `META-INF/services` thay cho `provides` trong một explicit named module.

Consumer mẫu:

```java
module demo.number.app {
    uses java.text.spi.NumberFormatProvider;
}
```

Một `Main` trong `demo.number.app` gọi:

```java
String text = NumberFormat.getNumberInstance(Locale.US).format(12.5);
boolean fromSpi = text.equals("SPI:12.5");
```

Đây là **đoạn dùng trong method**, cần imports `java.text.NumberFormat` và `java.util.Locale`. Mục đích là xác minh cùng loại provider được tìm từ module graph, không cần code consumer trực tiếp new implementation.

### Ví dụ named module ngắn đã được kiểm chứng

Một fixture độc lập khác với hai named modules được kiểm thử trên JDK 24:

- `demo.number.spi` triển khai `NumberFormatProvider` và khai báo `provides`.
- `demo.number.app` khai báo `uses`, gọi `NumberFormat.getNumberInstance(Locale.US)`.
- Launcher có `-Djava.locale.providers=SPI,CLDR` và `--module-path`.

Lệnh mẫu với module source tree phù hợp:

```bash
mkdir -p mods
javac --release 17 --module-source-path src -d mods \
  $(find src -name '*.java')
java -Djava.locale.providers=SPI,CLDR \
  --module-path mods \
  --module demo.number.app/demo.app.Main
```

Trong fixture đã biên dịch, `Main` có một assertion kiểm tra mình thuộc named module và kết quả formatter là `SPI:12.5`, sau đó in:

```text
namedSpiProvider=true
```

**Giới hạn của đoạn phụ:** Muốn chạy đúng lệnh này, phải có file `demo.app.Main` và module source tree được thiết lập như đã mô tả; đây là **mẫu ghép module**, không phải thay thế trực tiếp project classpath ở mục 7. Cấu trúc classpath đầy đủ ở mục 7 mới là chương trình từ đầu đến cuối của bài.

**Không quên `-Djava.locale.providers=SPI,CLDR`:** có module provider và khai báo `provides` chưa có nghĩa mặc định CLDR của JDK 26 sẽ tự ưu tiên SPI cho `Locale.US`.

## 9. Phạm vi dữ liệu thực sự phụ thuộc vào runtime image

Chọn `CLDR` không có nghĩa **mọi dữ liệu của bản JDK đầy đủ** đều tồn tại trong một runtime image tối giản.

Theo Oracle JDK 26 Supported Locales:

- `java.base` chứa dữ liệu locale **US English và các parent locales**, bao gồm `Locale.ROOT`.
- Những locale data khác chủ yếu nằm ở module **`jdk.localedata`**.
- JDK đầy đủ thông thường có đầy đủ các locale dữ liệu được distribution hỗ trợ, nhưng **runtime image tạo bằng `jlink`** có thể chỉ gồm một phần.

Ví dụ có thể dùng:

```bash
java --list-modules
```

để quan sát danh sách modules của runtime. Nếu dùng custom runtime image, kiểm tra có `jdk.localedata` hay không; chỉ xem `java.locale.providers` chưa đủ.

### `jlink --include-locales`

`jlink` hỗ trợ `--include-locales` để giữ một subset dữ liệu CLDR khi tạo runtime image:

```bash
jlink --add-modules java.base,jdk.localedata \
  --include-locales en,ja,*-IN \
  --output runtime-with-locales
```

Đây là **ví dụ lựa chọn tập dữ liệu**, mang tính hướng dẫn. Khi sử dụng trong dự án, các root modules và đường module path phải phù hợp với ứng dụng; có thể cần thêm `--module-path` và lựa chọn khác. `--include-locales` không có nghĩa mọi service ngoài CLDR đều được cung cấp cho các locale trong danh sách.

**Một bẫy deployment:** bản dev chạy đầy đủ JDK và kiểm thử locale `vi-VN` thành công, còn Docker/custom image thiếu `jdk.localedata` hoặc đã lọc bỏ Vietnamese data. Code Java và `-Djava.locale.providers=CLDR` vẫn giống nhau, nhưng runtime có phạm vi dữ liệu khác.

### Đừng dùng `Locale.forLanguageTag` làm test có data

`Locale.forLanguageTag("vi-VN")` chỉ tạo metadata locale; vẫn thành công khi runtime image thiếu dữ liệu định dạng Vietnamese. Hãy thực sự gọi API liên quan như `NumberFormat.getNumberInstance(locale)` hoặc `DateTimeFormatter` và so sánh hành vi với runtime image mục tiêu theo kỳ vọng được xác định.

## 10. CLDR version là một phần môi trường

Javadoc Java SE 26 nêu dữ liệu CLDR gắn với bản JDK. Ví dụ:

| JDK | CLDR data version theo tài liệu API |
| --- | --- |
| JDK 17 | CLDR 39 |
| JDK 21 | CLDR 43 |
| JDK 23 | CLDR 45 |
| JDK 25 | CLDR 47 |
| JDK 26 | CLDR 48 |

**Không biến bảng này thành ràng buộc runtime cho mọi bản phân phối bên thứ ba:** vendor/custom image có thể đóng gói khác hoặc cung cấp bản vá. Hãy xác minh môi trường thực tế khi yêu cầu byte-for-byte stable output.

Dữ liệu locale có thể thay đổi mà không cần Java source code thay đổi:

- Ngăn cách hàng nghìn/thập phân có thể cập nhật theo quy tắc ngôn ngữ/khu vực.
- Date/time patterns và ký hiệu tháng, weekdays có thể được sửa.
- Tên nước, đơn vị tiền, ký hiệu và translation có thể thay đổi.
- Unicode locale extensions làm output khác theo yêu cầu numbering system hoặc region override.
- Kết quả parse một chuỗi ngày/giờ cũ có thể không còn phù hợp khi pattern mặc định thay đổi.

Vì vậy nếu sản phẩm truyền giá trị định dạng qua API giữa các hệ thống, **đừng dùng localized display text làm wire format**. Dùng ISO date/time (khi phù hợp), numeric machine format và schema rõ ràng; chỉ format localized tại ranh giới hiển thị.

## 11. Format, parse và dữ liệu tiền tệ trong ứng dụng

### 11.1. Định dạng số cho người dùng

`NumberFormat.getNumberInstance(locale)` phản ánh dữ liệu của nguồn được chọn. Nếu đổi `CLDR` sang `SPI` cho `Locale.US` như demo, output thay đổi hoàn toàn.

Dữ liệu format bao gồm nhiều khía cạnh hơn một dấu phẩy: pattern, ký tự nhóm, chữ số của numbering system, percent rules, currency display style, v.v. Một provider thực sự phải triển khai đầy đủ theo nghiệp vụ.

### 11.2. `DateTimeFormatter` và `java.time`

Đối với lập trình Java 17+, ưu tiên API `java.time` khi xử lý ngày/giờ mới. `DateTimeFormatter` cũng có cách hiển thị phụ thuộc locale và CLDR data.

Ví dụ minh họa:

```java
Locale vi = Locale.forLanguageTag("vi-VN");
var formatter = java.time.format.DateTimeFormatter
        .ofLocalizedDate(java.time.format.FormatStyle.MEDIUM)
        .withLocale(vi);
String displayed = formatter.format(java.time.LocalDate.of(2026, 11, 5));
```

Đoạn trên **không có stdout cố định** trong bài vì localized pattern có thể khác JDK/runtime image. Kết quả dùng để **hiển thị** theo môi trường, không phải khóa dữ liệu hoặc định dạng giao tiếp giữa các hệ thống.

### 11.3. Chênh lệch format và parse

Đừng giả định output ngày giờ đã format ở máy A bằng CLDR X sẽ chắc chắn parse được trên máy B dùng CLDR Y hoặc source HOST.

Tại ranh giới dữ liệu:

- Dùng format không phụ thuộc locale cho API/database khi có thể.
- Chỉ dùng localized format để hiển thị hoặc nhập liệu mà quy tắc ngôn ngữ được chỉ định.
- Nếu nhận input người dùng theo locale, lựa chọn formatter/locale và các quy tắc parse phải rõ ràng, được test theo runtime.
- Khi nâng JDK, kiểm thử cả **formatting** lẫn **parsing**, không chỉ snapshot của UI.

### 11.4. Currency code không đồng nghĩa currency display name

`java.util.Currency` có ISO currency code cùng các dữ liệu liên quan; `CurrencyNameProvider` là service cho **localized currency name/symbol**. Việc đổi provider hiển thị ký hiệu không có nghĩa nó thay đổi mã ISO currency hoặc các phép tính tiền được bảo vệ bởi domain model.

Giá trị tiền nên dùng kiểu số và loại tiền theo contract; text currency localized chỉ là biểu diễn.

## 12. Lựa chọn CLDR/SPI/HOST theo môi trường sản phẩm

| Mục tiêu | Cấu hình/định hướng | Kiểm tra cần có |
| --- | --- | --- |
| Muốn data mặc định của JDK hiện hành | Không đặt property hoặc `CLDR` | Khóa JDK distribution/version; kiểm thử CLDR data changes |
| Muốn bổ sung locale đặc thù của ứng dụng | `CLDR,SPI` và provider service phù hợp | Provider được đóng gói, custom locale thực sự xuất hiện |
| Muốn override formatter JDK cho locale có sẵn | `SPI,CLDR` | Provider scope, formatting/parse đúng, không áp sai dịch vụ |
| Muốn phản ánh OS custom settings | `HOST,CLDR` trên runtime hỗ trợ | Test Windows/macOS JDK thực tế; đừng suy ra Linux cũng có |
| Muốn runtime image nhỏ | `jlink` với `jdk.localedata` và `--include-locales` theo yêu cầu | Kiểm tra locales còn hỗ trợ sau khi link |
| Cần output machine-stable | Không dựa localized patterns cho wire format | ISO/schema/explicit fixed patterns phù hợp |
| Cần nhiều nhóm dịch vụ riêng | Provider cụ thể cho từng `LocaleServiceProvider` | Dùng NumberFormatProvider không tự thay DateFormatProvider |
| Nâng JDK/CLDR | Giữ policy, kiểm thử fixtures trước/sau | Date/number/currency/name, parsing, fallback, extensions |

**Khuyến nghị chung:** dùng `CLDR` theo mặc định nếu không có yêu cầu khác. Chỉ đưa `SPI` hoặc `HOST` vào thứ tự tìm kiếm khi ứng dụng thật sự có provider cần dùng hoặc muốn dùng user OS customization. Việc mở thêm nguồn không có mục tiêu có thể làm môi trường khó tái lập hơn.

## 13. Những sai lầm thường gặp

### Sai lầm 1 — Cho rằng CLDR/SPI/HOST đều là file resource giống nhau

Chúng là **nguồn dữ liệu** với cách triển khai khác nhau. CLDR được JDK tích hợp; SPI do provider classes của ứng dụng đăng ký; HOST phụ thuộc OS và implementation.

### Sai lầm 2 — Chỉ đặt provider lên classpath và mong nó thắng CLDR

JDK 26 dùng mặc định `CLDR`. Nếu muốn runtime nạp SPI provider từ classpath, phải khai báo `SPI` trong `java.locale.providers`. Nếu muốn SPI ưu tiên các dịch vụ JDK đã có, đặt `SPI` **trước** `CLDR`.

### Sai lầm 3 — Đặt thứ tự `CLDR,SPI` rồi nghĩ SPI bị vô hiệu hóa hoàn toàn

SPI vẫn có thể được chọn cho một locale/service mà CLDR không đáp ứng. Demo chứng minh `zz-ZZ` xuất hiện và được custom NumberFormat xử lý ngay cả khi CLDR đứng trước.

### Sai lầm 4 — Nghĩ số locale trong getAvailableLocales quyết định provider thắng

Tập available locales và provider precedence không tương đương. Một locale được nhiều nguồn hỗ trợ; thứ tự property và loại dịch vụ mới quyết định nguồn được chọn khi có nhiều ứng viên.

### Sai lầm 5 — Gọi `System.setProperty` sau khi đã dùng NumberFormat

Thứ tự provider được cache ở quá trình khởi tạo. Thay property giữa runtime không phải cách tin cậy để đổi nguồn dữ liệu. Dùng `-D` tại JVM startup và chạy các processes độc lập.

### Sai lầm 6 — Nghĩ HOST luôn có trên Linux và cho mọi locale

Oracle JDK 26 mô tả HOST trên Windows/macOS và phụ thuộc default OS customizations. Không kỳ vọng tác động giống nhau trên mọi platform/JDK vendor.

### Sai lầm 7 — Dùng nguồn dữ liệu đã bị loại bỏ

Các provider legacy `JRE`/`COMPAT` đã **bị gỡ khỏi JDK từ JDK 23**; chúng không phải cách hợp lệ để khôi phục dữ liệu JDK 8 trong JDK 26. Nếu có format compatibility thật sự, dùng patterns cố định theo contract hoặc tạo provider hiện hành phù hợp.

### Sai lầm 8 — Bỏ qua `jdk.localedata` khi tạo custom runtime image

Ứng dụng vẫn tạo được `Locale.forLanguageTag("vi-VN")`, nhưng các localized resources ngoài `java.base` có thể không còn. Kiểm tra module composition, `jlink --include-locales` và runtime end-to-end.

### Sai lầm 9 — Nghĩ NumberFormatProvider thay tất cả localized APIs

Một SPI class cung cấp đúng **service type** của nó; không tự kiểm soát DateFormat, CurrencyName, Locale display names hoặc TimeZoneName.

### Sai lầm 10 — Hard-code output theo một JDK rồi coi là Java spec

Localized formatting có data version và implementation. Test snapshots có thể hợp lệ với JDK pinned, nhưng không nên dùng làm tuyên bố bất biến cho mọi JDK.

### Sai lầm 11 — Không xét Locale extensions

Ví dụ numbering system `-u-nu-thai` có thể ảnh hưởng formatter. `isSupportedLocale` mặc định bỏ qua extensions khi so sánh; provider chuyên biệt cần override khi extensions làm thay đổi khả năng hỗ trợ.

### Sai lầm 12 — Gọi Locale.getDefault() khi đã có locale từ user profile

Server locale có thể khác user locale. Nếu nội dung gửi cho user đã có BCP 47 tag, dùng locale tường minh cho formatter và display names.

## 14. Checklist trước khi triển khai Locale SPI

1. Xác định **JDK/vendor/build** đang dùng và **CLDR data version** theo tài liệu distribution.
2. Xác định code được launch trên classpath hay named module, provider được đóng gói/đăng ký đúng cơ chế.
3. Ghi rõ `java.locale.providers` trong JVM arguments và thứ tự dự kiến, không dựa vào việc set sau startup.
4. Nếu dùng SPI classpath, kiểm tra `META-INF/services/<service-type>` tồn tại trong JAR/output đúng tên.
5. Nếu dùng named module, kiểm tra `module-info.java` có `provides` implementation và module được resolved.
6. Xác nhận phạm vi `getAvailableLocales()` và `isSupportedLocale(...)`, gồm các extensions quan trọng.
7. Dùng test **chứng minh provider thực sự được chọn**, không chỉ class load được.
8. Kiểm tra CLDR fallback khi provider không có service/locale.
9. Kiểm tra locale mặc định thuộc category `FORMAT` hay `DISPLAY`, không vô ý dùng server locale.
10. Nếu tạo runtime image bằng `jlink`, xác nhận `jdk.localedata` và `--include-locales` đáp ứng vùng ngôn ngữ sản phẩm.
11. Có test với số, ngày, tiền tệ, locale display names khi các nhóm đó nằm trong phạm vi sản phẩm.
12. Không áp dụng dữ liệu localized text làm format lưu trữ hoặc wire format khi cần deterministic machines.
13. Khi nâng JDK, kiểm thử parsing các giá trị do bản cũ phát sinh; không chỉ so bản dịch hiển thị.
14. Thử locale extensions và locale không hỗ trợ để chắc chắn fallback/provenance đúng.
15. Nếu `HOST` quan trọng, kiểm thử trên đúng OS/user configuration, tránh output snapshot cross-platform.
16. Giới hạn provider ở nguồn đáng tin cậy: SPI code chạy **trong process**, không phải data file thụ động.
17. Log các thông tin chẩn đoán cấu hình cần thiết nhưng tránh ghi dữ liệu nhạy cảm của người dùng.
18. Viết tài liệu compatibility khi thay đổi thứ tự nguồn và cập nhật localization patterns.

## 15. Câu hỏi tự kiểm tra

**1. JDK 26 dùng những loại locale data sources chính nào?**

`CLDR`, `SPI` và `HOST`. CLDR là mặc định; SPI do ứng dụng cung cấp, HOST phụ thuộc OS/JDK implementation.

**2. Cách chỉ ưu tiên SPI cho services mà ứng dụng triển khai, nhưng vẫn cho CLDR làm nguồn dự phòng?**

Khởi động với `-Djava.locale.providers=SPI,CLDR`. Provider phải tồn tại và được đăng ký đúng loại service.

**3. `CLDR,SPI` có làm mọi provider SPI vô hiệu không?**

Không. CLDR ưu tiên phần nó hỗ trợ; SPI có thể phục vụ locale/service khác còn thiếu, như `zz-ZZ` trong demo.

**4. `NumberFormatProvider` có thay locale date/time patterns không?**

Không. Nó chỉ cung cấp `NumberFormat`. Date/time localization dùng các API và dịch vụ liên quan khác.

**5. Có nên đổi `java.locale.providers` giữa runtime bằng `System.setProperty` không?**

Không nên: thứ tự được cache khi lớp provider của runtime khởi tạo. Dùng launcher argument và một JVM process mới.

**6. Tại sao provider class có mặt trong JAR nhưng không được gọi?**

Có thể thiếu `SPI` trong provider order, sai file `META-INF/services` hoặc sai `provides` của module, class/provider không visible, hay CLDR đứng trước và đã đáp ứng locale/service.

**7. Tại sao chạy trên full JDK hỗ trợ Vietnamese nhưng jlink image lại không?**

Dữ liệu locale ngoài English/ROOT trong `java.base` chủ yếu thuộc `jdk.localedata`; custom runtime có thể bỏ/lọc module hoặc locales đó.

**8. HOST có cung cấp mọi thông tin cho mọi locale trên mọi OS không?**

Không. JDK 26 Oracle nêu HOST trên Windows/macOS, chủ yếu phản ánh cấu hình user default. Phạm vi phụ thuộc OS/JDK implementation.

**9. `Locale.forLanguageTag("vi-VN")` có bảo đảm NumberFormat cho vi-VN có dữ liệu riêng không?**

Không. Việc tạo Locale object độc lập với locale service data đang có; runtime có thể fallback hoặc thiếu dữ liệu theo image.

**10. JDK 26 dùng CLDR version nào theo Javadoc?**

CLDR 48. Không xem patterns của CLDR 48 là bất biến với JDK versions sau.

**11. Provider có nhất thiết nhận đúng loại Locale object xuất hiện trong getAvailableLocales khi fallback không?**

Không nhất thiết. Theo hợp đồng `LocaleServiceProvider`, khi dùng candidate matching, factory có thể truyền **requested Locale ban đầu**, gồm extensions, vào phương thức tạo object/tên. Provider phải tuân thủ contract của dịch vụ.

**12. Khi ứng dụng cần kết quả parsing ổn định qua các bản JDK, có nên dựa vào DateFormat.getDateInstance(MEDIUM,locale) như một protocol format không?**

Không. Patterns/data theo JDK có thể thay đổi. Dùng format machine-stable hoặc pattern được quản lý rõ ràng, và có test cho dữ liệu thật.

## Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — `LocaleServiceProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): CLDR/SPI/HOST, `java.locale.providers`, phạm vi providers, `getAvailableLocales()`, `isSupportedLocale()`, fallback và CLDR versions.
- [Oracle — JDK 26 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk26-supported-locales.html): ba nguồn, CLDR 48, HOST theo nền tảng, module `jdk.localedata` và `jlink --include-locales`.
- [Oracle Java SE 26 — `NumberFormatProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/spi/NumberFormatProvider.html): factory methods mà một custom number provider phải triển khai.
- [Oracle Java SE 26 — `NumberFormat`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/NumberFormat.html): các factory methods và locale extensions.
- [Oracle Java SE 26 — `Locale`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): BCP 47, locale mặc định, `getAvailableLocales()` và locale data support.
- [Oracle Java SE 26 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): đăng ký providers trên classpath và JPMS.
- [Oracle Java SE 26 — `jlink`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html): `--add-modules`, `--include-locales` và image composition.
- [Oracle Java SE 26 Migration Guide — Removed Components](https://docs.oracle.com/en/java/javase/26/migrate/removed-tools-components.html): ghi nhận `JRE/COMPAT` locale data đã bị loại từ JDK 23.
- [Oracle Java SE 26 — Internationalization Overview](https://docs.oracle.com/en/java/javase/26/intl/internationalization-guide.html): nền tảng quốc tế hóa và phạm vi dữ liệu locale.

**Ghi nhớ:** **`Locale` chọn ngôn ngữ/khu vực; `java.locale.providers` chọn thứ tự nguồn dữ liệu; `LocaleServiceProvider` quyết định phạm vi một dịch vụ; runtime image quyết định dữ liệu JDK thực sự có.** Trong JDK 26, `CLDR` là mặc định, `SPI` cho phép cung cấp data chuyên biệt, `HOST` phụ thuộc hệ điều hành. Muốn ứng dụng ổn định, cần pin JDK/toolchain phù hợp, cấu hình `-D` tại startup, kiểm thử theo **service + locale + provider order + runtime image**, không dựa vào giả định mọi locale data đều bất biến hoặc mọi provider đều bao phủ toàn bộ APIs.
