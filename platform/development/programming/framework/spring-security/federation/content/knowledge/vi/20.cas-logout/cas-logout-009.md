# Kiểm chứng hành vi đăng xuất khi nhiều dịch vụ cùng có phiên hoạt động

Một người dùng có thể đăng nhập **CAS Single Sign-On (SSO)** một lần rồi sử dụng đồng thời nhiều ứng dụng, chẳng hạn **Portal A**, **Reports B** và **Admin C**. Mỗi ứng dụng thường tạo **HTTP session / SecurityContext riêng** sau khi xác minh service ticket (ST) của CAS Server. Do đó, một trang CAS hiển thị “Đã đăng xuất” **không tự chứng minh** các phiên A, B và C đã thực sự bị chấm dứt.

Với **CAS Single Logout (SLO)**, khi phiên SSO tại CAS Server kết thúc và SLO được cấu hình đúng, CAS cố gắng gửi **thông báo logout tới những CAS services đã tham gia phiên**. Mỗi service nhận thông báo phải tìm **đúng phiên ứng dụng liên quan đến service ticket** và hủy nó. Đây là cơ chế **best effort**: thông báo có thể bị lỗi mạng, gửi bất đồng bộ, front-channel bị chặn, hoặc ứng dụng không xử lý đúng. Bài học này tập trung vào cách **thiết kế và thực thi kiểm chứng end-to-end** khi nhiều service cùng có phiên hoạt động, bao gồm trường hợp callback đến trễ, một service offline, nhiều phiên cùng người dùng và API token tồn tại sau logout.

**Kết quả mong đợi:** biết phân biệt **local logout**, **CAS logout** và **CAS SLO**; dựng bài test nhiều dịch vụ; đối chiếu thông điệp `logoutRequest` theo **SessionIndex (service ticket ID)** với phiên local; xác minh trạng thái cuối ở **từng ứng dụng** thay vì chỉ nhìn redirect; phát hiện lỗi propagation và đưa ra chính sách bù trừ an toàn.

> **Nguyên tắc kiểm chứng:** "CAS Server đã hủy phiên SSO" là một sự kiện; "mỗi service đã hủy phiên ứng dụng tương ứng" là **nhiều sự kiện độc lập** cần được chứng minh. Một HTTP 200 hoặc trang logout thành công ở CAS không thay thế phép kiểm tra truy cập tài nguyên được bảo vệ tại A/B/C.

## 1. Các loại phiên cùng tồn tại trong một lần SSO

Giả sử người dùng `lan` mở cùng browser profile và truy cập:

- `https://portal.example.org` — **Service A**, ứng dụng Spring Boot.
- `https://reports.example.org` — **Service B**, một ứng dụng báo cáo.
- `https://admin.example.org` — **Service C**, ứng dụng quản trị.
- `https://sso.example.org/cas` — **CAS Server**, chịu trách nhiệm SSO.

Khi A/B/C nhận service ticket và xác minh thành công với CAS, mỗi service có thể sinh **cookie phiên local độc lập** (ví dụ `JSESSIONID` theo host/context path) cùng một `SecurityContext` tương ứng. CAS Server giữ **Ticket-Granting Ticket (TGT)** trong kho server, và browser có cookie CAS liên quan (thường gọi **TGC**).

| Đối tượng | Nơi quản lý | Hệ quả khi kết thúc | Không nên nhầm với |
| --- | --- | --- | --- |
| CAS TGT / phiên SSO | CAS Server | Lần vào service mới có thể cần xác thực lại; CAS có thể phát SLO notifications. | `JSESSIONID` của A/B/C. |
| Cookie CAS / TGC | Browser và CAS Server | Browser không còn SSO theo phiên TGT đó. | Cookie local của từng service. |
| ST của Service A | CAS Server phát, A xác minh | Ràng buộc một giao dịch login vào A; thông tin này còn hữu ích cho SLO correlation. | TGT hoặc local session ID. |
| ST của Service B/C | CAS Server phát riêng cho B/C | Tương ứng từng lần login tại B/C. | ST của A, dù cùng username. |
| HTTP session tại A | Servlet container / Spring Session của A | Quyền truy cập A trong phiên đó chấm dứt khi invalidate. | Phiên CAS Server hoặc B. |
| HTTP session tại B | Service B | Chỉ phiên B bị thay đổi khi B xử lý logout. | Phiên A và C. |
| HTTP session tại C | Service C | Chỉ phiên C bị thay đổi khi C xử lý logout. | Phiên A và B. |
| Access token / API session riêng | Authorization Server / Resource Server | Có thể vẫn còn hiệu lực theo TTL/revocation riêng. | CAS SLO tự động chấm dứt mọi bearer token. |

**Không có một `HttpSession` chung giữa các ứng dụng** chỉ vì người dùng cùng đăng nhập qua CAS. Cũng không có một giả định rằng `logoutRequest` sẽ xóa mọi phiên mang cùng username trên mọi thiết bị.

### 1.1. Trạng thái ví dụ trước logout

~~~text
CAS:
  TGT-SESSION-1 (user=lan, active=true)
    visited services:
      A -> ST-A1
      B -> ST-B1
      C -> ST-C1

Service A:
  ST-A1 -> HttpSession A-S1 -> Authentication(lan) [ACTIVE]

Service B:
  ST-B1 -> HttpSession B-S1 -> Authentication(lan) [ACTIVE]

Service C:
  ST-C1 -> HttpSession C-S1 -> Authentication(lan) [ACTIVE]
~~~

Những ID chỉ mang tính **minh họa**, không phải ticket/cookie thật. Sau CAS SLO thành công, **từng session A-S1, B-S1, C-S1** phải không còn được phép truy cập tài nguyên bảo vệ. Một service có thể duy trì **nhiều local sessions** cho cùng subject, ví dụ hai trình duyệt hoặc hai CAS TGT khác nhau; SLO phải nhắm đúng session được CAS báo, không tự xóa mọi session của user nếu chính sách không cho phép.

## 2. Ba kiểu logout cần kiểm chứng riêng

| Hành động | Sự kiện xảy ra ở đâu | Kết quả tối thiểu | Có tự ảnh hưởng service khác? |
| --- | --- | --- | --- |
| **Local logout tại A** | `POST /logout` của Spring Security A | Xóa `SecurityContext`, invalidate session A theo cấu hình. | **Không** mặc định: CAS TGT và session B/C có thể vẫn sống. |
| **CAS logout** | Browser truy cập CAS `/logout` qua flow hợp lệ | CAS hủy phiên SSO/TGT tương ứng. | **Không đảm bảo** B/C bị hủy trừ khi SLO được bật và thông báo được xử lý. |
| **CAS Single Logout (SLO)** | CAS phát logout requests cho services đã đăng nhập trong TGT | Mỗi service nhận và invalidate đúng local session đã ánh xạ. | Có thể lan tới A/B/C, nhưng **best effort** và phụ thuộc từng service. |
| **Logout bởi expiration/timeout** | CAS hoặc local session đến hạn | CAS/client có thể có hành vi SLO theo policy/version. | **Không đồng nhất** với người dùng chủ động CAS logout; phải test riêng. |
| **Logout upstream IdP/broker** | Hệ thống upstream OIDC/SAML khác | Kết thúc phiên upstream theo protocol tương ứng. | Không thể mặc nhiên dùng CAS SLO để suy ra upstream/downstream logout. |

Nếu người dùng bấm logout tại A, ứng dụng có thể hiển thị lựa chọn **“Đăng xuất ứng dụng này”** và **“Đăng xuất khỏi hệ thống CAS”**. Hai lựa chọn cần URL, kỳ vọng và thông báo UI rõ. Nếu A chỉ logout local nhưng CAS TGT còn sống, khi browser quay lại A và bị redirect CAS login, CAS có thể lập tức cấp **ST mới** mà không yêu cầu nhập mật khẩu. Đây là hành vi SSO hợp lệ, **không chứng minh local logout thất bại**.

### 2.1. Tại sao nút logout tại CAS không đủ?

SLO là cơ chế **thông báo**: CAS Server chủ động liên hệ những services đã ghi nhận; mỗi service phải **xử lý thông điệp** để hủy session. Hãy phân biệt:

~~~text
TGT destroyed               -- CAS Server xác nhận
SLO message for A created    -- CAS Server điều phối
SLO POST A accepted          -- có network delivery tới A
A mapped SessionIndex=ST-A1 -- A tìm đúng local session
A invalidated A-S1           -- phiên A đã bị hủy
A GET /private returns 401/redirect CAS -- người dùng không còn quyền trong A-S1
~~~

Chỉ bước cuối và bằng chứng local liên quan mới chứng minh người dùng **không còn truy cập được A bằng phiên cũ**. Ở B/C phải có chuỗi kiểm chứng tương tự. Nếu browser tự động SSO lại khi test, có thể nhầm một **session mới sau logout** với session cũ vẫn còn; phải đối chiếu ticket/session generation/timestamps.

## 3. CAS SLO: server gửi yêu cầu tới nhiều services như thế nào?

Theo CAS Protocol và tài liệu Apereo CAS, khi TGT được **chủ động hủy** (và có thể khi timeout theo khả năng cấu hình), CAS tìm các service tickets đã phát trong phiên đó, rồi gửi thông báo Single Logout cho các service tương ứng. Ở **back-channel SLO**, CAS Server thường gửi một HTTP POST trực tiếp tới service; ở **front-channel**, CAS có thể dùng browser/AJAX/iframe theo CAS Server và client.

### 3.1. Back-channel: ví dụ ba thông báo độc lập

~~~text
                    CAS Server /logout
                      | destroy TGT-SESSION-1
             +--------+---------+
             |        |         |
         POST A    POST B     POST C
         ST-A1     ST-B1      ST-C1
             |        |         |
        A session  B session   C session
        A-S1 gone  B-S1 gone   C-S1 gone
~~~

Các thông báo có thể được gửi **bất đồng bộ**. A có thể nhận trước C, B nhận trễ hoặc offline. Không được kỳ vọng rằng ngay tại millisecond browser được redirect khỏi CAS, cả ba service đã xử lý xong.

### 3.2. LogoutRequest trông như thế nào?

Ví dụ **CAS SLO message** dùng XML với cấu trúc tương tự SAML LogoutRequest:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout-unique-1"
    Version="2.0"
    IssueInstant="2026-11-07T04:00:00Z">
  <saml:NameID>lan</saml:NameID>
  <samlp:SessionIndex>ST-A1</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

Trong **CAS SLO protocol**, `SessionIndex` thường chính là **service ticket ID** đã được ứng dụng dùng khi login, **không phải CAS TGT ID, không phải servlet `JSESSIONID` và không phải `AuthnStatement SessionIndex` của một SAML SSO federation riêng**.

Ví dụ POST (biểu diễn rút gọn, chỉ mô phỏng transport):

~~~http
POST /login/cas HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

logoutRequest=<url-encoded-xml-logout-request>
~~~

Dòng `logoutRequest` trên là **ký hiệu**. Khi client xử lý thật, CAS library chịu trách nhiệm trích và parse thông điệp theo phiên bản. Không lấy chuỗi XML do một browser tự gửi tới `/logout` rồi coi là đủ quyền invalidate phiên người khác.

**Đặc biệt:** mặc dù dùng XML element names trong SAML namespace, **CAS back-channel SLO không đồng nghĩa với đầy đủ SAML 2.0 SLO profile có chữ ký và trust metadata**. Phải áp dụng các điều kiện xác thực nguồn thông báo phù hợp với CAS deployment: HTTPS, đường mạng tin cậy, endpoint ACL/mTLS/gateway khi cần, replay protection và xử lý thư viện chuẩn.

### 3.3. Mỗi service xác định đúng local session bằng gì?

Điều đúng:

~~~text
CAS logoutRequest SessionIndex = ST-A1
             |
             v
Service A CAS Client mapping:
  key   = ST-A1
  value = HttpSession A-S1
             |
             v
A invalidates A-S1 (not B-S1/C-S1)
~~~

Điều sai:

~~~text
logoutRequest NameID = lan
  -> service A delete ALL sessions username "lan"
~~~

Một tài khoản có thể đang hoạt động tại **hai browser profiles** với **hai TGT độc lập**. Xóa tất cả các session theo username khi chỉ một TGT bị hủy có thể đăng xuất sai các thiết bị còn lại; tệ hơn, nếu thông báo bị giả mạo, attacker có thể làm gián đoạn mọi phiên của nạn nhân. **Định danh correlation ở SLO là service ticket ID → local HttpSession**, không phải tên người dùng.

## 4. Cơ chế Spring Security và Apereo Java CAS Client

Các thành phần quan trọng trong ứng dụng Servlet:

| Thành phần | Vai trò khi logout |
| --- | --- |
| **`CasAuthenticationFilter`** | Xử lý CAS service ticket callback để Spring Authentication thành công. |
| **`CasAuthenticationProvider`** | Xác minh ST qua `TicketValidator`; nạp user authorities. |
| **`SingleSignOutFilter`** (`org.apereo.cas.client.session.SingleSignOutFilter`) | Nhận CAS logoutRequest, tìm session cần hủy; đồng thời tham gia lưu mapping khi login. |
| **`SingleSignOutHttpSessionListener`** | Dọn mapping khi servlet `HttpSession` bị hủy/hết hạn, tránh reference cũ. |
| **`SessionMappingStorage` / `SessionMappingStorageImpl`** | Map giữa **service ticket ID** và HttpSession của service. |
| **Spring Security `LogoutFilter`** | Xử lý logout do ứng dụng kích hoạt, gọi logout handlers/clear SecurityContext. |
| **`SecurityContextRepository`** | Giữ/khôi phục Authentication của ứng dụng theo request/session. |
| **Spring Session** (khi dùng) | Quản lý session qua store phân tán và xử lý expiration/invalidation phù hợp. |

### 4.1. Bộ lọc SLO cần chạy đúng thứ tự

Tài liệu Apereo Java CAS Client thường cấu hình `SingleSignOutFilter` ở **container filter chain** và `SingleSignOutHttpSessionListener` ở servlet listener:

~~~xml
<!-- Ví dụ rút gọn trong web.xml; áp dụng cho container hỗ trợ Servlet listener. -->
<filter>
  <filter-name>CAS Single Sign Out Filter</filter-name>
  <filter-class>org.apereo.cas.client.session.SingleSignOutFilter</filter-class>
</filter>
<filter-mapping>
  <filter-name>CAS Single Sign Out Filter</filter-name>
  <url-pattern>/*</url-pattern>
</filter-mapping>
<listener>
  <listener-class>
    org.apereo.cas.client.session.SingleSignOutHttpSessionListener
  </listener-class>
</listener>
~~~

**Đây là cấu hình minh họa**, không phải `web.xml` hoàn chỉnh. Khi dùng Spring Boot embedded servlet container, việc đăng ký `FilterRegistrationBean` và `ServletListenerRegistrationBean` (hoặc cơ chế listener/filter có hỗ trợ tương đương) phải đảm bảo **CAS logout callback đi qua filter**, filter được khởi tạo sớm đúng pipeline, và listener được container gọi. Không đăng ký hai bản `SingleSignOutFilter` xử lý cùng request; tránh double registration/duplicate invalidation.

Điểm cần test: **`SingleSignOutFilter` phải nhìn thấy yêu cầu CAS ST login để ghi mapping và yêu cầu CAS SLO để xóa mapping**. Nếu filter chỉ được map tới `/cas/logout` nhưng ticket callback thật là `/login/cas`, có thể nó không bao giờ ghi được mapping. Nếu Spring Security chặn callback POST trước khi filter xử lý, CAS Server nhận 403 và phiên không bị hủy.

### 4.2. SLO và Spring Security logout không phải một handler

Spring Security local logout thường được cấu hình:

~~~java
http.logout(logout -> logout
    .logoutUrl("/logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true));
~~~

Đây là **mảnh cấu hình bên trong `SecurityFilterChain`**, không phải chương trình chạy độc lập; tùy CSRF config, browser phải gửi **POST** tới local `/logout`. Nó chỉ đảm bảo **local** logout theo Spring Security policy, **không tự bắt CAS back-channel SLO** và không tự gửi browser đến CAS `/logout`.

Ngược lại, `SingleSignOutFilter` cần **lấy được logoutRequest từ CAS** rồi gọi invalidation cho đúng session, không cần browser đang mở trang A. **CAS server-side SLO có thể hủy A-S1 ngay cả khi browser đang đứng tại tab B**.

### 4.3. Session fixation protection và mapping sau login

Spring Security có thể đổi **session ID** sau authentication (session fixation protection). Nếu CAS Client mapping giữ reference `HttpSession` nhưng storage/container thay ID, hoặc callback đến đúng lúc session đổi, test phải xác minh mapping **vẫn tìm được session sống thực tế**. Không tắt session fixation protection chỉ để “SLO hoạt động”; cần kiểm thử phiên bản Spring Security/Servlet container và CAS Client thực tế.

Nếu session được **invalidate và tạo một session hoàn toàn mới** thay vì chỉ đổi ID, mapping cũ có thể chỉ đến session đã hủy. Cần đảm bảo listener/management lifecycle và đăng ký mapping cho đúng phiên còn sống. Không suy từ một lần callback 200 rằng session được hủy khi lưu reference sai.

### 4.4. Spring Security session không tồn tại nếu app dùng JWT/BFF khác

Nếu service B là SPA hoặc API server sử dụng bearer token stateless, không có `HttpSession` tương đương với service ticket. `SingleSignOutFilter` không thể tự thu hồi mọi JWT đã phát. B cần thiết kế **session registry/token revocation/introspection/version check/short token TTL** riêng. Không gắn tên “CAS SLO” cho OIDC Back-Channel Logout hoặc SAML SLO: **các giao thức khác nhau có logout message, correlation và trust rules khác nhau**.

## 5. Cấu hình SLO ở CAS Server: phạm vi theo từng service

Apereo CAS cho phép cấu hình Single Logout ở **registered service**. Các cài đặt liên quan tùy phiên bản bao gồm:

| Khía cạnh | Điều phải xác minh |
| --- | --- |
| CAS Server có bật SLO không? | Một số version mặc định bật; không suy đoán từ UI, kiểm tra runtime và service registry. |
| **`logoutType`** | `BACK_CHANNEL`, `FRONT_CHANNEL` hoặc không gửi thông báo (`NONE`/tương đương tùy phiên bản). |
| **`logoutUrl`** | Có thể đưa callback tới endpoint khác với `service` được sử dụng khi cấp ST; phải cấu hình riêng và test URL đó. |
| **Logout propagation** | Async/sync, thread pool/queue/retry và thứ tự; không dựa vào một SLA giả định. |
| Front-channel mode | JSONP/AJAX/iframe và khả năng client/browser hỗ trợ. |
| Service registry | ST phải thuộc service đã đăng ký, URL public HTTPS đúng proxy/ingress. |
| CAS SSO session lifecycle | Explicit logout, TGT expiration, idle timeout, global logout policy. |
| Upstream federation | Nếu CAS làm broker cho OIDC/SAML, từng giao thức có logout logic riêng. |

Ví dụ rút gọn **service registration ở CAS Server**:

~~~json
{
  "@class": "org.apereo.cas.services.CasRegisteredService",
  "serviceId": "^https://portal[.]example[.]org/login/cas$",
  "name": "portal",
  "id": 1001,
  "logoutType": "BACK_CHANNEL",
  "logoutUrl": "https://portal.example.org/login/cas"
}
~~~

**Đây là JSON minh họa**; schema, regex escaping, `@class` và field values phải được xác thực với **CAS Server version/service registry implementation** đang dùng. Không copy trực tiếp lên CAS production hoặc coi mọi release cho phép cùng cấu trúc. Nếu dùng `logoutUrl` riêng, endpoint phải trỏ tới nơi có SLO filter/handler, **không** chỉ là trang HTML “logout successful”.

### 5.1. Back-channel: thích hợp cho server-side services nhưng không phải delivery bảo đảm tuyệt đối

**Back-channel SLO** gửi POST trực tiếp từ CAS Server tới service, không phụ thuộc người dùng còn giữ tab service hay third-party cookie browser. Nhưng nó phụ thuộc **network, DNS, certificate/TLS, service availability, firewalls, authentication của endpoint, message parsing, storage mapping và internal session store**.

CAS Server có thể gửi thông báo **asynchronously** và bỏ qua lỗi delivery để không làm chậm logout CAS. Vì vậy **CAS /logout HTTP 200 không chứng minh B đã nhận callback**. Cần metric/delivery outcome theo service và kiểm tra bằng request thực tế với cookie session cũ.

### 5.2. Front-channel: quan sát browser và CSP/iframe

**Front-channel SLO** dựa vào browser để chuyển/tiếp nhận thông báo, có thể là AJAX JSONP hoặc iframe tùy CAS Server. Nó có thể bị ảnh hưởng bởi **browser privacy settings, CSP, third-party cookie policy, mixed content, network, tab closed** hoặc client không hỗ trợ. Không tự giả định front-channel “mạnh hơn” chỉ vì browser thấy nhiều trang; phải test từng browser hiện đại và client version.

Với service thuần server-side Spring Security, **back-channel** thường dễ quan sát hơn; front-channel phù hợp chỉ khi yêu cầu/triển khai thực sự hỗ trợ. Không trộn cơ chế CAS front-channel với **OpenID Connect Front-Channel Logout** dù tên giống nhau.

### 5.3. Điều kiện “đã tham gia phiên SSO”

CAS thông thường chỉ biết service đã **được cấp ST/ghi nhận trong TGT**. Một ứng dụng có thể nhận login từ local account không đi qua CAS, một browser khác hoặc một IdP khác; CAS SLO **không thể tự biết** và xóa những phiên không liên quan.

Vì vậy test baseline cần chắc chắn A/B/C đều được đăng nhập **bằng cùng một CAS TGT**, đúng CAS Server, không phải đơn thuần cùng username. Có thể dùng browser profile mới, dọn cookie từ test, ghi lại identity correlation ở test server và kiểm tra CAS audit đã phát ST riêng từng service.

## 6. Thiết kế bài test: ba service, một TGT, ba phiên local

### 6.1. Tiền điều kiện

Chuẩn bị môi trường **staging/test** với CAS Server và ba services A/B/C. Đảm bảo:

1. Mỗi service có **URL public HTTPS**, được CAS service registry cho phép.
2. CAS Server cấu hình **SLO BACK_CHANNEL** (hoặc mode cụ thể đang cần test) cho cả ba.
3. Cả ba có CAS Client/Spring Security integration xử lý logoutRequest.
4. Ở mỗi service, một endpoint có bảo vệ, ví dụ `GET /private/whoami`, trả **200 kèm user/session generation** nếu đã đăng nhập; nếu chưa đăng nhập trả **401/403** hoặc **302 tới CAS login**. Không gán nghĩa cứng 302=logout, phải xem đích chuyển hướng.
5. Có audit/metric đã che ST/cookie, đủ để biết service được CAS gọi, mapping được tìm, session bị invalidate, và request tiếp theo có còn quyền không.
6. Có thể dùng **cùng một browser profile** hoặc automation với một cookie jar cho CAS và từng service; không xóa toàn bộ cookies ngay trước khi kiểm chứng session ở từng ứng dụng.
7. Các đồng hồ đồng bộ ở mức hợp lý (NTP), có correlation IDs và dấu mốc timestamp cho cuộc test.
8. Có quyền kiểm soát kết nối để test service B offline/latency trong môi trường này.

**Không chạy logout thử trên người dùng/tổ chức production thật.** Những phiên cần kiểm tra phải là tài khoản test được phép.

### 6.2. Thiết lập trạng thái ban đầu

~~~text
User: lan (cùng browser profile)
CAS TGT: TGT-1

Visit A -> CAS issues ST-A1 -> A validates -> HttpSession A-S1
Visit B -> CAS issues ST-B1 -> B validates -> HttpSession B-S1
Visit C -> CAS issues ST-C1 -> C validates -> HttpSession C-S1

Verify before logout:
  GET A/private/whoami with A cookie -> authenticated lan
  GET B/private/whoami with B cookie -> authenticated lan
  GET C/private/whoami with C cookie -> authenticated lan

Record privately:
  correlation test-run = slo-20261107-001
  A session generation (non-secret ref)
  B session generation
  C session generation
  CAS audit references for ST-A1/ST-B1/ST-C1 (hashed)
~~~

Không cần đưa raw service tickets hoặc `JSESSIONID` vào báo cáo test; các references đã HMAC/hash bằng key audit riêng thường đủ để đối chiếu.

### 6.3. Kích hoạt CAS logout đúng cách

Browser test kích hoạt CAS `/logout` theo cơ chế đã đăng ký, hoặc một nút “Đăng xuất toàn hệ thống” tại A **được cấu hình chính thức** để chuyển đến CAS logout. Nếu có post-logout redirect, phải dùng URL đã được CAS server cho phép; không nhận `service=https://attacker.example` tùy ý từ client.

CAS Server hủy TGT-1 và điều phối thông báo cho A/B/C. Sau đó:

- Kiểm tra **CAS TGT thật sự hết hiệu lực**.
- Theo dõi **callback A**, **callback B**, **callback C** riêng; không kết luận “tất cả xong” khi mới thấy A.
- Đợi theo **timeout/SLA test được thiết kế trước**, không đoán 100 ms là đủ cho mọi callback async.
- Dùng **cookie session cũ của từng service** gọi endpoint bảo vệ với **không tự follow login redirects** để đo quyền trong phiên hiện có.
- Nếu API tự redirect qua CAS rồi tự đăng nhập lại, phải phân biệt **old session denied** với **new session issued**; ở bài test này TGT đã bị hủy nên new login thường yêu cầu primary authentication.

### 6.4. Acceptance criteria

| Kiểm chứng | PASS khi |
| --- | --- |
| CAS TGT | TGT-1 bị hủy; không còn cấp ST mới qua SSO im lặng từ TGT-1. |
| SLO dispatch | CAS tạo thông báo đúng service A/B/C của TGT-1, không thiếu service được kỳ vọng. |
| Delivery | HTTP request đi tới endpoint cấu hình của A/B/C, không bị 404/403/timeout. |
| Session correlation | A nhận ST-A1, B nhận ST-B1, C nhận ST-C1 trong `SessionIndex`; không dùng username để xóa. |
| Local invalidation | A-S1, B-S1, C-S1 bị invalidated hoặc không còn authentication hợp lệ. |
| Authorization recheck | Dùng **cookie cũ** truy cập protected resources ở cả A/B/C **không được 200 với quyền cũ**. |
| Không ảnh hưởng ngoài phạm vi | Phiên thuộc **TGT khác** hoặc user khác không bị SLO này xóa sai. |
| Bằng chứng | Audit theo từng service nêu event, mapping, invalidate, kiểm chứng truy cập và kết luận. |

**Đặc biệt:** đôi khi `/private/whoami` trả 200 từ **HTTP cache/service worker** sau logout. Test phải đặt `Cache-Control: no-store` cho endpoint bảo vệ, tắt cache tại test client và xác minh server đã xử lý request, tránh xem nội dung từ cache là một phiên đang sống. Ngược lại, một UI vẫn hiển thị tên user không tự chứng minh backend còn truy cập được.

## 7. Ma trận tình huống: local logout, CAS logout, một service lỗi

| Tình huống | CAS TGT | Session A | Session B | Session C | Kết luận |
| --- | --- | --- | --- | --- | --- |
| Chưa logout | ACTIVE | ACTIVE | ACTIVE | ACTIVE | Baseline. |
| Chỉ local logout tại A | ACTIVE | CLOSED | ACTIVE | ACTIVE | **Không phải SLO**. |
| Truy cập lại A ngay sau local logout | ACTIVE | Có thể NEW LOGIN nhờ CAS SSO | ACTIVE | ACTIVE | Xác thực phiên mới, không phải phục hồi phiên cũ. |
| CAS logout + SLO mọi service thành công | CLOSED | CLOSED | CLOSED | CLOSED | **SLO E2E PASS**. |
| CAS logout, B offline | CLOSED | CLOSED | Có thể còn ACTIVE | CLOSED | **PARTIAL SLO**, cần cảnh báo/giảm thiểu. |
| CAS logout, C không cài SLO filter | CLOSED | CLOSED | CLOSED | Có thể còn ACTIVE | **PARTIAL SLO**, lỗi client/config. |
| CAS logout nhưng service registry `logoutType=NONE` ở B | CLOSED | CLOSED | ACTIVE | CLOSED | B nằm ngoài propagation theo policy; không đạt kỳ vọng logout toàn hệ thống. |
| CAS front-channel bị browser chặn tại C | CLOSED | CLOSED | CLOSED | Có thể còn ACTIVE | Phụ thuộc browser/client, phải test riêng. |
| CAS logout sau khi session A đã timeout | CLOSED | Đã CLOSED | CLOSED | CLOSED | Callback A có thể không tìm mapping; idempotent/no-op, không coi là xóa user khác. |
| A và B cùng username nhưng browser/TGT khác | CLOSED TGT-1 | Phiên từ TGT-1 CLOSED | Phiên từ TGT-2 vẫn ACTIVE | Theo scope | Không logout theo username. |
| CAS SLO nhận callback trùng | CLOSED | CLOSED | CLOSED | CLOSED | Duplicate phải an toàn, không tạo phiên. |
| CAS logout nhưng service API có JWT độc lập | CLOSED | Session web CLOSED | API JWT có thể vẫn hợp lệ | Tuỳ policy | SLO chưa đủ cho mọi bearer tokens. |

**Bảng là kỳ vọng test trong kiến trúc đã nêu, không phải lời đảm bảo mọi bản CAS Server/Client có hành vi mặc định y hệt.** Phải kiểm tra mode, protocol, service registry, session store và logout policy thật.

### 7.1. Không lẫn hai dấu hiệu “service B trả 200”

Một B callback POST **HTTP 200** chỉ cho thấy endpoint đã xử lý hoặc ACK request; nó có thể là 200 từ controller không hủy session. Phải có bằng chứng B đã tìm đúng ST, invalidate session, rồi request với cookie B cũ không còn quyền. Nếu endpoint callback trả 200 mà mapping miss, cần log `NO_MATCH`/metric và đánh giá; không đánh đồng với `INVALIDATED`.

## 8. Java 17 runnable: mô phỏng bốn phiên và một callback bị thất lạc

Chương trình dưới đây sử dụng **Java 17 thuần**, mô phỏng ba services A/B/C và một phiên thứ hai ở A. Nó cho thấy local logout tại A không ảnh hưởng B/C, CAS SLO cho cùng TGT phải nhắm **đúng ST**, và B offline tạo **partial logout** cho tới khi B xử lý notification.

**Ranh giới ví dụ:** phương thức `receiveSlo` chỉ được gọi **sau khi** một CAS Client/Filter thực đã xác minh nguồn thông báo ở tầng transport/trust và trích `SessionIndex`. Chương trình không tạo ticket thật, không parse XML, không xác thực CAS Server, không xử lý HttpSession hay CAS filter. Các `ST-...` là identifier giả phục vụ minh họa mapping.

Tệp **`CasMultiServiceLogoutDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class CasMultiServiceLogoutDemo {

    record LocalSession(String id, String username) {}

    static final class Service {
        private final Map<String, LocalSession> byTicket =
                new HashMap<>();
        private final Map<String, String> ticketBySession =
                new HashMap<>();

        synchronized void login(String serviceTicket,
                                String localSessionId, String username) {
            if (byTicket.containsKey(serviceTicket)
                    || ticketBySession.containsKey(localSessionId)) {
                throw new IllegalStateException("Duplicate mapping");
            }
            byTicket.put(serviceTicket,
                    new LocalSession(localSessionId, username));
            ticketBySession.put(localSessionId, serviceTicket);
        }

        synchronized void localLogout(String localSessionId) {
            String ticket = ticketBySession.remove(localSessionId);
            if (ticket != null) {
                byTicket.remove(ticket);
            }
        }

        // Trusted CAS client gọi sau khi xác định SessionIndex.
        synchronized String receiveSlo(String serviceTicket) {
            LocalSession session = byTicket.remove(serviceTicket);
            if (session == null) {
                return "NO_MATCH";
            }
            ticketBySession.remove(session.id());
            return "INVALIDATED";
        }

        synchronized boolean active(String localSessionId) {
            return ticketBySession.containsKey(localSessionId);
        }
    }

    public static void main(String[] args) {
        Service a = new Service();
        Service b = new Service();
        Service c = new Service();

        // TGT-1: một browser đã đăng nhập ở cả A, B, C.
        a.login("ST-A1", "A-S1", "lan");
        b.login("ST-B1", "B-S1", "lan");
        c.login("ST-C1", "C-S1", "lan");

        // TGT-2: browser khác, cùng username nhưng phiên riêng ở A.
        a.login("ST-A2", "A-S2", "lan");

        System.out.println("BEFORE="
                + (a.active("A-S1")
                   && b.active("B-S1")
                   && c.active("C-S1")));

        // Chỉ logout tại A: CAS TGT-1 và B/C vẫn còn.
        a.localLogout("A-S1");
        System.out.println("LOCAL=" + a.active("A-S1")
                + "," + b.active("B-S1")
                + "," + c.active("C-S1"));

        // A có thể đăng nhập lại bằng CAS SSO TGT-1 còn sống.
        a.login("ST-A3", "A-S3", "lan");
        System.out.println("SSO_RELOGIN=" + a.active("A-S3"));

        // CAS hủy TGT-1, gửi callback tới A và C trước.
        // B bị offline; CAS callback tới B chưa được xử lý.
        System.out.println("SLO_A=" + a.receiveSlo("ST-A3"));
        System.out.println("SLO_C=" + c.receiveSlo("ST-C1"));
        System.out.println("PARTIAL=" + a.active("A-S3")
                + "," + b.active("B-S1")
                + "," + c.active("C-S1"));

        // Giả định hệ thống retry/reconcile đã đưa notification tới B.
        System.out.println("B_RECOVERY=" + b.receiveSlo("ST-B1"));
        System.out.println("B_DUPLICATE=" + b.receiveSlo("ST-B1"));

        // TGT-2 độc lập: cùng user không bị hủy theo username.
        System.out.println("OTHER_BROWSER=" + a.active("A-S2"));

        // Một service không được consume ST của service khác.
        System.out.println("WRONG_SERVICE=" + a.receiveSlo("ST-B1"));
    }
}
~~~

Chạy:

~~~bash
javac CasMultiServiceLogoutDemo.java
java CasMultiServiceLogoutDemo
~~~

**Stdout chính xác:**

~~~text
BEFORE=true
LOCAL=false,true,true
SSO_RELOGIN=true
SLO_A=INVALIDATED
SLO_C=INVALIDATED
PARTIAL=false,true,false
B_RECOVERY=INVALIDATED
B_DUPLICATE=NO_MATCH
OTHER_BROWSER=true
WRONG_SERVICE=NO_MATCH
~~~

Giải thích:

1. Một CAS TGT hỗ trợ phiên ở **ba services**.
2. Local logout ở A chỉ hủy `A-S1`, B/C vẫn `ACTIVE`.
3. CAS TGT còn cho phép A có login mới `ST-A3` (mô phỏng).
4. Khi CAS SLO chỉ đến A/C, B vẫn active: **partial logout**.
5. Khi B thực sự nhận notification, `B-S1` bị hủy; callback lặp `ST-B1` là **NO_MATCH** và không làm gì thêm.
6. Phiên `A-S2` thuộc TGT khác nhưng cùng username vẫn active, chứng minh **không logout theo username**.
7. A không nhận `ST-B1` làm session của chính mình.

**Cảnh báo:** đoạn `B_RECOVERY` mô phỏng một **notification cuối cùng đến B**. Không được hiểu rằng CAS Server chắc chắn retry hoặc có một queue bền mặc định; hành vi retry/async tùy CAS Server và triển khai. **Hệ thống production phải có kế hoạch** giám sát, retry có kiểm soát/đối soát hoặc timeout/revocation theo SLA. `HashMap` của demo không đại diện cho `HttpSession` thật, không có mạng, auth, token revocation, TTL và không dùng cho production.

### 8.1. Vì sao không hủy theo username?

Hai browser profiles có thể cùng `lan` nhưng thuộc **TGT-1** và **TGT-2**. SLO của TGT-1 chỉ gửi ST IDs thuộc TGT đó; việc xóa mọi session `lan` ở A/B/C sẽ làm đăng xuất cả TGT-2, sai ranh giới. Một số tổ chức có chính sách **global account revocation** (khóa user toàn thiết bị); đó là **policy khác**, cần phát tín hiệu có xác thực và thực thi riêng, không được giả mạo là CAS SLO mặc định.

### 8.2. Giới hạn chứng minh của unit test

Chương trình chỉ chứng minh thuật toán mapping, không chứng minh:
- CAS Server đã gửi logoutRequest đúng service.
- XML/transport được CAS Client xác minh hợp lệ.
- `SingleSignOutFilter` thực sự nằm trước Spring Security chain.
- Session fixation rotation và session store vẫn cho lookup đúng.
- HTTP 200 của callback đồng nghĩa session invalidation.
- Cookies cũ ở browser không còn quyền.
- SLO partial được phát hiện đúng trong mạng đa node.

Cần **integration test + browser/E2E test** như các phần tiếp theo.

## 9. Kiểm thử end-to-end: phương pháp quan sát đáng tin

### 9.1. Với browser tự động

Dùng Playwright/Selenium hoặc trình duyệt thực với một browser context chứa CAS cookie và các cookies service. Test flow gợi ý:

~~~text
1. Login A qua CAS -> GET A/private -> 200 authenticated
2. Visit B          -> GET B/private -> 200 authenticated
3. Visit C          -> GET C/private -> 200 authenticated

4. Snapshot:
   A local session ref, B session ref, C session ref
   CAS ST correlation references; TGT test reference

5. Browser performs CAS /logout.
6. Collect:
   CAS dispatch events to A/B/C,
   A/B/C callback status,
   A/B/C session-invalidation events.

7. Reuse ORIGINAL service cookies:
   A/private -> no old authentication
   B/private -> no old authentication
   C/private -> no old authentication

8. Verify protected WRITE endpoints also reject old state.
9. Verify browser with independent TGT/session is unchanged.
~~~

Thao tác “reuse original cookies” cần cẩn thận: browser vẫn có cookies nhưng server có thể đã invalidated chúng; đó là điều muốn kiểm thử. Không xóa tất cả cookies local trước bước 7, vì như vậy kết quả “không còn quyền” chỉ chứng minh **client tự xóa cookies**, không chứng minh CAS SLO đã hủy session ở server.

### 9.2. Phân biệt response 401/403/302

| Response khi gọi tài nguyên bảo vệ | Cách hiểu |
| --- | --- |
| **401** | Người gọi chưa xác thực với API, thường phù hợp khi old session đã mất. |
| **302 tới CAS login** | Spring web app nhận anonymous và yêu cầu đăng nhập lại; thường phù hợp logout, **nhưng cần xác minh không auto SSO lại**. |
| **403** | Có thể do đã xác thực nhưng thiếu quyền, hoặc CSRF/authorization failure; không tự coi là logout. |
| **200 từ endpoint protected** | Cần xem đó có phải response thật từ server và danh tính thuộc **old session** hay session mới. |
| **200 từ trang `/logout-success`** | Chỉ xác nhận UI, không chứng minh session A/B/C đã hủy. |
| **304/200 từ cache** | Có thể là dữ liệu cũ; tắt cache/kiểm tra server-side. |

Một yêu cầu `GET /private` trả 302 là **tín hiệu**, không phải toàn bộ chứng cứ. Với các endpoint kiểm tra audit, ưu tiên trả 200 kèm một **session generation test-only** không nhạy cảm, hoặc trả 401 từ API, để có thể phân biệt session cũ/mới.

### 9.3. Kiểm tra request đồng thời khi callback đến trễ

Tạo một request tới B đúng lúc CAS đang dispatch SLO:

- Request B bắt đầu **trước** khi B session invalidation commit có thể hoàn thành dưới quyền cũ nếu không có cơ chế hủy request đang chạy.
- Request B bắt đầu **sau** khi session invalidation commit phải không còn quyền dựa trên session B cũ.
- Nếu business case yêu cầu thu hồi quyền **ngay lập tức ở mọi request đang chạy**, CAS SLO đơn thuần không đủ. Cần policy/hệ thống **revocation epoch**, check tại critical operation, hoặc session registry có hiệu lực trên API.

Không đặt yêu cầu phi thực tế “mọi request đã bắt đầu trước logout đều rollback” trừ khi hệ thống có transaction/revocation semantics rõ.

## 10. Test lỗi từng phần và giới hạn của “best effort”

### 10.1. Service B offline

Kịch bản:

1. A/B/C cùng dùng TGT-1.
2. Trước khi CAS logout, cho B unreachable hoặc chặn đường CAS → B trong staging.
3. CAS nhận logout, gửi callback A/C thành công, B thất bại.
4. CAS TGT bị hủy.
5. Kiểm tra B bằng cookie cũ khi B online trở lại; nếu không có cơ chế bù trừ, B-S1 có thể vẫn active cho đến session timeout.

**Đây là một bài test quan trọng**, vì chứng minh logout CAS **không atomic xuyên các services**. Không ghi PASS toàn hệ thống chỉ vì A/C thành công. Cần xác định RTO/RPO nghiệp vụ cho thu hồi phiên và có **biện pháp giảm thiểu** như session TTL ngắn, forced reauthentication ở ứng dụng nhạy cảm, versioned session invalidation/revocation, online introspection hoặc đối soát delivery.

### 10.2. Front-channel bị chặn

Dùng trình duyệt có CSP/third-party-cookie hoặc tracker protection nghiêm, đóng tab sớm hay tắt JavaScript trong test. Nếu CAS gửi front-channel nhưng client không xử lý được, C có thể giữ phiên. Không gắn sai thất bại này cho `HttpSessionMappingStorage` khi root cause là callback không đến. Cần quan sát DevTools network + CAS dispatch logs cùng session state backend.

### 10.3. Listener/session mapping bị mất

Cấu hình CAS client filter và listener đúng dependency/version:

- Xác minh khi ST login **đã được map vào HttpSession đang sống**.
- Kiểm tra mapping biến mất khi session timeout hoặc local logout.
- Kiểm tra `SingleSignOutFilter` tìm đúng mapping khi `SessionIndex=ST-A1`.
- Nếu mapping miss, ghi reason code, không lấy session “gần nhất” hay logout toàn bộ username.
- Sau deploy/failover, nếu mapping chỉ ở RAM JVM cũ, service không thể hủy session trên node mới.

CAS client có default in-memory implementations; khi ứng dụng triển khai multi-node hoặc Spring Session, cần nghiên cứu **session mapping storage phân tán có tương thích với phiên bản client/container**. Không giả định sticky session đủ khi callback là request riêng từ CAS Server, không có cookie browser.

### 10.4. Service logoutType=NONE

Nếu service registry được cấu hình không SLO cho B, B có thể tiếp tục active hợp lệ theo **cấu hình hiện tại**. Khi mục tiêu test là “mọi ứng dụng phải đăng xuất”, cần đánh dấu **không đạt yêu cầu hệ thống**, đồng thời ghi rằng root cause là **chính sách service registry** chứ không phải filter lỗi. Đây là phân biệt giữa **kỳ vọng nghiệp vụ** và **trạng thái thực thi đã cấu hình**.

## 11. Test nhiều thiết bị và nhiều phiên trên cùng service

### 11.1. Cùng user, hai CAS sessions độc lập

Giả sử:

~~~text
Browser-1 / TGT-1 (user=lan):
  A ST-A1 -> A-S1
  B ST-B1 -> B-S1

Browser-2 / TGT-2 (user=lan):
  A ST-A2 -> A-S2
  B ST-B2 -> B-S2

Logout tại Browser-1:
  CAS destroys TGT-1
  SLO A for ST-A1 -> A-S1 invalidated
  SLO B for ST-B1 -> B-S1 invalidated

Must NOT automatically invalidate:
  A-S2, B-S2 (belong to TGT-2)
~~~

Từ test này xác nhận SLO **nhắm vào phiên gắn ST**, không dùng username/email. Nếu tổ chức muốn “đăng xuất khỏi tất cả thiết bị”, cần một cơ chế **global logout** khác có xác thực và quy tắc thu hồi được thiết kế rõ; CAS SLO của một TGT không tự có nghĩa đó.

### 11.2. Nhiều tab một browser

Các tab cùng origin thường dùng **cùng local session cookie**. Khi CAS SLO invalidates A-S1, mọi tab của A gửi cookie cũ đều không còn Authentication hợp lệ. Tuy nhiên UI tab cũ có thể tiếp tục hiển thị dữ liệu render sẵn; điều đó khác với khả năng truy cập backend. Với SPA, cần cập nhật UX qua BroadcastChannel/event/state polling để tránh hiển thị sai trạng thái, nhưng **không tin JS để tự chứng minh session còn/hết**.

### 11.3. Một service có nhiều session do login lại

Nếu người dùng local logout ở A rồi SSO login lại trước CAS logout, A có thể có ST-A1 (phiên cũ đã xóa) và ST-A2 (phiên mới). CAS có thể ghi nhận nhiều service tickets trong TGT; notification cho ST cũ là no-op nếu mapping đã cleanup, còn notification cho ST mới phải hủy **phiên đang sống**. Không hủy session A mới chỉ vì match username của ST cũ.

## 12. Chống giả mạo và replay logoutRequest

Back-channel request có thể ảnh hưởng session người dùng khác, nên endpoint SLO là điểm nhạy cảm. Cần:

1. **Không tự chấp nhận bất kỳ XML POST** có trường `SessionIndex` rồi trực tiếp gọi `session.invalidate()`.
2. Sử dụng **Apereo Java CAS Client SingleSignOutFilter** hoặc handler được kiểm thử theo đúng CAS protocol/version.
3. Bảo vệ nguồn back-channel qua **HTTPS, mạng/gateway ACL, mTLS nếu phù hợp và được hỗ trợ, rate limiting**, không chỉ một HTTP header tùy ý.
4. Xác định `service` và endpoint được CAS Server cấu hình; không cho user nhập callback URL/issuer và tự chọn.
5. Parser XML phải phòng **XXE/entity expansion**; ưu tiên parser của thư viện chuẩn và phiên bản đã vá.
6. Duplicate callback cùng `SessionIndex` nên có hành vi **idempotent**: nếu session đã mất, không được xóa phiên khác.
7. Không xử lý `NameID` như khóa tìm tất cả user sessions khi chỉ có CAS SLO cho ST cụ thể.
8. Không vô hiệu CSRF bảo vệ mọi endpoint chỉ vì CAS SLO có POST không mang browser CSRF token; nếu cần exempt, **chỉ đúng CAS logoutRequest endpoint/path**, cùng source-trust controls.
9. Không log raw `logoutRequest`/ticket/session cookie/PII; dùng correlation hash và audit result.
10. Có giới hạn kích thước request XML, timeout, concurrency và chống DoS.

**CAS back-channel message hình thức giống SAML LogoutRequest nhưng không tự có SAML XML signature.** Khi chính sách yêu cầu authenticated logout delivery, phải triển khai các ràng buộc kênh và nguồn CAS Server phù hợp. Không hạ cấp trust chỉ vì kết quả “logout được nhiều app hơn” trong test.

### 12.1. SLO listener và session lifecycle

`SingleSignOutHttpSessionListener` giúp dọn mapping khi session hết hạn/hủy, nhưng **không tự gửi SLO tới mọi ứng dụng**; việc dispatch thuộc CAS Server. Một listener bị thiếu có thể làm mapping cũ tồn tại lâu, gây memory leak và false mapping. Một filter bị thiếu có thể khiến CAS callback 200/404 mà local session không đổi. Hai thành phần cần kiểm thử riêng.

## 13. Tích hợp phía Spring Boot Servlet: cách tổ chức kiểm thử

Ví dụ thành phần khái niệm:

~~~text
Servlet filter order:
  CharacterEncodingFilter (UTF-8 when needed)
  Apereo SingleSignOutFilter
  Spring Security FilterChainProxy (CAS auth and authorization)
  ...
Servlet session listener:
  SingleSignOutHttpSessionListener

Spring Security:
  CasAuthenticationEntryPoint
  CasAuthenticationFilter (/login/cas)
  CasAuthenticationProvider + TicketValidator
  SecurityContextRepository
  local LogoutFilter (/logout)

CAS Server:
  /logout
  service registry A/B/C with correct logoutType, logoutUrl
  SLO transport/dispatch and service ticket correlation
~~~

Đây là **sơ đồ kiến trúc**, không phải config file runnable. Filter ordering chi tiết phụ thuộc Spring Boot/Servlet deployment và phiên bản CAS Client, cần kiểm chứng qua integration tests. Không đặt hai `SingleSignOutFilter` trong cả container và Spring chain cùng xử lý một request.

### 13.1. Ví dụ registration trong Spring Boot

Mẫu thể hiện cách đăng ký CAS SLO filter + listener trong Servlet stack có version tương thích:

~~~java
package example.cas;

import org.apereo.cas.client.session.SingleSignOutFilter;
import org.apereo.cas.client.session.SingleSignOutHttpSessionListener;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class CasSingleLogoutConfig {

    @Bean
    FilterRegistrationBean<SingleSignOutFilter> singleSignOutFilter() {
        FilterRegistrationBean<SingleSignOutFilter> registration =
                new FilterRegistrationBean<>();
        registration.setFilter(new SingleSignOutFilter());
        registration.addUrlPatterns("/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return registration;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
            singleSignOutListener() {
        ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
                registration = new ServletListenerRegistrationBean<>();
        registration.setListener(new SingleSignOutHttpSessionListener());
        return registration;
    }
}
~~~

**Lưu ý:** mảnh trên cần **Spring Boot Servlet, `spring-security-cas` và Apereo Java CAS Client tương thích**, cấu hình filter/protocol đầy đủ và CAS Server thật. `Ordered.HIGHEST_PRECEDENCE` là **minh họa yêu cầu chạy sớm**; không có nghĩa luôn đúng trong mọi filter stack. Cần đo thứ tự filter thực tế, check UTF-8 encoding, exception handling, `LogoutFilter`, access log và CAS callback. Thử cấu hình test trước khi chọn order production. Nếu đã đăng ký filter/listener qua `web.xml` hoặc auto-configuration, không tạo bản trùng.

### 13.2. Cần tránh những lỗi cấu hình này

| Lỗi | Kết quả |
| --- | --- |
| SLO filter chỉ map `/logout` local. | Không thấy ticket callback/login hoặc CAS logoutRequest. |
| CAS Server gửi POST tới `/login/cas` nhưng reverse proxy chỉ cho GET. | CAS callback 405/403, local session còn sống. |
| Spring CSRF chặn SLO POST trước filter. | Không invalidate session. |
| Spring Boot auto-config thêm filter thứ hai. | Duplicate handler/mapping không nhất quán. |
| Thiếu `SingleSignOutHttpSessionListener`. | Mapping không được cleanup khi HttpSession expires. |
| Local session ID rotate nhưng mapping giữ stale reference. | SLO thông báo tới đúng ST nhưng hủy sai/không hủy phiên thực. |
| `SingleSignOutFilter` ở node A nhưng session ở node B. | Cần shared session/mapping, không phụ thuộc sticky cookie. |
| Service `logoutUrl` trỏ tới trang thông báo, không qua SLO filter. | HTTP 200 nhưng phiên không bị invalidate. |
| CAS Server/ticket validator khác môi trường (staging/prod). | ST correlation hoặc trust sai; có thể làm mất SLO. |

## 14. Quan sát trạng thái từng service và cách báo cáo QA

Khi có nhiều service, báo cáo SLO **phải có dòng riêng cho từng phiên**. Ví dụ:

| Service | ST ref | Local session ref | Callback received | Mapping found | Invalidation | Old-cookie test | Kết luận |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | HMAC(ST-A1) | A-S1-ref | YES | YES | YES | DENIED | PASS |
| B | HMAC(ST-B1) | B-S1-ref | YES | YES | YES | DENIED | PASS |
| C | HMAC(ST-C1) | C-S1-ref | NO | N/A | NO | STILL ACTIVE | **FAIL** |

Trong ví dụ này **toàn bài test phải FAIL/PARTIAL**, không thể tuyên bố success vì A/B pass. Nếu service C không cần SLO theo business contract, kết luận “out of scope” phải được **định nghĩa từ trước**, không tự loại bỏ C sau khi test thất bại.

### 14.1. Log/audit nên có gì?

Gợi ý event fields (tự định nghĩa, **không phải log mặc định** của Spring/CAS):

~~~text
event=CAS_SINGLE_LOGOUT
test_run=slo-20261107-001
timestamp=2026-11-07T04:00:00Z
cas_server_ref=cas-primary
service_ref=reports-b
service_ticket_ref=HMAC(ticket-id)
local_session_ref=HMAC(session-id)
callback_transport=BACK_CHANNEL
callback_received=true
session_mapping_found=true
session_invalidated=true
old_cookie_protected_request=DENIED
result=PASS
~~~

Không dùng plain ST, TGT, JSESSIONID, username, raw `logoutRequest` hoặc private tokens trong logs có thể truy cập rộng rãi. Nếu cần liên hệ các events, dùng **HMAC với secret audit** thay vì chỉ một hash ngắn dễ dò. Định nghĩa retention/ACL và cảnh báo cho error rate.

### 14.2. Metrics vận hành

Các metric gợi ý:

~~~text
cas_slo_dispatch_total{service,channel,outcome}
cas_slo_callback_received_total{service}
cas_slo_mapping_found_total{service}
cas_slo_mapping_missing_total{service}
cas_slo_session_invalidated_total{service}
cas_slo_callback_error_total{service,reason}
cas_slo_latency_seconds{service}
cas_slo_delivery_queue_depth
cas_local_session_active_after_slo_total{service}
cas_slo_replay_noop_total{service}
~~~

Không đưa `username`, raw ST hay session cookie làm metric labels vì **cardinality** và nhạy cảm. Theo dõi từ cả CAS Server (dispatch/delivery) lẫn services (mapping/invalidation). Hai phía có thể báo “delivery 200” nhưng một phía invalidation failed; vì vậy cần tính metric E2E **không chỉ success code HTTP**.

## 15. Ma trận kiểm thử đầy đủ

| Test case | Kết quả kỳ vọng |
| --- | --- |
| Một service A, CAS logout, back-channel thành công. | A session cũ không còn quyền. |
| A/B/C cùng một TGT, tất cả active. | Cả ba không còn quyền sau SLO hoàn tất. |
| Local logout ở A khi B/C vẫn active. | B/C và CAS TGT không bị hủy mặc định. |
| A local logout rồi vào lại khi CAS TGT còn. | Có thể SSO login **một phiên mới**; không dùng old session. |
| CAS logout nhưng B offline. | A/C hủy; B có thể còn active; test ghi **PARTIAL**, cảnh báo. |
| CAS callback B đến trễ. | B hủy đúng session khi callback hợp lệ; không hủy session mới khác. |
| CAS callback lặp lại cho cùng ST. | Idempotent no-op; không hủy session khác. |
| CAS `SessionIndex` sai ST. | Không tìm mapping; không xóa theo username. |
| CAS `NameID` bằng user thật nhưng ST sai. | Không hủy session user theo NameID. |
| CAS back-channel POST không tới filter. | Test FAIL và có chẩn đoán routing/order. |
| Receptor trả HTTP 200 nhưng không invalidate. | E2E FAIL dù transport 200. |
| Session mapping bị mất sau node restart. | Được phát hiện qua no-match/old-cookie test, không báo PASS giả. |
| A/B/C chạy nhiều node/shared session store. | Mọi callback có thể xác định/hủy đúng local session. |
| CAS Server chọn FRONT_CHANNEL nhưng C không hỗ trợ. | Phải phát hiện C còn active; không giả định mode tương thích. |
| Browser đóng tab trước front-channel. | Đánh giá lost delivery và policy bù trừ. |
| Một user, hai TGT trên hai browser profiles. | SLO TGT-1 không tự hủy TGT-2 sessions. |
| Một user, nhiều tabs cùng local session. | Tất cả tabs mất quyền backend bằng old session. |
| A đã timeout trước CAS logout. | SLO đến A có thể no-op; không tạo session mới. |
| SSO TGT expired theo idle timeout. | Kiểm tra CAS policy có phát SLO hay không, không suy từ explicit logout. |
| C dùng JWT access token. | CAS SLO không tự thu hồi JWT; test revocation/TTL riêng. |
| Browser cache giữ trang cũ. | Protected backend request bị chặn; UI stale được nhận diện riêng. |
| Callback giả mạo `logoutRequest`. | Không cho hủy session khi source không tin; parser/ACL chống injection. |
| Callback có XML quá lớn/XXE. | Bị từ chối an toàn, không làm cạn tài nguyên. |
| Service registry thiếu B. | SLO không được phát B, test FAIL so với yêu cầu A/B/C. |
| `logoutType=NONE` ở B. | B nằm ngoài propagation; không đánh giá B đã logout. |
| Service `logoutUrl` sai. | Phát hiện 404/302/200 giả, sửa registry. |
| Spring Security session ID rotation khi login. | Mapping ST → session vẫn phục vụ SLO đúng. |
| Local account bị DISABLED giữa phiên. | Authorization phải từ chối theo policy, độc lập với SLO. |
| Service nhận logout rồi có request đang chạy. | Xác minh semantics revocation ở critical operation, không giả định rollback tự động. |
| Logout CAS rồi browser tự login lại vì IdP upstream vẫn active. | Phân biệt new session qua identity/session generation; kiểm tra upstream logout contract. |

Một hệ thống cần kiểm thử cả **hành vi đúng** lẫn **mất thông báo/độ trễ/race**. Nếu chỉ test “bấm logout rồi thấy trang đăng nhập”, dễ bỏ sót B/C vẫn giữ phiên có hiệu lực.

## 16. Troubleshooting theo từng lớp

| Dấu hiệu | Root cause thường gặp | Hành động kiểm tra |
| --- | --- | --- |
| CAS đã logout nhưng cả A/B/C vẫn active. | SLO disabled, service registry sai, callback không đến. | Xem CAS dispatch event và `logoutType`. |
| Chỉ A logout, B/C không. | Local logout ở A, chưa điều hướng CAS `/logout`. | So nút “local” và “global” logout. |
| CAS dispatch A nhưng không có request ở A. | DNS/firewall/TLS/gateway/ingress sai. | Quan sát logs mạng và URL. |
| CAS POST A trả 403. | Spring security/CSRF hoặc WAF chặn. | Cho phép đúng SLO path theo transport trust, không tắt CSRF toàn site. |
| CAS POST A trả 404/405. | Sai `logoutUrl`, route chỉ GET, filter mapping không đúng. | So service registry và Servlet filter. |
| CAS POST A trả 200 nhưng A-S1 vẫn active. | Handler ACK mà không invalidation; mapping không được tìm. | Kiểm tra ST→HttpSession và protected old-cookie call. |
| Chỉ khi đổi session ID thì SLO fail. | Session fixation rotation/mapping stale. | Kiểm tra session strategy và listener/CAS client version. |
| SLO fail sau rolling deploy. | Session mapping RAM local ở node cũ. | Shared store, lifecycle/failover, CAS client compatibility. |
| SLO làm logout tất cả thiết bị của cùng user. | Xóa theo username thay vì ST/TGT scope. | Sửa correlation và test 2 browsers. |
| Một callback lặp làm lỗi 500. | Handler không idempotent khi session đã hủy. | No-op an toàn khi mapping missing, audit. |
| Front-channel không chạy trong một browser. | CSP/cookie restriction/iframe blocking/client không hỗ trợ. | Browser network + test mode khác; không giả định universal support. |
| Browser tab vẫn hiện dữ liệu. | UI cached/SPA state stale. | Thử call server protected endpoint không cache. |
| API JWT vẫn hoạt động sau SLO. | Token stateless riêng, không revoke. | Thiết kế token expiry, revocation/introspection/securityVersion. |
| CAS TGT hủy nhưng browser SSO lại ngay. | Upstream IdP vẫn đăng nhập và CAS broker tái xác thực. | Phân biệt CAS và upstream sessions. |
| Một service không nhận SLO theo đúng registry. | `logoutType=NONE` hoặc service không được ghi trong TGT. | Kiểm tra policy/business requirement. |

**Trình tự debug:** (1) test có cùng TGT và A/B/C đã login không → (2) CAS logout có hủy TGT không → (3) CAS có ghi nhận/deliver per-service SLO không → (4) endpoint có nhận không → (5) filter có parse SessionIndex không → (6) có ST→HttpSession mapping không → (7) invalidate có thành công không → (8) old-cookie protected access còn được không.

## 17. Thiết kế các biện pháp bù trừ khi SLO best effort không đủ

SLO giúp đồng bộ trải nghiệm và giảm thời gian tồn tại phiên, nhưng không nên là **điểm kiểm soát duy nhất** khi thao tác nhạy cảm cần thu hồi tức thời. Các biện pháp:

1. **Session timeout hợp lý** và absolute timeout cho ứng dụng nhạy cảm, không dựa mãi vào phiên cookie còn.
2. **Forced reauthentication** cho hành động rủi ro cao: CAS `renew` hoặc cơ chế assurance/step-up đã thỏa thuận; không tự coi `renew` đồng nghĩa MFA.
3. **Local account status/entitlement recheck**: revoked/disabled nên bị chặn ngay hoặc trong SLA đã định.
4. **Session registry/revocation version** phân tán nếu cần global logout hoặc hủy tất cả phiên của một account theo policy riêng.
5. **Token TTL ngắn, introspection/revocation** cho API access tokens độc lập; JWT không tự invalidated khi HttpSession CAS bị xóa.
6. **Reliable audit + alarm** khi CAS SLO dispatch/delivery/invalidation lệch nhau, nhất là services tài chính/quản trị.
7. **Idempotent callback** và lưu trạng thái xử lý an toàn; không retry ST đã dùng để sửa SLO.
8. **Policy fail-safe** khi service không liên hệ CAS được: nhạy cảm thì require reauth hoặc deny; không dùng silent fail-open vô hạn.
9. **Device/session visibility**: cung cấp UI cho người dùng biết phiên nào có thể còn hoạt động nếu yêu cầu doanh nghiệp; không tuyên bố "đã logout mọi nơi" chỉ khi CAS trả 200.
10. **Boundary với OIDC/SAML broker**: phải dùng logout profile/tokens tương ứng, không giả định CAS `logoutRequest` sẽ tới mọi relying party upstream/downstream.

**Một thiết kế thực tế** có thể chấp nhận SLO best effort với ứng dụng ít nhạy cảm nhưng yêu cầu **SLA thu hồi** rõ cho admin/finance. Không bắt CAS Server xử lý mọi service như một distributed transaction ACID, vì CAS SLO là notification protocol.

## 18. Sai lầm phổ biến

1. **“CAS /logout trả 200 nên A/B/C đều logout.”** Sai: cần chứng minh session tại từng service.
2. **“Bấm logout ở A là logout toàn CAS.”** Sai nếu A chỉ hủy local session.
3. **“Một người dùng chỉ có một HttpSession trong toàn bộ CAS.”** Sai: từng service, browser và thiết bị có phiên riêng.
4. **“CAS LogoutRequest SessionIndex là `JSESSIONID`.”** Sai: trong CAS SLO thường là **ST ID**.
5. **“Dùng NameID/username để xóa mọi phiên là đúng CAS SLO.”** Sai: có thể xóa sai TGT khác.
6. **“Một callback HTTP 200 chứng minh mapping đã hủy.”** Sai: phải kiểm tra local invalidation và old-cookie access.
7. **“Back-channel chắc chắn gửi tới tất cả dịch vụ, không bao giờ lỗi.”** Sai: SLO best effort, có timeout/async/queue.
8. **“Front-channel hoạt động ở mọi trình duyệt.”** Sai: CSP, iframe, privacy/cookie restrictions và client support khác nhau.
9. **“SLO filter được map chỉ ở `/logout` local là đủ.”** Sai: nó cần thấy ST login và CAS SLO callback.
10. **“Không cần session listener.”** Sai: cleanup mapping là phần quan trọng của lifecycle.
11. **“Sticky session luôn đảm bảo back-channel tới đúng pod.”** Sai: callback không có browser cookie và có thể tới node khác.
12. **“Không thấy logoutReq nên xóa session theo user.”** Sai: fail closed đối với dữ liệu không được xác minh.
13. **“SLO giống hệt SAML 2.0 signed Single Logout.”** Sai: CAS dùng một dạng XML tương tự nhưng protocol/trust khác.
14. **“CAS SLO xóa JWT access token của API ngay lập tức.”** Sai nếu API có token/authorization riêng.
15. **“Tab vẫn hiển thị profile chứng minh SLO fail.”** Chưa chắc: UI có thể cache; phải call server.
16. **“Old-cookie request trả 302 luôn chứng minh SLO pass.”** Chưa đủ nếu redirect/auto login tạo phiên mới; cần audit generation.
17. **“Retry cùng ST để kiểm chứng logout.”** Sai: ST one-time, test phải dùng protected resource/correlation.
18. **“SLO TGT-1 nên xóa tất cả thiết bị cùng username.”** Sai trừ khi có global logout policy riêng.
19. **“Đã CAS logout thì upstream IdP cũng logout.”** Sai nếu CAS đang làm broker và upstream session còn.
20. **“Service offline lúc SLO không quan trọng vì CAS đã logout.”** Sai: local session ở service có thể còn hiệu lực.

## 19. Checklist nghiệm thu trước production

1. A/B/C được đăng nhập bằng **cùng CAS TGT** trong test, mỗi service có local session riêng chưa?
2. CAS service registry xác định rõ **BACK_CHANNEL/FRONT_CHANNEL/NONE** cho từng service chưa?
3. `logoutUrl`/service URL dùng HTTPS public endpoint đúng nơi `SingleSignOutFilter` xử lý chưa?
4. Có `SingleSignOutFilter` và `SingleSignOutHttpSessionListener` với filter ordering đúng chưa?
5. Mapping **ST ID → HttpSession** được ghi khi login và tìm được khi SLO không?
6. Có test session fixation ID change, local logout trước CAS logout và session timeout không?
7. Có test CAS SLO hủy A/B/C sau khi một browser thực sự active ở cả ba không?
8. Có kiểm chứng bằng **original service cookies** và protected endpoints, không chỉ UI/HTTP 200 không?
9. Có test service B offline/timeout và đánh giá partial logout đúng không?
10. Có test hai CAS sessions cùng username ở hai browser profiles, không xóa sai TGT khác không?
11. Có test duplicate logoutRequest, wrong SessionIndex và malformed/forged XML không?
12. Callback có HTTPS, giới hạn inbound source, parser chống XXE và CSRF exemption đúng phạm vi không?
13. Multi-node deployment có session store/mapping đủ consistent, không phụ thuộc local RAM không?
14. Có audit per-service: dispatch, delivery, mapping, invalidation và old-cookie verification không?
15. Có SLA xử lý partial SLO, session timeout/revocation controls cho các service nhạy cảm không?
16. Với SPA/API JWT, có thiết kế logout/revoke riêng phù hợp không?
17. Có phân biệt CAS protocol SLO với OIDC/SAML logout downstream/upstream không?
18. Có tài liệu chính sách local vs CAS vs toàn hệ thống và hướng dẫn người dùng tránh hiểu nhầm không?

## 20. Tự kiểm tra kiến thức

1. **Vì sao CAS TGT đã hủy mà service B vẫn có thể active?** — Vì B giữ local session độc lập; SLO delivery/invalidation có thể thất bại.
2. **Khác biệt local logout và CAS logout là gì?** — Local chỉ hủy session của service; CAS logout hủy CAS SSO session.
3. **Ai gửi SLO callback tới A/B/C?** — CAS Server trong giao thức CAS, theo registered service policy.
4. **`SessionIndex` trong CAS logoutRequest thường trỏ tới gì?** — **Service ticket ID** đã cấp cho service.
5. **Tại sao không tìm session theo username?** — Một user có nhiều TGT/sessions; dễ hủy sai phiên.
6. **`SingleSignOutFilter` làm gì?** — Xử lý logout notifications và mapping ST→session theo CAS Client.
7. **`SingleSignOutHttpSessionListener` để làm gì?** — Cleanup session mapping khi session bị hủy/hết hạn.
8. **Bằng chứng E2E nào quan trọng nhất?** — Các protected requests bằng **cookie cũ** ở từng service không còn quyền sau khi SLO xử lý.
9. **SLO A/C thành công còn B offline thì có PASS không?** — Không nếu yêu cầu là toàn bộ A/B/C; đó là partial logout.
10. **CAS back-channel có cần browser mở tab B không?** — Không; CAS Server gửi request server-to-server.
11. **CAS front-channel có thể bị ảnh hưởng gì?** — Browser/CSP/iframe/cookie restrictions và client support.
12. **SLO back-channel dùng XML dạng SAML có mặc nhiên signature chuẩn SAML2 không?** — Không; cần CAS transport/source trust.
13. **Local logout A rồi truy cập lại A thấy đăng nhập ngay thì local logout sai?** — Không nhất thiết: CAS TGT còn, cấp ST mới cho phiên mới.
14. **Cùng user có TGT-1 và TGT-2, CAS logout TGT-1 thì TGT-2 sao?** — Không tự hủy theo CAS SLO của TGT-1.
15. **Các API access token hết hạn ngay khi CAS SLO hủy HttpSession không?** — Không tự động, trừ khi có revocation integration.
16. **Làm sao phát hiện callback HTTP 200 giả?** — Đối chiếu mapping found/session invalidated và protected old-cookie test.
17. **Tại sao session fixation protection liên quan SLO?** — Session ID có thể đổi sau login; mapping ST→live session phải cập nhật đúng.
18. **Chính sách nào bù trừ khi một service không nhận SLO?** — Session TTL, forced reauth, revocation/active status check, monitoring và SLA.

## Tài liệu tham khảo

- [Apereo CAS — Logout and Single Logout (CAS protocol, BACK_CHANNEL/FRONT_CHANNEL, service registry)](https://apereo.github.io/cas/8.0.x/installation/Logout-Single-Signout.html)
- [Apereo CAS — CAS Protocol Specification, /logout và Single Logout](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html)
- [Apereo CAS — Security Guide: SLO là best-effort, các biện pháp bù trừ](https://apereo.github.io/cas/development/planning/Security-Guide.html)
- [Spring Security — CAS Authentication, Single Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html)
- [Apereo Java CAS Client — SingleSignOutFilter và SingleSignOutHttpSessionListener](https://github.com/apereo/java-cas-client)
- [Apereo CAS — SSO Session Services & Applications](https://apereo.github.io/cas/development/authentication/Configuring-SSO-Services.html)
- [Spring Security — Session Management và session fixation protection](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Logout, Servlet applications](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
