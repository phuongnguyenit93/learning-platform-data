# Replay attack — Nhận diện và ngăn phát lại thông điệp xác thực

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích replay attack, phân biệt tính toàn vẹn với tính mới của bằng chứng, thiết kế nonce/challenge/counter và replay cache, đồng thời bảo vệ token, assertion, OTP, API request và giao dịch khỏi việc bị phát lại.

> **Chương:** Chống replay  
> **Chủ đề:** Replay attack  
> **Phạm vi:** Security Authentication Fundamentals — hiểu cách thông điệp xác thực hợp lệ bị ghi lại và phát lại, thiết kế freshness, nonce, challenge, counter, one-time consumption và idempotency; bảo vệ token, session, federation và giao dịch khỏi replay.

## 1. Replay attack là gì?

**Replay attack** là kiểu tấn công trong đó kẻ tấn công ghi lại một thông điệp, proof, token hoặc request từng hợp lệ rồi gửi lại để hệ thống thực hiện hoặc chấp nhận nó lần nữa. Nội dung được phát lại có thể vẫn giữ nguyên chữ ký hoặc MAC hợp lệ, nhưng đã cũ, đã được sử dụng hoặc không còn thuộc giao dịch hiện tại.

Ví dụ: Người dùng xác nhận một giao dịch chuyển tiền bằng challenge hợp lệ. Attacker ghi lại request xác nhận và gửi lại nhiều lần. Nếu server chỉ kiểm tra chữ ký mà không ghi nhận challenge đã dùng, một xác nhận có thể bị thực thi nhiều lần.

Replay có thể nhắm vào:

- Password hoặc OTP được gửi qua kênh xác thực;
- Challenge-response và chữ ký thiết bị;
- Authorization code, ID token hoặc assertion liên kết;
- API request đã ký;
- Cookie/session token hoặc bearer access token bị đánh cắp;
- Recovery link, reset token và invitation;
- Lệnh nghiệp vụ có side effect như chuyển tiền, cấp quyền hoặc tạo tài nguyên.

Replay không nhất thiết làm attacker biết bí mật ban đầu. Attacker chỉ cần lấy được một thông điệp hợp lệ và tìm cách khiến hệ thống chấp nhận lại nó trong ngữ cảnh khác hoặc ở thời điểm khác.

## 2. Replay khác gì với các kiểu tấn công khác?

| Kiểu tấn công | Cách hoạt động | Khác biệt chính |
| --- | --- | --- |
| **Replay** | Gửi lại thông điệp/proof đã từng hợp lệ | Tận dụng việc hệ thống không nhận ra bằng chứng cũ |
| **Forgery** | Tạo thông điệp hoặc chữ ký giả | Cố tạo bằng chứng mới mà không có khóa hợp lệ |
| **Tampering** | Sửa nội dung request/token | Thay đổi dữ liệu trên đường truyền hoặc trong storage |
| **Phishing** | Lừa người dùng cung cấp credential hoặc approve | Lấy bằng chứng mới từ người dùng qua giao diện giả |
| **Credential stuffing** | Thử credential bị lộ từ dịch vụ khác | Dùng cặp username/password đã biết |
| **Session hijacking** | Chiếm cookie/token/session đang hoạt động | Dùng quyền của session hợp lệ; có thể bao gồm replay token |
| **Relay attack** | Chuyển tiếp tương tác xác thực giữa hai bên | Có thể kết hợp replay hoặc realtime forwarding |

Một chữ ký hợp lệ có thể loại trừ tampering nhưng không loại trừ replay. Một access token chưa hết hạn có thể được ký đúng nhưng vẫn bị replay nếu attacker đánh cắp được bearer token. Vì vậy, cần kiểm tra cả tính toàn vẹn, nguồn phát hành, audience, thời hạn và tính mới/đã dùng của bằng chứng.

## 3. Vì sao chữ ký hợp lệ không chống replay?

Giả sử client gửi thông điệp M cùng chữ ký:

`````````text
signature = Sign(privateKey, M)
`````````

Server xác minh chữ ký bằng public key. Nếu attacker ghi lại cả M và signature rồi gửi lại nguyên vẹn, phép xác minh vẫn thành công. Chữ ký chứng minh thông điệp được ký bởi bên kiểm soát private key và chưa bị thay đổi; nó không tự cho biết thông điệp đã được chấp nhận trước đó hay chưa.

Tương tự, MAC hợp lệ chỉ chứng minh bên tạo thông điệp có khóa MAC phù hợp và dữ liệu chưa bị sửa. Nếu không có freshness hoặc trạng thái chống dùng lại, cùng một MAC có thể được gửi nhiều lần.

### Hai thuộc tính cần tách biệt

- **Integrity/authenticity:** nội dung có bị sửa không và có đến từ nguồn được tin không?
- **Freshness/uniqueness:** bằng chứng có thuộc giao dịch hiện tại, còn hiệu lực và chưa được tiêu thụ không?

Một thiết kế an toàn thường cần cả hai. Chỉ dùng timestamp mà không ký timestamp cũng không đủ, vì attacker có thể sửa thời gian. Chỉ ký nonce mà server không lưu trạng thái tiêu thụ cũng không đủ, vì nonce cũ có thể được gửi lại.

## 4. Mô hình replay và các điều kiện khai thác

Replay thường cần một hoặc nhiều điều kiện:

1. Attacker có thể quan sát, lấy cắp hoặc lưu thông điệp hợp lệ;
2. Thông điệp không gắn chặt với một phiên/giao dịch cụ thể;
3. Server không kiểm tra freshness hoặc không lưu trạng thái đã dùng;
4. Cùng một proof được chấp nhận ở nhiều endpoint, audience hoặc tenant;
5. Replay xảy ra trong khoảng token/challenge còn hiệu lực;
6. Nhiều server không chia sẻ trạng thái chống replay nhất quán;
7. Request có side effect nhưng không có idempotency hoặc deduplication.

### Các vị trí có thể bị replay

`````````mermaid
flowchart TD
    A["Thông điệp/proof hợp lệ"] --> B["Attacker ghi lại hoặc đánh cắp"]
    B --> C{"Bằng chứng có freshness và binding?"}
    C -- "Không" --> D["Gửi lại request"]
    D --> E{"Server có kiểm tra trạng thái đã dùng?"}
    E -- "Không" --> F["Replay có thể được chấp nhận"]
    E -- "Có" --> G["Từ chối bằng chứng đã tiêu thụ"]
    C -- "Có" --> H["Kiểm tra nonce, audience, thời gian, transaction"]
    H --> I{"Khớp và còn mới?"}
    I -- "Không" --> G
    I -- "Có" --> J["Consume nguyên tử rồi xử lý"]
`````````

## 5. Các cơ chế chống replay cơ bản

Không có một cơ chế phù hợp cho mọi giao thức. Các kỹ thuật thường dùng gồm:

| Cơ chế | Cách hoạt động | Phù hợp với |
| --- | --- | --- |
| **Nonce** | Giá trị ngẫu nhiên duy nhất gắn với transaction | Challenge-response, OIDC, API proof |
| **Timestamp** | Chấp nhận request trong cửa sổ thời gian hẹp | Signed request, assertion có thời hạn |
| **Sequence number/counter** | Chấp nhận số thứ tự mới theo trạng thái đã lưu | Giao thức có thứ tự, authenticator counter |
| **One-time token/code** | Token chỉ được tiêu thụ một lần | Authorization code, recovery code, reset link |
| **Challenge-response** | Server tạo challenge mới, client ký hoặc chứng minh possession | Device authentication, WebAuthn |
| **Replay cache** | Lưu ID/nonce đã chấp nhận để từ chối lần lặp | Assertion/token/request có định danh duy nhất |
| **Idempotency key** | Nhận diện retry của cùng một thao tác nghiệp vụ | Payment/API có side effect |
| **Sender-constrained token** | Ràng buộc token với khóa của client | mTLS-bound access token, DPoP |

Các cơ chế có thể kết hợp. Timestamp giới hạn thời gian replay; nonce hoặc unique ID phân biệt từng request; replay cache ngăn cùng một ID được chấp nhận hai lần.

## 6. Nonce: tạo, ràng buộc và tiêu thụ

Nonce là một giá trị dùng một lần hoặc một lần theo transaction, thường được tạo bằng cryptographically secure random number generator (CSPRNG). Mục tiêu là làm cho request cũ không thể dùng lại trong một transaction mới.

### Yêu cầu với nonce

- Có entropy đủ cao và khó đoán;
- Được tạo bởi bên có thẩm quyền, thường là server;
- Gắn với subject/session, audience, purpose hoặc transaction;
- Có thời hạn;
- Được lưu ở server nếu cần theo dõi trạng thái;
- Chỉ được chấp nhận một lần;
- Được consume atomically để hai request đồng thời không cùng thắng;
- Không tái sử dụng nonce sau khi transaction hoàn tất hoặc hết hạn.

Nonce không nhất thiết phải giữ bí mật sau khi phát hành; giá trị của nó nằm ở tính mới và tính duy nhất. Tuy nhiên, attacker không được phép tự chọn nonce hoặc thay nonce mà không làm chữ ký/proof thất bại.

### Pseudocode tạo và xác minh challenge

`````````
createChallenge(subject, session, purpose):
    nonce = secureRandomBytes()
    challenge = {
        nonce: nonce,
        subjectRef: subject.reference,
        sessionRef: session.reference,
        audience: expectedService,
        purpose: purpose,
        expiresAt: now + shortLifetime,
        status: PENDING
    }
    store(challenge)
    return challenge

verifyAndConsume(challengeId, signedProof):
    challenge = load(challengeId)
    require(challenge.status == PENDING)
    require(now < challenge.expiresAt)
    require(proofBindsNonceSubjectAudiencePurpose(signedProof, challenge))
    require(verifySignature(registeredPublicKey, signedProof))
    require(atomicTransition(challenge, PENDING, CONSUMED))
    return ACCEPT
`````````

Đây là pseudocode khái niệm. Thao tác atomicTransition phải được bảo đảm bởi storage/transaction primitive phù hợp; kiểm tra status rồi cập nhật bằng hai thao tác không nguyên tử có thể tạo race condition.

## 7. Timestamp và cửa sổ thời gian

Timestamp giúp từ chối request quá cũ hoặc ở tương lai bất hợp lý. Request thường mang thời gian được ký/MAC; server so sánh với thời gian hiện tại và chỉ chấp nhận trong cửa sổ được cấu hình.

### Ưu điểm

- Không cần lưu vô hạn mọi request ID;
- Dễ áp dụng cho signed API request;
- Giới hạn thời gian mà thông điệp bị đánh cắp còn hữu ích;
- Có thể kết hợp với request ID để ngăn replay trong cửa sổ.

### Giới hạn

- Đồng hồ client/server có thể lệch;
- Một request hợp lệ vẫn có thể bị replay nhiều lần trong cửa sổ;
- Clock rollback hoặc time sync lỗi có thể ảnh hưởng xác minh;
- Nếu timestamp không được ký/MAC, attacker có thể sửa;
- Cửa sổ quá rộng làm tăng thời gian replay có thể xảy ra.

### Clock skew

Hệ thống nên đồng bộ thời gian server bằng nguồn tin cậy, lưu UTC, cho phép clock skew nhỏ theo threat model, theo dõi độ lệch giữa occurred time và receive time, từ chối timestamp quá xa trong tương lai và kết hợp timestamp với nonce/request ID cùng replay cache.

Timestamp giới hạn thời gian; nó không thay thế uniqueness. Một request được ký lúc 10:00 vẫn có thể bị gửi lại lúc 10:01 nếu cửa sổ cho phép và server chưa đánh dấu request đó đã dùng.

## 8. Sequence number và counter

Sequence number/counter là giá trị tăng dần hoặc theo thứ tự để phát hiện thông điệp cũ.

### Cách hoạt động

- Client và server duy trì counter;
- Mỗi request hợp lệ dùng counter mới;
- Server kiểm tra counter theo trạng thái đã lưu;
- Counter đã dùng hoặc thấp hơn mốc chấp nhận sẽ bị từ chối theo giao thức.

Counter có thể phát hiện request cũ mà không cần giữ mọi nonce, nhưng cần xử lý mất gói, request đến sai thứ tự, nhiều thiết bị, reset/restore counter và trạng thái giữa nhiều node server.

### WebAuthn signCount

Authenticator có thể cung cấp signature counter trong authenticator data. RP có thể dùng thay đổi counter như một tín hiệu phát hiện credential clone ở một số loại authenticator. Tuy nhiên, một số authenticator luôn trả về 0; passkey đồng bộ có thể dùng trên nhiều thiết bị và counter không tăng theo mô hình đơn giản. RP cần tuân theo semantics của WebAuthn và dùng counter như risk signal phù hợp.

WebAuthn chống replay chủ yếu nhờ challenge mới do RP tạo, gắn với ceremony và kiểm tra origin/RP ID; không dựa riêng vào signCount.

## 9. One-time token và consume nguyên tử

Authorization code, password reset token, invitation token và recovery code thường được thiết kế dùng một lần.

### Điều kiện

- Token có entropy đủ cao;
- Token gắn với đúng subject, purpose, client/audience và transaction;
- Có expiry;
- Server lưu trạng thái pending/consumed hoặc verifier;
- Lần dùng đầu tiên phải tiêu thụ trạng thái một cách atomic;
- Token không được dùng cho purpose khác;
- Token đã consume phải bị từ chối kể cả khi request được gửi tới node server khác.

### Race condition

Giả sử hai request cùng đến trong vài mili giây:

1. Request A đọc token status=PENDING;
2. Request B cũng đọc token status=PENDING;
3. Cả hai cùng xác minh token;
4. Cả hai cùng thực hiện side effect;
5. Sau đó trạng thái mới được cập nhật thành CONSUMED.

Kết quả là một token dùng một lần bị chấp nhận hai lần. Cần dùng compare-and-swap, unique constraint, conditional update hoặc transaction serializable phù hợp để chỉ một request thắng.

### Pseudocode consume

`````````sql
UPDATE one_time_tokens
SET status = 'CONSUMED',
    consumed_at = CURRENT_TIMESTAMP
WHERE token_id = :token_id
  AND status = 'PENDING'
  AND expires_at > CURRENT_TIMESTAMP;
`````````

Sau câu lệnh, service phải kiểm tra đúng một row được cập nhật. Nếu không có row nào, token đã hết hạn, không tồn tại hoặc đã được dùng. Việc consume và tạo side effect cần được phối hợp bằng transaction hoặc workflow idempotent để tránh trạng thái token consumed nhưng nghiệp vụ không thực hiện, hoặc nghiệp vụ thực hiện hai lần.

## 10. Replay cache trong hệ thống phân tán

Khi nhiều instance cùng xác minh request, replay cache cần hoạt động nhất quán giữa các node. Nếu mỗi node chỉ giữ cache trong memory riêng, attacker có thể gửi cùng request tới node khác.

### Thiết kế replay cache

Key cache có thể dựa trên issuer/provider ID, token/assertion/request ID, audience/client, purpose/protocol và tenant nếu cần namespace. TTL phải dài ít nhất bằng khoảng thời gian request có thể được chấp nhận, cộng clock skew và biên an toàn. Nếu TTL quá ngắn, request có thể được replay sau khi entry bị xóa nhưng token vẫn còn hiệu lực.

### Các yêu cầu vận hành

- Insert-if-absent hoặc atomic set-if-not-exists;
- Cache dùng chung hoặc state store có consistency phù hợp;
- Namespace chống collision giữa issuer/tenant/protocol;
- TTL gắn với exp/notOnOrAfter và policy;
- Xử lý cache outage theo fail-closed cho bằng chứng có nguy cơ replay;
- Theo dõi eviction, memory pressure và replication lag;
- Không log raw token/secret khi ghi cache key.

Nếu hệ thống không thể kiểm tra replay state, không được âm thầm bỏ qua kiểm tra cho token hoặc assertion cần one-time semantics. Có thể từ chối tạm thời hoặc chuyển sang state store dự phòng đã được thiết kế; chỉ cho phép thao tác ít rủi ro theo policy rõ ràng.

## 11. OAuth 2.0 và OpenID Connect

OAuth/OIDC có nhiều điểm cần chống replay vì authorization response và token có thể bị đánh cắp hoặc gửi lại.

### Authorization code

Authorization code cần thời hạn ngắn, gắn với client ID và redirect URI, chỉ đổi được một lần và gắn với PKCE code challenge/verifier khi sử dụng. Nếu code đã đổi thành công, lần đổi tiếp theo phải bị từ chối. PKCE giảm nguy cơ code interception; one-time code semantics và binding ngăn code bị dùng lại hoặc chuyển sang client khác.

### OIDC state, nonce và PKCE

- **state** liên kết authorization response với browser transaction của client;
- **nonce** liên kết ID token với authentication request;
- **PKCE** chứng minh bên đổi code có code verifier tương ứng.

Các giá trị này có mục tiêu khác nhau và cần được quản lý riêng. State/nonce phải được tạo ngẫu nhiên, gắn với transaction và có expiry. Client cần đánh dấu transaction đã hoàn tất để callback lặp không tạo session thứ hai.

### ID token và access token

- ID token phải được kiểm tra issuer, audience, thời hạn và nonce khi nonce được gửi;
- Access token phải được resource server xác minh theo issuer, audience, scope và profile;
- Bearer access token bị đánh cắp có thể bị replay tới khi hết hạn hoặc bị thu hồi;
- Có thể dùng sender-constrained token như mTLS-bound token hoặc DPoP theo kiến trúc;
- Không dùng ID token thay access token tại API.

Không phải mọi token đều có one-time semantics. JWT access token có thể được dùng nhiều lần trong thời hạn theo thiết kế bearer token; chống replay khi bị đánh cắp cần sender constraint, revocation, scope, short lifetime và bảo vệ token storage.

## 12. SAML và replay assertion

SAML assertion có thể chứa authentication statement và attributes. Nếu assertion bị đánh cắp trong thời gian còn hiệu lực và RP không có replay detection, attacker có thể gửi lại assertion để tạo session.

### Kiểm tra cần thiết

- Xác minh chữ ký theo trust configuration của IdP;
- Kiểm tra issuer;
- Kiểm tra audience restriction;
- Kiểm tra recipient và destination;
- Kiểm tra điều kiện thời gian như NotBefore và NotOnOrAfter;
- Kiểm tra InResponseTo khi thuộc SP-initiated flow;
- Kiểm tra assertion ID/message ID chưa được sử dụng;
- Lưu assertion ID vào replay cache cho tới khi hết khoảng chấp nhận;
- Xác minh response/assertion đúng request và đúng SP.

Chữ ký hợp lệ không làm assertion miễn nhiễm replay. RP cần giữ assertion ID đã chấp nhận và từ chối ID lặp trong cửa sổ hợp lệ.

### Unsolicited/IdP-initiated SSO

Trong flow không có request tương ứng từ SP, không thể dựa vào InResponseTo như với SP-initiated flow. Cần đánh giá rõ rủi ro, kiểm tra các điều kiện còn lại và replay cache. Với ứng dụng nhạy cảm, nên ưu tiên flow có request correlation khi kiến trúc hỗ trợ.

## 13. WebAuthn và challenge-response

WebAuthn được thiết kế quanh challenge mới do Relying Party tạo. Authenticator ký dữ liệu chứa clientDataHash cùng authenticator data; RP xác minh challenge, origin, RP ID hash, type và chữ ký.

### Chống replay trong authentication ceremony

1. RP tạo challenge ngẫu nhiên;
2. RP lưu challenge gắn với transaction/session và thời hạn;
3. Browser chuyển challenge tới authenticator qua WebAuthn API;
4. Authenticator tạo assertion ký dữ liệu tương ứng;
5. RP xác minh chữ ký, challenge, origin, RP ID và các điều kiện user verification;
6. RP consume challenge để từ chối assertion cũ hoặc callback lặp.

Nếu RP chấp nhận lại challenge cũ, một assertion hợp lệ có thể bị phát lại. Vì vậy, challenge phải được đánh dấu đã dùng khi ceremony hoàn tất.

### Phân biệt challenge với signCount

Challenge mới và việc kiểm tra origin/RP ID là nền tảng của replay protection. signCount chỉ là tín hiệu bổ sung theo semantics authenticator; không thể thay challenge và replay cache.

### Recovery và registration

Registration ceremony cũng cần challenge và transaction binding. Không để một attestation/credential creation response cũ được gửi lại để tạo credential ngoài transaction mà người dùng đã xác nhận.

## 14. OTP, TOTP và HOTP

OTP thường được mô tả là one-time password, nhưng việc một mã được sinh từ thuật toán OTP không tự bảo đảm server chỉ chấp nhận nó một lần.

### HOTP

HOTP dựa trên secret và counter. Verifier chấp nhận counter trong một cửa sổ đồng bộ nhất định rồi phải cập nhật counter theo cách chống dùng lại. Nếu counter không được cập nhật nguyên tử, cùng mã có thể được chấp nhận đồng thời.

### TOTP

TOTP dựa trên secret và time step. Một mã thường hợp lệ trong một khoảng thời gian. Nếu verifier chấp nhận mã nhiều lần trong cùng time step, mã đó có thể bị replay trong cửa sổ còn hiệu lực.

### Kiểm soát

- Rate limit số lần thử;
- Giới hạn cửa sổ time step;
- Lưu trạng thái time step/mã đã chấp nhận nếu yêu cầu one-time use nghiêm ngặt;
- Consume atomically để request đồng thời không cùng thành công;
- Không ghi OTP hoặc seed vào log;
- Thu hồi và tái thiết lập seed khi nghi bị lộ;
- Không dùng OTP đơn lẻ làm bằng chứng chống phishing.

SMS OTP cũng có thể bị replay hoặc relay nếu attacker lấy được mã trong thời gian hiệu lực. Dùng mã ngắn hạn và rate limit giúp giảm rủi ro nhưng không tạo được phishing resistance như passkey.

## 15. API request signing, DPoP và mTLS

API có thể dùng chữ ký để chứng minh request đến từ client kiểm soát khóa. Nhưng nếu chữ ký không gắn request ID, thời gian, method, URI và body digest, request hợp lệ có thể bị phát lại.

### Signed request

Thông điệp ký thường cần ràng buộc:

- HTTP method;
- Target URI hoặc canonical resource;
- Body digest;
- Timestamp;
- Nonce/request ID;
- Audience/service;
- Key identifier;
- Các header quan trọng theo profile.

Server xác minh chữ ký, kiểm tra thời gian và request ID chưa được dùng, sau đó consume request ID trước khi thực hiện side effect.

### DPoP

Demonstrating Proof of Possession (DPoP) ràng buộc việc sử dụng access token với khóa của client thông qua proof JWT cho từng request. Resource server kiểm tra các claim và quan hệ với access token theo profile, bao gồm method, URI, token hash, thời gian, jti và nonce khi được yêu cầu.

DPoP giúp giảm nguy cơ bearer token bị dùng từ client không có private key. Tuy nhiên, proof JWT cũng có thể bị replay trong cửa sổ nếu verifier không áp dụng replay detection phù hợp cho jti/proof và các quy tắc nonce.

### mTLS-bound token

Access token có thể được ràng buộc với certificate của client. Resource server kiểm tra client certificate khi request tới. Kẻ chỉ đánh cắp token nhưng không có private key tương ứng khó dùng token ở một client khác.

mTLS không tự ngăn replay từ chính thiết bị/client đã bị compromise hoặc từ kẻ tấn công kiểm soát private key. Vẫn cần token expiry, revocation, endpoint security và authorization.

## 16. Session cookie và bearer token replay

Cookie/session token và bearer access token thường là bearer credential: ai sở hữu giá trị hợp lệ có thể sử dụng nó trong phạm vi được cấp.

### Rủi ro

- Cookie bị đánh cắp qua XSS, malware, browser profile compromise hoặc log;
- Access token bị lộ trong URL, browser storage, crash report hoặc telemetry;
- Refresh token bị copy từ thiết bị;
- Token bị gửi tới resource server sai audience;
- Session tiếp tục hoạt động sau khi người dùng logout hoặc account bị disable do revoke không lan truyền.

### Kiểm soát

- TLS và cookie Secure/HttpOnly/SameSite phù hợp;
- Không đưa token vào URL hoặc log;
- Bảo vệ browser/device và hạn chế XSS/CSRF;
- Session ID rotation sau authentication/step-up;
- Idle và absolute timeout;
- Refresh token rotation và reuse detection theo profile;
- Thu hồi session/token khi compromise hoặc recovery;
- Sender-constrained token khi cần;
- Audience/scope hẹp và short lifetime.

TLS bảo vệ dữ liệu trên đường truyền giữa hai đầu kết nối, nhưng không ngăn replay của bearer token đã bị đánh cắp từ endpoint, browser storage hoặc log. Cần bảo vệ vòng đời token và thiết bị đầu cuối.

## 17. TLS 1.3 0-RTT và replay

TLS 1.3 hỗ trợ early data (0-RTT) để giảm độ trễ khi client kết nối lại. Early data có đặc tính replay risk: một số mô hình triển khai cho phép cùng dữ liệu early data được gửi lại trong các điều kiện nhất định.

### Hệ quả

Không nên gửi thao tác có side effect không idempotent trong early data nếu hệ thống chưa có cơ chế chống replay phù hợp. Ví dụ tạo giao dịch, chuyển tiền, đổi mật khẩu hoặc cấp quyền cần được xử lý với chính sách an toàn.

### Kiểm soát

- Tắt early data cho endpoint nhạy cảm nếu không cần;
- Chỉ cho phép early data với request an toàn/idempotent theo thiết kế;
- Dùng anti-replay mechanism của TLS deployment khi phù hợp;
- Kiểm tra application-level idempotency;
- Không coi TLS 0-RTT là bằng chứng user vừa xác thực lại.

Transport security và application replay protection là hai lớp khác nhau; cần đánh giá cả hai.

## 18. Idempotency: chống thực thi trùng trong nghiệp vụ

Idempotency không giống replay protection, nhưng thường được dùng cùng nhau.

- **Replay protection** xác định bằng chứng/request cũ đã được chấp nhận hay chưa;
- **Idempotency** bảo đảm retry của cùng một thao tác không tạo side effect lặp.

Ví dụ: Client gửi yêu cầu thanh toán, server đã thực hiện nhưng response bị mất. Client retry cùng idempotency key. Server trả lại kết quả đã lưu thay vì trừ tiền lần thứ hai.

### Thiết kế idempotency key

- Client gửi key ngẫu nhiên cho một thao tác logic;
- Server gắn key với subject, tenant, endpoint và request digest;
- Cùng key/cùng payload trả lại kết quả đã lưu;
- Cùng key nhưng payload khác phải bị từ chối;
- Key được lưu đủ lâu để bao phủ retry window;
- State transition và side effect được phối hợp atomically.

Không dùng idempotency key thay nonce/challenge trong authentication. Một idempotency key ổn định có thể được dùng lại có chủ đích để retry cùng thao tác, trong khi challenge xác thực thường phải dùng một lần và không được tái sử dụng cho transaction khác.

## 19. Detection và incident response

Replay detection cần ghi nhận bằng chứng đã dùng lại mà không lưu secret thô.

### Event gợi ý

- auth.challenge.issued;
- auth.challenge.consumed;
- auth.challenge.replay_rejected;
- token.replay_detected;
- assertion.id.duplicate;
- otp.time_step.reused;
- api.proof.jti.duplicate;
- session.reuse_suspected;
- idempotency.key.payload_mismatch;
- tls.early_data.rejected hoặc endpoint policy decision.

### Dấu hiệu đáng chú ý

- Cùng challenge ID xuất hiện nhiều lần;
- Cùng assertion ID được nhận bởi nhiều node;
- Cùng DPoP jti/proof được gửi lại;
- Authorization code được đổi nhiều lần;
- OTP cùng time step được chấp nhận từ nhiều request;
- Session/token xuất hiện đồng thời ở nhiều context bất thường;
- Request được thực hiện sau khi credential/session đã revoke;
- Nhiều giao dịch có cùng proof nhưng transaction digest khác nhau.

### Ứng phó

1. Từ chối request replay và giữ nguyên bằng chứng event;
2. Xác định token/challenge/session/credential reference liên quan;
3. Kiểm tra request đầu tiên có hợp lệ hay đã bị attacker sử dụng;
4. Thu hồi session/token/credential nếu có dấu hiệu đánh cắp;
5. Kiểm tra side effect đã xảy ra bao nhiêu lần;
6. Dùng transaction ledger/idempotency record để xác định trạng thái nghiệp vụ;
7. Nếu có giao dịch tài chính, chuyển quy trình xử lý gian lận/đảo giao dịch theo policy;
8. Rà soát replay cache, distributed consistency và clock drift;
9. Tìm các node/tenant/client khác có cùng pattern;
10. Ghi nhận nguyên nhân gốc và kiểm thử lại sau khắc phục.

## 20. Threat model và bộ kiểm thử chấp nhận

### Threat model

| Rủi ro | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Nonce replay** | Gửi lại proof của challenge cũ | Nonce transaction-bound, expiry và atomic consume |
| **Timestamp replay** | Gửi lại request trong time window | Request ID/replay cache kết hợp timestamp |
| **Counter rollback** | Khôi phục counter cũ hoặc đồng bộ sai | State monotonic, reset policy và risk review |
| **One-time token race** | Hai request consume cùng token đồng thời | Atomic update/unique constraint |
| **Distributed cache gap** | Node A và B không chia sẻ replay state | Shared consistent store hoặc partition-aware design |
| **Cache eviction** | Entry bị xóa trước khi proof hết hiệu lực | TTL theo acceptance window, capacity monitoring |
| **Audience confusion** | Proof hợp lệ ở service A được gửi tới B | Audience, purpose và domain separation |
| **Token theft** | Bearer token bị lấy và dùng lại | Sender constraint, short expiry, revocation, secure storage |
| **OTP reuse** | Cùng OTP được chấp nhận nhiều lần | One-time state, rate limit và consume |
| **SAML assertion replay** | Assertion hợp lệ được gửi lại | Assertion ID cache, InResponseTo, audience/time checks |
| **OIDC callback replay** | Callback cũ tạo session mới | State/nonce transaction state và single-use callback |
| **WebAuthn challenge replay** | Assertion cũ được gửi lại | Challenge mới, origin/RP ID checks, consume |
| **TLS 0-RTT replay** | Early data được phát lại | Tắt với side effect hoặc application anti-replay |
| **Clock skew** | Đồng hồ lệch làm cửa sổ chấp nhận quá rộng | Time sync, bounded skew, monitoring |
| **TOCTOU/double execution** | Proof được kiểm tra nhưng side effect chạy nhiều lần | Atomic state transition và idempotency |

### Bộ kiểm thử

| Trường hợp | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| **Challenge hợp lệ** | Gửi proof cho challenge pending | Chấp nhận một lần |
| **Challenge replay** | Gửi lại cùng proof | Từ chối |
| **Challenge hết hạn** | Gửi proof sau TTL | Từ chối |
| **Challenge sai subject** | Dùng proof của account khác | Từ chối |
| **Challenge sai purpose** | Dùng proof login cho transaction confirmation | Từ chối |
| **Nonce bị sửa** | Thay nonce trong payload | Chữ ký/proof không hợp lệ |
| **Timestamp cũ** | Gửi request ngoài cửa sổ | Từ chối |
| **Timestamp tương lai** | Gửi request lệch xa trong tương lai | Từ chối và ghi nhận |
| **Request ID duplicate** | Gửi hai request cùng ID | Request thứ hai bị từ chối |
| **Counter lặp** | Gửi lại counter đã chấp nhận | Từ chối theo semantics giao thức |
| **OTP same time step** | Dùng lại TOTP đã chấp nhận | Từ chối nếu policy yêu cầu one-time consumption |
| **HOTP counter race** | Gửi hai request đồng thời cùng counter | Chỉ một request được chấp nhận |
| **Authorization code replay** | Đổi code lần thứ hai | Token endpoint từ chối |
| **OIDC nonce mismatch** | ID token chứa nonce khác transaction | Client từ chối |
| **OIDC state replay** | Gửi lại callback đã hoàn tất | Không tạo session mới |
| **SAML assertion replay** | Gửi lại assertion ID đã chấp nhận | RP từ chối |
| **SAML audience mismatch** | Gửi assertion tới SP khác | Từ chối |
| **WebAuthn challenge replay** | Gửi lại assertion của ceremony cũ | RP từ chối |
| **DPoP proof replay** | Gửi lại proof JWT có cùng jti | Từ chối theo replay policy |
| **mTLS token misuse** | Dùng token từ client không có certificate key tương ứng | Từ chối |
| **Bearer token theft** | Dùng token bị đánh cắp trong thời hạn | Sender constraint/revocation policy hạn chế sử dụng |
| **Distributed node race** | Gửi cùng proof đồng thời tới hai node | Chỉ một node chấp nhận |
| **Replay cache outage** | Làm state store không khả dụng | Không âm thầm bỏ qua replay check |
| **Cache eviction** | Tạo tải làm entry bị evict sớm | Không chấp nhận lại proof còn trong validity window |
| **Idempotent retry** | Retry cùng key và payload sau timeout | Trả kết quả cũ, không lặp side effect |
| **Idempotency payload mismatch** | Cùng key nhưng payload khác | Từ chối |
| **TLS early data** | Gửi side-effect request qua 0-RTT | Bị chặn hoặc bảo vệ bằng anti-replay/idempotency |
| **Revoked session** | Gửi lại session sau revoke | Từ chối theo SLA |
| **Clock drift** | Mô phỏng lệch thời gian giữa node | Hành vi bounded, có metric và không mở cửa sổ vô hạn |
| **Audit redaction** | Kiểm tra log/replay cache | Không có raw token, OTP, cookie hoặc private key |

Kiểm thử phải chạy cả trên một node và nhiều node, có request đồng thời, cache outage và retry sau timeout. Một unit test xác minh nonce một lần trong memory không chứng minh hệ thống production chống replay trong môi trường phân tán.

## 21. Checklist triển khai Replay protection

- **Threat model:** Đã xác định thông điệp/token nào có thể bị ghi lại và phát lại?
- **Integrity:** Chữ ký/MAC được xác minh bằng khóa và thuật toán được tin cậy?
- **Freshness:** Có nonce, timestamp, counter hoặc one-time ID phù hợp?
- **Binding:** Proof gắn với subject, session, audience, purpose, tenant và transaction?
- **Uniqueness:** Nonce/request ID có entropy và namespace phù hợp?
- **Expiry:** Thời hạn và clock skew được giới hạn?
- **Consumption:** Challenge/token được consume atomically?
- **Distributed state:** Replay cache nhất quán giữa các instance?
- **Failure mode:** Cache/store outage không làm bypass replay check?
- **Protocol:** OIDC state/nonce/PKCE, SAML assertion ID, WebAuthn challenge, OTP semantics được xử lý đúng?
- **Token:** Bearer token được bảo vệ; sender constraint được cân nhắc khi phù hợp?
- **Transport:** TLS 0-RTT không được dùng cho side effect không an toàn?
- **Business action:** Có idempotency và transaction state để tránh thực thi trùng?
- **Revocation:** Token/session/credential bị revoke được từ chối ở mọi điểm thực thi?
- **Monitoring:** Có event duplicate, replay rejection, cache lag/eviction và clock drift?
- **Testing:** Đã thử replay tuần tự, đồng thời, phân tán, cache outage và cross-audience?

### Câu hỏi tự kiểm tra

1. Vì sao chữ ký hợp lệ không đủ để ngăn replay?
2. Nonce và timestamp khác nhau ở điểm nào?
3. Vì sao timestamp cần kết hợp request ID hoặc replay cache?
4. Tại sao consume một lần phải được thực hiện atomically?
5. Replay cache cục bộ có thể thất bại thế nào khi hệ thống có nhiều node?
6. OIDC state, nonce và PKCE bảo vệ những phần nào của flow?
7. SAML RP cần kiểm tra assertion ID và InResponseTo ra sao?
8. Vì sao WebAuthn challenge quan trọng hơn việc chỉ dựa vào signCount?
9. TOTP có thể bị replay trong cùng time step như thế nào?
10. Replay protection khác idempotency của nghiệp vụ ra sao?
11. TLS 0-RTT có rủi ro gì với request tạo side effect?
12. Khi replay cache không khả dụng, vì sao không nên âm thầm bỏ qua kiểm tra?

## Kết luận

**Replay attack tận dụng một bằng chứng từng hợp lệ nhưng đã cũ hoặc đã được sử dụng, nên xác minh chữ ký/MAC đơn thuần chưa đủ.** Hệ thống cần gắn proof với đúng subject, session, audience, purpose và transaction; áp dụng nonce, timestamp, counter hoặc one-time identifier; rồi tiêu thụ trạng thái chống replay một cách nguyên tử. Trong hệ thống phân tán, replay cache phải nhất quán và tồn tại đủ lâu cho toàn bộ cửa sổ chấp nhận. OIDC, SAML, WebAuthn, OTP, API proof, bearer token và TLS 0-RTT có semantics khác nhau nên phải áp dụng đúng cơ chế theo từng giao thức. Cuối cùng, idempotency bảo vệ side effect khỏi retry trùng, còn replay protection bảo đảm bằng chứng cũ không được chấp nhận lại; cả hai cần phối hợp để bảo vệ luồng xác thực và giao dịch.
