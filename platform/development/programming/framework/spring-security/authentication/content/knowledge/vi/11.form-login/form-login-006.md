# RequestCache, SavedRequest và khôi phục yêu cầu sau đăng nhập

Người dùng chưa đăng nhập mở một liên kết tới báo cáo nội bộ:

```text
GET /reports/summary?period=2026
```

Ứng dụng yêu cầu xác thực và chuyển họ tới trang đăng nhập. Sau khi nhập mật khẩu đúng, người dùng thường mong được **trở lại đúng báo cáo vừa mở**, không phải luôn bị đưa về trang chủ. Trong Spring Security Servlet, hành vi này được xây bằng sự phối hợp giữa **`ExceptionTranslationFilter`, `RequestCache`, `SavedRequest`, `SavedRequestAwareAuthenticationSuccessHandler` và `RequestCacheAwareFilter`**.

Đây là bài Knowledge thuộc nhóm **Đăng nhập biểu mẫu** của *Spring Security - authentication*. Bài giải thích chính xác **khi nào một request được lưu, metadata nào được giữ, tại sao redirect sau login tìm lại URL ban đầu, khi nào cache bị xóa**, cùng giới hạn an ninh và ví dụ Java 17+/Spring Boot 3.x có MockMvc integration test. Chú ý đặc biệt đến thay đổi **tham số `continue` trong Spring Security 6**, các request không an toàn như POST, open redirect, nhiều tab và phiên stateful/stateless.

**Tóm tắt:** `RequestCache` không phải cơ sở dữ liệu người dùng và không phải `SecurityContextRepository`. Nó lưu *thông tin về yêu cầu bị gián đoạn do chưa đăng nhập*. `SavedRequestAwareAuthenticationSuccessHandler` dùng thông tin đó để **redirect** sau khi đăng nhập thành công; `RequestCacheAwareFilter` có thể khôi phục một request wrapper khi browser theo redirect tới URL phù hợp. Điều này **không đồng nghĩa tự replay nguyên HTTP body, tự submit lại thanh toán hay bỏ qua authorization**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Kể đúng chuỗi từ request vào vùng bảo vệ đến lần request đầu tiên sau login.
2. Giải thích `RequestCache`/`SavedRequest`/`DefaultSavedRequest`/`HttpSessionRequestCache` và các phương thức `saveRequest`, `getRequest`, `getMatchingRequest`, `removeRequest`.
3. Phân biệt trách nhiệm của `ExceptionTranslationFilter`, `LoginUrlAuthenticationEntryPoint`, `SavedRequestAwareAuthenticationSuccessHandler`, `RequestCacheAwareFilter` và `SecurityContextRepository`.
4. Giải thích sự khác biệt Spring Security 5 và 6 trong việc tối ưu tra cứu request với query parameter `continue`.
5. Dự đoán đường redirect khi có saved request, không có saved request, `alwaysUseDefaultTargetUrl`, `targetUrlParameter` hoặc cấu hình `NullRequestCache`.
6. Hiểu vì sao bookmark GET là kịch bản chính, còn POST với body, CSRF token, stream và giao dịch thay đổi dữ liệu **không được tự động gửi lại** sau login.
7. Viết cấu hình form login stateful với một `HttpSessionRequestCache` dùng chung cho security chain và success handler.
8. Chạy integration test: anonymous GET được lưu → form login đúng → redirect về URL kèm `continue` → request tiếp theo được authenticated → cache được tiêu thụ.
9. Thiết kế giới hạn lưu URL, chống open redirect/host-header poisoning, không cache query bí mật và không lưu nhầm request khác do nhiều tab.
10. Chọn khi nào cần tắt request caching cho API stateless, SPA hoặc endpoint nhạy cảm.

## 2. Khái niệm: “lưu yêu cầu” không phải “lưu nội dung thao tác”

`SavedRequest` biểu diễn **metadata cần thiết** về request bị gián đoạn để ứng dụng có thể quay lại vị trí ban đầu sau khi xác thực. Nó không phải một bản sao hoàn chỉnh có thể phát lại mọi byte của network stream trong tương lai.

Ví dụ request vào:

```http
GET /reports/summary?period=2026 HTTP/1.1
Host: app.example.test
Accept: text/html
```

Nếu chưa authenticated, hệ thống có thể ghi nhớ:

```text
Scheme/host/port/path = https://app.example.test/reports/summary
Query string          = period=2026
Method                = GET
Headers/parameters    = một phần metadata do DefaultSavedRequest giữ
Session ID            = session nơi RequestCache lưu request
```

Sau login, browser nhận **302 tới URL đã lưu**. Browser gửi một **request mới** đến URL đó, rồi authorization kiểm lại principal vừa đăng nhập. Nó không “tiếp tục” chính xác một servlet thread cũ. Request gốc đã kết thúc bằng redirect đến login; những bước phía sau là những HTTP exchanges khác.

### 2.1 Hai thứ hay bị gọi cùng là “session”

| Khái niệm | Dữ liệu | Mục đích |
| --- | --- | --- |
| **Saved request** | URL đích, query, method và metadata để quay lại. | Quyết định nên chuyển hướng tới đâu sau login. |
| **Authentication trong `SecurityContext`** | Principal đã xác minh, authorities, trạng thái authenticated. | Cho phép request sau vượt authentication/authorization. |
| **`HttpSession`** | Container server-side có thể chứa cả hai loại dữ liệu trên dưới các key khác nhau. | Duy trì state giữa các HTTP requests bằng session ID. |
| **Browser cookie `JSESSIONID`** | Tham chiếu tới một session phía server. | Nối những request độc lập của browser với cùng session. |

**Có `SPRING_SECURITY_SAVED_REQUEST` trong session không chứng minh user đã đăng nhập.** Ngược lại, đã authenticated nhưng không có saved request là hoàn toàn bình thường, ví dụ user truy cập trực tiếp `/login` rồi login.

### 2.2 Các class trọng yếu

| Thành phần | Việc làm |
| --- | --- |
| `ExceptionTranslationFilter` | Phát hiện `AuthenticationException` hoặc `AccessDeniedException` cần khởi động authentication; gọi `RequestCache.saveRequest` trước khi `AuthenticationEntryPoint.commence`. |
| `AuthenticationEntryPoint` | Chọn cách yêu cầu login, ví dụ `LoginUrlAuthenticationEntryPoint` redirect tới `/login`. |
| **`RequestCache`** | Interface lưu, đọc, tìm request khớp và xóa saved request. |
| **`SavedRequest`** | Giao diện biểu diễn request được ghi nhớ; `DefaultSavedRequest` là implementation thường gặp. |
| **`HttpSessionRequestCache`** | Implementation lưu `SavedRequest` trong `HttpSession`. |
| `SavedRequestAwareAuthenticationSuccessHandler` | Khi login thành công, tìm saved request và chọn redirect đích. |
| `RequestCacheAwareFilter` | Trên request theo redirect, gọi `getMatchingRequest` để khôi phục wrapper nếu khớp, đồng thời tiêu thụ cache. |
| `SavedRequestAwareWrapper` | Wrapper giúp downstream đọc metadata request đã được lưu theo semantics của implementation. |

### 2.3 RequestCache interface

Đây là chữ ký khái niệm từ Spring Security 6.x (để học, không tự định nghĩa lại interface):

```java
public interface RequestCache {
    void saveRequest(HttpServletRequest request, HttpServletResponse response);

    SavedRequest getRequest(
            HttpServletRequest request, HttpServletResponse response);

    HttpServletRequest getMatchingRequest(
            HttpServletRequest request, HttpServletResponse response);

    void removeRequest(
            HttpServletRequest request, HttpServletResponse response);
}
```

- `saveRequest`: ghi nhận request bị chặn, nếu implementation/policy cho phép.
- `getRequest`: **đọc saved request nhưng giữ nó trong cache**; success handler có thể dùng để quyết định đích redirect.
- `getMatchingRequest`: xét request hiện tại có khớp request đã lưu hay không; khi khớp trả wrapped request và **loại saved request khỏi cache**.
- `removeRequest`: xóa saved request một cách rõ ràng, ví dụ khi bỏ qua đích cũ hoặc dùng default target.

Không nhầm `getRequest` với `getMatchingRequest`. Một cái dùng **tìm thông tin đích**, cái kia dùng **kiểm request quay lại và tiêu thụ**. Đây là chìa khóa hiểu vì sao saved request có thể **vẫn còn trong session ngay sau redirect login**.

## 3. Toàn bộ chuỗi trước login và sau login

```text
T0: Browser -> GET /reports/summary?period=2026
                |
                v
       SecurityFilterChain
                |
                v
       AuthorizationFilter -> request cần authenticated
                |
                v
       ExceptionTranslationFilter bắt exception liên quan
                |
                +--> RequestCache.saveRequest(request, response)
                |        |
                |        +--> HttpSession chứa DefaultSavedRequest
                |
                +--> LoginUrlAuthenticationEntryPoint
                         |
                         v
                    HTTP 302 /login

T1: Browser -> GET /login
                |
                v
       Form login page; user nhập username/password

T2: Browser -> POST /login + CSRF token phù hợp
                |
                v
       UsernamePasswordAuthenticationFilter
       AuthenticationManager / ProviderManager
       DaoAuthenticationProvider + UserDetailsService + PasswordEncoder
                |
                +--> Sai: failure handler -> không dùng saved request
                |
                +--> Đúng: SessionAuthenticationStrategy
                          SecurityContext được lưu đúng repository
                          SavedRequestAwareAuthenticationSuccessHandler
                               |
                               +--> RequestCache.getRequest(...)
                               +--> redirect tới savedRequest.getRedirectUrl()
                                    (với Spring Security 6 có thể có ?continue)
                          HTTP 302 tới /reports/summary?period=2026&continue

T3: Browser -> GET /reports/summary?period=2026&continue
                |
                v
       SecurityContextRepository nạp Authentication từ session
       RequestCacheAwareFilter.getMatchingRequest(...)
                |
                +--> kiểm query marker / URL khớp
                +--> removeRequest(...) nếu khớp
                +--> SavedRequestAwareWrapper cho downstream
                |
                v
       AuthorizationFilter kiểm lại quyền
                |
                v
       Controller báo cáo -> HTTP 200
```

Sơ đồ là **một hành trình thường gặp với form login stateful và `HttpSessionRequestCache`**, không phải bảo đảm cho mọi cấu hình authentication. Một API dùng Bearer/JWT, basic auth, custom entry point trả JSON 401 hoặc `NullRequestCache` có thể không có redirect và cũng không tạo `SavedRequest`.

### 3.1 Vì sao `ExceptionTranslationFilter` quan trọng?

`ExceptionTranslationFilter` là cầu nối từ *lỗi bảo mật trong filter chain* tới *hành động bắt đầu authentication*. Khi principal chưa xác thực mà endpoint yêu cầu authentication, nó có thể lưu request gốc trước khi redirect tới login. Vì vậy saved request không phải do controller `/login` tạo lúc người dùng đã nhập mật khẩu. Nó đến từ **request được bảo vệ xảy ra trước đó**.

Nếu chính sách khác phát hiện người dùng đã authenticated nhưng thiếu role, Spring Security thường xử lý bằng **403 Access Denied**, không phải cứ tự lưu request và chuyển sang login lại. Cần phân biệt anonymous/unauthenticated với authenticated-but-forbidden; đừng biến mọi 403 thành vòng lặp login vô hạn.

### 3.2 Trạng thái ở ba thời điểm

| Thời điểm | `SecurityContext` | `RequestCache` | Điều người dùng thấy |
| --- | --- | --- | --- |
| Anonymous GET bị chặn | Chưa có authenticated principal | Có thể chứa request đến báo cáo | Redirect tới login. |
| Ngay sau login thành công | Có Authentication hợp lệ trong session | Saved request có thể **chưa bị xóa** | Redirect tới URL gốc. |
| Request quay lại đích hợp lệ | Context được nạp từ session | `getMatchingRequest` có thể tiêu thụ saved request | Trang ban đầu được trả về nếu đủ quyền. |

**Không coi saved request là bằng chứng authorization.** Dù URL đã được lưu, khi request quay lại hệ thống vẫn phải kiểm vai trò, tenant, ownership và trạng thái account theo chính sách.

### 3.3 Redirect khác forward

Saved-request flow thông thường là **HTTP redirect**, nghĩa là browser tạo request mới. Nó không phải server-side `RequestDispatcher.forward` nguyên request cũ hay continuation giữ nguyên method/body/transaction. Nếu cần khôi phục trạng thái một biểu mẫu đang điền, phải thiết kế **draft** được lưu hợp lệ và chống replay riêng, chứ không xem `RequestCache` là bộ nhớ “toàn bộ POST” của browser.

## 4. HttpSessionRequestCache: dữ liệu nằm ở đâu?

`HttpSessionRequestCache` là implementation mặc định thường dùng cho form login Servlet. Nó lưu một `DefaultSavedRequest` trong `HttpSession`; key mặc định là:

```text
SPRING_SECURITY_SAVED_REQUEST
```

Đây là attribute nội bộ của framework, **khác** với `SPRING_SECURITY_CONTEXT` dùng để lưu authentication. Một session có thể đồng thời chứa:

```text
HttpSession S
├── SPRING_SECURITY_SAVED_REQUEST
│     └── DefaultSavedRequest("/reports/summary?period=2026...")
├── SPRING_SECURITY_CONTEXT
│     └── SecurityContext(Authentication("alice", ROLE_USER))
└── CSRF token / app attributes / session metadata
```

### 4.1 Khi lưu có thể tạo session mới

`HttpSessionRequestCache` có lựa chọn `createSessionAllowed`. Mặc định thường cho phép tạo `HttpSession` để ghi nhớ request ban đầu nếu chưa có session. Đây là một **tác dụng phụ hữu ích nhưng không miễn phí**: một anonymous GET vào tài nguyên bảo vệ có thể khiến server cấp session cookie chỉ để giữ URL.

Nếu hệ thống có lượng API anonymous lớn, chi phí session creation có thể đáng kể. Có thể:

- Chỉ lưu những request GET/HEAD hợp lý thông qua `RequestMatcher`.
- Đặt `setCreateSessionAllowed(false)` nếu không muốn cache tự tạo session, đồng nghĩa request không có session ban đầu có thể không được lưu.
- Dùng `NullRequestCache` nếu luôn trở về trang mặc định hoặc API tự quản lý navigation.
- Dùng cơ chế quay lại đích khác có kiểm soát (chẳng hạn `returnTo` đã ký/allowlist) khi UX yêu cầu nhưng không dùng server session.
- Giám sát kích thước và TTL của HTTP sessions.

### 4.2 Chỉ lưu những URL phù hợp

Mặc định `HttpSessionRequestCache` có thể lưu rộng những request cần authentication. Một ứng dụng thực thường nên giới hạn các URL có ý nghĩa để redirect sau login:

```java
HttpSessionRequestCache cache = new HttpSessionRequestCache();
cache.setRequestMatcher(
        new AntPathRequestMatcher("/reports/**", "GET"));
cache.setMatchingRequestParameterName("continue");
```

Đây là **đoạn cấu hình**, cần imports Spring Security Servlet. Chỉ request GET thuộc `/reports/**` mới được lưu theo matcher này. Đừng chặn yêu cầu URL cấp phép khác một cách vô ý: chọn matcher theo hành vi sản phẩm. Với HEAD có thể quyết định không lưu vì browser thường không dùng nó như một trang điều hướng.

### 4.3 Nhiều tab dùng chung một session

`HttpSessionRequestCache` mặc định giữ **một saved request dưới một key** cho mỗi session, không phải queue vô hạn cho mọi tab. Ví dụ:

```text
Tab A (anonymous) -> GET /reports/annual   -> saved = A
Tab B (anonymous) -> GET /reports/monthly  -> saved = B (ghi đè A)
Tab A submit login -> success handler lấy B -> redirect Tab A sang monthly
```

Đây là giới hạn UX quan trọng. Nếu cần đúng *mỗi tab quay lại đúng nơi riêng*, phải thiết kế state riêng có correlation ID và integrity/TTL/ownership, không giả định `SPRING_SECURITY_SAVED_REQUEST` lưu một stack per-tab.

Cũng cần chú ý login thất bại nhiều lần và các request anonymous xen kẽ có thể cập nhật saved request; không để một URL nhạy cảm bị cố tình ép vào session rồi dùng làm open redirect.

## 5. SavedRequest / DefaultSavedRequest thực sự lưu gì?

`SavedRequest` chứa thông tin cần thiết để tái dựng/đối chiếu một yêu cầu gốc. `DefaultSavedRequest` là implementation được `HttpSessionRequestCache` sử dụng phổ biến. Nó có thể lưu method, URL redirect, query, parameters, selected headers/cookies/locales và metadata theo phiên bản.

**Những điều không nên suy ra:**

- Saved request không phải bản ghi **toàn bộ raw input stream** và không thể tái gửi một body JSON/multipart tùy ý với semantics giao dịch cũ.
- Nó không phải một authorization grant; controller vẫn phải kiểm quyền khi quay lại.
- Nó không phải cơ chế bảo đảm một lần (exactly-once) hoặc chống duplicate charge.
- Nó không bảo vệ nội dung query URL khỏi bị browser history, proxy/log hoặc session dump ghi lại.
- Nó không tự kiểm host đích có đáng tin để redirect hay không.
- Nó không tự kết nối một tác vụ đang chờ ở thread cũ.

### 5.1 `getRedirectUrl`

`SavedRequest.getRedirectUrl()` trả URL dùng để điều hướng sau login. Trong cấu hình Spring Security 6 với `HttpSessionRequestCache` và marker `continue`, URL saved request có thể chứa tham số này nhằm cho request tiếp theo chỉ tìm cache khi thật sự cần.

Ví dụ:

```text
Request ban đầu:  /reports/summary?period=2026
Redirect sau login: /reports/summary?period=2026&continue
```

Dấu `&` hay `?` phụ thuộc URL gốc có query hay chưa. Đây là marker **để tối ưu matching request cache**, không phải token xác thực, không chứng minh user có quyền. Một client tự thêm `?continue` vào URL **không nhận được quyền mới**; request vẫn đi qua SecurityContext/authorization.

### 5.2 RequestCache aware wrapping

Sau khi login thành công, `SavedRequestAwareAuthenticationSuccessHandler` có thể **giữ saved request trong session** trong lúc gửi redirect. `RequestCacheAwareFilter` chạy ở lần GET tiếp theo, dùng `getMatchingRequest` để tìm saved request và, nếu phù hợp, đưa một `SavedRequestAwareWrapper` cho downstream rồi xóa cache.

Vì vậy các thao tác được phân biệt:

```text
successHandler.getRequest(...)     = đọc để biết nơi redirect, không xóa
response.sendRedirect(savedUrl)    = browser tạo request mới
requestCache.getMatchingRequest(...) = nếu khớp thì consume + wrap
```

Trong Spring Security 6, marker `continue` giúp tránh việc `RequestCacheAwareFilter` thường xuyên đọc `HttpSession` khi không có yêu cầu cần khôi phục.

## 6. Spring Security 6: tham số continue và cải tiến hiệu năng

### 6.1 Vấn đề của lối cũ

Trong thiết kế thường gặp ở Spring Security 5, `RequestCacheAwareFilter` có thể hỏi `HttpSession` về saved request **trên nhiều request** ngay cả khi đa số request không liên quan tới luồng vừa login. Truy vấn session thừa có thể gây I/O, đặc biệt khi session nằm ở Redis hoặc hệ thống phân tán.

### 6.2 Hành vi Spring Security 6

Theo hướng dẫn migration Spring Security 6, `HttpSessionRequestCache` mặc định sử dụng **`continue`** làm tên query parameter chỉ ra rằng `getMatchingRequest` cần kiểm saved request. Điều này giảm số lần truy vấn session chỉ để tìm URL cần khôi phục.

```java
HttpSessionRequestCache requestCache = new HttpSessionRequestCache();
requestCache.setMatchingRequestParameterName("continue");

http.requestCache(cache -> cache.requestCache(requestCache));
```

Với cách này, **`getMatchingRequest`** có thể bỏ qua tra cache nếu query không chứa `continue`. Ngược lại, **`getRequest`** ở success handler vẫn có thể trực tiếp đọc saved request để quyết định redirect. Đừng suy ra mọi API của RequestCache đều chỉ hoạt động khi có `continue`.

### 6.3 Tại sao URL gốc có thể “tự thêm continue”?

`DefaultSavedRequest` có thể xây URL đích gắn marker theo cấu hình `matchingRequestParameterName`. Khi login thành công, handler redirect tới `savedRequest.getRedirectUrl()` với marker đó. Request theo redirect có marker, `RequestCacheAwareFilter` mới truy vấn và match.

Chỉ kiểm sự có mặt của marker **không đủ**: implementation cũng cần so URL hiện tại với URL đã lưu, xử lý session và khớp request thích hợp. Marker không phải password, không phải CSRF token và không phải một quyền mới.

### 6.4 Nếu đã tùy biến RequestCache từ trước

Một application nâng cấp có thể gặp:

- Tự viết `RequestCache` không hiểu marker `continue`.
- Dùng `HttpSessionRequestCache` nhưng set tên marker khác.
- Thêm custom success handler redirect đến URL **không mang marker**, khiến `RequestCacheAwareFilter` không consume saved request như mong đợi.
- Dùng `NullRequestCache` nhưng success handler vẫn nghĩ có saved request.
- Có nhiều `SecurityFilterChain` với các RequestCache khác nhau.
- Backend/SPA tự loại query marker trước request tiếp theo, làm matching không chạy.

**Khuyến nghị:** Cấu hình **cùng một instance RequestCache** ở filter chain và `SavedRequestAwareAuthenticationSuccessHandler` nếu tùy biến, rồi test toàn bộ anonymous GET → login → redirect → GET đích. Không tự “fix” bằng cách tắt SecurityContextRepository hoặc đụng session attribute thủ công.

## 7. SavedRequestAwareAuthenticationSuccessHandler chọn redirect theo ưu tiên nào?

`SavedRequestAwareAuthenticationSuccessHandler` kế thừa `SimpleUrlAuthenticationSuccessHandler`. Sau login thành công nó quyết định:

| Trường hợp | Đích redirect | Saved request |
| --- | --- | --- |
| `alwaysUseDefaultTargetUrl=true` | Luôn `defaultTargetUrl` | **Bị xóa** nếu có. |
| Request login có `targetUrlParameter` đã cấu hình và giá trị có ý nghĩa | Giá trị target theo cấu hình base handler | **Bị xóa** nếu có. |
| Có `SavedRequest` trong RequestCache | `savedRequest.getRedirectUrl()` | **Còn cache** cho request theo redirect xử lý. |
| Không có saved request | Hành vi `SimpleUrlAuthenticationSuccessHandler` (default target, v.v.) | Không có để xóa. |

### 7.1 `alwaysUseDefaultTargetUrl`

Nếu sản phẩm muốn mọi login đi tới dashboard:

```java
SavedRequestAwareAuthenticationSuccessHandler handler =
        new SavedRequestAwareAuthenticationSuccessHandler();
handler.setAlwaysUseDefaultTargetUrl(true);
handler.setDefaultTargetUrl("/home");
```

Trong nhánh này, handler xóa saved request; thông tin về URL ban đầu **không còn được dùng** để redirect. Hành vi này khác việc chỉ set `defaultTargetUrl`, bởi **default target chỉ là fallback** khi không có saved request, trừ khi force always.

### 7.2 `targetUrlParameter`: cẩn thận open redirect

Bạn có thể cấu hình một tên parameter cho đích redirect. Nhưng nếu giá trị đến trực tiếp từ client mà không có validate, nó có thể trở thành lỗ hổng **open redirect** (dẫn người dùng sang domain do attacker chọn) hoặc có tác dụng độc hại khi URL được browser/proxy giải thích.

Không làm như sau:

```java
// KHÔNG KHUYẾN NGHỊ: giá trị next do client tùy ý nhập.
handler.setTargetUrlParameter("next");
```

nếu chưa có policy kiểm đường đích. Nên ưu tiên đích do server xác định từ cache phù hợp và allowlist route nội bộ; nếu cần `returnTo` client-supplied, chuẩn hóa path và chặn scheme/host bất hợp lệ, `//evil.example`, dấu backslash/encoding nhiều lớp, CRLF và context path confusion. Đừng cho phép redirect tùy ý sang domain bên ngoài chỉ vì login đã thành công.

### 7.3 `useReferer` không phải bằng chứng tin cậy

`Referer` có thể thiếu hoặc bị giả, bị browser policy lọc, bị proxy chỉnh và chứa URL bên ngoài. Không nên dùng nó làm nguồn chính xác định redirect sau login nếu không kiểm nguồn. `SavedRequest` dưới server session có lợi thế về lifecycle nhưng vẫn chứa **URL gốc có thành phần do client điều khiển**; cả hai cần quy tắc an toàn.

### 7.4 User login trực tiếp

Nếu user chủ động mở `/login` (không có unauthenticated request trước đó), handler không có SavedRequest để đọc và dùng default target, ví dụ `/home`. Đây không phải lỗi RequestCache; không có “trang trước” nào được Spring ghi nhớ.

### 7.5 Saved request có nhưng user không đủ quyền

Một user chưa đăng nhập mở `/admin`, sau đó đăng nhập bằng account không có `ROLE_ADMIN`. Sau login, success handler vẫn có thể redirect về `/admin` theo SavedRequest. **Lần request mới phải trả 403**, không được bypass authorization chỉ vì URL đã cache. Nếu UX muốn thông báo “không đủ quyền” rồi quay dashboard, đó là flow bổ sung đã được thiết kế, không phải quyền của cache.

## 8. RequestCacheAwareFilter xử lý request quay lại

`RequestCacheAwareFilter` sử dụng `RequestCache.getMatchingRequest(request, response)`; khi có wrapper khớp, nó đưa wrapper vào phần còn lại của filter chain. Mục đích là giúp các lớp phía sau thấy metadata request tương ứng với SavedRequest trong hoàn cảnh phù hợp.

Pseudo-flow:

```java
HttpServletRequest wrapped =
        requestCache.getMatchingRequest(request, response);

if (wrapped == null) {
    chain.doFilter(request, response);
} else {
    chain.doFilter(wrapped, response);
}
```

Đây là **minh họa logic**, không phải lời mời đăng ký filter trùng với Spring Security. Filter đã thuộc chain khi request caching được cấu hình. Đừng tạo `RequestCacheAwareFilter` thêm một lần dưới dạng Servlet `@Component` nếu nó đã nằm trong `FilterChainProxy`.

### 8.1 Vì sao saved request chưa bị xóa ngay sau login?

Handler có nhiệm vụ **đưa browser tới đích**. Nếu xóa SavedRequest ngay khi gửi redirect, `RequestCacheAwareFilter` sẽ không thể tìm nó để tạo `SavedRequestAwareWrapper` cho request theo redirect. Vì vậy Javadoc nhấn mạnh: khi dùng saved URL, handler **để cache lại**, chờ request khớp tiếp theo tiêu thụ.

### 8.2 Nếu user không bấm redirect hoặc đóng browser

Saved request có thể còn trong session tới khi bị ghi đè, xóa, session hết hạn hoặc một flow khác loại bỏ. Không giả định nó tự xóa sau một khoảng tính bằng milliseconds. Với session store phân tán, xem retention/TTL; với dữ liệu nhạy cảm, nên giảm những gì cache chứa và có cleanup khi logout/switch account.

### 8.3 Nếu URL không match

Nếu client bỏ mất query `continue`, đổi đường dẫn, đổi scheme/host hoặc có proxy rewrite URL, `getMatchingRequest` có thể không thấy matching request; saved request vẫn còn cho đến khi cơ chế khác dọn. Bản thân việc truy cập trang vẫn có thể được authorization cho phép; **khả năng khôi phục metadata và khả năng truy cập endpoint là hai điều khác nhau**.

## 9. Những request không nên tự replay: POST, upload, payment và các thao tác thay đổi trạng thái

Đây là giới hạn an toàn quan trọng nhất của SavedRequest.

### 9.1 Redirect của browser thường tạo một GET

Giả sử user gửi:

```http
POST /orders/confirm HTTP/1.1
Content-Type: application/json

{"orderId":42,"confirm":true}
```

Nếu chưa đăng nhập và bị chuyển tới form login, không nên mong `RequestCache` giữ nguyên toàn bộ JSON stream rồi tự thực thi `POST /orders/confirm` sau login. Redirect tới URL gốc là một **lần điều hướng mới**, thường là GET. Raw body của request cũ không được framework bảo đảm tái tạo/submit tự động.

Một số metadata như method/parameters có thể nằm trong `DefaultSavedRequest`, nhưng wrapper không biến nó thành một hệ thống giao dịch exactly-once. Đừng coi "replay request" trong Javadoc là cam kết **replay mọi side effect** hoặc byte-for-byte.

### 9.2 CSRF có thể chặn POST trước khi nó được cache

Ở cookie-based browser apps, `CsrfFilter` thường nằm trong filter chain trước khi xử lý một POST unsafe. Nếu thiếu CSRF token, request có thể bị từ chối 403 trước khi xảy ra authentication entry point và request cache; không phải mọi POST anonymous đều đi vào SavedRequest.

Một POST có CSRF token hợp lệ cũng không tự trở thành thao tác được tái gửi sau login. Khi identity thay đổi, CSRF token có thể được rotate/invalidate, nên submit lại thông tin cũ mà không lấy token mới có thể thất bại như thiết kế.

### 9.3 Pattern an toàn: POST → yêu cầu login → quay lại GET/draft

Với form nhiều bước:

1. Người dùng chuẩn bị draft được lưu **rõ ràng**, có session/user scope, TTL và xác minh state.
2. Nếu cần login, điều hướng tới `GET /drafts/{id}/review` hoặc một route GET được allowlist.
3. Sau login, browser quay lại màn hình review, không tự chạy lại POST.
4. Người dùng xem lại thay đổi và chủ động bấm Confirm với CSRF/idempotency key mới.
5. Server kiểm quyền đối tượng/tenant và xử lý transaction đúng một lần, chống submit lặp.

Với API, phản hồi 401 hoặc redirect theo hợp đồng, client chỉ gửi lại unsafe request **sau quyết định rõ** và phải xử lý idempotency/confirmation; không nhét body transaction vào query string `next`.

### 9.4 GET cũng phải không gây side effect

Saved-request UX hoạt động thuận nhất nếu GET tuân thủ tính chất **safe** theo HTTP. Nếu endpoint `GET /delete?id=42` làm xóa dữ liệu, một redirect sau login có thể vô tình thực thi thao tác nguy hiểm. Sửa API để mutation dùng POST/PUT/PATCH/DELETE có CSRF/authz/idempotency phù hợp; không dùng SavedRequest như một lớp bảo vệ thay thế.

## 10. Cấu hình nào tạo, lưu hoặc bỏ qua saved request?

### 10.1 Mặc định form login

Với:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/reports/**").authenticated()
                    .anyRequest().permitAll())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Spring Security có thể cấu hình mặc định `HttpSessionRequestCache`, login entry point và success handler hiểu saved request. **Không cần tự viết controller để có redirect về trang trước login.** Tùy biến nên được làm vì nhu cầu cụ thể: filter chain, route, post-login UX, performance hoặc yêu cầu an ninh.

### 10.2 Tùy biến một RequestCache dùng chung

```java
@Bean
RequestCache requestCache() {
    HttpSessionRequestCache cache =
            new HttpSessionRequestCache();

    cache.setMatchingRequestParameterName("continue");
    cache.setRequestMatcher(
            new AntPathRequestMatcher("/reports/**", "GET"));
    return cache;
}

@Bean
SavedRequestAwareAuthenticationSuccessHandler savedRequestSuccessHandler(
        RequestCache cache) {

    SavedRequestAwareAuthenticationSuccessHandler handler =
            new SavedRequestAwareAuthenticationSuccessHandler();
    handler.setRequestCache(cache);
    handler.setDefaultTargetUrl("/home");
    return handler;
}

@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http, RequestCache cache,
        SavedRequestAwareAuthenticationSuccessHandler handler)
        throws Exception {

    return http
            .requestCache(c -> c.requestCache(cache))
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/reports/**").authenticated()
                    .requestMatchers("/home").permitAll()
                    .anyRequest().denyAll())
            .formLogin(login -> login.successHandler(handler))
            .build();
}
```

Đây là **các Bean methods mẫu để ghép trong `@Configuration`/Spring Boot**, chưa gồm imports/package và controller. Bản runnable đầy đủ ở mục 13.

### 10.3 Vì sao phải dùng cùng RequestCache?

Nếu `ExceptionTranslationFilter` lưu vào cache A, nhưng `SavedRequestAwareAuthenticationSuccessHandler` đọc cache B (ví dụ B là `NullRequestCache` hoặc dùng key khác), sau login không có saved URL và fallback về `/home`. Nếu success handler đọc đúng nhưng `RequestCacheAwareFilter` dùng cache C khác, URL redirect có thể đúng nhưng request matching/removal không hoàn tất. Hãy cấu hình một instance hoặc bảo đảm các implementation cùng truy cập đúng storage/attribute namespace; tránh biến saved request lifecycle thành nhiều hệ thống không nhất quán.

### 10.4 Tắt hoàn toàn lưu request với NullRequestCache

Với ứng dụng không cần quay lại URL cũ:

```java
http.requestCache(cache -> cache
        .requestCache(new NullRequestCache()));
```

`NullRequestCache` không lưu request và không khôi phục matching request. Sau login, `SavedRequestAwareAuthenticationSuccessHandler` không tìm được saved request và dùng default target theo cấu hình. Điều này thích hợp nếu app có navigation riêng, SPA dùng client router, API chỉ trả JSON 401, hoặc muốn giảm session allocations cho unauthenticated requests.

**Nhưng:** Tắt RequestCache không đồng nghĩa vô hiệu hóa session authentication hay `SecurityContextRepository`. Người dùng vẫn có thể đăng nhập bằng form và giữ session; chỉ **nhớ URL cũ** bị tắt.

### 10.5 CookieRequestCache và giải pháp custom

Một số phiên bản Spring Security có `CookieRequestCache` để lưu một phần thông tin URL vào cookie. Khi dùng cookie, phải đánh giá:

- Integrity: cookie do browser mang, không tin một redirect target tùy ý nếu không có bảo vệ/allowlist.
- Confidentiality: URL nhạy cảm không nên nằm ở cookie/log.
- Cookie flags, TTL, scope, size, cross-site behavior.
- Phiên bản API và những hạn chế về metadata được giữ.
- Kịch bản logout, đổi người dùng và switch tenant.

Không chuyển sang cookie/cache custom chỉ vì muốn tránh HttpSession mà bỏ qua kiểm open redirect, replay và privacy.

## 11. SecurityContextRepository và RequestCache là hai kho khác nhau

Nhiều bug “đăng nhập xong không quay lại trang cũ” thực chất do **một trong hai kho** sai:

| Kho | Lưu cái gì? | Bị thiếu sẽ gây gì? |
| --- | --- | --- |
| **`RequestCache`** | SavedRequest/đích điều hướng trước login. | Login thành công nhưng về `/home`, không nhớ trang cũ. |
| **`SecurityContextRepository`** | `SecurityContext` và `Authentication` đã xác minh. | Login có thể redirect đúng URL cũ nhưng **request mới lại anonymous**, tạo vòng lặp login. |

Cụ thể:

```text
RequestCache đúng, SecurityContextRepository sai:
   /reports -> /login -> login OK -> /reports -> /login -> ...

RequestCache sai, SecurityContextRepository đúng:
   /reports -> /login -> login OK -> /home
   (User vẫn authenticated, chỉ mất đích cũ.)
```

Trong Spring Security 6, custom authentication muốn lưu context qua requests phải gọi `SecurityContextRepository.saveContext(...)` nếu built-in flow không làm giúp. `SavedRequestAwareAuthenticationSuccessHandler` **không** thay việc persist authentication; nó chỉ quyết định điều hướng.

### 11.1 Phân biệt với SessionAuthenticationStrategy

`SessionAuthenticationStrategy` chạy sau login thành công để chống session fixation, giới hạn phiên hoặc reset CSRF token theo cấu hình. `RequestCache` lưu URL gốc lúc anonymous. Khi login thành công:

1. Provider xác thực credential.
2. SessionAuthenticationStrategy (nếu áp dụng) xử lý phiên.
3. SecurityContext được set/save.
4. Success handler hỏi RequestCache chọn đích.
5. Response commit/redirect.
6. Browser quay lại, RequestCacheAwareFilter cố match saved request.

Không tạo một phiên đăng nhập chỉ bằng việc ghi saved request. Đừng tự gọi session strategy trên mọi request có `continue`.

### 11.2 Session fixation thay đổi ID nhưng giữ saved request thế nào?

Nếu pre-login `HttpSession` đã có SavedRequest, login success có thể gọi `ChangeSessionIdAuthenticationStrategy` để thay session ID. Với Servlet 3.1+ cơ chế này thay **ID của logical session** thay vì coi mọi attributes phải bị bỏ. Nhờ đó SavedRequest có thể vẫn còn cho success handler đọc sau khi login. Nếu dùng `newSession`/`migrateSession` với policy khác, hãy kiểm saved request có được chuyển hay bị xóa; không mặc định mọi chiến lược fixation giữ giống nhau.

### 11.3 Logout và đổi danh tính

Nếu một session bị logout, phải xác định SavedRequest nào được giữ/xóa, user hiện tại có đổi sang account khác không và redirect destination có còn hợp lệ không. URL được lưu có thể chứa thông tin tenant hoặc workspace của user cũ. Không dùng cache cũ như “bằng chứng” người dùng mới được phép truy cập tenant cũ; authorization phải kiểm lại, và có thể cần xóa saved request khi logout/switch account.

## 12. Lựa chọn UX: khi nào quay lại URL, khi nào về trang mặc định?

| Kịch bản | Quy tắc thường hợp lý |
| --- | --- |
| User bấm link GET tới báo cáo nội bộ | Lưu URL và redirect về đúng báo cáo sau login, nếu còn quyền. |
| User chủ động bấm Sign in từ landing page | Không có SavedRequest; về dashboard mặc định. |
| User vừa đăng ký/hoàn tất onboarding | Có thể ép về onboarding/đổi mật khẩu bắt buộc, bỏ saved request theo policy. |
| Role ADMIN yêu cầu step-up hoặc MFA | Chỉ redirect sau khi đủ mức authentication; không dùng SavedRequest để vượt bước. |
| User bị khóa hoặc password sai | Giữ failure flow; không coi saved request là xác thực thành công. |
| User không còn quyền vào tài nguyên saved | Trả 403 hoặc UX lỗi quyền; không bỏ authorization. |
| SPA chỉ có client-side route | Có thể dùng state/correlation token và client navigation được validate thay vì HttpSessionRequestCache. |
| API/JWT stateless | Trả 401/WWW-Authenticate hoặc JSON; không tạo session chỉ để nhớ URL. |
| Kiosk/public shared device | Hạn chế lưu metadata nhạy cảm, session TTL ngắn và cleanup khi logout. |
| Nhiều tab song song | Thiết kế per-tab return flow nếu cần; mặc định một SavedRequest có thể bị ghi đè. |

Không có một behavior duy nhất cho tất cả sản phẩm. Quan trọng là **flow được mô tả rõ, có kiểm thử và không biến URL client cung cấp thành redirect tùy ý**.

## 13. Ví dụ Spring Boot 3.x chạy được: anonymous GET → login → saved redirect

Dự án học tập dùng Java 17+, Spring Boot 3.3.13, Spring Security 6.x và `MockMvc`. Mục tiêu là tái hiện đúng SavedRequest với **form login built-in**, để tập trung vào RequestCache thay vì tự viết một bộ lọc đăng nhập mới.

- `/reports/summary`: GET cần authenticated; trả JSON gồm username và `period`.
- `/admin/panel`: GET cần `ROLE_ADMIN` để chứng minh saved request không cấp quyền tự động.
- `/home`: GET public, fallback khi login trực tiếp.
- Hai tài khoản demo: `alice` có `ROLE_USER`, `bob` có `ROLE_ADMIN`.
- Một bean `HttpSessionRequestCache` dùng chung trong `http.requestCache` và `SavedRequestAwareAuthenticationSuccessHandler`.
- Chỉ lưu GET dưới `/reports/**` hoặc `/admin/**` thông qua `RequestMatcher` an toàn, không lưu POST.
- CSRF của Spring Security **giữ bật**; MockMvc gửi token bằng helper `csrf()`.
- `SavedRequestAwareAuthenticationSuccessHandler` giữ saved request trong cache cho request theo redirect.

**Phạm vi:** Dữ liệu user trong `InMemoryUserDetailsManager`, session in-memory, không có database. Đây là ứng dụng Servlet/MockMvc, không minh họa WebFlux. Password trong code là **chỉ dùng localhost**; khi triển khai thật phải dùng secret/config policy và HTTPS.

### 13.1 Cấu trúc

```text
saved-request-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/SavedRequestApplication.java
    └── test/java/demo/SavedRequestIntegrationTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'saved-request-lab'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Version được ghim để tái lập ví dụ. Đây không phải lời khuyên chọn một nhánh framework đã hết hỗ trợ cho production mới; hãy chọn Spring Boot/Security đang được hỗ trợ theo tổ chức khi triển khai sản phẩm.

### 13.2 Ứng dụng Spring Security

File `src/main/java/demo/SavedRequestApplication.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.RequestCache;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.OrRequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SavedRequestApplication {

    public static void main(String[] args) {
        SpringApplication.run(SavedRequestApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("local-demo-password"))
                .roles("USER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("different-demo-password"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }

    @Bean
    RequestCache requestCache() {
        HttpSessionRequestCache cache = new HttpSessionRequestCache();

        // Spring Security 6: tra cache khi request theo redirect có marker.
        cache.setMatchingRequestParameterName("continue");

        // Chỉ giữ GET cho hai vùng có ý nghĩa với điều hướng.
        cache.setRequestMatcher(new OrRequestMatcher(
                new AntPathRequestMatcher("/reports/**", "GET"),
                new AntPathRequestMatcher("/admin/**", "GET")));

        return cache;
    }

    @Bean
    SavedRequestAwareAuthenticationSuccessHandler successHandler(
            RequestCache requestCache) {

        SavedRequestAwareAuthenticationSuccessHandler handler =
                new SavedRequestAwareAuthenticationSuccessHandler();
        handler.setRequestCache(requestCache);
        handler.setDefaultTargetUrl("/home");
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RequestCache requestCache,
            SavedRequestAwareAuthenticationSuccessHandler handler)
            throws Exception {

        return http
                .requestCache(cache -> cache.requestCache(requestCache))
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET, "/reports/**")
                            .authenticated()
                        .requestMatchers(HttpMethod.GET, "/admin/**")
                            .hasRole("ADMIN")
                        .requestMatchers(HttpMethod.GET, "/home")
                            .permitAll()
                        .anyRequest().denyAll())
                .formLogin(form -> form.successHandler(handler))
                .logout(Customizer.withDefaults())
                .build();
    }
}

@RestController
class ReportController {

    @GetMapping("/reports/summary")
    Map<String, String> summary(
            @RequestParam String period,
            Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "period", period);
    }

    @GetMapping("/admin/panel")
    String adminPanel(Authentication authentication) {
        return "admin for " + authentication.getName();
    }

    @GetMapping("/home")
    String home() {
        return "home";
    }
}
```

**Vì sao dùng `formLogin(...)` thay vì tự làm POST login?** Filter chuẩn của Spring Security xử lý password, session strategy, context persistence và success handler. Bài học đang tập trung RequestCache; tự viết filter dễ khiến lỗi ở bộ phận khác làm mờ cơ chế saved request.

**Tại sao hai matcher cho cache?** `ExceptionTranslationFilter` có thể muốn lưu GET vào vùng reports/admin. User Alice sau login trở về `/admin/panel` nếu đã lưu URL đó, nhưng vì thiếu `ROLE_ADMIN`, request sau vẫn phải 403. `RequestMatcher` tránh lưu các POST/URLs không phù hợp; có thể điều chỉnh theo thiết kế app.

**Vì sao không tự tạo `RequestCacheAwareFilter`?** `HttpSecurity.requestCache(...)` tích hợp đúng vào Spring Security chain, không cần đăng ký filter Servlet ngoài chain. Một filter tự đăng ký hai lần có thể gây replay/cleanup không nhất quán.

**Vì sao handler và chain dùng một instance?** Handler đọc saved request đúng kho mà `ExceptionTranslationFilter` đã lưu; `RequestCacheAwareFilter` trong chain kiểm request khớp trên cùng kho. Không cần truy cập session attribute key bằng tay trong ứng dụng.

### 13.3 MockMvc integration tests

File `src/test/java/demo/SavedRequestIntegrationTest.java`:

```java
package demo;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import org.springframework.security.web.savedrequest.SavedRequest;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SavedRequestIntegrationTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession sessionFrom(MvcResult result) {
        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    private MvcResult signIn(
            MockHttpSession session, String username, String password)
            throws Exception {

        return mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", username)
                        .param("password", password))
                .andExpect(status().is3xxRedirection())
                .andReturn();
    }

    @Test
    void originalReportIsSavedAndRestoredAfterLogin() throws Exception {
        // 1. Anonymous GET tới route được bảo vệ.
        MvcResult initial = mvc.perform(
                        get("/reports/summary").param("period", "2026"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String loginRedirect = initial.getResponse().getRedirectedUrl();
        assertNotNull(loginRedirect);
        assertTrue(loginRedirect.contains("/login"));

        MockHttpSession session = sessionFrom(initial);

        Object stored = session.getAttribute("SPRING_SECURITY_SAVED_REQUEST");
        assertTrue(stored instanceof SavedRequest);
        SavedRequest saved = (SavedRequest) stored;

        assertTrue(saved.getRedirectUrl()
                .contains("/reports/summary?period=2026"));

        // 2. Login với CHÍNH SESSION đã lưu request trước đó.
        MvcResult login = signIn(
                session, "alice", "local-demo-password");

        String location = login.getResponse().getRedirectedUrl();
        assertNotNull(location);

        // Handler không chỉ về /home vì đã có SavedRequest.
        assertTrue(location.contains("/reports/summary?period=2026"));
        assertTrue(location.contains("continue"));

        // 3. Sau success handler, SavedRequest vẫn còn cho lần GET.
        assertNotNull(session.getAttribute(
                "SPRING_SECURITY_SAVED_REQUEST"));

        // 4. Browser theo redirect với cookie session đó.
        mvc.perform(get(URI.create(location)).session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.period").value("2026"));

        // 5. RequestCacheAwareFilter đã tiêu thụ saved request.
        assertNull(session.getAttribute("SPRING_SECURITY_SAVED_REQUEST"));
    }

    @Test
    void directLoginWithoutSavedRequestUsesDefaultTarget() throws Exception {
        MockHttpSession session = new MockHttpSession();

        MvcResult login = signIn(
                session, "alice", "local-demo-password");

        String location = login.getResponse().getRedirectedUrl();
        assertNotNull(location);
        assertTrue(location.endsWith("/home"));

        mvc.perform(get("/reports/summary")
                        .session(session)
                        .param("period", "2025"))
                .andExpect(status().isOk());
    }

    @Test
    void savedAdminUrlDoesNotGrantUserAnAdminRole() throws Exception {
        MvcResult initial = mvc.perform(get("/admin/panel"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session = sessionFrom(initial);

        MvcResult login = signIn(
                session, "alice", "local-demo-password");

        String location = login.getResponse().getRedirectedUrl();
        assertNotNull(location);
        assertTrue(location.contains("/admin/panel"));

        // Saved URL không qua mặt authorization: Alice vẫn thiếu ADMIN.
        mvc.perform(get(URI.create(location)).session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void postLoginIsProtectedByCsrfAndNotSavedAsNavigation()
            throws Exception {

        mvc.perform(post("/login")
                        .param("username", "alice")
                        .param("password", "local-demo-password"))
                .andExpect(status().isForbidden());

        // RequestCache chỉ lưu GET thuộc reports/admin.
        MvcResult initial = mvc.perform(
                        get("/reports/summary").param("period", "2026"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session = sessionFrom(initial);
        MvcResult login = signIn(
                session, "alice", "local-demo-password");

        assertNotNull(login.getResponse().getRedirectedUrl());
        assertFalse(login.getResponse().getRedirectedUrl()
                .contains("/login?error"));
    }
}
```

**Giải thích kiểm thử:**

- Test 1 chứng minh **đúng cả bốn request liên tiếp**: anonymous GET → redirect login → POST login đúng với cùng session → GET location sau redirect. Nó còn kiểm `SPRING_SECURITY_SAVED_REQUEST` còn ngay sau success handler và bị xóa khi request tiếp theo thật sự match.
- Test 2 không có URL đã cache, nên handler dùng `defaultTargetUrl="/home"`. Authentication vẫn tồn tại trong session; SavedRequest không phải điều kiện để login được lưu.
- Test 3 chứng minh request cũ không cấp quyền. Alice bị redirect về admin URL nhưng access sau login vẫn HTTP 403.
- Test 4 chứng minh form POST login cần CSRF token khi dùng browser cookie flow. `RequestCache` có matcher chỉ lưu GET reports/admin, không dùng nó để replay một POST.

**Kết quả ở đây là kỳ vọng theo mã nguồn**, không phải tuyên bố đã chạy build/MockMvc trong môi trường của người đọc. Với các phiên bản/framework mới hơn, redirect strategy có thể chọn URL tương đối hay tuyệt đối; test chỉ kiểm path/query cần thiết. Nếu test thất bại, kiểm session object, header Location, query marker, repository và thứ tự SecurityFilterChain — không tắt CSRF để “làm xanh test”.

### 13.4 Các lệnh chạy

Khi đã có Gradle wrapper:

```bash
./gradlew test
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

Khi chưa có wrapper nhưng có Gradle tương thích:

```bash
gradle test
gradle bootRun
```

Vì code import Spring Boot/Web/Security, chỉ chạy `javac SavedRequestApplication.java` **không đủ** nếu không có classpath. `MockMvc` test là cách thuận tiện nhất để mô phỏng session và CSRF; demo không cung cấp một endpoint phát CSRF token riêng cho curl. Đừng hardcode token hoặc tắt CSRF toàn ứng dụng chỉ để thử bằng terminal.

### 13.5 Kiểm bằng browser/HTTP client thật

Sau khi chạy ứng dụng, mở một URL protected trong browser mới chưa có session:

```text
http://localhost:8080/reports/summary?period=2026
```

Browser được chuyển tới `/login`, dùng:

```text
Username: alice
Password: local-demo-password
```

Sau form login thành công, nếu flow hoạt động đúng, browser trở về báo cáo `period=2026`. Query marker `continue` có thể xuất hiện trong URL theo Spring Security 6. Khi truy cập trực tiếp `/login` trước, sau đó login, bạn sẽ được chuyển về `/home` do cấu hình fallback.

Kiểm trong DevTools Network ở môi trường test: status 302 của request ban đầu, Location /login, Set-Cookie/CSRF/session, Location của POST login và request GET sau redirect. Không chụp hoặc gửi full cookie/session ID, raw password hay Bearer token cho người khác.

## 14. Chương trình Java 17 thuần: lựa chọn đích sau login

Để học logic ưu tiên mà **không cần Spring dependency**, đoạn sau mô phỏng quyết định “luôn về home”, “có saved URL” và “fallback”. Nó **không** chứng minh session/cookie/redirect thật; chỉ minh họa thứ tự.

File `SavedTargetDemo.java`:

```java
public final class SavedTargetDemo {

    static String choose(
            String savedUrl,
            boolean alwaysDefault,
            String defaultTarget) {

        if (alwaysDefault) {
            return defaultTarget;
        }
        if (savedUrl != null && !savedUrl.isBlank()) {
            return savedUrl;
        }
        return defaultTarget;
    }

    public static void main(String[] args) {
        System.out.println("saved="
                + choose("/reports/summary?period=2026",
                        false, "/home"));
        System.out.println("direct="
                + choose(null, false, "/home"));
        System.out.println("forced="
                + choose("/reports/summary?period=2026",
                        true, "/home"));
    }
}
```

Biên dịch/chạy:

```bash
javac SavedTargetDemo.java
java SavedTargetDemo
```

Stdout chính xác:

```text
saved=/reports/summary?period=2026
direct=/home
forced=/home
```

Đây là bài tập chọn đích, **không được dùng `choose(...)` trực tiếp với URL do client nhập trong production**. Cần chuẩn hóa/allowlist target, kiểm quyền của endpoint và không cho redirect ngoài origin tùy ý. Những bước `RequestCache`/`SavedRequestAwareAuthenticationSuccessHandler` thật đã được giải thích ở trên.

## 15. Bảo mật: open redirect, URL injection và host/proxy

### 15.1 SavedRequest không biến URL đầu vào thành trusted URL

Request được gửi đến app chứa scheme, host, port, path và query. Một phần trong đó chịu ảnh hưởng của browser/client và các header proxy. Nếu một app tin bất kỳ `Host` hoặc `X-Forwarded-Host` nào, kẻ tấn công có thể tìm cách khiến saved redirect trỏ tới domain ngoài hoặc tạo URL khác origin (*host-header poisoning*).

Biện pháp phòng thủ:

1. Ở reverse proxy/load balancer, **allowlist Host hợp lệ**; không chấp nhận arbitrary forwarded headers trực tiếp từ internet.
2. Cấu hình forwarded-header handling chỉ tin proxy thực sự được phép; không bật blindly với giá trị client tự cấp.
3. Giới hạn saved-request route theo `RequestMatcher` (GET navigation paths) và dùng HTTPS.
4. Khi có custom success redirect logic, xác thực origin, context path và path normalization; tránh `//example.org`, CRLF, percent-encoding nhiều lần và path traversal.
5. Không cho dùng `targetUrlParameter`/`returnTo` unchecked từ client. Nếu cần, dùng server-side correlation state có TTL hoặc dữ liệu được ký và allowlist.
6. Tránh chuyển hướng ra IdP hoặc sang domain khác dựa chỉ trên URL cached nếu không có validation phù hợp.
7. Đưa vào security tests các host/path/query bất thường, trailing slash, UTF-8 encoding và proxy behavior.

**Không tin một string đơn thuần vì nó nằm trong `HttpSession`**; giá trị có thể bắt nguồn từ request do client điều khiển trước khi login.

### 15.2 Ngăn redirect loop

Một vòng lặp như:

```text
/reports -> /login -> login OK -> /reports -> /login -> ...
```

có thể do:

- SecurityContext không được lưu qua session.
- Browser không giữ/gửi `JSESSIONID` sau login (SameSite, Secure, Path, Domain, CORS).
- Session store của node B không biết dữ liệu node A.
- `SecurityFilterChain` hoặc `SecurityContextRepository` của login/target khác nhau.
- Saved target yêu cầu authentication mechanism hoặc MFA khác mà login vừa hoàn tất chưa đáp ứng.
- Entry point/redirect target bị cấu hình sai (login URL cũng bị bảo vệ).
- Một custom success handler ghi response sớm trước khi session/context được save.

Đừng khắc phục vòng lặp bằng cách `permitAll("/reports/**")`, vì như vậy sẽ bỏ bảo vệ dữ liệu. Hãy xác minh status/cookie/session/context và policy.

### 15.3 Không lưu secret trong URL

Query như:

```text
/reports?access_token=...
/reset?otp=...
/billing?cardNumber=...
```

không nên được “vô tư” cache và redirect lại. URL có thể rò qua browser history, proxy logs, analytics, Referer, session replication và debug output. Token reset/password có lifecycle riêng, không nên dùng RequestCache chung với protected GET navigation.

Một `RequestMatcher` chỉ cho phép path phù hợp không tự loại mọi query nhạy cảm. Hãy thiết kế routes không chứa secret trong query và có logic lọc/sanitize query nếu cần; an toàn nhất là **không dùng saved request** cho các đường nhạy cảm đó.

### 15.4 Không log nguyên DefaultSavedRequest

`DefaultSavedRequest` có thể chứa metadata về URL, parameters hoặc headers. Không log `savedRequest.toString()`, `HttpSession` dump hoặc `SecurityContext` serialize nguyên trong production. Logging nên giới hạn: request ID, account ID đã xác minh, route category, boolean saved/redirected/matched và error code; tránh full query/authorization/cookie/credentials.

## 16. Phân biệt 401, 302, 403 và lỗi CSRF

| Tình huống | Hành vi thông dụng | Ý nghĩa |
| --- | --- | --- |
| Browser anonymous GET protected | 302 tới `/login` + có thể cache GET | Bắt đầu form login. |
| API stateless không có Bearer token | 401/WWW-Authenticate hoặc JSON 401 | Client phải đưa credential, thường không redirect HTML. |
| Form login sai password | Redirect `/login?error` hoặc failure response phù hợp | Không phải success, không tiêu thụ SavedRequest cho đích thành công. |
| Đã login nhưng thiếu role | 403 | Authenticated nhưng không authorized; saved URL không bypass. |
| POST thiếu/CSRF sai | Thường 403 trước authentication logic | Không suy ra password sai hay RequestCache hỏng. |
| Session hết hạn trước request theo redirect | Có thể redirect login lại | Context đã mất, còn/không còn SavedRequest tùy lifecycle. |
| `NullRequestCache` | Không có saved URL; login fallback | Chủ ý không lưu navigation. |
| `alwaysUseDefaultTargetUrl=true` | Luôn về default target, xóa cache | Chính sách điều hướng ưu tiên default. |

**Lưu ý:** HTTP code phụ thuộc entry point/failure handler được cấu hình, không phải tất cả Spring Security apps luôn trả đúng một status. Ví dụ Boot demo này dùng form login mặc định và login page được tạo, nên anonymous GET thường có 302.

## 17. Những lỗi hiểu sai phổ biến

### 17.1 “SavedRequest là chức năng tự submit lại form POST”

Sai. Flow chính là redirect và một request mới tới URL cũ, thường GET; stream/body không được bảo đảm tái tạo. Với giao dịch thay đổi dữ liệu, cần form draft/confirmation và idempotency.

### 17.2 “Đã lưu request trong session thì đã authenticated”

Sai. `SPRING_SECURITY_SAVED_REQUEST` là navigation state; `SPRING_SECURITY_CONTEXT` mới là một nơi có thể giữ Authentication; thậm chí authentication còn phải được kiểm lại theo authorization.

### 17.3 “Success handler redirect rồi sẽ tự xóa cache ngay”

Không nhất thiết. Với nhánh có SavedRequest, handler thường **giữ saved request** cho `RequestCacheAwareFilter` tiêu thụ ở request khớp theo redirect.

### 17.4 “`getRequest` và `getMatchingRequest` như nhau”

Sai. `getRequest` đọc mà giữ cache. `getMatchingRequest` kiểm request hiện tại và consume khi khớp.

### 17.5 “continue là CSRF token hoặc mật khẩu thứ hai”

Sai. Nó là **marker truy vấn tối ưu saved-request lookup** trong Spring Security 6, không cấp authority hay chống CSRF.

### 17.6 “Mọi login đều trở lại trang trước”

Sai. Nếu không có SavedRequest hoặc dùng `alwaysUseDefaultTargetUrl`/`NullRequestCache`, login đi tới default target.

### 17.7 “Khôi phục URL cũ là cho phép truy cập”

Sai. Authorization vẫn áp dụng ở GET sau redirect. Nếu account không có quyền/tenant membership, phải bị từ chối.

### 17.8 “Chỉ đổi thành `NullRequestCache` sẽ vô hiệu hóa login session”

Sai. RequestCache lưu **navigation**, SecurityContextRepository lưu **authentication**. Đây là hai chức năng tách biệt.

### 17.9 “`HttpSessionRequestCache` lưu vô hạn các tab”

Sai. Dưới cấu hình mặc định, một session attribute lưu một SavedRequest tại một thời điểm, các request anonymous khác có thể ghi đè.

### 17.10 “Có thể dùng `Referer` hoặc `next` tự do làm target”

Sai. Client có thể kiểm soát/giả mạo thông tin này; phải validate origin/path, tránh open redirect.

### 17.11 “POST anonymous 403 nghĩa là RequestCache bug”

Không. `CsrfFilter` có thể từ chối POST trước khi nó tới cơ chế authentication. Đừng tắt CSRF để buộc POST được cache.

### 17.12 “URL có ?continue thì server tin user đã login”

Sai. Server vẫn nạp `SecurityContext`, kiểm Authentication và quyền trên endpoint; marker chỉ bảo RequestCache có nên tra session tìm SavedRequest hay không.

## 18. Bài tập thực hành có lời giải

**Câu 1.** User anonymous GET `/reports/summary?period=2026` và được redirect login. Dữ liệu nào lưu yêu cầu ban đầu?

**Đáp án:** `RequestCache` (thường `HttpSessionRequestCache`) lưu `SavedRequest`/`DefaultSavedRequest` trong HttpSession, thường dưới `SPRING_SECURITY_SAVED_REQUEST`. Nó khác `SecurityContext`.

**Câu 2.** Sau login thành công, vì sao success handler có thể redirect đúng URL gốc?

**Đáp án:** `SavedRequestAwareAuthenticationSuccessHandler` gọi `RequestCache.getRequest` để đọc SavedRequest và dùng `getRedirectUrl()`. Nếu không có SavedRequest thì dùng default target của base handler.

**Câu 3.** Vì sao SavedRequest còn trong session ngay sau POST login redirect?

**Đáp án:** Handler giữ lại để `RequestCacheAwareFilter` có thể match ở request theo redirect và tiêu thụ cache. Nếu default-target forced hoặc targetUrlParameter thắng, cache có thể bị xóa ngay.

**Câu 4.** `getMatchingRequest` có khác `getRequest` ở đâu?

**Đáp án:** Nó kiểm request hiện tại có khớp SavedRequest hay không, tạo wrapper và remove saved request khi match; `getRequest` đọc mà không consume.

**Câu 5.** Trong Spring Security 6, marker `continue` trong URL sau login có tác dụng gì?

**Đáp án:** Cho biết `HttpSessionRequestCache.getMatchingRequest` nên truy vấn HttpSession để tìm request đã lưu, giảm lookup thừa. Marker không xác thực hoặc cấp quyền.

**Câu 6.** User mở A rồi B ở hai tab trước login, cùng session. Vì sao sau login Tab A lại tới trang B?

**Đáp án:** Một HttpSessionRequestCache mặc định thường có một saved request attribute, request gần đây có thể ghi đè request trước. Muốn per-tab thì thiết kế state có correlation riêng.

**Câu 7.** Có nên tự replay `POST /transfer` ngay sau login?

**Đáp án:** Không. Redirect không bảo đảm raw body, CSRF và giao dịch an toàn. Cần draft/review/explicit confirmation với idempotency và authorization mới.

**Câu 8.** User login với ROLE_USER, saved URL trỏ `/admin`. Sau login có vào được không?

**Đáp án:** Không nếu endpoint yêu cầu ADMIN; request quay lại vẫn bị 403. SavedRequest không bypass authorization.

**Câu 9.** Login đúng nhưng luôn về `/home` dù trước đó mở trang report. Cần kiểm gì?

**Đáp án:** RequestCache có lưu request không; matcher có cho phép GET đó không; có cùng session không; handler có dùng cùng cache không; `alwaysUseDefaultTargetUrl`/`targetUrlParameter`/`NullRequestCache` có override không.

**Câu 10.** Login redirect đúng URL cũ nhưng request đó lại anonymous. Lỗi thường ở đâu?

**Đáp án:** Không phải request-cache URL; thường `SecurityContextRepository` chưa save context, cookie không tới browser hoặc session store/chain khác nhau. Kiểm context persistence và session cookie.

**Câu 11.** Vì sao cần validate Host và path dù SavedRequest được lưu server-side?

**Đáp án:** Vì metadata ban đầu vẫn có thể chịu ảnh hưởng từ URL/headers của client và proxy. Nếu tin nguồn không được kiểm, redirect có thể bị điều hướng ra domain độc hại.

**Câu 12.** `alwaysUseDefaultTargetUrl(true)` khác `setDefaultTargetUrl("/home")` như thế nào?

**Đáp án:** Luôn dùng default xóa saved request và bỏ đích cũ; chỉ set default cho biết fallback khi không có saved URL hoặc nhánh base handler cần.

**Câu 13.** Tắt RequestCache bằng NullRequestCache có làm `GET /reports` public không?

**Đáp án:** Không. Authorization vẫn có hiệu lực. User có thể vẫn cần login; chỉ mất khả năng tự nhớ trang ban đầu để redirect.

**Câu 14.** User vào URL chứa `access_token` query trước login. Có nên lưu vào session để redirect lại không?

**Đáp án:** Không nên. Token/secret trong URL có rủi ro lộ qua logs/history/session/referrer. Thiết kế credential flow riêng, hạn chế saved paths và loại bỏ dữ liệu nhạy cảm.

**Câu 15.** Vì sao test chỉ POST /login và kiểm status 302 chưa đủ?

**Đáp án:** Không chứng minh RequestCache được tạo từ anonymous GET, redirect chính xác, session được duy trì, request theo redirect có quyền và cache được consume. Cần integration test toàn chuỗi.

## 19. Ma trận kiểm thử production

| Tình huống | Điều phải xác minh |
| --- | --- |
| Anonymous GET protected | Redirect login, SavedRequest đúng route/query và tạo session theo policy. |
| Request GET nằm ngoài matcher | Không tạo SavedRequest, sau login fallback. |
| Anonymous GET có query sẵn | Redirect đúng query + marker `continue` theo phiên bản/cấu hình. |
| Đã login rồi truy cập protected | Không thêm saved request vô ích, controller trả 200 nếu authorized. |
| Login sai mật khẩu | Failure flow, không dùng saved URL như login thành công. |
| Login đúng sau anonymous GET | Success handler đọc saved URL, 302 về đúng đích. |
| Theo redirect với cookie đúng | Principal được khôi phục, authorization được áp dụng. |
| Theo redirect khớp | `RequestCacheAwareFilter` consume saved request. |
| Request không có `continue` ở Spring Security 6 | Không tra saved request như matching path theo config; không biến thành quyền. |
| Login trực tiếp | Fallback `/home`, không tự tạo một URL cũ. |
| Force default target | Xóa cache, chuyển dashboard dù có saved request. |
| TargetUrlParameter | Nếu có, chỉ nhận đích được validate; kiểm cache removal. |
| User thiếu role tại saved URL | 403; không bypass do URL đã cache. |
| Saved URL thuộc tenant khác | Truy cập sau login bị scope authorization chặn. |
| Hai tab anonymous khác nhau | Xác định hành vi ghi đè hay cơ chế state per tab. |
| POST thiếu CSRF | 403; không tự replay POST qua cache. |
| POST có body nhạy cảm | Không serialize body vào navigation state, không tự thực thi mutation. |
| Logout/switch user | Cache được cleanup theo policy, không leak URL account cũ. |
| Session expired | SavedRequest không còn hoặc xử lý theo policy; không dùng stale session. |
| Nhiều node, session phân tán | SavedRequest và SecurityContext đều được đọc nhất quán. |
| Proxy/Host bất thường | Không open redirect tới domain client-supplied. |
| Cookie Secure/SameSite/path | Browser thật giữ và gửi session ID phù hợp. |
| NullRequestCache | Không save/restore navigation; authentication vẫn vận hành độc lập. |
| SecurityContextRepository sai | Test phát hiện redirect loop khi session không persist. |
| Security 5 → 6 migration | Marker `continue`, success handler, custom cache behavior đúng. |
| Logs/observability | Không in URL query chứa secrets, cookie, tokens, request headers thô. |

## 20. Checklist thiết kế và vận hành

1. **Xác định phạm vi:** có cần quay lại URL trước login hay chỉ về dashboard?
2. **Chỉ cache điều hướng hợp lý:** ưu tiên GET/HEAD safe, request matchers cho vùng được phép, tránh POST giao dịch/URL chứa secrets.
3. **Dùng đúng RequestCache:** biết rõ đang dùng HttpSessionRequestCache, NullRequestCache hay custom; không trộn phiên bản/chains.
4. **Cùng cache với success handler:** ExceptionTranslationFilter save, handler read, RequestCacheAwareFilter match trên cùng namespace/storage.
5. **Hiểu `continue` trong Security 6:** marker tối ưu getMatchingRequest, không phải auth/CSRF token.
6. **Form login chuẩn:** ưu tiên `formLogin` nếu không có yêu cầu đặc biệt; custom filter/controller phải tự xử lý context/save và session strategy đúng.
7. **Tách kho context:** SecurityContextRepository cần persist authentication; RequestCache chỉ persist đích navigation.
8. **Redirect có kiểm soát:** allowlist host/path/relative URLs, forwarded headers từ proxy tin cậy, tránh open redirect/CRLF.
9. **Không replay thao tác nguy hiểm:** POST/PUT/PATCH/DELETE và upload cần flow xác nhận/idempotency riêng.
10. **Nhiều tab:** một SavedRequest/session có thể bị overwrite; cần thiết kế per-tab state nếu yêu cầu.
11. **Session fixation/logout:** kiểm ID rotation và cleanup; saved request không phải authorization.
12. **CSRF/cookie:** browser cookie-session cần CSRF protection; redirect/cookies đúng SameSite/Secure/HttpOnly.
13. **Tính nhất quán phân tán:** session store/TTL trên nhiều node, không lộ SavedRequest qua logs.
14. **User không đủ quyền:** saved URL vẫn chịu authorization và tenant scope.
15. **Kiểm thử end-to-end:** anonymous GET → login → redirect → GET đích, test data/HTTP/cached request removal.
16. **Vận hành:** metric redirect loop, cache hit/miss, stale saved request, abnormal external target; log sanitized metadata.
17. **Sự cố:** khi login xong quay về home sai, kiểm matcher/cache/handler; khi quay đúng nhưng 401, kiểm SecurityContextRepository/session.
18. **Nâng cấp:** đọc Javadoc của phiên bản Security đang chạy, nhất là default matching parameter, redirect strategy và session persistence.

## 21. Tài liệu chính thức và đọc tiếp

- [Spring Security 6.5 — Servlet Architecture: Saving Requests Between Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `ExceptionTranslationFilter`, `RequestCache`, `RequestCacheAwareFilter` và cache mặc định.
- [Spring Security 6.5 — Session Management Migration: Optimize Querying of RequestCache](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): thay đổi `continue` từ Spring Security 5 sang 6 và ví dụ cấu hình.
- [Spring Security 6.5 — SavedRequestAwareAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html): các nhánh `alwaysUseDefaultTargetUrl`, `targetUrlParameter`, SavedRequest, fallback.
- [Spring Security 6.5 — RequestCache API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/savedrequest/RequestCache.html): `saveRequest`, `getRequest`, `getMatchingRequest` và `removeRequest`.
- [Spring Security 6.5 — HttpSessionRequestCache API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/savedrequest/HttpSessionRequestCache.html): session attribute, `matchingRequestParameterName`, matcher, session creation.
- [Spring Security 6.5 — SavedRequest API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/savedrequest/SavedRequest.html): dữ liệu request được cache và `getRedirectUrl`.
- [Spring Security 6.5 — RequestCacheAwareFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/savedrequest/RequestCacheAwareFilter.html): khôi phục wrapper sau redirect khi request khớp.
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): flow form login và AuthenticationSuccessHandler.
- [Spring Security 6.5 — Authentication Persistence](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): `SecurityContextRepository` và session state khác với saved-request navigation.
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): bảo vệ unsafe methods và tác động tới form login.
- [Spring Security 6.5 — MockMvc Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc.html): integration tests cho Spring Security.
- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): kiểm redirect target, tránh open redirect.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, session ID, lifecycle và privacy.

**Kết luận:** `RequestCache` ghi nhớ **yêu cầu điều hướng** bị chặn do chưa xác thực. `ExceptionTranslationFilter` lưu nó; `SavedRequestAwareAuthenticationSuccessHandler` chọn URL gốc sau login; `RequestCacheAwareFilter` có thể match và tiêu thụ nó khi browser quay lại. Với Spring Security 6, `continue` chủ yếu tối ưu việc đọc cache. Những thành phần này không xác thực user, không thay `SecurityContextRepository`, không tự cấp quyền và **không tự replay các thao tác POST có body**. Thiết kế đúng là **quay lại GET an toàn, kiểm authorization lại, validate redirect target và bảo vệ session/CSRF**.