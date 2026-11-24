# Authentication ceremony — Nghi thức xác thực bằng WebAuthn

**Authentication ceremony** trong WebAuthn là chuỗi bước mà trình duyệt, relying party (RP) và authenticator phối hợp để chứng minh người dùng đang kiểm soát một credential đã đăng ký cho website. Máy chủ tạo một challenge mới; trình duyệt chuyển yêu cầu tới authenticator; authenticator có thể yêu cầu người dùng xác minh cục bộ bằng PIN, sinh trắc hoặc phương thức phù hợp; sau đó authenticator ký dữ liệu xác thực bằng private key. RP kiểm tra chữ ký và ngữ cảnh trước khi tạo phiên đăng nhập.

Nghi thức này là nền tảng của **passkey** và khóa bảo mật FIDO2. Điểm mạnh quan trọng là chữ ký được ràng buộc với **RP ID và origin** của website, nhờ đó credential không thể được dùng tùy tiện trên một trang phishing có domain khác. Tuy nhiên, việc có một assertion hợp lệ vẫn chưa tự cấp quyền truy cập mọi tài nguyên: ứng dụng còn phải kiểm tra account, trạng thái phiên, chính sách assurance và authorization.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả vai trò của RP, trình duyệt, authenticator và credential trong một authentication ceremony.
2. Phân biệt **registration ceremony** với **authentication ceremony**, biết dữ liệu nào được tạo ở mỗi giai đoạn.
3. Giải thích challenge, client data, authenticator data, RP ID hash, origin, chữ ký và các cờ UP/UV.
4. Mô tả luồng WebAuthn assertion từ server options đến bước xác minh chữ ký ở server.
5. Thiết kế challenge có thời hạn, dùng một lần và ràng buộc với đúng tài khoản/phiên/giao dịch.
6. Phân biệt xác thực có username với luồng discoverable credential (usernameless/conditional UI).
7. Kiểm thử các trường hợp replay, origin/RP ID sai, credential không thuộc tài khoản, UV không đạt policy và session bị chiếm.

## 2. Các thành phần tham gia

| Thành phần | Vai trò trong ceremony | Điều cần tin/kiểm tra |
| --- | --- | --- |
| **Relying Party (RP)** | Website/dịch vụ yêu cầu xác thực, thường gồm backend và frontend | RP ID, challenge, policy, danh sách credential và kết quả xác minh phía server. |
| **Browser / user agent** | Thực thi WebAuthn API, kiểm soát origin và chuyển yêu cầu tới authenticator | Origin hiện tại, secure context, điều kiện API và dữ liệu trả về từ authenticator. |
| **Authenticator** | Giữ private key và tạo chữ ký cho credential | Credential đã được ghi danh, xác minh người dùng nếu policy yêu cầu và bảo vệ private key. |
| **Credential** | Cặp khóa gắn với một RP; server giữ public key/credential metadata | Credential ID, public key, user/account mapping và trạng thái thu hồi. |
| **Người dùng** | Khởi tạo thao tác và có thể xác minh cục bộ | Hiểu website/tác vụ đang yêu cầu xác thực; không chia sẻ PIN/recovery secret. |

Authenticator có thể là **platform authenticator** tích hợp trong điện thoại/máy tính hoặc **roaming authenticator** như security key USB/NFC/BLE. Passkey có thể đồng bộ giữa các thiết bị qua hệ sinh thái cung cấp hoặc gắn với một thiết bị cụ thể. RP không nhận private key và không trực tiếp đọc dữ liệu sinh trắc dùng để mở khóa authenticator.

### 2.1. Ranh giới tin cậy

~~~mermaid
flowchart LR
    U["Người dùng"] --> B["Browser / origin"]
    B -->|"WebAuthn API"| A["Authenticator"]
    A -->|"Assertion có chữ ký"| B
    B -->|"Credential response"| RP["RP backend"]
    RP --> DB[("Credential store: public key")]
    RP --> S[("Challenge / session state")]
    RP -->|"Xác minh xong mới cấp"| APP["Application session"]
~~~

Browser và authenticator giúp ràng buộc yêu cầu với website, nhưng **backend vẫn là nơi quyết định assertion có hợp lệ hay không**. Frontend không được tự đánh dấu đăng nhập thành công chỉ vì lời gọi WebAuthn trả về không lỗi.

## 3. Registration ceremony và authentication ceremony khác nhau

WebAuthn có hai nghi thức chính:

| Nghi thức | Mục đích | Kết quả lưu tại RP |
| --- | --- | --- |
| **Registration / create** (navigator.credentials.create) | Tạo credential mới cho RP và liên kết với tài khoản sau khi xác minh enrollment | Credential ID, public key, user handle, thông tin thuật toán và metadata cần thiết. |
| **Authentication / get** (navigator.credentials.get) | Chứng minh quyền kiểm soát private key của credential đã đăng ký | Assertion được xác minh; RP cập nhật trạng thái đăng nhập và cấp phiên theo policy. |

Registration không phải là đăng nhập thông thường. Khi ghi danh, RP cần xác thực người dùng bằng một phiên hiện tại hoặc quy trình enrollment đủ tin cậy; nếu attacker có thể tự thêm passkey vào tài khoản nạn nhân, mọi lần xác thực sau đó có thể hợp lệ về mật mã nhưng sai chủ thể.

Authentication ceremony **không tạo credential mới**. Nó dùng credential đã đăng ký để ký challenge mới. Attestation (nếu được dùng) chủ yếu thuộc registration và chính sách tin cậy authenticator; không phải thứ server yêu cầu trong mỗi lần authentication.

## 4. Trước ceremony: server tạo request options

Khi người dùng chọn “Đăng nhập bằng passkey”, frontend gọi backend để bắt đầu giao dịch. Backend tạo challenge mới bằng bộ sinh số ngẫu nhiên mật mã (CSPRNG), có entropy đủ mạnh, gắn challenge với transaction và đặt thời hạn ngắn.

Một bộ request options minh họa:

~~~json
{
  "challenge": "<base64url-random-challenge>",
  "rpId": "login.studyhub.example",
  "timeout": 60000,
  "userVerification": "required",
  "allowCredentials": [
    {
      "type": "public-key",
      "id": "<base64url-credential-id>"
    }
  ]
}
~~~

Đây là JSON khái niệm; server cần serialize challenge đúng định dạng base64url và frontend phải chuyển về ArrayBuffer khi gọi WebAuthn API. Giá trị timeout chỉ là gợi ý cho user agent, không thay thế thời hạn giao dịch ở server.

Các lựa chọn quan trọng:

- **challenge**: phải mới, khó đoán, gắn với một lần yêu cầu; server giữ bản gốc để so sánh khi nhận response.
- **rpId**: RP ID đã cấu hình cho website, thường là domain hiện tại hoặc domain cha đủ điều kiện theo quy tắc WebAuthn. Không lấy tùy ý từ dữ liệu người dùng.
- **allowCredentials**: danh sách credential ID được phép cho tài khoản đã biết. Có thể bỏ hoặc để rỗng trong luồng discoverable credential.
- **userVerification**: required, preferred hoặc discouraged. Policy có thể yêu cầu UV; không nên đặt discouraged cho thao tác cần xác minh người dùng.
- **timeout**: thời gian UI chờ; backend vẫn phải tự hết hạn transaction.
- **extensions**: chỉ bật khi RP hiểu rõ semantics, dữ liệu trả về và tác động quyền riêng tư/bảo mật.

Giao dịch chờ nên lưu server-side: transaction ID, challenge, RP ID, account/subject nếu đã biết, session khởi tạo, mục đích, thời hạn, trạng thái chưa tiêu thụ và policy UV. Không tin challenge do client tự tạo hoặc client tự gửi lại một giá trị không gắn với giao dịch server.

## 5. Frontend gọi WebAuthn API

Browser nhận request options từ backend, chuyển trường challenge và credential ID từ base64url sang binary rồi gọi:

~~~javascript
const assertion = await navigator.credentials.get({
  publicKey: publicKeyRequestOptions
});
~~~

Đoạn mã chỉ minh họa lời gọi API; ứng dụng thực tế cần chuyển đổi các trường nhị phân đúng chuẩn, xử lý null, cancellation, timeout và lỗi thiết bị. Với luồng discoverable credential, ứng dụng có thể dùng conditional mediation để trình duyệt đề xuất passkey trong trường username:

~~~javascript
const assertion = await navigator.credentials.get({
  publicKey: publicKeyRequestOptions,
  mediation: "conditional"
});
~~~

Conditional UI là trải nghiệm lựa chọn credential; nó không làm thay đổi các phép xác minh mật mã bắt buộc ở server. Trình duyệt có thể hiển thị passkey phù hợp, người dùng chọn credential, rồi authenticator xử lý yêu cầu.

### 5.1. Authenticator làm gì?

1. Nhận yêu cầu từ browser và xác định credential phù hợp với RP ID.
2. Có thể yêu cầu user presence (ví dụ chạm security key) và/hoặc user verification (PIN, sinh trắc hoặc cơ chế cục bộ).
3. Tạo authenticatorData chứa RP ID hash và các cờ liên quan.
4. Tạo clientDataJSON ở browser, trong đó có loại thao tác, challenge và origin.
5. Ký dữ liệu xác thực bằng private key của credential.
6. Trả assertion về browser để frontend chuyển tiếp tới RP backend.

Authenticator không gửi private key cho browser hoặc server. PIN/sinh trắc thường dùng cục bộ để mở khóa credential hoặc xác minh người dùng theo khả năng authenticator; RP chỉ nhận cờ kết quả và chữ ký, không nhận mẫu sinh trắc.

## 6. Assertion response chứa những gì?

Một authentication response WebAuthn thường có các trường:

| Trường | Ý nghĩa |
| --- | --- |
| id / rawId | Credential ID được chọn. |
| type | Loại credential, thường là public-key. |
| response.clientDataJSON | Client data được browser tạo; chứa type, challenge, origin và các dữ liệu liên quan theo chuẩn. |
| response.authenticatorData | Dữ liệu do authenticator tạo, bao gồm RP ID hash, flags và sign counter; có thể có phần mở rộng nếu được dùng. |
| response.signature | Chữ ký trên authenticator data kết hợp hash của client data JSON theo WebAuthn. |
| response.userHandle | User handle nếu có; thường quan trọng với discoverable credential. Có thể null trong một số luồng. |

Mô hình dữ liệu:

~~~text
Authentication response
  credentialId
  clientDataJSON
    type = "webauthn.get"
    challenge
    origin
  authenticatorData
    rpIdHash
    flags: UP, UV, BE, BS, ...
    signCount
  signature
  userHandle (optional)
~~~

Không dùng riêng id, userHandle hoặc một cờ do frontend gửi để xác thực. Backend phải kiểm tra **toàn bộ assertion theo WebAuthn** bằng thư viện server-side được duy trì.

## 7. Server xác minh assertion theo thứ tự

Server phải chứng minh response thuộc đúng transaction, đúng RP/origin, được ký bởi credential đã đăng ký và đạt policy. Các bước dưới đây mô tả logic tổng quát; thứ tự và điều kiện chi tiết cần tuân theo phiên bản WebAuthn và thư viện triển khai.

### 7.1. Xác minh transaction và client data

- Tìm transaction đang chờ dựa trên session/transaction ID server-side.
- Kiểm tra transaction còn hạn, chưa bị tiêu thụ và đúng mục đích.
- Parse clientDataJSON theo định dạng chuẩn.
- Kiểm tra type là webauthn.get.
- So sánh challenge trong client data với challenge server đã tạo; dùng so sánh an toàn phù hợp.
- Kiểm tra origin chính xác thuộc danh sách origin được phép cho RP.
- Kiểm tra các điều kiện cross-origin/top-origin nếu kiến trúc cho phép iframe hoặc luồng cross-origin; mặc định không mở rộng origin tùy tiện.

### 7.2. Xác minh authenticator data

- Tính hash của RP ID đã cấu hình và so sánh với rpIdHash trong authenticatorData.
- Kiểm tra cờ **UP (User Present)** nếu policy yêu cầu có tương tác người dùng.
- Kiểm tra cờ **UV (User Verified)** nếu policy yêu cầu xác minh người dùng bằng PIN/sinh trắc/cơ chế authenticator.
- Parse sign counter và các cờ backup liên quan theo chuẩn.
- Chỉ chấp nhận extension nếu đã yêu cầu/hỗ trợ và xác minh đúng semantics.

### 7.3. Xác minh credential và chữ ký

- Tìm credential theo credential ID đã đăng ký; xác định public key và account mapping từ database đáng tin cậy.
- Kiểm tra credential đang hoạt động, chưa bị thu hồi và thuộc đúng RP/account theo policy.
- Xác minh chữ ký trên dữ liệu đúng theo WebAuthn: authenticator data kết hợp hash của client data JSON, sử dụng public key và thuật toán gắn với credential.
- Nếu response có userHandle, đối chiếu với user handle đã lưu; không dùng nó để tự chọn account nếu credential ID đã ánh xạ sang tài khoản khác.
- Xử lý sign counter theo đặc tính authenticator; không từ chối mọi passkey đồng bộ chỉ vì counter bằng 0 hoặc không tăng như kỳ vọng.

### 7.4. Kiểm tra policy rồi mới cấp phiên

- Xác định account từ credential mapping đã xác minh.
- Kiểm tra tài khoản còn hoạt động, không bị khóa hoặc thu hồi.
- Xác minh UV/UP và mức assurance đáp ứng chính sách của hành động.
- Tiêu thụ transaction/challenge một lần để chống replay và race condition.
- Xoay session ID, tạo phiên mới phía server và thiết lập cookie bảo vệ.
- Ghi sự kiện cần thiết nhưng không log assertion/token hoặc dữ liệu nhạy cảm không cần thiết.

~~~mermaid
flowchart TD
    A["Nhận assertion"] --> B["Tải transaction server-side"]
    B --> C{"Còn hạn và chưa dùng?"}
    C -->|Không| X["Từ chối"]
    C -->|Có| D["Kiểm tra clientDataJSON: type, challenge, origin"]
    D --> E{"Đúng request/origin?"}
    E -->|Không| X
    E -->|Có| F["Kiểm tra rpIdHash và flags UP/UV"]
    F --> G{"Đạt policy?"}
    G -->|Không| X
    G -->|Có| H["Tìm credential và public key"]
    H --> I["Xác minh chữ ký"]
    I --> J{"Chữ ký hợp lệ và credential active?"}
    J -->|Không| X
    J -->|Có| K["Tiêu thụ challenge, xoay session ID"]
    K --> L["Cấp application session theo policy"]
~~~

Nếu bất kỳ kiểm tra bắt buộc nào thất bại, RP không được tạo phiên đã xác thực. Thông báo cho người dùng nên hữu ích nhưng không tiết lộ thông tin cho phép dò credential hoặc account.

## 8. UP, UV và mức bảo đảm

Hai cờ thường được nhắc tới:

- **UP — User Present:** authenticator cho biết có tương tác/sự hiện diện người dùng theo cơ chế của nó, ví dụ chạm security key.
- **UV — User Verified:** authenticator cho biết người dùng đã được xác minh theo phương thức cục bộ của authenticator, ví dụ PIN hoặc sinh trắc.

UP và UV không đồng nghĩa. Một lần chạm khóa có thể đáp ứng UP nhưng không nhất thiết đáp ứng UV. Nếu policy yêu cầu xác minh người dùng, RP phải yêu cầu userVerification là required và kiểm tra cờ UV trong assertion đã xác minh. Không suy luận UV chỉ từ giao diện có hiện màn hình PIN hay không.

| userVerification | Ý nghĩa request | Khi dùng |
| --- | --- | --- |
| required | Yêu cầu authenticator thực hiện user verification | Tài khoản/hành động cần assurance cao hoặc policy yêu cầu UV. |
| preferred | Ưu tiên UV nếu authenticator hỗ trợ | Trải nghiệm linh hoạt; RP vẫn phải xác định policy khi UV không xảy ra. |
| discouraged | Không yêu cầu UV | Chỉ khi mô hình bảo đảm cho phép; không dùng như mặc định cho thao tác nhạy cảm. |

Một passkey có UV có thể cung cấp nhiều bằng chứng trong cùng một thao tác. Tuy nhiên, mức bảo đảm cuối cùng còn phụ thuộc enrollment, bảo vệ authenticator, backup/sync, recovery, tài khoản nền tảng và chính sách RP. **Một assertion hợp lệ không tự chứng minh identity proofing đã đạt một mức cụ thể.**

## 9. Discoverable credential và usernameless authentication

Trong luồng truyền thống, người dùng nhập username trước; server tìm credential tương ứng và gửi allowCredentials gồm các credential ID được phép. Với **discoverable credential** (trước đây thường gọi resident credential), authenticator có thể tìm credential phù hợp với RP mà không cần RP gửi trước danh sách credential ID.

### 9.1. Luồng discoverable

1. Người dùng chọn “Đăng nhập bằng passkey” mà không nhập username.
2. Server tạo challenge và options cho RP ID, thường không chỉ định credential ID cụ thể.
3. Browser/authenticator hiển thị các passkey phù hợp với RP.
4. Người dùng chọn passkey và xác minh cục bộ nếu cần.
5. Assertion trả về credential ID và có thể có user handle.
6. Server tìm account theo credential ID đã đăng ký, kiểm tra user handle nếu có và xác minh assertion.

UserHandle là định danh người dùng do RP cấp khi tạo credential, không phải username tùy ý do client gửi. Nó cần được ánh xạ đúng với tài khoản đã lưu. Không dùng email hiển thị để thay cho credential mapping.

### 9.2. Conditional UI

Conditional mediation cho phép browser gợi ý passkey ngay trong trường username, giúp trải nghiệm đăng nhập tự nhiên. Nó là cách trình bày/khởi tạo credential selection, không làm giảm yêu cầu xác minh ở backend. RP vẫn phải xác minh challenge, origin, RP ID, chữ ký, credential status và policy.

### 9.3. Rủi ro enumeration và quyền riêng tư

Luồng discoverable có thể giúp tránh gửi danh sách credential của một tài khoản cụ thể trước khi biết người dùng. Tuy vậy, response và lỗi vẫn cần được xử lý cẩn trọng để không tiết lộ account tồn tại. Không ghi log credential ID hoặc user handle dạng rõ nếu không cần; giới hạn thông tin hiển thị về tài khoản.

## 10. Sign counter, backup flags và passkey đồng bộ

Authenticator data có trường **signCount** (signature counter). Trong một số authenticator, bộ đếm tăng sau mỗi lần ký; RP có thể dùng nó như một tín hiệu phát hiện credential clone hoặc bất thường. Nhưng nhiều passkey đồng bộ và authenticator hiện đại có thể luôn trả counter bằng 0 hoặc không bảo đảm counter tăng tuần tự giữa các thiết bị.

Vì vậy:

- Không xem sign counter là bằng chứng duy nhất chống clone.
- Nếu counter có giá trị và không tăng như kỳ vọng, ghi nhận tín hiệu rủi ro và áp policy phù hợp thay vì mặc định khóa tài khoản.
- Đánh giá theo loại authenticator, backup eligibility/state và mô hình đồng bộ.
- Không nhầm BE (backup eligible) với BS (backup state); chúng mô tả các thuộc tính backup của credential theo chuẩn, không tự chứng minh tài khoản nền tảng an toàn.
- Không giả định RP có thể thu hồi bản sao passkey trên mọi thiết bị đồng bộ; RP có thể thu hồi credential ở phía dịch vụ để từ chối assertion tiếp theo.

Các cờ backup không thay thế việc xác minh chữ ký và ràng buộc origin/RP ID. Chúng là metadata bổ sung giúp RP đưa ra quyết định chính sách và quan sát phù hợp.

## 11. Lỗi và tấn công trong authentication ceremony

| Lỗi/tấn công | Cách xảy ra | Phòng vệ |
| --- | --- | --- |
| **Replay assertion** | Gửi lại assertion của lần đăng nhập trước | Challenge mới, transaction một lần, TTL ngắn và atomic consume. |
| **Origin mismatch** | Response từ trang giả hoặc origin ngoài allowlist | Kiểm tra origin chính xác trong client data JSON. |
| **RP ID mismatch** | Assertion gắn với RP ID khác | Kiểm tra RP ID hash với RP ID đã cấu hình. |
| **Credential substitution** | Dùng credential của tài khoản khác để hoàn tất giao dịch | Ràng buộc transaction với account/credential policy, kiểm tra credential mapping và user handle. |
| **Challenge injection** | Client thay challenge hoặc dùng transaction của request khác | Server tạo/lưu challenge, gắn session/action và kiểm tra đúng giao dịch. |
| **Session fixation** | Session ID do attacker biết được giữ sau đăng nhập | Xoay session ID sau xác thực và nâng quyền. |
| **CSRF/login CSRF** | Nạn nhân bị ép hoàn tất đăng nhập vào tài khoản attacker | Bảo vệ transaction, cookie SameSite phù hợp, CSRF/state cho luồng ứng dụng liên quan. |
| **User verification downgrade** | Policy yêu cầu UV nhưng server chỉ kiểm tra chữ ký | Yêu cầu UV và kiểm tra cờ UV ở server. |
| **Enrollment takeover** | Attacker thêm passkey của mình vào account nạn nhân | Xác thực/enrollment đủ mạnh trước registration, thông báo thay đổi và audit. |
| **XSS** | Script chạy trên origin hợp lệ thực hiện hành động thay người dùng | CSP, output encoding, chống XSS, reauth/step-up cho hành động nhạy cảm; private key không bị lộ nhưng phiên có thể bị lạm dụng. |
| **RP ID cấu hình quá rộng** | Nhiều subdomain không đáng tin cùng phạm vi RP ID | Chọn RP ID tối thiểu phù hợp, kiểm soát subdomain và origin. |
| **Recovery yếu** | Email/help desk bỏ qua passkey | Recovery assurance tương xứng, kiểm soát hỗ trợ, thông báo và thu hồi. |

WebAuthn giúp chống phishing bằng cách ràng buộc credential với RP ID/origin, nhưng không tự bảo vệ khỏi XSS trên chính origin hợp lệ, session hijacking sau đăng nhập, enrollment yếu hoặc recovery bị lạm dụng. Phải bảo vệ toàn bộ vòng đời credential.

## 12. Quản lý lỗi và trải nghiệm người dùng

Các lỗi phổ biến khi gọi WebAuthn gồm người dùng hủy, không có credential phù hợp, authenticator không hỗ trợ UV, timeout, thiết bị không sẵn sàng, browser không hỗ trợ tính năng hoặc server từ chối assertion. Giao diện nên:

- Thông báo rõ người dùng có thể thử thiết bị/khóa khác hoặc phương thức dự phòng đã đăng ký.
- Không để thông báo lỗi tiết lộ danh sách tài khoản/credential.
- Cho phép hủy và thử lại với challenge mới; không tái sử dụng transaction đã hết hạn/tiêu thụ.
- Tránh fallback âm thầm xuống mật khẩu yếu nếu policy yêu cầu passkey/MFA.
- Hỗ trợ khả năng tiếp cận, nhiều thiết bị và trải nghiệm conditional UI khi phù hợp.
- Hướng dẫn recovery an toàn nếu người dùng mất tất cả authenticator.

Không nên hiển thị thông tin kỹ thuật nhạy cảm từ exception hoặc assertion cho người dùng. Backend có thể log mã nguyên nhân đã chuẩn hóa để vận hành và điều tra.

## 13. Bài thực hành: xây dựng authentication ceremony cho StudyHub

**Bối cảnh:** StudyHub có website login.studyhub.example. Học viên có thể đăng nhập bằng username + passkey hoặc usernameless conditional UI. Giảng viên cần UV cho thao tác sửa điểm. Người dùng có thể ghi danh nhiều passkey và security key dự phòng. Backend lưu credential ID, public key, user handle, trạng thái và session.

### 13.1. Thiết kế cần hoàn thành

1. **Sơ đồ registration:** xác thực phiên/enrollment, tạo challenge, gọi navigator.credentials.create, xác minh attestation/registration response theo policy và lưu public key.
2. **Sơ đồ authentication:** tạo challenge, options, gọi navigator.credentials.get, trả assertion và xác minh server-side.
3. **Bảng policy:** xác định tài khoản/hành động nào yêu cầu UP, UV, discoverable credential hoặc step-up.
4. **Credential mapping:** xác định account ID nội bộ, credential ID, public key và user handle; quy tắc thêm/xóa credential.
5. **Threat model:** phân tích replay, origin/RP ID mismatch, XSS, enrollment takeover, recovery và session fixation.
6. **Bộ kiểm thử:** viết ca thành công, hủy, timeout, sai challenge, sai origin, sai chữ ký, UV thiếu, credential revoked và transaction replay.

### 13.2. Bảng kiểm tra chấp nhận

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Assertion hợp lệ từ origin được phép | Server xác minh và cấp phiên mới theo policy. |
| Challenge đã hết hạn | Từ chối; không cấp phiên. |
| Assertion dùng challenge của giao dịch khác | Từ chối. |
| clientDataJSON.type không phải webauthn.get | Từ chối. |
| Origin không thuộc allowlist | Từ chối. |
| RP ID hash không khớp | Từ chối. |
| Chữ ký không hợp lệ | Từ chối; ghi nhận sự kiện an ninh phù hợp. |
| Credential ID không tồn tại hoặc đã thu hồi | Từ chối. |
| Policy yêu cầu UV nhưng assertion không có cờ UV | Từ chối hoặc yêu cầu phương thức đạt policy; không downgrade. |
| Credential thuộc account A nhưng request được gắn account B | Từ chối. |
| Usernameless response có userHandle không khớp mapping | Từ chối. |
| Assertion bị replay sau khi đã thành công | Từ chối vì challenge/transaction đã tiêu thụ. |
| Session ID trước đăng nhập bị giữ nguyên | Kiểm thử thất bại; hệ thống phải xoay session ID. |
| Sign counter luôn bằng 0 trên passkey đồng bộ | Không tự động từ chối chỉ vì counter bằng 0; áp policy phù hợp. |
| User hủy prompt hoặc authenticator timeout | Không cấp phiên; cho phép thử lại bằng transaction mới. |
| XSS thực hiện request nhạy cảm trong phiên hợp lệ | Kiểm soát XSS/CSRF và step-up hạn chế tác động; WebAuthn không được xem là giải pháp thay thế. |

### 13.3. Câu hỏi tự đánh giá

1. Authentication ceremony khác registration ceremony ở mục đích và dữ liệu nào?
2. Vì sao challenge phải do server tạo và chỉ dùng một lần?
3. clientDataJSON và authenticatorData chứa những thông tin gì?
4. RP ID hash và origin bảo vệ những ranh giới nào?
5. UP khác UV thế nào? Khi nào server phải bắt buộc UV?
6. Tại sao chữ ký hợp lệ vẫn chưa đủ để cấp quyền?
7. Khi nào dùng allowCredentials, khi nào dùng discoverable credential?
8. Vì sao sign counter có thể không tăng trên passkey đồng bộ?
9. Attestation thuộc giai đoạn nào? Vì sao không phải bước bắt buộc trong mọi authentication?
10. WebAuthn chống phishing nhưng không tự bảo vệ session/recovery như thế nào?

**Tiêu chí hoàn thành:** Người học có thể giải thích dữ liệu được ký, vẽ đúng luồng từ request options đến assertion verification, chỉ ra mỗi kiểm tra phải chạy ở browser hay server, và viết test chứng minh assertion sai ngữ cảnh, sai credential hoặc bị replay không thể tạo phiên.

## 14. Tài liệu đọc tiếp

- **W3C Web Authentication (WebAuthn) Level 2/Level 3**: cấu trúc request/response, credential, flags, discoverable credentials và các thuật toán xác minh.
- **FIDO Alliance — Passkeys**: passkey đồng bộ, device-bound credential, UX và khả năng tương tác.
- **MDN Web Docs — Web Authentication API**: cách dùng navigator.credentials.create() và navigator.credentials.get() trong browser.
- **OWASP Authentication Cheat Sheet và ASVS**: quản lý credential, session, enrollment, recovery và kiểm thử.
- **NIST SP 800-63B**: đánh giá authenticator, user verification và mức bảo đảm; đối chiếu phiên bản hiện hành.

Khi triển khai thực tế, dùng thư viện WebAuthn server-side được duy trì, kiểm tra đúng phiên bản chuẩn, cấu hình RP ID/origin chặt chẽ và kiểm thử trên các browser/authenticator mục tiêu. **Authentication ceremony chỉ hoàn tất khi RP xác minh đầy đủ assertion và cấp phiên theo policy ở phía server.**
