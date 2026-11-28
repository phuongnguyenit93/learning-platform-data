# Cookie name, Domain, Path và điều kiện trình duyệt gửi cùng định danh

Spring Session thường truyền session ID giữa trình duyệt và ứng dụng bằng một cookie. Khi muốn nhiều ứng dụng cùng nhận một session ID, việc đặt cùng tên cookie là chưa đủ. Trình duyệt chỉ gửi cookie khi request thỏa các quy tắc về host/domain, path, scheme, SameSite, thời hạn và chính sách cookie của trình duyệt. Sau khi cookie được gửi, mỗi ứng dụng còn phải truy cập được cùng session repository và hiểu cùng định dạng dữ liệu.

Cookie scope quyết định **request nào được trình duyệt đính kèm cookie**. Spring Session repository quyết định **session ID đó ánh xạ tới dữ liệu phiên nào**. Hai lớp này phải được cấu hình tương thích nếu muốn chia sẻ phiên giữa ứng dụng, nhưng không nên mở rộng cookie sang nhiều ứng dụng nếu chúng không cùng một ranh giới tin cậy.

## 1. Cookie session mang gì?

Cookie session thường chứa một cặp tên và giá trị, ví dụ:

```http
Set-Cookie: SESSION=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Trong ví dụ:

- `SESSION` là cookie name.
- `opaque-session-id` là giá trị định danh phiên do Spring Session phát hành.
- `Path=/` cho phép cookie được gửi tới các path phù hợp trên host nhận cookie.
- `Secure` giới hạn cookie vào request HTTPS.
- `HttpOnly` ngăn JavaScript đọc cookie qua API như `document.cookie`.
- `SameSite=Lax` hạn chế gửi cookie trong một số ngữ cảnh cross-site.

Khi request phù hợp, trình duyệt gửi header:

```http
Cookie: SESSION=opaque-session-id
```

Request `Cookie` thường chỉ chứa tên và giá trị. Các thuộc tính `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite` và thời hạn là metadata trình duyệt dùng để quyết định có gửi cookie hay không; chúng không được gửi lại như các tham số trong header `Cookie`.

Session ID là bearer credential. Người có ID hợp lệ có thể được ứng dụng nhận diện là chủ phiên. Vì vậy, không ghi giá trị cookie vào log, URL, analytics, ảnh chụp màn hình hoặc ticket hỗ trợ.

## 2. Cookie name và nhận diện cookie

Cookie name là tên mà resolver dùng để tìm session ID trong request. Spring Session mặc định thường dùng tên `SESSION`, nhưng có thể tùy chỉnh để phù hợp với ứng dụng hoặc tránh xung đột.

Trình duyệt có thể lưu nhiều cookie trùng tên nếu scope của chúng khác nhau, ví dụ:

| Name | Domain scope | Path | Ý nghĩa |
|---|---|---|---|
| `SESSION` | host-only `portal.example.com` | `/` | Cookie chỉ gửi tới host portal |
| `SESSION` | `example.com` | `/api` | Cookie domain-wide nhưng chỉ gửi tới path `/api` và path con phù hợp |
| `SESSION` | `example.com` | `/` | Cookie domain-wide cho các path phù hợp trên domain và subdomain |

Khi nhiều cookie cùng tên cùng khớp một request, trình duyệt có thể gửi nhiều cặp cùng tên trong header `Cookie`. Server framework hoặc resolver có thể chọn giá trị theo quy tắc parsing của nó; ứng dụng không nên dựa vào thứ tự để phân biệt session.

Để tránh xung đột:

- Dùng tên cookie riêng cho các ứng dụng độc lập, ví dụ `PORTAL_SESSION` và `ADMIN_SESSION`.
- Nếu thật sự chia sẻ một session, thống nhất cookie name, domain/path scope và resolver trên mọi ứng dụng tham gia.
- Xóa cookie cũ với đúng name, Path và Domain khi thay đổi cấu hình; cookie xóa sai scope có thể vẫn tồn tại.
- Không dùng cùng tên cookie cho nhiều phiên độc lập trên cùng host và path.

Đổi cookie name chỉ thay đổi cách trình duyệt gửi ID. Nó không di chuyển dữ liệu session và không làm hai repository khác nhau trở thành một kho dùng chung.

## 3. Host-only cookie và thuộc tính Domain

Nếu `Set-Cookie` không có thuộc tính `Domain`, trình duyệt tạo host-only cookie. Cookie chỉ được gửi tới đúng host đã phát hành nó, không tự động gửi tới subdomain.

Ví dụ response từ `portal.example.com`:

```http
Set-Cookie: SESSION=abc; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie trên là host-only cho `portal.example.com`. Request tới `api.example.com` không nhận cookie này.

Nếu response đặt:

```http
Set-Cookie: SESSION=abc; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
```

cookie có thể được gửi tới `example.com` và các subdomain phù hợp như `portal.example.com`, `api.example.com`. Trình duyệt kiểm tra domain attribute phải domain-match host đã phát hành cookie. Một host không thể đặt cookie cho domain không phải domain cha hợp lệ của nó.

Các quy tắc quan trọng:

- Không đặt `Domain` tạo host-only cookie; đây thường là phạm vi hẹp và an toàn hơn.
- `Domain=example.com` mở rộng cookie tới các subdomain phù hợp của `example.com`.
- `Domain=portal.example.com` cũng có thể được gửi tới các subdomain của `portal.example.com`, nhưng không phải sibling `api.example.com`.
- Dấu chấm đầu như `.example.com` không tạo semantics khác trong trình duyệt hiện đại; dùng `example.com`.
- Trình duyệt từ chối Domain là public suffix như `.com` hoặc public suffix tương ứng; không thể đặt cookie cho toàn bộ các website thuộc suffix đó.
- Không thể chia sẻ cookie giữa hai registrable domain độc lập như `example.com` và `example.net` bằng cách đặt `Domain`.

Domain scope là một quyết định bảo mật. Khi đặt `Domain=example.com`, mọi subdomain có thể nhận cookie đó nếu request thỏa các điều kiện khác. Một subdomain bị chiếm quyền hoặc có ứng dụng kém tin cậy có thể trở thành rủi ro đối với session dùng chung.

## 4. Path quyết định request path nào nhận cookie

`Path` giới hạn các đường dẫn request mà trình duyệt gửi cookie tới. Ví dụ:

```http
Set-Cookie: SESSION=abc; Domain=example.com; Path=/portal; Secure; HttpOnly
```

Cookie được gửi tới `/portal` và các path con phù hợp như `/portal/account`. Nó không được gửi tới `/api` hoặc `/admin`.

Một số ví dụ path matching:

| Cookie Path | Request Path | Có khớp? |
|---|---|---|
| `/` | `/` | Có |
| `/` | `/orders/42` | Có |
| `/portal` | `/portal` | Có |
| `/portal` | `/portal/account` | Có |
| `/portal` | `/portal-admin` | Không theo ranh giới path segment |
| `/api` | `/portal/api` | Không |

Nếu không khai báo `Path`, trình duyệt tính default path dựa trên URL request đã phát cookie. Điều này có thể gây bất ngờ khi ứng dụng được mount dưới context path hoặc proxy prefix. Với Spring Session, nên cấu hình path rõ ràng theo phạm vi ứng dụng cần dùng.

`Path` không phải ranh giới bảo mật đáng tin cậy giữa các ứng dụng cùng host. Nó điều khiển việc gửi cookie của trình duyệt, nhưng không ngăn code chạy trên cùng origin truy cập tài nguyên khác hoặc ngăn một ứng dụng có khả năng phát cookie cùng scope. Không dùng Path thay cho host isolation, phân quyền hoặc CSRF protection.

## 5. Domain và Path không phân biệt port

Cookie không được cô lập theo TCP port. Hai ứng dụng chạy tại `https://example.com:8443` và `https://example.com:9443` vẫn dùng cùng phạm vi cookie theo host/path/scheme và các thuộc tính liên quan. Nếu cookie scope khớp, trình duyệt có thể gửi cùng cookie tới cả hai port.

Điều này quan trọng trong môi trường phát triển và kiến trúc nhiều service. Không giả định chạy ứng dụng trên port khác sẽ tách session cookie. Nếu cần tách biệt, dùng hostname riêng hoặc cookie name/path được thiết kế rõ ràng; ưu tiên hostname riêng khi cần ranh giới bảo mật.

## 6. Các điều kiện khác ảnh hưởng việc trình duyệt gửi cookie

Domain và Path chỉ là hai điều kiện. Trình duyệt còn xét:

| Điều kiện | Tác động |
|---|---|
| `Secure` | Chỉ gửi cookie qua HTTPS, ngoại trừ một số hành vi đặc biệt của môi trường local mà không nên dựa vào production |
| `SameSite` | Giới hạn cookie trong ngữ cảnh same-site/cross-site |
| `Expires` / `Max-Age` | Cookie hết hạn thì không được gửi; session cookie được giữ theo phiên trình duyệt |
| Cookie bị xóa hoặc bị chặn | Không gửi dù domain/path khớp |
| Third-party cookie policy | Trình duyệt có thể chặn hoặc partition cookie trong một số ngữ cảnh bên thứ ba |
| Fetch/XHR credentials mode | Request JavaScript cross-origin cần cho phép gửi credentials ở phía client và server |
| Partitioning/browser privacy controls | Có thể cô lập cookie theo top-level site hoặc chính sách quyền riêng tư của trình duyệt |

Vì chính sách trình duyệt thay đổi theo phiên bản và cấu hình người dùng, hãy kiểm thử trên các trình duyệt được hỗ trợ. Không xem việc cookie xuất hiện trong tab Application/Storage là bằng chứng rằng nó sẽ được gửi trong mọi request.

## 7. SameSite và khái niệm same-site/cross-site

`SameSite` kiểm soát việc cookie được gửi trong request theo ngữ cảnh site. Khái niệm site khác origin:

- **Origin** gồm scheme, host và port.
- **Site** trong ngữ cảnh cookie hiện đại thường dựa trên scheme và registrable domain (eTLD+1).

Ví dụ `https://portal.example.com` và `https://api.example.com` là hai origin khác nhau nhưng thường cùng site vì có cùng scheme và registrable domain `example.com`. Vì vậy, `SameSite=Lax` không nhất thiết ngăn cookie gửi giữa hai subdomain này; Domain, Path, Secure và các điều kiện khác vẫn phải khớp.

Các giá trị thường dùng:

| SameSite | Hành vi khái quát |
|---|---|
| `Strict` | Chỉ gửi trong ngữ cảnh same-site; hạn chế mạnh điều hướng/request từ site khác |
| `Lax` | Gửi trong ngữ cảnh same-site và một số top-level navigation cross-site an toàn theo quy tắc trình duyệt |
| `None` | Cho phép cookie trong ngữ cảnh cross-site; trình duyệt hiện đại yêu cầu `Secure` |

Nếu hai ứng dụng nằm ở hai registrable domain khác nhau, ví dụ `portal.example.com` và `identity.example.net`, cookie của domain này không thể được đặt để trình duyệt gửi tới domain kia. `SameSite=None` không vượt qua giới hạn Domain và cũng không bảo đảm cookie bên thứ ba sẽ được trình duyệt chấp nhận.

## 8. Cross-origin fetch, credentials và CORS

Hai ứng dụng ở hai subdomain có thể cùng site nhưng khác origin. Khi JavaScript từ `https://portal.example.com` gọi `https://api.example.com`, request là cross-origin. Để trình duyệt gửi cookie trong `fetch`, client thường cần `credentials: "include"`:

```javascript
fetch("https://api.example.com/profile", {
  method: "GET",
  credentials: "include"
});
```

Server API phải cấu hình CORS cho origin cụ thể và cho phép credentials:

```http
Access-Control-Allow-Origin: https://portal.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Khi dùng credentials, `Access-Control-Allow-Origin: *` không hợp lệ. CORS quyết định JavaScript có được phép đọc response hay không và có thể ảnh hưởng preflight; nó không cấp quyền vượt qua Domain, Path, Secure, SameSite hoặc third-party cookie policy. Ngược lại, SameSite cho phép cookie không có nghĩa CORS sẽ cho JavaScript đọc response.

Với XHR, thiết lập `withCredentials = true` khi cần gửi cookie cross-origin. Hãy kiểm thử cả request thật và preflight nếu method/header kích hoạt preflight.

## 9. Cấu hình cookie Spring Session bằng DefaultCookieSerializer

Với ứng dụng Servlet dùng Spring Session, `DefaultCookieSerializer` cho phép tùy chỉnh cookie name, domain, path, Secure, HttpOnly và SameSite.

Ví dụ một ứng dụng portal và API ở các subdomain đáng tin cậy cần dùng chung cookie:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
class SharedSessionCookieConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("SHARED_SESSION");
        serializer.setDomainName("example.com");
        serializer.setCookiePath("/");
        serializer.setUseSecureCookie(true);
        serializer.setUseHttpOnlyCookie(true);
        serializer.setSameSite("Lax");
        return serializer;
    }
}
```

Ví dụ mở rộng cookie tới `example.com` và các subdomain phù hợp. Chỉ dùng Domain-wide cookie khi mọi subdomain nhận cookie đều nằm trong cùng ranh giới tin cậy. Nếu không cần chia sẻ, bỏ `setDomainName` để dùng host-only cookie.

Ví dụ host-only cookie có thể dùng:

```java
@Bean
CookieSerializer hostOnlySessionCookieSerializer() {
    DefaultCookieSerializer serializer = new DefaultCookieSerializer();
    serializer.setCookieName("__Host-PORTAL_SESSION");
    serializer.setCookiePath("/");
    serializer.setUseSecureCookie(true);
    serializer.setUseHttpOnlyCookie(true);
    serializer.setSameSite("Lax");
    // Không gọi setDomainName: cookie chỉ thuộc host phát hành.
    return serializer;
}
```

Tiền tố `__Host-` yêu cầu `Secure`, `Path=/` và không có `Domain` theo quy tắc trình duyệt hỗ trợ prefix này. Vì vậy, cookie `__Host-PORTAL_SESSION` không thể được chia sẻ giữa `portal.example.com` và `api.example.com`. Đây là một lựa chọn tốt khi muốn giới hạn cookie vào một host.

`DefaultCookieSerializer` và cách Spring Boot phát hiện bean serializer cần được xác nhận theo phiên bản Spring Session. Trong một application context chỉ nên có một serializer áp dụng cho cookie session của repository tương ứng. Với ứng dụng WebFlux, cookie resolver và cấu hình WebSession có API riêng; không bê nguyên bean Servlet `CookieSerializer` vào reactive stack.

## 10. DomainNamePattern và nhiều môi trường subdomain

`DefaultCookieSerializer` có thể hỗ trợ `cookieDomainNamePattern`/domain pattern theo phiên bản để suy ra Domain từ host request. Cách này có thể tiện khi cùng ứng dụng chạy trên nhiều subdomain, nhưng regex quá rộng có thể tạo cookie domain ngoài dự kiến.

Nếu dùng domain pattern:

- Chỉ khớp các host thuộc domain tổ chức đã xác định.
- Không phản chiếu nguyên host tùy ý từ request vào thuộc tính Domain.
- Kiểm thử host không hợp lệ, host giả mạo và môi trường staging/local.
- Không cho phép một tenant hoặc subdomain không tin cậy mở rộng cookie tới parent domain.
- Ưu tiên cấu hình Domain cố định nếu chỉ có một domain production.

Không dùng pattern kiểu `.*` hoặc quy tắc tự động chấp nhận mọi suffix. Forwarded host cũng phải được chuẩn hóa từ proxy đáng tin trước khi dùng làm đầu vào cho logic domain.

## 11. Chia sẻ cookie không đồng nghĩa chia sẻ session data

Giả sử `portal.example.com` và `api.example.com` cùng nhận cookie `SHARED_SESSION`. Hai ứng dụng chỉ có thể khôi phục cùng session nếu chúng cùng truy cập một kho session và dùng cấu hình tương thích.

Các điều kiện cần có:

1. **Cùng session ID:** cookie name và resolver phải đọc cùng giá trị ID.
2. **Cùng repository:** cả hai ứng dụng phải truy cập cùng Redis deployment/namespace hoặc cùng JDBC schema/table phù hợp.
3. **Cùng định dạng dữ liệu:** serializer, converter, class và version phải tương thích.
4. **Cùng semantics timeout:** idle timeout và cách cập nhật last-access phải nhất quán.
5. **Cùng cơ chế bảo mật:** mỗi ứng dụng phải xác minh principal, audience, tenant và quyền phù hợp với tài nguyên của nó.

Nếu portal lưu session trong Redis namespace `portal:sessions` còn API tìm trong `api:sessions`, cookie giống nhau vẫn dẫn tới hai lookup khác nhau. Nếu một app dùng Java serialization và app kia dùng JSON, app thứ hai có thể không đọc được attributes. Nếu serializer khác nhau nhưng cả hai chỉ cần một subset attribute tương thích, vẫn phải kiểm thử rõ ràng.

Chia sẻ session cũng không tự tạo Single Sign-On hoàn chỉnh. SSO cần một thiết kế xác thực chung, quy trình login/logout, session fixation protection, token/session revocation và cách các ứng dụng tin cậy identity. Cookie chỉ vận chuyển định danh; repository cung cấp dữ liệu; mỗi ứng dụng vẫn chịu trách nhiệm phân quyền.

## 12. Rủi ro khi mở rộng Domain

Domain-wide cookie làm tăng số host có thể nhận session ID. Nếu một subdomain có ứng dụng do nhóm khác vận hành, hệ thống legacy, nội dung người dùng tải lên hoặc khả năng bị takeover, cookie dùng chung có thể bị lộ hoặc bị lợi dụng.

Trước khi đặt `Domain=example.com`, đánh giá:

- Tất cả subdomain hiện có và subdomain có thể được tạo trong tương lai.
- Quyền tạo DNS record và quản lý hosting của từng nhóm.
- Subdomain có phục vụ nội dung không tin cậy hoặc cho phép người dùng upload file hay không.
- Có ứng dụng cũ dùng cùng cookie name/path nhưng không cùng session repository không.
- Có cần chia sẻ toàn bộ session hay chỉ cần trao đổi danh tính qua token có audience hẹp.

Nếu các ứng dụng không cùng mức tin cậy, ưu tiên host-only cookie và dùng luồng token exchange/OIDC hoặc cơ chế SSO được thiết kế riêng. Không mở rộng Domain chỉ để tránh triển khai đăng nhập chung.

## 13. Cookie collision và quá trình chuyển cấu hình

Khi đổi cookie name, Domain hoặc Path, trình duyệt có thể giữ cookie cũ. Cookie được xác định bởi name, domain/host-only scope và path; gửi lệnh xóa phải dùng đúng scope cũ.

Ví dụ trước đây ứng dụng phát:

```http
Set-Cookie: SESSION=old; Domain=example.com; Path=/portal; Max-Age=0; Secure; HttpOnly
```

Nếu cookie cũ được tạo với `Domain=example.com; Path=/portal`, gửi lệnh xóa với `Path=/` có thể không xóa đúng cookie đó. Cần biết chính xác các scope từng được phát hành.

Khi đổi cấu hình:

1. Ghi nhận cookie name/domain/path cũ và mới.
2. Phát cookie hết hạn cho từng scope cũ cần dọn.
3. Chọn thời điểm chuyển resolver để tránh một node đọc tên cookie cũ còn node khác chỉ đọc tên mới ngoài dự kiến.
4. Nếu cần chuyển session, thiết kế giai đoạn đọc cả cookie cũ và mới hoặc buộc đăng nhập lại có kế hoạch.
5. Kiểm thử browser cookie jar để xác nhận cookie trùng tên cũ không còn được gửi.

Không thể xóa cookie của domain khác hoặc scope mà ứng dụng không có quyền phát cookie. Nếu cookie cũ do một host khác tạo, host đó có thể cần phát response xóa cookie tương ứng.

## 14. Kiểm thử điều kiện browser gửi cookie

Kiểm thử bằng `MockMvc` có thể xác minh header `Set-Cookie`, nhưng không mô phỏng đầy đủ cookie jar và chính sách của trình duyệt. Với chia sẻ giữa ứng dụng, cần kiểm thử bằng browser automation hoặc trình duyệt thật.

Các kịch bản nên có:

1. **Host-only:** login tại `portal.example.com`; xác nhận cookie không được gửi tới `api.example.com`.
2. **Parent Domain:** đặt `Domain=example.com`; xác nhận cookie được gửi tới các subdomain được phép và không gửi tới domain ngoài.
3. **Path:** xác nhận cookie có `Path=/portal` được gửi tới `/portal/account` nhưng không tới `/api`.
4. **Path boundary:** xác nhận `/portal` không vô tình khớp `/portal-admin`.
5. **Port:** chạy hai ứng dụng cùng hostname trên port khác nhau và xác nhận cookie không được cô lập theo port.
6. **Secure:** xác nhận cookie Secure không được gửi qua HTTP thông thường.
7. **SameSite:** kiểm thử top-level navigation, cross-site POST, iframe và callback OAuth2 theo luồng thực tế.
8. **Fetch credentials:** xác nhận `credentials: include` cùng CORS credentials policy cho cross-origin API.
9. **Third-party restrictions:** kiểm tra trình duyệt mục tiêu khi ứng dụng chạy trong iframe hoặc ngữ cảnh third-party.
10. **Duplicate name:** tạo cookie cùng tên với scope khác nhau và xác nhận server không chọn nhầm session.
11. **Logout/rotation:** xác nhận cookie cũ bị xóa đúng scope và session ID mới được phát hành khi cần.
12. **Repository sharing:** login ở app A, gửi cookie tới app B và xác nhận B đọc được cùng session attributes được phép.

Không dùng session thật của người dùng trong test. Dùng domain test, account giả và cookie jar được tạo riêng cho mỗi kịch bản.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Subdomain thứ hai không nhận cookie | Cookie là host-only hoặc Domain/Path không khớp | Kiểm tra `Set-Cookie` và cookie jar trên browser |
| Cookie gửi tới quá nhiều subdomain | Domain được đặt ở parent domain rộng | Thu hẹp Domain hoặc chuyển về host-only |
| Cookie không gửi tới API path | Path cookie không khớp request path | Chọn Path phù hợp và kiểm tra path matching |
| Hai ứng dụng đọc nhầm session | Trùng name nhưng có nhiều cookie cùng tên với scope khác nhau | Dùng tên riêng hoặc thống nhất một scope duy nhất |
| Cookie giống nhau nhưng app B không thấy session | Repository/namespace/schema/serializer khác nhau | So sánh backend, namespace và serializer |
| Cross-origin fetch không có cookie | Thiếu `credentials: include`, CORS credentials sai hoặc SameSite/policy chặn | Kiểm tra từng lớp riêng biệt |
| Cookie biến mất sau chuyển cấu hình | Cookie cũ bị xóa với Path/Domain sai hoặc cookie mới bị browser từ chối | Xem response `Set-Cookie` và cookie jar |
| Cookie `__Host-` không được chia sẻ | Prefix yêu cầu không có Domain và Path=/ | Dùng host-only theo đúng mục tiêu hoặc chọn tên khác nếu thật sự cần Domain-wide |
| Cookie hoạt động ở HTTPS nhưng không ở local HTTP | Có thuộc tính Secure | Dùng HTTPS local hoặc profile development riêng |
| App khác đọc được session nhưng quyền không phù hợp | Chia sẻ session data bị nhầm là chia sẻ toàn bộ authorization policy | Xác minh audience, tenant, authorities và quyền tại từng app |

## 16. Nguyên tắc triển khai

- Cookie được nhận diện theo name và scope; nhiều cookie cùng tên có thể cùng tồn tại nếu Domain/Path khác nhau.
- Không đặt `Domain` tạo host-only cookie; chỉ mở rộng tới parent domain khi mọi subdomain nhận cookie cùng mức tin cậy.
- `Path` điều khiển request path gửi cookie nhưng không phải ranh giới bảo mật giữa ứng dụng.
- Cookie không được cô lập theo port; dùng hostname riêng nếu cần tách biệt.
- `Secure`, `HttpOnly`, `SameSite`, thời hạn và chính sách third-party đều ảnh hưởng việc browser gửi cookie.
- Same-site khác same-origin; hai subdomain có thể khác origin nhưng cùng site.
- CORS không vượt qua Domain, Path hoặc SameSite; cross-origin fetch cần credentials và CORS policy tương ứng.
- Cấu hình `DefaultCookieSerializer` nhất quán; không dùng Domain pattern quá rộng hoặc phản chiếu host không tin cậy.
- Chia sẻ cookie chỉ chia sẻ session ID; các ứng dụng còn phải dùng chung repository, namespace và serializer tương thích.
- Chia sẻ session không tự tạo SSO hoặc phân quyền chung; từng ứng dụng phải xác minh quyền truy cập của mình.
- Kiểm thử bằng browser cookie jar qua nhiều host/path, HTTPS, CORS, logout và repository thực tế.
