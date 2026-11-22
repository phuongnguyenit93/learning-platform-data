# Locale.setDefault và phạm vi ảnh hưởng toàn tiến trình trong Java

## 1. Locale mặc định là gì?

Trong Java, `Locale` biểu diễn lựa chọn ngôn ngữ, chữ viết, khu vực và một số quy ước liên quan đến bản địa hóa. Một số API nhận `Locale` tường minh; những API khác sử dụng **locale mặc định của JVM** khi người gọi không truyền lựa chọn.

Ví dụ, hai lời gọi sau có thể biểu diễn cùng cách định dạng số nếu không có bên nào thay đổi giá trị mặc định giữa lúc đọc và sử dụng:

~~~java
NumberFormat a = NumberFormat.getNumberInstance();
NumberFormat b = NumberFormat.getNumberInstance(
        Locale.getDefault(Locale.Category.FORMAT));
~~~

Đây là **đoạn minh họa**, cần `import java.text.NumberFormat;` và `import java.util.Locale;` trong mã chạy đầy đủ.

Vấn đề quan trọng nhất của chủ đề này là **`Locale.setDefault(...)` thay đổi trạng thái dùng chung trong cả một JVM**, không phải thiết lập ngôn ngữ chỉ cho phương thức, request, phiên đăng nhập hoặc một luồng đang thực thi. Nếu JVM có nhiều người dùng hay nhiều tác vụ đồng thời, việc một luồng gọi `setDefault` có thể tác động đến những thao tác locale-sensitive khác.

Khái niệm “toàn tiến trình” ở đây nên hiểu chính xác là **giá trị mặc định của một JVM instance**. Nó không chỉnh ngôn ngữ của hệ điều hành, không đổi mặc định của JVM khác và không tự làm mọi văn bản đang tồn tại được dịch lại. Một hệ thống chạy nhiều JVM có thể có các mặc định khác nhau.

## 2. Những API cần phân biệt

Java 17 cung cấp các phương thức tĩnh sau trên `java.util.Locale`:

| API | Vai trò |
| --- | --- |
| `Locale.getDefault()` | Đọc locale mặc định chung, không chỉ định category |
| `Locale.setDefault(Locale)` | Đặt locale mặc định chung **và mặc định của hai category `DISPLAY`, `FORMAT`** |
| `Locale.getDefault(Locale.Category)` | Đọc mặc định cho đúng category |
| `Locale.setDefault(Locale.Category, Locale)` | Chỉ thay đổi locale mặc định **của category được chỉ định** |
| `Locale.getDefault(Locale.Category.DISPLAY)` | Đọc mặc định thường dùng khi hiển thị tên ngôn ngữ/khu vực cho con người |
| `Locale.getDefault(Locale.Category.FORMAT)` | Đọc mặc định thường dùng cho số, tiền tệ, ngày và giờ |

Hai category của `Locale.Category`:

- **`DISPLAY`:** quy ước hiển thị tên ngôn ngữ, quốc gia/khu vực và dữ liệu tên hiển thị mang tính ngôn ngữ. Chẳng hạn `someLocale.getDisplayLanguage()` không truyền locale riêng sẽ sử dụng mặc định `DISPLAY`.
- **`FORMAT`:** quy ước định dạng số, tiền tệ, phần trăm, ngày và giờ. Chẳng hạn `NumberFormat.getNumberInstance()` sử dụng mặc định `FORMAT`.

`Locale.getDefault()` **không bắt buộc bằng** `Locale.getDefault(Locale.Category.FORMAT)` hoặc `Locale.getDefault(Locale.Category.DISPLAY)` sau khi có thiết lập theo category. Việc chỉ đọc `getDefault()` để đoán cách `NumberFormat` hoạt động có thể đưa đến kết luận sai.

### Trạng thái thay đổi như thế nào?

Giả sử bắt đầu bằng:

~~~java
Locale.setDefault(Locale.US);
~~~

Lúc này giá trị chung, `DISPLAY`, `FORMAT` đều là `en-US`. Sau đó:

~~~java
Locale.setDefault(Locale.Category.FORMAT, Locale.FRANCE);
~~~

Kết quả: mặc định chung vẫn là `en-US`, `DISPLAY` vẫn `en-US`, **chỉ `FORMAT` chuyển thành `fr-FR`**. Nếu sau đó gọi:

~~~java
Locale.setDefault(Locale.JAPAN);
~~~

Cả ba trở thành `ja-JP`. Cần phân biệt hai overload rõ ràng vì chúng có phạm vi tác động khác nhau nhưng đều là **trạng thái toàn JVM**.

Việc truyền `null` cho locale (hoặc category cần thiết) là lỗi và có thể gây `NullPointerException`; không dùng `null` với kỳ vọng khôi phục mặc định của hệ điều hành.

## 3. Locale mặc định được khởi tạo từ đâu?

Khi JVM khởi động, Java xác định giá trị mặc định ban đầu dựa trên môi trường host và cấu hình hệ thống. Các thuộc tính hệ thống như `user.language`, `user.country`, `user.script`, `user.variant` cùng biến thể theo category (ví dụ `user.language.format` và `user.language.display`) có thể tham gia xác định giá trị đó.

Các điểm cần hiểu đúng:

1. **Môi trường máy chạy ảnh hưởng giá trị ban đầu:** máy phát triển và máy CI/server có thể có locale mặc định khác nhau. Đừng dựa vào một mặc định “luôn là en-US” hoặc “luôn là vi-VN”.
2. **Tham số JVM có thể đặt đầu vào lúc khởi động:** ví dụ `-Duser.language=vi -Duser.country=VN` (khi runtime hỗ trợ cách khởi tạo tương ứng). Nếu muốn cấu hình mặc định, hãy ưu tiên một điểm cấu hình rõ ràng trước khi chương trình khởi tạo các thành phần phụ thuộc locale.
3. **`Locale.setDefault(...)` không cập nhật các system property `user.*`:** đọc `System.getProperty("user.language")` sau khi gọi `setDefault` có thể không phản ánh mặc định đang hoạt động.
4. **Gọi `System.setProperty("user.language", ...)` lúc runtime không phải phương pháp đáng tin cậy để thay đổi default locale đang dùng:** nếu muốn thay trạng thái Locale trực tiếp, API chính thức là `setDefault`, dù sự thay đổi runtime cần hết sức cân nhắc.
5. **Default locale khác default time zone:** `Locale.setDefault(Locale.JAPAN)` không tự đổi `TimeZone.getDefault()` hoặc `ZoneId.systemDefault()`, không tính tỷ giá và không chuyển tiền từ một đơn vị sang đơn vị khác.

Locale mặc định là *fallback cho các API sử dụng nó*; nó không phải nơi lưu danh sách ngôn ngữ mà ứng dụng hỗ trợ. Có thể chọn `Locale` hợp lệ nhưng không có resource bundle cho sản phẩm.

## 4. Chương trình Java 17 chứng minh phạm vi toàn JVM

Đặt chương trình sau vào file **`DefaultLocaleScopeDemo.java`**. Nó cố ý chuyển default locale để giải thích hành vi, sau đó khôi phục trạng thái ban đầu trong `finally`. Đoạn này phù hợp để chạy **riêng lẻ** như một demo, không phải mẫu thay đổi locale cho từng request trong ứng dụng server.

~~~java
import java.util.Locale;

public class DefaultLocaleScopeDemo {
    private static void show(String label) {
        String global = Locale.getDefault().toLanguageTag();
        String display = Locale.getDefault(
                Locale.Category.DISPLAY).toLanguageTag();
        String format = Locale.getDefault(
                Locale.Category.FORMAT).toLanguageTag();

        System.out.println(label + ": global=" + global
                + ", DISPLAY=" + display + ", FORMAT=" + format);
    }

    public static void main(String[] args) throws InterruptedException {
        Locale originalGlobal = Locale.getDefault();
        Locale originalDisplay =
                Locale.getDefault(Locale.Category.DISPLAY);
        Locale originalFormat =
                Locale.getDefault(Locale.Category.FORMAT);

        try {
            // Đặt mặc định chung: đồng thời thay đổi cả hai category.
            Locale.setDefault(Locale.US);
            show("US");

            // Chỉ FORMAT đổi; global và DISPLAY vẫn en-US.
            Locale.setDefault(
                    Locale.Category.FORMAT, Locale.FRANCE);
            show("FORMAT France");

            // Một luồng khác nhìn thấy cùng trạng thái mặc định.
            Thread other = new Thread(() ->
                    System.out.println("other thread FORMAT="
                            + Locale.getDefault(
                                    Locale.Category.FORMAT)
                                    .toLanguageTag()));
            other.start();
            other.join();

            // Gọi overload chung: cập nhật lại cả ba giá trị.
            Locale.setDefault(Locale.JAPAN);
            show("JAPAN");
        } finally {
            // Khôi phục cả mặc định chung và từng category.
            Locale.setDefault(originalGlobal);
            Locale.setDefault(Locale.Category.DISPLAY, originalDisplay);
            Locale.setDefault(Locale.Category.FORMAT, originalFormat);
        }
    }
}
~~~

Biên dịch/chạy bằng Java 17 trở lên:

~~~bash
javac -encoding UTF-8 DefaultLocaleScopeDemo.java
java DefaultLocaleScopeDemo
~~~

**Stdout dự kiến chính xác** của chương trình khi không có mã khác thay đổi default locale đồng thời:

~~~text
US: global=en-US, DISPLAY=en-US, FORMAT=en-US
FORMAT France: global=en-US, DISPLAY=en-US, FORMAT=fr-FR
other thread FORMAT=fr-FR
JAPAN: global=ja-JP, DISPLAY=ja-JP, FORMAT=ja-JP
~~~

Cách đọc kết quả:

- Lần gọi `setDefault(Locale.US)` cập nhật **mặc định chung và cả hai category**.
- `setDefault(Category.FORMAT, Locale.FRANCE)` không làm đổi `getDefault()` và `DISPLAY`, nhưng `FORMAT` trở thành `fr-FR`.
- Luồng `other` không hề được truyền `Locale.FRANCE`, nhưng khi đọc mặc định category `FORMAT` nó vẫn thấy `fr-FR`: đây là một đặc tính toàn JVM, không phải đặc quyền của luồng đã gọi `setDefault`.
- Lời gọi cuối `setDefault(Locale.JAPAN)` lại thay cả ba giá trị.

Chương trình lưu ba giá trị ban đầu riêng biệt, bởi vì trước khi chạy demo chúng **có thể đã khác nhau**. Chỉ khôi phục `Locale.getDefault()` bằng một lệnh `setDefault(originalGlobal)` sẽ làm mất khác biệt `DISPLAY`/`FORMAT` trước đó.

**Giới hạn của `finally`:** việc khôi phục giúp ví dụ có trách nhiệm khi chạy một mình, **không tạo ra transaction hoặc cơ chế cô lập**. Nếu nhiều thread khác cùng đọc/sửa default locale, chúng vẫn có thể nhìn thấy giá trị tạm thời. Nếu một bên khác thay đổi mặc định trong khoảng thời gian này, việc “khôi phục” còn có thể ghi đè thay đổi của bên đó. Đây là lý do không áp dụng mẫu tạm đổi rồi restore trong request đồng thời.

## 5. Ảnh hưởng thực tế lên API định dạng và hiển thị

Khi không được truyền locale cụ thể, nhiều API dùng giá trị mặc định tương ứng. Một số ví dụ (đoạn minh họa bên trong một method đã import các lớp cần thiết):

~~~java
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

// Các factory không có Locale tường minh thường dùng FORMAT default.
NumberFormat defaultNumber = NumberFormat.getNumberInstance();
NumberFormat explicitNumber =
        NumberFormat.getNumberInstance(Locale.GERMANY);

DateTimeFormatter defaultDate =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT);
DateTimeFormatter explicitDate =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(Locale.forLanguageTag("vi-VN"));

String a = defaultNumber.format(1234.5);
String b = explicitNumber.format(1234.5);
String c = defaultDate.format(LocalDate.of(2026, 1, 15));
String d = explicitDate.format(LocalDate.of(2026, 1, 15));
~~~

**Đây chỉ là các câu lệnh minh họa, không phải một chương trình độc lập:** chúng cần được đặt trong phương thức hoặc một class thích hợp. Trên một số API, quyết định locale diễn ra khi tạo đối tượng; trên API khác, khi format hoặc tra cứu, thư viện có thể đọc hoặc lưu cache giá trị khác nhau. Vì vậy **đổi default locale không có nghĩa tất cả formatter đã tạo, cache, UI cũ hay response đang gửi đều tự đổi theo**. Nếu một thành phần cần locale cụ thể, hãy truyền locale tường minh và cấu hình nó tại nơi sử dụng.

Đối với **tên quốc gia hoặc ngôn ngữ**, Java có overload phù hợp với `DISPLAY`:

~~~java
Locale target = Locale.JAPAN;
String byDefault = target.getDisplayCountry(); // DISPLAY default
String byVietnamese =
        target.getDisplayCountry(Locale.forLanguageTag("vi-VN"));
~~~

`getDisplayCountry()` có thể cho ra chuỗi khác khi category `DISPLAY` thay đổi, còn overload truyền locale cho kết quả phù hợp với lựa chọn đã đưa vào (trong giới hạn dữ liệu locale/provider có sẵn).

Đối với **tài nguyên thông điệp**, lưu ý `ResourceBundle.getBundle("messages")` tìm bundle dựa trên **`Locale.getDefault()` chung**, với cơ chế fallback của `ResourceBundle`; đừng suy luận rằng nó nhất thiết dùng category `DISPLAY` hoặc cứ đổi category `FORMAT` thì bản dịch sẽ đổi. Nếu muốn bundle cụ thể, gọi overload truyền `Locale` tường minh, kiểm tra hỗ trợ và quy tắc fallback của ứng dụng:

~~~java
ResourceBundle messages =
        ResourceBundle.getBundle("messages", requestedLocale);
~~~

Đoạn cuối cần `requestedLocale` là một biến `Locale` đã được xác định, `import java.util.ResourceBundle;`, và các tài nguyên `messages*.properties` tương ứng trên classpath.

## 6. Rủi ro khi gọi setDefault trong server nhiều người dùng

Giả sử một web server có hai request đồng thời:

~~~text
Thời điểm  Request A (người dùng vi-VN)      Request B (người dùng en-US)
   t1      Locale.setDefault(vi-VN)           -
   t2      -                                  Locale.setDefault(en-US)
   t3      NumberFormat.getInstance()         -
   t4      -                                  NumberFormat.getInstance()
~~~

Request A ở thời điểm `t3` có thể lấy formatter theo **en-US** mặc dù nó vừa đặt default là **vi-VN**. Lịch chạy các thread không bảo đảm lời gọi nào sẽ đọc giá trị nào. Lỗi có thể xảy ra ngẫu nhiên dưới tải, rất khó tái hiện bằng kiểm thử tuần tự.

Những hệ quả điển hình:

- **Sai ngôn ngữ/định dạng giữa người dùng:** số, ngày, nhãn hoặc bundle mặc định có thể mang locale của request khác.
- **Bị phụ thuộc thư viện:** một thư viện gọi API no-argument có thể quan sát default do code ứng dụng đổi, kể cả ở scheduler hoặc background task không liên quan.
- **Test không ổn định:** test A đổi `Locale.setDefault`, test B chạy song song hoặc sau đó nhận môi trường đã bị thay đổi. `@AfterEach` có thể trả lại trạng thái khi chạy tuần tự, nhưng không bảo đảm cô lập giữa test song song.
- **Cache không đồng bộ với mặc định:** formatter hoặc bản dịch được tạo khi locale cũ còn hiệu lực không bắt buộc tự đổi theo; một phần giao diện dùng locale cũ, phần khác dùng locale mới.
- **Nhiều đường cấu hình:** nếu một đoạn đổi category `FORMAT` còn đoạn khác gọi overload chung, kết quả cuối có thể khó đoán do thứ tự thực thi.

Không dùng `synchronized` cục bộ bao quanh một đoạn `setDefault` rồi restore và mặc định đó là giải pháp chung: chỉ có tác dụng với **tất cả** code cùng dùng đúng một khóa và không có thư viện/thread khác truy cập default bên ngoài khóa. Trong server dùng chung JVM, điều kiện này thường không thể bảo đảm.

## 7. Cách đúng để xử lý Locale theo request hoặc tác vụ

Thay vì sửa mặc định chung ở mỗi request, hãy chọn locale tại **ranh giới nhận input**, sau đó truyền tới các chức năng cần hiển thị dữ liệu:

~~~text
Request / user preference / Accept-Language
                    |
                    v
         Chọn Locale được hỗ trợ
                    |
                    v
            Presentation layer
              /         |         \
   ResourceBundle    NumberFormat   DateTimeFormatter
       (locale)        (locale)        (.withLocale)
                    |
                    v
        Văn bản trả riêng cho request
~~~

Ví dụ phần trình bày với tham số tường minh:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

public class AmountPresenter {
    public static String render(BigDecimal amount, Locale locale) {
        NumberFormat format = NumberFormat.getNumberInstance(locale);
        format.setMinimumFractionDigits(2);
        format.setMaximumFractionDigits(2);
        return format.format(amount);
    }

    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234.50");
        System.out.println(render(amount, Locale.US));
        System.out.println(render(amount, Locale.GERMANY));
    }
}
~~~

Biên dịch:

~~~bash
javac -encoding UTF-8 AmountPresenter.java
java AmountPresenter
~~~

Kết quả theo quy ước thông thường của các locale trên Java 17:

~~~text
1,234.50
1.234,50
~~~

Mặc dù dấu phân cách và khoảng trắng của một số locale có thể thay đổi theo nguồn dữ liệu CLDR/JDK, ví dụ này dùng cách trình bày US và Germany phổ biến. Quan trọng hơn, **hai lượt render độc lập với locale mặc định toàn JVM** và không cần `setDefault`.

Đối với API hoặc giao diện đa ngôn ngữ, có thể kết hợp:

1. **Chọn locale:** dựa trên lựa chọn người dùng, cấu hình hoặc thương lượng `Accept-Language`, rồi đối chiếu danh sách locale ứng dụng hỗ trợ.
2. **Truyền thông tin rõ ràng:** `Locale` vào adapter trình bày và resource bundle, `ZoneId` riêng để hiển thị thời điểm, `Currency` riêng nếu định dạng tiền.
3. **Giữ domain ổn định:** nghiệp vụ lưu `BigDecimal`, mã tiền, `Instant`, trạng thái ổn định; câu đã dịch không trở thành dữ liệu hoặc điều kiện nghiệp vụ.
4. **Truyền context có kiểm soát:** nếu framework có request-locale context (có thể là thread-local), dùng cơ chế quản lý của framework và lưu ý việc chuyển sang thread pool/reactive task; context đó **khác** với `Locale.setDefault`.
5. **Giới hạn fallback:** nếu resource không có bản dịch, chọn fallback sản phẩm công bố; không chỉnh default JVM để “sửa” resource thiếu.

### Khi nào có thể dùng setDefault?

Trong một chương trình batch hoặc desktop **một người dùng** cần chính sách locale thống nhất, việc gọi `Locale.setDefault(...)` **một lần trong giai đoạn bootstrap, trước khi tạo formatter/bundle hoặc chạy nhiều thread**, có thể là một quyết định cấu hình hợp lệ. Tuy nhiên phải hiểu rõ thư viện nào đọc default, liệu có category-specific config hay không và môi trường triển khai dùng nhiều JVM không.

Trong kiểm thử một thành phần phụ thuộc default locale, có thể cố tình đặt default rồi khôi phục sau test nếu test được chạy **tuần tự trong môi trường cô lập**; khôi phục cả `DISPLAY` và `FORMAT`, và không coi thao tác đó là giải pháp cho test chạy song song.

## 8. Các hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
| --- | --- |
| “`setDefault` chỉ đổi ngôn ngữ cho thread này” | Thay đổi default của JVM, thread khác có thể quan sát |
| “`setDefault(Category.FORMAT, ...)` đổi toàn bộ locale” | Chỉ category `FORMAT`; `getDefault()` và `DISPLAY` có thể giữ giá trị khác |
| “`Locale.getDefault()` luôn là locale mà mọi formatter đang dùng” | Formatter thường dựa trên `FORMAT` và có thể đã được tạo/cached trước |
| “Đổi sang `vi-VN` là Java tự dịch mọi câu sang tiếng Việt” | Cần tài nguyên và logic localization của sản phẩm |
| “`setDefault` đổi cấu hình Windows/Linux và mọi JVM” | Không thay locale của hệ điều hành, JVM khác hoặc tiến trình con đã chạy |
| “Đặt `System.setProperty("user.language", ...)` thì mọi API đổi ngay” | Đây không phải cơ chế đáng tin để cập nhật default runtime |
| “Có `finally` là request đồng thời an toàn” | Restore không ngăn thread khác đọc giá trị tạm thời |
| “Locale tự xác định múi giờ và đồng tiền nghiệp vụ” | Múi giờ, tiền tệ và quy tắc kinh doanh cần được mô hình hóa riêng |
| “Locale sau khi đổi sẽ cập nhật mọi object đã tạo” | Một số object lưu hoặc cache locale đã chọn; cần cấu hình lại có chủ đích |

## 9. Kiểm thử hành vi và phạm vi ảnh hưởng

Khi phát triển mã có liên quan đến default locale, nên kiểm tra các tình huống sau:

- **Khởi tạo:** chụp cả ba giá trị `getDefault()`, `getDefault(DISPLAY)`, `getDefault(FORMAT)` thay vì chỉ một giá trị.
- **Đổi chung:** gọi `setDefault(Locale.US)`; xác nhận cả ba cùng `en-US`.
- **Đổi riêng:** gọi `setDefault(FORMAT, Locale.FRANCE)`; xác nhận chỉ `FORMAT` đổi.
- **Luồng khác:** một thread chỉ đọc `getDefault(FORMAT)` phải thấy giá trị process-wide mới nếu không có cập nhật đồng thời khác.
- **API mặc định so với API tường minh:** `NumberFormat.getNumberInstance()` có thể chịu ảnh hưởng default, còn `getNumberInstance(Locale.US)` phải được chọn theo locale đã truyền.
- **Formatter được tạo trước/sau:** không xây test dựa trên giả định mọi formatter cũ tự cập nhật; kiểm tra hợp đồng của lớp đang dùng.
- **Khôi phục:** nếu test cần gọi `setDefault`, lưu và restore cả ba giá trị; chạy tuần tự hoặc cô lập JVM test.
- **Concurrency:** chủ động mô phỏng hai request có locale khác nhau để xác nhận pipeline tường minh không dựa trên việc thay đổi global default.

Đừng viết test dựa trên một số định dạng ngày/tháng hoặc ký tự phân cách sẽ giữ nguyên tuyệt đối qua mọi nhà cung cấp dữ liệu locale. Nếu cần kiểm thử chính xác chuỗi hiển thị, cố định phiên bản runtime/locale provider hoặc kiểm thử trên tập môi trường đã cam kết.

## 10. Quy tắc ghi nhớ

**`Locale.setDefault` là thiết lập mặc định toàn JVM, và `setDefault(Category, Locale)` là thiết lập mặc định toàn JVM nhưng giới hạn theo category. Không có phiên bản nào của hai lời gọi này tự tạo một locale riêng cho từng request/thread.**

Với chương trình một ngôn ngữ, cấu hình mặc định một lần lúc khởi động có thể phù hợp. Với API, server đa người dùng, công việc đồng thời và thư viện dùng chung, hãy truyền **`Locale` tường minh** ở ranh giới trình bày, xác định `ZoneId` riêng và tránh dùng default locale như trạng thái biến đổi theo người dùng.

**Tài liệu tham khảo:**

- Java SE 17 `Locale`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html
- Java SE 17 `Locale.Category`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.Category.html
- Java SE 17 `NumberFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html
- Java SE 17 `ResourceBundle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html
