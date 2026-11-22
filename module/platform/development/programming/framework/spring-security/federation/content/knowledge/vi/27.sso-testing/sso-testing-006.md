# Kiểm thử SPNEGO với KDC thử nghiệm, keytab và tên dịch vụ phù hợp

## 1. Mục tiêu và tiêu chí hoàn thành

Trong HTTP, **SPNEGO (Simple and Protected GSS-API Negotiation Mechanism)** cho phép server gửi challenge **401 WWW-Authenticate: Negotiate**, client tạo **GSS token** và gửi **Authorization: Negotiate**. Với Kerberos, client cần có service ticket do KDC phát cho một principal HTTP đúng. Spring Security Kerberos phải dùng **keytab phía dịch vụ** để xác minh ticket và sau đó mới quyết định local user có quyền hay không.

Bài kiểm thử end-to-end cần bằng chứng cho tất cả các tầng: **KDC test hoạt động → test user có TGT → KDC cấp service ticket cho HTTP/FQDN đúng → keytab trên app có principal/KVNO/enctype phù hợp → DNS/TLS/proxy đúng → client gửi Negotiate → Java GSS acceptor xác minh → local UserDetailsService cho phép đúng principal**.

Một HTTP 200 trên public endpoint, hoặc việc browser không hiện form mật khẩu, **không đủ** chứng minh Kerberos SSO. Có thể đang có cookie session, reverse proxy auth hoặc NTLM fallback. Phải test cả thành công lẫn thất bại an toàn.

Bài thuộc nhóm **Kiểm thử SSO** trong **Spring Security - federation**. Ví dụ sử dụng **Java 17, Spring Boot 3.3.5, Spring Security 6.x, Spring Security Kerberos extension 2.1.0** và MIT Kerberos trên Ubuntu/Debian. Realm, host và địa chỉ example.org là dữ liệu lab giả định, không phải hạ tầng sẵn có.

## 2. Lab topology và các giá trị quan trọng

~~~text
               KDC thử nghiệm
               kdc.lab.example.org
               REALM LAB.EXAMPLE.ORG
                   TCP/UDP 88
                       |
             AS-REQ / TGS-REQ
                       |
           Client alice@LAB.EXAMPLE.ORG
             TGT và HTTP service ticket
                       |
                       | HTTPS GET /private
                       v
               app.lab.example.org
               401 Negotiate challenge
               Authorization: Negotiate token
                       |
              Spring Security acceptor
              SPN HTTP/app.lab.example.org@LAB.EXAMPLE.ORG
              Keytab /etc/security/keytabs/http-app.keytab
                       |
              Verified Kerberos principal
              UserDetailsService và local authorities
                       |
                   200 hoặc 401/403
~~~

| Thành phần | Giá trị của lab | Ràng buộc |
| --- | --- | --- |
| Kerberos realm | **LAB.EXAMPLE.ORG** | KDC database, krb5.conf, principal suffix. |
| KDC FQDN | **kdc.lab.example.org** | DNS, KDC config và port 88. |
| URL public | **https://app.lab.example.org/private** | Tên host, HTTPS certificate, SPN. |
| Service principal | **HTTP/app.lab.example.org@LAB.EXAMPLE.ORG** | KDC principal, keytab, Java validator. |
| Service keytab | **/etc/security/keytabs/http-app.keytab** | OS permissions, KVNO, encryption types. |
| Test user | **alice@LAB.EXAMPLE.ORG** | kinit, client cache, local account. |
| Spring internal listener | **http://app-pod:8080** | Chỉ backend; không phải public HTTP SPN. |

**Service Principal Name (SPN)** gắn với tên mà client dùng để tới dịch vụ. Nếu browser mở portal.lab.example.org nhưng keytab chỉ có HTTP/app.lab.example.org, KDC/client có thể chọn ticket cho hostname khác và Java không accept được. DNS CNAME, reverse DNS, load balancer và hostname canonicalization phải có chính sách nhất quán. Trên Active Directory, một SPN không được gán bừa vào nhiều service accounts.

## 3. Kerberos TGT, service ticket, KVNO và keytab

~~~text
AS exchange:
  alice xác thực với KDC -> TGT krbtgt/LAB.EXAMPLE.ORG

TGS exchange:
  client dùng TGT xin ticket HTTP/app.lab.example.org

HTTP Negotiate:
  server trả 401 WWW-Authenticate: Negotiate
  client gửi Authorization: Negotiate kèm GSS token

Java acceptor:
  dùng keytab của HTTP/app.lab.example.org để kiểm service ticket
  -> xác thực alice@LAB.EXAMPLE.ORG

Local authorization:
  UserDetailsService / IAM -> account active + authorities
~~~

**TGT không phải service ticket**. kinit lấy TGT, còn kvno xin service ticket đúng SPN. **Keytab là secret chứa service key material**, không phải TLS certificate. Nó phải nằm trên app server/secret store được phép, không đưa vào Git, email, chat, CI logs hoặc client.

**KVNO** là key version number. Khi rotate service principal keys, keytab cũ có thể không giải mã được ticket mới. Lệnh **MIT ktadd thường randomize service keys và tăng KVNO** khi xuất keytab; chạy lại ktadd trên principal đang phục vụ mà không rollout keytab mới có thể gây outage.

**Enctype** là kiểu mã hóa của key/ticket; cần tương thích KDC, Java 17 và Kerberos policy. Không bật DES/RC4 yếu để qua test. Keytab secret và HTTPS TLS có chức năng khác nhau, và cả hai đều cần cấu hình đúng.

## 4. Điều kiện an toàn khi thực hành

- Chỉ tạo principals, chạy kdb5_util, kadmin.local và ktadd trên **KDC lab cô lập, được cấp quyền**. Không dùng AD/KDC production.
- Không đưa keytab cho browser hoặc để secret world-readable. App process chỉ được đọc đúng file keytab của service.
- DNS/hosts cho KDC và app phải phân giải đúng trong mạng thử nghiệm; port Kerberos TCP/UDP 88 chỉ mở cho hosts được phép.
- Nếu dùng kadmind trên TCP 749 để remote admin, chỉ mở cho mạng quản trị. Có thể chỉ dùng kadmin.local tại KDC mà không expose admin service.
- Đồng bộ NTP/UTC giữa KDC, client, Spring server. Không tăng clock skew lên nhiều giờ hoặc vô hiệu replay checks.
- HTTPS certificate phải có hostname hợp lệ và được client trust; không dùng curl -k làm kết quả security QA cuối cùng.
- Ghi nhận trace đã redact, không lưu raw Authorization Negotiate token, TGT, service tickets, keytab hoặc password.
- Khi hoàn tất lab, làm sạch test principals/keys/credential caches theo quy trình, không phá tickets của người dùng thật.

## 5. Cài KDC thử nghiệm MIT Kerberos

Các ví dụ sau giả định **KDC mới trên Ubuntu/Debian**. Đường dẫn service/database có thể khác tùy distro và image, nên kiểm package/version trước khi khởi tạo. **Không chạy kdb5_util create trên realm đang có dữ liệu.**

### 5.1. Packages và krb5.conf

~~~bash
sudo apt-get update
sudo apt-get install -y krb5-kdc krb5-admin-server krb5-user
~~~

File **/etc/krb5.conf** trên KDC, client và app server:

~~~ini
[libdefaults]
    default_realm = LAB.EXAMPLE.ORG
    dns_lookup_realm = false
    dns_lookup_kdc = false
    rdns = false

[realms]
    LAB.EXAMPLE.ORG = {
        kdc = kdc.lab.example.org
        admin_server = kdc.lab.example.org
    }

[domain_realm]
    .lab.example.org = LAB.EXAMPLE.ORG
    lab.example.org = LAB.EXAMPLE.ORG
~~~

**rdns=false** giảm một số reverse-DNS canonicalization của MIT krb5, nhưng không bảo đảm mọi Java/Windows/browser chọn SPN giống nhau. Kiểm hostname thực dùng trong service ticket sau kvno.

### 5.2. KDC configuration

File **/etc/krb5kdc/kdc.conf**, chỉ trên máy KDC:

~~~ini
[kdcdefaults]
    kdc_ports = 88
    kdc_tcp_ports = 88

[realms]
    LAB.EXAMPLE.ORG = {
        database_name = /var/lib/krb5kdc/principal
        acl_file = /etc/krb5kdc/kadm5.acl
        key_stash_file = /etc/krb5kdc/stash
        max_life = 10h 0m 0s
        max_renewable_life = 7d 0h 0m 0s
        default_principal_flags = +preauth
    }
~~~

Một số MIT Kerberos versions sử dụng cấu hình mới hơn như **kdc_listen** và **kdc_tcp_listen**. Xác nhận tên tùy phiên bản và daemon thực đang nghe TCP/UDP 88. Database path phải trùng nơi kdb5_util tạo database.

ACL chỉ cho lab trong **/etc/krb5kdc/kadm5.acl**:

~~~text
labadmin/admin@LAB.EXAMPLE.ORG *
~~~

Dòng này trao quyền admin rộng cho test principal; **không đưa ACL đó vào production**.

### 5.3. Tạo realm và principals

~~~bash
# Chỉ trên một KDC LAB MỚI, có master password tương tác.
sudo kdb5_util create -s -r LAB.EXAMPLE.ORG

# Hai user principals có password được nhập tương tác.
sudo kadmin.local -q "addprinc labadmin/admin@LAB.EXAMPLE.ORG"
sudo kadmin.local -q "addprinc alice@LAB.EXAMPLE.ORG"

# Service key ngẫu nhiên, dùng cho keytab.
sudo kadmin.local -q "addprinc -randkey HTTP/app.lab.example.org@LAB.EXAMPLE.ORG"

sudo systemctl enable --now krb5-kdc
sudo systemctl enable --now krb5-admin-server
sudo systemctl status krb5-kdc
~~~

Không lưu master/user passwords trong shell history. Nếu daemon không chạy, kiểm KDC database/stash, config path, file permissions và port. Trên distro không có systemd, kiểm cơ chế khởi động service tương ứng.

### 5.4. Xuất keytab và bảo vệ secret

Trên KDC lab:

~~~bash
sudo install -d -m 0700 /etc/security/keytabs
sudo kadmin.local -q "getprinc HTTP/app.lab.example.org@LAB.EXAMPLE.ORG"
sudo kadmin.local -q "ktadd -k /etc/security/keytabs/http-app.keytab HTTP/app.lab.example.org@LAB.EXAMPLE.ORG"
sudo klist -kte /etc/security/keytabs/http-app.keytab
~~~

Kết quả phải có entry **HTTP/app.lab.example.org@LAB.EXAMPLE.ORG** cùng KVNO/enctype phù hợp; không giả định KVNO luôn là 1.

Chuyển keytab sang app server qua kênh an toàn được quản trị, đặt tại **/etc/security/keytabs/http-app.keytab**, cho OS account chạy Java sở hữu và chỉ đọc được qua mode **0400/0600** hoặc ACL tương đương. Không copy keytab cho client, không nhét vào Spring jar.

Trên app server, chạy bằng đúng OS user app:

~~~bash
klist -kte /etc/security/keytabs/http-app.keytab
test -r /etc/security/keytabs/http-app.keytab && echo KEYTAB_READABLE
~~~

**klist -kte** chỉ kiểm file có principal, KVNO và enctype. Nó **không chứng minh service ticket đã được Java accept**. Khi xoay keys, bảo đảm phân phối keytab đúng phiên bản tới tất cả app nodes trước/đúng thời điểm rollout.

## 6. Kiểm TGT và HTTP service ticket từ client

Trên máy client test có đúng realm/DNS/time:

~~~bash
kinit alice@LAB.EXAMPLE.ORG
klist -e
kvno HTTP/app.lab.example.org@LAB.EXAMPLE.ORG
klist -e
~~~

**Diễn giải:**

1. **kinit** phải lấy được TGT cho **alice@LAB.EXAMPLE.ORG** với principal cache còn hạn.
2. **kvno** yêu cầu KDC/TGS cấp service ticket cho **HTTP/app.lab.example.org@LAB.EXAMPLE.ORG**. Có thể in KVNO thực tế, không cố định giữa môi trường.
3. **klist** sau kvno cần thấy ticket dành cho service cùng TGT trong cache phù hợp.
4. Nếu kinit fail: kiểm username/password, realm, KDC DNS/port 88, time.
5. Nếu kvno báo **Server not found in Kerberos database**: HTTP SPN chưa có hoặc FQDN/realm sai.
6. Nếu client không có service ticket thì **chưa thể kết luận lỗi nằm ở Spring**.

Client có cached service ticket còn hạn đôi khi vẫn dùng được ST ngay cả khi TGT hết. Vì vậy để test TGS exchange mới, dùng credential cache test được cô lập thay vì xóa cache người dùng production.

| Lệnh | Chứng minh | Không chứng minh |
| --- | --- | --- |
| **kinit** | Lấy TGT. | Chưa có HTTP service ticket. |
| **kvno** | KDC cấp ticket đúng SPN. | Chưa chứng minh Java keytab accept. |
| **klist -kte** | Keytab có principal/KVNO/enctype. | Chưa chứng minh HTTP GSS thành công. |
| **401 Negotiate** | Server yêu cầu authentication. | Chưa có token được accept. |
| **HTTP 200 protected** | Request đã qua authz chain. | Cần xác nhận không dùng session/NTLM/headers giả. |

## 7. DNS, hostname, proxy, TLS và SPN

~~~text
Public browser URL:
  https://app.lab.example.org/private

Kerberos service principal:
  HTTP/app.lab.example.org@LAB.EXAMPLE.ORG

Spring backend:
  http://app-pod:8080

Keytab trên Java:
  HTTP/app.lab.example.org@LAB.EXAMPLE.ORG
~~~

**URL public FQDN, service principal và keytab phải thống nhất**, dù backend là container hostname. Nếu client truy cập IP hoặc localhost, tên dịch vụ cần xin sẽ khác; đó không phải bài test chuẩn cho public SPN.

Proxy cần chuyển **Authorization: Negotiate** tới Java nếu Spring là acceptor. Proxy không được biến một **X-Remote-User/X-User** header do browser tự khai thành verified identity. Nếu proxy tự làm GSS acceptor, backend phải có trust boundary qua network/mTLS và verified headers riêng; mẫu Spring ở phần sau không áp dụng nguyên xi.

Tất cả backend nodes chấp nhận service ticket cho cùng HTTP SPN cần keytab/key versions nhất quán. Nếu DNS alias/CNAME được dùng, kiểm client canonicalization; không mặc định alias tự khớp.

TLS public certificate phải được tin, SAN trùng FQDN. Để test CA lab dùng **curl --cacert**. Không tắt TLS verification hoặc Windows Extended Protection/channel binding chỉ để làm test xanh.

## 8. Spring Boot 3.3.5: SPNEGO acceptor dùng keytab thật

### Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>spnego-lab</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties><java.version>17</java.version></properties>
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
      <version>2.1.0</version>
    </dependency>
    <dependency>
      <groupId>org.springframework.security.kerberos</groupId>
      <artifactId>spring-security-kerberos-web</artifactId>
      <version>2.1.0</version>
    </dependency>
  </dependencies>
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
~~~

Đây là **Spring Security Kerberos extension 2.x** cho Spring Security 6.x; starter-security không tự tích hợp SPNEGO. Kiểm dependency versions/patch security trước khi dùng production.

### application.yml

~~~yaml
server:
  port: 8080

lab:
  kerberos:
    principal: "HTTP/app.lab.example.org@LAB.EXAMPLE.ORG"
    keytab: "/etc/security/keytabs/http-app.keytab"
~~~

### Main class

**src/main/java/com/example/spnegolab/SpnegoLabApplication.java**

~~~java
package com.example.spnegolab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SpnegoLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SpnegoLabApplication.class, args);
    }
}
~~~

### SecurityConfig.java

**src/main/java/com/example/spnegolab/SecurityConfig.java**

~~~java
package com.example.spnegolab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityContextRepository repository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository());
    }

    @Bean
    UserDetailsService localUsers() {
        return principal -> {
            if (!"alice@LAB.EXAMPLE.ORG".equals(principal)) {
                throw new UsernameNotFoundException(
                    "Kerberos principal not provisioned locally");
            }
            return User.withUsername(principal)
                .password("{noop}not-used-in-kerberos")
                .authorities("ROLE_EMPLOYEE")
                .build();
        };
    }

    @Bean
    SunJaasKerberosTicketValidator validator(Environment env) {
        SunJaasKerberosTicketValidator v =
            new SunJaasKerberosTicketValidator();
        v.setServicePrincipal(
            env.getRequiredProperty("lab.kerberos.principal"));
        v.setKeyTabLocation(new FileSystemResource(
            env.getRequiredProperty("lab.kerberos.keytab")));
        return v;
    }

    @Bean
    KerberosServiceAuthenticationProvider provider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService localUsers) {
        KerberosServiceAuthenticationProvider p =
            new KerberosServiceAuthenticationProvider();
        p.setTicketValidator(validator);
        p.setUserDetailsService(localUsers);
        return p;
    }

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http,
            SecurityContextRepository repository,
            KerberosServiceAuthenticationProvider provider)
            throws Exception {
        SpnegoAuthenticationProcessingFilter spnego =
            new SpnegoAuthenticationProcessingFilter();
        spnego.setAuthenticationManager(new ProviderManager(provider));
        spnego.setSecurityContextRepository(repository);
        spnego.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/lab-health").permitAll()
                .anyRequest().authenticated())
            .securityContext(context -> context
                .securityContextRepository(repository))
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .authenticationProvider(provider)
            .addFilterBefore(spnego, BasicAuthenticationFilter.class);
        return http.build();
    }
}
~~~

**Cơ chế:**

- **SpnegoEntryPoint** trả 401 Negotiate cho protected request chưa authenticated.
- **SpnegoAuthenticationProcessingFilter** đọc Authorization Negotiate, chuyển token qua ProviderManager.
- **KerberosServiceAuthenticationProvider + SunJaasKerberosTicketValidator** xác minh Kerberos bằng principal và keytab phía server.
- **UserDetailsService** chỉ chấp nhận verified Alice đã provision; Bob có service ticket hợp lệ vẫn không tự được cấp ROLE_EMPLOYEE.
- **SecurityContextRepository** được gắn đồng nhất vào Spring và custom filter; **ChangeSessionIdAuthenticationStrategy** giảm session fixation.
- Không có logic đọc username từ header chưa verified hoặc tự cấp Authentication khi keytab lỗi.

### LabController.java

**src/main/java/com/example/spnegolab/LabController.java**

~~~java
package com.example.spnegolab;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LabController {
    @GetMapping("/lab-health")
    public Map<String, String> health() {
        return Map.of("service", "spnego-lab", "route", "public");
    }

    @GetMapping("/private")
    public Map<String, String> privatePage(Authentication auth) {
        return Map.of(
            "principal", auth.getName(),
            "result", "VERIFIED_BY_SERVER");
    }
}
~~~

Giá trị VERIFIED_BY_SERVER chỉ là label demo, không tự chứng minh GSS mechanism. Phải kiểm service ticket/KDC và validator thật.

### Khởi động

~~~bash
export JAVA_TOOL_OPTIONS="-Djava.security.krb5.conf=/etc/krb5.conf"
mvn spring-boot:run
~~~

App cần OS user có quyền đọc keytab, KDC/realm đúng và public HTTPS ingress. Không có KDC/keytab thật thì chỉ có thể kiểm compile/config phần nào, **không kết luận SPNEGO E2E thành công**.

## 9. Kiểm thử HTTP Negotiate bằng curl

Trên **test client đã kinit Alice và kvno HTTP service thành công**:

~~~bash
curl --version
curl --negotiate -u : --cacert /path/to/lab-ca.pem -i https://app.lab.example.org/private
~~~

Curl phải build với GSS-API/SSPI hoặc SPNEGO support. Theo manpage, **-u :** chỉ kích hoạt HTTP authentication, không phải password Kerberos rỗng; credentials lấy từ OS/GSS cache.

**Pass condition:** protected endpoint challenge 401 Negotiate khi chưa có app session; client dùng service ticket đúng, Spring validator accept token và final HTTP response có **200 + principal alice@LAB.EXAMPLE.ORG**. Số vòng HTTP authentication phụ thuộc client, không mặc định đúng hai requests.

**Test anonymous:**

~~~bash
curl --cacert /path/to/lab-ca.pem -i https://app.lab.example.org/private
~~~

Không gửi Negotiate credentials, protected resource phải không tiết lộ private content, thường trả 401 WWW-Authenticate: Negotiate.

**Đừng coi /lab-health 200 là proof SSO**; đó là public route. Curl verbose/trace có thể log Authorization header và GSS token, không upload nguyên trace lên issue tracker/CI.

## 10. Browser Integrated Windows Authentication

Với browser trên workstation managed:

1. Truy cập **https://app.lab.example.org/private** thay IP/localhost.
2. IWA allowlist/intranet zone chỉ có các hosts lab được quản trị, không allowlist mọi site.
3. OS user phải có Kerberos TGT/service ticket trong credential cache hoặc có thể xin ticket.
4. Nếu browser đã có HttpSession, request tiếp theo có thể bỏ qua fresh GSS exchange; thử profile/session mới khi kiểm authentication.
5. Một số clients có thể fallback NTLM trong Negotiate; **không gọi đó là Kerberos-only PASS** khi chỉ có HTTP header.
6. Nếu Extended Protection/channel binding policy bật, cần kiểm TLS termination, proxy và acceptor GSS tương thích; không tắt global protection để chữa lỗi.
7. Logout HttpSession ở Spring **không xóa TGT/ST của OS**, nên browser có thể tự đăng nhập lại bằng Kerberos và tạo session mới.

## 11. Java 17 độc lập: preflight policy test

**SpnegoLabPreflight.java** không kết nối KDC và không verify tickets. Nó kiểm **cấu hình giả lập trước integration**, giúp phát hiện lệch URL host/SPN/keytab/đường truyền. Kết quả PASS CONFIG_READY chỉ cho biết dữ liệu mẫu nhất quán, không phải chứng cứ Kerberos đã xác thực.

~~~java
public class SpnegoLabPreflight {
    static final String HOST = "app.lab.example.org";
    static final String REALM = "LAB.EXAMPLE.ORG";

    record Setup(String urlHost, String requestedSpn,
        String keytabSpn, boolean keytabReadable,
        boolean tlsTrusted, boolean hasTgt,
        boolean headerForwarded, boolean accountEnabled) {}

    static String check(Setup s) {
        String expected = "HTTP/" + HOST + "@" + REALM;
        if (!HOST.equals(s.urlHost())) return "FAIL URL_HOST";
        if (!expected.equals(s.requestedSpn())) {
            return "FAIL SERVICE_PRINCIPAL";
        }
        if (!expected.equals(s.keytabSpn())) {
            return "FAIL KEYTAB_PRINCIPAL";
        }
        if (!s.keytabReadable()) return "FAIL KEYTAB_UNREADABLE";
        if (!s.tlsTrusted()) return "FAIL TLS_TRUST";
        if (!s.hasTgt()) return "FAIL CLIENT_TGT_MISSING";
        if (!s.headerForwarded()) return "FAIL NEGOTIATE_HEADER";
        if (!s.accountEnabled()) return "FAIL LOCAL_ACCOUNT";
        return "PASS CONFIG_READY";
    }

    static void show(String label, Setup s) {
        System.out.println(label + ": " + check(s));
    }

    public static void main(String[] args) {
        String p = "HTTP/app.lab.example.org@LAB.EXAMPLE.ORG";
        show("baseline", new Setup("app.lab.example.org", p, p,
            true, true, true, true, true));
        show("alias url", new Setup("portal.lab.example.org", p, p,
            true, true, true, true, true));
        show("wrong spn", new Setup("app.lab.example.org",
            "HTTP/wrong.lab.example.org@LAB.EXAMPLE.ORG", p,
            true, true, true, true, true));
        show("wrong keytab", new Setup("app.lab.example.org", p,
            "HTTP/other.lab.example.org@LAB.EXAMPLE.ORG",
            true, true, true, true, true));
        show("keytab unreadable", new Setup("app.lab.example.org", p, p,
            false, true, true, true, true));
        show("untrusted tls", new Setup("app.lab.example.org", p, p,
            true, false, true, true, true));
        show("no tgt", new Setup("app.lab.example.org", p, p,
            true, true, false, true, true));
        show("header stripped", new Setup("app.lab.example.org", p, p,
            true, true, true, false, true));
        show("account disabled", new Setup("app.lab.example.org", p, p,
            true, true, true, true, false));
    }
}
~~~

Chạy:

~~~bash
javac SpnegoLabPreflight.java
java SpnegoLabPreflight
~~~

**stdout chính xác:**

~~~text
baseline: PASS CONFIG_READY
alias url: FAIL URL_HOST
wrong spn: FAIL SERVICE_PRINCIPAL
wrong keytab: FAIL KEYTAB_PRINCIPAL
keytab unreadable: FAIL KEYTAB_UNREADABLE
untrusted tls: FAIL TLS_TRUST
no tgt: FAIL CLIENT_TGT_MISSING
header stripped: FAIL NEGOTIATE_HEADER
account disabled: FAIL LOCAL_ACCOUNT
~~~

Một client đã cache ST hợp lệ có thể dùng nó dù TGT đã hết; test no tgt chỉ là **case preflight bắt đầu từ TGT mới**, không mô phỏng toàn bộ credential cache. Không nhận booleans từ client như bằng chứng để cấp Authentication ở ứng dụng thật.

## 12. Quy trình test E2E và negative cases

**A. KDC test:**

~~~bash
kinit alice@LAB.EXAMPLE.ORG
klist -e
kvno HTTP/app.lab.example.org@LAB.EXAMPLE.ORG
klist -e
~~~

Phải thấy TGT và ST đúng principal; nếu kinit/kvno fail thì chưa tới tầng HTTP.

**B. Acceptor test:** trên app server, kiểm keytab/KVNO/enctype và quyền đọc bằng OS user app; run Spring; kết quả anonymous GET /private nên là challenge 401.

**C. HTTP positive:** curl --negotiate -u : qua HTTPS CA trusted tới /private; kết quả cuối 200 verified Alice, có bằng chứng Java GSS/validator và service ticket thật.

**D. Negative local account:** tạo Bob trên **KDC lab** và thử cùng HTTP service; Bob có thể có ST đúng nhưng demo chỉ provision Alice nên không được truy cập.

~~~bash
# Chỉ chạy trên KDC LAB:
sudo kadmin.local -q "addprinc bob@LAB.EXAMPLE.ORG"

# Trên test client Bob có quyền:
kinit bob@LAB.EXAMPLE.ORG
kvno HTTP/app.lab.example.org@LAB.EXAMPLE.ORG
curl --negotiate -u : --cacert /path/to/lab-ca.pem -i https://app.lab.example.org/private
~~~

**E. Wrong SPN:** thử kvno cho service chưa tạo, ví dụ HTTP/wrong.lab.example.org@LAB.EXAMPLE.ORG. KDC không được phát ticket cho service không tồn tại.

**F. Wrong keytab/KVNO:** trên **app instance lab cách ly**, dùng keytab thuộc service khác hoặc snapshot keytab cũ sau key rotation có kiểm soát. GSS acceptor phải reject. **Không rotate principal production chỉ để làm negative test**.

**G. Time/replay:** dùng disposable VM/container/test harness để kiểm ticket expired, clock skew và replay; không chỉnh đồng hồ production, không bỏ replay verification.

**H. Multi-node:** kiểm keytab/KVNO, krb5.conf, JDK, host headers và secrets nhất quán trên từng node.

**I. Logout:** session Spring bị invalidate nhưng OS TGT còn nên browser có thể login lại; phân biệt session cũ với authentication mới.

## 13. Ma trận kiểm thử

| # | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| 1 | KDC lab và user Alice hợp lệ | kinit có TGT. |
| 2 | HTTP service principal đúng | kvno có ST. |
| 3 | Keytab principal/KVNO/enctype đúng | Acceptor có thể validate. |
| 4 | Curl GSSAPI, HTTPS trust, FQDN chuẩn | Kerberos E2E thành công. |
| 5 | Anonymous chưa login | Không đọc private resource. |
| 6 | Public health trả 200 | Không được coi là SSO PASS. |
| 7 | Bob có ST nhưng không provision ở app | Deny local account. |
| 8 | TGT còn, KDC reachable, ST chưa có | Có thể xin ST mới. |
| 9 | TGT hết, ST cache còn hạn | Có thể authenticate bằng ST. |
| 10 | Không có TGT/ST | Không silent SSO. |
| 11 | URL alias khác HTTP SPN | Fail hoặc cần explicit alias SPN. |
| 12 | URL bằng IP/localhost | Không phải test chuẩn cho public SPN. |
| 13 | Keytab chứa HTTP service khác | Reject. |
| 14 | Keytab realm sai | Reject. |
| 15 | App user không đọc được keytab | Fail, không chmod world-readable. |
| 16 | Keytab trống | Fail. |
| 17 | Key rotate nhưng app keytab cũ | KVNO mismatch, reject. |
| 18 | Enctype không tương thích | Reject, không dùng crypto yếu. |
| 19 | KDC port 88/DNS unreachable | kinit/kvno fail. |
| 20 | Client/KDC clock skew quá lớn | Kerberos fail. |
| 21 | Client/server clock skew quá lớn | Authenticator fail. |
| 22 | Browser không IWA allowlist | Có thể không gửi Negotiate. |
| 23 | Curl thiếu SPNEGO/GSS support | Không chạy được test đó. |
| 24 | TLS certificate không trusted | TLS fail; không dùng -k cho QA PASS. |
| 25 | Proxy strip Authorization header | Java không nhận token. |
| 26 | Client giả header X-Remote-User | Không thành Kerberos principal. |
| 27 | NTLM fallback | Không ghi Kerberos-only PASS. |
| 28 | GSS token malformed/replay | Reject. |
| 29 | ST expired | Reject theo Kerberos policy. |
| 30 | Kerberos verified, local account disabled | Deny. |
| 31 | User thiếu tenant/business role | 403 ở API protected. |
| 32 | Request dựa trên HttpSession cũ | Chưa chứng minh fresh GSS. |
| 33 | Logout app, OS TGT còn | Có thể re-authenticate. |
| 34 | Keytab khác giữa các LB nodes | Node-specific failures. |
| 35 | CNAME làm đổi hostname canonical | Kiểm SPN thật client yêu cầu. |
| 36 | KDC offline nhưng ST cached | Có thể vẫn authenticate. |
| 37 | KDC offline và không có ST | Không xin ticket mới. |
| 38 | Log chứa Authorization token/keytab | Security QA FAIL. |
| 39 | Channel binding mismatch | Phân tích TLS/EP, không tắt protection. |
| 40 | SPN ở realm khác cùng short name | Không auto-map user. |
| 41 | Secret keytab lọt Git/CI | Rotate/revoke theo incident runbook. |
| 42 | User dùng browser profile mới nhưng OS có TGT | Có thể silent SSO. |

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân và hướng kiểm |
| --- | --- |
| Kinit không liên hệ KDC | DNS, krb5.conf, firewall 88, daemon. |
| Kinit preauthentication failed | Wrong user/password, clock, realm policy. |
| Kvno Server not found | SPN HTTP/FQDN/realm sai hoặc chưa tạo. |
| Klist chỉ có TGT | ST chưa được lấy; chạy kvno. |
| Klist -kte không có đúng HTTP principal | Keytab xuất/triển khai sai. |
| Cannot find key of appropriate type | Enctype/keytab/JDK tương thích. |
| Checksum failed / decrypt error | Keytab stale, KVNO sai, principal sai. |
| KRB_AP_ERR_SKEW | Đồng bộ NTP/UTC. |
| KRB_AP_ERR_REPEAT | Kiểm replay/authenticator, không tắt bảo vệ. |
| Curl không hỗ trợ Negotiate | Binary thiếu GSSAPI/SSPI. |
| Browser không tự Negotiate | Hostname/IWA allowlist/OS ticket. |
| HTTP 401 loop | KDC, keytab, SPN, Authorization header, validator, local user mapping. |
| HTTP 200 anonymous | AuthorizationFilter, HttpSession hoặc proxy bypass. |
| HTTP 403 sau Kerberos pass | Local roles/tenant chưa được cấp. |
| App node A pass node B fail | Secret versions, config, krb5.conf, JDK khác. |
| Channel binding mismatch | TLS termination/Extended Protection/GSS mismatch. |
| Logout rồi browser tự login lại | OS Kerberos tickets vẫn còn hạn. |

Có thể bật **-Dsun.security.krb5.debug=true** trong lab với log access controls để xem phân tầng lỗi; không dùng ở production hoặc xuất raw token/secret.

## 15. CI và MiniKdc

CI có thể dùng **MIT KDC container tạm** hoặc **Apache Directory MiniKdc** để tạo realm/principals/keytab cho tests. Cần DNS/FQDN test, TLS CA trusted, secret injection, test user Bob, test SPN/KVNO lỗi và cleanup credential caches. MiniKdc hữu ích cho Java integration, **không thay thế** AD/GPO/NTLM/browser/IIS proxy/channel binding của staging doanh nghiệp.

**Phân tầng kết quả:** (1) Java offline preflight chỉ chứng minh policy mẫu; (2) MockMvc chỉ chứng minh Spring HTTP filter/authorization; (3) kinit/kvno chỉ chứng minh KDC/TGS; (4) curl Negotiate qua Spring mới chứng minh Kerberos HTTP end-to-end; (5) browser AD staging chứng minh policy/enterprise compatibility. Không gộp các bằng chứng này làm một.

## 16. Checklist production-like lab

- [ ] KDC test cô lập, realm và DNS đúng, port 88 reachable.
- [ ] Client kinit có TGT và kvno nhận ST đúng HTTP SPN.
- [ ] Keytab server-only, đúng principal/KVNO/enctype, chỉ app user đọc.
- [ ] Host public, TLS SAN, browser URL và principal khớp.
- [ ] Curl --negotiate -u : có GSSAPI/SSPI và dùng trusted CA.
- [ ] Spring filter/provider/JAAS validator thực sự xác minh token.
- [ ] UserDetailsService/local IAM chỉ cấp đúng account/roles.
- [ ] Anonymous, Bob, wrong SPN, wrong keytab, expiry, replay đều bị từ chối.
- [ ] Proxy forward Authorization, không tin client X-User.
- [ ] HA nodes có keytab và config nhất quán.
- [ ] Browser IWA allowlist có kiểm soát, không NTLM fallback ngoài policy.
- [ ] Không ghi raw token/keytab; có kế hoạch rotation/cleanup secrets.

## 17. Câu hỏi ôn tập

**1. Kinit thành công đã chứng minh SPNEGO chưa?** Không, nó mới tạo TGT; phải kiểm ST, acceptor keytab, HTTP Negotiate và local authorization.

**2. SPN phải dùng public FQDN hay pod hostname?** Public FQDN mà client truy cập/canonicalize, ví dụ HTTP/app.lab.example.org@LAB.EXAMPLE.ORG.

**3. Vì sao ktadd chạy lại có thể làm app fail?** Vì service keys/KVNO có thể đổi trong khi app còn keytab cũ.

**4. Curl -u : có phải gửi password rỗng để login?** Không, nó chỉ bật HTTP Negotiate code path; Kerberos credentials từ OS cache.

**5. Browser không hỏi mật khẩu có chắc Kerberos hoạt động?** Không; có thể session cookie, NTLM hoặc proxy authentication.

**6. Bob có ticket thật nhưng bị từ chối có bất thường không?** Không; local account policy có thể deny Bob sau khi Kerberos xác thực.

**7. Keytab có nên commit vào Git?** Không; keytab là credential bí mật của service acceptor.

**8. TGT hết nhưng service ticket còn hạn thì sao?** Client có thể dùng ST cached theo GSS policy.

**9. Có nên tắt TLS validation hoặc replay checks để chữa lab?** Không; phải sửa CA, clock, service keys và configuration.

**10. Logout Spring xóa OS TGT không?** Không; user có thể silent reauthenticate và tạo app session mới.

## 18. Tài liệu chính thống

1. [Spring Security Kerberos Reference](https://docs.spring.io/spring-security-kerberos/reference/ssk.html): SpnegoEntryPoint, filter, provider và SunJaasKerberosTicketValidator.
2. [Spring Security Kerberos 2.1.x API](https://docs.spring.io/spring-security-kerberos/docs/2.1.x/api/allclasses-index.html): API và MiniKdc.
3. [MIT Kerberos Installing KDCs](https://web.mit.edu/kerberos/www/krb5-1.15/doc/admin/install_kdc.html): tạo realm/KDC.
4. [MIT Kerberos krb5.conf](https://www.mit.edu/~kerberos/krb5-devel/doc/admin/conf_files/krb5_conf.html): realm/KDC mapping.
5. [MIT Kerberos kdc.conf](https://www.mit.edu/~kerberos/krb5-current/doc/admin/conf_files/kdc_conf.html): KDC config.
6. [MIT Kerberos kadmin.local](https://www.mit.edu/~kerberos/krb5-latest/doc/admin/admin_commands/kadmin_local.html): addprinc và ktadd.
7. [MIT kinit](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/kinit.html), [klist](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/klist.html), [kvno](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/kvno.html): test credentials.
8. [curl --negotiate](https://curl.se/docs/manpage.html): GSSAPI/SSPI với -u :.
9. [RFC 4120 Kerberos V5](https://www.rfc-editor.org/rfc/rfc4120): TGT/TGS/ST/replay.
10. [RFC 4559 HTTP SPNEGO](https://www.rfc-editor.org/rfc/rfc4559): HTTP Negotiate.
11. [RFC 4178 SPNEGO](https://www.rfc-editor.org/rfc/rfc4178): GSS negotiation.
12. [Spring Security Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): SecurityContext/session fixation.

**Kết luận:** Kiểm thử SPNEGO phải chứng minh **KDC test → user TGT → service ticket HTTP/FQDN đúng → keytab KVNO/enctype → HTTPS Negotiate → Spring GSS acceptor → local authorization**. Lỗi phải được sửa đúng tầng KDC/DNS/SPN/keytab/clock/TLS/browser/proxy/Spring; không hạ bảo mật để lấy HTTP 200.
