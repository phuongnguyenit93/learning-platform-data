# Challenge và response

## 1. Challenge–response là gì?

**Challenge–response** là một mẫu giao thức xác thực: bên xác minh (*verifier*) đưa ra một yêu cầu thử thách (*challenge*), còn bên đang chứng minh danh tính (*claimant/prover*) tạo một **response** dựa trên credential hoặc một bí mật/khóa mà mình kiểm soát. Verifier kiểm tra response theo quy tắc giao thức rồi mới quyết định có chấp nhận bằng chứng xác thực hay không.

Điểm cốt lõi là **chứng minh quyền kiểm soát credential trong một lần tương tác cụ thể**. Nếu thiết kế đúng, bên chứng minh có thể không cần gửi nguyên khóa bí mật. Ví dụ, thiết bị dùng khóa riêng để ký một challenge ngẫu nhiên; máy chủ dùng khóa công khai đã đăng ký để kiểm tra chữ ký.

Ví dụ trực giác: thay vì hỏi “Mật khẩu của bạn là gì?”, dịch vụ gửi một chuỗi ngẫu nhiên chưa từng dùng. Thiết bị tạo chữ ký trên chuỗi đó bằng khóa riêng mà dịch vụ đã biết khóa công khai tương ứng. Chữ ký kiểm tra được và đúng ngữ cảnh cho thấy người phản hồi **có khả năng sử dụng khóa** tại thời điểm này. Điều đó không tự chứng minh ai đang cầm thiết bị ngoài đời, tài khoản có quyền gì, hay hành động sau đăng nhập có hợp lệ không.

Đây là nội dung thuộc chương **Authentication flow** của module `SECURITY_AUTHENTICATION_FUNDAMENTALS`: người học cần hiểu luồng credential → challenge → bằng chứng → xác minh → phiên/token, nhận biết các ranh giới tin cậy và phòng chống phishing, replay, lạm dụng đăng nhập trong thiết kế thực tế.

| Thuật ngữ | Vai trò |
| --- | --- |
| **Claimant / prover** | Bên muốn chứng minh quyền kiểm soát credential; có thể là người dùng trên thiết bị hoặc dịch vụ máy–máy. |
| **Verifier** | Bên kiểm tra response và quyết định bằng chứng có hợp lệ theo giao thức không. |
| **Credential / key** | Bí mật chia sẻ, khóa riêng, hoặc dữ liệu xác thực đã gắn với principal. |
| **Challenge** | Dữ liệu hoặc thông điệp do giao thức quy định để làm mới và ràng buộc lần chứng minh. |
| **Response** | MAC, chữ ký, giá trị chứng minh hoặc cấu trúc phản hồi được tính từ challenge và credential. |
| **Principal** | Danh tính mà verifier ánh xạ từ credential đã được đăng ký hoặc cấp phát. |
| **Authentication result** | Kết quả xác minh có ngữ cảnh, sau đó có thể dẫn tới session/token theo chính sách. |

Không phải mọi hệ thống đăng nhập đều sử dụng challenge–response theo cùng cách. Việc gửi mật khẩu qua một kết nối TLS được bảo vệ, nhập TOTP theo đồng hồ, chạy WebAuthn, xác thực mTLS hay thực hiện một giao thức PAKE có **cơ chế chống replay, kiểm tra bí mật và ranh giới tin cậy khác nhau**.

## 2. Luồng cơ bản và điểm ra quyết định

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client/prover
    participant V as Verifier
    participant S as Kho challenge/credential
    C->>V: Bắt đầu xác thực: principal hoặc credential hint
    V->>S: Tạo challenge mới, lưu ngữ cảnh và hạn dùng
    S-->>V: challengeId và challenge
    V-->>C: challengeId, challenge, tham số giao thức
    C->>C: Tạo response bằng credential/khóa
    C->>V: challengeId, response
    V->>S: Tải record và credential đã đăng ký
    S-->>V: Record, principal và trạng thái
    V->>V: Kiểm tra response, mục đích và ngữ cảnh
    V->>S: Đánh dấu challenge đã dùng theo thao tác nguyên tử
    S-->>V: Thành công hoặc đã hết hạn/đã dùng
    alt Bằng chứng và chính sách hợp lệ
        V-->>C: Thiết lập phiên/token theo chính sách
    else Không hợp lệ
        V-->>C: Từ chối, phản hồi lỗi không làm lộ bí mật
    end
~~~

Đây là sơ đồ khái niệm. Khi triển khai, một số giao thức tự mã hóa challenge vào thông điệp; một số dùng trạng thái phía server; một số handshake có thêm nhiều bước và xác nhận hai chiều. Việc đánh dấu đã dùng phải **gắn với quyết định thành công của lần chứng minh**, ngăn nhiều yêu cầu đồng thời dùng lại cùng challenge. Khi kiểm tra thất bại, hệ thống có thể từ chối hoặc hủy challenge theo chính sách chống lạm dụng; không nên tạo khả năng khóa tài khoản dễ dàng vì người ngoài cố ý gửi response sai.

Ba kết luận cần tách biệt:

1. **Response hợp lệ:** bên phản hồi thỏa điều kiện mật mã hoặc quy tắc kiểm tra đối với challenge.
2. **Authentication thành công:** response hợp lệ **và** credential/principal được phép sử dụng trong ngữ cảnh hiện tại.
3. **Hành động được phép:** authorization, trạng thái tài khoản, yêu cầu step-up và chính sách nghiệp vụ cũng cho phép thao tác.

Một response được tính đúng bằng khóa đã bị thu hồi không được chấp nhận. Một response được chấp nhận để **đăng nhập** không tự cấp quyền **chuyển tiền**.

## 3. Challenge tốt cần những thuộc tính nào?

### 3.1. Tính mới, tính duy nhất và tính khó đoán

Trong nhiều giao thức, challenge là một **nonce** (*number used once*): giá trị dùng cho một lần chứng minh. Để bảo vệ trước việc dự đoán hoặc chuẩn bị response từ trước, nonce do verifier tạo bằng **CSPRNG** và có độ ngẫu nhiên đủ lớn theo đặc tả giao thức.

Ví dụ Node.js tạo 32 byte ngẫu nhiên:

~~~ts
import { randomBytes } from "node:crypto";

const challenge = randomBytes(32).toString("base64url");
// 32 byte ngẫu nhiên = 256 bit trước khi mã hóa.
// Lưu ngữ cảnh phía server; chỉ gửi challenge qua kênh phù hợp.
~~~

Độ dài biểu diễn Base64URL không phải entropy; entropy đến từ đầu ra CSPRNG. Không tạo challenge bằng `Math.random()`, timestamp, ID tăng dần hoặc chuỗi đơn giản có thể đoán. Timestamp vẫn có ích cho **kiểm tra thời gian**, nhưng riêng timestamp không tạo challenge khó đoán.

**Tính duy nhất** giúp tránh hai lần xác thực dùng chung dữ liệu thử thách. **Tính khó đoán** giúp chống người tấn công chuẩn bị response hợp lệ trước khi challenge được phát ra. Tuy nhiên, yêu cầu cụ thể về nonce, chống lặp và độ dài phụ thuộc từng giao thức; không nên tự đặt cấu trúc trái với đặc tả đã chuẩn hóa.

### 3.2. Có hiệu lực trong khoảng thời gian ngắn

Một challenge thường có `issuedAt` và `expiresAt`, hoặc giới hạn tương đương. Hạn dùng càng dài thì cửa sổ khai thác challenge hoặc response bị lộ càng lớn. Khi quá hạn, verifier từ chối và client phải yêu cầu challenge mới.

Hạn dùng **không thay thế chống dùng lại**. Một response bị chụp trong cửa sổ 60 giây vẫn có thể bị kẻ tấn công gửi lần thứ hai nếu verifier không ghi nhận challenge đã được chấp nhận.

### 3.3. Có mục đích và ngữ cảnh được xác thực

Challenge nên gắn được với **ai, bên nào, tác vụ nào, phiên nào, credential nào**. Một nonce đơn độc không giải quyết hết tình huống response hợp lệ nhưng được chuyển sang giao thức hoặc mục đích khác.

| Trường hoặc ràng buộc | Mục đích bảo vệ |
| --- | --- |
| `challengeId` và nonce ngẫu nhiên | Phân biệt lần thử; ngăn chấp nhận lặp. |
| Principal hoặc credential ID dự kiến | Response của khóa A không bị ánh xạ tùy ý sang tài khoản B. |
| Verifier / RP ID / audience | Phân biệt dịch vụ nhận và giới hạn nơi bằng chứng được sử dụng. |
| Purpose và phiên bản giao thức | Ngăn dùng response “đăng nhập” thành response “đổi khóa” hoặc lẫn thông điệp giữa các protocol. |
| Flow ID / session liên quan | Chống hoán đổi challenge–response giữa hai lượt đăng nhập đang diễn ra. |
| Thời hạn và trạng thái `pending/used` | Giới hạn cửa sổ hiệu lực và ngăn phát lại. |
| Nội dung hành động hoặc transaction digest khi cần | Gắn sự xác nhận với đúng hành động và tham số quan trọng. |

Các thuộc tính trên có thể nằm trong **bản ghi tin cậy phía verifier**, trong **transcript được ký/MAC**, hoặc được bảo vệ bằng cơ chế chuẩn của giao thức. Chỉ gửi `purpose=transfer` ở trường client tự sửa được mà không kiểm tra hoặc ràng buộc nó khi xác minh **không** giúp bảo vệ mục đích.

Không nên cứng nhắc ràng buộc authentication bằng IP hay User-Agent như bằng chứng mật mã: IP có thể thay đổi do mạng di động/NAT/proxy, còn User-Agent dễ giả mạo. Có thể dùng chúng làm tín hiệu đánh giá rủi ro, nhưng không thay cho kiểm tra khóa và phiên.

## 4. Response được tính bằng gì?

### 4.1. Khóa bí mật chia sẻ: HMAC

Client và verifier cùng biết khóa bí mật entropy cao. Client tính **MAC** trên challenge cùng ngữ cảnh giao thức; verifier tính lại bằng khóa tương ứng và so sánh an toàn.

~~~text
message = encode_canonical(
    protocol_version,
    verifier_id,
    purpose,
    challenge_id,
    challenge_bytes
)
response = HMAC-SHA256(shared_secret, message)
~~~

`encode_canonical` phải được định nghĩa chặt chẽ, có phân tách trường không nhập nhằng; hai bên phải tạo **cùng một chuỗi byte**. Đừng nối tùy ý các chuỗi không có cách phân tách thống nhất, vì các tập trường khác nhau có thể tạo cùng transcript. Đây là nguyên lý, chưa phải một giao thức HMAC hoàn chỉnh cho production.

Ưu điểm: secret không cần gửi trong mỗi response. Giới hạn: cả hai phía đều có khả năng tính MAC, nên verifier thường cũng nắm secret hoặc giá trị tương đương; nếu một bên bị xâm nhập thì credential có thể bị lạm dụng. Response bị chuyển tiếp **theo thời gian thực** vẫn là một nguy cơ nếu không có ràng buộc phù hợp.

**Không nên tự áp dụng HMAC(challenge, mật khẩu do người dùng đặt) như một “giao thức đăng nhập an toàn”.** Mật khẩu có entropy thấp; kẻ nghe thấy challenge và response có thể thử đoán mật khẩu ngoại tuyến. Các giao thức dùng mật khẩu cần chống tấn công từ điển và xử lý đúng việc lưu verifier, ví dụ PAKE được thiết kế chuyên biệt, hoặc kiến trúc mật khẩu qua TLS với băm mật khẩu an toàn ở server.

### 4.2. Khóa bất đối xứng: chữ ký số

Client giữ **khóa riêng**, verifier lưu **khóa công khai** gắn với credential. Client ký dữ liệu challenge và ngữ cảnh; verifier kiểm tra chữ ký:

~~~text
response = Sign(private_key, transcript)
accepted = Verify(public_key, transcript, response)
~~~

Ưu điểm quan trọng là máy chủ không cần lưu khóa riêng của client để xác minh. Điều này giảm tác hại của việc lộ cơ sở dữ liệu chứa public key (vẫn cần bảo vệ việc đăng ký/thay đổi khóa). Tuy vậy, chữ ký đúng không chứng minh khóa được bảo vệ trước mã độc hoặc người dùng không bị lừa ký sai nội dung.

### 4.3. Các cơ chế có challenge nhưng không dùng cùng công thức

| Cơ chế | Vai trò của challenge / freshness | Lưu ý |
| --- | --- | --- |
| **WebAuthn/passkey** | Relying party tạo challenge; authenticator ký cấu trúc có ngữ cảnh client và RP ID. | Phải kiểm tra `challenge`, `origin`, RP ID hash, credential ID, chữ ký, cờ UP/UV và chính sách. |
| **mTLS / TLS client certificate** | Handshake mật mã chứng minh khả năng dùng khóa riêng trong transcript được bảo vệ. | Dùng thư viện TLS chuẩn; kiểm tra trust chain, tên/định danh, hiệu lực và chính sách chứng chỉ. |
| **PAKE (ví dụ một biến thể chuẩn)** | Hai bên trao đổi thông điệp giao thức để chứng minh bí mật mật khẩu mà hạn chế đoán ngoại tuyến. | Không tự ghép các phép hash/HMAC thay cho PAKE; phải dùng triển khai được đánh giá kỹ. |
| **TOTP** | Giá trị thay đổi theo bước thời gian, thường không có challenge ngẫu nhiên do server gửi. | Mã có thể bị phishing, phát lại trong cửa sổ và cần chặn dùng lại theo chính sách. |
| **OTP qua SMS/email** | Mã do dịch vụ phát và kiểm tra trong luồng; thực chất là chứng minh quyền tiếp cận kênh nhận mã. | Không mặc nhiên chống phishing hoặc chứng minh danh tính pháp lý. |
| **Push approval** | Thiết bị nhận yêu cầu và có thể xác nhận số/thông tin ngữ cảnh. | Phải chống spam push, nhấn nhầm, mạo danh và xử lý hành động không đúng ý định. |

Do vậy, **challenge–response là mẫu thiết kế**, không phải tên của một thuật toán hay bằng chứng đủ rằng giao thức đã chống phishing.

## 5. Ví dụ minh họa: kiểm tra HMAC challenge–response

Giả sử hai dịch vụ backend đã chia sẻ một secret ngẫu nhiên 32 byte qua cơ chế cấp phát được bảo vệ. Mục tiêu là xác thực dịch vụ A khi gọi một endpoint dành cho chính A. Ví dụ sau chỉ mô tả các kiểm soát cốt lõi; ứng dụng thực tế cần kho trạng thái bền vững, kiểm soát đồng thời, hạn mức thử, giám sát và cơ chế phân quyền.

Khi phát challenge, verifier tạo nonce mới, ghi `challengeId`, `keyId`, `purpose`, `verifierId`, `flowId`, thời hạn và trạng thái `pending`. Những trường quyết định tin cậy phải được lưu ở phía server hoặc được xác thực mật mã; không nhận bản sao tùy ý do client sửa.

Ví dụ pseudocode TypeScript cho phần **kiểm tra**:

~~~ts
import { createHmac, timingSafeEqual } from "node:crypto";

// encodeFields là mã hóa nhị phân không nhập nhằng:
// mỗi trường được gắn độ dài (length-prefix) và quy tắc UTF-8 rõ ràng.
declare function encodeFields(...parts: (string | Buffer)[]): Buffer;
declare function loadPendingChallenge(id: string): Promise<Challenge | null>;
declare function loadActiveKey(keyId: string): Promise<KeyRecord | null>;
declare function consumeIfStillPending(
  challengeId: string,
  flowId: string,
  now: Date
): Promise<boolean>; // Kiểm tra trạng thái và cập nhật atomically
declare function issueSessionFor(subjectId: string): Promise<unknown>;

type Challenge = {
  id: string;
  keyId: string;
  nonce: Buffer; // 32 byte ngẫu nhiên, tạo bởi verifier
  verifierId: string;
  purpose: "login";
  flowId: string;
  expiresAt: Date;
};
type KeyRecord = {
  secret: Buffer; // ví dụ này: secret chung được bảo vệ
  subjectId: string;
  revoked: boolean;
};

async function finishAuthentication(
  challengeId: string,
  flowId: string,             // flow được ràng buộc với client
  receivedMac: Buffer,       // đã kiểm tra kích thước/định dạng
  now: Date
) {
  const challenge = await loadPendingChallenge(challengeId);
  if (!challenge || challenge.flowId !== flowId ||
      challenge.purpose !== "login" || now >= challenge.expiresAt) {
    return null;
  }

  const key = await loadActiveKey(challenge.keyId);
  if (!key || key.revoked) return null;

  const transcript = encodeFields(
    "auth-challenge/v1",
    challenge.verifierId,
    challenge.purpose,
    challenge.id,
    challenge.nonce
  );
  const expected = createHmac("sha256", key.secret).update(transcript).digest();
  if (receivedMac.length !== expected.length ||
      !timingSafeEqual(receivedMac, expected)) {
    return null;
  }

  // Chỉ một request đồng thời được chuyển pending -> used.
  // Điều kiện consume phải kiểm tra cả deadline và ràng buộc flow.
  const consumed = await consumeIfStillPending(challenge.id, flowId, now);
  if (!consumed) return null;

  return issueSessionFor(key.subjectId);
}
~~~

**Các giả định bảo mật cần bổ sung khi dùng ví dụ:**

- `flowId` phải được ràng buộc với phiên bắt đầu xác thực qua cookie hoặc cơ chế giao thức đáng tin, không đơn thuần là chuỗi client tự chọn không được kiểm tra.
- `verifierId` phải được kiểm tra với dịch vụ thực sự nhận response; không cho client tự đổi thành tên dịch vụ khác.
- Kho challenge phải bảo đảm cập nhật **nguyên tử** (compare-and-set/transaction) và các node API nhìn thấy cùng trạng thái đã dùng; chỉ `get` rồi `set` trong hai thao tác riêng dễ bị race condition.
- `loadActiveKey` phải trả về **đúng secret đã liên kết với chủ thể**, với trạng thái hiện tại, quyền/tenant hợp lệ và cách quản lý bí mật phù hợp. Đây chỉ là mô hình khóa chia sẻ cho backend tin cậy.
- `issueSessionFor` chỉ thực thi sau mọi kiểm tra; phiên được cấp có expiry, chính sách thu hồi và kiểm tra quyền riêng. Cần chính sách rõ khi thao tác cấp phiên thất bại sau lúc challenge đã được tiêu thụ: client thường phải bắt đầu lượt mới.
- Không log `key.secret`, nguyên response hoặc toàn bộ credential; giới hạn số lần thử, tốc độ tạo challenge, thời hạn, tổng số challenge đang pending và lỗi trả về công khai.

Ví dụ cố tình **không** thay các chuẩn như WebAuthn, TLS hoặc PAKE. Khi có chuẩn phù hợp, nên dùng thư viện được đánh giá và không tự tạo giao thức mật mã bằng các đoạn mã minh họa.

## 6. Replay: tại sao “response đúng” vẫn có thể là tấn công?

**Replay attack** là việc gửi lại một thông điệp xác thực đã được sử dụng hoặc quan sát trước đó để cố đạt cùng một kết quả. Nếu verifier chỉ kiểm tra chữ ký/MAC đúng với một challenge tĩnh, response hợp lệ hôm qua có thể được chấp nhận hôm nay.

Ví dụ sai:

~~~text
Server: "Hãy ký chuỗi LOGIN."
Client: Sign(private_key, "LOGIN") -> signature_1
Attacker ghi lại signature_1.
Hôm sau server vẫn yêu cầu ký "LOGIN".
Attacker gửi lại signature_1 -> chữ ký vẫn đúng.
~~~

Ví dụ đúng hướng:

~~~text
Lần 1: nonce_A ngẫu nhiên -> response_A -> chấp nhận 1 lần -> nonce_A USED
Lần 2: nonce_B khác nonce_A -> chỉ response_B phù hợp
Gửi lại response_A với nonce_A -> bị từ chối vì USED
Gửi response_A với nonce_B -> sai chữ ký/MAC
~~~

**Freshness** thường cần nhiều lớp: nonce khó đoán, thời hạn ngắn, xác minh phiên/ngữ cảnh, và từ chối dùng lại khi giao thức yêu cầu. Một nonce không cần giữ bí mật; giá trị của nó nằm ở tính mới, tính khó đoán và cách verifier sử dụng đúng.

### 6.1. Replay và relay không giống nhau

Chống replay **không đồng nghĩa** chống **relay/phishing theo thời gian thực**. Kẻ tấn công có thể mở phiên thật tới verifier, chuyển challenge tới nạn nhân, dụ nạn nhân tạo response rồi chuyển ngược lại **trước khi challenge bị dùng**. Khi đó response mới, hợp lệ và chưa từng phát lại.

~~~mermaid
sequenceDiagram
    participant A as Kẻ tấn công
    participant V as Verifier thật
    participant U as Nạn nhân
    A->>V: Bắt đầu login
    V-->>A: Challenge mới
    A->>U: Chuyển tiếp challenge, dụ ký
    U-->>A: Response hợp lệ
    A->>V: Chuyển response trước khi hết hạn
    V-->>A: Nếu giao thức thiếu ràng buộc: session
~~~

Để giảm kiểu tấn công này, giao thức cần ràng buộc bằng chứng với **bên xác minh/origin, kênh hoặc mục đích** phù hợp, kết hợp chống phishing ở cấp giao thức. WebAuthn được thiết kế để ràng buộc credential vào RP ID và client vào origin; một hệ thống tự thiết kế HMAC/chữ ký đơn giản không tự có thuộc tính đó.

Nếu người dùng đang đăng nhập tại website giả, chỉ hiển thị logo hoặc tên miền trong nội dung challenge mà thiết bị/người dùng không xác minh độc lập, thì kẻ tấn công vẫn có thể lừa họ phản hồi. **Định danh verifier phải được kiểm tra bởi thành phần tin cậy**, không chỉ ghi vào chuỗi hiển thị.

## 7. WebAuthn/passkey: challenge–response có ràng buộc origin

Với WebAuthn, server của **relying party (RP)** tạo challenge ngẫu nhiên khi xác thực. Trình duyệt gọi WebAuthn API, authenticator ký bằng khóa riêng gắn với credential đã đăng ký. Response chứa các cấu trúc như `clientDataJSON`, `authenticatorData`, `signature` và credential ID.

Thay vì chỉ kiểm tra “chữ ký đúng cho nonce”, server phải xác minh đầy đủ theo thư viện WebAuthn:

1. **`clientDataJSON.type`** phù hợp thao tác xác thực, thường là `webauthn.get`.
2. **Challenge** nhận về bằng đúng challenge đã phát, còn trong thời hạn và gắn đúng phiên/lượt đăng nhập; tiêu thụ theo chính sách.
3. **`origin`** là một origin được RP chấp nhận; kiểm tra ngữ cảnh iframe/cross-origin khi có hỗ trợ và chính sách tương ứng.
4. **RP ID hash** trong authenticator data đúng RP ID dự kiến; không chấp nhận giá trị RP ID do yêu cầu không tin cậy tùy ý cung cấp.
5. **Credential ID và public key** đúng credential đã đăng ký cho tài khoản/chủ thể; chữ ký phải kiểm tra trên dữ liệu được đặc tả quy định: `authenticatorData || SHA-256(clientDataJSON)`.
6. **User Presence (UP)** và **User Verification (UV)** đáp ứng chính sách của RP; lưu ý UV có thể là PIN hoặc sinh trắc học thực hiện cục bộ trên thiết bị.
7. **Credential status và sign counter** được xử lý theo quy định và đặc điểm authenticator. Counter không phải lúc nào cũng tăng đơn điệu trên passkey đồng bộ hoặc một số authenticator; không tự suy ra mọi trường hợp counter không tăng đều là đánh cắp khóa.

~~~mermaid
flowchart LR
    RP["RP tạo challenge"] --> Browser["Browser nhận tùy chọn WebAuthn"]
    Browser --> Auth["Authenticator dùng private key"]
    Auth --> Response["authenticatorData + clientDataJSON + signature"]
    Response --> Verify["RP kiểm tra challenge, origin, RP ID, chữ ký, UP/UV"]
    Verify --> Result{"Đúng chính sách?"}
    Result -->|Có| Session["Cấp session và kiểm tra quyền riêng"]
    Result -->|Không| Reject["Từ chối"]
~~~

Passkey có khả năng chống phishing tốt hơn OTP truyền thống nhờ **ràng buộc origin/RP ID được thực thi theo giao thức**, không nhờ nonce đơn độc. Nhưng passkey **không** thay cho bảo vệ phiên sau khi đăng nhập, kiểm soát quyền, phòng chống XSS, hoặc quy trình thêm thiết bị/khôi phục tài khoản an toàn.

## 8. Challenge–response trong các luồng xác thực khác

### 8.1. Mật khẩu và cơ chế challenge

Mật khẩu thường yếu hơn khóa ngẫu nhiên vì do con người chọn. Phương án phổ biến là gửi mật khẩu qua kết nối TLS đã xác thực server, rồi kiểm tra ở server bằng hàm băm mật khẩu có salt và chi phí thích hợp (ví dụ Argon2id). Cách này **không phải** challenge–response dựa trên nonce đối với mật khẩu, nhưng vẫn có thể là kiến trúc hợp lệ khi triển khai đúng, có hạn chế tốc độ, chống credential stuffing và MFA thích hợp.

Việc thay bằng `SHA-256(password || challenge)` hoặc `HMAC(password, challenge)` tự thiết kế có thể khiến kẻ quan sát response thử mật khẩu ngoại tuyến, nhất là khi challenge công khai. Với yêu cầu chứng minh mật khẩu không gửi bí mật trực tiếp, cần một **PAKE** chuẩn có mô hình an toàn và triển khai được đánh giá kỹ; không tự tạo giao thức từ các phép hash đơn lẻ.

### 8.2. OTP và kiểm tra một lần

TOTP dựa trên secret và **bước thời gian**, nên không luôn là “server phát challenge ngẫu nhiên”. Một mã TOTP có thể được chấp nhận trong một cửa sổ thời gian; nếu hệ thống không theo dõi trạng thái sử dụng, mã có thể được dùng lại trong cửa sổ ấy tùy chính sách. Cần giới hạn thử, kiểm soát sai lệch đồng hồ và từ chối phát lại theo thiết kế khi thích hợp.

Mã OTP gửi qua SMS/email có thể xem như yêu cầu thử thách qua kênh liên hệ; hệ thống cần mã ngẫu nhiên đủ mạnh, hạn dùng ngắn, ràng buộc với đúng flow, hạn chế thử và trạng thái một lần. Tuy nhiên, kẻ tấn công có thể dụ người dùng nhập mã ngay vào trang giả rồi chuyển tiếp. Bởi vậy, “dùng một lần” không tự đồng nghĩa “chống phishing”.

### 8.3. mTLS và chứng minh khóa riêng

Trong TLS có xác thực client bằng chứng chỉ, **handshake protocol** chứa dữ liệu mới và transcript mật mã. Client chứng minh khả năng sử dụng private key qua các bước được TLS quy định; server kiểm tra chứng chỉ và chính sách tin cậy. Không tự tạo “TLS challenge” bằng cách gửi một chuỗi rồi ký mà bỏ qua kiểm tra chứng chỉ, handshake, mục đích sử dụng khóa và ràng buộc phiên.

### 8.4. OAuth/OIDC: các giá trị gọi là challenge nhưng khác mục đích

Trong OAuth 2.0 Authorization Code với **PKCE**, client tạo `code_verifier` và đưa `code_challenge` dẫn xuất vào yêu cầu ủy quyền. Khi đổi authorization code lấy token, client trình `code_verifier` để ràng buộc việc đổi code với bên đã bắt đầu luồng. **PKCE không tự chứng minh danh tính người dùng** và không thay việc xác thực tại authorization server.

Trong OpenID Connect, tham số `nonce` có thể được dùng để liên kết ID token với yêu cầu xác thực và giảm một số rủi ro token injection/replay theo luồng. `state` chủ yếu giúp liên kết phản hồi ủy quyền và bảo vệ chống một số kiểu CSRF/lẫn phiên; chúng không phải thay thế cho WebAuthn challenge hoặc authorization ở API.

Mỗi khái niệm có **bên sinh, nơi kiểm tra và mục tiêu an ninh** riêng. Không suy ra chỉ cần có trường tên `nonce` hay `challenge` thì mọi thành phần đã được bảo vệ.

## 9. Step-up authentication và xác nhận giao dịch

Một phiên đã đăng nhập có thể cần **step-up authentication** khi thao tác tăng rủi ro: thêm passkey mới, tắt MFA, đổi email khôi phục, cấp quyền quản trị hoặc chuyển tiền.

Challenge dành cho step-up phải có **purpose riêng**, gắn với subject và phiên hiện tại, đồng thời có hạn dùng ngắn và được tiêu thụ đúng lúc. Nếu yêu cầu xác nhận một giao dịch cụ thể, giao thức cần ràng buộc bằng chứng với nội dung quan trọng của giao dịch, chẳng hạn:

~~~json
{
  "purpose": "approve-transfer",
  "transactionId": "tx_1045",
  "fromAccount": "acc_A",
  "toAccount": "acc_B",
  "amountMinor": 2500000,
  "currency": "VND",
  "challengeId": "ch_8f7d",
  "expiresAt": "2026-11-22T08:00:00Z"
}
~~~

Đây là **ví dụ mô hình dữ liệu**, không phải cấu trúc đã được bảo vệ. Server cần xây dựng transcript/digest của **các trường chính thức** theo cách mã hóa không nhập nhằng, đưa vào dữ liệu được ký/MAC, hiển thị thông tin đáng tin để người dùng hiểu mình đang xác nhận gì, rồi **kiểm tra lại dữ liệu giao dịch ngay trước khi thực hiện**. Nếu tài khoản nhận tiền hoặc số tiền có thể bị thay đổi sau lúc ký mà vẫn được chấp nhận, việc ký challenge không đạt mục tiêu bảo vệ ý định giao dịch.

Khi thao tác có thể được gửi lại do mất mạng, phải phân biệt:

- **Chống dùng lại challenge:** cùng một bằng chứng không thể mở nhiều lần xác thực/phê duyệt độc lập.
- **Idempotency của nghiệp vụ:** cùng một yêu cầu thanh toán có `transactionId`/idempotency key phù hợp không được tạo nhiều giao dịch trùng.

Đây là hai vấn đề khác nhau. Một nonce đã tiêu thụ không thay cho xử lý giao dịch nguyên tử, phê duyệt theo chính sách, hạn mức và nhật ký kiểm toán.

## 10. Các lỗi thiết kế phổ biến

| Lỗi | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Challenge cố định cho mọi lần đăng nhập | Response đã thu được có thể được phát lại. | Sinh mới theo giao thức, có hiệu lực và kiểm soát sử dụng. |
| Nonce từ timestamp, bộ đếm công khai hoặc `Math.random()` | Có thể đoán hoặc chuẩn bị trước response. | CSPRNG và độ ngẫu nhiên theo chuẩn áp dụng. |
| Chỉ kiểm tra chữ ký nhưng không kiểm tra challenge đã phát | Chữ ký của một message khác có thể được chấp nhận sai bối cảnh. | So với challenge và transcript tin cậy được lưu/gắn. |
| Không đánh dấu challenge đã dùng nguyên tử | Hai request đồng thời đều qua kiểm tra rồi cùng cấp session. | Compare-and-set/transaction hoặc cơ chế one-time có hiệu lực giữa các node. |
| Trộn response của hai phiên/tài khoản | Bằng chứng của principal A hoặc flow A bị gắn sang B. | Ràng buộc credential, subject, flow, verifier và purpose. |
| Tin `purpose`, `userId` hoặc `verified=true` do client tự gửi | Client tự nâng quyền hoặc chuyển mục đích sử dụng. | Lấy ngữ cảnh từ bản ghi/chứng thực phía server, xác minh transcript. |
| Tự tạo giao thức HMAC trên mật khẩu yếu | Có thể mở tấn công đoán mật khẩu ngoại tuyến. | Dùng PAKE chuẩn hoặc xác thực mật khẩu trên TLS với băm phía server. |
| Cho response quá hạn vẫn hợp lệ | Tăng cửa sổ khai thác. | Kiểm tra deadline phía server, giới hạn thời gian ngắn theo chính sách. |
| Chỉ có nonce mà tuyên bố chống phishing | Kẻ tấn công chuyển tiếp challenge/response theo thời gian thực. | Dùng cơ chế ràng buộc origin/verifier, WebAuthn hoặc giao thức thích hợp. |
| Không kiểm tra trạng thái credential sau chữ ký đúng | Credential bị thu hồi vẫn có thể được dùng. | Kiểm tra trạng thái khóa, tài khoản và chính sách trước cấp phiên. |
| Log toàn bộ response, secret hoặc token | Bằng chứng nhạy cảm lọt vào log. | Chỉ ghi metadata tối thiểu, che credential và bảo vệ log. |
| Thất bại rồi phát challenge vô hạn | Có thể tạo tải lớn hoặc hỗ trợ dò credential. | Giới hạn số challenge pending, tốc độ và số lần thử; giám sát lạm dụng. |
| Dùng challenge đăng nhập để phê duyệt giao dịch | Người dùng không xác nhận đúng nội dung nguy hiểm. | Purpose riêng, transcript ràng buộc tham số giao dịch và kiểm tra quyền. |

## 11. Thiết kế an toàn qua các ranh giới tin cậy

Challenge–response chỉ bảo đảm điều giao thức thực sự kiểm tra. Để triển khai trong hệ thống nhiều tầng, cần lần theo các ranh giới:

**Ranh giới trình duyệt/thiết bị → verifier.** Dữ liệu từ client là không tin cậy cho đến khi được xác minh. TLS bảo vệ kênh và xác thực server, nhưng không ngăn client đã bị xâm nhập. Với WebAuthn, trình duyệt và authenticator đóng vai trò thực thi origin/RP ID; với giao thức tự thiết kế, phải nêu rõ thành phần nào thực thi ràng buộc verifier.

**Ranh giới verifier → kho credential/challenge.** Verifier phải tra đúng credential, đảm bảo khóa chưa bị thu hồi, challenge chưa hết hạn hoặc dùng trước đó. Nếu nhiều instance cùng xử lý, trạng thái one-time phải nhất quán. Không được cấp phiên khi kho trạng thái không khả dụng và không thể kiểm tra điều kiện an toàn.

**Ranh giới verifier → session/token.** Chỉ cấp session hoặc token sau khi toàn bộ điều kiện đạt. Session cần cookie an toàn hoặc cơ chế token tương ứng, hạn dùng, khả năng thu hồi; bearer token bị lộ vẫn có thể được trình lại dù bước đăng nhập ban đầu dùng challenge–response mạnh.

**Ranh giới session/token → API nghiệp vụ.** API phải kiểm tra chính xác danh tính, tenant, scopes và **authorization cho từng hành động và tài nguyên**. Đăng nhập bằng passkey hoặc chữ ký HMAC không khiến yêu cầu đọc dữ liệu của người khác trở thành hợp lệ.

**Ranh giới khôi phục và liên kết danh tính.** Đường thêm credential, đặt lại mật khẩu, đổi email, liên kết IdP hoặc khôi phục tài khoản có thể bỏ qua bước chứng minh thông thường nếu thiết kế kém. Quy trình ấy phải có mức tin cậy phù hợp, giới hạn thử và ghi nhận thay đổi bảo mật.

Khi nhiều thành phần cùng tham gia, hãy trả lời: *ai tạo challenge, ai giữ ngữ cảnh, ai kiểm tra response, ai tiêu thụ challenge, ai cấp phiên, ai quyết định quyền?* Nếu trách nhiệm phân tán giữa browser, gateway, IdP và API, hợp đồng giữa các bên phải xác định rõ dữ liệu nào được phép tin.

## 12. Checklist triển khai challenge–response

1. **Mục tiêu:** response phải chứng minh sở hữu credential, chống replay, chống phishing hay phê duyệt một giao dịch? Đặc tính cần có đã được viết thành yêu cầu cụ thể chưa?
2. **Bằng chứng:** dùng khóa bí mật entropy cao, khóa riêng, passkey, mật khẩu/PAKE hay OTP? Giao thức có phù hợp với loại credential không?
3. **Nonce:** challenge được tạo đúng phía, bằng CSPRNG khi cần và có độ dài phù hợp chuẩn?
4. **Ngữ cảnh:** challenge và response gắn với đúng principal, credential, verifier, purpose, flow và dữ liệu hành động khi cần?
5. **Kiểm tra:** verifier có xác minh chữ ký/MAC hoặc bằng chứng theo đúng thuật toán, transcript và tiêu chí của giao thức chuẩn?
6. **Chống replay:** có thời hạn, trạng thái one-time hoặc cơ chế chống lặp tương đương, và kiểm soát đồng thời giữa các node?
7. **Chống relay/phishing:** đã hiểu giới hạn của nonce, và có ràng buộc origin/RP ID hoặc bảo vệ phù hợp thay vì chỉ dựa vào tên website hiển thị?
8. **Chống lạm dụng:** có giới hạn tốc độ tạo/kiểm tra challenge, số lượt sai, số challenge pending và cảnh báo hành vi bất thường?
9. **Vòng đời credential:** có kiểm tra trạng thái khóa/tài khoản, hỗ trợ thu hồi, đăng ký credential mới và khôi phục an toàn?
10. **Kết quả:** session/token chỉ được cấp sau khi xác minh đầy đủ, còn API nghiệp vụ luôn kiểm tra quyền độc lập?
11. **Thao tác nhạy cảm:** nếu step-up, có gắn đúng nội dung giao dịch, dùng dữ liệu từ server và giải quyết replay/idempotency theo hai lớp riêng?
12. **Quan sát:** có log ID và sự kiện đủ điều tra mà không ghi bí mật, response nhạy cảm hoặc token?

**Kết luận:** Challenge–response giúp bên xác minh yêu cầu một bằng chứng **mới, đúng khóa và đúng ngữ cảnh** thay vì chỉ tin vào một lời khai tĩnh. Độ an toàn phụ thuộc vào giao thức cụ thể: cách sinh và kiểm tra challenge, ràng buộc verifier/phiên/mục đích, chống replay và relay, cũng như vòng đời credential. Sau bước chứng minh, hệ thống vẫn phải quản lý session/token, phân quyền từng tài nguyên và bảo vệ luồng khôi phục tài khoản. 
