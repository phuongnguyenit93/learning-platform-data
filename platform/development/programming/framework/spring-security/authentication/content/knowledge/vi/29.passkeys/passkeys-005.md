# Challenge, thời hạn và kiểm tra đúng ngữ cảnh thao tác trong Passkey

Trong WebAuthn/Passkey, máy chủ (Relying Party, **RP**) gửi một **challenge ngẫu nhiên** cho trình duyệt trước khi đăng ký hoặc xác thực credential. Authenticator có khóa riêng để tạo kết quả WebAuthn, nhưng server chỉ có thể chấp nhận kết quả sau khi biết nó khớp **đúng thử thách đang chờ**, **đúng loại nghi thức**, **đúng website/RP**, **đúng phiên và danh tính** và, khi cần, **đúng thao tác nghiệp vụ**.

Một assertion có chữ ký hợp lệ **không tự động cho phép mọi request**. Challenge ngăn việc dùng lại bằng chứng cũ; thời hạn giới hạn cửa sổ sử dụng; còn ngữ cảnh ngăn bằng chứng của đăng nhập A bị dùng cho đăng ký B hoặc phê duyệt giao dịch C.

Bài học tập trung vào: cách tạo/lưu challenge, TTL thực thi phía server, atomic consume chống replay, kiểm tra WebAuthn ceremony và origin/RP ID, cách gắn challenge với session/account/operation, và cách áp dụng với Spring Security Servlet. Mã Java 17+ phía dưới minh họa **lớp quản lý challenge**, không phải trình xác minh chữ ký WebAuthn hoàn chỉnh.

## 1. Phân biệt registration, authentication và step-up

Hai nghi thức cốt lõi trong WebAuthn:

| Mục đích | Browser API | ClientDataJSON.type | Kết quả |
| --- | --- | --- | --- |
| **Đăng ký passkey** | `navigator.credentials.create()` | `webauthn.create` | Credential mới và public key để RP lưu cho account |
| **Xác thực bằng passkey** | `navigator.credentials.get()` | `webauthn.get` | Signed assertion để RP kiểm với public key đã đăng ký |

**Step-up** (xác thực lại trước hành động nhạy cảm) thường dùng ceremony `webauthn.get`, nhưng khác với login ở **ngữ cảnh ứng dụng**: đã có một session/account, có một operation cụ thể và kết quả phải được dùng đúng mục đích.

Một login flow tổng quát:

~~~text
Browser                 RP / Spring Security             Authenticator
   |                           |                              |
   |-- POST options ---------->|                              |
   |                           | Sinh challenge mới           |
   |                           | Lưu pending state + TTL      |
   |<-- publicKey options -----|                              |
   |-- navigator.credentials.get(options) -------------------->|
   |                           |                       UP / UV |
   |<------------------------ Signed assertion ----------------|
   |-- POST assertion -------->|                              |
   |                           | Consume pending challenge    |
   |                           | So khớp type, origin, RP ID   |
   |                           | Credential + signature       |
   |                           | Account + authorization      |
   |<-- authenticated / error -|                              |
~~~

Browser không có quyền tự quyết định rằng người dùng đã được xác thực. Chỉ server có thể xác minh credential, challenge và chính sách rồi tạo Authentication.

## 2. Challenge là gì?

Challenge là **một chuỗi byte ngẫu nhiên, không dự đoán được** do RP sinh cho một lần ceremony. Nó được gửi trong:

- `PublicKeyCredentialCreationOptions.challenge` cho đăng ký.
- `PublicKeyCredentialRequestOptions.challenge` cho xác thực.

Authenticator ký dữ liệu bao gồm hash của `clientDataJSON`; trong đó có challenge. Với authentication assertion, giá trị được ký là:

~~~text
authenticatorData || SHA-256(clientDataJSON)
~~~

Ví dụ một `clientDataJSON` do browser tạo:

~~~json
{
  "type": "webauthn.get",
  "challenge": "<base64url-cua-challenge-da-phat>",
  "origin": "https://login.example.org",
  "crossOrigin": false
}
~~~

Server phải **kiểm challenge trả về khớp challenge đã cấp và còn trong pending state**. Chữ ký trên một assertion cũ có thể vẫn hợp lệ về mặt toán học, nhưng không còn hợp lệ cho challenge mới.

Challenge **không phải secret**: browser nhìn thấy nó; nhiệm vụ của RP là chống việc đoán trước và sử dụng lại. Không tự nhét password, mã OTP, email hoặc số tiền giao dịch ở dạng plaintext vào challenge.

### Sinh challenge trong Java 17+

Ví dụ lớp Java dùng thư viện chuẩn:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class WebAuthnChallengeGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static String generate() {
        byte[] challenge = new byte[32];
        RANDOM.nextBytes(challenge);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(challenge);
    }
}
~~~

32 byte = 256 bit entropy từ nguồn ngẫu nhiên mật mã, được base64url không padding thành **43 ký tự**. Đây là lựa chọn thực hành mạnh; không phải số byte bắt buộc cho mọi implementation. Mỗi lần gọi phải cho một thử thách mới. Mã trên chỉ tạo challenge; không lưu pending state hoặc xác minh bất cứ assertion nào.

Những cách làm sai:

~~~text
challenge = username
challenge = currentTimeMillis()
challenge = "register" + accountId
challenge = hash(username) cố định
challenge = một chuỗi hardcode dùng cho mọi request
challenge = giá trị browser tự gửi để RP echo lại
~~~

Timestamp và username có thể được đoán trước. Hash dữ liệu dễ đoán không tạo thêm entropy. Dùng `SecureRandom`, không dùng `Math.random()` hoặc một ID tăng tuần tự làm challenge.

## 3. Mỗi challenge cần có pending state phía server

Chỉ lưu một chuỗi challenge ở browser là chưa đủ. RP nên lưu một bản ghi tạm mô tả **yêu cầu nào đang đợi response**.

Ví dụ bản ghi minh họa:

~~~yaml
challengeDigest: "server-stored-challenge-verifier"
ceremony: AUTHENTICATE
flowId: "flow-87"
sessionRef: "anonymous-session-42"
accountRef: null
tenantRef: "tenant-a"
rpId: "login.example.org"
expectedOrigin: "https://login.example.org"
userVerification: required
operationRef: null
createdAt: "2026-11-06T08:00:00Z"
expiresAt: "2026-11-06T08:02:00Z"
status: PENDING
~~~

Đây là **schema do ứng dụng tự thiết kế**, không phải JSON WebAuthn tiêu chuẩn. Server có thể lưu toàn bộ options hoặc bản ghi với các trường đủ để so sánh. Giá trị `accountRef` có thể rỗng nếu người dùng đăng nhập bằng discoverable credential mà chưa nhập username.

| Trường | Vai trò |
| --- | --- |
| Challenge hoặc digest tương ứng | So khớp dữ liệu challenge do browser trả về |
| Ceremony type | Ngăn `webauthn.create` bị chấp nhận như `webauthn.get` |
| Session/flow reference | Không nhận kết quả của browser/flow khác |
| Account/tenant reference | Gắn đúng user với đăng ký hoặc step-up |
| Expected RP ID / origin | Ngăn sai website hoặc sai scope credential |
| Expected credential IDs, nếu có | Giới hạn credential được phép dùng trong username-first flow |
| User verification requirement | Không hạ từ `required` thành `preferred` |
| Operation reference | Gắn step-up với hành động được yêu cầu |
| ExpiresAt + status | TTL, replay protection, audit |
| Correlation/rate-limit key | Giới hạn và chẩn đoán |

Trạng thái này phải do server quản lý; client không được tự sửa `accountRef`, `ceremony` hay `expiresAt`. Trong môi trường nhiều node, dùng session store, Redis hoặc database có semantics phù hợp, không dựa vào một `static Map` chỉ tồn tại trên một JVM.

## 4. Thời hạn: browser timeout không phải server expiration

Ví dụ request options có thể chứa:

~~~json
{
  "challenge": "<challenge-base64url>",
  "timeout": 120000,
  "rpId": "login.example.org",
  "allowCredentials": [],
  "userVerification": "required"
}
~~~

`timeout` có đơn vị **millisecond**, dùng làm tín hiệu cho trình duyệt về thời gian ceremony. Nó không phải một quy tắc từ phía server để tự động từ chối mọi response nhận sau 120 giây.

**Server phải lưu và kiểm thời hạn riêng**, ví dụ:

~~~text
issuedAt:  2026-11-06T08:00:00Z
expiresAt: 2026-11-06T08:02:00Z
accept iff now < expiresAt
~~~

| Thời điểm nhận | Kết luận về TTL |
| --- | --- |
| 08:00:30Z | Còn hạn, tiếp tục kiểm WebAuthn |
| 08:01:59Z | Còn hạn |
| 08:02:00Z | Hết hạn theo `now >= expiresAt` |
| 08:03:00Z | Hết hạn dù browser vẫn nộp assertion |
| 08:00:30Z nhưng session đã logout | Từ chối theo session binding |

TTL 120 giây là **giá trị minh họa**; tiêu chuẩn WebAuthn khuyến nghị challenge chỉ có hiệu lực trong một khoảng tương xứng với timeout ceremony. Thời gian thực tế phải cân bằng nguy cơ replay với UX của người dùng/thiết bị.

Cần phân biệt:

- **Browser timeout:** điều khiển thời gian chờ UX; client có thể ngắt sớm hoặc hành vi có thể khác giữa thiết bị.
- **Challenge TTL server:** giới hạn thời gian server cho phép dùng pending state.
- **Session expiration:** có thể hết hạn trước challenge; session đã vô hiệu không được hồi sinh chỉ bằng assertion pending.
- **Step-up grant TTL:** quyền sử dụng kết quả xác minh lại cho thao tác nhạy cảm có một thời hạn riêng, thường ngắn và được dùng một lần.

Dùng `Instant` hoặc clock UTC phía server, không tin timestamp do client cung cấp; kiểm ranh giới bằng `now.isBefore(expiresAt)`. Nhầm giây với millisecond có thể tạo challenge tồn tại dài hơn dự kiến 1.000 lần.

## 5. Chống replay bằng atomic consume

Một challenge hợp lệ phải có **single-use semantics**. Giả sử browser hoặc mạng gửi hai requests song song chứa cùng một assertion:

~~~text
Request A                Shared store                Request B
    |                         |                          |
    |--- consume(challenge) ->|                          |
    |                         | Atomic read + delete     |
    |<--- pending state ------|                          |
    |                         |<-- consume(challenge) ---|
    |                         |--- missing ------------->|
    |                         |                 B bị từ chối
    v
A tiếp tục kiểm signature/contexts
~~~

Nếu server làm `GET`, kiểm signature rồi mới `DELETE` mà không có transaction/lock, hai requests có thể cùng thấy challenge chưa dùng. TTL **không** ngăn replay trong khoảng challenge còn hiệu lực.

Trong production:

- Redis có thể dùng `GETDEL` hoặc Lua/transaction để lấy-xóa atomically.
- Database có thể dùng update điều kiện status=PENDING / version check trong transaction.
- Một challenge repository cần chứng minh có cùng semantics ở nhiều node, không chỉ trong unit test đơn luồng.

Một lựa chọn bảo thủ: **consume khi nhận attempt**, dù tiếp đó context hoặc signature thất bại, rồi yêu cầu một challenge mới nếu cần retry. Việc đó ngăn replay dễ dàng nhưng cần cân nhắc UX/DoS và bảo vệ session/CSRF/rate-limit. Không giữ challenge vô hạn sau lỗi xác thực.

**Atomic consume không chứng minh người dùng đã đăng nhập**. Nó chỉ xác nhận một pending challenge được sử dụng đúng một lần; các phép kiểm cryptographic và policy vẫn phải được làm tiếp.

## 6. Kiểm đúng ngữ cảnh WebAuthn

Server không chỉ so sánh challenge. Các điều kiện cần kiểm khi authentication assertion được nhận:

| Bất biến | Nguồn | Kiểm thế nào |
| --- | --- | --- |
| `clientDataJSON.type` | Browser data | `webauthn.get` cho authentication, `webauthn.create` cho registration |
| `clientDataJSON.challenge` | Browser data | Phải khớp challenge đang pending phía RP |
| `clientDataJSON.origin` | Browser data | So với danh sách origin được phép, đúng scheme/host/port |
| `crossOrigin` / `topOrigin` | Browser data | Khớp chính sách RP về iframe hoặc related origins |
| `authenticatorData.rpIdHash` | Authenticator data | SHA-256 của expected RP ID |
| `flags.UP` | Authenticator data | Kiểm user presence theo WebAuthn assertion verification |
| `flags.UV` | Authenticator data | Bắt buộc khi policy yêu cầu userVerification=required |
| `credentialId` | Credential store | Credential đã đăng ký cho RP/account phù hợp |
| `signature` | Assertion | Verify bằng public key của credential trên authData || SHA-256(clientDataJSON) |
| `userHandle` | Response / credential record | Phải phù hợp binding account khi có/được yêu cầu |
| `signCount` | Authenticator data / record | Xử lý tín hiệu rủi ro clone theo WebAuthn |

### RP ID và Origin khác nhau

Ví dụ:

~~~text
RP ID = example.org
Allowed Origin = https://login.example.org
~~~

RP ID là tên miền scope credential (không có scheme/port). Origin chứa scheme, hostname và port nếu có. Giá trị **không cần trùng chuỗi**, nhưng phải đáp ứng quy tắc RP ID của WebAuthn và allowlist origin phía RP.

Không đặt wildcard origin rộng tùy tiện. Nếu app chỉ chạy ở `https://login.example.org`, allowlist origin chính xác là phương án dễ audit. Không tắt origin/rpIdHash validation để sửa lỗi reverse proxy; phải sửa public host và forwarded headers tin cậy.

### User presence và User verification

- **UP:** authenticator kiểm một hành động hiện diện của người dùng.
- **UV:** authenticator thực hiện xác minh người dùng cục bộ (PIN, biometric hoặc phương thức tương đương).

`userVerification=preferred` **không đảm bảo UV**. Khi nghiệp vụ yêu cầu xác minh mạnh, chọn `required` và kiểm flag UV. UV=true không khẳng định nhất thiết đã có biometric vì PIN cũng có thể đáp ứng.

### Signature counter không thay challenge

Credential đồng bộ trên nhiều thiết bị có thể dùng signCount=0 hoặc không tăng theo mô hình thiết bị đơn truyền thống. Counter thấp/không tăng có thể là tín hiệu rủi ro tùy credential, **không** phải lý do bỏ challenge TTL hoặc cho phép replay. Xử lý clone risk theo thông tin backup eligibility/state và chính sách phù hợp.

## 7. Ràng buộc với đúng session và account

Trong **login chưa biết user**, challenge có thể gắn với anonymous session hoặc login flow ID; sau khi xác minh credential mới quyết định account.

Trong **username-first login**, server đã có username ứng viên và có thể cấp `allowCredentials` giới hạn theo account. Username vẫn chỉ là dữ liệu chọn flow, không phải bằng chứng đăng nhập.

Trong **registration**, người dùng thường phải **đã được xác thực** trước khi tạo passkey. Challenge phải gắn với session, account và quyền đăng ký credential mới. Một request client tự gửi `accountId=admin` không được khiến passkey mới ghi vào admin nếu session thuộc account khác.

Ví dụ:

~~~text
LOGIN:
  ceremony=LOGIN, sessionRef=anonymous-12
  accountRef=unknown, operationRef=none

REGISTER:
  ceremony=REGISTER, sessionRef=logged-in-93
  accountRef=user:lan, operationRef=REGISTER_FOR_user:lan

STEP_UP:
  ceremony=STEP_UP, sessionRef=logged-in-93
  accountRef=user:lan, operationRef=CHANGE_EMAIL_request-57
~~~

Một response từ challenge REGISTER nộp sang LOGIN phải bị từ chối dù cùng RP/origin. Một response cho session A nộp bằng cookie session B cũng không được coi là đúng flow chỉ vì challenge value khớp.

Các tình huống cần xử lý:

- Cookie phiên cần Secure/HttpOnly/SameSite phù hợp, truyền qua HTTPS.
- Khi logout, đổi account, session fixation rotation, pending states cũ phải bị vô hiệu theo policy.
- Hai tab song song phải có challenge/flow ID riêng hoặc policy rõ ràng “options mới hủy options cũ”.
- Không dùng một biến global `lastChallenge` cho mọi user.
- Rate-limit số pending challenges theo session/IP/account, dọn state theo TTL.

Theo tài liệu Spring Security, endpoints tạo WebAuthn options dùng **POST với CSRF token** vì việc cấp challenge làm thay đổi trạng thái phía server. Không coi POST options là GET read-only có thể gọi vô hạn từ website khác.

## 8. Registration: giữ đúng người sở hữu credential

Đăng ký passkey thay đổi phương thức đăng nhập của tài khoản, nên có nguy cơ account takeover nếu account binding sai.

Quy trình gợi ý:

1. Xác thực account hiện tại; yêu cầu step-up/re-auth nếu chính sách credential management đòi.
2. Server sinh challenge và `PublicKeyCredentialCreationOptions` cho account đó.
3. Lưu accountRef, sessionRef, RP ID, allowed origin, required UV và expiry trong pending state.
4. Browser gọi `navigator.credentials.create({publicKey: options})`.
5. Server consume đúng challenge, kiểm `type=webauthn.create`, origin, rpIdHash, flags, attestation policy và dữ liệu credential.
6. Chỉ khi mọi điều kiện hợp lệ mới ghi public key/credential ID **vào đúng account trong pending state**.
7. Audit việc thêm credential; hỗ trợ thu hồi/xem danh sách passkeys.

`user.id` trong options phải được RP xác định từ tài khoản của server, không dựa vào request parameter do client tùy chọn. `excludeCredentials` giúp tránh đăng ký trùng credential, nhưng kiểm uniqueness vẫn cần ở server.

Không dùng cùng một challenge cho đăng ký và đăng nhập; nó phục vụ hai ceremony có type khác nhau.

## 9. Login: account-first và discoverable credentials

Một authentication flow có thể:

- **Account-first:** user nhập username, server tìm credential IDs đã đăng ký và gửi `allowCredentials` phù hợp.
- **Discoverable passkey:** browser/authenticator chọn passkey dù user chưa nhập username; `allowCredentials` có thể rỗng và credential ID/userHandle được dùng để tra account **sau khi** kiểm chứng assertion.

Tại completion, phải đối chiếu:

1. Challenge còn hạn, đúng pending flow và chưa được dùng.
2. Type, origin, RP ID, flags/UV đúng.
3. Credential ID tồn tại, public key đúng và signature hợp lệ.
4. Account gắn với credential có quyền đăng nhập; userHandle nhất quán khi cần.
5. Nếu flow account-first, credential không được “chuyển” sang account khác.
6. Chỉ sau đó tạo Authentication, session và áp dụng authorization riêng.

Không lấy user từ field do client gửi rồi bỏ qua xác minh public key. Username, email hoặc userHandle trần không phải bằng chứng cryptographic.

## 10. Step-up: challenge phải gắn đúng thao tác nhạy cảm

Tình huống: user:lan đã đăng nhập, muốn chuyển tiền từ ví A sang ví B. Ứng dụng yêu cầu passkey lần nữa để cho phép hành động.

~~~text
Actor: user:lan
Operation ID: transfer-42
Version: 3
From: wallet-A
To: wallet-B
Amount: 5000000
Currency: VND
~~~

Một assertion WebAuthn hợp lệ theo challenge dùng cho LOGIN không nên được dùng như approval cho TRANSFER. Step-up cần hai tầng:

1. **WebAuthn context:** challenge, type, origin, RP ID, credential, signature, UV.
2. **Application context:** user/session, tenant, operation ID, version, người nhận, số tiền/đơn vị tiền, quyền thực thi, TTL và one-time grant.

Ví dụ pending state:

~~~yaml
ceremony: STEP_UP
sessionRef: "session-user-lan-2"
accountRef: "user:lan"
operationRef: "transfer-42"
operationVersion: 3
canonicalPayloadDigest: "hash-cua-noi-dung-server-side"
requireUserVerification: true
expiresAt: "2026-11-06T08:02:00Z"
status: PENDING
~~~

Khi assertion hợp lệ, server **chưa thực thi thao tác ngay**. Nó phải load operation từ nguồn đáng tin, xác nhận payload/version/recipient/amount không đổi, tài khoản và quyền vẫn hợp lệ, policy hạn mức còn đúng, rồi consume step-up grant cho **đúng operation** theo transaction/idempotency.

**Giới hạn quan trọng:** WebAuthn mặc định ký `authenticatorData || SHA-256(clientDataJSON)`, có challenge và origin. Nó **không mặc định ký một bản hiển thị đáng tin cậy về số tiền hoặc người nhận**. Lưu hash giao dịch trong pending state chống việc dùng kết quả xác thực lại cho giao dịch khác hoặc payload bị sửa ở server; điều đó **không chứng minh authenticator đã hiển thị cho user và user phê duyệt chính xác nội dung giao dịch**. Nếu sản phẩm cần “transaction signing” hoặc trusted approval, phải thiết kế cơ chế xác nhận nội dung riêng, không quảng bá login passkey thông thường là chữ ký giao dịch.

Không tạo challenge bằng phép nối `"transfer:" + amount + recipient`: dữ liệu đoán được, không có entropy và không gắn quyền. Phải sinh challenge random, rồi ràng buộc nó với operation canonical đã lưu ở server.

## 11. Java 17+: mô phỏng challenge TTL và binding

Chương trình **ChallengeContextDemo.java** dưới đây là ứng dụng console độc lập. Nó mô phỏng server challenge store theo ceremony, session, operation và TTL. Nó **không triển khai WebAuthn cryptographic verifier**, không parse assertion và không chứng minh account đã đăng nhập.

~~~java
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;

public class ChallengeContextDemo {
    enum Ceremony { REGISTER, LOGIN, STEP_UP }

    record Pending(Ceremony ceremony, String sessionId,
                   String operationKey, Instant expiresAt) {}

    static final SecureRandom RANDOM = new SecureRandom();
    static final Duration TTL = Duration.ofMinutes(2);

    private final Map<String, Pending> outstanding = new HashMap<>();

    public synchronized String issue(
            Ceremony ceremony, String sessionId,
            String operationKey, Instant now) {

        String challenge;
        do {
            byte[] bytes = new byte[32];
            RANDOM.nextBytes(bytes);
            challenge = Base64.getUrlEncoder()
                    .withoutPadding().encodeToString(bytes);
        } while (outstanding.containsKey(challenge));

        outstanding.put(challenge,
                new Pending(ceremony, sessionId, operationKey,
                        now.plus(TTL)));
        return challenge;
    }

    public synchronized boolean consume(
            String challenge, Ceremony ceremony, String sessionId,
            String operationKey, Instant now) {

        // Xóa atomically: kể cả attempt sai cũng không được dùng lại.
        Pending pending = outstanding.remove(challenge);
        return pending != null
                && now.isBefore(pending.expiresAt())
                && pending.ceremony() == ceremony
                && pending.sessionId().equals(sessionId)
                && pending.operationKey().equals(operationKey);
    }

    public static void main(String[] args) {
        ChallengeContextDemo store = new ChallengeContextDemo();
        Instant now = Instant.parse("2026-11-06T08:00:00Z");

        String login = store.issue(Ceremony.LOGIN, "session-A", "-", now);
        System.out.println("Challenge chars = " + login.length());
        System.out.println("Correct context = "
                + store.consume(login, Ceremony.LOGIN,
                        "session-A", "-", now.plusSeconds(30)));
        System.out.println("Replay rejected = "
                + store.consume(login, Ceremony.LOGIN,
                        "session-A", "-", now.plusSeconds(31)));

        String wrongSession = store.issue(
                Ceremony.LOGIN, "session-A", "-", now);
        System.out.println("Wrong session = "
                + store.consume(wrongSession, Ceremony.LOGIN,
                        "session-B", "-", now.plusSeconds(10)));

        String expired = store.issue(
                Ceremony.LOGIN, "session-A", "-", now);
        System.out.println("Expired = "
                + store.consume(expired, Ceremony.LOGIN,
                        "session-A", "-", now.plusSeconds(120)));

        String wrongType = store.issue(
                Ceremony.REGISTER, "session-A", "-", now);
        System.out.println("Wrong ceremony = "
                + store.consume(wrongType, Ceremony.LOGIN,
                        "session-A", "-", now.plusSeconds(20)));

        String stepUp = store.issue(
                Ceremony.STEP_UP, "session-A", "transfer-42-v3", now);
        System.out.println("Wrong operation = "
                + store.consume(stepUp, Ceremony.STEP_UP,
                        "session-A", "transfer-99-v3", now.plusSeconds(30)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ChallengeContextDemo.java
java ChallengeContextDemo
~~~

Stdout chính xác:

~~~text
Challenge chars = 43
Correct context = true
Replay rejected = false
Wrong session = false
Expired = false
Wrong ceremony = false
Wrong operation = false
~~~

Giải thích:

- Challenge 32 byte base64url không padding có đúng 43 ký tự; demo không in secret cụ thể.
- Lần consume hợp lệ đầu tiên trả true, lần thứ hai trả false do state đã bị xóa.
- Sai session, sai ceremony hoặc operation trả false.
- Sau đúng 120 giây, `now.isBefore(expiresAt)` trả false theo quy tắc hết hạn.

`synchronized` chỉ bảo vệ map trong một JVM. Ứng dụng có nhiều node cần Redis/database **atomic consume** và TTL thật. Chương trình chưa kiểm account, RP ID, origin, user verification, credential public key hoặc signature. Không dùng kết quả consume=true để tạo Authentication trong ứng dụng thật.

## 12. Spring Security hỗ trợ Passkeys

Trong dòng Spring Security 7.x Servlet, module `spring-security-webauthn` cung cấp các flow đăng ký và xác thực bằng passkey. Dùng dependency management của Spring Boot hoặc Spring Security BOM thay vì tự trộn các phiên bản.

Gradle Groovy:

~~~groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-web"
    implementation "org.springframework.boot:spring-boot-starter-security"
    implementation "org.springframework.security:spring-security-webauthn"
}
~~~

Ví dụ **một class cấu hình trong ứng dụng Spring Boot Servlet**:

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class PasskeySecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .webAuthn(webAuthn -> webAuthn
                .rpId("login.example.org")
                .allowedOrigins("https://login.example.org"));

        return http.build();
    }
}
~~~

Đoạn này **không chạy độc lập bằng javac**. Cần main Spring Boot, HTTPS thực, user/credential repository và frontend/login page phù hợp. `rpId` và `allowedOrigins` phải thay bằng hostname public được phê duyệt. Kiểm đúng API và hành vi của phiên bản Spring Security dự án đang dùng.

Theo tài liệu Spring Security 7.x, các endpoint mặc định thông dụng:

| Endpoint | Ý nghĩa |
| --- | --- |
| `POST /webauthn/register/options` | Sinh challenge/creation options cho user đang đăng nhập |
| `POST /webauthn/register` | Nhận credential registration response |
| `POST /webauthn/authenticate/options` | Sinh challenge/request options cho login |
| `POST /login/webauthn` | Nhận authentication assertion và kiểm |

Các POST options dùng CSRF token theo tài liệu Spring Security vì pending challenge state được thay đổi. Không thay chúng bằng GET không bảo vệ.

Spring Security dùng `PublicKeyCredentialCreationOptionsRepository` để lưu creation options giữa hai request; tài liệu 7.x cho biết mặc định lưu ở **HttpSession** và có thể tùy chỉnh repository. `PublicKeyCredentialUserEntityRepository` và `UserCredentialRepository` lưu user entity và credential public key; chúng không đồng nghĩa với challenge store có TTL. Với authentication options hoặc customization, đọc API phiên bản thực tế trước khi thay thế component mặc định.

**Đừng tự viết signature verifier dựa trên vài chuỗi JSON.** Thư viện WebAuthn đã có quy tắc chi tiết cho CBOR/authenticatorData/clientDataJSON/public keys, flags, algorithms, origin và counter. Nếu cần thêm operation binding, tích hợp tại ranh giới ứng dụng sau khi passkey verifier đã xác minh, không tắt các validation mặc định.

## 13. Browser xử lý challenge thế nào?

Client nhận JSON options, chuyển challenge từ base64url sang byte array rồi gọi browser WebAuthn API:

~~~javascript
// Mảnh minh họa, cần csrfToken từ trang đăng nhập.
const r = await fetch("/webauthn/authenticate/options", {
    method: "POST",
    headers: { "X-CSRF-TOKEN": csrfToken }
});
if (!r.ok) throw new Error("Cannot start passkey ceremony");
const options = await r.json();

function decodeBase64url(value) {
    const s = value.replace(/-/g, "+").replace(/_/g, "/");
    const padded = s.padEnd(Math.ceil(s.length / 4) * 4, "=");
    return Uint8Array.from(atob(padded), c => c.charCodeAt(0));
}

options.challenge = decodeBase64url(options.challenge);
options.allowCredentials = (options.allowCredentials || []).map(x => ({
    ...x,
    id: decodeBase64url(x.id)
}));

const credential = await navigator.credentials.get({
    publicKey: options
});
// Serialize binary fields (rawId, authenticatorData,
// clientDataJSON, signature, userHandle) to base64url and POST
// to /login/webauthn in the format the server expects.
~~~

Đây là **mảnh code client**, chưa bao gồm serialization hoàn chỉnh hay xử lý UX lỗi/hủy. Browser không có quyền tự sinh challenge thay server. Một `credential.id` trả về chưa đủ để chứng minh tài khoản; RP vẫn phải kiểm chữ ký và ngữ cảnh của assertion.

## 14. Lỗi phổ biến và hướng chẩn đoán

| Triệu chứng hoặc lỗi | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Replay assertion trong TTL vẫn thành công | Challenge bị dùng nhiều lần, consume không atomic | Atomic take/delete, retry với challenge mới |
| Browser timeout nhưng server vẫn chấp nhận | Chỉ dựa `options.timeout` | Enforce expiresAt server |
| Challenge tạo được nhưng completion ở node khác thất bại | Session/store không chia sẻ giữa nodes | Shared store hoặc sticky session có kiểm soát |
| Login A thành registration B | Không kiểm ceremony/clientDataJSON.type | Gắn state với type và verify |
| Đăng ký vào sai user | Tin accountId do client gửi | Bind current authenticated account trong pending state |
| User khác dùng challenge của session A | State không gắn flow/session | Bind sessionRef và bảo vệ cookie/CSRF |
| Passkey hợp lệ nhưng bị reject origin | Public host/reverse proxy sai | Sửa allowedOrigins, trusted forwarded headers |
| Bỏ origin validation để “fix” login | Mất ranh giới website | Không bỏ; sửa cấu hình |
| UserVerification=preferred nhưng app coi là MFA bắt buộc | Không kiểm UV | required và verify UV flag |
| Credential ID hợp lệ bị coi là đủ | Không verify chữ ký | Verify bằng public key đã đăng ký |
| SignCount=0 bị xử lý như replay | Syncable passkey có semantics khác | Risk-based handling, challenge vẫn single-use |
| Step-up cho thao tác A dùng được ở B | Không bind operation/version | Operation-scoped one-time grant |
| Đổi amount sau step-up vẫn được thực thi | Không revalidate canonical operation | Check payload digest/version và transaction policy |
| User mở nhiều tab bị hỏng flow | Chỉ một latestChallenge ghi đè | Bounded multiple pending flows hoặc UX hủy rõ ràng |
| Pending challenges tăng vô hạn | Không TTL/quota | Expire, cleanup, rate limit |
| Redis mất kết nối | State không thể xác minh | Fail closed và yêu cầu tạo challenge mới |

Một số lỗi HTTP có thể trông giống nhau (chẳng hạn 401 cho credential không hợp lệ). Trong log vận hành nên phân biệt **challenge_missing**, **challenge_expired**, **context_mismatch**, **origin_mismatch**, **signature_invalid**, **account_disabled** bằng reason code nội bộ, nhưng không trả về chi tiết giúp kẻ tấn công dò credential/account. Không log raw assertion nhạy cảm hay session tokens.

## 15. Kiểm thử bắt buộc theo ngữ cảnh

| Test | Kết quả mong đợi |
| --- | --- |
| Challenge ngẫu nhiên đủ entropy, mỗi ceremony mới | Giá trị khó đoán và khác request trước |
| Đúng challenge trong TTL | Cho qua lớp state để tiếp tục kiểm WebAuthn |
| Challenge hết hạn đúng boundary `now == expiresAt` | Từ chối |
| Replay cùng challenge | Từ chối lần thứ hai |
| Hai request đồng thời cùng challenge | Chỉ một consume thành công |
| Challenge REGISTER gửi tới LOGIN | Từ chối type/ceremony |
| Challenge của session A gửi với cookie B | Từ chối |
| Origin không thuộc allowlist | Từ chối |
| `rpIdHash` khác expected RP ID | Từ chối |
| Signature sai dù challenge đúng | Từ chối |
| UV required nhưng flag UV false | Từ chối |
| Credential ID không có hoặc khác account | Từ chối |
| UserHandle/credential mapping không nhất quán | Từ chối |
| User disabled giữa ceremony | Từ chối |
| Đăng ký passkey sau khi logout | Từ chối |
| Step-up operation ID/version/amount khác | Từ chối |
| Step-up grant dùng cho giao dịch thứ hai | Từ chối |
| Trình duyệt hủy và thử lại | Challenge mới; state cũ không dùng lại |
| Key store/Redis mất kết nối | Không được cấp Authentication |
| Thử đăng nhập qua nhiều node và hai tab | Không lẫn session/challenge |
| CSRF vào endpoint options | Bị ngăn theo policy Spring Security |

Nên có **unit test** cho challenge store với Clock có thể điều khiển; **integration test** thư viện verifier dùng credential thật/test authenticator để kiểm chữ ký/origin/flags; **end-to-end test** qua HTTPS và browser; cùng **business test** cho transaction binding và idempotency. Mô hình Java ở mục 11 chỉ kiểm TTL/context, không chứng minh toàn bộ WebAuthn.

## 16. Checklist triển khai và kết luận

1. Server dùng CSPRNG sinh **challenge mới, đủ entropy** cho từng ceremony?
2. Pending state do server sở hữu, có TTL thực thi và atomic single-use consume?
3. Có lưu/kiểm ceremony type, session, account, tenant, credential options và policy UV?
4. Có kiểm chính xác `type`, `challenge`, `origin`, `crossOrigin/topOrigin`, `rpIdHash`, UP/UV, signature, credential ownership và counter theo chuẩn?
5. Flow đăng ký có bảo vệ current account và CSRF, không tin accountId client?
6. Flow login có xử lý account-first/discoverable credential mà không tin username trước xác minh?
7. Step-up có gắn đúng operation version/payload và chỉ được sử dụng một lần?
8. Có tránh khẳng định passkey đã “ký số tiền/người nhận” chỉ vì challenge được bind ở server?
9. Load balancer/session store, time synchronization, cleanup và quota đã được test?
10. Mọi thất bại về state/signature/account có **fail closed**, không sinh principal dự phòng?

**Kết luận:** Một passkey ceremony an toàn không kết thúc ở “có chữ ký”. RP phải xác minh **chữ ký và tất cả bất biến WebAuthn**, đồng thời đối chiếu challenge **còn hạn, chưa dùng và được cấp đúng phiên, đúng mục đích**. Khi cần duyệt hành động nhạy cảm, ứng dụng phải ràng buộc kết quả xác minh lại vào **đúng operation** mà server đang quản lý, áp dụng authorization và ngăn replay ở cả lớp challenge lẫn lớp nghiệp vụ.

### Tài liệu tham khảo

- W3C Web Authentication Level 3 — challenge, origin, assertion verification: https://www.w3.org/TR/2026/REC-webauthn-3-20260825/
- Spring Security 7.0 — Passkeys, config và endpoints: https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/passkeys.html
- Spring Security — Servlet authentication architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — HTTP authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- MDN — Web Authentication API: https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API
