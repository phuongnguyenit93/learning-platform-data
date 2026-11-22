# Thứ tự tìm bundle dạng lớp và dạng properties

Trong Java, `ResourceBundle.getBundle(...)` tìm tài nguyên địa phương hóa theo **hai chiều ưu tiên khác nhau**:

1. **Độ cụ thể của locale**: ưu tiên bundle phù hợp với locale được yêu cầu (ví dụ `en_US`), sau đó xét các bundle tổng quát hơn (`en`, bundle gốc).
2. **Định dạng tài nguyên tại cùng một locale**: theo cấu hình mặc định, Java ưu tiên bundle được triển khai bằng **lớp Java** (`java.class`) trước bundle bằng **tệp `.properties`** (`java.properties`).

Không nên suy luận rằng **mọi bundle dạng class luôn thắng mọi bundle dạng properties**. `Messages_en_US.properties` có thể được chọn trước `Messages_en.class` vì `en_US` cụ thể hơn `en`. Nhưng nếu **cùng** tồn tại `Messages_en_US.class` và `Messages_en_US.properties`, mặc định bản class có ưu tiên ở **chính mức `en_US`**.

Điều này còn ảnh hưởng đến **chuỗi cha (parent chain)**: sau khi tìm được bundle phù hợp nhất, Java có thể nối các bundle tổng quát hơn để tra các khóa chưa có. **Hai tệp class/properties ở cùng một mức locale không tự động được hợp nhất thành một bundle.**

Bài này giải thích thứ tự logic, cách chạy thực tế trên Java 17+, cách tùy biến định dạng và các nhầm lẫn khi bundle fallback hoặc cache được sử dụng.

## 1. Hai cách triển khai cùng một họ `ResourceBundle`

Giả sử `baseName` là `Messages`.

### Dạng lớp — `java.class`

Một lớp thường kế thừa `ListResourceBundle`:

~~~java
import java.util.ListResourceBundle;

public class Messages_en extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"welcome", "Hello"},
                {"cancel", "Cancel"}
        };
    }
}
~~~

Tên nguồn `Messages_en.java` được biên dịch thành `Messages_en.class`. Khi classpath/module cho phép truy cập, loader có thể khởi tạo lớp đó như một `ResourceBundle`. Dạng class cho phép lưu giá trị không chỉ là `String`: `ListResourceBundle` lưu các đối tượng `Object`, có thể lấy qua `getObject`, đồng thời phải bảo đảm tính hợp lệ của dữ liệu và khả năng sử dụng giữa các luồng.

Một class bundle cần là lớp phù hợp với `ResourceBundle`, có thể tải và khởi tạo theo quy tắc truy cập của Java/runtime; không phải cứ có tệp class trùng tên là chắc chắn thành công.

### Dạng tài nguyên — `java.properties`

Tệp `Messages_en.properties`:

~~~properties
welcome=Hello
cancel=Cancel
~~~

Khi tìm thấy tài nguyên tương ứng trên classpath/module, Java có thể đọc nó thành `PropertyResourceBundle`. Các giá trị trong `.properties` là chuỗi; với `ListResourceBundle`, các giá trị có thể là đối tượng.

Đối với Java 17+, `PropertyResourceBundle` hỗ trợ đọc UTF-8 theo cơ chế quy định của JDK. Nên nhất quán lưu tệp bằng UTF-8. Đừng nhầm việc Java tự tra tệp `.properties` thành bundle với thao tác đọc chung bằng `java.util.Properties.load(InputStream)`, vì hai cơ chế có quy định mã hóa khác nhau.

Hai cách viết **cùng thuộc một họ baseName** nên có thể tham gia một chuỗi fallback nếu được đặt ở **các mức locale khác nhau**.

## 2. Thứ tự mặc định do `ResourceBundle.Control` mô tả

Trong quy trình tải bundle thông thường trên **classpath/unnamed module**, `ResourceBundle.Control.FORMAT_DEFAULT` có thứ tự:

~~~text
java.class
java.properties
~~~

Đây là danh sách format mặc định của `Control.getFormats(baseName)`. Tại một candidate locale, runtime thử bundle dạng class trước, rồi mới thử bundle dạng properties nếu không thể chọn bản class phù hợp.

Các hằng số hữu ích:

| Hằng số | Danh sách format | Tác dụng |
| --- | --- | --- |
| `ResourceBundle.Control.FORMAT_DEFAULT` | `["java.class", "java.properties"]` | Thứ tự thông thường |
| `ResourceBundle.Control.FORMAT_CLASS` | `["java.class"]` | Chỉ thử dạng class |
| `ResourceBundle.Control.FORMAT_PROPERTIES` | `["java.properties"]` | Chỉ thử dạng properties |

Các danh sách trên mô tả **format**, không thay thế thứ tự candidate locale. Khi phân tích một kết quả bất ngờ, hãy hỏi **bundle ở locale nào được chọn** trước, rồi hỏi **format nào thắng trong locale đó**.

**Giới hạn:** Trong **named module** (JPMS), cơ chế tìm kiếm còn chịu quy định truy cập package/module và dịch vụ provider; các overload `getBundle` nhận tham số `ResourceBundle.Control` không được hỗ trợ khi gọi từ named module. Phần minh họa có `Control` ở dưới dành cho ứng dụng **classpath/unnamed module**.

## 3. Candidate locale: ưu tiên bản cụ thể hơn

Ví dụ:

~~~java
Locale requested = Locale.US; // ngôn ngữ en, vùng US
ResourceBundle bundle = ResourceBundle.getBundle("Messages", requested);
~~~

Với locale này, danh sách ứng viên thông thường theo độ cụ thể là:

~~~text
Messages_en_US
Messages_en
Messages
~~~

Dạng tương ứng được thử cho **mỗi** tên ứng viên:

| Mức locale | Thứ tự ưu tiên logic tại mức đó |
| --- | --- |
| `en_US` | `Messages_en_US.class` → `Messages_en_US.properties` |
| `en` | `Messages_en.class` → `Messages_en.properties` |
| Gốc (ROOT) | `Messages.class` → `Messages.properties` |

Vì thế, thứ tự **ưu tiên logic** khi chọn bundle là:

~~~text
Messages_en_US.class
Messages_en_US.properties
Messages_en.class
Messages_en.properties
Messages.class
Messages.properties
~~~

Lưu ý đây là **trình tự ưu tiên để hiểu kết quả**, không phải cam kết rằng mọi lần gọi sẽ mở tập tin theo thứ tự vật lý trên. JDK có thể đã cache một số bundle, hoặc tải bundle gốc/cha trong lúc xây dựng parent chain. Vì vậy nhật ký thứ tự gọi `newBundle(...)` hoặc truy cập file thực tế **có thể không giống** thứ tự ưu tiên logic trên.

Với locale phức tạp hơn (ví dụ script `zh-Hant-TW` hoặc variant), `Control.getCandidateLocales(...)` tạo chuỗi ứng viên dài hơn và có các trường hợp đặc biệt. Không chỉ đơn giản tách đuôi chuỗi tag theo dấu gạch ngang trong mọi trường hợp.

## 4. Thí nghiệm 1: Class và properties cùng locale — class thắng

Tạo **năm tệp** trong **cùng một thư mục**. Tên tệp có ý nghĩa vì Java dùng nó để xây bundle name.

**Tệp `Messages_en_US.java`:**

~~~java
import java.util.ListResourceBundle;

public class Messages_en_US extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"origin", "US class"},
                {"shared", "from US class"}
        };
    }
}
~~~

**Tệp `Messages_en_US.properties`:**

~~~properties
origin=US properties
shared=from US properties
onlyInProperties=hidden value
~~~

**Tệp `Messages_en.properties`:**

~~~properties
origin=English properties
languageOnly=from language bundle
~~~

**Tệp `Messages.properties`:**

~~~properties
origin=Root properties
rootOnly=from root bundle
~~~

**Tệp `BundleOrderDemo.java`:**

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleOrderDemo {
    public static void main(String[] args) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("Messages", Locale.US);

        System.out.println(bundle.getLocale().toLanguageTag());
        System.out.println(bundle.getString("origin"));
        System.out.println(bundle.getString("shared"));
        System.out.println(bundle.getString("languageOnly"));
        System.out.println(bundle.getString("rootOnly"));
        System.out.println(bundle.containsKey("onlyInProperties"));
    }
}
~~~

Chạy bằng JDK 17+ trong thư mục chứa năm tệp:

~~~bash
javac -encoding UTF-8 Messages_en_US.java BundleOrderDemo.java
java -cp . BundleOrderDemo
~~~

Kết quả:

~~~text
en-US
US class
from US class
from language bundle
from root bundle
false
~~~

**Phân tích từng dòng:**

1. `getLocale()` cho biết bundle được chọn ứng với `en-US`. Đây là locale của **bundle được trả về**, không phải bằng chứng toàn bộ khóa nằm tại bundle đó.
2. `origin` và `shared` nằm trong `Messages_en_US` dạng class, nên trả về giá trị từ class.
3. `languageOnly` không tồn tại trong class `Messages_en_US`, nên Java tra parent ở mức `en` và lấy từ `Messages_en.properties`.
4. `rootOnly` lấy qua parent gốc `Messages.properties`.
5. `onlyInProperties` tuy có trong `Messages_en_US.properties` nhưng **không xuất hiện**: vì bundle dạng class ở **cùng locale `en_US`** đã được chọn, Java không gộp tệp properties cùng locale làm parent hoặc “bộ khóa bổ sung”.

Thí nghiệm này làm rõ hai điều: **ưu tiên format áp dụng cho mỗi candidate locale**, còn **fallback khóa** đi qua parent chain của các candidate locale tổng quát hơn.

Nếu bỏ `Messages_en_US.class` (và không còn bản class được tải từ classpath) rồi khởi chạy lại trong JVM mới, Java có thể chọn `Messages_en_US.properties`. Trong ứng dụng có cache, hãy kiểm tra lần chạy/JVM và classpath thực tế trước khi kết luận việc xóa file đã có tác dụng ngay.

## 5. Thí nghiệm 2: Properties cụ thể thắng class tổng quát

Để không lẫn với thí nghiệm 1, dùng **họ bundle khác** có baseName là `Levels`.

**Tệp `Levels_en.java`:**

~~~java
import java.util.ListResourceBundle;

public class Levels_en extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"origin", "EN class"},
                {"common", "English parent"}
        };
    }
}
~~~

**Tệp `Levels_en_US.properties`:**

~~~properties
origin=US properties
~~~

**Tệp `LevelsDemo.java`:**

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class LevelsDemo {
    public static void main(String[] args) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("Levels", Locale.US);

        System.out.println(bundle.getLocale().toLanguageTag());
        System.out.println(bundle.getString("origin"));
        System.out.println(bundle.getString("common"));
    }
}
~~~

Biên dịch/chạy với hai file `.java` và giữ `Levels_en_US.properties` trên classpath:

~~~bash
javac -encoding UTF-8 Levels_en.java LevelsDemo.java
java -cp . LevelsDemo
~~~

Kết quả:

~~~text
en-US
US properties
English parent
~~~

Tại mức `en_US` có `Levels_en_US.properties`; vì nó **cụ thể hơn** `Levels_en.class` nên **US properties thắng về bundle chính**. Khi cần khóa `common` chưa có ở bản US, Java dùng `Levels_en.class` làm parent.

Đây là ví dụ phản bác ngộ nhận “Java duyệt tất cả class trước rồi mới tới tất cả properties”. Đúng hơn là: **chọn theo candidate locale trước; ở mỗi candidate, class trước properties**.

## 6. Vì sao có chuỗi cha (parent chain)?

Sau khi tìm bundle ở candidate cụ thể nhất còn tồn tại, `ResourceBundle` thiết lập các bundle cấp tổng quát hơn thành **cha**, ví dụ:

~~~text
Messages_en_US (class)
    └── Messages_en (properties)
          └── Messages (properties)
~~~

Khi gọi `bundle.getString("someKey")`:

1. Java tìm khóa trong bundle hiện tại.
2. Nếu không có, tìm trong parent của nó, rồi parent tiếp theo.
3. Nếu không có trong toàn bộ chuỗi, ném `MissingResourceException`.

`getString` và `getObject` tra qua chuỗi cha; ngược lại, `bundle.getLocale()` chỉ phản ánh locale của bundle chính được trả về. Một tài nguyên hiển thị từ cha **không làm đổi** `getLocale()`.

**Phân biệt với Java inheritance:** class `Messages_en_US extends ListResourceBundle` có thể kế thừa lớp Java, nhưng **ResourceBundle parent chain** là cơ chế fallback tài nguyên riêng. Không cần khai báo `Messages_en_US extends Messages_en` để Java tìm `Messages_en`; runtime tự liên kết parent dựa trên ứng viên. Trường hợp class bundle đã tự thiết lập parent là một tình huống đặc biệt; mã chuẩn nên tránh phụ thuộc vào liên kết cha thủ công nếu không cần.

Không có quy tắc “thiếu khóa thì dùng bản properties cùng locale”, nếu class cùng locale đã được chọn. Đây là điểm rất dễ gây lỗi dịch vụ khi nhóm phát triển vô tình thêm cả `Messages_en_US.java` và `Messages_en_US.properties` cho cùng baseName.

## 7. Fallback khi không tìm được locale yêu cầu

Trong quy trình mặc định trên classpath, việc chọn bundle có thể xét **locale mặc định của JVM** nếu không tìm được bundle phù hợp theo locale yêu cầu; sau cùng có thể dùng **bundle gốc** nếu tồn tại.

Ví dụ: ứng dụng yêu cầu `fr_CA` nhưng họ `Messages` không có bản tiếng Pháp. Khi JVM default là `en_US` và có bundle tiếng Anh, Java có thể chọn bundle theo default `en_US`. Nếu không có ứng viên khác, bundle gốc có thể là phương án cuối. `getBundle(...)` ném `MissingResourceException` khi không tìm thấy tài nguyên phù hợp theo toàn bộ cơ chế tìm kiếm.

Không nên kể thuật toán này thành quy tắc đơn giản “luôn dùng bundle gốc trước default”. Theo quy trình `Control` mặc định, bản gốc có thể được giữ lại làm lựa chọn cuối trong lúc thử chuỗi theo default. Java 17 còn có sự khác nhau giữa các overload và ngữ cảnh module; cần căn cứ theo API thực sự sử dụng.

### Cần phân biệt hai loại dự phòng

- **Fallback bundle:** chọn bundle khác khi không có bundle phù hợp với locale yêu cầu.
- **Fallback khóa:** đã chọn được bundle nhưng thiếu một khóa; tra khóa đó từ parent.

Ví dụ `getLocale()` có thể trả `en-US` trong khi một khóa lấy từ `Messages.properties`. Đó là **fallback khóa**. Ngược lại, request `fr-CA` nhưng `getLocale()` trả `en-US` là một trường hợp **fallback bundle** theo default.

Một ứng dụng nhiều người dùng nên truyền locale cụ thể vào `getBundle(baseName, locale)`, có chính sách locale được hỗ trợ và fallback minh bạch. Không đổi `Locale.setDefault(...)` theo từng HTTP request: default là trạng thái chung của JVM và có thể gây trộn ngôn ngữ giữa các luồng.

## 8. Quan sát ứng viên bằng `ResourceBundle.Control`

Với ứng dụng chạy trên **classpath/unnamed module**, có thể in danh sách ứng viên/format mà Java chuẩn sử dụng để hiểu thứ tự logic. Tạo `BundleCandidatesDemo.java`:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleCandidatesDemo {
    public static void main(String[] args) {
        ResourceBundle.Control control =
                ResourceBundle.Control.getControl(
                        ResourceBundle.Control.FORMAT_DEFAULT);

        System.out.println(control.getFormats("Messages"));

        for (Locale candidate : control.getCandidateLocales(
                "Messages", Locale.US)) {
            System.out.println(
                    candidate.equals(Locale.ROOT)
                            ? "ROOT"
                            : candidate.toLanguageTag()
            );
        }
    }
}
~~~

~~~bash
javac BundleCandidatesDemo.java
java BundleCandidatesDemo
~~~

Kết quả:

~~~text
[java.class, java.properties]
en-US
en
ROOT
~~~

`getCandidateLocales` giúp giải thích **thứ tự mức locale**, trong khi `getFormats` cho thấy **thứ tự format trong một mức**. Lặp qua danh sách để quan sát không tự tải mọi bundle và không cần tệp `Messages*.properties` tồn tại.

Nếu request là `Locale.forLanguageTag("zh-Hant-TW")`, thuật toán có thể đưa cả ứng viên có script và không có script vào danh sách. Đừng tự viết thuật toán nối chuỗi `language_country` rồi kết luận đó là toàn bộ tìm kiếm của JDK.

**Quan trọng:** `ResourceBundle.Control` không dùng được trong overload `getBundle(..., Control)` khi caller ở **named module**. Nếu ứng dụng dùng JPMS, ưu tiên API tương ứng với module và xem thêm cơ chế `ResourceBundleProvider`/quy tắc export/open thay vì đưa nguyên thí nghiệm Control vào module có tên.

## 9. Tùy chọn chỉ class hoặc chỉ properties

Trong môi trường phù hợp với `ResourceBundle.Control`, Java hỗ trợ cấu hình chỉ thử một format:

~~~java
ResourceBundle.Control onlyProperties =
        ResourceBundle.Control.getControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle messages = ResourceBundle.getBundle(
        "Messages",
        Locale.US,
        onlyProperties
);
~~~

Đây là **đoạn minh họa bên trong method**, cần `import java.util.Locale;` và `import java.util.ResourceBundle;`. Nó dùng các candidate locale như thông thường nhưng cho phép **chỉ format `java.properties`**. Tương tự, `FORMAT_CLASS` chỉ dùng class.

Có thể dùng:

~~~java
ResourceBundle.Control noDefaultLocaleFallback =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_DEFAULT);
~~~

`getNoFallbackControl` ngăn bước thử locale mặc định thay thế theo cấu hình Control; nó **không** có nghĩa “chỉ tải đúng locale yêu cầu” vì chuỗi cha `en_US → en → ROOT` vẫn được xét.

### Thận trọng với cache khi đổi Control

`ResourceBundle` có bộ nhớ đệm dựa trên baseName/locale/class loader hoặc module và cơ chế TTL. Trong nhiều trường hợp, một bundle dạng class đã được tải vào cache khi dùng cấu hình mặc định có thể tiếp tục được trả lại nếu lời gọi kế tiếp đổi `Control` để chỉ cho phép properties. Tài liệu `ResourceBundle.Control` cảnh báo việc thay đổi danh sách format hoặc candidate locales không nhất quán giữa các lời gọi trên cùng baseName có thể gây kết quả bất ngờ.

Khi muốn chuyển toàn bộ ứng dụng từ class sang properties, hãy chọn **một chính sách nhất quán**, tránh pha trộn nhiều Control cho một họ bundle. Với kiểm thử, dùng JVM riêng hoặc baseName/class loader biệt lập để kiểm tra thứ tự tải; chỉ dùng `ResourceBundle.clearCache()` trong điều kiện và phạm vi phù hợp, nhớ rằng các tham chiếu bundle đã giữ không bị thay thế chỉ bằng thao tác clear cache.

## 10. Cách Java đặt tên và tìm tài nguyên

Đối với một `baseName` có package:

~~~java
ResourceBundle.getBundle(
        "com.example.i18n.Messages",
        Locale.US
);
~~~

Một số tên tương ứng:

~~~text
com.example.i18n.Messages_en_US   (tên class)
com/example/i18n/Messages_en_US.properties   (đường dẫn tài nguyên)
com.example.i18n.Messages_en
com/example/i18n/Messages_en.properties
com.example.i18n.Messages
com/example/i18n/Messages.properties
~~~

Khi viết lớp Java, tên package và tên class phải trùng quy tắc định danh. Với Gradle hoặc Maven, class bundle thường nằm dưới mã nguồn Java, còn `.properties` nằm trong resources của ứng dụng, và sau đóng gói phải **hiện diện trên runtime classpath/module**. Tên file có phân biệt hoa/thường trên nhiều hệ thống tệp; ví dụ `messages_en.properties` khác `Messages_en.properties`.

Lưu ý tên file tài nguyên dạng Java truyền thống dùng dấu gạch dưới cho thành phần locale (`Messages_en_US.properties`) trong khi `Locale.toLanguageTag()` trả dạng BCP 47 dùng dấu gạch ngang (`en-US`). Không đổi tên tệp thành `Messages_en-US.properties` chỉ vì language tag hiển thị như vậy.

**Classpath và class loader rất quan trọng:** chỉ cần một bản class bundle cùng tên ở dependency khác được tải trước, tệp properties dự kiến có thể không bao giờ được chọn. Khi chẩn đoán, xác định JAR/classpath thực tế và class loader đang dùng, không chỉ nhìn source của module.

## 11. Chẩn đoán kết quả chọn bundle bất ngờ

Khi thấy giá trị dịch không khớp file `.properties`, thực hiện theo trình tự:

1. **Kiểm tra baseName và target locale thực tế.** Ví dụ request truyền `en-US` hay vô tình gọi overload không có locale nên dùng default?
2. **Kiểm tra `bundle.getLocale()`.** Đây là locale của bundle chính, có thể khác target nếu fallback.
3. **Kiểm tra candidate locales.** Với `Locale.US` thông thường là `en_US`, `en`, ROOT. Nếu script/variant/locale đặc biệt, dùng `getCandidateLocales` trong ngữ cảnh hỗ trợ.
4. **Kiểm tra cả dạng class và properties cho từng candidate.** Với **cùng** locale, class mặc định ưu tiên.
5. **Xác định khóa nằm ở bundle nào.** Nếu khóa không có ở bundle chính, `getString` có thể lấy từ parent; việc đó không thể hiện qua `getLocale()`.
6. **Kiểm tra nội dung gói triển khai.** `Messages_en_US.class` còn tồn tại trong JAR hay bị tạo ra từ lần build trước? Tệp `.properties` có thực sự được đóng gói đúng đường dẫn?
7. **Xem chính sách Control/provider, cache và module.** Một `Control` khác, class loader khác, instance cache trước đó hoặc cấu hình JPMS có thể thay đổi đường tải.
8. **Kiểm tra lỗi phân biệt hoa/thường và mã hóa ký tự.** File xuất hiện trong source không đồng nghĩa runtime đọc đúng file/byte.

Nên tránh đoán “file properties không được đọc là do Java ưu tiên class trên toàn bộ các locale”; cần xác định hai chiều ưu tiên để biết lý do cụ thể.

## 12. Những lỗi và ngộ nhận phổ biến

### “Class luôn thắng properties”

**Sai nếu class ở locale ít cụ thể hơn.** `Levels_en_US.properties` được chọn làm bundle chính khi request `en-US` dù tồn tại `Levels_en.class`. Chỉ khi **cùng candidate locale**, class đứng trước properties theo danh sách format mặc định.

### “Tệp properties cùng locale sẽ bù khóa bị thiếu trong class”

**Sai.** Ở thí nghiệm 1, `Messages_en_US.class` và `Messages_en_US.properties` không được hợp nhất tự động. Khóa thiếu có thể được tìm ở bundle cha `Messages_en`/`Messages`; tệp properties bị che ở **cùng mức** không trở thành cha.

### “`getLocale()` nói rõ mọi khóa đến từ locale nào”

**Sai.** `getLocale()` phản ánh bundle được chọn. Nếu một khóa lấy từ parent, phương thức đó không cho biết cấp cha đã cung cấp khóa. Muốn kiểm thử nguồn thực tế, dùng giá trị được kiểm soát trong từng bundle như các thí nghiệm trên.

### “Root bundle luôn được dùng ngay khi target locale không có”

Không nhất thiết. Default locale fallback có thể được xét trước khi chấp nhận root làm kết quả cuối. Phải phân biệt quy trình lấy bundle với chuỗi parent để tra khóa.

### “Có `Messages_en_US.java` thì `ResourceBundle` tải file `.java`”

**Sai.** Mã nguồn `.java` phải được **biên dịch** thành `.class`. Đường tải runtime không thực thi file mã nguồn Java như tài nguyên properties.

### “Thay tài nguyên ở runtime sẽ cập nhật ngay”

Không được bảo đảm vì cache. `ResourceBundle.clearCache()` ảnh hưởng đến cache được quản lý tương ứng, nhưng không biến đổi các đối tượng bundle mà ứng dụng đang giữ, và không tự xóa cache do framework khác quản lý.

### “Các API dùng `Control` đều hoạt động y hệt trong mọi named module”

**Sai.** Các overload nhận `Control` không được hỗ trợ khi caller ở named module. Trong JPMS còn có quy tắc đóng gói và truy cập tài nguyên; cần phân tích đường tải dành cho module.

## 13. Bài tập thực hành có đáp án

### Tình huống A: chọn bundle chính

Có các file:

~~~text
Labels_en_US.properties
Labels_en.class
Labels.properties
~~~

Yêu cầu `Locale.US` và dùng format mặc định. Bundle chính được chọn là gì?

**Đáp án:** `Labels_en_US.properties` vì candidate `en_US` được ưu tiên hơn `en`. `Labels_en.class` vẫn có thể làm parent cho khóa thiếu.

### Tình huống B: có cả hai format tại cùng locale

Có:

~~~text
Labels_en_US.class
Labels_en_US.properties
Labels_en.properties
~~~

Yêu cầu `Locale.US`. Khóa `title` chỉ có trong `Labels_en_US.properties`, còn `Labels_en_US.class` không có. Liệu Java tự lấy `title` từ properties cùng locale?

**Đáp án:** Không theo thứ tự mặc định. Class cùng locale đã được chọn; Java tìm khóa thiếu qua **parent** (`en`, ROOT nếu có), không tự ghép properties cùng `en_US`.

### Tình huống C: không có bản dịch cho locale yêu cầu

Có `Labels_en.properties` và `Labels.properties`, không có bản tiếng Pháp; default JVM là `en-US`, yêu cầu `fr-CA`. Có thể chọn bundle tiếng Anh không?

**Đáp án:** Có thể theo cơ chế fallback default locale; không nên giả định hệ thống chỉ tìm root khi thiếu `fr_CA`. Chính sách i18n sản phẩm nên quản lý fallback tường minh.

### Tình huống D: kiểm thử bằng Control

`Control.FORMAT_PROPERTIES` được áp dụng cho lần đầu trong JVM chưa có bundle class cache. Với `Labels_en_US.class` và `Labels_en_US.properties`, định dạng nào được phép tìm?

**Đáp án:** Chỉ `java.properties`. Tuy nhiên việc dùng các Control khác nhau cho cùng baseName sau khi cache đã hình thành có thể làm kết quả kiểm thử gây hiểu nhầm.

### Tình huống E: lỗi thiếu khóa

`ResourceBundle.getBundle("Labels", Locale.US)` trả một bundle, nhưng `getString("missing")` ném `MissingResourceException`. Điều gì đã xảy ra?

**Đáp án:** Bundle **được tìm thấy**, nhưng khóa `missing` không tồn tại trong bundle chính và các parent của nó. Đây không phải lỗi không tìm được bundle.

## 14. Kết luận áp dụng

Khi thiết kế bundle cho ứng dụng Java:

- Dùng **baseName nhất quán** và tên file/class đúng chuẩn.
- Chọn **một format chủ đạo** cho một họ bundle, hoặc nếu cố ý pha class/properties thì hiểu rõ luật ưu tiên theo candidate locale.
- Đảm bảo các khóa quan trọng tồn tại ở lớp bundle cụ thể hoặc parent được thiết kế rõ.
- Ghi nhớ **class và properties cùng locale không được merge**.
- Truyền `Locale` theo request/người dùng và kiểm thử chính sách fallback thay vì thay default JVM.
- Kiểm tra thực tế trên classpath/module đóng gói, đặc biệt khi đổi cách tải hoặc cache.

**Công thức nhớ:** **Locale cụ thể hơn ưu tiên trước; trong cùng một candidate locale, class trước properties (với format mặc định).** Sau khi tìm được bundle chính, Java tiếp tục tra các **khóa thiếu** qua parent chain; đây là một bước riêng so với lựa chọn class/properties.

**Tài liệu tham khảo:** [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html) và [Java SE 17 — ResourceBundle.Control](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html).