# MethodAuthorizationDeniedHandler và @HandleAuthorizationDenied theo phiên bản Spring Security

`MethodAuthorizationDeniedHandler` và `@HandleAuthorizationDenied` là cơ chế **xử lý kết quả bị từ chối ở mức method** của Spring Security. Thay vì lúc nào cũng ném lỗi khi `@PreAuthorize`/`@PostAuthorize` từ chối, ứng dụng có thể chỉ định một handler để trả về giá trị dự phòng (`null`, chuỗi đã che, DTO đã lọc...) hoặc tiếp tục ném exception. Điều này đặc biệt hữu ích khi trả dữ liệu có trường nhạy cảm nhưng không muốn bỏ toàn bộ đối tượng.

**Điểm mấu chốt về phiên bản:** Cả interface `MethodAuthorizationDeniedHandler` và annotation `@HandleAuthorizationDenied` có `@since 6.3` trong Javadoc của Spring Security. Không thể sử dụng hai API này trên Spring Security 6.2 trở xuống. Một số triển khai dựng sẵn xuất hiện muộn hơn; phải kiểm tra Javadoc theo **phiên bản thư viện thực sự nằm trong classpath**.

## 1. Ma trận phiên bản: API nào dùng được?

| Phiên bản Spring Security | `MethodAuthorizationDeniedHandler` | `@HandleAuthorizationDenied` | Cách triển khai phù hợp |
| --- | --- | --- | --- |
| 5.x, 6.0–6.2 | **Chưa có** | **Chưa có** | Giữ từ chối mặc định; nếu cần giá trị fallback, thiết kế DTO/redaction ở lớp ứng dụng hoặc AOP rõ ràng, có test |
| 6.3.x | **Có** (`since 6.3`) | **Có** (`since 6.3`) | Tạo bean handler của riêng ứng dụng; dùng `handlerClass` |
| 6.4.x | **Có** | **Có** | Cùng mô hình xử lý denied invocation/denied result |
| 6.5.x | **Có** | **Có** | Có thể dùng cả custom handler và `NullReturningMethodAuthorizationDeniedHandler` (Javadoc: `since 6.5.0`) |
| 7.0.x, 7.1.x | **Có** | **Có** | Tiếp tục cơ chế handler, kiểm tra Javadoc và cấu hình trên nhánh 7.x |

**Phân biệt Spring Boot với Spring Security:** Spring Boot quản lý phiên bản Spring Security qua dependency management/BOM. Không quyết định sự có mặt API chỉ từ dòng `spring-boot-starter-security` hoặc chỉ từ tên phiên bản Boot. Trong dự án Maven, kiểm tra phiên bản thực tế:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.security
~~~

Trên Windows, có thể chạy `mvnw.cmd dependency:tree -Dincludes=org.springframework.security`. Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
~~~

Nếu `@HandleAuthorizationDenied` hoặc `MethodAuthorizationDeniedHandler` báo `cannot find symbol` / `ClassNotFoundException` trong dự án Spring Security 6.2 hoặc cũ hơn, nguyên nhân là **API chưa tồn tại**, không phải thiếu import đơn thuần. Khi nâng cấp, kiểm tra phiên bản của *toàn bộ* module `spring-security-*` và dùng một BOM nhất quán.

## 2. Cơ chế hoạt động

Method security cần được kích hoạt bằng `@EnableMethodSecurity`. Spring Boot Starter Security **không tự bật method security** chỉ vì dependency có mặt. Các kiểm tra được thực thi qua Spring AOP trên bean do Spring quản lý.

~~~text
Call qua Spring proxy của service
  |
  +-- @PreAuthorize: kiểm tra trước khi gọi method
  |       |
  |       +-- được phép -> chạy method -> trả kết quả thực
  |       |
  |       '-- bị từ chối -> MethodAuthorizationDeniedHandler
  |                             handleDeniedInvocation(...)
  |                             -> fallback / exception
  |                             (method chưa chạy)
  |
  '-- @PostAuthorize: method chạy trước
          |
          +-- được phép -> trả nguyên kết quả
          |
          '-- bị từ chối -> MethodAuthorizationDeniedHandler
                                handleDeniedInvocationResult(...)
                                -> kết quả đã che / fallback / exception
                                (method đã chạy)
~~~

`@HandleAuthorizationDenied(handlerClass = MyDeniedHandler.class)` chỉ định **loại handler**, không phải bean name hay một hàm callback; handler đó phải được đăng ký như Spring bean (chẳng hạn bằng `@Component` hoặc `@Bean`). Annotation có thể khai báo tại method hoặc type, và có thể được dùng làm meta-annotation.

Handler có thể được gọi trong các tình huống tài liệu Spring Security mô tả: từ chối bởi `@PreAuthorize`, `@PostAuthorize` hoặc `AuthorizationDeniedException` được ném trong lời gọi method. **Không mặc định suy rộng hành vi sang mọi loại interceptor, exception hay handler HTTP**.

Phân biệt hai nhánh:

- `@PreAuthorize` từ chối **trước** invocation: method chưa chạy, handler có `MethodInvocation`, không có giá trị trả về thật của method để che. Handler nên trả fallback có kiểu tương thích.
- `@PostAuthorize` từ chối **sau** invocation: method đã chạy, handler có `MethodInvocationResult`, cho phép dùng `getResult()` để che/lọc đầu ra. Không dùng cách này để ngăn thao tác ghi DB, gửi email hoặc side effect khác vì thao tác có thể đã xảy ra.
- Nếu không cung cấp handler thay thế (hoặc chọn handler ném exception), mặc định từ chối được giữ nguyên. Trong luồng HTTP Servlet, Spring Security/ứng dụng có thể chuyển lỗi thành 403 hoặc challenge xác thực tùy hoàn cảnh; **annotation tự nó không quyết định status HTTP**.

## 3. Hai phương thức của interface

Trong package `org.springframework.security.authorization.method`:

~~~java
public interface MethodAuthorizationDeniedHandler {
    Object handleDeniedInvocation(
        MethodInvocation methodInvocation,
        AuthorizationResult authorizationResult
    );

    default Object handleDeniedInvocationResult(
        MethodInvocationResult methodInvocationResult,
        AuthorizationResult authorizationResult
    ) {
        return handleDeniedInvocation(
            methodInvocationResult.getMethodInvocation(),
            authorizationResult
        );
    }
}
~~~

Đây là **dạng rút gọn để giải thích hợp đồng**; chữ ký nullability/annotation có thể được biểu diễn khác nhau giữa các bản Javadoc. Điểm quan trọng là `handleDeniedInvocation(...)` là phương thức cần triển khai, còn `handleDeniedInvocationResult(...)` có triển khai mặc định chuyển về phương thức đầu tiên. Muốn che dựa trên **giá trị thực** sau `@PostAuthorize`, cần override phương thức thứ hai.

| Tham số | Dùng để làm gì |
| --- | --- |
| `MethodInvocation` | Thông tin method được gọi, tham số gọi, metadata của phương thức; hữu ích để xác định fallback thích hợp |
| `AuthorizationResult` | Thông tin kết quả quyết định phân quyền; không nên giả định kiểu cụ thể khi framework chỉ hứa interface |
| `MethodInvocationResult` | Bọc `MethodInvocation` và giá trị đã trả về từ method qua `getResult()` |
| Giá trị trả về `Object` | Phải tương thích với kiểu trả về thật mà Spring proxy chuyển cho caller; có thể là `null` nếu hợp lệ hoặc ném exception |

**Lưu ý về fallback:** Handler có thể trả `null`, trả giá trị giả lập có kiểu thích hợp, hoặc ném `AuthorizationDeniedException`. Dùng `null` cho method trả về primitive như `int`/`boolean` dễ gây lỗi unboxing; các kiểu như `Optional<T>`, collection, DTO cần fallback được thiết kế rõ ràng. Handler chỉ làm thay đổi **kết quả của lời gọi được bảo vệ**, không cấp thêm authority cho người dùng.

## 4. Ví dụ đầy đủ: fallback trước lời gọi và che email sau lời gọi

Ví dụ dựa trên **Java 17+, Spring Boot project có Spring Security 6.3+** (chẳng hạn Spring Security 6.5.x). Các file sau sử dụng package `com.example.demo`. Dự án Spring Boot/Maven phải có `spring-boot-starter-security`; để chạy test, thêm `spring-boot-starter-test` và `spring-security-test` ở scope `test`. Phụ thuộc nên lấy phiên bản từ Spring Boot BOM thay vì tự ghép các version không tương thích.

**`src/main/java/com/example/demo/DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@EnableMethodSecurity` bật các interceptor cho `@PreAuthorize` và `@PostAuthorize`. Không cần tự đăng ký interceptor chỉ để dùng hai annotation này trong cấu hình chuẩn.

**`src/main/java/com/example/demo/RedactingDeniedHandler.java`**

~~~java
package com.example.demo;

import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.method.MethodAuthorizationDeniedHandler;
import org.springframework.security.authorization.method.MethodInvocationResult;
import org.springframework.stereotype.Component;

@Component
public class RedactingDeniedHandler
        implements MethodAuthorizationDeniedHandler {

    // @PreAuthorize từ chối trước khi method chạy:
    // không có kết quả gốc để đọc.
    @Override
    public Object handleDeniedInvocation(
            MethodInvocation invocation,
            AuthorizationResult authorizationResult) {
        return "[HIDDEN]";
    }

    // @PostAuthorize từ chối sau khi method chạy:
    // che phần local-part, chỉ giữ domain trong demo.
    @Override
    public Object handleDeniedInvocationResult(
            MethodInvocationResult invocationResult,
            AuthorizationResult authorizationResult) {
        Object result = invocationResult.getResult();
        if (!(result instanceof String email)) {
            return "[HIDDEN]";
        }
        int at = email.lastIndexOf('@');
        return at > 0 ? "***" + email.substring(at) : "[HIDDEN]";
    }
}
~~~

Vì handler là Spring bean, có thể inject các dependency cần thiết để quyết định chính sách che dữ liệu. Nhưng **tránh log hoặc cache nội dung gốc** chỉ vì handler nhìn thấy giá trị sau lời gọi. Việc giữ domain trong ví dụ nhằm minh họa chức năng `getResult()`; trong hệ thống thật, nếu domain cũng nhạy cảm, hãy trả giá trị hoàn toàn cố định, `null` hoặc DTO không chứa thông tin nhạy cảm.

**`src/main/java/com/example/demo/ContactService.java`**

~~~java
package com.example.demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authorization.method.HandleAuthorizationDenied;
import org.springframework.stereotype.Service;

@Service
public class ContactService {

    private final AtomicInteger noteInvocations = new AtomicInteger();

    @PreAuthorize("hasAuthority('note:read')")
    @HandleAuthorizationDenied(handlerClass = RedactingDeniedHandler.class)
    public String internalNote() {
        noteInvocations.incrementAndGet();
        return "INTERNAL-42";
    }

    @PostAuthorize("hasAuthority('email:read')")
    @HandleAuthorizationDenied(handlerClass = RedactingDeniedHandler.class)
    public String contactEmail() {
        return "alice@example.org";
    }

    @PreAuthorize("hasAuthority('note:read')")
    public String defaultDenied() {
        return "NEVER-EXPOSED";
    }

    public int noteInvocationCount() {
        return noteInvocations.get();
    }
}
~~~

Điểm cần quan sát:
- Không có `note:read`: `internalNote()` trả `[HIDDEN]` và **bộ đếm không tăng**, chứng minh method không chạy.
- Có `note:read`: method chạy, trả `INTERNAL-42`.
- Không có `email:read`: `contactEmail()` đã chạy, nhưng caller chỉ nhận `***@example.org`.
- Có `email:read`: caller nhận `alice@example.org`.
- `defaultDenied()` không gắn `@HandleAuthorizationDenied`, nên vẫn ném exception khi thiếu quyền.

Việc đưa `@HandleAuthorizationDenied` cùng với `@PreAuthorize`/`@PostAuthorize` là quyết định **có chủ đích ở từng method**: không phải cứ bật method security là mọi yêu cầu bị từ chối đều trở thành kết quả che dữ liệu.

## 5. Kiểm thử hành vi bằng JUnit và Spring Security Test

Tệp sau cần dependency `spring-security-test` và `spring-boot-starter-test`. Dùng `@WithMockUser` để đặt `Authentication` có authorities xác định trong `SecurityContext`; gọi bean qua Spring proxy để interceptor hoạt động.

**`src/test/java/com/example/demo/ContactServiceTests.java`**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class ContactServiceTests {

    @Autowired
    ContactService service;

    @Test
    @WithMockUser
    void preAuthorizeDeniedReturnsFallbackWithoutCallingMethod() {
        int before = service.noteInvocationCount();
        assertEquals("[HIDDEN]", service.internalNote());
        assertEquals(before, service.noteInvocationCount());
    }

    @Test
    @WithMockUser(authorities = "note:read")
    void preAuthorizeAllowedReturnsRealValue() {
        int before = service.noteInvocationCount();
        assertEquals("INTERNAL-42", service.internalNote());
        assertEquals(before + 1, service.noteInvocationCount());
    }

    @Test
    @WithMockUser
    void postAuthorizeDeniedMasksActualResult() {
        assertEquals("***@example.org", service.contactEmail());
    }

    @Test
    @WithMockUser(authorities = "email:read")
    void postAuthorizeAllowedReturnsOriginalValue() {
        assertEquals("alice@example.org", service.contactEmail());
    }

    @Test
    @WithMockUser
    void withoutHandlerDenialStillThrows() {
        assertThrows(AccessDeniedException.class, service::defaultDenied);
    }
}
~~~

Chạy kiểm thử trong dự án Maven đã cấu hình Spring Boot và dependencies nêu trên:

~~~bash
./mvnw test
~~~

Trên Windows dùng `mvnw.cmd test`. **Kết quả mong đợi** là cả năm phép kiểm tra đều đạt; đây là kết quả dự kiến theo mã, không phải log chạy thử đã được ghi nhận. Kiểm thử HTTP bằng `MockMvc` là bước bổ sung nếu muốn xác minh mapping đến 401/403/200; test service trực tiếp kiểm tra chính cơ chế handler, độc lập cấu hình HTTP.

## 6. Khi nào nên dùng fallback và khi nào phải từ chối thẳng?

| Bài toán | Khuyến nghị | Lý do |
| --- | --- | --- |
| Thuộc tính không nhạy cảm khi ẩn (ví dụ trả email đã che theo chính sách) | `@PostAuthorize` + handler lọc đầu ra | Có kết quả thật để tạo biến thể an toàn |
| Tính toán/đọc tốn chi phí nhưng người không có quyền có thể nhận một nhãn cố định | `@PreAuthorize` + handler trả fallback | Tránh chạy method trước khi quyết định |
| Ghi DB, chuyển tiền, xóa dữ liệu, gửi email | **Từ chối trước invocation**; thường giữ exception | `@PostAuthorize` không đảo ngược side effect |
| Tài nguyên không được phép tiết lộ dù chỉ domain hay metadata | Trả `null`/mask toàn phần hoặc exception | Kết quả che một phần vẫn có thể làm lộ dữ liệu |
| API cần client phân biệt thiếu quyền để xin cấp quyền | Giữ exception/403 theo chính sách API | Fallback có thể biến response thành 200 gây hiểu nhầm |
| Spring Security 6.2 hoặc cũ hơn | Thiết kế xử lý dữ liệu ở tầng service/DTO hoặc nâng cấp đúng BOM | Annotation/interface này chưa tồn tại |

**Không xem fallback là “bỏ qua bảo mật”.** Việc cho caller nhận một kết quả thay thế cũng là một chính sách bảo mật cần phê duyệt, test quyền, test tenant và test rò rỉ thông tin. Đặc biệt, nếu controller serialize fallback thành HTTP 200, client có thể coi đó là dữ liệu thật: hãy ghi rõ contract (`null`, masked string, cờ `redacted`...), tránh làm hỏng logic nghiệp vụ phía client.

## 7. Xử lý khác biệt phiên bản khi muốn trả null

Nếu yêu cầu chỉ là trả `null` thay vì exception khi bị từ chối, có thể tự viết handler nhỏ áp dụng từ Spring Security **6.3+**:

~~~java
package com.example.demo;

import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.method.MethodAuthorizationDeniedHandler;
import org.springframework.stereotype.Component;

@Component
public class NullDeniedHandler implements MethodAuthorizationDeniedHandler {
    @Override
    public Object handleDeniedInvocation(
            MethodInvocation invocation,
            AuthorizationResult result) {
        return null;
    }
}
~~~

Áp dụng với method có return type chấp nhận `null`:

~~~java
@PreAuthorize("hasAuthority('profile:read')")
@HandleAuthorizationDenied(handlerClass = NullDeniedHandler.class)
public String readProfile() {
    return "visible";
}
~~~

Đoạn method trên **chỉ minh họa cách gắn annotation trong một Spring bean**; phải đặt vào class được Spring quản lý và bật `@EnableMethodSecurity` như ví dụ đầy đủ. Từ Spring Security **6.5.0**, Javadoc còn có `NullReturningMethodAuthorizationDeniedHandler` dựng sẵn. Khi hỗ trợ nhiều nhánh 6.3/6.4/6.5, dùng handler tự định nghĩa như trên để tránh import class chưa có trong 6.3/6.4.

Không nên dùng fallback `null` nếu method trả primitive, hoặc nếu client sẽ lập tức dereference giá trị. Với DTO hoặc JSON, chính sách serialize (giữ trường bằng `null` hay bỏ trường) cũng cần được xác định và kiểm thử riêng.

## 8. Lỗi thường gặp và cách chẩn đoán

1. **Import không tồn tại dù documentation hiện tại có:** mở dependency tree, kiểm tra Spring Security có từ **6.3** hay chưa. Đừng sao chép ví dụ của 7.x vào dự án 6.2.
2. **Có annotation nhưng vẫn ném exception:** xác nhận handler có `@Component`/`@Bean`, method security đã bật, lời gọi đi qua Spring proxy, annotation ở method/type đúng nơi, interceptor có quyền xử lý denial đó.
3. **Gọi từ method khác trong cùng class:** self-invocation qua `this.method()` thường **bỏ qua Spring AOP proxy**, làm `@PreAuthorize` và handler không được thực thi. Tách thành hai Spring bean hoặc dùng thiết kế phù hợp.
4. **Dùng `handleDeniedInvocation` để che kết quả của `@PostAuthorize`:** phương thức mặc định không dùng `getResult()`. Override `handleDeniedInvocationResult` nếu muốn dựa trên kết quả thực.
5. **Trả giá trị sai kiểu:** ví dụ trả chuỗi `"denied"` cho method khai báo `List<Order>` có thể gây lỗi kiểu dữ liệu. Dùng collection rỗng hoặc DTO fallback phù hợp, miễn là chính sách cho phép.
6. **Nghĩ `@PostAuthorize` ngăn được ghi dữ liệu:** method đã chạy trước kiểm tra; phân quyền quan trọng cho mutation phải thực hiện **trước side effect**.
7. **Dựa vào handler để che mọi lỗi:** handler nhằm xử lý denial của method authorization. `NullPointerException`, lỗi database, mọi `AccessDeniedException` bên ngoài các điểm được framework hỗ trợ **không mặc nhiên** bị chuyển thành fallback.
8. **Quên thống nhất HTTP status:** fallback đã thay exception có thể dẫn đến 200 trong controller, không còn 403. Nếu API contract yêu cầu báo thiếu quyền, chọn handler ném exception hoặc dùng thiết kế response có chủ đích.
9. **Test trực tiếp đối tượng `new ContactService()`:** bỏ qua proxy nên annotation không được áp dụng. Test `@Autowired` Spring bean với `@WithMockUser`, kiểm thử cả denied và allowed.
10. **Che email chưa đủ chặt:** domain, độ dài chuỗi, khác biệt thông báo hoặc thời gian phản hồi có thể làm lộ thông tin. Dùng fallback cố định nếu chính sách yêu cầu không tiết lộ sự tồn tại.

## 9. Checklist chọn API cho dự án

- [ ] Đã xác định chính xác version `spring-security-core` và các module liên quan trong dependency tree.
- [ ] Dự án 6.2 trở xuống: không dùng hai API mới; đánh giá nâng cấp hoặc phương án cũ.
- [ ] Dự án 6.3+: bật `@EnableMethodSecurity`, tạo Spring bean implements `MethodAuthorizationDeniedHandler`.
- [ ] Chỉ định `@HandleAuthorizationDenied(handlerClass = ...)` đúng method/type cần fallback.
- [ ] Nếu cần dữ liệu thật sau invocation: override `handleDeniedInvocationResult`.
- [ ] Chọn fallback tương thích return type, đặc biệt primitive/`Optional`/reactive.
- [ ] Không đặt `@PostAuthorize` làm lớp ngăn side effect của thao tác ghi.
- [ ] Test qua proxy: allowed, denied, handler mặc định ném exception, dữ liệu che an toàn.
- [ ] Kiểm tra hợp đồng API/HTTP khi fallback thay đổi đường đi của exception.
- [ ] Dùng Javadoc **đúng nhánh phiên bản** trước khi áp dụng built-in handler mới.

## Tài liệu chính thức để đối chiếu phiên bản

1. [Spring Security 6.5 — Method Security / Providing Fallback Values When Authorization is Denied](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
2. [`MethodAuthorizationDeniedHandler` — API Spring Security 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/MethodAuthorizationDeniedHandler.html) (Javadoc: `since 6.3`).
3. [`@HandleAuthorizationDenied` — API Spring Security 7.1](https://docs.spring.io/spring-security/reference/7.1/api/java/org/springframework/security/authorization/method/HandleAuthorizationDenied.html) (Javadoc: `since 6.3`, tham số `handlerClass`).
4. [`NullReturningMethodAuthorizationDeniedHandler` — API Spring Security 7.1](https://docs.spring.io/spring-security/reference/7.1/api/java/org/springframework/security/authorization/method/NullReturningMethodAuthorizationDeniedHandler.html) (Javadoc: `since 6.5.0`).
5. [Spring Security 7.1 — Method Security](https://docs.spring.io/spring-security/reference/7.1/servlet/authorization/method-security.html).

**Ghi nhớ:** Version hỗ trợ API được xác định bởi Spring Security thật trong build; `@PreAuthorize` và `@PostAuthorize` quyết định **khi nào** từ chối, còn `MethodAuthorizationDeniedHandler` và `@HandleAuthorizationDenied` quyết định **trả gì hoặc ném gì khi bị từ chối**.
