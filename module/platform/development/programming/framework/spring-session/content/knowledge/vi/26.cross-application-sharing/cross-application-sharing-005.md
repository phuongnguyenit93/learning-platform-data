# Ranh giới tin cậy khi nhiều ứng dụng có thể đọc, sửa cùng một phiên

Spring Session cho phép nhiều instance hoặc nhiều ứng dụng dùng chung một kho session như Redis hoặc JDBC. Khi các ứng dụng cùng nhận một session ID và cùng truy cập bản ghi phiên, chúng có thể đọc hoặc thay đổi các attributes do ứng dụng khác ghi. Khả năng kỹ thuật này không tự động tạo ra một ranh giới bảo mật hợp lệ: ứng dụng nào đọc được session có thể tiếp cận dữ liệu của ứng dụng khác, và một ứng dụng bị xâm nhập có thể sửa hoặc thu hồi trạng thái mà ứng dụng còn lại đang tin cậy.

Trước khi chia sẻ session, cần xác định các ứng dụng có thật sự thuộc cùng một miền tin cậy hay không. Nếu chỉ cần đăng nhập một lần trên nhiều ứng dụng, OpenID Connect hoặc một giao thức SSO thường tạo ranh giới rõ ràng hơn việc cho mọi ứng dụng đọc và sửa cùng một session store. Nếu bắt buộc chia sẻ session, phải thống nhất cookie, namespace, schema attributes, serializer, timeout, quyền truy cập kho dữ liệu, quy tắc cập nhật đồng thời và hành vi logout.

## 1. Chia sẻ session là chia sẻ quyền đọc và ghi trạng thái

Một session phía server thường chứa `SecurityContext`, principal hoặc mã tham chiếu tới người dùng, trạng thái quy trình, tùy chọn và dữ liệu tạm thời. Khi ứng dụng A và B cùng dùng một session ID và cùng repository, cả hai có thể truy cập cùng trạng thái phiên theo quyền mà repository cung cấp.

Ví dụ, ứng dụng A ghi:

```java
session.setAttribute("checkout.currentStep", "PAYMENT");
session.setAttribute("checkout.cartId", "CART-204");
```

Ứng dụng B có thể đọc các giá trị đó nếu nó khôi phục đúng session và serializer hiểu kiểu dữ liệu. Nhưng nếu B có quyền ghi cùng session, nó cũng có thể thay đổi hoặc xóa chúng:

```java
session.removeAttribute("checkout.currentStep");
session.setAttribute("checkout.currentStep", "CONFIRMED");
```

Do đó, dùng chung session store tương đương chia sẻ một vùng trạng thái có thể thay đổi. Prefix attribute chỉ giúp tránh đụng tên; nó không phải cơ chế phân quyền. Một ứng dụng có thể đọc hoặc ghi key của ứng dụng khác nếu nó có quyền đọc/ghi session chứa key đó.

## 2. Phân biệt dùng chung hạ tầng và dùng chung session

Hai ứng dụng có thể dùng cùng một Redis cluster hoặc cùng một database mà vẫn giữ session riêng. Điều quan trọng là repository namespace, bảng và cookie được tách biệt.

| Mô hình | Kho vật lý | Namespace/bảng | Cookie | Mức chia sẻ |
|---|---|---|---|---|
| Cùng hạ tầng, session riêng | Redis/database chung | Khác nhau | Tên hoặc path riêng | Không đọc cùng session theo mặc định |
| Cùng session store | Redis/database chung | Cùng namespace hoặc cùng bảng/session schema | Cùng cookie name, domain và path phù hợp | Các ứng dụng có thể khôi phục cùng session |
| SSO bằng OIDC | Có thể dùng kho riêng | Riêng từng ứng dụng | Cookie session riêng từng ứng dụng | Chia sẻ danh tính qua token/protocol, không chia sẻ session record |

Ví dụ, A dùng namespace `app-a:session`, B dùng `app-b:session`; hai ứng dụng có thể cùng kết nối Redis nhưng session không tự xuất hiện trong repository của nhau. Nếu cả hai cấu hình cùng namespace, cùng cách đọc session ID và tương thích serializer, chúng có thể truy cập cùng dữ liệu session.

Không xem việc dùng chung Redis host hoặc database là lý do đủ để chia sẻ session. Chọn namespace và cookie riêng thường an toàn hơn khi ứng dụng có vòng đời, đội vận hành hoặc mức độ tin cậy khác nhau.

## 3. Điều kiện kỹ thuật để hai ứng dụng khôi phục cùng session

Để ứng dụng A và B cùng khôi phục một phiên, tối thiểu phải tương thích các yếu tố sau:

1. **Session ID:** cả hai đọc cùng giá trị từ cookie hoặc header.
2. **Cookie scope:** tên cookie, domain và path cho phép trình duyệt gửi ID tới cả hai ứng dụng.
3. **Repository:** cả hai kết nối tới cùng kho session và cùng namespace/bảng.
4. **Schema:** các trường metadata và attributes có cấu trúc mà cả hai hiểu.
5. **Serializer:** dữ liệu do A ghi có thể được B deserialize an toàn, và ngược lại nếu B ghi.
6. **Timeout:** hai bên thống nhất semantics về inactivity timeout và expiration.
7. **Security policy:** hai bên hiểu rõ attribute nào là dữ liệu tin cậy, ai có quyền thay đổi và cách thu hồi.

Nếu cookie được gửi tới B nhưng B dùng namespace khác, B không tìm thấy session. Tùy luồng request, B có thể xem request như chưa có session và tạo phiên mới; điều đó không phải SSO. Nếu namespace giống nhưng serializer không tương thích, B có thể gặp lỗi deserialize hoặc bỏ qua dữ liệu không đọc được.

## 4. Cấu hình chia sẻ Redis session có chủ đích

Ví dụ hai ứng dụng Servlet cùng dùng một namespace Redis và cùng cookie session:

```java
@Configuration
@EnableRedisHttpSession(
        redisNamespace = "company:shared-session",
        maxInactiveIntervalInSeconds = 1800)
class SharedSessionConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("COMPANY_SESSION");
        serializer.setCookieDomain("example.com");
        serializer.setCookiePath("/");
        serializer.setUseSecureCookie(true);
        serializer.setUseHttpOnlyCookie(true);
        serializer.setSameSite("Lax");
        return serializer;
    }
}
```

Nếu cả A và B dùng cùng cấu hình này, cùng Redis deployment và cùng serializer/schema, cookie `COMPANY_SESSION` có thể đưa cùng session ID tới cả hai subdomain thuộc `example.com`.

Đây là cấu hình minh họa cho ứng dụng Servlet. Các phiên bản Spring Session khác nhau có thể cung cấp annotation/property hoặc customizer khác nhau; hãy đối chiếu API đúng phiên bản. Không đăng ký hai cơ chế tạo repository cho cùng một ứng dụng. Nếu dùng JDBC, hai ứng dụng phải dùng cùng schema/table và SQL tương thích; hai bảng riêng sẽ không tự chia sẻ session.

Không mở rộng cookie domain tới `example.com` nếu các subdomain không cùng mức độ tin cậy. Cookie domain rộng khiến trình duyệt gửi session ID tới nhiều host hơn. Một subdomain yếu hoặc bị chiếm quyền có thể tạo thêm bề mặt tấn công cho credential dùng chung.

## 5. Cookie session ID là bearer credential

Cookie thường chỉ chứa một session ID ngẫu nhiên, không phải toàn bộ attributes. Tuy vậy, session ID là bearer credential: bên nào có được ID còn hiệu lực có thể thử dùng phiên đó.

Khi chia sẻ session giữa subdomain, cần đánh giá:

- `Secure`: chỉ gửi cookie qua HTTPS.
- `HttpOnly`: hạn chế JavaScript đọc cookie, nhưng không ngăn script bị xâm nhập gửi request thay mặt người dùng.
- `SameSite`: chọn theo luồng điều hướng/SSO. `Lax` thường phù hợp cho nhiều ứng dụng web; `None` chỉ dùng khi thật sự cần cookie trong ngữ cảnh cross-site và phải đi cùng `Secure`.
- `Domain`: giới hạn host nhận cookie. Domain cha mở rộng phạm vi chia sẻ sang các subdomain.
- `Path`: giới hạn đường dẫn nhận cookie; `/` chia sẻ với toàn bộ ứng dụng trên host.
- `Max-Age`/`Expires`: điều khiển thời gian browser giữ cookie, không thay thế session timeout phía server.

`SameSite` không phải cơ chế phân quyền giữa các ứng dụng cùng site và không thay thế CSRF protection. CORS cũng không làm cookie trở thành credential riêng cho từng ứng dụng; CORS chủ yếu điều khiển việc JavaScript đọc response cross-origin. Nếu A và B dùng chung cookie, mỗi ứng dụng vẫn cần CSRF policy phù hợp cho các thao tác thay đổi trạng thái.

## 6. Ranh giới tin cậy quan trọng nhất: SecurityContext

Không nên mặc định chia sẻ `SecurityContext` giữa các ứng dụng chỉ vì chúng cùng đọc được session. `SecurityContext` có thể chứa `Authentication`, principal, authorities và các chi tiết phụ thuộc vào cấu hình Spring Security của một ứng dụng.

Ví dụ, A xác thực người dùng với authorities `ROLE_CUSTOMER`, còn B có các quyền `ROLE_OPERATOR`, `ROLE_ADMIN`. Nếu B tin nguyên trạng authorities do A lưu, một lỗi mapping hoặc một principal class không tương thích có thể dẫn tới cấp quyền sai. B cũng có thể có quy tắc về tenant, audience hoặc mức xác thực khác A.

Các nguyên tắc nên áp dụng:

- Mỗi ứng dụng tự thực hiện authorization cho tài nguyên của mình.
- Không coi một attribute như `authenticated=true` là bằng chứng xác thực.
- Không chấp nhận username hoặc role do ứng dụng khác ghi nếu chưa xác định cơ chế tin cậy.
- Không dùng `SecurityContext` chia sẻ như một giao thức SSO không được đặc tả.
- Nếu chia sẻ trạng thái xác thực, phải định nghĩa issuer, subject, audience, thời hạn, authorities/scopes và cách thu hồi.

Trong nhiều kiến trúc, cách an toàn hơn là dùng OIDC: identity provider xác thực người dùng; mỗi ứng dụng nhận token có audience và scope phù hợp, sau đó tạo `Authentication` cục bộ. Session của A và B vẫn độc lập.

## 7. Chia sẻ danh tính bằng OIDC thay vì chia sẻ toàn bộ session

SSO không đòi hỏi mọi ứng dụng cùng đọc một session record. Với OpenID Connect:

1. Người dùng truy cập ứng dụng A và được chuyển tới identity provider.
2. Identity provider xác thực người dùng và tạo kết quả đăng nhập/token theo protocol.
3. A nhận token có issuer, audience, subject và thời hạn được xác minh.
4. Người dùng truy cập B; B cũng chuyển tới identity provider.
5. Identity provider có thể dùng phiên đăng nhập của chính nó để hoàn tất SSO mà không yêu cầu nhập credential lại.
6. B nhận token dành cho B, xác minh độc lập và tạo session cục bộ nếu cần.

Mỗi ứng dụng quản lý cookie và session riêng. Token giúp chia sẻ danh tính có cấu trúc, có audience/scope và thời hạn rõ ràng. Điều này giảm việc cho ứng dụng A quyền đọc/ghi mọi attribute của B.

OIDC không tự giải quyết mọi vấn đề logout toàn cục hoặc revocation. Cần chọn front-channel/back-channel logout, token expiry hoặc introspection theo yêu cầu. Tuy nhiên, nó cung cấp giao thức rõ hơn việc cùng lưu `SecurityContext` vào một session tùy ý.

## 8. Định nghĩa hợp đồng attributes nếu bắt buộc chia sẻ

Nếu các ứng dụng thật sự cần trao đổi trạng thái qua một session, hãy định nghĩa schema dùng chung. Mỗi attribute cần có:

- Tên có namespace và version.
- Kiểu dữ liệu ổn định.
- Chủ sở hữu ghi (writer) và các bên được đọc.
- Quy tắc validation và authorization.
- Thời gian tồn tại và hành vi khi thiếu/không tương thích.
- Quy tắc thay đổi trong rolling deployment.

Ví dụ quy ước:

```text
identity.subject.v1
identity.tenant.v1
checkout.reference.v1
checkout.state.v1
preferences.locale.v1
```

Prefix giúp tránh va chạm tên giữa ứng dụng A và B. Version suffix giúp thay đổi schema có kiểm soát. Nhưng prefix không ngăn ứng dụng B ghi `identity.subject.v1`; quyền ghi vẫn do repository và thiết kế ứng dụng quyết định.

Nên lưu dữ liệu nhỏ và ổn định, ví dụ user ID, tenant ID đã xác minh hoặc reference ID. Tránh lưu entity ORM, object chứa service, request/response, lazy collection hoặc dữ liệu cá nhân dư thừa. Khi một ứng dụng không hiểu version mới, hành vi phải là từ chối hoặc bỏ qua attribute theo hợp đồng; không deserialize tùy tiện sang class gần giống.

## 9. Serializer và tương thích phiên bản

Hai ứng dụng phải thống nhất định dạng serialization. Nếu A dùng Java native serialization và B dùng JSON converter, B không thể mặc nhiên đọc byte do A ghi. Ngay cả khi cùng dùng Java serialization, class name, package, `serialVersionUID`, dependency và classloader phải tương thích.

Các biện pháp nên cân nhắc:

- Dùng DTO nhỏ, có schema version và type ID allowlist.
- Ưu tiên định dạng dữ liệu rõ ràng, có kiểm soát kiểu và validation.
- Không bật polymorphic deserialization rộng trên dữ liệu session.
- Không cho phép deserialize class tùy ý chỉ vì session đến từ Redis dùng chung.
- Kiểm thử dữ liệu A ghi, B đọc; B ghi, A đọc; và phiên bản cũ/mới cùng chạy.
- Có kế hoạch cho attribute không tương thích: bỏ qua an toàn, migrate có kiểm soát hoặc yêu cầu người dùng tạo session mới.

Một ứng dụng bị xâm nhập có thể ghi payload độc hại vào session store nếu có quyền ghi. Vì vậy, serializer phải coi dữ liệu đọc từ kho chia sẻ là dữ liệu cần validation. Redis nằm trong mạng nội bộ không biến payload thành đáng tin tuyệt đối.

## 10. Tách quyền truy cập kho dữ liệu

Khi nhiều ứng dụng cùng dùng Redis, ACL hoặc network policy nên giới hạn quyền theo nhu cầu. Tuy nhiên, nếu cả hai dùng cùng namespace và cần đọc/ghi cùng session keys, Redis ACL ở mức key pattern có thể không phân biệt được quyền ghi từng attribute trong một hash. Redis không tự cung cấp field-level authorization cho mỗi ứng dụng trong hash session.

Điều này tạo ra một giới hạn quan trọng: nếu A và B cùng cần quyền ghi toàn bộ session key, compromise của A có thể cho phép sửa trạng thái mà B tin cậy. Prefix attribute không khắc phục được giới hạn đó.

Các lựa chọn:

- Dùng session store riêng cho từng ứng dụng và chia sẻ danh tính qua OIDC.
- Đưa dữ liệu dùng chung vào một service/API trung gian có authorization rõ ràng.
- Nếu vẫn dùng cùng session, chỉ cho các ứng dụng cùng miền tin cậy và cấp quyền Redis tối thiểu trên đúng namespace.
- Dùng Redis instance/service riêng khi cần cô lập mạnh; không xem Redis logical database là ranh giới bảo mật đủ mạnh.
- Bảo vệ kết nối bằng TLS, secret riêng, ACL và network isolation.

Với JDBC, có thể dùng database/schema/table và database principal riêng cho từng ứng dụng. Nhưng nếu hai ứng dụng cùng cần đọc/ghi cùng hàng session, quyền SQL vẫn có thể cho phép một ứng dụng sửa cả hàng và attributes. Cần phân tích quyền ở cấp bảng/hàng và cân nhắc API trung gian nếu cần kiểm soát chi tiết.

## 11. Namespace và cookie riêng cho ứng dụng không chia sẻ

Nếu không có nhu cầu chia sẻ session, hãy cấu hình namespace và cookie riêng. Ví dụ:

```java
// Ứng dụng A
@EnableRedisHttpSession(redisNamespace = "app-a:sessions")
class AppASessionConfiguration {
}

// Ứng dụng B
@EnableRedisHttpSession(redisNamespace = "app-b:sessions")
class AppBSessionConfiguration {
}
```

Và đặt cookie name riêng như `APP_A_SESSION` và `APP_B_SESSION`, cùng path phù hợp. Cấu hình minh họa; trong dự án Boot có thể dùng properties/customizer thay cho annotation. Mục tiêu là tránh hai ứng dụng vô tình đọc cùng session chỉ vì dùng chung Redis và cookie name mặc định.

Nếu hai ứng dụng cùng host nhưng context path khác nhau, cookie path có thể giúp tách cookie. Nếu hai ứng dụng ở subdomain khác nhau, host-only cookie thường tách biệt; chỉ dùng domain cha khi thực sự cần chia sẻ.

## 12. Timeout và logout khi dùng chung session

Một session dùng chung có một vòng đời chung. Nếu A và B cùng sửa last-access time hoặc timeout, hoạt động ở một ứng dụng có thể giữ session sống lâu hơn dự kiến của ứng dụng kia. Nếu timeout nghiệp vụ khác nhau, một session chung thường không phải abstraction phù hợp.

Khi A gọi `invalidate()` hoặc xóa session qua repository, B cũng sẽ không khôi phục được session đó ở request mới nếu cả hai thực sự dùng cùng store/namespace. Điều này có thể là hành vi mong muốn cho logout toàn cục, nhưng cũng có thể gây ảnh hưởng ngoài ý muốn nếu B chỉ muốn kết thúc một quy trình cục bộ.

Hãy định nghĩa rõ:

- Logout có nghĩa đăng xuất khỏi mọi ứng dụng hay chỉ ứng dụng hiện tại?
- Timeout được tính theo hoạt động ở A, B hay cả hai?
- Một ứng dụng có được phép xóa session do ứng dụng khác tạo không?
- Remember-me token có được chia sẻ không, hay mỗi ứng dụng có cơ chế riêng?
- Khi người dùng đổi tenant hoặc quyền, các ứng dụng khác nhận biết thay đổi bằng cách nào?

Nếu yêu cầu timeout/logout khác nhau, tách session và dùng identity provider hoặc revocation service để điều phối thường dễ kiểm soát hơn.

## 13. Cập nhật đồng thời từ nhiều ứng dụng

Hai ứng dụng có thể cùng đọc một snapshot, thay đổi attribute rồi lưu. Ví dụ A cập nhật `checkout.state`, trong khi B cập nhật `preferences.locale`. Nếu repository lưu toàn bộ attributes từ snapshot cũ, một lần ghi có thể ghi đè thay đổi của bên kia. Nếu repository chỉ ghi attributes đã được đặt, các cập nhật riêng có thể cùng tồn tại, nhưng xung đột trên cùng attribute vẫn có thể là last-write-wins.

Không giả định `SaveMode.ON_SET_ATTRIBUTE`, `FlushMode.ON_SAVE` hoặc transaction JDBC cung cấp khóa phân tán cho toàn bộ session. Các chế độ này điều khiển thời điểm/phạm vi ghi, không tự biến mọi chuỗi đọc–sửa–ghi thành thao tác nguyên tử.

Để giảm xung đột:

- Mỗi ứng dụng chỉ ghi các attribute thuộc quyền sở hữu của nó.
- Dùng prefix và schema version.
- Tránh nhiều ứng dụng sửa cùng một object mutable.
- Đưa dữ liệu nghiệp vụ có cập nhật đồng thời quan trọng sang bảng/service riêng có optimistic locking hoặc transaction.
- Dùng version/ETag hoặc compare-and-set ở tầng nghiệp vụ nếu cần phát hiện ghi đè.
- Viết test ép lịch A-read, B-read, A-save, B-save rồi kiểm tra trạng thái cuối.

Ví dụ, giỏ hàng, số dư hoặc trạng thái thanh toán không nên phụ thuộc vào một attribute session được nhiều ứng dụng cùng sửa mà không có cơ chế đồng bộ riêng.

## 14. Cookie scope và các ứng dụng trên subdomain

Để browser gửi cùng session cookie tới `app-a.example.com` và `app-b.example.com`, cookie thường phải có `Domain=example.com` và path phù hợp. Cookie host-only phát bởi `app-a.example.com` sẽ không được gửi tới `app-b.example.com`.

Mở rộng domain cookie có nghĩa mở rộng nơi credential được gửi. Nếu một subdomain do đội khác quản lý, có hệ thống plugin không tin cậy hoặc có nguy cơ takeover, cookie dùng chung làm tăng tác động của sự cố. `HttpOnly` giảm khả năng đọc cookie bằng JavaScript nhưng không ngăn một host nhận cookie hợp lệ và gửi request.

Nếu các ứng dụng ở domain hoàn toàn khác nhau, browser không thể gửi một cookie domain chung cho cả hai. Không cố sao chép session ID qua query string hoặc URL. Dùng OIDC redirect/token flow hoặc cơ chế trao đổi credential có chữ ký và audience thay thế.

## 15. CSRF và request cross-application

Khi cùng một cookie được gửi tới nhiều ứng dụng, mỗi ứng dụng có thể nhận request mang session ID mà không cần JavaScript của origin đó đọc được response. Vì vậy, CSRF vẫn cần được đánh giá độc lập ở từng ứng dụng.

- Giữ CSRF protection cho các request thay đổi trạng thái dùng cookie.
- Không coi `SameSite=Lax` là biện pháp duy nhất.
- Không dùng GET để thay đổi dữ liệu hoặc logout.
- Kiểm tra Origin/Referer theo chính sách phù hợp, nhưng không thay thế token CSRF khi framework yêu cầu.
- Đảm bảo token CSRF không bị chia sẻ hoặc xác minh sai giữa ứng dụng có ranh giới khác nhau.
- Kiểm tra CORS riêng; CORS không phải cơ chế ngăn trình duyệt gửi cookie.

Nếu A và B cùng một site nhưng khác subdomain, request có thể vẫn thuộc ngữ cảnh same-site theo định nghĩa trình duyệt. SameSite không tạo isolation giữa hai ứng dụng cùng site.

## 16. Không để một ứng dụng nâng quyền cho ứng dụng khác

Một lỗi thiết kế nguy hiểm là B tin một attribute do A ghi, ví dụ:

```java
session.setAttribute("isAdmin", true);
session.setAttribute("roles", List.of("ROLE_ADMIN"));
```

Nếu B dùng trực tiếp các giá trị đó để cấp quyền, ứng dụng A có thể trở thành nguồn cấp quyền cho B. Điều này chỉ hợp lệ khi A là authority được tin cậy, dữ liệu được xác thực và hợp đồng cấp quyền được thiết kế rõ.

Thay vì tin cờ boolean hoặc danh sách role tùy ý, mỗi ứng dụng nên:

- Tự kiểm tra principal qua identity provider hoặc authorization service.
- Kiểm tra audience/tenant/scope phù hợp với ứng dụng.
- Xác minh chữ ký và thời hạn của assertion/token nếu dùng cơ chế trao đổi.
- Không dùng giá trị từ session làm bằng chứng duy nhất cho thao tác nhạy cảm.
- Kiểm tra quyền trên tài nguyên cụ thể tại thời điểm thực hiện.

Một session store dùng chung không phải một trust broker. Redis/JDBC chỉ lưu bytes và metadata; nó không xác minh ứng dụng nào đã ghi attribute hoặc người dùng có quyền sử dụng giá trị đó.

## 17. Sự kiện, xóa phiên và tác động giữa các ứng dụng

Khi một ứng dụng xóa session qua Spring Session repository, ứng dụng còn lại sẽ không khôi phục được phiên ở request mới nếu cả hai dùng chung store. Tuy nhiên, event listener trong mỗi JVM không nhất thiết nhận được cùng một application event chỉ vì repository giống nhau.

Với Redis, một số repository có thể sử dụng Pub/Sub và keyspace notifications để truyền sự kiện tạo, xóa hoặc hết hạn. Cần cấu hình đúng notification, kiểm tra topology và hiểu rằng Pub/Sub/keyspace notifications không phải event log bền vững. Với JDBC, application event có thể chỉ được phát trong tiến trình thực hiện thao tác, tùy implementation; không giả định node khác tự nhận.

Nếu B cần đóng WebSocket hoặc xóa tài nguyên khi A logout, hãy dùng một cơ chế broadcast có chủ đích hoặc cho B kiểm tra session/revocation state. Listener nên idempotent vì có thể nhận lặp. Request mới phải dựa trên repository state; không dựa vào việc event chắc chắn đã đến.

## 18. Khi nào nên tách session thay vì chia sẻ?

Nên giữ session riêng nếu có một trong các điều kiện:

- Ứng dụng thuộc các đội hoặc tổ chức có mức tin cậy khác nhau.
- Một ứng dụng có thể bị triển khai hoặc vận hành bởi bên thứ ba.
- Các ứng dụng có quyền, tenant hoặc vòng đời đăng nhập khác nhau.
- Serializer, principal class hoặc phiên bản framework không tương thích.
- Một ứng dụng không nên có quyền sửa trạng thái của ứng dụng khác.
- Timeout hoặc logout policy khác nhau.
- Cần cô lập tác động khi một ứng dụng bị xâm nhập.

Trong các trường hợp này, dùng session store và cookie riêng; chia sẻ danh tính qua OIDC/SAML hoặc API identity có kiểm soát. Nếu cần chia sẻ một phần dữ liệu nghiệp vụ, tạo API/service riêng chỉ trả những trường được phép thay vì cấp quyền đọc toàn bộ session.

## 19. Kiểm thử ranh giới tin cậy giữa hai ứng dụng

Một bộ integration test cần xác minh cả trường hợp chia sẻ có chủ đích và trường hợp phải được cô lập:

1. **Namespace isolation:** A và B dùng namespace khác nhau; xác nhận session của A không được B khôi phục dù cùng Redis host.
2. **Cookie isolation:** kiểm tra tên/domain/path để browser không gửi session cookie của A tới B khi không chủ ý.
3. **Shared session:** nếu chia sẻ, A tạo session; B khôi phục đúng cùng ID và đọc được chỉ các attributes thuộc hợp đồng.
4. **Attribute ownership:** B không ghi hoặc xóa các key do A sở hữu theo quy tắc ứng dụng.
5. **Schema compatibility:** A ghi version hiện tại; B đọc; B ghi; A đọc; kiểm tra rolling version.
6. **Serialization rejection:** payload có type ID hoặc class không được phép phải bị từ chối an toàn.
7. **SecurityContext boundary:** đăng nhập A không tự động cấp quyền quản trị trong B nếu không có assertion/authority phù hợp.
8. **Logout:** A invalidate session; request mới qua B với ID cũ không được xác thực.
9. **Concurrent writes:** ép A và B cùng đọc rồi ghi các attributes khác nhau và cùng một attribute; kiểm tra bất biến.
10. **Expiration:** hoạt động ở một ứng dụng có làm gia hạn session chung không, và hành vi có đúng chính sách không?
11. **CSRF:** request thay đổi trạng thái tới từng ứng dụng phải có token/kiểm tra phù hợp.
12. **Event propagation:** nếu cần cleanup cross-node, xác nhận event được truyền và listener idempotent; mô phỏng subscriber offline.

Nên chạy test với hai application context thật cùng Testcontainers Redis/JDBC và cookie HTTP thực tế. Test chỉ dùng mock repository không xác minh cookie scope, serializer, key namespace hoặc quyền truy cập kho dữ liệu.

## 20. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| B luôn tạo session mới dù nhận cookie từ A | Cookie domain/path/name hoặc Redis namespace khác | Kiểm tra `Set-Cookie`, request cookie, namespace và repository |
| B đọc được session nhưng lỗi deserialize | Serializer hoặc DTO/class không tương thích | So sánh converter, class version và schema attributes |
| Đăng nhập A làm B coi người dùng là authenticated | SecurityContext bị chia sẻ mà chưa xác định trust boundary | Kiểm tra repository và chính sách xác thực/authorization của B |
| A sửa attribute nhưng B thấy dữ liệu cũ | Snapshot cache, flush timing hoặc request B đã tải trước khi A save | Đọc lại bằng request mới, kiểm tra SaveMode/FlushMode |
| A logout nhưng WebSocket ở B vẫn hoạt động | Event không được broadcast hoặc B không quản lý connection theo session | Kiểm tra event transport, registry và revocation check |
| Session bị kéo dài bởi hoạt động ở ứng dụng khác | Hai ứng dụng dùng chung inactivity timeout/last-access semantics | Xác định timeout chung hoặc tách session |
| Cookie bị gửi tới subdomain không mong muốn | Domain cookie quá rộng | Thu hẹp Domain/Path, tách cookie và đánh giá subdomain trust |
| Một ứng dụng ghi role khiến ứng dụng kia cấp quyền | Tin attribute không có nguồn xác thực | Dùng identity/authorization service và assertion có audience |

Khi điều tra, ghi nhận ứng dụng/node, namespace, loại thao tác và correlation ID. Không ghi session ID, cookie, SecurityContext payload hoặc token nguyên vẹn. Dùng metric tổng hợp và định danh đã che để tránh tạo thêm một kho dữ liệu nhạy cảm trong hệ thống log.

## 21. Quy trình ra quyết định và triển khai

1. Xác định mục tiêu là chia sẻ danh tính, chia sẻ một vài dữ liệu hay thật sự chia sẻ toàn bộ session.
2. Nếu chỉ cần SSO, ưu tiên OIDC và session riêng cho từng ứng dụng.
3. Nếu cần chia sẻ session, xác nhận các ứng dụng thuộc cùng miền tin cậy và có chủ sở hữu vận hành rõ ràng.
4. Cấu hình cùng repository, namespace, cookie name/domain/path, serializer và timeout.
5. Định nghĩa attribute contract có prefix, version, writer, reader, validation và retention.
6. Không chia sẻ SecurityContext hoặc authorities một cách ngầm định; xác định issuer/audience/scope và cơ chế thu hồi.
7. Giới hạn quyền Redis/JDBC; hiểu rằng ACL ở cấp key/table không nhất thiết cô lập từng attribute trong cùng session.
8. Kiểm thử CSRF, cookie scope, logout, expiration, concurrent writes và rolling compatibility.
9. Theo dõi lỗi deserialize, session miss, session size, cleanup và hành vi logout cross-application.
10. Có kế hoạch tách namespace/session nếu mức độ tin cậy hoặc vòng đời của ứng dụng thay đổi.

## 22. Tài liệu chính thức để đối chiếu

API và cấu hình thay đổi theo phiên bản Spring Session, Spring Security và Spring Data Redis. Khi triển khai, đối chiếu tài liệu đúng dòng đang dùng:

- [Spring Session — Redis configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — HttpSession integration](https://docs.spring.io/spring-session/reference/http-session.html)
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)

Chia sẻ session giữa nhiều ứng dụng là quyết định về ranh giới tin cậy, không chỉ là cấu hình cùng Redis và cookie. Khi cùng namespace và cùng session ID, mỗi ứng dụng có thể tác động tới trạng thái mà ứng dụng kia đọc. Hãy ưu tiên session riêng và SSO có protocol khi chỉ cần chia sẻ danh tính. Nếu bắt buộc chia sẻ, hãy đặc tả attribute contract, bảo vệ kho dữ liệu, giới hạn quyền, xác minh SecurityContext, xử lý ghi đồng thời và kiểm thử logout/expiration qua từng ứng dụng trước khi đưa vào production.
