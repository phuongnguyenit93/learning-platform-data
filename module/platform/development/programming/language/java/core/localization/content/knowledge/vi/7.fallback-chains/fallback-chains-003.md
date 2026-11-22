# Phân biệt tìm bundle phù hợp với tìm khóa trong chuỗi cha

## 1. Vấn đề: cùng một “fallback”, hai thao tác khác nhau

Trong Java, `ResourceBundle` cung cấp tài nguyên theo từng locale. Khi ứng dụng viết:

```java
ResourceBundle bundle = ResourceBundle.getBundle("Messages", locale);
String value = bundle.getString("button.save");
```

Java thực hiện **hai công việc khác nhau**:

1. **Tìm bundle phù hợp:** `getBundle(...)` xác định trong họ tài nguyên `Messages` có bundle nào dùng được cho locale yêu cầu, dựa vào danh sách ứng viên, classpath/module, chế độ fallback và các tài nguyên thực sự có mặt.
2. **Tìm khóa trong chuỗi cha:** sau khi có bundle, `getString("button.save")` tìm giá trị của khóa ở bundle đang giữ; nếu không có thì tra các bundle cha (`parent`) đã được liên kết.

Hai thao tác dễ nhầm vì cùng có thể đi từ nội dung cụ thể sang tổng quát. Nhưng chúng khác **điểm xuất phát, câu hỏi được giải quyết, lúc xảy ra và kiểu lỗi**.

| Tiêu chí | Tìm bundle phù hợp | Tìm khóa trong chuỗi cha |
| --- | --- | --- |
| API thường gặp | `ResourceBundle.getBundle(...)` | `bundle.getString(key)` / `bundle.getObject(key)` |
| Câu hỏi | “Có bản tài nguyên nào phù hợp với locale này?” | “Trong bundle này hoặc cha của nó, khóa này ở đâu?” |
| Đầu vào chủ đạo | Base name, locale, module/class loader, `Control` (nếu hỗ trợ) | Một bundle đã tải và một khóa |
| Đơn vị tìm kiếm | Bundle / tệp / lớp tài nguyên | Key/value trong bundle hiện tại và các parent |
| Kết quả | Đối tượng `ResourceBundle` | Giá trị đối tượng hoặc chuỗi của khóa |
| Lỗi điển hình | `MissingResourceException` khi không tìm được bundle nào phù hợp | `MissingResourceException` khi không tìm được khóa |
| Dùng locale mặc định JVM? | Có thể, theo cơ chế tải bundle | Không tự chuyển sang locale mặc định chỉ vì thiếu key |
| Đường đi tới base bundle | Một ứng viên cuối của quá trình chọn bundle | Một parent có thể cung cấp khóa còn thiếu |

**Điểm quan trọng nhất:** Nếu tìm được bundle `Messages_vi_VN`, sau đó khóa `button.save` bị thiếu, Java **không chạy lại quá trình chọn bundle để tìm một bản tiếng Anh có khóa**. Nó dùng *parent chain của chính bundle đã chọn*.

## 2. Chuỗi tài nguyên theo độ cụ thể

Giả sử bộ tài nguyên trên classpath:

```text
Messages.properties
Messages_vi.properties
Messages_vi_VN.properties
Messages_en_US.properties
```

- `Messages.properties`: base bundle (bundle không có hậu tố locale).
- `Messages_vi.properties`: tài nguyên chung cho tiếng Việt.
- `Messages_vi_VN.properties`: tài nguyên chuyên biệt tiếng Việt tại Việt Nam.
- `Messages_en_US.properties`: một bundle khác dành cho tiếng Anh tại Hoa Kỳ.

Với locale `vi-VN` đơn giản, Java có danh sách ứng viên theo mức cụ thể:

```text
Messages_vi_VN
      |
      v
Messages_vi
      |
      v
Messages (base)
```

Khi tìm được `Messages_vi_VN`, các bundle mức rộng hơn thực sự tồn tại có thể được liên kết thành chuỗi cha:

```text
bundle đang giữ
  Messages_vi_VN
      parent --> Messages_vi
                      parent --> Messages (base)
```

**Hai mũi tên có ý nghĩa khác nhau theo thời điểm:**

- Khi **tải**, Java chọn một bundle phù hợp và thiết lập quan hệ parent với các bundle ít cụ thể hơn.
- Khi **đọc key**, Java tìm lần lượt ở bundle hiện tại rồi đi dọc parent đã có. Parent là **tài nguyên thực tế** được nạp theo thuật toán, không phải tự động mọi hậu tố có thể nghĩ ra.

Nếu không có `Messages_vi_VN.properties` nhưng có `Messages_vi.properties`, bundle trả về có thể chính là `Messages_vi` với parent là base. `bundle.getLocale()` cho biết locale của **bundle được trả về**, có thể là `vi` dù locale yêu cầu là `vi-VN`.

### 2.1. Tên tệp và language tag

`Locale.forLanguageTag("vi-VN")` dùng BCP 47 với dấu gạch ngang `-`. Hậu tố tệp `ResourceBundle` dùng cách đặt tên `Messages_vi_VN.properties` với dấu gạch dưới `_`. Đừng nhầm chuỗi tên tệp với language tag hay tên base bundle.

Danh sách `vi_VN → vi → base` phù hợp ví dụ language/region không script/variant. Với `zh-Hant-TW` hoặc locale có variant, danh sách candidate có thể dài và khác thứ tự; không tự suy ra luôn chỉ có ba mức.

## 3. Giai đoạn A: tìm và tải bundle phù hợp

Ở Java, một lời gọi điển hình là:

```java
Locale requested = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle = ResourceBundle.getBundle("Messages", requested);
```

Về ý tưởng, Java cần:

1. Tạo danh sách **candidate locales** theo `requested`, từ cụ thể đến ít cụ thể hơn, trong đó có base.
2. Tìm bundle tương ứng trong nguồn tài nguyên khả dụng, thông thường là class `ListResourceBundle` hoặc tệp `.properties` trên classpath; class-based bundle có thể được ưu tiên hơn properties theo mặc định.
3. Nếu có bundle phù hợp đủ cụ thể, chọn nó và liên kết các parent hiện có.
4. Nếu không tìm được bundle không phải base cho locale yêu cầu, chiến lược mặc định có thể thử lại với **locale mặc định của JVM**; base bundle đóng vai trò tài nguyên cuối.
5. Nếu không có bundle phù hợp nào, ném `MissingResourceException`.

Mô hình này là mô hình cho classpath/unnamed module với chiến lược tải mặc định. Trong named module, Java có thêm quy tắc truy cập tài nguyên và provider; không nên suy tất cả từ ví dụ classpath.

**Chú ý bước 4:** Một tệp `Messages.properties` đang tồn tại không nhất thiết được trả ngay nếu không có bundle theo locale yêu cầu. Chẳng hạn yêu cầu `fr-FR`, JVM default `en-US` và có `Messages_en_US.properties`, Java có thể chọn bundle tiếng Anh theo default JVM trước khi dùng base. Đây vẫn là **tìm bundle**, xảy ra trước khi gọi `getString(key)`.

Khi Java chọn `Messages_en_US` vì không có bản Pháp, parent chain lúc đó được xây dựng cho nhánh bundle đã chọn. Nó không tự tạo một cây toàn cầu chứa mọi ngôn ngữ.

### 3.1. `getBundle` không kiểm tra key bạn sẽ đọc

Lời gọi `getBundle("Messages", viVN)` không có tham số `key`. Nó không biết lát nữa bạn sẽ gọi `getString("button.save")` hay `getString("menu.exit")`.

Một bundle `Messages_vi_VN` có **duy nhất một khóa** vẫn có thể được chọn. Chất lượng hoặc độ đầy đủ của bản dịch là trách nhiệm quản lý nội dung và kiểm thử, không phải tiêu chí mà `getBundle` dùng để từ chối bundle.

### 3.2. Quan sát candidate locales chính xác

Ví dụ Java 17 độc lập dưới đây liệt kê danh sách candidate cho `vi-VN` mà không cần tạo bất kỳ tệp tài nguyên nào.

Tệp `CandidatesDemo.java`:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class CandidatesDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");

        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        for (Locale candidate :
                control.getCandidateLocales("Messages", locale)) {
            System.out.println(
                    candidate.equals(Locale.ROOT)
                            ? "(base)"
                            : candidate.toLanguageTag());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 CandidatesDemo.java
java CandidatesDemo
```

Stdout:

```text
vi-VN
vi
(base)
```

Lệnh `getCandidateLocales` chỉ cho biết **các ứng viên có thể thử**. Nó không bảo đảm tất cả tệp tương ứng đang tồn tại, không cho biết key nào hiện diện, và không tự biểu diễn bước fallback sang locale mặc định JVM.

## 4. Giai đoạn B: đọc key trong bundle và parent chain

Sau khi đã có đối tượng:

```java
String savedLabel = bundle.getString("button.save");
```

`getString` thực chất lấy kết quả của `getObject(key)` rồi chuyển sang `String`. Theo đặc tả `ResourceBundle`, `getObject`:

1. Hỏi **bundle hiện tại** bằng `handleGetObject(key)`.
2. Nếu không có giá trị ở bundle này và bundle có parent, gọi `parent.getObject(key)`.
3. Lặp theo chuỗi cha cho đến khi tìm thấy giá trị.
4. Nếu hết chuỗi mà không có, ném `MissingResourceException`.

Không có bước tự ý tìm `Messages_en_US` khi một key đang thiếu ở `Messages_vi_VN`. Nếu `Messages_en_US` là một “anh em” thuộc locale khác và **không nằm trong parent chain đang giữ**, key ở đó hoàn toàn không được xét.

Giữa một key vừa có trong `Messages_vi_VN` vừa có trong `Messages_vi`, giá trị ở **bundle cụ thể hơn** thắng. Đây là **shadowing/override** một khóa bằng bản dịch cụ thể.

Một số API hay bị hiểu sai:

| API | Có tính cả parent không? | Điều cần nhớ |
| --- | --- | --- |
| `getString(key)` | Có | Trả giá trị từ nơi gần nhất chứa key |
| `getObject(key)` | Có | Trả object, hoặc ném khi thiếu |
| `getStringArray(key)` | Có | Giá trị phải có kiểu `String[]` |
| `containsKey(key)` | Có | `true` chưa chứng minh bundle hiện tại có key riêng |
| `keySet()` | Có | Tập key nhìn thấy từ bundle và parent |
| `getKeys()` | Có | Liệt kê khóa từ bundle và các parent |
| `getLocale()` | Không phải tra key | Cho biết locale của bundle được trả, **không nói key đến từ tệp nào** |

Với `getString(key)`, nếu key tồn tại nhưng giá trị không có kiểu `String`, có thể gặp `ClassCastException`. Nếu key `null`, gặp `NullPointerException`. Cần phân biệt các lỗi ấy với “không tìm được bundle”.

### 4.1. Hai cách “thiếu” không giống nhau

- **Thiếu bundle:** `getBundle("NoSuchBase", locale)` không tìm thấy cả họ bundle khả dụng → ném `MissingResourceException` ngay tại bước tải.
- **Thiếu key:** `getBundle("Messages", locale)` đã thành công, nhưng `getString("does.not.exist")` không thấy key trong bất kỳ parent nào → cũng ném `MissingResourceException`, nhưng ở **bước đọc key**.

Có thể log có ngữ cảnh để chẩn đoán hai lỗi riêng: base name, requested locale, resolved bundle locale và key; đừng chỉ dựa vào việc cả hai cùng ném một exception class.

## 5. Ví dụ hoàn chỉnh: mỗi key được lấy ở một mức khác nhau

Tạo bốn tệp trong **cùng một thư mục**:

```text
BundleChainDemo.java
Messages.properties
Messages_vi.properties
Messages_vi_VN.properties
```

**`Messages.properties`**

```properties
title=Base title
button.save=Save
help=Base help
```

**`Messages_vi.properties`**

```properties
title=Tiêu đề tiếng Việt
button.save=Lưu
```

**`Messages_vi_VN.properties`**

```properties
title=Tiêu đề dành cho Việt Nam
```

**`BundleChainDemo.java`**

```java
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;

public class BundleChainDemo {
    public static void main(String[] args) {
        Locale requested = Locale.forLanguageTag("vi-VN");

        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        ResourceBundle bundle =
                ResourceBundle.getBundle("Messages", requested, control);

        System.out.println("requested=" + requested.toLanguageTag());
        System.out.println("selected=" + bundle.getLocale().toLanguageTag());
        System.out.println("title=" + bundle.getString("title"));
        System.out.println("button.save=" + bundle.getString("button.save"));
        System.out.println("help=" + bundle.getString("help"));
        System.out.println("has.help=" + bundle.containsKey("help"));
        System.out.println("has.unknown=" + bundle.containsKey("unknown"));

        try {
            bundle.getString("unknown");
        } catch (MissingResourceException ex) {
            System.out.println("unknown=MissingResourceException");
        }
    }
}
```

Chạy bằng JDK 17+ trên classpath; lưu các tệp `.properties` và `.java` bằng UTF-8:

```bash
javac -encoding UTF-8 BundleChainDemo.java
java -cp . BundleChainDemo
```

Stdout khi terminal hiển thị Unicode UTF-8:

```text
requested=vi-VN
selected=vi-VN
title=Tiêu đề dành cho Việt Nam
button.save=Lưu
help=Base help
has.help=true
has.unknown=false
unknown=MissingResourceException
```

Giải thích:

- `requested` là locale yêu cầu `vi-VN`.
- `selected` cũng là `vi-VN` vì có `Messages_vi_VN.properties`. Đó là **kết quả tìm bundle**.
- `title` ở ngay `Messages_vi_VN`, vì vậy che giá trị cùng key ở `Messages_vi` và base.
- `button.save` không có trong `vi_VN`; `getString` tìm trong parent `Messages_vi`, trả `Lưu`.
- `help` không nằm trong `vi_VN` hay `vi`; nó nằm tại base, trả `Base help`.
- `bundle.containsKey("help")` là `true` vì API tính cả parent. Không được suy kết quả này thành “tệp `Messages_vi_VN.properties` có key `help`”.
- `unknown` không có ở bất kỳ mức nào; `containsKey` cho `false` và `getString` ném `MissingResourceException`.

Có thể tóm tắt **nguồn của từng key** trong tình huống này:

| Key | Tệp gần nhất chứa key | Giá trị |
| --- | --- | --- |
| `title` | `Messages_vi_VN.properties` | `Tiêu đề dành cho Việt Nam` |
| `button.save` | `Messages_vi.properties` | `Lưu` |
| `help` | `Messages.properties` | `Base help` |
| `unknown` | Không có trong chain | Ném `MissingResourceException` |

**Phân biệt quan trọng:** `bundle.getLocale()` vẫn trả `vi-VN` ở cả bốn lời gọi. Nó không thay thành `vi` khi đọc `button.save` và không thay thành `Locale.ROOT` khi đọc `help`.

Từ Java 9, tệp `.properties` được `PropertyResourceBundle` đọc với hỗ trợ UTF-8 mặc định (có cơ chế tương thích Latin-1); nên quản lý encoding của tệp và terminal nhất quán để quan sát chữ tiếng Việt đúng.

## 6. Khi bundle cụ thể không tồn tại: chọn bundle thay đổi, cách đọc key vẫn giống nhau

Giữ ví dụ phần 5 nhưng **không đóng gói** `Messages_vi_VN.properties`; chỉ còn base và `Messages_vi.properties`. Chạy cùng mã sẽ có sự thay đổi:

- `getBundle("Messages", vi-VN, control)` trả `Messages_vi`, vì đây là bundle cụ thể nhất còn có sẵn.
- `bundle.getLocale().toLanguageTag()` là `vi`.
- `title` nay trở thành `Tiêu đề tiếng Việt` từ bundle `vi`.
- `button.save` vẫn là `Lưu` từ `vi`.
- `help` vẫn lấy từ base thông qua parent.

Không có chuyện `getString("title")` tự tìm thấy `Messages_vi_VN` “ở đâu đó”; bundle chuyên biệt ấy đã vắng mặt ngay ở bước đầu. Ngược lại, nếu bundle cụ thể **có tồn tại** nhưng thiếu key `title`, nó vẫn có thể được chọn, rồi `getString` mới tìm `title` ở parent.

Hai tình huống dễ trộn lẫn:

```text
Tình huống A — thiếu tệp Messages_vi_VN:
  getBundle(vi-VN)  -> trả Messages_vi
  getString(title) -> đọc tại Messages_vi

Tình huống B — có tệp Messages_vi_VN nhưng thiếu key title:
  getBundle(vi-VN)  -> trả Messages_vi_VN
  getString(title) -> tìm ở Messages_vi (parent)
```

Trong hai tình huống, màn hình có thể hiển thị cùng chuỗi, nhưng **nguồn gốc và chẩn đoán khác nhau**. `getLocale()` giúp phân biệt bundle được chọn, song **không chỉ ra chính xác tệp chứa mỗi key**.

## 7. Bundle sibling không nằm trong chuỗi cha

Một ví dụ khác:

```text
Messages.properties
Messages_vi.properties
Messages_vi_VN.properties
Messages_en_US.properties
```

Giả sử key `account.delete` chỉ có trong `Messages_en_US.properties`, không có ở ba tệp còn lại. Sau khi tải `Messages_vi_VN` và gọi:

```java
bundle.getString("account.delete");
```

Java **không** tìm `Messages_en_US` chỉ vì đó là nơi duy nhất có key. `Messages_en_US` là bundle cho một locale khác, không phải parent của `Messages_vi_VN` trong chuỗi `vi_VN → vi → base`. Kết quả là `MissingResourceException`.

Nếu hệ thống muốn fallback một key sang tiếng Anh, cần **thiết kế chính sách** để chuỗi fallback nội dung phù hợp: ví dụ đặt key mặc định trong base tiếng Anh, hoặc có message resolver ở tầng ứng dụng chủ động tra nhiều nguồn. Không tuyên bố rằng Java mặc định tra hết mọi ngôn ngữ đến khi tìm thấy key.

Tương tự, nếu có `Messages_fr.properties` và `Messages_de.properties`, việc thiếu một key trong `fr` không kích hoạt việc thử `de`. Java tra parent chain của `fr`, không duyệt ngẫu nhiên mọi bản dịch tồn tại.

## 8. Một loại fallback nữa: JVM default khi chọn bundle

Để tách rõ hơn, xem tình huống yêu cầu `fr-CA` nhưng không có tệp tiếng Pháp. JVM default locale là `en-US`, bộ tài nguyên:

```text
Messages.properties
Messages_en_US.properties
```

Với overload mặc định:

```java
ResourceBundle bundle =
        ResourceBundle.getBundle(
                "Messages", Locale.forLanguageTag("fr-CA"));
```

Java có thể thử ứng viên `fr_CA`, `fr`; khi không có bundle phù hợp không phải base, nó thử ứng viên theo default locale JVM `en-US` rồi chọn `Messages_en_US`. Sau đó, khi gọi `bundle.getString(key)`, Java tìm key trong `Messages_en_US` rồi parent chain của bundle ấy (thường là base). Nó **không quay lại chuỗi `fr_CA → fr`** vì đang đọc một key.

Đây là **fallback của quá trình tìm bundle**, khác với fallback key. Sự khác biệt có ý nghĩa thực tế: phụ thuộc `Locale.getDefault()` của máy chủ có thể khiến cùng yêu cầu hiển thị ngôn ngữ khác nhau ở hai môi trường triển khai.

Nếu app đã tự chọn locale hỗ trợ phù hợp trước khi gọi `getBundle` và cung cấp đủ tệp, bước JVM fallback có thể không xảy ra. Với ứng dụng muốn tránh hẳn fallback sang default JVM trên classpath, Java có `Control` chuyên dụng:

```java
ResourceBundle.Control noJvmDefaultFallback =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle bundle =
        ResourceBundle.getBundle(
                "Messages", Locale.forLanguageTag("fr-CA"),
                noJvmDefaultFallback);
```

`getNoFallbackControl` khiến `Control.getFallbackLocale(...)` trả `null`, nghĩa là **không thử locale mặc định JVM**. Nó **không vô hiệu hóa** các ứng viên `fr_CA → fr → base`, cũng **không vô hiệu hóa** việc tìm key ở parent. Với bộ tệp nói trên và có base, phương thức này trả base. Nếu không có bundle nào, nó vẫn có thể ném `MissingResourceException`.

**Giới hạn Java Module System:** Các overload `ResourceBundle.getBundle(..., ResourceBundle.Control)` dành cho code trong unnamed module / classpath; gọi từ named module không được hỗ trợ và có thể ném `UnsupportedOperationException`. Với named module, tìm hiểu `ResourceBundleProvider` và cơ chế tài nguyên module phù hợp. Những ví dụ dùng `Control` ở đây được thiết kế để chạy trên classpath.

## 9. Ví dụ chạy được: “key chỉ có ở sibling” không cứu được request

Tạo các tệp:

```text
SiblingDemo.java
Catalog.properties
Catalog_vi.properties
Catalog_en_US.properties
```

**`Catalog.properties`**

```properties
title=Catalog
```

**`Catalog_vi.properties`**

```properties
title=Danh mục
```

**`Catalog_en_US.properties`**

```properties
title=Catalog for US
action.checkout=Checkout
```

**`SiblingDemo.java`**

```java
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;

public class SiblingDemo {
    public static void main(String[] args) {
        Locale vietnamese = Locale.forLanguageTag("vi-VN");

        ResourceBundle.Control control =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        ResourceBundle bundle =
                ResourceBundle.getBundle("Catalog", vietnamese, control);

        System.out.println("selected=" + bundle.getLocale().toLanguageTag());
        System.out.println("title=" + bundle.getString("title"));
        System.out.println("has.checkout=" +
                bundle.containsKey("action.checkout"));

        try {
            System.out.println(bundle.getString("action.checkout"));
        } catch (MissingResourceException ex) {
            System.out.println("checkout=MissingResourceException");
        }

        ResourceBundle us =
                ResourceBundle.getBundle("Catalog", Locale.US, control);
        System.out.println("us.checkout=" + us.getString("action.checkout"));
    }
}
```

Chạy với JDK 17+:

```bash
javac -encoding UTF-8 SiblingDemo.java
java -cp . SiblingDemo
```

Stdout khi terminal hiển thị UTF-8:

```text
selected=vi
title=Danh mục
has.checkout=false
checkout=MissingResourceException
us.checkout=Checkout
```

Đọc kết quả theo đúng hai giai đoạn:

1. Với `vi-VN`, không có `Catalog_vi_VN` nên **tìm bundle** chọn `Catalog_vi`.
2. Trong parent chain của `Catalog_vi` có base `Catalog`, nhưng cả hai không có `action.checkout`. **Tìm key** thất bại.
3. `Catalog_en_US` lại có khóa đó, nhưng là **sibling**, không nằm trong chuỗi cha của `Catalog_vi`.
4. Chỉ khi thực hiện một lời gọi `getBundle("Catalog", Locale.US, control)` **riêng biệt**, ứng dụng mới tải bundle tiếng Anh và lấy được `Checkout`.

Đây là lý do không nên dùng việc “có key trong một tệp dịch bất kỳ” làm bằng chứng rằng tất cả locale được hỗ trợ đều hiển thị được key ấy.

## 10. Phân tích tên API và phạm vi thông tin chúng cung cấp

### `bundle.getLocale()`

Trả về locale của bundle đã chọn. Hữu ích để kiểm tra có phải Java dùng `vi_VN`, `vi`, base hay fallback JVM. Nhưng nếu key đọc từ parent, `getLocale()` **vẫn là locale của đối tượng bundle hiện tại**; API không đổi locale cho từng key.

### `bundle.containsKey(key)`

Trả `true` nếu key nằm trong bundle này **hoặc parent**. Không dùng làm test khẳng định “bản dịch riêng của `vi_VN` chứa key”. Nếu cần kiểm tra sự đầy đủ của từng tệp dịch, hãy đọc/so sánh nội dung nguồn tài nguyên hoặc dùng tooling kiểm định riêng. `keySet()` và `getKeys()` cũng bao gồm parent.

### `getString(key)` và `getObject(key)`

Chúng đọc giá trị theo chuỗi cha; không có tham số locale và không phát sinh một bước tìm bundle khác chỉ vì thiếu key. `getString` đòi kiểu giá trị là `String`, trong khi `getObject` có thể trả kiểu khác nếu bundle lưu object.

### `ResourceBundle.Control.getCandidateLocales(...)`

Cho biết các locale *ứng viên* của giai đoạn tìm bundle, chứ không phải danh sách bundle thực sự có mặt, và càng không phải danh sách parent mà từng key đã đi qua. Cách tạo ứng viên phức tạp hơn khi locale có script/variant. `Control` còn cho phép điều chỉnh format và fallback locale trên classpath, nhưng một custom control phải bảo đảm tính nhất quán và thread-safety.

### Cache và nguồn tài nguyên

`ResourceBundle` thường cache các bundle đã nạp. Nếu thay tệp `.properties` khi ứng dụng đang chạy, lời gọi kế tiếp có thể nhận bản cache; cơ chế `clearCache`, TTL hoặc triển khai lại cần được quản lý phù hợp. Việc cache **không làm gộp** hai giai đoạn chọn bundle và đọc key thành một.

## 11. Hệ quả khi phát triển ứng dụng đa ngôn ngữ

### 11.1. Tách locale ứng dụng và bundle được chọn

Ứng dụng xác định locale hiển thị từ sở thích người dùng, danh sách hỗ trợ và fallback sản phẩm. Khi đã quyết định `uiLocale`, gọi `getBundle(..., uiLocale)`. Nếu trả bundle `vi` cho `uiLocale=vi-VN`, điều đó không có nghĩa phải giảm locale formatter xuống `vi`: vẫn có thể dùng `vi-VN` cho số và ngày, và dùng `ZoneId` riêng cho giờ.

Không dùng `Locale.setDefault(...)` ở mỗi HTTP request vì nó thay đổi default của cả JVM và có thể ảnh hưởng request khác. Truyền locale tường minh.

### 11.2. Kiểm soát độ phủ bản dịch theo từng locale

Với giao diện quan trọng, “tải bundle thành công” **không** có nghĩa đủ bản dịch. Một bundle chuyên biệt thậm chí không cần chứa bất kỳ key nào của màn hình đang xem; khi đó toàn bộ màn hình có thể được hiển thị từ parent.

Cần kiểm tra:

- Mọi key giao diện quan trọng có mặt trong base và các bản dịch được yêu cầu đủ độ phủ.
- Placeholder như `{0}`, `{1}` tương thích giữa các locale, không thiếu hoặc đổi nghĩa.
- Key được phép kế thừa từ parent theo chính sách nào; có chấp nhận màn hình trộn ngôn ngữ hay không.
- Khi thiếu key ở mọi mức, ứng dụng ghi nhận lỗi ở bước đọc key, không âm thầm dùng key làm nội dung hiển thị nếu sản phẩm chưa định nghĩa hành vi đó.
- Các trường hợp script, region và locale mặc định máy chủ được kiểm thử đúng với vùng hỗ trợ thực tế.

### 11.3. Phân biệt “fallback do thiết kế” và “lộ nội dung từ base”

Ví dụ `Messages.properties` bằng tiếng Anh, `Messages_vi.properties` dịch chưa hết. Khi `getString("button.save")` trả “Save” ở màn hình `vi-VN`, đó là **kế thừa key từ base**, không phải Java đã chọn locale `en-US`. Nếu yêu cầu sản phẩm là tiếng Việt hoàn toàn, việc nên làm là bổ sung key ở bundle Việt hoặc kiểm định thất bại khi build. Đổi `uiLocale` theo `bundle.getLocale()` sẽ không sửa được nguyên nhân.

### 11.4. Quan sát lỗi đủ ngữ cảnh

Khi gặp `MissingResourceException`, cần ghi lại bối cảnh theo loại:

```text
BUNDLE_NOT_FOUND
  baseName=Messages
  requestedLocale=vi-VN
  source=ResourceBundle.getBundle(...)

KEY_NOT_FOUND
  baseName=Messages
  requestedLocale=vi-VN
  resolvedBundleLocale=vi
  key=button.save
  source=bundle.getString(...)
```

Đây là **dạng log gợi ý**, không phải lỗi tự động do Java tạo đúng những tên trường trên. Không cần log dữ liệu cá nhân hay toàn bộ nội dung người dùng để chẩn đoán.

## 12. Những ngộ nhận phổ biến

| Ngộ nhận | Sửa lại |
| --- | --- |
| “Java tìm tệp có key trước, rồi mới chọn bundle.” | `getBundle` chọn bundle độc lập với key sẽ đọc sau này. |
| “Không có `vi_VN` và key thiếu trong `vi_VN` là một tình huống.” | Thiếu bundle xảy ra lúc tải; thiếu key xảy ra lúc đọc qua parent. |
| “Có key trong `en_US` thì `getString` từ `vi` sẽ tự lấy.” | Không; sibling không thuộc parent chain. |
| “`getLocale()` đổi thành locale của parent vừa trả key.” | Không; nó cho locale của bundle đang giữ. |
| “`containsKey` cho biết key được khai báo trong tệp cụ thể hiện tại.” | Nó tính cả parent. |
| “`getNoFallbackControl` cấm mọi dạng fallback.” | Nó chặn fallback sang locale do `getFallbackLocale` cung cấp, không chặn candidate/base/parent. |
| “Base bundle luôn được trả trước JVM default.” | Với chiến lược mặc định, Java có thể thử bundle của default JVM trước khi chọn base. |
| “Đã tải bundle là sẽ không bao giờ thiếu key.” | `getString` vẫn có thể ném `MissingResourceException`. |
| “Nhiều locale dùng chung một JVM thì có thể set default mỗi request.” | Default JVM mang tính toàn tiến trình; truyền locale theo yêu cầu. |
| “Mọi ứng dụng đều dùng `Control` được.” | Overload nhận `Control` không được hỗ trợ khi gọi từ named module. |

## 13. Kiểm thử và bài tập thực hành

### Tình huống A — khuyết bản theo khu vực

Giả sử chỉ có `Labels.properties` và `Labels_vi.properties`, yêu cầu `vi-VN`. Java chọn bundle nào? Nếu `Labels_vi.properties` thiếu key `help` nhưng base có thì kết quả ra sao?

**Đáp án:** `getBundle` thường trả `Labels_vi`; `getString("help")` lấy từ base qua parent.

### Tình huống B — bundle đầy đủ nhưng thiếu một key

Có `Labels_vi_VN.properties` với key `title`, trong khi `Labels_vi.properties` có `save`. Có nên nói rằng ứng dụng đã chuyển sang `vi` khi người dùng bấm nút Save?

**Đáp án:** Không. Bundle được trả là `vi-VN`, key `save` lấy từ parent `vi`. `bundle.getLocale()` vẫn là `vi-VN`.

### Tình huống C — thiếu key ở toàn bộ chuỗi

Có `Labels_en_US.properties` chứa `delete`, nhưng bundle được chọn `Labels_vi` và base đều không chứa `delete`. `getString("delete")` có tra `en_US` không?

**Đáp án:** Không. Nó ném `MissingResourceException` vì `en_US` không phải parent của `vi`. Muốn tra riêng bundle `en_US` phải chủ động tải nó bằng logic khác.

### Tình huống D — default JVM can thiệp

Máy chủ default `en-US`, yêu cầu `fr-FR`, có base và `Labels_en_US.properties`, không có bản Pháp. Java có thể chọn `en-US` trong bước nào?

**Đáp án:** Trong **tìm bundle**, với chiến lược mặc định có nhánh thử default JVM. Việc tìm key bắt đầu sau khi bundle đã được chọn, đi theo chuỗi parent của bundle kết quả.

### Tình huống E — kiểm tra độ phủ

`bundle.containsKey("submit")` là `true` nhưng tệp bản dịch chuyên biệt thiếu key. Test thế nào để bắt thiếu bản dịch?

**Đáp án:** So sánh tập khóa **khai báo trực tiếp** trong từng nguồn tài nguyên với tập khóa chuẩn hoặc yêu cầu coverage, thay vì dựa riêng `containsKey`/`keySet` vốn tính cả parent.

### Bài tập mở rộng

Giữ ví dụ `BundleChainDemo` rồi làm theo thứ tự:

1. Xóa **chỉ khỏi bộ tài nguyên được chạy** tệp `Messages_vi_VN.properties`; quan sát `selected` chuyển từ `vi-VN` sang `vi`.
2. Thêm lại tệp `vi_VN` nhưng bỏ key `title`; quan sát `selected` vẫn là `vi-VN`, còn `title` lấy từ `vi`.
3. Thêm `Messages_en_US.properties` chỉ có key `unknown`; kiểm tra `bundle.getString("unknown")` từ `vi-VN` vẫn ném lỗi.
4. Chỉ định `Locale.getDefault()` khác nhau trong một chương trình thử nghiệm cô lập và so sánh chiến lược mặc định với `getNoFallbackControl`; không làm điều này trong request server đa luồng.

Các kết quả phải được diễn giải bằng **hai câu hỏi tách biệt**: “bundle nào được chọn?” và “key nằm ở mức nào trong parent chain?”.

## 14. Kết luận

**Tìm bundle** trả lời “họ tài nguyên này có bản nào phù hợp với locale đang yêu cầu?”. **Tìm key** trả lời “trong bundle đã tải hoặc các bundle cha của nó, giá trị gần nhất cho key này là gì?”. Hai giai đoạn có thể cùng liên quan đến `vi_VN → vi → base`, nhưng việc thiếu tệp và thiếu key tạo ra hành vi khác nhau; key ở bundle của ngôn ngữ khác không tự được tìm kiếm.

Khi thiết kế localization Java, hãy giữ locale ứng dụng tường minh, hiểu đúng candidate/base/default-JVM fallback, kiểm tra độ phủ từng bản dịch, và dùng `bundle.getLocale()` để chẩn đoán bundle được chọn chứ không suy ra nguồn của từng key.

**Tài liệu tham khảo (Java 17):**

- [Oracle JDK 17 — `ResourceBundle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html): `getBundle`, `getObject`, `getString`, `getLocale` và cơ chế nạp bundle.
- [Oracle JDK 17 — `ResourceBundle.Control`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html): candidate locales, formats và `getNoFallbackControl`.
