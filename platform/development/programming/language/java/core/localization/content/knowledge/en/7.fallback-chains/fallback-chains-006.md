# MissingResourceException khi thiếu bundle hoặc thiếu khóa trong Java

## 1. Tình huống thường gặp

Trong ứng dụng hỗ trợ nhiều ngôn ngữ, `ResourceBundle` nạp các thông điệp từ tập tài nguyên như `messages.properties`, `messages_vi.properties` hoặc `messages_en_US.properties`. Từng thông điệp được lấy bằng một khóa ổn định:

```java
ResourceBundle messages =
        ResourceBundle.getBundle("messages", Locale.forLanguageTag("vi-VN"));
String title = messages.getString("app.title");
```

Hai thao tác trong đoạn minh họa trên có **hai kiểu thất bại khác nhau**:

1. **Không tìm thấy bundle phù hợp:** `ResourceBundle.getBundle(...)` không tìm được tài nguyên cho base name sau khi đã áp dụng các quy tắc tìm kiếm và fallback. Phương thức ném `MissingResourceException`.
2. **Có bundle nhưng không tìm được key:** `getBundle(...)` thành công, nhưng `messages.getString("app.title")` không tìm thấy khóa trong bundle đã chọn **hoặc các bundle cha**. `getString(...)` ném `MissingResourceException`.

Điều này quan trọng khi thiết kế **chuỗi dự phòng (fallback)**: thiếu một bản dịch ở locale cụ thể **chưa chắc là lỗi** nếu có bản dịch ở bundle cha; chỉ khi không còn nơi hợp lệ để tìm kiếm thì mới phát sinh ngoại lệ.

### Mục tiêu bài học

- Phân biệt **missing bundle** và **missing key**, biết ngoại lệ xảy ra ở lệnh nào.
- Hiểu cách `ResourceBundle` dò tài nguyên theo language/region và kế thừa khóa từ parent.
- Chẩn đoán lỗi base name, classpath, tên tệp, key và môi trường locale.
- Xây chính sách fallback có thể kiểm thử, không giấu bản dịch bị thiếu trong quá trình phát triển.
- Viết và chạy ví dụ Java 17+ với kết quả rõ ràng cho cả hai loại lỗi.

## 2. Kiến thức nền: bundle, base name, locale và key

Một resource bundle là nguồn giá trị theo ngôn ngữ/vùng; với tài nguyên `.properties`, mỗi dòng thường là một cặp `key=value`.

Ví dụ cấu trúc tệp trong classpath:

```text
messages.properties
messages_vi.properties
messages_en_US.properties
```

- `"messages"` trong `ResourceBundle.getBundle("messages", locale)` là **base name**, không phải tên tệp `messages.properties` có đuôi.
- `messages_vi.properties` là ứng viên cho locale tiếng Việt, `messages_en_US.properties` là ứng viên cho tiếng Anh tại Hoa Kỳ.
- `"app.title"` là khóa nằm trong tệp; phần `app.` là một quy ước đặt tên do ứng dụng định nghĩa, không phải cú pháp đường dẫn thư mục của API.
- Giá trị từ tệp `.properties` là chuỗi; ứng dụng có thể dùng `MessageFormat` sau đó để gắn tham số.
- Tên thư mục trong package/classpath là một phần của base name: tài nguyên `src/main/resources/i18n/messages_vi.properties` khi đóng gói ở `i18n/messages_vi.properties` được gọi bằng `"i18n.messages"`.

**Lưu ý về encoding:** từ Java 9, `PropertyResourceBundle` được `ResourceBundle` sử dụng theo mặc định ưu tiên UTF-8 (và có đường tương thích cho dữ liệu Latin-1). Với Java 17, có thể lưu bản dịch tiếng Việt trực tiếp bằng UTF-8. Phải bảo đảm công cụ biên tập/build không tự chuyển encoding sai.

## 3. Khi thiếu bundle: lỗi ở `getBundle(...)`

`getBundle(baseName, locale)` cố gắng tìm bundle theo tên và locale được yêu cầu. Nó có thể tìm đến một ứng viên khác theo thuật toán fallback, nên **không tồn tại tệp khớp chính xác locale không có nghĩa là ngoại lệ ngay lập tức**.

Ví dụ:

```text
Yêu cầu: Locale vi-VN, base name "messages"

Ưu tiên thông thường:
  messages_vi_VN.properties   (cụ thể nhất)
  messages_vi.properties      (ngôn ngữ)
  messages.properties         (bundle gốc, nếu có)

Có thể có fallback liên quan tới locale mặc định JVM,
tùy ứng viên hiện có và cơ chế nạp tài nguyên.
```

Cách biểu diễn trên là sơ đồ khái quát cho tag đơn giản, không phải mô tả toàn bộ thuật toán BCP 47 (script, variant, extension, default locale, class bundle và cơ chế `Control` có thể làm kết quả phức tạp hơn). Khi tìm thấy bundle được chấp nhận, `getBundle(...)` **trả về đối tượng**. Nếu không tìm thấy bundle nào sau quy trình dò/fallback, nó ném `MissingResourceException`.

### Những nguyên nhân phổ biến

- Base name sai, ví dụ gọi `"message"` trong khi tài nguyên tên `messages.properties`.
- Tệp tồn tại trong source tree nhưng không được sao chép lên runtime classpath.
- Base name thiếu package, ví dụ cần `"i18n.messages"` nhưng lại gọi `"messages"`.
- Không có bundle cho locale yêu cầu, cũng không có tài nguyên fallback thích hợp.
- Quy tắc classloader/module hoặc cấu hình tài nguyên làm bundle không truy cập được; lỗi nạp khác cũng có thể xuất hiện tùy nguyên nhân.

Ví dụ xử lý ngoại lệ ở ranh giới nạp:

```java
try {
    ResourceBundle bundle = ResourceBundle.getBundle(
            "messages", Locale.forLanguageTag("vi-VN"));
    System.out.println(bundle.getString("welcome"));
} catch (MissingResourceException ex) {
    System.err.println("Missing bundle or key: " + ex.getKey());
}
```

Đoạn minh họa này **chưa phân biệt** nơi nào phát sinh lỗi vì cả `getBundle` và `getString` nằm trong cùng một `try`. Khi cần chẩn đoán chính xác, hãy tách hai thao tác hoặc kiểm tra tầng phát sinh ngoại lệ và giữ thông tin gốc khi báo lỗi.

## 4. Khi thiếu khóa: lỗi ở `getString(...)`

Giả sử:

**`messages.properties`**

```properties
welcome=Hello!
support=Contact support
```

**`messages_vi.properties`**

```properties
welcome=Xin chào!
```

Khi ứng dụng tải bundle tiếng Việt:

- `getString("welcome")` tìm thấy ở `messages_vi.properties` → `"Xin chào!"`.
- `getString("support")` **không có trong tệp tiếng Việt**, nhưng có trong `messages.properties` → `"Contact support"` thông qua parent fallback.
- `getString("not.existing")` không có ở bundle đang dùng hoặc chuỗi parent → `MissingResourceException`.

Sự khác nhau giữa ba kết quả này là cốt lõi của quản lý bản dịch: fallback bình thường giúp ứng dụng chạy, nhưng bản dịch còn thiếu vẫn cần được nhận diện, theo dõi và hoàn thiện.

### `containsKey(...)` có đủ để kiểm tra?

`ResourceBundle.containsKey(key)` trả `true` nếu khóa tồn tại trong bundle **hoặc parent**. Vì thế:

```java
boolean hasSupport = bundle.containsKey("support"); // true
```

Giá trị `true` ở đây **không chứng minh** bản dịch `"support"` tồn tại trong `messages_vi.properties`; nó có thể đến từ bundle gốc. Tương tự, `bundle.keySet()` bao gồm các khóa có thể truy cập từ parent chain. Nếu muốn kiểm kê bản dịch cụ thể của từng tệp, phải so sánh tài nguyên địa phương theo từng locale hoặc xây công cụ kiểm tra bản dịch thay vì chỉ dùng `containsKey` trên bundle đã fallback.

Không dùng `containsKey` để bỏ qua `getBundle`: nếu bundle không tồn tại, bạn chưa có đối tượng để gọi nó.

## 5. Ví dụ Java 17+ chạy được: thành công, fallback và hai lỗi

Tạo **ba tệp trong cùng thư mục**, lưu bằng UTF-8. Đảm bảo khi chạy, thư mục này có trong classpath để Java tìm được các tệp `.properties`.

**Tệp `messages.properties`**

```properties
welcome=Hello!
support=Contact support
```

**Tệp `messages_vi.properties`**

```properties
welcome=Xin chào!
```

**Tệp `MissingResourceDemo.java`**

```java
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;

public class MissingResourceDemo {

    private static void tryRead(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=found");
        } catch (MissingResourceException ex) {
            System.out.println(label + "=MissingResourceException");
        }
    }

    public static void main(String[] args) {
        Locale vietnamese = Locale.forLanguageTag("vi-VN");

        // 1. Có bundle tiếng Việt và bundle gốc.
        ResourceBundle messages =
                ResourceBundle.getBundle("messages", vietnamese);
        System.out.println("welcome=" + messages.getString("welcome"));

        // 2. Key không có trong bundle tiếng Việt,
        // nhưng được kế thừa từ bundle gốc.
        System.out.println("support=" + messages.getString("support"));
        System.out.println("containsSupport="
                + messages.containsKey("support"));

        // 3. Không có key trong bất kỳ bundle/parent nào.
        tryRead("missingKey",
                () -> messages.getString("not.existing"));

        // 4. Không có bundle thuộc base name được chỉ định.
        tryRead("missingBundle",
                () -> ResourceBundle.getBundle(
                        "missing_bundle_for_this_demo_987654",
                        vietnamese));
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn, trong thư mục chứa ba tệp:

```bash
javac -encoding UTF-8 MissingResourceDemo.java
java -cp . MissingResourceDemo
```

**Stdout chính xác của ví dụ khi thư mục có đúng các tệp nêu trên:**

```text
welcome=Xin chào!
support=Contact support
containsSupport=true
missingKey=MissingResourceException
missingBundle=MissingResourceException
```

### Giải thích từng kết quả

1. Java không thấy `messages_vi_VN.properties` nhưng thấy `messages_vi.properties`, nên có bundle phù hợp.
2. `welcome` được cung cấp trong bundle tiếng Việt; vì thế ưu tiên giá trị `Xin chào!`.
3. `support` bị thiếu trong bundle tiếng Việt nhưng có ở bundle gốc. `getString` tra parent và trả `Contact support`; `containsKey` cũng trả `true`.
4. `not.existing` vắng mặt cả ở bản tiếng Việt lẫn bundle gốc, nên `getString` ném `MissingResourceException`, được `tryRead` bắt để in nhãn.
5. Base name `missing_bundle_for_this_demo_987654` cố ý không tương ứng tài nguyên nào trong ví dụ; `getBundle` ném cùng loại exception, nhưng ở **thời điểm nạp bundle**.

Ví dụ này chỉ bắt và trình bày lỗi để học tập. Trong sản phẩm thật, không nên dùng `catch` chung để coi cả missing key và missing bundle là tình trạng bình thường; cần phân loại nguyên nhân, báo log phù hợp và chọn chính sách hiển thị rõ ràng.

## 6. Đọc thông tin từ `MissingResourceException`

`MissingResourceException` thuộc `java.util` và kế thừa `RuntimeException`. Nó là **unchecked exception**, nên code Java không bắt buộc phải khai báo `throws` hoặc bắt bằng `catch`.

Các thông tin hữu ích:

| API | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| `getMessage()` | Thông điệp giải thích của exception | Log để hỗ trợ chẩn đoán; không phụ thuộc văn bản chính xác để test. |
| `getClassName()` | Class/base-name mà cơ chế tìm kiếm báo liên quan | Giúp xác định đang lỗi resource bundle nào. |
| `getKey()` | Khóa mà exception ghi nhận | Giúp xem lỗi nạp bundle hay lỗi thiếu key. |
| `getCause()` | Nguyên nhân nền nếu được gắn kèm | Phân tích khi lỗi nạp tài nguyên có cause. |

Dữ liệu của `getClassName()` và `getKey()` phản ánh nơi exception được tạo, không phải một hợp đồng có thể tự suy ra mọi đường đi fallback. Nếu test phải phân biệt hai tình huống, dễ kiểm chứng hơn khi tách thao tác tải bundle và thao tác lấy key tại những điểm khác nhau.

Ví dụ chẩn đoán đủ ngữ cảnh nhưng không biến message thành giao diện người dùng:

```java
try {
    ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);
    return bundle.getString(key);
} catch (MissingResourceException ex) {
    logger.warning(() -> "Localization resource lookup failed"
            + " baseName=messages"
            + " locale=" + locale.toLanguageTag()
            + " key=" + key
            + " exceptionKey=" + ex.getKey());
    throw ex;
}
```

Đây là **mã minh họa trong một phương thức** đã có biến `locale`, `key`, `logger` và kiểu trả về `String`; không phải chương trình độc lập. Đoạn mã ném lại lỗi thay vì trả bản dịch đoán mò. Trong log thực tế, cân nhắc mã key/tên tài nguyên, tránh log dữ liệu người dùng không cần thiết.

## 7. Hiểu fallback theo locale và fallback theo khóa

Hai cấp tìm kiếm cần được tách rõ:

**Cấp A — chọn bundle:** `getBundle("messages", requestedLocale)` chọn một bundle phù hợp, dựa trên danh sách candidate và fallback mặc định. Tài nguyên có thể được đặt trong `.properties` hoặc class bundle; classloader/module và cơ chế nạp ảnh hưởng khả năng tìm thấy.

**Cấp B — chọn giá trị theo khóa:** từ bundle được chọn, `getString(key)` tra giá trị trong bundle đó rồi các bundle cha. Một key có thể vắng mặt trong bundle con nhưng có ở cha.

```text
Request locale: vi-VN

getBundle("messages", vi-VN)
    │
    ├─ messages_vi_VN   (không có trong ví dụ)
    ├─ messages_vi      (có, được chọn)
    └─ messages         (bundle gốc/parent)
                ↓
getString("welcome") -> messages_vi -> "Xin chào!"
getString("support") -> messages_vi thiếu -> messages -> "Contact support"
getString("unknown") -> cả hai thiếu -> MissingResourceException
```

**Đừng nhầm “thiếu bản dịch trong locale yêu cầu” với “thiếu key sau fallback”.** Hệ thống có thể đang hiển thị tiếng Anh cho một key tiếng Việt không có bản dịch, và `getString` vẫn hoàn toàn thành công.

### Fallback qua JVM default locale

Theo quy tắc mặc định của `ResourceBundle`, khi không tìm được bundle thích hợp cho locale yêu cầu, quá trình tìm kiếm có thể xét locale mặc định của JVM. Điều này có thể gây bất ngờ: hai môi trường có default locale khác nhau có khả năng chọn bundle khác nhau khi cùng gọi một `getBundle(...)`.

Để kiểm thử chính xác chính sách fallback:

- Nên có bundle gốc rõ ràng (`messages.properties`) chứa các chuỗi fallback được chấp nhận.
- Chỉ rõ `Locale` khi gọi API; không xây test trên giả định mọi máy đều có default locale `en-US`.
- Nếu yêu cầu không được fallback qua JVM default, có thể xem `ResourceBundle.Control.getNoFallbackControl(...)` trong ngữ cảnh classpath hỗ trợ. Cần đọc kỹ điều kiện sử dụng `Control`, đặc biệt ứng dụng named modules, và không coi đây là bước thay thế cho kiểm tra bản dịch.
- Nếu sản phẩm cần fallback có kiểm soát theo danh sách ngôn ngữ riêng (ví dụ `vi-VN` → `en-US` → marker), hãy thiết kế chính sách ở lớp ứng dụng và kiểm thử nó. Thuật toán mặc định có thể khác thứ tự mong muốn của sản phẩm.

## 8. Chiến lược xử lý lỗi khi xây sản phẩm

### 8.1. Khi không tìm thấy bundle

Đây thường là lỗi cấu hình hoặc đóng gói tài nguyên. Cần kiểm tra base name, classpath, tên file và cấu hình build. Tùy ứng dụng, có thể:

1. **Fail fast khi khởi động:** xác minh các bundle bắt buộc trước khi nhận request, báo rõ base name và locale.
2. **Fallback có kiểm soát:** sử dụng bundle gốc hoặc bản dịch bắt buộc được thiết kế sẵn; chỉ khi chính sách cho phép.
3. **Báo lỗi rõ ràng:** khi không có tài nguyên tối thiểu, không giả vờ đã dịch bằng cách trả chuỗi trống.

Đối với hệ thống nhiều người dùng, không nên gọi `Locale.setDefault(...)` mỗi request để “sửa” missing bundle. Đó là trạng thái JVM chung, có thể tác động các request khác và không giải quyết lỗi file resource thiếu.

### 8.2. Khi thiếu một key

Có thể cung cấp cơ chế an toàn, ví dụ:

- Trả marker như `"[missing:app.title]"` trong môi trường phát triển để phát hiện lỗi nhanh.
- Dùng nguồn dự phòng đã định nghĩa rõ, nếu sản phẩm chấp nhận việc hiển thị thông điệp ở ngôn ngữ khác.
- Ghi log hoặc metric chứa base name, locale và key để đo tỷ lệ bản dịch còn thiếu.
- Khi key là chuỗi quan trọng về giao dịch hoặc bảo mật, cần chính sách nghiêm ngặt hơn marker để không làm người dùng hiểu sai.

Nếu muốn bọc API, hãy phân biệt **lỗi không tải được bundle** với **lỗi không có key**. Có thể kiểm tra `containsKey` trước `getString` hoặc tách `try` theo từng bước. Tuy nhiên `containsKey` trên bundle đã có parent cũng phản ánh key từ fallback; nó không dùng để xác định ngôn ngữ thật của từng giá trị.

### 8.3. Không giấu lỗi bằng `catch` quá rộng

Mẫu như `catch (Exception e) { return ""; }` sẽ biến lỗi resource bị thiếu, lỗi sai dữ liệu và thậm chí lỗi lập trình thành chuỗi rỗng. Kết quả có thể khiến giao diện thiếu nhãn, khó chẩn đoán và test giả thành công. Khi bắt `MissingResourceException`, nên kèm ngữ cảnh cần thiết và chỉ chuyển thành fallback nếu đó là chính sách được nêu rõ.

## 9. Chẩn đoán theo trình tự

Khi gặp `MissingResourceException` trong ứng dụng Java:

1. **Xác định điểm ném:** `getBundle(...)` hay `getString(...)`? Đọc stack trace, vị trí gọi và thông tin `getClassName()`/`getKey()`.
2. **Đối chiếu base name:** nếu bundle nằm trong `i18n/`, đường dẫn trong classpath phải tương ứng với `i18n.messages`.
3. **Kiểm tra artifact thực tế:** tệp `.properties` có thật trong thư mục classpath hoặc JAR khi chạy? Không chỉ kiểm tra thư mục source.
4. **Kiểm tra locale dùng để nạp:** in `locale.toLanguageTag()`; trên bundle đã nạp, `bundle.getLocale()` giúp thấy locale mà bundle được chọn đại diện. Giá trị đó có thể không trùng requested locale.
5. **Kiểm tra chữ hoa/chữ thường và key:** tên file/package và key phải khớp chính xác; `"app.title"` khác `"app.Title"`.
6. **Kiểm tra chuỗi parent:** tìm key ở bundle cụ thể và root; hiểu rằng `getString` có thể trả giá trị từ parent.
7. **Kiểm tra encoding và nội dung:** file resource đúng tên nhưng lỗi encoding có thể làm giá trị sai; điều này khác lỗi thiếu key.
8. **Kiểm tra cache nếu vừa thay resource trong lúc chạy:** `ResourceBundle` có cơ chế cache; việc thay tệp trên đĩa không bảo đảm mọi đối tượng bundle cũ tự tải lại. `ResourceBundle.clearCache()` có thể cần trong tình huống kiểm thử hoặc nạp lại được thiết kế rõ ràng, nhưng không thay thế việc đóng gói tài nguyên chính xác.

Nếu thông điệp lỗi từ production có thông tin classloader/module, cần xác định cơ chế resource lookup đang dùng. Không nên suy luận chỉ từ việc tệp tồn tại trong source tree.

## 10. Kiểm thử chính sách fallback

Thiết kế test theo ma trận hành vi thay vì chỉ thử “một locale hiển thị đúng”.

| Dữ liệu đầu vào / cấu hình | Kết quả cần xác minh |
| --- | --- |
| Bundle locale yêu cầu có key | Trả giá trị của locale đó. |
| Bundle locale yêu cầu thiếu key, parent có key | Trả giá trị parent; có kiểm thử phát hiện thiếu bản dịch địa phương. |
| Tất cả bundle trong chain đều thiếu key | `getString` ném `MissingResourceException` hoặc lớp ứng dụng xử lý theo chính sách. |
| Không có bundle phù hợp cho base name | `getBundle` ném `MissingResourceException`. |
| Locale yêu cầu thiếu tệp cụ thể nhưng có tệp ngôn ngữ | Chọn bundle language khi thuật toán matching hỗ trợ. |
| Locale yêu cầu không được ứng dụng hỗ trợ | Ứng dụng áp dụng chính sách fallback có chủ đích, không đoán theo country. |
| Chạy trên máy có default locale khác nhau | Kết quả kiểm thử ổn định bằng cách kiểm soát nguồn fallback. |
| Đổi giá trị tài nguyên ở runtime | Có chính sách cache/reload rõ ràng; không kỳ vọng cập nhật tự động. |

Nên có một bước kiểm tra tính đầy đủ của translation key trong CI, ví dụ lấy tập key của bundle gốc làm danh sách bắt buộc rồi so sánh với các tệp bản dịch ở mức nguồn. **Đừng chỉ gọi `ResourceBundle.keySet()` của bundle đã tải** để chứng minh dịch đầy đủ, vì danh sách này có thể chứa key được kế thừa từ parent.

## 11. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Nghĩ thiếu `messages_vi_VN.properties` là lỗi ngay | Java có thể dùng `messages_vi.properties` hoặc tài nguyên dự phòng. | Xác định candidate và actual bundle. |
| Nghĩ `getString` chỉ xem một tệp | Nó có thể tra parent chain. | Phân biệt key địa phương với key kế thừa. |
| Bắt `MissingResourceException` ở một `try` rất rộng | Khó biết lỗi ở nạp bundle hay lấy key. | Tách hai bước hoặc log điểm phát sinh. |
| Gọi `getBundle("messages.properties", locale)` | Base name thường không gồm đuôi `.properties`. | Dùng `"messages"` hoặc tên có package đúng. |
| Để tệp resource ngoài runtime classpath | File source tồn tại nhưng runtime không thấy. | Kiểm tra `target/classes`, `build/resources` hoặc nội dung JAR. |
| Cho rằng `containsKey` xác nhận đã dịch tại locale hiện tại | Nó xét cả parent. | So sánh nội dung bundle gốc và từng bản dịch cụ thể. |
| Trả chuỗi trống cho mọi exception | Che lỗi cấu hình/thiếu bản dịch, khiến giao diện khó dùng. | Có chính sách fallback, log và test rõ ràng. |
| Cài default locale toàn JVM theo từng request | Trạng thái chung dễ gây nhiễu giữa người dùng. | Truyền `Locale` tường minh. |
| Bỏ qua `MissingResourceException` trong CI | Lỗi xuất hiện muộn trong production. | Kiểm tra độ phủ key và các locale quan trọng. |
| Tin thay file tài nguyên lập tức có hiệu lực | `ResourceBundle` có cache. | Thiết kế reload/cache strategy, test khi cần. |

## 12. Bài tập tự luyện

**Bài 1 — Thiếu key, có fallback:** thêm khóa `goodbye` vào `messages.properties` nhưng không thêm vào `messages_vi.properties`. Chạy `getString("goodbye")` với `vi-VN`; giải thích vì sao không ném ngoại lệ. Sau đó bổ sung `goodbye` vào bản tiếng Việt và so sánh kết quả.

**Bài 2 — Thiếu key hoàn toàn:** gọi `getString("order.unknown")`, bắt `MissingResourceException` và in một marker ổn định. Không đổi nội dung bundle trong quá trình thử; xác nhận ngoại lệ xảy ra ở bước lấy key.

**Bài 3 — Thiếu bundle:** đổi base name sang `"nonexistent.catalog"` và kiểm tra exception ở `getBundle(...)`. Sau đó tạo thư mục `nonexistent/` và bundle `catalog.properties` trên classpath, chạy lại để thấy khác biệt.

**Bài 4 — Kiểm tra chất lượng bản dịch:** có ba file `messages.properties`, `messages_vi.properties`, `messages_fr.properties`. Tạo kiểm tra cho biết key nào có trong root nhưng chưa được dịch ở từng file địa phương. Không lấy `keySet()` của bundle có parent rồi kết luận mọi key đều đã được dịch.

**Bài 5 — Default locale và fallback:** chạy cùng cấu hình bundle với hai giá trị default locale JVM khác nhau trong môi trường test riêng. Quan sát trường hợp không có bundle ứng viên cho requested locale; ghi lại bundle được chọn và so với chính sách fallback mà ứng dụng mong muốn.

### Ghi nhớ

- **Thiếu bundle**: `ResourceBundle.getBundle(...)` không tìm được tài nguyên thích hợp → `MissingResourceException`.
- **Thiếu key**: có bundle, nhưng không có khóa trong bundle và parent → `ResourceBundle.getString(...)` → `MissingResourceException`.
- **Chỉ thiếu bản dịch địa phương**: parent có thể cung cấp giá trị fallback, nên **chưa chắc phát sinh exception**.
- Luôn dùng base name, locale và classpath chính xác; kiểm thử cả ba tình huống trước khi triển khai localization cho người dùng thật.
