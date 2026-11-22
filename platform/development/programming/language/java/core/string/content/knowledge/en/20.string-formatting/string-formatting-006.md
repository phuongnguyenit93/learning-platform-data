# Locale mặc định so với `String.format(Locale, ...)` trong Java

Khi định dạng chuỗi có chứa số, ngày giờ hoặc nội dung phụ thuộc ngôn ngữ, cùng một lời gọi `String.format` có thể tạo ra kết quả khác nhau ở các môi trường chạy. Nguyên nhân thường là **locale**: tập quy ước ngôn ngữ và vùng được áp dụng cho việc định dạng. Bài này phân biệt hai overload của `String.format`, giải thích locale mặc định và cách chọn locale tường minh để có kết quả đúng mục đích.

## 1. Locale ảnh hưởng đến định dạng như thế nào?

`java.util.Locale` mô tả các quy ước theo ngôn ngữ/vùng, chẳng hạn `Locale.US` (Mỹ), `Locale.GERMANY` (Đức) hoặc `Locale.forLanguageTag("vi-VN")` (tiếng Việt tại Việt Nam). Khi áp dụng vào `Formatter`, locale có thể chi phối:

- Dấu phân cách thập phân và dấu phân nhóm chữ số khi dùng conversion/flag tương ứng (`%f`, `%,d`, `%,.2f`, ...).
- Tên tháng, tên thứ và một số biểu diễn ngày giờ bằng `%t`/`%T`.
- Việc đổi thành chữ hoa ở một số conversion như `%S` theo quy tắc locale.

Locale **không tự dịch** phần chữ viết cố định trong mẫu. Chẳng hạn `"Total: %,.2f"` vẫn có nhãn `Total:` với mọi locale; sự khác biệt nằm ở phần số được chèn vào. Locale cũng không tự thay đổi giá trị số đầu vào, kiểu dữ liệu hay múi giờ của đối tượng ngày giờ.

## 2. Hai overload của `String.format`

~~~java
String format(String format, Object... args)
String format(Locale locale, String format, Object... args)
~~~

Đây là hai phương thức `static` của `java.lang.String`:

| Lời gọi | Locale được sử dụng | Phù hợp khi |
| --- | --- | --- |
| `String.format("... ", args)` | Locale mặc định thuộc `Locale.Category.FORMAT` của JVM tại lúc gọi | Kết quả hướng tới người dùng theo cấu hình định dạng mặc định của ứng dụng |
| `String.format(Locale.US, "...", args)` | Chính locale được truyền vào | Muốn quy ước Mỹ ổn định dù JVM chạy ở máy nào |
| `String.format(selectedLocale, "...", args)` | Locale được chọn theo người dùng/yêu cầu | Giao diện phục vụ nhiều ngôn ngữ/vùng |
| `String.format(Locale.ROOT, "...", args)` | Locale trung lập (root locale) | Định dạng không cần quy ước vùng cụ thể, khi phù hợp với giao thức/đặc tả |

**Điểm then chốt:** overload không có tham số `Locale` dùng `Locale.getDefault(Locale.Category.FORMAT)`. Không nên ngầm đồng nhất giá trị này với `Locale.getDefault()` trong mọi tình huống, vì Java cho phép cấu hình mặc định riêng theo từng `Locale.Category`.

Cú pháp mẫu vẫn giống nhau. Ví dụ, `%,.2f` yêu cầu số thực có dấu phân nhóm (`,` flag) và đúng hai chữ số phần thập phân (`.2` precision); **dấu thực tế trong kết quả được quyết định bởi locale**, không nhất thiết là ký tự dấu phẩy/dấu chấm của mẫu.

## 3. Ví dụ chạy được: mặc định so với locale tường minh

Tạo tệp `FormatLocaleDemo.java`:

~~~java
import java.util.Locale;

public class FormatLocaleDemo {
    public static void main(String[] args) {
        Locale previous = Locale.getDefault(Locale.Category.FORMAT);

        try {
            // Cố định locale mặc định để kết quả ví dụ có thể kiểm chứng.
            Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);

            double amount = 12345.67;
            System.out.println(String.format("Default: %,.2f", amount));
            System.out.println(String.format(Locale.US, "US: %,.2f", amount));
            System.out.println(String.format(Locale.GERMANY, "Germany: %,.2f", amount));
            System.out.println(String.format(Locale.US, "US without grouping: %.2f", amount));
        } finally {
            Locale.setDefault(Locale.Category.FORMAT, previous);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac FormatLocaleDemo.java
java FormatLocaleDemo
~~~

Kết quả:

~~~text
Default: 12.345,67
US: 12,345.67
Germany: 12.345,67
US without grouping: 12345.67
~~~

Giải thích từng dòng:

1. `Default` dùng overload thiếu `Locale` nên lấy mặc định `FORMAT` đã tạm chuyển sang `Locale.GERMANY`: phân nhóm bằng dấu chấm, phần thập phân bằng dấu phẩy.
2. `US` truyền `Locale.US` trực tiếp nên phân nhóm bằng dấu phẩy, phần thập phân bằng dấu chấm, bất kể mặc định JVM đang là Đức.
3. `Germany` minh họa truyền tường minh locale Đức: kết quả trùng dòng đầu trong chương trình này nhưng không phụ thuộc mặc định.
4. `US without grouping` bỏ flag `,`: không thêm dấu phân nhóm; vẫn giữ hai chữ số thập phân nhờ `.2f`.

Trong ví dụ, `try/finally` khôi phục thiết lập trước khi chạy để minh họa an toàn hơn. Tuy vậy, thay đổi locale mặc định vẫn tác động **toàn tiến trình JVM** trong khoảng thời gian giữa hai lời gọi `setDefault`. Không dùng kỹ thuật thay đổi mặc định theo từng request trong server đa luồng: request đồng thời có thể quan sát cấu hình của nhau. Trong ứng dụng thực tế, hãy truyền `Locale` trực tiếp vào mỗi phép định dạng khi cần chọn quy ước cụ thể.

## 4. Mặc định FORMAT khác mặc định DISPLAY

Java phân biệt ít nhất hai nhu cầu:

- `Locale.Category.FORMAT` dành cho định dạng số, ngày giờ và dữ liệu nhạy với quy ước vùng.
- `Locale.Category.DISPLAY` dành cho cách hiển thị tên ngôn ngữ, quốc gia và các thông tin địa phương hóa khác.

Có thể đọc chúng riêng:

~~~java
Locale formatting = Locale.getDefault(Locale.Category.FORMAT);
Locale displaying = Locale.getDefault(Locale.Category.DISPLAY);
Locale general = Locale.getDefault();
~~~

Đây là **đoạn minh họa API**, không phải chương trình độc lập. Sau khi một ứng dụng tùy chỉnh từng category, `formatting` và `displaying` có thể khác nhau. `String.format(String, ...)` lấy category `FORMAT`; hãy kiểm tra chính category này khi điều tra vì sao kết quả định dạng thay đổi.

Locale mặc định ban đầu thường xuất phát từ cấu hình môi trường/JVM; có thể đổi bằng API `Locale.setDefault(...)`. Vì vậy không được suy luận rằng cứ chạy trên Windows, Linux hay một máy chủ cụ thể là mặc định sẽ luôn là `Locale.US`.

## 5. Chọn locale theo mục đích sử dụng

### Kết quả để người dùng đọc

Nếu người dùng đã chọn ngôn ngữ/vùng, dùng đúng locale của họ khi hiển thị:

~~~java
Locale viewerLocale = Locale.forLanguageTag("de-DE");
String displayed = String.format(viewerLocale, "Preis: %,.2f", 1234.5);
~~~

Đoạn này minh họa mã sử dụng trong ứng dụng, không phải chương trình đầy đủ. Kết quả có định dạng số theo quy ước Đức nhưng chữ `Preis:` là phần mẫu do lập trình viên cung cấp. Để bản địa hóa chính nhãn hoặc toàn bộ thông điệp, cần thêm cơ chế tài nguyên đa ngôn ngữ (chẳng hạn `ResourceBundle`).

### Kết quả máy cần đọc ổn định

Khi định dạng số cho khóa dữ liệu, đoạn văn bản kiểm thử, hoặc một giao thức **quy định** dấu chấm thập phân, hãy chỉ định locale phù hợp thay vì phụ thuộc hệ điều hành:

~~~java
String value = String.format(Locale.US, "%.2f", 12.5);
// value: "12.50"
~~~

Đây là đoạn mã minh họa độc lập về biểu thức. Phải tuân thủ định dạng chính thức của giao thức: nhiều giao thức nên dùng API serialize chuyên dụng (ví dụ thư viện JSON hoặc chuẩn số tương ứng), thay vì tùy tiện ghép chuỗi `String.format`. `Locale.ROOT` có thể hữu ích cho một số thao tác trung lập về ngôn ngữ nhưng không tự động là định dạng đúng của mọi giao thức.

### Không chỉnh global default theo mỗi request

~~~java
// Tránh trong web server xử lý nhiều request đồng thời:
Locale.setDefault(Locale.Category.FORMAT, requestedLocale);
String output = String.format("%,.2f", value);

// Ưu tiên:
String safeOutput = String.format(requestedLocale, "%,.2f", value);
~~~

Hai đoạn trên chỉ minh họa lựa chọn API trong ngữ cảnh đã có `requestedLocale` và `value`. Cách thứ hai làm rõ phụ thuộc ngay tại điểm sử dụng, thuận tiện cho review và kiểm thử.

## 6. Các ký hiệu định dạng thường gặp

| Mẫu | Ý nghĩa | Ghi chú về locale |
| --- | --- | --- |
| `%s` | Biểu diễn đối tượng thành chuỗi | Không tự dịch nội dung của chuỗi |
| `%S` | Như `%s` nhưng chuyển chữ hoa | Quy tắc chuyển hoa có thể phụ thuộc locale |
| `%d` | Số nguyên dạng thập phân | Có thể dùng chữ số theo hệ chữ số của locale |
| `%,d` | Số nguyên có phân nhóm hàng nghìn | Dấu phân nhóm tùy locale |
| `%.2f` | Số thực, hai chữ số phần thập phân | Dấu thập phân tùy locale |
| `%,.2f` | Số thực có phân nhóm và hai chữ số thập phân | Cả dấu nhóm và dấu thập phân tùy locale |
| `%1$tB` | Tên tháng đầy đủ của đối số thứ nhất | Tên tháng phụ thuộc locale |
| `%%` | Ký tự `%` | Không sử dụng đối số |
| `%n` | Dấu xuống dòng theo nền tảng | Do nền tảng, không phải lựa chọn theo locale |

Ví dụ các conversion ngày tháng (đoạn mã sử dụng trong một phương thức):

~~~java
java.time.LocalDate date = java.time.LocalDate.of(2026, 10, 23);
String usMonth = String.format(Locale.US, "%1$tB", date);
String germanMonth = String.format(Locale.GERMANY, "%1$tB", date);
~~~

`%1$tB` nghĩa là lấy tên tháng đầy đủ từ đối số số 1. Locale điều khiển cách thể hiện tên tháng; bản thân ngày `2026-10-23` không thay đổi. Các đối số thời gian có thông tin múi giờ cần được xử lý đúng kiểu và múi giờ riêng; chuyển `Locale` không đồng nghĩa chuyển múi giờ.

## 7. `Locale.ROOT`, `null` và phạm vi không được hiểu nhầm

- `Locale.ROOT` là locale trung lập dùng khi không muốn chọn riêng một quốc gia/ngôn ngữ. Tuy nhiên, việc định dạng vẫn theo quy tắc của `Formatter` và không phải mọi cách thể hiện đều phù hợp với chuẩn dữ liệu bên ngoài.
- Overload `String.format(Locale, String, Object...)` cũng cho phép tham số locale là `null`: khi đó **không áp dụng bản địa hóa** theo đặc tả `Formatter`. Điều này khác về ý nghĩa API với “lấy locale mặc định”; nên ưu tiên truyền locale rõ ràng khi yêu cầu định dạng đã xác định.
- `String.format` dùng để **tạo chuỗi**, không dùng để phân tích ngược chuỗi theo locale. Nếu cần đọc giá trị dạng `"12.345,67"`, xem xét `NumberFormat` với locale phù hợp và kiểm tra việc parse có tiêu thụ hết chuỗi đầu vào hay không.
- Với tiền tệ, đừng coi `%,.2f` là định dạng tiền hoàn chỉnh: ký hiệu, vị trí ký hiệu, số chữ số thập phân và cách làm tròn theo tiền tệ cần `NumberFormat.getCurrencyInstance(locale)` và kiểu số phù hợp (thường `BigDecimal` cho phép tính chính xác theo thập phân).
- Một số dấu phân nhóm (nhất là dấu cách và biến thể Unicode của nó) có thể khác theo locale/dữ liệu bản địa hóa của JDK. Vì vậy, kiểm thử đầu ra bằng locale cụ thể và tránh đoán dấu cách bằng mắt thường.

## 8. Lỗi thường gặp và cách khắc phục

**Lỗi 1 — Kết quả khác giữa máy phát triển và CI.** Mã dùng `String.format("%,.2f", amount)` nhưng kỳ vọng dấu thập phân luôn là `.`. Nguyên nhân: ngầm dùng locale mặc định `FORMAT`. Khắc phục: truyền `Locale.US` (hoặc locale được đặc tả) ở ngay lời gọi.

**Lỗi 2 — Đặt `Locale.setDefault` để phục vụ một người dùng.** Cấu hình được thay đổi cho toàn JVM, làm những request chạy song song ảnh hưởng nhau. Khắc phục: truyền `Locale` theo từng request, rồi truyền tiếp vào hàm định dạng.

**Lỗi 3 — Nhầm `%s` với bản địa hóa thông điệp.** `String.format(Locale.GERMANY, "Total: %s", "OK")` không dịch `Total` hoặc `OK`. Khắc phục: quản lý các thông điệp/nội dung dịch theo locale bằng resource bundle hoặc cơ chế tương đương.

**Lỗi 4 — So sánh chuỗi số đã định dạng để tính toán.** `"1.234,50"` được thiết kế cho hiển thị, không thể đưa trực tiếp vào `Double.parseDouble`. Khắc phục: giữ dữ liệu là số trong xử lý; chỉ format tại biên hiển thị và dùng parser đúng locale khi nhận đầu vào.

**Lỗi 5 — Nhầm locale với timezone.** `Locale.US` có thể cho tên tháng tiếng Anh, nhưng không tự chuyển thời điểm sang giờ Mỹ. Khắc phục: xác định `ZoneId`/`ZonedDateTime` hoặc múi giờ yêu cầu một cách tường minh.

**Lỗi 6 — Format specifier sai loại.** Ví dụ `String.format(Locale.US, "%d", 12.5)` gây `IllegalFormatConversionException` vì `%d` không nhận số thực `double`. Đặt locale khác không sửa được lỗi kiểu; cần chọn conversion phù hợp như `%.1f`.

## 9. Tự kiểm tra

**Câu 1.** Nếu mặc định `FORMAT` là `Locale.GERMANY`, dự đoán kết quả:

~~~java
String a = String.format("%,.2f", 1234.5);
String b = String.format(Locale.US, "%,.2f", 1234.5);
~~~

**Đáp án:** `a` là `"1.234,50"`; `b` là `"1,234.50"`.

**Câu 2.** Một API yêu cầu số thập phân dùng dấu chấm bất kể vùng địa lý của máy chủ. Nên chọn overload nào?

**Đáp án:** overload nhận `Locale`, ví dụ `String.format(Locale.US, "%.2f", value)` khi định dạng đó phù hợp với đặc tả API. Với JSON hoặc giao thức có serializer chuẩn, nên dùng serializer theo chuẩn đó.

**Câu 3.** Việc gọi `Locale.setDefault(Locale.Category.DISPLAY, Locale.US)` có bảo đảm `String.format("%,.2f", value)` dùng dấu phân cách Mỹ không?

**Đáp án:** Không. `String.format` mặc định xét `Locale.Category.FORMAT`; thay đổi riêng `DISPLAY` không xác lập `FORMAT`.

## 10. Ghi nhớ để áp dụng

Khi đọc một lời gọi `String.format`, hãy hỏi: **locale lấy từ đâu?** Nếu thiếu tham số locale, kết quả định dạng có thể phụ thuộc mặc định `FORMAT` của JVM. Nếu có `Locale` tường minh, hành vi bản địa hóa được kiểm soát tại lời gọi. Thiết kế tốt thường truyền locale người dùng khi hiển thị, truyền locale cố định theo đặc tả khi xuất dữ liệu máy đọc, và tránh thay đổi locale mặc định ở các luồng xử lý đồng thời.

Tài liệu API tham khảo: [`String.format` (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#format(java.util.Locale,java.lang.String,java.lang.Object...)), [`Formatter` (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html) và [`Locale` (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html).