# Tùy chỉnh phản hồi khi CAS ticket hết hạn, bị dùng lại hoặc không hợp lệ

## 1. Bài toán và mục tiêu

Ứng dụng Java Spring Security tích hợp **CAS Protocol** thường chuyển browser sang CAS Server để đăng nhập. CAS xác thực người dùng, phát một **Service Ticket (ST)** ngắn hạn dành cho một service URL, rồi redirect về ứng dụng:

~~~http
GET /login/cas?ticket=ST-EXAMPLE-ONE-TIME HTTP/1.1
Host: app.example.org
~~~

Ứng dụng không được coi `ticket` là bằng chứng đăng nhập. Spring Security CAS client phải dùng `TicketValidator` gọi CAS Server (thường `/serviceValidate` hoặc `/p3/serviceValidate` qua HTTPS) để xác minh ST và service trước khi tạo `Authentication`.

Trong thực tế, callback có thể thất bại vì ST:
- Hết hạn trước khi CAS kiểm tra;
- Đã được kiểm tra một lần, sau đó browser refresh hoặc một filter/retry dùng lại;
- Chưa từng được cấp, sai, thuộc môi trường khác, bị sửa hoặc không tìm thấy;
- Được cấp cho **service khác** với service URL client gửi để validate;
- Không thỏa `renew` hoặc quy tắc loại ticket;
- Không thể được xác minh vì CAS Server, mạng, TLS hoặc parser đang lỗi.

Mục tiêu của bài học **“Tùy chỉnh phản hồi khi ticket hết hạn, bị dùng lại hoặc không hợp lệ”**, thuộc **Spring Security - federation → Tích hợp CAS**, là xây cơ chế xử lý thất bại vừa **an toàn** vừa **dễ vận hành**: nhận diện đúng mức thông tin thực sự có, không tự đăng nhập khi validation lỗi, không retry ST đã dùng, và không rơi vào vòng lặp CAS↔ứng dụng.

Sau bài bạn sẽ:
1. Hiểu **service-bound**, **one-time** và **short-lived** của CAS ST.
2. Phân biệt mã CAS `INVALID_TICKET`, `INVALID_SERVICE`, `INVALID_REQUEST` và `INTERNAL_ERROR`.
3. Giải thích vì sao một CAS client thường **không biết chắc** ticket hết hạn, đã dùng hay không tồn tại khi chỉ thấy `INVALID_TICKET`.
4. Tùy chỉnh `AuthenticationFailureHandler` trên `CasAuthenticationFilter`.
5. Chọn HTML redirect hay JSON/HTTP status theo hợp đồng browser và API.
6. Tổ chức logging/metrics, correlation IDs và phân loại nguyên nhân nội bộ mà không làm lộ ticket.
7. Tránh retry ST, double filter registration, wrong service URL và authentication redirect loops.
8. Thực hành Java 17 chạy độc lập để mô phỏng nguyên tắc CAS ticket one-time, service-bound và mapping lỗi.
9. Viết kịch bản kiểm thử expired/replayed/invalid ticket, timeout và CAS outage.
10. Phân biệt CAS ticket validation error với SAML Response error, lỗi phân quyền hoặc HTTP lỗi.

Ngữ cảnh: Java 17+, Spring Boot 3.x, Spring Security CAS trên Servlet/MVC. Khi dùng Spring Security 5.x/6.x/7.x cần kiểm tra Javadoc đúng phiên bản; những phiên bản Jakarta Servlet và javax Servlet không có cùng import.

## 2. Một CAS Service Ticket chỉ dùng cho một validation attempt

CAS Server sở hữu **Ticket-Granting Ticket (TGT)** biểu diễn phiên SSO tập trung và dùng **Ticket-Granting Cookie (TGC)** tại browser để nhận diện phiên đó. ST là ticket **riêng cho một service** và **dùng để được ứng dụng xác minh một lần**. Chúng không phải một:

| Đối tượng | Chức năng | Nơi xử lý |
| --- | --- | --- |
| `TGT` | CAS Server quản lý phiên SSO và khả năng cấp ST mới | CAS Server/ticket registry |
| `TGC` | Browser cookie tham chiếu phiên CAS | Browser ↔ CAS Server |
| `ST` | Một credential ngắn hạn dành cho service cụ thể | Browser mang tới app; backend app xác minh với CAS |
| `HttpSession/JSESSIONID` | Phiên local của ứng dụng sau xác thực | Spring Security và session store của app |

**CAS Protocol 2.0 quy định ST chỉ hợp lệ cho một lần thử validation, dù attempt thành công hay không.** CAS phải vô hiệu hóa ST sau attempt đó. Điều này bao gồm trường hợp ticket hợp lệ nhưng service URL gửi lên bị sai: `INVALID_SERVICE` không cho phép lấy chính ST ấy thử lại với service khác. Nếu ST hết hạn, CAS cũng từ chối.

Ví dụ luồng:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring CAS client
    participant CAS as CAS Server
    B->>SP: GET /protected
    SP-->>B: Redirect /cas/login?service=...
    B->>CAS: CAS login/SSO session
    CAS-->>B: Redirect /login/cas?ticket=ST-ONE
    B->>SP: GET callback với ST-ONE
    SP->>CAS: /serviceValidate?ticket=ST-ONE&service=...
    CAS->>CAS: Kiểm tra và tiêu thụ ticket
    alt Hợp lệ
        CAS-->>SP: authenticationSuccess, principal
        SP->>SP: Tạo Authentication / SecurityContext
        SP-->>B: Redirect URL không còn ST
    else Không hợp lệ
        CAS-->>SP: authenticationFailure với CAS code
        SP->>SP: AuthenticationFailureHandler
        SP-->>B: Trang lỗi an toàn
    end
    B->>SP: Refresh callback cũ với ST-ONE
    SP->>CAS: serviceValidate cùng ST-ONE
    CAS-->>SP: INVALID_TICKET
~~~

Một ST có thể bị replay do refresh, back button, browser extension, retry library hoặc duplicate filter chứ **không nhất thiết** có kẻ tấn công. Ngược lại, ST bị lộ và bị người khác sử dụng trước là rủi ro nghiêm trọng. Do đó phải kiểm soát TLS, service-binding, logging và redirect.

## 3. CAS validation thành công và thất bại

Với CAS 2.0, service có thể gọi:

~~~http
GET /cas/serviceValidate?ticket=ST-DEMO&service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas HTTP/1.1
Host: cas.example.org
~~~

Một CAS XML **success** minh họa:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>opaque-user-id</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

Một CAS XML **failure** minh họa:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_TICKET">
    Service ticket cannot be validated
  </cas:authenticationFailure>
</cas:serviceResponse>
~~~

Các XML trên **chỉ là ví dụ định dạng**, không phải response thật của server ví dụ. Đừng tự viết parser tìm text `authenticationSuccess` theo chuỗi; dùng thư viện CAS client có XML parser an toàn và **HTTPS server authentication**.

### Danh mục mã lỗi giao thức

| CAS Protocol error code | Ý nghĩa | Phản ứng phù hợp |
| --- | --- | --- |
| `INVALID_REQUEST` | Thiếu/sai tham số yêu cầu validation | Kiểm tra URL/handler; không tự tạo session |
| `INVALID_TICKET` | Ticket không hợp lệ, có thể đã hết hạn/được dùng/không tồn tại; cũng có thể do `renew` requirement | Cho đăng nhập mới, không retry ST |
| `INVALID_SERVICE` | Ticket có thể hợp lệ nhưng service khác service đã cấp | Sửa ServiceProperties/public URL/registry; ST cũ đã bị consume |
| `INTERNAL_ERROR` | Lỗi nội bộ CAS khi validation | Vận hành CAS health/audit, không đổ lỗi user |
| `INVALID_TICKET_SPEC` | Ticket không đáp ứng quy tắc validation specification ở một số bản CAS | Kiểm tra validator, renew/proxy/policy |
| `UNAUTHORIZED_SERVICE_PROXY` | Service không được cấp quyền làm proxy | Kiểm tra service registry và proxy trust |
| `INVALID_PROXY_CALLBACK` | Proxy callback không thỏa yêu cầu bảo mật | Kiểm tra pgtUrl/TLS/callback |

**Lưu ý phiên bản:** CAS Protocol 2.0 có tập mã tối thiểu, Apereo CAS phiên bản mới có thể có thêm mã. Không mặc nhiên coi mã không biết là thành công. CAS 1.0 `/validate` trả text yes/no, còn CAS 3.0 `/p3/serviceValidate` hỗ trợ attributes; chỉ áp các XML codes phù hợp endpoint.

**HTTP status không thay CAS protocol result.** CAS Server có thể trả HTTP 200 với `cas:authenticationFailure`. Ngược lại HTTP 502/503 hoặc timeout không chứng minh ticket sai.

## 4. Ba tình huống đều có thể là INVALID_TICKET

Đây là ranh giới kiến thức quan trọng nhất của bài.

### Ticket hết hạn

CAS Server lưu ST có thời hạn theo ticket expiration policy. Nếu đến quá trễ, CAS từ chối. Nguyên nhân có thể là browser chờ lâu, network nghẽn, time sync hoặc ST TTL quá thấp so với flow.

### Ticket bị dùng lại

ST đã được CAS kiểm tra thành công **hoặc thất bại**, rồi một validation attempt nữa gửi cùng ticket. CAS từ chối. Một filter bị đăng ký hai lần, tự động retry GET `/serviceValidate` sau timeout, hoặc user nhấn Refresh callback đều có thể gây việc này.

### Ticket không nhận diện

Một ST giả, ticket thuộc hệ CAS khác, ticket đã bị evict hoặc mã đã bị sửa có thể không còn trong registry. CAS cũng từ chối.

**CAS client chỉ có `INVALID_TICKET` có thể KHÔNG biết tình huống nào đã xảy ra.** Một số CAS Server cung cấp lý do chi tiết trong audit/registry, nhưng CAS Protocol không bắt buộc mã riêng EXPIRED/REUSED/UNKNOWN. Vì vậy:

- Đừng viết `exception.getMessage().contains("expired")` rồi xem đó là contract.
- Đừng tuyên bố “replay attack” từ một INVALID_TICKET.
- Đừng thêm API công khai trả trạng thái ticket có tồn tại hay không; đó có thể là **ticket oracle**.
- Nếu cần điều tra, xem **trusted CAS Server audit**, correlation event, metrics và timestamp.
- User-facing message nên chung: **“Không thể hoàn tất lượt đăng nhập này. Vui lòng bắt đầu đăng nhập mới.”**

Sự phân biệt **mã lỗi giao thức** và **nguyên nhân vận hành** giúp xử lý đúng rủi ro mà không tạo false-positive.

## 5. Cấu trúc các lớp Spring Security CAS

Trong mô hình browser CAS:

~~~text
Browser:
  GET /login/cas?ticket=ST-...
      |
      v
CasAuthenticationFilter
      |
      v
AuthenticationManager / ProviderManager
      |
      v
CasAuthenticationProvider
      |
      v
CAS Client TicketValidator
      |
      v
CAS Server /serviceValidate
      |
      +--> CAS success -> Spring Authentication -> SecurityContext/session
      |
      +--> CAS failure/exception -> AuthenticationFailureHandler
                                      |
                                      v
                             HTTP response/redirect an toàn
~~~

Vai trò:
- `CasAuthenticationEntryPoint` đưa browser chưa xác thực sang `/cas/login</BT> với `service`.
- `ServiceProperties</BT> chứa service callback URL và tùy chọn `sendRenew</BT>.
- `CasAuthenticationFilter</BT> nhận ST tại callback, theo mặc định thường `/login/cas</BT>.
- `CasAuthenticationProvider</BT> xác minh ticket và tạo authentication từ kết quả CAS.
- `Cas20ServiceTicketValidator</BT> thường gọi CAS `/serviceValidate</BT> qua HTTPS.
- `AuthenticationFailureHandler</BT> tạo HTTP response sau lỗi authentication tại filter.
- `SecurityContextRepository/HttpSession</BT> giữ phiên ứng dụng sau login nếu cấu hình session.

Một lỗi TicketValidator có thể được bọc thành `AuthenticationException</BT>, đôi khi có root cause như `TicketValidationException</BT>. **Không có bảo đảm** mọi lỗi expired/replayed/invalid được biểu diễn bằng ba exception subclasses riêng. Chỉ xử lý structured code khi thư viện/version thực sự cung cấp; nếu không có, dùng nhóm `AUTHENTICATION_FAILED</BT> chung.

### AuthenticationFailureHandler khác AccessDeniedHandler

| Lỗi | Nơi xử lý đúng |
| --- | --- |
| CAS ST invalid, không tạo Authentication mới | CAS filter → AuthenticationFailureHandler |
| CAS validator timeout/TLS lỗi | Đường CAS provider/filter; phân loại network nếu có bằng chứng |
| CAS ticket đã valid nhưng user không đủ quyền | Spring AuthorizationManager / AccessDeniedHandler |
| User chưa có phiên đi vào route protected | AuthenticationEntryPoint (redirect CAS) |
| Lỗi CSRF của API POST | CSRF filter/AccessDeniedHandler theo cấu hình |
| Browser local logout, CAS TGC còn | Session/logout policy, không phải ST validation |
| SAMLResponse invalid signature | Spring SAML provider, không phải CAS TicketValidator |

Không bắt toàn bộ `Exception</BT> của ứng dụng rồi gọi lại CAS login, vì điều đó giấu lỗi thật, dễ gây login loop và có thể làm sai semantics HTTP/API.

## 6. Thiết kế phản hồi browser an toàn

Khi ST bị CAS từ chối:
1. **Không tạo Authentication** từ ticket lỗi hoặc từ query user khai.
2. **Không retry ST cũ**, kể cả khi lỗi là HTTP timeout vì CAS có thể đã consume nó.
3. Điều hướng đến một trang **public** cố định, ví dụ `/cas-error</BT>.
4. Trang này không có ticket trên URL, không tự động redirect trở lại CAS.
5. Hiển thị thông báo ngắn, không nêu raw ticket, CAS server nội bộ, Java stack trace.
6. Có hành động “Bắt đầu đăng nhập mới” **theo thao tác người dùng**, tạo một CAS login transaction và ST mới.
7. Không redirect đến URL do browser chọn thông qua `returnUrl</BT> chưa kiểm tra.
8. Log event theo trace ID riêng nhưng redact ticket, cookie, user identifiers.

Một gợi ý văn bản cho người dùng:

> Không thể hoàn tất lượt đăng nhập này. Liên kết xác thực có thể đã hết hiệu lực hoặc đã được sử dụng. Vui lòng bắt đầu đăng nhập mới. Nếu sự cố tiếp diễn, hãy liên hệ bộ phận hỗ trợ.

Thông báo này có thể dùng chung cho expired, reused và unknown. Không bảo đảm có thể nói “expired” nếu CAS chỉ cung cấp INVALID_TICKET.

### Khi đã xác minh INVALID_SERVICE

Có thể dùng thông báo khác:

> Ứng dụng hiện không thể hoàn tất đăng nhập. Vui lòng liên hệ hỗ trợ và cung cấp mã tham chiếu được hiển thị.

Vì lỗi service URL/registry có thể **không tự hết sau vài giây**, đừng auto-loop sang CAS login.

### Khi hệ CAS tạm gián đoạn

Một thông báo phù hợp:

> Dịch vụ đăng nhập đang tạm thời không khả dụng. Vui lòng thử lại sau.

Phải có evidence CAS endpoint/TLS/network, không coi mọi INVALID_TICKET là outage.

## 7. Tùy chỉnh CAS filter qua AuthenticationFailureHandler

`CasAuthenticationFilter</BT> kế thừa `AbstractAuthenticationProcessingFilter</BT>, hỗ trợ `setAuthenticationFailureHandler(AuthenticationFailureHandler)</BT>. Đây là extension point đúng để kiểm soát response khi **đăng nhập CAS ở filter** thất bại.

Tệp `src/main/java/com/example/federation/CasFailureHandler.java</BT>:

~~~java
package com.example.federation;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.stereotype.Component;

@Component
public final class CasFailureHandler
        implements AuthenticationFailureHandler {

    private static final Logger log =
            LoggerFactory.getLogger(CasFailureHandler.class);

    @Override
    public void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException {

        String incidentId = UUID.randomUUID().toString();

        // Không ghi ticket/query/cookie hoặc raw exception message.
        log.warn("cas_login_failed incidentId={} exceptionClass={}",
                incidentId, exception.getClass().getSimpleName());

        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Pragma", "no-cache");

        // Fixed local path, không lấy redirect URL từ browser.
        response.sendRedirect(request.getContextPath() + "/cas-error");
    }
}
~~~

**Giải thích code:**
- Handler chạy ở **Spring Security CAS filter**, không sửa/giải mã ticket.
- `incidentId</BT> là mã vận hành không nhạy cảm, trong ví dụ chỉ lưu ở log. Nếu muốn hiển thị cho người dùng, cần một kênh state/view riêng không cho phép truy vấn log tùy ý.
- `exception.getClass().getSimpleName()</BT> cho tín hiệu chẩn đoán mà không in raw message chứa ST.
- `response.sendRedirect</BT> chuyển browser đến URL cố định không có query ticket.
- Không có logic `if expired/replayed</BT> vì exception Spring không bảo đảm thông tin đó.
- Đây là **một lớp Java trong Spring Boot project**, cần Spring Security, Jakarta Servlet và SLF4J; **không chạy chỉ bằng javac** và không có stdout cố định.

### Gắn vào CasAuthenticationFilter

Tệp `src/main/java/com/example/federation/CasFilterConfig.java</BT>:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.web.CasAuthenticationFilter;

@Configuration
public class CasFilterConfig {

    @Bean
    CasAuthenticationFilter casAuthenticationFilter(
            AuthenticationManager authenticationManager,
            ServiceProperties serviceProperties,
            CasFailureHandler failureHandler) {

        CasAuthenticationFilter filter = new CasAuthenticationFilter();
        filter.setAuthenticationManager(authenticationManager);
        filter.setServiceProperties(serviceProperties);
        filter.setFilterProcessesUrl("/login/cas");
        filter.setAuthenticationFailureHandler(failureHandler);
        return filter;
    }
}
~~~

**Quan trọng:** bean trên là **một mảnh tích hợp**, không tự tạo hệ CAS login hoàn chỉnh. Dự án còn cần `CasAuthenticationEntryPoint</BT>, `CasAuthenticationProvider</BT>, `TicketValidator</BT>, user-details mapping, service registry và Spring SecurityFilterChain.

Nếu ứng dụng tạo một Filter bean theo cách Spring Boot auto-register nó thành **Servlet Filter** và cũng `addFilterAt</BT> vào Spring SecurityFilterChain, một callback có thể **bị xử lý hai lần**. Cần kiểm soát `FilterRegistrationBean</BT>/registration và kiểm thử thứ tự filter. Đừng vừa đăng ký filter thủ công trong Servlet container vừa cho cùng filter xử lý lại trong security chain.

### SecurityFilterChain minh họa điểm chèn

~~~java
@Bean
SecurityFilterChain casSecurity(
        HttpSecurity http,
        CasAuthenticationFilter casFilter,
        CasAuthenticationEntryPoint entryPoint) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/cas-error", "/public/**").permitAll()
                    .anyRequest().authenticated())
            .exceptionHandling(ex -> ex.authenticationEntryPoint(entryPoint))
            .addFilterAt(casFilter,
                    UsernamePasswordAuthenticationFilter.class)
            .build();
}
~~~

Đây là **snippet**, cần import `@Bean</BT>, `HttpSecurity</BT>, `SecurityFilterChain</BT>, `CasAuthenticationFilter</BT>, `CasAuthenticationEntryPoint</BT>, `UsernamePasswordAuthenticationFilter</BT> và mọi bean CAS thực tế. Tùy dự án có thể cần filter matcher, session strategy, CSRF và đăng ký provider riêng. **Không copy snippet như full project rồi kỳ vọng SSO chạy.**

Trang `/cas-error</BT> **phải public**. Nếu nó yêu cầu authentication, browser sẽ bị redirect về CAS ngay và tạo vòng lặp khi config lỗi.

## 8. Đừng nhầm CAS AuthenticationEntryPoint và CAS failure handler

**AuthenticationEntryPoint** được gọi khi browser chưa authenticated đi vào route bảo vệ. Nó thường chuyển sang CAS login:

~~~text
GET /private
  -> chưa Authentication
  -> CasAuthenticationEntryPoint
  -> 302 https://cas.example.org/cas/login?service=...
~~~

**AuthenticationFailureHandler** được gọi khi **CAS callback đã được nhận** nhưng ticket validation/provider thất bại:

~~~text
GET /login/cas?ticket=ST-BAD
  -> CasAuthenticationFilter
  -> TicketValidator rejects
  -> AuthenticationFailureHandler
  -> 302 /cas-error
~~~

Nếu failure handler redirect ngay về `/private</BT>, entry point sẽ tự khởi động CAS lần nữa. Với sai service URL, mỗi ST mới đều thất bại, nên browser có thể rơi vào vòng lặp vô hạn CAS↔app.

Thiết kế an toàn:
- Redirect lỗi tới trang public local cố định, **không tự động** sang CAS.
- Một nút đăng nhập lại do người dùng chọn để bắt đầu flow mới.
- Rate limit/alert khi lỗi liên tục.
- Kiểm tra callback URL có chứa ST ở browser history; sau success/failure phải điều hướng sạch.
- Xóa/không lưu request ticket đã thất bại khỏi đường đi sau đó.

## 9. Service URL mismatch: lỗi đặc thù đáng quan tâm

CAS ST được phát cho **một service identifier**. Ví dụ lúc xin ticket:

~~~text
CAS /login?service=https://app.example.org/login/cas
~~~

nhưng lúc xác minh app gửi:

~~~text
CAS /serviceValidate?service=http://app-internal:8080/login/cas
~~~

CAS có thể trả `INVALID_SERVICE</BT> vì service URL không khớp, dù hai địa chỉ đi tới cùng ứng dụng qua reverse proxy. CAS Protocol quy định ST bị vô hiệu hóa sau validation mismatch; sửa URL xong **phải xin ticket mới**.

Cần xem:
1. Public scheme HTTPS và internal scheme HTTP.
2. Host, port, context path, trailing slash và query.
3. `ServiceProperties.getService()</BT> và CAS service registry.
4. LB/ingress rewrite và `Forwarded/X-Forwarded-Proto/Host</BT> chỉ từ reverse proxy tin cậy.
5. Đồng bộ cấu hình giữa các pod.
6. Chính sách CAS Server allow-list để không cho cấp ST sang host ngoài.
7. Không gắn user-supplied return URL vào `service</BT> mà thiếu allow-list.

**Không sửa bằng cách cho phép mọi service wildcard hoặc tắt TLS hostname verification.** Đó là trust boundary, không chỉ là cấu hình tiện lợi.

## 10. Ticket expired và TTL

Ticket expiration policy do CAS Server quản lý. App không nên:
- Tự parse ticket opaque để lấy expiry.
- Gia hạn ST.
- Cho ST được sử dụng nhiều lần vì browser chậm.
- Thay đổi local clock để validation thành công.
- Tăng thời hạn ST lên nhiều giờ chỉ để che lỗi.
- Xem “browser đã chờ 5 giây” là chứng cứ đủ ticket expired.

Điều tra:
- CAS Server expiry policy và ticket registry settings.
- Thời điểm ST được cấp, thời điểm validator thực sự nhận request (từ audit có quyền).
- Phân phối thời gian/NTP giữa nodes.
- Browser delay hoặc proxy/WAF buffering.
- Phát/đọc ticket store giữa các node CAS cluster.
- Lỗi CAS registry evictions hoặc data lifecycle.
- CAS client network latency p95/p99.
- Timeout/redirect không cần thiết trong callback.

Nếu CAS chỉ trả `INVALID_TICKET</BT>, người dùng nhận thông báo chung, còn đội vận hành dùng CAS audit để xác định expiry khi có dữ liệu đáng tin.

## 11. Ticket reuse do lập trình hoặc browser

Các nguyên nhân:
- User Refresh/Back vào URL có `ticket=ST-OLD</BT>;
- Callback GET được load hai lần bởi SPA/lifecycle;
- HTTP client tự retry `/serviceValidate</BT> vì nghĩ GET luôn idempotent;
- Spring filter bị đăng ký ngoài Servlet chain và trong SecurityFilterChain;
- Reverse proxy hoặc automation test replay URL;
- Hai tab hoặc hai request đến đồng thời;
- Backend tự xác minh ST trong controller rồi CasAuthenticationFilter xác minh lại.

**Cẩn trọng:** mặc dù CAS `/serviceValidate</BT> dùng HTTP GET, nó có **side effect tiêu thụ ST**. Vì vậy **GET validation không an toàn để retry cùng ticket** theo nghĩa idempotency thông thường.

Khi provider trả `INVALID_TICKET</BT>, nếu nghi duplicate:
1. Đếm số validation attempts theo correlation/audit; không log ST thô.
2. Xác nhận một callback được xử lý đúng một lần theo thiết kế.
3. Kiểm tra filter registration và retry policy.
4. Chuyển browser khỏi URL có ticket sau mỗi login attempt.
5. Kiểm tra concurrent request tại LB/pod.
6. Không hạ chính sách CAS one-time để làm test pass.

**Một CAS login thành công và phiên app còn tồn tại** không mâu thuẫn với việc callback cũ bị từ chối. ST đã dùng xong; HttpSession/app Authentication vẫn có lifecycle riêng.

## 12. Lỗi unknown hoặc ticket giả

Một ST không có trong CAS registry không tự chứng minh đã có replay. Nguyên nhân có thể:
- Ticket chưa từng được CAS cấp;
- Ticket bị sửa hoặc thuộc môi trường staging/production khác;
- Ticket hết hạn đã bị evict;
- Ticket đã được consume nhưng không còn tombstone;
- CAS cluster/routing sai;
- CAS Server thay key/store hoặc node lỗi;
- Ticket format không được validator chấp nhận.

Browser có thể gửi một query `ticket=ST-guess</BT> để thử dò. Ứng dụng phải giữ nguyên nguyên tắc:
- **Không tạo Authentication** trước CAS validation;
- Không trả “ticket này tồn tại”/“ticket thuộc user X”;
- Không dùng URL ticket như một user identity;
- Không lưu ticket vào session làm bearer credential dài hạn;
- Log category chung, đánh giá rate-limit và CAS audit khi có dấu hiệu nghiêm trọng.

CAS cũng có **Proxy Ticket (PT)** và các endpoint `/proxyValidate</BT> có policy riêng. Một PT không nên tự được chấp nhận tại `/serviceValidate</BT> nếu profile không cho phép; không coi mọi string bắt đầu `PT-</BT> là ST.

## 13. Response HTML và API nên khác thế nào?

### Browser SSO

Browser callback có thể:
- Trả **302** tới `/cas-error</BT> cố định;
- Trang lỗi hiển thị thông báo thân thiện;
- Có nút “Đăng nhập lại” dẫn vào **giao dịch CAS mới**, không retry ST;
- Được đặt `Cache-Control: no-store</BT> / Referrer-Policy phù hợp;
- Không có raw ticket hoặc return URL bên ngoài.

### API

Một API có thể định nghĩa:

| Điều kiện | HTTP status tham khảo | Lưu ý |
| --- | --- | --- |
| Chưa có Authentication hợp lệ | 401 | Không có đủ bằng chứng để cấp session |
| Đã authenticated nhưng thiếu quyền | 403 | Authorization, không phải CAS ticket validation |
| CAS validator/Server outage đã được xác nhận | 503 | Tùy hợp đồng API và thành phần xử lý |
| Request malformed trước validation | 400 | Phải có contract, không cho người dùng enumerate ticket |
| Browser SSO callback ticket fail | 302 tới trang lỗi | Browser navigation khác REST JSON |

Không ép **mọi** CAS lỗi thành HTTP 500. CAS có thể trả HTTP 200 với `authenticationFailure</BT>. HTTP status là kết quả transport/app, còn `INVALID_TICKET</BT> là lỗi giao thức CAS.

### JSON ví dụ

~~~json
{
  "error": "authentication_failed",
  "message": "Không thể hoàn tất đăng nhập. Vui lòng bắt đầu phiên mới.",
  "traceId": "example-reference-001"
}
~~~

Đây là **schema minh họa**. Không đưa raw ST, CAS Server stack trace, username, exception cause hoặc service secrets vào response. Nếu muốn dùng cùng app phục vụ browser lẫn API, nên có security chains và response contracts rõ ràng, **không chỉ phân biệt dựa vào untrusted Accept header rồi trả tùy ý**.

## 14. Mức độ phân loại lỗi có thể tin

Hãy chia thành ba nhóm dữ liệu:

| Mức | Ví dụ | Được phép dùng ở đâu? |
| --- | --- | --- |
| CAS **protocol code** được validator xác minh | `INVALID_TICKET</BT>, `INVALID_SERVICE</BT> | Nội bộ ứng dụng/metrics |
| CAS **operational diagnosis** có bằng chứng | EXPIRED từ CAS Server audit, REPLAYED nếu có server-side record, TLS_TIMEOUT từ network | Vận hành/forensics |
| **Public response** cho user | AUTHENTICATION_FAILED, RETRY_NEW_LOGIN, CONTACT_SUPPORT | Browser/API |

Nếu CAS protocol chỉ cho `INVALID_TICKET</BT>, đặt internal reason `UNCLASSIFIED</BT> thay vì đoán nguyên nhân bằng message substring. Đừng dùng mã `BadCredentialsException</BT> để tự suy ST hết hạn: Spring provider có thể wrap nhiều lỗi theo version.

Nếu cần chia lỗi “hết hạn” và “đã dùng lại” chính xác:
1. CAS Server phải có dữ liệu audit ticket issuance/consume/expiry hoặc trusted status mở rộng.
2. Phải có cách liên hệ event mà không lưu ST raw tại app.
3. Các event cần access control, retention và privacy policy.
4. Khi nguồn không đủ, kết luận `UNKNOWN</BT>.
5. Không trả trạng thái tồn tại của ticket cho browser để tránh ticket oracle.

### Tránh log raw exception message

Một exception từ validator có thể chứa ticket hoặc service URL. Nên log:
- Stable exception **type**, CAS error code nếu có structured evidence;
- Trace ID do app sinh;
- Service **alias** đã đăng ký (không raw URL query);
- Node, environment, thời gian, latency;
- Outcome = DENY, action = NEW_LOGIN;
- Health error type (timeout, TLS) đã được phân loại.

Không log:
- Query string callback `ticket=...`;
- Cookies TGC/JSESSIONID;
- Full CAS XML response body;
- Session/ticket cache keys;
- Raw stack trace hoặc full request dump vào hệ logs công khai;
- Thông tin cá nhân như user principal nếu không cần.

## 15. Monitoring và điều tra lỗi sau deploy

Một event nội bộ:

~~~json
{
  "event": "cas_ticket_validation_failed",
  "traceId": "login-event-7a2e",
  "serviceAlias": "portal-cas",
  "casCode": "INVALID_TICKET",
  "diagnosis": "UNCLASSIFIED",
  "node": "portal-02",
  "durationMs": 117,
  "result": "DENY"
}
~~~

Trường `diagnosis</BT> là enum nội bộ, không phải CAS Protocol code. Không dùng ST làm metric label.

Các metric có thể dùng:
- `cas_ticket_validation_failed_total{code="INVALID_TICKET"}</BT>;
- `cas_ticket_validation_failed_total{code="INVALID_SERVICE"}</BT>;
- `cas_dependency_error_total{type="timeout"}</BT>;
- `cas_authentication_success_total</BT>;
- Validation latency p95/p99;
- Lượt callback thất bại trong một khoảng thời gian;
- Số lần redirect CAS↔app lặp;
- Số node có cấu hình service URL khác version.

**Không dùng username/ST/raw service URL làm label**, vì cardinality và data leak. Khi INVALID_SERVICE tăng đột biến ngay sau deploy, ưu tiên xem canonical URL/proxy/service registry. Khi INVALID_TICKET tăng cùng latency, xem TTL, CAS node/time sync và duplicate requests.

## 16. Lỗi network/TLS không giống CAS INVALID_TICKET

Ví dụ:
- DNS lookup lỗi;
- Connect/read timeout;
- CAS HTTP 502/503;
- TLS certificate hết hạn hoặc hostname sai;
- CAS response không phải XML;
- Trả về HTML login page thay vì CAS validation XML;
- Proxy/WAF chặn request;
- CAS ticket registry outage.

Trong các trường hợp đó app **chưa xác minh được ticket**, nên không tạo Authentication mới. Nhưng không được ghi báo cáo “CAS khẳng định ticket sai” khi **không có CAS response hợp lệ**.

Đặc biệt nguy hiểm: network timeout có thể xảy ra **sau khi CAS đã consume ST** nhưng trước khi app nhận response. Retry validation với chính ST đó **có thể trả INVALID_TICKET**. Do đó policy tốt là:
- Không có unbounded retry cho CAS validation;
- Khi có outage, fail closed cho login mới;
- Cho phép người dùng bắt đầu một CAS flow mới sau phục hồi;
- Có backoff/circuit breaker và monitoring hạ tầng;
- Không tắt TLS validation hoặc dùng HTTP plain để “sửa timeout”.

Session local đã xác thực trước outage có vòng đời và chính sách riêng; không mặc định xóa toàn bộ session vì CAS tạm mất kết nối, cũng không cho login mới bypass CAS.

## 17. Java 17 độc lập: mô phỏng expired/replay/wrong-service

Chương trình dưới đây dùng **chỉ JDK 17**, mô phỏng ticket registry **phía CAS Server**. Vì nó nắm quyền phát/tiêu thụ ticket, nó biết lý do EXPIRED hoặc REUSED. Sau đó nó quy nhiều nguyên nhân về **cùng mã giao thức INVALID_TICKET**, minh họa vì sao client không thể suy ngược nguyên nhân chính xác.

Tệp `CasTicketFailureDemo.java</BT>:

~~~java
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public final class CasTicketFailureDemo {

    enum Reason {
        OK, INVALID_REQUEST, EXPIRED, REUSED,
        INVALID_SERVICE, UNKNOWN
    }

    record Ticket(String service, Instant expiresAt) {}

    static final class TicketStore {
        private final Map<String, Ticket> live = new HashMap<>();
        private final Set<String> attempted = new HashSet<>();

        synchronized void issue(
                String id, String service, Instant expiresAt) {
            live.put(id, new Ticket(service, expiresAt));
        }

        synchronized Reason validate(
                String id, String presentedService, Instant now) {
            if (id == null || id.isBlank()
                    || presentedService == null
                    || presentedService.isBlank()) {
                return Reason.INVALID_REQUEST;
            }

            Ticket entry = live.remove(id);
            if (entry == null) {
                return attempted.contains(id)
                        ? Reason.REUSED : Reason.UNKNOWN;
            }
            attempted.add(id);

            if (!entry.expiresAt().isAfter(now)) {
                return Reason.EXPIRED;
            }
            if (!entry.service().equals(presentedService)) {
                return Reason.INVALID_SERVICE;
            }
            return Reason.OK;
        }
    }

    static String casCode(Reason reason) {
        return switch (reason) {
            case OK -> "SUCCESS";
            case INVALID_REQUEST -> "INVALID_REQUEST";
            case INVALID_SERVICE -> "INVALID_SERVICE";
            case EXPIRED, REUSED, UNKNOWN -> "INVALID_TICKET";
        };
    }

    static String userAction(Reason reason) {
        return reason == Reason.OK
                ? "SIGNED_IN" : "NEW_LOGIN_REQUIRED";
    }

    static void print(String label, Reason reason) {
        System.out.println(label + ": " + reason
                + " / CAS=" + casCode(reason)
                + " / UX=" + userAction(reason));
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T03:00:00Z");
        String service = "https://app.example.org/login/cas";
        String wrong = "https://other.example.org/login/cas";

        TicketStore server = new TicketStore();
        server.issue("ST-FRESH", service, now.plusSeconds(60));
        server.issue("ST-OLD", service, now.minusSeconds(1));
        server.issue("ST-WRONG", service, now.plusSeconds(60));

        print("fresh",
                server.validate("ST-FRESH", service, now));
        print("replay",
                server.validate("ST-FRESH", service, now));
        print("expired",
                server.validate("ST-OLD", service, now));
        print("wrong-service",
                server.validate("ST-WRONG", wrong, now));
        print("retry-after-wrong",
                server.validate("ST-WRONG", service, now));
        print("unknown",
                server.validate("ST-UNKNOWN", service, now));
        print("missing",
                server.validate("", service, now));
    }
}
~~~

Chạy bằng Java 17+:

~~~bash
javac CasTicketFailureDemo.java
java CasTicketFailureDemo
~~~

Stdout **chính xác**:

~~~text
fresh: OK / CAS=SUCCESS / UX=SIGNED_IN
replay: REUSED / CAS=INVALID_TICKET / UX=NEW_LOGIN_REQUIRED
expired: EXPIRED / CAS=INVALID_TICKET / UX=NEW_LOGIN_REQUIRED
wrong-service: INVALID_SERVICE / CAS=INVALID_SERVICE / UX=NEW_LOGIN_REQUIRED
retry-after-wrong: REUSED / CAS=INVALID_TICKET / UX=NEW_LOGIN_REQUIRED
unknown: UNKNOWN / CAS=INVALID_TICKET / UX=NEW_LOGIN_REQUIRED
missing: INVALID_REQUEST / CAS=INVALID_REQUEST / UX=NEW_LOGIN_REQUIRED
~~~

**Giới hạn demo:** đây không phải CAS Server thật, không cấp ticket bằng SecureRandom, không HTTP/TLS, không XML, không có ticket store phân tán và không xác minh account. Set `attempted</BT> là state phụ **tự tạo** để nhận biết replay; CAS implementation không bắt buộc giữ tombstone như vậy. Client CAS chỉ có protocol result không thể tự biết Reason. Không dùng code demo làm authentication middleware production.

Điểm bài học:
1. ST vừa cấp còn hạn và đúng service → lần đầu thành công.
2. ST dùng lại → server mô phỏng biết REUSED nhưng trả protocol `INVALID_TICKET</BT>.
3. ST hết hạn → EXPIRED cũng về `INVALID_TICKET</BT>.
4. ST đúng nhưng service sai → `INVALID_SERVICE</BT> và bị tiêu thụ.
5. Sau mismatch, thử lại cùng ST với service đúng → vẫn không được.
6. Ticket chưa từng cấp → cùng `INVALID_TICKET</BT>.
7. Thiếu ticket → `INVALID_REQUEST</BT>.
8. UI không tiết lộ phân biệt nhạy cảm, chỉ yêu cầu login mới.

## 18. Tránh một vòng lặp redirect điển hình

Giả sử cấu hình sai:

~~~text
App public URL: https://app.example.org/login/cas
App validator service: http://internal:8080/login/cas

1. GET /private -> CAS login
2. CAS phát ST-1 cho public URL
3. App validate ST-1 với internal URL -> INVALID_SERVICE
4. Failure handler tự redirect về /private
5. /private lại đưa browser sang CAS login
6. CAS phát ST-2, vẫn sai service
7. Lặp vô hạn, browser báo too many redirects
~~~

Cách xử lý:
- Failure handler redirect đến public `/cas-error</BT>, **không về route protected**.
- Trang này không tự khởi động login tiếp.
- Gắn trace ID để đội vận hành biết lỗi.
- Sửa `ServiceProperties.service</BT>, trusted forwarded headers và CAS service registry.
- Sau khi sửa, user chọn bắt đầu **login transaction mới** với ST mới.
- Không thay đổi CAS Server để bỏ service binding.

**Không giải quyết bằng cách bỏ security filter, tin URL từ client hoặc allow mọi service**. Một CAS ticket được cấp cho bên nhận khác không được dùng để xác thực app hiện tại.

## 19. Kiểm thử hệ thống với CAS test server

### Test 1 — Ticket hợp lệ

1. Mở một browser session test mới.
2. Truy cập resource bảo vệ, theo redirect tới CAS login đúng service.
3. CAS cấp ST mới, browser quay về callback.
4. App gọi validation HTTPS với đúng ticket/service.
5. CAS trả success, Spring tạo Authentication và HttpSession.
6. Success redirect không còn `ticket</BT> trên URL.
7. Test trang được phép truy cập theo authorization.

### Test 2 — Ticket đã dùng lại

1. Dùng một ST test đăng nhập thành công.
2. Trong lab, gửi lại đúng callback URL chứa ST đó.
3. CAS từ chối attempt thứ hai.
4. App không tạo Authentication mới từ attempt bị từ chối.
5. Handler trả trang lỗi chung, không log/hiển thị ST.
6. Nút đăng nhập lại tạo giao dịch mới; không retry same ST.

### Test 3 — Ticket hết hạn

1. CAS test có ticket expiration policy ngắn hoặc hỗ trợ fault injection.
2. Tạo một ST, cố ý delay validation vượt TTL trong lab.
3. CAS trả validation failure.
4. App hiển thị lỗi chung, không khẳng định “replay attack”.
5. Dùng CAS audit chứng minh expired nếu có dữ liệu.

### Test 4 — Wrong service

1. CAS phát ST cho public URL HTTPS.
2. Client validation sử dụng service URL nội bộ HTTP sai.
3. CAS từ chối `INVALID_SERVICE</BT> theo trường hợp phù hợp.
4. Không retry ST đó.
5. Sửa config, lấy ST mới rồi kiểm tra login thành công.

### Test 5 — Unknown ticket

1. Gửi ticket giả ở môi trường test đã được cấp phép.
2. CAS từ chối, không tạo Authentication.
3. App không xác nhận ticket có từng tồn tại hay không.
4. Đánh giá rate-limit nếu nguồn phát request bất thường.

### Test 6 — Timeout và response mất

1. Dùng network fault injection giữa app và CAS sau khi validation được gửi.
2. CAS có thể đã consume ST trong khi app không nhận response.
3. App fail closed, không retry same ST.
4. Dùng CAS Server logs/audit giải thích tình huống nếu có.
5. Retry UX khởi động login mới sau khi service hồi phục.

### Test 7 — Filter double registration

1. Instrument CAS validation count bằng event/correlation không chứa ST.
2. Thực hiện một browser callback.
3. Nếu cùng ST được validation hai lần do filter ngoài và trong SecurityFilterChain, sửa registration.
4. Không cho CAS bỏ chính sách one-time.

### Test 8 — Local authorization error

1. CAS validate ST thành công.
2. App mapping account không có quyền vào route.
3. Route bị từ chối 403 hoặc policy cụ thể.
4. Không biến authorization failure thành `INVALID_TICKET</BT>.

## 20. Kiểm thử security bổ sung

| Kịch bản tiêu cực | Bảo đảm cần giữ |
| --- | --- |
| XML CAS có `authenticationFailure</BT> | Không tạo Authentication |
| HTTP 200 nhưng XML failure | Không coi HTTP 200 là login success |
| Ticket giả có prefix ST- | Chỉ tin CAS Server validation |
| Reuse ST | CAS phải từ chối validation attempt sau |
| ST được cấp cho service A, dùng ở B | Service binding vẫn được kiểm tra |
| HTTPS hostname mismatch | Không bỏ TLS verification |
| XML chứa DTD/external entity | CAS parser an toàn, chặn XXE |
| User truyền URL CAS validator tùy ý | Không cho phép SSRF |
| Ticket xuất hiện trong query/log | Redact ticket và hạn chế telemetry |
| Untrusted return URL | Không open redirect |
| Browser refresh callback | Fail an toàn, không dùng ST cũ |
| CAS outage | Không fail-open |
| CAS success nhưng mapping user lỗi | Không cấp quyền mặc định cao |
| Multi-node cấu hình không đồng nhất | Phát hiện per-node và xử lý |
| SAML trên cùng nền tảng CAS | Không lẫn CAS protocol handler với SAML provider |

Không dùng ticket hoặc tài khoản của người khác trong negative testing. Thực hiện với IdP/CAS test đã được phép.

## 21. Khi có nhiều pod và browser đồng thời

Một ST có thể đến cùng lúc hai lần:
- Request A đi pod A;
- Request B đi pod B;
- Cả hai gửi `/serviceValidate</BT> cùng ST;
- CAS registry phải có one-time consume an toàn;
- Một validation có thể thành công, còn request còn lại trả INVALID_TICKET.

Không sửa bằng cách cho phép dùng ST hai lần. Cần:
1. Loại double filter registration.
2. Kiểm tra client HTTP retry policy.
3. Bảo đảm browser callback chỉ được phát một lần theo UX.
4. Cân nhắc idempotency ở lớp navigation/UI **không bỏ validation**.
5. Kiểm tra load balancer, duplicate callbacks và session store.
6. Ghi lại validation attempt count cùng trace ID.
7. Đảm bảo các pod có ServiceProperties giống nhau.
8. Không lấy INVALID_TICKET ở request B để kết luận login A không hợp lệ hoặc người dùng bị khóa.

Tương tự, CAS Server cluster cần ticket store đồng nhất; một node không tìm thấy ticket có thể là lỗi cluster/registry, không tự là ticket giả.

## 22. Đặc thù proxy tickets và stateless caching

CAS có **Proxy Ticket (PT)** và endpoint `/proxyValidate</BT> dành cho use case proxy. Spring Security CAS từng hỗ trợ `StatelessTicketCache</BT> cho một số stateful/stateless remoting flows.

Điều phải phân biệt:
- **CAS Server** vẫn áp dụng quy tắc **one-time ticket validation** cho ST/PT theo giao thức.
- **Spring client** có thể cache Authentication đã xác minh trong trường hợp stateless proxy-ticket integration theo contract cụ thể.
- Cache đó không phải quyền chung để browser dùng ST cũ vô hạn.
- Không đem proxy ticket vào `/serviceValidate</BT> rồi coi như service ticket.
- Kiểm tra proxy chain, CAS registration và TicketValidator phù hợp nếu proxy authentication được cho phép.
- Không sao chép ví dụ stateless CAS cũ vào phiên browser login mà chưa đánh giá bảo mật.

Trong bài học này, flow mặc định là **stateful browser CAS login** với ST một lần và local HttpSession sau success.

## 23. Những ngộ nhận cần tránh

1. **“INVALID_TICKET chắc chắn là hết hạn.”** Sai. Có thể replay/unknown/renew failure.
2. **“INVALID_TICKET chứng minh attacker replay.”** Sai. Browser refresh hoặc filter double registration cũng có thể gây.
3. **“CAS /serviceValidate là GET nên có thể retry tùy ý.”** Sai. Validation tiêu thụ ST.
4. **“Sai service thì sửa URL rồi retry cùng ticket.”** Sai. Ticket đã bị vô hiệu hóa.
5. **“Ticket string ST-... đủ để xác thực.”** Sai. ST opaque phải được CAS Server validation.
6. **“CAS XML failure với HTTP 200 vẫn là login thành công.”** Sai.
7. **“Network timeout đồng nghĩa ticket invalid.”** Sai. Có thể CAS đã consume nhưng response mất.
8. **“Spring có ExpiredTicketException chuẩn cho mọi CAS version.”** Không bảo đảm.
9. **“Chỉ cần regex exception message để phân biệt lỗi.”** Sai; không ổn định và có thể lộ ST.
10. **“Tự redirect CAS login mọi lỗi giúp UX tốt hơn.”** Có thể tạo redirect loop với INVALID_SERVICE/outage.
11. **“CSRF 403 luôn do CAS ticket.”** Sai. HTTP security filter/business authorization khác.
12. **“CAS TGC còn làm ST đã dùng hợp lệ lại.”** Sai. TGC có thể giúp cấp **ST mới**.
13. **“Spring Boot auto-registered Filter không thể trùng SecurityFilterChain.”** Sai, phải kiểm soát registration.
14. **“Có thể log raw ticket vì nó hết hạn nhanh.”** Không an toàn: ticket có thể được dùng trước khi tiêu thụ.
15. **“SAML Response error giống CAS INVALID_TICKET.”** Sai, giao thức khác.
16. **“CAS validation fail thì xóa mọi user sessions.”** Không mặc định; session revocation có policy riêng.
17. **“Trả chi tiết ticket có tồn tại cho UI sẽ giúp debug.”** Có thể tạo ticket oracle và information leak.
18. **“Khóa account tại CAS tự cập nhật authorities trong mọi phiên app.”** Không bảo đảm.

## 24. Câu hỏi ôn tập kèm đáp án

**Bài 1.** CAS trả `INVALID_TICKET</BT>. Có thể khẳng định ticket hết hạn không?

**Đáp án:** không. Đây là protocol code chung cho nhiều tình huống; cần CAS Server audit để kết luận khi có bằng chứng.

**Bài 2.** Vì sao retry cùng ST sau timeout không an toàn?

**Đáp án:** CAS có thể đã tiêu thụ ST dù app chưa nhận response; attempt thứ hai sẽ bị từ chối. Cần flow mới lấy ST mới.

**Bài 3.** CAS trả `INVALID_SERVICE</BT> và app sửa cấu hình service URL. Có thể gửi lại ST cũ không?

**Đáp án:** không. CAS spec yêu cầu vô hiệu hóa ST sau validation attempt kể cả wrong service.

**Bài 4.** `CasAuthenticationFilter</BT> và `CasAuthenticationEntryPoint</BT> khác vai trò thế nào?

**Đáp án:** EntryPoint chuyển browser chưa đăng nhập tới CAS. Filter nhận callback ST và qua provider/validator xác minh nó. FailureHandler điều khiển response khi filter authentication thất bại.

**Bài 5.** Nên trả exception stack trace từ CAS Server ra trang lỗi không?

**Đáp án:** không. Có thể chứa ticket và thông tin nội bộ. Dùng thông báo public ngắn cùng trace ID.

**Bài 6.** User refresh callback sau login thành công và thấy INVALID_TICKET. Có chứng minh login ban đầu sai không?

**Đáp án:** không. ST có thể đã được tiêu thụ trong validation thành công; local HttpSession có vòng đời riêng.

**Bài 7.** CAS Server trả HTTP 200 nhưng XML `authenticationFailure</BT>. App có được tạo Authentication không?

**Đáp án:** không. Phải có CAS protocol success được xác minh, không chỉ HTTP 200.

**Bài 8.** Một pod gọi CAS validation hai lần vì filter bean cũng là Servlet Filter. Sửa cách nào?

**Đáp án:** kiểm tra FilterRegistrationBean/SecurityFilterChain, bảo đảm một đường xử lý CAS callback, không tắt CAS one-time.

**Bài 9.** Vì sao trang `/cas-error</BT> nên được permitAll?

**Đáp án:** người dùng chưa authenticated vẫn cần xem thông báo. Nếu trang này bảo vệ, app có thể tự redirect CAS rồi lặp.

**Bài 10.** Nếu CAS hết kết nối TLS, có nên tắt hostname verification để login thành công?

**Đáp án:** không. Sửa CAS endpoint/truststore/cert và network; không bỏ validation.

**Bài 11.** CAS validation success nhưng route app trả 403. Có nên đổi TTL ST không?

**Đáp án:** không mặc định. Đó có thể là authorization/account policy sau xác thực.

**Bài 12.** User logout local, quay lại app được SSO ngay. Có phải ST cũ đã được dùng lại?

**Đáp án:** không. CAS TGT/TGC còn có thể giúp CAS cấp một ST **mới**.

**Bài 13.** Có nên lưu raw ST trong cache để hỗ trợ điều tra replay?

**Đáp án:** không. Dùng audit của CAS Server hoặc correlation đã được bảo vệ; không biến app logs thành kho credentials.

**Bài 14.** Có thể trả riêng “ticket đã tồn tại và bị dùng” cho browser không?

**Đáp án:** không nên. Nếu CAS không có bằng chứng hoặc việc tiết lộ tạo ticket oracle, chỉ báo chung; phân loại kỹ thuật nội bộ.

**Bài 15.** CAS Server trả XML INVALID_TICKET và lỗi network timeout ở hai flow. Chúng có là cùng loại lỗi?

**Đáp án:** không. Một bên là CAS **protocol failure có response**; bên kia là **không xác minh được** do dependency/transport.

**Bài 16.** Khi nào cần kiểm tra service registry?

**Đáp án:** khi có INVALID_SERVICE hoặc service không được cấp phép, đặc biệt sau deploy/reverse-proxy rewrite. Đăng ký public HTTPS callback chính xác, không allow wildcard vô hạn.

## 25. Checklist trước khi đưa production

- [ ] CAS Server và CAS client dùng đúng CAS Protocol endpoint/version.
- [ ] CAS Service Ticket được verify qua backend HTTPS với TLS server authentication.
- [ ] `ServiceProperties.service</BT> khớp callback public và CAS service registration.
- [ ] CAS ST giữ semantics one-time, time-limited, service-bound.
- [ ] Không retry ST cũ sau INVALID_TICKET, INVALID_SERVICE hoặc timeout.
- [ ] Spring CAS filter/provider/validator wiring đúng; không duplicate filter registration.
- [ ] `AuthenticationFailureHandler</BT> đưa browser tới trang public không chứa ST.
- [ ] Trang lỗi không tự redirect CAS liên tục, có nút bắt đầu login mới.
- [ ] Không tạo Authentication/role từ ticket chưa được CAS xác minh.
- [ ] `INVALID_TICKET</BT> không bị diễn giải chắc thành expired/replay/unknown.
- [ ] Nếu cần nguyên nhân chi tiết, có trusted CAS Server audit/typed evidence.
- [ ] Log/metrics không chứa raw ticket, query string, cookie hay sensitive CAS XML.
- [ ] Có trace ID, category, service alias, latency, node và status đã redact.
- [ ] Reverse proxy, ingress, ServiceProperties, CAS registry nhất quán trong multi-node.
- [ ] API và browser response contracts phân biệt rõ; không phải mọi failure đều HTTP 500.
- [ ] CAS outage fail closed cho login mới; không bỏ TLS/cert verification.
- [ ] Không có open redirect qua service/return URL.
- [ ] CSRF, session fixation, user provisioning và authorization sau login vẫn được kiểm tra.
- [ ] Test expired, replay, unknown, wrong service, malformed, timeout, outage, duplicate callback.
- [ ] Kiểm thử browser Refresh, Back, two tabs, long redirect chain, mobile browser.
- [ ] Chọn đúng module CAS; không nhầm SAML 2.0 Web Browser SSO.

## 26. Tổng kết

Khi CAS ticket hết hạn, đã dùng lại hoặc không hợp lệ, ứng dụng phải **từ chối xác thực bằng ticket đó**. CAS Protocol có thể dùng cùng mã `INVALID_TICKET</BT> cho nhiều nguyên nhân; client không nên bịa nguyên nhân chi tiết khi chỉ có một mã chung. Service Ticket **không được retry**, vì nó gắn với service và dùng cho **một validation attempt**.

Tùy chỉnh tốt nằm ở đúng ba lớp: **CAS Server/validator bảo vệ ticket**, **Spring Security CAS filter + AuthenticationFailureHandler trả response an toàn**, và **vận hành dùng audit/metrics có kiểm chứng để điều tra**. Trang lỗi không lộ ST, không tạo vòng lặp login, không tự cấp phiên; người dùng bắt đầu một giao dịch mới khi thích hợp.

### Tài liệu chính thức

1. Apereo CAS — CAS Protocol 2.0 Specification (one-time ST, INVALID_TICKET, INVALID_SERVICE, serviceValidate): https://apereo.github.io/cas/8.0.x/protocol/CAS-Protocol-V2-Specification.html
2. Apereo CAS — CAS Protocol Specification (CAS 3.x and proxy error codes): https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
3. Apereo CAS — Troubleshooting Guide: https://github.com/apereo/cas/blob/master/docs/cas-server-documentation/installation/Troubleshooting-Guide.md
4. Spring Security — CAS Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
5. Spring Security API — CasAuthenticationFilter: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html
6. Spring Security API — CasAuthenticationProvider: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html
7. Spring Security API — AuthenticationFailureHandler: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html
8. Spring Security API — AbstractAuthenticationProcessingFilter: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html
