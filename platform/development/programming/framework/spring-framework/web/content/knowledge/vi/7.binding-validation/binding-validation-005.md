# Giới hạn trường được binding để tránh sửa thuộc tính ngoài hợp đồng trong Spring MVC

> **Bối cảnh:** Spring Web MVC (Servlet stack), Java 17+ và Spring Boot 3.x. Trọng tâm là ngăn **mass assignment / over-posting**: client gửi thêm tên trường ngoài hợp đồng API và framework vô tình gán chúng vào thuộc tính mà người dùng không được phép sửa. Bài học hướng dẫn thiết kế DTO, `@InitBinder` với `WebDataBinder#setAllowedFields`, kiểm tra trường bị loại, giới hạn constructor binding, phân biệt form binding với JSON deserialization, và kiểm soát cập nhật ở tầng nghiệp vụ.

## 1. Vấn đề: client có thể gửi nhiều hơn những gì giao diện hiển thị

Giả sử endpoint chỉ cho phép người dùng cập nhật tên hiển thị và phần giới thiệu:

```http
POST /profiles/42
Content-Type: application/x-www-form-urlencoded

displayName=Lan&bio=Java+learner
```

Một client tùy ý có thể thêm:

```http
POST /profiles/42
Content-Type: application/x-www-form-urlencoded

displayName=Lan&bio=Java+learner&admin=true&ownerId=7
```

Trường `admin` và `ownerId` **không có trong hợp đồng chỉnh sửa profile**. Việc giao diện HTML không tạo input tương ứng không ngăn client tự gửi các tham số ấy.

Ví dụ **không an toàn**:

```java
// Minh họa rủi ro, không dùng cho ứng dụng thực.
@PostMapping("/profiles/{id}")
public String update(@PathVariable long id,
                     @ModelAttribute Account account) {
    accountRepository.save(account);
    return "saved";
}
```

Nếu `Account` có setter công khai cho `admin`, `role` hoặc `ownerId`, quá trình property binding có thể gán các trường mà client gửi vào object. Không phải cứ đưa ID vào URL là tự động kiểm tra quyền sở hữu; `save` cũng không bảo đảm người dùng được phép sửa toàn bộ object.

**Nguyên tắc:** kiểm soát **tập trường client được phép cung cấp** và **tập thuộc tính nghiệp vụ được phép thay đổi** là hai ranh giới riêng. Binding an toàn không thay thế authentication, authorization và kiểm tra quyền sở hữu bản ghi.

## 2. Spring MVC binding hoạt động ở đâu?

Với `@ModelAttribute`, Spring MVC tạo hoặc lấy một model object, rồi dùng `WebDataBinder` để nhận dữ liệu từ request và chuyển kiểu cho object. Nguồn input có thể gồm request parameters (query string/form data), URI variables hoặc request headers theo cơ chế `@ModelAttribute`; request parameters có mức ưu tiên thích hợp khi trùng tên.

Ví dụ:

```java
@PostMapping("/profiles")
public void update(@ModelAttribute ProfileForm form) {
    // form được Spring tạo/gắn dữ liệu trước khi method chạy.
}
```

Với JavaBean mutable, các trường phù hợp với setter công khai có thể được gán theo **property binding**. Spring cũng hỗ trợ **constructor binding**, trong đó input phù hợp với tham số constructor được dùng để tạo object. Với object có thể chứa dữ liệu đặc quyền, dùng một object rộng có nhiều setter mà không giới hạn đầu vào là rủi ro.

Sơ đồ luồng:

```text
HTTP form/query/path inputs
          |
          v
Handler mapping chọn controller method
          |
          v
@ModelAttribute tạo/lấy đối tượng
          |
          v
WebDataBinder
    ├─ constructor binding (tham số constructor)
    └─ property binding (setter/field theo cấu hình)
          |
          v
BindingResult (lỗi chuyển kiểu, validation, suppressed fields)
          |
          v
Controller kiểm tra lỗi và quyền -> cập nhật đúng thuộc tính
```

**Phân biệt ba câu hỏi:**

1. **Bind field nào?** Giải quyết bằng DTO/form chuyên dụng, `setAllowedFields`, hoặc constructor binding chủ đích.
2. **Giá trị có hợp lệ?** Giải quyết bằng validation (`@Valid`, Bean Validation, logic ứng dụng).
3. **Ai được phép thay đổi gì trên tài nguyên nào?** Giải quyết bằng authorization, kiểm tra ownership và quy tắc nghiệp vụ ở server.

Một giá trị có thể hoàn toàn **hợp lệ về kiểu** (ví dụ `admin=true`) nhưng vẫn **bị cấm cập nhật**.

## 3. Cách ưu tiên: input DTO chỉ chứa các trường được phép

Tạo object dành riêng cho thao tác chỉnh sửa, khác với entity lưu trong database:

```java
public record EditProfileRequest(String displayName, String bio) {
}
```

Hợp đồng chỉ định hai trường `displayName` và `bio`. Không có `admin`, `role` hoặc `ownerId` nên code nghiệp vụ không thể vô tình sao chép các thuộc tính ấy từ DTO.

Ví dụ cách cập nhật có chủ đích:

```java
// Phần mã minh họa nghiệp vụ, không phải chương trình độc lập.
@PostMapping("/profiles/{id}/edit")
public String edit(@PathVariable long id,
                   @ModelAttribute EditProfileRequest input,
                   Principal principal) {
    Account account = accountRepository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND));

    authorizationService.requireCanEdit(principal, account);
    account.setDisplayName(input.displayName());
    account.setBio(input.bio());
    accountRepository.save(account);
    return "saved";
}
```

Đoạn trên giả định tồn tại `Account`, `accountRepository` và `authorizationService` của ứng dụng. Điều cần nhìn là **chỉ gán hai property được cho phép** trên entity server đã xác định và đã kiểm tra quyền.

DTO là lựa chọn ưu tiên vì cấu trúc type thể hiện hợp đồng ngay trong mã nguồn. Tuy nhiên cần hiểu đúng rằng với `@ModelAttribute`, **constructor binding chỉ giới hạn những tham số được khai báo trong constructor**; nếu DTO vẫn có setter khác hoặc cấu hình cho phép property binding sau đó, hãy kiểm soát cơ chế này như ở mục 5.

**Tránh bind trực tiếp vào JPA entity** chứa các thuộc tính như `id`, `tenantId`, `owner`, `status`, `balance`, `approved`, `isAdmin`, `permissions`. Một entity phục vụ persistence thường có phạm vi rộng hơn hợp đồng API.

## 4. `@InitBinder` + `setAllowedFields`: danh sách trường được phép

Khi cần property binding vào một JavaBean mutable, hãy chủ động đăng ký **allowlist**:

```java
@InitBinder("profileForm")
void initProfileBinder(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "bio");
}
```

- `@InitBinder("profileForm")`: áp dụng tùy chỉnh binder cho model attribute có tên `profileForm` trong phạm vi controller. Tên phải trùng với `@ModelAttribute("profileForm")` của method xử lý.
- `WebDataBinder`: binder do Spring MVC tạo **riêng cho request/target phù hợp**, dùng để xử lý binding và conversion.
- `setAllowedFields("displayName", "bio")`: cho phép property binding **chỉ** hai tên này. Trường khác, kể cả `admin`, không được ghi qua setter/property binding.
- Chuỗi tên trường trong allowlist **phân biệt chữ hoa chữ thường**; hãy dùng đúng tên property JavaBean. Wildcard được hỗ trợ nhưng cần dùng rất dè dặt.

Ví dụ HTTP form:

```text
displayName=Lan&bio=Java+learner&admin=true
```

Với binder đã giới hạn, `displayName` và `bio` được nhận; `admin` bị loại khỏi property binding. Nếu thuộc tính `admin` mặc định là `false`, sau binding nó vẫn là `false`.

### 4.1. `setDisallowedFields` có phải lựa chọn tốt?

```java
// Không khuyến nghị làm hàng rào bảo vệ chính.
binder.setDisallowedFields("admin", "role", "ownerId");
```

Blocklist chỉ liệt kê các trường đã biết là nguy hiểm. Một property mới như `discountLimit` hoặc `securityFlags` có thể được thêm vào model nhưng không ai cập nhật blocklist. Vì vậy **allowlist rõ ràng** an toàn và dễ review hơn. Trong các tài liệu Spring Framework mới, `setDisallowedFields` còn được xem là cách tiếp cận mong manh và đang trên lộ trình deprecated ở phiên bản tương ứng; ưu tiên `setAllowedFields`.

### 4.2. Tên property lồng nhau, collection và wildcard

Spring có thể bind vào property paths, không chỉ property đơn:

```text
contact.email
addresses[0].city
settings[theme]
```

Allowlist có thể nêu đích danh path cần thiết, ví dụ:

```java
binder.setAllowedFields(
        "displayName",
        "contact.email",
        "addresses[0].city");
```

Đây là minh họa cho form object thực sự có các property lồng nhau tương ứng. Không tự động dùng `addresses*` hoặc `*` nếu hợp đồng chỉ cho phép một trường cụ thể: wildcard mở rộng tập input, đôi khi cho phép sửa phần tử khác hoặc các property phụ. Nếu một danh sách cần chỉnh sửa linh hoạt, hãy đặt giới hạn số phần tử, chỉ số hợp lệ và kiểm tra từng thuộc tính trong DTO thay vì để client quyết định bất kỳ path nào.

**Lưu ý giới hạn:** `setAllowedFields` kiểm soát **property binding**. Nó không kiểm soát mọi cơ chế tạo object hay mọi đường ghi dữ liệu khác, đặc biệt không phải hàng rào mặc định cho JSON `@RequestBody`. Xem mục 7.

## 5. Constructor binding và `setDeclarativeBinding(true)`

Từ Spring Framework **6.1**, `WebDataBinder` hỗ trợ:

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

Khi cờ này bật:

- **Constructor binding** vẫn hoạt động, dựa trên các tham số constructor đã khai báo.
- **Property binding** chỉ xảy ra nếu binder có `allowedFields` được cấu hình.

Như vậy có thể thiết kế record/immutable DTO có constructor chỉ nhận trường hợp đồng và không cho setter binding ngoài ý muốn. Khi constructor nhận `admin` hoặc `ownerId` thì giá trị ấy **vẫn có thể được bind qua constructor**; cờ không thể biến constructor thiếu an toàn thành an toàn. Chỉ khai báo các thành phần thực sự chấp nhận từ client.

Ví dụ dùng immutable input:

```java
// Đoạn code minh họa khi dùng Spring Framework 6.1+.
public record UpdateContact(String displayName, String phone) {
}

@ControllerAdvice
class BindingPolicy {

    @InitBinder
    void bindOnlyDeclaredFields(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

Đây là lựa chọn cấu hình rộng cho các controller chịu ảnh hưởng của `@ControllerAdvice`; không áp dụng bất ngờ lên cả ứng dụng mà chưa đánh giá những form trước đây phụ thuộc setter binding. Với các form JavaBean mutable cần property binding, có thể cấu hình `allowedFields` tại controller/attribute liên quan. Có thể giới hạn phạm vi `@ControllerAdvice` theo package hoặc controller type.

So sánh:

| Cách triển khai | Đặc điểm | Đề xuất |
| --- | --- | --- |
| Entity mutable + bind trực tiếp | Rộng hơn hợp đồng, dễ lộ setter nhạy cảm | Tránh |
| DTO mutable + `@InitBinder` allowlist | Kiểm soát property binding theo trường | Tốt nếu cần JavaBean/form |
| Record/immutable DTO chỉ chứa trường hợp đồng | Bề mặt input gọn và dễ review | Ưu tiên khi phù hợp |
| Declarative binding + DTO an toàn | Chỉ constructor binding; setter binding chỉ khi được cho phép | Phù hợp Spring 6.1+ |
| Blocklist `disallowedFields` | Dễ bỏ sót trường mới | Không dùng làm biện pháp chính |

## 6. Ví dụ Spring Boot 3.x có thể chạy: chặn `admin=true` từ HTML form

Ví dụ này **cố tình** đặt thuộc tính `admin` trong form bean để minh họa rủi ro và khả năng chặn của allowlist. Trong code production nên **loại hẳn property nhạy cảm khỏi input DTO**, theo mục 3.

### 6.1. Chuẩn bị dự án

Tạo Spring Boot 3.x project với Java 17+ và dependency **Spring Web** trên [Spring Initializr](https://start.spring.io/). Trong file `src/main/java/com/example/demo/DemoApplication.java`, đặt toàn bộ mã sau (một public class, hai package-private classes; không cần database hay Spring Security để chạy minh họa):

```java
package com.example.demo;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@RestController
class ProfileController {

    @InitBinder("profileForm")
    void initProfileFormBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "bio");
    }

    @PostMapping(
            path = "/profiles/{id}",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, Object>> update(
            @PathVariable("id") long id,
            @ModelAttribute("profileForm") ProfileForm form,
            BindingResult bindingResult) {

        // BindingResult phải đặt ngay sau @ModelAttribute tương ứng.
        String[] suppressed = bindingResult.getSuppressedFields();
        if (suppressed.length > 0) {
            Map<String, Object> rejected = new LinkedHashMap<>();
            rejected.put("error", "Fields not allowed");
            rejected.put("fields", Arrays.asList(suppressed));
            return ResponseEntity.badRequest().body(rejected);
        }

        if (bindingResult.hasErrors()) {
            Map<String, Object> rejected = new LinkedHashMap<>();
            rejected.put("error", "Invalid form input");
            return ResponseEntity.badRequest().body(rejected);
        }

        // Demo chỉ phản hồi object đã bind; không ghi database.
        Map<String, Object> accepted = new LinkedHashMap<>();
        accepted.put("id", id);
        accepted.put("displayName", form.getDisplayName());
        accepted.put("bio", form.getBio());
        accepted.put("admin", form.isAdmin());
        return ResponseEntity.ok(accepted);
    }
}

class ProfileForm {
    private String displayName = "";
    private String bio = "";
    private boolean admin;

    public ProfileForm() {
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getBio() {
        return bio;
    }

    public void setBio(String bio) {
        this.bio = bio;
    }

    public boolean isAdmin() {
        return admin;
    }

    public void setAdmin(boolean admin) {
        this.admin = admin;
    }
}
```

**Phân tích mã:**

1. `@ModelAttribute("profileForm")` tạo JavaBean `ProfileForm` bằng constructor không tham số và thực hiện property binding.
2. `@InitBinder("profileForm")` cấu hình binder cho đúng model attribute. Chỉ `displayName`, `bio` được phép gán, kể cả `ProfileForm` có `setAdmin(...)` công khai.
3. `getSuppressedFields()` trả các property path đã bị binder loại khỏi property binding. Demo chọn **từ chối request với HTTP 400** nếu có trường không được phép; đây là quyết định chính sách ứng dụng. **Spring không mặc định tự biến mỗi suppressed field thành HTTP 400**.
4. `bindingResult.hasErrors()` xử lý lỗi binding/conversion thông thường; không đồng nghĩa với `getSuppressedFields().length > 0`. Trong ví dụ này các trường hợp lệ đều có kiểu `String`.
5. Method **không lưu dữ liệu**. Output cho thấy `admin` giữ `false` và chỉ khi request không chứa trường ngoài hợp đồng thì được chấp nhận.

Với hệ thống thật, sau khi qua bước kiểm tra bạn còn phải xác định người dùng hiện tại, tải bản ghi server bằng ID, kiểm tra quyền và chỉ cập nhật những thuộc tính cho phép. Không dùng `form.isAdmin()` để quyết định quyền hay trạng thái admin, dù demo cho thấy nó bị chặn.

### 6.2. Chạy và kiểm tra HTTP output

Trong thư mục gốc của project Spring Initializr:

```bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell hoặc Command Prompt
mvnw.cmd spring-boot:run
```

Request hợp lệ:

```bash
curl -sS -X POST 'http://localhost:8080/profiles/42' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Lan' \
  --data-urlencode 'bio=Java learner'
```

Với cấu hình mặc định và không có filter làm thay đổi response, status **200 OK**, body JSON:

```json
{"id":42,"displayName":"Lan","bio":"Java learner","admin":false}
```

Request tấn công (có field ngoài hợp đồng):

```bash
curl -i -X POST 'http://localhost:8080/profiles/42' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Lan' \
  --data-urlencode 'bio=Java learner' \
  --data-urlencode 'admin=true'
```

Status dự kiến **400 Bad Request** do nhánh kiểm tra suppressed fields **do chúng ta viết**, body:

```json
{"error":"Fields not allowed","fields":["admin"]}
```

Các header như `Date` hoặc `Connection` phụ thuộc servlet container. Nếu chạy bằng PowerShell, đặt lệnh cURL trên một dòng và dùng `curl.exe` thay cho alias có thể tồn tại:

```powershell
curl.exe -i -X POST "http://localhost:8080/profiles/42" -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "displayName=Lan" --data-urlencode "bio=Java learner" --data-urlencode "admin=true"
```

Kết quả cho thấy server **phát hiện** input bị cấm, không chỉ âm thầm bỏ qua. Nếu bỏ nhánh kiểm tra suppressed fields, bản thân `setAllowedFields` vẫn có thể ngăn `admin` được gán; status có thể vẫn là 200, tùy code xử lý.

### 6.3. Vì sao `BindingResult` cần đứng ngay sau form?

```java
public ResponseEntity<?> update(
        @ModelAttribute("profileForm") ProfileForm form,
        BindingResult errors,
        @PathVariable long id) { /* ... */ }
```

Đây là **chữ ký minh họa**, cho thấy `BindingResult` đứng ngay sau object nó theo dõi. Nếu chèn tham số khác giữa `@ModelAttribute` và `BindingResult`, Spring không thể liên kết lỗi binding với object theo hợp đồng giải quyết đối số. Có thể đặt các tham số độc lập trước hoặc sau cặp này.

## 7. Phân biệt form `@ModelAttribute` và JSON `@RequestBody`

Đây là điểm bảo mật rất dễ nhầm:

| Đường vào | Cơ chế chuyển dữ liệu | `@InitBinder#setAllowedFields` kiểm soát trực tiếp? |
| --- | --- | --- |
| Form/query được bind vào `@ModelAttribute` mutable bean | `WebDataBinder` / property binding | **Có**, đối với các property được bind qua cơ chế đó |
| `@ModelAttribute` immutable record/constructor | Constructor binding | **Không** giới hạn constructor parameters bằng `allowedFields`; phải thiết kế constructor an toàn |
| JSON `@RequestBody` | `HttpMessageConverter`, thường Jackson deserialization | **Không** dùng `allowedFields` làm danh sách khóa JSON được phép |
| Cập nhật JPA entity đã lấy trong service | Code nghiệp vụ / persistence | Không; phải gán field có chủ đích và kiểm tra quyền |

Ví dụ JSON nguy hiểm:

```java
// KHÔNG NÊN: không deserialize JSON trực tiếp vào entity rộng.
@PatchMapping("/accounts/{id}")
public void patch(@PathVariable long id,
                  @RequestBody Account entity) {
    accountRepository.save(entity);
}
```

Jackson có thể điền những property nhận diện được trên `Account` theo cấu hình của nó. Một `@InitBinder#setAllowedFields` dành cho `@ModelAttribute` **không tự biến thành allowlist cho quá trình JSON deserialize này**.

Cách sửa cho endpoint JSON:

```java
// Đoạn minh họa: service dùng entity từ database và kiểm tra quyền.
public record EditAccountJson(String displayName, String bio) {
}

@PatchMapping("/accounts/{id}")
public ResponseEntity<Void> patch(
        @PathVariable long id,
        @RequestBody EditAccountJson input,
        Principal currentUser) {

    Account saved = accountRepository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND));

    authorizationService.requireCanEdit(currentUser, saved);
    saved.setDisplayName(input.displayName());
    saved.setBio(input.bio());
    accountRepository.save(saved);
    return ResponseEntity.noContent().build();
}
```

Đoạn code trên giả định có `Account`, repository và service bảo mật tương ứng; nó **không chạy độc lập** nếu thiếu các thành phần đó. Ưu điểm là JSON DTO chỉ có hai trường, và service cập nhật chính xác hai property. Nếu yêu cầu **từ chối** mọi JSON key lạ (ví dụ `admin`), cần cấu hình chính sách unknown properties của Jackson phù hợp với DTO và viết bài kiểm thử riêng; một số cấu hình mặc định có thể bỏ qua unknown keys. Bỏ qua key lạ và trả 2xx **khác** với chủ động từ chối request.

Với API dùng JSON, `@JsonIgnore`, `@JsonProperty(access = READ_ONLY)` hoặc Jackson views có thể là lớp bổ sung trong một số trường hợp, nhưng không nên thay cho thiết kế request DTO và kiểm soát quyền. Các field đặc quyền không nên xuất hiện trong request DTO chỉ để rồi phải nhớ chặn.

## 8. Không cho bind vào entity đã tồn tại: `@ModelAttribute(binding = false)`

Một pattern khác là để Spring cung cấp object đã có trong model, nhưng **không áp request parameters lên nó**:

```java
// Mã minh họa, yêu cầu repository và service do ứng dụng định nghĩa.
@ModelAttribute("account")
public Account loadAccount(@PathVariable long id) {
    return accountRepository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND));
}

@PostMapping("/accounts/{id}/edit")
public String update(
        @ModelAttribute("editForm") EditProfileRequest form,
        @ModelAttribute(value = "account", binding = false)
        Account account,
        Principal principal) {

    authorizationService.requireCanEdit(principal, account);
    account.setDisplayName(form.displayName());
    account.setBio(form.bio());
    accountRepository.save(account);
    return "saved";
}
```

`binding = false` nói Spring không dùng request values để data-bind **model attribute `account` trong method argument này**. Controller vẫn phải kiểm tra quyền và sao chép field đúng hợp đồng từ `editForm`. Chú ý một attribute khác hoặc code ngoài controller vẫn có thể tác động vào entity; đây là biện pháp ở ranh giới handler argument, không phải cơ chế khóa object tuyệt đối.

Khi method có nhiều `@ModelAttribute`, đặt tên rõ ràng giúp tách binder cho input form và binder cho domain entity. `@InitBinder("editForm")` nên được giới hạn theo đúng input nếu bạn cần allowlist khác.

## 9. Khi nào cấu hình ở controller, khi nào cấu hình chung?

### 9.1. Phạm vi controller và attribute

```java
@Controller
class SettingsController {
    @InitBinder("settingsForm")
    void allowSettings(WebDataBinder binder) {
        binder.setAllowedFields("theme", "notificationsEnabled");
    }
}
```

Áp dụng cho `settingsForm` trong controller. Tên thuộc tính hợp đồng khác nhau giữa các form thường nên có allowlist khác nhau. Không cấu hình cùng một danh sách field cho mọi domain object chỉ vì chúng đều đi qua MVC.

### 9.2. `@ControllerAdvice`

```java
@ControllerAdvice(basePackages = "com.example.web")
class WebBindingPolicy {
    @InitBinder
    void configure(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }
}
```

Đây là lựa chọn chính sách cho phạm vi package đã xác định, áp dụng tốt khi ứng dụng thiết kế các DTO theo constructor binding hoặc đã khai báo allowlist riêng nơi cần property binding. **Kiểm thử các form cũ** trước khi bật cho toàn bộ controller: form trông như bind đúng trước đây có thể không còn được gán setter khi bật declarative binding mà không có `allowedFields`.

Nếu nhiều `@InitBinder` cùng tác động lên một target, kiểm tra cấu hình thực tế của binder và tránh cho các binder ghi đè allowlist bằng thứ tự hoặc chính sách không rõ ràng. Đặt tên form và bảo vệ phạm vi rõ ràng giúp review đơn giản hơn.

## 10. Allowlist là một lớp bảo vệ; quy tắc nghiệp vụ vẫn cần thiết

Những giá trị không được phép sửa thường nằm **ngoài hợp đồng input**, ví dụ:

| Thuộc tính | Vì sao không cho client bind tùy ý? | Xử lý an toàn |
| --- | --- | --- |
| `id` | Chuyển sang tài nguyên khác | ID từ route, kiểm tra quyền và load bản ghi server |
| `ownerId`, `tenantId` | Chiếm quyền sở hữu/cross-tenant | Xác định từ identity và ngữ cảnh tổ chức đáng tin |
| `role`, `isAdmin` | Leo thang đặc quyền | Quản trị riêng, authorization nghiêm ngặt |
| `price`, `balance` | Thay đổi giá trị tài chính | Service nghiệp vụ được bảo vệ, tính toán phía server |
| `status`, `approved` | Bỏ qua quy trình phê duyệt | State transition do service kiểm soát |
| `createdAt`, `createdBy` | Sửa audit trail | Ghi từ server/persistence |
| `version` | Bỏ qua optimistic locking hoặc nhầm trạng thái | Cơ chế concurrency có kiểm soát |

Ngay cả field nằm trong allowlist vẫn có thể yêu cầu điều kiện nghiệp vụ. Ví dụ `displayName` cần độ dài hợp lệ, `email` có thể cần xác minh, trạng thái `published` có thể yêu cầu quyền riêng.

Ở tầng service nên thực hiện theo thứ tự: xác định current principal → truy vấn entity theo scope được phép → kiểm tra quyền thao tác → xác thực giá trị → gán các field được phép → lưu trong transaction khi cần. Tránh tin bất kỳ `ownerId`/`role` client gửi dù ở URL, query, form hay JSON.

## 11. Validation, suppressed fields và unknown fields khác nhau

- `@Valid` / `@Validated`: kiểm tra ràng buộc giá trị trên object (ví dụ `@NotBlank`, `@Size`); **không phải allowlist**. Nếu muốn dùng Bean Validation với Spring Boot, thêm dependency `spring-boot-starter-validation`.
- `BindingResult.hasErrors()`: phản ánh lỗi binding hoặc validation đã thực hiện. Không nên coi nó là phép kiểm tra mọi trường bị chặn.
- `BindingResult.getSuppressedFields()`: danh sách field/property path bị loại qua binder vì không được phép bind. Có thể chọn policy ghi log có kiểm soát, trả 400, hoặc chỉ bỏ qua; quyết định phụ thuộc hợp đồng API.
- `Unknown field`: tên không có property tương ứng, có thể được binder bỏ qua tùy cấu hình. Đừng giả định mọi tham số lạ đều có mặt trong `getSuppressedFields()` hay luôn gây lỗi.
- `setIgnoreUnknownFields(false)` chỉ điều chỉnh cách binder xử lý property không tồn tại trong những thao tác áp dụng, không phải danh sách trường nhạy cảm hay phương án thay thế allowlist.

Nếu cần hợp đồng **strict** (từ chối mọi tham số thừa) thì ngoài allowlist có thể cần đối chiếu tập key request cho phép và key thực tế, xử lý cả nested path, multi-value params và trường do framework gửi (ví dụ token CSRF). Đừng tự tạo kiểm tra chuỗi đơn giản rồi kết luận đã bảo vệ được toàn bộ đường binding; xây dựng test HTTP cho input hợp lệ, bị cấm và bất thường.

## 12. Checklist code review và các bài kiểm thử có giá trị

Khi review một endpoint update có `@ModelAttribute` hoặc `@RequestBody`, trả lời:

1. Object nhận input là **request DTO** hay entity/domain object?
2. Những trường nào thuộc hợp đồng update? Có `role`, `admin`, `ownerId`, `status` hoặc JPA relationship có thể chỉnh sửa ngoài ý muốn không?
3. Với mutable `@ModelAttribute`, có `setAllowedFields` chính xác không? `@InitBinder("...")` có trùng tên attribute không?
4. Có constructor binding không? Constructor có vô tình khai báo trường nhạy cảm? Có cần `setDeclarativeBinding(true)`?
5. Nếu dùng JSON `@RequestBody`, có DTO và chính sách xử lý unknown JSON keys phù hợp không?
6. Khi binder bỏ field, handler có kiểm tra `getSuppressedFields()` và đưa ra quyết định chính sách rõ ràng không?
7. Authorization có xác minh **user + target resource + action** trước khi sửa và lưu không?
8. Có kiểm tra các property lồng nhau/collection/indexed path, giá trị rỗng, kiểu lỗi và trường thừa không?

Bộ kiểm thử nên gồm cả request bình thường và tấn công:

| Input | Kỳ vọng |
| --- | --- |
| `displayName=Lan&bio=Java+learner` | Chấp nhận, chỉ cập nhật hai thuộc tính |
| `displayName=Lan&admin=true` | Bị từ chối hoặc admin không thay đổi, đúng policy |
| `ownerId=7` | Không chuyển quyền sở hữu |
| `role=ADMIN` | Không thay đổi vai trò |
| `addresses[0].isPrimary=true` ngoài allowlist | Không bind property lồng nhau ngoài hợp đồng |
| JSON `{"displayName":"Lan","admin":true}` | JSON DTO không cho gán admin; xử lý key thừa theo policy |
| User A sửa `/profiles/{id}` của User B | Bị từ chối ở tầng authorization, dù body chỉ có allowed fields |

Trong ứng dụng thực, dùng `MockMvc` hoặc HTTP integration test để xác minh cả status, response và **trạng thái database sau request**. Chỉ kiểm tra output JSON mà không kiểm tra record được lưu có thể bỏ sót mass assignment ở service.

## 13. Những lỗi dễ gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Bind trực tiếp vào JPA entity rộng | Client có thể gán thuộc tính nhạy cảm | DTO riêng và explicit update |
| Chỉ ẩn field trong HTML | Client vẫn tự gửi field | Allowlist phía server |
| Chỉ thêm `@Valid` | Giá trị bị cấm vẫn có thể hợp lệ | Validation **kèm** giới hạn binding |
| Dùng `setDisallowedFields` làm lớp chính | Bỏ sót property mới | `setAllowedFields` hoặc constructor DTO |
| Cho phép wildcard quá rộng | Vô tình mở đường cho nested properties | Liệt kê field/path cụ thể |
| Nhầm `setAllowedFields` bảo vệ JSON | Jackson vẫn deserialize object theo cấu hình | JSON request DTO và mapping rõ ràng |
| Quên xem `getSuppressedFields()` | Client gửi field cấm mà không bị phát hiện | Xác định policy cho suppressed field |
| `@InitBinder("name")` khác `@ModelAttribute("name")` | Allowlist không áp đúng target | Đồng nhất tên, kiểm thử HTTP |
| Cho phép bind `id`/`tenantId` từ body | Cross-record/cross-tenant update | Xác định resource ở server, kiểm tra scope |
| Bật `declarativeBinding` toàn cục không kiểm thử | Form cũ ngừng bind property | Rà soát DTO/form và config theo phạm vi |

## 14. Tự kiểm tra

**Câu 1.** Form HTML chỉ có hai input `displayName` và `bio`. Có cần bảo vệ trước `admin=true` không?

**Đáp án:** Có. Client không buộc phải dùng HTML form của ứng dụng; họ có thể tự gửi bất kỳ tham số HTTP nào.

**Câu 2.** `binder.setAllowedFields("displayName", "bio")` có tự trả 400 nếu gửi `admin=true`?

**Đáp án:** Không mặc định. Nó ngăn property binding ngoài allowlist. Ứng dụng có thể đọc `BindingResult#getSuppressedFields()` và chủ động quyết định từ chối, như ví dụ ở mục 6.

**Câu 3.** Có thể chỉ dùng `@InitBinder` để ngăn JSON body gán `role` lên entity của `@RequestBody` không?

**Đáp án:** Không. `@RequestBody` dùng `HttpMessageConverter` (thường là Jackson) để deserialize; hãy nhận JSON bằng request DTO có phạm vi hẹp và chỉ cập nhật field được phép.

**Câu 4.** `setDeclarativeBinding(true)` có chặn mọi input trong constructor không?

**Đáp án:** Không. Constructor binding vẫn hoạt động. Constructor/record phải chỉ chứa trường mà client được phép gửi.

**Câu 5.** Vì sao đã có allowlist `displayName`, `bio` vẫn cần kiểm tra quyền người dùng với ID trên URL?

**Đáp án:** Vì allowlist chỉ quyết định **field** nào được bind, không quyết định **ai** được sửa **bản ghi** nào.

## 15. Tài liệu chính thức

- [Spring Framework — MVC Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html): hướng dẫn model design, allowlist, constructor binding, declarative binding.
- [Spring Framework — `@InitBinder`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html): phạm vi cấu hình binder ở controller và `@ControllerAdvice`.
- [Spring Framework — `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): cách tạo model attribute, nhận request values và tùy chọn `binding=false`.
- [Spring Framework — `@RequestBody`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): chuyển JSON/body bằng `HttpMessageConverter` và validation.
- [Spring Framework — MVC Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): vị trí `BindingResult` và các loại tham số controller.

**Kết luận áp dụng:** Định nghĩa request DTO tối thiểu theo từng thao tác cập nhật, ưu tiên constructor/immutable DTO khi phù hợp, giới hạn property binding qua `@InitBinder#setAllowedFields` khi dùng mutable form, và kiểm tra `getSuppressedFields()` nếu chính sách yêu cầu từ chối trường thừa. Với JSON `@RequestBody`, áp dụng chính sách deserialize riêng. Mọi thay đổi entity phải đi qua kiểm tra quyền và mapping thuộc tính do server kiểm soát.
