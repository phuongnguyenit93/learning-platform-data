# Phân biệt chọn locale ứng dụng với cơ chế dự phòng ResourceBundle

## 1. Hai quyết định khác nhau thường bị nhầm là một

Một ứng dụng Java hỗ trợ nhiều ngôn ngữ thường phải trả lời **hai câu hỏi** trước khi hiển thị một thông điệp:

1. **Ứng dụng chọn locale nào cho người dùng/yêu cầu hiện tại?** Ví dụ, dựa vào ngôn ngữ người dùng đã lưu, header `Accept-Language`, các locale sản phẩm thực sự hỗ trợ và locale mặc định do sản phẩm quy định.
2. **Với locale đã chọn, `ResourceBundle` tải tệp tài nguyên nào và lấy một khóa ở đâu?** Java tìm các bundle ứng viên, có thể thử locale mặc định của JVM và kế thừa khóa từ bundle cha.

Câu hỏi thứ nhất là **chính sách của ứng dụng** (application locale selection/negotiation); câu hỏi thứ hai là **cơ chế tra cứu tài nguyên** (resource-bundle lookup/fallback). Chúng liên quan nhưng không thay thế nhau.

Ví dụ: Người dùng yêu cầu tiếng Pháp Canada (`fr-CA`), nhưng sản phẩm chỉ cung cấp `vi-VN` và `en-US`. Ứng dụng có thể chủ động chọn `vi-VN` làm fallback sản phẩm. Nếu bỏ qua bước này và gọi thẳng `ResourceBundle.getBundle("Messages", Locale.CANADA_FRENCH)`, Java có thể tìm tài nguyên theo locale mặc định của máy chủ, chẳng hạn `en-US`. Đây là **hai quyết định dẫn đến hai kết quả khác nhau**.

> **Nguyên tắc:** Locale của giao diện phải được quyết định ở tầng ứng dụng; bundle được tìm thấy là phương tiện cung cấp dữ liệu dịch. Không nên suy ngược “ứng dụng đang dùng locale nào” chỉ từ tệp bundle được tải.

## 2. Bốn lớp cần phân biệt

| Lớp | Đầu vào | Quyết định | Ví dụ |
| --- | --- | --- | --- |
| Sở thích người dùng | Cấu hình tài khoản, yêu cầu HTTP | Người dùng **muốn** ngôn ngữ nào | `fr-CA` |
| Chọn locale ứng dụng | Sở thích + danh sách locale hỗ trợ + fallback sản phẩm | Giao diện **sẽ dùng** locale nào | `vi-VN` |
| Chọn `ResourceBundle` | Base name, locale ứng dụng, classpath/module và luật tra cứu | Bundle **được tải** | `Messages_vi.properties` |
| Tìm khóa trong bundle | `getString("button.save")` | Giá trị ở bundle hiện tại hay bundle cha | `Messages.properties` |

Một luồng minh họa:

```text
Ưu tiên người dùng: fr-CA
          |
          v
[CHÍNH SÁCH ỨNG DỤNG]
Supported: vi-VN, en-US
Không có fr -> fallback sản phẩm: vi-VN
          |
          v
Locale ứng dụng: vi-VN
          |
          v
[RESOURCEBUNDLE LOOKUP]
Messages_vi_VN? (không)
Messages_vi?    (có) ---> chọn bundle vi
Messages?       (có) ---> parent cho các khóa chưa có
          |
          v
getString("greeting")   -> từ Messages_vi
getString("button.save")-> từ Messages (base)
```

Ở đây có **ba loại fallback** cần gọi tên chính xác:

- **Fallback chọn locale sản phẩm:** từ sở thích không được hỗ trợ sang một locale mà ứng dụng công bố hỗ trợ; do ứng dụng định nghĩa.
- **Fallback chọn bundle:** từ locale ứng viên cụ thể (`vi-VN`) xuống locale rộng hơn (`vi`), có thể tới base bundle, và với `getBundle` mặc định còn có quy tắc thử locale mặc định JVM.
- **Fallback giá trị của khóa:** bundle đã chọn thiếu `button.save`, `getString` có thể đi qua chuỗi bundle cha để tìm cùng khóa.

Sự kiện “chọn `Messages_vi`” không chứng minh ứng dụng đã đổi locale `vi-VN` thành `vi`. Nó chỉ cho biết tài nguyên cụ thể nhất sẵn có cho nội dung đó.

## 3. Tầng ứng dụng tự quyết định locale trước khi tải tài nguyên

Một ứng dụng cần định nghĩa rõ **supported locales** (các locale có thể phục vụ) và **product fallback locale** (locale mặc định của sản phẩm). Những dữ liệu này **không tự xuất hiện** khi chỉ gọi `ResourceBundle.getBundle`.

Các nguồn sở thích thường gặp, theo chính sách tùy sản phẩm:

1. Lựa chọn ngôn ngữ đã lưu trong tài khoản hoặc chọn tạm thời trong giao diện.
2. Sở thích do client gửi, ví dụ `Accept-Language: fr-CA,fr;q=0.9,en-US;q=0.7`.
3. Locale mặc định đã cấu hình cho sản phẩm, ví dụ `vi-VN`.

Ứng dụng có thể ưu tiên lựa chọn tường minh hơn header, nhưng phải tự quy định và kiểm thử thứ tự ưu tiên. `Accept-Language` là **danh sách ưu tiên có trọng số**, không phải một BCP 47 language tag duy nhất; vì vậy không truyền nguyên chuỗi header vào `Locale.forLanguageTag(...)`.

Một thuật toán ứng dụng đơn giản:

```text
1. Đọc ưu tiên của người dùng (có thể nhiều locale).
2. Chuẩn hóa / phân tích cú pháp hợp lệ.
3. Đối chiếu với danh sách locale sản phẩm hỗ trợ.
4. Nếu khớp chính xác, chọn locale đó.
5. Nếu chính sách cho phép, khớp ngôn ngữ hoặc script phù hợp.
6. Nếu không khớp, chọn fallback sản phẩm đã công bố.
7. Truyền locale cuối cùng tới i18n/message service và formatter.
```

Ví dụ, sản phẩm hỗ trợ `en-US` nhưng người dùng yêu cầu `en-GB`. Ứng dụng **có thể** chọn `en-US` vì cùng tiếng Anh nếu chính sách cho phép. Tuy nhiên, việc này có thể làm mất phân biệt vùng khi định dạng ngày tháng; trong ứng dụng phức tạp, **locale ngôn ngữ giao diện** và **locale định dạng** có thể được quản lý riêng.

Với vùng có nhiều ngôn ngữ, không tự suy từ `Locale.getCountry()` sang language. Cũng không tự đổi tiền tệ hay múi giờ khi chọn locale hiển thị: chúng là dữ liệu và chính sách độc lập.

### 3.1. Khớp ưu tiên theo tiêu chuẩn

Java hỗ trợ `Locale.LanguageRange.parse(...)` để phân tích danh sách ưu tiên và `Locale.lookup(...)` hoặc `Locale.filter(...)` để khớp các locale được hỗ trợ. Các phương thức này thực hiện một kiểu tìm kiếm theo RFC 4647, nhưng **chính sách chọn fallback cuối cùng** vẫn do ứng dụng quyết định.

Ví dụ minh họa **nằm trong một phương thức**:

```java
List<Locale.LanguageRange> priorities =
        Locale.LanguageRange.parse("fr-CA,fr;q=0.9,en-US;q=0.7");

List<Locale> supported = List.of(
        Locale.forLanguageTag("vi-VN"),
        Locale.forLanguageTag("en-US")
);

Locale matched = Locale.lookup(priorities, supported);
Locale appLocale = matched != null
        ? matched
        : Locale.forLanguageTag("vi-VN");
```

Với danh sách trên, `en-US` là lựa chọn có mặt trong supported locales và có trong preference list, vì thế `matched` là `en-US`. Nếu danh sách sở thích chỉ có `fr-CA` và `fr`, `lookup` không tìm được lựa chọn được hỗ trợ, trả `null`; ứng dụng sẽ chọn `vi-VN` từ cấu hình fallback.

Đừng giả định `Locale.lookup` tự hiểu chất lượng bản dịch, chủ đích kinh doanh hay việc “fr chắc chắn đổi sang en”. Nó chỉ là một thuật toán khớp định danh ngôn ngữ.

## 4. `ResourceBundle` làm gì sau khi nhận locale?

Giả sử một nhóm tài nguyên `Messages` có các tệp trên classpath:

```text
Messages.properties
Messages_vi.properties
Messages_vi_VN.properties
Messages_en.properties
Messages_en_US.properties
```

Khi yêu cầu `vi-VN`, các ứng viên phổ biến (khi locale có language+region và không có script/variant) là:

```text
Messages_vi_VN
Messages_vi
Messages              (base bundle, Locale.ROOT)
```

Java có thể tải bundle cụ thể và liên kết bundle ít cụ thể hơn làm cha. Nếu `Messages_vi_VN` tồn tại và được chọn, một khóa thiếu ở đây có thể được tìm trong `Messages_vi` rồi `Messages`. Khi không có tệp `vi_VN`, Java có thể chọn `Messages_vi` làm bundle trả về. Nếu cả bundle `vi_VN` lẫn `vi` đều thiếu, hành vi **khác nhau** giữa overload mặc định và `Control` cấm thử fallback locale của JVM.

Đây là mô hình đơn giản cho language/region. Các tag có script, variant hoặc các trường hợp đặc biệt có thể cho ra danh sách candidate dài và thứ tự khác. Muốn quan sát danh sách chính xác cho một locale trong môi trường classpath, có thể dùng `ResourceBundle.Control.getCandidateLocales(...)`.

Tên BCP 47 như `vi-VN` dùng dấu gạch ngang, còn hậu tố tệp `.properties` thường là `_vi_VN`. Đừng coi `Messages_vi_VN` là một language tag.

### 4.1. Đúng bản chất của “fallback sang JVM default”

Với `ResourceBundle.getBundle("Messages", requestedLocale)` ở chế độ mặc định, cơ chế tìm kiếm có thể:

1. Thử các bundle ứng viên của locale yêu cầu (từ cụ thể đến rộng hơn).
2. Nếu **chưa tìm thấy bundle không phải base** cho locale yêu cầu, thử các ứng viên tương ứng với locale mặc định của JVM.
3. Nếu vẫn không có bundle cụ thể hơn, dùng base bundle (`Messages.properties`) đã tìm được; nếu không có bundle khả dụng thì ném `MissingResourceException`.

Vì vậy, **base bundle không nhất thiết được trả về ngay khi tìm thấy**: nó có thể được giữ lại trong khi Java thử locale mặc định của JVM. Hành vi mặc định phụ thuộc vào base name, tài nguyên tồn tại, locale yêu cầu, locale mặc định, provider/caching và môi trường module/classpath.

Ví dụ: máy chủ default locale là `en-US`, có `Messages.properties` và `Messages_en_US.properties`, nhưng không có `Messages_fr` hay `Messages_fr_CA`. Gọi `getBundle("Messages", fr-CA)` có thể trả `Messages_en_US`, **không phải `Messages.properties`**. Điều này là fallback của **bundle loader**, không phải bằng chứng ứng dụng đã chủ động chọn ngôn ngữ tiếng Anh.

Nếu đã có `Messages_fr.properties`, Java tìm thấy một bundle không phải base cho `fr-CA` và sẽ không phải thử nhánh `en-US` chỉ để chọn bundle. Thiếu khóa trong `Messages_fr` lại là một câu chuyện **kế thừa khóa** qua parent chain, không đồng nghĩa tìm một bundle mới theo default locale.

### 4.2. `getNoFallbackControl` loại bỏ đúng loại fallback nào?

Khi ứng dụng chạy trên classpath / unnamed module, Java 17 hỗ trợ:

```java
ResourceBundle.Control control =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle bundle =
        ResourceBundle.getBundle("Messages", selectedLocale, control);
```

`getNoFallbackControl(...)` làm `Control.getFallbackLocale(...)` trả `null`. Nó **ngăn bước chuyển sang default locale JVM** khi không tìm thấy bundle cụ thể cho locale mục tiêu.

Nó **không** có nghĩa:

- Không được dùng `Messages_vi` khi chọn `vi-VN`.
- Không được dùng `Messages.properties` (base bundle).
- Không được kế thừa khóa từ bundle cha.
- Bảo đảm có bản dịch đầy đủ cho mọi khóa.
- Tự thực hiện negotiation để chọn locale thuộc supported list.

Tên dễ gây nhầm: “no fallback” ở đây chỉ áp dụng tới **fallback locale do `Control.getFallbackLocale` quyết định**, không phải mọi tầng fallback của tài nguyên.

**Lưu ý Java Module System (JPMS):** Các overload `getBundle(..., ResourceBundle.Control)` không được hỗ trợ khi gọi từ **named module**, có thể ném `UnsupportedOperationException`. Ví dụ tiếp theo chạy ứng dụng Java đơn giản trên classpath (unnamed module). Với named module, thiết kế theo cơ chế `ResourceBundleProvider`/quy tắc tài nguyên module thay vì sao chép nguyên cách dùng `Control`.

## 5. Ví dụ Java 17 chạy được: cùng yêu cầu, ba kết quả fallback

Ví dụ này **cố ý** giả lập JVM default locale là `en-US` trong một ứng dụng dòng lệnh độc lập để minh họa rủi ro. Không gọi `Locale.setDefault` cho từng request trong dịch vụ nhiều người dùng vì đây là thay đổi toàn JVM.

Tạo chính xác bốn tệp cùng thư mục:

```text
LocaleFallbackDemo.java
Messages.properties
Messages_vi.properties
Messages_en_US.properties
```

**`Messages.properties`**

```properties
greeting=Base greeting
button.save=Save
```

**`Messages_vi.properties`**

```properties
greeting=Xin chào
```

**`Messages_en_US.properties`**

```properties
greeting=Howdy
```

**`LocaleFallbackDemo.java`**

```java
import java.util.List;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocaleFallbackDemo {
    private static final Locale PRODUCT_FALLBACK =
            Locale.forLanguageTag("vi-VN");

    private static final List<Locale> SUPPORTED = List.of(
            PRODUCT_FALLBACK,
            Locale.forLanguageTag("en-US")
    );

    private static Locale chooseAppLocale(Locale requested) {
        // Chính sách đơn giản, minh họa: chỉ nhận khớp chính xác.
        return SUPPORTED.contains(requested)
                ? requested
                : PRODUCT_FALLBACK;
    }

    public static void main(String[] args) {
        Locale originalDefault = Locale.getDefault();

        try {
            // Chỉ dùng trong demo cô lập để tái hiện JVM fallback.
            Locale.setDefault(Locale.US);

            Locale requested = Locale.CANADA_FRENCH; // fr-CA
            Locale appLocale = chooseAppLocale(requested);

            ResourceBundle.Control noJvmFallback =
                    ResourceBundle.Control.getNoFallbackControl(
                            ResourceBundle.Control.FORMAT_PROPERTIES);

            ResourceBundle fromAppPolicy =
                    ResourceBundle.getBundle(
                            "Messages", appLocale, noJvmFallback);

            ResourceBundle fromNaiveLookup =
                    ResourceBundle.getBundle("Messages", requested);

            ResourceBundle fromStrictLookup =
                    ResourceBundle.getBundle(
                            "Messages", requested, noJvmFallback);

            System.out.println("requested=" + requested.toLanguageTag());
            System.out.println("appLocale=" + appLocale.toLanguageTag());
            System.out.println("appBundle=" +
                    fromAppPolicy.getLocale().toLanguageTag());
            System.out.println("appGreeting=" +
                    fromAppPolicy.getString("greeting"));

            System.out.println("naiveBundle=" +
                    fromNaiveLookup.getLocale().toLanguageTag());
            System.out.println("naiveGreeting=" +
                    fromNaiveLookup.getString("greeting"));

            System.out.println("strictBase=" +
                    fromStrictLookup.getLocale().equals(Locale.ROOT));
            System.out.println("appSave=" +
                    fromAppPolicy.getString("button.save"));
        } finally {
            Locale.setDefault(originalDefault);
        }
    }
}
```

Biên dịch và chạy trên classpath bằng JDK 17 trở lên, lưu các tệp ở UTF-8:

```bash
javac -encoding UTF-8 LocaleFallbackDemo.java
java -cp . LocaleFallbackDemo
```

**Stdout kỳ vọng:**

```text
requested=fr-CA
appLocale=vi-VN
appBundle=vi
appGreeting=Xin chào
naiveBundle=en-US
naiveGreeting=Howdy
strictBase=true
appSave=Save
```

Phân tích từng kết quả:

- `requested=fr-CA`: sở thích đầu vào, **chưa** phải locale được sản phẩm chấp nhận.
- `appLocale=vi-VN`: kết quả từ `chooseAppLocale`, do **chính sách ứng dụng** quyết định vì `fr-CA` không nằm trong supported list.
- `appBundle=vi`: không có `Messages_vi_VN.properties`, Java dùng `Messages_vi.properties` cho appLocale `vi-VN`. Hai locale này hợp lệ khi khác nhau: một là lựa chọn ứng dụng, một là mức dữ liệu dịch có sẵn.
- `appGreeting=Xin chào`: khóa `greeting` có mặt ở `Messages_vi`.
- `naiveBundle=en-US` và `naiveGreeting=Howdy`: gọi thẳng `getBundle` bằng `fr-CA` mà không chọn locale ứng dụng; Java không tìm được bản Pháp nên đi sang **JVM default `en-US`**.
- `strictBase=true`: cùng locale yêu cầu `fr-CA` nhưng với no-JVM-fallback control, không có bundle Pháp, Java nhận base bundle `Messages.properties`; `getLocale()` bằng `Locale.ROOT`.
- `appSave=Save`: `Messages_vi` không có khóa `button.save`, nên `getString` lấy từ parent `Messages.properties`. Đây là **fallback của khóa**, độc lập với việc chọn bundle. Một bản dịch tiếng Việt chưa đủ khóa có thể lộ chữ tiếng Anh ngay cả khi ứng dụng đã chọn `vi-VN` đúng.

Lưu ý: dùng `try/finally` chỉ để khôi phục mặc định JVM sau demo; `Locale.setDefault(...)` vẫn thay đổi trạng thái toàn tiến trình và không phù hợp trong ứng dụng server chạy đồng thời. Demo giả định không có `Messages_fr*`, `Messages_en*` khác trong classpath và không có lớp `Messages` tương ứng. Nếu thêm tệp cùng base name, thứ tự/chọn bundle sẽ thay đổi có chủ đích.

## 6. Quy tắc quan trọng: tìm bundle khác với tìm khóa

Xét:

```properties
# Messages.properties
menu.open=Open
menu.close=Close
```

```properties
# Messages_vi.properties
menu.open=Mở
```

Nếu chọn `vi-VN` và Java chọn `Messages_vi`:

| Lời gọi | Kết quả | Nguồn |
| --- | --- | --- |
| `bundle.getLocale()` | `vi` | Bundle được chọn |
| `bundle.getString("menu.open")` | `Mở` | Bundle `vi` |
| `bundle.getString("menu.close")` | `Close` | Bundle cha/base |
| `bundle.getString("menu.exit")` | `MissingResourceException` | Không có ở chuỗi bundle |

Không có sự kiện “`getString` đổi locale ứng dụng sang tiếng Anh”; nó đơn thuần trả chuỗi từ parent khi key thiếu. Bất kỳ ứng dụng nào muốn hỗ trợ tiếng Việt đầy đủ cần **kiểm tra độ phủ của khóa** (coverage), không chỉ kiểm tra `getBundle` tải được.

Một rủi ro khác: một chuỗi dịch có thể dùng tham số `{0}`, `{1}` hoặc ngữ pháp khác; fallback lấy chuỗi từ base nhưng formatter, con số hoặc ngày lại theo locale yêu cầu. Do đó không trộn chuỗi từng ngôn ngữ một cách vô ý; hãy có chính sách fallback về nội dung và test hiển thị với tham số.

## 7. Bảng hành vi cho các cách gọi thường gặp

Giả sử JVM default locale là `en-US`, tồn tại các tệp `Messages.properties`, `Messages_vi.properties`, `Messages_en_US.properties`, không có bản `fr` hoặc `fr_CA`:

| Yêu cầu | Cách gọi | Bundle được trả | Vì sao |
| --- | --- | --- | --- |
| `vi-VN` | `getBundle("Messages", viVN)` | `vi` | Có bản gần nhất theo ngôn ngữ |
| `vi-VN` | `getBundle("Messages", viVN, noJvmFallback)` | `vi` | Không cần thử JVM default |
| `fr-CA` | `getBundle("Messages", frCA)` | `en-US` | Không có bản Pháp, nên thử JVM default |
| `fr-CA` | `getBundle("Messages", frCA, noJvmFallback)` | `ROOT` (base) | Không thử JVM default; còn base |
| `vi-VN` sau app fallback từ `fr-CA` | `getBundle("Messages", selectedViVN, noJvmFallback)` | `vi` | Do sản phẩm chọn locale rồi mới tra cứu |

Nếu bỏ cả `Messages.properties` và không còn bất cứ bundle nào phù hợp theo quy tắc tìm kiếm, Java sẽ ném `MissingResourceException`. `getNoFallbackControl` **không bảo đảm** luôn có dữ liệu; nó chỉ đổi chiến lược thử fallback locale của JVM.

Trong một hệ thống có nhiều hơn hai thành phần locale, script/variant làm ứng viên đa dạng hơn; bảng trên mô tả đúng **bộ tệp giả định** và không phải bảng tra cứu tổng quát cho mọi locale có thể có.

## 8. Vì sao `getBundle().getLocale()` không nên dùng làm locale của cả ứng dụng?

Giả sử người dùng được chọn `vi-VN` nhưng trong hệ thống chỉ tồn tại `Messages_vi.properties`. `bundle.getLocale()` trả `vi` vì đó là bundle đã tìm thấy. Nếu lại dùng:

```java
Locale wrongFormattingLocale = bundle.getLocale();
```

thì ứng dụng vô tình đánh mất thông tin region `VN` từ lựa chọn ban đầu. Số tiền, ngày, ngôn ngữ và quy ước vùng có thể bị định dạng theo locale quá chung. Tương tự, `getBundle(... fr-CA ...)` có thể trả bundle `en-US` do JVM default; `getLocale()` lúc này không phản ánh ý muốn của người dùng.

Thiết kế nên giữ hai biến tường minh:

```java
Locale uiLocale = Locale.forLanguageTag("vi-VN");

ResourceBundle labels = ResourceBundle.getBundle(
        "Messages", uiLocale,
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES)
);

// uiLocale là locale ứng dụng đã chọn.
// labels.getLocale() chỉ cho biết bundle cụ thể được trả.
```

Đây là đoạn mã minh họa đặt trong class hoặc method. Formatter nên được cấp **locale trình bày đã quyết định**, có thể là `uiLocale` hoặc `formattingLocale` riêng, theo thiết kế sản phẩm. Đừng dùng `labels.getLocale()` để ghi đè state locale người dùng.

## 9. Thiết kế dịch vụ nhiều người dùng

Trên backend Java, các request có thể đến đồng thời:

```text
Request A: người dùng vi-VN ─┐
                             ├── cùng JVM ── cùng tài nguyên, nhiều locale
Request B: người dùng en-US ─┘
```

Nếu request A chạy `Locale.setDefault(viVN)` còn request B chạy `Locale.setDefault(enUS)`, hai request có thể ghi đè trạng thái chung và gây kết quả không ổn định. Cách làm đúng là truyền locale theo request:

```java
String renderGreeting(Locale uiLocale) {
    ResourceBundle bundle =
            ResourceBundle.getBundle("Messages", uiLocale);
    return bundle.getString("greeting");
}
```

Đây là đoạn minh họa trong một lớp. Với chính sách cần tránh JVM-default fallback, trên classpath có thể dùng overload `Control` như phần trước; trên named module cần cơ chế provider phù hợp.

Các tầng thường dùng:

- **Locale resolver:** chọn `uiLocale` từ profile và request, đối chiếu supported list, trả về product fallback nếu cần.
- **Message service:** tải bundle với `uiLocale` đã chọn, lấy key và xử lý placeholder; kiểm soát fallback chính xác.
- **Formatter:** tạo `NumberFormat`/`DateTimeFormatter` với locale trình bày, chọn `ZoneId` độc lập.
- **Validation/error boundary:** xuất **mã lỗi ổn định** cho hệ thống, dịch thông điệp khi hiển thị, không coi nội dung tiếng người dùng là định danh nghiệp vụ.

Cấu hình locale mặc định của JVM vẫn hữu ích cho ứng dụng dòng lệnh một người dùng hoặc khi môi trường chủ động định nghĩa mặc định. Nhưng với server nhiều người dùng, không dùng nó như quyết định fallback không được công bố của sản phẩm.

## 10. Hai chính sách fallback có thể kết hợp như thế nào?

### Chính sách A: Chỉ cho người dùng dùng locale được sản phẩm hỗ trợ

Ví dụ supported `vi-VN, en-US`, fallback sản phẩm `vi-VN`. UI tự chọn locale theo profile/`Accept-Language`; sau đó tìm bundle. Khi không có tài nguyên tương ứng, hệ thống coi là lỗi triển khai hoặc dùng tài nguyên gốc theo quy tắc đã định. Ưu điểm: hành vi rõ, có thể kiểm soát trải nghiệm người dùng.

### Chính sách B: Cho phép locale rộng hơn nhưng fallback bản dịch

Ứng dụng có thể chấp nhận `fr-CA` để **định dạng** ngày, giờ và số, dù chưa có bản tiếng Pháp; còn **ngôn ngữ thông điệp** được fallback rõ ràng sang tiếng Anh hoặc tiếng Việt. Muốn làm tốt, nên tách `formattingLocale` khỏi `messageLocale`, hoặc cung cấp chiến lược fallback cho message resolver; không cần ép tất cả dữ liệu đi theo bundle được tải.

Một mô hình là:

```text
User preference: fr-CA
      ├── formattingLocale = fr-CA
      └── messageLocale    = en-US (product fallback được công bố)
                                   │
                                   └── Messages_en_US / Messages_en / base
```

Hai chính sách đều có thể đúng tùy sản phẩm. Vấn đề là phải **quy định và kiểm thử rõ**, thay vì để JVM default ngầm quyết định ngôn ngữ người dùng sẽ thấy.

### Có nên dùng `Messages.properties` như “bản dịch mặc định”?

Có thể, nếu nó chứa bản dịch của ngôn ngữ fallback sản phẩm. Tuy nhiên base bundle là tài nguyên cuối của parent chain, **không tự thay việc chọn product locale**. Một tệp base tiếng Anh có thể làm lộ tiếng Anh ở một màn hình đã chọn tiếng Việt khi bản Việt thiếu khóa. Vì thế:

1. Xác định ngôn ngữ của base bundle bằng quy ước dự án.
2. Đảm bảo mọi locale được tuyên bố hỗ trợ có đủ key quan trọng và placeholder.
3. Cho phép fallback key chỉ theo chính sách đã công bố; cân nhắc fail-fast ở môi trường kiểm thử cho bản dịch thiếu.
4. Không dựa vào default locale JVM để hoàn thiện các bản dịch thiếu.

## 11. Cách kiểm tra, chẩn đoán và xác minh

Khi người dùng báo “đã chọn tiếng Việt nhưng lại thấy tiếng Anh”, cần tách từng bằng chứng:

| Cần biết | Quan sát |
| --- | --- |
| Sở thích người dùng được đọc là gì? | Language tag hoặc danh sách `Accept-Language` |
| App cuối cùng chọn gì? | Log `uiLocale.toLanguageTag()` sau locale resolver |
| JVM default là gì? | `Locale.getDefault()`, chỉ để chẩn đoán |
| Bundle nào được tải? | `bundle.getLocale()` và base name |
| Khóa đang lấy từ bundle nào? | Kiểm tra trong tệp bundle hiện tại và parent; `getLocale()` một mình không chỉ rõ nơi từng khóa xuất phát |
| Bản dịch có đủ khóa không? | Test độ phủ và placeholder ở build/test |
| Cách gọi `getBundle` là gì? | Có dùng `Control` hay provider? classpath hay named module? |
| Có cache/triển khai trộn phiên bản không? | Xem vòng đời cache, class loader, tài nguyên sau deploy |

**Không nên log nội dung nhạy cảm của người dùng** chỉ để chẩn đoán localization. Log locale, mã key, mã lỗi và bundle được chọn khi cần thiết thường đủ.

`ResourceBundle` có cache. Khi thay tệp `.properties` trong lúc JVM đang chạy, kết quả đọc có thể chưa đổi do cache. Tùy kiến trúc, cần triển khai lại, cấu hình TTL/`needsReload`, hoặc `ResourceBundle.clearCache(...)`; không mặc định rằng sửa tệp lập tức thay đổi mọi bundle. Đồng thời, classpath nhiều JAR có thể chứa cùng base bundle, cần kiểm tra thực tế nơi tệp được đóng gói.

## 12. Kiểm thử hành vi đúng tầng

Bộ kiểm thử nên tách **hai nhóm**:

**Nhóm 1 — locale resolver (chính sách ứng dụng)**

- Profile chọn `vi-VN`, request header chọn `en-US`: thuật toán ưu tiên cấu hình người dùng đúng như quy tắc sản phẩm.
- Sở thích `fr-CA` không hỗ trợ: app chọn fallback sản phẩm, độc lập default locale JVM.
- Sở thích `en-GB` với supported `en-US`: test chính sách có hoặc không cho fallback theo ngôn ngữ.
- Header nhiều tag và `q`: parse/lookup đúng thứ tự ưu tiên, không gọi `forLanguageTag` với nguyên chuỗi header.

**Nhóm 2 — resource lookup (Java runtime / file thực tế)**

- Có `Messages_vi_VN`: trả bundle `vi-VN`.
- Không có `Messages_vi_VN` nhưng có `Messages_vi`: trả bundle `vi`.
- Không có bundle của `fr-CA`: so sánh overload mặc định với `getNoFallbackControl` trong môi trường default `en-US`.
- Tệp `vi` thiếu một key: xác nhận key từ bundle cha hoặc phát hiện thiếu theo chính sách coverage.
- Không có bundle thỏa mãn: ném `MissingResourceException`.
- Cùng selectedLocale nhưng đổi JVM default: kết quả không được làm ứng dụng chọn một locale sản phẩm khác.

Trường hợp test thay `Locale.setDefault` cần chạy cô lập, tránh làm hỏng các test chạy đồng thời. Bài demo đặt lại default trong `finally`, nhưng vẫn không nên chạy song song với test khác phụ thuộc global default.

### 12.1. Một bài tập nhỏ quan sát candidate locales

Đoạn sau độc lập và chạy với JDK 17:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class CandidateLocalesDemo {
    public static void main(String[] args) {
        Locale requested = Locale.forLanguageTag("vi-VN");
        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        for (Locale candidate :
                control.getCandidateLocales("Messages", requested)) {
            System.out.println(candidate.equals(Locale.ROOT)
                    ? "(base)" : candidate.toLanguageTag());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CandidateLocalesDemo.java
java CandidateLocalesDemo
```

Stdout chính xác trong Java 17:

```text
vi-VN
vi
(base)
```

Đoạn code trên chỉ **liệt kê candidate locales**, không thử tìm tệp `Messages`, cũng không hiển thị fallback sang default JVM: fallback JVM là bước tìm kiếm bổ sung do `getFallbackLocale` quyết định, không nằm trong danh sách candidate cho `vi-VN`.

## 13. Những hiểu lầm hay gặp

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| `getBundle(requested)` tự chọn locale sản phẩm được hỗ trợ | Nó tra bundle theo thuật toán Java; supported locales là chính sách app |
| `Locale.getDefault()` là ngôn ngữ do người dùng chọn | Đây là trạng thái mặc định JVM; có thể khác mỗi request |
| `getNoFallbackControl` cấm mọi fallback | Nó cấm fallback locale do `getFallbackLocale` cung cấp; vẫn có candidate/base/parent |
| Có `Messages.properties` thì Java luôn dùng base trước JVM default | Base có thể được giữ lại trong khi tìm bundle của JVM default |
| `bundle.getLocale()` luôn bằng locale yêu cầu | Giá trị này phản ánh bundle thực sự được trả |
| Một key thiếu làm Java “đổi sang bundle default JVM” | Key lookup đi dọc parent chain của bundle được chọn; đừng lẫn với bundle selection |
| `Messages_vi` tồn tại nghĩa là bản dịch Việt đã đủ | Cần test toàn bộ key và placeholder |
| Chọn locale ứng dụng đủ để quyết định múi giờ và tiền tệ | `ZoneId` và `Currency` là quyết định riêng |
| `ResourceBundle.Control` chạy giống nhau trên classpath và named module | Overload `Control` không được hỗ trợ khi gọi từ named module |
| Đổi default locale theo từng HTTP request là an toàn | Default là trạng thái chung JVM, dễ ảnh hưởng request khác |

## 14. Câu hỏi tự luyện và đáp án

**Câu 1.** Người dùng gửi `fr-CA`, ứng dụng chỉ hỗ trợ `vi-VN` và `en-US`. Máy chủ đang default `ja-JP`. Ai quyết định UI hiển thị tiếng Việt?

**Đáp án:** locale resolver của ứng dụng có quy tắc fallback sản phẩm sang `vi-VN`. `ResourceBundle` không thể tự suy diễn điều này chỉ từ `fr-CA` và default JVM `ja-JP`.

**Câu 2.** App đã chọn `vi-VN`, bundle được trả có locale `vi`. Đây có phải lỗi?

**Đáp án:** chưa chắc. Nếu chưa có `Messages_vi_VN` nhưng có `Messages_vi`, Java chọn bản theo ngôn ngữ là hợp lệ. Vẫn nên giữ `vi-VN` cho formatter nếu đó là locale trình bày đã quyết định.

**Câu 3.** `getNoFallbackControl` có ngăn lấy `button.save` từ `Messages.properties` khi `Messages_vi.properties` thiếu khóa không?

**Đáp án:** không. Nó chỉ ngăn tìm **fallback locale** theo `Control.getFallbackLocale`, không ngăn chuỗi bundle cha.

**Câu 4.** Có base bundle và bundle `en-US`, default JVM `en-US`, yêu cầu `fr-CA` không có bản Pháp. Overload mặc định thường trả gì?

**Đáp án:** `en-US` vì Java thử default locale trước khi kết luận dùng base; thử `getNoFallbackControl` sẽ trả base trong điều kiện bộ tệp giả định ở bài.

**Câu 5.** App hiển thị tiếng Anh cho một khóa đơn lẻ giữa màn hình tiếng Việt, nhưng `bundle.getLocale()` vẫn là `vi`. Nên kiểm tra gì?

**Đáp án:** kiểm tra khóa đó có trong `Messages_vi` hay chỉ trong parent/base; sau đó bổ sung dịch và test coverage. Không vội thay đổi locale resolver vì bundle đã được chọn đúng.

## 15. Tóm lược kiến thức cần nhớ

- **Locale selection**: quyết định của sản phẩm cho từng người dùng hoặc request, dựa trên preferences, supported locales và fallback rõ ràng.
- **Bundle selection**: thuật toán Java tìm tài nguyên phù hợp với locale đã truyền, có candidate locales, base bundle và có thể thêm fallback tới default locale JVM ở overload mặc định.
- **Key inheritance**: khi bundle đã chọn thiếu key, `getString` tra bundle cha; đây không phải chọn lại locale ứng dụng.
- **`getNoFallbackControl`**: chặn fallback sang default locale JVM khi dùng `ResourceBundle.Control` trên classpath, nhưng vẫn cho candidate và base/parent hoạt động.
- **Thiết kế ổn định**: giữ locale của ứng dụng tường minh, ghi nhận bundle locale như thông tin chẩn đoán, test thiếu khóa và không dùng `Locale.setDefault` theo từng request.

Tài liệu tham khảo chính thức cho Java 17:

- [`ResourceBundle` — Resource Bundle Search and Loading Strategy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [`ResourceBundle.Control` — `getCandidateLocales` và `getNoFallbackControl`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html)
- [`Locale` — Language Ranges and Matching](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
