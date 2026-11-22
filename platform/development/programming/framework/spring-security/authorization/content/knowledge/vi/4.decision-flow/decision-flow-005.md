# AuthorizationDecision, AuthorizationResult và API phù hợp phiên bản trong Spring Security

## 1. Mục tiêu: hiểu kết quả phân quyền trước khi chọn API

Khi một yêu cầu đi qua Spring Security, hệ thống phải trả lời: **chủ thể hiện tại có được thực hiện hành động trên tài nguyên đang xét không?** Kết quả đó không phải một đối tượng `Authentication`, cũng không phải mã HTTP `403`. Trong cơ chế phân quyền hiện đại, `AuthorizationManager` đánh giá yêu cầu và trả về một **kết quả phân quyền**. Lớp thực thi (HTTP filter, method interceptor, message security...) mới sử dụng kết quả để cho phép tiếp tục hoặc từ chối.

Bài học này tập trung vào ba khái niệm:

- `AuthorizationDecision` — **lớp kết quả cụ thể** biểu diễn allow/deny.
- `AuthorizationResult` — **giao diện kết quả** có phương thức `isGranted()`, giúp API không bị khóa cứng vào một lớp duy nhất.
- `AuthorizationManager<T>` — **bộ đánh giá** nhận `Supplier<Authentication>` và một đối tượng ngữ cảnh kiểu `T`; chữ ký phương thức thay đổi theo phiên bản Spring Security.

Sau khi học, bạn có thể:

1. Phân biệt kết quả phân quyền với bộ kiểm tra, exception và HTTP status.
2. Viết và đọc đúng `check(...)`/`authorize(...)`/`verify(...)` theo phiên bản thư viện.
3. Nhận ra vì sao `AuthorizationResult` đã tồn tại nhưng mã nguồn cũ vẫn trả `AuthorizationDecision`.
4. Tạo custom `AuthorizationManager` cho HTTP theo API của Spring Security 6.3, 6.4–6.5 và 7.x mà không trộn chữ ký.
5. Chọn cách tích hợp phù hợp giữa `authorizeHttpRequests`, `@PreAuthorize` và custom policy.
6. Viết kiểm thử cho quyết định `ALLOW`, `DENY` và rủi ro `null`/abstain, không chỉ test status code.

**Lưu ý cốt lõi:** tên class và API thay đổi theo phiên bản. Không sao chép nguyên xi snippet từ nhánh tài liệu "current" vào một dự án dùng Spring Security 6.3 hoặc 6.5 mà không kiểm tra dependency thực tế.

## 2. Mô hình quyết định của Spring Security

```text
HTTP request / method invocation / message
                  │
                  ▼
        Authentication hiện có
    (danh tính + GrantedAuthority)
                  │
                  ▼
           AuthorizationManager<T>
        ┌─────────────────────────┐
        │ Supplier<Authentication>│
        │ secure object/context T │
        │ policy theo nghiệp vụ   │
        └────────────┬────────────┘
                     │
             AuthorizationResult
               /           \
          granted=true   granted=false
               │             │
               ▼             ▼
        tiếp tục xử lý   từ chối truy cập
                         (exception/filter)
```

**Bốn phần cần tách bạch:**

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `Authentication` | Chủ thể đã đăng nhập hoặc cơ chế xác thực hiện hành, kèm authorities | `ROLE_EDITOR`, `document:read` |
| `T` trong `AuthorizationManager<T>` | Đối tượng/metadata cần kiểm tra quyền | `RequestAuthorizationContext`, `MethodInvocation` |
| `AuthorizationManager<T>` | Chạy chính sách phân quyền | Kiểm tra permission, tenant, resource state |
| `AuthorizationResult` / `AuthorizationDecision` | Cho biết **có được cấp quyền hay không** | `new AuthorizationDecision(true)` |

`AuthorizationResult` không có chức năng nạp user hay giải mã JWT. `AuthorizationDecision` không tự chặn request. Việc từ chối thực sự nằm ở nơi **tiêu thụ** kết quả phân quyền.

Quyết định theo chức năng và quyết định theo đối tượng có thể được kết hợp: có `document:edit` là điều kiện cần; khi sửa `document d7`, service vẫn phải kiểm tra owner, tenant và trạng thái tài liệu. Custom manager có thể sử dụng thêm dữ liệu đó, nhưng framework **không tự biết** quy tắc domain nếu ứng dụng chưa triển khai.

## 3. Phân biệt AuthorizationDecision và AuthorizationResult

### 3.1. AuthorizationDecision — lớp có thể khởi tạo

`AuthorizationDecision` nằm trong package:

```text
org.springframework.security.authorization.AuthorizationDecision
```

Một quyết định allow/deny thông thường:

```java
AuthorizationDecision allow = new AuthorizationDecision(true);
AuthorizationDecision deny  = new AuthorizationDecision(false);

boolean a = allow.isGranted();  // true
boolean d = deny.isGranted();   // false
```

Lớp có constructor `AuthorizationDecision(boolean granted)` và `isGranted()`. Khi code policy chỉ cần trả true/false, đây là dạng biểu diễn đơn giản, rõ ràng.

### 3.2. AuthorizationResult — giao diện hợp đồng

`AuthorizationResult` ở cùng package, có `isGranted()` và kế thừa `Serializable`. Nó được giới thiệu trong dòng **Spring Security 6.3**. `AuthorizationDecision` **implements AuthorizationResult**.

```java
AuthorizationResult result = new AuthorizationDecision(true);
System.out.println(result.isGranted()); // true
```

Ví dụ trên chỉ áp dụng khi dự án có `AuthorizationResult` (6.3 trở lên). Dùng kiểu trả về giao diện cho phép framework/ứng dụng sử dụng các loại kết quả khác nhau, thay vì buộc mọi kết quả luôn là `AuthorizationDecision`.

**Không hiểu nhầm:**

- `AuthorizationResult` là **interface**, không dùng `new AuthorizationResult(...)`.
- `AuthorizationDecision` là **class**, có thể tạo bằng `new AuthorizationDecision(boolean)`.
- `AuthorizationResult` không phải kiểu mới "thay thế hoàn toàn" `AuthorizationDecision`; lớp cụ thể vẫn là cách hợp lệ để tạo kết quả trong các phiên bản hiện đại.
- Dù nhiều API chuyển sang trả `AuthorizationResult`, bạn vẫn có thể return `new AuthorizationDecision(allowed)` vì nó thực thi interface đó.

### 3.3. Đọc kết quả mà không ép kiểu

**Nên làm** khi API đã trả `AuthorizationResult`:

```java
AuthorizationResult result = manager.authorize(authenticationSupplier, context);
boolean allowed = result != null && result.isGranted();
```

Cách kiểm tra ở trên **cố ý fail closed trong mã ứng dụng tự viết**: `null` không được coi là allow. Nó là cách xử lý minh họa để ứng dụng tự đưa ra quyết định chắc chắn, không phải tuyên bố mọi interceptor của framework luôn diễn giải `null` là deny.

**Tránh**:

```java
AuthorizationDecision decision =
        (AuthorizationDecision) manager.authorize(authenticationSupplier, context);
```

Lý do: API công bố `AuthorizationResult`, không hứa mọi implementation đều trả đúng lớp `AuthorizationDecision`. Ép kiểu có thể gây `ClassCastException` khi dùng subclass/result khác. Tốt hơn hãy đọc `isGranted()` trên giao diện, hoặc sử dụng dữ liệu bổ sung theo hợp đồng của implementation cụ thể nếu cần.

### 3.4. Kết quả DENY không đồng nghĩa với exception ngay lập tức

`new AuthorizationDecision(false)` chỉ là **dữ liệu quyết định từ chối**. Tùy nơi sử dụng, bộ phận enforcement có thể ném `AccessDeniedException`, dừng method, xử lý sự kiện hoặc chuyển thành HTTP `403`. Một manager tự trả false **không tự gửi HTTP response**.

Ngược lại, `verify(...)` là convenience API của `AuthorizationManager`: gọi chính sách rồi có thể **ném `AccessDeniedException` khi bị từ chối**. Khi chỉ cần kết quả để log, test hoặc tổ hợp policy, dùng `authorize(...)` theo phiên bản phù hợp; khi mục tiêu là yêu cầu quyền hoặc thất bại bằng exception, cân nhắc `verify(...)`.

## 4. Ma trận phiên bản: 6.3, 6.4–6.5 và 7.x

Đây là phần quan trọng nhất của bài:

| Dòng Spring Security | Phương thức chính trên `AuthorizationManager<T>` | Kiểu trả về | Ghi chú |
| --- | --- | --- | --- |
| **6.3.x** | `check(Supplier<Authentication>, T)` | `AuthorizationDecision` (có thể `null`) | `check` là abstract method; **chưa có `authorize` trên interface này** |
| **6.4.x** | `authorize(Supplier<Authentication>, T)` | `AuthorizationResult` (có thể `null`) | `authorize` được **thêm dưới dạng default method**; `check` còn nhưng **deprecated** |
| **6.5.x** | `authorize(Supplier<Authentication>, T)` | `AuthorizationResult` (có thể `null`) | `check` vẫn tồn tại/deprecated; để implement interface, `check` còn là abstract method trong các Javadoc 6.5 |
| **7.0+** | `authorize(Supplier<? extends Authentication>, T)` (nullability annotations có thể hiện trong Javadoc) | `AuthorizationResult` (có thể `null`) | `authorize` là **abstract method**; `check` **đã bị xóa khỏi interface** |

**Phân biệt hai mốc:**

- Spring Security **6.3**: có kiểu `AuthorizationResult`, nhưng `AuthorizationManager` lúc đó vẫn dùng `check(...)`.
- Spring Security **6.4**: mới bổ sung `AuthorizationManager.authorize(...)` và deprecate `check(...)` để API trả về interface `AuthorizationResult`.
- Spring Security **7.x**: loại bỏ `check(...)` khỏi interface, dùng `authorize(...)` làm điểm triển khai.

Đừng nhầm thời điểm **giới thiệu interface** với thời điểm **thay đổi chữ ký AuthorizationManager**. Trong dự án cũ, code dùng `check` có thể vẫn đúng với phiên bản đó; trong dự án mới, không nên lấy ví dụ `check` cũ làm mẫu mặc định.

### 4.1. Cùng tên, khác vai trò: check, authorize, verify

```text
6.3:
  AuthorizationDecision check(Supplier<Authentication>, T)
  default void verify(Supplier<Authentication>, T)

6.4 / 6.5:
  @Deprecated AuthorizationDecision check(Supplier<Authentication>, T)
  default AuthorizationResult authorize(Supplier<Authentication>, T)
  default void verify(Supplier<Authentication>, T)

7.x:
  AuthorizationResult authorize(Supplier<? extends Authentication>, T)
  default void verify(Supplier<? extends Authentication>, T)
  [check() không còn là thành viên interface]
```

Chữ ký trên mô tả dạng tổng quát, bỏ bớt annotations để dễ đọc. Khi copy code hãy đối chiếu **Javadoc trùng phiên bản được quản lý bởi BOM/parent POM**. Đặc biệt Spring Boot quản lý phiên bản Spring Security; không suy từ phiên bản Java hoặc từ một snippet trên internet.

### 4.2. Ý nghĩa khi viết custom manager

Trong **6.3** và **6.4–6.5**, viết:

```java
@Override
public AuthorizationDecision check(
        Supplier<Authentication> authentication, T context) {
    return new AuthorizationDecision(true);
}
```

là cách đáp ứng abstract method của interface ở các dòng đó. Với 6.4–6.5, code gọi `authorize(...)` có thể sử dụng default implementation kế thừa từ interface, tùy manager. **Không sửa thành chỉ override `authorize` rồi xóa `check` ở 6.5** nếu interface đó vẫn yêu cầu `check`; project có thể báo lỗi class chưa implement abstract method.

Trong **7.x**, interface yêu cầu triển khai `authorize(...)`:

```java
@Override
public AuthorizationResult authorize(
        Supplier<? extends Authentication> authentication, T context) {
    return new AuthorizationDecision(true);
}
```

Đoạn minh họa dùng kiểu generic `T`; implementation thật cần khai báo `T` ở class, ví dụ `RequestAuthorizationContext`. Khi nâng cấp từ 6.5 lên 7, đổi method triển khai và kiểm tra build; một `@Override` trên `check` sẽ báo lỗi vì method không còn ở interface.

### 4.3. Tại sao không dán một implementation dùng cho mọi phiên bản?

Có khác biệt về **abstract/default method** và **generic signature**. Một đoạn code "tưởng như giống nhau" có thể:

- Biên dịch ở 6.5 vì implement `check`, nhưng không còn implement `authorize` bắt buộc ở 7.
- Dùng `authorize` trong module 6.3, gây lỗi **cannot find symbol**.
- Override `authorize(Supplier<Authentication>, ...)` theo 6.5 trong một class 7.x có chữ ký wildcard khác, dẫn tới lỗi **name clash**/**does not override** tùy code.
- Chỉ test với một version rồi áp dụng cho một repository có nhiều service dùng BOM khác nhau.

**Cách chắc chắn:** mỗi module chọn đúng API theo resolved dependency; nâng phiên bản theo từng mốc có biên dịch + integration test. Đối với public library phải hỗ trợ nhiều dòng, cân nhắc adapter/module tách riêng theo version, không dựa vào cast hoặc reflection tùy tiện.

## 5. `null`, abstain và nguyên tắc fail closed

Javadoc cho phép kết quả `null` khi một manager **không đưa ra quyết định** (abstain). Đây **không phải** tương đương tuyệt đối với `new AuthorizationDecision(false)`:

| Kết quả | Ý nghĩa ở tầng policy | Cách hiểu an toàn trong ứng dụng tự viết |
| --- | --- | --- |
| `new AuthorizationDecision(true)` | Có quyết định cho phép | ALLOW, nếu các điều kiện bắt buộc khác đạt |
| `new AuthorizationDecision(false)` | Có quyết định từ chối | DENY |
| `null` | Không đưa ra quyết định / abstain | Không tự coi là cho phép; cần quy tắc hợp nhất rõ |

Ở một số interceptor hoặc bộ kết hợp, abstain có thể có hành vi khác negative decision. Tài liệu của `AuthorizationManager.verify` mô tả ném exception khi có **negative** decision, không cho phép kết luận rằng `null` luôn bị chặn như false ở mọi nơi.

Với policy bảo vệ dữ liệu nhạy cảm, nên **trả kết quả tường minh** và cấu hình fallback từ chối:

```java
boolean allowed = actor != null
        && actorHasPermission(actor, "document:read")
        && sameTenant(actor, document)
        && canReadObject(actor, document);
return new AuthorizationDecision(allowed);
```

Đây là **pseudocode method body**, các hàm `actorHasPermission`, `sameTenant`, `canReadObject` do ứng dụng định nghĩa. Nếu thiếu actor/resource hoặc repository lỗi, không mặc định trả allow. Tùy nghiệp vụ có thể phân biệt lỗi hạ tầng với access denied, nhưng không được vô tình cấp quyền.

### 5.1. Không tự ép "null = DENY" rồi nghĩ framework cũng như vậy

Trong mã ứng dụng tự gọi manager, ta có thể chọn:

```java
AuthorizationResult result = manager.authorize(authSupplier, resource);
boolean explicitlyGranted = result != null && result.isGranted();
```

Cách này là **chính sách fail closed do ứng dụng đặt ra**, không phải bản mô tả hành vi ngầm của toàn framework. Nếu viết custom `AuthorizationManager`, tốt nhất tránh `null` trừ khi thật sự thiết kế cơ chế abstain có quy tắc kết hợp/điểm cuối.

### 5.2. Không dựa riêng vào mã HTTP

- `401 Unauthorized` thường phản ánh chưa được xác thực trên một API yêu cầu authentication.
- `403 Forbidden` thường phản ánh caller đã xác thực nhưng không có quyền.
- `404 Not Found` đôi khi được sản phẩm chủ động dùng để không lộ sự tồn tại của một resource.

Các mã cụ thể phụ thuộc `AuthenticationEntryPoint`, `AccessDeniedHandler`, CSRF, và contract API. Kiểu `AuthorizationDecision`/**`AuthorizationResult` không phải mã HTTP**, nên unit test chính sách và integration test HTTP cần tách riêng.

## 6. Ví dụ code cho Spring Security 6.3 đến 6.5

### 6.1. Custom HTTP AuthorizationManager ở 6.3, 6.4 và 6.5

Ví dụ bảo vệ hành động đọc báo cáo dựa trên authority `report:read`. Đây là **mã tích hợp trong project Spring Security Servlet** có đầy đủ dependencies, không chạy bằng `javac` thuần.

Tạo một class theo package ứng dụng của bạn:

```java
import java.util.function.Supplier;

import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class ReportReadAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        // get() có thể trả null hoặc ném exception nếu chưa có Authentication.
        Authentication current;
        try {
            current = authentication.get();
        } catch (AuthenticationCredentialsNotFoundException ex) {
            return new AuthorizationDecision(false);
        }

        boolean allowed = current != null
                && current.getAuthorities().stream().anyMatch(authority ->
                        "report:read".equals(authority.getAuthority()));

        return new AuthorizationDecision(allowed);
    }
}
```

Ở đây `AuthenticationCredentialsNotFoundException` được xử lý minh họa để **fail closed**; ứng dụng thực nên quyết định có giữ nguyên `AuthenticationException` cho cơ chế entry point hay không. Không nên bắt `Exception` tổng quát rồi trả allow. Việc xác thực token/session và ánh xạ authority phải diễn ra trước khi custom manager đánh giá. Nếu không có `report:read`, kết quả là `false`.

**Mức phiên bản:**

- `check` này tương thích với chữ ký abstract trong **6.3**.
- Trong **6.4–6.5**, `check` vẫn có thể compile nhưng sẽ có cảnh báo `@Deprecated`; giao diện cung cấp `authorize(...)` default cho người gọi.
- Đoạn này **không phải implementation dùng nguyên xi cho 7.x**.

**Tùy chọn quản lý migration 6.4–6.5:** có thể vẫn override `check` và cho caller mới dùng `authorize` (default). Nếu code phức tạp cần kiểm soát hoàn toàn kết quả, hãy kiểm tra Javadoc/behavior của manager cụ thể; đừng giả định mọi subclass đều được gọi qua cùng một đường.

### 6.2. Cấu hình HTTP bằng manager

Trong class `@Configuration`, tạo/tiêm bean `ReportReadAuthorizationManager` rồi dùng:

```java
@Bean
SecurityFilterChain filterChain(
        HttpSecurity http,
        ReportReadAuthorizationManager reportReadManager) throws Exception {

    return http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/reports/*")
                .access(reportReadManager)
            .anyRequest().denyAll()
    ).build();
}
```

Đây là **fragment Spring Security Servlet**, cần imports của `@Bean`, `SecurityFilterChain`, `HttpSecurity`, `HttpMethod` và component/bean manager đã được đăng ký. Nguyên tắc kiểm tra là phân quyền dựa trên `AuthorizationManager<RequestAuthorizationContext>` cho route cụ thể, không tạo HTTP response bên trong manager.

Nếu không có chính sách đặc thù, cách ngắn gọn hơn là dùng built-in:

```java
.requestMatchers(HttpMethod.GET, "/api/reports/*")
    .hasAuthority("report:read")
```

Đừng tạo custom manager chỉ để thay `hasAuthority` khi không cần thêm policy. Ví dụ custom được dùng ở đây để quan sát rõ kiểu trả về và cách tích hợp.

## 7. Ví dụ code cho Spring Security 7.x

Ở Spring Security **7.x**, `AuthorizationManager.check(...)` không còn là member của interface. Implementation cần override `authorize(...)` và có thể trả `AuthorizationResult`. Đoạn sau là **class thay thế** cho class 6.x, không đặt đồng thời hai class trùng tên trong cùng package:

```java
import java.util.function.Supplier;

import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class ReportReadAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    @Override
    public AuthorizationResult authorize(
            Supplier<? extends Authentication> authentication,
            RequestAuthorizationContext context) {

        Authentication current;
        try {
            current = authentication.get();
        } catch (AuthenticationCredentialsNotFoundException ex) {
            return new AuthorizationDecision(false);
        }

        boolean allowed = current != null
                && current.getAuthorities().stream().anyMatch(authority ->
                        "report:read".equals(authority.getAuthority()));

        return new AuthorizationDecision(allowed);
    }
}
```

`AuthorizationResult` là interface, còn `new AuthorizationDecision(allowed)` là implementation hợp lệ. `authorize(...)` trong đoạn 7.x là method phải implement; `check(...)` không còn là phương thức để override.

Cùng fragment `SecurityFilterChain` ở mục 6.2 có thể sử dụng manager phiên bản 7.x đã thay, với những API cấu hình HTTP tương ứng bản 7 của project.

### 7.1. Vì sao Supplier thay vì lấy Authentication ngay từ đầu?

Việc nhận `Supplier<Authentication>` cho phép framework **trì hoãn** truy xuất authentication tới khi thực sự cần đánh giá quyền. Custom code không nên gọi `get()` nhiều lần nếu không cần thiết; có thể lấy một lần, dùng giá trị đó để tính kết quả. Với `permitAll` hoặc policy không cần principal, framework có thể tránh tải authentication không cần thiết.

### 7.2. Không gán kiểu trả về quá hẹp

Trong 7.x, nên khai báo manager theo interface:

```java
AuthorizationResult result = manager.authorize(authSupplier, context);
if (result != null && result.isGranted()) {
    // Cho phép bước tiếp theo, nếu các điều kiện nghiệp vụ khác đã đạt.
}
```

Đoạn trên dùng các biến đã tồn tại trong project, không phải chương trình chạy độc lập. Tránh ép `AuthorizationResult` sang `AuthorizationDecision` nếu không kiểm soát cụ thể implementation.

## 8. Khác nhau giữa API của người triển khai và của người sử dụng

Một thay đổi dễ bỏ sót khi upgrade là **call site** và **implementation site** không đổi giống nhau.

| Vai trò trong code | 6.3 | 6.4–6.5 | 7.x |
| --- | --- | --- | --- |
| **Implementation** custom `AuthorizationManager` | Override `check` | Vẫn cần triển khai `check` theo interface 6.x; `authorize` có default | Override `authorize` |
| **Caller** muốn lấy kết quả | Gọi `check`, nhận `AuthorizationDecision` | Nên gọi `authorize`, nhận `AuthorizationResult` | Gọi `authorize`, nhận `AuthorizationResult` |
| **Caller** muốn buộc quyền | Dùng `verify` hoặc interceptor thích hợp | Dùng `verify` hoặc interceptor | Dùng `verify` hoặc interceptor |
| **Đọc trạng thái** | `isGranted()` | `isGranted()` | `isGranted()` |
| **Trả kết quả đơn giản** | `new AuthorizationDecision(boolean)` | Như cũ, tương thích `AuthorizationResult` | Như cũ, tương thích `AuthorizationResult` |

### 8.1. Caller: mã 6.3 và mã 6.5/7

**6.3:**

```java
// Trong dự án đã có manager, authSupplier, context:
AuthorizationDecision decision = manager.check(authSupplier, context);
boolean allowed = decision != null && decision.isGranted();
```

**6.4, 6.5 và 7.x:**

```java
// Trong dự án đã có manager, authSupplier, context:
AuthorizationResult result = manager.authorize(authSupplier, context);
boolean allowed = result != null && result.isGranted();
```

Đây là các fragment minh họa API call; không tự định nghĩa biến hoặc dependencies. `allowed` ở đây là kết quả đánh giá **của manager đó**, không bảo đảm vượt qua mọi kiểm tra khác của ứng dụng.

### 8.2. Verify: dùng khi cần cơ chế "deny bằng exception"

```java
// API có trên AuthorizationManager:
manager.verify(authSupplier, context);
```

Nếu bị từ chối, `verify` có thể ném `AccessDeniedException`; nếu quyết định cho phép, lời gọi có thể kết thúc bình thường. Với kết quả `null`, phải đọc contract phiên bản và quy tắc điểm chặn cụ thể, không suy thành deny.

Dùng `verify` khi một use case cần chuyển quyết định thành rào chắn. Tuy nhiên không nên **gọi verify rồi xem như đã kiểm tra mọi quyền trên resource** nếu manager chỉ làm `hasAuthority("report:read")`. Các ràng buộc tenant/owner/state còn phải có ở policy khác.

### 8.3. Spring Security 7 và API thế hệ cũ

`AuthorizationManager` là mô hình hiện đại thay cho các thiết kế cũ như `AccessDecisionManager`/`AccessDecisionVoter`. Trong Spring Security 7, một số thành phần *Access API* cũ được chuyển sang module legacy `spring-security-access`. Không nhầm công việc **đổi `check` sang `authorize`** với việc **chuyển toàn bộ ứng dụng từ voter/decision-manager cũ sang AuthorizationManager**: đây là hai trục migration liên quan nhưng khác nhau.

Nếu project đang dùng `AccessDecisionVoter` hoặc cấu hình cổ điển, cần lập kế hoạch riêng. Bài này hướng dẫn quyết định của **AuthorizationManager**, không khuyến nghị tiếp tục thiết kế mới dựa trên voter API cũ.

## 9. Method security và kết quả quyết định

### 9.1. @PreAuthorize là đường sử dụng phổ biến

Trong nhiều project, không cần viết `AuthorizationManager<MethodInvocation>` thủ công: dùng `@EnableMethodSecurity` và `@PreAuthorize` để mô tả rule.

```java
// Fragment trong Spring-managed @Service; cần bật @EnableMethodSecurity.
@PreAuthorize("hasAuthority('report:read')")
public ReportView readReport(String reportId) {
    return reportService.load(reportId);
}
```

Với biểu thức trên, Spring Security dùng các thành phần authorization nội bộ để đánh giá permission khi method được gọi qua interceptor. Bạn **không cần tự tạo** `AuthorizationDecision` trong method. Đừng nghĩ `@PreAuthorize` có nghĩa “Java method bắt buộc return AuthorizationResult”: method nghiệp vụ vẫn return `ReportView`.

### 9.2. Policy trên đối tượng

Ví dụ cùng quyền chức năng nhưng phải đọc báo cáo đúng tenant/owner:

```java
@PreAuthorize("hasAuthority('report:read') and " +
        "@reportPolicy.canRead(authentication, #reportId)")
public ReportView readReport(String reportId) {
    return reportService.load(reportId);
}
```

Bean `reportPolicy` do ứng dụng tự triển khai: nạp report đáng tin, kiểm tra cùng tenant, quan hệ được chia sẻ, trạng thái; `#reportId` cần tên tham số khả dụng khi runtime (ví dụ `-parameters` hoặc cơ chế annotation phù hợp). Đây không phải syntax tự cấp quyền cho mọi report.

### 9.3. Khi nào cần custom manager cho method?

Chọn `AuthorizationManager<MethodInvocation>` khi bạn cần cơ chế chung phức tạp, integration ở interceptor, dữ liệu invocation hoặc policy không thuận tiện diễn đạt bằng SpEL. Kiểu ngữ cảnh method thường liên quan `MethodInvocation`, khác `RequestAuthorizationContext` dành cho HTTP.

- Không lấy một `AuthorizationManager<RequestAuthorizationContext>` rồi ép kiểu thành manager dùng cho `MethodInvocation`.
- Đừng giả định một method security interceptor tự chặn mọi cách gọi: self-invocation trong cùng bean có thể bỏ qua proxy.
- Nếu có request HTTP bảo vệ và method bảo vệ, cả hai điều kiện thực sự chạy phải được đáp ứng; chúng có thể là hai rule bổ sung, nhưng cần được tài liệu hóa và test.

### 9.4. Return giá trị giả khi deny không phải đường mặc định

Thông thường, không đạt `@PreAuthorize` khiến lời gọi bị chặn bằng exception; method không được chạy. Spring Security một số dòng mới có khả năng tùy biến cách xử lý denied method invocation, nhưng không nên mặc định mọi version đều hỗ trợ cùng annotation/handler. Khi chỉ cần **chặn truy cập**, ưu tiên rule rõ ràng thay vì tự triển khai fallback trả `null` hoặc “một đối tượng rỗng” có thể che lỗi bảo mật.

## 10. Ví dụ Java 17 chạy độc lập để hiểu hợp đồng kết quả

Đoạn Java thuần dưới đây mô phỏng một **result interface** và một **decision class** để hình dung quan hệ interface/implementation. Chúng **không phải** các class thật của Spring; chương trình không cần dependency framework và dùng tên `Local...` để tránh nhầm. Code Spring thực ở mục 6–7.

Tạo file `AuthorizationResultConceptDemo.java`:

```java
import java.util.Set;

public class AuthorizationResultConceptDemo {

    interface LocalAuthorizationResult {
        boolean isGranted();
    }

    record LocalAuthorizationDecision(boolean granted)
            implements LocalAuthorizationResult {

        @Override
        public boolean isGranted() {
            return granted;
        }
    }

    record Actor(String name, Set<String> permissions) {
        Actor {
            permissions = permissions == null
                    ? Set.of() : Set.copyOf(permissions);
        }
    }

    record Report(String id, String owner) {}

    static LocalAuthorizationResult authorize(Actor actor, Report report) {
        boolean allowed = actor != null
                && report != null
                && actor.name() != null
                && actor.permissions().contains("report:read")
                && actor.name().equals(report.owner());

        return new LocalAuthorizationDecision(allowed);
    }

    static String label(LocalAuthorizationResult result) {
        // Ứng dụng chủ động fail closed với kết quả chưa quyết định.
        return result != null && result.isGranted() ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
                "alice", Set.of("report:read"));
        Actor bob = new Actor(
                "bob", Set.of("report:read"));
        Actor guest = new Actor(
                "guest", Set.of());
        Report report = new Report("r7", "alice");

        System.out.println("owner=" + label(authorize(alice, report)));
        System.out.println("same-permission-other-owner="
                + label(authorize(bob, report)));
        System.out.println("missing-permission="
                + label(authorize(guest, report)));
        System.out.println("missing-authentication="
                + label(authorize(null, report)));
        System.out.println("missing-resource="
                + label(authorize(alice, null)));
        System.out.println("abstain-fail-closed=" + label(null));

        LocalAuthorizationResult allowed = authorize(alice, report);
        System.out.println("result-interface=" + allowed.isGranted());
        System.out.println("decision-class="
                + allowed.getClass().getSimpleName());
    }
}
```

Lệnh JDK 17+:

```bash
javac AuthorizationResultConceptDemo.java
java AuthorizationResultConceptDemo
```

Kết quả stdout:

```text
owner=ALLOW
same-permission-other-owner=DENY
missing-permission=DENY
missing-authentication=DENY
missing-resource=DENY
abstain-fail-closed=DENY
result-interface=true
decision-class=LocalAuthorizationDecision
```

**Phân tích:**

1. Phương thức trả về **interface** `LocalAuthorizationResult`, nhưng thực tế trả một instance của **class/record** `LocalAuthorizationDecision`. Đây là ý tưởng tương ứng với `AuthorizationResult` và `AuthorizationDecision`.
2. Cùng permission `report:read` chưa đủ nếu Bob không phải chủ tài nguyên. Bài toán authorization không dừng ở việc tạo kết quả boolean.
3. `label(null)` trả `DENY` vì chương trình này **tự định nghĩa fail closed**. Không đem quy tắc này gán mặc định cho mọi manager/interceptor Spring Security.
4. Trong framework thật, `AuthorizationManager` còn có Supplier<Authentication>, secure object và lifecycle của HTTP/method interceptor.

Nếu tạo class giả lập có tên giống package `org.springframework.security.authorization` để chạy mà không có thư viện, người học dễ hiểu nhầm. Vì vậy ví dụ giữ tiền tố `Local`, còn mẫu Spring thực ở mục 6 và 7 được ghi rõ là fragment tích hợp.

## 11. Kiểm thử đúng phiên bản và đúng hợp đồng

### 11.1. Test trực tiếp custom manager

Đối với manager 6.3–6.5 ở mục 6, test giả định:

```text
Authentication có authority "report:read"    -> granted = true
Authentication chỉ có "report:write"          -> granted = false
Authentication rỗng authorities               -> granted = false
Authentication null / thiếu xác thực          -> không được ALLOW
```

Với 6.3, dùng `manager.check(...).isGranted()`. Với 6.4–6.5, ưu tiên `manager.authorize(...).isGranted()` để thực hành caller API mới. Với 7.x, chỉ dùng `authorize(...)`. Đây là cách đối chiếu behavior, không phải một test file chạy độc lập.

**Đặc biệt:** test mã nguồn được compile dưới **đúng BOM/version**, không chỉ test hành vi bằng Mockito. Một mock cho interface cũ có thể che việc `@Override` đã không còn hợp lệ trên version mới.

### 11.2. Test HTTP thực sự

Một `AuthorizationDecision(true)` ở custom manager không bảo đảm request cuối cùng thành `200 OK`. Request có thể tiếp tục qua CSRF, business validation, kiểm tra tenant, controller, exception handler hoặc bộ bảo mật khác. Vì vậy:

- Test một request hợp lệ với `report:read` và resource mà test user được phép xem.
- Test thiếu `report:read`, thử cả cùng một route và một route khác.
- Test endpoint không có matcher nằm dưới `anyRequest().denyAll()`.
- Test phân biệt `401`/`403`/redirect login theo cấu hình authentication entry point.
- Test `@PreAuthorize` với lời gọi từ bean đã được Spring proxy.
- Test object authorization: có permission nhưng sai owner/tenant vẫn phải bị chặn.
- Với request thay đổi dữ liệu, cung cấp CSRF token phù hợp nếu ứng dụng yêu cầu, không nhầm từ chối CSRF với logic manager.

### 11.3. Test "null" và exception

Nên có test cho manager custom nếu code cho phép `null`. Kiểm tra **hành vi của bộ phận tiêu thụ**: khi manager abstain, có manager nào khác xử lý không, route có fallback deny không, và request có bị cho phép ngoài ý định không. Đừng chỉ assert `result == null` rồi xem như đã an toàn.

Với `verify`, xác minh exception xảy ra khi **quyết định âm tính**; test cho positive decision hoạt động bình thường. Đừng bắt `AccessDeniedException` rồi tiếp tục ghi dữ liệu nếu business action đòi quyền bắt buộc.

### 11.4. Test nâng cấp 6.5 → 7.x

1. Nâng version bằng một BOM/parent POM thống nhất; đọc dependency tree/version thực chạy.
2. Biên dịch **custom implementer `AuthorizationManager`** trước: chuyển `check` sang `authorize` đúng kiểu trả về.
3. Tìm mọi caller của `manager.check(...)` và chuyển sang `authorize(...)`, dùng kiểu `AuthorizationResult`.
4. Rà soát các custom adapter, method interceptor, event publisher hoặc logger đang nhận `AuthorizationDecision` thay vì `AuthorizationResult`.
5. Xóa ép kiểu `(AuthorizationDecision) result` không cần thiết.
6. Test trên cả HTTP, method security, async/batch/message flow nếu project có.
7. Kiểm tra role/authority mappings, cache và policy đối tượng không đổi hành vi.
8. Kiểm tra cả `ALLOW`, `DENY` và trường hợp thiếu dữ liệu/abstain trước khi deploy.

Đổi method tên là một phần của migration, nhưng **không bảo đảm tương đương ngữ nghĩa** nếu manager cũ dùng `null`, quy tắc ghép quyền hay exception handling khác. Integration test giữ vai trò quyết định.

## 12. Lỗi thường gặp khi học và triển khai

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| "Có AuthorizationResult từ 6.3 thì 6.3 dùng authorize(...)" | Nhầm mốc ra đời interface với mốc thêm method | 6.3 dùng `check`; `authorize` bắt đầu 6.4 |
| "AuthorizationDecision đã bị thay thế, không dùng được ở 7.x" | Class vẫn implement `AuthorizationResult` | Dùng `new AuthorizationDecision(boolean)` làm implementation |
| "Ở 6.5 chỉ cần override authorize là đủ" | `check` vẫn là abstract method trong API 6.5 | Implement `check` hoặc chọn adapter đúng version |
| "Ở 7.x giữ nguyên @Override check" | `check` đã bị loại khỏi interface | Override `authorize` |
| "authorize luôn trả AuthorizationDecision" | Contract trả `AuthorizationResult` | Dùng `isGranted()`, không ép kiểu vô điều kiện |
| "null nghĩa là DENY" | `null` biểu diễn abstain; tùy nơi thực thi | Trả quyết định tường minh; fail closed có chủ đích |
| "new AuthorizationDecision(false) tự trả HTTP 403" | Decision không trực tiếp viết response | Enforcement point xử lý từ chối/exception |
| "verify chỉ là alias trả boolean" | `verify` thiên về kiểm tra rồi ném exception khi denied | Dùng `authorize` để lấy kết quả; `verify` khi cần guard |
| "Manager HTTP dùng được nguyên xi cho method" | Kiểu `T` khác nhau | Chọn `RequestAuthorizationContext` hoặc `MethodInvocation` đúng chỗ |
| "Có permission là đọc được mọi resource" | Thiếu kiểm tra đối tượng | Kết hợp tenant/owner/ACL/state |
| "Code chạy ở ví dụ current nghĩa là chạy trên BOM cũ" | API khác theo phiên bản | Kiểm tra resolved version/Javadoc tương ứng, compile test |
| "Null pointer do unauthenticated thì catch Exception và allow" | Vô tình fail open | Chặn, giữ cơ chế authentication hoặc trả deny an toàn |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `AuthorizationDecision` và `AuthorizationResult` khác nhau ở đâu?

**Đáp án:** `AuthorizationResult` là interface mô tả trạng thái cấp quyền; `AuthorizationDecision` là class cụ thể implement interface và có constructor nhận boolean. Cả hai đều hỗ trợ `isGranted()`.

**Câu 2.** Một module đang dùng Spring Security 6.3. Người lập trình gọi `manager.authorize(...)` nhưng build báo không có method. Vì sao?

**Đáp án:** `AuthorizationManager.authorize(...)` được thêm từ 6.4. Với 6.3 dùng `check(...)` hoặc nâng cấp dependency có kế hoạch.

**Câu 3.** Trong Spring Security 6.5, custom manager chỉ override `authorize(...)` mà không implement `check(...)`. Vì sao có thể không compile?

**Đáp án:** `check(...)` vẫn là abstract method của interface 6.5 (dù deprecated). `authorize(...)` là default method. Phải đáp ứng hợp đồng của interface đang compile.

**Câu 4.** Trong Spring Security 7, tại sao `@Override` trước `check(...)` lỗi?

**Đáp án:** `check(...)` đã bị loại khỏi `AuthorizationManager`. Cần implement `authorize(...)` với chữ ký và kiểu trả về của dòng 7.

**Câu 5.** `AuthorizationResult result = manager.authorize(...)`. Có nên cast result thành `AuthorizationDecision` để gọi `isGranted()` không?

**Đáp án:** Không. Interface đã có `isGranted()`. Cast tạo ràng buộc không cần thiết và có thể thất bại với implementation khác.

**Câu 6.** Một manager trả `null`. Có thể kết luận yêu cầu chắc chắn bị từ chối không?

**Đáp án:** Không. `null` có nghĩa chưa quyết định/abstain. Hành vi phụ thuộc nơi tiêu thụ/ghép quyết định; ứng dụng bảo mật nên có quy tắc fail closed rõ ràng và test.

**Câu 7.** HTTP custom manager quyết định `ALLOW` cho `report:read`. Caller có mặc nhiên được đọc report của tenant khác không?

**Đáp án:** Không. Còn cần kiểm tra tenant/membership/owner/ACL theo chính sách object-level authorization. Permission chức năng không thay thế các điều kiện này.

**Câu 8.** Khi nào dùng `verify` thay vì `authorize`?

**Đáp án:** Khi điểm gọi cần một guard có khả năng ném `AccessDeniedException` nếu quyết định từ chối. Khi muốn lấy kết quả để hiển thị/log/test/tổ hợp policy, dùng `authorize` theo phiên bản tương ứng; vẫn xử lý `null` và quyền bổ sung đúng cách.

## 14. Checklist áp dụng vào dự án

- [ ] Đọc **resolved Spring Security version** qua dependency tree/BOM; không đoán theo Spring Boot hoặc Java version.
- [ ] Ghi rõ dòng API đang dùng: 6.3 `check`; 6.4–6.5 `authorize` cho caller nhưng `check` còn trong implementation; 7.x `authorize` cho cả hai.
- [ ] Khai báo kết quả theo interface `AuthorizationResult` khi API hỗ trợ; dùng `AuthorizationDecision` để tạo quyết định đơn giản.
- [ ] Không ép kiểu result vô điều kiện; không coi `null` là allow/deny mặc định của framework.
- [ ] Áp dụng `deny by default` và kiểm tra object/tenant/context đủ điều kiện.
- [ ] Đặt custom manager đúng kiểu ngữ cảnh `T` và đúng điểm enforcement HTTP/method.
- [ ] Bật method security nếu cần; test proxy/self-invocation và các đường ngoài HTTP.
- [ ] Test code trên đúng dependency trước khi nâng cấp; cover allow, deny, abstain, exception và request thực.
- [ ] Ghi nhận thay đổi API trong migration, tránh pha trộn tài liệu 6.x và 7.x.

**Kết luận:** `AuthorizationDecision` là một **cách tạo kết quả**, `AuthorizationResult` là **hợp đồng đọc kết quả**, còn `AuthorizationManager` là **nơi đưa ra quyết định**. Spring Security 6.3 dùng `check`; 6.4–6.5 chuyển hướng sang `authorize` trong khi giữ `check` deprecated; 7.x hoàn tất chuyển đổi. Chọn đúng API theo version, trả quyết định rõ ràng và kiểm thử enforcement là điều kiện để luồng phân quyền vừa chính xác vừa bảo trì được.

## Tài liệu tham khảo — đối chiếu đúng phiên bản

- Spring Security 6.3.3 API — `AuthorizationManager` (`check`): https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authorization/AuthorizationManager.html
- Spring Security 6.5 API — `AuthorizationManager` (`check` deprecated, `authorize`): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html
- Spring Security 7.0 API — `AuthorizationManager` (`authorize`): https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/authorization/AuthorizationManager.html
- Spring Security 6.5 API — `AuthorizationResult`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationResult.html
- Spring Security 7.0 API — `AuthorizationDecision`: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/authorization/AuthorizationDecision.html
- Spring Security 7.0 — Authorization architecture: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/architecture.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — HTTP Requests Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
