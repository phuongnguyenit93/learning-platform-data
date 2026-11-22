# Đăng ký dịch vụ, cấu hình lúc khởi động và xác minh khả năng hỗ trợ trong Java Localization

## 1. Bối cảnh: viết lớp provider chưa đủ để Java sử dụng

Java cung cấp nhiều dịch vụ bản địa hóa có thể mở rộng: định dạng số, ngày giờ, tên locale, tên múi giờ, so sánh chuỗi theo ngôn ngữ và các quy tắc phân đoạn. Một dự án có thể cần bổ sung dữ liệu cho một locale chuyên biệt hoặc tùy biến một formatter mà dữ liệu mặc định trong JDK chưa đáp ứng.

Giả sử bạn viết class kế thừa `java.text.spi.NumberFormatProvider`. Việc class **biên dịch được** không có nghĩa `NumberFormat.getNumberInstance(locale)` sẽ tự gọi nó. Để mở rộng hệ thống một cách đúng đắn, cần hoàn thành **ba trách nhiệm riêng biệt**:

1. **Đăng ký dịch vụ:** đóng gói class và mô tả đúng service provider trên **classpath** hoặc **module path**.
2. **Cấu hình lúc khởi động:** yêu cầu JDK xét nguồn `SPI` theo thứ tự thích hợp trong `java.locale.providers`.
3. **Xác minh khả năng hỗ trợ:** kiểm tra provider có được phát hiện, có khai báo locale phù hợp, có thực sự được factory chọn, có fallback chính xác và có làm đúng semantics của dịch vụ.

Ba bước trên là chủ đề chính của bài thuộc nhóm **Đóng gói và mở rộng**. Một triển khai thành công phải đáp ứng cả ba; không chỉ có file `META-INF/services` hoặc một dòng `-D` là đủ.

### Mục tiêu học tập

Sau bài này bạn có thể:

- Phân biệt **service type**, **implementation**, **service registry**, **provider preference** và **selected provider**.
- Đóng gói `NumberFormatProvider` với `META-INF/services` bằng công cụ `javac`/`jar` trên Java 17+.
- Dùng `-Djava.locale.providers=SPI,CLDR` đúng chỗ khi khởi động JVM; hiểu vì sao `CLDR,SPI` có thể cho kết quả khác.
- Sử dụng `ServiceLoader` như một phép kiểm tra đăng ký, đồng thời hiểu tại sao **discovered không đồng nghĩa selected**.
- Sử dụng `getAvailableLocales()` và `isSupportedLocale(...)` để xác minh phạm vi provider, gồm cả vấn đề locale extensions.
- Kiểm tra fallback với một locale không được custom provider hỗ trợ.
- Biết cách khai báo `provides ... with ...` trong JPMS và phân biệt classpath/module path.
- Chẩn đoán lỗi registration, packaging, startup property, supported locales, provider semantics và xung đột giữa các nguồn dữ liệu.
- Tránh phụ thuộc dữ liệu locale legacy `COMPAT` sau khi nâng JDK 23+.

## 2. Hai cơ chế cần hiểu: Java SPI và thứ tự locale provider

### 2.1. Java SPI (Service Provider Interface)

Một SPI là hợp đồng để Java hoặc ứng dụng tải các implementation cài thêm. Trong localization, các abstract provider classes nằm trong:

- `java.text.spi`: `NumberFormatProvider`, `DateFormatProvider`, `CollatorProvider`, `DecimalFormatSymbolsProvider` và những SPI tương ứng.
- `java.util.spi`: `LocaleServiceProvider` (lớp gốc), `CurrencyNameProvider`, `LocaleNameProvider`, `TimeZoneNameProvider`, v.v.

Ví dụ class:

```java
public final class PrefixNumberProvider
        extends NumberFormatProvider {
    // Phải triển khai các phương thức abstract được yêu cầu.
}
```

Chỉ riêng class này chưa được discover. Phải khai báo nó thông qua **provider-configuration file** hoặc metadata module. Đồng thời phải đưa artifact của nó vào đúng classpath/module path của tiến trình Java thực sự chạy ứng dụng.

### 2.2. java.locale.providers điều khiển nguồn ưu tiên

`java.locale.providers` là system property nhận danh sách provider cách nhau bằng dấu phẩy, ví dụ:

```text
SPI,CLDR,COMPAT
```

Với JDK 17, một cách diễn giải thông dụng là:

1. `SPI`: thử những implementation do ứng dụng/thư viện cài, với dịch vụ/locale phù hợp.
2. `CLDR`: thử dữ liệu Unicode CLDR của JDK nếu bước trước không đáp ứng.
3. `COMPAT`: thử dữ liệu legacy, nếu JDK còn hỗ trợ và không có nguồn trước đáp ứng.

**Trên JDK 23 trở lên, dữ liệu COMPAT/JRE đã bị loại bỏ.** Cấu hình trên vẫn có chữ COMPAT không làm legacy formatter sống lại. Đối với runtime hiện đại, một cấu hình điển hình là:

```bash
java -Djava.locale.providers=SPI,CLDR ...
```

**Hai cơ chế là độc lập:** `META-INF/services` giúp JVM tìm thấy implementation; `java.locale.providers` giúp locale service lookup chọn xét nguồn SPI theo thứ tự. Không đăng ký sẽ không được phát hiện; không đưa `SPI` vào provider preference của JDK ở classpath có thể khiến implementation có mặt nhưng không được factory sử dụng.

### 2.3. Discovered và selected là hai trạng thái khác nhau

| Câu hỏi | Cách kiểm tra | Điều chưa chứng minh |
| --- | --- | --- |
| Class provider có trong JAR không? | `jar --list --file` hoặc xem cấu trúc artifact. | Chưa chứng minh có service registry đúng. |
| File `META-INF/services` có trong JAR không? | Kiểm tra đường dẫn và nội dung UTF-8. | Chưa chứng minh provider class load được. |
| `ServiceLoader` thấy class không? | Iterate `ServiceLoader.load(NumberFormatProvider.class)`. | Chưa chứng minh factory đã chọn nó. |
| Provider khai báo hỗ trợ locale không? | `getAvailableLocales()`, `isSupportedLocale(locale)`. | Chưa chứng minh formatter trả đúng nội dung hoặc được ưu tiên. |
| Factory thật có dùng implementation không? | Gọi `NumberFormat.getNumberInstance(locale)` với cấu hình khởi động khác nhau; instrument method nếu cần. | Không đảm bảo mọi dịch vụ/locale khác cũng dùng SPI. |
| Khi provider không hỗ trợ thì sao? | Thử locale ngoài phạm vi. | Phải kiểm tra fallback và chính sách tương thích. |

**Không coi `ServiceLoader` trả về một instance là điều kiện đủ.** Một JAR có thể được load đúng nhưng runtime vẫn ưu tiên CLDR nếu startup option là `CLDR,SPI`, hoặc method yêu cầu một locale mà SPI không nhận.

## 3. Provider nào thường có trong JDK?

| Provider | Vai trò | Giới hạn |
| --- | --- | --- |
| `CLDR` | Dữ liệu Unicode Common Locale Data Repository, dùng rộng rãi trên JDK mới. | Dữ liệu có thể thay đổi giữa các phiên bản JDK; không phải mọi service dùng chính xác một nguồn. |
| `SPI` | Provider do ứng dụng hoặc thư viện cài. | Cần implementation, đăng ký, packaging, startup preference và test. |
| `HOST` | Một số locale data hoặc custom settings từ hệ điều hành. | Phụ thuộc OS/vendor, không phải nền tảng nào cũng có. |
| `COMPAT` / alias `JRE` | Dữ liệu legacy tương thích các JDK cũ. | Có ở JDK 17; bị loại bỏ từ JDK 23. |

Mặc định trên Oracle/OpenJDK 17 tương đương `CLDR,COMPAT`. Với Java 23+, legacy COMPAT không còn và nguồn mặc định chủ đạo là `CLDR`.

Đối với bài toán mở rộng **một locale/service cụ thể**, không nên đặt `HOST` hay `COMPAT` vào danh sách chỉ vì muốn “nhiều lựa chọn hơn”. Hãy ưu tiên cơ chế rõ nghĩa, xác định theo nhu cầu, rồi test trên JDK thực tế.

## 4. Thiết kế ví dụ: mở rộng NumberFormat cho một locale có sẵn

Ví dụ này dùng `Locale.FRANCE` để dễ **quan sát xung đột ưu tiên**: CLDR của JDK đã hỗ trợ locale đó; một SPI được cấu hình trước CLDR có thể ghi đè một số hành vi của dịch vụ định dạng số cho chính locale ấy.

Hành vi demo:

- `NumberFormat.getNumberInstance(Locale.FRANCE).format(12.5)` theo provider custom tạo `SPI:12.50`.
- Theo định dạng số tiếng Pháp từ JDK CLDR điển hình, cùng số tạo `12,5`.
- `Locale.US` không được provider custom khai báo hỗ trợ, do đó tiếp tục dùng formatter JDK, kết quả ví dụ `12.5`.
- Provider được discover qua `ServiceLoader` nhưng có thể **không được chọn** khi `CLDR` đứng trước `SPI`.

**Lưu ý:** tiền tố `SPI:` và dấu thập phân chấm ở ví dụ là **dấu hiệu kiểm chứng trong bài thực hành**, không phải quy tắc định dạng tiếng Pháp nên dùng trong sản phẩm. Custom provider production phải có dữ liệu và semantics thực sự phù hợp locale, không ghi dấu kiểm thử vào output người dùng.

### Cây thư mục mẫu

Tạo một thư mục riêng, không cần Maven/Gradle:

```text
spi-demo/
├── src/
│   └── demo/
│       ├── PrefixNumberProvider.java
│       └── ProviderCheck.java
└── resources/
    └── META-INF/
        └── services/
            └── java.text.spi.NumberFormatProvider
```

Hai class cùng package `demo`; tệp service registry nằm chính xác tại `resources/META-INF/services/java.text.spi.NumberFormatProvider`. Tên file **phải trùng tên đầy đủ của SPI class**, không phải tên implementation.

## 5. File thứ nhất: implementation NumberFormatProvider

Lưu vào `src/demo/PrefixNumberProvider.java`:

```java
package demo;

import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Currency;
import java.util.Locale;
import java.util.Objects;

public final class PrefixNumberProvider
        extends NumberFormatProvider {

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] { Locale.FRANCE };
    }

    @Override
    public boolean isSupportedLocale(Locale locale) {
        Objects.requireNonNull(locale, "locale");
        // Ví dụ chỉ nhận đúng fr-FR, không nhận extension.
        return Locale.FRANCE.equals(locale);
    }

    private static DecimalFormat create(String pattern) {
        return new DecimalFormat(
                pattern,
                DecimalFormatSymbols.getInstance(Locale.ROOT));
    }

    @Override
    public NumberFormat getNumberInstance(Locale locale) {
        return create("'SPI:'#,##0.00");
    }

    @Override
    public NumberFormat getIntegerInstance(Locale locale) {
        DecimalFormat format = create("'SPI:'#,##0");
        format.setParseIntegerOnly(true);
        return format;
    }

    @Override
    public NumberFormat getCurrencyInstance(Locale locale) {
        DecimalFormat format = new DecimalFormat(
                "'SPI:'¤#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.FRANCE));
        format.setCurrency(Currency.getInstance("EUR"));
        return format;
    }

    @Override
    public NumberFormat getPercentInstance(Locale locale) {
        // Dấu % trong DecimalFormat pattern mang semantics nhân 100.
        return create("'SPI:'#,##0%");
    }
}
```

**Đây là class Java hoàn chỉnh có thể biên dịch trên JDK 17+.** Nó triển khai bốn phương thức abstract cơ bản của `NumberFormatProvider`. Nó không phải thư viện production đầy đủ: nếu triển khai thật còn phải kiểm soát tất cả hàm parse, làm tròn, tiền tệ, Unicode numbering systems, các biến thể locale và yêu cầu UI.

### Vì sao getAvailableLocales quan trọng?

`getAvailableLocales()` công bố những locale mà provider cung cấp đối tượng/dữ liệu. Ở ví dụ:

```java
return new Locale[] { Locale.FRANCE };
```

Nếu khai báo locale không có implementation tương ứng, runtime có thể chọn provider sai rồi nhận output không hợp mong đợi. Đừng trả tất cả locale chỉ để “được gọi nhiều hơn”.

### isSupportedLocale và Unicode extensions

`LocaleServiceProvider.isSupportedLocale(locale)` mặc định so sánh các locale khả dụng mà **bỏ qua locale extensions**. Một số extension (ví dụ numbering system `u-nu-...`) có thể thay đổi yêu cầu định dạng số. Nếu implementation không hỗ trợ extension đó, nên định nghĩa rõ cách xử lý thay vì nhận mà âm thầm bỏ qua.

Ví dụ này override `isSupportedLocale` với kiểm tra `Locale.FRANCE.equals(locale)` nên chỉ nhận **chính xác fr-FR không có extensions**. Với ứng dụng thực, hãy xác định support matrix cho language tag, script, region, Unicode extensions và locale fallback; không chỉ kiểm tra chuỗi tên quốc gia.

### Vì sao factory tạo DecimalFormat trực tiếp?

Nếu trong method `getNumberInstance(Locale.FRANCE)` ta lại gọi:

```java
return NumberFormat.getNumberInstance(Locale.FRANCE);
```

và SPI đang được ưu tiên, lời gọi đó có thể quay về chính provider, gây vòng đệ quy. Demo tránh lỗi bằng `new DecimalFormat(pattern, symbols)`, sử dụng `DecimalFormatSymbols.getInstance(Locale.ROOT)` cho trường hợp số thử nghiệm, không gọi lại factory `NumberFormat` cho locale đang phục vụ.

**Lưu ý:** các service locale khác có thể có SPI riêng. Nếu provider của bạn phụ thuộc một factory khác, vẫn cần phân tích chuỗi phụ thuộc để tránh vòng lặp hoặc nhận dữ liệu không như ý khi SPI có nhiều service.

## 6. File thứ hai: probe để xác minh discovery và selection

Lưu vào `src/demo/ProviderCheck.java`:

```java
package demo;

import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Locale;
import java.util.ServiceLoader;

public final class ProviderCheck {

    public static void main(String[] args) {
        System.out.println("configured="
                + System.getProperty(
                        "java.locale.providers", "<default>"));

        boolean found = false;
        for (NumberFormatProvider provider :
                ServiceLoader.load(NumberFormatProvider.class)) {

            if (provider.getClass().getName().equals(
                    "demo.PrefixNumberProvider")) {
                found = true;
                System.out.println("supportsFR="
                        + provider.isSupportedLocale(Locale.FRANCE));
                System.out.println("supportsUS="
                        + provider.isSupportedLocale(Locale.US));
            }
        }
        System.out.println("discovered=" + found);

        System.out.println("frNumber="
                + NumberFormat.getNumberInstance(
                        Locale.FRANCE).format(12.5));
        System.out.println("usNumber="
                + NumberFormat.getNumberInstance(
                        Locale.US).format(12.5));
    }
}
```

Chương trình này **không mặc định rằng discovered=true thì JDK đã chọn SPI**. Nó đo ba điều khác nhau:

1. `ServiceLoader` có tìm ra class `demo.PrefixNumberProvider` không?
2. Class đó có khai báo hỗ trợ fr-FR nhưng không hỗ trợ en-US không?
3. Kết quả của **factory thực tế** có khác khi đổi thứ tự provider không?

Thứ tự vòng lặp `ServiceLoader` có thể khác nếu classpath có nhiều thư viện; demo chỉ in chi tiết của một class có tên xác định và một dòng `discovered`. Nếu thư viện khác có SPI cùng loại và cùng locale, cần xem lại ưu tiên giữa nhiều implementations và chính sách deploy.

### ServiceLoader trực tiếp không giống locale service lookup

`ServiceLoader.load(NumberFormatProvider.class)` tìm service implementations đã đăng ký; nó không yêu cầu `java.locale.providers` phải chứa SPI để **được liệt kê** theo cách chung của ServiceLoader. Còn `NumberFormat.getNumberInstance(...)` là locale-sensitive factory được JDK điều phối theo provider preference.

Vì vậy có thể xảy ra:

```text
discovered=true
frNumber=12,5
```

Điều này **không mâu thuẫn**. Provider đã được phát hiện, nhưng `CLDR` có thể đã đáp ứng yêu cầu trước khi đến SPI.

## 7. File thứ ba: đăng ký trong META-INF/services

Tạo file văn bản **không có phần mở rộng**:

```text
resources/META-INF/services/java.text.spi.NumberFormatProvider
```

Nội dung **chính xác một dòng**, là tên class provider đầy đủ:

```text
demo.PrefixNumberProvider
```

Theo contract ServiceLoader:

- Tên service file phải là **fully qualified name** của SPI: `java.text.spi.NumberFormatProvider`.
- Nội dung là một hoặc nhiều tên class cụ thể, mỗi dòng một class.
- File phải được lưu bằng **UTF-8**.
- Class phải có thể được class loader phù hợp nạp, truy cập và tạo instance.
- Dòng trống và comment bắt đầu bằng `#` có thể được bỏ qua.
- Không ghi `demo.ProviderCheck` thay cho provider; đó là class kiểm thử, không triển khai SPI.
- Với nhiều provider có thể ghi nhiều dòng, nhưng phải quản lý rõ khả năng hỗ trợ và tránh phụ thuộc thứ tự không bảo đảm khi các JAR khác cùng đăng ký.

**Chú ý PowerShell 5.1:** một số cách ghi text bằng `Set-Content -Encoding UTF8` có thể thêm UTF-8 BOM. Service registry yêu cầu UTF-8; BOM có thể khiến tên provider đầu file bị đọc sai. Dùng editor lưu **UTF-8 không BOM** hoặc cách sinh resource được build tool kiểm soát; đừng lưu thành UTF-16 hay tên file `.txt`.

### Jar phải chứa resource đúng vị trí

Sau khi đóng gói, bên trong JAR phải có đường dẫn:

```text
META-INF/services/java.text.spi.NumberFormatProvider
demo/PrefixNumberProvider.class
demo/ProviderCheck.class
```

Chỉ có tệp class mà thiếu metadata service thì `ServiceLoader` không có căn cứ tìm implementation. Chỉ có metadata mà thiếu class thì có thể gặp `ServiceConfigurationError` khi nạp provider.

## 8. Biên dịch, đóng gói và chạy từ command line

Đứng tại thư mục `spi-demo` chứa `src` và `resources`.

### Bước 1: compile cả hai class

```bash
javac -encoding UTF-8 -d out src/demo/PrefixNumberProvider.java src/demo/ProviderCheck.java
```

`-encoding UTF-8` chỉ định encoding của Java source file; nó **không tự chỉnh encoding mọi dữ liệu ở runtime**. `-d out` ghi `.class` vào đúng package directory dưới `out`.

### Bước 2: tạo JAR gồm class và resource

```bash
jar --create --file spi-demo.jar -C out . -C resources .
```

Lệnh `jar` của JDK 17+ này đưa cả compiled classes lẫn thư mục `META-INF/services` vào JAR. Có thể kiểm tra danh sách entry:

```bash
jar --list --file spi-demo.jar
```

Xác nhận có entry `META-INF/services/java.text.spi.NumberFormatProvider` và `demo/PrefixNumberProvider.class`. Lệnh liệt kê chỉ kiểm tra có entry, không chứng minh nội dung service file đúng; nếu `discovered=false`, hãy kiểm tra riêng nội dung resource trong artifact và lỗi runtime.

### Bước 3: chạy trong **JVM mới** với SPI ưu tiên

```bash
java -Djava.locale.providers=SPI,CLDR -cp spi-demo.jar demo.ProviderCheck
```

**Stdout kỳ vọng** với JDK 17+ có SPI hoạt động và CLDR tương ứng:

```text
configured=SPI,CLDR
supportsFR=true
supportsUS=false
discovered=true
frNumber=SPI:12.50
usNumber=12.5
```

Dòng `frNumber` chứa `SPI:` chứng minh factory thực tế sử dụng implementation custom trong cấu hình thử nghiệm; `usNumber` cho thấy locale khác vẫn dùng nguồn JDK có sẵn.

### Bước 4: khởi động tiến trình khác với CLDR ưu tiên

```bash
java -Djava.locale.providers=CLDR,SPI -cp spi-demo.jar demo.ProviderCheck
```

Trên runtime CLDR hỗ trợ `fr-FR` như các JDK hiện đại thông dụng, kết quả ví dụ:

```text
configured=CLDR,SPI
supportsFR=true
supportsUS=false
discovered=true
frNumber=12,5
usNumber=12.5
```

Chú ý `discovered=true` vẫn giữ nguyên, nhưng factory `frNumber` không còn tiền tố SPI. Vì `CLDR` được ưu tiên và có dữ liệu cho service/locale ấy, implementation custom không được chọn để format số này.

**Không dùng một kết quả cụ thể của CLDR như một giao thức cố định trên mọi JDK**. Locale data có thể thay đổi theo JDK/vendor; tuy nhiên, trên môi trường này, phép thử đủ minh họa cơ chế provider priority.

### Bước 5: chạy không đưa SPI JAR vào classpath

Nếu chỉ muốn xem formatter JDK, có thể tạo một Java main độc lập không tham chiếu implementation rồi chạy mà không có provider JAR. **Không chạy `demo.ProviderCheck` bằng classpath trống** bởi bản thân class main cũng nằm trong `spi-demo.jar`. Để mô phỏng SPI resource thiếu, tạo artifact thử nghiệm khác **có main nhưng không chứa provider registration**, rồi kiểm tra `discovered=false`; không xóa hoặc sửa artifact gốc đang deploy.

### Bước 6: lặp lại ở JDK và OS mục tiêu

Lưu lại JDK vendor/version, `java.locale.providers`, các locale/service được thử và output từng tiến trình. Khi nâng version, sự thay đổi output có thể đến từ CLDR data hoặc rule SPI; không tự kết luận do compiler hoặc encoding.

## 9. Cấu hình startup đúng chỗ

### 9.1. Thứ tự JVM options và application args

**Đúng:**

```bash
java -Djava.locale.providers=SPI,CLDR -cp spi-demo.jar demo.ProviderCheck
```

**Sai:**

```text
java -cp spi-demo.jar demo.ProviderCheck -Djava.locale.providers=SPI,CLDR
```

Dòng sai đặt `-D` **sau tên class**, nên thông thường đó là `args[]` cho ứng dụng, không phải system property khởi động JVM.

Với executable jar có `Main-Class`:

```bash
java -Djava.locale.providers=SPI,CLDR -jar application.jar
```

**Đặt property ở launcher của JVM chạy thật**, không chỉ ở terminal dùng để compile. Cấu hình Maven Surefire, Gradle Test, IDE Run/Debug, Docker entrypoint và application server phải được kiểm tra theo JVM cụ thể mà chúng khởi tạo.

### 9.2. Không đổi bằng System.setProperty sau initialization

`java.locale.providers` được đọc lúc runtime khởi động; trên JDK 17 tài liệu nêu gọi:

```java
System.setProperty("java.locale.providers", "SPI,CLDR");
```

**sau khi JVM chạy không đổi thứ tự provider đã chọn**. Vì vậy, để so sánh `SPI,CLDR` với `CLDR,SPI`, chạy hai processes, không đổi property trong một process rồi format lại.

Tương tự, `Locale.setDefault(Locale.FRANCE)` đổi locale mặc định của JVM, không phải property provider. Với ứng dụng nhiều người dùng, nên truyền locale cụ thể vào factory; không đổi default toàn JVM mỗi request.

### 9.3. Cấu hình trên nhiều JDK

- **JDK 17:** mặc định tương đương `CLDR,COMPAT`; muốn nạp SPI trên classpath phải đưa `SPI` vào preference.
- **JDK 21–22:** COMPAT/JRE đang ở giai đoạn cảnh báo loại bỏ; cần chuẩn bị migrate.
- **JDK 23+:** dữ liệu COMPAT/JRE legacy đã bị loại. Cấu hình `SPI,CLDR` vẫn hữu ích nếu custom SPI có mặt và được hỗ trợ.
- **HOST:** phụ thuộc nền tảng và không thay thế bước test provider SPI.

Khi cần output ổn định cho giao thức, định dạng dữ liệu bằng schema/ISO hoặc pattern cụ thể; đừng dùng CLDR output như key lưu trữ bất biến.

## 10. JPMS: đăng ký trong named module

Nếu dự án triển khai provider trong một **Java named module**, thay cho resource classpath kiểu truyền thống có thể khai báo provider bằng `module-info.java`:

```java
module custom.locale.provider {
    provides java.text.spi.NumberFormatProvider
        with demo.PrefixNumberProvider;
}
```

Ở phía **consumer named module** sử dụng trực tiếp `ServiceLoader`:

```java
module locale.demo.app {
    uses java.text.spi.NumberFormatProvider;
}
```

Đây là **hai mô tả module riêng**; chúng không thay thế cùng lúc trong một file `module-info.java`. Một main application dùng `NumberFormat.getNumberInstance(...)` có thể không cần trực tiếp gọi `ServiceLoader`, nên không nhất thiết phải khai báo `uses` chỉ để gọi factory Java core. Nhưng nếu consumer tự `ServiceLoader.load(NumberFormatProvider.class)` trong named module, `uses` là phần service dependency cần thiết.

Với modules, provider phải:

1. Có class implementation tương thích yêu cầu module/service loader.
2. Có `provides ... with ...` trong provider module.
3. Được đặt trên module path và **được đưa vào module graph/resolution** phù hợp.
4. Được JDK locale service xem xét khi `SPI` có mặt trong `java.locale.providers`.
5. Có test nhận diện trên Java command line thật và trong tool packaging thực tế.

Một lệnh chạy module minh họa:

```bash
java -Djava.locale.providers=SPI,CLDR --module-path mods -m locale.demo.app/demo.ProviderCheck
```

Lệnh trên **chỉ là cú pháp minh họa**, yêu cầu bạn đã biên dịch hai named modules vào `mods`, cấu hình `requires`/`provides`/`uses` đúng và module provider được resolve. Nó **không phải lệnh chạy cho bản JAR classpath ở mục 8**.

### Có nên để META-INF/services và provides cùng lúc?

Đừng giả định cách đóng gói trên classpath và named module là giống nhau. Với **explicit named module**, service provision nên được khai báo trong module descriptor. Với **classpath JAR**, `META-INF/services` là cơ chế truyền thống.

Khi có một thư viện hỗ trợ cả classpath lẫn module path, build/deploy phải test từng chế độ để tránh trùng service, service không được load hoặc provider module chưa nằm trong graph. `Automatic modules` và fat JAR/shading có các quy tắc riêng; không chỉ đổi extension rồi mặc định service discovery vẫn hoạt động.

## 11. Xác minh “có hỗ trợ locale” không giống “đang được chọn”

### 11.1. Kiểm tra provider-local capability

`getAvailableLocales()` trả mảng locale do provider khai báo. `isSupportedLocale(locale)` là phép kiểm tra chi tiết, có thể xét Unicode extensions. Hai phép này kiểm tra **provider có tuyên bố hỗ trợ hay không**.

Tài liệu `LocaleServiceProvider` nói default `isSupportedLocale` thường bỏ qua extensions. Trong demo, ta override để nhận chính xác `Locale.FRANCE`, không tự nhận numbering extension mà implementation chưa xử lý.

**Không suy diễn** chỉ cần `Locale.FRANCE` xuất hiện trong `NumberFormat.getAvailableLocales()` là custom SPI đã thắng. JDK CLDR cũng có thể hỗ trợ locale đó; method trả khả năng hỗ trợ tổng hợp, không đưa ra dấu vết provider nào đã được chọn.

### 11.2. Kiểm tra discovery

`ServiceLoader.load(NumberFormatProvider.class)` cho biết implementation được register và load được trong class loader/module context tương ứng.

Nếu xuất hiện `ServiceConfigurationError`, kiểm tra tên file, FQCN, constructor, class visibility, dependencies, lỗi module và UTF-8 encoding. Đừng catch rộng rồi im lặng trả `false` trong production: điều đó che giấu lỗi packaging quan trọng.

### 11.3. Kiểm tra selection bằng hành vi riêng và instrumentation

Chỉ khi factory thật gọi custom behavior thì bạn có thể nói SPI đã thực sự được chọn cho **dịch vụ và locale đang thử**. Demo dùng output tiền tố `SPI:`. Với production, nên viết test dựa trên marker/spy trong môi trường test, hoặc logging trong provider implementation, thay vì thêm dấu kiểm thử vào output người dùng.

**Một test locale không chứng minh mọi service đều dùng provider đó**: `NumberFormatProvider` không tự kiểm soát `DateFormat`, `DecimalFormatSymbolsProvider` hoặc `Collator`. Mỗi service có cơ chế và phạm vi hỗ trợ riêng.

### 11.4. Kiểm tra fallback

Một provider chỉ khai báo fr-FR không nên tự chiếm formatting en-US. Trong demo, `supportsUS=false` và factory en-US dùng dữ liệu JDK. Khi production provider hỗ trợ rất nhiều locale, thêm test những locale không hỗ trợ để phát hiện lỗi khai báo sai hoặc fallback không như dự kiến.

### 11.5. Kiểm tra sau nâng JDK

Locale data theo CLDR có thể thay đổi qua JDK versions; nên ghi cả code point khi so sánh Unicode whitespace. `12 345,67` có thể chứa dấu nhóm U+0020, U+00A0 hoặc U+202F khác nhau dù hiển thị gần giống. Đừng lưu chuỗi đã format như source of truth của giá trị số.

## 12. Những lỗi phổ biến khi đóng gói SPI

| Hiện tượng | Nguyên nhân hay gặp | Cách xác minh/sửa |
| --- | --- | --- |
| `discovered=false` | Thiếu `META-INF/services`, sai FQCN, provider JAR chưa trên classpath. | `jar --list --file`, inspect resource, kiểm tra launcher. |
| `ServiceConfigurationError` | File service sai UTF-8, tên class không tồn tại, provider không load được hoặc không có cấu trúc constructor phù hợp. | Xem exception gốc, class/module dependencies. |
| `discovered=true` nhưng không có prefix `SPI:` | `CLDR` trước `SPI` hoặc locale/service không thuộc support scope. | Kiểm tra `-Djava.locale.providers` và gọi factory với fr-FR. |
| `supportsFR=false` | `getAvailableLocales` hoặc `isSupportedLocale` khai báo không đúng. | Test trực tiếp Locale.FRANCE, extensions, country/language. |
| `supportsUS=true` ngoài ý muốn | Provider khai báo quá rộng. | Giới hạn support matrix; test locale ngoài phạm vi. |
| Chạy Maven/Gradle thấy khác IDE | JVM được truyền option khác nhau. | In `System.getProperty` trong process thực. |
| Đổi `System.setProperty` không tác dụng | Locale provider order đã đọc lúc startup. | Khởi động JVM mới với `-D`. |
| Provider dùng lại factory cùng locale | Nguy cơ recursion hoặc kết quả lặp không mong muốn. | Tạo formatter trực tiếp hoặc dùng dependency không tái nhập service. |
| Provider cho currency/percent sai | Không đáp ứng semantics formatter tương ứng. | Test phần trăm, tiền tệ, số âm, grouping, rounding và parse. |
| Test ra tiền tố theo một JDK nhưng khác JDK khác | Thay đổi source order/vendor/data hoặc deployment. | Ghi JDK version, provider options và registry artifact. |
| Fat JAR mất service registry | Shading/assembly không merge đúng `META-INF/services`. | Inspect artifact cuối cùng, chạy integration test. |
| Named module không thấy provider | Thiếu `provides`, `uses` hoặc provider chưa được resolve. | Kiểm tra module descriptor, module path, module graph. |
| CLDR output khác sau nâng JDK | CLDR data thay đổi, COMPAT đã bị loại bỏ. | Kiểm thử regression và dùng invariant format nếu cần. |

### Đừng làm sai semantics của service

Provider có thể được phát hiện và sử dụng mà vẫn **sai**. Một `NumberFormatProvider` production phải cho các formatter đáp ứng mục đích:

- `getNumberInstance`: trình bày số thông thường theo locale.
- `getIntegerInstance`: cách hiển thị/parse số nguyên theo hợp đồng.
- `getCurrencyInstance`: tiền tệ, ký hiệu, vị trí, làm tròn, các đơn vị tiền.
- `getPercentInstance`: tỷ lệ và semantics phần trăm (thường nhân giá trị với 100).
- Cách parse, dấu âm, grouping, chữ số Unicode và các special values phải được kiểm thử nếu domain hỗ trợ.

Không chỉ viết đủ bốn phương thức để compiler thôi báo lỗi. **Khả năng hỗ trợ** là một cam kết về hành vi, không chỉ một mảng Locale.

## 13. Kiểm thử và nghiệm thu một provider

Ma trận nên có:

| Thử nghiệm | Cách thử | Điều cần chứng minh |
| --- | --- | --- |
| Compile | `javac -encoding UTF-8` | Class/provider API chính xác với JDK 17+. |
| JAR registry | `jar --list --file` | Resource đúng path, không bị build tool làm mất. |
| Discovery | `ServiceLoader` | Implementation được load trên classpath/module path thực. |
| Capability | `getAvailableLocales`, `isSupportedLocale` | Đúng locale/extension đã công bố. |
| Selection | `SPI,CLDR` rồi `CLDR,SPI` trong hai process | Thứ tự nguồn ảnh hưởng provider được chọn khi cùng support. |
| Fallback | `Locale.US` ngoài scope custom | Không chiếm formatter của locale khác. |
| Startup | Đặt `-D` trước class/`-jar` | Cấu hình nằm trong JVM thực. |
| Alternative startup | Thử `System.setProperty` sau init | Không trông đợi thay chain giữa chừng. |
| Formatter semantics | Số âm, currency, integer, percent, parse | Output thực sự phù hợp loại formatter. |
| Unicode locale | Locale có chữ số hoặc extensions | Provider có chính sách rõ, không giả vờ hỗ trợ. |
| Upgrade | JDK 17, 21, 23+ | Không phụ thuộc legacy COMPAT ở JDK mới. |
| Concurrency | Nhiều request/thread | Formatter mutable không bị chia sẻ thiếu kiểm soát. |
| Final artifact | Classpath JAR và named module nếu cần | Cả hai dạng deploy đều nhận provider phù hợp. |

### Cẩn thận với NumberFormat mutable

`NumberFormat` và `DecimalFormat` là mutable, không mặc nhiên thread-safe. Một provider nên tạo **formatter instance mới** trong mỗi lời gọi factory, hoặc quản lý an toàn nếu có pooling/caching. Không trả về một `static DecimalFormat` dùng chung rồi cho request khác nhau thay currency/rounding mà không đồng bộ.

Class demo tạo formatter mới mỗi lần, phù hợp để thử. Với ứng dụng có performance yêu cầu cao, benchmark đúng workload rồi thiết kế reuse an toàn, không hi sinh correctness.

### Chọn hợp đồng ổn định cho dữ liệu máy–máy

Nếu ứng dụng truyền giá trị sang một service khác, đừng lưu `SPI:12.50` hay `12,5` làm giá trị tiền gốc. Nên giữ `BigDecimal`/giá trị số có kiểu và currency code riêng; UI format theo locale/provider. Như vậy thay provider hoặc CLDR không làm thay nghĩa dữ liệu lưu trữ.

## 14. Bài tập thực hành

**Bài 1 — Đăng ký chuẩn:** dựng cấu trúc `src/demo` và `resources/META-INF/services` như bài. Cố ý đổi sai tên file registry rồi chạy `ProviderCheck`. Quan sát `discovered=false`, sửa lại và chạy từ **JAR cuối cùng**, không chỉ từ IDE.

**Bài 2 — Kiểm tra thứ tự:** chạy `SPI,CLDR` và `CLDR,SPI` trong hai tiến trình Java. Giải thích tại sao `discovered=true` ở cả hai nhưng `frNumber` có thể khác.

**Bài 3 — Hỗ trợ locale/extension:** gọi trực tiếp `isSupportedLocale(Locale.FRANCE)`, `isSupportedLocale(Locale.US)` và một locale fr-FR có Unicode extension `u-nu-thai`. Thay đổi phương thức hỗ trợ chỉ khi provider thực sự xử lý đúng numbering system tương ứng.

**Bài 4 — Fallback:** dùng provider chỉ hỗ trợ `Locale.FRANCE`; thử `Locale.US` và `Locale.forLanguageTag("vi-VN")`. Không cần cố làm SPI thắng mọi locale. Test cái gì vẫn dùng CLDR/JDK.

**Bài 5 — Sửa lỗi packaging:** xóa provider class khỏi JAR thử nghiệm nhưng để service file; quan sát `ServiceConfigurationError`. Hãy tạo artifact thử nghiệm mới, không sửa file JAR đang deploy.

**Bài 6 — NumberFormat semantics:** mở rộng unit tests cho getIntegerInstance, getCurrencyInstance và getPercentInstance. Kiểm tra `0.125` hiển thị theo phần trăm, số âm, grouping, rounding và parse. Phân biệt tính đúng cú pháp với tính đúng định dạng ngôn ngữ.

**Bài 7 — Named module:** xây hai modules độc lập, provider khai báo `provides ... with ...`, consumer nếu tự gọi ServiceLoader khai báo `uses ...`. Đặt đúng module path và xác nhận provider được resolve.

**Bài 8 — JVM startup:** thử đặt property ở IDE, test fork và application server. Ghi JVM args, property trong process và JDK vendor/version. Trả lời vì sao đặt property ở build tool JVM không chắc áp dụng cho application JVM.

**Bài 9 — JDK migration:** trên môi trường JDK 17 còn COMPAT và một JDK 23+ đã bỏ COMPAT, kiểm tra behavior provider khi `SPI,CLDR` và policy fallback. Không dùng legacy data như một yêu cầu bắt buộc cho mọi Java 17+.

### Checklist hoàn thành

- [ ] Biết SPI khác class implementation và khác provider preference.
- [ ] Đóng gói đúng `META-INF/services/java.text.spi.NumberFormatProvider` UTF-8.
- [ ] Có class public triển khai đầy đủ abstract methods; biết cách package JAR.
- [ ] Đặt `-Djava.locale.providers=SPI,CLDR` đúng vị trí lúc startup.
- [ ] Phân biệt `ServiceLoader` discovery với factory selection.
- [ ] Dùng `getAvailableLocales`/`isSupportedLocale` cho support matrix.
- [ ] Có test fallback với locale khác, test same-locale khác thứ tự.
- [ ] Biết cơ chế `provides`/`uses` khi dùng named module.
- [ ] Không thay provider chain bằng System.setProperty sau runtime initialization.
- [ ] Không dựa vào COMPAT/JRE trên JDK 23+.
- [ ] Test semantics formatter, locale extensions, concurrency và final packaged artifact.
- [ ] Không lưu display string làm giao thức dữ liệu máy–máy.

## 15. Tham khảo chính thức

- **JDK 17 LocaleServiceProvider** — packaging, `getAvailableLocales`, `isSupportedLocale` và `java.locale.providers`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleServiceProvider.html
- **JDK 17 NumberFormatProvider** — các factory methods cần triển khai: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/spi/NumberFormatProvider.html
- **JDK 17 ServiceLoader** — provider configuration và service discovery: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- **JDK 23 Migration — COMPAT removal**: https://docs.oracle.com/en/java/javase/23/migrate/removed-tools-and-components.html

**Kết luận:** mở rộng localization trong Java phải đi qua chuỗi **đăng ký service đúng → cấu hình JVM đúng lúc → kiểm chứng discovery, capability, selection và fallback**. `ServiceLoader` thấy class chưa có nghĩa locale factory chọn nó; `SPI` nằm trong property chưa đủ nếu artifact hoặc service file sai; `getAvailableLocales` chỉ là lời công bố khả năng, chưa phải bằng chứng định dạng chính xác. Hãy kiểm thử end-to-end trên **JAR/module và JDK thực tế** trước khi xem một provider là đã hoạt động.
