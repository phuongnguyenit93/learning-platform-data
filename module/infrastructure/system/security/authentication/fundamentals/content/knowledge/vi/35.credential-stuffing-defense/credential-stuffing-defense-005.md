# Online guessing

## 1. Online guessing là gì?

**Online guessing (đoán credential trực tuyến)** là kiểu tấn công trong đó attacker gửi nhiều lần thử xác thực tới dịch vụ đang hoạt động, với mục tiêu tìm được password, PIN, OTP hoặc một bí mật đăng nhập hợp lệ. Khác với việc đoán offline trên bản sao database bị đánh cắp, online guessing tương tác trực tiếp với endpoint đăng nhập và phải đối mặt với các kiểm soát như rate limit, MFA, phát hiện bot và giám sát rủi ro.

Ví dụ: một cổng doanh nghiệp cho phép đăng nhập bằng email và password. Attacker thử hàng nghìn mật khẩu phổ biến cho một tài khoản, hoặc thử một mật khẩu phổ biến trên hàng nghìn tài khoản. Nếu không có kiểm soát phù hợp, attacker có thể tìm được tài khoản dùng mật khẩu yếu hoặc gây quá tải cho hệ thống xác thực.

Online guessing không chỉ là gửi nhiều request từ một IP. Attacker có thể phân tán request qua nhiều địa chỉ mạng, thiết bị, proxy hoặc tài khoản; thay đổi tốc độ và user agent; hoặc kết hợp mật khẩu bị rò rỉ với các mẫu đoán phổ biến. Vì vậy, phòng thủ cần kết hợp nhiều tín hiệu và đặt giới hạn ở nhiều cấp.

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, online guessing là một mối đe dọa trực tiếp tới password, MFA và account recovery. Mục tiêu của phòng thủ là làm cho việc đoán trực tuyến khó mở rộng, phát hiện hành vi bất thường, hạn chế tác động lên người dùng hợp lệ và không tạo ra một đường vòng yếu hơn qua OTP hoặc recovery.

## 2. Phân biệt các kiểu tấn công đoán credential

Các thuật ngữ thường bị dùng lẫn nhau, nhưng chiến thuật và tín hiệu phòng thủ khác nhau:

| Kiểu tấn công | Cách thực hiện | Tín hiệu thường thấy |
| --- | --- | --- |
| **Brute-force guessing** | Thử nhiều password khác nhau cho một tài khoản hoặc một tập nhỏ tài khoản. | Nhiều lần thất bại tập trung vào một principal hoặc một endpoint. |
| **Password spraying** | Thử một vài password phổ biến trên nhiều tài khoản để tránh ngưỡng khóa theo từng tài khoản. | Một password hoặc một nhóm nhỏ password được thử trên nhiều principal. |
| **Credential stuffing** | Dùng cặp username/password đã bị lộ từ dịch vụ khác để đăng nhập nơi khác. | Nhiều cặp credential, tỷ lệ thất bại cao, thiết bị/IP phân tán và một số lần thành công bất thường. |
| **Dictionary attack** | Dùng danh sách từ hoặc password phổ biến để đoán. | Các mẫu password có tính phổ biến hoặc biến thể dễ dự đoán. |
| **PIN/OTP guessing** | Thử mã số ngắn hoặc mã dùng một lần trong cửa sổ hiệu lực. | Nhiều lần thử trong cùng challenge hoặc nhiều challenge liên tiếp. |

Credential stuffing dùng thông tin xác thực đã có từ trước; password spraying và brute force chủ yếu thử đoán bí mật. Trong thực tế, attacker có thể phối hợp nhiều kiểu trong cùng chiến dịch.

### 2.1. Online guessing và offline guessing

**Online guessing** gửi thử nghiệm qua dịch vụ xác thực. Server có thể đếm lần thử, giới hạn tốc độ, yêu cầu MFA hoặc từ chối nguồn có rủi ro.

**Offline guessing** xảy ra khi attacker có được password hash hoặc verifier và thử đoán trên máy của họ. Rate limit ở login endpoint không ngăn được việc đoán offline. Biện pháp chính cho offline guessing là password hashing chậm có salt riêng, cấu hình cost phù hợp, bảo vệ database và secret pepper nếu kiến trúc sử dụng.

Không nên nhầm hai lớp phòng thủ: rate limiting bảo vệ endpoint trực tuyến; Argon2id, scrypt hoặc bcrypt được cấu hình phù hợp giúp làm chậm việc kiểm tra password khi verifier bị lộ.

## 3. Mô hình đe dọa và mục tiêu phòng thủ

Attacker có thể:

- Biết email, username hoặc mã nhân viên của nạn nhân.
- Có danh sách password phổ biến, password đã lộ hoặc biến thể từ dữ liệu cá nhân.
- Gửi request từ nhiều IP, ASN, proxy, thiết bị hoặc browser profile.
- Phân phối tốc độ thử để tránh ngưỡng đơn giản.
- Dò xem tài khoản có tồn tại, bị khóa hay có bật MFA không.
- Chuyển sang endpoint OTP, password reset, recovery hoặc API đăng nhập khác khi login chính bị giới hạn.
- Dùng thông tin lỗi, thời gian phản hồi và trạng thái HTTP để suy ra kết quả.

Phòng thủ cần đạt các mục tiêu:

1. Giới hạn số lần đoán có thể thực hiện đối với một principal và toàn hệ thống.
2. Nhận diện chiến dịch phân tán như password spraying và credential stuffing.
3. Không để attacker khóa tài khoản nạn nhân một cách dễ dàng.
4. Giảm khả năng đoán thành công bằng MFA, passkey và kiểm tra password bị lộ.
5. Không tiết lộ tài khoản có tồn tại hoặc factor nào đã đăng ký.
6. Bảo vệ các endpoint phụ trợ có thể dùng để vượt qua login policy.
7. Giữ trải nghiệm đăng nhập hợp lệ và có quy trình khôi phục khi người dùng bị giới hạn nhầm.

Không có một kiểm soát đơn lẻ nào đủ để chống mọi biến thể. Một IP blocklist có thể chặn một nguồn cụ thể nhưng không giải quyết được botnet; lockout cứng có thể ngăn đoán nhưng tạo điều kiện denial of service; CAPTCHA có thể tăng chi phí tự động hóa nhưng không thay thế xác minh credential.

## 4. Những nơi cần bảo vệ

Rate limit chỉ ở form đăng nhập là chưa đủ. Attacker có thể thử một endpoint khác hoặc gọi trực tiếp API:

| Endpoint/flow | Rủi ro |
| --- | --- |
| Password login | Brute force, spraying, stuffing và account enumeration. |
| MFA challenge/TOTP | Đoán mã ngắn, replay hoặc thử lại nhiều challenge. |
| Push approval | MFA fatigue và gửi nhiều prompt gây nhầm lẫn. |
| Password reset | Dò tài khoản, lạm dụng gửi email/SMS và chiếm recovery channel. |
| Account recovery | Đoán recovery code hoặc khai thác quy trình hỗ trợ yếu. |
| Passkey fallback | Attacker ép người dùng chuyển sang phương thức yếu hơn. |
| API/token endpoint | Thử credential hoặc client secret qua giao thức khác. |
| Enrollment endpoint | Thêm factor của attacker sau khi vượt qua bước xác thực yếu. |

Các endpoint có thể chia sẻ cùng một risk engine hoặc quota policy. Nếu login endpoint giới hạn nhưng password reset và MFA endpoint không giới hạn, attacker có thể chuyển tải tấn công sang các đường đó.

## 5. Rate limiting nhiều chiều

**Rate limiting** giới hạn số lần thử trong một khoảng thời gian. Với online guessing, nên kết hợp nhiều chiều thay vì chỉ giới hạn theo IP:

- **Per account/principal:** tổng số lần thất bại hoặc challenge trong một cửa sổ.
- **Per source IP/network:** giới hạn tốc độ từ một nguồn hoặc một dải mạng.
- **Per device/session:** nhận diện việc một thiết bị thử nhiều tài khoản.
- **Per tenant/client:** bảo vệ một tổ chức hoặc ứng dụng khỏi bị một chiến dịch làm cạn tài nguyên.
- **Global service limit:** bảo vệ hệ thống xác thực và dependency khỏi quá tải.
- **Per challenge/factor:** giới hạn thử OTP, recovery code hoặc challenge cụ thể.

Mỗi chiều giải quyết một mẫu tấn công. Per-account limit giúp chống brute force tập trung; per-source limit giảm tốc độ từ một nguồn; per-device và cross-account signals giúp phát hiện spraying; global limit bảo vệ dịch vụ trước lưu lượng bất thường.

### 5.1. Cửa sổ và thuật toán giới hạn

Một số cách triển khai:

| Cách | Đặc điểm | Lưu ý |
| --- | --- | --- |
| Fixed window | Đếm số request trong từng khoảng cố định. | Đơn giản nhưng có thể tạo burst ở ranh giới hai cửa sổ. |
| Sliding window | Tính số request trong khoảng thời gian trượt. | Phản ánh tốc độ tốt hơn nhưng cần lưu/ước lượng trạng thái. |
| Token bucket | Request tiêu thụ token; token được bổ sung theo tốc độ. | Cho phép burst có giới hạn và kiểm soát tốc độ trung bình. |
| Leaky bucket | Xử lý request theo tốc độ ổn định. | Hữu ích để làm phẳng tải, cần quyết định request bị xếp hàng hay từ chối. |

Chọn thuật toán theo yêu cầu latency, quy mô và khả năng vận hành. Với endpoint xác thực, việc từ chối nhanh khi vượt ngưỡng thường phù hợp hơn xếp hàng lâu khiến attacker giữ tài nguyên.

### 5.2. Khóa hoặc băm định danh principal

Để đếm theo tài khoản trước khi biết username có hợp lệ hay không, hệ thống có thể chuẩn hóa account identifier rồi tạo khóa đếm bằng HMAC với secret phía server. Nhờ vậy, kho rate-limit không cần lưu email/username thô.

Không dùng giá trị do client gửi làm định danh đáng tin nếu nó có thể thay đổi cách chuẩn hóa. Cần nhất quán về Unicode normalization, chữ hoa/thường, alias và tenant scope theo quy tắc đăng nhập thực tế.

## 6. Tránh account lockout trở thành denial of service

Khóa tài khoản sau một số lần nhập sai có thể làm giảm brute force, nhưng cũng cho phép attacker cố tình nhập sai nhiều lần để khóa tài khoản của người khác. Đây là một dạng denial of service.

Các lựa chọn thay thế hoặc bổ sung:

- Throttling tăng dần theo số lần thất bại.
- Cooldown ngắn, có giới hạn và tự hết hạn.
- Giới hạn theo account kết hợp source/device/global signals.
- Step-up hoặc CAPTCHA theo risk policy.
- Yêu cầu phương thức phishing-resistant khi tín hiệu đủ mạnh.
- Giữ tài khoản ở trạng thái đăng nhập bình thường nhưng tạm giới hạn hành động nhạy cảm khi có dấu hiệu rủi ro.
- Cung cấp quy trình hỗ trợ khôi phục khi người dùng hợp lệ bị chặn nhầm.

Nếu cần khóa tài khoản vì rủi ro cao, phải có lý do, thời hạn, thông báo phù hợp và con đường mở khóa đã xác minh. Không nên dùng lockout vô thời hạn chỉ dựa trên số request từ một nguồn không đáng tin.

### 6.1. Throttling tăng dần

Ví dụ chính sách khái niệm:

~~~text
Sau vài lần thất bại:
  áp dụng cooldown ngắn cho principal

Nếu tiếp tục thất bại:
  tăng thời gian chờ theo giới hạn tối đa
  đánh giá nguồn, thiết bị và pattern cross-account

Nếu có tín hiệu rủi ro cao:
  yêu cầu step-up hoặc chuyển review

Khi hết cooldown:
  cho phép thử lại theo quota bình thường
~~~

Đây là ví dụ logic, không phải các ngưỡng cố định. Cần tránh tiết lộ chính xác quota nội bộ ra ngoài vì attacker có thể điều chỉnh tốc độ để nằm dưới ngưỡng.

## 7. Phát hiện password spraying và stuffing

Chỉ đếm số lần sai trên một tài khoản không đủ. Password spraying thường cố tình giữ số lần thử trên từng tài khoản thấp trong khi thử rất nhiều tài khoản.

Các tín hiệu có thể kết hợp:

- Một nguồn hoặc cụm nguồn thử nhiều principal trong thời gian ngắn.
- Một password pattern xuất hiện trên nhiều tài khoản (không cần lưu password thô để phân tích).
- Nhiều tài khoản thất bại nhưng có cùng đặc điểm thiết bị, automation hoặc network.
- Tỷ lệ thất bại tăng bất thường so với baseline của tenant hoặc ứng dụng.
- Một số lần đăng nhập thành công xen giữa số lượng lớn thất bại.
- Nhiều request dùng user agent, TLS/client fingerprint hoặc hành vi browser giống nhau bất thường.
- Thử đăng nhập trên nhiều tenant hoặc nhiều ứng dụng trong cùng một khoảng thời gian.

Không nên coi một IP, ASN, user agent hoặc thiết bị là bằng chứng chắc chắn của tấn công. Mạng doanh nghiệp, NAT, VPN và thiết bị dùng chung có thể khiến nhiều người hợp lệ xuất hiện giống nhau. Risk engine cần kết hợp nhiều tín hiệu, có ngưỡng và đánh giá false positive.

### 7.1. Kiểm tra password bị lộ

Khi người dùng đặt hoặc đổi password, hệ thống có thể kiểm tra password có nằm trong danh sách password phổ biến hoặc đã xuất hiện trong các vụ rò rỉ đã biết hay không. Mục tiêu là ngăn người dùng chọn một bí mật đã bị attacker biết.

Việc kiểm tra cần bảo vệ chính password:

- Không gửi password plaintext tới dịch vụ bên thứ ba tùy tiện.
- Nếu dùng dịch vụ kiểm tra breach, đánh giá giao thức bảo vệ truy vấn, chính sách dữ liệu và nhà cung cấp.
- Không log password hoặc hash có thể dùng để xác định password.
- Không từ chối chỉ dựa trên một danh sách nhỏ hoặc lỗi thời; kết hợp password blocklist, độ dài và hướng dẫn chọn password.

Kiểm tra password bị lộ khi đặt/đổi mật khẩu giúp giảm credential stuffing trong tương lai; nó không thay thế MFA, rate limiting hoặc phát hiện tấn công đang diễn ra.

## 8. MFA và passkey làm giảm giá trị của password guessing

MFA bổ sung yếu tố khác ngoài password, khiến password đúng chưa đủ để hoàn tất đăng nhập. Tuy nhiên, hiệu quả phụ thuộc loại factor:

- **TOTP:** thêm yếu tố possession nhưng mã có thể bị phishing/relay trong cửa sổ hiệu lực; cần giới hạn thử và chống replay.
- **Push approval:** có thể bị MFA fatigue; hiển thị context, number matching hoặc biện pháp xác nhận rõ ràng.
- **Security key/WebAuthn:** ràng buộc credential với RP ID/origin, giúp chống phishing tốt khi triển khai đúng.
- **Passkey:** dùng public-key credential và user verification theo policy; không chia sẻ password để attacker thử lại trên nhiều dịch vụ.

MFA không được triển khai như một bước có thể bỏ qua dễ dàng. Nếu attacker chỉ cần chọn “Use another method” để quay về password-only, đường fallback trở thành mục tiêu chính.

### 8.1. Bảo vệ endpoint OTP

OTP thường có không gian giá trị nhỏ hơn password. Vì vậy:

- Giới hạn số lần thử trên mỗi challenge và mỗi tài khoản.
- Gắn OTP với đúng flow, purpose và thời hạn.
- Tiêu thụ mã thành công một lần; không chấp nhận replay.
- Tạo challenge mới theo policy và không cho attacker tạo vô hạn challenge để có thêm lượt thử.
- Không tiết lộ mã đúng/sai theo cách giúp dò thông tin tài khoản.
- Giới hạn việc gửi SMS/email để chống spam và chi phí phát sinh.

### 8.2. Không bỏ qua passkey khi password thất bại

Nếu tài khoản đã đăng ký passkey, ứng dụng có thể cung cấp lựa chọn đăng nhập passkey theo policy. Nhưng không nên tiết lộ tài khoản có passkey hay không trước khi người dùng được xác minh ở mức phù hợp. Với tài khoản cần phishing-resistant authentication, không được âm thầm downgrade sang password-only chỉ vì passkey không khả dụng.

## 9. Chống account enumeration

Account enumeration xảy ra khi attacker phân biệt được tài khoản tồn tại, không tồn tại, bị khóa hoặc có factor nào dựa trên phản hồi của hệ thống.

Kiểm soát:

- Dùng thông báo chung cho các trường hợp không thể xác thực trước khi xác minh danh tính.
- Tránh khác biệt thời gian phản hồi quá rõ giữa tài khoản tồn tại và không tồn tại.
- Không hiển thị “email này chưa đăng ký” ở endpoint nhạy cảm nếu điều đó tạo oracle.
- Không tiết lộ số factor, recovery code còn lại hoặc trạng thái account lockout.
- Áp dụng rate limit cả với account hint không tồn tại.
- Giữ mã lý do chi tiết trong log nội bộ có kiểm soát.

Thông báo chung không có nghĩa là không được giúp người dùng. Sau khi xác minh qua kênh phù hợp, ứng dụng có thể hướng dẫn họ khôi phục tài khoản hoặc liên hệ quản trị viên.

## 10. Kiến trúc rate limit trong hệ thống phân tán

Nếu dịch vụ đăng nhập chạy trên nhiều instance, bộ đếm trong RAM của từng instance không bảo đảm giới hạn toàn hệ thống. Attacker có thể phân tán request để mỗi instance chỉ thấy một phần nhỏ.

Một kiến trúc tham khảo:

~~~mermaid
flowchart TD
    C["Login request"] --> E["Edge / WAF"]
    E --> R["Shared rate-limit service"]
    R --> P["Risk and abuse signals"]
    P --> A["Authentication service"]
    A --> V["Credential verifier"]
    A --> S["Session service"]
    R --> L["Security telemetry"]
    P --> L
    A --> L
~~~

Các nguyên tắc triển khai:

- Dùng kho đếm dùng chung hoặc cơ chế quota phân tán có tính nhất quán phù hợp.
- Cập nhật bộ đếm nguyên tử để tránh nhiều instance cùng cho phép vượt quota.
- Đặt TTL cho counter để dữ liệu cũ tự hết hạn.
- Dùng key namespace tách tenant, endpoint, principal và source.
- Giới hạn kích thước input trước khi chuẩn hóa hoặc tính HMAC.
- Có global circuit breaker để bảo vệ hệ thống khi dependency bị quá tải.
- Theo dõi độ trễ và lỗi của rate-limit service; định nghĩa rõ hành vi khi dịch vụ này không khả dụng.

Với login nhạy cảm, nếu rate-limit service lỗi, không nên mặc định bỏ qua mọi giới hạn. Có thể dùng quota bảo thủ tại edge hoặc tạm từ chối một số request cho tới khi trạng thái được phục hồi, tùy yêu cầu availability và threat model.

## 11. Ví dụ pseudocode quyết định rate limit

Đoạn mã khái niệm:

~~~ts
async function evaluateLoginAttempt(input) {
  const principalKey = hmacAccountKey(
    normalizeAccountIdentifier(input.account, input.tenantId)
  );
  const sourceKey = classifySource(input.ip, input.deviceSignals);

  const limits = await rateLimiter.consumeAtomically([
    { key: "principal:" + principalKey, policy: "login-principal" },
    { key: "source:" + sourceKey, policy: "login-source" },
    { key: "tenant:" + input.tenantId, policy: "login-tenant" },
    { key: "global:login", policy: "login-global" }
  ]);

  if (!limits.allowed) {
    await securityEvents.record("login.throttled", {
      tenantId: input.tenantId,
      requestId: input.requestId
    });
    return { allowed: false, reason: "throttled" };
  }

  return riskEngine.evaluate(input);
}
~~~

Đây là pseudocode minh họa. Production cần tránh ghi account identifier thô vào telemetry, kiểm tra input và tenant, bảo vệ HMAC key, xử lý IP proxy chỉ từ header do edge tin cậy thiết lập, và bảo đảm bộ đếm được cập nhật nhất quán. Không tin `X-Forwarded-For` do client tự gửi nếu request không đi qua proxy tin cậy.

## 12. Giám sát và cảnh báo

Hệ thống nên theo dõi:

- Tỷ lệ login thất bại/thành công theo thời gian, tenant, ứng dụng và phương thức.
- Số principal bị thử từ một nguồn hoặc cụm nguồn.
- Số nguồn thử một principal.
- Pattern password spraying hoặc credential stuffing trên nhiều tài khoản.
- Số lần OTP sai, challenge tạo mới và push bị từ chối.
- Số lần throttling, cooldown, lockout và false positive.
- Tỷ lệ login thành công bất thường sau một chuỗi thất bại.
- Lưu lượng tăng ở password reset/recovery khi login chính bị chặn.
- Lỗi, latency và saturation của rate-limit service.

Alert nên phân biệt sự cố diện rộng với một người dùng nhập sai password vài lần. Có thể dùng baseline theo tenant, giờ làm việc và phương thức xác thực; tránh đặt ngưỡng quá nhạy khiến đội vận hành bị cảnh báo liên tục.

Khi phát hiện chiến dịch, response có thể gồm tăng throttling, yêu cầu step-up, chặn nguồn có bằng chứng rõ, thu hồi session đáng ngờ, yêu cầu đổi password đã lộ và thông báo cho người dùng bị ảnh hưởng. Mọi hành động cần có phạm vi, thời hạn và cách rollback để giảm ảnh hưởng tới người dùng hợp lệ.

## 13. Trải nghiệm người dùng và xử lý false positive

Kiểm soát đoán credential có thể ảnh hưởng người dùng hợp lệ, đặc biệt khi nhiều nhân viên dùng chung NAT, người dùng đi công tác hoặc password manager tự điền password cũ.

Trải nghiệm nên:

- Giải thích khi nào người dùng cần chờ và thời gian chờ ở mức phù hợp.
- Không tiết lộ ngưỡng nội bộ hoặc tín hiệu risk cụ thể.
- Cho phép thử lại sau cooldown mà không buộc tạo tài khoản mới.
- Cung cấp phương thức khôi phục đã xác minh khi bị chặn nhầm.
- Hỗ trợ người dùng có nhu cầu tiếp cận khác nhau; không phụ thuộc CAPTCHA thị giác duy nhất.
- Không yêu cầu người dùng thay password liên tục nếu không có lý do; việc đổi quá thường xuyên có thể khiến họ chọn password dễ đoán.
- Có kênh báo cáo nếu nhận được thông báo đăng nhập không phải do họ thực hiện.

Không nên tự động khóa toàn bộ tenant chỉ vì một nguồn IP có nhiều lần thất bại; đó có thể là NAT lớn hoặc một chiến dịch tấn công đang dùng nguồn phân tán. Quyết định cần dựa trên nhiều tín hiệu và có giới hạn tác động.

## 14. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ rate limit theo IP | Attacker phân tán nguồn để vượt giới hạn. | Kết hợp principal, source, device, tenant và global quota. |
| Chỉ đếm theo tài khoản | Password spraying giữ số lần thử mỗi tài khoản thấp. | Phân tích cross-account và pattern nguồn/password. |
| Khóa cứng tài khoản sau vài lần sai | Attacker có thể gây denial of service cho nạn nhân. | Throttling tăng dần, cooldown và risk-based controls. |
| Rate limit lưu trong RAM từng instance | Nhiều instance cho phép vượt quota tổng. | Dùng shared counter hoặc distributed quota. |
| Không bảo vệ MFA/recovery endpoint | Attacker chuyển sang đường phụ yếu hơn. | Áp dụng quota và risk policy xuyên suốt auth flows. |
| OTP không one-time | Mã đã dùng có thể replay. | Consume nguyên tử và gắn mã với challenge/purpose. |
| Tin header IP do client tự gửi | Attacker giả mạo source để né hoặc gây block. | Chỉ dùng forwarding header từ proxy/edge tin cậy. |
| Thông báo lỗi phân biệt account tồn tại | Account enumeration. | Phản hồi chung và audit nội bộ chi tiết. |
| CAPTCHA được coi là biện pháp duy nhất | Bot nâng cấp hoặc dịch vụ giải CAPTCHA có thể vượt qua. | Dùng như tín hiệu bổ sung cùng rate limit, MFA và risk engine. |
| Password breach check gửi plaintext tùy tiện | Tạo thêm nơi lộ password. | Dùng giao thức và nhà cung cấp đã đánh giá; không log secret. |
| Fallback MFA cho phép password-only | Attacker downgrade khi factor mạnh bị chặn. | Enforce assurance policy phía server. |
| Không theo dõi false positive | Người dùng hợp lệ bị chặn và tìm cách né kiểm soát. | Theo dõi, điều chỉnh quota và cung cấp recovery an toàn. |

## 15. Ví dụ: phát hiện password spraying trên cổng nhân viên

Một cổng nhân viên ghi nhận nhiều lần đăng nhập thất bại. Mỗi tài khoản chỉ có hai lần thử trong vài phút, nhưng cùng một nhóm nguồn đã thử hàng trăm tài khoản bằng một số ít password pattern.

**Cách xử lý:**

1. Edge áp dụng quota theo source/network và global login traffic.
2. Risk engine tổng hợp số principal được thử theo source/device cluster trong cửa sổ thời gian.
3. Per-account throttling giới hạn thêm các lần thử trên từng principal.
4. Hệ thống không khóa vĩnh viễn toàn bộ tài khoản chỉ dựa trên số lần sai.
5. Tài khoản có tín hiệu đăng nhập bất thường được yêu cầu passkey/security key hoặc MFA theo policy.
6. Các endpoint password reset, TOTP và recovery cũng được giám sát để tránh chuyển hướng tấn công.
7. Security team nhận cảnh báo có context, xác định phạm vi, chặn nguồn có bằng chứng và kiểm tra các lần login thành công xen giữa.
8. Người dùng bị ảnh hưởng nhận thông báo phù hợp và có thể báo cáo hoạt động không nhận biết.

**Điểm cần nhớ:** số lần thử trên mỗi tài khoản thấp không có nghĩa hệ thống an toàn. Cần nhìn cả hành vi trên nhiều tài khoản và nhiều nguồn.

## 16. Checklist phòng thủ online guessing

Trước khi đưa login flow vào production, hãy kiểm tra:

1. Đã phân biệt brute force, password spraying, credential stuffing và offline guessing trong threat model chưa?
2. Có rate limit theo principal, source, device/session, tenant, challenge và global service không?
3. Counter có được cập nhật nguyên tử và chia sẻ giữa các instance không?
4. Có kiểm soát lockout để tránh attacker khóa tài khoản nạn nhân không?
5. Có phân tích cross-account và nhiều nguồn để phát hiện spraying/stuffing không?
6. Password bị lộ/phổ biến có được chặn khi đặt hoặc đổi mật khẩu bằng quy trình bảo vệ dữ liệu phù hợp không?
7. MFA, TOTP, push, passkey, password reset và recovery endpoint có quota/risk policy tương ứng không?
8. OTP/recovery code có challenge binding, expiry, one-time use và chống replay không?
9. Fallback có giữ nguyên assurance policy và không cho downgrade tùy tiện không?
10. Phản hồi login có tránh account enumeration và timing oracle không?
11. Proxy/IP headers có chỉ được tin từ edge/proxy đã cấu hình không?
12. Rate-limit service lỗi có hành vi fail-safe được định nghĩa và giám sát không?
13. Có dashboard/alert cho tỷ lệ thất bại, spraying, stuffing, throttling và false positive không?
14. Có quy trình incident response, thông báo người dùng, revoke session và đổi credential bị lộ không?
15. Có kiểm thử NAT dùng chung, bot phân tán, nhiều instance, cooldown, race condition, MFA fallback và recovery abuse không?

**Kết luận:** Online guessing là việc thử credential trực tiếp qua dịch vụ xác thực, gồm brute force, password spraying và credential stuffing. Phòng thủ cần rate limiting nhiều chiều, phát hiện hành vi trên nhiều tài khoản, throttling tăng dần, MFA/passkey, bảo vệ OTP và recovery, chống account enumeration và giám sát liên tục. Account lockout cứng hoặc chặn IP đơn lẻ không đủ và có thể gây gián đoạn cho người dùng hợp lệ. Hệ thống phải kết hợp kiểm soát ở edge, authentication service và các luồng phụ, đồng thời phân biệt rõ online guessing với offline password cracking.
