# CAS: Service Ticket và xác thực tập trung trong Spring Security

## 1. Bài toán: nhiều ứng dụng, một nơi đăng nhập

Giả sử một tổ chức có cổng nhân sự, hệ thống tài liệu và ứng dụng quản trị. Nếu mỗi ứng dụng tự nhận mật khẩu và quản lý phiên đăng nhập, người dùng phải đăng nhập nhiều lần; đội bảo mật cũng phải duy trì nhiều cơ chế xác thực và khó thống nhất chính sách. **Central Authentication Service (CAS)** giải quyết bài toán đó bằng cách đưa khâu xác thực người dùng về **CAS Server**, còn mỗi ứng dụng là một **CAS Service** xác minh chứng cứ đăng nhập do CAS cấp.

Một triển khai CAS điển hình có:

- **CAS Server:** dịch vụ xác thực tập trung, kết nối nguồn danh tính (LDAP/AD, cơ sở dữ liệu, MFA, v.v.) và phát hành ticket.
- **Browser:** điều hướng giữa ứng dụng và CAS, mang cookie phiên SSO của CAS và service ticket trong URL callback.
- **CAS Service (client/application):** ứng dụng Spring Security bảo vệ tài nguyên, chuyển người dùng chưa xác thực sang CAS và **kiểm tra ticket trực tiếp với CAS Server**.
- **Kho người dùng/quyền của ứng dụng:** ánh xạ username hoặc các thuộc tính từ CAS sang tài khoản nội bộ và `GrantedAuthority` để kiểm soát truy cập.

**Mục tiêu bài học:** hiểu `service ticket` (ST), `ticket-granting ticket` (TGT), cookie `TGC`, quy trình redirect và back-channel validation; biết cấu hình Spring Security Servlet sử dụng CAS, phân biệt xác thực tập trung với phân quyền và xử lý bảo mật/đăng xuất/khắc phục lỗi.

CAS ở đây là **Apereo CAS / giao thức CAS**, không phải OAuth 2.0 Authorization Code, không phải OIDC ID Token, cũng không phải “cơ chế session mặc định” của Spring Security. Một CAS Server có thể hỗ trợ các giao thức khác qua module riêng, nhưng bài này tập trung vào **CAS protocol với Service Ticket**.

## 2. Thuật ngữ và trách nhiệm

| Thành phần/khái niệm | Vai trò | Vị trí tồn tại |
| --- | --- | --- |
| **CAS Server** | Xác thực người dùng và cấp, kiểm tra ticket theo policy | Hạ tầng xác thực tập trung |
| **CAS Service** | Ứng dụng sử dụng CAS (ví dụ `https://hr.example.test`) | Backend Spring/Java |
| **service identifier** / `service` | URL định danh **đích mà ST được cấp cho**, ví dụ `https://hr.example.test/login/cas` | Giá trị trong yêu cầu login và validate |
| **Ticket-Granting Ticket (TGT)** | Ticket biểu diễn phiên SSO phía CAS, giúp tạo thêm ST | Được CAS Server quản lý |
| **Ticket-Granting Cookie (TGC)** | Cookie trình duyệt mang tham chiếu phiên TGT của CAS | Trình duyệt, theo phạm vi domain CAS |
| **Service Ticket (ST)** | Chuỗi opaque dạng `ST-...` cấp cho **một service**, dùng để service kiểm tra danh tính | Truyền qua redirect tới callback của service |
| **Local session / JSESSIONID** | Phiên ứng dụng Spring sau khi ticket đã được xác minh | Trình duyệt và ứng dụng |
| **Proxy Ticket (PT)** | Ticket cho một backend khác trong luồng ủy quyền CAS, khác ST | CAS proxy flow (mở rộng) |
| **Authentication** | Danh tính đã được xác minh của request tại ứng dụng | `SecurityContext` của Spring Security |
| **Authorization** | Quyết định user có role/quyền vào tài nguyên hay không | Rule của ứng dụng |

TGT và TGC **không phải** Service Ticket:

- Sau khi user đăng nhập CAS, CAS tạo/duy trì phiên SSO (TGT) và browser nhận TGC theo policy.
- Mỗi lần một ứng dụng đăng nhập qua CAS, CAS phát một **ST mới** dành riêng cho ứng dụng đó.
- Ứng dụng **không** nhận TGT của CAS và không được dùng TGC làm credential trực tiếp.
- ST đã xác minh thành công thường được đổi thành **local authentication/session**; các request tiếp theo sử dụng phiên local, không dùng lại ST.

Ví dụ người dùng đã vào App A, sau đó vào App B: trình duyệt gửi TGC đến CAS khi chuyển từ App B, CAS có thể nhận ra phiên SSO và cấp **ST-B** mới mà không hỏi lại mật khẩu. **ST-A và ST-B khác nhau**, vì được cấp cho các service khác nhau.

## 3. Luồng đăng nhập CAS từng bước

Ví dụ giả định:

~~~text
CAS Server       https://sso.example.test/cas
Ứng dụng Spring  https://hr.example.test
Callback service https://hr.example.test/login/cas
Tài nguyên cần   https://hr.example.test/profile
~~~

Luồng tổng quát:

~~~text
   Browser                     Spring Service                     CAS Server
      |                               |                                |
 (1)  | GET /profile                  |                                |
      |------------------------------>|                                |
 (2)  | 302 → /cas/login?service=...   |                                |
      |<------------------------------|                                |
 (3)  | GET /cas/login?service=...                                      |
      |--------------------------------------------------------------->|
 (4)  |    form login / dùng TGC còn hợp lệ                             |
      |<-------------------------------------------------------------->|
 (5)  | 302 → /login/cas?ticket=ST-...                                  |
      |<---------------------------------------------------------------|
 (6)  | GET /login/cas?ticket=ST-...   |                                |
      |------------------------------>|                                |
 (7)  |                               | GET /cas/serviceValidate       |
      |                               |   ?ticket=ST-...&service=...  |
      |                               |------------------------------->|
 (8)  |                               | XML success + username        |
      |                               |<-------------------------------|
 (9)  | 302 → /profile, local session |                                |
      |<------------------------------|                                |
(10)  | GET /profile + local cookie   |                                |
      |------------------------------>|                                |
      | 200 nội dung đã được cấp quyền|                                |
      |<------------------------------|                                |
~~~

Đọc chi tiết:

1. Browser gọi `/profile`, nhưng chưa có `Authentication` hợp lệ trong phiên Spring.
2. Spring Security phát hiện tài nguyên cần xác thực; `CasAuthenticationEntryPoint` tạo HTTP redirect đến `https://sso.example.test/cas/login` với query parameter `service` trỏ về **callback của ứng dụng**.
3. Browser tới CAS. Nếu chưa có phiên CAS, CAS hiển thị form hoặc quy trình xác thực tập trung (có thể kèm MFA); nếu TGC hợp lệ và policy cho phép SSO, có thể bỏ qua bước nhập mật khẩu.
4. CAS cấp **ST mới cho chính callback đã đăng ký** và redirect browser về `https://hr.example.test/login/cas?ticket=ST-...`.
5. `CasAuthenticationFilter` ở ứng dụng nhận request callback, lấy giá trị `ticket`, tạo một yêu cầu authentication đặc thù CAS rồi chuyển tới `AuthenticationManager`.
6. `CasAuthenticationProvider` dùng `TicketValidator` mở kết nối **server-to-server qua HTTPS** đến CAS `/serviceValidate` với **cùng service URL** và ST.
7. CAS kiểm tra ST còn hợp lệ, chưa dùng và **khớp service**. Nếu thành công, CAS gửi phản hồi chứa username và có thể có attributes; CAS tiêu thụ ST.
8. Provider nạp authorities cho user; Spring thiết lập `SecurityContext`, lưu phiên local nếu đã cấu hình, rồi chuyển về URL đã yêu cầu ban đầu.
9. Browser dùng cookie **của ứng dụng** cho các request sau. Việc giữ TGC ở domain CAS giúp đăng nhập SSO vào ứng dụng khác, nhưng không thay thế cookie của từng ứng dụng.

### URL redirect minh họa

Yêu cầu từ ứng dụng đến CAS:

~~~http
HTTP/1.1 302 Found
Location: https://sso.example.test/cas/login?service=https%3A%2F%2Fhr.example.test%2Flogin%2Fcas
~~~

Sau khi xác thực, CAS redirect về callback:

~~~http
HTTP/1.1 302 Found
Location: https://hr.example.test/login/cas?ticket=ST-example-9a82
~~~

Ứng dụng kiểm tra ST bằng HTTPS server-to-server (URL đã encode ngắn gọn để dễ đọc):

~~~http
GET /cas/serviceValidate?service=https%3A%2F%2Fhr.example.test%2Flogin%2Fcas&ticket=ST-example-9a82 HTTP/1.1
Host: sso.example.test
~~~

Phản hồi thành công dạng CAS 2.0 XML minh họa:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

Trường hợp ticket không hợp lệ, CAS có thể trả:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_TICKET">
    Ticket is invalid or already consumed
  </cas:authenticationFailure>
</cas:serviceResponse>
~~~

Các mã `ST-example-...` ở trên là chuỗi giả định để giải thích giao thức; ứng dụng thực phải để CAS phát hành ticket khó đoán. Không xây dựng ticket bằng username hay tự coi chuỗi bắt đầu bằng `ST-` là đã xác thực.

## 4. Thuộc tính bảo mật của Service Ticket

Một ST không phải password và không phải token có thể tự giải mã:

1. **Opaque:** service không tự suy ra username/claims từ chuỗi ST. Service phải hỏi CAS Server qua validation endpoint.
2. **Gắn với service:** ticket phát cho `https://hr.example.test/login/cas` không được dùng để đăng nhập `https://admin.example.test/login/cas`.
3. **Một lần kiểm tra:** chuẩn CAS yêu cầu ST chỉ được dùng cho **một lần validation attempt**. Dù lần kiểm tra thành công hay thất bại, ticket có thể bị tiêu thụ; vì vậy không retry cùng ST một cách vô điều kiện.
4. **Thời gian sống ngắn:** ST chưa dùng nên có TTL ngắn; thông số cụ thể do CAS Server policy quyết định. Đừng suy rằng “5 phút” là bảo đảm cho mọi triển khai.
5. **Khó đoán:** CAS phát hành chuỗi ngẫu nhiên đủ mạnh, service không tự cấp.
6. **Không thay local session:** sau khi dùng ST, ứng dụng phải quản lý session hoặc một cơ chế state phù hợp của riêng mình.

**Hệ quả thực hành:** một request `GET /login/cas?ticket=ST-...` được browser gửi lại sau khi ST đã được xác minh sẽ **không** được coi là đăng nhập mới hợp lệ. Người dùng có thể vẫn truy cập ứng dụng bằng phiên local đã tồn tại, nhưng việc xác minh lại chính ST đó phải thất bại.

### Chỉ cần kiểm tra prefix “ST-” có an toàn không?

Không. Attacker có thể tự gửi `ticket=ST-anything`. Spring Security phải gọi một `TicketValidator` đáng tin cậy và xác nhận response CAS gắn đúng `service`. Không tạo rule kiểu “có parameter ticket thì authenticated” và không tin user do browser đính kèm ở query/header.

## 5. Service URL: chi tiết nhỏ nhưng thường gây lỗi lớn

Tham số `service` là URL định danh tài nguyên callback mà CAS đã cấp ST. Nó phải được xác định thống nhất giữa:

- `CasAuthenticationEntryPoint` khi redirect đến CAS login.
- `ServiceProperties` bên Spring Security.
- `CasAuthenticationFilter` nhận `/login/cas`.
- `TicketValidator` khi yêu cầu CAS xác minh ticket.
- Danh sách dịch vụ (service registry) được CAS Server cho phép.

Ví dụ:

~~~text
Đúng:
https://hr.example.test/login/cas

Lệch thường gặp:
http://hr.example.test/login/cas            (khác scheme)
https://hr.example.test:8443/login/cas       (khác port)
https://hr.example.test/app/login/cas        (khác context path)
https://hr.example.test/login/cas/           (khác path slash)
https://internal-host:8080/login/cas         (URL backend nội bộ)
~~~

Tùy CAS Server policy/registry, các khác biệt này gây `INVALID_SERVICE`, validation failure hoặc redirect tới URL ngoài whitelist. Không tự “chấp nhận mọi service URL” để sửa nhanh lỗi; cấu hình service registry phải hạn chế chính xác scheme, host, port, path và callback được ủy quyền.

**Khi ứng dụng nằm sau reverse proxy:** URL ngoài là `https://hr.example.test/login/cas`, trong khi backend có thể thấy `http://127.0.0.1:8080`. Hãy cấu hình **service URL cố định theo URL public** và cấu hình forwarding headers theo **trusted proxy**. Không lấy host/scheme tùy tiện từ `X-Forwarded-*` do Internet gửi.

## 6. Endpoint CAS thường gặp

| Endpoint | Ý nghĩa |
| --- | --- |
| `/login?service=...` | Browser được CAS xác thực và nhận ST cho service; có thể dùng TGC cho SSO |
| `/logout` | CAS xử lý đăng xuất phiên trung tâm theo policy |
| `/validate` | Giao thức CAS 1.0, trả `yes/no` đơn giản |
| `/serviceValidate` | Xác minh ST kiểu CAS 2.0, thường trả XML |
| `/p3/serviceValidate` | Validation kiểu CAS 3.0, có thể trả user attributes |
| `/proxyValidate` | Validation có hỗ trợ proxy ticket theo CAS 2.0 |
| `/p3/proxyValidate` | Validation kiểu CAS 3.0 với thông tin proxy/attributes |
| `/proxy` | Cấp proxy ticket cho backend từ một proxy-granting ticket (PGT) hợp lệ |

Một số tham số quan trọng:

- `ticket`: ST đang cần kiểm tra; bắt buộc ở validate.
- `service`: service identifier mà ticket được cấp; **phải khớp**.
- `renew=true`: yêu cầu kiểm tra theo policy yêu cầu user xác thực lại bằng primary credentials thay vì chỉ dựa vào SSO đã có; tránh dùng tùy tiện nếu cần trải nghiệm SSO.
- `gateway=true` ở login: thử SSO thụ động, không buộc hiển thị form login; cần hiểu quy tắc redirect và trường hợp không có phiên CAS.
- `pgtUrl`: callback HTTPS trong luồng proxy ticket, **không cần thiết** cho dịch vụ chỉ nhận ST thông thường.

CAS 2.0 XML có `<cas:authenticationSuccess>` hoặc `<cas:authenticationFailure>`; response của CAS 3 có thể bổ sung attributes. Đừng nhầm CAS protocol 3.0 với “phiên bản 3 của chính CAS Server”; các thế hệ sản phẩm CAS hiện đại có thể hỗ trợ nhiều phiên bản giao thức.

## 7. Các class Spring Security tham gia

Trong **Spring Security Servlet**, module `spring-security-cas` cung cấp phần tích hợp CAS.

| Thành phần | Vai trò |
| --- | --- |
| `CasAuthenticationEntryPoint` | Redirect browser sang CAS login khi request cần xác thực |
| `ServiceProperties` | Khai báo service URL ổn định và policy `sendRenew` |
| `CasAuthenticationFilter` | Nhận `ticket` tại callback, tạo `CasServiceTicketAuthenticationToken` |
| `CasServiceTicketAuthenticationToken` | Request authentication đặc thù CAS trước khi ticket được xác minh |
| `AuthenticationManager` / `ProviderManager` | Chuyển request tới provider nhận CAS token |
| `CasAuthenticationProvider` | Dùng `TicketValidator` xác minh ticket; lấy user/authorities |
| `Cas20ServiceTicketValidator` | Thư viện CAS Java Client gọi endpoint xác minh ST |
| `CasAuthenticationToken` | Authentication đã xác thực sau khi provider xử lý thành công |
| `SecurityContextRepository` | Quyết định cách lưu `SecurityContext`, thường vào HTTP session |
| `UserDetailsService` / authorities mapper | Ánh xạ username do CAS xác nhận sang quyền tại ứng dụng |

Với các phiên bản Spring Security 6.x hiện đại, `CasAuthenticationFilter` tạo `CasServiceTicketAuthenticationToken`. Một số ví dụ tài liệu cũ mô tả `UsernamePasswordAuthenticationToken` đặc biệt; khi triển khai phải đọc API của phiên bản thực tế, tránh copy nội dung Java 5/Servlet XML namespace sang dự án Spring Boot mới.

**Tách nhiệm vụ:** CAS Server xác minh danh tính; Spring `CasAuthenticationProvider` xác minh ticket CAS và tạo `Authentication`; ứng dụng vẫn tự quyết định quyền truy cập. Đăng nhập CAS hợp lệ không có nghĩa là mọi tài nguyên đều được `permitAll`.

## 8. Ví dụ Spring Boot 3.x / Spring Security 6.x (Java 17+)

Ví dụ này là **CAS Service** phía Spring, không triển khai CAS Server. Nó có thể **biên dịch/chạy** sau khi tạo dự án Maven đúng dependency, nhưng việc đăng nhập end-to-end cần một CAS Server hoạt động, URL callback public, chứng thư TLS hợp lệ và tài khoản CAS tương ứng.

### 8.1. Tạo project và dependency

Từ Spring Initializr, chọn **Java 17+**, **Maven**, **Spring Boot 3.5.x**, Spring Web và Spring Security. Boot 3.5.x sử dụng Spring Security 6.5.x tương thích qua dependency management. Bổ sung vào `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-cas</artifactId>
</dependency>
~~~

Dự án cần các dependency do CAS module kéo theo, trong đó có Apereo Java CAS Client (`cas-client-core`). Dùng BOM của Spring Boot để quản lý phiên bản Spring Security; không trộn tùy ý Spring Security 7 với Boot 3 hoặc bản CAS client không tương thích.

### 8.2. Cấu hình service URL

Tệp `src/main/resources/application.properties`:

~~~properties
server.port=8080

# Ví dụ: CAS Server thật mà tổ chức đã triển khai.
cas.server-url-prefix=https://sso.example.test/cas

# URL callback PUBLIC, phải được CAS Server cho phép.
cas.service-url=https://hr.example.test/login/cas
~~~

Nếu ứng dụng nằm sau proxy TLS, hãy để `cas.service-url` là **HTTPS public URL** (không dùng `localhost:8080` nếu browser/CAS không truy cập được). Reverse proxy phải route `/login/cas` về đúng ứng dụng.

### 8.3. Java đầy đủ

Tệp `src/main/java/demo/cas/CasDemoApplication.java`:

~~~java
package demo.cas;

import java.util.Map;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CasDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CasDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            @Value("${cas.server-url-prefix}") String casBaseUrl,
            @Value("${cas.service-url}") String callbackUrl) throws Exception {

        // CAS nhận diện service bằng đúng URL callback này.
        ServiceProperties service = new ServiceProperties();
        service.setService(callbackUrl);
        service.setSendRenew(false);

        // Demo: CAS đã xác nhận user 'alice', còn ứng dụng
        // quyết định có provision user và cấp role hay không.
        var users = new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}not-used-by-cas")
                    .roles("USER")
                    .build()
        );

        var provider = new CasAuthenticationProvider();
        provider.setKey("hr-cas-provider");
        provider.setServiceProperties(service);
        provider.setTicketValidator(
                new Cas20ServiceTicketValidator(casBaseUrl));
        provider.setUserDetailsService(users);

        var manager = new ProviderManager(provider);

        // Dùng cùng repository cho chain và CAS callback filter:
        // Spring Security 6.x yêu cầu lưu context rõ ràng.
        var contextRepository = new HttpSessionSecurityContextRepository();

        var casFilter = new CasAuthenticationFilter();
        casFilter.setFilterProcessesUrl("/login/cas");
        casFilter.setAuthenticationManager(manager);
        casFilter.setServiceProperties(service);
        casFilter.setSecurityContextRepository(contextRepository);

        var entryPoint = new CasAuthenticationEntryPoint();
        entryPoint.setLoginUrl(casBaseUrl + "/login");
        entryPoint.setServiceProperties(service);

        http
            .securityContext(sc ->
                    sc.securityContextRepository(contextRepository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health", "/error", "/login/cas").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex ->
                    ex.authenticationEntryPoint(entryPoint))
            .addFilterAt(casFilter, CasAuthenticationFilter.class);

        return http.build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/health")
        String health() {
            return "CAS service started";
        }

        @GetMapping("/me")
        Map<String, Object> me(Authentication authentication) {
            return Map.of(
                "username", authentication.getName(),
                "authorities", authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList()
            );
        }
    }
}
~~~

**Điểm mấu chốt của ví dụ:**

- `ServiceProperties.service` trỏ đúng callback public mà CAS phát hành ST cho. `CasAuthenticationFilter` mặc định xử lý `/login/cas`; ví dụ đặt rõ đường dẫn để tránh nhầm.
- `CasAuthenticationEntryPoint` dùng CAS login URL và service identifier đã cấu hình, chuyển browser đi khi cần login.
- `Cas20ServiceTicketValidator` gọi CAS qua HTTPS bằng ticket và service URL. Mã Java không tự parse username từ ST, không nhận danh tính chỉ bằng query parameter.
- `CasAuthenticationProvider` dựa vào validation response và nạp thông tin user. User `alice` đã được provision; user CAS khác chưa có trong service sẽ không tự được cấp `ROLE_USER`.
- `ProviderManager` là manager của CAS filter. Đặt provider đúng vào manager mà filter sử dụng; tránh chỉ khai báo bean provider rồi suy rằng mọi filter tự nhận nó.
- `HttpSessionSecurityContextRepository` được **gắn trực tiếp vào CAS filter và security chain**; khi ticket hợp lệ, authentication có thể được lưu để các request sau dùng local session, không lặp validation một ST đã tiêu thụ.
- Chỉ `/health` là route public của ví dụ. `/login/cas` được cho phép đi qua authorization để filter xử lý callback; `permitAll` không có nghĩa là GET callback mang ST giả sẽ tạo một Authentication hợp lệ.
- Demo không tự triển khai SLO, proxy ticket, mapping attribute phức tạp hoặc nhiều tenant. Đó là công việc cần cấu hình riêng.

**Chú ý phiên bản:** ví dụ nhắm đến **Spring Boot 3.5.x / Spring Security 6.5.x**. API và cơ chế quản lý phiên có thể thay đổi khi nâng lên Spring Security 7/Boot 4; cần đối chiếu Javadoc và migration guide của phiên bản dự án trước khi sử dụng.

### 8.4. Chạy và quan sát

Trong thư mục Maven (đã có JDK, Maven hoặc Maven Wrapper):

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell/CMD: `mvnw.cmd spring-boot:run`. Nếu không có wrapper: `mvn spring-boot:run`.

Kiểm tra rằng ứng dụng đã khởi động **khi không cần CAS**:

~~~bash
curl -i http://127.0.0.1:8080/health
~~~

HTTP status và body kỳ vọng:

~~~text
HTTP/1.1 200
...
CAS service started
~~~

Khi đã triển khai theo URL public và CAS cho phép `https://hr.example.test/login/cas`, mở `https://hr.example.test/me` trên browser:

1. Chưa có local session → nhận redirect đến CAS login với tham số `service`.
2. Đăng nhập CAS bằng `alice` hoặc dùng TGC còn hợp lệ → CAS redirect về callback kèm ST.
3. App xác minh ST qua `/serviceValidate`, nạp user `alice` và authority `ROLE_USER`.
4. Browser được đưa về `/me` (theo request cache/success flow), nhận response tương ứng với dữ liệu đã xác thực.

Ví dụ JSON hợp lệ:

~~~json
{
  "username": "alice",
  "authorities": ["ROLE_USER"]
}
~~~

Tùy phiên bản và provider, authentication có thể có các authority bổ sung do framework ghi nhận, ví dụ factor authentication; **không hard-code chính xác toàn bộ mảng authorities ở integration test** nếu chưa xác minh trên phiên bản đang chạy.

Nếu không có CAS Server thực hoặc URL `example.test` chưa được cấu hình DNS/TLS, ví dụ vẫn minh họa cấu hình Java nhưng **không thể hoàn thành login end-to-end**. Đừng xem lỗi DNS tới domain minh họa là lỗi của `CasAuthenticationProvider`.

## 9. Thí nghiệm độc lập bằng Java 17: service binding và one-time validation

Để tự kiểm chứng logic cốt lõi mà không cần CAS Server, chương trình sau mô phỏng **kho ticket** và hai quy tắc: ST chỉ dành cho một service; mọi lần validation đều tiêu thụ ticket.

Đây là **mô hình học tập**, không thực hiện TLS, xác thực mật khẩu, cấp ticket ngẫu nhiên an toàn, session management hoặc CAS protocol XML. Không đưa code mô phỏng này vào hệ thống sản xuất.

Tạo tệp `ServiceTicketRulesDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class ServiceTicketRulesDemo {

    record Ticket(String service, String username) {}

    static boolean validate(
            Map<String, Ticket> issued, String value, String service) {
        // remove() mô phỏng một lần validation attempt,
        // kể cả khi URL service đưa vào sai.
        Ticket ticket = issued.remove(value);
        return ticket != null && ticket.service().equals(service);
    }

    public static void main(String[] args) {
        String hr = "https://hr.example.test/login/cas";
        String admin = "https://admin.example.test/login/cas";

        Map<String, Ticket> tickets = new HashMap<>();
        tickets.put("ST-demo-1", new Ticket(hr, "alice"));

        System.out.println(validate(tickets, "ST-demo-1", hr));
        System.out.println(validate(tickets, "ST-demo-1", hr));

        tickets.put("ST-demo-2", new Ticket(hr, "alice"));
        System.out.println(validate(tickets, "ST-demo-2", admin));
        System.out.println(validate(tickets, "ST-demo-2", hr));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ServiceTicketRulesDemo.java
java ServiceTicketRulesDemo
~~~

**Stdout chính xác:**

~~~text
true
false
false
false
~~~

Giải thích:

- Dòng 1: ST-demo-1 thuộc service HR → lần đầu hợp lệ.
- Dòng 2: ticket đã bị tiêu thụ → replay thất bại.
- Dòng 3: ST-demo-2 được cấp cho HR nhưng bị mang sang Admin → sai service.
- Dòng 4: ST-demo-2 cũng đã tiêu thụ ở lần kiểm tra không khớp → không thể dùng lại.

Trong CAS Server thật, tính hợp lệ còn bao gồm TTL, độ ngẫu nhiên, thời điểm phát hành, trạng thái session/policy và những kiểm tra khác.

## 10. Single Sign-On khác với Single Logout

**SSO:** người dùng xác thực tại CAS một lần; các ứng dụng tiếp theo có thể được cấp ST mới qua TGC. Mỗi service vẫn tạo local session riêng sau khi xác minh ST.

**Local logout:** Spring Security xóa `SecurityContext` và local session/cookie theo cấu hình. Nếu TGC tại CAS còn hợp lệ, browser trở lại ứng dụng có thể được SSO ngay mà không nhập lại mật khẩu.

**Central logout:** CAS Server kết thúc TGT/TGC; tuy nhiên local session đã tạo ở các ứng dụng **không nhất thiết tự biến mất**. Muốn đăng xuất đồng bộ cần **Single Logout (SLO)** hoặc cơ chế tương đương:

- CAS thông báo đến các service đã đăng nhập, theo back-channel/front-channel tương thích.
- Ứng dụng xác thực/kiểm tra logout notification và tìm session tương ứng để invalidation.
- CAS Java Client có các thành phần như `SingleSignOutFilter`/session mapping; cấu hình phải phù hợp filter order, lifecycle và cơ chế lưu session.
- Khi chạy nhiều replica, cần chiến lược session mapping/shared session nhất quán; một map cục bộ trên một instance có thể không tìm thấy phiên nằm ở instance khác.
- SLO phụ thuộc điều kiện mạng/trình duyệt/timeout, nên cần quy trình xử lý trường hợp thông báo thất bại.

**Điểm cần ghi nhớ:** xóa ST khỏi URL sau validation và đóng local session chưa đảm bảo người dùng đã đăng xuất hoàn toàn khỏi CAS. Ngược lại, CAS logout không tự xóa tất cả local session nếu các service chưa tích hợp SLO.

## 11. renew, gateway và trải nghiệm SSO

### 11.1. `sendRenew`

Khi yêu cầu `renew=true`, CAS áp policy đòi primary authentication mới thay vì chỉ chấp nhận phiên SSO trước đó. Trong Spring Security, `ServiceProperties.setSendRenew(true)` yêu cầu behavior tương ứng khi đăng nhập/kiểm tra.

Dùng `renew` khi tài nguyên thực sự cần xác thực lại ở thời điểm truy cập, nhưng cân nhắc UX và tương thích với MFA/IdP policy. Đừng bật trên mọi request nếu yêu cầu tổ chức là SSO liền mạch.

### 11.2. `gateway`

`gateway=true` cho phép browser hỏi CAS có phiên SSO sẵn hay không mà **không buộc form login tương tác**. Nếu không có TGC hợp lệ, CAS có thể redirect về service mà không có ticket. Ứng dụng cần dự kiến nhánh không xác thực; tránh redirect loop.

### 11.3. Chọn lưu phiên hay stateless

Ví dụ web browser thông thường dùng **local HTTP session** sau validation để không phải dùng lại ST. Trong các trường hợp remote/stateless, việc gửi ticket trên mỗi request dễ sai vì ticket chỉ dùng một lần. Spring Security có lớp `StatelessTicketCache` trong tích hợp CAS để hỗ trợ các luồng đặc biệt, nhưng nó không biến ST thành bearer token dùng vô hạn.

Nếu client là SPA/mobile/backend API, cần đánh giá UX, cookie cross-site, CSRF, logout và mô hình phiên trước khi dùng CAS browser redirect. OIDC/OAuth 2.0 có thể phù hợp hơn cho hệ sinh thái API hiện đại; quyết định dựa trên yêu cầu và hạ tầng thực tế.

## 12. Proxy Ticket: mở rộng khi một service gọi service khác

Một Service Ticket cấp cho App A **không được gửi sang Backend B để đăng nhập B**. CAS định nghĩa cơ chế **proxy authentication** cho nhu cầu gọi backend thay mặt user:

1. App A xác minh ST và gửi `pgtUrl` HTTPS đến CAS, nếu App A đã đăng ký làm CAS proxy.
2. CAS xác nhận callback, cấp **proxy-granting ticket (PGT)** và mã liên kết `PGTIOU` theo giao thức.
3. App A dùng PGT gọi CAS `/proxy?targetService=...` để nhận **Proxy Ticket (PT)** cho Backend B.
4. App A chuyển PT đến Backend B.
5. Backend B dùng `/proxyValidate` (không dùng `/serviceValidate` thông thường) để xác minh PT, đồng thời kiểm tra **proxy chain** chỉ gồm proxy được cho phép.

Cơ chế này không tự bật trong demo ST ở trên. Muốn nhận proxy ticket trong Spring Security cần `Cas20ProxyTicketValidator`, cấu hình `CasAuthenticationFilter`/proxy callback, storage PGT, `CasProxyDecider` và giới hạn proxy cho phép. Dùng `AcceptAnyCasProxy` tùy tiện có thể trao quyền ngoài mong muốn.

**Tách biệt:** ST dùng cho browser đăng nhập vào một service; PT phục vụ ủy quyền giữa các service có cấu hình phù hợp. Không tự tái sử dụng ST làm PT.

## 13. Security checklist khi triển khai CAS

### 13.1. Bảo vệ đường truyền và ticket

- Dùng **HTTPS có chứng thư hợp lệ** cho CAS login, CAS validation, callback của service và mọi kênh chứa ticket/cookie.
- JVM phải tin cậy đúng CA của CAS Server; không tắt hostname verification hoặc TLS certificate validation để “đăng nhập được”.
- ST xuất hiện trong URL nên có thể rò qua access log, browser history, proxy logs, monitoring hoặc `Referer`. Xác minh càng sớm càng tốt, làm sạch URL sau callback và không log nguyên ticket.
- Không nhúng ticket vào trang HTML, analytics, URL của tài nguyên bên thứ ba hoặc các redirect không kiểm soát. Thiết lập `Referrer-Policy` phù hợp.
- Xác minh ST bằng kết nối server-to-server đến **đúng CAS Server tin cậy**; không gọi arbitrary URL do client cung cấp.

### 13.2. Service registry và redirect

- CAS Server nên đăng ký whitelist service được phép và URL callback chính xác.
- Không chấp nhận service URL tùy ý hoặc regex quá rộng gây open redirect/ticket delivery tới attacker.
- Cấu hình `ServiceProperties.service` là HTTPS URL public cố định, nhất quán giữa login và validation.
- Sau proxy, chỉ tin forwarded host/proto từ trusted ingress; kiểm soát header spoofing.

### 13.3. Session và quyền

- Cấu hình session fixation protection, cookie Secure/HttpOnly/SameSite theo topology và yêu cầu browser.
- Giữ phân quyền ở ứng dụng; username hợp lệ từ CAS chưa có nghĩa được truy cập mọi endpoint.
- Mapping user/roles phải kiểm soát thay đổi tài khoản, disabled accounts và quyền nhạy cảm.
- Không lưu password CAS ở ứng dụng và không đưa TGC/TGT vào session của ứng dụng.
- Định nghĩa rõ local logout, central logout, SLO, timeout và nhiều instance.

### 13.4. Tính sẵn sàng và quan sát

- CAS Server là thành phần hạ tầng quan trọng; giám sát latency validation, tỷ lệ login thất bại, certificate expiry và outage.
- Đặt timeout hợp lý khi gọi validation; lỗi CAS network phải **fail closed**, không cho qua vì không kiểm tra được ticket.
- Không retry ST tùy tiện sau timeout: lần validation trước có thể đã tiêu thụ ticket dù response bị thất lạc. Cho user đi lại luồng login để nhận ST mới khi cần.
- Audit user/service/trace ID và result code phù hợp; che ticket, cookie và thông tin nhạy cảm.

## 14. Chẩn đoán theo lỗi điển hình

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Redirect vòng lặp giữa App ↔ CAS | Session local không được lưu, cookie không được gửi, callback không match filter, service URL sai | Kiểm tra `CasAuthenticationFilter`, repository, cookie, path và redirect |
| CAS trả `INVALID_SERVICE` | Sai scheme/host/port/path hoặc callback không nằm trong registry | So sánh chính xác URL trong login, validate và service registry |
| CAS trả `INVALID_TICKET` | ST hết hạn, đã validate trước đó hoặc không đúng flow | Quan sát request count và redirect; không retry cùng ST |
| GET `/login/cas?ticket=...` không tạo Authentication | Filter không nằm trong security chain, callback path khác cấu hình, provider không nhận token | Kiểm tra filter order, matcher và manager/provider |
| Ticket hợp lệ nhưng user không vào được | User chưa provision hoặc thiếu `GrantedAuthority` | Kiểm tra CAS username, `UserDetailsService` và policy |
| Lỗi TLS handshake/PKIX | Trust store JVM thiếu CA, hostname certificate sai hoặc proxy TLS cấu hình không đúng | Kiểm tra trust chain, DNS, hostname và proxy upstream |
| Trang vẫn đăng nhập sau local logout | TGC tại CAS còn hợp lệ, browser được SSO lại | Phân biệt local logout với CAS central logout |
| CAS logout nhưng service vẫn truy cập được | SLO chưa tích hợp hoặc local session không bị invalidate | Kiểm tra logout callback, session mapping, cluster |
| Mỗi request đều quay lại CAS | Không tạo/lưu local session, cookie Secure/SameSite/Domain sai | Inspect `Set-Cookie`, request cookie và context repository |
| Dưới reverse proxy tạo `http://internal:8080` | Sai public URL/forwarded header | Cố định `cas.service-url`, cấu hình trusted proxy |
| Login CAS thành công nhưng API admin vẫn 403 | CAS xác nhận danh tính, authorization local không cấp quyền | Kiểm tra authority mapping và access rule |

**Thứ tự debug hiệu quả:** xác minh callback public và service registry → xác minh redirect có tham số service → xem browser có ST quay lại không → xác minh back-channel HTTPS → xem kết quả validation → kiểm tra `Authentication`/session → cuối cùng kiểm tra authorities. Điều này giúp tìm đúng tầng lỗi thay vì sửa quyền để che lỗi ticket.

## 15. So sánh CAS với các cơ chế liên kết danh tính khác

| Tiêu chí | CAS protocol (ST) | OIDC Authorization Code | SAML 2.0 Web SSO |
| --- | --- | --- | --- |
| Mục tiêu chính | SSO web với CAS Server | Đăng nhập liên kết danh tính và claims theo OIDC | SSO doanh nghiệp dựa trên assertion SAML |
| Dữ liệu trả về browser khi login | ST opaque, thường ở `ticket` query | Authorization code, sau đó đổi token ở back-channel | SAML response/assertion |
| Xác minh | Service hỏi CAS validation endpoint | Client trao đổi code với token endpoint rồi xác minh token/claims theo chuẩn | SP kiểm tra chữ ký, issuer, audience, thời gian, correlation |
| Phiên SSO trung tâm | TGT/TGC theo CAS | Session của OpenID Provider | Session của IdP |
| Phân quyền tại app | Vẫn do app quyết định | Vẫn do app quyết định | Vẫn do app quyết định |
| Thích hợp | Hệ sinh thái đã dùng CAS, SSO browser truyền thống | Ứng dụng web, mobile, API hiện đại dùng IdP hỗ trợ OIDC | Hệ sinh thái doanh nghiệp cần SAML |

Không nên tự biến ST thành JWT, token API dài hạn hoặc “code OAuth”. CAS ST có quy tắc **service binding + one-time validation** riêng.

## 16. Bài tập và câu hỏi tự kiểm tra

1. Giải thích sự khác nhau giữa `TGT`, `TGC`, `ST` và local `JSESSIONID`.
2. Người dùng đã login App A qua CAS; khi vào App B có cần dùng lại ST-A không? Vì sao?
3. Vì sao Spring Security phải gọi `/serviceValidate` thay vì tin parameter `ticket`?
4. ST-A cấp cho `https://a.example.test/login/cas` có dùng được tại App B không?
5. Điều gì xảy ra khi service validate lại cùng một ST sau lần thành công?
6. Vì sao CAS logout không chắc chắn xóa phiên trên mọi ứng dụng nếu thiếu SLO?
7. Khi backend chạy trên HTTP sau reverse proxy TLS, service URL cần là HTTP nội bộ hay HTTPS public?
8. `CasAuthenticationProvider`, `TicketValidator` và `UserDetailsService` đóng vai trò khác nhau như thế nào?
9. Khi nào `renew=true` hữu ích và vì sao có thể làm giảm trải nghiệm SSO?
10. Vì sao một service đã xác minh ST vẫn cần rule `hasRole`/`hasAuthority`?

Có thể tự thực hành thêm bằng cách mở Chrome DevTools/Network trong một môi trường CAS test có quyền truy cập và ghi lại **chuỗi request/redirect không chứa ticket thật**: URL login với service, callback, validation phía server (qua log đã được che), cookie CAS và cookie ứng dụng. Đối chiếu chúng với sơ đồ ở mục 3 và các trường hợp lỗi ở mục 14.

## 17. Tài liệu chính thức

- [Apereo CAS — CAS Protocol specification](https://apereo.github.io/cas/8.0.x/protocol/CAS-Protocol-V2-Specification.html)
- [Apereo CAS — Protocol overview](https://github.com/apereo/cas/blob/master/docs/cas-server-documentation/protocol/CAS-Protocol.md)
- [Spring Security — CAS Authentication (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html)
- [Spring Security — CasAuthenticationFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html)
- [Spring Security — CasAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html)
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — Project modules and dependencies](https://docs.spring.io/spring-security/reference/6.5/modules.html)
