# @SessionAttributes, SessionStatus và khác biệt với @SessionAttribute trong Spring MVC

> **Bối cảnh:** Spring Web MVC theo **Servlet stack**, Java 17+ và Spring Boot 3.x/Spring Framework 6.x. Bài học phân biệt ba thành phần dễ nhầm vì tên giống nhau: **`@SessionAttributes`** lưu tạm các **model attributes** qua nhiều HTTP request của một luồng làm việc; **`SessionStatus`** đánh dấu kết thúc luồng ấy và yêu cầu dọn những attribute đã quản lý; **`@SessionAttribute`** đọc một **session attribute đã tồn tại** như tham số handler. Cả ba gắn với HTTP session nhưng **không đồng nghĩa**, cũng không thay thế bảo mật, validation hoặc lưu trữ bền vững.

## 1. Vì sao cần trạng thái giữa các request?

HTTP vốn không tự mang một Java object từ request này sang request tiếp theo. Một biểu mẫu nhiều bước có thể yêu cầu:

1. Người dùng điền **tên** ở bước 1.
2. Người dùng điền **thành phố** ở bước 2.
3. Người dùng xác nhận cả hai và hoàn tất.
4. Server xóa bản nháp tạm, không để dữ liệu cũ xuất hiện khi bắt đầu quy trình mới.

Nếu mỗi request chỉ có các trường của bước hiện tại thì cần một nơi giữ **draft tạm thời**. Một lựa chọn trong Spring MVC là model attribute được đưa vào **HTTP session** nhờ `@SessionAttributes`.

```text
Client (cookie JSESSIONID)
     |
GET /wizard/start
     | Controller tạo model["draft"]
     v
HTTP Session: draft(name="", city="")
     |
POST /wizard/name -> draft.name="Lan"
     |
POST /wizard/city -> draft.city="Da Nang"
     |
POST /wizard/finish
     | hoàn tất nghiệp vụ
     | SessionStatus.setComplete()
     v
HTTP Session: không còn draft thuộc controller workflow
     |
GET /wizard/start -> tạo draft mới
```

Cookie session (thường là `JSESSIONID` với cấu hình Servlet mặc định) giúp server nhận biết nhiều request đến từ cùng một HTTP session. Không gửi cookie tiếp thì server có thể xem request là session mới. Thuộc tính session không phải biến toàn cục giữa mọi người dùng.

**Khái niệm cốt lõi:**
- **Request scope:** dữ liệu chỉ tồn tại trong quá trình xử lý một request.
- **Model:** map dữ liệu controller đưa sang view; bình thường **không tự bền** qua các request.
- **HTTP session:** nơi giữ thuộc tính liên kết với một phiên phía server (tùy hạ tầng triển khai).
- **Controller conversation:** chuỗi request phục vụ một tác vụ tạm thời, ví dụ wizard; `@SessionAttributes` dành cho loại dữ liệu này.

## 2. So sánh ba API ngay từ đầu

| API | Khai báo ở đâu? | Nó làm gì? | Có tự lưu hay tự dọn không? |
| --- | --- | --- | --- |
| `@SessionAttributes("draft")` | **Trên class** `@Controller` / `@RestController` | Khai báo model attribute tên `draft` cần được lưu vào session giữa các request của controller workflow | Spring MVC tự đồng bộ model attribute phù hợp vào session; dọn khi conversation được đánh dấu complete |
| `SessionStatus status` | **Tham số handler method** | Cung cấp `setComplete()` và `isComplete()` cho lifecycle của workflow | `setComplete()` kích hoạt Spring MVC dọn **các attribute được `@SessionAttributes` quản lý** |
| `@SessionAttribute(name="tenantCode")` | **Trên tham số handler method** | Đọc một attribute đã nằm trong HTTP session | **Không tự tạo, lưu hay dọn** attribute; chỉ resolve giá trị để truyền vào tham số |
| `HttpSession` | Tham số handler method / Servlet API | Đọc, ghi, xóa attribute trực tiếp; có thể invalidate toàn bộ session | Chính code hoặc container/session infrastructure quản lý |

**Đừng nhầm số nhiều và số ít:**

- **`@SessionAttributes` (số nhiều):** cơ chế **model → session** theo phạm vi controller và lifecycle tác vụ.
- **`@SessionAttribute` (số ít):** cơ chế **session → tham số method** cho một giá trị đã có.
- **`SessionStatus`:** tín hiệu **hoàn tất** để controller thôi duy trì model attribute tạm trong session.

Chúng không phải cách khai báo “bean scope=session”. Ví dụ `@SessionScope` là cơ chế của Spring container để quản lý bean theo session; bài này tập trung vào **Spring MVC handler model attributes**.

## 3. `@SessionAttributes`: khai báo trên controller và lưu model attribute

Cú pháp tối thiểu:

```java
@Controller
@SessionAttributes("draft")
public class WizardController {

    @GetMapping("/wizard")
    public String start(Model model) {
        model.addAttribute("draft", new DraftForm());
        return "wizard-form";
    }
}
```

Đây là **method minh họa**, cần tự định nghĩa `DraftForm` và view `wizard-form`. Vai trò từng phần:

- `@SessionAttributes("draft")` khai báo controller dùng một **model attribute tên `draft`** xuyên nhiều request.
- `model.addAttribute("draft", new DraftForm())` đưa object vào Model.
- Sau khi method hoàn thành theo pipeline Spring MVC, Spring nhận ra attribute đã khai báo và giữ nó ở HTTP session.
- Ở request sau, Spring khôi phục model attribute từ session để handler cùng workflow tiếp tục sử dụng nó.

`@SessionAttributes` không đồng nghĩa “lấy mọi local variable của controller cho vào session”. Chỉ những **model attributes phù hợp theo tên hoặc kiểu** được khai báo mới tham gia.

### 3.1. Khai báo theo tên và/hoặc kiểu

```java
@SessionAttributes(names = {"draft", "addressForm"})
class WizardController {
    // ...
}
```

Hoặc:

```java
@SessionAttributes(types = DraftForm.class)
class WizardController {
    // ...
}
```

Các snippet trên là **hai phương án riêng**, không đặt trên cùng một class. Annotation hỗ trợ `names`/`value` và `types`:

- Dùng **tên** khi chỉ muốn một số model attributes cụ thể tham gia conversation.
- Dùng **kiểu** khi chủ đích muốn model attributes thuộc type tương ứng được lưu. Cẩn thận nếu controller có nhiều attributes cùng type nhưng không cần persistence: khai báo quá rộng có thể lưu nhiều dữ liệu hơn mong muốn.
- Có thể kết hợp name/type theo hợp đồng Spring; hãy tránh chọn quá rộng vì có thể tạo session không cần thiết, tăng dung lượng hoặc giữ dữ liệu nhạy cảm lâu hơn.

**Phạm vi:** annotation nằm ở class của **handler controller**. Spring chỉ kích hoạt cơ chế conversation khi xử lý controller đó; không phải lệnh “mọi controller đều tự động lưu `draft`”. Tuy nhiên HTTP session là kho chứa dùng chung trong cùng phiên, nên nếu nhiều controller vô tình dùng **cùng session attribute name**, có thể đụng nhau. Dùng tên đủ đặc thù cho workflow.

### 3.2. Lấy lại attribute bằng `@ModelAttribute`

```java
@PostMapping("/wizard/name")
public String saveName(
        @ModelAttribute("draft") DraftForm draft,
        BindingResult bindingResult) {
    // Spring tìm model attribute "draft", gồm giá trị đã khôi phục từ session.
    // Có thể thực hiện binding/validation theo quy tắc MVC.
    return "wizard-next";
}
```

Đây là **method minh họa** và yêu cầu template thích hợp. Không phải mỗi request Spring lại xây object mới nếu đã có session attribute tương ứng. `@ModelAttribute("draft")` là cách truy cập đối tượng của workflow và tham gia cơ chế binding.

**Cảnh báo an toàn:** property binding từ client có thể gán các field của bean mutable nếu method không giới hạn đầu vào. Không lưu entity chứa `isAdmin`, `ownerId`, `price` hoặc quan hệ JPA rộng chỉ vì `@SessionAttributes` tiện. Dùng form DTO chỉ chứa input hợp đồng, kiểm tra quyền và/hoặc cấu hình `@InitBinder#setAllowedFields`.

### 3.3. Tạo model attribute khi chưa có trong session

Để không phải khởi tạo thủ công tại nhiều handler:

```java
@ModelAttribute("draft")
public DraftForm initializeDraft() {
    return new DraftForm();
}
```

Method `@ModelAttribute` kiểu này được gọi để đóng góp giá trị khi model chưa có attribute đó; ở request có `draft` đã được phục hồi từ session, nó không nên ghi đè draft đã tồn tại. Đây là pattern phổ biến cho form wizard; xem ví dụ hoàn chỉnh ở mục 8.

**Cần phân biệt thiếu khởi tạo:** nếu handler khai báo `@ModelAttribute("draft")` và Spring kỳ vọng attribute trong session mà không có, behavior có thể phụ thuộc cách attribute được khai báo, có hay không initializer, constructor binding và luồng method. Đừng dựa vào việc một session rỗng luôn tự sinh đúng trạng thái; thiết kế bước khởi tạo rõ ràng và test request đi tắt/đánh dấu hoàn tất.

## 4. `SessionStatus`: đánh dấu hoàn tất và dọn attribute của workflow

Spring MVC cho phép chèn `SessionStatus` trực tiếp vào handler method:

```java
@PostMapping("/wizard/finish")
public String finish(
        @ModelAttribute("draft") DraftForm draft,
        SessionStatus sessionStatus) {

    // Đã xác thực/ghi dữ liệu nghiệp vụ thành công.
    sessionStatus.setComplete();
    return "redirect:/wizard/done";
}
```

Đây là **snippet minh họa**, không chạy độc lập. `setComplete()` có nghĩa **conversation hiện tại đã hoàn tất**; sau khi xử lý, Spring dọn những attributes do `@SessionAttributes` của controller quản lý. Đừng hiểu nhầm method này là:

- `HttpSession.invalidate()`: hủy cả HTTP session, kéo theo các session attributes khác và session identity.
- `session.removeAttribute("anyKey")`: xóa một key tùy ý trong servlet session.
- `model.clear()`: xóa mọi attribute tạm thời trong Model tại thời điểm method.
- `userService.save(...)`: lưu dữ liệu vĩnh viễn vào database.

`SessionStatus` là interface `org.springframework.web.bind.support.SessionStatus`, có:

| Method | Ý nghĩa |
| --- | --- |
| `void setComplete()` | Đánh dấu conversation đã xong để MVC thực hiện cleanup |
| `boolean isComplete()` | Xem handler hiện tại đã đánh dấu complete chưa |

**Quan trọng về thứ tự:** gọi `setComplete()` **sau khi** kiểm tra validation, quyền và commit/save nghiệp vụ thành công. Nếu validation fail rồi gọi complete, người dùng có thể mất dữ liệu draft và không thể tiếp tục đúng quy trình. Nếu database write thất bại, không đánh dấu complete trước khi kiểm tra kết quả.

### 4.1. `setComplete()` dọn những gì?

Với `@SessionAttributes("draft")`, Spring MVC xóa dữ liệu `draft` do conversation manager theo dõi trong session. Nó **không tự dọn** các session keys như `tenantCode`, giỏ hàng được tạo trực tiếp qua `HttpSession.setAttribute("cart", ...)`, hoặc trạng thái đăng nhập do framework bảo mật quản lý.

Nếu controller còn dùng `@SessionAttributes("shippingForm")`, cùng controller có thể dọn attribute phù hợp với annotation đó khi session status được complete. Đừng đặt nhiều workflow độc lập cần lifecycle khác nhau dưới một cấu hình `@SessionAttributes` quá rộng nếu một lần `setComplete()` có thể làm mất dữ liệu của luồng khác.

### 4.2. `SessionStatus` không phải trạng thái đăng nhập

Câu lệnh:

```java
status.setComplete();
```

**không tương đương logout**. Đăng nhập/đăng xuất do cơ chế security và session management điều khiển. Với Spring Security, logout thường dọn SecurityContext và có thể invalidate session theo cấu hình; không sử dụng `SessionStatus` để thay thế logout.

### 4.3. Sau complete, gọi workflow lần nữa có điều gì xảy ra?

Khi handler controller cần draft trở lại, Spring có thể **tạo một draft mới** nếu đã khai báo `@ModelAttribute("draft")` initializer. Vì vậy sau POST finish và GET start mới, dữ liệu có thể trở về chuỗi rỗng. Đây là cách thông thường để tránh hiển thị nhầm bản nháp cũ. Cần có test xác nhận tạo mới thực sự, nhất là khi đồng thời có một nơi khác ghi cùng key session.

## 5. `@SessionAttribute`: đọc giá trị đã có trong session

Annotation **số ít** được đặt trên **tham số method**, không trên class:

```java
@GetMapping("/current-tenant")
@ResponseBody
public String currentTenant(
        @SessionAttribute(name = "tenantCode", required = false)
        String tenantCode) {

    return tenantCode == null ? "missing" : tenantCode;
}
```

Giả sử một filter, authentication flow hoặc code ứng dụng đã làm:

```java
session.setAttribute("tenantCode", "tenant-a");
```

Khi request mang cùng HTTP session, Spring resolve attribute đó làm đối số `tenantCode`. Đây chỉ là một giá trị đọc được trong session, **không cần** class-level `@SessionAttributes("tenantCode")`.

Các tùy chọn:

- `name` hoặc `value`: tên session key.
- `required = true` (mặc định): thiếu attribute có thể phát sinh exception khi resolve method argument.
- `required = false`: cho phép giá trị không tồn tại; với kiểu reference như `String`, method có thể nhận `null`, nên kiểm tra trước khi dùng.
- Có thể dùng `Optional<T>` nếu muốn biểu diễn có/không theo kiểu mạnh hơn.

Ví dụ:

```java
@GetMapping("/locale-preference")
@ResponseBody
public String preferred(
        @SessionAttribute(name = "preferredLanguage", required = false)
        String language) {

    return language == null ? "default" : language;
}
```

**Khi nào dùng `@SessionAttribute`?** Khi một attribute được quản lý **ngoài controller conversation** và controller chỉ cần tham chiếu nó: thông tin do filter đặt, một setting theo session, hoặc metadata lưu bởi phần khác của ứng dụng. Nếu cần thêm/xóa attribute, có thể lấy `HttpSession` hoặc `WebRequest` theo hợp đồng tương ứng; không cần cố ép `@SessionAttributes` vào trường hợp đó.

### 5.1. Thiếu required session attribute

```java
@GetMapping("/must-have-tenant")
@ResponseBody
public String mustHave(
        @SessionAttribute("tenantCode") String tenantCode) {
    return tenantCode;
}
```

Nếu không có session hoặc không có key `tenantCode`, Spring MVC có thể ném exception do thiếu required session attribute trước khi method được gọi. HTTP status và body cụ thể do resolver/error configuration quyết định; **không khẳng định mọi phiên bản trả một body y hệt nhau**. Với dữ liệu thực sự tùy chọn, viết `required=false` hoặc `Optional` và xử lý nhánh vắng rõ ràng.

### 5.2. `@SessionAttribute` có sửa session không?

Không tự động. Đối số chỉ đưa một giá trị đã tồn tại cho method. Với reference đến một mutable object, code Java có thể **thay đổi chính object** đó; thế nhưng đó là side effect của object/session, **không phải cơ chế model conversation tự động của annotation**. Với dữ liệu persistent cần kiểm soát, ưu tiên immutable value hoặc service có logic ghi rõ ràng.

## 6. So sánh trực tiếp bằng một tình huống

Giả sử cùng session chứa:

```text
draft       = DraftForm("Lan", "Da Nang")
tenantCode  = "demo-tenant"
cart        = [Book-1, Book-2]
```

| Thao tác | Kết quả |
| --- | --- |
| Handler thuộc `@SessionAttributes("draft")` nhận `@ModelAttribute("draft") DraftForm` | Được tham gia lifecycle model/session; có thể đọc và cập nhật draft |
| Handler nhận `@SessionAttribute("tenantCode") String` | Chỉ đọc value `demo-tenant` vào method argument |
| `SessionStatus.setComplete()` của wizard controller | Xóa `draft` đã quản lý, không chủ động xóa `tenantCode` hoặc `cart` |
| `session.removeAttribute("tenantCode")` | Xóa key `tenantCode` mà không cần kết thúc draft |
| `session.invalidate()` | Hủy toàn bộ HTTP session, tất cả attributes trong session đó không còn được dùng |

**Tóm lại:** số nhiều quản lý **conversation model state**; số ít đọc **existing session state**; `SessionStatus` kết thúc conversation đã được quản lý. Không thay chúng cho nhau chỉ vì cùng liên quan `HttpSession`.

## 7. Khác biệt với những cơ chế gần giống

### 7.1. `@ModelAttribute` nhưng không có `@SessionAttributes`

```java
@PostMapping("/one-step")
public String submit(@ModelAttribute SimpleForm form) {
    return "done";
}
```

Thông thường form chỉ tồn tại trong vòng đời xử lý request hiện tại; Spring **không mặc định** giữ nó trong HTTP session cho các request kế tiếp. Muốn wizard cần lưu tạm, thêm cơ chế tương ứng (session conversation hoặc storage khác).

### 7.2. `RedirectAttributes.addFlashAttribute(...)`

```java
@PostMapping("/done")
public String done(RedirectAttributes redirects) {
    redirects.addFlashAttribute("notice", "Đã lưu");
    return "redirect:/summary";
}
```

Flash attribute phục vụ **truyền dữ liệu qua một redirect tới request kế tiếp**, thường cho thông báo thành công, không dành cho cả wizard nhiều bước kéo dài. Nền tảng có thể dùng session để mang flash data, nhưng vòng đời của flash không bằng `@SessionAttributes`.

### 7.3. `HttpSession` trực tiếp

```java
@GetMapping("/manual-session")
@ResponseBody
public String manual(HttpSession session) {
    session.setAttribute("pref", "compact");
    return (String) session.getAttribute("pref");
}
```

Đây là code chủ động thao tác session key. Dùng `HttpSession` nếu cần quản lý rõ key/TTL/invalidating/session metadata, nhưng nhớ kiểm soát kích thước và quyền. `SessionStatus` không xóa mặc định key `pref` ở ví dụ này nếu nó không phải managed session attribute của controller workflow.

### 7.4. `@SessionScope`

```java
@Component
@SessionScope
class ShoppingCart {
    // Bean theo scope session, không phải model attribute của wizard.
}
```

`@SessionScope` là cơ chế bean scope với proxy theo session trong Spring IoC; không phải annotation để bind Model sang session. Nếu ứng dụng chỉ cần shared state giữa controller/services trong một session, session-scoped bean có thể là một lựa chọn riêng, nhưng vẫn có vấn đề concurrency/serialization/session expiry.

## 8. Ví dụ hoàn chỉnh, chạy được: wizard và session attribute độc lập

Ví dụ Spring Boot 3.x, Java 17+ với duy nhất dependency **Spring Web** để giảm độ phức tạp. Không cần template engine hoặc database: các handler trả JSON nhưng vẫn là Spring MVC controller, nên có thể quan sát model/session lifecycle trực tiếp. Ví dụ cố tình không thêm Spring Security, dùng dữ liệu giả lập. Trong ứng dụng thật cần auth/CSRF phù hợp.

### 8.1. Chuẩn bị project

Tạo Maven Spring Boot 3.x project với dependency **Spring Web** tại [Spring Initializr](https://start.spring.io/). File `pom.xml` có starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Đây là dependency fragment; parent/plugin/metadata do Initializr chuẩn bị. Đặt Java source sau ở `src/main/java/com/example/demo/DemoApplication.java`. Toàn file chỉ có một `public class`; những class khác package-private hợp lệ theo Java 17.

### 8.2. Mã Java đầy đủ

```java
package com.example.demo;

import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.SessionAttribute;
import org.springframework.web.bind.annotation.SessionAttributes;
import org.springframework.web.bind.support.SessionStatus;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

class DraftForm {
    private String name = "";
    private String city = "";

    public DraftForm() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}

@Controller
@RequestMapping("/wizard")
@SessionAttributes("draft")
class WizardController {

    // Chỉ tạo draft mới khi chưa có attribute khôi phục từ session.
    @ModelAttribute("draft")
    public DraftForm initializeDraft() {
        return new DraftForm();
    }

    @GetMapping("/start")
    @ResponseBody
    public Map<String, String> start(
            @ModelAttribute(value = "draft", binding = false)
            DraftForm draft) {

        return snapshot("started", draft);
    }

    @GetMapping("/state")
    @ResponseBody
    public Map<String, String> state(
            @ModelAttribute(value = "draft", binding = false)
            DraftForm draft) {

        return snapshot("in-progress", draft);
    }

    @PostMapping(path = "/name",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    @ResponseBody
    public Map<String, String> name(
            @ModelAttribute(value = "draft", binding = false)
            DraftForm draft,
            @RequestParam("name") String name) {

        draft.setName(name);
        return snapshot("name-set", draft);
    }

    @PostMapping(path = "/city",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    @ResponseBody
    public Map<String, String> city(
            @ModelAttribute(value = "draft", binding = false)
            DraftForm draft,
            @RequestParam("city") String city) {

        draft.setCity(city);
        return snapshot("city-set", draft);
    }

    @PostMapping("/finish")
    @ResponseBody
    public Map<String, String> finish(
            @ModelAttribute(value = "draft", binding = false)
            DraftForm draft,
            SessionStatus status) {

        // Demo không ghi database. Trước khi complete trong hệ thống thật,
        // phải kiểm tra validation/quyền và commit nghiệp vụ thành công.
        Map<String, String> result = snapshot("complete", draft);
        status.setComplete();
        return result;
    }

    @PostMapping("/cancel")
    @ResponseBody
    public ResponseEntity<Map<String, String>> cancel(
            SessionStatus status) {

        status.setComplete();
        return ResponseEntity.ok(Map.of("stage", "cancelled"));
    }

    private static Map<String, String> snapshot(
            String stage, DraftForm draft) {
        Map<String, String> result = new LinkedHashMap<>();
        result.put("stage", stage);
        result.put("name", draft.getName());
        result.put("city", draft.getCity());
        return result;
    }
}

@RestController
@RequestMapping("/session/tenant")
class TenantController {

    @PostMapping("/set-demo")
    public Map<String, String> setDemo(HttpSession session) {
        // Chỉ minh họa server-side assignment; không lấy tenant từ client.
        session.setAttribute("tenantCode", "demo-tenant");
        return Map.of("tenant", "demo-tenant");
    }

    @GetMapping
    public Map<String, String> get(
            @SessionAttribute(name = "tenantCode", required = false)
            String tenantCode) {
        return Map.of("tenant",
                tenantCode == null ? "<missing>" : tenantCode);
    }

    @PostMapping("/clear")
    public Map<String, String> clear(HttpSession session) {
        session.removeAttribute("tenantCode");
        return Map.of("tenant", "<missing>");
    }
}
```

**Giải thích thiết kế:**

- `@Controller @SessionAttributes("draft")` đăng ký model attribute `draft` cho workflow. Nhờ `@ModelAttribute("draft")` initializer, request đầu có một `DraftForm` mới; request sau có session attr thì giữ cùng dữ liệu.
- `@ModelAttribute(value = "draft", binding = false)` ở handler tham gia việc lấy draft từ model/session **nhưng không tự bind mọi request parameter vào các property của nó**. Hai endpoint dùng `@RequestParam` và gán có chủ đích một property cho mỗi bước để minh họa tránh over-posting. Trong production còn phải validation và authorization, không chỉ copy chuỗi thô.
- Các method trả JSON nhờ `@ResponseBody`; dù controller không trả view template, MVC vẫn quản lý model/session attributes qua pipeline thông thường.
- `finish` và `cancel` nhận `SessionStatus` và gọi `setComplete()`; Spring dọn attribute `draft` của wizard. Object `DraftForm` trong handler vẫn dùng được khi tạo body result, nhưng sau request không được tiếp tục giữ trong managed session.
- `TenantController` không khai báo `@SessionAttributes`. Nó đưa session key `tenantCode` bằng `HttpSession.setAttribute(...)`, rồi đọc bằng **`@SessionAttribute` số ít**. `SessionStatus.setComplete()` của wizard không đụng vào key này.
- `Map.of(...)` không cam kết thứ tự JSON object fields, nên khi kiểm tra hãy so các field/values, không so thứ tự key. `snapshot` dùng `LinkedHashMap` để output quan sát dễ đọc.
- Spring MVC controllers là singleton theo mặc định; **không** đặt `private DraftForm currentDraft` lên controller để lưu user state, vì như vậy nhiều người dùng có thể nhìn thấy/chỉnh state của nhau. Draft phải đến từ session/model của request.

### 8.3. Chạy ứng dụng

Trong root project Maven:

```bash
# macOS hoặc Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
```

Server mặc định nghe `http://localhost:8080` nếu không đổi `server.port` hoặc context path.

### 8.4. Gửi nhiều request với **cùng session cookie**

Dùng `-c cookies.txt -b cookies.txt` ở **mọi request** để lưu và nạp cookie jar; nếu bỏ một trong hai, request mới có thể không thuộc cùng session. Lệnh bên dưới dành cho Bash; PowerShell có thể dùng `curl.exe` và gộp mỗi lệnh trên một dòng.

**Bước 1 — Khởi tạo draft:**

```bash
curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/wizard/start
```

JSON body:

```json
{"stage":"started","name":"","city":""}
```

**Bước 2 — Chỉ ghi tên:**

```bash
curl -sS -c cookies.txt -b cookies.txt \
  -X POST http://localhost:8080/wizard/name \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=Lan'
```

JSON:

```json
{"stage":"name-set","name":"Lan","city":""}
```

**Bước 3 — Chỉ ghi thành phố:**

```bash
curl -sS -c cookies.txt -b cookies.txt \
  -X POST http://localhost:8080/wizard/city \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'city=Da Nang'
```

JSON:

```json
{"stage":"city-set","name":"Lan","city":"Da Nang"}
```

**Bước 4 — Đọc bản nháp xuyên request:**

```bash
curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/wizard/state
```

JSON:

```json
{"stage":"in-progress","name":"Lan","city":"Da Nang"}
```

Tất cả dữ liệu đến từ **HTTP session**; request `GET /wizard/state` không cần query/body gửi lại tên/thành phố.

**Bước 5 — Tạo một session attribute ngoài workflow:**

```bash
curl -sS -c cookies.txt -b cookies.txt \
  -X POST http://localhost:8080/session/tenant/set-demo

curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/session/tenant
```

Bước đầu ghi `tenantCode=demo-tenant` vào HttpSession; bước sau dùng `@SessionAttribute` đọc lại. Body có dữ liệu:

```json
{"tenant":"demo-tenant"}
```

**Bước 6 — Hoàn tất wizard:**

```bash
curl -sS -c cookies.txt -b cookies.txt \
  -X POST http://localhost:8080/wizard/finish
```

JSON phản ánh giá trị ngay trước cleanup:

```json
{"stage":"complete","name":"Lan","city":"Da Nang"}
```

Sau response này, `SessionStatus.setComplete()` đã yêu cầu MVC dọn `draft`. Gọi lại:

```bash
curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/wizard/state
```

JSON sẽ là trạng thái **khởi tạo mới** theo initializer:

```json
{"stage":"in-progress","name":"","city":""}
```

Nhưng đọc `tenantCode` vẫn thấy giá trị đã đặt:

```bash
curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/session/tenant
```

```json
{"tenant":"demo-tenant"}
```

Điều này minh họa khác biệt quan trọng: **kết thúc wizard không xóa toàn HTTP session**.

Nếu gọi `POST /wizard/cancel`, body là `{"stage":"cancelled"}` và draft cũng được dọn. Sau đó, gọi `POST /session/tenant/clear` thì riêng `tenantCode` được xóa; `GET /session/tenant` trả `{"tenant":"<missing>"}`.

**Lưu ý:** các chuỗi JSON phía trên mô tả giá trị trường trong ví dụ Spring Boot/Jackson mặc định; các HTTP header hoặc thứ tự field có thể khác theo cấu hình. Nếu request mất cookie session, bạn có thể thấy dữ liệu bị reset sớm hơn vì đã chuyển session. Nếu Spring Security được thêm và CSRF protection bật, POST có thể trả 403 nếu không kèm token; ví dụ này không bật security.

## 9. Kiểm thử lifecycle bằng MockMvc

Có thể kiểm thử việc **cùng session giữ draft qua nhiều request** và **cleanup khi complete** thay vì chỉ nhìn body JSON. Tạo Spring Boot test dependency `spring-boot-starter-test` trong build và file `src/test/java/com/example/demo/WizardSessionTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WizardSessionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void draftSurvivesAcrossRequestsAndIsClearedOnComplete()
            throws Exception {

        var start = mvc.perform(get("/wizard/start"))
                .andExpect(status().isOk())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) start.getRequest().getSession(false);
        assertNotNull(session);
        assertNotNull(session.getAttribute("draft"));

        mvc.perform(post("/wizard/name")
                        .session(session)
                        .param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Lan"));

        mvc.perform(post("/wizard/city")
                        .session(session)
                        .param("city", "Da Nang"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.city").value("Da Nang"));

        mvc.perform(get("/wizard/state").session(session))
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.city").value("Da Nang"));

        mvc.perform(post("/wizard/finish").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.stage").value("complete"));

        assertNull(session.getAttribute("draft"));

        mvc.perform(get("/wizard/state").session(session))
                .andExpect(jsonPath("$.name").value(""))
                .andExpect(jsonPath("$.city").value(""));
    }
}
```

Đây là file test **riêng**, sử dụng JUnit 5 và MockMvc của Spring Boot 3.x. Nếu test framework đã được tùy biến filter/security, cần cấu hình thích hợp. Chạy:

```bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
```

Các assertions quan trọng:
- Sau GET start, session có `draft`.
- POST của step1/step2 với **chính `MockHttpSession`** giữ dữ liệu.
- Sau POST finish, session **không còn** `draft`.
- GET state tiếp theo tạo draft rỗng mới.

Một bài test khác hữu ích: đặt `tenantCode` trong cùng session trước khi finish, rồi xác nhận `getAttribute("tenantCode")` vẫn còn sau cleanup. Điều này kiểm tra `SessionStatus` chỉ xử lý managed session attributes.

## 10. Hạn chế và rủi ro trong ứng dụng production

### 10.1. HTTP session không phải database

Session có vòng đời riêng và có thể timeout, bị invalidate lúc logout, bị mất khi container restart nếu không có persistence phù hợp, hoặc được replicate/serialize trong hạ tầng phân tán. Nếu workflow phải tồn tại lâu, cần resume từ thiết bị khác hoặc yêu cầu audit, cân nhắc **server-side persistence** (database/cache với key an toàn) thay vì coi `@SessionAttributes` là nơi lưu bền vững.

Nếu chạy nhiều server instances, load balancer sticky sessions hoặc giải pháp session chia sẻ như Spring Session có thể cần thiết. Không mặc định session attribute nằm trong bộ nhớ JVM này tự xuất hiện ở JVM khác.

### 10.2. Không đặt mutable user state vào singleton controller

**Sai:**

```java
@Controller
class UnsafeController {
    private DraftForm draft = new DraftForm(); // Dùng chung giữa requests/users!
}
```

Controller thông thường là singleton bean. Field mutable như trên có nguy cơ rò dữ liệu giữa nhiều người dùng hoặc gây race condition. Đúng hơn là dùng request/model/session-bound data, với scope và lifecycle rõ ràng.

### 10.3. Nhiều tab và request đồng thời

Một session có thể được dùng bởi nhiều tab trình duyệt. Hai tab cùng mở wizard, cùng key `draft` có thể ghi đè dữ liệu của nhau. Ngoài ra, nhiều request đồng thời cập nhật một mutable object trong session có thể dẫn đến mất cập nhật; HTTP session **không** tự cung cấp transaction lock hoặc optimistic locking cho mọi thao tác.

Giải pháp tùy yêu cầu:
- Thiết kế một workflow/session tại một thời điểm nếu UX cho phép.
- Dùng unique **workflow ID** và storage riêng mỗi workflow (có TTL, quyền truy cập).
- Dùng concurrency control/transaction ở service hoặc persistence layer.
- Không sử dụng một mutable DraftForm session chung nếu sản phẩm hỗ trợ nhiều luồng chỉnh sửa song song.

### 10.4. Session fixation, cookies, CSRF và authorization

Không xem session ID hoặc việc có một attribute như bằng chứng duy nhất của quyền. Với web app dùng cookie session, cần TLS, `HttpOnly`, `Secure`, `SameSite` phù hợp; login/logout/session fixation protection do security configuration kiểm soát. `@SessionAttribute("tenantCode")` chỉ lấy giá trị đã có, không đảm bảo tenant đó được xác thực hay người dùng được phép truy cập mọi tài nguyên trong tenant.

Trong ví dụ `TenantController`, giá trị `tenantCode` được server gán là demo cố định. **Không** tạo một endpoint production cho phép client đổi tenant hay principal tùy ý rồi dùng giá trị đó để phân quyền; luôn xác minh từ identity/authorization service đáng tin cậy.

Các form POST/PUT/DELETE có tác dụng thay đổi trạng thái cần CSRF protection khi dùng cookie-based authentication. `SessionStatus.setComplete()` không tự kiểm tra CSRF hoặc ủy quyền.

### 10.5. Giảm dữ liệu nhạy cảm và giới hạn dung lượng

Tránh lưu password thô, access token tùy tiện, file upload lớn, JPA entity graph khổng lồ hoặc những object không thể serialize khi session replication yêu cầu. Session state nên nhỏ, có TTL phù hợp, chỉ giữ dữ liệu cần cho workflow. Nếu lưu object Java trong session cluster, loại object/cấu trúc có thể yêu cầu khả năng serialization theo cấu hình session store.

### 10.6. Validation và over-posting

Ở handler dùng `@ModelAttribute` có data binding, client có thể tự gửi các tham số ngoài UI, ví dụ `isAdmin=true`. Vì vậy:
- Ưu tiên **DTO riêng** cho wizard thay vì entity.
- Mỗi bước chỉ cho phép những trường tương ứng với hợp đồng.
- Nếu cần property binding mutable form, cân nhắc `@InitBinder("draft")` + `setAllowedFields(...)`, hoặc `@ModelAttribute(binding=false)` và gán field có chủ đích như demo.
- Kiểm tra Bean Validation và các ràng buộc nghiệp vụ trước khi gọi `setComplete()`.
- Authorization và kiểm tra ownership ở service vẫn bắt buộc; session object không tự đảm bảo quyền.

**Không nhầm:** validation kiểm tra giá trị hợp lệ; hạn chế binding kiểm soát field được gửi; authorization quyết định ai được phép thao tác tài nguyên.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Draft mất sau mỗi request | Client không gửi cùng session cookie, session timeout, session store không chia sẻ | Gửi cùng `JSESSIONID`/cookie jar, kiểm tra session config |
| Draft cũ vẫn xuất hiện sau finish | Quên `SessionStatus.setComplete()` hoặc handler finish không thuộc workflow mong đợi | Gọi `setComplete()` sau khi hoàn tất; test attribute cleanup |
| `setComplete()` không xóa `tenantCode` | Key đó không do `@SessionAttributes` quản lý | Dùng `HttpSession.removeAttribute` hoặc cơ chế owner phù hợp |
| Session bị xóa toàn bộ sau wizard | Code gọi `HttpSession.invalidate()` | Phân biệt invalidate với `SessionStatus.setComplete()` |
| `@SessionAttribute` nhận `null` | `required=false` và key chưa có/session khác | Kiểm tra null/Optional hoặc đảm bảo nơi tạo value |
| Thiếu attribute báo lỗi trước controller method | `@SessionAttribute` mặc định `required=true` | Dùng required=false khi optional, bảo đảm key khi required |
| Hai tab sửa lẫn draft | Cả hai tab cùng HttpSession và same attribute key | Dùng workflow ID riêng và transaction/concurrency policy |
| Request body có field lạ sửa draft | Mutable model attribute bị property-bound ngoài hợp đồng | DTO nhỏ, allowlist hoặc binding=false |
| Trang POST trả 403 | CSRF protection bật nhưng thiếu token | Xem Spring Security và form/cURL token |
| Lưu draft trong field controller | Singleton chia sẻ giữa users | Không lưu mutable state per-user trên controller |
| Logout không xảy ra khi finish | `SessionStatus` không điều khiển authentication | Dùng logout/security session management |
| Browser mới không thấy draft | Session khác nhau theo cookie/client | Đây là giới hạn theo HTTP session, không phải lỗi converter |
| Cùng key session bị dùng ở controller khác | Collision tên attribute | Đặt tên attribute rõ workflow, kiểm thử tích hợp |

### 11.1. Gỡ lỗi có hệ thống

1. Kiểm tra mọi request có cùng session cookie không (tránh log nguyên session ID trong log production).
2. Kiểm tra controller có `@SessionAttributes("draft")` đúng tên model attribute không.
3. Kiểm tra đã thêm `draft` vào Model hoặc có `@ModelAttribute("draft")` initializer chưa.
4. Kiểm tra handler có nhận `@ModelAttribute("draft")` và có data binding bị cấm/ngoài ý muốn không.
5. Kiểm tra `SessionStatus#setComplete()` có được gọi **trước thời điểm mong muốn** hay bị bỏ quên.
6. Nếu chỉ đọc key có sẵn, kiểm tra nơi nào làm `HttpSession.setAttribute(...)` và tên key dùng với `@SessionAttribute`.
7. Với ứng dụng nhiều instance, kiểm tra session persistence/replication, load balancing và serialization.
8. Viết MockMvc test nhiều request cùng session, kết thúc workflow rồi tạo lại draft; thêm test nhiều tab/concurrent updates nếu sản phẩm cần.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Muốn giữ object `draft` thuộc Model giữa bước 1 và bước 2 của cùng controller, dùng gì?

**Đáp án:** Class-level `@SessionAttributes("draft")` và xây dựng/phục hồi Model attribute tương ứng.

**Câu 2.** Muốn kết thúc form wizard và xóa đúng những model attributes do controller workflow quản lý?

**Đáp án:** Nhận `SessionStatus` trong handler và gọi `setComplete()` sau khi hoàn tất thành công.

**Câu 3.** `@SessionAttribute("preferredLanguage") String language` có tự tạo key khi thiếu không?

**Đáp án:** Không. Nó đọc session attribute có sẵn; mặc định `required=true` và thiếu key có thể gây lỗi argument resolution. Nếu optional, dùng `required=false` hoặc `Optional` và xử lý vắng mặt.

**Câu 4.** `SessionStatus.setComplete()` có logout user và xóa mọi session key không?

**Đáp án:** Không. Nó kết thúc conversation do `@SessionAttributes` quản lý, không invalidate toàn HTTP session hoặc logout.

**Câu 5.** Vì sao `private DraftForm draft` là field không an toàn trong `@Controller`?

**Đáp án:** Controller thường là singleton và field bị chia sẻ giữa người dùng/request, tạo race condition và rủi ro lộ dữ liệu.

**Câu 6.** Cùng một người dùng mở wizard ở hai tab có hai bản nháp độc lập không?

**Đáp án:** Không mặc định. Hai tab thường có chung session cookie và key, có thể chỉnh chung object. Nếu cần workflow song song, phải thiết kế key/storage riêng.

**Câu 7.** Sau khi `@SessionAttributes` giữ được `DraftForm`, có thể bỏ validation và authorization vì dữ liệu nằm server-side không?

**Đáp án:** Không. Client có thể gửi tham số để bind và người dùng vẫn phải được kiểm tra quyền theo tài nguyên/động tác; session persistence chỉ là cơ chế lưu trạng thái.

## 13. Tài liệu chính thức

- [Spring Framework — `@SessionAttributes`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html): lưu model attributes tạm trong HTTP session và kết thúc bằng `SessionStatus`.
- [Spring Framework — `@SessionAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattribute.html): đọc pre-existing HTTP session attributes qua handler method parameter.
- [Spring Framework — `@ModelAttribute` methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-modelattrib-methods.html): cung cấp model attribute và phối hợp controller methods.
- [Spring Framework — `@ModelAttribute` method arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): binding, validation, model/session attribute resolution.
- [Spring Framework — MVC Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): `SessionStatus`, `@SessionAttribute`, `HttpSession` và những loại tham số được hỗ trợ.
- [Spring Framework — `SessionStatus` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/bind/support/SessionStatus.html): hợp đồng `setComplete()`, `isComplete()`.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): bảo vệ các state-changing requests dùng session/cookie.

**Kết luận:** dùng **`@SessionAttributes`** cho một tập model attributes tồn tại tạm xuyên request trong cùng controller workflow; dùng **`SessionStatus.setComplete()`** để dọn chúng khi workflow thành công hoặc hủy; dùng **`@SessionAttribute`** khi chỉ cần **đọc** một key đã có trong HTTP session, đặc biệt khi được quản lý ngoài controller. Cả ba không thay thế session security, binding limits, business validation, concurrency control và lưu trữ bền vững.
