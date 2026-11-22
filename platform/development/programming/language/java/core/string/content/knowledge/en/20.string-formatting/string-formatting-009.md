# MessageFormat khi mẫu cần đổi thứ tự theo ngôn ngữ

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích lý do dịch một câu bằng cách nối chuỗi cố định thường gây sai thứ tự từ, giới từ và cấu trúc ngữ pháp.
- Dùng `java.text.MessageFormat` với placeholder **theo chỉ số** `{0}`, `{1}`, `{2}` để đặt cùng dữ liệu vào các vị trí khác nhau ở từng bản dịch.
- Kết hợp `ResourceBundle` và `Locale` để chọn mẫu thông điệp theo ngôn ngữ, trong khi chương trình giữ nguyên thứ tự đối số truyền vào.
- Nhận biết cú pháp `MessageFormat` cho số, ngày giờ, dấu nháy đơn, dấu ngoặc nhọn và những giới hạn quan trọng khi quốc tế hóa (i18n).

## 1. Vì sao thay thứ tự theo ngôn ngữ là cần thiết?

Giả sử ứng dụng thông báo rằng **Lan gửi PDF cho Minh lúc 09:00**. Tiếng Anh và tiếng Việt có thể diễn đạt cùng một sự kiện nhưng đặt thời gian ở vị trí khác nhau:

- Tiếng Anh: “Lan sent PDF to Minh at 09:00.”
- Tiếng Việt: “Lúc 09:00, Lan gửi PDF cho Minh.”
- Tiếng Nhật (một cách diễn đạt minh họa): “09:00にLanがMinhへPDFを送りました。”

Cách ghép cứng như sau rất khó chuyển ngữ:

~~~java
String message = sender + " sent " + item + " to " + receiver + " at " + time;
~~~

Nếu dịch bằng cách thay riêng từ `sent` thành `gửi`, các từ nối hoặc thứ tự thành phần có thể vẫn sai. Cách phù hợp hơn là **dịch toàn bộ mẫu câu**, rồi để người dịch tự chọn vị trí của từng đối số.

`MessageFormat` nhận một **pattern** chứa placeholder đánh số, cùng một mảng đối số:

~~~text
English: {0} sent {2} to {1} at {3}.
Tiếng Việt: Lúc {3}, {0} gửi {2} cho {1}.
日本語: {3}に{0}が{1}へ{2}を送りました。
~~~

Cả ba mẫu dùng cùng ánh xạ:

| Chỉ số | Ý nghĩa | Giá trị minh họa |
| --- | --- | --- |
| `{0}` | Người gửi | `Lan` |
| `{1}` | Người nhận | `Minh` |
| `{2}` | Vật/tệp được gửi | `PDF` |
| `{3}` | Thời gian | `09:00` |

**Điểm cốt lõi:** chỉ số chỉ ra **đối số nào** được sử dụng, không buộc đối số phải xuất hiện theo thứ tự tăng dần. Mẫu có thể đặt `{3}` trước `{0}`, dùng lại `{0}` nhiều lần hoặc không dùng một đối số nào đó. Thứ tự các phần tử trong mảng truyền cho `format` vẫn ổn định.

## 2. Ví dụ Java 17+ chạy độc lập: thay thứ tự theo Locale

Lưu thành tệp `MessageOrderDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageOrderDemo {
    public static void main(String[] args) {
        Object[] values = {"Lan", "Minh", "PDF", "09:00"};

        String english = "{0} sent {2} to {1} at {3}.";
        String vietnamese = "Lúc {3}, {0} gửi {2} cho {1}.";
        String japanese = "{3}に{0}が{1}へ{2}を送りました。";

        System.out.println(
                new MessageFormat(english, Locale.ENGLISH).format(values));
        System.out.println(
                new MessageFormat(vietnamese, Locale.forLanguageTag("vi-VN"))
                        .format(values));
        System.out.println(
                new MessageFormat(japanese, Locale.JAPANESE).format(values));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 MessageOrderDemo.java
java MessageOrderDemo
~~~

Kết quả (xem bằng terminal hỗ trợ UTF-8):

~~~text
Lan sent PDF to Minh at 09:00.
Lúc 09:00, Lan gửi PDF cho Minh.
09:00にLanがMinhへPDFを送りました。
~~~

**Điều đáng chú ý:**

1. Mảng `values` chỉ được tạo **một lần** và có thứ tự cố định: người gửi, người nhận, vật được gửi, thời gian.
2. Tiếng Anh đặt `{3}` cuối câu; tiếng Việt và tiếng Nhật có thể đặt `{3}` lên đầu.
3. Không phải đổi thứ tự phần tử trong `values` cho từng `Locale`; mỗi pattern quyết định thứ tự xuất hiện.
4. Ví dụ dùng `String` như `"09:00"` và `"PDF"` để đầu ra xác định. Ở ứng dụng thực, nên biểu diễn thời gian, tiền tệ và các giá trị có định dạng bằng kiểu dữ liệu phù hợp, sau đó định dạng theo locale của người nhận.

Đối tượng `MessageFormat` có hai thành phần độc lập: **mẫu câu** để sắp thứ tự thành phần và **Locale** để điều khiển cách định dạng những loại dữ liệu nhạy với ngôn ngữ/khu vực như số hoặc ngày. Chọn một `Locale` không tự động dịch văn bản tiếng Anh trong pattern; chương trình phải cung cấp bản dịch của mẫu.

## 3. Cách MessageFormat hiểu placeholder

Cú pháp tổng quát thường gặp:

~~~text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
~~~

Trong đó:

- `argumentIndex` là số nguyên không âm, tính từ `0`; tương ứng với phần tử cùng chỉ số trong `Object[]` truyền vào `format`.
- `formatType` có thể là `number`, `date`, `time`, `choice` hoặc được bỏ qua nếu chỉ cần giá trị văn bản.
- `formatStyle` xác định kiểu hiển thị, ví dụ `short`, `medium`, `long` hoặc `integer` tùy `formatType`.

Ví dụ các mẫu:

| Pattern | Ý nghĩa |
| --- | --- |
| `"Xin chào {0}!"` | Chèn đối số thứ 0 |
| `"{1} đã mời {0}"` | Đảo vị trí hai đối số |
| `"{0} / {0}"` | Dùng cùng một đối số hai lần |
| `"Tổng số: {0,number,integer}"` | Định dạng đối số thứ 0 dưới dạng số nguyên theo locale |
| `"Ngày: {0,date,short}"` | Định dạng đối số ngày theo kiểu ngắn của locale |

`MessageFormat` **không dùng tên biến làm khóa placeholder** theo cú pháp Java chuẩn. `{sender}` không phải cú pháp thay thế tên hợp lệ của `java.text.MessageFormat`; hãy dùng `{0}` và ghi rõ quy ước ánh xạ giữa chỉ số với ý nghĩa của tham số. Nếu đổi vị trí các tham số trong mã nhưng quên cập nhật quy ước, mẫu dịch có thể hiển thị sai mà vẫn chạy.

Khi một mẫu đang yêu cầu một chỉ số không có trong `Object[]`, `MessageFormat` không thể lấy đúng giá trị dự định. Nên kiểm tra số lượng và kiểu đối số trong chương trình hoặc kiểm thử bản dịch. Không nên coi việc biên dịch được mã Java là bằng chứng rằng tất cả tài nguyên dịch đều đúng.

## 4. Tách câu dịch bằng ResourceBundle

Ví dụ phần 2 minh họa cơ chế với các chuỗi đặt ngay trong mã. Trong ứng dụng thật, các mẫu nên nằm trong tệp bản dịch, do `ResourceBundle` chọn theo `Locale`. Nhờ đó, nhóm dịch thuật có thể chỉnh vị trí placeholder mà không sửa logic Java.

Giả sử bốn tệp nằm **cùng thư mục** khi biên dịch/chạy:

~~~text
LocalizedMessageDemo.java
messages.properties
messages_en.properties
messages_vi.properties
messages_ja.properties
~~~

Nội dung `messages.properties` — giá trị mặc định nếu không có bản dịch phù hợp:

~~~properties
sent={0} sent {2} to {1} at {3}.
~~~

Nội dung `messages_en.properties`:

~~~properties
sent={0} sent {2} to {1} at {3}.
~~~

Nội dung `messages_vi.properties`:

~~~properties
sent=Lúc {3}, {0} gửi {2} cho {1}.
~~~

Nội dung `messages_ja.properties`:

~~~properties
sent={3}に{0}が{1}へ{2}を送りました。
~~~

Lưu chương trình sau vào `LocalizedMessageDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocalizedMessageDemo {
    private static String buildMessage(Locale locale, Object[] values) {
        ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);
        String pattern = bundle.getString("sent");
        return new MessageFormat(pattern, locale).format(values);
    }

    public static void main(String[] args) {
        Object[] values = {"Lan", "Minh", "PDF", "09:00"};

        System.out.println(buildMessage(Locale.ENGLISH, values));
        System.out.println(
                buildMessage(Locale.forLanguageTag("vi-VN"), values));
        System.out.println(buildMessage(Locale.JAPANESE, values));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LocalizedMessageDemo.java
java LocalizedMessageDemo
~~~

Kết quả:

~~~text
Lan sent PDF to Minh at 09:00.
Lúc 09:00, Lan gửi PDF cho Minh.
09:00にLanがMinhへPDFを送りました。
~~~

Luồng xử lý:

1. `ResourceBundle.getBundle("messages", locale)` tra cứu nhóm tài nguyên có tên gốc `messages` và chọn bản dịch phù hợp. Chẳng hạn `vi-VN` có thể tìm bản quốc gia trước, sau đó dùng bản ngôn ngữ `messages_vi.properties`.
2. `bundle.getString("sent")` lấy nguyên mẫu thông điệp cho khóa `sent`. Khóa giữ ổn định; nội dung pattern có thể khác nhau ở từng ngôn ngữ.
3. `new MessageFormat(pattern, locale)` tạo bộ định dạng với locale cụ thể.
4. `format(values)` áp dụng các placeholder lên đúng phần tử của mảng, bất kể thứ tự xuất hiện trong câu.

Từ Java 9 trở lên, bộ đọc `ResourceBundle` cho `.properties` hỗ trợ UTF-8 (có cơ chế fallback lịch sử), vì vậy văn bản tiếng Việt hoặc tiếng Nhật có thể lưu trực tiếp trong các tệp tài nguyên UTF-8. Hãy kiểm soát encoding của trình biên tập và môi trường chạy để tránh hiển thị lỗi ký tự. Nếu tệp bản dịch và khóa cần thiết không tồn tại trong đường tìm kiếm, các thao tác `getBundle`/`getString` có thể ném `MissingResourceException`.

### Giữ hợp đồng về tham số khi dịch

Tạo quy ước có thể kiểm thử cho từng khóa:

~~~text
sent:
  {0} = sender / người gửi (String)
  {1} = recipient / người nhận (String)
  {2} = item / vật được gửi (String)
  {3} = time / thời gian đã được định dạng để hiển thị (String)
~~~

Người dịch được phép **đổi thứ tự placeholder trong pattern**, nhưng không được âm thầm đổi ý nghĩa của từng chỉ số. Nếu bản dịch viết nhầm `{4}` hoặc đổi `{1}` thành người gửi, kết quả sẽ sai. Hãy kiểm tra mọi locale được hỗ trợ và các giá trị thực tế, thay vì chỉ kiểm thử ngôn ngữ mặc định.

### Lưu ý về fallback

`ResourceBundle` có quy tắc tra cứu biến thể ngôn ngữ/quốc gia và có thể xét cả locale mặc định của JVM trước khi dùng bundle gốc trong một số tình huống. Bởi vậy, nên có bundle nền `messages.properties`, đặt `messages_en.properties` khi cần bản tiếng Anh xác định, và viết bài kiểm thử với locale rõ ràng. Đừng giả định thiếu một bản dịch luôn đồng nghĩa chắc chắn dùng bundle gốc ngay lập tức.

## 5. Định dạng số, ngày và thời gian theo Locale

Đổi thứ tự thành phần chỉ là một phần của bản địa hóa. Với giá trị có cấu trúc, `MessageFormat` còn có cú pháp định dạng trực tiếp:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class LocaleNumberDemo {
    public static void main(String[] args) {
        Object[] values = {"Lan", 1234.5};

        String en = "{0}: {1,number}";
        String vi = "Số điểm của {0}: {1,number}";

        System.out.println(
                new MessageFormat(en, Locale.US).format(values));
        System.out.println(
                new MessageFormat(vi, Locale.forLanguageTag("vi-VN"))
                        .format(values));
    }
}
~~~

Lưu `LocaleNumberDemo.java` và chạy bằng `javac -encoding UTF-8 LocaleNumberDemo.java`, sau đó `java LocaleNumberDemo`. Dấu phân cách hàng nghìn và dấu thập phân trong hai dòng có thể khác nhau theo dữ liệu locale mà bản Java đang sử dụng, nên hãy quan sát chính ký tự được in ra (bao gồm khoảng trắng đặc biệt), thay vì cố định đáp án kiểu dấu phân cách.

Một số quy tắc đáng nhớ:

- `{0,number}` và `{0,number,integer}` dùng định dạng số theo `Locale`; `integer` liên quan đến **định dạng/làm tròn số để hiển thị**, không biến đầu vào thành kiểu nguyên.
- `{0,number,currency}` dùng định dạng tiền tệ theo locale của formatter. Nếu cần chỉ rõ loại tiền tệ kinh doanh (ví dụ USD so với VND), phải quản lý `Currency` và `NumberFormat` riêng để tránh nhầm ký hiệu/đơn vị.
- `{0,date,short}` và `{0,time,short}` cần đối số ngày/giờ tương thích, thường là `java.util.Date`; không truyền chuỗi ngày tùy ý rồi mong formatter tự nhận dạng.
- Các định dạng ngày/giờ truyền thống bên dưới `MessageFormat` có thể dùng múi giờ mặc định của JVM. Nếu ứng dụng phải hiển thị một múi giờ cố định, hãy kiểm soát timezone thông qua formatter thích hợp hoặc chuẩn bị giá trị đã được bản địa hóa trước.
- Với API `java.time` hiện đại, `DateTimeFormatter` hỗ trợ nhiều kiểu thời gian, locale và timezone rõ ràng hơn. Có thể dùng nó định dạng thành `String` trước khi gắn vào mẫu `MessageFormat`, đặc biệt khi làm việc với `Instant`, `ZonedDateTime` hoặc lịch trình đa múi giờ.

Cũng cần phân biệt **dịch ngữ pháp** với **định dạng giá trị**: đảo `{1}` và `{0}` giải quyết thứ tự tham số, nhưng không tự dịch tên sản phẩm, danh từ số ít/số nhiều hay biểu thức thời gian. Các dữ liệu hiển thị đó phải được bản địa hóa tương ứng khi nghiệp vụ yêu cầu.

## 6. Dấu nháy đơn và ngoặc nhọn: bẫy cú pháp MessageFormat

`MessageFormat` có cú pháp riêng: dấu nháy đơn `'` dùng để quote đoạn của pattern, còn `{...}` dùng cho placeholder. Điều này đặc biệt quan trọng khi dịch thông điệp sang ngôn ngữ có dấu apostrophe.

Ví dụ Java 17:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageQuoteDemo {
    public static void main(String[] args) {
        Object[] values = {"done"};

        System.out.println(new MessageFormat(
                "It's {0}.", Locale.ENGLISH).format(values));

        System.out.println(new MessageFormat(
                "It''s {0}.", Locale.ENGLISH).format(values));

        System.out.println(new MessageFormat(
                "Use '{' and '}' around {0}.", Locale.ENGLISH)
                .format(new Object[] {"x"}));
    }
}
~~~

Lưu `MessageQuoteDemo.java` rồi chạy `javac -encoding UTF-8 MessageQuoteDemo.java` và `java MessageQuoteDemo`. Kết quả:

~~~text
Its {0}.
It's done.
Use { and } around x.
~~~

**Vì sao dòng đầu đáng ngạc nhiên?** Trong pattern `"It's {0}."`, dấu `'` đơn có thể mở một vùng quote và làm `{0}` còn là ký tự literal, khiến placeholder không được thay. Viết `"It''s {0}."` để biểu diễn dấu apostrophe thật khi dùng cú pháp `MessageFormat`.

Để hiển thị dấu ngoặc nhọn mà không bắt đầu placeholder, có thể quote chúng trong pattern như `"'{' "` hoặc `"'}'"` (ví dụ `"Use '{' and '}' around {0}."`). Không dùng quy tắc escape của Java String hoặc regex để tự suy đoán quy tắc của `MessageFormat`; đây là một ngữ pháp khác.

Trong `.properties`, cần phân biệt escape của định dạng tệp, escape của chuỗi Java và cú pháp `MessageFormat`. Ví dụ: bản dịch có từ chứa apostrophe thật vẫn phải tuân thủ quy tắc nhân đôi `''` khi đưa vào `MessageFormat`, kể cả nếu nội dung đã được nạp từ `ResourceBundle`.

## 7. MessageFormat khác String.format như thế nào?

Cả hai đều hỗ trợ format tham số, nhưng cú pháp và mục đích thường khác nhau:

| Tiêu chí | `MessageFormat` | `String.format` / `Formatter` |
| --- | --- | --- |
| Placeholder | `{0}`, `{1}`, `{0,number}` | `%s`, `%d`, `%.2f` |
| Đổi vị trí tham số trong mẫu | Chỉ số `{2}`, `{0}` | Chỉ số đối số `%2$s`, `%1$s` |
| Mẫu trong tệp bản dịch | Dùng tốt với `ResourceBundle` và `Locale` | Cũng dùng được nhưng phải giữ đúng cú pháp `%...` |
| Số/ngày theo locale | Cú pháp `number/date/time` tích hợp | Bộ định dạng có các conversion và flag riêng |
| Dấu đặc biệt cần lưu ý | Apostrophe `'`, ngoặc `{ }` | Dấu phần trăm `%`, conversion ký tự |
| Lựa chọn thực tế | Mẫu thông báo i18n với vị trí đối số và kiểu trình bày tùy ngôn ngữ | Xuất chuỗi có đặc tả kiểu/độ rộng/chính xác, log, bảng số liệu |

`MessageFormat` không phải cách duy nhất để hoán đổi thứ tự đối số: `String.format` cũng hỗ trợ tham chiếu vị trí. Trong bài này, `MessageFormat` là lựa chọn phù hợp vì ứng dụng **đã dùng mẫu thông điệp theo locale** và có thể tận dụng cú pháp dành cho hiển thị số/ngày trong tài nguyên dịch.

Không trộn cú pháp: truyền `"%2$s -> %1$s"` cho `MessageFormat` sẽ không khiến các specifier kiểu `Formatter` được thay thế; và truyền `"{1} -> {0}"` cho `String.format` cũng không hiểu placeholder kiểu `MessageFormat`.

## 8. Các lỗi phổ biến và cách tránh

**Lỗi 1 — Ghép câu từng từ rồi mới dịch.** Việc thêm từ nối bằng toán tử `+` hoặc placeholder rời rạc có thể gây sai ngữ pháp khi ngôn ngữ đòi đảo vị trí thành phần. Hãy dịch **mẫu câu hoàn chỉnh**, để người dịch quyết định vị trí `{0}`, `{1}`.

**Lỗi 2 — Thay thứ tự dữ liệu để phục vụ bản dịch.** Sửa `Object[]` theo từng `Locale` làm mất hợp đồng của chỉ số. Giữ thứ tự đối số trong code, đổi chỉ thứ tự placeholder ở tài nguyên dịch.

**Lỗi 3 — Viết nhầm chỉ số hoặc loại đối số.** Mẫu `{2,number}` sẽ gặp vấn đề nếu đối số 2 là `"PDF"` thay vì số. Định nghĩa bảng hợp đồng tham số, kiểm thử mọi bản dịch và những giá trị có kiểu dữ liệu thực tế.

**Lỗi 4 — Nghĩ Locale tự dịch câu.** `Locale.forLanguageTag("vi-VN")` chỉ cho formatter biết quy tắc vùng/ngôn ngữ. Muốn có câu tiếng Việt, phải nạp mẫu tiếng Việt qua `ResourceBundle` hoặc hệ thống i18n tương đương.

**Lỗi 5 — Không escape apostrophe trong MessageFormat.** Dấu `'` đơn trong pattern có thể khiến placeholder không còn được xử lý. Dùng `''` khi phải hiển thị apostrophe literal và kiểm tra bản dịch có dấu nháy.

**Lỗi 6 — Chỉ dịch mẫu nhưng bỏ quên giá trị.** Nếu đưa `"Monday"`, `"a report"` hoặc chuỗi ngày kiểu Mỹ vào mẫu tiếng Việt, kết quả vẫn có nội dung không phù hợp. Phải bản địa hóa cả các giá trị mang ngôn ngữ/định dạng khu vực.

**Lỗi 7 — Dùng một MessageFormat mutable chung nhiều luồng.** `MessageFormat` có trạng thái thay đổi và không đảm bảo thread-safe. Tạo formatter mới theo thao tác hoặc dùng bản sao riêng cho từng luồng. Nếu cần hiệu năng, quản lý cache pattern/bundle và chiến lược formatter riêng có kiểm soát thay vì chia sẻ cùng đối tượng đang bị chỉnh sửa.

**Lỗi 8 — Xem thông điệp i18n là hệ thống pluralization toàn năng.** Java `MessageFormat` chuẩn hỗ trợ cú pháp `choice` cho một số tình huống số lượng, nhưng không cung cấp đầy đủ mọi quy tắc giống/biến cách/số ít số nhiều của mọi ngôn ngữ. Khi cần plural/gender phức tạp, cân nhắc thư viện i18n chuyên dụng như ICU MessageFormat và mô hình dịch phù hợp; không tự ghép hậu tố `"s"` theo logic tiếng Anh.

**Lỗi 9 — Không kiểm thử tất cả locale.** Bản tiếng Anh đúng chưa đảm bảo bản tiếng Việt hoặc tiếng Nhật đúng. Hãy chạy thử với cả giá trị thông thường, chuỗi rỗng, số/ngày khác biệt, ký tự đặc biệt, giới hạn chỗ hiển thị và thứ tự placeholder đã bị đảo.

**Lỗi 10 — Tin rằng formatter tự escape HTML hoặc mã lệnh.** `MessageFormat` chỉ tạo chuỗi hiển thị; nó không tự làm sạch HTML, SQL hay nội dung đưa vào một ngữ cảnh có rủi ro. Khi hiển thị trên web, áp dụng escaping theo chính ngữ cảnh đầu ra, và tránh sử dụng pattern không tin cậy làm nội dung điều khiển.

## 9. Thực hành: tự dự đoán kết quả

Cho dữ liệu:

~~~java
Object[] values = {"Mai", "Lan", "file.zip", "10:30"};
~~~

Và các mẫu:

~~~text
A = "{0} gửi {2} cho {1} lúc {3}."
B = "Vào {3}, {1} nhận {2} từ {0}."
C = "{0} đã gửi; người gửi là {0}."
~~~

Thử thay từng chỉ số trong đầu trước khi chạy chương trình:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class OrderQuiz {
    public static void main(String[] args) {
        Object[] values = {"Mai", "Lan", "file.zip", "10:30"};
        String[] patterns = {
            "{0} gửi {2} cho {1} lúc {3}.",
            "Vào {3}, {1} nhận {2} từ {0}.",
            "{0} đã gửi; người gửi là {0}."
        };
        for (String pattern : patterns) {
            System.out.println(new MessageFormat(
                    pattern, Locale.forLanguageTag("vi-VN")).format(values));
        }
    }
}
~~~

Lưu `OrderQuiz.java` rồi chạy bằng `javac -encoding UTF-8 OrderQuiz.java` và `java OrderQuiz`. Kết quả:

~~~text
Mai gửi file.zip cho Lan lúc 10:30.
Vào 10:30, Lan nhận file.zip từ Mai.
Mai đã gửi; người gửi là Mai.
~~~

Ba câu cùng dùng một mảng dữ liệu. Pattern có thể **đổi chỗ**, **lặp lại** hoặc **không dùng** một đối số; người viết template kiểm soát cách diễn đạt mà không đổi logic truyền dữ liệu.

### Checklist áp dụng trong dự án

1. Đặt khóa thông điệp có ý nghĩa ổn định như `sent`, `payment.received`, `notification.invite`.
2. Ghi tài liệu chỉ số `{0}`, `{1}`, ... kèm kiểu và ý nghĩa, rồi giữ hợp đồng đó cho tất cả locale.
3. Dịch toàn câu trong từng resource bundle; cho phép đổi vị trí placeholder và điều chỉnh từ nối cho tự nhiên.
4. Nạp pattern theo `Locale`, tạo `MessageFormat(pattern, locale)` và đưa vào **cùng một thứ tự tham số**.
5. Kiểm thử bản dịch có placeholder bị thiếu/sai, dấu apostrophe, định dạng số/ngày, fallback bundle và văn bản dài hơn dự kiến.

## Tài liệu chính thức

- [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html)
- [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html)
- [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html)
- [Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html)
- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
