# Locale được hỗ trợ và lựa chọn fallback trong Java Locale SPI

## 1. Vì sao “hỗ trợ locale” không chỉ là có một đối tượng Locale?

Java dùng `java.util.Locale` để biểu diễn ngôn ngữ, vùng lãnh thổ, hệ chữ, variant và Unicode extensions. Tuy nhiên, **tạo được một `Locale` không có nghĩa mọi dịch vụ i18n của JDK đều có dữ liệu chuyên biệt cho locale đó**.

Ví dụ:

~~~java
Locale requested = Locale.forLanguageTag("qaa-QA");
NumberFormat formatter = NumberFormat.getNumberInstance(requested);
~~~

Đây là snippet Java với import `java.util.Locale` và `java.text.NumberFormat`. `Locale.forLanguageTag(...)` chỉ xây dựng đối tượng chứa các subtag. `NumberFormat.getNumberInstance(...)` sau đó phải **lựa chọn một nguồn dữ liệu/implementation** phù hợp: dữ liệu CLDR do JDK cung cấp, một locale-sensitive service provider được cài đặt bằng SPI, hoặc cơ chế dự phòng khi không có dữ liệu chuyên biệt.

Chủ đề **Locale SPI** trả lời những câu hỏi sau:

- Một `LocaleServiceProvider` **quảng cáo những locale nào** bằng `getAvailableLocales()`?
- Khi Java gọi `isSupportedLocale(...)`, locale có extension, script hoặc region khác nhau được xét ra sao?
- JDK quyết định dùng **SPI**, **CLDR** hay **HOST** theo thứ tự nào?
- Điều gì xảy ra khi locale được yêu cầu không có provider hỗ trợ chính xác: có fallback về locale ít cụ thể hơn hoặc root không?
- Khi nhiều người dùng có locale riêng, liệu đổi `Locale.setDefault(...)` có phải cách chọn provider đúng?
- Làm thế nào đóng gói provider trên classpath hoặc module path, và làm sao kiểm thử provider có thực sự được chọn?
- Khác biệt giữa **Locale SPI fallback** và **ResourceBundle fallback** là gì?

Bài học ưu tiên **Java 17+ và API Java SE hiện hành**. Ví dụ có đầy đủ mã Java, file đăng ký service, lệnh biên dịch/chạy và output đã thử trên JDK 24.

## 2. Ba tầng cần phân biệt

~~~text
Ứng dụng
  |
  | requested Locale (ví dụ qaa-QA)
  v
NumberFormat.getNumberInstance(requested)
  |
  +--> Lựa chọn nguồn dịch vụ theo java.locale.providers
  |         |
  |         +--> SPI  : NumberFormatProvider do ứng dụng đóng gói
  |         +--> CLDR : dữ liệu i18n tích hợp của JDK
  |         +--> HOST : dữ liệu từ OS, nếu JDK/platform hỗ trợ
  |
  +--> Kiểm tra support của locale/candidate locales
  |         |
  |         +--> isSupportedLocale(...)
  |         +--> candidate ít cụ thể hơn khi cần
  |         +--> root khi không có dữ liệu chuyên biệt
  |
  v
NumberFormat thực tế
  |
  v
format(12.5)
~~~

Đây là **sơ đồ khái niệm**. Cơ chế nội bộ có thể khác nhau giữa các dịch vụ, nhưng những thành phần chính được định nghĩa trong JavaDoc `LocaleServiceProvider`.

| Khái niệm | Ý nghĩa | API quan sát |
| --- | --- | --- |
| **Requested locale** | Locale ứng dụng muốn dùng, có thể do user chọn | `Locale.forLanguageTag(...)` |
| **Available locales của một provider** | Các locale provider công bố có thể xử lý | `provider.getAvailableLocales()` |
| **Supported locale** | Kết quả kiểm tra provider có hỗ trợ locale yêu cầu không | `provider.isSupportedLocale(locale)` |
| **Provider preference** | Thứ tự nguồn dữ liệu i18n được ưu tiên | `-Djava.locale.providers=...` |
| **Candidate locale** | Locale ít cụ thể hơn được thử khi không tìm được support | Quy tắc trong JavaDoc `LocaleServiceProvider` và `ResourceBundle.Control` |
| **JDK root fallback** | Dữ liệu tối thiểu của môi trường Java | `Locale.ROOT` |
| **Service loader discovery** | JVM nhìn thấy implementation SPI trên classpath/module path | `ServiceLoader` / `META-INF/services` hoặc `provides` |

**Điểm cốt lõi:** “provider có mặt”, “provider quảng cáo locale”, “provider được cấu hình ưu tiên” và “provider thực sự được chọn cho lời gọi cụ thể” là **bốn điều khác nhau**.

## 3. `LocaleServiceProvider` và các SPI chuyên biệt

Superclass chuẩn:

~~~java
package java.util.spi;

public abstract class LocaleServiceProvider {
    public abstract Locale[] getAvailableLocales();
    public boolean isSupportedLocale(Locale locale) { /* ... */ }
}
~~~

Đây là **lược đồ chữ ký để giải thích API**, không phải mã được phép biên dịch để thay thế class JDK. `LocaleServiceProvider` nằm trong `java.util.spi` và có các subclass phục vụ từng nhóm i18n:

| SPI | Dịch vụ mà nó cung cấp |
| --- | --- |
| `java.text.spi.NumberFormatProvider` | Định dạng số, số nguyên, phần trăm, tiền tệ, compact number |
| `java.text.spi.DateFormatProvider` | Định dạng ngày/giờ kiểu `java.text.DateFormat` |
| `java.text.spi.DecimalFormatSymbolsProvider` | Ký hiệu thập phân, nhóm số, chữ số... |
| `java.text.spi.DateFormatSymbolsProvider` | Ký hiệu tháng, ngày, era cho `DateFormat` |
| `java.text.spi.CollatorProvider` | So sánh/sắp xếp chuỗi theo quy tắc ngôn ngữ |
| `java.text.spi.BreakIteratorProvider` | Ranh giới ký tự, từ, câu, dòng |
| `java.util.spi.LocaleNameProvider` | Tên hiển thị của ngôn ngữ/vùng/variant |
| `java.util.spi.CurrencyNameProvider` | Tên và ký hiệu tiền tệ |
| `java.util.spi.TimeZoneNameProvider` | Tên hiển thị của múi giờ |
| `java.util.spi.CalendarDataProvider` | Dữ liệu vùng cho lịch như ngày đầu tuần |
| `java.util.spi.CalendarNameProvider` | Tên các thành phần của `Calendar` |

**Mỗi SPI là một dịch vụ riêng.** Viết `NumberFormatProvider` cho `qaa-QA` không tự cung cấp dữ liệu cho `DateFormat`, `Collator` hoặc `Locale.getDisplayName()`. Ứng dụng phải xác định **loại dữ liệu địa phương hóa đang cần** và test trực tiếp factory method tương ứng.

Lưu ý về Java hiện đại: `java.time.format.DateTimeFormatter` thuộc API thời gian hiện hành, nhưng các provider `DateFormatProvider` ở trên là dành cho `java.text.DateFormat`. **Không mặc định việc viết một `DateFormatProvider` sẽ tùy biến mọi kết quả của `java.time`**. Nếu ứng dụng chủ yếu dùng `java.time`, hãy kiểm tra cơ chế locale data cụ thể của API đó.

## 4. `getAvailableLocales()`: tuyên bố khả năng của một provider

Mọi concrete subclass của `LocaleServiceProvider` phải cung cấp:

~~~java
@Override
public Locale[] getAvailableLocales() {
    return new Locale[] {
            Locale.forLanguageTag("qaa-QA")
    };
}
~~~

Đây là **snippet thuộc một implementation provider**, không phải một `main` độc lập. `qaa-QA` được chọn làm **locale thử nghiệm nhân tạo** để tránh nhầm với những locale thông thường mà CLDR đã hỗ trợ.

Theo hợp đồng JavaDoc:

- Mảng trả về liệt kê các locale mà **provider có thể cung cấp** đối tượng hoặc tên i18n cho dịch vụ tương ứng.
- Không đưa vào mảng hai `Locale` chỉ khác nhau bởi extensions.
- Không quảng cáo một locale rồi trả kết quả không đúng hợp đồng của factory method chuyên biệt.
- Với provider có nhiều locale, có thể trả một mảng nhiều phần tử; hãy viết test coverage cho **từng locale được quảng cáo**.
- Mảng từ provider **không đại diện** toàn bộ locale của JVM. JDK/CLDR và các provider khác có thể hỗ trợ thêm nhiều locale.

Ví dụ nếu provider chỉ quảng cáo `qaa-QA` thì không được tự kết luận nó cũng quảng cáo `qaa-QB` (cùng ngôn ngữ, khác region). Quan hệ cùng language không làm hai locale **bằng nhau**.

### 4.1. Các API “available locales” nhìn ở những phạm vi khác nhau

| API | Trả lời câu hỏi |
| --- | --- |
| `myProvider.getAvailableLocales()` | **Implementation này** công bố hỗ trợ locale nào? |
| `NumberFormat.getAvailableLocales()` | Các locale dịch vụ định dạng số có thể hỗ trợ theo nguồn/provider được triển khai và cấu hình |
| `Locale.getAvailableLocales()` | Tập locale từ Java runtime và những locale provider triển khai mà môi trường cung cấp |
| `Locale.availableLocales()` | Dòng `Stream<Locale>` tương ứng trong Java hiện hành |

Tập trả từ factory/service API không phải **danh sách các locale mà sản phẩm của bạn đã dịch đủ**. Một JDK có thể biết cách định dạng số cho hàng trăm locale, còn ứng dụng chỉ có UI translations cho hai ngôn ngữ.

Không dùng `NumberFormat.getAvailableLocales()` để tạo danh sách ngôn ngữ giao diện trong sản phẩm mà không qua **danh sách locale do ứng dụng thực sự hỗ trợ**. Danh sách trong UI, chính sách fallback của sản phẩm và khả năng của provider là các lớp trách nhiệm khác nhau.

### 4.2. `Locale` chứa language, script, region, variant và extensions

Một vài ví dụ:

~~~java
Locale a = Locale.forLanguageTag("fr-CA"); 
Locale b = Locale.forLanguageTag("zh-Hant-TW");
Locale c = Locale.forLanguageTag("qaa-QA-u-nu-latn");
~~~

Đây là các snippet Java có thể đặt trong method, với import `java.util.Locale`.

- `fr-CA`: tiếng Pháp tại Canada.
- `zh-Hant-TW`: tiếng Trung, chữ Hán phồn thể, vùng Taiwan.
- `qaa-QA-u-nu-latn`: locale giả lập có Unicode extension `nu` liên quan tới numbering system `latn`.

Một implementation provider có thể quan tâm **hoặc không** tới extension. Không mặc định rằng mọi biến thể có cùng language đều được provider hỗ trợ.

## 5. `isSupportedLocale(Locale)`: kiểm tra cả extensions thế nào?

`LocaleServiceProvider.isSupportedLocale(Locale)` có implementation mặc định:

- Kiểm tra locale được hỏi với danh sách từ `getAvailableLocales()`.
- Mặc định **bỏ qua locale extensions khi so sánh**.
- Trả `true` nếu locale, sau khi bỏ extension, khớp một trong các locale provider quảng cáo.
- Trả `false` nếu không khớp; truyền `null` gây `NullPointerException`.

Nếu provider quảng cáo `qaa-QA`, thì:

| Locale được hỏi | `isSupportedLocale` mặc định | Vì sao |
| --- | --- | --- |
| `qaa-QA` | `true` | Khớp locale được quảng cáo |
| `qaa-QA-u-nu-latn` | `true` | Extension bị bỏ qua khi so sánh mặc định |
| `qaa-QB` | `false` | Region khác, provider không quảng cáo |
| `qaa` | `false` | Language-only khác exact locale trong danh sách |
| `fr-CA` | `false` | Không thuộc tập provider giả lập |

**Không có nghĩa provider bỏ qua extensions về mặt dữ liệu.** Hành vi mặc định chỉ nói rằng **bước kiểm tra support** bỏ qua extensions. Nếu dịch vụ cần tuân thủ Unicode extension (ví dụ hệ chữ số `nu`), subclass có thể override `isSupportedLocale(...)` và hỗ trợ đúng những extension mà implementation thật hiểu.

Mẫu kiểm tra có chủ đích:

~~~java
@Override
public boolean isSupportedLocale(Locale locale) {
    if (locale == null) {
        throw new NullPointerException("locale");
    }
    // Quy tắc riêng của provider cho vùng, script, extension...
    return super.isSupportedLocale(locale);
}
~~~

Đây là **snippet hướng dẫn cấu trúc**, không cần override như vậy nếu bạn muốn đúng hành vi mặc định. Trong ví dụ hoàn chỉnh bên dưới, chúng ta **không override** và kiểm thử rằng extension `-u-nu-latn` không làm mất support.

### 5.1. Khi gọi factory, locale truyền vào không nhất thiết là candidate hỗ trợ

Theo JavaDoc, nếu không có service hỗ trợ trực tiếp requested locale, JDK thử các candidate locale bớt cụ thể hơn. **Ngay cả khi tìm thấy support ở một candidate**, method chuyên biệt của provider nhận **locale yêu cầu ban đầu**, kể cả các extensions, thay vì mặc định được truyền object candidate đã rút gọn.

Hệ quả: nếu provider công bố chỉ hỗ trợ `fr` nhưng JDK gọi để giải quyết yêu cầu `fr-CA` thông qua candidate `fr`, implementation phải được thiết kế và kiểm thử cho tình huống factory nhận `fr-CA`. Không dùng quy tắc “`locale phải bằng đúng một phần tử của `getAvailableLocales()`” theo cách máy móc nếu API có thể được gọi qua fallback.

Với extension `-u-nu-*`, nếu provider hứa hỗ trợ nhiều numbering systems, factory phải thực sự xử lý được chúng hoặc quy định chính sách fallback rõ ràng. Trả `NumberFormat` có chữ số Latin mặc định cho mọi numbering system mà không xem xét nhu cầu người dùng có thể không phù hợp cho sản phẩm quốc tế hóa.

## 6. Cơ chế lựa chọn và fallback của Java Locale SPI

JavaDoc `LocaleServiceProvider` mô tả quy trình theo ý nghĩa:

1. Một API locale-sensitive (ví dụ `NumberFormat.getNumberInstance(requested)`) bắt đầu với locale được yêu cầu.
2. Môi trường chọn nguồn dữ liệu/implementation theo **thứ tự locale data providers** được cấu hình.
3. JDK hoặc `LocaleServiceProvider` tương ứng được hỏi về support cho locale.
4. Nếu không nguồn/provider nào hỗ trợ locale trực tiếp, JDK tạo **danh sách candidate locales** và thử từng mức ít cụ thể hơn.
5. Cuối cùng, các locale-sensitive services phải có mức tối thiểu ở **root locale** để quá trình dừng được.

Danh sách candidate dùng thuật toán tương tự quy tắc mặc định của `ResourceBundle.Control.getCandidateLocales(...)`. Với locale đơn giản, có thể hình dung:

~~~text
requested fr-CA
     |
     v
candidate fr-CA
     |
     v
candidate fr
     |
     v
root
~~~

Nhưng trong trường hợp có **script, region, variant hoặc xử lý đặc thù một số ngôn ngữ**, danh sách có thể nhiều bước hơn. Đừng tự viết thuật toán chỉ cắt `-CA` khỏi chuỗi locale cho tất cả trường hợp.

### 6.1. Không fallback sang locale “anh em” một cách tùy tiện

Nếu chỉ có custom provider cho `qaa-QA`, yêu cầu `qaa-QB` không mặc nhiên chuyển ngang từ `qaa-QB` sang `qaa-QA`. Các locale này là hai nhánh region **cùng cấp**, không phải quan hệ parent-child.

Trong ví dụ, với `-Djava.locale.providers=SPI,CLDR`:

~~~text
qaa-QA     -> custom SPI formatter
qaa-QA-u-nu-latn -> custom SPI formatter (extension ignored for support)
qaa-QB     -> no matching custom candidate; JDK/CLDR fallback
~~~

Kết quả cuối của `qaa-QB` trong môi trường thử là chuỗi số thông thường `12.5`, không có tiền tố `SPI:`. Đây là **quan sát từ demo JDK 24**, không phải cam kết rằng mọi CLDR version/locale/provider đều có cùng cách viết dấu thập phân và dấu nhóm.

### 6.2. Một provider dành cho locale cha có thể nhận yêu cầu locale con

Nếu một provider hỗ trợ `fr`, request `fr-CA` có thể được giải quyết thông qua candidate `fr` theo quy tắc tìm kiếm dịch vụ. Trong trường hợp đó, implementation nên cân nhắc semantics của region Canada và không giả định argument method luôn có `getCountry().isEmpty()`.

Nhưng **một factory khác có thể đã được CLDR/HOST đáp ứng trước**, tùy thứ tự nguồn dữ liệu. Việc có provider không đủ để khẳng định nó chắc chắn được gọi.

### 6.3. Name providers có một đường fallback bổ sung

Các subclass **cung cấp tên** (ví dụ `LocaleNameProvider`, `CurrencyNameProvider`, `TimeZoneNameProvider`, `CalendarNameProvider`) được phép trả `null` đối với một tên cụ thể mà chúng chưa có, dù locale được đánh dấu supported. Khi đó lookup có thể tiếp tục tìm nguồn/candidate tiếp theo theo đặc tả.

Điều này **khác** với những provider tạo đối tượng định dạng (ví dụ `NumberFormatProvider`), nơi các factory methods được kỳ vọng trả đúng đối tượng `NumberFormat` chứ không dùng `null` như một “không biết tên”. Không suy ra rằng tất cả SPI subclasses đều có cùng quy tắc thiếu dữ liệu.

## 7. `java.locale.providers`: chọn SPI, CLDR hoặc HOST

Đối với JDK hiện hành, JavaDoc liệt kê những nguồn dữ liệu locale chính:

| Tên cấu hình | Vai trò |
| --- | --- |
| `SPI` | Các implementation của `LocaleServiceProvider` được triển khai trong ứng dụng |
| `CLDR` | Dữ liệu chuẩn do Unicode Consortium Common Locale Data Repository cung cấp, tích hợp vào JDK |
| `HOST` | Cài đặt locale từ hệ điều hành, khi JDK/platform có provider loại này |

JDK hiện hành **mặc định ưu tiên CLDR**. Nếu ứng dụng muốn custom SPI được sử dụng, cần cấu hình SPI tường minh bằng system property **`java.locale.providers`**, ví dụ:

~~~sh
java -Djava.locale.providers=SPI,CLDR -cp out demo.LocaleSpiDemo
~~~

Khi đó:

1. Tìm nguồn **SPI** trước cho locale/service được yêu cầu.
2. Nếu SPI không có hỗ trợ phù hợp, thử **CLDR**.
3. Nếu cần thiết, tiếp tục tìm candidate locales theo thuật toán hiện hành và về root khi không có khả năng đáp ứng chuyên biệt.

Trong khi đó:

~~~sh
java -Djava.locale.providers=CLDR -cp out demo.LocaleSpiDemo
~~~

cấu hình chỉ dùng CLDR. Provider class vẫn có thể xuất hiện trên classpath và được `ServiceLoader` tìm thấy, nhưng **các factory locale-sensitive của JDK sẽ không tự chọn nó chỉ vì file service tồn tại**. Đó là một test âm tính hữu ích.

### 7.1. Vì sao phải đặt property trên dòng lệnh khởi động?

Theo JavaDoc `LocaleServiceProvider`, thứ tự `java.locale.providers` được **đọc và cache khi các lớp liên quan khởi tạo**. Do đó nên đặt bằng option `-D...` trên **java launcher** hoặc cấu hình JVM của ứng dụng.

Không thiết kế như sau:

~~~java
System.setProperty("java.locale.providers", "SPI,CLDR");
NumberFormat format = NumberFormat.getNumberInstance(requested);
~~~

Đây là **snippet không được khuyến nghị**. Nếu locale subsystem đã khởi tạo trước khi gọi `setProperty`, thứ tự provider có thể không thay đổi theo kỳ vọng. Với unit/integration tests cần so sánh nhiều cấu hình, **khởi chạy JVM riêng cho mỗi cấu hình** như hai lệnh demo bên dưới.

### 7.2. `HOST` phụ thuộc hệ điều hành và bản JDK

Không phải mọi JDK/platform đều có cùng tập dữ liệu HOST. Trên một số nền tảng, HOST phản ánh các thiết lập hệ thống cho cách định dạng số/ngày, nhưng ứng dụng cần fallback sang CLDR hoặc cấu hình rõ các nguồn khác.

**Không dùng các provider compatibility đã bị loại bỏ** như `COMPAT`/`JRE` làm nền tảng cho tài liệu Java hiện hành. Trên các JDK mới, CLDR là lựa chọn mặc định; nếu cần kiểm thử khác biệt do nâng JDK, hãy kiểm tra CLDR version thực tế của bản triển khai.

### 7.3. Cấu hình provider không phải chính sách ngôn ngữ của sản phẩm

`java.locale.providers=SPI,CLDR` quyết định **nguồn dữ liệu i18n**; nó **không chọn locale của từng người dùng**. Sản phẩm vẫn phải giải quyết riêng:

- Người dùng yêu cầu locale nào?
- Locale nào được UI/backend chính thức hỗ trợ?
- Có cần dùng preference dự phòng khi request ngoài danh sách?
- Định dạng số, ngày/giờ và tên hiển thị có dùng cùng locale hay không?
- Nếu SPI và CLDR cùng xử lý một locale, ưu tiên provider nào theo cấu hình và semantics sản phẩm?

Không dùng một cấu hình JVM toàn cục để thay thế bước negotiation/validation theo request.

## 8. Đăng ký provider đúng cách

### 8.1. Classpath: `META-INF/services`

Cho một custom `NumberFormatProvider`:

~~~text
locale-spi-demo/
├── src/
│   └── demo/
│       ├── DemoNumberProvider.java
│       └── LocaleSpiDemo.java
└── out/
    ├── demo/
    │   ├── DemoNumberProvider.class
    │   └── LocaleSpiDemo.class
    └── META-INF/
        └── services/
            └── java.text.spi.NumberFormatProvider
~~~

File **`out/META-INF/services/java.text.spi.NumberFormatProvider`** chứa đúng một dòng:

~~~text
demo.DemoNumberProvider
~~~

Quy tắc:

- Tên file là **fully qualified name của service class**, ở đây `java.text.spi.NumberFormatProvider`.
- Nội dung là **fully qualified name của provider implementation**, ở đây `demo.DemoNumberProvider`.
- File service descriptor dùng encoding UTF-8.
- Concrete provider cần là class có thể tạo instance bằng cơ chế service loading; ví dụ có constructor public mặc định do không khai báo constructor khác.
- File descriptor và class implementation phải **cùng khả năng được system class loader tìm thấy**, không chỉ nằm ở một đường dẫn tuỳ ý không tham gia classpath.
- Nếu đóng gói vào JAR, giữ nguyên các đường dẫn `META-INF/services/...` cùng file `demo/DemoNumberProvider.class`.

**Không đặt file service vào thư mục `src/demo` với tên tùy ý rồi nghĩ Java sẽ tự nhận.** Dịch vụ được phát hiện theo đường dẫn `META-INF/services/<service-FQN>` hoặc theo `provides` trong named module.

### 8.2. Named module: `provides`

Khi đóng gói **provider** thành named module, có thể khai báo:

~~~java
module demo.locale.provider {
    provides java.text.spi.NumberFormatProvider
            with demo.DemoNumberProvider;
}
~~~

Đây là **đoạn `module-info.java` minh họa cho một cách đóng gói khác**, không nằm trong ví dụ classpath đã kiểm thử ở mục 10. Để chạy chế độ module, cần chuyển cấu trúc source/output sang module path, biên dịch module, bảo đảm provider module được giải quyết vào module graph và cấu hình `java.locale.providers` có `SPI`.

Không bắt buộc dùng cả `META-INF/services` lẫn `provides` cho cùng một provider; chọn cơ chế khớp với cách deploy. Classpath demo chủ đích dùng file descriptor để dễ thực hành với `javac --release 17`.

## 9. Thiết kế provider thực tế và các yêu cầu về chất lượng

Provider demo sẽ dùng một locale giả lập `qaa-QA` để output dễ nhận biết. `getNumberInstance` trả `DecimalFormat` với prefix `SPI:`, nhờ vậy ta phân biệt trực tiếp formatter của custom provider và formatter từ CLDR.

Các phương thức abstract của `NumberFormatProvider` gồm:

~~~java
NumberFormat getNumberInstance(Locale locale);
NumberFormat getIntegerInstance(Locale locale);
NumberFormat getCurrencyInstance(Locale locale);
NumberFormat getPercentInstance(Locale locale);
~~~

Đây là **tóm tắt chữ ký API**, không phải một class Java hoàn chỉnh. Trong ví dụ, chúng ta triển khai cả bốn phương thức để class có thể được khởi tạo.

Một số nguyên tắc:

1. Mỗi lời gọi trả **một đối tượng formatter mới**, không phát tán một `DecimalFormat` mutable dùng chung trong nhiều thread. Nhiều lớp `NumberFormat` không bảo đảm thread-safe khi bị nhiều thread sửa cùng instance.
2. Dùng `DecimalFormatSymbols.getInstance(Locale.ROOT)` để lấy các ký hiệu cho **giá trị trong fixture**, tránh phụ thuộc locale máy khi chỉ cần đánh dấu kết quả. Đây không phải cách sản xuất để thay thế ký hiệu bản địa.
3. `getIntegerInstance` cần phù hợp semantics định dạng số nguyên, bao gồm rounding và parse-integer-only; demo đặt `RoundingMode.HALF_EVEN` và `setParseIntegerOnly(true)`.
4. `getPercentInstance` nên nhân tỉ lệ theo quy tắc của `DecimalFormat` với dấu `%`. Demo dùng pattern định dạng phần trăm mang nhãn `SPI-PCT:`.
5. `getCurrencyInstance` trong sản phẩm thật phải dùng currency symbol, fraction digits, locale và tiền tệ thích hợp. Demo dùng nhãn giả `SPI-CUR:` **chỉ để nhận diện provider**, không đại diện cách format tiền tệ đúng cho Qatar hay bất kỳ thị trường nào.
6. `getCompactNumberInstance(...)` có API trên `NumberFormatProvider`; implementation mặc định có thể ném `UnsupportedOperationException`. Nếu sản phẩm cần compact number formatting cho locale mới, cần override và kiểm thử riêng. Ví dụ không gọi phương thức compact.

Một provider quảng cáo `qaa-QA` nhưng chỉ thực hiện đúng `getNumberInstance` còn ba phương thức kia trả null/sai định dạng sẽ tạo một SPI không đáng tin. Hãy giới hạn các locale được quảng cáo ở những nơi implementation thực sự đáp ứng hợp đồng đã cam kết.

## 10. Ví dụ Java 17+ chạy được: custom NumberFormatProvider và fallback

Bài thực hành gồm **hai file Java + một file service descriptor**. Nó không cần thư viện bên ngoài, không thay đổi source JDK, không cần ghi registry hay hệ thống locale của OS.

Kết quả giúp phân biệt:

- Provider tự công bố `qaa-QA`.
- `isSupportedLocale` chấp nhận exact locale và extension theo implementation mặc định; không nhận region sibling.
- `ServiceLoader` tìm được provider file, dù không chắc JDK sẽ dùng provider đó.
- `NumberFormat.getAvailableLocales()` phản ánh locale provider được bật khi `SPI` nằm trong `java.locale.providers`.
- Với `SPI,CLDR`: custom formatter được dùng cho `qaa-QA` và biến thể Unicode extension.
- Với `CLDR`: dù service descriptor vẫn load được, `NumberFormat` sử dụng CLDR/root thay vì custom provider.
- Với `qaa-QB`: provider chỉ hỗ trợ `qaa-QA`, nên request vùng khác không “nhảy ngang” sang formatter giả lập.

### 10.1. Provider: `src/demo/DemoNumberProvider.java`

~~~java
package demo;

import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Locale;

public final class DemoNumberProvider extends NumberFormatProvider {
    private static final Locale DEMO = Locale.forLanguageTag("qaa-QA");

    @Override
    public Locale[] getAvailableLocales() {
        return new Locale[] {DEMO};
    }

    private static DecimalFormat create(String pattern) {
        return new DecimalFormat(pattern,
                DecimalFormatSymbols.getInstance(Locale.ROOT));
    }

    @Override
    public NumberFormat getNumberInstance(Locale locale) {
        return create("'SPI:'0.00");
    }

    @Override
    public NumberFormat getIntegerInstance(Locale locale) {
        DecimalFormat format = create("'SPI-INT:'0");
        format.setRoundingMode(RoundingMode.HALF_EVEN);
        format.setParseIntegerOnly(true);
        return format;
    }

    @Override
    public NumberFormat getCurrencyInstance(Locale locale) {
        return create("'SPI-CUR:'0.00");
    }

    @Override
    public NumberFormat getPercentInstance(Locale locale) {
        return create("'SPI-PCT:'0%");
    }
}
~~~

**Cách đọc:**

- `getAvailableLocales()` chỉ quảng cáo `qaa-QA`; không quảng cáo `qaa-QB` hoặc tất cả các locale có language `qaa`.
- `LocaleServiceProvider.isSupportedLocale(...)` mặc định bỏ qua extension. Chương trình sẽ kiểm tra behavior này thay vì chỉ mô tả bằng lời.
- `create("'SPI:'0.00")` tạo `DecimalFormat` mới mang dấu hiệu dễ kiểm tra; `12.5` được định dạng `SPI:12.50`.
- Constructor không được khai báo trong class nên compiler tạo constructor mặc định public phù hợp visibility của class public; `ServiceLoader` có thể khởi tạo provider.
- Ví dụ deliberately tối giản: methods không đọc argument `locale` để biến đổi output theo vùng. Một provider production phải xử lý locales/extensions đã quảng cáo theo đúng nhu cầu i18n, không chỉ in marker cố định.
- Bốn nhánh number/integer/currency/percent được triển khai nhằm bảo đảm provider là một class cụ thể hợp lệ; bài thực hành chỉ gọi **number**.

### 10.2. Client: `src/demo/LocaleSpiDemo.java`

~~~java
package demo;

import java.text.NumberFormat;
import java.text.spi.NumberFormatProvider;
import java.util.Arrays;
import java.util.Locale;
import java.util.ServiceLoader;

public final class LocaleSpiDemo {
    public static void main(String[] args) {
        Locale exact = Locale.forLanguageTag("qaa-QA");
        Locale withExtension = Locale.forLanguageTag("qaa-QA-u-nu-latn");
        Locale unsupported = Locale.forLanguageTag("qaa-QB");

        DemoNumberProvider provider = new DemoNumberProvider();
        System.out.println("Provider locales: "
                + Arrays.toString(provider.getAvailableLocales()));
        System.out.println("Supports exact: "
                + provider.isSupportedLocale(exact));
        System.out.println("Supports with extension: "
                + provider.isSupportedLocale(withExtension));
        System.out.println("Supports other region: "
                + provider.isSupportedLocale(unsupported));

        boolean serviceFound = ServiceLoader.load(NumberFormatProvider.class)
                .stream().anyMatch(p -> p.type() == DemoNumberProvider.class);
        System.out.println("Service file found: " + serviceFound);

        boolean advertised = Arrays.stream(NumberFormat.getAvailableLocales())
                .anyMatch(exact::equals);
        System.out.println("NumberFormat advertises locale: " + advertised);
        System.out.println("Exact: "
                + NumberFormat.getNumberInstance(exact).format(12.5));
        System.out.println("With extension: "
                + NumberFormat.getNumberInstance(withExtension).format(12.5));
        System.out.println("Other region: "
                + NumberFormat.getNumberInstance(unsupported).format(12.5));
    }
}
~~~

**Chú ý về test:**

- `ServiceLoader.load(NumberFormatProvider.class).stream()` chứng minh class và descriptor có thể được phát hiện. Nó **không chứng minh NumberFormat thực sự chọn SPI**.
- `NumberFormat.getAvailableLocales()` hiển thị tập locale mà dịch vụ NumberFormat quảng cáo trong chế độ đang chạy.
- `getNumberInstance(...)` mới là phép thử **end-to-end** xem nguồn dữ liệu nào đang được chọn.
- Cả ba locale đều được tạo từ `Locale.forLanguageTag`; điều đó không đồng nghĩa cả ba có provider riêng.
- `NumberFormat` không có phương thức chuẩn tương đương `ResourceBundle.getLocale()` để đọc locale bundle được chọn. Ví dụ dùng marker trong output để quan sát provider; ứng dụng production nên có test/telemetry riêng thay vì suy luận mọi kết quả chỉ từ chuỗi hiển thị.

### 10.3. File service descriptor

Đặt tại **`out/META-INF/services/java.text.spi.NumberFormatProvider`**:

~~~text
demo.DemoNumberProvider
~~~

Nội dung chỉ là tên class, **không** có dấu ngoặc kép, chú thích Java hay tên module. Nếu dùng Maven/Gradle, file descriptor thường được đặt trong `src/main/resources/META-INF/services/java.text.spi.NumberFormatProvider` rồi được đóng vào JAR. Ví dụ thuần `javac` đặt trực tiếp trong `out` cho đơn giản.

### 10.4. Lệnh biên dịch và chạy

Tạo thư mục từ project root:

~~~sh
mkdir -p out/META-INF/services
~~~

Trên Windows PowerShell, thay lệnh tạo thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force out/META-INF/services | Out-Null
~~~

Tạo file descriptor với đúng nội dung đã nêu (trong editor, encoding UTF-8) rồi dùng:

~~~sh
javac --release 17 -d out src/demo/DemoNumberProvider.java src/demo/LocaleSpiDemo.java
java -Djava.locale.providers=SPI,CLDR -cp out demo.LocaleSpiDemo
java -Djava.locale.providers=CLDR -cp out demo.LocaleSpiDemo
~~~

Tại Windows, Linux và macOS, cú pháp trên tương đương vì chỉ sử dụng **một đường dẫn** `out` trong `-cp`. Nếu classpath có nhiều đường dẫn, dấu phân cách khác nhau theo OS; không nối tùy tiện bằng dấu `:` trên Windows.

**Chạy mỗi cấu hình trong JVM riêng**. Không thử `System.setProperty("java.locale.providers", ...)` giữa hai lần factory call trong cùng process vì thứ tự provider có thể đã được JDK cache từ lúc khởi tạo subsystem.

### 10.5. Kết quả chính xác với `SPI,CLDR`

Đã biên dịch bằng `javac --release 17` và chạy trên JDK 24 trong môi trường kiểm thử:

~~~text
Provider locales: [qaa_QA]
Supports exact: true
Supports with extension: true
Supports other region: false
Service file found: true
NumberFormat advertises locale: true
Exact: SPI:12.50
With extension: SPI:12.50
Other region: 12.5
~~~

Giải thích:

1. `[qaa_QA]` là biểu diễn `Locale.toString()` của locale custom trong mảng; input BCP 47 của nó là `qaa-QA`.
2. `Supports with extension: true` xác nhận implementation mặc định của `isSupportedLocale` bỏ qua `-u-nu-latn` khi so khớp support.
3. `Supports other region: false` cho biết `qaa-QB` không thuộc tập công bố.
4. `Service file found: true` chứng minh descriptor và implementation đã được load qua `ServiceLoader`.
5. `NumberFormat advertises locale: true` cho biết dịch vụ NumberFormat đã đưa locale từ SPI vào tập locale quảng cáo khi SPI được bật.
6. Hai dòng bắt đầu `SPI:` chứng minh provider được chọn cho locale custom.
7. `Other region: 12.5` cho thấy JDK dùng nguồn dữ liệu dự phòng thay vì formatter sibling `qaa-QA`.

### 10.6. Kết quả chính xác với `CLDR`

Chạy trong **JVM riêng** với `-Djava.locale.providers=CLDR`:

~~~text
Provider locales: [qaa_QA]
Supports exact: true
Supports with extension: true
Supports other region: false
Service file found: true
NumberFormat advertises locale: false
Exact: 12.5
With extension: 12.5
Other region: 12.5
~~~

Những điều không đổi:

- Mã provider vẫn có thể được khởi tạo trực tiếp bằng `new DemoNumberProvider()`.
- `getAvailableLocales/isSupportedLocale` của object provider trực tiếp vẫn có kết quả như trước.
- File `META-INF/services` vẫn được `ServiceLoader` nhìn thấy.

Điều thay đổi:

- `NumberFormat` **không đưa locale custom vào tập locale do chế độ CLDR này cung cấp**.
- Cả ba lời gọi factory không dùng marker `SPI:`; JDK fallback về formatter có sẵn.

**Đây là phép thử quan trọng nhất để tránh “đã đăng ký provider nhưng thực ra không được dùng”.** Thử `ServiceLoader` thành công không đủ; cần test chính API i18n của JDK và cấu hình `java.locale.providers`.

### 10.7. Không áp dụng output số thập phân của fixture như một hợp đồng toàn cầu

Đối với locale thật, `NumberFormat.format(12.5)` phụ thuộc CLDR data, provider order, hệ chữ số, pattern, vùng và JDK version. Chuỗi `12.5` trong nhánh không SPI là **kết quả đã xác minh của fixture trên JDK 24**, không bảo đảm cho mọi OS/JDK/provider khác.

Nếu cần test ổn định xuyên các version, nên assert **bất biến có ý nghĩa** như custom provider được gọi với marker, khả năng parse/format theo contract, và fallback không sử dụng provider cho locale sibling; tránh khẳng định dấu phân cách của CLDR là bất biến khi nâng phiên bản.

## 11. Lựa chọn fallback ở tầng ứng dụng

Locale SPI fallback thuộc **môi trường Java**; nhưng nhiều ứng dụng cần một chính sách sản phẩm riêng. Ví dụ backend hỗ trợ UI ở `vi-VN`, `en-US` và `fr-FR`, trong khi JDK hỗ trợ định dạng số cho nhiều locale hơn.

Một flow hợp lý:

~~~text
User preference / HTTP Accept-Language
                  |
                  v
       Parse và validate Locale
                  |
                  v
   Chọn từ tập locale ứng dụng hỗ trợ
                  |
                  +--> Có locale chính xác? chọn nó
                  |
                  +--> Có cùng language phù hợp? theo product policy
                  |
                  +--> Không có? dùng product default
                  |
                  v
   chosen Locale cho từng request
                  |
          +-------+--------+
          |                |
          v                v
 NumberFormat/JDK SPI   ResourceBundle UI
          |                |
          v                v
  số/ngày/tên locale     message text
~~~

Tách rõ:

- **User preference**: ngôn ngữ người dùng muốn, có thể gồm script/region.
- **Supported product locales**: dịch vụ UI/business thực sự cung cấp.
- **Supported SPI locales**: những locale một implementation provider quảng cáo.
- **JDK available locales**: tập dữ liệu locale khả dụng trong runtime/config.
- **Product fallback**: ví dụ ưu tiên `fr-CA → fr-FR → en-US`, một quyết định nghiệp vụ không tự suy ra từ `LocaleServiceProvider`.

Không tự tạo một menu locale của sản phẩm từ `NumberFormat.getAvailableLocales()`. Nếu ứng dụng chỉ có UI tiếng Việt và tiếng Anh, việc CLDR biết format số cho tiếng Nhật **không có nghĩa ứng dụng đã có giao diện tiếng Nhật**.

### 11.1. Không dùng `Locale.setDefault()` để chọn locale từng request

`Locale.setDefault(locale)` thay giá trị mặc định **toàn JVM**, có thể tác động đến những thread/ứng dụng khác. Với web server đa user, tránh thay default locale theo request; truyền locale tường minh vào formatter, resource lookup và hàm business.

~~~java
Locale userLocale = Locale.forLanguageTag("vi-VN");
NumberFormat formatter = NumberFormat.getNumberInstance(userLocale);
~~~

Đây là snippet minh họa trong method. Nó **không** thay `Locale.getDefault()` của JVM; vẫn cho phép JDK thực hiện selection/fallback tương ứng theo locale được yêu cầu.

### 11.2. Không dùng property `java.locale.providers` để chọn ngôn ngữ người dùng

Property này là **thứ tự nguồn dữ liệu i18n**, không phải một giá trị `Locale` như `fr-CA`. Nó không thay thế danh sách supported locales hoặc giải quyết HTTP `Accept-Language`. Thông thường property được cấu hình **khi khởi chạy JVM**, còn locale của từng request được chọn **trong application**.

## 12. So sánh Locale SPI với `ResourceBundle`

Hai cơ chế cùng sử dụng `Locale` nhưng có phạm vi khác nhau.

| Vấn đề | Locale SPI (ví dụ NumberFormatProvider) | ResourceBundle |
| --- | --- | --- |
| Mục đích | Bổ sung dữ liệu/implementation cho **dịch vụ locale-sensitive của JDK** | Tải các message/resource của ứng dụng theo locale |
| Đăng ký | `META-INF/services` hoặc JPMS `provides` | Family `Messages*.properties`, class bundle hoặc provider theo module |
| Danh sách support | `getAvailableLocales()`, `isSupportedLocale(...)` | Những bundle thực tế tìm được |
| Thứ tự nguồn | `java.locale.providers=SPI,CLDR,...` | Quy tắc tìm bundle/parent, classpath/module/control |
| Fallback | candidate locales, root và nguồn/provider theo thứ tự | candidate bundle, có thể fallback default locale, parent key lookup |
| Quan sát | Thường không có `getLocale()` trên đối tượng formatter | `ResourceBundle.getLocale()` |
| Key missing | Tùy service; name providers có thể trả null | `getString(key)` tìm parent; thiếu toàn bộ thì `MissingResourceException` |
| Kiểm thử | Factory thực tế + provider registration + config JVM | `getBundle` + `getLocale` + `getString` + bundle fixtures |

Không nhầm `ResourceBundle.Control.getNoFallbackControl(...)` với `LocaleServiceProvider.isSupportedLocale(...)`. Control của ResourceBundle **không phải** cách cấu hình toàn bộ các dịch vụ `NumberFormat`, `Collator`, `LocaleNameProvider`.

Ví dụ `NumberFormatProvider` của bài này **không làm thay đổi nội dung file `Messages_fr_CA.properties`**, và tạo một bundle tiếng Việt **không khiến NumberFormat tự dùng quy tắc format số của một provider mới**.

## 13. Kiểm thử fallback và provider thực sự được chọn

### 13.1. Bộ test tối thiểu

| Kịch bản | Kỳ vọng / điều cần assert |
| --- | --- |
| Descriptor sai hoặc bị bỏ khỏi artifact | `ServiceLoader` không tìm thấy implementation như dự kiến |
| Provider class không tạo được instance | Lỗi service configuration hoặc classloading; fail test rõ ràng |
| `getAvailableLocales()` | Chỉ chứa locale mà provider thực sự hỗ trợ, không trùng chỉ khác extension |
| `isSupportedLocale(exact)` | `true` cho `qaa-QA` trong demo |
| `isSupportedLocale(withExtension)` | `true` theo default policy bỏ qua extensions |
| `isSupportedLocale(sibling)` | `false` cho `qaa-QB` |
| Property `SPI,CLDR` | Factory `NumberFormat` chọn marker `SPI:` cho custom locale |
| Property `CLDR` | Factory không chọn marker `SPI:` |
| Locale ngoài vùng hỗ trợ | Fallback hợp lệ thay vì tự “nhảy ngang” sang locale sibling |
| API khác cùng locale | `DateFormat`/`Collator` không tự có custom implementation chỉ vì NumberFormatProvider tồn tại |
| Provider priority thay đổi | Kết quả được kiểm chứng trong JVM riêng cho từng configuration |
| Runtime được nâng cấp | Golden tests kiểm tra ý nghĩa format/fallback, không lệ thuộc text CLDR bất biến |

### 13.2. Tách unit test và integration test

**Unit test cho provider trực tiếp:**

~~~java
DemoNumberProvider provider = new DemoNumberProvider();
if (!provider.isSupportedLocale(Locale.forLanguageTag("qaa-QA"))) {
    throw new AssertionError("Locale not advertised");
}
~~~

Đây là snippet trong method, cần các class/import của project. Nó kiểm tra logic provider nhưng **không** bảo đảm system JDK đã kích hoạt SPI.

**Integration test cho locale service factory:**

~~~java
String actual = NumberFormat
        .getNumberInstance(Locale.forLanguageTag("qaa-QA"))
        .format(12.5);
if (!actual.startsWith("SPI:")) {
    throw new AssertionError("Custom provider was not selected");
}
~~~

Đây cũng là snippet bên trong method và **chỉ được kỳ vọng PASS trong JVM chạy với `-Djava.locale.providers=SPI,CLDR` và descriptor đúng**. Đừng đưa assertion này vào run `CLDR`; test âm tính của `CLDR` phải kiểm tra custom provider không được chọn.

**Packaging test:** mở artifact JAR sau build và kiểm tra nó chứa `META-INF/services/java.text.spi.NumberFormatProvider` cùng class provider, hoặc `module-info.class` với `provides` đúng. Đây là một tầng khác với việc IDE có thể chạy trực tiếp từ source tree.

### 13.3. Tránh phụ thuộc dữ liệu CLDR thay đổi theo phiên bản

JDK lấy dữ liệu locale từ CLDR; version CLDR thay đổi khi JDK được nâng cấp. Vì thế:

- Đừng assert cứng dấu thập phân, dấu nhóm, tên tiền tệ hoặc pattern ngày tháng cho **tất cả** locale trên mọi JDK.
- Với test chức năng SPI, dùng marker riêng của custom provider để chứng minh selection.
- Với test i18n sản phẩm, kiểm thử bản runtime mà production thực sự sử dụng và cập nhật golden outputs sau khi review thay đổi CLDR.
- Nếu cần output máy đọc cố định, đừng dùng format locale dành cho người dùng làm format protocol; chọn serialization/formatter quy định rõ chuẩn.

## 14. Sai lầm hay gặp

### 14.1. “Tôi tạo được Locale nên Java chắc chắn có dữ liệu địa phương hóa”

Sai. `Locale.forLanguageTag(...)` tạo đối tượng mô tả locale. Support thực tế phụ thuộc **loại dịch vụ**, nguồn dữ liệu và cấu hình provider.

**Sửa:** kiểm tra `getAvailableLocales()` của dịch vụ tương ứng và test kết quả factory method theo locale cần hỗ trợ.

### 14.2. “ServiceLoader tìm thấy implementation nên JDK chắc chắn dùng nó”

Sai. `ServiceLoader` có thể tìm provider ngay cả khi `java.locale.providers=CLDR`. Demo đã kiểm tra chính tình huống này.

**Sửa:** kiểm tra launcher property, service descriptor, và kết quả của factory `NumberFormat.getNumberInstance(...)` trong một JVM mới.

### 14.3. “`getAvailableLocales()` trả `qaa-QA` thì mọi vùng `qaa-*` được hỗ trợ”

Sai. `qaa-QB` là region khác, không tự có support. Cơ chế candidate có thể tìm **locale cha** nếu provider quảng cáo nó, nhưng không chọn một **sibling region** bất kỳ.

**Sửa:** quảng cáo đúng từng locale, dùng `isSupportedLocale` hợp lý và test candidate fallback.

### 14.4. “Locale extension sẽ luôn khiến provider từ chối”

Không đúng theo default implementation. `isSupportedLocale` mặc định **bỏ qua extensions**. Nhưng provider thực tế phải xét xem các extension cần được thực thi hay không.

**Sửa:** nếu cần numbering system, calendar hay trường hợp extension-aware, override `isSupportedLocale` và xử lý semantics của extension trong factory.

### 14.5. “Có thể đổi provider order giữa hai request bằng `System.setProperty`”

Không đáng tin. Property được đọc và cache khi subsystem khởi tạo. Chuyển cấu hình provider cho từng request không phải cơ chế được hỗ trợ ổn định.

**Sửa:** cấu hình `-Djava.locale.providers=...` trên launcher, chọn `Locale` riêng cho mỗi request, dùng JVM riêng để test các thứ tự provider.

### 14.6. “Default locale của JVM chính là fallback language của sản phẩm”

Không nhất thiết. Locale SPI fallback thường đi theo candidate/root và provider ordering; nghiệp vụ có thể yêu cầu fallback UI từ `vi-VN` sang `en-US` theo một quy tắc khác.

**Sửa:** implement product locale negotiation riêng, truyền locale tường minh, không phụ thuộc default host locale.

### 14.7. “Một provider sẽ tự xử lý mọi API i18n”

Sai. `NumberFormatProvider`, `CollatorProvider`, `DateFormatProvider`... là những SPI riêng. Support ở service này không đồng nghĩa support ở service khác.

**Sửa:** inventory các API locale-sensitive ứng dụng thực sự gọi, chọn provider đúng loại và test từng API.

### 14.8. “Provider có thể trả một formatter singleton dùng chung cho mọi thread”

Rủi ro. Nhiều implementation `NumberFormat` mutable và không an toàn để dùng chung khi có thay đổi cấu hình hay parse/format đồng thời.

**Sửa:** trả instance mới mỗi lần factory hoặc dùng cấu trúc immutable/thực sự thread-safe theo contract; tránh chia sẻ `DecimalFormat` mutable không kiểm soát.

### 14.9. “Có thể dựa vào COMPAT provider cũ để khắc phục khác biệt CLDR”

Không phù hợp với Java hiện hành: nguồn locale data compatibility cũ đã bị loại bỏ trong các bản JDK mới. Không viết hướng dẫn mới phụ thuộc provider legacy.

**Sửa:** sử dụng `CLDR`, `SPI` hoặc `HOST` khi có và kiểm tra quy tắc mới với runtime được triển khai.

## 15. Cách triển khai trong ứng dụng production

Một trình tự thực tế:

1. **Xác định dữ liệu cần tùy biến:** định dạng số, tên vùng, lịch, phân tách từ hay collation; từ đó chọn đúng SPI subclass.
2. **Xác định supported locales:** tập locale mà provider cam kết có dữ liệu chính xác, bao gồm script/region/extensions khi thích hợp.
3. **Đóng gói provider:** dùng service descriptor UTF-8 trên classpath hoặc `provides` trong named module, và verify artifact sau build.
4. **Chọn provider order ở launcher:** `SPI,CLDR` nếu muốn custom provider có ưu tiên, thêm `HOST` nếu có yêu cầu cụ thể và platform hỗ trợ.
5. **Chọn locale theo user:** lấy từ preference/request đã được validate, không gọi `Locale.setDefault` mỗi request.
6. **Dựa vào candidate fallback có kiểm thử:** xem điều gì xảy ra ở locale vùng thiếu, locale language-only, locale có Unicode extensions và root.
7. **Đảm bảo thread-safety và performance:** trả formatter objects hợp lệ, tránh state mutable toàn cục dùng chung giữa các lời gọi.
8. **Chạy unit + integration + packaging tests:** không chỉ kiểm tra provider methods trực tiếp mà còn factory selection trong JVM cấu hình thật.
9. **Theo dõi khi nâng JDK/CLDR:** test những locale có ý nghĩa với sản phẩm, review thay đổi formatting/currency/locale display names.
10. **Tách service fallback khỏi business fallback:** hệ thống UI phải biết product-supported locales của chính nó, không suy luận từ toàn bộ runtime locales.

### 15.1. Chỉ định rõ behavior khi locale unsupported

Với số cần hiển thị cho người dùng, fallback về formatter CLDR/root là hợp lý trong nhiều trường hợp. Nhưng nếu một chức năng yêu cầu format theo quy định pháp lý của một vùng cụ thể, **fallback im lặng có thể không đủ**.

Khi đó, ứng dụng có thể kiểm tra explicit support ở tầng product trước khi sử dụng dịch vụ:

~~~java
Set<Locale> supportedByProduct = Set.of(
        Locale.forLanguageTag("vi-VN"),
        Locale.forLanguageTag("en-US"));
if (!supportedByProduct.contains(requested)) {
    // Áp dụng product fallback hoặc thông báo locale chưa được hỗ trợ.
}
~~~

Đây là **snippet** cần import `java.util.Set` và đã có `requested`; không phải code hoàn chỉnh có `main`. Danh sách supportedByProduct là **quy tắc nghiệp vụ**, không phải copy tự động từ `NumberFormat.getAvailableLocales()`.

### 15.2. Chọn fallback không phụ thuộc kết quả format trông có vẻ hợp lý

Một locale không được hỗ trợ vẫn có thể sinh ra output như `1,234.5` hoặc `12.5` nhờ root fallback. Người dùng thấy số “đọc được” không có nghĩa ứng dụng đã chọn đúng bản địa hóa.

Nếu yêu cầu cần đảm bảo một provider chuyên biệt, test/provider selection phải rõ ràng. Ví dụ demo dùng prefix `SPI:` để phân biệt; implementation thật có thể dùng instrumentation hoặc contract-specific tests mà không chèn marker vào UI.

## 16. Tự kiểm tra

**Câu 1.** `Locale.forLanguageTag("qaa-QA")` chạy được. Có khẳng định `NumberFormatProvider` hỗ trợ nó không?

**Trả lời:** Không. Đối tượng `Locale` có thể được tạo độc lập với dữ liệu locale. Kiểm tra `provider.getAvailableLocales()`, `isSupportedLocale` và factory `NumberFormat.getNumberInstance(...)` trong cấu hình JVM đang chạy.

**Câu 2.** Provider quảng cáo `qaa-QA`; vậy `isSupportedLocale("qaa-QA-u-nu-latn")` mặc định trả gì?

**Trả lời:** `true`, vì implementation mặc định bỏ qua locale extensions khi kiểm tra support. Điều đó không bảo đảm provider thật có xử lý đúng numbering system extension; cần thiết kế thêm khi có yêu cầu.

**Câu 3.** Provider quảng cáo `qaa-QA`, còn request là `qaa-QB`. Có tự fallback sang `qaa-QA` không?

**Trả lời:** Không. Hai region là hai nhánh ngang. JDK tìm các candidate ít cụ thể hơn và nguồn i18n tương ứng; trong fixture JDK 24, lời gọi `qaa-QB` dùng formatter CLDR/root, không có marker `SPI:`.

**Câu 4.** `ServiceLoader.load(NumberFormatProvider.class)` tìm được provider nhưng `NumberFormat.getNumberInstance(...)` không dùng custom format. Nguyên nhân có thể là gì?

**Trả lời:** Property `java.locale.providers` có thể không bao gồm `SPI` hoặc SPI không được ưu tiên cho locale/service này. Ngoài ra cần kiểm tra supported locale, module visibility và packaging.

**Câu 5.** Vì sao phải đặt `-Djava.locale.providers=SPI,CLDR` khi khởi chạy thay vì gọi `System.setProperty` sau khi ứng dụng đã chạy?

**Trả lời:** Thứ tự provider được JDK đọc và cache khi các lớp liên quan được khởi tạo; đổi property giữa runtime không bảo đảm làm mới selection.

**Câu 6.** `NumberFormat.getAvailableLocales()` có thể làm menu chọn ngôn ngữ sản phẩm không?

**Trả lời:** Không trực tiếp. Nó liệt kê phạm vi hỗ trợ định dạng số, không nói ứng dụng đã dịch UI/messages cho những locale đó. Sản phẩm cần danh sách supported locales riêng.

**Câu 7.** Custom `NumberFormatProvider` có làm `Collator` hoặc `ResourceBundle` tự dùng quy tắc mới không?

**Trả lời:** Không. Chúng là các dịch vụ khác với cơ chế provider hoặc resource lookup riêng. Phải cấu hình và kiểm thử đúng API tương ứng.

**Câu 8.** Một provider dùng `getAvailableLocales()` trả `fr`, còn lời gọi là `fr-CA`. Provider chuyên biệt có luôn nhận đúng `fr` làm argument không?

**Trả lời:** Không được giả định. Theo JavaDoc, lookup có thể tìm support ở candidate `fr` nhưng gọi factory method với **locale được yêu cầu ban đầu** (có thể gồm extension); implementation phải kiểm thử và xử lý hợp lý.

**Câu 9.** Có nên bật provider `COMPAT` trong JDK hiện đại nếu muốn giữ locale behavior cũ?

**Trả lời:** Không. Đây là hướng legacy đã bị loại bỏ khỏi JDK mới. Cần đánh giá khác biệt với CLDR và tạo SPI chuyên biệt nếu sản phẩm có nhu cầu được xác minh.

**Câu 10.** Tại sao test cần chạy hai JVM riêng cho `SPI,CLDR` và `CLDR`?

**Trả lời:** Vì provider preference có thể được cache khi subsystem khởi tạo. Hai process độc lập bảo đảm mỗi cấu hình được áp dụng từ đầu và kết quả test phản ánh đúng launcher property.

**Ghi nhớ:** Trong **Locale SPI**, `getAvailableLocales()` là lời cam kết của một provider; `isSupportedLocale(...)` xác định support (mặc định bỏ qua extensions); JDK chọn locale data theo provider order `SPI/CLDR/HOST` và thử **candidate locales/root** khi thiếu support. Việc service được phát hiện không đồng nghĩa được sử dụng. Hãy bật `SPI` tường minh, kiểm thử qua factory thực tế và tách fallback ở tầng Java khỏi chính sách locale của sản phẩm.

### Tài liệu tham khảo chính thức (Java SE hiện hành)

- [Oracle Java SE 26 — `LocaleServiceProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): supported/available locales, extensions, candidate fallback, provider order, deployment.
- [Oracle Java SE 26 — `NumberFormatProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/spi/NumberFormatProvider.html): các factory methods, contract và compact number support.
- [Oracle Java SE 26 — `NumberFormat`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/NumberFormat.html): locale-sensitive number format factories.
- [Oracle Java SE 26 — `Locale`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): BCP 47, default locale, extensions, available locales.
- [Oracle Java SE 26 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): service descriptor và module service loading.
- [Oracle — Supported Locales in JDK 26](https://www.oracle.com/java/technologies/javase/jdk26-supported-locales.html): CLDR, SPI, HOST và loại bỏ dữ liệu provider compatibility cũ.
