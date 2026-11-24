# Context binding: ràng buộc ngữ cảnh xác thực với request

> **Chương:** Authentication context  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này giải thích cách ràng buộc bằng chứng xác thực với đúng principal, session, client, resource và hành động để ngăn replay, response mix-up, token theft và việc dùng một lần step-up cho một giao dịch khác.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích authentication context và context binding; phân biệt binding mật mã với tín hiệu rủi ro thông thường.
2. Xác định các chiều cần ràng buộc: issuer/subject, client, session, request, resource, action, channel và transaction.
3. Mô tả vai trò của state, nonce, PKCE, WebAuthn challenge, SAML InResponseTo và assertion replay cache.
4. Hiểu token sender-constraining qua DPoP hoặc mutual TLS và giới hạn của từng cơ chế.
5. Thiết kế step-up challenge chỉ dùng được cho đúng account, session và hành động đã yêu cầu.
6. Ràng buộc xác nhận giao dịch với dữ liệu có ý nghĩa, phiên bản và thời hạn cụ thể.
7. Nhận diện các lỗi mix-up, confused deputy, replay, race condition và session fixation.
8. Triển khai mô hình context binding trong Java/Spring và xây dựng ma trận kiểm thử.

## 2. Authentication context là gì?

**Authentication context** là tập hợp thông tin mô tả một sự kiện xác thực và trạng thái phiên mà hệ thống dùng để đưa ra quyết định. Nó có thể gồm:

- **Principal:** danh tính đã được xác minh, thường được xác định bởi issuer và subject.
- **Authentication event:** thời điểm, phương thức và kết quả xác thực.
- **Assurance:** mức bảo đảm hoặc authentication context theo profile đã thỏa thuận.
- **Session:** phiên đang hoạt động, thời điểm tạo, thời điểm xác thực gần nhất và trạng thái thu hồi.
- **Client:** ứng dụng hoặc workload đang yêu cầu truy cập.
- **Resource/audience:** API hoặc tài nguyên mà credential được phát hành cho.
- **Action:** thao tác mà user hoặc service muốn thực hiện.
- **Device/channel:** thiết bị, authenticator hoặc cơ chế bảo vệ token nếu có bằng chứng đáng tin.
- **Risk context:** các tín hiệu như IP, vị trí ước lượng, hành vi và lịch sử bất thường.

Authentication context giúp hệ thống trả lời: ai đã xác thực, bằng phương thức nào, vào lúc nào, trong phiên nào và sự kiện đó có đủ điều kiện cho hành động hiện tại không?

## 3. Context binding là gì?

**Context binding** là việc liên kết một bằng chứng, challenge, token hoặc quyết định xác thực với đúng ngữ cảnh mà nó được tạo ra. Một proof chỉ hợp lệ khi các thuộc tính ràng buộc vẫn khớp.

Ví dụ, An vừa xác thực lại bằng passkey để đổi email khôi phục. Bằng chứng đó cần được gắn với:

- Account của An.
- Session hiện tại của An.
- Client và ứng dụng đang yêu cầu thao tác.
- Hành động CHANGE_RECOVERY.
- Resource/account setting cụ thể.
- Challenge một lần và thời hạn ngắn.

Nếu attacker lấy response của An rồi gửi sang account khác, session khác hoặc dùng nó để phê duyệt giao dịch chuyển tiền, server phải từ chối.

Binding làm giảm nguy cơ một bằng chứng hợp lệ bị dùng sai nơi, sai thời điểm hoặc sai mục đích. Nó không tự cấp quyền: sau khi binding được xác minh, hệ thống vẫn phải kiểm tra authorization.

## 4. Các chiều context cần ràng buộc

| Chiều | Ví dụ | Mục tiêu |
|---|---|---|
| **Identity binding** | issuer + subject | Proof thuộc đúng danh tính |
| **Client binding** | client_id, azp hoặc workload identity | Proof/token thuộc đúng ứng dụng |
| **Session binding** | session ID/version, authentication event | Không dùng proof của phiên khác |
| **Request binding** | state, nonce, PKCE verifier | Response thuộc đúng request khởi tạo |
| **Resource binding** | audience, resource indicator, tenant | Token/proof chỉ dùng tại đúng API/tài nguyên |
| **Action binding** | đổi email, thêm authenticator, approve | Step-up chỉ cho đúng loại thao tác |
| **Transaction binding** | amount, currency, beneficiary, object version | Xác nhận gắn với đúng nội dung giao dịch |
| **Channel/sender binding** | DPoP key, client certificate | Giảm khả năng bên khác tái sử dụng token |
| **Authenticator binding** | WebAuthn credential/public key | Proof đến từ authenticator đã liên kết |
| **Time binding** | challenge expiry, auth_time, token exp | Proof chỉ hợp lệ trong khoảng thời gian cho phép |

Không phải giao thức nào cũng cung cấp mọi chiều. Ứng dụng cần xác định những thuộc tính nào được giao thức bảo vệ bằng mật mã, thuộc tính nào được server lưu và kiểm tra, và thuộc tính nào chỉ là tín hiệu phụ.

## 5. Binding khác gì risk signal?

Đây là phân biệt quan trọng:

- **Cryptographic/protocol binding:** challenge, nonce, chữ ký, audience, session reference hoặc public-key proof được kiểm tra theo giao thức.
- **Server-side binding:** server lưu quan hệ giữa challenge, principal, session, action và transaction rồi kiểm tra lại khi hoàn tất.
- **Risk signal:** IP, ASN, User-Agent, vị trí ước lượng, fingerprint hoặc hành vi giúp phát hiện bất thường nhưng không chứng minh quyền kiểm soát danh tính.

| Dữ liệu | Có thể dùng làm binding mạnh? | Ghi chú |
|---|---|---|
| WebAuthn challenge được ký trong authenticator assertion | Có, theo WebAuthn ceremony | Phải kiểm tra challenge, origin, RP ID và credential |
| OAuth state được lưu và so khớp với browser session | Có, cho request correlation/CSRF defense | State tự nó không chứng minh user identity |
| OIDC nonce được so khớp trong ID token | Có, ràng buộc token với authentication request | Vẫn phải kiểm tra chữ ký, issuer, audience và thời hạn |
| DPoP proof với khóa client | Có, sender-constraining access token theo profile | Không tự ràng buộc nội dung request body |
| IP address | Không | Có thể đổi, dùng chung hoặc đi qua proxy/VPN |
| User-Agent | Không | Dễ giả mạo và không phải secret |
| Device fingerprint | Không nên coi là binding mật mã | Có thể thay đổi, va chạm hoặc bị giả mạo |
| Geolocation | Không | Chỉ là ước lượng/risk context |

Không biến một tín hiệu tiện lợi thành bằng chứng xác thực. Có thể dùng IP hoặc device context để tăng/giảm risk, nhưng không dùng chúng thay challenge signature hoặc token validation.

## 6. Binding trong OAuth và OpenID Connect

Các tham số OAuth/OIDC có vai trò khác nhau:

- **state:** ràng buộc authorization response với request do client khởi tạo; RP cần lưu và so khớp giá trị ngẫu nhiên với browser transaction/session.
- **nonce:** ràng buộc ID token với OIDC authentication request; RP so khớp nonce đã gửi với claim trong ID token.
- **PKCE:** ràng buộc authorization code với client instance nắm code_verifier; authorization server xác minh code_challenge khi đổi code.
- **redirect_uri:** giới hạn nơi authorization response được gửi; phải khớp chính xác redirect URI đã đăng ký.
- **iss, aud, azp:** ràng buộc token với issuer và client nhận token.
- **resource/audience:** giới hạn access token cho resource server dự kiến.

Các cơ chế này bổ sung cho nhau. State không thay PKCE; PKCE không thay issuer/audience validation; nonce không thay chữ ký ID token.

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser
    participant RP as OIDC client
    participant IdP as Authorization server

    RP->>RP: Generate state, nonce and PKCE verifier
    RP->>RP: Store transaction bound to browser session
    RP-->>Browser: Redirect with state, nonce and code_challenge
    Browser->>IdP: Authorization request
    IdP-->>Browser: Redirect with authorization code and state
    Browser->>RP: Callback
    RP->>RP: Verify state against pending browser transaction
    RP->>IdP: Exchange code with code_verifier
    IdP-->>RP: ID token
    RP->>RP: Verify signature, iss, aud, exp and nonce
    RP-->>User: Create authenticated RP session
~~~

RP không nên lưu state chỉ trong một biến JavaScript hoặc tin state do callback tự gửi mà không có giá trị đối chiếu server-side. State phải gắn với đúng browser transaction và được tiêu thụ một lần.

## 7. Binding trong SAML

Trong SAML Web Browser SSO, SP cần liên kết response với AuthnRequest và đúng endpoint:

- **InResponseTo:** response/assertion phải tương ứng với request đang chờ trong SP-initiated flow.
- **Issuer:** phải là IdP đã cấu hình.
- **AudienceRestriction:** phải chứa entity ID của SP.
- **Recipient/Destination:** phải khớp ACS URL dự kiến.
- **Conditions:** NotBefore/NotOnOrAfter phải còn hiệu lực.
- **SubjectConfirmationData:** phải thỏa recipient, thời gian và InResponseTo theo profile.
- **Assertion ID/Response ID:** cần replay cache để không chấp nhận lại cùng response/assertion.

Chữ ký hợp lệ không đủ nếu assertion được phát hành cho SP khác hoặc response đã được dùng. SP phải kiểm tra cả cấu trúc, chữ ký và các ràng buộc giao dịch.

## 8. Binding trong WebAuthn/passkey

WebAuthn sử dụng challenge do RP tạo và authenticator ký trong assertion. Challenge giúp ràng buộc proof với một yêu cầu cụ thể.

Khi xác minh assertion, server kiểm tra:

1. Challenge khớp giá trị đang chờ của đúng account/session.
2. Challenge chưa hết hạn và chưa được tiêu thụ.
3. Client data type là webauthn.get.
4. Origin đúng origin được RP cho phép.
5. RP ID hash khớp RP ID.
6. Credential ID thuộc account và đang active.
7. Chữ ký hợp lệ với public key đã lưu.
8. User presence/user verification flags đáp ứng policy.
9. Sign counter hoặc backup state được xử lý theo đặc tính authenticator và policy, không dùng một quy tắc cứng cho mọi passkey sync.

Challenge phải được tạo mới cho mỗi ceremony. Không dùng một challenge cố định trong nhiều lần xác thực và không chấp nhận response của account/session khác.

## 9. Session binding và authentication event

Một proof xác thực có thể hợp lệ nhưng không còn phù hợp với session hiện tại. Ví dụ, user đã step-up trong một tab, sau đó đăng xuất, đổi account hoặc chuyển sang session khác.

Server có thể lưu authentication context trong session:

- Principal key: issuer + subject hoặc account ID đã ánh xạ.
- Session ID hoặc session version.
- Authentication event ID.
- Authenticated-at/auth_time.
- Method và assurance đã xác minh.
- Client/application và audience.
- Step-up purpose/action.
- Thời hạn hiệu lực của step-up grant.

Khi login hoặc thay đổi privilege, nên rotate session ID và vô hiệu ID cũ. Khi logout hoặc nghi compromise, revoke session phía server. Không chỉ dựa vào cookie còn tồn tại ở browser.

### Không dùng session ID thô làm dữ liệu audit

Nếu cần correlation, dùng identifier nội bộ hoặc hash có kiểm soát; không log cookie/session secret. Session ID là bearer credential và log thường có phạm vi truy cập rộng hơn session store.

## 10. Step-up binding: xác thực lại cho đúng hành động

Một step-up grant không nên chỉ là boolean mfa=true. Nó phải nói rõ:

- Ai đã hoàn tất step-up?
- Trong session nào?
- Dùng phương thức/assurance nào?
- Hoàn tất lúc nào?
- Cho hành động/resource nào?
- Có ràng buộc transaction cụ thể không?
- Hạn dùng và trạng thái đã sử dụng ra sao?

Ví dụ, An xác thực lại để thêm passkey. Step-up grant này không được dùng để đổi email, thêm tài khoản ngân hàng hoặc phê duyệt giao dịch.

~~~text
Step-up grant:
  principal = issuer + subject
  session = current server session
  action = AUTHENTICATOR_ENROLL
  resource = account security settings
  assurance = phishing-resistant
  authenticated_at = recent timestamp
  expires_at = short deadline
  consumed = false
~~~

Server phải kiểm tra grant ở endpoint đích và tiêu thụ nó nguyên tử khi hoàn tất thao tác. Nếu request retry, cần idempotency có chủ đích; không cho phép một grant được dùng để hoàn tất nhiều thao tác khác nhau.

## 11. Transaction binding

Với hành động có tác động tài chính hoặc dữ liệu lớn, chỉ ràng buộc user và session có thể chưa đủ. Cần gắn challenge với nội dung giao dịch.

Ví dụ giao dịch chuyển tiền:

~~~text
transaction_context:
  account_id = A-104
  action = TRANSFER
  amount = 25000000
  currency = VND
  beneficiary_id = B-205
  transaction_version = 7
  nonce = random-one-time-value
  expires_at = short-deadline
~~~

Server tạo digest từ biểu diễn canonical của các trường quan trọng. Khi user xác nhận, server:

1. Đọc giao dịch từ nguồn dữ liệu server-side.
2. Tạo lại canonical representation và digest.
3. So sánh digest với context đã được challenge.
4. Xác minh proof và principal/session binding.
5. Kiểm tra giao dịch chưa thay đổi, chưa hết hạn và chưa hoàn tất.
6. Tiêu thụ challenge/grant nguyên tử và thực hiện giao dịch.

Nếu số tiền, người nhận, currency hoặc transaction version thay đổi, challenge cũ phải mất hiệu lực và cần xác nhận lại.

### Challenge binding không tự bảo đảm trusted display

WebAuthn challenge có thể ràng buộc chữ ký với digest do server tạo, nhưng authenticator thông thường không hiển thị chi tiết giao dịch trên màn hình đáng tin cậy. Nếu browser bị XSS, nội dung hiển thị có thể bị thay đổi dù challenge vẫn được ký.

Vì vậy, phân biệt:

- **Server-side transaction binding:** proof chỉ hợp lệ cho digest giao dịch cụ thể.
- **User intent/trusted confirmation:** người dùng thực sự nhìn thấy và xác nhận đúng người nhận/số tiền trên một giao diện đáng tin cậy.
- **Transaction signing:** cơ chế chuyên dụng ký nội dung giao dịch, nếu hệ thống yêu cầu assurance cao hơn.

Không tuyên bố WebAuthn tự động ký hoặc hiển thị mọi chi tiết giao dịch chỉ vì challenge chứa transaction hash.

## 12. Sender-constrained tokens: DPoP

Access token dạng bearer có thể bị dùng bởi bất kỳ bên nào lấy được token. **DPoP (Demonstrating Proof of Possession)** bổ sung proof-of-possession để ràng buộc việc sử dụng token với một public/private key của client.

Ở mức khái niệm:

1. Client tạo key pair và giữ private key.
2. Client gửi DPoP proof JWT kèm request token hoặc resource request.
3. Proof chứa các thông tin như HTTP method (htm), target URI (htu), thời điểm phát hành (iat), unique identifier (jti), hash access token (ath) khi gửi tới resource server và có thể có server nonce.
4. Resource server xác minh proof và thumbprint của public key phải khớp confirmation claim (cnf/jkt) trong access token.
5. Server kiểm soát replay của proof theo jti/nonce và time window.

DPoP giúp token bị sao chép khó sử dụng ở client khác nếu attacker không có private key. Nhưng nếu endpoint bị compromise và attacker có thể gọi signing key, DPoP không bảo vệ được khỏi chính endpoint đó.

DPoP proof ràng buộc method và URI theo profile; **không mặc định ký request body**. Nếu cần bảo vệ nội dung giao dịch, cần transaction binding riêng.

## 13. Sender-constrained tokens: mutual TLS

OAuth mutual TLS có thể ràng buộc access token với client certificate. Token có thể mang confirmation claim với thumbprint certificate, ví dụ cnf.x5t#S256 theo profile.

Resource server kiểm tra:

- TLS client certificate đã được xác minh theo trust store/policy.
- Thumbprint certificate trong token khớp certificate của kết nối hiện tại.
- Issuer, audience, expiry và scope của token vẫn hợp lệ.
- Certificate chưa bị thu hồi hoặc hết hạn theo PKI policy.

mTLS hữu ích cho workload/service-to-service hoặc môi trường quản lý thiết bị. Nó có thể phức tạp ở browser/mobile và qua reverse proxy; phải xác định rõ proxy nào xác minh certificate và cách chuyển thông tin đã xác minh tới backend mà không cho client tự giả mạo header.

DPoP và mTLS giảm rủi ro bearer-token replay từ một bên không có private key/certificate tương ứng. Chúng không thay authorization, token lifetime, revocation hoặc bảo vệ endpoint.

## 14. Channel binding và giới hạn của TLS

TLS bảo vệ tính bí mật và toàn vẹn dữ liệu trên đường truyền giữa các điểm kết thúc TLS. Tuy nhiên, TLS không tự ràng buộc một access token với một browser session hoặc một giao dịch nghiệp vụ.

Phân biệt:

- **Transport protection:** HTTPS bảo vệ request/response trên kết nối.
- **Channel binding:** liên kết bằng chứng với một kênh cụ thể theo cơ chế/protocol có định nghĩa.
- **Sender-constrained token:** token chỉ được sử dụng khi client chứng minh nắm khóa/certificate tương ứng.
- **Application context binding:** server gắn proof với account/session/action/resource/transaction.

Nếu TLS kết thúc tại load balancer, backend không nên tin header client-certificate do internet client tự gửi. Chỉ tin metadata được proxy tin cậy xác minh, loại bỏ header giả từ bên ngoài và bảo vệ kênh proxy-to-backend.

Không tự chế một scheme dựa trên TLS session ID hoặc IP để gọi đó là channel binding. Dùng cơ chế chuẩn và thư viện được duy trì.

## 15. Replay, mix-up và confused deputy

### Replay

Attacker ghi lại một response/challenge/proof hợp lệ rồi gửi lại.

Kiểm soát:

- Challenge/nonce ngẫu nhiên, ngắn hạn và dùng một lần.
- Lưu trạng thái đã tiêu thụ phía server.
- Kiểm tra jti/nonce của DPoP và replay cache.
- Dùng assertion ID/response ID cache trong SAML.
- Token lifetime ngắn và sender-constraining khi phù hợp.

### Mix-up

Response từ một issuer/client/request bị nhầm sang luồng khác. Ví dụ RP có nhiều IdP nhưng không ràng buộc issuer và transaction state.

Kiểm soát:

- Lưu issuer/authorization server dự kiến trong transaction.
- Kiểm tra iss, aud, azp và redirect URI.
- Ràng buộc state/nonce với browser session và client.
- Không chọn IdP dựa trên claim chưa xác minh trong response.

### Confused deputy

Một service có quyền rộng bị client lợi dụng để hành động thay họ trong resource hoặc tenant khác.

Kiểm soát:

- Ràng buộc subject và actor rõ ràng.
- Kiểm tra audience/resource và scope.
- Không dùng service credential rộng để bỏ qua authorization user.
- Ghi audit cả actor service lẫn subject được đại diện.
- Ràng buộc transaction/action với request đã được ủy quyền.

## 16. Race condition và atomic consumption

Một challenge có thể được gửi đồng thời tới hai request. Nếu hệ thống kiểm tra trạng thái trước rồi mới cập nhật sau, cả hai request có thể cùng thấy challenge còn pending và cùng thành công.

Thiết kế cần:

- Challenge có trạng thái pending, consumed, expired hoặc revoked.
- Chuyển pending → consumed bằng thao tác atomic/conditional update.
- Transaction DB hoặc compare-and-set/row lock để ngăn hai consumer.
- Unique constraint cho transaction/action idempotency key phù hợp.
- Kiểm tra session và account state trong cùng giao dịch hợp lý.
- Không khôi phục challenge consumed khi retry hoặc timeout không rõ kết quả.

Một proof hợp lệ chỉ nên tạo ra một kết quả được chấp nhận cho đúng mục đích đã định.

## 17. Java: mô hình challenge gắn với context

Ví dụ dưới đây minh họa cách lưu challenge đã hash và ràng buộc nó với account, session, action, resource và transaction digest. Việc xác minh chữ ký WebAuthn thực tế phải do thư viện chuẩn thực hiện.

~~~java
record BoundContext(
    UUID accountId,
    String issuer,
    String subject,
    String sessionId,
    String clientId,
    String audience,
    String action,
    String resourceId,
    String transactionDigest
) {}

record PendingChallenge(
    UUID id,
    byte[] challenge,
    byte[] contextHash,
    Instant expiresAt,
    String status
) {}

record StepUpGrant(
    UUID id,
    byte[] contextHash,
    Instant expiresAt,
    boolean consumed
) {}
~~~

Server xây dựng context từ principal/session đã xác minh và dữ liệu transaction đọc từ backend. Không lấy accountId, subject, amount hoặc beneficiary chỉ từ body rồi coi đó là dữ liệu có thẩm quyền.

### Tạo challenge

~~~java
@Service
class BoundChallengeService {
    private final SecureRandom random = new SecureRandom();
    private final ChallengeRepository challenges;
    private final ContextHasher contextHasher;

    BoundChallengeService(
            ChallengeRepository challenges,
            ContextHasher contextHasher) {
        this.challenges = challenges;
        this.contextHasher = contextHasher;
    }

    byte[] begin(BoundContext context) {
        byte[] challenge = new byte[32];
        random.nextBytes(challenge);

        byte[] contextHash = contextHasher.hashCanonical(context);

        challenges.savePending(
            challenge,
            contextHash,
            Instant.now().plusSeconds(180)
        );
        return challenge;
    }

}
~~~

Challenge thô chỉ được trả về cho browser để đưa vào WebAuthn options; server có thể lưu challenge trong pending record có TTL để verifier đối chiếu. Challenge là nonce dùng một lần, không phải credential đăng nhập, nhưng vẫn không nên log hoặc tái sử dụng. Không log session secret hoặc token. ContextHasher phải canonicalize trường theo thứ tự và encoding xác định, tránh hash JSON tùy ý có thứ tự/biểu diễn không ổn định.

### Hoàn tất challenge

~~~java
@Transactional
StepUpGrant complete(
        UUID challengeId,
        BoundContext currentContext,
        WebAuthnAssertion assertion) {

    PendingChallenge pending = challenges.lockPending(challengeId)
        .orElseThrow(InvalidChallengeException::new);

    if (!"PENDING".equals(pending.status())
            || pending.expiresAt().isBefore(Instant.now())) {
        throw new InvalidChallengeException();
    }

    byte[] currentContextHash =
        contextHasher.hashCanonical(currentContext);

    if (!MessageDigest.isEqual(
            pending.contextHash(), currentContextHash)) {
        throw new InvalidChallengeException();
    }

    webAuthnVerifier.verify(
        assertion,
        currentContext.accountId(),
        pending.challenge()
    );

    challenges.consumeAtomically(challengeId);
    return grants.create(
        currentContextHash,
        Instant.now().plusSeconds(120)
    );
}
~~~

Đây là pseudocode ở mức kiến trúc: verifier phải nhận và xác minh challenge đúng theo WebAuthn protocol, bao gồm origin, RP ID, credential, signature và flags. Trong code production, phải xác minh challenge đúng định dạng byte đã gửi, bảo đảm consumeAtomically là conditional update chỉ thành công một lần và xử lý rollback/transaction semantics rõ ràng.

### Dùng step-up grant

Endpoint thực hiện hành động phải dựng lại context từ trạng thái server-side, so khớp context hash, kiểm tra expiry và tiêu thụ grant một lần. Nếu transaction thay đổi sau step-up, hash mới không khớp và phải yêu cầu challenge mới.

## 18. Java/Spring: kiểm tra authentication context

Trong ứng dụng Spring, principal đã xác minh nên được lấy từ SecurityContext, còn session context từ server/session repository. Không tạo authentication context bằng cách tin các field trong request body.

~~~java
record AuthenticationContext(
    String issuer,
    String subject,
    String sessionId,
    Instant authenticatedAt,
    Set<String> methods,
    String assurance
) {}

void requireFreshStepUp(
        AuthenticationContext context,
        Duration maximumAge) {

    Instant cutoff = Instant.now().minus(maximumAge);
    if (context.authenticatedAt() == null
            || context.authenticatedAt().isBefore(cutoff)) {
        throw new InsufficientAuthenticationException(
            "Recent authentication is required"
        );
    }
}
~~~

Đây là ví dụ khung. Assurance/methods chỉ được điền sau khi xác minh token/assertion và semantics của issuer. Không coi claim acr/amr tùy ý là một mức chuẩn nếu chưa có hợp đồng. Nếu dùng OIDC, phân biệt auth_time với iat; nếu yêu cầu xác thực gần đây, có thể yêu cầu max_age và kiểm tra auth_time theo policy.

## 19. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Dùng một boolean mfa=true cho mọi thao tác | Step-up có thể bị dùng sai mục đích | Grant gắn principal/session/action/resource và expiry |
| Không ràng buộc challenge với session | Proof có thể chuyển sang session khác | Lưu session reference/version server-side |
| Dùng challenge cố định | Replay dễ dàng | Nonce ngẫu nhiên, một lần, ngắn hạn |
| Chỉ kiểm tra state mà không lưu đối chiếu | Response injection/mix-up | State server-side gắn browser transaction |
| Coi PKCE thay nonce/state | Thiếu các ràng buộc OIDC khác | Dùng đúng vai trò từng tham số |
| Chỉ kiểm tra chữ ký token | Token có thể dành cho client/resource khác | Kiểm tra issuer, audience, client và profile |
| Dùng IP làm device binding | Người dùng hợp lệ bị khóa; attacker có thể dùng proxy | IP chỉ là risk signal |
| Dùng DPoP như ký toàn bộ request body | Hiểu sai phạm vi proof | Transaction binding riêng khi cần bảo vệ body |
| Coi TLS là session binding | Token bị sao chép vẫn có thể dùng ở kết nối khác | Sender-constrained token hoặc server-side binding |
| Challenge transaction không chứa version/digest | Giao dịch có thể thay đổi sau xác nhận | Bind canonical digest và transaction version |
| Không tiêu thụ challenge atomic | Hai request đồng thời cùng thành công | Lock/conditional update/unique constraint |
| Không kiểm tra authorization sau binding | Proof hợp lệ bị biến thành quyền quá rộng | Authorization theo principal/resource/action |
| Tin User-Agent/fingerprint là danh tính | Dễ giả mạo và tạo false positive | Dùng bằng chứng mật mã và policy server-side |

## 20. Ma trận kiểm thử context binding

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Proof của account A gửi cho account B | Từ chối |
| Proof của session cũ gửi trong session mới | Từ chối |
| Step-up grant cho ADD_AUTHENTICATOR dùng cho TRANSFER | Từ chối |
| Challenge hết hạn | Từ chối |
| Challenge đã consumed được gửi lại | Từ chối |
| Hai request đồng thời tiêu thụ cùng challenge | Chỉ một request thành công |
| OIDC state không khớp browser transaction | RP từ chối |
| OIDC nonce không khớp ID token | RP từ chối |
| PKCE verifier sai | Authorization server từ chối đổi code |
| ID token sai issuer/audience | RP từ chối |
| SAML InResponseTo không khớp | SP từ chối |
| SAML assertion ID đã xuất hiện trong replay cache | SP từ chối |
| WebAuthn origin hoặc RP ID sai | RP từ chối |
| DPoP proof dùng sai method hoặc URI | Resource server từ chối |
| DPoP jti bị replay hoặc nonce sai | Resource server từ chối theo policy |
| Access token cnf không khớp DPoP key | Resource server từ chối |
| mTLS certificate thumbprint không khớp token | Resource server từ chối |
| IP thay đổi nhưng proof mật mã và policy hợp lệ | Không tự động coi proof vô hiệu chỉ vì IP đổi |
| Transaction amount/beneficiary thay đổi sau challenge | Challenge cũ không còn hợp lệ |
| Transaction version thay đổi giữa step-up và commit | Từ chối hoặc yêu cầu xác nhận lại |
| Context hash được tính từ dữ liệu client tự khai | Test phải chứng minh server dùng dữ liệu authoritative |
| Challenge response hợp lệ nhưng user thiếu quyền resource | Authorization vẫn từ chối |
| Session bị revoke sau khi tạo challenge | Challenge không thể hoàn tất |
| Token bị đánh cắp nhưng không có sender key | Sender-constrained validation từ chối |

Kiểm thử cả đường thành công, replay, retry, timeout, race condition, account switch và transaction mutation. Dùng key, token, session và dữ liệu giao dịch giả lập trong môi trường test.

## 21. Tình huống phân tích

### Tình huống A: step-up bị dùng cho giao dịch khác

An xác thực lại để thay email recovery. Một endpoint khác chỉ kiểm tra cờ MFA gần đây và cho phép An chuyển tiền giá trị cao mà không yêu cầu xác nhận riêng.

**Phân tích:** step-up không được ràng buộc với action/resource. Tạo grant riêng cho từng mục đích; giao dịch chuyển tiền cần challenge gắn với người nhận, số tiền, currency và transaction version.

### Tình huống B: authorization response bị gửi nhầm

RP hỗ trợ nhiều IdP nhưng callback chỉ kiểm tra code tồn tại, không gắn state với issuer và browser session.

**Phân tích:** có nguy cơ mix-up/login CSRF. Lưu transaction server-side gồm issuer dự kiến, state, nonce, PKCE verifier và browser session; xác minh đầy đủ trước khi tạo local session.

### Tình huống C: bearer token bị sao chép

Attacker lấy access token từ log và dùng từ một máy khác trước khi token hết hạn.

**Phân tích:** token bearer không ràng buộc người gửi. Redact log, revoke token nếu có thể, giảm lifetime và cân nhắc DPoP/mTLS cho client phù hợp.

### Tình huống D: challenge được dùng hai lần

Hai request hoàn tất cùng một enrollment challenge gần như đồng thời. Cả hai cùng đọc trạng thái pending trước khi cập nhật.

**Phân tích:** kiểm tra và consume phải atomic. Dùng lock/conditional update và chỉ cho một transition pending → consumed.

### Tình huống E: giao dịch đổi người nhận sau xác nhận

User xác nhận chuyển tiền cho B-205. Trước khi commit, một request khác thay beneficiary thành B-999 nhưng vẫn dùng step-up grant cũ.

**Phân tích:** grant phải ràng buộc transaction digest/version. Trước commit, server đọc lại dữ liệu authoritative và xác minh digest; nếu thay đổi, yêu cầu xác nhận mới.

## 22. Quy trình thiết kế và vận hành

Trước khi phát hành authentication context binding, hãy xác định:

1. Principal được xác định bằng issuer + subject hoặc account mapping nào?
2. Client, session, resource, action và tenant nào phải nằm trong context?
3. Giao thức cung cấp state, nonce, PKCE, challenge hoặc sender proof nào?
4. Những giá trị nào được lưu server-side và tiêu thụ một lần?
5. Challenge có entropy, TTL, replay protection và concurrency control ra sao?
6. Step-up grant có purpose, assurance, auth_time và expiry không?
7. Giao dịch có canonical representation, digest và version không?
8. Có cần DPoP hoặc mTLS sender-constrained token cho client/API không?
9. Token audience, issuer, scope, token type và confirmation claim được kiểm tra thế nào?
10. IP/device/behavior signals có được dùng đúng vai trò risk context không?
11. Khi session, account, authenticator hoặc quyền bị revoke, challenge/grant liên quan được xử lý ra sao?
12. Có bảo vệ CSRF, mix-up, confused deputy, replay và race condition không?
13. Audit có correlation ID và reason code mà không ghi token, cookie, private key hoặc challenge secret không?
14. Có diễn tập account switch, session switch, transaction mutation và token theft không?

## 23. Ghi nhớ trọng tâm

- **Context binding gắn proof với đúng ngữ cảnh.** Principal, client, session, resource, action và thời gian phải được kiểm tra theo yêu cầu.
- **State, nonce và PKCE có vai trò khác nhau.** Dùng kết hợp đúng giao thức; không coi một tham số thay thế mọi kiểm soát còn lại.
- **Challenge phải ngẫu nhiên, ngắn hạn, một lần và được lưu phía server.** Ràng buộc challenge với account/session/action/resource.
- **Step-up không phải boolean dùng chung.** Grant chỉ áp dụng cho đúng mục đích và phải được tiêu thụ có kiểm soát.
- **Transaction binding cần digest/version từ dữ liệu server-side.** Nếu người nhận, số tiền hoặc nội dung thay đổi, yêu cầu xác nhận mới.
- **DPoP và mTLS ràng buộc token với khóa/certificate của sender.** Chúng giảm token replay nhưng không bảo vệ endpoint đã bị compromise.
- **IP, User-Agent và fingerprint là risk signals, không phải bằng chứng mật mã.**
- **Binding không thay authorization.** Sau khi proof hợp lệ, vẫn kiểm tra quyền trên resource và tenant.
- **Replay và race condition cần xử lý nguyên tử.** Một challenge không được hoàn tất hai lần.

Authentication context chỉ có giá trị khi hệ thống biết nó thuộc về ai, được tạo trong phiên nào, dành cho resource và hành động nào, và còn hiệu lực đến khi nào. Binding đúng giao thức cùng với trạng thái server-side, sender-constrained token khi phù hợp và authorization riêng sẽ làm giảm đáng kể nguy cơ replay, mix-up và lạm dụng bằng chứng xác thực hợp lệ.
