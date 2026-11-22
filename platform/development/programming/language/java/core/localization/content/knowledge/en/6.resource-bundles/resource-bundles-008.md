# ResourceBundle.getLocale(): xác định bundle thực sự được nạp trong Java

## 1. Vấn đề: locale yêu cầu chưa chắc là locale được tải

Trong ứng dụng đa ngôn ngữ, một lời gọi như:

```java
Locale requested = Locale.forLanguageTag("fr-CA");
ResourceBundle bundle = ResourceBundle.getBundle("Messages", requested);
```

không có nghĩa JVM chắc chắn đã tìm thấy bundle dành riêng cho tiếng Pháp tại Canada (`fr-CA`). Khi tệp tương ứng không tồn tại, `ResourceBundle` có thể dùng bundle ít cụ thể hơn, locale mặc định của JVM hoặc bundle gốc tùy cơ chế tìm kiếm.

**`ResourceBundle.getLocale()` cho biết locale gắn với đối tượng bundle đã được `getBundle(...)` lựa chọn và trả về.** Đây là cách trực tiếp để biết kết quả tra cứu bundle thực tế, thay vì chỉ biết locale mà người gọi đã yêu cầu.

```java
Locale requested = Locale.forLanguageTag("fr-CA");
ResourceBundle bundle = ResourceBundle.getBundle("Messages", requested);
Locale resolved = bundle.getLocale();
```

Ở đây:

- `requested` là **locale người dùng/ứng dụng yêu cầu**.
- `resolved` là **locale của bundle được tìm thấy**; nó có thể bằng hoặc khác `requested`.
- `bundle.getString("key")` tra cứu một khóa trong bundle hiện tại, và có thể tiếp tục tìm trong các **parent bundles** nếu bundle hiện tại không chứa khóa đó.

Sự phân biệt cuối cùng rất quan trọng: `getLocale()` nhận diện **bundle ở đầu chuỗi được trả về**, không nhất thiết là bundle chứa từng khóa riêng lẻ. Chúng ta sẽ kiểm chứng điều đó bằng ví dụ chạy được.

## 2. Cơ chế nạp và fallback liên quan đến `getLocale()`

Giả sử có các tài nguyên cùng `baseName` là `Messages`:

```text
Messages.properties
Messages_fr.properties
Messages_en_US.properties
```

Một số kết quả minh họa:

| Locale được yêu cầu | Bundle khả dụng phù hợp | `bundle.getLocale()` |
|---|---|---|
| `en-US` | `Messages_en_US.properties` | `en-US` |
| `fr-CA` | `Messages_fr.properties` | `fr` |
| `de-DE` | Chỉ bundle gốc nếu **không dùng fallback sang JVM default** | `Locale.ROOT` |
| `en` | Chỉ bundle gốc nếu không có `Messages_en.properties` và không dùng default fallback | `Locale.ROOT` |
| `Locale.ROOT` | `Messages.properties` | `Locale.ROOT` |

Tên tệp dùng dấu gạch dưới (`_`) theo quy ước tài nguyên Java; mã language tag dùng dấu gạch nối (`-`). Ví dụ `en-US` ánh xạ đến tên bundle `Messages_en_US.properties`. Để lấy tên language tag từ một `Locale`, dùng `toLanguageTag()`.

Trong tìm kiếm mặc định, Java sử dụng các **candidate locales** theo mức độ cụ thể, chẳng hạn với `fr-CA` là `fr_CA`, `fr`, rồi bundle gốc. Đối với locale có script hoặc variant, danh sách ứng viên đầy đủ phức tạp hơn; không nên tự dựng tên bằng cách bỏ một phần chuỗi theo cảm tính.

**Hai loại fallback phải được phân biệt:**

1. **Candidate fallback**: đi từ locale cụ thể về locale tổng quát hơn, ví dụ `fr-CA` → `fr` → root trong cùng lượt tra cứu.
2. **Fallback sang default locale của JVM**: khi không tìm được bundle phù hợp riêng cho locale đích (ngoại trừ root), `ResourceBundle.getBundle` mặc định có thể thử `Locale.getDefault()` trước khi trả bundle gốc.

Do đó, nếu JVM có default locale `en-US` và tồn tại `Messages_en_US.properties`, yêu cầu `de-DE` có thể trả bundle `en-US` thay vì root, **ngay cả khi tồn tại `Messages.properties`**. Đây là lý do cần đo `getLocale()` thay vì tự suy luận theo tên tệp.

Cơ chế này được điều chỉnh bằng `ResourceBundle.Control` khi dùng các overload hỗ trợ Control. Với ví dụ trên classpath, ta có thể dùng `Control.getNoFallbackControl(...)` để **ngăn việc tìm tiếp theo default locale**, giúp thí nghiệm có kết quả ổn định. Điều đó không tắt chuỗi parent bundles cho các khóa dữ liệu.

## 3. Ví dụ Java 17+ hoàn chỉnh, chạy được không phụ thuộc default locale

Tạo bốn tệp trong **cùng một thư mục**. Ba tệp `.properties` là dữ liệu tài nguyên; tệp `.java` là chương trình gọi và in kết quả.

### Tệp 1 — `Messages.properties`: bundle gốc

```properties
hello=Root hello
shared=Shared from root
```

`Messages.properties` không có phần hậu tố locale; nếu được nạp, bundle tương ứng có `Locale.ROOT`.

### Tệp 2 — `Messages_fr.properties`: tiếng Pháp chung

```properties
hello=Bonjour
```

Đây là bundle `fr`, **không phải** `fr-CA`. Nó cố tình không có khóa `shared` để minh họa việc kế thừa khóa từ parent bundle.

### Tệp 3 — `Messages_en_US.properties`: tiếng Anh tại Hoa Kỳ

```properties
hello=Howdy
```

Bundle này cũng cố tình thiếu `shared`. Không có `Messages_en.properties`, vì vậy yêu cầu language đơn giản `en` không tự tìm “chiều lên” `en-US` khi fallback sang default bị tắt.

### Tệp 4 — `BundleLocaleDemo.java`

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleLocaleDemo {
    private static final ResourceBundle.Control NO_DEFAULT_FALLBACK =
            ResourceBundle.Control.getNoFallbackControl(
                    ResourceBundle.Control.FORMAT_PROPERTIES);

    public static void main(String[] args) {
        printBundle("fr-CA");
        printBundle("en-US");
        printBundle("de-DE");
        printBundle("en");

        ResourceBundle root = ResourceBundle.getBundle(
                "Messages", Locale.ROOT, NO_DEFAULT_FALLBACK);

        System.out.println(
                "root is Locale.ROOT: " + root.getLocale().equals(Locale.ROOT));
        System.out.println(
                "root toLanguageTag: " + root.getLocale().toLanguageTag());
    }

    private static void printBundle(String requestedTag) {
        Locale requested = Locale.forLanguageTag(requestedTag);

        ResourceBundle bundle =
                ResourceBundle.getBundle(
                        "Messages", requested, NO_DEFAULT_FALLBACK);

        Locale actual = bundle.getLocale();
        String actualTag = actual.equals(Locale.ROOT)
                ? "ROOT"
                : actual.toLanguageTag();

        System.out.printf(
                "requested=%s | actual=%s | same=%s | hello=%s | shared=%s%n",
                requested.toLanguageTag(),
                actualTag,
                requested.equals(actual),
                bundle.getString("hello"),
                bundle.getString("shared"));
    }
}
```

Chương trình dùng `FORMAT_PROPERTIES` để chỉ xét `.properties` và `getNoFallbackControl` để loại trừ đường fallback sang locale mặc định JVM. Đây là lựa chọn **cho ví dụ thử nghiệm trên classpath**, không phải yêu cầu bắt buộc cho mọi ứng dụng. Một số overload dùng `ResourceBundle.Control` không được hỗ trợ từ named module; nếu ứng dụng dùng Java modules, cần tra cứu quy tắc bundle loading và cách khai báo tài nguyên tương ứng.

Mở terminal tại thư mục chứa bốn tệp và chạy:

```bash
javac BundleLocaleDemo.java
java BundleLocaleDemo
```

Kết quả dự kiến trên Java 17+:

```text
requested=fr-CA | actual=fr | same=false | hello=Bonjour | shared=Shared from root
requested=en-US | actual=en-US | same=true | hello=Howdy | shared=Shared from root
requested=de-DE | actual=ROOT | same=false | hello=Root hello | shared=Shared from root
requested=en | actual=ROOT | same=false | hello=Root hello | shared=Shared from root
root is Locale.ROOT: true
root toLanguageTag: und
```

Cách đọc kết quả:

- `fr-CA` không có bundle riêng. JVM tìm `Messages_fr.properties` nên `getLocale()` trả `fr`.
- `en-US` có bundle khớp chính xác nên `getLocale()` trả `en-US`.
- `de-DE` không có `de_DE` hay `de`. Do đã tắt fallback sang default locale, kết quả là `Messages.properties` có locale `ROOT`.
- `en` không có `Messages_en.properties`. Nó không tìm ngược sang bundle cụ thể hơn `en-US`; kết quả là root.
- `Locale.ROOT.toLanguageTag()` trả `"und"` (*undetermined*) khi chuyển sang language tag. Để phát hiện root trong code, dùng `actual.equals(Locale.ROOT)`. `Locale.ROOT.toString()` là chuỗi rỗng, vì vậy không nên log chỉ bằng `toString()` rồi hiểu dòng trống là không có bundle.

Nếu thay đổi cấu trúc tệp, ví dụ bổ sung `Messages_fr_CA.properties`, kết quả khi yêu cầu `fr-CA` sẽ khác. Điều này chính là thông tin mà `getLocale()` giúp ta quan sát.

## 4. Điểm tinh tế: `getLocale()` không nói khóa `getString()` đến từ tệp nào

Trong ví dụ trên, yêu cầu `en-US` cho kết quả:

```text
actual=en-US | ... | hello=Howdy | shared=Shared from root
```

Vì `Messages_en_US.properties` chứa `hello`, `getString("hello")` tìm thấy giá trị ở bundle `en-US`. Nhưng khóa `shared` chỉ nằm trong `Messages.properties`. Khi không tìm thấy khóa ở bundle `en-US`, Java tiếp tục đi qua **parent chain**, nên vẫn trả được `Shared from root`.

Tuy vậy, `bundle.getLocale()` **vẫn là `en-US`** sau khi lấy `shared`.

Điều này đưa đến hai câu hỏi riêng:

| Câu hỏi | API phù hợp |
|---|---|
| “`getBundle` đã trả về bundle cho locale nào?” | `bundle.getLocale()` |
| “Một khóa cụ thể đang lấy giá trị từ bundle nào trong parent chain?” | Không thể suy ra chỉ bằng `bundle.getLocale()`; phải kiểm tra nguồn giá trị hoặc thiết kế công cụ tra cứu/ghi log riêng |

`ResourceBundle.getString` gọi cơ chế tra cứu khóa của bundle, có thể rơi về parent; `getObject` hoạt động tương tự. `containsKey` và `keySet` cũng có thể tính đến parent bundles, vì vậy chúng **không phải** bằng chứng rằng khóa được định nghĩa trực tiếp trong tệp có locale bằng `getLocale()`.

Điểm sai thường gặp trong logging:

```java
String label = bundle.getString("shared");
System.out.println("Loaded from " + bundle.getLocale());
```

Dòng log trên có thể khiến người đọc hiểu nhầm `shared` được định nghĩa trong bundle `en-US`. Câu mô tả chính xác hơn là **“Selected bundle locale = en-US”**. Nếu cần audit dịch thiếu theo từng khóa, hãy có cơ chế theo dõi nơi định nghĩa khóa thay vì gán nhãn nguồn dựa vào `getLocale()`.

## 5. Fallback mặc định có thể làm `getLocale()` bất ngờ

Khi sử dụng overload đơn giản:

```java
ResourceBundle bundle =
        ResourceBundle.getBundle("Messages", requested);
```

Java có thể thử default locale của JVM nếu không tìm thấy bundle cụ thể cho locale được yêu cầu. Việc đã có bundle root **không nhất thiết chấm dứt ngay** mọi tìm kiếm trước khi JVM thử default locale.

Để quan sát hành vi đó trên bộ tệp ở mục 3, ta có thể thêm một chương trình kiểm chứng độc lập, `DefaultFallbackDemo.java`:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class DefaultFallbackDemo {
    public static void main(String[] args) {
        Locale previousDefault = Locale.getDefault();

        try {
            Locale.setDefault(Locale.US);

            ResourceBundle bundle = ResourceBundle.getBundle(
                    "Messages",
                    Locale.forLanguageTag("de-DE"));

            System.out.println(bundle.getLocale().toLanguageTag());
            System.out.println(bundle.getString("hello"));
        } finally {
            Locale.setDefault(previousDefault);
        }
    }
}
```

Chạy với **cùng ba tệp properties**:

```bash
javac DefaultFallbackDemo.java
java DefaultFallbackDemo
```

Kết quả trong quy trình thử này:

```text
en-US
Howdy
```

Ở đây yêu cầu là `de-DE` nhưng JVM default được đặt tạm thành `en-US`. Vì tồn tại `Messages_en_US.properties`, `ResourceBundle.getBundle` trả bundle tương ứng với **default locale**, và `getLocale()` phản ánh đúng thực tế đó.

**Không gọi `Locale.setDefault(...)` theo từng HTTP request trong dịch vụ thật.** Đây là trạng thái mặc định chia sẻ cho tiến trình, có thể gây ảnh hưởng chéo giữa người dùng và các luồng. Chỉ dùng thao tác đặt default có khôi phục như trên trong thí nghiệm độc lập. Trong ứng dụng thực tế, truyền locale yêu cầu tường minh và xây dựng chính sách fallback nhất quán.

Nếu cần tránh fallback sang default locale trong một ứng dụng classpath, cân nhắc:

```java
ResourceBundle.Control control =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle bundle =
        ResourceBundle.getBundle("Messages", requested, control);
```

Cần nhớ: “NoFallback” trong tên API này **ngăn fallback sang default locale**; nó không loại bỏ các candidate ít cụ thể hơn như `fr` và root, cũng không loại bỏ parent chain để tra cứu khóa.

## 6. Cách phân loại kết quả bằng `getLocale()`

Sau khi gọi `getBundle` thành công, một dịch vụ có thể phân biệt:

1. **Exact match**: `bundle.getLocale().equals(requested)` trả `true`. Bundle được chọn đúng locale yêu cầu.
2. **Candidate fallback**: hai locale khác nhau nhưng bundle đã chọn là một candidate ít cụ thể hơn, chẳng hạn `fr-CA` → `fr`.
3. **Default-locale fallback**: bundle đã chọn là locale mặc định JVM (hoặc candidate của nó), có thể khác hẳn ngôn ngữ người dùng yêu cầu.
4. **Root fallback**: `bundle.getLocale().equals(Locale.ROOT)`, tức bundle không mang mã language/region cụ thể.
5. **Không có bundle**: `getBundle(...)` ném `MissingResourceException`; không có đối tượng để gọi `getLocale()`.

Lưu ý: chỉ so sánh `requested` với `actual` là đủ phát hiện **match hay mismatch**, nhưng không luôn xác định được **tại sao** mismatch. Nếu phải phân loại chính xác candidate fallback và default fallback, cần biết cấu hình `ResourceBundle.Control`, các candidate locales, default locale được sử dụng tại thời điểm tra cứu và tập tài nguyên sẵn có. Không chỉ nhìn `actual.getLanguage()` rồi kết luận loại fallback.

Đặc biệt, khi sử dụng custom `Control`, resource bundle provider hoặc Java modules, chiến lược tìm kiếm có thể thay đổi. `getLocale()` vẫn là thông tin về đối tượng bundle được trả về, nhưng không mô tả toàn bộ lịch sử tìm kiếm.

## 7. Ghi log đúng cách để debug lựa chọn bản dịch

Một mẫu log cơ bản:

```java
Locale requested = Locale.forLanguageTag("fr-CA");
ResourceBundle bundle = ResourceBundle.getBundle(
        "Messages",
        requested,
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES));

Locale actual = bundle.getLocale();
String actualTag = actual.equals(Locale.ROOT)
        ? "ROOT"
        : actual.toLanguageTag();

System.out.printf(
        "bundle=Messages requested=%s resolved=%s exact=%s%n",
        requested.toLanguageTag(),
        actualTag,
        requested.equals(actual));
```

Đây là **đoạn mã đặt trong chương trình đã có biến và import `Locale`, `ResourceBundle`**; các ví dụ hoàn chỉnh ở mục trước có thể chạy độc lập. Log cần phân biệt rõ tên bundle (`baseName`), locale được yêu cầu và locale được chọn.

Các thông tin nên cân nhắc khi chẩn đoán:

| Dữ liệu | Lý do |
|---|---|
| `baseName` | Cho biết nhóm tệp tài nguyên nào đang được tìm |
| `requested.toLanguageTag()` | Xác định yêu cầu từ ứng dụng/người dùng |
| `bundle.getLocale()` | Cho biết locale gắn với bundle đã nạp |
| `requested.equals(bundle.getLocale())` | Phát hiện có khớp locale chính xác hay không |
| Default locale/Control nếu có | Giải thích đường fallback khi cần |
| Khóa đang tra cứu và kết quả | Giúp tìm vấn đề dịch thiếu; không suy ra nguồn khóa chỉ từ `getLocale()` |

Không nhất thiết log toàn bộ HTTP header hay thông tin người dùng nếu không phục vụ việc debug. Với các hệ thống có nhiều requests, phân biệt rõ dữ liệu per-request và cấu hình chung.

## 8. Xử lý trường hợp không tìm thấy bundle

Nếu không có `Messages.properties` lẫn các biến thể phù hợp (kể cả những nguồn tìm qua default locale), lời gọi `getBundle(...)` sẽ ném `java.util.MissingResourceException`.

Ví dụ minh họa trong một chương trình Java:

```java
try {
    ResourceBundle bundle =
            ResourceBundle.getBundle("UnknownMessages", Locale.JAPAN);
    System.out.println(bundle.getLocale().toLanguageTag());
} catch (java.util.MissingResourceException ex) {
    System.out.println("Khong tim thay resource bundle");
}
```

`UnknownMessages` ở đây phải thực sự không có file/class tương ứng trên classpath; nếu trùng bundle có sẵn thì kết quả sẽ khác. Lưu ý không truy cập `bundle.getLocale()` khi `getBundle` chưa trả về bundle.

Ngược lại, nếu **bundle được tìm thấy nhưng khóa thiếu ở cả bundle hiện tại và parent**, `bundle.getString("key")` cũng có thể ném `MissingResourceException`. Hai lỗi khác nhau:

- *Missing bundle*: chưa lấy được `ResourceBundle`.
- *Missing key*: đã lấy được bundle, nhưng không có khóa ở chuỗi tra cứu.

Khi xử lý lỗi, giữ thông tin `baseName`, locale yêu cầu, locale thực tế (nếu đã có bundle) và khóa bị thiếu. Điều này giúp nhận biết lỗi cấu hình tài nguyên hay lỗi thiếu bản dịch.

## 9. `getLocale()` và cơ chế cache

`ResourceBundle.getBundle(...)` có thể dùng cache để tái sử dụng các resource bundles đã nạp. `getLocale()` vẫn thể hiện locale của **đối tượng được trả về** ngay cả khi đối tượng đến từ cache; nó không phải timestamp hay chứng cứ bundle vừa được đọc lại từ đĩa.

Một số điểm thực tế:

- Thay đổi nội dung `Messages_fr.properties` trong lúc ứng dụng đang chạy không bảo đảm lần `getBundle` kế tiếp lập tức đọc lại tệp.
- `ResourceBundle.clearCache()` hoặc các cấu hình time-to-live/reload trong `Control` có thể cần thiết trong công cụ phát triển; chỉ sử dụng khi hiểu tác động cache của ứng dụng.
- Việc đổi default locale trong cùng tiến trình có thể thay đổi hướng tìm fallback. Đừng dùng `getLocale()` của một lần gọi cũ như thể nó mô tả kết quả của mọi lần gọi tiếp theo.
- Nếu gặp lỗi locale không mong muốn, hãy kiểm tra classpath, tên resource, candidate locales, default locale, cơ chế module/classloader và cache.

Thông thường, ứng dụng production đóng gói các tệp properties cùng bản build; khi đó giải pháp ổn định nhất là xác định rõ bộ locale hỗ trợ và kiểm thử trên đúng artifact được triển khai.

## 10. Những lỗi thường gặp

**Lỗi 1 — Đồng nhất locale yêu cầu với locale đã nạp.** Lệnh `getBundle("Messages", frCA)` có thể trả bundle `fr`, default locale hoặc root. Luôn xem `getLocale()`.

**Lỗi 2 — Dựa vào `Locale.getDefault()` để đoán kết quả.** JVM default có thể là một đường fallback, nhưng bundle phù hợp với locale yêu cầu thường được ưu tiên. Bundle thực tế phải đo từ kết quả `getBundle`.

**Lỗi 3 — Coi bundle root là `null`.** Khi bundle gốc được chọn, `getLocale()` trả `Locale.ROOT`, không phải `null`. `Locale.ROOT.toLanguageTag()` là `und`, còn `toString()` rỗng.

**Lỗi 4 — Coi `getLocale()` là locale nguồn của từng khóa.** Một khóa có thể được kế thừa từ parent `Messages.properties` dù bundle được chọn là `en-US`.

**Lỗi 5 — Hiểu sai `getNoFallbackControl`.** Nó ngăn tìm tiếp theo default locale nhưng vẫn cho phép tìm parent/candidate và root.

**Lỗi 6 — Tự tạo tên tệp từ chuỗi locale sai.** `fr-CA` dùng dấu `-` trong BCP 47; tên tệp resource Java là `Messages_fr_CA.properties`. Script/variant làm quy tắc candidate phức tạp hơn.

**Lỗi 7 — Giả định `fr-CA` tự chuyển sang `fr-FR`.** Candidate fallback thông thường có thể thử `fr`, chứ không tùy tiện chọn một region khác cùng language. Default locale hoặc custom policy là câu chuyện khác.

**Lỗi 8 — Bỏ qua `MissingResourceException`.** Thiếu bundle hoặc thiếu khóa có thể gây lỗi runtime; thiết kế dữ liệu gốc và cơ chế fallback hợp lý.

**Lỗi 9 — Dùng `Locale.setDefault` trên mỗi request.** Default locale là trạng thái chia sẻ trong JVM; truyền `Locale` tường minh và tránh cập nhật toàn cục từ request.

**Lỗi 10 — Dùng `getLocale()` để xác nhận bản dịch đầy đủ.** Exact match chỉ chứng minh bundle được chọn có đúng locale, không chứng minh mọi khóa có bản dịch cho locale đó.

## 11. Câu hỏi tự kiểm tra

1. **Yêu cầu `fr-CA`, chỉ có `Messages_fr.properties` và root, không fallback JVM default. `getLocale()` là gì?** → `fr`.
2. **Yêu cầu `de-DE`, chỉ có root và không fallback default. `getLocale()` là gì?** → `Locale.ROOT`.
3. **Yêu cầu `en-US`, bundle `en-US` thiếu khóa `shared` nhưng root có khóa đó. `getLocale()` sau `getString("shared")` là gì?** → Vẫn `en-US`.
4. **`getLocale()` trả `Locale.ROOT`, gọi `toLanguageTag()` ra gì?** → `"und"`.
5. **Không có bundle phù hợp và không có root. Lấy `getLocale()` bằng cách nào?** → Không thể, vì `getBundle` ném `MissingResourceException`.
6. **Muốn tránh fallback sang default locale trong ví dụ classpath Java 17, dùng gì?** → `ResourceBundle.Control.getNoFallbackControl(...)` với định dạng phù hợp.

## 12. Ghi nhớ

`ResourceBundle.getLocale()` giúp trả lời câu hỏi chính xác: **“Bundle mà Java thực sự trả về thuộc locale nào?”**. So sánh nó với locale được yêu cầu để phát hiện fallback, kiểm tra `Locale.ROOT` để nhận diện bundle gốc và luôn nhớ rằng tra cứu **từng khóa** có thể tiếp tục qua parent bundles khác. Khi hành vi không như kỳ vọng, kiểm tra candidate locales, default locale, nguồn resources, Control/module và cache.

**Tài liệu chính thức:** [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html) · [Java SE 17 — ResourceBundle.Control](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html) · [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html).
