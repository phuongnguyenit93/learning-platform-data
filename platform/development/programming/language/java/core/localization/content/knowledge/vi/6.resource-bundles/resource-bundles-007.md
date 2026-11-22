# PropertyResourceBundle so với ListResourceBundle trong Java

## Mục tiêu

Khi ứng dụng Java cần hiển thị nội dung theo ngôn ngữ, `ResourceBundle` cung cấp giao diện chung để tìm tài nguyên theo tên khóa (key) và `Locale`. Hai cách tổ chức tài nguyên tiêu biểu trong thư viện chuẩn là **`PropertyResourceBundle`** — đọc cặp khóa/giá trị từ nội dung định dạng `.properties` — và **`ListResourceBundle`** — lấy tài nguyên từ mã Java qua phương thức `getContents()`.

Sau bài học này, bạn có thể:

- Giải thích điểm chung và điểm khác nhau về **nguồn dữ liệu, kiểu giá trị, biên dịch, phân phối và bảo trì**.
- Tạo bundle từ tệp `.properties` và từ lớp Java `ListResourceBundle`, rồi tra cứu qua một API chung `ResourceBundle.getBundle(...)`.
- Hiểu cách đặt tên bundle theo `Locale`, tìm bundle phù hợp, tìm khóa trong cha và chọn định dạng nguồn khi cả tệp lớp lẫn `.properties` cùng tên.
- Phân biệt `getString(...)` với `getObject(...)` khi giá trị không phải `String`.
- Hiểu quy tắc mã hóa của `PropertyResourceBundle` trên Java 17+, giới hạn của `Reader` và `InputStream`, cùng những lỗi thường gặp.

Bài học tập trung vào **hai hiện thực của ResourceBundle**. Cơ chế lựa chọn locale, bộ lọc ngôn ngữ và quản lý nội dung sản phẩm là những phần liên quan nhưng cần được giữ riêng.

## 1. Điểm chung: cả hai là ResourceBundle

`PropertyResourceBundle` và `ListResourceBundle` đều kế thừa `java.util.ResourceBundle`. Người sử dụng tài nguyên thông thường không cần biết dữ liệu được lưu trong tệp properties hay lớp Java:

```java
ResourceBundle bundle = ResourceBundle.getBundle("Messages", locale);
String greeting = bundle.getString("greeting");
```

Đây là đoạn minh họa dùng trong một phương thức, giả định đã có biến `locale` kiểu `Locale`, và đã nhập `java.util.ResourceBundle`.

Trong mô hình này:

1. **Base name** `"Messages"` đại diện một **họ bundle**.
2. **Locale được yêu cầu** cho biết ngôn ngữ/vùng cần tìm.
3. **Bundle cụ thể** (ví dụ `Messages_vi.properties` hoặc lớp `Messages_en`) cung cấp các khóa và giá trị.
4. **ResourceBundle API** giải quyết candidate, parent/fallback và tra cứu khóa.

`ResourceBundle` quyết định quá trình lựa chọn và tra cứu; mỗi lớp con quyết định **cách lưu các cặp khóa/giá trị của riêng nó**. Vì vậy, hai hiện thực có thể thay thế cho nhau ở cấp gọi API, nhưng khác nhau khi viết và bảo trì nguồn tài nguyên.

`ResourceBundle` cũng có bộ đệm (cache) và chiến lược fallback. Việc sửa tệp nguồn trên đĩa **không bảo đảm** lần gọi `getBundle` kế tiếp đọc lại ngay; vấn đề cache thuộc lớp `ResourceBundle`, không riêng một kiểu bundle.

## 2. So sánh tổng quan

| Tiêu chí | `PropertyResourceBundle` | `ListResourceBundle` |
| --- | --- | --- |
| Nguồn dữ liệu | Nội dung dạng Java `.properties` | Một lớp Java kế thừa `ListResourceBundle` |
| Định nghĩa tài nguyên | Các dòng `key=value`, dấu phân tách và escape của properties | Override `protected Object[][] getContents()` |
| Kiểu key | `String` | `String` |
| Kiểu value | `String` | `Object` — có thể là `String`, `Integer`, `String[]`, v.v. |
| Có cần biên dịch mã dịch thuật? | Không cần biên dịch `.properties`, nhưng phải đóng gói như classpath resource | Có, vì giá trị được khai báo trong mã Java |
| Cách đặt tên theo locale | `Messages.properties`, `Messages_vi.properties`, … | `Messages`, `Messages_vi`, … (các lớp Java công khai tương ứng) |
| Trường hợp phù hợp | Thông điệp giao diện, nhãn và văn bản dịch do người dịch quản lý | Tài nguyên có kiểu đối tượng, tài nguyên tạo thuận tiện bằng mã Java |
| Rủi ro thường gặp | Sai tên/đường dẫn resource, lỗi escape/encoding, thiếu key | Sai cấu trúc `Object[][]`, lớp không tải được, thay đổi tài nguyên phải biên dịch lại |

Chọn loại nào phụ thuộc nội dung:

- **Văn bản, nhãn, câu thông báo, mẫu `MessageFormat`**: tệp `.properties` thường dễ chỉnh sửa, diff và giao cho người dịch.
- **Dữ liệu thật sự cần kiểu Java** (như mảng chuỗi, số, đối tượng bất biến): `ListResourceBundle` có thể phù hợp.
- Một bộ tài nguyên pha trộn vẫn được, nhưng cần đặt tên, quy tắc tải và kiểu giá trị nhất quán để tránh tác dụng phụ khó dự đoán.

Không phải vì `ListResourceBundle` viết bằng Java mà nó tự dịch văn bản, và không phải vì `PropertyResourceBundle` dùng tệp đơn giản mà nó tự cập nhật khi file đổi.

## 3. PropertyResourceBundle: cặp khóa và chuỗi trong .properties

Một tệp properties có thể trông như sau:

```properties
# Messages.properties
greeting=Hello
help=Contact support
source=Root bundle
```

Bản tiếng Việt:

```properties
# Messages_vi.properties
greeting=Xin chào
help=Liên hệ hỗ trợ
```

Những tệp này thuộc cùng họ bundle có base name `Messages`.

Khi gọi:

```java
ResourceBundle vi = ResourceBundle.getBundle(
        "Messages", Locale.forLanguageTag("vi-VN"));
```

`ResourceBundle` có thể chọn `Messages_vi.properties` cho locale `vi-VN` vì không có biến thể `vi_VN` riêng. Nếu bản tiếng Việt thiếu key `source`, tài nguyên ở base bundle `Messages.properties` có thể được dùng qua parent chain.

Tệp `.properties` không chứa biểu thức Java thực thi. Giá trị như:

```properties
maxRetries=3
enabled=true
```

vẫn là các chuỗi `"3"` và `"true"` khi đọc qua `PropertyResourceBundle`. Nếu cần `int` hoặc `boolean`, mã ứng dụng phải kiểm tra và chuyển đổi:

```java
int retries = Integer.parseInt(bundle.getString("maxRetries"));
boolean enabled = Boolean.parseBoolean(bundle.getString("enabled"));
```

Đây là đoạn minh họa trong phương thức có biến `bundle`. Với đầu vào có thể bị sửa, hãy kiểm tra giá trị và xử lý `NumberFormatException` thích hợp.

### Quy tắc cú pháp .properties

- `=` và `:` có thể phân cách key với value; whitespace cũng có thể đóng vai trò dấu phân cách theo định dạng properties.
- Dòng bắt đầu bằng `#` hoặc `!` là comment (sau khoảng trắng đầu dòng cho phép).
- Dấu gạch chéo ngược `\` dùng cho escape, chẳng hạn `\n` và `\uXXXX`; một số ký tự đặc biệt trong key cần escape.
- Phần continuation dùng dấu `\` ở cuối dòng vật lý có quy tắc riêng. Đừng suy ra văn bản hiển thị sẽ luôn giữ newline chỉ vì file xuống dòng.

Vì vậy, khi viết thông điệp có dấu `:`, `=` hoặc `\`, cần phân biệt vị trí key/value và kiểm thử giá trị tải ra. Java properties **không phải JSON, YAML hay Java source**, và không tự giải thích placeholder của `MessageFormat`: placeholder chỉ được xử lý nếu bạn truyền chuỗi vào formatter thích hợp.

### Mã hóa trên Java 17+

Đây là điểm dễ nhầm do tài liệu cũ:

- **Từ Java 9**, cơ chế đọc `PropertyResourceBundle` qua byte stream ưu tiên **UTF-8**. Với chuỗi byte không hợp lệ UTF-8, hành vi mặc định có thể đọc lại bằng **ISO-8859-1** để tương thích với nguồn cũ.
- System property `java.util.PropertyResourceBundle.encoding` được đặt thành `UTF-8` hoặc `ISO-8859-1` có thể yêu cầu một encoding cụ thể cho quá trình đọc byte stream. Nếu ép UTF-8, byte không hợp lệ có thể gây lỗi thay vì fallback.
- Property encoding nói trên được xét khi **lớp `PropertyResourceBundle` được khởi tạo**. Đổi property giữa chừng không phải cách đáng tin để đổi encoding của các bundle đã tải.
- Constructor `PropertyResourceBundle(Reader)` dùng các ký tự mà `Reader` đã giải mã; **charset là trách nhiệm của mã tạo Reader**, không phải của constructor này.

Vì thế, trên Java 17+, thường có thể viết trực tiếp `greeting=Xin chào` trong `Messages_vi.properties` được lưu UTF-8. Đừng áp dụng máy móc quan niệm “properties chỉ đọc ISO-8859-1 và luôn phải escape mọi ký tự Unicode” của các môi trường Java cũ.

Lưu ý: `java.util.Properties.load(InputStream)` là API khác với cơ chế đọc của `PropertyResourceBundle`. Không suy ra chúng có cùng hợp đồng encoding chỉ vì cùng cú pháp tệp.

### Constructor trực tiếp khác với getBundle

Có thể tạo riêng một `PropertyResourceBundle` từ `InputStream` hoặc `Reader`:

```java
import java.io.StringReader;
import java.util.PropertyResourceBundle;

PropertyResourceBundle direct = new PropertyResourceBundle(
        new StringReader("greeting=Xin chào\n"));
String greeting = direct.getString("greeting");
```

Đây là đoạn minh họa đặt trong một phương thức có khả năng xử lý hoặc khai báo `IOException`. `StringReader` đã cung cấp chuỗi Unicode nên không có bước giải mã UTF-8 trong `PropertyResourceBundle`.

Khi tạo bundle trực tiếp như vậy, bạn tự quản lý nguồn và không tự động nhận đầy đủ quá trình giải quyết tên, locale, cache và parent chain của `ResourceBundle.getBundle(...)`. Với tập thông điệp đa ngôn ngữ thông thường, `getBundle` là điểm vào thuận tiện hơn.

## 4. ListResourceBundle: lớp Java trả về Object[][]

`ListResourceBundle` là lớp trừu tượng (`abstract`). Để tạo bundle, viết một lớp con public và override `getContents()`:

```java
import java.util.ListResourceBundle;

public class Messages_en extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
            {"greeting", "Hello from Java class"},
            {"maxRetries", Integer.valueOf(3)},
            {"enabled", Boolean.TRUE}
        };
    }
}
```

Lưu trong `Messages_en.java` và biên dịch thành `Messages_en.class`.

Mỗi hàng trong `Object[][]` có đúng **hai phần tử**: key và value. Key phải là `String`, còn value có thể là đối tượng Java thích hợp. Không được đặt key trùng nhau hoặc value không hợp lệ rồi giả định loader tự giải quyết rõ ràng mọi xung đột. Tốt nhất giữ key duy nhất, giá trị khác null và bộ dữ liệu dễ kiểm thử.

Khi gọi:

```java
ResourceBundle en = ResourceBundle.getBundle(
        "Messages", Locale.forLanguageTag("en-GB"));

String message = en.getString("greeting");
Integer retries = (Integer) en.getObject("maxRetries");
Boolean enabled = (Boolean) en.getObject("enabled");
```

Đây là đoạn minh họa trong phương thức có `import java.util.ResourceBundle;` và `import java.util.Locale;`.

Điều quan trọng là **giá trị có kiểu**:

- `getObject(key)` trả `Object`, có thể cast sau khi biết hoặc kiểm tra kiểu.
- `getString(key)` chỉ thích hợp khi giá trị thực sự là `String`.
- `getStringArray(key)` dành cho giá trị `String[]`.
- Gọi `getString("maxRetries")` đối với `Integer.valueOf(3)` sẽ gây `ClassCastException`; kiểu runtime không tự chuyển số thành văn bản cho bạn.

Không nên dùng `ListResourceBundle` như kho bất kỳ object tùy ý có trạng thái thay đổi. Tài nguyên được cache và có thể được nhiều luồng sử dụng; các giá trị bất biến hoặc được quản lý thread-safe giúp tránh lỗi đồng thời. Một bundle chứa mảng mutable cũng cần chiến lược bảo vệ nếu trả tham chiếu trực tiếp cho mã gọi.

### Khi nào ListResourceBundle hữu ích?

Có những tình huống muốn biểu diễn tài nguyên vốn không tự nhiên là một chuỗi, ví dụ danh sách lựa chọn cố định, dãy tên đã tổ chức hoặc giá trị cần giữ kiểu mà không phải parse từ văn bản. Khi ấy khai báo bằng Java có thể rõ ràng.

Mặt trái là người dịch thường cần đụng vào mã nguồn hoặc một quy trình tạo Java class; file phải được biên dịch và phát hành cùng ứng dụng. Nếu tất cả giá trị đều là văn bản giao diện, `.properties` thường đơn giản và dễ bảo trì hơn.

## 5. Ví dụ hoàn chỉnh: hai cách khai báo cùng một họ bundle

Ví dụ sau chạy trên **Java 17+** và chứng minh:

1. `ResourceBundle.getBundle(...)` có thể tải `Messages_en.class` lẫn `Messages_vi.properties` trong cùng một họ.
2. Giá trị của lớp Java có thể là `Integer`.
3. Khóa không có ở bản địa phương hóa có thể được lấy từ bundle gốc.
4. `getString(...)` không tự ép kiểu một `Integer`.

Tạo bốn tệp sau trong **cùng một thư mục**.

### Tệp 1: Messages.properties

```properties
greeting=Hello from root
help=Help from root
origin=Root resource
```

### Tệp 2: Messages_vi.properties

Lưu bằng **UTF-8**:

```properties
greeting=Xin chào
help=Trợ giúp bằng tiếng Việt
```

### Tệp 3: Messages_en.java

```java
import java.util.ListResourceBundle;

public class Messages_en extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
            {"greeting", "Hello from Java class"},
            {"maxRetries", Integer.valueOf(3)},
            {"enabled", Boolean.TRUE}
        };
    }
}
```

### Tệp 4: BundleTypesDemo.java

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleTypesDemo {
    public static void main(String[] args) {
        ResourceBundle english = ResourceBundle.getBundle(
                "Messages", Locale.forLanguageTag("en-GB"));

        ResourceBundle vietnamese = ResourceBundle.getBundle(
                "Messages", Locale.forLanguageTag("vi-VN"));

        System.out.println(english.getClass().getSimpleName());
        System.out.println(english.getString("greeting"));
        System.out.println(english.getString("help"));
        System.out.println(english.getObject("maxRetries"));

        System.out.println(vietnamese.getClass().getSimpleName());
        System.out.println(vietnamese.getString("greeting"));
        System.out.println(vietnamese.getString("help"));
        System.out.println(vietnamese.getString("origin"));

        try {
            english.getString("maxRetries");
        } catch (ClassCastException ex) {
            System.out.println("Wrong type for getString");
        }
    }
}
```

Mở terminal tại thư mục chứa cả bốn tệp và chạy:

```bash
javac -encoding UTF-8 Messages_en.java BundleTypesDemo.java
java -cp . BundleTypesDemo
```

Stdout mong đợi:

```text
Messages_en
Hello from Java class
Help from root
3
PropertyResourceBundle
Xin chào
Trợ giúp bằng tiếng Việt
Root resource
Wrong type for getString
```

Giải thích kết quả:

- `en-GB` không có bản riêng `Messages_en_GB`, nên chọn bản ngôn ngữ `Messages_en` (lớp Java). Lớp này có `greeting`, `maxRetries` và `enabled`.
- `help` không được khai báo ở `Messages_en`, nên lời gọi lấy được giá trị từ `Messages.properties`, là tài nguyên gốc.
- `vi-VN` không có bản riêng `Messages_vi_VN`, nên tìm `Messages_vi.properties`. Các khóa tiếng Việt được đọc từ tệp UTF-8; `origin` lấy từ tài nguyên gốc.
- `getClass().getSimpleName()` cho biết kiểu hiện thực được trả về trong ví dụ. Kiểm tra kiểu chỉ để **quan sát**; mã sản phẩm thường nên dùng giao diện `ResourceBundle`.
- `maxRetries` trong lớp Java là `Integer`, nên `getObject` trả đối tượng số. `getString` trên cùng key gây `ClassCastException` và được bắt để in dòng cuối.

Kết quả không phụ thuộc locale mặc định của JVM vì hai locale được yêu cầu đều có bundle tương ứng, và base bundle luôn có sẵn. Để giữ đúng kết quả, hãy đảm bảo không có các lớp/tệp `Messages*` khác cùng tên trong classpath.

Trong dự án có package, phải nhất quán với tên đầy đủ: ví dụ lớp `com.example.i18n.Messages_en` và resource `com/example/i18n/Messages_vi.properties`, sau đó gọi `getBundle("com.example.i18n.Messages", locale)`.

## 6. ResourceBundle lựa chọn .class hay .properties ra sao?

Khi dùng `ResourceBundle.getBundle(baseName, locale)` với cơ chế mặc định cho classpath thông thường, quá trình tìm kiếm được định hướng bởi **base name**, **locale candidates** và **định dạng được phép**.

Ví dụ với `Messages` và yêu cầu `en-GB`, các ứng viên liên quan có thể là:

```text
Messages_en_GB
Messages_en
Messages
```

Với mỗi ứng viên, bộ tải xem có lớp Java thích hợp hay tệp `.properties` thích hợp hay không. **Ở cùng một candidate name**, thứ tự định dạng mặc định là **`java.class` trước `java.properties`**. Vì vậy, nếu đồng thời có lớp `Messages_en` và tệp `Messages_en.properties`, trong cơ chế classpath mặc định, lớp Java được ưu tiên cho candidate `Messages_en`.

Tuy nhiên, **độ cụ thể của locale cũng quan trọng**: một tệp `Messages_en_GB.properties` cho locale cụ thể hơn có thể được chọn trước lớp `Messages_en`. Không diễn giải “class được ưu tiên” thành “mọi class trong họ bundle luôn thắng mọi tệp properties”.

### Các trường hợp cần ghi nhớ

| Tình huống | Kết quả thường thấy với lookup mặc định |
| --- | --- |
| Có `Messages_vi.properties` và yêu cầu `vi-VN` | Chọn bản `vi` khi không có `vi_VN` phù hợp |
| Có `Messages_en.class`, `Messages_en.properties` ở cùng candidate | Bản `.class` có ưu tiên định dạng |
| Có `Messages_en_GB.properties` và `Messages_en.class`, yêu cầu `en-GB` | Ưu tiên candidate cụ thể `en_GB` |
| Bản đã chọn thiếu một key, bundle cha có key | Tìm key qua parent chain |
| Không có bundle nào tìm được theo cơ chế fallback | `MissingResourceException` có thể được ném |
| Một key có trong cả con và cha | Giá trị tại con che giá trị cùng key của cha |

Lookup và fallback không đơn giản chỉ là thay chuỗi `"vi-VN"` thành `"vi"`. Với một số đầu vào thiếu ứng viên, cơ chế mặc định có thể xét default locale của JVM rồi tới bundle gốc. Kết quả phụ thuộc cấu hình runtime, class loader, custom `ResourceBundle.Control` hoặc module nếu ứng dụng sử dụng những cơ chế đó.

Vì thế, **không nên xem mọi lần lookup thất bại của ngôn ngữ được yêu cầu đều lập tức chọn base bundle**. Để đưa ra quyết định ngôn ngữ có thể đoán trước trong ứng dụng, hãy giải quyết danh sách locale sản phẩm hỗ trợ trước khi tra tài nguyên.

### Tránh đè tên ngoài ý muốn

Trong ví dụ, lớp `Messages_en` và file `Messages_vi.properties` hỗ trợ hai locale khác nhau nên rõ ràng. Nếu dự án vô tình đóng gói **cả** `Messages_en.class` và `Messages_en.properties`, đội ngũ có thể chỉnh properties mà không thấy thay đổi vì class được chọn trước.

Khi chuyển một họ bundle từ loại này sang loại kia, hãy kiểm tra artifact cuối (JAR/classpath), loại bỏ tài nguyên cũ gây che khuất và kiểm thử đầu ra của các locale được hỗ trợ. Không chỉ nhìn nội dung thư mục nguồn.

## 7. Kiểu giá trị: điểm khác biệt ảnh hưởng trực tiếp đến API

`PropertyResourceBundle` cung cấp chuỗi. `ListResourceBundle` có thể cung cấp những kiểu object tùy mục đích.

```java
protected Object[][] getContents() {
    return new Object[][] {
        {"title", "Welcome"},
        {"retryCount", Integer.valueOf(5)},
        {"tabs", new String[] {"home", "settings"}}
    };
}
```

Đây là nội dung minh họa cho override `getContents()` bên trong một lớp kế thừa `ListResourceBundle`, không phải chương trình độc lập.

Khi dùng tài nguyên này:

```java
String title = bundle.getString("title");
int count = (Integer) bundle.getObject("retryCount");
String[] tabs = bundle.getStringArray("tabs");
```

Các biểu thức minh họa trên giả định biến `bundle` đã chứa bundle tương ứng.

Nếu vô tình thay `retryCount` từ `Integer` thành chuỗi `"5"`, phép cast sang `Integer` sẽ thất bại. Đây là một thay đổi **hợp đồng kiểu**, dù key giữ nguyên. Ngược lại, khi dùng properties, app thường phải parse `"5"` thành `int` ở tầng sử dụng và xử lý dữ liệu không hợp lệ.

Không nên đưa giá trị kiểu bất kỳ vào `ListResourceBundle` chỉ để tránh parse. Với các nhãn giao diện, cả đội phát triển và người dịch thường dễ kiểm tra văn bản hơn khi khóa và giá trị đều là `String`.

## 8. Thiếu key, cache và lỗi tải tài nguyên

### Thiếu key

`getString("missingKey")` không trả chuỗi rỗng mặc định. Nếu key không có ở bundle hiện tại và các bundle cha, `ResourceBundle` ném `MissingResourceException`. Cách xử lý nên phù hợp chính sách sản phẩm:

- Trong phát triển/test: phát hiện key thiếu sớm để tránh phát hành giao diện thiếu dịch.
- Trong production: fallback thông điệp đã xác định hoặc log được kiểm soát; không âm thầm trả null rồi gây `NullPointerException` ở nơi khác.
- Khi dịch thuật: giữ key nhất quán và tránh đổi key mà chưa cập nhật mọi bản địa phương hóa.

Key trong resource bundle có phân biệt chữ hoa/chữ thường. `title` và `Title` là hai key khác nhau.

### Cache

`ResourceBundle.getBundle(...)` có cơ chế cache bundle đã giải quyết. Cập nhật trực tiếp `Messages_vi.properties` trên đĩa trong lúc ứng dụng chạy **không** có nghĩa bundle đang được giữ và mọi lần lookup tiếp theo tự cập nhật ngay.

Tùy nhu cầu, có thể dùng `ResourceBundle.clearCache()` (hoặc overload theo class loader) và quản lý quy trình tải lại phù hợp. Việc clear cache không sửa các tham chiếu `ResourceBundle` đã được code lưu từ trước; cũng không bảo đảm mọi class loader, module và framework nạp lại theo cùng cách. Nếu yêu cầu hot-reload tài nguyên, cần thiết kế và kiểm thử quy trình cụ thể.

### Lỗi cấu hình

- Đặt sai base name hoặc đặt resource ngoài classpath có thể dẫn đến `MissingResourceException`.
- Java class bundle không load được (sai visibility/package/constructor) có thể bị bỏ qua trong quá trình tìm ứng viên hoặc gây lỗi tùy đường tải; phải kiểm tra nguyên nhân class loading.
- Tệp `.properties` có escape sai có thể gây `IllegalArgumentException` trong quá trình parse.
- Việc ép encoding UTF-8 với byte không hợp lệ có thể dẫn tới lỗi mã hóa khi đọc `PropertyResourceBundle`.
- Dữ liệu `Object[][]` không đúng hợp đồng (key không phải `String`, null value, trùng key) là lỗi của lớp `ListResourceBundle`; không kỳ vọng `ResourceBundle` tự khắc phục nội dung không hợp lệ.

Để kiểm tra nhanh, hãy xác minh **tên base**, **đường dẫn package**, **class loader**, **artifact thực sự có trong runtime**, **locale yêu cầu**, và **nguồn tài nguyên được chọn**.

## 9. Khi nào nên chọn từng loại?

Chọn `PropertyResourceBundle` khi:

- Nội dung chủ yếu là văn bản dịch, nhãn, thông điệp lỗi, template hiển thị.
- Người dịch hoặc pipeline localization cần sửa dữ liệu mà không phải sửa mã Java.
- Bạn cần diff các bộ khóa/giá trị giữa những ngôn ngữ và kiểm tra key thiếu.
- Bạn muốn giữ nguồn dịch tách khỏi logic Java.

Chọn `ListResourceBundle` khi:

- Tài nguyên là các object Java có kiểu và giữ kiểu đem lại lợi ích thật.
- Một số giá trị cấu trúc khó diễn đạt rõ bằng properties dạng chuỗi.
- Bạn kiểm soát việc biên dịch và phát hành class tài nguyên.
- Nhóm phát triển có test kiểm tra các key và kiểu giá trị.

Có thể pha trộn hai cách trong cùng họ, như ví dụ, nhưng phải nắm **quy tắc lựa chọn nguồn**, **kiểu trả về** và **parent fallback**. Một hệ thống phức tạp đôi khi nên tách một phần dữ liệu có cấu trúc ra khỏi `ResourceBundle` thay vì nhét mọi thứ vào danh sách đa kiểu.

### Checklist triển khai

1. Chọn base name ổn định như `com.example.i18n.Messages`.
2. Đặt đúng tên từng bản ngôn ngữ theo quy tắc locale candidate của Java.
3. Đảm bảo class và properties được đóng gói vào classpath/module đúng vị trí.
4. Thống nhất key giữa các locale và kiểm tra key thiếu.
5. Giữ kiểu giá trị ổn định đối với code gọi `getObject`/`getStringArray`.
6. Lưu `.properties` bằng UTF-8 trên Java 17+ và có test cho Unicode.
7. Nếu chuyển từ file sang class hoặc ngược lại, kiểm tra không còn tài nguyên cùng tên che khuất.
8. Quyết định rõ chính sách fallback, cache/reload và danh sách locale được hỗ trợ.

## 10. Các câu hỏi tự kiểm tra

**Câu 1.** Nếu `Messages_vi.properties` có `count=5`, `getObject("count")` trả kiểu gì? Vì sao không thể cast thẳng sang `Integer` như khi lấy từ `ListResourceBundle` có `Integer.valueOf(5)`?

**Câu 2.** Ứng dụng có cả `Messages_en.class` và `Messages_en.properties`. Với cùng candidate `Messages_en` và lookup mặc định, dữ liệu ở đâu được ưu tiên? Nếu thêm `Messages_en_GB.properties` và yêu cầu `en-GB`, vị trí ưu tiên của candidate cụ thể thay đổi thế nào?

**Câu 3.** Bundle `Messages_vi.properties` thiếu key `help` nhưng `Messages.properties` có key này. Tại sao `getString("help")` vẫn có thể trả giá trị? Nếu cả bundle cha không có key, ngoại lệ nào xảy ra?

**Câu 4.** Vì sao `PropertyResourceBundle` trên Java 17+ không cần bắt buộc dùng Unicode escape cho mọi ký tự tiếng Việt? Tại sao constructor nhận `Reader` lại không tự giải mã UTF-8?

**Câu 5.** Nếu bạn sửa `Messages_vi.properties` khi ứng dụng đang chạy, liệu tham chiếu `ResourceBundle` đang được giữ có tự động đổi giá trị không? Cơ chế cache ảnh hưởng thế nào?

**Câu 6.** Bộ tài nguyên hiện tại chỉ chứa thông điệp `String`. Hãy giải thích tại sao một nhóm có nhiều người dịch có thể ưu tiên `PropertyResourceBundle`, và trường hợp nào thực sự đáng dùng `ListResourceBundle`.

## 11. Kết luận

`PropertyResourceBundle` và `ListResourceBundle` cùng thực hiện hợp đồng `ResourceBundle` nhưng có nguồn và kiểu dữ liệu khác nhau. **PropertyResourceBundle** đọc tài nguyên kiểu properties và biểu diễn giá trị bằng `String`, rất hợp với văn bản bản địa hóa. **ListResourceBundle** lấy tài nguyên từ `Object[][]` trong lớp Java, hỗ trợ giá trị là đối tượng có kiểu nhưng đòi hỏi biên dịch và kiểm soát hợp đồng kiểu.

Ở lớp sử dụng, `ResourceBundle.getBundle(baseName, locale)` giải quyết việc chọn bản phù hợp, parent/fallback và tra cứu khóa. Hãy hiểu ưu tiên class-vs-properties theo **cùng candidate**, giữ sự khác biệt giữa candidate cụ thể và định dạng nguồn, và kiểm thử cả Unicode lẫn key/type khi phát hành.

Tài liệu API tham khảo: [`ResourceBundle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html), [`PropertyResourceBundle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html), [`ListResourceBundle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListResourceBundle.html) (Java SE 17).
