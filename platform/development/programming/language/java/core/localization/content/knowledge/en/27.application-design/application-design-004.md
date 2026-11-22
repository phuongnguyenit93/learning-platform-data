# Quản lý khóa, phiên bản tài nguyên và hợp đồng tham số trong Java Localization

Ứng dụng Java đa ngôn ngữ không thể vận hành ổn định chỉ bằng cách chuyển câu tiếng Anh sang `messages_vi.properties`. Trong một hệ thống đang phát triển, cùng một thông báo có thể được gọi bởi nhiều màn hình, bản dịch có thể thay đổi trong lúc ứng dụng cũ vẫn đang chạy, và tham số có thể đổi từ số lượng thành số tiền hoặc thêm một mã vận đơn. Những thay đổi tưởng chừng chỉ liên quan văn bản có thể làm hỏng mã gọi, hiển thị nhầm dữ liệu hoặc tạo lỗi khó phát hiện khi triển khai.

**Ba trụ cột thiết kế cần quản lý đồng thời:**

1. **Khóa tài nguyên (resource key):** tên định danh ổn định cho một *ý nghĩa*, không phải bản thân câu chữ.
2. **Phiên bản tài nguyên (catalog version):** bản snapshot những khóa, bản dịch và hợp đồng đang được ứng dụng sử dụng.
3. **Hợp đồng tham số (parameter contract):** định nghĩa mỗi biến chèn vào thông điệp có vị trí, kiểu, ý nghĩa, đơn vị, trạng thái bắt buộc và quy tắc format như thế nào.

Bài học nằm trong nhóm **Thiết kế ứng dụng** của module **Java core - localization**, dùng **Java 17+**, `ResourceBundle`, `MessageFormat` và file `.properties`. Các ví dụ có thể chạy độc lập khi tạo đúng các file đã chỉ định. Java hỗ trợ cơ chế tải resource và format thông điệp, nhưng **không tự xây hệ thống versioning, kiểm tra hợp đồng kiểu dữ liệu hoặc quy trình phê duyệt bản dịch**; những phần đó phải được thiết kế ở cấp ứng dụng.

## 1. Phân biệt message code, resource key và nội dung hiển thị

Giả sử backend phát hiện thanh toán thất bại. Ba giá trị dưới đây có trách nhiệm khác nhau:

| Tầng | Ví dụ | Mục đích |
| --- | --- | --- |
| Mã trạng thái nghiệp vụ | `PAYMENT_DECLINED` | Phục vụ API, phân loại lỗi, xử lý logic |
| Khóa tài nguyên | `checkout.payment.declined` | Tìm mẫu thông điệp trong catalog |
| Nội dung hiển thị | `Thanh toán không thành công.` | Hiển thị cho người dùng theo locale |

Không lưu bản dịch `Thanh toán không thành công.` như giá trị ổn định của cột `payment_status`, vì chỉ một lần sửa câu chữ là bản ghi đã lưu không còn đồng nhất với phiên bản mới. Hãy lưu mã nghiệp vụ hoặc trạng thái có kiểu, rồi render câu thông báo tại lớp hiển thị.

**Khóa là một hợp đồng gọi nội bộ.** Khi lập trình viên đổi tên một key mà không sửa các callsite, `ResourceBundle.getString(key)` có thể ném `MissingResourceException`. Khi người dịch thay `{0}` bằng `{1}`, code có thể vẫn chạy nhưng đưa dữ liệu sai vào câu. Cả hai là lỗi hợp đồng, không phải lỗi chính tả đơn thuần.

### Sơ đồ luồng dữ liệu

```text
Business event: ORDER_SUMMARY
  orderId = "A-7"
  itemCount = 3
      |
      v
Key: checkout.summary
Contract: {0}:String orderId, {1}:Number itemCount
      |
      v
ResourceBundle(locale) -> thông điệp/pattern
      |
      v
MessageFormat(pattern, locale) + typed arguments
      |
      v
Đơn A-7: 3 món (người dùng vi-VN)
```

## 2. Đặt semantic key đúng mục đích

Các khóa nên bộc lộ *ngữ cảnh và ý định*:

```properties
account.signIn.title=Sign in
account.signIn.submit=Continue
checkout.pay.cta=Pay now
checkout.summary=Order {0}: {1,number,integer} items
checkout.payment.declined=Payment declined.
profile.displayName.label=Display name
```

Quy tắc đề xuất:

- Dùng tên như `feature.screen.intent` hoặc `domain.event.variant`; chọn một convention duy nhất cho toàn dự án.
- Tách key theo **ngữ nghĩa**. Cùng từ “Open” trong tiếng Anh có thể là động từ mở file hoặc trạng thái đang mở; nhiều ngôn ngữ không dịch giống nhau.
- Có thể tái sử dụng khi thực sự là cùng thông điệp, cùng vai ngữ pháp và cùng hợp đồng tham số.
- Đặt key có chủ sở hữu: module/team chịu trách nhiệm khi sửa, xóa hoặc chuyển sang phiên bản mới.
- Không dùng nguyên văn tiếng Anh `Payment failed` làm key, vì text biên tập sẽ thay đổi.
- Không dùng `msg001` hoặc `error2` vì thiếu ngữ cảnh, khó tìm và dễ tái sử dụng sai.
- Không tạo key động từ chuỗi không tin cậy khi không có danh sách key được phép.
- Không đổi chữ hoa/thường của key tùy tiện: key lookup trong `ResourceBundle` có phân biệt case.
- Không dùng resource key làm khóa database cho những giá trị nghiệp vụ không liên quan hiển thị.

**Sửa câu chữ không đồng nghĩa đổi key:** bản dịch có thể sửa chính tả, dấu câu hoặc diễn đạt tự nhiên hơn mà vẫn giữ contract. **Đổi nghĩa/kiểu tham số là một thay đổi lớn hơn** và có thể đòi một key khác trong giai đoạn di trú.

## 3. Định nghĩa catalog gốc và bản dịch theo locale

Tạo đúng cấu trúc sau cho ví dụ trên classpath:

```text
example/
  messages.properties
  messages_vi.properties
  BundleLookupDemo.java
```

**`messages.properties`**:

```properties
welcome=Hello, {0}!
checkout.summary=Order {0}: {1,number,integer} items
checkout.failed=Payment failed.
checkout.pay.cta=Pay now
```

**`messages_vi.properties`**:

```properties
welcome=Xin chào, {0}!
checkout.summary=Đơn {0}: {1,number,integer} món
checkout.pay.cta=Thanh toán
```

Tên bundle cơ sở ở ví dụ là `messages`. Với `vi-VN`, hệ thống có thể thử `messages_vi_VN.properties`, `messages_vi.properties` rồi `messages.properties` theo danh sách ứng viên. File root là fallback cuối trong chuỗi parent thích hợp.

**Lưu ý encoding Java 17:** từ Java 9, `PropertyResourceBundle` mặc định cố đọc file properties theo UTF-8, có fallback ISO-8859-1 khi gặp byte UTF-8 lỗi (nếu không ép encoding bằng system property phù hợp). Vì vậy file tiếng Việt UTF-8 phù hợp với cấu hình Java 17 phổ biến. Không nhầm API này với `Properties.load(InputStream)` vốn có quy tắc ISO-8859-1 truyền thống. Build và CI nên thống nhất UTF-8, kiểm tra nội dung đúng và tránh các file trộn encoding.

**`checkout.failed` cố ý thiếu trong file vi** để minh họa fallback ở ví dụ tiếp theo, không phải tiêu chuẩn chất lượng cho sản phẩm đã phát hành.

## 4. Ví dụ Java 17: lookup và format từ ResourceBundle

Lưu **`BundleLookupDemo.java`** cạnh hai file properties:

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleLookupDemo {
    private static ResourceBundle catalog(Locale locale) {
        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);
        return ResourceBundle.getBundle("messages", locale, control);
    }

    private static String render(
            ResourceBundle bundle, Locale locale,
            String key, Object... args) {
        return new MessageFormat(
                bundle.getString(key), locale).format(args);
    }

    public static void main(String[] args) {
        Locale vi = Locale.forLanguageTag("vi-VN");
        ResourceBundle bundle = catalog(vi);

        System.out.println(render(bundle, vi, "welcome", "Lan"));
        System.out.println(render(
                bundle, vi, "checkout.summary", "A-7", 3));
        System.out.println(bundle.getString("checkout.failed"));

        ResourceBundle root = catalog(Locale.ROOT);
        System.out.println(render(
                root, Locale.ROOT, "welcome", "Lan"));
    }
}
```

```bash
javac -encoding UTF-8 BundleLookupDemo.java
java BundleLookupDemo
```

Stdout (console hỗ trợ UTF-8):

```text
Xin chào, Lan!
Đơn A-7: 3 món
Payment failed.
Hello, Lan!
```

**Cơ chế:**

- `ResourceBundle` tìm pattern có key phù hợp; việc gọi `getString` **không tự thay thế** `{0}` hay `{1}`.
- `MessageFormat` nhận pattern và `Locale` để format các tham số theo locale đó.
- `getNoFallbackControl(FORMAT_PROPERTIES)` loại bỏ **fallback sang default locale của JVM** nhưng **không loại chuỗi parent/root resource**; vì vậy key `checkout.failed` lấy từ root.
- `{0}` là mã đơn; `{1,number,integer}` định dạng số lượng nguyên trong câu.
- Không phụ thuộc `Locale.getDefault()` của máy chủ khi render cho từng user.

**Giới hạn JPMS:** overload `ResourceBundle.getBundle` có `ResourceBundle.Control` không hỗ trợ trong các **named modules** của Java 17 và có thể ném `UnsupportedOperationException`. Ví dụ trên chủ ý chạy qua **classpath/unnamed module**. Với ứng dụng named modules, dùng cơ chế provider/bundle lookup phù hợp JPMS, không copy ví dụ mà bỏ qua giới hạn.

## 5. Fallback không đồng nghĩa bản dịch đầy đủ

Trong ví dụ, `bundle.containsKey("checkout.failed")` có thể là `true` vì thấy key được **thừa kế từ root**, dù `messages_vi.properties` không chứa key đó. Vì vậy:

- **Runtime fallback** có thể giúp không hiển thị chỗ trống cho user.
- **Translation coverage** phải kiểm tra **từng file ngôn ngữ** hoặc thông tin metadata của công cụ dịch, không chỉ nhìn kết quả `containsKey`.
- **Localization acceptance** có thể yêu cầu mọi thông điệp pháp lý, thanh toán và an toàn có bản dịch đã phê duyệt; không chỉ tự động fallback sang tiếng Anh.
- **Observability** nên ghi key, locale yêu cầu, catalog version và mức độ fallback, tránh đưa dữ liệu cá nhân trong argument vào log.

Hai khái niệm khác nhau trong `ResourceBundle.Control`:

1. **Candidate/parent chain** như `vi-VN -> vi -> root`.
2. **Fallback sang default locale** khi không có bundle phù hợp, được điều khiển bởi `getFallbackLocale`. `getNoFallbackControl` có thể tắt trường hợp thứ hai.

### Lỗi thiếu key

Một key hoàn toàn không tồn tại trong cả chuỗi parent sẽ khiến `getString` ném `MissingResourceException`. Không mong đợi Java trả `null` hoặc tự trả tên key.

**`MissingKeyDemo.java`**, dùng cùng hai file properties:

```java
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;

public class MissingKeyDemo {
    public static void main(String[] args) {
        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);
        ResourceBundle vi = ResourceBundle.getBundle(
                "messages", Locale.forLanguageTag("vi-VN"), control);

        System.out.println("Inherited key: "
                + vi.containsKey("checkout.failed"));
        System.out.println("Unknown key: "
                + vi.containsKey("checkout.unknown"));

        try {
            vi.getString("checkout.unknown");
            System.out.println("Unexpected success");
        } catch (MissingResourceException ex) {
            System.out.println("Missing key detected");
        }
    }
}
```

```bash
javac -encoding UTF-8 MissingKeyDemo.java
java MissingKeyDemo
```

Stdout:

```text
Inherited key: true
Unknown key: false
Missing key detected
```

Khi thiết kế lỗi runtime, hãy quyết định loại key nào được phép fallback, loại nào cần chặn release, và phản ứng nào khi một bản dịch vẫn thiếu. Không dùng `catch(Exception)` rồi trả `"?"` cho tất cả các lỗi: điều đó che giấu lỗi dữ liệu nghiêm trọng.

## 6. Hợp đồng tham số là một phần của API message

Một message có placeholder là **một API nhỏ**. Với `checkout.summary`, nên ghi schema rõ:

| Vị trí | Tên nghiệp vụ | Kiểu Java | Ý nghĩa | Ràng buộc |
| --- | --- | --- | --- | --- |
| `{0}` | `orderId` | `String` | Mã đơn hiển thị | Bắt buộc; không tự dịch |
| `{1}` | `itemCount` | `Number`/`Integer` | Số mặt hàng | Số nguyên không âm |
| Format style | `{1,number,integer}` | Number formatter | Trình bày số đếm | Locale do người xem quyết định |

Cần xác định **tên, vị trí, type, nullability, ý nghĩa, đơn vị, cách định dạng, tính nhạy cảm** và tình huống cần plural/gender. Chỉ ghi “hai tham số” là chưa đủ nếu một tham số là tiền tệ, một tham số là tỉ lệ hay ngày lịch.

**Tham số theo vị trí:** `MessageFormat` chuẩn Java 17 dùng index `0`, `1`, ...; không trực tiếp hiểu named placeholder `{orderId}`. Ứng dụng có thể xây typed facade cho caller, nhưng tên đối số của hàm Java không được Java MessageFormat tự ánh xạ vào bản dịch.

**Đảo vị trí được, đổi vai trò không được:** người dịch có thể đặt `{1}` trước `{0}` cho tự nhiên. Nhưng người dịch không được tự gán `{0}` thành số lượng nếu contract quy định đó là mã đơn.

## 7. Ví dụ: đổi thứ tự tham số giữa ngôn ngữ

File **`ArgumentOrderDemo.java`**:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class ArgumentOrderDemo {
    public static void main(String[] args) {
        Object[] values = {"A-7", 3};

        String en = "Order {0}: {1,number,integer} items";
        String vi = "Có {1,number,integer} món trong đơn {0}";

        System.out.println("EN: "
                + new MessageFormat(en, Locale.US).format(values));
        System.out.println("VI: "
                + new MessageFormat(
                        vi, Locale.forLanguageTag("vi-VN"))
                        .format(values));
    }
}
```

```bash
javac -encoding UTF-8 ArgumentOrderDemo.java
java ArgumentOrderDemo
```

Stdout:

```text
EN: Order A-7: 3 items
VI: Có 3 món trong đơn A-7
```

Cùng `values`, cùng index và ý nghĩa, nhưng trình tự xuất hiện có thể khác. Đây là ví dụ **số lượng 3**; pattern tiếng Anh `items` chưa xử lý đủ số ít/nhiều cho tất cả trường hợp. Trong sản phẩm thật, cần thiết kế pluralization phù hợp cho locale.

## 8. Kiểu tham số và những trường hợp MessageFormat không tự bảo vệ

Các subformats chính trong Java 17:

| Placeholder | Kiểu mong đợi / hiệu quả |
| --- | --- |
| `{0}` | Chèn Object; với String thì dùng nội dung string |
| `{1,number}` | Cần Number tương thích với NumberFormat |
| `{1,number,integer}` | Number định dạng theo số nguyên cho trình bày |
| `{1,number,currency}` | Number với currency subformat gắn locale |
| `{1,number,percent}` | Number với percent subformat |
| `{2,date,short}` | Thường cần `java.util.Date`/kiểu mà date subformat hỗ trợ |
| `{2,time,short}` | Date/time theo locale |
| `{0,choice,...}` | ChoiceFormat kiểu legacy, thường dựa trên Number |

**Java Time khác java.util.Date:** `LocalDate`, `Instant` và `ZonedDateTime` không mặc nhiên là kiểu đầu vào cho các subformat date cũ của `MessageFormat`. Chọn kiểu dữ liệu theo nghiệp vụ, rồi chuyển/format qua `DateTimeFormatter` hoặc adapter có kiểm soát, có `ZoneId` khi cần.

**Currency:** `{1,number,currency}` có thể chọn đơn vị tiền theo locale, trong khi giao dịch thực tế dùng mã tiền khác. Contract của giao dịch phải chứa amount và currencyCode nghiệp vụ; đừng coi locale người xem là đơn vị tiền thanh toán.

**Thiếu tham số không nhất thiết là exception:** `MessageFormat` có thể giữ literal `{1}` nếu caller không cung cấp index đó. Vì vậy chỉ test “không ném lỗi” là không đủ.

### ParameterTypeDemo.java

```java
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.util.Locale;

public class ParameterTypeDemo {
    public static void main(String[] args) {
        MessageFormat f = new MessageFormat(
                "Order {0}: {1,number,integer} items",
                Locale.US);

        System.out.println("Argument slots: "
                + f.getFormatsByArgumentIndex().length);
        System.out.println("Arg 1 numeric: "
                + (f.getFormatsByArgumentIndex()[1]
                        instanceof NumberFormat));
        System.out.println("Correct: "
                + f.format(new Object[]{"A-7", 3}));

        try {
            f.format(new Object[]{"A-7", "3"});
            System.out.println("Wrong type accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("Wrong type rejected");
        }

        System.out.println("Missing: "
                + f.format(new Object[]{"A-7"}));
    }
}
```

```bash
javac -encoding UTF-8 ParameterTypeDemo.java
java ParameterTypeDemo
```

Stdout:

```text
Argument slots: 2
Arg 1 numeric: true
Correct: Order A-7: 3 items
Wrong type rejected
Missing: Order A-7: {1} items
```

**Cảnh báo về validator:** `getFormatsByArgumentIndex` giúp kiểm tra subformat có/không ở một index, nhưng các vị trí không dùng có thể cho `null` và mảng có thể có độ dài theo index lớn nhất. Không dùng **độ dài mảng đơn lẻ** để chứng minh mọi tham số được dùng, đúng kiểu và đúng ngữ nghĩa. Muốn có hợp đồng mạnh, cần schema/linter cùng các test render.

## 9. Dấu nháy đơn và dấu ngoặc là cú pháp, không chỉ là văn bản

`MessageFormat` dùng dấu nháy đơn để quote literal. Để xuất một dấu `'` thật, pattern thường cần **hai dấu `''`**. Dịch giả có thể vô tình làm một placeholder không còn được thay khi viết dấu nháy đơn sai.

File **`ApostrophePatternDemo.java`**:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class ApostrophePatternDemo {
    public static void main(String[] args) {
        MessageFormat first = new MessageFormat(
                "It''s time for {0}.", Locale.US);
        MessageFormat second = new MessageFormat(
                "Click ''Save'' to {0}.", Locale.US);

        System.out.println(first.format(
                new Object[]{"Lan"}));
        System.out.println(second.format(
                new Object[]{"continue"}));
    }
}
```

```bash
javac -encoding UTF-8 ApostrophePatternDemo.java
java ApostrophePatternDemo
```

Stdout:

```text
It's time for Lan.
Click 'Save' to continue.
```

Cú pháp của file `.properties` và của `MessageFormat` là **hai tầng khác nhau**: Java đọc escape của properties trước, sau đó MessageFormat phân tích `{index}`, kiểu format và quote. Một file properties hợp lệ vẫn có thể chứa **MessageFormat pattern sai**, hoặc pattern vẫn parse được nhưng không còn placeholder như mong muốn.

**Không parse MessageFormat phức tạp bằng regex sơ sài**. ChoiceFormat có thể chứa các pattern lồng nhau, còn dấu `'` làm thay đổi ý nghĩa của ngoặc. Validator thực tế cần parser phù hợp và metadata của message; `new MessageFormat(pattern, locale)` chỉ là bước kiểm tra cú pháp, chưa đủ biết `{1}` phải là `itemCount`.

## 10. Plural, gender và ngữ cảnh văn bản phải được mô hình hóa

Đừng ghép câu tiếng Anh bằng `count + " item" + (count == 1 ? "" : "s")` rồi cho rằng có thể bản địa hóa mọi ngôn ngữ. Nhiều ngôn ngữ có quy tắc số ít/nhiều khác nhau; còn giống ngữ pháp, kính ngữ hay vai trò từ cũng có thể cần biến thể.

`ChoiceFormat` trong Java có thể hỗ trợ một vài nhánh dựa trên số nhưng **không tự cung cấp bộ quy tắc plural CLDR đầy đủ**. Với yêu cầu đa ngôn ngữ phong phú, cân nhắc một hệ thống thông điệp có plural/select phù hợp (ví dụ ICU MessageFormat) và kiểm thử thực tế theo từng locale.

Cần cho translator biết **ngữ cảnh câu** và đặc tính tham số. Nếu thông báo có số lượng, có thể cần tách message thành các biến thể hoặc dùng công cụ plural hóa. Nếu thông báo có tên người, không được tự ý viết tên theo cách áp đặt giống ngữ pháp. Cùng một key có chuỗi giống nhau ở tiếng Anh chưa chắc có thể dùng ở mọi ngôn ngữ.

## 11. Version resource: bản nào chứa những gì?

Có nhiều lớp phiên bản:

| Loại version | Chức năng |
| --- | --- |
| Application version | Mã Java/API callsite và UI |
| Catalog version | Snapshot keys, patterns, translations |
| Contract version | Semantics và schema tham số cho key |
| API version | Dạng message code/data được client nhận |
| JDK/CLDR version | Dữ liệu locale dùng định dạng ngày, số, currency |
| Translation tooling version | Parser/linter, kiểm soát thay đổi bản dịch |

Một ví dụ: build `2026.10.28` phát hành với `catalogVersion=3`, trong đó `checkout.summary` ở contract 1. Sau đó UI cần thêm `deliveryDate`, tức contract mới không còn tương thích với caller cũ. Không nên thay trực tiếp pattern hiện có để mọi client cũ bỗng cần `{2}`.

**Snapshot bất biến:** lý tưởng mỗi bản build dùng một catalog đã validate và biết được version hoặc hash của nó. Khi bug report nói “sai bản dịch”, cần biết **app version, catalog version, requested locale, key** để tái hiện. Với translation service động, chỉ thay catalog atomically sau khi đã kiểm tra đầy đủ, không cập nhật từng key khiến hệ thống ở trạng thái nửa v1/nửa v2.

### Khi nào đổi key?

- **Giữ key** nếu sửa typo, dấu câu, diễn đạt tự nhiên hơn nhưng ý nghĩa và tham số không đổi.
- **Có thể giữ key** khi bản dịch đảo vị trí `{0}`/`{1}` mà hợp đồng vẫn giữ nguyên.
- **Đổi key hoặc contract version** khi một tham số bắt buộc được thêm, bị bỏ, đổi kiểu hay đổi ý nghĩa.
- **Đổi semantic key** khi thông báo không còn nói về cùng hành động/trạng thái.
- **Không tăng hậu tố v2 ở mọi chỉnh sửa văn bản** vì làm phình catalog không cần thiết.

## 12. Ví dụ hai contract cùng tồn tại trong rolling deployment

Giả sử câu v1 chỉ cần mã đơn; câu v2 cần cả mã tracking bắt buộc. Trong giai đoạn hệ thống và client chưa nâng cấp đồng bộ, giữ cả hai mẫu:

```properties
purchase.confirmed.v1=Confirmed order {0}.
purchase.confirmed.v2=Confirmed order {0} with tracking {1}.
```

**VersionedMessageDemo.java**:

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.Map;

public class VersionedMessageDemo {
    public static void main(String[] args) {
        Map<String, String> patterns = Map.of(
                "purchase.confirmed.v1",
                "Confirmed order {0}.",
                "purchase.confirmed.v2",
                "Confirmed order {0} with tracking {1}.");

        String old = new MessageFormat(
                patterns.get("purchase.confirmed.v1"),
                Locale.US).format(new Object[]{"A-7"});

        String newer = new MessageFormat(
                patterns.get("purchase.confirmed.v2"),
                Locale.US).format(new Object[]{"A-7", "T-9"});

        System.out.println("V1: " + old);
        System.out.println("V2: " + newer);
    }
}
```

```bash
javac -encoding UTF-8 VersionedMessageDemo.java
java VersionedMessageDemo
```

Stdout:

```text
V1: Confirmed order A-7.
V2: Confirmed order A-7 with tracking T-9.
```

Hậu tố `v1/v2` ở đây diễn tả **hai hợp đồng không tương thích đang tồn tại đồng thời**, không phải quy tắc mọi key đều phải có version suffix. Dùng v2 cho caller mới; giữ v1 khi client cũ vẫn được hỗ trợ, rồi dọn sau khi quan sát không còn phụ thuộc.

## 13. Rollout: thêm trước, chuyển dần, xóa sau

Một chiến lược an toàn:

1. Xác định schema, kiểu và semantics của contract mới; nêu rõ catalog version tối thiểu mà caller mới yêu cầu.
2. Thêm key/pattern mới vào **catalog gốc và các locale bắt buộc**, review ngữ pháp và tham số.
3. Chạy CI lint và preview ở các locale trước khi phát hành.
4. Deploy resource mới **trước hoặc đồng thời với caller mới** theo cơ chế atomic/compatible của sản phẩm.
5. Giữ key cũ đủ lâu cho mobile offline, background jobs, notification queues và các phiên bản được hỗ trợ.
6. Theo dõi tần suất key cũ được dùng và missing/failed render theo version/locale.
7. Khi đã hết compatibility window, loại bỏ key cũ cùng code phụ thuộc và lập kế hoạch rollback.

Khi gửi lỗi qua API, nên gửi **mã trạng thái và dữ liệu có kiểu** thay vì chỉ gửi thông báo đã bản địa hóa. Client có thể dùng catalog phù hợp với locale và phiên bản của nó. Nếu server trả luôn localizedMessage, phải quy định ai sở hữu việc dịch và xử lý khi người dùng đổi ngôn ngữ sau đó.

### Caching và vòng đời của ResourceBundle

`ResourceBundle` được **cache** theo cơ chế lookup; khi sửa file ngoài runtime, không mặc nhiên JVM đang chạy lập tức đọc lại. `ResourceBundle.Control.getTimeToLive`, `needsReload` và `ResourceBundle.clearCache` có những vai trò cụ thể, nhưng **clear cache không bảo đảm artifact/deployment đã có file mới**. Không đổi `System.setProperty` hoặc sửa file properties giữa các request rồi kỳ vọng tất cả client có catalog nhất quán. Với named modules, kiểm tra lại cơ chế control/provider của môi trường thật.

`MessageFormat` là một đối tượng **mutable**, nên không chia sẻ instance có thể bị `applyPattern`/`setFormat` bởi nhiều request mà không có cơ chế đồng bộ. Tạo formatter riêng cho mỗi lần render hoặc clone/copy có kiểm soát.

## 14. Kiểm tra file nào thật sự thiếu bản dịch

`ResourceBundle.containsKey` có thể thấy key inherited; muốn đo coverage **của chính file vi**, hãy đọc hai file và so tập khóa trực tiếp ở CI.

**BundleCoverageDemo.java** (dùng file properties của mục 3):

```java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;
import java.util.Set;
import java.util.TreeSet;

public class BundleCoverageDemo {
    private static Properties read(String name) throws Exception {
        Properties properties = new Properties();
        try (Reader input = Files.newBufferedReader(
                Path.of(name), StandardCharsets.UTF_8)) {
            properties.load(input);
        }
        return properties;
    }

    public static void main(String[] args) throws Exception {
        Properties root = read("messages.properties");
        Properties vi = read("messages_vi.properties");

        Set<String> missing = new TreeSet<>(
                root.stringPropertyNames());
        missing.removeAll(vi.stringPropertyNames());

        Set<String> unexpected = new TreeSet<>(
                vi.stringPropertyNames());
        unexpected.removeAll(root.stringPropertyNames());

        System.out.println("Missing vi: " + missing);
        System.out.println("Unexpected vi: " + unexpected);
    }
}
```

```bash
javac -encoding UTF-8 BundleCoverageDemo.java
java BundleCoverageDemo
```

Stdout:

```text
Missing vi: [checkout.failed]
Unexpected vi: []
```

Kết quả này đúng với hai file ví dụ: file vi thiếu `checkout.failed`. Trong dự án thật, một số fallback được cho phép, một số bản dịch bắt buộc sẽ làm build fail. Chương trình trên **chỉ so key**: chưa kiểm tra nội dung được dịch đúng, có duplicate keys hay không, tham số và kiểu có đồng nhất không.

**Chú ý:** `Properties.load(Reader)` nhận ký tự mà `Reader` đã decode; dùng `Files.newBufferedReader(..., UTF_8)` ở ví dụ để không phụ thuộc encoding ngầm. `Properties` có thể ghi đè duplicate key mà không cảnh báo, nên muốn phát hiện trùng key trong file gốc cần linter riêng.

## 15. Lint pattern và hợp đồng kiểu dữ liệu

Một bản catalog có thể kèm metadata:

```yaml
key: checkout.summary
description: Tóm tắt số mặt hàng của một đơn mua
contractVersion: 1
arguments:
  - index: 0
    name: orderId
    type: string
    required: true
  - index: 1
    name: itemCount
    type: integer-number
    required: true
localesRequired: [en, vi]
```

Đây là **ví dụ schema do ứng dụng tự quy định**, không phải định dạng YAML mà `ResourceBundle` hay `MessageFormat` tự hiểu.

Một bộ CI đáng tin cần:

- Kiểm tra key bắt buộc hiện diện ở catalog gốc và locale có yêu cầu đầy đủ.
- Kiểm tra key trùng, không còn callsite, và chuỗi có kiểu dữ liệu không hợp lệ.
- Parse `MessageFormat` pattern cho từng locale và phát hiện dấu quote/ngoặc sai.
- Xác minh placeholder **required** thật sự được sử dụng, không có index lạ, format style đúng cho mỗi index.
- Kiểm thử input `0`, `1`, `3`, số lớn, ngày, tên có dấu nháy đơn, Unicode và ngôn ngữ RTL khi liên quan.
- Kiểm tra bản dịch dài gây tràn UI, thông báo sai ngữ cảnh và yêu cầu plural/gender.
- Không log payload nhạy cảm; log key + locale + version khi cần debug.
- Dùng cùng bộ dữ liệu/resource version thực sự được đóng gói trong ứng dụng.
- Kiểm thử fallback, reload/cache, và kịch bản client cũ gọi key v1.

**Giới hạn:** `new MessageFormat(pattern, locale)` kiểm tra cú pháp có ích, nhưng không biết `{0}` có nghĩa là `orderId` hay `username`. Regex `\\{(\\d+)\\}` không hiểu đủ subformat có quote/nested patterns. Vì vậy CI phải dựa vào schema và parser/validator phù hợp, không chỉ tìm chuỗi bằng regex.

## 16. Một typed facade giảm lỗi tại callsite

Caller Java thường chỉ thấy `render(String key, Object... args)`, khiến thứ tự và kiểu tham số dễ bị nhầm. Một wrapper theo nghiệp vụ có thể làm hợp đồng rõ hơn:

```java
// Fragment trong class đã có render(key, Object... args).
public String checkoutSummary(String orderId, int itemCount) {
    if (itemCount < 0) {
        throw new IllegalArgumentException(
                "itemCount must not be negative");
    }
    return render("checkout.summary", orderId, itemCount);
}
```

Đây là **fragment**, không phải chương trình độc lập. Nó giúp compiler kiểm tra `String` và `int` tại callsite, có tên nghiệp vụ và validation rõ. Nhưng **chưa bảo đảm translator giữ đúng placeholder**: một bản dịch có thể bỏ `{1}` mà không có lỗi biên dịch. Vì vậy kiểm thử typed facade và kiểm tra catalog phải được làm song song.

Một tổ chức lớn có thể tạo code generation từ message schema để tự sinh methods typed, nhưng **Java Core không tự sinh hợp đồng từ properties**. Hãy coi đây là kiến trúc bổ sung, không mô tả nó như API built-in của `ResourceBundle`.

## 17. Phân biệt MessageFormat với escaping HTML và bảo mật

Các argument là **dữ liệu** dùng để format; `MessageFormat` **không phải bộ lọc XSS, HTML escaping hoặc SQL escaping**. Ví dụ tên người chứa `<script>` nếu được đưa thẳng vào HTML không escape ở output sink có thể gây lỗ hổng. Hãy dùng HTML templating/output encoding đúng ngữ cảnh, và chuẩn bị message từ các key/pattern **đáng tin**.

Không ghép trực tiếp input người dùng vào **pattern** rồi parse bằng `new MessageFormat(...)` vì ký tự `'`, `{`/`}` có thể làm đổi cú pháp template. Thay vào đó, dùng pattern từ catalog đã kiểm duyệt và đưa dữ liệu user vào argument.

Với email, notification và mã lỗi máy đọc, tách **ngữ nghĩa sự kiện** khỏi câu chữ. Nếu payload API có `"code": "PAYMENT_DECLINED"` và data typed, phía trình bày có thể render tùy ngôn ngữ mà không thay đổi code.

## 18. Quy trình của developer, translator và reviewer

Một workflow gọn nhưng đầy đủ:

1. Developer khai báo **semantic key**, owner, mô tả ngữ cảnh và tham số dự kiến.
2. Contract reviewer xác nhận type, nullability, units, plural, gender, locale/timezone và phiên bản hợp đồng.
3. Translator nhận pattern + ngữ cảnh; được phép đổi thứ tự placeholder, không được đổi index/kiểu.
4. Tooling kiểm tra UTF-8, `.properties`, MessageFormat pattern, missing keys, coverage, duplicate keys, placeholder contract.
5. Reviewer nhìn câu trong UI thực, kiểm tra layout và cách diễn đạt khi số lượng/ngữ cảnh khác nhau.
6. CI test toàn bộ locale bắt buộc và các kịch bản v1/v2, fallback.
7. Build gắn catalog snapshot/version với binary hoặc tài nguyên cập nhật atomically.
8. Deployment giữ tương thích giữa web/mobile/backend/batch trong giai đoạn chuyển đổi.
9. Monitoring có missing-key/fallback metrics theo key, locale, catalogVersion mà không log secret.
10. Chỉ dọn key cũ khi không còn client hợp lệ sử dụng và có kế hoạch rollback.

Nếu người dịch chỉ biết chuỗi `"Order {0}: {1} items"`, họ có thể hiểu sai tham số. Một mô tả tốt hơn là: `{0} là mã đơn hàng, không dịch; {1} là số món trong đơn, số nguyên không âm; xuất hiện ở màn hình giỏ hàng`.

## 19. Lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng câu tiếng Anh làm key | Đổi câu làm hỏng lookup | Dùng semantic key |
| Tái dùng key cho nghĩa khác | Sai bản dịch/ngữ cảnh | Tách key theo intent |
| Đổi tên key mà không cập nhật caller | `MissingResourceException` | Typed facade, static scan, test |
| Tin `containsKey` = đã dịch | Root fallback che thiếu locale | So file locale trực tiếp |
| Đổi `{0}` và `{1}` do hiểu nhầm | Sai dữ liệu trong UI | Schema/index QA |
| Caller truyền `"3"` cho `number` | Runtime error | Number typed args |
| Thiếu argument nhưng không lỗi | In `{1}` ra UI | Required-args validation |
| Không escape dấu nháy đơn trong pattern | Placeholder có thể không format | Test `MessageFormat` |
| Giả định MessageFormat có plural CLDR đầy đủ | Sai văn phạm | Công cụ plural phù hợp |
| Thêm tham số bắt buộc trực tiếp vào key cũ | Client cũ không tương thích | Version contract/song song keys |
| Xóa key ngay khi backend deploy | Mobile/job cũ vẫn dùng | Theo dõi compatibility |
| Không gắn catalog version vào build | Khó tái hiện bug | Snapshot/version/hash |
| Dùng default Locale của server | Hiển thị sai ngôn ngữ user | Truyền Locale tường minh |
| Coi `getNoFallbackControl` chặn root | Hiểu sai candidate chain | Phân biệt default fallback và parent |
| Dùng Control trong named module | `UnsupportedOperationException` | Thiết kế JPMS đúng |
| Sửa file nhưng quên bundle caching | Runtime vẫn dùng text cũ | Cache/version lifecycle |
| Chia sẻ mutable MessageFormat giữa thread | Race/mất nhất quán | Instance per render |
| Dùng MessageFormat như HTML escaping | XSS ở output sink | Escape theo ngữ cảnh |
| Chỉ test bản dịch tiếng Anh | Lỗi quote/locale khác bị bỏ qua | QA tất cả locale bắt buộc |

## 20. Bài tập thực hành

**Bài 1 — Khóa có nghĩa:** thiết kế semantic keys cho màn hình đăng nhập, lỗi tài khoản, giỏ hàng, thanh toán. Giải thích trường hợp nào cùng câu tiếng Anh vẫn cần hai key.

**Bài 2 — Tham số:** tạo schema cho `checkout.summary` với orderId/string và itemCount/number. Dịch sang hai ngôn ngữ với thứ tự tham số khác nhau, xác minh output từ `ArgumentOrderDemo`.

**Bài 3 — Fallback:** chạy `BundleLookupDemo` và `MissingKeyDemo`. Quan sát key `checkout.failed` lấy từ root, key `checkout.unknown` gây lỗi. Nêu lý do UI cần theo dõi missing translation dù fallback đã hoạt động.

**Bài 4 — Kiểm tra coverage:** chạy `BundleCoverageDemo`, thêm bản dịch `checkout.failed` vào file vi và kiểm tra tập missing trở thành `[]`.

**Bài 5 — Bẫy syntax:** chạy `ApostrophePatternDemo`; thay `It''s` thành `It's` và quan sát hành vi. Thiết kế linter bắt các chuỗi quote sai.

**Bài 6 — Sai kiểu/thiếu đối số:** dùng `ParameterTypeDemo`, thay `Integer 3` bằng `String "3"` và thử bỏ tham số. Vì sao chỉ bắt exception chưa đủ để xác nhận template đúng?

**Bài 7 — Vòng đời version:** catalog v1 có `purchase.confirmed.v1`, v2 có thêm tracking. Lập kế hoạch triển khai cho mobile offline và backend, điều kiện xóa v1, test rollback.

**Bài 8 — Security:** thử tên người chứa HTML markup và dấu nháy đơn. Phân biệt pattern parsing, argument formatting, HTML escaping và logging dữ liệu nhạy cảm.

## 21. Tài liệu tham khảo

- [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html): lookup, fallback, keySet/containsKey, caching.
- [Java SE 17 — ResourceBundle.Control](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html): `getNoFallbackControl`, candidate locales, TTL và named module limitation.
- [Java SE 17 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html): UTF-8 và fallback ISO-8859-1.
- [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html): placeholder, number/date subformats, quote, missing argument và `getFormatsByArgumentIndex`.
- [Java SE 17 — MissingResourceException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/MissingResourceException.html): missing bundle/key.
- [Unicode CLDR](https://cldr.unicode.org/): dữ liệu ngôn ngữ và quy tắc plural để định hướng yêu cầu bản địa hóa nâng cao.

## 22. Ghi nhớ

**Resource key là hợp đồng ngữ nghĩa; message catalog là một artifact có phiên bản; placeholder là một API có kiểu và ý nghĩa.** Đặt khóa theo chức năng thay vì câu chữ, giữ khi chỉ sửa bản dịch và tạo contract mới khi thay đổi không tương thích. Dùng `ResourceBundle` để chọn nội dung theo locale, `MessageFormat` để thay tham số, nhưng phải tự thiết kế versioning, typed schema, coverage và CI.

Một release an toàn **thêm key mới trước, cho nhiều phiên bản cùng tồn tại, giám sát, rồi mới xóa key cũ**. Kiểm tra cả file locale thực tế lẫn fallback; không hiểu `containsKey` là bản dịch đã hoàn thiện. Luôn xác minh người dịch không thay sai index, kiểu, quote, plural và ngữ nghĩa của argument. Hệ thống đáng tin cậy phải giữ **dữ liệu nghiệp vụ và mã lỗi độc lập với câu hiển thị**, để thay đổi ngôn ngữ không làm thay đổi logic.