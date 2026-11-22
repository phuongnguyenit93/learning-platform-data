# Kiểm thử locale không được hỗ trợ và khác biệt tên vùng trong Java

## 1. Mục tiêu và phạm vi

Trong ứng dụng đa ngôn ngữ, một Locale như fr-CA, en-US hoặc zh-Hant-TW mô tả lựa chọn ngôn ngữ, script và vùng của người dùng. Tuy nhiên, việc **tạo được một đối tượng Locale không chứng minh runtime, một API cụ thể hoặc ứng dụng có đủ dữ liệu cho locale đó**. Java có thể fallback sang locale cha hoặc dữ liệu mặc định; kết quả hiển thị tên quốc gia, ngày tháng và số có thể thay đổi theo locale, data provider và phiên bản JDK.

Bài thuộc chủ đề **Ngôn ngữ và locale** và tập trung vào hai yêu cầu:

- **Kiểm thử ngôn ngữ/locale không được hỗ trợ:** phân biệt language tag sai cú pháp, tag đúng cú pháp nhưng chưa có dữ liệu, locale không được một dịch vụ cụ thể hỗ trợ và locale ứng dụng không có bản dịch.
- **Kiểm thử khác biệt tên vùng:** phân biệt vùng đang được mô tả với ngôn ngữ dùng để hiển thị tên vùng; kiểm tra tên quốc gia, định dạng số và tác động của default locale.

Các API được dùng là java.util.Locale, Locale.Builder, Locale.LanguageRange, NumberFormat, DateFormat, LocaleServiceProvider và các API locale-sensitive hiện hành. Những API này vẫn được duy trì trong JDK hiện đại. Bài tập trung vào các locale data provider hiện hành: CLDR, HOST và SPI. Các chương trình độc lập được biên dịch bằng **javac --release 17**; kết quả stdout ghi rõ đã kiểm thử trên **OpenJDK 24.0.2**.

Sau bài học, bạn có thể:

1. Phân biệt locale identifier, well-formed language tag, locale được đăng ký và locale có dữ liệu hỗ trợ.
2. Kiểm tra danh sách locale toàn runtime và danh sách locale riêng của NumberFormat/DateFormat.
3. Giải thích candidate locale fallback khi dịch vụ không có dữ liệu đúng locale.
4. Viết test cho một locale có cú pháp hợp lệ nhưng không được runtime hỗ trợ.
5. Hiểu Locale.getDisplayCountry(displayLocale) và lý do cùng một vùng có tên khác nhau theo ngôn ngữ hiển thị.
6. Kiểm thử định dạng số theo vùng, như dấu thập phân và phân nhóm hàng nghìn.
7. Phân biệt Locale.Category.DISPLAY với Locale.Category.FORMAT.
8. Xác thực language tag bằng Locale.Builder và thương lượng locale bằng Locale.lookup.
9. Xử lý dữ liệu CLDR/provider thay đổi giữa JDK mà không tạo test brittle.
10. Thiết kế fallback, resource bundle, allowlist locale và kiểm thử tích hợp đáng tin cậy.

## 2. Locale là định danh, không phải gói dữ liệu dịch

Một Locale là đối tượng định danh một tổ hợp thông tin văn hóa/địa lý. Nó có thể gồm:

- **Language**: ngôn ngữ, ví dụ en, fr, vi.
- **Script**: hệ chữ viết, ví dụ Latn, Hant, Cyrl.
- **Region**: vùng/quốc gia, ví dụ US, CA, TW, hoặc mã khu vực số.
- **Variant**: biến thể bổ sung trong các trường hợp đặc biệt.
- **Extensions**: mở rộng BCP 47, ví dụ Unicode extension để chọn calendar hoặc numbering system.

Ví dụ tag zh-Hant-TW-u-nu-hanidec có thể được hiểu là tiếng Trung, chữ phồn thể, vùng Đài Loan, với extension chọn kiểu chữ số Han decimal.

~~~text
zh-Hant-TW-u-nu-hanidec
|  |    |  |
|  |    |  +-- Unicode locale extension: numbering system
|  |    +----- Region
|  +---------- Script
+------------- Language
~~~

**Locale không chứa sẵn mọi bản dịch, tên vùng hoặc quy tắc định dạng.** Những dữ liệu đó đến từ runtime locale data hoặc các LocaleServiceProvider đã được triển khai. Vì vậy, cùng một Locale có thể được một dịch vụ hỗ trợ nhưng một dịch vụ khác chỉ fallback; hoặc được JDK hỗ trợ nhưng ứng dụng không có resource bundle tương ứng.

### Bốn khái niệm không được đánh đồng

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Well-formed tag | Chuỗi có đúng cú pháp language tag không? | fr-CA |
| Registered subtag | Các mã có trong registry tương ứng không? | Kiểm tra theo BCP 47/IANA |
| Runtime/service support | JDK có dữ liệu cho API cụ thể không? | NumberFormat.getAvailableLocales() |
| Application support | Sản phẩm có bản dịch và quy trình cho ngôn ngữ đó không? | Resource bundle messages_fr_CA |

Một chuỗi có thể **well-formed nhưng không registered hoặc không có locale data**. Và runtime có thể format số cho locale nhưng ứng dụng vẫn không có bản dịch giao diện cho ngôn ngữ ấy.

### Vì sao phân biệt này quan trọng?

Nếu code chỉ làm:

~~~java
Locale locale = Locale.forLanguageTag(userInput);
return showPage(locale);
~~~

thì chưa đủ để kết luận người dùng có thể sử dụng sản phẩm bằng ngôn ngữ đó. Cần validate tag, chọn locale được sản phẩm hỗ trợ, xác định fallback và kiểm tra từng dịch vụ locale-sensitive cần dùng.

## 3. BCP 47: cú pháp, canonical form và validation

Java Locale triển khai language tag theo BCP 47. Các thành phần được canonicalize theo quy ước: language thường viết thường, script viết hoa chữ đầu, region viết hoa; extension key/value thường viết thường. Dùng toLanguageTag() để tạo biểu diễn language tag chuẩn.

~~~java
// Mảnh mã: tạo Locale từ một BCP 47 language tag.
Locale locale = new Locale.Builder()
        .setLanguageTag("zh-Hant-TW-u-nu-hanidec")
        .build();

System.out.println(locale.toLanguageTag());
~~~

### Locale.forLanguageTag và Locale.Builder khác nhau

- **Locale.forLanguageTag(String)** có hành vi dung thứ hơn: khi gặp phần language tag sai cú pháp, phương thức bỏ phần không hợp lệ và các phần theo sau theo quy tắc API, rồi trả về Locale từ phần hợp lệ trước đó.
- **new Locale.Builder().setLanguageTag(tag).build()** kiểm tra tag well-formed; nếu tag sai cú pháp, ném IllformedLocaleException.
- Locale.Builder kiểm tra **cú pháp từng trường**, không xác minh toàn bộ giá trị có được đăng ký trong IANA registry hay có dữ liệu trong JDK.
- Với mã mới, ưu tiên Locale.forLanguageTag hoặc Locale.Builder để thể hiện rõ language tag và validation policy.

Nếu đầu vào từ HTTP Accept-Language, file cấu hình hoặc user profile cần validation chặt, Locale.Builder phù hợp hơn việc âm thầm chấp nhận một tag bị cắt cụt. Sau đó vẫn cần kiểm tra allowlist locale của sản phẩm.

### Ví dụ về tag sai cú pháp

en_US dùng dấu gạch dưới, không phải cú pháp BCP 47 chuẩn. Dùng Locale.Builder.setLanguageTag("en_US") sẽ ném IllformedLocaleException. Còn việc tạo Locale từ các trường riêng lẻ chỉ kiểm tra theo quy tắc tương ứng của API, không biến mã tùy ý thành locale có dữ liệu.

**Không tự thay dấu gạch dưới bằng dấu gạch ngang cho mọi đầu vào không tin cậy** rồi coi là hợp lệ; nếu sản phẩm có dữ liệu lịch sử cần migration, hãy thực hiện migration có chủ đích và test các alias được cho phép.
## 4. Well-formed không đồng nghĩa được hỗ trợ

Để kiểm thử locale không được hỗ trợ, trước tiên cần xác định **hỗ trợ ở tầng nào**.

### Locale toàn runtime

Locale.getAvailableLocales() trả tập hợp các locale được Java runtime và các LocaleServiceProvider đã triển khai hỗ trợ. Tập này có ít nhất Locale.ROOT và Locale.US. Không dựa vào thứ tự mảng trả về vì thứ tự không phải hợp đồng.

### Locale của từng dịch vụ

Mỗi API locale-sensitive có thể cung cấp danh sách riêng. Ví dụ:

~~~java
Locale[] runtimeLocales = Locale.getAvailableLocales();
Locale[] numberLocales = NumberFormat.getAvailableLocales();
Locale[] dateLocales = DateFormat.getAvailableLocales();
~~~

NumberFormat.getAvailableLocales() mô tả locale mà các factory NumberFormat có thể tạo instance localized. DateFormat.getAvailableLocales() mô tả phạm vi tương ứng của DateFormat. **Không dùng danh sách của NumberFormat để kết luận DateFormat, Collator hay ResourceBundle cũng hỗ trợ cùng tập locale.**

### Locale không có trong danh sách có chắc chắn ném exception không?

Không. Một factory như NumberFormat.getNumberInstance(locale) có thể tìm **candidate locale cha** nếu locale yêu cầu không được hỗ trợ, rồi dùng dữ liệu của candidate phù hợp. Khi không có dữ liệu riêng cho vùng, formatter có thể dùng dữ liệu language-level hoặc root-level. Do đó, một locale well-formed không nằm trong NumberFormat.getAvailableLocales() vẫn có thể tạo ra NumberFormat thành công.

Đây là hành vi fallback có chủ đích, không phải bằng chứng dịch vụ có dữ liệu chính xác cho locale yêu cầu.

### Phải kiểm tra danh sách nào?

| Mục tiêu kiểm thử | Nguồn kiểm tra |
|---|---|
| Locale có trong tập runtime hay không | Locale.getAvailableLocales() |
| Number formatting có locale data hay không | NumberFormat.getAvailableLocales() |
| Date formatting có locale data hay không | DateFormat.getAvailableLocales() |
| Collation/sắp xếp có hỗ trợ hay không | Collator.getAvailableLocales() |
| Ngôn ngữ giao diện sản phẩm có bản dịch hay không | Allowlist của ứng dụng/resource bundles |
| Có provider riêng hỗ trợ hay không | LocaleServiceProvider tương ứng |

**Không dùng Locale.getAvailableLocales() làm allowlist ngôn ngữ sản phẩm.** Runtime có thể có locale data mà sản phẩm chưa dịch; ngược lại, ứng dụng có thể tự cung cấp resource cho locale mà một formatter của JDK không có dữ liệu riêng.

## 5. Candidate locale fallback khi không có dữ liệu chính xác

Khi một locale-sensitive service không tìm thấy dữ liệu cho locale yêu cầu, Java kiểm tra các locale ứng viên theo quan hệ cha. Ví dụ một yêu cầu theo vùng có thể thử lần lượt vùng, language và root. Cơ chế chính xác tuân theo candidate-locale algorithm được định nghĩa cho locale services và ResourceBundle.

~~~text
Yêu cầu: fr-CA
       |
       v
Có dữ liệu fr-CA?
   | Có       | Không
   v           v
Dùng fr-CA    Có dữ liệu fr?
                 | Có       | Không
                 v           v
               Dùng fr     Dùng ROOT nếu dịch vụ hỗ trợ
~~~

Ví dụ: nếu một dịch vụ không có dữ liệu cho fr-CA nhưng có cho fr, nó có thể dùng dữ liệu của fr. Việc formatter nhận đối số Locale gốc vẫn có ý nghĩa: service có thể giữ extension của Locale được yêu cầu trong quá trình tạo object, dù dữ liệu cơ sở được lấy từ candidate locale cha.

### Fallback không đồng nghĩa sửa lại Locale của ứng dụng

Giả sử yêu cầu là zz-ZZ, formatter fallback sang ROOT. Điều đó không có nghĩa đối tượng Locale ban đầu đã trở thành Locale.ROOT, và cũng không có nghĩa ứng dụng có bản dịch zz-ZZ. Hãy ghi nhận rõ ba giá trị trong log/test:

- **requestedLocale**: locale người dùng yêu cầu.
- **resolved/applicationLocale**: locale sản phẩm quyết định dùng sau negotiation/fallback.
- **serviceLocaleData**: locale data/provider mà API cụ thể có thể dùng để cung cấp kết quả.

Không phải mọi API đều expose trực tiếp serviceLocaleData đã chọn. Khi không có cách quan sát chính xác, test contract đầu ra và ghi nhận requested/application locale thay vì tự suy luận implementation.

## 6. Ví dụ Java hoàn chỉnh 1 — locale đúng cú pháp nhưng không được hỗ trợ

Tạo file **UnsupportedLocaleFallbackDemo.java**:

~~~java
import java.text.NumberFormat;
import java.util.Arrays;
import java.util.Locale;

public class UnsupportedLocaleFallbackDemo {
    public static void main(String[] args) {
        Locale unsupported = new Locale.Builder()
                .setLanguage("zz").setRegion("ZZ").build();
        boolean runtimeLists = Arrays.asList(Locale.getAvailableLocales())
                .contains(unsupported);
        boolean numberLists = Arrays.asList(NumberFormat.getAvailableLocales())
                .contains(unsupported);
        String actual = NumberFormat.getNumberInstance(unsupported)
                .format(12345.67);
        String root = NumberFormat.getNumberInstance(Locale.ROOT)
                .format(12345.67);
        System.out.println("requested=" + unsupported.toLanguageTag());
        System.out.println("runtimeLists=" + runtimeLists);
        System.out.println("numberFormatLists=" + numberLists);
        System.out.println("formatted=" + actual);
        System.out.println("sameAsRoot=" + actual.equals(root));
    }
}
~~~

Chạy:

~~~text
javac --release 17 UnsupportedLocaleFallbackDemo.java
java UnsupportedLocaleFallbackDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
requested=zz-ZZ
runtimeLists=false
numberFormatLists=false
formatted=12,345.67
sameAsRoot=true
~~~

**Giải thích:**

1. Locale.Builder tạo được locale theo cú pháp trường language/region. Điều này chỉ xác nhận cú pháp, không xác nhận locale có trong registry hay data provider.
2. zz-ZZ không xuất hiện trong tập locale runtime hoặc tập locale NumberFormat ở môi trường kiểm thử.
3. NumberFormat.getNumberInstance(unsupported) vẫn tạo được formatter.
4. Kết quả format bằng kết quả NumberFormat cho Locale.ROOT trong runtime này, thể hiện fallback.
5. Không nên khẳng định mọi locale không hỗ trợ đều luôn cho đúng chuỗi 12,345.67; dữ liệu root và provider có thể thay đổi theo runtime.
6. Bài test xác nhận hai điều độc lập: **locale không được liệt kê** và **factory vẫn fallback thay vì ném lỗi**.

**Ý nghĩa trong production:** Nếu sản phẩm muốn từ chối locale không được hỗ trợ, phải kiểm tra allowlist của ứng dụng và trả thông báo rõ ràng trước khi format. Đừng chờ NumberFormat ném exception để phát hiện ngôn ngữ không được hỗ trợ.

## 7. Tên vùng: locale được mô tả và locale hiển thị là hai tham số khác nhau

Một trường hợp dễ gây nhầm lẫn là tên quốc gia. Ví dụ muốn hiển thị tên vùng của Locale.US bằng tiếng Pháp, ta viết:

~~~java
String name = Locale.US.getDisplayCountry(Locale.FRENCH);
~~~

Ở đây:

- Locale.US là **locale được mô tả**: ngôn ngữ English, vùng United States.
- Locale.FRENCH là **display locale**: ngôn ngữ dùng để diễn đạt tên vùng.
- Kết quả là tên quốc gia bằng tiếng Pháp.

Các phương thức liên quan:

- getDisplayLanguage(displayLocale): tên ngôn ngữ theo ngôn ngữ hiển thị.
- getDisplayScript(displayLocale): tên hệ chữ viết theo ngôn ngữ hiển thị.
- getDisplayCountry(displayLocale): tên vùng/quốc gia theo ngôn ngữ hiển thị.
- getDisplayName(displayLocale): tên đầy đủ của locale theo ngôn ngữ hiển thị.

**Đừng nhầm display locale với region của locale gốc.** Nếu muốn tên vùng không phụ thuộc máy đang chạy, truyền displayLocale tường minh. Phương thức không tham số sử dụng default DISPLAY locale, nên cùng code có thể hiển thị tên khác nhau giữa hai máy.

### Vùng không được nhận diện hoặc không có tên bản địa hóa

Một region code có thể đúng cú pháp nhưng không có tên trong data provider. Kết quả hiển thị có thể là fallback như "Unknown Region" hoặc mã/nhãn theo data provider. Không dùng một chuỗi fallback làm logic xác thực vùng; hãy validate region theo đặc tả và policy của ứng dụng.

## 8. Ví dụ Java hoàn chỉnh 2 — tên một vùng theo nhiều ngôn ngữ hiển thị

Tạo file **RegionalDisplayNamesDemo.java**:

~~~java
import java.util.Locale;

public class RegionalDisplayNamesDemo {
    public static void main(String[] args) {
        Locale us = Locale.US;
        Locale unknown = new Locale.Builder()
                .setLanguage("en").setRegion("ZZ").build();
        System.out.println("regionTag=" + us.toLanguageTag());
        System.out.println("english=" + us.getDisplayCountry(Locale.ENGLISH));
        System.out.println("french=" + us.getDisplayCountry(Locale.FRENCH));
        System.out.println("japanese=" + us.getDisplayCountry(Locale.JAPANESE));
        System.out.println("unknownRegion="
                + unknown.getDisplayCountry(Locale.ENGLISH));
    }
}
~~~

Chạy:

~~~text
javac --release 17 RegionalDisplayNamesDemo.java
java RegionalDisplayNamesDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
regionTag=en-US
english=United States
french=États-Unis
japanese=アメリカ合衆国
unknownRegion=Unknown Region
~~~

**Phân tích:**

- regionTag cho biết locale đang được mô tả là en-US.
- english, french và japanese là ba cách hiển thị tên cùng một vùng theo ba display locale.
- Locale.US không đổi; chỉ đối số displayLocale thay đổi.
- Region ZZ trong ví dụ cho ra Unknown Region trên bộ locale data của runtime đã kiểm thử. Đây là kết quả dữ liệu, không phải thông báo lỗi xác thực.
- Tên hiển thị có thể đổi theo phiên bản CLDR/JDK. Nếu test snapshot chuỗi chính xác, phải pin runtime/provider; nếu không, nên kiểm tra hành vi và đặc tính cần thiết thay vì hardcode tên bản địa hóa toàn cầu.

### Tại sao không so sánh getDisplayCountry() không tham số trong test?

Vì phương thức đó phụ thuộc default DISPLAY locale. Một máy developer dùng English, một máy CI dùng French hoặc Japanese có thể cho output khác nhau dù code giống hệt. Truyền Locale.ENGLISH hoặc display locale mong muốn sẽ làm test rõ ràng và có thể tái lập hơn.

## 9. Khác biệt tên vùng không chỉ là tên quốc gia

Cùng một language, thay region có thể làm thay đổi:

- Quy tắc phân nhóm hàng nghìn và dấu thập phân.
- Mẫu ngày tháng và thứ tự ngày/tháng/năm.
- Đồng tiền mặc định và cách hiển thị symbol.
- Quy tắc số nhiều, tên tháng, ngày trong tuần và một số nhãn văn hóa.
- Calendar, numbering system và các Unicode locale extension nếu dịch vụ hỗ trợ.

Ví dụ NumberFormat cho số 12.345,67 có thể dùng dấu phân nhóm và dấu thập phân khác nhau:

| Locale | Kết quả minh họa | Dấu phân nhóm | Dấu thập phân |
|---|---|---|---|
| en-US | 12,345.67 | , | . |
| de-DE | 12.345,67 | . | , |
| fr-FR | 12 345,67 | narrow no-break space | , |

Trong chuỗi của French, dấu phân nhóm có thể là **U+202F NARROW NO-BREAK SPACE**, không phải dấu cách ASCII. Không viết test chỉ bằng cách nhìn chuỗi trên màn hình; khi cần, kiểm tra code point hoặc NumberFormatSymbols.

### Đừng suy luận currency chỉ từ tên vùng

NumberFormat.getCurrencyInstance(locale) dùng currency data gắn với locale. Nhưng currency có thể thay đổi theo thời gian và data provider; một locale không phải là nguồn dữ liệu kế toán. Nếu nghiệp vụ có currency code rõ ràng, dùng Currency.getInstance("USD") hoặc mã tiền tệ từ dữ liệu nghiệp vụ, rồi định dạng theo display locale khi phù hợp. Đừng để default currency của máy quyết định giá trị giao dịch.

### Định dạng hiển thị không phải định dạng lưu trữ

- Số dùng cho API/database nên có schema và quy ước machine-readable rõ ràng.
- Ngày/giờ lưu trữ nên dùng kiểu thời gian và timezone phù hợp, không lưu chuỗi ngày tháng localized làm nguồn dữ liệu chính.
- Chỉ format khi trình bày cho người dùng; khi parse input người dùng, truyền locale rõ và kiểm tra strictness/range theo yêu cầu.

## 10. Ví dụ Java hoàn chỉnh 3 — cùng số, khác định dạng theo vùng

Tạo file **RegionNumberFormatDemo.java**:

~~~java
import java.text.NumberFormat;
import java.util.Locale;

public class RegionNumberFormatDemo {
    public static void main(String[] args) {
        double amount = 12345.67;
        System.out.println("us="
                + NumberFormat.getNumberInstance(Locale.US).format(amount));
        System.out.println("germany="
                + NumberFormat.getNumberInstance(Locale.GERMANY).format(amount));
        System.out.println("france="
                + NumberFormat.getNumberInstance(Locale.FRANCE).format(amount));
    }
}
~~~

Chạy:

~~~text
javac --release 17 RegionNumberFormatDemo.java
java RegionNumberFormatDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
us=12,345.67
germany=12.345,67
france=12 345,67
~~~

Trong dòng france, giữa 12 và 345 là **U+202F**, một khoảng trắng hẹp không ngắt dòng. Đây là chi tiết có ý nghĩa khi kiểm thử chuỗi localized: một dấu cách thông thường và narrow no-break space nhìn khá giống nhưng không bằng nhau.

**Test nên làm gì?**

- Truyền locale tường minh, không dùng default khi muốn kiểm tra quy tắc của một vùng.
- Kiểm tra dấu phân nhóm và dấu thập phân bằng NumberFormatSymbols khi cần.
- Tránh so sánh chuỗi nếu test chạy trên nhiều JDK/provider và mục tiêu không phải kiểm tra snapshot CLDR.
- Nếu sản phẩm phải hiển thị đúng một định dạng đã được phê duyệt, pin data/runtime hoặc áp dụng formatter và pattern theo yêu cầu sản phẩm, không hy vọng mọi CLDR version trả đúng một chuỗi vĩnh viễn.

## 11. Ví dụ Java hoàn chỉnh 4 — kiểm tra language tag và Unicode extension

Tạo file **LocaleTagValidationDemo.java**:

~~~java
import java.util.IllformedLocaleException;
import java.util.Locale;

public class LocaleTagValidationDemo {
    public static void main(String[] args) {
        Locale locale = new Locale.Builder()
                .setLanguageTag("zh-Hant-TW-u-nu-hanidec").build();
        System.out.println("tag=" + locale.toLanguageTag());
        System.out.println("language=" + locale.getLanguage());
        System.out.println("script=" + locale.getScript());
        System.out.println("region=" + locale.getCountry());
        System.out.println("numbering=" + locale.getUnicodeLocaleType("nu"));
        try {
            new Locale.Builder().setLanguageTag("en_US");
        } catch (IllformedLocaleException expected) {
            System.out.println("badTag=IllformedLocaleException");
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 LocaleTagValidationDemo.java
java LocaleTagValidationDemo
~~~

Stdout:

~~~text
tag=zh-Hant-TW-u-nu-hanidec
language=zh
script=Hant
region=TW
numbering=hanidec
badTag=IllformedLocaleException
~~~

**Giải thích:**

1. setLanguageTag nhận BCP 47 tag với language, script, region và Unicode extension.
2. toLanguageTag trả lại biểu diễn canonical.
3. getUnicodeLocaleType("nu") đọc numbering-system extension.
4. en_US không phải language tag BCP 47 well-formed, nên Builder ném IllformedLocaleException.
5. Ví dụ chỉ xác nhận cú pháp tag và cách đọc field. Nó không khẳng định locale zh-Hant-TW hoặc numbering system cụ thể có đầy đủ mọi service data trong mọi JDK.

### Extension không được mọi dịch vụ hỗ trợ như nhau

Unicode locale extension có thể yêu cầu calendar, numbering system, collation hoặc currency format. Locale.Builder có thể giữ extension hợp lệ về cú pháp; một dịch vụ có thể áp dụng, bỏ qua hoặc fallback nếu extension không được hỗ trợ. Vì vậy hãy test **đầu ra của đúng dịch vụ** chứ không chỉ kiểm tra Locale có extension.

## 12. Thương lượng locale theo danh sách sản phẩm hỗ trợ

Ứng dụng thường nhận danh sách ưu tiên từ header Accept-Language hoặc cấu hình người dùng. Không nên chỉ lấy ngôn ngữ đầu tiên rồi giả định sản phẩm hỗ trợ. Hãy so khớp danh sách yêu cầu với **supported locales của ứng dụng**.

Java cung cấp:

- **Locale.LanguageRange.parse(String)**: phân tích danh sách language range và trọng số q.
- **Locale.lookup(priorityList, locales)**: tìm locale phù hợp nhất theo lookup matching của RFC 4647.
- **Locale.filter(priorityList, locales)**: trả các locale phù hợp theo filtering.
- Nếu lookup không tìm được locale nào, nó trả **null**; ứng dụng cần fallback rõ ràng, ví dụ locale mặc định được cấu hình hoặc trang thông báo không hỗ trợ.

~~~java
// Mảnh mã.
List<Locale> supported = List.of(
        Locale.forLanguageTag("fr-CA"),
        Locale.FRANCE,
        Locale.US
);
List<Locale.LanguageRange> requested =
        Locale.LanguageRange.parse("fr-CA,fr;q=0.9,en;q=0.8");
Locale selected = Locale.lookup(requested, supported);
~~~

Kết quả lookup được chọn từ **danh sách supported do ứng dụng cung cấp**. Nó không tự tra tất cả locale của JDK, không tải bản dịch và không chứng minh một NumberFormatProvider cụ thể có dữ liệu.
## 13. Ví dụ Java hoàn chỉnh 5 — thương lượng theo Accept-Language

Tạo file **LocaleNegotiationDemo.java**:

~~~java
import java.util.List;
import java.util.Locale;

public class LocaleNegotiationDemo {
    public static void main(String[] args) {
        List<Locale> supported = List.of(
                Locale.forLanguageTag("fr-CA"),
                Locale.FRANCE,
                Locale.US
        );
        List<Locale.LanguageRange> requested =
                Locale.LanguageRange.parse("fr-CA,fr;q=0.9,en;q=0.8");
        Locale selected = Locale.lookup(requested, supported);
        Locale noMatch = Locale.lookup(
                Locale.LanguageRange.parse("ja-JP"),
                List.of(Locale.US, Locale.FRANCE));
        System.out.println("selected="
                + (selected == null ? "none" : selected.toLanguageTag()));
        System.out.println("noMatch="
                + (noMatch == null ? "none" : noMatch.toLanguageTag()));
    }
}
~~~

Chạy:

~~~text
javac --release 17 LocaleNegotiationDemo.java
java LocaleNegotiationDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
selected=fr-CA
noMatch=none
~~~

**Giải thích:**

- Danh sách supported là ba locale ứng dụng đã quyết định có thể phục vụ.
- Accept-Language yêu cầu fr-CA trước, sau đó fr và en với quality khác nhau.
- lookup chọn fr-CA từ danh sách được hỗ trợ.
- Khi chỉ yêu cầu ja-JP mà ứng dụng chỉ có en-US và fr-FR, lookup trả null; code không giả định tự động có một bản dịch Japanese.
- Nếu ứng dụng muốn fallback sang locale mặc định, hãy viết policy rõ sau lookup và ghi nhận cả requestedLocale lẫn selectedLocale.

### Lookup và fallback dịch vụ khác nhau

Locale.lookup là **language negotiation theo danh sách ưu tiên của client**. Candidate locale fallback của NumberFormat/DateFormat là **cơ chế tìm data provider khi một dịch vụ không hỗ trợ locale đã được yêu cầu**. Hai quy trình có mục tiêu khác nhau và không thay thế nhau.

## 14. Default locale có hai category quan trọng

Java có hai default locale category:

- **Locale.Category.FORMAT**: dùng bởi các API format số, ngày, giờ, tiền tệ khi caller không truyền Locale.
- **Locale.Category.DISPLAY**: dùng cho tên hiển thị ngôn ngữ, quốc gia, script và tên locale khi caller không truyền display locale.

Ví dụ:

~~~java
NumberFormat implicit = NumberFormat.getInstance();
String name = Locale.US.getDisplayCountry();
~~~

Hai kết quả trên có thể phụ thuộc hai default category khác nhau. Vì vậy một máy có thể format số theo Germany nhưng hiển thị tên vùng theo French nếu default FORMAT là de-DE và default DISPLAY là fr.

### Truyền Locale tường minh vẫn là cách tốt nhất

Trong ứng dụng đa tenant hoặc server xử lý nhiều người dùng đồng thời, không đổi global default theo từng request. Nếu request A đặt default French trong lúc request B cần German, cả hai có thể tác động lẫn nhau vì default locale là trạng thái toàn JVM.

Ưu tiên:

~~~java
NumberFormat format = NumberFormat.getInstance(requestLocale);
String country = Locale.US.getDisplayCountry(displayLocale);
~~~

Nếu một bài test cần chứng minh hành vi của default category, đổi trong **một JVM test riêng**, lưu giá trị cũ và khôi phục trong finally. Không chạy test thay đổi default locale song song với test khác đang phụ thuộc default.

## 15. Ví dụ Java hoàn chỉnh 6 — FORMAT và DISPLAY không phải một

Tạo file **LocaleCategoryDemo.java**:

~~~java
import java.text.NumberFormat;
import java.util.Locale;

public class LocaleCategoryDemo {
    public static void main(String[] args) {
        Locale oldFormat = Locale.getDefault(Locale.Category.FORMAT);
        Locale oldDisplay = Locale.getDefault(Locale.Category.DISPLAY);
        try {
            Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);
            Locale.setDefault(Locale.Category.DISPLAY, Locale.FRENCH);
            System.out.println("defaultFormat="
                    + Locale.getDefault(Locale.Category.FORMAT).toLanguageTag());
            System.out.println("implicit="
                    + NumberFormat.getInstance().format(12345.67));
            System.out.println("explicitUS="
                    + NumberFormat.getInstance(Locale.US).format(12345.67));
            System.out.println("defaultDisplay="
                    + Locale.getDefault(Locale.Category.DISPLAY).toLanguageTag());
            System.out.println("displayName=" + Locale.US.getDisplayCountry());
        } finally {
            Locale.setDefault(Locale.Category.FORMAT, oldFormat);
            Locale.setDefault(Locale.Category.DISPLAY, oldDisplay);
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 LocaleCategoryDemo.java
java LocaleCategoryDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
defaultFormat=de-DE
implicit=12.345,67
explicitUS=12,345.67
defaultDisplay=fr
displayName=États-Unis
~~~

**Giải thích:**

1. Chương trình lưu hai default category ban đầu để không để lại trạng thái toàn JVM sau test.
2. NumberFormat.getInstance() không truyền locale nên dùng FORMAT default de-DE.
3. NumberFormat.getInstance(Locale.US) bỏ qua default và format theo US.
4. Locale.US.getDisplayCountry() không truyền display locale nên dùng DISPLAY default French.
5. finally khôi phục cả hai giá trị dù phần test thành công hay ném exception.

**Không đưa Locale.setDefault vào code xử lý request.** Đây là cấu hình toàn JVM, không phải một biến theo từng người dùng. Nếu ứng dụng phục vụ nhiều locale, truyền Locale vào từng formatter/renderer.

## 16. Case conversion cũng có khác biệt theo ngôn ngữ

Một ví dụ nổi tiếng là chữ I trong tiếng Thổ Nhĩ Kỳ. Chuyển đổi chữ hoa/thường theo locale có thể khác quy tắc không phụ thuộc ngôn ngữ:

Mảnh mã:

~~~java
String value = "TITLE";
String root = value.toLowerCase(Locale.ROOT);
String turkish = value.toLowerCase(Locale.forLanguageTag("tr"));
~~~

Trong Turkish, chữ I hoa có thể chuyển thành ı (LATIN SMALL LETTER DOTLESS I). Đây là hành vi đúng theo ngôn ngữ, nhưng có thể làm sai việc chuẩn hóa identifier/protocol token nếu lập trình viên dùng default locale.

**Quy tắc thực tế:**

- Văn bản dành cho người đọc: chuyển case theo locale phù hợp khi nghiệp vụ yêu cầu.
- Tên field, HTTP header, token ASCII hoặc identifier kỹ thuật: dùng quy tắc không phụ thuộc locale, thường là Locale.ROOT hoặc phép so sánh ASCII/Unicode được giao thức quy định.
- Không dùng String.toLowerCase() không tham số để chuẩn hóa key giao thức trên server có default locale tùy môi trường.

## 17. Ứng dụng không hỗ trợ ngôn ngữ: resource bundle là một lớp riêng

Locale data của JDK và bản dịch giao diện là hai nguồn khác nhau. Ví dụ NumberFormat có thể format cho fr-CA bằng cách fallback sang fr, nhưng ứng dụng vẫn có thể thiếu messages_fr_CA và messages_fr.

Với ResourceBundle, ứng dụng cần xác định:

- Base bundle hoặc resource mặc định.
- Các locale bundle thật sự được đóng gói.
- Candidate locale chain cho yêu cầu cụ thể.
- Chính sách fallback về locale mặc định hoặc base bundle.
- Hành vi khi thiếu key, thiếu bundle hoặc bundle không đọc được.

Ví dụ khái niệm:

~~~java
Locale requested = Locale.forLanguageTag("fr-CA");
ResourceBundle messages =
        ResourceBundle.getBundle("i18n.Messages", requested);
Locale bundleLocale = messages.getLocale();
String title = messages.getString("page.title");
~~~

messages.getLocale() cho biết locale của bundle đã được nạp. Nó có thể khác requested nếu quá trình lookup dùng bundle cha/fallback. Đây là thông tin hữu ích để log và test.

**Lưu ý:** ResourceBundle có candidate search và default-locale fallback riêng; đừng suy ra kết quả bundle chỉ từ NumberFormat.getAvailableLocales(). Nếu sản phẩm không muốn tự động fallback sang ngôn ngữ máy, cần cấu hình resource lookup/policy phù hợp và test riêng đường fallback đó.

### Test resource fallback bằng bộ fixture nhỏ

Một bộ test tốt có thể chuẩn bị:

- Base bundle chứa key bắt buộc.
- Bundle cho fr.
- Bundle cho fr-CA.
- Một locale không có bundle.
- Một key bị thiếu trong bundle con nhưng có ở bundle cha.

Kiểm tra bundle locale được chọn và giá trị key thực tế. Đừng chỉ kiểm tra bundle không ném MissingResourceException; một bundle cha có thể được tải thành công nhưng nội dung khác với ngôn ngữ người dùng yêu cầu.

## 18. Ví dụ Java hoàn chỉnh 7 — locale-sensitive case conversion

Tạo file **TurkishCaseDemo.java**:

~~~java
import java.util.Locale;

public class TurkishCaseDemo {
    public static void main(String[] args) {
        String value = "TITLE";
        System.out.println("root=" + value.toLowerCase(Locale.ROOT));
        System.out.println("turkish="
                + value.toLowerCase(Locale.forLanguageTag("tr")));
    }
}
~~~

Chạy:

~~~text
javac --release 17 TurkishCaseDemo.java
java TurkishCaseDemo
~~~

Stdout trên OpenJDK 24.0.2:

~~~text
root=title
turkish=tıtle
~~~

Trong kết quả Turkish, ký tự i ở giữa là **U+0131 LATIN SMALL LETTER DOTLESS I**. Đây là một ví dụ cho thấy locale không chỉ ảnh hưởng tên quốc gia hoặc dấu phân nhóm số; nó còn có thể thay đổi quy tắc ngôn ngữ của thao tác văn bản.

**Quy tắc kiểm thử:** Nếu xử lý identifier, tên protocol hoặc key kỹ thuật, test bằng Locale.ROOT để tránh kết quả phụ thuộc default locale. Nếu xử lý văn bản ngôn ngữ tự nhiên, test theo locale thực tế mà sản phẩm hỗ trợ.

## 19. Locale data providers và LocaleServiceProvider

Java nhận locale data từ runtime hoặc provider được triển khai. Trong JDK hiện đại, các provider chính gồm:

| Provider | Vai trò |
|---|---|
| CLDR | Dữ liệu từ Unicode Common Locale Data Repository; là nguồn mặc định trong các JDK hiện đại |
| HOST | Phản ánh một số thiết lập locale của hệ điều hành; khả năng hỗ trợ phụ thuộc JDK/OS |
| SPI | Các LocaleServiceProvider do ứng dụng/thư viện triển khai |

### Thứ tự provider

Thuộc tính hệ thống **java.locale.providers** cho phép cấu hình thứ tự ưu tiên giữa các nguồn. Ví dụ:

~~~text
java -Djava.locale.providers=SPI,CLDR -jar app.jar
~~~

Với cấu hình trên, provider SPI được tìm trước CLDR trong danh sách provider. Nếu provider ưu tiên không có dữ liệu cho dịch vụ/locale yêu cầu, quá trình tìm kiếm tiếp tục theo thứ tự đã cấu hình.

**Đặt thuộc tính lúc khởi chạy JVM.** JavaDoc nêu property được đọc và cache khi LocaleServiceProvider khởi tạo; gọi System.setProperty("java.locale.providers", ...) trong lúc ứng dụng đang chạy có thể không thay đổi thứ tự lookup.

Default hiện đại tương đương CLDR. HOST có thể không có trên mọi JDK reference implementation. Đừng giả định máy Windows, macOS, Linux và container luôn trả cùng dữ liệu HOST.

### LocaleServiceProvider dùng để làm gì?

Nếu runtime không cung cấp locale data cần thiết, ứng dụng có thể triển khai SPI tương ứng, chẳng hạn:

- NumberFormatProvider: format số, tiền tệ, phần trăm.
- DateFormatProvider: format ngày/giờ theo locale.
- DateFormatSymbolsProvider: tên tháng, ngày, AM/PM.
- CollatorProvider: so sánh/sắp xếp chuỗi theo locale.
- LocaleNameProvider: tên language, script, region và variant.
- TimeZoneNameProvider: tên múi giờ.

Một provider cụ thể khai báo danh sách locale được hỗ trợ và triển khai các factory/name methods của SPI. Ví dụ một NumberFormatProvider cần cung cấp getAvailableLocales(), isSupportedLocale(Locale) và các phương thức tạo NumberFormat phù hợp.

### Cách đăng ký provider

- Với classpath: cung cấp file UTF-8 trong META-INF/services có tên service interface, ví dụ java.text.spi.NumberFormatProvider; file chứa tên đầy đủ của class provider.
- Với module: khai báo provides java.text.spi.NumberFormatProvider with ... trong module-info.java.
- Provider phải được nhìn thấy bởi system class loader theo contract của SPI.
- Nếu muốn runtime sử dụng SPI, cấu hình provider order tại JVM startup để có SPI trong java.locale.providers.

### isSupportedLocale và extension

LocaleServiceProvider kiểm tra locale được hỗ trợ bằng isSupportedLocale. Theo mặc định, **locale extensions bị bỏ qua khi kiểm tra hỗ trợ**; provider chỉ cần quan tâm extension nếu override phương thức phù hợp. Vì vậy, đừng chỉ so sánh nguyên Locale object rồi kết luận mọi Unicode extension đều được provider xử lý.

### Provider hỗ trợ locale không đồng nghĩa mọi tên đều có sẵn

Với các provider cung cấp tên (ví dụ tên ngôn ngữ/vùng), JavaDoc cho phép provider trả null đối với một số yêu cầu tên ngay cả khi locale có trong getAvailableLocales(). Khi tên không có, lookup có thể tiếp tục fallback theo candidate locales. Vì vậy, test một tên cụ thể vẫn cần gọi đúng phương thức name lookup; không chỉ kiểm tra danh sách locale.

## 20. CLDR và khác biệt giữa các phiên bản JDK

Java sử dụng locale data từ Unicode CLDR cho nhiều API java.text và java.util. CLDR được cập nhật theo thời gian, nên tên vùng, mẫu ngày, symbol tiền tệ, quy tắc số nhiều và một số dữ liệu khác có thể đổi giữa các JDK.

Oracle công bố các mốc CLDR tương ứng cho các dòng JDK, ví dụ:

| JDK | CLDR locale data |
|---|---|
| JDK 17 | CLDR 39 |
| JDK 24 | CLDR 46 |
| JDK 25 | CLDR 47 |

Đây là lý do một chuỗi hiển thị được chụp snapshot trên một JDK có thể thay đổi khi chạy trên JDK mới hơn, dù code Locale không thay đổi.

### Test ổn định theo contract, không theo ảnh chụp tình cờ

Tách hai loại test:

**Contract tests** kiểm tra hành vi bền vững:

- Language tag canonicalize đúng.
- Locale được chọn thuộc allowlist ứng dụng.
- Locale không hỗ trợ được fallback theo policy.
- NumberFormat output có thể parse lại khi dùng đúng locale/formatter.
- Display name không rỗng nếu dịch vụ có tên; nếu không có thì fallback theo policy.
- Kết quả format được gọi với đúng Locale tường minh.
- Không sử dụng default locale ngoài ý muốn.

**Snapshot tests** kiểm tra chính xác chuỗi localized:

- Chỉ nên bật khi sản phẩm thật sự cần chuỗi đúng từng ký tự.
- Pin JDK vendor/build, CLDR data/provider và locale.
- Khi nâng JDK, review thay đổi snapshot như một thay đổi dữ liệu localization, không tự động sửa expected value mà chưa xác minh.

### Đừng hardcode tên vùng như dữ liệu nghiệp vụ

Không dùng chuỗi "United States", "États-Unis" hoặc "アメリカ合衆国" để so sánh danh tính vùng. Hãy lưu region code chuẩn như US, CA, TW hoặc mã domain riêng; chỉ gọi getDisplayCountry(displayLocale) khi render cho người đọc.

Tương tự, không so sánh symbol tiền tệ hiển thị để quyết định currency code. Lưu mã tiền tệ và amount theo domain; localized formatter chỉ chịu trách nhiệm trình bày.
## 21. Thiết kế test matrix cho locale không được hỗ trợ

Một bộ test locale tốt không chỉ có một case "supported" và một case "unsupported". Nên chia theo các lớp sau:

| Case | Input | Kiểm tra | Kết quả mong muốn |
|---|---|---|---|
| Well-formed, có hỗ trợ | en-US, fr-FR | Service-specific available locales | Có trong service list ở runtime đã pin |
| Well-formed, không hỗ trợ | zz-ZZ | Locale có tạo được không, service list có chứa không | Locale tạo được; service có thể fallback |
| Sai cú pháp | en_US | Locale.Builder.setLanguageTag | IllformedLocaleException |
| Có language, thiếu region data | Một locale con chưa có data | Candidate fallback | Dùng locale cha nếu có |
| Không có app translation | Locale không nằm allowlist/bundle | Application support | Chọn fallback đã định nghĩa hoặc từ chối |
| Tên vùng theo nhiều display locale | Locale.US + EN/FR/JA | getDisplayCountry(displayLocale) | Tên thay đổi theo ngôn ngữ hiển thị |
| Định dạng theo region | US/DE/FR | NumberFormat với Locale tường minh | Dấu phân nhóm/thập phân theo locale |
| Default category khác nhau | FORMAT=DE, DISPLAY=FR | Factory không tham số và tên hiển thị | Mỗi API dùng đúng category |
| Language negotiation không có match | Accept-Language ja-JP, app chỉ US/FR | Locale.lookup | null và app fallback có chủ đích |
| Khác phiên bản JDK | JDK 17/24/25 | Tên vùng, symbol, pattern | Review thay đổi data, không coi là lỗi code mặc định |

### Các lớp test nên tách riêng

1. **Parsing/validation test:** kiểm tra cú pháp BCP 47 và canonicalization.
2. **Support test:** kiểm tra service-specific locale availability trên runtime/provider đã xác định.
3. **Fallback test:** kiểm tra hành vi khi locale không có dữ liệu riêng.
4. **Display-name test:** kiểm tra tên vùng/ngôn ngữ theo display locale.
5. **Formatting test:** kiểm tra số/ngày/tiền tệ theo FORMAT locale.
6. **Negotiation test:** kiểm tra lựa chọn locale trong allowlist ứng dụng.
7. **Resource test:** kiểm tra bản dịch và fallback bundle độc lập với JDK locale data.
8. **Cross-runtime test:** kiểm tra thay đổi CLDR/provider khi nâng JDK.

Không gom tất cả vào một test dùng default locale của máy developer. Nếu một test thay đổi Locale.setDefault, chạy cô lập hoặc bảo đảm không chạy song song với test khác.

## 22. Cách viết assertion bền vững

### Test support, không test thứ tự mảng

getAvailableLocales() trả mảng locale, không có bảo đảm thứ tự. Dùng Set hoặc Arrays.asList(...).contains(locale), không assert mảng có đúng thứ tự như một snapshot.

~~~java
Set<Locale> supported =
        new HashSet<>(Arrays.asList(NumberFormat.getAvailableLocales()));
assertTrue(supported.contains(Locale.US));
~~~

Nếu dùng service khác, kiểm tra danh sách của service đó. Không dùng một danh sách chung cho mọi API.

### Test format bằng locale tường minh

~~~java
String formatted =
        NumberFormat.getNumberInstance(Locale.GERMANY).format(12345.67);
~~~

Nếu test chỉ muốn chứng minh dấu phân nhóm/thập phân, có thể lấy DecimalFormatSymbols của locale và kiểm tra grouping separator/decimal separator. Cách này rõ mục tiêu hơn việc so sánh cả chuỗi có khoảng trắng đặc biệt.

### Test fallback theo runtime đã pin

Nếu muốn assert zz-ZZ fallback giống Locale.ROOT, hãy pin JDK/provider và xác nhận môi trường test không cài SPI riêng hỗ trợ zz-ZZ. Trong một runtime có custom provider, cùng locale đó có thể được hỗ trợ thật sự; kết quả khác là hợp lệ.

### Test tên hiển thị

Khi mục tiêu là kiểm tra API gọi đúng display locale, dùng các giá trị display locale tường minh và snapshot theo runtime đã pin. Nếu mục tiêu chỉ là kiểm tra không rỗng, dùng assert không rỗng. Không hardcode mọi tên vùng cho tất cả ngôn ngữ/JDK.

### Test default locale

Mặc định, không dùng API không truyền locale trong business logic hoặc test cần kết quả xác định. Nếu buộc kiểm tra default, lưu FORMAT/DISPLAY riêng, đổi bằng setDefault(category, locale), và khôi phục trong finally. Test này nên chạy serial vì default là state chung JVM.

## 23. Những lỗi thường gặp

### 23.1. Nghĩ tạo được Locale là runtime có hỗ trợ

Locale là identifier. Dữ liệu locale được cung cấp riêng bởi runtime hoặc provider. Cần kiểm tra API service cụ thể.

### 23.2. Dùng Locale.getAvailableLocales cho mọi dịch vụ

Một locale có thể có trong runtime nhưng không có data cho NumberFormat/DateFormat cụ thể. Dùng getAvailableLocales() của chính service cần kiểm tra.

### 23.3. Dùng available locales của JDK làm danh sách ngôn ngữ sản phẩm

JDK có thể hỗ trợ nhiều locale mà ứng dụng chưa dịch; ứng dụng cũng có thể có resource tự cung cấp. Dùng allowlist/resource registry của ứng dụng.

### 23.4. Cho rằng unsupported locale luôn ném exception

Nhiều factory fallback qua candidate locale chain và vẫn trả formatter. Hãy kiểm tra dữ liệu/locale thực tế được dùng theo contract và policy của sản phẩm.

### 23.5. Cho rằng locale fallback đã thay đổi requested Locale

Không. Requested locale vẫn là yêu cầu ban đầu; fallback chỉ là cách service tìm dữ liệu để thực hiện công việc.

### 23.6. Dùng Locale.forLanguageTag cho validation strict

forLanguageTag có hành vi bỏ phần sai cú pháp. Nếu muốn từ chối tag malformed, dùng Locale.Builder.setLanguageTag và bắt IllformedLocaleException.

### 23.7. Nhầm well-formed với registered hoặc supported

Builder kiểm tra cú pháp, không bảo đảm mã có trong IANA registry hoặc runtime data. Phải có bước kiểm tra riêng.

### 23.8. Dùng getDisplayCountry() không tham số trong snapshot test

Kết quả phụ thuộc default DISPLAY locale của JVM. Truyền display locale tường minh.

### 23.9. Nhầm display locale với format locale

Tên quốc gia dùng DISPLAY; số/ngày/tiền tệ dùng FORMAT khi gọi factory không tham số. Test đúng category.

### 23.10. Thay default locale theo từng request

Locale.setDefault thay trạng thái JVM, có thể làm các request/test khác ảnh hưởng lẫn nhau. Truyền Locale cho từng API.

### 23.11. So sánh tên quốc gia localized để xác định country code

Tên hiển thị có thể khác theo ngôn ngữ và CLDR. Lưu mã vùng chuẩn; chỉ format tên để hiển thị.

### 23.12. Giả định dữ liệu locale không thay đổi giữa các JDK

CLDR được cập nhật theo release; tên vùng, symbol, date pattern có thể đổi. Pin runtime cho snapshot test hoặc assert contract ổn định.

### 23.13. Bỏ qua khoảng trắng Unicode trong output

French number formatting có thể dùng U+202F. Nếu so sánh string, cần hiểu code point, không thay mọi whitespace bằng ASCII space một cách tùy tiện.

### 23.14. Dùng formatter default để parse dữ liệu machine

Default locale của host có thể khác. Với protocol, file format và identifier, dùng locale/charset/grammar được đặc tả rõ, thường không dựa vào user default.

### 23.15. Coi Base language match là mọi region đều giống nhau

fr-CA và fr-FR có thể khác quy tắc vùng, currency và display names dù cùng language. Test cả language và region khi sản phẩm yêu cầu.

### 23.16. Không xử lý Locale.lookup trả null

Nếu không có locale phù hợp trong danh sách sản phẩm hỗ trợ, lookup trả null. Phải fallback hoặc từ chối rõ, không dereference null.

### 23.17. Cài custom provider nhưng không cấu hình provider order

SPI phải được đăng ký và nằm trong thứ tự provider được runtime tìm. Kiểm tra module/service descriptor và đặt java.locale.providers lúc khởi chạy.

### 23.18. Đổi java.locale.providers bằng System.setProperty khi app đang chạy

Property được đọc/cache khi service khởi tạo. Cấu hình lúc launch JVM và test bằng process riêng.

### 23.19. Chỉ kiểm tra bundle tồn tại mà không kiểm tra bundle locale

ResourceBundle có thể fallback về bundle cha hoặc default locale. Kiểm tra getLocale() và các key quan trọng, không chỉ kiểm tra không ném exception.

### 23.20. Coi tên vùng không có là locale không hợp lệ

Một provider có thể thiếu một tên riêng lẻ dù locale có hỗ trợ. Tên display, service data và validation của region code là các vấn đề riêng.

## 24. Checklist trước khi triển khai đa ngôn ngữ

- Đầu vào language tag có được parse theo BCP 47 và reject malformed input không?
- Sản phẩm có allowlist locale riêng thay vì dùng toàn bộ Locale.getAvailableLocales() không?
- Có phân biệt app translation support với JDK service data support không?
- Với mỗi service, có kiểm tra danh sách getAvailableLocales() tương ứng không?
- Có policy fallback rõ ràng cho language/region không hỗ trợ không?
- Có ghi nhận requested locale và locale ứng dụng thực sự chọn không?
- Nếu lookup không tìm được locale, có xử lý null không?
- Tên vùng có được hiển thị theo display locale tường minh không?
- NumberFormat/DateFormat có nhận FORMAT locale tường minh khi cần không?
- Có tránh Locale.setDefault trong request handler không?
- Có kiểm thử vùng khác nhau trong cùng một language (ví dụ fr-CA và fr-FR) không?
- Có hiểu khoảng trắng Unicode và dấu phân nhóm trong localized output không?
- Có kiểm thử ResourceBundle fallback riêng với formatter fallback không?
- Nếu dùng custom LocaleServiceProvider, đã đăng ký provider và cấu hình thứ tự lúc JVM startup chưa?
- Có pin JDK/provider cho snapshot test tên vùng hoặc mẫu định dạng không?
- Khi nâng JDK, có review thay đổi CLDR data và cập nhật test có chủ đích không?
- Identifier/protocol token có dùng Locale.ROOT hoặc quy tắc machine-readable thay vì default locale không?
- Mã vùng/currency có được lưu bằng code ổn định thay vì tên hiển thị không?

## 25. Câu hỏi ôn tập

**Câu 1.** Tạo được Locale có chứng minh JDK hỗ trợ locale đó không?

*Đáp án:* Không. Locale là identifier; runtime/provider có thể không có dữ liệu cho service cần dùng.

**Câu 2.** Locale.getAvailableLocales() và NumberFormat.getAvailableLocales() khác nhau thế nào?

*Đáp án:* Cái đầu là tập locale runtime và LocaleServiceProvider nói chung; cái sau là tập locale mà NumberFormat có thể tạo localized instance. Hỗ trợ phải được kiểm tra theo từng service.

**Câu 3.** Locale.Builder kiểm tra điều gì?

*Đáp án:* Kiểm tra cú pháp/well-formedness của language tag và các trường; không xác nhận mọi subtag đã đăng ký hoặc có locale data.

**Câu 4.** Khi nào dùng Locale.forLanguageTag và khi nào dùng Locale.Builder?

*Đáp án:* forLanguageTag có hành vi tolerant với phần sai cú pháp; Builder phù hợp khi cần reject tag malformed bằng IllformedLocaleException.

**Câu 5.** Vì sao NumberFormat.getNumberInstance(zz-ZZ) có thể không ném exception?

*Đáp án:* Locale-sensitive service có candidate locale fallback và có thể dùng locale cha hoặc root nếu không có data cho locale yêu cầu.

**Câu 6.** getDisplayCountry(Locale.FRENCH) thay đổi điều gì?

*Đáp án:* Nó giữ nguyên vùng được mô tả, nhưng trả tên vùng bằng ngôn ngữ hiển thị French.

**Câu 7.** Khác biệt giữa FORMAT và DISPLAY category?

*Đáp án:* FORMAT phục vụ formatting số/ngày/tiền tệ; DISPLAY phục vụ tên hiển thị locale/language/region.

**Câu 8.** Vì sao không set default locale theo từng request?

*Đáp án:* Default locale là state toàn JVM; request khác và thread khác có thể chịu ảnh hưởng.

**Câu 9.** Locale.lookup trả null có nghĩa gì?

*Đáp án:* Không có locale nào trong danh sách ứng dụng cung cấp match phù hợp với language ranges; ứng dụng phải chọn fallback hoặc từ chối.

**Câu 10.** Vì sao snapshot tên quốc gia có thể đổi sau khi nâng JDK?

*Đáp án:* Locale data từ CLDR thay đổi theo phiên bản; runtime/provider khác có thể cập nhật tên và quy tắc định dạng.

**Câu 11.** Nếu NumberFormat hỗ trợ fr-CA thì ứng dụng có chắc có bản dịch fr-CA không?

*Đáp án:* Không. JDK locale data và application resource bundles là hai nguồn độc lập.

**Câu 12.** Dùng provider SPI để làm gì?

*Đáp án:* Cung cấp locale-sensitive services/dữ liệu bổ sung cho runtime, ví dụ NumberFormatProvider hoặc DateFormatProvider.

**Câu 13.** Tại sao java.locale.providers nên được đặt lúc khởi chạy?

*Đáp án:* Thứ tự provider được đọc và cache khi LocaleServiceProvider khởi tạo; đổi System property sau đó có thể không có tác dụng.

**Câu 14.** Tại sao tên vùng không nên là khóa lưu trữ?

*Đáp án:* Tên vùng localized phụ thuộc display locale và CLDR version; lưu region code ổn định rồi render tên theo người dùng.

**Câu 15.** Khi test locale không hỗ trợ, cần ghi nhận những gì?

*Đáp án:* Requested tag, cú pháp, runtime/service availability, provider/runtime đã dùng, fallback thực tế và locale ứng dụng đã chọn.

## 26. Tài liệu chính thức còn được duy trì

- Oracle Java SE 25 — **Locale**: BCP 47, locale fields, default locale, available locales và display names: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html
- Oracle Java SE 25 — **Locale.Builder**: validation language tag và IllformedLocaleException: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.Builder.html
- Oracle Java SE 25 — **LocaleServiceProvider**: hỗ trợ locale, candidate fallback và provider order: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/spi/LocaleServiceProvider.html
- Oracle Java SE 25 — **NumberFormat**: factory theo Locale và danh sách locale được hỗ trợ: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/NumberFormat.html
- Oracle Java SE 25 — **DateFormat**: factory và available locales: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/DateFormat.html
- Oracle Java SE 25 — **ResourceBundle**: candidate locale search và fallback bundle: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ResourceBundle.html
- Oracle Java SE 25 — **Internationalization Overview**: locale identification, localization và locale data providers: https://docs.oracle.com/en/java/javase/25/intl/internationalization-overview.html
- Oracle — **JDK 25 Supported Locales**: CLDR, HOST, SPI và locale data hiện hành: https://www.oracle.com/latam/java/technologies/javase/jdk25-supported-locales.html
- IETF — **RFC 5646**: Tags for Identifying Languages: https://www.rfc-editor.org/rfc/rfc5646
- IETF — **RFC 4647**: Matching of Language Tags: https://www.rfc-editor.org/rfc/rfc4647
- Unicode Consortium — **CLDR**: dữ liệu locale dùng trong nhiều API quốc tế hóa: https://cldr.unicode.org/

**Kết luận:** Locale trong Java là định danh, còn dữ liệu thực tế được cung cấp theo từng locale-sensitive service và provider. Một tag đúng cú pháp có thể không được runtime hỗ trợ; factory có thể fallback thay vì ném lỗi. Tên vùng phụ thuộc display locale, còn định dạng số/ngày phụ thuộc format locale và data provider. Hãy validate tag, dùng allowlist ứng dụng, kiểm tra hỗ trợ theo đúng service, truyền Locale tường minh và thiết kế test có tính đến CLDR/JDK version. Khi cần dữ liệu riêng, triển khai LocaleServiceProvider đúng cách; khi cần bản dịch ứng dụng, quản lý resource bundle và fallback riêng.
