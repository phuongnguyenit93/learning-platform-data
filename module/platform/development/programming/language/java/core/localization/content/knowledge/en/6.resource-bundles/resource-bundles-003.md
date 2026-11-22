# Tạo ResourceBundle gốc và các bản dịch theo Locale trong Java

Một ứng dụng đa ngôn ngữ không nên đặt câu chữ giao diện trực tiếp trong nhiều nhánh `if (language.equals(...))`. Cách làm có thể mở rộng là **tách nội dung thành bộ thông điệp (bundle)** theo ngôn ngữ và vùng, rồi chọn bộ phù hợp với `Locale` của người dùng. Java cung cấp `java.util.ResourceBundle` cho nhu cầu đó.

Bài học này hướng dẫn **tạo bundle gốc**, tạo những file bản dịch cùng tên cơ sở cho từng locale, đọc thông điệp qua Java 17+, hiểu quan hệ giữa bundle vùng–ngôn ngữ–gốc, xử lý key còn thiếu và đóng gói tài nguyên đúng cách. Trọng tâm là **tổ chức và tạo file tài nguyên**, kèm chương trình có thể chạy để kiểm chứng.

## 1. Bundle gốc và bundle theo locale là gì?

`ResourceBundle` là một API tra cứu dữ liệu bản địa hóa bằng **khóa (key)**. Với bundle dựa trên file `.properties`, mỗi file chứa các cặp `key=value`:

```properties
app.title=Locale Workshop
button.start=Start
button.quit=Quit
```

- **Base name** là tên logic chung của bộ tài nguyên, ví dụ `messages`. Khi gọi API, truyền `"messages"`, không truyền đuôi `.properties`.
- **Bundle gốc (root/base bundle)** là `messages.properties`, không có hậu tố locale. Nó cung cấp các giá trị mặc định làm điểm dự phòng.
- **Bundle ngôn ngữ** là file như `messages_en.properties` hoặc `messages_vi.properties`.
- **Bundle vùng** là file như `messages_en_US.properties`, `messages_en_GB.properties`, `messages_vi_VN.properties`. Nó ghi đè các khóa cần khác nhau theo vùng, không nhất thiết chép lại toàn bộ bundle cha.
- **Locale được yêu cầu** là tham số `Locale` khi gọi `ResourceBundle.getBundle(baseName, locale)`. Nó quyết định các tên file ứng viên mà Java xem xét.

Ví dụ `en-US` và `en-GB` đều dùng tiếng Anh nhưng có thể chọn nhãn nút khác nhau. Nếu key của file vùng không tồn tại, Java có thể lấy từ bundle tiếng Anh chung và sau đó từ bundle gốc theo chuỗi bundle cha. Nói cách khác, bản dịch theo locale **có thể chỉ chứa phần khác biệt**.

**Phân biệt hai cú pháp:** thẻ ngôn ngữ BCP 47 viết `en-US` (dấu gạch nối); **tên file ResourceBundle Java** dùng `messages_en_US.properties` (dấu gạch dưới). Đây là hai quy ước khác nhau. Trong Java, hãy tạo locale bằng `Locale.forLanguageTag("en-US")`.

## 2. Thiết kế bộ tài nguyên mẫu

Ta xây dựng một ứng dụng nhỏ hỗ trợ tiếng Anh chung, tiếng Anh Hoa Kỳ, tiếng Anh Vương quốc Anh, tiếng Việt chung và tiếng Việt tại Việt Nam. Các file có cùng base name `messages`:

```text
localization-demo/
├── BundleDemo.java
├── messages.properties
├── messages_en.properties
├── messages_en_US.properties
├── messages_en_GB.properties
├── messages_vi.properties
└── messages_vi_VN.properties
```

Đặt tất cả các file trên vào **cùng một thư mục** cho ví dụ chạy trực tiếp. Khi chạy từ thư mục đó với classpath là `.`, JVM sẽ thấy cả mã lớp và tài nguyên `.properties`.

Quy ước đặt tên:

| File | Vai trò |
| --- | --- |
| `messages.properties` | Bundle gốc; dự phòng các key chưa được dịch hoặc khi không có bộ locale phù hợp |
| `messages_en.properties` | Bản tiếng Anh chung |
| `messages_en_US.properties` | Phần cần khác riêng cho `en-US` |
| `messages_en_GB.properties` | Phần cần khác riêng cho `en-GB` |
| `messages_vi.properties` | Bản tiếng Việt chung |
| `messages_vi_VN.properties` | Phần cần khác riêng cho `vi-VN` |

File gốc **không bắt buộc** tồn tại để mọi cách tra cứu đều hoạt động, nhưng việc tạo nó là một lựa chọn hữu ích: bạn chủ động xác định điểm dự phòng cuối cùng. Nếu không tìm thấy **bất kỳ bundle ứng viên nào**, `getBundle` sẽ ném `MissingResourceException` thay vì tự tạo thông điệp.

### Bước 1 — Tạo bundle gốc `messages.properties`

```properties
# messages.properties
app.title=Locale Workshop
button.start=Start
button.quit=Quit
status.ready=Ready
```

Ý nghĩa bốn key:

- `app.title`: tiêu đề ứng dụng.
- `button.start` và `button.quit`: nhãn hai thao tác.
- `status.ready`: thông báo trạng thái.

Bundle gốc nên có **đủ các key mà ứng dụng dùng** để có điểm dự phòng xác định. Tên key thường được đặt theo chức năng giao diện thay vì dùng trực tiếp câu tiếng Anh làm key: khi câu dịch đổi, code có thể giữ nguyên key.

### Bước 2 — Tạo bundle tiếng Anh chung `messages_en.properties`

```properties
# messages_en.properties
button.start=Start
```

Ở đây bản tiếng Anh chung chỉ ghi đè `button.start`. Các key `app.title`, `button.quit` và `status.ready` chưa được khai báo sẽ được tìm từ bundle cha `messages.properties`.

Bạn **cũng có thể** đặt đầy đủ mọi key ở file ngôn ngữ, nếu đó là chính sách kiểm soát bản dịch của nhóm. Ví dụ này cố ý dùng bundle gọn để cho thấy cách tra cứu kế thừa.

### Bước 3 — Tạo bản tiếng Anh theo vùng

File `messages_en_US.properties`:

```properties
# messages_en_US.properties
button.start=Get started
```

File `messages_en_GB.properties`:

```properties
# messages_en_GB.properties
button.start=Begin
```

Hai file này đều có một key nhưng giá trị khác nhau. Các key còn lại đến từ `messages_en.properties` nếu có, rồi `messages.properties`. Điều này tránh chép lặp hàng chục chuỗi giống nhau cho các vùng cùng ngôn ngữ.

Nếu hai vùng thực sự dùng cùng một cách diễn đạt, không nhất thiết phải tạo file vùng riêng. Chỉ tạo khi có bản dịch, chính tả, từ vựng hoặc nội dung riêng cần duy trì.

### Bước 4 — Tạo bản tiếng Việt và biến thể `vi-VN`

File `messages_vi.properties`:

```properties
# messages_vi.properties
app.title=Học Locale
button.start=Bắt đầu
status.ready=Sẵn sàng
```

File `messages_vi_VN.properties`:

```properties
# messages_vi_VN.properties
button.start=Khởi động
```

Ở đây tiếng Việt chung đã dịch ba key nhưng chưa có `button.quit`. Giá trị `button.quit=Quit` từ bundle gốc vẫn có hiệu lực. Đây là cách fallback hợp lệ về mặt cơ chế, nhưng có thể không phù hợp để phát hành vì giao diện bị **trộn ngôn ngữ**. Trong sản phẩm thực, kiểm tra độ đầy đủ của bản dịch và có quy tắc quyết định key nào được phép fallback.

**Mã hóa:** từ Java 9 trở đi, `PropertyResourceBundle` đọc tài nguyên `.properties` dưới dạng **UTF-8** theo mặc định, với cơ chế xử lý tương thích khi gặp dữ liệu không hợp lệ. Vì vậy, Java 17+ có thể chứa trực tiếp `Học`, `Bắt đầu`, `Sẵn sàng` trong file UTF-8. Cần lưu file thật ở UTF-8; editor, quy trình đóng gói và console phải hiển thị Unicode đúng. Không chuyển những chuỗi này thành ASCII không dấu chỉ để tránh giải quyết lỗi mã hóa.

## 3. Chương trình Java 17+ đọc các bundle vừa tạo

Lưu file sau với tên **`BundleDemo.java`** vào cùng thư mục với sáu file `.properties`:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleDemo {
    public static void main(String[] args) {
        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        String[] tags = {
                "en-US", "en-GB", "en-AU", "vi-VN", "fr-FR"
        };

        for (String tag : tags) {
            Locale locale = Locale.forLanguageTag(tag);
            ResourceBundle bundle =
                    ResourceBundle.getBundle("messages", locale, control);

            System.out.println(
                    tag
                    + " | title=" + bundle.getString("app.title")
                    + " | start=" + bundle.getString("button.start")
                    + " | quit=" + bundle.getString("button.quit")
                    + " | ready=" + bundle.getString("status.ready"));
        }
    }
}
```

Từ thư mục chứa các file, chạy:

```bash
javac -encoding UTF-8 BundleDemo.java
java -cp . BundleDemo
```

**Stdout của chương trình, khi sáu file được tạo đúng như hướng dẫn và được đọc dưới dạng UTF-8:**

```text
en-US | title=Locale Workshop | start=Get started | quit=Quit | ready=Ready
en-GB | title=Locale Workshop | start=Begin | quit=Quit | ready=Ready
en-AU | title=Locale Workshop | start=Start | quit=Quit | ready=Ready
vi-VN | title=Học Locale | start=Khởi động | quit=Quit | ready=Sẵn sàng
fr-FR | title=Locale Workshop | start=Start | quit=Quit | ready=Ready
```

**Giải thích từng hàng:**

1. `en-US` có `messages_en_US`: `button.start` lấy từ US, các key còn lại đi qua cha `en` đến gốc.
2. `en-GB` tương tự nhưng chọn `Begin` từ bundle GB.
3. `en-AU` **không có** file vùng tương ứng: Java dùng `messages_en.properties` cho `button.start`, sau đó dùng gốc cho những key còn lại.
4. `vi-VN` có `messages_vi_VN.properties`; `button.start` là `Khởi động`, `app.title` và `status.ready` từ `messages_vi.properties`, `button.quit` từ gốc.
5. `fr-FR` không có bundle tiếng Pháp: với cách gọi đã vô hiệu hóa fallback sang locale mặc định của JVM, Java dùng `messages.properties`.

Kết quả cho thấy **một lần gọi `getBundle` chọn bundle thích hợp**, còn mỗi lần gọi `getString(key)` có thể lấy giá trị từ bundle đang chọn hoặc các bundle cha.

### Vì sao dùng `getNoFallbackControl` trong ví dụ?

`ResourceBundle.Control.getNoFallbackControl(ResourceBundle.Control.FORMAT_PROPERTIES)` có hai ý nghĩa:

- Chỉ xét các bundle dạng file `.properties` theo cấu hình format này, không dùng lựa chọn class-based trong danh sách format ứng viên.
- Không thêm một lượt **fallback sang default locale JVM** khi không tìm được bundle cho locale yêu cầu. Bundle gốc vẫn là một ứng viên bình thường và vẫn là nguồn dự phòng.

Ví dụ sẽ dễ kiểm thử vì không thay đổi theo `Locale.getDefault()` của máy đang chạy. Với overload phổ biến `ResourceBundle.getBundle("messages", locale)`, Java có thể tìm bundle theo **default locale** nếu không tìm được tài nguyên ứng viên phù hợp. Lúc đó một yêu cầu `fr-FR` có thể chọn ngôn ngữ mặc định của server nếu môi trường và danh sách tài nguyên dẫn đến kết quả đó. Điều này làm đường fallback khó đoán nếu không kiểm thử rõ.

`Control` trong ví dụ áp dụng cho cách dùng bundle **classpath truyền thống**. Trong môi trường JPMS với named modules, các overload `getBundle` dùng `ResourceBundle.Control` có giới hạn/không được hỗ trợ theo cách này; hãy sử dụng cơ chế lookup của module/provider phù hợp. Ví dụ đang đặt mã và properties trên classpath, không tạo named module.

## 4. Java tìm bundle và key theo thứ tự nào?

Hãy phân biệt hai câu hỏi:

**Câu hỏi A — chọn bundle:** Java xét các bundle ứng viên tương ứng với locale được yêu cầu, chẳng hạn khi yêu cầu `en-US` thì thứ tự đơn giản hóa là:

```text
messages_en_US.properties
           ↓
messages_en.properties
           ↓
messages.properties
```

Đối với `en-AU` chưa có file vùng:

```text
messages_en_AU.properties  (không có)
           ↓
messages_en.properties     (có)
           ↓
messages.properties        (có)
```

**Câu hỏi B — tìm một key:** bundle locale cụ thể có thể **chỉ định nghĩa một số key**. Khi `bundle.getString("button.quit")` không tìm thấy trong bundle vùng, nó tiếp tục tìm ở bundle cha và cuối cùng ở gốc. Java không nhất thiết “ghép vật lý” tất cả file thành một file mới; kết quả được tra qua chuỗi kế thừa.

| Locale yêu cầu | Bundle cụ thể nhất trong ví dụ | `button.start` | `button.quit` |
| --- | --- | --- | --- |
| `en-US` | `messages_en_US` | `Get started` | Gốc: `Quit` |
| `en-GB` | `messages_en_GB` | `Begin` | Gốc: `Quit` |
| `en-AU` | `messages_en` | `Start` | Gốc: `Quit` |
| `vi-VN` | `messages_vi_VN` | `Khởi động` | Gốc: `Quit` |
| `fr-FR` | `messages` | `Start` | Gốc: `Quit` |

Thứ tự trên minh họa trường hợp ngôn ngữ + vùng thông thường. Locale còn có thể có **script, variant và extensions**, vì vậy danh sách ứng viên thực tế do `ResourceBundle.Control.getCandidateLocales(...)` quy định, không nên tự ghép/cắt chuỗi tag BCP 47 bằng tay để giả lập toàn bộ thuật toán.

Thêm file `messages_en_AU.properties` với `button.start=Launch` sẽ cho phép `en-AU` lấy nhãn mới ở vùng đó mà không sửa code Java. Các key chưa khai báo vẫn theo chuỗi bundle cha.

### Kiểm tra bundle cụ thể đã được chọn

Có thể dùng `getLocale()` trên đối tượng `ResourceBundle` để quan sát locale của bundle cụ thể nhất được tìm thấy. Nó có thể **khác locale đã yêu cầu** khi fallback:

```java
Locale request = Locale.forLanguageTag("en-AU");
ResourceBundle bundle = ResourceBundle.getBundle(
        "messages",
        request,
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES));

System.out.println("Requested: " + request.toLanguageTag());
System.out.println("Loaded: " + bundle.getLocale().toLanguageTag());
```

Đây là đoạn mã **đặt bên trong phương thức Java với import `Locale`/`ResourceBundle`**, không phải một chương trình độc lập. Với bộ file của bài, stdout:

```text
Requested: en-AU
Loaded: en
```

Nếu bundle gốc được chọn, `bundle.getLocale()` thường là `Locale.ROOT`; `Locale.ROOT.toLanguageTag()` là `und` (undetermined). `getLocale()` cho biết bundle được chọn, **không trả nguồn của từng key riêng lẻ**: key có thể đến từ bundle cha.

## 5. Đặt tên file đúng và đặt trên classpath

Các tên đúng cho base name `messages`:

| Locale Java | Thẻ BCP 47 | Tên file dự kiến |
| --- | --- | --- |
| `Locale.ROOT` | `und` khi gọi `toLanguageTag()` | `messages.properties` |
| `Locale.forLanguageTag("en")` | `en` | `messages_en.properties` |
| `Locale.forLanguageTag("en-US")` | `en-US` | `messages_en_US.properties` |
| `Locale.forLanguageTag("pt-BR")` | `pt-BR` | `messages_pt_BR.properties` |
| `Locale.forLanguageTag("zh-Hant-TW")` | `zh-Hant-TW` | `messages_zh_Hant_TW.properties` |

**Không đặt tên file là `messages_en-US.properties`** rồi kỳ vọng cơ chế `ResourceBundle` theo quy ước chuẩn tự tìm thấy. API sử dụng các thành phần `Locale` để xây dựng tên resource với dấu `_`.

Nếu đưa vào dự án Gradle/Java thông thường, cấu trúc có thể là:

```text
src/
├── main/
│   ├── java/
│   │   └── com/example/i18n/
│   │       └── Main.java
│   └── resources/
│       └── com/example/i18n/
│           ├── messages.properties
│           ├── messages_en.properties
│           ├── messages_en_US.properties
│           ├── messages_en_GB.properties
│           ├── messages_vi.properties
│           └── messages_vi_VN.properties
```

Với cách đặt resources **bên trong package `com/example/i18n`**, base name phải là `"com.example.i18n.messages"`:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "com.example.i18n.messages",
        Locale.forLanguageTag("vi-VN"));
```

Đây là ví dụ gọi API trong một phương thức đã import các lớp. Nếu các file `.properties` được để **ngay tại gốc resources**, base name tương ứng là `"messages"`. Đặt sai base name hoặc resources không nằm trên runtime classpath thường dẫn đến `MissingResourceException` dù file có mặt trong thư mục dự án.

Cần kiểm tra cả **việc đóng gói**: file tài nguyên phải được copy vào classpath output/đóng gói trong JAR ở đường dẫn phù hợp. `javac` chỉ biên dịch `.java`; nó không tự chuyển `.properties` từ thư mục khác vào output. Gradle/Maven có bước xử lý resources; khi chạy Java thủ công, hãy để files đúng thư mục trong `-cp` hoặc sao chép rõ ràng.

## 6. Chọn giữa ghi đè từng key và bản dịch đầy đủ

Có hai chiến lược thiết kế thông dụng:

**Kế thừa gọn:** bundle vùng chỉ ghi đè key khác, bundle ngôn ngữ dịch các key còn lại, bundle gốc làm fallback. Ưu điểm là ít lặp; nhược điểm là bản dịch thiếu có thể bị che bởi fallback và giao diện trộn ngôn ngữ.

**Bản dịch đầy đủ theo locale hỗ trợ:** mỗi locale được công bố chính thức phải có mọi key cần thiết. Ưu điểm là dễ kiểm soát chất lượng/làm việc với biên dịch viên; nhược điểm là cần cơ chế đồng bộ key, công sức duy trì và có thể trùng nhiều giá trị. Ngay cả khi file đầy đủ, ResourceBundle vẫn giữ cơ chế kế thừa.

Cách áp dụng thường hợp lý:

1. Định nghĩa **khóa chuẩn** trong `messages.properties` như một hợp đồng nội dung, với tên có nghĩa rõ ràng.
2. Xác định các locale app **thực sự hỗ trợ** và mức độ bản dịch cần đạt để phát hành. `Locale.getAvailableLocales()` không phải danh sách bản dịch của ứng dụng.
3. Tạo bundle ngôn ngữ và chỉ thêm bundle vùng/script khi có khác biệt có chủ đích.
4. Tạo kiểm thử/kiểm tra build đối chiếu key của bundle dịch với bundle gốc, phân biệt key thiếu được phép fallback và key bắt buộc phải dịch.
5. Kiểm tra nhãn trong UI thực tế: chiều dài chữ, ký tự Unicode, chỗ xuống dòng, từ ngữ tự nhiên, placeholder/biến số.

**Không dịch các key**; dịch giá trị. Tránh đặt tên key là số thứ tự hay câu UI có khả năng thay đổi để các refactor câu chữ không gây thay đổi khắp code.

## 7. Key bị thiếu: kết quả thực tế và cách phát hiện

Có hai tình huống khác nhau:

- **Thiếu key ở bundle vùng nhưng có ở cha/gốc:** `getString(key)` vẫn trả giá trị ở cha. Đây chính là hành vi muốn minh họa ở ví dụ.
- **Key không có trong bất kỳ bundle nào của chuỗi tra cứu:** `getString(key)` ném `MissingResourceException`. Đừng bắt lỗi chung rồi âm thầm hiển thị chuỗi trống, vì làm mất dấu hiệu bản dịch bị lỗi.

Chương trình nhỏ sau dùng **cùng sáu file đã tạo**. Lưu thành `MissingKeyDemo.java`:

```java
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;

public class MissingKeyDemo {
    public static void main(String[] args) {
        ResourceBundle bundle = ResourceBundle.getBundle(
                "messages",
                Locale.forLanguageTag("vi-VN"),
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES));

        System.out.println("Has quit: "
                + bundle.containsKey("button.quit"));
        System.out.println("Has help: "
                + bundle.containsKey("help.text"));

        try {
            System.out.println(bundle.getString("help.text"));
        } catch (MissingResourceException exception) {
            System.out.println("Missing key: " + exception.getKey());
        }
    }
}
```

```bash
javac -encoding UTF-8 MissingKeyDemo.java
java -cp . MissingKeyDemo
```

Stdout:

```text
Has quit: true
Has help: false
Missing key: help.text
```

`containsKey("button.quit")` là `true` vì Java tìm được key trong **bundle cha** dù `messages_vi_VN.properties` không tự khai báo nó. `containsKey` cho biết key có tồn tại ở **chuỗi bundle**, không xác nhận file dịch cụ thể đã dịch key đó. Vì thế muốn đo **độ đầy đủ** của từng file, phải phân tích danh sách key trong file nguồn trực tiếp bằng công cụ build/QA riêng, không chỉ kiểm tra `ResourceBundle.containsKey` sau fallback.

Một ứng dụng có thể thiết kế fallback “chỉ root, không dùng ngôn ngữ mặc định JVM” hoặc chính sách khác; nhưng chính sách phải tường minh và được kiểm thử trên locale chưa có bản dịch.

## 8. Cấu trúc nội dung và những chi tiết của `.properties`

`.properties` có một số quy tắc cần nhớ:

- Một key thường được viết như `section.action.label=Text`; dấu `=` hoặc `:` có thể ngăn key và value. Để dễ đọc và review, dùng nhất quán `=`.
- Các dòng bắt đầu bằng `#` hoặc `!` (sau khoảng trắng đầu dòng) là comment. Tránh đặt comment giữa nhiều dòng của một value nối bằng backslash.
- Giá trị dài có thể nối nhiều dòng bằng dấu backslash ở cuối dòng theo cú pháp properties. Đừng nghĩ xuống dòng vật lý trong file luôn là ký tự xuống dòng của chuỗi Java.
- Dấu cách đầu giá trị, backslash và các ký tự cú pháp cần được viết/escape đúng theo định dạng Java properties. Thử chạy parser thật để kiểm tra các giá trị nhạy cảm.
- File bản dịch nên dùng UTF-8 với Java 17+ và kiểm thử đầu ra Unicode. Khi dùng `Properties.load(InputStream)` trực tiếp thì mặc định về mã hóa khác `PropertyResourceBundle`; **không đánh đồng hai API**.
- Nếu câu chứa tham số động, ví dụ `Hello, {0}!`, `getString` chỉ lấy nguyên mẫu. Muốn chèn tham số theo locale có thể dùng `java.text.MessageFormat` với locale tường minh; cần kiểm tra cú pháp dấu nháy đơn và placeholder. Không dùng `String.format` một cách tùy tiện nếu các vùng cần đổi thứ tự tham số.
- Tránh để password/token hoặc thông tin bí mật trong bundle giao diện được đóng gói phát hành: các file đó là **tài nguyên ứng dụng có thể bị đọc**.

Đối với nút có nhãn khác theo vùng, giữ `button.start` giống nhau và chỉ thay **value**. Nếu mỗi vùng lại dùng key khác, code sẽ phải biết chi tiết của từng ngôn ngữ và phá vỡ mục tiêu tách nội dung khỏi logic.

## 9. Tạo bundle trong dự án thực tế

Quy trình triển khai được đề xuất:

1. **Lập danh sách message key** từ các vị trí cần bản địa hóa. Ví dụ `login.title`, `login.submit`, `errors.required`, `nav.home`. Đặt tên nhất quán, không gắn tên vùng trong key nếu cùng một vai trò.
2. **Tạo file gốc** `messages.properties` và đưa tất cả key chuẩn vào đây. Chuỗi ở gốc phải được chủ động biên tập như một lựa chọn fallback chính thức.
3. **Tạo file theo ngôn ngữ** như `messages_en.properties`, `messages_vi.properties`, `messages_fr.properties`. Đồng bộ key cần dịch.
4. **Thêm file theo vùng/script khi có yêu cầu thật**, ví dụ `messages_en_GB.properties`, `messages_pt_BR.properties`, `messages_zh_Hant_TW.properties`. Chú ý candidate locale khi có script.
5. **Đặt file ở resources/classpath**, kiểm tra tên base name trong lời gọi `getBundle` và khả năng package trong JAR.
6. **Chọn locale ở ranh giới ứng dụng**: ưu tiên locale người dùng đã chọn; nếu lấy từ HTTP `Accept-Language`, đối chiếu với danh sách locale được ứng dụng hỗ trợ. Dùng một fallback ứng dụng rõ ràng.
7. **Đọc key bằng ResourceBundle** và truyền giá trị vào UI. Khi render nhiều key cùng một request, tái sử dụng bundle thích hợp thay vì lặp nhiều lần thao tác chọn locale.
8. **Kiểm thử độ phủ và bản dịch** qua các locale hỗ trợ, key thiếu, sai mã hóa, cả trường hợp vùng chưa có file riêng.
9. **Review với người bản ngữ** và rà soát nội dung, tràn layout, dấu câu, văn phong. Đúng cú pháp không có nghĩa là bản dịch tốt.

### Khi bản dịch được sửa lúc ứng dụng đang chạy

`ResourceBundle` có cơ chế **cache bundle** để tránh tải file lặp lại không cần thiết. Việc chỉnh file trên đĩa **không bảo đảm** một lời gọi `getBundle` kế tiếp thấy ngay nội dung mới. Với tài nguyên tĩnh đóng gói trong JAR, thông thường cần phát hành lại/restart theo quy trình ứng dụng. Nếu ứng dụng tự triển khai cơ chế reload động, cần thiết kế `ResourceBundle.Control`/TTL, refresh và đồng bộ cache phù hợp với môi trường; không mặc định Java theo dõi file `.properties` tự động. Với bài học cơ bản này, chỉ dùng bản dịch tĩnh trên classpath.

## 10. Lỗi phổ biến khi tạo bộ file dịch

| Lỗi | Hiện tượng / nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đặt `messages_en-US.properties` | Cơ chế tên file chuẩn không khớp hậu tố vùng | Dùng `messages_en_US.properties` |
| Truyền `"messages.properties"` vào `getBundle` | Base name bị hiểu sai | Truyền `"messages"` |
| Đặt resources trong package nhưng gọi `"messages"` | Không tìm đúng đường dẫn | Dùng base name đầy đủ `"com.example.i18n.messages"` |
| Biên dịch Java nhưng bỏ quên file `.properties` trên classpath | Không tải được bundle | Đưa resources vào đường dẫn runtime/JAR |
| Chỉ có file vùng mà không có gốc trong thiết kế kỳ vọng fallback chung | Key hoặc locale khác có thể không có ứng viên hợp lệ | Tạo bundle gốc và kiểm thử fallback |
| Key ở bundle dịch khác key trong gốc | Tra không đúng chuỗi mong muốn | Dùng cùng bộ key chuẩn |
| Chỉ tạo file vùng, bỏ key không khác rồi tưởng `getString` luôn thất bại | Cơ chế cha có thể cung cấp giá trị | Hiểu chuỗi kế thừa; kiểm tra bản dịch theo chính sách |
| Dùng `containsKey` để đánh giá bản dịch vùng đã đầy đủ | Nó có thể thấy key từ bundle cha | So sánh file dịch với key chuẩn riêng |
| Dựa vào locale mặc định của server để chọn ngôn ngữ người dùng | Kết quả có thể phụ thuộc môi trường | Truyền `Locale` tường minh vào `getBundle` |
| File Việt không thực sự lưu UTF-8 | Ký tự bị lỗi khi tải/hiển thị | Kiểm tra encoding editor, nguồn và console |
| Đổi `Locale.setDefault` theo từng request | Default là toàn JVM và gây ảnh hưởng luồng khác | Chọn locale theo user/request, không sửa global |
| Cho rằng `getBundle` tự dịch mọi chuỗi | API chỉ tra giá trị trong bundle | Tạo và quản lý bản dịch thật |
| Cho rằng key thiếu trong bundle vùng là key không tồn tại | `getString` có thể tìm ở cha | Phân biệt key chưa dịch và key vắng toàn bộ |
| Mong thay đổi file `.properties` được đọc lại ngay | Bundle có cache | Thiết kế reload hoặc deploy lại có kiểm soát |

## 11. Bài tập và cách tự kiểm tra

**Bài tập 1 — Bổ sung bản dịch tiếng Pháp.** Tạo `messages_fr.properties` gồm:

```properties
# messages_fr.properties
app.title=Atelier Locale
button.start=Démarrer
status.ready=Prêt
```

Chạy lại `BundleDemo`. Vì bundle `fr` đã tồn tại, yêu cầu `fr-FR` giờ sử dụng bộ tiếng Pháp cho ba key đã dịch và bundle gốc cho `button.quit`. Hãy dự đoán hàng `fr-FR` trước khi chạy.

**Bài tập 2 — Bổ sung `en-AU`.** Tạo `messages_en_AU.properties`:

```properties
# messages_en_AU.properties
button.start=Let's begin
```

Khi chạy lại, `en-AU` chọn giá trị `Let's begin` trong file vùng, các key còn lại tiếp tục fallback. Chú ý: dấu nháy đơn trong file `.properties` thông thường không yêu cầu escape đặc biệt; cú pháp `MessageFormat` có quy tắc khác nếu sau này sử dụng template có tham số.

**Bài tập 3 — Kiểm tra key thiếu.** Gọi `bundle.getString("help.text")` trước khi tạo key này trong các file. Xác định lỗi, sau đó thêm `help.text=Help` vào bundle gốc và kiểm chứng lookup không còn lỗi. Thử thêm một bản dịch `help.text` vào `messages_vi.properties` để thấy kết quả khác theo locale.

**Bài tập 4 — Chọn cấu trúc resources.** Di chuyển bộ `messages*.properties` từ gốc classpath vào `com/example/i18n/` và cập nhật base name Java thành `com.example.i18n.messages`. Kiểm tra classpath và các file được đóng gói trước khi chạy. Mục tiêu là nắm quan hệ giữa **tên logic** và **đường dẫn tài nguyên**, không sửa các khóa nội dung.

**Tự đánh giá:** sau bài này, bạn nên giải thích được vì sao `en-GB` lấy `Begin` nhưng `en-AU` lấy `Start`, vì sao `vi-VN` vẫn nhận `Quit` từ gốc, vì sao `fr-FR` lấy bundle gốc ở ví dụ ban đầu, và vì sao file trong package khác cần base name khác.

## 12. Ghi nhớ

- Bundle gốc **`messages.properties`** là nền tảng dự phòng; các file `messages_<language>.properties`, `messages_<language>_<REGION>.properties` cung cấp bản dịch và ghi đè theo mức cụ thể.
- Dùng **cùng key** giữa mọi locale. Các file vùng chỉ cần ghi đè key có khác biệt nếu chính sách dự án cho phép.
- Gọi `ResourceBundle.getBundle("messages", locale)` để tra resource theo locale; dùng `getString(key)` để lấy giá trị, có thể fallback qua bundle cha.
- Trong ví dụ Java 17+, dùng `getNoFallbackControl(FORMAT_PROPERTIES)` nhằm phân biệt rõ **fallback trong chuỗi bundle** với **fallback sang default locale JVM**.
- Dấu `-` của tag `en-US` và dấu `_` của tên file `messages_en_US.properties` có vai trò khác nhau.
- File phải có mặt **trên runtime classpath** đúng đường dẫn và đúng base name. UTF-8, key đầy đủ và chính sách fallback cần được kiểm thử.
- `ResourceBundle` hỗ trợ **lựa chọn thông điệp đã dịch**, không tự dịch nội dung và không xác nhận chất lượng bản dịch.

Tạo một bundle gốc rõ ràng, thêm bản dịch theo ngôn ngữ trước, và chỉ thêm biến thể vùng khi thật sự cần. Khi thiết kế và kiểm thử đầy đủ, một key như `button.start` có thể phục vụ nhiều locale mà code Java không cần biết những cách diễn đạt cụ thể trong từng vùng.