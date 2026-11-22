# 15.7. Session, tái sử dụng phiên và vòng đời kết nối

**Một HTTPS request mới không nhất thiết tạo một TLS connection mới. Một TLS connection mới cũng không nhất thiết làm một full handshake từ đầu.** Hai cơ chế hiệu năng thường bị gọi lẫn là **connection reuse (tái sử dụng kết nối đã mở)** và **TLS session resumption (tiếp tục một phiên bảo mật trước trên kết nối mới)**. Cùng có thể giúp giảm độ trễ, nhưng chúng vận hành ở các tầng khác nhau, yêu cầu trạng thái khác nhau và có hệ quả bảo mật khác nhau.

Trong Java, sự nhầm lẫn còn xuất hiện do các lớp `SSLContext`, `SSLSession`, `SSLSessionContext`, `SSLSocket`, `SSLEngine`, `HttpClient` và cả connection pool có vòng đời riêng. Chẳng hạn `SSLSession.isValid() == true` **không chứng minh TCP socket đang mở**; `SSLSession.invalidate()` **không có nghĩa đóng ngay mọi socket**; và hai request đi cùng một kết nối HTTP/2 **không phải** hai lần TLS session resumption.

Bài này giải thích ba lớp vòng đời: **transport connection**, **TLS secure connection/handshake/session state**, và **application/HTTP request**. Sau đó phân biệt TLS 1.2 session IDs/tickets với TLS 1.3 PSK resumption, cách Java expose session cache, session timeout, ticket expiration, 0-RTT, replay và những giới hạn cần nhớ khi kiểm tra production.

> **Lưu ý tiêu chuẩn:** Tính đến tháng 10/2026, đặc tả TLS 1.3 hiện hành là **RFC 9846 (xuất bản tháng 7/2026)**, thay thế RFC 8446 với những cập nhật làm rõ và siết chặt yêu cầu. Nhiều thư viện và tài liệu Java 17 được viết dựa trên RFC 8446; mô hình session resumption vẫn tương thích, nhưng khi thiết kế mới nên tham chiếu RFC 9846 và yêu cầu của phiên bản JDK/provider thực tế.

## 1. Mục tiêu bài học

Sau khi học, bạn có thể:

- Phân biệt **TLS connection**, **TLS session/resumption state**, **TCP socket**, **HTTP keep-alive/connection pooling**, và **HTTP/2 multiplexing**.
- Giải thích tại sao cùng một `SSLContext` có thể duy trì session cache qua nhiều kết nối, còn một `SSLSocket` chỉ đại diện cho một kết nối cụ thể.
- Mô tả full handshake và resumed handshake ở TLS 1.2/TLS 1.3, gồm `NewSessionTicket`, PSK identity và PSK binder.
- Phân biệt **1-RTT PSK resumption** với **0-RTT early data**, biết vì sao 0-RTT có nguy cơ replay và có các giới hạn forward secrecy.
- Đọc đúng `SSLSession.getProtocol()`, `getCipherSuite()`, `getCreationTime()`, `getLastAccessedTime()`, `getSessionContext()`, `isValid()` và `invalidate()`.
- Cấu hình cơ bản `SSLSessionContext.setSessionTimeout()` và `setSessionCacheSize()` trong Java 17+, đồng thời hiểu rằng điều đó **không ép server chấp nhận resumption**.
- Mô tả kết thúc kết nối, đóng TLS/HTTP, idle timeout, ticket expiration, server restart/rotation và tải cân bằng.
- Xây dựng tiêu chí kiểm thử thật sự xác định được full/resumed handshake; không kết luận chỉ từ timing, HTTP status hoặc session ID.

## 2. Các khái niệm phải tách biệt

| Khái niệm | Cái gì tồn tại? | Có thể sống qua lần request sau? | Điều **không** suy ra |
| --- | --- | --- | --- |
| TCP connection | Luồng byte giữa client/server qua socket (TLS over TCP) | Có, nếu còn mở và application cho tái dùng | Không nói handshake đã resumption hay chưa |
| TLS connection | Trạng thái record-layer bảo mật, keys và sequence numbers cho một kết nối | Có, trong chính kết nối còn sống | Không mặc định chuyển nguyên traffic keys sang socket mới |
| TLS handshake | Quá trình thương lượng thông số, key agreement, authentication | Thường một lần ban đầu cho kết nối, có các trường hợp cập nhật theo protocol | Không phải “mỗi HTTP request một handshake” |
| TLS session/resumption state | Thông tin cho phép nối tiếp một sự xác thực/kết nối đã thực hiện trên **kết nối mới** | Có nếu cache/ticket/policy còn hợp lệ | Không bằng một TCP socket |
| TLS session ticket | Vật mang/định danh cho resumption state hoặc PSK theo phiên bản TLS | Có theo lifetime/chính sách | Không phải password, không phải token ứng dụng |
| HTTP request/response | Một thao tác nghiệp vụ của client | Mỗi thao tác có vòng đời riêng | Không tự sinh session TLS mới |
| HTTP persistent connection | HTTP/1.1 keep-alive hoặc HTTP/2 connection còn mở | Nhiều requests dùng cùng connection | **Không** phải TLS resumption |
| Connection pool | Bộ quản lý nhiều kết nối tới origin/route | Có trong thời gian pool giữ kết nối | Không bảo đảm server vẫn chấp nhận TLS tickets |
| Session cookie/token ứng dụng | Trạng thái đăng nhập của user/app | Có qua nhiều kết nối TLS | Không phải `SSLSession` hay TLS session ticket |

Một sơ đồ ba lớp:

```text
ỨNG DỤNG (HTTPS)
    Request #1  Request #2  Request #3
          \        |        /
           \       |       /
       HTTP/2 streams hoặc HTTP/1.1 keep-alive
                     |
        Một TLS connection đang mở
                     |
             Một TCP connection
                     |
           Socket bị đóng sau idle / EOF
                     |
            Lần sau mở socket mới
                     |
          Full hoặc resumed TLS handshake
                     |
               Request #4
```

**Điểm nhớ:** nếu Request #1 và Request #2 được gửi trên **cùng socket/TLS connection**, bạn đang quan sát **connection reuse**, không phải hai lần resumption. Nếu một socket mới được mở và handshake sử dụng trạng thái xác thực từ trước (ticket/session), đó mới là **TLS session resumption**.

### 2.1. Session không phải HTTP login session

Một người dùng có thể đăng nhập bằng cookie hoặc OAuth token trên một TLS connection, sau đó kết nối mạng được thay mới. HTTP login session có thể vẫn tiếp tục nếu cookie/token còn hiệu lực. Ngược lại, một TLS session có thể được resume giữa các TCP connections mà application-level login đã hết hạn.

Các vòng đời phải độc lập:
- **TLS:** cung cấp kênh mã hóa/xác thực server (và client khi dùng mTLS), phụ thuộc handshake và keys.
- **Authentication ứng dụng:** session cookie, bearer token, mTLS principal mapping hoặc credential.
- **Authorization:** xác định principal có quyền truy cập tài nguyên và hành động hay không, kiểm tra theo chính sách.
- **Business idempotency/replay:** yêu cầu giao dịch lặp được xử lý thế nào.

Không gắn “TLS session còn sống” với “user chắc chắn còn đăng nhập và có quyền như cũ”.

## 3. Full handshake và sử dụng lại kết nối

### 3.1. Full handshake trên một kết nối mới

Ở TLS 1.3, một full certificate-based handshake điển hình (mô tả đơn giản):

```text
Client                                                Server
  |                                                    |
  | --- ClientHello (+ key_share, versions, suites) --> |
  | <-- ServerHello (+ selected key_share) ------------ |
  | <-- EncryptedExtensions / Certificate ------------ |
  | <-- CertificateVerify / Finished ------------------ |
  | --- Finished -------------------------------------> |
  | <============== Application Data =================> |
  |                                                    |
   TCP/TLS connection tiếp tục mang các HTTP requests.
```

Trong full handshake, server thường phải chứng minh identity qua certificate và bằng chứng private key trong handshake. TLS 1.3 key schedule dẫn xuất traffic secrets theo transcript; record-layer keys có phạm vi kết nối và có thể được cập nhật theo protocol.

### 3.2. Tái sử dụng connection

Sau full handshake, client gửi nhiều HTTP requests qua connection còn mở:

```text
TCP connect + TLS full handshake
        |
     HTTP #1 ------- response #1
        |
     HTTP #2 ------- response #2
        |
     HTTP #3 ------- response #3
        |
     Connection idle / closed
```

Với HTTP/1.1 keep-alive, có thể xử lý nhiều request tuần tự trên cùng kết nối theo cơ chế client/server; với HTTP/2, nhiều streams có thể hoạt động đồng thời trên một connection. Trường hợp này không cần một handshake mới giữa Request #1 và #2.

**Không đánh đồng:** connection reuse thường tiết kiệm cả TCP setup và TLS handshake. TLS resumption chỉ giúp **rút gọn handshake khi một transport connection mới vẫn phải mở**, chứ bản thân nó không biến socket mới thành socket cũ.

## 4. TLS 1.2: session ID và session tickets

TLS 1.2 lịch sử có cơ chế full handshake và abbreviated handshake (resumption). Hai biến thể tiêu biểu:

### 4.1. Session ID + server-side session cache

```text
Lần đầu:
    ClientHello --------------> Server
    Full handshake <----------> Certificate/key exchange...
    Server caches session state with session ID
    Client remembers session ID + relevant secrets

Lần sau (new TCP connection):
    ClientHello(session_id) --> Server
    Server finds acceptable cached state?
       yes -> abbreviated handshake -> new connection keys
       no  -> full handshake (or handshake failure by policy)
```

Ưu điểm: giảm chi phí của một số thao tác full handshake. Hạn chế: server cần giữ/tra lại session state phù hợp; load balancer nhiều node có thể phải dùng sticky routing hoặc chia sẻ cache để tăng tỉ lệ resume.

### 4.2. TLS 1.2 session ticket

Cơ chế ticket từng được chuẩn hóa theo RFC 5077 (một tài liệu lịch sử được RFC 9846 thay thế). Server có thể mã hóa/xác thực session state thành opaque ticket cho client giữ. Khi reconnect, client đưa ticket; server có key phù hợp để phục hồi state mà không nhất thiết lưu mỗi session ở database.

Cần nhớ:
- Ticket không làm mất nhu cầu **bảo vệ server-side ticket-encryption key** và vòng đời rotation.
- Key rotation/không chia sẻ ticket keys qua các node có thể làm resumption thất bại và fallback full handshake.
- Chỉ “có ticket” không bắt buộc server phải chấp nhận; còn timeout, cipher suite, scope và policy.
- Không tạo cơ chế tự chế để lưu/giải mã ticket ở application thay cho TLS provider.

### 4.3. Học TLS 1.2 để hiểu, không tự thiết kế giao thức cũ

Các deployment hiện đại ưu tiên TLS 1.3 khi khả dụng; RFC 9846 đã cập nhật yêu cầu và loại bỏ khả năng thương lượng TLS 1.0/1.1. Khi tích hợp hệ thống cũ, cần cấu hình protocol allowlist đúng chính sách, không bật các phiên bản yếu chỉ để tăng tỷ lệ resumption.

TLS 1.2 session resumption và TLS 1.3 PSK resumption **không dùng cùng cú pháp handshake**, dù `SSLSession` của Java là một abstraction áp dụng cho nhiều phiên bản.

## 5. TLS 1.3: resumption bằng PSK và NewSessionTicket

Theo **RFC 9846**, TLS 1.3 gộp khái niệm session resumption vào mô hình **pre-shared key (PSK)**. PSK cho resumption thường được dẫn xuất từ bí mật của phiên trước và được liên hệ với một **ticket** do server phát sau handshake.

### 5.1. Khi nào có ticket?

```text
Full TLS 1.3 handshake
       |
       v
Server authenticates / Finished
       |
       v
Application connection ready
       |
       +--> Server MAY issue NewSessionTicket
                  |
                  +--> Client stores ticket/associated resumption state
                               |
                               v
                     Later: another TCP connection
                               |
                               v
                        ClientHello offers PSK identity
                               |
                     Server MAY accept or decline
```

Các từ **MAY** quan trọng:
- Server **có thể** phát nhiều tickets, một ticket hoặc không phát.
- Client **có thể** không lưu hoặc không offer ticket.
- Server **có thể** từ chối resume dù ticket được client offer.
- Vì `NewSessionTicket` có thể được gửi **sau khi handshake chính kết thúc**, client đóng connection quá nhanh có thể chưa nhận đủ các message cần cho resumption. Tùy framework/provider, việc đọc, cache và xử lý post-handshake messages có thể ảnh hưởng kết quả.
- Ticket có lifetime và giới hạn chính sách; theo RFC 9846, không được cache ticket vô thời hạn chỉ vì application vẫn hoạt động.

### 5.2. Handshake mới với PSK

```text
Client đã có ticket/PSK từ phiên trước        Server giữ được policy/ticket keys
                |                                           |
new TCP connection                             new TCP connection
                |                                           |
ClientHello + PSK identity + binder ---------> |
                |                        Check PSK/ticket age/scope
                |                        and selected handshake mode
                | <---------------- ServerHello + accepts PSK
                |                   (may also use fresh DHE key_share)
                | <---------------- EncryptedExtensions / Finished
Client Finished ------------------------------> |
                |                                           |
          New record-layer traffic keys for this connection
                |                                           |
              Application data over the new TLS connection
```

Trong resumption TLS 1.3, không cần lặp lại cùng một certificate authentication exchange như full certificate-based handshake; server authentication có thể dựa trên PSK được liên hệ từ kết nối trước. **Không được hiểu rằng client không cần kiểm tra tên máy chủ nữa**: implementation phải ràng buộc việc dùng PSK với identity, SNI, ALPN/ứng dụng và security policy phù hợp.

**PSK binder** giúp chứng minh phía client biết PSK phù hợp và ràng buộc phần liên quan của ClientHello. Client không tự gửi plaintext PSK hay tự tạo binder bằng `HMAC(password)` không theo TLS; quá trình này do TLS implementation xử lý.

### 5.3. PSK-only và PSK-DHE không có bảo đảm giống nhau

TLS 1.3 có các mode sử dụng PSK:
- **`psk_ke` (PSK-only):** key establishment dựa vào PSK, không bổ sung fresh (EC)DHE cho 1-RTT handshake theo mode đó.
- **`psk_dhe_ke` (PSK + ephemeral DHE):** có ephemeral key agreement mới, đóng góp forward secrecy cho traffic mới theo thiết kế protocol.

Vì vậy không phát biểu “TLS 1.3 resumed session luôn có fresh DHE” hoặc “resumption luôn bảo vệ hoàn toàn nếu ticket key/PSK lộ”. Cần biết server chọn mode nào, lifetime/rotation ra sao và threat model liên quan.

**Quan trọng với RFC 9846:** không tái sử dụng `KeyShare` giá trị giữa các kết nối khi triển khai protocol. Dùng TLS library chuẩn; không cố cache DH private/public ephemeral keys để “tăng tốc” handshake.

### 5.4. Ticket là bearer material ở tầng TLS

Một ticket không nhất thiết là bí mật thuần dạng raw key, nhưng nó là thành phần liên quan đến khả năng resumption; tài liệu ticket/PSK của TLS provider có thể rất nhạy cảm. Không log raw ticket, PSK hoặc session secrets ra application log. Hệ thống cần bảo vệ ticket key của server và client-side resumption cache, đồng thời quản lý lifetime/revocation/scope.

## 6. 0-RTT early data là gì? Vì sao không giống resumption thông thường?

Ở TLS 1.3, khi đã có PSK phù hợp, protocol **có thể** cho phép client gửi một số application data **ngay trong first flight của handshake mới** (0-RTT early data). Đây là một tính năng tùy chọn, **không đồng nghĩa** mọi TLS 1.3 resumption đều dùng 0-RTT.

```text
Resumption 1-RTT:
ClientHello(PSK offer) -------------------------->
                     <---------------- ServerHello/Finished
Client Finished ------------------------------->
Application Data <=============================>

Resumption + 0-RTT (only when explicitly enabled/accepted):
ClientHello(PSK offer) + Early Data ------------>
                     <---------------- ServerHello/Finished
Client Finished ------------------------------->
Normal Application Data <======================>
```

### 6.1. Khác biệt an toàn

RFC 9846 cảnh báo **0-RTT early data** có tính chất bảo mật yếu hơn 1-RTT data:

1. **Không có forward secrecy cho bản thân 0-RTT data** vì được bảo vệ bằng keys dẫn xuất từ offered PSK, chưa dựa trên fresh server key share cho phiên mới.
2. **Có nguy cơ replay giữa các kết nối**. Attacker có thể tìm cách gửi lại ClientHello/early data tới server hoặc cụm server trong cửa sổ cho phép.
3. Những biện pháp anti-replay ở tầng TLS có thể giảm nguy cơ nhưng **không thay thế kiểm soát lệnh nghiệp vụ**. Điều kiện mạng, multi-region và retries vẫn có thể làm nhận nhiều bản copy dữ liệu.
4. Server có thể **từ chối early data** nhưng tiếp tục handshake. Ứng dụng cần biết dữ liệu nào đã/ chưa được xử lý và cách retry an toàn.
5. Khả năng dùng 0-RTT phụ thuộc protocol/application profile, policy server, ticket và API/provider. **Không giả định Java 17 `HttpClient` tự gửi 0-RTT chỉ vì có cache**.

### 6.2. Ví dụ request được và không được dùng 0-RTT

| Request | 0-RTT mặc định nên như thế nào? | Lý do |
| --- | --- | --- |
| `GET` chỉ đọc, thực sự không có side effect và theo profile cho phép | Có thể cân nhắc | Phải chịu được replay và request authentication policy |
| `HEAD` lấy metadata | Có thể cân nhắc | Cũng cần kiểm tra tình huống logging/billing/rate limits |
| `POST /transfer-money` | **Không** | Một replay có thể kích hoạt giao dịch lặp |
| `POST /delete-account` | **Không** | Hậu quả không idempotent/replay-safe |
| `POST /issue-token` | **Không** nếu có side effect/nonce logic yếu | Replay có thể tạo nhiều credential |
| `POST /create-order` dù có requestId | Mặc định không; chỉ cân nhắc khi đã có profile và idempotency **thực sự an toàn** | Idempotency store phải atomic và scope đúng |
| API có cookie đăng nhập nhưng stateful | Không mặc định | Cookie hợp lệ không có nghĩa request replay-safe |

“HTTP GET thường idempotent” không tự động cho phép mọi GET dùng 0-RTT: có API GET thực tế gây side effect hoặc rò rỉ dữ liệu theo session state. Ứng dụng phải xác nhận tính an toàn, kiểm soát replay và yêu cầu profile cụ thể.

### 6.3. Idempotency không đồng nghĩa hết rủi ro

Dù một endpoint có `Idempotency-Key`, nếu idempotency store chỉ tồn tại trong một node thì hai early-data requests vào hai node có thể vẫn xử lý hai lần. Cần thiết kế atomicity, namespace theo principal/tenant, expiration, khóa nghiệp vụ và xử lý retry.

**Bài học:** 0-RTT là tối ưu hóa đòi hỏi thiết kế an toàn riêng; **1-RTT session resumption** đã có lợi ích hiệu năng mà không đòi client gửi dữ liệu nguy hiểm trước khi handshake hoàn thành.

## 7. Vòng đời của một TLS session/ticket

Một session không “mãi mãi hợp lệ” chỉ vì handshake từng thành công.

### 7.1. Các giai đoạn

```text
HANDSHAKE AUTHENTICATED
         |
         v
SESSION / RESUMPTION STATE CREATED
         |
         v
STORED / AVAILABLE
  client cache or ticket
  server cache or ticket keys
         |
         +---------> USED IN NEW HANDSHAKE IF POLICY ACCEPTS
         |                          |
         |                          +--> new connection, new traffic keys
         |                          +--> possibly new tickets
         |
         +---------> EXPIRES / INVALIDATED / EVICTED
         |                 |
         |                 +--> new connection needs full handshake
         |
         +---------> SERVER KEY/CONFIG ROTATION
                           |
                           +--> resumption may be declined
```

Các nguyên nhân session không được resume:
- Server không phát ticket, client chưa nhận ticket hoặc cache của client bị xóa.
- Ticket/session đã hết hạn theo thời gian protocol, chính sách server hoặc provider cache.
- Server restart mất in-memory state hoặc rotate ticket-protection keys.
- Server cluster chọn node không có cùng resumption state/keys.
- Client dùng `SSLContext` hoặc trust/identity configuration khác.
- SNI, ALPN, phiên bản TLS, cipher-suite hash hoặc chính sách authentication khác.
- Server từ chối resumption khi chính sách bảo mật thay đổi, certificate/key bị thu hồi hoặc có sự kiện an ninh.
- Session bị evicted khỏi cache vì giới hạn dung lượng.
- Resumption bị vô hiệu theo chính sách hoặc implementation.

**Không phải mọi nguyên nhân đều là bug.** Full handshake có thể là hành vi an toàn và mong muốn nếu trạng thái không còn phù hợp.

### 7.2. Timeout nào chi phối?

| Loại timeout/lifetime | Cái gì hết hạn? | Tác động |
| --- | --- | --- |
| TCP connect timeout | Chờ tạo transport connection | Socket connect fail, chưa có TLS handshake |
| TLS handshake timeout | Chờ hoàn tất handshake | Kết nối mới chưa sẵn sàng |
| Socket read timeout | Chờ đọc dữ liệu trên socket | Có thể fail I/O, tùy API không nhất thiết xóa session cache |
| HTTP request timeout | Một tác vụ HTTP | Request có thể bị hủy, không phải quy tắc TTL ticket TLS |
| HTTP idle connection timeout | Kết nối còn mở nhưng không dùng | Pool đóng socket; lần sau cần kết nối mới |
| TLS session cache timeout | Một cache entry có thể được dùng lại bao lâu | Có thể buộc full handshake lần sau |
| Ticket lifetime | Resumption ticket/PSK được offer/chấp nhận bao lâu | Hết ticket thì không resume theo ticket đó |
| Server ticket-key rotation | Khóa server giải/kiểm ticket đã phát | Ticket cũ có thể không còn được chấp nhận |
| App authentication/session expiry | User/token/cookie ứng dụng | User cần xác thực lại dù TLS session hợp lệ |

Không dùng một cấu hình `SSLSessionContext.setSessionTimeout(600)` rồi suy ra “mọi TCP socket sẽ tự đóng sau 600 giây”. Đó là **session-cache policy**, không phải connection idle timeout.

### 7.3. Hai phía có thể có giới hạn khác nhau

Client có thể còn lưu ticket nhưng server đã đổi ticket key; client có thể chủ động gửi PSK identity và bị server từ chối. Tương tự, server còn khả năng resume nhưng client đã evict ticket. Thành công cần **hai bên đồng thuận** trong handshake mới.

## 8. Java 17+ biểu diễn TLS session qua những API nào?

### 8.1. `SSLContext`

`SSLContext` chứa cấu hình TLS provider được khởi tạo với các KeyManagers, TrustManagers và nguồn ngẫu nhiên phù hợp. Từ một context có thể tạo socket/engine để thực hiện nhiều TLS connections.

`SSLContext` cũng expose:
- `getClientSessionContext()`: context quản lý các sessions phía client theo khả năng provider.
- `getServerSessionContext()`: context quản lý sessions phía server theo khả năng provider.

Không coi cùng một context là “phiên TLS duy nhất”; đây là **hạ tầng tạo connections và quản lý trạng thái**.

### 8.2. `SSLSessionContext`

Các API chính:

```java
SSLSessionContext sessions = sslContext.getClientSessionContext();

sessions.setSessionTimeout(600); // timeout in seconds
sessions.setSessionCacheSize(128); // cache entries limit

int seconds = sessions.getSessionTimeout();
int limit = sessions.getSessionCacheSize();
```

Ý nghĩa:
- `setSessionTimeout(int seconds)` điều chỉnh giới hạn thời gian session được giữ trong cache mà provider quản lý. **0** theo API nghĩa là không giới hạn thời gian bằng setting này; không có nghĩa tắt resumption.
- `setSessionCacheSize(int size)` điều chỉnh giới hạn số sessions trong cache. **0** nghĩa là không áp giới hạn kích thước bằng setting này; không có nghĩa cache trống hay bị vô hiệu.
- Giá trị âm không hợp lệ và thường dẫn tới `IllegalArgumentException` theo API.
- `getIds()` liệt kê IDs các sessions trong cache dưới khả năng của implementation; `getSession(byte[])` truy xuất theo ID khi có.
- Trong TLS 1.3, một server có thể gửi nhiều tickets và provider có nhiều trạng thái nội bộ; **không đảm bảo API `getIds()` hiển thị một ticket một-một**, hoặc một session ID có nghĩa giống TLS 1.2.
- Thời gian và kích thước cache chỉ là **một phần policy**. Server có quyền từ chối; ticket lifetime và TLS implementation có thêm ràng buộc.

**Chú ý:** không tùy tiện đặt cache size/timeouts = 0 với hy vọng “disable”; nếu mục tiêu là vô hiệu resumption vì chính sách, phải đọc đúng tài liệu provider, áp cấu hình có hỗ trợ và kiểm thử wire handshake.

### 8.3. `SSLSession`

`SSLSession` đại diện thông tin một established TLS session theo model JSSE, có các phương thức hữu ích:

| API | Có thể xem gì? | Giới hạn |
| --- | --- | --- |
| `getProtocol()` | Phiên bản như `TLSv1.3` | Không cho biết handshake vừa full hay resumed |
| `getCipherSuite()` | Suite negotiated | Không đồng nghĩa ticket được sử dụng |
| `getPeerPrincipal()` | Peer principal nếu được xác thực theo session | Có thể throw nếu không có peer authentication; không thay authorization |
| `getCreationTime()` | Thời điểm tạo session theo model/provider | Không phải thời điểm mỗi HTTP request |
| `getLastAccessedTime()` | Thời điểm được truy cập theo model/provider | Không phải network idle timer của socket |
| `getId()` | Session ID bytes theo JSSE | Không phải wire ticket ID đáng tin để chứng minh resumption |
| `getSessionContext()` | Cache context sở hữu session, có thể null | Không nói kết nối còn mở |
| `isValid()` | Trạng thái session có thể còn hợp lệ theo API | Không bảo đảm socket còn mở hoặc server sẽ accept ticket |
| `invalidate()` | Đánh dấu session không thể dùng tiếp cho resume/join theo API | Không tự đóng established TLS connection |
| `getPeerCertificates()` | Peer certificate chain nếu hiện diện | Không tự thay certificate validation/hostname hoặc authz |

Trong TLS 1.3, khái niệm session được mapping lên JSSE provider có thể khác về ticket/ID và thời điểm cập nhật. Đừng xây business state dựa trên `SSLSession.getId()`, `getCreationTime()` hoặc assumption rằng session object identity chứng minh resumed handshake.

### 8.4. `SSLSocket`, `SSLEngine` và HTTP client

- `SSLSocket`: TLS over socket truyền thống, có `startHandshake()`, `getSession()`, `close()`. Phải cấu hình đúng trust và endpoint identity.
- `SSLEngine`: TLS state machine không gắn trực tiếp I/O, được NIO/framework dùng. Application chịu trách nhiệm wrap/unwrap, handshake status, close inbound/outbound và buffer.
- `java.net.http.HttpClient`: quản lý kết nối, pooling, HTTP/2 và TLS dưới abstraction. `HttpResponse.sslSession()` có thể cung cấp thông tin phiên, **không** công khai đầy đủ quyết định reuse/resumption.
- `HttpsURLConnection`: còn có API lấy thông tin TLS; không mặc định so sánh hai response là hai handshake.

Không tự xây cơ chế “caching `SSLSocket` mãi mãi” để giữ security state. Một socket có thể đã đóng, mất mạng, hết idle timeout, hết certificate policy hoặc không còn phù hợp cho origin khác.

## 9. Java 17+: chương trình chạy offline để hiểu session cache

Ví dụ dưới đây chủ động **không kết nối mạng**; nó chỉ tạo một `SSLContext` mới, lấy session contexts của client và server, đặt timeout/cache sizes rồi kiểm tra các tham số nhận lại.

Điều này giúp phân biệt **quản lý khả năng cache session** với việc **thực sự tạo TLS handshake/session**. Demo không cố khẳng định resumption đã xảy ra khi chưa có remote server.

Tạo tệp `TlsSessionCacheDemo.java`:

```java
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSessionContext;

public class TlsSessionCacheDemo {
    static SSLContext createContext() throws GeneralSecurityException {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, new SecureRandom());
        return context;
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = createContext();

        SSLSessionContext client = context.getClientSessionContext();
        SSLSessionContext server = context.getServerSessionContext();

        client.setSessionTimeout(600);
        client.setSessionCacheSize(128);
        server.setSessionTimeout(300);
        server.setSessionCacheSize(64);

        System.out.println("Client session timeout (s): "
                + client.getSessionTimeout());
        System.out.println("Client session cache size: "
                + client.getSessionCacheSize());
        System.out.println("Server session timeout (s): "
                + server.getSessionTimeout());
        System.out.println("Server session cache size: "
                + server.getSessionCacheSize());

        boolean badTimeoutRejected = false;
        try {
            client.setSessionTimeout(-1);
        } catch (IllegalArgumentException expected) {
            badTimeoutRejected = true;
        }

        boolean badSizeRejected = false;
        try {
            client.setSessionCacheSize(-1);
        } catch (IllegalArgumentException expected) {
            badSizeRejected = true;
        }

        System.out.println("Negative timeout rejected: " + badTimeoutRejected);
        System.out.println("Negative cache size rejected: " + badSizeRejected);
        System.out.println("Client and server cache objects differ: "
                + (client != server));

        // This program creates no SSLSocket or SSLEngine handshake.
        System.out.println("TLS handshakes performed by demo: 0");
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac TlsSessionCacheDemo.java
java TlsSessionCacheDemo
```

Stdout đã kiểm tra trên JDK có `SunJSSE` tương thích Java 17:

```text
Client session timeout (s): 600
Client session cache size: 128
Server session timeout (s): 300
Server session cache size: 64
Negative timeout rejected: true
Negative cache size rejected: true
Client and server cache objects differ: true
TLS handshakes performed by demo: 0
```

### 9.1. Giải thích kết quả

- Các setters/getters xác nhận **cấu hình cache của context** chứ không chứng minh có session nào được tạo.
- Client và server session caches khác nhau vì có hai vai trò TLS độc lập.
- Tham số âm bị từ chối vì không có nghĩa hợp lệ cho thời gian/kích thước cache.
- Dòng cuối là tuyên bố về luồng code: chương trình không mở socket/engine handshake. **Không được viết unit test “session resumption worked” dựa trên chương trình này.**
- Một provider khác có thể có đặc điểm session-cache riêng; test trên phải được thực hiện trong môi trường thực tế nếu muốn dùng như kiểm tra tương thích. Chương trình không thiết lập chính sách certificate/hostname vì nó hoàn toàn không kết nối tới endpoint nào.

### 9.2. Điểm cần tránh khi cấu hình production

Việc đặt `setSessionTimeout(600)` không:
- Tạo TLS session ticket.
- Bảo đảm server đồng ý resume trong mười phút.
- Thiết lập HTTP keep-alive idle timeout.
- Đóng connection sau mười phút.
- Bật 0-RTT.
- Tái xác thực certificate hoặc app principal mỗi 600 giây.
- Bảo đảm server ticket key còn hiệu lực hay cache được share giữa các nodes.

Tương tự, `setSessionCacheSize(128)` là giới hạn cache theo implementation, không phải giới hạn 128 TCP connections, 128 concurrent users hay 128 HTTP requests.

## 10. Java 17+: quan sát TLS session trong HTTPS request thật

Ví dụ thứ hai dùng `HttpClient` cho một địa chỉ HTTPS có thật. Nó mở kết nối mạng và có thể cho thấy protocol/cipher suite; vì kết quả phụ thuộc mạng, server, proxy, provider và connection pool, **không có stdout cố định**.

Tệp `ObserveHttpsSession.java`:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Optional;
import javax.net.ssl.SSLSession;

public class ObserveHttpsSession {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        URI uri = URI.create("https://example.com/");
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        for (int i = 1; i <= 2; i++) {
            HttpResponse<Void> response = client.send(
                    request, HttpResponse.BodyHandlers.discarding()
            );
            Optional<SSLSession> maybeSession = response.sslSession();
            System.out.println("Request: " + i);
            System.out.println("HTTP status: " + response.statusCode());
            System.out.println("TLS protocol: " + maybeSession
                    .map(SSLSession::getProtocol).orElse("not exposed"));
            System.out.println("Cipher suite: " + maybeSession
                    .map(SSLSession::getCipherSuite).orElse("not exposed"));
        }
    }
}
```

Chạy:

```bash
javac ObserveHttpsSession.java
java ObserveHttpsSession
```

Điều quan sát được:
- Hai requests cùng dùng **một `HttpClient` instance**, tăng khả năng connection pooling nhưng không bảo đảm cả hai được gửi trên cùng socket.
- Kết quả `response.sslSession()` có thể hiển thị protocol/cipher suite. Nó **không có một boolean chuẩn “isResumedHandshake”**.
- Nếu pool reuse một kết nối đã mở, request thứ hai **không thực hiện TLS handshake mới** và không có sự kiện resumption để đo.
- Nếu server/route/proxy đóng kết nối giữa hai requests, client có thể tạo connection mới; handshake mới **có thể full hoặc resumed** tùy điều kiện.
- Một server có thể phản hồi HTTP/1.1 hay HTTP/2; phiên bản HTTP không thể được suy ra chỉ từ TLS cipher suite.
- Nếu TLS handshake thất bại hoặc không có mạng, ví dụ ném exception thay vì in stdout. Không tắt certificate verification để “chạy cho được”.

**Không log raw `SSLSession.getId()`, ticket, key material hay HTTP cookie.** Nếu cần debug, nên có logging đã đánh giá bảo mật và môi trường thử nghiệm được kiểm soát.

### 10.1. Muốn chứng minh handshake đã resumed thật thì làm thế nào?

Một phép thử đáng tin phải:
1. Điều khiển client và server test, cùng TLS provider/configuration và cùng peer identity.
2. Đầu tiên tạo **full authenticated handshake**; bảo đảm session ticket được phát và được client thực sự nhận/lưu.
3. Đóng **đúng transport/TLS connection**, nhưng giữ resumption cache/PSK state có chủ đích.
4. Mở một **new transport connection** với cùng endpoint, policy và context.
5. Thu thập bằng chứng từ **TLS handshake debug/protocol trace** rằng client offered PSK và server selected PSK/resumption (hoặc TLS 1.2 selected session ID/ticket).
6. Thử lại sau khi cache evicted, ticket expired hoặc ticket key rotated; xác nhận fallback full handshake.
7. Kiểm tra certificate validation và expected identity vẫn được thực thi theo protocol/resumption policy.
8. Kiểm tra không xảy ra 0-RTT khi application không chủ động hỗ trợ.

**Không đủ chứng cứ:**
- Handshake thứ hai “nhanh hơn”.
- `SSLSession.isValid()` là true.
- `getId()` giống hoặc khác.
- HTTP status 200.
- Response thứ hai dùng cùng `HttpClient`.
- `SSLSession.getCreationTime()` vẫn cũ.
- TCP connection bị reused nhưng không hề có new handshake.

Khi phân tích trace ở TLS 1.3, nhớ rằng nhiều handshake messages/traffic đã mã hóa; phải sử dụng diagnostic/provider tooling phù hợp và tránh xuất session secrets/keys ra ngoài.

## 11. Session cache và connection pool: hai bộ nhớ khác nhau

### 11.1. Connection pool giữ thứ gì?

Một HTTP connection pool có thể giữ **sockets đã bắt tay xong**, với:
- Remote endpoint/origin, proxy route, network interface.
- Giao thức HTTP/1.1 hoặc HTTP/2, trạng thái stream.
- TLS connection đang sống.
- Idle timeout, số kết nối tối đa, keep-alive policy.
- Các giới hạn concurrency, HTTP/2 GOAWAY, connection health.

Mục đích chính: tránh phải mở socket mới và thực hiện lại handshake nếu có kết nối đang dùng được.

### 11.2. TLS session cache giữ thứ gì?

Tùy protocol/provider, TLS session cache giữ resumption state, PSK/tickets/session IDs và metadata đủ để **rút gọn handshake cho một kết nối mới**. Không tự hiểu nó là một live socket.

### 11.3. Kết hợp hai loại cache

```text
HTTP request arrives
       |
       v
HTTP connection pool contains usable live connection?
       |
   +---+---+
   |       |
  YES      NO
   |       |
reuse      open new TCP connection
existing       |
TLS conn       v
   |       TLS library checks resumption state
   |           |
   |       +---+---+
   |       |       |
   |     ticket   no ticket / rejected
   |     valid       |
   |       |          |
   |     resumed    full handshake
   |     handshake
   |       |          |
   +-------+----------+
           |
           v
       Send HTTP request
```

Vì thế, tăng connection pool reuse có thể làm **ít handshake mới hơn**, khiến tỷ lệ resumption trong số tất cả requests có vẻ thấp dù hiệu năng tốt. Ngược lại, giảm idle timeout khiến nhiều sockets mới và resumption attempts hơn; không mặc định kết quả là bảo mật/hiệu năng tốt hơn.

### 11.4. HTTP/2, HTTP/3 và QUIC

- Với **HTTPS HTTP/2 over TLS/TCP**, nhiều streams cùng chia sẻ một TLS connection; không có TLS handshake riêng cho mỗi stream.
- Với **HTTP/3**, giao vận là QUIC và TLS 1.3 được tích hợp vào QUIC, không chạy như `SSLSocket` TLS-over-TCP thông thường. QUIC có khái niệm connection migration, connection IDs và resumption/0-RTT khác với keep-alive TCP; đọc RFC 9000/9001 và stack HTTP/3 tương ứng.
- Một thư viện Java 17 `java.net.http.HttpClient` chuẩn không nên được giả định có mọi cơ chế HTTP/3/QUIC tùy deployment. Không áp các công cụ quản lý TCP socket trực tiếp cho QUIC mà không kiểm tra implementation.

## 12. Kết thúc kết nối: close socket, close_notify và session cache

Đây là phần thường gây bug về vòng đời.

### 12.1. Bốn hành động khác nhau

| Hành động | Ảnh hưởng chính | Không nhất thiết làm gì? |
| --- | --- | --- |
| Đóng HTTP response body/stream | Giải phóng tài nguyên request, giúp connection pool xử lý tái dùng hoặc đóng | Không nhất thiết xóa TLS resumption state |
| Đóng `SSLSocket` / TLS connection | Ngừng sử dụng kết nối và giải phóng tài nguyên liên quan | Không nhất thiết invalidate mọi cached sessions/tickets |
| `SSLSession.invalidate()` | Đánh dấu session không thể tiếp tục tham gia/resume theo API | Không tự đóng kết nối đã established |
| Ticket expired / evicted | Không còn khả năng resume bằng ticket đó | Không tự kill socket cũ đang truyền dữ liệu |

Ứng dụng không nên “tắt SSL session” bằng cách chỉ gọi `close()` trên một HTTP response hay “đóng socket” bằng `SSLSession.invalidate()`.

### 12.2. TLS `close_notify`

TLS có thông điệp alert `close_notify` để báo một phía không gửi thêm dữ liệu qua kênh TLS theo ngữ nghĩa protocol. Với TCP, abrupt EOF hoặc connection reset khác với orderly TLS closure.

Tuy nhiên behavior cụ thể liên quan half-close, EOF, HTTP framing và API shutdown phụ thuộc giao thức và stack. Đừng làm một chương trình đọc dữ liệu nhạy cảm rồi **chấp nhận EOF bất ngờ như bằng chứng bản tin đã hoàn chỉnh** khi protocol chưa có length/framing/integrity đúng.

Với HTTPS client chuẩn, framework quản lý TLS connection shutdown và pool. Với `SSLEngine`, ứng dụng phải chú ý `closeOutbound()`, wrap dữ liệu đóng và xử lý `closeInbound()` theo API/provider; không chỉ gọi `ByteBuffer.clear()` hay bỏ qua handshake status.

### 12.3. Invalidation không thay key rotation hay revoke certificate

Nếu một TLS session bị invalidate ở client, một server đã phát ticket có thể vẫn giữ state hoặc ticket key; bạn cần kiểm soát policy **ở cả phía phù hợp**. Nếu có sự cố private key/certificate hoặc PSK/ticket key, hệ thống thường phải đánh giá phạm vi resumption, rotation server keys, cache, revoke credentials và thời gian chấp nhận tickets; gọi `invalidate()` trên một session Java cục bộ **không phải** global revocation.

Trong các kết nối đang mở, việc đánh giá có cần đóng ngay/áp chính sách lại là quyết định an ninh và triển khai riêng.

## 13. Authentication, chứng thư và vòng đời resumption

### 13.1. Resumption dựa trên xác thực trước đó

Một TLS 1.3 PSK resumption bình thường kế thừa sự ràng buộc an ninh từ handshake trước và ticket/state được phát hợp lệ. Nó có thể không lặp lại `Certificate` và `CertificateVerify` của server ở mọi resumed handshake.

Điều đó tạo yêu cầu vận hành:
- Không kéo dài trust vào một chứng thư đã bị thu hồi hoặc key bị lộ mà không có policy.
- Giới hạn tuổi ticket, số lần nối tiếp, và key lifetimes theo security policy.
- Bảo đảm SNI, ALPN, protocol, cipher hash và principal binding phù hợp.
- Nếu certificate hoặc mTLS client principal thay đổi, cần quyết định resumption state có còn được phép hay không.
- Nếu có refresh login/authorization policy, áp ở tầng ứng dụng; không dùng resumption để bỏ qua kiểm tra quyền.

RFC 9846 có hướng dẫn giới hạn tổng thời gian duy trì resumption state từ chứng thực trước, xét certificate lifetime, khả năng bị thu hồi và thời gian từ lần chứng thực online gần nhất.

### 13.2. Hostname verification không được bị bỏ qua

Khi client tạo TLS connection mới tới `payments.example.com`, việc dùng PSK/ticket từ phiên trước cần nằm trong phạm vi identity chính xác. Không sử dụng một ticket “trông hợp lệ” để kết nối tới arbitrary server chỉ vì server đó trình cùng một loại cipher suite.

Nếu application tắt hostname verification hoặc dùng trust-all, rủi ro MITM vẫn còn. TLS resumption **không sửa sai** trust manager hoặc certificate validation của initial handshake.

### 13.3. mTLS và vòng đời client certificate

Với mTLS, server có thể đã xác minh client certificate trong full handshake. Khi resume bằng một session/ticket liên quan tới client identity, server phải bảo đảm policy còn phù hợp; quyền người dùng/ứng dụng có thể đã bị thu hồi hoặc đổi tenant.

Một service không nên tự động cấp quyền admin chỉ vì resumed connection mang trạng thái xác thực cũ:
- Kiểm tra identity/principal mapping và thời hạn chính sách.
- Gắn certificate identity và key IDs với tenant/role từ nguồn tin cậy.
- Có cơ chế revoke/session invalidation phù hợp cluster và token/key lifecycle.
- Tránh đưa thông tin quyền ứng dụng dài hạn vào TLS ticket mà không có expiry/version/revalidation policy.

## 14. KeyUpdate không phải resumption

Trong TLS 1.3, `KeyUpdate` cho phép thay đổi application traffic keys trong **một TLS connection đang tồn tại** theo protocol. Nó không:
- Mở TCP connection mới.
- Tạo HTTP request mới.
- Mặc định tái xác thực certificate.
- Bắt buộc phát session ticket mới.
- Chứng minh một resumed handshake đã xảy ra.

Cần phân biệt:

```text
Same TLS connection:
    handshake -> traffic keys A -> KeyUpdate -> traffic keys B
                                (transport connection remains)

Resumption:
    connection #1 handshake -> ticket/state
              [connection #1 closes]
    connection #2 new handshake using PSK/ticket -> new traffic keys
```

Khi phân tích debug hoặc thiết kế key rotation, đừng lấy sự kiện key update làm thước đo session resumption rate.

## 15. Load balancer và hệ thống nhiều node

Một API gateway có nhiều backend nodes có thể có:
- TLS termination ở load balancer, backend chỉ nhận HTTP/gRPC nội bộ.
- TLS termination tại từng application instance.
- Một lớp proxy/mesh thực hiện mTLS giữa services.
- Các instance giữ caches/ticket keys khác nhau.

Khi client kết nối nhiều lần:
- Nếu TLS kết thúc ở gateway, **session resumption được quyết định ở gateway**, không phải `SSLContext` của service phía sau.
- Nếu terminate ở từng node với server-side session cache cục bộ, new connection tới node khác có thể full handshake vì không có state.
- Nếu server-issued tickets dùng key chia sẻ, nhiều nodes có thể resume dễ hơn; **việc chia sẻ ticket keys tăng blast radius** nếu một node bị lộ và đòi cơ chế rotation/phân phối an toàn.
- Nếu 0-RTT được bật ở nhiều zones, cần **anti-replay coordination**; không dùng cache cục bộ đơn giản như bằng chứng chống replay toàn cụm.
- Restart/rolling deployment có thể làm cache miss/rotated ticket keys, dẫn tới tăng full handshake. Đây có thể là hành vi đúng.

Thiết kế phải cân bằng hiệu năng, khả năng mở rộng và bí mật:
- Chỉ chia sẻ ticket keys/trust material trong phạm vi được chính sách cho phép.
- Rotation có overlap hạn chế, giới hạn ticket lifetime và audit.
- Giữ cache gần nơi TLS terminate; tránh truyền TLS secret vào application logs.
- Benchmark tỉ lệ full/resumed handshake **tại đúng tầng kết thúc TLS**, không ở service không nhìn thấy handshake.

## 16. Đo lường và debug mà không tiết lộ TLS secrets

### 16.1. Những chỉ số thực sự hữu ích

- Số lượng **new TCP connections** và **TLS handshakes** trong một khoảng thời gian.
- Số **full handshakes** và **resumed handshakes** được server/provider xác nhận.
- Ticket issue rate, offer/accept/reject rate, expiration, cache hit/miss/eviction.
- TLS handshake latency theo phiên bản/cipher/route, nhưng không suy kết quả resumption chỉ từ latency.
- HTTP connection pool reuse, idle close, HTTP/2 stream concurrency.
- Handshake failures theo nhóm: certificate validation, SNI/ALPN mismatch, expired ticket, key rotation, network failures.
- 0-RTT offered/accepted/rejected, replay attempts và business idempotency outcomes nếu tính năng bật.

**Không gom tất cả thành “TLS sessions” mà không ghi rõ đơn vị.** Sessions khác connections, handshakes và requests.

### 16.2. Java TLS debug

Trong môi trường thử nghiệm, JSSE có cơ chế debug cho SSL/TLS, ví dụ option thường thấy:

```bash
java -Djavax.net.debug=ssl,handshake,session ObserveHttpsSession
```

Đây là công cụ diagnostic, **không phải cấu hình mặc định production**. Debug log có thể chứa metadata nhạy cảm như hostname, certificate subject, phiên bản, session IDs/ticket details tùy provider và mức log. Không công bố raw traces khi chưa review; tránh bất kỳ key logging/secret extraction nào không cần thiết.

Các thông tin cần nhận diện trong trace/protocol:
- Khi new connection được tạo, có `ClientHello`/`ServerHello` mới không?
- Có offered `pre_shared_key` identity/PSK binder trong TLS 1.3 không?
- Server có selected PSK/resumption không, hay fallback certificate-based full handshake?
- Có `NewSessionTicket` sau full handshake được client tiếp nhận không?
- HTTP request thứ hai thực ra có dùng lại socket đầu tiên không?

**Chỉ nhìn `CipherSuite` hoặc `SSLSession.getId()` không đủ kết luận.**

### 16.3. Đừng log ticket/raw PSK và token

Dữ liệu nhạy cảm:
- Raw ticket bytes, resumption PSK, traffic secrets.
- Credential/cookie/token tầng HTTP.
- Key material của certificate client hoặc ticket-protection key server.
- Debug traces đủ chi tiết để làm lộ mối liên hệ sessions/users/hosts.
- Application request body chứa dữ liệu cá nhân.

Dùng metrics aggregate và trace IDs không nhạy cảm. Khi có incident, áp quyền, retention và redaction cho artifacts như với dữ liệu bảo mật.

## 17. Các lỗi phổ biến và cách sửa

| Ngộ nhận / lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “Hai GET liên tiếp trên cùng HttpClient là hai lần session resumption” | Pool có thể reuse cùng live connection | Phân biệt socket reuse và new handshake |
| “Không cần mở socket mới vì có session ticket” | Ticket giúp rút gọn handshake **sau khi** tạo connection mới | Kết nối mới vẫn cần transport và key establishment |
| “`SSLSession.isValid()` nghĩa là TCP socket còn mở” | Session state khác socket state | Theo dõi socket/HTTP pool riêng |
| “`SSLSession.invalidate()` đóng mọi TLS connection ngay” | Invalidation cấm resume/join trong tương lai theo API, không đồng nghĩa close | Đóng socket/engine theo lifecycle riêng |
| “`setSessionTimeout(600)` nghĩa là đóng idle TCP sau 600s” | Là cache time policy | Cấu hình HTTP/TCP idle riêng |
| “`setSessionCacheSize(0)` là tắt cache” | 0 biểu thị không giới hạn cache size theo API | Dùng provider policy đúng nếu muốn disable |
| “Resumption lúc nào cũng gồm 0-RTT” | 0-RTT là feature riêng, tùy chọn | 1-RTT PSK resumption có thể không có early data |
| “0-RTT đã có TLS nên transfer-money an toàn” | Early data có thể replay; weaker secrecy | Cấm unsafe operations, anti-replay/idempotency theo profile |
| “Dùng PSK resumption thì mọi thứ có PFS” | PSK-only khác PSK-DHE; 0-RTT không có FS | Chọn mode/policy rõ, bảo vệ ticket/PSK |
| “Client đã có ticket nên server bắt buộc resume” | Server có thể reject do policy/rotation/expiry | Chấp nhận fallback full handshake |
| “Ticket lifetime = HTTP login lifetime” | Hai lớp xác thực khác nhau | AuthN/AuthZ application có TTL riêng |
| “Server restart không ảnh hưởng resumption” | In-memory state/key rotation có thể mất | Thiết kế ticket/cache/cluster phù hợp |
| “TLS ticket có thể dùng cho bất kỳ hostname” | Identity binding/SNI/security policy quan trọng | Verify expected endpoint, scope ticket |
| “0-RTT GET nào cũng an toàn” | Có thể có side effect, token state hoặc retry nguy hiểm | Chỉ khi application profile chứng minh replay-safe |
| “Full handshake là lỗi nếu đã bật cache” | Cache miss/expiry là hành vi bình thường | Monitor rate và nguyên nhân, không downgrade |
| “KeyUpdate mở phiên TLS mới” | KeyUpdate xảy ra trong connection hiện tại | Phân biệt key rotation và resumption |
| “TLS resumption thay certificate validation” | Tin cậy phải có nền tảng từ full handshake và policy | Không tắt trust/hostname verification |
| “mTLS resumed = user còn được quyền admin” | App roles và certificates có thể đã bị revoke | Revalidate authorization/policy |
| “Chỉ cần so session ID để chứng minh resumed” | TLS 1.3 abstraction/ticket và pooling phức tạp | Dùng wire/JSSE handshake evidence đúng |
| “TLS over QUIC cũng là SSLSocket” | QUIC tích hợp TLS khác TCP/TLS | Dùng provider/API HTTP/3 và chuẩn QUIC phù hợp |

## 18. Tình huống thực hành

### Tình huống A: HTTP/2 tải 40 resources

Client mở một TLS connection tới `cdn.example.com` rồi tải 40 resources qua HTTP/2 streams. Nhóm vận hành nói đã có 40 TLS resumptions vì có 40 requests.

**Phân tích:** Không. Có thể chỉ có **một TLS handshake** và một connection, với 40 HTTP/2 streams. Connection reuse/multiplexing khác resumption. Đo ở network/TLS layer, không lấy request count.

### Tình huống B: HTTP/1.1 keep-alive hết hạn

Request #1 hoàn thành; pool đóng socket sau idle timeout. Request #2 mở TCP connection mới, client còn ticket TLS 1.3 và server chấp nhận PSK.

**Phân tích:** Có **new transport connection + resumed TLS handshake**. Request #2 không reuse socket cũ. Nếu ticket bị từ chối, vẫn có thể full handshake và xử lý HTTP bình thường.

### Tình huống C: Server vừa rotate certificate

Client còn resumption ticket gắn với handshake trước, nhưng server vừa rotate certificate hoặc thay đổi trust/policy.

**Phân tích:** Không mặc định resume tất cả tickets cũ. Phải xem ticket lifetime, chính sách binding, revocation/rotation và key resumption. Full handshake mới có thể được yêu cầu. Không giữ quyền an ninh cũ vô thời hạn chỉ để nhanh.

### Tình huống D: Giao dịch chuyển tiền trong 0-RTT

Client dùng early data gửi `POST /transfer`; kẻ tấn công ghi lại early-data flight và thử replay ở một region khác.

**Phân tích:** 0-RTT có replay risk ngay khi traffic được mã hóa. Không đưa lệnh có side effect như chuyển tiền vào early data nếu không có profile chống replay được chứng minh; biện pháp mặc định là không cho phép 0-RTT với thao tác này.

### Tình huống E: Client sửa `SSLSession.invalidate()` rồi kỳ vọng socket đóng

Ứng dụng gọi `invalidate()` nhưng tiếp tục thấy dữ liệu truyền trên `SSLSocket` cũ.

**Phân tích:** Không mâu thuẫn. Invalidation liên quan khả năng reuse/resumption state, còn established TLS connection vẫn có vòng đời riêng. Đóng socket/engine theo đúng API nếu muốn kết thúc truyền.

### Tình huống F: Server restart làm resumption giảm mạnh

Sau deploy, tỷ lệ resumed handshake từ 80% xuống 10%, full handshake tăng, nhưng HTTP vẫn hoạt động.

**Phân tích:** Có thể server mất in-memory session state hoặc rotate ticket keys, load balancer đổi route, client tickets hết hạn. Không tự suy đó là sự cố certificate hay bị tấn công; xác minh qua ticket/PSK accept diagnostics và cấu hình cluster.

### Tình huống G: Một Java service sau reverse proxy

Client ngoài kết nối HTTPS tới API gateway; gateway kết nối HTTP nội bộ tới Java backend. Java backend kiểm tra `SSLSessionContext` của mình và không thấy TLS sessions từ client.

**Phân tích:** TLS đã terminate ở gateway, backend không sở hữu sessions của client. Kiểm tra handshake ở gateway; identity propagation phải an toàn và không tin header client tự khai.

### Tình huống H: TLS 1.3 resumption nhưng không có 0-RTT

Client nhận ticket, lần sau dùng PSK và server chấp nhận; application data chỉ gửi sau bước Finished theo mode 1-RTT.

**Phân tích:** Đây vẫn là **session resumption hợp lệ**, không có early data. Phân biệt performance optimization thông thường với tính năng 0-RTT vốn yêu cầu replay-safe application semantics.

### Tình huống I: Application session expired

TLS connection vẫn sống và `SSLSession.isValid()` trả true, nhưng access token của user đã hết hạn.

**Phân tích:** Server phải từ chối hoặc yêu cầu auth lại theo chính sách. TLS state không gia hạn bearer token hoặc user privileges.

### Tình huống J: Java HTTP client đã tạo hai connections song song

Hai requests đến cùng origin nhưng pool chọn hai sockets khác nhau do concurrency/HTTP version. Handshake thứ hai có thể full dù cache còn ticket.

**Phân tích:** Số socket và khả năng resumption phụ thuộc timing nhận ticket, trust, policy và provider. Không suy từ số `HttpClient` instances; chạy tests có instrument TLS handshakes và connection reuse.

## 19. Checklist thiết kế và vận hành

### Application client

- [ ] Xác định rõ có cần connection pooling, TLS resumption hay cả hai; metric cho từng thứ.
- [ ] Sử dụng `HttpClient`/HTTP framework được hỗ trợ với trust manager và endpoint identity validation chuẩn.
- [ ] Không thay `SSLSession` cho HTTP auth session hoặc principal.
- [ ] Hạn chế số connections và idle timeouts theo tài nguyên/latency/threat model.
- [ ] Nếu custom `SSLContext`, quản lý client session cache, trust material và shutdown theo policy.
- [ ] Không tự gửi 0-RTT cho operation có side effect; kiểm tra profile/SDK hỗ trợ có chủ đích.
- [ ] Không giả định session ID/cache state chứng minh resumption hoặc peer identity.

### TLS termination server / gateway

- [ ] Chọn TLS versions, cipher suites, key-exchange modes và certificate policy cập nhật theo RFC 9846.
- [ ] Quản lý session/ticket lifetimes, resumption cache, server ticket-key rotation và secrets an toàn.
- [ ] Có chiến lược xử lý node restart, load balancing, key sharing và fallback full handshake.
- [ ] Giới hạn ticket lifetime và resumption chain theo policy, xét thay đổi certificate/CA/client identity.
- [ ] Nếu bật 0-RTT, cần anti-replay ở cluster, chỉ chấp nhận traffic replay-safe và có ứng dụng đồng thuận.
- [ ] Bảo vệ logs, traces, metric dimensions và key material; không ghi raw PSK/tickets.
- [ ] Kiểm tra session invalidation/revocation có scope thực tế, không tuyên bố một lệnh Java giải quyết toàn cluster.

### Vòng đời kết nối và tài nguyên

- [ ] Đóng `SSLSocket` hoặc `SSLEngine` theo contract khi không cần, xử lý lỗi/network EOF đúng.
- [ ] HTTP response bodies được đọc/đóng đúng để giải phóng connection pool resources.
- [ ] Không lấy timeout session cache làm socket read/HTTP request/idle timeout.
- [ ] Theo dõi pool saturation, keep-alive, idle close, HTTP/2 streams và remote GOAWAY.
- [ ] Duy trì authorization của ứng dụng độc lập với TLS resumption state.
- [ ] Có load tests, restart tests, ticket-key rotation tests, browser/mobile/network-change tests.

### Security regression

- [ ] Full handshake tới certificate hợp lệ và expected hostname thành công; sai trust/hostname fail.
- [ ] Resumed handshake thực sự được xác nhận bằng provider/wire evidence.
- [ ] Hết ticket/cache hoặc đổi trust/policy -> full handshake hoặc reject theo expected behavior.
- [ ] Raw ticket/key không xuất hiện trong logs/heap-dump artifacts không được bảo vệ.
- [ ] PSK-only/PSK-DHE policy được kiểm tra, không tái sử dụng ephemeral KeyShare.
- [ ] Không tự kích hoạt 0-RTT trên unsafe requests.
- [ ] Multi-instance anti-replay giữ đúng consistency nếu 0-RTT dùng.
- [ ] App auth expired vẫn bị từ chối dù TLS session hợp lệ.

## 20. Câu hỏi tự kiểm tra

**1. Hai HTTP requests qua cùng một TCP/TLS socket có phải session resumption không?**  
**Không.** Đó là connection reuse/HTTP pooling. TLS resumption cần một **handshake trên kết nối mới** sử dụng state từ trước.

**2. Một TCP socket bị đóng có xóa TLS session ticket không?**  
**Không nhất thiết.** TLS provider có thể tiếp tục giữ session/ticket để resume trên socket mới cho đến expiry/eviction/policy.

**3. `SSLSession.isValid() == true` có cho biết `SSLSocket` đang mở?**  
**Không.** Đây là trạng thái session, không phải trạng thái transport socket.

**4. `SSLSession.invalidate()` có đóng socket đang chạy ngay không?**  
**Không.** API invalidation nhằm ngăn phiên tham gia/resume trong tương lai; established connection có thể tiếp tục tới khi đóng.

**5. TLS 1.3 dùng gì để resume?**  
**PSK**, thường được gắn với `NewSessionTicket` từ handshake trước; client offer PSK identity + binder, server có thể accept/reject.

**6. Resumption 1-RTT có nhất thiết dùng 0-RTT không?**  
**Không.** 0-RTT là early-data mode riêng, phải được cho phép và phù hợp profile ứng dụng.

**7. Vì sao không gửi lệnh chuyển tiền bằng 0-RTT theo mặc định?**  
Vì early data có thể bị replay giữa các kết nối; mã hóa TLS không ngăn được hành động lặp.

**8. Có thể kết luận ticket được server accept chỉ từ độ trễ handshake thấp không?**  
**Không.** Cần TLS handshake trace hoặc metrics/provider evidence thể hiện PSK/resumption được chọn.

**9. Đặt `setSessionTimeout(600)` có buộc socket đóng sau mười phút?**  
**Không.** Đây là session cache setting, không phải HTTP keep-alive/connection idle timeout.

**10. Đặt `setSessionCacheSize(0)` có disable cache?**  
**Không.** Theo contract của API, 0 nghĩa là không giới hạn kích thước theo setting này; muốn tắt resumption cần policy/provider configuration khác.

**11. Nếu server có ticket key mới nhưng không nhận ticket cũ, client có phải lỗi kết nối không?**  
Không nhất thiết. Nếu policy cho phép, server/client có thể fallback sang full handshake an toàn.

**12. TLS resumption có tự gia hạn application login token không?**  
**Không.** HTTP cookie, JWT, OAuth token hoặc session ứng dụng có vòng đời riêng.

**13. Resumption và KeyUpdate khác nhau ở đâu?**  
Resumption tạo **new handshake trên new connection** dùng trạng thái cũ; KeyUpdate thay application traffic keys **trong connection hiện tại**.

**14. Một service Java sau TLS-terminating reverse proxy có nhìn thấy TLS sessions của browser không?**  
Thông thường **không**. Chúng thuộc gateway/proxy; backend nhìn thấy protocol kết nối của chính nó.

**15. TLS 1.3 resumption có bảo đảm forward secrecy mọi trường hợp không?**  
**Không**: PSK-only, PSK-DHE và 0-RTT có bảo đảm khác nhau; xét ticket/PSK compromise và kết quả DHE.

**16. RFC TLS 1.3 được dùng làm chuẩn chính vào tháng 10/2026 là gì?**  
**RFC 9846**, xuất bản tháng 7/2026, thay thế RFC 8446 nhưng giữ TLS version 1.3 và tương thích về cơ bản.

## 21. Sơ đồ ghi nhớ cuối bài

```text
                APPLICATION HTTP REQUEST
                         |
               live HTTP connection?
                    /          \
                  YES           NO
                   |             |
               reuse socket    new transport connection
                   |             |
               same TLS        TLS handshake begins
               connection         |
                   |         Resumption PSK/ticket available?
                   |               /         \
                   |              YES         NO
                   |               |           |
                   |          Server accepts? full handshake
                   |            /       \
                   |           YES       NO
                   |            |         |
                   |          resumed   full handshake
                   |            |
                   |      1-RTT normally
                   |      0-RTT only if explicitly enabled/replay-safe
                   |            |
                   +------------+----------+
                                |
                         HTTP application data
                                |
                         Close live connection
                                |
                        Ticket may survive
                                |
                         Later new connection

  Important:
    TLS session != TCP socket
    TLS session != login session
    Connection reuse != TLS resumption
    Resumption != 0-RTT
    Session invalidation != socket.close()
```

**Kết luận:** Hãy tách rõ ba vòng đời: **application request**, **transport/TLS connection đang sống**, và **session/resumption state có thể sống qua nhiều connections**. Connection pooling và HTTP/2 tiết kiệm handshake bằng cách **không mở lại kết nối**; TLS session resumption tiết kiệm handshake bằng cách **tái sử dụng trạng thái được xác thực trên một kết nối mới**. TLS 1.3 theo RFC 9846 dùng PSK/tickets cho resumption; 0-RTT là một lựa chọn có rủi ro replay, không phải mặc định của resumption. Trong Java, `SSLSessionContext` giúp cấu hình cache nhưng không chứng minh handshake đã resume, còn `SSLSession.invalidate()` không đóng socket. Một hệ thống production cần policy về lifetime, hostname/authentication, cache/ticket keys, 0-RTT, authorization, logging và đóng kết nối đúng tầng.

### Tài liệu tham khảo

- RFC 9846 (2026) — *The Transport Layer Security (TLS) Protocol Version 1.3*, thay thế RFC 8446: https://www.rfc-editor.org/rfc/rfc9846
- RFC 8446 (2018) — TLS 1.3 bản gốc, nay đã được RFC 9846 thay thế: https://www.rfc-editor.org/rfc/rfc8446
- RFC 9000 — *QUIC: A UDP-Based Multiplexed and Secure Transport*: https://www.rfc-editor.org/rfc/rfc9000
- RFC 9001 — *Using TLS to Secure QUIC*, resumption và early data: https://www.rfc-editor.org/rfc/rfc9001
- Java SE 17, `SSLContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html
- Java SE 17, `SSLSessionContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSessionContext.html
- Java SE 17, `SSLSession`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html
- Java SE 17, `SSLSocket`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSocket.html
- Java SE 17, `SSLEngine`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html
- Java SE 17, `HttpClient`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Java SE 17, `HttpResponse.sslSession()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- Oracle JSSE Reference Guide — provider, session caching and diagnostic configuration: https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html
