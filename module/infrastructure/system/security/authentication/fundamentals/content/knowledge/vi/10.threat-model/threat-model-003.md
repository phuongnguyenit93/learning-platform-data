# Replay

## 1. Replay attack là gì?

**Replay attack (tấn công phát lại)** xảy ra khi kẻ tấn công thu được một thông điệp, bằng chứng xác thực hoặc yêu cầu đã từng hợp lệ rồi gửi lại nó để khiến hệ thống chấp nhận lần nữa. Thông điệp được phát lại có thể là mật khẩu, mã OTP, chữ ký, MAC, token, cookie phiên, yêu cầu API đã ký hoặc một bản tin trong giao thức xác thực.

Điểm nguy hiểm của replay là **bằng chứng từng hợp lệ không nhất thiết còn hợp lệ ở lần sử dụng tiếp theo**. Nếu verifier chỉ kiểm tra chữ ký/MAC đúng hoặc token có cấu trúc hợp lệ mà không xét tính mới, trạng thái sử dụng và ngữ cảnh, một bản sao có thể được chấp nhận nhiều lần.

Ví dụ: một API nhận yêu cầu chuyển 5 triệu đồng kèm chữ ký HMAC hợp lệ. Attacker ghi lại toàn bộ request và gửi lại sau đó. Nếu server chỉ kiểm tra HMAC mà không nhận biết request đã được xử lý, giao dịch thứ hai có thể được thực thi. Chữ ký đúng chỉ chứng minh request được tạo bởi bên có khóa; nó không tự chứng minh đây là lần gửi đầu tiên.

Replay xuất hiện ở nhiều lớp:

| Lớp | Dữ liệu bị phát lại | Hậu quả có thể xảy ra |
| --- | --- | --- |
| Credential | Mật khẩu, API key, bearer token | Đăng nhập hoặc gọi API dưới danh nghĩa chủ credential. |
| OTP | TOTP/HOTP hoặc mã gửi qua SMS/email | Xác thực lại trong cửa sổ mã còn được chấp nhận. |
| Challenge–response | Response của một challenge cũ | Vượt qua xác thực nếu challenge không mới hoặc không bị tiêu thụ một lần. |
| Session | Cookie phiên hoặc access token bị đánh cắp | Tiếp tục sử dụng phiên đã xác thực. |
| Request/API | HTTP request đã ký hoặc lệnh nghiệp vụ | Lặp hành động, ví dụ tạo đơn hoặc chuyển tiền hai lần. |
| Giao thức mạng | Bản tin được ghi lại trong một phiên/kênh | Tái sử dụng bản tin nếu giao thức không bảo vệ sequence/freshness đúng cách. |

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, replay cần được xem như một mối đe dọa xuyên suốt: credential có thể được xác minh đúng nhưng bị dùng sai thời điểm, trong phiên khác, cho verifier khác hoặc cho cùng một hành động nhiều lần.

## 2. Phân biệt replay với các kiểu tấn công gần giống

Replay có thể đi cùng các cuộc tấn công khác, nhưng không nên đánh đồng chúng:

| Kiểu tấn công | Cách hoạt động | Khác replay ở điểm nào? |
| --- | --- | --- |
| **Replay** | Thu một thông điệp hợp lệ rồi gửi lại chính thông điệp đó. | Bằng chứng cũ được tái sử dụng. |
| **Relay / real-time phishing** | Chuyển tiếp challenge và response giữa nạn nhân với verifier thật trong thời gian thực. | Response có thể hoàn toàn mới, chưa từng được dùng trước đó. |
| **Credential stuffing** | Thử username/password bị lộ từ dịch vụ khác. | Attacker có thể tạo lần đăng nhập mới bằng credential bị lộ, không nhất thiết phát lại một bản tin. |
| **Brute force / guessing** | Đoán credential hoặc response. | Attacker tự tạo giá trị để thử, không cần thông điệp hợp lệ đã thu được. |
| **CSRF** | Dụ trình duyệt nạn nhân gửi yêu cầu có cookie tự động đính kèm. | Có thể tạo yêu cầu mới trong phiên nạn nhân; không nhất thiết gửi lại nguyên request cũ. |
| **Duplicate delivery / retry** | Client gửi lại yêu cầu do timeout hoặc không nhận được phản hồi. | Có thể là hành vi hợp lệ ngoài ý muốn, cần idempotency để tránh xử lý trùng. |

Ví dụ: OTP có hạn 30 giây bị kẻ tấn công lấy và gửi lại trong cùng cửa sổ là replay. Nếu attacker đứng giữa trang giả, chuyển tiếp OTP của nạn nhân đến website thật ngay khi nạn nhân nhập, đó là relay/phishing thời gian thực. Cả hai có thể dẫn tới chiếm phiên, nhưng cần các biện pháp khác nhau.

## 3. Vì sao thông điệp cũ vẫn có thể được chấp nhận?

Một thông điệp có chữ ký hoặc MAC hợp lệ chỉ cho biết dữ liệu khớp với khóa tương ứng. Nếu thông điệp không chứa dữ liệu mới, hoặc verifier không theo dõi việc sử dụng, cùng một bằng chứng có thể được kiểm tra thành công nhiều lần.

Ví dụ thiết kế sai:

~~~text
Server: Hãy ký chuỗi cố định "LOGIN".
Client: Sign(private_key, "LOGIN") -> signature
Attacker ghi lại signature.

Lần đăng nhập sau:
Server: Hãy ký chuỗi cố định "LOGIN".
Attacker gửi lại signature cũ.
Verifier: chữ ký hợp lệ -> chấp nhận.
~~~

Vấn đề không nằm ở thuật toán chữ ký. Chữ ký đã xác minh chính xác nội dung cũ. Lỗi là giao thức không tạo sự khác biệt giữa các lần xác thực và không ràng buộc response với lần thử hiện tại.

Một thiết kế tốt hơn cần kiểm tra:

- **Freshness:** bằng chứng gắn với một lần tương tác mới.
- **Uniqueness:** cùng challenge, nonce, sequence hoặc token dùng một lần không được chấp nhận lại.
- **Context binding:** bằng chứng gắn với đúng principal, verifier, phiên, audience, mục đích và yêu cầu.
- **Expiry:** bằng chứng chỉ được dùng trong khoảng thời gian phù hợp.
- **Atomic consumption:** việc đánh dấu đã dùng phải an toàn khi nhiều request đến đồng thời hoặc nhiều node cùng xác minh.

Không phải mọi giao thức đều dùng tất cả thuộc tính theo cùng cách. Hãy theo đúng đặc tả giao thức thay vì tự thêm trường có thể làm thay đổi cách chuẩn hóa hoặc cách xác minh.

## 4. Các cơ chế chống replay

### 4.1. Nonce ngẫu nhiên và challenge dùng một lần

**Nonce** là giá trị được dùng một lần trong một ngữ cảnh giao thức. Với challenge–response, verifier tạo nonce mới bằng bộ sinh số ngẫu nhiên an toàn về mặt mật mã (CSPRNG), gửi cho client và lưu trạng thái. Client đưa nonce vào dữ liệu được ký/MAC. Verifier kiểm tra response đối với đúng nonce đã phát, rồi tiêu thụ challenge theo cơ chế một lần.

Ví dụ tạo nonce 32 byte bằng Node.js:

~~~ts
import { randomBytes } from "node:crypto";

const nonce = randomBytes(32); // 256 bit ngẫu nhiên
~~~

Không dùng timestamp, số tăng dần dễ đoán hoặc `Math.random()` làm nonce bảo mật. Nonce không nhất thiết phải bí mật; điều quan trọng là nó mới, khó đoán khi cần và được ràng buộc đúng giao thức.

Một bản ghi challenge có thể gồm:

~~~json
{
  "challengeId": "ch_8f7d",
  "nonce": "base64url-random-value",
  "principalId": "service-A",
  "verifier": "api.example.test",
  "purpose": "login",
  "flowId": "flow_123",
  "expiresAt": "2026-11-22T08:05:00Z",
  "status": "pending"
}
~~~

Đây là mô hình minh họa. Server phải lưu và kiểm soát các trường quyết định tin cậy. Không được tin một bản JSON client gửi lại nếu client có thể tự sửa `principalId`, `purpose` hoặc `status`.

Sau khi response được xác minh, verifier cần chuyển challenge từ `pending` sang `used`. Việc kiểm tra và chuyển trạng thái phải nguyên tử; nếu hai request đồng thời cùng kiểm tra một challenge đang pending rồi cùng cập nhật, cả hai có thể vượt qua nếu thao tác được chia thành hai bước không an toàn.

### 4.2. Timestamp và cửa sổ thời gian

Timestamp cho phép verifier từ chối thông điệp quá cũ hoặc đến quá sớm. Ví dụ, server chỉ chấp nhận request có thời gian ký nằm trong khoảng vài phút quanh thời gian hiện tại.

Timestamp **một mình không chống replay**. Attacker có thể gửi lại nguyên request trong cửa sổ thời gian vẫn hợp lệ. Vì vậy, thiết kế request ký thường kết hợp:

1. Timestamp được đưa vào nội dung chữ ký/MAC.
2. Nonce ngẫu nhiên hoặc request identifier duy nhất.
3. Replay cache hoặc kho trạng thái để từ chối nonce/ID đã dùng.
4. Hạn dùng ngắn và đồng hồ được đồng bộ ở mức phù hợp.

Timestamp giúp giới hạn thời gian lưu giữ trạng thái chống replay. Nếu thời gian chấp nhận là ±5 phút, replay cache phải giữ nonce đủ lâu để không có request bị chấp nhận ở node khác sau khi bản ghi đã hết TTL.

### 4.3. Sequence number hoặc counter

Một số giao thức dùng số thứ tự tăng dần. Verifier lưu sequence cuối cùng đã chấp nhận và từ chối số cũ hoặc trùng. Cơ chế này phù hợp khi hai bên có trạng thái và quy tắc đồng bộ rõ.

Giới hạn:

- Client khởi động lại hoặc khôi phục snapshot có thể quay counter về giá trị cũ.
- Nhiều request song song có thể đến sai thứ tự.
- Nhiều thiết bị hoặc node cùng dùng credential cần quy tắc sequence riêng.
- Mất đồng bộ có thể khiến người dùng hợp lệ bị khóa khỏi luồng.

Một số giao thức cho phép *sliding window* để chấp nhận bản tin đến lệch thứ tự trong giới hạn. Cần triển khai theo đặc tả, lưu trạng thái bền vững và kiểm soát cập nhật đồng thời.

### 4.4. Token dùng một lần và trạng thái phía server

Token reset mật khẩu, mã xác minh email, magic link hoặc challenge có thể được phát hành với trạng thái `pending` và chỉ được tiêu thụ một lần. Server lưu hash hoặc giá trị dẫn xuất của token, chủ thể, mục đích, thời hạn và trạng thái.

Khi token được dùng, server kiểm tra mọi điều kiện rồi đánh dấu đã tiêu thụ trong một thao tác nguyên tử. Token phải gắn với đúng mục đích: token xác minh email không được tái sử dụng làm token đặt lại mật khẩu.

### 4.5. Ràng buộc khóa/người gửi

Với bearer token, bất kỳ ai có bản sao token có thể trình lại nó. Có thể giảm rủi ro bằng cách ràng buộc token với khóa của client hoặc chứng chỉ, ví dụ mTLS hoặc cơ chế proof-of-possession phù hợp. Khi đó, chỉ có token chưa đủ; bên gọi còn phải chứng minh quyền sử dụng khóa tương ứng.

Ràng buộc người gửi không bảo vệ nếu attacker chiếm được cả token và khóa riêng, hoặc điều khiển được runtime hợp lệ. Nó là một lớp giảm thiểu replay token bị đánh cắp, không thay cho bảo vệ endpoint, khóa và quyền truy cập.

## 5. Replay trong challenge–response

Một luồng challenge–response có khả năng chống replay khi verifier tạo challenge mới, response bao phủ challenge đó, và verifier chỉ chấp nhận challenge đúng một lần trong đúng ngữ cảnh.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant V as Verifier
    participant DB as Challenge store
    C->>V: Bắt đầu xác thực
    V->>DB: Tạo nonce ngẫu nhiên, trạng thái pending
    DB-->>V: challengeId + nonce
    V-->>C: Challenge mới
    C->>C: Tính chữ ký/MAC trên challenge và context
    C->>V: challengeId + response
    V->>DB: Đọc challenge và credential
    DB-->>V: Bản ghi pending, chưa hết hạn
    V->>V: Kiểm tra response và context
    V->>DB: Consume pending -> used (atomic)
    DB-->>V: Chỉ một request thắng
    V-->>C: Thành công hoặc từ chối
~~~

Response cũ gửi với challenge cũ phải bị từ chối vì challenge đã hết hạn hoặc đã dùng. Response cũ gửi với challenge mới phải thất bại vì chữ ký/MAC không bao phủ nonce mới.

Tuy nhiên, chống replay không đồng nghĩa chống relay. Kẻ tấn công có thể tạo phiên mới với verifier thật, chuyển challenge mới cho nạn nhân và chuyển response về trước khi challenge được dùng. Response khi đó là mới và hợp lệ. Cần thêm ràng buộc verifier/origin, audience, kênh hoặc cơ chế chống phishing ở cấp giao thức, chẳng hạn WebAuthn với RP ID/origin được kiểm tra đúng cách.

## 6. Replay với OTP

### 6.1. TOTP

TOTP tạo mã dựa trên secret và bước thời gian. Server thường cho phép sai lệch một số bước để chịu được đồng hồ client không hoàn toàn đồng bộ. Điều đó có nghĩa một mã có thể còn hợp lệ trong một cửa sổ thời gian.

Nếu server chỉ kiểm tra mã đúng mà không ghi nhận mã đã được chấp nhận, attacker có thể gửi lại cùng mã trong cùng cửa sổ. Với chính sách chống replay, server có thể lưu bước thời gian đã chấp nhận gần nhất cho credential và từ chối dùng lại bước đó, đồng thời cập nhật trạng thái nguyên tử. Phải cân nhắc đồng bộ đồng hồ và xử lý request đồng thời để tránh chấp nhận hai lần hoặc từ chối nhầm.

### 6.2. HOTP

HOTP dựa trên counter. Verifier kiểm tra một cửa sổ counter cho phép lệch, rồi cập nhật counter đã đồng bộ khi mã hợp lệ. Nếu không cập nhật trạng thái sau khi chấp nhận, cùng mã có thể được sử dụng lại.

### 6.3. OTP qua SMS/email

Mã gửi qua SMS/email cần gắn với đúng flow, tài khoản và mục đích; có thời hạn ngắn, giới hạn số lần thử và được tiêu thụ một lần. Mã dùng một lần vẫn có thể bị phishing hoặc relay theo thời gian thực trước khi chủ tài khoản sử dụng. Do đó OTP không mặc nhiên chống phishing.

## 7. Replay với session cookie và access token

Sau khi authentication thành công, ứng dụng thường tạo session cookie hoặc access token. Nhiều loại là **bearer credential**: ai có bản sao hợp lệ đều có thể gửi lại để được nhận diện là phiên/chủ thể tương ứng.

Kẻ tấn công có thể lấy token từ:

- XSS hoặc mã độc chạy trong thiết bị/trình duyệt.
- Log, crash report, URL, lịch sử, proxy hoặc công cụ quan sát.
- Kho lưu trữ phía client, bản backup hoặc máy đã bị chiếm.
- Extension độc hại, cấu hình CI/CD hoặc secret bị commit.
- Kênh hỗ trợ hoặc quy trình chia sẻ token không an toàn.

TLS bảo vệ token khi truyền giữa các đầu cuối đã xác thực, nhưng không ngăn token bị lấy từ endpoint hoặc log. Cookie `Secure`, `HttpOnly`, `SameSite` giúp giảm một số đường lộ và tấn công trình duyệt, nhưng không làm bearer cookie đã bị đánh cắp mất khả năng replay.

Biện pháp giảm thiểu gồm:

1. Access token có thời hạn ngắn và scope/audience tối thiểu.
2. Session phía server có khả năng thu hồi; khi logout, khóa tài khoản hoặc đổi credential, xử lý phiên theo chính sách.
3. Bảo vệ endpoint, chống XSS, quản lý cookie an toàn và tránh log token.
4. Dùng token ràng buộc người gửi (sender-constrained) như mTLS hoặc DPoP khi kiến trúc hỗ trợ và lợi ích tương xứng.
5. Giám sát việc sử dụng cùng credential từ nhiều vị trí hoặc hành vi bất thường, nhưng không dựa duy nhất vào IP/User-Agent làm bằng chứng.

DPoP (Demonstrating Proof of Possession) ràng buộc việc sử dụng access token với khóa của client bằng proof được ký cho từng HTTP request, cùng các claim như method/URI và thời gian; server có thể dùng nonce và cơ chế phát hiện proof ID đã dùng theo đặc tả. DPoP giảm nguy cơ token đơn lẻ bị đánh cắp và phát lại từ client không có khóa. Nó không ngăn attacker điều khiển client hợp lệ hoặc đánh cắp cả khóa.

## 8. Replay ở tầng giao thức mạng: TLS và 0-RTT

TLS dùng sequence number và cơ chế bảo vệ record để phát hiện bản ghi bị sửa, lặp hoặc sai thứ tự trong một kết nối. Một bản ghi mã hóa từ kết nối TLS này không thể đơn giản được chép sang kết nối khác và được chấp nhận như record mới trong một handshake độc lập.

Tuy nhiên, **TLS 1.3 0-RTT early data** có đặc tính replay riêng: dữ liệu gửi sớm trong quá trình nối lại phiên có thể bị phát lại trong một số kịch bản, tùy thiết kế triển khai và hạ tầng. Vì vậy, không nên cho phép 0-RTT thực hiện hành động không idempotent hoặc gây tác động tài chính nếu hệ thống không có cơ chế chống replay phù hợp.

Các nguyên tắc:

- Hiểu chính sách 0-RTT của TLS terminator, CDN, load balancer và origin; replay có thể đi qua nhiều tầng.
- Chỉ cho phép early data với thao tác an toàn/idempotent theo thiết kế, hoặc có chống replay ở cấp ứng dụng.
- Không nhầm bảo vệ record của một kết nối TLS với chống phát lại một yêu cầu HTTP ở tầng ứng dụng.
- Kiểm tra cấu hình thư viện và hạ tầng theo đặc tả TLS; không tự xây dựng lại handshake.

## 9. Replay request API và idempotency

Với API nhận request có chữ ký/MAC, verifier thường cần xác minh cả **tính xác thực** và **tính mới**. Ví dụ một request được ký có thể bao gồm:

~~~text
signature = HMAC(
  secret,
  canonical(
    method,
    path,
    query,
    body_hash,
    audience,
    timestamp,
    nonce
  )
)
~~~

Server phải tạo lại đúng canonical request, kiểm tra chữ ký, kiểm tra timestamp trong cửa sổ chấp nhận và từ chối nonce đã dùng. Nonce phải được ràng buộc với key/principal phù hợp. Nếu chỉ ký timestamp nhưng không lưu nonce/request ID đã dùng, attacker vẫn có thể gửi lại request trong cửa sổ.

Canonicalization phải được định nghĩa chính xác: cách chuẩn hóa method, path, query, header, body encoding, thứ tự tham số và cách xử lý ký tự. Nếu client và server diễn giải khác nhau, chữ ký có thể bị kiểm tra sai hoặc một phần dữ liệu quan trọng không được ký. Ưu tiên chuẩn/thư viện có thiết kế rõ, không tự phát minh giao thức.

### 9.1. Replay protection khác idempotency

Hai cơ chế giải quyết hai vấn đề khác nhau:

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| **Replay protection** | Bằng chứng/request này đã được chấp nhận trước đó chưa? Có còn mới và đúng ngữ cảnh không? | Từ chối nonce đã dùng trong chữ ký API. |
| **Idempotency** | Nếu client gửi lại cùng một thao tác hợp lệ do timeout, hệ thống có tránh thực hiện tác động nghiệp vụ nhiều lần không? | Cùng idempotency key và payload thanh toán trả lại cùng kết quả giao dịch. |

Một client hợp lệ có thể gửi lại yêu cầu vì không nhận được phản hồi. Nếu server từ chối mọi request trùng như replay, client có thể không biết giao dịch trước đã thành công hay chưa. Idempotency cho phép trả lại kết quả đã ghi nhận mà không thực thi tác động lần hai.

Ngược lại, idempotency key không tự chứng minh request đến từ client được phép. Attacker có thể gửi request giả nếu thiếu authentication và authorization. Idempotency key cần được ràng buộc với principal, endpoint và payload; lưu kết quả đủ lâu và cập nhật nghiệp vụ trong giao dịch nhất quán.

~~~text
Nhận request
  -> Xác thực credential/chữ ký
  -> Kiểm tra freshness và replay nonce
  -> Kiểm tra principal, scope, tenant, quyền
  -> Kiểm tra idempotency key + payload
       -> Đã hoàn tất cùng payload: trả kết quả cũ
       -> Đang xử lý: trả trạng thái phù hợp
       -> Chưa có: thực hiện nghiệp vụ và lưu kết quả nguyên tử
~~~

## 10. Ví dụ xử lý chống replay trong API

Giả sử một dịch vụ backend ký mỗi request bằng HMAC-SHA-256. Client tạo nonce ngẫu nhiên cho từng request và ký nonce cùng method, path, body hash, audience và timestamp. Server kiểm tra chữ ký trước, rồi **chèn nonce vào replay store với ràng buộc duy nhất**.

Pseudocode:

~~~ts
async function verifySignedRequest(req) {
  const key = await loadActiveKey(req.keyId);
  if (!key) return unauthorized();

  const signedBytes = canonicalize({
    method: req.method,
    path: req.path,
    bodyHash: sha256(req.rawBody),
    audience: EXPECTED_AUDIENCE,
    timestamp: req.timestamp,
    nonce: req.nonce
  });

  if (!constantTimeVerifyHmac(key.secret, signedBytes, req.signature)) {
    return unauthorized();
  }

  if (!isWithinAllowedClockWindow(req.timestamp, now())) {
    return unauthorized();
  }

  // INSERT với UNIQUE(key_id, nonce), TTL dài hơn cửa sổ chấp nhận.
  // Chỉ một request có thể claim nonce này.
  const firstUse = await replayStore.insertIfAbsent({
    keyId: req.keyId,
    nonce: req.nonce,
    expiresAt: replayRetentionDeadline(req.timestamp)
  });
  if (!firstUse) return unauthorized();

  const principal = await resolvePrincipalAndCurrentPolicy(key);
  return authorizeAndHandle(req, principal);
}
~~~

Đây là pseudocode, không phải thư viện dùng trực tiếp. Khi triển khai cần:

- Kiểm tra định dạng và độ dài của nonce, timestamp, key ID và chữ ký trước khi xử lý tốn tài nguyên.
- Dùng so sánh chữ ký an toàn, kiểm tra đúng thuật toán và khóa; không cho client tự chọn thuật toán không được phép.
- Chỉ ký dữ liệu canonical lấy từ đúng request thực tế, bao gồm body bytes hoặc digest có định nghĩa rõ.
- `insertIfAbsent` phải được bảo đảm duy nhất và nguyên tử giữa mọi instance/region có thể nhận cùng credential.
- Giữ bản ghi replay lâu hơn toàn bộ cửa sổ mà request còn có thể được chấp nhận, tính cả clock skew và độ trễ.
- Nếu replay store không khả dụng, với endpoint nhạy cảm nên từ chối theo nguyên tắc fail closed thay vì bỏ kiểm tra.
- Không log secret hoặc toàn bộ chữ ký/credential; log key ID, kết quả, request ID và tín hiệu điều tra cần thiết.
- Xử lý riêng idempotency của nghiệp vụ nếu client cần retry an toàn.

## 11. Replay trong hệ thống phân tán

Chống replay khó hơn khi có nhiều API node, nhiều vùng địa lý hoặc cache:

1. **Race condition:** hai node cùng đọc nonce chưa tồn tại rồi cùng chấp nhận. Cần thao tác insert-if-absent có ràng buộc duy nhất, transaction hoặc primitive tương đương.
2. **Eventual consistency:** node A đã tiêu thụ nonce nhưng node B chưa thấy cập nhật và vẫn chấp nhận. Kho chống replay cần mức nhất quán phù hợp với mục tiêu bảo vệ.
3. **TTL quá ngắn:** bản ghi nonce bị xóa khi request vẫn còn trong cửa sổ timestamp được chấp nhận; request cũ lại có thể được nhận.
4. **Clock skew:** đồng hồ giữa client, gateway và server lệch nhau; cửa sổ chấp nhận rộng hơn dự kiến hoặc client hợp lệ bị từ chối.
5. **Fail-open:** khi kho trạng thái lỗi, hệ thống bỏ qua kiểm tra replay để duy trì khả dụng, vô tình mở đường cho tấn công.
6. **Khôi phục backup/snapshot:** trạng thái đã tiêu thụ bị quay lùi sau khi restore, khiến nonce cũ có thể xuất hiện như chưa dùng.

Thiết kế cần xác định rõ:

- Phạm vi duy nhất của nonce: toàn hệ thống, theo key ID, theo principal, theo phiên hay theo endpoint.
- Thời gian lưu trạng thái và cách tính TTL so với cửa sổ chấp nhận.
- Mức nhất quán cần thiết giữa các node; cách xử lý request đồng thời.
- Cách vận hành khi replay store, KMS hoặc nguồn thời gian gặp lỗi.
- Quy trình khôi phục sau sự cố để không làm sống lại trạng thái cũ.

Không phải mọi hệ thống đều cần kho replay toàn cục. Có thể phân vùng theo credential hoặc principal để mở rộng, miễn là **mọi nơi có thể xác minh cùng một credential đều chia sẻ được trạng thái chống lặp phù hợp**.

## 12. Mô hình hóa đe dọa replay

Khi lập threat model, hãy xác định:

| Thành phần | Câu hỏi |
| --- | --- |
| **Tài sản** | Credential, session, quyền truy cập, lệnh nghiệp vụ hay tiền/dữ liệu nào cần bảo vệ? |
| **Attacker** | Attacker có thể nghe lén, lấy log, chiếm endpoint, đọc token, điều khiển proxy hay chỉ gửi request từ Internet? |
| **Điểm quan sát** | Thông điệp có thể bị ghi lại ở browser, TLS terminator, gateway, queue, log, CI hay thiết bị client không? |
| **Khả năng phát lại** | Attacker có thể gửi lại ở cùng endpoint, node khác, tenant khác, verifier khác hay sau khi khôi phục hệ thống không? |
| **Điều kiện chấp nhận** | Server kiểm tra chữ ký/MAC, nonce, timestamp, sequence, trạng thái dùng một lần và context nào? |
| **Tác động** | Replay có tạo phiên, thay đổi mật khẩu, thêm credential, đọc dữ liệu, thanh toán hay lặp thao tác không? |
| **Phát hiện và ứng phó** | Có log đủ điều tra, revoke credential/session, khóa key và khắc phục hậu quả không? |

Ví dụ threat scenario:

~~~text
Tài sản: quyền tạo lệnh chuyển tiền của dịch vụ thanh toán.
Điểm yếu: API chỉ kiểm tra HMAC và timestamp, không lưu nonce đã dùng.
Khả năng attacker: đọc được request qua log debug bị lộ.
Khai thác: gửi lại request đã ký trong cửa sổ 5 phút.
Tác động: lệnh chuyển tiền được tạo lần thứ hai.
Kiểm soát:
  - ký method/path/body hash/audience/timestamp/nonce;
  - replay store atomic, UNIQUE(key_id, nonce);
  - authorization và hạn mức trên từng lệnh;
  - idempotency theo transaction intent;
  - redaction log và quy trình rotate/revoke key.
~~~

Threat model cần phân biệt hai kịch bản: attacker chỉ có request đã ký, và attacker đã chiếm được secret/private key. Trong kịch bản thứ hai, attacker có thể tạo **request mới** và nonce mới; replay cache không ngăn được hành vi đó. Cần thu hồi credential, bảo vệ khóa, giới hạn quyền và điều tra runtime bị xâm nhập.

## 13. Checklist phòng chống replay

Trước khi phát hành một luồng authentication hoặc API lên production, hãy rà soát:

1. Thông điệp nào có thể bị thu và gửi lại? Attacker có thể quan sát nó ở đâu?
2. Bằng chứng có gắn với challenge/nonce, sequence hoặc request ID mới theo đúng giao thức không?
3. Verifier có kiểm tra đúng principal, credential, audience, purpose, flow và endpoint không?
4. Có thời hạn phù hợp và kiểm tra timestamp/clock skew ở phía server không?
5. Trạng thái đã dùng có được lưu bền vững và cập nhật nguyên tử giữa các node không?
6. TTL của replay cache có bao phủ toàn bộ cửa sổ chấp nhận, kể cả độ trễ và lệch đồng hồ không?
7. Có phân biệt replay với relay/phishing thời gian thực và có ràng buộc origin/verifier khi cần không?
8. OTP/TOTP/HOTP/token reset/magic link có bị từ chối sau lần sử dụng thành công theo chính sách không?
9. Session/access token có khả năng thu hồi, thời hạn và cơ chế giảm rủi ro bearer-token replay không?
10. API request đã ký có canonicalization chặt, nonce duy nhất, audience và body được ràng buộc không?
11. Idempotency có xử lý retry nghiệp vụ riêng, ràng buộc principal/payload và lưu kết quả nhất quán không?
12. Khi replay store hoặc dịch vụ thời gian gặp lỗi, endpoint nhạy cảm có fail closed không?
13. Có giám sát replay, cảnh báo hành vi bất thường, log không chứa secret và quy trình rotate/revoke credential không?

**Kết luận:** Replay khai thác việc hệ thống chấp nhận lại một bằng chứng hoặc yêu cầu từng hợp lệ. Chống replay đòi hỏi freshness, ràng buộc ngữ cảnh và trạng thái tiêu thụ một lần được kiểm tra an toàn trong toàn hệ thống. Nonce, timestamp, sequence, OTP một lần, token ràng buộc người gửi và idempotency giải quyết các phần khác nhau của vấn đề; không biện pháp đơn lẻ nào thay thế việc bảo vệ credential, session, authorization và quy trình ứng phó khi khóa bị lộ.
