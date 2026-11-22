# Kerberos, SPNEGO và các dependency, điều kiện triển khai riêng trong Spring Security

## 1. Mục tiêu và bối cảnh liên kết danh tính

Trong môi trường doanh nghiệp dùng Active Directory (AD) hoặc một Kerberos realm, người dùng thường đã đăng nhập máy tính và sở hữu Kerberos Ticket Granting Ticket (TGT). Khi truy cập một trang nội bộ, trình duyệt có thể tự thương lượng bằng **HTTP Negotiate/SPNEGO** để lấy service ticket cho ứng dụng. Ứng dụng Spring Security dùng ticket để xác thực danh tính rồi ánh xạ principal đó vào **tài khoản và quyền nội bộ**. Người dùng không cần nhập lại mật khẩu tại ứng dụng nếu toàn bộ điều kiện triển khai phù hợp.

Bài này giải thích đầy đủ **Kerberos/SPNEGO là gì, dependency nào thực sự cần và các yêu cầu hạ tầng đặc biệt để chạy được**, trong ngữ cảnh **liên kết danh tính**. Sau bài học, bạn có thể:

1. Phân biệt Kerberos, GSS-API, SPNEGO, HTTP Negotiate, Kerberos principal và Spring Security `Authentication`.
2. Mô tả vai trò của realm/KDC, DNS, SPN, keytab, ticket, thời gian hệ thống và browser policy.
3. Chọn đúng module Spring Security Kerberos theo nhánh Spring Security 6.x hoặc 7.x, tránh nhầm group ID và thư viện server/client.
4. Cấu hình một ví dụ Spring Boot Servlet nhận Kerberos service ticket và ánh xạ principal thành `UserDetails`/authorities.
5. Chẩn đoán lỗi 401, ticket không được gửi, `KRB_AP_ERR_MODIFIED`, sai SPN, KVNO/keytab, DNS, clock skew hoặc proxy.
6. Phân biệt đăng nhập SSO bằng Kerberos với delegation khi backend gọi hệ thống khác thay mặt người dùng.

**Giới hạn quan trọng:** ví dụ Java có thể được biên dịch trong môi trường có dependencies, nhưng **không thể kiểm chứng một phiên Kerberos thật chỉ bằng mã Java**. Bài thực hành cần realm/KDC hoặc AD, service principal, keytab, trình duyệt/client đã có vé Kerberos và các thiết lập mạng tương ứng. Mã nguồn không tự tạo ra những thành phần này.

## 2. Các khái niệm phải tách biệt

| Khái niệm | Ý nghĩa | Vai trò khi user truy cập Spring |
| --- | --- | --- |
| **Kerberos V5** | Giao thức xác thực dựa trên vé (ticket) và khóa mật mã chia sẻ với KDC | Bảo vệ danh tính của client và dịch vụ; không truyền mật khẩu người dùng trong HTTP request |
| **Realm** | Miền định danh Kerberos, ví dụ `EXAMPLE.COM`; thường liên quan AD domain nhưng không mặc nhiên đồng nhất mọi cấu hình DNS | Đặt namespace cho user/service principal và chính sách tin cậy |
| **KDC** | Key Distribution Center gồm dịch vụ xác thực và phát vé; trong AD thường do domain controller cung cấp | Cấp TGT và service ticket |
| **TGT** | Ticket Granting Ticket sau khi user đăng nhập Kerberos | Client dùng để xin service ticket mà không nhập lại password |
| **Service ticket** | Vé dành cho đúng service principal cụ thể | Browser gửi trong SPNEGO token đến ứng dụng |
| **SPN** | Service Principal Name, ví dụ `HTTP/app.example.com@EXAMPLE.COM` | KDC chọn khóa mã hóa vé đúng dịch vụ |
| **Keytab** | Tệp chứa khóa dài hạn của service principal (thường nhiều KVNO/enctype) | Server dùng để xác minh/giải mã ticket; phải được bảo vệ như bí mật |
| **GSS-API/JGSS** | API bảo mật trừu tượng; Java hỗ trợ qua JGSS/JAAS | Cài đặt cơ chế xác minh ticket trong JVM |
| **SPNEGO** | Giao thức thương lượng cơ chế bảo mật, thường mang Kerberos qua HTTP Negotiate | Kết nối browser với ứng dụng web đã tích hợp Kerberos |
| **Spring Security Authentication** | Principal + authorities + authenticated flag trong `SecurityContext` | Đầu vào để app kiểm tra quyền; không phải chính vé Kerberos |

Một **user principal** có thể là `alice@EXAMPLE.COM`; một **service principal** có thể là `HTTP/app.example.com@EXAMPLE.COM`. Chúng có mục đích khác nhau: user chứng minh danh tính, còn service principal đại diện cho endpoint ứng dụng có khóa tương ứng trong keytab.

**SPNEGO không đồng nghĩa Kerberos.** `Negotiate` là cơ chế thương lượng: tùy client/môi trường, một số client có thể đề xuất NTLM. Spring Security Kerberos với Kerberos ticket validator không tự trở thành một NTLM server. Muốn chấp nhận cơ chế nào, phải kiểm thử rõ và từ chối những cơ chế không nằm trong chính sách.

## 3. Một lần truy cập diễn ra như thế nào?

```text
Nhân viên đăng nhập workstation                     KDC / Active Directory
              |                                               |
              |--- Kerberos logon / xin TGT ------------------>|
              |<-- Ticket Granting Ticket --------------------|
              |
              |   browser mở https://app.example.com/private/me
              v
         Browser / Client                               Spring Boot app
              |                                               |
              |--- GET /private/me --------------------------->|
              |<-- 401 WWW-Authenticate: Negotiate -----------|
              |                                               |
              |--- TGS-REQ cho HTTP/app.example.com ---------> KDC
              |<-- Service ticket cho SPN trên --------------- KDC
              |                                               |
              |--- Authorization: Negotiate <SPNEGO token> --->|
              |                                               |
              |                         SpnegoAuthenticationProcessingFilter
              |                                  |
              |                         KerberosServiceAuthenticationProvider
              |                                  |
              |                  SunJaasKerberosTicketValidator + service keytab
              |                                  |
              |                  principal: alice@EXAMPLE.COM
              |                                  |
              |                  UserDetailsService / account link
              |                                  |
              |                  Authentication + ROLE_USER
              |                                  |
              |                  SecurityContext + authorization
              |<-- 200 nội dung được phép --------------------|
```

Chuỗi trên là luồng khái niệm; với browser đã có ticket cache và hỗ trợ proactive Negotiate, số vòng HTTP thực tế có thể khác. Phản hồi 401 ở bước đầu **là challenge hợp lệ**, không nhất thiết là lỗi.

### Bước 1: HTTP 401 khởi tạo HTTP Negotiate

Ứng dụng trả:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
```

Header này báo browser có thể dùng cơ chế Negotiate nếu được hỗ trợ và cho phép theo chính sách máy/trình duyệt.

### Bước 2: Browser xin service ticket

Browser xây dựng service principal theo **tên host đích** (thường `HTTP/<FQDN>`), rồi tương tác với KDC để có service ticket. Ví dụ:

```text
HTTP/app.example.com@EXAMPLE.COM
```

KDC mã hóa thông tin dành cho dịch vụ bằng khóa của service account. Keytab trên server cần chứa khóa tương thích với ticket đó.

**Điểm dễ sai:** nếu browser vào `https://app-alias.example.com`, ticket có thể dành cho `HTTP/app-alias.example.com`. Keytab và SPN của `HTTP/app.example.com` không đương nhiên dùng được. Không nên “sửa” bằng cách đổi một header trong Spring; phải thiết kế tên public, DNS, SPN và keytab cùng nhau.

### Bước 3: Browser gửi SPNEGO token

Khi thương lượng, request có dạng:

```http
GET /private/me HTTP/1.1
Host: app.example.com
Authorization: Negotiate <base64-encoded-SPNEGO-token>
```

Ví dụ chỉ mô tả cấu trúc: chuỗi `<base64-encoded-SPNEGO-token>` không phải một ticket chạy được. Token thực có thể chứa dữ liệu nhạy cảm; không copy vào log hoặc ticket hỗ trợ kỹ thuật.

### Bước 4: Spring xác minh ticket rồi xây dựng Authentication

Trong Servlet Spring Security:

1. `SpnegoAuthenticationProcessingFilter` tìm `Authorization: Negotiate ...`, trích xuất token và tạo `KerberosServiceRequestToken`.
2. Filter gọi `AuthenticationManager`, thường là `ProviderManager` có `KerberosServiceAuthenticationProvider`.
3. Provider chuyển ticket cho `KerberosTicketValidator` (trên OpenJDK/Oracle JDK thường là `SunJaasKerberosTicketValidator`).
4. Validator dùng JGSS/JAAS và service principal/keytab để xác minh ticket, nhận principal đã chứng thực.
5. Provider dùng `UserDetailsService` để tìm user, lấy account status và authorities. Kerberos **chủ yếu xác lập ai là user**, không tự quyết định user được quyền sửa mọi dữ liệu.
6. Nếu thành công, Spring có `Authentication`; `SecurityContext` được thiết lập cho request và có thể được lưu qua `SecurityContextRepository` nếu cấu hình rõ ràng.
7. `AuthorizationFilter` đánh giá `authenticated()`, `hasRole(...)` và các policy khác.

**Không làm tắt bước xác minh:** lấy base64 token, `decode` rồi tự tách “username” hoặc tin header `X-User` không có nghĩa đã có xác thực Kerberos.

## 4. Điều kiện triển khai riêng: checklist bắt buộc

### 4.1. KDC / Active Directory và miền tin cậy

Cần có Kerberos realm hoạt động (AD DS hoặc MIT/Heimdal KDC) và tài khoản user được phép xin ticket. Thiết lập DNS/KDC discovery hoặc `krb5.conf`/`krb5.ini`, đường mạng đến KDC và chính sách liên realm nếu có nhiều domain.

Các port thường liên quan: DNS 53, Kerberos 88 TCP/UDP, kpasswd 464 khi quản lý thay đổi mật khẩu; LDAP/LDAPS 389/636 **chỉ khi ứng dụng hoặc hạ tầng thực sự tra cứu directory**. Không mở toàn bộ port “cho chắc”; xác nhận đường client → KDC và, khi cần, server → KDC/directory theo sơ đồ triển khai.

### 4.2. DNS, tên public và SPN duy nhất

Với URL `https://app.example.com`, service principal thường là:

```text
HTTP/app.example.com@EXAMPLE.COM
```

Điều kiện:

- Tên máy mà browser dùng phải được DNS phân giải đúng và nhất quán; tránh test bằng IP, `localhost` hoặc CNAME tùy tiện khi SPN chưa được chuẩn bị.
- SPN cần được gán cho **đúng service account**, không có bản ghi trùng trên tài khoản khác. Trong AD có thể tra cứu bằng `setspn -Q HTTP/app.example.com` và kiểm tra trùng bằng `setspn -X` (cần quyền phù hợp).
- Nếu chạy sau load balancer/reverse proxy, **SPN tương ứng với URL nhìn thấy bởi browser**, không nhất thiết là hostname nội bộ của pod. Chọn nơi kết thúc SPNEGO (proxy hay Java backend) và đảm bảo service ticket được xử lý tại đúng nơi.
- Khi đổi hostname, alias hoặc service account, phải cập nhật SPN, keytab và cấu hình browser/ứng dụng đồng bộ.

### 4.3. Service account và keytab

Quản trị Kerberos/AD cấp một service account, đăng ký SPN và xuất keytab có khóa/kvno/enctype phù hợp. Ví dụ keytab lưu bên ngoài artifact tại `/run/secrets/http.keytab`.

**Keytab chứa bí mật mật mã.** Không commit vào Git, đóng gói trong JAR, đưa vào Docker image layer, đính kèm email/log hoặc sao chép cho client. Mount dưới dạng file chỉ đọc với ACL chặt chẽ và quyền truy cập chỉ dành cho tiến trình ứng dụng. Kiểm soát cả bản sao, backup, secret store và cơ chế luân chuyển key.

Khi thay đổi mật khẩu service account, key version number (KVNO) thay đổi, keytab cũ có thể không còn xác minh được service ticket. Lập kế hoạch cập nhật keytab cho **mọi instance** và giám sát lỗi ngay sau rotation.

### 4.4. Đồng bộ thời gian

Kerberos có cơ chế kiểm tra độ lệch thời gian để chống replay. Máy client, KDC và server phải có NTP/đồng bộ thời gian tin cậy. Mức clock skew cho phép phụ thuộc chính sách realm, không nên giả định “luôn đúng 5 phút”. Đừng tăng skew tùy tiện để che vấn đề cấu hình thời gian.

### 4.5. Browser/client được phép Negotiate

Không phải mọi thiết bị tự động gửi Kerberos ticket:

- Client thường cần đăng nhập domain hoặc có TGT trong ticket cache.
- Browser cần hỗ trợ HTTP Negotiate và xem URL đích là trusted/intranet theo chính sách tương ứng. Với Firefox có các tham số như `network.negotiate-auth.trusted-uris`; Edge/Chrome trong môi trường doanh nghiệp có các policy allowlist cho authentication.
- Khi dùng client ngoài domain, trình duyệt riêng tư, mobile, proxy Internet, jump host hoặc VPN, cần kiểm tra khả năng lấy vé và chính sách SSO. Có thể phải dùng đăng nhập khác như OIDC với IdP hoặc form fallback được bảo vệ.
- `curl --negotiate -u :` chỉ hoạt động nếu bản `curl` được build hỗ trợ GSSAPI/SSPI và client có Kerberos credentials hợp lệ.

### 4.6. TLS, reverse proxy và nhiều instance

SPNEGO bảo vệ một phần của giao thức xác thực nhưng **không thay HTTPS**. Triển khai HTTPS, bảo vệ session cookie, headers và đường chuyển tiếp. Nếu TLS termination đặt ở reverse proxy, xác định proxy chuyển tiếp nguyên vẹn `Authorization: Negotiate` và không thay nó bằng header không được xác thực.

Với cluster:

- Nếu Java backend chấp nhận ticket, các node phải có khả năng xác minh ticket dành cho **cùng SPN**, thường là được cấp quyền sử dụng đúng keytab/service account (bảo vệ riêng từng node).
- Nếu proxy đã hoàn thành Kerberos rồi đưa một identity header đến backend, đó là mô hình **pre-auth dựa trên proxy**. Backend phải chỉ nhận request từ proxy tin cậy; không giả vờ nó đang tự kiểm chứng SPNEGO.
- Nếu ứng dụng lưu Spring session, cần quản lý affinity hoặc shared session store, session invalidation, expiry và cập nhật quyền. Việc xác thực Kerberos một request không tự làm session application hết hạn đồng thời với TGT.

## 5. Dependency chính xác theo hệ phiên bản Spring

**Điểm khác biệt dễ gây lỗi build:** Spring Security Kerberos là module chuyên dụng, không tự xuất hiện chỉ vì đã thêm `spring-boot-starter-security`. Hệ group ID thay đổi giữa Spring Security 6 và 7.

### Spring Boot 3.5 / Spring Security 6.5 (ví dụ chính của bài)

Maven:

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
```

Gradle Groovy:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security.kerberos:spring-security-kerberos-core:2.2.0'
    implementation 'org.springframework.security.kerberos:spring-security-kerberos-web:2.2.0'
}
```

Spring Security Kerberos **2.2.0** được dự án Spring ghi là build/test với **Java 17, Spring Security 6.5.1 và Spring Framework 6.2.8**. Đối với project Boot 3.5.x, cần dùng các bản patch tương thích và kiểm tra dependency tree thực tế. Không trộn ngẫu nhiên thư viện Jakarta/Servlet và Spring Security khác major.

### Spring Security 7.x / Spring Boot 4.x

Tài liệu Spring Security 7.1.x dùng tọa độ:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-kerberos-core</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-kerberos-web</artifactId>
</dependency>
```

Gradle:

```groovy
dependencies {
    implementation 'org.springframework.security:spring-security-kerberos-core'
    implementation 'org.springframework.security:spring-security-kerberos-web'
}
```

Khi sử dụng BOM của phiên bản Spring Boot 4/Spring Security 7 phù hợp, để BOM quản lý version. **Không sao chép group ID của nhánh 6.x vào ví dụ 7.x** và không tự thêm `2.2.0` vào artifact của group mới. Tài liệu Spring Security 7.1.2 nêu JDK 17, Spring Security 7.1.2 và Spring Framework 7.0.10 cho Kerberos trong nhánh này.

### Các module khác khi thật sự cần

- `spring-security-kerberos-client`: dành cho **ứng dụng Java khởi tạo request tới dịch vụ Kerberos khác**; một web server chỉ cần nhận ticket thông qua SPNEGO thường **không cần** module này.
- `spring-security-ldap` / Spring LDAP: chỉ khi nạp user, group, authorities hoặc dữ liệu directory từ AD/LDAP; xác minh ticket Kerberos tự nó **không đòi LDAP**.
- `spring-security-kerberos-test` hoặc công cụ MiniKdc: phục vụ test tích hợp có KDC; test Java thông thường/MockMvc `@WithMockUser` không kiểm chứng ticket.
- `spring-security-test`: test authorization trong Spring. Không thay thế server ticket validation.
- JDK 17+ với JGSS/JAAS. `javax.security.auth` trong JDK là tên package chuẩn và khác với việc ứng dụng Servlet hiện đại dùng `jakarta.servlet`.
- Với WebFlux, ví dụ `SpnegoAuthenticationProcessingFilter` thuộc **Servlet Filter API**, không phải `WebFilter` reactive có thể thêm trực tiếp vào `SecurityWebFilterChain`.

Để kiểm tra dependency đã thực sự được giải quyết:

```bash
mvn dependency:tree -Dincludes=org.springframework.security.kerberos
```

Dùng bản Maven và toolchain Java phù hợp project; pin dependencies từ một BOM nhất quán và chạy kiểm tra lỗ hổng theo chính sách tổ chức.

## 6. Cấu hình Spring Boot Servlet: một ứng dụng nhận SPNEGO

Ví dụ dưới đây dùng **Java 17, Spring Boot 3.5.x, Spring Security 6.5.x và Spring Security Kerberos 2.2.0**. Để tái lập build, `pom.xml` dùng Spring Boot `3.5.16`. Ví dụ phục vụ **HTTP service ticket do KDC thật phát hành**. Nó không tự tạo KDC, không tự đăng ký SPN và không thể login thành công nếu keytab chưa được provisioning.

### 6.1. Cấu trúc dự án

```text
kerberos-spnego-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/kerberos/KerberosDemoApplication.java
        └── resources/application.yml
```

Tạo `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>kerberos-spnego-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/resources/application.yml`:

```yaml
app:
  kerberos:
    service-principal: "${KRB5_SERVICE_PRINCIPAL}"
    keytab-path: "${KRB5_KEYTAB_FILE}"

server:
  port: 8080
```

Hai biến môi trường là **đầu vào từ hạ tầng**. Ví dụ thực tế:

```text
KRB5_SERVICE_PRINCIPAL=HTTP/app.example.com@EXAMPLE.COM
KRB5_KEYTAB_FILE=/run/secrets/http.keytab
```

Không để keytab trong `src/main/resources` hoặc trong JAR. Phải cấp cả SPN và keytab thật trước khi chạy một phiên login.

### 6.2. Cấu hình Java 17

Tạo `src/main/java/demo/kerberos/KerberosDemoApplication.java`:

```java
package demo.kerberos;

import java.security.Principal;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class KerberosDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(KerberosDemoApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice@EXAMPLE.COM")
                .password("{noop}not-used-by-spnego")
                .roles("USER")
                .build()
        );
    }

    @Bean
    SunJaasKerberosTicketValidator ticketValidator(
            @Value("${app.kerberos.service-principal}") String spn,
            @Value("${app.kerberos.keytab-path}") String keytabPath) {
        var validator = new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(spn);
        validator.setKeyTabLocation(new FileSystemResource(keytabPath));
        validator.setDebug(false);
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService users) {
        var provider = new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);
        return provider;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider provider) throws Exception {

        // Cùng một repository để load và save SecurityContext.
        var contexts = new HttpSessionSecurityContextRepository();
        var entryPoint = new SpnegoEntryPoint();

        // Khai báo cục bộ để Boot không đăng ký filter hai lần.
        var spnego = new SpnegoAuthenticationProcessingFilter();
        spnego.setAuthenticationManager(new ProviderManager(provider));
        spnego.setSecurityContextRepository(contexts);
        spnego.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());
        spnego.setFailureHandler((request, response, failure) ->
            entryPoint.commence(request, response, failure));

        return http
            .securityContext(context ->
                context.securityContextRepository(contexts))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/private/**").authenticated()
                .anyRequest().denyAll())
            .exceptionHandling(errors ->
                errors.authenticationEntryPoint(entryPoint))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .addFilterBefore(spnego, BasicAuthenticationFilter.class)
            .build();
    }
}

@RestController
class DemoController {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/private/me")
    String currentUser(Principal principal) {
        return principal.getName();
    }
}
```

**Từng thành phần trong mã làm gì?**

- `SunJaasKerberosTicketValidator` xác minh service ticket bằng SPN và keytab của service account.
- `KerberosServiceAuthenticationProvider` nhận principal Kerberos sau xác minh và tra cứu `UserDetailsService`. Ví dụ nhận **chỉ** user `alice@EXAMPLE.COM`, quyền `ROLE_USER`.
- `SpnegoEntryPoint` trả 401 và header `WWW-Authenticate: Negotiate`, yêu cầu browser bắt đầu/tiếp tục thương lượng.
- `SpnegoAuthenticationProcessingFilter` lấy HTTP Negotiate token và gọi provider. Nó được đặt trước `BasicAuthenticationFilter` trong chain; chỉ dùng lớp `BasicAuthenticationFilter` như **mốc thứ tự**, còn HTTP Basic trong ví dụ đã bị tắt.
- `HttpSessionSecurityContextRepository` được cấu hình **cả phía filter ghi lẫn phía Spring đọc**; từ request sau, session application có thể khôi phục Authentication. Đây là lựa chọn **stateful**, khác với mỗi request phải tự gửi SPNEGO ticket.
- `ChangeSessionIdAuthenticationStrategy` đưa bước bảo vệ session fixation vào lần xác thực thành công theo mẫu minh họa. Sản phẩm thật vẫn cần thiết kế logout, hạn sử dụng session và refresh authority.
- Không khai báo `SpnegoAuthenticationProcessingFilter` thành `@Bean` riêng rồi đồng thời thêm nó vào `SecurityFilterChain`: Spring Boot có thể auto-register Servlet Filter đó ngoài `FilterChainProxy`, gây chạy trùng.
- `password("{noop}not-used-by-spnego")` là dữ liệu **mẫu** vì interface `UserDetails` có password field; luồng SPNEGO không so sánh mật khẩu. Không dùng `{noop}` cho login password thực.
- `/private/me` lấy Spring Security principal đã xác thực. Dữ liệu user phải được **map chính xác**; nếu KDC trả tên khác casing/realm, local lookup phải có chính sách canonicalization tin cậy.

**Lưu ý:** vì mã hướng tới domain thật, việc build không có nghĩa kiểm thử được Kerberos. Cần SPN, keytab và ticket hợp lệ trước khi nhận 200 từ endpoint bảo vệ. Khi chỉ học cơ chế authentication, không nên tự tạo một `KerberosServiceRequestToken` giả rồi cố bypass validator để “test pass”.

## 7. Quy trình dựng môi trường và chạy thử

Một môi trường tối thiểu gồm AD/KDC, user `alice@EXAMPLE.COM`, service account cho `HTTP/app.example.com@EXAMPLE.COM`, keytab tương ứng, hostname công khai `app.example.com`, một client có TGT và máy Java chạy được ứng dụng.

### 7.1. Phần việc của quản trị Kerberos/AD

- Đăng ký SPN duy nhất trên service account do ứng dụng sử dụng.
- Xuất keytab chính xác cho service account (enctype, key version và principal), chuyển bằng kênh bảo mật vào secret mount của ứng dụng.
- Cấp quyền read file keytab cho tiến trình server, hạn chế user khác.
- Bảo đảm clock, DNS, KDC reachability, chính sách realm/trust và chính sách duyệt dịch vụ.
- Trong AD, tránh tạo SPN trùng, dùng AES/crypto suite phù hợp chính sách và thay khóa theo quy trình.

Các lệnh tham khảo để **xác minh cấu hình**:

```bash
# Chạy trên máy có quyền và tool AD phù hợp:
setspn -Q HTTP/app.example.com
setspn -X

# Linux với MIT Kerberos client tools:
klist
klist -kte /run/secrets/http.keytab
```

Lệnh `klist -kte` đọc **metadata** keytab (KVNO, principal, enctype), không in khóa; vẫn nên hạn chế chia sẻ output nội bộ vì có thông tin cấu hình nhạy cảm. `setspn` là công cụ Windows/AD, không có sẵn trên mọi Linux host.

Có thể dùng `kvno HTTP/app.example.com@EXAMPLE.COM` từ **client đã có TGT** để xin service ticket và kiểm tra SPN/KDC path. Nếu có hostname canonicalization khác, trước hết đối chiếu principal thực mà browser đang yêu cầu.

### 7.2. Chạy ứng dụng

Trên máy/host cài Java 17+ và Maven:

```bash
export KRB5_SERVICE_PRINCIPAL='HTTP/app.example.com@EXAMPLE.COM'
export KRB5_KEYTAB_FILE='/run/secrets/http.keytab'

mvn -DskipTests package
java -Djava.security.krb5.conf=/etc/krb5.conf \
     -jar target/kerberos-spnego-demo-1.0.0.jar
```

Đường `/etc/krb5.conf` chỉ là ví dụ Linux; trong AD domain có thể dùng realm discovery/Java native config tùy môi trường. Nếu app nghe HTTP tại 8080 sau ingress HTTPS, cần routing bảo vệ và chuyển `Authorization` header phù hợp. Tên client dùng khi truy cập phải là hostname đã đăng ký SPN.

### 7.3. Test negotiation, không giả lập ticket

Trên client có TGT hợp lệ:

```bash
# Xem ticket cache:
klist

# Để thấy 401 challenge khi chưa gửi vé:
curl -i https://app.example.com/private/me

# Nếu curl hỗ trợ GSSAPI/SSPI và đã có credentials:
curl --negotiate -u : -i https://app.example.com/private/me
```

Kỳ vọng:

- Request đầu chưa xác thực có thể nhận `401` với `WWW-Authenticate: Negotiate`.
- Với client có service ticket hợp lệ, SPN/keytab khớp và user được map nội bộ, response nhận `200`; body theo demo là `alice@EXAMPLE.COM` **nếu user thực đúng là alice**.
- User có ticket Kerberos hợp lệ nhưng không có bản ghi trong `UserDetailsService` có thể bị từ chối; kết quả 401/403 còn phụ thuộc failure handler/authorization. Đừng tự chuyển mọi user không có trong local store thành mặc định `ROLE_USER`.
- Nếu browser tự chọn NTLM thay vì Kerberos, kết quả có thể không xác thực được với Kerberos validator.

Đối với test tự động, dùng thư viện MiniKdc/test harness để cấp service ticket thật trong pipeline cách ly, hoặc integration test trên một realm dùng riêng. `MockMvc.with(user(...))` hoặc `@WithMockUser` chỉ kiểm tra quyền và controller **sau khi đã có Authentication**, không chứng minh SPNEGO/JAAS/keytab hoạt động.

## 8. Liên kết Kerberos principal với danh tính và quyền nội bộ

Kerberos xác minh một principal như `alice@EXAMPLE.COM`. Ứng dụng thường cần ánh xạ nó vào tài khoản nội bộ có ID bất biến, tenant, role và trạng thái. Một chiến lược đúng là:

```text
Verified Kerberos principal
    "alice@EXAMPLE.COM"
                 |
                 v
KerberosServiceAuthenticationProvider
                 |
                 v
UserDetailsService / identity mapping
    (realm, principal) -> localUserId
                 |
                 v
account status + organization membership
                 |
                 v
ROLE_USER / ROLE_EDITOR / access policies
                 |
                 v
Spring Security Authentication
                 |
                 v
AuthorizationFilter / service policy
```

**Vì sao phải gồm realm?** `alice@EXAMPLE.COM` và `alice@PARTNER.COM` có thể là hai người khác nhau. Không strip `@REALM` bừa bãi rồi coi mọi user name trùng là cùng tài khoản.

**Vì sao không tin mọi principal có vé?** Một vé hợp lệ chỉ cho biết principal được KDC xác minh với key đúng; user có thể chưa được cấp quyền sử dụng ứng dụng. `UserDetailsService` và authorization phải kiểm tra trạng thái account, membership và business policy.

**Tại sao cần LDAP/AD đôi khi?** LDAP thường được dùng để lấy display name, thông tin phòng ban/group và mapping role. Nó không thay cho quá trình xác minh service ticket. Có thể dùng `LdapUserDetailsService` hoặc `ActiveDirectoryLdapAuthenticationProvider` theo kiến trúc, nhưng **provider kiểm tra mật khẩu qua LDAP là luồng khác** với provider kiểm tra Kerberos service ticket.

Một thiết kế database nội bộ minh họa:

```sql
CREATE TABLE local_user (
    id UUID PRIMARY KEY,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE kerberos_identity (
    realm VARCHAR(255) NOT NULL,
    principal VARCHAR(512) NOT NULL,
    local_user_id UUID NOT NULL REFERENCES local_user(id),
    PRIMARY KEY (realm, principal)
);
```

Đây chỉ là schema ý tưởng: ứng dụng cần quy tắc canonicalization, case sensitivity, rename/upn changes, migration, uniqueness, transaction và deprovisioning. Không tự động link account dựa trên email ngẫu nhiên hoặc local-part username.

## 9. Authentication khác với Kerberos Delegation

Một ứng dụng Java **chấp nhận** ticket của browser là **service acceptor**. Nếu nó gọi một dịch vụ khác (LDAP, SQL Server, HTTP service B) nhân danh user, đó là câu chuyện khác:

- Nó cần credentials/ticket có thể sử dụng cho request đi ra; xác thực thành công ở service A không mặc nhiên có quyền đại diện user tới service B.
- Mô hình **Kerberos Constrained Delegation (KCD)** hoặc **resource-based KCD** trong AD có điều kiện cấu hình, domain trust, SPN/service account và policy riêng.
- Java/JGSS có thể cần giữ GSS context/Subject theo API cụ thể; client adapter như `KerberosRestTemplate` chỉ có ý nghĩa khi ứng dụng cần tạo request đi ra.
- Trường hợp Microsoft Entra Application Proxy dùng KCD: connector có thể thực hiện delegation tới backend sau khi xác thực ngoài tại Entra. Phải phân biệt nơi xác thực user ngoài, nơi lấy service ticket và nơi backend xác minh ticket.

**Không coi một header principal, vé acceptor, hoặc `SecurityContext.getAuthentication()` là vé delegation hợp lệ.** Ứng dụng phải áp dụng cơ chế delegation được quản trị viên phê duyệt với phạm vi dịch vụ đích cụ thể.

## 10. Các lỗi đặc trưng và quy trình chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Chỉ thấy 401, browser không gửi `Authorization: Negotiate` | Browser không tin URL, client chưa có TGT, policy không cho Kerberos, hoặc proxy gỡ header | Kiểm tra browser policy, ticket cache, request/response headers |
| `401 Negotiate` lặp lại | Service ticket không thể xác minh, browser chọn cơ chế khác, SPN sai | Kiểm tra GSS/Kerberos logs có lọc dữ liệu nhạy cảm, SPN, keytab và cơ chế |
| `KRB_AP_ERR_MODIFIED` | Ticket được mã hóa cho service/key khác; SPN trùng/sai account, keytab không khớp | `setspn -Q/-X`, KVNO, principal/enctype keytab |
| `KRB_AP_ERR_SKEW` hoặc clock skew | Đồng hồ client/KDC/server lệch đáng kể | Kiểm tra NTP/time sync và realm policy |
| “Server not found in Kerberos database” | Service principal/realm không tồn tại hoặc DNS canonicalization khác | Kiểm tra URL, DNS, SPN và realm |
| “No valid credentials provided” ở browser/curl | Không có TGT, ticket cache sai hoặc JGSS không tìm thấy credential | Kiểm tra `klist`, `kinit`/SSPI và client setup |
| “Checksum failed”, “integrity check failed” | Keytab sai khóa/kvno/enctype hoặc dữ liệu ticket không hợp lệ | Xác minh keytab rotation, KDC/account encryption settings |
| Chạy localhost được nhưng FQDN thất bại | Hostname/SPN hoặc proxy TLS setup không tương ứng | Dùng đúng URL/SPN thực, kiểm tra virtual host |
| Ticket hợp lệ nhưng không có user trong app | `UserDetailsService` thiếu principal hoặc mapping realm/casing sai | Kiểm tra verified principal trước khi liên kết local user |
| Login thành công nhưng HTTP 403 | Spring authorities/role mapping thiếu quyền | Kiểm tra `ROLE_*`, rules và policy ở tầng service |
| Một node cluster chạy được, node khác trả 401 | Keytab/KVNO/config không đồng nhất giữa nodes | So sánh secret deployment và service principal từng node |
| Browser bất ngờ hiện popup password | Negotiate không hoạt động, browser fallback Basic/NTLM hoặc policy intranet sai | Kiểm tra `WWW-Authenticate` và browser/Windows event logs |
| Principal/role còn hiệu lực sau khi user bị vô hiệu | Spring session đã giữ Authentication, cache authority chưa refresh | Chính sách session expiry, logout, re-auth, revocation |
| Debug log chứa token/keytab thông tin nhạy cảm | Bật JAAS/GSS debug ở production | Tắt debug, phân loại và xóa log nhạy cảm theo chính sách |

**Quy trình chẩn đoán theo lớp:**

1. **Client:** browser có gửi Negotiate token thật không? Đã có TGT và URL trusted chưa?
2. **KDC/DNS:** service ticket lấy cho SPN nào? Principal có duy nhất, đúng realm và đúng service account không?
3. **Keytab/JVM:** server có thể đọc keytab không; SPN, enctype, KVNO có khớp; JVM có tìm đúng `krb5.conf` không?
4. **Spring filter/provider:** request đi qua chain và filter đúng thứ tự không; provider có xác minh vé không?
5. **Local mapping:** `UserDetailsService` nhận đúng username canonical và cấp đúng authorities không?
6. **Authorization/session:** `SecurityContext` lưu/đọc đúng, policy app có cho truy cập tài nguyên hay không?

Khi cần debug Java cục bộ, có thể bật tạm:

```bash
java -Djava.security.krb5.conf=/etc/krb5.conf \
     -Dsun.security.krb5.debug=true \
     -Dsun.security.spnego.debug=true \
     -jar target/kerberos-spnego-demo-1.0.0.jar
```

**Không để debug bật mặc định trên production**. Log Kerberos/GSS có thể tiết lộ principal, realm, SPN và thông tin phiên. Hãy bảo vệ trace và tắt ngay sau khi xác minh nguyên nhân.

## 11. Những nhầm lẫn hay gặp

**“Chỉ cần spring-boot-starter-security là tự có Kerberos SSO?”** Không. Cần extension phù hợp phiên bản, cấu hình filter/provider, SPN, keytab, KDC, browser và trust boundary.

**“SPNEGO = LDAP?”** Không. SPNEGO là cơ chế thương lượng xác thực qua HTTP; Kerberos ticket được xác minh bằng khóa dịch vụ. LDAP có thể bổ sung user/group lookup nhưng không tự thay Kerberos.

**“Có vé Kerberos thì tự có quyền admin?”** Không. Vé chứng minh principal, còn authorities phải dựa vào nguồn chính sách được quản lý.

**“Kerberos ticket là JWT?”** Không. Kerberos ticket dùng cơ chế KDC/secret keys, không phải JWT/OIDC ID Token. Nếu một gateway chuyển Kerberos identity thành OIDC token, backend dùng giao thức đã được chuyển đổi theo trust boundary mới.

**“Có thể test bằng cách tự thêm Authorization: Negotiate base64(alice)?”** Không. Đây không phải Kerberos service ticket hợp lệ; base64 chỉ là encoding, không tạo bằng chứng mật mã.

**“SPNEGO đồng nghĩa với việc backend có thể gọi mọi dịch vụ dưới danh nghĩa user?”** Không. Delegation là cấu hình riêng, thường cần KCD, quyền dịch vụ đích và giới hạn bảo mật chặt chẽ.

**“Ticket dùng HTTP service principal nên không cần TLS?”** Sai. Phải bảo vệ cả kênh HTTP, cookie, proxy và các request/response sau login.

## 12. Câu hỏi tự kiểm tra

1. **Trong URL `https://app.example.com`, SPN nào thường được browser dùng?** Thường là `HTTP/app.example.com` trong realm được chọn, nhưng phải đối chiếu DNS/canonicalization và chính sách KDC thực tế.
2. **Ứng dụng lấy khóa xác minh service ticket từ đâu?** Từ keytab hoặc cấu hình acceptor credential được quản trị cho đúng service principal.
3. **Vì sao phải có `UserDetailsService` nếu Kerberos đã xác minh principal?** Để kiểm tra account và cung cấp authorities/chính sách nội bộ.
4. **Dependency Kerberos cho Spring Security 6.5 và 7.1 có cùng group ID không?** Không. 6.x extension 2.2.0 dùng `org.springframework.security.kerberos`, còn 7.x dùng `org.springframework.security` theo BOM của thế hệ mới.
5. **Một `401 WWW-Authenticate: Negotiate` luôn là lỗi không?** Không. Đó là challenge thông thường ở đầu negotiation.
6. **Cần kiểm tra gì nếu service chạy trên một node nhưng lỗi trên node khác?** Keytab, principal, KVNO/enctype, secret mount và config chính xác ở từng node.
7. **Nếu user đổi AD password hoặc bị disable, session Spring hiện tại có tự mất hiệu lực?** Không thể mặc định như vậy; chính sách session, logout và revalidation phải được thiết kế.
8. **Test `@WithMockUser` xác minh được keytab không?** Không. Nó bypass Kerberos ticket validation và chỉ kiểm tra logic đã có Authentication.
9. **Gọi HTTP service thứ hai nhân danh user có tự động không?** Không. Phải cấu hình delegation được phê duyệt và chỉ dành cho các service đích cần thiết.

## 13. Tài liệu chính thức để đối chiếu

- Spring Security Kerberos 2.2.0 / Spring Security 6.5 compatibility: https://docs.spring.io/spring-security-kerberos/reference/introduction.html
- Spring Security Kerberos 7.1.x dependency coordinates: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html
- Spring Security Kerberos – SPNEGO Negotiate và JavaConfig: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- API `SpnegoAuthenticationProcessingFilter`: https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html
- API `KerberosServiceAuthenticationProvider`: https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html
- API `SunJaasKerberosTicketValidator`: https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/authentication/sun/SunJaasKerberosTicketValidator.html
- Java 17 JGSS / HTTP SPNEGO: https://docs.oracle.com/en/java/javase/17/security/part-vi-httpspnego-authentication.html
- Microsoft Entra Kerberos Constrained Delegation: https://learn.microsoft.com/en-us/entra/architecture/auth-kcd
- Maven Central `spring-security-kerberos-web:2.2.0`: https://central.sonatype.com/artifact/org.springframework.security.kerberos/spring-security-kerberos-web/2.2.0
