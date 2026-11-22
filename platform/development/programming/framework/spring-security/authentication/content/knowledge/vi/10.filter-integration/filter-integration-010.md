# Phân biệt tiếp tục chuỗi, trả phản hồi và chuyển lỗi cho thành phần phù hợp

## 1. Ba quyết định của một Servlet Filter không được trộn lẫn

Trong ứng dụng Spring Security theo mô hình Servlet, mỗi HTTP request đi qua một chuỗi filter trước khi đến `DispatcherServlet`, controller hoặc một servlet đích. Một filter có thể kiểm tra header, xác thực, giới hạn tốc độ, kiểm tra quyền hoặc ghi log. Sau khi đã kiểm tra request, filter **phải lựa chọn cách chuyển quyền điều khiển**: để phần sau xử lý, tự kết thúc response, hoặc để một cơ chế xử lý lỗi thích hợp quyết định.

Ba lựa chọn này có hậu quả rất khác nhau:

1. **Tiếp tục chuỗi:** gọi `FilterChain.doFilter(request,response)`. Những filter còn lại và servlet/controller có cơ hội chạy.
2. **Tự xử lý phản hồi:** đặt HTTP status/header/body hoặc redirect rồi **return**, không gọi tiếp chain. Filter đã nhận trách nhiệm kết thúc request hiện tại.
3. **Phát sinh ngoại lệ:** ném exception đúng ngữ nghĩa cho bộ xử lý được cấu hình, nhưng **chỉ có hiệu quả nếu exception thực sự đi qua lớp bắt phù hợp trong thứ tự filter hiện tại**. Ngoại lệ bảo mật không tự động chuyển thành 401/403 ở mọi nơi.

Đây là nội dung cốt lõi của đề mục **“Phân biệt tiếp tục chuỗi, trả phản hồi và chuyển lỗi cho thành phần phù hợp”**, thuộc nhóm **“Tích hợp bộ lọc”** của Spring Security - authentication.

**Sau bài học**, người đọc có thể:

- Phân biệt chính xác `chain.doFilter`, `return` sau khi ghi response và `throw`.
- Hiểu `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler` và `AuthenticationFailureHandler` khác nhau thế nào.
- Chọn đường xử lý đúng cho xác thực chưa đủ, đăng nhập sai, thiếu quyền, rate limit, lỗi dữ liệu và lỗi hệ thống.
- Nhận diện tác động của **thứ tự filter** và trạng thái **response đã committed**.
- Kiểm thử được từng nhánh bằng chương trình Java 17 chạy qua API Spring Security 6.5 và Servlet mock.

## 2. Filter chain là một lời gọi lồng nhau, không phải danh sách chạy tự động

Một `jakarta.servlet.Filter` có phương thức:

```java
void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException;
```

Khi gọi `chain.doFilter(...)`, filter đang **trao quyền xử lý cho phần còn lại của chuỗi**. Nó không đơn thuần “báo đã xong” hoặc “đi tới dòng kế tiếp” trong một danh sách trừu tượng.

Ví dụ với ba filter:

```text
Client
  |
  v
Filter A -- before
  |
  +--> chain.doFilter(...)
           |
           v
        Filter B -- before
           |
           +--> chain.doFilter(...)
                    |
                    v
                 Filter C -- before
                    |
                    +--> chain.doFilter(...)
                             |
                             v
                         Controller/Servlet
                             |
                    <--------+
                    |
                 Filter C -- after
           <--------+
           |
        Filter B -- after
  <--------+
  |
Filter A -- after
  |
  v
Response
```

Nếu `Filter B` **không gọi chain** và trả HTTP response, thì `Filter C` và controller **không chạy**, nhưng code trong `Filter A` nằm **sau lời gọi `chain.doFilter`** vẫn có thể chạy khi lời gọi trở về bình thường.

Đây là điểm dễ bỏ sót: **“Dừng chuỗi ở filter B” không có nghĩa hủy toàn bộ stack của những filter đã vào trước đó.** Code `finally` hoặc code sau `chain.doFilter` ở filter trước vẫn có thể được thực thi. Do vậy không nên ghi thêm response body hoặc redirect muộn trong code hậu xử lý khi response đã được filter khác commit.

### Các tính chất cần nắm

- `chain.doFilter` thường chỉ nên được gọi **một lần** trên một đường xử lý nhất định, trừ khi có một cơ chế được thiết kế rõ ràng để lặp.
- Sau khi đã ủy quyền cho phần sau, filter **có thể chạy logic hậu xử lý** nếu không có exception làm thay đổi luồng.
- Nếu filter **không gọi chain**, không có gì bảo đảm Servlet/controller sẽ chạy.
- Nếu filter **ném exception**, luồng được tháo stack cho đến nơi có catch phù hợp; một filter nằm sau vị trí ném không có cơ hội chạy.
- `sendRedirect`, `sendError` và việc ghi response **không tự gọi chain**; chúng là thao tác lên response.
- `return` rời khỏi `doFilter` hiện tại; nó không có nghĩa “đi tiếp filter tiếp theo”.

### Bộ khung Java tiêu biểu

```java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException {

    // Trước phần còn lại của ứng dụng.
    doBefore(request);

    try {
        chain.doFilter(request, response);
    } finally {
        // Cleanup hoặc đo thời gian, kể cả khi phần sau ném lỗi.
        cleanup();
    }
}
```

Đây là **trích đoạn minh họa**, cần một class đã định nghĩa `doBefore` và `cleanup`; không phải chương trình độc lập. Dùng `finally` cho cleanup phù hợp, **không** tự ghi JSON lỗi ở `finally` khi downstream có thể đã ghi response thành công hoặc commit.

## 3. Quyết định A: tiếp tục chuỗi khi filter không cần tiêu thụ request

Tình huống phù hợp:

- Request **không khớp** endpoint mà filter có trách nhiệm, ví dụ filter xử lý `POST /login` nhưng nhận `GET /catalog`.
- Một kiểm tra hợp lệ, không chặn request, chẳng hạn correlation ID đã được xác minh.
- Một cơ chế authentication theo mỗi request đã có kết quả hợp lệ và được thiết kế để request tiếp tục tới authorization/controller, ví dụ resource server bearer token filter tương ứng.
- Filter chỉ ghi metrics, sửa request wrapper/response wrapper hoặc áp dụng chính sách cho downstream.

Mẫu đúng:

```java
if (!appliesToThisRequest(request)) {
    chain.doFilter(request, response);
    return;
}

if (passesPolicy(request)) {
    chain.doFilter(request, response);
    return;
}

// Từ đây policy đã từ chối. Chọn xử lý response hoặc exception.
```

Đây là **pseudocode Java** cần các method và biến tương ứng. `return` sau `chain.doFilter` không bắt buộc nếu method tự kết thúc, nhưng giúp làm rõ rằng nhánh đó **không rơi xuống code xử lý lỗi phía dưới**.

### Cần phân biệt filter authentication và filter authorization

Một filter xác thực theo từng request có thể thiết lập authentication rồi gọi tiếp chain; còn `UsernamePasswordAuthenticationFilter` / `AbstractAuthenticationProcessingFilter` khi nhận **đúng login processing request** thường **tiêu thụ request** và gọi success/failure handler, không tiếp tục controller như một request bình thường.

Vì thế:

> “Authentication thành công thì mọi filter đều phải gọi `chain.doFilter`” là kết luận sai.

Đúng hay không phụ thuộc **loại filter và endpoint contract**. Token authentication cho `GET /api/orders` khác với form login `POST /login`.

### Một ví dụ về `OncePerRequestFilter`

`OncePerRequestFilter` hữu ích cho filter Servlet custom vì cung cấp method `doFilterInternal(HttpServletRequest,HttpServletResponse,FilterChain)`, quản lý attribute đánh dấu theo dispatch và các cơ chế skip theo contract.

```java
public final class RequestMarkerFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        response.setHeader("X-Request-Checked", "true");
        chain.doFilter(request, response);
    }
}
```

Đây là một **class minh họa dùng trong project có Spring Web**, cần imports. Header được đặt trước `chain.doFilter` để tránh lỗi ghi header khi response đã committed. Nó không làm nhiệm vụ xác thực; chỉ cho thấy đường pass-through.

**Không mặc định `OncePerRequestFilter` có nghĩa “đúng một lần tuyệt đối trên mọi REQUEST/ERROR/ASYNC dispatch”.** Cách filter được đăng ký, cơ chế skip, dispatcher types và lifecycle Servlet vẫn cần được kiểm tra.

## 4. Quyết định B: ghi HTTP response và kết thúc filter hiện tại

Khi filter thực sự **sở hữu phản hồi** — chẳng hạn từ chối request vì giới hạn tốc độ hoặc endpoint chuyên dụng yêu cầu trả JSON — nó có thể tự đặt status, headers, content type/body rồi **return**.

Ví dụ giới hạn tốc độ:

```java
if (!rateLimiter.allow(request)) {
    response.setStatus(HttpServletResponse.SC_TOO_MANY_REQUESTS);
    response.setContentType("application/json");
    response.setCharacterEncoding("UTF-8");
    response.setHeader("Cache-Control", "no-store");
    response.getWriter().write(
            "{\"error\":\"too_many_requests\"}");
    return; // Không gọi chain sau khi đã quyết định chặn.
}

chain.doFilter(request, response);
```

Đoạn trên là **mã tích hợp**: `rateLimiter` chưa được định nghĩa; không đưa vào ứng dụng nếu chưa có rate limiting thực và phân tích nguồn IP/user được tin cậy.

Nhánh này có nghĩa:

- Các filter/controller **phía sau** không chạy.
- Client nhận response theo contract của filter.
- Không có `AuthenticationException` được ném để một authentication handler khác định nghĩa lại response.
- Những filter **phía trước** vẫn có thể chạy cleanup/hậu xử lý khi stack trở về.
- Nếu đã ghi body, **đừng tiếp tục chain** rồi để controller ghi body lần nữa.

### `setStatus` khác `sendError` và `sendRedirect`

| Thao tác | Tác dụng | Rủi ro hay nhầm |
| --- | --- | --- |
| `response.setStatus(401)` | Đặt mã HTTP; không tự chọn body, không mặc nhiên commit ngay. | Phải bảo đảm response body/header theo API contract và kết thúc luồng đúng. |
| `response.getWriter().write(...)` | Ghi nội dung response qua writer. | Không được dùng đồng thời `getOutputStream` trên cùng response; charset/content type phải phù hợp. |
| `response.sendError(403)` | Yêu cầu container xử lý error response/status theo Servlet semantics. | Có thể dẫn tới error page/`ERROR` dispatch tùy container; không phải việc ném `AccessDeniedException` cho Spring Security. |
| `response.sendRedirect("/login")` | Trả redirect với header `Location` theo container. | Không tiếp tục chain, không redirect tới URL do client tự điều khiển (open redirect). |
| `response.flushBuffer()` | Buộc response buffer được flush, thường **commit** headers/status. | Sau commit không thể đổi status/header như trước. |
| `return` | Rời method filter hiện tại. | **Không** tự đặt status hay body; nếu chưa ghi gì có thể thành response mặc định không mong muốn. |

**Phân biệt đặc biệt:** `sendError(401)` **không đồng nghĩa** `throw new BadCredentialsException(...)`. Một bên yêu cầu Servlet container quản lý error response; một bên là exception có thể được bộ xử lý Spring Security bắt nếu đúng vị trí/contract.

### Đừng gọi `chain.doFilter` sau khi đã gửi response

**Sai:**

```java
response.setStatus(401);
response.getWriter().write("{\"error\":\"unauthorized\"}");
chain.doFilter(request, response); // Có thể còn chạy controller!
```

**Đúng cho nhánh tự xử lý:**

```java
response.setStatus(401);
response.setContentType("application/json");
response.getWriter().write("{\"error\":\"unauthorized\"}");
return;
```

Tuy nhiên, nếu đây là lỗi bảo mật do policy authentication/authorization của Spring Security quản lý, **thường nên dùng đúng EntryPoint/FailureHandler/AccessDeniedHandler**, thay vì phân tán logic 401/403 ở mọi custom filter. Phần này sẽ được phân loại ở mục 6–8.

### Vì sao không được “trả 200 rỗng” khi đang chặn?

Nếu code chỉ có:

```java
if (blocked) {
    return;
}
```

thì response có thể giữ status mặc định `200` và body rỗng, khiến client tưởng request thành công. Nếu nhánh đó là “đang chờ MFA”, “rate limit” hoặc “không có quyền”, phải xác định **HTTP contract rõ ràng**: status, body, retry/error semantics và cách client tiếp tục.

Với authentication nhiều bước, trả `null` từ một method như `attemptAuthentication` có thể biểu diễn “chưa hoàn tất”, nhưng subclass phải tự xử lý redirect/response; **không phải** tự động trả 401 hay 202.

## 5. Quyết định C: ném exception có ngữ nghĩa và đúng vị trí

Một filter hoặc controller có thể phát hiện tình huống cần thành phần chung xử lý. Thay vì viết status/body tại nhiều vị trí, có thể **ném exception đúng loại**.

Ví dụ:

```java
throw new AccessDeniedException("Policy denies this resource");
```

Nhưng cần hỏi **ba điều trước khi ném**:

1. **Ai sẽ bắt?** `ExceptionTranslationFilter`, một `AuthenticationFailureHandler` của login filter, `@ControllerAdvice`, exception resolver của MVC, hay Servlet container?
2. **Vị trí có đúng không?** Exception có được ném **bên trong đoạn `chain.doFilter` mà component bắt lỗi đang bao quanh** không?
3. **Response còn sửa được không?** Status/header/body có bị commit bởi phần trước không?

Một exception **không tự mang status HTTP cố định**. `AuthenticationException` là một nhóm exception Java của Spring Security; `AccessDeniedException` là nhóm từ chối truy cập. Đường ánh xạ ra 401/403/302 phụ thuộc handler/entry point, chính sách và authentication hiện tại.

### Ngoại lệ phù hợp, không lạm dụng

- **`AuthenticationException`:** một yêu cầu cần xác thực, hoặc authentication không đủ/không hợp lệ theo contract của Spring Security. Ví dụ `BadCredentialsException`, `InsufficientAuthenticationException`.
- **`AccessDeniedException`:** đã đánh giá **authorization/security policy** và từ chối truy cập. Có thể dẫn tới entry point hoặc access denied handler tùy loại authentication.
- **Lỗi validation request:** thường trả 400 hoặc response đặc thù bởi controller/validation/error handler; không tự đổi thành `AuthenticationException` để “lọt qua Spring Security”.
- **Lỗi database, timeout, bug/null pointer:** thuộc vận hành/application error handling. Không nên biến mọi lỗi thành `AccessDeniedException` rồi trả 403 để giấu bug.
- **Giới hạn tốc độ:** thường phản hồi HTTP 429 qua rate-limit handler/filter thích hợp. Không đồng nghĩa sai credentials hoặc thiếu role.
- **Không tìm thấy tài nguyên:** thường 404 theo contract ứng dụng và chính sách chống lộ thông tin, không tự nhét vào `BadCredentialsException`.

**Nguyên tắc:** dùng loại exception thể hiện **nguyên nhân và người có quyền xử lý**; nếu không xác định được handler chịu trách nhiệm, đừng ném rồi hy vọng Spring Security tự tìm ra.

## 6. ExceptionTranslationFilter: cầu nối giữa ngoại lệ bảo mật và HTTP

Trong Spring Security Servlet, **`ExceptionTranslationFilter`** là thành phần tiêu biểu chuyển `AuthenticationException` và `AccessDeniedException` phát sinh trong **phần chuỗi mà nó bao quanh** thành hành động HTTP.

Sơ đồ cơ bản:

```text
             ExceptionTranslationFilter
                        |
                  try {
                        |
                        v
                  chain.doFilter(...)
                        |
              filter/controller phía sau
                        |
                có thể throw ...
                        |
                  } catch (...)
                        |
            +-----------+--------------+
            |                          |
   AuthenticationException     AccessDeniedException
            |                          |
            v                  +-------+--------+
   AuthenticationEntryPoint    |                |
   bắt đầu authentication      v                v
                           anonymous /        full authenticated
                           remember-me         |
                               |                |
                               v                v
                    AuthenticationEntryPoint  AccessDeniedHandler
                         thường 401/302         thường 403
```

Lưu ý: **`ExceptionTranslationFilter` không tự xác thực credential và không tự quyết định phân quyền**. Các filter/provider/authorization component khác làm việc đó; translation filter chọn cách phản hồi dựa trên exception và ngữ cảnh.

### 6.1. `AuthenticationException` → AuthenticationEntryPoint

Khi exception bảo mật thuộc loại `AuthenticationException` đi tới translator, nó thực hiện logic bắt đầu authentication. Tùy cấu hình:

- **Form login:** `LoginUrlAuthenticationEntryPoint` có thể redirect tới trang đăng nhập.
- **HTTP Basic:** `BasicAuthenticationEntryPoint` thường trả HTTP 401 và header `WWW-Authenticate` theo scheme.
- **Bearer token/resource server:** `BearerTokenAuthenticationEntryPoint` áp dụng response/challenge theo cơ chế bearer.
- **REST API tự thiết kế:** một entry point tùy biến có thể trả JSON 401 không tiết lộ dữ liệu nhạy cảm.

Một request không được phép vì chưa có credentials hợp lệ nên **không nhất thiết** phải nhận đúng text hoặc body nào; đó là lựa chọn của entry point.

### 6.2. `AccessDeniedException` không phải lúc nào cũng trả 403

Khi nhận `AccessDeniedException`, translator xem authentication hiện tại:

- **Anonymous**: cần bắt đầu xác thực; thường gọi `AuthenticationEntryPoint` (401 hoặc redirect).
- **Remember-me** được coi là chưa đủ mức xác thực cho yêu cầu: có thể gọi entry point để đòi xác thực mạnh hơn.
- **Đã xác thực đầy đủ** nhưng thiếu quyền: gọi `AccessDeniedHandler`; thường 403.

Đây là lý do một URL yêu cầu `ROLE_ADMIN` có thể trả **401/302 với khách chưa đăng nhập** nhưng trả **403 cho người đã đăng nhập với `ROLE_READER`**.

**Không đoán rằng `AccessDeniedException` luôn là HTTP 403.** Người dùng anonymous chưa có identity hợp lệ để đưa ra kết luận “đã đăng nhập nhưng thiếu role”. Cách phân loại còn chịu ảnh hưởng `AuthenticationTrustResolver` và policy.

### 6.3. RequestCache và saved request

Khi cần khởi động authentication, translator có thể dùng `RequestCache` để lưu request ban đầu, giúp người dùng sau khi login quay lại trang họ đang muốn xem. Trong cấu hình session-backed, cache có thể dùng HttpSession; trong API stateless có thể dùng `NullRequestCache`.

Điều đó giải thích một redirect như:

```text
GET /reports/annual -> 302 /login
POST /login (thành công)
-> redirect lại /reports/annual
```

**Không nhầm saved request với việc cấp quyền.** Request cache không thay thế authentication/authorization; redirect sau login vẫn phải đi qua security filter chain. Không lấy tùy ý return URL từ user rồi tạo open redirect.

### 6.4. Những ngoại lệ translator không có trách nhiệm xử lý

`ExceptionTranslationFilter` không phải một `catch(Throwable)` toàn năng:

- `IllegalArgumentException`, `NullPointerException`, lỗi JDBC, JSON parsing, IOException thông thường không được tự chuyển thành security 401/403.
- Nếu một MVC `HandlerExceptionResolver`/`@ControllerAdvice` đã xử lý exception trong `DispatcherServlet` và trả response thì translator có thể **không thấy exception nữa**.
- Nếu exception bị filter **phía trước** translator ném **trước khi gọi chain**, translator không có mặt trong call stack để bắt.
- Nếu response đã **committed**, dù translator nhìn thấy `AuthenticationException`/`AccessDeniedException`, nó có thể không còn tạo được response phù hợp; framework có thể ném thêm `ServletException` để báo việc không thể xử lý an toàn.

### 6.5. Thứ tự filter mang ý nghĩa điều khiển thực tế

Giả sử chuỗi đi theo thứ tự:

```text
Filter A
  |
  v
ExceptionTranslationFilter
  |
  v
Filter B (authorization)
  |
  v
Controller
```

`ExceptionTranslationFilter` gọi `chain.doFilter(...)` để chạy **B + controller**. Nếu B ném `AccessDeniedException`, exception đi ngược qua translator và được chuyển thành response. Nhưng nếu **A ném exception trước khi gọi `chain.doFilter`**, translator chưa được gọi nên **không thể bắt**. Đây là hệ quả trực tiếp của mô hình filter lồng nhau.

**Đừng nghĩ thêm `ExceptionTranslationFilter` vào một security chain sẽ khiến mọi custom filter ở bất cứ đâu tự động chuyển exception thành 401/403.** Nếu custom authentication filter nằm phía trước translator, nó thường phải dùng **failure handler/entry point của chính mình**, hoặc có một đường xử lý lỗi được thiết kế rõ ràng.

## 7. Phân biệt AuthenticationEntryPoint, FailureHandler và AccessDeniedHandler

Ba interface có trách nhiệm khác nhau:

| Thành phần | Khi nào nên gọi? | Thường xử lý | Không chịu trách nhiệm chính |
| --- | --- | --- | --- |
| **`AuthenticationEntryPoint`** | Request chưa đáp ứng authentication requirement, cần bắt đầu/challenge login | Redirect trang login, HTTP 401 + challenge header, JSON 401 | Không kiểm chứng raw password trong một login POST. |
| **`AuthenticationFailureHandler`** | Một **login attempt** đã được authentication filter thử và thất bại | Redirect `/login?error`, JSON lỗi, 401, chính sách thông báo an toàn | Không quyết định 403 cho mọi authorization failure. |
| **`AccessDeniedHandler`** | Đã có authentication đủ mức nhưng thiếu quyền | 403, trang denied hoặc JSON theo API contract | Không tự mời anonymous login trong mọi tình huống. |

### 7.1. Login form sai password thường không tới ExceptionTranslationFilter

Với `UsernamePasswordAuthenticationFilter` (một subclass của `AbstractAuthenticationProcessingFilter`), nhánh cơ bản:

```text
POST /login
    |
    v
UsernamePasswordAuthenticationFilter
    |
    +--> AuthenticationManager.authenticate(...)
             |
             +-- sai --> BadCredentialsException
                          |
                          v
                    unsuccessfulAuthentication(...)
                          |
                          v
                    AuthenticationFailureHandler
                          |
                         RETURN
             |
             +-- đúng --> successfulAuthentication(...)
                          |
                          v
                    AuthenticationSuccessHandler
                          |
                         RETURN
```

Filter đăng nhập **bắt ngoại lệ xác thực trong chính luồng attempt của nó** rồi gọi failure handler. Nó không cần ném tiếp lỗi sai password cho translator nằm sau. Nếu bạn viết một custom filter rồi tự ném `BadCredentialsException` **trước** translator, bạn không thể khẳng định translator sẽ bắt nó.

Đừng tự viết:

```java
try {
    authenticationManager.authenticate(token);
} catch (AuthenticationException ex) {
    throw new AccessDeniedException("Not allowed", ex);
}
```

để “ép lỗi đăng nhập thành 403”. Cách đó trộn authentication và authorization, tạo thông điệp/trạng thái sai và có thể làm lộ thêm thông tin. Hãy dùng đúng authentication failure mechanism.

### 7.2. Khi truy cập tài nguyên protected mà chưa login

`AuthorizationFilter` có thể từ chối truy cập do người dùng chưa đáp ứng policy. Translator đặt trước nó trong filter chain có thể bắt loại exception phù hợp, rồi gọi entry point để **bắt đầu authentication**.

Ví dụ có thể là HTTP 401 đối với API hoặc redirect đối với browser. Không nhất thiết phải có `POST /login` trong request đó.

### 7.3. Khi đã login nhưng thiếu role

Authenticated user có `ROLE_READER` gọi `GET /admin` yêu cầu `ROLE_ADMIN`. Lỗi là **authorization**, không phải password sai: AccessDeniedHandler có thể trả 403.

**Đừng xóa `SecurityContext` để tạo 401 thay cho 403** chỉ vì UI muốn hiện trang login. Quyết định hạ mức authentication hoặc buộc step-up phải nằm trong chính sách tin cậy và có lý do rõ.

## 8. Bảng chọn nhánh theo kịch bản thực tế

| Kịch bản | Tiếp tục chain? | Tự phản hồi? | Giao lỗi cho ai? |
| --- | --- | --- | --- |
| Filter chỉ thêm correlation ID | **Có**, sau khi đặt header/context | Không | Exception application tùy downstream |
| Custom filter không áp dụng cho URL hiện tại | **Có** | Không | Không có lỗi |
| Xác minh bearer token thành công trong resource-server filter | Thường **có** để authorization/controller chạy | Không tại đây | Theo authentication filter/framework |
| `POST /login` form thành công | Thường **không** trong login processing filter | Success handler có thể 200/204/302 | `AuthenticationSuccessHandler` |
| `POST /login` sai password | Thường **không** | Failure handler có thể 401/302 | `AuthenticationFailureHandler` |
| Request protected từ user anonymous | Exception đến đúng translator | Entry point có thể 401/302 | `AuthenticationEntryPoint` |
| Authenticated user thiếu quyền | Exception đến đúng translator | Denied handler thường 403 | `AccessDeniedHandler` |
| Rate limit phát hiện trước controller | Không khi block | Có thể trả 429 | Rate-limit handler/filter riêng |
| Trường bắt buộc trong JSON body thiếu | Tùy controller/validation flow | 400 do API error contract | MVC validation/`@ControllerAdvice` |
| Lỗi database/bug | Thường exception được đưa tới error handling | 5xx theo policy, không dump stack trace | Application error handler/container |
| Callback auth nhiều bước chưa hoàn tất | Không trong request đã được filter tiêu thụ | Redirect/202/challenge theo giao thức | Filter/protocol handler tương ứng |
| Response đã committed rồi mới phát hiện thiếu quyền | Không thể chọn lại status một cách an toàn | Có thể đã quá muộn | Logging/rollback/correct ordering, không chữa bằng response thứ hai |

Bảng này là **nguyên tắc lựa chọn**. Kết quả HTTP cụ thể còn tùy SecurityFilterChain, authentication mechanism, Servlet container, handler cấu hình, dispatcher types và request/response lifecycle.

## 9. Response committed: thời điểm không thể làm lại response

`HttpServletResponse` có **buffer**. Khi headers/status được commit, ứng dụng không thể tự do đổi chúng. Các thao tác có thể commit hoặc dẫn tới commit:

- `response.flushBuffer()`.
- `sendError(...)` hoặc `sendRedirect(...)` theo hợp đồng Servlet.
- Ghi body đủ lớn làm vượt buffer.
- Framework hoàn tất/flush response hoặc connection đã bắt đầu gửi dữ liệu.
- Một số cơ chế streaming/SSE/async response phát header sớm.

Một mẫu nguy hiểm:

```java
response.getWriter().write("partial response");
response.flushBuffer();
throw new AccessDeniedException("Permission missing");
```

Đến đây `ExceptionTranslationFilter` dù nằm đúng chỗ cũng **không thể biến một response đã committed thành response lỗi sạch**. Bạn có thể gặp `ServletException` có ý nghĩa “không thể xử lý security exception vì response đã commit”.

**Nguyên tắc thực tế:** kiểm tra authentication/authorization, tenant policy và các điều kiện không được phép **trước khi** gửi body/stream. Đối với streaming, phải định nghĩa rõ xử lý lỗi sau commit (đóng kết nối, protocol-specific event/error frame, auditing) thay vì cố gửi JSON 401 thứ hai.

### `isCommitted()` giúp gì?

`response.isCommitted()` có thể giúp debug/tránh thao tác sai trong error handler, nhưng không nên biến thành logic “nếu committed thì im lặng nuốt exception”. Hệ thống vẫn phải có tracing và xử lý sự cố rõ ràng. Quan trọng hơn, thiết kế nên tránh đến tình huống kiểm quyền quá muộn.

### Vì sao `sendError` và `ERROR dispatch` khác với Spring Security exception?

`sendError(403)` là lời nhờ Servlet container xử lý error response. Tùy container/cấu hình, nó có thể điều hướng đến error page qua `DispatcherType.ERROR`. Trong khi đó ném `AccessDeniedException` cho `ExceptionTranslationFilter` dẫn tới `AccessDeniedHandler` hoặc `AuthenticationEntryPoint` theo security context.

Một ứng dụng có thể dùng cả hai tầng: denied handler gọi `sendError(403)`, rồi container error dispatch tới `/error`. Cần kiểm tra rule authorization và bộ lọc cho `ERROR` dispatch, tránh vòng lỗi hoặc vô tình lộ dữ liệu nhạy cảm ở trang lỗi.

## 10. Ví dụ Java 17 chạy được với Spring Security 6.5.11

Chương trình này dùng **Spring Security Web 6.5.11** và **Spring Framework 6.2.12 Servlet mocks**, không cần web server hay database. Nó kiểm chứng trực tiếp ba lựa chọn:

- `chain.doFilter` tiếp tục tới terminal.
- Tự viết HTTP status/body và return.
- Ném `AuthenticationException`/`AccessDeniedException` ở **phía sau** `ExceptionTranslationFilter`.
- Gỡ rối trường hợp **anonymous** khác **authenticated**.
- Lỗi không thuộc loại security không được translator sửa thành 401/403.
- Response đã committed trước khi ném lỗi bảo mật không còn đổi status an toàn.
- Exception do filter **phía trước** translator ném không được translator bắt.

**Không dùng mô phỏng này làm cơ chế đăng nhập production.** `SecurityContext` được gắn bằng đối tượng dựng sẵn để **chỉ nghiên cứu error-routing**, không phải cấp identity từ request thật.

### 10.1. Tổ chức file

```text
filter-routing-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    └── FilterRoutingDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'filter-routing-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.5.11'
    implementation 'org.springframework:spring-test:6.2.12'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'demo.FilterRoutingDemo'
}
```

Các version trên cố định để kiểm tra API theo nhánh Spring Security 6.5.11. Trong ứng dụng Spring Boot thật, nên dùng BOM/dependency management để đồng bộ các phiên bản Spring Framework/Spring Security được hỗ trợ. Có thể có log hoặc warning của thư viện tùy môi trường; chúng không thuộc các dòng stdout chủ đích.

### 10.2. File `src/main/java/demo/FilterRoutingDemo.java`

```java
package demo;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.InsufficientAuthenticationException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.access.ExceptionTranslationFilter;
import org.springframework.security.web.savedrequest.NullRequestCache;

public final class FilterRoutingDemo {

    // Filter này chỉ dùng để quan sát cách chọn đường đi.
    // Không phải authorization policy đầy đủ của ứng dụng thật.
    static final class DecisionFilter implements Filter {

        @Override
        public void doFilter(
                ServletRequest rawRequest,
                ServletResponse rawResponse,
                FilterChain chain)
                throws IOException, ServletException {

            HttpServletRequest request = (HttpServletRequest) rawRequest;
            HttpServletResponse response = (HttpServletResponse) rawResponse;
            String path = request.getRequestURI();

            switch (path) {
                case "/continue":
                    chain.doFilter(request, response);
                    return;

                case "/respond":
                    response.setStatus(202);
                    response.setContentType("text/plain");
                    response.getWriter().write("accepted");
                    return;

                case "/auth-required":
                    throw new InsufficientAuthenticationException(
                            "Authentication required");

                case "/denied":
                    throw new AccessDeniedException(
                            "Missing authority");

                case "/bug":
                    throw new IllegalStateException(
                            "Unexpected application failure");

                case "/late-denied":
                    response.flushBuffer(); // commit trước khi báo lỗi
                    throw new AccessDeniedException(
                            "Authorization checked too late");

                default:
                    chain.doFilter(request, response);
            }
        }
    }

    private static void assumePrincipal(boolean anonymous) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();

        // Chỉ là identity mẫu, KHÔNG tự tạo Authentication đã
        // xác thực từ username/roles client cung cấp ở production.
        Authentication auth;
        if (anonymous) {
            auth = new AnonymousAuthenticationToken(
                    "demo-anonymous-key",
                    "anonymousUser",
                    AuthorityUtils.createAuthorityList("ROLE_ANONYMOUS"));
        } else {
            auth = UsernamePasswordAuthenticationToken.authenticated(
                    "lan",
                    null,
                    AuthorityUtils.createAuthorityList("ROLE_READER"));
        }

        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);
    }

    private static void run(
            String label,
            String path,
            boolean anonymous,
            ExceptionTranslationFilter translator,
            DecisionFilter decision,
            AtomicInteger entryCalls,
            AtomicInteger deniedCalls) {

        SecurityContextHolder.clearContext();
        assumePrincipal(anonymous);

        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", path);
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        int[] terminalCalls = {0};
        FilterChain terminal = (req, res) -> terminalCalls[0]++;

        FilterChain downstream =
                (req, res) -> decision.doFilter(req, res, terminal);

        int oldEntry = entryCalls.get();
        int oldDenied = deniedCalls.get();
        String thrown = "-";

        try {
            translator.doFilter(request, response, downstream);
        } catch (Exception ex) {
            // Chỉ để HIỂN THỊ hậu quả trong demo console.
            // Ứng dụng thật phải báo cáo lỗi vận hành đúng chỗ.
            thrown = ex.getClass().getSimpleName();
        }

        System.out.println(label
                + " status=" + response.getStatus()
                + " terminal=" + terminalCalls[0]
                + " entry=" + (entryCalls.get() - oldEntry)
                + " denied=" + (deniedCalls.get() - oldDenied)
                + " thrown=" + thrown);

        SecurityContextHolder.clearContext();
    }

    private static void runUpstream(
            DecisionFilter decision,
            ExceptionTranslationFilter translator,
            AtomicInteger entryCalls,
            AtomicInteger deniedCalls) {

        SecurityContextHolder.clearContext();
        assumePrincipal(true);

        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", "/auth-required");
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        int[] terminalCalls = {0};
        FilterChain terminal = (req, res) -> terminalCalls[0]++;

        // Bố trí NGƯỢC: decision nằm TRƯỚC translator.
        // Khi decision throw ngay, translator chưa từng được gọi.
        FilterChain downstream =
                (req, res) -> translator.doFilter(req, res, terminal);

        int oldEntry = entryCalls.get();
        int oldDenied = deniedCalls.get();
        String thrown = "-";

        try {
            decision.doFilter(request, response, downstream);
        } catch (Exception ex) {
            thrown = ex.getClass().getSimpleName();
        }

        System.out.println("upstreamAuth"
                + " status=" + response.getStatus()
                + " terminal=" + terminalCalls[0]
                + " entry=" + (entryCalls.get() - oldEntry)
                + " denied=" + (deniedCalls.get() - oldDenied)
                + " thrown=" + thrown);

        SecurityContextHolder.clearContext();
    }

    public static void main(String[] args) {

        AtomicInteger entryCalls = new AtomicInteger();
        AtomicInteger deniedCalls = new AtomicInteger();

        ExceptionTranslationFilter translator =
                new ExceptionTranslationFilter(
                        (request, response, authException) -> {
                            entryCalls.incrementAndGet();
                            response.setStatus(401);
                        },
                        new NullRequestCache());

        translator.setAccessDeniedHandler(
                (request, response, accessDeniedException) -> {
                    deniedCalls.incrementAndGet();
                    response.setStatus(403);
                });

        translator.afterPropertiesSet();

        DecisionFilter decision = new DecisionFilter();

        run("continue", "/continue", true,
                translator, decision, entryCalls, deniedCalls);

        run("respond", "/respond", true,
                translator, decision, entryCalls, deniedCalls);

        run("authentication", "/auth-required", true,
                translator, decision, entryCalls, deniedCalls);

        run("anonymousDenied", "/denied", true,
                translator, decision, entryCalls, deniedCalls);

        run("authenticatedDenied", "/denied", false,
                translator, decision, entryCalls, deniedCalls);

        run("bug", "/bug", false,
                translator, decision, entryCalls, deniedCalls);

        run("lateDenied", "/late-denied", false,
                translator, decision, entryCalls, deniedCalls);

        runUpstream(decision, translator, entryCalls, deniedCalls);
    }
}
```

### 10.3. Lệnh chạy và stdout

Với JDK 17+ và Gradle/Gradle Wrapper hỗ trợ Java 17:

```bash
gradle run --quiet
```

**Các dòng chuẩn do chính chương trình in ra** theo cấu hình ví dụ, không tính output riêng của Gradle/runtime:

```text
continue status=200 terminal=1 entry=0 denied=0 thrown=-
respond status=202 terminal=0 entry=0 denied=0 thrown=-
authentication status=401 terminal=0 entry=1 denied=0 thrown=-
anonymousDenied status=401 terminal=0 entry=1 denied=0 thrown=-
authenticatedDenied status=403 terminal=0 entry=0 denied=1 thrown=-
bug status=200 terminal=0 entry=0 denied=0 thrown=IllegalStateException
lateDenied status=200 terminal=0 entry=0 denied=0 thrown=ServletException
upstreamAuth status=200 terminal=0 entry=0 denied=0 thrown=InsufficientAuthenticationException
```

Trong demo, `MockHttpServletResponse` bắt đầu với status mặc định **200**. Vì vậy `bug`, `lateDenied` và `upstreamAuth` hiển thị `status=200` ở object mock **không có nghĩa client production được coi là đã xử lý thành công**: các nhánh đó còn ném exception; Servlet container/error handler thật có thể tạo HTTP 5xx hoặc response lỗi theo cấu hình. Kết quả cũng không mô phỏng tác dụng của toàn bộ filter chain do Spring Boot tự tạo.

### 10.4. Vì sao mỗi dòng có kết quả như vậy?

**`continue`:** DecisionFilter gọi `terminal.doFilter` một lần. Translator không phải xử lý exception; status mock vẫn 200.

**`respond`:** filter tự trả 202 và viết text, rồi `return`; terminal không chạy, không có authentication entry point hoặc denied handler.

**`authentication`:** DecisionFilter phía sau translator ném `InsufficientAuthenticationException`, là một `AuthenticationException`. Translator bắt, clear context cần thiết và gọi entry point do demo cấu hình trả 401. Vì `NullRequestCache` được chọn, không có session cache phải kiểm tra ở đây.

**`anonymousDenied`:** mặc dù exception là `AccessDeniedException`, principal đang là `AnonymousAuthenticationToken` nên translator dùng entry point (401) thay vì denied handler.

**`authenticatedDenied`:** principal được mô phỏng là authenticated với `ROLE_READER`, không đủ quyền theo chính tình huống demo; translator gọi denied handler trả 403.

**`bug`:** `IllegalStateException` không thuộc hai loại security exception. Translator không đổi nó thành 401/403; exception đi ra ngoài để tầng lỗi ứng dụng/container xử lý.

**`lateDenied`:** code gọi `flushBuffer` trước khi ném `AccessDeniedException`; mock response đã committed. Translator không thể an toàn tạo 403 mới nên báo `ServletException` theo implementation. Status object mock vẫn 200 đã commit; không suy ra status cuối cùng trên mạng trong một web server thực.

**`upstreamAuth`:** DecisionFilter nằm ngoài translator và ném exception trước khi gọi chain. Translator không nằm trong stack xử lý nên entry point không được gọi. Ví dụ này giải thích vì sao **vị trí của filter quyết định liệu ném exception có đi tới người xử lý hay không**.

### 10.5. Giới hạn của demo

- Không sử dụng `FilterChainProxy` hay toàn bộ `SecurityFilterChain` do Boot cấu hình; demo dựng các thành phần Spring Security thật ở cấp unit/integration style.
- Không thực hiện `AuthenticationManager.authenticate(...)`: principal do code đặt cho mục đích test. **Không** sao chép `assumePrincipal` vào filter ứng dụng thật.
- Không có credential, cookie session, OAuth2/JWT, CSRF hoặc account status checks.
- `NullRequestCache` tránh tạo saved request/session trong demo; ứng dụng browser thật có thể dùng `HttpSessionRequestCache`.
- Không có MVC `@ControllerAdvice`, nên demo cho thấy rõ exception chảy ra filter stack khi chưa được resolver khác xử lý.
- Những giá trị status và số lần callback là contract của các handler demo, **không phải status bắt buộc cho mọi ứng dụng Spring Security**.
- Bộ đếm `entryCalls`/`deniedCalls` chỉ để kiểm chứng nhánh, không phải công cụ audit bảo mật.

## 11. Tích hợp trong SecurityFilterChain thật: thứ tự rất quan trọng

### 11.1. Vị trí chuẩn của các lớp

Một `SecurityFilterChain` thông dụng có các thành phần thuộc nhiều giai đoạn:

```text
[Khôi phục SecurityContext]
         |
[CSRF/CORS/headers và bảo vệ request]
         |
[Authentication filter: form/basic/bearer...]
         |
[AnonymousAuthenticationFilter khi phù hợp]
         |
[ExceptionTranslationFilter]
         |
[AuthorizationFilter]
         |
[DispatcherServlet / controller]
```

Đây là sơ đồ **khái niệm**, không phải danh sách đầy đủ hoặc thứ tự tuyệt đối cho mọi ứng dụng. Spring Security có thể có nhiều filter khác, nhiều security chains và cấu hình/phiên bản khác nhau. Có thể bật log DEBUG/TRACE có kiểm soát để xem thứ tự thực tế. Không ghi credentials vào log khi bật trace.

**Hệ quả:** Authentication filter thường xử lý credentials **trước `ExceptionTranslationFilter`**, nên phải chủ động dùng failure handler/entry point phù hợp. AuthorizationFilter thường xuất hiện phía sau translator, nên denial do nó phát ra có thể được translator xử lý theo authentication state.

### 11.2. Đặt custom filter đúng giai đoạn

Trước khi thêm:

```java
http.addFilterAfter(customFilter, AnonymousAuthenticationFilter.class);
```

hãy xác định filter làm việc gì: authentication, authorization, exploit protection, correlation ID hay rate limiting?

Đoạn trên là **trích đoạn DSL**, cần class configuration/bean tương ứng. `addFilterAfter(..., AnonymousAuthenticationFilter.class)` giúp filter chạy sau anonymous filter, nhưng **không tự bảo đảm nằm phía sau `ExceptionTranslationFilter`**. Theo thứ tự phổ biến, nó có thể vẫn ở **trước translator**, nên một `AccessDeniedException` do custom filter ném không mặc nhiên được translator bắt.

Đây là lỗi rất dễ mắc:

> “Tôi thêm tenant authorization filter sau AnonymousAuthenticationFilter, ném AccessDeniedException, sao không ra 403 đẹp như AuthorizationFilter?”

Vì custom filter có thể **chạy sớm hơn ExceptionTranslationFilter**. Giải pháp đúng là xem thứ tự filter hiện hành và chọn một trong các hướng được thiết kế rõ ràng:

- Đặt logic authorization vào chính sách `authorizeHttpRequests`, method security hoặc một `AuthorizationManager` phù hợp để framework xử lý.
- Nếu có filter custom tự sở hữu denial, cấu hình **AccessDeniedHandler/AuthenticationEntryPoint** phù hợp tại vị trí đó thay vì trông chờ translator ở phía sau.
- Nếu chủ đích cần translator bao quanh filter, kiểm tra thứ tự tương đối sau translator và trước nơi xử lý tài nguyên; phải hiểu tác động đến filter ordering/authorization.
- Với authentication custom, dùng một authentication filter/framework pattern có failure mechanism đúng.

Không tùy tiện chuyển filter xuống sau `AuthorizationFilter` chỉ để exception được bắt nếu làm vậy bỏ qua các điều kiện cần kiểm tra **trước authorization**. Hãy thiết kế vị trí theo trách nhiệm của filter và kiểm thử đầy đủ.

### 11.3. Nhiều SecurityFilterChain

Spring Security có thể dùng:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());
    return http.build();
}
```

Đây là **trích đoạn cấu hình**, cần imports `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, `Customizer` và các policy session/CSRF/authentication đầy đủ. `FilterChainProxy` chọn **security chain đầu tiên khớp**, không “gộp tất cả chain”. Vì vậy `/api/**` có thể dùng entry point/authorization khác với browser paths. Đừng debug một filter trong web chain rồi nghĩ nó chắc chắn xử lý API chain.

**Security chain selection khác với `chain.doFilter`:** chọn chain quyết định **danh sách filter**, còn `chain.doFilter` bên trong quyết định **có chạy phần còn lại của danh sách đã chọn hay không**.

### 11.4. Đăng ký filter hai lần

Trong Spring Boot, một `Filter` được khai báo `@Component` hoặc `@Bean` có thể được auto-register vào Servlet container. Nếu cùng instance hoặc lớp đó lại được thêm qua `http.addFilterBefore/After`, filter có thể chạy hai lần, ngoài/ trong security chain khác nhau. Điều này làm rối số lượt gọi chain, logging, response status và vị trí catch exception.

Nếu filter cần là Spring bean để inject dependency nhưng chỉ muốn chạy bên trong Spring Security chain, kiểm soát container registration bằng `FilterRegistrationBean` disabled hoặc cách cấu hình phù hợp; test chính xác vị trí một lần. Không tự kết luận `OncePerRequestFilter` sẽ tự giải quyết tất cả trường hợp double registration.

## 12. MVC @ControllerAdvice, Servlet ERROR dispatch và Spring Security khác nhau

Khi lỗi phát sinh **ở controller**, nhiều ứng dụng Spring MVC có `@ControllerAdvice`/`@ExceptionHandler` hoặc `HandlerExceptionResolver` để chuyển exception thành JSON hay view. Nó **có thể xử lý lỗi trước khi exception thoát ra filter stack**.

| Vị trí lỗi | Người có thể xử lý | Điều phải kiểm tra |
| --- | --- | --- |
| Trong controller/service được MVC gọi | MVC `@ExceptionHandler`/`@ControllerAdvice`, hoặc exception chảy ra ngoài | Handler có được chọn không và có trả response không? |
| Trong filter trước DispatcherServlet | Filter-local handler, Spring Security filter thích hợp, Servlet container | MVC advice không mặc nhiên xử lý exception ném trước khi dispatcher chạy. |
| Trong authentication filter | Authentication failure handler/entry point của filter | Có bắt đúng `AuthenticationException` không? |
| Trong AuthorizationFilter phía sau translator | `ExceptionTranslationFilter` | Context anonymous/remember-me/authenticated quyết định entry/denied. |
| Exception do filter ngoài security chain ném | Container/global filter đã bao quanh | Security translator bên trong không thấy nếu chưa được gọi. |
| `sendError` hoặc exception chưa xử lý | Servlet container error handling/ERROR dispatch | Dispatcher type, error page và response commit. |

### Một lỗi phổ biến với `@ControllerAdvice`

Viết một `@RestControllerAdvice` bắt `Exception.class` rất rộng và trả HTTP 200 hoặc một JSON lỗi chung có thể **nuốt mất `AccessDeniedException`** do method security ném bên trong MVC. Khi đó translator không còn cơ hội xử lý và client nhận sai status.

Không áp dụng lời khuyên “hãy để mọi AccessDeniedException ném ra từ controller” một cách mù quáng: việc một exception có thoát MVC hay không phụ thuộc exception resolvers đã đăng ký. Cần test thực tế với `@PreAuthorize`/authorization và error mapping, bảo đảm 401/403 phản ánh chính sách.

### Dùng ProblemDetail / RFC 9457

Nếu API dùng `application/problem+json`, một handler có thể trả cấu trúc gồm `type`, `title`, `status`, `detail`, `instance` theo contract. Tuy nhiên:

- Không tiết lộ raw password, access token, bearer token, hash, stacktrace hoặc thông tin tài khoản nhạy cảm.
- HTTP status thực phải phù hợp với `status` trong body.
- Authentication entry point/AccessDeniedHandler vẫn là các nơi phù hợp để xử lý lỗi bảo mật phát sinh trong filter chain.
- Không tạo JSON vấn đề mới khi response đã committed.
- Phần body thống nhất không có nghĩa mọi loại lỗi được biến thành cùng mã 200.

## 13. Khi cần 401, 403, 404, 429 hay 5xx?

Mỗi status mô tả một tình huống khác nhau. Đừng chọn status chỉ vì “mình không muốn request chạy tiếp”.

| Mã | Ý nghĩa thường dùng | Ví dụ xử lý |
| --- | --- | --- |
| **400 Bad Request** | Dữ liệu request sai cú pháp/validation | MVC validation hoặc API handler. |
| **401 Unauthorized** | Cần/thiếu authentication hợp lệ; có thể yêu cầu challenge | AuthenticationEntryPoint, login failure handler phù hợp. |
| **403 Forbidden** | Tài nguyên bị từ chối theo authorization policy | AccessDeniedHandler, `AuthorizationFilter`/method security. |
| **404 Not Found** | Tài nguyên không tồn tại hoặc policy cố ý che sự hiện diện | MVC/resource handler theo contract. |
| **409 Conflict** | Xung đột trạng thái nghiệp vụ | Service/controller exception mapping. |
| **422 Unprocessable Content** | Một số API dùng cho dữ liệu hợp lệ về cú pháp nhưng không đáp ứng quy tắc xử lý | API error mapping theo contract, không tự coi là authentication failure. |
| **429 Too Many Requests** | Request vượt quota/rate limit | Gateway/filter/rate-limiter có thể thêm `Retry-After` khi có căn cứ. |
| **500 Internal Server Error** | Bug/lỗi máy chủ không được xử lý tốt hơn | Global error handler, không trả stacktrace ra ngoài. |
| **503 Service Unavailable** | Phụ thuộc hạ tầng không khả dụng tạm thời | Error handler + retry/circuit-breaker policy, không giả thành mật khẩu sai. |

**401 không có nghĩa chắc chắn “password sai”** và **403 không có nghĩa chắc chắn “đã login”**: policy, cách triển khai và tình huống thực tế quyết định. HTTP 401 theo chuẩn có semantics của authentication challenge; một endpoint được chuẩn hóa nên đặt header/challenge phù hợp cơ chế, không chỉ trả body tùy ý.

### Ví dụ với rate limiting và authentication

Khi bị rate-limit **trước khi verify credential**, có thể trả `429` và dừng chain để tránh tiêu tốn tài nguyên băm password. Khi một login attempt đến được provider và password sai, failure handler có thể trả `401` hoặc redirect. Nếu hai chính sách cùng tồn tại, cần xác định thứ tự và response cho từng trường hợp; không đưa `rate limit exceeded` vào `BadCredentialsException` chỉ để tái sử dụng một handler.

### Ví dụ với lỗi database

Nếu `UserDetailsService` không kết nối được DB, đó thường là lỗi **hạ tầng**, không phải bằng chứng password sai. Xử lý error/alert tương ứng, không cấp authentication và không công khai stacktrace. Việc chỉ trả 401 sẽ khiến người dùng cứ thử password lại, có thể che giấu outage.

## 14. Bài toán “đã gửi response rồi vẫn chạy controller”

Giả sử custom filter có:

```java
if (!tokenValid) {
    response.sendError(401);
}

chain.doFilter(request, response);
```

Khi token không hợp lệ, filter đã yêu cầu lỗi 401 nhưng **vẫn gọi chain**, nên các thành phần sau vẫn có thể chạy và phát sinh exception, ghi log, xử lý nghiệp vụ hoặc cố ghi response tiếp. Không thể dựa vào `sendError` để tự cắt đứt chương trình Java.

**Sửa tối thiểu:**

```java
if (!tokenValid) {
    response.sendError(401);
    return;
}

chain.doFilter(request, response);
```

Cần hiểu rằng đây chỉ là ví dụ về **flow control**. Với token authentication thực, không nên tự viết verifier JWT, không bỏ qua policy resource server, kiểm tra issuer/audience/signature/expiry đúng thư viện và đưa lỗi vào entry point phù hợp. Với một filter thực sự đóng vai trò authentication, thường dùng failure handler/entry point được framework hỗ trợ.

### Một biến thể gây lỗi khác: gọi chain hai lần

```java
if (matchesSomeRule) {
    chain.doFilter(request, response);
}

chain.doFilter(request, response); // Lần thứ hai!
```

Nếu điều kiện đúng, phần sau có thể được gọi hai lần, gây lặp controller hoặc các side effects khó đoán. Dùng `return` sau nhánh thành công hoặc viết một đường gọi chain duy nhất.

### Vì sao không “giải quyết” bằng catch mọi exception?

```java
try {
    chain.doFilter(request, response);
} catch (Exception ex) {
    response.setStatus(200);
}
```

Đây là một antipattern nghiêm trọng: bỏ qua security exception, biến bug và lỗi thực thành success giả, làm hỏng tracing và có thể trả response không nhất quán. Nếu cần ghi log, log có kiểm soát và **rethrow** hoặc để đúng handler xử lý. Không ghi raw credentials/Authorization headers/response body nhạy cảm khi debug.

## 15. Thiết kế một filter custom có contract rõ ràng

Trước khi code, hãy viết bảng quyết định cho filter của mình:

```text
Input: request HTTP đã qua những filter nào?
    |
    v
Filter này có áp dụng cho request không?
    |
    +-- Không: chain.doFilter -> return
    |
    +-- Có:
         |
         +-- Điều kiện hợp lệ và cần downstream?
         |       |
         |       +-- Có: set attrs/headers/context phù hợp
         |               -> chain.doFilter -> return
         |
         +-- Filter sở hữu response lỗi/early result?
         |       |
         |       +-- Có: set status/headers/body hoặc redirect
         |               -> return (không gọi chain)
         |
         +-- Lỗi bảo mật do framework cần xử lý?
         |       |
         |       +-- Có: xác định đúng exception class
         |               -> xác định handler/catch nằm ở đâu
         |               -> throw hoặc gọi handler theo contract
         |
         +-- Lỗi nghiệp vụ/hạ tầng?
                 |
                 +-- Đưa về MVC/global/container error mechanism
                     tương ứng, không biến thành auth error giả
```

Một code review nên trả lời được:

1. Filter này nằm trong **chain nào**, ở **thứ tự nào**?
2. Trên mỗi nhánh, gọi `chain.doFilter` **0, 1 hay hơn một lần**?
3. Nếu 0 lần, **ai đã ghi response**?
4. Nếu ném exception, **lớp nào bắt** và đang ở **trước hay sau** filter ném?
5. Có nơi nào ghi header/body sau khi response committed không?
6. Trường hợp request anonymous, remembered và fully authenticated có nhánh khác nhau không?
7. Lỗi 4xx có bị map sai thành 200, hoặc lỗi hạ tầng bị map thành 401 không?
8. Đăng ký filter có gây chạy hai lần ở Servlet container và `SecurityFilterChain` không?
9. Có data nhạy cảm trong `Authentication`, request logs hoặc exception messages không?
10. Nếu có `ERROR`/`ASYNC` dispatch, filter được gọi lại hay bị skip, và cleanup có an toàn không?

### Hậu xử lý an toàn sau `chain.doFilter`

Việc dùng `finally` hoặc hậu xử lý nên ưu tiên các việc **không thay đổi response đã committed**, ví dụ metrics/timing, dọn MDC/ThreadLocal do chính filter tạo. Đừng gọi `response.reset()` hoặc tự thay HTTP status 200/401 trong `finally` vì có thể xóa/đổi kết quả của controller hoặc handler chuyên trách.

## 16. Kiểm thử phải kiểm soát cả chain và handler

### 16.1. Unit tests cho filter flow

Đối với một filter custom, nên có:

| Test | Cấu hình | Assertion hữu ích |
| --- | --- | --- |
| Không áp dụng | URL/method khác | `chain.doFilter` được gọi đúng một lần. |
| Được phép | Token/policy hợp lệ | Request tới downstream; không tự viết error status. |
| Chặn có response | Rate limit | Status 429, body đúng, chain không được gọi. |
| Exception auth phía sau translator | `AuthenticationException` | Entry point được gọi, không chạy terminal. |
| Access denied với anonymous | `AnonymousAuthenticationToken` | Entry point/challenge theo policy. |
| Access denied với authenticated | `Authentication` thật | AccessDeniedHandler trả 403 theo policy. |
| Lỗi không liên quan security | `IllegalStateException` | Không bị translator biến thành 401/403. |
| Response committed | Đã flush, rồi deny | Không viết status/body lần hai; lỗi được quan sát đúng. |
| Filter sớm hơn translator | Throw trước khi gọi chain | Translator không tự nhận exception. |
| Dispatcher type | `REQUEST`/`ERROR`/`ASYNC` | Không đăng ký/thi hành sai theo lifecycle. |

Dùng Mockito/MockFilterChain hoặc Java lambda với bộ đếm để chứng minh filter nào được gọi. **Không chỉ assert response status**: một filter có thể trả 401 đúng nhưng vẫn cho controller chạy và gây side effects.

### 16.2. Integration test bằng MockMvc và Spring Security

Khi có một `SecurityFilterChain` thật, dùng `MockMvc` kèm Spring Security setup để kiểm tra:

- Request anonymous tới URL protected → entry point theo scheme.
- Login form đúng/sai → success/failure handler tương ứng và session/CSRF policy.
- Authenticated user thiếu role → 403.
- Custom rate limit → 429 và controller **không** được gọi.
- Lỗi validation → 400 qua MVC handler, không chuyển thành login failure.
- Lỗi hệ thống → 5xx/error contract, không tiết lộ thông tin.
- Thứ tự filter/chain: custom filter được gọi một lần, không bị bỏ qua do `securityMatcher` của chain khác.
- Response redirect có `Location` đúng, không có open redirect.
- ERROR dispatch và async nếu sản phẩm có sử dụng.

`@WithMockUser` hữu ích cho test authorization nhưng **không chứng minh** đường authentication thật, filter matcher, password encoder hay session persistence. Dùng credential và authentication manager/provider thật trong integration test khi mục tiêu là kiểm tra login.

### 16.3. Test phân biệt status và body sau response commit

Một test chỉ dùng `MockHttpServletResponse` có thể cho phép một số thao tác được mô phỏng khác Servlet container thật. Khi sản phẩm có streaming, error dispatch, buffering phức tạp hoặc reverse proxy, phải kiểm tra bằng integration test với server thật và quan sát HTTP bytes/status. Đừng suy diễn một status mock mặc định 200 thành client production chắc chắn đã nhận HTTP 200.

## 17. Dấu hiệu debug và các bẫy thường gặp

1. **Đã ghi JSON 401 nhưng controller vẫn thực thi:** quên `return` hoặc vẫn gọi `chain.doFilter`.
2. **Filter chạy hai lần:** đăng ký cả container và security chain, hoặc gọi chain hai lần.
3. **Lỗi AccessDeniedException không tới AccessDeniedHandler:** filter ném **trước** `ExceptionTranslationFilter`, hoặc MVC/resolver đã xử lý trước.
4. **Anonymous nhận 401 thay vì 403:** translator dùng entry point khi auth chưa đủ; đây có thể là hành vi đúng.
5. **User có role thấp nhận 403:** access denied sau khi đã authenticated đầy đủ; khác với password sai.
6. **Login sai password không xuất hiện trong ExceptionTranslationFilter:** authentication filter thường xử lý bằng failure handler.
7. **Thay `BadCredentialsException` thành `AccessDeniedException` để ra 403:** sai ngữ nghĩa, tăng rủi ro leak hoặc sai UX.
8. **Trả 200 body chứa `{"error":...}`:** client và monitoring có thể coi thành công; status phải phù hợp.
9. **Trả body rồi ném exception:** response có thể committed; handler không thể thay body/status an toàn.
10. **`sendError` rồi tiếp tục chain:** Servlet error response không tự chấm dứt code Java.
11. **Ném `RuntimeException` và nghĩ Spring Security sẽ trả 401:** translator chỉ quan tâm loại security exception phù hợp.
12. **`@ControllerAdvice` bắt `Exception.class` rộng rồi nuốt authorization denial:** có thể bỏ qua handler bảo mật mong đợi.
13. **Đặt filter sau `AnonymousAuthenticationFilter` rồi nghĩ chắc chắn sau translator:** cần đọc thứ tự thực tế; đây là hai mốc khác nhau.
14. **Chèn filter custom sau authorization mà nó cần authentication trước:** có thể quá muộn hoặc bỏ qua policy cần thiết.
15. **Dùng một chain cho API và web nhưng quên khác entry point:** browser có thể nhận redirect HTML thay vì JSON/challenge API.
16. **Dùng nhiều `SecurityFilterChain` nhưng chỉ debug một chain:** chain đầu tiên match có thể không chứa filter bạn mong đợi.
17. **Trả `null` ở authentication filter mà không gửi phản hồi:** client có thể gặp một response rỗng/trạng thái không rõ.
18. **Bật `continueChainBeforeSuccessfulAuthentication` để ép controller chạy:** downstream có thể thực thi trước khi authentication mới được lưu.
19. **Ghi body trong `finally`:** downstream có thể đã commit hoặc exception đang được handler khác xử lý.
20. **Bắt mọi exception rồi đổi thành 403:** che lỗi database/bug và làm access control khó quan sát.
21. **Ném `AccessDeniedException` cho rate limit hoặc lỗi hạ tầng:** trộn status 429/5xx với authorization.
22. **HTTP Basic 401 thiếu challenge header:** có thể làm client không biết cách xác thực; dùng entry point chuẩn theo scheme.
23. **Thay đổi `SecurityContextHolder` tùy tiện để tạo 403/401:** authentication state phải đến từ cơ chế tin cậy và được cleanup đúng.
24. **Tạo authenticated token từ giá trị header client:** có nguy cơ giả danh và nâng quyền.
25. **Log username/password/access token đầy đủ khi debug lỗi filter:** gây lộ credentials trong log/trace.
26. **Không kiểm thử `DispatcherType.ERROR`:** trang lỗi có thể bị chặn lần hai hoặc khôi phục context sai.
27. **Không xét response streaming/async:** lỗi sau khi gửi headers cần contract riêng, không thể “làm lại” JSON 401.
28. **Cho rằng `OncePerRequestFilter` là biện pháp chống mọi double registration:** không đúng với nhiều registration/dispatch paths.
29. **Nhầm `FilterChainProxy` chọn chain với `FilterChain.doFilter`:** một bên chọn cấu hình, một bên thực thi phần còn lại.
30. **Chỉ kiểm tra status mà không assert downstream invocation:** dễ bỏ sót side effects mặc dù response nhìn có vẻ đúng.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Gọi `chain.doFilter(request,response)` có ý nghĩa gì?

**Đáp án:** Nó mời phần còn lại của filter chain và cuối cùng servlet/controller xử lý. Khi lời gọi trở về, filter phía trước có thể tiếp tục hậu xử lý. Nó không tự ghi response.

**Câu 2.** Filter đã gọi `response.sendError(401)` thì có tự động ngừng chạy không?

**Đáp án:** Không. Code phải `return` hoặc có nhánh control-flow khác để không gọi tiếp chain; `sendError` là thao tác trên Servlet response, không phải câu lệnh điều khiển Java.

**Câu 3.** Trường hợp nào phù hợp để filter tự trả 429?

**Đáp án:** Khi một filter/gateway rate limiter sở hữu quyết định vượt hạn và response API; nó đặt status/headers/body theo contract rồi dừng chain để tránh tiêu tốn thêm tài nguyên.

**Câu 4.** Tại sao `AccessDeniedException` không nhất thiết trả HTTP 403?

**Đáp án:** `ExceptionTranslationFilter` có thể gọi `AuthenticationEntryPoint` cho anonymous hoặc remember-me chưa đủ mức; chỉ user authenticated đủ mức nhưng thiếu quyền mới thường tới `AccessDeniedHandler` trả 403.

**Câu 5.** Login form sai password do thành phần nào xử lý?

**Đáp án:** `AbstractAuthenticationProcessingFilter`/`UsernamePasswordAuthenticationFilter` thường bắt `AuthenticationException` trong login attempt rồi gọi `AuthenticationFailureHandler`. Không phải mọi login failure đều ném ra translator.

**Câu 6.** Filter A ném `AuthenticationException` trước khi gọi một translator nằm sau nó. Translator có bắt được không?

**Đáp án:** Không. Translator chưa được gọi, nên không ở trong call stack để bắt exception đó. Phải chọn thứ tự filter hoặc handler phù hợp.

**Câu 7.** Một controller đã được MVC `@ExceptionHandler` xử lý lỗi `AccessDeniedException` và trả response. Translator có luôn thấy không?

**Đáp án:** Không. Nếu resolver đã xử lý, exception không còn thoát ra tới translator. Vì thế cần test `@ControllerAdvice`/method-security mapping thực.

**Câu 8.** Một filter ném `IllegalStateException` phía sau translator. Nó có tự thành HTTP 401 không?

**Đáp án:** Không. Đây không phải `AuthenticationException`/`AccessDeniedException`; thường được tầng lỗi vận hành/MVC/container xử lý theo 5xx policy.

**Câu 9.** Nếu response đã committed và sau đó ném `AccessDeniedException`, có thể tự đổi sang 403 bằng `setStatus` không?

**Đáp án:** Không thể bảo đảm. Headers/status có thể đã gửi; Spring Security có thể ném thêm `ServletException` vì không xử lý an toàn được. Phải kiểm tra quyền trước khi stream body.

**Câu 10.** `AuthenticationEntryPoint` khác `AuthenticationFailureHandler` thế nào?

**Đáp án:** Entry point bắt đầu/challenge authentication cho request chưa đủ identity; failure handler trình bày **kết quả thất bại của một login attempt** do filter đã thử.

**Câu 11.** Một custom filter sau `AnonymousAuthenticationFilter` đã nằm sau translator chưa?

**Đáp án:** Không được giả định. Thứ tự phổ biến còn có translator ở vị trí muộn hơn; cần kiểm tra danh sách filter thật và xác định người bắt exception.

**Câu 12.** Với API stateless, vì sao 401/403 không được quyết định chỉ bằng việc có cookie session hay không?

**Đáp án:** Authentication có thể dựa bearer token hoặc cơ chế khác; policy phải dựa context thật, mức authentication và quyền. Session cookie không phải điều kiện phổ quát.

**Câu 13.** Tại sao không nên dùng `@WithMockUser` để kết luận login filter đã chạy đúng?

**Đáp án:** Mock user thường chèn `SecurityContext` trực tiếp; không kiểm tra matcher, provider, password encoder, failure handler hay việc lưu authentication.

**Câu 14.** Điều gì chứng minh một filter chặn được request?

**Đáp án:** Ngoài kiểm tra response status/body phù hợp, cần xác nhận **`chain.doFilter` không được gọi**, controller không có side effects, handler đúng được gọi và không có response thứ hai.

**Câu 15.** Một response có status 200 nhưng phương thức filter đã ném exception thì có phải login thành công?

**Đáp án:** Không. Mock Servlet response có thể còn status mặc định 200 trước khi container xử lý exception. Cần theo dõi exception và response thực trên HTTP server, không suy ra từ status object mock đơn lẻ.

## 19. Tài liệu tham khảo chính thức

- [Spring Security 6.5.11 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `FilterChain`, `FilterChainProxy`, thứ tự filters, `ExceptionTranslationFilter`, thêm custom filter và lưu ý double registration.
- [Spring Security 6.5.11 — ExceptionTranslationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html): cách xử lý `AuthenticationException`/`AccessDeniedException`, entry point, denied handler và request cache.
- [Spring Security 6.5.11 — AbstractAuthenticationProcessingFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html): login attempt, success/failure handlers và kết quả `null`.
- [Spring Security 6.5.11 — AuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/AuthenticationEntryPoint.html): bắt đầu/challenge authentication theo scheme.
- [Spring Security 6.5.11 — AccessDeniedHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/AccessDeniedHandler.html): phản hồi khi thiếu quyền.
- [Spring Security 6.5.11 — AuthenticationFailureHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html): phản hồi thất bại của login attempt.
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter` và quy tắc authorization HTTP.
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): `SecurityContextHolder`, repository, filter lifecycle và explicit save.
- [Spring Framework 6.2 — MockHttpServletResponse API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/mock/web/MockHttpServletResponse.html): status/commit/buffer trong Servlet mock.
- [Jakarta Servlet 6.0 — Filter / FilterChain / HttpServletResponse](https://jakarta.ee/specifications/servlet/6.0/apidocs/): hợp đồng `doFilter`, `sendError`, `sendRedirect` và commit.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): ý nghĩa các HTTP status và authentication challenge.

**Kết luận:** Trong Servlet filter chain, **`chain.doFilter` là cho phép phần sau chạy**, **ghi response rồi return là filter tự kết thúc request**, còn **ném exception là giao trách nhiệm cho bộ xử lý có thực sự bao quanh vị trí ném**. Với Spring Security, `AuthenticationEntryPoint` xử lý nhu cầu bắt đầu xác thực, `AuthenticationFailureHandler` xử lý login attempt thất bại, và `AccessDeniedHandler` xử lý thiếu quyền của người đã có authentication phù hợp. `ExceptionTranslationFilter` kết nối các exception bảo mật phát sinh ở downstream với các handler đó nhưng **không phải global catch**, và không cứu được response đã committed. Chọn đúng nhánh, đúng vị trí filter, đúng HTTP status và kiểm thử cả **số lần gọi chain** mới tạo ra hành vi an toàn, có thể dự đoán.