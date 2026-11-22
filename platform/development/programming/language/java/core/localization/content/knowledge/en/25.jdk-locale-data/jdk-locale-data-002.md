# Locale.getAvailableLocales so với locale hỗ trợ của từng dịch vụ trong Java

Khi xây dựng phần mềm Java đa ngôn ngữ, lập trình viên có thể gọi **Locale.getAvailableLocales()**, nhận hàng trăm đối tượng Locale và tưởng rằng mọi tính năng quốc tế hóa của JVM đều hỗ trợ đầy đủ các locale đó. Kết luận ấy chưa chính xác. **Danh sách locale cấp runtime** không tương đương **danh sách locale của từng dịch vụ**, càng không tương đương **danh sách ngôn ngữ mà sản phẩm đã dịch và kiểm thử**.

Ví dụ, **NumberFormat**, **DateFormat**, **Collator**, **BreakIterator**, **DateFormatSymbols**, **DecimalFormatSymbols** đều có những API hoặc dữ liệu chuyên biệt. Một locale có thể được môi trường Java công bố nhưng không có cùng độ sâu dữ liệu cho tất cả dịch vụ. Ngược lại, nếu một factory có thể tạo đối tượng với locale ít phổ biến, điều đó có thể là kết quả của **fallback**, chưa chứng minh có dữ liệu riêng đúng từng vùng.

Bài học này giải thích cách phân biệt **locale identifier**, **locale do JDK công bố**, **locale do từng dịch vụ công bố** và **locale do ứng dụng cam kết hỗ trợ**; cách kiểm tra chúng bằng Java 17+, quản lý CLDR/provider, chọn fallback và xây cơ chế lựa chọn ngôn ngữ an toàn.

## 1. Bốn tầng của từ “hỗ trợ locale”

| Tầng | Câu hỏi cần trả lời | Công cụ |
| --- | --- | --- |
| Định danh locale | Có thể tạo đối tượng Locale mang mã ngôn ngữ/vùng này không? | Locale.forLanguageTag, Locale.Builder |
| Khả năng công bố chung của JDK | JVM hiện tại liệt kê những locale nào? | Locale.getAvailableLocales() |
| Khả năng của dịch vụ | Dịch vụ số/ngày/từ điển/phân đoạn công bố locale nào? | Các lớp dịch vụ và getAvailableLocales() riêng |
| Khả năng của sản phẩm | Có bản dịch UI, nội dung, font, QA và chính sách fallback không? | Danh sách appSupportedLocales của dự án |

**Bốn danh sách này không được tự động coi là bằng nhau.** Một ứng dụng có thể chỉ hỗ trợ giao diện tiếng Việt và tiếng Anh, trong khi Java runtime có dữ liệu định dạng cho nhiều locale hơn. Một locale có mặt trong danh sách chung cũng không chứng minh tất cả dịch vụ có tailoring chuyên biệt cho nó.

Bài toán phải bắt đầu bằng câu hỏi cụ thể: “App hỗ trợ tiếng Việt trong UI?” khác với “JDK biết cách định dạng số theo vi-VN?” và khác với “Collator vi-VN sắp danh bạ như từ điển tiếng Việt?”.

## 2. Locale là định danh chứ không phải bộ tài nguyên

**java.util.Locale** mang các thành phần ngôn ngữ, script, quốc gia/vùng, variant và một số extensions được biểu diễn bằng language tag. Nó không tự chứa tất cả từ dịch, pattern ngày giờ và quy tắc xếp thứ tự.

**File LocaleIdentity.java**

~~~java
import java.util.Locale;

public class LocaleIdentity {
    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        Locale ca = Locale.forLanguageTag("fr-CA");

        System.out.println(vi.toLanguageTag());
        System.out.println(vi.getLanguage());
        System.out.println(vi.getCountry());
        System.out.println(ca.toLanguageTag());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LocaleIdentity.java
java LocaleIdentity
~~~

Stdout:

~~~text
vi-VN
vi
VN
fr-CA
~~~

**Chương trình chỉ xác nhận định danh được biểu diễn đúng.** Nó không truy vấn được danh sách các bản dịch ứng dụng, không xác nhận fr-CA có kiểu collation chuyên biệt, không chứng minh Currency của giao dịch là CAD.

Locale.forLanguageTag nhận một language tag và tạo Locale theo quy tắc API; việc tạo thành công không tương đương kiểm tra hỗ trợ dịch vụ. Nếu cần validation nghiêm ngặt của một tag, nghiên cứu quy tắc **Locale.Builder**, xử lý tag không hợp lệ và giới hạn danh sách mà ứng dụng chấp nhận.

## 3. Locale.getAvailableLocales thực sự nói gì?

**Locale.getAvailableLocales()** trả mảng **Locale[]** của các locale được cài đặt/công bố trong runtime Java hiện tại. Tập locale có thể đến từ những nguồn dữ liệu mà môi trường Java và provider hỗ trợ. Đây là **thông tin về môi trường**, không phải chứng chỉ rằng mọi dịch vụ có cùng quy tắc chất lượng cao.

~~~java
Locale[] all = Locale.getAvailableLocales();
~~~

Đoạn minh họa trên nằm trong một phương thức, cần import java.util.Locale.

Các điểm phải hiểu:

1. Số lượng locale có thể thay đổi theo **phiên bản JDK, nhà cung cấp JDK, provider và cấu hình**. Không hardcode một con số chung.
2. Mảng trả về không phải danh sách ngôn ngữ mà ứng dụng đã dịch.
3. Không dựa vào **thứ tự phần tử** để xây menu.
4. Sự hiện diện của một locale không chứng minh dữ liệu chuyên biệt có ở mọi dịch vụ.
5. Một Locale có thể có extension như yêu cầu hệ chữ số; kiểm tra thành viên chính xác trong danh sách không đủ để biết extension đó được xử lý hoàn chỉnh.
6. Khi cần năng lực cụ thể, phải hỏi đúng dịch vụ rồi kiểm tra hành vi trên runtime triển khai.

**Tóm lại:** Locale.getAvailableLocales là một điểm khởi đầu của khả năng quốc tế hóa trong JDK, không phải lời cam kết toàn bộ chức năng của sản phẩm.

## 4. Từng dịch vụ có tập locale riêng

Java có các API static **getAvailableLocales()** ở các lớp định dạng và xử lý ngôn ngữ:

| API | Năng lực được công bố |
| --- | --- |
| **NumberFormat.getAvailableLocales()** | Dịch vụ định dạng số và các biến thể number/currency/percent |
| **DateFormat.getAvailableLocales()** | Dịch vụ định dạng ngày giờ kiểu java.text |
| **Collator.getAvailableLocales()** | Dịch vụ so sánh/xếp thứ tự văn bản theo ngôn ngữ |
| **BreakIterator.getAvailableLocales()** | Dịch vụ xác định ranh giới văn bản |
| **DateFormatSymbols.getAvailableLocales()** | Ký hiệu và tên liên quan ngày giờ |
| **DecimalFormatSymbols.getAvailableLocales()** | Ký hiệu liên quan số, dấu thập phân, dấu nhóm |
| **Locale.getAvailableLocales()** | Danh sách tổng quát cấp runtime |

**Danh sách dịch vụ không phải phép chiếu đơn giản của danh sách chung.** Mỗi dịch vụ trả những locale mà nó công bố theo hợp đồng API và nguồn provider tương ứng. Không suy từ NumberFormat rằng Collator cũng có locale chuyên biệt; không suy từ DateFormatSymbols rằng DateFormat đáp ứng mọi cách hiển thị.

Một vài trường hợp cần phân biệt:

- **Currency.getAvailableCurrencies()** trả **Set<Currency>**, là tập đồng tiền, không phải Locale[].
- **DateTimeFormatter** của java.time không có phương thức static **getAvailableLocales()** tương đương DateFormat.
- **ResourceBundle** ứng dụng có tài nguyên riêng; không có một API chung ResourceBundle.getAvailableLocales cho mọi bộ bản dịch.
- Thư viện i18n bên thứ ba có danh sách hỗ trợ riêng, không tự động trùng JDK.

## 5. Java 17+: chương trình khảo sát đúng dịch vụ

Ví dụ này in số lượng locale phân biệt của **chính JVM đang chạy**. Các số là dữ liệu runtime nên không được đóng đinh stdout cho mọi môi trường.

**File LocaleServiceCatalog.java**

~~~java
import java.text.BreakIterator;
import java.text.Collator;
import java.text.DateFormat;
import java.text.DateFormatSymbols;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

public class LocaleServiceCatalog {
    private static Set<Locale> asSet(Locale[] locales) {
        return new HashSet<>(Arrays.asList(locales));
    }

    private static void report(String name, Locale[] locales) {
        System.out.printf(Locale.ROOT, "%s: %d%n",
                name, asSet(locales).size());
    }

    public static void main(String[] args) {
        report("Locale", Locale.getAvailableLocales());
        report("NumberFormat",
                NumberFormat.getAvailableLocales());
        report("DateFormat",
                DateFormat.getAvailableLocales());
        report("Collator",
                Collator.getAvailableLocales());
        report("BreakIterator",
                BreakIterator.getAvailableLocales());
        report("DateFormatSymbols",
                DateFormatSymbols.getAvailableLocales());
        report("DecimalFormatSymbols",
                DecimalFormatSymbols.getAvailableLocales());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LocaleServiceCatalog.java
java LocaleServiceCatalog
~~~

Chương trình in đúng **bảy dòng**, theo thứ tự nhãn **Locale**, **NumberFormat**, **DateFormat**, **Collator**, **BreakIterator**, **DateFormatSymbols**, **DecimalFormatSymbols**; sau mỗi dấu hai chấm là một số nguyên không âm do môi trường hiện tại trả về.

**Không gán một bộ stdout số lượng cố định**: con số ấy là đối tượng đang được khảo sát. Nếu hai lớp cùng có N locale, chưa thể kết luận danh sách giống nhau; cần so thành viên. Nếu số lượng khác, đó không tự động là lỗi hay chứng minh chất lượng dữ liệu của một locale riêng lẻ.

Dùng **Set<Locale>** để đếm thành viên phân biệt thay vì dựa vào giả định mảng được sắp sẵn hoặc thứ tự có ý nghĩa. Locale.ROOT ở printf chỉ làm rõ định dạng báo cáo kỹ thuật; nó không thay dữ liệu bên trong từng mảng.

## 6. Kiểm tra thành viên của một locale mục tiêu

Để so ba tập, dùng Set và contains với cùng đối tượng Locale:

**File LocaleMembership.java**

~~~java
import java.text.Collator;
import java.text.NumberFormat;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

public class LocaleMembership {
    private static Set<Locale> set(Locale[] values) {
        return new HashSet<>(Arrays.asList(values));
    }

    public static void main(String[] args) {
        Locale target = Locale.forLanguageTag("vi-VN");

        System.out.println("locale=" + target.toLanguageTag());
        System.out.println("general="
                + set(Locale.getAvailableLocales())
                        .contains(target));
        System.out.println("number="
                + set(NumberFormat.getAvailableLocales())
                        .contains(target));
        System.out.println("collation="
                + set(Collator.getAvailableLocales())
                        .contains(target));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LocaleMembership.java
java LocaleMembership
~~~

Dòng đầu luôn là:

~~~text
locale=vi-VN
~~~

Ba dòng tiếp theo có nhãn **general=**, **number=**, **collation=** và một giá trị true/false do JDK hiện tại quyết định. Không suy đoán boolean trước khi chạy.

**Ý nghĩa:** để xét chất lượng định dạng số, kiểm tra NumberFormat và chạy các ví dụ số; để xét thứ tự từ điển, kiểm tra Collator rồi thử danh sách tên thật. Không dùng một phép contains trên Locale.getAvailableLocales để kết luận mọi khả năng.

### 6.1. Vì sao exact membership chưa đủ cho locale extension?

Một Locale có thể mang Unicode extension như **en-US-u-nu-arab**. Nó yêu cầu cách biểu diễn chữ số nhưng có thể không xuất hiện như một phần tử nguyên văn trong mọi getAvailableLocales. Điều này **không tự chứng minh** NumberFormat không xử lý được extension đó, cũng không bảo đảm nó có hỗ trợ đầy đủ.

Hãy phân biệt **một locale được liệt kê** và **một tính năng của locale được thực thi đúng theo extension**. Kiểm tra formatter thực tế, tài liệu runtime và output.

## 7. Có trong danh sách không đồng nghĩa đủ chức năng

Giả sử **fr-CA** hiện diện ở một danh sách. Sản phẩm vẫn cần kiểm tra:

- **NumberFormat**: dấu thập phân, dấu phân nhóm và số chữ số khi format tiền.
- **DateFormat**: thứ tự thành phần, tên tháng/ngày và dấu câu.
- **Collator**: thứ tự các từ có dấu và biến thể chữ.
- **BreakIterator**: vị trí ngắt từ, câu hoặc cụm ký tự.
- **DateFormatSymbols** và **DecimalFormatSymbols**: ký hiệu thực tế.
- **UI translations**: văn bản và thông báo lỗi đúng fr-CA, không bị rơi về một ngôn ngữ khác.
- **Font/RTL/accessibility**: mức độ phù hợp của giao diện theo ngôn ngữ.
- **Chính sách nghiệp vụ**: currency thực tế của giao dịch, timezone, nội dung pháp lý và định dạng phải tuân thủ.

**Metadata “có hỗ trợ” không thay thế functional tests**. Một dịch vụ có thể cung cấp fallback hợp lệ về mặt API nhưng chưa đủ tiêu chuẩn chất lượng của sản phẩm.

## 8. Thiếu trong danh sách không đồng nghĩa factory chắc chắn thất bại

Một lời gọi:

~~~java
Locale requested = Locale.forLanguageTag("fr-CA");
NumberFormat format =
        NumberFormat.getNumberInstance(requested);
String result = format.format(1234.5);
~~~

Đoạn minh họa cần import **java.util.Locale** và **java.text.NumberFormat**; đặt trong phương thức. Factory có thể lấy dữ liệu phù hợp hoặc dùng cơ chế fallback tùy runtime. **Không lấy việc format thành công làm bằng chứng tuyệt đối rằng có dữ liệu chuyên biệt đúng fr-CA**.

Tương tự, nếu một Locale không xuất hiện trong mảng service, đừng tự viết thông báo “Java cannot format this Locale”. Có thể runtime vẫn sinh ra một kết quả dự phòng. Nhưng nếu sản phẩm cần định dạng chuyên biệt, bạn có thể **chủ động cấm fallback chưa được kiểm thử** theo hợp đồng sản phẩm.

### 8.1. Dấu hiệu fallback và hậu quả

Fallback có thể khiến:

- Tên tháng thuộc dạng chung thay vì dạng riêng vùng.
- Thứ tự/ngôn ngữ không như mong đợi.
- Ký hiệu số hoặc tiền không theo kiểu người dùng quen.
- Một phần câu UI xuất hiện bằng ngôn ngữ khác.
- Các bản JDK khác nhau cho kết quả khác.

Không có một method chung trên mọi formatter để hỏi chính xác **effective locale sau fallback**. Vì vậy nên log requested locale, selected app locale, loại dịch vụ và phiên bản runtime, kèm test output trọng yếu.

## 9. CLDR, SPI và hệ thống LocaleServiceProvider

Java sử dụng những nguồn dữ liệu địa phương hóa và cơ chế locale provider. Trong những runtime hiện đại, **CLDR** là nguồn dữ liệu quan trọng; có thể gặp **SPI** (providers được đăng ký), một số khả năng **HOST** tùy runtime/hệ điều hành và các provider tương thích ở những JDK còn hỗ trợ. Tập provider và thứ tự có thể được cấu hình tùy phiên bản, chẳng hạn qua thuộc tính JVM **java.locale.providers** ở các phiên bản hỗ trợ.

**Không giả định mọi bản JDK 17+ đều có chính xác cùng danh sách giá trị cấu hình provider.** Một provider di sản có thể được thay đổi hoặc loại bỏ trong bản Java mới.

Một số loại SPI:

| API provider | Chức năng |
| --- | --- |
| **java.text.spi.NumberFormatProvider** | Tạo định dạng số |
| **java.text.spi.DateFormatProvider** | Tạo định dạng ngày giờ legacy |
| **java.text.spi.CollatorProvider** | So sánh ngôn ngữ |
| **java.text.spi.BreakIteratorProvider** | Phân đoạn văn bản |
| **java.text.spi.DecimalFormatSymbolsProvider** | Ký hiệu số |
| **java.text.spi.DateFormatSymbolsProvider** | Ký hiệu ngày tháng |
| **java.util.spi.CurrencyNameProvider** | Tên và ký hiệu tiền |
| **java.util.spi.LocaleNameProvider** | Tên ngôn ngữ và vùng |
| **java.util.spi.TimeZoneNameProvider** | Tên vùng giờ |
| **java.util.spi.CalendarDataProvider** | Dữ liệu lịch địa phương |

Chúng liên quan đến **java.util.spi.LocaleServiceProvider**, nhưng mỗi loại có dữ liệu/khả năng riêng.

**Tại sao cùng code có thể cho kết quả khác?** Vì JDK version, dữ liệu CLDR, tùy chọn provider, môi trường HOST hoặc thư viện SPI được cài có thể khác. Đừng tự coi sự khác nhau đó là lỗi; phải đối chiếu với hợp đồng của sản phẩm và bộ runtime được hỗ trợ.

### 9.1. Thay đổi provider có thể thay danh sách và output

Một quy trình kiểm thử nâng cấp JDK nên lưu phiên bản runtime, cấu hình provider và các output trọng yếu. Không khẳng định rằng chỉ cần **vi-VN** có mặt ở Locale.getAvailableLocales thì tất cả pattern và cách sắp tên tiếng Việt vẫn giữ y hệt qua mọi phiên bản.

## 10. NumberFormat, DecimalFormatSymbols và currency

Một locale có thể cần nhiều loại định dạng số:

~~~java
NumberFormat number =
        NumberFormat.getNumberInstance(locale);
NumberFormat currency =
        NumberFormat.getCurrencyInstance(locale);
NumberFormat percent =
        NumberFormat.getPercentInstance(locale);
~~~

Đoạn minh họa trong phương thức, cần import NumberFormat/Locale và biến locale. **NumberFormat.getAvailableLocales()** có ích để khảo sát dịch vụ, nhưng kết quả thực tế còn phụ thuộc kiểu formatter và chính sách.

**DecimalFormatSymbols.getAvailableLocales()** lại công bố các locale có ký hiệu thập phân, phân nhóm, chữ số và các dấu khác của dịch vụ symbols. Nó không làm nhiệm vụ tính toán tỷ giá.

Nếu giao dịch là EUR, có thể cần:

~~~java
currency.setCurrency(
        Currency.getInstance("EUR"));
~~~

Đoạn minh họa cần import java.util.Currency. **setCurrency không đổi số tiền từ VND sang EUR**, nó chỉ cấu hình đơn vị được hiển thị. Currency.getAvailableCurrencies là tập loại tiền và không chứng minh locale hỗ trợ một ngôn ngữ UI.

Đừng đồng nhất currency mặc định của một vùng với đồng tiền của giao dịch. Trong nhiều ứng dụng, **amount + Currency** là dữ liệu nghiệp vụ, còn **Locale** là lựa chọn hiển thị.

## 11. DateFormat và DateTimeFormatter không có cùng API khám phá locale

**DateFormat.getAvailableLocales()** dành cho dịch vụ định dạng ngày giờ kiểu **java.text**:

~~~java
DateFormat legacy =
        DateFormat.getDateInstance(
                DateFormat.FULL, locale);
~~~

Còn Java 17 khuyến nghị **java.time**:

~~~java
DateTimeFormatter modern =
        DateTimeFormatter.ofLocalizedDate(
                FormatStyle.FULL)
                .withLocale(locale);
~~~

Đây là hai đoạn minh họa trong phương thức, cần import DateFormat, DateTimeFormatter, FormatStyle, Locale và có biến locale.

**DateTimeFormatter không công bố một static DateTimeFormatter.getAvailableLocales() như DateFormat.** Nếu muốn xác nhận localized date formatter đáp ứng yêu cầu cho locale nào, hãy thử formatter, kiểu ngày/lịch và FormatStyle mà sản phẩm thực sự dùng. Kiểm tra tên tháng/ngày, thứ tự trường và dấu câu; không chỉ tra một danh sách tổng quát.

Đặc biệt, **Locale không phải ZoneId**: một LocalDate khác với Instant, và giờ người dùng ở địa điểm nào phải được xác định bằng timezone khi cần. Locale có sẵn không chứng minh ứng dụng đã chọn múi giờ phù hợp.

## 12. Collator: locale cho so sánh theo từ điển

**Collator.getAvailableLocales()** là danh sách của dịch vụ so sánh chuỗi theo ngôn ngữ. Nếu sản phẩm sắp tên tiếng Việt, nên lấy locale cụ thể:

~~~java
Collator collator =
        Collator.getInstance(
                Locale.forLanguageTag("vi-VN"));
collator.setStrength(Collator.TERTIARY);
~~~

Đoạn minh họa dùng import Collator, Locale. Nhưng việc có vi-VN trong danh sách không chứng minh bộ quy tắc mặc định đáp ứng mọi tiêu chuẩn của một từ điển chuyên ngành.

Cần test:

- Chữ **ă, â, đ, ê, ô, ơ, ư**.
- Các dấu thanh, chữ hoa và chữ thường.
- Cặp Unicode dựng sẵn và combining marks.
- Strength và decomposition.
- Nhiều hệ chữ lẫn nhau và dấu câu.
- Khác biệt giữa JDK/provider khi nâng cấp.

**String.compareTo** chỉ so các char UTF-16; nó không thay thế Collator khi người dùng mong thứ tự từ điển.

## 13. BreakIterator: locale cho phân đoạn văn bản

**BreakIterator.getAvailableLocales()** cho biết những locale mà dịch vụ công bố. Các factory:

~~~java
BreakIterator words =
        BreakIterator.getWordInstance(locale);
BreakIterator sentences =
        BreakIterator.getSentenceInstance(locale);
BreakIterator characters =
        BreakIterator.getCharacterInstance(locale);
~~~

Đây là đoạn minh họa cần import BreakIterator và Locale, biến locale.

Một locale được công bố không bảo đảm mọi ranh giới từ/câu trên dữ liệu thực tế của sản phẩm đều đúng ý định. Đặc biệt, một số hệ chữ có quy tắc phân đoạn phức tạp; **String.split(" ")** không tự thay thế được word boundary cho mọi ngôn ngữ.

Nếu ứng dụng dùng double-click để chọn từ, tìm điểm cắt câu hoặc phân tích đoạn có emoji/combining marks, hãy test những chức năng ấy. Đừng dùng thành công của NumberFormat để suy ra BreakIterator đáp ứng nhu cầu của trình soạn thảo.

## 14. ResourceBundle: JDK có locale chưa chắc app đã có bản dịch

Giả sử sản phẩm có các file:

~~~text
messages.properties
messages_en.properties
messages_vi.properties
~~~

Đây là ví dụ về file do **ứng dụng** quản lý. **ResourceBundle** có cơ chế tìm bundle theo Locale và fallback. Nếu yêu cầu fr-CA nhưng ứng dụng chỉ có base bundle, việc gọi getBundle có thể **trả về bản base**. Đây không phải bằng chứng sản phẩm đã dịch tiếng Pháp Canada.

Một locale hỗ trợ ở tầng sản phẩm cần:

1. Đầy đủ chuỗi UI cốt lõi, thông báo lỗi, email, accessibility labels.
2. Quy trình dịch và review.
3. Kiểm thử màn hình, biểu mẫu, ngày giờ, số tiền.
4. Font, hiển thị RTL (nếu cần), nội dung địa phương.
5. Chính sách fallback được mô tả rõ.
6. Đơn vị tiền, múi giờ và các giá trị nghiệp vụ được mô hình hóa riêng.
7. Kiểm thử chất lượng trên thiết bị/môi trường mục tiêu.

**Không xây dropdown ngôn ngữ từ Locale.getAvailableLocales.** Danh sách ấy có thể lớn hơn nhiều so với các ngôn ngữ app đã thực sự cung cấp.

## 15. Danh sách locale do sản phẩm công bố

Nên khai báo một tập **appSupportedLocales** tường minh. Ví dụ Java 17:

**File AppSupportedLocales.java**

~~~java
import java.util.List;
import java.util.Locale;

public class AppSupportedLocales {
    private static final List<Locale> SUPPORTED = List.of(
            Locale.forLanguageTag("vi-VN"),
            Locale.US,
            Locale.FRANCE);

    public static boolean isSupported(Locale locale) {
        return SUPPORTED.contains(locale);
    }

    public static void main(String[] args) {
        System.out.println(isSupported(
                Locale.forLanguageTag("vi-VN")));
        System.out.println(isSupported(
                Locale.forLanguageTag("ja-JP")));
        System.out.println(SUPPORTED.size());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AppSupportedLocales.java
java AppSupportedLocales
~~~

Stdout chính xác:

~~~text
true
false
3
~~~

Chương trình minh họa **chính sách của một ứng dụng giả định**, không có nghĩa ba ngôn ngữ này tự được mọi sản phẩm hỗ trợ. Khi phát hành bản dịch mới, cập nhật cấu hình và bộ test của sản phẩm thay vì cho dropdown tự mở rộng theo JDK.

### 15.1. Locale extension và exact equality

Một locale như **en-US-u-nu-arab** có Unicode extension liên quan hệ chữ số. Phép **SUPPORTED.contains(locale)** dùng equality của đối tượng Locale; một tag có extension có thể không bằng đối tượng Locale.US. Đó là quyết định kiểm tra danh sách được chọn, **không phải kết luận rằng formatter chắc chắn không áp dụng được extension**.

Ứng dụng phải quyết định rõ liệu có chấp nhận extension, giữ/lược bớt chúng, hay yêu cầu một locale chính xác. Đừng vô tình bỏ những tùy chọn calendar/numbering system có ý nghĩa đối với người dùng nếu sản phẩm đã cam kết hỗ trợ.

## 16. Locale.LanguageRange và Locale.lookup để thương lượng ngôn ngữ

Nhiều web client gửi một chuỗi ưu tiên có quality weight, ví dụ:

~~~text
vi-VN, en-US;q=0.8, fr-FR;q=0.5
~~~

Java hỗ trợ **Locale.LanguageRange.parse** và **Locale.lookup** để tìm lựa chọn phù hợp trong **danh sách ứng dụng truyền vào**.

**File LocaleNegotiation.java**

~~~java
import java.util.List;
import java.util.Locale;

public class LocaleNegotiation {
    public static void main(String[] args) {
        List<Locale> supported = List.of(
                Locale.forLanguageTag("vi-VN"),
                Locale.US,
                Locale.FRANCE);

        List<Locale.LanguageRange> preferred =
                Locale.LanguageRange.parse(
                        "vi-VN, en-US;q=0.8, fr-FR;q=0.5");

        Locale selected =
                Locale.lookup(preferred, supported);

        if (selected == null) {
            selected = Locale.US;
        }

        System.out.println(selected.toLanguageTag());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LocaleNegotiation.java
java LocaleNegotiation
~~~

Stdout:

~~~text
vi-VN
~~~

**Locale.lookup** chọn trên **supported**, không tự thay danh sách bằng các locale JDK công bố. Nếu không có ứng viên khớp, nó có thể trả **null**, nên ứng dụng phải có fallback. Với input không hợp lệ hoặc header quá dài, cần kiểm soát lỗi và giới hạn, không trông chờ mọi chuỗi do client gửi đều an toàn/hợp lệ.

**Locale.filter** phù hợp hơn nếu muốn nhận nhiều ứng viên phù hợp thay vì một lựa chọn. Dù dùng lookup hay filter, tập supported phải do app định nghĩa theo bản dịch và QA.

## 17. Requested, selected và formatting locale không nhất thiết giống nhau

Một mô hình minh họa:

~~~text
requestedLocale   = fr-CA
selectedUiLocale  = fr-FR
formattingLocale  = fr-CA
currency          = CAD
timeZone          = America/Toronto
~~~

Đây là các giá trị ví dụ, không phải kết quả fallback mặc định của Java.

- **requestedLocale:** giá trị user yêu cầu.
- **selectedUiLocale:** ứng dụng lựa chọn từ bộ ngôn ngữ đã dịch.
- **formattingLocale:** locale dùng format ngày/số khi chức năng cần.
- **currency:** đơn vị tiền thực tế của giao dịch.
- **timeZone:** timezone cần dùng để biểu diễn Instant thành ngày giờ vùng.

Không đồng nhất các chiều đó chỉ vì tất cả có liên quan quốc tế hóa. Người dùng giao diện tiếng Việt vẫn có thể xem số theo en-US và thanh toán EUR; Locale không tự quy đổi tỷ giá hoặc quyết định múi giờ.

### 17.1. Không tự suy effective locale

Khi một formatter fallback, không phải dịch vụ nào cũng cung cấp phương thức đơn giản để đọc lại chính xác dữ liệu locale nào đã được áp dụng. Vì thế log nên có runtime JDK/provider, requested locale, cấu hình app và dữ liệu mẫu liên quan; tránh tự ghi log một “resolved locale” được suy đoán mà chưa có API chứng minh.

## 18. Locale mặc định DISPLAY và FORMAT

Java cung cấp hai loại Locale mặc định quan trọng:

~~~java
Locale display =
        Locale.getDefault(Locale.Category.DISPLAY);
Locale format =
        Locale.getDefault(Locale.Category.FORMAT);
~~~

Đoạn minh họa trong phương thức, cần import Locale.

**DISPLAY** liên quan cách biểu diễn tên ngôn ngữ/vùng, **FORMAT** liên quan định dạng theo ngữ cảnh. Hai giá trị có thể khác nhau tùy môi trường.

Nếu code tạo NumberFormat/DateFormat hoặc gọi Collator mà không truyền locale, kết quả có thể phụ thuộc default JVM. **Không thay Locale.setDefault theo từng request** trên server đa người dùng: đó là cấu hình có phạm vi toàn JVM và dễ gây tác động chéo. Nên truyền Locale tường minh cho mọi thao tác phục vụ user.

## 19. Kiểm thử chất lượng thay vì test số lượng

Một assertion như sau không đáng tin về lâu dài:

~~~java
// Mã minh họa KHÔNG nên dùng:
assert Locale.getAvailableLocales().length == 500;
~~~

Con số là tùy tiện; runtime cập nhật có thể thay danh sách. Test tốt hơn chia thành:

| Test | Mong đợi |
| --- | --- |
| App supported locales | Khớp đúng danh sách sản phẩm chấp thuận |
| Locale.lookup | Chọn locale ưu tiên hoặc fallback của app |
| NumberFormat | Dấu thập phân, nhóm, tiền theo hợp đồng |
| DateFormat/DateTimeFormatter | Kiểu ngày/tháng và tên địa phương mong muốn |
| Collator | Xếp đúng tập tên thực tế |
| BreakIterator | Ngắt đoạn đúng trường hợp trọng yếu |
| ResourceBundle | Đủ bản dịch, fallback không làm lộ sai ngôn ngữ |
| Unicode extensions | Cấu hình số/lịch đúng kỳ vọng |
| Nâng JDK/provider | Phát hiện thay đổi dữ liệu có ý nghĩa |
| RTL/font/accessibility | Không vỡ bố cục hoặc mất khả năng đọc |
| Currency/TimeZone | Không suy từ locale một cách máy móc |

Nếu sản phẩm cần giá trị chuỗi chính xác đến từng code point, phải kiểm soát runtime/provider và chính sách định dạng. Nếu chấp nhận cập nhật CLDR, nên kiểm tra hành vi ở cấp phù hợp thay vì bắt mọi bản JDK luôn trả một snapshot nguyên văn.

## 20. Quy trình chẩn đoán khi hỗ trợ locale không như mong đợi

Nếu vi-VN có trong Locale.getAvailableLocales nhưng danh sách tên tiếng Việt bị sắp không tự nhiên:

1. Xác định **dịch vụ liên quan**: Collator, không phải NumberFormat.
2. Kiểm tra **Collator.getAvailableLocales** và cấu hình provider trên runtime thật.
3. Xác minh code truyền **Locale.forLanguageTag("vi-VN")**, không dùng default ngẫu nhiên.
4. Kiểm tra **strength/decomposition** và comparator tùy chỉnh.
5. Chạy một bộ test từ có **ă, â, đ, ê, ô, ơ, ư**, chữ hoa và dấu thanh.
6. So kết quả với quy chuẩn từ điển mà sản phẩm yêu cầu.
7. Nếu chuyên ngành cần khác rule set mặc định, xác định collation tailoring/versioning riêng.
8. Đánh giá việc nâng JDK hoặc đổi provider nếu các môi trường khác nhau.

Nếu tiền tệ hiển thị sai, chuyển sang kiểm tra NumberFormat, DecimalFormatSymbols và Currency. Nếu từ bị ngắt sai, kiểm tra BreakIterator. **Điều tra theo dịch vụ, không theo một cờ hỗ trợ chung mơ hồ**.

## 21. Các sai lầm thường gặp

### Sai lầm 1: Locale.getAvailableLocales là menu ngôn ngữ app

Không đúng. Nó phản ánh dữ liệu runtime; sản phẩm phải có danh sách supportedLocales riêng dựa trên bản dịch và QA.

### Sai lầm 2: Mọi getAvailableLocales trả cùng tập

Không nên mặc định. Các lớp dịch vụ có loại dữ liệu và provider tương ứng, nên hỏi đúng API.

### Sai lầm 3: Locale.forLanguageTag chứng minh locale được hỗ trợ

Không. Định danh hợp lệ không đồng nghĩa có formatter hoặc bản dịch riêng.

### Sai lầm 4: Factory thành công nghĩa là đã có dữ liệu đặc thù

Không nhất thiết. Fallback có thể cho kết quả hợp lệ theo API nhưng chưa đạt nhu cầu sản phẩm.

### Sai lầm 5: So số lượng thay vì so phần tử

Hai tập có cùng số lượng có thể chứa những locale khác nhau. Cần Set membership, giao/hợp và các test chức năng.

### Sai lầm 6: Dùng NumberFormat locale list để xác nhận Collator

Định dạng số và thứ tự từ điển là hai dịch vụ riêng. Dùng Collator.getAvailableLocales và test tên.

### Sai lầm 7: Suy java.time có danh sách như DateFormat legacy

DateTimeFormatter không có static getAvailableLocales. Kiểm thử formatter hiện đại bằng API thật và dữ liệu thật.

### Sai lầm 8: Nhầm Currency với ngôn ngữ

Currency.getAvailableCurrencies cho danh sách đơn vị tiền, không cho locale UI. Không quy đổi tiền bằng setCurrency.

### Sai lầm 9: ResourceBundle fallback tức là có bản dịch

Base bundle có thể khiến lookup thành công nhưng trả ngôn ngữ khác. Danh sách app phải kiểm soát nội dung dịch.

### Sai lầm 10: Hardcode số lượng locale trong test

Dữ liệu provider/JDK thay đổi. Đo count chỉ để chẩn đoán, không mặc định là contract của Java 17+.

### Sai lầm 11: Exact contains phủ định mọi locale extension

Một tag mở rộng có thể không nằm trong danh sách nhưng formatter vẫn xét một số extension. Phải kiểm tra hành vi tính năng.

### Sai lầm 12: Đổi Locale.setDefault theo request

Cấu hình toàn JVM ảnh hưởng request khác; truyền Locale tường minh.

### Sai lầm 13: Coi JDK/CLDR là bất biến

Dữ liệu locale có thể được cập nhật. Test trên runtime hỗ trợ và thiết kế chiến lược nâng cấp.

### Sai lầm 14: Nhận rằng “hỗ trợ tiếng X” chỉ vì một formatter có dữ liệu

Ứng dụng còn cần bản dịch, hiển thị, font, validation, UX và chính sách nội dung theo ngôn ngữ.

## 22. Bài tập

1. Chạy LocaleServiceCatalog trên JDK 17 và một runtime Java khác đang dùng trong hệ thống; so số lượng nhưng không coi chúng là tiêu chuẩn bất biến.
2. Dùng LocaleMembership với vi-VN, fr-CA và locale thực tế của dự án; so danh sách general/number/collation.
3. Tạo dropdown ngôn ngữ riêng cho một app có hai bản dịch; chứng minh số lượng không tự tăng khi đổi JDK.
4. Với một Locale có Unicode numbering extension, so NumberFormat output với locale không extension trên runtime mục tiêu.
5. So thứ tự tên tiếng Việt bằng String.compareTo và Collator vi-VN; diễn giải vì sao khác.
6. Chạy BreakIterator cho một đoạn có dấu câu và tên riêng; so với phép String.split(" ").
7. Thử ResourceBundle chỉ có base và tiếng Anh; kiểm tra một yêu cầu fr-CA được fallback ra sao.
8. Thử Locale.lookup với ưu tiên không thuộc danh sách app; xác nhận fallback theo chính sách.
9. Khi nâng JDK, chạy lại bộ test về tiền tệ, ngày giờ, collation và phân đoạn; ghi rõ các thay đổi chấp nhận được.
10. Viết tài liệu giải thích requestedLocale, selectedUiLocale, formattingLocale, currency và timeZone của ứng dụng.

## 23. Checklist

- [ ] Hiểu Locale là **định danh**, không phải bản dịch tự động.
- [ ] Phân biệt **Locale.getAvailableLocales** với danh sách của từng dịch vụ.
- [ ] Biết NumberFormat, DateFormat, Collator, BreakIterator có phương thức riêng.
- [ ] Phân biệt DateFormatSymbols và DecimalFormatSymbols với formatter sử dụng chúng.
- [ ] Không nhầm Currency.getAvailableCurrencies với danh sách locale.
- [ ] Không suy DateTimeFormatter có static getAvailableLocales.
- [ ] Hiểu các nguồn CLDR, SPI và cơ chế LocaleServiceProvider.
- [ ] Không khẳng định cùng số locale trên mọi JDK.
- [ ] Xác minh kết quả chức năng, không chỉ exact membership.
- [ ] Có danh sách appSupportedLocales do sản phẩm cam kết.
- [ ] Kiểm tra bản dịch ResourceBundle không fallback sai ngôn ngữ.
- [ ] Dùng Locale.lookup/LanguageRange trên danh sách app được phép.
- [ ] Xác định fallback nếu không tìm thấy ứng viên.
- [ ] Tách requested, UI và formatting locale.
- [ ] Tách Currency và ZoneId khỏi Locale.
- [ ] Không thay Locale.setDefault trong request đồng thời.
- [ ] Kiểm thử extension nếu sản phẩm hỗ trợ.
- [ ] Kiểm tra JDK/provider/CLDR khi nâng runtime.
- [ ] Kiểm tra ngôn ngữ RTL, font và accessibility khi có.
- [ ] Không dùng getAvailableLocales làm giấy chứng nhận cho toàn bộ UX.

## 24. Kết luận

**Locale.getAvailableLocales() không đồng nghĩa locale hỗ trợ của tất cả các dịch vụ.** Nó cho một danh sách chung của môi trường Java. Các dịch vụ **NumberFormat, DateFormat, Collator, BreakIterator, DateFormatSymbols và DecimalFormatSymbols** có danh sách công bố riêng và dữ liệu/provider riêng; việc có trong danh sách hoặc tạo factory thành công cũng không thay thế kiểm thử kết quả, vì có thể xảy ra fallback.

Trong Java 17+, hãy dùng **đúng API của dịch vụ cần hỏi**, kiểm tra chức năng trên JDK/provider thật và quản lý **appSupportedLocales** như một quyết định sản phẩm độc lập. Dùng Locale.LanguageRange và Locale.lookup để lựa chọn ngôn ngữ từ danh sách ứng dụng đã dịch; tách Locale khỏi Currency/TimeZone; kiểm soát fallback và tránh thay Locale default toàn JVM trong request. Cách làm này giúp ứng dụng tận dụng dữ liệu locale phong phú của JDK mà không tuyên bố nhầm các bản dịch và tính năng chưa được kiểm thử.
