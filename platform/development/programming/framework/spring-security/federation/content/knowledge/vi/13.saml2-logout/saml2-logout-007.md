# Lưu yêu cầu đăng xuất và kiểm tra InResponseTo của phản hồi trong Spring Security SAML 2.0

## 1. Mục tiêu và vấn đề bảo mật

Trong **Spring Security – federation**, ứng dụng Java thường đóng vai **Service Provider (SP / Relying Party)** còn hệ thống xác thực tập trung đóng vai **Identity Provider (IdP / Asserting Party)**. Khi người dùng đăng xuất, ứng dụng có thể không chỉ xóa phiên local mà còn khởi tạo **SAML 2.0 Single Logout (SLO)** để đề nghị IdP đóng phiên SSO và xử lý các phiên liên quan.

Ở luồng **SP-initiated Single Logout**, SP phát **LogoutRequest**, chuyển trình duyệt sang IdP, và sau đó có thể nhận **LogoutResponse**. Đây là hai HTTP request khác nhau, có thể đi qua proxy, browser, load balancer và các node khác nhau. Trong khoảng giữa, phiên xác thực local có thể đã bị hủy.

Câu hỏi cốt lõi:

**Làm sao biết LogoutResponse thực sự trả lời đúng LogoutRequest do SP phát trước đó, trong đúng luồng trình duyệt và đến từ đúng IdP?**

Để giải quyết, SP cần:

1. **Lưu LogoutRequest đang chờ xử lý** khi tạo request, trước khi giao quyền điều khiển cho trình duyệt đi đến IdP.
2. Sau khi nhận phản hồi, xác minh rằng **LogoutResponse.InResponseTo khớp LogoutRequest.ID đã lưu**.
3. Kiểm tra thêm **RelayState, registration/IdP, chữ ký, Destination, Status, thời hạn, ngữ cảnh trình duyệt và chống replay**.
4. **Consume/xóa trạng thái một lần** sau khi hoàn tất theo đúng chính sách, không giữ pending request vô thời hạn.

Bài học thuộc nhóm **Đăng xuất SAML2**, dành cho người triển khai Spring Security SAML 2.0 Servlet. Trọng tâm là vòng đời của state, cách dùng **Saml2LogoutRequestRepository**, chiến lược storage trong cluster và cách kiểm chứng **InResponseTo** mà không tự bỏ qua cơ chế xác thực SAML.

**Lưu ý:** kiểm tra InResponseTo chỉ là một ràng buộc giao thức. Nó **không phải chữ ký mật mã**, và một chuỗi ID khớp không tự biến một phản hồi do người lạ tạo thành đáng tin cậy.

## 2. Phân biệt ba loại đăng xuất

| Luồng | Bên khởi tạo | Thông điệp trên đường truyền | State cần giữ |
| --- | --- | --- | --- |
| **Đăng xuất local** | Người dùng tại SP | Không có SAML LogoutRequest/LogoutResponse | Không có pending SLO |
| **SP/RP-initiated SLO** | **SP** | SP gửi LogoutRequest; IdP có thể trả LogoutResponse | **SP phải nhớ request đã phát** |
| **IdP/AP-initiated SLO** | **IdP** | IdP gửi LogoutRequest; SP trả LogoutResponse | IdP là bên có trách nhiệm correlation với request của nó |

### 2.1. SP-initiated SLO: luồng chính của bài

~~~text
Trình duyệt                  SP ứng dụng                     IdP
     |                            |                            |
     | POST /logout               |                            |
     |--------------------------->|                            |
     |                            | LogoutHandler xóa phiên    |
     |                            | xác thực local             |
     |                            |                            |
     |                            | Tạo LogoutRequest          |
     |                            | ID = _logout_001           |
     |                            | RelayState = state-abc     |
     |                            | SAVE pending request       |
     |                            |                            |
     |<---------------------------| Redirect/POST SAMLRequest  |
     |-------------------------------------------------------->|
     |                            |                            | verify request,
     |                            |                            | xử lý SLO
     |<--------------------------------------------------------|
     |   SAMLResponse chứa LogoutResponse InResponseTo=_logout_001
     |--------------------------->|                            |
     |                            | LOAD pending               |
     |                            | verify signature, issuer,  |
     |                            | InResponseTo, RelayState,  |
     |                            | Destination, Status        |
     |                            | consume/cleanup state      |
     |<---------------------------| kết quả SLO chính xác      |
~~~

**Điểm dễ bỏ sót:** tại thời điểm nhận LogoutResponse, Authentication và session local cũ có thể đã bị vô hiệu hóa. Vì thế không được thiết kế kiểm tra chỉ dựa vào việc người dùng vẫn đang đăng nhập. Spring Security có cơ chế riêng để **lưu request trong session phục vụ RelayState và InResponseTo**.

Theo tài liệu Spring Security, với SAML principal phù hợp, thao tác **POST /logout** có thể kích hoạt RP-initiated SLO. Framework chạy các logout handlers để vô hiệu hóa phiên local, tạo và gửi LogoutRequest tới SingleLogoutService của IdP. Nếu nhận LogoutResponse thì framework tiếp tục kiểm tra và hoàn tất phần callback. IdP có thể **không trả phản hồi** do lỗi mạng, trình duyệt bị đóng hoặc cấu hình; không nên mặc định mọi lần local logout đều chứng minh SLO toàn federation đã thành công.

### 2.2. IdP-initiated SLO: không tìm pending request của SP

Ở hướng còn lại:

~~~text
IdP -> SP: LogoutRequest.ID = _idp_request_9
SP: xác minh chữ ký/issuer/request, xử lý phiên local theo policy
SP -> IdP: LogoutResponse.InResponseTo = _idp_request_9
~~~

SP đang **trả lời yêu cầu đến từ IdP**, không chờ LogoutResponse cho một request do SP tạo trước. Bởi vậy, SP không được áp dụng nhầm logic “phải tìm pending SP LogoutRequest” vào **IdP-initiated**. Khi IdP nhận LogoutResponse của SP, IdP chịu trách nhiệm đối chiếu InResponseTo với request IdP đã gửi.

## 3. InResponseTo, ID, RelayState, SessionIndex khác nhau ra sao?

| Trường | Nơi xuất hiện | Mục đích |
| --- | --- | --- |
| **LogoutRequest.ID** | Thuộc tính ID của LogoutRequest | ID duy nhất của yêu cầu SP đã tạo |
| **LogoutResponse.ID** | Thuộc tính ID của LogoutResponse | ID riêng của thông điệp trả lời |
| **LogoutResponse.InResponseTo** | Thuộc tính InResponseTo của LogoutResponse | Trỏ tới **LogoutRequest.ID** đang được trả lời |
| **RelayState** | Tham số trong HTTP binding ngoài XML | Mang correlation state/luồng trình duyệt qua IdP |
| **SessionIndex** | Thường nằm trong LogoutRequest | Xác định một phiên SAML cần kết thúc |
| **NameID** | Trong LogoutRequest | Nhận diện principal cần đăng xuất ở SAML |
| **registrationId** | Trong Spring Security repository | Khóa local của cặp SP–IdP |
| **SP/IdP entityId** | Metadata, phần tử Issuer | Định danh logic của hai hệ thống |

Ví dụ:

~~~text
LogoutRequest.ID              = _logout_001
LogoutResponse.ID             = _response_987
LogoutResponse.InResponseTo   = _logout_001
RelayState                    = state-abc
SessionIndex                  = _saml_session_24
~~~

Chính **InResponseTo** phải khớp ID request đã lưu. Không so nhầm LogoutResponse.ID, SessionIndex hoặc NameID với LogoutRequest.ID. Việc cả hai bên cùng dùng một SAML NameID cũng không chứng minh đây là response của **đúng một yêu cầu**.

### 3.1. Vì sao InResponseTo quan trọng?

Giả sử hai lượt đăng xuất được khởi tạo:

~~~text
Pending A: LogoutRequest.ID = _A
Pending B: LogoutRequest.ID = _B

Response 1: InResponseTo = _A  -> chỉ có thể đối chiếu với A
Response 2: InResponseTo = _B  -> chỉ có thể đối chiếu với B
Response X: InResponseTo = _unknown -> không có pending state, phải từ chối
~~~

Nếu cho phép LogoutResponse không có InResponseTo hoặc không tìm được pending state vẫn xác nhận thành công, hệ thống có nguy cơ **chấp nhận response lạc luồng hoặc replay**. Mục đích là giữ tính liên tục của cuộc trao đổi SAML, không chỉ kiểm tra rằng một IdP nào đó đã ký một XML.

### 3.2. Vì sao RelayState vẫn cần được kiểm tra?

RelayState thường là một **mã opaque** để khôi phục ngữ cảnh trình duyệt. Nó được truyền kèm SAMLRequest và trả lại cùng SAMLResponse, nhưng **nằm bên ngoài XML**. Trong HTTP-Redirect binding, khi có chữ ký query, RelayState tham gia vào signed input theo quy tắc của binding. Trong HTTP-POST binding có XML Signature, chữ ký XML không tự bao trùm tham số form RelayState; phải xác minh bằng cơ chế correlation của SP.

**InResponseTo trả lời câu hỏi “message nào được phản hồi”, RelayState trả lời câu hỏi “luồng trình duyệt nào”.** Hai điều kiện này bổ trợ nhau. Một RelayState đúng không thay thế chữ ký hoặc InResponseTo; một InResponseTo đúng cũng không chứng minh RelayState chưa bị thay đổi.

Không sử dụng RelayState như URL redirect tùy ý hoặc quyền chọn tenant/IdP. Nên dùng **chuỗi ngẫu nhiên khó đoán, không chứa dữ liệu cá nhân hay secret**, gắn với context đã lưu phía SP.

## 4. Cấu trúc SAML LogoutRequest

Ví dụ minh họa các trường có ý nghĩa cho việc lưu state:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout_001"
    Version="2.0"
    IssueInstant="2026-01-01T10:00:00Z"
    Destination="https://idp.example.test/saml/slo">
    <saml:Issuer>urn:example:portal:sp</saml:Issuer>
    <saml:NameID>user-42</saml:NameID>
    <samlp:SessionIndex>_saml_session_24</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

**Đây là XML rút gọn để dạy khái niệm, không phải LogoutRequest đã được ký đầy đủ.** Trong giao thức thực, thông điệp cần được Spring Security/OpenSAML tạo, ký/encode theo binding và có thể chứa trường bổ sung.

Các điểm cần lưu ý:

- **ID** của request dùng cho correlation; cần duy nhất và khó đoán. Spring Security có cơ chế sinh ID cho LogoutRequest.
- **IssueInstant** giúp chính sách tuổi thọ/freshness, nhưng không tự là TTL lưu trữ; repository cần timeout độc lập.
- **Issuer** thường là SP Entity ID, để IdP tìm cấu hình trust.
- **Destination** là SingleLogoutService URL của IdP đã đăng ký.
- **NameID/SessionIndex** phục vụ định danh người/phiên tại IdP, không thay thế ID của request.
- **Chữ ký** theo binding cần private key SP và certificate công khai SP được IdP tin; ID request đúng không thay thế xác thực chữ ký.

## 5. Cấu trúc LogoutResponse và vị trí InResponseTo

Ví dụ IdP trả lời:

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response_987"
    Version="2.0"
    IssueInstant="2026-01-01T10:00:05Z"
    InResponseTo="_logout_001"
    Destination="https://portal.example.test/logout/saml2/slo">
    <saml:Issuer>https://idp.example.test/issuer</saml:Issuer>
    <samlp:Status>
        <samlp:StatusCode
            Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
    </samlp:Status>
</samlp:LogoutResponse>
~~~

**Không dùng ví dụ này như thông điệp an toàn**: XML đã rút gọn và bỏ phần chữ ký. Trong hệ thống thật, IdP ký response theo cấu hình/binding, SP xác minh đúng certificate IdP.

Quy tắc correlation:

~~~text
Request.ID                 = _logout_001
Response.InResponseTo      = _logout_001  -> khớp request
Response.ID                = _response_987 -> ID mới của response
~~~

Khớp InResponseTo chỉ chứng minh **mối quan hệ ID trong dữ liệu**, chưa đủ để kết luận IdP thực sự phát phản hồi. SP còn phải kiểm chữ ký, issuer, destination, RelayState, freshness, registration và Status.

### 5.1. StatusCode cũng là điều kiện cần xem xét

| StatusCode | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| **Success** | IdP thông báo xử lý thành công theo profile | Chỉ xác nhận SLO hoàn thành nếu response đã được validate toàn diện |
| **PartialLogout** | Không phải tất cả phiên downstream đã được xử lý | Không tuyên bố mọi hệ thống đều đã đăng xuất |
| **Requester** | Có lỗi phía yêu cầu | Phân loại lỗi và ghi nhận, không khẳng định SLO thành công |
| **Responder** | Có lỗi ở bên xử lý | Phân loại lỗi và áp dụng chính sách hỗ trợ/retry |

**Phiên local có thể đã bị đóng từ khi SP gửi LogoutRequest**, ngay cả khi IdP trả lỗi hoặc không trả response. Cần diễn đạt trung thực trạng thái “đã đăng xuất ứng dụng” và “đã hoàn tất single logout”.

## 6. Spring Security dùng gì để lưu LogoutRequest?

Spring Security Servlet SAML2 có các thành phần chính:

| Thành phần | Công việc |
| --- | --- |
| **Saml2LogoutRequestResolver** | Tạo, ký và serialize LogoutRequest theo Authentication/registration |
| **Saml2RelyingPartyInitiatedLogoutSuccessHandler** | Khởi động RP-initiated SLO, gửi request đến IdP và lưu pending state |
| **Saml2LogoutRequestRepository** | Giao diện lưu, lấy, xóa pending Saml2LogoutRequest giữa các HTTP requests |
| **HttpSessionLogoutRequestRepository** | Triển khai repository dựa trên HttpSession |
| **Saml2LogoutResponseFilter** | Nhận SAMLResponse trên endpoint SLO và chuyển cho quá trình xử lý |
| **Saml2LogoutResponseValidator** | Xác minh response theo policy và thông tin request liên quan |
| **RelyingPartyRegistrationRepository** | Cung cấp cấu hình SP–IdP, certificates, endpoints, binding |

Tài liệu **Performing Single Logout** của Spring Security nêu rõ: khi ứng dụng gửi LogoutRequest, **giá trị được lưu trong session để kiểm tra RelayState và InResponseTo** của LogoutResponse nhận về. Nếu muốn lưu ở nơi khác, có thể cung cấp implementation riêng thông qua DSL **logoutRequestRepository**.

### 6.1. Hợp đồng Saml2LogoutRequestRepository

Các method theo Javadoc của Spring Security hiện đại, ở đây trình bày chữ ký đơn giản hóa để thấy mục đích:

~~~java
Saml2LogoutRequest loadLogoutRequest(
    HttpServletRequest request);

void saveLogoutRequest(
    Saml2LogoutRequest logoutRequest,
    HttpServletRequest request,
    HttpServletResponse response);

Saml2LogoutRequest removeLogoutRequest(
    HttpServletRequest request,
    HttpServletResponse response);
~~~

Lưu ý:

- Đây là **trích đoạn chữ ký API**, không phải một file Java độc lập hoặc interface bạn phải khai báo lại.
- Phiên bản hiện đại sử dụng **jakarta.servlet.http**; các method trả về có thể có annotation nullable, và **saveLogoutRequest(null, ...)** có ý nghĩa xóa theo contract.
- **save** lưu request đã tạo cho luồng SLO sau này.
- **load** trả request đang chờ theo HTTP context để validator dùng so sánh.
- **remove** lấy và xóa state theo semantics của repository, nhằm không tái sử dụng sau khi xử lý.
- Không được hiểu “load thành công” là “phản hồi đã được xác minh”; vẫn phải kiểm chữ ký/issuer/InResponseTo và mọi điều kiện liên quan.

### 6.2. Phân biệt repository logout với repository login

| Repository | Dùng cho | ID tương ứng |
| --- | --- | --- |
| **Saml2LogoutRequestRepository** | LogoutRequest/LogoutResponse của **SLO** | LogoutRequest.ID và LogoutResponse.InResponseTo |
| **Saml2AuthenticationRequestRepository** | AuthnRequest/Response của **SSO login** | AuthnRequest.ID và Response.InResponseTo |

Không dùng **HttpSessionSaml2AuthenticationRequestRepository** thay cho **HttpSessionLogoutRequestRepository**. Hai loại state đều có request ID và correlation nhưng **khác giao thức, lifecycle, API và security filter**.

## 7. Ví dụ cấu hình Spring Boot SLO

Ví dụ tối giản dành cho ứng dụng Spring Boot 3.x/Spring Security SAML2 Servlet có IdP hỗ trợ Single Logout. Cần kiểm tra version property chính xác trong ứng dụng đang triển khai.

Tệp **src/main/resources/application.yml**:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "urn:example:portal:sp"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-sign.key"
                  certificate-location: "file:/etc/saml/sp-sign.crt"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
            assertingparty:
              metadata-uri: "file:/etc/saml/idp-metadata.xml"
~~~

Giải thích:

1. **corp** là registrationId dùng để tìm đúng cặp SP–IdP.
2. **entity-id** là định danh SP trong SAML, khác ID của LogoutRequest.
3. **signing.credentials** nạp private key/certificate SP, dùng ký LogoutRequest/LogoutResponse khi profile yêu cầu. IdP cần có public certificate SP đã đăng ký.
4. **singlelogout.url** là SLO endpoint công khai của SP. Đường mặc định thường là **/logout/saml2/slo** và có thể được cấu hình lại.
5. **assertingparty.metadata-uri** dùng nhập IdP metadata để biết SingleLogoutService, binding và certificate xác minh; nguồn metadata phải có trust policy phù hợp.
6. File mẫu cần được provision thật. Không lưu private key trong source control hay tin rằng đường dẫn metadata tự chứng minh IdP hợp lệ.

**Điều kiện trước khi bật SLO:** IdP metadata có **SingleLogoutService**; SP đã đăng ký đúng SLO URL/certificate tại IdP; binding và cách ký phù hợp. Login SSO thành công **không có nghĩa** SLO sẽ tự hoạt động.

## 8. Java SecurityFilterChain: dùng repository của Spring

Tệp **SecurityConfig.java** trong ứng dụng Spring Boot có dependencies SAML2:

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.web.authentication.logout.HttpSessionLogoutRequestRepository;
import org.springframework.security.saml2.provider.service.web.authentication.logout.Saml2LogoutRequestRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    Saml2LogoutRequestRepository logoutRequestRepository() {
        return new HttpSessionLogoutRequestRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            Saml2LogoutRequestRepository logoutRequestRepository)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Logout(saml2 -> saml2
                .logoutRequest(req -> req
                    .logoutRequestRepository(logoutRequestRepository)));
        return http.build();
    }
}
~~~

Đây là **class Spring**, không thể biên dịch bằng JDK thuần nếu thiếu Spring Boot/Spring Security và IdP registration. Mục đích là chỉ ra API **logoutRequestRepository**, không tái hiện toàn bộ project.

**Nếu không cần custom storage**, thông thường có thể dùng **saml2Logout(Customizer.withDefaults())** và để Spring Security quản lý repository mặc định. Khi cung cấp bean như ví dụ, cần bảo đảm filter chain **thực sự nhận đúng repository**.

Không tự tạo một logout controller chỉ nhìn tham số InResponseTo rồi redirect sang trang thành công. Bộ lọc SAML2 của Spring Security/OpenSAML phải đảm nhận parse/chữ ký/validation.

### 8.1. Những endpoint cần biết

Theo Spring Security SLO thông dụng:

~~~text
POST /logout
    -> RP-initiated logout bởi người dùng đã xác thực SAML

POST /logout/saml2/slo + SAMLRequest
    -> IdP-initiated LogoutRequest đến SP

POST /logout/saml2/slo + SAMLResponse
    -> LogoutResponse từ IdP cho request SP đã phát
~~~

IdP có thể dùng **HTTP-Redirect binding** (GET), tùy sản phẩm/config và profile hỗ trợ; endpoint có thể thay qua DSL. Không suy rằng mọi IdP bắt buộc dùng POST, và không tắt **CSRF trên toàn ứng dụng** để sửa lỗi một SLO callback.

## 9. Cần lưu dữ liệu gì trong pending logout state?

Ở mức API, Spring lưu đối tượng **Saml2LogoutRequest**. Khi thiết kế repository custom, dữ liệu ở mức khái niệm có thể gồm:

~~~text
PendingLogout:
  requestId            = _logout_001
  registrationId       = corp
  expectedIdpEntityId  = https://idp.example.test/issuer
  relayState           = opaque-relay-7
  spEntityId           = urn:example:portal:sp
  expectedResponseUrl  = https://portal.example.test/logout/saml2/slo
  browserFlowBinding   = opaque-browser-context
  createdAt            = 2026-01-01T10:00:00Z
  expiresAt            = 2026-01-01T10:03:00Z
  status               = pending
~~~

Mô hình trên **không có nghĩa đối tượng Saml2LogoutRequest trong Spring có đủ từng field**. Repository có thể giữ object đã serialize và metadata khác phục hồi từ registration/request context. Điều cần bảo đảm là khi Response quay về, SP khôi phục được **request đúng** để validator kiểm tra.

Đặc biệt:

- **requestId** phải đến từ LogoutRequest đã phát, không nhận do browser tự khai rồi xem là đã tồn tại.
- **registrationId** gắn một trust configuration; không nhầm với IdP Entity ID.
- **RelayState** dùng ngữ cảnh browser và có thể giúp tìm pending state.
- **expectedIdpEntityId** giúp ràng buộc đúng issuer, nhưng issuer vẫn cần chữ ký đáng tin.
- **createdAt/expiresAt** giới hạn cửa sổ dùng state. Ba phút trong ví dụ chỉ là **một TTL minh họa**, không phải hằng số SAML.
- **Saml2LogoutRequest** có thể mang message XML/NameID/SessionIndex; storage phải có hạn truy cập/retention tương ứng, không in payload ra log công khai.

## 10. Quy trình validate LogoutResponse

Về mặt nghiệp vụ bảo mật, quá trình nhận LogoutResponse cần thỏa đồng thời các điều kiện:

1. **Nhận qua SLO endpoint/binding hợp lệ**, giới hạn kích thước request và XML parsing.
2. **Tìm đúng registration/trust context** từ cấu hình và pending request. Nếu cần dùng một trường response chưa verified để lookup, trường đó **chỉ là gợi ý**, chưa có quyền quyết định trust.
3. **Xác minh chữ ký IdP** theo HTTP-Redirect/HTTP-POST profile và certificate IdP đã được cấp/nhập qua nguồn đáng tin.
4. **Issuer** của phản hồi phù hợp IdP Entity ID mong đợi.
5. **Load pending LogoutRequest** thuộc đúng browser/flow context và registration.
6. **LogoutResponse.InResponseTo** phải khớp **LogoutRequest.ID** đã lưu. Nếu không có pending hoặc ID sai, từ chối.
7. **RelayState** nếu có phải khớp state đã lưu và tuân thủ semantics của binding.
8. **Destination** là SLO response endpoint công khai của SP, thời gian/Version/Status phù hợp chính sách.
9. **Chống replay:** không xử lý thành công cùng một response nhiều lần; pending request không được consume hơn một lần.
10. **Xử lý StatusCode trung thực:** Success, PartialLogout, Requester, Responder khác nhau.
11. **Xóa hoặc cập nhật state** sau validation theo transaction policy và cleanup expired states.
12. **Không tạo lại Authentication** từ LogoutResponse; đây là phản hồi logout, không phải token đăng nhập.

Đây là **danh sách yêu cầu logic**. Spring Security có thể thực hiện thao tác lookup trước khi verify chữ ký để chọn certificate và state; điều đó có thể đúng khi chỉ dùng dữ liệu chưa verified làm **hint không đáng tin**. Không tự viết một thuật toán kiểm chữ ký XML mới vì muốn sắp xếp các bước theo thứ tự trên.

### 10.1. Mẫu sai: chỉ kiểm InResponseTo

~~~java
// KHONG AN TOAN: thieu signature, issuer, destination, status...
if (response.getInResponseTo().equals(pendingId)) {
    return "logout successful";
}
~~~

Attacker có thể viết XML chứa cùng chuỗi InResponseTo. Khi bỏ qua chữ ký và trust boundary, SP không biết response do ai tạo. **InResponseTo là correlation, không phải authentication.**

### 10.2. Mẫu điều kiện đúng về ý nghĩa

~~~text
responseValidatedBySamlLibrary
AND pendingRequestFoundForCorrectBrowserFlow
AND response.InResponseTo == pendingRequest.ID
AND relayStateMatchesIfUsed
AND registrationAndIdpIssuerMatch
AND destinationAndFreshnessValid
AND responseNotReplayed
AND statusPolicySatisfied
    => consume pending once, then report SLO outcome
~~~

Đây là **pseudocode**, không phải API Spring Security. Một số điều kiện đã nằm trong implementation validator của framework tùy phiên bản. Không tự bỏ validator mặc định rồi thay bằng vài phép so sánh Java.

## 11. Redis, JDBC và cluster: khi nào dùng custom repository?

Một ứng dụng nhiều instance có thể gặp:

~~~text
User -> Node A: LogoutRequest được lưu trong session/local memory A
IdP  -> Node B: LogoutResponse đến B
Node B: không tìm được pending -> InResponseTo không thể xác minh
~~~

Các giải pháp hợp lý:

- Nếu đã dùng **Spring Session chia sẻ HttpSession qua Redis/JDBC** và cookie/browser binding phù hợp, **HttpSessionLogoutRequestRepository vẫn có thể dùng được**.
- Nếu app stateless hoặc muốn quản lý pending state riêng, cung cấp **custom Saml2LogoutRequestRepository** dựa trên Redis/database có TTL và atomic consume.
- Session affinity có thể giúp trong một số topology nhưng không giải quyết hết trường hợp restart/failover. Cần bảo đảm behavior khi state mất.

**Không cần viết custom Redis repository chỉ vì có nhiều node** nếu HttpSession đã được phân tán an toàn. Cũng không được dùng một **static HashMap không TTL** làm nơi lưu state production: không chia sẻ giữa node, dễ mất khi restart, thiếu kiểm soát bộ nhớ/replay.

### 11.1. Hợp đồng cần giữ của custom repository

~~~text
saveLogoutRequest(logoutRequest, httpRequest, httpResponse):
    xác định requestId, registrationId, relayState
    gắn với browser flow / session context đã tin
    lưu state còn hạn, namespace rõ
    không đè state khác một cách im lặng

loadLogoutRequest(httpRequest):
    tìm state theo context/opaque correlation handle
    chỉ trả request thuộc đúng flow và registration
    không tự tin issuer/ID/KeyInfo trong response chưa verified

removeLogoutRequest(httpRequest, httpResponse):
    xóa state đúng request và context
    chống reuse và race giữa các worker
    có cleanup riêng cho dữ liệu hết hạn
~~~

Đây là **pseudocode cho API**, không phải Redis implementation runnable. Hợp đồng thực tế của interface chỉ nhận HttpServletRequest/HttpServletResponse, nên việc trích xuất correlation handle cần thống nhất với SAML filter và browser callback của framework.

### 11.2. Không dùng InResponseTo chưa kiểm chứng làm quyền truy cập kho

Một index nội bộ có thể dùng request ID:

~~~text
slo:pending:corp:_logout_001
~~~

Nhưng nếu server chấp nhận mọi InResponseTo trong body rồi truy xuất cả kho pending cross-tenant, attacker có thể dùng request giả để dò ID, gây resource exhaustion hoặc tạo cross-browser confusion.

Cần:

- Namespace theo tenant/application/registration đã tin.
- Browser-flow/session binding riêng hoặc opaque RelayState đủ entropy.
- TTL ngắn theo policy, giới hạn số lượng pending.
- Lookup read-only dựa trên hint cho tới khi signature và điều kiện khác được kiểm tra.
- Atomic state transition **pending -> completed**, không cho response lặp lại trở thành thành công.
- Hạn quyền đọc/ghi state, mã hóa storage khi cần và không log serialized SAML request chứa định danh người dùng.

### 11.3. Khi nào nên xóa state?

- Sau một response **đã được xác minh và xử lý** theo policy: consume một lần.
- Sau TTL: cleanup state hết hạn.
- Khi SLO bị hủy theo workflow quản trị: hủy có kiểm soát và audit nếu cần.

**Không xóa pending ngay khi một response chưa xác minh vừa xuất hiện**, vì attacker có thể gửi response giả để khiến request thật bị mất, gây từ chối dịch vụ. Tuy nhiên không được để state tồn tại vô hạn chỉ vì callback chưa đến.

## 12. Session invalidation, SameSite và cookie

Vòng đời SLO có khác biệt so với một biểu mẫu web thông thường:

1. Người dùng **đã đăng nhập** bấm logout tại SP.
2. SP có thể **hủy phiên xác thực local** trước khi gửi LogoutRequest.
3. Pending LogoutRequest phải còn truy xuất được cho callback trở về.
4. Browser di chuyển **cross-site** từ SP sang IdP rồi quay lại.
5. Callback có thể là **cross-site POST** hoặc Redirect, với hành vi cookie khác nhau.

### 12.1. Vì sao loadLogoutRequest có thể trả null?

- Browser đã làm mất cookie nhận biết pending flow.
- Cookie có **SameSite=Lax** và callback bằng cross-site POST không được gửi cookie trong tình huống đó.
- Session đã bị custom logout handler xóa sau khi state được lưu.
- Response đến một node khác khi session chưa được chia sẻ.
- Pending state quá hạn hoặc bị request logout thứ hai ghi đè.
- SLO URL, scheme, domain hoặc reverse proxy cấu hình sai.

**Không sửa bằng cách bỏ kiểm InResponseTo.** Cần kiểm tra browser Network, Set-Cookie/SameSite/Secure, các callback SAML, session store và giai đoạn tạo/hủy session.

### 12.2. Cookie SameSite và CSRF

Khi cần cross-site POST, cấu hình cookie có thể phải xét **SameSite=None; Secure** hoặc cơ chế correlation ngoài session tương đương theo chính sách và browser. Tuy nhiên:

- Không đặt SameSite=None toàn hệ thống mà không đánh giá CSRF, third-party cookies và toàn bộ endpoint.
- Không tắt CSRF cho mọi POST của ứng dụng chỉ để nhận SLO.
- SAML SLO endpoint là trường hợp protocol đặc thù, cần cơ chế xác minh message và correlation chặt.
- RelayState/cookie không thay chữ ký IdP.
- Kiểm tra đường dẫn public HTTPS sau TLS termination, forward headers chỉ từ proxy đáng tin.

Nếu SLO callback dùng Redirect/GET, hành vi cookie có thể khác POST, vì vậy **test đúng binding thực tế**, không suy từ trình duyệt test một lần.

## 13. Replay, nhiều tab và race condition

### 13.1. Một response được gửi hai lần

Giả sử request A còn pending. Response A hợp lệ đến, SP xác minh và hoàn thành. Sau đó chính response đó được gửi lại. Nếu state đã được consume một lần, lần thứ hai phải bị từ chối vì không còn pending request.

Một store phân tán nên có **compare-and-delete** hoặc transition **pending -> completed** nguyên tử, thay vì hai node đọc trạng thái pending rồi đều báo thành công. Bản ghi đã hoàn tất có thể được cleanup sau thời gian chống replay theo chính sách.

### 13.2. Hai tab logout cùng lúc

~~~text
Tab A: LogoutRequest.ID = _A, RelayState = state-A
Tab B: LogoutRequest.ID = _B, RelayState = state-B
~~~

Một repository chỉ lưu **một pending request trên mỗi session** có thể bị request B ghi đè A. Response A quay về không còn request phù hợp, buộc phải từ chối. Đó có thể là giới hạn được chấp nhận, nhưng phải **được kiểm thử và có thông báo chính xác**.

Nếu ứng dụng bắt buộc hỗ trợ nhiều logout flows song song, cần mô hình state **nhiều request theo ID + flow binding + TTL**, không đơn giản dùng key “pendingLogout” ghi đè.

### 13.3. Response đến muộn

Nếu pending đã hết hạn, dù chữ ký response đúng, SP không được tự tạo lại pending từ InResponseTo hoặc chọn “request gần nhất”. Trả lỗi/ thông báo rằng SLO toàn federation chưa được xác nhận, dọn state cũ theo policy và điều tra vì sao IdP xử lý quá lâu.

### 13.4. Trả Status lỗi sau khi logout local

SP có thể đã thoát phiên local trước khi IdP trả **PartialLogout**, **Requester** hoặc **Responder**. Trường hợp đó cần ghi nhận chính xác: **đã kết thúc phiên ứng dụng nhưng không thể xác nhận đăng xuất hết các SP liên quan**. Không khôi phục phiên đã thoát từ response thất bại.

## 14. Java 17 độc lập: lưu pending và kiểm tra correlation

Chương trình sau chạy với **JDK 17 trở lên**, không cần Spring. Nó mô phỏng repository đơn giản và các trường hợp:

- InResponseTo phải trỏ đúng pending request ID.
- RelayState, registration, IdP issuer và browser-flow binding phải khớp.
- Phản hồi chưa được thư viện SAML xác minh bị từ chối.
- Pending request phải còn trong TTL ba phút.
- Response hợp lệ chỉ được dùng một lần bằng **ConcurrentHashMap.remove(key, value)**.

**Giới hạn:** đây chỉ là mô hình correlation. Boolean **verifiedSamlResponse** phải được hình dung là **kết quả Spring Security/OpenSAML đã kiểm chữ ký và protocol**, không phải giá trị từ HTTP query/body. Chương trình **không parse LogoutResponse XML, không xác minh XMLDSig/Redirect signature, StatusCode, Destination hoặc Subject**. Nó không phải implementation Saml2LogoutRequestRepository production.

Tệp **LogoutCorrelationDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class LogoutCorrelationDemo {
    record Pending(String requestId, String registrationId,
            String expectedIdpIssuer, String relayState,
            String browserFlowId, Instant createdAt) {}

    record Reply(String inResponseTo, String registrationId,
            String actualIdpIssuer, String relayState,
            String browserFlowId, boolean verifiedSamlResponse) {}

    static final class PendingStore {
        private final Map<String, Pending> entries = new ConcurrentHashMap<>();
        private final Duration ttl = Duration.ofMinutes(3);

        void save(Pending request) {
            if (entries.putIfAbsent(request.requestId(), request) != null) {
                throw new IllegalStateException("Duplicate request ID");
            }
        }

        boolean complete(Reply reply, Instant now) {
            // In production, "verifiedSamlResponse" MUST come from
            // Spring Security/OpenSAML signature and protocol validation.
            if (!reply.verifiedSamlResponse()) return false;

            Pending expected = entries.get(reply.inResponseTo());
            if (expected == null) return false;
            if (now.isBefore(expected.createdAt())
                    || !now.isBefore(expected.createdAt().plus(ttl))) {
                return false;
            }
            if (!expected.registrationId().equals(reply.registrationId())
                    || !expected.expectedIdpIssuer().equals(reply.actualIdpIssuer())
                    || !expected.relayState().equals(reply.relayState())
                    || !expected.browserFlowId().equals(reply.browserFlowId())) {
                return false;
            }
            return entries.remove(expected.requestId(), expected);
        }
    }

    public static void main(String[] args) {
        Instant started = Instant.parse("2026-01-01T10:00:00Z");
        Instant now = started.plusSeconds(30);
        PendingStore store = new PendingStore();
        store.save(new Pending("_logout_001", "corp",
            "https://idp.example.test/issuer", "relay-abc",
            "browser-7", started));

        Reply valid = new Reply("_logout_001", "corp",
            "https://idp.example.test/issuer", "relay-abc",
            "browser-7", true);

        System.out.println("wrongInResponseTo=" + store.complete(
            new Reply("_other", "corp",
                "https://idp.example.test/issuer", "relay-abc",
                "browser-7", true), now));
        System.out.println("wrongRelayState=" + store.complete(
            new Reply("_logout_001", "corp",
                "https://idp.example.test/issuer", "changed",
                "browser-7", true), now));
        System.out.println("wrongBrowserFlow=" + store.complete(
            new Reply("_logout_001", "corp",
                "https://idp.example.test/issuer", "relay-abc",
                "browser-other", true), now));
        System.out.println("wrongIdpIssuer=" + store.complete(
            new Reply("_logout_001", "corp",
                "https://other.example.test/issuer", "relay-abc",
                "browser-7", true), now));
        System.out.println("untrustedResponse=" + store.complete(
            new Reply("_logout_001", "corp",
                "https://idp.example.test/issuer", "relay-abc",
                "browser-7", false), now));
        System.out.println("accepted=" + store.complete(valid, now));
        System.out.println("replayed=" + store.complete(valid, now));

        store.save(new Pending("_logout_old", "corp",
            "https://idp.example.test/issuer", "relay-old",
            "browser-7", started));
        System.out.println("expired=" + store.complete(
            new Reply("_logout_old", "corp",
                "https://idp.example.test/issuer", "relay-old",
                "browser-7", true), started.plusSeconds(181)));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 LogoutCorrelationDemo.java
java LogoutCorrelationDemo
~~~

**Stdout chính xác**:

~~~text
wrongInResponseTo=false
wrongRelayState=false
wrongBrowserFlow=false
wrongIdpIssuer=false
untrustedResponse=false
accepted=true
replayed=false
expired=false
~~~

Giải thích:

- **wrongInResponseTo=false:** không có LogoutRequest ID tương ứng.
- **wrongRelayState=false:** State đã bị đổi dù request ID khớp.
- **wrongBrowserFlow=false:** request đang chờ không thuộc đúng browser context.
- **wrongIdpIssuer=false:** không nhận response của IdP khác trong flow này.
- **untrustedResponse=false:** chưa qua SAML validation thì không xử lý thành công.
- **accepted=true:** trong demo, các điều kiện đều khớp và state được consume.
- **replayed=false:** cùng reply không thể được xử lý lần hai.
- **expired=false:** quá ba phút kể từ khi lưu request, flow không còn hợp lệ.

Đây là **một Map trong một JVM**, không phải store phân tán, không tự cleanup TTL và không xử lý XML. Để triển khai, cần dùng **Saml2LogoutRequestRepository** của Spring Security và một store/validator có lifecycle đúng.

## 15. Ma trận kiểm thử

| Ca kiểm thử | Dữ liệu | Kết quả |
| --- | --- | --- |
| SP SLO chuẩn | Request ID=_A đã lưu; IdP ký Response InResponseTo=_A | Validate toàn diện, consume pending |
| Sai InResponseTo | Pending _A nhưng Response trỏ _B | Từ chối |
| Thiếu InResponseTo | Response không tham chiếu request trong SP-initiated flow | Từ chối theo profile |
| Response.ID khác Request.ID | Response.ID=_R, InResponseTo=_A | Correlation vẫn có thể hợp lệ |
| Không có pending | Request hết TTL hoặc session mất | Fail closed |
| RelayState sai | ID đúng, RelayState khác | Từ chối |
| Sai browser flow | Response browser B thay cho A | Không dùng pending A |
| Sai registration | IdP A response được xử lý theo cấu hình B | Từ chối |
| Chữ ký IdP sai | XML chứa InResponseTo đúng nhưng signer lạ | Từ chối |
| Issuer sai | Response đến từ IdP khác | Từ chối |
| Destination sai | Response gửi sai URL SP SLO | Từ chối |
| Replay | Cùng Response gửi lại sau consume | Từ chối |
| Two-node race | Hai node nhận cùng Response | Chỉ một transition completed |
| PartialLogout | Status chỉ một phần | Không thông báo mọi phiên đã thoát |
| Responder/Requester | IdP báo lỗi | Phân loại, không báo SLO success |
| Browser đóng | Không có Response quay lại | State hết hạn; local logout có thể đã xong |
| Cross-site POST | Cookie session bị SameSite policy chặn | Kiểm tra cookie/binding, không bỏ InResponseTo |
| Cluster | State ở node A, callback node B | Shared store hoặc fail an toàn |
| Redis lỗi | Không đọc được pending state | Không tự chấp nhận Response |
| Hai tab logout | Pending A/B gần đồng thời | Behavior được định nghĩa và test |
| IdP-initiated | IdP gửi LogoutRequest | SP validate request, trả InResponseTo tới ID của IdP |
| Local-only | Không phát LogoutRequest | Không chờ LogoutResponse |
| SAML XML độc hại | DTD, external reference, oversized XML | Chặn/giới hạn parse |
| Tấn công ID đoán được | Cố đoán ID để trỏ InResponseTo | Signature và flow binding phải từ chối |

**Ngoài unit test Java, hãy kiểm thử luồng thật với IdP test** và browser network vì các lỗi thường chỉ lộ qua session cookies, SLO binding, proxy hoặc IdP không round-trip RelayState.

## 16. Lỗi thường gặp và cách chẩn đoán

| Lỗi | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| **loadLogoutRequest = null** | Session bị hủy, cookie không gửi, TTL hết, replica khác | Kiểm tra session lifecycle, SameSite, Redis/Spring Session |
| **InResponseTo mismatch** | IdP trả sai request, nhiều tab ghi đè, khác flow | So pending ID và response InResponseTo |
| **RelayState mismatch** | IdP không echo, proxy/query encode sai, khác browser | So state đã lưu và binding |
| **Invalid signature** | IdP cert/metadata sai, ký sai binding | Xác minh certificate và thuật toán, không tắt validator |
| **Invalid issuer** | Sử dụng sai registration | Đối chiếu IdP entityId và trust config |
| **Destination invalid** | SLO URL/proxy host khác public URL | Xem metadata và reverse proxy |
| **Không có SAML LogoutRequest** | Principal không phải SAML, chưa bật SLO, IdP không công bố SLO | Kiểm tra SAML principal/DSL/SingleLogoutService |
| **Chỉ lỗi trên POST** | Cookie SameSite ngăn callback cross-site | Test cookie Secure/SameSite và browser |
| **Chỉ lỗi cluster** | Pending nằm local node khác | Dùng Spring Session/distributed store |
| **Request cũ vẫn được dùng** | Không cleanup/consume một lần | TTL và atomic delete |
| **IdP báo PartialLogout** | Một số downstream SP không xử lý logout | Thông báo chính xác, audit |
| **Không logout toàn bộ dù local logout thành công** | IdP SLO timeout/không được hỗ trợ | Phân biệt local logout và federation SLO |

### 16.1. Thu thập log mà không lộ dữ liệu

Log có thể bao gồm **request ID**, registrationId, IdP Entity ID, thời điểm phát/nhận, TTL, mã lỗi validation và kết quả correlation ở mức phù hợp chính sách. Không ghi toàn bộ SAMLRequest/Response, NameID, SessionIndex, cookie, token hay RelayState chứa dữ liệu nhạy cảm vào log sản xuất.

### 16.2. Những “bản vá” không an toàn

- Bỏ kiểm InResponseTo vì “trong cluster hay mất session”.
- Khi không tìm thấy pending request thì mặc định lấy request gần nhất.
- Chấp nhận LogoutResponse unsigned nếu RelayState có vẻ khớp.
- Dùng InResponseTo từ XML chưa verified làm quyền đọc toàn bộ pending của tenant khác.
- Xóa state ngay khi nhận response giả, gây DoS cho SLO thật.
- Tắt CSRF trên mọi endpoint chỉ để xử lý callback.
- Gắn quyền user hoặc tenant với URL RelayState do người dùng tự đưa vào.

Cần sửa đúng lớp: **storage/cookie/cluster**, **binding/IdP config**, hoặc **signature/correlation validation**.

## 17. Checklist triển khai

- [ ] Đã xác định rõ local logout, RP-initiated SLO và AP-initiated SLO.
- [ ] IdP có SingleLogoutService với SLO endpoint và binding đúng.
- [ ] SP có signing credentials, IdP verification credentials và metadata trust tương ứng.
- [ ] Khi RP khởi tạo SLO, **LogoutRequest được lưu trước khi gửi**.
- [ ] Request ID duy nhất, không nhầm LogoutResponse.ID hoặc SessionIndex.
- [ ] LogoutResponse.InResponseTo so với đúng pending LogoutRequest.ID.
- [ ] RelayState và browser-flow context được bảo vệ, đối chiếu sau callback.
- [ ] Signature, issuer, Destination, time, Status và replay checks không bị bỏ qua.
- [ ] Pending state có TTL, giới hạn số lượng, cleanup và one-time consume.
- [ ] Custom repository tuân thủ load/save/remove contract của Spring Security.
- [ ] Session sau local logout vẫn giữ hoặc truy hồi được SLO pending theo thiết kế.
- [ ] Cross-site POST/Redirect đã kiểm thử cookie SameSite, Secure và HTTPS.
- [ ] Cluster A/B có shared session hoặc distributed repository; không dùng Map local production.
- [ ] Không dùng response chưa verified làm quyền chọn tenant, IdP key hoặc kho request.
- [ ] Có chính sách lỗi khi IdP timeout, trả PartialLogout hoặc không trả response.
- [ ] Đã có negative tests: thiếu/sai InResponseTo, replay, sai RelayState, wrong issuer, invalid signature, expiry.
- [ ] IdP-initiated LogoutRequest được xác minh và phản hồi dựa trên ID request của IdP.
- [ ] Log không làm lộ NameID/SessionIndex/SAML payload/cookie hoặc private key.

## 18. Câu hỏi tự kiểm tra

**1. Vì sao phải lưu LogoutRequest khi SP đã đăng xuất local?**

Vì LogoutResponse của IdP có thể đến sau khi Authentication local đã bị xóa. Pending request cho biết ID và ngữ cảnh ban đầu để kiểm InResponseTo/RelayState.

**2. LogoutResponse.ID có phải khớp LogoutRequest.ID?**

Không. LogoutResponse có ID riêng. **InResponseTo** mới tham chiếu ID của LogoutRequest gốc.

**3. Nếu InResponseTo đúng nhưng chữ ký IdP không hợp lệ thì sao?**

Phải từ chối. ID là dữ liệu có thể bị giả; nguồn phản hồi phải được xác minh bằng chữ ký và trust configuration.

**4. RelayState có thay InResponseTo được không?**

Không. RelayState giữ browser state; InResponseTo ràng buộc cấp message SAML. Cần cả hai theo flow đã thiết kế.

**5. Spring Security mặc định lưu SLO request ở đâu?**

Spring Security tài liệu hóa lưu trong **session**, với triển khai **HttpSessionLogoutRequestRepository** và khả năng thay qua **Saml2LogoutRequestRepository**.

**6. Spring Session đã dùng Redis thì có cần custom Redis repository không?**

Không bắt buộc nếu HttpSession đã chia sẻ đúng và callback browser vẫn mang cookie cần thiết. Phải kiểm thử thực tế.

**7. Response đến node khác nhưng state mất; có thể chấp nhận vì issuer đúng không?**

Không. Mất pending nghĩa là không chứng minh được correlation trong SP-initiated flow; cần fail closed và sửa storage.

**8. Trong IdP-initiated SLO, InResponseTo của LogoutResponse SP gửi trỏ đến đâu?**

Trỏ đến **ID của LogoutRequest do IdP vừa gửi**, không phải một request SP đã khởi tạo trước đó.

**9. PartialLogout với InResponseTo đúng có nghĩa logout toàn federation thành công?**

Không. StatusCode nói có một phần chưa hoàn tất; kết quả hiển thị cần chính xác.

**10. Có nên consume pending ngay khi nhận response chưa qua signature validation?**

Không. Điều đó có thể cho phép attacker gây mất state bằng response giả. Cần validation, atomic completion và TTL cleanup.

**11. Vì sao callback SLO cross-site POST có thể không thấy session?**

Cookie session có thể bị chặn bởi SameSite/third-party cookie policy hoặc session bị xóa. Cần kiểm tra cookie, binding và storage, không bỏ correlation.

**12. Người dùng đóng browser và IdP không trả response thì làm gì?**

Pending request hết hạn/cleanup. Phiên local có thể đã kết thúc, nhưng không tuyên bố federation SLO hoàn tất khi chưa có phản hồi được xác minh.

## 19. Tài liệu chuẩn để đối chiếu

- Spring Security, **Performing Single Logout**, RP/AP-initiated SLO và lưu LogoutRequest để kiểm RelayState/InResponseTo: https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Security Javadoc, **Saml2LogoutRequestRepository** và các method load/save/remove: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/Saml2LogoutRequestRepository.html
- Spring Security Javadoc, **HttpSessionLogoutRequestRepository**, lưu SLO request trong HttpSession: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/HttpSessionLogoutRequestRepository.html
- Spring Security Javadoc, **Saml2LogoutRequest**, ID, RelayState và registration: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/logout/Saml2LogoutRequest.html
- Spring Security, **SAML 2.0 Login Overview**, phân biệt AuthnRequest SSO với LogoutRequest SLO: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- OASIS, **SAML 2.0 Technical Overview**, mục Single Logout Profile: https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html
- OASIS, **SAML V2.0 Profiles**, đặc tả Single Logout Profile: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS, **SAML V2.0 Bindings**, HTTP-Redirect/POST và RelayState: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- Microsoft Entra ID, **Single Sign-Out SAML Protocol**, ví dụ LogoutResponse InResponseTo: https://learn.microsoft.com/en-us/entra/identity-platform/single-sign-out-saml-protocol

**Ghi nhớ:** trong **SP-initiated SAML2 Single Logout**, SP **lưu LogoutRequest.ID trước khi đi IdP** và chỉ xử lý LogoutResponse khi **InResponseTo khớp request pending trong đúng flow**. Spring Security cung cấp **Saml2LogoutRequestRepository**, mặc định dựa trên HttpSession, để khôi phục state và đối chiếu InResponseTo/RelayState. Tuy vậy, correlation chỉ là một lớp: **chữ ký IdP, issuer, destination, time, StatusCode, TTL, browser/session binding và chống replay** vẫn phải được bảo đảm trước khi kết luận SLO thành công.