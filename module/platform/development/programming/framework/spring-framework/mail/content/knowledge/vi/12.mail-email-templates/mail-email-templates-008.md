# Kiểm soát expression và dữ liệu đầu vào

Một ứng dụng Spring gửi email xác nhận đơn hàng thường dùng template HTML để trình bày tên khách hàng, mã đơn, trạng thái và liên kết xem chi tiết. Template có thể chứa các **expression** để lấy giá trị từ dữ liệu ứng dụng, ví dụ Thymeleaf dùng `${customerName}` để đọc biến `customerName`. Những expression này giúp template tái sử dụng, nhưng cũng tạo ra một ranh giới cần kiểm soát: **template quyết định cách diễn giải dữ liệu, còn dữ liệu đầu vào không được tự biến thành mã expression hoặc cấu trúc template**.

Nếu ứng dụng ghép dữ liệu người dùng trực tiếp vào nguồn template, cho phép người dùng chọn template tùy ý hoặc đưa nội dung chưa kiểm soát vào những expression được đánh giá, có thể dẫn đến lỗi hiển thị, lộ dữ liệu hoặc thực thi biểu thức ngoài ý muốn. Ngay cả khi template là cố định, dữ liệu động vẫn cần được xác thực theo nghiệp vụ và xuất ra đúng ngữ cảnh HTML.

Trong **Spring Framework Mail**, `MimeMessageHelper.setText(html, true)` đặt nội dung dưới dạng HTML cho email. Nó **không kiểm soát expression của template engine, không xác thực dữ liệu đầu vào và không tự làm sạch HTML**. Bài này tập trung vào cách quản lý expression và dữ liệu khi render template email, với ví dụ sử dụng **Thymeleaf, Spring Boot và JavaMailSender**.

## 1. Expression trong template email là gì?

Template email là một mẫu nội dung có phần cố định và phần thay đổi theo từng lần gửi. Ví dụ:

~~~html
<h2>Đơn hàng đã được xác nhận</h2>
<p>Xin chào, <span th:text="${customerName}">Tên khách hàng</span>!</p>
<p>Mã đơn: <span th:text="${orderCode}">A102</span></p>
~~~

Các thuộc tính `th:text` và expression `${customerName}`, `${orderCode}` là cú pháp của Thymeleaf. Khi render, template engine đọc biến trong context, thay nội dung tương ứng và tạo ra HTML cuối cùng.

**Expression không phải dữ liệu đầu vào.** Expression là một phần của ngôn ngữ template, được tác giả template định nghĩa để truy xuất hoặc xử lý dữ liệu. Tên khách hàng và mã đơn là giá trị dữ liệu mà expression đọc.

~~~mermaid
flowchart LR
    A["Template cố định"] --> C["Template engine"]
    B["Dữ liệu đầu vào đã kiểm soát"] --> C
    C --> D["HTML đã render"]
    D --> E["MimeMessageHelper"]
    E --> F["JavaMailSender"]
~~~

Một thiết kế an toàn giữ hai luồng tách biệt:

- **Template source**: được ứng dụng quản lý, review và triển khai cùng phiên bản phần mềm.
- **Template context**: chứa dữ liệu của từng email, được kiểm tra trước khi render.

Khi render, engine kết hợp hai phần. Dữ liệu người dùng đi vào context dưới dạng giá trị, không được dùng để tạo expression hoặc thay đổi nội dung template source.

## 2. Các loại expression thường gặp trong Thymeleaf

Thymeleaf Standard Dialect và Spring integration cung cấp một số nhóm expression. Hiểu đúng chúng giúp xác định dữ liệu được lấy ở đâu và template đang thực hiện thao tác gì.

| Cú pháp | Tên | Mục đích thường gặp |
| --- | --- | --- |
| `${...}` | Variable expression | Đọc biến từ context, ví dụ tên khách hàng hoặc mã đơn. |
| `*{...}` | Selection expression | Đọc thuộc tính từ đối tượng đang được chọn qua `th:object`. |
| `#{...}` | Message expression | Lấy thông điệp từ message source, thường dùng cho nội dung đa ngôn ngữ. |
| `@{...}` | Link URL expression | Xây URL theo cơ chế URL của Thymeleaf. |
| `~{...}` | Fragment expression | Tham chiếu một fragment template để tái sử dụng nội dung. |
| `__...__` | Expression preprocessing | Tiền xử lý một expression trước khi phân tích expression bên ngoài. |

Ví dụ:

~~~html
<p th:text="${customerName}">Tên khách hàng</p>

<div th:object="${order}">
  <p th:text="*{code}">A102</p>
  <p th:text="*{statusLabel}">Đã xác nhận</p>
</div>

<p th:text="#{mail.order.confirmed}">Đơn hàng đã được xác nhận</p>

<a th:href="@{/orders/{id}(id=${orderId})}">Xem đơn hàng</a>
~~~

Các expression trên là **mã do tác giả template định nghĩa**. Dữ liệu được truyền vào như `customerName`, `order` và `orderId`. Người dùng không cần biết cú pháp expression và không nên được phép thay đổi nó thông qua các trường form.

### 2.1. Variable expression

`${...}` đọc biến hoặc thuộc tính trong context:

~~~html
<p th:text="${customerName}">Tên khách hàng</p>
~~~

Nếu context có biến `customerName` bằng `Nguyễn An`, phần tử sẽ hiển thị giá trị đó. Với Spring integration, biểu thức có thể được đánh giá thông qua cơ chế expression của Spring. Vì vậy, không nên biến dữ liệu người dùng thành một expression tùy ý rồi yêu cầu engine đánh giá.

### 2.2. Selection expression

`*{...}` thường được sử dụng khi phần tử hoặc vùng template đã chọn một object:

~~~html
<section th:object="${order}">
  <p>Mã: <span th:text="*{code}">A102</span></p>
  <p>Trạng thái: <span th:text="*{statusLabel}">Đã xác nhận</span></p>
</section>
~~~

`th:object` xác định object được chọn; `*{code}` truy cập thuộc tính của object đó. Đây là cách viết giúp template dễ đọc khi có nhiều thuộc tính cùng thuộc một đối tượng.

### 2.3. Message expression

`#{...}` lấy nội dung đã được quản lý trong message bundle:

~~~html
<h2 th:text="#{mail.order.title}">Thông báo đơn hàng</h2>
~~~

Ứng dụng có thể có các file message theo locale để hiển thị tiếng Việt, tiếng Anh hoặc ngôn ngữ khác. Người dùng không nên được tự chọn key message tùy ý; template nên tham chiếu các key đã được định nghĩa.

### 2.4. URL expression

`@{...}` hỗ trợ xây URL theo cơ chế của Thymeleaf:

~~~html
<a th:href="@{/orders/{id}(id=${orderId})}">
  Xem đơn hàng
</a>
~~~

Trong email, liên kết thường cần là URL tuyệt đối vì người đọc mở thư bên ngoài website. Ứng dụng phải bảo đảm context hoặc dữ liệu URL được cấu hình đúng, dùng domain đáng tin cậy và không để đầu vào tùy ý quyết định scheme/host.

### 2.5. Fragment expression

Template có thể tái sử dụng phần header/footer:

~~~html
<div th:replace="~{mail/fragments :: footer}"></div>
~~~

Tên template và fragment nên là lựa chọn do ứng dụng kiểm soát. Không nối một tên fragment từ request người dùng rồi đưa vào expression để engine tìm và render nội dung tùy ý.

### 2.6. Expression preprocessing

Cú pháp preprocessing có thể khiến expression bên trong được xử lý trước khi expression bên ngoài được phân tích. Đây là tính năng hữu ích cho một số template nâng cao, nhưng **không nên xây nội dung preprocessing từ dữ liệu người dùng**. Nó làm tăng độ phức tạp của quá trình đánh giá và có thể mở đường cho việc dữ liệu trở thành cú pháp.

Trong các email thông thường, hãy dùng các biến context tường minh và expression cố định; chỉ dùng preprocessing khi có yêu cầu template cụ thể, được hiểu và kiểm soát đầy đủ.

## 3. Ranh giới tin cậy: template source và template data

Một template email thường chứa các phần:

- Markup HTML do nhóm phát triển quản lý.
- Expression Thymeleaf do tác giả template viết.
- Nội dung tĩnh như tiêu đề, hướng dẫn và chân trang.
- Placeholder lấy dữ liệu động từ context.

Ví dụ template tin cậy:

~~~html
<h2>Đơn hàng đã được xác nhận</h2>
<p>Xin chào, <span th:text="${customerName}">Khách hàng</span>!</p>
<p>Mã đơn: <span th:text="${orderCode}">A102</span></p>
~~~

Dữ liệu không đáng tin cậy:

~~~text
customerName = "An <Bảo>"
orderCode = "A102"
~~~

Khi render, `th:text` xử lý tên như text và escape HTML phù hợp. Người nhận thấy `An <Bảo>` dưới dạng văn bản; chuỗi `<Bảo>` không trở thành một thẻ mới.

**Không làm như sau:**

~~~java
String template = "<p>Xin chào, " + userInput + "!</p>";
// Sau đó đưa nội dung động này qua một engine để xử lý như template.
~~~

Cách này trộn dữ liệu vào template source. Nếu người dùng nhập markup hoặc cú pháp template, engine hoặc trình đọc HTML có thể diễn giải nội dung ngoài ý định.

Một cách làm đúng hơn là giữ template cố định và truyền dữ liệu bằng context:

~~~java
Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("customerName", userInput);

String html = templateEngine.process(
        "mail/welcome",
        context
);
~~~

Template `mail/welcome` được ứng dụng quản lý; `userInput` chỉ là giá trị của biến. Việc dùng context không tự xác thực dữ liệu nghiệp vụ, nhưng giữ ranh giới giữa source và data rõ ràng.

## 4. Expression injection và template injection

Hai khái niệm này có liên quan nhưng không hoàn toàn giống nhau.

**Expression injection** xảy ra khi đầu vào không đáng tin cậy có thể ảnh hưởng tới expression được đánh giá. Ví dụ ứng dụng ghép chuỗi người dùng vào một biểu thức Spring Expression Language rồi parse/evaluate biểu thức đó. Người dùng có thể khiến hệ thống đánh giá nội dung ngoài ý định.

**Template injection** xảy ra khi người dùng có thể kiểm soát một phần hoặc toàn bộ template source, và ứng dụng sau đó đưa source đó vào template engine để render. Nếu template engine hỗ trợ expression, nội dung do người dùng cung cấp có thể được xử lý như cú pháp thay vì văn bản.

Ví dụ minh họa lỗi thiết kế ở tầng expression:

~~~java
// Không làm: userInput bị dùng để tạo expression source.
String expressionText = "${" + userInput + "}";

// Việc parse/evaluate expression tùy ý từ input là rủi ro.
~~~

Ví dụ minh họa lỗi thiết kế ở tầng template:

~~~text
Người dùng nhập template hoặc markup
        ↓
Ứng dụng lưu nội dung như template source
        ↓
Template engine đánh giá expression bên trong
        ↓
Nội dung được render trong quyền hạn của engine
~~~

Không phải mọi chuỗi có ký tự `${...}` đều tự động được thực thi. Rủi ro xuất hiện khi chuỗi đó đi vào **nguồn template hoặc expression parser** theo cách khiến engine đánh giá nó. Nếu chuỗi chỉ được truyền như một biến và xuất qua `th:text`, nó được xử lý như dữ liệu văn bản.

### Vì sao đây là rủi ro đáng quan tâm?

Tùy template engine, dialect, phiên bản và cấu hình evaluation context, expression có thể truy cập các biến, thuộc tính, phương thức hoặc bean được cung cấp trong phạm vi đánh giá. Nếu template source không đáng tin cậy, khả năng của engine có thể vượt xa việc thay một placeholder đơn giản.

Không nên giả định template engine là một sandbox để chạy template do người dùng gửi lên. Hãy coi **template source và expression là mã ứng dụng**, áp dụng kiểm soát truy cập, review và quy trình phát hành như đối với mã.

## 5. Đưa dữ liệu vào context thay vì tạo expression động

Cách thiết kế nên dùng là: template định nghĩa expression cố định; Java chuẩn bị object có dữ liệu cần thiết và thêm vào context.

~~~java
Context context = new Context(Locale.forLanguageTag("vi-VN"));

context.setVariable("customerName", customerName);
context.setVariable("orderCode", orderCode);
context.setVariable("statusLabel", statusLabel);
~~~

Template:

~~~html
<p>Xin chào, <span th:text="${customerName}">Khách hàng</span>!</p>
<p>Mã đơn: <span th:text="${orderCode}">A102</span></p>
<p>Trạng thái: <span th:text="${statusLabel}">Đã xác nhận</span></p>
~~~

Không cần tạo expression theo tên field mà người dùng gửi lên. Ví dụ, tránh nhận request có `fieldName` rồi tạo chuỗi expression dựa vào giá trị đó để đọc thuộc tính tùy ý của object.

### Dùng DTO nhỏ thay vì đưa cả domain object vào template

Không nên truyền nguyên một đối tượng domain lớn, chứa nhiều quan hệ và phương thức, nếu template chỉ cần vài giá trị. Một lựa chọn dễ kiểm soát hơn:

~~~java
public record OrderMailView(
        String orderCode,
        String customerName,
        String statusLabel,
        String detailsUrl) {
}
~~~

Tạo view model chỉ gồm các trường template được phép hiển thị:

~~~java
OrderMailView view = new OrderMailView(
        order.getCode(),
        customer.getDisplayName(),
        statusLabel,
        detailsUrl
);

context.setVariable("mail", view);
~~~

Template:

~~~html
<p th:text="${mail.customerName}">Khách hàng</p>
<p th:text="${mail.orderCode}">A102</p>
<p th:text="${mail.statusLabel}">Đã xác nhận</p>
<a th:href="${mail.detailsUrl}">Xem đơn hàng</a>
~~~

DTO giúp giới hạn dữ liệu được đưa vào template và làm rõ hợp đồng giữa service render với template. Tuy nhiên, việc dùng DTO không thay thế kiểm tra dữ liệu, phân quyền hoặc URL.

## 6. Kiểm soát đầu vào theo quy tắc nghiệp vụ

Không phải mọi dữ liệu đều cần cùng một loại validation. Một mã đơn hàng, địa chỉ email, tên khách hàng và ghi chú tự do có các quy tắc khác nhau.

| Trường | Ví dụ kiểm tra đầu vào |
| --- | --- |
| Địa chỉ người nhận | Không rỗng, cú pháp email hợp lệ, người nhận được phép nhận loại thông báo này. |
| Mã đơn hàng | Theo định dạng do hệ thống định nghĩa, giới hạn chiều dài. |
| Tên khách hàng | Bắt buộc hoặc tùy chọn theo nghiệp vụ, giới hạn chiều dài; vẫn cho phép Unicode và ký tự tên hợp lệ. |
| Trạng thái đơn hàng | Chỉ nhận một giá trị trong enum/allowlist. |
| Ghi chú | Giới hạn độ dài, cho phép newline nếu cần; xử lý như văn bản khi render. |
| Locale | Chọn trong danh sách locale được hỗ trợ. |
| Template name | Chọn từ danh sách template cố định do ứng dụng quản lý. |
| URL | Xây từ host tin cậy hoặc kiểm tra scheme/host/path theo chính sách. |

**Validation và escaping là hai bước khác nhau:**

- Validation xác định dữ liệu có đáp ứng hợp đồng nghiệp vụ hay không.
- Escaping/encoding biểu diễn dữ liệu đúng với ngữ cảnh đầu ra.
- Authorization xác định người dùng có quyền gửi thông báo hoặc xem dữ liệu liên quan hay không.

Một tên khách hàng có dấu `<` có thể hợp lệ như tên văn bản; không nhất thiết phải từ chối nó. Thay vào đó, HTML output phải escape ký tự đó khi đặt vào text node.

### 6.1. Kiểm tra dữ liệu bằng Bean Validation

Ví dụ DTO nhận yêu cầu gửi:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record OrderMailRequest(
        @NotBlank
        @Email
        String recipient,

        @NotBlank
        @Size(max = 120)
        String customerName,

        @NotBlank
        @Pattern(regexp = "[A-Z0-9-]{1,32}")
        String orderCode,

        @Size(max = 500)
        String customerNote
) {
}
~~~

Có thể kích hoạt validation ở tầng controller/service bằng `@Valid` hoặc gọi validator theo kiến trúc ứng dụng. Ví dụ controller:

~~~java
@PostMapping("/mail/order-confirmation")
public ResponseEntity<Void> send(
        @Valid @RequestBody OrderMailRequest request) {

    orderMailService.sendConfirmation(request);
    return ResponseEntity.accepted().build();
}
~~~

Đây là ví dụ minh họa khi ứng dụng có Spring Web và Bean Validation. `@Email` kiểm tra định dạng ở mức validator, không chứng minh hộp thư tồn tại. `@Size` giới hạn chiều dài, không thay thế output escaping. `@Pattern` chỉ phù hợp với mã đơn hàng có quy tắc thực sự như ví dụ; không dùng regex quá chặt cho tên người thật.

### 6.2. Không kiểm tra bằng cách xóa ký tự đặc biệt

Tránh xử lý tên khách hàng bằng cách xóa mọi dấu `<`, `>` hoặc `&`. Cách này làm thay đổi dữ liệu hợp lệ. Hãy giữ chuỗi theo quy tắc nghiệp vụ và escape ở vị trí HTML. Nếu nghiệp vụ cấm một số ký tự điều khiển hoặc giới hạn Unicode, hãy nêu rõ quy tắc đó và kiểm tra tại đầu vào.

### 6.3. Chuẩn hóa dữ liệu có chủ đích

Có thể cần trim khoảng trắng đầu/cuối hoặc chuẩn hóa mã đơn hàng về dạng chữ hoa. Nhưng không nên tự động biến đổi mọi chuỗi người dùng mà không hiểu ý nghĩa, vì có thể làm thay đổi tên, ngôn ngữ hoặc nội dung ghi chú.

Quy trình hợp lý:

1. Xác định quy tắc của trường.
2. Chuẩn hóa những gì quy tắc cho phép.
3. Validate giá trị sau chuẩn hóa.
4. Giữ giá trị logic để sử dụng trong nghiệp vụ.
5. Encode/escape khi xuất vào template.

## 7. Chọn template bằng allowlist, không nhận tên tùy ý

Một ứng dụng có thể có các template:

~~~text
mail/order-confirmed.html
mail/payment-received.html
mail/password-reset.html
~~~

Không nên lấy trực tiếp `templateName` từ request rồi truyền vào template engine. Nếu template resolver có thể tìm các template theo tên động, người gọi có thể chọn nội dung ngoài dự kiến hoặc khai thác cách resolver được cấu hình.

Thay vào đó, dùng enum hoặc allowlist:

~~~java
public enum MailTemplate {
    ORDER_CONFIRMED("mail/order-confirmed"),
    PAYMENT_RECEIVED("mail/payment-received"),
    PASSWORD_RESET("mail/password-reset");

    private final String templateName;

    MailTemplate(String templateName) {
        this.templateName = templateName;
    }

    public String templateName() {
        return templateName;
    }
}
~~~

Sau đó service chọn template qua một quyết định nghiệp vụ đã kiểm tra:

~~~java
String templateName = switch (mailType) {
    case ORDER_CONFIRMED -> MailTemplate.ORDER_CONFIRMED.templateName();
    case PAYMENT_RECEIVED -> MailTemplate.PAYMENT_RECEIVED.templateName();
    case PASSWORD_RESET -> MailTemplate.PASSWORD_RESET.templateName();
};

String html = templateEngine.process(templateName, context);
~~~

`mailType` nên là enum hoặc một giá trị được ánh xạ qua allowlist, không phải đường dẫn tự do do người dùng cung cấp.

**Không cho phép request chọn file template tùy ý**, ví dụ gửi đường dẫn hoặc tên resource bất kỳ rồi kỳ vọng resolver tự bảo vệ. Hãy cố định tên template trong code hoặc cấu hình quản trị đáng tin cậy.

## 8. Không dùng dữ liệu người dùng để quyết định expression hoặc fragment

Template có thể có nhiều biến thể:

~~~html
<div th:replace="~{mail/fragments :: footer}"></div>
~~~

Đây là lựa chọn fragment cố định. Nếu ứng dụng ghép tên fragment từ input, dữ liệu có thể tác động tới cấu trúc template hoặc nội dung được nạp.

Nếu sản phẩm cần người dùng chọn loại footer, theme hoặc ngôn ngữ, hãy dùng **mã lựa chọn allowlist**:

~~~java
String footerFragment = switch (theme) {
    case STANDARD -> "mail/fragments :: standardFooter";
    case COMPACT -> "mail/fragments :: compactFooter";
};
~~~

Các lựa chọn là hằng số do ứng dụng định nghĩa. Người dùng chỉ chọn một giá trị nghiệp vụ được phép, không cung cấp cú pháp fragment hoặc expression.

Tương tự, không tạo tên biến, thuộc tính hay method call trong expression dựa trên chuỗi input. Đặt các biến cần thiết vào context với tên cố định.

## 9. th:text và th:utext: kiểm soát dữ liệu đầu ra

Một template email an toàn thường dùng `th:text` cho dữ liệu text:

~~~html
<p th:text="${customerName}">Tên khách hàng</p>
<p th:text="${customerNote}">Ghi chú</p>
~~~

`th:text` đặt giá trị như nội dung văn bản và thực hiện escaping HTML. Dữ liệu `An <Bảo> & Co.` sẽ được biểu diễn an toàn để người đọc vẫn thấy đúng tên.

Ngược lại:

~~~html
<p th:utext="${customerNote}">Ghi chú</p>
~~~

`th:utext` xuất nội dung không escape. Nếu ghi chú là chuỗi tự do, không dùng cách này. Dữ liệu có thể chứa markup hoặc cấu trúc mà template không dự định cho phép.

### Khi nào cần rich text?

Nếu nghiệp vụ cho phép người dùng viết nội dung có định dạng như chữ đậm, danh sách và liên kết, HTML escaping toàn bộ sẽ làm các thẻ hiện thành văn bản. Khi đó cần **HTML sanitizer có allowlist** trước khi đưa nội dung đã được kiểm soát vào vùng unescaped.

Allowlist cần xác định rõ:

- Thẻ nào được phép, ví dụ `p`, `strong`, `em`, `ul`, `li`.
- Thuộc tính nào được phép.
- Có cho phép `href` không và scheme nào được chấp nhận.
- Có cho phép ảnh, CSS hoặc tài nguyên từ xa không.
- Cách xử lý thẻ lồng nhau và markup không hợp lệ.

Không tự viết sanitizer bằng một vài regex. HTML là ngôn ngữ có quy tắc phân tích phức tạp; dùng thư viện được duy trì, cấu hình chính sách rõ ràng và kiểm tra đầu ra trước khi xuất.

## 10. URL expression và dữ liệu đầu vào

Email thường có liên kết “Xem đơn hàng”, “Đặt lại mật khẩu” hoặc “Theo dõi yêu cầu”. Template có thể sử dụng URL expression:

~~~html
<a th:href="@{/orders/{id}(id=${orderId})}">
  Xem đơn hàng
</a>
~~~

Trong email, URL nên là **địa chỉ tuyệt đối** mà người nhận có thể mở từ bên ngoài ứng dụng. Có thể đưa một URL đã được tạo từ cấu hình tin cậy vào context:

~~~html
<a th:href="${detailsUrl}">Xem chi tiết</a>
~~~

Nhưng việc template escape giá trị thuộc tính không tự xác nhận URL là an toàn. Ứng dụng cần:

1. Dùng base URL HTTPS được cấu hình bởi hệ thống.
2. Tạo path/query từ dữ liệu đã validate và encode đúng thành phần.
3. Không cho input tự quyết định host hoặc scheme.
4. Không đưa token bí mật vào URL nếu chính sách sản phẩm không cho phép.
5. Nếu URL đến từ nguồn ngoài, kiểm tra allowlist domain/scheme và quy tắc redirect.

Ví dụ, mã đơn hàng có thể bị giới hạn thành `[A-Z0-9-]{1,32}` rồi đưa vào path segment đã encode. Host vẫn lấy từ cấu hình ứng dụng, không lấy từ header Host hoặc chuỗi do người dùng nhập nếu chưa có cơ chế xác minh.

### Expression không thay thế URL validation

`@{...}` giúp tạo URL theo quy tắc Thymeleaf, nhưng không biết một URL có đúng quyền truy cập nghiệp vụ hay không. Template có thể render link hợp lệ về mặt cú pháp nhưng trỏ tới đơn hàng không thuộc người nhận. **Authorization và kiểm tra quan hệ người dùng–tài nguyên phải thực hiện trước khi render.**

## 11. Giới hạn dữ liệu được đưa vào template context

Một context gọn và có kiểu rõ ràng giúp giảm nhầm lẫn. Ví dụ:

~~~java
Context context = new Context(Locale.forLanguageTag("vi-VN"));

context.setVariable("mail", new OrderMailView(
        orderCode,
        customerName,
        statusLabel,
        detailsUrl
));
~~~

Tránh đưa vào context:

- Toàn bộ Spring ApplicationContext hoặc bean registry.
- Service có thể thực hiện thao tác ghi/xóa hoặc truy cập hệ thống.
- Entity lớn chứa quan hệ lười tải và dữ liệu không liên quan.
- Request/session object có nhiều thuộc tính nhạy cảm.
- Đối tượng chứa credential, token hoặc bí mật không cần cho template.

Template chỉ nên nhận **dữ liệu hiển thị tối thiểu**. Việc truyền ít dữ liệu không tự tạo sandbox hoàn chỉnh cho expression, nhưng giảm khả năng template truy cập nhầm dữ liệu và giúp hợp đồng dễ review.

### Dùng kiểu dữ liệu cụ thể

Thay vì một map tùy ý chứa hàng chục key, có thể tạo DTO:

~~~java
public record OrderMailView(
        String customerName,
        String orderCode,
        String statusLabel,
        boolean paid,
        String detailsUrl) {
}
~~~

DTO giúp compiler hỗ trợ kiểm tra cấu trúc, làm rõ những trường template cần và hạn chế việc truyền nhầm object. Dù vậy, giá trị bên trong vẫn cần được validate và xuất đúng ngữ cảnh.

## 12. Giới hạn vòng lặp và dữ liệu collection

Template email có thể lặp qua danh sách sản phẩm:

~~~html
<tr th:each="item : ${mail.items}">
  <td th:text="${item.name}">Sản phẩm</td>
  <td th:text="${item.quantity}">1</td>
</tr>
~~~

Expression `th:each` được viết cố định trong template; collection `mail.items` là dữ liệu được đưa vào context. Không nên để người dùng gửi một expression tùy ý để quyết định collection hoặc cách truy cập thuộc tính.

Trước khi render, cần kiểm soát:

- Số phần tử tối đa để tránh email quá dài hoặc tiêu tốn tài nguyên.
- Kiểu dữ liệu và trường cần thiết của từng phần tử.
- Các giá trị số như quantity, price và tổng tiền theo quy tắc nghiệp vụ.
- Quyền xem các item có thuộc đúng đơn hàng/người nhận hay không.
- Cách hiển thị khi collection rỗng.

Ví dụ giới hạn:

~~~java
if (items == null || items.size() > 100) {
    throw new IllegalArgumentException(
            "Danh sách sản phẩm không hợp lệ"
    );
}
~~~

Con số 100 chỉ là giá trị minh họa; giới hạn thật phải dựa vào thiết kế email, hiệu năng render và giới hạn dung lượng của nhà cung cấp.

Không nên để template tự thực hiện các phép tính nghiệp vụ quan trọng như tính tổng tiền cuối cùng. Hãy tính và xác thực ở tầng domain/service, sau đó truyền giá trị đã xác định vào view model.

## 13. Expression trong message bundle và nội dung đa ngôn ngữ

Email thường cần locale theo người nhận. Thymeleaf có thể dùng message expression:

~~~html
<h2 th:text="#{mail.order.title}">Thông báo đơn hàng</h2>
<p th:text="#{mail.order.greeting(${mail.customerName})}">
  Xin chào
</p>
~~~

Các key message nên được quản lý trong resource bundle:

~~~properties
mail.order.title=Đơn hàng đã được xác nhận
mail.order.greeting=Xin chào, {0}!
~~~

Ví dụ tiếng Anh trong resource riêng:

~~~properties
mail.order.title=Your order is confirmed
mail.order.greeting=Hello, {0}!
~~~

Ứng dụng chọn locale đã được xác thực:

~~~java
Locale locale = switch (requestedLanguage) {
    case "vi" -> Locale.forLanguageTag("vi-VN");
    case "en" -> Locale.US;
    default -> Locale.forLanguageTag("vi-VN");
};

Context context = new Context(locale);
~~~

Không lấy trực tiếp một chuỗi locale bất kỳ rồi giả định hệ thống có message bundle tương ứng. Chọn locale trong danh sách hỗ trợ, đồng thời giữ dữ liệu truyền vào message parameter ở dạng giá trị. Message bundle là nội dung do ứng dụng quản lý; không để người dùng tự cung cấp key expression tùy ý.

## 14. Ví dụ hoàn chỉnh: validate input, render template và gửi mail

Ví dụ dưới đây minh họa ranh giới giữa request, dữ liệu hiển thị, template và Spring Mail.

### 14.1. DTO đầu vào

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record OrderConfirmationRequest(
        @NotBlank
        @Email
        String recipient,

        @NotBlank
        @Size(max = 120)
        String customerName,

        @NotBlank
        @Pattern(regexp = "[A-Z0-9-]{1,32}")
        String orderCode,

        @Size(max = 500)
        String note
) {
}
~~~

Định dạng `orderCode` là ví dụ; hệ thống cần thay bằng quy tắc mã đơn thực tế. Tên và ghi chú không bị cấm ký tự `<` hoặc `&` chỉ vì chúng xuất hiện trong HTML; template sẽ xử lý chúng như text.

### 14.2. View model cho template

~~~java
public record OrderMailView(
        String customerName,
        String orderCode,
        String statusLabel,
        String note,
        String detailsUrl) {
}
~~~

View model chỉ chứa dữ liệu cần hiển thị. Không truyền credential SMTP, entity đầy đủ hoặc service vào context.

### 14.3. Template Thymeleaf cố định

Tệp `src/main/resources/templates/mail/order-confirmed.html`:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Đơn hàng đã được xác nhận</title>
</head>
<body>
  <h2>Đơn hàng đã được xác nhận</h2>

  <p>
    Xin chào,
    <strong th:text="${mail.customerName}">Khách hàng</strong>!
  </p>

  <p>
    Mã đơn:
    <span th:text="${mail.orderCode}">A102</span>
  </p>

  <p>
    Trạng thái:
    <span th:text="${mail.statusLabel}">Đã xác nhận</span>
  </p>

  <p th:if="${mail.note != null and !#strings.isEmpty(mail.note)}">
    Ghi chú:
    <span th:text="${mail.note}">Ghi chú</span>
  </p>

  <p>
    <a th:href="${mail.detailsUrl}">Xem chi tiết đơn hàng</a>
  </p>
</body>
</html>
~~~

Các expression là hằng số do nhà phát triển viết. `th:text` escape nội dung hiển thị; `th:if` quyết định có render phần ghi chú hay không dựa trên biến trong context. `th:href` đặt URL vào thuộc tính; ứng dụng vẫn phải tạo và xác thực URL trước.

### 14.4. Service render và gửi

~~~java
import java.net.URI;
import java.util.Locale;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class OrderConfirmationMailService {

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;
    private final String fromAddress;
    private final URI publicBaseUri;

    public OrderConfirmationMailService(
            JavaMailSender mailSender,
            TemplateEngine templateEngine,
            @Value("${app.mail.from}") String fromAddress,
            @Value("${app.public-base-url}") URI publicBaseUri) {

        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
        this.fromAddress = fromAddress;
        this.publicBaseUri = publicBaseUri;
    }

    public void send(OrderConfirmationRequest request)
            throws MessagingException {

        // Dữ liệu đã được validate ở ranh giới ứng dụng.
        String name = request.customerName().trim();
        String code = request.orderCode();

        // Trạng thái được lấy từ kết quả nghiệp vụ, không từ input tùy ý.
        String statusLabel = "Đã xác nhận";

        // Base URI lấy từ cấu hình tin cậy; code đã có allowlist.
        String detailsUrl = buildDetailsUrl(publicBaseUri, code);

        OrderMailView view = new OrderMailView(
                name,
                code,
                statusLabel,
                request.note(),
                detailsUrl
        );

        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("mail", view);

        // Tên template là hằng số do ứng dụng quản lý.
        String html = templateEngine.process(
                "mail/order-confirmed",
                context
        );

        String plainText = """
                Xin chào, %s!

                Đơn hàng %s đã được xác nhận.
                Trạng thái: %s

                Xem chi tiết: %s
                """.formatted(name, code, statusLabel, detailsUrl);

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(fromAddress);
        helper.setTo(request.recipient());
        helper.setSubject("Đơn hàng " + code + " đã được xác nhận");
        helper.setText(plainText, html);

        mailSender.send(message);
    }

    private static String buildDetailsUrl(URI baseUri, String orderCode) {
        if (!"https".equalsIgnoreCase(baseUri.getScheme())
                || baseUri.getHost() == null
                || baseUri.getUserInfo() != null) {
            throw new IllegalArgumentException(
                    "Base URL của ứng dụng không hợp lệ"
            );
        }

        // orderCode đã được kiểm tra theo allowlist ở tầng request.
        String base = baseUri.toString().replaceAll("/+$", "");
        return base + "/orders/" + orderCode;
    }
}
~~~

Phần `buildDetailsUrl` được giữ đơn giản vì mã đơn đã bị giới hạn thành chữ hoa, số và dấu gạch ngang. Nếu path segment có thể chứa ký tự khác, hãy dùng URI builder và encode path segment theo đúng quy tắc URL; không nối chuỗi tùy tiện. Trong hệ thống thật, cũng cần bảo đảm `publicBaseUri` đến từ cấu hình đáng tin cậy và chỉ cho phép domain được quản trị.

Ví dụ tập trung vào phần chuẩn bị template và message. Việc gửi thật còn phụ thuộc cấu hình SMTP, quyền sử dụng `From`, chính sách người nhận và xử lý lỗi `MailException`.

### 14.5. Điều gì đã được bảo vệ ở đâu?

| Thành phần | Nơi kiểm soát | Cơ chế |
| --- | --- | --- |
| Địa chỉ người nhận | DTO / service | Bean Validation và authorization |
| Mã đơn | DTO / domain | Allowlist định dạng |
| Tên và ghi chú | Template output | `th:text` HTML escaping |
| Tên template | Code ứng dụng | Hằng số/allowlist |
| Expression | File template | Template source do ứng dụng quản lý |
| URL | Service / cấu hình | Base HTTPS tin cậy, kiểm tra host và path |
| SMTP credential | Cấu hình triển khai | Secret/environment management |
| MIME message | Spring Mail/Jakarta Mail | `MimeMessageHelper` |
| Kết nối gửi | JavaMailSender | SMTP, TLS và AUTH theo cấu hình |

Không có một annotation hoặc một phương thức `validate()` duy nhất làm tất cả việc trên. Mỗi ranh giới cần cơ chế phù hợp.

## 15. Nếu người dùng được phép tạo template thì sao?

Một số sản phẩm cho quản trị viên hoặc tenant tự chỉnh sửa mẫu email. Khi đó, template không còn hoàn toàn là mã do nhóm phát triển kiểm soát. Cần quyết định rõ mức tự do được cấp.

### Mức 1: Chỉ cho thay văn bản tĩnh

Cho phép người dùng chỉnh tiêu đề hoặc đoạn văn bản, nhưng không cho nhập expression. Nội dung được xuất như text hoặc qua một editor có quy tắc rõ ràng.

### Mức 2: Cho dùng placeholder allowlist

Ví dụ chỉ hỗ trợ:

~~~text
{{customerName}}
{{orderCode}}
{{supportUrl}}
~~~

Ứng dụng thay placeholder từ một danh sách tên biến cố định. Không cho placeholder chứa expression, method call, bean reference hay cú pháp tùy ý. Giá trị thay thế phải được escape theo vị trí HTML, và parser phải xử lý placeholder rõ ràng thay vì đánh giá nó như Spring EL.

### Mức 3: Cho rich HTML có giới hạn

Nếu cho phép người dùng chỉnh markup, dùng HTML sanitizer với allowlist thẻ/thuộc tính/URL. Expression Thymeleaf nên bị cấm hoặc không được đánh giá trong nguồn do người dùng cung cấp.

### Mức 4: Cho template expression nâng cao

Đây là mức rủi ro cao hơn. Cần một thiết kế riêng: template language giới hạn, evaluation context tối thiểu, dữ liệu view model đã kiểm soát, giới hạn thời gian/kích thước render, cách ly tenant và review bảo mật. Không nên đơn giản cho phép người dùng gửi Thymeleaf template bất kỳ rồi render bằng cùng engine có quyền truy cập application context của ứng dụng.

**Không xem sanitizer HTML là sandbox expression.** Một bộ lọc loại bỏ thẻ script không nhất thiết hiểu hoặc loại bỏ mọi cú pháp template. Cần xử lý cả hai ngôn ngữ theo đúng tầng của chúng.

## 16. Kiểm soát template name, locale và nội dung expression

Ngoài dữ liệu text, có một số giá trị có thể vô tình điều khiển việc render:

| Giá trị | Rủi ro nếu không kiểm soát | Cách làm |
| --- | --- | --- |
| Template name | Chọn template ngoài ý định hoặc khai thác resolver | Enum/allowlist trong code |
| Fragment name | Chọn fragment không được phép | Hằng số hoặc map lựa chọn đã duyệt |
| Locale | Yêu cầu bundle không hỗ trợ, fallback bất ngờ | Allowlist locale |
| Expression string | Đánh giá cú pháp do người dùng điều khiển | Không parse/evaluate expression từ input |
| Collection cho `th:each` | Render quá nhiều dòng, tốn bộ nhớ | Giới hạn kích thước và kiểu dữ liệu |
| URL | Liên kết giả mạo hoặc destination không mong muốn | Base URL tin cậy, kiểm tra scheme/host |
| HTML rich text | Markup hoặc thuộc tính ngoài chính sách | Sanitizer allowlist hoặc hiển thị như text |

Nếu template có điều kiện:

~~~html
<div th:if="${mail.paid}">
  Đơn hàng đã thanh toán.
</div>
~~~

`mail.paid` nên là boolean đã được tính từ kết quả nghiệp vụ, không phải chuỗi `"true"` do người dùng gửi lên mà chưa kiểm tra. Template thể hiện cách hiển thị; nó không phải nơi xác định một khoản thanh toán đã thành công.

Tương tự, không dùng expression để tính lại số tiền, quyền truy cập hoặc trạng thái đơn hàng. Những quyết định đó phải đến từ domain/service có thẩm quyền.

## 17. Kiểm tra kết quả render trước khi gửi

Khi template có nhiều biến và điều kiện, nên có kiểm thử render riêng để phát hiện lỗi expression và lỗi dữ liệu trước khi kết nối SMTP.

Ví dụ, với dữ liệu kiểm thử:

~~~java
Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("mail", new OrderMailView(
        "An <Bảo> & Co.",
        "A102",
        "Đã xác nhận",
        "Gọi trước 17:00 & hỏi lễ tân",
        "https://app.example.org/orders/A102"
));

String html = templateEngine.process(
        "mail/order-confirmed",
        context
);
~~~

Có thể kiểm tra đầu ra chứa nội dung hiển thị đã được escape, chẳng hạn `An &lt;Bảo&gt; &amp; Co.`, thay vì kiểm tra một chuỗi raw expression cụ thể. Cũng cần kiểm tra:

- Template được tìm thấy và render không ném lỗi.
- Các biến bắt buộc được cung cấp.
- Nhánh điều kiện và danh sách có dữ liệu rỗng hoạt động hợp lý.
- Link được tạo từ domain mong đợi.
- Dữ liệu có ký tự đặc biệt không tạo markup ngoài ý muốn.
- Bản plain text vẫn giữ văn bản logic, không chứa HTML entity.
- Nội dung và số lượng phần tử không vượt giới hạn của ứng dụng.

### Payload kiểm tra trong môi trường test

Một số chuỗi có thể dùng để xác minh escaping text node:

~~~text
An <Bảo> & Co.
"VIP" và 'khách hàng'
<p>Đây là ghi chú</p>
5 < 10 & 10 > 5
~~~

Khi đưa vào `th:text`, các ký tự có ý nghĩa HTML phải được biểu diễn dưới dạng text. Kiểm thử này nhằm xác nhận **đầu ra render**, không cần gửi email thật.

Không cần dùng payload khai thác phức tạp trong dữ liệu production. Các test có kiểm soát giúp xác nhận ranh giới template/data mà không làm lộ thông tin khách hàng.

### Không log context đầy đủ

Context có thể chứa tên, địa chỉ email, mã đơn, URL có token và ghi chú riêng tư. Khi template render lỗi, log nên ghi tên template, mã yêu cầu, loại lỗi và các metadata tối thiểu. Không dump toàn bộ context hoặc raw HTML vào log production nếu không có chính sách bảo vệ phù hợp.

## 18. Những lỗi thường gặp

### 18.1. Nối dữ liệu người dùng vào template source

**Lỗi:** người dùng có thể thay đổi markup hoặc expression được engine xử lý.

**Cách làm:** giữ template cố định, truyền dữ liệu qua context và dùng escaped output.

### 18.2. Đưa expression do người dùng nhập vào parser

**Lỗi:** chuỗi input trở thành biểu thức được đánh giá.

**Cách làm:** không parse/evaluate expression từ request. Dùng biến và lựa chọn allowlist.

### 18.3. Cho người dùng chọn template bằng đường dẫn tùy ý

**Lỗi:** template resolver có thể tìm nội dung ngoài danh sách mong muốn, tùy cấu hình resolver.

**Cách làm:** map mã nghiệp vụ sang tên template cố định.

### 18.4. Dùng th:utext cho ghi chú tự do

**Lỗi:** dữ liệu có thể được diễn giải như markup.

**Cách làm:** dùng `th:text`; nếu cần rich HTML, sanitize bằng allowlist.

### 18.5. Đưa toàn bộ entity hoặc service vào context

**Lỗi:** template có thể nhìn thấy nhiều thuộc tính/phương thức hơn cần thiết, làm tăng phạm vi dữ liệu và khả năng truy cập.

**Cách làm:** tạo DTO/view model chỉ có trường được phép hiển thị.

### 18.6. Nhầm validation với escaping

**Lỗi:** kiểm tra tên không rỗng nhưng vẫn nối thẳng vào HTML.

**Cách làm:** validation theo nghiệp vụ, sau đó escaping theo ngữ cảnh xuất.

### 18.7. Escape mọi dữ liệu ngay khi lưu database

**Lỗi:** dữ liệu bị gắn với ngữ cảnh HTML, có thể hiển thị entity trong plain text hoặc bị double escaping.

**Cách làm:** giữ dữ liệu logic và escape tại thời điểm render HTML.

### 18.8. Cho URL đầu vào quyết định host

**Lỗi:** liên kết trong email có thể trỏ tới host không được phép.

**Cách làm:** dùng base URL tin cậy, kiểm tra scheme/host và encode thành phần path/query.

### 18.9. Dùng template để tính quyết định nghiệp vụ

**Lỗi:** expression hiển thị trạng thái thanh toán hoặc quyền truy cập dựa trên dữ liệu chưa được xác thực.

**Cách làm:** tính quyết định trong service/domain, truyền kết quả rõ ràng vào view model.

### 18.10. Nghĩ MimeMessageHelper tự xử lý template security

**Lỗi:** helper chỉ dựng MIME content; nó không biết expression nào được phép và dữ liệu nào đáng tin cậy.

**Cách làm:** xử lý template và input trước khi gọi `setText(...)`.

## 19. Bài tập suy luận

**Câu 1.** Template có `th:text="${customerName}"` và context chứa tên `An <Bảo>`. Có cần tự escape tên trước khi đặt vào context không?

Thông thường **không**, nếu template dùng escaped output `th:text`. Hãy truyền chuỗi dữ liệu logic và để template escape tại điểm xuất. Tránh escape hai lần.

**Câu 2.** Request gửi lên chuỗi `${T(...)}`. Nếu ứng dụng chỉ đặt chuỗi đó vào biến và hiển thị bằng `th:text`, nó có tự được đánh giá thành expression không?

Không. Trong trường hợp đó, chuỗi là giá trị dữ liệu được xuất như text. Rủi ro xuất hiện nếu ứng dụng đưa chuỗi vào template source hoặc expression parser để đánh giá.

**Câu 3.** Có thể cho client truyền `templateName` rồi gọi `templateEngine.process(templateName, context)` không?

Không nên dùng tên template tùy ý từ client. Hãy ánh xạ một mã template nghiệp vụ đã được cho phép sang tên cố định.

**Câu 4.** Vì sao không nên đưa toàn bộ `OrderEntity` vào context?

Entity có thể chứa nhiều quan hệ, dữ liệu nhạy cảm và phương thức không cần cho email. DTO/view model nhỏ giúp giới hạn dữ liệu và làm rõ hợp đồng của template.

**Câu 5.** `th:utext` có thể dùng cho ghi chú người dùng nếu đã gọi một hàm HTML escape đơn giản không?

Nếu đã escape toàn bộ, mục tiêu giữ rich HTML không còn đạt được; nếu chưa escape/sanitize, nội dung có thể trở thành markup ngoài ý muốn. Với ghi chú văn bản, dùng `th:text`. Với rich HTML, dùng sanitizer allowlist phù hợp rồi mới xuất unescaped.

**Câu 6.** `@{...}` có bảo đảm link không giả mạo không?

Không. Nó tạo URL theo cơ chế Thymeleaf, nhưng ứng dụng vẫn phải kiểm soát base URL, scheme, host và quyền truy cập tài nguyên.

**Câu 7.** Một template dùng `th:each` trên danh sách 10.000 sản phẩm. Có cần giới hạn danh sách không?

Có. Giới hạn số phần tử, kích thước dữ liệu và nội dung email để tránh render quá lớn, vượt giới hạn nhà cung cấp hoặc tiêu tốn tài nguyên.

**Câu 8.** `MimeMessageHelper.setText(html, true)` có ngăn expression injection không?

Không. Expression injection thuộc tầng template/evaluation. Helper chỉ đặt chuỗi đã render hoặc HTML đã chuẩn bị thành body MIME.

## 20. Mô hình ghi nhớ

Một template email an toàn cần kiểm soát **ba ranh giới**:

~~~mermaid
flowchart TD
    A["Request / dữ liệu từ hệ thống ngoài"] --> B["Validation + authorization"]
    B --> C["DTO / view model tối thiểu"]
    D["Template source cố định, được review"] --> E["Template engine"]
    C --> E
    E --> F["HTML render: escaped output"]
    F --> G["MimeMessageHelper"]
    G --> H["JavaMailSender / SMTP"]
~~~

Hãy ghi nhớ các nguyên tắc:

1. **Expression là cú pháp template, dữ liệu đầu vào là giá trị.** Không biến chuỗi người dùng thành expression hoặc template source.
2. **Giữ template source trong quyền kiểm soát của ứng dụng.** Tên template, fragment, locale và lựa chọn template phải qua allowlist.
3. **Truyền dữ liệu bằng context và DTO nhỏ.** Chỉ đưa những trường thật sự cần hiển thị vào template.
4. **Validate theo nghiệp vụ trước khi render.** Kiểm tra địa chỉ, mã, kích thước, trạng thái và quyền truy cập; không xóa ký tự đặc biệt một cách tùy tiện.
5. **Dùng escaped output cho text.** Trong Thymeleaf, `th:text` phù hợp với dữ liệu văn bản; `th:utext` chỉ dùng với HTML đã được kiểm soát/sanitize.
6. **Kiểm soát URL riêng.** Expression URL và HTML attribute escaping không thay thế xác thực scheme, host hoặc quyền truy cập.
7. **Giới hạn collection và dữ liệu context.** Template chỉ nên trình bày dữ liệu đã được chuẩn bị, không tự quyết định nghiệp vụ quan trọng.
8. **Kiểm thử render trước khi gửi.** Kiểm tra kết quả HTML/plain text và xử lý lỗi template tách biệt với lỗi SMTP.
9. **Không coi template engine là sandbox cho template không tin cậy.** Nếu cần cho người dùng tùy biến template, hãy thiết kế ngôn ngữ giới hạn và cơ chế cách ly riêng.

Trong Spring Framework Mail, ứng dụng nên hoàn tất việc kiểm tra đầu vào và render template trước khi gọi `MimeMessageHelper.setText(...)`. Thymeleaf đảm nhiệm việc đánh giá expression cố định và xuất dữ liệu theo quy tắc template; `MimeMessageHelper` đóng gói nội dung thành MIME; `JavaMailSender` gửi message qua SMTP. Khi ranh giới giữa **expression, template source và dữ liệu đầu vào** được giữ rõ ràng, email có thể cá nhân hóa mà vẫn kiểm soát được nội dung và phạm vi dữ liệu được phép hiển thị.
