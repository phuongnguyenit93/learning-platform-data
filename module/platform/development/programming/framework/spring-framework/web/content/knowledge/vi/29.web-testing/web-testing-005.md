# Kiểm thử view, form, redirect, flash attributes và session trong Spring MVC

Một luồng web dùng HTML có thể trả lại trang biểu mẫu khi nhập sai, hoặc nhận POST thành công rồi chuyển hướng tới một GET khác. Kiểm thử đúng luồng này phải nhìn được **view nào được chọn, model nào được chuyển cho view, dữ liệu form có được bind và validate, response có redirect đi đâu, thông điệp flash đến được request nào, và trạng thái session có tồn tại đúng vòng đời hay không**.

Đây là nội dung của Spring MVC theo mô hình Servlet, áp dụng cho `@Controller` trả về HTML/view (khác với các endpoint `@RestController` chủ yếu trả JSON). Ví dụ dùng Java 17+, Spring Boot 3.3 và JUnit 5 để cấu hình dễ chạy; cơ chế view/model/`RedirectAttributes`/session thuộc Spring MVC.

## 1. Nhìn cả luồng, không chỉ một status code

Giả sử có trang đăng ký tại `GET /signup` và form gửi đến `POST /signup`:

```text
GET /signup
  → controller khởi tạo đối tượng form vào Model
  → view "signup/form"
  → trình duyệt nhận trang HTML có <form>

POST /signup, name="  " (không hợp lệ)
  → data binding + Bean Validation
  → BindingResult chứa lỗi
  → trả lại view "signup/form" cùng lỗi, KHÔNG redirect

POST /signup, name="An" (hợp lệ)
  → xử lý form
  → ghi thuộc tính lâu hơn một request vào HttpSession
  → addFlashAttribute("notice", ...)
  → response 3xx + Location: /signup/done

GET /signup/done (cùng session)
  → thông điệp flash trở thành thuộc tính trong Model
  → view "signup/done" hiển thị kết quả
  → flash đã được lấy khỏi nơi lưu tạm

GET /signup/done lần nữa (cùng session)
  → flash "notice" không còn
  → thuộc tính session vẫn còn nếu chưa xóa
```

Luồng thành công là mẫu **Post/Redirect/Get (PRG)**. Trình duyệt nhận kết quả POST bằng redirect, sau đó chuyển sang GET; refresh trang kết quả thường không tự lặp lại POST. PRG giúp giảm nguy cơ gửi lại biểu mẫu do refresh, nhưng không phải bảo đảm chống mọi POST trùng lặp: thao tác thay đổi dữ liệu quan trọng vẫn cần kiểm soát ở tầng nghiệp vụ, chẳng hạn idempotency key hoặc unique constraint khi phù hợp.

| Thành phần | Dữ liệu sống ở đâu / bao lâu | Điều nên assert |
| --- | --- | --- |
| View name | Kết quả chọn view của handler | `view().name("signup/form")` |
| Model | Thuộc tính đưa cho view trong request | `model().attributeExists(...)`, `model().attribute(...)` |
| Form binding / validation | Request parameters → form object; lỗi trong `BindingResult` | `model().attributeHasFieldErrors(...)` hoặc `attributeHasNoErrors(...)` |
| Redirect | HTTP response 3xx với header `Location` | `status().is3xxRedirection()`, `redirectedUrl(...)` |
| Flash attribute | Dữ liệu tạm để chuyển sang request đích, thường lưu qua session | `flash().attribute(...)` ở POST, `model().attribute(...)` ở GET sau redirect |
| Session attribute | Trạng thái gắn với session, có thể tồn tại qua nhiều request | `session().attribute(...)` với cùng `MockHttpSession` |

**Chú ý:** `MockMvc` dùng request/response Servlet mô phỏng, có thể thực hiện MVC, view resolution và render template được cấu hình, nhưng không mở HTTP socket. `andExpect(redirectedUrl(...))` kiểm tra thông tin chuyển hướng; nó **không tự thực hiện GET tiếp theo**. Muốn kiểm tra PRG đầy đủ, bài test phải gọi GET riêng và mang cùng session.

## 2. Chuẩn bị một ví dụ chạy được

Cấu trúc ví dụ:

```text
src/main/java/com/example/webtest/
  WebTestApplication.java
  SignupForm.java
  SignupController.java
src/main/resources/templates/signup/
  form.html
  done.html
src/test/java/com/example/webtest/
  SignupControllerWebTest.java
```

Dùng một dự án Spring Boot 3.3 (Java 17+) với các dependency Gradle sau; phần cấu hình plugin/version Spring Boot của project vẫn do build chính quản lý:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-validation` cung cấp implementation Bean Validation cho `@NotBlank`/`@Valid`. `spring-boot-starter-thymeleaf` có tác dụng render view thật bằng template; nhờ vậy ngoài tên view và model, có thể assert nội dung HTML. Nếu ứng dụng thật dùng JSP hoặc một view resolver khác, phải cấu hình engine và môi trường tương ứng; đừng tự suy rằng tên view đúng đồng nghĩa file template tồn tại.

Tệp `WebTestApplication.java`:

```java
package com.example.webtest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebTestApplication.class, args);
    }
}
```

Tệp `SignupForm.java`:

```java
package com.example.webtest;

import jakarta.validation.constraints.NotBlank;

public class SignupForm {
    @NotBlank(message = "Tên không được để trống")
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Tệp `SignupController.java`:

```java
package com.example.webtest;

import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/signup")
public class SignupController {

    @GetMapping
    public String showForm(Model model) {
        model.addAttribute("signupForm", new SignupForm());
        return "signup/form";
    }

    @PostMapping
    public String submit(
            @Valid @ModelAttribute("signupForm") SignupForm form,
            BindingResult errors,
            RedirectAttributes redirect,
            HttpSession session) {

        if (errors.hasErrors()) {
            return "signup/form";
        }

        session.setAttribute("lastName", form.getName());
        redirect.addFlashAttribute("notice", "Đăng ký thành công");
        return "redirect:/signup/done";
    }

    @GetMapping("/done")
    public String done(Model model, HttpSession session) {
        model.addAttribute("lastName", session.getAttribute("lastName"));
        return "signup/done";
    }

    @GetMapping("/reset")
    public String reset(HttpSession session) {
        session.removeAttribute("lastName");
        return "redirect:/signup";
    }
}
```

Đặt `BindingResult` **ngay sau** tham số `@Valid @ModelAttribute` mà nó kiểm tra. Khi dữ liệu không hợp lệ, controller trả lại form và các lỗi binding/validation trong model; nếu đẩy `BindingResult` ra vị trí không phù hợp hoặc không xử lý lỗi, hành vi có thể chuyển thành exception thay vì hiển thị lỗi trong form.

Mã trên cố ý chỉ ghi một tên vào session để minh họa; ứng dụng thực tế cần xử lý nghiệp vụ, phân quyền và dữ liệu nhạy cảm theo yêu cầu hệ thống. Không dùng `HttpSession` làm kho dữ liệu dùng chung giữa các người dùng.

Tệp `templates/signup/form.html`:

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Đăng ký</title></head>
<body>
<h1>Nhập tên</h1>
<form th:action="@{/signup}" th:object="${signupForm}" method="post">
    <label for="name">Tên</label>
    <input id="name" type="text" th:field="*{name}">
    <p th:if="${#fields.hasErrors('name')}"
       th:errors="*{name}">Lỗi nhập tên</p>
    <button type="submit">Gửi</button>
</form>
</body>
</html>
```

Tệp `templates/signup/done.html`:

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Kết quả</title></head>
<body>
<h1>Đăng ký</h1>
<p id="notice" th:text="${notice}">Thông báo</p>
<p id="name" th:text="${lastName}">Tên đã nhập</p>
</body>
</html>
```

Thymeleaf tự dùng `BindingResult` để render lỗi của `th:errors`. Model attribute là dữ liệu server gửi cho view; trình duyệt không có quyền truy cập trực tiếp object Java. Template tương ứng mới cho phép chuyển nội dung ấy thành HTML.

## 3. Kiểm thử GET: tên view, model và HTML được render

Sử dụng `@WebMvcTest(SignupController.class)` để nạp web slice cùng `MockMvc`. Test này kiểm tra route, binding, validation, view resolver/template sẵn có trong slice và session mô phỏng; nó không tạo server thật và không tự chứng minh các dịch vụ bên ngoài.

Tệp `src/test/java/com/example/webtest/SignupControllerWebTest.java`:

```java
package com.example.webtest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.session;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@WebMvcTest(SignupController.class)
class SignupControllerWebTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getFormReturnsViewModelAndRenderedHtml() throws Exception {
        mvc.perform(get("/signup"))
                .andExpect(status().isOk())
                .andExpect(view().name("signup/form"))
                .andExpect(model().attributeExists("signupForm"))
                .andExpect(content().string(containsString("Nhập tên")))
                .andExpect(content().string(containsString("name=\"name\"")));
    }

    @Test
    void invalidFormShowsFieldErrorWithoutRedirect() throws Exception {
        mvc.perform(post("/signup").param("name", "   "))
                .andExpect(status().isOk())
                .andExpect(view().name("signup/form"))
                .andExpect(model().attributeHasFieldErrors(
                        "signupForm", "name"))
                .andExpect(content().string(
                        containsString("Tên không được để trống")));
    }

    @Test
    void successRedirectsAndCarriesFlashAcrossOneGet() throws Exception {
        MockHttpSession browserSession = new MockHttpSession();

        mvc.perform(post("/signup")
                        .session(browserSession)
                        .param("name", "An"))
                .andExpect(status().is3xxRedirection())
                .andExpect(view().name("redirect:/signup/done"))
                .andExpect(redirectedUrl("/signup/done"))
                .andExpect(flash().attribute(
                        "notice", "Đăng ký thành công"))
                .andExpect(session().attribute("lastName", "An"));

        mvc.perform(get("/signup/done").session(browserSession))
                .andExpect(status().isOk())
                .andExpect(view().name("signup/done"))
                .andExpect(model().attribute(
                        "notice", "Đăng ký thành công"))
                .andExpect(model().attribute("lastName", "An"))
                .andExpect(content().string(
                        containsString("Đăng ký thành công")));

        mvc.perform(get("/signup/done").session(browserSession))
                .andExpect(status().isOk())
                .andExpect(model().attributeDoesNotExist("notice"))
                .andExpect(model().attribute("lastName", "An"));
    }

    @Test
    void resetRemovesPersistentSessionAttribute() throws Exception {
        MockHttpSession browserSession = new MockHttpSession();
        browserSession.setAttribute("lastName", "An");

        mvc.perform(get("/signup/reset").session(browserSession))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/signup"))
                .andExpect(session().attributeDoesNotExist("lastName"));
    }
}
```

Chạy test với Gradle wrapper từ thư mục project:

```bash
./gradlew test --tests com.example.webtest.SignupControllerWebTest
```

Trên Windows PowerShell, có thể dùng `.\gradlew.bat test --tests com.example.webtest.SignupControllerWebTest`. Các assertion ở trên mô tả **kết quả mong đợi** của ví dụ, không phải log chạy test được công bố. Dự án cần có đúng dependency, class và template đã trình bày; nếu thiếu template, lỗi có thể xuất hiện ở khâu resolve/render view dù controller chọn đúng logical view name.

### Tại sao phải assert cả view và HTML?

`view().name("signup/form")` chứng minh handler chọn logical view phù hợp. Nó chưa chứng minh view engine tìm được template và render đúng nội dung. Khi Thymeleaf được nạp cùng các tệp `form.html` và `done.html`, kiểm tra `content().string(...)` bổ sung chứng cứ HTML trả về có các phần quan trọng.

Đừng so toàn bộ chuỗi HTML nếu mục đích chỉ là xác nhận một nhãn, lỗi validation hay trường input; format whitespace, thứ tự attribute HTML hoặc layout có thể thay đổi mà chức năng vẫn đúng. Nếu cần xác thực cấu trúc DOM và hành vi JavaScript, dùng công cụ test HTML/DOM hoặc trình duyệt phù hợp; `MockMvc` không thực thi JavaScript trình duyệt.

## 4. Kiểm thử form binding và validation

Trong ví dụ, `post("/signup").param("name", "   ")` tạo Servlet request parameter đã được decode; MVC binder gán giá trị vào `SignupForm.name` trước khi `@Valid` kiểm tra `@NotBlank`. Các trường hợp quan trọng nên tách rành mạch:

- **Form hợp lệ:** attribute `signupForm` bind được, `BindingResult` không có lỗi, controller redirect.
- **Form lỗi validation:** MVC vẫn bind được giá trị nhưng constraint không đạt, controller render lại form cùng field error; không gọi thành công nghiệp vụ.
- **Form lỗi chuyển đổi kiểu:** một trường số nhận ký tự không hợp lệ có thể sinh lỗi binding/conversion; cần assert đúng field/object error, không mặc nhiên coi đó là cùng một lỗi `@NotBlank`.
- **Thiếu parameter:** tùy kiểu dữ liệu và constraint, field có thể là `null` hoặc giá trị mặc định; test cần phản ánh hợp đồng thực tế, không dựa vào suy đoán.
- **Lỗi giả dữ liệu từ test:** `.param("name", "An")` thêm request parameter mô phỏng; nó không kiểm tra browser thật đã gửi form hay cơ chế multipart/form encoding ở tầng mạng.

Một assertion tập trung vào form hợp lệ có thể dùng `model().attributeHasNoErrors("signupForm")` khi response thực sự có thuộc tính form trong model. Trong mẫu thành công, controller trả **redirect**, vì vậy assert redirect và flash/session là đúng trọng tâm hơn việc kỳ vọng form model còn tồn tại ở response chuyển hướng.

Có thể dùng `@InitBinder` và custom validator nếu nghiệp vụ đòi hỏi. Lúc đó cần kiểm tra cùng cấu hình binder/validator với ứng dụng; tạo controller trực tiếp trong unit test sẽ không tự đi qua data binder MVC.

## 5. Redirect: kiểm tra Location và PRG

Trong controller, `return "redirect:/signup/done"` yêu cầu Spring MVC tạo redirect response. Test nên xác minh cả response là 3xx và URL đích:

```java
mvc.perform(post("/signup").param("name", "An"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/signup/done"));
```

Đoạn kiểm tra độc lập này chỉ minh họa matcher; test đầy đủ ở phần trước dùng cùng `MockHttpSession` để theo dấu state. Nếu muốn xác nhận đúng mã HTTP cụ thể do contract quy định, có thể assert `status().isFound()` cho 302, hoặc mã 303 khi ứng dụng chủ động trả “See Other”. Không nên cho rằng Spring MVC mặc định luôn dùng 303 chỉ vì code theo PRG.

`redirectedUrl(...)` kiểm tra URL trong redirect; `header().string("Location", "...")` cũng có thể dùng nếu muốn kiểm tra trực tiếp header. `view().name("redirect:/signup/done")` là tên view logic phía MVC; HTTP client thật không thấy tên view logic này, nó thấy response status và header.

`RedirectAttributes` có hai đường truyền cần phân biệt:

```java
// Minh họa trong handler xử lý redirect:
redirect.addAttribute("page", 2);          // Có thể đi vào path/query URL
redirect.addFlashAttribute("notice", "OK"); // Qua FlashMap, không nằm trong URL
```

`addAttribute` dùng giá trị để mở rộng URI template hoặc tạo query parameter tùy target redirect và cấu hình. `addFlashAttribute` lưu dữ liệu tạm cho request sau chuyển hướng (thường dựa trên HTTP session). Không đặt password/token hay dữ liệu nhạy cảm trong query string chỉ để truyền từ POST sang GET; URL có thể xuất hiện trong log, history và referrer.

## 6. Flash attributes: hai phía và đúng một lần sử dụng

Flash attributes là dữ liệu được giữ **giữa các request** để hiển thị một thông báo sau redirect. Spring MVC quản lý chúng qua `FlashMap` và `FlashMapManager`. Controller dùng `RedirectAttributes.addFlashAttribute` nên thông thường không phải thao tác trực tiếp với `FlashMap`.

Có hai phép đo khác nhau:

1. **Output flash map của POST:** `flash().attribute("notice", "...")` cho thấy handler đã chuẩn bị thông báo để chuyển tiếp.
2. **Input/model của GET đích:** `model().attribute("notice", "...")` trên `GET /signup/done` chứng minh request đích đã nhận thông báo.

Phép đo thứ ba trong ví dụ, cùng session gọi `GET /signup/done` thêm lần nữa rồi assert `model().attributeDoesNotExist("notice")`, kiểm tra đặc trưng dùng một lần. Session `lastName` vẫn còn, nên thấy rõ flash khác dữ liệu session bền hơn.

**Không đánh đồng:** việc viết `.flashAttr("notice", "OK")` ngay trên request GET trong một test là cách **tiêm sẵn input flash attribute** để kiểm tra view đích; nó hữu ích để cô lập view, nhưng không chứng minh POST đã tạo flash hay `FlashMapManager` đã lưu rồi tiêu thụ nó. Muốn kiểm tra trọn PRG như bài này, thực hiện POST và GET thật sự bằng hai `MockMvc.perform` có cùng `MockHttpSession`.

Spring MVC gắn metadata của redirect target vào flash map nhằm hạn chế request khác lấy nhầm thông báo. Dù vậy, các request song song (polling, asset hoặc AJAX trong một số trường hợp) có thể tạo tình huống đua; không dùng flash như một hàng đợi nghiệp vụ có yêu cầu giao hàng chính xác hoặc làm nơi lưu kết quả dài hạn.

## 7. Session: chia sẻ đúng một phiên qua nhiều request

Một HTTP session có thể giữ state giữa nhiều request của cùng client. Với test `MockMvc`, hai lời gọi `perform` độc lập không tự biểu diễn cùng một trình duyệt nếu bạn không tái sử dụng session. Vì vậy ta tạo một `MockHttpSession` và đưa nó vào các request bằng `.session(browserSession)`:

```java
MockHttpSession browserSession = new MockHttpSession();
browserSession.setAttribute("theme", "dark");

mvc.perform(get("/signup/done").session(browserSession))
        .andExpect(session().attribute("theme", "dark"));
```

Ở ứng dụng chạy thật, client thường gắn session id bằng cookie như `JSESSIONID` và server quản lý dữ liệu thuộc phiên đó; tên cookie, session store và chính sách bảo vệ còn phụ thuộc cấu hình Servlet container/Spring Session. `MockHttpSession` chỉ kiểm tra trạng thái ở tầng Servlet mô phỏng, không chứng minh cookie của trình duyệt được bảo vệ bởi `Secure`, `HttpOnly`, `SameSite`, hoặc session store phân tán hoạt động đúng.

Để kiểm tra session được dọn đúng lúc, endpoint `/signup/reset` gọi `session.removeAttribute("lastName")`; test dùng `session().attributeDoesNotExist("lastName")`. Nếu ứng dụng cần kết thúc **toàn bộ** phiên, `session.invalidate()` là thao tác khác, có tác động tới tất cả thuộc tính session; hãy kiểm tra theo chính sách logout và bảo mật của ứng dụng.

### HttpSession khác @SessionAttributes

`HttpSession` là Servlet API cho dữ liệu gắn với phiên. `@SessionAttributes` trên lớp `@Controller` lại là cơ chế Spring MVC đưa một số **model attributes do controller quản lý** vào session để hỗ trợ nhiều bước form/wizard:

```java
// Ví dụ ý tưởng; không phải controller hoàn chỉnh chạy độc lập.
@Controller
@SessionAttributes("draft")
class DraftController {
    // Model có thuộc tính "draft" sẽ được lưu trong session.
    // Khi kết thúc hội thoại, handler nhận SessionStatus:
    // status.setComplete();
}
```

`SessionStatus.setComplete()` kết thúc việc lưu các model attributes mà controller khai báo với `@SessionAttributes`; nó **không có nghĩa** invalidate toàn bộ `HttpSession` và không thay thế logic logout. Với form nhiều bước, test nên kiểm tra draft sống qua các request cần thiết và được dọn sau `setComplete()`; với form một bước ở ví dụ này, dùng `HttpSession` trực tiếp đủ để làm rõ state.

Dữ liệu session có thể tạo phụ thuộc giữa test cases. Tạo `MockHttpSession` mới cho từng test hoặc dọn fixture rõ ràng; không dùng một static session chung khiến thứ tự chạy test ảnh hưởng kết quả.

## 8. Những điểm cần đặc biệt lưu ý khi viết test thực tế

**Cấu hình web slice:** `@WebMvcTest` là annotation của Spring Boot; nó nạp phần MVC phù hợp, không nạp toàn bộ service/repository của ứng dụng. Controller có dependency ngoài slice cần mock rõ ràng (với Boot 3.3 thường là `@MockBean`). Muốn kiểm tra kết nối bean thật, cân nhắc `@SpringBootTest` kết hợp `@AutoConfigureMockMvc`; vẫn không có HTTP socket trừ khi dùng server thật và một client HTTP mạng. Các matcher view, model, flash và session vẫn hữu ích trong MockMvc có context lớn hơn.

**Security/CSRF:** nếu thêm `spring-boot-starter-security`, POST form có thể bị chặn 403 trước khi vào controller nếu thiếu CSRF token hoặc quyền. Khi muốn kiểm tra flow có security, thêm dependency `spring-security-test` và cung cấp xác thực/CSRF đúng với tình huống kiểm thử, ví dụ `post("/signup").with(csrf())` với static import `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf`. Đừng tắt security filter chỉ để một test form xanh rồi xem như đã kiểm tra bảo mật.

**Tên view so với HTTP thực:** với `MockMvc`, `view().name(...)` và `model()` là assertion thuộc tầng Spring MVC; với HTTP client chạy qua cổng thật, chỉ có status/header/body/cookie và hành vi public quan sát được. Nếu endpoint phục vụ SPA hoặc response JSON, việc assert logical view không còn là hợp đồng tương ứng.

**Redirect chain:** `MockMvc` không tự theo redirect. Test có thể cần nhiều `perform` liên tiếp; một test chỉ kiểm tra mã 302 sẽ bỏ sót flash không tới đích, session bị mất hoặc view GET lỗi.

**Dữ liệu form và encoding:** `.param(...)` cung cấp parameter đã decode. Nếu đặc tả yêu cầu xử lý UTF-8, kích thước payload, multipart file upload hoặc proxy/client thật, cần thêm test phù hợp với tầng mà vấn đề có thể xảy ra.

**Lỗi validation:** không assert mỗi `status().isOk()` ở POST lỗi rồi kết luận người dùng đã được báo lỗi. Phải kiểm tra `BindingResult` và/hoặc thông báo HTML hiển thị. Kiểm thử chuyển đổi kiểu và lỗi business (ví dụ tên đã tồn tại) là các tình huống khác nhau; mỗi tình huống cần kết quả kỳ vọng riêng.

**Độ tin cậy của session:** flash thường dùng session như nơi lưu tạm nhưng có vòng đời khác session attribute. Tránh dùng flash để giữ một đối tượng lớn hoặc trạng thái quan trọng phải tồn tại qua nhiều request; tránh giữ tài nguyên không serializable nếu hệ thống dự định dùng session store phân tán.

## 9. Checklist trước khi kết luận một luồng form đã được kiểm thử

| Bước | Câu hỏi chứng minh | Assertion điển hình |
| --- | --- | --- |
| GET form | Có chọn đúng view và cung cấp form object? | `view().name`, `model().attributeExists` |
| Render form | HTML có field và nhãn cần thiết? | `content().string(containsString(...))` |
| POST sai | Có bind/validate, trả lại form và lỗi field? | `attributeHasFieldErrors`, `view().name` |
| POST đúng | Có redirect thay vì render trực tiếp trang kết quả? | `is3xxRedirection`, `redirectedUrl` |
| Flash sau POST | Thông báo được đặt vào output flash? | `flash().attribute` |
| GET sau redirect | Request đích nhận thông báo và hiển thị? | `model().attribute` và HTML content |
| GET tiếp theo | Thông báo tạm không xuất hiện lần nữa? | `attributeDoesNotExist` |
| Cùng session | Thuộc tính ổn định qua nhiều request? | Tái sử dụng `MockHttpSession`, `session().attribute` |
| Dọn state | Thuộc tính đã xóa khi workflow kết thúc? | `session().attributeDoesNotExist` |

Tách các câu hỏi này ra sẽ giúp phân biệt lỗi controller/model, lỗi render template, lỗi validation, lỗi chuyển hướng và lỗi vòng đời state. Bài test mạnh là bài test đưa ra đúng **bằng chứng cho hợp đồng người dùng cần**, với bối cảnh MVC được cấu hình tương ứng.

### Tài liệu tham khảo

- Spring Framework — MockMvc expectations: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/expectations.html
- Spring Framework — MockMvc requests: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html
- Spring Framework — Redirect attributes: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html
- Spring Framework — Flash attributes: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/flash-attributes.html
- Spring Framework — @SessionAttributes: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html
- Spring Boot 3.3 — Testing Spring Boot applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
