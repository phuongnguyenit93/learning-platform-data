# SunJaasKerberosTicketValidator, service principal và keytab

**Module:** Spring Security – federation  
**Nhóm kiến thức:** Tích hợp Kerberos  
**Stack dùng để học:** Kerberos V5, HTTP SPNEGO/Negotiate, JAAS/JGSS của JDK, Spring Security Kerberos **2.2.0**, Spring Security **6.5.x**, Spring Boot **3.x** phù hợp, Java **17+**.

## 1. Bài toán: xác thực người dùng bằng ticket dành riêng cho website

Trong môi trường Active Directory (AD) hoặc Kerberos KDC, nhân viên đã đăng nhập vào máy doanh nghiệp có thể mở website nội bộ và được nhận diện mà không nhập lại mật khẩu. Trình duyệt và ứng dụng thực hiện cơ chế **HTTP Negotiate / SPNEGO**. Ứng dụng Spring Security phải xác minh ticket Kerberos do browser gửi, thay vì tin trực tiếp vào một username được đính kèm trong header.

Ba thành phần quan trọng nhất:

1. **SunJaasKerberosTicketValidator:** bộ kiểm tra Kerberos/SPNEGO service ticket trên server dùng JAAS/JGSS và Kerberos implementation của Sun/Oracle/OpenJDK.
2. **Service principal (SPN):** danh tính Kerberos của service HTTP mà browser yêu cầu, ví dụ **HTTP/portal.example.org@EXAMPLE.ORG**.
3. **Keytab:** file chứa khóa bí mật dài hạn cho service principal; server dùng nó để chấp nhận Kerberos ticket mà KDC đã mã hóa cho service đó.

Để đưa kết quả vào Spring Security, ta dùng **SpnegoAuthenticationProcessingFilter** và **KerberosServiceAuthenticationProvider**. Sau khi ticket được xác minh, UserDetailsService nạp quyền/roles cục bộ. Ticket có chữ ký/khóa phù hợp **không** tự đồng nghĩa với quyền đọc hồ sơ, phê duyệt hóa đơn hay ROLE_ADMIN.

**Nguyên tắc học:** SPN và keytab thuộc về **service**, còn Kerberos principal trong ticket thuộc về **người dùng**. Đừng dùng user principal làm service principal hoặc lưu password người dùng trong keytab ứng dụng.

## 2. Tổng quan luồng HTTP/SPNEGO

~~~text
Browser (ALICE)               Spring web app                  KDC / Active Directory
       |                             |                                  |
       | GET /private                |                                  |
       |---------------------------->|                                  |
       |<----------------------------| 401 WWW-Authenticate: Negotiate  |
       |                             |                                  |
       | Xin ticket cho              |                                  |
       | HTTP/portal.example.org     |                                  |
       |---------------------------------------------------------------->|
       |<----------------------------------------------------------------|
       | service ticket cấp riêng cho HTTP/portal.example.org             |
       |                             |                                  |
       | GET /private                |                                  |
       | Authorization: Negotiate ...|                                  |
       |---------------------------->| SpnegoAuthenticationFilter       |
       |                             | KerberosServiceProvider          |
       |                             | SunJaasKerberosTicketValidator   |
       |                             | JAAS/JGSS dùng keytab của SPN    |
       |                             | -> alice@EXAMPLE.ORG             |
       |                             | UserDetailsService/authorities   |
       |<----------------------------| 200/403 hoặc lỗi Kerberos         |
~~~

Sơ đồ là **happy path rút gọn**. SPNEGO có thể cần hơn một vòng 401/Negotiate, KDC có thể tham gia các bước ticket khác nhau và client có thể không hỗ trợ Kerberos. Header **Authorization: Negotiate** mang SPNEGO/GSS token, không phải một SAMLResponse, CAS Service Ticket hay OAuth Bearer JWT.

Chi tiết xử lý trong Spring Security:

- **SpnegoEntryPoint** phát HTTP challenge WWW-Authenticate: Negotiate khi request cần authentication.
- **SpnegoAuthenticationProcessingFilter** đọc Negotiate header và tạo **KerberosServiceRequestToken** để đưa vào AuthenticationManager.
- **KerberosServiceAuthenticationProvider** gọi **KerberosTicketValidator** đã cấu hình, thường là SunJaasKerberosTicketValidator.
- Validator dùng **JAAS/Krb5LoginModule** và **JGSS acceptor** với service keytab để kiểm tra token; khi thành công, nó trả kết quả cho provider.
- **UserDetailsService** tra danh tính cục bộ để xác định GrantedAuthorities, disabled status hoặc policy.
- SecurityContext được sử dụng để quyết định quyền và có thể được lưu trong HttpSession nếu ứng dụng browser stateful.

**Không tự Base64-decode header rồi coi chuỗi là username.** Token phải được trình xác minh Kerberos kiểm tra về mật mã, không chỉ có cú pháp hợp lệ.

## 3. Service principal là gì?

Một service principal web thường có dạng:

~~~text
HTTP/portal.example.org@EXAMPLE.ORG

HTTP                   service class
portal.example.org     canonical FQDN mà browser truy cập
EXAMPLE.ORG            Kerberos realm
~~~

**HTTP** là service class của Kerberos, không có nghĩa chỉ được truyền trên HTTP không mã hóa. SPNEGO thường kết hợp HTTPS để bảo vệ browser request, session cookie và traffic.

**FQDN** nên khớp hostname công khai browser dùng. Ví dụ:

~~~text
Browser: https://portal.example.org/private
Reverse proxy: http://portal-service:8080/private
Ticket service principal: HTTP/portal.example.org@EXAMPLE.ORG
~~~

Nếu keytab của Java backend chỉ có **HTTP/portal-service@EXAMPLE.ORG** nhưng client nhận ticket cho **HTTP/portal.example.org@EXAMPLE.ORG**, backend không thể tùy tiện dùng key của tên backend để nhận ticket công khai. Chọn canonical external hostname hoặc thiết kế alias/SPN bổ sung có quản lý.

**Realm** là namespace của Kerberos. Dấu @EXAMPLE.ORG không tự bắt buộc trùng hoàn toàn tên miền DNS; ví dụ một web host portal.corp.example có thể dùng realm AD.EXAMPLE.ORG nếu KDC/krb5.conf và AD được cấu hình đúng.

### 3.1. SPN và AD service account không đồng nhất

| Giá trị | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Public URL | https://portal.example.org | Website |
| Kerberos HTTP SPN | HTTP/portal.example.org@EXAMPLE.ORG | Principal mà ticket hướng tới |
| AD account owner | EXAMPLE\svc-webportal | Account giữ khóa cho SPN |
| Keytab path | /run/secrets/http-portal.keytab | File khóa trên server |
| Client identity | alice@EXAMPLE.ORG | Người dùng đã được xác thực |
| Local app user | user_id=1001 | Tài khoản/quyền nội bộ |

Trong AD, **SPN cần gắn đúng một account owner theo chính sách**. Các SPNs trùng hoặc sai owner có thể khiến ticket không được cấp hoặc bị từ chối khi accept.

Để xem mapping AD **mà không tự thay đổi**:

~~~powershell
setspn -Q HTTP/portal.example.org
setspn -L EXAMPLE\svc-webportal
~~~

Đây là các lệnh xem SPN trên máy Windows có công cụ/đặc quyền tra AD. Không tự chạy các thao tác thêm/xóa SPN trên production ngoài quy trình IAM.

### 3.2. Nhiều aliases và multi-tenant

Hai host **portal.example.org** và **intranet.example.org** có thể khiến client xin hai tickets khác nhau dù cùng trỏ một IP. Một keytab có thể chứa nhiều principals nếu được quản trị đúng, nhưng một **SunJaasKerberosTicketValidator** thường được cấu hình hướng tới **một servicePrincipal xác định**. Không suy ra nó tự chấp nhận mọi alias chỉ vì DNS CNAME chung.

Nếu ứng dụng dùng nhiều host/realm, cần thiết kế các trusted SPNs, acceptors/registrations và routing rõ ràng; không dùng Host header tự khai để thay đổi servicePrincipal ở runtime rồi bỏ các kiểm tra bảo mật.

## 4. Keytab là gì và vì sao nhạy cảm?

**Keytab** là file chứa khóa bí mật Kerberos cho một hoặc nhiều principals. Những entry thường bao gồm:

- **Principal:** ví dụ HTTP/portal.example.org@EXAMPLE.ORG.
- **KVNO (Key Version Number):** phiên bản key; có thể thay đổi khi service account rotate password/key.
- **Enctype:** loại mã hóa, ví dụ AES256/AES128 được KDC, JDK và chính sách cho phép.
- **Key material:** secret bytes thực tế, giúp service chấp nhận ticket.

**Keytab không phải danh sách user tickets, không phải TGT của người dùng, và không phải file cấu hình plaintext vô hại.** Người có khả năng truy cập keytab cùng môi trường thích hợp có thể giả mạo service, vì vậy phải bảo vệ như credential mật.

### Kiểm tra keytab không làm lộ key bytes

Trên Linux có MIT Kerberos tools:

~~~bash
klist -k -e /run/secrets/http-portal.keytab
~~~

Lệnh thường hiển thị principal, KVNO, encryption types. **Không thêm -K**, vì tham số đó có thể in khóa bí mật. Không chia sẻ bản keytab hoặc kết quả debug chứa key material trong chat, issue công khai hay repository.

Điều cần đối chiếu:

~~~text
servicePrincipal trong Java:
  HTTP/portal.example.org@EXAMPLE.ORG

Principal trong keytab:
  HTTP/portal.example.org@EXAMPLE.ORG

KVNO/enctype của keytab:
  phải có key có thể chấp nhận ticket mà KDC đang phát.
~~~

**Có entry đúng text chưa chứng minh ticket hợp lệ:** key bytes có thể lỗi, KVNO cũ, enctype không được hỗ trợ, clocks lệch hoặc JAAS không đọc được file.

### Vị trí file và permission

Khuyến nghị đặt keytab ngoài source/JAR, ví dụ **/run/secrets/http-portal.keytab**, mount từ secrets manager/volume có quyền chặt. JVM runtime phải có quyền **read** theo UID/GID thực; không mở quyền cho tất cả users và không chạy root chỉ để dễ đọc.

Trong môi trường hỗ trợ ACL/POSIX, admin có thể thiết lập quyền chỉ đọc cho process owner, ví dụ file mode **0400**. Đường dẫn/mount trong container phải là nơi **JVM nhìn thấy**, không phải nơi file tồn tại trên laptop của developer.

### Vì sao ưu tiên FileSystemResource?

API validator nhận Spring **Resource** qua **setKeyTabLocation(Resource)**. Tuy có thể dùng các prefixes file:/classpath:, **JAAS thường cần một path thực trên filesystem**; resource đóng gói trong fat JAR không luôn tương thích. Tài liệu Spring Kerberos khuyến nghị dùng file resource và bảo vệ file.

~~~java
validator.setKeyTabLocation(
    new FileSystemResource("/run/secrets/http-portal.keytab"));
~~~

Đây là fragment Java trong Bean setup, không phải lệnh tạo keytab. Không nhúng keytab vào src/main/resources hoặc Docker image để tiện build.

## 5. SunJaasKerberosTicketValidator dùng những API nào?

Class:

~~~text
org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator
~~~

Đây là implementation của **KerberosTicketValidator** cho Sun/Oracle/OpenJDK Kerberos/JAAS/JGSS. Nó hoạt động ở vai trò **service acceptor**, không phải một KDC mini và không tự cấp service tickets cho user.

| Setter/method | Tác dụng | Cảnh báo |
| --- | --- | --- |
| **setServicePrincipal(String)** | Chọn principal của service | Phải đúng SPN được KDC phát và khóa tương ứng |
| **setKeyTabLocation(Resource)** | Nạp vị trí keytab | Dùng file resource tới secret được bảo vệ |
| **setDebug(boolean)** | Debug JAAS login module | Mặc định không bật production |
| **setRealmName(String)** | Cung cấp realm khi cấu hình cần | Khác hostname của server |
| **setRefreshKrb5Config(boolean)** | Refresh cấu hình krb5 trước login theo thiết lập | Không chữa sai SPN/keytab |
| **setMultiTier(boolean)** | Hỗ trợ một số trường hợp multi-tier/Subject copy | Chỉ dùng nếu thực sự cần, cần test |
| **setHoldOnToGSSContext(boolean)** | Giữ GSSContext sau accept cho tương tác tiếp | Mặc định dispose; có chi phí vòng đời |
| **validateTicket(byte[])** | Xác minh Kerberos/SPNEGO token | Chỉ dùng với token đúng giao thức từ filter/manager |

Cấu hình tối thiểu:

~~~java
SunJaasKerberosTicketValidator validator =
    new SunJaasKerberosTicketValidator();

validator.setServicePrincipal(
    "HTTP/portal.example.org@EXAMPLE.ORG");
validator.setKeyTabLocation(
    new FileSystemResource("/run/secrets/http-portal.keytab"));
validator.setDebug(false);
~~~

**Sự khác biệt quan trọng:** **SunJaasKerberosClient** ở phía initiator có thể dùng để lấy Kerberos credentials khi Java gọi một service khác. **SunJaasKerberosTicketValidator** ở phía acceptor dùng keytab của service để chấp nhận ticket mà browser gửi. Không dùng một class thay class còn lại chỉ vì cùng có chữ Kerberos.

### Validator xác minh đến mức nào?

JGSS/Kerberos xử lý ticket proof-of-possession và mã hóa/khóa phù hợp, trả về client identity khi thành công. Tuy nhiên:

- Không tự biết local user còn enabled hay không.
- Không tự biết quyền đọc document 42, vai trò manager, tenant hoặc luật phê duyệt.
- Không cho phép ứng dụng tin một header X-User do reverse proxy hoặc browser tự khai.
- Không thay TLS, CSRF protection, session fixation protection và authorization trên từng resource.

Nếu ticket đúng mật mã nhưng UserDetailsService báo không có local user được phép, Spring vẫn phải từ chối theo policy.

## 6. Hạ tầng bắt buộc: KDC, realm, DNS, NTP và browser

Một app dù code hoàn chỉnh vẫn không thể tự tạo Kerberos realm chỉ bằng application.yml. Cần:

1. **KDC/Active Directory** có realm và xác thực người dùng.
2. **HTTP SPN** được đăng ký cho đúng service account.
3. **Keytab** cùng principal/keys/KVNO/enctypes được cấp bởi đơn vị quản lý KDC.
4. **DNS/FQDN** phù hợp với URL mà browser mở và principal mà KDC phát ticket.
5. **Thời gian đồng bộ** giữa KDC, clients và app; tránh lỗi clock skew.
6. **Browser/OS Negotiate policy** cho site nội bộ tin cậy; workstation có credentials Kerberos.
7. **Network path/TLS proxy** giữ nguyên Authorization: Negotiate và channel-binding policy phù hợp.
8. **Spring SecurityFilterChain** đặt SPNEGO filter/entrypoint/provider chính xác.

### Mẫu krb5.conf để đọc hiểu

~~~ini
[libdefaults]
 default_realm = EXAMPLE.ORG
 dns_lookup_kdc = true
 rdns = false

[realms]
 EXAMPLE.ORG = {
   kdc = dc1.example.org
   kdc = dc2.example.org
 }

[domain_realm]
 .example.org = EXAMPLE.ORG
 example.org = EXAMPLE.ORG
~~~

Đây là file **minh họa**, không phải cấu hình KDC production. Một số môi trường dùng DNS SRV và cross-realm trust; mapping host-to-realm phải theo tổ chức.

JVM có thể chỉ rõ cấu hình:

~~~bash
java -Djava.security.krb5.conf=/etc/krb5.conf -jar application.jar
~~~

Chỉ chạy khi có file/JAR/môi trường thích hợp. Debug có thể bật thông qua cờ Java phù hợp trong **môi trường test có kiểm soát**; không log toàn bộ token hay keytab.

### Đồng hồ và timezone

Ticket Kerberos có thời gian bắt đầu/kết thúc và chấp nhận clock skew có giới hạn theo chính sách KDC. Clock app hoặc client lệch giờ có thể dẫn đến **Clock skew too great** hoặc ticket expired. Đồng bộ NTP/chrony và kiểm tra UTC; **không** bỏ time checks hay kéo dài ticket lifetime vô hạn để chữa cấu hình sai.

## 7. Chọn dependency đúng phiên bản

**Spring Security Kerberos 2.2.0** là một extension được tài liệu hóa là build/test trên **JDK 17**, **Spring Security 6.5.1** và **Spring Framework 6.2.8**. Nó dùng Maven group:

~~~text
org.springframework.security.kerberos
    spring-security-kerberos-core
    spring-security-kerberos-web
    version 2.2.0
~~~

Dòng **Spring Security Kerberos 7.x** thay Maven group thành **org.springframework.security**, tương ứng Spring Security 7/Framework 7; **không** trộn artifact 7.x vào Spring Boot 3 / Spring Security 6.x.

Với Boot 3.x, cần chọn bản Boot phù hợp Spring Security 6.5.x và kiểm tra actual dependency tree. Không khẳng định mọi Boot 3.0–3.5 dùng extension 2.2.0 mà không cần chỉnh dependency. Mã Java bên dưới hướng tới phiên bản **2.2.0 + Security 6.5.x**.

## 8. Dự án Spring Boot 3 / Java 17: SPNEGO service-side

Ví dụ gồm main class, một SecurityFilterChain, SunJaasKerberosTicketValidator, provider, filter và controller. Đây là **mẫu tích hợp có thể biên dịch trong dự án đúng dependency**, nhưng muốn xác thực end-to-end vẫn cần AD/KDC, SPN, keytab, browser có Kerberos TGT và URL công khai khớp.

### 8.1. Dependencies

Trong phần **dependencies** của pom.xml có Spring Boot parent/BOM tương thích Spring Security 6.5:

~~~xml
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
    <groupId>org.springframework.security.kerberos</groupId>
    <artifactId>spring-security-kerberos-core</artifactId>
    <version>2.2.0</version>
  </dependency>
  <dependency>
    <groupId>org.springframework.security.kerberos</groupId>
    <artifactId>spring-security-kerberos-web</artifactId>
    <version>2.2.0</version>
  </dependency>
</dependencies>
~~~

Khai báo cả core và web vì code import classes từ cả hai. Không giả định Boot BOM quản lý chính xác version extension, vì thế ví dụ pin **2.2.0**. Khi gặp class/method mismatch, kiểm tra dependency tree trước khi thay API bằng code tự chế.

### 8.2. application.yml

**src/main/resources/application.yml**

~~~yaml
app:
  kerberos:
    service-principal: "HTTP/portal.example.org@EXAMPLE.ORG"
    keytab-path: "/run/secrets/http-portal.keytab"

server:
  servlet:
    session:
      timeout: 30m
~~~

**service-principal** phải match SPN do KDC/AD phát ticket và **keytab-path** phải là file thực trong JVM container. Session timeout 30 phút là thời gian idle của HttpSession ứng dụng, **không** định nghĩa hạn TGT/service ticket tại KDC.

### 8.3. Main class

**src/main/java/com/example/kerberos/KerberosApplication.java**

~~~java
package com.example.kerberos;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KerberosApplication {

    public static void main(String[] args) {
        SpringApplication.run(KerberosApplication.class, args);
    }
}
~~~

### 8.4. Security configuration

**src/main/java/com/example/kerberos/KerberosSecurityConfig.java**

~~~java
package com.example.kerberos;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class KerberosSecurityConfig {

    @Bean
    SunJaasKerberosTicketValidator ticketValidator(Environment env) {
        String principal = env.getRequiredProperty(
            "app.kerberos.service-principal");
        String keytabPath = env.getRequiredProperty(
            "app.kerberos.keytab-path");

        SunJaasKerberosTicketValidator validator =
            new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(principal);
        validator.setKeyTabLocation(
            new FileSystemResource(keytabPath));
        validator.setDebug(false);
        return validator;
    }

    @Bean
    UserDetailsService localUsers() {
        // Demo: một tài khoản được cho phép vào app.
        // Production: lookup DB/LDAP/tenant, account enabled.
        return username -> {
            if (!"alice@EXAMPLE.ORG".equalsIgnoreCase(username)) {
                throw new org.springframework.security.core.userdetails
                    .UsernameNotFoundException("No enabled local account");
            }
            return User.withUsername(username)
                .password("{noop}unused-for-kerberos")
                .roles("READER")
                .build();
        };
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService localUsers) {
        KerberosServiceAuthenticationProvider provider =
            new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(localUsers);
        return provider;
    }

    @Bean
    SecurityFilterChain browserSecurity(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider provider)
            throws Exception {

        SecurityContextRepository contextRepository =
            new HttpSessionSecurityContextRepository();

        // Không tạo @Bean SpnegoAuthenticationProcessingFilter.
        // Filter chỉ ở trong Spring Security chain này.
        SpnegoAuthenticationProcessingFilter spnego =
            new SpnegoAuthenticationProcessingFilter();
        spnego.setAuthenticationManager(new ProviderManager(provider));
        spnego.setSecurityContextRepository(contextRepository);
        spnego.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .securityContext(sc -> sc
                .securityContextRepository(contextRepository))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .addFilterBefore(spnego, BasicAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Giải thích chi tiết:**

1. **Environment.getRequiredProperty** đọc đúng hai thuộc tính từ YAML; không dùng password service account ở Spring code.
2. **SunJaasKerberosTicketValidator** được cấu hình bằng **service principal** và **FileSystemResource** trỏ tới keytab.
3. **KerberosServiceAuthenticationProvider** sử dụng validator; nếu token Kerberos xác minh thành công, nó cần UserDetailsService để tải authorities/trạng thái account.
4. **SpnegoEntryPoint** gửi challenge **WWW-Authenticate: Negotiate** cho browser chưa authenticated.
5. **SpnegoAuthenticationProcessingFilter** nhận Authorization header và gọi **ProviderManager** gồm Kerberos service provider.
6. **addFilterBefore(..., BasicAuthenticationFilter.class)** đặt filter vào vị trí authentication đúng trong SecurityFilterChain, không đặt sau authorization.
7. **HttpSessionSecurityContextRepository** gắn cho cả chain và filter, quan trọng khi muốn trạng thái authenticated còn lại qua các requests khác thay vì chỉ request đang nhận Negotiate token.
8. **ChangeSessionIdAuthenticationStrategy** giúp chống session fixation khi tạo Authentication mới.
9. **SessionCreationPolicy.IF_REQUIRED** phù hợp với browser stateful. Nếu API dùng Bearer token/stateless, cấu hình một chain riêng với matchers rõ.
10. Filter được tạo bằng **new** trong method SecurityFilterChain, tránh Spring Boot tự đăng ký thêm Servlet Filter bean và khiến filter chạy ngoài chain.
11. **UserDetailsService demo** chỉ cho một principal minh họa. Production không dùng allowlist hardcoded này thay identity-link DB.
12. Không bật debug JAAS production và không log ticket ở header Authorization.

**Giới hạn mẫu:** Đây là cấu hình HTTP SPNEGO và Kerberos service acceptor. Nó không tự tạo/đăng ký SPN trong AD, không tự sinh keytab hoặc cấp TGT cho browser. Nếu username khác alice, UserDetailsService demo từ chối dù ticket hợp lệ; đó là local authorization policy minh họa, không phải lỗi keytab.

### 8.5. Controller

**src/main/java/com/example/kerberos/HelloController.java**

~~~java
package com.example.kerberos;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/")
    public String home() {
        return "Kerberos SPNEGO example ready";
    }

    @GetMapping("/me")
    public Map<String, String> whoAmI(Principal principal) {
        return Map.of(
            "principal", principal.getName(),
            "mechanism", "Kerberos-SPNEGO");
    }
}
~~~

GET **/me** yêu cầu Authentication do **anyRequest().authenticated()**. Sau khi SPNEGO login, SecurityContext có principal cục bộ, không cần mọi GET đều xin service ticket mới nếu HttpSession còn hợp lệ.

### 8.6. Lệnh chạy và thử

Trong project Spring Boot Maven tương thích, có JDK 17+, mount keytab và KDC/AD thật:

~~~bash
mvn spring-boot:run
~~~

Nếu app khởi động và route public được permit:

~~~bash
curl -i http://localhost:8080/
~~~

Body từ controller:

~~~text
Kerberos SPNEGO example ready
~~~

Trên máy Linux **đã có Kerberos user ticket cache** và bản curl có GSSAPI/SPNEGO, với public hostname/SPN thật:

~~~bash
curl --negotiate -u : -i https://portal.example.org/me
~~~

**Không bảo đảm curl thành công chỉ bằng đoạn lệnh này.** Cần realm, KDC, SPN, keytab, TLS và user principal được localUsers chấp nhận. Nếu browser/curl chưa có credentials, có thể nhận HTTP 401; phải phân loại đúng lỗi client, KDC, JAAS hay local roles.

## 9. Java 17 độc lập: bài thực hành về SPN, KVNO và enctype

Ví dụ standalone dưới đây là **mô hình kiểm tra metadata**, không parse keytab thật, không thực hiện Kerberos cryptography và không dùng Spring. Mục đích là hiểu ba lỗi cấu hình thường gặp: sai service principal, keytab thiếu principal, và KVNO/enctype không khớp ticket.

**Tệp: ServicePrincipalPolicyDemo.java**

~~~java
import java.util.List;

public final class ServicePrincipalPolicyDemo {

    enum Result {
        READY_FOR_CRYPTO_VALIDATION,
        WRONG_SERVICE_PRINCIPAL,
        KEYTAB_MISSING_PRINCIPAL,
        KEYTAB_MISSING_KVNO_OR_ENCTYPE
    }

    record KeytabEntry(
        String principal, int kvno, String enctype) { }

    record TicketShape(
        String targetPrincipal, int kvno, String enctype) { }

    static Result preflight(
            String configuredPrincipal,
            TicketShape incoming,
            List<KeytabEntry> entries) {

        if (!configuredPrincipal.equals(incoming.targetPrincipal())) {
            return Result.WRONG_SERVICE_PRINCIPAL;
        }

        boolean hasPrincipal = entries.stream()
            .anyMatch(entry ->
                entry.principal().equals(configuredPrincipal));

        if (!hasPrincipal) {
            return Result.KEYTAB_MISSING_PRINCIPAL;
        }

        boolean matchingKeyMetadata = entries.stream()
            .anyMatch(entry ->
                entry.principal().equals(configuredPrincipal)
                && entry.kvno() == incoming.kvno()
                && entry.enctype().equals(incoming.enctype()));

        return matchingKeyMetadata
            ? Result.READY_FOR_CRYPTO_VALIDATION
            : Result.KEYTAB_MISSING_KVNO_OR_ENCTYPE;
    }

    public static void main(String[] args) {
        String principal =
            "HTTP/portal.example.org@EXAMPLE.ORG";
        String aes = "aes256-cts-hmac-sha1-96";

        List<KeytabEntry> keytab = List.of(
            new KeytabEntry(principal, 7, aes));

        TicketShape correct =
            new TicketShape(principal, 7, aes);
        TicketShape wrongHost =
            new TicketShape("HTTP/backend.example.org@EXAMPLE.ORG",
                7, aes);
        TicketShape oldKvno =
            new TicketShape(principal, 6, aes);

        System.out.println("matching=" +
            preflight(principal, correct, keytab));
        System.out.println("wrongHost=" +
            preflight(principal, wrongHost, keytab));
        System.out.println("oldKvno=" +
            preflight(principal, oldKvno, keytab));
        System.out.println("noPrincipal=" +
            preflight(principal, correct,
                List.of(new KeytabEntry(
                    "HTTP/other.example.org@EXAMPLE.ORG", 7, aes))));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ServicePrincipalPolicyDemo.java
java ServicePrincipalPolicyDemo
~~~

**Stdout chính xác:**

~~~text
matching=READY_FOR_CRYPTO_VALIDATION
wrongHost=WRONG_SERVICE_PRINCIPAL
oldKvno=KEYTAB_MISSING_KVNO_OR_ENCTYPE
noPrincipal=KEYTAB_MISSING_PRINCIPAL
~~~

**Lưu ý bảo mật/giới hạn:** READY_FOR_CRYPTO_VALIDATION chỉ xác nhận **danh mục metadata khớp theo mô hình**, không phải vé đã hợp lệ. JGSS thật còn kiểm tra key bytes, Kerberos ticket integrity, client identity, lifetime, realm, replay và chính sách cơ chế. JDK/KDC có thể chọn keys theo cách phức tạp hơn so khớp ba trường trong demo; đây **không phải thuật toán chuẩn hóa key selection của SunJaasKerberosTicketValidator**.

## 10. Kiểm tra SPN, keytab, client và server bằng công cụ an toàn

### 10.1. AD tra SPN

Trên Windows với công cụ AD:

~~~powershell
setspn -Q HTTP/portal.example.org
setspn -L EXAMPLE\svc-webportal
~~~

Lệnh tra cứu chỉ để biết SPN đã gắn đúng account và có duplicate không. Các thao tác thay đổi SPN/key/password phải do IAM/AD admin thực hiện trong change control.

### 10.2. Linux keytab metadata

Trên node service:

~~~bash
klist -k -e /run/secrets/http-portal.keytab
~~~

Kiểm tra principal, KVNO, encryption type. Nếu file không tồn tại/permission denied, sửa secret mount và quyền JVM; **không in raw keytab** và không dùng option in key như -K.

### 10.3. Client Kerberos cache và ticket

Trên Linux có client Kerberos:

~~~bash
klist
kvno HTTP/portal.example.org@EXAMPLE.ORG
~~~

**klist** liệt kê các tickets user đang có; **kvno** có thể yêu cầu service ticket từ KDC (và vì vậy cần KDC/credentials thật), giúp kiểm tra SPN có tồn tại. Trên Windows có công cụ klist tương ứng. Khi browser không gửi Authorization: Negotiate, kiểm tra site trust/GPO/Integrated Authentication trước khi đổ lỗi cho Java keytab.

### 10.4. HTTP challenge

Khi chưa có session hợp lệ, response có thể chứa:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

Nếu server không phát challenge, xem SpnegoEntryPoint và SecurityFilterChain. Nếu browser phát Negotiate nhưng backend không thấy, xem gateway/proxy có strip header hay không. Nếu đã xác thực nhưng HTTP **403**, kiểm tra local UserDetailsService/authorities/authorization chứ không tự sửa SPN.

## 11. Key rotation, KVNO và encryption types

**Service account password/key rotation** có thể làm KDC chuyển sang KVNO mới, trong khi các pods còn giữ keytab KVNO cũ. Ticket mới có thể không được accept và xuất hiện lỗi như **KRB_AP_ERR_MODIFIED**, integrity/checksum failure hoặc missing key type.

Một kế hoạch rotation an toàn:

1. Inventory: SPN, account owner, hiện trạng KVNO/enctypes trên KDC và keytab của từng instance.
2. Chuẩn bị keytab mới qua IAM, phân phối bằng secret store, kiểm thử trong môi trường tích hợp.
3. Phối hợp mốc chuyển key ở KDC với rollout backend, xem xét tickets cũ và khả năng có nhiều keys/overlap theo policy.
4. Không mặc định thay file trên đĩa làm một JAAS Subject đang sống tự reload; kiểm tra version và khởi động lại/reinitialize có kiểm soát khi cần.
5. Xác minh từng node bằng keytab metadata và Kerberos integration test.
6. Theo dõi validation errors, có rollback plan được duyệt, loại bỏ keytab cũ khi an toàn.
7. Khi nghi keytab bị lộ, coi đó là sự cố credential; ưu tiên rotate/revoke theo chính sách thay vì chỉ xóa một file.

**Enctype:** Dùng bộ mã hóa hiện đại theo chính sách KDC/client/JDK, ưu tiên AES khi tương thích. Đừng mở RC4/DES legacy hoặc tắt Kerberos encryption checks chỉ để chữa lỗi keytab sai.

## 12. Multi-instance, HTTPS reverse proxy và channel binding

### Nhiều pods cùng service hostname

Nếu browser đến một public FQDN qua load balancer, tất cả replicas thực sự nhận SPNEGO token phải có acceptor credentials cho **cùng HTTP SPN** hoặc chiến lược routing được quản trị. Nếu pod A có keytab mới còn pod B có keytab cũ, cùng một user có thể đăng nhập thất bại ngẫu nhiên.

Phân phối keytab qua secret mounts an toàn; không để secret trên public image layers. Multi-node application còn cần SecurityContext/HttpSession share hoặc chiến lược session nhất quán nếu dùng stateful authentication.

### HTTPS termination và Extended Protection

Khi TLS kết thúc tại reverse proxy, service principal mà browser yêu cầu có thể vẫn là public hostname. Một số môi trường Windows có **Extended Protection for Authentication / channel binding (CBT)**; nếu TLS bindings của client, proxy và JDK acceptor không phù hợp có thể gặp **channel binding mismatch**.

Không giải quyết bằng cách vô hiệu hóa tùy tiện Extended Protection hoặc giảm mức an toàn của Windows/AD. Phải xem lại TLS termination, proxy design, CBT capability của client/JDK và yêu cầu bảo mật tổ chức.

### Browser fallback NTLM

Header **Negotiate** không bảo đảm bên trong chắc chắn là Kerberos AP-REQ; client có thể thử NTLM trong một số môi trường Windows. **SunJaasKerberosTicketValidator không tự trở thành NTLM provider**. Nếu chỉ chấp nhận Kerberos, fallback không phù hợp phải bị từ chối; nếu doanh nghiệp cần cơ chế dự phòng, thiết kế authentication provider/entrypoint và trust riêng có kiểm soát.

## 13. Sự cố điển hình và cách phân loại

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Browser 401 mãi, không thấy Authorization: Negotiate | Chưa bật integrated auth, site không trusted, client thiếu Kerberos credentials | Kiểm tra browser GPO/zone, TGT và HTTP challenge |
| **KDC_ERR_S_PRINCIPAL_UNKNOWN** | SPN không tồn tại, DNS/realm mapping sai | Kiểm tra setspn -Q, hostname và realm |
| **KRB_AP_ERR_MODIFIED** | Sai service key, duplicate SPN, KVNO cũ hoặc keytab từ account khác | Đối chiếu owner, kvno/enctypes và keytab |
| **Cannot find key of appropriate type** | Ticket yêu cầu enctype không có trong keytab/JDK | Điều tra keytab/KDC encryption policy |
| **KeyTab not found** | Config path sai hoặc volume chưa mount | Kiểm tra file thực trong JVM container |
| **Permission denied reading keytab** | UID/GID/mode không cho đọc | Sửa ACL/secret mount theo least privilege |
| **Clock skew too great** | Client, server, KDC lệch thời gian | Đồng bộ NTP/chrony |
| **GSSException Defective token** | Header malformed, proxy rewrite, cơ chế NTLM không tương thích | Kiểm tra Negotiate forwarding và client mechanism |
| **Channel binding mismatch** | TLS termination/CBT không tương thích | Rà soát architecture và bảo vệ Extended Protection |
| **Sai hostname vì CNAME** | Browser xin ticket cho alias khác keytab | Đặt canonical URL hoặc đăng ký SPN alias |
| Validation thành công nhưng HTTP 403 | Local account/role/tenant bị từ chối | Kiểm tra UserDetailsService và business policy |
| Request đầu thành công, request sau anonymous | SecurityContextRepository/HttpSession không lưu, cookie hoặc cluster | Cấu hình persistence/session đúng |
| Khởi động được nhưng không login được | Chưa có ticket end-to-end; Java bean tồn tại không chứng minh keytab đúng | Test KDC/browser/SPN/keytab và runtime logs |
| Một số pods chạy được, một số fail | Keytab/KVNO/enctype hoặc file permissions không đồng nhất | So sánh từng pod và rollout đồng bộ |
| SPNEGO filter chạy trùng | Filter bean auto-register cộng thêm SecurityFilterChain | Chỉ add filter vào một chain, không @Bean filter |

**Không in raw Authorization: Negotiate token, keytab bytes, Kerberos session keys, mật khẩu, TGT hoặc debug log nhạy cảm**. Sử dụng request correlation ID, error class, SPN và trạng thái đã được giảm thiểu theo privacy policy.

## 14. Kiểm thử tích hợp cần có

| Trường hợp | Kỳ vọng |
| --- | --- |
| 1. Correct SPN + valid keytab + user enabled | Authenticated principal được nhận |
| 2. Ticket hướng đến HTTP/backend, app chỉ chấp nhận HTTP/portal | Deny |
| 3. Keytab không có service principal cấu hình | Validation fail |
| 4. Keytab KVNO không khớp ticket đang phát | Không cho phép ngầm |
| 5. Keytab không có enctype tương thích | Không accept |
| 6. Wrong key bytes dù SPN/KVNO text khớp | Cryptographic validation fail |
| 7. SPN duplicate/sai account owner | KDC/service failure, không bypass |
| 8. User Kerberos ở realm ngoài trust được duyệt | Không gộp user, deny theo policy |
| 9. Service có keytab đúng nhưng user không có local account | Không cấp quyền ứng dụng |
| 10. User disabled trong DB/LDAP | Deny |
| 11. Browser không gửi Negotiate | 401/fallback policy có kiểm soát |
| 12. Client fallback NTLM | Không tự coi là Kerberos đã xác thực |
| 13. Clock skew vượt mức chấp nhận | Fail theo Kerberos time checks |
| 14. Header Negotiate giả/malformed | Deny, không tin username tự khai |
| 15. Reverse proxy strip Authorization | Backend không xác thực, chẩn đoán gateway |
| 16. Channel binding mismatch | Fail; sửa TLS/CBT đúng policy |
| 17. Nhiều pods có keytab versions khác nhau | Detect và fix rollout |
| 18. Keytab rotation + JVM restart | Token mới xác minh được; keys cũ được quản lý |
| 19. Request sau đã authenticated với session cookie | Policy session đúng, không có 401 loop |
| 20. API stateless riêng browser SSO | SecurityFilterChains tách biệt |
| 21. User có cùng local-part ở hai realms | Không auto-link quyền |
| 22. Local role revoked trong lúc session SP còn hoạt động | Authorization phản ánh revoke theo SLA |
| 23. GSS context tùy chọn bị dispose | Không cố sử dụng context đã dispose |
| 24. SPN host mới nhưng keytab chưa cập nhật | Fail an toàn, không fallback sang password admin |
| 25. Keytab bị lộ | Security incident response: revoke/rotate và audit |

**Phân lớp test:**

- **Unit:** kiểm tra service principal string, config mapping, UserDetailsService và authorization policy.
- **Integration với KDC test:** cấp và xác minh ticket thật qua SPNEGO, sai key/realm/KVNO, lifetime và replay behavior.
- **End-to-end với AD/browser:** DNS, GPO/zone, Windows tickets, HTTPS reverse proxy/CBT và multi-node rollout.

Chỉ unit test dùng mock Authentication **không chứng minh** SunJaasKerberosTicketValidator đã cryptographically validate token; kiểm thử tích hợp phải có KDC thật hoặc test KDC tin cậy.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Browser vào portal.example.org nhưng keytab chỉ có HTTP/backend1@REALM; validator chấp nhận được không?  
**Trả lời:** Không mặc định. Browser thường xin ticket cho public SPN của portal. Phải đồng bộ canonical SPN và keytab.

**Câu 2.** Klist cho thấy đúng principal mà vẫn KRB_AP_ERR_MODIFIED, vì sao?  
**Trả lời:** Có thể key bytes/KVNO/enctype khác KDC, duplicate SPN hoặc account owner không đúng. Text giống nhau chưa đủ.

**Câu 3.** Có nên lưu keytab trong JAR/resources không?  
**Trả lời:** Không khuyến nghị. JAAS thường cần path thật và keytab là secret cần quản lý ngoài image/source.

**Câu 4.** Kerberos ticket đã đúng mật mã nhưng UserDetailsService không có user?  
**Trả lời:** Không cấp business access; yêu cầu local identity link hoặc onboarding được phê duyệt.

**Câu 5.** User principal alice@EXAMPLE.ORG có phải service principal không?  
**Trả lời:** Không. Service principal thường là HTTP/FQDN@REALM, keytab là của service account.

**Câu 6.** Keytab bị rotate trên disk, JVM đang chạy có tự nhận key mới ngay không?  
**Trả lời:** Không được giả định. Cần test JAAS/JDK version, quản lý Subject/key cache và reload/restart có kiểm soát.

**Câu 7.** Vì sao không dùng HTTP X-User từ browser làm Kerberos authentication?  
**Trả lời:** Header ấy không chứng minh possession của Kerberos ticket; chỉ nhận identity do GSS/JGSS validator đã xác minh hoặc trusted proxy protocol được bảo vệ riêng.

**Câu 8.** SPNEGO khác CAS Service Ticket ở đâu?  
**Trả lời:** SPNEGO dùng Kerberos service ticket/JAAS acceptor, còn CAS có service ticket opaque và CAS validation endpoint. Không thay một validator cho validator kia.

## 16. Checklist production

- [ ] Service principal **HTTP/FQDN@REALM** phản ánh hostname công khai mà browser truy cập.
- [ ] AD/KDC SPN có đúng owner, không duplicate; realm/DNS mapping tin cậy.
- [ ] Keytab có đúng principal, KVNO, enctype/key bytes; file nằm ngoài JAR/Git.
- [ ] Secret mount bảo mật, read permission tối thiểu, audit và kế hoạch rotation/rollback.
- [ ] Validator gọi **setServicePrincipal** và **setKeyTabLocation** đúng giá trị.
- [ ] Keytab được kiểm tra bằng **klist -k -e**; không dùng -K làm lộ key.
- [ ] Java 17, Kerberos extension 2.2.0, Security 6.5.x/Boot 3.x có dependency tree tương thích.
- [ ] **SpnegoEntryPoint**, **SpnegoAuthenticationProcessingFilter** và **KerberosServiceAuthenticationProvider** nằm trong đúng chain/provider.
- [ ] SPNEGO filter chỉ được đăng ký một lần, không auto-register ngoài Spring Security.
- [ ] Nếu muốn stateful browser, SecurityContextRepository/HttpSession và session fixation policy hoạt động.
- [ ] NTP/clock, KDC reachability, DNS, browser Negotiate settings đã được test end-to-end.
- [ ] HTTPS reverse proxy giữ Authorization Negotiate và phù hợp channel binding policy.
- [ ] Không coi NTLM fallback là Kerberos authentication thành công.
- [ ] User Kerberos principal được ánh xạ sang account/realm/tenant đáng tin, local authorization được áp dụng riêng.
- [ ] Không cấp ROLE_ADMIN chỉ vì có ticket; kiểm tra resources và trạng thái user/DB revoke.
- [ ] Debug JAAS chỉ được bật tạm trong môi trường kiểm thử, tránh lộ secrets/tokens.
- [ ] Test positive, wrong SPN, missing principal, stale KVNO, wrong enctype, key leakage, multi-pod và browser fallback.
- [ ] Có hướng xử lý bảo mật khi keytab bị nghi lộ và khi đổi KDC/service account.

**Kết luận:** SunJaasKerberosTicketValidator là **service-side JAAS/JGSS acceptor** cho Kerberos/SPNEGO. Nó chỉ xác minh đúng khi cấu hình **servicePrincipal phản ánh HTTP SPN của website** và **keytab có secret keys phù hợp với ticket do KDC phát**. Đồng bộ SPN, realm, hostname, DNS, KVNO/enctype, quyền đọc keytab, SecurityFilterChain và local roles là điều kiện để tích hợp Kerberos an toàn; không có một setter nào tự thay thế toàn bộ các bước đó.

## 17. Tài liệu tham khảo

- [Spring Security Kerberos 2.2.0 – Introduction](https://docs.spring.io/spring-security-kerberos/reference/introduction.html): version compatibility với JDK17/Security6.5.1/Framework6.2.8.
- [Spring Security Kerberos 2.2.0 – JavaConfig/SPNEGO](https://docs.spring.io/spring-security-kerberos/reference/ssk.html): cấu hình SunJaasKerberosTicketValidator, provider/filter và SPNEGO.
- [SunJaasKerberosTicketValidator Javadoc](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/authentication/sun/SunJaasKerberosTicketValidator.html): servicePrincipal, keyTabLocation, debug, holdOnToGSSContext và refresh configuration.
- [KerberosServiceAuthenticationProvider Javadoc](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html): validator và UserDetailsService.
- [SpnegoAuthenticationProcessingFilter Javadoc](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html): Negotiate header, AuthenticationManager và SecurityContextRepository.
- [SpnegoEntryPoint Javadoc](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/web/authentication/SpnegoEntryPoint.html): WWW-Authenticate: Negotiate.
- [Maven Central – Kerberos core](https://central.sonatype.com/artifact/org.springframework.security.kerberos/spring-security-kerberos-core/2.2.0) và [web](https://central.sonatype.com/artifact/org.springframework.security.kerberos/spring-security-kerberos-web/2.2.0): dependencies 2.2.0.
- [MIT Kerberos – klist](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/klist.html): đọc principal/KVNO/enctype của keytab.
- [MIT Kerberos – krb5.conf](https://web.mit.edu/kerberos/krb5-latest/doc/admin/conf_files/krb5_conf.html): realm/KDC/domain mapping.
- [Microsoft – Service Principal Names](https://learn.microsoft.com/en-us/windows/win32/ad/service-principal-names): SPN mapping.
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): xác thực và trust boundaries.
