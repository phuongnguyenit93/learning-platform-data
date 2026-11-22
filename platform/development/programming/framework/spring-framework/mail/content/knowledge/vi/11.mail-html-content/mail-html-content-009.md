# Template engine và ranh giới giữa dữ liệu với markup

Email HTML giúp ứng dụng Spring gửi thông báo có bố cục, màu sắc, nút hành động và nội dung được cá nhân hóa. Thay vì nối nhiều chuỗi HTML trong Java, ứng dụng thường dùng **template engine**: một file template chứa cấu trúc HTML và những vị trí được thay bằng dữ liệu khi gửi thư.

Khả năng chèn dữ liệu động cũng tạo ra một ranh giới quan trọng:

> **Markup là cấu trúc trình bày do ứng dụng thiết kế và kiểm soát; dữ liệu là giá trị được đưa vào cấu trúc ấy, có thể đến từ người dùng hoặc hệ thống khác.**

Nếu ứng dụng vô tình coi dữ liệu chưa đáng tin cậy là markup, một tên khách hàng hoặc ghi chú đơn hàng có thể biến thành thẻ HTML, liên kết giả mạo hoặc nội dung làm thay đổi bố cục thư. Ngược lại, nếu tất cả nội dung đều bị xử lý như văn bản thuần, các đoạn HTML được chủ động thiết kế có thể xuất hiện nguyên dạng trên mail client.

Trong **Spring Framework Mail**, một kiến trúc thường gặp là **Thymeleaf** (hoặc một template engine tương đương) dựng HTML, sau đó **`JavaMailSender`** và **`MimeMessageHelper`** đóng gói HTML đó thành một MIME message. Bài học giải thích ranh giới giữa dữ liệu và markup, cách escape theo ngữ cảnh, ví dụ Spring Boot/Thymeleaf và những sai lầm phổ biến.

## 1. Template engine đóng vai trò gì trong email HTML?

Một template engine nhận **template** và **model dữ liệu**, sau đó tạo ra chuỗi kết quả:

```text
Sự kiện nghiệp vụ: đơn hàng đã xác nhận
               |
               v
   Xây dựng mail model có kiểu dữ liệu rõ ràng
   - customerName
   - orderCode
   - orderUrl
               |
               v
     Template engine (ví dụ Thymeleaf)
       + template HTML do ứng dụng viết
       + dữ liệu từ mail model
               |
               v
     Chuỗi HTML đã được render
               |
               v
     MimeMessageHelper.setText(..., html)
               |
               v
      Jakarta Mail tạo MIME message
               |
               v
          JavaMailSender
               |
               v
     SMTP server -> mail client
```

Hai khối công việc không nên trộn lẫn:

1. **Render:** template engine quyết định ký tự hoặc cấu trúc HTML xuất hiện ở phần thân thư từ template và dữ liệu.
2. **Send:** Spring Mail/Jakarta Mail đóng gói nội dung dưới dạng MIME, thiết lập người gửi/người nhận, charset và chuyển thư qua SMTP.

`MimeMessageHelper` **không phải template engine**: nó có thể khai báo một phần body là HTML nhưng không tự quyết định liệu giá trị `customerName` có được HTML-escape hay không. Template engine cũng **không gửi thư**; kết quả render phải được đưa vào một message rồi giao cho sender.

### Khi nào nên dùng template engine?

- Nhiều email dùng chung header, footer, logo và quy tắc bố cục.
- Nội dung thay đổi theo dữ liệu đơn hàng, người dùng hoặc ngôn ngữ.
- HTML có điều kiện hiển thị (ví dụ có/không có mã giảm giá).
- Cần duy trì mẫu email riêng biệt với mã nghiệp vụ.
- Muốn có quy ước nhất quán về escape giá trị động.

Với một email text rất đơn giản, dùng `SimpleMailMessage` có thể đủ. Nhưng khi cần **HTML và data binding an toàn**, template engine thường làm ranh giới giữa dữ liệu và cấu trúc rõ ràng hơn.

## 2. Hiểu ranh giới: đâu là markup, đâu là dữ liệu?

Xét email chào mừng có tên người dùng.

**Markup do ứng dụng thiết kế:**

```html
<p>Xin chào, <strong>...</strong>!</p>
<p>Cảm ơn bạn đã đăng ký.</p>
```

**Dữ liệu đến từ hệ thống:**

```text
customerName = "Nguyễn An"
```

Kết quả mong muốn:

```html
<p>Xin chào, <strong>Nguyễn An</strong>!</p>
<p>Cảm ơn bạn đã đăng ký.</p>
```

Ở trường hợp bình thường, hai cách làm có thể trông giống nhau:

```java
// Không nên ghép dữ liệu tùy ý trực tiếp vào HTML.
String html = "<p>Xin chào, <strong>" + customerName
        + "</strong>!</p>";
```

Nhưng nếu `customerName` chứa ký tự HTML đặc biệt:

```text
customerName = "<b>Khách VIP</b> & bạn"
```

Với cách nối chuỗi thô, văn bản trên có thể trở thành **markup thực sự**. Thẻ `<b>` được diễn giải như cấu trúc HTML thay vì một phần của tên người dùng. Dữ liệu đã vượt qua ranh giới mà ứng dụng cần bảo vệ.

Kết quả đúng nếu muốn hiển thị **giá trị nguyên văn** là:

```html
<p>Xin chào, <strong>&lt;b&gt;Khách VIP&lt;/b&gt; &amp; bạn</strong>!</p>
```

Mail client hiển thị tên là `<b>Khách VIP</b> & bạn` dưới dạng chữ, không biến `<b>` do người dùng nhập thành một tag mới.

**Quy tắc:** dữ liệu không tự trở thành mã HTML chỉ vì nó chứa các ký tự `<`, `>` hoặc dấu nháy. Template quyết định cấu trúc, còn giá trị động phải được đưa vào bằng thao tác phù hợp với **ngữ cảnh HTML**.

## 3. HTML escaping: cơ chế bảo vệ cơ bản

**HTML escaping** chuyển những ký tự có ý nghĩa đặc biệt trong HTML sang dạng entity để chúng được hiển thị như dữ liệu:

| Ký tự trong dữ liệu | Biểu diễn HTML thường gặp | Vì sao cần xử lý? |
| --- | --- | --- |
| `&` | `&amp;` | Tránh bị hiểu thành đầu một HTML entity |
| `<` | `&lt;` | Tránh bắt đầu một tag HTML |
| `>` | `&gt;` | Tránh kết thúc một tag theo cách không mong muốn |
| `"` | `&quot;` | Cần chú ý trong thuộc tính có dấu nháy kép |
| `'` | `&#39;` hoặc một biểu diễn phù hợp | Cần chú ý trong thuộc tính có dấu nháy đơn |

Tên entity cụ thể có thể khác nhau giữa các bộ escape, miễn khi parse HTML chúng giữ được ý nghĩa văn bản mong muốn. Ứng dụng thường **không cần tự thay từng ký tự**; hãy để template engine thực hiện escaping phù hợp với ngữ cảnh.

### Escaping khác validation và sanitization

Ba hoạt động này giải quyết những vấn đề khác nhau:

- **Validation:** dữ liệu có đáp ứng điều kiện nghiệp vụ không? Ví dụ mã đơn hàng có đúng định dạng, link có dùng HTTPS và thuộc miền cho phép?
- **Escaping/output encoding:** khi chèn dữ liệu vào HTML, ký tự cần được biểu diễn ra sao để không trở thành cú pháp markup?
- **Sanitization:** nếu thật sự chấp nhận **HTML do một nguồn bên ngoài cung cấp**, giữ lại chỉ một tập tag/attribute/protocol đã cho phép và loại bỏ phần nguy hiểm.

Ví dụ:

```text
Input:  "<strong>Xin chào</strong>"

Escape như văn bản:
  "&lt;strong&gt;Xin chào&lt;/strong&gt;"
  -> Hiển thị nguyên chữ <strong>Xin chào</strong>

Sanitize như đoạn HTML được cho phép:
  "<strong>Xin chào</strong>"
  -> Hiển thị chữ Xin chào được in đậm
```

Hai kết quả phục vụ **hai ý định sản phẩm khác nhau**. Không được chọn cách xử lý raw HTML chỉ vì muốn “giữ định dạng” mà chưa có chính sách cho phép markup.

### Cẩn thận với double escaping

Giả sử ứng dụng tự HTML-escape tên:

```text
Input:       A & B
Manual:      A &amp; B
```

Nếu sau đó lại đưa giá trị `A &amp; B` vào thao tác template **tự escape**, kết quả có thể là:

```html
A &amp;amp; B
```

Mail client sẽ hiển thị `A &amp; B` thay vì `A & B`. Vì vậy, hãy đưa **giá trị gốc đã được kiểm tra nghiệp vụ** cho một thao tác template escape đúng ngữ cảnh, thay vì tự encode trước rồi encode lần nữa.

## 4. Thymeleaf: `th:text` và `th:utext` khác nhau

Thymeleaf là template engine phổ biến trong ứng dụng Spring. Khi render HTML:

- **`th:text`:** đặt nội dung dưới dạng **escaped text**; giá trị được xử lý để không trở thành HTML markup.
- **`th:utext`:** đặt nội dung dưới dạng **unescaped text**; chuỗi có thể được diễn giải thành HTML markup.

Ví dụ template:

```html
<p>
  Xin chào,
  <span th:text="${customerName}">Khách hàng</span>
</p>
```

Model:

```java
context.setVariable(
        "customerName",
        "<strong>Người dùng mới</strong>"
);
```

Thymeleaf với `th:text` sẽ đưa giá trị vào vị trí của `span` **dưới dạng văn bản đã escape**. Một đoạn HTML tương đương:

```html
<span>&lt;strong&gt;Người dùng mới&lt;/strong&gt;</span>
```

Trong khi đó:

```html
<span th:utext="${customerName}">Khách hàng</span>
```

có thể đưa trực tiếp chuỗi `<strong>Người dùng mới</strong>` vào output, khiến tag `strong` trở thành markup.

### Vì sao `th:utext` nguy hiểm với dữ liệu ngoài?

Nếu một trường ghi chú hoặc tên người dùng được chuyển qua `th:utext`, người dùng có thể cung cấp HTML để làm sai bố cục, chèn liên kết giả mạo, hình ảnh theo dõi hoặc nội dung không mong muốn. Một số mail client lọc script và HTML nguy hiểm, nhưng **không được dựa vào việc lọc của mail client để bảo vệ nội dung email**.

Ví dụ **không nên làm**:

```html
<!-- UNSAFE nếu customerNote do người dùng hoặc nguồn ngoài nhập -->
<div th:utext="${customerNote}"></div>
```

Nên làm khi chỉ cần hiển thị ghi chú dạng văn bản:

```html
<p th:text="${customerNote}">Ghi chú đơn hàng</p>
```

Nếu thực sự phải hỗ trợ rich text:

1. Xác định rõ chỉ cho phép những thành phần markup nào.
2. Dùng bộ sanitize HTML đáng tin cậy, cấu hình **allowlist tag/attribute/protocol** cho ngữ cảnh email.
3. Loại bỏ script, event handlers, iframe, URL nguy hiểm và CSS không được phép.
4. Chỉ dùng raw/unescaped output cho **kết quả đã được sanitize** theo chính sách đó.
5. Ghi nhận rằng sanitization và tính tương thích HTML email vẫn cần được duy trì khi hệ thống hoặc thư viện thay đổi.

Với phần lớn email giao dịch, **không cần cho người dùng cung cấp HTML**; dữ liệu text qua `th:text` là phương án đơn giản và ít rủi ro hơn.

## 5. Escaping phải phụ thuộc vào vị trí dữ liệu được chèn

Không có một thao tác “escape mọi thứ” dùng đúng cho tất cả tình huống. Một biến có thể được chèn vào:

1. Nội dung văn bản giữa hai tag HTML.
2. Giá trị attribute như `title`, `alt` hoặc `href`.
3. URL đích của liên kết.
4. CSS hoặc thuộc tính `style`.
5. Một phần markup đã được cho phép theo chính sách.

Mỗi trường hợp cần **phân biệt cấu trúc cố định với giá trị động**.

### 5.1. Text node — dùng escaped text

```html
<p>Mã đơn hàng: <strong th:text="${orderCode}">ORD-001</strong></p>
```

Khi `orderCode` là dữ liệu, Thymeleaf đưa nó vào như văn bản, không như thẻ HTML.

### 5.2. HTML attribute — dùng cơ chế đặt attribute của template

```html
<img src="cid:brandLogo"
     th:alt="${companyDisplayName}"
     width="120"
     height="40"/>
```

`th:alt` giúp đặt giá trị của attribute và xử lý các ký tự đặc biệt theo cách template engine hỗ trợ. Không tự nối:

```java
// Không nên ghép attribute với dữ liệu không kiểm soát.
String img = "<img alt=\"" + companyDisplayName + "\" ...>";
```

Tên hiển thị chứa dấu nháy hoặc ký tự đặc biệt không nên được phép làm vỡ cú pháp attribute.

### 5.3. URL trong `href` — escape chưa đủ

Đây là ranh giới quan trọng:

```html
<a th:href="${orderUrl}">Xem đơn hàng</a>
```

Template engine có thể escape giá trị attribute đúng cú pháp, **nhưng một chuỗi URL vẫn có thể trỏ tới đích không an toàn**. Ví dụ, nếu `orderUrl` được lấy trực tiếp từ request và chứa một host giả mạo hoặc scheme không cho phép, việc HTML-escape dấu nháy **không biến URL đó thành URL an toàn**.

Vì vậy, với liên kết trong email:

- Ưu tiên tạo URL từ **base URL do hệ thống quản lý**, không phải từ giá trị tùy ý của người dùng.
- Chỉ cho phép scheme có mục đích hợp lệ; với nút truy cập ứng dụng, thường cần **HTTPS**.
- Kiểm tra host/domain theo danh sách tin cậy khi dữ liệu nguồn có thể ảnh hưởng đến đích.
- Mã hóa từng phần của URL (path segment, query parameter) bằng công cụ xây URI phù hợp khi chúng chứa giá trị động.
- Đặt nội dung hiển thị của nút một cách minh bạch, không che giấu URL dẫn đến miền lạ.

Ví dụ an toàn về mặt cấu trúc với ID đã có kiểu:

```java
UUID orderId = /* ID đơn hàng đã được xác định */;

// Base URL do ứng dụng sở hữu; orderId có định dạng UUID.
String orderUrl = "https://app.example.org/orders/" + orderId;
context.setVariable("orderUrl", orderUrl);
```

Đây là URL minh họa. Trong triển khai thật, hostname cần được cấu hình/kiểm soát theo môi trường và bảo đảm người nhận có quyền truy cập đơn hàng; **biết link không tự cấp quyền truy cập**.

### 5.4. CSS hoặc `style` — không đưa CSS tự do từ người dùng

HTML email thường dùng inline CSS vì nhiều mail client hỗ trợ hạn chế CSS. Tuy nhiên, chèn một chuỗi không tin cậy vào thuộc tính `style` cũng có thể gây sai bố cục hoặc tạo ra tham chiếu tài nguyên không mong muốn.

Không nên:

```html
<div th:style="${userProvidedCss}">Nội dung</div>
```

Thay vào đó, chọn giữa một số style **cố định và được kiểm soát**:

```html
<p th:style="${isUrgent}
          ? 'color: #b42318; font-weight: bold;'
          : 'color: #344054;'">
  Thông báo
</p>
```

Ở ví dụ này, `isUrgent` là một boolean do nghiệp vụ xác định; hai chuỗi CSS do ứng dụng viết. Không đưa một đoạn CSS tùy ý từ dữ liệu ngoài vào template.

### 5.5. JavaScript không phải cách tạo tương tác trong email

Đừng thiết kế email HTML dựa vào `<script>`, event handler như `onclick` hoặc các cơ chế browser có thể bị mail client chặn. Email phù hợp thường dùng **liên kết HTTPS** dẫn tới website hoặc ứng dụng, nơi hành động của người dùng được xác thực và kiểm tra quyền.

Một template engine không làm HTML email trở thành một trang web tương tác đầy đủ.

## 6. Ranh giới dữ liệu không chỉ ở tên khách hàng

Cần xem tất cả biến được đưa vào template như **dữ liệu**, trừ khi chúng thực sự là nội dung markup do ứng dụng sở hữu và được kiểm soát:

| Trường dữ liệu | Nguồn có thể có | Cách đưa vào email |
| --- | --- | --- |
| `customerName` | Hồ sơ người dùng | `th:text`, giới hạn độ dài |
| `orderCode` | Database | `th:text`, định dạng rõ |
| `productName` | Danh mục sản phẩm, dữ liệu đối tác | `th:text`, không coi là HTML |
| `customerNote` | Người dùng nhập | `th:text`; không dùng `th:utext` trực tiếp |
| `priceLabel` | Logic format tiền tệ | `th:text` sau khi định dạng |
| `orderUrl` | URL xây từ domain tin cậy và ID | `th:href` với URL đã được kiểm soát |
| `buttonLabel` | Chuỗi do ứng dụng hoặc localization cung cấp | `th:text` |
| `statusColor` | Quy tắc trình bày của ứng dụng | Enum/boolean ánh xạ sang CSS cố định |
| `trackingId` | Mã tương quan nghiệp vụ | Chỉ đưa vào nếu cần, tránh lộ dữ liệu nhạy cảm |

Ngay cả dữ liệu “từ database” cũng chưa chắc là tin cậy để render raw HTML. Một trường có thể đã được người dùng nhập và lưu từ trước. **Lưu vào database không biến nó thành markup an toàn**.

### Dữ liệu nghiệp vụ nên có kiểu rõ ràng

Ví dụ một model:

```java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderMailData(
        UUID orderId,
        String orderCode,
        String customerName,
        BigDecimal totalAmount
) {}
```

Đặt dữ liệu có kiểu rõ ràng giúp tầng nghiệp vụ giới hạn nguồn và trạng thái. Template chỉ nhận những trường đã chọn, thay vì truyền cả entity chứa mật khẩu, token, địa chỉ nội bộ hoặc dữ liệu không dành cho người nhận.

Không nên gắn toàn bộ entity người dùng vào template context chỉ vì làm vậy tiện. **Data minimization** giúp giảm nguy cơ vô tình đưa thông tin nhạy cảm vào email.

## 7. Ví dụ Spring Boot: Thymeleaf + Spring Framework Mail

Một ứng dụng cần gửi email **xác nhận đơn hàng bằng HTML** và thêm phiên bản text thuần. Mục tiêu:

- Sử dụng HTML template nằm trong classpath.
- Thay tên người nhận và mã đơn bằng **escaped text**.
- Tạo URL bằng domain tin cậy và `UUID`.
- Đưa HTML đã render vào `MimeMessage` bằng `MimeMessageHelper`.
- Giữ các header `From`, `To`, `Subject` tách biệt khỏi template HTML.

### 7.1. Dependency

Với Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-thymeleaf</artifactId>
    </dependency>
</dependencies>
```

Starter Mail cung cấp tích hợp gửi thư; starter Thymeleaf cung cấp template engine và cấu hình phù hợp trong Spring Boot. Template engine **render chuỗi**, còn mail sender **tạo và gửi message**.

### 7.2. Cấu hình SMTP

Ví dụ `application.yml` cho một SMTP submission server hỗ trợ STARTTLS trên cổng 587:

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM_ADDRESS}
```

Đây là cấu hình minh họa. Khi triển khai, cần chọn host, port, TLS và credential theo nhà cung cấp; dùng secret manager hoặc môi trường thay vì hardcode mật khẩu.

`spring.mail.default-encoding=UTF-8` giúp xử lý ký tự tiếng Việt khi tạo MIME text/HTML. Nó **không thay thế HTML escaping** ở bước render template.

### 7.3. Tạo template HTML

Đặt file:

```text
src/main/resources/templates/mail/order-confirmation.html
```

Ví dụ nội dung template:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Xác nhận đơn hàng</title>
</head>
<body style="margin: 0; padding: 24px; font-family: Arial, sans-serif;">
  <main style="max-width: 600px; margin: 0 auto;">
    <h1 style="font-size: 24px; color: #1d2939;">
      Đơn hàng đã được xác nhận
    </h1>

    <p>
      Xin chào,
      <strong th:text="${customerName}">Khách hàng</strong>!
    </p>

    <p>
      Đơn hàng
      <strong th:text="${orderCode}">ORD-EXAMPLE</strong>
      đã được ghi nhận.
    </p>

    <p>
      <a th:href="${orderUrl}"
         style="display: inline-block; padding: 12px 16px;
                background-color: #175cd3; color: #ffffff;
                text-decoration: none; border-radius: 6px;">
        Xem đơn hàng
      </a>
    </p>

    <p style="color: #667085; font-size: 13px;">
      Nếu bạn không thực hiện đơn hàng này,
      hãy truy cập ứng dụng hoặc liên hệ bộ phận hỗ trợ.
    </p>
  </main>
</body>
</html>
```

Điểm đáng chú ý:

- `th:text` được dùng cho tên khách hàng và mã đơn, để nội dung được **escape** thay vì được coi là markup.
- `th:href` dùng biến URL đã được tạo bởi backend từ một domain tin cậy.
- Các thẻ và thuộc tính CSS mang tính cấu trúc đều do **ứng dụng viết sẵn**.
- Chuỗi mẫu nằm giữa tag, như `Khách hàng` hoặc `ORD-EXAMPLE`, là nội dung dự phòng trong file template; khi render bằng Thymeleaf, chúng được thay bằng giá trị từ context.
- `<meta charset="UTF-8">` là thông tin bên trong HTML; MIME text part vẫn cần charset tương ứng khi gửi qua email.

Đây là ví dụ HTML email đơn giản. Các mail client có mức hỗ trợ CSS khác nhau; bố cục production có thể cần dùng table layout hoặc các quy tắc CSS tương thích hơn, nhưng **nguyên tắc tách dữ liệu khỏi markup không thay đổi**.

### 7.4. Service tạo HTML và gửi bằng `JavaMailSender`

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.UUID;

@Service
public class OrderConfirmationMailService {

    private static final String ORDER_URL_PREFIX =
            "https://app.example.org/orders/";

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;
    private final String fromAddress;

    public OrderConfirmationMailService(
            JavaMailSender mailSender,
            TemplateEngine templateEngine,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
        this.fromAddress = fromAddress;
    }

    public void sendOrderConfirmation(
            String recipient,
            String customerName,
            UUID orderId,
            String orderCode
    ) throws MessagingException {

        // Domain cố định do ứng dụng kiểm soát.
        // UUID giúp phần ID có cú pháp dự đoán được.
        String orderUrl = ORDER_URL_PREFIX + orderId;

        Context context = new Context(Locale.forLanguageTag("vi"));
        context.setVariable("customerName", customerName);
        context.setVariable("orderCode", orderCode);
        context.setVariable("orderUrl", orderUrl);

        // Template tự xử lý escaping qua th:text/th:href.
        String html = templateEngine.process(
                "mail/order-confirmation", context
        );

        // Bản text giúp mail client không hiển thị HTML.
        String plain = "Xin chào " + customerName + "!\n"
                + "Đơn hàng " + orderCode + " đã được xác nhận.\n"
                + "Xem đơn hàng: " + orderUrl;

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng " + orderCode);
        helper.setText(plain, html);

        mailSender.send(message);
    }
}
```

Các giá trị `recipient`, `customerName` và `orderCode` trong ví dụ được giả định đã qua kiểm tra nghiệp vụ thích hợp (độ dài, đúng người nhận, định dạng mã đơn). `orderId` là `UUID`; URL cố định chỉ là hostname minh họa, cần thay bằng domain HTTPS đáng tin cậy theo môi trường và bảo đảm người nhận phải đăng nhập/được cấp quyền khi mở trang chi tiết.

**Điều gì giữ ranh giới an toàn?**

1. Template engine nhận `customerName` và `orderCode` như **giá trị dữ liệu**.
2. File HTML sử dụng `th:text`, không `th:utext`, cho các trường động đó.
3. URL được xây dựng từ prefix HTTPS do ứng dụng sở hữu, không chấp nhận một URL tùy ý do người dùng cung cấp.
4. `MimeMessageHelper` đặt `From`, `To` và `Subject` bằng API riêng, không ghép chúng vào HTML template.
5. `setText(plain, html)` tạo các phiên bản text và HTML của cùng nội dung; không tự xây MIME headers.

### 7.5. Khi gửi nhiều email, có nên dùng chung Context?

Không nên chia sẻ một `Context` có thể thay đổi giữa các luồng gửi song song. Mỗi email nên tạo một context riêng chứa dữ liệu đúng người nhận:

```java
Context context = new Context(locale);
context.setVariable("customerName", name);
context.setVariable("orderCode", code);
```

Nếu một context được tái sử dụng và bị thay giá trị trong lúc nhiều email được render, nội dung cá nhân hóa có thể lẫn giữa người nhận. Template engine do Spring quản lý có thể được dùng chung theo hợp đồng của nó, còn **model/context theo request phải tách riêng**.

## 8. Vì sao nên có bản text thuần?

Email HTML có thể được render khác nhau trên Outlook, Gmail, ứng dụng mail di động hoặc client chỉ đọc text. Một số người dùng tắt HTML hoặc công cụ hỗ trợ tiếp cận ưu tiên văn bản thuần.

Trong MIME, hai phiên bản thường được đóng gói bằng **`multipart/alternative`**:

```text
MimeMessage
└── multipart/alternative
    ├── text/plain; charset=UTF-8
    │   └── "Xin chào. Đơn hàng đã xác nhận..."
    └── text/html; charset=UTF-8
        └── "<p>Xin chào...</p>"
```

Trong Spring:

```java
helper.setText(plainText, htmlText);
```

`MimeMessageHelper` sẽ tạo cấu trúc MIME phù hợp khi được khởi tạo ở chế độ multipart. **Hai bản phải có cùng ý nghĩa nghiệp vụ**: nếu HTML có đường dẫn đến đơn hàng, bản plain-text nên có URL có thể đọc và sao chép.

### Có cần escape HTML trong plain-text không?

Không theo cùng cách. Plain-text không có parser HTML để biến `<b>` thành chữ in đậm. Nếu nội dung là text, chuỗi `<b>` có thể xuất hiện nguyên dạng và không tạo ra một phần tử HTML. Tuy nhiên, vẫn cần:

- Giới hạn độ dài và định dạng các trường được phép xuất hiện.
- Xử lý ký tự xuống dòng khi người dùng không được phép phá bố cục thông báo.
- Tránh đưa dữ liệu nhạy cảm hoặc link không đáng tin cậy vào nội dung.
- Giữ văn bản dễ hiểu với người nhận.

**HTML escaping** là thao tác cần thiết tại điểm render vào markup; **text formatting/validation** là việc riêng cho bản plain-text.

## 9. Template không nên sở hữu message headers

HTML template chỉ nên tạo **body content**. Nó không phải nơi đặt các trường header email như `From`, `To`, `Subject`, `Reply-To` hoặc `Content-Type` ở mức MIME message.

Không nên tạo một chuỗi template kiểu:

```text
From: notifications@example.org
To: customer@example.net
Subject: Xác nhận đơn hàng
Content-Type: text/html

<html>...</html>
```

rồi coi toàn bộ chuỗi này như body của một `MimeMessage`. Nếu đưa vào `setText(...)`, các dòng `From:`/`Subject:` sẽ trở thành **nội dung thư**, không mặc nhiên là header. Nếu lại tự ghép raw MIME hoàn chỉnh, code phải tự xử lý toàn bộ cú pháp, charset, boundary và nhiều rủi ro khác.

Thay vào đó:

```java
String htmlBody = templateEngine.process("mail/order-confirmation", context);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setReplyTo("support@example.org");
helper.setSubject("Xác nhận đơn hàng");
helper.setText(htmlBody, true);
```

Các header do helper/Jakarta Mail quản lý riêng, trong khi `htmlBody` chỉ là body đã render. Điều này cũng giúp giảm nguy cơ **header injection** từ dữ liệu chứa CR/LF bị nối trực tiếp vào raw message headers.

**Lưu ý:** dùng helper không thay thế kiểm tra dữ liệu recipient và policy SMTP. Cần xác định người nhận hợp lệ, sender được cấp quyền và nội dung phù hợp nghiệp vụ.

## 10. Template engine có tự ngăn mọi loại injection không?

Không. `th:text` giúp ngăn một biến dữ liệu trở thành markup **ở ngữ cảnh text**. Nhưng template engine không thể tự biết một URL có đáng tin cậy, một file đính kèm có an toàn hoặc một tác vụ nghiệp vụ có được người dùng cho phép hay không.

Xem bảng:

| Ngữ cảnh | Cách làm an toàn hơn | Điều vẫn phải quản lý |
| --- | --- | --- |
| Text trong `<p>` hoặc `<span>` | `th:text` | Độ dài, nội dung nghiệp vụ |
| Text trong `title` / `alt` | Attribute processor của engine | Giá trị phù hợp và không nhạy cảm |
| Link trong `href` | `th:href` và URL xây từ domain tin cậy | Scheme, host, quyền truy cập, token |
| Ảnh trong `src` | Resource/CID hoặc URL được kiểm soát | Theo dõi, quyền riêng tư, hỗ trợ client |
| CSS trong `style` | Style cố định hoặc enum chọn style | Không cho CSS tùy ý từ input |
| Rich HTML được bên ngoài cung cấp | Sanitizer với allowlist, sau đó mới unescaped output khi thật sự cần | Cập nhật chính sách sanitizer, client compatibility |
| Subject hoặc From | `MimeMessageHelper.setSubject/setFrom` | Cú pháp, quyền gửi, độ dài và dữ liệu đầu vào |
| PDF/ảnh đính kèm | `addAttachment(...)` / `addInline(...)` | Loại file thật, byte, quyền tải, kích thước |

### Ví dụ cụ thể: URL HTML-escape đúng nhưng vẫn sai đích

Một email có:

```html
<a th:href="${redirectUrl}">Đăng nhập để xem hóa đơn</a>
```

Nếu `redirectUrl` được lấy trực tiếp từ request của người dùng và trỏ đến một domain giả, việc escape attribute không loại bỏ được rủi ro **phishing**. Đây là lỗi **độ tin cậy của URL**, không phải lỗi cú pháp HTML.

Thiết kế phù hợp hơn: URL của nút được xây bằng domain ứng dụng đáng tin cậy; nếu có tham số động, kiểm tra định dạng và mã hóa thành phần URL; khi mở link, server vẫn xác thực quyền truy cập.

## 11. Các engine và lựa chọn template cho Spring Mail

Trong hệ sinh thái Java/Spring, có nhiều lựa chọn:

| Công cụ | Phong cách template | Khi nào có thể phù hợp? |
| --- | --- | --- |
| **Thymeleaf** | HTML template với attribute như `th:text`, `th:if` | Ứng dụng Spring cần template HTML dễ xem và data binding có escape |
| **FreeMarker** | Template text với directive và interpolation riêng | Hệ thống đã dùng FreeMarker hoặc có nhiều loại template text/HTML |
| **Mustache** | Template logic-light với biến và section | Email đơn giản, muốn hạn chế logic trong template |
| **Template đơn giản tự viết** | Thay chuỗi thủ công | Chỉ phù hợp trong tình huống rất hẹp; dễ lỗi khi giá trị cần escape |

Đây là các phương án thay thế về công nghệ render, **không phải API gửi SMTP**. Dù chọn engine nào, vẫn cần:

1. Xác định rõ ngữ cảnh output và escape phù hợp.
2. Không truyền trực tiếp HTML không tin cậy vào chế độ raw/unescaped.
3. Kiểm tra URL/attribute/định dạng riêng, không chỉ dựa vào HTML escaping.
4. Dùng `JavaMailSender` để gửi message sau khi render.

Ví dụ những cơ chế raw output ở một số template engine có thể bỏ qua escaping mặc định. Không nên chuyển từ Thymeleaf sang engine khác và mặc định rằng quy tắc escape hoàn toàn giống nhau; cần nắm rõ cú pháp và chế độ mặc định của engine đang dùng.

## 12. HTML email không giống một trang web thông thường

Các mail client khác nhau về cách xử lý HTML và CSS. Một template hợp lệ khi mở trong trình duyệt vẫn có thể hiển thị khác trong inbox.

Một số điểm thực tế:

- Nhiều client giới hạn script, form, external stylesheet hoặc CSS phức tạp.
- Hình ảnh tải từ Internet có thể bị chặn hoặc được nạp qua cơ chế proxy.
- Layout dựa trên bảng và CSS inline thường được dùng để tăng khả năng tương thích.
- Nên có text thuần dự phòng và văn bản nút hành động dễ hiểu.
- Không thiết kế luồng nghiệp vụ yêu cầu người dùng chạy JavaScript ngay trong email.
- Tối ưu kích thước HTML, độ tương phản, alt text và hiển thị trên màn hình nhỏ.
- Chỉ dùng tài nguyên từ domain đáng tin cậy hoặc inline CID khi cần; không mặc định mọi client xử lý giống nhau.

### Inline image thuộc MIME, không phải HTML escaping

HTML template có thể chứa:

```html
<img src="cid:brandLogo" alt="Logo" width="120" height="40"/>
```

Để mail client tìm được ảnh, ứng dụng phải tạo **inline MIME part** tương ứng:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Thông báo mới");
helper.setText(htmlBody, true);

helper.addInline(
        "brandLogo",
        new org.springframework.core.io.ClassPathResource(
                "mail/logo.png"
        ),
        "image/png"
);

mailSender.send(message);
```

Nội dung `src="cid:brandLogo"` là một tham chiếu cố định, và `addInline` gắn dữ liệu ảnh. Đó là **cơ chế MIME** khác với việc escape tên khách hàng. Nên tạo body HTML trước khi thêm inline resource theo cách sử dụng thông thường của `MimeMessageHelper`.

## 13. Tách trách nhiệm giữa dữ liệu, template và sending

Một thiết kế dễ bảo trì có thể chia thành các tầng:

```text
Order Service
  |
  | Sự kiện "đơn hàng đã xác nhận"
  v
Mail Model Builder
  |
  | Chọn đúng dữ liệu dành cho người nhận
  | Chuẩn hóa giá trị nghiệp vụ
  | Xây URL từ base URL tin cậy
  v
Template Renderer
  |
  | Template cố định
  | th:text/th:href đúng ngữ cảnh
  | HTML đã render + plain text
  v
Mail Composer
  |
  | MimeMessageHelper
  | From/To/Subject, charset, MIME multipart
  v
JavaMailSender -> SMTP
```

Ưu điểm:

- Thay đổi layout không yêu cầu sửa logic xác nhận đơn hàng.
- Dữ liệu đi vào email được chọn lọc rõ ràng.
- URL đáng tin cậy được quyết định trước khi render.
- Helper là nơi duy nhất thiết lập message headers và MIME.
- Có thể thay template engine mà ít ảnh hưởng đến tầng gửi SMTP.
- Dễ tạo bản text thuần có cùng ngữ nghĩa với bản HTML.

### Không để template quyết định quyền truy cập

Ví dụ template có một điều kiện:

```html
<section th:if="${showDiscount}">
  <p>Bạn có ưu đãi đặc biệt.</p>
</section>
```

`th:if` chỉ quyết định **hiển thị hay không hiển thị markup**. Nó không bảo vệ API sử dụng ưu đãi. Backend vẫn phải kiểm tra người dùng có quyền dùng mã hay không. Không nên xem việc ẩn một phần HTML là một cơ chế phân quyền.

### Tránh đưa logic nghiệp vụ phức tạp vào template

Không nên viết nhiều phép tính giảm giá, trạng thái đơn hàng và truy vấn dữ liệu ngay trong biểu thức template. Hãy xử lý ở service và truyền những trường đã chuẩn bị:

```java
context.setVariable("discountLabel", "Giảm 10%");
context.setVariable("showDiscount", true);
```

Trong template:

```html
<p th:if="${showDiscount}" th:text="${discountLabel}">
  Ưu đãi
</p>
```

Khi format tiền tệ, ngày giờ và ngôn ngữ, nên xác định `Locale` phù hợp và chuẩn bị kết quả nhất quán, tránh để template phải biết cấu trúc sâu của entity hoặc phụ thuộc vào múi giờ hệ thống một cách ngầm định.

## 14. Những dấu hiệu lỗi thường gặp

| Hiện tượng | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Email hiển thị `&lt;p&gt;...&lt;/p&gt;` thay vì đoạn HTML | HTML bị escape ở tầng không phù hợp hoặc message được gửi như `text/plain` | Kiểm tra render và `setText(html, true)` |
| Tên người dùng chứa `<b>` lại làm chữ in đậm | Dùng raw output hoặc nối string trực tiếp | Dùng `th:text` |
| Tên người dùng hiển thị `&amp;` thay vì `&` | Dữ liệu bị pre-escape rồi template escape thêm | Đưa giá trị gốc vào `th:text` |
| Button dẫn tới miền lạ | URL động chưa được ràng buộc nguồn tin cậy | Tạo/validate URL ở backend |
| HTML hiển thị không giống trình duyệt | Mail client hỗ trợ HTML/CSS hạn chế | Dùng HTML email tương thích; có bản plain |
| HTML có dấu bị lỗi ký tự | Charset ở nguồn/MIME part không nhất quán | Dùng UTF-8 xuyên suốt và kiểm tra raw MIME |
| Logo `cid:brandLogo` không hiển thị | Thiếu inline part hoặc Content-ID không khớp | Gọi `addInline(...)` với đúng CID và media type |
| Email gửi được nhưng không có bản text | Chỉ gọi `setText(html, true)` | Tạo `plain` và dùng `setText(plain, html)` |
| Giá trị template không được thay | Sai tên biến hoặc template không được engine xử lý | Kiểm tra cách đưa context và gọi `process(...)` |
| Render template bị lỗi trước khi gửi | Template thiếu, biểu thức sai, data model không phù hợp | Xử lý lỗi render riêng với lỗi SMTP |
| Email của khách A có thông tin khách B | Tái sử dụng context có thể thay đổi hoặc model không tách theo mail | Tạo context riêng cho mỗi email |
| Mail có link nhưng người dùng không có quyền xem | Chỉ kiểm tra URL khi render, thiếu kiểm tra quyền ở backend | Xác thực/ủy quyền khi mở link |

### Ví dụ lỗi 1: raw HTML từ ghi chú khách hàng

```html
<div th:utext="${customerNote}"></div>
```

Nếu ghi chú là dữ liệu người dùng, dùng `th:text` để hiển thị như văn bản. Chỉ sử dụng rich HTML đã được sanitize khi nghiệp vụ thật sự yêu cầu.

### Ví dụ lỗi 2: HTML bị gửi như text

```java
String html = templateEngine.process("mail/order-confirmation", context);
helper.setText(html, false);
```

`false` nói với `MimeMessageHelper` rằng body là text thuần. Nếu muốn HTML:

```java
helper.setText(html, true);
```

hoặc tốt hơn, khi có bản text:

```java
helper.setText(plain, html);
```

### Ví dụ lỗi 3: nhầm HTML escaping với bảo vệ URL

```html
<a th:href="${redirectUrl}">Xem tài khoản</a>
```

`th:href` không bảo đảm `redirectUrl` thuộc domain hợp lệ. Phải kiểm soát đích URL bằng quy tắc server-side, không nhận một chuỗi URL tùy ý.

### Ví dụ lỗi 4: ghép chuỗi dữ liệu thô vào template trước khi render

```java
String template = "<p>Xin chào " + customerName + "</p>";
String html = templateEngine.process(template, context);
```

Cách này đã trộn dữ liệu không tin cậy vào **template source** trước khi engine có cơ hội xử lý escaping thông thường. Hơn nữa, tùy cấu hình engine, `process(...)` có thể coi đối số là **tên template**, không phải nội dung HTML tùy ý. Hãy dùng một template được lưu ở vị trí rõ ràng và truyền `customerName` qua `Context`.

## 15. Thiết kế URL trong email có token

Các email xác nhận địa chỉ, đặt lại mật khẩu hoặc mời tham gia thường chứa đường dẫn có token. Đây là trường hợp cần phân biệt rất rõ **markup escaping** với **bảo mật nghiệp vụ**.

Ví dụ phần HTML:

```html
<a th:href="${verificationUrl}">Xác nhận địa chỉ email</a>
```

Một URL chứa token cần được hệ thống:

1. Tạo token bằng cơ chế phù hợp, giới hạn phạm vi và thời gian hiệu lực.
2. Xây URL từ domain tin cậy, mã hóa đúng thành phần query/path.
3. Chỉ gửi đến địa chỉ người dùng theo workflow xác nhận hợp lệ.
4. Không để token xuất hiện trong log ứng dụng hoặc metadata không cần thiết.
5. Xác minh token, hiệu lực và quyền khi người dùng truy cập endpoint.
6. Hủy hoặc giới hạn token theo ngữ nghĩa nghiệp vụ nếu đã sử dụng.

Template engine chỉ chịu trách nhiệm đặt URL vào HTML attribute đúng cú pháp. Nó **không tạo tính an toàn của token**. Nếu dữ liệu đầu vào chứa token hợp lệ nhưng bị chèn vào domain giả, escaping cũng không khắc phục được sai lầm này.

Tương tự, một đường dẫn đến đơn hàng phải được bảo vệ bằng kiểm tra quyền truy cập sau khi người dùng mở trang, thay vì phụ thuộc vào việc ID đơn hàng khó đoán.

## 16. Một quy trình phát triển template có thể bảo trì

Với nhiều loại email, có thể xây một cấu trúc tài nguyên:

```text
src/main/resources/
└── templates/
    └── mail/
        ├── order-confirmation.html
        ├── invoice-ready.html
        ├── password-reset.html
        └── shared/
            └── footer.html
```

Những nguyên tắc hữu ích:

- Dùng tên template có nghĩa theo sự kiện nghiệp vụ.
- Xác định **model contract** cho mỗi template: biến nào có mặt, kiểu gì, giá trị có thể rỗng hay không.
- Để logo, CSS dùng chung và footer trong những phần template do ứng dụng quản lý.
- Chọn rõ escape/raw output cho từng biến; mặc định xem giá trị từ người dùng là text.
- Tránh yêu cầu template thực hiện truy vấn database hoặc gọi service từ biểu thức.
- Có bản plain-text truyền tải cùng nội dung quan trọng.
- Xử lý lỗi render riêng với lỗi SMTP, không xem mọi lỗi trong pipeline đều có thể retry.

### Lỗi render khác lỗi gửi

```text
Mail request
    |
    v
Render template
    |
    +-- Template missing / expression error
    |      -> chưa tạo được nội dung gửi
    |
    v
Build MimeMessage
    |
    +-- Invalid address / MIME preparation error
    |      -> lỗi tạo thông điệp
    |
    v
SMTP submission
    |
    +-- Auth / quota / network / relay policy
           -> lỗi tương tác với server
```

Không nên retry SMTP nhiều lần khi file template chưa tồn tại hoặc lỗi biểu thức không thay đổi. Ngược lại, khi có lỗi mạng tạm thời, cần chiến lược retry có giới hạn và trạng thái nghiệp vụ để giảm nguy cơ gửi trùng. Việc render thành công **không bảo đảm** email được SMTP server chấp nhận hay giao tới inbox.

## 17. Các tình huống tự luyện

### Tình huống A: khách hàng nhập tên chứa thẻ HTML

Tên được lưu là:

```text
<em>Người mua</em>
```

Nếu hiển thị như dữ liệu bình thường, nên dùng:

```html
<span th:text="${customerName}">Tên khách hàng</span>
```

**Kết luận:** tag trong tên sẽ được thể hiện như văn bản, không được phép tạo thêm markup.

### Tình huống B: mô tả sản phẩm có ký tự `&`

Mô tả:

```text
Coffee & Tea
```

Không cần thay `&` thành `&amp;` trong service nếu template dùng `th:text`. Đưa chuỗi gốc vào context, để engine thực hiện escaping tại đầu ra.

### Tình huống C: người dùng được phép nhập mô tả giàu định dạng

Sản phẩm yêu cầu hỗ trợ một vài tag như `<strong>` và `<em>`. Nếu hiển thị bằng `th:text`, những tag sẽ trở thành chữ; nếu dùng `th:utext` với input thô, nội dung ngoài chính sách có thể đi vào email.

**Hướng giải quyết:** định nghĩa một chính sách HTML allowlist và dùng sanitizer được duy trì phù hợp, rồi render phần đã sanitize theo một đường rõ ràng. Nếu không cần định dạng, chỉ dùng escaped text.

### Tình huống D: link trong email dẫn ra ngoài miền công ty

Một trường `orderUrl` được lấy trực tiếp từ payload. Template dùng `th:href` nhưng URL vẫn dẫn tới một domain không được duyệt.

**Kết luận:** attribute escaping chỉ bảo vệ cấu trúc HTML; cần validate/buộc host từ backend trước khi render.

### Tình huống E: thông báo có HTML đẹp nhưng mail client chỉ đọc text

Email chỉ gọi:

```java
helper.setText(html, true);
```

**Hướng giải quyết:** thêm bản plain-text và gọi `helper.setText(plain, html)` với helper ở chế độ multipart. Nội dung hành động quan trọng, đặc biệt là URL, nên xuất hiện ở cả hai bản.

### Tình huống F: template render đúng nhưng khách hàng thấy mã HTML

Engine tạo chuỗi:

```html
<p>Đơn hàng đã xác nhận.</p>
```

Song code gọi `helper.setText(html, false)`. Mail client nhận `text/plain` nên hiển thị tag dưới dạng chữ.

**Hướng giải quyết:** khai báo đúng `text/html` bằng `setText(html, true)` hoặc dùng hai phiên bản. Đây là vấn đề **MIME content type**, không phải vấn đề escaping trong template.

### Tình huống G: nhiều email chạy đồng thời bị lẫn tên

Service tái sử dụng một `Context` và thay `customerName` trước mỗi lần gọi engine. Khi các luồng chạy song song, giá trị có thể bị lẫn nếu context bị chia sẻ không đồng bộ.

**Hướng giải quyết:** khởi tạo context/model theo từng lần render; không chia sẻ mutable data của người nhận giữa các yêu cầu.

## 18. Bảng ghi nhớ nhanh

| Mục tiêu | Công cụ hoặc quy tắc |
| --- | --- |
| Tạo HTML theo mẫu | Template engine như Thymeleaf |
| Hiển thị dữ liệu dưới dạng văn bản | `th:text` |
| Chèn raw HTML | Chỉ dùng cho markup được tin cậy/đã sanitize theo chính sách |
| Đặt link động | `th:href` **và** URL do backend kiểm soát |
| Chọn style theo trạng thái | Enum/boolean ánh xạ sang CSS cố định |
| Tách HTML khỏi nghiệp vụ | Model dữ liệu riêng, template riêng |
| Tạo MIME HTML | `MimeMessageHelper.setText(html, true)` |
| Có cả text và HTML | `MimeMessageHelper.setText(plain, html)` ở chế độ multipart |
| Thiết lập Subject, To, From | API chuyên dụng của `MimeMessageHelper` |
| Gửi email | `JavaMailSender.send(...)` |
| Hiển thị tiếng Việt đúng | Charset UTF-8 nhất quán từ nguồn tới MIME |
| Bảo vệ dữ liệu liên kết | Validation URL, token, quyền truy cập ở backend |
| Chống nhầm dữ liệu thành HTML | Escape theo ngữ cảnh và không nối HTML thô |

## 19. Kết luận

Template engine giúp viết email HTML có cấu trúc rõ ràng và dễ bảo trì. Nhưng giá trị lớn nhất của nó không chỉ là “thay biến trong chuỗi”: **nó giúp ứng dụng giữ ranh giới giữa dữ liệu và markup**, miễn là ta dùng đúng cơ chế escaped output và kiểm soát những ngữ cảnh đặc biệt như URL, thuộc tính và CSS.

Trong Spring Framework Mail, nên để **template engine render body**, **`MimeMessageHelper` tạo MIME và message headers**, còn **`JavaMailSender` gửi qua SMTP**. Dữ liệu người dùng cần đi qua `th:text` hoặc cơ chế escape tương ứng; raw HTML chỉ dùng khi có chính sách cho phép và sanitization thích hợp. Một URL được escape vẫn phải được kiểm tra đích và quyền truy cập. Khi các trách nhiệm được tách rõ, email HTML vừa linh hoạt trong trình bày vừa giảm rủi ro chèn markup, nhầm dữ liệu và làm lộ thông tin.
