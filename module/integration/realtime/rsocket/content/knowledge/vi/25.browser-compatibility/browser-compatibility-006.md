# Truyền thông tin xác thực và xử lý hết hạn ở phía trình duyệt

Ứng dụng chạy trong trình duyệt có thể dùng RSocket qua WebSocket để nhận thông báo, mở request-stream hoặc trao đổi hai chiều bằng request-channel. Tuy nhiên, trình duyệt có giới hạn khi mở WebSocket: API WebSocket chuẩn chỉ nhận URL và danh sách subprotocol, không cho JavaScript tự gắn header HTTP tùy ý như Authorization.

RSocket giải quyết một phần khác của bài toán: sau khi WebSocket handshake thành công, client và server trao đổi frame RSocket. Credential có thể được gửi trong **metadata của SETUP** hoặc **metadata của từng request**. Vì vậy, cần phân biệt xác thực HTTP upgrade với xác thực RSocket; hai giai đoạn này có thể dùng cùng danh tính nhưng không tự động thay thế nhau.

Một thiết kế tốt cần chọn đúng phạm vi credential, lưu token an toàn trong trình duyệt, làm mới token trước khi hết hạn, xử lý stream đang chạy và reconnect có kiểm soát. Kết nối RSocket có thể sống lâu hơn access token, nên việc mở socket thành công không bảo đảm socket vẫn được phép hoạt động mãi.

## 1. Hai giai đoạn xác thực khác nhau

Khi browser kết nối RSocket qua WebSocket, quá trình có hai giai đoạn:

1. **WebSocket handshake:** trình duyệt gửi HTTP Upgrade request để mở WebSocket. Server có thể kiểm tra cookie, Origin và các thông tin handshake mà browser tự gửi.
2. **RSocket SETUP và các interaction:** sau khi WebSocket mở, client gửi frame SETUP để thương lượng phiên RSocket. Từ đây có thể gửi authentication metadata theo extension của RSocket. Những request tiếp theo cũng có thể mang metadata riêng.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant W as WebSocket Endpoint
    participant R as RSocket Server
    participant S as Spring Security
    B->>W: HTTP Upgrade + Cookie + Origin
    W->>W: Kiểm tra handshake / Origin
    W-->>B: 101 Switching Protocols
    B->>R: RSocket SETUP + auth metadata
    R->>S: Xác thực credential
    S-->>R: Principal / reject
    R-->>B: SETUP accepted hoặc connection rejected
    B->>R: Request + route + payload
    R->>S: Request authentication/authorization
    S-->>R: Cho phép hoặc từ chối
    R-->>B: Response / stream
~~~

Cookie được gửi trong WebSocket handshake không tự động trở thành Bearer Token Authentication metadata của RSocket. Nếu ứng dụng muốn dùng identity từ cookie để gắn với RSocket session, server phải tích hợp và xác minh rõ cách chuyển identity qua ranh giới handshake. Với Spring Security RSocket, một cách trực tiếp là gửi credential theo RSocket authentication metadata.

## 2. Vì sao browser không thể đặt Authorization header cho WebSocket?

Fetch API cho phép đặt header Authorization:

~~~javascript
await fetch("/api/profile", {
  headers: {
    Authorization: "Bearer " + accessToken
  }
});
~~~

Nhưng constructor WebSocket chuẩn chỉ có dạng:

~~~javascript
const socket = new WebSocket(
  "wss://api.example.com/rsocket"
);
~~~

Hoặc có thêm subprotocol:

~~~javascript
const socket = new WebSocket(
  "wss://api.example.com/rsocket",
  ["rsocket"]
);
~~~

Không có tham số headers hoặc options để đặt Authorization. Subprotocol dùng để thương lượng giao thức ứng dụng, không phải chỗ thích hợp để nhét Bearer token. Token đặt trong URL query string cũng dễ xuất hiện trong access log, telemetry, browser history hoặc hệ thống giám sát.

Với RSocket, có thể gửi token trong metadata của SETUP hoặc request sau khi WebSocket đã được nâng cấp. Cách này giữ credential trong payload nhị phân của giao thức ứng dụng, không cần custom HTTP header.

## 3. Chọn xác thực tại SETUP hay từng request?

Spring Security hỗ trợ xác thực RSocket ở SETUP, ở request hoặc kết hợp cả hai. Lựa chọn phụ thuộc vào cách ứng dụng dùng connection.

| Mô hình | Khi phù hợp | Cách xử lý token |
|---|---|---|
| SETUP authentication | Một connection gắn với một user/device | Gửi token lúc mở RSocket session |
| Request authentication | Một connection được chia sẻ cho nhiều user | Gửi token trong metadata của mỗi request |
| Kết hợp hai tầng | Gateway/service identity và user identity cùng cần xác thực | Xác thực connection ở SETUP, user ở từng request |

**Một user cho mỗi connection:** browser lấy access token mới rồi tạo connection RSocket bằng token trong SETUP. Nếu token hết hạn và policy yêu cầu token mới, client làm mới token, đóng connection cũ, mở connection mới và khôi phục subscription.

**Một connection dùng chung nhiều user:** không gắn connection với token của user đầu tiên rồi tái sử dụng cho mọi user. Mỗi request cần credential của user tương ứng. Điều này đặc biệt quan trọng nếu backend tạo một RSocket connection tới downstream service để phục vụ nhiều phiên browser.

**Kết hợp hai tầng:** SETUP có thể chứng minh ứng dụng/gateway được phép mở connection; từng request mang user credential để phân quyền theo người dùng cuối.

Không có lựa chọn nào tự động phù hợp mọi hệ thống. Hãy xác định một connection đại diện cho ai và mỗi request cần được kiểm tra theo identity nào.

## 4. Gửi Bearer token trong RSocket SETUP bằng rsocket-js

Ví dụ dưới đây dùng API **rsocket-js 0.x** với composite metadata. RSocket JS có các package độc lập như rsocket-core và rsocket-websocket-client. Phiên bản 1.0 alpha là bản viết lại TypeScript với thay đổi API; không trộn ví dụ 0.x với API alpha trong cùng dự án.

Cài các package tương thích cùng dòng phiên bản:

~~~bash
npm install rsocket-core@0.0.29-alpha.0 rsocket-websocket-client@0.0.29-alpha.0
~~~

Ví dụ tạo connection dùng bearer token trong SETUP:

~~~javascript
import {
  RSocketClient,
  BufferEncoders,
  JsonSerializer,
  IdentitySerializer,
  APPLICATION_JSON,
  MESSAGE_RSOCKET_COMPOSITE_METADATA,
  MESSAGE_RSOCKET_AUTHENTICATION,
  encodeCompositeMetadata,
  encodeBearerAuthMetadata
} from "rsocket-core";

import RSocketWebsocketClient
  from "rsocket-websocket-client";

function createSetupMetadata(accessToken) {
  return encodeCompositeMetadata([
    [
      MESSAGE_RSOCKET_AUTHENTICATION,
      encodeBearerAuthMetadata(accessToken)
    ]
  ]);
}

export async function connectRSocket(accessToken) {
  const client = new RSocketClient({
    serializers: {
      data: JsonSerializer,
      metadata: IdentitySerializer
    },
    setup: {
      keepAlive: 60000,
      lifetime: 180000,
      dataMimeType: APPLICATION_JSON.string,
      metadataMimeType:
        MESSAGE_RSOCKET_COMPOSITE_METADATA.string,
      payload: {
        metadata: createSetupMetadata(accessToken)
      }
    },
    transport: new RSocketWebsocketClient({
      url: "wss://api.example.com/rsocket"
    }, BufferEncoders)
  });

  return client.connect();
}
~~~

Điểm cần chú ý:

- MESSAGE_RSOCKET_AUTHENTICATION là MIME type của authentication metadata extension.
- encodeBearerAuthMetadata(accessToken) mã hóa nội dung theo Bearer authentication format.
- encodeCompositeMetadata(...) đóng gói authentication entry vào composite metadata.
- IdentitySerializer giữ nguyên buffer metadata đã được encode; không serialize composite metadata như JSON lần nữa.
- BufferEncoders giúp transport xử lý dữ liệu nhị phân theo API của phiên bản rsocket-js được chọn.
- keepAlive và lifetime là tham số keepalive của RSocket, không phải thời hạn JWT.

Ví dụ này giả định token đã được lấy an toàn từ luồng đăng nhập của ứng dụng. Không ghi token ra console hoặc log.

## 5. Spring Security xác thực JWT ở phía server

Phía server cần bật RSocket Security và cấu hình JWT decoder. Ví dụ:

~~~java
@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfiguration {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity security) {

        security
            .authorizePayload(authorize -> authorize
                .setup().hasRole("RSOCKET_CONNECT")
                .route("profile.me")
                    .hasAuthority("SCOPE_profile.read")
                .anyRequest().authenticated()
                .anyExchange().permitAll()
            )
            .jwt(Customizer.withDefaults());

        return security.build();
    }

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        return ReactiveJwtDecoders.fromIssuerLocation(
            "https://identity.example.com"
        );
    }
}
~~~

Các authority trong ví dụ phải khớp với claim và converter mà ứng dụng dùng. hasRole("RSOCKET_CONNECT") thường kiểm tra authority ROLE_RSOCKET_CONNECT; hasAuthority("SCOPE_profile.read") cần authority tương ứng được ánh xạ từ scope.

Cấu hình trên minh họa mô hình có credential tại SETUP và route authorization. anyExchange().permitAll() xử lý các payload không có metadata; trong request-channel, payload tiếp theo không lặp lại metadata route của message mở interaction. Vì vậy handler/domain service vẫn phải kiểm tra quyền trên từng command. Nếu dùng request authentication trên một connection chia sẻ, hãy cấu hình SETUP theo policy của gateway và yêu cầu authentication trên từng request thay vì bắt mọi SETUP phải mang role của user cuối.

Ví dụ policy tối giản cho mô hình request authentication, trong đó SETUP không xác thực user cuối nhưng mỗi request có metadata phải được xác thực:

~~~java
security
    .authorizePayload(authorize -> authorize
        .setup().permitAll()
        .anyRequest().authenticated()
        .anyExchange().permitAll()
    )
    .jwt(Customizer.withDefaults());
~~~

Chỉ dùng setup().permitAll() khi kiến trúc có biện pháp bảo vệ connection ở tầng khác, chẳng hạn gateway identity, quota và giới hạn tài nguyên. Authentication theo request không loại bỏ nhu cầu kiểm soát việc mở socket.

Spring Boot có thể tự đăng ký security interceptor khi có dependency RSocket Security phù hợp. Nếu cấu hình server thủ công, cần gắn interceptor vào SocketAcceptor của RSocket server.

JWT được kiểm tra chữ ký, issuer, thời hạn và các điều kiện validation khác bởi decoder/converter. Không tin claim do browser tự gửi nếu không nằm trong token đã xác thực.

## 6. Gửi token theo từng request

Nếu connection được chia sẻ hoặc cần token mới cho mỗi interaction, client có thể thêm authentication metadata cùng route trong payload request.

~~~javascript
import {
  MESSAGE_RSOCKET_ROUTING,
  MESSAGE_RSOCKET_AUTHENTICATION,
  encodeCompositeMetadata,
  encodeRoute,
  encodeBearerAuthMetadata
} from "rsocket-core";

function requestMetadata(route, accessToken) {
  return encodeCompositeMetadata([
    [MESSAGE_RSOCKET_ROUTING, encodeRoute(route)],
    [
      MESSAGE_RSOCKET_AUTHENTICATION,
      encodeBearerAuthMetadata(accessToken)
    ]
  ]);
}

function findProfile(socket, accessToken) {
  return socket.requestResponse({
    data: { includePreferences: true },
    metadata: requestMetadata(
      "profile.me",
      accessToken
    )
  });
}
~~~

Ví dụ giả định socket đã được mở và serializers được cấu hình tương thích. Khi gửi request, token được gắn cùng route trong composite metadata. Server có thể xác thực request bằng Spring Security trước khi thực thi handler.

Nếu token được refresh, các request mới dùng token mới. Tuy nhiên, một request-stream hoặc request-channel đã mở không tự động được xác thực lại chỉ vì browser thay đổi biến accessToken ở phía JavaScript. Metadata của request mở interaction không tự thay đổi theo biến đó.

## 7. Access token hết hạn trong khi connection vẫn mở

JWT thường có claim exp. Access token có thể hết hạn trong khi WebSocket và RSocket session vẫn đang hoạt động.

Cần phân biệt:

- **Token expiry:** credential không còn hợp lệ để xác thực request mới.
- **RSocket keepalive:** cơ chế phát hiện peer không phản hồi.
- **RSocket lifetime:** giới hạn thời gian peer chờ keepalive theo cấu hình.
- **Application session expiry:** phiên đăng nhập của người dùng hết hạn hoặc bị thu hồi.
- **Stream lifetime:** thời gian một interaction đang hoạt động.

Các mốc này độc lập. Token hết hạn không đồng nghĩa WebSocket tự đóng ngay tại thời điểm exp. Nếu server xác thực ở SETUP, không nên giả định Spring Security sẽ tự đóng socket khi JWT hết hạn giữa một stream. Cần có chính sách vòng đời phiên và subscription.

### Chính sách nên xác định

1. Client biết thời điểm token hết hạn hoặc nhận được thông tin expires_in từ auth server.
2. Làm mới token trước hạn với một khoảng đệm để tránh sai lệch đồng hồ.
3. Nếu xác thực theo request, dùng token mới cho interaction mới.
4. Nếu xác thực ở SETUP, tạo connection mới bằng token mới.
5. Hủy stream cũ và mở lại từ cursor/offset đã xác nhận nếu cần khôi phục dữ liệu.
6. Nếu refresh thất bại hoặc phiên đã bị thu hồi, đóng connection và đưa người dùng về luồng đăng nhập.

Không chờ tới lúc token đã hết hạn mới bắt đầu refresh. Browser có thể bị treo nền, timer bị throttling hoặc mạng chậm khiến tác vụ refresh chạy muộn.

## 8. Làm mới token qua HTTPS

Một mô hình thường dùng là browser gọi endpoint HTTPS để lấy access token mới. Refresh token nên được giữ trong cơ chế an toàn phía server/BFF hoặc cookie HttpOnly; JavaScript không cần đọc refresh token.

Ví dụ luồng refresh:

~~~javascript
async function refreshAccessToken() {
  const response = await fetch("/auth/refresh", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-TOKEN": readCsrfToken()
    },
    body: "{}"
  });

  if (!response.ok) {
    throw new Error("Không thể làm mới phiên đăng nhập");
  }

  return response.json();
}
~~~

Ví dụ này giả định ứng dụng dùng cookie phiên/refresh HttpOnly và có CSRF token phù hợp. Endpoint, tên header và cách cấp token là hợp đồng của ứng dụng, không phải API bắt buộc của RSocket.

### Refresh trước hạn

~~~javascript
async function ensureFreshToken(session) {
  const refreshSkewMs = 60_000;
  const now = Date.now();

  if (session.expiresAt - now > refreshSkewMs) {
    return session.accessToken;
  }

  const refreshed = await refreshAccessToken();

  session.accessToken = refreshed.access_token;
  session.expiresAt =
    Date.now() + refreshed.expires_in * 1000;

  return session.accessToken;
}
~~~

expires_in được tính từ thời điểm nhận response. Nếu client đọc exp từ JWT để lên lịch, giá trị đó chỉ phục vụ điều phối phía giao diện; server vẫn phải tự xác minh token. Không dùng việc decode payload JWT ở browser để quyết định token có hợp lệ hay không.

Không để nhiều tab đồng thời refresh cùng một refresh token nếu auth server dùng rotation. Có thể phối hợp qua BFF, BroadcastChannel hoặc cơ chế single-flight để tránh race giữa các tab.

## 9. Reconnect sau khi token SETUP được làm mới

Nếu token chỉ được gửi trong SETUP, cách đơn giản và dễ kiểm soát là tạo connection mới sau refresh:

~~~mermaid
sequenceDiagram
    participant UI as Browser App
    participant Auth as Auth Server
    participant R as RSocket Server
    UI->>Auth: POST /auth/refresh
    Auth-->>UI: Access token mới
    UI->>R: WebSocket WSS + RSocket SETUP(token mới)
    R->>R: Xác thực JWT
    R-->>UI: Connection accepted
    UI->>R: Subscribe từ cursor đã lưu
    R-->>UI: Replay các event tiếp theo
~~~

Một quy trình reconnect:

1. Dừng tạo request mới trên connection cũ.
2. Hủy hoặc hoàn tất stream theo chính sách ứng dụng.
3. Lưu cursor/sequence cuối cùng đã xử lý bền vững.
4. Làm mới access token qua HTTPS.
5. Đóng RSocket session cũ bằng API close/dispose phù hợp phiên bản client.
6. Tạo RSocketClient mới và gửi token trong SETUP.
7. Đăng ký lại các stream từ cursor đã xác nhận.
8. Dùng message ID/idempotency key để tránh xử lý trùng sau replay.

Nếu stream có dữ liệu quan trọng, không chỉ lưu “phần tử cuối cùng đã nhận”. Cursor phải phản ánh phần tử cuối cùng đã commit nghiệp vụ, nếu không reconnect có thể bỏ qua dữ liệu chưa xử lý xong.

## 10. Token hết hạn khi request-stream hoặc request-channel đang chạy

Một request-stream có thể kéo dài nhiều phút hoặc nhiều giờ. Request-channel còn có thể tiếp tục nhận command từ browser trong lúc server trả response.

Authentication metadata thường nằm trong payload mở interaction. Những payload tiếp theo của channel không nhất thiết mang lại metadata route/auth như request đầu tiên. Do đó:

- Token mới dùng cho request tiếp theo không tự thay token của stream đang chạy.
- Rule authorization theo route bảo vệ lúc mở interaction.
- Command tiếp theo trong channel vẫn cần kiểm tra quyền nghiệp vụ và trạng thái phiên theo yêu cầu.
- Nếu session hết hạn, server cần hủy stream/subscription hoặc yêu cầu reconnect.
- Khi mở lại stream, dùng cursor hoặc sequence để không bỏ sót dữ liệu.

Nếu cần xác thực lại giữa stream, thiết kế một giao thức ứng dụng rõ ràng: ví dụ route refresh/session-renew riêng, token mới được xác minh, server cập nhật trạng thái phiên hoặc hủy stream cũ và yêu cầu client mở lại. Không coi Metadata Push là cách tự động thay thế JWT đã được Spring Security xác thực cho mọi stream đang chạy.

## 11. Cookie, BFF và lưu trữ credential trong browser

Có hai mô hình thường gặp:

### Backend for Frontend (BFF)

Browser giữ cookie phiên có thuộc tính phù hợp; BFF giữ refresh token hoặc credential OAuth phía server. Khi cần RSocket credential, browser gọi BFF qua HTTPS để nhận access token ngắn hạn hoặc ticket theo chính sách ứng dụng.

Ưu điểm:

- Refresh token không nằm trong JavaScript.
- Cookie HttpOnly giảm khả năng script đọc credential.
- Server có thể kiểm soát refresh, logout và thu hồi phiên.
- Có thể cấp token ngắn hạn chỉ dùng cho RSocket.

Cookie nên được cấu hình Secure, HttpOnly và SameSite phù hợp. Nếu có request thay đổi trạng thái qua HTTP, vẫn cần bảo vệ CSRF theo kiến trúc ứng dụng.

### SPA giữ access token trong bộ nhớ

Nếu SPA trực tiếp thực hiện OAuth Authorization Code + PKCE, hãy ưu tiên giữ access token trong bộ nhớ và dùng token có thời hạn ngắn. Tránh lưu bearer token hoặc refresh token trong localStorage/sessionStorage vì JavaScript cùng origin có thể đọc được khi xảy ra XSS.

Bộ nhớ không loại bỏ rủi ro XSS: script độc hại đang chạy trong trang vẫn có thể đọc token hoặc thực hiện request thay người dùng. Cần CSP, Trusted Types nếu phù hợp, dependency hygiene và encode output.

Không nhúng client secret hoặc API key có quyền cao vào bundle JavaScript. Mọi bí mật được đóng gói trong frontend đều có thể bị người dùng trích xuất.

## 12. Cookie và bảo vệ WebSocket handshake

Browser có thể tự gửi cookie phù hợp trong WebSocket handshake. Điều này tiện cho session-based auth nhưng làm tăng rủi ro Cross-Site WebSocket Hijacking nếu server chấp nhận kết nối từ Origin không tin cậy.

Server nên:

- Dùng WSS trên môi trường production.
- Kiểm tra Origin bằng allowlist chính xác.
- Không dùng wildcard hoặc kiểm tra substring lỏng lẻo.
- Dùng SameSite cookie phù hợp với luồng đăng nhập.
- Bổ sung CSRF protection khi mô hình cookie cần.
- Xác thực session trước khi cho phép truy cập dữ liệu.
- Đóng connection khi logout hoặc session bị thu hồi.

Origin là tín hiệu bảo vệ browser handshake, không phải bằng chứng xác thực tuyệt đối. Client không phải browser có thể giả mạo Origin. Server vẫn cần authentication và authorization ở tầng ứng dụng.

CORS không thay thế kiểm tra Origin của WebSocket handshake. Cấu hình CORS cho HTTP endpoint lấy token cũng không tự bảo vệ WebSocket upgrade endpoint.

## 13. Những cách truyền token nên tránh

| Cách làm | Vấn đề | Hướng xử lý |
|---|---|---|
| Authorization header trên WebSocket constructor | Browser API không hỗ trợ custom header | Dùng RSocket authentication metadata hoặc cookie/BFF |
| Token trong query string | Có thể lọt vào log, history và monitoring | Dùng SETUP/request metadata hoặc one-time ticket |
| Token trong subprotocol | Sai mục đích giao thức, dễ lộ trong handshake log | Dùng metadata extension |
| Refresh token trong localStorage | JavaScript/XSS có thể đọc | Giữ phía BFF hoặc cookie HttpOnly |
| Token SETUP dùng mãi | Session có thể sống lâu hơn token | Refresh + reconnect hoặc request authentication |
| Gửi token trong mọi payload data | Trộn credential vào DTO nghiệp vụ, dễ log nhầm | Dùng authentication metadata |
| Retry vô hạn với token cũ | Tạo vòng lặp lỗi và tải không cần thiết | Refresh một lần, sau đó yêu cầu đăng nhập nếu thất bại |

## 14. Xử lý auth error, network error và reconnect

Không phải mọi lỗi connection đều là token hết hạn. Browser cần phân biệt:

- WebSocket handshake bị từ chối.
- RSocket SETUP bị server reject.
- Request bị authentication/authorization error.
- Network bị mất hoặc tab chuyển trạng thái.
- Server restart hoặc proxy đóng idle connection.
- Stream bị cancel do người dùng rời màn hình.

Chính sách tham khảo:

| Lỗi | Hành động |
|---|---|
| Token sắp hết hạn | Refresh trước khi request mới |
| Authentication thất bại do token hết hạn | Refresh qua HTTPS, tạo request/connection mới |
| Refresh token bị thu hồi | Xóa trạng thái local và yêu cầu đăng nhập lại |
| Authorization denied | Hiển thị lỗi quyền; không retry tự động |
| Network tạm mất | Reconnect với exponential backoff và jitter |
| Server đóng connection | Kiểm tra session, refresh nếu cần rồi reconnect |
| Request ghi có kết quả chưa rõ | Dùng idempotency key hoặc truy vấn trạng thái trước khi retry |

Không retry vô hạn khi nhận lỗi xác thực. Nếu server từ chối token mới hoặc refresh endpoint trả lỗi phiên, dừng reconnect và chuyển người dùng về luồng đăng nhập.

Với thao tác ghi, timeout có thể xảy ra sau khi server đã commit nhưng trước khi browser nhận response. Khi retry, dùng idempotency key để tránh thực hiện tác dụng phụ hai lần.

## 15. Logout và thu hồi phiên

Khi người dùng logout:

1. Gọi endpoint logout qua HTTPS để vô hiệu hóa session/refresh token theo chính sách.
2. Hủy subscription và request-channel đang mở.
3. Đóng RSocket connection.
4. Xóa access token và thông tin expiresAt khỏi bộ nhớ ứng dụng.
5. Xóa state nhạy cảm khỏi UI/cache phù hợp.
6. Thông báo cho các tab khác nếu ứng dụng có nhiều tab.
7. Server hủy stream và từ chối request tiếp theo từ credential đã thu hồi.

Nếu một connection chỉ phục vụ một người dùng, logout nên đóng connection đó. Nếu connection được chia sẻ cho nhiều người dùng, phải hủy các interaction gắn với user vừa logout mà không làm ảnh hưởng user khác.

Không chỉ xóa token khỏi JavaScript rồi coi phiên đã kết thúc. Server phải xử lý thu hồi hoặc hết hạn credential.

## 16. Keepalive, lifetime và token expiry không phải một

Các thông số keepAlive và lifetime trong SETUP của RSocket điều khiển nhịp KEEPALIVE và thời gian peer chờ phản hồi. Chúng không phải thời hạn đăng nhập.

Ví dụ:

~~~javascript
setup: {
  keepAlive: 60000,
  lifetime: 180000,
  dataMimeType: APPLICATION_JSON.string,
  metadataMimeType:
    MESSAGE_RSOCKET_COMPOSITE_METADATA.string
}
~~~

- keepAlive: chu kỳ gửi KEEPALIVE.
- lifetime: thời gian tối đa peer chờ KEEPALIVE phản hồi trước khi xem peer không còn hoạt động.
- JWT exp: thời điểm credential hết hạn.
- Application session timeout: thời hạn phiên đăng nhập do ứng dụng quản lý.

Đặt keepAlive ngắn không làm JWT hết hạn sớm hơn. Đặt lifetime dài cũng không kéo dài quyền truy cập của người dùng. Các giới hạn phải được quản lý riêng.

## 17. Kiểm thử credential và token expiry

Nên kiểm thử cả browser handshake, RSocket authentication metadata và vòng đời stream.

| Tình huống | Kết quả mong đợi |
|---|---|
| Browser mở WSS không có session | Handshake hoặc SETUP bị từ chối theo policy |
| Origin không nằm trong allowlist | WebSocket handshake bị từ chối |
| JWT hợp lệ ở SETUP | Connection được xác thực |
| JWT sai chữ ký/issuer | SETUP hoặc request bị từ chối |
| JWT hết hạn trước khi mở connection | Không xác thực được |
| JWT hết hạn khi stream đang chạy | Stream/session được xử lý theo expiry policy rõ ràng |
| Request mới mang token mới | Server xác thực token mới |
| Shared connection với hai user | Mỗi request được gắn đúng principal |
| User logout | Stream của user bị hủy và credential bị thu hồi |
| Refresh endpoint thất bại | Không retry vô hạn; yêu cầu đăng nhập |
| Reconnect sau refresh | SETUP mới dùng token mới |
| Resubscribe sau reconnect | Bắt đầu từ cursor đã commit |
| Request ghi bị timeout rồi retry | Idempotency ngăn tác dụng phụ lặp |
| Tab chuyển nền rồi hoạt động lại | Client kiểm tra expiry trước khi dùng connection |

Dùng integration test với RSocket client/server thật để kiểm tra authentication metadata và security interceptor. Browser automation có thể xác nhận WebSocket handshake, Origin, cookie và hành vi khi tab offline/online. Không chỉ mock hàm refresh vì lỗi thường nằm ở ranh giới HTTP handshake, RSocket SETUP và request metadata.

## 18. Checklist triển khai

- Phân biệt WebSocket handshake và RSocket SETUP.
- Không cố đặt Authorization header qua browser WebSocket constructor.
- Chọn SETUP auth hoặc request auth theo mô hình connection.
- Dùng composite metadata và Bearer Authentication metadata đúng MIME type.
- Cấu hình Spring Security JWT decoder và route authorization.
- Dùng WSS và kiểm tra Origin.
- Không đặt token trong URL hoặc subprotocol.
- Giữ refresh token phía BFF/cookie HttpOnly khi có thể.
- Hạn chế access token trong bộ nhớ và thời hạn ngắn.
- Refresh trước exp với clock skew.
- Có policy reconnect và resubscribe theo cursor.
- Xử lý token expiry cho stream đang chạy.
- Hủy connection/stream khi logout hoặc revoke.
- Không retry vô hạn khi auth/authorization thất bại.
- Dùng idempotency key cho request ghi có thể retry.
- Kiểm thử nhiều tab, tab nền, mạng mất và token hết hạn.

## 19. Kết luận

Browser không thể tự đặt Authorization header trong WebSocket handshake bằng WebSocket API chuẩn. Với RSocket qua WebSocket, ứng dụng có thể gửi Bearer token trong authentication metadata của SETUP hoặc của từng request. Xác thực ở SETUP phù hợp một connection gắn với một user; request authentication phù hợp connection được chia sẻ cho nhiều user.

Access token có thể hết hạn trong khi RSocket session vẫn mở. Vì vậy, hãy refresh token qua HTTPS, quyết định rõ cách xử lý stream đang chạy, reconnect bằng credential mới và resubscribe từ cursor đã xác nhận. Kết hợp WSS, Origin allowlist, cookie an toàn, bảo vệ XSS/CSRF, logout/revocation và idempotency để thông tin xác thực ở browser có vòng đời rõ ràng và không làm gián đoạn dữ liệu nghiệp vụ.

Tài liệu tham khảo:
- [MDN – WebSocket constructor](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/WebSocket)
- [MDN – Writing WebSocket servers and Origin validation](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_servers)
- [RSocket JS 0.x Client Guide](https://rsocket.io/guides/rsocket-js/client/)
- [Spring Security – RSocket Authentication and JWT](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
- [RSocket JS GitHub repository and version notes](https://github.com/rsocket/rsocket-js)
- [RSocket JS issue – Bearer authentication metadata example](https://github.com/rsocket/rsocket-js/issues/88)

