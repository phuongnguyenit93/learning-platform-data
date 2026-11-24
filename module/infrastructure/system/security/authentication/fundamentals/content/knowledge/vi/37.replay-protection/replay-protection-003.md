# Timestamp

## 1. Timestamp trong replay protection là gì?

**Timestamp** là giá trị biểu diễn thời điểm một request, assertion hoặc thông điệp được tạo. Trong cơ chế chống replay, bên gửi đưa timestamp vào dữ liệu được ký hoặc xác thực bằng MAC; bên nhận kiểm tra timestamp có nằm trong khoảng thời gian chấp nhận hay không. Một request quá cũ hoặc có thời gian bất hợp lý sẽ bị từ chối.

Replay attack xảy ra khi attacker ghi lại một thông điệp hợp lệ rồi gửi lại để lặp lại hành động hoặc tái sử dụng bằng chứng xác thực. Ví dụ, attacker ghi lại một request chuyển tiền đã được ký, một HTTP request có HMAC, một assertion đăng nhập hoặc một mã xác thực có thể dùng lại. Timestamp giúp giới hạn thời gian một thông điệp còn hợp lệ, nhưng **timestamp đơn lẻ không ngăn được replay trong cửa sổ thời gian cho phép**. Muốn chống việc gửi lặp trong cửa sổ đó, hệ thống thường cần nonce, request ID, replay cache hoặc cơ chế tiêu thụ một lần.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, timestamp là một thành phần của trust boundary giữa client, authenticator, authorization server và resource server. Nó giúp xác định freshness của bằng chứng, nhưng không thay thế chữ ký/MAC, TLS, authorization hay kiểm soát trạng thái giao dịch. Người học cần hiểu timestamp được tin từ đâu, được ràng buộc với nội dung nào, server kiểm tra ra sao và hệ thống xử lý request trùng như thế nào.

Sau bài học, người học có thể:

- Giải thích timestamp giúp giới hạn replay window như thế nào.
- Phân biệt timestamp, nonce, request ID và idempotency key.
- Thiết kế freshness window và clock-skew tolerance.
- Ràng buộc timestamp với request bằng HMAC hoặc chữ ký số.
- Chọn định dạng thời gian, đơn vị và cách chuẩn hóa thống nhất.
- Đồng bộ clock giữa client, server và các node phân tán.
- Thiết kế replay cache và thao tác consume-once nguyên tử.
- Xử lý retry, concurrency, clock drift và sự cố time service.
- Kiểm thử replay cũ, replay trong window, timestamp tương lai và request bị sửa.

## 2. Timestamp hạn chế replay như thế nào?

Một thông điệp hợp lệ tại thời điểm tạo không nên được chấp nhận vô thời hạn. Bên nhận kiểm tra tuổi thông điệp so với thời gian hiện tại của server. Nếu thông điệp cũ hơn giới hạn, server từ chối.

Mô hình đơn giản:

~~~text
message_age = server_now - signed_timestamp

accept_freshness =
    -allowed_future_skew <= message_age <= max_message_age
~~~

Trong đó:
- **server_now** là thời gian do server lấy từ nguồn thời gian được quản lý.
- **signed_timestamp** là timestamp được bảo vệ bằng chữ ký hoặc MAC.
- **max_message_age** là tuổi tối đa cho phép.
- **allowed_future_skew** là khoảng dung sai nhỏ cho sai lệch clock ở phía client.

Có thể viết tương đương:

~~~text
server_now - max_age <= signed_timestamp
signed_timestamp <= server_now + future_skew
~~~

Điều kiện này chỉ kiểm tra freshness. Server vẫn phải xác minh chữ ký/MAC, identity của key, audience, quyền, nonce và trạng thái nghiệp vụ.

### 2.1. Timestamp ngăn replay cũ

Giả sử một request được ký lúc 10:00 và policy cho phép tuổi tối đa 5 phút. Nếu attacker phát lại request lúc 11:00, server thấy timestamp đã cũ và từ chối. Điều này giới hạn thời gian sử dụng lại thông điệp bị đánh cắp.

### 2.2. Replay trong cửa sổ vẫn có thể xảy ra

Nếu attacker ghi lại request lúc 10:01 và phát lại lúc 10:02, cả request gốc lẫn bản replay đều nằm trong cửa sổ 5 phút. Chữ ký/MAC vẫn hợp lệ vì nội dung không thay đổi. Timestamp không tự biết request đã được xử lý trước đó.

Vì vậy, với thao tác cần chống replay, cần kết hợp timestamp với:
- Nonce ngẫu nhiên, duy nhất cho từng request.
- Request ID hoặc jti dùng một lần.
- Replay cache lưu dấu request đã chấp nhận.
- Challenge-response có trạng thái server.
- Idempotency record cho thao tác nghiệp vụ có side effect.

### 2.3. Timestamp không thay thế TLS

TLS bảo vệ dữ liệu trên đường truyền và xác thực endpoint theo cấu hình. Timestamp/MAC/signature bảo vệ freshness và tính toàn vẹn ở lớp thông điệp. Một request có timestamp mới nhưng truyền qua kênh không an toàn vẫn có thể bị quan sát, sửa đổi hoặc đánh cắp key/token theo các cách khác.

Dùng TLS và kiểm soát thông điệp ở tầng ứng dụng khi threat model yêu cầu. Không xem timestamp là biện pháp thay thế mã hóa kênh.

## 3. Timestamp phải được bảo vệ bằng chữ ký hoặc MAC

Nếu timestamp chỉ nằm trong header hoặc body không được bảo vệ, attacker có thể thay timestamp cũ thành thời điểm hiện tại để vượt freshness check. Server phải xác minh timestamp thuộc chính thông điệp đã được ký.

Với HMAC, client và server chia sẻ secret. Client tính MAC trên tập dữ liệu canonical bao gồm timestamp; server tự tính lại và so sánh bằng phép so sánh constant-time phù hợp.

~~~text
canonical_request =
    method
    + "\n" + authority
    + "\n" + path_and_query
    + "\n" + content_digest
    + "\n" + timestamp
    + "\n" + nonce

signature = HMAC(secret_key, canonical_request)
~~~

Đây là mô hình minh họa, không phải chuẩn canonicalization áp dụng cho mọi HTTP API. Trong triển khai thực tế, ưu tiên giao thức và thư viện đã được review, ví dụ HTTP Message Signatures (RFC 9421), thay vì tự thiết kế quy tắc ký tùy tiện.

### 3.1. Những gì cần ràng buộc với timestamp?

Tùy giao thức, chữ ký/MAC nên ràng buộc các thành phần cần thiết để request không thể được chuyển sang ngữ cảnh khác:

- HTTP method hoặc loại operation.
- Authority/host hoặc audience.
- Path và query theo quy tắc canonicalization.
- Timestamp.
- Nonce hoặc request identifier.
- Content-Type khi nó ảnh hưởng cách diễn giải.
- Digest/hash của body nếu body có ý nghĩa bảo mật.
- Key identifier hoặc credential context theo profile.

Nếu chỉ ký timestamp mà không ký method, resource và body, attacker có thể thay nội dung hoặc chuyển bằng chứng sang endpoint khác nếu giao thức cho phép. Phạm vi chữ ký phải phản ánh chính xác request cần được bảo vệ.

### 3.2. Canonicalization phải nhất quán

Client và server phải tạo cùng một representation trước khi tính MAC/chữ ký. Khác biệt về percent-encoding, header trùng, thứ tự query parameter, Unicode, khoảng trắng hoặc cách chuẩn hóa URI có thể gây lỗi xác minh hoặc tạo ambiguity.

Không tự lowercase mọi header/value, decode URL nhiều lần hoặc sắp xếp query theo một quy tắc không được thỏa thuận. Chọn một canonicalization profile cụ thể, dùng implementation đã kiểm chứng và có test vectors.

### 3.3. Chọn key đúng principal

Timestamp hợp lệ và MAC hợp lệ vẫn chưa đủ nếu key thuộc client khác. Server cần ánh xạ key ID tới client/principal, tenant, audience và quyền đã đăng ký. Không lấy key ID hoặc JWKS URL tùy ý từ request rồi tin ngay.

Key rotation, revoke và secret storage phải được quản lý độc lập với timestamp. Khi key bị compromise, freshness window ngắn không thay thế việc thu hồi key và xử lý incident.

## 4. Chọn freshness window

Freshness window là khoảng thời gian server chấp nhận timestamp. Window càng rộng thì request chịu được mạng trễ và clock drift tốt hơn, nhưng thông điệp bị đánh cắp cũng có thời gian replay lâu hơn. Window quá hẹp có thể từ chối người dùng hợp lệ khi mạng chậm hoặc clock chưa đồng bộ.

| Bối cảnh | Cân nhắc |
| --- | --- |
| Service-to-service trong cùng hạ tầng | Có thể dùng window ngắn nếu clock được quản lý tốt |
| Mobile client qua mạng di động | Cần tính tới sleep, reconnect và sai lệch clock; không tin clock thiết bị vô điều kiện |
| API giao dịch nhạy cảm | Window ngắn, nonce và transaction state; có thể cần xác nhận bổ sung |
| Webhook giữa hai hệ thống | Timestamp ký, event ID và deduplication theo thời gian lưu |
| Assertion đăng nhập | Dùng quy tắc freshness, expiry và one-time semantics của giao thức |
| Hệ thống phân tán nhiều region | Cần đo clock skew, propagation và độ trễ replay cache |

Không có một giá trị window đúng cho mọi hệ thống. Chọn dựa trên latency thực tế, độ lệch clock đo được, hậu quả của replay và khả năng duy trì nonce/replay cache.

### 4.1. Freshness window hai phía

Một số giao thức cho phép dung sai timestamp trong tương lai. Có thể xác định hai giới hạn riêng:

- **max_age:** thông điệp không được cũ hơn khoảng này.
- **future_skew:** timestamp không được nằm quá xa trong tương lai.

Không nên dùng một tolerance quá lớn để che lỗi đồng bộ clock. Nếu client gửi timestamp tương lai vượt ngưỡng, từ chối và ghi reason code; không tự chấp nhận vì có thể đồng hồ bị sai.

### 4.2. Window không phải TTL của session

Timestamp request freshness thường chỉ áp dụng cho một request hoặc assertion. Nó không phải thời hạn session đăng nhập, access token hay refresh token. Session có thể tồn tại lâu hơn nhưng mỗi request nhạy cảm có thể cần bằng chứng mới; ngược lại, timestamp của một request cũ không được tái sử dụng chỉ vì session còn sống.

## 5. Đồng bộ thời gian và clock skew

Timestamp-based protection phụ thuộc vào việc client và server có khái niệm thời gian đủ gần nhau. **Clock skew** là độ lệch giữa các đồng hồ. Nếu server nhanh hơn client hoặc client nhanh hơn server, request hợp lệ có thể bị coi là quá cũ hoặc nằm trong tương lai.

### 5.1. Nguồn thời gian đáng tin

- Đồng bộ server với nguồn thời gian được quản lý, thường qua NTP; môi trường yêu cầu độ chính xác cao có thể dùng PTP.
- Giám sát offset, drift, synchronization state và alert khi vượt ngưỡng.
- Cấu hình nhiều time source đáng tin cậy và quy trình khi nguồn chính lỗi.
- Đồng bộ clock trên container, VM, host và các region.
- Không lấy giờ từ request, browser hoặc header do caller tự khai làm server time.
- Dùng UTC cho trao đổi và lưu trữ timestamp.
- Ghi nhận độ chính xác và nguồn thời gian nếu audit yêu cầu.

NTP/PTP giúp đồng bộ đồng hồ nhưng không tự bảo đảm mọi máy luôn đúng. Time source bị cấu hình sai hoặc bị tấn công có thể ảnh hưởng nhiều service; cần bảo vệ cấu hình, giám sát và quy trình incident.

### 5.2. Wall clock và monotonic clock

Wall clock biểu diễn thời gian lịch (ví dụ UTC epoch) và có thể được điều chỉnh khi đồng bộ. Nó phù hợp để so sánh timestamp giữa các máy.

Monotonic clock chỉ tăng trong phạm vi một máy/boot context và phù hợp đo khoảng thời gian hoặc timeout nội bộ. Không so sánh monotonic timestamp giữa hai máy khác nhau hoặc lưu nó như timestamp toàn cục.

Một implementation có thể dùng wall clock để kiểm tra timestamp do client gửi, và monotonic clock để đo thời gian xử lý nội bộ. Không dùng monotonic clock thay cho Unix timestamp trong giao thức.

### 5.3. Clock step và clock rollback

Nếu clock bị lùi đột ngột, server có thể chấp nhận lại timestamp hoặc tạo TTL sai. Nếu clock nhảy tiến, nhiều request có thể bị coi là hết hạn. Hệ thống cần:
- Theo dõi bước nhảy thời gian và offset.
- Tránh dùng thời gian local không đồng bộ làm căn cứ duy nhất.
- Phát hiện timestamp trong tương lai bất thường.
- Duy trì replay cache đủ lâu ngay cả khi clock thay đổi trong phạm vi policy.
- Có hành vi an toàn khi time synchronization không đáng tin.

Không sửa request timestamp bằng cách cộng trừ một offset không được quản lý. Nếu cần dung sai, cấu hình nó rõ ràng và đo được.

## 6. Định dạng, đơn vị và parsing timestamp

Một lỗi phổ biến là client gửi millisecond nhưng server hiểu second, hoặc một service dùng local timezone trong khi service khác giả định UTC.

### 6.1. Unix epoch và NumericDate

Timestamp số thường dùng số giây hoặc mili giây kể từ Unix epoch. Cần định nghĩa đơn vị trong protocol.

Ví dụ:
- **1795323000** có thể là Unix time theo giây.
- **1795323000000** có thể là Unix time theo mili giây.

Không tự suy đoán đơn vị chỉ dựa trên độ dài nếu protocol chưa quy định. Một parser linh hoạt quá mức có thể tạo ambiguity hoặc bypass validation.

OIDC/JWT NumericDate được biểu diễn theo giây kể từ epoch theo đặc tả. Không nhầm với JavaScript Date, nơi Date.now() trả mili giây.

### 6.2. ISO 8601 / RFC 3339

Timestamp dạng text nên có timezone rõ, thường là UTC với hậu tố Z, ví dụ:

~~~text
2026-11-22T06:15:00Z
~~~

Tránh chuỗi thời gian không có timezone như 2026-11-22 13:15:00, vì các service có thể hiểu theo timezone local khác nhau. Nếu dùng fractional seconds, định nghĩa số chữ số và cách rounding/truncation.

### 6.3. Parsing nghiêm ngặt

Server nên:
- Chấp nhận đúng format đã định nghĩa.
- Từ chối giá trị thiếu, rỗng, overflow hoặc không parse được.
- Kiểm tra đơn vị và phạm vi hợp lý.
- Từ chối timestamp quá xa trong tương lai hoặc quá cũ.
- Không âm thầm thay giá trị lỗi bằng thời gian hiện tại.
- Tránh integer overflow và mất độ chính xác khi chuyển kiểu.
- Dùng cùng quy tắc trên mọi node và phiên bản service.

Không để một service parse timestamp theo giây còn service khác theo mili giây. Contract cần được version hóa và test tương thích.

## 7. Kết hợp timestamp với nonce và replay cache

Để ngăn replay trong freshness window, server cần biết request đã được xử lý chưa. Một cách phổ biến là mỗi request có nonce duy nhất được bảo vệ bằng chữ ký/MAC. Server kiểm tra nonce chưa xuất hiện, rồi ghi nhận nonce atomically trước khi thực hiện side effect.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    participant R as Replay Store
    C->>C: Tạo timestamp và nonce ngẫu nhiên
    C->>C: Ký request + timestamp + nonce
    C->>S: Request, timestamp, nonce, signature
    S->>S: Kiểm tra format và freshness
    S->>S: Xác minh key và signature
    S->>R: Consume nonce nếu chưa tồn tại
    R-->>S: Thành công hoặc đã dùng
    alt Nonce mới
        S->>S: Kiểm tra authorization và xử lý request
        S-->>C: Response
    else Nonce đã dùng
        S-->>C: Từ chối replay
    end
~~~

### 7.1. Tạo nonce

Nonce cần:
- Được sinh từ CSPRNG.
- Có độ dài/entropy đủ cao theo threat model.
- Duy nhất trong phạm vi principal/key và cửa sổ sử dụng.
- Được đưa vào dữ liệu ký/MAC.
- Không lấy từ timestamp hoặc counter không có bảo đảm uniqueness.
- Không tái sử dụng khi retry nếu protocol yêu cầu mỗi request mới có nonce mới.

Nonce không cần là bí mật sau khi gửi, nhưng cần khó đoán trước và không bị attacker thay đổi mà không làm chữ ký/MAC thất bại.

### 7.2. Replay cache

Replay cache lưu dấu nonce hoặc request identifier đã được chấp nhận. Key cache có thể gồm issuer/client/key ID và nonce để tránh va chạm giữa các principal. Việc kiểm tra và insert phải nguyên tử: chỉ một request được phép consume nonce.

Nếu cache là distributed, mọi node có thể nhận request giống nhau. Dùng kho chia sẻ hoặc primitive atomic có consistency phù hợp. Local in-memory cache trên từng node không đủ nếu attacker có thể gửi bản replay tới node khác.

### 7.3. Thời gian lưu nonce

Nonce cần được giữ ít nhất tới khi request không còn được chấp nhận theo freshness window. Nếu timestamp T được chấp nhận tới T + max_age, cache entry không được hết hạn trước mốc đó cộng thêm margin cho clock skew/propagation.

Có thể ước lượng TTL còn lại:

~~~text
replay_entry_expiry = signed_timestamp + max_age + safety_margin
cache_ttl = max(0, replay_entry_expiry - server_now)
~~~

Cần giới hạn kích thước cache và rate request để tránh attacker tạo lượng nonce khổng lồ làm cạn bộ nhớ. Nếu cache không thể ghi nhận nonce cho thao tác rủi ro cao, nên từ chối hoặc chuyển sang cơ chế an toàn đã định nghĩa; không âm thầm bỏ replay check.

## 8. Timestamp và idempotency key

Nonce/replay ID và idempotency key có mục đích liên quan nhưng khác nhau.

| Cơ chế | Mục đích | Vòng đời |
| --- | --- | --- |
| **Timestamp** | Giới hạn độ mới của thông điệp | Cửa sổ freshness ngắn |
| **Nonce** | Phân biệt một lần gửi cụ thể và chống phát lại | Một lần dùng, giữ trong replay window |
| **Request ID / jti** | Định danh duy nhất thông điệp hoặc token | Theo thời hạn và replay policy |
| **Idempotency key** | Đảm bảo retry nghiệp vụ không tạo side effect lặp | Có thể lưu lâu hơn request freshness |
| **Transaction ID** | Theo dõi một nghiệp vụ qua nhiều bước | Tới khi giao dịch kết thúc và hết retention cần thiết |

Ví dụ, client gửi yêu cầu tạo thanh toán nhưng bị timeout và không biết server đã xử lý chưa. Client retry với cùng idempotency key để nhận kết quả cũ mà không tạo thanh toán thứ hai. Mỗi HTTP attempt vẫn có thể dùng timestamp và nonce mới để chống replay ở tầng request.

Không dùng idempotency key thay nonce nếu attacker có thể phát lại request ngoài ngữ cảnh retry hợp lệ. Ngược lại, nonce mới cho mỗi retry không tự bảo đảm nghiệp vụ chỉ chạy một lần; cần idempotency record ở tầng nghiệp vụ.

### 8.1. Atomic consume và side effect

Nếu server đánh dấu nonce đã dùng sau khi chuyển tiền, hai request đồng thời có thể cùng vượt qua kiểm tra rồi cùng thực hiện side effect. Consume nonce phải xảy ra trước side effect theo một transaction hoặc workflow bảo đảm nhất quán.

Với nghiệp vụ có database transaction, có thể lưu replay record và business operation trong cùng transaction khi kiến trúc cho phép. Với external side effect, dùng idempotency key, outbox hoặc saga/compensation theo thiết kế; không giả định một database commit có thể nguyên tử với API bên ngoài.

## 9. Timestamp trong các giao thức xác thực

Timestamp xuất hiện trong nhiều giao thức nhưng semantics khác nhau. Không áp dụng một quy tắc chung mà bỏ qua đặc tả giao thức.

| Giao thức / thành phần | Timestamp liên quan | Kiểm soát bổ sung |
| --- | --- | --- |
| **JWT / OIDC** | iat, exp, nbf, đôi khi auth_time | Verify signature, issuer, audience, token purpose và jti/session policy |
| **SAML** | IssueInstant, NotBefore, NotOnOrAfter | Signature, issuer, recipient, audience, InResponseTo và assertion replay cache |
| **HTTP signed request** | Timestamp hoặc created/expires trong signature parameters | Ký timestamp, method/target/body digest và nonce theo profile |
| **TOTP** | Time step dùng tạo mã | Secret protection, time-step window nhỏ và one-time/replay tracking |
| **HMAC API request** | Timestamp trong canonical request | HMAC verify, key/client binding và nonce/replay cache |
| **Challenge-response** | Thời hạn challenge hoặc thời điểm tạo | Challenge random, session binding và consume-once |

### 9.1. JWT: iat, exp và nbf

- **iat** biểu thị thời điểm token được phát hành.
- **exp** biểu thị thời điểm token hết hạn.
- **nbf** biểu thị thời điểm token bắt đầu có hiệu lực.
- **auth_time** trong OIDC ID Token biểu thị thời điểm người dùng được xác thực theo OP.

Một token có iat mới không chứng minh người dùng vừa xác thực; nó có thể được cấp bằng refresh token. Khi chống replay token, cần xem xét token ID/jti, audience, token type, expiry, sender constraint hoặc trạng thái session theo profile.

### 9.2. SAML assertion

SAML assertion có thể dùng IssueInstant và điều kiện NotBefore/NotOnOrAfter để giới hạn thời gian chấp nhận. SP vẫn cần xác minh chữ ký, issuer, audience, recipient, destination và InResponseTo theo flow.

Một assertion hợp lệ về chữ ký có thể bị phát lại trong thời gian còn hiệu lực nếu SP không lưu assertion ID hoặc không có replay cache. Timestamp/expiry giới hạn thời gian, còn assertion ID và trạng thái consume-once giúp ngăn dùng lại.

### 9.3. TOTP

TOTP tạo mã dựa trên secret và time step. Server thường cho phép một cửa sổ nhỏ để dung sai clock drift, nhưng mã hợp lệ trong time step có thể bị gửi lại nếu server không theo dõi việc sử dụng theo policy.

Với thao tác nhạy cảm, có thể ghi nhận time step/counter đã chấp nhận hoặc transaction binding để không dùng lại cùng mã cho nhiều giao dịch. Cần bảo vệ secret và tránh mở rộng cửa sổ thời gian quá mức.

## 10. Request timestamp trong API HMAC

Một API dùng HMAC có thể yêu cầu mỗi request mang timestamp và nonce. Server thực hiện theo thứ tự khái niệm:

1. Parse timestamp theo format cố định.
2. Kiểm tra timestamp nằm trong freshness window.
3. Xác định key ID và client identity từ registry đáng tin.
4. Tạo canonical request theo profile.
5. Tính và xác minh HMAC bằng constant-time comparison.
6. Kiểm tra nonce chưa được consume.
7. Kiểm tra audience, scope và quyền.
8. Xử lý nghiệp vụ với idempotency nếu cần.
9. Ghi audit an toàn.

Thứ tự thực tế có thể điều chỉnh để tránh lộ thông tin hoặc lãng phí CPU, nhưng không thực hiện side effect trước khi các kiểm tra bắt buộc đạt.

Ví dụ request minh họa:

~~~http
POST /v1/transfers HTTP/1.1
Host: api.example.test
X-Client-Key-Id: client-42
X-Request-Timestamp: 1795323000
X-Request-Nonce: 7Qz4...random...
X-Request-Signature: base64url-hmac-value
Content-Type: application/json

{"destination":"account-73","amount":250000}
~~~

Timestamp, nonce và chữ ký phải được ràng buộc với body digest, method, authority và target URI theo canonicalization đã thống nhất. Ví dụ trên không phải giao thức tiêu chuẩn hoàn chỉnh; không sao chép trực tiếp vào production nếu chưa định nghĩa key management, encoding, canonicalization, replay store và error handling.

### 10.1. Vì sao timestamp phải nằm trong MAC?

Nếu timestamp nằm ngoài dữ liệu ký, attacker có thể giữ nguyên body và MAC nhưng thay timestamp thành giá trị mới. Khi timestamp nằm trong canonical request, thay đổi timestamp làm MAC không khớp.

Tương tự, nonce cũng phải được ký. Nếu attacker có thể thay nonce mà MAC vẫn hợp lệ, replay cache không nhận ra request trùng.

### 10.2. Kiểm tra body và URI

Nếu body không được ký hoặc digest không được ràng buộc, attacker có thể giữ timestamp/MAC nhưng đổi amount, destination hoặc operation. Nếu path/authority không được ký, một signature có thể bị chuyển tới endpoint khác.

Canonicalization cần định nghĩa chính xác byte representation. Tránh parse JSON rồi serialize lại theo cách khác nhau giữa client/server nếu chữ ký được tính trên raw bytes; hoặc nếu ký semantic representation thì phải dùng một chuẩn canonical JSON đã thống nhất.

## 11. Distributed systems và multi-region

Trong hệ thống nhiều node, request có thể đến bất kỳ instance nào; replay cache và clock phải được chia sẻ hoặc đồng bộ đủ tốt.

Các vấn đề thường gặp:
- Node A và B có clock offset khác nhau.
- Replay request được gửi tới hai region.
- Cache replication trễ khiến cả hai region cùng thấy nonce chưa tồn tại.
- Cache eviction sớm làm nonce bị chấp nhận lại.
- Time service lỗi khiến node tạo timestamp tương lai.
- Retry queue gửi lại event sau khi request ban đầu đã thành công.

### 11.1. Shared replay store

Dùng shared store có primitive atomic insert-if-absent hoặc unique constraint theo replay key. Nếu multi-region, xác định consistency model: eventual consistency có thể cho phép cùng nonce được consume ở hai region trong khoảng replication lag.

Với thao tác có hậu quả cao, cần global uniqueness hoặc partition/routing bảo đảm cùng replay key luôn đi qua một authority. Nếu không thể bảo đảm, bổ sung transaction/idempotency guard ở tầng nghiệp vụ.

### 11.2. Cache eviction và outage

Replay cache cần capacity planning, TTL và monitoring. Evict entry trước khi freshness window kết thúc có thể mở lại khả năng replay. Khi cache đầy hoặc không sẵn sàng, không bỏ qua replay check cho request nhạy cảm.

Có thể:
- Từ chối tạm thời các request cần replay protection.
- Chuyển sang durable store có uniqueness.
- Dùng partitioning theo client/tenant.
- Giới hạn request tạo nonce.
- Cảnh báo sớm khi memory/latency tăng.

Không giữ replay cache không giới hạn; attacker có thể gửi nhiều request hợp lệ về chữ ký với nonce khác nhau để gây resource exhaustion.

### 11.3. Clock skew giữa region

Đo offset giữa các node và đặt skew tolerance dựa trên dữ liệu thực tế. Nếu region lệch quá ngưỡng, có thể tạm ngừng nhận request ký thời gian từ region đó hoặc dùng một verification authority có clock được kiểm soát.

Không tăng freshness window toàn hệ thống mỗi khi một node lỗi. Sửa time synchronization và cô lập node sai clock.

## 12. Timestamp và webhook/event delivery

Webhook thường được gửi lại khi receiver timeout hoặc sender không nhận acknowledgement. Timestamp giúp receiver từ chối event quá cũ, nhưng retry hợp lệ có thể dùng cùng event ID hoặc chữ ký.

Một receiver nên:
- Xác minh chữ ký của sender.
- Kiểm tra timestamp nằm trong delivery window được thỏa thuận.
- Kiểm tra event ID đã xử lý chưa.
- Ghi event ID vào durable deduplication store trước side effect.
- Xử lý retry idempotent.
- Giữ deduplication record theo retention phù hợp với thời gian sender có thể retry.
- Kiểm tra event type, tenant và resource scope.

Nếu sender retry cùng event sau khi receiver timeout, receiver có thể trả lại acknowledgement/kết quả đã lưu mà không lặp side effect. Không từ chối mọi retry chỉ vì event ID đã xuất hiện; cần phân biệt replay trái phép với delivery retry hợp lệ qua idempotent processing.

## 13. Rủi ro và lỗi triển khai thường gặp

| Lỗi / mối đe dọa | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Timestamp không được ký | Attacker thay timestamp cũ thành mới | Ký/MAC timestamp cùng request |
| Chỉ dùng timestamp, không nonce | Replay trong window vẫn thành công | Nonce/request ID và replay cache |
| Freshness window quá rộng | Thông điệp bị đánh cắp có thời gian replay dài | Window dựa trên latency/skew và risk |
| Window quá hẹp | Request hợp lệ bị từ chối | Đo clock offset và latency thực tế |
| Sai đơn vị giây/millisecond | Token/request bị chấp nhận sai hoặc luôn hết hạn | Contract đơn vị, parser nghiêm ngặt |
| Timestamp không có timezone | Các service diễn giải khác nhau | UTC và format chuẩn |
| Clock rollback | Timestamp cũ có thể được coi là mới | Time monitoring, replay state và safe handling |
| Timestamp client tự khai không ràng buộc | Client giả mạo freshness | Verify signature/MAC và key binding |
| Chỉ ký timestamp, không ký body/path | Request bị sửa hoặc chuyển endpoint | Canonical request đầy đủ |
| Replay cache local từng node | Replay gửi tới node khác vẫn qua | Shared atomic store hoặc routing authority |
| Cache TTL quá ngắn | Nonce hết hạn trước request window | Retain tới timestamp + max_age + margin |
| Cache outage fail-open | Replay không được phát hiện | Fail closed hoặc durable fallback |
| Consume nonce sau side effect | Concurrent replay có thể lặp giao dịch | Atomic consume trước side effect |
| Idempotency key dùng sai | Retry/replay gây side effect lặp | Tách replay defense khỏi business idempotency |
| JWT chỉ kiểm tra exp | Token bị dùng lặp trong thời hạn | jti/session/revocation/sender constraint theo profile |
| TOTP window quá rộng | Mã cũ được chấp nhận lâu | Cửa sổ nhỏ, clock sync và replay tracking |
| Log timestamp/request secret đầy đủ | Rò rỉ dữ liệu hoặc credential | Redaction và audit tối thiểu |

## 14. Quan sát và vận hành

Timestamp-based replay protection cần telemetry để biết request bị từ chối vì lý do gì và hệ thống có đang lệch thời gian hay không.

Chỉ số gợi ý:
- Tỷ lệ timestamp quá cũ.
- Tỷ lệ timestamp nằm trong tương lai.
- Clock offset theo node/region.
- Tỷ lệ chữ ký/MAC không hợp lệ.
- Số nonce/request ID bị trùng.
- Tỷ lệ replay cache hit và insert conflict.
- Replay cache latency, size, eviction và availability.
- Số request bị từ chối do cache outage.
- Tỷ lệ retry hợp lệ của client/webhook.
- Tỷ lệ false rejection do window quá hẹp.

Log cần chứa reason code, client/key reference, request correlation ID và timestamp đã chuẩn hóa khi phù hợp. Không log HMAC secret, private key, raw bearer token hoặc toàn bộ body nhạy cảm. Hạn chế quyền truy cập telemetry vì nó có thể tiết lộ mẫu hoạt động và danh tính client.

### 14.1. Alert và incident response

Nếu phát hiện replay:
1. Xác định client/key, request ID và resource bị ảnh hưởng.
2. Kiểm tra cùng request có được chấp nhận ở nhiều node/region không.
3. Kiểm tra clock offset và replay cache health.
4. Xác định có side effect trùng lặp hay không.
5. Thu hồi key/token nếu có dấu hiệu compromise.
6. Hủy hoặc đảo giao dịch theo business recovery policy nếu có thể.
7. Giữ audit cần thiết và thông báo owner.
8. Điều chỉnh window, cache hoặc canonicalization sau khi xác minh nguyên nhân.

Không chỉ tăng freshness window để giảm lỗi timestamp; điều đó có thể mở rộng cửa sổ replay. Tìm nguyên nhân từ time service, latency, parsing và contract trước.

## 15. Ví dụ thiết kế cho API chuyển tiền

Một API chuyển tiền cần chống việc attacker phát lại request đã ký. Mỗi request gồm timestamp, nonce, chữ ký HMAC và idempotency key.

Quy trình:
1. Client tạo request ID, nonce ngẫu nhiên và timestamp UTC theo đơn vị đã thỏa thuận.
2. Client tạo body và tính digest.
3. Client tạo canonical representation gồm method, authority, path, body digest, timestamp, nonce và key context.
4. Client ký bằng HMAC secret.
5. Server xác định client/key từ registry và xác minh MAC.
6. Server kiểm tra timestamp nằm trong window.
7. Server consume nonce atomically trong replay store.
8. Server kiểm tra idempotency key và transaction state.
9. Server kiểm tra principal, account, limit, authorization và fraud policy.
10. Server thực hiện chuyển tiền trong transaction nghiệp vụ.
11. Server lưu kết quả theo idempotency key và trả response.
12. Nếu client timeout rồi retry, request mới có timestamp/nonce mới nhưng dùng cùng idempotency key; server trả kết quả nghiệp vụ đã lưu thay vì chuyển tiền lần hai.

~~~mermaid
flowchart TD
    A[Client tạo timestamp + nonce + idempotency key] --> B[Ký canonical request]
    B --> C[Server xác minh client key và MAC]
    C --> D{Timestamp trong freshness window?}
    D -- Không --> X[Từ chối request cũ/tương lai]
    D -- Có --> E[Atomic consume nonce]
    E --> F{Nonce đã dùng?}
    F -- Có --> Y[Từ chối replay]
    F -- Không --> G[Kiểm tra idempotency và transaction]
    G --> H[Authorization + fraud policy]
    H --> I{Được phép?}
    I -- Không --> Z[Từ chối]
    I -- Có --> J[Thực hiện side effect một lần]
    J --> K[Lưu kết quả và trả response]
~~~

Trong ví dụ này, timestamp giới hạn thời gian request còn được chấp nhận; nonce chặn cùng request bị gửi lại; idempotency key giúp retry nghiệp vụ không chuyển tiền hai lần. Ba cơ chế có nhiệm vụ riêng.

## 16. Kiểm thử timestamp-based replay protection

| Test case | Kết quả mong đợi |
| --- | --- |
| Timestamp hợp lệ và chữ ký đúng | Tiếp tục kiểm tra nonce, authorization và policy |
| Timestamp quá cũ | Từ chối trước side effect |
| Timestamp tương lai vượt skew | Từ chối và ghi reason code |
| Timestamp bị sửa nhưng MAC cũ | Xác minh MAC thất bại |
| Body/path bị sửa | Chữ ký/MAC thất bại |
| Cùng timestamp và nonce gửi lại | Replay bị phát hiện |
| Cùng request gửi tới hai node | Chỉ một node consume nonce |
| Nonce khác nhưng cùng idempotency key | Không lặp side effect nghiệp vụ |
| Nonce bị thay nhưng không ký | Test phải chứng minh request bị từ chối |
| Timestamp giây bị gửi như mili giây | Parser từ chối theo contract |
| Timestamp thiếu timezone | Từ chối nếu format yêu cầu timezone |
| Timestamp overflow hoặc malformed | Từ chối an toàn |
| Clock lệch trong tolerance | Xử lý theo policy |
| Clock lệch vượt tolerance | Từ chối hoặc cô lập node |
| Replay cache hết kết nối | Không fail-open cho thao tác nhạy cảm |
| Replay cache entry bị evict sớm | Test phát hiện nguy cơ replay; TTL phải được sửa |
| Hai request đồng thời cùng nonce | Atomic consume chỉ cho một request |
| Webhook retry cùng event ID | Deduplication không lặp side effect |
| JWT iat mới nhưng auth_time cũ | Không suy ra user vừa xác thực |
| SAML assertion ID bị phát lại | Assertion replay cache từ chối |
| TOTP code dùng lại trong cùng policy window | Không cho dùng lại nếu policy yêu cầu one-time |
| Time service rollback | Không mở lại nonce hoặc freshness đã tiêu thụ |
| Audit/log inspection | Không có secret, private key hoặc token thô |

### 16.1. Kiểm thử hiệu năng và khả năng chịu lỗi

Đo độ trễ của signature verification, replay cache và atomic insert dưới tải bình thường cũng như burst. Kiểm tra cache capacity, TTL cleanup, multi-region replication và behavior khi một node bị partition.

Không chỉ test request đơn lẻ. Replay protection cần được kiểm tra với request đồng thời, retry, failover và clock drift để phát hiện race condition.

## 17. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Timestamp có nằm trong dữ liệu ký? | Sửa timestamp làm signature/MAC thất bại |
| Request scope có được ký? | Method, target, body digest và audience được ràng buộc |
| Freshness window có lý do? | Dựa trên latency, clock skew và risk |
| Future skew có giới hạn? | Timestamp tương lai bất thường bị từ chối |
| Format/đơn vị có cố định? | UTC, epoch unit hoặc RFC 3339 được quy định |
| Parsing có nghiêm ngặt? | Không đoán đơn vị hoặc âm thầm sửa giá trị |
| Server time có đáng tin? | NTP/PTP, monitoring và alert |
| Wall/monotonic clock dùng đúng? | Cross-node timestamp dùng wall clock; timeout nội bộ dùng monotonic |
| Có nonce hoặc request ID? | Mỗi request có định danh duy nhất được ký |
| Replay cache có atomic? | Concurrent request không cùng consume |
| Cache retention đủ lâu? | Không hết hạn trước khi request hết freshness |
| Distributed nodes có chia sẻ state? | Replay không thể né bằng đổi node/region |
| Cache outage có policy? | Request nhạy cảm không fail-open |
| Idempotency có tách riêng? | Retry nghiệp vụ không tạo side effect lặp |
| Side effect có xảy ra sau consume? | Replay guard trước khi xử lý nghiệp vụ |
| JWT/SAML/TOTP tuân thủ semantics? | Không áp dụng timestamp generic thay đặc tả |
| Logging an toàn? | Không log key, token hoặc body nhạy cảm |
| Có test clock/replay/concurrency? | Có negative test và multi-node test |

### Tình huống tự kiểm tra

**Tình huống 1:** Một request có HMAC hợp lệ và timestamp mới được gửi hai lần trong vòng 10 giây. Timestamp có chặn lần thứ hai không?

**Trả lời:** Không. Cả hai request đều nằm trong freshness window. Cần nonce/request ID và replay cache để phát hiện lần gửi lặp.

**Tình huống 2:** Client gửi timestamp hiện tại nhưng timestamp không nằm trong dữ liệu HMAC. Attacker có thể làm gì?

**Trả lời:** Attacker có thể thay timestamp cũ thành mới mà không làm MAC thất bại. Timestamp phải được ký cùng nội dung request.

**Tình huống 3:** Server A và B có replay cache riêng. Attacker gửi request gốc tới A và bản replay tới B. Rủi ro là gì?

**Trả lời:** Cả hai có thể chấp nhận vì mỗi node chưa thấy nonce. Cần shared atomic replay store hoặc một authority/routing strategy bảo đảm uniqueness.

**Tình huống 4:** Webhook sender retry event vì không nhận acknowledgement. Receiver có nên xử lý side effect lần nữa không?

**Trả lời:** Không. Timestamp kiểm tra freshness, event ID/deduplication và idempotent processing ngăn side effect lặp.

**Tình huống 5:** Một API chuyển tiền dùng nonce mới mỗi lần retry. Có đủ để tránh chuyển tiền hai lần không?

**Trả lời:** Không. Nonce mới làm request attempt khác nhau; idempotency key ở tầng nghiệp vụ cần giữ nguyên để nhận kết quả cũ thay vì thực hiện giao dịch lần hai.

**Tình huống 6:** Client gửi Unix milliseconds nhưng server mong NumericDate giây. Có nên tự chia cho 1000 khi giá trị lớn không?

**Trả lời:** Không nên đoán. Protocol phải quy định đơn vị; parser nghiêm ngặt và từ chối giá trị sai format để tránh ambiguity.

## 18. Ghi nhớ

**Timestamp giới hạn khoảng thời gian một thông điệp có thể được chấp nhận, nhưng không tự ngăn replay trong freshness window.** Timestamp phải được bảo vệ bằng chữ ký hoặc MAC cùng method, resource và nội dung cần bảo vệ. Server cần dùng thời gian đáng tin, định dạng/đơn vị thống nhất và freshness window phù hợp với clock skew cùng latency.

Để chống gửi lặp, kết hợp nonce hoặc request ID với replay cache có thao tác consume-once nguyên tử và thời gian lưu đủ dài. Tách nonce khỏi idempotency key: nonce ngăn phát lại request, còn idempotency key ngăn retry tạo side effect nghiệp vụ lặp. Trong hệ thống phân tán, cần shared state, clock monitoring, failover policy và kiểm thử concurrency. Timestamp chỉ là một lớp trong thiết kế chống replay; chữ ký/MAC, TLS, authorization, token semantics và quản lý session vẫn phải được thực hiện độc lập.
