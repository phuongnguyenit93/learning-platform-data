# Locale.getDefault và giá trị khởi tạo từ môi trường chạy trong Java

## Mục tiêu của bài học

Trong Java, nhiều API định dạng số, ngày tháng, tên ngôn ngữ hoặc xử lý văn bản cần một `Locale`. Khi chương trình **không truyền Locale tường minh**, một số API sử dụng **default locale** của JVM. Default locale này được Java xác định ban đầu dựa trên môi trường khởi chạy, nhưng ứng dụng cũng có thể thay đổi trong khi JVM đang chạy.

Sau bài học, bạn có thể:

- Giải thích `Locale.getDefault()` trả về gì và tại sao kết quả có thể khác nhau giữa các máy hoặc giữa các lần chạy.
- Mô tả cơ chế khởi tạo default locale từ môi trường của hệ điều hành và các system property `user.language`, `user.country`, `user.script`, `user.variant`, `user.extensions`.
- Phân biệt default locale chung với các mặc định theo `Locale.Category.DISPLAY` và `Locale.Category.FORMAT`.
- Hiểu sự khác biệt giữa **cấu hình trước khi JVM khởi động**, `System.setProperty(...)` trong lúc chạy, và `Locale.setDefault(...)`.
- Lựa chọn cách sử dụng default locale an toàn trong ứng dụng nhiều người dùng, dịch vụ web và kiểm thử.

Trọng tâm của bài là **giá trị mặc định được khởi tạo và được đọc như thế nào**. Không cần giả định rằng máy phát triển, máy CI, container và máy production đều sử dụng cùng một locale.

## 1. Default Locale là gì?

`java.util.Locale` mô tả yêu cầu về quy ước ngôn ngữ và vùng, ví dụ:

- `vi-VN`: tiếng Việt tại Việt Nam.
- `en-US`: tiếng Anh tại Hoa Kỳ.
- `en-GB`: tiếng Anh tại Vương quốc Anh.
- `fr-CA`: tiếng Pháp tại Canada.

Một số thao tác có hai cách gọi:

```java
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat implicit = NumberFormat.getNumberInstance();
NumberFormat explicit = NumberFormat.getNumberInstance(
        Locale.forLanguageTag("vi-VN"));
```

Đây là đoạn minh họa đặt trong một phương thức, không phải chương trình chạy độc lập.

- Với `implicit`, chương trình không truyền `Locale` nên API lựa chọn mặc định phù hợp (đối với định dạng số là mặc định loại `FORMAT`).
- Với `explicit`, chương trình chỉ rõ locale. Kết quả không phụ thuộc vào người đã đổi default locale của JVM, dù vẫn có thể phụ thuộc dữ liệu định dạng/provider đang sử dụng.

Default locale **không phải một bản dịch**, cũng không phải tên quốc gia mà chương trình đang chạy. Nó là một **giá trị cấu hình cấp JVM** được nhiều API có hành vi phụ thuộc ngôn ngữ/vùng tham khảo khi không nhận locale tường minh.

Không phải mọi API đều lấy cùng một loại mặc định: có **mặc định chung**, **DISPLAY** và **FORMAT**. Cần hiểu điểm này trước khi giải thích một sự khác biệt trong output.

## 2. Locale.getDefault() đọc giá trị nào?

Các phương thức quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `Locale.getDefault()` | Lấy default locale chung hiện tại của JVM. |
| `Locale.getDefault(Locale.Category.DISPLAY)` | Lấy locale mặc định dùng cho việc hiển thị tên ngôn ngữ, quốc gia và các nhãn tương tự. |
| `Locale.getDefault(Locale.Category.FORMAT)` | Lấy locale mặc định dùng cho các quy ước định dạng như số và ngày tháng. |
| `Locale.setDefault(locale)` | Đổi default locale chung **và cả hai mặc định theo Category** trong JVM. |
| `Locale.setDefault(category, locale)` | Đổi mặc định của **một Category** đã chọn; không tự đổi mặc định chung hay Category còn lại. |

`Locale.getDefault()` trả về giá trị **hiện tại**, không nhất thiết là giá trị lúc JVM mới khởi động. Khi một thành phần gọi `Locale.setDefault(...)`, các lệnh đọc về sau có thể nhận locale khác.

Mỗi JVM có trạng thái mặc định riêng. Hai chương trình Java chạy trên cùng máy vẫn có thể có default locale khác nhau nếu được khởi chạy với các tham số khác nhau hoặc có mã thay đổi default sau khi khởi động.

Bạn có thể đọc language tag của locale hiện tại bằng:

```java
String tag = Locale.getDefault().toLanguageTag();
```

Đây là dòng mã minh họa trong một phương thức có `import java.util.Locale;`. `toLanguageTag()` trả chuỗi theo cú pháp BCP 47, dễ lưu hoặc truyền qua API hơn `Locale.toString()` vốn có thể dùng dấu gạch dưới như `en_US`.

## 3. JVM khởi tạo default locale từ môi trường chạy ra sao?

Trong lúc Java runtime khởi động, default locale được thiết lập dựa trên môi trường host. Về bản chất, quá trình diễn ra theo ba bước:

1. Runtime thu thập các thông tin locale phù hợp từ **hệ điều hành và cấu hình người dùng của môi trường chạy** để lập các system property liên quan.
2. Các giá trị được truyền vào tại thời điểm **khởi chạy JVM** có thể ghi đè phần tương ứng, thông thường bằng tùy chọn `-D...` của lệnh `java`.
3. JVM tạo các đối tượng default `Locale` từ các giá trị đó, bao gồm các mặc định theo `DISPLAY` và `FORMAT`.

Các system property chính:

| System property | Thành phần của Locale | Giá trị ví dụ |
| --- | --- | --- |
| `user.language` | Mã ngôn ngữ | `vi`, `en`, `fr` |
| `user.script` | Hệ chữ viết, khi có | `Latn`, `Hant` |
| `user.country` | Vùng/quốc gia | `VN`, `US`, `CA` |
| `user.variant` | Biến thể, khi có | `POSIX` |
| `user.extensions` | Locale extensions, khi có | `u-nu-latn` |

Không phải máy nào cũng cung cấp đủ tất cả các property. Đặc biệt, một locale chỉ có ngôn ngữ như `en` là một định danh có ý nghĩa; **không được suy rằng nếu thiếu `user.country` thì Java luôn chọn `US`**.

Môi trường host có thể bao gồm thiết lập vùng/ngôn ngữ của hệ điều hành, cấu hình tài khoản người chạy quy trình, thiết lập container hoặc môi trường CI. Cách Java lấy dữ liệu từ host là chi tiết phụ thuộc nền tảng/JDK. Vì thế không nên tuyên bố một biến môi trường đơn lẻ, chẳng hạn `LANG`, luôn quyết định default locale trên mọi hệ điều hành.

### Ghi đè ngay khi khởi động JVM

Ví dụ giả sử đã có lớp `DefaultLocaleDemo` bên dưới, có thể chạy:

```bash
java "-Duser.language=vi" "-Duser.country=VN" DefaultLocaleDemo
```

Hai tham số `-D` được truyền **trước tên lớp chính** và đặt cấu hình dùng khi JVM khởi tạo. Đây là cách kiểm soát default locale lúc khởi động một tiến trình Java; tác dụng chỉ trong JVM đó, không thay đổi cài đặt ngôn ngữ của toàn bộ hệ điều hành.

Nếu không truyền `-D`, `Locale.getDefault()` có thể trả `vi-VN` trên một máy, `en-US` trên máy khác hoặc locale khác tùy môi trường. Không nên viết bài kiểm thử yêu cầu một giá trị cố định khi chưa kiểm soát cấu hình chạy.

### Vì sao không tự đọc user.language rồi suy ra Locale?

`System.getProperty("user.language")` chỉ cho biết **system property**, còn `Locale.getDefault()` trả về **đối tượng mặc định hiện tại**. Hai thứ có thể lệch nhau:

- Property được dùng làm **đầu vào khởi tạo**.
- `Locale.setDefault(...)` có thể đổi default locale mà **không đổi property**.
- `System.setProperty(...)` sau khi JVM đã khởi tạo default locale **không làm default locale tự cập nhật**.

Vì vậy, nếu muốn biết default locale **hiện tại**, hãy đọc `Locale.getDefault()` hoặc `Locale.getDefault(Category)`. Đừng tự ghép một locale mới từ những system property có thể đã trở nên lỗi thời.

## 4. DISPLAY và FORMAT là hai ngữ cảnh khác nhau

Java hỗ trợ hai Category để phân tách công việc:

- **`DISPLAY`:** quy ước ngôn ngữ dùng khi hiển thị tên một ngôn ngữ, quốc gia hay locale. Chẳng hạn phương thức `someLocale.getDisplayLanguage()` không nhận tham số locale sẽ sử dụng default `DISPLAY` để tạo tên ngôn ngữ.
- **`FORMAT`:** quy ước dùng khi hiển thị số, phần trăm, tiền tệ, ngày giờ… Một số API định dạng không có tham số locale sử dụng default `FORMAT`.

Hệ điều hành có thể cấu hình giao diện bằng tiếng Anh nhưng định dạng số/ngày theo tiếng Pháp. Java biểu diễn tình huống đó bằng hai Category khác nhau, thay vì buộc mọi tác vụ vào cùng một giá trị.

Các property theo Category sử dụng hậu tố:

| Cấu hình chung | DISPLAY | FORMAT |
| --- | --- | --- |
| `user.language` | `user.language.display` | `user.language.format` |
| `user.country` | `user.country.display` | `user.country.format` |
| `user.script` | `user.script.display` | `user.script.format` |
| `user.variant` | `user.variant.display` | `user.variant.format` |
| `user.extensions` | `user.extensions.display` | `user.extensions.format` |

Nếu một property theo Category không được đặt, runtime có thể sử dụng giá trị tương ứng từ cấu hình chung. Ví dụ, `user.language=vi` cùng `user.language.display=en` cho phép ngôn ngữ mặc định chung là tiếng Việt nhưng ngôn ngữ hiển thị mặc định là tiếng Anh.

**Không đồng nhất** `Locale.getDefault()` với `Locale.getDefault(Locale.Category.FORMAT)`. Chúng có thể bằng nhau lúc khởi động một chương trình cụ thể nhưng không được đảm bảo luôn bằng nhau.

## 5. Ví dụ Java 17+ chạy được và kết quả xác định

Ví dụ minh họa cả ba giai đoạn:

- Khởi tạo qua các tham số JVM `-D`.
- Thay đổi một system property **sau** khi default locale đã được khởi tạo.
- Thay đổi trực tiếp default locale bằng `Locale.setDefault` và bằng setter theo Category.

Tạo tệp `DefaultLocaleDemo.java`:

```java
import java.util.Locale;

public class DefaultLocaleDemo {

    private static void show(String stage) {
        System.out.printf(
                "%s: base=%s, display=%s, format=%s%n",
                stage,
                Locale.getDefault().toLanguageTag(),
                Locale.getDefault(Locale.Category.DISPLAY).toLanguageTag(),
                Locale.getDefault(Locale.Category.FORMAT).toLanguageTag()
        );
    }

    public static void main(String[] args) {
        show("startup");

        System.setProperty("user.language", "de");
        show("after property");

        Locale.setDefault(Locale.forLanguageTag("ja-JP"));
        show("after base setter");

        Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);
        show("after format setter");
    }
}
```

Biên dịch:

```bash
javac -encoding UTF-8 DefaultLocaleDemo.java
```

Chạy với tham số cụ thể ở **đầu lệnh khởi chạy JVM**:

```bash
java "-Duser.language=vi" "-Duser.country=VN" "-Duser.language.display=en" "-Duser.country.display=US" "-Duser.language.format=fr" "-Duser.country.format=FR" DefaultLocaleDemo
```

Stdout:

```text
startup: base=vi-VN, display=en-US, format=fr-FR
after property: base=vi-VN, display=en-US, format=fr-FR
after base setter: base=ja-JP, display=ja-JP, format=ja-JP
after format setter: base=ja-JP, display=ja-JP, format=de-DE
```

Giải thích từng mốc:

**`startup`:** cấu hình chung nhận `vi-VN`; hai cấu hình theo Category lần lượt là `en-US` và `fr-FR`. Các giá trị được kiểm soát bằng `-D` nên không cần đoán ngôn ngữ cài sẵn trên máy.

**`after property`:** `System.setProperty("user.language", "de")` thay đổi giá trị property, nhưng không kích hoạt lại quá trình khởi tạo default locale. Do đó `Locale.getDefault()` vẫn là `vi-VN`, không phải `de-VN`.

**`after base setter`:** `Locale.setDefault(Locale.forLanguageTag("ja-JP"))` đặt lại default chung và **cả hai Category** thành `ja-JP` trong JVM hiện tại.

**`after format setter`:** `Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY)` chỉ thay đổi `FORMAT` thành `de-DE`. Default chung và `DISPLAY` vẫn là `ja-JP`.

Ví dụ cố ý in **language tag**, tránh dựa vào ký hiệu tiền tệ hoặc tên tháng có thể thay đổi theo dữ liệu bản địa hóa của JDK/provider. Nó cho thấy sự khác nhau giữa property khởi tạo và trạng thái default locale đang hoạt động.

Bạn không nên tùy tiện chạy mã `Locale.setDefault` như trên trong một dịch vụ production nhiều người dùng. Phần này là thí nghiệm nhỏ trong **một JVM riêng** để quan sát cơ chế.

## 6. Thay đổi mặc định lúc chạy: tác dụng và giới hạn

### setDefault(Locale)

```java
Locale.setDefault(Locale.forLanguageTag("fr-FR"));
```

Dòng mã minh họa trong phương thức, có `import java.util.Locale;`. Lệnh đổi default locale chung và defaults theo Category cho toàn bộ JVM. Nó **không** đổi thiết lập của hệ điều hành, không cập nhật các system property `user.language`/`user.country`, và không có nghĩa các đối tượng formatter đã tạo trước đó tự cấu hình lại.

Ví dụ, một `NumberFormat` đã được khởi tạo trước khi thay đổi default có cấu hình riêng. Đừng giả định nó sẽ tự đổi theo giá trị mới của `Locale.getDefault()`. Nếu cần định dạng theo locale mới, tạo formatter phù hợp hoặc cấu hình API rõ ràng.

### setDefault(Category, Locale)

```java
Locale.setDefault(
        Locale.Category.DISPLAY,
        Locale.forLanguageTag("en-GB")
);
```

Lệnh trên chỉ đổi default `DISPLAY`, không chủ động sửa `FORMAT` hay default chung. Điều này có ích trong những ứng dụng mà ngôn ngữ tên hiển thị cần tách khỏi quy ước định dạng, nhưng vẫn là **thay đổi toàn JVM** đối với Category được chọn.

### Không dùng System.setProperty như lệnh đổi default

```java
System.setProperty("user.country", "VN");
```

Dòng này thay đổi system property trong quá trình chạy, không phải lệnh cập nhật `Locale.getDefault()`. Muốn biết trạng thái hiện tại phải gọi `Locale.getDefault()`. Muốn thay đổi trạng thái, API chính thức là `Locale.setDefault` (kèm đánh giá ảnh hưởng đến toàn tiến trình).

Một lỗi chẩn đoán thường gặp là đọc `System.getProperty("user.language")` rồi ngạc nhiên vì `Locale.getDefault()` trả locale khác. Hãy kiểm tra xem chương trình hoặc một framework nào đã gọi `setDefault` chưa; hai nguồn dữ liệu không bắt buộc còn đồng bộ.

## 7. Ảnh hưởng đến API không truyền Locale

Để thấy default locale thực tế có ích ở đâu, hãy so sánh hai kiểu gọi:

| Nhóm xử lý | Dựa vào default | Truyền tường minh |
| --- | --- | --- |
| Định dạng số | `NumberFormat.getNumberInstance()` | `NumberFormat.getNumberInstance(locale)` |
| Định dạng tiền | `NumberFormat.getCurrencyInstance()` | `NumberFormat.getCurrencyInstance(locale)` |
| Định dạng ngày | `DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)` dùng FORMAT default khi tạo | `DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).withLocale(locale)` |
| Tên ngôn ngữ | `target.getDisplayLanguage()` dùng DISPLAY default | `target.getDisplayLanguage(locale)` |
| So sánh theo ngôn ngữ | `Collator.getInstance()` | `Collator.getInstance(locale)` |
| Chuyển chữ | `text.toUpperCase()` dùng default locale | `text.toUpperCase(locale)` |

Bảng minh họa các API quen thuộc; từng API có quy tắc về Category và thời điểm đọc default riêng. Không nên suy ra “mọi API không nhận Locale đều luôn lấy kết quả trực tiếp từ `Locale.getDefault()`”. Hãy xem hợp đồng của phương thức cụ thể.

Ví dụ lập trình ứng dụng web:

```java
import java.text.NumberFormat;
import java.util.Locale;

public final class PriceLabel {
    private PriceLabel() {}

    public static String formatAmount(double amount, Locale requestedLocale) {
        NumberFormat format = NumberFormat.getNumberInstance(requestedLocale);
        return format.format(amount);
    }
}
```

Đây là lớp tiện ích có thể biên dịch thành `PriceLabel.java`, không có `main` để tự chạy. Hàm nhận locale của người dùng một cách rõ ràng thay vì đọc cấu hình ngầm của JVM. Khi truyền `Locale.forLanguageTag("vi-VN")` hoặc `Locale.forLanguageTag("en-US")`, hành vi định dạng theo locale yêu cầu; chi tiết dấu phân tách vẫn phụ thuộc dữ liệu bản địa hóa/provider.

Khi xử lý dữ liệu **máy đọc** như mã định danh, khóa cấu hình, hoặc chuyển chữ phục vụ thuật toán độc lập với người dùng, cân nhắc `Locale.ROOT` thay vì mặc định:

```java
String normalized = "identifier".toUpperCase(Locale.ROOT);
```

`Locale.ROOT` không phải cấu hình ngôn ngữ giao diện; nó hữu ích cho thao tác không nên bị thay đổi theo người dùng. Ví dụ, quy tắc viết hoa tiếng Thổ Nhĩ Kỳ có thể khác tiếng Anh, nên các phép biến đổi chữ có ngữ nghĩa ngôn ngữ cần locale tường minh.

## 8. Default locale, múi giờ và encoding là những cấu hình độc lập

Một máy có thể có:

```text
Default Locale: vi-VN
Time Zone:      Europe/Paris
Charset:        UTF-8
```

Không có gì mâu thuẫn: default locale có thể dùng để chọn quy ước ngôn ngữ/định dạng, nhưng **không quyết định múi giờ**. Ngày giờ của một `Instant` muốn hiển thị theo giờ địa phương còn cần `ZoneId`. Charset là cách mã hóa byte của văn bản, cũng không thể suy ra chỉ từ default locale.

Ví dụ:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

Locale locale = Locale.forLanguageTag("vi-VN");
ZoneId zone = ZoneId.of("Europe/Paris");

String output = DateTimeFormatter
        .ofLocalizedDateTime(FormatStyle.MEDIUM)
        .withLocale(locale)
        .withZone(zone)
        .format(Instant.parse("2026-10-28T08:00:00Z"));
```

Đây là đoạn minh họa nằm trong một phương thức, không phải chương trình độc lập; `output` thể hiện cùng một `Instant` với quy ước định dạng theo `vi-VN` và múi giờ Paris. Không ghi cứng chuỗi kết quả vì tên tháng, dấu câu và quy tắc định dạng có thể phụ thuộc dữ liệu JDK/provider.

Đừng hiểu `Locale.getDefault()` là “múi giờ hệ thống” hoặc “quốc gia người dùng hiện tại”.

## 9. Rủi ro khi dựa vào default trong dịch vụ nhiều người dùng

Default locale là **trạng thái chung cấp tiến trình JVM**, không tự gắn với mỗi HTTP request hay mỗi thread. Giả sử hệ thống xử lý đồng thời:

```text
Request A (vi-VN): Locale.setDefault(vi-VN)
Request B (en-US): Locale.setDefault(en-US)
Request A:        NumberFormat.getNumberInstance()
```

Request A có thể nhận formatter theo default FORMAT bị B thay đổi. Tại thời điểm A gọi API, giá trị chung không nhất thiết còn là `vi-VN`. Vấn đề vẫn xảy ra ngay cả khi các lời gọi `setDefault` bản thân nó hợp lệ: **trạng thái dùng chung không biểu diễn đúng ngữ cảnh riêng của từng request**.

Cách thực hiện tốt hơn:

1. Xác định locale người dùng từ cài đặt đã lưu, yêu cầu HTTP hoặc kết quả thương lượng ngôn ngữ.
2. Kiểm tra và giải quyết locale theo danh sách hỗ trợ của ứng dụng; đừng tự suy vị trí hay múi giờ từ locale.
3. Truyền `Locale` đã giải quyết tường minh cho formatter, dịch thông điệp, xử lý thứ tự sắp xếp hoặc tầng giao diện cần nó.
4. Giữ cấu hình default locale của tiến trình ổn định; tránh gọi `Locale.setDefault` trong đường xử lý từng request.

Trong ứng dụng backend, khởi tạo default locale một lần lúc bootstrap có thể phù hợp nếu ứng dụng thực sự có một lựa chọn chung cố định. Nhưng với hệ thống phục vụ nhiều người dùng/ngôn ngữ, ưu tiên truyền tham số `Locale` hoặc một request context được quản lý rõ ràng.

### Hệ quả đối với kiểm thử và CI

Một test định dạng “hôm nay hiển thị `1,234.56`” có thể chạy đúng trên máy của tác giả, nhưng thất bại ở CI dùng ngôn ngữ khác. Nguyên nhân không nhất thiết do thuật toán sai; test đã phụ thuộc mặc định của môi trường.

Có hai hướng kiểm thử:

- Khi kiểm tra chức năng định dạng cụ thể, **truyền Locale tường minh** và chọn dữ liệu thời gian/tỷ giá độc lập.
- Khi cố ý kiểm tra hành vi theo default locale, chạy test trong JVM có cấu hình khởi động đã xác định, ví dụ `-Duser.language=...` và `-Duser.country=...`. Kiểm tra cả hai Category nếu tính năng có liên quan.

Trường hợp test bắt buộc dùng `Locale.setDefault` trong cùng JVM, cần lưu lại cả default chung, `DISPLAY`, `FORMAT` và khôi phục trong `finally`. Tuy nhiên việc khôi phục vẫn không làm các bài test song song hoàn toàn an toàn: trong khoảng thay đổi, những test khác có thể đọc cấu hình chung tạm thời. Tách JVM hoặc tránh mutation thường đáng tin cậy hơn.

## 10. Các nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế và cách sửa |
| --- | --- |
| `Locale.getDefault()` luôn cho `en-US` | Giá trị ban đầu tùy môi trường và cấu hình khởi động; không có mặc định toàn cầu bắt buộc là `en-US`. |
| Default Locale được cập nhật mỗi khi người dùng đổi ngôn ngữ OS | JVM thiết lập mặc định ban đầu khi khởi động; không giả định tự theo dõi các thay đổi OS về sau. |
| `System.setProperty("user.language", "fr")` thay đổi locale hiện tại | Đây là thay đổi property, không phải gọi `Locale.setDefault`. |
| `Locale.setDefault(frFR)` cũng đổi system property và OS | Chỉ đổi trạng thái default locale trong JVM; không đổi host locale hoặc property khởi tạo. |
| `getDefault()`, `getDefault(DISPLAY)` và `getDefault(FORMAT)` luôn giống nhau | Category có thể được cấu hình và thay đổi độc lập. |
| Đổi default locale sẽ tự điều chỉnh mọi formatter đã tạo | Đối tượng định dạng đã tạo thường có trạng thái riêng; không coi chúng là view luôn đồng bộ với default. |
| `Locale` quy định múi giờ, charset, loại tiền của giao dịch | Các dữ liệu này thuộc những cấu hình/miền nghiệp vụ riêng. |
| Đọc `user.language` là cách chính xác nhất để biết default locale | Giá trị property có thể đã cũ; dùng `Locale.getDefault()`. |
| `setDefault` cho mỗi request giúp hỗ trợ đa ngôn ngữ | Trạng thái JVM chung dẫn đến ảnh hưởng chéo giữa request đồng thời. |
| Đặt locale trong constructor của chương trình là đủ cho mọi test | Hãy xác định Category và cách API liên quan chọn locale; ưu tiên truyền tham số cụ thể. |

## 11. Bài tập kiểm tra hiểu biết

**Bài tập 1 – môi trường chạy.** Cùng một lớp gọi `Locale.getDefault().toLanguageTag()` được thực thi trên hai máy không có `-D`. Tại sao hai giá trị có thể khác nhau? Hãy chỉ ra phần nào là thông tin từ môi trường host và phần nào là cấu hình do ứng dụng chủ động chọn.

**Bài tập 2 – ba default khác nhau.** Chạy ví dụ `DefaultLocaleDemo` với bộ property trong mục 5. Giải thích vì sao `startup` báo `base=vi-VN` nhưng `display=en-US` và `format=fr-FR`. Nếu bỏ các property mang hậu tố `.display` và `.format`, hãy dự đoán lúc khởi động Category sẽ kế thừa thông tin nào.

**Bài tập 3 – property khác state.** Sau khi thực hiện `System.setProperty("user.language", "de")`, tại sao `Locale.getDefault()` không tự đổi? Khi gọi `Locale.setDefault(Locale.JAPAN)`, tại sao property `user.language` vẫn không nhất thiết khớp default locale mới?

**Bài tập 4 – concurrency.** Hai request A và B có locale riêng. Vì sao gọi `Locale.setDefault` trong từng request là sai về mô hình đồng thời? Hãy thay bằng phương thức `formatAmount(double, Locale)` và giải thích lợi ích của việc truyền locale tường minh.

**Bài tập 5 – tính độc lập.** Người dùng chọn ngôn ngữ tiếng Việt, múi giờ Paris và loại tiền giao dịch USD. Hãy chỉ ra các giá trị `Locale`, `ZoneId` và `Currency` cần quản lý riêng. Thay đổi default locale có tự đổi múi giờ hoặc đơn vị tiền trên hóa đơn hay không?

## 12. Tóm tắt kiến thức cốt lõi

- `Locale.getDefault()` trả **default locale chung hiện tại của JVM**, có thể khác với giá trị được khởi tạo lúc đầu nếu ứng dụng gọi `setDefault`.
- Java khởi tạo default locale khi bắt đầu runtime từ thông tin môi trường host và các system property `user.language`, `user.country`, `user.script`, `user.variant`, `user.extensions`; tham số `-D` tại lúc khởi chạy có thể ghi đè những thông tin đó.
- `DISPLAY` và `FORMAT` là hai mặc định theo mục đích; chúng có thể được khởi tạo từ property riêng và thay đổi độc lập.
- `System.setProperty` sau khi JVM đã khởi tạo default **không cập nhật** đối tượng default locale; `Locale.setDefault` thay đổi default trong JVM nhưng **không cập nhật** property tương ứng hoặc cài đặt host.
- Với ứng dụng nhiều người dùng, dùng `Locale` tường minh trong API thay cho mutation của cấu hình dùng chung; kiểm thử cần kiểm soát locale, Category và các phụ thuộc khác như múi giờ.

**Tham khảo API:** [`java.util.Locale` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html), các phần “Default Locale”, “Locale Category”, `getDefault` và `setDefault`.
