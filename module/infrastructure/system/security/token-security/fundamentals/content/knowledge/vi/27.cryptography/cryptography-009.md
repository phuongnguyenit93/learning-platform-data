# Nonce trong giao thức mật mã

Khi xác thực người dùng, ký một thông điệp, mã hóa dữ liệu hoặc gửi một proof tới API, hệ thống thường cần biết **“đây có phải thông điệp dành cho giao dịch hiện tại, hay chỉ là bản sao của thông điệp cũ?”** Một trong những công cụ để giải quyết bài toán ấy là **nonce**, viết từ *number used once*: giá trị được sử dụng theo quy tắc một lần hoặc theo một miền không lặp được xác định bởi giao thức.

Nonce xuất hiện trong nhiều bối cảnh nhưng **không có một cách sinh, lưu và kiểm tra duy nhất** cho mọi bối cảnh. Với AES-GCM, IV/nonce **không được lặp với cùng khóa mã hóa**. Với OpenID Connect (OIDC), `nonce` giúp client liên kết **ID token** với một yêu cầu đăng nhập cụ thể. Với DPoP, `jti`, `iat` và đôi khi **nonce do server cấp** giúp resource server/authorization server hạn chế phát lại proof đã ký. Với challenge–response, verifier cấp một giá trị mới để bên giữ khóa chứng minh mình đang tham gia giao dịch.

Điểm quan trọng: **nonce không phải mật khẩu, access token, refresh token hay chữ ký**. Một chuỗi ngẫu nhiên đặt ở mọi request sẽ không tự ngăn replay nếu server không kiểm tra giá trị ấy, không ràng buộc nó với nội dung/thời điểm/bên tham gia hoặc chấp nhận dùng lại sai quy tắc.

Bài **“Nonce trong giao thức mật mã”** thuộc chương **Cryptography** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Mục tiêu là hiểu mô hình tin cậy và vòng đời token, phân biệt JWT/opaque token, access/refresh token, OAuth 2.0/OIDC, claims, audience, scope, kiểm tra token, thu hồi và phòng chống token theft/replay thông qua các trường hợp sử dụng nonce thực tế.

> **Nguyên tắc:** **Yêu cầu đối với nonce đến từ giao thức.** Có nơi chỉ cần **không trùng**, có nơi cần **khó dự đoán**, có nơi cần **freshness và server-side replay state**. Một nonce hợp lệ về định dạng nhưng không được ràng buộc mật mã với request và không được kiểm tra ở đúng nơi **không tạo ra bảo vệ thực sự**.

## 1. Nonce là gì và không phải là gì?

Nonce là một giá trị được chọn để bảo đảm **tính mới hoặc tính duy nhất trong một phạm vi đã định**. Tên gọi *number* mang tính lịch sử; trên thực tế nonce có thể là dãy bytes ngẫu nhiên, một bộ đếm, chuỗi Base64url hoặc giá trị được dẫn xuất theo thuật toán.

Ví dụ:

~~~text
Tình huống A: mã hóa AES-GCM
  key = K
  nonce = IV_001
  ciphertext_1 = Encrypt(K, IV_001, message_1)
  -> Không mã hóa message_2 dưới K với IV_001 lần nữa.

Tình huống B: đăng nhập OIDC
  browser transaction = TX_42
  nonce = N_42
  authorization request mang N_42
  ID token trả về phải có nonce = N_42.

Tình huống C: DPoP
  HTTP request #1 có proof jti = J_101
  HTTP request #2 phải có proof jti mới = J_102
  RS kiểm chữ ký và replay window; không chấp nhận phát lại J_101.
~~~

Trong ba trường hợp:

- AES-GCM yêu cầu **tính duy nhất theo khóa**, không đòi nonce phải bí mật.
- OIDC `nonce` cần được sinh và lưu trong **đúng authorization transaction**, không chỉ kiểm “đã từng thấy”.
- DPoP `jti` có tác dụng chống replay **chỉ khi verifier kiểm tra và lưu trạng thái đủ lâu**, theo profile và policy.

### 1.1. Nonce không phải secret mặc định

Nonce AES-GCM thường được gửi **công khai cùng ciphertext**. Server challenge cũng thường được gửi công khai tới client. Tính an toàn đến từ **thuộc tính duy nhất/khó đoán đúng yêu cầu** và **khóa mật mã được giữ bí mật**, chứ không phải giấu mọi nonce.

Tuy nhiên, một số giao thức yêu cầu nonce **khó dự đoán trước khi được cấp** để tránh attacker chuẩn bị trước câu trả lời hoặc kiểm soát giao dịch. Do đó không nên suy “nonce công khai được nên dùng `timestamp` dễ đoán cho mọi trường hợp”.

### 1.2. Nonce không phải token truy cập

Một access token Bearer còn hạn thường được dùng cho **nhiều** HTTP requests hợp lệ; nó không phải “number used once”. Một `nonce` trong DPoP proof hoặc `jti` của proof có thể mang semantics khác. Đừng khóa access token sau lần gọi API đầu tiên chỉ vì JWT có claim `jti`.

### 1.3. Nonce không thay chứng thực và phân quyền

Một nonce có tính duy nhất tốt nhưng không có **signature, HMAC hoặc AEAD authentication** có thể bị attacker thay đổi cùng thông điệp. Và một proof mật mã hợp lệ vẫn cần kiểm **issuer, audience, scope, expiry, tenant, resource ownership** trước khi cho phép hành động.

## 2. Ba tính chất dễ bị nhầm: unique, unpredictable, fresh

| Tính chất | Ý nghĩa | Khi nào cần? | Điều **không** suy ra |
| --- | --- | --- | --- |
| **Unique (không trùng)** | Không dùng lại giá trị trong miền được quy định | AES-GCM key/nonce, nhiều sequence numbers | Không đảm bảo khó đoán |
| **Unpredictable (khó dự đoán)** | Attacker không đoán được giá trị tương lai trước khi nó được tiết lộ | Challenge–response, OIDC nonce/state theo threat model | Không tự ngăn replay sau khi giá trị đã lộ |
| **Fresh (mới ở thời điểm kiểm tra)** | Giá trị được verifier chấp nhận cho giao dịch/cửa sổ hiện tại | Login transaction, DPoP proof, challenge | Không tự bảo vệ nội dung nếu thiếu cryptographic binding |
| **Single-use (tiêu thụ một lần)** | Verifier không chấp nhận lần thứ hai theo policy | One-time challenge, authorization code | Không áp mặc định cho mọi nonce/IV |
| **Bound to context** | Giá trị nằm trong thông điệp được MAC/ký và gắn đúng hành động/bên nhận | Proof API, OIDC ID token, challenge–response | Không thay kiểm tra quyền |

### 2.1. Một counter có thể unique nhưng đoán được

~~~text
K = AES-GCM key dành cho một sender
nonce[0] = 000000000000000000000001
nonce[1] = 000000000000000000000002
nonce[2] = 000000000000000000000003
~~~

Nếu giao thức cho phép nonce theo counter, việc người ngoài đoán được counter **không nhất thiết phá bảo mật**. Nhưng counter phải **không lặp khi process restart, nhiều nodes cùng dùng key hoặc counter overflow**. Với một challenge đăng nhập cần khó đoán, counter đơn giản **không phải lựa chọn phù hợp**.

### 2.2. Random không có nghĩa chắc chắn unique

Một nonce được sinh ngẫu nhiên vẫn có xác suất trùng. Với \(n\) giá trị ngẫu nhiên độc lập, phân bố đều trong không gian \(2^b\) khả năng, xác suất đụng độ xấp xỉ theo *birthday bound* khi \(n\) đủ nhỏ:

\[
P(\text{có collision}) \approx \frac{n(n-1)}{2^{b+1}}
\]

Không sử dụng công thức này để suy ra một con số “an toàn tuyệt đối”. Phải xem giới hạn số lần dùng một khóa, tổng bytes/blocks được xử lý và yêu cầu của thuật toán/protocol. Ví dụ **AES-GCM với IV 96 bit** thường dùng random IV khi giới hạn số bản mã trên mỗi khóa được quản lý; hệ thống tải lớn/nhiều nodes phải có nonce strategy và key rotation phù hợp, không chỉ gọi `SecureRandom` vô hạn rồi bỏ theo dõi.

### 2.3. Freshness là quan hệ với thời gian và trạng thái

Nếu user đăng nhập lúc 10:00, ID token có nonce đúng cho **lần đăng nhập 09:00** không thể tự được coi là hợp lệ cho transaction mới. Nếu DPoP proof có `iat` trong cửa sổ cho phép nhưng `jti` đã được sử dụng trong cửa sổ đó, verifier phải xử lý như **replay** theo policy.

**Nonce mới không phải bằng chứng của giao dịch mới** nếu client/server không lưu hoặc so sánh với **ngữ cảnh được tạo trước**.

## 3. Bảng phân biệt nonce với các giá trị mật mã liên quan

| Giá trị | Mục đích chính | Yêu cầu điển hình | Không nên nhầm với |
| --- | --- | --- | --- |
| **Nonce/challenge** | Freshness, chống phản hồi cũ | Random khó đoán hoặc unique + TTL/replay state | Access token, password |
| **IV của AES-GCM** | Mã hóa an toàn dưới một key | Không tái sử dụng cùng key | OTP, secret, HMAC key |
| **Salt của password hash** | Chống bảng tra chung, phân biệt hashes | Unique/random theo password-hashing scheme; thường public | Nonce chống replay của HTTP |
| **ECDSA signing nonce `k`** | Ephemeral scalar trong chữ ký | Unique, được bảo vệ, sinh an toàn hoặc deterministic RFC 6979 | Public AES-GCM IV |
| **OIDC `nonce`** | Ràng buộc ID token với authentication request | Random, gắn session/transaction và so sánh | OAuth `state`, PKCE |
| **OAuth `state`** | Ràng buộc authorization response với request, chống CSRF/mix-up theo thiết kế | Không đoán được, gắn user session, kiểm equality | OIDC ID token nonce |
| **PKCE `code_verifier`** | Bằng chứng client đổi code đúng | Random high entropy, giữ bí mật cho token exchange | Nonce công khai |
| **JWT `jti`** | Định danh token | Unique trong profile, dùng tra cứu/revoke | Automatic one-use |
| **DPoP proof `jti`** | Nhận diện proof để chống replay | Unique + replay tracking trong cửa sổ | JWT access-token `jti` |
| **DPoP server nonce** | Server tăng freshness/context cho proof | Do AS/RS cấp và verifier kiểm theo policy | Client-generated proof `jti` |
| **Authorization code** | Credential giao dịch đổi token | Single-use, short-lived, client/redirect/PKCE binding | Generic random nonce |
| **Device code** | Credential polling của Device Authorization Grant | High-entropy, TTL, client binding, consume khi exchange | OIDC nonce/IV |

**Cùng tên “nonce” không có nghĩa cùng cách kiểm tra.** Một IV AES-GCM có thể dùng lại **giá trị bytes** sau khi đổi sang một key khác theo điều kiện của thuật toán, nhưng OIDC transaction nonce cũ không được dùng làm nonce cho lần đăng nhập mới chỉ vì issuer đã đổi signing key.

## 4. Threat model: nonce giúp chống kiểu tấn công nào?

### 4.1. Replay attack

Attacker ghi lại thông điệp hợp lệ:

~~~text
Message M:
  action=transfer
  amount=500000
  signature=valid
~~~

Nếu verifier chấp nhận chính `M` nhiều lần mà không có định danh giao dịch/idempotency/replay state, attacker có thể gửi lại để tạo **nhiều giao dịch**. Một nonce/challenge mới trong **nội dung được ký** và trạng thái *seen/consumed* tại server có thể giúp ngăn thông điệp cũ được chấp nhận.

**Quan trọng:** HTTP idempotency keys, transaction IDs và nonce có thể cùng tồn tại nhưng không đồng nhất. Một hệ thống thanh toán nên dùng **business-level idempotency**, authorization/state checks và audit; không tự coi một random string là đủ ngăn chuyển tiền trùng.

### 4.2. Precomputation/predictable challenge

Nếu verifier luôn gửi `nonce=1234` hoặc `nonce=currentMinute`, attacker có thể chuẩn bị trước phản hồi trong một số giao thức và tăng khả năng mạo danh. Với challenge–response, hãy dùng **CSPRNG** và TTL gắn với session/action, bảo đảm nonce chỉ được tiêu thụ theo hợp đồng.

### 4.3. Chosen-context/relay

Attacker không nhất thiết phải *phát lại một thông điệp cũ*: họ có thể **chuyển tiếp challenge hiện tại** tới nạn nhân và lấy phản hồi hợp lệ rồi dùng nó ở một nơi khác. Chống kiểu này cần **ràng buộc target origin, audience, resource, action, method/URL và session** trong phần được ký/MAC, đồng thời bảo vệ kênh truyền. Một nonce đơn lẻ **không chống real-time relay/MITM**.

### 4.4. Cryptographic nonce reuse

Với các thuật toán như AES-GCM, dùng lại cùng key/nonce không chỉ làm freshness yếu mà có thể **làm hỏng confidentiality và authenticity**. Đây là vấn đề ở **bản thân encryption primitive**, khác với việc một Bearer access token được gửi hai lần.

## 5. Kiến trúc tổng quát: nonce phải đi từ nơi tạo tới nơi kiểm tra

Một nonce được thiết kế tốt cần xác định **issuer của nonce**, **đối tượng được bảo vệ**, **bên kiểm tra** và **vòng đời**.

~~~mermaid
sequenceDiagram
    autonumber
    participant V as Verifier / Server
    participant P as Prover / Client
    participant S as State store
    V->>S: Tạo transaction + nonce + expiry + context
    V-->>P: Challenge nonce
    P->>P: Tạo bằng chứng MAC/signature trên nonce + context
    P->>V: Proof + transaction reference
    V->>V: Verify key, signature, context, freshness
    V->>S: Atomic check-and-consume nonce / proof ID
    S-->>V: Accepted once hoặc already used/expired
    V-->>P: Cho phép bước tiếp theo hoặc từ chối
~~~

Các bước thay đổi theo giao thức: AES-GCM không có verifier gửi challenge như sơ đồ, mà sender tạo IV và bên decrypt kiểm authentication tag. **Đây là sơ đồ cho challenge–response**, không phải sơ đồ thay thế mọi nonce mode.

### 5.1. Bốn thông tin cần định nghĩa

| Trường | Câu hỏi cần chốt |
| --- | --- |
| **Scope/namespace** | Giá trị cần unique **trong một key**, một issuer, một user session hay toàn hệ thống? |
| **Creator** | Client tự sinh, server sinh, hay được dẫn xuất deterministic từ sequence/key? |
| **Verifier** | Ai giữ expected nonce, replay cache, trusted key và expiration policy? |
| **Lifecycle** | Khi nào được tạo, tiết lộ, dùng, tiêu thụ, hết hạn và dọn dẹp? |

### 5.2. Không có nonce store thì sao?

Một giao thức có thể bảo đảm uniqueness nhờ counter/deterministic state tại bên phát, **không cần distributed “seen nonce” store** cho mỗi thông điệp. Ngược lại, một protocol yêu cầu **reject proof replay** thì verifier phải có cơ chế phát hiện sử dụng lại theo thời gian: stateful set, monotonic sequence window, server-issued transaction state hoặc phương pháp phù hợp.

**Đừng thêm Redis cho mọi nonce vì tên gọi “used once”, cũng đừng bỏ replay state trong DPoP chỉ vì proof đã được ký.**

## 6. Nonce/IV trong AES-GCM: trường hợp lỗi cực kỳ nghiêm trọng

**AES-GCM** là chế độ authenticated encryption (AEAD). Khi mã hóa:

~~~text
Inputs:
  K   = AES encryption key
  IV  = nonce / initialization vector
  P   = plaintext
  AAD = additional authenticated data

Outputs:
  C   = ciphertext
  TAG = authentication tag

(C, TAG) = AES_GCM_Encrypt(K, IV, P, AAD)
~~~

Khi giải mã, bên nhận phải có key, IV, AAD tương ứng và **kiểm authentication tag**. IV **không phải secret** và thường được lưu ngay cạnh ciphertext.

### 6.1. Tính duy nhất của cặp (key, nonce)

~~~text
An toàn theo thiết kế nonce:
  Encrypt(K1, IV001, plaintext_A)
  Encrypt(K1, IV002, plaintext_B)

Không được làm:
  Encrypt(K1, IV001, plaintext_A)
  Encrypt(K1, IV001, plaintext_B)  <-- key/nonce reuse
~~~

Reuse AES-GCM nonce với cùng khóa có thể làm lộ quan hệ giữa plaintexts và giúp kẻ tấn công **giả mạo authentication tags** trong những điều kiện nhất định. Đừng coi đó chỉ là “xác suất đoán được nonce tăng một chút”. **Nonce reuse là lỗi crypto design có mức độ nghiêm trọng cao.**

### 6.2. Random IV 96-bit và deterministic IV

Hai chiến lược thường gặp:

1. **Random 96-bit IV** sinh bằng CSPRNG: dễ triển khai cho ứng dụng quy mô vừa; phải theo dõi **giới hạn số lần encrypt mỗi key** và rủi ro collision, kể cả khi nhiều nodes cùng dùng key.
2. **Deterministic 96-bit IV** gồm phần định danh sender/instance cố định và counter được phân vùng đúng: có thể bảo đảm uniqueness theo cấu trúc nhưng phải xử lý restart, failover, overflow và phân quyền cấp dải counter.

**Không dùng `System.currentTimeMillis()` đơn thuần, `Random`, PID hoặc restart counter=0 dưới cùng key.** Định nghĩa rõ domain và quotas; áp hướng dẫn NIST SP 800-38D và profile liên quan, không tự suy rằng bất kỳ IV dài 12 bytes đều an toàn.

### 6.3. Multi-instance là tình huống nonce collision dễ bị bỏ qua

~~~text
Node A giữ K, counter=001 -> IV001
Node B giữ K, counter=001 -> IV001

Kết quả:
  cùng (K, IV001) được dùng ở hai nodes.
~~~

Giải pháp có thể là **khóa khác nhau theo node/epoch**, cấp dải counter duy nhất bằng authoritative service hoặc một chiến lược CSPRNG/nonce policy phù hợp với tổng lưu lượng. Nếu counter được lưu bền vững, cần **commit trước khi phát ciphertext** hoặc cơ chế ngăn lặp sau crash/rollback.

### 6.4. AAD, nonce và business metadata

AES-GCM cho phép **AAD** (không mã hóa nhưng được integrity-protected). Ví dụ:

~~~text
AAD = protocol_version || issuer_id || tenant_context
~~~

Bên decrypt phải cung cấp **đúng AAD**; nếu attacker sửa AAD hoặc ciphertext, tag verification thất bại. Nhưng AAD do hệ thống thiết kế còn phải được **ràng buộc với nguồn tin cậy**. Đừng đặt `tenant_id` từ HTTP header chưa xác minh vào AAD rồi suy ra user có quyền tenant đó.

### 6.5. Key rotation không thay khắc phục nonce reuse đã xảy ra

Đổi key mới ngăn những encryptions tiếp theo tiếp tục dùng cùng key/nonce pair, nhưng **không khôi phục tính bí mật của ciphertext cũ** đã bị đặt dưới key/nonce trùng. Nếu có evidence nonce reuse trong production, phải coi đó là một **crypto incident**, đánh giá dữ liệu và key exposure, thu hồi/rotate và có kế hoạch re-encryption.

## 7. Chữ ký ECDSA và ephemeral signing nonce `k`

Một thuật ngữ *nonce* khác xuất hiện trong **ECDSA signing**: số ngẫu nhiên/ephemeral scalar `k` được dùng **nội bộ khi tạo chữ ký**. Khác với IV AES-GCM có thể được gửi công khai, **giá trị `k` của ECDSA phải được bảo vệ**.

### 7.1. Vì sao không được dùng lại `k`?

ECDSA (mô tả giản lược, không dùng làm code tính chữ ký):

\[
s = k^{-1}(H(m)+r d)\pmod n
\]

Trong đó \(\,d\,\) là private signing key, \(\,k\,\) là per-signature secret, \(\,H(m)\,\) là message digest, và \(\,r,s\,\) là các thành phần chữ ký. Nếu `k` bị dùng lại cho hai message khác nhau hoặc bị lộ, attacker có thể trong nhiều tình huống **khôi phục private signing key**.

**Đây là lý do không bao giờ tự tạo ECDSA nonce bằng timestamp hoặc `Random`.** Dùng thư viện chữ ký chuẩn được kiểm thử và key management an toàn.

### 7.2. Deterministic ECDSA theo RFC 6979

RFC 6979 mô tả cách dẫn xuất `k` deterministic từ private key và message hash, giúp tránh nhiều lỗi của entropy source khi ký. **Deterministic không có nghĩa `k` được phép lặp giữa hai messages**; thuật toán được thiết kế để tránh reuse nguy hiểm và tạo giá trị khó suy ra nếu không biết private key.

### 7.3. Nonce trong các thuật toán khác không luôn giống nhau

RSA-PSS sử dụng **salt** theo signature scheme, không phải AES-GCM IV. EdDSA có cách tạo giá trị ephemeral theo đặc tả của nó; không lấy quy tắc ECDSA `k` để tự sinh “nonce EdDSA” tùy ý.

**Quy tắc:** chọn **thư viện crypto**, thuật toán và profile đã được chuẩn hóa; không tự xây signature primitive chỉ vì đã hiểu công thức nonce.

## 8. Challenge–response: nonce gắn với bằng chứng sở hữu khóa

Giả sử server muốn client chứng minh sở hữu **private signing key** mà không gửi key qua mạng.

~~~mermaid
sequenceDiagram
    autonumber
    participant S as Server / verifier
    participant C as Client giữ private key
    S->>S: Sinh challenge ngẫu nhiên N + expiry
    S-->>C: N, transaction ID, audience, action
    C->>C: Sign(domain || N || audience || action)
    C->>S: Transaction ID + signature
    S->>S: Kiểm public key, context, TTL
    S->>S: Atomic consume challenge
    S-->>C: Chấp nhận hoặc từ chối
~~~

### 8.1. Chữ ký phải bao phủ context

Sai:

~~~text
signature = Sign(privateKey, nonce_only)
~~~

Nếu proof có thể dùng ở nhiều endpoints và verifier không ràng buộc purpose, một chữ ký trên challenge có thể bị **relay** hoặc dùng nhầm giao thức.

Tốt hơn về mặt thiết kế:

~~~text
signed_payload = canonicalEncode(
  protocol_id,
  protocol_version,
  nonce,
  transaction_id,
  issuer_or_verifier_id,
  target_audience,
  operation,
  expiration
)
signature = Sign(privateKey, signed_payload)
~~~

**Không tự phát minh protocol signing string cho production**: canonicalization, domain separation, cross-protocol reuse và downgrade attacks rất khó xử lý. Ưu tiên profile đã chuẩn hóa (ví dụ WebAuthn, DPoP, mTLS) khi phù hợp.

### 8.2. One-time consume cần nguyên tử

Kiểm “nonce tồn tại” rồi xử lý request và xóa sau **không đủ** nếu hai requests đồng thời có thể cùng qua bước kiểm:

~~~text
Request A: lookup N -> chưa dùng
Request B: lookup N -> chưa dùng
Request A: cho phép
Request B: cho phép    <-- replay race
~~~

Server cần **atomic check-and-consume** hoặc transaction state transition có bảo đảm phù hợp. Trong distributed deployments, local `ConcurrentHashMap` trên từng node chỉ bảo vệ **trong một process**, không chống duplicate qua các nodes.

### 8.3. Nonce không ngăn relay thời gian thực

Nếu attacker có thể yêu cầu nạn nhân ký challenge **ngay lúc đó**, rồi chuyển signature đến server, một nonce unique vẫn có thể được dùng hợp lệ cho lần đầu. Cần **user presence/verification, origin binding, audience/action binding** và các lớp phòng chống phishing/relay theo protocol.

## 9. Nonce trong OAuth 2.0 và OpenID Connect: không gộp các tham số

Một luồng đăng nhập Authorization Code + PKCE có thể xuất hiện:

~~~http
GET /authorize?response_type=code
  &client_id=reports-web
  &redirect_uri=https%3A%2F%2Freports.example.com%2Fcallback
  &scope=openid%20profile
  &state=<random-state>
  &nonce=<random-oidc-nonce>
  &code_challenge=<s256-challenge>
  &code_challenge_method=S256 HTTP/1.1
Host: auth.example.com
~~~

Request trên được **ngắt dòng để giải thích**; URI thực tế cần encode đúng và được gửi thành một URL hợp lệ. Các giá trị mang chức năng khác nhau:

| Tham số | Ai tạo? | Kiểm ở đâu? | Đảm bảo chính |
| --- | --- | --- | --- |
| **`state`** | OAuth/OIDC client | Client kiểm trong authorization response, gắn browser session | Response correlation/CSRF defense, hỗ trợ chống mix-up khi kết hợp issuer check |
| **`nonce`** | OIDC client | Client kiểm claim `nonce` trong **ID token đã verify** | ID token gắn với authentication request |
| **`code_challenge`** | Client dẫn xuất từ verifier | AS so với `code_verifier` khi đổi authorization code | Chống authorization-code interception/substitution theo PKCE |
| **`code_verifier`** | Client, entropy cao | AS kiểm tại token endpoint | Bằng chứng client đang đổi đúng code |
| **Authorization code** | AS | AS tiêu thụ khi token exchange | One-time short-lived credential |

### 9.1. `state` không thay `nonce`

OAuth `state` giúp client nhận diện callback thuộc request mình khởi tạo. OIDC `nonce` được gửi trong authentication request và **xuất hiện lại trong ID token**, để client xác minh ID token thuộc lần đăng nhập đó. Một ứng dụng dùng `state` đúng chưa chắc đã kiểm `nonce` khi có; ngược lại, chỉ kiểm ID token nonce không thay CSRF/session binding cho authorization response.

### 9.2. PKCE không phải generic replay nonce

`code_verifier` có entropy cao và `code_challenge=S256(code_verifier)`, nhưng PKCE là cơ chế **ràng buộc authorization code với client đã bắt đầu flow**. Đừng đổi tên verifier thành `nonce` rồi coi mọi JWT proof/token đều được chống replay.

### 9.3. JWT access token không nhất thiết có claim `nonce`

Trong OIDC, `nonce` nói trên liên hệ **ID token**, không phải trường mặc định bắt buộc của OAuth JWT access token. Một API nhận access token nên validate `iss`, `aud`, `exp`, scope và token type theo profile; **không yêu cầu OIDC nonce từ access token tùy tiện**.

## 10. OIDC nonce: ràng buộc ID token với yêu cầu đăng nhập

**OpenID Connect Core 1.0** định nghĩa tham số `nonce` trong Authentication Request. Khi client gửi `nonce=N`, OpenID Provider (OP) phải đưa giá trị tương ứng vào claim `nonce` trong ID token theo profile, và **client phải kiểm tra nó khớp giá trị gửi cho đúng transaction**.

Một flow đơn giản:

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant C as OIDC Client / BFF
    participant OP as OpenID Provider
    B->>C: Bắt đầu đăng nhập
    C->>C: Sinh state S, nonce N, PKCE verifier V
    C->>C: Lưu S → (N, V, session, issuer, expiry)
    C-->>B: Redirect đến OP với state=S, nonce=N, challenge(V)
    B->>OP: Authorization request
    OP->>B: Login, consent theo policy
    OP-->>B: Redirect callback với code + state S
    B->>C: Callback
    C->>C: Kiểm S đúng session/transaction, issuer
    C->>OP: Đổi code + PKCE verifier V
    OP-->>C: ID token đã ký, nonce=N (+ access token)
    C->>C: Verify ID token signature, iss, aud, exp, nonce=N
    C-->>B: Tạo local session hợp lệ
~~~

### 10.1. Vì sao có `nonce` khi đã có `state`?

`state` ràng buộc **authorization response/callback** với transaction của client. `nonce` ràng buộc **ID token cụ thể** với authentication request tương ứng. Cả hai giúp phòng các biến thể replay/injection/mix-up **khi được kiểm đúng nơi và đúng trust boundary**.

Ví dụ attacker tìm cách đưa một ID token cũ của user A vào transaction login mới của user B. Nếu client chỉ verify chữ ký và `exp` nhưng bỏ `nonce`, ID token cũ có thể vẫn cryptographically valid. Khi client gửi `nonce` mới và kiểm giá trị trong ID token, token cũ có `nonce` khác **bị từ chối**.

**Không tuyên bố `nonce` một mình chặn toàn bộ login CSRF hoặc mix-up.** Client vẫn cần `state`, issuer/authorization response binding, PKCE, redirect URI registration và ID token validation theo OIDC profile.

### 10.2. Yêu cầu phụ thuộc response type/flow

Trong **OIDC Authorization Code Flow**, gửi `nonce` có thể là tùy chọn theo yêu cầu của OIDC Core, nhưng nếu client đã gửi thì **phải kiểm giá trị tương ứng trong ID token**. Với **Implicit/Hybrid Flow**, OIDC Core đặt các quy tắc bắt buộc riêng cho `nonce`. Thiết kế ứng dụng mới thường ưu tiên **Authorization Code + PKCE**; không chọn Implicit chỉ để có `nonce`.

### 10.3. Lưu expected nonce ở client/BFF

Một transaction record:

~~~text
oidc_transaction:
  transaction_id: random reference
  state_hash: HMAC/hash theo scheme và policy
  expected_nonce: N
  expected_issuer: https://auth.example.com
  client_id: reports-web
  redirect_uri: https://reports.example.com/callback
  browser_session_binding: session-xyz
  pkce_verifier: V  [giữ bí mật đến token exchange]
  created_at / expires_at
  consumed_at
~~~

Đây là **mô hình tự thiết kế**, không phải schema chuẩn bắt buộc. Mục tiêu: callback không thể lấy expected nonce từ một biến global “latest nonce” của toàn ứng dụng, không thể dùng transaction của browser khác và không lưu `code_verifier` ở URL/log.

### 10.4. So sánh `nonce` trong ID token đúng thứ tự

Trình tự an toàn:

1. Nhận authorization callback từ đúng endpoint/redirect, kiểm `state` và issuer theo flow.
2. Đổi authorization code bằng đúng PKCE verifier/client authentication nếu có.
3. Validate ID token **signature/key/issuer/audience/expiry và claims OIDC** bằng trust config của OP.
4. Lấy expected nonce từ **transaction đã tạo**.
5. So sánh **chính xác** claim `nonce` trong ID token với expected value; nếu thiếu/sai khi đã gửi nonce, từ chối.
6. Tiêu thụ/đóng transaction theo policy, không tái dùng để đăng nhập lần khác.

**Không coi `nonce` đúng nhưng signature sai là hợp lệ.** Attacker có thể tự tạo JSON chứa nonce đã thấy; chỉ ID token xác minh toàn vẹn và nguồn OP đáng tin mới có ý nghĩa.

### 10.5. Hai tab đăng nhập song song

~~~text
Tab A: state=S_A, nonce=N_A, verifier=V_A
Tab B: state=S_B, nonce=N_B, verifier=V_B

Callback của A -> tìm transaction S_A -> mong đợi N_A.
Callback của B -> tìm transaction S_B -> mong đợi N_B.
~~~

Nếu client chỉ có một biến `expectedNonce` trong session và bị Tab B ghi đè, Tab A có thể thất bại hoặc bị **ghép sai ngữ cảnh**. Dùng transaction store theo `state` và session binding, TTL, kiểm pending/consumed. Không giải quyết bằng cách bỏ nonce validation để “hết lỗi nhiều tab”.

### 10.6. Nonce không được dùng làm bearer session ID

OIDC nonce là giá trị chứng minh tương quan request/ID token, **không phải cookie session dùng được để gọi API**. Không gửi `nonce` đến Resource Server như `Authorization: Bearer`; không dùng nó thay `id_token` hoặc access token.

## 11. OAuth `state`, PKCE và authorization code: ba cơ chế khác nonce OIDC

Một client đăng nhập hiện đại có thể dùng đồng thời **`state`**, **PKCE** và OIDC **`nonce`**. Cần hiểu rõ trách nhiệm:

~~~text
STATE:
  Client tạo S và gắn S với browser transaction.
  AS gửi S trong authorization response.
  Client kiểm S trước khi xử lý callback.

PKCE:
  Client tạo secret verifier V.
  AS nhận challenge = BASE64URL(SHA256(ASCII(V))).
  Khi đổi code, client gửi V; AS kiểm với challenge.

OIDC NONCE:
  Client tạo N và gửi ở Authentication Request.
  OP đặt N trong ID token.
  Client verify ID token và so N với transaction.

AUTHORIZATION CODE:
  AS tạo code C, TTL ngắn, gắn client/redirect/PKCE.
  Code được tiêu thụ một lần tại token endpoint.
~~~

### 11.1. Không dùng một giá trị cho tất cả tham số

Một implementation có thể nghĩ “đã có random nonce N thì gửi N làm state và code verifier để đỡ tạo ba biến”. Đây là **key/secret reuse và context confusion không cần thiết**. Nên sinh riêng cho từng vai trò theo requirements, lưu đúng thời gian và ràng buộc độc lập. `code_verifier` là **bí mật** tới token exchange; `state` và OIDC nonce có thể xuất hiện qua front-channel.

### 11.2. `state` nên chống CSRF bằng transaction binding

Một `state` khó đoán không có ý nghĩa nếu client:

~~~text
if state.length >= 10:
    acceptCallback()
~~~

Client phải so `state` response với đúng giá trị request đã tạo/bảo vệ, gắn browser session, issuer khi profile cần, kiểm expiry và ngăn các reuse không hợp lệ. State không phải chỉ là “chuỗi bất kỳ có độ dài 10”.

### 11.3. PKCE không thay issuer/audience validation

Một authorization code được đổi thành công bằng đúng verifier chưa chứng minh access token dành cho Orders API hoặc ID token có issuer/audience đúng. Cần validate mỗi loại token theo profile; không dùng PKCE để bỏ các bước đó.

### 11.4. Một code được dùng một lần không đồng nghĩa access token một lần

OAuth authorization code là **single-use credential**, nhưng access token Bearer nhận được từ code đó thường có thể được dùng cho **nhiều API requests** trong lifetime. Đừng áp check-and-consume một lần lên JWT access token chỉ vì code exchange đã dùng nonce/challenge.

## 12. DPoP: proof `jti`, server nonce và chống replay

**DPoP (RFC 9449)** là cơ chế *Demonstrating Proof of Possession* trong OAuth 2.0: client ký một **DPoP proof JWT** bằng private key tương ứng với public key được công bố trong proof. AS/RS kiểm proof và **ràng buộc access token** với key đó khi triển khai sender-constrained token.

DPoP thường xuất hiện ở hai nơi:

1. **Authorization Server/token endpoint**: client gửi proof khi xin/nhận access token bound to key.
2. **Resource Server/API endpoint**: client gửi access token và proof mới ràng buộc method/URI, token hash khi áp dụng.

### 12.1. Các trường trong DPoP proof

Protected header minh họa:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<public-x>",
    "y": "<public-y>"
  }
}
~~~

Payload cho một API call minh họa:

~~~json
{
  "jti": "unique-proof-id-9283",
  "htm": "GET",
  "htu": "https://api.example.com/orders",
  "iat": 1800000000,
  "ath": "<base64url-sha256-of-access-token>",
  "nonce": "<server-issued-nonce-if-required>"
}
~~~

Chỉ dùng placeholder, không phải proof được ký hợp lệ. **`ath`** gắn proof với access token được trình ở resource request; tại token endpoint khi chưa có access token để hash, semantics proof khác. **`nonce` claim** chỉ xuất hiện khi server/profile yêu cầu hoặc cung cấp nonce tương ứng.

### 12.2. Vai trò của từng thành phần

| Thành phần | Tác dụng | Có ngăn replay một mình? |
| --- | --- | --- |
| **DPoP proof signature** | Chứng minh proof được ký bởi private key tương ứng public JWK | Không nếu bản sao proof vẫn trong cửa sổ |
| **`htm`** | Ràng buộc HTTP method | Không nếu cùng method |
| **`htu`** | Ràng buộc URI mục tiêu đã chuẩn hóa theo RFC | Không nếu cùng URI |
| **`iat`** | Giới hạn độ cũ, freshness window | Không nếu proof bị phát lại ngay |
| **`jti`** | Định danh proof duy nhất | Cần **replay tracking** |
| **`ath`** | Ràng buộc proof với access token | Không thay kiểm access token và key binding |
| **`nonce` do AS/RS cấp** | Bổ sung freshness theo chính sách server | Không thay jti/replay checks |
| **Access token `cnf.jkt`** | Ràng buộc access token với thumbprint của DPoP key | Không thay scope/audience/expiry |

### 12.3. DPoP `jti` phải mới theo proof, không phải access token

~~~text
Access token AT1:
  được dùng trong 10 API calls hợp lệ.

DPoP proof cho call #1:
  jti = J1

DPoP proof cho call #2:
  jti = J2

Replay call #1:
  jti = J1   <-- verifier phát hiện trong replay window
~~~

**Không xóa/thu hồi access token AT1 sau call #1** chỉ vì proof J1 là single-use. Access token và DPoP proof có **vòng đời khác nhau**.

### 12.4. DPoP server-provided nonce

Authorization Server hoặc Resource Server có thể yêu cầu client đưa **nonce do server cấp** vào proof. Server có thể cung cấp nonce trong header `DPoP-Nonce` và yêu cầu proof mới theo RFC 9449, chẳng hạn qua error signal `use_dpop_nonce` được profile quy định.

Quan trọng:

- **AS nonce và RS nonce là hai trust domains khác nhau**; client nên quản lý theo đúng origin/endpoint authority, không trộn làm một “global nonce”.
- Server nonce có thể được **cho phép tái sử dụng trong một thời hạn** theo thiết kế; không mặc định mọi DPoP nonce phải được consume một lần. **Proof `jti` vẫn phải unique và được kiểm replay**.
- Client phải gửi proof mới với `nonce` server yêu cầu, **không phát lại nguyên proof cũ** chỉ thay header HTTP.
- Server phải xác minh nonce do **chính nó cấp** (hoặc verifier authority được chia sẻ đúng), TTL và binding/context nếu policy yêu cầu.
- Một nonce có nội dung ký/MAC hay server-side store có thể được dùng để xác minh mà không cần lưu toàn bộ nonce plaintext; nhưng phải chống replay và kiểm lạm dụng đúng model.

### 12.5. Nonce giúp gì khi clock skew?

DPoP proof có `iat` chịu ảnh hưởng đồng hồ client. Nếu đồng hồ sai, server có thể dùng nonce do mình cấp để yêu cầu client tạo proof mới dựa trên thông tin server; tuy nhiên **nonce không cho phép bỏ mọi kiểm tra `iat` hoặc replay theo RFC/profile**. Phải thiết kế validity policy và error recovery cho client, tránh lặp retries vô hạn.

### 12.6. DPoP không chống XSS toàn diện

Nếu attacker có quyền chạy JavaScript trong origin SPA, attacker có thể **yêu cầu ứng dụng/keystore ký proof mới** hoặc thực hiện actions trong user session dù private key không bị export. DPoP giảm token-only replay nhưng không tự chặn XSS, malicious extensions hay token/grant misuse. Vẫn cần XSS hardening, TTL, scope/audience, authorization và revoke.

### 12.7. Quy trình kiểm một DPoP proof tại Resource Server

~~~text
1. Chỉ nhận endpoint/method hợp lệ qua HTTPS.
2. Parse proof theo size/format giới hạn.
3. Kiểm typ=dpop+jwt, JWS alg/key type theo policy.
4. Verify chữ ký bằng public JWK trong proof.
5. Kiểm htm đúng HTTP method, htu đúng target URI theo RFC.
6. Kiểm iat trong cửa sổ chấp nhận; nonce nếu RS yêu cầu.
7. Kiểm ath là hash của access token đang trình.
8. Verify access token issuer, aud, exp, scope, token type.
9. Đối chiếu access token cnf.jkt với DPoP JWK thumbprint.
10. Atomic replay check cho jti trong phạm vi proof key/verifier/window.
11. Kiểm business authorization: tenant, ownership, limits.
12. Allow action hoặc trả lỗi phù hợp, không log raw token/proof.
~~~

**Đây là checklist logic**, không thay validator đầy đủ của RFC 9449. Thứ tự thực tế có thể tối ưu để tránh DoS, nhưng **không được cho request qua chỉ vì `jti` chưa từng thấy**.

## 13. JWT `jti` và nonce: định danh không đồng nghĩa chống replay

JWT có thể chứa claim `jti` (*JWT ID*) theo RFC 7519:

~~~json
{
  "iss": "https://auth.example.com",
  "aud": "orders-api",
  "jti": "access-token-unique-id",
  "scope": "orders.read",
  "exp": 1800000900
}
~~~

`jti` có thể hỗ trợ audit, denylist hoặc correlation, nhưng **chỉ riêng việc có trường `jti` không buộc token dùng một lần**.

### 13.1. So sánh vòng đời

| Credential/proof | Được phép dùng lặp? | Kiểm soát |
| --- | --- | --- |
| **Bearer access token** | Thường **có**, cho nhiều requests trước expiry | `exp`, `aud`, `scope`, revocation, sender binding nếu có |
| **DPoP proof JWT** | **Không** phát lại cùng proof trong replay window | `jti`, `iat`, method/URI, `ath`, nonce server |
| **OIDC ID token** | Được xác minh trong login transaction theo profile; không dùng làm API bearer | Signature, `iss`, `aud`, `exp`, expected nonce |
| **Authorization code** | **Một lần** tại token endpoint | Short TTL, client, redirect, PKCE |
| **Rotated refresh token** | Old value không được dùng lại sau rotation | AS state/rotation family/reuse detection |
| **OAuth Device `device_code`** | Poll **nhiều lần khi pending**, tối đa một exchange thành công | Status, TTL, interval, client binding, atomic consume |

**Một quy tắc “mọi credential xuất hiện lần hai đều là replay” sẽ phá các OAuth flows hợp lệ.** Phải kiểm **đúng semantics của đối tượng**.

### 13.2. Denylist `jti` là trạng thái revoke, không phải proof nonce

Nếu admin revoke JWT access token có `jti=AT7`, RS cần **tra authoritative denylist/version state** để từ chối token trước `exp`. Đây là **bài toán revocation**. Ngược lại, RS dùng replay set của DPoP proof IDs nhằm ngăn **cùng một proof được dùng hai lần**, thường trong một time window hẹp.

Không dùng chung một table hoặc TTL cho access-token revocation và DPoP-proof replay mà không phân namespace/token type/issuer.

### 13.3. Refresh token rotation dùng state ở Authorization Server

Refresh token có thể là opaque hoặc JWT tùy AS. Dù có `jti`/nonce, AS vẫn cần biết **refresh token nào mới nhất/hợp lệ trong rotation chain**. Khi token cũ bị dùng lại, đó có thể là **reuse signal** để xử lý token family. Ký/mã hóa refresh token không tự tạo one-time semantics.

### 13.4. Device authorization không được nhầm nonce

Trong RFC 8628, `device_code` cần là credential ngẫu nhiên đủ khó đoán; thiết bị có thể **poll cùng code nhiều lần** trong trạng thái PENDING, theo `interval`/`slow_down`. Sau khi approval và successful token exchange, AS chỉ cấp tối đa một lần. Đừng áp replay store của DPoP proof `jti` lên mỗi lần device polling.

## 14. Nonce trong TLS: giao thức tự quản lý, không phải ứng dụng tùy chèn

TLS sử dụng nhiều giá trị random/sequence/nonce trong handshake và record protection. Chẳng hạn với **TLS 1.3**, các record AEAD có nonce được dẫn xuất theo quy tắc của TLS, kết hợp per-direction IV và sequence number; ứng dụng không tự cấp IV cho từng TLS record.

~~~text
Application:
  HTTPS request với Bearer token

TLS implementation:
  handshake: key schedule, random shares/values
  record layer: secret keys + unique per-record nonce
  AEAD encrypt/authenticate record
~~~

### 14.1. Không tự thêm `X-Nonce` là có chống replay

Nếu client gửi:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <token>
X-Nonce: random-string
~~~

và RS **không kiểm `X-Nonce` có được ký/MAC, đúng scope và chưa dùng**, attacker có thể sao chép nguyên request hoặc thay `X-Nonce`. Header này **không tự ràng buộc Bearer token với sender**.

### 14.2. TLS 1.3 0-RTT và replay

TLS 1.3 **early data (0-RTT)** có các giới hạn chống replay: early data có thể bị attacker phát lại trong một số điều kiện. Application endpoints có thao tác **không idempotent** (chuyển tiền, tạo đơn hàng, đổi quyền) không nên cho phép 0-RTT bừa bãi. Cần cấu hình server/CDN và business idempotency/replay policy, không suy “TLS có nonces nên mọi HTTP request chắc chắn không replay”.

### 14.3. TLS không bảo vệ token sau khi endpoint đã đọc

Một access token có thể bị lộ từ logs, error tracking, browser memory hoặc service compromise **sau TLS termination**. Nonce nội bộ TLS không chặn kẻ cầm Bearer token trình token qua một TLS session mới. Cần thêm sender constraints/TTL/revocation tùy threat model.

## 15. WebAuthn/passkey: challenge mới được ký với đúng origin/RP

**WebAuthn** là ví dụ điển hình của server challenge trong xác thực người dùng. Relying Party (RP) sinh **challenge khó đoán**, gửi tới client; authenticator tạo một assertion có chữ ký ràng buộc challenge và các thông tin như RP ID, origin, authenticator data, flags/sign counter theo protocol. Server kiểm toàn bộ theo WebAuthn profile.

### 15.1. Luồng ở mức khái niệm

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User + authenticator
    participant B as Browser
    participant RP as Relying Party / Server
    RP->>RP: Sinh challenge C + session + TTL
    RP-->>B: WebAuthn request options chứa C, RP ID
    B->>U: Yêu cầu user presence/verification
    U-->>B: Authenticator assertion đã ký
    B->>RP: clientDataJSON + authenticatorData + signature
    RP->>RP: Kiểm challenge, type, origin, rpIdHash,
    Note over RP: credential public key, UP/UV, counter/policy
    RP->>RP: Consume challenge/session transaction
    RP-->>B: Login được thiết lập theo policy
~~~

### 15.2. Challenge không đủ để thay toàn bộ WebAuthn verification

Một WebAuthn assertion có **challenge đúng** nhưng `origin` sai hoặc `rpIdHash` sai phải bị từ chối. Tương tự, signature sai, credential public key không khớp hoặc user verification requirement không đạt thì không tạo session. Một challenge ngẫu nhiên không thay **origin/RP binding**.

### 15.3. Không tự tạo “passkey protocol” bằng ký nonce trần

Nếu ứng dụng cần passkeys/WebAuthn, hãy dùng thư viện WebAuthn tuân chuẩn, kiểm challenge TTL/single-use, origin, RP ID, credential metadata và user verification. Đừng chỉ nhận `signature=Sign(challenge)` rồi coi tương đương WebAuthn, vì sẽ bỏ qua các ràng buộc chống phishing quan trọng.

## 16. Sinh nonce: chọn entropy và cách biểu diễn theo yêu cầu

**Đầu tiên xác định protocol và tính chất cần thiết**, sau đó chọn generator. Ví dụ:

| Nhu cầu | Cách sinh tham khảo | Cách lưu/truyền | Chú ý |
| --- | --- | --- | --- |
| OIDC nonce | 16–32+ bytes từ CSPRNG, Base64url | Trong auth request, expected value tại client | Ngẫu nhiên, transaction-bound |
| OAuth state | 16–32+ bytes CSPRNG | Auth request/callback, session-bound | Chống đoán và CSRF |
| PKCE code verifier | Theo RFC 7636, entropy cao | Giữ verifier bí mật; gửi challenge trước | Không thay bằng public nonce |
| WebAuthn challenge | Random bytes CSPRNG theo RP policy | WebAuthn options; expected challenge trên server | TTL, origin/RP binding |
| AES-GCM IV | 96-bit random CSPRNG hoặc deterministic unique policy | Có thể đặt cạnh ciphertext | **Uniqueness với cùng key**, hạn số lần |
| DPoP proof `jti` | Unique high-entropy identifier | Trong signed proof JWT | Server anti-replay window |
| Server DPoP nonce | Server-generated theo RFC/profile | Header + proof claim | AS/RS scope riêng, validity policy |
| ECDSA ephemeral `k` | Do crypto library sinh/dẫn xuất theo scheme | **Không xuất ra public message** | Không reuse/lộ, RFC 6979 khi phù hợp |

Các độ dài là **ví dụ/khuyến nghị thiết kế**, không thay giới hạn hoặc MUST của từng RFC. Một AES-GCM IV 12 bytes và một OIDC nonce 32 bytes **không hoán đổi quy tắc** chỉ vì cả hai là random bytes.

### 16.1. Những nguồn tạo nonce không nên dùng

~~~text
new java.util.Random()
Math.random()
currentTimeMillis() without cryptographic design
process ID + timestamp
sequential database ID for unpredictable challenge
UUID derived from non-CSPRNG source without validation
hardcoded nonce = "abc123"
~~~

**`SecureRandom` Java** phù hợp để tạo nonce/challenge ngẫu nhiên. UUID v4 có thể được sinh bằng CSPRNG trong implementation phù hợp, nhưng nếu protocol yêu cầu entropy/high throughput cụ thể, nên sinh **bytes trực tiếp** và encode; không chọn UUID chỉ vì hình thức giống chuỗi khó đoán.

### 16.2. Base64url không bổ sung entropy

Nếu nonce gốc có 8 bits entropy rồi Base64url thành 12 ký tự, entropy **vẫn chỉ 8 bits**. Encoding là cách biểu diễn; an toàn đến từ nguồn random bytes và số lượng bits không thể đoán.

### 16.3. Randomness quality cần đi cùng key lifecycle

CSPRNG tốt không sửa được **nonce reuse do clone VM snapshot**, deterministic counter reset, hoặc nhiều processes chia một key và cùng sequence range. Với AES-GCM, nonce strategy phải được thiết kế theo key domain và failure modes; với challenge replay, server store/TTL và concurrency cũng quan trọng như random generation.

## 17. Java 17: sinh nonce và challenge bằng `SecureRandom`

Một component Java backend có thể dùng `java.security.SecureRandom` để sinh nonce cho **OIDC transaction, OAuth state, WebAuthn challenge hoặc transaction challenge**. Ví dụ:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class SecureNonceFactory {
    private static final int CHALLENGE_BYTES = 32;
    private final SecureRandom secureRandom = new SecureRandom();

    /** 32 random bytes = 256 random bits trước khi encode. */
    public String newChallenge() {
        byte[] bytes = new byte[CHALLENGE_BYTES];
        secureRandom.nextBytes(bytes);
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(bytes);
    }

    public byte[] newGcmIv() {
        byte[] bytes = new byte[12];
        secureRandom.nextBytes(bytes);
        return bytes;
    }
}
~~~

**Không trộn hai phương thức chỉ vì chúng dùng cùng `SecureRandom`:**

- `newChallenge()` trả 32 bytes entropy trước khi Base64url, phù hợp làm ví dụ tạo challenge ngẫu nhiên khó đoán.
- `newGcmIv()` trả IV 96 bit dùng cho một **AES-GCM encryption operation**. Đó mới chỉ là bước sinh IV; hệ thống phải đảm bảo **không trùng trên mọi encryptions dùng cùng key** và tuân quota/rotation. Không dùng hàm này vô hạn mà bỏ kiểm rủi ro collision.

### 17.1. Vì sao không dùng `java.util.Random`?

`Random` không được thiết kế làm **cryptographically secure pseudorandom number generator**. Một attacker quan sát output có thể suy/đoán các output khác trong những điều kiện nhất định. Với challenge cần khó đoán hoặc key-related randomness, dùng CSPRNG như `SecureRandom`, không tự seed bằng timestamp.

### 17.2. Sinh khác nhau cho từng vai trò

~~~java
SecureNonceFactory nonceFactory = new SecureNonceFactory();

String oauthState = nonceFactory.newChallenge();
String oidcNonce = nonceFactory.newChallenge();
String webAuthnChallenge = nonceFactory.newChallenge();

// Ba giá trị khác nhau, mỗi giá trị lưu ở đúng giao dịch.
~~~

Việc cùng **factory** sinh ngẫu nhiên không có nghĩa nên dùng **cùng một kết quả** cho state, nonce và challenge. Có thể cân nhắc domain separation/transaction binding sâu hơn theo protocol, nhưng không tự chế tiêu chuẩn mới.

### 17.3. Không log nonce/challenge kèm nhiều thông tin liên kết

Một số nonce không bí mật nhưng có thể liên kết authorization transaction, client/session/user hoặc làm input cho token exchange. Tránh log raw `state`, OIDC nonce, WebAuthn challenge cùng email/authorization code ở nhiều hệ thống quan sát; ưu tiên **non-secret correlation ID** và event categories.

## 18. Java 17: AES-GCM với IV mới cho mỗi lần mã hóa

Ví dụ dưới đây là **Java 17 JCA**, minh họa nguyên tắc **một random IV mới cho một encryption** bằng AES-GCM và kiểm tag khi decrypt. Nó **không phải JWE implementation**, không chứa key-management hoặc multi-node nonce allocator.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class GcmNonceExample {
    private static final int IV_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final SecureRandom RNG = new SecureRandom();

    public record Envelope(byte[] iv, byte[] ciphertextAndTag) {}

    private GcmNonceExample() {}

    public static Envelope encrypt(
            SecretKey key,
            byte[] plaintext,
            byte[] aad) throws Exception {
        byte[] iv = new byte[IV_BYTES];
        RNG.nextBytes(iv); // fresh IV, mỗi lần encryption.

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
            new GCMParameterSpec(TAG_BITS, iv));
        cipher.updateAAD(aad);

        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        return new Envelope(iv, ciphertextAndTag);
    }

    public static byte[] decrypt(
            SecretKey key,
            Envelope envelope,
            byte[] aad) throws Exception {
        if (envelope == null || envelope.iv() == null
                || envelope.iv().length != IV_BYTES) {
            throw new IllegalArgumentException("Invalid GCM envelope");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
            new GCMParameterSpec(TAG_BITS, envelope.iv()));
        cipher.updateAAD(aad);
        // doFinal kiểm authentication tag; sai thì ném exception.
        return cipher.doFinal(envelope.ciphertextAndTag());
    }

    public static void main(String[] args) throws Exception {
        // Demo: production key phải do KMS/secret manager quản lý.
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey key = generator.generateKey();

        byte[] data = "account=user-42"
            .getBytes(StandardCharsets.UTF_8);
        byte[] aad = "purpose=secure-storage"
            .getBytes(StandardCharsets.UTF_8);

        Envelope envelope = encrypt(key, data, aad);
        byte[] recovered = decrypt(key, envelope, aad);
        System.out.println("Round trip: "
            + Arrays.equals(data, recovered));

        byte[] tampered = envelope.ciphertextAndTag().clone();
        tampered[0] ^= 1;
        try {
            decrypt(key, new Envelope(envelope.iv(), tampered), aad);
            throw new AssertionError("Tampering accepted");
        } catch (AEADBadTagException expected) {
            System.out.println("Authentication tag rejected tampering");
        }
    }
}
~~~

### 18.1. Điều mẫu code không bảo đảm

- **Không có chứng minh collision-free qua hàng tỷ encryptions.** CSPRNG tốt giảm xác suất đụng, không loại bỏ nó; số lần sử dụng dưới mỗi key phải theo security limits.
- **Không có persistent counter/distributed coordination.** Khi nhiều nodes dùng cùng key hoặc clone VM, cần key/nonce policy toàn hệ thống.
- **Không thực hiện JWE, OAuth token signing, DPoP hay OIDC nonce validation.** Đây chỉ là JCA AES-GCM.
- **Không bảo vệ key trong production** vì ví dụ tạo tạm trong process.
- **Không quản lý dữ liệu untrusted quá lớn**; cần giới hạn input length và memory.
- **Không thay business authorization**; giải mã được không chứng minh client được quyền dùng dữ liệu.

### 18.2. Test negative quan trọng

Thử thay **ciphertext**, **tag**, **AAD**, **key**, và các biến thể IV sai → decryption phải từ chối. Đồng thời kiểm thử nonce generator sau **restart, multi-instance, snapshot restore** và theo dõi số lần encrypt/key. **Không cố ý triển khai AES-GCM nonce reuse trên dữ liệu thật để “xem có sao không”.**

## 19. Java 17: replay guard atomic cho một process

Để minh họa replay detection cho **proof IDs** (ví dụ DPoP `jti` sau khi đã xác minh chữ ký và claims), có thể dùng `ConcurrentHashMap.compute` để làm **check-and-insert** nguyên tử trong một JVM.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

public final class LocalProofReplayGuard {
    private final ConcurrentHashMap<String, Instant> seen =
        new ConcurrentHashMap<>();

    /**
     * Trả true khi key chưa tồn tại hoặc entry đã hết cửa sổ.
     * Key đã được canonicalize từ trusted proof context.
     */
    public boolean markFirstUse(
            String replayKey,
            Instant now,
            Duration window) {
        if (replayKey == null || replayKey.isBlank()
                || now == null || window == null
                || window.isZero() || window.isNegative()) {
            throw new IllegalArgumentException("Invalid replay input");
        }

        AtomicBoolean accepted = new AtomicBoolean(false);

        seen.compute(replayKey, (key, expiresAt) -> {
            if (expiresAt != null && expiresAt.isAfter(now)) {
                return expiresAt; // Proof đã được thấy, từ chối.
            }
            accepted.set(true);
            return now.plus(window);
        });

        return accepted.get();
    }

    /** Dọn entry đã hết hạn; production cần giới hạn memory/rate. */
    public void evictExpired(Instant now) {
        seen.forEach((key, expiresAt) -> {
            if (!expiresAt.isAfter(now)) {
                seen.remove(key, expiresAt);
            }
        });
    }
}
~~~

Ví dụ gọi (chỉ sau **DPoP signature + HTTP binding + `iat` + `ath` + key binding validation**):

~~~java
LocalProofReplayGuard replayGuard = new LocalProofReplayGuard();

String replayKey = "trusted-rs/orders/"
    + verifiedDpopKeyThumbprint + "/" + verifiedProofJti;

boolean fresh = replayGuard.markFirstUse(
    replayKey,
    java.time.Instant.now(),
    java.time.Duration.ofMinutes(5)
);

if (!fresh) {
    throw new SecurityException("DPoP proof was already used");
}
~~~

**`verifiedDpopKeyThumbprint` và `verifiedProofJti` là các giá trị được tạo ở lớp xác minh JOSE/DPoP**, không phải biến toàn cục hoặc dữ liệu chưa kiểm. Chuỗi replay key minh họa; production nên canonicalize/encode từng field an toàn, ràng buộc verifier/trust domain, tránh delimiter collisions và không log key thô.

### 19.1. Giới hạn quan trọng của mẫu local

1. **Chỉ atomic trong một process.** Proof J1 gửi đồng thời tới RS node A/B có thể được cả hai chấp nhận nếu mỗi node có map riêng.
2. **State mất khi restart.** Một proof còn trong time window có thể được chấp nhận lại sau restart.
3. **Không có persistence hoặc built-in TTL eviction.** Cần periodic cleanup, max entries, rate limit và memory monitoring để chống DoS.
4. **Window là ví dụ**, không phải 5 phút bắt buộc của RFC 9449; phải phù hợp `iat` acceptance window, nonce policy và clock skew.
5. **Không thay verify chữ ký.** Nếu mark-first-use một `jti` attacker tự khai trước signature validation, attacker có thể làm ô nhiễm replay cache và gây DoS.

### 19.2. Tại sao phải mark nguyên tử?

Sai:

~~~java
// Không atomic: hai threads có thể cùng qua bước containsKey.
if (!seen.containsKey(jti)) {
    seen.put(jti, expiration);
    allow();
}
~~~

Đúng về nguyên tắc: **check-and-insert phải là một thao tác nguyên tử** trên miền có cùng enforcement state. Trong Redis có thể dùng `SET key value NX PX ttl` với schema phù hợp; trong DB có thể dùng unique index/transaction. Với nhiều nodes, chọn một nguồn trạng thái hoặc phân vùng proof routing có bảo đảm đủ mạnh.

## 20. Server-side nonce trong ứng dụng Java: transaction + TTL + consume

Với challenge–response hoặc OIDC authentication transaction, server có thể lưu:

~~~text
ChallengeRecord:
  transaction_id: random opaque reference
  nonce_value_or_secure_digest
  browser_session_id / registered_client_id
  expected_issuer_or_verifier
  target_audience / operation
  expires_at
  status: PENDING | CONSUMED | EXPIRED | CANCELLED
~~~

Đây là **schema minh họa**, không phải table/claim bắt buộc trong RFC. Mỗi record nên gắn đúng **source of truth** và authorization session; không dựa vào một nonce global giữa tất cả users.

### 20.1. Quy trình OIDC callback ở mức pseudocode

~~~text
beginOidcLogin(browserSession):
  state = CSPRNG(32 bytes)
  nonce = CSPRNG(32 bytes)
  verifier = PKCE.createCodeVerifier()
  storePending(state, nonce, verifier, browserSession, issuer, ttl)
  redirectToIssuer(state, nonce, challenge(verifier), ...)

handleCallback(browserSession, response):
  tx = lookupByState(response.state)
  require tx exists && tx.pending && notExpired
  require tx.browserSession == browserSession
  require response.issuer == tx.issuer (when required by profile)
  validateCallbackAndExchangeCodeWithPkce(tx.verifier)
  idToken = verifyIdTokenSignatureIssuerAudienceExpiry(...)
  require idToken.nonce == tx.expectedNonce
  atomicallyMarkTransactionConsumed(tx)
  createApplicationSessionForVerifiedPrincipal()
~~~

### 20.2. Không đơn giản hóa thành “nonce xuất hiện trong response là pass”

Sai:

~~~text
if response.nonce != null:
    loginSuccess()
~~~

Sai tiếp:

~~~text
if idToken.nonce == request.query.nonce:
    loginSuccess()
~~~

Ở ví dụ thứ hai, nếu `request.query.nonce` lấy từ dữ liệu response/client hiện tại thay vì **transaction được tạo trước và bảo vệ**, attacker có thể chọn cả hai phía để chúng bằng nhau. Đúng là so với **expected nonce đã lưu an toàn cho transaction**, sau khi xác minh ID token.

### 20.3. Khi callback bị gửi hai lần

Nếu user refresh callback hoặc attacker replay cùng callback, authorization code thường đã bị consume một lần. Dù vậy server-side transaction phải có trạng thái và không tạo lại application session/grant ngoài mong đợi. **Một callback duplicate không nên hồi sinh transaction đã CONSUMED**.

### 20.4. Hết hạn và cleanup

Khi nonce/transaction hết hạn, phải **không còn được chấp nhận trước cả khi background cleanup xóa dữ liệu**. TTL cleanup chỉ tiết kiệm tài nguyên, không thay điều kiện `now < expires_at` trong đường xác minh.

## 21. Distributed replay defense: nhiều server, nhiều vùng và sự kiện lỗi

Một cluster Resource Servers sau load balancer là môi trường mà **nonce/replay bugs thường không xuất hiện khi test unit nhưng lộ ra ở production**.

~~~mermaid
flowchart TD
    C["Client có proof J1"] --> LB["Load balancer"]
    LB --> A["RS node A"]
    LB --> B["RS node B"]
    A --> R["Shared atomic replay store"]
    B --> R
    R --> D{"J1 đã tồn tại?"}
    D -->|Chưa| F["Insert TTL và chấp nhận một lần"]
    D -->|Rồi| X["Từ chối replay"]
~~~

### 21.1. Check-then-insert là race condition

~~~text
RS A: GET replay:J1 -> absent
RS B: GET replay:J1 -> absent
RS A: SET replay:J1
RS B: SET replay:J1
Both allow -> replay check thất bại.
~~~

Thay thế bằng một thao tác **atomic insert-if-absent** tại authoritative store. Nếu store replicate bất đồng bộ và có failover, cần test **đường chuyển node/region** để chắc rằng cùng proof không được chấp nhận hai lần trong guarantee đã công bố.

### 21.2. Replay cache key cần namespace và binding

Một key có thể biểu diễn:

~~~text
HMAC_SHA256(
  K_cache,
  canonical(
    verifier_trust_domain,
    proof_type,
    authenticated_key_thumbprint,
    jti
  )
)
~~~

`K_cache` là key chuyên dụng cho cache/audit, không phải DPoP private key hay JWT issuer signing key. Schema phải phù hợp RFC và security contract; **không tái dùng key** giữa OIDC nonce, DPoP `jti`, WebAuthn challenge và access-token revocation `jti` khi semantics khác nhau.

### 21.3. TTL và proof validity window

Nếu verifier chấp nhận proofs có `iat` trong cửa sổ \(W\) với clock skew \(\delta\), replay store phải giữ trạng thái **đủ lâu để một proof đã chấp nhận không quay lại và vẫn được chấp nhận trong chính cửa sổ hợp lệ đó**. Không tự dùng TTL 3 giây chỉ vì server xử lý request nhanh nếu proof có thể được accept trong 5 phút.

Khi dùng DPoP nonce server, tương tác giữa nonce validity, proof timestamp và `jti` replay policy phải được thiết kế và test theo RFC; một server nonce có thể chưa hết hạn nhưng proof `jti` cũ **vẫn bị từ chối**.

### 21.4. Fail-open khi store lỗi là nguy hiểm

~~~text
try:
    wasUsed = replayStore.checkAndInsert(jti)
catch timeout:
    wasUsed = false  // SAI: tiếp tục allow khi không biết
~~~

Với endpoint bắt buộc chống replay, nếu authoritative store unavailable, cần **fail closed**, có thể trả dependency error theo API contract. Không coi network timeout là bằng chứng proof chưa từng được dùng.

### 21.5. Snapshot/rollback và network partition

Một replay store có thể mất recent entries khi replica failover; một client/attacker có thể gửi lại proof mà RS nghĩ “chưa thấy”. Cần đánh giá durability/replication/consistency, snapshot restore, monitoring lag và fallback. Không khẳng định “Redis có TTL” là bảo đảm chống replay qua mọi partition.

### 21.6. Rate limiting và cache exhaustion

Nếu server ghi vào replay store **trước khi kiểm signature**, attacker gửi hàng triệu `jti` giả có thể làm đầy memory. Hãy kiểm format/size, signature, key binding và freshness trước; sau đó dùng atomic replay insert có TTL, quotas và resource limits.

## 22. Vòng đời nonce, privacy và observability

Nonce có thể là dữ liệu công khai về mặt mật mã, nhưng **không phải mọi nonce đều nên có mặt trong logs**. Một nonce OIDC có thể liên kết một authorization request với ID token; một WebAuthn challenge gắn với login session; một DPoP proof chứa URI và key thumbprint. Việc thu thập tất cả vào centralized tracing tạo thêm liên kết danh tính không cần thiết.

### 22.1. Định nghĩa vòng đời theo từng mục đích

| Mục đích | Sinh | Kiểm | Kết thúc | Thông tin nên giữ |
| --- | --- | --- | --- | --- |
| **AES-GCM IV** | Mỗi encryption, theo key policy | Khi decrypt cùng IV/tag/AAD | Ciphertext hết retention; nonce quota theo key | IV đi cùng ciphertext, key version, không log secret |
| **OIDC nonce** | Khi tạo auth transaction | Khi verify ID token | Transaction complete/expired/cancelled | Result/category/transaction alias, không cần token raw |
| **OAuth state** | Khi redirect | Khi nhận callback | Consumed/expired | Correlation ID không phải bearer secret |
| **WebAuthn challenge** | Khi bắt đầu operation | Khi verify assertion | Consumed/expired | Audit success/failure, credential alias |
| **DPoP proof `jti`** | Mỗi proof | Khi verify proof tại AS/RS | Hết replay window | Key thumbprint hash/aggregate metrics khi cần |
| **DPoP server nonce** | Khi server yêu cầu | Khi kiểm nonce claim | Hết validity policy | Version/expiry, không ép unique-one-use nếu profile cho reuse |
| **ECDSA ephemeral `k`** | Mỗi signature/deterministic derivation | Nội bộ thuật toán | Không lưu dưới dạng log | Không bao giờ xuất raw `k` |

### 22.2. Không “dọn sau” thay kiểm TTL

Một transaction đã hết hạn phải bị từ chối ngay cả khi cleanup job chưa xóa record. Với AES-GCM, một nonce đã được dùng dưới cùng key **không được dùng lại** vì record log/TTL đã hết; unique requirement gắn với **toàn bộ lịch sử sử dụng khóa**, không phải chỉ cache time window.

### 22.3. Không dùng nonce làm bearer token một cách vô tình

Một challenge ID được yêu cầu trong response có thể trở thành credential nếu backend cho phép:

~~~text
GET /approve?nonce=N -> approve_action()
~~~

Nếu chỉ cần biết N là có thể approve, thì N thực chất đang được sử dụng như **capability token** và phải có security controls tương ứng (entropy, TTL, audience, action, one-time, leak prevention). Với thao tác rủi ro cao, không cho `GET` tự thực hiện side effect và không coi một nonce là bằng chứng user đã xác thực/đồng ý.

### 22.4. Error message không thành oracle

Tùy giao thức, báo chi tiết “nonce N này thuộc user A và đã dùng lúc 10:42” cho caller không xác thực có thể tiết lộ trạng thái user/session. Error client-facing nên tối giản: invalid/expired/replay theo mức cần thiết; chi tiết ở **audit backend được bảo vệ**.

### 22.5. Metrics hữu ích

~~~text
oidc_nonce_mismatch_count
oidc_transaction_expired_count
dpop_proof_replay_rejected_count
dpop_nonce_challenge_count
replay_store_unavailable_count
replay_store_capacity_used
webAuthn_challenge_reused_count
aes_gcm_encryptions_per_key
nonce_allocator_epoch_changes
nonce_collision_or_counter_rollback_alerts
~~~

Không đưa **nonce/JWT/key thumbprint raw** vào metric labels. Theo dõi tỷ lệ lỗi theo **issuer alias, route category, verifier instance, time window** và cảnh báo khi xuất hiện dấu hiệu collision/replay bất thường.

### 22.6. Những giá trị phải tuyệt đối tránh log

- Access token, refresh token, ID token, authorization code, PKCE `code_verifier`;
- JWT client assertion, private signing/decryption keys và ECDSA `k`;
- Raw DPoP proof nếu logs công khai hoặc retention dài;
- Full `Authorization`/cookie headers và query URI chứa transaction data;
- Session store secrets và nonce material khi có khả năng bị dùng như capability.

Nonce AES-GCM có thể nằm công khai cạnh ciphertext theo thiết kế, nhưng **cũng không có lý do đưa cả ciphertext + key ID + user PII vào mọi log event**.

## 23. Nonce reuse và sự khác biệt về mức độ nghiêm trọng

Từ “reuse” có nhiều ngữ nghĩa. Không thể áp cùng một policy cho mọi giao thức:

| Tình huống | Hành vi chuẩn hay lỗi? | Mức rủi ro và cách xử lý |
| --- | --- | --- |
| **Cùng AES-GCM key + IV encrypt hai plaintexts** | **Lỗi nghiêm trọng** | Có thể phá confidentiality/integrity; ngừng dùng key, điều tra |
| **ECDSA dùng lại cùng secret `k` cho hai messages** | **Lỗi nghiêm trọng** | Nguy cơ lộ private key; key compromise response |
| **OIDC ID token nonce không khớp transaction** | **Lỗi bảo mật** | Từ chối login, xem xét injection/replay |
| **OIDC login từ tab A bị kiểm với nonce tab B** | Lỗi ứng dụng/context | Sửa transaction store, không bỏ nonce check |
| **DPoP proof `jti` bị dùng lại trong replay window** | **Replay** theo policy | Từ chối, audit/rate limit |
| **DPoP server nonce xuất hiện ở nhiều proofs mới** | **Có thể hợp lệ** theo server nonce policy | Mỗi proof vẫn cần `jti` mới và đầy đủ validation |
| **Access token Bearer được dùng cho nhiều API calls** | **Thường hợp lệ** | Verify signature/expiry/audience/scope; giám sát bất thường |
| **Rotated refresh token cũ được gửi lại** | **Không hợp lệ** sau rotation | AS reuse detection/token family response |
| **Device code được poll nhiều lần khi PENDING** | **Hợp lệ** theo RFC 8628 | Respect `interval`, `slow_down`, expiry |
| **Authorization code được exchange lần hai** | **Không hợp lệ** | AS từ chối code đã dùng |
| **WebAuthn challenge đã consumed được chấp nhận lại** | **Lỗi replay/state** | Từ chối và xem lại transaction processing |

### 23.1. Vì sao không thể dựa vào từ “nonce” để đánh giá?

Ở AES-GCM, uniqueness là tính chất **của phép mã hóa theo khóa**. Ở DPoP, chống replay là tính chất **của verifier và proof lifecycle**. Ở OIDC, nonce liên kết **một ID token với một transaction**. Một giá trị có cùng hình thức Base64url nhưng mang nghĩa rất khác nhau.

### 23.2. Trạng thái không tồn tại thì không có bằng chứng “chưa dùng”

Một local replay cache sau restart không có entry J1 **không chứng minh J1 chưa từng được dùng**. Một deterministic nonce allocator reset counter sau restore cũng không chứng minh IV mới. Hệ thống cần xử lý **durability/epoch/key rotation** theo guarantee đã chọn.

### 23.3. Nonce không làm token tự thu hồi

Ngay cả khi ID token OIDC nonce đúng hoặc DPoP proof J1 chưa bị replay, access token có thể bị **revoke** hoặc user mất quyền tenant. Resource Server vẫn cần **issuer/audience/scope/time/authorization/revocation checks**, không dùng freshness proof thay trạng thái quyền hiện tại.

## 24. Những sai lầm phổ biến

### 24.1. “Nonce luôn phải bí mật”

**Sai.** Nonce AES-GCM thường công khai; DPoP server nonce/challenge được gửi cho client. Nhiều giao thức đòi **uniqueness/freshness** chứ không cần confidentiality. Nhưng các giá trị như ECDSA secret `k` có yêu cầu bảo mật riêng.

### 24.2. “Nonce chỉ cần random, server không cần lưu gì”

**Sai trong cơ chế đòi chống replay/transaction binding.** Challenge hoặc DPoP proof cần verifier xác thực và quản lý state/window theo model; ngẫu nhiên không tự phát hiện bản sao.

### 24.3. “Counter nonce dễ đoán nên AES-GCM không an toàn”

**Không đúng tổng quát.** Counter nonce theo scheme an toàn có thể phù hợp nếu **không trùng dưới cùng key** và tuân yêu cầu chuẩn. Với challenge cần unpredictable, quy tắc khác.

### 24.4. “Mỗi lần gọi `SecureRandom` thì chắc chắn không trùng”

**Sai.** Random có xác suất collision; cần thống kê/quota/rotation và bảo vệ multi-node/VM snapshot theo algorithm requirement.

### 24.5. “Dùng lại AES-GCM IV chỉ lộ một chút thông tin”

**Sai nghiêm trọng.** Reuse cặp (key, nonce) có thể dẫn đến cả confidentiality và authentication failures. Phải xử lý như lỗi mật mã.

### 24.6. “ECDSA nonce `k` có thể gửi công khai như AES-GCM IV”

**Sai.** ECDSA `k` là **secret signing scalar**. Lộ/dùng lại `k` có thể làm lộ private key.

### 24.7. “OIDC `state` và `nonce` là hai tên cho cùng một thứ”

**Sai.** State ràng buộc authorization response/callback; OIDC nonce ràng buộc **ID token** với authentication request. Cần kiểm đúng nơi.

### 24.8. “Đã dùng PKCE thì không cần kiểm `nonce` nếu client đã gửi”

**Sai.** PKCE chống code interception/substitution; khi OIDC nonce đã được gửi, client phải kiểm claim nonce trong ID token theo profile.

### 24.9. “Access token JWT phải có `nonce` để hợp lệ”

**Sai.** JWT access token validation chủ yếu dựa token profile, issuer, audience, signature, time, scope và policies. OIDC nonce là cơ chế ID token, không phải field mặc định của access token.

### 24.10. “Một DPoP server nonce chỉ được phép dùng cho đúng một request”

**Không mặc định.** Server nonce lifecycle do RFC/profile và policy của AS/RS quyết định; có thể dùng lại trong validity window. **DPoP proof `jti` mới và replay checks** mới là thành phần riêng cần kiểm.

### 24.11. “DPoP `jti` đã mới nên không cần kiểm chữ ký”

**Sai.** Attacker có thể gửi bất kỳ `jti` mới nào. Phải verify proof signature, `htm`, `htu`, `iat`, `ath`, key binding và server nonce khi yêu cầu.

### 24.12. “RS có thể kiểm DPoP replay chỉ bằng map trong một node”

**Sai nếu traffic đi qua nhiều nodes** và không có routing/state guarantee. Cần atomic distributed state hoặc kiến trúc được chứng minh tương đương.

### 24.13. “Nonce header `X-Nonce` tự chặn request replay”

**Sai.** Nếu header không được ký/MAC, không gắn action/session và không được verifier quản lý, attacker có thể sao chép/thay.

### 24.14. “TLS 1.3 có nonce nên 0-RTT request không thể replay”

**Sai.** 0-RTT early data có giới hạn chống replay; phải hạn chế/kiểm request non-idempotent theo protocol và business policy.

### 24.15. “Challenge đúng là WebAuthn assertion hợp lệ”

**Sai.** Còn phải kiểm signature, credential public key, origin, RP ID, user presence/verification flags và policy.

### 24.16. “Nonce hết TTL trong database nên ciphertext AES-GCM được dùng lại IV”

**Sai.** AES-GCM IV uniqueness cần trên **lifetime của encryption key**, không phải TTL của database record.

### 24.17. “Mất replay store thì cứ coi proof mới”

**Nguy hiểm.** Nếu chống replay là yêu cầu bảo mật bắt buộc, outage cần **fail closed** hoặc fallback được chứng minh an toàn.

### 24.18. “Nonce giúp nhận biết user có quyền xóa order”

**Sai.** Nonce có thể góp phần vào freshness/anti-replay, nhưng quyền phải đến từ access token/grant đã verify và resource/business authorization.

## 25. Tình huống thực tế và cách phân tích

**Tình huống A — AES-GCM IV sau mỗi lần restart trở về 0.**

Service mã hóa bằng cùng AES key sau restart và bắt đầu IV counter từ 0.

**Phân tích:** Có thể reuse (key, IV). Cần persistent/unique counter allocation, key-per-epoch hoặc scheme được đánh giá; điều tra ciphertext đã tạo trong khoảng va chạm.

**Tình huống B — Hai pods dùng cùng key nhưng counter độc lập.**

Pod A và B đồng thời mã hóa với nonce `0001` dưới key K.

**Phân tích:** Unique per process **không đủ**. Cần phân vùng nonce space hoặc tách key theo pod/epoch và quản lý rotation.

**Tình huống C — OIDC nonce đúng chữ, sai transaction.**

User mở hai tab; callback A bị so với nonce B do ứng dụng lưu một biến global.

**Phân tích:** Lỗi correlation; dùng per-`state` pending transaction store gắn browser session, không tắt nonce verification.

**Tình huống D — ID token cũ được replay vào login mới.**

Attacker có ID token chưa hết `exp`, đưa vào một transaction khác.

**Phân tích:** Khi OIDC client đã gửi nonce mới, so expected nonce của transaction với claim trong ID token đã verify để từ chối; vẫn cần state/issuer/PKCE.

**Tình huống E — Client gửi `code_verifier` ra URL để “reuse nonce”.**

Verifier có entropy cao nhưng bị đưa vào query logs/browser history.

**Phân tích:** PKCE verifier phải được giữ bí mật đến token exchange, không dùng như public nonce/URL parameter.

**Tình huống F — DPoP proof được gửi lại qua hai API nodes.**

Node A đã chấp nhận proof J1; Node B có replay cache riêng và cũng chấp nhận.

**Phân tích:** Thiếu shared atomic replay state/guarantee. Kiểm time window, key binding và infrastructure failover.

**Tình huống G — Server yêu cầu DPoP nonce nhưng client chỉ thay header.**

Client nhận `DPoP-Nonce=N` và gửi lại proof cũ có `jti=J1` mà không ký proof mới chứa `nonce=N`.

**Phân tích:** Proof không gắn nonce mới và có thể bị replay. Client phải tạo/ký proof mới, `jti` mới, đúng `htm/htu`/`ath` và nonce.

**Tình huống H — DPoP proof mới nhưng access token đã revoke.**

Client còn giữ DPoP private key và tạo proof mới hợp lệ, nhưng grant/access token đã bị AS thu hồi.

**Phân tích:** Sender proof không thay token revocation; RS phải áp state/TTL/revocation policy riêng.

**Tình huống I — Nonce chỉ nằm ngoài thông điệp được ký.**

Attacker lấy signature hợp lệ trên nội dung cố định và tự gắn `nonce=random` ở HTTP header.

**Phân tích:** Nonce không được cryptographically bound với proof; cần đưa nonce/context vào bytes được ký/MAC theo profile.

**Tình huống J — Challenge được ký đúng nhưng chuyển tới một endpoint khác.**

Signer ký một challenge dùng cho “xem hồ sơ”, attacker relay signature tới endpoint “xóa user”.

**Phân tích:** Chỉ nonce không chống confused-deputy/cross-action relay. Phải ràng buộc audience/action/origin, đúng protocol và quyền business.

**Tình huống K — WebAuthn challenge đúng nhưng origin sai.**

Assertion trả về chứa challenge của RP nhưng clientDataJSON origin thuộc phishing domain.

**Phân tích:** WebAuthn verification phải kiểm origin/RP ID, credential signature và flags. Challenge match đơn độc không đủ.

**Tình huống L — TLS 0-RTT replay thao tác tạo đơn hàng.**

Một non-idempotent API nhận early data và tạo hai orders vì cùng request bị phát lại.

**Phân tích:** Hạn chế 0-RTT cho thao tác rủi ro, dùng idempotency/business transaction rules và server/CDN anti-replay theo TLS profile.

**Tình huống M — Access token có `jti=AT1` dùng 10 lần.**

Monitoring báo “token reuse attack” sau lần thứ hai.

**Phân tích:** Access-token `jti` không mặc định one-time. Phân biệt token theft signals với DPoP proof replay và rotated refresh token reuse.

**Tình huống N — Opaque token được introspect active nhưng thiếu audience.**

RS nhận `active=true` nhưng không kiểm token có dành cho API đó.

**Phân tích:** Nonce không liên quan; vẫn cần issuer/audience/scope và token purpose checks, không suy active nghĩa là toàn quyền.

**Tình huống O — Replay guard Redis mất toàn bộ keys sau failover.**

Proof J1 vừa được chấp nhận, entry biến mất ở replica mới, attacker gửi lại trong cửa sổ.

**Phân tích:** Kiểm durability/replication/consistency và hành vi failover; nếu guarantee chống replay mạnh, cần nguồn state đáng tin hoặc fail closed.

**Tình huống P — ECDSA signing nonce bị dùng lại.**

Một thư viện custom sinh `k` từ timestamp, tạo hai signatures với cùng `k`.

**Phân tích:** Có nguy cơ lộ private signing key; xem như signing-key incident, rotate/distrust keys và thay thư viện crypto, không chỉ thay timestamp.

## 26. Ma trận kiểm thử an toàn cho nonce và replay

Một bài kiểm thử đạt cần xác định rõ **protocol, verifier, namespace, time window và expected outcome**. Không chỉ assert “chuỗi có độ dài lớn hơn 20”.

| Test case | Kỳ vọng |
| --- | --- |
| Sinh 1.000 OIDC nonces bằng CSPRNG trong test | Tất cả đúng encoding/length; collision kiểm cảnh báo, không dùng test này làm chứng minh tuyệt đối |
| OIDC nonce lấy từ `Random` seed bằng timestamp | Security review từ chối generator |
| OIDC ID token đã verify và nonce khớp transaction | Có thể tiếp tục các kiểm khác theo OIDC |
| OIDC ID token signature sai nhưng nonce đúng | Từ chối |
| OIDC ID token sai `iss` hoặc `aud` nhưng nonce đúng | Từ chối |
| ID token thiếu `nonce` khi auth request có gửi nonce | Từ chối |
| ID token nonce khác expected nonce | Từ chối |
| OIDC callback state không khớp browser transaction | Từ chối |
| Hai tab OIDC dùng state/nonce/verifier khác nhau | Không trộn transaction |
| OIDC transaction đã CONSUMED được callback lại | Không tạo session mới sai policy |
| OIDC nonce đã expired | Không chấp nhận ID token cho transaction đã hết hạn |
| PKCE verifier bị dùng nhầm làm OIDC nonce | Test flow/hợp đồng nhận diện sai |
| PKCE challenge S256 khác verifier gửi token endpoint | AS từ chối code exchange |
| Authorization code đổi token lần hai | AS từ chối theo one-time semantics |
| AES-GCM encrypt/decrypt với IV/key/AAD đúng | Round trip thành công |
| AES-GCM ciphertext hoặc tag sửa một bit | Decrypt thất bại |
| AES-GCM AAD bị sửa | Decrypt thất bại |
| AES-GCM key sai | Decrypt thất bại |
| AES-GCM IV sai | Decrypt thất bại (xác thực tag không khớp) |
| Counter IV reset sau process restart cùng key | Test uniqueness policy thất bại |
| Hai nodes sinh cùng IV dưới cùng key | Test uniqueness policy thất bại |
| Counter đạt giới hạn hoặc bị overflow | Dừng encrypt/rotate key theo policy, không wrap silently |
| VM snapshot restore có nguy cơ lặp IV | Không tiếp tục encrypt với cùng key/counter chưa bảo đảm |
| Random IV đạt quota encryption/key | Rekey/stop theo NIST/issuer policy |
| ECDSA implementation reuse `k` giữa hai messages | Crypto test/security review thất bại, key compromise response |
| ECDSA `k` bị export/log | Security test thất bại |
| Challenge response signature đúng nhưng context sai | Từ chối |
| Challenge response nonce đã expired/consumed | Từ chối |
| Hai requests cùng challenge đồng thời | Tối đa một consume thành công khi policy single-use |
| Server replay cache kiểm `contains` rồi `put` | Concurrency test phát hiện race |
| DPoP proof có signature sai và `jti` chưa dùng | Từ chối |
| DPoP proof đúng signature, sai `htm` | Từ chối |
| DPoP proof đúng signature, sai `htu` | Từ chối |
| DPoP proof `iat` quá cũ/theo clock policy | Từ chối |
| DPoP proof `ath` không khớp access token | Từ chối |
| DPoP access token `cnf.jkt` không khớp proof JWK | Từ chối |
| DPoP proof `jti` dùng lần hai trong replay window | Từ chối |
| DPoP proof `jti` được dùng đồng thời ở hai RS nodes | Một request được chấp nhận tối đa theo guarantee |
| DPoP server yêu cầu nonce, proof thiếu/sai nonce | Từ chối và gửi challenge/error đúng contract |
| Client nhận server nonce rồi phát lại proof cũ | Từ chối replay hoặc missing nonce |
| Client tạo proof mới với server nonce hợp lệ | Chấp nhận nếu mọi điều kiện khác đạt |
| Server nonce được policy cho reuse trong window | Không false positive chỉ vì nonce lặp; proof `jti` vẫn mới |
| Nonce của AS được gửi tới RS không đúng authority | Từ chối theo nonce domain/binding |
| DPoP replay store unavailable | Fail closed nếu replay check là bắt buộc |
| DPoP cache bị rollback/failover | Không mất guarantee đã công bố |
| Attacker spam proof `jti` chưa verify | Không làm đầy cache vô hạn; validate trước insert |
| Access token Bearer cùng `jti` dùng nhiều API calls hợp lệ | Không tự coi là replay chỉ vì token lặp |
| Refresh token cũ reuse sau rotation | AS phát hiện theo refresh family policy |
| Device code được poll nhiều lần khi PENDING | Cho phép polling theo RFC 8628, không false replay |
| WebAuthn challenge đúng nhưng origin sai | Từ chối |
| WebAuthn challenge đúng nhưng RP ID hash sai | Từ chối |
| WebAuthn challenge đúng nhưng signature/credential key sai | Từ chối |
| WebAuthn challenge cũ bị replay | Từ chối khi consumed/expired |
| TLS 0-RTT non-idempotent API replay | Chặn hoặc idempotently handle theo server/application policy |
| Authorization request chứa state/nonce bị log cùng token | Privacy/security review thất bại |
| API token sai issuer/audience/scope nhưng proof nonce hợp lệ | Resource Server từ chối |
| User mất quyền tenant nhưng proof mới hợp lệ | Resource Server từ chối theo business authorization |

### 26.1. Tầng unit tests

**CSPRNG/encoding:** giá trị đúng bytes/entropy target, Base64url không padding khi profile yêu cầu, không dùng time-only seed.

**AES-GCM:** đúng key/IV/tag/AAD, negative cases, IV allocation strategy theo key, restart và multi-instance.

**Transaction validation:** state/nonce/PKCE mapping, expiry, duplicate callback và concurrent tabs.

**Replay store:** check-and-insert atomic, TTL chính xác, expired entry cleanup, concurrent calls với cùng key, failure handling.

### 26.2. Tầng integration và end-to-end

**OIDC:** authorization redirect → callback → code exchange → ID token signature/claims/nonce validation; test injection ID token của flow khác.

**DPoP:** client tạo proof mới mỗi request, đúng `ath`, `htm`, `htu`, `cnf.jkt` và server nonce nếu yêu cầu; thử replay đến nhiều RS instances.

**WebAuthn:** RP challenge → authenticator assertion → signature/origin/RP ID/flags/counter policy; duplicate challenge.

**TLS/HTTP:** API non-idempotent không dựa vào 0-RTT như anti-replay, các headers do proxy tin cậy thiết lập, không nhận fake nonce như authentication.

**Business API:** sau khi proof pass vẫn kiểm token audience/scope, tenant/object ownership, grant revocation và business idempotency.

### 26.3. Resilience và chaos tests

Thử:

- Restart một node RS khi proof còn trong replay window;
- Redis failover mất recent keys;
- Clock skew giữa AS/RS và client;
- Nhiều pods encrypt cùng AES key;
- Rollback VM snapshot/counter;
- Flood invalid proofs trước signature validation;
- Event/token revocation thay đổi trong lúc proof vẫn fresh;
- Trùng transaction ở hai browser tabs.

**Không dùng production tokens/private keys trong test fixtures.** Security event nên dùng non-secret correlation IDs, ghi outcome có giới hạn thay vì toàn raw proof/nonce.

## 27. Checklist triển khai production

1. **Xác định đúng giao thức:** OIDC nonce, AES-GCM IV, DPoP proof `jti`, DPoP server nonce, WebAuthn challenge và ECDSA signing nonce không cùng semantics.
2. **Xác định thuộc tính cần có:** uniqueness, unpredictability, freshness, one-time consumption và cryptographic context binding.
3. **Xác định uniqueness domain:** per encryption key, per signer, per user transaction, per verifier/key/thumbprint hoặc per authorization grant.
4. **Dùng CSPRNG cho challenge:** entropy đủ, encoding không làm tăng entropy, không sinh từ timestamp/`Random`.
5. **AES-GCM nonce uniqueness:** không tái sử dụng (key, IV), áp quota/key rotation, multi-node counter partition và crash recovery.
6. **Không tự xây chữ ký:** ECDSA `k` phải do crypto library an toàn tạo/dẫn xuất; không log/export `k`.
7. **Gắn nonce vào dữ liệu được bảo vệ:** ký/MAC challenge kèm audience, method/URI/action/session theo profile chuẩn.
8. **Không dùng nonce thay authentication:** kiểm credential, public key, issuer, origin/target và user context.
9. **OIDC `nonce` đúng chỗ:** nếu gửi, verify claim trong ID token đã validate, so với expected value của transaction.
10. **OAuth `state` đúng chỗ:** kiểm callback response và browser session, không đánh đồng OIDC nonce.
11. **PKCE đúng trách nhiệm:** `code_verifier` giữ bí mật tới exchange, `code_challenge` không phải một token dùng để gọi API.
12. **OIDC multi-tab an toàn:** per-state transaction store, TTL và status để không trộn các lần đăng nhập.
13. **DPoP proof validation đầy đủ:** signature, `typ`, `htm`, `htu`, `iat`, `jti`, `ath` và access-token key binding.
14. **DPoP server nonce theo authority:** AS/RS scope riêng, proof mới chứa nonce khi yêu cầu, không mặc định nonce luôn one-time.
15. **Replay tracking nguyên tử:** check-and-insert trên miền verification, không check-then-set race.
16. **Phân tán an toàn:** shared state/routing consistency, failover/rollback policy, không coi local map đủ cho cluster.
17. **TTL đúng cửa sổ:** lưu replay marker đến khi proof không thể được chấp nhận lại; cleanup không thay expiry checks.
18. **Fail closed khi bắt buộc:** replay store/crypto verifier unavailable không biến thành allow.
19. **Chống DoS:** verify format/size/signature trước khi ghi state, quotas/cleanup để không bị cache exhaustion.
20. **WebAuthn profile đầy đủ:** challenge, credential signature, origin, RP ID, user verification và transaction state.
21. **TLS không thay business anti-replay:** 0-RTT restrictions cho non-idempotent requests, idempotency theo nghiệp vụ.
22. **Phân biệt JWT access-token `jti`:** access token thường multi-use; DPoP proof IDs/reused refresh tokens có quy tắc khác.
23. **Không log secrets/proofs:** redact access/refresh/ID tokens, authorization codes, PKCE verifier và raw private keys.
24. **Không đưa nonce vào token authority:** một proof mới không tự cấp scope, audience, tenant hoặc quyền đối tượng.
25. **Kiểm token lifecycle:** issuer, audience, scope, expiry, revocation và sender constraint vẫn bắt buộc theo profile.
26. **Có runbook crypto incident:** GCM nonce collision, ECDSA `k` leak, signing-key compromise và replay-store rollback.
27. **Test concurrency/chaos:** multi-node, multi-tab, snapshot, clock skew, lost state, duplicate requests và traffic spikes.
28. **Đo metrics đúng:** collision/replay rate, cache lag, nonce allocation per key, validation errors; không dùng raw nonce làm label.

## 28. Tài liệu tham khảo

- [NIST SP 800-38D — Recommendation for Block Cipher Modes of Operation: GCM and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): IV uniqueness, authenticated encryption và giới hạn sử dụng GCM.
- [RFC 5116 — An Interface and Algorithms for Authenticated Encryption](https://www.rfc-editor.org/rfc/rfc5116): AEAD interfaces và nonce requirements.
- [RFC 6979 — Deterministic Usage of DSA and ECDSA](https://www.rfc-editor.org/rfc/rfc6979): per-signature ephemeral scalar và deterministic signing.
- [FIPS 186-5 — Digital Signature Standard](https://csrc.nist.gov/pubs/fips/186-5/final): digital signatures và key/nonce security.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): proof `jti`, `iat`, `htm`, `htu`, `ath`, server nonce và key binding.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC Authentication Request `nonce`, ID token verification và response flows.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization request `state`, authorization code, access/refresh token lifecycle.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE `code_verifier`/`code_challenge` và code interception protection.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT `jti`, `iat`, `exp` và token claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): JWT validation, key/algorithm trust và cross-token confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token issuer/audience/type/claims validation.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): OAuth threat model, token theft/replay, client and grant protections.
- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628): `device_code`, `user_code`, polling và one-time token exchange.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): access-token state checks và caller authentication.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): refresh/access-token revocation.
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): record-layer AEAD nonces và 0-RTT replay security considerations.
- [Web Authentication Level 3 — W3C Working Draft](https://www.w3.org/TR/webauthn-3/): RP challenge, authenticator assertion, origin/RP ID verification.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): authentication hardening, sessions và related controls.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): cryptographic algorithms, keys, IVs và implementation hygiene.
- [Java SE 17 — `SecureRandom` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): CSPRNG trong Java.
- [Java SE 17 — `GCMParameterSpec` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): GCM IV/tag parameter handling.

**Ghi nhớ:** Nonce không phải “một chuỗi ngẫu nhiên dùng ở đâu cũng được”. **AES-GCM** đòi IV **không lặp với cùng khóa**; **ECDSA** đòi secret `k` được tạo và bảo vệ đúng scheme; **OIDC nonce** ràng buộc ID token với một authorization transaction; **DPoP proof `jti`** cùng server nonce, timestamp và signature giúp hạn chế replay **khi verifier thực hiện kiểm tra, lưu trạng thái đúng phạm vi và thời hạn**; **WebAuthn challenge** phải đi cùng origin, RP ID và chữ ký. Nonce không thay **PKCE, OAuth state, TLS, JWT issuer/audience/scope validation, revocation hoặc quyền trên tài nguyên**. Muốn chống replay thực sự, phải ràng buộc mật mã với **đúng yêu cầu, đúng bên tham gia, đúng ngữ cảnh và đúng vòng đời**, sau đó kiểm thử cả concurrency, restart và network partition.
