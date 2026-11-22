# Tách endpoint đăng xuất cục bộ với endpoint đăng xuất liên kết trong SAML 2.0

> **Module:** Spring Security – federation. **Nhóm:** Đăng xuất SAML2. Bài học hướng dẫn xây hai hành động độc lập: **Local Logout** chỉ kết thúc phiên tại Service Provider (SP), và **SAML Single Logout (SLO)** gửi yêu cầu đến Identity Provider (IdP) để điều phối đăng xuất liên kết. Các ví dụ dùng Java 17, Spring Boot 3.5.x và Spring Security 6.5.x trên Servlet stack.

## 1. Mục tiêu và kiến thức nền

Sau bài học, bạn cần:

1. Phân biệt phiên HTTP/SecurityContext của SP với phiên SSO tại IdP và phiên ở các SP khác.
2. Chỉ đúng **`POST /logout`** (local-only), **`POST /saml2/logout`** (SP/RP-initiated SLO), và **`POST /logout/saml2/slo`** (nhận SAML LogoutRequest/LogoutResponse từ IdP).
3. Giải thích hướng đi của `LogoutRequest`, `LogoutResponse`, `SAMLRequest`, `SAMLResponse`, `InResponseTo`, `NameID` và `SessionIndex`.
4. Tách hai endpoint trong Spring Security DSL, không tự viết controller xóa session rồi giả định đã logout đúng framework.
5. Hiểu điều kiện bật SLO: IdP `SingleLogoutService`, SP signing key, public certificates, metadata, tương quan giao dịch và session repository.
6. Bảo vệ các thao tác người dùng bằng POST/CSRF; xác minh chữ ký và issuer của thông điệp SLO inbound bằng validator chuẩn.
7. Kiểm thử hai hành vi độc lập, xử lý IdP-initiated SLO, timeout, logout một phần và các giới hạn đa thiết bị.
8. Thiết kế nội dung UX không tuyên bố “đã đăng xuất mọi nơi” khi không có bằng chứng.

**Kiến thức đầu vào:** SAML2 login, IdP/SP metadata, `RelyingPartyRegistration`, Spring Security `SecurityFilterChain`, `LogoutFilter`, HTTP POST/redirect, cookie session và CSRF.

## 2. Local Logout và federated logout khác nhau ở đâu?

Giả sử Portal và Payroll cùng sử dụng một IdP để SSO:

~~~text
          IdP: browser SSO session
             /               \
            v                 v
   Portal SP session     Payroll SP session

Đăng xuất local ở Portal:
   Portal session -> bị hủy
   IdP session    -> có thể vẫn sống
   Payroll        -> có thể vẫn đăng nhập

Đăng xuất liên kết từ Portal:
   Portal -> LogoutRequest -> IdP
   IdP có thể kết thúc IdP session
   và yêu cầu các SP tham gia SLO kết thúc phiên.
   Kết quả tùy IdP, SP khác, binding và network.
~~~

| Khía cạnh | Local Logout | SAML Single Logout |
| --- | --- | --- |
| Ai bắt đầu | User ở SP | User ở SP (RP-initiated) hoặc IdP (AP-initiated) |
| Phạm vi tối thiểu | Phiên tại SP hiện tại | Phiên SP và một giao dịch giao thức với IdP |
| Phát `LogoutRequest` | Không | Có, từ SP hoặc từ IdP tùy chiều |
| Đòi IdP có SLO endpoint | Không | Có đối với flow tích hợp theo metadata |
| Đòi SP signing credential | Không bắt buộc riêng cho local logout | Thường cần để ký SLO requests/responses theo policy |
| IdP cookie có bị xóa? | Không | Có thể, theo kết quả/policy IdP |
| Các SP khác có bị logout? | Không mặc nhiên | Chỉ khi các SP tham gia SLO và flow thành công |
| Kết quả user thấy | Trang local-signed-out | Có thể chuyển browser sang IdP rồi quay về SP |
| Rủi ro UX | User có thể login lại ngay nhờ IdP session | SLO partial/timeout không thể hứa mọi app/thiết bị đã out |

**Điểm dễ hiểu nhầm:** Local logout thành công nhưng user bấm `/private` rồi được đăng nhập SAML ngay, không hỏi mật khẩu. Nguyên nhân thường là **phiên SSO tại IdP vẫn còn**; đây không có nghĩa Spring Security không hủy session local.

**Điểm phải nói rõ:** SAML SLO không phải cơ chế thu hồi tất cả API tokens, refresh tokens, session trên mọi thiết bị hoặc mọi ứng dụng không tham gia federation. Đăng xuất toàn tổ chức cần thêm chính sách IdP, device/session management hoặc token revocation riêng.

## 3. Ba loại endpoint và thông điệp

Trong Spring Security 6.5, `saml2Logout` có thể dùng `POST /logout` làm điểm bắt đầu SLO nếu không tách. Để user có hai lựa chọn, cấu hình **hai trigger khác nhau** và **một endpoint giao thức inbound**.

| Endpoint | Chủ thể gửi | Loại request | Chức năng |
| --- | --- | --- | --- |
| **`POST /logout`** | Browser/user, CSRF hợp lệ | Form POST, không có SAML protocol message | Xóa phiên tại SP, không phát LogoutRequest |
| **`POST /saml2/logout`** | Browser/user, CSRF hợp lệ | Form POST | Bắt đầu RP-initiated SLO, tạo/ký LogoutRequest |
| **`POST /logout/saml2/slo`**, parameter `SAMLRequest` | IdP qua browser | SAML LogoutRequest | AP-initiated SLO, SP xác minh trước khi xóa local session |
| **`POST /logout/saml2/slo`**, parameter `SAMLResponse` | IdP qua browser | SAML LogoutResponse | Trả lời request SLO trước đó của SP |
| **`GET /logout`** | Browser | Request trang confirmation | Thường chỉ hiển thị trang xác nhận khi CSRF enabled, không thực hiện logout |

**Đặc biệt:** `/saml2/logout` **không phải** callback để IdP POST SAMLRequest đến SP. Callback SLO mặc định là `/logout/saml2/slo`. Không đặt cả “nút user” và “listener từ IdP” chung một controller tự kiểm tra form parameters.

~~~text
Browser:
  POST /logout + CSRF
       -> LogoutFilter -> local cleanup -> local success page
       -> KHÔNG SAMLRequest

Browser:
  POST /saml2/logout + CSRF
       -> local cleanup + SAML LogoutRequest
       -> IdP SingleLogoutService
       -> IdP SAMLResponse trở về /logout/saml2/slo

IdP:
  SAMLRequest -> POST /logout/saml2/slo
       -> Saml2LogoutRequestFilter
       -> validate -> local cleanup -> SAML LogoutResponse cho IdP
~~~

Nhiều IdP có thể hỗ trợ HTTP-Redirect binding cho SLO (GET với signature query parameters), nhưng ví dụ và các endpoint mặc định Spring Security 6.5 trong bài dùng HTTP-POST. Khi thay binding phải theo khả năng của IdP và phiên bản thư viện; **không** tự biến mọi GET mang `SAMLRequest` thành request đáng tin.

## 4. Local Logout: cơ chế xóa phiên cục bộ

Trong Spring Security Servlet, `LogoutFilter` xử lý action logout qua các `LogoutHandler`. Hành vi mặc định thường bao gồm invalidating HTTP session, xóa `SecurityContextHolder`/`SecurityContextRepository`, dọn CSRF token, remember-me state nếu dùng và phát sự kiện logout; sau đó `LogoutSuccessHandler` quyết định redirect.

### Các bước

1. User đã đăng nhập Portal và có session cookie `JSESSIONID`.
2. Form gửi `POST /logout` cùng CSRF token.
3. Spring Security thực hiện local logout handlers và invalidates session.
4. SP có thể redirect về `/local-signed-out` để giải thích phạm vi.
5. **Không gửi SAML LogoutRequest** đến IdP.
6. Khi user vào lại tài nguyên cần xác thực, SP có thể khởi tạo login SAML mới; nếu IdP cookie vẫn hợp lệ, IdP có thể trả assertion mới ngay.

**Không thay bằng controller đơn giản:**

~~~java
// Ví dụ KHÔNG nên dùng làm toàn bộ cơ chế logout Spring Security:
@PostMapping("/logout")
String wrong(HttpSession session) {
    session.invalidate();
    return "redirect:/";
}
~~~

Đoạn trên chỉ minh họa lỗi thiết kế, không phải phần code nên đưa vào ứng dụng. Nó có thể thiếu cleanup cho SecurityContextRepository, remember-me, CSRF và custom LogoutHandler. Dùng `http.logout(...)`.

### Tại sao local logout hữu ích?

- Người dùng chỉ muốn đóng Portal nhưng vẫn tiếp tục công việc ở Payroll/email đang đăng nhập.
- IdP không hỗ trợ SLO hoặc chưa cấu hình liên thông.
- Ứng dụng muốn giảm gián đoạn các SP khác, hoặc có yêu cầu UX rõ về phạm vi.
- Đóng session local là bước cần có trước khi rời thiết bị dùng chung, **nhưng nếu mục tiêu là IdP logout thì phải chọn SLO**.

**Không nên hiển thị:** “Đăng xuất khỏi tất cả hệ thống thành công” sau local logout. Thông báo nên là “Bạn đã đăng xuất khỏi ứng dụng này; phiên đăng nhập tại nhà cung cấp danh tính có thể vẫn tồn tại.”

## 5. RP-initiated SLO: SP chủ động yêu cầu IdP đăng xuất

RP = Relying Party, tương ứng SP. Khi người dùng đang có `Saml2AuthenticatedPrincipal` và gọi trigger `POST /saml2/logout`:

1. Spring Security thực hiện local logout/cleanup theo cơ chế.
2. `Saml2RelyingPartyInitiatedLogoutSuccessHandler` dùng `Saml2LogoutRequestResolver` để tạo SAML `LogoutRequest`.
3. Request mang `ID`, `Issuer` (SP entity ID), `Destination` (IdP SingleLogoutService), `NameID` và `SessionIndex` phù hợp phiên SAML.
4. SP dùng signing credential của mình ký thông điệp theo binding và IdP policy.
5. Browser chuyển SAMLRequest tới IdP.
6. IdP xác minh SP signer, quyết định logout IdP session và có thể điều phối tới SP khác.
7. IdP có thể trả `LogoutResponse` về `/logout/saml2/slo`.
8. `Saml2LogoutResponseFilter` kiểm chứng response, đặc biệt signer/issuer, destination/status và `InResponseTo` với request đã lưu.

~~~text
Portal:
  POST /saml2/logout
     -> SP LogoutHandler
     -> Saml2LogoutRequestResolver
     -> signed LogoutRequest ID="_lo123"
     -> Browser -> IdP /slo

IdP:
  verify SP signature + session
  close / coordinate sessions
  -> signed LogoutResponse InResponseTo="_lo123"

Portal:
  POST /logout/saml2/slo (SAMLResponse)
  -> Saml2LogoutResponseFilter
  -> validate / correlate / finish flow
~~~

### LogoutRequest mẫu

~~~xml
<samlp:LogoutRequest
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_lo123"
  Version="2.0"
  IssueInstant="2030-01-01T10:00:00Z"
  Destination="https://idp.example.org/slo">
  <saml:Issuer>urn:portal:sp</saml:Issuer>
  <saml:NameID
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
    opaque-user-identifier
  </saml:NameID>
  <samlp:SessionIndex>_idp-session-1</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

Đây là **XML minh họa** chưa có chữ ký và chưa sẵn sàng gửi. `Issuer` ở chiều SP→IdP chính là **SP entity ID**, không phải IdP. `SessionIndex` đến từ `AuthnStatement` của phiên SAML, không phải `JSESSIONID` hoặc internal user ID. Các giá trị phải do framework và registration đáng tin cung cấp.

### LogoutResponse mẫu

~~~xml
<samlp:LogoutResponse
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_lores456"
  InResponseTo="_lo123"
  Version="2.0"
  IssueInstant="2030-01-01T10:00:30Z"
  Destination="https://portal.example.org/logout/saml2/slo">
  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
</samlp:LogoutResponse>
~~~

Đây cũng chỉ là trích đoạn không ký. SP phải verify signature, issuer, destination, correlation và status trước khi tin kết quả. `Status=Success` chưa được kiểm chứng từ browser không chứng minh IdP đã logout xong.

**Không hứa global logout:** Nếu một SP khác không phản hồi, IdP có thể báo `PartialLogout` hoặc hoàn tất trong phạm vi hạn chế. Ngay cả khi IdP xác nhận, các session không tham gia SLO, thiết bị khác hoặc API tokens có thể tồn tại.

## 6. AP/IdP-initiated SLO: listener nhận request từ IdP

Ở chiều ngược lại, IdP phát `LogoutRequest` tới SP SLO endpoint. Với Spring Security 6.5, `Saml2LogoutRequestFilter` tiếp nhận giao thức; nó không phải `LogoutFilter` của user form.

~~~text
IdP
   -> SAMLRequest: LogoutRequest đã ký
   -> Browser POST /logout/saml2/slo
   -> Saml2LogoutRequestFilter
       * Resolve registration đã phê duyệt
       * Verify IdP signing key
       * Validate Issuer, Destination, subject/NameID,
         SessionIndex, thời gian và policy có liên quan
       * Logout local session tương ứng nếu request hợp lệ
       * Tạo/ký LogoutResponse gửi lại IdP
~~~

**Ranh giới an toàn:** Không chỉ nhìn thấy parameter `SAMLRequest` rồi gọi `session.invalidate()`. Tên parameter có thể do attacker gửi. Chỉ xử lý sau khi SAML protocol validator kiểm tra issuer/signature, message destination và session context. Nếu signature sai, request từ IdP không đáng tin hoặc session không khớp, phải từ chối chứ không logout nhầm user.

### Vì sao cần inbound endpoint riêng?

- **User trigger** `/saml2/logout` cần principal đã đăng nhập để biết IdP/SP registration và phiên SAML.
- **Protocol listener** `/logout/saml2/slo` phải nhận cả `LogoutRequest` AP-initiated lẫn `LogoutResponse` phản hồi request trước đó, có thể sau khi local session đã bị hủy.
- **Local trigger** `/logout` làm cleanup không gửi giao thức.

Nếu gộp cả ba vào một MVC endpoint, dễ gặp CSRF mismatch, filter order collision, bỏ SAML signature validation, mất correlation hoặc vòng lặp logout.

## 7. Cấu hình phân tách trong Spring Security

Điểm cốt lõi, được Spring Security 6.5 mô tả trực tiếp:

~~~java
http
    .logout(logout -> logout.logoutUrl("/logout"))
    .saml2Logout(saml -> saml.logoutUrl("/saml2/logout"));
~~~

Khi cấu hình này hoạt động:

- `POST /logout`: chỉ local session cleanup.
- `POST /saml2/logout`: RP-initiated SLO (nếu principal và registration hỗ trợ).
- `POST /logout/saml2/slo` với protocol message: do SAML SLO filters xử lý theo metadata/registration.

**Mặc định nếu không tách:** Khi bật `saml2Logout`, `POST /logout` có thể trigger SLO cho principal SAML. Nếu UI cần hai lựa chọn đúng nghĩa, **không thể chỉ đổi nhãn nút**; phải đặt URI khác nhau trong DSL.

### 7.1. Mức độ cần thiết của signing keys và metadata

Để SLO thực sự chạy:

1. IdP metadata công bố `SingleLogoutService` với binding/Location hỗ trợ.
2. SP có signing private key PKCS#8 và X.509 public certificate tương ứng để ký SLO messages.
3. IdP đã đăng ký SP signing certificate và SP SLO callback.
4. SP tin public verification cert của IdP từ metadata đáng tin.
5. Cặp SP entity ID/IdP entity ID, NameID/SessionIndex và binding thống nhất.
6. Browser/request repository có thể giữ correlation của LogoutRequest/LogoutResponse khi cần.

**Đăng nhập SAML thành công không đồng nghĩa SLO được hỗ trợ.** Thiếu SingleLogoutService hoặc key/metadata không khớp thì nút federated logout không được quảng cáo là tính năng đang hoạt động. Local logout vẫn nên được duy trì như hành động riêng.

## 8. Spring Boot 3.5.x: project Java 17 có hai nút logout

Project demo dùng Spring MVC + Thymeleaf tạo **hai POST forms**. Spring Security xử lý logout ở filter, không cần `@PostMapping` tùy biến. Chỉ có thể thử SSO/SLO thật sau khi có IdP sandbox hỗ trợ Single Logout và SP credentials.

Cấu trúc:

~~~text
saml-logout-demo/
  pom.xml
  src/main/java/demo/SamlLogoutApplication.java
  src/main/resources/application.yml
  src/main/resources/templates/index.html
  src/main/resources/templates/local-signed-out.html
~~~

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>saml-logout-demo</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
  <repositories>
    <repository>
      <id>shibboleth-releases</id>
      <url>https://build.shibboleth.net/maven/releases</url>
      <snapshots><enabled>false</enabled></snapshots>
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
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-thymeleaf</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-saml2-service-provider</artifactId>
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
~~~

### 8.2. application.yml

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
            signing:
              credentials:
                - private-key-location: file:/run/secrets/sp-signing.key
                  certificate-location: file:/run/secrets/sp-signing.crt
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
~~~

Giải thích:

- `metadata-uri` chỉ **IdP metadata được phê duyệt**, cần công bố `SingleLogoutService` và public verification certificate.
- `signing.credentials` là **SP private signing key + SP public certificate**; không phải private key IdP. Lưu private key qua secret manager hoặc read-only mount với quyền hạn chế, không commit vào Git.
- `singlelogout.url` chỉ **callback SP** nhận protocol messages `/logout/saml2/slo`. Đây **không phải** nút user bắt đầu SLO.
- `{baseUrl}` phải dùng public scheme/host/path chính xác sau proxy; kiểm tra metadata do SP công bố tại địa chỉ production.
- IdP phải biết SP entity ID, ACS, SLO endpoint và SP signing cert, có binding tương thích. Không thể đăng nhập với URL minh họa chưa hoạt động.

Spring Boot có thể đọc credential PEM theo format phù hợp; private key thường cần là PKCS#8. Nếu file đang ở PKCS#1/encrypted PEM hoặc keystore có passphrase, phải xác định loader/provider tương ứng thay vì copy plaintext vào application.yml.

### 8.3. SamlLogoutApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@SpringBootApplication
public class SamlLogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlLogoutApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/local-signed-out", "/error")
                            .permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .logoutSuccessUrl("/local-signed-out")
                        .permitAll())
                .saml2Logout(saml -> saml
                        .logoutUrl("/saml2/logout"))
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }

    @Controller
    static class Pages {
        @GetMapping("/")
        String index() {
            return "index";
        }

        @GetMapping("/local-signed-out")
        String localSignedOut() {
            return "local-signed-out";
        }
    }
}
~~~

`SecurityFilterChain` sử dụng **hai logout configurers** với URI khác nhau. `.logout(...)` xử lý local cleanup; `.saml2Logout(...)` kích hoạt RP SLO cho SAML principal; endpoint inbound là trách nhiệm của SAML filters. Controller chỉ render hai trang public, **không thực hiện logic logout**.

### 8.4. templates/index.html

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>SAML Logout</title>
</head>
<body>
  <h1>Chọn phạm vi đăng xuất</h1>

  <form th:action="@{/logout}" method="post">
    <button type="submit">Đăng xuất khỏi ứng dụng này</button>
  </form>
  <p>Phiên đăng nhập IdP và các ứng dụng khác có thể vẫn tồn tại.</p>

  <form th:action="@{/saml2/logout}" method="post">
    <button type="submit">Yêu cầu đăng xuất liên kết</button>
  </form>
  <p>Kết quả tại ứng dụng khác phụ thuộc hỗ trợ Single Logout.</p>
</body>
</html>
~~~

Với Thymeleaf/Spring Security integration, POST form có `th:action` được tích hợp CSRF token theo cơ chế framework. **Kiểm tra HTML render thực tế** xem có hidden `_csrf` field; nếu dùng SPA/fetch, phải lấy và gửi token đúng cách. Không hardcode CSRF token vào HTML, không tắt CSRF để sửa lỗi form.

### 8.5. templates/local-signed-out.html

~~~html
<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Đã đăng xuất cục bộ</title>
</head>
<body>
  <h1>Đã đăng xuất khỏi ứng dụng này</h1>
  <p>
    Phiên tại nhà cung cấp danh tính có thể vẫn đang hoạt động.
    Nếu truy cập lại ứng dụng, bạn có thể được SSO ngay
    mà không cần nhập lại mật khẩu.
  </p>
  <a href="/">Về trang chủ</a>
</body>
</html>
~~~

Không tự redirect từ trang này đến tài nguyên bảo vệ, nếu không user sẽ được SSO lại ngay và tưởng local logout thất bại. Trang cũng không đưa ra lời hứa “đăng xuất mọi nơi”.

### 8.6. Chạy và kiểm thử

Sau khi cung cấp metadata/credentials thật của IdP sandbox:

~~~bash
mvn spring-boot:run
~~~

Mở `http://localhost:8080/` để xem hai nút. Với IdP test đã đăng ký ứng dụng, login và quan sát network:

- **Local:** `POST /logout` → local success page, không phát SAML LogoutRequest.
- **Federated:** `POST /saml2/logout` → Spring tạo SAMLRequest và chuyển browser tới IdP SingleLogoutService, có thể nhận callback tại `/logout/saml2/slo`.
- **IdP-initiated:** IdP gửi signed LogoutRequest tới SP inbound endpoint, Spring verify rồi dọn session phù hợp và trả LogoutResponse.

Không có stdout/login response cố định cho SLO vì HTTP redirect, binding và IdP policy khác nhau. Không nói demo đã tích hợp SLO khi chưa thử với IdP thật.

## 9. CSRF, SameSite cookies và vòng đời session

**Form user:** Cả local và RP-initiated triggers nên là POST kèm CSRF token. `GET /logout` với CSRF enabled thường là trang xác nhận chứ không trực tiếp logout; đây là đặc tính an toàn, không phải lỗi routing. Một attacker không nên có thể khiến user logout bằng cách nhúng image hoặc GET link.

**SAML inbound:** IdP không có CSRF token của form SP. Spring SAML logout filters phải xử lý binding và validate signed SAML messages. Đừng dùng `csrf.disable()` cho cả ứng dụng hoặc cho `/logout/**` rộng quá mức; chỉ thêm ngoại lệ chính xác nếu cấu hình phiên bản yêu cầu và có kiểm tra SAML thay thế.

**Cookie:** SP `JSESSIONID` và IdP SSO cookie thuộc domain khác nhau. SP không thể trực tiếp xóa IdP cookie bằng một Set-Cookie cho domain SP. Cần SLO protocol hoặc IdP logout flow. `SameSite`, `Secure`, browser privacy restrictions và cross-site POST có thể ảnh hưởng callback; test bằng browser thực trên public HTTPS hostname.

**Session cleanup:** Spring `LogoutFilter` + handlers có thể invalidate session và xóa SecurityContext. Nếu app lưu extra user state (caches, WebSocket, shopping cart, remember-me), phải quyết định cleanup riêng. Không tự xóa repository chứa `LogoutRequest` cần cho `InResponseTo` trước khi callback; để framework quản lý lifecycle hoặc sử dụng repository tương thích cluster.

**Cluster:** SP phát request ở node A, IdP response về node B. Cần session/request repository chung, hoặc routing hợp lệ; không giải quyết lỗi bằng cách bỏ validation LogoutResponse. Khi dùng Spring Session, kiểm tra cách lưu và truy hồi SLO requests ở phiên bản thực.

## 10. InResponseTo, NameID, SessionIndex và sự khác nhau với login

| Trường SAML | Nơi xuất hiện | Ý nghĩa |
| --- | --- | --- |
| `LogoutRequest/ID` | Request logout | Unique message ID để correlating response |
| `LogoutResponse/InResponseTo` | Response logout | Trỏ về LogoutRequest ID ban đầu |
| `LogoutRequest/Issuer` | Message bên khởi tạo phát | SP entity ID khi RP-initiated; IdP entity ID khi AP-initiated |
| `LogoutRequest/Destination` | Message logout | URI SLO endpoint của bên nhận |
| `LogoutRequest/NameID` | Message logout | Subject trong namespace SAML, không phải app user ID |
| `LogoutRequest/SessionIndex` | Request logout | IdP session index từ AuthnStatement khi có |
| `LogoutResponse/Status` | Response logout | Success, PartialLogout hoặc lỗi theo SAML |
| `RelayState` | HTTP binding | Hỗ trợ state/correlation; không phải bằng chứng xác thực riêng |

**SAMLResponse của SLO khác SAMLResponse của login:** Có thể cùng tên HTTP form parameter `SAMLResponse`, nhưng XML SLO là `samlp:LogoutResponse`, còn login là `samlp:Response` chứa Assertion. Endpoint SLO khác ACS login. Không đưa `LogoutResponse` qua `Saml2WebSsoAuthenticationFilter`.

**Validation:** Với LogoutResponse, signature/issuer/destination/status cùng `InResponseTo` phải hợp lệ; `Status=Success` đơn lẻ không đủ. Với LogoutRequest inbound, chữ ký IdP và đúng principal/session là điều kiện quan trọng trước khi logout local.

## 11. Java 17 độc lập: nhận diện loại endpoint

Chương trình này chỉ mô phỏng **phân loại route**, không xử lý SAML thật và **không xác thực một LogoutRequest**. Dùng để thấy ba endpoint có nhiệm vụ khác nhau.

**LogoutRouteDemo.java:**

~~~java
public class LogoutRouteDemo {
    enum Action {
        LOCAL_ONLY,
        RP_SLO,
        INBOUND_REQUEST,
        INBOUND_RESPONSE,
        NO_MATCH
    }

    static Action classify(String method, String path, String formKey) {
        if (!"POST".equals(method)) {
            return Action.NO_MATCH;
        }
        return switch (path) {
            case "/logout" -> Action.LOCAL_ONLY;
            case "/saml2/logout" -> Action.RP_SLO;
            case "/logout/saml2/slo" -> switch (formKey) {
                case "SAMLRequest" -> Action.INBOUND_REQUEST;
                case "SAMLResponse" -> Action.INBOUND_RESPONSE;
                default -> Action.NO_MATCH;
            };
            default -> Action.NO_MATCH;
        };
    }

    static void show(String label, Action action) {
        System.out.println(label + " -> " + action);
    }

    public static void main(String[] args) {
        show("POST /logout", classify("POST", "/logout", ""));
        show("POST /saml2/logout",
                classify("POST", "/saml2/logout", ""));
        show("POST /logout/saml2/slo [SAMLRequest]",
                classify("POST", "/logout/saml2/slo", "SAMLRequest"));
        show("POST /logout/saml2/slo [SAMLResponse]",
                classify("POST", "/logout/saml2/slo", "SAMLResponse"));
        show("GET /logout", classify("GET", "/logout", ""));
        show("POST /logout/saml2/slo [none]",
                classify("POST", "/logout/saml2/slo", ""));
    }
}
~~~

Biên dịch/chạy với Java 17+:

~~~bash
javac LogoutRouteDemo.java
java LogoutRouteDemo
~~~

**Stdout chính xác:**

~~~text
POST /logout -> LOCAL_ONLY
POST /saml2/logout -> RP_SLO
POST /logout/saml2/slo [SAMLRequest] -> INBOUND_REQUEST
POST /logout/saml2/slo [SAMLResponse] -> INBOUND_RESPONSE
GET /logout -> NO_MATCH
POST /logout/saml2/slo [none] -> NO_MATCH
~~~

Trong Spring Security thực, `GET /logout` có thể hiển thị confirmation page; `NO_MATCH` trong ví dụ nghĩa **không phải một hành động logout bằng POST**. Và một inbound SAMLRequest giả mạo cũng sẽ được chương trình nhận diện là `INBOUND_REQUEST`, nhưng phải bị Spring Security từ chối vì chữ ký/issuer invalid. Đây chỉ là phép phân loại đường đi, không phải implementation dùng ở production.

## 12. Trường hợp bất thường và cách ứng xử đúng

### 12.1. User local logout xong mới bấm federated logout

Sau local logout, SP đã mất principal/session SAML mà SLO request resolver có thể cần để xác định IdP, NameID và SessionIndex. Không giả định có thể gọi `/saml2/logout` sau đó để lấy lại ngữ cảnh cũ. Nếu user cần federated SLO, họ nên **chọn nút federated khi session còn đang xác thực**. Nếu đã mất session, có thể phải đi qua quy trình IdP logout riêng hoặc policy thích hợp.

### 12.2. Multi-IdP và nhiều tenant

Portal có IdP A và B. Khi user A bắt đầu SLO, SP phải dựa vào `Saml2AuthenticatedPrincipal` và **trusted RelyingPartyRegistration** liên quan để chọn IdP A SLO service. Không tin query parameter `?idp=https://...` do user nhập để gửi logout messages; có thể thành open redirect, SSRF hoặc IdP mix-up. Mỗi đối tác cần signing/verification keys và metadata đúng.

### 12.3. IdP thiếu SLO support

Nếu metadata không có `SingleLogoutService` hoặc đối tác không hỗ trợ signing/binding, giữ Local Logout hoạt động và **ẩn/disable nút federated** nếu không thể thực hiện. Nếu cần, hướng dẫn user đăng xuất tại cổng IdP được phê duyệt; đây không phải cùng một SLO guarantee.

### 12.4. IdP trả PartialLogout hoặc không phản hồi

SP có thể đã xóa session local trước khi IdP hoàn tất. Không được tuyên bố “mọi nơi đã đăng xuất” vì chỉ có redirect sang IdP hoặc vì local cookie đã mất. UX nên giải thích “phiên ứng dụng này đã được kết thúc; chưa xác nhận tất cả phiên SSO đã đóng”. Ghi lỗi/status theo mức tối thiểu và cung cấp hướng dẫn sử dụng thiết bị dùng chung.

### 12.5. IdP-initiated LogoutRequest không hợp lệ

Không xóa session user chỉ vì có parameter `SAMLRequest`. Hãy để `Saml2LogoutRequestFilter` kiểm tra signature, issuer, destination, NameID/SessionIndex và policy phù hợp trước khi gọi LogoutHandlers. Tránh tự cài controller `@PostMapping("/logout/saml2/slo")` parse XML bằng DOM/XPath rồi invalidates session.

### 12.6. API tokens tồn tại sau SLO

SAML SLO điều phối browser SSO sessions; REST API Bearer token, refresh token, service-to-service credentials hoặc mobile sessions là những loại state riêng. Nếu phải thu hồi khi user logout hoặc bị offboard, thiết kế token revocation/introspection, session registry hoặc policy tại API gateway/authorization server riêng.

## 13. Ma trận kiểm thử trước khi go-live

| Ca kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| POST `/logout` có CSRF hợp lệ | Xóa local session; không phát SAMLRequest |
| POST `/saml2/logout` có CSRF hợp lệ + SAML principal | Tạo/ký LogoutRequest tới IdP SLO endpoint |
| GET `/logout` khi CSRF bật | Không trực tiếp thực hiện logout |
| POST local không có CSRF | Request bị từ chối, không logout tùy tiện |
| POST federated không có CSRF | Không bắt đầu SLO |
| Local logout xong login lại ngay do IdP cookie | Có thể SSO tự động; không coi là lỗi local logout |
| SLO LogoutResponse signed hợp lệ và InResponseTo khớp | SP xác minh và hoàn tất flow |
| SLO LogoutResponse sai issuer hoặc InResponseTo | Từ chối/không báo complete |
| IdP-initiated signed LogoutRequest hợp lệ | SP logout đúng session và gửi LogoutResponse |
| IdP-initiated unsigned/bad signature LogoutRequest | Từ chối, không xóa session người khác |
| IdP không hỗ trợ `SingleLogoutService` | Local vẫn dùng được; SLO không được quảng cáo là pass |
| IdP chưa tin SP signing cert mới | IdP từ chối RP-initiated request; kiểm certificate rotation |
| IdP trả `PartialLogout` | Không tuyên bố logout mọi ứng dụng |
| IdP timeout hoặc user đóng tab khi đang SLO | Local/session state và UX thể hiện kết quả chưa rõ |
| SAMLRequest gửi vào `/logout` | Không được xử lý như protocol SLO |
| SAMLResponse SLO gửi vào login ACS | Không được xử lý như authentication assertion |
| SP cluster node B nhận callback sau khi node A phát request | Repository/correlation hoạt động hoặc fail an toàn |
| Một browser đăng xuất SLO | Không mặc nhiên suy luận mọi thiết bị đã logout |
| User không phải SAML principal gọi `/saml2/logout` | Không tự chọn IdP tùy ý để phát LogoutRequest |
| Trang local-signed-out được bảo vệ nhầm | Fix permitAll để không auto SSO lại khi render |
| Role/user status thay sau logout | Authorization luôn kiểm theo app policy; logout không đồng nghĩa role revocation |

**Kiểm chứng bằng nhiều lớp:** UI/route test kiểm hai POST actions; Spring MVC/MockMvc kiểm CSRF và session cleanup; IdP sandbox integration test kiểm **signed SAML LogoutRequest/LogoutResponse**, issuer/destination/InResponseTo và NameID/SessionIndex; browser E2E kiểm cookie/SameSite/proxy/callback; multi-node test kiểm repository.

Để test đúng SLO signature/issuer validator, dùng IdP test phát **message có chữ ký hợp lệ nhưng điều kiện khác sai**. Nếu sửa XML sau khi ký, failure đầu tiên là signature; test đó không nhất thiết chứng minh validator correlation/destination.

### Nguyên tắc log

Ghi event type (LOCAL, RP_SLO, AP_SLO, SLO_RESPONSE), registrationId, correlation ID đã được kiểm soát, thời gian, status/error code. Tránh log raw XML, SAMLRequest/SAMLResponse, NameID, session cookies, signing private keys và dữ liệu cá nhân. Thu thập SAML tracer chỉ ở test, mask rồi xóa dữ liệu theo retention policy.

## 14. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Bấm local mà redirect sang IdP | `saml2Logout` vẫn dùng `POST /logout` mặc định | Tách `.logout(...)` và `.saml2Logout(...logoutUrl(...))` |
| Local logout xong login lại không cần mật khẩu | IdP session vẫn còn | Giải thích UX, dùng SLO/reauth khi cần |
| Bấm federated nhưng không có SAMLRequest | Sai form action, principal không phải SAML, thiếu SLO capability | Kiểm URI/registration/IdP metadata |
| CSRF 403 | Form không gửi token | Dùng Thymeleaf `th:action`/framework token handling |
| IdP từ chối LogoutRequest | Signing key/cert sai, binding không hỗ trợ, issuer/NameID/SessionIndex lệch | Đối chiếu SP metadata, IdP logs, key rotation |
| SP nhận SLO nhưng trả 400 | Invalid LogoutRequest signature/issuer/destination/session | Điều tra validator; không bỏ kiểm tra |
| LogoutResponse callback không match | Mất `InResponseTo`, RelayState hoặc request repository | Kiểm session cookie, cluster store và IdP response |
| SLO callback vào sai URL | `singlelogout.url`/proxy/metadata sai | Cấu hình đúng public HTTPS SLO endpoint |
| Bị login loop trên local-signed-out | Trang logout success bị bảo vệ | Cho phép trang success public |
| IdP SLO thành công nhưng Payroll vẫn login | Payroll không tham gia SLO hoặc phiên khác tồn tại | Kiểm khả năng SLO, không hứa universal logout |
| HTTP response thành công nhưng vẫn lỗi SLO | 302 chỉ là bước chuyển browser | Kiểm LogoutResponse và status đã verify |
| User logout SAML nhưng API token vẫn chạy | Token có vòng đời riêng | Token revocation/session management riêng |
| Lỗi chỉ một node | Session repository hoặc keys không đồng nhất | Shared session, deployment config, signing certs |

**Không sửa bằng cách** tắt CSRF cho cả ứng dụng, cho phép GET logout, bỏ signature verification, trust arbitrary public key từ SAML message, hay chấp nhận LogoutResponse không có correlation.

## 15. Quyết định UX và vận hành

**Nên chọn Local Logout** khi người dùng chỉ muốn kết thúc công việc ở một ứng dụng, SLO không được đối tác hỗ trợ, hoặc hệ thống muốn tránh đóng các SP khác ngoài ý muốn. Nút nên ghi “Đăng xuất khỏi ứng dụng này”.

**Nên cung cấp Federated SLO** khi có SLO được IdP/SP hỗ trợ, người dùng cần yêu cầu kết thúc phiên SSO liên kết, đặc biệt trên thiết bị dùng chung; tổ chức có kế hoạch xử lý PartialLogout và IdP timeout. Nút nên ghi “Yêu cầu đăng xuất liên kết”, không ghi “Đăng xuất mọi nơi chắc chắn”.

Sau **local success**, thông báo: “Phiên tại ứng dụng này đã kết thúc; phiên tại nhà cung cấp danh tính và ứng dụng khác có thể vẫn hoạt động.”

Khi **federated response không xác minh được**, không hiển thị thông báo global success. Có thể thông báo rằng ứng dụng đã kết thúc phiên local nhưng chưa xác nhận toàn bộ liên kết, kèm hướng dẫn truy cập IdP logout chính thức.

Sau **AP-initiated SLO**, browser thường quay lại IdP theo LogoutResponse, nên không chắc trang success của SP được render. Thiết kế UX không phụ thuộc vào một callback HTML local ở nhánh này.

**Operational checklist:**

- [ ] IdP metadata có `SingleLogoutService`; SP signing certificate được IdP tin.
- [ ] Public SP SLO endpoint `/logout/saml2/slo` đúng binding, scheme, host và path.
- [ ] Hai trigger user là **POST /logout** và **POST /saml2/logout**, không trùng URI.
- [ ] Form POST mang CSRF token; inbound SAML message do protocol validator kiểm tra.
- [ ] LogoutRequest/Response được ký/xác minh theo policy.
- [ ] LogoutResponse có `InResponseTo` tương quan request đã gửi.
- [ ] Cluster/session repository không làm mất state giữa các node.
- [ ] Local logout không phát `LogoutRequest`; federated logout có phát khi đủ điều kiện.
- [ ] Có negative tests cho signature/issuer/destination/status và unauthorized request.
- [ ] Trang success phân biệt “local” với trạng thái federation.
- [ ] Không hứa thu hồi mọi thiết bị, application session hoặc API token chỉ nhờ SAML SLO.
- [ ] Có monitoring, runbook IdP timeout/PartialLogout và rotation certificates.

## 16. Bài tập và tiêu chí đạt

**Bài A – vẽ ba đường đi:** Vẽ riêng local `POST /logout`, RP-initiated `POST /saml2/logout` và AP-initiated `POST /logout/saml2/slo`. Ghi thành phần Spring Security xử lý mỗi nhánh.

**Bài B – cấu hình:** Tạo project mục 8 với IdP SAML sandbox có SingleLogoutService. Cho hai form render đúng CSRF. Chứng minh bấm local không gửi SAMLRequest và bấm federated có signed LogoutRequest.

**Bài C – Java:** Chạy `LogoutRouteDemo.java`, đối chiếu 6 dòng stdout và giải thích vì sao route matcher không đủ để xác thực một inbound SAMLRequest.

**Bài D – IdP-initiated:** Từ IdP test, gửi LogoutRequest ký hợp lệ, quan sát SP dọn session và gửi LogoutResponse. Gửi request giả mạo và xác minh SP từ chối.

**Bài E – correlation:** Đổi `InResponseTo` trong LogoutResponse test thành ID khác theo cách IdP test ký lại; SP phải từ chối. Kiểm tra nơi lưu LogoutRequest khi session bị invalidated.

**Bài F – UX:** Viết hai thông báo khác nhau cho local success và federated PartialLogout, tránh hứa mọi ứng dụng đã out.

**Bài G – multi-IdP:** Nếu một ứng dụng có IdP A/B, hãy lý giải vì sao SP phải chọn IdP từ authenticated principal/registration thay vì query parameter tự do.

**Đạt bài** khi hiểu đúng phạm vi logout, tách hai trigger và protocol listener bằng Spring DSL, bảo vệ POST/CSRF, tích hợp signed SAML SLO bằng metadata/certificates và kiểm thử được local, RP-initiated, AP-initiated cùng failure cases.

## 17. Nguồn tham khảo chính thức

- Spring Security **6.5** – Performing Single Logout, đặc biệt “Separating Local Logout from SAML 2.0 Logout”: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html
- Spring Security 6.5 – Handling Logouts: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security – SAML 2.0 Logout reference (cần đối chiếu version): https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Security – SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – SAML Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Boot 3.5 – SAML Relying Party: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- OASIS SAML 2.0 Core – Single Logout Protocol: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles – Single Logout: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS SAML 2.0 Metadata – SingleLogoutService: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
