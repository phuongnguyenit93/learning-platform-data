# Kiểm thử RP-initiated SLO, IdP-initiated SLO và đăng xuất cục bộ

> **Module:** Spring Security – federation. **Nhóm:** Kiểm thử SAML2. Bài học xây dựng bộ kiểm thử cho ba hành vi logout: **Local Logout**, **RP-initiated SAML Single Logout** và **IdP/AP-initiated SAML Single Logout**, cùng callback **LogoutResponse**. Ví dụ dùng Java 17, Spring Boot 3.5.x và Spring Security 6.5.x trên Servlet stack. Tất cả Entity ID, URL và chứng thư trong ví dụ là fixture sandbox; không dùng tài khoản hoặc khóa ký production.

## 1. Mục tiêu

Sau khi học, bạn có thể:

1. Phân biệt session HTTP/SecurityContext của Service Provider (SP), session SSO của Identity Provider (IdP) và session ở SP thứ hai.
2. Chỉ đúng endpoint cho local logout, RP-initiated user trigger, IdP-initiated LogoutRequest và IdP LogoutResponse callback.
3. Kiểm rằng local logout xóa session nhưng không phát SAML LogoutRequest; RP flow phát signed LogoutRequest đến IdP; IdP flow xác minh inbound trước khi xóa session.
4. Thiết kế negative tests cho chữ ký, Issuer, Destination, NameID/Format, SessionIndex, InResponseTo, RelayState, Status, replay và CSRF.
5. Phân biệt HTTP transport success, SAML protocol result và thực tế user/IdP/other-SP sessions có bị xóa không.
6. Cấu hình Spring Security SAML2 với hai nút logout riêng; biết vai trò của LogoutFilter, Saml2LogoutRequestFilter, Saml2LogoutResponseFilter và LogoutRequestRepository.
7. Chạy chương trình Java 17 mô phỏng oracle test với stdout chính xác; hiểu rằng test mật mã cần IdP sandbox có signed fixtures.
8. Kiểm browser cookie SameSite, reverse proxy/HTTPS, IdP timeout, PartialLogout, callback qua nhiều node và multi-session.
9. Thu thập bằng chứng QA an toàn, tránh lưu private keys, raw SAML XML, NameID và bearer cookies.

**Kiến thức đầu vào:** SAML 2.0 Web Browser SSO, RelyingPartyRegistration, SAML Assertion, NameID/SessionIndex, logout messages, XML Signature, HTTP-POST/Redirect binding, Java Servlet session, CSRF, Spring SecurityFilterChain.

## 2. Kiến trúc và phạm vi logout

~~~text
                  IdP SSO session
                    /        \
                   v          v
             Portal SP     Reports SP
             JSESSIONID    session riêng

Local:
 Browser --POST /logout + CSRF--> Portal
 Portal dọn session của chính mình
 IdP và Reports không mặc nhiên bị logout

RP-initiated:
 Browser --POST /saml2/logout + CSRF--> Portal
 Portal dọn local, gửi signed LogoutRequest tới IdP
 IdP xử lý SSO/SLO, có thể điều phối Reports
 IdP có thể trả signed LogoutResponse cho Portal

IdP-initiated:
 IdP --signed LogoutRequest--> Portal SLO listener
 Portal verify, dọn session phù hợp, gửi LogoutResponse cho IdP
~~~

| Luồng | Tác nhân khởi đầu | SAML traffic | Pass tối thiểu | Không được tự kết luận |
| --- | --- | --- | --- | --- |
| Local | User tại Portal | **Không** LogoutRequest tới IdP | Session/SecurityContext Portal invalidated | IdP/Reports đã logout |
| RP SLO | User tại Portal | Portal gửi LogoutRequest, có thể nhận LogoutResponse | Outbound request signed/đúng IdP; local cleanup; inbound response verify nếu có | Mọi thiết bị/API token đã revoked |
| IdP SLO | IdP | IdP gửi LogoutRequest, Portal gửi LogoutResponse | Verify inbound rồi logout đúng phiên | Bất kỳ người dùng cùng NameID đã logout mọi nơi |
| Callback RP | IdP phản hồi request SP | IdP gửi LogoutResponse | Verify signer/issuer/destination/status/InResponseTo | Response chỉ có HTTP 200 là success |

**Điểm hay gây nhầm:** Local logout thành công mà user truy cập lại Portal và được SSO ngay, vì **IdP session vẫn tồn tại**. Đó có thể là **một session Portal mới**, không phải session cũ còn sống. Test phải kiểm session fingerprint và việc phát Assertion mới, không chỉ xem user có phải nhập lại password hay không.

## 3. Endpoint contract trong Spring Security 6.5

Nếu chỉ gọi SAML logout mặc định, `POST /logout` của SAML principal có thể khởi tạo RP SLO. Muốn local và federated độc lập, cần cấu hình **hai user-trigger endpoints khác nhau**:

~~~java
http
    .logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/local-signed-out"))
    .saml2Logout(saml -> saml
        .logoutUrl("/saml2/logout"));
~~~

| Endpoint | Ai gửi | Input | Thành phần Spring | Assertion |
| --- | --- | --- | --- | --- |
| `POST /logout` | Browser/user | Form POST + CSRF | LogoutFilter, LogoutHandlers | Chỉ local cleanup, không SAMLRequest |
| `POST /saml2/logout` | Browser/user SAML | Form POST + CSRF | Saml2RelyingPartyInitiatedLogoutSuccessHandler | Phát LogoutRequest tới IdP |
| `POST /logout/saml2/slo` | IdP | Form field `SAMLRequest` | Saml2LogoutRequestFilter | Valid signed LogoutRequest rồi logout local |
| `POST /logout/saml2/slo` | IdP | Form field `SAMLResponse` | Saml2LogoutResponseFilter | Valid signed LogoutResponse + correlation |
| `GET /logout` | Browser | GET | Logout confirmation (khi CSRF bật) | Không thực hiện logout trực tiếp |
| `GET /saml2/logout` | Browser | GET | Không phải POST RP trigger | Không phát LogoutRequest |

**Ghi chú binding:** Với HTTP-POST, `SAMLRequest`/`SAMLResponse` là form parameters, **không** phải query parameters. Với HTTP-Redirect, chữ ký có thể ở query fields `SigAlg`/`Signature`, cần verify binding-specific signature, không chỉ nhìn `ds:Signature` trong XML. Bài dùng HTTP-POST fixture; chỉ mở GET SLO nếu IdP/SP đã thống nhất Redirect binding và validator tương ứng.

**Tách callback khỏi nút:** `/saml2/logout` dùng để user khởi tạo RP SLO; `/logout/saml2/slo` là protocol listener. Không cài controller tự xóa session khi thấy parameter `SAMLRequest` mà bỏ SAML validators.

## 4. Fixture test và tiền điều kiện

Mô hình sandbox:

~~~text
Browser QA -> Portal Spring Security 6.5
  https://portal.test.example.org
  SP Entity ID: urn:portal:test:sp
  registrationId: corporate
  ACS: /login/saml2/sso/corporate
  SLO callback: /logout/saml2/slo

Test IdP
  https://idp.test.example.org
  IdP Entity ID: https://idp.test.example.org/saml
  SingleLogoutService: https://idp.test.example.org/slo
  Signing private key chỉ dùng trong lab
  Public verification certificate công bố trong trusted metadata

Reports SP (tùy chọn)
  https://reports.test.example.org
  Có session riêng và tham gia SLO nếu IdP hỗ trợ

QA user: opaque-user-17
NameIDFormat: persistent
SessionIndex: _idp-session-17
Binding: HTTP-POST
~~~

| Chuẩn bị | Tại sao phải có? |
| --- | --- |
| IdP metadata có `SingleLogoutService`/binding/location | Login SAML được không đồng nghĩa IdP hỗ trợ SLO |
| SP PKCS#8 signing private key + X.509 certificate | IdP cần verify signed LogoutRequest/LogoutResponse |
| SP trust IdP signer public cert qua metadata đã phê duyệt | SP verify inbound SAML messages |
| SP entity ID, ACS và SLO callback public HTTPS | Destination/Recipient/service URLs phải đúng |
| Principal thực sự từ SAML login | RP resolver cần correct registration/NameID/session |
| NameIDFormat, SessionIndex từ Assertion/IdP | Kiểm logout đúng user/SSO session theo profile |
| Saml2LogoutRequestRepository và browser session | Giữ request ID/RelayState cho InResponseTo |
| Đồng hồ đồng bộ, test user và signing cert riêng | Tránh false negative clock; cô lập secrets |
| HTTPS browser, SameSite/Secure, reverse proxy | Callback có thể mất cookie/state |
| IdP có khả năng chủ động ký invalid-case fixture | Kiểm độc lập validator thay vì phá chữ ký sau khi ký |

**Không log raw SAMLRequest/SAMLResponse, cookies hay NameID của người thật.** Dùng test identities, certificate alias và ID fingerprints khi điều tra.

## 5. Local Logout: happy path và negative cases

### 5.1. Arrange → Act → Assert

**Arrange:** User QA login Portal qua SAML, `GET /private` trả 200; ghi fingerprint local session, IdP session và Reports session. Bật test IdP event recorder để đếm SAML LogoutRequests.

**Act:** Browser gửi `POST /logout` với CSRF token hợp lệ.

**Assert:**
1. Spring chạy LogoutHandlers, invalidates HTTP session, clears SecurityContext và CSRF/remember-me state nếu cấu hình.
2. Response tới `/local-signed-out` theo chính sách, success page public và không tạo login loop.
3. Old cookie/session không tiếp tục cho `GET /private` truy cập dữ liệu với authentication cũ.
4. **Không** có SAMLRequest/LogoutRequest gửi IdP; IdP và Reports sessions **không mặc nhiên thay đổi**.
5. User truy cập lại protected URL có thể SSO lập tức; kiểm session Portal mới khác session trước.
6. Ứng dụng không hiển thị “đăng xuất tất cả ứng dụng” sau local action.

### 5.2. Negative cases

| Case | Kỳ vọng |
| --- | --- |
| POST /logout thiếu CSRF | Reject, thường 403; không forced logout |
| POST CSRF token của browser khác | Reject |
| GET /logout | Confirmation/no logout |
| GET /saml2/logout | Không phát federated LogoutRequest |
| Đặt `SAMLRequest` giả vào POST /logout | Vẫn là local route, không nhận IdP command |
| User double-click local logout | Không tạo nhiều SLO messages hoặc session lạ |
| Old JSESSIONID được dùng lại | Không còn authentication cũ |
| Browser có IdP cookie và SSO lại ngay | Không phải bằng chứng local logout thất bại |
| Trang local-signed-out bị bảo vệ | Phát hiện loop/redirect tới IdP, sửa permitAll |
| Custom app caches chưa dọn | Test business state, bổ sung LogoutHandler được quản trị |

Không chỉ assert HTTP 302. Một controller tự `return "redirect:..."` mà không xóa session vẫn có thể cho 302. Tầng test cần kiểm **session cũ thực sự không còn được phép truy cập** và outgoing SAML event count bằng 0.

## 6. RP-initiated SLO: test luồng từ SP đến IdP

### 6.1. Positive flow

1. User SAML-authenticated tại Portal, có trusted registration `corporate`. Nếu muốn kiểm propagation, mở Reports và login cùng IdP trong cùng sandbox.
2. Browser gửi `POST /saml2/logout` với valid CSRF.
3. Portal thực hiện local cleanup; `Saml2RelyingPartyInitiatedLogoutSuccessHandler` dùng `Saml2LogoutRequestResolver` sinh request có `ID` riêng.
4. Kiểm outbound `LogoutRequest`: `Issuer=urn:portal:test:sp`, `Destination=https://idp.test.example.org/slo`, `IssueInstant` hợp lý, đúng `NameID`/Format và `SessionIndex` tương ứng profile.
5. IdP sandbox kiểm chữ ký bằng SP public cert đã đăng ký; browser chuyển message bằng HTTP-POST binding.
6. IdP kết thúc/điều phối session theo policy và có thể gửi signed `LogoutResponse` chứa `InResponseTo` trỏ về request ID.
7. Portal `Saml2LogoutResponseFilter` verify signed response, issuer, destination, status và pending request correlation.
8. Kiểm session cũ Portal invalidated, IdP SSO outcome và Reports outcome **từng nơi**, không suy từ HTTP redirect.
9. Nếu Reports không hỗ trợ SLO hoặc không nhận request, ghi `PartialLogout`/unconfirmed thay vì global success.

**LogoutRequest XML chỉ minh họa, CHƯA KÝ:**

~~~xml
<samlp:LogoutRequest
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_sp-logout-17" Version="2.0"
  IssueInstant="2030-01-01T10:00:00Z"
  Destination="https://idp.test.example.org/slo">
  <saml:Issuer>urn:portal:test:sp</saml:Issuer>
  <saml:NameID Format=
      "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
    opaque-user-17
  </saml:NameID>
  <samlp:SessionIndex>_idp-session-17</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

Đây là mẫu cú pháp, không sử dụng như signed fixture thực. Theo SAML Profiles, session participant phải nêu SessionIndex khi khởi tạo Single Logout cho session liên quan. Kiểm SAMLMessage do Spring resolver thực tế sinh và thỏa thuận IdP; **không** thay SessionIndex bằng JSESSIONID.

**LogoutResponse XML mẫu, cũng CHƯA KÝ:**

~~~xml
<samlp:LogoutResponse
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_idp-res-17"
  InResponseTo="_sp-logout-17"
  Version="2.0"
  IssueInstant="2030-01-01T10:00:10Z"
  Destination="https://portal.test.example.org/logout/saml2/slo">
  <saml:Issuer>https://idp.test.example.org/saml</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
       Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
</samlp:LogoutResponse>
~~~

**Không chấp nhận** Status=Success từ XML do browser gửi nếu chưa verify signer/issuer/destination và `InResponseTo`. Một response của IdP B không thuộc registration của Portal A phải bị từ chối.

### 6.2. Negative cases RP flow

| Case | Kỳ vọng |
| --- | --- |
| POST /saml2/logout thiếu CSRF | Không phát LogoutRequest |
| User anonymous hoặc không phải SAML principal | Không tự chọn IdP bất kỳ để phát request |
| IdP metadata thiếu SingleLogoutService | SLO unsupported; local logout vẫn dùng được |
| SP signing key thiếu/cert mismatch | IdP reject hoặc config failure |
| Outbound Destination sai | IdP reject |
| Outbound Issuer/SP entity ID sai | IdP reject |
| NameID/Format sai | IdP không logout nhầm session |
| SessionIndex wrong/missing khi profile yêu cầu | IdP reject hoặc không xác nhận session đó |
| IdP unreachable/timeout | Portal local có thể đã logout, federation unconfirmed |
| Browser đóng tab trước callback | Không có verified full SLO completion |
| User bấm RP logout lần 2 sau session cleanup | Không mint request bằng principal stale |
| IdP trả signed LogoutResponse có lỗi | Không đánh dấu global success |
| IdP trả PartialLogout | Không tuyên bố mọi SP đã logout |

**Không yêu cầu rollback local logout khi IdP unreachable**: Spring có thể invalidates Portal session trước khi browser đi IdP. UX nên nói “phiên ứng dụng đã kết thúc; chưa xác nhận kết quả đăng xuất liên kết.”

## 7. IdP-initiated SLO: test xác minh trước khi dọn session

### 7.1. Positive scenario

**Arrange:** User QA có authenticated SAML session ở Portal. IdP test đã có private signing key được Portal trust qua metadata.

**Act:** IdP chủ động phát signed `LogoutRequest` theo HTTP-POST binding, đặt Base64-encoded payload trong form field `SAMLRequest`, browser POST tới `/logout/saml2/slo`.

**Assert:**
1. `Saml2LogoutRequestFilter` nhận message, chọn đúng registration/IdP trust.
2. Validator kiểm chữ ký, issuer, destination, subject/NameID/Format, session context, time và replay theo framework/policy.
3. **Chỉ khi request hợp lệ** mới gọi local LogoutHandlers và dọn đúng session user.
4. `Saml2LogoutResponseResolver` phát signed `LogoutResponse` với `InResponseTo` bằng LogoutRequest ID, `Issuer` SP entity ID, `Destination` IdP SLO response URL.
5. Browser gửi response về IdP. **Không assert** ứng dụng render local success page; IdP điều khiển browser tiếp.
6. Session unrelated users/tenants/devices không bị xóa chỉ vì có cùng email hoặc NameID.

**Incoming LogoutRequest XML mẫu CHƯA KÝ:**

~~~xml
<samlp:LogoutRequest
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_idp-logout-17" Version="2.0"
  IssueInstant="2030-01-01T10:30:00Z"
  Destination="https://portal.test.example.org/logout/saml2/slo">
  <saml:Issuer>https://idp.test.example.org/saml</saml:Issuer>
  <saml:NameID Format=
    "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
    opaque-user-17
  </saml:NameID>
  <samlp:SessionIndex>_idp-session-17</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

Chỉ dùng XML này làm **minh họa cấu trúc**. Positive test phải để IdP sandbox tạo/ký message hợp lệ. Session authority/IdP có quy tắc riêng trong SAML Profiles về việc có hoặc không SessionIndex, tùy scope logout; test đúng profile và policy thực, không mặc định một request không có SessionIndex là giả mạo chỉ vì thiếu field.

### 7.2. Negative scenarios

| Input | Expected |
| --- | --- |
| Thiếu `SAMLRequest` hoặc malformed Base64/XML | Reject, không forced logout |
| Unsigned request khi policy yêu cầu signed | Reject |
| Signed bởi IdP chưa được trust | Reject |
| Issuer khác trusted registration | Reject |
| Destination là SP khác | Reject |
| NameID/Format không khớp user session | Không logout nhầm |
| SessionIndex không khớp khi phải match | Không logout unrelated session |
| Expired/invalid IssueInstant theo policy | Reject |
| Replay cùng request ID | Reject hoặc không gây lại side effects theo replay policy |
| Malicious XML Signature Wrapping | Validator không dùng unsigned element |
| User không có current SP session | Không tạo session mới hoặc xóa user khác |
| IdP tenant B gửi request cho tenant A | Không cross-tenant logout |

**Thứ tự kiểm rất quan trọng:** Nếu một invalid SAMLRequest vẫn khiến session user bị invalidate trước khi signature/subject validation, đó là bug forced-logout. Test phải assert cả rejection và **old valid session không bị ảnh hưởng** khi reject request.

## 8. LogoutResponse callback: kiểm InResponseTo và RelayState

RP flow chưa hoàn tất chỉ vì Portal gửi LogoutRequest. Khi IdP gửi `SAMLResponse` tới `/logout/saml2/slo`:

~~~text
Portal generated LogoutRequest:
  ID = _sp-logout-17
  Issuer = urn:portal:test:sp
  Store request + RelayState (nếu dùng) trong repository

IdP returns LogoutResponse:
  InResponseTo = _sp-logout-17
  Issuer = https://idp.test.example.org/saml
  Destination = https://portal.test.example.org/logout/saml2/slo
  signed by trusted IdP private key

Portal:
  lookup pending request
  verify signature/issuer/destination/status/ID
  consume state / finish or report failure
~~~

### Các ca callback cần thực hiện

1. Positive signed LogoutResponse có `InResponseTo` đúng pending request; ứng dụng xử lý theo Status.
2. Signed LogoutResponse có wrong `InResponseTo` nhưng cùng IdP signer và Destination hợp lệ → reject.
3. Signed LogoutResponse có correct ID nhưng Issuer khác → reject.
4. Signed LogoutResponse có correct ID nhưng Destination khác → reject.
5. LogoutResponse bị replay sau khi flow hoàn tất → reject/no duplicate completion.
6. `RelayState` bị sửa hoặc thuộc một browser khác → không chọn sai IdP/tenant và không bypass request correlation.
7. IdP trả `Status=Responder`/error → không báo global success.
8. Callback đến node B sau khi node A tạo request, request repository không dùng chung → fail an toàn chứ không bỏ `InResponseTo`.
9. Browser cross-site POST không gửi cookie do SameSite → phát hiện state loss và xử lý cấu hình browser/session/repository, không làm validator “always pass”.
10. Callback đến sau khi user mở login session mới → không apply response cũ lên session mới.

**Test chữ ký chuẩn:** Nếu sửa `InResponseTo` trong XML sau khi IdP ký, signature hỏng và validator reject ở lớp cryptographic, **chưa chứng minh** kiểm correlation. Phải cho IdP sandbox **ký mới** LogoutResponse với wrong InResponseTo để cô lập lớp validation.

### SAML Status PartialLogout

~~~xml
<samlp:Status xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
  <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:Success">
    <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:PartialLogout"/>
  </samlp:StatusCode>
</samlp:Status>
~~~

Đây là second-level status minh họa, không phải signed LogoutResponse. Theo SAML Profiles, `PartialLogout` dùng khi session authority không xác nhận được tất cả session participants. Tester phải phân biệt:
- Local session cleanup của Portal;
- IdP báo Success, PartialLogout hoặc error;
- Reports SP có thực sự logout đúng user hay không;
- Các thiết bị, tokens và ứng dụng khác vẫn có thể tồn tại ngoài phạm vi SLO.

## 9. CSRF: user form khác signed SAML protocol callback

**User-triggered:** `POST /logout` và `POST /saml2/logout` thay đổi browser session, phải có CSRF token. `GET /logout` khi CSRF enabled thường hiển thị confirmation page; không thực hiện logout chỉ vì GET từ một external page.

**Protocol inbound:** IdP **không có** form CSRF token của Portal; `POST /logout/saml2/slo` phải đi qua signed SAML validator. Có thể cần exclusion CSRF **chính xác** cho route inbound tùy Spring config/version; nhưng tuyệt đối **không** tắt CSRF toàn ứng dụng và không mở wildcard `/logout/**` thiếu kiểm soát.

**Negative test:** Attacker tự POST `SAMLRequest` giả tới listener không có CSRF token. Request vẫn phải bị SAML validator từ chối vì signature/issuer/session sai, không logout user chỉ do có parameter.

**Không nhầm 403 và 400:** User form thiếu CSRF thường 403; SAML invalid message có thể được Spring SAML filter trả 400. Assert chính xác behavior của version đã pin và **side effects** hơn là chỉ đo một status cố định khi config khác nhau.

## 10. Spring Boot 3.5.x sandbox app: hai nút độc lập

Mẫu bên dưới cần IdP test có metadata SLO thực, SP private signing key/cert và public HTTPS deployment. Không thể hoàn thành SLO với URL ví dụ chưa hoạt động.

### Cấu trúc

~~~text
saml-slo-sandbox/
  pom.xml
  src/main/java/demo/SloSandboxApplication.java
  src/main/resources/application.yml
  src/main/resources/templates/home.html
  src/main/resources/templates/local-signed-out.html
~~~

### pom.xml

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
  <artifactId>saml-slo-sandbox</artifactId>
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
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
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
~~~

### application.yml

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.test.example.org/metadata
            signing:
              credentials:
                - private-key-location: file:/run/secrets/saml/sp-signing.key
                  certificate-location: file:/run/secrets/saml/sp-signing.crt
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
~~~

`singlelogout.url` là **SP protocol callback**, không phải trigger của user. IdP metadata cần `SingleLogoutService`; SP private key **PKCS#8** và X.509 public certificate nằm ngoài source code, theo secret store/mount. IdP phải được cấu hình biết SP EntityID, ACS/SLO URL, signing public cert. Nếu IdP metadata không thể tải, Spring có thể fail ở startup.

### SloSandboxApplication.java

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
public class SloSandboxApplication {

    public static void main(String[] args) {
        SpringApplication.run(SloSandboxApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
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
        String home() {
            return "home";
        }

        @GetMapping("/local-signed-out")
        String signedOut() {
            return "local-signed-out";
        }
    }
}
~~~

Controller chỉ hiển thị trang; logout được xử lý bởi Spring filter/handler. Không thêm `@PostMapping` tự thực hiện logout.

### templates/home.html

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>SAML SLO</title></head>
<body>
  <h1>Chọn phạm vi đăng xuất</h1>
  <form th:action="@{/logout}" method="post">
    <button type="submit">Đăng xuất ứng dụng</button>
  </form>
  <p>IdP và các ứng dụng khác có thể còn phiên.</p>
  <form th:action="@{/saml2/logout}" method="post">
    <button type="submit">Yêu cầu đăng xuất liên kết</button>
  </form>
  <p>Kết quả liên kết tùy IdP và các SP tham gia.</p>
</body>
</html>
~~~

Kiểm HTML đã render có `_csrf` field khi template integration tự chèn. Với SPA/fetch, phải gửi CSRF token theo repository/header policy; **không** disable CSRF để pass bài test.

### templates/local-signed-out.html

~~~html
<!DOCTYPE html>
<html lang="vi">
<head><meta charset="UTF-8"><title>Local logout</title></head>
<body>
  <h1>Đã đăng xuất khỏi ứng dụng này</h1>
  <p>Phiên SSO tại IdP có thể vẫn còn hoạt động.</p>
  <a href="/">Trang chủ</a>
</body>
</html>
~~~

**Chạy thử** sau khi provision keys, test IdP, DNS/TLS đúng:

~~~bash
mvn spring-boot:run
~~~

Quan sát thực tế, không giả lập:
- Local POST → local success page, **không** có SAML LogoutRequest.
- RP POST → SP phát signed LogoutRequest tới IdP; IdP có thể trả LogoutResponse.
- IdP POST SAMLRequest → SP verify rồi phát signed LogoutResponse.
- IdP POST SAMLResponse → SP verify response tương quan RP transaction.

## 11. MockMvc: cách kiểm servlet layer mà không ngộ nhận SAML pass

MockMvc giúp kiểm routing, CSRF, local LogoutHandlers/redirects. Khi Spring Boot app có metadata-uri, test bootstrap có thể cần IdP sandbox hoặc registration bean fixture để tránh network startup dependency.

**Ví dụ test fragment** (cần project mục 10 và test IdP fixture; không chứng minh signed SAML):

~~~java
package demo;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class LocalLogoutSmokeTest {
    @Autowired MockMvc mvc;

    @Test
    void localLogoutPostWithCsrfCanProceed() throws Exception {
        mvc.perform(post("/logout")
                .with(user("qa-user"))
                .with(csrf()))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void localLogoutWithoutCsrfMustBeRejected() throws Exception {
        mvc.perform(post("/logout")
                .with(user("qa-user")))
            .andExpect(status().isForbidden());
    }
}
~~~

`user("qa-user")` tạo một **non-SAML mock principal**: test này chỉ kiểm CSRF/local filter wiring, **không kiểm RP-initiated SLO**. Hãy thêm test thực sự xác định session/`SecurityContext` sau logout và IdP message recorder để chứng minh không phát SAML. Để test SLO hãy dùng SAML principal fixture + signed OpenSAML messages từ test IdP; không mock validator `always true` rồi tuyên bố đã kiểm cryptography.

## 12. Java 17 chạy độc lập: test oracle cho bốn event

Chương trình dùng JDK 17 thuần, **không** cần Maven/IdP và không parse SAML; nó mô phỏng state decisions dựa trên các boolean *được giả định đã kiểm bởi framework*. Đây là **unit-level oracle**, không thay signature/protocol integration test.

**Tệp SloTestOracle.java:**

~~~java
public class SloTestOracle {

    enum Event {
        LOCAL, RP_START, IDP_REQUEST, IDP_RESPONSE
    }

    record TestCase(Event event, boolean csrf, boolean samlPrincipal,
                    boolean trustedSignature, boolean sameSubject,
                    boolean correlated, boolean idpAvailable) {}

    static String outcome(TestCase c) {
        return switch (c.event()) {
            case LOCAL -> c.csrf()
                    ? "LOCAL_CLEARED_NO_SAML"
                    : "REJECT_CSRF";
            case RP_START -> {
                if (!c.csrf()) yield "REJECT_CSRF";
                if (!c.samlPrincipal()) yield "REJECT_NO_SAML";
                yield c.idpAvailable()
                    ? "LOCAL_CLEARED_SEND_REQUEST"
                    : "LOCAL_CLEARED_FEDERATION_UNCONFIRMED";
            }
            case IDP_REQUEST -> {
                if (!c.trustedSignature()) yield "REJECT_BAD_REQUEST";
                if (!c.sameSubject()) yield "REJECT_WRONG_SUBJECT";
                yield "LOCAL_CLEARED_SEND_RESPONSE";
            }
            case IDP_RESPONSE -> {
                if (!c.trustedSignature()) yield "REJECT_BAD_RESPONSE";
                yield c.correlated()
                    ? "RESPONSE_CORRELATED"
                    : "REJECT_IN_RESPONSE_TO";
            }
        };
    }

    static void show(String label, TestCase c) {
        System.out.println(label + "=" + outcome(c));
    }

    public static void main(String[] args) {
        show("localOK", new TestCase(
            Event.LOCAL, true, true, false, false, false, false));
        show("localNoCsrf", new TestCase(
            Event.LOCAL, false, true, false, false, false, false));
        show("rpOK", new TestCase(
            Event.RP_START, true, true, false, false, false, true));
        show("rpNoSaml", new TestCase(
            Event.RP_START, true, false, false, false, false, true));
        show("rpOffline", new TestCase(
            Event.RP_START, true, true, false, false, false, false));
        show("idpRequestOK", new TestCase(
            Event.IDP_REQUEST, false, true, true, true, false, true));
        show("idpUnsigned", new TestCase(
            Event.IDP_REQUEST, false, true, false, true, false, true));
        show("idpWrongSubject", new TestCase(
            Event.IDP_REQUEST, false, true, true, false, false, true));
        show("responseOK", new TestCase(
            Event.IDP_RESPONSE, false, false, true, false, true, true));
        show("responseWrongId", new TestCase(
            Event.IDP_RESPONSE, false, false, true, false, false, true));
        show("responseBadSignature", new TestCase(
            Event.IDP_RESPONSE, false, false, false, false, true, true));
    }
}
~~~

Chạy:

~~~bash
javac SloTestOracle.java
java SloTestOracle
~~~

**Stdout chính xác:**

~~~text
localOK=LOCAL_CLEARED_NO_SAML
localNoCsrf=REJECT_CSRF
rpOK=LOCAL_CLEARED_SEND_REQUEST
rpNoSaml=REJECT_NO_SAML
rpOffline=LOCAL_CLEARED_FEDERATION_UNCONFIRMED
idpRequestOK=LOCAL_CLEARED_SEND_RESPONSE
idpUnsigned=REJECT_BAD_REQUEST
idpWrongSubject=REJECT_WRONG_SUBJECT
responseOK=RESPONSE_CORRELATED
responseWrongId=REJECT_IN_RESPONSE_TO
responseBadSignature=REJECT_BAD_RESPONSE
~~~

`csrf=false` ở IDP_REQUEST/RESPONSE không cho phép mọi request vượt bảo mật: đó là các **protocol callbacks** cần signed SAML validation, không phải form user. `trustedSignature` trong demo là boolean giả định; **không nhận boolean từ HTTP client**. `idpAvailable=false` minh họa local state đã dọn mà federation chưa xác nhận; thực tế phụ thuộc thời điểm network fail. Không dùng chương trình này làm production logout handler.

## 13. Ma trận negative tests cấp giao thức và hệ thống

| ID | Request/state | Expected |
| --- | --- | --- |
| L01 | Local valid POST+CSRF | Local logout, no LogoutRequest |
| L02 | Local POST missing CSRF | Reject, no forced logout |
| L03 | GET /logout | No direct logout |
| L04 | Local success page public | No redirect loop |
| L05 | Old JSESSIONID after local | No authenticated access |
| L06 | Local logout rồi SSO lại | New Portal session, không nhầm failure |
| R01 | RP POST valid SAML user+CSRF | Signed LogoutRequest đúng IdP |
| R02 | RP missing CSRF | No outbound request |
| R03 | RP non-SAML principal | Không gửi request tùy ý |
| R04 | IdP no SingleLogoutService | Capability missing, local usable |
| R05 | SP wrong signing key/certificate | IdP reject |
| R06 | Outbound wrong Issuer | IdP reject |
| R07 | Outbound wrong Destination | IdP reject |
| R08 | Wrong NameID/Format | Không logout wrong user |
| R09 | Wrong SessionIndex | Không logout wrong session |
| R10 | Valid LogoutResponse matching request | Correlated success/status handled |
| R11 | LogoutResponse unsigned/bad signature | Reject |
| R12 | Signed LogoutResponse other IdP | Reject |
| R13 | Signed LogoutResponse wrong InResponseTo | Reject |
| R14 | Signed LogoutResponse wrong Destination | Reject |
| R15 | Replayed LogoutResponse | Reject/no duplicate completion |
| R16 | Modified RelayState | No open redirect/tenant switch |
| R17 | PartialLogout | Không báo global success |
| R18 | IdP timeout/browser tab closed | Federation unconfirmed |
| R19 | Callback node B missing request | Fail-closed, không bỏ validation |
| A01 | IdP signed LogoutRequest right subject | Verify, local logout, signed LogoutResponse |
| A02 | IdP unsigned request | Reject/no session invalidation |
| A03 | IdP wrong signer/Issuer | Reject |
| A04 | IdP wrong Destination | Reject |
| A05 | IdP wrong NameID | Không xóa session khác |
| A06 | IdP wrong SessionIndex | Không logout wrong session |
| A07 | Malformed Base64/XML | Reject |
| A08 | Replay LogoutRequest | Reject/no repeated side effects |
| A09 | IdP request no current SP session | Không tạo authentication mới |
| A10 | AP flow expected local success page | Không bắt buộc: browser thuộc IdP |
| A11 | IdP request from wrong tenant | Không logout cross-tenant |
| E01 | Cross-site POST cookie blocked | Detect session/correlation issue |
| E02 | Signing cert rotation | Only approved trusted certs accepted |
| E03 | Reports SP SLO fails | Partial/unconfirmed, local still correct |
| E04 | Session user A vs B same NameID | No cross-user/tenant logout |
| E05 | API refresh token still active | SLO không tự revoke tokens |
| E06 | User logged in on second device | Không hứa mọi device logout |
| E07 | Debug log records raw SAML | QA fail, redact/incident process |
| E08 | LB reverse proxy scheme/host wrong | Fix metadata/public URL, không tắt Destination |

### 13.1. Thử từng validator độc lập

Nếu sửa `Destination` trong signed XML, signature hỏng; test sẽ fail vì signature **trước** khi destination rule được đo. Để test destination hoặc correlation, IdP test phải phát **signed fixture hợp lệ nhưng có đúng field sai**. Tương tự:
- Wrong signer: ký bởi một key không nằm trong trusted IdP metadata.
- Wrong issuer: ký lại với signer đã được phê duyệt nhưng claim issuer không hợp với registration.
- Wrong InResponseTo: ký lại với ID chưa có trong repository.
- Wrong SessionIndex: ký lại LogoutRequest cho subject/session khác.
- Wrong status: ký một LogoutResponse error/PartialLogout thật.
- Replay: gửi lại **y nguyên** message đã được xử lý, kiểm replay/side effects.

Không dùng một mock `Saml2LogoutRequestValidator` always-pass rồi khẳng định signature/issuer tests đã đạt.

## 14. Test browser, cluster và các trường hợp khó

**Browser scenario Local:**
1. Login Portal và Reports cùng IdP.
2. Ghi session fingerprints.
3. Click Local Logout; kiểm no SAMLRequest trong IdP event recorder.
4. Reports vẫn có thể giữ session; Portal old session invalidated.
5. Vào lại Portal, phân biệt session mới SSO từ IdP.

**Browser scenario RP:**
1. Login hai SP; click SAML SLO.
2. Capture signed LogoutRequest SP→IdP, ID và signature validation result.
3. Theo dõi IdP propagate tới Reports (nếu supported) và callback.
4. Verify LogoutResponse signature/InResponseTo/status.
5. Kiểm mỗi session; PartialLogout khi một SP không respond.

**Browser scenario IdP:**
1. User login Portal.
2. IdP sandbox initiate SLO cho session user.
3. Portal nhận signed LogoutRequest; verify rồi xóa session.
4. Portal ký LogoutResponse gửi IdP, không assert Portal local success page.
5. Thử unsigned/wrong-subject/replay and ensure no forced logout.

**Cluster scenario:** Node A tạo LogoutRequest, node B nhận LogoutResponse; repository/session phải cho phép correlation hoặc fail an toàn. Không chữa bằng cách bỏ `InResponseTo`. Nếu SameSite/HTTPS/proxy làm cookie không gửi theo cross-site POST, test bằng real browser. Cấu hình `SameSite=None; Secure` khi hợp đồng và threat model cần, không cài bừa mà làm yếu CSRF.

**Multi-IdP:** Portal có IdP A/B; request phải tới IdP tương ứng principal/registration được xác thực, không chọn URL IdP từ query user. Issuer/signing key của IdP B không được chấp nhận để logout user A, dù NameID/email trùng.

**Multi-device:** SAML SLO theo browser/session flow không tự revoke mọi HTTP sessions trên thiết bị khác, access/refresh tokens, WebSocket, app non-SAML. Muốn offboarding/global logout phải thiết kế session registry và token revocation riêng.

## 15. Troubleshooting theo lớp

| Triệu chứng | Nguồn lỗi có thể | Khắc phục |
| --- | --- | --- |
| Bấm local lại gửi SAMLRequest | Local/RP URL chưa tách | Configure both logout URLs |
| Local xong login lại tức thì | IdP SSO cookie còn | So session cũ/mới, UX đúng |
| POST local 403 | CSRF token thiếu/sai | Form token đúng, không disable toàn app |
| RP không phát request | Principal không phải SAML hoặc SLO config thiếu | Registration/IdP metadata/SP key |
| IdP từ chối request | SP signer/issuer/NameID/SessionIndex sai | IdP verifier logs + metadata |
| AP request bị 400 | Invalid SAML signature/issuer/destination | Dùng signed IdP test fixtures |
| AP request bị 403 | CSRF matcher chặn protocol endpoint | Exemption chính xác + signed SAML validator |
| Callback báo InResponseTo mismatch | Mất request state/cookie/cluster | Request repository + SameSite/shared store |
| Callback sai host/path | Proxy/public SLO URL sai | Fix metadata, canonical HTTPS, no bypass |
| PartialLogout | Một participant không phản hồi | Report partial; test Reports riêng |
| Login loop local success | Trang success không permitAll | Cho phép success page public |
| Tests wrong correlation always fail signature | Sửa XML sau khi ký | Ký mới invalid-field fixture |
| IdP timeout | Network/browser chưa hoàn tất | Local done/federation unconfirmed |
| Logout device B vẫn hoạt động | Không có cross-device revocation | Session registry/token policy |
| Key rotation | SP/IdP signer chưa đồng bộ | Public cert rollover/rotation tests |

**Quy trình chẩn đoán:** Route+CSRF → local LogoutHandlers → outbound resolver & SP signer → IdP SLO service → inbound IdP signer/issuer/destination → request repository/InResponseTo → SAML Status → real SP/IdP/Reports sessions. Không sửa tầng sau bằng cách tắt validator tầng trước.

## 16. Ghi nhận kết quả QA và bảo vệ dữ liệu

Một test report hữu ích có fields:

~~~text
Case ID: R13
Flow: RP-initiated / LogoutResponse callback
SP registration: corporate
Expected: Signed LogoutResponse with unknown InResponseTo rejected
Actual: callback rejected, old session state checked
Signature verified: YES (sandbox IdP test signer)
Correlation verified: NO
Pending request ID: fingerprint only
SAML response Status: not treated as success
Other SP sessions: not asserted
Evidence: redacted test-IdP event ID and SP log correlation ID
Result: PASS
~~~

Báo cáo không được chứa: raw `SAMLRequest/SAMLResponse`, NameID người thật, `JSESSIONID`, CSRF tokens, private signing keys, SAML assertions, API tokens, email/attributes không cần thiết.

**CI:**
- Unit/MockMvc tests chạy trong profile riêng, metadata fixtures chỉ từ approved test keys.
- IdP integration có thể dùng một test IdP đóng vai trusted signer để tạo negative messages **được ký lại**.
- Browser E2E với HTTPS public host và cookie SameSite behavior, không chỉ MockMvc.
- Test user/session riêng mỗi test, cleanup IdP/Portal/Reports sau suite.
- Không chạy malformed SAML tests vào production IdP hoặc users thật.
- Có monitoring cho signature validation failures, correlation failures, SLO timeouts và partial statuses.
- Report thiếu bằng chứng signing/correlation thì không tự đánh PASS chỉ vì HTTP 302/200.

## 17. Bài tập và tiêu chí đạt

**Bài A:** Vẽ bốn endpoint/actions. Phân biệt form CSRF token của user với signed SAML protocol callback.

**Bài B:** Chạy `SloTestOracle.java` và đối chiếu 11 dòng stdout. Giải thích vì sao `csrf=false` ở IdP flow không có nghĩa “bỏ security”.

**Bài C:** Với Spring Boot sandbox, POST local có CSRF và không có CSRF; assert session old invalidated ở case valid, rejected ở case invalid và no outbound SAMLRequest.

**Bài D:** RP SLO với IdP sandbox: kiểm outbound signed LogoutRequest, correct Issuer/Destination/NameID/SessionIndex; IdP trả signed LogoutResponse có InResponseTo đúng.

**Bài E:** Dùng test IdP ký lại một LogoutResponse wrong InResponseTo nhưng signature hợp lệ; chứng minh SP từ chối vì correlation, không chỉ signature.

**Bài F:** IdP-initiated signed LogoutRequest đúng subject → SP logout local và trả signed LogoutResponse. Signed request với wrong NameID → không xóa session người khác.

**Bài G:** IdP trả PartialLogout vì Reports không phản hồi; thiết kế UX “Đã kết thúc phiên ứng dụng, đăng xuất liên kết chưa hoàn tất” thay vì “Đã đăng xuất mọi nơi”.

**Bài H:** Node A gửi LogoutRequest, node B nhận callback khi session cookie SameSite bị chặn. Chẩn đoán request repository và đề xuất cấu hình có bảo mật.

**Bài I:** Một user có hai browsers. IdP-initiated SLO đến một session; phân biệt phạm vi hiện tại và nhu cầu global session revocation riêng.

**Bài J:** Tạo ma trận 10 negative cases cho signature, issuer, destination, status, session, replay, CSRF; chỉ rõ cách tạo signed invalid-field fixture để test đúng validator.

**Đạt bài:** Có thể giải thích và kiểm chứng **local cleanup không SAML**, **RP LogoutRequest/IdP LogoutResponse đúng transaction**, **IdP signed LogoutRequest/đúng principal** và **failure/partial/multi-node** mà không tuyên bố global logout vượt quá bằng chứng.

## 18. Tài liệu chính thức

- Spring Security 6.5 – Performing Single Logout, APIs, endpoints, handlers và separating local: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html
- Spring Security 6.5 – Handling Logouts và CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security 6.5 – MockMvc setup: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html
- Spring Security 6.5 – SAML2 login/registration: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html
- Spring Security – SAML2 metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- OASIS SAML 2.0 Core – Single Logout Protocol: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS SAML 2.0 Profiles – Single Logout Profile, SessionIndex và PartialLogout: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS SAML 2.0 Bindings – HTTP-POST/Redirect và signature handling: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- OASIS SAML 2.0 Metadata – SingleLogoutService: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
