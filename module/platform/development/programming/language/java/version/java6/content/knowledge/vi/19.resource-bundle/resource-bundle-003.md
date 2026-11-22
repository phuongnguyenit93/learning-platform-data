# Fallback và lựa chọn locale mặc định với ResourceBundle trong Java

## 1. Bài toán: yêu cầu một ngôn ngữ nhưng tài nguyên không đầy đủ

`java.util.ResourceBundle` là API Java SE hiện hành để chọn thông điệp/tài nguyên theo `Locale`. Ứng dụng có thể lưu lời chào, nhãn nút, lỗi kiểm tra dữ liệu hoặc nội dung tương tác trong nhiều bundle thuộc cùng một **family**. Khi người dùng chọn `fr-CA`, ứng dụng nên hiển thị tài nguyên Canada tiếng Pháp nếu có; những key chưa được dịch có thể lấy từ bundle tiếng Pháp chung rồi từ bundle gốc.

Nhưng chuyện gì xảy ra khi **không có bất kỳ bundle tiếng Đức nào** cho yêu cầu `de-DE` và JVM đang dùng locale mặc định `en-US`? Theo cơ chế tra cứu thông thường, `ResourceBundle` có thể **chọn bundle tiếng Anh** trước khi trả về bundle gốc. Đây là một fallback hoàn toàn khác với chuyện **một key bị thiếu** trong bundle tiếng Pháp đang chọn.

Để tránh nhầm lẫn, bài học tách bốn khái niệm:

- **Target/requested locale:** `Locale` mà code truyền cho `ResourceBundle.getBundle(baseName, locale)`, ví dụ `Locale.CANADA_FRENCH`.
- **JVM default locale:** giá trị `Locale.getDefault()`, thường được JVM lấy từ môi trường lúc khởi động; `getBundle(baseName)` sử dụng giá trị này khi không có đối số `Locale`.
- **Selected/actual bundle locale:** locale thực của bundle tìm được; xem bằng `bundle.getLocale()`. Nó **có thể khác cả requested lẫn default**.
- **Parent bundle chain:** chuỗi bundle dùng **để tìm một key** còn thiếu trong bundle đã chọn; ví dụ `Messages_fr_CA → Messages_fr → Messages`.

Hai kiểu fallback quan trọng không giống nhau:

1. **Fallback khi *chọn* bundle:** tìm các tên phù hợp target locale; nếu không có localized bundle, có thể tìm theo JVM default locale, và sau cùng mới dùng root bundle.
2. **Fallback khi *tra một key*:** sau khi có bundle, `getString(key)` tìm ở bundle ấy và các **parent** của nó; nó **không tự nhảy sang JVM default locale** chỉ vì key không tồn tại trong nhánh đã chọn.

Mục tiêu của một ứng dụng đa ngôn ngữ là lựa chọn target locale có chủ ý, có baseline root bundle rõ ràng và dự đoán được cả hai đường fallback.

## 2. Các API chính

| API | Vai trò |
| --- | --- |
| `Locale.getDefault()` | Lấy default locale chung của JVM |
| `Locale.setDefault(locale)` | Thay default locale chung của JVM; nên hạn chế dùng trong server nhiều user |
| `Locale.forLanguageTag("fr-CA")` | Tạo locale từ nhãn BCP 47 |
| `ResourceBundle.getBundle(baseName)` | Tra family theo default locale hiện tại |
| `ResourceBundle.getBundle(baseName, locale)` | Tra family theo target locale do caller chọn |
| `ResourceBundle.getBundle(baseName, locale, loader)` | Tra theo class loader chỉ định khi có lý do quản lý visibility |
| `ResourceBundle.getBundle(baseName, locale, module)` | Tra bundle nhân danh module chỉ định trong hệ thống JPMS |
| `ResourceBundle.getBundle(baseName, locale, control)` | Điều khiển cách chọn bundle trên **classpath/unnamed module** |
| `ResourceBundle.Control.getNoFallbackControl(formats)` | Ngăn fallback sang default locale, không bỏ các bundle cha/root |
| `ResourceBundle.getLocale()` | Cho biết **locale của bundle được chọn thực tế** |
| `ResourceBundle.getString(key)` | Lấy string bằng cơ chế tìm key trong bundle và parent chain |
| `ResourceBundle.containsKey(key)` | Kiểm tra key có thể tìm được trong bundle hoặc parent |
| `ResourceBundle.keySet()` | Tập các key có thể truy xuất, kể cả inherited keys |

Tất cả ví dụ chạy được dưới đây sử dụng **Java 17+** và các API vẫn tồn tại trong Java SE hiện hành. `ResourceBundle`, `Locale`, `PropertyResourceBundle` và `ResourceBundle.Control` đều thuộc module `java.base`; không cần dependency thư viện ngoài để chạy ví dụ classpath.

**Lưu ý tên package:** `java.util.ResourceBundle` chứa cơ chế lựa chọn bundle; `java.util.Locale` chứa định danh locale; `java.text.MessageFormat` hoặc `NumberFormat` giải quyết các bài toán **định dạng** nội dung khác, không thay thế công việc chọn bundle.

## 3. Một family có những file nào?

Ví dụ family `Messages` trên classpath:

~~~text
bundle-demo/
├── BundleFallbackDemo.java
├── Messages.properties
├── Messages_en.properties
├── Messages_fr.properties
└── Messages_fr_CA.properties
~~~

Những file này cùng có **base name** `Messages`; hậu tố thể hiện các locale có bản dịch:

| File | Locale của bundle | Chức năng |
| --- | --- | --- |
| `Messages.properties` | `Locale.ROOT` | Root bundle, tài nguyên chung/baseline |
| `Messages_en.properties` | `en` | Bản dịch tiếng Anh |
| `Messages_fr.properties` | `fr` | Bản dịch tiếng Pháp |
| `Messages_fr_CA.properties` | `fr-CA` | Bản dịch tiếng Pháp dùng tại Canada |
| `Messages_de.properties` | Không có trong demo | Dùng để kiểm thử fallback khỏi tiếng Đức |
| `Messages_en_US.properties` | Không có trong demo | Để thấy `en-US` chọn parent `en` |

Với bundle trong package `com.example.i18n`, base name là `com.example.i18n.Messages` và các file thường nằm trong đường dẫn classpath `com/example/i18n/Messages*.properties`. Tên bundle **không phải tên file gồm đuôi `.properties`**; phương thức `getBundle(...)` nhận tên family.

Không có yêu cầu phải tạo đủ mọi ngôn ngữ/quốc gia. Thực tế nên có root bundle chứa **toàn bộ key mặc định** và bổ sung những file locale-specific chỉ chứa phần bản dịch khác baseline. Đây là mẫu giúp giảm lặp, nhưng policy về ngôn ngữ dùng làm baseline phải rõ ràng.

Trong Java hiện đại, file `PropertyResourceBundle` được đọc theo UTF-8 mặc định (với hành vi tương thích encoding được JavaDoc mô tả). Ví dụ dùng giá trị ASCII để đầu ra có thể kiểm thử nhất quán. Khi lưu bản dịch tiếng Việt hoặc tiếng Pháp có dấu, nên sử dụng file UTF-8 và kiểm tra toolchain build không thay encoding.

## 4. Cơ chế thứ nhất: tìm bundle ứng với target locale

### 4.1. Candidate locales cho `fr-CA`

Khi gọi:

~~~java
ResourceBundle bundle =
        ResourceBundle.getBundle("Messages", Locale.CANADA_FRENCH);
~~~

Đây là **snippet trong chương trình** với import `ResourceBundle` và `Locale`. Với family/tập locale demo, các candidate điển hình theo thứ tự:

~~~text
Messages_fr_CA
Messages_fr
Messages
~~~

Các candidate này tương ứng:

~~~text
fr-CA -> fr -> root
~~~

Nếu `Messages_fr_CA.properties` tồn tại, nó được chọn làm **bundle chính**. `Messages_fr.properties` và `Messages.properties` có thể được liên kết làm **parent chain** để tìm key chưa có.

Nếu không có `Messages_fr_CA.properties` nhưng có `Messages_fr.properties`, `getBundle(...)` chọn `fr` và trả `bundle.getLocale()` tương ứng `fr`. Không cần sửa requested locale ở ứng dụng để đạt ngôn ngữ chung.

Thứ tự candidate không phải lúc nào cũng chỉ có dạng `language_country → language → root`. Đối với locale có script, variant hoặc một số locale đặc biệt, `ResourceBundle.Control.getCandidateLocales(...)` có quy tắc thứ tự chi tiết hơn, ví dụ tên có `language_script_country`. Khi cần kiểm tra trường hợp phức tạp như `zh-Hant-TW`, dùng API và JavaDoc thay vì tự ghép chuỗi bằng một quy tắc đơn giản.

### 4.2. Thấy root bundle chưa chắc đã kết thúc việc chọn bundle

Một chi tiết dễ nhầm: nếu không có localized bundle cho target nhưng có `Messages.properties`, mặc định Java **có thể giữ root làm lựa chọn dự phòng** rồi thử các localized bundle của JVM default locale **trước khi** quyết định dùng root.

Ví dụ:

~~~text
Target locale  = de-DE
JVM default    = en-US

Có: Messages.properties
Có: Messages_en.properties
Không: Messages_de_DE.properties
Không: Messages_de.properties
Không: Messages_en_US.properties
~~~

Đường tìm kiếm mặc định tương đương:

~~~text
Lượt target:
  Messages_de_DE -> không có
  Messages_de    -> không có
  Messages       -> có root, giữ dự phòng

Lượt fallback sang JVM default en-US:
  Messages_en_US -> không có
  Messages_en    -> có -> chọn bundle en
  Parent của en  -> Messages root

Kết quả:
  bundle.getLocale() = en
~~~

Do đó **`getBundle("Messages", Locale.GERMANY)` không bảo đảm chọn root chỉ vì thiếu file tiếng Đức**. Nếu JVM default `en-US` và có `Messages_en.properties`, tiếng Anh có thể là bundle được chọn.

Điều này hợp lý cho nhiều ứng dụng desktop có default locale được kiểm soát, nhưng có thể gây bất ngờ cho server nhiều tenant khi default locale của host không trùng ngôn ngữ dự phòng của từng user.

### 4.3. Khi đã tìm thấy localized bundle cho target

Nếu request `fr-CA` có `Messages_fr_CA` hoặc chí ít có `Messages_fr`, Java dùng nhánh phù hợp target và parent chain của nhánh ấy. Nó **không cần fallback sang locale mặc định `en-US`** chỉ vì một vài key trong nhánh `fr` không tồn tại.

Chính khác biệt này giải thích vì sao một bundle `fr-CA` vẫn có thể thiếu key `only_en` dù file `Messages_en.properties` có key ấy. Cơ chế tìm key được mô tả chi tiết ở mục 5.

## 5. Cơ chế thứ hai: tìm key trong parent chain

Giả sử nội dung file của ví dụ:

~~~properties
# Messages.properties
greeting=Base hello
shared=Base shared
~~~

~~~properties
# Messages_fr.properties
greeting=Bonjour
~~~

~~~properties
# Messages_fr_CA.properties
region=Quebec
~~~

Khi chương trình gọi `getBundle("Messages", Locale.CANADA_FRENCH)`, bundle đã chọn là `fr-CA`. Những lời gọi tiếp theo có nguồn dữ liệu khác nhau:

| Lời gọi | Giá trị | Lấy từ |
| --- | --- | --- |
| `bundle.getString("region")` | `Quebec` | `Messages_fr_CA` |
| `bundle.getString("greeting")` | `Bonjour` | `Messages_fr` (parent) |
| `bundle.getString("shared")` | `Base shared` | `Messages` (root parent) |

Theo JavaDoc, `ResourceBundle.getObject(key)` (và `getString`) tra bundle hiện tại; nếu key không có, nó tìm tiếp các **parent bundle**. Đó là **fallback theo key**.

Giờ giả sử file `Messages_en.properties` có:

~~~properties
greeting=Hello
only_en=English only
~~~

`fr-CA` không có `only_en`, `fr` cũng không có và root cũng không có. Khi gọi `frCa.getString("only_en")`, Java ném **`MissingResourceException`**. Nó **không tự chạy sang bundle `en`** vì `en` không thuộc parent chain của `fr-CA`.

**Kết luận:** “Tôi đã cấu hình default locale tiếng Anh” không đồng nghĩa “mọi key thiếu của tiếng Pháp sẽ tự động lấy bản tiếng Anh”. Muốn fallback **theo key** về một ngôn ngữ cụ thể, bạn phải thiết kế baseline root bundle hoặc một tầng lookup nghiệp vụ bổ sung.

### 5.1. Root bundle là fallback theo key dễ dự đoán nhất

Nếu root chứa mọi key bắt buộc và mỗi locale-specific file chỉ chứa những bản dịch riêng, việc tìm key tự động đi qua parent chain:

~~~text
locale-specific value (nếu có)
     |
     v
language-level value (nếu có)
     |
     v
root/default text
~~~

Không nên phân phối các key bắt buộc **chỉ** trong `Messages_en.properties` rồi mong ứng dụng tiếng Pháp lấy được chúng khi thiếu. Nếu fallback chuẩn của sản phẩm là tiếng Anh, một cách đơn giản là lưu nội dung baseline tiếng Anh ngay trong `Messages.properties`, hoặc xác định cơ chế fallback ứng dụng riêng và kiểm thử nó.

### 5.2. Kiểm tra sự tồn tại của key

`bundle.containsKey("greeting")` tính cả các bundle cha, không chỉ key khai báo trực tiếp tại file được chọn. `bundle.keySet()` cũng bao gồm key của parent chain.

Vì vậy, `containsKey(...)` **không chứng minh một bản dịch dành riêng cho locale này đã tồn tại**. Nếu muốn audit tỷ lệ dịch, cần đọc dữ liệu nguồn hoặc xây công cụ kiểm tra bản dịch theo từng file; việc đếm `keySet()` của bundle đã fallback sẽ đánh giá sai mức hoàn thiện bản địa hóa.

Nếu biết key có thể không tồn tại, xử lý `MissingResourceException` (hoặc `containsKey`) một cách rõ ràng; không catch chung mọi `RuntimeException` rồi im lặng trả chuỗi rỗng.

## 6. Locale mặc định của JVM: nó được lấy từ đâu và khi nào dùng?

### 6.1. `Locale.getDefault()` khác target locale tường minh

Java cung cấp:

~~~java
Locale defaultLocale = Locale.getDefault();
ResourceBundle automatic = ResourceBundle.getBundle("Messages");
~~~

`getBundle(baseName)` tương đương việc yêu cầu family bằng **default locale của JVM hiện tại**, về logic là `ResourceBundle.getBundle(baseName, Locale.getDefault())` trong caller module tương ứng. Default locale thường được xác định từ cấu hình hệ điều hành/môi trường khi JVM khởi động, và có thể thay đổi bởi code gọi `Locale.setDefault(...)`.

Mặt khác:

~~~java
Locale preferred = Locale.forLanguageTag("fr-CA");
ResourceBundle explicit = ResourceBundle.getBundle("Messages", preferred);
~~~

truyền thẳng preference của caller. **Tuy nhiên**, nếu preference này không có localized bundle, mặc định Java **vẫn có thể fallback tới JVM default locale**; truyền target locale không đồng nghĩa vô hiệu hóa fallback mặc định.

**Khuyến nghị:** Trong backend nhiều user, không dựa vào `Locale.getDefault()` để quyết định ngôn ngữ giao diện của mọi user. Chọn `Locale` cho từng request/session/user trước khi gọi `getBundle(...)`. Đồng thời phải định nghĩa rõ chính sách khi ngôn ngữ đó không có bundle.

### 6.2. Không sử dụng `Locale.setDefault(...)` để chuyển ngôn ngữ riêng từng request

`Locale.setDefault(locale)` **thay đổi trạng thái toàn cục trong JVM**, có thể ảnh hưởng các thread và library khác. Nếu hai request đồng thời gọi `setDefault(fr)` và `setDefault(en)`, nội dung có thể bị trộn hoặc format thay đổi ngoài ý muốn.

Ví dụ bài học dùng `setDefault(Locale.US)` **chỉ để làm đầu ra kiểm thử độc lập với thiết lập của máy**. Chương trình lưu default ban đầu và restore trong `finally`; nó là một ví dụ chạy đơn giản, **không phải mẫu code nên đặt trong web service sản xuất**. Trong ứng dụng thật, xác định default product policy bằng cấu hình và truyền locale tường minh; tránh thay global state trong request handler.

### 6.3. Locale theo `DISPLAY` và `FORMAT` không phải cùng phép chọn

Java hỗ trợ `Locale.Category.DISPLAY` (cho chuỗi hiển thị giao diện) và `Locale.Category.FORMAT` (ngày, số, tiền tệ...). Có thể gọi `Locale.getDefault(Locale.Category.DISPLAY)` hoặc `Locale.getDefault(Locale.Category.FORMAT)` khi thiết kế một ứng dụng i18n có tách hai yêu cầu.

**Nhưng `ResourceBundle.getBundle(baseName)` được tài liệu mô tả là dùng `Locale.getDefault()`**, không tự động suy luận toàn bộ chính sách UI từ một category khác. Nếu sản phẩm muốn UI dùng DISPLAY preference, hãy **lấy hoặc cấu hình locale đó và truyền tường minh** vào `getBundle(baseName, locale)`.

Ví dụ: menu có thể dùng tiếng Pháp trong khi số tiền ở định dạng phù hợp `en-US`. `ResourceBundle` chọn message text; `NumberFormat`/`DateTimeFormatter` format dữ liệu theo locale được truyền riêng.

## 7. Ví dụ Java 17+ hoàn chỉnh: chọn bundle, fallback sang default và lookup parent key

Ví dụ này bao gồm **một file Java và bốn file `.properties`**, không cần Maven/Gradle hay thư viện bên ngoài. Nó minh họa chính xác:

1. JVM default được đặt tạm thành `en-US` để kết quả kiểm thử cố định.
2. Yêu cầu `fr-CA` chọn `fr-CA`, key `region` đến từ `fr-CA`, `greeting` từ `fr`, `shared` từ root.
3. Key `only_en` chỉ có trong tiếng Anh **vẫn thiếu** trong nhánh `fr-CA`.
4. Yêu cầu `fr-FR` chọn bundle `fr` khi không có bản `fr-FR`.
5. Yêu cầu `de-DE` chọn tiếng Anh `en` do **fallback default locale**.
6. Với `ResourceBundle.Control.getNoFallbackControl(...)`, yêu cầu `de-DE` dùng root thay vì `en`.
7. `getBundle(BASE)` không truyền locale chọn theo default `en-US`, thực tế chọn bundle `en`.
8. Lấy danh sách candidate locales cho `fr-CA`.

Ví dụ chạy ở **classpath/unnamed module** để sử dụng overload có `ResourceBundle.Control`. Phần khác biệt với named modules được giải thích ở mục 9.

### 7.1. Tạo đúng cấu trúc file

~~~text
bundle-demo/
├── BundleFallbackDemo.java
├── Messages.properties
├── Messages_en.properties
├── Messages_fr.properties
└── Messages_fr_CA.properties
~~~

**`Messages.properties`:**

~~~properties
greeting=Base hello
shared=Base shared
~~~

**`Messages_en.properties`:**

~~~properties
greeting=Hello
only_en=English only
~~~

**`Messages_fr.properties`:**

~~~properties
greeting=Bonjour
~~~

**`Messages_fr_CA.properties`:**

~~~properties
region=Quebec
~~~

**Không tạo `Messages_de.properties`, `Messages_de_DE.properties`, `Messages_fr_FR.properties` hoặc `Messages_en_US.properties`** trong bài demo; việc cố tình thiếu các file ấy tạo ra những trường hợp fallback cần kiểm thử.

### 7.2. File Java hoàn chỉnh: `BundleFallbackDemo.java`

~~~java
import java.util.List;
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;
import java.util.stream.Collectors;

public class BundleFallbackDemo {
    private static final String BASE = "Messages";

    private static String label(Locale locale) {
        return Locale.ROOT.equals(locale)
                ? "root" : locale.toLanguageTag();
    }

    private static String optional(ResourceBundle bundle, String key) {
        try {
            return bundle.getString(key);
        } catch (MissingResourceException e) {
            return "<missing>";
        }
    }

    public static void main(String[] args) {
        Locale previous = Locale.getDefault();
        try {
            Locale.setDefault(Locale.US);
            System.out.println("Default: " + label(Locale.getDefault()));

            ResourceBundle frCa = ResourceBundle.getBundle(
                    BASE, Locale.CANADA_FRENCH);
            System.out.println("fr-CA selected: " + label(frCa.getLocale()));
            System.out.println("fr-CA region: " + frCa.getString("region"));
            System.out.println("fr-CA greeting: " + frCa.getString("greeting"));
            System.out.println("fr-CA shared: " + frCa.getString("shared"));
            System.out.println("fr-CA only_en: " + optional(frCa, "only_en"));

            ResourceBundle frFr = ResourceBundle.getBundle(BASE, Locale.FRANCE);
            System.out.println("fr-FR selected: " + label(frFr.getLocale()));

            ResourceBundle deDe = ResourceBundle.getBundle(BASE, Locale.GERMANY);
            System.out.println("de-DE selected: " + label(deDe.getLocale()));
            System.out.println("de-DE greeting: " + deDe.getString("greeting"));

            ResourceBundle.Control noFallback =
                    ResourceBundle.Control.getNoFallbackControl(
                            ResourceBundle.Control.FORMAT_PROPERTIES);
            ResourceBundle strict = ResourceBundle.getBundle(
                    BASE, Locale.GERMANY, noFallback);
            System.out.println("de-DE no fallback selected: "
                    + label(strict.getLocale()));
            System.out.println("de-DE no fallback greeting: "
                    + strict.getString("greeting"));

            ResourceBundle automatic = ResourceBundle.getBundle(BASE);
            System.out.println("No locale selected: "
                    + label(automatic.getLocale()));

            List<String> candidates =
                    ResourceBundle.Control.getControl(
                            ResourceBundle.Control.FORMAT_PROPERTIES)
                    .getCandidateLocales(BASE, Locale.CANADA_FRENCH)
                    .stream().map(BundleFallbackDemo::label)
                    .collect(Collectors.toList());
            System.out.println("fr-CA candidates: " + candidates);
        } finally {
            Locale.setDefault(previous);
        }
    }
}
~~~

**Giải thích những phần không hiển nhiên:**

- `label(Locale.ROOT)` trả chuỗi `root` để trình bày dễ đọc. `Locale.ROOT.toLanguageTag()` có thể hiển thị khác tên “root” trong console, nên code tách riêng.
- `optional(...)` bắt đúng `MissingResourceException` cho **một key cố ý không tồn tại** và chuyển thành `<missing>` để demo không dừng. Đây là policy hiển thị riêng của ví dụ, không phải giá trị mặc định của `ResourceBundle`.
- `try/finally` hoàn lại default locale lúc kết thúc. Điều này chỉ phù hợp với demo single-process; một server không được đổi default locale giữa các request.
- `ResourceBundle.Control.FORMAT_PROPERTIES` chỉ yêu cầu các file `.properties` ở nhánh kiểm thử no-fallback. Các lời gọi `getBundle(...)` mặc định có thể tìm class-based bundle trước property bundle nếu cả hai cùng tồn tại.
- `getCandidateLocales(...)` trả danh sách `Locale`; code in ra BCP 47 tags để minh họa thứ tự.
- Phần giá trị ví dụ đều là ASCII nhằm tránh khác biệt về encoding/console khi copy và chạy, nhưng cơ chế `ResourceBundle` hoạt động với Unicode.

### 7.3. Lệnh biên dịch và chạy

Mở terminal trong thư mục `bundle-demo` chứa cả năm file:

~~~sh
javac --release 17 BundleFallbackDemo.java
java BundleFallbackDemo
~~~

Không thêm package vào class Java trong ví dụ này; file `.properties` và `BundleFallbackDemo.class` cùng nằm ở **classpath hiện tại** khi chạy lệnh từ thư mục đã nêu. Nếu chạy ở một thư mục khác, chỉ rõ `-cp` để cả class và resource file đều nằm trong classpath.

**Stdout chính xác** (đã biên dịch bằng `javac --release 17` và chạy trên JDK 24):

~~~text
Default: en-US
fr-CA selected: fr-CA
fr-CA region: Quebec
fr-CA greeting: Bonjour
fr-CA shared: Base shared
fr-CA only_en: <missing>
fr-FR selected: fr
de-DE selected: en
de-DE greeting: Hello
de-DE no fallback selected: root
de-DE no fallback greeting: Base hello
No locale selected: en
fr-CA candidates: [fr-CA, fr, root]
~~~

Kết quả có thể tái tạo với các file nguồn **chính xác** đã liệt kê và môi trường Java 17+ tương thích. Không phụ thuộc default locale trước khi chạy vì `main` đặt tạm `Locale.US` và restore sau thử nghiệm.

### 7.4. Đọc kết quả theo ba tình huống

**Tình huống A — target có localized bundle:** `fr-CA` chọn `Messages_fr_CA`. `getLocale()` trả `fr-CA`. Key `greeting` không có ở Canada thì đi tới `Messages_fr`; key `shared` tiếp tục tới root; key `only_en` vẫn thiếu vì `Messages_en` không nằm trên nhánh `fr-CA`.

**Tình huống B — target không có bản vùng nhưng có bản ngôn ngữ:** `fr-FR` không có file `Messages_fr_FR`, nhưng có `Messages_fr`, nên selected locale là `fr` thay vì `fr-FR`. Đây là fallback **trong chuỗi candidate của target**, không phải chuyển sang JVM default.

**Tình huống C — không có localized bundle của target:** `de-DE` không có cả `de-DE` lẫn `de`, còn JVM default là `en-US` và có `Messages_en`. Kết quả mặc định chọn `en`, nhưng khi dùng `getNoFallbackControl(FORMAT_PROPERTIES)` thì JVM bỏ bước tìm default `en-US` và dùng root `Messages.properties`.

## 8. `getNoFallbackControl`: kiểm soát việc chuyển sang JVM default locale

Trong nhiều sản phẩm, fallback mong muốn là:

~~~text
requested locale -> requested language -> root baseline
~~~

chứ **không phải**:

~~~text
requested locale -> requested language -> JVM default language -> root
~~~

Trên classpath/unnamed module, có thể dùng `ResourceBundle.Control`:

~~~java
ResourceBundle.Control noFallback =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle bundle = ResourceBundle.getBundle(
        "Messages", requestedLocale, noFallback);
~~~

Đây là **snippet** với `requestedLocale` là `Locale` hợp lệ, sử dụng các import `java.util.ResourceBundle` và `java.util.Locale` trong method. `getNoFallbackControl(...)` tạo control mà `getFallbackLocale(...)` trả `null`, từ đó **không thử ngôn ngữ mặc định của JVM** khi thiếu localized bundle được yêu cầu.

**Nó không vô hiệu hóa tất cả fallback.** `getCandidateLocales(...)` vẫn có thể thử `fr-CA → fr → root`. Các key trong bundle đã chọn vẫn có thể đến từ parent chain. Tên API “NoFallback” nói về **bước chuyển từ target locale sang JVM default locale**, không có nghĩa chỉ chấp nhận file exact `Messages_fr_CA`.

`FORMAT_PROPERTIES` ở đây làm control chỉ tìm property-based bundle; nếu ứng dụng có cả `ListResourceBundle` bằng class và `.properties`, việc hạn chế format có thể thay đổi bundle được chọn. Muốn hỗ trợ cả hai dạng theo thứ tự mặc định, xem `ResourceBundle.Control.FORMAT_DEFAULT` trong môi trường cho phép control. Không tùy tiện đổi formats khi triển khai logic ứng dụng.

### 8.1. Nếu root bundle cũng không có thì sao?

Khi không có localized bundle phù hợp target, fallback sang default đã bị tắt và root không tồn tại, `getBundle(...)` sẽ **ném `MissingResourceException`**. Đó có thể là hành vi đúng cho cấu hình bắt buộc; không nên bắt lỗi rồi lặng lẽ in nội dung rỗng.

Với ứng dụng cần luôn hiển thị message, root bundle chứa đủ key thiết yếu là một quyết định tốt. Nhưng muốn tránh việc lộ nội dung chưa được dịch, một số sản phẩm chọn fail-fast trong test/CI thay vì chấp nhận root không điều kiện. Tùy policy, ta có thể kiểm tra `getLocale()` và chặn những fallback không được phép.

### 8.2. Named module: không dùng overload `Control` như classpath demo

Các overload `ResourceBundle.getBundle(...)` nhận `ResourceBundle.Control` sẽ ném **`UnsupportedOperationException` khi gọi từ named module**. Vì vậy **đừng bê nguyên snippet no-fallback ở trên vào một class thuộc named module rồi mong hoạt động**.

Với JPMS hiện đại:

- Dùng `getBundle(baseName, locale)` trong caller module hoặc `getBundle(baseName, locale, module)` khi có một module cụ thể.
- Tổ chức resource bundle trong module hoặc dưới dạng **`ResourceBundleProvider`** service theo hợp đồng module.
- Quy tắc encapsulation/visibility của resource trong module có thể ảnh hưởng tìm kiếm bundle; cần kiểm tra JavaDoc của `ResourceBundle` về resource access và module path.
- Nếu sản phẩm cần một fallback policy đặc biệt, triển khai ở **application/service layer** hoặc cơ chế provider phù hợp thay vì phụ thuộc vào `Control` trong named module.

`ResourceBundle.Control` vẫn là API hiện hành cho các trường hợp được hỗ trợ như classpath/unnamed module, không phải “API lỗi thời” — chỉ có giới hạn sử dụng theo môi trường JPMS.

## 9. Locale mặc định trong ứng dụng đa người dùng: lựa chọn có chủ đích

### 9.1. Target locale nên đến từ user preference/session/request

Một cách chọn locale rõ ràng:

~~~java
Locale requested = Locale.forLanguageTag("vi-VN");
ResourceBundle messages = ResourceBundle.getBundle(
        "com.example.i18n.Messages", requested);
~~~

Đây là **snippet**, giả sử family `com.example.i18n.Messages` được đóng gói trong classpath/module của ứng dụng. Thực tế, preference có thể đến từ cấu hình tài khoản, phiên làm việc hoặc thông tin request đã được xác thực/kiểm tra.

Nếu ứng dụng nhận HTTP `Accept-Language`, nó phải **parse và chọn locale hỗ trợ** theo policy của ứng dụng trước khi dùng `getBundle(...)`. `ResourceBundle` không phải một máy tự động giải toàn bộ bài toán content negotiation và không tự kết luận những locale product hỗ trợ.

Ví dụ người dùng muốn `es-MX` nhưng sản phẩm chỉ có `en` và `fr`. Có thể thiết kế bước chọn supported locale thành `en`, thay vì giao thẳng `es-MX` và vô tình phụ thuộc vào JVM default khác nhau trên các server. Sự lựa chọn của product cần được test và log rõ ràng.

### 9.2. Quy ước một fallback cố định của sản phẩm

Có hai tầng chính sách thường thấy:

**Cách 1 — root baseline:** đặt bản nội dung mặc định đã duyệt trong `Messages.properties`. Khi thiếu key ở localized bundle, parent chain tìm tới root. Nếu không muốn fallback sang JVM default khi chọn bundle, dùng no-fallback Control **chỉ khi caller ở unnamed module** hoặc dùng cơ chế ứng dụng phù hợp trong named module.

**Cách 2 — explicit fallback policy:** khi target không phù hợp, code chọn locale hỗ trợ theo một danh sách ưu tiên do sản phẩm kiểm soát (ví dụ `vi-VN → vi → en-US`). Sau đó tải bundle có target đã chọn. Cần phân biệt “không có bundle được hỗ trợ” với “bundle có nhưng thiếu key”, và có unit test cho từng nhánh.

Đừng coi `Locale.getDefault()` của server là policy sản phẩm bất biến. Khi tăng số máy, chạy container hoặc thay OS locale, cùng request có thể hiển thị ngôn ngữ khác nếu phụ thuộc trạng thái JVM.

### 9.3. Khi nào `getBundle(baseName)` vẫn phù hợp?

Ứng dụng desktop một người dùng, công cụ CLI chạy theo ngôn ngữ môi trường hoặc một tác vụ được cấu hình rõ default locale có thể dùng `getBundle(baseName)` rất tự nhiên. Chỉ cần biết nó **ngầm chọn locale từ JVM**, không phải luôn `Locale.ENGLISH`.

Nếu sản phẩm cần log/metric để debug, ghi nhận cả:

~~~text
requestedLocale = fr-CA
defaultLocale   = en-US
selectedLocale  = fr-CA
~~~

và khi default fallback xảy ra:

~~~text
requestedLocale = de-DE
defaultLocale   = en-US
selectedLocale  = en
~~~

Đây là **giá trị minh họa từ demo**, không phải một chuẩn log bắt buộc. Thông tin này đặc biệt hữu ích khi điều tra tại sao một user nhìn thấy tiếng Anh trong khi request của họ là tiếng Đức.

## 10. Chọn resource bundle và format ngày/số là hai việc độc lập

Giả sử người dùng muốn UI tiếng Pháp nhưng format tiền theo US. Có thể lấy:

~~~java
ResourceBundle ui = ResourceBundle.getBundle(
        "Messages", Locale.CANADA_FRENCH);
NumberFormat amounts = NumberFormat.getCurrencyInstance(Locale.US);
~~~

Đây là **snippet** trong code có cả `java.util.ResourceBundle` và `java.text.NumberFormat`, với file `Messages*` trên classpath. Một bên chọn **template/nhãn**, bên kia format **số tiền**. Không giả định `ui.getLocale()` sẽ tự biến default locale của `NumberFormat`.

Tương tự, nếu message chứa tham số, `String.format(...)` hay `MessageFormat` nên có locale **tường minh** khi kết quả ảnh hưởng định dạng số/ngày. `ResourceBundle` không tự động nội địa hóa tất cả argument chỉ vì nó đã chọn bản dịch tiếng Pháp.

Một lưu ý về dữ liệu: nếu muốn format số/ngày theo một locale khác với ngôn ngữ UI, truyền hai locale riêng biệt một cách có chủ đích. Điều này tránh việc bản dịch ngôn ngữ bị ràng buộc ngầm vào một định dạng tiền tệ.

## 11. Xử lý `MissingResourceException` đúng cách

Có hai lỗi thường bị gọi nhầm là “fallback không hoạt động”:

1. **Không tìm thấy bundle family:** sai base name, resource không nằm trên classpath/module path, hoặc không có bất kỳ candidate/root nào phù hợp. `getBundle(...)` có thể ném `MissingResourceException` ngay khi tải.
2. **Tìm thấy bundle nhưng thiếu key trong toàn bộ parent chain:** `bundle.getString(key)` hoặc `getObject(key)` ném `MissingResourceException` cho key ấy.

Để debug, ghi rõ giai đoạn:

~~~java
try {
    ResourceBundle b = ResourceBundle.getBundle("Messages", requested);
    String label = b.getString("greeting");
} catch (MissingResourceException e) {
    // Phân loại/log lỗi và xử lý theo chính sách sản phẩm.
}
~~~

Đây là **snippet** với biến `requested` là `Locale` hợp lệ, không phải chương trình độc lập. Nếu ứng dụng cần hiển thị fallback placeholder, chỉ tạo placeholder ở tầng UI phù hợp. Không catch tất cả `Exception` rồi trả mặc định im lặng: lỗi key thiếu thường phản ánh **chất lượng bản dịch hoặc đóng gói resources**.

**Kiểm tra `containsKey(...)` cũng không phân biệt key direct với inherited key.** Nếu chính sách sản phẩm bắt buộc mọi locale có đủ 100% key và không fallback, test nên duyệt nguồn resource trực tiếp để kiểm tra completeness, không chỉ gọi `bundle.containsKey(key)`.

### 11.1. `getLocale()` phát hiện fallback khi chọn bundle, không chỉ ra nguồn của từng key

Trong demo, `frCa.getLocale()` là `fr-CA`, dù `getString("greeting")` lấy từ `fr` và `getString("shared")` lấy từ root. `getLocale()` chỉ nói về **bundle được chọn chính**, không trả “bundle nguồn của key vừa lookup”.

Nếu cần telemetry “key này được dịch ở cấp nào”, phải thêm kiểm tra ở dữ liệu nguồn hoặc xây một bundle abstraction có metadata riêng. Đừng suy ra mọi key trong `frCa` đều được dịch đặc thù Canada vì `getLocale() == fr-CA`.

## 12. File resource, charset và deployment

### 12.1. UTF-8 trên Java 17+

Từ Java SE 9, property resource bundles được đọc theo UTF-8 mặc định; với một số byte sequence không hợp lệ theo UTF-8 có hành vi fallback decoding theo đặc tả `PropertyResourceBundle`. **Không cần ép mọi chữ Unicode thành chuỗi `\uXXXX` chỉ để dùng với Java 17+**. Tuy nhiên khi dùng build tools lọc/merge resource files, cần xác minh charset không bị đổi.

Đừng lẫn `PropertyResourceBundle` với hành vi **`Properties.load(InputStream)`** của `java.util.Properties`: những API này có hợp đồng encoding khác nhau. Với dữ liệu trong project, sử dụng cơ chế mà `ResourceBundle` hỗ trợ và test một file tiếng Việt có dấu để đảm bảo toolchain encode/decode đúng.

Ví dụ một bundle UTF-8 có thể chứa:

~~~properties
greeting=Xin chào
button.save=Lưu
validation.required=Trường này là bắt buộc
~~~

Đây là **ví dụ resource minh họa**, không nằm trong năm file của chương trình demo, vì thay file `Messages.properties` sẽ thay output đã kiểm thử.

### 12.2. Classpath versus module path

Trong classpath, file resource được đặt tại đường dẫn tương ứng base name. Với JAR, các file `com/example/i18n/Messages*.properties` phải thật sự nằm trong JAR dưới thư mục ấy; một path sai hoặc file chưa được đóng gói sẽ dẫn đến missing bundle.

Trong named module, bundle còn chịu **quy tắc encapsulation**, module/resource visibility và cách đăng ký provider theo JavaDoc. `getBundle(baseName, locale)` tìm từ caller module, trong khi `getBundle(baseName, locale, module)` cho phép chỉ định module target. Không mặc định rằng một resource được tìm bằng class loader từ bất kỳ module nào cũng đọc được nếu package bị encapsulate.

### 12.3. Class-based bundle và properties-based bundle

`ResourceBundle` có thể sử dụng class-based resource bundle (chẳng hạn subclass của `ListResourceBundle`) hoặc property-based bundle. Trong cơ chế default trên classpath, nếu cùng tên candidate tồn tại cả class và file property, thứ tự formats có thể khiến class-based bundle được chọn trước.

Ví dụ dùng các file `.properties` và không cung cấp class-based `Messages_xx`, nên kết quả chỉ liên quan những file đã liệt kê. Khi debug một bundle “đọc file nhưng giá trị không như file”, kiểm tra có class-based bundle trùng tên trong classpath hay không.

## 13. Caching, sửa bản dịch và vòng đời

`ResourceBundle.getBundle(...)` **có cache** để tránh tạo lại bundle liên tục. Một số lời gọi có thể dùng lại bundle instance đã được load; cũng có cache cho kết quả tìm kiếm không có bundle. Do đó:

- **Đừng kỳ vọng chỉ sửa file `Messages_fr.properties` trên đĩa là mọi request đang chạy thấy bản dịch mới ngay**.
- Với deployment thông thường, phát hành bản dịch mới như một phần artifact, test và restart/redeploy theo workflow.
- Nếu cần reload động, xem `ResourceBundle.clearCache()` hoặc `clearCache(loader)` trong đúng class loader/context và cân nhắc tính nhất quán của request đang dùng object cũ.
- Trong môi trường classpath hỗ trợ `Control`, `getTimeToLive` và `needsReload` có thể phục vụ policy cache nâng cao, nhưng cần implementation và test cẩn thận; không dùng như cách khắc phục thiếu file trong deployment.
- Trong named modules, cơ chế provider/module và cache có những quy tắc riêng; không chuyển nguyên một `Control` từ classpath sang mà bỏ qua `UnsupportedOperationException`.

**Không gọi `clearCache()` sau mỗi message lookup**. Việc này làm mất lợi ích cache và có thể tăng tải I/O đáng kể; với app bình thường các resource bundle có lifecycle gắn với artifact/deployment.

### 13.1. Cache không có nghĩa fallback locale là một kết quả cố định mãi mãi

Kết quả chọn bundle phụ thuộc base name, requested locale, default locale và visibility/loader. Khi thay default locale toàn cục, kết quả tra cứu khác có thể xuất hiện. Tuy nhiên bộ nhớ đệm và các object đã được lấy trước đó vẫn tồn tại trong phạm vi của chúng.

Điều an toàn cho ứng dụng multi-user là **đưa locale vào API nghiệp vụ**, chứ không dựa vào thứ tự các request đã làm thay đổi default locale hay cache.

## 14. Kiểm thử fallback theo ma trận, không chỉ một ngôn ngữ

Với bộ resource của demo và default `en-US`:

| Requested locale | Bundle được chọn theo lookup mặc định | Một ví dụ giá trị | Lý do |
| --- | --- | --- | --- |
| `fr-CA` | `fr-CA` | `region=Quebec` | Có file riêng của Canada |
| `fr-FR` | `fr` | `greeting=Bonjour` | Không có `fr-FR`, có `fr` |
| `de-DE` | `en` | `greeting=Hello` | Không có `de`, fallback sang JVM default `en-US` rồi tìm `en` |
| `de-DE` + no-fallback Control | `root` | `greeting=Base hello` | Không thử default locale, còn root |
| Không truyền locale | `en` | `greeting=Hello` | `Locale.getDefault()` là `en-US`, có parent `en` |
| `fr-CA`, key `only_en` | **Missing key** | `<missing>` trong wrapper demo | `only_en` không có ở nhánh `fr-CA → fr → root` |

Không đánh đồng việc **fallback sang bundle khác** với **fallback sang key của parent**. Một ma trận test tốt cần kiểm tra cả `getLocale()`, giá trị key, và trường hợp `MissingResourceException`.

Nếu dự án có script hoặc variant, thêm các trường hợp:

- `zh-Hant-TW` với bundle cho script `Hant` và country `TW`.
- `sr-Latn` đối với nhóm ngôn ngữ có nhiều hệ chữ.
- `pt-BR` và `pt-PT` nếu muốn áp dụng ngôn ngữ chung `pt`.
- `es-MX` khi chỉ có `es`/root, và khi default locale là ngôn ngữ khác.
- `Locale.ROOT` khi chủ ý muốn baseline bundle.

Đừng tự khẳng định chính xác thứ tự candidate cho mọi tổ hợp script/variant khi chưa kiểm tra `Control.getCandidateLocales(...)` theo runtime/Javadoc. Trên named module, dùng kiểm thử tích hợp tài nguyên thật thay vì giả định mọi tính năng của `Control` được hỗ trợ.

## 15. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi `getBundle(baseName)` trong server nhiều user | Mọi request chịu JVM default locale | Truyền locale của user/session/request tường minh |
| Nghĩ `getBundle(baseName, locale)` không bao giờ fallback tới default | Bất ngờ nhận bundle tiếng khác | Kiểm tra `getLocale()`; định nghĩa fallback policy |
| Nghĩ root luôn được chọn trước default locale khi target vắng mặt | Đoán sai ngôn ngữ hiển thị | Hiểu root có thể được giữ dự phòng trước khi thử default |
| Nghĩ thiếu key ở `fr` sẽ tự tìm `en` vì default là `en-US` | `MissingResourceException` | Cung cấp key ở parent/root hoặc policy lookup ứng dụng |
| Chỉ xem `getLocale()` để đo tỷ lệ dịch đủ | Bỏ sót key lấy từ parent | Audit từng nguồn translation, test keys |
| Dùng `getNoFallbackControl` và tưởng bỏ cả root/parent chain | Hiểu sai fallback của `ResourceBundle` | Phân biệt default-locale fallback và parent lookup |
| Gọi overload `Control` từ named module | `UnsupportedOperationException` | API module/provider hoặc service-layer fallback |
| Dùng `Locale.setDefault` mỗi request | Race condition, ảnh hưởng thread khác | Truyền locale tường minh, tránh global mutable state |
| Bỏ file `Messages.properties`, không kiểm tra completeness | Lỗi khi không có locale/thiếu key | Tạo baseline bundle và kiểm thử fallback |
| Dùng đường dẫn `com/foo/Messages` làm baseName tùy tiện | Lookup không đúng cơ chế đặt tên | Dùng tên family đầy đủ dạng `com.foo.Messages` |
| Sửa file properties trong runtime và kỳ vọng tự reload | Cache trả bundle đã load | Có chiến lược reload/redeploy phù hợp |
| Phụ thuộc vào system default máy phát triển | CI/container chạy ra ngôn ngữ khác | Test trên locale xác định; config product fallback |
| Quên kiểm tra package encapsulation trong JPMS | Không tìm được resource | Kiểm tra module boundary/provider, API getBundle đúng |
| Lấy text bundle rồi tự mặc định format số cùng locale | UI và format không nhất quán | Chọn locale formatting rõ ràng |
| Đổi encoding file khi build | Text Unicode bị lỗi | UTF-8 theo Java hiện hành, test resource thật |

## 16. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** JVM default `en-US`, có root bundle và `Messages_en.properties`. Nếu yêu cầu `de-DE` nhưng không có file tiếng Đức, bundle nào được chọn theo cơ chế mặc định?

**Trả lời:** Có thể chọn `Messages_en`, vì sau khi không tìm thấy localized candidate tiếng Đức, lookup thử **default locale `en-US`** trước khi dùng root đã tìm thấy. Trong bộ file demo, `getLocale()` là `en`.

**Câu 2.** `fr-CA` đã chọn `Messages_fr_CA`. Key `greeting` chỉ có trong `Messages_fr`, vậy `getString("greeting")` có trả `Bonjour` không?

**Trả lời:** Có. `Messages_fr` là parent của `Messages_fr_CA` theo candidate chain, nên key được tìm từ parent.

**Câu 3.** Key `only_en` chỉ nằm trong `Messages_en.properties`. `fr-CA` có nhận `English only` không, nếu JVM default là `en-US`?

**Trả lời:** Không. Sau khi bundle `fr-CA` đã được chọn, key lookup chỉ đi trong `fr-CA → fr → root`. Kết quả là `MissingResourceException` nếu cả ba không có key.

**Câu 4.** `getNoFallbackControl(FORMAT_PROPERTIES)` có bỏ cơ chế parent key lookup hay không?

**Trả lời:** Không. Nó bỏ bước **chuyển sang JVM default locale khi chọn bundle**, còn candidate locales và parent chain vẫn hoạt động. Trong demo, `de-DE` dùng root bundle thay vì tiếng Anh.

**Câu 5.** Một application chạy dưới named module có thể dùng y nguyên `getBundle(baseName, requested, noFallback)` không?

**Trả lời:** Không. Overload nhận `ResourceBundle.Control` không được hỗ trợ khi caller thuộc named module và có thể ném `UnsupportedOperationException`. Cần dùng API module/resource provider hoặc xây fallback policy của ứng dụng.

**Câu 6.** `bundle.getLocale()` là `fr-CA`. Có thể kết luận mọi key đã được dịch theo tiếng Pháp Canada không?

**Trả lời:** Không. `getLocale()` cho biết **bundle được chọn**. Key còn có thể đến từ `fr` hoặc root; kiểm tra completeness bằng audit dữ liệu nguồn và test.

**Câu 7.** Có nên đổi `Locale.setDefault(Locale.US)` mỗi khi user chuyển trang để buộc fallback về tiếng Anh?

**Trả lời:** Không trong server nhiều request. `setDefault` thay trạng thái chung toàn JVM, ảnh hưởng request khác. Chọn target locale tường minh và định nghĩa default product policy ở tầng ứng dụng.

**Câu 8.** Nếu chỉ có `Messages.properties` và không có bản dịch theo locale, sẽ luôn có lỗi?

**Trả lời:** Không. Root có thể được dùng làm bundle fallback và cung cấp key mặc định. Lỗi xảy ra khi không tìm được bundle cần thiết hoặc key không tồn tại trong root/parent chain, tùy lời gọi.

**Câu 9.** ResourceBundle đã chọn tiếng Pháp, số tiền có tự động được format theo `fr-CA` không?

**Trả lời:** Không. Bundle chọn message text, còn số/ngày/tiền tệ được định dạng bởi API chuyên trách với locale được truyền/đặt riêng.

**Câu 10.** Vì sao phải test cả `fr-FR` và `de-DE`?

**Trả lời:** `fr-FR` kiểm tra fallback **trong target candidate chain** (từ region xuống language), còn `de-DE` kiểm tra fallback **sang JVM default locale** khi không có localized candidate của target. Hai cơ chế khác nhau dễ gây bug nếu chỉ test một locale.

**Ghi nhớ:** Với `ResourceBundle`, hãy xác định rõ **requested locale**, **JVM default locale**, **selected bundle locale** và **parent chain**. Việc chọn bundle có thể fallback sang default locale nếu thiếu localized candidate; việc tìm key thì chỉ theo parent chain của bundle đã chọn. Sử dụng `getLocale()` để quan sát kết quả, cung cấp root baseline đủ key, tránh dùng `setDefault(...)` cho từng user và lưu ý giới hạn `Control` trong named modules. Đây là cơ chế Java SE hiện hành áp dụng cho hệ thống đa ngôn ngữ.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 26 — `ResourceBundle`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.html): default-locale fallback, parent key lookup, cache và named module.
- [Oracle Java SE 26 — `ResourceBundle.Control`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.Control.html): candidate locales, `getFallbackLocale`, `getNoFallbackControl` và formats.
- [Oracle Java SE 26 — `Locale`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): `getDefault`, `setDefault`, language tags và locale categories.
- [Oracle Java SE 26 — `PropertyResourceBundle`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/PropertyResourceBundle.html): thuộc tính và decoding của property bundles.
- [Oracle Java SE 26 — `ResourceBundleProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/ResourceBundleProvider.html): service provider khi đóng gói các bundle trong JPMS.
