# Reauthentication trigger

## Mục tiêu và phạm vi

**Reauthentication trigger** là điều kiện khiến dịch vụ yêu cầu người dùng xác thực lại trước khi tiếp tục một session hoặc thực hiện một hành động. Trigger xác định **khi nào phải kiểm tra lại quyền kiểm soát tài khoản**, đồng thời chỉ rõ bằng chứng nào còn thiếu, hành động nào phải chờ và kết quả xác thực được dùng trong phạm vi nào.

Trong chương **Reauthentication** của module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, bài học đặt trigger vào luồng người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Mục tiêu là kết hợp đánh giá rủi ro, token dùng một lần, xác minh danh tính, chống lạm dụng và kiểm soát session để giảm nguy cơ chiếm đoạt tài khoản.

Sau bài này, người học cần có khả năng:

- Phân biệt tái xác thực, step-up, đăng nhập mới và khôi phục tài khoản.
- Chọn trigger theo hành động, thời gian, sự kiện bảo mật và bối cảnh rủi ro.
- Thiết kế cổng kiểm tra phía server để hành động nhạy cảm chưa được thực hiện trước khi đủ bằng chứng.
- Ràng buộc kết quả tái xác thực với đúng tài khoản, session, mục đích và trạng thái bảo mật.
- Xử lý trường hợp mất factor, lỗi IdP hoặc yêu cầu lặp mà không tạo lối bỏ qua kiểm soát.

Các profile, tên trạng thái, khoảng thời gian và hạn mức trong bài là chính sách minh họa của một dịch vụ giả định. Chúng không phải cấu hình mặc định của mọi sản phẩm hoặc bằng chứng hệ thống đã đáp ứng đầy đủ một chuẩn xác thực.

## 1. Tái xác thực giải quyết vấn đề gì?

### 1.1. Session còn hiệu lực chưa đủ cho mọi hành động

Một session cho phép người dùng duy trì tương tác mà không phải nhập credential ở mỗi request. Nhưng session cookie có thể bị đánh cắp, trình duyệt có thể bị người khác sử dụng, hoặc bằng chứng xác thực ban đầu đã quá cũ đối với hành động đang yêu cầu.

Ví dụ, đọc danh sách khóa học và thay email recovery có tác động khác nhau. Một session được chấp nhận cho thao tác đọc chưa chắc đủ để thay kênh sẽ dùng khôi phục tài khoản về sau.

OWASP khuyến nghị tái xác thực cho tính năng nhạy cảm và sau các sự kiện rủi ro như account recovery, password reset hoặc hành vi đáng ngờ. [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)

Trigger không chỉ là mở thêm một hộp thoại. Trigger phải làm thay đổi quyết định ở backend: hành động liên quan chưa được thực hiện cho tới khi yêu cầu xác thực và các điều kiện phân quyền cùng đạt.

### 1.2. Phân biệt bốn đường xử lý

| Đường xử lý | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Reauthentication | Xác nhận lại bằng chứng theo yêu cầu về độ mới và bối cảnh | Yêu cầu dùng lại passkey trước khi đổi email |
| Step-up authentication | Đạt mức hoặc thuộc tính xác thực mạnh hơn bằng chứng hiện có | Session dùng phương thức yếu hơn phải chuyển sang phương thức chống phishing |
| Đăng nhập mới | Thiết lập context xác thực khi session không còn hợp lệ hoặc không có session | Session đã bị thu hồi, người dùng phải đăng nhập lại |
| Account recovery | Lấy lại khả năng truy cập khi không còn hoàn thành được xác thực cần thiết | Mất cả mật khẩu và thiết bị MFA |

Reauthentication và step-up có thể cùng xuất hiện. Người dùng vừa cần bằng chứng mới hơn, vừa cần loại phương thức khác. Ngược lại, tái xác thực không luôn yêu cầu thêm một factor mới: phương thức và tổ hợp bằng chứng phải theo chính sách của hành động.

Một tài khoản không có mật khẩu nhưng dùng passkey hợp lệ không nên bị bắt “nhập mật khẩu hiện tại” chỉ vì hệ thống hard-code mọi trigger thành một biểu mẫu mật khẩu.

### 1.3. Tái xác thực không thay phân quyền hoặc gỡ hold

Một người có thể xác thực lại thành công nhưng không có quyền xóa dữ liệu, tài khoản đang bị vô hiệu hóa hoặc thao tác đang bị security hold. Khi đó, kết quả xác thực không làm hành động trở nên được phép.

Tương tự, một session đã bị thu hồi không được khôi phục chỉ bằng việc đặt cờ `reauthenticated=true`. Cần đi theo đường xác thực và phát hành context mới phù hợp.

## 2. Nhóm trigger theo nguồn phát sinh

### 2.1. Trigger theo hành động nhạy cảm

Đây là nhóm có thể khai báo trực tiếp trong chính sách ứng dụng.

| Hành động | Vì sao cần xem xét trigger? | Điều kiện bổ sung ngoài xác thực |
| --- | --- | --- |
| Đổi mật khẩu khi đang đăng nhập | Có thể thay quyền truy cập tài khoản | Credential mới đạt chính sách và đúng luồng thay đổi |
| Thêm hoặc thay MFA/passkey | Có thể cấp đường đăng nhập lâu dài cho người khác | Kiểm soát enrollment và trạng thái credential |
| Xóa factor cuối cùng | Có thể làm tài khoản mất cơ chế bảo vệ cần thiết | Chính sách có cho phép xóa hay phải thay thế trước |
| Đổi email/số điện thoại recovery | Có thể chuyển quyền khôi phục tương lai | Xác minh kênh mới và các điều kiện bảo vệ kênh cũ |
| Tạo hoặc thay bộ recovery code | Cấp bí mật có thể dùng phục hồi tài khoản | Thu hồi bộ cũ theo chính sách và bảo vệ lần hiển thị |
| Tạo API key hoặc cấp quyền ứng dụng | Có thể mở truy cập dài hạn ngoài session hiện tại | Scope, thời hạn và quyền cấp của chủ thể |
| Xuất dữ liệu nhạy cảm hoặc xóa tài khoản | Tác động lớn, khó đảo ngược | Quyền tài nguyên, xác nhận ý định và điều kiện nghiệp vụ |
| Nâng quyền hoặc dùng chức năng quản trị | Tăng phạm vi ảnh hưởng | Vai trò hiện tại và đường xác thực quản trị được phép |

Không phải mọi hành động đều dùng cùng cửa sổ độ mới hay cùng phương thức. Một policy cho đổi email không tự đủ cho việc thêm quản trị viên hoặc tạo API key có quyền rộng.

Trigger phải nằm trên tất cả endpoint thực hiện cùng hành động: giao diện web, ứng dụng di động, API nội bộ và các đường tương đương. Chỉ kiểm tra ở trang cài đặt để lại đường gọi API trực tiếp không được bảo vệ.

### 2.2. Trigger theo thời gian

Cần phân biệt ba loại đồng hồ:

| Đồng hồ | Đo điều gì? | Điều không được dùng thay thế |
| --- | --- | --- |
| Tuổi session tổng thể | Thời gian từ lần xác thực/tái xác thực làm cơ sở cho session | Thời gian phát access token gần nhất |
| Thời gian không hoạt động | Khoảng không có hoạt động được hệ thống tính hợp lệ | Một timestamp do client tự khai báo |
| Tuổi bằng chứng cho hành động | Thời gian từ sự kiện xác thực phù hợp với action cụ thể | Thời gian click nút hoặc mở trang |

NIST phân biệt overall timeout và inactivity timeout. Hoạt động cập nhật giới hạn không hoạt động; tái xác thực thành công mới đặt lại các giới hạn tương ứng theo yêu cầu áp dụng. [NIST SP 800-63B-4 — Session Management](https://pages.nist.gov/800-63-4/sp800-63b/session/)

Ví dụ chính sách ứng dụng: đổi kênh recovery cần sự kiện xác thực phù hợp trong 5 phút gần nhất. Một session vẫn đủ điều kiện đọc nội dung sau 20 phút không hoạt động nhạy cảm có thể phải tái xác thực để đổi kênh.

Không kéo dài vô hạn tuổi xác thực bằng heartbeat, refresh token hoặc request nền. Các thao tác này không tự tạo bằng chứng người dùng vừa kiểm soát authenticator.

### 2.3. Trigger theo sự kiện bảo mật

Một sự kiện có thể làm kết quả xác thực trước đó không còn phù hợp:

- Hoàn tất reset mật khẩu hoặc recovery tài khoản.
- Thay đổi credential, recovery contact hoặc kênh phục hồi.
- Thu hồi session/refresh family liên quan đến thiết bị mất.
- Thay đổi vai trò hoặc chính sách xác thực của tài nguyên.
- Phát hiện credential bị lộ hoặc hoạt động cần điều tra.

Không phải sự kiện nào cũng dẫn đến cùng phản ứng. Nếu session bị thu hồi hoặc account bị hold, có thể phải từ chối hoặc yêu cầu đăng nhập mới, thay vì chỉ yêu cầu nhập lại một factor trong session cũ.

Một yêu cầu password reset công khai chưa được xác minh chưa đủ để buộc mọi session đang hoạt động phải tái xác thực. Nếu làm vậy, người khác chỉ cần biết email là có thể gây gián đoạn liên tục.

### 2.4. Trigger theo bối cảnh và tín hiệu rủi ro

Các tín hiệu như thiết bị mới, thay đổi mạng, tốc độ thao tác bất thường hoặc lịch sử push bị từ chối có thể làm tăng yêu cầu xác thực.

Nhưng chất lượng tín hiệu khác nhau:

- IP và vị trí suy đoán có thể thay đổi vì mạng di động, VPN hoặc chuyển vùng.
- User-Agent, tên máy và browser fingerprint không phải bằng chứng mật mã về thiết bị.
- Cookie “đã tin cậy” có thể bị sao chép cùng session.
- Chứng minh kiểm soát một khóa thiết bị có giá trị khác với một chuỗi device ID do client gửi.

Vì vậy, chính sách nên dùng tín hiệu theo độ tin cậy, ngữ cảnh và tổ hợp phù hợp. Không kết luận chắc chắn bị chiếm đoạt chỉ từ một IP mới, cũng không bỏ trigger bắt buộc chỉ vì IP quen thuộc.

Với tín hiệu cho thấy xâm nhập nghiêm trọng, phản ứng có thể là thu hồi, hold hoặc chuyển xử lý sự cố. Yêu cầu thêm một OTP trên cùng thiết bị đang nghi bị kiểm soát có thể không giải quyết được vấn đề.

## 3. Trigger trong vòng đời account recovery

### 3.1. Trước thay đổi phương thức phục hồi

Khi người dùng vẫn xác thực được, cần trigger trước các thao tác làm thay đổi đường recovery: thêm kênh, thay recovery contact, xem/tạo recovery code hoặc đổi MFA.

Ví dụ, cookie phiên còn mở trên máy tính công cộng không nên đủ để tạo bộ recovery code mới. Nếu đủ, người có quyền dùng trình duyệt tạm thời có thể chiếm quyền phục hồi lâu dài.

Chính sách cần chọn bằng chứng tương xứng. Chỉ yêu cầu xác nhận email mới chứng minh kiểm soát kênh đích, chưa chứng minh người yêu cầu có quyền thay kênh của tài khoản.

### 3.2. Khi người dùng đã mất factor

Nếu trigger yêu cầu một authenticator mà người dùng không còn sử dụng được, cung cấp đường recovery được chính sách cho phép. Không tự bỏ trigger hoặc thay bằng câu hỏi cá nhân dễ tìm chỉ để luồng đi tiếp.

Cũng không tạo vòng lặp:

~~~text
Muốn khôi phục MFA -> phải dùng MFA đã mất
Không dùng được MFA -> quay về chính bước đó
~~~

Recovery có tiêu chí bằng chứng riêng. Một session `RECOVERY_ONLY` chỉ có các quyền được cấp cho quy trình đó; nó không phải session đã tái xác thực đủ cho mọi hành động nghiệp vụ.

### 3.3. Sau khi hoàn tất recovery

Trigger có thể yêu cầu đăng nhập/xác thực mới trước khi tiếp tục, hoặc yêu cầu độ mới cao hơn cho hành động nhạy cảm trong giai đoạn sau recovery.

Trong mọi trường hợp, phải kiểm tra trạng thái account hiện tại. Nếu còn thời gian hạn chế đổi kênh recovery, việc người dùng vừa dùng passkey mới không tự gỡ hạn chế đó.

Điểm cần tránh là dùng credential vừa được cấp trong recovery để chứng minh hồi tố rằng bước cấp quyền recovery ban đầu đã đúng. Nó chỉ chứng minh khả năng sử dụng credential mới; quyền gắn credential phải có căn cứ từ trước.

### 3.4. Không tự nâng độ tin cậy từ một dấu thời gian

Một trường `lastReauthAt` duy nhất dễ gây sai nếu mọi loại xác thực đều cập nhật nó.

Ví dụ:

~~~text
09:00  Người dùng hoàn thành mật khẩu và MFA.
10:30  Client refresh access token.
10:31  Người dùng muốn đổi email recovery.
~~~

Nếu action cần bằng chứng phù hợp trong 5 phút, thời điểm 10:30 không làm sự kiện MFA lúc 09:00 trở nên mới. Cần đánh giá lại dựa trên phương thức, thời điểm và trạng thái thật của sự kiện xác thực.

Tương tự, một lần nhập mật khẩu mới không được làm timestamp của bằng chứng chống phishing cũ trở nên hiện hành.

## 4. Kết quả quyết định trigger

### 4.1. Không chỉ trả một boolean

| Kết quả minh họa | Ý nghĩa | Hành động đang chờ |
| --- | --- | --- |
| `ALLOW_WITH_EXISTING_AUTH` | Bằng chứng hiện có vẫn đáp ứng policy | Có thể tiếp tục sau các kiểm tra quyền còn lại |
| `REQUIRE_REAUTH` | Cần bằng chứng mới hơn hoặc phù hợp hơn trong cùng mức yêu cầu | Chưa thực hiện action |
| `REQUIRE_STEP_UP` | Cần thuộc tính/mức xác thực mà bằng chứng hiện có chưa có | Chưa thực hiện action |
| `REQUIRE_LOGIN` | Không còn session hợp lệ để tiếp tục theo context cũ | Thiết lập context đăng nhập phù hợp |
| `RECOVERY_REQUIRED` | Không hoàn thành được phương thức yêu cầu, phải xét đường recovery | Không tự cho action đi qua |
| `DENY_OR_HOLD` | Quyền, trạng thái bảo mật hoặc giới hạn account không cho phép | Xác thực lại không tự giải quyết |
| `RETRY_OR_REVIEW` | Thiếu dữ kiện bắt buộc hoặc thành phần kiểm tra chưa khả dụng | Chưa cấp quyền cho action nhạy cảm |

`RECOVERY_REQUIRED` không được suy ra chỉ vì một credential chưa xuất hiện trong hộp chọn của trình duyệt. Có thể còn phương thức hợp lệ khác. Thông tin từ client giúp chọn đường hỗ trợ; server vẫn phải xác minh mọi bằng chứng.

### 4.2. Nội dung một quyết định

Một quyết định nên chứa hoặc tham chiếu tới:

- Account, tenant, session và client context liên quan.
- Action, tài nguyên đích và phiên bản nội dung sẽ thực hiện.
- Lý do trigger: bằng chứng quá cũ, chưa đạt profile, sự kiện bảo mật hoặc rủi ro.
- Profile xác thực yêu cầu, tuổi bằng chứng tối đa và các phương thức được phép.
- Security epoch/credential version cùng phiên bản chính sách.
- Thời hạn challenge, phạm vi dùng lại kết quả và cách xử lý khi thất bại.

Mã lý do chi tiết phục vụ audit và vận hành. Thông báo cho người dùng cần đủ để hiểu bước tiếp theo, nhưng không phải liệt kê mọi ngưỡng rủi ro nội bộ.

## 5. Thiết kế chính sách trigger

### 5.1. Profile xác thực cần có định nghĩa

Một profile có thể mô tả các thuộc tính cần có: phương thức được chấp nhận, user verification, chống phishing, mức bảo đảm và yêu cầu độ mới. Tên profile như `FRESH_MFA` chỉ là nhãn nội bộ; nó không tự chứng minh giao dịch đã đạt yêu cầu.

Không sắp xếp các giá trị `acr` bằng thứ tự chuỗi rồi chọn giá trị “lớn nhất”. Ý nghĩa và quan hệ giữa các profile cần được định nghĩa trong hợp đồng với verifier/IdP.

Một profile phải có khả năng chỉ rõ các phương án thay thế hợp lệ. Ví dụ, nhiều authenticator khác nhau có thể đáp ứng cùng yêu cầu. Không bắt người dùng thực hiện đồng thời mọi phương thức trong danh sách nếu chính sách thực chất cho phép chọn một trong các tổ hợp.

### 5.2. Mẫu cấu hình minh họa

~~~yaml
policyId: account-sensitive-actions
version: 4

actions:
  changeRecoveryChannel:
    requiredProfile: APPROVED_MFA
    maxAuthenticationAgeSeconds: 300
    bindToAction: true
    singleUseActionGrant: true

  regenerateRecoveryCodes:
    requiredProfile: APPROVED_MFA
    maxAuthenticationAgeSeconds: 300
    bindToAction: true
    singleUseActionGrant: true

  grantAdministrativeAccess:
    requiredProfile: PHISHING_RESISTANT
    maxAuthenticationAgeSeconds: 120
    bindToAction: true
    singleUseActionGrant: true

challenge:
  ttlSeconds: 180
  reuseEquivalentPendingChallenge: true
  allowSilentFallbackToWeakerMethod: false

postRecovery:
  enforceAccountRestrictionsBeforeChallenge: true
  acceptRefreshAsAuthentication: false
~~~

Trong ví dụ, action grant là quyền thực hiện hành động sau khi tái xác thực đạt yêu cầu, khác challenge dùng trong ceremony. Challenge 180 giây không có nghĩa người dùng được thực hiện hành động tùy ý trong 180 giây.

Profile `APPROVED_MFA` và `PHISHING_RESISTANT` phải được triển khai bởi một verifier và policy có tiêu chí cụ thể. Client không được tự chọn profile yếu hơn hoặc tự sửa `maxAuthenticationAgeSeconds`.

### 5.3. Kết hợp nhiều trigger

Nếu một request cùng chịu trigger theo action, thời gian và bối cảnh, cần tạo một yêu cầu tổng hợp. Thông thường, các ràng buộc bắt buộc cùng phải đạt; giới hạn độ cũ chặt hơn không bị thay bởi giới hạn rộng hơn.

Ví dụ, action cho phép bằng chứng không quá 5 phút, nhưng một sự kiện vừa xảy ra buộc xác thực lại sau sự kiện đó. Sự kiện xác thực cách đây 2 phút vẫn chưa đủ nếu nó xảy ra trước mốc cần kiểm tra lại.

Nếu hai chính sách tạo yêu cầu không thể đồng thời đáp ứng, trả kết quả cần xử lý chính sách hoặc hỗ trợ phù hợp. Không âm thầm bỏ một điều kiện để tìm được phương thức có thể chạy.

## 6. Luồng thực thi phía server

### 6.1. Chặn action trước khi phát challenge

~~~mermaid
flowchart TD
    A[Request thực hiện action] --> B[Nạp account, session, quyền và policy]
    B --> C{Có hold hoặc action không được phép?}
    C -->|Có| D[Từ chối hoặc chuyển xử lý bảo mật]
    C -->|Không| E{Session hợp lệ?}
    E -->|Không| F[Yêu cầu đăng nhập phù hợp]
    E -->|Có| G[Đánh giá trigger và bằng chứng hiện có]
    G --> H{Đáp ứng đầy đủ?}
    H -->|Có| I[Kiểm tra lại trạng thái rồi thực hiện action]
    H -->|Chưa| J{Có đường xác thực được phép?}
    J -->|Không| K[Recovery hoặc hỗ trợ theo policy]
    J -->|Có| L[Phát challenge gắn account và action]
    L --> M[Xác minh kết quả ceremony]
    M --> N{Đúng subject và đủ yêu cầu?}
    N -->|Không| O[Giữ action chưa thực hiện]
    N -->|Có| P[Cấp action grant hẹp]
    P --> Q[Kiểm tra quyền, trạng thái và dữ liệu action lần cuối]
    Q --> R[Tiêu thụ grant và commit action]
~~~

Trình duyệt có thể hiển thị trạng thái chờ, nhưng backend mới là nơi giữ action chưa được thực hiện. Không cập nhật email trước rồi mở hộp thoại “xác nhận lại” sau.

Những request không có tác động, như đọc trạng thái challenge đã được cấp quyền, có thể có chính sách riêng. Không làm mọi request nền tự động gửi push hay mở thêm ceremony.

### 6.2. Mã giả đánh giá trigger

Đoạn Java dưới minh họa cổng quyết định, không phải một thư viện xác thực hoàn chỉnh.

~~~java
TriggerDecision evaluateTrigger(TrustedRequestContext context) {
    Account account = accountFacts.current(context.accountId());
    Action action = actions.resolveAndNormalize(context);
    Session session = sessionFacts.verifiedSession(context);
    Instant now = clock.instant();

    if (!requiredFactsAvailable(account, action)) {
        return TriggerDecision.retryOrReview("REQUIRED_STATE_UNAVAILABLE");
    }
    if (account.hasSecurityHold()
            || !authorization.mayRequest(account, context, action)) {
        return TriggerDecision.denyOrHold("ACTION_NOT_ALLOWED");
    }
    if (!session.isValidAt(now)
            || session.securityEpoch() != account.securityEpoch()) {
        return TriggerDecision.requireLogin("SESSION_NOT_CURRENT");
    }

    Policy policy = policies.current(account, action);
    if (policy.blockedByAccountRestrictions(account, action)) {
        return TriggerDecision.denyOrHold("ACCOUNT_RESTRICTION");
    }

    RiskSnapshot risk = riskFacts.validatedFor(account, session, action, now);
    if (!risk.satisfiesAvailabilityRequirements(policy)) {
        return TriggerDecision.retryOrReview("RISK_STATE_UNAVAILABLE");
    }
    if (risk.requiresSecurityReview()) {
        return TriggerDecision.denyOrHold("SECURITY_REVIEW_REQUIRED");
    }

    AuthRequirement required = policy.combineRequirements(
        action, account.securityEvents(), risk
    );
    AuthEvidence existing = authenticationFacts.forSession(session);

    if (existing.satisfies(required, account, action, now)) {
        return TriggerDecision.allowWithExistingAuth(required);
    }
    if (!authenticators.hasPermittedRoute(account, required)) {
        return TriggerDecision.recoveryRequired("NO_PERMITTED_AUTH_ROUTE");
    }
    return required.needsStrongerEvidenceThan(existing)
        ? TriggerDecision.requireStepUp(required)
        : TriggerDecision.requireReauth(required);
}
~~~

`TrustedRequestContext` và các facts phải được xác minh ở server. IP qua proxy cần được xử lý theo cấu hình proxy tin cậy; role, tenant, epoch và kết quả MFA không lấy từ body tùy ý.

`existing.satisfies(...)` phải kiểm tra cả loại bằng chứng, độ mới, mốc sự kiện, account/session binding và phiên bản liên quan. Nó không chỉ kiểm tra `verifiedAt > now - maxAge`.

`hasPermittedRoute` nói rằng có một đường được policy chấp nhận, không khẳng định chắc chắn người dùng hiện cầm được authenticator. Nếu người dùng báo mất phương thức, cần đường recovery phù hợp; không sửa policy để coi factor yếu hơn là đạt.

Thiếu một nguồn risk không luôn đòi khóa toàn bộ tài khoản. Chính sách có thể cho phép các hành động ít nhạy cảm tiếp tục, trong khi giữ action cần dữ kiện đó ở trạng thái chưa được phép.

### 6.3. Challenge phải thuộc đúng ceremony

Khi tạo challenge, server cần khóa vào:

- Account và tenant đang được kiểm tra.
- Session hoặc client context hợp lệ.
- Mục đích tái xác thực và profile yêu cầu.
- Action/tài nguyên đích nếu policy dùng ràng buộc theo action.
- Security epoch, credential version hoặc các mốc trạng thái có liên quan.
- Challenge ngẫu nhiên, thời hạn, số lần thử và trạng thái tiêu thụ.

Không nhận một challenge do client tự chọn, một assertion cũ hoặc một cờ `success=true` rồi coi là kết quả ceremony. Dùng thư viện xác thực phù hợp để kiểm tra các thuộc tính của giao thức.

Với tái xác thực bằng passkey cho hành động nhạy cảm, giữ nguyên tài khoản đích và chỉ chấp nhận credential thuộc tài khoản đó. Nếu người dùng muốn đổi tài khoản, bắt đầu luồng phù hợp thay vì dùng kết quả của B để mở action của A. [passkeys.dev — Reauthentication](https://passkeys.dev/docs/use-cases/reauth/)

Không hạ yêu cầu user verification, MFA hay chống phishing chỉ vì một ceremony bị hủy hoặc timeout. Thất bại vận chuyển và không đạt chính sách là những kết quả cần xử lý riêng.

## 7. Kết quả tái xác thực mở quyền đến đâu?

### 7.1. Hai mô hình dùng kết quả

| Mô hình | Cách dùng | Điều cần kiểm soát |
| --- | --- | --- |
| Cửa sổ xác thực theo profile | Dùng sự kiện mới cho một nhóm action trong thời hạn | Nhóm action, profile, mốc sự kiện và giới hạn account |
| Action grant một lần | Cấp quyền cho một action/tài nguyên cụ thể | Binding dữ liệu, thời hạn, replay và tính nguyên tử |

Cửa sổ chung giúp giảm số lần nhắc lại cho các hành động tương đương. Action grant thích hợp khi cần ràng buộc chặt với thay đổi cụ thể, chẳng hạn thay một địa chỉ recovery đã được chuẩn bị.

Không dùng một cờ toàn session như `reauthenticated=true` mà không có profile, thời gian và phạm vi. Khi cờ đó được mọi API tin cậy, một ceremony yếu có thể vô tình mở toàn bộ thao tác nhạy cảm.

### 7.2. Ràng buộc với nội dung action

Giả sử người dùng đang tái xác thực để đổi email recovery từ địa chỉ cũ sang `new@example.test`. Nếu client sửa đích thành địa chỉ khác sau khi ceremony thành công, action grant cũ không được bao phủ thay đổi đó.

Một action grant có thể gắn với digest của nội dung action đã được server chuẩn hóa, bao gồm loại action, account, tenant, tài nguyên đích, các trường có tác động và phiên bản đối tượng.

Digest chỉ là một phần của kiểm soát binding. Nội dung phải được server xác định và chuẩn hóa nhất quán; không tin vào `actionHash` client tự tính hoặc coi hash là chữ ký của người dùng. Với passkey/WebAuthn thông thường, một assertion hợp lệ cũng không tự bảo đảm người dùng đã được hiển thị và xác nhận đầy đủ nội dung giao dịch.

Nếu nội dung thay đổi, hủy grant hoặc đánh giá lại theo chính sách. Không cho client dùng một grant hợp lệ để chọn bất kỳ thao tác mới nào có cùng nhãn “cài đặt bảo mật”.

### 7.3. Kiểm tra lại trước commit

Giữa thời điểm tạo trigger và thời điểm thực hiện action, role, epoch, credential hoặc trạng thái hold có thể thay đổi. Vì vậy, phải kiểm tra lại ở bước cuối.

Trong mô hình một cơ sở dữ liệu, có thể dùng giao dịch để:

1. Khóa hoặc kiểm tra phiên bản account/action/grant phù hợp.
2. Kiểm tra grant còn hiệu lực, đúng subject, session context và nội dung action.
3. Kiểm tra quyền hiện tại và các điều kiện bảo mật mới.
4. Tiêu thụ grant và thực hiện thay đổi cùng nhau.
5. Ghi audit/outbox cần thiết.

Nếu action và grant nằm ở nhiều dịch vụ, cần giao thức điều phối hoặc cơ chế idempotency/so sánh phiên bản tương ứng. Không giả định kiểm tra ở gateway vài giây trước đã bảo vệ được mọi lần commit ở downstream.

Một action retry không được tạo nhiều API key hoặc thay đổi hai lần ngoài dự kiến. Mã idempotency cần gắn với chủ thể và nội dung action, nhưng bản thân việc biết mã đó chưa đủ để có quyền nhận bí mật hoặc thực hiện lại thao tác.

### 7.4. Quản lý session sau tái xác thực

Nếu kết quả làm thay đổi mức quyền hoặc context xác thực của session, dùng cơ chế framework phù hợp để đổi session ID/token và vô hiệu context cũ theo chính sách. Không di chuyển các cờ quyền chưa được xác minh sang session mới.

Việc xoay token không tự gỡ security hold, không tự đặt lại lịch sử recovery và không cho refresh family cũ nhận mức tin cậy mới. Context mới phải mô tả đúng sự kiện xác thực thực tế.

## 8. Trigger khi dùng SSO và OAuth

### 8.1. Token mới chưa chắc chứa sự kiện xác thực mới

RP có thể yêu cầu người dùng “đăng nhập lại”, nhưng IdP vẫn giữ SSO session và trả token mà không yêu cầu tương tác xác thực mới. Vì thế, thời điểm nhận token hoặc `iat` mới chưa chứng minh trigger về độ mới đã được đáp ứng.

Trong OpenID Connect, `max_age` đặt giới hạn thời gian từ lần xác thực, và khi tham số này được dùng, ID Token phải có `auth_time`. `prompt=login` yêu cầu IdP tái xác thực, nhưng RP vẫn phải xác minh phản hồi và điều kiện cần thiết, thay vì chỉ tin rằng đã gửi tham số. [OpenID Connect Core 1.0 — Authentication Request](https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest)

RP cần diễn giải profile/`acr` theo hợp đồng với IdP và kiểm tra giá trị thực sự được đáp ứng. Không coi việc gửi yêu cầu profile mạnh hơn là bằng chứng IdP đã thực hiện đúng profile đó.

Nếu kết quả không đủ mới hoặc không đạt profile, không mở action. Trả trạng thái rõ ràng để người dùng chọn phương thức được phép hoặc chuyển hỗ trợ; tránh vòng redirect lặp vô hạn.

### 8.2. Resource server có thể phát tín hiệu step-up

Với hệ thống triển khai RFC 9470, API có thể dùng lỗi `insufficient_user_authentication` trong Bearer challenge để báo bằng chứng gắn với access token chưa đủ. Tham số `max_age` diễn đạt độ mới, còn `acr_values` diễn đạt context xác thực cần có. [RFC 9470 — Authentication Requirements Challenge](https://www.rfc-editor.org/rfc/rfc9470.html#section-3)

Ví dụ minh họa:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="insufficient_user_authentication",
  max_age="300",
  acr_values="urn:example:auth:phishing-resistant"
Cache-Control: no-store
~~~

Giá trị `urn:example:auth:phishing-resistant` là profile giả định trong hệ thống ví dụ, không phải giá trị chuẩn phổ quát.

Client dùng challenge để đi qua authorization flow phù hợp, rồi gọi lại API bằng token đạt yêu cầu. Resource server vẫn phải kiểm tra thông tin xác thực được issuer cung cấp qua access token hoặc introspection tương ứng. Một ID Token không tự trở thành access token cho API.

Nếu client chưa hỗ trợ cơ chế này, cần thiết kế phản hồi và đường tiếp tục tương thích. Không đổi mọi lỗi phân quyền thành lỗi step-up: thiếu quyền truy cập hoặc account bị hold không được giải quyết chỉ bằng xác thực mạnh hơn.

### 8.3. Giữ đúng account và context liên kết

Trong tái xác thực cho action của A, phản hồi SSO đăng nhập bằng B không được coi là bằng chứng của A. Ràng buộc issuer, subject, tenant, client và context theo giao thức; không chỉ so sánh tên hiển thị hoặc email.

Các kiểm tra chữ ký, audience, nonce/state và redirect thuộc giao thức phải được thư viện/tích hợp thực hiện đầy đủ. Trigger là chính sách bổ sung cho xác thực giao thức, không thay thế các kiểm tra đó.

## 9. Tránh vòng lặp và MFA fatigue

### 9.1. Một tín hiệu không được liên tục tạo mốc mới

Giả sử session bị gắn cờ “thiết bị mới” lúc 10:00. Policy yêu cầu một lần xác thực phù hợp sau sự kiện này. Nếu mỗi request lại đặt `reauthRequiredAfter = now`, người dùng sẽ không bao giờ theo kịp mốc yêu cầu.

Đúng hơn, lưu tham chiếu và thời điểm sự kiện phát sinh. Sau khi người dùng cung cấp bằng chứng đạt yêu cầu cho sự kiện đó, các request tương đương được đánh giá theo mốc ổn định, trừ khi có sự kiện mới hoặc cửa sổ bằng chứng hết hạn.

Không xóa mọi tín hiệu rủi ro sau một lần thành công. Cần ghi rõ trigger nào đã được đáp ứng, trong profile nào và phạm vi nào. Một sự kiện chiếm đoạt cần hold không trở thành an toàn chỉ nhờ hoàn tất một OTP.

### 9.2. Gộp các challenge tương đương

Khi nhiều tab cùng thực hiện một action, backend có thể tái sử dụng challenge pending tương đương trong cùng context, với điều kiện nó còn hiệu lực và cùng account, action, profile, epoch.

Không gộp ceremony của hai account khác nhau hoặc hai nội dung action khác nhau. Một challenge thành công cho đổi email không tự xác nhận yêu cầu tạo API key từ tab khác.

Giao diện nên giữ một tiến trình xác thực rõ ràng, có trạng thái đang chờ, hủy và hết hạn. Không phát push lại ở mọi lần polling hoặc tự lặp vô hạn sau khi người dùng từ chối.

### 9.3. Hạn mức theo nhiều chiều

Kiểm soát số lần phát challenge, số lần thử, push gửi đi và các yêu cầu đồng thời. Cân nhắc account, session/client context, nguồn yêu cầu và mức sử dụng toàn dịch vụ.

Hạn mức chỉ theo IP dễ bị né tránh và có thể chặn nhầm nhiều người sau cùng một mạng. Hạn mức chỉ theo account có thể bị lạm dụng để làm chủ tài khoản không dùng được hệ thống. Cần phân biệt giữ action nhạy cảm, tạm ngừng gửi challenge và khóa toàn bộ tài khoản.

Sau nhiều lần push bị từ chối hoặc bằng chứng sai, có thể yêu cầu một đường được phép khác hoặc chuyển xử lý rủi ro. Không hạ phương thức xuống SMS/email chỉ vì phương thức mạnh hơn chưa hoàn thành.

### 9.4. Thiết kế trải nghiệm theo lý do thực tế

Thông điệp có thể là:

> Để đổi email khôi phục, hãy xác thực lại tài khoản đang hiển thị. Thay đổi này chưa được thực hiện.

Nếu trigger do hết cửa sổ độ mới, giải thích rằng cần xác nhận lại trước thao tác nhạy cảm. Nếu account bị hold, dùng thông báo phù hợp với đường xử lý; không hiển thị nút “xác thực lại để bỏ chặn” khi policy không cho phép.

Cho phép hủy mà không thực hiện action. Với dữ liệu nhập dở, có thể giữ bản nháp an toàn để giảm gián đoạn, nhưng phải kiểm tra lại nội dung trước khi dùng grant. Không lưu credential hoặc bí mật ceremony vào bản nháp.

Cookie thường được chia sẻ giữa các tab trong cùng browser profile. Không hứa một lần tái xác thực bằng cookie chỉ ảnh hưởng đúng tab đang mở. Nếu cần cách ly quyền theo action, dùng binding ở server thay vì dựa vào tab.

### 9.5. Khi verifier hoặc IdP gặp lỗi

Một timeout không phải bằng chứng người dùng sai và cũng không phải lý do cho action đi qua. Với action cần kiểm tra bắt buộc, giữ nguyên trạng thái chưa thực hiện và cho retry có kiểm soát.

Nếu có phương thức dự phòng đáp ứng cùng chính sách, có thể cho người dùng chọn. Nếu chỉ còn phương thức yếu hơn, cần quyết định chính sách riêng hoặc recovery; không tự coi hai phương thức là tương đương vì cả hai đều có ô nhập mã.

## 10. Audit và dữ liệu để đánh giá trigger

### 10.1. Ghi quyết định, không ghi bí mật

Một chuỗi sự kiện có thể gồm:

~~~text
SENSITIVE_ACTION_REQUESTED
REAUTH_TRIGGER_EVALUATED
REAUTH_CHALLENGE_CREATED hoặc EQUIVALENT_CHALLENGE_REUSED
REAUTH_VERIFICATION_SUCCEEDED hoặc REAUTH_VERIFICATION_FAILED
ACTION_GRANT_ISSUED
ACTION_COMMITTED hoặc ACTION_REJECTED_AFTER_RECHECK
~~~

Audit cần liên kết account/tenant, session reference, action reference, policy version, trigger reason, profile yêu cầu, authentication event và kết quả cuối.

Không ghi mật khẩu, raw recovery code, seed TOTP, session cookie hoặc token dùng được. Nếu cần tương quan, dùng tham chiếu hoặc cách biểu diễn không thể trực tiếp dùng để xác thực.

Thành công ở `REAUTH_VERIFICATION_SUCCEEDED` chưa chứng minh action đã commit. Ngược lại, một action bị từ chối do quyền thay đổi không có nghĩa ceremony xác thực trước đó sai.

### 10.2. Những chỉ số hữu ích

| Chỉ số | Câu hỏi vận hành |
| --- | --- |
| Tỷ lệ trigger theo action và lý do | Có action nhạy cảm nào thiếu kiểm soát hoặc action ít rủi ro bị nhắc quá nhiều không? |
| Nhiều trigger liên tiếp cho cùng sự kiện | Mốc yêu cầu có bị đặt lại ở mỗi request không? |
| Challenge được tạo nhưng không hoàn thành | Có lỗi giao diện, phương thức không phù hợp hoặc MFA fatigue không? |
| Xác thực thành công nhưng action bị chặn | Quyền/trạng thái thay đổi hay binding action bị sai? |
| Action gọi trực tiếp không có bằng chứng yêu cầu | Có endpoint bỏ sót cổng trigger không? |
| Nhiều vòng SSO nhưng profile không đạt | IdP/client có hỗ trợ yêu cầu và kiểm tra phản hồi đúng không? |
| Nhiều fallback sau lỗi provider | Có đường hạ cấp xác thực ngoài chính sách không? |

Thiết bị, mạng và tín hiệu hành vi có thể chứa dữ liệu cá nhân. Chỉ thu thập mức cần thiết cho quyết định, hạn chế quyền truy cập và đặt thời gian lưu phù hợp; không mở rộng thu thập chỉ để làm mô hình rủi ro phức tạp hơn.

## 11. Các tình huống minh họa

### 11.1. Session còn sống nhưng bằng chứng đã cũ

Lan đăng nhập bằng phương thức đạt policy lúc 09:00. Đến 10:00, Lan vẫn đọc nội dung bình thường và muốn đổi email recovery.

Policy của action yêu cầu bằng chứng không quá 5 phút. Backend trả `REQUIRE_REAUTH`, giữ thay đổi chưa thực hiện và phát challenge đúng tài khoản. Một request refresh token lúc 09:59 không thay đổi kết quả.

Sau xác thực phù hợp, Lan nhận action grant cho đúng địa chỉ mới đã chuẩn bị. Backend kiểm tra lại rồi mới commit.

Bài học: thời gian session hoạt động và tuổi bằng chứng cho action là hai khái niệm riêng.

### 11.2. Bằng chứng mới nhưng không đạt thuộc tính yêu cầu

Minh vừa hoàn thành một phương thức xác thực được phép cho nội dung thông thường. Minh muốn thêm một quản trị viên, trong khi action yêu cầu phương thức chống phishing.

Backend trả `REQUIRE_STEP_UP` dù sự kiện vừa xảy ra. Nó không chỉ so sánh timestamp rồi cho phép. Nếu tài khoản chưa có đường đáp ứng policy, Minh phải đi qua quy trình enrollment/recovery hoặc hỗ trợ đủ điều kiện, không được tự động dùng phương thức yếu hơn.

Bài học: mới hơn không đồng nghĩa mạnh hơn; một điều kiện không thay thế điều kiện kia.

### 11.3. Mất factor trong lúc cần tái xác thực

Hà còn cookie đăng nhập trên máy tính nhưng mất điện thoại chứa MFA. Hà muốn thay MFA bằng thiết bị mới.

Cookie giúp xác định context, nhưng không tự đủ để cấp factor thay thế. Hệ thống cho Hà lựa chọn phương thức còn dùng được hoặc đường recovery được chính sách cho phép. Nó không hỏi lại factor đã mất mãi, cũng không tắt kiểm tra chỉ vì Hà còn session.

Bài học: cần đường thoát hợp lệ sang recovery, không cần một lối bỏ qua trigger.

### 11.4. Action bị sửa sau ceremony

Quân tái xác thực để đổi kênh recovery sang địa chỉ X. Trước khi gửi bước hoàn tất, request bị đổi thành địa chỉ Y.

Server phát hiện grant không khớp nội dung chuẩn hóa và từ chối. Nếu muốn thực hiện Y, cần đánh giá hoặc cấp quyền tương ứng theo policy. Một ceremony thành công không mở quyền đổi mọi địa chỉ trong tài khoản.

Bài học: kết quả xác thực phải được dùng đúng mục đích và phạm vi.

### 11.5. Tín hiệu mạng gây nhắc lặp

An dùng mạng di động nên IP thay đổi thường xuyên. Một chính sách sơ sài yêu cầu tái xác thực ở mọi thay đổi IP và liên tục gửi push.

Thiết kế phù hợp đánh giá chất lượng tín hiệu, nhóm những sự kiện tương đương và ghi nhận yêu cầu đã được đáp ứng trong context xác định. Sự kiện mới có giá trị bảo mật vẫn được xét, nhưng một tín hiệu nhiễu không tự tạo vô hạn challenge.

Bài học: trigger cần hiệu lực rõ ràng; quá nhiều nhắc xác thực có thể làm người dùng chấp nhận yêu cầu ngoài ý muốn.

### 11.6. Đã tái xác thực nhưng account vừa bị hold

Một challenge hoàn tất hợp lệ. Trước lúc commit hành động, tài khoản bị đặt security hold bởi một quyết định bảo mật có thẩm quyền.

Kiểm tra cuối từ chối action dù action grant chưa hết hạn. Nếu hệ thống chỉ kiểm tra kết quả ceremony và TTL, grant cũ có thể vượt qua trạng thái bảo mật mới.

Bài học: điều kiện thực hiện action phải còn đúng tại thời điểm có tác động.

## 12. Các nguyên tắc cần giữ

- Trigger mô tả action đang bị giữ và bằng chứng cần bổ sung, không chỉ mở một màn hình.
- Chính sách phân biệt tái xác thực, step-up, đăng nhập mới, recovery và từ chối do trạng thái bảo mật.
- Tuổi bằng chứng được tính từ sự kiện phù hợp, không từ refresh token, heartbeat hoặc thời điểm phát token.
- Tín hiệu rủi ro không bù được quyền thiếu hoặc điều kiện chặn bắt buộc.
- Mốc sự kiện cần tái xác thực là mốc ổn định, không tự cập nhật thành hiện tại ở mọi request.
- Context và bằng chứng luôn thuộc đúng account, tenant, session và mục đích.
- Kết quả tái xác thực chỉ có hiệu lực trong profile, thời hạn và phạm vi được cấp.
- Thay đổi nội dung action hoặc trạng thái bảo mật có thể làm grant cũ không còn sử dụng được.
- Mất factor dẫn tới đường recovery đủ căn cứ; lỗi provider không dẫn tới hạ cấp âm thầm.
- Server kiểm tra ở mọi endpoint liên quan và kiểm tra lại trước commit.
- Audit tách thành công của ceremony khỏi kết quả thực hiện action.

Một reauthentication trigger hiệu quả giúp dịch vụ yêu cầu thêm bằng chứng đúng lúc, cho đúng hành động và với phạm vi rõ ràng. Trong account recovery, sự chính xác này bảo vệ các đường khôi phục tương lai, ngăn session bị chiếm dụng sửa cơ chế xác thực và giữ quyền truy cập nhất quán với trạng thái bảo mật hiện tại.
