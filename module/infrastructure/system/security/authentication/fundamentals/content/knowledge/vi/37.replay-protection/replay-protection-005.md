# Challenge freshness — Bảo đảm challenge thuộc đúng giao dịch hiện tại

Một API quản trị yêu cầu client ký request bằng khóa riêng. Server xác minh chữ ký hợp lệ và chấp nhận lệnh đổi recovery email. Vài phút sau, attacker phát lại nguyên request đã bắt được. Chữ ký vẫn hợp lệ vì nội dung chưa thay đổi; nếu server không kiểm tra request còn mới và chưa được sử dụng, cùng một lệnh có thể được thực hiện lần nữa. Đây là replay attack: attacker không cần phá mật mã, chỉ cần phát lại một thông điệp hợp lệ trong ngữ cảnh mà server vẫn chấp nhận.

**Challenge freshness** là thuộc tính bảo đảm bằng chứng xác thực hoặc request được tạo để đáp ứng một thử thách mới, còn hiệu lực và gắn với đúng giao dịch hiện tại. Một challenge thường chứa nonce ngẫu nhiên do server phát hành; client hoặc authenticator đưa challenge vào dữ liệu được ký hoặc xác thực. Server xác minh phản hồi, kiểm tra challenge có đúng transaction, audience, purpose và thời hạn, rồi chỉ chấp nhận nó một lần.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài học này giúp người học phân biệt freshness với authenticity và integrity, hiểu nonce, timestamp, counter và sequence number, thiết kế replay cache có thao tác nguyên tử, xử lý clock skew và concurrency, và áp dụng nguyên tắc này cho WebAuthn, OIDC, TOTP, HMAC request signing và API nhạy cảm. Mục tiêu là ngăn một bằng chứng từng hợp lệ được tái sử dụng để đăng nhập, đổi credential hoặc thực hiện hành động ngoài ý định ban đầu.

## 1. Freshness giải quyết vấn đề gì?

Một chữ ký số hoặc MAC hợp lệ chứng minh thông điệp được tạo bởi bên nắm khóa tương ứng và nội dung không bị sửa theo cơ chế đã chọn. Nó không tự chứng minh thông điệp vừa được tạo, chưa từng được gửi hoặc còn phù hợp với giao dịch hiện tại.

Ví dụ:

1. Người dùng xác nhận thêm một passkey mới.
2. Server phát challenge và browser gửi assertion có chữ ký hợp lệ.
3. Server chấp nhận assertion nhưng không đánh dấu challenge đã dùng.
4. Attacker phát lại assertion đã ghi nhận.
5. Nếu server chấp nhận lại, cùng một bằng chứng có thể hoàn tất một thao tác khác hoặc một lần xác thực khác.

Challenge freshness ngăn tình huống này bằng cách buộc phản hồi gắn với một giá trị mới và có trạng thái server-side. Giá trị đó phải được kiểm tra ở đúng endpoint, đúng subject và đúng mục đích.

### 1.1. Phân biệt các thuộc tính

| Thuộc tính | Câu hỏi | Cơ chế thường dùng |
| --- | --- | --- |
| **Authenticity** | Ai tạo thông điệp hoặc ai đang chứng minh quyền kiểm soát khóa? | Chữ ký số, MAC, authenticator |
| **Integrity** | Nội dung có bị sửa sau khi ký/MAC không? | Digital signature, HMAC, AEAD |
| **Freshness** | Bằng chứng có thuộc giao dịch hiện tại và còn trong thời hạn không? | Challenge, nonce, timestamp, counter |
| **Anti-replay** | Bằng chứng đã được dùng trước đó chưa? | One-time consume, replay cache, sequence tracking |
| **Idempotency** | Retry cùng một thao tác có tạo thêm hiệu ứng ngoài ý muốn không? | Idempotency key và kết quả thao tác được lưu |
| **Authentication age** | Người dùng đã xác thực gần đây chưa? | Auth time, max-age, reauthentication policy |

Các thuộc tính bổ sung cho nhau. HMAC đúng không thay thế nonce; timestamp hợp lệ không thay thế replay cache; idempotency key không chứng minh người gửi đã xác thực; session còn sống không chứng minh người dùng vừa thực hiện step-up.

## 2. Threat model của replay

Attacker có thể ghi lại một thông điệp hợp lệ từ browser, proxy, mobile app, API client, webhook hoặc một giao thức nội bộ. Sau đó họ gửi lại thông điệp đó:

- Trong cùng cửa sổ thời gian mà server vẫn chấp nhận.
- Sau khi người dùng đã logout hoặc credential đã bị thu hồi.
- Tới một account, tenant, endpoint hoặc audience khác nếu request không được ràng buộc ngữ cảnh.
- Đồng thời từ nhiều kết nối để khai thác race condition.
- Từ một region hoặc server instance khác chưa chia sẻ trạng thái đã dùng.
- Sau khi clock bị lệch, cache bị flush hoặc hệ thống failover.

### Tài sản và hậu quả

| Tài sản / thao tác | Hậu quả khi replay thành công |
| --- | --- |
| Login assertion hoặc MFA response | Đăng nhập lại mà không có tương tác mới của người dùng |
| Password reset / recovery approval | Đổi credential hoặc hoàn tất recovery ngoài ý định |
| Passkey enrollment assertion | Gắn authenticator vào account bằng bằng chứng cũ |
| HMAC-signed API request | Lặp lại lệnh chuyển trạng thái, cập nhật quyền hoặc tạo tài nguyên |
| Webhook có chữ ký | Xử lý một event nhiều lần |
| TOTP code | Dùng lại mã đã được chấp nhận trong cùng time step |
| OAuth/OIDC callback | Tái sử dụng callback hoặc ghép response với login transaction khác |
| Sequence-protected device message | Phát lại command cũ tới thiết bị hoặc service |

### 2.1. Các dạng replay phổ biến

1. **Exact replay:** gửi lại nguyên thông điệp hoặc assertion đã bắt được.
2. **Delayed replay:** giữ thông điệp rồi gửi lại sau một khoảng thời gian.
3. **Concurrent replay:** gửi nhiều bản sao gần như đồng thời để hai request cùng vượt qua kiểm tra.
4. **Cross-context replay:** dùng bằng chứng của account/client/tenant/purpose này trong ngữ cảnh khác.
5. **Cross-protocol replay:** tái sử dụng một response ở endpoint hoặc giao thức khác do thiếu domain separation.
6. **Stale challenge:** dùng challenge đã hết hạn hoặc đã bị thay thế.
7. **State rollback replay:** tận dụng cache mất dữ liệu, replica chậm hoặc restore backup để làm trạng thái đã dùng biến mất.

Một hệ thống chống replay phải xét cả giao thức lẫn cách triển khai state. Chỉ thêm một trường timestamp vào payload không đủ.

## 3. Nonce và challenge

**Nonce** (number used once) là giá trị được thiết kế để chỉ dùng một lần trong một phạm vi xác định. Trong challenge-response, server tạo challenge mới; client đưa challenge vào dữ liệu được ký hoặc MAC. Server xác minh rằng phản hồi chứa đúng challenge đang chờ và challenge chưa được consume.

### 3.1. Yêu cầu với challenge

- **Unpredictable:** tạo bằng CSPRNG, không dùng timestamp, counter công khai hoặc ID tăng dần làm nonce bí mật.
- **Unique in scope:** xác suất trùng cực thấp trong phạm vi key, client hoặc transaction.
- **Short-lived:** có TTL phù hợp với thời gian hoàn tất giao dịch.
- **Bound to context:** gắn với subject/account, client, tenant, audience, purpose, method và transaction.
- **Authenticated:** được đưa vào phần dữ liệu có chữ ký/MAC hoặc được bảo vệ bởi giao thức xác thực.
- **Single-use:** trạng thái được consume nguyên tử khi chấp nhận thành công.
- **Unambiguous:** encoding và canonicalization rõ ràng, tránh nhiều biểu diễn cho cùng một thông điệp.

Một nonce ngẫu nhiên 128 bit trở lên thường tạo không gian đủ lớn cho nhiều hệ thống; 256 bit là lựa chọn phổ biến, đơn giản khi dùng CSPRNG. Kích thước chính xác cần phù hợp giao thức và giới hạn dữ liệu. Độ dài lớn không sửa được lỗi thiếu context binding hoặc không lưu trạng thái đã dùng.

### 3.2. Ràng buộc context

Một challenge record có thể chứa:

| Trường | Mục đích |
| --- | --- |
| **challenge_hash / challenge_id** | Tham chiếu challenge; tránh lưu raw secret nếu không cần |
| **subject_ref** | Account hoặc principal dự kiến |
| **client_id** | Ứng dụng đã bắt đầu transaction |
| **tenant_id** | Phạm vi tenant/realm |
| **audience** | Endpoint hoặc service được phép chấp nhận |
| **purpose** | Login, step-up, enrollment, recovery hoặc action cụ thể |
| **method** | WebAuthn, HMAC, MFA hoặc phương thức đã chọn |
| **issued_at / expires_at** | Thời điểm phát hành và hết hạn |
| **consumed_at / revoked_at** | Trạng thái one-time và thu hồi |
| **transaction_id** | Liên kết với giao dịch phía server |
| **policy_version** | Policy đã phát challenge |

Không nhận subject, audience hoặc purpose từ response rồi tự tin tưởng. Server phải lấy kỳ vọng từ transaction đã tạo trước đó và so sánh với bằng chứng.

### 3.3. Challenge không phải session

Challenge chỉ cấp quyền trả lời một thử thách cụ thể. Nó không nên cấp quyền truy cập API, không thay session cookie và không tự xác nhận user đã đăng nhập. Sau khi response hợp lệ, server thực hiện authentication decision và tạo session riêng theo policy.

## 4. Timestamp và clock window

Timestamp cho biết thông điệp được tạo vào khoảng thời gian nào. Server có thể chỉ chấp nhận request nếu timestamp nằm trong một cửa sổ cho phép:

\[
|t_{server} - t_{request}| \leq \Delta
\]

Trong đó \(\Delta\) là clock-skew window. Ví dụ một hệ thống nội bộ có thể cho phép lệch vài phút, nhưng giá trị phải dựa trên hạ tầng, giao thức và threat model.

### 4.1. Timestamp một mình không chống replay

Nếu attacker bắt được một request có timestamp còn trong cửa sổ hợp lệ, họ có thể gửi lại request đó nhiều lần trước khi cửa sổ đóng. Timestamp giới hạn độ tuổi của thông điệp; nó không chứng minh thông điệp chưa từng được chấp nhận.

Kết hợp:

- Timestamp để giới hạn tuổi của request.
- Nonce duy nhất để phân biệt từng request.
- MAC/chữ ký để bảo vệ timestamp, nonce và payload.
- Replay cache để từ chối nonce đã được chấp nhận.

### 4.2. Clock skew và đồng bộ

- Đồng bộ server bằng nguồn thời gian tin cậy, giám sát NTP drift và clock step.
- Dùng UTC trong protocol và audit.
- Không dùng clock client làm nguồn thời gian có thẩm quyền.
- Chọn cửa sổ vừa đủ để chịu mạng trễ nhưng không kéo dài cơ hội replay.
- Theo dõi clock rollback/forward jump và có hành vi an toàn khi vượt ngưỡng.
- Dùng monotonic clock cho timeout nội bộ trong tiến trình; dùng timestamp UTC cho dữ liệu trao đổi và lưu bền vững.

Nếu cho phép timestamp tương lai quá rộng, attacker có thể gửi request được chấp nhận lâu hơn dự kiến. Nếu cửa sổ quá hẹp, người dùng hợp lệ gặp lỗi do thiết bị lệch giờ hoặc mạng chậm. Cần xử lý clock error riêng và không tự động tắt anti-replay để sửa lỗi.

## 5. Counter và sequence number

Một counter tăng đơn điệu có thể chống replay mà không cần lưu nonce ngẫu nhiên cho từng message. Server lưu giá trị đã chấp nhận gần nhất và từ chối giá trị cũ hoặc bằng giá trị đó.

### 5.1. Monotonic counter

Với mỗi credential hoặc key:

\[
counter_{received} > counter_{lastAccepted}
\]

Chỉ cập nhật counter khi thông điệp đã được xác thực và được chấp nhận. Cập nhật phải nguyên tử để hai request đồng thời không cùng được chấp nhận.

### 5.2. Out-of-order messages

Trong giao thức có nhiều message đồng thời, yêu cầu counter tăng nghiêm ngặt có thể từ chối message hợp lệ đến trễ. Có thể dùng sliding window/bitmap:

- Lưu sequence cao nhất đã thấy.
- Giữ bitmap các sequence trong cửa sổ gần nhất.
- Từ chối sequence đã được đánh dấu.
- Chấp nhận sequence mới trong cửa sổ theo policy.
- Từ chối sequence quá cũ hoặc vượt giới hạn tương lai.

Đây là trade-off giữa khả năng chịu reorder và độ phức tạp state. Cần định nghĩa rõ kích thước cửa sổ, rollover, reset và đồng bộ giữa node.

### 5.3. HOTP và TOTP

- **HOTP** dùng counter; server tìm counter phù hợp trong một look-ahead window có giới hạn rồi cập nhật counter sau khi xác minh.
- **TOTP** thay counter tường minh bằng time step. Một mã có thể hợp lệ trong một cửa sổ thời gian; nếu không lưu trạng thái đã dùng, mã có thể được phát lại trong cùng time step.
- Với TOTP, lưu time step/counter đã chấp nhận gần nhất cho từng credential và chỉ cập nhật một lần bằng thao tác nguyên tử.
- Nếu cho phép clock window nhiều bước, phải tránh chấp nhận lại cùng time step trong các request song song.

TOTP không có khả năng chống phishing như WebAuthn vì mã có thể bị người dùng nhập vào trang giả trong thời gian hiệu lực. Replay prevention chỉ ngăn dùng lại mã đã tiêu thụ tại cùng hệ thống; nó không ngăn attacker relay mã theo thời gian thực.

## 6. One-time consume và replay cache

Server cần ghi nhớ challenge hoặc nonce nào đã được chấp nhận. Có thể dùng database unique constraint, atomic conditional update, Redis SET NX với TTL hoặc một replay cache chuyên dụng.

### 6.1. Quy tắc xử lý

1. Kiểm tra cấu trúc và giới hạn request.
2. Tải transaction/challenge đang chờ và kiểm tra expiry/context.
3. Xác minh chữ ký/MAC hoặc assertion.
4. Atomically claim/consume challenge để chỉ một request thắng.
5. Thực hiện action và ghi audit trong cùng transaction hoặc qua cơ chế idempotent nhất quán.
6. Từ chối các bản sao tiếp theo.

Thứ tự cần cân bằng DoS và race. Nếu consume trước khi xác minh chữ ký, attacker có thể gửi payload sai nhưng biết challenge và làm challenge bị đốt. Nếu chỉ xác minh trước mà không có atomic consume, nhiều request đồng thời có thể cùng vượt qua. Mẫu thường dùng là xác minh mật mã trước, sau đó atomic claim, rồi thực hiện action với transaction/idempotency phù hợp.

### 6.2. Database unique constraint

Ví dụ bảng replay record có unique key theo principal/key scope và nonce:

~~~sql
CREATE TABLE accepted_nonce (
    principal_ref VARCHAR(128) NOT NULL,
    nonce_hash VARCHAR(128) NOT NULL,
    accepted_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    PRIMARY KEY (principal_ref, nonce_hash)
);
~~~

Khi chấp nhận request, insert record. Nếu primary key đã tồn tại, request là replay. TTL cleanup chỉ xóa record sau khi không còn bất kỳ server nào chấp nhận timestamp hoặc challenge tương ứng. Không xóa quá sớm chỉ để tiết kiệm storage.

### 6.3. Atomic Redis pattern

Một cache có thể dùng thao tác kiểu SET key value NX EX ttl: chỉ tạo key nếu chưa tồn tại và gắn TTL trong một thao tác nguyên tử. Nếu key đã tồn tại, từ chối replay.

Key nên được namespace theo protocol, principal/key ID, audience và nonce digest. Không dùng raw credential hoặc token bí mật làm tên key có thể xuất hiện trong telemetry. Redis persistence, replication, eviction và failover phải được đánh giá; cache mất dữ liệu có thể làm nonce cũ được chấp nhận lại.

### 6.4. TTL của replay cache

TTL phải bao phủ toàn bộ khoảng thời gian mà request còn có thể được chấp nhận:

- Challenge lifetime.
- Timestamp acceptance window và clock skew.
- Network retry hoặc queue delay được policy cho phép.
- Độ trễ replication/region nếu có.

Nếu server chấp nhận timestamp lệch tối đa 5 phút, replay record không nên bị xóa chỉ sau 60 giây. Tốt hơn là tính TTL từ expiry của challenge hoặc từ cửa sổ chấp nhận cuối cùng.

## 7. Concurrency, distributed systems và failover

Replay thường khai thác race condition: hai request giống nhau đến hai instance khác nhau gần như cùng lúc. Cả hai đọc trạng thái chưa dùng, cả hai xác minh chữ ký, rồi cùng thực hiện hành động nếu không có atomic claim.

~~~mermaid
sequenceDiagram
    participant A as Attacker / Client
    participant N1 as Server instance 1
    participant N2 as Server instance 2
    participant C as Shared replay store
    A->>N1: Signed request + nonce N
    A->>N2: Replay cùng request + nonce N
    N1->>N1: Verify signature
    N2->>N2: Verify signature
    N1->>C: Atomic insert (principal, N)
    N2->>C: Atomic insert (principal, N)
    C-->>N1: Insert success
    C-->>N2: Unique conflict
    N1->>N1: Execute action once
    N2-->>A: Reject replay
~~~

Các yêu cầu triển khai:

- Replay state phải được chia sẻ giữa mọi instance/region có thể chấp nhận cùng credential.
- Dùng unique constraint hoặc atomic primitive; read-then-write không đủ.
- Định nghĩa consistency model và failover behavior.
- Không fail-open khi replay store mất kết nối đối với thao tác nhạy cảm.
- Nếu dùng multi-region active-active, thiết kế global uniqueness hoặc phân vùng key sao cho cùng nonce không thể được chấp nhận ở hai region.
- Xử lý eviction, backup restore, replication lag và cache flush như sự kiện security-relevant.
- Đặt giới hạn kích thước cache và rate limit để attacker không thể làm cạn replay store bằng nonce ngẫu nhiên.

Nếu replay store unavailable, có thể trả lỗi tạm thời và yêu cầu client retry bằng một challenge mới. Không bỏ qua anti-replay để duy trì availability cho thao tác đổi credential, thay đổi quyền hoặc giao dịch tài chính.

## 8. Freshness trong WebAuthn/passkey

Trong WebAuthn, Relying Party (RP) tạo challenge ngẫu nhiên và gửi trong PublicKeyCredentialRequestOptions. Authenticator tạo assertion gắn với challenge; browser gửi assertion về RP.

Server cần kiểm tra:

- Challenge trong client data khớp chính xác challenge đang chờ phía server.
- Challenge chưa hết hạn, chưa bị thu hồi và chưa được consume.
- Client data type là assertion cho authentication, không phải ceremony khác.
- Origin khớp origin được RP cho phép.
- RP ID hash đúng với RP ID cấu hình.
- Chữ ký assertion hợp lệ với public key đã đăng ký.
- Credential ID/user handle ánh xạ tới đúng account và policy.
- User presence và user verification đáp ứng yêu cầu.
- Challenge được consume nguyên tử trước khi tạo session.

Challenge cần gắn với login transaction và browser context. Không lấy challenge do client tự chọn rồi coi nó là challenge mới. Không chấp nhận assertion của account A trong transaction đang xác thực account B.

### Sign counter không phải cơ chế duy nhất

WebAuthn authenticator có thể cung cấp signature counter giúp phát hiện một số trường hợp credential bị clone. Tuy nhiên, counter có thể luôn bằng 0 hoặc không tăng đơn điệu với passkey đồng bộ. Vì vậy:

- Challenge freshness và one-time consume vẫn là kiểm soát chính cho replay assertion.
- Counter là tín hiệu bổ sung theo loại authenticator.
- Không từ chối mọi passkey chỉ vì counter không tăng nếu mô hình credential không bảo đảm counter tăng.
- Ghi nhận anomaly và kết hợp với risk policy.

## 9. Freshness trong OIDC và federation

OIDC sử dụng nhiều giá trị có vai trò khác nhau:

- **state:** ràng buộc callback với authorization request do RP khởi tạo, chống login CSRF và response injection.
- **nonce:** ràng buộc ID token với authentication request; RP kiểm tra nonce trong ID token.
- **PKCE:** ràng buộc authorization code với code verifier của client.
- **iat/exp:** thời điểm phát hành và thời điểm hết hạn của token.
- **auth_time/max_age:** thể hiện thời điểm xác thực người dùng và yêu cầu xác thực gần đây khi policy cần.

RP phải xác minh chữ ký, issuer, audience, authorized party khi áp dụng, expiry, nonce và state theo đúng protocol. iat trong quá khứ không tự chứng minh token đã được sử dụng; replay detection còn phụ thuộc nonce/state và cách RP quản lý transaction.

Nếu ứng dụng yêu cầu xác thực gần đây cho hành động nhạy cảm, hãy dùng policy reauthentication/max-age và kiểm tra authentication time. Không nhầm token mới được phát hành với việc người dùng vừa nhập lại credential: refresh token có thể tạo token mới mà không có tương tác xác thực mới.

## 10. Freshness trong HMAC-signed API request

Với API request signing, client và server chia sẻ secret key. Client ký một canonical representation chứa thông tin đủ để chữ ký không thể được chuyển sang request khác:

- Key ID hoặc principal reference.
- HTTP method.
- Canonical path và query.
- Audience/host/service.
- Hash của body.
- Timestamp.
- Nonce duy nhất.
- Content type hoặc header quan trọng theo protocol.

Ví dụ cấu trúc khái niệm:

~~~text
METHOD
CANONICAL_PATH_AND_QUERY
AUDIENCE
BODY_SHA256
TIMESTAMP
NONCE
~~~

Server:

1. Xác định key từ key ID đã đăng ký và kiểm tra key còn hiệu lực.
2. Kiểm tra timestamp trong clock window.
3. Canonicalize request đúng một cách duy nhất.
4. Tính lại HMAC và so sánh theo constant-time.
5. Kiểm tra nonce chưa tồn tại trong replay cache cho key/principal scope.
6. Atomically ghi nonce.
7. Thực hiện action theo idempotency/transaction policy.

Timestamp và nonce phải nằm trong phần được ký. Nếu nonce chỉ nằm trong header nhưng bị bỏ khỏi canonical string, attacker có thể thay nonce để né replay cache mà vẫn giữ chữ ký cũ.

Không canonicalize khác nhau giữa client và server. Khác biệt về percent-encoding, thứ tự query parameter, header whitespace, path normalization hoặc body serialization có thể tạo lỗi xác minh hoặc lỗ hổng request binding.

## 11. Freshness trong TOTP, webhook và message queue

### TOTP

TOTP dựa trên time step. Server thường cho phép một cửa sổ nhỏ để chịu lệch đồng hồ, nhưng phải lưu time step đã chấp nhận gần nhất hoặc tập mã đã dùng trong phạm vi hợp lệ. Một mã không được chấp nhận hai lần chỉ vì nó vẫn nằm trong cửa sổ thời gian.

### Webhook

Webhook provider nên ký payload và timestamp. Receiver kiểm tra chữ ký, timestamp window và event ID/delivery ID chưa xử lý. Vì provider có thể retry webhook hợp lệ, receiver cần idempotency theo event ID: event đã xử lý thì trả response phù hợp mà không lặp side effect. Đây là xử lý duplicate delivery; nó không có nghĩa chấp nhận một chữ ký cũ cho event khác.

### Message queue

Message cần có message ID, producer identity, audience/topic, creation time và sequence/version khi phù hợp. Consumer lưu ID hoặc sequence đã xử lý theo retention phù hợp. Queue redelivery hợp lệ phải được xử lý idempotently; message cũ từ producer không đáng tin hoặc ngoài retention cần bị từ chối theo policy.

## 12. TLS và replay ở tầng vận chuyển

TLS bảo vệ confidentiality và integrity của kết nối, nhưng không thay thế mọi cơ chế anti-replay ở tầng ứng dụng. Một request có thể được phát lại qua kết nối mới nếu ứng dụng không ràng buộc transaction và trạng thái đã xử lý.

TLS 1.3 0-RTT early data có đặc tính replayability trong một số deployment. Server và reverse proxy cần áp dụng anti-replay policy; không dùng early data cho thao tác thay đổi trạng thái như login completion, password reset, MFA enrollment, quyền truy cập hoặc giao dịch không idempotent nếu chưa có bảo đảm chống replay phù hợp. Có thể từ chối early data cho endpoint nhạy cảm hoặc yêu cầu client gửi lại qua handshake hoàn tất.

TLS sequence number bảo vệ record trong một kết nối; nó không phải application nonce dùng chung giữa các kết nối hay thay thế one-time challenge.

## 13. Freshness, idempotency và retry

Mạng có thể mất response sau khi server đã xử lý request. Client không biết thao tác đã hoàn tất hay chưa và gửi lại. Đây là tình huống retry hợp lệ, nhưng cũng giống replay ở bề ngoài.

Phân biệt:

- **Replay credential:** dùng lại bằng chứng xác thực đã được tiêu thụ; phải từ chối.
- **Retry cùng operation:** client gửi lại cùng operation ID để nhận lại kết quả đã lưu; có thể trả kết quả cũ mà không chạy side effect lần nữa.
- **New operation:** cần challenge/nonce mới, dù payload gần giống request cũ.

Một idempotency key phải gắn với principal, endpoint, payload digest và kết quả operation. Không dùng idempotency key thay nonce challenge; nó giúp ngăn lặp side effect chứ không chứng minh request mới.

Nếu action cần atomicity, lưu replay claim, operation result và thay đổi dữ liệu trong cùng transaction. Với side effect bên ngoài database, dùng transactional outbox, idempotent consumer hoặc workflow state machine để tránh trường hợp token đã consume nhưng action bị lặp hoặc bị mất.

## 14. Java: phát challenge và consume một lần

Ví dụ dưới đây là pseudocode Java định hướng. Repository cần bảo đảm atomicity bằng unique constraint hoặc conditional update trong database/replay store dùng chung.

~~~java
record ChallengeRecord(
    String challengeHash,
    String subjectRef,
    String clientId,
    String audience,
    String purpose,
    Instant expiresAt,
    Instant consumedAt
) {}

String createChallenge() {
    byte[] random = new byte[32];
    secureRandom.nextBytes(random);
    return Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(random);
}

ChallengeRecord issueChallenge(
        String rawChallenge,
        LoginTransaction tx) {

    return challengeRepository.insert(
        sha256(rawChallenge),
        tx.subjectRef(),
        tx.clientId(),
        tx.audience(),
        tx.purpose(),
        clock.instant().plus(CHALLENGE_TTL)
    );
}
~~~

Khi nhận response:

~~~java
AuthenticationResult verifyResponse(
        String rawChallenge,
        SignedResponse response,
        LoginTransaction tx) {

    ChallengeRecord challenge =
        challengeRepository.findByHash(sha256(rawChallenge));
    if (challenge == null || challenge.expiresAt().isBefore(clock.instant())) {
        return AuthenticationResult.staleChallenge();
    }

    if (!challenge.subjectRef().equals(tx.subjectRef())
            || !challenge.clientId().equals(tx.clientId())
            || !challenge.audience().equals(tx.audience())
            || !challenge.purpose().equals(tx.purpose())) {
        return AuthenticationResult.contextMismatch();
    }

    if (!signatureVerifier.verify(response, challenge)) {
        return AuthenticationResult.invalidProof();
    }

    // Chỉ một request đồng thời có thể chuyển challenge từ unused sang consumed.
    boolean claimed = challengeRepository.consumeIfUnused(
        challenge.challengeHash(), clock.instant()
    );
    if (!claimed) {
        return AuthenticationResult.replayed();
    }

    return authenticationPolicy.complete(tx, response);
}
~~~

Đây là pseudocode; trong production cần:

- Không nhận raw challenge tùy ý từ client làm nguồn sự thật; dùng transaction reference để tìm challenge server-side.
- Bảo đảm signature verifier xác minh toàn bộ context và payload cần thiết, không chỉ một phần message.
- Consume nguyên tử sau khi proof hợp lệ; xử lý race giữa verify và consume.
- Ràng buộc completion với database transaction/idempotency để không lặp side effect.
- Dùng clock có đồng bộ, TTL và cleanup phù hợp.
- Không log raw challenge, signed response nhạy cảm hoặc secret key.
- Không fail-open nếu replay store unavailable cho hành động nhạy cảm.

## 15. Ma trận kiểm thử challenge freshness

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Challenge ngẫu nhiên mới được phát | Có entropy, TTL và context binding |
| Challenge bị đoán hoặc tạo từ timestamp | Test phát hiện nguồn ngẫu nhiên yếu |
| Response chứa challenge sai | Từ chối |
| Challenge đúng nhưng đã hết hạn | Từ chối theo server clock |
| Challenge đúng nhưng purpose khác | Từ chối context mismatch |
| Challenge thuộc account A dùng cho account B | Từ chối |
| Challenge thuộc client/tenant khác | Từ chối |
| Assertion/HMAC hợp lệ được gửi lần đầu | Chấp nhận một lần nếu policy đạt |
| Exact request được gửi lại | Từ chối replay |
| Hai bản sao tới hai instance đồng thời | Chỉ một request claim được challenge |
| Replay cache unavailable | Từ chối hoặc lỗi tạm thời theo policy; không fail-open |
| Replay cache bị flush/failover | Cảnh báo và bảo toàn anti-replay state theo thiết kế |
| Timestamp trong cửa sổ nhưng nonce đã dùng | Từ chối |
| Timestamp ngoài clock window | Từ chối |
| Client clock lệch hợp lệ trong skew | Xử lý theo cửa sổ đã định nghĩa |
| TOTP cùng time step được gửi hai lần | Chỉ lần đầu được chấp nhận |
| HOTP counter cũ được gửi lại | Từ chối |
| Sequence đến sai thứ tự trong sliding window | Chấp nhận/từ chối theo bitmap policy đã định nghĩa |
| WebAuthn assertion có origin/RP ID sai | Từ chối dù chữ ký hoặc payload khác có vẻ hợp lệ |
| OIDC state/nonce bị ghép từ transaction khác | Từ chối callback/token |
| TLS 1.3 early data gửi action nhạy cảm | Không xử lý như request mới an toàn nếu endpoint không có anti-replay |
| Client retry operation sau timeout | Trả kết quả idempotent đã lưu, không lặp side effect |
| Replay record bị xóa trước khi acceptance window kết thúc | Test phát hiện cửa sổ replay mở lại |
| Raw challenge hoặc token xuất hiện trong log | Redaction test thất bại và chặn ghi |

### Tình huống thực hành

Một API nội bộ nhận lệnh đổi MFA factor. Client ký request bằng HMAC với shared secret. Payload có timestamp nhưng không có nonce. Server chấp nhận timestamp lệch tối đa 5 phút. Hai instance API dùng replay cache local riêng. Một request hợp lệ bị bắt lại và gửi đồng thời tới cả hai instance trong vòng 30 giây; cả hai đều trả success.

**Yêu cầu:** thiết kế lại giao thức và cách triển khai.

**Hướng phân tích:**

1. Timestamp chỉ giới hạn tuổi request, không ngăn replay trong cửa sổ 5 phút.
2. Thêm nonce CSPRNG duy nhất; đưa nonce, timestamp, method, canonical path/query, audience và body digest vào canonical string được HMAC.
3. Ràng buộc key ID/principal, tenant, endpoint và purpose; không cho chữ ký dùng chéo service hoặc thao tác.
4. Sau khi xác minh HMAC và timestamp, atomically claim nonce trong replay store dùng chung hoặc database có unique constraint.
5. Đặt TTL của replay record bao phủ toàn bộ timestamp acceptance window và clock skew; không dùng cache local độc lập.
6. Lưu operation ID/idempotency result để client retry khi response mất mà side effect không chạy lần hai.
7. Nếu shared replay store unavailable, từ chối tạm thời thao tác đổi MFA; không bỏ qua anti-replay.
8. Ghi audit principal, request reference, nonce digest, outcome và policy version; không ghi shared secret hoặc raw credential.

## 16. Câu hỏi tự kiểm tra

1. **Chữ ký hợp lệ có chứng minh request mới không?** Không. Nó chứng minh nguồn tạo chữ ký và integrity; freshness cần challenge/timestamp/counter và trạng thái anti-replay.
2. **Timestamp một mình có ngăn replay không?** Không. Request cũ vẫn có thể được phát lại trong clock window.
3. **Nonce cần gắn với những gì?** Subject, client, tenant, audience, purpose, transaction và thời hạn phù hợp.
4. **Vì sao cần atomic consume?** Để hai request đồng thời không cùng thấy challenge chưa dùng và cùng thực hiện action.
5. **Vì sao replay cache phải dùng chung giữa instance?** Nếu mỗi node có state riêng, cùng request có thể được chấp nhận một lần ở mỗi node.
6. **TOTP có chống replay tự động không?** Không. Server cần ghi nhận time step đã dùng và ngăn mã được chấp nhận lặp lại trong cửa sổ.
7. **Idempotency key có thay nonce không?** Không. Idempotency tránh lặp side effect khi retry; nonce/challenge chứng minh bằng chứng chưa bị dùng lại.
8. **Vì sao TLS 1.3 0-RTT cần policy riêng?** Early data có thể replay trong một số deployment; thao tác thay đổi trạng thái cần anti-replay hoặc bị từ chối trong early data.

**Ghi nhớ:** Freshness không đến từ một chữ ký đúng hay một timestamp còn mới. Hãy tạo challenge khó đoán, ràng buộc nó với đúng subject/client/audience/purpose, bảo vệ challenge trong chữ ký hoặc MAC, kiểm tra TTL và consume nguyên tử bằng replay state dùng chung. Kết hợp nonce với timestamp/counter khi cần, phân biệt replay với retry idempotent, và không fail-open cho thao tác nhạy cảm khi cơ chế chống replay gặp lỗi.
