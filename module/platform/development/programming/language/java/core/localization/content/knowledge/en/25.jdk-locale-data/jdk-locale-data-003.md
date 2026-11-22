# java.locale.providers và thứ tự nhà cung cấp trong JDK

## 1. Vấn đề: Locale không phải nguồn dữ liệu locale

Khi viết phần mềm Java đa ngôn ngữ, ta thường chọn locale tường minh rồi gọi:

```java
Locale fr = Locale.FRANCE;
NumberFormat number = NumberFormat.getNumberInstance(fr);
DateFormat date = DateFormat.getDateInstance(
        DateFormat.LONG, fr);
```

Các lệnh nằm trong phương thức Java, với import phù hợp. Chúng yêu cầu hiển thị số và ngày theo quy ước tiếng Pháp ở Pháp. Nhưng **mẫu ngày, dấu thập phân, ký hiệu nhóm nghìn và tên tháng lấy từ nguồn nào?**

Các JDK có **locale-sensitive service providers**. System property `java.locale.providers` điều khiển **thứ tự ưu tiên nguồn cung cấp dữ liệu/implementation cho các dịch vụ bản địa hóa**:

```bash
java -Djava.locale.providers=CLDR,SPI -jar app.jar
```

Property này **không chọn locale người dùng**. Nó chỉ nói cho runtime thứ tự tìm provider, ví dụ CLDR trước rồi SPI. Với cùng `Locale.FRANCE`, kết quả format có thể thay đổi khi đổi provider hoặc nâng JDK vì dữ liệu nguồn thay đổi.

Đây là vấn đề cốt lõi khi di chuyển từ JDK 8 sang JDK 17, hoặc từ JDK 17 lên JDK 23+: những bộ dữ liệu locale có vòng đời riêng và có thể thay đổi dấu câu, ký hiệu, Unicode whitespace hoặc chữ viết tắt. Nếu ứng dụng lưu chuỗi đã format thay vì dữ liệu có kiểu, thay đổi tưởng chừng chỉ là hiển thị có thể gây lỗi parse hoặc test.

### Kết quả cần đạt

Sau bài học, người đọc có thể:

1. Phân biệt `Locale`, locale provider và API sử dụng dữ liệu locale.
2. Hiểu `CLDR`, `COMPAT`/`JRE`, `SPI` và `HOST`, bao gồm giới hạn phiên bản.
3. Giải thích thứ tự provider được xét như thế nào và khi nào xảy ra fallback.
4. Đặt `-Djava.locale.providers=...` đúng lúc **khởi động** JVM.
5. Thử hai thứ tự trong hai Java processes độc lập và chẩn đoán mã Unicode khác biệt.
6. Biết provider SPI được tạo và đăng ký bằng cơ chế nào.
7. Tránh giả định thứ tự provider ảnh hưởng mọi thư viện hoặc mọi dịch vụ giống nhau.
8. Lập kế hoạch kiểm thử khi nâng JDK, nhất là mốc loại bỏ COMPAT từ **JDK 23**.

## 2. Ba khái niệm cần tách rời

| Thành phần | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Locale** | Cho người dùng/ngôn ngữ/vùng nào? | `Locale.FRANCE`, `Locale.forLanguageTag("vi-VN")` |
| **Locale provider** | Ai cung cấp dữ liệu/implementation bản địa hóa? | `CLDR`, `SPI`, `HOST`, `COMPAT` trên JDK cũ |
| **Locale-sensitive API** | Đang yêu cầu loại dịch vụ nào? | `NumberFormat`, `DateFormat`, `Currency`, `Locale` display names |

Ví dụ:

```java
NumberFormat formatter =
        NumberFormat.getNumberInstance(Locale.FRANCE);
```

`Locale.FRANCE` là **locale đích**, `NumberFormat` là **loại dịch vụ**, còn runtime tra nguồn theo thứ tự property khi tạo formatter. Đổi property không có nghĩa đổi người dùng từ tiếng Việt sang tiếng Pháp.

Ngược lại, `Locale.getDefault()` và `Locale.setDefault(...)` liên quan **locale mặc định của JVM**. Nếu một factory không nhận locale tường minh, nó có thể dùng `Locale.getDefault(Locale.Category.FORMAT)`. Đây là trục khác với provider. Không đổi default locale theo từng web request, vì tác động JVM-wide có thể ảnh hưởng thread khác.

`java.locale.providers` cũng **không phải charset**: UTF-8/UTF-16 là chuyện chuyển text thành byte. Nó không thay bằng `ResourceBundle` của ứng dụng, không xử lý thiếu bản dịch và không quyết định timezone của `Instant`.

## 3. Bốn nhóm provider quan trọng

### 3.1. CLDR — dữ liệu bản địa hóa của Unicode

`CLDR` là nguồn dựa trên **Common Locale Data Repository** của Unicode. JDK sử dụng dữ liệu này cho nhiều dịch vụ như quy tắc format ngày/giờ, số, ký hiệu tiền tệ và tên hiển thị, tùy API và phiên bản.

**Từ JDK 9, CLDR trở thành nguồn ưu tiên theo mặc định.** CLDR không bất biến: khi JDK nâng phiên bản dữ liệu CLDR, chuỗi hiển thị có thể thay đổi. Ví dụ dấu cách phân nhóm số có thể là U+202F (narrow no-break space) chứ không phải U+0020 (space) dù mắt thấy tương tự.

**Không kết luận mọi dịch vụ đều sử dụng đúng CLDR theo cùng cách.** Tài liệu Oracle JDK 17 có lưu ý riêng đối với dữ liệu `BreakIterator` và `Collator`. Các thư viện ngoài JDK như ICU4J hoặc engine trên trình duyệt cũng có pipeline và dữ liệu riêng.

### 3.2. COMPAT/JRE — legacy provider

Với **JDK 17**, `COMPAT` là nguồn dữ liệu nhằm tương thích với quy tắc của các bản JDK cũ, đặc biệt trước JDK 9. `JRE` là tên alias lịch sử của `COMPAT` và đã bị deprecated.

Ví dụ để **thử** độ tương thích trên JDK 17:

```bash
java -Djava.locale.providers=COMPAT,CLDR LocaleProvidersDemo
```

Cấu hình này ưu tiên COMPAT trước CLDR cho các locale/dịch vụ phù hợp. Nó có thể tạo định dạng giống hệ thống cũ ở một số nơi, nhưng **không bảo đảm khôi phục mọi hành vi Java 8**.

Mốc quan trọng:

| Phiên bản | Bối cảnh |
| --- | --- |
| JDK 8 | Nguồn JRE truyền thống được dùng mặc định; CLDR có thể là lựa chọn cấu hình. |
| JDK 9–20 | CLDR là nguồn ưu tiên; COMPAT vẫn phục vụ chuyển tiếp trong các phiên bản có hỗ trợ. |
| JDK 21–22 | Khi dùng JRE/COMPAT có cảnh báo chuẩn bị loại bỏ dữ liệu legacy. |
| **JDK 23 trở lên** | **Đã loại bỏ dữ liệu legacy JRE/COMPAT.** Ghi tên này trong property không khôi phục dữ liệu cũ. |

Vì vậy, câu nói “cứ dùng COMPAT để giữ kết quả cũ” chỉ có thể là **biện pháp chuyển tiếp ở các JDK còn COMPAT**, không phải chiến lược cho toàn bộ Java 17+.

### 3.3. SPI — Service Provider Interface

`SPI` dành cho những implementation do nhà phát triển hoặc thư viện cung cấp thông qua các class kế thừa provider của `java.text.spi` và `java.util.spi`. Một số API:

- `NumberFormatProvider` — formatter số, phần trăm, tiền tệ, số nguyên.
- `DateFormatProvider`, `DateFormatSymbolsProvider` — định dạng ngày và ký hiệu.
- `DecimalFormatSymbolsProvider` — ký hiệu số.
- `LocaleNameProvider`, `CurrencyNameProvider` — tên ngôn ngữ/vùng, tiền tệ.
- `TimeZoneNameProvider` — tên múi giờ.
- `CollatorProvider` và `BreakIteratorProvider` — các dịch vụ tương ứng.

Nếu muốn SPI được ưu tiên, đặt nó trước:

```bash
java -Djava.locale.providers=SPI,CLDR LocaleProvidersDemo
```

**Không chỉ thêm chữ SPI rồi kỳ vọng có dữ liệu mới.** Runtime phải tìm thấy implementation tương ứng trên classpath/module path. Nếu không có implementation hoặc provider không hỗ trợ dịch vụ/locale đã yêu cầu, provider kế tiếp trong danh sách mới có cơ hội đáp ứng.

Ngược lại, `CLDR,SPI` thường ưu tiên CLDR ở nơi CLDR hỗ trợ, nên SPI tự viết có thể không được dùng cho những yêu cầu trùng phạm vi. Thứ tự đặt tên provider chính là phần cấu hình quan trọng.

### 3.4. HOST — dữ liệu từ OS khi khả dụng

`HOST` có thể phản ánh các tùy chỉnh locale của hệ điều hành người dùng, ví dụ quy tắc format ngày/giờ hoặc số. **Không phải hệ điều hành/JDK nào cũng hỗ trợ HOST như nhau**. Trong Oracle JDK 17, HOST có hỗ trợ trên Windows/macOS theo tài liệu locale tương ứng.

Cấu hình mẫu:

```bash
java -Djava.locale.providers=HOST,CLDR LocaleProvidersDemo
```

Nếu HOST không khả dụng hoặc không hỗ trợ dịch vụ/locale cụ thể, runtime có thể tiếp tục nguồn sau. Do đó, **đặt HOST trong property không chứng minh kết quả thực tế đã đến từ OS**. Server chạy Linux/container có thể khác desktop Windows/macOS; đừng dùng HOST nếu yêu cầu reproducibility mà chưa kiểm tra môi trường.

## 4. Cơ chế ưu tiên và fallback

Xét JDK 17 với property:

```text
java.locale.providers=SPI,CLDR,COMPAT
```

Khi ứng dụng gọi `NumberFormat.getNumberInstance(localeX)`, thứ tự tìm **ở mức khái niệm** là:

```text
Yêu cầu: NumberFormat cho localeX
   |
   v
SPI hỗ trợ NumberFormat + localeX?
   | có -> dùng formatter SPI tương ứng
   | không
   v
CLDR hỗ trợ dịch vụ + localeX?
   | có -> dùng CLDR
   | không
   v
COMPAT hỗ trợ? (chỉ trên JDK còn COMPAT)
   | có -> dùng COMPAT
   | không
   v
Fallback locale/root và cơ chế JDK áp dụng
```

Đây là sơ đồ giảng giải, **không phải source code nội bộ**. Runtime có những quy tắc tra cứu locale cha, cấu hình service, caching và đặc tính implementation riêng. Nhưng nó cho thấy hai sự thật:

1. **Thứ tự có ý nghĩa:** `SPI,CLDR` và `CLDR,SPI` có thể tạo kết quả khác khi cả hai nguồn đáp ứng yêu cầu.
2. **Fallback có ý nghĩa:** nếu provider đầu không có dịch vụ/locale được yêu cầu, runtime có thể dùng nguồn sau. Không có sự bảo đảm provider đứng đầu sẽ thắng mọi lời gọi.

### Phân biệt bốn loại fallback

- **Provider fallback:** từ SPI sang CLDR khi SPI không có dữ liệu phù hợp.
- **Locale fallback:** từ locale cụ thể sang locale cha/chung theo luật API.
- **ResourceBundle fallback:** tìm bundle của ứng dụng, không đồng nghĩa property provider.
- **Font fallback:** renderer tìm font/glyph, hoàn toàn khác dữ liệu format locale.

Khi thấy output không đổi giữa các cấu hình, có thể vì hai nguồn có cùng quy tắc cho locale đó, service không hỗ trợ provider đang thử, hoặc fallback dẫn đến cùng dữ liệu. **Không có thay đổi không đồng nghĩa property bị bỏ qua.**

### Default provider order theo JDK

Với **Oracle/OpenJDK 17**, tài liệu công bố mặc định tương đương `CLDR,COMPAT`. Từ **JDK 23**, legacy COMPAT không còn, và mặc định trên Oracle JDK 23 tương đương `CLDR`. Vendor/JDK khác cần được kiểm tra theo tài liệu triển khai.

`System.getProperty("java.locale.providers")` trả `null` không có nghĩa không có provider. Nó chỉ cho thấy không có giá trị tường minh được đặt trong system properties tại thời điểm bạn đọc.

## 5. Khởi động JVM đúng cách

### 5.1. Cú pháp system property

`-Djava.locale.providers=...` là một **JVM option**. Nó phải đứng trước main class, hoặc trước `-jar`:

```bash
java -Djava.locale.providers=CLDR,SPI -cp app.jar com.example.Main
java -Djava.locale.providers=CLDR,SPI -jar app.jar
```

Ví dụ sai:

```text
java com.example.Main -Djava.locale.providers=SPI,CLDR
```

Trong lệnh sai, phần `-D...` thường đi vào `args[]` của ứng dụng, chứ không trở thành JVM system property. Cần kiểm tra JVM options của tiến trình chạy thật, không chỉ file cấu hình của công cụ build.

### 5.2. Property được đọc lúc startup

Theo tài liệu Java 17, thứ tự provider được đọc khi Java runtime khởi động; ở tài liệu JDK mới, giá trị cũng được đọc/cached trong quá trình khởi tạo dịch vụ. Vì vậy:

```java
System.setProperty("java.locale.providers", "SPI,CLDR");
```

**không phải cách đổi provider an toàn sau khi các dịch vụ locale đã khởi tạo**. Đừng tạo formatter trước, set property sau rồi suy luận rằng formatter mới sẽ dùng thứ tự mới. **So sánh bằng hai JVM processes riêng** với command-line options khác nhau.

`Locale.setDefault(Locale.US)` cũng không giải quyết vấn đề: nó chỉ điều chỉnh locale mặc định, không phải provider order, và là trạng thái dùng chung JVM.

### 5.3. Điểm dễ sai trong hệ thống build

IDE, Maven, Gradle, application server, test fork, container và CLI có thể chạy bằng **những Java processes khác nhau**. Đặt system property cho Gradle daemon không tự bảo đảm test JVM hoặc application JVM đã nhận nó. Trong CI hãy ghi rõ:

- Command line của process chạy ứng dụng hoặc test.
- JDK vendor + version (không chỉ compiler version).
- `java.locale.providers` thực tế trong process.
- Locale, timezone, currency và style/pattern tại điểm format.
- Bộ thử nghiệm trước/sau nâng cấp.

Trong container có thể cần đưa property vào JVM options của container entrypoint; không cố đổi ở một thread khi service đã bắt đầu.

## 6. Ví dụ Java 17+ độc lập: kiểm tra số, ngày và Unicode code points

Tạo file **`LocaleProvidersDemo.java`** dưới đây. Chương trình không cần file dữ liệu, không thay default locale JVM, dùng `Locale.FRANCE` và `UTC` tường minh. Nó hiển thị cấu hình property hiện tại, số phiên bản feature JDK và code point của chuỗi số để phát hiện các ký tự gần giống nhau.

```java
import java.text.DateFormat;
import java.text.NumberFormat;
import java.time.Instant;
import java.util.Date;
import java.util.Locale;
import java.util.StringJoiner;
import java.util.TimeZone;

public class LocaleProvidersDemo {

    private static String codePoints(String text) {
        StringJoiner out = new StringJoiner(" ");
        text.codePoints().forEach(cp ->
                out.add(String.format(
                        Locale.ROOT, "U+%04X", cp)));
        return out.toString();
    }

    public static void main(String[] args) {
        Locale fr = Locale.FRANCE;
        Date fixed = Date.from(
                Instant.parse("2024-01-02T12:00:00Z"));

        DateFormat date = DateFormat.getDateInstance(
                DateFormat.LONG, fr);
        date.setTimeZone(TimeZone.getTimeZone("UTC"));

        String number = NumberFormat
                .getNumberInstance(fr)
                .format(12345.67);

        System.out.println("javaFeature="
                + Runtime.version().feature());
        System.out.println("configured="
                + System.getProperty(
                        "java.locale.providers", "<default>"));
        System.out.println("frDate=" + date.format(fixed));
        System.out.println("frNumberCodepoints="
                + codePoints(number));
        System.out.println("frNumberLength=" + number.length());
    }
}
```

Biên dịch bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 LocaleProvidersDemo.java
```

Chạy **mỗi dòng trong một process riêng**:

```bash
java LocaleProvidersDemo
java -Djava.locale.providers=CLDR LocaleProvidersDemo
java -Djava.locale.providers=SPI,CLDR LocaleProvidersDemo
```

Nếu bạn đang trên **JDK 17–22** và muốn kiểm tra dữ liệu legacy:

```bash
java -Djava.locale.providers=COMPAT,CLDR LocaleProvidersDemo
java -Djava.locale.providers=CLDR,COMPAT LocaleProvidersDemo
```

Từ JDK 23 trở lên, COMPAT không còn là lựa chọn thực chất. **Không dùng kết quả test trên JDK 24 để giả định COMPAT của JDK 17 hoạt động như thế nào.**

**Stdout quan sát trên máy thử Zulu OpenJDK 24, cấu hình mặc định:**

```text
javaFeature=24
configured=<default>
frDate=2 janvier 2024
frNumberCodepoints=U+0031 U+0032 U+202F U+0033 U+0034 U+0035 U+002C U+0036 U+0037
frNumberLength=9
```

Đây là **output cụ thể đã kiểm tra**, không phải hứa hẹn tất cả runtime Java 17+ đều trả đúng từng dòng. Trên JDK 17 `javaFeature` sẽ là 17; khi có `-D`, `configured` sẽ hiện giá trị đã đặt. Ngày/số có thể khác khi provider, CLDR version, JDK vendor hoặc dữ liệu locale thay đổi.

### Đọc các dòng kết quả

1. `javaFeature` xác nhận phiên bản feature của process thật.
2. `configured=<default>` nghĩa là không thấy property tường minh; runtime vẫn sử dụng thứ tự provider mặc định.
3. `frDate` minh họa tên tháng tiếng Pháp nhờ `Locale.FRANCE` được truyền tường minh.
4. `frNumberCodepoints` trong môi trường thử dùng `U+202F` làm dấu nhóm nghìn, còn `U+002C` là dấu phẩy thập phân.
5. `frNumberLength=9` đếm **UTF-16 code units**, không phải byte UTF-8.
6. Không thể suy tên provider thực sự dùng chỉ từ một chuỗi output; nhiều provider có thể cho kết quả giống nhau.

### Vì sao kiểm tra bằng code point?

Dấu cách ASCII `U+0020`, no-break space `U+00A0` và narrow no-break space `U+202F` có thể trông gần giống trên giao diện, nhưng **`String.equals`, parser hoặc snapshot test phân biệt chúng**. Việc in từng mã code point giúp truy đúng nguyên nhân sau khi nâng JDK, thay vì “sửa” chuỗi bằng cách loại bỏ mọi khoảng trắng mà không xét định dạng.

## 7. SPI: đóng gói một provider do ứng dụng cung cấp

### 7.1. Cơ chế đăng ký

`java.util.spi.LocaleServiceProvider` là abstract base class cho các locale-sensitive SPIs. Một implementation có thể được đóng gói trên classpath với **service configuration file**:

```text
META-INF/services/java.text.spi.NumberFormatProvider
```

Nếu implementation tên `demo.CustomNumberProvider`, nội dung file là:

```text
demo.CustomNumberProvider
```

File service configuration cần được mã hóa UTF-8. Với Java modules có thể khai báo `provides ... with ...` trong `module-info.java` theo hợp đồng Java module/service loader. Không chỉ tạo class rồi mong runtime tự quét mọi class trên classpath.

### 7.2. Cấu trúc provider mẫu

Dưới đây là một ví dụ **minh họa cách mở rộng API**, không phải bộ formatter production đã hoàn thiện:

```java
package demo;

import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Locale;

public final class CustomNumberProvider
        extends NumberFormatProvider {

    private static final Locale TEST =
            Locale.forLanguageTag("en-XA");

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { TEST };
    }

    private NumberFormat make(String pattern) {
        // Dùng US symbols ở đây để tránh tự gọi lại
        // factory NumberFormat cho chính locale TEST.
        return new DecimalFormat(pattern,
                DecimalFormatSymbols.getInstance(Locale.US));
    }

    @Override
    public NumberFormat getNumberInstance(Locale locale) {
        return make("'[custom] '#,##0.00");
    }

    @Override
    public NumberFormat getIntegerInstance(Locale locale) {
        NumberFormat f = make("'[custom] '#,##0");
        f.setParseIntegerOnly(true);
        return f;
    }

    @Override
    public NumberFormat getCurrencyInstance(Locale locale) {
        return make("'[custom currency] '¤#,##0.00");
    }

    @Override
    public NumberFormat getPercentInstance(Locale locale) {
        return make("'[custom percent] '0.0%");
    }
}
```

Với code trên cần bổ sung **kiểm tra tham số locale**, chính sách integer rounding/parsing, currency metadata, locale fallback, Unicode extensions và test các method contracts trước khi dùng thật. `NumberFormatProvider` đòi mỗi phương thức đáp ứng semantics của loại formatter tương ứng; ví dụ percent phải nhân input với 100 khi hiển thị chứ không chỉ thêm một dấu `%` literal. Phần ví dụ chỉ tập trung vào bộ khung SPI.

Một provider thực phải khai báo đúng những locale nó hỗ trợ. Nếu khai báo hỗ trợ cả những locale không được triển khai đúng, kết quả có thể làm hỏng format ở nhiều nơi. Không tạo vòng đệ quy bằng cách gọi lại `NumberFormat.getNumberInstance(locale)` với chính locale mà provider đang phục vụ.

### 7.3. Thứ tự SPI và classpath

Đưa provider JAR vào classpath/module path của **tiến trình ứng dụng** rồi chạy với:

```bash
java -Djava.locale.providers=SPI,CLDR -cp "app.jar;provider.jar" demo.Main
```

Dòng classpath trên minh họa **Windows** với dấu `;`. Trên Linux/macOS, dấu phân cách classpath thường là `:`. Các JAR và main class chỉ là tên minh họa; chúng phải tồn tại sau bước build và đăng ký provider đúng chuẩn.

Khi một service/locale đã được CLDR hỗ trợ, `CLDR,SPI` có thể ưu tiên CLDR, còn `SPI,CLDR` giúp SPI có cơ hội được chọn trước. Nếu không có SPI artifact thực sự, thêm `SPI` vào order không tạo dữ liệu mới.

## 8. Chẩn đoán: property không chứng minh provider nào đã thắng

`System.getProperty("java.locale.providers")` chỉ cho biết **thứ tự được yêu cầu**, không phải lịch sử chính xác của mọi lần lookup. Không có một API chuẩn chung đơn giản để mọi formatter trả tên provider thực tế đã được dùng.

Để chẩn đoán, bạn nên thu thập:

- Phiên bản Java đầy đủ và nhà phân phối JDK.
- JVM arguments/launcher thật (không chỉ test compile options).
- Giá trị `java.locale.providers`.
- Locale, style/pattern, timezone/currency và API format/parse.
- Unicode code points của formatted result nếu lỗi ở dấu câu/khoảng trắng.
- Kết quả khi chạy với **hai JVM process mới**.
- Với SPI tự viết, log ngay trong provider methods và kiểm tra service registration.

`NumberFormat.getAvailableLocales()` hay `DateFormat.getAvailableLocales()` cho biết những locale có thể được hỗ trợ, **không phải bản đồ “mỗi locale được phục vụ bởi provider nào”**. Cùng một locale có thể được nhiều nguồn hỗ trợ.

### Không đánh đồng provider chain với ResourceBundle

`ResourceBundle.getBundle(...)` có cơ chế tìm và fallback bundle của ứng dụng. Nó không tự chuyển các file bản dịch `messages_vi.properties` thành nguồn CLDR hoặc SPI. Tương tự, ICU4J có cơ chế/dữ liệu riêng; đổi `java.locale.providers` không mặc nhiên thay format của ICU4J hay trình duyệt.

## 9. Nâng JDK: những thay đổi phải kiểm thử

Khi nâng từ JDK 8 lên 17 hoặc từ JDK 17/21 lên 23+, hãy tìm các đường code dùng locale-sensitive services:

| Vùng | API thường gặp | Điều có thể thay đổi |
| --- | --- | --- |
| Ngày giờ | `DateFormat`, `SimpleDateFormat`, localized `DateTimeFormatter` | Tên tháng, thứ, dấu câu, AM/PM, style. |
| Số | `NumberFormat`, `DecimalFormatSymbols` | Dấu grouping/decimal, chữ số, spacing. |
| Tiền tệ | `NumberFormat.getCurrencyInstance`, `Currency` | Ký hiệu, vị trí, khoảng trắng, số chữ số phần lẻ. |
| Display names | `Locale.getDisplayName` và locale-name services | Tên ngôn ngữ/vùng. |
| Timezone text | `TimeZone.getDisplayName` | Tên/viết tắt của múi giờ. |
| Sắp xếp/phân đoạn | `Collator`, `BreakIterator` | Dữ liệu và implementation cụ thể, không đồng nhất hoàn toàn với CLDR. |

### Một ma trận test ngắn nên có

- Dùng các locale thực sự được sản phẩm hỗ trợ, không chỉ `en-US`.
- Cố định `Instant`, timezone, currency và input number khi so sánh.
- In formatted text và code point/hex để thấy khoảng trắng khác.
- Test parse sau format khi domain cần; kiểm tra parser tiêu thụ hết input.
- Với ngày tháng, test năm hai chữ số, tên tháng, ngày không tồn tại, thứ tự ngày/tháng.
- Với số, test grouping, phần lẻ, số âm, percent và currency.
- Thử input thực tế mà người dùng đã lưu từ bản JDK cũ.
- Chạy trên từng JDK/vendor và đúng `java.locale.providers` dự kiến deploy.
- Khi có SPI, test trường hợp provider hỗ trợ locale và trường hợp phải fallback.

### Vì sao COMPAT không phải giải pháp dài hạn?

Một hệ thống cũ có thể đã dựa vào `COMPAT` để trì hoãn thay đổi format từ JDK 9. Nhưng **từ JDK 23, dữ liệu legacy không còn**. Khi ứng dụng cần giao tiếp máy–máy, hãy dùng schema, ISO formatter hoặc định dạng decimal ổn định thay vì serialized display strings. Nếu hóa đơn/biểu mẫu phải theo quy tắc cố định, chủ động cấu hình format và version hóa hợp đồng; đừng trông chờ dữ liệu legacy tồn tại mãi trong runtime.

## 10. Lỗi phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ property chọn ngôn ngữ người dùng | CLDR/SPI không phải `Locale.FRANCE`. | Chọn Locale tường minh; provider là nguồn dữ liệu. |
| Viết `-D` sau main class | Chỉ là tham số ứng dụng. | Đặt option trước class/`-jar`. |
| Gọi `System.setProperty` sau khi init | Thứ tự có thể đã đọc/cached. | Restart process với JVM option. |
| Dùng `COMPAT` trên mọi Java 17+ | JDK 23 đã bỏ legacy data. | Migrate CLDR hoặc provider/format riêng. |
| Nghĩ `JRE` là nhà cung cấp hoàn toàn khác `COMPAT` | Tên alias lịch sử. | Hiểu timeline và loại bỏ từ JDK 23. |
| Có SPI JAR nhưng không bật `SPI` | Custom provider có thể không được xét. | Đăng ký service và khai báo order. |
| Đặt `CLDR,SPI` rồi kỳ vọng SPI luôn thắng | Provider đứng trước có thể hỗ trợ locale. | Dùng `SPI,CLDR` nếu cần ưu tiên tùy biến. |
| Tin HOST luôn hoạt động trong container | HOST phụ thuộc OS/vendor. | Có fallback và test OS mục tiêu. |
| Xem output format là protocol ổn định | Dữ liệu CLDR/JDK có thể đổi. | Lưu typed data, format ở UI. |
| Bỏ qua U+202F/U+00A0 trong snapshot | Chuỗi trông giống nhưng khác code point. | Ghi mã Unicode khi chẩn đoán. |
| Nghĩ mọi dịch vụ đều lấy data từ CLDR | Có ngoại lệ theo API/JDK. | Xem tài liệu từng service. |
| Nghĩ `System.getProperty` là thông tin provider thực | Nó chỉ là cấu hình muốn dùng. | So sánh thực nghiệm và log SPI. |
| Thay `Locale.setDefault` theo user | Ảnh hưởng nhiều request. | Factory nhận locale của mỗi user. |

## 11. Bài tập thực hành

**Bài 1 — Thứ tự:** trên JDK 17, chạy `CLDR,COMPAT` và `COMPAT,CLDR` trong hai JVM processes. Ghi stdout chương trình `LocaleProvidersDemo` và nhận xét: vì sao không thấy khác biệt ở một locale không chứng minh thứ tự bị bỏ qua?

**Bài 2 — So sánh version:** chạy cùng code trên JDK 17 và JDK 23+, thử cấu hình COMPAT trong môi trường test. Xác nhận phiên bản hỗ trợ legacy khác nhau và viết kế hoạch migrate.

**Bài 3 — Provider SPI:** tạo `NumberFormatProvider` cho locale thử nghiệm, đóng gói file `META-INF/services` và chạy `SPI,CLDR`. Thử một locale mà SPI hỗ trợ, một locale không hỗ trợ; ghi nơi fallback xảy ra.

**Bài 4 — Unicode whitespace:** so sánh chuỗi số của `Locale.FRANCE` trên hai JDK; in code points, phân biệt `U+0020`, `U+00A0` và `U+202F`. Đừng tự thay toàn bộ dấu cách khi chưa hiểu hợp đồng.

**Bài 5 — Property timing:** tạo formatter, sau đó gọi `System.setProperty` rồi tạo lại formatter. Đối chiếu với process mới khởi động bằng `-D`. Giải thích vì sao test trong cùng JVM không đủ.

**Bài 6 — Kiến trúc API:** một REST API đang xuất `"1 234,50 €"` làm dữ liệu giao dịch. Thiết kế lại với amount và currency code riêng, rồi format tại UI theo locale. Nêu vì sao cách này ít bị ảnh hưởng bởi thay đổi provider.

**Bài 7 — Phân tích lỗi nâng cấp:** sau đổi JDK, một ngày được viết với dấu câu hoặc ký hiệu AM/PM khác. Liệt kê JDK version, provider property, API, Locale, timezone và code point cần thu thập; tách lỗi hiển thị khỏi lỗi parse/protocol.

### Checklist

- [ ] Phân biệt `Locale`, locale provider và locale-sensitive service.
- [ ] Biết cú pháp `-Djava.locale.providers` và cơ chế ưu tiên theo thứ tự.
- [ ] Giải thích `CLDR`, `SPI`, `HOST`, `COMPAT/JRE` và giới hạn nền tảng/phiên bản.
- [ ] Biết CLDR làm mặc định từ JDK 9 và COMPAT bị loại bỏ từ JDK 23.
- [ ] Hiểu fallback theo service/locale, không suy source thực từ property.
- [ ] Đặt system property khi launcher khởi động JVM, không dựa vào thay đổi runtime.
- [ ] Biết file `META-INF/services` và vai trò của `SPI`.
- [ ] Test exact Unicode code points khi output nhìn giống nhưng khác.
- [ ] Truyền Locale/zone/currency rõ ràng và không dùng display strings làm protocol.
- [ ] Có phương án kiểm thử migration khi nâng JDK/CLDR.

## 12. Tham khảo chính thức

- JDK 17 `LocaleServiceProvider`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleServiceProvider.html
- Oracle JDK 17 supported locales: https://www.oracle.com/java/technologies/javase/jdk17-suported-locales.html
- JDK 23 removed legacy locale data: https://docs.oracle.com/en/java/javase/23/migrate/removed-tools-and-components.html
- JDK 17 `NumberFormatProvider`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/spi/NumberFormatProvider.html

**Kết luận:** `java.locale.providers` chỉ định **nguồn dữ liệu locale được ưu tiên tra cứu**, không tự thay ngôn ngữ của người dùng. CLDR là nguồn chính trên JDK hiện đại; SPI cho phép mở rộng; HOST phụ thuộc hệ thống; COMPAT/JRE là quá khứ của các JDK trước 23. Hãy đặt thứ tự khi khởi động Java, truyền locale cụ thể vào API, test trên runtime thực và không biến chuỗi đã bản địa hóa thành dữ liệu định danh.
