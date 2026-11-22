# CAS, JAAS và Kerberos: phạm vi tích hợp, dependency và điều kiện sử dụng

**Module:** Spring Security – Servlet  
**Chủ đề cha:** Tích hợp danh tính

## 1. Ba tên gọi thường đứng cạnh nhau nhưng không cùng một lớp kiến trúc

Khi đưa Spring Security Servlet vào một hệ thống doanh nghiệp có sẵn cơ chế đăng nhập, ta có thể gặp **CAS**, **JAAS** hoặc **Kerberos**. Cả ba đều liên quan đến xác thực danh tính, nhưng chúng không phải ba phương án thay thế hoàn toàn tương đương:

- **CAS (Central Authentication Service):** một **giao thức/hệ thống Single Sign-On (SSO)**. Ứng dụng được chuyển hướng tới CAS Server, nhận **service ticket** rồi yêu cầu CAS xác minh ticket.
- **JAAS (Java Authentication and Authorization Service):** **API/framework xác thực bên trong nền tảng Java**, gồm `LoginContext`, `LoginModule`, `Subject` và `Principal`. JAAS là điểm tích hợp cơ chế đăng nhập Java; bản thân JAAS không chỉ định SSO provider, ticket endpoint hay cách browser đăng nhập.
- **Kerberos:** **giao thức xác thực mạng dựa trên ticket và khóa mật mã**. Trong web intranet, ứng dụng thường dùng **SPNEGO / HTTP Negotiate** để browser gửi bằng chứng Kerberos tới server. Kerberos cần hạ tầng KDC/realm/SPN/keytab và điều kiện client phù hợp.

Đặc biệt, **JAAS có thể sử dụng Kerberos** thông qua `Krb5LoginModule` trong những ngữ cảnh thích hợp; đây là quan hệ **API tích hợp → cơ chế xác thực**, không phải JAAS đối đầu Kerberos. CAS cũng có thể được cấu hình sử dụng LDAP, Kerberos hoặc một nguồn danh tính khác **ở phía CAS Server**, trong khi ứng dụng Java chỉ biết kết quả xác thực CAS.

### 1.1. Bảng chọn nhanh

| Tiêu chí | CAS | JAAS | Kerberos/SPNEGO |
| --- | --- | --- | --- |
| Vai trò chính | SSO cho ứng dụng web | API/bridge xác thực Java | Giao thức xác thực qua mạng và ticket |
| Ai kiểm tra thông tin đăng nhập? | CAS Server và nguồn danh tính của nó | `LoginModule` được cấu hình | KDC phát ticket, phía nhận kiểm chứng ticket |
| Luồng browser đặc trưng | Redirect → CAS login → service ticket → validate | Không có một luồng browser chuẩn chung | 401 `Negotiate` → browser gửi SPNEGO token |
| Có hoạt động độc lập chỉ với Maven dependency? | Không; cần CAS Server/config đúng | Có thể demo local; production cần LoginModule và nguồn danh tính thật | Không; cần realm/KDC/SPN/keytab, DNS/clock/client phù hợp |
| Tình huống phù hợp | Tổ chức đã có CAS SSO hoặc hệ thống legacy dựa CAS | Hệ thống Java có LoginModule/Subject hoặc yêu cầu bridge JAAS | Intranet dùng Active Directory/Kerberos và browser enterprise |
| Quyền ứng dụng được cấp tự động? | Không | Không | Không |
| Thay Spring Security authorization? | Không | Không | Không |
| Phụ thuộc hệ sinh thái Spring | Tích hợp CAS tùy phiên bản, có module riêng/adapter legacy | Lớp JAAS trong JDK; adapter Spring tùy version | GSS/Krb5 của JDK; adapter SPNEGO/Spring Kerberos ngoài lõi hoặc ở gateway |

**Quy tắc chọn giải pháp:** Nếu một CAS server hiện đại hỗ trợ **OIDC hoặc SAML 2.0** và hệ thống không bắt buộc CAS ticket protocol, cân nhắc tích hợp qua `oauth2Login()` hoặc `saml2Login()` mà phiên bản Spring Security đang dùng hỗ trợ. Không thêm CAS adapter legacy chỉ vì tổ chức gọi chung mọi đăng nhập doanh nghiệp là “CAS”.

## 2. CAS: SSO qua ticket, không phải OAuth2 access token

### 2.1. Thành phần và luồng đăng nhập

Trong **CAS protocol**, ứng dụng web là **service/client**, CAS Server là nơi quản lý SSO. Một luồng đơn giản:

~~~text
Browser           Ứng dụng Servlet          CAS Server
   | GET /reports        |                      |
   |-------------------->|                      |
   | 302 /login?service=...                     |
   |<--------------------|                      |
   | GET CAS /login?service=...                 |
   |------------------------------------------->|
   |                user login / CAS SSO session|
   | 302 tới service URL?ticket=ST-...          |
   |<-------------------------------------------|
   | GET service?ticket=ST-...                  |
   |-------------------->|                      |
   |                     | validate ticket ST   |
   |                     |--------------------->|
   |                     | principal/attributes |
   |                     |<---------------------|
   |    App session      |                      |
   |<--------------------|                      |
~~~

Các thuật ngữ:

- **TGT (Ticket Granting Ticket):** dùng cho phiên SSO ở CAS Server; ứng dụng dịch vụ thông thường **không** được dùng TGT như chứng cứ ủy quyền riêng.
- **ST (Service Ticket):** ticket ngắn hạn, thường dùng một lần, gắn với service được chỉ định. Ứng dụng cần chuyển ticket tới **CAS Server** để xác minh trước khi tạo `Authentication`.
- **Service URL:** callback/địa chỉ được CAS cho phép; phải khớp hợp đồng đăng ký service. Sai hostname, scheme, cổng hoặc context path dễ gây vòng lặp redirect/validation failure.
- **Principal + attributes:** thông tin CAS trả sau xác thực; ứng dụng vẫn phải tự map nhóm/role theo chính sách quyền nghiệp vụ.

**Không nhầm:** CAS service ticket không phải bearer access token cho một OAuth2 Resource Server; không nên cấu hình `oauth2ResourceServer().jwt()` để “kiểm tra CAS ticket”.

### 2.2. CAS phù hợp khi nào?

Dùng CAS protocol trực tiếp khi:

1. Doanh nghiệp đã vận hành CAS Server và service catalog, đồng thời quy định ứng dụng phải dùng CAS ticket flow.
2. Ứng dụng là web browser **Servlet** có khả năng điều hướng login và quản lý session.
3. Đội vận hành kiểm soát được HTTPS, public service URL, load balancer, CAS trust, logout và quy tắc phát hành attributes.
4. Có adapter **tương thích với phiên bản Java / Spring Security / Servlet hiện tại** hoặc kế hoạch tự xây bridge đã được đánh giá bảo mật.

Không mặc định áp dụng CAS browser redirect cho API thuần machine-to-machine; API thường cần token standard/credential phù hợp hơn. Một frontend SPA cũng cần thiết kế BFF/session hoặc OIDC phù hợp chứ không tự tùy tiện giữ ST trong browser state.

### 2.3. Dependency và tính tương thích CAS

Trong hệ sinh thái cũ có artifact **`org.springframework.security:spring-security-cas`** và các class kiểu `CasAuthenticationFilter`, `CasAuthenticationProvider`, `ServiceProperties`, `Cas20ServiceTicketValidator`. Tuy nhiên:

- **CAS không phải cấu hình được bật chỉ bằng `spring-boot-starter-security`**. Module, nhà phát hành và phiên bản phải được xác nhận trong BOM/repository của **release đang triển khai**.
- Đừng suy ra module CAS cũ luôn tồn tại hoặc tương thích với **Spring Security 6/7, Java 17+, Spring Boot 3 và Jakarta Servlet**. Nhiều hướng dẫn CAS online dùng API cấu hình trước Spring Security 6 hoặc `javax.servlet` cũ.
- Không thêm dependency CAS legacy bằng cách thử version ngẫu nhiên hoặc ép dependency conflict. Cần kiểm chứng artifact có được duy trì không, transitive dependencies, phiên bản CAS client/protocol và tương thích `jakarta.servlet`.
- Nếu dùng CAS Server chỉ như **Identity Provider OIDC/SAML2**, dependency web app tương ứng có thể là `spring-boot-starter-oauth2-client` hoặc các module SAML phù hợp, **không** phải `spring-security-cas`.

**Mẫu lựa chọn, không phải một `pom.xml` hoàn chỉnh:**

~~~text
CAS ticket protocol trực tiếp:
  Kiểm tra module CAS/adapter được hỗ trợ cho release đang dùng.
  Không tự coi spring-security-cas là dependency mặc định của Boot 3.

CAS Server có OIDC:
  spring-boot-starter-oauth2-client
  SecurityFilterChain với oauth2Login(...)
  OIDC issuer/client registration/redirect URI phù hợp.

CAS Server có SAML 2.0:
  Spring Security SAML2 Service Provider module phù hợp.
  Đăng ký SP/IdP metadata, chứng chỉ, assertion consumer service.
~~~

### 2.4. Các điều kiện bảo mật quan trọng của CAS

- **Chỉ tin kết quả ticket validation qua kênh HTTPS** tới CAS Server đã cấu hình; không tin chuỗi `ticket` tự gửi trên URL.
- **Service ticket phải khớp service** được CAS phát cho ứng dụng, không dùng ticket của service khác để đăng nhập.
- Chặn **open redirect** qua `service` hoặc `returnUrl` không được allowlist; cấu hình callback chính xác khi đi qua reverse proxy.
- Không ghi ticket vào access log, browser analytics hoặc thông báo lỗi; ticket có thể xuất hiện trong query string callback nên cần chính sách logging cẩn thận.
- Tạo authentication và session theo cơ chế Spring Security, cân nhắc **session fixation protection**, session timeout, HTTPS-only/HttpOnly/SameSite cookie và CSRF cho form đổi trạng thái.
- Phân biệt **logout ứng dụng** với **Single Logout (SLO)** ở toàn bộ CAS; logout một nơi không mặc nhiên kết thúc mọi phiên của tổ chức.
- Mapping attributes thành quyền: dùng **allowlist** và kiểm tra tenant/resource; CAS xác thực danh tính không tự cho phép mọi thao tác.

## 3. JAAS: điểm mở rộng xác thực của Java

### 3.1. Các đối tượng của JAAS

JAAS là API trong JDK, sử dụng các class thuộc namespace **`javax.security.auth.*`** — điều này vẫn đúng trên Java 17, **không đổi thành `jakarta.security.auth`** chỉ vì Spring Boot 3 dùng Jakarta Servlet.

| Thành phần | Trách nhiệm |
| --- | --- |
| `LoginContext` | Điều phối quá trình login/logout cho tên cấu hình JAAS. |
| `LoginModule` | Thực hiện một cơ chế xác thực cụ thể; có `initialize`, `login`, `commit`, `abort`, `logout`. |
| `CallbackHandler` | Cung cấp input cho LoginModule như tên người dùng, password hoặc lựa chọn tương tác. |
| `Subject` | Chứa tập principals, credentials công khai/riêng tùy ngữ cảnh và kết quả JAAS. |
| `Principal` | Đại diện một danh tính hoặc tên nhóm; không đồng nghĩa authority Spring nếu chưa map. |
| `Configuration` / `login.config` | Chọn module và cách kết hợp `required`, `requisite`, `sufficient`, `optional`. |

Với Spring Security, JAAS là **một nguồn xác thực** có thể được nối vào `AuthenticationManager`. Bộ adapter JAAS của Spring (nếu được phiên bản đang dùng hỗ trợ) chuyển kết quả login/Subject/principal thành `Authentication` và `GrantedAuthority`. Bạn cần chính sách map principal → authority; `Subject` không tự làm người dùng thành `ROLE_ADMIN`.

### 3.2. LoginModule control flag

Khi một cấu hình có nhiều LoginModule:

- **`REQUIRED`**: module phải thành công để login chung thành công, nhưng vẫn có thể chạy tiếp module sau.
- **`REQUISITE`**: phải thành công; khi thất bại thường kết thúc login sớm.
- **`SUFFICIENT`**: nếu thành công và không có thất bại REQUIRED trước đó, có thể hoàn tất sớm.
- **`OPTIONAL`**: riêng nó không quyết định login phải thành công; kết quả chung phụ thuộc các module khác và luật JAAS.

Đặt flag không đúng có thể cho phép đường login yếu đi khi một module khác thất bại. Phải kiểm thử **tổ hợp module** và nhánh lỗi, không chỉ case đăng nhập thành công.

### 3.3. Ví dụ Java 17 thuần JDK chạy được, không cần Spring

Ví dụ sau minh họa chính xác lifecycle JAAS: cấu hình module, cung cấp callback, tạo `Subject`/principal, logout. **Thông tin đăng nhập hard-code chỉ phục vụ học API, tuyệt đối không dùng làm backend xác thực thật.**

Lưu thành **`JaasFlowDemo.java`**:

~~~java
import java.io.IOException;
import java.security.Principal;
import java.util.Arrays;
import java.util.Map;
import javax.security.auth.Subject;
import javax.security.auth.callback.Callback;
import javax.security.auth.callback.CallbackHandler;
import javax.security.auth.callback.NameCallback;
import javax.security.auth.callback.PasswordCallback;
import javax.security.auth.callback.UnsupportedCallbackException;
import javax.security.auth.login.AppConfigurationEntry;
import javax.security.auth.login.Configuration;
import javax.security.auth.login.FailedLoginException;
import javax.security.auth.login.LoginContext;
import javax.security.auth.login.LoginException;
import javax.security.auth.spi.LoginModule;

public class JaasFlowDemo {
    public static void main(String[] args) throws LoginException {
        Configuration configuration = new Configuration() {
            @Override
            public AppConfigurationEntry[] getAppConfigurationEntry(
                    String name) {
                if (!"training".equals(name)) {
                    return null;
                }
                return new AppConfigurationEntry[] {
                    new AppConfigurationEntry(
                        DemoLoginModule.class.getName(),
                        AppConfigurationEntry.LoginModuleControlFlag.REQUIRED,
                        Map.of())
                };
            }
        };

        CallbackHandler handler = callbacks -> {
            for (Callback callback : callbacks) {
                if (callback instanceof NameCallback name) {
                    name.setName("alice");
                } else if (callback instanceof PasswordCallback password) {
                    password.setPassword("demo-only".toCharArray());
                } else {
                    throw new UnsupportedCallbackException(callback);
                }
            }
        };

        LoginContext context =
            new LoginContext("training", null, handler, configuration);

        context.login();
        Subject subject = context.getSubject();
        System.out.println("Login: OK");
        System.out.println(
            "Principals: " + subject.getPrincipals(UserIdentity.class).size());

        context.logout();
        System.out.println(
            "Principals after logout: "
            + subject.getPrincipals(UserIdentity.class).size());
    }

    public static final class UserIdentity implements Principal {
        private final String name;

        public UserIdentity(String name) {
            this.name = name;
        }

        @Override
        public String getName() {
            return name;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof UserIdentity identity
                && name.equals(identity.name);
        }

        @Override
        public int hashCode() {
            return name.hashCode();
        }
    }

    public static final class DemoLoginModule implements LoginModule {
        private Subject subject;
        private CallbackHandler handler;
        private UserIdentity identity;
        private boolean authenticated;

        @Override
        public void initialize(
                Subject subject,
                CallbackHandler handler,
                Map<String, ?> sharedState,
                Map<String, ?> options) {
            this.subject = subject;
            this.handler = handler;
        }

        @Override
        public boolean login() throws LoginException {
            NameCallback name = new NameCallback("User: ");
            PasswordCallback password =
                new PasswordCallback("Password: ", false);
            char[] supplied = null;

            try {
                handler.handle(new Callback[] { name, password });
                supplied = password.getPassword();

                if (!"alice".equals(name.getName())
                        || !Arrays.equals(
                            "demo-only".toCharArray(), supplied)) {
                    throw new FailedLoginException(
                        "Invalid training credentials");
                }

                identity = new UserIdentity(name.getName());
                authenticated = true;
                return true;
            } catch (IOException | UnsupportedCallbackException error) {
                LoginException exception =
                    new LoginException("Callback failed");
                exception.initCause(error);
                throw exception;
            } finally {
                if (supplied != null) {
                    Arrays.fill(supplied, '\0');
                }
                password.clearPassword();
            }
        }

        @Override
        public boolean commit() {
            if (!authenticated) {
                return false;
            }
            subject.getPrincipals().add(identity);
            return true;
        }

        @Override
        public boolean abort() {
            if (!authenticated) {
                return false;
            }
            return logout();
        }

        @Override
        public boolean logout() {
            if (identity != null) {
                subject.getPrincipals().remove(identity);
            }
            authenticated = false;
            identity = null;
            return true;
        }
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac JaasFlowDemo.java
java JaasFlowDemo
~~~

**Stdout kỳ vọng:**

~~~text
Login: OK
Principals: 1
Principals after logout: 0
~~~

**Giải thích:** module được JAAS tạo bằng tên class, gọi callback, xác thực dữ liệu giả lập rồi thêm `UserIdentity` vào `Subject` trong `commit()`; `logout()` loại principal đó. Đây là ví dụ **thuần JDK để hiểu lifecycle**, không có session HTTP, LDAP, CAS, KDC, hash password hoặc Spring Security filter. Không dùng account/password mẫu ở môi trường thật.

Trong hệ thống thực, một `LoginModule` phải có cách kiểm chứng đáng tin (LDAP/Kerberos/hardware key/service nội bộ), bảo vệ credential, chống brute force, xử lý lỗi và audit. Nếu một module đã xác thực bằng Kerberos, không viết lại phần mật mã Kerberos bằng Java thủ công.

### 3.4. JAAS tích hợp với Spring Security Servlet khi nào?

Dùng bridge JAAS khi doanh nghiệp có **LoginModule hiện hữu được vận hành và kiểm chứng** hoặc yêu cầu bảo mật/hạ tầng chỉ expose kết quả xác thực dưới dạng `Subject`. Bộ adapter trong Spring Security (ví dụ các lớp liên quan `JaasAuthenticationProvider`, `AuthorityGranter` ở các release có hỗ trợ) có thể kết nối kết quả này với `Authentication`.

Hãy kiểm tra **tồn tại và trạng thái hỗ trợ của adapter** trên release thực tế; không suy đoán rằng mọi Spring Security 6/7 module cũ đều còn hoặc tự động được Boot starter cấu hình. Với ứng dụng web mới sử dụng OIDC/SAML2 tiêu chuẩn, integration trực tiếp bằng cơ chế hiện đại thường rõ ràng hơn việc viết `LoginModule` tùy biến.

Luồng logic, **không phải class Java độc lập**:

~~~text
HTTP request
  -> Spring Security AuthenticationFilter / AuthenticationManager
  -> JAAS authentication provider/adapter phù hợp
  -> LoginContext.login()
  -> LoginModule(s) + Subject(principals)
  -> map approved Principals to GrantedAuthority (ROLE_...)
  -> Authentication stored in SecurityContext
  -> authorization for URL, method, tenant, resource
~~~

Ví dụ một principal đã được xác thực tên `engineering` có thể được **chính sách nội bộ** map sang `ROLE_ENGINEER`. Không map mọi `Principal.getName()` trực tiếp thành authority đặc quyền bằng nối chuỗi và không tin vào principal tự tạo từ request do client điều khiển.

## 4. Kerberos và HTTP SPNEGO

### 4.1. Kerberos cần những thành phần gì?

Kerberos là cơ chế xác thực dùng ticket và **Key Distribution Center (KDC)**; trong môi trường doanh nghiệp, Microsoft Active Directory thường cung cấp KDC. Những khái niệm thiết yếu:

- **Realm:** miền Kerberos, ví dụ `EXAMPLE.COM`.
- **KDC:** máy chủ phát hành/cấp ticket theo giao thức.
- **Client principal:** định danh của người dùng hoặc dịch vụ.
- **SPN (Service Principal Name):** định danh của service, thường có dạng `HTTP/app.example.com@EXAMPLE.COM` cho HTTP.
- **Keytab:** tệp chứa key bí mật của service principal để server xác thực/giải mã hoặc chấp nhận ticket Kerberos theo cơ chế áp dụng.
- **TGT:** Ticket Granting Ticket của người dùng, dùng để yêu cầu service ticket; ứng dụng web thông thường không nhận TGT như HTTP credential.
- **Service ticket:** ticket dành cho SPN cụ thể; browser có thể đưa nó tới website qua SPNEGO/Negotiate.
- **SPNEGO:** cơ chế negotiation cho phép HTTP client/server dùng token `Negotiate` để xác thực Kerberos trong điều kiện phù hợp.

Giao thức cụ thể khác CAS: browser không bị redirect đến một trang login CAS. Browser được cấu hình có thể tự lấy ticket từ môi trường đăng nhập domain và gửi khi server yêu cầu Negotiate.

### 4.2. Luồng SPNEGO trong HTTP

~~~text
Domain-joined browser     HTTP app / reverse proxy      KDC
        | GET /intranet             |                   |
        |-------------------------->|                   |
        | 401 + WWW-Authenticate: Negotiate             |
        |<--------------------------|                   |
        |    lấy service ticket cho HTTP/app...          |
        |----------------------------------------------->|
        |<-----------------------------------------------|
        | Authorization: Negotiate <SPNEGO token>        |
        |-------------------------->|                   |
        |                           | verify ticket      |
        |                           | using service key  |
        |                           v                   |
        |                         principal              |
        |                           |                   |
        |         Spring Authentication / authorities    |
        |<--------------------------|                   |
~~~

Một response challenge/response minh họa:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

Sau đó client gửi:

~~~http
GET /intranet HTTP/1.1
Host: app.example.com
Authorization: Negotiate <base64-SPNEGO-token>
~~~

**Không nhầm** `Authorization: Negotiate` với `Authorization: Bearer`. Bearer access token được dùng trong OAuth2 Resource Server; SPNEGO token là bằng chứng Kerberos được giao thức HTTP negotiation dùng. Các dữ liệu trên chỉ mang tính minh họa, không phải credentials thật.

### 4.3. Điều kiện bắt buộc để Kerberos hoạt động ổn định

1. **KDC/realm hoạt động**, account hoặc service principal được cấp phát đúng.
2. **SPN khớp hostname mà browser truy cập**, ví dụ `HTTP/app.example.com`; tránh duplicate SPN trên nhiều tài khoản.
3. **Keytab/credential của service** được cấp đúng account và version/key type; phân quyền file chặt, không commit vào Git.
4. **DNS, tên miền và reverse proxy** nhất quán; truy cập qua IP, alias hoặc tên khác có thể khiến browser không lấy đúng service ticket.
5. **Thời gian được đồng bộ** giữa KDC, client và server (clock skew có thể khiến ticket không hợp lệ).
6. **Browser/OS cho phép integrated authentication** tới hostname; thường cần chính sách intranet/enterprise, không thể giả định mọi thiết bị cá nhân hoặc browser mobile tự gửi Kerberos ticket.
7. **TLS/HTTPS** vẫn quan trọng để bảo vệ toàn bộ request/response, cookie, dữ liệu nghiệp vụ và giảm rủi ro proxy. Kerberos không thay TLS.
8. **Realm trust / cross-domain trust** chỉ hoạt động khi hạ tầng đã thiết lập và policy cho phép.
9. **Mô hình chạy nhiều node/load balancer** có thể dùng keytab/service account nhất quán; cần thiết kế SPN và routing đúng.
10. **Nhận dạng principal và role mapping** được xác minh. Kerberos cho biết một danh tính đã được xác thực, **không tự cấp các quyền ứng dụng**. Nhóm/role có thể đến từ LDAP/AD hoặc nguồn phân quyền riêng.

Nếu bất kỳ điều kiện nào thiếu, thường gặp **vòng lặp 401 Negotiate**, lỗi keytab/SPN, nhận sai realm hoặc browser hiện form đăng nhập thay vì tự SSO.

### 4.4. Dependency và phạm vi Spring Kerberos

Ở lớp Java, JAAS và Java GSS/Kerberos là các cơ chế của **JDK** (ví dụ `javax.security.auth.login.LoginContext`, `javax.security.auth.kerberos`, `org.ietf.jgss`). Ứng dụng Servlet muốn xử lý **HTTP SPNEGO** cần thêm filter/provider/adapter hoặc để **reverse proxy thực hiện Negotiate** rồi chuyển danh tính theo cơ chế ủy thác đã được bảo vệ.

Trong lịch sử hệ sinh thái Spring có **Spring Security Kerberos extension** với các artifact như:

~~~text
org.springframework.security.kerberos:spring-security-kerberos-core
org.springframework.security.kerberos:spring-security-kerberos-web
~~~

và các class adapter kiểu `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider` / `SunJaasKerberosTicketValidator`.

**Đây là các tọa độ/thành phần cần kiểm chứng theo phiên bản, không phải cam kết có bản tương thích với mọi Spring Boot hoặc Spring Security mới nhất.** Extension Kerberos có lịch phát hành khác Spring Security core. Không lấy một version plugin trong hướng dẫn Spring 4/5 rồi ghép vào Boot 3/Security 6 mà bỏ qua namespace Servlet và API changes.

Các lựa chọn triển khai:

- **SPNEGO trực tiếp trong Servlet app:** cần phiên bản adapter tương thích, KDC, SPN, keytab và kiểm thử trên hạ tầng thật.
- **SPNEGO tại reverse proxy/SSO gateway:** proxy xác thực Kerberos rồi ứng dụng chỉ tin danh tính qua một kênh nội bộ đã được bảo vệ. **Không** tin `X-Remote-User` hoặc `X-Forwarded-User` do client Internet tự gửi; proxy phải xóa header đầu vào không tin cậy, gắn header sau xác thực, giới hạn đường kết nối (mTLS/network policy) và áp dụng authorization ở ứng dụng.
- **Chuyển sang OIDC/SAML2 từ IdP tích hợp Kerberos:** nhiều IdP có thể dùng Kerberos ở bước xác thực người dùng nhưng phát token/assertion chuẩn để ứng dụng Servlet tiêu thụ. Thường thuận tiện hơn cho browser ngoài domain và kiến trúc hiện đại.

## 5. Dependency: chia thành lớp nào, và kiểm tra trước khi thêm vào pom.xml

Không có một dependency duy nhất làm “bật CAS + JAAS + Kerberos” cùng lúc. Hãy phân loại:

| Nhu cầu thực tế | Thành phần/dependency | Điều kiện cần kiểm tra |
| --- | --- | --- |
| Web Servlet có Spring Security filter chain | `spring-boot-starter-security`, `spring-boot-starter-web` nếu dùng Boot | Phiên bản Boot/Java/Jakarta Servlet tương thích. |
| Login với CAS ticket protocol | Module/adapter CAS phù hợp; `spring-security-cas` là tên lịch sử phổ biến | Có tồn tại artifact bản tương thích không; service URL, CAS server, validator, logout, session. |
| CAS Server expose OIDC | `spring-boot-starter-oauth2-client` | IdP issuer, client registration, secret, redirect URI, OIDC claims. |
| Tích hợp LoginModule JAAS thuần Java | JDK `javax.security.auth.*`; không cần dependency Maven riêng cho API JAAS | LoginModule đáng tin, callback, configuration, Subject, role bridge. |
| Spring Security gọi JAAS | JAAS adapter/provider có trong phiên bản Spring Security đã chọn | API hiện hành, authority mapping, session/context, lifecycle logout. |
| Kerberos/GSS-API trong JVM | JDK Kerberos/GSS/JAAS | KDC, realm, service principal, keytab, krb5.conf, clock, DNS. |
| HTTP SPNEGO trong Spring Servlet | Adapter/extension Kerberos tương thích, lịch sử gồm `spring-security-kerberos-core`, `spring-security-kerberos-web` | Tương thích Spring Security/Servlet, browser Negotiate, SPN, keytab. |
| SPNEGO tại ingress/proxy | Reverse proxy có cơ chế Kerberos phù hợp + phương pháp truyền danh tính đã xác thực | Xóa header giả mạo, mTLS/trust boundary, internal access, auditing. |
| API nhận JWT bearer token | `spring-boot-starter-oauth2-resource-server` | Issuer/audience/JWK/token lifetime. Không dùng CAS ST hoặc SPNEGO token trực tiếp. |

### 5.1. Checklist kiểm tra dependency theo release

Trước khi chỉnh pom/build:

1. Xác nhận **Java 17+**, Spring Boot và Spring Security phiên bản nào; xem BOM quản lý các module core nào.
2. Kiểm tra artifact **thực sự tồn tại** và còn được hỗ trợ trên release mục tiêu; ghi rõ phiên bản **extension riêng** nếu BOM không quản lý.
3. Xác nhận có dùng **`jakarta.servlet.*`** (Boot 3/Spring Security 6) hay `javax.servlet.*` (hệ thống cũ); không mix bừa bộ adapter biên dịch cho namespace khác.
4. Kiểm tra dependency tree để tránh xung đột `spring-security-core`, servlet APIs, HTTP client và thư viện CAS/Kerberos bên thứ ba.
5. Tránh `WebSecurityConfigurerAdapter` từ ví dụ cũ; cấu hình Servlet hiện đại dùng `SecurityFilterChain` bean với DSL thích hợp.
6. Nếu nguồn SSO hỗ trợ OIDC/SAML2 tốt hơn giao thức cũ, đánh giá phương án chuẩn thay vì trói hệ thống vào bridge chưa có người duy trì.
7. Có integration test với **CAS server / realm / browser thật** trước production; unit test thuần Java không thể chứng minh ticket protocol hoặc SPNEGO end-to-end đúng.

**Không nên** đưa một danh sách Maven version cố định kiểu “CAS 6 + Kerberos 2 + Security 6 = chắc chắn chạy”. Các module này không nhất thiết phát hành đồng bộ.

## 6. Authentication, authority và việc liên kết danh tính

Dù dùng CAS, JAAS hay Kerberos, Spring Security authorization vẫn dựa vào `Authentication` và các `GrantedAuthority` mà ứng dụng tin cậy.

Ví dụ:

~~~text
CAS principal "an" + attribute groups=["finance"]
JAAS Subject có UserPrincipal("an") + GroupPrincipal("finance")
Kerberos principal "an@EXAMPLE.COM" + AD group lookup
                         |
                         v
       Chuẩn hóa định danh theo nguồn đáng tin
                         |
                         v
   Policy ứng dụng: finance -> ROLE_FINANCE_VIEWER
                         |
                         v
       hasRole("FINANCE_VIEWER")
                         |
                         v
  Kiểm tra tiếp quyền trên resource/tenant/owner
~~~

Các yêu cầu an toàn:

- **Không tự động map** mọi tên nhóm, tên realm hoặc `Principal.getName()` thành quyền admin.
- Chỉ chuyển đổi bằng **allowlist** và mapping có người sở hữu; ví dụ `engineering` → `ROLE_ENGINEER` là một quyết định nghiệp vụ, không phải quy tắc chuẩn CAS/JAAS/Kerberos.
- Định danh `an` từ CAS realm A không mặc nhiên trùng `an` từ realm B. Nên gắn identity với issuer/realm nguồn, tránh **account confusion**.
- Xử lý chủ thể **người dùng** khác chủ thể **máy/dịch vụ**. Với Kerberos service principal, việc đã xác thực SPN không có nghĩa có quyền người dùng.
- Vai trò có thể thay đổi sau khi đăng nhập; khi authentication được lưu trong session, cần chính sách **refresh/re-login/revoke** nếu muốn quyền cập nhật nhanh.
- Endpoint `/admin` có thể dùng `hasRole("ADMIN")`, nhưng với dữ liệu nhiều tenant vẫn cần **object-level authorization**.

### 6.1. Khi nào yêu cầu session, khi nào không?

- **CAS web SSO:** sau khi xác minh service ticket, ứng dụng thường tạo session xác thực nội bộ; nên xem xét session timeout, fixation protection và logout.
- **JAAS:** kết quả `Subject`/principal không tự tạo session HTTP; adapter Spring hoặc app phải quyết định cách quản lý `Authentication` và SecurityContext.
- **SPNEGO:** browser có thể trao token trong HTTP negotiation; app/gateway có thể tạo session để giảm lượt xác thực, hoặc xác thực theo request tùy thiết kế. Session lifecycle, caching và identity freshness phải được xác định rõ.
- **OAuth2/OIDC login:** web app có thể duy trì session sau login; dù IdP bên dưới xác thực bằng Kerberos, app vẫn cần quản lý session riêng.

**CSRF:** Nếu xác thực dựa trên **cookie tự động gửi** và có request đổi trạng thái, cần bảo vệ CSRF phù hợp. Việc dùng CAS hay Kerberos không phải lý do để tắt CSRF. Ngược lại, API hoàn toàn stateless nhận bearer token trong Authorization header có thể có đánh giá CSRF khác, nhưng không nên áp chính sách đó mù quáng cho ứng dụng web/session.

## 7. Phạm vi tích hợp với Spring Security Servlet

### 7.1. Cấu hình web Spring Security cơ sở

Với ứng dụng Servlet hiện đại dùng một cơ chế login đã được kết nối phù hợp, authorization vẫn được định nghĩa qua `SecurityFilterChain`:

~~~java
// Trích đoạn bên trong phương thức cấu hình HttpSecurity:
// Chưa đủ để chạy CAS, JAAS hay Kerberos; provider/filter phải được đăng ký riêng.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/health").permitAll()
    .requestMatchers("/finance/**").hasRole("FINANCE_VIEWER")
    .anyRequest().authenticated()
);
~~~

Điểm cần hiểu: `authorizeHttpRequests` chỉ mô tả **điều kiện truy cập**; nó **không** cài đặt CAS service ticket validation, JAAS LoginModule hoặc SPNEGO ticket verification.

Các ví dụ cũ có `WebSecurityConfigurerAdapter`, `configure(AuthenticationManagerBuilder)` hoặc `antMatchers` có thể cần chuyển đổi theo phiên bản. Không copy đoạn mã cũ vào Spring Security 6 rồi giả định biên dịch.

### 7.2. Điều kiện riêng cho từng phương án

**CAS direct ticket flow:**

- Endpoint/cơ chế redirect đúng CAS login service; service ticket validator xác thực bằng CAS Server.
- URL callback đúng public origin khi đi qua reverse proxy.
- Provider chuyển principal hợp lệ thành `Authentication` và gán authorities.
- Session/cookie/SLO và xử lý lỗi ticket replay.
- Adapter tương thích với runtime và cơ chế Spring Security hiện tại.

**JAAS bridge:**

- Một hoặc nhiều `LoginModule` đáng tin + `Configuration` rõ ràng.
- `CallbackHandler` nhận credential đúng cách, không giữ password trong log/string lâu dài.
- Adapter dùng `Subject` đúng lifecycle và kết nối với `SecurityContext`.
- Mapping `Principal` → `GrantedAuthority` theo policy; kiểm thử login/logout/abort.
- Lựa chọn JAAS chỉ khi cần tích hợp legacy/runtime; không tái tạo toàn bộ Spring Security authentication khi đã có protocol chuẩn tốt hơn.

**Kerberos/SPNEGO:**

- KDC/realm/SPN/keytab cùng đường truyền chứng thực.
- Filter/adapter/gateway hiểu `Authorization: Negotiate` và phản hồi challenge `WWW-Authenticate: Negotiate`.
- Browser chính sách intranet/Negotiate và DNS hostname phù hợp.
- Principal mapping, role lookup, reverse proxy trust boundary, timeout và fallback.
- Kiểm thử domain-joined clients thực, không chỉ unit test bằng fake principal.

## 8. Xử lý lỗi: phân biệt bằng chứng xác thực và môi trường

| Hiện tượng | Hướng chẩn đoán hợp lý |
| --- | --- |
| CAS liên tục chuyển giữa app và CAS login | Kiểm tra service URL, HTTPS/public host, cookie/session, callback path, ticket validator và browser. |
| CAS báo ticket không hợp lệ | Ticket đã dùng/hết hạn, sai service, CAS endpoint sai hoặc lỗi xác thực server-to-server. |
| CAS login thành công nhưng `/admin` trả 403 | Principal đã được xác thực nhưng thiếu authority nghiệp vụ hoặc bị policy từ chối. |
| JAAS `LoginException` | Kiểm tra LoginModule, login.config, CallbackHandler, flag và nguồn dữ liệu xác thực. |
| JAAS `Subject` có principal nhưng Spring thiếu role | Thiếu/bất nhất mapping từ principal sang `GrantedAuthority`; không phải cứ có Subject là có ROLE. |
| Browser Kerberos lặp 401 Negotiate | Kiểm tra SPN, keytab, realm, DNS, browser integrated auth và thời gian KDC/client/server. |
| Kerberos chạy với một hostname nhưng lỗi với alias | SPN không khớp FQDN/alias hoặc browser không gửi ticket cho hostname đó. |
| Kerberos qua proxy lỗi | Proxy có thể bỏ header `Authorization: Negotiate`, terminate auth mà chưa truyền identity an toàn, hoặc đổi hostname. |
| Chạy JDK JAAS demo ổn nhưng web CAS/Kerberos không chạy | Demo chỉ chứng minh JAAS lifecycle; CAS/Kerberos cần IdP/KDC/browser/protocol adapter thật. |
| Adapter Spring legacy bị lỗi class/method | Spring Security/Boot/Servlet namespace hoặc dependency version không tương thích. |
| Đăng nhập được nhưng tài liệu tenant khác vẫn xem được | Lỗi authorization theo đối tượng; không phụ thuộc giao thức authentication. |

**Không debug bằng cách log TGT, service ticket, keytab, password, client secret hoặc full `Authorization` header.** Log tên bước, loại lỗi, correlation ID và số liệu an toàn; giữ các credential ngoài log/tracing.

## 9. Kiểm thử và nghiệm thu theo hạ tầng

**Unit test** có thể xác nhận mapping authority, validation policy và callback JAAS. **Integration test** mới kiểm chứng cơ chế ticket/SSO thực tế:

| Bài kiểm thử | CAS | JAAS | Kerberos/SPNEGO |
| --- | --- | --- | --- |
| Đăng nhập đúng | CAS Server phát ST, app validate, session tạo đúng | LoginModule + handler/login success | Browser nhận Negotiate challenge, ticket được chấp nhận |
| Đăng nhập sai/credential hết hiệu lực | ST invalid/expired/replayed bị từ chối | `LoginException` và không còn principal đặc quyền | Ticket expired, sai SPN/keytab hoặc realm trust bị từ chối |
| Quyền | Claims/groups map allowlist, `/admin` thiếu quyền → 403 | Subject principals map đúng ROLE | Kerberos principal/AD group map đúng ROLE |
| Logout/revocation | App logout, CAS SLO nếu triển khai | LoginModule logout/abort; Spring session clear | Session logout/freshness, keytab rotation |
| Hạ tầng | CAS unreachable/TLS error → không fail open | Auth backend unavailable → không tự cấp quyền | KDC/DNS/clock/browser policy/alias/proxy |
| Bảo vệ web | HTTPS, session cookie, CSRF, open redirect | Credential handling, session và CSRF nếu có | HTTPS, reverse proxy trust, CSRF nếu có cookie session |

**Chạy thử JAAS demo**: `javac JaasFlowDemo.java` rồi `java JaasFlowDemo`. Đây chỉ là bài kiểm chứng JDK API.

**Chạy thử CAS hoặc Kerberos**: bắt buộc có môi trường tương ứng và tài khoản được phép dùng. Không thể trung thực hứa một chương trình Java độc lập sẽ kiểm chứng SSO CAS/Kerberos nếu thiếu CAS Server/KDC, SPN, keytab, browser và policy thực tế.

### 9.1. Checklist trước triển khai production

1. Xác nhận **phương thức đăng nhập thật** của tổ chức: CAS service-ticket, OIDC/SAML2 qua CAS, JAAS module, Kerberos SPNEGO hay IdP dùng Kerberos ở backend.
2. Chọn dependency/adapter **được duy trì và tương thích** với Java/Boot/Security/Servlet đang dùng; kiểm tra BOM và namespace.
3. Chứng minh ứng dụng chỉ tin **CAS Server / LoginModule / KDC / proxy identity** đã được xác thực trong trust boundary.
4. Quản lý HTTPS, cert, client secret, keytab, realm/SPN, DNS và đồng bộ thời gian.
5. Tách authentication và role mapping; có allowlist và kiểm tra **resource/tenant**.
6. Thử các nhánh invalid/replayed ticket, role thiếu, expired credential, backend unavailable, session timeout, logout và reverse proxy.
7. Không tắt mặc định CSRF/session protection chỉ vì cơ chế đăng nhập là SSO.
8. Có kế hoạch rotation, monitoring, audit và phương án khi IdP/KDC không khả dụng.
9. Nếu cần hỗ trợ mobile/external users, cân nhắc OIDC/SAML2 chính thống thay vì buộc mọi client dùng Kerberos browser negotiation.
10. Ghi rõ trách nhiệm: ai vận hành CAS/KDC/AD/adapter, ai phê duyệt mapping quyền, ai xử lý sự cố và key rotation.

## 10. Câu hỏi tự kiểm tra

**1.** “JAAS và Kerberos là hai giao thức SSO browser tương đương” — đúng không?

**Trả lời:** Không. JAAS là API Java để điều phối LoginModule/Subject; Kerberos là giao thức xác thực mạng. Một LoginModule JAAS có thể tương tác với Kerberos trong cấu hình phù hợp.

**2.** Thêm `spring-boot-starter-security` đã đủ để CAS login hoạt động chưa?

**Trả lời:** Chưa. Phải có CAS Server, service URL, ticket validation adapter và phiên bản tương thích hoặc chọn OIDC/SAML2 nếu CAS Server hỗ trợ.

**3.** Ứng dụng Spring Boot 3 có nên copy trực tiếp `spring-security-cas` version bất kỳ từ bài Spring 4 cũ không?

**Trả lời:** Không. Phải kiểm tra artifact còn hỗ trợ, Java/Spring/Servlet namespace và dependency tree. Nếu dùng CAS Server như OIDC IdP, dùng OAuth2 Client tích hợp OIDC sẽ phù hợp hơn trong nhiều dự án.

**4.** Vì sao SPNEGO hoạt động trên laptop domain-joined nhưng không hoạt động trên điện thoại cá nhân?

**Trả lời:** Browser/OS/device có thể không có TGT hoặc không được cấu hình cho integrated authentication với hostname/realm. Còn cần KDC, DNS, SPN và policy mạng phù hợp.

**5.** CAS/JAAS/Kerberos đã xác thực “admin” thì có thể bỏ `hasRole` và kiểm tra tenant không?

**Trả lời:** Không. Authentication xác nhận danh tính; authority mapping và authorization của ứng dụng mới quyết định người đó được truy cập endpoint và đối tượng nào.

**6.** Vì sao không cho phép application server tin `X-Remote-User` từ bất kỳ request nào?

**Trả lời:** Client có thể tự giả header. Chỉ tin header được gateway xác thực gắn vào sau khi xóa dữ liệu client và bảo vệ kết nối/trust boundary; vẫn kiểm tra quyền trong ứng dụng.

**7.** Mẫu JAAS Java 17 ở trên đã kiểm tra được Kerberos hay CAS chưa?

**Trả lời:** Chưa. Nó chỉ minh họa LoginContext/LoginModule/Subject, với credential giả lập. CAS cần CAS Server/ticket validator; Kerberos cần KDC/realm/SPN/keytab/client Negotiate.

---

## Kết luận

**CAS** giải quyết SSO qua **service ticket**; **JAAS** là API xác thực của **Java** có thể bridge các LoginModule vào Spring; **Kerberos** là giao thức xác thực bằng ticket, thường đi qua **SPNEGO/HTTP Negotiate** trong intranet. Mỗi công nghệ yêu cầu **hạ tầng, dependency và điều kiện vận hành khác nhau**. Đừng đồng nhất CAS ST với OAuth bearer token, đừng coi JAAS Subject tự sinh quyền Spring và đừng nghĩ thêm thư viện Kerberos là đủ khi chưa có SPN/keytab/KDC/browser policy.

**Nguyên tắc an toàn:** xác minh phiên bản adapter; xác thực ticket/credential với nguồn đáng tin; map authorities bằng allowlist; dùng HTTPS; kiểm soát session/CSRF/logout; và luôn kiểm tra authorization theo tài nguyên sau khi login.