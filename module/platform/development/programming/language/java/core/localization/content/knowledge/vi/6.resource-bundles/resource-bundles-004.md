# ResourceBundle.getBundle và locale được yêu cầu

## 1. Vấn đề: yêu cầu một locale không có nghĩa là chắc chắn nhận đúng bundle của locale đó

Trong ứng dụng Java đa ngôn ngữ, ta thường lấy thông điệp từ `java.util.ResourceBundle`:

~~~java
Locale requested = Locale.forLanguageTag("en-US");
ResourceBundle bundle = ResourceBundle.getBundle("Labels", requested);
String message = bundle.getString("title");
~~~

Đây là một **đoạn mã minh họa**, đặt trong lớp/phương thức có import `java.util.Locale` và `java.util.ResourceBundle`.

Tham số `requested` xác định **locale mà ứng dụng muốn sử dụng** để tìm tài nguyên. Nó **không bảo đảm** bundle được trả về mang chính xác locale ấy. Nếu file tương ứng không tồn tại, `ResourceBundle` có thể tìm đến mức ngôn ngữ, bundle gốc hoặc locale mặc định của JVM tùy điều kiện và cơ chế fallback.

Hai khái niệm cần phân biệt ngay:

- **Requested locale (locale được yêu cầu):** `Locale` truyền vào `getBundle(baseName, locale)`, ví dụ `en-US`.
- **Resolved bundle locale (locale thực tế của bundle trả về):** giá trị `bundle.getLocale()` sau khi Java tìm tài nguyên, có thể là `en-US`, `en`, một locale fallback khác, hoặc `Locale.ROOT`.

Ngoài ra, một bundle đã được chọn có thể **thừa kế khóa** từ bundle cha. Vì vậy `bundle.getLocale()` cho biết locale của **bundle kết quả**, không nhất thiết cho biết file chứa **từng giá trị khóa** mà `getString(key)` trả về.

Đây là điểm quan trọng nhất khi debug giao diện bị hiện lẫn ngôn ngữ: phải kiểm tra cả locale được yêu cầu, locale giải quyết cuối cùng, đường fallback và khóa thực tế được tìm thấy.

## 2. Các overload phổ biến của `ResourceBundle.getBundle`

| Lời gọi | Locale sử dụng | Khi nào phù hợp |
| --- | --- | --- |
| `ResourceBundle.getBundle("Labels")` | Locale mặc định qua `Locale.getDefault()` | Tiện cho ứng dụng đơn giản thật sự muốn dùng mặc định JVM |
| `ResourceBundle.getBundle("Labels", requested)` | Locale `requested` do người gọi chỉ định | Trường hợp thông dụng trong ứng dụng đa người dùng |
| `ResourceBundle.getBundle("Labels", requested, loader)` | Locale tường minh và `ClassLoader` tường minh | Khi cần kiểm soát nơi tìm tài nguyên trong ứng dụng classpath |
| `ResourceBundle.getBundle("Labels", requested, control)` | Locale tường minh với chính sách tải/fallback tùy chỉnh | Dùng trong ứng dụng **unnamed module / classpath** khi cần kiểm soát tìm kiếm |

`baseName` ở ví dụ là `Labels`. Nếu tài nguyên nằm trong package, base name là tên có dấu chấm, ví dụ `"com.example.i18n.Labels"` tương ứng đường dẫn `com/example/i18n/Labels.properties` trên classpath.

Các overload nhận `ResourceBundle.Control` có ràng buộc theo Java Platform Module System: trên **named module**, việc dùng overload có `Control` có thể ném `UnsupportedOperationException`. Đối với named module, cần tuân theo cơ chế module và `ResourceBundleProvider` khi muốn mở rộng cách tải; đừng sao chép nguyên mẫu `Control` classpath vào module và mặc định nó hoạt động.

**Nên chọn gì?** Khi biết locale người dùng, truyền nó tường minh: `getBundle("Labels", requested)`. Nhưng đây là **điểm bắt đầu tìm kiếm**, không phải lệnh "chỉ tải bundle khớp tuyệt đối".

## 3. Cách Java tìm bundle từ requested locale

Với cấu trúc tài nguyên phổ biến:

~~~text
src/main/resources/                  (ví dụ trong một project build)
├── Labels.properties                (bundle gốc)
├── Labels_en.properties             (tiếng Anh chung)
├── Labels_en_US.properties          (tiếng Anh tại Hoa Kỳ)
├── Labels_fr.properties             (tiếng Pháp chung)
└── Labels_fr_CA.properties          (tiếng Pháp tại Canada)
~~~

Khi được yêu cầu `en-US`, các ứng viên thông dụng được xét theo thứ tự từ cụ thể đến tổng quát:

~~~text
Requested: en-US
    |
    v
Labels_en_US
    |
    v
Labels_en
    |
    v
Labels (ROOT)
~~~

Tên bundle dùng **dấu gạch dưới** (`_`) cho các phần locale trong tên tài nguyên; language tag theo chuẩn **BCP 47** dùng **dấu gạch nối** (`-`), ví dụ `en-US`.

### Đường ứng viên là một phần của thuật toán, không phải toàn bộ fallback

Với quy tắc mặc định của `ResourceBundle.Control` trong môi trường classpath, Java có thể tìm bundle ứng viên theo language, script, country và variant; ví dụ tổ hợp có script có các mức `language_script_country`, `language_script` rồi các mức không có script. Một số locale có quy tắc đặc biệt; không nên tự định nghĩa thuật toán thành việc xóa tùy tiện từng đoạn thẻ.

Nếu **không tìm được một bundle theo các ứng viên đích ngoại trừ bundle gốc**, Java có thể tiếp tục thử **locale mặc định của JVM** trước khi chấp nhận bundle gốc đang chờ. Vì thế, dù `Labels.properties` tồn tại, yêu cầu `es-MX` vẫn có thể chọn `Labels_fr.properties` nếu locale mặc định hiện tại là tiếng Pháp và file ấy tồn tại.

Chính sách mặc định có hai nhóm hành vi khác nhau:

1. **Fallback giữa các ứng viên của requested locale**, ví dụ `en-US → en → ROOT`.
2. **Fallback sang default locale của JVM**, có thể xảy ra khi không tìm được bundle cụ thể phù hợp requested locale.

Đừng nhầm fallback về bundle cha trong lúc **tìm khóa** với fallback sang default locale trong lúc **chọn bundle**. Hai bước đó giải quyết hai vấn đề khác nhau.

### Cùng tên, khác định dạng tài nguyên

`ResourceBundle` mặc định có thể tải resource bundle từ lớp Java (thường kế thừa `ListResourceBundle`) hoặc từ tệp `.properties`. Trong classpath, khi cùng ứng viên có cả bản class và properties, chế độ mặc định ưu tiên định dạng class. Vì vậy nếu mã nguồn có `Labels_en.java` lẫn `Labels_en.properties`, cần biết chính xác file nào được tải.

Ví dụ phía dưới chỉ tạo các file `.properties` để dễ quan sát và không phải xử lý định dạng class.

## 4. Ví dụ đầy đủ: locale yêu cầu, locale trả về và thừa kế khóa

Đây là chương trình Java 17+ chạy độc lập trên classpath, có dữ liệu cố định để kiểm tra từng trường hợp.

### Bước 1 — tạo các file trong cùng thư mục

~~~text
demo/
├── BundleLocaleDemo.java
├── Labels.properties
├── Labels_en.properties
├── Labels_en_US.properties
└── Labels_fr.properties
~~~

Nội dung `Labels.properties` (bundle gốc):

~~~properties
title=Welcome
currency=Generic
help=Contact support
~~~

Nội dung `Labels_en.properties`:

~~~properties
title=Hello
~~~

Nội dung `Labels_en_US.properties`:

~~~properties
currency=USD
~~~

Nội dung `Labels_fr.properties`:

~~~properties
title=Bonjour
~~~

Ở cấu trúc này:

- Bundle gốc có đủ ba khóa `title`, `currency` và `help`.
- `Labels_en` ghi đè `title`, nhưng lấy `currency` và `help` từ cha khi cần.
- `Labels_en_US` chỉ ghi đè `currency`. Khóa `title` trong kết quả `en-US` có thể đến từ `Labels_en`.
- `Labels_fr` chỉ ghi đè `title`.
- Không có `Labels_en_AU` và không có `Labels_es` hay `Labels_es_MX`: đây là tình huống cố ý để kiểm thử fallback.

### Bước 2 — tạo `BundleLocaleDemo.java`

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleLocaleDemo {
    public static void main(String[] args) {
        Locale us = Locale.forLanguageTag("en-US");
        ResourceBundle usBundle = ResourceBundle.getBundle("Labels", us);

        System.out.println("US requested: " + us.toLanguageTag());
        System.out.println("US resolved: " + usBundle.getLocale().toLanguageTag());
        System.out.println("US title: " + usBundle.getString("title"));
        System.out.println("US currency: " + usBundle.getString("currency"));
        System.out.println("US help: " + usBundle.getString("help"));

        Locale australia = Locale.forLanguageTag("en-AU");
        ResourceBundle auBundle =
                ResourceBundle.getBundle("Labels", australia);

        System.out.println("AU requested: " + australia.toLanguageTag());
        System.out.println("AU resolved: "
                + auBundle.getLocale().toLanguageTag());
        System.out.println("AU title: " + auBundle.getString("title"));
        System.out.println("AU currency: " + auBundle.getString("currency"));
    }
}
~~~

Từ thư mục `demo/` chạy:

~~~bash
javac -encoding UTF-8 BundleLocaleDemo.java
java -cp . BundleLocaleDemo
~~~

Kết quả:

~~~text
US requested: en-US
US resolved: en-US
US title: Hello
US currency: USD
US help: Contact support
AU requested: en-AU
AU resolved: en
AU title: Hello
AU currency: Generic
~~~

### Phân tích từng kết quả

**Trường hợp `en-US`:**

- `getBundle("Labels", us)` nhận requested locale `en-US` và tìm được `Labels_en_US.properties`.
- `usBundle.getLocale()` trả `en-US`, vì đó là locale của bundle được chọn.
- `currency` có trong `Labels_en_US` nên là `USD`.
- `title` không có trong `Labels_en_US`; Java tìm ở bundle cha `Labels_en` và trả `Hello`.
- `help` không có trong hai bundle trên nhưng có ở `Labels.properties`, nên trả `Contact support`.

**Trường hợp `en-AU`:**

- Không có `Labels_en_AU.properties`; Java tìm đến `Labels_en.properties`.
- `auBundle.getLocale()` là `en`, khác requested locale `en-AU`.
- `title` lấy từ `Labels_en` (`Hello`).
- `currency` không có tại `Labels_en` nên tìm được `Generic` ở bundle gốc.

Từ đó thấy rõ: **`getLocale()` phản ánh locale của bundle đã chọn; `getString()` có thể nhận dữ liệu từ bundle được chọn hoặc từ parent chain của nó.**

Không dùng `bundle.getLocale().equals(requested)` như một phép kiểm tra chắc chắn rằng *mọi khóa* đều có bản dịch ở cấp requested locale. Ngay cả khi `getLocale()` là `en-US`, khóa `title` ở ví dụ vẫn lấy từ bundle `en`.

## 5. Locale mặc định có thể ảnh hưởng đến `getBundle(baseName, requestedLocale)`

Nhiều lập trình viên tưởng rằng khi đã truyền `requested` thì locale mặc định hoàn toàn không liên quan. Điều đó **không đúng với chiến lược tìm kiếm mặc định** của `ResourceBundle`.

Giả sử requested locale là `es-MX`, nhưng chỉ có bundle gốc và các bundle Anh/Pháp như ví dụ trên. Nếu default locale là `fr-FR`, Java có thể tìm thấy `Labels_fr` qua fallback rồi trả nó trước bundle gốc.

Để minh họa có thể **chủ động thiết lập default locale trong một chương trình kiểm chứng đơn luồng**. Đoạn dưới đây là chương trình độc lập có cùng bốn file `Labels*.properties` từ mục 4. Không sử dụng `Locale.setDefault` như cơ chế chọn ngôn ngữ theo từng request trong ứng dụng đa luồng.

Tạo `DefaultFallbackDemo.java`:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class DefaultFallbackDemo {
    public static void main(String[] args) {
        Locale previous = Locale.getDefault();

        try {
            // Chỉ để minh họa fallback trong chương trình demo riêng.
            Locale.setDefault(Locale.FRANCE);

            Locale requested = Locale.forLanguageTag("es-MX");

            ResourceBundle ordinary =
                    ResourceBundle.getBundle("Labels", requested);

            System.out.println("Requested: " + requested.toLanguageTag());
            System.out.println("Default: "
                    + Locale.getDefault().toLanguageTag());
            System.out.println("Resolved: "
                    + ordinary.getLocale().toLanguageTag());
            System.out.println("Title: " + ordinary.getString("title"));

            ResourceBundle.Control noDefaultFallback =
                    ResourceBundle.Control.getNoFallbackControl(
                            ResourceBundle.Control.FORMAT_PROPERTIES
                    );
            ResourceBundle noFallback = ResourceBundle.getBundle(
                    "Labels", requested, noDefaultFallback
            );

            System.out.println("Without default fallback: "
                    + (noFallback.getLocale().equals(Locale.ROOT)
                            ? "ROOT"
                            : noFallback.getLocale().toLanguageTag()));
            System.out.println("Root title: " + noFallback.getString("title"));
        } finally {
            Locale.setDefault(previous);
        }
    }
}
~~~

Biên dịch/chạy trên classpath:

~~~bash
javac -encoding UTF-8 DefaultFallbackDemo.java
java -cp . DefaultFallbackDemo
~~~

Với bốn file tài nguyên của ví dụ, kết quả:

~~~text
Requested: es-MX
Default: fr-FR
Resolved: fr
Title: Bonjour
Without default fallback: ROOT
Root title: Welcome
~~~

**Tại sao?**

- Với lời gọi thông thường, hệ thống không tìm được bundle `es_MX` hay `es`. Bundle gốc có tồn tại nhưng có thể được tạm giữ trong giai đoạn chọn bundle; Java tiếp tục thử fallback `fr-FR` và tìm thấy `Labels_fr`. `getLocale()` của kết quả là `fr`.
- Với `ResourceBundle.Control.getNoFallbackControl(FORMAT_PROPERTIES)`, việc chuyển từ requested locale sang **default locale** bị vô hiệu hóa. Tuy nhiên, **fallback giữa candidate locales vẫn tồn tại**, và **bundle gốc vẫn có thể được chọn**. Vì vậy kết quả của requested `es-MX` là `ROOT` và khóa `title` trả `Welcome` từ `Labels.properties`.
- `Locale.setDefault(...)` là trạng thái toàn cục. Ví dụ hoàn nguyên giá trị cũ trong `finally` nhưng không khiến việc thay default trở nên an toàn trong chương trình đa luồng đang phục vụ request. Trong ứng dụng thực tế, hãy đặt locale yêu cầu theo ngữ cảnh, định nghĩa chính sách fallback ở tầng ứng dụng và tránh thay default JVM cho người dùng cá nhân.

### “No fallback” không có nghĩa là “khớp chính xác hoặc lỗi”

Tên `getNoFallbackControl` có thể gây hiểu nhầm. Nó **không** loại bỏ việc tìm ứng viên ít cụ thể hơn (ví dụ `en-AU → en`) và **không** tự bỏ bundle gốc. Nó chỉ chặn phương án tìm kiếm bổ sung theo locale mặc định. Nếu yêu cầu chỉ chấp nhận bản dịch khớp chính xác, cần thiết kế quy tắc xác thực riêng (ví dụ kiểm tra tài nguyên được phân phối, locale giải quyết và các khóa bắt buộc), không chỉ dựa vào tên phương thức.

Ngoài ra, overload dùng `ResourceBundle.Control` chủ yếu dành cho môi trường **classpath/unnamed module**; trên named module có giới hạn đã nêu ở mục 2.

## 6. Đọc đúng thông tin khi debug

Khi nghi ngờ hệ thống hiển thị không đúng bản dịch, hãy kiểm tra theo trình tự sau:

| Cần xác minh | Cách kiểm tra | Kết luận có thể rút ra |
| --- | --- | --- |
| Locale người dùng yêu cầu | Ghi nhận `requested.toLanguageTag()` | Đầu vào lựa chọn ngôn ngữ/vùng |
| Bundle đã được chọn | `bundle.getLocale().toLanguageTag()` | Locale của bundle được tải, có thể là fallback |
| Bundle gốc | Kiểm tra `Labels.properties` trên classpath | Nơi cung cấp fallback cuối cho nhiều khóa |
| Khóa có tìm thấy không | `bundle.containsKey("title")` | Tồn tại trong bundle hoặc chuỗi cha, **không** chứng minh có trong bundle hiện tại |
| Giá trị hiển thị | `bundle.getString("title")` | Giá trị thực tế sau khi tìm qua parent chain |
| Tài nguyên đã đóng gói | Kiểm tra file `Labels_*.properties` trong classpath/JAR | Tránh nhầm file có trong source nhưng không nằm trong bản deploy |
| Locale mặc định và chính sách fallback | `Locale.getDefault()`, mã gọi `getBundle` và `Control` | Vì sao kết quả có thể chuyển sang locale khác |

Nếu muốn xem các khóa hiệu dụng, `bundle.keySet()` trả về tập hợp khóa của bundle và parent chain. Còn việc xác định **chính xác file nào cung cấp từng khóa** thường cần kiểm tra cấu trúc bundle hoặc instrument quá trình tải, bởi API `getString` công khai không trả một “source locale” cho từng giá trị.

Với bundle gốc, `bundle.getLocale()` có thể là `Locale.ROOT`. Khi gọi `Locale.ROOT.toLanguageTag()`, kết quả là `und` (*undetermined language*) chứ không phải chuỗi `"ROOT"`. Ví dụ trên dùng điều kiện `equals(Locale.ROOT)` để in nhãn `ROOT` dễ đọc.

### Hai loại thiếu dữ liệu cần phân biệt

**Thiếu cả bundle phù hợp:** nếu không có tài nguyên nào khả dụng theo chính sách tìm kiếm, `ResourceBundle.getBundle(...)` có thể ném `MissingResourceException`.

**Có bundle nhưng thiếu một khóa:** `getBundle(...)` có thể thành công, nhưng `bundle.getString("unknown.key")` ném `MissingResourceException` nếu khóa không tồn tại ở bundle và các parent. Đây là lỗi khác với việc chọn sai locale.

Đoạn kiểm tra an toàn khi chấp nhận fallback:

~~~java
try {
    ResourceBundle bundle =
            ResourceBundle.getBundle("Labels", requested);
    String value = bundle.getString("title");
    // Sử dụng value để hiển thị.
} catch (MissingResourceException ex) {
    // Báo hoặc xử lý lỗi theo chính sách nội dung của ứng dụng.
}
~~~

Đây là **mảnh mã trong phương thức**, yêu cầu import `java.util.Locale`/`java.util.ResourceBundle`/`java.util.MissingResourceException` và biến `requested` có sẵn. Đừng tự trả một thông điệp khác ngôn ngữ một cách im lặng nếu tính nhất quán của trải nghiệm là yêu cầu bắt buộc; cần có chính sách fallback có thể giám sát.

## 7. Các điểm tinh tế về cache, encoding và môi trường chạy

### 7.1. Cache không làm thay đổi ý nghĩa requested locale

`ResourceBundle` cache bundle đã tải để giảm chi phí I/O và tạo đối tượng. Khi thay đổi file `.properties` trong quá trình chạy, giá trị có thể chưa đổi vì cache. `ResourceBundle.clearCache()` hoặc phiên bản có `ClassLoader` có thể dùng trong công cụ/test khi cần xóa cache, nhưng **không nên gọi bừa trên mỗi request**: điều này tạo chi phí và ảnh hưởng các request khác. Việc hot-reload bản dịch thường cần thiết kế riêng.

Khi hệ thống dùng chiến lược tải khác nhau hoặc nhiều classloader, cache và cấu hình provider có thể tác động kết quả. Nếu định nghĩa `ResourceBundle.Control` tùy chỉnh, cần đọc kỹ quy tắc cache và nhất quán `getFormats`/`getCandidateLocales` theo tài liệu Java.

### 7.2. Encoding của `.properties`

Trong Java 9+ (bao gồm Java 17), `PropertyResourceBundle` đọc resource bundle `.properties` theo UTF-8 mặc định, với cơ chế dự phòng theo quy định của API trong một số trường hợp byte không hợp lệ. Hãy lưu các file bản dịch ở UTF-8, cấu hình quy trình build đóng gói đúng dữ liệu và kiểm thử chữ có dấu/Unicode. Đây là câu chuyện **encoding của tài nguyên**; `Locale` quyết định tìm phiên bản ngôn ngữ, không tự sửa byte dữ liệu sai encoding.

### 7.3. Classpath và named module

Ví dụ trong bài chạy bằng `javac`/`java -cp .` thuộc **unnamed module** (classpath), nên các overload với `ResourceBundle.Control` có thể dùng như minh họa. Nếu chuyển sang project Java module có `module-info.java`, việc tìm `ResourceBundle` phải tuân theo quy tắc đóng gói và khả năng truy cập tài nguyên của module. Đối với cơ chế provider tùy biến, xem `ResourceBundleProvider` và yêu cầu `uses`/`provides` của module tương ứng; không giả định rằng cách truyền `ClassLoader` hoặc `Control` giữ nguyên mọi hành vi.

### 7.4. ResourceBundle chọn nội dung, không thay mọi phép định dạng

`ResourceBundle` chủ yếu phục vụ chọn chuỗi/dữ liệu theo locale. Định dạng số, ngày, tiền và múi giờ có API riêng như `NumberFormat`, `DateTimeFormatter`, `Currency` và `ZoneId`. Nếu giao diện hiển thị câu từ bundle nhưng phần ngày giờ theo locale khác, kiểm tra các lời gọi định dạng riêng. Việc `getBundle("Labels", requested)` thành công không tự động đồng bộ toàn bộ formatter trong ứng dụng.

## 8. Thiết kế chính sách lựa chọn bản dịch cho ứng dụng thật

Khi người dùng yêu cầu một locale cụ thể, cần làm rõ sản phẩm cho phép fallback tới đâu:

1. **Fallback theo ngôn ngữ:** người dùng yêu cầu `en-AU` mà chỉ có `en`. Nếu nội dung được chấp nhận chung cho tiếng Anh, có thể dùng `Labels_en`.
2. **Fallback về ngôn ngữ mặc định của sản phẩm:** người dùng yêu cầu `es-MX` nhưng sản phẩm chưa có bản tiếng Tây Ban Nha. Sản phẩm có thể chủ đích hiển thị tiếng Anh, nhưng cần chọn và kiểm thử chính sách này, không phụ thuộc ngẫu nhiên default locale của server.
3. **Fallback về bundle gốc:** bảo đảm những khóa tối thiểu tồn tại ở `Labels.properties`. Tuy vậy, sự tồn tại của root không tự chứng minh toàn bộ giao diện sẽ dùng một ngôn ngữ duy nhất nếu vẫn có bản dịch từng phần ở bundle khác.
4. **Không cho phép fallback:** khi nội dung thuộc yêu cầu pháp lý, hợp đồng hoặc cần bản địa hóa hoàn chỉnh, xác nhận tài nguyên chính xác và các khóa bắt buộc trước khi hiển thị; nếu thiếu, hiển thị lỗi phù hợp hoặc điều hướng theo quy định sản phẩm.

**Gợi ý cho tầng service:** lưu cả `requestedLocale` và `resolvedLocale` khi cần theo dõi lỗi localization; không ghi log dữ liệu cá nhân nhạy cảm hoặc nội dung nhạy cảm chỉ để debug. Xây dựng unit test dựa trên tập file bundle kiểm soát được, với một default locale cố định tại cấp bộ kiểm thử hoặc bằng `Control` phù hợp, thay vì để môi trường CI vô tình quyết định kết quả.

## 9. Sai lầm phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Truyền `en-US` nghĩa là chắc chắn tải `Labels_en_US`.” | Đây là yêu cầu tìm kiếm; nếu thiếu có thể dùng `en`, default locale hoặc bundle gốc. |
| “`getLocale()` luôn bằng locale truyền vào.” | `getLocale()` phản ánh locale của bundle thực tế được chọn. |
| “`getLocale() == en-US` nên mọi khóa đều ở file `Labels_en_US`.” | `getString` tìm qua parent chain. |
| “Có root bundle thì không bao giờ fallback sang default locale.” | Với chiến lược mặc định, root có thể được tạm giữ trong khi thử default locale. |
| “`getNoFallbackControl` vô hiệu hóa mọi fallback.” | Chỉ vô hiệu hóa fallback tới default locale; vẫn có ứng viên ít cụ thể hơn và root. |
| “`containsKey` cho biết khóa chỉ nằm trong bundle hiện tại.” | Nó có thể tìm trong bundle hoặc parent. |
| “Thiếu một key sẽ khiến `getBundle` ném lỗi ngay.” | `getBundle` có thể trả bundle; lỗi xuất hiện khi gọi `getString` với khóa không có ở toàn bộ chuỗi tìm. |
| “Hai file class và properties cùng tên được ưu tiên như nhau.” | Trong chiến lược tải mặc định classpath, định dạng class được xét trước properties. |
| “Một app đa luồng có thể `Locale.setDefault` cho từng request rồi khôi phục.” | Default là trạng thái dùng chung, gây nguy cơ race. Truyền locale tường minh và định nghĩa fallback rõ. |

## 10. Bài tập tự kiểm tra

1. Với bốn file trong mục 4, giải thích vì sao `getBundle("Labels", Locale.US).getLocale()` trả `en-US` nhưng `getString("title")` lại là `Hello` từ file `Labels_en`.
2. Xóa tạm `Labels_en_US.properties` rồi chạy lại demo. Locale thực tế của bundle US là gì? `currency` được lấy từ đâu? Khôi phục file sau khi thử.
3. Chỉ thay default locale của chương trình demo kiểm chứng thành `Locale.JAPAN` nhưng không thêm `Labels_ja`. Với requested `es-MX`, điều gì xảy ra nếu vẫn có `Labels.properties`?
4. So sánh `getBundle("Labels", Locale.forLanguageTag("es-MX"))` với overload dùng `getNoFallbackControl(FORMAT_PROPERTIES)` khi default JVM là `fr-FR`. Giải thích vì sao kết quả có thể khác.
5. Thêm một khóa `footer` chỉ vào `Labels.properties`. `getString("footer")` khi requested `en-US` có hoạt động không? `getLocale()` sẽ thay đổi không?
6. Thiết kế test cho một sản phẩm yêu cầu **không dùng sai ngôn ngữ** khi thiếu bundle. Những thông tin nào cần xác minh ngoài việc `getBundle` không ném exception?

**Ghi nhớ:** `ResourceBundle.getBundle(baseName, requestedLocale)` bắt đầu tìm kiếm theo **locale được yêu cầu**, nhưng bundle trả về có thể thuộc **locale khác** theo cơ chế ứng viên và fallback. `bundle.getLocale()` xác định locale của bundle đã chọn, còn từng `getString(key)` có thể lấy khóa từ bundle cha. Hãy kiểm thử đường tìm kiếm, tài nguyên đóng gói và chính sách fallback của sản phẩm; tránh phụ thuộc ngẫu nhiên vào default locale của JVM.