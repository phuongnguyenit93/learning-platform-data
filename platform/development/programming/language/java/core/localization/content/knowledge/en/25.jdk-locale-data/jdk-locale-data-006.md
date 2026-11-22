# Giới hạn phụ thuộc quy ước của hệ điều hành trong dữ liệu locale JDK

Khi một chương trình Java chạy trên Windows, macOS, Linux, máy chủ cloud hoặc trong container, nhiều người kỳ vọng đổi **ngôn ngữ, vùng và cách hiển thị số/ngày của hệ điều hành** thì mọi lời gọi `NumberFormat`, `DateFormat`, `Locale` và `java.time` sẽ tự thay theo. Kỳ vọng này **chỉ đúng trong những phạm vi nhất định**: hệ điều hành có thể ảnh hưởng tới **locale và múi giờ mặc định ban đầu** mà JVM nhận lúc khởi động, nhưng **bộ quy tắc định dạng được dùng thực tế còn phụ thuộc dữ liệu locale và provider của JDK**.

Bài Knowledge thuộc nhóm **Dữ liệu locale JDK**, tập trung vào giới hạn của việc trông đợi Java phản chiếu quy ước hệ điều hành. Cần phân biệt:

1. **Cấu hình host**: ngôn ngữ, vùng, múi giờ, ký hiệu tùy chỉnh và môi trường của tiến trình.
2. **`Locale` Java**: ngữ cảnh ngôn ngữ/vùng được truyền vào API hoặc chọn làm mặc định.
3. **Locale data provider**: nguồn dữ liệu như `CLDR`, `HOST`, `SPI` hoặc `COMPAT` trong các phiên bản JDK còn hỗ trợ.
4. **Các API riêng**: định dạng số, ngày, tiền tệ, thứ tự sắp xếp, ngắt từ, timezone, charset và định dạng máy đọc không có cùng một hợp đồng phụ thuộc OS.

Ví dụ ưu tiên **Java 17+**, có lệnh `javac`/`java` và đầu ra xác định ở những đoạn độc lập với OS. Với thông tin vốn phụ thuộc môi trường, bài **không bịa ra một stdout cố định** mà chỉ rõ giá trị nào cần quan sát tại nơi chạy.

## 1. Hai điều khác nhau: default locale và quy tắc định dạng

### Default locale

`Locale.getDefault()` cho biết locale mặc định đang được JVM dùng; `Locale.getDefault(Locale.Category.FORMAT)` và `Locale.getDefault(Locale.Category.DISPLAY)` cho hai nhóm chức năng có thể tách nhau. Giá trị ban đầu thường được xác lập khi runtime khởi động bằng cách đọc thông tin môi trường/host và những tùy chọn khởi chạy Java.

Ví dụ: một JVM có thể bắt đầu với locale định dạng `en-US`, một JVM khác với `de-DE`. Nếu code gọi `NumberFormat.getNumberInstance()` không truyền `Locale`, locale định dạng mặc định sẽ ảnh hưởng đầu ra. Nhưng **không được suy luận** rằng mọi quy ước tùy chỉnh trong Control Panel, System Settings hay locale của một shell đều được chuyển nguyên vẹn vào formatter.

### Quy tắc locale từ JDK/provider

Ngay khi đã chọn `Locale.US`, formatter còn cần biết **dấu thập phân, dấu grouping, mẫu ngày, tên tháng, cách viết currency** và nhiều dữ liệu khác. Trên Oracle JDK 17 và JDK 21, **CLDR** (Common Locale Data Repository) là nguồn locale data mặc định ưu tiên; bộ dữ liệu này được **đóng gói với JDK**, không đơn giản là một lệnh hỏi toàn bộ cấu hình format của OS ở mỗi lần gọi.

Nói cách khác:

```text
Quyết định của ứng dụng            Nguồn có thể ảnh hưởng
----------------------------------------------------------
Locale mặc định của JVM            Host lúc khởi động và tùy chọn JVM
Locale được truyền vào API         Code, request hợp lệ, cấu hình người dùng
Dấu số và mẫu ngày                 Locale data provider đang được chọn
Tên tháng/đơn vị tiền              CLDR / HOST / SPI / legacy provider
Múi giờ mặc định                   Host/JVM/user.timezone và cấu hình thời gian
Bản dịch thông báo ứng dụng         ResourceBundle và tài nguyên ứng dụng
Charset dùng ghi file              Hợp đồng I/O, không suy ra từ Locale
```

Một ứng dụng có thể dùng `Locale.GERMANY` trên máy đặt vùng Hoa Kỳ; đồng thời nó có thể vẫn xuất ngày API ở ISO `2026-10-28` không phụ thuộc bất kỳ locale nào. Đó là **thiết kế đúng**, không phải dấu hiệu localization thất bại.

## 2. Trình tự suy nghĩ đúng khi kết quả khác giữa hai máy

Khi cùng mã Java in hai dạng ngày hoặc số khác nhau, hãy hỏi theo thứ tự:

1. API có **truyền `Locale` tường minh** không, hay nhận default JVM?
2. Runtime là Java phiên bản nào, vendor nào, module locale data nào có sẵn?
3. `java.locale.providers` có được thiết lập lúc **khởi động** không? Provider nào có thể được ưu tiên?
4. Các máy có dùng **cùng phiên bản dữ liệu CLDR** hoặc cùng provider không?
5. Dùng `Locale.Category.FORMAT` hay `DISPLAY`? Có khác nhau không?
6. Có lấy múi giờ mặc định `ZoneId.systemDefault()`/`TimeZone.getDefault()` không?
7. Vấn đề có phải ở charset/console/UI/CSV/HTTP client, thay vì thực sự ở locale data?
8. Phần mềm muốn **định dạng cho người xem** hay **biểu diễn máy đọc cần ổn định**?

Nếu không xác định được tầng nào quyết định kết quả, không nên thử sửa bằng cách đổi locale JVM toàn cục, thay dấu phân cách bằng `replace` hoặc hard-code mẫu ngày cho cả hệ thống.

## 3. Các locale data provider trong JDK 17 và JDK 21

JDK dùng cơ chế **locale-sensitive service providers**. Với Oracle JDK 17/21, các nguồn thường gặp:

| Provider | Nguồn dữ liệu/chức năng | Giới hạn |
| --- | --- | --- |
| `CLDR` | Dữ liệu Common Locale Data Repository do Unicode Consortium duy trì, được tích hợp vào JDK | Phiên bản CLDR đi cùng phiên bản JDK; không tự cập nhật mỗi khi OS đổi cấu hình |
| `HOST` | Một phần quy ước tùy chỉnh của **hệ điều hành** cho locale mặc định | Phụ thuộc nền tảng/JDK; không bảo đảm mọi locale hoặc mọi dịch vụ đều được hỗ trợ |
| `SPI` | Các provider do ứng dụng/thư viện triển khai qua service provider interfaces | Chỉ có tác dụng với dịch vụ/locale được provider hỗ trợ và khi cơ chế lựa chọn cho phép |
| `COMPAT` | Dữ liệu locale tương thích các JDK trước đây, đặc biệt hành vi cũ trước JDK 9 | Nguồn legacy của JDK 17/21; đã bị loại khỏi các bản JDK hiện đại hơn |
| `JRE` | Tên alias legacy của `COMPAT` trong các JDK cũ | Không nên dùng làm kế hoạch tương thích lâu dài |

**Quan trọng theo phiên bản:**

- Oracle **JDK 17** dựa vào CLDR 39 cho provider CLDR; Oracle **JDK 21** dùng CLDR 43.
- Trong JDK 17/21, thứ tự mặc định về cơ bản ưu tiên `CLDR`, với `COMPAT` phục vụ khả năng tương thích còn được hỗ trợ; nếu muốn ưu tiên `HOST`, phải cấu hình provider tường minh.
- `COMPAT`/`JRE` về sau bị loại bỏ khỏi các JDK mới. **Không hướng dẫn ứng dụng Java nhiều phiên bản phụ thuộc vĩnh viễn vào `COMPAT`**.
- `HOST` có thể không tồn tại ở một nền tảng hoặc bản phân phối JDK cụ thể. Trong **Oracle JDK 17/21**, tài liệu công bố provider này có trên **Windows và macOS**; đừng suy rộng kết luận đó sang mọi Linux, container hay mọi vendor.
- Riêng dữ liệu `BreakIterator` và `Collator` không được đồng nhất hoàn toàn với dữ liệu CLDR ở các JDK 17/21: tài liệu Supported Locales nói rõ các dịch vụ này **không lấy bộ dữ liệu tương ứng từ CLDR** theo cách các dịch vụ khác dùng. Không lấy danh sách locale của `NumberFormat` để suy luận chính xác quy tắc tách từ hay collation.

**Hệ quả thực tế:** người dùng chọn một mẫu ngày trong hệ điều hành không đồng nghĩa `DateTimeFormatter.ofLocalizedDate(...)` với `CLDR` sẽ tuân thủ chính xác mẫu đã sửa đó. Provider và dịch vụ phải thực sự hỗ trợ tùy chỉnh ấy.

## 4. HOST provider không phải “đọc toàn bộ thiết lập hệ điều hành”

`HOST` thường là tên dễ gây hiểu lầm nhất. Hãy hiểu đúng phạm vi:

- Nó nhằm phản ánh **một phần các tùy chỉnh của host** phục vụ các locale **mặc định của người dùng**, đặc biệt nhóm `Locale.Category.FORMAT` và/hoặc `DISPLAY`.
- Trong các JDK hỗ trợ, chức năng thực tế còn tùy **OS và implementation**. Tài liệu JDK 17 nêu chủ yếu là định dạng **ngày, giờ, số, tiền tệ**; không hứa cung cấp mọi biến thể của mọi dịch vụ text.
- Nó có thể fallback sang provider khác khi không có dữ liệu hoặc dịch vụ thích hợp.
- Nó không phải giải pháp tự động lấy mọi preference riêng của từng **người dùng web** vào một JVM server chung. Host là môi trường chạy **server**, không phải điện thoại/trình duyệt của từng khách hàng.
- Nó không chuyển một `Locale` tùy ý thành tập quy tắc tùy chỉnh của một OS không có hỗ trợ tương ứng.
- Nó không biến encoding text, quy tắc ký số, nội dung `ResourceBundle` hay timezone database thành các dữ liệu luôn đồng bộ với OS.

Ví dụ người dùng Windows tùy chỉnh dấu phân nhóm, mẫu ngày hoặc vùng định dạng trong Settings. Với `HOST` được chọn, **một số** API có thể phản ánh những lựa chọn ấy. Nhưng với provider `CLDR`, cùng một `Locale` vẫn có thể theo mẫu CLDR chứ không theo mẫu riêng của người dùng Windows.

**Không có bảo đảm “Windows dùng dấu phẩy → Java nào cũng dùng dấu phẩy”, cũng không có bảo đảm “HOST đặt lên đầu → mọi formatter nhất định từ HOST”.** Câu hỏi đúng là: **provider nào được chọn cho loại dịch vụ này, trên locale này, dưới runtime này?**

## 5. Cấu hình lựa chọn provider đúng thời điểm

Java cho phép thiết lập thứ tự qua system property **`java.locale.providers`**. Trong môi trường **JDK 17/21** ví dụ:

```bash
java -Djava.locale.providers=CLDR,COMPAT LocaleProviderDemo
java -Djava.locale.providers=HOST,CLDR,COMPAT LocaleProviderDemo
```

Mỗi lệnh khởi động **một JVM riêng**. `HOST` đứng trước để JVM có thể ưu tiên dữ liệu host khi provider và dịch vụ tương ứng được hỗ trợ. Khi HOST không hỗ trợ yêu cầu, cơ chế tìm kiếm có thể chuyển tới CLDR/COMPAT theo thứ tự; không được suy diễn sự ưu tiên bảo đảm mọi kết quả sẽ khác.

`LocaleServiceProvider` đọc và cache cấu hình provider lúc khởi tạo. Vì vậy:

```java
// KHÔNG dùng cách này để kỳ vọng tái cấu hình provider giữa request:
System.setProperty("java.locale.providers", "HOST,CLDR");
```

Thay đổi property sau khi runtime đã dùng dịch vụ locale **không có bảo đảm cập nhật provider đang chạy**. Chọn property trên dòng lệnh `java`/cấu hình JVM **trước** khi dùng locale service, rồi khởi động lại khi cần thay đổi.

**Lưu ý tương thích:** ví dụ có `COMPAT` nhắm đến **JDK 17/21**. Với JDK mới đã loại `COMPAT`, danh sách provider hợp lệ và cách fallback phải dựa theo tài liệu **đúng version**, chẳng hạn `HOST,CLDR`. Đây là một lý do không copy cấu hình JVM cũ vô hạn qua các bản nâng cấp.

### Khi nào nên dùng HOST?

Dùng `HOST` khi **yêu cầu sản phẩm thực sự là theo các tùy chỉnh hệ điều hành của người đang chạy ứng dụng desktop**, và bạn đã kiểm chứng OS + JDK + locale + từng formatter. Với ứng dụng server đa người dùng, giải pháp ưu tiên thường là **Locale tường minh theo người dùng** và **CLDR/provider kiểm soát**, không lấy cấu hình OS của máy chủ làm đại diện cho người dùng.

## 6. Chương trình chẩn đoán: default, provider và host

Tạo file **`LocaleProviderDemo.java`**:

```java
import java.nio.charset.Charset;
import java.time.ZoneId;
import java.util.Locale;
import java.util.TimeZone;

public class LocaleProviderDemo {
    public static void main(String[] args) {
        System.out.println("Java: "
                + Runtime.version().feature());
        System.out.println("OS: "
                + System.getProperty("os.name"));
        System.out.println("Providers: "
                + System.getProperty(
                        "java.locale.providers", "(not set)"));

        System.out.println("Default: "
                + Locale.getDefault().toLanguageTag());
        System.out.println("FORMAT: "
                + Locale.getDefault(
                        Locale.Category.FORMAT).toLanguageTag());
        System.out.println("DISPLAY: "
                + Locale.getDefault(
                        Locale.Category.DISPLAY).toLanguageTag());
        System.out.println("TimeZone ID: "
                + TimeZone.getDefault().getID());
        System.out.println("ZoneId: "
                + ZoneId.systemDefault().getId());
        System.out.println("Charset: "
                + Charset.defaultCharset().name());
    }
}
```

```bash
javac -encoding UTF-8 LocaleProviderDemo.java
java LocaleProviderDemo
java -Duser.language=de -Duser.country=DE LocaleProviderDemo
java -Djava.locale.providers=HOST,CLDR,COMPAT LocaleProviderDemo
```

**Không có stdout giống nhau trên mọi máy.** Đây là chương trình **in chẩn đoán runtime**, không phải một bài kiểm tra mà `OS`, `TimeZone ID`, `FORMAT`, `Charset` phải có giá trị cố định.

Các điểm cần quan sát:

1. `Default`, `FORMAT`, `DISPLAY` có thể không giống nhau.
2. JVM có thể đã chọn default từ host khi khởi động; `-Duser.language`/`-Duser.country` cho phép thử một default khác theo cấu hình hỗ trợ.
3. `Providers: (not set)` **không có nghĩa không dùng CLDR**; nó có nghĩa chưa khai báo property và JVM áp dụng **thứ tự mặc định** của phiên bản đó.
4. In `java.locale.providers` không cho biết provider **thực sự được chọn cho từng lời gọi**. Để nhận biết ảnh hưởng, thử cùng formatter với các tiến trình khởi động bằng provider order khác nhau.
5. `Charset` và `ZoneId` được ghi để đối chiếu môi trường; không coi chúng là một phần duy nhất của locale data.

Đây là đoạn mã **Java 17** chạy được. Không gọi `Locale.setDefault` hoặc `TimeZone.setDefault` trong chương trình để tránh làm thay đổi trạng thái toàn cục và khiến kết quả chẩn đoán bị sai lệch.

## 7. Hai nhóm default locale: DISPLAY và FORMAT

`Locale.Category.DISPLAY` và `Locale.Category.FORMAT` giúp tách **ngôn ngữ nhãn** khỏi **quy ước hiển thị số/ngày**. Ví dụ một người làm việc ở Việt Nam có thể chọn giao diện tiếng Anh nhưng muốn đọc số theo kiểu Đức; một JVM hoặc ứng dụng có thể biểu diễn hai preference khác nhau.

| API/trường hợp | Ngữ cảnh nên xem xét |
| --- | --- |
| `Locale.getDefault(Locale.Category.DISPLAY)` | Locale dùng cho tên hiển thị của locale, ngôn ngữ/khu vực theo nhu cầu |
| `Locale.getDefault(Locale.Category.FORMAT)` | Locale định dạng số, ngày, giờ khi không được truyền tường minh |
| `NumberFormat.getNumberInstance()` | Có thể dùng default FORMAT locale |
| `DateFormat.getDateInstance()` | Có thể dùng default FORMAT locale |
| `Locale.getDisplayName(displayLocale)` | Nên chỉ định locale muốn dùng để hiển thị tên |
| `ResourceBundle.getBundle(baseName, userLocale)` | Locale tìm bản dịch của ứng dụng, **không phải chọn theo format locale một cách máy móc** |

Một hạn chế quan trọng: hệ điều hành của người dùng có thể có nhiều danh mục preference, còn **Java không bảo đảm ánh xạ đầy đủ từng tùy chỉnh OS vào từng API**. `DISPLAY` không nhất thiết là locale của tất cả resource translations, và `FORMAT` không nhất thiết khiến mọi mẫu ngày giống hệt ảnh chụp của OS.

### Vì sao server càng không được coi default là ý định người dùng?

Một JVM server có hàng nghìn request đến từ nhiều locale. Default locale chỉ là **cấu hình của tiến trình**. Nó không tự thay theo `Accept-Language` của từng request và không tự biết region người dùng.

Nên lưu locale được người dùng chọn trong profile hoặc xác định từ request theo chính sách của sản phẩm; sau đó truyền locale tường minh:

```java
NumberFormat nf = NumberFormat.getNumberInstance(userLocale);
DateTimeFormatter df = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.MEDIUM)
        .withLocale(userLocale);
```

Đây là **fragment** với biến `userLocale` là `Locale` đã xác thực, imports `java.text.NumberFormat`, `java.time.format.DateTimeFormatter` và `FormatStyle`.

Không gọi `Locale.setDefault(...)` trên mỗi request. Đổi default là thay đổi trạng thái dùng chung, dễ gây nhiễu giữa các luồng và request đồng thời.

## 8. Ví dụ runnable: cùng ngày/số, chọn locale tường minh

File **`ExplicitLocaleDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class ExplicitLocaleDemo {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234.50");
        LocalDate date = LocalDate.of(2026, 10, 28);

        Locale us = Locale.US;
        Locale de = Locale.GERMANY;

        NumberFormat usNumber = NumberFormat.getNumberInstance(us);
        NumberFormat deNumber = NumberFormat.getNumberInstance(de);
        usNumber.setMinimumFractionDigits(2);
        usNumber.setMaximumFractionDigits(2);
        deNumber.setMinimumFractionDigits(2);
        deNumber.setMaximumFractionDigits(2);

        DateTimeFormatter usDate = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.MEDIUM).withLocale(us);
        DateTimeFormatter deDate = DateTimeFormatter
                .ofLocalizedDate(FormatStyle.MEDIUM).withLocale(de);

        System.out.println("US number: " + usNumber.format(amount));
        System.out.println("DE number: " + deNumber.format(amount));
        System.out.println("US date: " + usDate.format(date));
        System.out.println("DE date: " + deDate.format(date));

        System.out.println("Date unchanged: "
                + date.equals(LocalDate.of(2026, 10, 28)));
        System.out.println("Amount unchanged: "
                + amount.compareTo(new BigDecimal("1234.50")) == 0);
    }
}
```

```bash
javac -encoding UTF-8 ExplicitLocaleDemo.java
java ExplicitLocaleDemo
```

**Lưu ý rất quan trọng về stdout của ví dụ:** bốn dòng định dạng đầu được **cố ý để cho chương trình tự hiển thị**, không gắn với một chuỗi bất biến vì chúng có thể phụ thuộc provider/JDK. Hai dòng kiểm tra cuối phải cho biết giá trị dữ liệu Java vẫn giữ nguyên:

```text
Date unchanged: true
Amount unchanged: true
```

Với Oracle JDK 17 dùng CLDR thông thường, định dạng số en-US và de-DE thường có nhóm/thập phân khác nhau, nhưng **đó không chứng minh mọi biến thể OS sẽ ảnh hưởng đến output**. Khi thay provider order hoặc nâng cấp JDK, hãy quan sát thực tế thay vì ép so toàn bộ chuỗi với một ví dụ lấy từ một máy.

**Lỗi dễ mắc:** coi việc truyền `Locale.GERMANY` là lệnh “hãy lấy tất cả custom settings của Windows ở Đức”. Nó yêu cầu **locale Đức**; provider JDK đang chọn mới quyết định dữ liệu được cung cấp.

## 9. CLDR là dữ liệu của JDK, không phải một bản sao sống của OS

CLDR gồm các quy tắc địa phương hóa dùng chung ở nhiều nền tảng: mẫu ngày, dấu phân cách, tên tháng, kiểu tiền tệ, danh sách tên locale và nhiều mục khác. JDK tích hợp một **phiên bản CLDR cụ thể** thay vì luôn tải bản mới nhất từ OS.

Hệ quả:

- Hai máy có OS khác nhau nhưng **cùng JDK, cùng provider, cùng locale** thường nhận các kết quả tương đồng hơn so với việc để default locale thay đổi; tuy nhiên vẫn cần xem timezone và các provider khác.
- Hai bản JDK khác nhau, ngay cả trên cùng OS, có thể dùng **CLDR khác phiên bản**, khiến những tên, dấu, mẫu ngày hoặc quy ước định dạng thay đổi.
- Đổi **regional format** của OS không nhất thiết làm CLDR trong JVM thay đổi.
- Một **custom JDK runtime image** có thể không chứa tất cả locale data ban đầu, làm khác khả năng hỗ trợ/fallback.
- Những locale cụ thể và các Unicode locale extensions có thể thay đổi cách định dạng; không đoán từ hai chữ cái ngôn ngữ mà bỏ qua region/script/extensions.

Trong các tài liệu Oracle, `jdk.localedata` chứa phần lớn dữ liệu locale ngoài `java.base` cho JDK 17/21, trong khi `java.base` cung cấp dữ liệu nền tảng hạn chế. Một ứng dụng đóng gói bằng `jlink` có thể **cố ý chọn một tập locale nhỏ hơn** so với JDK đầy đủ.

### Module locale data và jlink

Ví dụ một lệnh `jlink` (minh họa, không phải lệnh duy nhất để đóng gói sản phẩm):

```bash
jlink --add-modules java.base,jdk.localedata \
  --include-locales en,ja,vi \
  --output runtime-locales
```

Cú pháp chia dòng trên phù hợp shell hỗ trợ dấu `\` tiếp dòng như Bash. Trên PowerShell cần điều chỉnh cách xuống dòng hoặc viết trên một dòng. Khi phân phối runtime tối giản, hãy kiểm tra JDK/jlink version và tập locale cần giữ cho cả **số, ngày, tên tháng, bản dịch provider**.

**Không suy luận “Locale.forLanguageTag trả object nên runtime có đủ dữ liệu locale đó”.** Tạo một object `Locale` không phải phép kiểm tra tính đầy đủ của dữ liệu định dạng. Nếu service cụ thể thiếu một locale, nó có thể dùng fallback hoặc biểu diễn khác; hãy kiểm tra trên runtime đã đóng gói.

## 10. Hạn chế phụ thuộc hệ điều hành với timezone

`Locale` **không phải** `ZoneId`. Một locale như `en-US` không cho biết người dùng đang ở New York, Los Angeles hay Honolulu. Hệ điều hành có thể ảnh hưởng **múi giờ mặc định ban đầu** của JVM; JDK cũng có **dữ liệu quy tắc timezone (tzdb)** để tính offset lịch sử và DST.

| Khái niệm | Ví dụ | Công dụng |
| --- | --- | --- |
| Locale | `vi-VN` | Ngôn ngữ/region để định dạng |
| Offset | `+07:00` | Chênh lệch so với UTC tại một thời điểm |
| Zone ID | `Asia/Ho_Chi_Minh` | Quy tắc offset theo thời gian cho một khu vực |
| Instant | `2026-10-28T03:30:00Z` | Thời điểm tuyệt đối |
| LocalDate | `2026-10-28` | Ngày trên lịch, không có timezone |

Nếu code gọi `ZoneId.systemDefault()` trong hai container khác nhau, local datetime kết quả có thể khác. Đây không hẳn là khác dữ liệu locale. Với tính toán thời điểm, **nên giữ `Instant`**, khi cần hiển thị theo region người dùng mới chọn một `ZoneId` tường minh.

### Demo Java 17+ không phụ thuộc zone mặc định

**`ExplicitZoneDemo.java`**:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

public class ExplicitZoneDemo {
    public static void main(String[] args) {
        Instant when = Instant.parse("2026-10-28T03:30:00Z");
        ZoneId utc = ZoneOffset.UTC;
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

        System.out.println("Instant: " + when);
        System.out.println("UTC: "
                + LocalDateTime.ofInstant(when, utc));
        System.out.println("Vietnam: "
                + LocalDateTime.ofInstant(when, vietnam));
        System.out.println("ISO: "
                + DateTimeFormatter.ISO_INSTANT.format(when));
    }
}
```

```bash
javac -encoding UTF-8 ExplicitZoneDemo.java
java ExplicitZoneDemo
```

Stdout trên JDK có tzdb hỗ trợ vùng đã chọn:

```text
Instant: 2026-10-28T03:30:00Z
UTC: 2026-10-28T03:30
Vietnam: 2026-10-28T10:30
ISO: 2026-10-28T03:30:00Z
```

Dữ liệu nguồn `Instant` không đổi khi hiển thị tại các vùng khác nhau. **Chọn `Locale` không tự chọn múi giờ**. Đừng dùng `LocalDateTime.now()` mà không chỉ định clock/zone cho bài test cần kết quả xác định.

Với lịch sử timezone và vùng có DST, **phiên bản tzdb** cũng có thể ảnh hưởng phép quy đổi, nên test nghiệp vụ nhiều năm cần kiểm soát phiên bản runtime và vùng.

## 11. Calendar, tuần đầu năm và thứ tự ngày: provider có ý nghĩa

Dữ liệu locale không chỉ quyết định dấu phân cách; nó còn ảnh hưởng **định nghĩa tuần**: thứ nào bắt đầu tuần, tuần đầu của năm phải có bao nhiêu ngày, nhãn AM/PM, format lịch và đôi khi chronology.

Trong Java Time, `WeekFields.of(locale)` cho các quy tắc tuần theo locale; `WeekFields.ISO` đại diện cho **quy tắc ISO**: thứ Hai là đầu tuần và tuần đầu năm có ít nhất bốn ngày.

**File `WeekRulesDemo.java`**:

```java
import java.time.DayOfWeek;
import java.time.temporal.WeekFields;
import java.util.Locale;

public class WeekRulesDemo {
    public static void main(String[] args) {
        WeekFields iso = WeekFields.ISO;
        WeekFields us = WeekFields.of(Locale.US);
        WeekFields de = WeekFields.of(Locale.GERMANY);

        System.out.println("ISO starts Monday: "
                + (iso.getFirstDayOfWeek() == DayOfWeek.MONDAY));
        System.out.println("ISO minimal days: "
                + iso.getMinimalDaysInFirstWeek());
        System.out.println("US first day: "
                + us.getFirstDayOfWeek());
        System.out.println("DE first day: "
                + de.getFirstDayOfWeek());
    }
}
```

```bash
javac -encoding UTF-8 WeekRulesDemo.java
java WeekRulesDemo
```

Hai dòng có kết quả cố định:

```text
ISO starts Monday: true
ISO minimal days: 4
```

Các dòng `US first day` và `DE first day` **phụ thuộc dữ liệu locale/provider**; thông thường khác nhau, nhưng không phải lệnh đọc trực tiếp “ngày đầu tuần hiện được người dùng OS chọn” trong mọi cấu hình JDK.

Nếu nghiệp vụ định nghĩa tuần theo **ISO**, dùng `WeekFields.ISO`, không dùng `WeekFields.of(Locale.getDefault())` rồi kỳ vọng cả thế giới dùng cùng một năm-tuần. Đặc biệt tránh dùng pattern `YYYY` (week-based-year) để biểu diễn năm lịch `yyyy`/`uuuu`; tuần-năm có thể khác năm lịch quanh ngày cuối năm.

## 12. Collator và BreakIterator: không thể khái quát cùng một nguồn

Các API văn bản:

- `Collator.getInstance(locale)` để sắp xếp/so sánh chuỗi theo quy ước ngôn ngữ.
- `BreakIterator.getWordInstance(locale)`, `getCharacterInstance(locale)`, v.v. để xác định ranh giới từ/ký tự/câu.

Chúng **không chỉ là cài đặt Windows/Linux**. Thuật toán, dữ liệu Unicode và provider từng loại có thể khác nhau. Trong Oracle JDK 17/21, ghi chú supported locales nói dữ liệu **BreakIterator và Collator không được adopt từ CLDR** theo cùng cách với nhiều locale service khác.

Vì vậy, việc thấy `NumberFormat` đổi dấu thập phân sau khi thay provider **không đủ chứng minh** `BreakIterator` sẽ đổi cách tách từ tiếng Việt hoặc `Collator` sẽ sao chép quy tắc sort của OS.

**Không dùng locale data làm hợp đồng khóa duy nhất của database:** nếu username/order ID cần uniqueness ổn định, `Collator` phụ thuộc locale/provider/version không phải lựa chọn mặc định cho identity. Nên dùng khóa canonical theo chính sách dữ liệu và kiểm tra collation thực tế của DB.

## 13. Tiền tệ: locale hiển thị không xác định đơn vị giao dịch

`NumberFormat.getCurrencyInstance(Locale.US)` lấy một formatter tiền tệ phục vụ ngữ cảnh Hoa Kỳ. Không thể chỉ từ đó suy luận **giao dịch thực sự bằng USD** nếu sản phẩm có thể thanh toán bằng EUR hoặc VND. Locale là ngữ cảnh **hiển thị**, còn tiền tệ là thuộc tính **nghiệp vụ**.

`Currency.getInstance(locale)` có thể xác định một currency liên hệ với territory ở nhiều locale, nhưng không phải mọi locale đều có country hoặc chỉ có đúng một kết quả thích hợp cho mọi tình huống. Các quy tắc hệ điều hành, CLDR và dữ liệu tiền tệ theo thời gian có thể thay đổi.

**Chương trình `CurrencyLocaleDemo.java`**:

```java
import java.util.Currency;
import java.util.Locale;

public class CurrencyLocaleDemo {
    public static void main(String[] args) {
        Locale display = Locale.GERMANY;
        Currency actual = Currency.getInstance("USD");

        System.out.println("Display locale: "
                + display.toLanguageTag());
        System.out.println("Transaction currency: "
                + actual.getCurrencyCode());
        System.out.println("Same currency as locale?: "
                + actual.equals(Currency.getInstance(display)));
    }
}
```

```bash
javac -encoding UTF-8 CurrencyLocaleDemo.java
java CurrencyLocaleDemo
```

Stdout cho hai dòng đầu:

```text
Display locale: de-DE
Transaction currency: USD
```

Dòng `Same currency as locale?` phản ánh quy ước currency tương ứng với locale Đức của bộ dữ liệu JDK; trong môi trường thông dụng là `false`, nhưng bài không dựa vào nó để xác định tiền tệ giao dịch. Code cố tình giữ `actual = USD` do **nghiệp vụ chọn**, thay vì suy từ locale.

Khi thiết kế API, lưu mã tiền tệ chuẩn (ví dụ `USD`) cùng số tiền có kiểu `BigDecimal`; sử dụng formatter theo `Locale` của người xem và mã tiền thực tế.

## 14. Default charset và dòng mới là ảnh hưởng OS khác, không phải locale data

Một nguyên nhân khác tạo output khác trên các máy là **charset** hoặc **line separator**:

- Trong **JDK 17**, default charset của một số API cũ có thể phụ thuộc hệ điều hành, locale môi trường và cấu hình JVM.
- Từ **JDK 18** (JEP 400), nhiều API Java SE dùng **UTF-8 default**, nhưng không phải mọi API legacy đều thay hợp đồng encoding.
- `StandardCharsets.UTF_8` luôn có sẵn, nên dùng tường minh khi file/API yêu cầu UTF-8.
- `System.lineSeparator()` có thể là `"\n"` hoặc `"\r\n"` tùy môi trường. Một file máy đọc có yêu cầu LF phải ghi `"\n"` rõ.
- `Files.readString(path)`/`Files.writeString(path,text)` đã dùng **UTF-8 theo tài liệu Java 17**. Không hiểu mọi overload thiếu charset đều dùng default theo OS.

**Không nhầm ba quyết định:**

```text
Locale       -> cách hiển thị số/ngày/ngôn ngữ
Charset      -> cách mã hóa ký tự thành byte
Line ending  -> các ký tự phân tách dòng trong file
```

Hệ điều hành có thể ảnh hưởng cả ba theo những đường khác nhau, nhưng việc truyền `Locale.GERMANY` không tự chuyển UTF-8 thành Latin-1, và bật `HOST` cũng không làm mọi file CSV tự có CRLF.

### Ví dụ Java 17+ tách ba yếu tố

**`IndependentSettingsDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.Locale;

public class IndependentSettingsDemo {
    public static void main(String[] args) {
        Locale presentation = Locale.forLanguageTag("vi-VN");
        String text = "Chào";
        byte[] encoded = text.getBytes(StandardCharsets.UTF_8);

        String wireDate = LocalDate.of(2026, 10, 28).toString();

        System.out.println("Presentation locale: "
                + presentation.toLanguageTag());
        System.out.println("UTF-8 round trip: "
                + text.equals(new String(
                        encoded, StandardCharsets.UTF_8)));
        System.out.println("Wire date: " + wireDate);
        System.out.println("LF constant length: "
                + "\n".length());
    }
}
```

```bash
javac -encoding UTF-8 IndependentSettingsDemo.java
java IndependentSettingsDemo
```

Stdout:

```text
Presentation locale: vi-VN
UTF-8 round trip: true
Wire date: 2026-10-28
LF constant length: 1
```

Bài này không hỏi dòng xuống dòng của hệ điều hành là gì; nó chọn **LF literal** làm hợp đồng. Cùng cách, ISO `LocalDate.toString()` không lấy mẫu ngày đã sửa trong OS.

## 15. Ứng dụng server: ranh giới của host locale

Trên server hoặc trong container, **host là máy chủ/container runtime**. Nó có thể chạy ở UTC, locale `C`/`en-US` hoặc một vùng không liên hệ gì với người dùng. Nếu lấy `Locale.getDefault()` để trả UI cho mọi request, người ở Việt Nam và Đức có thể cùng nhìn thấy định dạng máy chủ, bất kể họ chọn gì.

Luồng được khuyến nghị:

```text
Người dùng / request
    |
    +-- uiLocale được xác thực (vi-VN, en-US, ...)
    +-- userZoneId được xác thực (Asia/Ho_Chi_Minh, ...)
    |
    v
Dữ liệu có kiểu: BigDecimal, LocalDate, Instant
    |
    +-- UI: format theo uiLocale + userZoneId
    |
    +-- API/file/DB: serialize theo schema ổn định
                       (decimal, ISO 8601, UTC/offset, UTF-8)
```

Cần phân biệt `Accept-Language` là **gợi ý** mà trình duyệt gửi, không phải bảo đảm ý định cuối cùng của user hoặc locale hợp lệ/sẵn tài nguyên. Nhiều ứng dụng nên ưu tiên preference lưu trong tài khoản và có fallback rõ ràng. Với locale không được hỗ trợ, trả một locale có tài nguyên ứng dụng đã chọn, không ném các chuỗi mặc định của OS một cách ngẫu nhiên.

`Locale.setDefault(...)`/`TimeZone.setDefault(...)` thay đổi cấu hình **JVM-wide**; không dùng để mô phỏng “mỗi HTTP request có môi trường riêng”. Ngoài lỗi concurrency, những thay đổi này có thể ảnh hưởng logic của thư viện không liên quan.

## 16. Java API không cam kết đồng nhất với hệ điều hành mọi mặt

Bảng giới hạn thiết kế:

| Mong đợi | Điều Java/JDK có thể thực sự bảo đảm | Cách làm phù hợp |
| --- | --- | --- |
| Đổi region của OS thì mọi formatter Java đổi ngay | Không; default ban đầu, provider và runtime có vai trò khác nhau | Truyền Locale rõ, cấu hình provider ở startup nếu cần |
| Tùy chỉnh dấu thập phân Windows luôn được CLDR dùng | Không; CLDR là dữ liệu JDK | HOST khi hỗ trợ và đã kiểm thử, hoặc cấu hình `DecimalFormatSymbols` cho yêu cầu đặc biệt |
| Locale `vi-VN` thì timezone là Asia/Ho_Chi_Minh | Không; Locale không mang timezone | Truyền `ZoneId` |
| Có `Locale` thì chắc có mọi bản dịch UI | Không; ứng dụng quản lý resource bundle riêng | ResourceBundle/translation fallback riêng |
| Java 17 và Java 21 luôn in mọi số/ngày giống nhau | Không; dữ liệu CLDR/version có thể đổi | Kiểm thử/cố định runtime hoặc contract format |
| HOST được chọn thì mọi OS đều có provider | Không; còn tùy implementation/platform | Kiểm tra nơi chạy, có fallback |
| Java Locale phản chiếu sở thích của từng user web | Không; default JVM là cho tiến trình | Lưu/đọc preference theo user |
| Locale quyết định encoding file | Không | `StandardCharsets.UTF_8` theo contract |
| Locale quyết định thứ tự sắp xếp DB | Không | DB collation/identifier policy rõ |
| Múi giờ OS quyết định instant đã lưu | Instant là thời điểm tuyệt đối, zone dùng hiển thị | Lưu Instant, chuyển zone khi cần |
| Số/ngày gửi API nên theo dấu của OS | Sai với hợp đồng máy đọc | JSON typed number / ISO date / UTC tường minh |
| Nâng cấp JDK không ảnh hưởng localization | Không chắc; CLDR/tzdb/provider thay đổi | Regression test theo version/JDK |

Đừng coi hiện tượng khác dấu/chữ tên tháng sau khi đổi hệ điều hành là bằng chứng duy nhất “Java phụ thuộc Windows”. Có thể đó là **default locale**, provider được chọn, data version hoặc timezone, không phải OS luôn quyết định mọi thứ.

## 17. Kiểm thử portable: so giá trị có kiểu, không khóa toàn bộ UI vào snapshot một máy

Một test localization tốt tách:

**Nhóm A — bất biến dữ liệu:**

- `LocalDate.of(2026,10,28)` là ngày 28/10/2026 dù định dạng UI khác.
- `BigDecimal("1234.50")` giữ giá trị decimal và scale theo Java BigDecimal.
- `Instant.parse("2026-10-28T03:30:00Z")` có cùng instant trên mọi zone.
- UTF-8 round-trip bảo toàn text hợp lệ khi hai đầu cùng dùng UTF-8.
- Thẻ `Locale.forLanguageTag("vi-VN").toLanguageTag()` là BCP 47 độc lập OS.

**Nhóm B — đầu ra localized:**

- Dấu decimal/grouping của `NumberFormat` cho `Locale.US`/`Locale.GERMANY`.
- Mẫu `DateTimeFormatter.ofLocalizedDate` theo locale/provider.
- Thứ đầu tuần qua `WeekFields.of(locale)`.
- Tên tháng, weekday, tên timezone hoặc currency symbol.
- Các ví dụ đặc thù `HOST` trên Windows/macOS.

Nhóm B nên được kiểm tra trên **JDK/provider đã chỉ rõ**, không tuyên bố mọi phiên bản, mọi platform đều phải có chuỗi tương tự. Các chuỗi localized là dữ liệu giao diện có thể được cải tiến theo CLDR.

### Lệnh kiểm thử khác nhau theo startup

```bash
javac -encoding UTF-8 ExplicitLocaleDemo.java LocaleProviderDemo.java
java -Duser.language=en -Duser.country=US LocaleProviderDemo
java -Duser.language=de -Duser.country=DE LocaleProviderDemo
java -Djava.locale.providers=CLDR,COMPAT ExplicitLocaleDemo
java -Djava.locale.providers=HOST,CLDR,COMPAT ExplicitLocaleDemo
```

Với Windows PowerShell, một lệnh `java` trên mỗi dòng cũng dùng được; không cần viết script Linux riêng. Nếu đang trên JDK mới không còn COMPAT, đổi provider order thành `CLDR` hoặc `HOST,CLDR` theo tài liệu bản đó.

Ghi lại trong bug report: **JDK vendor/feature/update**, OS/platform, locale FORMAT/DISPLAY, provider property, timezone, API format đang dùng, locale truyền vào và kết quả được quan sát. Không log thông tin nhạy cảm của người dùng chỉ để debug localization.

## 18. Những bẫy khác: fallback, SPI, cache và khả năng hỗ trợ locale

### Fallback không bảo đảm độ bao phủ đầy đủ

Một locale có thể được chấp nhận về cú pháp, nhưng một formatter cụ thể không có dữ liệu riêng cho đúng locale đó. Java/provider có thể dùng danh sách locale ứng viên/fallback. Vì thế, **không kết luận hỗ trợ đầy đủ** chỉ vì `Locale.forLanguageTag("xx-YY")` tạo object thành công.

### SPI không tự bật khi ứng dụng không cấu hình

`SPI` là nguồn provider do các thư viện triển khai. Việc thư viện có mặt trên classpath/module path không tự đảm bảo mọi locale-sensitive API sẽ lựa chọn nó; phải đáp ứng cơ chế service lookup và **provider order** được cấu hình phù hợp.

### Caching và lifecycle

Một số locale data/provider hoặc formatter cache thông tin. Vì thế, việc thay `System.setProperty("java.locale.providers", ...)` hoặc thay OS regional settings **sau khi JVM chạy** không là hợp đồng bắt buộc mọi formatter sẵn có refresh ngay. Tạo một JVM mới và test lại là cách chắc chắn hơn khi so sánh các chế độ provider.

### Sự tương thích của runtime image

Một image `jlink` giới hạn modules/locales, hoặc một môi trường triển khai không mang `jdk.localedata` như full JDK, có thể có tập locale khả dụng khác. Kiểm tra runtime **thực tế được đưa lên production**, không chỉ JDK developer cài ở máy cá nhân.

### Locale extensions không phải bản sao cấu hình OS

Thẻ Unicode locale có thể mang các extension như numbering system hoặc region override. Những extension được hỗ trợ theo Java/JDK và provider tương ứng, không đồng nghĩa sao chép tất cả preference của host. Nếu sản phẩm cần chữ số Latin hoặc lịch cụ thể, hãy thiết kế locale/chronology/decimal symbols theo API, kiểm thử support thực tế.

## 19. Bài tập ứng dụng

**Bài 1 — Tách hai nguồn ảnh hưởng.** Trên hai máy khác OS, chạy `LocaleProviderDemo`. So sánh `Locale.getDefault(FORMAT)` với `Locale.getDefault(DISPLAY)`, `ZoneId.systemDefault` và `Charset.defaultCharset`. Sau đó chạy `ExplicitLocaleDemo` với `Locale.US`/`Locale.GERMANY`. Chỉ ra khác biệt nào đến từ default và khác biệt nào còn có thể đến từ provider.

**Bài 2 — Thử HOST nếu hệ thống hỗ trợ.** Chạy `ExplicitLocaleDemo` trong hai JVM riêng: `-Djava.locale.providers=CLDR,COMPAT` và `-Djava.locale.providers=HOST,CLDR,COMPAT` trên JDK 17/21. Thử tùy chỉnh định dạng số/ngày của OS nếu môi trường hỗ trợ; ghi nhận **dịch vụ nào đổi** và dịch vụ nào không. Không kết luận HOST không hoạt động chỉ vì một locale không được HOST hỗ trợ.

**Bài 3 — Múi giờ là tầng riêng.** Chạy `ExplicitZoneDemo` rồi thử đổi system timezone. Vì ví dụ có `ZoneId` tường minh, kết quả cùng một instant phải vẫn nhất quán theo dữ liệu tzdb. Sau đó viết biến thể cố ý dùng `ZoneId.systemDefault()` để quan sát phụ thuộc host.

**Bài 4 — Tuần theo locale và theo ISO.** So sánh `WeekFields.ISO`, `WeekFields.of(Locale.US)` và `WeekFields.of(Locale.GERMANY)`. Vì sao ứng dụng tính số tuần ISO của chứng từ nên dùng `WeekFields.ISO` thay vì locale mặc định của server?

**Bài 5 — Container tối giản.** Thiết kế test cho runtime `jlink` có/không có `jdk.localedata`, kết quả tên tháng/định dạng số của locale `vi-VN`, `de-DE`. Chỉ ra vì sao cùng một `Locale` object không đảm bảo mọi provider/data đều tồn tại.

**Bài 6 — API máy đọc và giao diện bản địa hóa.** Với `amount=1234.50` và `date=2026-10-28`, trả một payload JSON theo quy tắc máy đọc, đồng thời hiển thị nhãn UI cho locale/zone người dùng. Giải thích vì sao không lưu chuỗi `"1.234,50"` thay cho `BigDecimal` và không parse ngày từ snapshot của OS.

## 20. Tài liệu tham khảo chính thức

- [Oracle — JDK 17 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk17-suported-locales.html): CLDR 39, HOST trên Windows/macOS, các provider của JDK 17, dữ liệu được đóng gói.
- [Oracle — JDK 21 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk21-supported-locales.html): CLDR 43, cấu hình `java.locale.providers` và giới hạn locale data.
- [Java SE 17 — LocaleServiceProvider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/spi/LocaleServiceProvider.html): thứ tự tìm kiếm provider, fallback và property phải đặt khi khởi động.
- [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): default locale, `DISPLAY`/`FORMAT`, language tag và categories.
- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): factory locale-aware và grouping/decimal symbols.
- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): `withLocale`, `ofLocalizedDate`, định dạng ISO.
- [Java SE 17 — WeekFields](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/WeekFields.html): ISO và week fields theo locale.
- [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252): lý do chuyển sang dữ liệu CLDR.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset Java 18+, không phải locale formatting.
- [JDK 26 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk26-supported-locales.html): ví dụ minh họa COMPAT/JRE không còn là lựa chọn cho các JDK hiện đại.

## 21. Ghi nhớ

**Hệ điều hành có thể giúp JVM chọn locale và timezone mặc định ban đầu, nhưng không quyết định toàn bộ dữ liệu locale JDK.** Trên JDK 17/21, CLDR thường là nguồn mặc định ưu tiên; HOST chỉ phản ánh những tùy chỉnh OS trong phạm vi platform, locale và dịch vụ được hỗ trợ. `java.locale.providers` được chọn ở **thời điểm khởi động**, không phải đổi một property giữa các request.

Với code đáng tin cậy: dùng **`Locale` tường minh cho giao diện từng người dùng**, **`ZoneId` tường minh khi quy đổi thời điểm**, **`StandardCharsets.UTF_8` cho byte/text theo hợp đồng** và **định dạng ISO/giá trị có kiểu cho API, file, database**. Đừng trông chờ `Locale.getDefault()` của một server thay mặt sở thích của người dùng, đừng coi `HOST` tương đương “mọi cài đặt OS”, và đừng khóa chính sách định danh/kiểm toán vào snapshot format của một JDK không cố định.