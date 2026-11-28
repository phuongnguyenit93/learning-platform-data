# Subdomain, site, origin và giới hạn của cơ chế cookie

Spring Session thường nhận diện phiên bằng một session ID được gửi qua cookie. Khi nhiều ứng dụng chạy trên các subdomain, đội phát triển có thể muốn dùng chung cookie để người dùng đã đăng nhập ở một ứng dụng tiếp tục được nhận diện ở ứng dụng khác. Khả năng này phụ thuộc vào cách trình duyệt xác định host, domain, site và origin; các khái niệm này có liên quan nhưng không giống nhau.

Cookie có thể được mở rộng tới các subdomain thuộc cùng một domain cha bằng thuộc tính `Domain`, nhưng không thể đặt cookie cho một registrable domain độc lập khác. `SameSite=None` cũng không vượt qua giới hạn domain, chính sách chặn third-party cookie hoặc cơ chế partitioning của trình duyệt. Ngay cả khi trình duyệt gửi cùng cookie tới hai ứng dụng, hai ứng dụng chỉ đọc được cùng phiên nếu chúng dùng chung session repository và serializer tương thích.

## 1. Phân biệt host, domain, site và origin

Các khái niệm sau giải quyết những câu hỏi khác nhau:

| Khái niệm | Thành phần chính | Dùng để quyết định |
|---|---|---|
| Host | Tên máy chủ trong URL, ví dụ `portal.example.com` | Request đi tới máy chủ nào; cookie host-only gắn với host nào |
| Cookie domain | Host-only hoặc domain được chỉ định trong `Domain` | Host nào được trình duyệt gửi cookie tới |
| Site | Scheme và registrable domain theo quy tắc same-site hiện đại | Ngữ cảnh same-site/cross-site cho `SameSite` và một số chính sách trình duyệt |
| Origin | Scheme, host và port | Same-origin policy, CORS và quyền truy cập giữa các origin |
| Registrable domain | Domain có thể đăng ký theo Public Suffix List, thường gọi là eTLD+1 | Ranh giới domain chính để xác định site và phạm vi chia sẻ cookie |

Ví dụ với HTTPS:

- `https://portal.example.com` và `https://api.example.com` là hai origin khác nhau vì host khác nhau.
- Hai host trên thường cùng site vì có cùng scheme `https` và registrable domain `example.com`.
- `https://portal.example.com` và `https://portal.example.net` khác site và khác origin.
- `http://portal.example.com` và `https://api.example.com` là khác scheme; trình duyệt hiện đại áp dụng khái niệm schemeful same-site nên chúng được xem là cross-site.
- `https://portal.example.com:8443` và `https://portal.example.com:9443` khác origin vì port khác nhau, nhưng port không tạo ra phạm vi cookie riêng và không làm chúng thành hai site khác nhau.

Vì vậy, nói “hai ứng dụng cùng domain” chưa đủ chính xác. Cần xác định chúng cùng host, cùng registrable domain, cùng site hay cùng origin tùy vấn đề đang giải quyết.

## 2. Registrable domain và Public Suffix List

Registrable domain không đơn giản là lấy hai nhãn cuối cùng của hostname. Trình duyệt dựa vào Public Suffix List để biết phần nào là public suffix và phần nào có thể đăng ký độc lập.

Ví dụ:

| Host | Public suffix | Registrable domain |
|---|---|---|
| `portal.example.com` | `com` | `example.com` |
| `api.example.com` | `com` | `example.com` |
| `shop.example.co.uk` | `co.uk` | `example.co.uk` |
| `login.example.net` | `net` | `example.net` |

`portal.example.com` và `api.example.com` cùng registrable domain `example.com`. Nhưng `example.com` và `example.net` là hai registrable domain độc lập.

Điều này ảnh hưởng cả SameSite lẫn cookie Domain. Một ứng dụng ở `portal.example.com` có thể phát cookie với `Domain=example.com` để cookie được gửi tới các host phù hợp dưới `example.com`. Nó không thể phát cookie có `Domain=example.net`. Trình duyệt cũng từ chối đặt cookie trên public suffix như `com` hoặc `co.uk`, vì làm vậy sẽ cho phép một website đặt cookie ảnh hưởng tới nhiều website không liên quan.

Không tự xác định registrable domain bằng cách tách chuỗi hostname. Với domain nhiều tầng như `example.co.uk`, cách đó dễ tạo kết quả sai. Dùng thư viện hoặc dữ liệu Public Suffix List được cập nhật nếu ứng dụng thật sự cần phân tích site/domain.

## 3. Cookie host-only và cookie Domain-wide

Nếu response `Set-Cookie` không có thuộc tính `Domain`, trình duyệt tạo host-only cookie. Cookie chỉ được gửi tới đúng host đã phát hành.

Ví dụ response từ `portal.example.com`:

```http
Set-Cookie: PORTAL_SESSION=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie này được gửi tới `portal.example.com`, không tự động tới `api.example.com`.

Nếu ứng dụng phát:

```http
Set-Cookie: SHARED_SESSION=opaque-id; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
```

trình duyệt có thể gửi cookie tới `example.com` và các subdomain phù hợp như `portal.example.com`, `api.example.com`. Host phát hành phải domain-match thuộc tính Domain; không thể đặt cookie cho domain cha không liên quan hoặc public suffix.

Một vài quy tắc cần nhớ:

- Bỏ `Domain` là host-only; đây là lựa chọn giới hạn phạm vi tốt nếu không cần chia sẻ.
- `Domain=example.com` bao phủ domain đó và các subdomain phù hợp.
- `Domain=portal.example.com` không bao phủ sibling `api.example.com`.
- Dấu chấm đầu như `.example.com` không tạo khác biệt trong cách xử lý hiện đại; dùng `example.com`.
- Cookie không được phân vùng theo port.
- `Path` lọc request path nhưng không thay thế ranh giới bảo mật theo host.

Domain-wide cookie có thể giúp chia sẻ session ID giữa các subdomain, nhưng mọi subdomain trong phạm vi đó trở thành nơi trình duyệt có thể gửi bearer credential. Chỉ dùng khi các subdomain cùng một ranh giới tin cậy.

## 4. Same-site không đồng nghĩa same-origin

Hai URL có thể cùng site nhưng khác origin. Ví dụ:

```text
https://portal.example.com  -> origin A
https://api.example.com     -> origin B
```

Chúng khác host nên khác origin. Trình duyệt áp dụng same-origin policy và CORS khi JavaScript từ portal gọi API. Tuy nhiên, chúng thường cùng site vì scheme và registrable domain giống nhau.

Hệ quả:

- `SameSite=Lax` hoặc `SameSite=Strict` không nhất thiết ngăn cookie gửi giữa hai subdomain cùng site; cookie vẫn cần domain/path phù hợp.
- JavaScript từ portal gọi API vẫn là cross-origin và cần CORS policy phù hợp nếu muốn đọc response.
- `fetch` cross-origin cần cấu hình credentials ở client nếu request phải gửi cookie.
- CORS không làm cookie vượt qua Domain, Path, Secure hoặc SameSite.

Ngược lại, hai URL có thể cùng origin nhưng request vẫn chịu các điều kiện cookie thông thường như Path, Secure và thời hạn. Origin là khái niệm quyền truy cập tài nguyên; cookie scope là một cơ chế riêng.

## 5. Schemeful same-site và ảnh hưởng HTTP/HTTPS

Trình duyệt hiện đại áp dụng schemeful same-site: scheme là một phần của site. Vì vậy, `http://portal.example.com` và `https://api.example.com` không được xem là cùng site chỉ vì cùng registrable domain.

Điều này quan trọng trong môi trường có một subdomain cũ chạy HTTP và một ứng dụng mới chạy HTTPS. Cookie `SameSite=Lax` có thể không được gửi trong một số request giữa hai ngữ cảnh này vì chúng là cross-site theo schemeful same-site. Cookie có `Secure` cũng chỉ được gửi qua HTTPS.

Giải pháp đúng thường là chuẩn hóa toàn bộ ứng dụng liên quan sang HTTPS và cấu hình reverse proxy/forwarded headers chính xác. Không hạ `SameSite` hoặc bỏ `Secure` chỉ để che giấu một cấu hình TLS không đồng nhất.

## 6. SameSite Strict, Lax và None

`SameSite` quyết định trình duyệt có gửi cookie trong một số ngữ cảnh cross-site hay không. Nó không quyết định cookie thuộc host nào và không làm thay đổi registrable domain.

| Giá trị | Hành vi khái quát | Tình huống thường cân nhắc |
|---|---|---|
| `Strict` | Hạn chế cookie trong ngữ cảnh cross-site | Ứng dụng muốn hạn chế tối đa cookie khi người dùng đi từ site khác |
| `Lax` | Cho phép cookie trong same-site và một số top-level navigation cross-site an toàn | Nhiều ứng dụng web thông thường |
| `None` | Cho phép gửi cookie trong ngữ cảnh cross-site nếu các điều kiện khác thỏa | Một số tích hợp cross-site hoặc iframe cần cookie |

Trình duyệt hiện đại yêu cầu cookie `SameSite=None` phải có `Secure`. Tuy nhiên, `SameSite=None; Secure` không bảo đảm cookie third-party được gửi: trình duyệt có thể chặn cookie bên thứ ba hoặc áp dụng partitioning theo chính sách quyền riêng tư.

Nếu không khai báo SameSite, trình duyệt có thể áp dụng mặc định riêng; nhiều trình duyệt hiện đại mặc định theo hành vi gần với Lax. Không nên dựa vào default vì hành vi có thể khác theo browser/version. Hãy phát thuộc tính tường minh theo yêu cầu ứng dụng.

## 7. Cookie bên thứ ba và giới hạn khi nhúng ứng dụng

Một cookie có thể được xem là third-party trong request khi site của tài nguyên được tải khác site cấp cao nhất (top-level site) đang mở. Ví dụ, người dùng đang ở `https://news.example.net` và trang nhúng iframe từ `https://portal.example.com`.

Trong tình huống này, cookie của `portal.example.com` được sử dụng trong ngữ cảnh bên thứ ba. Dù cookie được phát với `SameSite=None; Secure`, trình duyệt vẫn có thể chặn hoặc hạn chế cookie theo cài đặt người dùng, chế độ riêng tư, chính sách doanh nghiệp hoặc thay đổi của trình duyệt.

Do đó:

- Không thiết kế xác thực quan trọng chỉ dựa vào third-party cookie trong iframe.
- Kiểm thử trên các browser/version mà ứng dụng hỗ trợ và với chính sách chặn cookie bên thứ ba được bật.
- Cân nhắc top-level redirect tới ứng dụng xác thực để thiết lập phiên trong first-party context.
- Nếu dùng embedded app, xác định rõ fallback khi cookie bị chặn.

Third-party cookie policy là lớp độc lập với Domain và SameSite. Đặt `Domain=example.com` không giúp cookie của `example.com` được gửi khi trình duyệt chặn cookie bên thứ ba trong ngữ cảnh hiện tại.

## 8. Partitioned cookies và giới hạn chia sẻ

Một số trình duyệt hỗ trợ partitioned cookies (ví dụ thuộc tính `Partitioned`, liên quan tới CHIPS). Cookie partitioned được lưu trong partition gắn với top-level site. Nhờ đó, cùng một embedded service có thể có cookie riêng trong từng site nhúng.

Partitioning giải quyết một bài toán khác với chia sẻ một session giữa nhiều site:

- Cookie partitioned trong `news.example.net` không tự động là cùng cookie trong `shop.example.org`.
- Giá trị cookie có thể được cô lập theo top-level site, nên không dùng nó làm một session ID toàn cục giữa các ứng dụng khác site.
- Cookie partitioned không thay thế session repository dùng chung và không biến hai registrable domain thành cùng site.
- Hỗ trợ và chính sách của trình duyệt cần được kiểm tra thực tế.

Nếu ứng dụng cần một danh tính đăng nhập thống nhất qua nhiều site, hãy dùng một giao thức xác thực liên ứng dụng như OpenID Connect thay vì dựa vào partitioned cookie để chia sẻ session.

## 9. CORS và fetch giữa các subdomain

`https://portal.example.com` gọi `https://api.example.com` là cross-origin dù thường same-site. Nếu JavaScript cần gửi cookie, phải bật credentials:

```javascript
fetch("https://api.example.com/profile", {
  method: "GET",
  credentials: "include"
});
```

API cần trả CORS headers cho origin cụ thể:

```http
Access-Control-Allow-Origin: https://portal.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Khi dùng credentials, không thể đặt `Access-Control-Allow-Origin: *`. Server cần cho phép origin cụ thể và xử lý preflight nếu request dùng method hoặc header không đơn giản.

Hãy phân tích từng lớp độc lập:

1. Domain/host xác định cookie có thể gửi tới host nào.
2. Path xác định request path nào phù hợp.
3. Secure xác định cookie có được gửi qua HTTP hay không.
4. SameSite và browser privacy policy xác định ngữ cảnh site có được phép gửi cookie không.
5. Fetch credentials mode quyết định JavaScript có yêu cầu gửi credential không.
6. CORS quyết định JavaScript có được phép đọc response cross-origin hay không.

Nếu một lớp không thỏa, bật CORS không thể sửa Domain mismatch hoặc cookie bị chặn bởi SameSite. Tương tự, cookie được gửi không có nghĩa JavaScript được phép đọc response.

## 10. Cookie sharing không tự tạo SSO

Giả sử portal và API cùng nhận cookie `SHARED_SESSION`. Việc đó chỉ cung cấp cùng một session ID cho hai ứng dụng. Để thực sự đọc cùng phiên, cả hai phải:

- Dùng cùng Redis deployment/namespace hoặc cùng JDBC database/schema phù hợp.
- Dùng cùng session ID resolver và cookie name.
- Dùng serializer/converter tương thích với mọi attribute mà ứng dụng cần đọc.
- Thống nhất idle timeout và cách cập nhật last-access time.
- Có class principal, Spring Security module và model dữ liệu tương thích.
- Xác định rõ ứng dụng nào được phép tin cậy session và thuộc tính nào được chia sẻ.

Nếu portal dùng Redis namespace `portal:sessions` còn API dùng `api:sessions`, cùng cookie vẫn không giúp API tìm thấy dữ liệu. Nếu hai app dùng serializer khác nhau, API có thể không deserialize được `SecurityContext` hoặc custom principal.

Chia sẻ session không tự giải quyết authorization. API phải tự kiểm tra quyền, tenant, audience và phạm vi truy cập của request. Không nên để một ứng dụng có mức tin cậy thấp đọc toàn bộ session attributes của ứng dụng quản trị chỉ vì chúng cùng dùng một session ID.

## 11. Giới hạn bảo mật của cookie domain-wide

Cookie với `Domain=example.com` được gửi tới các subdomain phù hợp. Điều này mở rộng nơi nhận bearer credential. Một subdomain bị takeover, có DNS misconfiguration hoặc chạy nội dung không tin cậy có thể làm tăng nguy cơ lộ session.

Trước khi chia sẻ cookie giữa subdomain, đánh giá:

- Có bao nhiêu subdomain và ai quản lý từng subdomain?
- Có subdomain do tenant, đối tác hoặc người dùng tự tạo không?
- Có host phục vụ file upload hoặc nội dung HTML không tin cậy không?
- Có hệ thống legacy dùng cùng cookie name nhưng repository khác không?
- Các ứng dụng có cùng mức bảo mật và cùng vòng đời release không?
- Có thể dùng host-only cookie kết hợp OIDC/token exchange thay vì cookie domain-wide không?

`Path` không phải ranh giới bảo mật mạnh. CORS cũng không ngăn một request được gửi tới server; nó chủ yếu kiểm soát việc script đọc response. `SameSite` không đủ để bảo vệ CSRF giữa các subdomain cùng site nếu một sibling subdomain bị kiểm soát. Ứng dụng dùng cookie authentication vẫn cần CSRF token, kiểm tra `Origin`/`Referer` theo chính sách và authorization server-side.

## 12. Cấu hình Spring Session cho chia sẻ giữa subdomain

Với ứng dụng Servlet, `DefaultCookieSerializer` cho phép đặt cookie name, Domain, Path, Secure, HttpOnly và SameSite. Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
class SharedSubdomainSessionCookieConfiguration {

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

Ví dụ chỉ phù hợp khi các subdomain thuộc cùng ranh giới tin cậy và thực sự cần cùng cookie. Trong production, HTTPS phải được sử dụng; nếu TLS kết thúc tại reverse proxy, cấu hình forwarded headers và cookie serializer phải thống nhất để cookie được phát với thuộc tính đúng.

Nếu không cần chia sẻ qua subdomain, bỏ `setDomainName` để tạo host-only cookie. Có thể dùng cookie prefix `__Host-` với `Secure`, `Path=/` và không có `Domain` để trình duyệt áp dụng ràng buộc host-only chặt hơn. Cookie `__Host-` không thể dùng để chia sẻ cùng một cookie qua sibling subdomain.

Với WebFlux, Spring Session dùng `WebSessionIdResolver` và `CookieWebSessionIdResolver`, không dùng trực tiếp Servlet `DefaultCookieSerializer`. Cấu hình cookie phải theo API của reactive stack.

## 13. Khi ứng dụng nằm trên các registrable domain khác nhau

Ví dụ `portal.example.com` và `identity.example.net` là hai site khác nhau. Không có thuộc tính `Domain` nào cho phép portal đặt cookie để trình duyệt gửi tới `identity.example.net`. `SameSite=None` chỉ thay đổi chính sách gửi cookie trong ngữ cảnh cross-site; nó không thay đổi domain sở hữu cookie.

Giải pháp phù hợp thường là OpenID Connect hoặc một giao thức SSO tương đương:

1. Người dùng truy cập ứng dụng A và chưa có phiên local.
2. Ứng dụng A chuyển hướng trình duyệt tới authorization server ở domain xác thực.
3. Authorization server sử dụng cookie first-party của chính domain đó để nhận diện người dùng.
4. Sau xác thực, authorization server trả authorization code về callback của ứng dụng A.
5. Ứng dụng A đổi code ở back channel, xác minh token và tạo session local bằng Spring Session.
6. Ứng dụng B thực hiện flow tương tự; authorization server nhận diện phiên của nó trong first-party context và cấp code/token riêng cho B.

Mỗi ứng dụng giữ cookie session host-only của riêng mình. SSO được cung cấp bởi giao thức xác thực và authorization server, không phải bằng cách chia sẻ cookie giữa hai registrable domain.

Không đưa session ID của ứng dụng A vào URL để chuyển sang B. URL có thể xuất hiện trong browser history, referrer, proxy log và analytics. Dùng authorization code flow với PKCE cho public clients và token exchange/back-channel phù hợp.

## 14. Kiểm thử subdomain, site và origin

Kiểm thử bằng unit test header `Set-Cookie` chưa đủ. Cần kiểm thử bằng browser cookie jar qua các host thật hoặc môi trường test có domain tương ứng.

Các kịch bản nên có:

1. **Host-only:** login ở `portal.example.com`; xác nhận cookie không được gửi tới `api.example.com`.
2. **Parent Domain:** phát `Domain=example.com`; xác nhận cookie được gửi tới các subdomain phù hợp.
3. **Domain độc lập:** xác nhận cookie của `example.com` không được gửi tới `example.net`.
4. **Public suffix:** xác nhận trình duyệt từ chối Domain không hợp lệ như public suffix.
5. **Same-site khác origin:** gọi API từ portal sang api cùng site và xác nhận cần CORS/credentials phù hợp.
6. **Schemeful same-site:** kiểm thử HTTP subdomain gọi HTTPS subdomain và xác nhận cookie theo SameSite/Secure policy.
7. **Khác port:** xác nhận cookie không được cô lập theo port dù origin khác nhau.
8. **SameSite:** kiểm thử Strict, Lax, None với top-level navigation, cross-site POST và iframe.
9. **Third-party blocking:** bật chính sách chặn cookie bên thứ ba và xác nhận fallback hoạt động.
10. **Partitioned cookie:** xác nhận cookie partitioned trong hai top-level site không bị nhầm là cùng một session toàn cục.
11. **CORS:** kiểm tra `credentials: include`, exact allowed origin, allow credentials và preflight.
12. **CSRF:** kiểm thử request thay đổi trạng thái từ sibling subdomain không tin cậy.
13. **Repository sharing:** xác nhận hai ứng dụng dùng cùng cookie có thể đọc cùng session attributes được phép từ cùng backend.
14. **Logout:** logout ở ứng dụng A và xác nhận cách thu hồi/đóng phiên ở ứng dụng B theo thiết kế event hoặc revocation.

Kiểm thử trên các browser/version được hỗ trợ vì chính sách third-party cookie và partitioning có thể thay đổi. Dùng tài khoản giả, domain test và cookie jar riêng; không đưa cookie production vào test report.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Subdomain sibling không nhận cookie | Cookie host-only hoặc Domain chỉ là subdomain phát hành | Kiểm tra `Set-Cookie` và Domain attribute |
| Cookie không đi qua hai domain độc lập | Domain attribute không thể vượt registrable-domain boundary | Dùng OIDC/SSO thay vì cố mở rộng Domain |
| SameSite=None nhưng iframe vẫn không có cookie | Browser chặn third-party cookie hoặc partitioning | Kiểm tra browser policy và thiết kế top-level redirect/fallback |
| Cùng site nhưng JavaScript không đọc được API response | Hai subdomain khác origin và CORS chưa đúng | Cấu hình exact origin, credentials và preflight |
| Cookie không được gửi giữa HTTP và HTTPS subdomain | Schemeful same-site và/hoặc Secure attribute | Chuẩn hóa HTTPS và kiểm tra SameSite/Secure |
| Cookie gửi tới mọi subdomain ngoài dự kiến | Domain-wide cookie quá rộng | Chuyển host-only hoặc thu hẹp domain architecture |
| App B nhận cookie nhưng không tìm thấy session | Repository/namespace khác nhau hoặc serializer không tương thích | So sánh session store và serializer của hai app |
| CSRF từ sibling subdomain vẫn thành công | Cùng site nên SameSite không chặn request; thiếu CSRF/Origin validation | Bổ sung CSRF token và kiểm tra Origin theo allowlist |
| Port khác nhưng vẫn nhận cùng cookie | Cookie không được phân vùng theo port | Dùng hostname riêng nếu cần cô lập |
| Cookie cũ vẫn được gửi sau thay đổi | Cookie name giống nhau nhưng scope cũ chưa được xóa đúng | Hết hạn cookie với đúng Domain và Path cũ |

## 16. Nguyên tắc triển khai

- Host, cookie domain, site và origin là các khái niệm khác nhau; xác định đúng loại ranh giới trước khi cấu hình.
- Site hiện đại có tính tới scheme và registrable domain; origin gồm scheme, host và port.
- Host-only cookie chỉ được gửi tới host phát hành; `Domain=example.com` có thể mở rộng tới subdomain phù hợp.
- Không thể dùng Domain hoặc `SameSite=None` để chia sẻ cookie giữa các registrable domain độc lập.
- Cookie không được cô lập theo port; Path chỉ lọc đường dẫn và không phải ranh giới bảo mật.
- SameSite, Secure, third-party cookie policy và partitioning đều có thể ngăn cookie được gửi dù Domain/Path khớp.
- Hai subdomain cùng site vẫn có thể khác origin; cross-origin fetch cần credentials và CORS policy chính xác.
- Chia sẻ cookie chỉ chia sẻ session ID; các ứng dụng còn phải dùng chung repository, namespace, serializer và timeout tương thích.
- Domain-wide cookie mở rộng bearer credential tới nhiều subdomain; chỉ dùng trong cùng ranh giới tin cậy và vẫn cần CSRF protection.
- Với các site khác nhau, dùng OIDC/SSO và session local thay vì cố chia sẻ cookie.
- Kiểm thử bằng browser cookie jar trên nhiều host, scheme, origin, iframe, CORS, logout và browser privacy settings.
