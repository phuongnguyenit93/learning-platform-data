# ResourceBundle: containsKey(), keySet() và truy cập tài nguyên cha

Khi ứng dụng Java có nhiều bản dịch, mỗi ngôn ngữ/vùng thường chỉ khai báo những thông điệp cần thay đổi. Chẳng hạn bộ tài nguyên cho `vi-VN` có lời chào riêng, bộ `vi` có bản dịch chung, còn bộ gốc chứa các câu chưa dịch. `ResourceBundle` cho phép tìm giá trị theo **chuỗi tài nguyên cha (parent chain)**, giúp một khóa bị thiếu ở mức cụ thể vẫn lấy được giá trị ở mức tổng quát hơn.

Bài này giải thích chính xác ba câu hỏi:

1. `containsKey(key)` kiểm tra khóa **của bundle hiện tại hay cả các bundle cha**?
2. `keySet()` trả tập khóa nào và khác `handleKeySet()` ra sao?
3. `getString()/getObject()` đi qua chuỗi cha thế nào khi một khóa bị thiếu hoặc bị ghi đè?

Câu trả lời quan trọng: **`containsKey` và `keySet` đều tính cả khóa kế thừa từ cha**, còn tra cứu giá trị ưu tiên bundle cụ thể nhất rồi mới tới cha. Vì vậy một khóa xuất hiện trong `keySet()` không chứng minh khóa đó được định nghĩa ngay tại tệp bản dịch đang xét.

## 1. Mô hình bundle cha trong Java

Một *bundle family* gồm các tài nguyên có cùng *base name*, chẳng hạn `messages`:

~~~text
messages_vi_VN.properties      (cụ thể nhất: tiếng Việt tại Việt Nam)
          ↓ parent
messages_vi.properties         (tiếng Việt nói chung)
          ↓ parent
messages.properties            (gốc, không kèm locale)
~~~

Khi yêu cầu `vi-VN`, cơ chế tải tiêu chuẩn có thể liên kết bundle cụ thể với các bundle ít cụ thể hơn đã có. Nếu `messages_vi_VN.properties` không có `logout`, Java tìm tiếp ở `messages_vi.properties`, rồi `messages.properties`. Một khóa được khai báo tại con sẽ **che (override/shadow)** giá trị cùng khóa trong cha, trong khi các khóa chỉ có ở cha vẫn truy cập được.

Ví dụ dữ liệu minh họa:

| Khóa | `messages.properties` | `messages_vi.properties` | `messages_vi_VN.properties` |
| --- | --- | --- | --- |
| `app.name` | Sample App | — | — |
| `greeting` | Hello | Xin chào | Chào bạn |
| `logout` | Sign out | — | — |
| `thanks` | — | Cảm ơn | — |
| `region` | — | — | Việt Nam |

Dấu “—” nghĩa là **không khai báo trong bundle đó**, không phải một chuỗi rỗng. Khi đọc từ bundle `vi-VN`, kết quả hiệu lực là:

| Khóa | Giá trị nhận được | Nguồn thực tế |
| --- | --- | --- |
| `app.name` | Sample App | Bundle gốc |
| `greeting` | Chào bạn | Bundle `vi-VN` ghi đè |
| `logout` | Sign out | Bundle gốc |
| `thanks` | Cảm ơn | Bundle `vi` |
| `region` | Việt Nam | Bundle `vi-VN` |

Bảng này thể hiện **fallback theo khóa trên chuỗi cha đã được thiết lập**, khác với fallback chọn bundle khi `ResourceBundle.getBundle(...)` không tìm thấy ứng viên của locale được yêu cầu. Không nên trộn lẫn hai quá trình ấy.

### Cha được thiết lập như thế nào?

`ResourceBundle.getBundle(baseName, locale)` tự xác định bundle phù hợp và liên kết các bundle cha theo cơ chế tìm kiếm. Các lớp con tùy chỉnh của `ResourceBundle` cũng có phương thức `setParent(parent)` ở mức `protected` để thiết lập cha. Trong phần lớn ứng dụng dùng tệp `.properties`, bạn **không tự gọi `setParent`**: bộ tải làm việc đó.

Chuỗi cha là **quan hệ giữa các đối tượng ResourceBundle**, không phải quan hệ cha-con của Java class. Một bundle có thể kế thừa giá trị dù lớp thực thi của nó không extends lớp của bundle cha.

## 2. containsKey(String key): khóa hiện tại hoặc kế thừa

Hợp đồng của phương thức:

~~~java
boolean exists = bundle.containsKey("logout");
~~~

`containsKey` trả `true` khi khóa nằm trong bundle hiện tại **hoặc bất kỳ bundle cha nào**; `false` nếu không tồn tại trong toàn chuỗi. Với mô hình ở trên, gọi trên bundle `vi-VN`:

~~~java
bundle.containsKey("greeting"); // true: có ngay tại vi-VN
bundle.containsKey("thanks");   // true: được kế thừa từ vi
bundle.containsKey("logout");   // true: được kế thừa từ gốc
bundle.containsKey("unknown");  // false: không có ở đâu
~~~

Đây là đoạn minh họa, với `bundle` là `ResourceBundle` đã được lấy và nối cha như ví dụ.

**Điểm dễ nhầm:** `containsKey("logout") == true` **không** đồng nghĩa bản dịch tiếng Việt đã có. Nó chỉ nói rằng phép tra cứu khóa sẽ tìm thấy một tài nguyên hiệu lực theo chuỗi cha.

Một số lưu ý:

- Khóa có kiểu `String` và phân biệt chữ hoa/thường: `"logout"` khác `"Logout"`.
- Truyền `null` cho `containsKey` ném `NullPointerException`; kiểm tra input trước nếu key do người dùng cung cấp.
- `containsKey` là phép **kiểm tra sự hiện diện**, không xác nhận kiểu giá trị, chất lượng bản dịch, tính đúng ngôn ngữ hoặc việc string có rỗng hay không.
- Với các bundle thông thường, tài nguyên có giá trị được định nghĩa không nên là `null`; trong `ResourceBundle`, `handleGetObject(key)` trả `null` để biểu thị khóa **không được tìm thấy ở bundle hiện tại** và cho phép tìm cha.

Nếu dùng `containsKey` trước `getString`, cần hiểu cả hai thao tác là hai lần truy vấn riêng. Với tài nguyên bất biến sau khi tải, pattern này hợp lý; khi tự xây bundle động, hãy bảo đảm thread safety và ý nghĩa cập nhật được thiết kế rõ ràng. Không dùng `containsKey` làm cơ chế phát hiện xem một bản dịch cụ thể đã được dịch xong.

## 3. keySet(): tập khóa hiệu lực của cả chuỗi cha

`bundle.keySet()` trả `Set<String>` chứa **tất cả khóa của bundle và cha**, bỏ trùng theo tên khóa. Một khóa bị định nghĩa tại nhiều mức vẫn xuất hiện **một lần** trong tập vì `Set` không chứa phần tử trùng nhau.

Với dữ liệu ở mục 1:

~~~java
Set<String> keys = bundle.keySet();
// Về mặt tập hợp: app.name, greeting, logout, thanks, region
~~~

Không nên mặc định thứ tự duyệt từ `keySet()`: `Set` không hứa thứ tự hiển thị ổn định. Nếu cần output tái lập trong log, test hoặc công cụ QA, sao chép sang `TreeSet`:

~~~java
Set<String> sorted = new TreeSet<>(bundle.keySet());
System.out.println(sorted);
// [app.name, greeting, logout, region, thanks]
~~~

Hai đoạn trên là đoạn mã minh họa; cần import `java.util.Set` và `java.util.TreeSet` cùng với biến `bundle` đã xác định.

**`keySet` không chứa thông tin “khóa này đến từ đâu”.** Tập `["greeting", "logout"]` không cho biết `greeting` có ở `vi-VN` hay `logout` đến từ bundle gốc. Muốn kiểm toán các bản dịch còn thiếu, bạn cần một nguồn khóa cục bộ tại từng lớp hoặc đọc trực tiếp tệp tài nguyên tương ứng.

### So sánh keySet(), getKeys() và handleKeySet()

| API | Phạm vi | Mức truy cập | Kết quả |
| --- | --- | --- | --- |
| `keySet()` | Bundle hiện tại **và cha** | `public` | `Set<String>` |
| `getKeys()` | Bundle hiện tại **và cha** | `public` | `Enumeration<String>` |
| `handleKeySet()` | **Chỉ khóa của bundle hiện tại** | `protected` | `Set<String>` |

`handleKeySet()` được thiết kế chủ yếu cho việc triển khai các subclass của `ResourceBundle`, **không phải API public để một service ngoài lớp bất kỳ gọi trực tiếp**. Mặc định, Java xác định tập khóa cục bộ bằng những khóa có giá trị từ `handleGetObject`; các subclass như `ListResourceBundle` có thể cung cấp cách thực hiện tối ưu hơn.

Trong một subclass, có thể cung cấp phương thức riêng để phục vụ công cụ kiểm thử:

~~~java
class InspectableBundle extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"message", "Hello"}
        };
    }

    Set<String> localKeys() {
        return handleKeySet(); // Chỉ khóa của instance này
    }
}
~~~

Đây chỉ là ví dụ lớp độc lập khi đặt trong tệp Java đã import `java.util.ListResourceBundle` và `java.util.Set`. Nó không tự có chuỗi cha. Đối với `PropertyResourceBundle` do `getBundle` trả về, bạn không thể viết `bundle.handleKeySet()` trong service thông thường vì truy cập `protected`.

Không cố suy ra khóa cục bộ bằng `keySet(child) - keySet(parent)`: một khóa được con ghi đè sẽ cũng có ở cha và bị phép trừ loại bỏ, dù thực tế **con có định nghĩa khóa ấy**.

## 4. Truy cập một khóa theo chuỗi cha

Khi gọi:

~~~java
String text = bundle.getString("logout");
~~~

`ResourceBundle.getString()` gọi cơ chế lấy tài nguyên và ưu tiên đối tượng hiện tại. Nếu tài nguyên không có tại con, nó thử cha, rồi cha của cha, cho đến khi tìm được giá trị hoặc hết chuỗi. Đối với giá trị không phải chuỗi, có `getObject(key)`; đối với mảng chuỗi, có `getStringArray(key)`.

Quy tắc tổng quát:

~~~text
getString("greeting")
   vi-VN: có -> trả "Chào bạn"             (dừng)

getString("thanks")
   vi-VN: không có
       vi: có -> trả "Cảm ơn"              (dừng)

getString("logout")
   vi-VN: không có
       vi: không có
           root: có -> trả "Sign out"      (dừng)

getString("unknown")
   vi-VN: không có
       vi: không có
           root: không có -> MissingResourceException
~~~

Nếu khóa không được tìm thấy trong cả chuỗi cha, `getString`/`getObject` ném `MissingResourceException` — **không trả chuỗi rỗng hoặc `null` để báo vắng khóa**. Việc đọc theo nhầm kiểu (ví dụ thực tế là `String[]` nhưng gọi `getString`) có thể gây `ClassCastException`.

Khi đã tìm thấy một khóa ở con, giá trị ở cha cùng tên **không còn được dùng**. Quy tắc override dựa trên **tên khóa**, không gộp một phần các giá trị phức tạp và không trộn hai chuỗi với nhau. Nếu một thông điệp của con thiếu placeholder hoặc sai ngữ pháp, Java không thể tự ghép nó với bản dịch của cha.

### Nếu con khai báo chuỗi rỗng thì sao?

Ví dụ:

~~~properties
# messages_vi_VN.properties
logout=
~~~

`logout` ở bundle con **có tồn tại** với giá trị là chuỗi rỗng. Vì vậy:

- `containsKey("logout")` là `true`.
- `getString("logout")` trả `""`.
- Java **không** tự bỏ qua chuỗi rỗng để tìm `logout=Sign out` ở cha.

Muốn coi chuỗi rỗng là “thiếu bản dịch”, phải có quy tắc kiểm định tài nguyên hoặc logic nghiệp vụ riêng; cách an toàn thường là phát hiện lúc build/QA, thay vì âm thầm thay đổi nghĩa của một giá trị hợp lệ.

## 5. Ví dụ Java 17+ chạy trong một tệp, minh họa cha và khóa cục bộ

Để quan sát cả `handleKeySet()` (vốn là `protected`) mà không cần tạo nhiều tệp, ví dụ tự xây các đối tượng `ListResourceBundle` và nối cha bằng `setParent`. Đây là **mô hình giảng dạy cùng cơ chế tra cứu của ResourceBundle**, không phải cách bắt buộc để nạp bundle `.properties` trong ứng dụng thực tế.

Tạo **`ParentKeysDemo.java`**:

~~~java
import java.util.ListResourceBundle;
import java.util.MissingResourceException;
import java.util.ResourceBundle;
import java.util.Set;
import java.util.TreeSet;

public class ParentKeysDemo {

    static final class Messages extends ListResourceBundle {
        private final Object[][] entries;

        Messages(ResourceBundle parent, Object[][] entries) {
            this.entries = entries;
            if (parent != null) {
                setParent(parent);
            }
        }

        @Override
        protected Object[][] getContents() {
            return entries;
        }

        // Chỉ dùng trong subclass để quan sát khóa cục bộ.
        Set<String> localKeys() {
            return handleKeySet();
        }
    }

    public static void main(String[] args) {
        Messages root = new Messages(null, new Object[][] {
                {"app.name", "Sample App"},
                {"greeting", "Hello"},
                {"logout", "Sign out"}
        });

        Messages vi = new Messages(root, new Object[][] {
                {"greeting", "Xin chao"},
                {"thanks", "Thanks"}
        });

        Messages viVN = new Messages(vi, new Object[][] {
                {"greeting", "Chao ban"},
                {"region", "Vietnam"}
        });

        System.out.println("Local: "
                + new TreeSet<>(viVN.localKeys()));
        System.out.println("Visible: "
                + new TreeSet<>(viVN.keySet()));

        System.out.println("Inherited key: "
                + viVN.containsKey("logout"));
        System.out.println("Absent key: "
                + viVN.containsKey("missing"));

        System.out.println("Greeting: "
                + viVN.getString("greeting"));
        System.out.println("Thanks: "
                + viVN.getString("thanks"));
        System.out.println("Logout: "
                + viVN.getString("logout"));
        System.out.println("App: "
                + viVN.getString("app.name"));

        try {
            viVN.getString("missing");
        } catch (MissingResourceException ex) {
            System.out.println("Missing: " + ex.getKey());
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac -encoding UTF-8 ParentKeysDemo.java
java ParentKeysDemo
~~~

**Stdout** (đã đối chiếu hành vi thực thi):

~~~text
Local: [greeting, region]
Visible: [app.name, greeting, logout, region, thanks]
Inherited key: true
Absent key: false
Greeting: Chao ban
Thanks: Thanks
Logout: Sign out
App: Sample App
Missing: missing
~~~

Giải thích chi tiết:

1. `root` có ba khóa: `app.name`, `greeting`, `logout`. `vi` khai báo `greeting` và `thanks`, còn `viVN` khai báo `greeting` và `region`.
2. `viVN.localKeys()` gọi `handleKeySet()` ở subclass nên chỉ có `greeting`, `region`.
3. `viVN.keySet()` là hợp của **cả ba tầng**: năm khóa khác nhau. Khóa `greeting` chỉ xuất hiện một lần dù cả ba tầng đều khai báo.
4. `containsKey("logout")` vẫn là `true` vì `logout` tồn tại ở `root`, dù không ở `viVN`.
5. `getString("greeting")` ưu tiên `Chao ban` từ `viVN`, không lấy giá trị `Xin chao` của `vi` hay `Hello` của `root`.
6. `getString("thanks")` lấy từ `vi`; `getString("logout")` và `getString("app.name")` lấy từ `root`.
7. `getString("missing")` ném `MissingResourceException`, được chương trình bắt và in `getKey()`.

Chương trình dùng các giá trị ASCII để stdout không phụ thuộc cấu hình console. Trong bản dịch thực, giá trị hoàn toàn có thể là tiếng Việt Unicode; cơ chế kế thừa khóa hoạt động tương tự.

**Lưu ý về ví dụ:** `setParent` được gọi **một lần khi tạo đối tượng**. Trong ứng dụng thực tế không nên tùy tiện thay đổi cha của bundle đang được nhiều luồng sử dụng. Khi dùng `ResourceBundle.getBundle` thông thường, API tự tổ chức việc nạp và liên kết cha.

## 6. Sử dụng thực tế với các tệp .properties

Giả sử thư mục classpath chứa đúng ba tệp sau, được lưu theo encoding UTF-8:

**`messages.properties`**

~~~properties
app.name=Sample App
greeting=Hello
logout=Sign out
~~~

**`messages_vi.properties`**

~~~properties
greeting=Xin chào
thanks=Cảm ơn
~~~

**`messages_vi_VN.properties`**

~~~properties
greeting=Chào bạn
region=Việt Nam
~~~

Lưu chúng trong cùng vị trí trên classpath (ví dụ `src/main/resources/` với dự án Gradle/Maven thông thường). Khai báo `baseName` là `messages` và yêu cầu `vi-VN`:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

ResourceBundle bundle = ResourceBundle.getBundle(
        "messages",
        Locale.forLanguageTag("vi-VN"),
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES)
);

System.out.println(bundle.getString("greeting")); // Chào bạn
System.out.println(bundle.getString("logout"));   // Sign out
System.out.println(bundle.containsKey("logout")); // true
~~~

**Đây là đoạn mã minh họa** đặt trong một phương thức của chương trình classpath hoặc unnamed module đã import hai lớp. `getNoFallbackControl(FORMAT_PROPERTIES)` được dùng ở đây để **loại bỏ fallback sang locale mặc định của JVM trong bước tìm bundle** và chỉ tìm tệp properties. Nó **không loại bỏ việc truy cập các bundle cha theo locale**: chuỗi `vi-VN → vi → root` vẫn hoạt động với các tệp đã cung cấp.

Cơ chế `ResourceBundle.Control` thuộc mô hình tải bundle có hỗ trợ tham số `Control` (điển hình là classpath/unnamed module). Những overload có `Control` **không hỗ trợ áp dụng như vậy trong named module**; với named module cần dùng cơ chế resource bundle/module/provider theo tài liệu Java tương ứng. Không áp dụng mã ví dụ này máy móc cho mọi hệ triển khai JPMS.

### Vì sao ví dụ có bundle gốc?

Bundle gốc `messages.properties` thường đóng vai trò nguồn thông điệp dự phòng cho các khóa chưa được bản địa hóa. Nếu không có khóa nào ở tất cả các tầng, việc lấy giá trị vẫn thất bại. Nếu không có bundle thích hợp để tải, `ResourceBundle.getBundle(...)` có thể ném `MissingResourceException` ngay tại bước lấy bundle; đây là lỗi khác với **lấy được bundle nhưng thiếu một key**.

Với `PropertyResourceBundle` trên Java 17, tệp properties nạp theo đường tải thông thường được đọc dưới dạng UTF-8, có cơ chế tương thích ngược với ISO-8859-1 khi gặp byte không hợp lệ tùy cấu hình system property. Nên lưu nhất quán UTF-8, kiểm soát đường build/resource copy và kiểm thử ký tự có dấu.

## 7. Hai loại fallback rất dễ bị nhầm

`ResourceBundle` có ít nhất hai giai đoạn cần phân biệt:

### A. Chọn bundle khi tải bằng getBundle()

Ví dụ yêu cầu `vi-VN` nhưng không tồn tại `messages_vi_VN.properties`. Java tìm bundle phù hợp từ các tên ứng viên ít cụ thể hơn và có thể dùng `messages_vi.properties` hoặc `messages.properties`.

Với `ResourceBundle.getBundle(baseName, locale)` mặc định, quy trình còn có thể xét **locale mặc định của JVM** theo quy tắc tải, tùy các tệp có sẵn. Nếu cần hành vi fallback chính xác theo yêu cầu sản phẩm, cấu hình cơ chế tìm bundle phù hợp, đừng giả định mọi ứng dụng luôn đi thẳng về root hoặc luôn đi sang ngôn ngữ của server.

### B. Tìm khóa khi đã có bundle và chuỗi cha

Sau khi bundle được tải, `getString("logout")` tra từ bundle cụ thể qua các parent theo chuỗi đã thiết lập. `containsKey` và `keySet` phản ánh **khóa hiệu lực trong chuỗi đó**. Kết quả của chúng không mô tả chi tiết quá trình Java đã thử những locale ứng viên nào trước khi chọn bundle.

Hai câu hỏi khác nhau:

- “Yêu cầu `fr-CA` được nạp thành bundle nào?” — xem chính sách `getBundle`, `bundle.getLocale()` và danh sách tài nguyên.
- “Bundle đã chọn có thể đọc khóa `logout` không?” — dùng `containsKey`, `keySet`, `getString` xét cả cha.

`bundle.getLocale()` giúp biết locale của **bundle được trả về**, nhưng không cho biết một **khóa cụ thể** nằm ở tầng nào của chuỗi cha.

## 8. Kiểm tra độ phủ bản dịch: đừng dùng keySet() một cách ngây thơ

Giả sử bản dịch `vi-VN` không có `logout` nhưng root có `logout=Sign out`. Mã:

~~~java
if (bundle.containsKey("logout")) {
    System.out.println("Translated");
}
~~~

sẽ in `Translated`, dù thực tế đang lấy tiếng Anh từ root. Đây là lỗi đánh đồng **“có thể đọc”** với **“đã được dịch tại locale này”**.

Để xây công cụ QA bản dịch:

1. Xác định **tập khóa bắt buộc** từ schema, bundle gốc hoặc danh mục chính thức.
2. Đọc **tập khóa định nghĩa thực sự tại mỗi tệp locale**, thay vì dùng `keySet()` của bundle đã được nối cha.
3. So sánh tập khóa cục bộ với tập khóa bắt buộc để tìm khóa chưa dịch, khóa thừa và khóa lỗi chính tả.
4. Kiểm tra nội dung: không rỗng khi yêu cầu bắt buộc, có đủ tham số `{0}`, không làm hỏng cú pháp `MessageFormat`, định dạng đúng ngôn ngữ, không chứa chuỗi tạm.
5. Kiểm thử truy cập ở runtime với `ResourceBundle.getBundle` để chắc chắn cơ chế fallback thực tế hoạt động đúng.

Với tệp `.properties`, một công cụ build có thể đọc trực tiếp từng tệp để lấy khóa cục bộ. Với subclass tự viết, có thể cung cấp API kiểm tra cục bộ dành riêng cho QA, hoặc kiểm tra dữ liệu nguồn của subclass. Không nên dùng reflection để đọc trường `parent` hoặc `handleKeySet` của lớp JDK chỉ để vượt rào `protected`; cách đó dễ vướng module encapsulation và làm code khó bảo trì.

Nếu mục tiêu chỉ là **hiển thị giá trị có thể lấy được**, `keySet()` chính là API phù hợp. Nếu mục tiêu là **đo độ hoàn chỉnh bản dịch**, phải dùng dữ liệu từng locale.

## 9. Xử lý khóa thiếu trong ứng dụng

Có hai cách dùng phổ biến, tùy mức độ quan trọng của nội dung.

### Khóa tùy chọn

Với tooltip hoặc nhãn không bắt buộc, có thể chọn giá trị dự phòng do ứng dụng định nghĩa:

~~~java
String caption = bundle.containsKey("optional.caption")
        ? bundle.getString("optional.caption")
        : "Optional information";
~~~

Đây là đoạn minh họa với biến `ResourceBundle bundle` đã có. Lưu ý `containsKey` vẫn tính cả parent: nếu parent chứa khóa, kết quả sẽ lấy giá trị parent thay vì chuỗi dự phòng thủ công.

Nếu ứng dụng muốn biết **bundle đang chọn có khai báo khóa trực tiếp hay không**, đoạn mã trên không giải quyết được yêu cầu; phải dùng dữ liệu cục bộ như đã phân tích.

### Khóa bắt buộc

Với tiêu đề, nút thanh toán hoặc văn bản pháp lý không thể thiếu, có thể để `getString` ném `MissingResourceException` và xử lý ở điểm kiểm soát thích hợp; tốt hơn là phát hiện thiếu key khi build/test. Việc im lặng hiện tên key (`"payment.submit"`) ra UI có thể giúp debug nhưng thường không phù hợp trong sản phẩm hoàn chỉnh.

**Không dùng `getString(key)` nếu chưa biết tài nguyên có kiểu `String`.** `ResourceBundle` có thể chứa `Object` hoặc `String[]`, trong khi `PropertyResourceBundle` thông thường quản lý chuỗi. Mã dùng nhiều loại bundle phải quy định schema kiểu dữ liệu rõ ràng.

## 10. Những điểm kỹ thuật cần lưu ý

### Thứ tự khóa và hiệu năng

`keySet()` trả `Set`, không bảo đảm thứ tự. Không viết test so sánh trực tiếp `toString()` của Set nếu kỳ vọng thứ tự cố định. Dùng `new TreeSet<>(bundle.keySet())` hoặc `new ArrayList<>(...)` rồi sort.

Trong việc hiển thị UI, thường bạn **biết trước key cần lấy**, không cần duyệt mọi khóa rồi kiểm tra từng khóa. Với thao tác QA hoặc màn hình debug, duyệt `keySet` hợp lý; nếu lặp qua nhiều request, có thể cache cấu trúc đã chuẩn bị thay vì tái tạo danh sách và sắp xếp liên tục.

### Key không phân biệt theo locale, nhưng value thì có

Key thường là định danh kỹ thuật ổn định như `login.button`, `payment.total`, `error.invalidEmail`. **Key phân biệt chữ hoa/thường**, còn giá trị được thay đổi theo locale. Việc đổi tên key ở riêng một tệp locale sẽ khiến parent có thể che lỗi thiếu key bằng giá trị mặc định.

### Bundle cache và cập nhật runtime

`ResourceBundle.getBundle` có cơ chế cache. Việc sửa tệp properties khi ứng dụng đang chạy không có nghĩa lần gọi tiếp theo lập tức đọc nội dung mới. Nếu cần thay tài nguyên động, phải có chiến lược reload và invalidation phù hợp; các API `ResourceBundle.clearCache()` và `ResourceBundle.Control` có vai trò trong bối cảnh hỗ trợ tương ứng.

### Đừng sửa quan hệ cha ngoài lúc thiết lập

Một subclass có thể dùng `setParent`, nhưng không nên tự thay parent giữa các request hoặc chia sẻ cấu trúc đang bị thay đổi giữa các luồng. Dùng chuỗi bundle được xây dựng ổn định và kiểm thử sau khởi tạo. Với subclass tùy chỉnh, hợp đồng của `ResourceBundle` đòi hỏi triển khai an toàn luồng nếu được dùng đồng thời.

### Bundle cha và miền nghiệp vụ

Có thể dùng nhiều family khác nhau như `validation`, `messages`, `errors`. Một bundle cha **không** tự động bao gồm mọi file `.properties` của ứng dụng: quan hệ cha chỉ tồn tại trong **cùng chuỗi bundle** đã được thiết lập. Nếu khóa `notFound` nằm ở family `errors` nhưng bạn đang dùng `messages`, `containsKey` không tự tìm sang family khác.

## 11. Bài tập thực hành

**Bài 1.** Với ba bundle ở mục 1, dự đoán kết quả của các câu lệnh sau trước khi chạy:

~~~java
bundle.containsKey("logout");
bundle.containsKey("region");
bundle.containsKey("unknown");
bundle.getString("greeting");
bundle.getString("thanks");
~~~

**Đáp án:** `true`, `true`, `false`, `"Chào bạn"`, `"Cảm ơn"`. Hai kết quả đầu đều là `true`, nhưng `logout` đến từ root, còn `region` nằm ở bundle `vi-VN`.

**Bài 2.** Vì sao `bundle.keySet().contains("app.name")` vẫn là `true` dù `messages_vi_VN.properties` không khai báo `app.name`?

**Đáp án:** `keySet()` trả tập khóa hợp của bundle hiện tại và các parent. Tên `app.name` được kế thừa từ root.

**Bài 3.** Nếu cả root và `vi-VN` đều có `greeting`, khóa ấy xuất hiện bao nhiêu lần trong `keySet()`? Khi `getString("greeting")` được gọi, Java chọn giá trị nào?

**Đáp án:** Chỉ một lần trong Set. Java chọn giá trị của bundle gần nhất (`vi-VN`) và không đi tiếp tới root.

**Bài 4.** Nếu `messages_vi_VN.properties` có `logout=`, `getString("logout")` có lấy `Sign out` từ root không?

**Đáp án:** Không. Chuỗi rỗng là giá trị của khóa đã được định nghĩa ở con, nên che giá trị ở cha.

**Bài 5.** Một công cụ QA báo mọi khóa trong `bundle.keySet()` đều tồn tại nên kết luận bản dịch `vi-VN` hoàn chỉnh. Kết luận sai ở đâu?

**Đáp án:** `keySet()` bao gồm khóa kế thừa; cần so sánh các key được khai báo **trực tiếp trong tệp bản dịch `vi-VN`** với danh sách khóa bắt buộc và kiểm tra chất lượng value.

**Bài mở rộng.** Bổ sung khóa `logout` ở bundle `vi` trong chương trình một tệp; dự đoán rằng `viVN.containsKey("logout")` không đổi, `viVN.keySet()` không đổi, nhưng `viVN.getString("logout")` đổi sang giá trị ở `vi`. Sau đó xóa khóa này ở `vi` để quan sát fallback trở lại root.

## 12. Checklist kiểm thử và nguyên tắc nhớ

Khi xây dựng kiểm thử ResourceBundle, nên bao phủ:

- Khóa có ngay tại bundle con.
- Khóa thiếu ở con nhưng có ở cha hoặc ông.
- Khóa trùng tên ở con và cha: con override giá trị.
- Khóa không tồn tại ở toàn chuỗi: `containsKey == false`, `getString` ném `MissingResourceException`.
- Khóa có value rỗng ở con: không được nhảy qua cha nếu ứng dụng không định nghĩa logic đặc biệt.
- `keySet()` có hợp các khóa và loại bỏ trùng tên; không phụ thuộc thứ tự.
- Khóa chỉ có ở parent vẫn được nhìn thấy qua `containsKey` và `keySet`.
- Cú pháp key, kiểu tài nguyên, encoding, ResourceBundle cache và quy tắc tải bundle trong môi trường ứng dụng.
- Độ phủ bản dịch được đánh giá trên từng nguồn locale, không từ `keySet()` của bundle đã nối cha.

**Cần nhớ:** `containsKey()` trả lời “khóa có thể tìm được qua chuỗi hiện tại + cha không?”, `keySet()` trả lời “tập mọi khóa có thể tìm được là gì?”, `handleKeySet()` trả lời “riêng bundle hiện tại định nghĩa những khóa nào?” (chỉ truy cập `protected` trong subclass). `getString()/getObject()` ưu tiên giá trị ở con rồi mới tìm cha; thiếu toàn bộ chuỗi thì ném `MissingResourceException`.

### Tài liệu API chính thức

- [ResourceBundle — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html): `containsKey`, `keySet`, `handleKeySet`, `getObject`, chuỗi parent và cơ chế tải bundle.
- [ListResourceBundle — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListResourceBundle.html): khai báo tài nguyên trong mã Java.
- [PropertyResourceBundle — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html): tệp `.properties`, encoding và triển khai bundle từ file.
