# SessionRegistry và theo dõi phiên phục vụ logout

Một OpenID Provider (OP) cần biết phiên đăng nhập nào đang tồn tại để thực hiện logout đúng người dùng và đúng phiên. Khi End-User mở nhiều tab, đăng nhập từ nhiều trình duyệt hoặc có nhiều thiết bị, một tài khoản có thể sở hữu nhiều HTTP sessions đồng thời. Nếu OP chỉ biết access token mà không theo dõi phiên đăng nhập, việc logout tại browser hiện tại có thể không kết thúc đúng phiên; logout một phiên cũng có thể vô tình ảnh hưởng tất cả phiên của người dùng.

Trong Spring Authorization Server, **Spring Security SessionRegistry** là thành phần theo dõi các phiên đã xác thực. Khi OIDC được bật, SessionRegistry được dùng bởi SessionAuthenticationStrategy mặc định của OAuth2 Authorization Endpoint để đăng ký phiên mới. Khi End-User yêu cầu RP-Initiated Logout, OidcLogoutAuthenticationProvider sử dụng registry để tìm SessionInformation gắn với người dùng đang đăng xuất; logout success handler thực hiện thao tác logout.

Bài học thuộc chương **OIDC Logout**, module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**. Phạm vi module là học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Trọng tâm của bài là SessionRegistry, vòng đời HttpSession, cách Spring Authorization Server đăng ký phiên và cách dùng dữ liệu phiên trong logout.

> **Điểm cần nhớ:** SessionRegistry là chỉ mục theo dõi principal và session ID. Nó không phải kho lưu toàn bộ nội dung HttpSession, không phải token store và không tự động thu hồi mọi access token/refresh token khi browser logout.

## 1. Vì sao Authorization Server phải theo dõi phiên?

Trong Authorization Code Flow, End-User tương tác với browser để đăng nhập tại OP. Sau khi xác thực, OP tạo hoặc sử dụng một HttpSession để duy trì trạng thái đăng nhập. Các request authorization tiếp theo có thể dùng lại session đó mà không yêu cầu người dùng nhập lại mật khẩu.

Ví dụ một người dùng đăng nhập tại:

- Browser trên laptop;
- Browser trên điện thoại;
- Một profile trình duyệt riêng cho môi trường quản trị.

Đây là các HttpSession khác nhau, dù cùng một principal. Khi người dùng chọn logout ở một browser, OP cần xác định session hiện tại và xử lý đúng phạm vi logout. Khi một session hết hạn hoặc bị invalidated, thông tin theo dõi cũng phải được dọn khỏi registry.

### 1.1. Phân biệt các loại phiên và token

| Thành phần | Được lưu ở đâu? | Ý nghĩa |
|---|---|---|
| OP HttpSession | Servlet container hoặc Spring Session | Phiên đăng nhập của End-User tại Authorization Server |
| SessionInformation | SessionRegistry | Metadata về principal, session ID, last request và trạng thái expire |
| OAuth2 Authorization | OAuth2AuthorizationService | Authorization và các token đã phát hành |
| ID Token | RP nhận từ token endpoint | Bằng chứng OIDC về authentication và subject |
| Access Token | Client/RP gửi đến Resource Server | Credential truy cập protected resource |
| RP local session | Ứng dụng client | Phiên đăng nhập của người dùng tại từng Relying Party |

Không đồng nhất OP session với RP session. Một người dùng có thể đăng nhập vào OP một lần rồi tạo nhiều RP sessions ở các ứng dụng khác nhau. SessionRegistry trong Spring Authorization Server theo dõi phiên đã xác thực tại OP.

### 1.2. Logout cần xác định phạm vi

Một thao tác logout có thể mang các ý nghĩa khác nhau:

- Kết thúc phiên browser hiện tại tại OP;
- Kết thúc mọi OP sessions của một End-User;
- Yêu cầu một RP kết thúc session của người dùng;
- Thông báo logout đến nhiều RP qua front-channel hoặc back-channel;
- Thu hồi access/refresh tokens theo chính sách.

Các thao tác này có thể phối hợp nhưng không tự động tương đương nhau. Cần xác định rõ phạm vi trước khi thiết kế session tracking.

## 2. SessionRegistry là gì?

org.springframework.security.core.session.SessionRegistry là interface quản lý các SessionInformation đã biết. SessionRegistryImpl là implementation mặc định của Spring Security.

Về mặt khái niệm, registry duy trì hai hướng tra cứu:

~~~text
principal  -> danh sách session IDs
session ID -> SessionInformation(principal, lastRequest, expired)
~~~

Nhờ đó ứng dụng có thể tra cứu các phiên theo người dùng hoặc tìm thông tin của một session cụ thể.

### 2.1. Registry không phải Session Store

SessionRegistryImpl không lưu toàn bộ SecurityContext, request attributes, session attributes hoặc dữ liệu nghiệp vụ của HttpSession. Nó chỉ giữ thông tin cần cho quản lý phiên. Việc invalidation vẫn cần Servlet API, Spring Session hoặc logout handlers phù hợp.

Ví dụ:

- SessionRegistry biết session ID S1 thuộc principal user-42;
- Servlet container hoặc Spring Session giữ nội dung thực của S1;
- Logout handler dùng session ID để kết thúc phiên;
- Khi session bị destroy, event lifecycle giúp registry xóa record tương ứng.

Nếu registry còn record nhưng session thực tế đã hết hạn, dữ liệu registry đã stale. Ngược lại, nếu session vẫn tồn tại nhưng registry không có record, logout/concurrent-session logic có thể không tìm thấy phiên.

### 2.2. SessionRegistryImpl mặc định

SessionRegistryImpl giữ cấu trúc dữ liệu trong bộ nhớ của JVM và lắng nghe các session lifecycle events. Nó là lựa chọn phù hợp cho ứng dụng đơn node hoặc môi trường development/test.

Khi OIDC được bật trong Spring Authorization Server:

- Nếu không có bean SessionRegistry, framework dùng SessionRegistryImpl;
- Nếu ứng dụng khai báo bean SessionRegistryImpl, cần đăng ký HttpSessionEventPublisher để gửi session lifecycle events;
- Nếu Spring Security Concurrent Session Control cũng được sử dụng, nên chia sẻ cùng một bean SessionRegistry.

## 3. Luồng đăng ký và kết thúc phiên

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End-User
    participant B as Browser
    participant OP as Authorization Server
    participant STR as SessionAuthenticationStrategy
    participant SR as SessionRegistry
    participant E as HttpSessionEventPublisher

    U->>B: Mở authorization request
    B->>OP: GET authorization endpoint
    OP->>OP: Kiểm tra SecurityContext / đăng nhập
    OP->>STR: Xử lý session sau authentication
    STR->>SR: registerNewSession(sessionId, principal)
    SR-->>STR: Session được theo dõi
    OP-->>B: Tiếp tục consent / authorization response
    Note over U,SR: Người dùng tiếp tục dùng OP session
    U->>B: Logout / session bị timeout
    B->>OP: Logout hoặc HttpSession bị invalidate
    OP->>OP: Logout handlers / session invalidation
    OP->>E: Servlet session lifecycle event
    E->>SR: SessionDestroyedEvent
    SR->>SR: remove session information
~~~

Spring Authorization Server gắn session registration với default SessionAuthenticationStrategy của OAuth2 Authorization Endpoint. Vì vậy, cần giữ đúng filter chain và session strategy khi tùy chỉnh Authorization Server. Nếu thay strategy mặc định, phải bảo đảm logic đăng ký phiên vẫn được thực hiện.

## 4. Các API quan trọng của SessionRegistry

| Phương thức | Công dụng |
|---|---|
| registerNewSession(sessionId, principal) | Đăng ký session mới cho principal |
| getSessionInformation(sessionId) | Lấy SessionInformation theo session ID |
| getAllSessions(principal, includeExpiredSessions) | Liệt kê các session của principal |
| getAllPrincipals() | Lấy các principal đã biết |
| refreshLastRequest(sessionId) | Cập nhật thời điểm request cuối |
| removeSessionInformation(sessionId) | Xóa record session khỏi registry |

Ví dụ tra cứu các session:

~~~java
List<SessionInformation> sessions =
    sessionRegistry.getAllSessions(principal, false);

for (SessionInformation session : sessions) {
    String sessionId = session.getSessionId();
    Date lastRequest = session.getLastRequest();
    boolean expired = session.isExpired();
}
~~~

Đây là ví dụ sử dụng API để quan sát session. Không hiển thị raw session ID cho người dùng cuối hoặc ghi nó vào log công khai; session ID là dữ liệu nhạy cảm có thể giúp chiếm quyền phiên.

### 4.1. Tìm session theo ID

~~~java
SessionInformation information =
    sessionRegistry.getSessionInformation(sessionId);

if (information != null && !information.isExpired()) {
    Object principal = information.getPrincipal();
    // Áp dụng policy hoặc điều tra session đã được xác định.
}
~~~

getSessionInformation có thể trả về session đã được đánh dấu expired. Session đã destroyed thì không còn được trả về nếu lifecycle event đã được xử lý.

### 4.2. Xóa record registry

~~~java
sessionRegistry.removeSessionInformation(sessionId);
~~~

Phương thức này chỉ xóa thông tin khỏi registry. Nó **không thay thế** HttpSession.invalidate() hoặc việc xóa session khỏi Spring Session repository. Nếu chỉ xóa registry record, session thực tế có thể tiếp tục hoạt động.

## 5. Vòng đời SessionInformation

Spring Security phân biệt ba trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| **Active** | Session đang được theo dõi và chưa bị đánh dấu kết thúc |
| **Expired** | Spring Security muốn kết thúc session, ví dụ do giới hạn concurrent sessions |
| **Destroyed** | Session thực tế đã bị invalidate hoặc servlet container đã hủy |

### 5.1. expireNow() không trực tiếp invalidate session

~~~java
SessionInformation information =
    sessionRegistry.getSessionInformation(sessionId);

if (information != null) {
    information.expireNow();
}
~~~

expireNow() đánh dấu session expired. Với Concurrent Session Control, ConcurrentSessionFilter kiểm tra trạng thái này ở request tiếp theo, gọi logout handlers và thường invalidate session. Nó không có nghĩa Servlet container đã hủy session ngay tại thời điểm gọi.

Điểm này quan trọng khi triển khai logout:

- Đánh dấu expired là một trạng thái trong registry;
- Invalidate là thao tác trên session store/container;
- Destroyed event là tín hiệu lifecycle để dọn record;
- Logout handlers có thể xóa SecurityContext, cookie và dữ liệu liên quan.

Không dùng expireNow() như một thay thế chung cho toàn bộ logout workflow.

### 5.2. Session timeout và explicit logout

Session có thể kết thúc do người dùng chủ động logout, session timeout do inactivity, administrator/security policy kết thúc phiên, concurrent session policy đánh dấu phiên expired hoặc servlet container/session store hủy session.

Tất cả đường đi này cần cập nhật registry nhất quán. Nếu một đường đi bypass lifecycle event, stale records có thể tích tụ.

## 6. Spring Authorization Server sử dụng SessionRegistry khi nào?

Khi OIDC 1.0 được bật, Spring Authorization Server dùng SessionRegistry để theo dõi authenticated sessions. Default SessionAuthenticationStrategy liên kết với OAuth2 Authorization Endpoint đăng ký session mới. Khi End-User yêu cầu OIDC Logout, OidcLogoutAuthenticationProvider dùng registry để tra SessionInformation liên quan đến End-User đang logout.

Các thành phần liên quan:

| Thành phần | Vai trò |
|---|---|
| OAuth2AuthorizationServerConfigurer | Bật và cấu hình các protocol endpoints |
| OIDC configurer | Bật OIDC endpoints, trong đó có Logout Endpoint |
| SessionAuthenticationStrategy | Đăng ký authenticated session trong quá trình authorization |
| SessionRegistry | Tra cứu principal/session metadata |
| OidcLogoutAuthenticationProvider | Xác thực RP-Initiated Logout request và tra session |
| OidcLogoutAuthenticationSuccessHandler | Xử lý logout sau khi provider thành công |
| HttpSessionEventPublisher | Phát session lifecycle events cho registry |

OidcLogoutAuthenticationProvider nhận RegisteredClientRepository, OAuth2AuthorizationService và SessionRegistry trong constructor. Điều này cho thấy logout cần kết hợp client registration, authorization state và session tracking.

### 6.1. Bật OIDC trên Authorization Server

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .oidc(Customizer.withDefaults())
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Đây là khung filter chain cho Spring Authorization Server 1.5.x. Ứng dụng vẫn cần các beans về RegisteredClient, authorization/token services, issuer, signing keys và application login.

### 6.2. Endpoint logout không phải endpoint logout của mọi ứng dụng

OIDC Logout Endpoint của Authorization Server phục vụ RP-Initiated Logout tại OP. Nó xử lý request theo OIDC và dùng phiên đăng nhập tại OP. Logout URL trong một Spring Security OAuth2 Client application lại là một cơ chế khác, phục vụ phiên local của RP.

## 7. Khai báo SessionRegistryImpl và HttpSessionEventPublisher

Nếu ứng dụng muốn dùng rõ ràng cùng một registry cho OIDC logout và concurrent-session control, khai báo:

~~~java
@Bean
SessionRegistry sessionRegistry() {
    return new SessionRegistryImpl();
}

@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

HttpSessionEventPublisher chuyển các Servlet HttpSession lifecycle events thành Spring application events, ví dụ session created, destroyed và session ID changed. SessionRegistryImpl lắng nghe các session events để cập nhật dữ liệu theo dõi.

### 7.1. Vì sao cần publisher?

Khi session bị timeout hoặc invalidate, SessionRegistryImpl cần biết sự kiện để loại bỏ SessionInformation. Nếu không có publisher, record của session đã chết có thể còn trong registry. Hậu quả có thể gồm:

- getAllSessions trả về dữ liệu stale;
- Concurrent session limit đếm nhầm session cũ;
- Logout lookup không tìm thấy session thực tế hoặc nhìn thấy record không còn hợp lệ;
- Memory tăng do record không được dọn.

### 7.2. Spring Boot và servlet listener

Trong cấu hình Spring Boot, khai báo HttpSessionEventPublisher bằng @Bean như ví dụ là cách được Spring Authorization Server hướng dẫn. Ở ứng dụng servlet cấu hình thủ công, có thể đăng ký listener trong deployment descriptor hoặc qua servlet context theo mô hình triển khai.

Không tạo nhiều publisher cho cùng một servlet context nếu không có lý do rõ ràng; duplicate event processing có thể khiến việc chẩn đoán lifecycle khó hơn.

## 8. Principal phải ổn định để registry tìm đúng phiên

SessionRegistryImpl nhóm các session theo principal. Principal dùng làm key cần có equals() và hashCode() ổn định trong suốt thời gian được đăng ký.

Khuyến nghị:

- Dùng principal object đại diện cho user identity ổn định;
- equals()/hashCode() dựa trên identifier ổn định, không dựa trên mutable display name;
- Không dùng raw access token làm principal;
- Không dùng object mới mỗi request mà không có equality semantics;
- Trong custom registry phân tán, chuẩn hóa principal thành một key dạng string nhất quán.

Ví dụ một custom principal có thể dùng subject nội bộ bất biến:

~~~java
public final class ApplicationPrincipal implements UserDetails {

    private final String userId;
    private final String username;

    public ApplicationPrincipal(String userId, String username) {
        this.userId = userId;
        this.username = username;
    }

    public String getUserId() {
        return this.userId;
    }

    @Override
    public String getUsername() {
        return this.username;
    }

    // equals() và hashCode() phải dùng userId ổn định.
    // Các UserDetails methods khác được triển khai theo policy ứng dụng.
}
~~~

Đây là skeleton minh họa; một UserDetails production phải triển khai đầy đủ contract. Điểm quan trọng là định danh dùng để nhóm session không đổi khi tên hiển thị hoặc email được cập nhật.

## 9. Kết hợp với Concurrent Session Control

Spring Security có thể giới hạn số phiên đồng thời cho một principal. Concurrent Session Control và OIDC logout cùng cần tra cứu session, nên Spring Authorization Server khuyến nghị dùng chung một SessionRegistry bean khi bật cả hai tính năng.

Ví dụ application login chain:

~~~java
@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http,
        SessionRegistry sessionRegistry) throws Exception {

    http
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .sessionManagement(session -> session
            .maximumSessions(2)
            .sessionRegistry(sessionRegistry)
        );

    return http.build();
}
~~~

Đây là ví dụ cấu hình giới hạn hai sessions cho mỗi principal. Tùy ứng dụng, có thể chọn maxSessionsPreventsLogin(true) để từ chối login mới hoặc cho login mới và đánh dấu session cũ expired. Hãy lựa chọn policy phù hợp UX và bảo mật.

### 9.1. Chia sẻ registry thực sự

Không tạo một SessionRegistryImpl cho Authorization Server và một registry khác cho Concurrent Session Control. Nếu hai filter chains dùng hai instance khác nhau, một bên có thể đăng ký session trong khi bên kia không thấy session đó.

Inject cùng bean qua method parameters để bảo đảm cùng một instance được sử dụng.

### 9.2. Session fixation protection

Spring Security có session fixation protection và có thể thay session ID sau authentication. Registry cần theo kịp thay đổi session ID. Đừng tự lưu session ID vào database một lần rồi giả định nó không đổi. Dùng lifecycle events và cơ chế session management được hỗ trợ để duy trì liên kết.

## 10. RP-Initiated Logout sử dụng session tracking

Theo OIDC RP-Initiated Logout, RP điều hướng User Agent tới Logout Endpoint của OP. URL thường được lấy từ end_session_endpoint trong OpenID Provider Configuration.

Request có thể chứa:

| Parameter | Ý nghĩa |
|---|---|
| id_token_hint | ID Token trước đó OP đã cấp cho RP; được khuyến nghị để gợi ý End-User/session |
| post_logout_redirect_uri | URI RP muốn browser quay về sau logout |
| state | Giá trị RP gửi để liên kết response với logout request |
| client_id | Có thể dùng trong các trường hợp phù hợp theo OIDC Logout specification |
| logout_hint | Gợi ý định danh End-User theo extension/policy được hỗ trợ |

Ví dụ redirect:

~~~http
GET /connect/logout?id_token_hint=ID_TOKEN_VALUE&post_logout_redirect_uri=https%3A%2F%2Fportal.example.com%2Flogged-out&state=RANDOM_STATE HTTP/1.1
Host: identity.example.com
~~~

URL và endpoint path trong ví dụ phụ thuộc end_session_endpoint thực tế của OP. Không hardcode path nếu RP có thể lấy từ discovery.

### 10.1. Từ logout request tới SessionInformation

Trong Spring Authorization Server:

1. OidcLogoutEndpointFilter nhận RP-Initiated Logout request.
2. OidcLogoutAuthenticationConverter chuyển HTTP request thành OidcLogoutAuthenticationToken.
3. OidcLogoutAuthenticationProvider xác thực request, phối hợp RegisteredClientRepository, OAuth2AuthorizationService và SessionRegistry.
4. Provider tra SessionInformation gắn với End-User đang yêu cầu logout.
5. OidcLogoutAuthenticationSuccessHandler xử lý logout sau khi authentication thành công.
6. Logout handlers kết thúc phiên OP và điều hướng theo response/redirect policy.

SessionRegistry là phần giúp provider tìm đúng session đã được đăng ký. Nếu registry không có dữ liệu hoặc dữ liệu stale, logout có thể không tìm thấy session như mong đợi.

### 10.2. Redirect URI phải được kiểm tra

Spring Authorization Server có default OidcLogoutAuthenticationValidator để kiểm tra post_logout_redirect_uri. Giá trị này phải phù hợp với post-logout redirect URIs đã đăng ký cho client. Không chấp nhận URL tùy ý từ query parameter; nếu không, endpoint có thể trở thành open redirect.

Nếu thay đổi validation, custom validator phải ném OAuth2AuthenticationException khi request không hợp lệ. Không bỏ validation chỉ để tránh lỗi redirect.

## 11. OP session logout không đồng nghĩa token revocation

SessionRegistry theo dõi phiên đăng nhập của End-User tại OP. Khi RP-Initiated Logout kết thúc HttpSession, người dùng không còn phiên browser đó để tiếp tục authorization mà không đăng nhập lại. Tuy nhiên, thao tác này không tự động chứng minh mọi access token hoặc refresh token đã được thu hồi.

| Tài nguyên | Ảnh hưởng khi OP HttpSession logout |
|---|---|
| Browser session tại OP | Được logout/invalidate theo logout handler |
| SessionInformation | Được dọn khi lifecycle event được phát và xử lý |
| Authorization record | Vẫn do OAuth2AuthorizationService quản lý |
| Access token JWT đã cấp | Có thể vẫn hợp lệ đến exp nếu không có cơ chế revocation/denylist bổ sung |
| Opaque access token | Có thể bị introspection đánh giá inactive nếu authorization/token state được revoke |
| Refresh token | Cần chính sách revoke riêng theo authorization/session lifecycle |
| RP local session | Cần front-channel/back-channel notification hoặc RP tự logout |

Vì vậy, hãy thiết kế logout như nhiều hành động phối hợp: kết thúc OP session, xử lý authorization/token state theo policy, và thông báo các RPs nếu deployment hỗ trợ logout propagation. Không dùng SessionRegistry như thể nó là token revocation store.

### 11.1. Khi nào cần revoke authorization hoặc refresh token?

Một số hệ thống yêu cầu khi người dùng logout thì refresh token gắn với phiên đó không còn được dùng để cấp access token mới. Khi đó, ứng dụng cần liên kết authorization/token với session hoặc có một policy rõ để revoke các token liên quan. Việc này cần được thiết kế với OAuth2AuthorizationService và token lifecycle.

Không revoke tất cả authorization của cùng subject nếu policy chỉ muốn kết thúc một browser session. Một user có thể đang đăng nhập ở thiết bị khác hoặc có một client khác cần tiếp tục hoạt động.

### 11.2. JWT access token có thể tiếp tục sống

Resource Server xác minh JWT offline thường kiểm tra chữ ký, issuer, audience và expiry. Invalidate OP HttpSession không làm thay đổi chữ ký JWT đã phát hành. Nếu cần logout có hiệu lực ngay đối với JWT, phải dùng một cơ chế bổ sung như token denylist, introspection, token version/session state check hoặc access-token lifetime ngắn theo threat model.

## 12. Phân biệt RP-Initiated Logout, Front-Channel và Back-Channel Logout

OIDC định nghĩa các cơ chế logout có mục đích khác nhau:

| Cơ chế | Ai khởi tạo? | Kênh truyền | Mục đích |
|---|---|---|---|
| RP-Initiated Logout | RP | Browser redirect tới OP | RP yêu cầu OP logout End-User |
| Front-Channel Logout | OP | Browser/User Agent | OP thông báo logout tới các RPs qua browser |
| Back-Channel Logout | OP | HTTP server-to-server | OP gửi Logout Token trực tiếp đến RP |
| Local application logout | Ứng dụng | Local session/logout handler | Kết thúc phiên tại chính ứng dụng đó |

RP-Initiated Logout là request từ RP tới OP. Front-channel và back-channel là cơ chế OP thông báo tới RP. Có thể dùng riêng hoặc kết hợp theo khả năng của OP và RP.

### 12.1. Back-Channel Logout dùng Logout Token

Khi OP hỗ trợ Back-Channel Logout, OP gửi HTTP POST đến back-channel logout URI đã đăng ký của RP. Body có tham số logout_token chứa một JWT được ký, xác định người dùng/phiên cần kết thúc.

Logout Token cần được RP kiểm tra, gồm các nội dung quan trọng:

- Chữ ký và thuật toán;
- Issuer và audience;
- Issued-at;
- jti (định danh duy nhất của Logout Token);
- Có claim events với event URI của back-channel logout;
- Có ít nhất một trong hai claim sub hoặc sid;
- Không có nonce;
- Có thể kiểm tra jti đã được nhận trước đó để chống replay.

Nếu Logout Token có sid, RP kết thúc phiên được liên kết với OP session đó. Nếu chỉ có sub, RP kết thúc các phiên của End-User tương ứng tại RP theo semantics của specification.

### 12.1.1. Discovery và client registration cho Back-Channel Logout

OP có thể công bố các metadata boolean:

- backchannel_logout_supported: OP hỗ trợ Back-Channel Logout;
- backchannel_logout_session_supported: OP có thể đưa sid vào Logout Token; khi hỗ trợ, sid cũng được đưa vào ID Tokens tương ứng.

RP đăng ký backchannel_logout_uri. Nếu RP yêu cầu sid trong Logout Token, client registration có thể khai báo backchannel_logout_session_required. Chỉ công bố support khi OP thực sự lưu được thông tin RPs đã đăng nhập và có thể gửi Logout Token hợp lệ tới các URI đã đăng ký.

SessionRegistry tại OP không tự triển khai toàn bộ Back-Channel Logout. Nó theo dõi OP HttpSession; việc lưu danh sách RPs đã đăng nhập, phát Logout Token và gửi request tới backchannel_logout_uri là các phần của một workflow khác.

### 12.2. sid không phải Servlet session ID

OIDC sid là định danh phiên do OP cấp và có ý nghĩa trong phạm vi issuer. Servlet session ID là định danh HttpSession tại một application/container. Hai giá trị có thể được liên kết trong một mapping, nhưng không được coi là cùng một giá trị.

SessionRegistry ở OP theo dõi principal và servlet session ID của OP. Để xử lý Back-Channel Logout ở RP, ứng dụng RP cần một registry riêng ánh xạ OIDC provider session (sid) và client registration với RP local session.

### 12.3. Không nhầm SessionRegistry của OP với OidcSessionRegistry của RP

| Registry | Nằm ở đâu? | Theo dõi gì? |
|---|---|---|
| Spring Security SessionRegistry | Authorization Server / OP | Authenticated HttpSessions tại OP |
| Spring Security OidcSessionRegistry | OAuth2 Client / RP | Liên kết OP session ID và local RP session |
| Spring Session repository | Ứng dụng dùng Spring Session | Nội dung và vòng đời session thực tế |

Spring Security OAuth2 Client có OidcSessionRegistry phục vụ Back-Channel Logout. Đó là abstraction khác với SessionRegistry được Spring Authorization Server dùng trong RP-Initiated Logout. Không inject nhầm registry của RP vào Authorization Server.

## 13. SessionRegistry trong môi trường nhiều node

SessionRegistryImpl lưu dữ liệu trong bộ nhớ của một JVM. Nếu Authorization Server chạy nhiều pods, mỗi node có thể có một registry riêng:

~~~text
Browser -> Load Balancer -> Node A (SessionRegistry A)
                         -> Node B (SessionRegistry B)
                         -> Node C (SessionRegistry C)
~~~

Giả sử login/authorization request đi qua Node A và session được đăng ký tại registry A. Logout request sau đó đi qua Node B. Nếu Node B không thấy record, OIDC Logout Provider có thể không tìm được SessionInformation mong đợi.

Sticky session có thể làm giảm xác suất request chuyển node, nhưng không thay thế một registry/session store dùng chung. Node có thể restart, failover hoặc request được gửi tới node khác.

### 13.1. Các lựa chọn

| Giải pháp | Đặc điểm | Phù hợp |
|---|---|---|
| SessionRegistryImpl per-node | Đơn giản, in-memory | Single node, dev/test |
| Shared/custom SessionRegistry | Registry state được chia sẻ qua database/cache | Cluster cần lookup nhất quán |
| Spring Session + SpringSessionBackedSessionRegistry | Session data và lookup dựa trên Spring Session repository | Cluster dùng Redis/JDBC hoặc repository tương thích |
| Custom session index | Lưu principal/session mapping và metadata riêng | Multi-tenant hoặc logout policy phức tạp |

### 13.2. Spring Session và SpringSessionBackedSessionRegistry

Spring Session cung cấp FindByIndexNameSessionRepository và SpringSessionBackedSessionRegistry. Implementation này truy xuất SessionInformation dựa trên Spring Session thay vì duy trì một map riêng trong bộ nhớ, giúp concurrent-session management hoạt động trong môi trường clustered.

Ví dụ cấu hình khái niệm:

~~~java
@Bean
SessionRegistry sessionRegistry(
        FindByIndexNameSessionRepository<? extends Session> sessionRepository) {

    return new SpringSessionBackedSessionRegistry<>(sessionRepository);
}
~~~

Generic type cụ thể có thể cần điều chỉnh theo repository đang dùng (ví dụ RedisIndexedSessionRepository hoặc JdbcIndexedSessionRepository). Quan trọng là repository phải có khả năng tìm session theo principal index.

### 13.3. Principal index phải được populate

FindByIndexNameSessionRepository định nghĩa PRINCIPAL_NAME_INDEX_NAME để tìm session theo principal name. Spring Session không tự biết mọi cơ chế authentication; ứng dụng cần bảo đảm index principal được điền.

SpringSessionBackedSessionRegistry cũng cần tạo cùng một string representation của principal mà repository đã index. Nếu Authentication principal được chuẩn hóa thành user ID nhưng session repository index theo username, lookup có thể trả rỗng dù session vẫn tồn tại.

Kiểm thử phải bao gồm login trên node A, logout/lookup trên node B, query session theo principal index, invalidate session và xác minh repository không còn trả session, thay đổi session ID và xác minh mapping được cập nhật.

### 13.4. Đồng bộ session store và registry

Nếu registry tùy chỉnh nằm trong Redis nhưng HttpSession vẫn lưu trong memory của từng node, registry có thể trỏ đến session mà node hiện tại không thể invalidate. Session tracking và session storage phải dùng một kiến trúc nhất quán: cùng distributed store hoặc có cơ chế gọi đúng node/session owner.

## 14. Thiết kế một custom SessionRegistry

Chỉ triển khai custom registry khi có yêu cầu rõ như multi-node, multi-tenant, session audit hoặc policy lookup riêng. Implementation phải đáp ứng contract của SessionRegistry và không được trả kết quả không nhất quán giữa các method.

### 14.1. Những dữ liệu nên lưu

| Field | Mục đích |
|---|---|
| session_id | Định danh session thực tế, bảo vệ như secret |
| principal_key | Subject/user identifier ổn định |
| created_at | Thời điểm đăng ký |
| last_request_at | Request cuối được quan sát |
| expired | Trạng thái được đánh dấu expired |
| tenant_id | Phân vùng tenant nếu ứng dụng multi-tenant |
| node/owner | Chỉ khi cần định tuyến tới session owner |

Không lưu access token hoặc refresh token trong session registry chỉ để tiện logout. Token lifecycle thuộc authorization/token service.

### 14.2. Contract và concurrency

Custom registry cần bảo đảm:

- registerNewSession xử lý session ID đã tồn tại theo một quy tắc rõ ràng;
- getAllSessions không trả session đã destroyed;
- getSessionInformation trả đúng session hoặc null;
- refreshLastRequest không hồi sinh session đã expired/destroyed;
- removeSessionInformation là idempotent;
- Principal normalization giống nhau ở mọi node;
- Session ID rotation cập nhật mapping nguyên tử;
- Cleanup khi timeout/invalidate có thể chạy lặp an toàn;
- Các thao tác đồng thời không tạo hai record mâu thuẫn.

### 14.3. TTL không được vượt vòng đời session

Nếu dùng Redis/database index, TTL của record registry phải phù hợp với session timeout và gia hạn session. Record registry hết hạn sớm sẽ khiến logout lookup thất bại; record tồn tại quá lâu gây stale sessions và tăng rủi ro memory/data retention.

Nên có cleanup job như biện pháp dự phòng, nhưng nguồn sự thật vẫn phải là session repository/container. Cleanup job không nên xóa record chỉ dựa trên tuổi nếu session thực tế vẫn active.

## 15. Kiểm thử SessionRegistry

Kiểm thử nên bao phủ cả registry contract, servlet lifecycle và OIDC Logout Endpoint. Unit test riêng cho SessionRegistry không chứng minh filter chain và logout handler thực sự được wiring.

### 15.1. Unit test đăng ký và tra cứu

~~~java
class SessionRegistryTests {

    private final SessionRegistry registry = new SessionRegistryImpl();

    @Test
    void registersAndFindsSessionForPrincipal() {
        Object principal = "user-42";
        registry.registerNewSession("session-1", principal);

        SessionInformation information =
            registry.getSessionInformation("session-1");

        assertThat(information).isNotNull();
        assertThat(information.getPrincipal()).isEqualTo(principal);
        assertThat(registry.getAllSessions(principal, false)).hasSize(1);
    }

    @Test
    void removesSessionInformation() {
        registry.registerNewSession("session-1", "user-42");
        registry.removeSessionInformation("session-1");

        assertThat(registry.getSessionInformation("session-1")).isNull();
    }
}
~~~

Đây là ví dụ unit test cho API registry. Nó không tạo HttpSession thật và không kiểm tra HttpSessionEventPublisher.

### 15.2. Test session lifecycle events

Integration test cần:

1. Tạo authenticated HttpSession;
2. Xác nhận SessionRegistry có SessionInformation;
3. Gọi HttpSession.invalidate();
4. Xác nhận HttpSessionEventPublisher phát event;
5. Xác nhận SessionRegistryImpl xóa record sau event.

Ngoài explicit invalidate, cần test session timeout trong servlet container hoặc test environment có hỗ trợ session expiry. Session timeout là nguồn stale record phổ biến nếu lifecycle publisher chưa được cấu hình.

### 15.3. Test OIDC RP-Initiated Logout

Một integration test hoàn chỉnh nên:

- Bật OIDC trong Authorization Server filter chain;
- Tạo RegisteredClient có post-logout redirect URI hợp lệ;
- Thực hiện authorization flow để có OP session và registry record;
- Gửi logout request với id_token_hint và post_logout_redirect_uri hợp lệ;
- Xác nhận success handler kết thúc OP session;
- Xác nhận session lifecycle event dọn registry record;
- Gửi redirect URI không đăng ký và xác nhận request bị từ chối.

Không chỉ mock OidcLogoutAuthenticationProvider vì mục tiêu là xác minh cả session registration, provider lookup, validation và logout handler.

Một test qua MockMvc có thể kiểm tra redirect URI không hợp lệ:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OidcLogoutSessionIntegrationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void rejectsUnregisteredPostLogoutRedirectUri() throws Exception {
        MockHttpSession session = authenticatedOpSession();
        String idTokenHint = registeredClientIdToken();

        mvc.perform(get("/connect/logout")
                .session(session)
                .param("id_token_hint", idTokenHint)
                .param("post_logout_redirect_uri",
                    "https://attacker.example/"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Đây là test skeleton cho endpoint mặc định. authenticatedOpSession và registeredClientIdToken là fixtures do test application tạo; cần có RegisteredClient, ID Token/authorization record và session registry record tương ứng. Nếu deployment đổi logout endpoint path hoặc error entry point, điều chỉnh URI/status assertion theo cấu hình thực tế.

MockMvc test cho happy path cũng cần xác nhận session được invalidate và record được dọn sau khi lifecycle event được phát. Để kiểm chứng servlet listener và timeout thực, nên bổ sung test với embedded servlet container thay vì chỉ dựa vào MockHttpSession.

### 15.4. Test token lifecycle riêng

Sau logout, kiểm tra access/refresh token theo policy đã chọn. Nếu hệ thống tuyên bố logout revoke refresh token, phải xác minh token state trong OAuth2AuthorizationService hoặc introspection. Không suy ra token đã revoked chỉ vì browser bị redirect tới trang logged-out.

## 16. Các lỗi và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Logout không tìm thấy session | Session chưa được register hoặc principal không khớp | SessionAuthenticationStrategy, principal equals/hashCode |
| SessionRegistry còn record sau timeout | Thiếu HttpSessionEventPublisher hoặc event không tới registry | Kiểm tra listener và SessionDestroyedEvent |
| Concurrent session limit đếm sai | Hai registry instances hoặc stale records | Chia sẻ bean và lifecycle cleanup |
| Logout thành công trên node A nhưng lỗi node B | SessionRegistryImpl in-memory per node | Distributed registry/session repository |
| Session ID thay đổi nhưng lookup cũ còn tồn tại | Session fixation event không được xử lý | HttpSessionIdChangedEvent và session tracking |
| User đăng nhập nhiều lần bị gom nhầm | Principal key không duy nhất/không ổn định | Dùng stable user identifier |
| Logout redirect tới host lạ | post_logout_redirect_uri không được allowlist đúng | RegisteredClient.postLogoutRedirectUris |
| OP logout nhưng RP vẫn đăng nhập | Chưa có front/back-channel propagation hoặc RP local logout | OIDC logout notification |
| Browser logout nhưng access token còn dùng được | Logout session không tự revoke JWT | Token revocation/introspection policy |
| Spring Session repository không tìm thấy session | Principal index chưa được populate | PRINCIPAL_NAME_INDEX_NAME và principal resolver |

## 17. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Nghĩ SessionRegistry là HttpSession store | Không biết cách invalidate session thực tế | Kết hợp registry với Servlet/Spring Session |
| Không đăng ký HttpSessionEventPublisher cho SessionRegistryImpl | Stale session records | Publish session lifecycle events |
| Mỗi filter chain tạo registry riêng | Session registration và logout lookup lệch nhau | Inject cùng một bean |
| Dùng SessionRegistryImpl trong cluster mà không chia sẻ | Node khác không tìm thấy session | Shared/custom registry hoặc Spring Session |
| Dùng mutable principal làm map key | Không tìm thấy sessions sau khi principal thay đổi | Stable equals/hashCode |
| Gọi removeSessionInformation rồi nghĩ đã logout | HttpSession vẫn có thể hoạt động | Invalidate session qua logout handler |
| Dùng expireNow như invalidate | Session chỉ được đánh dấu expired | Dùng logout/session invalidation flow phù hợp |
| Nghĩ logout tự thu hồi mọi JWT | Access token có thể còn hợp lệ đến exp | Thiết kế token revocation/denylist riêng |
| Nhầm OP SessionRegistry với RP OidcSessionRegistry | Logout sai loại session | Phân biệt vai trò OP và RP |
| Cho phép post-logout redirect tùy ý | Open redirect | Đối chiếu RegisteredClient allowlist |
| Log raw session ID | Session hijacking nếu log bị lộ | Redact session identifiers |

## 18. Bảo mật và quyền riêng tư

Session tracking liên quan trực tiếp đến khả năng chiếm quyền phiên và dữ liệu nhận dạng người dùng. Cần:

- Không log raw session ID, cookie hoặc access token;
- Không đưa session ID vào URL, analytics hay tracing tags;
- Bảo vệ SessionRegistry/session repository bằng quyền truy cập nội bộ;
- Dùng HTTPS và cookie flags phù hợp như Secure, HttpOnly, SameSite theo flow;
- Bảo đảm session ID rotation sau authentication theo session fixation policy;
- Kiểm soát post-logout redirect URI bằng registration;
- Không cho client tự khai principal/session ID để logout người dùng khác;
- Hạn chế quyền truy cập admin APIs liệt kê hoặc kết thúc sessions;
- Có audit event cho logout nhưng không chứa credential;
- Xóa dữ liệu session tracking theo retention policy.

### 18.1. Không để lộ session existence

API quản trị tra cứu session cần xác thực và authorization riêng. Không cung cấp endpoint public cho phép người gọi thử session ID rồi biết session có tồn tại hay không.

### 18.2. Logout phải idempotent

Người dùng có thể logout nhiều lần, session có thể đã hết hạn trước khi request đến, hoặc event có thể được xử lý lặp. Logout handler và registry cleanup nên chịu được việc session đã không còn tồn tại. Không biến một session đã destroyed thành lỗi nghiêm trọng hoặc khôi phục record cũ.

## 19. Vận hành và giám sát

Theo dõi session lifecycle bằng các metric không chứa session ID hoặc PII:

| Metric/event | Ý nghĩa |
|---|---|
| oidc_sessions_registered_total | Số session được register |
| oidc_sessions_destroyed_total | Số session được dọn |
| oidc_logout_requests_total | Số RP-Initiated Logout requests |
| oidc_logout_failures_total | Logout validation/provider failures |
| session_registry_lookup_misses_total | Không tìm thấy SessionInformation |
| session_registry_stale_records | Số record nghi stale nếu có cleanup check |
| concurrent_sessions_rejected_total | Login bị từ chối vì session limit |
| session_store_lookup_latency | Độ trễ truy xuất session store |

### 19.1. Audit events

Một audit record hữu ích có thể gồm:

- Event type: login, logout requested, logout completed, session expired;
- Client ID đã xác thực nếu có;
- Principal identifier đã pseudonymize;
- Timestamp và correlation ID;
- Kết quả và error code;
- Logout scope: current session hoặc all sessions nếu ứng dụng hỗ trợ.

Không ghi raw session ID, cookie value, ID Token, refresh token hoặc access token.

### 19.2. Alert gợi ý

- SessionRegistry lookup miss tăng bất thường;
- SessionDestroyedEvent không tương xứng với session expiry/invalidation;
- Logout failure tăng sau deployment;
- Các node có số lượng session registry chênh lệch bất thường;
- Spring Session repository lookup latency hoặc error tăng;
- Token vẫn active sau logout vượt quá revocation SLA đã định nghĩa.

## 20. Checklist production

1. **OIDC enabled:** OIDC configurer được bật trên Authorization Server?
2. **Registry bean:** Có một SessionRegistry instance dùng chung giữa logout và concurrent-session control?
3. **Registration:** Default SessionAuthenticationStrategy vẫn đăng ký authenticated sessions?
4. **Lifecycle:** SessionRegistryImpl có HttpSessionEventPublisher?
5. **Principal:** Principal key ổn định và equals/hashCode đúng?
6. **Session store:** Registry và HttpSession store có cùng nguồn dữ liệu nhất quán?
7. **Cluster:** Multi-node deployment dùng shared registry/session repository?
8. **Session ID:** Session fixation protection và ID rotation được theo dõi?
9. **Logout endpoint:** RP-Initiated Logout được bật và có validation?
10. **Redirect:** post_logout_redirect_uri khớp allowlist đã đăng ký?
11. **Logout scope:** Chính sách current-session/all-sessions được xác định?
12. **Token lifecycle:** Có chính sách riêng cho access/refresh token sau logout?
13. **RP propagation:** Front/back-channel logout được triển khai nếu yêu cầu SSO logout toàn hệ sinh thái?
14. **Security:** Không log session ID/cookie/token; bảo vệ admin session APIs?
15. **Testing:** Có tests cho registration, invalidation, timeout, logout và cluster failover?
16. **Monitoring:** Có metric/alert cho lookup miss, stale records và logout failures?

## 21. Bài tập vận dụng

**Tình huống A — Stale session:** Một user logout nhưng SessionRegistry vẫn còn SessionInformation. Hãy kiểm tra HttpSessionEventPublisher, session invalidation và SessionDestroyedEvent. Viết test chứng minh record được dọn.

**Tình huống B — Hai node:** User login qua node A, logout request được load balancer gửi đến node B. Vì sao SessionRegistryImpl có thể không tìm thấy session? Hãy thiết kế registry dùng chung.

**Tình huống C — Concurrent sessions:** Một user được phép tối đa hai phiên. Khi login lần thứ ba, policy nên từ chối login mới hay đánh dấu phiên cũ expired? Phân tích UX, security và logout handlers.

**Tình huống D — Token còn active:** Browser đã logout OP nhưng Resource Server vẫn chấp nhận JWT access token. Vì sao điều này có thể xảy ra? Hãy chọn cơ chế phù hợp để đáp ứng yêu cầu logout hiệu lực nhanh.

**Tình huống E — OP và RP:** OP nhận RP-Initiated Logout thành công nhưng RP vẫn giữ local session. Phân biệt SessionRegistry ở OP với OidcSessionRegistry ở RP và chọn front-channel/back-channel propagation.

**Tình huống F — Principal đổi username:** User đổi username sau khi session được đăng ký. Nếu equals/hashCode hoặc principal index dựa trên username, lookup có thể sai thế nào? Đề xuất stable principal key.

**Gợi ý:** A cần event publisher và cleanup; B cần shared registry/session store; C cần chọn maximumSessions policy; D cần token revocation/introspection hoặc JWT lifetime phù hợp; E cần logout notification tới RP; F nên dùng immutable user ID làm key.

## 22. Tổng kết

SessionRegistry là thành phần theo dõi các phiên đã xác thực trong Spring Security. Khi OIDC được bật, Spring Authorization Server dùng registry để đăng ký sessions ở OAuth2 Authorization Endpoint và để OidcLogoutAuthenticationProvider tra cứu SessionInformation khi End-User yêu cầu RP-Initiated Logout.

SessionRegistryImpl phù hợp với ứng dụng đơn node và cần HttpSessionEventPublisher để nhận lifecycle events, đặc biệt là SessionDestroyedEvent. Nếu dùng Concurrent Session Control, nên chia sẻ cùng một registry bean. Principal cần có identity ổn định để lookup không bị sai sau khi object hoặc hồ sơ người dùng thay đổi.

Trong môi trường clustered, SessionRegistryImpl in-memory không đủ để chia sẻ session state giữa các nodes. Có thể dùng Spring Session và SpringSessionBackedSessionRegistry hoặc một implementation dùng chung, đồng thời bảo đảm principal index, session store và logout lookup nhất quán.

Cuối cùng, OP session logout, RP local logout và token revocation là các hành động khác nhau. Thiết kế OIDC logout production cần phối hợp session lifecycle, redirect validation, front/back-channel notification khi cần, token lifecycle policy, kiểm thử đa node và giám sát mà không làm lộ session identifiers.

## 23. Tài liệu tham khảo

- [Spring Authorization Server — Core Model / Components: SessionRegistry](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): cách OIDC dùng SessionRegistry, SessionAuthenticationStrategy và HttpSessionEventPublisher.
- [Spring Authorization Server — Protocol Endpoints: OIDC Logout Endpoint](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OidcLogoutEndpointConfigurer, OidcLogoutAuthenticationProvider và logout handlers.
- [Spring Authorization Server API — OidcLogoutAuthenticationProvider](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcLogoutAuthenticationProvider.html): provider, dependencies và authentication validator.
- [Spring Security API — SessionRegistry](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/session/SessionRegistry.html): các thao tác tra cứu và đăng ký sessions.
- [Spring Security API — SessionRegistryImpl](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/session/SessionRegistryImpl.html): implementation mặc định và session lifecycle events.
- [Spring Security API — SessionInformation](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/session/SessionInformation.html): trạng thái active/expired/destroyed và expireNow.
- [Spring Security API — ConcurrentSessionFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/session/ConcurrentSessionFilter.html): refresh last request và xử lý session expired.
- [Spring Session API — SpringSessionBackedSessionRegistry](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/security/SpringSessionBackedSessionRegistry.html): SessionRegistry dựa trên Spring Session cho clustered environments.
- [Spring Session API — FindByIndexNameSessionRepository](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FindByIndexNameSessionRepository.html): tìm session theo principal name index.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html): end_session_endpoint, id_token_hint, post_logout_redirect_uri và state.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0-final.html): Logout Token, sub/sid, validation và session termination ở RP.
