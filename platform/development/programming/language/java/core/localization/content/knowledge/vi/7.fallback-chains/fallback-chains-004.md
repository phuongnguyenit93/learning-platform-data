# Vai trò của locale mặc định và bundle gốc khi không có bản khớp

## 1. Bài toán: yêu cầu ngôn ngữ không có trong các bản dịch

Giả sử một ứng dụng Java có các tệp tài nguyên sau:

```text
messages.properties
messages_en.properties
messages_vi.properties
```

Người dùng muốn `ja-JP` (tiếng Nhật ở Nhật Bản), nhưng ứng dụng chưa có `messages_ja_JP.properties` hoặc `messages_ja.properties`. Kết quả của:

```java
ResourceBundle bundle =
        ResourceBundle.getBundle("messages",
                Locale.forLanguageTag("ja-JP"));
```

không phải lúc nào cũng là văn bản trong `messages.properties`. Với cơ chế tìm kiếm mặc định của `java.util.ResourceBundle`, JVM có thể tìm thêm theo **locale mặc định** của tiến trình, trước khi dùng **bundle gốc** (*root/base bundle*) làm lựa chọn cuối.

Hiểu đúng điều này giúp tránh lỗi ứng dụng chạy ở máy chủ có ngôn ngữ khác thì người dùng nhận thông báo khác, dù đầu vào `Locale` giống nhau.

Bài này tập trung vào ba câu hỏi: khi nào Java thử default locale, bundle gốc đóng vai trò gì, và vì sao **thiếu bản dịch cho một locale** khác với **thiếu một key trong bundle đã chọn**.

## 2. Ba locale/bundle không được nhầm lẫn

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Locale được yêu cầu (*requested/target locale*) | `Locale.forLanguageTag("ja-JP")` | Ngôn ngữ mà caller muốn nhận |
| Locale mặc định của JVM (*default locale*) | `Locale.getDefault()` bằng `en-US` | Có thể được dùng cho bước tìm kiếm dự phòng khi target không có bundle phù hợp |
| Bundle gốc (*base/root bundle*) | `messages.properties` | Nguồn tài nguyên không gắn hậu tố locale, có thể là lựa chọn cuối và là bundle cha của bản dịch cụ thể |

**Root bundle và `Locale.ROOT` liên quan nhưng không đồng nhất khái niệm:**

- `Locale.ROOT` là đối tượng `Locale` có các thành phần ngôn ngữ/vùng rỗng.
- `messages.properties` là tệp **bundle gốc** của họ tài nguyên có base name `messages`. Khi bundle gốc được chọn, `bundle.getLocale().equals(Locale.ROOT)` là `true`.
- `Locale.getDefault()` lấy locale mặc định của JVM; nó không tự động là `Locale.ROOT`, cũng không đồng nghĩa với ngôn ngữ mặc định **do sản phẩm** công bố.

Lệnh `ResourceBundle.getBundle("messages")` sử dụng locale mặc định làm **locale được yêu cầu**. Lệnh `ResourceBundle.getBundle("messages", selectedLocale)` dùng locale được truyền vào, nhưng trong quy tắc mặc định vẫn có thể thử default locale khi không có bản khớp.

Trong dịch vụ web nhiều người dùng, default locale của JVM thường **không** đại diện cho sở thích của từng request. Tùy ứng dụng, locale của một người dùng có thể đến từ cấu hình tài khoản hoặc `Accept-Language`; cần chọn nó rõ ràng và thiết kế fallback của sản phẩm.

## 3. Tên bundle và trình tự candidate locale

Với base name `messages` và target `fr-CA`, cơ chế chuẩn của ResourceBundle có thể tìm những candidate sau:

```text
messages_fr_CA.properties
messages_fr.properties
messages.properties
```

Trên thực tế, mỗi candidate còn có thể tương ứng với một lớp ResourceBundle (dạng `.class` được kiểm tra trước `.properties`) và các locale có script/variant tạo danh sách chi tiết hơn. Ba dòng trên chỉ là mô hình đơn giản cho locale chỉ có language + country.

Điểm quan trọng: **gặp bundle gốc không đồng nghĩa lập tức trả root cho mọi request**. Theo thuật toán mặc định được mô tả trong JDK:

1. Thử các bundle đặc thù của **target locale**, từ cụ thể đến tổng quát (ví dụ `fr_CA` rồi `fr`).
2. Nếu tìm được bundle **không phải root** phù hợp với target, chọn nó; quá trình dựng parent chain sẽ gắn các bundle cha có sẵn, bao gồm root nếu có.
3. Nếu chỉ tìm được root trong lượt target, tạm **giữ root**.
4. Nếu chưa có bundle không phải root phù hợp, thử danh sách candidate của **default locale** (trừ khi quy tắc fallback hoặc `Control` đặc biệt chặn bước này).
5. Nếu tìm được bundle không phải root theo default locale, dùng bundle đó. Nếu vẫn không có, trả root đã giữ lại nếu tồn tại. Nếu không tìm được bundle nào, ném `MissingResourceException`.

Dấu hiệu dễ quan sát là `bundle.getLocale()`: nó cho biết locale của bundle thực tế được chọn. **Nó có thể khác hoàn toàn với locale truyền vào `getBundle`.**

Cơ chế trên mô tả hành vi mặc định với ResourceBundle thông thường trên classpath ở JDK 17+. Với hệ thống dùng named module, `ResourceBundleProvider`, `ResourceBundle.Control` tùy chỉnh hoặc framework i18n riêng, cách tìm kiếm có thể khác; phải kiểm tra hợp đồng của từng cơ chế.

## 4. Thí nghiệm có kiểm soát: default locale được ưu tiên trước root

Tạo cùng thư mục bốn tệp:

```text
fallback-demo/
├── FallbackDemo.java
├── messages.properties
├── messages_en.properties
└── messages_vi.properties
```

Tệp `messages.properties` (**bundle gốc**):

```properties
screen.title=Base screen
screen.help=Help from root
```

Tệp `messages_en.properties`:

```properties
screen.title=English screen
```

Tệp `messages_vi.properties`:

```properties
screen.title=Màn hình tiếng Việt
```

Ở đây chỉ root có key `screen.help`. Điều đó giúp phân biệt **lựa chọn bundle** và **tra cứu key trên parent chain**.

Mã `FallbackDemo.java`:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class FallbackDemo {
    private static void show(Locale requested) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("messages", requested);

        System.out.println("request: " + requested.toLanguageTag());
        System.out.println("selected: " +
                bundle.getLocale().toLanguageTag());
        System.out.println("title: " + bundle.getString("screen.title"));
        System.out.println("help: " + bundle.getString("screen.help"));
    }

    public static void main(String[] args) {
        Locale original = Locale.getDefault();
        try {
            // Cố định môi trường cho ví dụ; tránh làm vậy theo request.
            Locale.setDefault(Locale.forLanguageTag("en-US"));

            show(Locale.forLanguageTag("ja-JP"));
            show(Locale.forLanguageTag("vi-VN"));
            show(Locale.ROOT);
        } finally {
            Locale.setDefault(original);
        }
    }
}
```

Lưu cả bốn tệp UTF-8, mở terminal ở thư mục này và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 FallbackDemo.java
java -cp . FallbackDemo
```

Stdout (với ba file tài nguyên đúng như trên):

```text
request: ja-JP
selected: en
title: English screen
help: Help from root
request: vi-VN
selected: vi
title: Màn hình tiếng Việt
help: Help from root
request: und
selected: und
title: Base screen
help: Help from root
```

Phân tích từng lần gọi:

- **Yêu cầu `ja-JP`:** không có `messages_ja_JP` và `messages_ja`. Root có tồn tại nhưng được tạm giữ. Vì JVM có default locale `en-US`, Java tìm `messages_en_US` rồi `messages_en`, chọn `messages_en.properties`; `getLocale()` trả `en`, dù yêu cầu là `ja-JP`.
- **Yêu cầu `vi-VN`:** Java tìm được `messages_vi.properties`, nên chọn `vi` mà không cần đổi sang default `en-US`. Key `screen.help` không có trong bundle tiếng Việt, nên được lấy từ parent là root.
- **Yêu cầu `Locale.ROOT`:** vì `messages.properties` tồn tại, root là lựa chọn trực tiếp; `Locale.ROOT.toLanguageTag()` trả `und`. Không cần dùng bundle tiếng Anh của locale mặc định.

**Điểm mấu chốt:** ở lần gọi tiếng Nhật, `screen.title` là tiếng Anh do **fallback của việc chọn bundle**. Ở lần gọi tiếng Việt, `screen.help` là tiếng Anh do **fallback của việc tra cứu key trên parent chain**. Hai cơ chế khác nhau.

`Locale.setDefault` chỉ được dùng trong `main` của ví dụ để kết quả có thể tái lập và được khôi phục bằng `finally`. Trong ứng dụng phục vụ nhiều request đồng thời, **không thay default locale toàn JVM cho từng người dùng**, vì trạng thái này ảnh hưởng luồng và thư viện khác.

## 5. Khi default locale cũng không có bundle: root là lựa chọn cuối

Vẫn giữ ba tệp của phần 4 nhưng thay locale mặc định trong ví dụ từ `en-US` sang `de-DE`:

```java
Locale.setDefault(Locale.forLanguageTag("de-DE"));
ResourceBundle bundle = ResourceBundle.getBundle(
        "messages", Locale.forLanguageTag("ja-JP"));
System.out.println(bundle.getLocale().toLanguageTag());
System.out.println(bundle.getString("screen.title"));
```

Với các tệp `messages.properties`, `messages_en.properties`, `messages_vi.properties`:

```text
und
Base screen
```

Lý do: không có bundle cho `ja-JP` và `de-DE`; root `messages.properties` là nguồn còn lại. `getLocale()` trả ROOT, biểu diễn language tag là `und`.

Bảng quyết định với **cùng tập bundle** đó:

| Target | JVM default | Bundle thực tế được chọn | Vì sao |
| --- | --- | --- | --- |
| `vi-VN` | `en-US` | `messages_vi` | Có bản tiếng Việt phù hợp target |
| `ja-JP` | `en-US` | `messages_en` | Target thiếu, default `en-US` có bundle `en` |
| `ja-JP` | `de-DE` | `messages` (root) | Target và default đều thiếu bản riêng |
| `Locale.ROOT` | `en-US` | `messages` (root) | Đã yêu cầu root và root tồn tại |
| `en-GB` | `vi-VN` | `messages_en` | Candidate `en` khớp target, không cần default |

Bảng này nói về **lựa chọn bundle**, không mặc định rằng bundle được chọn tự chứa tất cả key.

## 6. Thiếu locale, thiếu key và thiếu root khác nhau

### Trường hợp A: không có bundle cho target

Nếu chỉ có `messages.properties` và `messages_en.properties`, target `ja-JP` không khớp. Có thể chọn `en` nếu default là `en-US`, hoặc chọn root nếu default cũng không có bundle phù hợp.

### Trường hợp B: có bundle cho target nhưng thiếu một key

Nếu `messages_vi.properties` chứa:

```properties
screen.title=Màn hình tiếng Việt
```

và root chứa `screen.help`, thì:

```java
ResourceBundle bundle =
        ResourceBundle.getBundle("messages",
                Locale.forLanguageTag("vi-VN"));

String title = bundle.getString("screen.title");
String help = bundle.getString("screen.help");
```

`title` lấy từ bundle `vi`, `help` lấy từ bundle gốc. Ở đây Java **không** duyệt qua bundle của default locale `en` để tìm key còn thiếu; parent chain của bundle được chọn là cơ chế quyết định.

### Trường hợp C: không có bundle gốc

Nếu chỉ có `messages_en.properties` và default `en-US`, target `ja-JP` vẫn có thể fallback sang `en`. Tuy nhiên, không có root để cung cấp các key bị thiếu trong `messages_en`.

Nếu target không khớp, default cũng không khớp, **và không có bundle gốc**, `ResourceBundle.getBundle` ném `MissingResourceException`. Vì thế đặt bundle gốc có bộ key đầy đủ là thực hành phổ biến, dù ứng dụng có thể chủ động chọn một chính sách khác.

### Trường hợp D: có bundle nhưng key không có ở bất kỳ parent nào

`bundle.getString("unknown.key")` ném `MissingResourceException` nếu cả bundle được chọn và chuỗi cha của nó đều thiếu key đó. Lỗi này khác với lỗi lúc `getBundle` không tải được bundle nào.

`bundle.containsKey(key)` kiểm tra key trong cả bundle và parent chain. `bundle.keySet()` cũng có thể bao gồm key kế thừa; do đó một lời gọi `containsKey` thành công **không chứng minh key đã được dịch riêng trong chính tệp của locale yêu cầu**.

## 7. Quan sát bundle nào đã được chọn

Khi gỡ lỗi, log cả target locale và locale thực tế:

```java
Locale requested = Locale.forLanguageTag("ja-JP");
ResourceBundle bundle = ResourceBundle.getBundle("messages", requested);

System.out.println("requested=" + requested.toLanguageTag());
System.out.println("resolved=" + bundle.getLocale().toLanguageTag());
System.out.println("base=" + bundle.getBaseBundleName());
```

`getLocale()` xác định locale của bundle thực tế được chọn, kể cả khi đó là default locale hoặc ROOT. `getBaseBundleName()` có thể giúp xác định họ tài nguyên (`messages`). Đừng kết luận ứng dụng có bản dịch `ja-JP` chỉ vì `getBundle("messages", jaJP)` trả về một đối tượng: nó có thể là bundle tiếng Anh hoặc root.

Nếu cần kiểm tra bản dịch có đầy đủ, hãy so sánh các key theo chính sách trong pipeline dịch hoặc kiểm tra trực tiếp các tệp nguồn. Phương thức `getString` có fallback giúp ứng dụng tiếp tục chạy, nhưng cũng có thể che giấu thiếu bản dịch của một locale.

## 8. Kiểm soát fallback: không muốn phụ thuộc default của JVM

Trong một số ứng dụng, yêu cầu rõ ràng là:

> Nếu không có bundle cho ngôn ngữ được yêu cầu, dùng bundle gốc; không tự động nhảy sang ngôn ngữ mặc định của máy chủ.

Đối với ứng dụng chạy trên **classpath / unnamed module**, Java cho phép điều chỉnh qua `ResourceBundle.Control`:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class NoDefaultFallbackDemo {
    public static void main(String[] args) {
        Locale original = Locale.getDefault();
        try {
            Locale.setDefault(Locale.US);

            Locale japanese = Locale.JAPAN;
            ResourceBundle normal =
                    ResourceBundle.getBundle("messages", japanese);

            ResourceBundle.Control noDefaultFallback =
                    ResourceBundle.Control.getNoFallbackControl(
                            ResourceBundle.Control.FORMAT_PROPERTIES);

            ResourceBundle strict =
                    ResourceBundle.getBundle(
                            "messages", japanese, noDefaultFallback);

            System.out.println(normal.getLocale().toLanguageTag());
            System.out.println(strict.getLocale().toLanguageTag());
        } finally {
            Locale.setDefault(original);
        }
    }
}
```

Chạy trong cùng thư mục có ba file `messages.properties`, `messages_en.properties`, `messages_vi.properties` của phần 4:

```bash
javac -encoding UTF-8 NoDefaultFallbackDemo.java
java -cp . NoDefaultFallbackDemo
```

Kết quả mong đợi:

```text
en
und
```

`getNoFallbackControl(FORMAT_PROPERTIES)` loại bỏ **bước thử default locale** trong cơ chế tìm kiếm bundle theo control đã cung cấp. Nó **không loại bỏ bundle gốc** khỏi danh sách candidate. Vì vậy khi không có `messages_ja`, nhưng có `messages.properties`, kết quả có thể là root.

Điều này **không** đồng nghĩa luôn có kết quả: nếu không có root cũng không có bundle tương ứng với target, `MissingResourceException` vẫn xảy ra.

**Giới hạn quan trọng:** các overload `getBundle` nhận `ResourceBundle.Control` không dùng được theo cách này khi code gọi chúng từ **named module**; JDK có thể ném `UnsupportedOperationException`. Khi dùng Java Platform Module System, hãy xem cơ chế `ResourceBundleProvider` và thiết kế chính sách lựa chọn ngôn ngữ ở tầng ứng dụng. Không áp nguyên ví dụ classpath sang named module mà không kiểm tra.

## 9. Fallback nghiệp vụ: chọn từ danh sách locale thực sự hỗ trợ

`ResourceBundle` giải quyết việc tìm bundle và key, nhưng **không tự biết** hệ thống muốn phục vụ những ngôn ngữ nào. Nếu backend có file `messages_fr.properties` phục vụ phần mềm nội bộ, không có nghĩa giao diện công khai đã hỗ trợ tiếng Pháp hoàn chỉnh.

Một chính sách sản phẩm có thể là:

1. Người dùng chọn một locale hoặc gửi `Accept-Language`.
2. Ứng dụng đối chiếu với tập locale **được công bố** và có tài nguyên đầy đủ.
3. Nếu không khớp, ứng dụng chọn fallback cố định, ví dụ `en-US`.
4. Chuyển locale đã chọn vào `ResourceBundle.getBundle`.
5. Kiểm tra kết quả tải được, các key bắt buộc và ngoại lệ theo hợp đồng sản phẩm.

Ví dụ, khi đã bảo đảm có tài nguyên cho `en-US` và `vi-VN`, một bộ chọn đơn giản cho lựa chọn **chính xác** có thể là:

```java
import java.util.Locale;
import java.util.Set;

public class ProductLocalePolicy {
    private static final Set<String> SUPPORTED =
            Set.of("en-US", "vi-VN");

    public static Locale select(Locale requested) {
        String tag = requested == null
                ? ""
                : requested.toLanguageTag();

        String chosen = SUPPORTED.contains(tag)
                ? tag
                : "en-US";

        return Locale.forLanguageTag(chosen);
    }

    public static void main(String[] args) {
        System.out.println(
                select(Locale.forLanguageTag("ja-JP")).toLanguageTag());
        System.out.println(
                select(Locale.forLanguageTag("vi-VN")).toLanguageTag());
    }
}
```

```bash
javac -encoding UTF-8 ProductLocalePolicy.java
java ProductLocalePolicy
```

Stdout:

```text
en-US
vi-VN
```

Đây là ví dụ về **chính sách exact-tag**, không phải thuật toán thương lượng ngôn ngữ tổng quát. Trong sản phẩm, có thể muốn `vi` khớp với `vi-VN` hoặc dùng `Locale.LanguageRange` và `Locale.lookup` để thương lượng từ nhiều ưu tiên. Bài toán lựa chọn này nên được giải quyết **trước** bước nạp bundle, thay vì dựa toàn bộ vào locale mặc định của JVM.

Lưu ý: ngay cả khi đã chọn locale được phép, `getBundle` vẫn có thể trả bundle cha như `messages_en` cho `en-US`. Đó có thể là hành vi mong muốn. Cần công bố rõ điều kiện nào được coi là “hỗ trợ” và điều kiện nào là “fallback”.

## 10. Không nên dùng `Locale.setDefault` để chọn ngôn ngữ từng request

`Locale.setDefault(Locale)` thay đổi locale mặc định ở phạm vi JVM. Hai request xử lý song song sẽ ảnh hưởng nhau nếu mỗi request gọi `setDefault`.

Ví dụ dễ gây lỗi:

```java
// Không dùng trong controller xử lý request:
Locale.setDefault(userLocale);
String message = ResourceBundle.getBundle("messages")
        .getString("screen.title");
```

Khi luồng A đang xử lý người dùng Việt Nam, luồng B có thể đổi default sang tiếng Anh trước khi luồng A lấy bundle. Kết quả không ổn định, và thư viện khác sử dụng `Locale.getDefault()` cũng bị ảnh hưởng.

Cách rõ ràng hơn:

```java
String message = ResourceBundle
        .getBundle("messages", userLocale)
        .getString("screen.title");
```

Tuy nhiên, truyền `userLocale` **chưa tự loại bỏ fallback sang JVM default** khi target thiếu bundle. Nếu sản phẩm yêu cầu fallback cố định, cần chọn locale hỗ trợ từ trước hoặc kiểm soát cách tìm bundle cho phù hợp. Thay default locale của JVM không phải chiến lược tốt để thực hiện fallback trên từng request.

Trong ứng dụng thực tế, locale mặc định có thể phục vụ các tiện ích khi không có ngữ cảnh người dùng, nhưng không nên được xem là nguồn chân lý cho mọi dữ liệu người dùng.

## 11. Root là nơi dự phòng dữ liệu, không phải ngôn ngữ mặc định của sản phẩm

Bundle gốc `messages.properties` không có hậu tố ngôn ngữ. Nhiều dự án dùng tiếng Anh làm nội dung root để dễ bảo trì, nhưng **đó là quyết định của dự án**, không phải quy định của `ResourceBundle`. Một dự án khác có thể dùng tiếng Việt trong root; Java vẫn chọn bundle đó theo cùng thuật toán.

Vì root có thể cung cấp key cho các bundle cha/con, nên nó thường giữ **tập key đầy đủ**, với giá trị có ý nghĩa. Ví dụ:

```properties
screen.title=Application
screen.help=See instructions.
error.unknown=An unexpected error occurred.
```

Nếu `messages_vi.properties` chưa có `error.unknown`, kết quả tiếng Anh từ root có thể xuất hiện trong UI tiếng Việt. Việc này giúp tránh exception nhưng cần được quản trị:

- Với các màn hình quan trọng, có thể yêu cầu 100% key đã dịch trước release.
- Với nội dung ít quan trọng, tạm fallback vào root có thể chấp nhận nếu UI nêu rõ chính sách ngôn ngữ.
- Với dữ liệu pháp lý hoặc an toàn, không nên tự động dùng bản dịch khác nếu có yêu cầu về độ chính xác và phê duyệt ngôn ngữ.
- Kiểm thử phải phân biệt **bundle được chọn** và **nguồn của từng key**; `getLocale()` chỉ cho biết bundle được chọn, không nói key đó đến từ parent nào.

Do đó, đừng đặt tên `messages.properties` là “English bundle” trong tài liệu nội bộ nếu mục tiêu là giải thích kỹ thuật. Chính xác hơn: đó là **root bundle**, có thể chứa nội dung tiếng Anh theo chính sách dự án.

## 12. Kiểm thử ma trận fallback

Với bộ dữ liệu `messages.properties`, `messages_en.properties`, `messages_vi.properties`, nên có test theo ma trận:

| Target | Default JVM | Kết quả kỳ vọng | Điều kiểm chứng |
| --- | --- | --- | --- |
| `ja-JP` | `en-US` | `getLocale() == en` | Có fallback qua default trước root |
| `ja-JP` | `de-DE` | `getLocale() == ROOT` | Default không khớp, dùng root |
| `vi-VN` | `en-US` | `getLocale() == vi` | Target khớp nên không cần fallback default |
| `Locale.ROOT` | `en-US` | `getLocale() == ROOT` | Root được yêu cầu và có sẵn |
| `vi-VN`, key `screen.help` | `en-US` | `Help from root` | Key tìm từ parent root, không từ bundle `en` |
| `ja-JP` + NoFallbackControl | `en-US` | ROOT | Bỏ qua bước fallback theo JVM default |

Thêm các ca âm:

- Xóa root và mọi bundle có thể khớp target/default: xác nhận `MissingResourceException` từ `getBundle`.
- Giữ bundle phù hợp nhưng xóa một key ở **mọi** parent: xác nhận `MissingResourceException` từ `getString`.
- Thêm `messages_ja.properties`: yêu cầu `ja-JP` giờ phải chọn `ja` ngay cả khi JVM default là tiếng Anh.
- Bổ sung key `screen.help` vào `messages_vi.properties`: giá trị ở `vi` phải ghi đè giá trị từ root.

Khi cần đổi default locale trong **bài test riêng biệt**, khôi phục nó bằng `finally`. Tránh chạy đồng thời nhiều test cùng thay `Locale.setDefault`, vì default là trạng thái dùng chung. Có thể cô lập các kịch bản vào tiến trình JVM khác nhau hoặc dùng cơ chế test bảo vệ trạng thái toàn cục.

## 13. Các hiểu lầm thường gặp

1. **“Truyền Locale vào getBundle thì không bao giờ dùng JVM default.”** Sai. Target chỉ là ưu tiên đầu; thuật toán mặc định có bước tìm thêm theo default nếu thiếu bản khớp.
2. **“Có messages.properties thì luôn lấy root ngay khi thiếu target.”** Sai. Root có thể bị tạm giữ, trong khi Java thử default locale.
3. **“Default locale là ngôn ngữ của người dùng hiện tại.”** Không đúng trong dịch vụ nhiều người dùng; đó là trạng thái JVM.
4. **“Root luôn là tiếng Anh.”** Không có quy định như vậy; nội dung root do dự án quyết định.
5. **“Nếu getBundle trả đối tượng thì requested locale được hỗ trợ.”** Không chắc; hãy kiểm tra `bundle.getLocale()` và danh sách hỗ trợ do sản phẩm công bố.
6. **“Thiếu key trong vi sẽ được tìm trong en vì JVM default là en.”** Không đúng khi `vi` đã được chọn; tra cứu key dựa vào parent chain, thường qua root.
7. **“NoFallbackControl loại bỏ root.”** Không; nó loại bỏ bước thử fallback locale, root vẫn có thể là candidate hợp lệ.
8. **“Cứ gọi Locale.setDefault là sửa được fallback cho mọi người.”** Dễ gây xung đột giữa các request, sai locale và ảnh hưởng thư viện khác.
9. **“getLocale() cho biết ngôn ngữ của từng chuỗi.”** Nó cho biết locale của bundle được chọn; key có thể đến từ parent.
10. **“Thiếu bundle và thiếu key là một lỗi giống nhau.”** Cùng có thể dẫn đến `MissingResourceException`, nhưng vị trí và cách khắc phục khác.

## 14. Quy trình lựa chọn đáng tin cậy

Khi xây dựng một ứng dụng có nhiều ngôn ngữ:

1. **Xác định nguồn target locale** của người dùng: lựa chọn trong tài khoản, tham số rõ ràng hoặc tiêu đề `Accept-Language`.
2. **Công bố tập ngôn ngữ hỗ trợ** và mức độ đầy đủ của từng bộ tài nguyên.
3. **Thiết kế fallback sản phẩm**: ngôn ngữ nào được ưu tiên khi không có bản khớp? Có cho phép trộn bản dịch từ root không?
4. **Định nghĩa root bundle**: giữ bộ key chung, nội dung mặc định có ý nghĩa, nguồn dịch được kiểm soát.
5. **Nạp bundle và quan sát kết quả**: dùng `getBundle`, `getLocale`, `getString` đúng ngữ cảnh.
6. **Kiểm thử cả cấp bundle lẫn cấp key**, trên JDK và packaging thực tế, bao gồm cache và classpath.
7. **Tránh trạng thái global theo request**: truyền `Locale` cụ thể, không thay JVM default trong xử lý đồng thời.

**Ghi nhớ:** Trong cơ chế `ResourceBundle` mặc định, *default locale* có thể tham gia **chọn bundle** khi target thiếu bản khớp; *root bundle* là tài nguyên cuối và thường là **parent của các bản dịch cụ thể**. Thiếu một bundle và thiếu một key dẫn tới hai đường tìm kiếm khác nhau. Hiểu hai đường này giúp bạn thiết kế fallback đúng ý định thay vì phụ thuộc cấu hình máy chủ.

## 15. Tài liệu tham khảo

- [Oracle JDK 21 — ResourceBundle và Search/Loading Strategy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Oracle JDK 21 — ResourceBundle.Control](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.Control.html)
- [Oracle JDK 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
