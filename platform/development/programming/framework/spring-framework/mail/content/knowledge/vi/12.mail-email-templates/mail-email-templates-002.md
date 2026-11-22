# Template variable và giá trị mặc định

Trong một ứng dụng gửi email bằng **Spring Framework Mail**, nội dung thư thường thay đổi theo người nhận và sự kiện: tên người dùng, mã đơn hàng, ngày hết hạn, số tiền, liên kết xác nhận hoặc thông tin hỗ trợ. Nếu viết trực tiếp những giá trị đó vào chuỗi Java, mỗi lần đổi nội dung lại phải sửa mã, còn việc tạo nhiều biến thể email dễ dẫn đến logic rải rác và khó kiểm soát.

**Email template** giải quyết vấn đề bằng cách tách phần trình bày khỏi dữ liệu. Template chứa những vị trí cần thay thế; ứng dụng chuẩn bị một **model/context** gồm các biến rồi render thành nội dung cuối cùng trước khi gửi qua **JavaMailSender**. Một biến có thể bắt buộc phải có, có thể tùy chọn, hoặc cần một **giá trị mặc định (default value)** khi dữ liệu không được cung cấp.

Chủ đề này tập trung vào cách khai báo và truyền **template variable**, cách chọn nơi đặt giá trị mặc định, cách xử lý **missing/null/blank**, và các lưu ý khi dùng biến trong HTML email. Ví dụ sử dụng **Thymeleaf** để minh họa vì nó tích hợp tốt với hệ sinh thái Spring; nguyên tắc về dữ liệu và fallback vẫn áp dụng cho FreeMarker hoặc một template engine khác, nhưng cú pháp biến và biểu thức mặc định sẽ khác.

## 1. Template variable là gì?

Một template là nội dung có phần tĩnh và phần động. Ví dụ email chào mừng:

~~~html
<html>
  <body>
    <h1>Chào mừng, <span th:text="${recipientName}">bạn</span>!</h1>
    <p>Tài khoản của bạn đã được tạo thành công.</p>
    <p>Mã tài khoản: <strong th:text="${accountCode}">ACC-000</strong></p>
  </body>
</html>
~~~

Trong ví dụ:

- **recipientName** là biến tên người nhận.
- **accountCode** là biến mã tài khoản.
- Biểu thức **${recipientName}** và **${accountCode}** truy cập dữ liệu trong context của Thymeleaf.
- **th:text** yêu cầu Thymeleaf ghi giá trị biến thành nội dung văn bản của phần tử.
- Nội dung nằm giữa thẻ span hoặc strong là **giá trị dự phòng trong template file** khi xem file HTML trực tiếp hoặc khi thuộc tính Thymeleaf chưa được xử lý. Khi render thành công, th:text thay nội dung đó bằng giá trị đã đánh giá.

Template variable không phải là một biến Java nằm trực tiếp trong file HTML. Nó là **tên khóa trong context** mà template engine tra cứu khi render.

### Tách ba thành phần

~~~text
Business data
   |
   | recipientName = "Lan"
   | accountCode   = "ACC-1528"
   v
Template context / model
   |
   | recipientName -> "Lan"
   | accountCode   -> "ACC-1528"
   v
Email template
   |
   | ${recipientName}
   | ${accountCode}
   v
Rendered HTML/text
   |
   v
MimeMessage -> JavaMailSender -> SMTP
~~~

**Business data** là dữ liệu nghiệp vụ được lấy từ database hoặc service. **Context** là tập giá trị mà template được phép sử dụng. **Template** quyết định cách trình bày chúng. **Rendered content** là chuỗi hoàn chỉnh mà ứng dụng đưa vào MIME message.

Tách các phần này giúp:

- Thay đổi nội dung email mà không sửa logic gửi thư.
- Dùng cùng một bộ dữ liệu để tạo bản HTML và plain text.
- Kiểm tra biến bắt buộc trước khi gửi.
- Áp dụng giá trị mặc định một cách nhất quán.
- Kiểm thử template độc lập với SMTP.

## 2. Truyền biến vào template bằng Thymeleaf

Với Thymeleaf, ứng dụng thường tạo một **Context**, đặt biến bằng **setVariable(...)**, rồi gọi **TemplateEngine.process(...)**.

~~~java
import java.util.Locale;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class WelcomeTemplateRenderer {

    private final TemplateEngine templateEngine;

    public WelcomeTemplateRenderer(TemplateEngine templateEngine) {
        this.templateEngine = templateEngine;
    }

    public String renderHtml(String recipientName, String accountCode) {
        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("recipientName", recipientName);
        context.setVariable("accountCode", accountCode);

        return templateEngine.process("mail/welcome", context);
    }
}
~~~

Tên template **mail/welcome** được resolver ánh xạ tới file tương ứng, chẳng hạn **templates/mail/welcome.html**, tùy cấu hình của ứng dụng. Đường dẫn và phần mở rộng thực tế phụ thuộc **ITemplateResolver** đang dùng.

Template có thể đọc các biến:

~~~html
<p>Xin chào <span th:text="${recipientName}">bạn</span>.</p>
<p>Mã tài khoản: <span th:text="${accountCode}">ACC-000</span></p>
~~~

Nếu **recipientName** có giá trị **Lan** và **accountCode** có giá trị **ACC-1528**, kết quả render về cơ bản là:

~~~html
<p>Xin chào <span>Lan</span>.</p>
<p>Mã tài khoản: <span>ACC-1528</span></p>
~~~

Template engine thay giá trị động vào đúng vị trí, giữ lại cấu trúc HTML tĩnh.

### Tên biến phải khớp giữa Java và template

Nếu Java truyền:

~~~java
context.setVariable("recipientName", "Lan");
~~~

nhưng template lại viết:

~~~html
<span th:text="${receiverName}">bạn</span>
~~~

thì hai tên khóa không khớp. Template không tự suy ra **receiverName** từ **recipientName**. Tùy engine và biểu thức, biến không tồn tại có thể cho kết quả null/rỗng hoặc phát sinh lỗi khi biểu thức tiếp tục truy cập thuộc tính. Vì vậy, cần coi tên biến là một **hợp đồng giữa renderer và template**.

Một quy ước hữu ích:

| Tên biến | Ý nghĩa | Kiểu dữ liệu gợi ý |
| --- | --- | --- |
| **recipientName** | Tên hiển thị người nhận | String |
| **accountCode** | Mã tài khoản | String |
| **activationUrl** | Liên kết kích hoạt | URI hoặc String đã kiểm soát |
| **expiresAt** | Thời điểm hết hạn | Instant/ZonedDateTime đã định dạng |
| **totalAmount** | Số tiền | BigDecimal |
| **currencyCode** | Mã tiền tệ | String hoặc enum |
| **items** | Danh sách dòng hàng | List |
| **supportEmail** | Địa chỉ hỗ trợ | String |

Tên biến nên mô tả **ý nghĩa nghiệp vụ**, không mô tả vị trí hiển thị như **firstLineText** hoặc **greenButtonLabel**, trừ khi đó thật sự là dữ liệu giao diện riêng. Một tên ổn định giúp nhiều template dùng chung model mà không phụ thuộc vào cách trình bày cụ thể.

## 3. Giá trị mặc định là gì?

Giá trị mặc định là giá trị được dùng khi dữ liệu tùy chọn **không được cung cấp hoặc không có giá trị hữu ích** theo quy tắc đã chọn.

Ví dụ:

~~~text
recipientName = null
~~~

Thay vì render:

~~~text
Xin chào null!
~~~

ứng dụng có thể hiển thị:

~~~text
Xin chào bạn!
~~~

Hoặc khi thiếu địa chỉ hỗ trợ cụ thể, email có thể dùng một hộp thư hỗ trợ chung:

~~~text
Nếu cần trợ giúp, vui lòng liên hệ support@example.test.
~~~

Tuy nhiên, **không phải biến nào cũng nên có default**. Nếu thiếu **activationUrl** trong email kích hoạt tài khoản, thay một URL giả định hoặc chuỗi rỗng có thể tạo một email không thể sử dụng. Với biến bắt buộc, hành vi đúng thường là **từ chối render và báo lỗi dữ liệu**, thay vì che giấu lỗi bằng giá trị mặc định.

### Phân loại biến trước khi chọn default

| Loại biến | Ví dụ | Khi thiếu dữ liệu |
| --- | --- | --- |
| **Bắt buộc** | activationUrl, orderId, verificationCode | Báo lỗi và không gửi template không hoàn chỉnh |
| **Tùy chọn có default hợp lý** | recipientName, supportEmail | Dùng giá trị thay thế đã được nghiệp vụ chấp nhận |
| **Tùy chọn có thể ẩn cả phần** | promotionCode, secondaryAddress | Không render phần tử liên quan nếu không có giá trị |
| **Có thể rỗng theo nghiệp vụ** | middleName, companyName | Hiển thị rỗng hoặc bỏ qua mà không làm câu văn sai |
| **Có kiểu dữ liệu cần định dạng** | totalAmount, expiresAt | Không thay bằng chuỗi tùy tiện; áp dụng locale/format rõ ràng |

Một default tốt phải **đúng về ngữ nghĩa**, không chỉ giúp template không còn null. Ví dụ, nếu thiếu số tiền, hiển thị **0 VND** có thể khiến người nhận hiểu nhầm đơn hàng miễn phí. Nếu thiếu ngày hết hạn, hiển thị ngày hiện tại là một thông tin sai. Trong các trường hợp đó, nên ẩn phần không có dữ liệu hoặc từ chối gửi.

## 4. Phân biệt missing, null, empty và blank

Các trạng thái dưới đây khác nhau:

| Trạng thái | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Missing** | Không gọi setVariable cho recipientName | Khóa không tồn tại trong context |
| **Null** | setVariable("recipientName", null) | Khóa có mặt nhưng giá trị là null |
| **Empty** | Chuỗi rỗng "" | Chuỗi có độ dài bằng 0 |
| **Blank** | "   " hoặc chuỗi chỉ có tab/khoảng trắng | Có ký tự nhưng không có nội dung hữu ích |
| **Present** | "Lan" | Có giá trị hiển thị |

Không phải template engine nào cũng xử lý các trường hợp này giống nhau. Một biểu thức có thể trả null khi khóa missing, nhưng một phép truy cập thuộc tính sâu như **customer.name** có thể gặp lỗi nếu **customer** không tồn tại. Vì vậy, không nên dựa vào hành vi ngẫu nhiên của engine để xác định chính sách dữ liệu.

### Blank không tự động giống null

Đoạn kiểm tra:

~~~java
if (recipientName == null) {
    recipientName = "bạn";
}
~~~

chỉ xử lý null. Nếu **recipientName** là chuỗi chỉ có khoảng trắng, email vẫn có thể thành:

~~~text
Xin chào    !
~~~

Nếu nghiệp vụ coi chuỗi chỉ có khoảng trắng là thiếu dữ liệu, hãy chuẩn hóa bằng **isBlank()** và **strip()**:

~~~java
String displayName =
        recipientName == null || recipientName.isBlank()
                ? "bạn"
                : recipientName.strip();
~~~

Đây là một quyết định của **lớp chuẩn bị dữ liệu**, không phải hành vi tự động của mọi template engine.

## 5. Đặt default ở Java hay trong template?

Có hai nơi phổ biến để cung cấp giá trị mặc định:

1. **Trong Java trước khi render**: model đã có giá trị chuẩn hóa, template chỉ tập trung trình bày.
2. **Trong template**: biểu thức hiển thị chọn giá trị thay thế khi biến không có dữ liệu.

Hai cách phục vụ các mục đích khác nhau và có thể phối hợp, nhưng không nên đặt cùng một chính sách ở nhiều nơi mà không có lý do.

### Default ở Java: chính sách dữ liệu tập trung

~~~java
public record WelcomeMailModel(
        String recipientName,
        String accountCode,
        String supportEmail
) {
    public static WelcomeMailModel from(
            String recipientName,
            String accountCode,
            String supportEmail
    ) {
        String normalizedName =
                recipientName == null || recipientName.isBlank()
                        ? "bạn"
                        : recipientName.strip();

        if (accountCode == null || accountCode.isBlank()) {
            throw new IllegalArgumentException(
                    "accountCode là dữ liệu bắt buộc"
            );
        }

        String normalizedSupportEmail =
                supportEmail == null || supportEmail.isBlank()
                        ? "support@example.test"
                        : supportEmail.strip();

        return new WelcomeMailModel(
                normalizedName,
                accountCode.strip(),
                normalizedSupportEmail
        );
    }
}
~~~

Khi render:

~~~java
WelcomeMailModel model = WelcomeMailModel.from(
        rawName,
        accountCode,
        configuredSupportEmail
);

Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("recipientName", model.recipientName());
context.setVariable("accountCode", model.accountCode());
context.setVariable("supportEmail", model.supportEmail());
~~~

Ưu điểm của cách này:

- Quy tắc **null/blank/default** nằm ở một nơi có thể kiểm thử.
- Template không phải lặp lại điều kiện cho cùng một biến ở nhiều vị trí.
- Các phiên bản HTML và plain text nhận cùng dữ liệu đã chuẩn hóa.
- Biến bắt buộc được kiểm tra trước khi render, dễ trả lỗi nghiệp vụ rõ ràng.

Đây thường là lựa chọn tốt cho **giá trị có ý nghĩa nghiệp vụ**, ví dụ tên hiển thị chuẩn, địa chỉ hỗ trợ mặc định hoặc mã đơn bắt buộc.

### Default trong template: fallback cho mục đích hiển thị

Thymeleaf cho phép dùng biểu thức điều kiện ngay tại vị trí hiển thị:

~~~html
<p>
  Xin chào
  <span th:text="${recipientName != null ? recipientName : 'bạn'}">bạn</span>!
</p>
~~~

Biểu thức trên dùng **recipientName** khi giá trị khác null; nếu null thì dùng literal **bạn**. Đây là fallback ở tầng trình bày. Nó không tự xử lý chuỗi chỉ có khoảng trắng.

Nếu cần xử lý null hoặc chuỗi rỗng, Thymeleaf cung cấp utility **#strings**. Ví dụ:

~~~html
<span th:text="${#strings.isEmpty(recipientName) ? 'bạn' : recipientName}">
  bạn
</span>
~~~

Biểu thức **#strings.isEmpty(...)** xử lý giá trị rỗng theo tiện ích của Thymeleaf; nó không thay thế quy tắc chuẩn hóa chuỗi blank theo chính sách Java của ứng dụng. Nếu **"   "** cũng được xem là thiếu, hãy chuẩn hóa trước khi đưa vào context.

Fallback trong template phù hợp với **cách diễn đạt hiển thị đơn giản**, chẳng hạn câu chào có thể dùng “bạn” khi không có tên. Nó không nên là nơi duy nhất kiểm tra các giá trị bắt buộc như URL xác nhận hoặc số tiền.

### Nên chọn cách nào?

| Tình huống | Nơi nên xử lý |
| --- | --- |
| Biến bắt buộc phải tồn tại | Java/service/model validation |
| Chuẩn hóa null, blank, khoảng trắng, định dạng | Java trước khi render |
| Default nghiệp vụ dùng chung nhiều template | Java/model hoặc một policy service |
| Cách diễn đạt fallback riêng của một template | Template, nếu đơn giản và rõ ràng |
| Ẩn/hiện một đoạn HTML theo dữ liệu | Template với điều kiện |
| Giá trị phụ thuộc locale, timezone, tiền tệ | Java/service hoặc formatter đã cấu hình rõ |

Một nguyên tắc hữu ích là: **Java quyết định dữ liệu nào được phép đưa vào email; template quyết định cách trình bày dữ liệu đó**. Có thể để template có fallback nhỏ để tăng độ bền, nhưng không dùng fallback để che một lỗi dữ liệu quan trọng.

## 6. Giá trị mặc định trong Thymeleaf

Thymeleaf sử dụng **Standard Expression** để đọc biến và đánh giá biểu thức. Một số cách thường dùng:

### Dùng toán tử điều kiện

~~~html
<p th:text="${recipientName != null ? recipientName : 'bạn'}">
  Xin chào bạn
</p>
~~~

Đây là cách rõ ràng khi điều kiện chỉ kiểm tra null.

### Dùng utility kiểm tra chuỗi rỗng

~~~html
<p th:text="${#strings.isEmpty(recipientName) ? 'bạn' : recipientName}">
  Xin chào bạn
</p>
~~~

Thích hợp khi giá trị null hoặc empty đều được coi là thiếu. Nếu dữ liệu có thể chứa khoảng trắng, nên chuẩn hóa bằng Java hoặc dùng một hàm kiểm tra phù hợp với quy tắc của ứng dụng.

### Dùng biểu thức Elvis khi muốn fallback ngắn gọn

Thymeleaf hỗ trợ **Elvis operator** trong Standard Expressions:

~~~html
<span th:text="${recipientName} ?: 'bạn'">bạn</span>
~~~

Biểu thức này chọn giá trị bên trái nếu có giá trị, nếu không sẽ dùng biểu thức mặc định bên phải. Cú pháp Elvis có thể ngắn hơn điều kiện ba ngôi, nhưng với template có nhiều người cùng bảo trì, nên dùng cách viết dễ đọc và kiểm tra theo phiên bản Thymeleaf đang sử dụng.

### Fallback cho thuộc tính lồng nhau

Giả sử context có biến **customer** với thuộc tính **displayName**. Nếu customer luôn tồn tại nhưng displayName có thể null:

~~~html
<span th:text="${customer.displayName != null ? customer.displayName : 'bạn'}">
  bạn
</span>
~~~

Nếu chính **customer** có thể null, biểu thức truy cập **customer.displayName** có thể gặp vấn đề trước khi phần fallback được áp dụng, tùy cách biểu thức được đánh giá. An toàn hơn là chuẩn bị một model có cấu trúc rõ ràng trong Java, hoặc kiểm tra object cha trước:

~~~html
<span th:text="${customer != null and customer.displayName != null
                  ? customer.displayName
                  : 'bạn'}">
  bạn
</span>
~~~

Trong template dài, điều kiện lồng nhau làm giảm khả năng đọc. Nếu có nhiều thuộc tính phụ thuộc nhau, hãy chuẩn bị biến hiển thị như **recipientName** ở Java thay vì buộc mọi template hiểu toàn bộ cấu trúc object nghiệp vụ.

## 7. Default không đồng nghĩa với ẩn phần tử

Có hai nhu cầu khác nhau:

- **Thay giá trị thiếu bằng một nội dung mặc định**.
- **Không hiển thị phần nội dung đó khi không có dữ liệu**.

Ví dụ mã khuyến mãi chỉ xuất hiện khi có chương trình:

~~~html
<p th:if="${promotionCode != null and !#strings.isEmpty(promotionCode)}">
  Mã ưu đãi:
  <strong th:text="${promotionCode}">WELCOME</strong>
</p>
~~~

Nếu không có mã, cả đoạn paragraph không được render. Đây khác với:

~~~html
<p>
  Mã ưu đãi:
  <strong th:text="${promotionCode != null ? promotionCode : 'Không có'}">
    Không có
  </strong>
</p>
~~~

Ở ví dụ thứ hai, thông điệp vẫn xuất hiện và hiển thị **Không có**. Cả hai có thể đúng tùy trải nghiệm cần tạo.

### Dùng điều kiện với các biến boolean

~~~html
<p th:if="${showSupportInstructions}">
  Nếu cần trợ giúp, hãy liên hệ bộ phận hỗ trợ.
</p>
~~~

Không nên dùng một giá trị mặc định **true** cho cờ điều khiển phần nhạy cảm nếu việc hiển thị phụ thuộc quyền hoặc trạng thái nghiệp vụ. Hãy xác định boolean trong Java từ dữ liệu và chính sách đã được kiểm tra.

### Dùng default cho danh sách

Nếu danh sách hàng hóa rỗng, không nên tự tạo một dòng giả như **“Không có sản phẩm”** nếu email đang xác nhận đơn hàng mà thiếu dữ liệu có thể là lỗi. Có thể:

- Từ chối render nếu danh sách là dữ liệu bắt buộc.
- Hiển thị một câu **“Không có dòng chi tiết”** nếu nghiệp vụ thực sự cho phép danh sách rỗng.
- Ẩn cả bảng nếu bảng là phần tùy chọn.

Ví dụ điều kiện:

~~~html
<table th:if="${items != null and !items.isEmpty()}">
  <tr th:each="item : ${items}">
    <td th:text="${item.name}">Tên sản phẩm</td>
    <td th:text="${item.quantity}">1</td>
  </tr>
</table>
<p th:if="${items == null or items.isEmpty()}">
  Không có dòng chi tiết.
</p>
~~~

Đoạn trên minh họa hai nhánh hiển thị. Nếu danh sách bắt buộc phải có ít nhất một dòng, hãy validate trong Java và không render nhánh “Không có dòng chi tiết” để che lỗi.

## 8. Chuẩn bị model rõ ràng trước khi render

Một email template có thể dùng nhiều biến. Nếu gọi **setVariable(...)** từng biến rải rác ở nhiều service, tên khóa và default dễ bị lệch giữa các luồng. Nên tạo một model chuyên biệt cho loại email.

~~~java
import java.math.BigDecimal;
import java.time.ZonedDateTime;
import java.util.List;

public record OrderMailModel(
        String recipientName,
        String orderNumber,
        BigDecimal totalAmount,
        String currencyCode,
        ZonedDateTime createdAt,
        List<OrderMailItem> items,
        String supportEmail
) {
    public OrderMailModel {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException(
                    "orderNumber là dữ liệu bắt buộc"
            );
        }
        if (totalAmount == null || currencyCode == null
                || currencyCode.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu thông tin tổng tiền hoặc tiền tệ"
            );
        }

        recipientName =
                recipientName == null || recipientName.isBlank()
                        ? "bạn"
                        : recipientName.strip();

        supportEmail =
                supportEmail == null || supportEmail.isBlank()
                        ? "support@example.test"
                        : supportEmail.strip();

        items = items == null ? List.of() : List.copyOf(items);
    }
}

public record OrderMailItem(
        String name,
        int quantity,
        BigDecimal lineTotal
) {
}
~~~

Đây là ví dụ minh họa Java record; trong dự án dùng Java phiên bản cũ hơn có thể dùng class bất biến thông thường. Constructor compact của record kiểm tra dữ liệu bắt buộc, chuẩn hóa tên hiển thị và địa chỉ hỗ trợ, đồng thời thay danh sách null bằng danh sách rỗng.

Điều cần cân nhắc: nếu **items rỗng** là trạng thái không hợp lệ của đơn hàng, không nên âm thầm đổi null thành list rỗng. Model phải phản ánh quy tắc thật của nghiệp vụ. Việc chuẩn hóa chỉ phù hợp khi default có ý nghĩa hợp lệ.

Render model:

~~~java
Context context = new Context(locale);
context.setVariable("order", orderMailModel);
String html = templateEngine.process("mail/order-confirmation", context);
~~~

Template truy cập:

~~~html
<p>Xin chào <span th:text="${order.recipientName}">bạn</span>.</p>
<p>
  Đơn hàng:
  <strong th:text="${order.orderNumber}">ORD-000</strong>
</p>
<p>
  Hỗ trợ:
  <span th:text="${order.supportEmail}">support@example.test</span>
</p>
~~~

Thay vì tạo hàng loạt khóa top-level như **recipientName**, **orderNumber**, **totalAmount**, model **order** gom dữ liệu cùng một khái niệm nghiệp vụ. Với template lớn, cách này giảm nguy cơ trùng tên biến và làm rõ nguồn gốc dữ liệu.

## 9. Biến có kiểu dữ liệu cần được định dạng trước khi hiển thị

Không phải mọi biến đều là String. Một email có thể chứa:

- Số tiền dạng **BigDecimal**.
- Ngày giờ dạng **Instant**, **LocalDate** hoặc **ZonedDateTime**.
- Số lượng dạng integer.
- Trạng thái dạng enum.
- Danh sách các dòng sản phẩm.

Không nên biến mọi thứ thành chuỗi ngay khi lấy dữ liệu từ database. Giữ kiểu dữ liệu rõ ràng giúp kiểm tra và áp dụng định dạng theo locale đúng cách.

### Số tiền

Ví dụ số tiền:

~~~java
BigDecimal totalAmount = new BigDecimal("1250000.50");
String currencyCode = "VND";
~~~

Không nên dùng default **0** nếu thiếu totalAmount là dấu hiệu lỗi dữ liệu. Nếu giá trị bắt buộc chưa có, hãy từ chối render. Khi có dữ liệu, định dạng tiền tệ theo locale:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public String formatMoney(
        BigDecimal amount,
        String currencyCode,
        Locale locale
) {
    if (amount == null || currencyCode == null) {
        throw new IllegalArgumentException(
                "Thiếu amount hoặc currencyCode"
        );
    }

    NumberFormat format = NumberFormat.getCurrencyInstance(locale);
    format.setCurrency(Currency.getInstance(currencyCode));
    return format.format(amount);
}
~~~

Kết quả phụ thuộc locale và currency. **vi-VN** có thể định dạng VND khác **en-US**; không nên tự nối chuỗi số với hậu tố tiền tệ nếu muốn hỗ trợ nhiều ngôn ngữ. Ngoài ra, quy tắc số chữ số thập phân còn phụ thuộc loại tiền.

Một cách khác là truyền **BigDecimal** và mã tiền tệ vào context rồi dùng formatter/utility được cấu hình trong template. Tuy nhiên, việc định dạng ở Java giúp tái sử dụng kết quả cho cả HTML và plain text, đồng thời dễ kiểm thử hơn. Quan trọng là phải thống nhất locale và currency.

### Ngày và thời gian

Ngày giờ lưu dưới dạng **Instant** là một thời điểm toàn cục; khi hiển thị cho người nhận, cần xác định **timezone** và **locale**:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public String formatExpiry(
        Instant expiresAt,
        ZoneId recipientZone,
        Locale locale
) {
    if (expiresAt == null) {
        throw new IllegalArgumentException(
                "expiresAt là dữ liệu bắt buộc"
        );
    }

    DateTimeFormatter formatter = DateTimeFormatter
            .ofPattern("dd/MM/yyyy HH:mm z", locale)
            .withZone(recipientZone);

    return formatter.format(expiresAt);
}
~~~

Nếu ngày hết hạn là thông tin bảo mật hoặc ảnh hưởng quyền sử dụng, không được dùng một ngày mặc định chỉ để template render thành công. Phải truyền thời điểm đúng đã được nghiệp vụ xác định.

### Biến boolean và enum

Với cờ boolean, hãy xác định rõ ý nghĩa tên biến:

- **showSupportInstructions**: có hiển thị hướng dẫn hỗ trợ hay không.
- **isTrialAccount**: tài khoản có phải dùng thử không.
- **paymentReceived**: đã nhận thanh toán hay chưa.

Một biến boolean bị thiếu không nên tự động trở thành **true** nếu điều đó có thể làm lộ nội dung hoặc đưa ra khẳng định sai. Với enum trạng thái, nên ánh xạ sang nhãn hiển thị trong Java hoặc một bảng thông điệp rõ ràng, thay vì render tên enum kỹ thuật như **PAYMENT_PENDING_REVIEW** trực tiếp cho khách hàng.

## 10. Locale và biến mặc định theo ngôn ngữ

Email template có thể gửi cho người nhận ở nhiều ngôn ngữ. Khi đó, default cũng có thể phụ thuộc locale:

| Locale | Tên mặc định gợi ý |
| --- | --- |
| **vi-VN** | bạn |
| **en-US** | there |
| **fr-FR** | bonjour |

Đây chỉ là ví dụ diễn đạt; nội dung thật cần được biên tập phù hợp ngôn ngữ và văn hóa. Không nên đặt một chuỗi tiếng Việt cố định trong Java rồi gửi cùng template cho mọi locale.

Thymeleaf Context có thể nhận locale:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
Context context = new Context(locale);
context.setVariable("recipientName", displayName);
~~~

Template engine có thể sử dụng locale này cho các cơ chế message resolution và formatter được tích hợp. Với email nhiều ngôn ngữ, cần quản lý cả **template**, **message bundle**, **format ngày/tiền** và **default text** theo cùng locale.

### Dùng message bundle cho câu mặc định

Thay vì hard-code câu fallback trong template, có thể đưa nhãn fallback vào message bundle theo locale. Ví dụ bundle tiếng Việt:

~~~properties
mail.greeting.defaultName=bạn
mail.support.label=Bộ phận hỗ trợ
~~~

Và bundle tiếng Anh:

~~~properties
mail.greeting.defaultName=there
mail.support.label=Support team
~~~

Template có thể dùng message expression của Thymeleaf:

~~~html
<span th:text="${recipientName != null
                  ? recipientName
                  : #messages.msg('mail.greeting.defaultName')}">
  bạn
</span>
~~~

Cách tổ chức cụ thể phụ thuộc cấu hình **MessageSource** và template resolver của ứng dụng. Mục tiêu là đặt **câu chữ phụ thuộc ngôn ngữ** trong nguồn dịch thuật, không rải chuỗi ở nhiều Java service.

### Locale mặc định phải được chọn có chủ đích

Nếu người nhận không có locale, ứng dụng cần một chính sách xác định:

- Dùng locale người dùng đã chọn trong hồ sơ.
- Dùng locale gắn với giao dịch hoặc sản phẩm.
- Dùng locale mặc định đã công bố của hệ thống.

Không nên suy đoán locale chỉ từ địa chỉ email hoặc server timezone. Nếu chọn default **vi-VN**, hãy truyền locale đó vào Context và dùng cùng locale khi format ngày/tiền, tránh email có lời chào tiếng Việt nhưng ngày tháng theo định dạng của một locale khác.

## 11. HTML escaping: biến động không được trở thành markup

Khi đưa biến vào HTML email, phải phân biệt **nội dung văn bản** với **cấu trúc HTML**.

Giả sử người dùng có tên:

~~~text
Lan <Manager> & Co
~~~

Nếu đưa trực tiếp chuỗi này vào HTML như markup, các ký tự **<**, **>** và **&** có thể bị diễn giải như cú pháp. Template có thể hiển thị sai hoặc tạo ra nội dung ngoài dự kiến.

Trong Thymeleaf, **th:text** là cách phù hợp để hiển thị một giá trị như văn bản và thực hiện escaping HTML:

~~~html
<p>Xin chào <span th:text="${recipientName}">bạn</span>.</p>
~~~

Nếu giá trị là **Lan <Manager> & Co**, kết quả HTML được escape tương đương:

~~~html
<p>Xin chào <span>Lan &lt;Manager&gt; &amp; Co</span>.</p>
~~~

Trình duyệt/email client hiển thị lại các ký tự theo nội dung văn bản, thay vì coi chúng là thẻ HTML.

### Tránh dùng th:utext với dữ liệu không tin cậy

**th:utext** hiển thị nội dung HTML không escape theo cách của th:text. Nếu dữ liệu đến từ người dùng, database có thể chứa dữ liệu do người dùng nhập, hoặc một hệ thống bên ngoài, việc đưa thẳng vào **th:utext** có thể tạo markup không mong muốn và nguy cơ nội dung HTML độc hại.

Chỉ dùng HTML không escape khi giá trị đã được tạo bởi một nguồn template đáng tin cậy hoặc đã qua quy trình sanitize phù hợp với mục đích. Với tên người dùng, địa chỉ, ghi chú và nội dung nhập tự do, ưu tiên **th:text**.

### Default cũng phải được escape đúng ngữ cảnh

Một giá trị mặc định như **bạn** là literal an toàn trong ví dụ. Nhưng nếu default được lấy từ cấu hình hoặc database, vẫn cần xử lý nó theo ngữ cảnh sử dụng. Không phải mọi chuỗi đã escape cho HTML text đều an toàn khi đặt vào:

- Thuộc tính HTML như **href** hoặc **title**.
- URL.
- JavaScript hoặc CSS.
- Nội dung HTML không escape.

**HTML text escaping không thay thế URL validation**. Với liên kết trong email, hãy giới hạn scheme (thường là HTTPS), kiểm soát domain theo nghiệp vụ và encode giá trị thuộc tính đúng cách. Không đưa URL do người dùng tùy ý cung cấp vào href chỉ vì template đã dùng th:text ở chỗ hiển thị.

## 12. Biến URL và giá trị mặc định an toàn

Một email xác nhận thường có biến **activationUrl**. Đây là biến **bắt buộc** vì thiếu nó, người nhận không thể thực hiện hành động.

~~~java
if (activationUrl == null || activationUrl.isBlank()) {
    throw new IllegalArgumentException(
            "Không thể render email vì thiếu activationUrl"
    );
}
~~~

Không nên dùng default là một URL chung nếu đây không phải URL xác nhận thực sự. Người nhận có thể bấm vào trang không liên quan và tưởng đã hoàn thành thao tác.

Trong template:

~~~html
<a th:href="${activationUrl}" th:text="#{mail.activate.button}">
  Kích hoạt tài khoản
</a>
~~~

Ở đây **activationUrl** được đưa vào thuộc tính href, còn nhãn nút được lấy từ message bundle. Ứng dụng phải tạo URL từ nguồn tin cậy, bảo đảm scheme và host đúng, token có thời hạn và không bị ghi vào log. Template chỉ trình bày URL đã được chuẩn bị.

### Giá trị URL không nên được fallback bằng chuỗi rỗng

Nếu dùng:

~~~html
<a th:href="${activationUrl ?: '#'}">Kích hoạt</a>
~~~

thì email vẫn có nút nhưng nút không thực hiện hành động hợp lệ. Đây là một fallback **che lỗi**. Với biến bắt buộc, tốt hơn là dừng render, ghi nhận lỗi template data và không gửi một email không thể sử dụng.

## 13. Dùng cùng model cho HTML và plain text

Một email có thể cần hai bản nội dung: **text/plain** và **text/html**. Không nên tạo hai bộ biến độc lập, vì giá trị mặc định giữa hai bản có thể lệch nhau.

Luồng khuyến nghị:

~~~text
Business data
    |
    v
Validate required fields
    |
    v
Normalize optional fields and defaults
    |
    v
One mail model
    |
    +--> Render HTML template
    |
    '--> Render plain text template
              |
              v
       MimeMessageHelper.setText(plain, html)
              |
              v
       JavaMailSender.send(...)
~~~

Ví dụ:

~~~java
Context htmlContext = new Context(locale);
htmlContext.setVariable("order", orderMailModel);

Context textContext = new Context(locale);
textContext.setVariable("order", orderMailModel);

String html = htmlTemplateEngine.process(
        "mail/order-confirmation",
        htmlContext
);
String plain = textTemplateEngine.process(
        "mail/order-confirmation",
        textContext
);
~~~

Hai template có thể dùng cùng tên biến và cùng model. Cấu hình **template mode** khác nhau: HTML resolver tạo HTML, còn text resolver tạo plain text. Trong một ứng dụng, có thể dùng hai resolver/engine hoặc cấu hình template engine theo cách phù hợp với cấu trúc template.

Sau khi render:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("orders@example.test");
helper.setTo(recipient);
helper.setSubject(subject);
helper.setText(plain, html);

mailSender.send(message);
~~~

**setText(plain, html)** tạo nội dung thay thế trong MIME message. Hai bản phải dùng cùng giá trị **recipientName**, **orderNumber**, **totalAmount**, **activationUrl** và các dữ liệu liên quan. Nếu bản plain hiển thị “hết hạn sau 15 phút” nhưng HTML hiển thị “30 phút”, đó là lỗi tạo model/template chứ không phải lỗi SMTP.

### Fallback hiển thị phải nhất quán

Nếu thiếu **recipientName**, hãy chuẩn hóa thành **bạn** trong model trước khi tạo hai Context. Không nên để HTML dùng fallback **bạn** nhưng plain text lại render **null**. Tương tự, nếu không có promotion code, cả hai bản phải cùng ẩn phần ưu đãi hoặc cùng hiển thị thông điệp tương ứng theo nghiệp vụ.

## 14. Cú pháp biến và default phụ thuộc template engine

Tên biến và quy tắc mặc định không phải cú pháp chung của Java hoặc Spring Mail. Chúng thuộc **template engine** mà ứng dụng chọn.

| Engine | Cú pháp đọc biến | Fallback minh họa | Ghi chú |
| --- | --- | --- | --- |
| **Thymeleaf** | Biểu thức dollar trong Standard Expression | Điều kiện ba ngôi hoặc Elvis expression | Có Standard Dialect, utility và message expressions |
| **FreeMarker** | Biểu thức dollar trong FTL | Toán tử default dùng dấu chấm than | Quy tắc missing/null khác Thymeleaf |
| **Mustache** | Double curly braces | Section/inverted section hoặc default từ model | Cú pháp logic trong template được giữ tối giản |

Ví dụ FreeMarker:

~~~ftl
<p>Xin chào ${recipientName!"bạn"}!</p>
<p>Mã đơn: ${orderNumber!"Chưa có mã"}</p>
~~~

Trong FreeMarker, toán tử **!** cung cấp giá trị thay thế khi biểu thức bên trái thiếu/null theo quy tắc engine. Nó không tự động coi chuỗi chỉ có khoảng trắng là thiếu. Nếu cần xử lý blank, hãy chuẩn hóa dữ liệu trước khi render hoặc dùng biểu thức/utility phù hợp với phiên bản FreeMarker.

Ví dụ Mustache thường dựa vào model đã có default:

~~~mustache
<p>Xin chào {{recipientName}}!</p>
{{#showPromotion}}
  <p>Mã ưu đãi: {{promotionCode}}</p>
{{/showPromotion}}
~~~

Mustache không sử dụng cú pháp fallback như Thymeleaf hoặc FreeMarker trong biểu thức biến thông thường. Ứng dụng nên đưa **recipientName** đã chuẩn hóa và cờ **showPromotion** vào model.

**Không sao chép cú pháp default từ engine này sang engine khác.** Một file Thymeleaf có thể chứa **th:text**, trong khi FreeMarker dùng chỉ thị và cú pháp riêng. Template resolver và template mode cũng phải phù hợp với file đang render.

### Placeholder của Spring không giống biến trong email template

Trong Spring configuration:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST:smtp.example.test}
~~~

là cơ chế **property placeholder** của Spring để đọc cấu hình môi trường và giá trị mặc định. Nó không phải template variable của Thymeleaf.

Trong email template, biểu thức dollar được dùng để đọc context. Dù ký hiệu có vẻ giống nhau, **nguồn dữ liệu và thời điểm đánh giá khác nhau**:

- Spring property placeholder được giải quyết khi binding/cấu hình bean.
- Template variable được giải quyết khi render nội dung cho một email cụ thể.
- MIME headers/body chỉ được tạo sau khi template đã render ra chuỗi.

Không nên đưa cú pháp template vào YAML để mong Spring tự thay thế biến người nhận; cũng không nên kỳ vọng template engine đọc được mọi biến môi trường nếu ứng dụng chưa truyền chúng vào context.

## 15. Tránh truyền model quá rộng vào template

Một cách tiện lợi nhưng thiếu kiểm soát là đưa toàn bộ entity/database object vào context:

~~~java
context.setVariable("user", userEntity);
~~~

Điều đó có thể làm template truy cập được nhiều thuộc tính không liên quan tới email, ví dụ trạng thái nội bộ, thông tin riêng tư hoặc quan hệ lazy-loading. Nó cũng khiến nội dung email phụ thuộc trực tiếp cấu trúc entity.

Nên tạo **mail view model** chỉ chứa dữ liệu cần thiết:

~~~java
public record PasswordResetMailModel(
        String recipientName,
        String resetUrl,
        String expiresInText,
        String supportEmail
) {
}
~~~

Model này không cần chứa password, token nội bộ không được phép lộ, hoặc toàn bộ đối tượng tài khoản. **resetUrl** là URL đã được tạo theo chính sách bảo mật; template chỉ nhận URL cần hiển thị.

Lợi ích:

- Template chỉ nhìn thấy đúng những dữ liệu cần để trình bày.
- Dễ kiểm tra biến bắt buộc và default.
- Giảm phụ thuộc vào entity, ORM và lazy-loading.
- Tránh vô tình đưa trường riêng tư vào HTML email.
- Model có thể được kiểm thử mà không cần kết nối database.

### Không để template tự truy cập service hoặc database

Template nên render từ **dữ liệu đã chuẩn bị**, không nên thực hiện truy vấn database, gọi API bên ngoài hoặc tạo token khi đang xử lý biểu thức. Những công việc đó cần diễn ra trong service trước khi render.

Ví dụ, thay vì để template tự tìm địa chỉ hỗ trợ theo tenant, service nên resolve tenant, xác định supportEmail và truyền biến vào model. Điều này giúp lỗi dữ liệu xuất hiện ở một ranh giới rõ ràng, thay vì phát sinh giữa lúc render HTML.

## 16. Kiểm tra biến bắt buộc trước khi render

Một template có thể phụ thuộc nhiều biến. Nên xác định hợp đồng cho mỗi template:

| Template | Biến bắt buộc | Biến tùy chọn/default | Phần có thể ẩn |
| --- | --- | --- | --- |
| **mail/welcome** | accountCode | recipientName, supportEmail | promotion |
| **mail/password-reset** | resetUrl, expiresInText | recipientName | support instructions |
| **mail/order-confirmation** | orderNumber, totalAmount, currencyCode | recipientName, supportEmail | note, promotion |

Đây là ví dụ về **template contract**, không phải metadata tự động của Thymeleaf. Có thể biểu diễn hợp đồng bằng record/constructor validation, hoặc một lớp validator trước khi gọi TemplateEngine.

~~~java
public record PasswordResetMailModel(
        String recipientName,
        String resetUrl,
        String expiresInText,
        String supportEmail
) {
    public PasswordResetMailModel {
        if (resetUrl == null || resetUrl.isBlank()) {
            throw new IllegalArgumentException(
                    "resetUrl là dữ liệu bắt buộc"
            );
        }
        if (expiresInText == null || expiresInText.isBlank()) {
            throw new IllegalArgumentException(
                    "expiresInText là dữ liệu bắt buộc"
            );
        }

        recipientName =
                recipientName == null || recipientName.isBlank()
                        ? "bạn"
                        : recipientName.strip();

        supportEmail =
                supportEmail == null || supportEmail.isBlank()
                        ? "support@example.test"
                        : supportEmail.strip();
    }
}
~~~

Nếu model hợp lệ được tạo thành công, template có thể dựa vào các invariant đó. Cách này giúp template gọn hơn và không cần lặp lại điều kiện cho các biến bắt buộc.

### Missing variable và property path sai

Một template có thể tham chiếu:

~~~html
<span th:text="${order.customer.displayName}">bạn</span>
~~~

Nhưng model chỉ truyền:

~~~java
context.setVariable("order", orderSummary);
~~~

Nếu **orderSummary** không có **customer** hoặc **displayName**, biểu thức có thể không đánh giá như dự kiến. Việc thêm default ở cuối không phải lúc nào cũng khắc phục được một property path không hợp lệ.

Để giảm lỗi:

- Dùng mail model có cấu trúc ổn định, thay vì entity thay đổi liên tục.
- Đặt tên biến và thuộc tính theo một quy ước.
- Kiểm tra các thuộc tính cần thiết trong constructor hoặc validator.
- Render template trong test với dữ liệu mẫu đầy đủ.
- Tránh truy cập chuỗi thuộc tính sâu nếu template chỉ cần một giá trị đã được chuẩn hóa.

## 17. Gắn template renderer với JavaMailSender

Template engine chỉ tạo nội dung. **JavaMailSender** vẫn chịu trách nhiệm gửi MIME message. Một service thường có hai phần: render template và gửi thư.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.util.Locale;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class PasswordResetMailService {

    private final TemplateEngine templateEngine;
    private final JavaMailSender mailSender;

    public PasswordResetMailService(
            TemplateEngine templateEngine,
            JavaMailSender mailSender
    ) {
        this.templateEngine = templateEngine;
        this.mailSender = mailSender;
    }

    public void send(
            String recipient,
            PasswordResetMailModel model,
            Locale locale
    ) throws MessagingException {

        Context context = new Context(locale);
        context.setVariable("mail", model);

        String html = templateEngine.process(
                "mail/password-reset",
                context
        );

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("security@example.test");
        helper.setTo(recipient);
        helper.setReplyTo(model.supportEmail());
        helper.setSubject("Yêu cầu đặt lại mật khẩu");
        helper.setText(html, true);

        mailSender.send(message);
    }
}
~~~

Template tương ứng:

~~~html
<html>
  <body>
    <h1>Đặt lại mật khẩu</h1>
    <p>Xin chào <span th:text="${mail.recipientName}">bạn</span>.</p>
    <p>Liên kết có hiệu lực trong
      <strong th:text="${mail.expiresInText}">15 phút</strong>.
    </p>
    <p>
      <a th:href="${mail.resetUrl}">Đặt lại mật khẩu</a>
    </p>
    <p>
      Hỗ trợ:
      <span th:text="${mail.supportEmail}">support@example.test</span>
    </p>
  </body>
</html>
~~~

Trong ví dụ:

1. **PasswordResetMailModel** xác nhận các biến bắt buộc và chuẩn hóa giá trị tùy chọn.
2. **Context** đưa model vào dưới khóa **mail**.
3. **TemplateEngine.process(...)** tạo HTML hoàn chỉnh.
4. **MimeMessageHelper.setText(html, true)** đánh dấu phần body là HTML.
5. **JavaMailSender.send(...)** chuyển message tới transport.

Đây là ví dụ HTML-only để làm rõ quá trình render và gửi. Nếu email cần fallback plain text, hãy render thêm template text và dùng **setText(plain, html)** trong multipart mode phù hợp.

### Tại sao validate model trước khi gọi process?

Nếu template thiếu **resetUrl**, nội dung có thể render thành một liên kết trống hoặc sai. Việc kiểm tra trước giúp lỗi được báo tại tầng dữ liệu, nơi có đủ bối cảnh để tạo URL hoặc từ chối yêu cầu. Template engine không thể tự tạo một token xác nhận hợp lệ chỉ vì một biến đang null.

## 18. Kiểm thử template variable và default mà không gửi email

Template rendering có thể kiểm thử độc lập với SMTP. Điều này giúp phát hiện:

- Tên biến trong Java không khớp tên dùng trong template.
- Giá trị mặc định không xuất hiện khi null/blank.
- Một biến bắt buộc bị thiếu.
- HTML escaping không đúng.
- Phần tùy chọn không được ẩn như mong muốn.
- Locale không được truyền đúng.

Ví dụ test renderer:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

class WelcomeTemplateTest {

    private final TemplateEngine templateEngine = createTestEngine();

    @Test
    void rendersNameAndAccountCode() {
        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("recipientName", "Lan");
        context.setVariable("accountCode", "ACC-1528");

        String html = templateEngine.process(
                "mail/welcome",
                context
        );

        assertTrue(html.contains("Lan"));
        assertTrue(html.contains("ACC-1528"));
    }

    @Test
    void displaysFallbackNameWhenNameIsNull() {
        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("recipientName", null);
        context.setVariable("accountCode", "ACC-1528");

        String html = templateEngine.process(
                "mail/welcome",
                context
        );

        assertTrue(html.contains("bạn"));
    }
}
~~~

**createTestEngine()** là hàm thiết lập TemplateEngine và resolver cho test, phụ thuộc cách ứng dụng cấu hình Thymeleaf. Đoạn trên minh họa ý tưởng kiểm thử; một test hoàn chỉnh cần dùng đúng template resolver và đường dẫn resource của dự án.

### Kiểm tra escaping

~~~java
context.setVariable("recipientName", "Lan <Manager> & Co");
String html = templateEngine.process("mail/welcome", context);

assertTrue(html.contains("Lan &lt;Manager&gt; &amp; Co"));
~~~

Test này xác nhận biến được hiển thị như văn bản đã escape khi template dùng **th:text**. Nếu template chuyển sang **th:utext**, kỳ vọng cần thay đổi và phải có quy trình kiểm soát HTML đầu vào phù hợp.

### Kiểm tra biến bắt buộc

Nếu model từ chối **resetUrl** null, có thể test constructor/model validation:

~~~java
assertThrows(
        IllegalArgumentException.class,
        () -> new PasswordResetMailModel(
                "Lan",
                " ",
                "15 phút",
                "support@example.test"
        )
);
~~~

Đây là test cho **hợp đồng dữ liệu**, không phải test SMTP. Việc tách test model, template và mail transport giúp xác định lỗi xuất phát từ đâu.

## 19. Tập hợp nhiều biến trong context

Khi template chỉ có một vài biến, gọi **setVariable(...)** từng khóa khá dễ đọc. Với model lớn, có thể gom dữ liệu vào một object hoặc map.

Ví dụ dùng object:

~~~java
Context context = new Context(locale);
context.setVariable("order", orderMailModel);
context.setVariable("recipient", recipientView);
context.setVariable("supportEmail", supportEmail);
~~~

Ví dụ dùng map:

~~~java
Map<String, Object> variables = new HashMap<>();
variables.put("recipientName", displayName);
variables.put("accountCode", accountCode);
variables.put("supportEmail", supportEmail);

Context context = new Context(locale);
context.setVariables(variables);
~~~

Map phù hợp khi model được tạo động hoặc khi một renderer dùng chung cho nhiều template. Nhưng nếu có nhiều khóa, object model có kiểu rõ ràng thường dễ đọc và an toàn hơn.

### Lưu ý với Map.of(...)

Java **Map.of(...)** không chấp nhận key hoặc value null. Vì vậy:

~~~java
Map<String, Object> variables = Map.of(
        "recipientName", recipientName,
        "accountCode", accountCode
);
~~~

có thể ném **NullPointerException** nếu recipientName null. Nếu dữ liệu tùy chọn có thể null, hãy chuẩn hóa trước, dùng object model hoặc một map có thể chứa null trong quá trình chuẩn bị. Không để lỗi Map.of bị hiểu nhầm thành lỗi của template engine.

### Tránh trùng tên khóa

Nếu context đặt:

~~~java
context.setVariable("name", recipientName);
context.setVariable("name", companyName);
~~~

thì lần gán sau ghi đè giá trị trước. Template sẽ chỉ thấy một khóa **name**, khiến kết quả khó giải thích.

Nên đặt tên thể hiện đúng ý nghĩa:

- **recipientName** cho người nhận.
- **companyName** cho doanh nghiệp.
- **supportContactName** cho người liên hệ hỗ trợ.

Nếu dùng một model lồng nhau, chẳng hạn **mail.recipient.name** và **mail.company.name**, template có thể thể hiện quan hệ rõ ràng hơn.

## 20. Những lỗi thường gặp khi dùng template variable và default

### Lỗi 1: Không truyền biến nhưng vẫn kỳ vọng template tự biết dữ liệu

Template dùng **recipientName**, nhưng renderer không đặt khóa đó vào Context. Template engine không thể tự lấy tên từ người nhận SMTP hoặc tự suy ra từ địa chỉ email.

**Cách xử lý:** xác định model và context contract; truyền đúng biến hoặc thay template bằng dữ liệu thật có nguồn rõ ràng.

### Lỗi 2: Dùng default cho biến bắt buộc

Nếu **activationUrl** thiếu, fallback sang URL trang chủ có thể tạo email trông hợp lệ nhưng không thực hiện được hành động xác nhận.

**Cách xử lý:** validate biến bắt buộc trong Java; không render hoặc không gửi nếu thiếu dữ liệu.

### Lỗi 3: Chỉ kiểm tra null mà bỏ qua blank

Một chuỗi **"   "** không null và có thể tạo câu chào trống.

**Cách xử lý:** xác định blank có được coi là thiếu hay không; nếu có, dùng **isBlank()** và **strip()** ở lớp chuẩn hóa.

### Lỗi 4: Default ở HTML và plain text không giống nhau

HTML hiển thị **bạn**, nhưng plain text hiển thị **null** hoặc chuỗi trống.

**Cách xử lý:** chuẩn hóa một lần trong mail model rồi dùng chung cho cả hai renderer.

### Lỗi 5: Copy cú pháp từ template engine khác

Biểu thức default của FreeMarker không phải cú pháp Thymeleaf; cú pháp Mustache lại khác.

**Cách xử lý:** xác định template engine và phiên bản đang dùng, viết biểu thức theo dialect của engine đó.

### Lỗi 6: Dùng th:utext cho tên hoặc ghi chú người dùng

Dữ liệu có thể được diễn giải thành HTML thay vì hiển thị như văn bản.

**Cách xử lý:** ưu tiên **th:text** cho giá trị văn bản; chỉ dùng HTML không escape với nội dung đã được kiểm soát/sanitize phù hợp.

### Lỗi 7: Định dạng ngày hoặc tiền bằng default tùy tiện

Thiếu số tiền mà hiển thị **0 VND**, hoặc thiếu ngày hết hạn mà hiển thị ngày hiện tại, có thể làm người nhận hiểu sai.

**Cách xử lý:** phân loại dữ liệu bắt buộc và tùy chọn; định dạng theo locale/timezone, không thay giá trị nghiệp vụ bị thiếu bằng con số/ngày giả.

### Lỗi 8: Dùng toàn bộ entity làm model

Template có thể vô tình truy cập thuộc tính nhạy cảm hoặc quan hệ database không cần thiết.

**Cách xử lý:** tạo mail view model chứa đúng các trường cần hiển thị.

### Lỗi 9: Tạo fallback cho URL bằng dấu #

Nút vẫn xuất hiện nhưng không thực hiện hành động.

**Cách xử lý:** URL bắt buộc phải được tạo và xác thực ở Java; thiếu URL thì dừng render.

### Lỗi 10: Cho rằng render thành công nghĩa là email đã gửi

TemplateEngine chỉ tạo chuỗi HTML/text. Nó không kết nối SMTP và không xác nhận việc phát thư.

**Cách xử lý:** tách trạng thái render khỏi trạng thái gửi. Sau khi render, ứng dụng mới tạo MimeMessage và gọi JavaMailSender.

## 21. Quy trình xử lý template variable trong một mail job

Một quy trình có thể tổ chức như sau:

~~~text
Nhận sự kiện nghiệp vụ
       |
       v
Lấy dữ liệu từ service/repository
       |
       v
Tạo mail view model
       |
       +--> Validate biến bắt buộc
       |
       +--> Normalize null/blank
       |
       +--> Chọn locale/timezone/currency
       |
       +--> Tính default hợp lệ
       |
       v
Tạo template Context
       |
       v
Render HTML và/hoặc plain text
       |
       v
Tạo MimeMessage
       |
       v
JavaMailSender.send(...)
       |
       v
Ghi nhận trạng thái submit và xử lý lỗi
~~~

Tại mỗi bước có một trách nhiệm rõ:

| Bước | Trách nhiệm |
| --- | --- |
| Lấy dữ liệu | Đọc thông tin nghiệp vụ có nguồn xác định |
| Mail view model | Giới hạn dữ liệu được phép xuất hiện trong thư |
| Validation | Từ chối khi biến bắt buộc thiếu hoặc không hợp lệ |
| Normalization | Xử lý null/blank và giá trị tùy chọn theo chính sách |
| Formatting | Chuẩn hóa ngày, tiền tệ, số lượng theo locale |
| Context | Đưa model vào template engine bằng tên khóa thống nhất |
| Render | Tạo chuỗi HTML/plain text |
| MIME creation | Đóng gói nội dung và attachment nếu có |
| Sending | Nộp message qua JavaMailSender |

Không nên trộn toàn bộ các bước vào một đoạn nối chuỗi dài. Khi template không render đúng, có thể kiểm tra model trước; khi MIME sai, kiểm tra message sau render; khi SMTP lỗi, xem exception và transport.

## 22. Tự kiểm tra qua các tình huống

### Tình huống A — Tên người nhận null

Model nhận **recipientName = null**. Email cần câu chào tự nhiên.

**Hỏi:** nên xử lý ở đâu?

**Đáp:** nếu default **bạn** là chính sách chung, chuẩn hóa trong Java mail model để HTML và plain text cùng dùng. Template có thể thêm fallback nhỏ như lớp bảo vệ hiển thị.

### Tình huống B — Tên người nhận chỉ có khoảng trắng

**Hỏi:** kiểm tra **recipientName != null** có đủ không?

**Đáp:** không. Chuỗi blank vẫn khác null. Nếu blank được coi là thiếu, dùng **isBlank()** và chuẩn hóa bằng **strip()**.

### Tình huống C — Thiếu activationUrl

**Hỏi:** có nên dùng trang chủ làm URL mặc định để email vẫn gửi?

**Đáp:** không, trừ khi trang chủ thật sự là hành động dự kiến của nghiệp vụ. Email xác nhận cần URL hợp lệ; thiếu URL thì phải dừng render và báo lỗi dữ liệu.

### Tình huống D — Không có promotionCode

**Hỏi:** nên hiển thị “Không có mã” hay ẩn cả đoạn?

**Đáp:** tùy nội dung sản phẩm. Nếu mã ưu đãi là thông tin tùy chọn, có thể ẩn cả đoạn. Nếu người nhận cần biết không có ưu đãi, hiển thị câu rõ ràng. Hai cách đều phải thống nhất giữa HTML và plain text.

### Tình huống E — HTML và plain text dùng hai Context riêng

**Hỏi:** có thể chuẩn hóa tên ở HTML context và không chuẩn hóa ở text context không?

**Đáp:** không nên. Hai Context nên nhận cùng một mail model đã được chuẩn hóa; khác nhau chỉ ở cách render.

### Tình huống F — Tên chứa dấu ngoặc nhọn

**Hỏi:** có nên xóa ký tự **<** và **>** khỏi tên người dùng trước khi render?

**Đáp:** không cần xóa tùy tiện. Khi hiển thị như văn bản, dùng cơ chế HTML escaping như **th:text** để giữ nguyên ý nghĩa mà không diễn giải chuỗi thành markup. Nếu có quy tắc dữ liệu tên riêng, áp dụng ở tầng validation riêng.

### Tình huống G — Default tên khác nhau theo ngôn ngữ

**Hỏi:** nên hard-code “bạn” trong mọi template?

**Đáp:** không nếu hệ thống gửi đa ngôn ngữ. Chọn locale trước khi render và lấy default từ message bundle hoặc model theo locale.

### Tình huống H — Biến ngày hết hạn bị thiếu

**Hỏi:** có thể dùng ngày hiện tại để tránh lỗi template?

**Đáp:** không nếu ngày hết hạn ảnh hưởng quyền sử dụng. Đây là dữ liệu bắt buộc; cần lấy đúng thời điểm từ nghiệp vụ hoặc dừng gửi.

### Tình huống I — Template dùng cú pháp FreeMarker trong Thymeleaf

**Hỏi:** tại sao default không hoạt động?

**Đáp:** cú pháp thuộc engine khác. Xác định đúng template engine, resolver và dialect; dùng biểu thức fallback phù hợp với engine thực sự render file.

## 23. Nguyên tắc ghi nhớ

~~~text
Template variable
    -> khóa dữ liệu trong Context/model

Default value
    -> chỉ dùng khi thiếu dữ liệu tùy chọn

Missing / null / empty / blank
    -> các trạng thái khác nhau, cần chính sách rõ

Biến bắt buộc
    -> validate trong Java; không thay bằng giá trị giả

Biến tùy chọn
    -> normalize/default hoặc ẩn phần hiển thị

HTML text
    -> dùng th:text để escape nội dung văn bản

HTML URL
    -> kiểm soát scheme/domain và tạo URL ở Java

HTML + plain text
    -> dùng cùng một mail model đã chuẩn hóa

Template engine
    -> cú pháp biến/default phụ thuộc Thymeleaf, FreeMarker, Mustache...

JavaMailSender
    -> chỉ gửi MIME message sau khi nội dung đã render
~~~

**Template variable** là cầu nối giữa dữ liệu nghiệp vụ và nội dung email; **giá trị mặc định** giúp xử lý những trường tùy chọn một cách tự nhiên khi dữ liệu không có. Để tránh gửi thư sai, hãy phân biệt missing/null/empty/blank, validate các biến bắt buộc, chuẩn hóa default trong model, dùng cú pháp đúng template engine và escape dữ liệu theo ngữ cảnh HTML. Khi có cả plain text và HTML, dùng cùng một model để hai phiên bản luôn nhất quán trước khi đưa nội dung vào **MimeMessage** và gửi bằng **JavaMailSender**.

## 9. Biến có kiểu dữ liệu cần được định dạng trước khi hiển thị

Không phải mọi biến đều là String. Một email có thể chứa:

- Số tiền dạng **BigDecimal**.
- Ngày giờ dạng **Instant**, **LocalDate** hoặc **ZonedDateTime**.
- Số lượng dạng integer.
- Trạng thái dạng enum.
- Danh sách các dòng sản phẩm.

Không nên biến mọi thứ thành chuỗi ngay khi lấy dữ liệu từ database. Giữ kiểu dữ liệu rõ ràng giúp kiểm tra và áp dụng định dạng theo locale đúng cách.

### Số tiền

Ví dụ số tiền:

~~~java
BigDecimal totalAmount = new BigDecimal("1250000.50");
String currencyCode = "VND";
~~~

Không nên dùng default **0** nếu thiếu totalAmount là dấu hiệu lỗi dữ liệu. Nếu giá trị bắt buộc chưa có, hãy từ chối render. Khi có dữ liệu, định dạng tiền tệ theo locale:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public String formatMoney(
        BigDecimal amount,
        String currencyCode,
        Locale locale
) {
    if (amount == null || currencyCode == null) {
        throw new IllegalArgumentException(
                "Thiếu amount hoặc currencyCode"
        );
    }

    NumberFormat format = NumberFormat.getCurrencyInstance(locale);
    format.setCurrency(Currency.getInstance(currencyCode));
    return format.format(amount);
}
~~~

Kết quả phụ thuộc locale và currency. **vi-VN** có thể định dạng VND khác **en-US**; không nên tự nối chuỗi số với hậu tố tiền tệ nếu muốn hỗ trợ nhiều ngôn ngữ. Ngoài ra, quy tắc số chữ số thập phân còn phụ thuộc loại tiền.

Một cách khác là truyền **BigDecimal** và mã tiền tệ vào context rồi dùng formatter/utility được cấu hình trong template. Tuy nhiên, việc định dạng ở Java giúp tái sử dụng kết quả cho cả HTML và plain text, đồng thời dễ kiểm thử hơn. Quan trọng là phải thống nhất locale và currency.

### Ngày và thời gian

Ngày giờ lưu dưới dạng **Instant** là một thời điểm toàn cục; khi hiển thị cho người nhận, cần xác định **timezone** và **locale**:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public String formatExpiry(
        Instant expiresAt,
        ZoneId recipientZone,
        Locale locale
) {
    if (expiresAt == null) {
        throw new IllegalArgumentException(
                "expiresAt là dữ liệu bắt buộc"
        );
    }

    DateTimeFormatter formatter = DateTimeFormatter
            .ofPattern("dd/MM/yyyy HH:mm z", locale)
            .withZone(recipientZone);

    return formatter.format(expiresAt);
}
~~~

Nếu ngày hết hạn là thông tin bảo mật hoặc ảnh hưởng quyền sử dụng, không được dùng một ngày mặc định chỉ để template render thành công. Phải truyền thời điểm đúng đã được nghiệp vụ xác định.

### Biến boolean và enum

Với cờ boolean, hãy xác định rõ ý nghĩa tên biến:

- **showSupportInstructions**: có hiển thị hướng dẫn hỗ trợ hay không.
- **isTrialAccount**: tài khoản có phải dùng thử không.
- **paymentReceived**: đã nhận thanh toán hay chưa.

Một biến boolean bị thiếu không nên tự động trở thành **true** nếu điều đó có thể làm lộ nội dung hoặc đưa ra khẳng định sai. Với enum trạng thái, nên ánh xạ sang nhãn hiển thị trong Java hoặc một bảng thông điệp rõ ràng, thay vì render tên enum kỹ thuật như **PAYMENT_PENDING_REVIEW** trực tiếp cho khách hàng.

## 10. Locale và biến mặc định theo ngôn ngữ

Email template có thể gửi cho người nhận ở nhiều ngôn ngữ. Khi đó, default cũng có thể phụ thuộc locale:

| Locale | Tên mặc định gợi ý |
| --- | --- |
| **vi-VN** | bạn |
| **en-US** | there |
| **fr-FR** | bonjour |

Đây chỉ là ví dụ diễn đạt; nội dung thật cần được biên tập phù hợp ngôn ngữ và văn hóa. Không nên đặt một chuỗi tiếng Việt cố định trong Java rồi gửi cùng template cho mọi locale.

Thymeleaf Context có thể nhận locale:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");
Context context = new Context(locale);
context.setVariable("recipientName", displayName);
~~~

Template engine có thể sử dụng locale này cho các cơ chế message resolution và formatter được tích hợp. Với email nhiều ngôn ngữ, cần quản lý cả **template**, **message bundle**, **format ngày/tiền** và **default text** theo cùng locale.

### Dùng message bundle cho câu mặc định

Thay vì hard-code câu chào trong template:

~~~html
<span th:text="${recipientName != null ? recipientName : 'bạn'}">
  bạn
</span>
~~~

có thể đưa nhãn fallback vào message bundle theo locale. Ví dụ một bundle tiếng Việt:

~~~properties
mail.greeting.defaultName=bạn
mail.support.label=Bộ phận hỗ trợ
~~~

Và bundle tiếng Anh:

~~~properties
mail.greeting.defaultName=there
mail.support.label=Support team
~~~

Template có thể dùng message expression của Thymeleaf để lấy nhãn:

~~~html
<span th:text="${recipientName != null
                  ? recipientName
                  : #messages.msg('mail.greeting.defaultName')}">
  bạn
</span>
~~~

Cách tổ chức cụ thể phụ thuộc cấu hình **MessageSource** và template resolver của ứng dụng. Mục tiêu là đặt **câu chữ phụ thuộc ngôn ngữ** trong nguồn dịch thuật, không rải chuỗi ở nhiều Java service.

### Locale mặc định phải được chọn có chủ đích

Nếu người nhận không có locale, ứng dụng cần một chính sách xác định:

- Dùng locale người dùng đã chọn trong hồ sơ.
- Dùng locale gắn với giao dịch hoặc sản phẩm.
- Dùng locale mặc định đã công bố của hệ thống.

Không nên suy đoán locale chỉ từ địa chỉ email hoặc server timezone. Nếu chọn default **vi-VN**, hãy truyền locale đó vào Context và dùng cùng locale khi format ngày/tiền, tránh email có lời chào tiếng Việt nhưng ngày tháng theo định dạng của một locale khác.

## 11. HTML escaping: biến động không được trở thành markup

Khi đưa biến vào HTML email, phải phân biệt **nội dung văn bản** với **cấu trúc HTML**.

Giả sử người dùng có tên:

~~~text
Lan <Manager> & Co
~~~

Nếu đưa trực tiếp chuỗi này vào HTML như markup, các ký tự **<**, **>** và **&** có thể bị diễn giải như cú pháp. Template có thể hiển thị sai hoặc tạo ra nội dung ngoài dự kiến.

Trong Thymeleaf, **th:text** là cách phù hợp để hiển thị một giá trị như văn bản và thực hiện escaping HTML:

~~~html
<p>Xin chào <span th:text="${recipientName}">bạn</span>.</p>
~~~

Nếu giá trị là **Lan <Manager> & Co**, kết quả HTML được escape tương đương:

~~~html
<p>Xin chào <span>Lan &lt;Manager&gt; &amp; Co</span>.</p>
~~~

Trình duyệt/email client hiển thị lại các ký tự theo nội dung văn bản, thay vì coi chúng là thẻ HTML.

### Tránh dùng th:utext với dữ liệu không tin cậy

**th:utext** hiển thị nội dung HTML không escape theo cách của th:text. Nếu dữ liệu đến từ người dùng, database có thể chứa dữ liệu do người dùng nhập, hoặc một hệ thống bên ngoài, việc đưa thẳng vào **th:utext** có thể tạo markup không mong muốn và nguy cơ nội dung HTML độc hại.

Chỉ dùng HTML không escape khi giá trị đã được tạo bởi một nguồn template đáng tin cậy hoặc đã qua quy trình sanitize phù hợp với mục đích. Với tên người dùng, địa chỉ, ghi chú và nội dung nhập tự do, ưu tiên **th:text**.

### Default cũng phải được escape đúng ngữ cảnh

Một giá trị mặc định như **bạn** là literal an toàn trong ví dụ. Nhưng nếu default được lấy từ cấu hình hoặc database, vẫn cần xử lý nó theo ngữ cảnh sử dụng. Không phải mọi chuỗi đã escape cho HTML text đều an toàn khi đặt vào:

- Thuộc tính HTML như **href** hoặc **title**.
- URL.
- JavaScript hoặc CSS.
- Nội dung HTML không escape.

**HTML text escaping không thay thế URL validation**. Với liên kết trong email, hãy giới hạn scheme (thường là HTTPS), kiểm soát domain theo nghiệp vụ và encode giá trị thuộc tính đúng cách. Không đưa URL do người dùng tùy ý cung cấp vào href chỉ vì template đã dùng th:text ở chỗ hiển thị.

## 12. Biến URL và giá trị mặc định an toàn

Một email xác nhận thường có biến **activationUrl**. Đây là biến **bắt buộc** vì thiếu nó, người nhận không thể thực hiện hành động.

~~~java
if (activationUrl == null || activationUrl.isBlank()) {
    throw new IllegalArgumentException(
            "Không thể render email vì thiếu activationUrl"
    );
}
~~~

Không nên dùng default:

~~~text
activationUrl = https://example.test/
~~~

nếu đây không phải URL xác nhận thực sự. Người nhận có thể bấm vào trang không liên quan và tưởng đã hoàn thành thao tác.

Trong template:

~~~html
<a th:href="${activationUrl}" th:text="#{mail.activate.button}">
  Kích hoạt tài khoản
</a>
~~~

Ở đây **activationUrl** được đưa vào thuộc tính href, còn nhãn nút được lấy từ message bundle. Ứng dụng phải tạo URL từ nguồn tin cậy, bảo đảm scheme và host đúng, token có thời hạn và không bị ghi vào log. Template chỉ trình bày URL đã được chuẩn bị.

### Giá trị URL không nên được “fallback” bằng chuỗi rỗng

Nếu dùng:

~~~html
<a th:href="${activationUrl ?: '#'}">Kích hoạt</a>
~~~

thì email vẫn có nút nhưng nút không thực hiện hành động hợp lệ. Đây là một fallback **che lỗi**. Với biến bắt buộc, tốt hơn là dừng render, ghi nhận lỗi template data và không gửi một email không thể sử dụng.

## 13. Dùng cùng model cho HTML và plain text

Một email có thể cần hai bản nội dung: **text/plain** và **text/html**. Không nên tạo hai bộ biến độc lập, vì giá trị mặc định giữa hai bản có thể lệch nhau.

Luồng khuyến nghị:

~~~text
Business data
    |
    v
Validate required fields
    |
    v
Normalize optional fields and defaults
    |
    v
One mail model
    |
    +--> Render HTML template
    |
    '--> Render plain text template
              |
              v
       MimeMessageHelper.setText(plain, html)
              |
              v
       JavaMailSender.send(...)
~~~

Ví dụ:

~~~java
Context htmlContext = new Context(locale);
htmlContext.setVariable("order", orderMailModel);

Context textContext = new Context(locale);
textContext.setVariable("order", orderMailModel);

String html = htmlTemplateEngine.process(
        "mail/order-confirmation",
        htmlContext
);
String plain = textTemplateEngine.process(
        "mail/order-confirmation",
        textContext
);
~~~

Hai template có thể dùng cùng tên biến và cùng model. Cấu hình **template mode** khác nhau: HTML resolver tạo HTML, còn text resolver tạo plain text. Trong một ứng dụng, có thể dùng hai resolver/engine hoặc cấu hình template engine theo cách phù hợp với cấu trúc template.

Sau khi render:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("orders@example.test");
helper.setTo(recipient);
helper.setSubject(subject);
helper.setText(plain, html);

mailSender.send(message);
~~~

**setText(plain, html)** tạo nội dung thay thế trong MIME message. Hai bản phải dùng cùng giá trị **recipientName**, **orderNumber**, **totalAmount**, **activationUrl** và các dữ liệu liên quan. Nếu bản plain hiển thị “hết hạn sau 15 phút” nhưng HTML hiển thị “30 phút”, đó là lỗi tạo model/template chứ không phải lỗi SMTP.

### Fallback hiển thị phải nhất quán

Nếu thiếu **recipientName**, hãy chuẩn hóa thành **bạn** trong model trước khi tạo hai Context. Không nên để HTML dùng fallback **bạn** nhưng plain text lại render **null**. Tương tự, nếu không có promotion code, cả hai bản phải cùng ẩn phần ưu đãi hoặc cùng hiển thị thông điệp tương ứng theo nghiệp vụ.
