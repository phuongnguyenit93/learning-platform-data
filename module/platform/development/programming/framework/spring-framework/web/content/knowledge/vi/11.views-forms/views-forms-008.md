# Giới hạn nội dung động, escape HTML và nguy cơ XSS khi kết xuất view trong Spring MVC

## 1. Mục tiêu và bối cảnh

Spring MVC thường đưa dữ liệu từ database, request parameter hoặc form vào `Model`, rồi chuyển model tới Thymeleaf/JSP để render HTML. Những dữ liệu như tên, nội dung bình luận, mô tả sản phẩm hoặc đường dẫn do người dùng nhập đều có thể chứa ký tự mang ý nghĩa đặc biệt với trình duyệt. **Nếu nội dung không đáng tin cậy bị kết xuất thành mã HTML hoặc JavaScript, trình duyệt có thể thực thi nó**: đó là nền tảng của lỗ hổng Cross-Site Scripting (XSS).

Sau bài này, bạn có thể:

1. Phân biệt **dữ liệu văn bản** với **HTML được phép render**, và giải thích vì sao dữ liệu trong `Model` không tự trở nên an toàn.
2. Sử dụng Thymeleaf `th:text`, `th:value`, `th:href`, biểu thức inline có escape và DOM `textContent` phù hợp; nhận diện rủi ro của `th:utext`, inline unescaped và `innerHTML`.
3. Áp dụng **output encoding theo ngữ cảnh** HTML text, HTML attribute, URL, JavaScript và CSS; hiểu khi nào encoding không đủ và phải kiểm soát cấu trúc/allowlist.
4. Giới hạn dữ liệu động (độ dài, định dạng, quyền hiển thị, danh sách URL cho phép), sanitize HTML giàu định dạng khi thực sự cần, và đặt CSP như lớp phòng vệ bổ sung.
5. Tạo một ví dụ **Spring Boot 3.x + Thymeleaf + Java 17+**, rồi kiểm thử rằng payload có dấu `<`, `>`, dấu nháy hoặc nội dung trông giống HTML vẫn được hiển thị dưới dạng text mà không biến thành thẻ/thuộc tính có thể thực thi.

**Phạm vi:** Spring Framework 6.x, Spring MVC trên Servlet stack và các trang HTML render phía server. Nhiều nguyên tắc cũng áp dụng cho trang frontend SPA; nhưng Spring MVC không tự bảo vệ những DOM update do JavaScript ở trình duyệt thực hiện.

## 2. XSS hình thành ở đâu trong luồng render view?

Một form nhận tên hiển thị hoặc lời bình:

~~~http
GET /pages/preview?message=Hello HTTP/1.1
Host: localhost:8080
~~~

Dữ liệu đến controller:

~~~java
@GetMapping("/preview")
public String preview(@RequestParam String message, Model model) {
    model.addAttribute("message", message);
    return "preview";
}
~~~

Đây là đoạn **minh họa trong một `@Controller`**, cần import annotation và khai báo class. `Model` chứa đúng giá trị mà client gửi; `model.addAttribute(...)` **không phải sanitizer**.

Sau đó view sử dụng attribute `message`. Nếu template cho trình duyệt hiểu dữ liệu ấy như **HTML source**, các thẻ và thuộc tính có thể làm thay đổi cấu trúc DOM và gây XSS. Ví dụ chuỗi kiểm thử vô hại để nhận biết khác biệt:

~~~text
<img src=x onerror=alert(1)>
~~~

Đoạn trên chỉ là **test payload**. Khi được escape và render làm text, trình duyệt hiển thị nguyên dòng ký tự. Khi được đưa trực tiếp vào HTML parser, nó tạo thẻ `img` có event handler, gây nguy cơ thực thi JavaScript.

Ba điểm cần kiểm soát:

- **Nguồn dữ liệu không đáng tin cậy:** request parameter, form, cookie, header, dữ liệu từ database do user tạo, nội dung bên thứ ba, Markdown/HTML từ CMS. Dữ liệu đã lưu trong database vẫn có thể gây **stored XSS** khi hiển thị lại.
- **Chặng đưa dữ liệu vào response:** Thymeleaf/JSP template, `ResponseEntity<String>` trả HTML tự ghép, JavaScript nhúng trong trang, attribute `href`, CSS, `iframe`, hoặc DOM update sau khi trang tải.
- **Ngữ cảnh parser đích:** HTML text, HTML attribute, JavaScript code/string, URL, CSS hoặc DOM API. **Mỗi ngữ cảnh cần quy tắc khác nhau**; một hàm “escape chung” không bảo vệ được mọi vị trí.

**Reflected XSS** xảy ra khi input từ request bị phản chiếu vào response nguy hiểm; **stored XSS** xảy ra khi nội dung đã lưu được render nguy hiểm; **DOM-based XSS** liên quan JavaScript phía client đưa dữ liệu vào các DOM sink có khả năng diễn giải như code/markup. Các dạng có thể kết hợp.

## 3. Escape khác sanitize và validate như thế nào?

| Thao tác | Giải quyết vấn đề | Ví dụ |
| --- | --- | --- |
| **Output encoding / escaping** | Chuyển ký tự đặc biệt thành biểu diễn an toàn cho **đúng ngữ cảnh output** | Trong HTML text, `<` thành `&lt;` |
| **Input validation** | Xác minh dữ liệu đúng contract/nghiệp vụ (độ dài, cấu trúc, tập giá trị) | Tên dài tối đa 200 ký tự |
| **HTML sanitization** | Loại bỏ/thay thế phần markup nguy hiểm nhưng giữ một số HTML hợp lệ | Chỉ cho phép `<b>`, `<em>`, link an toàn |
| **Authorization** | Xác nhận người xem có quyền nhận dữ liệu | Không đưa email riêng tư vào model công khai |
| **CSP / Trusted Types** | Hạn chế một số hướng thực thi script/DOM injection | `Content-Security-Policy` chặn inline scripts không được cho phép |

**Đầu ra thường phải được escape tại điểm render**, dù đầu vào đã qua validation. Validation không thể thay thế encoding: một tên sản phẩm hợp lệ có thể chứa ký tự `<`, dấu `&` hoặc dấu nháy. Ngược lại, HTML escaping không giới hạn độ dài, kiểm tra quyền hay biến một URL nguy hiểm thành URL đáng tin.

Một ví dụ HTML text được escape:

~~~html
<!-- Source trong response -->
<p>&lt;img src=x onerror=alert(1)&gt;</p>
~~~

Trình duyệt hiển thị đúng chuỗi ký tự `<img src=x onerror=alert(1)>`; nó **không tạo ra một `img` child** từ chuỗi đó. Browser đã giải mã entity thành text trong DOM, nhưng text node không được parse lại thành HTML.

Đừng escape khi ghi vào database rồi escape lại một lần nữa trong view nếu contract lưu trữ yêu cầu văn bản thô: có thể phát sinh `&amp;lt;` và hiển thị sai. Một hướng bền vững là **lưu canonical text**, validate theo nghiệp vụ, và encode **mỗi lần đưa ra một sink cụ thể**.

## 4. Thymeleaf: `th:text` an toàn cho HTML text, `th:utext` là lối thoát nguy hiểm

### 4.1. `th:text`: mặc định escape HTML

~~~html
<p id="comment" th:text="${comment}">Bình luận</p>
~~~

Nếu `comment = "<b>Xin chào</b>"`, Thymeleaf kết xuất:

~~~html
<p id="comment">&lt;b&gt;Xin chào&lt;/b&gt;</p>
~~~

Trình duyệt **hiển thị** ký tự `<b>Xin chào</b>` dưới dạng chữ, không tạo thẻ bôi đậm. Khi muốn hiển thị nội dung do user nhập chính xác như text, đây là lựa chọn phù hợp.

Trong Thymeleaf 3.1, biểu thức inline dùng **ngoặc kép** `[[...]]` tương ứng escaped text:

~~~html
<p>Nhận xét: [[${comment}]]</p>
~~~

### 4.2. `th:utext` và `[(...)]`: HTML không được escape

~~~html
<!-- KHÔNG dùng với comment do người dùng cung cấp trực tiếp -->
<p th:utext="${comment}">Bình luận</p>
<p>[(${comment})]</p>
~~~

`th:utext` là *unescaped text*. Nếu `comment` chứa thẻ HTML, thẻ có thể được parser của browser diễn giải. Biểu thức inline `[(...)]` cũng cho output không escape. Thymeleaf 3.1 có một số giới hạn đánh giá expression để bảo vệ template engine, nhưng **không phải sanitizer cho HTML output**.

Chỉ cân nhắc unescaped HTML khi nghiệp vụ thực sự yêu cầu HTML giàu định dạng và bạn đã xây pipeline sanitization với chính sách allowlist phù hợp. Không cho rằng “dữ liệu từ database” hay “chỉ admin nhập” thì tự động an toàn: tài khoản quản trị cũng có thể bị chiếm quyền hoặc nội dung được import từ nguồn khác.

### 4.3. HTML attribute là ngữ cảnh khác

~~~html
<input type="text" th:value="${comment}">
<span th:title="${comment}">Rê chuột để xem</span>
<div th:attr="data-comment=${comment}"></div>
~~~

Thymeleaf xử lý biểu thức gắn attribute, encode các ký tự thích hợp và giữ cấu trúc thuộc tính trong trường hợp thông thường. **Vẫn phải sử dụng thuộc tính cố định và đúng mục đích**. Nếu tự ghép HTML string, bỏ dấu quote quanh attribute, hoặc dùng dữ liệu người dùng làm tên thuộc tính, nguy cơ injection tăng mạnh.

Một giá trị chứa dấu nháy như `" autofocus onfocus="...` không được phép “thoát” ra khỏi attribute đã được framework encode đúng. Với HTML tự ghép, cần encoder chuyên dụng cho quoted HTML attribute và luôn quote giá trị.

**Không nhầm điều này với event handler attribute** như `onclick` hoặc `onerror`: giá trị của chúng là JavaScript. HTML attribute encoding thông thường **không làm code JavaScript trở thành dữ liệu an toàn** sau khi browser giải mã entity. Tránh ghép dữ liệu user vào `th:onclick` hoặc bất kỳ `on*` attribute nào.

## 5. Output encoding phải theo đúng ngữ cảnh

| Vị trí đưa dữ liệu vào | Cách làm phù hợp | Những điều phải tránh |
| --- | --- | --- |
| Text nằm giữa thẻ HTML | Thymeleaf `th:text` / `[[...]]` | `th:utext`, `[(...)]` với input thô |
| Quoted HTML text attribute | `th:value`, `th:title`, `th:attr` với tên attribute cố định | Ghép tag string, attribute không quote, tên attribute động |
| Query parameter của `href` | Thymeleaf URL link expression với parameter; encode URL component và HTML attribute đúng ngữ cảnh | Nối chuỗi `?q=` trực tiếp rồi render raw |
| Toàn URL do user nhập | Parse/validate scheme và đích, allowlist trước khi render | Tin URL chỉ vì được HTML-escaped |
| JavaScript string trong HTML | Inlining JavaScript có serializer theo đúng ngữ cảnh hoặc truyền qua data attribute và đọc bằng DOM | Chèn trực tiếp template expression vào JS code/event handler |
| CSS property value | Giá trị hữu hạn được validate/allowlist, tên thuộc tính CSS cố định | Cho input làm selector, property name hay raw `style` |
| DOM text update | `textContent` | `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write` với input thô |
| HTML do user biên soạn | HTML sanitizer theo allowlist nghiêm ngặt rồi render theo contract | HTML parser/render raw trực tiếp từ user |
  
**Không tồn tại một “hàm escape HTML” dùng được cho tất cả JavaScript, CSS, URL và HTML attribute**. Browser đi qua nhiều parser liên tiếp. Một chuỗi đã HTML-encoded vẫn có thể nguy hiểm nếu sau đó được diễn giải như JavaScript hoặc URL executable scheme.

### 5.1. URL: encode parameter và kiểm soát scheme

Với một route nội bộ cố định, Thymeleaf hỗ trợ:

~~~html
<a th:href="@{/pages/search(q=${comment})}">Tìm kiếm</a>
~~~

`@{...}` là link expression; tham số `q` được xử lý như một URL parameter và giá trị kết quả được đặt vào HTML attribute. Dấu `&`, dấu cách hay dấu hỏi trong comment không nên được nối thô làm thay đổi cấu trúc query.

**Nhưng** nếu input là toàn bộ URL, việc encode ký tự HTML thôi **không ngăn** một giá trị bắt đầu bằng `javascript:` hoặc một URL ngoài miền không được phép. Khi nghiệp vụ cho phép link do người dùng nhập, bạn cần **parse URI, kiểm tra scheme `http`/`https`, host/đích theo allowlist phù hợp**, rồi render bằng cơ chế attribute an toàn. Tránh kiểm tra URL bằng phép `startsWith("https")` đơn giản, vì còn cần xác thực cú pháp và các biến thể bất thường.

Nếu frontend tạo URL bằng JavaScript, `encodeURIComponent(value)` chỉ dùng để encode **một thành phần** như query parameter; nó không kiểm tra an toàn của cả URL. Dùng `new URL(...)` và chính sách scheme/host cho URL động.

### 5.2. JavaScript embedded trong HTML

Không dùng:

~~~html
<!-- Không an toàn: giá trị động tự ghép vào JavaScript source -->
<script>
  const message = '/* USER_INPUT_GHEP_THO_VAO_DAY */';
</script>
~~~

Một input chứa dấu nháy, backslash hay đoạn trông giống đóng script có thể phá ngữ cảnh nếu thao tác escape không phù hợp. Cách ưu tiên là **không tạo inline script từ dữ liệu user**: đặt text vào attribute do template escape, rồi dùng một JavaScript file tĩnh đọc qua `dataset` và đưa ra UI bằng `textContent` (ví dụ thực hành ở phần 7).

Nếu buộc phải dùng script do Thymeleaf render, chế độ `th:inline="javascript"` và **escaped inlining** `[[...]]` cho phép trình tuần tự hóa Thymeleaf tạo JavaScript literal, bao gồm dấu quote và escaping. Dạng minh họa:

~~~html
<script th:inline="javascript">
  const message = /*[[${comment}]]*/ "default";
</script>
~~~

**Không chuyển sang** `[(...)]` để bỏ escape. Cũng không tạo raw JavaScript statement, event-handler code hoặc tên biến từ untrusted input. Tính an toàn của inline script phải xét cả ngữ cảnh **HTML script element** và **JavaScript string**; kiểm thử các chuỗi đặc biệt như dấu quote, dấu `<` và chuỗi kết thúc script. Thiết kế dùng external JS + escaped DOM attribute thường dễ kiểm soát CSP hơn.

### 5.3. CSS và các ngữ cảnh nguy hiểm

Không đặt input tự do vào CSS selector, tên property, toàn bộ `style` hoặc cú pháp `url(...)`. Nếu cho user chọn màu nền, hãy giới hạn một tập giá trị:

~~~java
Set<String> allowedColors = Set.of("red", "blue", "green");
String chosen = allowedColors.contains(color) ? color : "blue";
~~~

Đoạn trên chỉ minh họa nằm trong method Java có `color` và import `Set`. Cách tốt hơn là ánh xạ giá trị nghiệp vụ sang **CSS class cố định** ở server hoặc frontend, thay vì tự ghép style text. Dữ liệu dynamic trong HTML comment, tên thẻ, tên attribute, raw JavaScript hay raw style block cũng là các **ngữ cảnh nguy hiểm**; không cố giải quyết bằng cách escape một vài ký tự.

## 6. Giới hạn nội dung động ở nhiều lớp

“Giới hạn” không chỉ là cắt chuỗi. Một view an toàn nên đưa ra **đúng lượng dữ liệu cần thiết và đúng định dạng được phép**:

1. **Giới hạn độ dài:** ví dụ bình luận preview tối đa 200 ký tự hoặc nội dung bài viết tối đa theo nghiệp vụ. Giới hạn giúp kiểm soát UX, chi phí render, kích thước response và các hình thức lạm dụng tài nguyên; nó **không tự loại bỏ XSS**.
2. **Giới hạn field và data exposure:** controller chỉ đưa những thuộc tính cần hiển thị vào `Model`. Không đưa password hash, access token, internal error details, nguyên entity có dữ liệu nhạy cảm vào template.
3. **Validation theo schema:** kiểu dữ liệu, phạm vi, enum, ID, quyền sở hữu, độ dài; không loại bỏ tùy tiện mọi ký tự `<` hoặc `&` nếu chúng hợp lệ về nghiệp vụ.
4. **Giới hạn loại markup:** nếu cho phép rich text, chỉ hỗ trợ một subset HTML cần thiết; không dùng regex thay thế sanitizer parser-based.
5. **Giới hạn URL/media:** kiểm soát scheme, host, loại MIME/file, đường dẫn tài nguyên và quyền xem; một link được escape vẫn có thể điều hướng người dùng đến trang lừa đảo.
6. **Giới hạn script và resource của trình duyệt:** đặt CSP, tránh inline script, quản lý third-party script có chủ đích. CSP bổ sung cho template escaping, không thay thế nó.
7. **Giới hạn lúc truy cập:** authorization kiểm tra người xem có được lấy dữ liệu hay không trước khi đưa dữ liệu vào model.

Với plain text hiển thị từ database, việc lưu và truyền dưới dạng string thông thường rồi render bằng `th:text` gần như luôn hợp lý hơn cơ chế tự build HTML string. Với nội dung nhiều dòng, có thể dùng CSS `white-space: pre-wrap` cố định cho vùng text; không cần chuyển `\n` thành `<br>` bằng `th:utext`.

## 7. Ví dụ Spring Boot 3.x chạy được: render text an toàn

Tạo project bằng Spring Initializr: **Java 17+**, **Spring Boot 3.x**, **Maven**, dependencies **Spring Web**, **Thymeleaf** và **Spring Boot Starter Test**. Với Maven, các starter tương ứng là `spring-boot-starter-web`, `spring-boot-starter-thymeleaf`, `spring-boot-starter-test`. Package là `com.example.demo`.

Cấu trúc file:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/SafeViewController.java
src/main/resources/templates/preview.html
src/main/resources/static/js/preview.js
src/test/java/com/example/demo/SafeViewControllerTest.java
~~~

### 7.1. File khởi động

**`src/main/java/com/example/demo/DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 7.2. Controller: giới hạn độ dài và chỉ đưa text vào model

**`src/main/java/com/example/demo/SafeViewController.java`**

~~~java
package com.example.demo;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.server.ResponseStatusException;

@Controller
@RequestMapping("/pages")
public class SafeViewController {

    @GetMapping("/preview")
    public String preview(
            @RequestParam(defaultValue = "Xin chào") String message,
            Model model) {

        return render(message, model);
    }

    @GetMapping("/search")
    public String search(@RequestParam("q") String q, Model model) {
        return render(q, model);
    }

    private String render(String message, Model model) {
        if (message.length() > 200) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Text is too long");
        }

        model.addAttribute("message", message);
        return "preview";
    }
}
~~~

**Giải thích:**

- Cả hai endpoint dùng **`@Controller`** và trả logical view `"preview"` để Thymeleaf tạo HTML.
- Tham số `message` hoặc `q` có thể mang văn bản nhập từ trình duyệt. `render` từ chối input dài hơn 200 UTF-16 code units theo quy tắc của `String.length()`; giới hạn này **chỉ là ví dụ UX/tài nguyên**, không phải điều kiện an toàn XSS.
- Giá trị lưu trong model **vẫn là text gốc**; Thymeleaf thực hiện encoding đúng lúc đưa ra HTML.
- App không chứa database hoặc hệ thống phân quyền; production cần kiểm tra quyền và data exposure nếu hiển thị dữ liệu riêng tư.

### 7.3. Template: text, attribute, URL và data attribute an toàn

**`src/main/resources/templates/preview.html`**

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Xem trước nội dung</title>
  <script th:src="@{/js/preview.js}" defer></script>
</head>
<body>
  <h1>Xem trước</h1>

  <!-- HTML text context: Thymeleaf escape dữ liệu. -->
  <p id="safe-text" th:text="${message}">Văn bản xem trước</p>

  <!-- HTML attribute context: giữ tên attribute cố định. -->
  <label for="input-preview">Dữ liệu</label>
  <input id="input-preview" type="text" th:value="${message}">

  <!-- URL parameter context, đích /pages/search cố định. -->
  <a id="search-link" th:href="@{/pages/search(q=${message})}">
    Xem kết quả tìm kiếm
  </a>

  <!-- Truyền dữ liệu đã encode qua attribute, không chèn JS source. -->
  <div id="client-data" th:attr="data-message=${message}"></div>
  <p id="client-text"></p>
</body>
</html>
~~~

**Vì sao template này an toàn đối với dữ liệu đang xử lý?**

- `th:text` render dữ liệu thành HTML text đã escape.
- `th:value` và `th:attr` đưa dữ liệu vào attribute **được định tên cố định**, có quoting/encoding theo template engine.
- `th:href="@{/pages/search(q=${message})}"` dùng một đường dẫn nội bộ đã quyết định ở server; dữ liệu chỉ nằm ở query parameter.
- Không có `th:utext`, không có inline JavaScript ghép input, không có `href` động nguyên URL, và không có HTML tự nối từ user input.

### 7.4. JavaScript external: dùng `textContent`

**`src/main/resources/static/js/preview.js`**

~~~javascript
"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const source = document.getElementById("client-data");
  const output = document.getElementById("client-text");

  if (!source || !output) {
    return;
  }

  const text = source.dataset.message ?? "";
  output.textContent = text;
});
~~~

`dataset.message` lấy giá trị đã được browser phân tích từ HTML attribute. `textContent` tạo **text node**, không parse HTML trong chuỗi dữ liệu.

**Không thay bằng:**

~~~javascript
// KHÔNG AN TOÀN cho dữ liệu không đáng tin cậy:
output.innerHTML = text;
~~~

`innerHTML` yêu cầu browser parse text như HTML source; nó có thể tạo element/attribute nguy hiểm. Các API như `outerHTML`, `insertAdjacentHTML` và `document.write` cũng cần được kiểm soát nghiêm ngặt. Nếu muốn tạo DOM node có cấu trúc, dùng `document.createElement`, thiết lập attribute cố định và gán text qua `textContent`.

### 7.5. Chạy và quan sát payload

Ở thư mục dự án Maven:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows dùng `mvnw.cmd spring-boot:run`. Nếu không có Maven Wrapper, dùng `mvn spring-boot:run` khi Maven đã cài.

Gửi test string có thẻ HTML bằng `curl`:

~~~bash
curl -G -i "http://localhost:8080/pages/preview"   --data-urlencode 'message=<img src=x onerror=alert(1)>'
~~~

Cú pháp xuống dòng trên dùng dấu `\` trong Linux/macOS/Git Bash. Trên Windows PowerShell có thể dùng `curl.exe` trên một dòng và xử lý quoting theo PowerShell.

**Kết quả cần quan sát:**

- Status 200, `Content-Type` là HTML.
- HTML response ở vùng `id="safe-text"` sẽ có các entity escape tương ứng, chẳng hạn:

~~~html
<p id="safe-text">&lt;img src=x onerror=alert(1)&gt;</p>
~~~

- Trong trình duyệt, đoạn đó hiển thị **như chữ**, không xuất hiện phần tử `img` do user input tạo ra.
- JavaScript external cũng gán chuỗi vào `#client-text` bằng `textContent`, nên không tạo HTML element mới.
- Link `/pages/search?q=...` có tham số được encode phù hợp; đích liên kết vẫn là đường dẫn nội bộ cố định.

Giới hạn của ví dụ: `String.length()` đếm UTF-16 code units chứ không phải số grapheme nhìn thấy của tiếng Việt/emoji. Với sản phẩm cần giới hạn theo ký tự người dùng nhìn thấy hoặc byte trên wire, phải định nghĩa quy tắc và dùng công cụ đếm phù hợp.

## 8. Kiểm thử HTML đã render bằng MockMvc

Chỉ test `model().attribute("message", input)` **chưa đủ** để khẳng định HTML được escape; controller có thể bind đúng nhưng template lại dùng `th:utext`. Bài test dưới đây chạy **cả ứng dụng + template Thymeleaf** bằng `@SpringBootTest` và `@AutoConfigureMockMvc`.

**`src/test/java/com/example/demo/SafeViewControllerTest.java`**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeViewControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void untrustedMarkupIsRenderedAsText() throws Exception {
        String payload = "<img src=x onerror=alert(1)>";

        String html = mockMvc.perform(get("/pages/preview")
                        .param("message", payload))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        assertTrue(html.contains(
                "&lt;img src=x onerror=alert(1)&gt;"));
        assertFalse(html.contains(
                "<img src=x onerror=alert(1)>"));
    }

    @Test
    void quotesStayInsideInputAttribute() throws Exception {
        String payload = "\" autofocus onfocus=\"alert(1)";

        String html = mockMvc.perform(get("/pages/preview")
                        .param("message", payload))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        // Dấu nháy bên trong dữ liệu không trở thành attribute mới.
        assertFalse(html.contains(
                "value=\"\" autofocus onfocus="));
        assertTrue(html.contains("id=\"input-preview\""));
    }

    @Test
    void rejectsExcessiveInputLength() throws Exception {
        mockMvc.perform(get("/pages/preview")
                        .param("message", "a".repeat(201)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void searchUsesSameSafeView() throws Exception {
        mockMvc.perform(get("/pages/search")
                        .param("q", "<b>Hello</b>"))
                .andExpect(status().isOk());
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

Các assert trên kiểm chứng HTML response bằng việc **render template thật** trong MockMvc integration. Test đầu yêu cầu `<img...>` bị escape trong HTML, test thứ hai kiểm tra dữ liệu có dấu nháy không trở thành attribute mới, test cuối xác minh giới hạn độ dài.

**Giới hạn kiểm thử:** MockMvc không chạy JavaScript của browser. Để xác nhận DOM-based XSS và việc không có script thực thi, bổ sung browser integration/security tests với dữ liệu đặc biệt và môi trường cô lập. Có thể dùng DOM assertions dựa trên parser HTML (thay vì so khớp substring) để chứng minh không có element hoặc event-handler do input user tạo ra. Test nguồn là chỉ báo quan trọng, nhưng bảo vệ XSS cần xem toàn bộ sink và đường dữ liệu.

## 9. Rich text thật sự cần HTML: sanitize bằng allowlist

Một công cụ nhập nội dung WYSIWYG có thể cần cho phép **in đậm, in nghiêng, danh sách và link**. Nếu áp dụng `th:text`, tag sẽ hiển thị dưới dạng chữ, không giữ format. Trong trường hợp này, giải pháp là **HTML sanitization** trước khi render unescaped, bằng một thư viện được duy trì và chính sách cho phép thật rõ.

Ví dụ **minh họa độc lập** với thư viện [OWASP Java HTML Sanitizer](https://github.com/OWASP/java-html-sanitizer) (phải tự thêm dependency tương ứng với phiên bản dự án):

~~~java
import org.owasp.html.PolicyFactory;
import org.owasp.html.Sanitizers;

public class RichTextSanitizer {
    private static final PolicyFactory POLICY =
            Sanitizers.FORMATTING.and(Sanitizers.LINKS);

    public static String sanitize(String input) {
        return POLICY.sanitize(input == null ? "" : input);
    }
}
~~~

Chính sách có sẵn ở đây chỉ để giới thiệu API: `FORMATTING` và `LINKS` cho phép tập markup nhất định, đồng thời thư viện lọc theo quy tắc của nó. Trong production, **thiết kế allowlist cụ thể** cho tag/attribute/protocol cần dùng, thường cấm script, event-handler attributes và URL scheme không được phép. Nên kiểm thử cả link, SVG, MathML, tag lồng nhau và những trường hợp parse phức tạp; cập nhật bản vá thư viện đều đặn.

Sau khi sanitize:

~~~java
String safeHtml = RichTextSanitizer.sanitize(rawHtml);
model.addAttribute("safeHtml", safeHtml);
~~~

Chỉ khi `safeHtml` đã qua chính sách đáng tin, template có thể chủ động render:

~~~html
<div th:utext="${safeHtml}"></div>
~~~

**Quan trọng:** `th:utext` ở đây vẫn là một sink rủi ro; nó chỉ phù hợp khi giá trị vào đã được sanitize đúng yêu cầu. Không để code path khác đưa `rawHtml` trực tiếp vào cùng attribute. Không nối thêm HTML thô không đáng tin vào **sau** sanitization. Không coi sanitize HTML là đủ cho dữ liệu sau đó đưa vào JavaScript/CSS/URL; mỗi output context vẫn có quy tắc riêng.

Đối với phần lớn trang hiển thị tên sản phẩm, địa chỉ, bình luận văn bản, trạng thái, thông báo, **không cần `th:utext`**. Giữ dữ liệu như text và render bằng `th:text` là an toàn và dễ bảo trì hơn.

## 10. JSP, Spring `HtmlUtils` và những đường render khác

Nếu dự án dùng JSP/JSTL, một cách render text có escape là:

~~~jsp
<%@ taglib prefix="c" uri="jakarta.tags.core" %>
<p><c:out value="${comment}" /></p>
~~~

Ví dụ này dành cho môi trường Jakarta Tags 3.x/JSP tương thích Spring Boot 3 và có dependency/taglib được cấu hình. `c:out` với mặc định escape XML giúp hiển thị dữ liệu như text trong nhiều ngữ cảnh HTML text đơn giản. Không sử dụng output text/XML escaping này để tự xây JavaScript source, CSS hoặc URL executable.

Spring Framework cũng có `org.springframework.web.util.HtmlUtils.htmlEscape(String)`, ví dụ trong Java:

~~~java
String escaped = HtmlUtils.htmlEscape("<b>Hello</b>");
System.out.println(escaped);
~~~

Khi có import `HtmlUtils` và chạy trong project có Spring Web, stdout về mặt ý nghĩa sẽ là:

~~~text
&lt;b&gt;Hello&lt;/b&gt;
~~~

Đây là **HTML escaping cho văn bản**, không thay thế JavaScript encoding, URL validation hay sanitizer. Thông thường bạn không cần gọi `HtmlUtils.htmlEscape` trước Thymeleaf `th:text` vì có thể gây **double-encoding**.

Nếu tự trả HTML từ REST controller:

~~~java
return ResponseEntity.ok()
        .contentType(MediaType.TEXT_HTML)
        .body("<p>" + untrusted + "</p>");
~~~

Đây là **mẫu phản diện**: concatenation có thể đưa `untrusted` trực tiếp vào HTML source. Chọn Thymeleaf, hoặc dùng API encoder đúng ngữ cảnh trước khi build HTML thật sự. Không gọi escaping thủ công tại ngẫu nhiên một điểm rồi tái sử dụng encoded string ở các ngữ cảnh khác.

## 11. CSP, cookie flags và Trusted Types

Output encoding và HTML sanitization xử lý nguyên nhân trực tiếp. Các cơ chế khác bổ sung lớp kiểm soát:

### Content Security Policy (CSP)

Ví dụ **ý tưởng chính sách**, cần kiểm thử với các resource thực tế của ứng dụng:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Chính sách này giới hạn script tới origin hiện tại, không cho object/plugin, kiểm soát base URI và embedding. Với ứng dụng có inline script, CDN, iframe cần thiết hoặc chính sách tương thích browser khác, phải chỉnh policy, sử dụng nonce/hash khi cần và triển khai dần bằng report-only mode.

**CSP không phải “thuốc chữa XSS”**: cấu hình quá rộng như `unsafe-inline` có thể làm suy yếu lợi ích; script từ origin được cho phép hoặc logic DOM sai vẫn có thể nguy hiểm. Kiểm thử template escaping trước; CSP là defense in depth.

### Trusted Types

Một số browser dựa trên Chromium hỗ trợ **Trusted Types** kết hợp CSP `require-trusted-types-for 'script'`, giúp kiểm soát việc đưa plain string vào những DOM sink nguy hiểm như `innerHTML`. Nếu triển khai, cần chuẩn bị policy được kiểm duyệt và kế hoạch tương thích với thư viện frontend. Trusted Types không thay quyền kiểm tra input hoặc output encoding.

### Cookie flags

`HttpOnly`, `Secure`, `SameSite` là các flag cookie có ích cho quản lý session và giảm hậu quả một số tấn công. Chúng **không ngăn việc mã JavaScript độc hại thực thi trên trang** nếu XSS đã xảy ra. Đừng cho rằng cookie HttpOnly làm HTML render không cần escape.

## 12. Cách kiểm thử XSS một cách có hệ thống

Tạo ma trận **nguồn → sink** cho các dữ liệu động thực sự xuất hiện:

| Nguồn | Sink | Kiểm tra quan trọng |
| --- | --- | --- |
| Query parameter `message` | Thymeleaf `th:text` | Chuỗi chứa tag không tạo element mới |
| Form field `name` | `input th:value` | Dấu nháy không thoát attribute |
| Text tìm kiếm | `th:href` với query param | Đường dẫn giữ nguyên, tham số được encode |
| Dữ liệu từ DB | Comment/list trong template | Stored markup hiển thị an toàn |
| Dữ liệu trong `data-*` | DOM `textContent` | Không dùng `innerHTML` sau khi đọc |
| Rich text WYSIWYG | Vùng `th:utext` có kiểm soát | Sanitizer chỉ giữ subset HTML đã định nghĩa |
| URL do user cung cấp | `href` động | Scheme, host, redirect target thuộc allowlist |
| Dữ liệu cần gửi vào script | JS serializer hoặc external JS | Quote, slash, closing script và ngữ cảnh được xử lý |

Với quy trình QA cho ứng dụng, kết hợp:

1. **Unit tests** cho validator, URL allowlist, rich-text sanitizer.
2. **MockMvc / integration tests** render Thymeleaf thật với dấu `<`, `>`, `&`, quote và chuỗi giống markup; xác nhận DOM hoặc output encoding.
3. **Browser tests** cho DOM sink, link điều hướng và CSP trong trình duyệt thật.
4. **Code review** tập trung vào `th:utext`, `[(...)]`, `innerHTML`, `outerHTML`, `document.write`, raw HTML concatenation, dynamic `href`, event-handler attribute và template injection.
5. **Dependency updates** đối với template engine, sanitizer và frontend libraries, đặc biệt khi xử lý rich text.

Không nên chỉ tìm một payload cố định rồi tuyên bố hết XSS. Mỗi đường dữ liệu mới, đặc biệt các tính năng user-generated content, cần được đối chiếu ngữ cảnh output của nó.

## 13. Những lỗi thường gặp

### Lỗi 1. Nghĩ rằng `Model` sẽ tự loại bỏ HTML

`model.addAttribute("comment", untrusted)` chỉ lưu thuộc tính vào model. **Thymeleaf `th:text`** mới encode giá trị cho HTML text ở lúc render. Nếu template dùng `th:utext`, kết quả khác hoàn toàn.

### Lỗi 2. Dùng `th:utext` để giữ xuống dòng

Nếu mục tiêu chỉ là giữ newline, dùng text escaping và CSS:

~~~html
<p class="comment" th:text="${comment}">Bình luận</p>
<style>
  .comment { white-space: pre-wrap; }
</style>
~~~

Không cần đổi text thành `<br>` bằng HTML string. CSS này cố định, không lấy từ user.

### Lỗi 3. HTML-escape rồi đưa sang JavaScript string

HTML entity encoding không đảm bảo an toàn của JavaScript context. Dùng serializer được thiết kế cho JS literal và ngữ cảnh HTML script, hoặc external script đọc dữ liệu từ DOM rồi dùng `textContent`.

### Lỗi 4. Escape `href` là đủ

Một URL sai scheme hoặc trỏ đến site lừa đảo có thể vẫn nguy hiểm khi attribute được HTML-escaped hợp lệ. **Validate URL theo scheme/host**, chỉ cho phép những đích nghiệp vụ yêu cầu.

### Lỗi 5. Sanitize HTML bằng regex

HTML có nested markup, attribute encoding, namespace, URL scheme và nhiều cú pháp parser phức tạp. Regex thường không mô phỏng chính xác browser parser. Dùng sanitizer được duy trì với allowlist và bộ test dành cho rich text.

### Lỗi 6. Gọi `innerHTML` cho text từ response API

Ngay cả khi response API là JSON (media type `application/json`) và dữ liệu lấy từ server, chuỗi vẫn có thể chứa HTML nguy hiểm. **`textContent`** hoặc DOM APIs có kiểm soát giúp render như dữ liệu. JSON không tự sanitize mọi sink ở trình duyệt.

### Lỗi 7. Encode sẵn rồi encode lại

Lưu `&lt;b&gt;` vào DB rồi `th:text` tiếp có thể hiển thị `&lt;b&gt;` dưới dạng chữ do double encoding. Cần phân biệt raw data, sanitized HTML và context-specific encoded output trong hợp đồng dữ liệu.

### Lỗi 8. Cắt ngắn chuỗi rồi tưởng chống XSS

Giới hạn 200 ký tự giúp kiểm soát UX/tài nguyên, nhưng nhiều payload nguy hiểm rất ngắn. Validation về độ dài **bổ sung** cho encoding theo output context; nó không thay thế biện pháp chống XSS.

### Lỗi 9. Dựa hoàn toàn vào CSP hoặc WAF

CSP là defense in depth; WAF có thể bỏ sót DOM XSS hoặc payload mới. Kiểm soát output encoding/sanitization, nguồn dữ liệu và DOM sink vẫn là chính.

### Lỗi 10. Chỉ kiểm tra model, bỏ qua template

MockMvc `model().attribute("comment", payload)` chỉ chứng minh controller gửi dữ liệu đúng. Muốn kiểm tra XSS ở server-rendered view cần **render template** và kiểm tra response/DOM output. Đây là lý do ví dụ sử dụng `@SpringBootTest` + `@AutoConfigureMockMvc`.

## 14. Câu hỏi ôn tập

**1. Vì sao `th:text` thường phù hợp hơn `th:utext` cho bình luận người dùng?**

Vì `th:text` encode HTML và hiển thị ký tự dữ liệu như text, còn `th:utext` cho phép HTML parser diễn giải markup. Nếu cần rich text, phải sanitize bằng allowlist đáng tin trước.

**2. Nếu một input chỉ chứa 20 ký tự thì chắc chắn không gây XSS?**

Không. Giới hạn độ dài là quy tắc tài nguyên/UX; XSS phụ thuộc vào việc dữ liệu được giải thích như code/markup ở ngữ cảnh output hay không.

**3. Dùng Thymeleaf link expression `@{/search(q=${query})}` giải quyết được mọi nguy cơ URL?**

Không. Nó giúp xây URL parameter trong đường dẫn cố định. Nếu cả `href` là URL do user điều khiển, phải kiểm tra scheme/host/chính sách redirect.

**4. Vì sao `output.textContent = value` phù hợp khi chỉ hiển thị text?**

Vì nó tạo hoặc thay **text content** của DOM node, không yêu cầu parser đọc chuỗi như HTML. `innerHTML` thì có.

**5. Khi nào cần sanitizer?**

Khi sản phẩm thật sự cho phép người dùng cung cấp một subset HTML được render, ví dụ editor có format. Sanitizer parser-based phải lọc theo chính sách allowlist và được bảo trì; plain text thông thường nên escape tại view.

**6. `HttpOnly` cookie có loại bỏ XSS không?**

Không. Nó hạn chế JavaScript đọc cookie được đánh dấu HttpOnly, nhưng không làm JS injection bất khả thi và không bảo đảm thao tác trang không bị chiếm quyền.

## 15. Checklist trước khi đưa giao diện lên production

1. Xác định mọi trường động từ request/database/third-party và **vị trí cuối** chúng được render.
2. Với HTML text dùng `th:text`/`[[...]]`; với attribute thường dùng Thymeleaf attribute processors và quote; không ghép HTML raw từ input.
3. Tránh event-handler attributes, `th:utext`, `[(...)]` và các DOM HTML sinks cho dữ liệu không đáng tin.
4. Với URL, xác thực scheme/host/đích trước, sau đó encode tham số và attribute theo ngữ cảnh.
5. Với JavaScript, dùng external script + escaped DOM data và `textContent` khi phù hợp; nếu cần inline, dùng serializer đúng và test HTML script context.
6. Với rich text, dùng HTML sanitizer theo allowlist, có test, kiểm soát nơi dữ liệu sanitized được đưa vào; cập nhật thư viện.
7. Giới hạn input và dữ liệu đưa vào model theo nghiệp vụ, nhưng **vẫn escape output** và kiểm tra quyền truy cập.
8. Bật CSP phù hợp, xem xét Trusted Types nếu có frontend DOM phức tạp; coi chúng là biện pháp bổ sung.
9. Test HTML template thực tế, browser DOM, những chuỗi đặc biệt và các trường hợp sai quyền; không chỉ test controller/model.

## Tài liệu chính thức và tham khảo bảo mật

- [Thymeleaf 3.1 — Using Thymeleaf: escaped/unescaped text, attributes, JavaScript inlining](https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html)
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [OWASP — DOM Based XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html)
- [OWASP — HTML Sanitization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML_Sanitization_Cheat_Sheet.html)
- [Spring Framework 6.2 — View Technologies](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-view.html)
- [Spring Framework Javadoc — HtmlUtils](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/util/HtmlUtils.html)
- [OWASP Java HTML Sanitizer](https://github.com/OWASP/java-html-sanitizer)
