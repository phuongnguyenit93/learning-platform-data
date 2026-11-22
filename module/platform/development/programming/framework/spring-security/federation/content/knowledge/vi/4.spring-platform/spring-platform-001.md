# Chọn phiên bản Spring Boot, Spring Security và thư viện giao thức tương thích

**Chủ đề:** Spring Security – federation / Nền tảng Spring. Bài học này hướng dẫn chọn một **tổ hợp phiên bản có thể xây dựng, chạy và bảo trì được** để triển khai OIDC/OAuth 2.0, SAML 2.0 hoặc Kerberos/SPNEGO với Spring Security.

**Mốc thông tin: 07/11/2026.** Các số phiên bản dưới đây được đối chiếu với tài liệu Spring công khai tại thời điểm soạn. Khi bắt đầu dự án mới hoặc chuẩn bị phát hành, phải đọc lại bản vá, dependency BOM và thời hạn hỗ trợ. Không coi ví dụ phiên bản trong bài là “phiên bản mới nhất” vĩnh viễn.

## 1. Hiểu cấu trúc bộ công nghệ trước khi chọn phiên bản

```text
Java/JDK và Maven hoặc Gradle
  └─ Spring Boot (parent hoặc dependency management BOM)
      ├─ Spring Framework (Core, Web MVC/WebFlux, HTTP)
      ├─ Spring Security (Core, Web, Config)
      │   ├─ OAuth2 Client / OpenID Connect login
      │   ├─ OAuth2 Resource Server / JOSE-JWT
      │   ├─ SAML2 Service Provider / OpenSAML
      │   ├─ Kerberos/SPNEGO (khi sử dụng)
      │   └─ OAuth2 Authorization Server (khi tự cấp token)
      ├─ Servlet container / reactive runtime
      └─ Jackson, logging, test, các thư viện trung gian
```

**Spring Boot** điều phối các phiên bản Spring Framework, Spring Security, thư viện nền và một số thư viện ngoài Spring trong BOM `spring-boot-dependencies`. **Spring Security** gồm các mô-đun phải tương thích API và phiên bản. **Thư viện giao thức** có thể kéo thêm OpenSAML, thư viện XML Signature, Nimbus JOSE/JWT, Java GSS/Kerberos hoặc thư viện chuyên biệt cho Identity Provider (IdP).

Vì thế, lựa chọn đúng không phải là “lấy Spring Security bản mới nhất và cài vào Boot bất kỳ”. Cần chọn **Spring Boot release train** có hỗ trợ, rồi để BOM quyết định các phiên bản đã được phối hợp. Một thay đổi major có thể làm sai bytecode, package namespace, auto-configuration, xác minh assertion hoặc token.

Phân biệt các vai trò để không chọn sai starter:

- **OIDC login / OAuth2 Client:** ứng dụng web đóng vai client/Relying Party, đưa người dùng đến OpenID Provider để xác thực và nhận authorization code/ID Token.
- **OAuth2 Resource Server:** API nhận và kiểm chứng access token (JWT hoặc opaque token), không tự xây trải nghiệm web SSO.
- **SAML 2.0 SP:** ứng dụng web là Service Provider/Relying Party, xác minh SAML Response/Assertion từ IdP.
- **Kerberos/SPNEGO:** ứng dụng web dùng ticket của miền/KDC trong mô hình Windows Integrated Authentication.
- **Authorization Server:** chính dịch vụ của bạn cấp authorization code/access token cho các client. Đừng cài nó khi ứng dụng chỉ cần đăng nhập vào IdP khác.
- **LDAP/SCIM:** directory/provisioning không thay cho giao thức web SSO; chỉ thêm client LDAP/SCIM nếu nghiệp vụ thực sự cần.

## 2. Ma trận phiên bản làm điểm xuất phát (07/11/2026)

| Spring Boot đã phát hành | Spring Framework do Boot quản lý | Spring Security do Boot quản lý | Java tối thiểu | Sử dụng phù hợp |
| --- | --- | --- | --- | --- |
| **4.1.2** | Dòng **7.0.x** | **7.1.2** | Java **17** | Dự án mới có thư viện phụ trợ và môi trường tương thích Boot 4 |
| **4.0.9** | Dòng **7.0.x** | **7.0.8** | Java **17** | Hệ thống đang dùng Boot 4.0; cần tính lịch cập nhật nhánh |
| **3.5.16** | Dòng **6.2.x** | **6.5.11** | Java **17** | Baseline hiện hữu hoặc bước chuyển tiếp trước khi lên Boot 4 |
| **4.2.0-RC2** (preview tại thời điểm kiểm tra) | Phụ thuộc bản preview | Phụ thuộc bản preview | Đọc yêu cầu preview | Thử nghiệm migration; không mặc định dùng production khi chưa GA |

Các phiên bản Security trong bảng là giá trị được công bố trong **Managed Dependency Coordinates** của đúng Boot release: Boot 4.1.2 quản lý các artifact Security chính ở **7.1.2**, Boot 4.0.9 ở **7.0.8**, Boot 3.5.16 ở **6.5.11**. Với **Boot 3.5.16**, Spring Authorization Server là dòng riêng **1.5.8**; với **Boot 4.x**, khả năng Authorization Server đã là mô-đun của Spring Security 7.

**Java 17+** là baseline của các dòng nêu trên. Có thể chọn Java 21 LTS khi CI, runtime, SDK và môi trường triển khai hỗ trợ; kiểm tra giới hạn JDK cụ thể trong System Requirements của từng bản vá. Không dùng `--release 21` rồi deploy lên Java 17. Maven/Gradle wrapper, bytecode, native image toolchain, container và ứng dụng phải cùng mục tiêu.

**Spring Boot GA không đồng nghĩa mọi nhánh còn hỗ trợ bảo mật.** Khi khóa phiên bản, tra [Spring Support Policy](https://spring.io/support), thông báo CVE, release notes và chính sách bảo trì thực tế của tổ chức. Không dùng RC/milestone/snapshot chỉ vì số major/minor cao hơn.

### 2.1. Quy tắc của BOM

Khi có `spring-boot-starter-parent` (Maven) hoặc import Boot BOM bằng Maven/Gradle, các dependency được BOM quản lý **không cần khai báo `<version>` hoặc version string**. Ví dụ Boot 4.1.2 + `spring-security-oauth2-client` sẽ chọn Security 7.1.2 từ BOM.

Chỉ override một dependency khi có yêu cầu cụ thể (bản vá an ninh, tương thích phần mềm ngoài) và đã đánh giá trên toàn bộ classpath. Đổi riêng `spring-security-core` từ 7.1.2 sang một phiên bản khác nhưng giữ `spring-security-web`, `config` và `test` cũ có thể dẫn đến `NoSuchMethodError` khi runtime. Nếu Spring Security mới yêu cầu phiên bản Spring Framework mới, xem hướng dẫn của Spring Security thay vì tự đoán tổ hợp.

**Không trộn Spring Security 6.x và 7.x cùng JVM**; không trộn Framework 6 với 7 trong một Spring Boot 4 application. Hạn chế thêm BOM thứ hai ghi đè phiên bản Security/OpenSAML/Nimbus/Jackson mà không phân tích độ ưu tiên dependency management.

## 3. Ma trận thư viện theo giao thức và phiên bản Boot

Các starter trong hai cột Boot có group `org.springframework.boot` nếu không chỉ rõ group khác.

| Vai trò hoặc yêu cầu | **Boot 4.1.x / Security 7.1.x** | **Boot 3.5.x / Security 6.5.x** | Điều kiện kèm theo |
| --- | --- | --- | --- |
| Web MVC/Servlet | `spring-boot-starter-webmvc` | `spring-boot-starter-web` | Boot 4 đổi starter để rõ mô-đun; starter `web` cũ còn để di trú nhưng deprecated |
| Spring Security chung | `spring-boot-starter-security` | `spring-boot-starter-security` | Chỉ một dòng Security theo BOM |
| **OIDC Login / OAuth2 Client** | `spring-boot-starter-security-oauth2-client` | `spring-boot-starter-oauth2-client` | OP issuer/discovery, client registration, callback, client secret/PKCE |
| **OAuth2 Resource Server** | `spring-boot-starter-security-oauth2-resource-server` | `spring-boot-starter-oauth2-resource-server` | API JWT/opaque token, issuer, audience, key/introspection |
| **SAML 2.0 Service Provider** | `spring-boot-starter-security-saml2` | `org.springframework.security:spring-security-saml2-service-provider` | Cần thêm repository Shibboleth để resolve OpenSAML |
| **OAuth2 Authorization Server** | `spring-boot-starter-security-oauth2-authorization-server` | `spring-boot-starter-oauth2-authorization-server` | Security 7 tích hợp AS; Boot 3 quản lý dòng AS 1.5.x |
| **Kerberos/SPNEGO** | `org.springframework.security:spring-security-kerberos-core` và `spring-security-kerberos-web` | Extension dòng 2.x, group `org.springframework.security.kerberos` | Kiểm tra bản extension hỗ trợ Security 6.5, JDK và hạ tầng KDC |
| Test Security | `spring-boot-starter-security-test` hoặc `spring-security-test` | `org.springframework.security:spring-security-test` | Test module phải cùng major/minor Security runtime |

**Không thêm tất cả starter chỉ vì ứng dụng có chữ SSO.** Một Spring MVC web app dùng OIDC không cần SAML/OpenSAML; một resource server chỉ xác minh Bearer token không cần login client; một B2B portal dùng SAML nên có module SAML SP. Thư viện thừa làm tăng classpath, rủi ro xung đột và công vá lỗi.

### 3.1. OIDC và OAuth2 trên Boot 4

OIDC login thường sử dụng `spring-boot-starter-security-oauth2-client`, từ đó kéo các mô-đun OAuth2, JOSE cần thiết. Ứng dụng phải thực hiện Authorization Code theo tiêu chuẩn, kiểm chứng `iss`, `aud`, chữ ký, thời hạn, `state` và `nonce` theo luồng; public client dùng PKCE. Client secret không đặt trong trình duyệt.

API nhận JWT nên dùng resource server module; JWT phải được kiểm chứng theo issuer và **đối tượng nhận/access token audience** mà API trông đợi. ID Token dành cho client xác nhận danh tính người dùng **không tự động là access token** có quyền gọi API. OIDC client và resource server có thể cùng một sản phẩm nhưng phải chia security filter chain và chính sách rõ ràng.

**Không tự chọn Nimbus JOSE/JWT chỉ vì một ví dụ trên mạng có số phiên bản cao hơn**. BOM/starter thường giải quyết bộ JOSE liên quan; nếu thư viện ngoài yêu cầu version riêng, xem runtime graph, release notes và thử chữ ký/thuật toán thực tế của IdP.

### 3.2. SAML2 SP và OpenSAML

SAML v2.0 web SSO của Spring Security là tích hợp **Servlet**, sử dụng `spring-security-saml2-service-provider`. Với Boot 4.1 có starter `spring-boot-starter-security-saml2`, trong khi Boot 3.5 dùng module Security trực tiếp. **OpenSAML** cần kho Shibboleth Releases, vì vậy Maven/Gradle ngoài Maven Central phải có:

```text
https://build.shibboleth.net/maven/releases/
```

Tài liệu Spring Security 7 hiện mô tả `OpenSaml5AuthenticationProvider`. Khi nâng từ Security 6.x hoặc SAML extension đời cũ, cần kiểm tra việc nâng OpenSAML, thay đổi Java API, xử lý metadata, `RelyingPartyRegistration`, cấu hình ký/mã hóa, chữ ký và mapping authorities. Không sửa lỗi dependency bằng cách ép một `org.opensaml` major riêng trái với tổ hợp được hỗ trợ.

Nếu web chính là **WebFlux**, đừng sao chép API Servlet như `HttpSecurity` vào `SecurityWebFilterChain` rồi tin SAML sẽ chạy. Kiểm tra hỗ trợ trên đúng phiên bản; mô hình **identity broker/gateway Servlet** phía trước và dùng OIDC/OAuth2 cho ứng dụng reactive có thể đơn giản hơn.

### 3.3. Kerberos/SPNEGO và vấn đề đổi Maven group

Spring Security Kerberos **7.1.2** được tài liệu chính thức mô tả là kiểm thử cùng JDK 17, Spring Security 7.1.2 và Spring Framework 7.0.x. Với Security 7, Maven coordinates đổi về:

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

Boot 4.1.2 BOM quản lý các mô-đun đó ở Security **7.1.2**. Với Boot 3.5 / Security 6.5, extension Kerberos thế hệ trước dùng group `org.springframework.security.kerberos` và bản 2.x độc lập; **phải đọc compatibility/release notes của extension 2.x cụ thể** trước khi thêm version thủ công. Tránh dùng artifact group mới Security 7 trong Boot 3.5, hoặc ép JAR extension 2.x vào Boot 4 chỉ vì tên class trùng nhau.

Bên ngoài build còn phải cấu hình service principal, SPN, keytab, Kerberos realm/KDC, DNS, đồng hồ hệ thống và trình duyệt HTTP Negotiate. Một `401` trên intranet có thể hoàn toàn do SPN/keytab hoặc browser thay vì lỗi phiên bản.

### 3.4. OAuth Authorization Server, LDAP và SDK ngoài

Nếu sản phẩm **phát hành token** cho client khác, Boot 4.1 dùng `spring-boot-starter-security-oauth2-authorization-server` trong hệ sinh thái Security 7; Boot 3.5 dùng `spring-boot-starter-oauth2-authorization-server` với dòng Spring Authorization Server 1.5.x do Boot BOM quản lý. Không cài đồng thời JAR Authorization Server 1.5.x và mô-đun Security 7.

Truy cập AD bằng LDAP có thể yêu cầu Spring LDAP, nhưng **OIDC/SAML federation với IdP đã tích hợp AD không bắt buộc ứng dụng phải có client LDAP**. Với SDK IdP bên thứ ba (Keycloak adapter cũ, gateway module, XML/security library), kiểm tra version matrix của nhà phát hành: đặc biệt các ràng buộc Java 17, Jakarta Servlet, Spring Framework 7, Jackson 3 và Spring Security 7. Tránh dựa vào SDK không còn bảo trì nếu Spring Security đã có hỗ trợ chuẩn.

## 4. Chọn bộ phiên bản từ yêu cầu dự án

### Bước 1 – Xác định kiến trúc và ranh giới danh tính

Trước khi chọn dependency, trả lời: web Servlet hay WebFlux? Người dùng đăng nhập qua OIDC/SAML hay Windows Negotiate? API chỉ nhận access token hay cả login tương tác? Có tự làm Authorization Server không? Đối tác yêu cầu metadata, thuật toán ký hoặc thư viện đặc thù nào? CI chạy Java/Maven/Gradle nào? Có dùng Spring Cloud hoặc servlet container bên ngoài không?

Dùng bảng quyết định đơn giản:

| Câu hỏi | Đầu ra cần ghi |
| --- | --- |
| Web MVC hay reactive? | Starter web phù hợp, DSL Servlet hay Reactive |
| Vai trò federation? | OIDC client, SAML SP, Kerberos acceptor, JWT resource server hoặc Authorization Server |
| IdP yêu cầu gì? | Issuer/discovery/redirect; metadata/ACS/chứng chỉ; SPN/KDC |
| Ràng buộc hạ tầng? | Java toolchain, Gradle/Maven wrapper, proxy repository, Tomcat/Jetty |
| Có SDK/module ngoài BOM? | Artifact, group, version, compatibility document, người chịu trách nhiệm cập nhật |
| Hỗ trợ production? | Nhánh GA, lịch vá bảo mật, kế hoạch regression và rollback |

### Bước 2 – Chọn Spring Boot GA, rồi đối chiếu BOM

Với dự án mới, chọn Boot GA được hỗ trợ và thư viện quan trọng đã xác nhận tương thích. Ví dụ tại 07/11/2026, **Boot 4.1.2 + Security 7.1.2** là một cặp được quản lý chính thức. Với hệ thống chưa thể di trú, **Boot 3.5.16 + Security 6.5.11** là ví dụ baseline để chuẩn hóa và lên kế hoạch nâng cấp; cần đánh giá hỗ trợ thật của nhánh 3.5.

Không tự ghép Boot 3.5 với Security 7.1; không tự lấy Framework 7 cho ứng dụng Boot 3.5. Khi cần patch ngoài BOM vì CVE, phải có kiểm tra dependency và tích hợp tương ứng.

### Bước 3 – Chọn module tối thiểu cho đúng vai trò

- Web OIDC: MVC/WebFlux, Security, OAuth2 Client; đăng ký RP với IdP.
- API Bearer: Security, OAuth2 Resource Server; kiểm chứng đúng JWT/opaque access token.
- SAML portal: MVC, Security, SAML2 SP + Shibboleth repository, tin cậy certificate IdP.
- Intranet Kerberos: Security, đúng Kerberos extension và cấu hình AD/SPNEGO.
- Cấp token: Authorization Server; thiết kế client registration, scopes, key rotation, lưu token và policy.

### Bước 4 – Xác minh dependency tree **trước khi viết tính năng**

Phải kiểm tra **các phiên bản thực tế đã resolve**, không chỉ version nhìn thấy trong `pom.xml`. Maven có nearest-wins và dependency management, Gradle có conflict resolution/version constraints; một SDK có thể kéo bản không mong muốn. So sánh compile classpath và runtime classpath; build trên CI sạch với JDK chính thức.

## 5. Mẫu Maven: Spring Boot 4.1.2 + OIDC Login trên Servlet MVC

Mẫu này gồm các tệp Java 17+, XML và YAML cần đặt trong **một dự án Spring Boot Maven**; `javac` đơn lẻ không thể biên dịch lớp Spring vì thiếu classpath. Dự án **biên dịch được khi Maven resolve các dependency**, còn đăng nhập thật cần IdP và credentials hợp lệ; ví dụ không có stdout xác định trước.

```text
federation-web/
├─ pom.xml
└─ src/main/
   ├─ java/com/example/federation/
   │  ├─ FederationApplication.java
   │  └─ SecurityConfig.java
   └─ resources/application.yml
```

`pom.xml`:

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
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>federation-web</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-oauth2-client</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-test</artifactId>
            <scope>test</scope>
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

Không có `<version>` riêng cho starter hoặc Spring Security: Spring Boot parent quản lý.

`src/main/java/com/example/federation/FederationApplication.java`:

```java
package com.example.federation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederationApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederationApplication.class, args);
    }
}
```

`src/main/java/com/example/federation/SecurityConfig.java`:

```java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/public/**").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

`src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
        provider:
          corporate-idp:
            issuer-uri: https://idp.example.com/realms/corporate
```

Đây là miền URL minh họa: phải thay **issuer-uri** bằng OP thật, cung cấp `OIDC_CLIENT_ID` và `OIDC_CLIENT_SECRET` bằng biến môi trường/secret manager; đăng ký redirect URI phù hợp `/login/oauth2/code/corporate` tại IdP. Khi dùng reverse proxy, cấu hình forwarded headers/host/scheme và HTTPS đúng để tránh mismatch redirect. `oauth2Login` chỉ cung cấp cơ chế xác thực; **mapping quyền và tenant** cần bổ sung theo chính sách của hệ thống.

Tại thư mục chứa `pom.xml`:

```bash
java -version
mvn -version
mvn -DskipTests compile
mvn dependency:tree -Dincludes=org.springframework.security
mvn test
```

Trong dependency graph của Boot 4.1.2, kỳ vọng các mô-đun Security được quản lý là **7.1.2**. Với IdP sandbox thật, chạy `mvn spring-boot:run` rồi kiểm thử login/callback, không tuyên bố chương trình có một stdout cố định. Nếu chỉ cần API resource server, thay client starter bằng `spring-boot-starter-security-oauth2-resource-server` và khai báo filter chain/resource server config theo yêu cầu.

## 6. Mẫu Maven: Boot 3.5.16 + SAML2 Service Provider

Đoạn POM này làm rõ điểm khác giữa Boot 3 và 4: SAML trên Boot 3.5 dùng module `spring-security-saml2-service-provider` trực tiếp; vì OpenSAML cần thêm kho, POM khai báo Shibboleth Releases. Đây là **build example**, phải thêm Java application, SAML relying party metadata, trusted certificate, ACS và `saml2Login` mới có dịch vụ hoạt động.

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
    <groupId>com.example</groupId>
    <artifactId>partner-saml</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
            <snapshots>
                <enabled>false</enabled>
            </snapshots>
        </repository>
    </repositories>
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
            <artifactId>spring-security-saml2-service-provider</artifactId>
        </dependency>
    </dependencies>
</project>
```

Không tự thêm version 7.x cho SAML SP: Boot 3.5.16 BOM quản lý nó ở Security **6.5.11**. Khi nâng lên Boot 4.1.2, đổi `web` → `webmvc`, thêm `spring-boot-starter-security-saml2`, và kiểm tra migration toàn bộ API/security config/OpenSAML; **Boot 4 vẫn cần Shibboleth repository**. Nếu CI lỗi resolve `org.opensaml`, kiểm tra Nexus/Artifactory proxy và Maven mirror trước, không “sửa” bằng cách kéo OpenSAML khác major.

## 7. Mẫu Gradle: cách khóa một BOM tương thích

Đối với `build.gradle` (Groovy DSL) trên Boot 4.1.2, có thể dùng Spring Boot Gradle plugin và khai báo BOM qua Gradle `platform`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')

    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-security-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Nếu dùng plugin `io.spring.dependency-management` để import Boot BOM, tránh quản lý bằng **hai BOM xung đột**. Với SAML, bổ sung `maven { url 'https://build.shibboleth.net/maven/releases/' }` vào `repositories` và dependency `spring-boot-starter-security-saml2`. Nhớ khóa Gradle wrapper theo yêu cầu System Requirements của đúng Boot patch.

Lệnh kiểm tra trên Linux/macOS (Windows dùng `gradlew.bat`):

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-saml2-service-provider --configuration runtimeClasspath
./gradlew test
```

`dependencyInsight` cho SAML chỉ hiển thị module nếu dự án thực sự khai báo dependency SAML; không tìm thấy dependency phù hợp không phải lỗi của bản build OIDC. Kiểm tra cả `compileClasspath` và `runtimeClasspath` khi phát sinh lỗi runtime.

## 8. Thực hành kiểm chứng dependency tree / classpath

### 8.1. Maven

```bash
mvn help:effective-pom
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=org.springframework
mvn dependency:tree -Dincludes=org.opensaml
mvn test
```

Đọc các kết quả theo thứ tự:

1. Parent/BOM version có đúng với kiến trúc đã chốt?
2. `spring-security-core`, `spring-security-config`, `spring-security-web`, `spring-security-oauth2-*`, `spring-security-saml2-service-provider` và `spring-security-test` có cùng version family theo BOM?
3. Có SDK khác kéo Security 6 trong Boot 4, Framework 6 trong Framework 7 hoặc OpenSAML đời cũ vào runtime không?
4. Artifact đúng group và tên cho Boot major chưa? Kerberos 7 dùng `org.springframework.security`; Boot 3 Kerberos dùng extension group cũ.
5. Có repository đáng tin và khóa build/release trong CI? Token, secret, metadata/key IdP không được hardcode trong POM/YAML.
6. Có `ClassNotFoundException` hoặc `NoSuchMethodError` chỉ trên bản JAR đóng gói dù IDE compile thành công không? Nếu có, mở dependency graph **bên trong artifact cuối**.

Maven BOM quản lý được phiên bản dependency, nhưng nếu phiên bản khác bị explicit dependency hoặc parent/property override, runtime có thể khác kỳ vọng. `mvn -U test` kiểm tra cập nhật metadata theo cơ chế Maven; bản thân `-U` không giải quyết binary incompatibility.

### 8.2. Gradle

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml --configuration runtimeClasspath
./gradlew test
```

Gradle version constraints, plugin BOM và transitive dependencies có thể dẫn đến phiên bản **khác dòng** nếu áp dụng chồng chéo. Theo dõi dấu `->` trong báo cáo dependency resolution. Cần ghi lại dependency graph hoặc SBOM cùng build/commit để tái hiện lỗi federation chính xác trong production.

## 9. Nâng cấp từ Boot 3.5 / Security 6.5 sang Boot 4.1 / Security 7.1

**Chuyển major cần chuẩn bị và thử nghiệm, không chỉ sửa một số trong POM.**

1. **Ổn định baseline 3.5:** cập nhật đến bản vá phù hợp, giữ Java 17+, Spring Security 6.5 và chạy toàn bộ test. Đọc [Spring Security Migration 7.0](https://docs.spring.io/spring-security/reference/7.0/migration/index.html) để xử lý API deprecated, lambda DSL và hành vi xác thực/ủy quyền trước.
2. **Kiểm tra SDK ngoài BOM:** Spring Cloud, IdP adapter, thư viện XML/OpenSAML, Jackson, test frameworks, servlet engine, Jakarta namespace và bất kỳ custom starter nào. Boot 4 thay đổi module/auto-configuration và dùng Spring Framework 7; không giả định custom library Boot 3 sẽ tương thích Boot 4.
3. **Nâng parent/plugin Boot và module tương ứng:** chọn cùng nhánh BOM Security 7, thay `spring-boot-starter-web` bằng `webmvc`, OAuth2 Client/Resource Server/Authorization Server starter theo tên Boot 4, SAML2 starter theo Boot 4.
4. **Cập nhật Kerberos/Authorization Server:** kiểm tra group mới Kerberos Security 7, thay mô-đun AS 1.5.x bằng module Security 7 tương ứng; xóa import/mã adapter cũ nếu không còn hợp lệ.
5. **Sửa code và cấu hình:** Boot 4 modularization/Jackson 3/Servlet API; Security 7 thay đổi một số DSL/API và mặc định. Với ứng dụng cũ hơn Boot 3, bước di trú `javax.servlet.*` → `jakarta.servlet.*` phải được xử lý theo lộ trình Boot 3, không “vá” bằng cách đưa cả hai API vào classpath.
6. **Thử nghiệm federation thật/sandbox:** OIDC redirect, discovery, callback, session/CSRF; SAML metadata, ACS, signature validation, certificate rotation; Kerberos ticket/SPN; resource server audience/issuer; auth server token endpoint nếu có.
7. **Canary/rollback:** giữ bản deploy và cấu hình IdP compatible, monitor lỗi login; không xoay certificate/client secret một chiều khi chưa xác nhận có thể rollback. Ghi lại ADR về version pair và dependencies.

Các bản vá bảo mật có thể làm việc xác minh token/assertion nghiêm ngặt hơn; một IdP gửi message không đạt chuẩn có thể bị từ chối sau nâng cấp. Điều tra validation error, metadata, issuer/audience và chữ ký. **Không tắt signature verification, audience/issuer check, state hay CSRF để “cho hệ thống chạy lại”.**

## 10. Bảng lỗi thường gặp khi chọn sai tổ hợp

| Triệu chứng | Nguyên nhân có thể | Bước xác minh |
| --- | --- | --- |
| `NoSuchMethodError` hoặc `NoClassDefFoundError` | Framework/Security khác nhánh, class bị chuyển package hoặc exclusion sai | Đọc stack trace + runtime dependency tree, so với Boot BOM |
| `ClassNotFoundException: javax.servlet...` | SDK/adapter cũ chưa chuyển Jakarta cho Boot 3+/4 | Nâng SDK compatible `jakarta.servlet`, kiểm tra Servlet/container |
| Maven không tải `org.opensaml` | Thiếu Shibboleth Releases hoặc proxy nội bộ chưa cấu hình | Bổ sung đúng repository và kiểm tra mirror/TLS/network |
| SAML login lỗi sau upgrade | OpenSAML API hoặc metadata/certificate/ACS/issuer/audience sai | Test IdP sandbox, inspect validation đã lọc, đối chiếu exact assertion |
| OIDC báo thiếu client registration | Sai OAuth2 Client starter theo Boot major, thiếu config, issuer không có discovery | Xem build graph, client registration, metadata endpoint và redirect URI |
| API mọi request đều 401 | Access token sai issuer/audience, key/algorithm hoặc API đang xác minh ID Token | Kiểm tra `iss`, `aud`, key/JWKS, opaque introspection và policy API |
| SPNEGO hoạt động trên một số máy | Browser không gửi Negotiate, SPN/keytab/DNS/KDC/time sai | Kiểm tra domain join, service principal, ticket, realm, bản Kerberos extension |
| Unit test Security lỗi nhưng app build được | `spring-security-test` khác runtime hoặc test auto-config đổi | Dùng module test cùng BOM, sửa cấu hình `MockMvc`/`WebTestClient` |
| Local pass, CI fail | Khác JDK/wrapper/Gradle plugin, repository mirror/cache, dependency bị khóa cũ | So sánh `java -version`, wrapper, resolved graph, build sạch |
| Login thành công nhưng sai quyền | Authentication khác authorization, chưa ánh xạ issuer/tenant/role | Test quyền tối thiểu và cross-tenant; không coi mọi IdP claim là tin cậy |

Một mã `401` hay lỗi callback có thể đến từ IdP, proxy, đồng hồ, claim hoặc cấu hình; **không được kết luận “lỗi version” trước khi có dependency tree và log lỗi có cơ sở.**

## 11. Checklist QA trước khi chọn/duyệt tổ hợp phiên bản

**Phiên bản và build**
- [ ] Spring Boot là bản GA được tổ chức hỗ trợ; release notes và security advisory đã được xem.
- [ ] Java runtime/toolchain, Maven/Gradle wrapper và servlet container đạt yêu cầu bản Boot đó.
- [ ] Spring Framework/Security/Crypto/Web/OAuth2/SAML2/Test không trộn major hoặc version lạc BOM.
- [ ] Đã xác minh phiên bản thực trong `dependency:tree` / `dependencyInsight`; lưu SBOM/build metadata.
- [ ] Shibboleth repo được cấu hình khi dùng SAML; Kerberos extension đúng Maven group và version.
- [ ] Không đưa client secret, signing private key, keytab, token hoặc SAML assertion vào log/build output.

**Kiểm tra giao thức**
- [ ] OIDC Authorization Code login hoạt động; callback, issuer, audience, signature, expiry, state/nonce/PKCE đáp ứng đúng luồng.
- [ ] Resource server từ chối access token sai issuer/audience, hết hạn hoặc không đúng scope; không dùng ID Token để gọi API.
- [ ] SAML SP từ chối assertion sai issuer, signature, recipient/audience, hết hạn hoặc replay; thử certificate rotation với đối tác.
- [ ] Kerberos SPNEGO thử trên máy domain-joined và ngoài domain; xử lý đúng lỗi KDC, SPN/keytab, time drift.
- [ ] Vai trò/tenant được ánh xạ từ danh tính tin cậy, không tự cấp quyền vì email/domain trùng nhau.
- [ ] Logout, session timeout, IdP outage, MFA/step-up, reverse proxy HTTPS và rollback được kiểm chứng.

**Chọn phiên bản an toàn còn phụ thuộc hỗ trợ của toàn bộ hệ sinh thái**: Spring Boot có thể compile, nhưng nhà cung cấp IdP, browser, proxy, SDK bên thứ ba hoặc extension chưa hỗ trợ major mới. Chỉ triển khai khi bằng chứng kiểm thử bao phủ các kết nối thực tế quan trọng.

## 12. Bốn tình huống lựa chọn

**A. Web Spring MVC mới + IdP OIDC + Java 21:** Có thể chọn **Boot 4.1.2/Security 7.1.2** qua BOM, starter `webmvc` + `security` + `security-oauth2-client`. Thêm resource server ở API riêng nếu cần; không pin Nimbus thủ công. Đăng ký redirect, kiểm tra JWT/OIDC token và tenant mapping.

**B. Portal B2B SAML đang ở Boot 3.5.16:** Dùng tổ hợp **Security 6.5.11** do BOM quản lý và `spring-security-saml2-service-provider` với Shibboleth repo. Muốn lên Boot 4.1 phải thử SDK, OpenSAML, SAML metadata/ACS/certificate và chuyển starter phù hợp; tránh ghép Security 7 vào Boot 3.5.

**C. Intranet cần Windows Integrated Authentication:** Trên Boot 4.1.2 sử dụng Kerberos group `org.springframework.security` dòng **7.1.2**. Trên Boot 3.5/Security 6.5 dùng extension group cũ dòng 2.x được kiểm tra tương thích. Cả hai đều cần SPN, keytab, domain/browser/KDC đúng; nếu phải phục vụ mobile/Internet, cân nhắc OIDC qua IdP kết nối AD.

**D. Tự xây Authorization Server:** Với Boot 3.5 dùng starter Authorization Server cũ được quản lý ở 1.5.x; Boot 4.1 dùng `spring-boot-starter-security-oauth2-authorization-server` thuộc Spring Security 7. Không cho cả hai thế hệ chung classpath. Một ứng dụng chỉ dùng IdP sẵn có không cần triển khai Authorization Server.

## 13. Tài liệu chính thức để rà soát mỗi lần nâng bản

1. [Spring Boot – các bản ổn định](https://docs.spring.io/spring-boot/) và [System Requirements](https://docs.spring.io/spring-boot/system-requirements.html).
2. [Spring Boot 4.1 – Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.1/appendix/dependency-versions/coordinates.html) và [Spring Boot 3.5 – Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html).
3. [Spring Boot – Build Systems/Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html).
4. [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide).
5. [Spring Security – Getting Spring Security](https://docs.spring.io/spring-security/reference/getting-spring-security.html) và [Migration to 7](https://docs.spring.io/spring-security/reference/7.0/migration/index.html).
6. [Spring Security – SAML2 Service Provider](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html).
7. [Spring Security – Kerberos](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html).
8. [Spring Security – Releases](https://spring.io/projects/spring-security) và [Spring Support Policy](https://spring.io/support).

**Ghi nhớ:** Chọn **Spring Boot branch + patch** trước; dùng **BOM để đồng bộ Spring Security/Framework và thư viện giao thức**; thêm đúng starter theo role; kiểm tra **dependency graph, IdP integration và regression** trước khi công bố tương thích.