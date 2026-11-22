# Spring MVC — RedirectAttributes, flash attributes và vòng đời dữ liệu chuyển hướng

## 1. Mục tiêu

Sau khi người dùng gửi form POST và server lưu dữ liệu thành công, trang kết quả thường được mở qua một URL GET. Spring MVC hỗ trợ cách làm này bằng **Post/Redirect/Get (PRG)**, `RedirectAttributes` và **flash attributes**.

Bạn sẽ học cách:

- Phân biệt `addAttribute(...)` (giá trị trong URL) và `addFlashAttribute(...)` (dữ liệu tạm dành cho request đích).
- Hiểu quy trình HTTP POST → 302/303 redirect → GET và giới hạn của PRG.
- Theo dõi `FlashMap` đầu ra, việc lưu tạm (mặc định thường qua HTTP session), khớp URL đích, `FlashMap` đầu vào và hành vi tiêu thụ một lần.
- Xử lý form validation, thông báo thành công và redirect tới trang chi tiết với Thymeleaf.
- Đánh giá các tình huống flash mất sớm, session hết hạn, nhiều tab cùng lúc, API/AJAX và dữ liệu nhạy cảm.
- Chạy dự án Spring Boot 3.5, Java 17 và kiểm thử redirect/flash bằng MockMvc.

Bài viết tập trung **Spring MVC trên Servlet stack**. Không tự áp dụng cơ chế session FlashMap của MVC sang Spring WebFlux.

## 2. Post/Redirect/Get giải quyết vấn đề gì?

Nếu server trả HTML trực tiếp cho POST:

~~~text
Browser                         Server
 POST /messages --------------->
                 lưu dữ liệu
 <---------------- HTTP 200 HTML
 Refresh: trình duyệt có thể hỏi "gửi lại form" và POST lần nữa
~~~

Một lần refresh có thể tạo bản ghi trùng. Cách thiết kế PRG:

~~~text
Browser                         Spring MVC
 POST /messages --------------> Validate, save: id=42
 <-------------- HTTP 302 Location: /messages/42
 GET /messages/42 ------------> Lấy dữ liệu theo id
 <-------------- HTTP 200 HTML
 Refresh trang kết quả --------> GET /messages/42
~~~

Ví dụ handler minh họa:

~~~java
@PostMapping("/messages")
public String create(RedirectAttributes redirectAttributes) {
    long id = 42; // ID thực tế lấy từ service sau khi lưu thành công.
    redirectAttributes.addAttribute("id", id);
    redirectAttributes.addFlashAttribute("notice", "Tạo thành công");
    return "redirect:/messages/{id}";
}
~~~

`redirect:` là prefix của một **view name** dành cho redirect. Spring MVC tạo HTTP redirect với header `Location`. Sau khi browser thực hiện GET đích, người dùng refresh sẽ lặp GET, không tự động lặp POST cũ.

**Giới hạn:** PRG giảm nguy cơ lặp POST do refresh nhưng **không bảo đảm idempotency** khi người dùng double-click, client retry request, mạng timeout sau khi server đã commit hoặc có hai POST đồng thời. Với đơn hàng, thanh toán hoặc thao tác ghi quan trọng, cần thêm idempotency key/unique constraints/transaction thích hợp.

### 2.1. Chọn 302, 303, 307 hay 308?

| Status | Ý nghĩa cần chú ý | Vai trò khi PRG |
| --- | --- | --- |
| `302 Found` | Redirect tạm, lịch sử client thường chuyển POST thành GET | `redirect:` thông thường trả 302 |
| `303 See Other` | Client nên truy xuất tài nguyên đích, thường bằng GET | Rõ nghĩa nhất cho POST thành công rồi mở trang kết quả |
| `307 Temporary Redirect` | Giữ method và body khi redirect | Không phù hợp nếu muốn đổi POST thành GET |
| `308 Permanent Redirect` | Giữ method và body, redirect mang tính lâu dài | Không dùng cho PRG thông thường |

Để tạo 303 một cách tường minh, có thể trả một `RedirectView` được cấu hình status:

~~~java
RedirectView view = new RedirectView("/messages/42");
view.setStatusCode(HttpStatus.SEE_OTHER);
return view;
~~~

Đoạn này minh họa trong handler có return type `RedirectView`, cần các import Spring MVC/HTTP tương ứng. Nếu dùng `return "redirect:..."` như dự án phía dưới, không khẳng định mặc định là 303; test cần xác minh 3xx/Location phù hợp.

## 3. RedirectAttributes: dữ liệu cho chuyển hướng

Interface cần import:

~~~java
import org.springframework.web.servlet.mvc.support.RedirectAttributes;
~~~

Hai thao tác trung tâm:

~~~java
attrs.addAttribute("id", 42);
attrs.addAttribute("tab", "history");
attrs.addFlashAttribute("notice", "Đã lưu thành công");
~~~

| Thao tác | Nơi giá trị xuất hiện | Vòng đời | Cách dùng |
| --- | --- | --- | --- |
| `addAttribute("id", 42)` | URI path hoặc query parameter | Tồn tại trong URL, bookmark/share được | Mã tài nguyên, trang, bộ lọc |
| `addFlashAttribute("notice", "...")` | FlashMap tạm, không được gắn vào URL | Dành cho request đích phù hợp rồi bị tiêu thụ | Thông báo thành công một lần |
| `model.addAttribute(...)` trong handler trả view thường | Model của request hiện tại | Phục vụ render hiện tại | Form/view data |
| `HttpSession.setAttribute(...)` | HTTP session | Tới khi bị xóa/hết hạn | Trạng thái nhiều request |
| `@SessionAttributes` | Model attributes được Spring lưu qua session | Tới khi kết thúc flow hoặc session hết hạn | Wizard nhiều bước |

### 3.1. addAttribute đi vào path hoặc query

~~~java
@PostMapping("/orders")
public String create(RedirectAttributes attrs) {
    attrs.addAttribute("id", 42);
    attrs.addAttribute("tab", "history");
    return "redirect:/orders/{id}";
}
~~~

Trong kịch bản này Location có dạng:

~~~text
/orders/42?tab=history
~~~

`id` mở rộng placeholder `{id}`, còn `tab` không có placeholder tương ứng nên có thể được đưa thành query parameter. Redirect attributes được format/encode phù hợp để dùng trong URI; tránh tự nối chuỗi query từ đầu vào không tin cậy.

Vì URL xuất hiện trong browser history, bookmarks, analytics, referer và access logs, **không** truyền access token, mật khẩu, email riêng tư hoặc thông tin nhạy cảm bằng `addAttribute`. Một ID có thể được xuất công khai vẫn cần kiểm tra quyền truy cập ở GET handler.

### 3.2. addFlashAttribute đưa dữ liệu vào request GET đích

~~~java
@PostMapping("/orders")
public String create(RedirectAttributes attrs) {
    attrs.addAttribute("id", 42);
    attrs.addFlashAttribute("notice", "Tạo đơn thành công");
    return "redirect:/orders/{id}";
}

@GetMapping("/orders/{id}")
public String detail(@PathVariable long id, Model model) {
    model.addAttribute("orderId", id);
    return "order-detail";
}
~~~

Đây là các fragment của controller đã khai báo mapping và view. Spring MVC sẽ tự chuyển flash `notice` vào `Model` của GET đích nếu flash còn hiệu lực và request khớp.

Ở template Thymeleaf:

~~~html
<p th:if="${notice != null}" th:text="${notice}"></p>
~~~

Không cần `@RequestParam("notice")`, vì notice **không phải query parameter**. Và không cần GET handler tự gọi session.getAttribute, vì Spring quản lý input FlashMap tự động.

### 3.3. RedirectAttributes không có hiệu lực giống Model thường

Handler:

~~~java
@PostMapping("/preview")
public String preview(Model model, RedirectAttributes attrs) {
    model.addAttribute("preview", "Hello");
    attrs.addFlashAttribute("notice", "Saved");
    return "preview";
}
~~~

Vì handler trả view `preview`, **không có redirect**, nên không nên trông đợi `notice` được chuyển cho request sau. Model thông thường phục vụ render request hiện tại.

Spring MVC có quy tắc tương thích cũ về default Model khi redirect: thuộc tính đơn giản của model có thể xuất hiện trên URL redirect nếu không dùng redirect attributes tường minh. `RequestMappingHandlerAdapter` có tùy chọn `ignoreDefaultModelOnRedirect` để điều khiển trường hợp này. Việc chỉ định `RedirectAttributes` rõ ràng giúp hạn chế lộ thuộc tính không mong muốn từ model.

## 4. FlashMap và FlashMapManager

Spring MVC có hai abstraction quan trọng:

- **`FlashMap`:** một map chứa các thuộc tính flash cộng với metadata nhận diện request đích và expiration.
- **`FlashMapManager`:** quản lý lưu/lấy/xóa FlashMap; implementation MVC mặc định thường là `SessionFlashMapManager`, lưu tạm trong HTTP session.

Spring MVC cung cấp khái niệm input/output map theo từng request:

- **Output FlashMap:** dữ liệu được đặt ở request nguồn để chuyển tới request tương lai.
- **Input FlashMap:** dữ liệu nhận ở request đích từ output trước đó.

**Quy trình chi tiết:**

~~~text
A. POST /orders
   Controller:
      attrs.addAttribute("id",42)
      attrs.addFlashAttribute("notice","OK")
      return "redirect:/orders/{id}"
   MVC/RedirectView:
      Expand URL thành /orders/42
      Stamp output FlashMap với target path và query
      FlashMapManager lưu output, thường trong HTTP session
   Server -> Client:
      HTTP 302, Location: /orders/42
      Set-Cookie: JSESSIONID=... (nếu session mới được tạo)

B. GET /orders/42, giữ cookie session
   FlashMapManager tìm map trùng target
   Lấy làm input FlashMap, loại map đã tiêu thụ khỏi nơi lưu
   MVC thêm notice="OK" vào Model
   Controller GET load order 42
   Template render notice và order detail

C. Browser refresh GET /orders/42
   Flash đã tiêu thụ, model không có notice từ A
   Trang vẫn load order 42 nhờ URL và dữ liệu bền vững
~~~

Một flash attribute **không được bảo đảm** sẽ xuất hiện đúng một lần trong mọi hoàn cảnh. Nó có thể mất vì timeout/session hoặc request khác; do đó phải hiểu là **nỗ lực chuyển dữ liệu tạm tới một request phù hợp**, không phải message queue có delivery guarantee.

### 4.1. Request matching và URL stamping

Đặc điểm nguy hiểm của flash là "request kế tiếp" có thể là polling/AJAX hoặc tải resource trước khi browser GET đích. Spring MVC giảm rủi ro bằng cách `RedirectView` **đánh dấu URL đích** (path và query parameters) trên FlashMap, và manager kiểm tra khi lấy:

~~~text
POST /orders -> Location: /orders/42?tab=summary
GET /api/notifications       -> thường không khớp target
GET /orders/42?tab=summary   -> khớp target, lấy flash
~~~

Spring khuyến nghị flash chủ yếu cho redirect scenarios. Stamping giảm nguy cơ bị lấy nhầm nhưng **không loại bỏ mọi race**, nhất là khi nhiều tab cùng session cùng redirect tới một target path/query. Request đích bị lỗi sau khi flash đã lấy cũng có thể khiến thông báo không còn cho lần refresh.

### 4.2. Flash có tạo session không?

Hỗ trợ flash **luôn có sẵn** trong Spring MVC, nhưng nếu không sử dụng flash, riêng việc bật hỗ trợ này không bắt buộc tạo session. Khi thực sự có output flash cần lưu, implementation mặc định thường dùng HTTP session.

Hệ quả:

- Client phải giữ **session cookie** giữa POST và GET.
- Nếu session expired/invalidated hoặc cookie bị chặn, notice có thể mất.
- Ứng dụng nhiều node phải cấu hình session sharing/sticky session nếu dữ liệu flash cần di chuyển giữa nodes.
- Object được lưu trong distributed session có thể đòi hỏi serialization phù hợp; ưu tiên flash value nhỏ, đơn giản.
- Flash không thay database và không phải chỗ lưu biên nhận duy nhất cho giao dịch.

### 4.3. Expiration và điều kiện dữ liệu biến mất

FlashMap có thời hạn tồn tại. Có thể mất trước khi trình duyệt mở URL đích nếu TTL hết; thời gian thực tế phụ thuộc manager/config. Nếu GET đích nhận được flash, manager thường **loại entry khi lấy**, không chờ người dùng click xác nhận đọc.

Đừng thiết kế điều kiện nghiệp vụ "chỉ thành công nếu trang đọc được flash": thao tác POST có thể đã thành công dù flash message bị mất. Nguồn dữ liệu kết quả phải là database/resource GET.

### 4.4. Khi cần dùng FlashMap trực tiếp

Có thể truy cập qua:

~~~java
Map<String, ?> input = RequestContextUtils.getInputFlashMap(request);
FlashMap output = RequestContextUtils.getOutputFlashMap(request);
~~~

Cần `org.springframework.web.servlet.support.RequestContextUtils`, `org.springframework.web.servlet.FlashMap` và Servlet `request`. Đây là fragment minh họa cho trường hợp nâng cao. Với controller thông thường, **ưu tiên `RedirectAttributes`** vì Spring lo việc lấy/lưu URL và flash.

Khi tự tạo redirect với tầng thấp (ví dụ tự set header Location), output FlashMap không nhất thiết được stamp/lưu theo cùng cơ chế view redirect. `RequestContextUtils.saveOutputFlashMap(location,request,response)` tồn tại cho các trường hợp như vậy, nhưng chỉ dùng nếu bạn chủ động kiểm soát redirect flow.

## 5. Vòng đời biểu mẫu hợp lệ và không hợp lệ

Một xử lý form MVC điển hình:

~~~java
@PostMapping("/messages")
public String submit(
        @Valid @ModelAttribute("form") MessageForm form,
        BindingResult errors,
        RedirectAttributes attrs) {

    if (errors.hasErrors()) {
        return "message-form";
    }

    long id = saveMessage(form); // Hàm service minh họa.
    attrs.addAttribute("id", id);
    attrs.addFlashAttribute("notice", "Đã lưu thành công");
    return "redirect:/messages/{id}";
}
~~~

**Nhánh thành công:** lưu dữ liệu → URL GET mới chứa ID → flash success message → redirect.

**Nhánh lỗi validation:** giữ form và `BindingResult` trong **cùng request** → render lại form; người dùng thấy field errors và dữ liệu vừa nhập. `BindingResult` bắt buộc đứng **ngay sau** tham số `@ModelAttribute` tương ứng.

Vì sao thường không redirect khi form lỗi?

- Các thông tin lỗi và rejected values nằm trong binding/model của request hiện tại.
- Redirect là một request mới: nếu không chủ động lưu form/errors vào flash, các thông tin này mất.
- Việc flash toàn bộ form chứa password, file upload, dữ liệu lớn hoặc nhạy cảm có thể không an toàn.
- Không cần thêm session flow phức tạp cho một form đơn giản.

### 5.1. Có thể dùng flash để mang lỗi validation qua redirect?

Có, nếu kiến trúc yêu cầu strict PRG ngay cả khi lỗi. Fragment nâng cao:

~~~java
attrs.addFlashAttribute("form", form);
attrs.addFlashAttribute(
        BindingResult.MODEL_KEY_PREFIX + "form", errors);
return "redirect:/messages/new";
~~~

Chú ý key `BindingResult.MODEL_KEY_PREFIX + "form"` phải khớp tên model attribute. GET form cũng phải tránh ghi đè form/errors nhận từ flash. Nhưng flash có giới hạn session, TTL, concurrency, dữ liệu cần bảo vệ và trạng thái BindingResult phức tạp: **render lại form cùng request khi lỗi** thường dễ bảo trì hơn.

## 6. So sánh RedirectAttributes, session và URL

| Nhu cầu | Cách làm phù hợp | Hệ quả |
| --- | --- | --- |
| Đường dẫn tới tài nguyên mới | `addAttribute("id", id)` và `redirect:/resources/{id}` | Dễ bookmark, reload và chia sẻ |
| Bộ lọc/tab/page hiện tại | `addAttribute` | Được lưu trong URL |
| Notice một lần sau POST | `addFlashAttribute` | Dữ liệu tạm, có thể mất do timeout |
| Dữ liệu nhiều bước wizard | `@SessionAttributes` hoặc session/state backend có kiểm soát | Cần quản lý lifecycle và cleanup |
| Kết quả nghiệp vụ bền vững | Database/repository | GET lại được sau reload và session hết hạn |
| API REST trả kết quả tạo mới | `201 Created` + Location/JSON | Không nhất thiết dùng redirect HTML |
| SPA/AJAX tự điều hướng | Response JSON và client-side navigation | Không dựa vào việc fetch tự follow redirect để chuyển màn hình |

`@SessionAttributes` không phải flash: đó là tính năng MVC giữ các model attributes qua nhiều request trong một controller flow và thường kết thúc bằng `SessionStatus.setComplete()`. `@RequestAttribute` cũng khác: đọc attribute của **request hiện tại**, không tự lưu qua redirect.

## 7. Cẩn thận với trạng thái HTTP và URL

### 7.1. RedirectView và 303 See Other

Nếu muốn 303 thay vì 302:

~~~java
@PostMapping("/submit")
public RedirectView submit(RedirectAttributes attrs) {
    long id = save(); // Minh họa.
    attrs.addAttribute("id", id);
    RedirectView view = new RedirectView("/messages/{id}");
    view.setStatusCode(HttpStatus.SEE_OTHER);
    return view;
}
~~~

Fragment này cần imports cho `RedirectView`, `HttpStatus` và service. Xác minh URL expansion/encoding/contextPath theo cấu hình sử dụng. Cách return `redirect:` ngắn gọn thường đủ với form MVC, còn 303 rõ ý nghĩa HTTP hơn nếu API contract muốn enforce GET.

### 7.2. Không mở open redirect

Sai:

~~~java
return "redirect:" + request.getParameter("next");
~~~

Nếu `next=https://evil.example`, ứng dụng có thể redirect người dùng sang domain do attacker chọn và tạo phishing. Dùng route nội bộ đã xác định, whitelist đích, canonicalization và kiểm tra scheme/host nếu thật sự cho phép return URL.

### 7.3. Không đưa bí mật vào URL hoặc flash tùy tiện

`addAttribute("token", secret)` lộ token qua history/referer/log. Flash không nằm trong URL nhưng có thể được giữ trong session, được render lên trang đích và chịu rủi ro session fixation/hijacking nếu quản trị session kém. Không lưu credentials, access tokens hay object domain có dữ liệu nhạy cảm trong flash chỉ vì nó "ẩn khỏi URL".

## 8. Dự án Spring Boot 3.5 hoàn chỉnh

Dự án Java 17 + Maven: mở form nhập nội dung, gửi POST, lưu memory, redirect đến trang detail với flash notice. Refresh GET không còn notice, còn dữ liệu message tồn tại trong bộ nhớ ứng dụng.

### 8.1. Cấu trúc

~~~text
redirect-flash-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/RedirectFlashApplication.java
    │   └── resources/templates/
    │       ├── message-form.html
    │       └── message-detail.html
    └── test/java/demo/MessageControllerTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>redirect-flash-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. RedirectFlashApplication.java

Toàn bộ Java code dưới đây thuộc **một file** `src/main/java/demo/RedirectFlashApplication.java`. Có một public top-level class trùng tên file, các class khác package-private.

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@SpringBootApplication
public class RedirectFlashApplication {
    public static void main(String[] args) {
        SpringApplication.run(RedirectFlashApplication.class, args);
    }
}

class MessageForm {
    @NotBlank
    @Size(max = 100)
    private String text;

    public MessageForm() {}

    public String getText() { return text; }
    public void setText(String text) { this.text = text; }
}

record Message(long id, String text) {}

@Controller
@RequestMapping("/messages")
class MessageController {
    private final Map<Long, Message> store = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong();

    @GetMapping("/new")
    String newForm(Model model) {
        if (!model.containsAttribute("form")) {
            model.addAttribute("form", new MessageForm());
        }
        return "message-form";
    }

    @PostMapping
    String create(
            @Valid @ModelAttribute("form") MessageForm form,
            BindingResult errors,
            RedirectAttributes attrs) {

        if (errors.hasErrors()) {
            return "message-form";
        }

        long id = nextId.incrementAndGet();
        store.put(id, new Message(id, form.getText().trim()));

        attrs.addAttribute("id", id);
        attrs.addFlashAttribute(
                "notice", "Đã tạo thông báo thành công");

        return "redirect:/messages/{id}";
    }

    @GetMapping("/{id}")
    String detail(@PathVariable long id, Model model) {
        Message message = store.get(id);
        if (message == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Message not found");
        }

        model.addAttribute("message", message);
        // notice đã được đưa vào model nếu input FlashMap tồn tại.
        return "message-detail";
    }
}
~~~

**Giải thích:** POST thành công thêm hai loại attribute: `id` thay vào URL, `notice` đi theo flash. POST lỗi render lại form nên `BindingResult` vẫn khả dụng. GET detail tự tải data theo id, không cần notice để hoạt động; refresh GET vẫn hiển thị message.

`ConcurrentHashMap`/`AtomicLong` cho phép demo trong RAM có nhiều request, nhưng đây không phải storage bền vững; khởi động lại ứng dụng sẽ mất messages. Ứng dụng thật cần repository/service, transaction và authorization.

### 8.4. message-form.html

Đặt vào `src/main/resources/templates/message-form.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Tạo thông báo</title>
</head>
<body>
  <h1>Tạo thông báo</h1>
  <form th:action="@{/messages}" th:object="${form}" method="post">
    <label for="text">Nội dung</label>
    <input id="text" type="text" th:field="*{text}" maxlength="100">
    <div th:if="${#fields.hasErrors('text')}"
         th:errors="*{text}">Lỗi nhập liệu</div>
    <button type="submit">Tạo</button>
  </form>
</body>
</html>
~~~

`th:object` chọn form bean, `th:field` bind input vào property `text`. Khi `@NotBlank` hoặc `@Size` không đạt, Thymeleaf lấy field errors từ `BindingResult` của model mà Spring đã chuẩn bị.

### 8.5. message-detail.html

Đặt vào `src/main/resources/templates/message-detail.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Chi tiết thông báo</title>
</head>
<body>
  <p th:if="${notice != null}" th:text="${notice}">Đã tạo</p>
  <h1 th:text="${message.text}">Nội dung</h1>
  <p>ID: <span th:text="${message.id}">0</span></p>
  <a th:href="@{/messages/new}">Tạo thông báo khác</a>
</body>
</html>
~~~

Dùng `th:text` để tự HTML-escape nội dung khi xuất ra view. Không dùng `th:utext` với dữ liệu người dùng chưa sanitize vì có thể gây XSS. Sau refresh, `notice` thường không tồn tại nên đoạn thông báo ẩn; `message` được tải lại từ store.

### 8.6. Khởi chạy và quan sát qua browser

Trong thư mục `redirect-flash-demo`:

~~~bash
mvn spring-boot:run
~~~

Mở `http://localhost:8080/messages/new`. Nhập một nội dung hợp lệ rồi submit. Browser được redirect tới `/messages/1` nếu đó là lần tạo đầu; thông báo flash chỉ xuất hiện trong lượt GET đích đầu. Refresh trang: nội dung message vẫn có, còn notice biến mất. Quay lại form, nhập chuỗi trống hoặc toàn dấu cách để kiểm tra validation: controller render form trực tiếp và không redirect.

### 8.7. Thử với curl và cookie session

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  -X POST 'http://localhost:8080/messages' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'text=Hello Spring'
~~~

Khi là bản ghi đầu tiên, response redirect có Location `/messages/1` (và có thể có Set-Cookie cho HTTP session). Sau đó:

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  'http://localhost:8080/messages/1'
~~~

GET kế tiếp cùng session:

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  'http://localhost:8080/messages/1'
~~~

GET đầu có HTML notice, GET thứ hai không còn notice. Nếu không giữ cookie, flash có thể mất. Trên Windows PowerShell, dùng `curl.exe` và chạy trên một dòng hoặc dùng cú pháp nối dòng PowerShell; `\` trong ví dụ dành cho Bash.

Không dùng `curl -L -X POST` để suy diễn PRG: tùy tùy chọn, cURL có thể tiếp tục dùng POST khi theo redirect. Hai lệnh POST và GET tách biệt giúp thấy rõ redirect URL, HTTP status và session cookie.

### 8.8. Kiểm thử MockMvc

Tạo `src/test/java/demo/MessageControllerTest.java`:

~~~java
package demo;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class MessageControllerTest {
    @Autowired MockMvc mvc;

    @Test
    void validPostRedirectsAndStoresFlash() throws Exception {
        mvc.perform(post("/messages").param("text", "Hello"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("/messages/*"))
            .andExpect(flash().attribute(
                    "notice", "Đã tạo thông báo thành công"));
    }

    @Test
    void invalidPostRendersTheForm() throws Exception {
        mvc.perform(post("/messages").param("text", "  "))
            .andExpect(status().isOk())
            .andExpect(view().name("message-form"))
            .andExpect(model().attributeHasFieldErrors("form", "text"));
    }

    @Test
    void noticeExistsOnFirstMatchingGetOnly() throws Exception {
        MvcResult postResult = mvc.perform(
                post("/messages").param("text", "Once"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String location = postResult.getResponse().getRedirectedUrl();
        assertNotNull(location);
        HttpSession session = postResult.getRequest().getSession(false);
        assertNotNull(session);
        MockHttpSession mockSession = (MockHttpSession) session;

        mvc.perform(get(location).session(mockSession))
            .andExpect(status().isOk())
            .andExpect(view().name("message-detail"))
            .andExpect(model().attribute(
                    "notice", "Đã tạo thông báo thành công"));

        mvc.perform(get(location).session(mockSession))
            .andExpect(status().isOk())
            .andExpect(model().attributeDoesNotExist("notice"));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Test kiểm tra redirect Location, flash ở output FlashMap, việc load flash ở GET đầu và sự biến mất ở GET thứ hai. Lấy redirect URL thực tế nên không giả định ID cố định giữa tests. Đây là **MockMvc test** của MVC; muốn kiểm tra browser session cookie, nhiều node, proxy, timeout hoặc concurrent tabs cần integration/E2E tests bổ sung.

## 9. Các sai lầm thường gặp

1. **Dùng `addAttribute` cho thông báo riêng tư:** thông báo có thể xuất hiện trên query string và lộ qua history/log. Dùng flash cho notice nhỏ; không dùng flash để lưu secrets.
2. **Quên redirect:** gọi `addFlashAttribute` nhưng handler trả view thường. Flash không được tự chuyển sang request đích.
3. **Không giữ session cookie:** POST và GET diễn ra ở hai session khác nhau, nên GET không thấy flash.
4. **Tự tạo Location header mà không lưu FlashMap:** cách redirect thấp tầng có thể bỏ qua lifecycle của RedirectView.
5. **GET detail phụ thuộc vào flash:** refresh hoặc mất session làm trang hỏng. GET phải truy xuất resource theo ID URL.
6. **Validation lỗi vẫn redirect mà không mang form/BindingResult:** người dùng không thấy lỗi; với lỗi form thông thường render lại cùng view.
7. **Dùng flash làm queue hoặc dữ liệu bền vững:** dữ liệu có TTL, bị tiêu thụ và có thể mất do concurrency.
8. **Đặt cùng target cho redirect từ nhiều tab:** URL stamping không phân biệt hoàn toàn các flash maps có cùng URL đích.
9. **Tin PRG ngăn mọi duplicate write:** cần idempotency protection ở server cho tác vụ ghi quan trọng.
10. **Dùng `@SessionAttributes` thay cho flash:** session attribute sống qua nhiều requests và cần kết thúc rõ, nên notice có thể hiển thị lặp.
11. **Tự nối redirect URL từ giá trị không tin cậy:** nguy cơ open redirect và encoding sai.
12. **Dùng browser fetch tự follow redirect rồi chờ full page navigation:** AJAX/SPA thường cần client navigation và trạng thái riêng.
13. **Quên CSRF protection cho form POST khi có Spring Security:** PRG không ngăn CSRF; bật CSRF theo policy, không bỏ chỉ vì demo.
14. **Không kiểm tra URL/query stamping qua reverse proxy:** rewrite URL hoặc thay query có thể làm flash không khớp request đích.
15. **Dùng flash chứa entity/lượng dữ liệu lớn:** tạo rủi ro session serialization, memory và thông tin riêng tư.

## 10. Câu hỏi luyện tập

**Bài 1.** POST tạo đơn id 123, GET kết quả `/orders/123`. Viết đoạn dùng `addAttribute("id", 123)` và `addFlashAttribute("notice", "Đã tạo đơn")`. Cho biết field nào nằm ở URL, field nào chỉ được render một lần.

**Bài 2.** Vẽ chuỗi POST → 302 → GET → refresh GET. Xác định lúc nào output FlashMap được lưu, lúc nào input FlashMap được lấy và lúc nào dữ liệu bị loại bỏ.

**Bài 3.** Vì sao trong form validation `BindingResult` phải đứng ngay sau `@ModelAttribute`? Khi lỗi nên trả lại form hay redirect, và nếu redirect thì cần giữ những gì?

**Bài 4.** So sánh `addFlashAttribute` với `@SessionAttributes` đối với wizard cần giữ dữ liệu qua bốn bước. Tại sao flash có thể mất trước khi đến bước 4?

**Bài 5.** Hai tab cùng session POST rồi redirect tới `/profile` với hai notices khác nhau. Giải thích vì sao URL stamping chưa đảm bảo đúng notice ở từng tab và đề xuất hướng điều chỉnh flow.

**Bài 6.** Khách hàng gửi `next=https://attacker.example`. Vì sao `return "redirect:" + next` có thể nguy hiểm? Thiết kế allowlist các đích nội bộ.

**Bài 7.** Trong MockMvc, làm sao assert output flash, lấy URL redirect thực tế, truyền cùng MockHttpSession cho GET thứ nhất và xác minh flash không còn ở GET thứ hai?

**Bài 8.** Nếu POST tạo đơn thành công nhưng cookie không được gửi trong GET, kết quả domain và thông báo flash khác nhau như thế nào? Trang GET nên hoạt động ra sao?

## 11. Ghi nhớ

- **PRG** ngăn refresh trang kết quả vô tình gửi lại POST, nhưng không bảo đảm idempotency tuyệt đối.
- **`RedirectAttributes.addAttribute`** tạo URL/path/query state; chỉ dùng cho dữ liệu được phép công khai.
- **`RedirectAttributes.addFlashAttribute`** tạo dữ liệu tạm cho **request đích phù hợp**; mặc định dựa trên HTTP session và có hạn sử dụng.
- **`FlashMap` + `FlashMapManager`** chịu trách nhiệm lưu, khớp target, đưa vào model rồi tiêu thụ; URL stamping giảm nhưng không xóa hết race.
- **Validation lỗi thường render form cùng request** để giữ BindingResult. **Thành công thường redirect** và flash thông báo.
- Flash là UX convenience, không phải database, session wizard, secret store hay queue bảo đảm giao hàng.

## 12. Tham khảo

- [Spring Framework 6.2 — Redirect Attributes](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html).
- [Spring Framework 6.2 — Flash Attributes](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/flash-attributes.html).
- [Spring MVC — RedirectAttributes API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/support/RedirectAttributes.html).
- [Spring MVC — FlashMap API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/FlashMap.html).
- [Spring MVC — RedirectView API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/view/RedirectView.html).
- [Spring MVC — Thymeleaf Views](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-view/mvc-thymeleaf.html).
