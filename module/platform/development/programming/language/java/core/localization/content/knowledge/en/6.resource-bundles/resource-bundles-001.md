# Tách văn bản khỏi mã nguồn bằng khóa tài nguyên

## 1. Vì sao không nên viết cố định văn bản giao diện trong Java?

Một ứng dụng có thể có nhiều loại văn bản hướng tới người dùng: tiêu đề trang, nhãn nút, thông báo xác nhận, lỗi nhập liệu và lời chào. Nếu mỗi vị trí đều chứa trực tiếp một chuỗi tiếng Việt trong mã Java, việc thay đổi câu chữ hoặc thêm tiếng Anh sẽ buộc lập trình viên tìm và sửa nhiều vị trí:

```java
System.out.println("Xin chào, " + name + "!");
System.out.println("Bạn có muốn đăng xuất?");
```

Khi xuất hiện yêu cầu đổi ngôn ngữ, cách viết này dễ dẫn đến các nhánh điều kiện rải rác:

```java
String greeting = locale.getLanguage().equals("vi")
        ? "Xin chào, " + name + "!"
        : "Hello, " + name + "!";
```

Ban đầu chỉ có hai ngôn ngữ, nhưng khi thêm ngôn ngữ, cùng một thông điệp phải được cập nhật tại nhiều vị trí. Văn bản cũng bị gắn chặt với logic xử lý.

Giải pháp là **định nghĩa một khóa tài nguyên ổn định cho mỗi thông điệp**, lưu giá trị hiển thị trong tệp tài nguyên tương ứng với từng ngôn ngữ và dùng Java để tra cứu theo `Locale`.

Ví dụ:

| Khóa kỹ thuật | Giá trị tiếng Việt | Giá trị tiếng Anh |
| --- | --- | --- |
| `app.title` | `Ví dụ ResourceBundle` | `ResourceBundle demo` |
| `greeting` | `Xin chào, {0}!` | `Hello, {0}!` |
| `logout.confirm` | `Bạn muốn đăng xuất?` | `Do you want to sign out?` |

**Khóa** đóng vai trò định danh trong mã nguồn; **giá trị** là nội dung có thể bản địa hóa. Một thao tác Java vẫn gọi `getString("logout.confirm")` bất kể văn bản hiển thị đang là tiếng Việt hay tiếng Anh.

Bài này tập trung vào **tách văn bản khỏi mã Java bằng khóa tài nguyên** trong `ResourceBundle`: cách tổ chức tệp, tra cứu, tham số hóa, fallback, quản lý khóa và kiểm thử. Đây là nền tảng để mở rộng hệ thống đa ngôn ngữ có thể bảo trì.

## 2. ResourceBundle và quan hệ giữa base name, key, value, Locale

`java.util.ResourceBundle` là API của Java để lấy tài nguyên dựa trên `Locale`. Một tập tài nguyên có **base name** chung và có thể gồm nhiều biến thể theo ngôn ngữ, vùng hoặc script.

Ví dụ chọn base name `messages`:

```text
messages.properties       # tài nguyên gốc (root)
messages_vi.properties    # tiếng Việt
messages_en.properties    # tiếng Anh
```

Trong mỗi tệp `.properties`, nội dung điển hình là các cặp `key=value`. Với `ResourceBundle`, key là một `String`; `getString(key)` đọc giá trị tương ứng. Phần hậu tố của tên file cho biết locale; nó **không** phải một phần của key.

Ba thành phần độc lập:

1. `baseName` (`"messages"`): nhóm tài nguyên muốn tìm.
2. `locale` (ví dụ `Locale.forLanguageTag("vi-VN")`): ngôn ngữ hoặc biến thể mong muốn.
3. `key` (`"greeting"`): thông điệp cụ thể trong nhóm.

Lệnh cơ bản:

```java
ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);
String text = bundle.getString("app.title");
```

Java xác định bundle phù hợp thông qua các candidate locale, tìm tài nguyên trên classpath/module path theo quy tắc của API và có thể dùng bundle cha để tra cứu key còn thiếu. **Một key không giống một đường dẫn tệp**; `getString("app.title")` tra cứu khóa trong bundle đã nạp.

Ngoài `.properties`, ResourceBundle còn có thể dùng các lớp `ListResourceBundle` hoặc provider tùy môi trường. Với bài toán văn bản UI thông thường, `.properties` dễ đọc, dễ phiên dịch và giúp logic Java ít thay đổi khi cập nhật câu chữ.

## 3. Ví dụ hoàn chỉnh với tệp .properties và chương trình Java 17+

Tạo bốn tệp **cùng một thư mục**:

```text
localization-demo/
├── ResourceBundleDemo.java
├── messages.properties
├── messages_vi.properties
└── messages_en.properties
```

Nội dung tệp `messages.properties`, đóng vai trò bundle gốc:

```properties
app.title=ResourceBundle demo
greeting=Hello, {0}!
logout.confirm=Do you want to sign out?
```

Nội dung tệp `messages_vi.properties`:

```properties
app.title=Ví dụ ResourceBundle
greeting=Xin chào, {0}!
logout.confirm=Bạn muốn đăng xuất?
```

Nội dung tệp `messages_en.properties`:

```properties
app.title=ResourceBundle demo
greeting=Hello, {0}!
logout.confirm=Do you want to sign out?
```

Nội dung tệp `ResourceBundleDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class ResourceBundleDemo {

    private static void show(Locale locale) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("messages", locale);

        String title = bundle.getString("app.title");
        String greetingPattern = bundle.getString("greeting");

        MessageFormat formatter =
                new MessageFormat(greetingPattern, locale);
        String greeting = formatter.format(new Object[] {"Mai"});

        System.out.println(locale.toLanguageTag());
        System.out.println(title);
        System.out.println(greeting);
        System.out.println(bundle.getString("logout.confirm"));
    }

    public static void main(String[] args) {
        show(Locale.forLanguageTag("vi-VN"));
        show(Locale.forLanguageTag("en-US"));
    }
}
```

Lưu các tệp văn bản bằng UTF-8. Với JDK 17+:

```bash
javac -encoding UTF-8 ResourceBundleDemo.java
java -cp . ResourceBundleDemo
```

Stdout chính xác:

```text
vi-VN
Ví dụ ResourceBundle
Xin chào, Mai!
Bạn muốn đăng xuất?
en-US
ResourceBundle demo
Hello, Mai!
Do you want to sign out?
```

Giải thích:

- `vi-VN` được yêu cầu, Java có thể rút candidate locale về `vi`, vì vậy bundle `messages_vi.properties` được chọn.
- `en-US` dùng bundle `messages_en.properties` vì nó có phần ngôn ngữ `en`.
- Cùng key `greeting` nhưng giá trị trả về khác nhau theo locale.
- `{0}` trong văn bản là tham số do `MessageFormat` thay bằng tên `Mai`. Tên không bị hard-code vào bản dịch và translator có thể đặt tham số ở vị trí phù hợp với ngữ pháp.
- Chuỗi gốc `messages.properties` là một nơi bổ sung tài nguyên mặc định và là nguồn fallback ở những trường hợp được quy tắc `ResourceBundle` cho phép.

Thư mục chứa các tệp `.properties` phải nằm trên classpath khi chạy. Trong ví dụ `-cp .` khiến chương trình tìm các file cạnh `.class`. Nếu đặt file bên trong package `com.example.i18n`, base name có thể là `"com.example.i18n.messages"`; đường dẫn tài nguyên trong classpath phải tương ứng.

**Trong dự án Maven/Gradle:** vị trí thông thường là `src/main/resources/messages.properties`, `src/main/resources/messages_vi.properties`, v.v. Trong code, gọi `ResourceBundle.getBundle("messages", locale)`. Build system thường sao chép `src/main/resources` vào output classpath; không cần tự đọc file bằng `FileInputStream` để tra cứu thông điệp.

## 4. Thiết kế khóa tài nguyên có thể duy trì lâu dài

Tên khóa tốt là **định danh có ý nghĩa nghiệp vụ hoặc mục đích hiển thị**, độc lập với nội dung dịch. Nên dùng tên nhất quán và dễ dò:

```properties
auth.login.title=Sign in
auth.login.submit=Continue
auth.login.error.invalidCredentials=Incorrect email or password.
profile.save.success=Changes saved.
order.checkout.confirm=Place order?
```

Quy tắc thực dụng:

- Phân nhóm theo chức năng (`auth`, `profile`, `order`) và mục đích (`title`, `submit`, `error`, `success`).
- Khóa giữ ổn định khi văn bản tiếng Anh hoặc tiếng Việt thay đổi; **không** dùng cả câu hiển thị làm key.
- Không tự tái sử dụng một khóa cho hai ngữ cảnh khác nhau chỉ vì hiện tại văn bản giống nhau. Một chữ “Open” dùng với file và dùng với cửa có thể cần bản dịch khác.
- Không đưa dữ liệu cá nhân, dữ liệu động hoặc thông tin bí mật vào tên khóa.
- Quy định rõ cách đặt chữ hoa/thường; thông thường dùng chữ ASCII, số và dấu chấm để tránh các lỗi khó nhận ra.
- Khóa là API nội bộ giữa code và file dịch: đổi tên khóa cần cập nhật tất cả nơi gọi và tất cả locale.

Ví dụ **không nên** dùng:

```java
bundle.getString("Please press the blue button to continue");
```

Văn bản hiển thị là thứ có thể chỉnh sửa; nếu biến nó thành key, chỉnh sửa một câu sẽ kéo theo chỉnh sửa mã Java và các file dịch.

Để tránh key rải rác, dự án lớn có thể tập trung các key thành hằng số:

```java
public final class MessageKeys {
    private MessageKeys() {}

    public static final String LOGIN_TITLE = "auth.login.title";
    public static final String INVALID_CREDENTIALS =
            "auth.login.error.invalidCredentials";
}
```

Hằng số giúp người viết code dễ tìm và refactor; nhưng Java compiler **không tự xác minh** key có trong mọi file. Cần kiểm thử hoặc công cụ kiểm tra tài nguyên riêng. Không nhất thiết phải tạo hằng số cho từng key nếu dự án đã dùng giải pháp kiểm tra key tự động.

## 5. Tham số hóa chuỗi thay cho phép nối văn bản

Bản dịch thường cần chèn tên, số lượng hoặc thời gian. Không nên nối các fragment tiếng Anh và áp vào mọi ngôn ngữ:

```java
String message = "Hello, " + name + "!";
```

Với `MessageFormat`, file tài nguyên giữ trọn câu:

```properties
greeting=Hello, {0}!
files.count=You have {0,number,integer} files.
```

Một locale khác có thể đảo trật tự của các placeholder mà không sửa code. `MessageFormat` hỗ trợ số, ngày và các mẫu định dạng, nhưng phải xây bằng **locale mong muốn**:

```java
String pattern = bundle.getString("files.count");
MessageFormat format = new MessageFormat(pattern, locale);
String message = format.format(new Object[] {3});
```

Trong ví dụ này, `{0}` lấy phần tử chỉ số 0 trong mảng đối số. Còn `{0,number,integer}` yêu cầu định dạng như số nguyên theo locale của `MessageFormat`. Không thay thế bằng `String.format` nếu file dịch đang dùng cú pháp `MessageFormat`: hai API sử dụng cú pháp placeholder khác nhau.

**Hai quy tắc quan trọng của MessageFormat:**

1. Dấu nháy đơn `'` có ý nghĩa escape trong pattern. Muốn hiển thị một dấu nháy đơn, dùng `''` trong pattern, ví dụ `You''re welcome, {0}!`. Nếu translator chèn nháy đơn như văn xuôi thông thường, pattern có thể cho kết quả bất ngờ.
2. Dấu ngoặc nhọn có cú pháp đặc biệt. Nếu cần hiển thị dấu `{` hoặc `}` theo nghĩa chữ, phải escape theo cú pháp của `MessageFormat`. Nên viết test cho những thông điệp chứa dấu nháy và ngoặc.

Với văn bản có nhiều dạng số ít/số nhiều, giới tính hoặc cấu trúc ngữ pháp phức tạp, chỉ một câu với `{0}` chưa đủ. Cần thiết kế mẫu dịch có ngữ cảnh hoặc dùng cơ chế i18n hỗ trợ pluralization phù hợp, chẳng hạn các lựa chọn có sẵn trong hệ thống/framework. Không tự ghép từ đơn thành câu dựa trên quy tắc tiếng Anh.

## 6. Hiểu fallback và bundle cha

Khi gọi:

```java
ResourceBundle.getBundle("messages", Locale.forLanguageTag("vi-VN"))
```

Java có quy tắc tìm candidate bundle theo độ cụ thể của locale. Với ví dụ đơn giản, nó có thể xét dạng `messages_vi_VN`, `messages_vi`, rồi bundle gốc `messages`, tùy cơ chế `ResourceBundle.Control` và môi trường. ResourceBundle cũng có **cơ chế fallback sang locale mặc định của JVM** khi không tìm thấy bundle phù hợp theo locale được yêu cầu. Vì vậy không nên hiểu rằng lúc nào không có `messages_ja` thì Java tự động lấy `messages.properties` ngay lập tức; tài nguyên của default locale có thể được ưu tiên trong một số đường tìm kiếm.

Cần phân biệt:

- **Fallback theo locale:** khi không có bundle dành cho locale được yêu cầu, Java tìm ứng viên khác theo quy tắc `ResourceBundle`.
- **Fallback theo key:** khi bundle được chọn thiếu một key, Java có thể tra cứu từ bundle cha.
- **Fallback nghiệp vụ:** sản phẩm quyết định ngôn ngữ mặc định mong muốn (ví dụ `en-US`), độc lập với cấu hình ngẫu nhiên của máy chủ.

Muốn chọn ngôn ngữ đúng theo danh sách thực có của sản phẩm, hãy xác định các locale hỗ trợ trước khi `getBundle`, rồi truyền locale đã chọn. Không coi `Locale.getDefault()` là chính sách sản phẩm. Với ứng dụng nhiều request, không gọi `Locale.setDefault(...)` để chọn ngôn ngữ cho từng người dùng: nó làm thay đổi trạng thái chung của JVM, có thể ảnh hưởng request khác.

Một `messages.properties` đầy đủ key đóng vai trò fallback quan trọng, nhưng **không thay thế việc kiểm chứng chất lượng mỗi bản dịch**. Một UI pha tiếng Việt và tiếng Anh do key thiếu có thể chạy được về mặt kỹ thuật nhưng kém chất lượng trải nghiệm.

## 7. Thiếu bundle và thiếu key là hai lỗi khác nhau

Nếu base name không tồn tại hoặc không tìm thấy bundle nào phù hợp, `ResourceBundle.getBundle` ném `MissingResourceException`. Nếu đã có bundle nhưng `getString(key)` không tìm thấy key trong chuỗi bundle/parent, nó cũng ném `MissingResourceException`.

Ví dụ kiểm tra key bằng chính bundle đã nạp:

```java
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;

public class MissingKeyDemo {
    public static void main(String[] args) {
        ResourceBundle bundle = ResourceBundle.getBundle(
                "messages", Locale.forLanguageTag("vi-VN"));

        String key = "not.existing";
        try {
            System.out.println(bundle.getString(key));
        } catch (MissingResourceException error) {
            System.out.println("Missing key: " + error.getKey());
        }
        System.out.println(bundle.containsKey("app.title"));
    }
}
```

Chạy trong cùng thư mục tài nguyên của ví dụ ở phần 3:

```bash
javac -encoding UTF-8 MissingKeyDemo.java
java -cp . MissingKeyDemo
```

Stdout:

```text
Missing key: not.existing
true
```

`containsKey` có thể giúp kiểm tra một key trước khi gọi `getString`, nhưng **không nên im lặng trả chuỗi rỗng** cho mọi key thiếu: điều đó che giấu lỗi bản dịch trong quá trình phát triển. Tùy sản phẩm, có thể hiển thị fallback có kiểm soát trong production, đồng thời log một mã cảnh báo rõ ràng và có test phát hiện key thiếu trước release.

Phân biệt lỗi key không tồn tại và bản dịch cố tình là chuỗi rỗng. Chuỗi rỗng có thể hợp lệ với một số resource, còn key thiếu là vấn đề về hợp đồng tài nguyên.

## 8. Encoding, ký tự tiếng Việt và định dạng .properties

Các file `.properties` trong ví dụ được lưu bằng **UTF-8**. Trong Java 9+, `PropertyResourceBundle` khi nạp từ stream theo cơ chế chuẩn mặc định đọc UTF-8 và có cơ chế fallback ISO-8859-1 khi gặp dữ liệu UTF-8 không hợp lệ; có thể điều khiển thông qua thuộc tính `java.util.PropertyResourceBundle.encoding`. Với Java 17+, tiếng Việt trong file UTF-8 dùng trực tiếp được khi build và chạy thông thường.

Điều cần chú ý là các API hoặc tool xử lý `.properties` có thể khác nhau:

- `ResourceBundle` dùng `PropertyResourceBundle` cho file tài nguyên.
- `java.util.Properties.load(InputStream)` theo hợp đồng đọc ISO-8859-1, không giống cách xử lý Unicode mặc định của `PropertyResourceBundle` trên Java 17.
- Một số pipeline dịch cũ dùng escape Unicode như `\\u00E9` thay vì ký tự trực tiếp. Nếu có nhiều công cụ cùng ghi file, hãy chuẩn hóa encoding trong toàn pipeline.

Trong `.properties`, dòng bắt đầu bằng `#` hoặc `!` là comment; `=` và `:` có thể phân cách key/value. Các ký tự đặc biệt như dấu gạch chéo ngược, dấu xuống dòng hoặc ký tự phân tách trong key có quy tắc escape. Với thông điệp nhiều dòng, cần dùng cú pháp continuation hoặc escape phù hợp và test output thực tế.

**Đừng dùng mã byte hay cách xử lý charset thủ công trong logic lấy key**, vì chức năng nạp tài nguyên đã có sẵn trong `ResourceBundle`. Chỉ cần bảo đảm file nằm đúng classpath và mã hóa đúng.

## 9. Nơi đặt tài nguyên và lifecycle

Ví dụ giữ `.properties` cạnh `.class` để dễ học. Trong dự án thực tế nên đặt tài nguyên trong thư mục được build tool đưa vào runtime classpath, ví dụ:

```text
src/main/java/com/example/app/GreetingService.java
src/main/resources/messages.properties
src/main/resources/messages_vi.properties
src/main/resources/messages_en.properties
```

Khi đó Java code nằm trong package vẫn có thể gọi `ResourceBundle.getBundle("messages", locale)`, vì `messages.properties` nằm ở root classpath. Nếu đặt bundle trong `src/main/resources/i18n/`, base name phải tương ứng `i18n.messages`.

`ResourceBundle` có cơ chế cache để tránh nạp tài nguyên lặp lại. Điều này phù hợp các ứng dụng chạy lâu, nhưng **thay đổi file ngoài đĩa không có nghĩa resource sẽ tự cập nhật ngay** trong mọi ứng dụng. Tài nguyên đi kèm JAR thường được quản lý qua vòng đời build/deploy. Trong trường hợp cần nạp lại động, hãy thiết kế rõ chính sách cache/reload, class loader và môi trường deploy; API có `ResourceBundle.clearCache()` nhưng xóa cache có thể ảnh hưởng nhiều caller.

Một ứng dụng hoặc framework (như Spring) có thể có abstraction khác để truy cập resource messages, với vòng đời và cấu hình cache riêng. Tuy vậy, nguyên tắc tách **khóa ổn định** khỏi **văn bản địa phương hóa** vẫn giữ nguyên.

## 10. Quy trình làm việc với người dịch và kiểm soát chất lượng

Khi dự án có nhiều ngôn ngữ, lập trình viên và người dịch cần cùng tuân thủ hợp đồng:

1. **Chốt ý nghĩa khóa và ngữ cảnh.** Một câu ngắn như “Save” có thể nghĩa là lưu dữ liệu hoặc tiết kiệm tiền. Cần mô tả vị trí dùng và ý định cho người dịch.
2. **Thêm khóa trong bundle gốc**, rồi bổ sung vào các bản dịch được hỗ trợ. Mỗi key phải có ý nghĩa nhất quán giữa các locale.
3. **Giữ placeholder ổn định.** Nếu gốc dùng `{0}`, translator có thể đổi vị trí placeholder nhưng không được tự ý xóa hoặc đổi thành `%s`.
4. **Cho phép dịch nguyên câu.** Không ép người dịch ghép nhiều mẩu `prefix`, `noun`, `suffix`; ngữ pháp của các ngôn ngữ khác nhau.
5. **Kiểm tra key dư và key thiếu** trong CI hoặc một bài test phù hợp. Nên có cơ chế phát hiện key đã xóa khỏi mã nhưng còn trong file dịch.
6. **Xem trực tiếp trên giao diện**: độ dài chuỗi, xuống dòng, dấu câu, số nhiều, tên riêng, định dạng số/ngày và bố cục UI.
7. **Lưu ý bảo mật:** nội dung dịch là dữ liệu hiển thị, không phải chuỗi HTML hoặc lệnh SQL tin cậy. Khi đưa lên web, vẫn cần HTML escaping/contextual encoding theo nơi chèn; `MessageFormat` không phải bộ chống XSS.

Có thể giữ comment ngay trong file gốc để giải thích:

```properties
# Appears on the final confirmation button before a purchase.
checkout.confirm=Place order

# {0}: customer display name. Keep the placeholder.
greeting=Hello, {0}!
```

Không nhất thiết mọi bản dịch phải giữ comment giống hệt, nhưng nên có nguồn dữ liệu ngữ cảnh để translator tránh hiểu sai.

## 11. Các lỗi phổ biến và cách tránh

| Lỗi | Hệ quả | Cách tránh |
| --- | --- | --- |
| Viết trực tiếp câu chữ trong Java | Mỗi lần dịch phải sửa mã | Đưa giá trị ra `.properties`, tra cứu bằng key |
| Đặt key bằng nguyên câu tiếng Anh | Thay câu chữ kéo theo đổi code | Đặt key theo chức năng và ngữ cảnh |
| Dùng chung key cho hai ngữ nghĩa | Bản dịch một nơi ảnh hưởng nơi khác | Tách key theo mục đích |
| Quên file bundle trên classpath | `MissingResourceException` | Kiểm tra cấu trúc và output build |
| Thiếu key trong một ngôn ngữ | Có thể fallback sai mong muốn hoặc thiếu key | Test đối chiếu tập key |
| Nối từng mảnh câu bằng `+` | Ngữ pháp sai khi dịch | Dùng thông điệp đầy đủ cùng placeholder |
| Dùng `MessageFormat` mà không kiểm tra dấu nháy | Pattern hiển thị sai | Escape và test pattern |
| Dùng locale mặc định cho mọi người dùng | Request bị phụ thuộc môi trường server | Truyền `Locale` cụ thể theo request |
| Sửa file tài nguyên rồi trông chờ reload ngay | Cache giữ nội dung cũ | Có quy trình deploy/reload rõ ràng |
| Nhầm `Properties.load(InputStream)` với ResourceBundle | Đọc Unicode có thể sai | Dùng đúng API và encoding |

Đừng dùng `getString` như một phép kiểm tra ngôn ngữ đã được hỗ trợ: một key có thể tìm thấy nhờ parent/fallback dù bản dịch mong muốn không tồn tại. Nếu sản phẩm chỉ hỗ trợ danh sách locale nhất định, hãy công bố và xác thực danh sách đó trước khi nạp bundle.

## 12. Kiểm thử đơn vị và kiểm thử tích hợp nên xác minh gì?

- **Tồn tại bundle**: base name tìm được trên classpath sau build, cả khi chạy local lẫn khi đóng gói JAR.
- **Bộ key**: bundle gốc có đủ mọi key mã Java dùng; các bản dịch có coverage như chính sách sản phẩm yêu cầu.
- **Fallback theo locale**: yêu cầu `vi-VN` nhưng chỉ có `messages_vi`, yêu cầu ngôn ngữ không hỗ trợ và kiểm tra đúng fallback nghiệp vụ.
- **Fallback theo key**: bản dịch thiếu một key, xác định rõ lấy từ parent hay phát hiện lỗi.
- **Placeholder**: mỗi locale có đủ số/thứ tự tham số; pattern `MessageFormat` hợp lệ, nhất là các câu có nháy đơn, dấu ngoặc, số và ngày.
- **Unicode**: chữ có dấu tiếng Việt được lưu, đọc và hiển thị chính xác trên runtime Java mục tiêu.
- **Không phụ thuộc locale mặc định**: truyền locale cụ thể vào các API; không thay `Locale.setDefault` toàn JVM trong logic request.
- **Đổi câu chữ không cần sửa code**: thay một value trong file dịch, build/deploy lại và xác minh cùng key hiện thông điệp mới.
- **An toàn đầu ra**: nếu có giá trị do người dùng cung cấp nằm trong placeholder, tầng hiển thị phải encode theo đúng context.

**Lưu ý về test:** một chương trình demo in ra tiếng Việt và tiếng Anh chưa chứng minh toàn bộ key hợp lệ. Với module thực tế, cần thêm kiểm tra tự động để nhận ra key thiếu hoặc placeholder sai trước khi release.

## 13. Bài tập áp dụng

Giữ nguyên chương trình ở phần 3 và thử:

1. Thêm `messages_fr.properties` với bản tiếng Pháp cho ba key `app.title`, `greeting`, `logout.confirm`; gọi `show(Locale.forLanguageTag("fr-FR"))`. Xác minh code không cần điều kiện mới cho tiếng Pháp.
2. Đổi câu `logout.confirm` trong file tiếng Việt nhưng giữ nguyên key; xác minh không cần sửa Java.
3. Xóa tạm `greeting` khỏi `messages_vi.properties`; quan sát cách `ResourceBundle` tra cứu giá trị từ bundle cha. Sau đó phục hồi key và giải thích lý do UI trộn hai ngôn ngữ có thể không mong muốn.
4. Thêm key `files.count` với pattern `You have {0,number,integer} files.` và bản dịch tiếng Việt đầy đủ. Dùng `new MessageFormat(pattern, locale)` để thay giá trị `3`; tránh nối fragment.
5. Gọi `getString("missing.key")`, ghi nhận `MissingResourceException` và cân nhắc cách báo lỗi phù hợp thay vì ẩn lỗi bằng chuỗi rỗng.

Những bài tập này củng cố một quy tắc cốt lõi: **mã Java xác định thông điệp cần dùng bằng key; file tài nguyên quyết định cách biểu đạt thông điệp cho locale đã chọn**. Khi hai vai trò này được tách bạch, ứng dụng dễ dịch, dễ kiểm thử và dễ bảo trì hơn.

## 14. Tài liệu API để đọc thêm

- [Oracle JDK 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Oracle JDK 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [Oracle JDK 21 — MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html)
- [Oracle JDK 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
