# Kiểm tra model, view và các chi tiết phía máy chủ

`MockMvcTester` là API kiểm thử Spring MVC theo phong cách AssertJ, có từ Spring Framework 6.2. Ngoài status, header và response body, API này cho phép kiểm tra các kết quả chỉ tồn tại ở phía máy chủ như model attributes, logical view name, flash attributes và handler đã xử lý request. Những kiểm tra này hữu ích với controller trả view, luồng redirect, form có validation, hoặc endpoint cần gắn dữ liệu vào request/session.

Một response HTTP `200 OK` chưa chứng minh controller đã chọn đúng view hay đưa đúng dữ liệu vào model. Ví dụ, trang chi tiết tài khoản có thể trả status 200 nhưng thiếu model attribute `account`; template khi render sẽ không có dữ liệu cần thiết. Kiểm tra model và view giúp test xác nhận hợp đồng giữa controller với tầng hiển thị.

## MockMvcTester trong luồng xử lý MVC

`MockMvcTester` dùng hạ tầng `MockMvc`. Request được chuyển qua `DispatcherServlet` cùng các thành phần Spring MVC đã được cấu hình trong môi trường test. Vì vậy, test có thể quan sát handler được chọn, model và view mà controller trả về, flash attributes của redirect, request/session attributes và response cuối cùng mà servlet mock tạo ra.

`MockMvcTester` không khởi động một web server thật. Test chạy trong mock servlet environment, không mở socket và không kiểm tra trình duyệt render trang. Đây là kiểm thử phía server cho luồng Spring MVC; nếu cần kiểm tra network stack, container, TLS hoặc HTML trong trình duyệt thật, cần thêm kiểm thử chạy ứng dụng trên server.

`MockMvcTester` được giới thiệu trong Spring Framework 6.2. Dự án cần có module `spring-test` và AssertJ trên test classpath. Các ví dụ dưới đây dùng Java, JUnit Jupiter và Spring Test 6.2 trở lên.

## Tạo MockMvcTester

Có ba cách dựng thường gặp, tùy phạm vi muốn kiểm tra.

### Dùng WebApplicationContext

Khi muốn dùng cấu hình Spring MVC của ứng dụng, tạo tester từ `WebApplicationContext`:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.web.SpringJUnitWebConfig;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.web.context.WebApplicationContext;

@SpringJUnitWebConfig(ApplicationWebConfiguration.class)
class AccountControllerMvcTest {

    private final MockMvcTester mvc;

    AccountControllerMvcTest(@Autowired WebApplicationContext context) {
        this.mvc = MockMvcTester.from(context);
    }
}
```

`ApplicationWebConfiguration` cần nạp controller, MVC infrastructure và các dependency mà controller sử dụng. Cách này phù hợp khi test cần kiểm tra mapping, interceptor, converter, validator, advice và cấu hình view resolver đã đăng ký trong context.

Với Spring Boot, có thể dùng `@SpringBootTest` để nạp application context rồi inject `WebApplicationContext` tương tự. Nếu dự án đã có `MockMvc`, có thể tạo tester từ instance đó bằng `MockMvcTester.create(mockMvc)`.

### Dùng một controller cụ thể

Nếu chỉ cần dựng một controller và cấu hình MVC tối thiểu, dùng `MockMvcTester.of(...)`:

```java
MockMvcTester mvc = MockMvcTester.of(new AccountController(accountService));
```

Ở chế độ này, test tập trung vào controller được truyền vào. Những thành phần như controller advice, validator, converter hoặc view resolver tùy chỉnh cần được cấu hình thêm nếu hành vi cần kiểm tra phụ thuộc vào chúng. Khi mục tiêu là kiểm tra cấu hình ứng dụng thật, nên dùng tester dựng từ `WebApplicationContext`.

## Cách gửi request và thực thi assertion

Request builder của `MockMvcTester` có các phương thức như `get()`, `post()`, `put()`, `delete()` và `uri(...)`. Nó tái sử dụng cách cấu hình request của MockMvc, ví dụ `param`, `header`, `content`, `contentType`, `accept`, `cookie`, `sessionAttr` và `with`.

```java
import static org.assertj.core.api.Assertions.assertThat;

assertThat(mvc.get().uri("/accounts/{id}", 42L))
        .hasStatusOk();
```

Lời gọi `assertThat(...)` nhận builder có hỗ trợ AssertJ, thực thi request và trả về assertion chuyên biệt cho `MvcTestResult`. Có thể gọi `.exchange()` nếu muốn giữ kết quả rồi dùng nhiều câu assertion:

```java
MvcTestResult result = mvc.get()
        .uri("/accounts/{id}", 42L)
        .exchange();

assertThat(result).hasStatusOk();
assertThat(result).hasViewName("accounts/detail");
```

Không thực thi cùng một builder hai lần nếu test muốn kiểm tra một request duy nhất. Hãy giữ `MvcTestResult` sau `.exchange()` và dùng nó cho tất cả assertion tiếp theo. `MvcTestResult` cũng cung cấp request, response và `MvcResult` nền để truy cập chi tiết khi assertion cấp cao chưa đủ.

## Kiểm tra model attributes

Model là dữ liệu controller chuẩn bị cho view. Controller có thể thêm dữ liệu bằng tham số `Model`, `ModelMap`, `ModelAndView` hoặc annotation `@ModelAttribute`.

Ví dụ controller trả view chi tiết:

```java
@Controller
class AccountController {

    private final AccountService accountService;

    AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @GetMapping("/accounts/{id}")
    String detail(@PathVariable long id, Model model) {
        Account account = accountService.findById(id);
        model.addAttribute("account", account);
        model.addAttribute("canEdit", accountService.canEdit(id));
        return "accounts/detail";
    }
}
```

Test có thể kiểm tra view và model trong cùng một chuỗi:

```java
assertThat(mvc.get().uri("/accounts/{id}", 42L))
        .hasStatusOk()
        .hasViewName("accounts/detail")
        .model()
        .containsKey("account")
        .containsEntry("canEdit", true);
```

`model()` trả về `ModelAssert`, một AssertJ map assertion trên các entry của model. Vì vậy, có thể dùng các phép kiểm tra map quen thuộc:

```java
assertThat(mvc.get().uri("/accounts/{id}", 42L))
        .model()
        .containsKeys("account", "canEdit")
        .containsEntry("canEdit", true)
        .doesNotContainKey("internalToken");
```

Nếu cần kiểm tra giá trị object, hãy assert trực tiếp entry hoặc kiểm tra thuộc tính của object:

```java
assertThat(mvc.get().uri("/accounts/{id}", 42L))
        .model()
        .hasEntrySatisfying("account", value -> {
            assertThat(value).isInstanceOf(Account.class);
            Account account = (Account) value;
            assertThat(account.getId()).isEqualTo(42L);
            assertThat(account.getDisplayName()).isEqualTo("Mai Nguyen");
        });
```

Nếu test chỉ quan tâm controller đưa object đúng vào model, không cần render template thật. Nếu muốn xác nhận response HTML, cần cấu hình view technology để view có thể render trong môi trường MockMvc và assert nội dung response. Hai mục tiêu đó khác nhau: model assertion xác nhận dữ liệu phía server, còn body assertion xác nhận nội dung được render ra response.

## Kiểm tra model không có lỗi validation

`ModelAssert` hỗ trợ kiểm tra lỗi validation được gắn với model attribute. Khi controller trả lại form sau khi bind và validate thành công, có thể xác nhận attribute không có lỗi:

```java
assertThat(mvc.post().uri("/accounts")
                .param("displayName", "Mai Nguyen")
                .param("email", "mai@example.test"))
        .hasStatusOk()
        .hasViewName("accounts/confirm")
        .model()
        .doesNotHaveErrors()
        .doesNotHaveAttributeErrors("accountForm");
```

`doesNotHaveErrors()` kiểm tra model không có binding/validation errors. `doesNotHaveAttributeErrors("accountForm")` chỉ tập trung vào attribute được chỉ định. Dùng assertion hẹp khi model có thể chứa một attribute khác với lỗi hợp lệ trong cùng response.

## Kiểm tra BindingResult và field errors

Khi controller nhận form qua `@ModelAttribute` và có `BindingResult` ngay sau object, Spring đặt binding result vào model dưới key có prefix `BindingResult.MODEL_KEY_PREFIX` cùng tên attribute. `MockMvcTester` cung cấp `extractingBindingResult(...)` để kiểm tra các lỗi đó theo kiểu AssertJ.

Ví dụ controller:

```java
@PostMapping("/accounts")
String create(
        @Valid @ModelAttribute("accountForm") AccountForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return "accounts/new";
    }

    accountService.create(form);
    return "redirect:/accounts";
}
```

Test xác nhận lỗi gắn đúng field:

```java
assertThat(mvc.post().uri("/accounts")
                .param("displayName", "Mai")
                .param("email", "not-an-email"))
        .hasStatusOk()
        .hasViewName("accounts/new")
        .model()
        .hasAttributeErrors("accountForm")
        .extractingBindingResult("accountForm")
        .hasFieldErrors("email");
```

Các assertion chuyên biệt cho `BindingResult` gồm:

| Assertion | Ý nghĩa |
|---|---|
| `model().hasErrors()` | Model có ít nhất một binding result chứa lỗi |
| `model().doesNotHaveErrors()` | Model không có lỗi |
| `model().hasAttributeErrors("accountForm")` | Attribute được chỉ định có lỗi |
| `model().doesNotHaveAttributeErrors("accountForm")` | Attribute được chỉ định không có lỗi |
| `model().extractingBindingResult("accountForm").hasErrorsCount(2)` | Binding result có đúng số lỗi |
| `.hasFieldErrors("email", "displayName")` | Các field được nêu có lỗi |
| `.hasOnlyFieldErrors("email")` | Chỉ field email có lỗi, không có lỗi khác |
| `.hasFieldErrorCode("email", "Email")` | Field có lỗi với error code được chỉ định |

`hasFieldErrors(...)` xác nhận các field được nêu có lỗi, còn `hasOnlyFieldErrors(...)` xác nhận danh sách field lỗi chính xác và không có lỗi khác. Dùng `hasOnlyFieldErrors` khi số lượng và tập field lỗi là một phần của hành vi mà test cần bảo vệ.

Lỗi binding do chuyển đổi kiểu và lỗi Bean Validation có thể cùng xuất hiện dưới dạng field errors. Nếu cần phân biệt `age=abc` với `age=-1`, có thể truy cập `BindingResult` gốc qua `MvcTestResult` và kiểm tra `FieldError#isBindingFailure()`, hoặc dùng API `MvcResult` như phần dưới.

## Kiểm tra view name

Với controller trả về tên view, `hasViewName(...)` kiểm tra logical view name trong `ModelAndView`:

```java
assertThat(mvc.get().uri("/accounts/new"))
        .hasStatusOk()
        .hasViewName("accounts/new");
```

Có thể dùng `viewName()` khi muốn tiếp tục với các phép so sánh chuỗi của AssertJ:

```java
assertThat(mvc.get().uri("/accounts/new"))
        .viewName()
        .startsWith("accounts/");
```

View name là tên logic do controller trả về. Ví dụ `accounts/detail` có thể được `ViewResolver` ánh xạ tới template hoặc JSP tương ứng. Assertion này không chứng minh file template tồn tại hay trình duyệt hiển thị trang đúng pixel. Muốn kiểm tra nội dung đã render, hãy assert response body; muốn kiểm tra trải nghiệm thực tế trên browser, cần end-to-end test.

Nếu controller trả `@ResponseBody`, `ResponseEntity` hoặc một DTO từ `@RestController`, thường sẽ không có `ModelAndView`. Trong trường hợp đó, không gọi `hasViewName()` hoặc `model()`; hãy kiểm tra status, headers và response body.

## Kiểm tra redirect, forward và flash attributes

Sau khi xử lý thành công một form, controller thường redirect để tránh gửi lại dữ liệu khi người dùng refresh trang:

```java
@PostMapping("/accounts")
String create(
        @Valid @ModelAttribute("accountForm") AccountForm form,
        BindingResult errors,
        RedirectAttributes redirectAttributes) {

    if (errors.hasErrors()) {
        return "accounts/new";
    }

    Account created = accountService.create(form);
    redirectAttributes.addFlashAttribute(
            "notice", "Account created successfully");
    return "redirect:/accounts/" + created.getId();
}
```

MockMvcTester có thể xác nhận status redirect, URL đích và flash attributes:

```java
assertThat(mvc.post().uri("/accounts")
                .param("displayName", "Mai Nguyen")
                .param("email", "mai@example.test"))
        .hasStatus3xxRedirection()
        .hasRedirectedUrl("/accounts/42")
        .flash()
        .containsEntry("notice", "Account created successfully");
```

`flash()` trả về map assertion trên output flash attributes được lưu trong quá trình xử lý request. Nó phù hợp để kiểm tra thông báo một lần được gửi qua redirect. Flash attribute khác với query parameter và khác với model attribute thông thường của request hiện tại.

Nếu controller dùng forward thay vì redirect, có thể kiểm tra URL forward:

```java
assertThat(mvc.get().uri("/legacy/accounts"))
        .hasStatusOk()
        .hasForwardedUrl("/accounts/list");
```

Redirect và forward có ngữ nghĩa khác nhau. Redirect yêu cầu client gửi request mới đến URL đích; forward chuyển tiếp request bên trong server. Không dùng assertion redirect cho controller trả `forward:` hoặc ngược lại.

## Kiểm tra handler đã xử lý request

Một URL có thể được xử lý bởi nhiều mapping với điều kiện khác nhau. `handler()` cho phép xác nhận controller hoặc handler method thực sự được gọi:

```java
assertThat(mvc.get().uri("/accounts/{id}", 42L))
        .handler()
        .hasType(AccountController.class);
```

Có thể xác nhận method handler cụ thể:

```java
assertThat(mvc.get().uri("/accounts/{id}", 42L))
        .handler()
        .method()
        .hasName("detail");
```

Kiểm tra handler hữu ích khi ứng dụng có route chồng lấn, controller kế thừa hoặc nhiều mapping theo HTTP method, `params`, `headers`, `consumes` và `produces`. Nếu chỉ assert response body, hai handler khác nhau có thể tình cờ trả nội dung giống nhau và test không phát hiện việc request được dispatch sai.

## Kiểm tra request và session attributes

Model thuộc `ModelAndView`, còn request/session attributes thuộc Servlet API. Khi cần xác nhận dữ liệu được đặt vào request hoặc session, giữ `MvcTestResult` rồi đọc mock request:

```java
MvcTestResult result = mvc.get()
        .uri("/wizard/step")
        .sessionAttr("wizardId", "W-42")
        .exchange();

assertThat(result).hasStatusOk();
assertThat(result.getRequest().getAttribute("currentStep"))
        .isEqualTo("review");
assertThat(result.getRequest().getSession(false))
        .isNotNull();
assertThat(result.getRequest().getSession(false)
        .getAttribute("wizardId"))
        .isEqualTo("W-42");
```

Ở đây `sessionAttr(...)` thiết lập session attribute đầu vào cho request test. Nếu controller thay đổi session, hãy kiểm tra session sau khi request hoàn tất. Dùng `getSession(false)` khi muốn xác nhận request đã có session mà không vô tình tạo session mới trong lúc assertion.

Đối với request attribute, cần phân biệt attribute do test gửi vào với attribute được interceptor/filter/controller đặt trong quá trình xử lý. Nếu đang kiểm tra giá trị do server tạo, không thiết lập cùng key đó bằng `.requestAttr(...)` trước khi thực hiện request, vì test sẽ không còn chứng minh được server đã tạo giá trị.

## Dùng MvcTestResult để kiểm tra chi tiết

`MvcTestResult` là kết quả của một lần thực thi request. Nó cho phép lấy `MvcResult` nền, request và response. Khi assertion chuyên biệt chưa đáp ứng nhu cầu, có thể truy cập `ModelAndView` trực tiếp:

```java
MvcTestResult result = mvc.get()
        .uri("/accounts/{id}", 42L)
        .exchange();

MvcResult mvcResult = result.getMvcResult();
ModelAndView modelAndView = mvcResult.getModelAndView();

assertThat(modelAndView).isNotNull();
assertThat(modelAndView.getViewName()).isEqualTo("accounts/detail");
assertThat(modelAndView.getModel()).containsKey("account");
```

Để đọc binding result trong model:

```java
BindingResult bindingResult = (BindingResult) modelAndView.getModel().get(
        BindingResult.MODEL_KEY_PREFIX + "accountForm");

assertThat(bindingResult).isNotNull();
assertThat(bindingResult.getFieldErrors("email")).isNotEmpty();
```

Nếu controller trả response body thay vì view, `getModelAndView()` có thể là `null`. Hãy kiểm tra trước khi đọc model. Với response body, dùng `result.getResponse().getContentAsString()` hoặc các assertion `bodyText()`/`bodyJson()` của MockMvcTester.

Nếu handler ném exception đã được `HandlerExceptionResolver` xử lý, request vẫn có thể có một response hoàn chỉnh để assert. Nếu exception không được xử lý và request thất bại bất ngờ, `MvcTestResult` có `getUnresolvedException()`; khi đó không thể đọc một kết quả MVC hoàn chỉnh như thể request đã kết thúc bình thường.

## Kết hợp assertion MockMvc cũ

`MockMvcTester` không loại bỏ toàn bộ API `MockMvc`. Nếu dự án đã có `RequestBuilder`, `ResultMatcher` hoặc `ResultHandler` riêng, có thể tích hợp chúng:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

assertThat(mockMvc.perform(get("/accounts/{id}", 42L)))
        .matches(status().isOk())
        .hasViewName("accounts/detail");
```

Hoặc dùng `.matches(...)` để áp dụng `ResultMatcher` cũ lên kết quả được tạo bởi request builder của `MockMvcTester`:

```java
assertThat(mvc.get().uri("/accounts/{id}", 42L))
        .matches(status().isOk())
        .hasViewName("accounts/detail");
```

Với custom `ResultHandler`, dùng `.apply(...)`. Cách tích hợp này hữu ích khi chuyển dần từ `mockMvc.perform(...).andExpect(...)` sang AssertJ mà không phải viết lại ngay toàn bộ matcher dùng chung.

## Request bất đồng bộ

Nếu controller xử lý bất đồng bộ, `exchange()` chờ request hoàn tất trước khi trả kết quả để assertion đọc một response đã ổn định. Mặc định thời gian chờ là 10 giây; có thể chỉ định timeout cho request:

```java
assertThat(mvc.get().uri("/reports/42")
                .exchange(Duration.ofSeconds(5)))
        .hasStatusOk()
        .hasViewName("reports/detail");
```

Nếu cần tự quản lý vòng đời request async đang chạy, dùng `asyncExchange()` và xử lý trạng thái async theo mục tiêu test. Không dùng `exchange()` với timeout quá ngắn nếu handler cần thời gian hoàn tất hợp lý; cũng không tăng timeout để che một xử lý bị treo.

## Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy `MockMvcTester` | Spring Framework cũ hơn 6.2 hoặc thiếu `spring-test` | Dùng Spring Framework 6.2 trở lên và thêm test dependency phù hợp |
| `assertThat(...)` không có assertion MVC | Thiếu AssertJ hoặc builder không đến từ `MockMvcTester` | Kiểm tra AssertJ trên test classpath và kiểu request builder |
| Không có `ModelAndView` | Controller trả `@ResponseBody`, `ResponseEntity` hoặc `@RestController` | Assert response body; không kiểm tra view/model của response body |
| Model thiếu attribute | Controller không thêm attribute, sai tên model attribute hoặc nhánh xử lý khác được gọi | Kiểm tra `Model`, `@ModelAttribute` và handler thực tế |
| Binding result không được tìm thấy | Sai tên attribute hoặc controller không khai báo `BindingResult` đúng vị trí | Dùng đúng tên `@ModelAttribute` và đặt `BindingResult` liền sau object |
| View name đúng nhưng HTML không đúng | Test chỉ kiểm tra logical view name | Kiểm tra response body đã render hoặc bổ sung browser test |
| Flash attribute không xuất hiện | Controller dùng model attribute thường thay vì `addFlashAttribute`, hoặc request không redirect | Kiểm tra nhánh redirect và dùng `RedirectAttributes` |
| Handler assertion thất bại | Mapping khác được chọn do method, path, params hoặc headers | Kiểm tra điều kiện `@RequestMapping` và request gửi vào |
| Session assertion tạo ra kết quả giả | Test gọi `getSession()` làm phát sinh session mới | Dùng `getSession(false)` để chỉ đọc session đã có |

## Cách chọn assertion theo mục tiêu

| Điều cần chứng minh | Assertion nên dùng |
|---|---|
| Request trả đúng status | `hasStatusOk()`, `hasStatus(...)` |
| Controller chọn đúng logical view | `hasViewName(...)` hoặc `viewName()` |
| Model có dữ liệu cần cho view | `model().containsKey(...)`, `containsEntry(...)` |
| Model không có validation errors | `model().doesNotHaveErrors()` |
| Form có lỗi đúng field | `model().extractingBindingResult(...).hasFieldErrors(...)` |
| Redirect đến đúng URL | `hasRedirectedUrl(...)` |
| Có flash message sau redirect | `flash().containsEntry(...)` |
| Request được controller dự kiến xử lý | `handler().hasType(...)` hoặc `handler().method().hasName(...)` |
| Server đặt đúng request/session attribute | `MvcTestResult#getRequest()` và Servlet API |
| Cần đọc chi tiết ModelAndView | `MvcTestResult#getMvcResult()` |

Khi kiểm thử controller trả view, hãy xác nhận status, logical view name và các model attributes quan trọng. Với form, thêm assertion cho `BindingResult`; với luồng PRG, kiểm tra redirect URL và flash attributes. Những assertion này cho biết controller đã chuẩn bị đúng dữ liệu phía server và chọn đúng kết quả điều hướng trước khi người dùng nhìn thấy trang.
