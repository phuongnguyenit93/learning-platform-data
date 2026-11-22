# Dữ liệu locale có thể thay đổi khi cập nhật JDK

Một đối tượng **Locale** chỉ mô tả ngôn ngữ, script, vùng và các extension theo BCP 47. Các quy tắc để hiển thị ngày tháng, giờ, số, tiền tệ, tên quốc gia, tên múi giờ và nhiều thông tin địa phương khác được cung cấp bởi dữ liệu locale của Java Runtime hoặc các LocaleServiceProvider đã cài đặt.

Dữ liệu này có thể thay đổi giữa các bản JDK vì JDK cập nhật dữ liệu từ **Unicode Common Locale Data Repository (CLDR)** và có thể cập nhật cách triển khai các API quốc tế hóa. Do đó, cùng một mã Java, cùng Locale và cùng dữ liệu đầu vào vẫn có thể tạo ra chuỗi hiển thị khác sau khi nâng cấp JDK. Đây là thay đổi hành vi cần được kiểm thử trong quy trình nâng cấp runtime.

## 1. Phân biệt Locale với dữ liệu locale

Locale là một định danh có cấu trúc, không phải bản sao của toàn bộ quy tắc định dạng.

Ví dụ:

~~~java
Locale locale = Locale.forLanguageTag("fr-FR");
~~~

Đối tượng trên biểu thị tiếng Pháp tại Pháp. Nó không lưu cố định:

- Mẫu ngày ngắn hoặc ngày đầy đủ.
- Ký hiệu phân tách hàng nghìn và phần thập phân.
- Vị trí ký hiệu tiền tệ và khoảng trắng giữa số với ký hiệu.
- Tên tháng, tên ngày trong tuần, tên quốc gia hoặc tên múi giờ.
- Ngày đầu tuần và một số quy tắc lịch.
- Các bản dịch và tên hiển thị được dùng bởi API locale-sensitive.

Khi gọi DateTimeFormatter, NumberFormat, DateFormat, Currency hoặc các API tương tự, Java tra cứu dữ liệu từ provider phù hợp với Locale và dịch vụ đang được yêu cầu.

Vì vậy, có hai lớp cần phân biệt:

| Thành phần | Chức năng | Mức ổn định |
|---|---|---|
| Locale | Định danh ngôn ngữ, script, vùng và extension | Giá trị định danh ổn định theo BCP 47 |
| Locale data | Mẫu định dạng, tên hiển thị, quy tắc tuần, ký hiệu và bản dịch | Có thể thay đổi theo JDK, CLDR hoặc provider |
| LocaleServiceProvider | Cung cấp dữ liệu cho một nhóm dịch vụ locale-sensitive | Phụ thuộc provider được triển khai và cấu hình |
| Default Locale | Locale mặc định lấy từ môi trường lúc JVM khởi động | Có thể khác giữa máy, container và môi trường chạy |

Locale.forLanguageTag("fr-FR") giúp chọn đúng locale một cách tường minh. Nó không đóng băng dữ liệu CLDR được JDK sử dụng cho fr-FR.

## 2. Vì sao dữ liệu locale thay đổi khi nâng cấp JDK?

JDK sử dụng **Common Locale Data Repository (CLDR)** do Unicode Consortium duy trì. CLDR chứa dữ liệu quốc tế hóa cho nhiều ngôn ngữ và khu vực, bao gồm mẫu ngày giờ, số, tiền tệ, tên địa danh, tên múi giờ và quy tắc địa phương.

JDK 9 chuyển CLDR thành nguồn dữ liệu locale mặc định theo JEP 252. Từ đó, mỗi dòng JDK có thể tích hợp một phiên bản CLDR mới. Các phiên bản CLDR mới bổ sung locale, sửa bản dịch và điều chỉnh quy tắc theo tiêu chuẩn hoặc tập quán địa phương.

Bảng phiên bản CLDR được ghi trong Javadoc LocaleServiceProvider của JDK 26:

| JDK feature release | CLDR version |
|---:|---:|
| 9 | 29 |
| 10 | 29 |
| 11 | 33 |
| 12 | 33 |
| 13 | 35.1 |
| 14 | 36 |
| 15 | 37 |
| 16 | 38 |
| 17 | 39 |
| 18 | 39 |
| 19 | 41 |
| 20 | 42 |
| 21 | 43 |
| 22 | 44 |
| 23 | 45 |
| 24 | 46 |
| 25 | 47 |
| 26 | 48 |

Theo tài liệu JDK, các bản update trong cùng một dòng feature release thường dùng cùng phiên bản CLDR, trừ khi release note nêu thay đổi riêng. Điều này không có nghĩa mọi bản JDK khác nhau đều tạo cùng kết quả: khi chuyển từ JDK 24 sang 25, dữ liệu CLDR tăng từ 46 lên 47; từ JDK 25 sang 26 tăng lên 48.

## 3. Ví dụ thay đổi thực tế trong CLDR 48

Release note JDK 26 ghi nhận nhiều thay đổi từ CLDR 48 có thể ảnh hưởng đến kết quả định dạng:

- Ngày đầu tuần của Iceland được sửa từ Monday thành Sunday.
- Dữ liệu phân nhóm số của Thụy Sĩ được sửa.
- Một số mẫu giờ được thay đổi, bao gồm cách biểu diễn giờ khi không có phút.
- Một số tên metazone và alias múi giờ được điều chỉnh.
- Dữ liệu lịch Hijrah và các locale tiếng Anh theo khu vực được bổ sung hoặc sửa.

Những thay đổi này có thể ảnh hưởng đến WeekFields, DateTimeFormatter, NumberFormat, DateFormatSymbols, TimeZone và các API sử dụng dữ liệu locale tương ứng.

Ví dụ, nếu ứng dụng hiển thị lịch tuần bắt đầu vào thứ Hai hoặc Chủ nhật, kết quả có thể đổi khi dữ liệu của locale được cập nhật. Nếu ứng dụng so sánh chuỗi tiền tệ với một snapshot cũ, thay đổi khoảng trắng không ngắt dòng hoặc ký hiệu phân nhóm cũng có thể làm test thất bại.

Không phải mọi dịch vụ locale-sensitive đều lấy dữ liệu từ cùng một nguồn. Tài liệu Oracle JDK 26 lưu ý CLDR provider không cung cấp dữ liệu cho BreakIterator và Collator trong bản JDK đó. Khi kiểm tra một API cụ thể, hãy xác định provider và dữ liệu thực tế của chính dịch vụ ấy.

## 4. Những API dễ bị ảnh hưởng

| API | Dữ liệu có thể thay đổi | Tác động thường gặp |
|---|---|---|
| DateTimeFormatter.ofLocalizedDate() | Mẫu ngày, tên thứ, tên tháng | Chuỗi hiển thị thay đổi; chuỗi cũ có thể không parse được |
| DateTimeFormatter.ofLocalizedTime() | Mẫu giờ, AM/PM, tên múi giờ | Chuỗi thời gian khác trước |
| DateTimeFormatter.ofLocalizedDateTime() | Kết hợp mẫu ngày và giờ | Thứ tự, dấu phân cách hoặc tên hiển thị thay đổi |
| NumberFormat | Dấu thập phân, dấu nhóm, chữ số | Chuỗi số khác nhau |
| NumberFormat.getCurrencyInstance() | Ký hiệu tiền tệ, vị trí và khoảng trắng | Chuỗi tiền tệ khác nhau |
| Currency.getDisplayName() | Tên tiền tệ theo locale | Nhãn hiển thị thay đổi |
| DateFormatSymbols | Tên tháng, tên thứ, AM/PM | Giao diện lịch và form ngày tháng thay đổi |
| WeekFields | Ngày đầu tuần, số ngày tối thiểu của tuần đầu năm | Lịch tuần và báo cáo tuần thay đổi |
| Locale display-name APIs | Tên ngôn ngữ, vùng và script | Danh sách locale hiển thị khác nhau |
| TimeZone / ZoneId | Tên múi giờ và quy tắc giờ mùa hè | Tên hoặc thời điểm quy đổi có thể thay đổi |

Đặc biệt, API định dạng và API phân tích chuỗi có quan hệ chặt chẽ. Một chuỗi đã được tạo bởi JDK cũ có thể không còn khớp với mẫu localized date của JDK mới. Tài liệu migration của Oracle nêu rõ thay đổi locale data có thể dẫn đến kết quả khác hoặc exception khi parse ngày tháng.

## 5. Phân biệt thay đổi CLDR với thay đổi timezone database

Dữ liệu locale và dữ liệu múi giờ liên quan nhưng không phải cùng một bộ dữ liệu.

- CLDR cung cấp nhiều thông tin locale-sensitive như mẫu ngày giờ, tên hiển thị và ký hiệu.
- IANA Time Zone Database (tzdb) cung cấp quy tắc lịch sử và tương lai của các múi giờ, bao gồm thay đổi UTC offset và giờ mùa hè.
- Provider của JDK và môi trường hệ điều hành có thể ảnh hưởng đến cách lấy dữ liệu cho từng dịch vụ.

Ví dụ, một bản cập nhật JDK có thể cập nhật tzdb để phản ánh quyết định pháp lý mới của một quốc gia về giờ mùa hè. Khi đó, phép chuyển đổi giữa Instant và ZonedDateTime có thể cho kết quả khác ở một thời điểm trong tương lai, dù Locale không đổi.

JDK 26.0.2 cập nhật IANA time-zone data lên 2026b. Đây là ví dụ cho thấy khi nâng cấp JDK cần kiểm tra cả locale data lẫn quy tắc múi giờ nếu ứng dụng xử lý lịch, đặt lịch hoặc báo cáo theo vùng.

Để tránh phụ thuộc múi giờ máy chạy, hãy dùng ZoneId rõ ràng khi nghiệp vụ gắn với một vùng cụ thể:

~~~java
ZoneId zone = ZoneId.of("Europe/Paris");
ZonedDateTime appointment = instant.atZone(zone);
~~~

Không nên mặc định rằng ZoneId.systemDefault() giống nhau giữa máy phát triển, CI, container và production.

## 6. Locale mặc định và provider được chọn

Nếu không truyền Locale vào API định dạng, Java thường dùng Locale mặc định. Locale này được khởi tạo dựa trên môi trường của JVM.

Ví dụ:

~~~java
NumberFormat defaultFormat = NumberFormat.getNumberInstance();
NumberFormat explicitFormat =
        NumberFormat.getNumberInstance(Locale.forLanguageTag("vi-VN"));
~~~

Hai formatter có thể tạo kết quả khác nhau vì chúng sử dụng locale khác nhau.

Java cung cấp hai nhóm default locale thường cần chú ý:

- Locale.Category.FORMAT: dùng cho định dạng ngày, giờ, số và tiền tệ.
- Locale.Category.DISPLAY: dùng cho tên hiển thị như tên ngôn ngữ hoặc quốc gia.

Có thể kiểm tra chúng bằng:

~~~java
Locale formatLocale = Locale.getDefault(Locale.Category.FORMAT);
Locale displayLocale = Locale.getDefault(Locale.Category.DISPLAY);
~~~

Để xác định nguồn dữ liệu locale, JDK Reference Implementation hiện có ba provider chính:

| Provider | Vai trò |
|---|---|
| CLDR | Dữ liệu dựa trên Unicode Common Locale Data Repository |
| HOST | Dữ liệu phản ánh thiết lập locale tùy chỉnh của hệ điều hành; khả năng hỗ trợ tùy JDK và nền tảng |
| SPI | Provider do ứng dụng hoặc thư viện triển khai qua java.text.spi và java.util.spi |

Trong Oracle JDK 26, CLDR là provider mặc định. HOST có thể dùng thiết lập hệ điều hành cho locale mặc định trên Windows và macOS; SPI dùng các LocaleServiceProvider đã cài đặt.

## 7. Cấu hình thứ tự Locale Data Provider

Có thể đặt thứ tự tìm provider bằng system property java.locale.providers. Các tên provider được phân cách bằng dấu phẩy và được tra cứu theo thứ tự ưu tiên.

Ví dụ:

~~~bash
java -Djava.locale.providers=CLDR MyApplication
~~~

Đây là hành vi mặc định của JDK Reference Implementation hiện hành.

Nếu ứng dụng có custom LocaleServiceProvider và muốn ưu tiên provider đó trước CLDR:

~~~bash
java -Djava.locale.providers=SPI,CLDR MyApplication
~~~

Nếu muốn ưu tiên dữ liệu locale từ hệ điều hành trước CLDR, trên JDK có hỗ trợ HOST:

~~~bash
java -Djava.locale.providers=HOST,CLDR MyApplication
~~~

Lưu ý:

- Giá trị property được đọc và cache khi LocaleServiceProvider được khởi tạo.
- Hãy cấu hình từ command line hoặc launcher trước khi ứng dụng khởi động.
- Gọi System.setProperty("java.locale.providers", ...) sau khi các lớp locale đã được khởi tạo có thể không thay đổi thứ tự tra cứu.
- HOST có thể khiến kết quả phụ thuộc máy hoặc hệ điều hành; cần kiểm thử đúng môi trường triển khai.
- SPI chỉ hữu ích khi ứng dụng thực sự đóng gói provider triển khai các interface tương ứng.

**Không dùng COMPAT hoặc JRE như cách quay lại dữ liệu locale cũ.** Hai tên này từng chỉ legacy locale data của JDK 8 và các JDK trước đó. Legacy provider đã bị loại khỏi JDK 23; đặt COMPAT/JRE trong java.locale.providers trên các JDK hiện hành không khôi phục được dữ liệu cũ.

Nếu cần giữ một định dạng nghiệp vụ cụ thể, hãy định nghĩa formatter hoặc custom LocaleServiceProvider theo hợp đồng của ứng dụng, thay vì phụ thuộc một provider đã bị loại bỏ.

## 8. Dùng Locale và ZoneId tường minh

Một cách giảm khác biệt do môi trường là truyền Locale rõ ràng cho từng formatter:

~~~java
Locale locale = Locale.forLanguageTag("fr-FR");

DateTimeFormatter dateFormatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.FULL)
                .withLocale(locale);

NumberFormat numberFormatter =
        NumberFormat.getNumberInstance(locale);
~~~

Điều này giúp kết quả không vô tình thay đổi chỉ vì Locale mặc định trên máy chạy khác nhau.

Tuy nhiên, Locale tường minh chỉ cố định lựa chọn ngôn ngữ và vùng. Nó không cố định phiên bản CLDR. Khi nâng cấp JDK, cùng Locale fr-FR vẫn có thể nhận mẫu ngày, tên tháng hoặc ký hiệu tiền tệ mới.

Nếu nghiệp vụ cần một timezone cụ thể, truyền ZoneId rõ ràng:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime localTime = instant.atZone(zone);
~~~

Nếu cần định dạng ngày tháng theo một quy ước nghiệp vụ cố định, dùng pattern rõ ràng thay cho localized style. Pattern cố định có thể ổn định cấu trúc, nhưng tên tháng hoặc tên thứ dạng chữ vẫn lấy từ dữ liệu locale.

## 9. Không dùng chuỗi hiển thị làm dữ liệu trao đổi

Chuỗi được format cho người dùng không nên trở thành định dạng lưu trữ hoặc giao thức trao đổi giữa các hệ thống.

Không nên:

- Lưu "08/03/2025" rồi giả định mọi JDK hoặc locale đều parse giống nhau.
- Lưu "1.234,56 €" làm giá trị tiền tệ trong database.
- Dùng tên tháng hoặc tên múi giờ đã localized làm khóa dữ liệu.
- So sánh số bằng chuỗi đã format.
- Gửi chuỗi localized qua API rồi parse lại bằng locale mặc định của server.

Nên lưu dữ liệu có cấu trúc:

| Loại dữ liệu | Cách lưu/trao đổi phù hợp |
|---|---|
| Ngày lịch không gắn giờ | LocalDate hoặc ISO-8601 yyyy-MM-dd |
| Thời điểm tuyệt đối | Instant hoặc ISO-8601 UTC |
| Thời điểm theo vùng | LocalDateTime/ZonedDateTime cùng ZoneId rõ ràng, tùy nghiệp vụ |
| Số thập phân chính xác | BigDecimal hoặc dạng decimal theo schema |
| Tiền tệ | Giá trị số cùng currency code ISO 4217 |
| Locale người dùng | BCP 47 language tag, ví dụ fr-FR hoặc vi-VN |
| Chuỗi hiển thị | Tạo tại biên giao diện theo locale được chọn |

Ví dụ:

~~~java
LocalDate invoiceDate = LocalDate.of(2025, 3, 8);
String storedDate = invoiceDate.toString();

BigDecimal amount = new BigDecimal("1234567.89");
Currency currency = Currency.getInstance("EUR");
String currencyCode = currency.getCurrencyCode();
~~~

Giá trị lưu trữ không chứa dấu phân nhóm hoặc ký hiệu tiền tệ phụ thuộc locale. Khi hiển thị, ứng dụng mới dùng NumberFormat với locale và currency đã chọn.

## 10. Định dạng cố định khi cần hợp đồng chuỗi ổn định

Nếu hệ thống bắt buộc trao đổi chuỗi, hãy định nghĩa pattern và quy tắc parse rõ ràng thay vì dùng localized style.

Ví dụ ngày ISO:

~~~java
DateTimeFormatter machineDate =
        DateTimeFormatter.ISO_LOCAL_DATE;

String encoded = machineDate.format(LocalDate.of(2025, 3, 8));
LocalDate parsed = LocalDate.parse(encoded, machineDate);
~~~

Kết quả là:

~~~text
2025-03-08
~~~

Với format do ứng dụng tự định nghĩa:

~~~java
DateTimeFormatter businessDate =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
~~~

Pattern tường minh cố định thứ tự trường và dấu phân cách. Nếu pattern có tên tháng hoặc tên thứ dạng chữ, phần tên đó vẫn có thể phụ thuộc locale data. Với giao thức máy, ưu tiên chữ số và ký hiệu được định nghĩa rõ trong schema.

Không nên tự viết parser mơ hồ cho các chuỗi như 03/04/2025 vì thứ tự ngày/tháng có thể khác nhau. Nếu nhận dữ liệu người dùng theo locale, hãy parse tại biên nhập liệu với locale đã biết, xác thực, sau đó chuyển thành kiểu dữ liệu chuẩn trước khi lưu.

## 11. Kiểm thử trước khi nâng cấp JDK

Locale data thay đổi là một dạng behavioral compatibility. Cần có kiểm thử hồi quy trước khi thay JDK ở CI, staging và production.

Một quy trình hữu ích:

1. Ghi lại JDK vendor, feature version và runtime version đang dùng.
2. Ghi lại java.locale.providers, Locale FORMAT/DISPLAY mặc định và ZoneId mặc định.
3. Liệt kê các locale quan trọng của sản phẩm, không chỉ locale của máy phát triển.
4. Chạy bộ test format và parse trên JDK hiện tại và JDK mục tiêu.
5. So sánh các chuỗi hiển thị quan trọng với golden output đã được duyệt.
6. Kiểm tra round-trip parse/format và các trường hợp biên.
7. Kiểm tra lịch tuần, giờ mùa hè, ngày chuyển đổi timezone và các thời điểm tương lai.
8. Cập nhật snapshot có chủ đích nếu thay đổi đúng theo dữ liệu locale mới.
9. Kiểm tra runtime image nếu ứng dụng dùng jlink để bảo đảm locale data cần thiết vẫn được đóng gói.

Nên có test cho:

- Ngày FULL, LONG, MEDIUM và SHORT ở các locale quan trọng.
- Giờ 12/24 giờ, AM/PM và tên múi giờ.
- Số âm, số lớn, số có nhiều chữ số thập phân và dấu phân nhóm.
- Tiền tệ với nhiều currency code và locale khác nhau.
- Ngày đầu tuần và số tuần trong năm.
- Parse chuỗi đã lưu từ các phiên bản trước.
- Các locale dùng chữ số không phải Latin hoặc Unicode extension nếu ứng dụng hỗ trợ.

Không nên chỉ chạy test trên một máy có Locale mặc định cố định. Hãy truyền Locale rõ ràng trong test và chạy thêm test tích hợp trên đúng môi trường OS/provider của production nếu dùng HOST.

## 12. Kiểm tra môi trường runtime

Đoạn mã sau giúp ghi nhận thông tin môi trường để chẩn đoán khác biệt sau khi nâng cấp:

~~~java
import java.time.ZoneId;
import java.util.Locale;

public class LocaleEnvironment {
    public static void main(String[] args) {
        System.out.println("JDK: " + Runtime.version());
        System.out.println("java.locale.providers: " +
                System.getProperty("java.locale.providers", "<default>"));
        System.out.println("format locale: " +
                Locale.getDefault(Locale.Category.FORMAT).toLanguageTag());
        System.out.println("display locale: " +
                Locale.getDefault(Locale.Category.DISPLAY).toLanguageTag());
        System.out.println("system zone: " + ZoneId.systemDefault());
    }
}
~~~

Lưu ý rằng API Java không cung cấp một phương thức chuẩn để truy vấn trực tiếp phiên bản CLDR đang nhúng trong JDK. Hãy ghi lại JDK vendor/version và đối chiếu bảng CLDR của đúng bản JDK đang triển khai.

Nếu ứng dụng sử dụng timezone database, có thể kiểm tra phiên bản dữ liệu của một vùng bằng ZoneRulesProvider:

~~~java
NavigableMap<String, ZoneRules> versions =
        ZoneRulesProvider.getVersions("Europe/Paris");
System.out.println(versions.lastKey());
~~~

Phiên bản timezone database và phiên bản CLDR là hai thông tin riêng. Ghi lại cả hai khi ứng dụng cần tái hiện chính xác kết quả định dạng hoặc quy đổi thời gian.

## 13. Runtime image và module jdk.localedata

Với runtime image được tạo bằng jlink, locale data có thể bị lược bỏ để giảm kích thước.

Trong Oracle JDK 26, java.base chứa dữ liệu locale tiếng Anh Mỹ và các parent locale cần thiết; dữ liệu của nhiều locale khác nằm trong module jdk.localedata. Nếu runtime image không chứa module hoặc không giữ locale cần dùng, ứng dụng có thể thiếu dữ liệu cho một số locale.

Ví dụ tạo runtime image chỉ giữ tiếng Anh, tiếng Nhật và các locale của Ấn Độ:

~~~bash
jlink --add-modules java.base,jdk.localedata \
      --include-locales en,ja,*-IN \
      --output runtime
~~~

Danh sách module và locale thực tế cần phụ thuộc ứng dụng. Hãy kiểm thử chính runtime image đã đóng gói, không chỉ kiểm thử bằng một JDK đầy đủ trên máy lập trình.

## 14. Những lỗi thường gặp và cách tránh

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ Locale chứa sẵn toàn bộ quy tắc định dạng | Cùng Locale có thể cho chuỗi khác sau khi nâng cấp JDK | Xem Locale là định danh; kiểm thử dữ liệu provider |
| Dùng Locale mặc định trong logic nghiệp vụ | Kết quả phụ thuộc môi trường chạy | Truyền Locale rõ ràng |
| Nghĩ Locale tường minh đóng băng CLDR | Dữ liệu CLDR vẫn thay đổi theo JDK | Kiểm thử lại trên JDK mục tiêu |
| Lưu chuỗi localized vào database | Bản ghi cũ có thể không parse được sau nâng cấp | Lưu kiểu dữ liệu chuẩn hoặc chuỗi theo schema cố định |
| So sánh chuỗi tiền tệ | Khác biệt dấu cách, ký hiệu hoặc dấu nhóm làm sai so sánh | So sánh BigDecimal và currency code |
| Dùng HOST mà không kiểm thử môi trường | Kết quả khác giữa Windows, macOS hoặc hệ thống khác | Chỉ dùng khi cần OS locale và kiểm thử trên môi trường đích |
| Đổi java.locale.providers bằng System.setProperty quá muộn | Provider order có thể đã được cache | Đặt property lúc khởi chạy JVM |
| Dùng COMPAT/JRE để quay lại dữ liệu cũ trên JDK mới | Provider legacy đã bị loại từ JDK 23 | Chuyển sang CLDR hoặc định nghĩa formatter/provider riêng |
| Chỉ kiểm tra format, không kiểm tra parse | Chuỗi mới có thể làm dữ liệu cũ không parse được | Có test tương thích parse dữ liệu lịch sử |
| Chỉ kiểm thử trên JDK đầy đủ | Runtime image có thể thiếu jdk.localedata hoặc locale cần thiết | Kiểm thử bản image được tạo bằng jlink |
| Nhầm CLDR với timezone database | Bỏ sót thay đổi quy tắc múi giờ | Kiểm thử CLDR và tzdb riêng biệt |
| Chấp nhận snapshot mới tự động | Thay đổi hiển thị ngoài ý muốn lọt vào sản phẩm | Review và phê duyệt golden output khi nâng cấp |

## 15. Ví dụ hoàn chỉnh: quan sát dữ liệu locale theo JDK

Chương trình sau dùng Locale tường minh để định dạng ngày và tiền tệ. Nó đồng thời in ngày ISO để phân biệt dữ liệu hiển thị với giá trị chuẩn có thể lưu trữ.

Lưu thành **LocaleDataProbe.java**:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocaleDataProbe {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("fr-FR");
        LocalDate date = LocalDate.of(2025, 3, 8);

        DateTimeFormatter localizedDate =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.FULL)
                        .withLocale(locale);
        NumberFormat currency =
                NumberFormat.getCurrencyInstance(locale);

        System.out.println("JDK feature: " +
                Runtime.version().feature());
        System.out.println("locale tag: " + locale.toLanguageTag());
        System.out.println("localized date: " +
                localizedDate.format(date));
        System.out.println("localized currency: " +
                currency.format(new BigDecimal("1234567.89")));
        System.out.println("canonical date: " + date);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all LocaleDataProbe.java
java LocaleDataProbe
~~~

Kết quả khi kiểm thử trên OpenJDK 24.0.2:

~~~text
JDK feature: 24
locale tag: fr-FR
localized date: samedi 8 mars 2025
localized currency: 1 234 567,89 €
canonical date: 2025-03-08
~~~

Chuỗi ngày và tiền tệ là dữ liệu hiển thị theo locale fr-FR và CLDR của JDK đang chạy. Khi nâng cấp JDK, hãy chạy lại chương trình và kiểm tra các chuỗi đó. Dòng canonical date giữ dạng ISO của LocalDate và phù hợp hơn cho trao đổi hoặc lưu trữ dữ liệu ngày.

## 16. Ghi nhớ

- Locale là định danh BCP 47; dữ liệu định dạng được cung cấp bởi runtime hoặc LocaleServiceProvider.
- Dữ liệu locale có thể thay đổi giữa các feature release khi JDK cập nhật CLDR.
- JDK 26 dùng CLDR 48; JDK 25 dùng CLDR 47 và JDK 24 dùng CLDR 46.
- JDK 9 chuyển CLDR thành nguồn locale data mặc định.
- JDK 26 hỗ trợ các provider CLDR, HOST và SPI; COMPAT/JRE đã bị loại từ JDK 23.
- Locale tường minh giảm phụ thuộc vào default locale nhưng không khóa phiên bản CLDR.
- Dữ liệu locale có thể ảnh hưởng định dạng và phân tích ngày, giờ, số, tiền tệ, tên hiển thị và quy tắc tuần.
- Timezone database là nguồn dữ liệu riêng; hãy kiểm thử tzdb khi nâng cấp.
- Không dùng chuỗi localized làm dữ liệu lưu trữ hoặc giao thức.
- Lưu ngày, thời điểm, số và tiền tệ bằng kiểu dữ liệu chuẩn; chỉ format khi hiển thị.
- Đặt java.locale.providers trước khi JVM khởi tạo dịch vụ locale.
- Kiểm thử trên JDK mục tiêu và runtime image thực tế; review các golden output trước khi phát hành.

## Tài liệu tham khảo

- [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252)
- [Locale — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html)
- [LocaleServiceProvider — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleServiceProvider.html)
- [JDK 26 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk26-supported-locales.html)
- [JDK 26 Release Notes — CLDR Version 48](https://www.oracle.com/java/technologies/javase/26all-relnotes.html)
- [JDK 26 Migration Guide — Changes to Locale Data](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html)
- [JDK 24 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk24-suported-locales.html)
- [Unicode CLDR Releases](https://cldr.unicode.org/index/downloads)
