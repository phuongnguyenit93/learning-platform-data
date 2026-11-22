# Tên hiển thị bằng `Locale.getDisplayName()` và locale dùng để hiển thị tên

Khi một ứng dụng Java hiển thị danh sách ngôn ngữ hoặc vùng cho người dùng lựa chọn, nó cần chuyển mã như `en-US`, `fr-CA` hay `zh-Hant-TW` thành **tên có thể đọc được**. Java cung cấp `java.util.Locale.getDisplayName()` cho nhiệm vụ đó. Điểm quan trọng nhất: **Locale được đặt tên** và **Locale dùng làm ngôn ngữ hiển thị tên** là hai vai trò khác nhau.

Ví dụ, cùng một đối tượng `Locale.forLanguageTag("de-DE")` có thể được trình bày bằng tiếng Đức trong giao diện tiếng Đức hoặc bằng tiếng Anh trong giao diện tiếng Anh. Đối tượng locale vẫn đại diện cho ngôn ngữ Đức tại Đức, chỉ có ngôn ngữ của **nhãn hiển thị** thay đổi.

## 1. Hai vai trò của Locale: đối tượng được mô tả và ngôn ngữ mô tả

Giả sử:

- **Locale đích (target / subject locale):** `fr-CA`, nghĩa là tiếng Pháp theo vùng Canada. Đây là đối tượng mà ta muốn lấy tên.
- **Locale hiển thị (display locale / inLocale):** `en-US`, nghĩa là yêu cầu Java diễn đạt tên đó bằng tiếng Anh theo quy ước địa phương được hỗ trợ.

Đoạn mã:

```java
Locale target = Locale.forLanguageTag("fr-CA");
Locale displayLocale = Locale.forLanguageTag("en-US");

String label = target.getDisplayName(displayLocale);
```

là **một đoạn mã minh họa**, cần đặt trong một phương thức và có `import java.util.Locale;` để biên dịch. Nó có nghĩa: “lấy tên của `fr-CA` để hiển thị bằng ngôn ngữ/vùng của `en-US`”. Lời gọi **không thay đổi** `target`, cũng không chuyển nội dung dịch hay vùng của đối tượng thành `en-US`.

Mô hình tư duy:

```text
Target locale:       fr-CA        (Đối tượng được đặt tên)
Display locale:      en-US        (Ngôn ngữ diễn đạt nhãn)
                    ↓
target.getDisplayName(displayLocale)
                    ↓
Tên hiển thị đọc được bằng tiếng Anh, chẳng hạn French (Canada)
```

Chữ “chẳng hạn” ở trên có chủ ý: cách viết chính xác của tên hiển thị phụ thuộc dữ liệu locale/provider trong JDK.

**Phân biệt ba loại giá trị:**

| Cách lấy | Mục đích | Có phụ thuộc locale hiển thị? |
| --- | --- | --- |
| `target.toLanguageTag()` | Mã BCP 47 để lưu hoặc truyền, ví dụ `fr-CA` | Không |
| `target.getLanguage()` và `target.getCountry()` | Mã thành phần ngôn ngữ/vùng, ví dụ `fr`, `CA` | Không |
| `target.getDisplayName(displayLocale)` | Tên thân thiện với người dùng | Có: phụ thuộc `displayLocale` và dữ liệu JDK |
| `target.getDisplayName()` | Tên theo **default DISPLAY locale** của JVM | Có: phụ thuộc mặc định của tiến trình |

**Quy tắc sử dụng:** dữ liệu định danh dùng `toLanguageTag()` hoặc đối tượng `Locale`; nội dung đưa ra giao diện dùng `getDisplayName(...)`.

## 2. Hai overload của `getDisplayName`

`Locale` có hai phương thức trọng tâm:

```java
String getDisplayName();
String getDisplayName(Locale inLocale);
```

Đây là **chữ ký API minh họa**, không phải một chương trình Java độc lập.

### `getDisplayName()` — sử dụng locale mặc định để hiển thị

Phương thức không có tham số dùng **default locale của category `Locale.Category.DISPLAY`**. Vì JVM có thể chạy trên máy khác, cấu hình khác, hoặc được một phần ứng dụng thay đổi, hai lần chạy trong các môi trường khác nhau có thể tạo nhãn bằng ngôn ngữ khác nhau.

```java
Locale target = Locale.forLanguageTag("de-DE");
String label = target.getDisplayName();
```

Nếu DISPLAY default là tiếng Anh, nhãn có thể ở dạng tiếng Anh; nếu DISPLAY default là tiếng Pháp, nhãn có thể ở dạng tiếng Pháp. Đừng hiểu rằng gọi `target.getDisplayName()` đồng nghĩa với “hiển thị bằng chính ngôn ngữ Đức” hoặc “hiển thị bằng ngôn ngữ của người dùng đang truy cập”.

### `getDisplayName(Locale inLocale)` — sử dụng locale hiển thị chỉ định

Phiên bản có tham số diễn đạt tên của **đối tượng nhận lời gọi** theo locale `inLocale`. Đây thường là lựa chọn rõ ràng hơn cho một giao diện có nhiều người dùng cùng truy cập một server:

```java
Locale target = Locale.forLanguageTag("de-DE");
Locale viewer = Locale.forLanguageTag("vi-VN");
String labelForViewer = target.getDisplayName(viewer);
```

Ứng dụng có thể chuyển `viewer` sang `en-GB` hay `fr-FR` cho request khác mà không phải đổi cài đặt toàn cục. Nếu `inLocale` không có dữ liệu bản địa hóa tương ứng, JDK có thể dùng dữ liệu dự phòng, bao gồm tên từ ngôn ngữ khác hoặc mã chưa được dịch; vì vậy **không đảm bảo** mọi locale có đủ tên đẹp bằng mọi ngôn ngữ.

## 3. Ví dụ Java 17+ chạy được: một Locale, nhiều ngôn ngữ hiển thị

Tạo file `LocaleDisplayNameDemo.java`:

```java
import java.util.List;
import java.util.Locale;

public class LocaleDisplayNameDemo {
    public static void main(String[] args) {
        Locale target = Locale.forLanguageTag("fr-CA");

        Locale english = Locale.forLanguageTag("en-US");
        Locale french = Locale.forLanguageTag("fr-FR");
        Locale vietnamese = Locale.forLanguageTag("vi-VN");

        System.out.println("Stored tag: " + target.toLanguageTag());
        System.out.println("Language code: " + target.getLanguage());
        System.out.println("Region code: " + target.getCountry());

        for (Locale displayLocale : List.of(
                english, french, vietnamese)) {
            System.out.println("Display locale: "
                    + displayLocale.toLanguageTag());
            System.out.println("Display name: "
                    + target.getDisplayName(displayLocale));
        }

        System.out.println("Stored tag after display: "
                + target.toLanguageTag());
    }
}
```

Lệnh chạy tại thư mục chứa file:

```bash
javac LocaleDisplayNameDemo.java
java LocaleDisplayNameDemo
```

Những dòng **có kết quả cố định** theo giá trị được tạo trong mã:

```text
Stored tag: fr-CA
Language code: fr
Region code: CA
Display locale: en-US
Display locale: fr-FR
Display locale: vi-VN
Stored tag after display: fr-CA
```

Chương trình thực tế in thêm **ba dòng `Display name: ...`**, mỗi dòng đứng ngay sau dòng `Display locale` tương ứng. Chúng thường có ngôn ngữ khác nhau; không chép cứng một bản dịch làm stdout chung cho mọi JDK và mọi locale provider. Kết quả quan trọng phải kiểm chứng là `target.toLanguageTag()` vẫn là `fr-CA` trước và sau các lời gọi: đây là thao tác **chỉ đọc tên**, không biến đổi locale.

> Nếu cần minh họa đầu ra bằng tiếng Anh, tên như `French (Canada)` là cách biểu đạt thường gặp của `fr-CA`. Tuy nhiên chuỗi này chỉ phù hợp làm ví dụ giao diện, không phải hợp đồng API cố định xuyên mọi phiên bản/dữ liệu JDK.

## 4. Mặc định DISPLAY khác mặc định FORMAT

Java phân biệt ít nhất hai nhóm mặc định thường quan trọng đối với bản địa hóa:

- `Locale.Category.DISPLAY`: được dùng khi lấy tên hiển thị của locale thông qua các phương thức như `getDisplayName()`, `getDisplayLanguage()`, `getDisplayCountry()` không truyền tham số.
- `Locale.Category.FORMAT`: là mặc định phục vụ các API định dạng hỗ trợ locale, chẳng hạn một số thao tác định dạng số/ngày khi không truyền locale tường minh.

Không suy ra rằng “người dùng đang xem nhãn ngôn ngữ bằng tiếng Pháp” thì số, ngày hoặc tiền tệ cũng buộc phải theo quy ước Pháp. Trong một ứng dụng quốc tế, hai lựa chọn này có thể được thiết lập riêng theo yêu cầu sản phẩm.

**Ví dụ chứng minh `getDisplayName()` theo DISPLAY default** — file `DisplayCategoryDemo.java`:

```java
import java.util.Locale;

public class DisplayCategoryDemo {
    public static void main(String[] args) {
        Locale original =
                Locale.getDefault(Locale.Category.DISPLAY);
        Locale target = Locale.forLanguageTag("de-DE");

        try {
            Locale english = Locale.forLanguageTag("en-US");
            Locale french = Locale.forLanguageTag("fr-FR");

            Locale.setDefault(Locale.Category.DISPLAY, english);
            System.out.println("Default: "
                    + Locale.getDefault(
                            Locale.Category.DISPLAY).toLanguageTag());
            System.out.println("Matches explicit: "
                    + target.getDisplayName()
                            .equals(target.getDisplayName(english)));

            Locale.setDefault(Locale.Category.DISPLAY, french);
            System.out.println("Default: "
                    + Locale.getDefault(
                            Locale.Category.DISPLAY).toLanguageTag());
            System.out.println("Matches explicit: "
                    + target.getDisplayName()
                            .equals(target.getDisplayName(french)));
        } finally {
            Locale.setDefault(Locale.Category.DISPLAY, original);
        }
    }
}
```

```bash
javac DisplayCategoryDemo.java
java DisplayCategoryDemo
```

Stdout chính xác của ví dụ trong một tiến trình đơn luồng, không có tác nhân đồng thời sửa mặc định:

```text
Default: en-US
Matches explicit: true
Default: fr-FR
Matches explicit: true
```

Đoạn chương trình **cố ý thay đổi cài đặt toàn cục để minh họa** và khôi phục trong `finally`. `Locale.setDefault(...)` ảnh hưởng đến toàn tiến trình JVM, có thể gây tác động đến các luồng/request khác, vì vậy **không gọi nó theo từng request** trong web server. Trong ứng dụng thực, nhận `displayLocale` từ ngữ cảnh người dùng và truyền tường minh vào `getDisplayName(displayLocale)`.

Lưu ý thêm: `Locale.getDefault()` không có category và `Locale.getDefault(Locale.Category.DISPLAY)` là hai API có ý nghĩa khác nhau; đừng thay thế tùy tiện khi viết code phụ thuộc từng category.

## 5. Lấy tên của từng thành phần: language, script, country, variant

`getDisplayName(...)` là **tên tổng hợp** của một locale. Khi UI muốn chia riêng các trường “Ngôn ngữ”, “Hệ chữ viết”, “Khu vực”, “Biến thể”, hãy dùng các phương thức chuyên biệt:

| Thành phần | Mã kỹ thuật | Tên cho người đọc |
| --- | --- | --- |
| Ngôn ngữ | `getLanguage()` | `getDisplayLanguage(displayLocale)` |
| Hệ chữ viết | `getScript()` | `getDisplayScript(displayLocale)` |
| Vùng | `getCountry()` | `getDisplayCountry(displayLocale)` |
| Biến thể | `getVariant()` | `getDisplayVariant(displayLocale)` |
| Tên tổng hợp | `toLanguageTag()` để lấy mã | `getDisplayName(displayLocale)` |

Mỗi API tên hiển thị cũng có overload **không tham số**, trong trường hợp đó nó sử dụng default DISPLAY locale. Các phương thức riêng có thể trả chuỗi rỗng nếu thành phần chưa được khai báo, ví dụ `Locale.forLanguageTag("en").getDisplayCountry(Locale.ENGLISH)` trả chuỗi rỗng vì locale đó không có mã vùng.

**Ví dụ Java 17+** — file `LocaleComponentsDemo.java`:

```java
import java.util.Locale;

public class LocaleComponentsDemo {
    public static void main(String[] args) {
        Locale target = Locale.forLanguageTag("zh-Hant-TW");
        Locale display = Locale.ENGLISH;

        System.out.println("Tag: " + target.toLanguageTag());
        System.out.println("Language code: " + target.getLanguage());
        System.out.println("Script code: " + target.getScript());
        System.out.println("Region code: " + target.getCountry());
        System.out.println("Language label: "
                + target.getDisplayLanguage(display));
        System.out.println("Script label: "
                + target.getDisplayScript(display));
        System.out.println("Region label: "
                + target.getDisplayCountry(display));
        System.out.println("Full label: "
                + target.getDisplayName(display));
    }
}
```

```bash
javac LocaleComponentsDemo.java
java LocaleComponentsDemo
```

Ba dòng mã kỹ thuật có kết quả ổn định:

```text
Tag: zh-Hant-TW
Language code: zh
Script code: Hant
Region code: TW
```

Bốn dòng `... label:` sử dụng dữ liệu địa phương hóa của JDK và không buộc phải giống hệt nhau trên mọi môi trường. Cách gọi này hữu ích vì `getDisplayName` có thể chứa cả tên ngôn ngữ, script, vùng và variant; thành phần nào có hay không phụ thuộc cấu hình của `target`. Với những ngôn ngữ cần script để phân biệt kiểu chữ, đừng chỉ dùng `getDisplayLanguage()` rồi làm mất `Hans`/`Hant`.

**Lưu ý về variant:** variant không luôn là một tên phổ thông đã được dịch. Nếu Java không có tên bản địa hóa cho variant, giá trị dạng mã có thể xuất hiện. Unicode locale extensions và các phần mở rộng trong thẻ BCP 47 cũng không đồng nghĩa với việc `getDisplayName` sẽ cung cấp lời giải thích đầy đủ mọi lựa chọn mở rộng; thiết kế UI riêng cho các tùy chọn đặc biệt nếu cần.

## 6. Hiển thị danh sách lựa chọn ngôn ngữ đúng với người dùng

Một danh sách locale có hai kiểu nhãn thường dùng:

1. **Tên theo ngôn ngữ hiện tại của giao diện (localized name):** `option.getDisplayName(uiLocale)`, ví dụ khi giao diện dùng tiếng Việt thì các nhãn cố gắng được diễn đạt bằng tiếng Việt.
2. **Tên bằng chính ngôn ngữ mà tùy chọn đại diện (native/autonym):** `option.getDisplayName(option)`. Cách này có ích trong màn hình chọn ngôn ngữ vì người dùng chưa đọc được ngôn ngữ giao diện hiện tại vẫn có cơ hội nhận ra ngôn ngữ của mình.

Hai cách đều hợp lệ nhưng phục vụ trải nghiệm khác nhau. Với danh sách nhiều vùng cùng ngôn ngữ, giữ đủ vùng/script trong locale option và hiển thị nhãn đủ rõ để phân biệt.

**Chương trình tạo dữ liệu lựa chọn — `LanguageMenuDemo.java`:**

```java
import java.util.List;
import java.util.Locale;

public class LanguageMenuDemo {
    public static void main(String[] args) {
        Locale uiLocale = Locale.forLanguageTag("vi-VN");

        List<Locale> supported = List.of(
                Locale.forLanguageTag("en-US"),
                Locale.forLanguageTag("en-GB"),
                Locale.forLanguageTag("fr-CA"),
                Locale.forLanguageTag("de-DE"),
                Locale.forLanguageTag("zh-Hant-TW"));

        for (Locale option : supported) {
            String value = option.toLanguageTag();
            String labelForUi = option.getDisplayName(uiLocale);
            String nativeLabel = option.getDisplayName(option);

            System.out.println("value=" + value);
            System.out.println("  uiLabel=" + labelForUi);
            System.out.println("  nativeLabel=" + nativeLabel);
        }
    }
}
```

```bash
javac LanguageMenuDemo.java
java LanguageMenuDemo
```

Ví dụ in **5 nhóm**, mỗi nhóm gồm dòng `value=...` và hai dòng `uiLabel=...`, `nativeLabel=...`. Các giá trị `value=` theo đúng thứ tự:

```text
value=en-US
value=en-GB
value=fr-CA
value=de-DE
value=zh-Hant-TW
```

Trong stdout thật, sau mỗi dòng `value=` là hai nhãn được tính từ JDK. Đây không phải ví dụ có stdout liên tiếp chỉ gồm 5 dòng ở trên. Khi người dùng chọn một tùy chọn, **lưu `value` là thẻ ngôn ngữ**, không lưu `uiLabel` hoặc `nativeLabel`: nhãn có thể đổi khi chuyển ngôn ngữ UI hoặc nâng cấp dữ liệu JDK.

### Có nên dùng `option.getDisplayName(option)` cho mọi menu?

Không nhất thiết. Nhãn tự thân (autonym) hữu ích nhưng có các giới hạn:

- Nếu dữ liệu tên hiển thị bằng chính ngôn ngữ đó chưa đủ, nhãn có thể fallback sang tên hoặc mã khác.
- Cùng ngôn ngữ nhưng nhiều vùng có thể khó phân biệt nếu UI chỉ hiện `getDisplayLanguage`; hãy bao gồm vùng hoặc script.
- Khi cần tuân thủ cách đặt tên thương hiệu, chính sách sản phẩm, hoặc tên gọi nhạy cảm theo từng thị trường, ứng dụng có thể duy trì **bảng nhãn đã được biên tập**. `getDisplayName` cung cấp dữ liệu chuẩn của runtime, không thay thế phê duyệt nội dung giao diện.
- Các script khác nhau yêu cầu font hỗ trợ và khả năng hiển thị ký tự; tên được trả về đúng chưa đảm bảo hệ thống có font hiển thị được.

## 7. Không dùng tên hiển thị làm mã định danh hoặc logic xử lý

Xét ba nhiệm vụ hoàn toàn khác:

| Nhiệm vụ | API/dữ liệu phù hợp | Vì sao? |
| --- | --- | --- |
| Ghi giá trị form cho lựa chọn `en-GB` | `locale.toLanguageTag()` | Mã ổn định hơn tên bản địa hóa |
| Hiển thị nhãn cho người dùng dùng `vi-VN` | `locale.getDisplayName(uiLocale)` | Nhãn phù hợp ngôn ngữ giao diện |
| Kiểm tra chọn đúng vùng `GB` | `locale.getCountry()` hoặc so sánh locale | Không phụ thuộc bản dịch hoặc cách viết tên quốc gia |

Không parse chuỗi kết quả `getDisplayName()` để lấy mã vùng. Định dạng tên tổng hợp (cách dùng dấu ngoặc, dấu phẩy, thứ tự vùng/script...) có thể thay đổi theo dữ liệu locale. Đồng thời, không dùng `getDisplayName` làm khóa của `Map`, khóa database, route, API query hoặc giá trị `<option value>` trong HTML.

Ví dụ sai ở cấp ý tưởng:

```java
// Sai về thiết kế: label dịch sang ngôn ngữ khác sẽ làm mất khóa ổn định.
String savedLocale = option.getDisplayName(uiLocale);
```

Cách thiết kế đúng cho dữ liệu bền vững:

```java
// Lưu tag; mỗi lần render có thể tạo label với locale người xem.
String savedLocale = option.toLanguageTag();
Locale restored = Locale.forLanguageTag(savedLocale);
String label = restored.getDisplayName(uiLocale);
```

Hai đoạn trên cần được dùng **bên trong ngữ cảnh đã khai báo** `option` và `uiLocale`; chúng chỉ minh họa cách chọn dữ liệu, không phải file Java độc lập.

## 8. Các giới hạn của tên hiển thị từ JDK

### Phụ thuộc dữ liệu địa phương hóa của runtime

Java có nhiều bộ dữ liệu locale, phiên bản JDK và cấu hình locale provider khác nhau. Bản dịch, cách viết tên vùng, cách sắp xếp thành phần của tên có thể thay đổi. Một bản kiểm thử snapshot so sánh **chính xác** chuỗi `getDisplayName(Locale)` đôi khi thất bại khi đổi JDK hoặc locale provider dù code ứng dụng vẫn đúng.

Để kiểm thử bền vững, kiểm tra các thuộc tính không phụ thuộc văn phong dịch (ví dụ thẻ lưu lại giống ban đầu, nhãn không rỗng cho các locale đã lựa chọn, UI sử dụng đúng display locale). Khi sản phẩm buộc phải có nhãn chính xác, lưu nhãn do ứng dụng kiểm soát và kiểm thử bảng nhãn đó. Không gọi `Locale.getAvailableLocales()` rồi suy ra ứng dụng tự có bản dịch giao diện cho tất cả: danh sách locale runtime có dữ liệu hỗ trợ **không phải** danh sách locale nội dung ứng dụng đã dịch.

### Phân biệt tên ngôn ngữ và mã ngôn ngữ

`getDisplayLanguage(displayLocale)` có thể trả tên ngôn ngữ nhưng **không hiển thị đầy đủ** script và vùng. Ví dụ, hai lựa chọn `en-US` / `en-GB` có cùng tên ngôn ngữ khi diễn đạt bằng tiếng Anh, trong khi toàn bộ `getDisplayName(displayLocale)` giúp trình bày thêm vùng để phân biệt. Nếu mục tiêu là một menu chọn ngôn ngữ và vùng, kiểm tra từng locale thực tế và bổ sung chú giải có kiểm soát nếu nhãn quá giống nhau.

### Không nhầm locale hiển thị với locale định dạng

Một người dùng có thể xem tên ngôn ngữ bằng tiếng Việt nhưng định dạng tiền/ngày theo quy ước của thị trường khác. `getDisplayName(uiLocale)` chỉ xác định **ngôn ngữ dùng để gọi tên locale** trong trường hợp này; không cần và không nên ép toàn bộ formatter chuyển sang `uiLocale` nếu chính sách của ứng dụng yêu cầu locale định dạng khác. Múi giờ cũng là cấu hình riêng (`ZoneId`), không được suy ra từ `getDisplayName`.

### Không xem tên hiển thị là công cụ dịch văn bản bất kỳ

`getDisplayName` chỉ trả tên bản địa hóa của **đối tượng Locale**, không dịch thông điệp tự do như câu chào hay nội dung trang. Tài nguyên dịch UI cần nguồn thông điệp thích hợp, chẳng hạn `ResourceBundle` hoặc hệ thống i18n được ứng dụng sử dụng. Một locale hợp lệ không đảm bảo ứng dụng có sẵn bản dịch cho nó.

## 9. Kiểm thử và thực hành

**Bộ kiểm thử khái niệm nên bao gồm:**

- **Hai display locale cho một target:** với `fr-CA`, lấy tên theo `en-US` và `fr-FR`; xác minh locale đích giữ nguyên `fr-CA` và nhãn hướng tới đúng ngôn ngữ mong muốn.
- **Hai vùng cùng ngôn ngữ:** `en-US`, `en-GB`; đảm bảo mã lưu khác nhau, UI có thể phân biệt chúng và không bỏ thông tin vùng.
- **Trường hợp có script:** `zh-Hans-CN` và `zh-Hant-TW`; xác minh thẻ bảo toàn script và nhãn UI đủ rõ.
- **Locale không có vùng:** `fr`; `getDisplayCountry(Locale.ENGLISH)` phải rỗng và UI không tự bịa vùng.
- **Default DISPLAY:** minh họa `getDisplayName()` sử dụng default DISPLAY category; code sản phẩm chuyển sang overload có tham số để tránh phụ thuộc global.
- **Đổi ngôn ngữ giao diện:** khi `uiLocale` thay đổi, các giá trị `value=` giữ nguyên; chỉ cập nhật nhãn.
- **Runtime khác nhau:** tránh kiểm thử tên dịch cố định xuyên JDK/provider khi sản phẩm không có cam kết về văn bản chính xác.

### Bài tập 1: Nhãn theo giao diện và nhãn tự thân

Tạo danh sách gồm `pt-BR`, `pt-PT`, `es-ES`, `es-MX`. Đặt `uiLocale` lần lượt là `vi-VN` và `en-US`. Với mỗi locale, in mã `toLanguageTag()`, nhãn `getDisplayName(uiLocale)` và nhãn `getDisplayName(option)`. Trả lời:

1. Mã nào không đổi khi đổi ngôn ngữ giao diện?
2. Có thể suy ra mã vùng chính xác bằng cách phân tích tên hiển thị không?
3. Khi nào nên hiển thị cả nhãn ngôn ngữ giao diện và nhãn tự thân?

**Gợi ý:** dựa trên vòng lặp của `LanguageMenuDemo`. Nhãn là dữ liệu trình bày; mã BCP 47 giữ vai trò nhận diện lựa chọn.

### Bài tập 2: Tránh phụ thuộc locale mặc định

Một dịch vụ web có nhiều người dùng cùng truy cập. Đoạn sau có thiết kế không ổn:

```java
Locale regionChoice = Locale.forLanguageTag("fr-CA");
String name = regionChoice.getDisplayName();
```

Nếu request của người dùng A dùng tiếng Anh, người dùng B dùng tiếng Việt, và máy chủ thay đổi DISPLAY default, tên hiển thị có thể không phản ánh ngôn ngữ của từng người. Thay bằng:

```java
Locale regionChoice = Locale.forLanguageTag("fr-CA");
Locale uiLocale = Locale.forLanguageTag("vi-VN"); // Ví dụ lấy từ user/request
String name = regionChoice.getDisplayName(uiLocale);
```

Trong thực tế, `uiLocale` phải đến từ cài đặt/ngữ cảnh hợp lệ của **request hiện tại** hoặc chính sách ứng dụng; hai đoạn này là ví dụ trong một phương thức, không phải chương trình độc lập. Không dùng `Locale.setDefault` theo request.

## 10. Ghi nhớ

- **`getDisplayName()`** lấy tên theo **default `Locale.Category.DISPLAY`** của JVM; kết quả có thể khác khi môi trường mặc định thay đổi.
- **`getDisplayName(inLocale)`** lấy tên của locale đích, nhưng được diễn đạt theo **locale hiển thị chỉ định**. Đây là API nên dùng cho các UI có locale người xem rõ ràng.
- **`getDisplayName(locale)`** là tên tổng hợp; `getDisplayLanguage/Script/Country/Variant(locale)` phục vụ nhãn của từng thành phần.
- **`getDisplayName(option)`** giúp hiển thị tên bằng ngôn ngữ của chính tùy chọn, hữu ích cho menu chọn ngôn ngữ, nhưng vẫn cần kiểm tra fallback, script và vùng.
- **`toLanguageTag()` là mã định danh để lưu/truyền**, còn tên hiển thị chỉ dành cho người đọc. Không dùng bản dịch của tên làm ID.
- Nội dung tên phụ thuộc dữ liệu locale/provider của JDK; kiểm thử đúng ý nghĩa và kiểm soát nhãn bằng tài nguyên ứng dụng khi cần văn bản cố định.

Khi cần diễn đạt một locale cho người dùng, luôn hỏi đủ hai câu: **đang gọi tên locale nào?** và **muốn tên đó bằng ngôn ngữ của ai?**. Hai câu trả lời tương ứng với đối tượng nhận `getDisplayName` và tham số `inLocale`.