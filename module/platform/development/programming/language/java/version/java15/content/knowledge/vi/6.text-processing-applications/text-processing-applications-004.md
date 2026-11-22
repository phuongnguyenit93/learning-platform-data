# Template email, thông báo và dữ liệu nhiều ngôn ngữ bằng Java text block

## 1. Khi nào nên dùng text block?

Từ **Java 15**, text block (ba dấu nháy kép `"""`) là cú pháp chính thức để tạo `String` nhiều dòng. Nó phù hợp khi một ứng dụng cần giữ bố cục **email dạng văn bản**, **thông báo nhiều dòng**, hoặc **đoạn dữ liệu/văn bản mẫu theo ngôn ngữ** ngay trong mã Java. Text block giúp thấy cấu trúc thông điệp ngay khi đọc code, giảm việc phải nối chuỗi với `+` và viết nhiều escape `\n`.

Ví dụ một email đơn giản:

```java
String message = """
        Xin chào,

        Lịch hẹn của bạn đã được xác nhận.

        Trân trọng,
        Nhóm hỗ trợ
        """;
```

Giá trị `message` chứa đúng các dòng hiển thị, gồm dòng trống giữa các đoạn và **một LF (`\n`) ở cuối**. Dấu xuống dòng bắt buộc ngay sau `"""` mở không tự tạo dòng trống đầu tiên; phần thụt lề chung trong mã nguồn được loại bỏ theo quy tắc text block.

**Giới hạn quan trọng:** text block chỉ là **cú pháp khai báo `String`**, không phải công cụ template đầy đủ. Nó **không** tự nội suy biến, dịch ngôn ngữ, escape HTML/JSON, định dạng ngày giờ theo quốc gia, gửi email hay xác thực dữ liệu. Các việc này thuộc logic Java hoặc thư viện chuyên dụng.

Bài này tập trung vào ba ứng dụng thực tế: soạn email, tạo thông báo, và quản lý nội dung đa ngôn ngữ. Các tính năng nêu ra vẫn được hỗ trợ trong Java hiện hành.

## 2. Bố cục email: xuống dòng, thụt lề và dấu đóng

Xét hai mẫu sau:

```java
String endsWithLineFeed = """
        Hello,

        Your request is approved.
        """;

String noFinalLineFeed = """
        Hello,

        Your request is approved.""";
```

Mẫu thứ nhất có giá trị tương đương `"Hello,\n\nYour request is approved.\n"`, mẫu thứ hai tương đương `"Hello,\n\nYour request is approved."`. Sự khác biệt là **ký tự LF cuối cùng**, vì dấu đóng của mẫu thứ nhất nằm ở dòng riêng; dấu đóng của mẫu thứ hai nằm ngay sau dấu chấm.

Thứ tự xử lý nội dung text block là: **chuẩn hóa kết thúc dòng thành LF → loại phần thụt lề/khoảng trắng không chủ ý → xử lý escape**. Vì vậy:

- Xuống dòng vật lý trong mã nguồn, dù tệp dùng CRLF trên Windows, được chuẩn hóa thành **LF** trong giá trị `String`.
- Phần lề dùng để căn chỉnh source code không mặc nhiên xuất hiện trong email; nếu muốn thụt đầu dòng có ý nghĩa, cần thiết kế lề nội dung phù hợp hoặc tạo khoảng trắng có chủ ý.
- Các dấu cách thừa ở cuối dòng thường bị loại. Escape `\s` có thể giữ dấu cách nếu định dạng thực sự yêu cầu, nhưng email văn bản thông thường không nên dựa vào khoảng trắng cuối dòng.
- `println(email)` còn tự in thêm kết thúc dòng của môi trường; khi kiểm tra chính xác, hãy dùng `email.endsWith("\n")`, `email.length()` hoặc hiển thị LF thành ký hiệu nhìn thấy.

**Email có nhiều thành phần:** subject, người nhận, người gửi, định dạng nội dung và thông tin đính kèm là **các trường riêng** của một thông điệp MIME/email. Text block thường dùng cho **body**; không ghép header giao thức và địa chỉ vào một khối văn bản rồi coi như đã gửi được email.

## 3. Chèn dữ liệu động vào mẫu

Java **không có cú pháp tự nội suy** kiểu `\${name}` trong text block. Muốn thay biến vào nội dung, có thể dùng placeholder của `Formatter` và `String.formatted(...)` (có từ Java 15):

```java
String emailTemplate = """
        Xin chào %s,

        Đơn hàng %s của bạn đã được tiếp nhận.
        """;

String email = emailTemplate.formatted("Linh", "DH-42");
```

`email` có giá trị:

```text
Xin chào Linh,

Đơn hàng DH-42 của bạn đã được tiếp nhận.
```

Và có **LF cuối chuỗi**, vì dấu đóng của template ở dòng riêng. Các quy tắc của `Formatter` cần được hiểu đúng:

- `%s` nhận đối số theo thứ tự truyền vào; nếu thiếu đối số, Java có thể ném `MissingFormatArgumentException`.
- `%1$s`, `%2$s` cho phép chỉ rõ vị trí, hữu ích khi mỗi bản dịch cần **đổi thứ tự thông tin**.
- `%%` biểu diễn dấu phần trăm trong **mẫu định dạng**; ví dụ `"Giảm 20%%".formatted()` cho `"Giảm 20%"`.
- `formatted` **không tự dịch nội dung**. Nó sử dụng định dạng của `Formatter` và locale mặc định cho các chuyển đổi nhạy cảm ngôn ngữ; với số, tiền tệ hoặc ngày giờ, nên chọn `Locale` tường minh và các API định dạng thích hợp.

Ví dụ placeholder có vị trí, chỉ là một đoạn minh họa có thể đặt trong phương thức Java:

```java
String vi = "Đơn %2$s của %1$s đã xác nhận.";
String en = "%1$s: order %2$s confirmed.";
System.out.println(vi.formatted("Linh", "DH-42"));
System.out.println(en.formatted("Linh", "DH-42"));
```

Hai dòng lần lượt là `Đơn DH-42 của Linh đã xác nhận.` và `Linh: order DH-42 confirmed.`. Thay đổi thứ tự placeholder không làm thay đổi thứ tự mảng dữ liệu truyền vào.

**Không trộn cú pháp template:** `%s` thuộc `Formatter`; `{0}` thuộc `MessageFormat`. Không thể đưa một mẫu `{0}` cho `formatted` rồi mong nó được thay tự động.

## 4. Thông báo ứng dụng, push và SMS

Text block cũng hữu ích cho thông báo có nhiều dòng:

```java
String notificationTemplate = """
        Giao dịch %s đã hoàn tất.
        Số tham chiếu: %s
        """;
```

Tuy nhiên, không phải kênh nào cũng hiển thị xuống dòng giống nhau. Một thông báo push có thể bị cắt bớt, SMS giới hạn độ dài theo cách mã hóa và phân đoạn của nhà cung cấp, còn thông báo trong ứng dụng có thể giữ bố cục nhiều dòng. Vì vậy, nên xem **title**, **preview/summary** và **body** là các trường nội dung riêng khi yêu cầu sản phẩm khác nhau.

Mẫu một dòng cho banner hay push có thể đơn giản là string literal:

```java
String shortNotice = "Đơn %s đã được xác nhận.".formatted("DH-42");
```

Chỉ chọn text block nếu bố cục nhiều dòng giúp ích cho việc đọc và bảo trì. Text block tạo giá trị chuỗi; việc **gửi** qua push, SMS, email hay hiển thị trong giao diện vẫn cần API/kênh tương ứng.

Đối với dữ liệu người dùng nhập vào, hãy xác thực giới hạn độ dài và ký tự được phép, đặc biệt ở tiêu đề hoặc trường chỉ cho phép một dòng. Đừng để giá trị chứa CR/LF không kiểm soát phá bố cục hoặc bị đưa trực tiếp vào header gửi email.

## 5. Dùng Locale để chọn bản dịch, không tự động dịch

`Locale` mô tả quy ước ngôn ngữ/vùng, ví dụ `Locale.forLanguageTag("vi-VN")` và `Locale.ENGLISH`. Một text block **không tự biết** người dùng muốn tiếng Việt hay tiếng Anh. Ứng dụng phải chọn nội dung tương ứng.

Với một chương trình nhỏ, có thể giữ các template theo mã ngôn ngữ trong `Map`:

```java
String vietnamese = """
        Xin chào %s,
        Lịch hẹn %s đã được xác nhận.
        """;

String english = """
        Hello %s,
        Appointment %s is confirmed.
        """;
```

Đây là hai mẫu **riêng biệt**, không phải kết quả dịch tự động của Java. Khi cần hỗ trợ nhiều ngôn ngữ, hãy quản lý bản dịch có phiên bản, người duyệt, khóa thông điệp, chính sách fallback và kiểm thử từng ngôn ngữ.

Dùng `locale.getLanguage()` để chọn `vi` hoặc `en` phù hợp với ví dụ hai ngôn ngữ này. Nếu sản phẩm phân biệt các biến thể vùng như `pt-BR` và `pt-PT`, cần chiến lược chọn theo **language tag đầy đủ**, thay vì chỉ theo mã ngôn ngữ.

**Định dạng theo locale là trách nhiệm riêng:** cùng một dữ liệu `LocalDate`, `BigDecimal` hoặc đơn vị tiền có thể cần cách trình bày khác nhau. Nên dùng `DateTimeFormatter`, `NumberFormat` hay API định dạng theo `Locale`, thay vì tự ghép dấu phân cách ngày, số hoặc tiền vào text block. Câu chữ của ngôn ngữ cũng cần người dịch hoặc hệ thống quản lý bản dịch.

## 6. Ví dụ hoàn chỉnh: email và thông báo tiếng Việt/tiếng Anh

Chương trình sau dùng **Java 15+**, không phụ thuộc thư viện bên ngoài. Nó giữ riêng subject, email body và notification, chọn bản dịch theo `Locale`, chèn dữ liệu bằng `formatted` và hiển thị ký tự xuống dòng dưới dạng chữ `\\n` để đối chiếu dễ dàng. Giá trị ngày ở dạng ISO là dữ liệu mẫu cố định để stdout ổn định trên mọi môi trường.

Lưu vào tệp **`MessageTemplateDemo.java`** (mã nguồn UTF-8):

```java
import java.util.Locale;
import java.util.Map;

public class MessageTemplateDemo {
    static final class Templates {
        final String subject;
        final String email;
        final String notification;

        Templates(String subject, String email, String notification) {
            this.subject = subject;
            this.email = email;
            this.notification = notification;
        }
    }

    private static final Map<String, Templates> CATALOG = Map.of(
        "vi", new Templates(
            "Xác nhận lịch hẹn %s",
            """
                Xin chào %s,

                Lịch hẹn %s đã được xác nhận.
                Ngày: %s

                Trân trọng,
                Nhóm hỗ trợ
                """,
            "Lịch hẹn %s đã được xác nhận."
        ),
        "en", new Templates(
            "Appointment %s confirmed",
            """
                Hello %s,

                Appointment %s is confirmed.
                Date: %s

                Regards,
                Support team
                """,
            "Appointment %s is confirmed."
        )
    );

    private static void render(Locale locale) {
        Templates selected = CATALOG.getOrDefault(
                locale.getLanguage(), CATALOG.get("en"));
        String bookingId = "A42";
        String dateIso = "2026-11-08";
        String subject = selected.subject.formatted(bookingId);
        String body = selected.email.formatted("Linh", bookingId, dateIso);
        String notice = selected.notification.formatted(bookingId);

        System.out.println("language=" + locale.getLanguage());
        System.out.println("subject=" + subject);
        System.out.println("body=" + body.replace("\n", "\\n"));
        System.out.println("notification=" + notice);
    }

    public static void main(String[] args) {
        render(Locale.forLanguageTag("vi-VN"));
        render(Locale.ENGLISH);
    }
}
```

Trong thư mục có tệp:

```bash
javac -encoding UTF-8 MessageTemplateDemo.java
java MessageTemplateDemo
```

**Stdout chính xác** (mỗi `\\n` trong dòng `body=` là **hai ký tự hiển thị** backslash và chữ `n`, do hàm `replace` dùng để quan sát LF thật của body):

```text
language=vi
subject=Xác nhận lịch hẹn A42
body=Xin chào Linh,\n\nLịch hẹn A42 đã được xác nhận.\nNgày: 2026-11-08\n\nTrân trọng,\nNhóm hỗ trợ\n
notification=Lịch hẹn A42 đã được xác nhận.
language=en
subject=Appointment A42 confirmed
body=Hello Linh,\n\nAppointment A42 is confirmed.\nDate: 2026-11-08\n\nRegards,\nSupport team\n
notification=Appointment A42 is confirmed.
```

Kết quả này đã được thiết kế để phân biệt **LF thực** trong email body với xuống dòng do `println` kết thúc mỗi dòng log. Với locale không có trong `CATALOG`, phương thức `getOrDefault` chọn mẫu tiếng Anh theo chính sách fallback của ví dụ. Đó là một **quyết định ứng dụng**, không phải cơ chế dịch tự động của `Locale`.

Có thể đổi riêng nội dung subject, body, notification hoặc bổ sung mã ngôn ngữ mà không phải sửa thuật toán hiển thị. Khi đưa vào hệ thống thật, thay các giá trị mẫu bằng dữ liệu đã xác thực và cấu hình locale từ người dùng.

## 7. Khi nội dung đa ngôn ngữ lớn hơn ví dụ

Các text block hard-code phù hợp với số lượng mẫu nhỏ, ổn định, do lập trình viên quản lý. Khi có nhiều câu dịch hoặc quy trình biên dịch nội dung độc lập, `ResourceBundle` và các tệp bản dịch là hướng chuẩn của Java.

Ví dụ cấu trúc file UTF-8:

```text
src/main/resources/
  messages.properties
  messages_vi.properties
```

`messages.properties` là gói cơ sở có nội dung mặc định (ở đây dùng tiếng Anh):

```properties
email.subject=Appointment %s confirmed
notice.confirmed=Appointment %s is confirmed.
```

`messages_vi.properties` chứa bản dịch:

```properties
email.subject=Xác nhận lịch hẹn %s
notice.confirmed=Lịch hẹn %s đã được xác nhận.
```

Đoạn Java sử dụng (minh họa trong một phương thức, cần hai file cấu hình ở classpath):

```java
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);
String subject = bundle.getString("email.subject").formatted("A42");
```

Cần `import java.util.Locale;` và `import java.util.ResourceBundle;`. Từ Java 9, `PropertyResourceBundle` mặc định đọc file properties dạng UTF-8 (có cơ chế fallback khi byte không phải UTF-8 hợp lệ). Vì thế, viết trực tiếp tiếng Việt có dấu bằng UTF-8 là phù hợp với Java 15+.

Một số lưu ý khi thiết kế bản dịch:

- Khóa như `email.subject` nên ổn định, dùng chung giữa các ngôn ngữ; thiếu khóa có thể làm `ResourceBundle` báo `MissingResourceException`. Cần quy trình kiểm tra khóa khi phát hành.
- Đặt gói cơ sở `messages.properties` rõ ràng cho fallback; quá trình chọn bundle còn chịu quy tắc tìm locale/default-locale của `ResourceBundle`. Đừng giả định mọi trường hợp thiếu bản dịch đều tự chọn chính xác ngôn ngữ mong muốn.
- File `.properties` không tự cung cấp cú pháp text block của Java. Email nhiều đoạn/dòng có thể lưu trong file template UTF-8 riêng hoặc dùng template engine được dự án lựa chọn; đừng nhét text block Java `"""` vào properties rồi mong Java tự biên dịch nó.
- Khi ngôn ngữ cần đảo thứ tự biến, sử dụng `%1$s`, `%2$s` nếu đang theo `Formatter`; hoặc dùng `MessageFormat` với **cú pháp riêng** `{0}`, `{1}` và `Locale`. `MessageFormat` có quy tắc xử lý dấu nháy đơn riêng, cần được kiểm thử với bản dịch thực.
- Số nhiều, giống ngữ pháp và cách xưng hô không giải quyết được chỉ bằng cách thêm nhiều text block; cần bản dịch và quy tắc phù hợp từng ngôn ngữ.

## 8. Dữ liệu nhiều ngôn ngữ dạng JSON/HTML: text block chỉ giữ văn bản

Text block giúp ghi **JSON tĩnh** dễ đọc, chẳng hạn một catalog nhỏ:

```java
String catalogJson = """
        {
          "vi": {
            "title": "Đã xác nhận",
            "message": "Lịch hẹn đã được ghi nhận."
          },
          "en": {
            "title": "Confirmed",
            "message": "Your appointment has been recorded."
          }
        }
        """;
```

Đây là một `String` chứa văn bản JSON tĩnh; Java **không tự parse, kiểm tra schema hay tự chuyển nó thành Map**. Nếu cần đọc JSON, hãy dùng thư viện JSON được dự án hỗ trợ. Nếu giá trị JSON **động**, không chèn dữ liệu người dùng trực tiếp vào `"""{"name":"%s"}""".formatted(userInput)` vì dấu `"`, backslash hay ký tự điều khiển trong dữ liệu có thể làm hỏng JSON hoặc thay đổi ý nghĩa. Dùng **JSON serializer** để tạo chuỗi hợp lệ và escape đúng theo JSON.

Với HTML email, text block cũng chỉ là `String` chứa markup; `formatted` không escape ký tự `<`, `>`, `&`, `"` trong biến. Nội dung không tin cậy phải được **HTML-encode theo đúng ngữ cảnh** (text node, attribute, URL...) hoặc dùng thư viện template có escaping phù hợp. Đừng coi việc chuyển sang text block là biện pháp chống chèn mã.

Dữ liệu đa ngôn ngữ cần đi qua các lớp theo đúng trách nhiệm:

1. **Chọn ngôn ngữ:** ngôn ngữ của người dùng/yêu cầu và chính sách fallback.
2. **Chọn template:** khóa thông điệp phù hợp kênh (email subject, email body, push title/body, SMS).
3. **Định dạng giá trị:** ngày, giờ, số, đơn vị, tiền theo locale và nghiệp vụ.
4. **Escape theo đích:** plain text, HTML, JSON hay header email có quy tắc khác nhau.
5. **Gửi/hiển thị:** ứng dụng/nhà cung cấp gửi chịu trách nhiệm MIME, charset, transport và các giới hạn của kênh.

## 9. UTF-8, email và các ký tự xuống dòng

Mã nguồn Java có thể chứa tiếng Việt trong text block; dùng `javac -encoding UTF-8` để cách đọc tệp rõ ràng, đặc biệt trên môi trường build không đồng nhất. Khi biến `String` thành byte để ghi tệp hoặc gửi dữ liệu, chọn charset tường minh:

```java
byte[] utf8 = email.getBytes(java.nio.charset.StandardCharsets.UTF_8);
```

Đây chỉ là thao tác **mã hóa dữ liệu thành byte**; không tự tạo thư MIME hay gửi email. Khi gửi email thực tế, hãy dùng thư viện email đang được hỗ trợ trong dự án, đặt kiểu nội dung và charset phù hợp như `text/plain; charset=UTF-8` cho body văn bản thuần, và để thư viện xử lý cấu trúc MIME/header.

Text block chuẩn hóa **xuống dòng vật lý** thành LF. Kết thúc dòng yêu cầu bởi một giao thức gửi cụ thể là trách nhiệm của tầng giao thức/serializer, không nên tùy tiện thay mọi `\n` bằng `\r\n` trong template mà chưa biết quy định của tầng nhận.

Nếu payload được ghi ra tệp để các hệ thống khác tiêu thụ, kiểm tra cả **charset** và **line ending**. Dấu tiếng Việt bị biến thành ký tự lạ thường do dùng sai encoding; sự khác nhau giữa `LF` và `CRLF` là vấn đề riêng, không phải lỗi Unicode.

## 10. Những lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Email bị dư dòng trắng | Thêm `\n` tường minh bên cạnh xuống dòng vật lý; hoặc dấu đóng trên dòng riêng | So sánh giá trị với chuỗi kỳ vọng; dùng `endsWith("\n")` và hiển thị ký tự điều khiển |
| Email bị thụt đầu dòng | Lề nội dung lớn hơn lề chung, hoặc tab và space không đồng nhất | Căn chỉnh nội dung và dấu đóng; kiểm tra giá trị runtime |
| Placeholder `%s` không thay | Chưa gọi `formatted`/`String.format` | Gọi định dạng với đủ tham số; test thứ tự placeholder |
| Lỗi `MissingFormatArgumentException` | Số placeholder và đối số không khớp | Kiểm kê `%s`, positional argument và `%%` trong từng bản dịch |
| Nội dung có `\${name}` nguyên dạng | Text block Java không tự nội suy biến | Chọn rõ `Formatter`, `MessageFormat` hoặc template engine |
| Ngôn ngữ hiển thị sai | Ánh xạ `Locale` sang bản dịch/fallback không đúng | Kiểm tra ngôn ngữ yêu cầu, khóa và chính sách fallback |
| Ngày, tiền vẫn cùng định dạng ở mọi ngôn ngữ | Chỉ dịch câu chữ, chưa định dạng dữ liệu theo locale | Dùng `DateTimeFormatter`, `NumberFormat` với `Locale` phù hợp |
| Tiếng Việt bị lỗi ký tự | Mã nguồn/tệp output và encoder không thống nhất | Kiểm tra UTF-8 ở mã nguồn, bundle, output, HTTP/MIME |
| JSON hoặc HTML hỏng khi chèn giá trị | `formatted` không escape theo cú pháp đích | Dùng JSON serializer / HTML encoder theo ngữ cảnh |
| Email subject hoặc preview bị xuống dòng bất ngờ | Dữ liệu đầu vào chứa control characters | Xác thực trường một dòng trước khi gửi/hiển thị |
| Kiểm thử chỉ nhìn `println` tưởng có thêm LF | `println` tự thêm kết thúc dòng | Kiểm tra `String` bằng assertion, `length()`, `endsWith` |

**Gợi ý kiểm thử:** với mỗi locale và kênh, kiểm tra bản dịch tồn tại, số placeholder, ký tự đặc biệt trong tên/nghiệp vụ, đúng LF cuối, giới hạn độ dài, và phép mã hóa dữ liệu cho định dạng đích. Dùng so sánh `String.equals` cho mẫu cố định; với HTML/JSON nên kiểm tra bằng parser/serializer tương ứng.

## 11. Quy tắc áp dụng

Text block phát huy tác dụng khi **bố cục nhiều dòng là một phần của nội dung**. `String.formatted` là cách chèn tham số gọn trong Java 15+ nhưng không thay thế giải pháp i18n hoặc escaping. Với số ít thông điệp có nội dung ổn định, `Map<language, template>` có thể đủ; khi số lượng bản dịch tăng, chuyển sang `ResourceBundle`/hệ thống quản lý bản dịch và tách nội dung ra khỏi mã Java. Phần gửi email, push, SMS hoặc xuất JSON/HTML vẫn dùng API đúng kênh và charset.

**Tài liệu chính thức đang áp dụng:** [Oracle Java SE 26 — Text Blocks](https://docs.oracle.com/en/java/javase/26/language/text-blocks.html), [Java SE 26 `String.formatted`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html), [Java SE 26 `ResourceBundle`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.html) và [Oracle — UTF-8 properties files từ Java 9](https://docs.oracle.com/javase/9/intl/internationalization-enhancements-jdk-9.htm).
