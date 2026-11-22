# @InitBinder: cấu hình cục bộ và dùng chung qua @ControllerAdvice trong Spring MVC

## Mục tiêu và phạm vi

Trong Spring MVC, `@InitBinder` cho phép bạn tùy chỉnh **`WebDataBinder`** trước khi Spring bind dữ liệu từ HTTP request vào tham số handler. Bài này giải thích `WebDataBinder` làm gì, phạm vi cấu hình **cục bộ trong controller** và **dùng chung qua `@ControllerAdvice`**, cách đặt tên model attribute, đăng ký bộ chuyển đổi/formatter, giới hạn field được bind, phối hợp với validation và `BindingResult`, cũng như cách kiểm thử tránh lỗi và rủi ro mass assignment.

Ví dụ sử dụng **Java 17+**, **Spring MVC trên Servlet stack**, **Spring Boot 3.x**. Các đoạn có đường dẫn file tạo thành một ứng dụng mẫu; ví dụ riêng được đánh dấu là minh họa. Spring WebFlux có cơ chế data binding tương tự nhưng không phải chủ đề ở đây.

## 1. Hiểu data binding trước khi dùng `@InitBinder`

Một form gửi request:

~~~http
POST /appointments HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded

visitorName=Lan&date=2026-10-21
~~~

Handler có thể nhận một object:

~~~java
@PostMapping("/appointments")
public String create(@ModelAttribute("appointmentForm") AppointmentForm form) {
    return form.getVisitorName();
}
~~~

Đây chỉ là phần thân phương thức minh họa: `AppointmentForm` là JavaBean có property `visitorName` và `date`.

Luồng đơn giản hóa của Spring MVC:

1. Chọn handler method phù hợp request.
2. Tạo hoặc tìm model attribute cần bind, ví dụ `appointmentForm`.
3. Tạo `WebDataBinder` gắn với target và object name tương ứng.
4. Áp dụng các phương thức `@InitBinder` đủ điều kiện, gồm phần dùng chung từ `@ControllerAdvice` và phần khai báo trong controller.
5. Bind dữ liệu request vào object bằng cơ chế constructor binding và/hoặc property binding tương ứng, đồng thời chuyển kiểu dữ liệu (ví dụ chuỗi `2026-10-21` thành `LocalDate`).
6. Nếu handler yêu cầu validation (`@Valid`, `@Validated`), Spring tiến hành validation; handler có thể đọc lỗi qua `BindingResult` đặt đúng vị trí.
7. Gọi handler với tham số đã bind.

Mỗi lần bind được tạo **`WebDataBinder` riêng**, nên cấu hình editor/formatter hay danh sách field trên binder áp dụng cho lần bind đó. Phương thức `@InitBinder` **không phải HTTP endpoint**, không tự tạo response, không thay thế `@PostMapping` và thường có kiểu trả về `void`.

`@InitBinder` được khai báo trong lớp `@Controller`/`@RestController` hoặc `@ControllerAdvice`. Đối số thông dụng nhất là `WebDataBinder`. Tùy phiên bản và cấu hình, có thể dùng một số đối số ngữ cảnh được hỗ trợ như `WebRequest` hoặc `Locale`; không khai báo tùy ý một `@ModelAttribute` làm đối số cho chính phương thức `@InitBinder`.

## 2. Phạm vi cục bộ: đặt `@InitBinder` trong một controller

~~~java
@RestController
class AppointmentController {

    @InitBinder
    void configureAllBindersInThisController(WebDataBinder binder) {
        binder.setAllowedFields("visitorName", "date");
    }

    // Các handler @RequestMapping/@PostMapping ở đây...
}
~~~

Đoạn trên chỉ minh họa cấu trúc, chưa phải file Java chạy độc lập (thiếu import và các handler). `@InitBinder` **không có tên** có thể áp dụng cho các binder phù hợp bên trong controller này. Nếu controller xử lý nhiều form khác nhau, áp dụng danh sách field chung cho tất cả có thể vô tình chặn những trường hợp hợp lệ.

Để giới hạn theo đúng **object name** của model attribute, sử dụng `@InitBinder("appointmentForm")`:

~~~java
@InitBinder("appointmentForm")
void configureAppointment(WebDataBinder binder) {
    binder.setAllowedFields("visitorName", "date");
}
~~~

Khai báo tương ứng ở handler:

~~~java
@PostMapping("/appointments")
public String create(
        @ModelAttribute("appointmentForm") AppointmentForm form) {
    return form.getVisitorName();
}
~~~

Tên `appointmentForm` phải khớp. Tham số `value` của `@InitBinder` cũng nhận nhiều tên, chẳng hạn `@InitBinder({"appointmentForm", "bookingForm"})`. Tên này là **tên model attribute hoặc request parameter mà binder xử lý**, không phải URL, tên Java class hoặc tên một method.

Khi cùng controller có `@InitBinder("appointmentForm")` và `@InitBinder("profileForm")`, mỗi binder có thể nhận cấu hình khác nhau. Đừng đặt tên từ thói quen rồi bỏ kiểm tra: nếu model attribute có tên khác, cấu hình cục bộ có thể không chạy trên object mong muốn.

## 3. Phạm vi dùng chung: `@InitBinder` trong `@ControllerAdvice`

~~~java
@ControllerAdvice
public class SharedBindingAdvice {

    @InitBinder
    public void configure(WebDataBinder binder) {
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(true));
    }
}
~~~

Đây là đoạn minh họa, cần import `WebDataBinder`, `StringTrimmerEditor` và `@ControllerAdvice`/`@InitBinder`. Editor được tạo trong lúc khởi tạo binder và sẽ cắt khoảng trắng đầu/cuối các property kiểu `String` được bind; đối số `true` biến chuỗi rỗng sau khi cắt thành `null`.

Nếu không chỉ định selector, `@ControllerAdvice` có phạm vi rộng, có thể áp dụng với các controller được Spring MVC quản lý. Có thể thu hẹp advice bằng:

~~~java
@ControllerAdvice(assignableTypes = {
        AppointmentController.class, ProfileController.class
})
~~~

Hoặc dùng selector theo package/annotation, ví dụ `basePackages = "com.example.demo.form"` hay `annotations = RestController.class`. Những selector ở đây là **cách chọn controller**, còn `@InitBinder("appointmentForm")` là **cách chọn target của binder trong controller đã được chọn**. Hai tầng phạm vi này bổ sung cho nhau.

Trong ứng dụng lớn, không nên tự động triển khai một cấu hình thay đổi mọi chuỗi hoặc mọi field lên tất cả controller. Ví dụ trim `String` có thể hợp lý với tên hiển thị nhưng lại làm thay đổi mật khẩu, mã ký, token hay chuỗi mà khoảng trắng có ý nghĩa. Hãy xác định rõ phạm vi từng advice.

**So sánh nhanh:**

| Khai báo | Phạm vi |
| --- | --- |
| `@InitBinder` trong `AppointmentController` | Các binder phù hợp của controller đó |
| `@InitBinder("appointmentForm")` trong `AppointmentController` | Binder có object name `appointmentForm` trong controller đó |
| `@InitBinder` trong `@ControllerAdvice` không selector | Các binder phù hợp ở các controller thuộc phạm vi advice |
| `@InitBinder("appointmentForm")` trong advice có selector | Controller khớp selector **và** binder khớp tên attribute |
| `WebMvcConfigurer#addFormatters(...)` | Đăng ký converter/formatter trong cấu hình MVC dùng chung |

Nếu nhiều advice cùng có thể áp dụng, cấu hình phải tránh xung đột (chẳng hạn hai nơi cùng đăng ký editor cho một kiểu). Đừng dựa vào thứ tự ngầm của những cấu hình trùng chức năng; tách phạm vi rõ ràng và kiểm thử kết quả cuối.

## 4. Bạn có thể cấu hình gì trên `WebDataBinder`?

| Cơ chế | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `setAllowedFields(...)` | Chỉ cho phép **property binding** những field khai báo | Phòng trường hợp client gửi thêm property không mong muốn |
| `setRequiredFields(...)` | Yêu cầu field xuất hiện khi bind input | Một số quy tắc có mặt của request field, không thay mọi validation |
| `registerCustomEditor(...)` | Đăng ký `PropertyEditor` chuyển đổi | Tình huống cần editor kiểu cũ hoặc logic cụ thể theo binder |
| `addCustomFormatter(...)` | Đăng ký `Formatter` cho kiểu/field | Chuyển giá trị có quy tắc hiển thị và parse phù hợp |
| `addValidators(...)` | Bổ sung `org.springframework.validation.Validator` | Kiểm tra nghiệp vụ bổ sung bên cạnh Bean Validation |
| `setDeclarativeBinding(true)` | Kiểm soát cách binding theo khai báo tường minh (nếu phiên bản hỗ trợ) | Giới hạn property binding trên những object cần bảo vệ |

`setAllowedFields` là **allowlist của setter/property binding**, đặc biệt cần cân nhắc khi bind những object có cả thuộc tính người dùng được nhập và thuộc tính nội bộ. `setRequiredFields` kiểm tra mức binding field có được cung cấp, **khác** với các annotation `@NotBlank`, `@NotNull`, `@Size` kiểm tra giá trị hợp lệ. Với API hiện đại, thường ưu tiên DTO chỉ chứa input được phép và Bean Validation.

Một cách chuyển kiểu ngày tháng thông thường là dùng ngay:

~~~java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate date;
~~~

Khi cần quy tắc riêng ở quy mô nhiều controller, cân nhắc đăng ký `Converter` hoặc `Formatter` qua `WebMvcConfigurer#addFormatters` và `FormattingConversionService`. Chỉ dùng `@InitBinder` để xử lý riêng tại binder khi phạm vi hẹp là chủ đích.

**Bảo mật:** Theo tài liệu Spring MVC, `allowedFields` là danh sách cho property binding, không nên hiểu là biện pháp kiểm soát constructor binding trong mọi trường hợp. Với object có constructor từ tham số request, hãy sử dụng DTO chuyên biệt, kiểm soát constructor input và cấu hình declarative binding thích hợp. Đừng bind trực tiếp entity/domain object nhiều thuộc tính nhạy cảm rồi trông chờ frontend “không gửi” những field đó.

## 5. Ứng dụng chạy được: một cấu hình local và một advice dùng chung

Tạo dự án Maven từ Spring Initializr với **Java 17+**, **Spring Boot 3.x**, dependencies **Spring Web**, **Validation** và **Spring Boot Starter Test**. Các dependency tương ứng là `spring-boot-starter-web`, `spring-boot-starter-validation`, `spring-boot-starter-test`. Giữ package Java là `com.example.demo`.

Cấu trúc:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/AppointmentController.java
src/main/java/com/example/demo/ProfileController.java
src/main/java/com/example/demo/FormBindingAdvice.java
src/test/java/com/example/demo/BindingControllerTest.java
~~~

### 5.1. Điểm khởi động

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

### 5.2. `@ControllerAdvice` cấu hình chung cho hai controller

**`src/main/java/com/example/demo/FormBindingAdvice.java`**

~~~java
package com.example.demo;

import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.InitBinder;

@ControllerAdvice(assignableTypes = {
        AppointmentController.class, ProfileController.class
})
public class FormBindingAdvice {

    @InitBinder
    public void trimStrings(WebDataBinder binder) {
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(true));
    }
}
~~~

Advice này chỉ áp dụng cho hai controller được liệt kê. Khi bind các form object trong hai controller, `StringTrimmerEditor` sẽ chuẩn hóa khoảng trắng. Do đang minh họa một quy tắc cắt khoảng trắng, hãy **không** mở rộng advice cho form có secret/password nếu sản phẩm cần giữ nguyên từng ký tự.

### 5.3. `@InitBinder("appointmentForm")` giới hạn field cục bộ

**`src/main/java/com/example/demo/AppointmentController.java`**

~~~java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;
import java.util.Map;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AppointmentController {

    @InitBinder("appointmentForm")
    public void restrictFields(WebDataBinder binder) {
        binder.setAllowedFields("visitorName", "date");
    }

    @PostMapping(
            path = "/appointments",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("appointmentForm") AppointmentForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "invalid appointment"));
        }

        return ResponseEntity.ok(new AppointmentResponse(
                form.getVisitorName(),
                form.getDate(),
                form.getRole()));
    }

    public record AppointmentResponse(
            String visitorName,
            LocalDate date,
            String role) {
    }

    public static class AppointmentForm {
        @NotBlank
        private String visitorName;

        @NotNull
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        private LocalDate date;

        // Thuộc tính cố ý để minh họa không bind từ request.
        private String role = "viewer";

        public AppointmentForm() {
        }

        public String getVisitorName() {
            return visitorName;
        }

        public void setVisitorName(String visitorName) {
            this.visitorName = visitorName;
        }

        public LocalDate getDate() {
            return date;
        }

        public void setDate(LocalDate date) {
            this.date = date;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }
    }
}
~~~

**Phân tích kỹ ví dụ:**

- `@ModelAttribute("appointmentForm")` khớp tên trong `@InitBinder("appointmentForm")`; do đó allowlist `visitorName`, `date` áp dụng đúng form.
- `AppointmentForm` có constructor không đối số và setter, nên ví dụ minh họa **property binding** cụ thể. Dù client gửi `role=admin`, property `role` không nằm trong allowlist và giữ giá trị `"viewer"`.
- `@DateTimeFormat(iso = ISO.DATE)` hướng dẫn chuyển chuỗi dạng `yyyy-MM-dd` sang `LocalDate`; format sai tạo lỗi binding.
- `@Valid` chạy Bean Validation sau binding. `@NotBlank` không chấp nhận `visitorName` rỗng, `@NotNull` không chấp nhận `date` null.
- `BindingResult errors` phải đặt **ngay sau tham số model attribute** tương ứng. Nếu đặt sai vị trí, Spring MVC không có cùng cơ chế đưa lỗi của attribute này cho handler.
- Nếu có lỗi, endpoint tự trả HTTP 400. Nếu không, endpoint trả JSON với `role` để **thấy hiệu ứng của allowlist**; sản phẩm thật không nên tiết lộ thông tin nội bộ chỉ để chứng minh cơ chế này.

`@InitBinder` không phải nơi phù hợp để xác thực danh tính hoặc quyết định quyền truy cập: phép kiểm tra `role` trong ví dụ là minh họa tránh **mass assignment**, còn phân quyền thực tế phải do tầng bảo mật/nghiệp vụ thực hiện.

### 5.4. Controller thứ hai nhận cùng quy tắc từ advice

**`src/main/java/com/example/demo/ProfileController.java`**

~~~java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @PostMapping(
            path = "/profiles",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "invalid profile"));
        }

        return ResponseEntity.ok(
                Map.of("displayName", form.getDisplayName()));
    }

    public static class ProfileForm {
        @NotBlank
        private String displayName;

        public ProfileForm() {
        }

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }
    }
}
~~~

`ProfileController` không hề khai báo `@InitBinder`, nhưng **vẫn được advice chọn** qua `assignableTypes`; input `displayName` vì vậy cũng được trim. Mặt khác, allowlist ở `AppointmentController` **không** ảnh hưởng form `profileForm`: hai controller có giới hạn cục bộ khác nhau.

## 6. Chạy request và giải thích kết quả

Sau khi tạo file theo cấu trúc trên, chạy:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows với Maven Wrapper: `mvnw.cmd spring-boot:run`. Nếu không có wrapper, dùng `mvn spring-boot:run` khi máy đã cài Maven.

Thử gọi bằng `curl`:

~~~bash
curl -i -X POST "http://localhost:8080/appointments"   -d "visitorName=%20%20Lan%20%20"   -d "date=2026-10-21"   -d "role=admin"
~~~

Đây là cú pháp shell dùng dấu `\` để nối dòng (Linux/macOS/Git Bash); trên PowerShell nên dùng `curl.exe` với toàn bộ tham số trên một dòng. `curl -d` mặc định gửi body `application/x-www-form-urlencoded`, khớp với `consumes` của controller.

Kết quả **200 OK** (thứ tự property JSON không quan trọng):

~~~json
{"visitorName":"Lan","date":"2026-10-21","role":"viewer"}
~~~

Lý do:

- Advice toàn cục có phạm vi chọn `AppointmentController` đã trim `"  Lan  "` thành `"Lan"`.
- Binder local cho `appointmentForm` cho phép `visitorName` và `date`, nhưng loại `role` khỏi property binding, nên `viewer` không bị thay bằng `admin`.
- `@DateTimeFormat` giúp bind ngày đúng định dạng; `@Valid` xác nhận dữ liệu hợp lệ.

Thử controller thứ hai:

~~~bash
curl -i -X POST "http://localhost:8080/profiles"   -d "displayName=%20%20Mai%20%20"
~~~

HTTP **200 OK**, body kỳ vọng:

~~~json
{"displayName":"Mai"}
~~~

Thử gửi tên toàn dấu cách hoặc ngày sai định dạng:

~~~bash
curl -i -X POST "http://localhost:8080/appointments"   -d "visitorName=%20%20%20"   -d "date=2026-10-21"

curl -i -X POST "http://localhost:8080/appointments"   -d "visitorName=Lan"   -d "date=21/10/2026"
~~~

Cả hai request đều nhận **400 Bad Request** trong ví dụ: request đầu có `visitorName` sau trim thành `null`, không đạt `@NotBlank`; request sau không chuyển được `date` theo ISO. Controller minh họa trả body:

~~~json
{"error":"invalid appointment"}
~~~

Những ví dụ này giả định ứng dụng chạy trên cổng Spring Boot mặc định `8080` và chưa có cấu hình Spring Security yêu cầu xác thực/CSRF. Nếu project thêm Spring Security, bạn phải cấu hình authentication và CSRF phù hợp trước khi sử dụng lệnh `curl` trên.

## 7. Kiểm thử bằng MockMvc để chứng minh phạm vi binder

Thêm **`src/test/java/com/example/demo/BindingControllerTest.java`**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = {
        AppointmentController.class, ProfileController.class
})
@Import(FormBindingAdvice.class)
class BindingControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void localAllowlistAndSharedTrimmingWorkTogether() throws Exception {
        mockMvc.perform(post("/appointments")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("visitorName", "  Lan  ")
                        .param("date", "2026-10-21")
                        .param("role", "admin"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.visitorName").value("Lan"))
                .andExpect(jsonPath("$.date").value("2026-10-21"))
                .andExpect(jsonPath("$.role").value("viewer"));
    }

    @Test
    void sharedAdviceAlsoAppliesToProfileController() throws Exception {
        mockMvc.perform(post("/profiles")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("displayName", "  Mai  "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Mai"));
    }

    @Test
    void blankVisitorNameFailsValidation() throws Exception {
        mockMvc.perform(post("/appointments")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("visitorName", "   ")
                        .param("date", "2026-10-21"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void invalidDateFailsConversion() throws Exception {
        mockMvc.perform(post("/appointments")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .param("visitorName", "Lan")
                        .param("date", "21/10/2026"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

Bài kiểm thử thứ nhất là bằng chứng đồng thời cho **phạm vi local** (field `role` bị bỏ qua) và **phạm vi shared** (tên được trim). Bài thứ hai chứng minh advice có hiệu lực ở controller khác. Hai bài cuối giúp phát hiện lỗi giữa chuyển kiểu và validation. `@Import(FormBindingAdvice.class)` bảo đảm advice có mặt trong Spring MVC test slice, ngay cả khi cấu hình quét component của test khác cấu hình ứng dụng chính.

`MockMvc` mô phỏng request tới Spring MVC mà không cần mở cổng HTTP thật; nó kiểm tra binder, argument resolution, validation và response của controller. Khi có `SecurityFilterChain` tùy chỉnh, các test cần cấu hình an ninh phù hợp.

## 8. Đăng ký `PropertyEditor`, `Formatter` và `Validator`: nên dùng ở đâu?

### `PropertyEditor`: cách cổ điển

~~~java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.registerCustomEditor(
            String.class, new StringTrimmerEditor(true));
}
~~~

Đoạn này đã dùng trong ví dụ chính. Các `PropertyEditor` thường giữ trạng thái, vì vậy **không chia sẻ một instance mutable cho nhiều request/thread**. Tạo instance mới khi binder được khởi tạo như code trên. Với `java.util.Date`, Spring còn có `CustomDateEditor`, nhưng khi dùng `java.time` hiện đại, `@DateTimeFormat`/`Formatter` thường gọn hơn.

### `Formatter`: khi cần parse/print một kiểu nhất quán

Ví dụ minh họa dưới đây dành cho property kiểu `java.util.Date`, không phải `LocalDate`:

~~~java
@InitBinder("legacyForm")
void initLegacyDate(WebDataBinder binder) {
    binder.addCustomFormatter(new DateFormatter("yyyy-MM-dd"));
}
~~~

Trong ngữ cảnh controller, bạn cần import `org.springframework.format.datetime.DateFormatter` và `org.springframework.web.bind.WebDataBinder`. Nếu formatter cần áp dụng ở nhiều nơi theo cùng quy tắc, hãy cân nhắc đặt trong shared MVC `ConversionService` thay vì lặp các `@InitBinder`.

### `Validator`: bổ sung quy tắc nghiệp vụ

Có thể dùng `binder.addValidators(customValidator)` để thêm một validator tương thích `org.springframework.validation.Validator`. Một validator kiểu này cần thực hiện `supports(Class<?>)` và `validate(Object, Errors)`. Lúc chạy, Spring kiểm tra kiểu target có phù hợp validator không; đăng ký sai validator có thể gây lỗi cấu hình.

`@InitBinder` chỉ **đăng ký** validator; nó không có nghĩa mọi handler đều tự động kiểm tra khi không có kích hoạt validation thích hợp. Dùng `@Valid` hoặc `@Validated` cho model attribute khi muốn Spring kích hoạt validation, hoặc gọi kiểm tra rõ ràng nếu thiết kế yêu cầu. Với Bean Validation thông thường, có thể dùng `@NotBlank`, `@Size`, `@Email`, `@NotNull` và kiểm tra `BindingResult`.

Nếu muốn thay đổi validator đang có, cần hiểu khác biệt giữa `addValidators` (bổ sung) và `setValidator` (thiết lập/thay thế một validator). Đừng vô tình thay mất Bean Validation chuẩn đang dùng.

## 9. Giới hạn quan trọng: `@InitBinder` không thay thế JSON deserialization

`@ModelAttribute` thường nhận dữ liệu query/form từ request và bind bằng `WebDataBinder`, trong khi `@RequestBody` thường đọc JSON qua `HttpMessageConverter`/Jackson. Ví dụ:

~~~java
@PostMapping("/users")
public void create(@RequestBody CreateUserRequest request) {
    // Jackson đọc JSON của toàn request thành CreateUserRequest.
}
~~~

Đây là đoạn minh họa chưa độc lập. Một `StringTrimmerEditor` gắn vào `WebDataBinder` **không có nghĩa** mọi chuỗi mà Jackson đọc từ JSON đều được trim. Với `@RequestBody`, hãy dùng cơ chế phù hợp ở tầng Jackson/deserializer, normalizer dành riêng cho dữ liệu hoặc xử lý ở service/DTO. Cơ chế `WebDataBinder` vẫn có thể liên quan đến **validation** của đối tượng được `@RequestBody` tạo ra, nhưng đừng nhầm điều đó với setter binding từ form.

Tương tự, `@InitBinder` không thay cho `@ControllerAdvice @ExceptionHandler`: hai loại callback có nhiệm vụ khác nhau. `@InitBinder` **cấu hình binding**; `@ExceptionHandler` **xử lý ngoại lệ**. Một lớp advice có thể chứa cả hai, nhưng nên phân tách rõ trách nhiệm.

## 10. Bảo mật binding: allowlist, constructor binding và mass assignment

Giả sử một entity `User` có các property `displayName`, `email`, `isAdmin`. Nếu bind request trực tiếp vào entity bằng setter, attacker có thể thêm `isAdmin=true` ngay cả khi giao diện không hiển thị trường đó. Đó là **mass assignment**.

Các biện pháp ưu tiên:

1. Tạo **input DTO** chỉ chứa các field người dùng được quyền cung cấp; chuyển DTO sang entity qua service theo luật nghiệp vụ.
2. Nếu cần property binding, dùng `WebDataBinder#setAllowedFields("fieldA", "fieldB")` theo từng model attribute. Cấu hình này chủ yếu bảo vệ **setter/property binding**, không nên đánh đồng với kiểm soát constructor parameter.
3. Với Spring Framework có hỗ trợ `setDeclarativeBinding(true)`, cân nhắc chế độ declarative binding: constructor binding vẫn hoạt động, property binding cần allowlist được cấu hình. Cần hiểu constructor DTO nhận input nào và kiểm thử cụ thể.
4. Kiểm tra quyền tại service/security layer dựa trên người dùng đã xác thực và trạng thái phía server, không tin `role`, `isAdmin` hoặc `ownerId` do client gửi.
5. Đừng dùng `setDisallowedFields` làm giải pháp mặc định khi có thể dùng allowlist: denylist dễ bỏ sót thuộc tính mới. Một số phiên bản Spring mới cũng định hướng tránh API này.

Trong code mẫu, field `role` với setter tồn tại chỉ để thấy tác dụng của allowlist; thiết kế API thật nên bỏ field đó khỏi form DTO nếu không phải input hợp lệ.

## 11. Lỗi thường gặp, cách xác minh

| Dấu hiệu | Khả năng | Cách kiểm tra |
| --- | --- | --- |
| `@InitBinder` local không chạy | Sai tên `@ModelAttribute` hoặc binder không thuộc controller mong đợi | Đối chiếu `@InitBinder("...")` và `@ModelAttribute("...")` |
| Advice không có hiệu lực | Controller không khớp `assignableTypes`, `basePackages` hoặc `annotations` | Kiểm tra selector và vị trí bean được Spring quét |
| Editor chạy cho form ngoài ý muốn | Advice quá rộng hoặc binder không có tên hạn chế | Thu hẹp selector, tách rule theo controller/attribute |
| Chuyển ngày bị lỗi | Định dạng chuỗi không khớp formatter/`@DateTimeFormat` | Kiểm tra input và expected pattern |
| `BindingResult` không nhận lỗi cần thiết | Đặt sai vị trí hoặc handler không có attribute tương ứng | Đặt ngay sau tham số `@Valid @ModelAttribute` |
| Field nội bộ bất ngờ bị thay đổi | Bind trực tiếp vào object quá rộng; thiếu allowlist | Dùng DTO, `setAllowedFields`, kiểm thử gửi field lạ |
| Một field hợp lệ không bind | Allowlist thiếu tên property | Bổ sung đúng property sau khi xác nhận contract input |
| Trim không tác động lên JSON `@RequestBody` | Jackson xử lý JSON riêng | Cấu hình Jackson hoặc normalizer riêng |
| Custom editor gây lỗi ngẫu nhiên khi tải cao | Chia sẻ editor mutable không an toàn giữa thread | Tạo editor theo binder; cân nhắc formatter/converter stateless |
| Handler vẫn trả 400 dù không gọi service | Lỗi binding/validation đã được phát hiện trước | Xem log, `BindingResult` hoặc exception handler cấu hình |

Khi cần kiểm chứng field bị từ chối bởi allowlist, `BindingResult#getSuppressedFields()` có thể cho biết tên field request đã bị suppress. Đây là tín hiệu chẩn đoán hữu ích; không thay thế việc xác minh API không vô tình lưu giá trị trái phép.

## 12. Câu hỏi ôn tập

**1. Tại sao `@InitBinder("appointmentForm")` không tương đương với `@InitBinder`?**

Vì bản có tên chỉ áp dụng cho binder của attribute/request parameter có tên khớp; bản không tên có phạm vi rộng hơn trong controller hoặc advice sở hữu method.

**2. Nếu ba controller dùng chung một quy tắc chuẩn hóa form thì đặt ở đâu?**

Ưu tiên `@ControllerAdvice` có selector khớp chính xác ba controller, hoặc cơ chế converter/formatter dùng chung ở MVC config nếu đây là quy tắc conversion cấp toàn ứng dụng.

**3. Gửi `role=admin` vào form mẫu tại sao vẫn nhận `role=viewer`?**

Vì `AppointmentForm` được bind theo property và allowlist chỉ có `visitorName`, `date`; giá trị client gửi cho `role` bị bỏ qua. Quyền truy cập thực tế vẫn phải kiểm tra ở server.

**4. `@Valid` có thể thay thế allowlist không?**

Không. Validation xác nhận giá trị sau/bên cạnh binding; allowlist giới hạn property nào được phép bind. Chúng giải quyết hai câu hỏi khác nhau và có thể cùng cần thiết.

**5. Tại sao editor String trên WebDataBinder không tự động trim JSON `@RequestBody`?**

Vì JSON được `HttpMessageConverter` (thường Jackson) deserialization, khác với cơ chế property binding form/query qua `WebDataBinder`.

## 13. Checklist trước khi dùng trong dự án

- Đặt tên model attribute tường minh nếu binder chỉ dành cho một loại form; kiểm tra tên trong `@InitBinder` và `@ModelAttribute` khớp.
- Đưa quy tắc thực sự dùng chung vào advice có phạm vi phù hợp; dùng global `ConversionService` nếu nhu cầu chỉ là converter/formatter chung.
- Sử dụng DTO input, allowlist đối với setter binding khi cần, và validation với `@Valid`/`BindingResult`; xác thực và phân quyền tại server.
- Phân biệt lỗi conversion, lỗi validation và field bị suppress. Kiểm thử tình huống hợp lệ, thiếu, sai định dạng và gửi field không được phép.
- Không dùng `@InitBinder` để thay thế JSON deserializer, exception handler hoặc security filter.

## Tài liệu tham khảo chính thức

- [Spring Framework — `@InitBinder` trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework — `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Controller Advice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html)
