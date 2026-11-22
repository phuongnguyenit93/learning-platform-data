# Phân biệt danh tính khi thiết lập kết nối và khi xử lý từng payload

## 1. Câu hỏi cốt lõi: ai đang sở hữu kết nối, ai đang thực hiện request?

Trong Spring Security reactive, **RSocket** khác HTTP ở chỗ một kết nối có thể tồn tại lâu, chứa đồng thời nhiều request/stream và truyền dữ liệu theo hai chiều. Khi dùng RSocket với Gateway, service-to-service hoặc ứng dụng nhiều người dùng, không thể mặc định rằng **người thiết lập kết nối** chính là **người dùng của mọi request** đi qua kết nối ấy.

Xem một ví dụ:

~~~text
                           Một kết nối RSocket TCP lâu dài
Gateway backend G ─────────────────────────────────────────► RSocket service
  SETUP identity: gateway-service / ROLE_CONNECT
            │
            ├─ REQUEST_RESPONSE route=account.me
            │      request identity: Alice / ROLE_VIEWER
            │      → trả hồ sơ Alice
            │
            ├─ REQUEST_STREAM route=report.feed
            │      request identity: Bob / ROLE_VIEWER
            │      → stream báo cáo thuộc tenant Bob
            │
            ├─ REQUEST_STREAM route=report.feed
            │      request identity: Alice / ROLE_VIEWER
            │      → stream báo cáo tenant Alice
            │
            └─ REQUEST_CHANNEL với nhiều PAYLOAD tiếp nối
                   → identity / policy không mặc nhiên được
                     xác thực lại cho từng frame PAYLOAD
~~~

Ở đây có **ít nhất hai lớp danh tính**:

1. **Connection identity**: ai có quyền mở và duy trì một RSocket connection? Thường là thiết bị cá nhân hoặc một gateway/service account, xác thực ở **SETUP**.
2. **Request/stream identity**: ai yêu cầu thực hiện một thao tác cụ thể? Có thể là Alice hoặc Bob, xác thực bằng authentication metadata của **request khởi tạo stream**.

Một vấn đề thứ ba chỉ xuất hiện khi luồng dài:
3. **Authorization trong thời gian stream còn chạy**: nếu quyền của Alice bị thu hồi sau khi đã mở `REQUEST_STREAM`, server có kiểm tra lại trước khi phát sự kiện tiếp theo không?

**Không được nhầm:** “xác thực theo từng request” **không có nghĩa** Spring Security tự xác thực lại trên **từng frame PAYLOAD** xuất hiện trong một stream. Theo tài liệu RSocket Security, `anyRequest()` áp các frame request có metadata; những payload tiếp nối thường không có cùng metadata và không được tự động kiểm theo một quy tắc authorization mới. Ứng dụng cần thiết kế thêm **per-event checks** khi rủi ro/độ dài stream yêu cầu.

### Kết quả học tập

Sau bài này bạn có thể:
- Mô tả các tương tác `REQUEST_RESPONSE`, `REQUEST_STREAM`, `REQUEST_CHANNEL`, `REQUEST_FNF`, `SETUP` và `PAYLOAD`.
- Phân biệt authentication **SETUP**, authentication ở **request khởi tạo** và re-authorization **theo sự kiện** trong stream.
- Chọn mô hình connection riêng mỗi user, shared connection nhiều users, hoặc hai lớp xác thực kết hợp.
- Cấu hình `@EnableRSocketSecurity`, `RSocketSecurity`, `PayloadSocketAcceptorInterceptor`, `setup()`, `route()` và `anyRequest()`.
- Gửi `UsernamePasswordMetadata` qua `setupMetadata(...)` hoặc `metadata(...)` bằng `SimpleAuthenticationEncoder`.
- Biết đường đi của JWT bearer metadata, `ReactiveJwtDecoder` và `jwt(...)` khi dùng access token thay Simple Authentication.
- Lấy Authentication từ `ReactiveSecurityContextHolder` mà không suy ra identity từ userId trong payload.
- Giữ tenant/owner boundaries khi nhiều requests/streams chạy đồng thời trên một connection.
- Hiểu cách xử lý expiring tokens, revoked permissions, cancellation, reconnect, resume, backpressure và resource cleanup.
- Thực hành Java 17+ Spring Boot RSocket/Spring Security và kiểm thử bằng `StepVerifier` với TCP RSocket thực.
- Nhận diện giới hạn của tests mẫu và lập checklist kiểm thử production.

## 2. RSocket không phải “một HTTP request kéo dài”

Một kết nối RSocket thường bắt đầu bằng frame **`SETUP`** rồi có thể chứa nhiều streams với các stream IDs khác nhau. RSocket hỗ trợ multiplexing và Reactive Streams backpressure; phía responder hoặc requester đều có thể khởi tạo những tương tác được protocol cho phép.

| Frame/tương tác | Ý nghĩa | Điểm cần chú ý về danh tính |
| --- | --- | --- |
| `SETUP` | Thiết lập connection và media types/connection metadata | Có thể mang credentials cấp kết nối |
| `REQUEST_RESPONSE` | Một yêu cầu và một kết quả | Có thể mang credentials riêng cho request |
| `REQUEST_STREAM` | Một yêu cầu, nhiều phần tử trả về | Metadata đầu request có thể chứa identity; các phần tử sau cần policy riêng |
| `REQUEST_CHANNEL` | Một request với hai dòng dữ liệu đi/đến | Không tự coi mọi PAYLOAD của channel là một login mới |
| `REQUEST_FNF` | Một message không chờ response payload | Cần authorize ngay từ đầu; không trả response không có nghĩa bỏ kiểm quyền |
| `PAYLOAD` tiếp nối | Phần dữ liệu trong request/response stream đã mở | Không mặc định chạy `authorizePayload` như một request mới |
| `REQUEST_N` | Demand/backpressure | Không là request identity, không được sử dụng để thay user |
| `CANCEL` | Đóng/cancel stream | Cần dừng việc đang làm và release resources |
| `METADATA_PUSH` | Metadata ở cấp connection, không thuộc request cụ thể | Không tự xem là lệnh đổi principal toàn connection |

Sơ đồ theo thời gian:

~~~text
TCP/WebSocket transport
        │
        ├──── SETUP (connection identity: gateway)
        │
        ├──── REQUEST_RESPONSE A (metadata: Alice)
        │            └──── PAYLOAD kết quả A
        │
        ├──── REQUEST_STREAM B (metadata: Bob)
        │            ├──── PAYLOAD B1
        │            ├──── PAYLOAD B2
        │            └──── PAYLOAD B3
        │
        ├──── REQUEST_STREAM C (metadata: Alice)
        │            ├──── PAYLOAD C1
        │            └──── PAYLOAD C2
        │
        └──── ... kết nối vẫn tồn tại
~~~

**Nguyên tắc:** Transport connection là phương tiện truyền; danh tính/ủy quyền là thuộc tính của một security context đã được xác minh trong **phạm vi cụ thể**. Không lấy connection ID, TCP peer IP hay “người dùng mới nhất” làm bằng chứng cho tất cả streams.

### 2.1. Metadata khác data

Một RSocket payload có thể có:
- **Data**: nội dung nghiệp vụ (ví dụ tenant name, report ID, thông điệp chat).
- **Metadata**: routing, MIME, authentication metadata hoặc thông tin protocol khác.

Client **có thể tự viết cả data và metadata**. Bảo mật xuất phát từ việc server **xác minh authentication metadata**, không phải từ việc nó mang tên metadata. Một field data `userId=admin` không thể thay thế credentials ở authentication metadata.

### 2.2. RSocket với WebFlux: tương đồng và khác biệt

WebFlux HTTP dùng `ServerHttpSecurity`/`SecurityWebFilterChain`. RSocket server dùng `RSocketSecurity` và `PayloadSocketAcceptorInterceptor`. Hai cơ chế có chung tư tưởng reactive/authentication/authorization, nhưng **không tự chia sẻ toàn bộ chuỗi filter**.

HTTP `Authorization: Bearer token` thuộc HTTP headers. RSocket bearer token đi qua **RSocket authentication metadata extension**, không phải mặc định một HTTP header cho từng frame. Nếu RSocket chạy trên WebSocket, HTTP Upgrade headers không tự làm credential cho từng RSocket request sau handshake.

## 3. Ba chiến lược xác thực

### 3.1. A — Xác thực một lần ở SETUP: một user trên một connection

Tình huống:
- Mobile app mở một connection riêng cho tài khoản Alice.
- Thiết bị hoặc desktop app chỉ một user active tại một thời điểm.
- Server nhận metadata ở `SETUP`, xác minh và gắn security context phù hợp.

~~~text
Alice device
   │ SETUP Bearer(Alice) hoặc SimpleAuth(Alice)
   ▼
RSocket connection Alice
   ├─ request 1 → Alice
   ├─ request 2 → Alice
   └─ stream 3  → Alice
~~~

**Ưu điểm:** client không cần gửi credentials lặp lại ở mỗi request, đơn giản cho một user, ít overhead.

**Giới hạn:**
- Connection identity có thể được dùng lại trong các request sau, nhưng token ở SETUP **không được mặc định revalidate khi exp đến**.
- Nếu Alice đăng xuất, đổi user, bị thu hồi quyền hoặc token hết hạn giữa lúc connection đang mở, phải có cơ chế chủ động **close connection, reauthenticate/reconnect, expire stream hoặc check policy theo thời gian**.
- Connection có thể được pool/reuse ngoài dự kiến; khi đó giả định “một kết nối = một user” bị phá vỡ.
- Trên connection của Alice không được cho request payload tự khai `userId=bob` rồi sử dụng để mở dữ liệu Bob.

Chọn setup-only khi có bằng chứng kiến trúc rằng connection thật sự gắn với **một user**, có lifecycle/revocation phù hợp và app biết xử lý session refresh.

### 3.2. B — Xác thực theo từng request: một connection nhiều users

Tình huống:
- Web backend/service B duy trì **một kết nối RSocket chung** tới service A.
- Backend B đang phục vụ Alice, Bob, Carol bằng nhiều HTTP requests.
- Mỗi request RSocket của B chuyển user credential/token tương ứng, không lấy người dùng từ SETUP connection.

~~~text
Web backend (shared RSocket connection)
   │ SETUP không có user hoặc chỉ identity của backend service
   │
   ├─ REQUEST_RESPONSE metadata=Alice JWT → xử lý Alice
   ├─ REQUEST_STREAM metadata=Bob JWT     → stream Bob
   └─ REQUEST_RESPONSE metadata=Carol JWT → xử lý Carol
~~~

**Ưu điểm:** cùng một connection phục vụ nhiều users mà không trộn SecurityContext; quyền của mỗi request tách biệt.

**Điều kiện:** phía client phải attach đúng credential **của user đang thực hiện request đó**, phía server phải xác minh issuer/audience/signature/role cho từng request. **Không** gắn credentials vào một `RSocketRequester.Builder` dùng chung nếu mục tiêu là nhiều users: `setupMetadata` thuộc connection chứ không tự đổi theo user.

Một bug nguy hiểm:

~~~java
// PHẢN VÍ DỤ: biến toàn cục cho connection pool dùng chung.
static volatile String currentUser;

// Request A vào: currentUser = "alice"
// Request B vào: currentUser = "bob"
// Stream A đọc currentUser → tự nhiên thấy Bob.
~~~

Identity cần đi qua request-specific metadata rồi vào **Reactor security context của đúng luồng**. Không dùng ThreadLocal hoặc biến global để giữ user xuyên các asynchronous streams.

### 3.3. C — Xác thực cả SETUP và từng request

Đây là mô hình phù hợp cho shared gateway/backend cần kiểm soát hai quyền khác nhau:

~~~text
SETUP:
   service account = gateway
   authorities = [ROLE_CONNECT]
   → có quyền mở kết nối, KHÔNG có quyền xem dữ liệu user

REQUEST Alice:
   user account = alice
   authorities = [ROLE_VIEWER]
   → được thực hiện request xem dữ liệu Alice

REQUEST Bob:
   user account = bob
   authorities = [ROLE_VIEWER]
   → được thực hiện request xem dữ liệu Bob
~~~

Quy tắc:
- `SETUP` yêu cầu authority `ROLE_CONNECT`.
- Routes nghiệp vụ yêu cầu `ROLE_VIEWER` từ request identity.
- User Alice/Bob **không có ROLE_CONNECT**, vì vậy không tự thiết lập connection “gateway”.
- Gateway service account **không có ROLE_VIEWER**, vì vậy không thể đọc tài nguyên khi quên per-request credentials.
- Nếu Alice/Bob khác tenant, authorization nghiệp vụ phải kiểm tenant theo request và resource.

**Đây không phải ủy quyền thần kỳ của gateway:** Backend phải verify cả service SETUP credential lẫn user request credential; gateway không được tự gửi một header hoặc metadata text giả `role=VIEWER` để cấp quyền.

## 4. Cơ chế Spring Security RSocket

### 4.1. Các lớp và extension points

| Thành phần | Vai trò |
| --- | --- |
| `@EnableRSocketSecurity` | Bật RSocket Security configuration |
| `RSocketSecurity` | DSL cấu hình authn/authz theo payload |
| `PayloadSocketAcceptorInterceptor` | Kết quả `rsocket.build()`, tham gia request interception |
| `SecuritySocketAcceptorInterceptor` | Gắn payload interceptor vào RSocket socket acceptor |
| `AuthenticationPayloadInterceptor` | Lấy credentials/ủy quyền authentication qua manager |
| `AuthorizationPayloadInterceptor` | Chạy authorization rules cho payload exchanges phù hợp |
| `ReactiveAuthenticationManager` | Xác thực credential không blocking |
| `MapReactiveUserDetailsService` | Demo users in-memory; không phải identity store production |
| `simpleAuthentication(...)` | RSocket Simple Authentication Metadata |
| `jwt(...)` | Bearer JWT metadata, cần `ReactiveJwtDecoder` |
| `authorizePayload(...)` | Quy tắc `setup()`, `route()`, `anyRequest()`, `anyExchange()` |
| `RSocketRequester` | Client builder, setup metadata và request metadata |
| `ReactiveSecurityContextHolder` | Đọc Authentication của reactive execution context |

Spring Boot RSocket server auto-configuration thường tự gắn `SecuritySocketAcceptorInterceptor` nếu dependencies phù hợp; nếu tự dựng raw RSocket server không qua Boot, phải lắp interceptor thủ công. **Không tuyên bố server bảo vệ chỉ vì class có annotation nếu interceptor thật chưa nằm trong socket acceptor path**.

### 4.2. Cấu hình authn/authz cơ bản

~~~java
@Configuration
@EnableRSocketSecurity
class SecurityConfig {

    @Bean
    PayloadSocketAcceptorInterceptor interceptor(
            RSocketSecurity rsocket) {

        rsocket
            .authorizePayload(authorize -> authorize
                .setup().hasRole("CONNECT")
                .route("identity.whoami").hasRole("VIEWER")
                .route("tenant.feed").hasRole("VIEWER")
                .anyRequest().denyAll()
                .anyExchange().permitAll()
            )
            .simpleAuthentication(Customizer.withDefaults());

        return rsocket.build();
    }
}
~~~

Đây là **đoạn trích**, file đầy đủ ở mục 8. Ý nghĩa:
- `setup().hasRole("CONNECT")` chỉ cho phép connection có `ROLE_CONNECT` được chấp nhận.
- `route("identity.whoami").hasRole("VIEWER")` kiểm request có quyền viewer; nhận diện route từ request metadata.
- `route("tenant.feed").hasRole("VIEWER")` là gate ở **request mở stream**, không tự kiểm mọi emission.
- `anyRequest().denyAll()` từ chối các request có route chưa được cho phép; giữ nguyên thứ tự matcher.
- `anyExchange().permitAll()` cho các frame exchanges không phải request có route/metadata; **không** đồng nghĩa bảo vệ mọi phần tử bằng cùng quy tắc. Những frame PAYLOAD tiếp nối nằm ngoài lớp route authorization thông thường.
- `simpleAuthentication` hỗ trợ RSocket authentication metadata chuẩn, không nhận role từ data JSON tự khai.

**Cảnh báo:** Quy tắc được đánh giá theo thứ tự, rule đầu tiên phù hợp sẽ quyết định. Nếu đặt `anyRequest().permitAll()` trước `route(...).hasRole(...)`, route sẽ không còn được bảo vệ như dự định.

### 4.3. SETUP authentication khác @ConnectMapping

`@ConnectMapping` là handler được Spring Framework gọi khi xử lý connection setup theo route/data setup. Nó có thể phục vụ logic ứng dụng ở thời điểm kết nối, nhưng **không tự là một phương thức xác thực an toàn**.

Không lấy `setupData("alice")` từ client rồi coi là user đã login. Authentication phải đi qua `RSocketSecurity`/credential validation. `@ConnectMapping` cũng không nên tự `subscribe()` vào một stream dài rồi cho phép logic tiếp tục trước khi xác thực kết nối xong.

## 5. Gửi credentials đúng vị trí bằng RSocketRequester

### 5.1. MIME type của RSocket authentication metadata

RSocket Authentication Metadata Extension có well-known MIME type:

~~~java
MimeType authenticationMimeType =
    MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());
~~~

Với Simple Authentication, Spring Security cung cấp:
- `UsernamePasswordMetadata(username, password)`.
- `SimpleAuthenticationEncoder` để mã hóa metadata đúng dạng.

### 5.2. Credentials tại SETUP

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies ->
        strategies.encoder(new SimpleAuthenticationEncoder()))
    .setupMetadata(
        new UsernamePasswordMetadata("gateway", "connect-pass"),
        authenticationMimeType)
    .tcp("localhost", 7000);
~~~

Đây là ví dụ client có connection identity gateway. `setupMetadata(...)` được gắn vào kết nối khi gửi SETUP; nó **không** tự thay khi Bob/Alice dùng cùng requester.

### 5.3. Credentials tại REQUEST

~~~java
Mono<String> alice = requester
    .route("identity.whoami")
    .metadata(
        new UsernamePasswordMetadata("alice", "alice-pass"),
        authenticationMimeType)
    .retrieveMono(String.class);

Mono<String> bob = requester
    .route("identity.whoami")
    .metadata(
        new UsernamePasswordMetadata("bob", "bob-pass"),
        authenticationMimeType)
    .retrieveMono(String.class);
~~~

Hai publisher dùng **cùng một RSocketRequester**, nhưng request metadata khác nhau. Server không được lấy identity từ một biến `currentUser` của connection.

### 5.4. Bearer JWT tại SETUP hoặc request

Khi dùng OAuth2/JWT thay Simple Authentication, Spring Security hỗ trợ `BearerTokenMetadata`:

~~~java
MimeType authMimeType =
    MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

BearerTokenMetadata aliceToken = ...; // access token đáng tin từ AS

// SETUP: token gắn connection.
RSocketRequester perUser = RSocketRequester.builder()
    .setupMetadata(aliceToken, authMimeType)
    .tcp("localhost", 7000);

// REQUEST: token gắn vào một request của shared connection.
Mono<String> oneRequest = sharedRequester
    .route("identity.whoami")
    .metadata(aliceToken, authMimeType)
    .retrieveMono(String.class);
~~~

**Đây là đoạn trích khái niệm, không phải file standalone.** `BearerTokenMetadata` phải được tạo từ access token hợp lệ theo SDK/API phiên bản, client phải sử dụng dữ liệu credential thật an toàn; không có Authorization Server thực trong project demo Simple Authentication.

RSocket Security server:

~~~java
@Bean
PayloadSocketAcceptorInterceptor jwtRSocket(
        RSocketSecurity rsocket) {

    return rsocket
        .authorizePayload(authorize -> authorize
            .setup().authenticated()
            .anyRequest().authenticated()
            .anyExchange().permitAll())
        .jwt(Customizer.withDefaults())
        .build();
}
~~~

Cấu hình JWT cần **`ReactiveJwtDecoder` đáng tin** (issuer, audience, signature, expiry, algorithms). Không xây decoder chỉ dựa vào `iss` không allowlist. Nếu dùng hai cấp identity (service SETUP + end-user REQUEST), phải định nghĩa quyền cho setup/request theo token policy và cách manager map authorities, không chỉ copy `authenticated()` cho mọi frame.

### 5.5. Chọn đúng credentials cho shared connection

Tuyệt đối không dùng:
- `setupMetadata(userAliceToken)` trên một connection pool dùng chung cho toàn bộ người dùng.
- Thay một `AtomicReference<BearerTokenMetadata> currentToken` mỗi khi có request vì stream khác có thể nhìn nhầm.
- Copy `Authorization` header của HTTP request từ một ThreadLocal Servlet vào callback Reactor không ràng buộc context.
- Tin một `payload.userId` hoặc `payload.role` làm bằng chứng identity nếu token không xác minh tương ứng.

Thiết kế đúng là **propagate verified end-user credential theo request context**, đặt nó vào metadata của request tương ứng, sau đó xác thực lại ở RSocket Resource Server.

## 6. Danh tính ở request đầu tiên khác quyền của từng phần tử stream

Đây là trọng tâm riêng của “luồng dài”.

### 6.1. Một REQUEST_STREAM có nhiều phần tử nhưng một điểm authorization ở đầu

~~~text
T0  REQUEST_STREAM "tenant.feed"
    request metadata: JWT Alice
    → signature/issuer/audience/exp VALID
    → route authorization PASS
    → stream bắt đầu

T1  PAYLOAD item #1
T2  PAYLOAD item #2
T3  Alice bị thu hồi quyền xem tenant
T4  PAYLOAD item #3
T5  PAYLOAD item #4
~~~

Nếu server chỉ kiểm quyền ở T0, nó có thể **vẫn phát item #3 và #4**. Đó không hẳn là bug của Spring Security; đây là chính sách time-of-check/time-of-use của một subscription đã mở. Tài liệu Spring Security mô tả request authorization theo request có metadata, không phải cứ mỗi PAYLOAD continuation là một request mới.

Một hệ thống cần revoke sớm phải bổ sung một hoặc nhiều cơ chế:
- Kiểm quyền **trước mỗi lần query/emit một sự kiện nhạy cảm**.
- Stream có max duration, buộc client reconnect với credential mới.
- Chủ động cancel/dispose streams khi account/tenant membership bị revoke.
- Giới hạn token lifetime và thiết kế ngữ nghĩa khi token hết hạn giữa subscription.
- Chặn dữ liệu ở **repository/owner/tenant query boundary** để không phát sai tài nguyên dù stream đang sống.
- Nếu dữ liệu cực nhạy cảm, reauthorize theo từng item/tenant boundary hoặc thay bằng paged requests ngắn.

### 6.2. Mỗi PAYLOAD trong REQUEST_CHANNEL không phải một request độc lập

`REQUEST_CHANNEL` gửi nhiều payload đi vào server. RSocket có routing/security metadata ở request khởi tạo channel, nhưng các `PAYLOAD` tiếp nối có thể không mang credential và có thể không đi qua `AuthorizationPayloadInterceptor` như request mới.

Vì vậy **không** nói “RSocket tự xác thực lại từng message trong channel”. Nếu ứng dụng muốn:
- Một user cho cả channel: pin verified principal từ đầu channel và kiểm role/tenant cho mỗi command payload.
- Nhiều users cùng một channel: **không** giả định mỗi message có authenticated user chỉ vì có field `userId`. Phải thiết kế protocol-level authenticated envelope hoặc tốt hơn tách thành requests/streams có auth metadata riêng.
- Chuyển user giữa chừng: cần cơ chế reauthentication xác minh cryptographically, bind vào channel/session có chống replay/confused deputy; không đổi một biến global.
- Revoke tại thời điểm chạy: cancel/deny những messages tiếp theo.

### 6.3. Authn per request không đồng nghĩa authz per item

Bốn mức bảo vệ tách biệt:

| Mức | Sự kiện | Điều được chứng minh | Điều **không** tự được chứng minh |
| --- | --- | --- | --- |
| Kết nối | SETUP | Gateway/thiết bị có quyền mở connection | Mọi user request đều là gateway |
| Request | REQUEST_STREAM đầu | Một user có credential/role để khởi tạo stream | User vẫn còn quyền sau nhiều phút |
| Mỗi item | App-level check trong Flux | User hiện được phép nhận item đó theo policy | Mọi dữ liệu khác đều được phép |
| Dữ liệu | DB query/tenant ACL | Từng row/object thuộc phạm vi authorized | Không có lỗi lộ dữ liệu ở path khác |

Giải pháp tốt là lựa chọn **rõ ràng** mức nào phải được recheck theo độ nhạy, latency và yêu cầu revoke.

### 6.4. Ví dụ kiểm quyền per emission bằng Reactor

~~~java
// SNIPPET kiến trúc: không tự thành một @MessageMapping độc lập.
Flux<Event> feed(Authentication authentication, String tenant) {
    String subject = authentication.getName();

    return eventStore.eventsForTenant(tenant)
        .concatMap(event -> membershipService
            .mayRead(subject, tenant, event.id())
            .flatMap(allowed -> allowed
                ? Mono.just(event)
                : Mono.error(new AccessDeniedException(
                    "Access revoked"))));
}
~~~

**Điều kiện để an toàn:** `eventStore.eventsForTenant` phải lọc đúng tenant trước khi trả dữ liệu; `mayRead` lấy user từ Authentication đã được xác minh, không từ event hay header. `concatMap` kiểm trước mỗi event phát ra. Với database streaming query trả trước nhiều rows, phải hiểu **prefetch/buffering** và liệu dữ liệu đã được đọc/giữ trong bộ nhớ trước lúc policy thay đổi; “check ở map” không tự làm dữ liệu cũ biến mất.

## 7. Vấn đề expiration, logout, revoke, reconnect và resume

### 7.1. JWT hết hạn trong lúc connection còn mở

Giả sử:
- T0: JWT exp ở T+5 phút, user mở RSocket connection và REQUEST_STREAM.
- T+5: Token hết hạn.
- T+7: Server vẫn phát PAYLOAD mới.

**Không mặc định cho rằng** Spring Security sẽ tự chạy `ReactiveJwtDecoder.decode(...)` lại khi `exp` đi qua. Decoder thường được gọi tại thời điểm authentication của setup/request. Nếu subscription tiếp tục, app cần policy rõ:
1. Stream bị giới hạn đến thời điểm token exp; dừng/cancel trước hoặc tại exp.
2. Stream chấp nhận identity đã được kiểm ở điểm mở, nhưng có TTL ngắn và dữ liệu ít nhạy cảm (quyết định rủi ro phải được review).
3. Re-auth trên request mới sau một khoảng thời gian; người dùng lấy access token mới rồi mở subscription khác.
4. Kiểm revocation/membership trên từng emission theo hệ thống bên trong.

**Không** chỉ dựa vào RSocket KEEPALIVE để kết luận user còn được phép; heartbeat xác nhận transport liveness, không phải JWT validity.

### 7.2. User logout ở một tab nhưng stream trong tab khác vẫn chạy

Logout ở frontend hoặc session HTTP không tự gửi cancellation đến RSocket streams đã mở. Cần:
- Client cancel subscriptions và đóng connection nếu nó là per-user.
- Server quản lý subscription registry (user/tenant/connection/stream) nếu cần chủ động cancel theo sự kiện revoke.
- Cập nhật trạng thái user/tenant trong DB hoặc centralized entitlement service.
- Test cả logout/revoke ở thời điểm T1 giữa stream, không chỉ request đầu tiên.
- Tránh giữ refresh token của user trong connection state dưới dạng plain text/log.

### 7.3. Reconnect khác session resumption

- **Reconnect:** một connection mới, phải làm lại SETUP auth theo policy; đừng tin cache `authenticated=true` của connection cũ.
- **Resume (nếu bật):** protocol có khả năng tiếp tục stream sau gián đoạn khi state còn. Việc resume **không mặc nhiên là OAuth2 reauthentication**. Phải định nghĩa chính sách resumption token/session, TTL và end-user permission sau reconnect.
- **Retry:** một số client tự retry request; không được dùng token đã hết hạn hoặc gắn nhầm user do thread/context thay đổi.
- **Token refresh:** làm ở client/authorized user flow, rồi gửi token mới ở request/connection mới; không “sửa” token string đang nằm trong một stream đã authenticated.

### 7.4. Backpressure và security

RSocket backpressure không thay authorization:
- `REQUEST_N` điều khiển số item có thể gửi, không phải permission.
- Queue lớn có thể giữ dữ liệu trước khi quyền bị revoke. Ưu tiên giới hạn buffering và kiểm quyền ngay trước thời điểm phát.
- Hạn chế số active streams/user/tenant, message size, concurrent subscriptions và stream lifetime để chống DoS.
- Khi cancel, cần cleanup subscription, DB cursors, scheduler, metadata/credentials trong memory.

### 7.5. Time-of-check/time-of-use

Một quyết định “user được truy cập tenant A lúc T0” không nhất thiết còn đúng ở T10. Nếu quyền đổi thường xuyên:
- Chọn consistency model cụ thể (immediate, near-real-time, expiry-bound).
- Xác định dữ liệu đã gửi trước revoke có thể thu hồi hay không (thường không).
- Nếu recheck async, xử lý race giữa revoke và event emit; có thể cần gating ở data source để tránh phát item sau revoke.
- Không biến DB outage thành `permitAll`; fail closed khi không đủ căn cứ.

## 8. Project chạy được: RSocket SETUP service identity, từng REQUEST là Alice/Bob

Ví dụ này là một **ứng dụng Spring Boot 3.3.13, Spring Security 6.3.x, Java 17+**, RSocket TCP port 7000. Dùng **Simple Authentication** để dễ kiểm chứng ranh giới SETUP/request mà không phụ thuộc Authorization Server/JWKS bên ngoài. Production nên dùng token/service identity, TLS/mTLS và secret management phù hợp; **passwords `{noop}` dưới đây chỉ để học/test local, không dùng ở Internet**.

Thiết kế:
- Service user `gateway` có duy nhất role `CONNECT`.
- Alice và Bob có role `VIEWER`, **không** có `CONNECT`.
- `SETUP` yêu cầu `ROLE_CONNECT`.
- `identity.whoami` và `tenant.feed` yêu cầu `ROLE_VIEWER`.
- Cùng một connection từ gateway có thể gửi requests metadata Alice hoặc Bob.
- Thiếu request credentials: SETUP account gateway không có VIEWER nên không thể đọc user data.
- `tenant.feed` chỉ cho user đọc tenant được `TenantPolicy` cấp, kiểm trước **mỗi item** của Flux.
- Mọi route khác bị từ chối ở policy route.
- Không có biến global `currentUser`.

### 8.1. Cấu trúc thư mục

~~~text
rsocket-identity-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── IdentityRSocketApplication.java
    │   │   ├── RSocketSecurityConfig.java
    │   │   ├── TenantPolicy.java
    │   │   └── IdentityController.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── RSocketIdentityTests.java
~~~

### 8.2. settings.gradle

~~~groovy
rootProject.name = 'rsocket-identity-lab'
~~~

### 8.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-rsocket'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Vì sao cần ba dependency runtime?**
- `spring-boot-starter-rsocket`: server/client RSocket, messaging và Reactor transport.
- `spring-boot-starter-security`: thành phần authentication/authorization cốt lõi.
- `spring-security-rsocket`: RSocket Security DSL, interceptor và RSocket Simple Authentication metadata classes.

Không nhầm với `spring-boot-starter-webflux`: nếu chỉ dựng RSocket TCP server, không cần thêm HTTP WebFlux controller. Nếu dùng RSocket **over WebSocket** trong một WebFlux app, cấu hình transport/mapping path khác; ví dụ này cố tình dùng TCP để tách hai lớp.

### 8.4. application.properties

~~~properties
spring.application.name=rsocket-identity-lab
spring.rsocket.server.transport=tcp
spring.rsocket.server.port=7000
spring.rsocket.server.address=127.0.0.1
~~~

Bound address `127.0.0.1` chỉ dành cho lab local. Production phải dùng TLS/mTLS hoặc private networking, không gửi simple username/password dạng plaintext trên Internet. Test override port thành 0 để OS tự chọn port trống.

### 8.5. IdentityRSocketApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IdentityRSocketApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdentityRSocketApplication.class, args);
    }
}
~~~

### 8.6. RSocketSecurityConfig.java

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration(proxyBeanMethods = false)
@EnableRSocketSecurity
public class RSocketSecurityConfig {

    @Bean
    MapReactiveUserDetailsService users() {
        // {noop} chỉ để demo local. Production dùng password hash/IdP.
        UserDetails gateway = User.withUsername("gateway")
            .password("{noop}connect-pass")
            .roles("CONNECT")
            .build();

        UserDetails alice = User.withUsername("alice")
            .password("{noop}alice-pass")
            .roles("VIEWER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password("{noop}bob-pass")
            .roles("VIEWER")
            .build();

        return new MapReactiveUserDetailsService(
            gateway, alice, bob);
    }

    @Bean
    PayloadSocketAcceptorInterceptor rsocketSecurity(
            RSocketSecurity rsocket) {

        return rsocket
            .authorizePayload(authorize -> authorize
                .setup().hasRole("CONNECT")
                .route("identity.whoami").hasRole("VIEWER")
                .route("tenant.feed").hasRole("VIEWER")
                .anyRequest().denyAll()
                .anyExchange().permitAll()
            )
            .simpleAuthentication(Customizer.withDefaults())
            .build();
    }
}
~~~

Điểm mấu chốt:
- `.setup().hasRole("CONNECT")` kiểm credential kết nối.
- `.route(...).hasRole("VIEWER")` kiểm credential của request có route.
- Alice/Bob không có CONNECT; gateway không có VIEWER.
- Một người dùng có thể **gửi password sai** hoặc không cung cấp per-request metadata; hệ thống không được chấp thuận chỉ vì SETUP service account thành công.
- `.anyRequest().denyAll()` ngăn route không có chính sách rõ; `.anyExchange().permitAll()` xử lý exchanges không phải request có metadata; tiếp nối PAYLOAD vẫn phải được app kiểm khi cần.
- Spring Boot tự lắp RSocket security interceptor theo auto-config khi có dependencies đúng. Nếu tự bootstrapping `RSocketServer` ngoài Boot, cần gắn `SecuritySocketAcceptorInterceptor`.
- **Đừng bỏ `@EnableRSocketSecurity`** và tự giả định Spring Security HTTP filter sẽ bảo vệ RSocket TCP.

### 8.7. TenantPolicy.java

~~~java
package demo;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class TenantPolicy {

    private final Map<String, Set<String>> grants =
        new ConcurrentHashMap<>();

    public TenantPolicy() {
        reset();
    }

    public synchronized void reset() {
        grants.clear();

        Set<String> alice = ConcurrentHashMap.newKeySet();
        alice.add("tenant-a");

        Set<String> bob = ConcurrentHashMap.newKeySet();
        bob.add("tenant-b");

        grants.put("alice", alice);
        grants.put("bob", bob);
    }

    public Mono<Boolean> mayRead(
            String authenticatedUser,
            String tenant) {

        // Mô phỏng kiểm quyền động trên mỗi lần subscribe.
        // Production: reactive DB/service, không blocking.
        return Mono.fromSupplier(() -> {
            Set<String> memberships =
                grants.getOrDefault(
                    authenticatedUser, Set.of());

            return memberships.contains(tenant);
        });
    }

    public void revoke(
            String authenticatedUser,
            String tenant) {

        Set<String> memberships = grants.get(authenticatedUser);

        if (memberships != null) {
            memberships.remove(tenant);
        }
    }
}
~~~

Ý nghĩa:
- `mayRead` dùng **tên đã xác thực**, không dùng `payload.userId`.
- Mỗi lần subscriber gọi `mayRead`, kết quả đọc trạng thái membership hiện hành.
- `ConcurrentHashMap.newKeySet()` và `Mono.fromSupplier` chỉ mô phỏng nonblocking memory access, không phải database.
- `revoke` có thể khiến những lần kiểm sau trả false. Test đơn vị kiểm được điều đó.
- Không dùng `MapReactiveUserDetailsService` làm cơ sở dữ liệu tenant production.

Giới hạn: `reset()` dành cho test/lab. Trong production, membership phải được quản lý trong datastore thật với access control và audit; không mở REST/RSocket endpoint public để reset quyền.

### 8.8. IdentityController.java

~~~java
package demo;

import java.time.Duration;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class IdentityController {

    private final TenantPolicy tenantPolicy;

    public IdentityController(TenantPolicy tenantPolicy) {
        this.tenantPolicy = tenantPolicy;
    }

    @MessageMapping("identity.whoami")
    public Mono<String> whoami() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context ->
                context.getAuthentication().getName());
    }

    @MessageMapping("tenant.feed")
    public Flux<String> feed(@Payload String tenant) {
        return ReactiveSecurityContextHolder.getContext()
            .flatMapMany(context -> {
                String authenticatedUser =
                    context.getAuthentication().getName();

                // 4 items; trước MỖI emission kiểm tenant quyền hiện hành.
                return Flux.interval(Duration.ofMillis(80))
                    .take(4)
                    .concatMap(index ->
                        tenantPolicy
                            .mayRead(authenticatedUser, tenant)
                            .flatMap(allowed -> allowed
                                ? Mono.just(authenticatedUser
                                    + ":" + tenant + ":" + index)
                                : Mono.error(
                                    new AccessDeniedException(
                                        "Tenant access revoked"))
                            )
                    );
            });
    }
}
~~~

**Tại sao không lấy `user` từ payload?** Tên user đã lấy từ `ReactiveSecurityContextHolder` của request/stream đã được Spring Security xác thực. Request chỉ cung cấp `tenant` như **mục tiêu yêu cầu**; server vẫn đối chiếu với `TenantPolicy` trước từng emission.

**Không tự `subscribe()`:** Controller trả `Mono`/`Flux`; Spring/RSocket framework quản lý subscription và cancellation. `Flux.interval` chỉ tạo bốn sự kiện demo và có demand/backpressure. Production có event source thật, giới hạn concurrency/buffer/timeout và kiểm quyền ở data source.

**Tại sao kiểm trước mỗi emission?** Nếu membership của Alice bị thu hồi sau item đầu, item tiếp theo sẽ bị từ chối thay vì tiếp tục chỉ vì route authorization ban đầu đã PASS. Nhưng vẫn có race giữa lần kiểm và lúc thực sự phát item; khi dữ liệu nhạy cảm, cần thiết kế gate gần data boundary và chính sách consistency.

## 9. RSocket integration tests qua TCP bằng StepVerifier

Các tests này kết nối tới một RSocket server thật chạy ở **port ngẫu nhiên** trong application context, không chỉ gọi controller method. Chúng kiểm:
- SETUP thiếu hoặc không có role CONNECT.
- SETUP gateway hợp lệ, request Alice/Bob có ROLE_VIEWER.
- Một connection dùng nhiều user requests mà không trộn identity.
- Bỏ quên per-request credential thì gateway không có quyền đọc.
- Sai password/tenant bị chặn.
- Request-stream kiểm tenant trong application layer.
- Policy nhận diện thu hồi quyền trong một kiểm tra mới.

### 9.1. RSocketIdentityTests.java

~~~java
package demo;

import java.time.Duration;
import java.util.function.Function;

import io.rsocket.metadata.WellKnownMimeType;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(properties = "spring.rsocket.server.port=0")
class RSocketIdentityTests {

    private static final MimeType AUTH_MIME =
        MimeTypeUtils.parseMimeType(
            WellKnownMimeType
                .MESSAGE_RSOCKET_AUTHENTICATION.getString());

    @LocalRSocketServerPort
    int port;

    @Autowired
    RSocketRequester.Builder requesterBuilder;

    @Autowired
    TenantPolicy tenantPolicy;

    @BeforeEach
    void resetPermissions() {
        tenantPolicy.reset();
    }

    private UsernamePasswordMetadata gatewayCredential() {
        return new UsernamePasswordMetadata(
            "gateway", "connect-pass");
    }

    private UsernamePasswordMetadata aliceCredential() {
        return new UsernamePasswordMetadata(
            "alice", "alice-pass");
    }

    private UsernamePasswordMetadata bobCredential() {
        return new UsernamePasswordMetadata(
            "bob", "bob-pass");
    }

    private RSocketRequester sharedRequester() {
        return requesterBuilder
            .rsocketStrategies(builder ->
                builder.encoder(new SimpleAuthenticationEncoder()))
            .setupMetadata(gatewayCredential(), AUTH_MIME)
            .tcp("localhost", port);
    }

    // Đóng connection sau khi publisher hoàn thành hoặc lỗi/cancel.
    private <T> Mono<T> usingRequester(
            Function<RSocketRequester, Mono<T>> operation) {

        return Mono.defer(() -> {
            RSocketRequester requester = sharedRequester();

            return operation.apply(requester)
                .doFinally(signal -> requester.dispose());
        });
    }

    private <T> Flux<T> usingRequesterFlux(
            Function<RSocketRequester, Flux<T>> operation) {

        return Flux.defer(() -> {
            RSocketRequester requester = sharedRequester();

            return operation.apply(requester)
                .doFinally(signal -> requester.dispose());
        });
    }

    @Test
    void gatewaySetupPlusAliceRequestReturnsAlice() {
        StepVerifier.create(
            usingRequester(requester -> requester
                .route("identity.whoami")
                .metadata(aliceCredential(), AUTH_MIME)
                .retrieveMono(String.class)))
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void sameConnectionCanProcessAliceThenBobSeparately() {
        StepVerifier.create(
            usingRequesterFlux(requester -> Flux.concat(
                requester.route("identity.whoami")
                    .metadata(aliceCredential(), AUTH_MIME)
                    .retrieveMono(String.class),
                requester.route("identity.whoami")
                    .metadata(bobCredential(), AUTH_MIME)
                    .retrieveMono(String.class)
            )))
            .expectNext("alice", "bob")
            .verifyComplete();
    }

    @Test
    void gatewaySetupIdentityAloneCannotReadUserRoute() {
        StepVerifier.create(
            usingRequester(requester -> requester
                .route("identity.whoami")
                .retrieveMono(String.class)))
            .expectError()
            .verify();
    }

    @Test
    void wrongRequestPasswordDoesNotInheritGatewayPrivilege() {
        StepVerifier.create(
            usingRequester(requester -> requester
                .route("identity.whoami")
                .metadata(
                    new UsernamePasswordMetadata(
                        "alice", "wrong-password"),
                    AUTH_MIME)
                .retrieveMono(String.class)))
            .expectError()
            .verify();
    }

    @Test
    void aliceCanStreamFromTenantA() {
        StepVerifier.create(
            usingRequesterFlux(requester -> requester
                .route("tenant.feed")
                .metadata(aliceCredential(), AUTH_MIME)
                .data("tenant-a")
                .retrieveFlux(String.class)))
            .expectNext(
                "alice:tenant-a:0",
                "alice:tenant-a:1",
                "alice:tenant-a:2",
                "alice:tenant-a:3")
            .verifyComplete();
    }

    @Test
    void aliceCannotRequestTenantBByChangingPayload() {
        StepVerifier.create(
            usingRequesterFlux(requester -> requester
                .route("tenant.feed")
                .metadata(aliceCredential(), AUTH_MIME)
                .data("tenant-b")
                .retrieveFlux(String.class)))
            .expectError()
            .verify();
    }

    @Test
    void bobCanStreamFromTenantB() {
        StepVerifier.create(
            usingRequesterFlux(requester -> requester
                .route("tenant.feed")
                .metadata(bobCredential(), AUTH_MIME)
                .data("tenant-b")
                .retrieveFlux(String.class)))
            .expectNext(
                "bob:tenant-b:0",
                "bob:tenant-b:1",
                "bob:tenant-b:2",
                "bob:tenant-b:3")
            .verifyComplete();
    }

    @Test
    void policyRevocationAffectsSubsequentChecks() {
        StepVerifier.create(
            tenantPolicy.mayRead("alice", "tenant-a"))
            .expectNext(true)
            .verifyComplete();

        tenantPolicy.revoke("alice", "tenant-a");

        StepVerifier.create(
            tenantPolicy.mayRead("alice", "tenant-a"))
            .expectNext(false)
            .verifyComplete();
    }

    @Test
    void requestCannotClaimUnknownUser() {
        StepVerifier.create(
            usingRequester(requester -> requester
                .route("identity.whoami")
                .metadata(
                    new UsernamePasswordMetadata(
                        "mallory", "anything"),
                    AUTH_MIME)
                .retrieveMono(String.class)))
            .expectError()
            .verify();
    }
}
~~~

**Chín tests** được viết ở đây. Với những test `expectError()`, lớp lỗi có thể được đóng gói thành RSocket application error khác nhau theo version. Vì vậy test đúng sự kiện bị từ chối mà không đoán cố định chuỗi exception hoặc status code HTTP (RSocket không phải HTTP).

### 9.2. Vì sao không gắn @LocalServerPort HTTP?

Annotation đúng trong Spring Boot **3.3.13** cho RSocket server test là:

~~~java
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
~~~

Không dùng `@LocalServerPort` của HTTP web server để nối tới RSocket TCP. Test đặt `spring.rsocket.server.port=0` để chọn ngẫu nhiên một port, tránh xung đột với server local. Port được cung cấp qua `@LocalRSocketServerPort`.

### 9.3. Giới hạn kiểm thử

Bộ test kiểm ranh giới setup/request với **Simple Authentication**, chưa kiểm:
- JWT signature/JWKS retrieval/issuer/audience/expiry ở RSocket.
- Reauthentication bằng JWT mới trong cùng connection sau token refresh.
- Thực sự thu hồi quyền ở giữa `REQUEST_STREAM` đúng thời điểm T3 (test `policyRevocationAffectsSubsequentChecks` chỉ xác nhận policy thay đổi giữa hai check).
- Network TLS/mTLS, gateway header/metadata translation, reconnect và resume.
- Multiple connections/streams được stress test ở tải lớn.
- Timeouts/backpressure, stream limit và cancellation dưới lỗi hạ tầng.

Để test revoke giữa stream, có thể xây integration test kiểm soát sự kiện bằng `Sinks.Many` hoặc một event source nhân tạo có latch, không dựa hoàn toàn vào sleep/timers. Dừng stream và xác minh không phát thêm item sau khi signal revoke đã được xử lý.

### 9.4. Chạy project

Yêu cầu JDK 17+, Gradle 8.x, Maven Central để tải dependencies lần đầu:

~~~bash
gradle test
~~~

Nếu có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Trên Windows dùng `gradlew.bat test`. **Không có log biên dịch thực tế ở đây**; kết quả `BUILD SUCCESSFUL` chỉ có thể khẳng định sau khi chạy đúng môi trường. Test `Mono/Flux` không phụ thuộc HTTP port hoặc Authorization Server ngoài.

Chạy RSocket server:

~~~bash
gradle bootRun
~~~

Ứng dụng lắng nghe RSocket TCP `localhost:7000`. Đây **không phải** một website HTTP, nên truy cập `http://localhost:7000` bằng browser không cho kết quả API như HTTP/REST. Có thể dùng Java `RSocketRequester` như ở tests để gọi các routes.

## 10. Phiên bản thiết kế dùng JWT thay Simple Authentication

Trong môi trường enterprise, credential setup có thể là **service account token**, request credential là **end-user access token**. Một sơ đồ:

~~~text
HTTP end user Alice/Bob
           │
           ▼
Gateway có service identity G
           │ SETUP: G token, audience=rsocket-connect
           │ REQUEST Alice: Alice access token, audience=report-api
           │ REQUEST Bob: Bob access token, audience=report-api
           ▼
RSocket resource service:
  SETUP: kiểm service issuer/aud/role CONNECT
  REQUEST: kiểm user issuer/aud/role VIEWER
  STREAM ITEM: kiểm tenant/resource policy
~~~

### 10.1. RSocketSecurity JWT

Một cấu hình trích cho một loại JWT trust domain:

~~~java
@Bean
PayloadSocketAcceptorInterceptor jwtInterceptor(
        RSocketSecurity rsocket) {

    return rsocket
        .authorizePayload(authorize -> authorize
            .setup().hasRole("CONNECT")
            .route("identity.whoami").hasRole("VIEWER")
            .route("tenant.feed").hasRole("VIEWER")
            .anyRequest().denyAll()
            .anyExchange().permitAll())
        .jwt(Customizer.withDefaults())
        .build();
}
~~~

Cần một `ReactiveJwtDecoder` bean phù hợp và authority converter/claim policy tương thích với `ROLE_CONNECT` và `ROLE_VIEWER`. **Không** cho rằng Spring Security mặc định chuyển `scope=connect` thành `ROLE_CONNECT`: default JWT scope thường là `SCOPE_connect`. Nếu muốn `hasRole("CONNECT")`, phải ánh xạ role một cách tường minh theo issuer policy hoặc dùng `hasAuthority("SCOPE_connect")`.

### 10.2. Hai issuers hoặc hai token profiles

Nếu setup token do Gateway Service Identity Provider phát, còn end-user JWT do OIDC issuer khác phát:
- Không chỉ dùng một decoder rồi chấp nhận tùy ý issuer.
- Cần cơ chế phân loại trust domains/decoder theo **trusted issuer allowlist**, đúng `aud` cho từng lớp.
- Setup credential cần chứng minh service được phép mở connection, không tự chứng minh quyền của Alice.
- Request token cần chứng minh end user, không tự gán ROLE_CONNECT.
- Tránh “token substitution”: một ID Token cho OAuth client không được dùng như access token của RSocket resource server.
- Không bật `alg=none`, không tải JWKS từ `jku` hay issuer do attacker tự giới thiệu mà chưa được allowlist.
- Có thể chọn giải pháp **mTLS cho service connection + JWT end user per request**, thay vì ép mọi lớp vào một JWT auth manager duy nhất.

### 10.3. Token relay và confused deputy

Một Gateway giữ connection có thể vô tình dùng service token để gọi mọi resource thay end user; lúc đó nó trở thành **confused deputy**. Cần:
- Explicit mapping từ incoming user authentication tới RSocket outgoing per-request metadata.
- Không lưu `currentUser` trong một singleton requester.
- Token exchange/audience restriction nếu access token từ HTTP frontend không dành cho downstream.
- Context propagation đúng Reactor Context; không dựa vào mutable ThreadLocal khi dùng `publishOn/subscribeOn`.
- Audit kết hợp end user ID + service connection identity + route/tenant/object.
- Không forward bearer token sang downstream không có quyền nhận nó.

## 11. Danh tính trong Reactor Context và lỗi rò chéo stream

### 11.1. Không sử dụng mutable connection state cho mọi user

Sai:

~~~java
class SharedConnection {
    String currentSubject;

    void setSubject(String name) {
        this.currentSubject = name;
    }

    String getSubject() {
        return this.currentSubject;
    }
}
~~~

Hai request đồng thời:
- Request Alice ghi currentSubject = Alice.
- Request Bob ghi currentSubject = Bob.
- Event của stream Alice đọc lại currentSubject và thấy Bob.

Hậu quả có thể gồm leak dữ liệu, audit gán sai chủ thể, permission check sai, cross-tenant access. Cách đúng là dùng **request-specific Authentication** trong Reactor Context, hoặc một immutable authenticated context đã pin riêng cho subscription.

### 11.2. Lấy Authentication trong handler

~~~java
Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context ->
            context.getAuthentication().getName());
}
~~~

Đây là đoạn trích. Nếu callback asynchronous được chạy trên một `new Thread(...)` tự tạo bên ngoài Reactor chain, security context không tự theo vào thread mới. Phải compose với publishers đúng, không dùng `SecurityContextHolder.getContext()` ThreadLocal của Servlet để xác định user trong RSocket handler.

### 11.3. Phân biệt authenticated subject và requested subject

Một payload:

~~~json
{
  "subject": "admin",
  "tenant": "tenant-victim",
  "reportId": "report-123"
}
~~~

chỉ là **yêu cầu của client**. Backend phải lấy subject từ Authentication đã verify rồi kiểm:
- Requested subject có trùng identity hoặc được policy cho phép truy cập thay không?
- Report có thuộc tenant mà user là member không?
- Resource owner/ACL có hợp lệ không?
- Nếu account bị disabled/revoked trong lúc stream đang chạy, có recheck không?

Đừng gán `Authentication` mới dựa trên JSON payload trong controller.

## 12. Lỗi authorization thường gặp

| Triệu chứng | Nguyên nhân | Cách kiểm |
| --- | --- | --- |
| Alice/Bob bị trộn dữ liệu trên shared connection | Đặt end-user credentials ở SETUP hoặc global currentUser | Chuyển credentials sang mỗi request metadata |
| Service gateway mở connection nhưng đọc được dữ liệu user | Role CONNECT cũng được cấp VIEWER hoặc route quá rộng | Tách ROLE_CONNECT và ROLE_VIEWER |
| Alice không thể mở RSocket connection | SETUP yêu cầu CONNECT, Alice chỉ có VIEWER | Dùng trusted service setup credential |
| Request thiếu per-request credentials vẫn được xem dữ liệu | SETUP principal có VIEWER hoặc route cho authenticated connection | Tách setup/request roles, test missing metadata |
| Bob dùng metadata Alice do dùng requester pool | Biến state toàn cục hoặc metadata sai | Immutable per-request metadata |
| Stream vẫn phát sau user logout | Auth chỉ ở request start, không có per-item revoke | Cancel/recheck/stream TTL |
| JWT hết hạn nhưng stream vẫn chạy | Không có expiry enforcement sau request mở | TTL/cancel/reconnect strategy |
| REQUEST_CHANNEL một message giả userId | Data field bị coi là identity | Pin verified principal, reauthorize each command |
| `@MessageMapping` route chạy mà chưa login | Không gắn RSocketSecurity interceptor hoặc route permitAll | Kiểm Boot auto config và order matcher |
| Route cần role nhưng token có scope | `ROLE_*` khác `SCOPE_*` | Converter/prefix policy rõ |
| JWT ở HTTP header nhưng RSocket request anonymous | Không gửi RSocket auth metadata | Dùng BearerTokenMetadata |
| Kết nối RSocket TCP qua browser thất bại | Browser không gọi TCP RSocket trực tiếp | RSocket over WebSocket + protocol client |
| `@LocalServerPort` không trỏ RSocket port | HTTP annotation khác RSocket port | `@LocalRSocketServerPort` |
| Token mới nhưng requester cũ vẫn identity cũ | Setup credential không thay theo request | Reconnect hoặc request-scoped metadata |
| Service verify signature đúng nhưng sai tenant | Chỉ kiểm JWT route, không kiểm object/tenant | Local membership + repository tenant predicates |
| Gateway có mTLS nên tin mọi end user | Service identity ≠ user identity | User request token riêng |
| Request ở setup bị từ chối do role | `setup().hasRole` không match | Kiểm authorities, matcher order |
| Sau revoke mất kết nối và retry vô hạn | Không có retry budget/backoff | Token refresh + bounded retries + cleanup |

### 12.1. RSocket errors không phải mã HTTP 401/403

RSocket transport giao tiếp bằng frame/errors, không phải HTTP status codes cho từng request. Khi authentication hoặc authorization bị từ chối, client nhận RSocket error (thường được convert thành exception ở phía requester). **Đừng khẳng định** rằng request RSocket phải nhận status `401 Unauthorized` hoặc `403 Forbidden` như REST.

Nếu RSocket qua WebSocket, HTTP status của **handshake** và lỗi RSocket xảy ra **sau khi connection mở** là hai vấn đề khác nhau. Ghi log/error metrics riêng cho setup rejection, request denial, token validation và stream revocation.

## 13. Bảo mật và hiệu năng khi phát stream dài

### 13.1. Không check DB blocking mỗi payload

Nếu per-item authorization truy cập database:
- Dùng reactive R2DBC/WebClient thay JDBC blocking trong Netty event loop.
- Có indexing theo user/tenant/resource để không gây N+1 queries khổng lồ.
- Với các quyền ổn định, có thể cache ngắn hạn kèm version/revocation signal.
- Nếu cache TTL dài, quyền vừa bị revoke có thể tiếp tục được cấp; xác định thời gian tối đa.
- Gắn timeout/retry budget và fail closed khi không chắc.
- Ưu tiên kiểm row-level tenant boundaries trong query để không đọc sai dữ liệu trước khi lọc.

### 13.2. Cancellation và leak tài nguyên

Khi client cancel `REQUEST_STREAM`:
- Không tiếp tục gửi event nếu subscription đã cancel.
- Dọn DB cursor, event-bus subscription, buffers, security state và metrics tags.
- Giới hạn active streams per user/tenant/service connection.
- Không giữ access token trong logs hoặc các biến global vô thời hạn.
- Kiểm memory/CPU khi có hàng ngàn subscriptions trên một RSocket connection.

### 13.3. Reauth có thể gây gián đoạn UX

Nếu client refresh token giữa khi xem dashboard:
- Có thể kết thúc stream cũ với một lỗi có ngữ nghĩa “reauth required” phù hợp ứng dụng.
- Client lấy token mới qua OAuth2 flow/refresh policy rồi mở một request-stream mới.
- Sử dụng resume cursor/event ID đã xác minh để tránh mất sự kiện, **không** dùng resume cursor làm credential.
- Chống replay/duplicate processing nếu request stream có side effects (thường stream read-only, nhưng REQUEST_CHANNEL có thể ghi).
- Bảo đảm mỗi lần reconnect/re-subscribe đều kiểm tenant membership mới.

### 13.4. Quan sát vận hành

Nên đo:
- Số SETUP success/failure theo service identity đã ẩn danh.
- Số route authorization success/deny theo route và class quyền, không log raw JWT.
- Active connections, active streams, tuổi stream, số times cancelled/revoked.
- Token validation failures theo nhóm: issuer, audience, signature, expired, malformed.
- Latency/timeout của membership checks; số lần deny cross-tenant.
- Tỷ lệ connect/reconnect/resume và event replay, Backpressure pressure.
- Không log mật khẩu Simple Authentication, bearer token, refresh token hoặc payload PII.

## 14. Bài tập tình huống

### Bài 1 — Mobile một user

Một mobile app chỉ dùng tài khoản Alice trên mỗi kết nối. Nên xác thực ở đâu?

**Gợi ý:** SETUP auth có thể đủ cho khởi tạo nếu lifetime/revoke policy rõ; stream nhạy cảm vẫn có thể cần per-event check.

### Bài 2 — Gateway nhiều users

Một gateway mở một kết nối cho 200 users. Có nên đặt JWT của user đăng nhập đầu tiên ở SETUP không?

**Đáp án:** Không. SETUP nên chứng minh gateway/service; request riêng gắn end-user credential tương ứng. Nếu không, mọi user có nguy cơ bị gán identity đầu tiên.

### Bài 3 — SETUP và REQUEST

Gateway có ROLE_CONNECT, Alice có ROLE_VIEWER. Gateway gửi GET-like request không có user metadata. Được không?

**Đáp án:** Không nên được phép đọc dữ liệu; role CONNECT khác VIEWER.

### Bài 4 — Bob cùng connection

Gateway gửi request Alice rồi Bob qua cùng requester. Backend `whoami` cần trả gì?

**Đáp án:** Alice cho request đầu và Bob cho request sau, do per-request authentication metadata; không dùng currentUser global.

### Bài 5 — Metadata vs data

Bob gửi payload `{"userId":"alice"}` nhưng metadata có credential Bob. Backend có được mở dữ liệu Alice?

**Đáp án:** Không, trừ khi Bob có quyền truy cập thay được kiểm riêng theo business policy. Identity authenticated vẫn là Bob.

### Bài 6 — Request-stream nhiều frames

Spring Security kiểm route khi stream bắt đầu. Liệu nó tự verify JWT chữ ký lại trên từng PAYLOAD #2, #3, #4 không?

**Đáp án:** Không nên giả định. Security route/request matching diễn ra ở request khởi tạo; per-event permission/expiry phải do kiến trúc bổ sung.

### Bài 7 — JWT hết hạn

JWT exp 10:05, stream mở lúc 10:00. 10:10 có nên tiếp tục phát bản ghi bí mật?

**Đáp án:** Phải có policy. Nếu yêu cầu strict expiry, stream cần dừng trước/đúng exp hoặc reauthorize, không dựa vào auth tại T0.

### Bài 8 — Logout và reconnect

Alice logout ở frontend nhưng backend giữ stream dài. Làm thế nào?

**Đáp án:** Client cancel/close, server nhận revocation signal hoặc kiểm local state per event, dừng streams của Alice theo policy.

### Bài 9 — Channel với nhiều users

Một RSocket REQUEST_CHANNEL chứa mỗi payload một `userId` khác. Có được xem là reauthentication không?

**Đáp án:** Không. Dữ liệu self-declared không chứng minh danh tính. Cần protocol identity đã verify hoặc tách requests.

### Bài 10 — TokenRelay

Gateway có HTTP JWT Alice. Có thể forward nó trực tiếp qua RSocket tới service bất kỳ?

**Đáp án:** Không. Phải kiểm đúng access token audience/scopes/consent và dùng RSocket bearer metadata; token exchange nếu downstream khác audience.

### Bài 11 — Per-item DB check

Per-item authorization dùng JDBC `findMembership` trong `Flux.map`. Có phù hợp reactive không?

**Đáp án:** Không. Blocking I/O có thể chặn event loop. Dùng R2DBC/WebClient reactive hoặc isolation được review.

### Bài 12 — Token signature/role

JWT `scope=read` có được dùng cho `hasRole("READER")` mặc định không?

**Đáp án:** Không. Scopes thường thành `SCOPE_read`, không tự thành `ROLE_READER`.

### Bài 13 — Tenant mismatch

Alice authenticated trên tenant-a nhưng payload yêu cầu tenant-b. Có được lấy event feed tenant-b không?

**Đáp án:** Không, trừ khi được membership service xác minh có quyền. Payload là đối tượng được yêu cầu, không là bằng chứng quyền.

### Bài 14 — Shared connection audit

Audit log chỉ ghi `connectionId=xyz` mà không ghi end-user principal. Có đủ không?

**Đáp án:** Không với connection đa user. Cần service connection identity và request user identity + route/tenant/decision.

### Bài 15 — Resume RSocket

Client resume stream sau mất mạng. Resume token có tự chứng minh JWT user còn hạn không?

**Đáp án:** Không. Resume là giao thức khôi phục stream; phải định nghĩa security validity/reauth/TTL riêng.

### Bài 16 — Gateway impersonation

Gateway có mTLS, nhận `userId=admin` từ HTTP body rồi tạo per-request auth metadata dưới danh admin. Có an toàn?

**Đáp án:** Không. Gateway phải lấy principal từ **verified incoming authentication**, không từ body do client gửi.

### Bài 17 — anyExchange().permitAll()

Quy tắc này có nghĩa mọi event PAYLOAD đều đã được authorize không?

**Đáp án:** Không. Nó thường cho phép các exchanges không phải request có route/metadata đi qua; app vẫn cần kiểm quyền per-event nếu cần.

### Bài 18 — Ai có thể mở connection?

Nếu Alice/Bob có VIEWER nhưng không CONNECT, họ có thể gửi request metadata Alice ngay từ một SETUP do Alice tự tạo không?

**Đáp án:** Không nếu setup rule yêu cầu ROLE_CONNECT và Alice thiếu quyền đó. Phải có trusted connection identity hợp lệ.

### Bài 19 — AUTH MIME

Gửi string `"alice"` ở metadata bất kỳ có được coi là Simple Authentication không?

**Đáp án:** Không. Cần MIME/format của RSocket authentication metadata và credential được server xác minh.

### Bài 20 — QA production cần gì ngoài tests mẫu?

**Đáp án:** E2E TLS/mTLS, JWT signature/expiry, shared connection concurrency, revoke giữa stream với Sinks, multi-tenant ACL, reconnect/resume, load/backpressure, cancellation và service failure.

## 15. Checklist bảo mật và kiến trúc

### Authentication

- [ ] Xác định rõ **connection identity** và **request identity** khác nhau khi dùng shared connection.
- [ ] `SETUP` có policy service/device authentication và lifecycle hợp lệ.
- [ ] `REQUEST_*` có auth metadata riêng khi một connection phục vụ nhiều users.
- [ ] Không lưu `currentUser` mutable dùng chung cho mọi streams.
- [ ] Không lấy principal/role từ payload, userId, tenantId hoặc metadata tự khai chưa được verify.
- [ ] JWT access token có issuer, audience, signature, alg, exp và purpose validation đúng.
- [ ] Không dùng ID Token OIDC thay access token của resource server.
- [ ] Service-to-service mTLS không thay end-user authorization.
- [ ] Token refresh không ngầm đổi identity của SETUP đang sống.
- [ ] Reconnect/resume có reauthentication/revalidation policy rõ ràng.

### Authorization và luồng dài

- [ ] Quy tắc `setup()`, `route()`, `anyRequest()`, `anyExchange()` được sắp thứ tự đúng.
- [ ] Role connection CONNECT không tự đủ quyền xem data của user.
- [ ] Per-request role VIEWER chỉ từ authenticated metadata.
- [ ] Per-payload continuation không bị giả định là authn/authz mới.
- [ ] Với stream nhạy cảm, có per-event entitlement checks/cancel-on-revoke/TTL.
- [ ] Authentication lấy từ Reactor Context của request, không ThreadLocal.
- [ ] Quyền tenant/object được kiểm tại service/data boundary.
- [ ] Local membership disabled/revoked được phát hiện theo SLA bảo mật.
- [ ] DB entitlement lookup không blocking trong event loop.
- [ ] Backpressure/buffers/stream length/active subscriptions bị giới hạn.
- [ ] Khi cancel, cleanup tài nguyên và dừng phát event.

### Kiểm thử/vận hành

- [ ] SETUP không credential/không CONNECT → từ chối.
- [ ] Gateway CONNECT hợp lệ + Alice VIEWER request → Alice.
- [ ] Cùng connection + Bob VIEWER request → Bob, không rò context.
- [ ] Gateway CONNECT không request credential → không vào route VIEWER.
- [ ] Sai per-request password/JWT → từ chối.
- [ ] Payload tenant-b của Alice tenant-a → từ chối.
- [ ] Stream Alice tenant-a hợp lệ → phát đúng các items.
- [ ] Revoke trong stream → dừng events theo policy.
- [ ] Expiring JWT trong stream → policy xử lý nhất quán.
- [ ] Kiểm REQUEST_CHANNEL continuation không tạo identity giả.
- [ ] Test metrics và trace IDs, không log secrets/raw tokens/PII.
- [ ] Stress test hàng nghìn streams, cancellation, outage và resume.
- [ ] Spring Boot/Security production được nâng cấp sang version còn hỗ trợ.

## 16. Nguồn tài liệu chính thức

- Spring Security — RSocket Security, Authentication at Setup versus Request Time, JWT, Authorization: https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html
- Spring Security 6.3 RSocket Security API — `RSocketSecurity` và payload authorization: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html
- Spring Framework — RSocket, SETUP/REQUEST_STREAM/REQUEST_CHANNEL/PAYLOAD, backpressure và RSocketRequester: https://docs.spring.io/spring-framework/reference/rsocket.html
- Spring Boot 3.3 — RSocket Server Auto-configuration và TCP/WebSocket settings: https://docs.spring.io/spring-boot/3.3/reference/messaging/rsocket.html
- Spring Boot 3.3 Test API — `@LocalRSocketServerPort`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/rsocket/server/LocalRSocketServerPort.html
- RSocket Protocol — SETUP, REQUEST, PAYLOAD, Metadata, CANCEL, RESUME: https://github.com/rsocket/rsocket/blob/master/Protocol.md
- RSocket Authentication Metadata Extension: https://github.com/rsocket/rsocket/blob/master/Extensions/Security/Authentication.md
- Spring Security — Reactive Security Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Project Reactor — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

**Ghi nhớ:** Kết nối RSocket dài hạn là một **kênh truyền**, không phải bằng chứng rằng mọi request cùng một end user. Xác thực SETUP để biết **ai có quyền mở kết nối**, xác thực từng REQUEST có metadata để biết **ai đang yêu cầu tác vụ**, và nếu stream dài/nhạy cảm thì **kiểm lại quyền theo item hoặc đóng stream khi revoke/expiry**. Đặc biệt, các PAYLOAD tiếp nối trong REQUEST_STREAM/REQUEST_CHANNEL **không mặc định được Spring Security xác thực lại**; thiết kế ứng dụng phải bảo đảm principal/tenant của từng stream được giữ đúng và không rò chéo khi connection được chia sẻ.
