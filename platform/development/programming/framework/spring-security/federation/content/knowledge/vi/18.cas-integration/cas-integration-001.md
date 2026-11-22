# ServiceProperties và cấu hình địa chỉ dịch vụ, endpoint xử lý ticket

> **Chủ đề:** Spring Security – federation. **Nhóm kiến thức:** Tích hợp CAS. Bài Knowledge này tập trung vào vai trò của `org.springframework.security.cas.ServiceProperties`, quy tắc xác định **service URL của ứng dụng**, endpoint `CasAuthenticationFilter` tiếp nhận Service Ticket và endpoint CAS server dùng để **xác minh ticket**. Hướng dẫn dành cho Java 17+, ứng dụng Spring Boot Servlet và Spring Security CAS client; ví dụ dùng Spring Security 6.5.x/Boot 3.x tương thích, kèm lưu ý kiểm tra API theo version thực tế.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

1. Phân biệt **CAS Server** với **CAS Service/Client** (ứng dụng Spring cần bảo vệ).
2. Biết tại sao `ServiceProperties.service` thường là **URL HTTPS tuyệt đối của callback trên ứng dụng**, chẳng hạn `https://app.example.org/login/cas`.
3. Giải thích quy tắc **một service URL xuyên suốt ba chặng**: tham số `service` gửi đến `/cas/login`, URL browser quay lại nhận `ticket`, và tham số `service` gửi đến `/cas/serviceValidate`.
4. Phân biệt `CasAuthenticationEntryPoint`, `CasAuthenticationFilter`, `CasAuthenticationProvider`, `TicketValidator` và `AuthenticationManager`; biết bean nào gọi bean nào.
5. Cấu hình `filterProcessesUrl` đúng với **đường dẫn local** của `ServiceProperties.service`, có tính tới context path, HTTPS reverse proxy và port.
6. Hiểu CAS **Service Ticket (ST)** là bằng chứng dùng một lần, gắn với service; không phải phiên trình duyệt của ứng dụng, CAS Ticket-Granting Ticket (TGT) hay JWT.
7. Viết cấu hình Java Spring Security CAS theo mẫu rõ ràng, tránh double-register servlet filter và không bỏ CSRF/authorization.
8. Phát hiện lỗi `INVALID_SERVICE`, `INVALID_TICKET`, vòng lặp login, callback 404 và sai proxy scheme/hostname bằng ma trận kiểm thử.
9. Nắm `sendRenew`, sự khác nhau giữa `/serviceValidate`, `/p3/serviceValidate`, `/proxyValidate` và optional proxy receptor.
10. Áp dụng các biện pháp bảo mật: service registry allowlist, HTTPS, không để ticket lộ trong log/referrer, kiểm soát Host/forwarded headers và không tin ticket từ callback chưa được validate.

**Ý chính:** `ServiceProperties` không phải bean mô tả CAS Server, cũng không phải nơi lưu ticket. Nó là cấu hình về **chính ứng dụng service đang đăng nhập**. Nếu `service` lúc cấp ST khác `service` lúc validate ST, CAS phải từ chối, dù người dùng đăng nhập thành công tại CAS Server.

## 2. Bức tranh tổng thể: CAS Server, browser và Spring Security service

Giả sử:

| Thành phần | URL hoặc định danh minh họa | Vai trò |
| --- | --- | --- |
| **CAS Server base URL** | `https://sso.example.org/cas` | Hệ thống SSO/IdP của tổ chức |
| **CAS Login endpoint** | `https://sso.example.org/cas/login` | Browser được chuyển tới để xác thực |
| **CAS Ticket-validation endpoint** | `https://sso.example.org/cas/serviceValidate` | Backend ứng dụng gửi ST cùng `service` để kiểm tra |
| **Ứng dụng Spring (Service)** | `https://app.example.org` | Service muốn bảo vệ |
| **CAS callback của ứng dụng** | `https://app.example.org/login/cas` | Browser quay lại với `?ticket=ST-...` |
| **`ServiceProperties.service`** | `https://app.example.org/login/cas` | Service identifier gửi đến CAS khi xin và kiểm tra ST |
| **`CasAuthenticationFilter.filterProcessesUrl`** | `/login/cas` | Đường dẫn request **trên ứng dụng**, được filter theo dõi |
| **Trang nghiệp vụ** | `https://app.example.org/reports` | Tài nguyên chỉ người đã xác thực/được phép mới truy cập |

**Điểm dễ nhầm:** `/login/cas` **không** phải URL CAS Server. Nó là đường dẫn callback trên **Spring application**. Trong khi `/cas/login` và `/cas/serviceValidate` nằm trên **CAS Server**. Hai bên có thể đều có chữ "cas" trong đường dẫn, nhưng host, nhiệm vụ, người vận hành và thứ tự xử lý khác nhau.

### 2.1. Luồng đầy đủ

```text
Browser                      Spring Service                    CAS Server
  |                                |                                |
  | GET /reports                   |                                |
  |------------------------------->|                                |
  |                   Chưa có Authentication                         |
  |                                |                                |
  |            CasAuthenticationEntryPoint                            |
  | 302 Location: https://sso.example.org/cas/login?                |
  |          service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas    |
  |<-------------------------------|                                |
  |                                                                 |
  | GET /cas/login?service=...                                       |
  |---------------------------------------------------------------->|
  |                               CAS login/TGT/TGC                  |
  |                               CAS phát ST cho service chính xác  |
  | 302 Location: https://app.example.org/login/cas?ticket=ST-xxx   |
  |<----------------------------------------------------------------|
  |                                |                                |
  | GET /login/cas?ticket=ST-xxx   |                                |
  |------------------------------->|                                |
  |                      CasAuthenticationFilter                     |
  |                      tạo CasServiceTicketAuthenticationToken     |
  |                      AuthenticationManager                      |
  |                      CasAuthenticationProvider                  |
  |                                |                                |
  |                                | GET /cas/serviceValidate       |
  |                                | ?ticket=ST-xxx                 |
  |                                | &service=https://app.../login/cas
  |                                |------------------------------->|
  |                                |     validate ST: service match |
  |                                |<-------------------------------|
  |                         CAS assertion: user alice               |
  |                         UserDetails/authorities                 |
  |                         SecurityContext/HttpSession             |
  | 302 /reports hoặc success URL  |                                |
  |<-------------------------------|                                |
  | GET /reports với cookie phiên ứng dụng                           |
  |------------------------------->|                                |
  |<-------------------------------| 200 (nếu được phân quyền)       |
```

Ở ví dụ này, có **một URL callback cố định** để tạo ST và validate ST. Nguyên tắc này giúp loại bỏ một lớp lỗi phổ biến: dùng URL trang nghiệp vụ làm `service` ở bước login nhưng lại dùng callback `/login/cas` khi validate.

### 2.2. CAS protocol là gì và khác SAML/OIDC ở điểm nào?

CAS protocol truyền **service ticket là chuỗi opaque** qua browser query parameter `ticket`. CAS client dùng kết nối backend tới CAS Server để kiểm tra ticket và nhận định danh người dùng, thường qua XML ở `/serviceValidate` hoặc `/p3/serviceValidate`. Đừng tự decode ST như JWT hay SAMLResponse; ST tự nó không chứa claim cho ứng dụng tin. Điểm tin cậy là **kết quả validation từ CAS Server đã được xác thực qua TLS/đúng endpoint**.

Một IdP Apereo CAS có thể đồng thời hỗ trợ SAML2/OIDC, nhưng khi ứng dụng dùng **CAS protocol**, các bean `ServiceProperties`/`CasAuthenticationFilter` và luồng ST khác với `saml2Login` hoặc `oauth2Login`. Không cấu hình `RelyingPartyRegistration` SAML rồi mong nó thay thế được `ServiceProperties` CAS.

## 3. `ServiceProperties` đại diện cho **service ứng dụng**, không phải CAS Server

Class `org.springframework.security.cas.ServiceProperties` chứa các thông tin thiết yếu của ứng dụng đang tham gia CAS. Theo Java API Spring Security, những thuộc tính đáng chú ý là:

| Thuộc tính/method | Vai trò | Giá trị/phạm vi thường dùng |
| --- | --- | --- |
| `setService(String)` / `getService()` | **Service URL** chính thức của Spring service | `https://app.example.org/login/cas` |
| `setSendRenew(boolean)` / `isSendRenew()` | Chỉ thị gửi `renew` khi login/validate, yêu cầu primary credential authentication theo CAS semantics | `false` mặc định |
| `setArtifactParameter(String)` / `getArtifactParameter()` | Tên request parameter mang artifact/ticket | `ticket` mặc định |
| `setServiceParameter(String)` / `getServiceParameter()` | Tên tham số dịch vụ CAS | `service` mặc định |
| `setAuthenticateAllArtifacts(boolean)` / `isAuthenticateAllArtifacts()` | Bật cách xử lý artifact ở nhiều URL, hữu ích cho proxy tickets trong trường hợp nâng cao | Thường để mặc định `false` cho ST login đơn giản |
| `afterPropertiesSet()` | Kiểm tra cấu hình bean khi Spring khởi tạo | Không thay thế validation ticket |

**Nhầm lẫn thường gặp:** `service` **không** phải `https://sso.example.org/cas`. Địa chỉ đó là **CAS Server base URL** để tạo `Cas20ServiceTicketValidator`. Cũng không phải `https://sso.example.org/cas/login` vì đó là nơi bắt đầu đăng nhập ở CAS. Và không phải URL trang yêu cầu bảo vệ `/reports` nếu filter đang nhận ST ở `/login/cas`.

### 3.1. Ví dụ tối thiểu khai báo ServiceProperties

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.cas.ServiceProperties;

@Configuration
public class CasServicePropertiesConfig {

    @Bean
    ServiceProperties serviceProperties() {
        ServiceProperties properties = new ServiceProperties();
        properties.setService("https://app.example.org/login/cas");
        properties.setSendRenew(false);
        return properties;
    }
}
```

Đây là một Spring configuration class **trong ứng dụng có classpath Spring Security CAS**, không phải chương trình Java thuần chạy bằng `javac` khi chưa có dependency. File thực tế cần một package declaration đúng với project, ví dụ `package com.example.casdemo;` ở đầu file và lưu tại `src/main/java/com/example/casdemo/CasServicePropertiesConfig.java`.

`ServiceProperties` **chỉ là một phần** của cấu hình. Nếu chỉ có bean này, người dùng chưa thể đăng nhập CAS vì còn thiếu entry point, filter, provider, ticket validator và filter chain đúng.

### 3.2. Vì sao `service` cần là HTTPS URL tuyệt đối?

CAS Server dùng `service` như **đích trả ticket**, đồng thời liên kết ST được cấp với service identifier đó. Một URL hợp lệ cần có:

- Scheme `https` đúng với đường browser thực tế truy cập vào ứng dụng.
- Hostname public/canonical mà CAS Server cho phép trong **service registry**.
- Port thật khi không dùng cổng HTTPS chuẩn, nếu endpoint thực có port riêng.
- Context path (nếu ứng dụng được triển khai dưới `/portal`, `/finance`, ...).
- Path callback chính xác mà `CasAuthenticationFilter` xử lý, thường `/login/cas`.
- Query tĩnh chỉ nếu kiến trúc đã cố ý dùng và đã kiểm thử CAS/service matching; nên giữ callback đơn giản, **không** kèm query nghiệp vụ động.

CAS protocol khuyến nghị chỉ cho các `service` URL đã đăng ký/được duyệt, ưu tiên HTTPS. Không cho bất kỳ website nào gắn `?service=https://attacker...` để nhận ST; cấu hình CAS service registry cần giới hạn URL rõ ràng và được quản trị có phê duyệt.

### 3.3. Ba nơi phải giữ thống nhất service identifier

```text
A. Spring ServiceProperties.getService()
   https://app.example.org/login/cas

B. CAS /login?service=...
   https://app.example.org/login/cas

C. CAS /serviceValidate?service=...&ticket=ST-xxx
   https://app.example.org/login/cas

=> A == B == C (theo chính sách so khớp service CAS)
```

CAS Server phải xác minh `service` dùng để validate tương ứng chính xác với service mà ST được cấp. Không thể lấy một ticket cấp cho `https://app.example.org/login/cas` rồi validate dưới `http://app-internal:8080/login/cas` hay `https://other.example.org/login/cas`.

**Không nối `?ticket=ST-xxx` vào `ServiceProperties.service`.** `ticket` là tham số CAS server thêm vào **callback browser**; khi validate, ứng dụng gửi ticket thành **tham số riêng** cùng giá trị service identifier gốc.

## 4. Phân biệt service URL và filterProcessesUrl

Một bất biến quan trọng là:

```text
ServiceProperties.service =
    "https://app.example.org/portal/login/cas"

CasAuthenticationFilter.filterProcessesUrl =
    "/login/cas"
```

Ví dụ này đúng khi ứng dụng Servlet có `context-path=/portal` và filter matcher áp dụng với đường dẫn **bên trong context**. Spring Security filter thường match path application tương ứng `/login/cas`; URL đầy đủ từ browser còn thêm scheme/host/context path `/portal`.

Khi không có context path:

```text
ServiceProperties.service =
    "https://app.example.org/login/cas"

CasAuthenticationFilter.filterProcessesUrl =
    "/login/cas"
```

Đừng viết `setFilterProcessesUrl("https://app.example.org/login/cas")` để bắt chước service, vì filter xử lý **đường dẫn request trong ứng dụng**, không match URL tuyệt đối theo cấu hình thông thường. Ngược lại, đừng viết `setService("/login/cas")` và mong CAS Server biết host/HTTPS của ứng dụng.

### 4.1. So sánh vài triển khai

| Deployment public | URL `service` đúng | Local `filterProcessesUrl` |
| --- | --- | --- |
| Root context, HTTPS 443 | `https://app.example.org/login/cas` | `/login/cas` |
| Context path `/portal` | `https://app.example.org/portal/login/cas` | `/login/cas` |
| Cổng HTTPS 8443 | `https://app.example.org:8443/login/cas` | `/login/cas` |
| Reverse proxy path prefix `/finance` | `https://app.example.org/finance/login/cas` | `/login/cas` **nếu** proxy/context mapping khiến servlet thấy `/login/cas`; kiểm tra thực tế |
| CAS service chạy trên subdomain riêng | `https://pay.example.org/login/cas` | `/login/cas` |
| Local development `localhost` | `https://localhost:8443/login/cas` khi có TLS và CAS registry dev | `/login/cas` |

**Chú ý reverse proxy prefix:** Nếu proxy không strip `/finance` và servlet thấy cả prefix ở path xử lý, matcher có thể cần điều chỉnh. Không tự cắt path bằng `replace` trong code auth để “cho khớp”; trước hết chuẩn hóa cấu hình ingress, context path và servlet path. Đọc Network redirect, request URI và path matcher thực sự trong test.

### 4.2. Những sai khác thường khiến `INVALID_SERVICE`

```text
https://app.example.org/login/cas
https://app.example.org/login/cas/
http://app.example.org/login/cas
https://app.example.org:8443/login/cas
https://app.example.org/portal/login/cas
https://app-internal:8080/login/cas
```

Những URL này không nên được coi là cùng một service identifier chỉ vì tên path có từ "cas". Đặc biệt scheme, port, path và trailing slash có thể tạo khác biệt. Một số CAS deployments có cấu hình service matching/regex riêng; **cấu hình lenient không phải là giải pháp bảo mật** để che URL sai. Nên xuất và sử dụng một URL canonical đã thỏa thuận ở cả Spring app và CAS service registry.

## 5. Những thành phần Spring Security CAS và trách nhiệm của mỗi thành phần

| Thành phần | Package (Spring Security) | Trách nhiệm |
| --- | --- | --- |
| `ServiceProperties` | `org.springframework.security.cas` | Cấu hình service URL, `renew` và tham số ticket/service |
| `CasAuthenticationEntryPoint` | `org.springframework.security.cas.web` | Khi chưa đăng nhập, redirect browser đến CAS `/login` cùng `service` |
| `CasAuthenticationFilter` | `org.springframework.security.cas.web` | Theo dõi callback `/login/cas`, lấy `ticket`, tạo authentication request |
| `CasAuthenticationProvider` | `org.springframework.security.cas.authentication` | Gọi `TicketValidator` để kiểm ticket và tải authorities/principal |
| `Cas20ServiceTicketValidator` | `org.apereo.cas.client.validation` | Gọi CAS `/serviceValidate` với `ticket` và `service` |
| `AuthenticationManager` / `ProviderManager` | `org.springframework.security.authentication` | Điều phối AuthenticationProvider xử lý CAS token |
| `UserDetailsService` hoặc `AuthenticationUserDetailsService` | Spring Security core | Ánh xạ user từ CAS assertion sang local account/authorities |
| `SecurityFilterChain` | `org.springframework.security.web` | Đảm bảo filter CAS/entry point/security context và authorization nằm đúng chuỗi |
| `SecurityContextRepository` | `org.springframework.security.web.context` | Lưu SecurityContext thành công để request tiếp theo có Authentication |
| `HttpSession` hoặc Spring Session | Servlet/Spring Session | Phiên ứng dụng, **khác** TGT/TGC trên CAS Server |

### 5.1. Thứ tự xử lý khi có callback

1. Browser gọi `GET /login/cas?ticket=ST-...` trên **Spring app**.
2. `CasAuthenticationFilter` có matcher trùng `filterProcessesUrl` nên trích xuất ticket từ request parameter mặc định `ticket`.
3. Filter tạo `CasServiceTicketAuthenticationToken` để gửi tới `AuthenticationManager`.
4. `CasAuthenticationProvider` chọn đúng `TicketValidator`, truyền **ST + `ServiceProperties.service`** tới CAS validation endpoint.
5. CAS Server kiểm ST chưa hết hạn/chưa tiêu thụ và được phát cho service đó, trả thành công kèm principal hoặc thất bại `INVALID_TICKET`/`INVALID_SERVICE`.
6. Provider tạo authenticated `CasAuthenticationToken` từ CAS assertion và áp user details/authorities theo cấu hình.
7. Spring Security lưu `SecurityContext`, tạo/rotate local app session theo chính sách và chuyển user tới URL trước đó hoặc success URL.
8. Các request tiếp theo dùng app session cookie, không cần replay ST.

**Không nên tạo MVC `@GetMapping("/login/cas")` để tự gọi CAS REST rồi tạo session thủ công.** Endpoint này phải do security filter xử lý; MVC controller không thay thế các kiểm tra của CAS client.

### 5.2. Những khác biệt quan trọng giữa các endpoint

`/login/cas` trong ứng dụng là nơi **nhận ticket**. `/cas/serviceValidate` trên CAS Server là nơi **kiểm tra ticket**. Khi tên đường dẫn giống nhau, việc dùng sai host là nguồn lỗi nghiêm trọng. Người đọc nên luôn ghi rõ “server” hoặc “client” trong tài liệu và log.

## 6. CAS protocol endpoints: chọn đúng validator

| Endpoint CAS Server | Mục đích | Khi nào dùng |
| --- | --- | --- |
| `/cas/login` | Đăng nhập CAS, cấp Service Ticket và redirect về `service` | Browser SSO |
| `/cas/validate` | CAS 1.0 validation trả văn bản đơn giản | Hệ thống cũ; không ưu tiên khi cần thuộc tính |
| `/cas/serviceValidate` | CAS 2.0 validation trả XML, xác thực Service Ticket | `Cas20ServiceTicketValidator` tiêu chuẩn |
| `/cas/p3/serviceValidate` | CAS 3.0 validation, có thể trả user attributes | Khi client/protocol được cấu hình tương thích |
| `/cas/proxyValidate` | Kiểm Service Ticket và Proxy Ticket theo chính sách | Proxy authentication nâng cao |
| `/cas/p3/proxyValidate` | CAS 3.0 proxy validation + attributes | Chỉ khi cần proxy |
| `/cas/logout` | Kết thúc phiên SSO ở CAS Server | Khác local `/logout` của app |
| `/cas/proxy` | Yêu cầu Proxy Ticket sử dụng PGT | Luồng CAS proxy ủy quyền, không phải login thông thường |

**Đừng nhầm `/cas/serviceValidate` với ServiceProperties.service.** `ServiceProperties.service` là URL **của ứng dụng**, thường `https://app.example.org/login/cas`. Trong khi validator nhận base `https://sso.example.org/cas` và tự gọi endpoint validation tương ứng theo protocol.

### 6.1. Ví dụ CAS validation request/response

CAS Server nhận:

```http
GET /cas/serviceValidate?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas&ticket=ST-EXAMPLE HTTP/1.1
Host: sso.example.org
```

Nếu ticket do chính service đó được cấp và chưa bị dùng/expire, server có thể trả:

```xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>alice</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
```

Nếu giá trị `service` không khớp:

```xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_SERVICE">
    Service identifier does not match the issued ticket.
  </cas:authenticationFailure>
</cas:serviceResponse>
```

Đây là **dữ liệu minh họa**, không phải ST thật hoặc kết quả có thể dự đoán từ server public. Không dùng chuỗi `ST-EXAMPLE` để kỳ vọng login thành công; CAS chỉ chấp nhận ST do chính nó cấp và trong chính sách hiệu lực.

**CAS `INVALID_SERVICE` là tín hiệu cực kỳ đáng giá:** kiểm tra ngay service URL ở entry point, callback browser và TicketValidator; không kết luận là sai mật khẩu người dùng.

### 6.2. ST không phải access token dùng lại

Theo CAS protocol, ST:

- Được phát cho **một service identifier cụ thể**.
- **Chỉ dùng một lần khi validation**: CAS phải vô hiệu sau một lần thử validate, kể cả validation thất bại.
- Thường có thời hạn ngắn; không được để trong cache ứng dụng như long-lived login credential.
- Được browser chuyển qua query parameter `ticket` nên có nguy cơ đi vào browser history, reverse proxy access log và Referer; phải giảm nguy cơ lộ.
- Không được đưa qua JavaScript client hoặc nhận qua API do user tự khai rồi cấp quyền mà bỏ backend CAS validation.

Khi người dùng bấm refresh callback cũ, ST đã tiêu thụ có thể bị từ chối. Đó là hành vi bảo vệ replay, không phải CAS Server mất session; luồng login mới có thể phát ST mới nếu TGT/TGC còn hợp lệ.

## 7. Spring Boot/Java 17: một ứng dụng demo CAS hoàn chỉnh về cấu hình

### 7.1. Dependency và version

Ví dụ nhắm **Spring Boot 3.x tương thích Spring Security 6.5.x**, Java 17+, Servlet/MVC. CAS integration **không** nằm trong một starter CAS chuyên biệt của Boot; cần thêm module Spring Security CAS.

Trong Maven project có Spring Boot dependency management, thêm:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-cas</artifactId>
  </dependency>
</dependencies>
```

Đây là **fragment `pom.xml`**, không phải POM tự chạy; project cần parent/BOM, build plugin và repositories phù hợp. `spring-security-cas` trong các phiên bản được kiểm tra phụ thuộc Apereo CAS client core; kiểm bằng `mvn dependency:tree` nếu dự án có exclusions/version conflicts, và quản lý phiên bản theo Spring Boot/Security BOM.

CAS Server phải là môi trường test đã chạy được, không phải do ba dependency trên tự tạo. Dùng JDK 17+, CAS Server có HTTPS được client tin, một user test `alice` và dịch vụ đã đăng ký.

### 7.2. Cấu hình application.yml

File `src/main/resources/application.yml`:

```yaml
server:
  port: 8080
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

app:
  cas:
    server-base-url: https://sso.example.org/cas
    login-url: https://sso.example.org/cas/login
    service-url: https://app.example.org/login/cas
```

**Lưu ý:** Đây là mô hình ứng dụng được public qua reverse proxy HTTPS `app.example.org:443`, backend nghe HTTP 8080. `forward-headers-strategy: framework` chỉ phù hợp nếu reverse proxy **được tin, loại bỏ forwarded headers do browser tự gửi** và thiết lập đúng header trước khi chuyển vào app. Nếu chạy local không có proxy, `cookie.secure=true` có thể khiến browser HTTP localhost không gửi cookie; dùng profile phát triển riêng có TLS/test certificate và service URL/registered service tương ứng. Không tắt HTTPS production để “chạy được”.

Các domain `example.org` là giá trị minh họa; **phải thay toàn bộ bằng CAS test/ứng dụng có DNS, TLS và service registry thực tế**. Không có CAS Server test thì demo cấu hình không thể hoàn tất login.

### 7.3. Spring Security configuration class

File `src/main/java/com/example/casdemo/CasSecurityConfig.java`:

```java
package com.example.casdemo;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.apereo.cas.client.validation.TicketValidator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

@Configuration
public class CasSecurityConfig {

    @Bean
    ServiceProperties serviceProperties(
        @Value("${app.cas.service-url}") String serviceUrl) {

        ServiceProperties properties = new ServiceProperties();
        properties.setService(serviceUrl);
        properties.setSendRenew(false);
        return properties;
    }

    @Bean
    TicketValidator ticketValidator(
        @Value("${app.cas.server-base-url}") String casBaseUrl) {

        return new Cas20ServiceTicketValidator(casBaseUrl);
    }

    // Lab only: tài khoản này đã tồn tại trong CAS test.
    // CAS kiểm danh tính; UserDetailsService gán quyền local.
    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}unused-for-cas")
                .roles("USER")
                .build());
    }

    @Bean
    CasAuthenticationProvider casAuthenticationProvider(
        ServiceProperties properties,
        TicketValidator validator,
        UserDetailsService users) {

        CasAuthenticationProvider provider =
            new CasAuthenticationProvider();
        provider.setServiceProperties(properties);
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);
        provider.setKey("cas-demo-provider-v1");
        return provider;
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain casWeb(
        HttpSecurity http,
        ServiceProperties properties,
        CasAuthenticationProvider provider,
        SecurityContextRepository contextRepository,
        @Value("${app.cas.login-url}") String casLoginUrl)
        throws Exception {

        CasAuthenticationEntryPoint entryPoint =
            new CasAuthenticationEntryPoint();
        entryPoint.setServiceProperties(properties);
        entryPoint.setLoginUrl(casLoginUrl);

        // KHÔNG khai báo @Bean Filter này để Spring Boot
        // không auto-register thêm một servlet Filter ngoài chain.
        CasAuthenticationFilter casFilter =
            new CasAuthenticationFilter();
        casFilter.setServiceProperties(properties);
        casFilter.setFilterProcessesUrl("/login/cas");
        casFilter.setAuthenticationManager(
            new ProviderManager(provider));
        casFilter.setSecurityContextRepository(contextRepository);
        casFilter.setAuthenticationFailureHandler(
            new SimpleUrlAuthenticationFailureHandler("/cas-error"));

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out",
                    "/cas-error", "/error").permitAll()
                .requestMatchers("/reports/**").hasRole("USER")
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint))
            .securityContext(context -> context
                .securityContextRepository(contextRepository))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true));

        http.addFilterAt(casFilter, CasAuthenticationFilter.class);
        return http.build();
    }
}
```

**Giải thích từng phần:**

- `ServiceProperties.service` lấy từ `app.cas.service-url`, không tự sinh từ raw `Host` header.
- `Cas20ServiceTicketValidator` lấy **CAS Server base URL** để gọi `/serviceValidate`, không nhận callback URL của app.
- `CasAuthenticationProvider` kiểm ST qua validator và dùng `UserDetailsService` để nạp quyền cục bộ. Password demo `{noop}unused-for-cas` **không được dùng để xác thực CAS**; đây chỉ là một user fixture rõ ràng trong lab, không phải hướng dẫn lưu password production.
- `CasAuthenticationEntryPoint` redirect đến CAS login cùng đúng service từ ServiceProperties.
- `CasAuthenticationFilter` theo dõi `/login/cas`, dùng `ProviderManager` và lưu `SecurityContext` thông qua repository dùng chung với chain.
- `setFilterProcessesUrl("/login/cas")` là **path filter**, khác `https://app.example.org/login/cas` là **service URL**.
- `http.addFilterAt(casFilter, CasAuthenticationFilter.class)` đưa CAS filter vào vị trí security chain. Filter được **tạo bên trong** phương thức chain thay vì expose thành `@Bean`, tránh Spring Boot tự đăng ký như global servlet filter và có nguy cơ xử lý ticket hai lần.
- `CasAuthenticationProvider` vẫn là bean cấu hình; `ProviderManager` dành cho CAS filter có một provider, không yêu cầu một provider mật khẩu/form login.
- `SecurityContextRepository` được gán nhất quán, giúp authentication sau CAS callback tồn tại qua request tiếp theo trong HttpSession khi cấu hình phù hợp.
- `requestMatchers("/reports/**").hasRole("USER")` chỉ minh họa phân quyền. Production phải kiểm user/account status, tenant/role/resource và policy của chính app.
- `/cas-error` và `/signed-out` chỉ được `permitAll`, **chưa tự có trang MVC**; cần controller/template được cung cấp như mục tiếp theo.
- Local `/logout` **không** tự gọi CAS Server logout/SLO. Với CSRF bật, logout nên dùng **POST có CSRF token**.
- Callback `/login/cas` **không** bị `web.ignoring`, không bị đưa ra khỏi chain và không được xử lý bằng controller thủ công.
- Spring Security không tự bảo đảm một CAS username khớp account người dùng trong DB hay đúng tenant; demo chỉ có `alice`. Production cần `UserDetailsService` đọc user/authorities từ nguồn nội bộ đã kiểm soát.

**Phụ thuộc phiên bản:** Spring Security 6.x sử dụng Servlet API Jakarta và có các method nêu trên. API giữa Spring Security 6.x/7.x, CAS client transitive dependencies và Boot version có thể thay đổi; đối chiếu Javadoc và build bằng đúng BOM của project trước khi áp dụng. Đây là class Spring nằm trong project, không biên dịch standalone với JDK không có dependencies.

### 7.4. Controller và Spring Boot application class

File `src/main/java/com/example/casdemo/CasDemoApplication.java`:

```java
package com.example.casdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CasDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CasDemoApplication.class, args);
    }
}
```

File `src/main/java/com/example/casdemo/DemoController.java`:

```java
package com.example.casdemo;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of("message", "Public CAS demo page");
    }

    @GetMapping("/reports")
    public Map<String, String> reports(Authentication authentication) {
        return Map.of(
            "message", "Protected report",
            "principal", authentication.getName());
    }

    @GetMapping("/cas-error")
    public Map<String, String> casError() {
        return Map.of("status", "CAS authentication failed");
    }

    @GetMapping("/signed-out")
    public Map<String, String> signedOut() {
        return Map.of("status", "Local application session ended");
    }
}
```

**Cần có:** Spring Boot Maven/Gradle app tương thích, IdP/CAS Server test, HTTPS reverse proxy, service registration và user `alice` trên CAS Server lẫn fixture local. Nếu CAS trả principal khác, lab sẽ fail ở `UserDetailsService` dù ticket được CAS verify; đó là **bước phân quyền/local mapping** riêng, không phải lý do bỏ ticket validation.

### 7.5. Chạy kiểm thử tích hợp

Trong dự án đã có Maven wrapper và đã đặt CAS Server test hợp lệ:

```bash
./mvnw spring-boot:run
```

Trên Windows có thể dùng `mvnw.cmd spring-boot:run`. Trước khi mở browser, kiểm tra reverse proxy public `https://app.example.org` thực sự route đến port backend 8080, service URL nằm trong CAS registry, CAS login URL reachable và truststore Java tin đúng chứng thư TLS của CAS Server.

Nếu không có CAS Server test, chỉ có thể chạy tới bước redirect hoặc gặp lỗi validation; **không có lệnh Spring Boot nào tự biến ví dụ thành CAS Server**. Việc kiểm tra liên hệ với hệ thống thật phải diễn ra trong môi trường staging có quyền.

## 8. Thiết lập service registry phía CAS Server

CAS Server thường có **service registry** quy định ứng dụng nào được phép yêu cầu CAS login/ticket. Để dùng `https://app.example.org/login/cas`, phía CAS phải có đăng ký tương ứng, theo format/management API và version CAS thực tế.

**Ví dụ tư duy policy:**

```text
Registered service:
  id              = app-cas-demo
  serviceId        = https://app.example.org/login/cas
  enabled          = true
  owner            = team-app
  redirect / CAS protocol allowed = theo policy
  permitted authentication policy = theo hợp đồng
```

Trên nhiều phiên bản Apereo CAS, `serviceId` của RegisteredService có thể là **regular expression** hoặc được kiểm soát bởi chiến lược matching của CAS; do đó URL example trên là **ý nghĩa đăng ký**, không phải khẳng định mọi CAS Server cho phép copy nguyên YAML này vào production.

**Nếu dùng regex**, phải escape dấu chấm, neo đầu/cuối và giới hạn HTTPS/hostname/path. Regex quá rộng như `.*`, `https?://.*`, `https://.*example.org/.*` có thể chấp nhận service do kẻ khác kiểm soát hoặc host gần giống. Đăng ký phải do người có thẩm quyền phê duyệt, không lấy serviceId từ browser hoặc ticket chưa verify.

### 8.1. Client configured không đủ nếu CAS Server không đăng ký service

Trình tự:

1. App xác định fixed `serviceUrl`.
2. CAS admin đăng ký **chính URL public** với chính sách phù hợp.
3. Đối chiếu browser redirect thực nhận `/cas/login?service=...`.
4. Đối chiếu `/serviceValidate?service=...`.
5. Kiểm `INVALID_SERVICE`/unauthorized service log nếu CAS từ chối cấp/validate ticket.
6. Chốt cấu hình ở **hai nơi** trước khi test nhóm user.

Không phải mọi lỗi `INVALID_SERVICE` đều do thiếu đăng ký; có thể CAS cho cấp ST cho một URL nhưng validator đang kiểm ST dưới URL khác. Cần xác định lỗi xảy ra ở **request login** hay **request validate** để tìm đúng bên.

## 9. Reverse proxy/ingress và sai URL công khai

Triển khai thường có:

```text
Browser
  |
  | HTTPS https://app.example.org/login/cas
  v
Reverse proxy / Ingress :443
  |
  | HTTP http://app-backend:8080/login/cas
  v
Spring Boot :8080
  |
  | HTTPS https://sso.example.org/cas/serviceValidate
  v
CAS Server
```

Nếu ứng dụng tự dựng `service` từ `request.getScheme()`/`getServerName()` phía backend, nó có thể thành `http://app-backend:8080/login/cas`. CAS Server lúc cấp ticket dùng `https://app.example.org/login/cas`, validation lại dùng địa chỉ nội bộ, gây `INVALID_SERVICE`.

### 9.1. Cách cấu hình an toàn

- Với **service URL một giá trị ổn định**, ưu tiên cấu hình tường minh `app.cas.service-url=https://app.example.org/login/cas` và dùng cùng `ServiceProperties` cho entry point, filter và provider.
- Cho reverse proxy quản lý TLS/Host/port/path rewrite. Chỉ tin `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port` đến từ proxy được phê duyệt, xóa giá trị browser tự đưa vào.
- Bảo đảm `server.forward-headers-strategy` phù hợp topology; **không coi bật nó là giải pháp thần kỳ** nếu proxy chuyển header giả hoặc app dùng hard-coded URL sai.
- Xác minh context path và `filterProcessesUrl` nhận trên Spring app. Nếu proxy thêm prefix, xác định chính xác ai strip prefix.
- Không thay `ServiceProperties.service` theo raw `Host`/`Referer` hay query parameter do user đưa.
- Không thêm HTTP internal URL vào CAS service registry chỉ để “fix” production HTTPS.
- Không tắt service matching hoặc chấp nhận bất kỳ certificate CAS Server khi gặp SSL/TLS lỗi.
- Nếu phục vụ nhiều vanity domains, thiết kế mỗi allowed service/tenant theo registry đã xác minh thay vì động ghép host từ request.

### 9.2. Checklist network debug

Trong browser Network (môi trường test):

1. `GET /reports` → app trả 302 đến CAS login.
2. Decode query `service` trong Location: phải là `https://app.example.org/login/cas`.
3. CAS login hoàn tất → Location quay lại **cùng service** với `?ticket=...`.
4. Browser GET đúng callback, không bị redirect sang host/HTTP/path khác trước khi filter xử lý.
5. Backend gọi CAS validation với **cùng service**. Quan sát server-side debug qua cấu hình an toàn, **không log ticket thật**.
6. CAS trả success hoặc mã failure.
7. App lập `Authentication`/HttpSession rồi redirect vào `/reports`; resource cần đúng role/user.

Nếu chỉ thấy browser tới `/login/cas?ticket=...` rồi 404, nhiều khả năng CAS filter không nằm đúng chain, matcher path sai, ứng dụng có servlet context path khác, hoặc security config bị override.

## 10. Bảo mật ticket trong URL, log và redirect

### 10.1. Ticket là credential nhạy cảm, dù chỉ dùng một lần

Browser nhận callback:

```text
https://app.example.org/login/cas?ticket=ST-example
```

Rủi ro là ST có thể xuất hiện trong:

- Access log của ingress/reverse proxy/CDN/WAF.
- Browser history hoặc address bar và screen recording.
- Monitoring/tracing query string.
- Referer tới external resource nếu callback không được xử lý/redirect đúng.
- Crash/report attachments được người dùng chia sẻ.
- Cache/analytics pipeline.

**Biện pháp:**

1. Bắt buộc HTTPS cho CAS Server, SP callback và validation.
2. Không log raw query parameter `ticket`; chỉ ghi request ID, failure category, service registration ID và hash được quản lý nếu cần đối chiếu sự kiện.
3. Giữ callback là endpoint filter, validate ST ngay rồi redirect đến URL không chứa ticket.
4. Đặt `Referrer-Policy` phù hợp, ví dụ `no-referrer` cho URL nhạy cảm, tránh tải third-party assets trên callback.
5. Chặn open redirect khi xử lý saved request; không chuyển ST đến host khác theo `redirect` parameter tự khai.
6. Không cho client/browser thực hiện `/serviceValidate` trực tiếp với secret không cần thiết; backend ứng dụng sử dụng TLS đáng tin.
7. Khi có WAF/ingress, cho phép `ticket` qua callback **được giới hạn** nhưng không log/echo lại.
8. Không đặt ticket vào cookie ứng dụng hay JavaScript localStorage để giữ phiên.

### 10.2. Service Ticket replay

CAS ST được phát cho một service và chỉ valid **một lần validation**. Nếu validator đã dùng ST, việc GET lại callback cùng ST phải thất bại. Để đăng nhập lại, app khởi tạo luồng CAS login mới; CAS có thể cấp ST khác nhờ TGT/TGC vẫn còn trên CAS Server.

Không dùng `CasAuthenticationProvider`/ticket validator để “verify” ST nhiều lần như một bearer token. Nếu app cần gọi backend service, hãy dùng mô hình **CAS proxy ticket** được phép hoặc OAuth2 theo kiến trúc phù hợp; không gửi lại browser ST của app A sang app B.

## 11. `sendRenew`: bắt CAS yêu cầu xác thực lại, không phải đổi service URL

`ServiceProperties#setSendRenew(true)` hướng CAS login/validation với tham số `renew` theo CAS protocol. Giá trị mặc định là `false`.

- **`false`:** CAS có thể dùng SSO TGT/TGC hiện tại để cấp ST mới, thường không yêu cầu user nhập lại mật khẩu.
- **`true`:** yêu cầu CAS không chỉ dựa vào phiên SSO hiện tại; người dùng phải được xác thực bằng primary credentials theo semantics/policy CAS và ticket validation phải kiểm điều kiện `renew`.
- Không mặc nhiên suy `renew=true` tương đương phishing-resistant MFA hoặc một assurance level cụ thể. Nếu nghiệp vụ yêu cầu MFA, cần CAS authentication policy/attribute assurance contract riêng.
- `renew` **không thay đổi** `ServiceProperties.service`, `filterProcessesUrl` hay CAS validation base URL.
- `renew=true` cũng không thu hồi local app session đang hoạt động; muốn fresh authentication khi user đang có session, app phải chủ động khởi tạo **luồng xác thực mới** thay vì chỉ đặt property rồi chờ.

**Chú ý:** `gateway` dùng cho kịch bản kiểm tra SSO thụ động và có semantics khác; CAS protocol nêu `gateway` và `renew` không tương thích. Không bật cả hai theo suy đoán.

## 12. Trường hợp nhiều ứng dụng, một CAS Server

```text
CAS Server: https://sso.example.org/cas
          |
          +-- App A service https://reports.example.org/login/cas
          |
          +-- App B service https://hr.example.org/login/cas
          |
          +-- App C service https://pay.example.org/portal/login/cas
```

Cả ba app có thể chia sẻ CAS SSO session, nhưng có **service identifier khác nhau** và **ST khác nhau**. Một ST cấp cho App A không được validate ở App B; CAS phải thực hiện service binding. Vì vậy không thể sao chép nguyên `ServiceProperties.service` từ A sang B, dù dùng cùng CAS Server base URL.

Mỗi app tạo **local HttpSession** sau CAS validation. Khi App A logout local, CAS TGT/TGC có thể còn và App B vẫn giữ phiên; đó là vấn đề session/logout, không phải ServiceProperties bị sai.

### 12.1. Nhiều tenant và service URLs

Nếu một Spring app phục vụ nhiều tenant, cần phân biệt:

- Một service URL cố định dùng chung cho tất cả tenants, rồi kiểm tenant membership sau authentication.
- Nhiều service URLs/hostnames/callbacks được CAS đăng ký riêng cho các tenants.
- Nhiều CAS Servers cho các đối tác khác nhau (mỗi server có trust boundary và service registration riêng).

`ServiceProperties` đơn giản với một `service` tĩnh phù hợp trường hợp **một service URL**. Nếu service identifier phải thay đổi theo tenant, không chỉ gọi `setService(...)` trên singleton bean trong mỗi request: tạo race condition và trộn tenant/issuer. Cần thiết kế resolver/registry được phê duyệt, request correlation và validation đúng service, đồng thời tránh chấp nhận ticket của tenant khác.

Trong trường hợp động/Proxy Ticket, Spring Security cung cấp `ServiceAuthenticationDetailsSource`, `ServiceAuthenticationDetails` và `authenticateAllArtifacts` theo mô hình nâng cao; **không bật tùy tiện** vì nó làm thay đổi phạm vi URL có thể xử lý ticket. Mỗi allowed service phải gắn với tenant/registration được kiểm chứng, không suy từ raw Host hoặc URL do browser chọn.

## 13. Java 17 thuần: nhìn rõ ba URL và phép so khớp

Chương trình chạy bằng JDK 17, **không có Spring hay CAS Server**. Nó mô phỏng xây URL login có service đã URL-encode và so sánh định danh service giữa các cấu hình. Nó **không tạo ST thật, không gọi /serviceValidate và không xác minh người dùng**.

File `CasServiceUrlDemo.java`:

```java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public final class CasServiceUrlDemo {

    private static final String CAS_BASE =
        "https://sso.example.org/cas";

    private static final String SERVICE =
        "https://app.example.org/login/cas";

    private static final String FILTER_PATH = "/login/cas";

    static String casLoginUrl(String base, String service) {
        return base + "/login?service=" +
            URLEncoder.encode(service, StandardCharsets.UTF_8);
    }

    static boolean exactMatch(String expected, String actual) {
        return expected.equals(actual);
    }

    public static void main(String[] args) {
        System.out.println("registered=" + SERVICE);
        System.out.println("login=" +
            casLoginUrl(CAS_BASE, SERVICE));
        System.out.println("filterPath=" + FILTER_PATH);

        System.out.println("matchExact=" +
            exactMatch(
                SERVICE,
                "https://app.example.org/login/cas"));

        System.out.println("httpDiff=" +
            exactMatch(
                SERVICE,
                "http://app.example.org/login/cas"));

        System.out.println("slashDiff=" +
            exactMatch(
                SERVICE,
                "https://app.example.org/login/cas/"));

        System.out.println("contextDiff=" +
            exactMatch(
                SERVICE,
                "https://app.example.org/portal/login/cas"));

        System.out.println("callbackWithTicket=" +
            SERVICE + "?ticket=ST-TEST");

        System.out.println("validationService=" + SERVICE);
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac --release 17 CasServiceUrlDemo.java
java CasServiceUrlDemo
```

Stdout xác định:

```text
registered=https://app.example.org/login/cas
login=https://sso.example.org/cas/login?service=https%3A%2F%2Fapp.example.org%2Flogin%2Fcas
filterPath=/login/cas
matchExact=true
httpDiff=false
slashDiff=false
contextDiff=false
callbackWithTicket=https://app.example.org/login/cas?ticket=ST-TEST
validationService=https://app.example.org/login/cas
```

**Bài học:** Khi CAS Server phát ST cho `SERVICE`, validate phải gửi lại `SERVICE`; URL callback có thêm `ticket` là **request browser**, không phải giá trị service mà validator nên gửi. URL-encode cho tham số `service` là **biểu diễn trong query**, không biến nó thành một identifier mới.

`exactMatch` là minh họa phép so khớp nghiêm ngặt giữa **chuỗi đã được quản trị phê duyệt**. Nó **không thay thế** parser, CAS service registry, CAS server `TicketValidator` hoặc chính sách xử lý URL trong production. Không tự cắt query, bỏ slash, đổi scheme, lowercase toàn URL hoặc “normalize” tùy tiện để cho ST không đúng service được chấp nhận.

## 14. Kiểm thử thực tế: phân biệt browser, callback và server-side validation

Chuẩn bị CAS Server test có registered service đúng và user `alice`. Dùng DevTools Network cho browser và application logs đã che ticket. Không sử dụng ticket production trong lệnh mẫu công khai.

### 14.1. Happy path

1. Browser `GET https://app.example.org/reports` chưa có app session.
2. Spring dùng `CasAuthenticationEntryPoint` redirect 302 tới `https://sso.example.org/cas/login?service=...`.
3. Decode `service` thấy đúng `https://app.example.org/login/cas`, không phải `/reports` hay HTTP nội bộ.
4. CAS Server kiểm registered service, user login hoặc có CAS SSO session hợp lệ.
5. CAS redirect browser về `https://app.example.org/login/cas?ticket=ST-...`.
6. Spring `CasAuthenticationFilter` nhận callback trên `/login/cas`.
7. Backend gọi `https://sso.example.org/cas/serviceValidate` với ticket và `service=https://app.example.org/login/cas`.
8. CAS Server trả `authenticationSuccess`; principal `alice` được map local `ROLE_USER`.
9. Spring tạo Authentication/app session, redirect đến `/reports`, HTTP 200 và không còn ST trong URL.
10. Refresh `/reports` được xác thực bằng app session, không cần validate lại ST.

**Bằng chứng QA:** ST được dùng **đúng một lần**, success đến từ CAS Server; app session mới hoạt động; user không được cấp quyền vượt local policy.

### 14.2. Chỉ kiểm redirect, không cần ST thật

Có thể chạy lệnh quan sát URL login từ máy đã được cấp quyền truy cập staging:

```bash
curl -I https://app.example.org/reports
```

Kỳ vọng có thể thấy `302` và `Location` trỏ CAS login kèm encoded service; thực tế có thể trả `302` cho `GET` nhưng `HEAD` khác tùy ứng dụng/proxy. Nếu `HEAD` không đại diện, dùng `curl -i -o /dev/null -D - https://app.example.org/reports` hoặc trình duyệt.

**Không tự GET `/serviceValidate?ticket=ST-TEST` và mong thành công.** ST giả/đã tiêu thụ phải bị từ chối. Nếu muốn kiểm định validator theo ma trận, dùng CAS test tự phát ST và quan sát tích hợp thật; ticket chỉ được dùng một lần.

## 15. Ma trận kiểm thử ST và service identifier

| Ca thử | Thiết lập | Kết quả kỳ vọng |
| --- | --- | --- |
| **Callback đúng** | `ServiceProperties.service` và CAS registered service đều là HTTPS app URL, filter `/login/cas` | Login thành công nếu ST hợp lệ |
| **Sai scheme** | CAS phát ST cho HTTPS, validation gửi HTTP | `INVALID_SERVICE`, không tạo session |
| **Sai host** | CAS phát cho app.example.org, validation gửi app-internal | Từ chối |
| **Sai port** | CAS phát cho :8443, validation bỏ port | Từ chối nếu service không khớp theo policy |
| **Sai context path** | CAS phát `/portal/login/cas`, validator dùng `/login/cas` | Từ chối |
| **Sai trailing slash** | CAS phát `/login/cas`, validator `/login/cas/` | Không coi tương đương tùy tiện |
| **Filter matcher sai** | CAS callback `/login/cas`, filter theo `/cas/login` | CAS filter không xử lý ST; login fail/404/loop |
| **Filter không nằm trong chain** | Config tạo bean nhưng không add vào đúng SecurityFilterChain | Không xác thực ST |
| **Hai lần validate cùng ST** | ST đã được CAS xác minh, gọi validate lại | `INVALID_TICKET` / không thể replay |
| **ST đã hết hạn** | Ticket quá thời gian CAS cho phép | Từ chối |
| **ST từ CAS Server khác** | Ứng dụng dùng validator tới server không cấp ticket | Từ chối |
| **CAS registered service không khớp** | Service không nằm trong allowlist | CAS từ chối service/ticket |
| **Browser có CAS TGT/TGC nhưng không có app session** | Truy cập `/reports` | Có thể SSO lại để cấp ST mới, app session mới |
| **User CAS không tồn tại trong local user registry** | CAS validation thành công cho user không được app cho phép | Không cấp app Authentication có quyền; theo code demo có thể fail |
| **Sai quyền nghiệp vụ** | CAS principal được verify nhưng không có `ROLE_USER`/tenant permission | `403` hoặc deny tài nguyên |
| **CAS Server HTTPS cert không tin cậy** | Backend không verify TLS CAS | Fail kết nối/validation; không bật trust-all |
| **Callback có ticket giả** | `?ticket=ST-FAKE` | Từ chối, không tạo session |
| **Ứng dụng login trên reverse proxy** | Browser HTTPS, backend HTTP, fixed canonical service | Thành công nếu trust/callback routing đúng |
| **Host header injection** | Client gửi Host/Forwarded giả để đổi service | Không được thay giá trị service đã phê duyệt |
| **Unknown query business value** | Browser thêm `?next=https://evil...` vào callback | Không tạo open redirect hoặc thay service |
| **CSRF/logout** | Logout app bằng POST có CSRF | Local session bị hủy; CAS session có thể còn |

**Kiểm thử độc lập từng biến:** Để chứng minh `INVALID_SERVICE`, cần CAS test phát ST hợp lệ cho service A rồi thử validate với service B theo chính sách, không dùng ST đã hết hạn hoặc fake vì kết quả `INVALID_TICKET` sẽ che nguyên nhân. Do ST dùng một lần, mỗi negative case cần **ticket mới**.

## 16. Kỹ thuật chẩn đoán nhanh theo triệu chứng

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra và sửa |
| --- | --- | --- |
| CAS login thành công nhưng app quay lại login liên tục | Service URL mismatch, session cookie không lưu, provider/filter lỗi | So ba giá trị service, app session và cookie |
| CAS Server báo `INVALID_SERVICE` | `service` lúc cấp ticket và validate khác nhau; hoặc server service registry không cho phép | Kiểm tra Location, service registered và request validation |
| App callback trả 404 | Filter CAS không match, chain thiếu, context path/proxy rewrite sai | Kiểm `filterProcessesUrl` vs path servlet, Spring Security chain |
| App callback trả 403 | Spring security/CSRF rule khác, method, WAF hoặc route bị chặn | Kiểm filter chain, HTTP method, origin và CSP/WAF |
| ST bị `INVALID_TICKET` | ST expired, đã dùng, server khác, fake ticket hoặc renew policy | Dùng ST mới do CAS test cấp, không retry cùng ST |
| CAS Server `/serviceValidate` trả lỗi TLS | JVM truststore không tin CAS Server, hostname mismatch, proxy MITM | Cài trust chain đúng, xác minh FQDN, không disable TLS |
| Backend cố gọi `https://app.example.org/serviceValidate` | Nhầm client service URL với CAS server validation URL | Validator phải dùng CAS base URL |
| Filter sử dụng URL đầy đủ trong `setFilterProcessesUrl` | Nhầm request path với service identifier | Dùng local `/login/cas`; service là HTTPS absolute URL |
| Ticket được validate nhưng user không có quyền | `UserDetailsService` không tìm principal, local role/tenant policy deny | Kiểm mapping local/entitlement, không skip CAS validation |
| App không giữ phiên sau CAS callback | SecurityContextRepository không được lưu, cookie Secure/SameSite sai, session store lỗi | Kiểm repo và Set-Cookie/Session ID/HTTPS |
| Callback bị xử lý hai lần | Filter CAS vừa là Boot servlet bean vừa là filter trong Spring Security chain | Chỉ đăng ký trong chain hoặc disable servlet auto-registration |
| App chạy dưới `/portal` nhưng service thiếu prefix | Cấu hình context path/proxy khác public URL | Dùng service public `/portal/login/cas`, local filter path phù hợp |
| Browser tự SSO lại sau local logout | CAS TGT/TGC vẫn còn | Phân biệt local logout và CAS global/SLO |
| Không có user prompt dù yêu cầu re-login | `sendRenew=false` và CAS SSO session hợp lệ | Đánh giá `sendRenew=true` + CAS authentication policy, không suy MFA |
| Service matching quá rộng | CAS allow-all/regex không neo | Siết service registry và tránh open redirect |
| Multi-tenant app dùng service của tenant khác | Singleton ServiceProperties bị sửa theo request | Thiết kế registry/binding tách biệt và test cross-tenant |
| Ticket xuất hiện trong access logs | Proxy log raw query | Redact ticket, kiểm Referer/retention và thay đổi logging policy |
| Lỗi chỉ trên một pod | Config/service URL/cookie/session store khác nhau | So release, env vars, route, truststore, Session/Redis |
| CAS Server báo không có registered service | CAS service registry chưa cấu hình, URI/regex sai | Đăng ký đúng HTTPS callback, review policy |

### 16.1. Cây quyết định cho sự cố đăng nhập

```text
A. Browser đã nhận 302 đến CAS login chưa?
   |
   +-- Chưa: SecurityFilterChain / EntryPoint / protected matcher.
   |
   +-- Rồi: decode ?service=...
         |
         +-- Service có bằng URL HTTPS đã duyệt?
               |
               +-- Không: sửa ServiceProperties / proxy / config.
               |
               +-- Có: CAS đã cho phép service và phát ST chưa?
                     |
                     +-- Không: registry CAS, chính sách IdP/TLS.
                     |
                     +-- Có: browser có GET callback /login/cas?ticket?
                           |
                           +-- Không: DNS, redirect, context, ingress.
                           |
                           +-- Có: CasAuthenticationFilter chạy không?
                                 |
                                 +-- Không: matcher/filter chain.
                                 |
                                 +-- Có: backend /serviceValidate trả gì?
                                       |
                                       +-- INVALID_SERVICE: so chính xác service.
                                       +-- INVALID_TICKET: ST expiry/replay/server.
                                       +-- TLS/network fail: truststore, hostname.
                                       +-- success: local UserDetails/authorities,
                                                    SecurityContext/session/roles.
```

Một hệ thống có thể có **nhiều lỗi cùng lúc**. Nếu đã sửa service URL nhưng vẫn login loop, kiểm bước lưu session và session cookie, không tự quay lại nới service matching.

## 17. CAS Proxy Ticket là tính năng khác, không bật chỉ để login thường

Spring Security CAS hỗ trợ những ứng dụng cần đại diện user để gọi downstream CAS service qua **proxy tickets (PT)**. Điều này sử dụng thêm:

- `Cas20ProxyTicketValidator` / `/proxyValidate`.
- `proxyReceptorUrl` trên ứng dụng để CAS Server trao Proxy-Granting Ticket (PGT).
- `ProxyGrantingTicketStorage` có lifecycle/cleanup.
- `ServiceAuthenticationDetailsSource` khi validate ticket theo service URL động.
- `ServiceProperties.authenticateAllArtifacts` khi thực sự muốn xử lý artifact ngoài callback mặc định.
- Danh sách proxy chains có thẩm quyền; **không** dùng `acceptAnyProxy=true` ở production.

**Cảnh báo trọng tâm:** `proxyReceptorUrl` **không phải** `filterProcessesUrl` cơ bản và không phải `ServiceProperties.service` của app thông thường. PGT callback là một endpoint giao thức riêng, thường bắt buộc HTTPS với kiểm tra TLS/PKIX nghiêm ngặt. Nếu chỉ cần login CAS và lập HttpSession, **đừng cấu hình PGT/proxy receptor** vì nó làm tăng bề mặt tấn công và số endpoint phải bảo vệ.

Nếu có nhu cầu Proxy Ticket, phải viết thiết kế riêng, sử dụng CAS protocol docs và Spring Security CAS Javadocs đúng version, không bật `authenticateAllArtifacts=true` chỉ để chữa callback 404 hay INVALID_SERVICE.

## 18. CAS local logout, SSO logout và độ mới xác thực

Local `POST /logout` ở app:

- Hủy `HttpSession`/`SecurityContext` của chính app.
- Không tự hủy CAS TGT/TGC ở `sso.example.org`.
- Khi truy cập lại app, user có thể được CAS phát ST mới dựa trên TGT/TGC và đăng nhập lại mà không gõ password.

CAS Server `/cas/logout`:

- Hủy/điều phối CAS SSO session theo cấu hình và CAS SLO.
- Không mặc nhiên xóa mọi local session của mọi dịch vụ nếu chúng không nhận/không xử lý SLO notifications.
- Không phải `ServiceProperties.service` và không thay CAS callback.

Đối với giao dịch nhạy cảm, `ServiceProperties.sendRenew=true` có thể yêu cầu primary-credential reauthentication theo CAS, nhưng **không bảo đảm mức MFA hay session freshness của mọi ứng dụng**. Chính sách nghiệp vụ có thể yêu cầu assurance context, transaction binding và kiểm quyền riêng, không chỉ nhìn user đã có CAS ST.

## 19. Bảo mật tối thiểu cần có cho CAS client

1. **HTTPS strict** giữa browser–service và service–CAS; backend xác minh TLS certificate của CAS Server, không tắt hostname verification.
2. **CAS service registry allowlist** với exact/cẩn thận regex, hostname/path owner và phê duyệt.
3. **Fixed canonical service** từ cấu hình đáng tin, không dựng từ raw `Host`/`X-Forwarded-*` do client kiểm soát.
4. **CAS Filter trong SecurityFilterChain**, không `web.ignoring` callback và không tạo controller tự nhận ST.
5. **CAS validation backend** với service identifier đúng; không tin opaque ticket chỉ vì có prefix `ST-`.
6. **Ticket dùng một lần**, xử lý replay/ticket hết hạn/thất bại theo fail-closed.
7. **CSRF protection** cho các thao tác session cookie thay đổi trạng thái; callback GET CAS được xử lý giao thức, không phải lý do tắt CSRF mọi route.
8. **Session fixation protection** và cookie `Secure`, `HttpOnly`, `SameSite` theo HTTPS topology; không URL-rewrite `JSESSIONID`.
9. **Redact ST** trong log/tracing/query metrics; Referrer-Policy và no-store thích hợp trên redirect/callback.
10. **User identity/authorization** sau ticket validation; membership/role nội bộ không được suy từ email/group chưa được phê duyệt.
11. **Local logout ≠ CAS SSO logout**; nếu cần SLO, thiết kế riêng và kiểm thử partial failures.
12. **Multi-tenant binding**: đúng source/issuer/service URL và tenant context, không chia sẻ ticket hay local session giữa tổ chức khác.
13. **Timeout/availability** của CAS validation được giám sát; nếu CAS unavailable, không cấp session từ unvalidated ticket.
14. **Rate limiting và anomaly monitoring** tại CAS login/callback/validation; không log ticket nguyên văn.
15. **Change management** cho đổi service URL, context path, reverse proxy, CAS hostname, truststore hoặc service registry.
16. **Regression tests** cho URL exact matching, wrong service, expired/replayed ST, filter matcher và session persistence sau mỗi deploy.

## 20. Bài tập áp dụng và đáp án

**Câu 1.** CAS Server URL là `https://sso.example.org/cas`, ứng dụng chạy public `https://portal.example.org/app` với callback `/app/login/cas`. `ServiceProperties.service` nên là gì?

**Đáp án:** `https://portal.example.org/app/login/cas`. `https://sso.example.org/cas` chỉ dùng làm CAS server base URL cho validator; local filter matcher thường là `/login/cas` bên trong context `/app`.

**Câu 2.** Spring cấu hình `ServiceProperties.service=https://portal.example.org/login/cas` nhưng `CasAuthenticationFilter.filterProcessesUrl=/cas/login`. Browser quay về `/login/cas?ticket=...`, điều gì xảy ra?

**Đáp án:** Filter không match đúng callback; ST không được xử lý, có thể thấy 404/redirect vòng lặp/không tạo Authentication. Sửa filterProcessesUrl về `/login/cas`; không chuyển service sang CAS Server login URL.

**Câu 3.** CAS phát ST cho `https://portal.example.org/login/cas`, nhưng Java validator gửi `service=http://portal-internal:8080/login/cas`. Login thất bại do đâu?

**Đáp án:** **INVALID_SERVICE** vì service identifier không khớp. Cần dùng canonical HTTPS URL xuyên suốt, sửa proxy/config; không mở CAS service registry cho mọi host.

**Câu 4.** `GET /login/cas?ticket=ST-REAL` vừa được Spring validate thành công. User refresh trang callback cũ; CAS trả INVALID_TICKET. CAS có lỗi không?

**Đáp án:** Không nhất thiết. ST được dùng một lần, đã bị tiêu thụ. App nên redirect sau login để URL không giữ ticket; việc truy cập lại tài nguyên bảo vệ sẽ dùng local session hoặc khởi tạo CAS flow mới nếu session đã mất.

**Câu 5.** Một controller `@GetMapping("/login/cas")` có thể tự đọc ticket và đặt `SecurityContext` thành authenticated nếu chuỗi bắt đầu bằng `ST-`?

**Đáp án:** Không. Phải để CAS filter/provider/validator xác minh ticket với CAS Server, đảm bảo đúng service và áp local identity/authorization.

**Câu 6.** `ServiceProperties.sendRenew=true` có tự bật MFA và khiến CAS Server thu hồi local session cũ của mọi ứng dụng không?

**Đáp án:** Không. `renew` yêu cầu CAS reauthentication theo semantics primary credentials; không tự khẳng định mức MFA và không tự thu hồi các HttpSession khác.

**Câu 7.** Một multi-tenant app thay `ServiceProperties.service` của singleton bean theo `X-Forwarded-Host` từ browser trong mỗi request. Có an toàn không?

**Đáp án:** Không. Có nguy cơ Host header injection, trộn tenant/race condition và ticket được validate ở service sai. Dùng mapping service/tenant đã xác minh và cơ chế request correlation nếu thật sự cần multiple services.

**Câu 8.** Chỉ đổi cổng public từ 443 sang 8443, backend port không đổi. Cần rà soát cấu hình nào?

**Đáp án:** `ServiceProperties.service`, CAS registered service, reverse proxy, browser Location callback, filter matcher thực tế, TLS và chính sách URL. Service URL có thể cần `:8443`; không chỉ sửa `server.port` backend.

## 21. Checklist nghiệm thu triển khai

- [ ] Đã định nghĩa ba URL: CAS Server base, CAS login, **application service callback**; không nhầm host/server/client.
- [ ] `ServiceProperties.service` là URL HTTPS tuyệt đối public, có scheme/port/context/path đúng.
- [ ] `CasAuthenticationFilter.filterProcessesUrl` trùng đường dẫn local của callback `service`, mặc định `/login/cas` khi root context.
- [ ] `CasAuthenticationEntryPoint` và `CasAuthenticationProvider` dùng **cùng ServiceProperties**; validator gọi CAS server base đúng.
- [ ] CAS service registry đã đăng ký **service URL chính xác** với policy có owner, không allow-all service IDs.
- [ ] Không thêm `ticket` vào cấu hình service URL; browser callback có `ticket` nhưng backend validate bằng giá trị service gốc.
- [ ] ST được CAS verify một lần; second validation bị từ chối.
- [ ] CAS login và ticket-validation endpoint ở **CAS Server**, callback filter ở **Spring app**.
- [ ] App Boot có dependency `spring-security-cas` và CAS Client tương thích; kiểm dependency tree/BOM.
- [ ] CAS filter chỉ được đăng ký trong Spring Security chain; không tự auto-register global Filter bean hai lần.
- [ ] Authentication thành công được lưu vào SecurityContext/HttpSession; có session fixation/CSRF/cookie policy.
- [ ] User CAS được map sang local account/roles/tenant membership theo chính sách, không tự cấp quyền global.
- [ ] Reverse proxy chỉ chấp nhận forwarded headers từ trusted hop; canonical host/service nhất quán.
- [ ] Không tắt TLS verification hay dùng HTTP nội bộ làm registered service production.
- [ ] Không log ST, raw query/cookies hay ticket-validation secrets; có no-store/Referrer-Policy phù hợp.
- [ ] Test happy path, invalid service, wrong path/port/scheme, expired/replayed ST, CAS outage, SSL failure và missing local user.
- [ ] `sendRenew` và CAS SSO/global logout được hiểu là cơ chế khác nhau, không coi local logout là CAS logout.
- [ ] Nếu cần proxy tickets/PGT, có thiết kế/test riêng thay vì bật `authenticateAllArtifacts` tùy tiện.
- [ ] Đã thử nhiều pod/tenant/context path và regression sau thay đổi ingress, cert/truststore hay registered service.
- [ ] Có runbook so sánh ba giá trị `service` lúc login, callback và validate để chẩn đoán `INVALID_SERVICE`.

**Kết luận:** Tích hợp CAS với Spring Security thành công khi **một ServiceProperties.service cố định, được CAS đăng ký** cùng trỏ tới endpoint callback ứng dụng mà `CasAuthenticationFilter` xử lý, và `CasAuthenticationProvider/TicketValidator` xác minh ST với CAS Server bằng **chính service identifier ấy**. Hiểu rõ khoảng cách giữa URL tuyệt đối và local filter path, đồng thời giữ nguyên single-use ticket validation, HTTPS, session và quyền ứng dụng sẽ giúp tránh login loop, lỗi `INVALID_SERVICE` và nguy cơ nhận ticket sai dịch vụ.

## 22. Tài liệu tham khảo chính thức

1. [Spring Security – CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): `ServiceProperties`, CAS interaction sequence, `CasAuthenticationEntryPoint`, filter/provider và validator.
2. [Spring Security 6.5 API – CasAuthenticationFilter](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html): callback `/login/cas` và xử lý ticket.
3. [Spring Security API – ServiceProperties](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/ServiceProperties.html): `service`, `sendRenew`, tham số `ticket`/`service` và `authenticateAllArtifacts`.
4. [Spring Security API – CasAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationEntryPoint.html): CAS login redirect/service URL.
5. [Spring Security API – CasAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html): `TicketValidator`, `UserDetailsService` và phương thức xác thực CAS.
6. [Spring Security – Project Modules/Dependencies](https://docs.spring.io/spring-security/reference/6.5/modules.html): module `spring-security-cas` và Apereo CAS client.
7. [Apereo CAS – Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): `service`, `ticket`, ``/login`, ``/serviceValidate`, `INVALID_SERVICE`, sử dụng ST một lần và proxy protocol.
8. [Apereo CAS – CAS Protocol Overview](https://apereo.github.io/cas/development/protocol/CAS-Protocol.html): TGT/TGC, ST, service registration và các biến thể CAS.
9. [Apereo CAS – Ticket Validation](https://apereo.github.io/cas/development/authentication/CAS-Protocol-TicketValidation.html): `service` exact matching và chính sách xác thực ticket.
10. [Spring Security – Logout (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): local session logout/CSRF, khác CAS SSO logout.
11. [Spring Security – Authentication Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html): `SecurityContextRepository` và HttpSession persistence.
12. [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie/session/URL sensitive data.
13. [OWASP – Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): xử lý redirect và URL input.
