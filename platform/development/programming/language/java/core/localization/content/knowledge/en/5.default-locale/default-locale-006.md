# Ảnh hưởng của thời điểm tạo formatter và bộ nhớ đệm

Trong Java, khi một API định dạng **không nhận `Locale` tường minh**, nó thường lấy locale mặc định **tại thời điểm tạo đối tượng formatter**. Nếu sau đó ứng dụng đổi locale mặc định, các formatter đã tạo thường **không tự đổi theo**, còn các formatter tạo mới có thể dùng giá trị mới. Bộ nhớ đệm (cache) khiến hành vi này dễ bị hiểu nhầm: đối tượng cũ tiếp tục được tái sử dụng dù cấu hình hiện tại đã khác.

Đây là một chủ đề quan trọng của **Locale mặc định**: phải biết **khi nào locale được chọn, ai giữ formatter, cache được đánh chỉ mục bằng gì và thay đổi nào cần làm mới cache**.

> **Nguyên tắc thực hành:** Chọn locale của request/người dùng một cách tường minh rồi truyền vào formatter. Không dùng thao tác đổi locale mặc định của JVM như cách chuyển ngôn ngữ cho từng request, và không cache formatter mutable để nhiều thread dùng đồng thời.

## 1. Phân biệt bốn thời điểm

Giả sử ứng dụng có các bước:

1. **T1:** JVM đang có locale mặc định `en-US`.
2. **T2:** Ứng dụng tạo `NumberFormat` hoặc `DateTimeFormatter` mà không truyền locale.
3. **T3:** Một nơi khác gọi `Locale.setDefault(..., Locale.GERMANY)`.
4. **T4:** Ứng dụng dùng lại formatter cũ hoặc tạo formatter mới để hiển thị dữ liệu.

Ở T4, hai thao tác có thể cho kết quả khác nhau:

- **Dùng lại formatter tạo ở T2:** đối tượng đã giữ locale hoặc các quy tắc/thiết lập có liên quan; thay đổi default tại T3 không tự cấu hình lại đối tượng đó.
- **Tạo formatter mới tại T4:** lời gọi factory không truyền locale có thể đọc default mới nên cho định dạng Đức.

Đổi default **không phải lệnh “refresh mọi formatter đang tồn tại”**. Ngược lại, nếu truyền `Locale` vào lúc tạo thì hành vi không phụ thuộc vào default JVM được đặt khi nào.

| Đối tượng hoặc thao tác | Thời điểm ảnh hưởng của default | Ghi chú |
| --- | --- | --- |
| `NumberFormat.getNumberInstance()` | Khi factory được gọi | Tạo formatter theo default `FORMAT` lúc đó |
| `NumberFormat.getNumberInstance(locale)` | Không cần đọc default để chọn locale | Dùng locale tham số |
| `DateTimeFormatter.ofLocalizedDate(style)` | Locale mặc định được gắn khi tạo formatter | `getLocale()` quan sát được locale của formatter |
| `formatter.withLocale(locale)` | Khi gọi `withLocale` | Trả về **formatter mới** với locale được yêu cầu |
| `new SimpleDateFormat(pattern)` | Khi constructor chạy | Có thể nhận default về locale và múi giờ; đối tượng mutable |
| `ResourceBundle.getBundle(baseName)` | Khi lời gọi chọn locale mặc định | Bundle được cache độc lập theo cơ chế `ResourceBundle` |
| `Locale.getDefault(...)` | Ngay khi gọi | Đọc trạng thái mặc định hiện tại của JVM; không phải formatter |

Không nên suy diễn một quy tắc duy nhất cho **mọi thư viện**. API Java chuẩn và thư viện thứ ba có thể quyết định khác nhau về snapshot, lazy loading, cache, fallback và khả năng cấu hình lại.

## 2. Locale mặc định chung và locale mặc định theo category

Java có `Locale.getDefault()` và `Locale.getDefault(Locale.Category)`. Hai category đáng chú ý:

- `Locale.Category.FORMAT`: ngữ cảnh mặc định cho các dịch vụ định dạng như số, ngày giờ.
- `Locale.Category.DISPLAY`: ngữ cảnh mặc định cho tên hiển thị của locale, quốc gia, ngôn ngữ.

`Locale.setDefault(Locale)` thay đổi locale mặc định chung, đồng thời cập nhật các locale mặc định theo category theo hợp đồng của API. `Locale.setDefault(Locale.Category.FORMAT, locale)` thay đổi riêng mặc định của category `FORMAT`; việc đó không có nghĩa `getDefault()` không tham số hoặc category `DISPLAY` nhất thiết trả cùng giá trị.

**Cảnh báo phạm vi:** default locale là trạng thái **toàn JVM**, không phải biến cục bộ cho một người dùng hay một HTTP request. Thay đổi nó giữa lúc nhiều luồng đang tạo formatter có thể khiến luồng này dùng quy ước của luồng khác. Các ví dụ dưới đây chỉ dùng việc đổi default trong chương trình thử nghiệm khép kín và khôi phục default bằng `finally`.

## 3. Thí nghiệm chạy được: formatter cũ và formatter mới

Tạo tệp **`FormatterCreationTimeDemo.java`**:

~~~java
import java.text.NumberFormat;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class FormatterCreationTimeDemo {
    public static void main(String[] args) {
        Locale original = Locale.getDefault(Locale.Category.FORMAT);

        try {
            Locale.setDefault(Locale.Category.FORMAT, Locale.US);

            NumberFormat oldNumber = NumberFormat.getNumberInstance();
            DateTimeFormatter oldDate =
                    DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);

            Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);

            NumberFormat newNumber = NumberFormat.getNumberInstance();
            DateTimeFormatter newDate =
                    DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);

            System.out.println("Old date locale: "
                    + oldDate.getLocale().toLanguageTag());
            System.out.println("New date locale: "
                    + newDate.getLocale().toLanguageTag());

            System.out.println("Old number: " + oldNumber.format(1234.5));
            System.out.println("New number: " + newNumber.format(1234.5));
            System.out.println("Old number again: "
                    + oldNumber.format(1234.5));
        } finally {
            Locale.setDefault(Locale.Category.FORMAT, original);
        }
    }
}
~~~

Biên dịch/chạy bằng **Java 17+**:

~~~bash
javac FormatterCreationTimeDemo.java
java FormatterCreationTimeDemo
~~~

Trên JDK dùng dữ liệu định dạng thông dụng cho hai locale này, kết quả:

~~~text
Old date locale: en-US
New date locale: de-DE
Old number: 1,234.5
New number: 1.234,5
Old number again: 1,234.5
~~~

Hai dòng `getLocale().toLanguageTag()` chứng minh đối tượng `DateTimeFormatter` cũ vẫn giữ `en-US`, đối tượng mới giữ `de-DE`. Phần số minh họa sự khác biệt dấu thập phân/dấu nhóm giữa `Locale.US` và `Locale.GERMANY`. Dữ liệu locale/provider có thể biến đổi theo JDK, nên khi cần kiểm thử byte-by-byte phải cố định cả runtime và các phụ thuộc định dạng, không coi mọi chuỗi localized là hợp đồng bất biến toàn cầu.

**Diễn giải chính xác:** Lời gọi `Locale.setDefault` không hề “đổi nội dung” của `oldNumber` hoặc `oldDate`. Tại thời điểm T4, `oldNumber` vẫn dùng cấu hình trước đó; `newNumber` lấy cấu hình khác khi được tạo. Việc gọi `format` nhiều lần trên cùng formatter không nhất thiết tra lại locale mặc định.

## 4. `DateTimeFormatter`: immutable, tạo mới khi đổi locale

Với Java Time API (`java.time`), `DateTimeFormatter` là immutable và thread-safe. `withLocale`, `withZone`, `withChronology` và các phương thức tương tự trả về formatter được cấu hình mới, không sửa formatter gốc.

Ví dụ đoạn mã đặt trong một phương thức Java:

~~~java
Locale vietnamese = Locale.forLanguageTag("vi-VN");

DateTimeFormatter base =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);

DateTimeFormatter forVietnam = base.withLocale(vietnamese);

System.out.println(forVietnam.getLocale().toLanguageTag());
~~~

Cần import `java.util.Locale`, `java.time.format.DateTimeFormatter` và `java.time.format.FormatStyle`. Dòng kết quả:

~~~text
vi-VN
~~~

Ngay cả khi `base` được tạo dưới default `en-US`, `forVietnam` có locale `vi-VN`. Trong dịch vụ nhiều người dùng, cách rõ ràng hơn là truyền locale người dùng tại lớp gọi:

~~~java
String formatDate(java.time.LocalDate date, Locale locale) {
    DateTimeFormatter formatter =
            DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                    .withLocale(locale);
    return formatter.format(date);
}
~~~

Đây là **phương thức minh họa**, cần đặt trong class với các import thích hợp; không phải chương trình Java độc lập. Nó không phụ thuộc vào việc một luồng khác vừa đổi default JVM.

### Hai điều không nên nhầm

1. **Formatter có locale** và **dữ liệu locale dùng để diễn giải mẫu localized** là hai tầng. Formatter giữ lựa chọn locale, còn JDK/provider cung cấp mẫu, tên tháng, ký hiệu. Một số chi tiết triển khai có thể được tra cứu hoặc cache khi formatter hoạt động; điều đó không biến default mới thành locale mới của formatter cũ.
2. **`withLocale` không phải lệnh dịch tất cả chuỗi trong ứng dụng.** Nó điều chỉnh formatter. Bản dịch thông điệp giao diện phải được lấy từ tài nguyên i18n, còn múi giờ, tiền tệ và lịch có thể cần cấu hình riêng.

## 5. `NumberFormat` và `SimpleDateFormat`: trạng thái mutable

Khác với `DateTimeFormatter`, những formatter cũ như `java.text.NumberFormat`, `DecimalFormat` và `SimpleDateFormat` có trạng thái thay đổi được. Chúng có thể giữ ký hiệu, pattern, số chữ số thập phân, chế độ làm tròn hoặc múi giờ, tùy lớp và cách cấu hình.

Ví dụ `NumberFormat` có các setter:

~~~java
NumberFormat number = NumberFormat.getNumberInstance(Locale.US);
number.setGroupingUsed(false);
number.setMinimumFractionDigits(2);
number.setMaximumFractionDigits(2);
System.out.println(number.format(1234.5));
~~~

Đây là **đoạn mã trong phương thức** có `import java.text.NumberFormat;` và `import java.util.Locale;`. Kết quả:

~~~text
1234.50
~~~

Dù sau đó default JVM chuyển sang `Locale.GERMANY`, đối tượng `number` vẫn giữ những thuộc tính đã đặt. Thay đổi default không được thiết kế để thay thế lời gọi setter hoặc tái cấu hình đối tượng đang tồn tại.

**Thread safety:** `NumberFormat` và `SimpleDateFormat` không bảo đảm an toàn khi nhiều luồng cùng truy cập một instance. Đặt chúng trong cache toàn cục và dùng chung có thể gây lỗi dữ liệu/race ngay cả khi **mọi** request đều dùng cùng locale. Các cách an toàn thường là:

- Tạo instance mới trong phạm vi một request/phép định dạng.
- Dùng cơ chế đồng bộ khi bắt buộc chia sẻ, có đánh giá hiệu năng.
- Dùng cache **cấu hình bất biến hoặc factory**, rồi tạo bản formatter mutable riêng khi sử dụng.
- Với ngày giờ, ưu tiên `DateTimeFormatter` immutable và có thể cache an toàn.

Không nên sửa `Locale.setDefault` để “sửa thread safety” của formatter: đây là hai vấn đề hoàn toàn khác nhau.

## 6. Bộ nhớ đệm làm hành vi phụ thuộc thời điểm rõ hơn

Trong ứng dụng Java, có thể tồn tại nhiều cache khác nhau:

| Tầng | Ví dụ | Điều cần lưu ý |
| --- | --- | --- |
| **Cache do ứng dụng tạo** | `static Map<Locale, DateTimeFormatter>` | Key, thời điểm tạo, chính sách vô hiệu hóa do ứng dụng sở hữu |
| **Cache thư viện/framework** | Cache formatter, message catalog, template đã biên dịch | Phụ thuộc tài liệu và cấu hình thư viện |
| **Cache trong dịch vụ JDK** | Dữ liệu/pattern/locale provider mà JDK tái sử dụng | Không có hợp đồng chung rằng đổi default sẽ xóa mọi cache |
| **Cache tài nguyên `ResourceBundle`** | Bundle theo base name, locale, class loader/module | Có API cache/clear riêng, khác cache formatter |
| **Cache kết quả đã định dạng** | Chuỗi tiền/ngày gắn với bản ghi | Key phải phản ánh locale và các tham số định dạng |

Cần tách **hai câu hỏi**:

1. Cache đang lưu **formatter** hay **chuỗi kết quả**?
2. Cache key đã phản ánh tất cả thông tin khiến đầu ra thay đổi chưa?

Ví dụ một `Map<String, String>` cache HTML của giao diện nếu key chỉ là mã sản phẩm sẽ có thể phục vụ phiên bản tiếng Việt cho người dùng tiếng Anh. Cache key có thể cần `productId + effectiveLocale + currency + zone + version` tùy nội dung thực tế. Nếu format chỉ là số thuần túy thì `ZoneId` không cần thiết; chọn đúng những chiều dữ liệu có ảnh hưởng, tránh khóa thừa.

### Cache formatter theo locale

Sai về mặt thiết kế:

~~~java
// Ví dụ chống chỉ định trong dịch vụ nhiều người dùng.
static final NumberFormat SHARED =
        NumberFormat.getNumberInstance();
~~~

Vấn đề gồm cả **snapshot** của default khi class được khởi tạo lẫn **mutable / không thread-safe** khi nhiều request gọi cùng một `SHARED`. Khi default đổi, `SHARED` không trở thành formatter mới theo locale khác.

Cũng dễ sai:

~~~java
// Cache chỉ có một phần tử, nhưng đầu ra phụ thuộc locale.
static DateTimeFormatter cached =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG);
~~~

Đối tượng `cached` là immutable và thread-safe, nhưng nếu dùng nó cho người dùng từ nhiều locale mà không thay locale, tất cả sẽ nhìn thấy định dạng theo locale được bắt tại thời điểm khởi tạo. **Thread-safe không có nghĩa là đúng ngữ cảnh người dùng.**

Thiết kế tốt hơn: cache các formatter **immutable** theo locale được chọn tường minh; đồng thời đưa các tùy chọn ảnh hưởng khác vào key nếu cần.

## 7. Ví dụ runnable: cache `DateTimeFormatter` đúng theo locale

Tạo tệp **`LocaleAwareFormatterCache.java`**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class LocaleAwareFormatterCache {
    private static final ConcurrentMap<Locale, DateTimeFormatter> CACHE =
            new ConcurrentHashMap<>();

    public static String format(LocalDate date, Locale locale) {
        DateTimeFormatter formatter = CACHE.computeIfAbsent(
                locale,
                requested -> DateTimeFormatter
                        .ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(requested)
        );
        return formatter.format(date);
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 12, 31);
        Locale original = Locale.getDefault(Locale.Category.FORMAT);

        try {
            String first = format(date, Locale.US);

            Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);

            String second = format(date, Locale.US);
            System.out.println(first.equals(second));
            System.out.println(CACHE.size());
        } finally {
            Locale.setDefault(Locale.Category.FORMAT, original);
        }
    }
}
~~~

~~~bash
javac LocaleAwareFormatterCache.java
java LocaleAwareFormatterCache
~~~

Kết quả:

~~~text
true
1
~~~

Giải thích:

- `computeIfAbsent` chỉ tạo formatter mới cho locale chưa có trong map; key được đưa vào `withLocale(requested)`.
- Cả hai lần đều dùng `Locale.US`, do đó kết quả của cùng ngày không đổi chỉ vì default `FORMAT` của JVM chuyển sang Đức.
- Cache có đúng một entry `Locale.US`. Vì formatter là immutable, có thể chia sẻ instance đó giữa các thread.

**Giới hạn ví dụ:** Trong hệ thống thật, nếu cache theo locale do người dùng tự gửi không giới hạn, có thể cần kiểm tra locale có được ứng dụng hỗ trợ và đặt giới hạn kích thước cache. Nếu tạo formatter khác nhau theo `FormatStyle`, `ZoneId`, `Chronology`, cấu hình pattern hay cách đánh số, một key chỉ có `Locale` chưa đủ cho mọi nhu cầu.

Không cần cache formatter chỉ để tránh viết một dòng `withLocale`. Trước khi thêm cache, đo chi phí thực tế; một cache vô hạn và sai key có thể gây nhiều lỗi hơn phần hiệu năng tiết kiệm được.

## 8. `ResourceBundle` có bộ nhớ đệm riêng

`ResourceBundle` là cơ chế lấy thông điệp được địa phương hóa, **không phải formatter số hoặc ngày**. Nó có bộ nhớ đệm của riêng mình.

Giả sử có các tệp trên classpath:

~~~text
Messages.properties
Messages_en.properties
Messages_vi.properties
~~~

Với code:

~~~java
ResourceBundle messages = ResourceBundle.getBundle("Messages");
~~~

Lời gọi **không có tham số locale** chọn locale mặc định tại thời điểm thực hiện lời gọi (theo quy tắc `ResourceBundle`). Đối tượng `messages` đã được giữ lại không tự chuyển sang bundle ngôn ngữ mới chỉ vì default sau đó thay đổi.

Trái lại:

~~~java
ResourceBundle messages =
        ResourceBundle.getBundle("Messages", requestedLocale);
~~~

Đoạn mã thứ hai **truyền locale rõ ràng** (biến `requestedLocale` phải được khai báo ở nơi sử dụng), nên giảm phụ thuộc vào default lúc gọi. Tuy nhiên `ResourceBundle` có cơ chế lựa chọn ứng viên và fallback riêng; nếu locale yêu cầu không có bundle đủ phù hợp, lựa chọn fallback có thể bao gồm locale mặc định JVM hoặc bundle gốc tùy trường hợp. Muốn bảo đảm chính sách sản phẩm, hãy kiểm thử chuỗi fallback và tài nguyên thực tế.

### Cập nhật tệp dịch có làm cache tự thay đổi?

Không nhất thiết. Với cơ chế mặc định, `ResourceBundle` có thể giữ bundle trong cache. Java hỗ trợ `ResourceBundle.clearCache()` và `ResourceBundle.clearCache(ClassLoader)`, nhưng việc gọi các hàm này chỉ tác động đến cache của `ResourceBundle` theo hợp đồng API: nó **không** xóa mọi cache trong framework hay những biến ứng dụng đang giữ tham chiếu đến bundle cũ.

Nếu cần reload động, có thể dùng `ResourceBundle.Control` (trong những ngữ cảnh API hỗ trợ), thiết kế TTL/reload rõ ràng, hoặc cơ chế catalog của framework đang dùng. Lựa chọn này phải tương thích class loader/module và cách triển khai tài nguyên thực tế. **Đổi default locale không phải giải pháp tự động reload bản dịch.**

### Ví dụ kiểm chứng lựa chọn bundle theo thời điểm gọi

Giả sử cùng thư mục có hai tệp UTF-8:

**`Messages_en.properties`:**

~~~properties
greeting=Hello
~~~

**`Messages_vi.properties`:**

~~~properties
greeting=Xin chào
~~~

Tệp **`BundleCreationTimeDemo.java`**:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleCreationTimeDemo {
    public static void main(String[] args) {
        Locale original = Locale.getDefault();

        try {
            Locale.setDefault(Locale.ENGLISH);
            ResourceBundle oldBundle =
                    ResourceBundle.getBundle("Messages");

            Locale.setDefault(Locale.forLanguageTag("vi"));
            ResourceBundle newBundle =
                    ResourceBundle.getBundle("Messages");

            System.out.println(oldBundle.getString("greeting"));
            System.out.println(newBundle.getString("greeting"));
            System.out.println(oldBundle.getString("greeting"));
        } finally {
            Locale.setDefault(original);
        }
    }
}
~~~

~~~bash
javac BundleCreationTimeDemo.java
java -cp . BundleCreationTimeDemo
~~~

Kết quả:

~~~text
Hello
Xin chào
Hello
~~~

Khi ngôn ngữ mặc định thay đổi, lời gọi `getBundle` thứ hai có thể lấy một bundle khác, dù JDK vẫn sử dụng cache để tối ưu. Tham chiếu `oldBundle` trong chương trình không bị thay thế. Khả năng reload của bundle và khả năng thay lựa chọn theo default là **hai hành vi khác nhau**.

Trong môi trường nhiều người dùng, nên truyền locale tường minh vào `getBundle`, không xoay default toàn JVM ở mỗi request.

## 9. Múi giờ mặc định: một nguồn phụ thuộc thời điểm khác

Với ngày giờ, **locale** quyết định văn phong/mẫu địa phương hóa, còn **time zone** quyết định cách diễn giải thời điểm trên trục thời gian thành giờ địa phương. Đổi default locale không làm thay đổi thời gian thực tế của `Instant`, và đổi default time zone không phải thao tác chọn ngôn ngữ.

Các API date/time cũ như `DateFormat`/`SimpleDateFormat` có thể lấy múi giờ mặc định **khi khởi tạo**. Một formatter được lưu lâu có thể tiếp tục giữ múi giờ đã cấu hình, dù mặc định của JVM thay đổi sau đó. Vì vậy cache key của một formatter hoặc kết quả hiển thị thời điểm có thể cần `ZoneId` ngoài `Locale`.

Với Java Time, nên chuyển `Instant` hoặc `ZonedDateTime` bằng zone được người dùng/ứng dụng chọn và dùng `DateTimeFormatter` có locale tường minh:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class ExplicitContextDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2024-01-01T00:00:00Z");
        ZoneId zone = ZoneId.of("Asia/Tokyo");
        Locale locale = Locale.US;

        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                        .withLocale(locale)
                        .withZone(zone);

        System.out.println(formatter.getLocale().toLanguageTag());
        System.out.println(formatter.getZone().getId());
        System.out.println(instant.atZone(zone).getHour());
    }
}
~~~

~~~bash
javac ExplicitContextDemo.java
java ExplicitContextDemo
~~~

Kết quả chính xác:

~~~text
en-US
Asia/Tokyo
9
~~~

Mã tách rõ ba thành phần: **thời điểm** `Instant`, **vùng giờ** `ZoneId` và **ngữ cảnh hiển thị** `Locale`. `formatter` trong ví dụ có cấu hình zone và locale tường minh; việc gọi `format(instant)` sau đó sẽ theo cấu hình ấy chứ không cần đọc default JVM mới.

## 10. Khi nào cache phải được vô hiệu hóa?

Một cache chỉ đúng khi **đầu vào có thể thay đổi kết quả** được phản ánh trong key và dữ liệu cache vẫn hợp lệ.

**Trường hợp A — Chỉ đổi default JVM, formatter cache theo locale tường minh.** Nếu lời gọi và key đã chứa `Locale.US`, không cần xóa cache chỉ vì default JVM đổi từ `en-US` sang `de-DE`. Đó chính là lợi ích của loại bỏ phụ thuộc ngầm.

**Trường hợp B — Cache formatter tạo bằng default mà key không có locale.** Đây là thiết kế dễ sai: đổi default xong vẫn nhận formatter cũ. Sửa **cách tạo và đánh key**, không dựa vào thao tác clear cache rời rạc. Sau khi sửa thiết kế, xóa/rebuild những entry cũ không phản ánh locale.

**Trường hợp C — Người dùng đổi locale đã lưu.** Cache kết quả render/HTML/message theo người dùng phải dùng locale hiệu lực mới trong key hoặc bị vô hiệu hóa phù hợp. Nếu không, có thể thấy kết quả cũ mặc dù formatter mới được tạo đúng.

**Trường hợp D — Bản dịch hoặc quy tắc ứng dụng được cập nhật.** Cache thông điệp/kết quả cần version hoặc chính sách reload rõ ràng. `ResourceBundle.clearCache` chỉ xử lý phần cache do `ResourceBundle` quản lý.

**Trường hợp E — Nâng JDK, thư viện CLDR/provider, dữ liệu tzdb hoặc cấu hình định dạng.** Chất lượng/hình thức đầu ra có thể đổi. Cần kiểm thử hồi quy và xây lại cache dữ liệu đã định dạng nếu sản phẩm đòi hỏi phản ánh quy tắc mới. Nhiều cache nội bộ runtime không có API “xóa tất cả” công khai; thông thường triển khai phiên bản runtime mới là một ranh giới khởi tạo mới.

Nếu cache lưu kết quả định dạng, một key có thể gồm `value`, `locale`, `formatOptions`, `currency`, `zone`, `catalogVersion` khi các yếu tố ấy thực sự tác động lên kết quả. Nếu cache lưu `DateTimeFormatter`, key thường gồm locale, style/pattern và các cấu hình của formatter. **Không có một cache key chung phù hợp mọi ứng dụng.**

## 11. Đồng thời, tính nhất quán và chống rò rỉ ngữ cảnh

Hãy xét một server có hai HTTP request chạy song song:

~~~text
Request A (vi-VN): setDefault(vi-VN) --- tạo formatter --- format
Request B (en-US):       setDefault(en-US) --- tạo formatter --- format
~~~

Thời điểm xen kẽ của hai request không kiểm soát được. Request A có thể tạo formatter **sau khi** B đã đổi default thành `en-US`. Vấn đề xảy ra ngay cả khi không dùng cache. Thêm cache không sửa được race này và có thể làm một lỗi nhất thời tồn tại lâu hơn.

Lựa chọn an toàn hơn:

~~~text
Request A (vi-VN) → Locale A → formatter/cache key vi-VN → kết quả A
Request B (en-US) → Locale B → formatter/cache key en-US → kết quả B
~~~

- Locale là dữ liệu của request hoặc ngữ cảnh người dùng, được truyền tường minh tới lớp định dạng.
- Formatter immutable có thể dùng chung theo key phù hợp.
- Formatter mutable cần instance riêng hoặc cơ chế đồng bộ rõ ràng.
- Không gọi `Locale.setDefault` trong đường xử lý request.
- Nếu framework có request-scoped locale context, cần hiểu phạm vi và cơ chế truyền ngữ cảnh qua tác vụ async/thread pool; không tự giả định biến theo thread luôn được kế thừa đúng.

**Ghi nhớ thêm:** một cache `ConcurrentHashMap` chỉ bảo đảm thao tác trên map an toàn giữa các thread; nó **không biến giá trị `NumberFormat` mutable bên trong thành thread-safe**.

## 12. Kiểm thử đúng vấn đề phụ thuộc thời điểm

Để kiểm tra hệ thống không phụ thuộc ngầm vào default JVM, có thể thiết kế các bài kiểm thử:

| Kiểm thử | Điều cần quan sát |
| --- | --- |
| Tạo formatter dưới default A, đổi default B, dùng lại formatter | Formatter cũ giữ cách định dạng/config đã tạo |
| Tạo formatter mới sau khi đổi default | API không truyền locale có thể chọn B |
| Truyền locale tường minh A, đổi default nhiều lần | Kết quả của cùng giá trị/formatter A vẫn ổn định |
| Cache theo `Locale`, truy cập đồng thời | Không trộn locale giữa các request |
| Cache formatter mutable dùng chung | Kiểm tra race; tốt nhất loại bỏ thiết kế này |
| Người dùng đổi ngôn ngữ | Cache nội dung trả về ngôn ngữ mới |
| Reload bundle/cập nhật message | Chính sách cache trả bản dịch đúng phiên bản |
| Đổi time zone hoặc cập nhật tzdb | Kết quả giờ địa phương phù hợp chính sách |
| Nâng JDK/provider | So sánh output định dạng quan trọng, đặc biệt ký tự Unicode và mẫu ngày |

### Để kiểm thử tái lập và không gây nhiễm giữa các bài

Trong chương trình Java chạy độc lập, có thể lưu default trước thử nghiệm và khôi phục trong `finally`. Tuy nhiên nếu test suite chạy **song song trong cùng JVM**, việc đổi default vẫn có thể ảnh hưởng các test khác trước khi `finally` được thực thi. Hãy cân nhắc chạy những test cần đổi default trong process JVM riêng hoặc tuần tự có cô lập, và ưu tiên test logic bằng cách truyền locale tường minh.

Nếu cần assert chuỗi localized **chính xác**, phải xác định phiên bản JDK, locale provider và dữ liệu phụ thuộc. Đừng chỉ so sánh các dấu cách trông giống nhau: ký tự dấu cách thường (`U+0020`), non-breaking space (`U+00A0`) và narrow no-break space (`U+202F`) khác nhau. Trong kiểm thử nghiệp vụ, so sánh trường dữ liệu/locale được chọn có thể đáng tin hơn so với snapshot từng ký tự phụ thuộc CLDR.

## 13. Những hiểu nhầm thường gặp

1. **“Đổi `Locale.setDefault` là mọi formatter đang sống sẽ đổi ngôn ngữ.”** Sai: nhiều formatter giữ thiết lập từ lúc tạo.
2. **“Mỗi lần `format` đều xem lại default locale.”** Không có bảo đảm chung như vậy; thông thường formatter đã giữ lựa chọn locale/quy tắc.
3. **“Một `static final NumberFormat` sẽ tự cập nhật theo người dùng.”** Sai; lại còn mutable và không thread-safe.
4. **“`DateTimeFormatter` immutable nghĩa là luôn đúng locale.”** Sai; nó có thể an toàn khi chia sẻ mà vẫn mang locale sai.
5. **“Đổi default sẽ xóa cache JDK, framework và `ResourceBundle`.”** Không có hành vi xóa cache tổng quát như vậy.
6. **“`ResourceBundle.clearCache()` làm thay đổi các đối tượng bundle cũ đang được giữ.”** Sai: xóa entry cache không thay thế tham chiếu mà ứng dụng đã lưu.
7. **“Dùng `ConcurrentHashMap<Locale, NumberFormat>` thì formatter thread-safe.”** Sai: map an toàn không làm giá trị mutable trở thành an toàn.
8. **“Locale và múi giờ là một.”** Sai: cả hai có thể ảnh hưởng hiển thị, nhưng quyết định những phần khác nhau.
9. **“Cache theo một locale là đủ cho mọi định dạng.”** Có thể thiếu style, pattern, zone, tiền tệ, chronology và các tùy chọn khác.
10. **“Thêm `synchronized` quanh `Locale.setDefault` trong từng request giải quyết hết vấn đề.”** Không giải quyết được các thư viện/luồng khác đọc default ngoài cùng khóa, và vẫn để sót ngữ cảnh ngầm toàn JVM.

## 14. Cách áp dụng trong ứng dụng Java

Một kiến trúc thực tế thường đi theo thứ tự:

1. **Nhận và xác thực locale của người dùng** bằng danh sách locale sản phẩm hỗ trợ; có fallback công khai.
2. **Lựa chọn locale hiệu lực** ngay tại ranh giới request/use case.
3. **Truyền `Locale` tường minh** vào các formatter và hệ thống thông điệp; truyền múi giờ, tiền tệ và các tùy chọn độc lập khi cần.
4. **Cache `DateTimeFormatter` immutable theo key đủ thông tin** nếu có lợi ích rõ; với `NumberFormat` mutable, tạo instance riêng cho phạm vi sử dụng.
5. **Không đổi locale mặc định toàn JVM trong đường xử lý đa người dùng.**
6. **Quản lý cache nội dung và bundle bằng chính sách riêng**, có version/reload khi cập nhật bản dịch hoặc quy tắc.
7. **Kiểm thử việc đổi ngữ cảnh và các request đồng thời**, không chỉ kiểm thử trên một default cố định lúc JVM khởi động.

### Câu hỏi tự kiểm tra

**1.** Đã tạo `NumberFormat.getNumberInstance()` khi default là `en-US`. Sau đó đổi default `de-DE`. Lời gọi `format` trên đối tượng cũ có tự chuyển sang `de-DE` không?

**Đáp án:** Không; formatter cũ giữ cấu hình tạo trước. Muốn định dạng Đức, tạo formatter mới đúng locale hoặc chủ động cấu hình formatter phù hợp.

**2.** Một `static final DateTimeFormatter` an toàn cho nhiều thread có phải là lựa chọn tốt cho mọi locale?

**Đáp án:** Chưa đủ; nó an toàn về truy cập nhưng có thể mang duy nhất locale đã được chọn khi tạo. Dùng `withLocale` hoặc cache theo locale cụ thể.

**3.** Tại sao `ResourceBundle.clearCache()` không bảo đảm giao diện lập tức đổi toàn bộ bản dịch?

**Đáp án:** Ứng dụng có thể vẫn giữ bundle cũ, kết quả HTML đã cache hoặc cache của framework khác. Phải quản lý từng tầng.

**4.** Nếu trong một JVM có người dùng `vi-VN` và `en-US` đồng thời, vì sao không dùng `Locale.setDefault` cho mỗi request?

**Đáp án:** Default là trạng thái chia sẻ; hai luồng có thể xen kẽ khi đọc/ghi và tạo formatter sai locale. Truyền locale của từng request là cách kiểm soát đúng.

**5.** Khi cache chuỗi ngày giờ đã hiển thị, ngoài locale còn có yếu tố nào có thể ảnh hưởng?

**Đáp án:** Giá trị thời gian, zone, style/pattern, chronology và phiên bản dữ liệu định dạng, tùy trường hợp sử dụng.

**Ghi nhớ:** **Thời điểm tạo formatter quyết định phần quan trọng của cấu hình nó mang theo; cache có thể kéo dài tuổi thọ cấu hình đó.** Locale mặc định là trạng thái JVM, nên hệ thống nhiều người dùng cần chọn locale tường minh, key cache đủ ngữ cảnh và kiểm soát vòng đời formatter theo đặc tính immutable/mutable.