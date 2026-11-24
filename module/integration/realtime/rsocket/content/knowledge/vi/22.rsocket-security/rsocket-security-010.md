# Xử lý token hết hạn, thu hồi quyền và kết nối đang hoạt động

Một RSocket connection có thể sống lâu hơn access token được dùng khi mở nó. Vì vậy, xác thực thành công ở thời điểm `SETUP` không có nghĩa token sẽ tiếp tục hợp lệ trong toàn bộ thời gian connection tồn tại. Tương tự, một stream đã được mở có thể vẫn chạy sau khi quyền của người dùng thay đổi, bởi authorization thường được kiểm tra khi request bắt đầu chứ không phải trên từng payload tiếp theo của stream.

Để xử lý đúng token hết hạn và thu hồi quyền, cần xác định danh tính được xác thực ở phạm vi nào, kiểm tra token ở thời điểm nào, và làm gì với connection hoặc stream đã được mở trước khi quyền thay đổi. Bài học này tập trung vào Spring Security RSocket, JWT, kiểm tra thu hồi và cách chủ động kết thúc tương tác đang hoạt động.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt xác thực ở `SETUP` với xác thực trên từng request.
- Giải thích vì sao token hết hạn không tự đóng một RSocket connection đang mở.
- Cấu hình JWT authentication và authorization cho RSocket bằng Spring Security.
- Gửi bearer token trong setup metadata hoặc request metadata.
- Xử lý token hết hạn, refresh và thu hồi bằng `jti`, denylist hoặc phiên bản quyền.
- Kiểm tra lại quyền hiện tại thay vì chỉ tin role claim cũ trong JWT.
- Theo dõi connection và stream đang hoạt động để dừng chúng khi cần.
- Thiết kế chính sách khi revocation store lỗi, race condition và kiểm thử bảo mật.

## 1. Vấn đề: vòng đời token và vòng đời connection khác nhau

Access token thường có thời hạn ngắn, trong khi RSocket connection được thiết kế để tồn tại lâu và multiplex nhiều request. Hai vòng đời này không tự đồng bộ.

Ví dụ:

- 09:00: client mở RSocket connection với JWT hết hạn lúc 09:15.
- 09:10: client mở một request-stream và nhận dữ liệu liên tục.
- 09:15: JWT hết hạn.
- 09:20: stream vẫn có thể đang hoạt động nếu server chỉ xác thực token tại `SETUP` hoặc chỉ kiểm tra authorization lúc stream bắt đầu.
- 09:22: quản trị viên thu hồi quyền người dùng.

Nếu hệ thống không có chính sách kiểm tra lại và kết thúc tương tác, connection vẫn có thể tồn tại sau thời điểm token hết hạn hoặc quyền đã bị thu hồi.

Cần tách ba khái niệm:

| Khái niệm | Câu hỏi cần trả lời |
|---|---|
| Authentication | Token có hợp lệ và đại diện cho ai tại thời điểm kiểm tra? |
| Authorization | Principal đó hiện có được phép thực hiện route/resource này không? |
| Connection/session lifecycle | Những connection và stream nào cần tiếp tục, bị hạn chế hoặc phải đóng? |

Token hợp lệ không tự động có nghĩa người dùng có quyền với mọi route. Ngược lại, quyền bị thu hồi cũng không tự động đóng socket nếu ứng dụng không triển khai cơ chế kết thúc connection.

## 2. Xác thực ở SETUP và xác thực theo từng request

Spring Security RSocket hỗ trợ xác thực ở thời điểm thiết lập connection, ở mỗi request hoặc kết hợp cả hai.

| Mô hình | Credential được gửi ở đâu? | Phù hợp khi nào? | Giới hạn |
|---|---|---|---|
| Authentication tại SETUP | Metadata của frame `SETUP` | Một connection chỉ đại diện cho một người dùng hoặc một thiết bị | Token được kiểm tra khi mở phiên; không tự được kiểm tra lại khi token hết hạn |
| Authentication theo request | Metadata của từng request | Một connection được chia sẻ bởi nhiều người dùng hoặc nhiều request identity | Các request mới được xác thực riêng; stream đã mở cần cơ chế re-check/terminate |
| Kết hợp cả hai | Credential dịch vụ ở SETUP, token người dùng ở từng request | Backend dùng connection chung nhưng vẫn cần xác thực service và user | Cần quy định rõ principal nào chịu trách nhiệm cho từng quyết định |

Spring Security lưu ý rằng khi một connection được nhiều người dùng chia sẻ, credential nên được gửi trên từng request để authorization dựa trên danh tính người dùng thực hiện request đó. Một mô hình kết hợp có thể yêu cầu quyền `SETUP` cho service mở connection, sau đó xác thực từng người dùng ở request metadata. Trong ví dụ, service principal không nên được cấp scope `devices.read`; nhờ vậy, việc thiếu user token không thể vô tình dùng quyền của service để gọi route dành cho người dùng.

### Luồng xác thực theo request

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket Server
    participant A as Spring Security
    C->>S: SETUP (service credential)
    S->>A: Authenticate setup
    A-->>S: Service principal
    C->>S: REQUEST (route + bearer token user)
    S->>A: Authenticate JWT
    A->>A: Check signature, exp, issuer, claims
    A-->>S: User Authentication
    S->>A: Authorize route/resource
    A-->>S: Allow or deny
    S-->>C: Response hoặc stream
~~~

Với request-stream và request-channel, request ban đầu mang metadata để xác thực và phân quyền. Các payload tiếp theo thuộc cùng interaction không tự mang lại một lần kiểm tra authorization mới.

## 3. Cấu hình JWT authentication và route authorization

Spring Security cung cấp `RSocketSecurity` để cấu hình xác thực và authorization theo payload. Với JWT, DSL `jwt(...)` sử dụng `ReactiveJwtDecoder` để kiểm tra token. Cần một decoder được cấu hình với issuer đáng tin cậy.

Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.config.Customizer;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfiguration {

    @Bean
    ReactiveJwtDecoder issuerJwtDecoder() {
        return ReactiveJwtDecoders.fromIssuerLocation(
                "https://identity.example.com");
    }

    @Bean
    PayloadSocketAcceptorInterceptor rsocketSecurity(
            RSocketSecurity rsocket) {

        rsocket
            .authorizePayload(authorize -> authorize
                .setup().hasRole("SERVICE")
                .route("devices.admin.*").hasRole("ADMIN")
                .route("devices.private.*").hasAuthority("SCOPE_devices.read")
                .anyRequest().authenticated()
                .anyExchange().denyAll()
            )
            .jwt(Customizer.withDefaults());

        return rsocket.build();
    }
}
~~~

Trong ví dụ:

- `issuerJwtDecoder()` lấy cấu hình khóa và issuer từ identity provider.
- `.jwt(...)` bật hỗ trợ bearer token metadata.
- `.setup().hasRole("SERVICE")` yêu cầu principal mở connection có role `SERVICE`.
- Route `devices.admin.*` yêu cầu role `ADMIN`.
- Route `devices.private.*` yêu cầu scope `devices.read` được ánh xạ thành authority `SCOPE_devices.read`; các request còn lại yêu cầu principal đã xác thực.
- `.anyExchange().denyAll()` từ chối exchange không khớp rule, bao gồm payload không có metadata xác thực nếu không có rule cụ thể cho chúng.

Các rule được xét theo thứ tự; rule khớp đầu tiên được áp dụng. Hãy đặt rule cụ thể trước rule tổng quát. `ReactiveJwtDecoder` cần kiểm tra chữ ký và các claim bắt buộc như `iss`, `exp`, `nbf`; nếu ứng dụng cần kiểm tra `aud`, hãy cấu hình validator audience phù hợp.

Trong Spring Boot có dependency RSocket Security phù hợp, auto-configuration đăng ký `SecuritySocketAcceptorInterceptor` vào server. Nếu không dùng auto-configuration, cần gắn interceptor này vào server socket acceptor. Không đăng ký hai lần khi Boot đã tự cấu hình.

## 4. Gửi bearer token ở SETUP

Với mô hình một connection cho một principal, client có thể gửi token trong setup metadata. Spring Security dùng MIME type của RSocket Authentication Metadata Extension.

~~~java
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

MimeType authMimeType = MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

BearerTokenMetadata token = new BearerTokenMetadata(accessToken);

Mono<RSocketRequester> requesterMono = RSocketRequester.builder()
        .setupMetadata(token, authMimeType)
        .connectTcp("rsocket.internal", 7000);
~~~

Server xác thực token trong lúc xử lý `SETUP`. Nếu token đã hết hạn tại thời điểm mở connection, authentication thất bại và connection không được thiết lập theo chính sách bảo mật.

Nhưng nếu token hợp lệ lúc `SETUP` rồi hết hạn sau đó, việc token đi qua mốc `exp` không tự động phát một frame đóng connection. Server cần có chính sách session TTL, re-authentication hoặc chủ động đóng connection khi đến hạn.

Không dùng setup token của một người dùng để đại diện cho nhiều người dùng khác nhau trên cùng connection. Nếu connection được chia sẻ bởi backend service, dùng credential service ở `SETUP` và gửi token người dùng ở từng request.

## 5. Gửi bearer token trên từng request

Với connection dùng chung, client có thể gửi token của người dùng ở metadata của mỗi request:

~~~java
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

private static final MimeType AUTH_MIME_TYPE = MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

public Mono<DeviceStatus> findStatus(
        RSocketRequester requester,
        String accessToken,
        String deviceId) {

    return requester
            .route("devices.private.status")
            .metadata(new BearerTokenMetadata(accessToken), AUTH_MIME_TYPE)
            .data(new DeviceStatusQuery(deviceId))
            .retrieveMono(DeviceStatus.class);
}
~~~

Mỗi lần gọi method, client truyền token hiện hành. Khi access token được refresh, request tiếp theo có thể dùng token mới mà không cần tạo connection mới chỉ vì token người dùng thay đổi.

`BearerTokenMetadata` biểu diễn bearer token trong authentication metadata extension. Hãy dùng đúng MIME type `MESSAGE_RSOCKET_AUTHENTICATION` và phiên bản Spring Security tương thích ở client/server.

Token không được ghi vào log, metric tag hoặc tracing baggage. Trên môi trường production, bảo vệ transport bằng TLS; metadata authentication không tự mã hóa dữ liệu trên đường truyền.

## 6. Token hết hạn: điều gì xảy ra với request mới?

JWT decoder kiểm tra thời hạn token khi token được xác thực. Nếu `exp` đã qua hoặc token chưa có hiệu lực do `nbf`, authentication sẽ thất bại. Với request-level authentication, request tiếp theo gửi token cũ sẽ bị từ chối.

| Tình huống | Kết quả mong đợi |
|---|---|
| Token đã hết hạn trước SETUP | Không tạo connection được xác thực |
| Token hợp lệ lúc SETUP, hết hạn sau đó | Connection có thể vẫn mở nếu không có session-expiry policy |
| Token request-level hết hạn trước request mới | Request mới bị authentication từ chối |
| Token request-level hết hạn khi stream đang chạy | Stream hiện tại có thể tiếp tục nếu không có cơ chế kiểm tra lại |
| Client gửi token mới sau refresh | Request mới có thể được xác thực bằng token mới |
| Client tiếp tục gửi token cũ sau refresh | Request mới bị từ chối khi token cũ không còn hợp lệ |

Một access token hết hạn không nhất thiết làm connection transport mất hiệu lực. JWT decoder chỉ được gọi khi authentication interceptor xử lý credential; nếu connection đã được xác thực một lần ở SETUP và không có bước xác thực lại, server không tự chạy decoder theo đồng hồ cho connection đó.

### Refresh token và reconnect

Refresh token thường được dùng tại identity provider để lấy access token mới. Không gửi refresh token cho RSocket server như bearer credential. Client giữ refresh token trong thành phần quản lý danh tính an toàn, đổi lấy access token mới rồi:

- Với request-level auth: gửi access token mới trong metadata của request tiếp theo.
- Với setup-level auth: mở connection/session mới bằng access token mới, theo chính sách reconnect của ứng dụng.
- Với stream đang chạy: quyết định có cho stream kết thúc tự nhiên, yêu cầu mở lại stream bằng token mới hay hủy stream và subscribe lại.

Không retry vô hạn bằng access token đã hết hạn. Khi server trả lỗi authentication, client cần refresh qua identity provider; nếu refresh thất bại, yêu cầu người dùng đăng nhập lại hoặc kết thúc phiên.

## 7. JWT và thu hồi token

JWT thường được xác thực cục bộ bằng chữ ký và claim. Nếu không có trạng thái phía server, một JWT đã phát hành vẫn có thể được chấp nhận cho đến `exp`, kể cả khi người dùng đã logout hoặc quản trị viên muốn thu hồi nó sớm.

Để hỗ trợ thu hồi trước hạn, ứng dụng cần thêm trạng thái hoặc cơ chế kiểm tra trực tuyến. Một số cách phổ biến:

| Cách | Dữ liệu cần kiểm tra | Đặc điểm |
|---|---|---|
| Denylist theo `jti` | ID duy nhất của từng token | Thu hồi một token cụ thể |
| Token/session version | Phiên bản token hiện hành của user | Thu hồi hàng loạt token cũ của một principal |
| Account/session status | Trạng thái tài khoản hoặc session | Khóa tài khoản hoặc kết thúc mọi session |
| OAuth2 token introspection | Trạng thái token tại authorization server | Có thể biết token còn active hay không; thêm độ trễ và phụ thuộc dịch vụ |
| Access token TTL ngắn | `exp` | Giới hạn thời gian token tồn tại nhưng không thu hồi tức thời |

Denylist nên lưu `jti` thay vì raw token. TTL của entry có thể kết thúc tại thời điểm token hết hạn để tránh giữ dữ liệu lâu hơn cần thiết. Khi quyền bị thu hồi, phát sự kiện invalidation để các cache và connection registry cập nhật nhanh.

Nếu dùng JWT không có `jti`, có thể dùng hash của token làm khóa denylist, nhưng cần cân nhắc chi phí và chính sách lưu trữ. Tuyệt đối không ghi token nguyên bản vào log hoặc database chỉ để tra cứu.

## 8. Tích hợp kiểm tra revocation vào ReactiveJwtDecoder

Một cách triển khai là bọc decoder xác minh chữ ký/claim bằng một bước kiểm tra denylist bất đồng bộ. `TokenRevocationStore` là interface do ứng dụng định nghĩa, ví dụ truy vấn Redis hoặc một store tập trung. Khi dùng mẫu này, thay bean `issuerJwtDecoder` ở phần trước bằng bean `jwtDecoder` dưới đây để Spring Security chỉ có một `ReactiveJwtDecoder` chính.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders;
import reactor.core.publisher.Mono;

interface TokenRevocationStore {
    Mono<Boolean> isRevoked(String tokenId);
}

@Configuration
public class RevocationJwtDecoderConfiguration {

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            TokenRevocationStore revocationStore) {

        ReactiveJwtDecoder issuerDecoder =
                ReactiveJwtDecoders.fromIssuerLocation(
                        "https://identity.example.com");

        return token -> issuerDecoder.decode(token)
                .flatMap(jwt -> {
                    String tokenId = jwt.getId();

                    if (tokenId == null || tokenId.isBlank()) {
                        return Mono.error(
                                new BadJwtException("JWT must contain jti"));
                    }

                    return revocationStore.isRevoked(tokenId)
                            .flatMap(revoked -> revoked
                                    ? Mono.error(new BadJwtException("JWT revoked"))
                                    : Mono.just(jwt));
                });
    }
}
~~~

Ví dụ giả định token có claim `jti` và `TokenRevocationStore.isRevoked(jti)` trả `Mono<Boolean>`. Decoder gốc vẫn xác minh chữ ký và claim chuẩn; wrapper chỉ thêm bước kiểm tra trạng thái thu hồi.

Store cần luôn phát ra `true` hoặc `false`; không trả `Mono.empty()`, vì khi đó decoder không tạo được một kết quả JWT đã xác thực. Lỗi truy cập store phải được xử lý theo fail-open/fail-closed policy đã chọn.

Nếu revocation store không truy cập được, cần quyết định fail-closed hay fail-open. Với route nhạy cảm, fail-closed thường an toàn hơn: không thể xác minh trạng thái thì không cấp quyền. Nếu chọn fail-open cho một số route ít rủi ro, phải giới hạn thời gian cache và ghi metric/cảnh báo rõ ràng. Không âm thầm coi lỗi Redis hoặc introspection là token hợp lệ.

## 9. Thu hồi quyền khác với thu hồi token

Một token có thể còn hợp lệ về chữ ký và thời hạn nhưng người dùng đã mất một quyền cụ thể. Ví dụ người dùng vẫn được đọc telemetry nhưng không còn quyền điều khiển thiết bị.

Nếu role/permission chỉ được đọc từ JWT claim, quyền cũ có thể tiếp tục được dùng cho tới khi token hết hạn hoặc bị thu hồi. Có ba hướng xử lý:

1. Phát hành access token mới với claim đã cập nhật và thu hồi token cũ.
2. Kiểm tra permission hiện tại ở authorization manager cho từng request.
3. So sánh claim phiên bản quyền trong JWT với phiên bản hiện tại lưu ở server.

Ví dụ dùng custom access rule để kiểm tra quyền hiện tại:

~~~java
rsocket.authorizePayload(authorize -> authorize
    .route("devices.control.{deviceId}")
        .access((authentication, context) ->
                devicePermissionService.canControl(
                        authentication,
                        context.getVariables().get("deviceId")))
    .anyRequest().authenticated()
    .anyExchange().denyAll()
);
~~~

Đoạn code minh họa ý tưởng custom `ReactiveAuthorizationManager`; chữ ký context và cách lấy route variables cần khớp với phiên bản Spring Security đang dùng. Kiểm tra quyền ở request mới giúp áp dụng thay đổi nhanh hơn so với chỉ dựa trên role claim cũ.

Một cách khác là thêm claim `authz_ver` vào token. Khi admin thay đổi quyền, tăng version ở user record. Request chỉ được phép nếu version trong JWT bằng version hiện tại. Cách này thu hồi mọi token có quyền cũ mà không cần lưu từng token ID, nhưng vẫn cần tra cứu/cache phiên bản hiện tại.

## 10. Vì sao stream đang chạy không tự bị thu hồi?

Authorization của Spring Security RSocket được thực hiện tại request mang metadata. Với request-stream, metadata xuất hiện khi request bắt đầu; các payload tiếp theo của stream không phải request mới và không tự chạy lại authorization rule.

Điều đó có nghĩa:

- Request mới sau khi token hết hạn có thể bị từ chối.
- Một request-stream đã mở trước thời điểm hết hạn có thể vẫn tiếp tục.
- Quyền bị thu hồi không tự động phát tín hiệu tới các stream đã mở.
- Nếu cần áp dụng thu hồi ngay, ứng dụng phải quản lý subscription và chủ động kết thúc chúng.

Đây là khác biệt quan trọng giữa kiểm tra authorization ở đầu request và kiểm tra liên tục trong suốt vòng đời stream.

### Gắn stream với principal và session

Khi một stream được mở, hãy lưu thông tin tối thiểu để có thể kết thúc đúng stream khi cần:

- subject hoặc principal ID.
- jti hoặc token/session version.
- connection/session ID nội bộ.
- route và resource ID.
- thời điểm hết hạn token.
- handle hủy stream hoặc tín hiệu revocation.

Không lưu raw access token trong registry. Một registry có thể ánh xạ `jti` hoặc principal ID tới các session/stream handle đang hoạt động.

## 11. Kết thúc stream khi token hết hạn hoặc quyền bị thu hồi

Với stream dài hạn, có thể kết hợp thời điểm hết hạn với một publisher phát tín hiệu thu hồi. Ví dụ dưới đây dùng `takeUntilOther` để kết thúc stream khi revocation signal phát ra:

Giá trị `tokenExpiresAt` phải được lấy từ claim `exp` của JWT đã được xác thực, không nhận trực tiếp từ payload do client tự khai báo.

~~~java
public Flux<DeviceReading> streamReadings(
        String deviceId,
        String subject,
        String tokenId,
        Instant tokenExpiresAt) {

    Mono<Void> tokenExpired = Mono.delay(
            Duration.between(Instant.now(), tokenExpiresAt).isNegative()
                    ? Duration.ZERO
                    : Duration.between(Instant.now(), tokenExpiresAt))
            .then();

    Mono<Void> revoked = revocationEvents
            .whenPrincipalRevoked(subject);
    Mono<Void> tokenRevoked = revocationEvents
            .whenTokenRevoked(tokenId);

    return readingService.stream(deviceId)
            .takeUntilOther(Mono.firstWithSignal(
                    tokenExpired, revoked, tokenRevoked));
}
~~~

Ví dụ cho thấy ba tín hiệu dừng: token tới hạn, principal bị thu hồi và token cụ thể bị thu hồi. `whenPrincipalRevoked` và `whenTokenRevoked` là API giả định của ứng dụng, trả publisher hoàn tất khi có sự kiện revoke. Trong code production, cần tính clock skew, cancellation và cách biểu diễn kết thúc stream. Nếu muốn client nhận terminal error thay vì complete bình thường, hãy phát lỗi domain từ tín hiệu dừng.

Với nhiều token của cùng principal, cần theo dõi cả token ID và principal. Thu hồi một `jti` chỉ nên dừng các stream gắn với token đó; khóa tài khoản hoặc thu hồi toàn bộ session nên dừng tất cả stream thuộc principal.

### Đóng toàn bộ connection

Nếu token được xác thực ở SETUP và đại diện cho duy nhất một principal, policy có thể yêu cầu đóng toàn bộ connection khi token hết hạn hoặc bị thu hồi. Để làm được điều này, server cần registry connection/session và một handle có thể đóng connection từ phía server.

Khi sự kiện revocation tới:

1. Tìm session theo `jti`, principal hoặc session ID.
2. Ngăn request mới được chấp nhận trên session đó.
3. Hủy stream đang chạy hoặc gửi terminal error theo policy.
4. Đóng connection nếu identity ở SETUP đã mất hiệu lực.
5. Xóa session khỏi registry và giải phóng tài nguyên.

Cách gọi API đóng connection phụ thuộc việc ứng dụng dùng raw `RSocket`, Spring `RSocketRequester` ở phía server hay một lớp quản lý connection riêng. Không nên giả định chỉ xóa entry khỏi registry là đã đóng transport.

## 12. Cửa sổ race giữa kiểm tra quyền và mở stream

Có thể xảy ra race condition:

1. Request được xác thực và authorization cho phép.
2. Admin thu hồi quyền.
3. Stream vừa được đăng ký vào registry sau sự kiện revoke.
4. Stream tiếp tục chạy vì đã bỏ lỡ tín hiệu thu hồi.

Để tránh bỏ sót:

- Đăng ký stream handle ngay sau khi authorization thành công.
- Sau khi đăng ký, kiểm tra lại trạng thái revoke/version trước khi phát dữ liệu đầu tiên.
- Dùng store có thứ tự hoặc version/epoch để phát hiện event revoke đến trước khi stream đăng ký.
- Khi revoke, đánh dấu trạng thái principal/session là revoked trước, sau đó phát tín hiệu hủy.
- Dọn registry khi stream complete, error hoặc cancel.

Với hệ thống phân tán, một node có thể nhận sự kiện revoke chậm hơn node khác. Nếu cần thu hồi tức thời, dùng cơ chế phát sự kiện có đảm bảo, shared state hoặc kiểm tra trạng thái trực tiếp ở request nhạy cảm. Cache cục bộ cần TTL ngắn và cơ chế invalidation.

## 13. Client xử lý token hết hạn và refresh

Client cần phân biệt lỗi authentication với lỗi mạng hoặc lỗi nghiệp vụ. Một luồng xử lý điển hình:

~~~mermaid
flowchart TD
    A[Request RSocket] --> B{Authentication thành công?}
    B -->|Có| C[Thực hiện request]
    B -->|Token expired| D[Refresh access token]
    D --> E{Refresh thành công?}
    E -->|Có| F[Gửi request mới với token mới]
    E -->|Không| G[Kết thúc phiên và yêu cầu đăng nhập]
    B -->|Revoked / disabled| H[Không retry bằng token cũ]
    H --> I[Đăng xuất hoặc yêu cầu cấp quyền lại]
    C --> J{Connection hoặc stream còn hợp lệ?}
    J -->|Có| K[Tiếp tục]
    J -->|Bị server terminate| L[Mở lại interaction theo policy]
~~~

Với request-level auth, client có thể giữ requester dùng chung và thêm token mới vào metadata của request tiếp theo. Với setup-level auth, client có thể phải tạo connection mới vì identity được gắn với connection lúc mở phiên.

Không tự động retry mọi lỗi `AccessDeniedException`. Một lỗi do token hết hạn có thể giải quyết bằng refresh; một lỗi do token bị thu hồi hoặc user bị khóa cần dừng retry và yêu cầu đăng nhập/cấp quyền lại. Với request có side effect, chỉ retry khi có idempotency key hoặc trạng thái đối soát.

## 14. Chính sách cache và khả năng sẵn sàng

Kiểm tra revocation ở mỗi request giúp phản ứng nhanh nhưng có thể tăng tải lên Redis, database hoặc identity provider. Cache giảm tải nhưng tạo một khoảng trễ giữa lúc thu hồi và lúc mọi node nhìn thấy trạng thái mới.

| Chính sách | Ưu điểm | Rủi ro |
|---|---|---|
| Tra cứu store mỗi request | Thu hồi có hiệu lực nhanh | Tăng độ trễ và phụ thuộc store |
| Cache trạng thái active ngắn hạn | Giảm số lần tra cứu | Có cửa sổ stale trong thời gian TTL |
| Push invalidation event tới mọi node | Cập nhật nhanh khi event được nhận | Cần đảm bảo delivery, retry và xử lý node offline |
| Token TTL ngắn | Giảm thời gian token cũ còn hiệu lực | Không thu hồi tức thời và tăng tần suất refresh |

Với dữ liệu nhạy cảm hoặc lệnh điều khiển thiết bị, ưu tiên kiểm tra trạng thái hiện tại hoặc cache có invalidation đáng tin cậy. Với telemetry ít rủi ro, có thể chấp nhận TTL ngắn nếu được ghi rõ trong threat model.

## 15. Kiểm thử token expiry, revocation và stream active

Một bộ integration test nên kiểm tra riêng từng tầng:

| Ca thử | Thiết lập | Kết quả mong đợi |
|---|---|---|
| Token hết hạn trước SETUP | Gửi JWT có `exp` trong quá khứ | SETUP authentication thất bại |
| Token hết hạn sau SETUP | Mở connection bằng token còn hạn, chờ tới exp | Connection không tự đóng nếu không có session expiry policy |
| Token request-level hết hạn | Gửi request mới bằng token cũ sau exp | Request bị authentication từ chối |
| Refresh token thành công | Request kế tiếp mang JWT mới | Request mới được xác thực |
| Token có jti bị denylist | Đánh dấu ID đã revoke rồi gửi request | Authentication thất bại |
| Quyền route bị thu hồi | Cập nhật permission store hoặc authz_ver | Request mới bị authorization từ chối |
| Stream mở trước revoke | Mở stream, phát sự kiện revoke | Stream bị complete/error theo policy |
| Connection identity bị revoke | Mở session bằng setup token rồi revoke | Registry đóng connection và dừng stream |
| Revocation store không truy cập được | Làm Redis/introspection timeout | Hành vi fail-open/fail-closed đúng policy |
| Race khi revoke | Phát revoke đồng thời với mở stream | Không có stream mới tiếp tục sau khi trạng thái revoke đã có hiệu lực |
| Logout | Revoke token/session rồi gửi request tiếp | Token/session cũ bị từ chối |

Dùng clock giả lập hoặc JWT test token có thời hạn ngắn để kiểm thử expiry. Không cần chờ thời gian thật dài. Với stream, dùng `StepVerifier` và test publisher để kích hoạt revocation signal rồi xác minh stream kết thúc đúng cách.

## 16. Logging, metrics và audit

Nên theo dõi:

- Số token hết hạn bị từ chối theo route và client type.
- Số token bị revoke và số request bị deny.
- Số connection đang hoạt động theo principal/session.
- Số stream bị kết thúc bởi expiry hoặc permission change.
- Độ trễ cập nhật revocation event giữa các node.
- Số lần revocation store lỗi hoặc timeout.
- Số request được refresh token thành công/thất bại ở client.
- Thời gian từ lúc revoke đến lúc stream/connection bị dừng.

Audit log nên lưu subject, jti đã hash hoặc ID không nhạy cảm, route, quyết định authorization, lý do kết thúc và timestamp. Không lưu bearer token, refresh token, password hoặc toàn bộ authentication metadata.

## 17. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ xác thực JWT tại SETUP cho connection dùng lâu dài | Token hết hạn nhưng connection vẫn hoạt động | Dùng request-level auth hoặc session expiry policy |
| Cho rằng JWT stateless tự thu hồi được | Token bị logout vẫn hợp lệ đến exp | Denylist, token version hoặc introspection |
| Chỉ kiểm tra authorization khi stream bắt đầu | Stream tiếp tục sau khi quyền bị thu hồi | Theo dõi và hủy stream bằng revocation signal |
| Chỉ cập nhật role ở database nhưng tin claim cũ | JWT cũ vẫn có role đã bị gỡ | Re-check permission hoặc so sánh authz version |
| Dùng raw token làm khóa registry | Rò rỉ credential và khó quản lý | Dùng jti, subject và session ID |
| Cache active token quá lâu | Thu hồi có hiệu lực chậm | TTL ngắn và push invalidation |
| Fail-open khi revocation store lỗi mà không có policy | Request nhạy cảm có thể được cấp quyền sai | Fail-closed cho thao tác rủi ro cao |
| Xóa session registry nhưng không đóng connection | Connection/stream vẫn tiếp tục | Gọi close/cancel trên resource thực tế |
| Revoke và register stream không đồng bộ | Stream mới có thể lọt qua race | Đăng ký rồi re-check, dùng version/epoch |
| Retry token đã bị revoke | Tạo tải vô ích và có thể lặp side effect | Dừng retry, refresh hoặc yêu cầu cấp quyền lại |

## 18. Checklist triển khai

- [ ] Chọn rõ authentication tại SETUP, request-level hay kết hợp.
- [ ] Connection dùng chung nhiều user phải mang credential ở từng request.
- [ ] JWT decoder kiểm tra chữ ký, issuer, thời hạn và audience theo yêu cầu.
- [ ] Route authorization có rule cụ thể và default-deny phù hợp.
- [ ] Có chiến lược thu hồi token bằng jti, token version hoặc introspection.
- [ ] Permission thay đổi được kiểm tra lại ở request mới.
- [ ] Stream dài hạn có TTL hoặc revocation signal để kết thúc.
- [ ] Connection identity bị revoke có registry và close policy.
- [ ] Revocation store có timeout, cache TTL và fail-open/fail-closed policy.
- [ ] Xử lý race giữa revoke và đăng ký stream.
- [ ] Client refresh token đúng nơi và không retry token đã revoke.
- [ ] Có metric, audit và integration test cho expiry/revoke/active stream.

## Kết luận

Token, quyền và connection có vòng đời riêng. JWT hết hạn được phát hiện khi token được xác thực; nếu chỉ xác thực tại `SETUP`, connection đang mở không tự đóng khi đồng hồ vượt exp. Với connection chia sẻ, xác thực token trên từng request giúp các request mới nhận quyết định mới nhất, nhưng stream đã mở vẫn cần TTL hoặc revocation signal riêng vì authorization không tự chạy lại trên từng payload. Để thu hồi trước hạn, bổ sung denylist theo jti, token version hoặc introspection; để thu hồi quyền, kiểm tra permission hiện tại; và để dừng session đang hoạt động, duy trì registry cùng chính sách cancel/close rõ ràng.

## Tài liệu tham khảo

- [Spring Security Reference – RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
- [Spring Security API – RSocketSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html)
- [Spring Security – Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [RSocket Protocol](https://rsocket.io/about/protocol/)
