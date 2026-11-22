# Hai nhóm `Locale.Category.DISPLAY` và `Locale.Category.FORMAT` trong Java

Trong một ứng dụng đa ngôn ngữ, người dùng có thể muốn **đọc tên các ngôn ngữ/quốc gia bằng tiếng Việt** nhưng **hiển thị số, ngày tháng theo quy ước của Đức**. Hai nhu cầu này không nhất thiết phải dùng cùng một `Locale`. Java cung cấp hai nhóm mặc định trong `java.util.Locale.Category`: `DISPLAY` và `FORMAT`.

Điểm cốt lõi của bài học: **`DISPLAY` điều khiển locale mặc định cho các thao tác tạo tên hiển thị**, còn **`FORMAT` điều khiển locale mặc định cho các thao tác định dạng được thiết kế sử dụng nhóm này**. Cả hai đều là cài đặt mặc định **cấp JVM**, không phải cấu hình riêng cho mỗi người dùng hay mỗi HTTP request.

## 1. Vì sao Java cần hai nhóm mặc định?

Hãy xét một màn hình cài đặt có các phần sau:

- Danh sách quốc gia/ngôn ngữ: `Germany`, `France`, `Vietnamese` hoặc các tên tương đương bằng ngôn ngữ giao diện.
- Một giá trị số: `12345.67`, có thể hiển thị bằng dấu phân cách phần nghìn/thập phân theo vùng.
- Một ngày: 28/10/2026, có thể được trình bày bằng thứ tự, cách viết và ký hiệu phù hợp với vùng.

Ngôn ngữ dùng để **gọi tên** một quốc gia là một lựa chọn; quy tắc dùng để **trình bày** số và ngày là một lựa chọn khác. Một JVM cũng có **default locale tổng quát** cho các API không chỉ định category. Do đó, phải biết lời gọi nào thật sự lấy default nào.

| Giá trị/default | API đọc | Mục đích chính | Ví dụ sử dụng |
| --- | --- | --- | --- |
| **Mặc định tổng quát** (không category) | `Locale.getDefault()` | Default chung cho API sử dụng mặc định tổng quát | `ResourceBundle.getBundle("messages")` dùng default tổng quát khi không truyền locale |
| **DISPLAY** | `Locale.getDefault(Locale.Category.DISPLAY)` | Ngôn ngữ/vùng ưu tiên để *diễn đạt tên* trong các API tên hiển thị | `target.getDisplayName()`, `getDisplayLanguage()`, `getDisplayCountry()` |
| **FORMAT** | `Locale.getDefault(Locale.Category.FORMAT)` | Quy ước địa phương ưu tiên khi *định dạng* qua API có hỗ trợ | `NumberFormat.getNumberInstance()`, `NumberFormat.getCurrencyInstance()` |

`Locale.Category` là một enum có hai hằng `DISPLAY` và `FORMAT`. Chúng **phân loại mục đích dùng default**, không phải hai kiểu đối tượng locale mới: cả ba lệnh `getDefault(...)` vẫn trả về đối tượng `Locale` thông thường.

### Nhìn dưới dạng luồng lựa chọn

```text
                 JVM
                  |
        +---------+----------+
        |         |          |
 general default  DISPLAY    FORMAT
        |         |          |
  API dùng      Tên ngôn    Số, tiền,
  default       ngữ/vùng    ngày tháng
  tổng quát     hiển thị    (API tương ứng)
        |         |          |
  getDefault()  getDisplayName()  NumberFormat.getNumberInstance()
```

Không phải API nào có yếu tố bản địa hóa cũng đương nhiên dùng `DISPLAY` hoặc `FORMAT`. Phải xem hợp đồng của **từng phương thức**. Nếu truyền `Locale` tường minh, API thường ưu tiên đối tượng được truyền thay vì các default toàn cục.

## 2. Đọc default của từng nhóm

Ba lời gọi dưới đây có thể trả về **ba locale khác nhau**:

```java
Locale base = Locale.getDefault();

Locale display = Locale.getDefault(
        Locale.Category.DISPLAY);

Locale format = Locale.getDefault(
        Locale.Category.FORMAT);
```

Đây là **đoạn mã trong một phương thức**, cần `import java.util.Locale;`. Không dùng `Locale.getDefault()` như một bí danh chắc chắn cho `Locale.getDefault(Locale.Category.FORMAT)` hoặc `DISPLAY`: chúng có thể trùng nhau trong một môi trường, nhưng không có yêu cầu phải luôn trùng nhau.

Chương trình Java 17+ in ra ba locale đang hoạt động — file `InspectDefaultLocale.java`:

```java
import java.util.Locale;

public class InspectDefaultLocale {
    public static void main(String[] args) {
        Locale general = Locale.getDefault();
        Locale display = Locale.getDefault(
                Locale.Category.DISPLAY);
        Locale format = Locale.getDefault(
                Locale.Category.FORMAT);

        System.out.println("General: " + general.toLanguageTag());
        System.out.println("DISPLAY: " + display.toLanguageTag());
        System.out.println("FORMAT: " + format.toLanguageTag());
        System.out.println("DISPLAY == FORMAT: "
                + display.equals(format));
    }
}
```

```bash
javac InspectDefaultLocale.java
java InspectDefaultLocale
```

Ví dụ **không có stdout cố định** vì default được JVM thiết lập khi khởi động dựa trên cấu hình máy chủ/môi trường. Một máy có thể in ra cùng thẻ cho cả ba dòng; máy khác có thể khác nhau. Dòng cuối là phép so sánh giá trị `Locale`, không so sánh object identity bằng `==`.

Khi cần kiểm tra thực trạng trên server, luôn quan sát từng category trực tiếp. Đừng kết luận `DISPLAY` và `FORMAT` giống nhau chỉ vì `Locale.getDefault()` trả một giá trị quen thuộc.

## 3. DISPLAY: ngôn ngữ diễn đạt tên của Locale

Đối tượng cần lấy tên và locale dùng để diễn đạt tên là **hai vai trò khác nhau**:

```java
Locale target = Locale.forLanguageTag("ja-JP");
Locale uiLocale = Locale.forLanguageTag("vi-VN");

String implicitLabel = target.getDisplayName();
String explicitLabel = target.getDisplayName(uiLocale);
```

- `target` là locale được gọi tên: tiếng Nhật ở Nhật Bản.
- `target.getDisplayName()` mặc định diễn đạt tên bằng `Locale.getDefault(Locale.Category.DISPLAY)`.
- `target.getDisplayName(uiLocale)` diễn đạt tên bằng `vi-VN` theo dữ liệu bản địa hóa của runtime, **không phụ thuộc** default DISPLAY hiện hành.
- Cả hai chỉ lấy chuỗi để hiển thị; chúng **không đổi** `target` và không biến locale Nhật thành locale Việt.

Cùng nhóm phương thức không tham số: `getDisplayLanguage()`, `getDisplayScript()`, `getDisplayCountry()`, `getDisplayVariant()`. Các overload có tham số `Locale inLocale` cho phép chọn ngôn ngữ hiển thị cụ thể.

**Lưu ý:** nhãn hiển thị có thể khác nhau theo bản JDK, locale provider/dữ liệu CLDR và fallback nếu không có bản dịch. Giá trị `getDisplayName()` là **dữ liệu trình bày**, không nên dùng làm ID, khóa database hoặc giá trị lâu dài của một tùy chọn. Lưu thẻ `target.toLanguageTag()` khi cần định danh.

### Ví dụ

Giả sử DISPLAY default là `en-US` và `target` là `fr-CA`:

```java
Locale target = Locale.forLanguageTag("fr-CA");
String label = target.getDisplayName();
```

Chuỗi có thể tương đương “French (Canada)” bằng tiếng Anh; với DISPLAY default `vi-VN`, nhãn được diễn đạt bằng tiếng Việt khi có dữ liệu hỗ trợ. Việc đặt tên locale **không quyết định** cách nhóm hàng nghìn hay hiển thị tiền tệ, vì đó là nhiệm vụ của formatter.

## 4. FORMAT: quy ước địa phương cho định dạng

Các phương thức `NumberFormat` không có tham số locale dùng default `FORMAT`. Theo hợp đồng Java:

```java
NumberFormat byDefault = NumberFormat.getNumberInstance();

NumberFormat equivalent =
        NumberFormat.getNumberInstance(
                Locale.getDefault(Locale.Category.FORMAT));
```

Hai formatter dùng cùng locale hiệu lực tại thời điểm tạo, vì vậy khi định dạng cùng một số với cấu hình mặc định, chuỗi kết quả tương ứng phải bằng nhau. Đối tượng formatter trả về không nhất thiết là cùng một instance.

Các ví dụ API thường dùng:

| Mục đích | Dùng default FORMAT | Chỉ định Locale tường minh |
| --- | --- | --- |
| Số thông thường | `NumberFormat.getNumberInstance()` | `NumberFormat.getNumberInstance(locale)` |
| Tiền tệ | `NumberFormat.getCurrencyInstance()` | `NumberFormat.getCurrencyInstance(locale)` |
| Phần trăm | `NumberFormat.getPercentInstance()` | `NumberFormat.getPercentInstance(locale)` |
| Định dạng ngày kiểu `java.text` | `DateFormat.getDateInstance()` | `DateFormat.getDateInstance(style, locale)` |
| Định dạng ngày kiểu `java.time` | `DateTimeFormatter.ofLocalizedDate(style)` lấy mặc định FORMAT khi tạo formatter | `DateTimeFormatter.ofLocalizedDate(style).withLocale(locale)` |

Khi dùng `java.time`, truyền locale tường minh giúp cách định dạng ngày rõ ràng, ổn định theo yêu cầu người dùng. `FORMAT` **không phải múi giờ**; ngày giờ thực tế còn cần `ZoneId` trong trường hợp liên quan đến thời điểm.

Dữ liệu có thể được định dạng theo cùng một ngôn ngữ nhưng khác vùng: `en-US` và `en-GB` có thể khác cách trình bày ngày và tiền tệ; `de-DE` và `en-US` khác quy tắc số. Không cố định một ví dụ chuỗi kết quả thành hợp đồng của mọi bản JDK và mọi nhà cung cấp dữ liệu locale.

### FORMAT không lựa chọn đơn vị tiền của giao dịch

`NumberFormat.getCurrencyInstance(formatLocale)` thường chọn đơn vị tiền mặc định gắn với vùng; **đồng tiền nghiệp vụ** (USD, EUR, VND...) phải được truyền/quản lý độc lập. Với giá trị tiền thực tế, có thể cấu hình `formatter.setCurrency(Currency.getInstance("USD"))` sau khi chọn cách trình bày. Cần xử lý số chữ số thập phân, làm tròn và chính sách tiền tệ theo yêu cầu nghiệp vụ, không suy luận từ locale.

## 5. Ví dụ kiểm chứng hai category hoạt động độc lập

**File `CategoryDefaultsDemo.java`, chạy trên Java 17+:**

```java
import java.text.NumberFormat;
import java.util.Locale;

public class CategoryDefaultsDemo {
    public static void main(String[] args) {
        Locale oldGeneral = Locale.getDefault();
        Locale oldDisplay = Locale.getDefault(
                Locale.Category.DISPLAY);
        Locale oldFormat = Locale.getDefault(
                Locale.Category.FORMAT);

        Locale enUS = Locale.forLanguageTag("en-US");
        Locale deDE = Locale.forLanguageTag("de-DE");
        Locale target = Locale.forLanguageTag("fr-CA");

        try {
            Locale.setDefault(Locale.Category.DISPLAY, enUS);
            Locale.setDefault(Locale.Category.FORMAT, deDE);

            System.out.println("General unchanged: "
                    + Locale.getDefault().equals(oldGeneral));
            System.out.println("DISPLAY: "
                    + Locale.getDefault(
                            Locale.Category.DISPLAY).toLanguageTag());
            System.out.println("FORMAT: "
                    + Locale.getDefault(
                            Locale.Category.FORMAT).toLanguageTag());

            String implicitName = target.getDisplayName();
            String explicitName = target.getDisplayName(enUS);
            System.out.println("Name uses DISPLAY: "
                    + implicitName.equals(explicitName));

            String implicitNumber =
                    NumberFormat.getNumberInstance()
                            .format(12345.67);
            String explicitNumber =
                    NumberFormat.getNumberInstance(deDE)
                            .format(12345.67);
            System.out.println("Number uses FORMAT: "
                    + implicitNumber.equals(explicitNumber));
        } finally {
            Locale.setDefault(oldGeneral);
            Locale.setDefault(
                    Locale.Category.DISPLAY, oldDisplay);
            Locale.setDefault(
                    Locale.Category.FORMAT, oldFormat);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac CategoryDefaultsDemo.java
java CategoryDefaultsDemo
```

**Stdout chính xác** khi ví dụ chạy đơn luồng và không có mã ngoài đồng thời thay đổi default JVM:

```text
General unchanged: true
DISPLAY: en-US
FORMAT: de-DE
Name uses DISPLAY: true
Number uses FORMAT: true
```

**Phân tích:**

1. `setDefault(DISPLAY, enUS)` cập nhật *chỉ default nhóm DISPLAY*.
2. `setDefault(FORMAT, deDE)` cập nhật *chỉ default nhóm FORMAT*.
3. `getDefault()` tổng quát giữ giá trị ban đầu vì chưa gọi overload `setDefault(Locale)`.
4. `target.getDisplayName()` tương đương yêu cầu tên theo `en-US` — **mặc định DISPLAY**.
5. `NumberFormat.getNumberInstance()` tương đương một formatter được tạo theo `de-DE` — **mặc định FORMAT**.
6. `finally` khôi phục ba default để chương trình minh họa không cố ý giữ cấu hình mới sau khi xong.

Đây là **ví dụ minh họa trong một tiến trình cô lập**. Thay đổi default locale là thao tác **toàn JVM**, không an toàn để dùng như cơ chế chọn ngôn ngữ theo từng HTTP request. Dù khôi phục trong `finally`, một luồng khác chạy **đồng thời** vẫn có thể quan sát giá trị tạm thời. Trong test, tránh chạy ví dụ thay đổi global song song với test phụ thuộc default; tốt nhất chạy ở process riêng nếu cần cách ly.

## 6. `setDefault(Locale)` và `setDefault(Category, Locale)` khác nhau

Java cung cấp hai cách thiết lập:

```java
Locale.setDefault(newLocale);
Locale.setDefault(Locale.Category.DISPLAY, displayLocale);
Locale.setDefault(Locale.Category.FORMAT, formatLocale);
```

Ở đây `newLocale`, `displayLocale` và `formatLocale` là các biến `Locale` đã được khai báo trong ngữ cảnh — đây là **chữ ký áp dụng**, không phải chương trình độc lập.

| Phương thức | Default tổng quát | DISPLAY | FORMAT |
| --- | --- | --- | --- |
| `Locale.setDefault(newLocale)` | Cập nhật | Cập nhật | Cập nhật |
| `Locale.setDefault(DISPLAY, locale)` | Giữ nguyên | Cập nhật | Giữ nguyên |
| `Locale.setDefault(FORMAT, locale)` | Giữ nguyên | Giữ nguyên | Cập nhật |

Vì `setDefault(Locale)` ghi đè **cả hai category**, việc đặt trước `DISPLAY=en-US`, `FORMAT=de-DE` rồi gọi `Locale.setDefault(Locale.forLanguageTag("fr-FR"))` sẽ làm cả ba thành `fr-FR`. Không dùng overload tổng quát nếu chỉ muốn thay đổi một category.

**Ví dụ độc lập — `ResetCategoriesDemo.java`:**

```java
import java.util.Locale;

public class ResetCategoriesDemo {
    public static void main(String[] args) {
        Locale oldBase = Locale.getDefault();
        Locale oldDisplay = Locale.getDefault(
                Locale.Category.DISPLAY);
        Locale oldFormat = Locale.getDefault(
                Locale.Category.FORMAT);

        try {
            Locale.setDefault(
                    Locale.Category.DISPLAY,
                    Locale.forLanguageTag("en-US"));
            Locale.setDefault(
                    Locale.Category.FORMAT,
                    Locale.forLanguageTag("de-DE"));

            Locale.setDefault(Locale.forLanguageTag("fr-FR"));

            System.out.println(Locale.getDefault().toLanguageTag());
            System.out.println(Locale.getDefault(
                    Locale.Category.DISPLAY).toLanguageTag());
            System.out.println(Locale.getDefault(
                    Locale.Category.FORMAT).toLanguageTag());
        } finally {
            Locale.setDefault(oldBase);
            Locale.setDefault(
                    Locale.Category.DISPLAY, oldDisplay);
            Locale.setDefault(
                    Locale.Category.FORMAT, oldFormat);
        }
    }
}
```

```bash
javac ResetCategoriesDemo.java
java ResetCategoriesDemo
```

Stdout:

```text
fr-FR
fr-FR
fr-FR
```

Điều này giải thích một lỗi cấu hình phổ biến: khởi tạo riêng `DISPLAY`/`FORMAT` rồi gọi `setDefault(Locale)` ở thư viện hoặc mã bootstrap khác, vô tình mất hai lựa chọn đã cấu hình.

### Thời điểm khởi tạo formatter

Default được đọc **khi API sử dụng nó**. Ví dụ, `NumberFormat.getNumberInstance()` tạo một formatter với locale áp dụng tại thời điểm gọi. Đổi `FORMAT` sau đó không phải lệnh yêu cầu mọi formatter đã tồn tại tự cập nhật. Cần tạo/cấu hình lại formatter phù hợp; đồng thời tránh chia sẻ formatter `java.text.NumberFormat` có trạng thái mutable giữa nhiều thread.

## 7. Thiết lập ban đầu khi JVM khởi động

Khi JVM khởi động, Java xác lập default locale dựa trên cấu hình môi trường và các thuộc tính hệ thống phù hợp. Ngoài thuộc tính cơ sở như `user.language`, `user.country`, Java còn có các thành phần dành cho category như:

- `user.language.display`, `user.country.display` cho nhóm DISPLAY.
- `user.language.format`, `user.country.format` cho nhóm FORMAT.

Ví dụ dòng lệnh khởi chạy chương trình ở mục 2 với các giá trị được yêu cầu (cách xử lý chính xác của các thuộc tính phụ thuộc quy tắc khởi tạo JDK):

```bash
java -Duser.language=en -Duser.country=US -Duser.language.display=vi -Duser.country.display=VN -Duser.language.format=de -Duser.country.format=DE InspectDefaultLocale
```

Với JDK tuân theo các thuộc tính khởi tạo này, ý định cấu hình là: mặc định tổng quát `en-US`, DISPLAY `vi-VN`, FORMAT `de-DE`. Không suy đoán default thực tế ở một runtime cụ thể mà không kiểm tra bằng `Locale.getDefault(...)`.

**Quan trọng:** đổi `System.setProperty("user.language.format", "de")` **sau khi JVM đã khởi tạo default** không phải cơ chế tin cậy để thay đổi `Locale` default đang hoạt động. Nếu có nhu cầu chuyển default khi đang chạy, API tương ứng là `Locale.setDefault(...)`. Tuy nhiên, vì tác động toàn tiến trình, một ứng dụng phục vụ nhiều người dùng thường nên truyền locale **tường minh** và chỉ cấu hình default tại điểm bootstrap có kiểm soát.

Đồng thời, locale không quyết định `ZoneId.systemDefault()` hay múi giờ của từng người dùng. Ngôn ngữ/vùng và múi giờ cần được quản lý như các lựa chọn độc lập.

## 8. Cách viết ứng dụng nhiều người dùng: truyền Locale tường minh

Với server web, chạy lần lượt hai request có `uiLocale` và `formatLocale` khác nhau **không nên sửa default JVM** trước mỗi lần dựng trang. Thay vào đó, xác định hai locale từ cài đặt người dùng/request và truyền vào từng API.

**File `ExplicitLocalePerRequestDemo.java` — Java 17+:**

```java
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.List;
import java.util.Locale;

public class ExplicitLocalePerRequestDemo {
    record View(String user, Locale display, Locale format) {}

    public static void main(String[] args) {
        Locale target = Locale.forLanguageTag("fr-CA");
        double amount = 12345.67;
        LocalDate date = LocalDate.of(2026, 10, 28);

        List<View> views = List.of(
                new View(
                        "A",
                        Locale.forLanguageTag("vi-VN"),
                        Locale.forLanguageTag("de-DE")),
                new View(
                        "B",
                        Locale.forLanguageTag("en-GB"),
                        Locale.forLanguageTag("en-US")));

        for (View view : views) {
            String name = target.getDisplayName(view.display());

            NumberFormat numberFormat =
                    NumberFormat.getNumberInstance(view.format());
            String number = numberFormat.format(amount);

            String dateText = DateTimeFormatter
                    .ofLocalizedDate(FormatStyle.MEDIUM)
                    .withLocale(view.format())
                    .format(date);

            System.out.println("User: " + view.user());
            System.out.println("Display locale: "
                    + view.display().toLanguageTag());
            System.out.println("Format locale: "
                    + view.format().toLanguageTag());
            System.out.println("Locale name: " + name);
            System.out.println("Number: " + number);
            System.out.println("Date: " + dateText);
        }
    }
}
```

```bash
javac ExplicitLocalePerRequestDemo.java
java ExplicitLocalePerRequestDemo
```

Chương trình luôn in **12 dòng**: 6 dòng cho A, sau đó 6 dòng cho B. Phần đầu và mã locale cố định:

```text
User: A
Display locale: vi-VN
Format locale: de-DE
...
User: B
Display locale: en-GB
Format locale: en-US
...
```

Dấu `...` trong khối trên **chỉ mô tả việc bỏ qua ba dòng tên/số/ngày của từng user, không phải stdout đầy đủ**. Ba dòng còn lại có tiền tố `Locale name:`, `Number:`, `Date:` với giá trị do JDK tạo theo dữ liệu locale hiện hành. Không cố định chuỗi số/ngày được localize xuyên các JDK/CLDR khác nhau. Lợi ích chính là các request không ghi vào global defaults, không can thiệp lẫn nhau và code nói rõ trách nhiệm: tên theo `display`, định dạng theo `format`.

Trong ứng dụng lớn, có thể gom các lựa chọn của request trong một đối tượng ngữ cảnh bất biến, truyền nó vào service render; nếu không cần hai lựa chọn riêng, cả hai trường có thể cùng một locale. Khi request thiếu lựa chọn, áp dụng **fallback của ứng dụng** đã được quy định, không mặc định mọi người dùng cùng locale của máy chủ.

## 9. Những API dễ hiểu nhầm về category

Không thể suy đoán một phương thức theo tên class “nó có vẻ liên quan đến giao diện thì dùng DISPLAY”. Ví dụ:

| Lời gọi | Đọc default nào? | Gợi ý |
| --- | --- | --- |
| `locale.getDisplayName()` | DISPLAY | Dùng `getDisplayName(uiLocale)` khi biết locale người xem |
| `locale.getDisplayLanguage()` | DISPLAY | Tên ngôn ngữ, không phải mã `getLanguage()` |
| `NumberFormat.getInstance()` | FORMAT | Dùng `getInstance(formatLocale)` khi biết locale định dạng |
| `NumberFormat.getCurrencyInstance()` | FORMAT | Lưu ý currency của giao dịch riêng |
| `DateFormat.getDateInstance()` | FORMAT | Dùng overload có locale khi render theo người dùng |
| `ResourceBundle.getBundle("messages")` | Mặc định **tổng quát** | Dùng `getBundle("messages", uiLocale)` khi muốn chọn tài nguyên theo user |
| `Locale.getDefault()` | Tổng quát | Không thay thế mặc định DISPLAY/FORMAT |
| `Locale.forLanguageTag("de-DE")` | Không dùng default JVM để chọn thẻ này | Tạo locale tường minh |

`ResourceBundle` là một ví dụ quan trọng: dù nó cung cấp chuỗi hiển thị trên UI, overload `getBundle(baseName)` dùng default `Locale.getDefault()` tổng quát, **không tự động chọn DISPLAY**. Vì vậy, đặt `Locale.Category.DISPLAY` không tự động đảm bảo toàn bộ thông điệp của ứng dụng chuyển sang đúng ngôn ngữ đó. Tài nguyên bản dịch cần được chọn riêng theo cơ chế i18n và fallback của ứng dụng.

Một sai lầm khác là coi định dạng ngày cũng tự mang theo múi giờ. Với ngày lịch thuần `LocalDate`, định dạng chỉ đổi cách viết; với thời điểm `Instant`, cần chọn múi giờ `ZoneId` trước khi trình bày giờ địa phương. `FORMAT` và `DISPLAY` không lưu thông tin thời điểm hay múi giờ.

## 10. Sai lầm phổ biến và cách tránh

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Cho rằng `getDefault()`, `getDefault(DISPLAY)`, `getDefault(FORMAT)` luôn bằng nhau | Các category có thể cấu hình độc lập | Kiểm tra và truyền đúng category |
| Chỉ gọi `setDefault(Locale)` để đổi FORMAT | Overload này cũng thay default tổng quát và DISPLAY | Nếu buộc thay default một nhóm, dùng overload có `Category` |
| Đổi `Locale.setDefault(...)` trong từng HTTP request | Tác động toàn JVM, các luồng có thể đọc giá trị của request khác | Truyền locale tường minh |
| Tin `getDisplayName()` dùng chính ngôn ngữ của locale đích | Nó dùng default DISPLAY | Gọi `getDisplayName(target)` nếu thực sự muốn nhãn tự thân |
| Cho rằng `DISPLAY` quyết định `ResourceBundle.getBundle(baseName)` | Overload không locale dùng general default | Truyền locale vào `getBundle` |
| Gọi `NumberFormat.getNumberInstance()` rồi mong nó theo DISPLAY | Nó dùng FORMAT | Truyền `formatLocale` tường minh hoặc chọn FORMAT đúng |
| Đổi default và mong formatter cũ cập nhật | Formatter đã tạo có trạng thái riêng | Tạo lại với locale phù hợp |
| Dùng tên đã dịch làm ID | Tên hiển thị có thể đổi theo ngôn ngữ/JDK | Lưu `toLanguageTag()` |
| Cho rằng FORMAT quyết định múi giờ | Locale và timezone là hai khái niệm khác nhau | Quản lý `ZoneId` riêng |
| Test xác nhận đúng toàn bộ chuỗi locale của mọi JDK | Dữ liệu locale/provider có thể thay đổi | Test hành vi/locale đã chọn; cố định runtime nếu snapshot bắt buộc |
| Khôi phục default không đầy đủ trong test | Có thể làm sai lệch test sau | Ghi lại cả general, DISPLAY, FORMAT và khôi phục trong `finally`; không chạy song song |

## 11. Kiểm thử nên thực hiện

Một bộ kiểm thử có ý nghĩa cho ứng dụng i18n nên kiểm chứng:

1. Khi đặt DISPLAY `en-US` và FORMAT `de-DE`, `getDisplayName()` tương đương overload có `en-US`, còn `NumberFormat.getNumberInstance()` tương đương overload có `de-DE`.
2. Đặt category DISPLAY riêng không làm thay đổi giá trị đọc từ `getDefault()` tổng quát hoặc FORMAT, và tương tự cho FORMAT.
3. Gọi `setDefault(Locale)` khiến general, DISPLAY và FORMAT cùng nhận locale mới.
4. Khi truyền locale tường minh cho từng request, hai người dùng A và B có thể xem tên theo ngôn ngữ khác nhau trong khi định dạng cùng một giá trị theo vùng riêng; cả hai không cần thay default.
5. Khi kiểm thử code có thay global defaults, cần khôi phục các giá trị trong `finally` và kiểm soát chạy song song. Test của ví dụ không thay thế kiểm thử độc lập tiến trình ở hệ thống thực.
6. Kiểm tra riêng locale mặc định khi startup và hệ thống dịch thông điệp: mã gọi `ResourceBundle.getBundle(baseName)` và mã gọi `getDisplayName()` có thể sử dụng hai default khác nhau.

### Bài tập thực hành

**Bài 1.** Viết chương trình in `getDefault()`, `getDefault(DISPLAY)` và `getDefault(FORMAT)`; dùng tùy chọn khởi động để yêu cầu các locale khác nhau. Quan sát trên runtime bạn đang sử dụng, giải thích vì sao ba giá trị có thể không giống nhau.

**Bài 2.** Với `target=Locale.forLanguageTag("ja-JP")`, hãy lấy tên theo locale hiển thị `vi-VN` và `en-US`, đồng thời hiển thị cùng một số theo `de-DE` và `en-US`. Không đổi `Locale.setDefault`. Giải thích API nào nhận display locale và API nào nhận format locale.

**Bài 3.** Sửa một chương trình web giả định đang dùng `Locale.setDefault(userLocale)` trong request handler. Đổi thiết kế thành hai tham số `displayLocale` và `formatLocale` được truyền đến renderer. Viết test chứng minh hai request có locale khác nhau không ghi vào global default.

**Đáp án nguyên tắc:** bài 1 kiểm tra category riêng; bài 2 truyền `Locale` tường minh vào `getDisplayName` và `NumberFormat`; bài 3 tách ngữ cảnh người dùng khỏi default JVM, không đổi trạng thái toàn tiến trình.

## 12. Tài liệu đối chiếu

- [JDK 21 — `java.util.Locale`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): `Category`, `getDefault`, `setDefault`, `getDisplayName`.
- [JDK 21 — `java.text.NumberFormat`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): các factory sử dụng mặc định `FORMAT` và overload truyền `Locale`.
- [JDK 21 — `java.util.ResourceBundle`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html): lựa chọn bundle bằng locale mặc định hoặc locale truyền tường minh.

## 13. Ghi nhớ

**`DISPLAY` trả lời “dùng ngôn ngữ/vùng nào để gọi tên các locale?”; `FORMAT` trả lời “dùng quy ước vùng nào để trình bày dữ liệu?”**. Java còn có default **tổng quát**, nên phải chọn đúng overload API. `Locale.setDefault(Locale)` thay đổi cả ba; `setDefault(Category, Locale)` thay đúng một nhóm nhưng vẫn tác động toàn JVM. Trong ứng dụng nhiều người dùng, truyền `Locale` tường minh vào API hiển thị và formatter để mỗi request độc lập, dễ kiểm thử và có hành vi rõ ràng.