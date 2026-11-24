# Quản lý cấu hình khôi phục tài khoản

Trong chương **Deployment Operations**, “Recovery configuration management” là cách quản lý những quyết định vận hành chi phối luồng khôi phục tài khoản: ai được bắt đầu, bằng chứng nào được chấp nhận, token sống bao lâu, khi nào phải chờ, ai được thay đổi policy và các node áp dụng thay đổi đó thế nào.

Đối với hệ thống `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, một thay đổi cấu hình có thể thay đổi đường đi đến quyền kiểm soát tài khoản. Tăng số lần thử mã, cho phép một kênh mới hoặc bỏ bước thu hồi session có thể tạo ra mức bảo vệ khác dù mã nguồn không đổi. Vì vậy, cấu hình recovery phải được quản lý như một phần của ranh giới xác thực.

Bài học này tập trung vào quản lý cấu hình cho tình huống người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Mục tiêu là triển khai và điều chỉnh policy có kiểm soát, giữ được khả năng vận hành nhưng không biến sự cố cấu hình thành đường tắt chiếm đoạt tài khoản.

## 1. Cấu hình recovery quyết định điều gì?

Một luồng đơn giản có thể được biểu diễn như sau:

```text
Tiếp nhận yêu cầu
    → đánh giá rủi ro
    → chọn phương thức khôi phục được phép
    → phát challenge
    → xác minh bằng chứng
    → chờ hoặc phê duyệt nếu policy yêu cầu
    → thay thông tin xác thực
    → vô hiệu hóa quyền truy cập cũ theo policy
    → thông báo và ghi nhận sự kiện
```

Cấu hình có thể tác động đến mọi mũi tên. Ví dụ, hai môi trường chạy cùng một bản ứng dụng nhưng một môi trường chỉ kiểm tra email, môi trường kia yêu cầu thêm bằng chứng độc lập trước khi gỡ MFA. Hai môi trường đó không còn cung cấp cùng mức bảo đảm khôi phục.

Để nhận diện mức độ ảnh hưởng, phân loại cấu hình theo chức năng:

| Nhóm | Ví dụ | Rủi ro nếu quản lý sai |
|---|---|---|
| Điều kiện đủ | Loại tài khoản được recovery, phương thức được phép | Mở phương thức yếu cho tài khoản đặc quyền |
| Vòng đời challenge | TTL, số lần thử, thời gian gửi lại | Mở rộng cửa sổ đánh cắp hoặc đoán mã |
| Đánh giá rủi ro | Điều kiện chuyển sang review, cooldown | Bỏ qua kiểm tra khi có dấu hiệu tấn công |
| Thay đổi credential | Có được reset mật khẩu, gỡ MFA hay đăng ký passkey mới | Một bằng chứng yếu cấp quyền thay nhiều yếu tố |
| Hậu khôi phục | Thu hồi session, refresh token, yêu cầu đăng nhập lại | Kẻ đang giữ session cũ tiếp tục truy cập |
| Hạ tầng | Provider gửi tin, timeout, retry, endpoint | Gửi trùng, mất thông báo, truy cập đích không tin cậy |
| Secret và khóa | Tham chiếu khóa MAC, thông tin xác thực provider | Lộ khả năng tạo hoặc kiểm tra bằng chứng |
| Vận hành | Tạm dừng phát challenge, đóng kênh, chuyển review | Nút khẩn cấp vô tình trở thành chế độ bỏ xác minh |

Các giá trị như số lần thử và TTL là tham số của policy; chúng không tự quyết định mức an toàn. Cùng TTL mười phút nhưng token dài ngẫu nhiên và mã số ngắn có mô hình tấn công khác nhau. Cần xét độ mạnh bằng chứng, giới hạn tổng số yêu cầu, điều kiện hoàn tất và tác động sau recovery.

## 2. Tách bốn loại dữ liệu thường bị trộn lẫn

### 2.1. Policy có thể kiểm toán

Policy mô tả hành vi được phép: kênh recovery, thời hạn, yêu cầu review, ràng buộc session. Nên có schema, phiên bản, người phê duyệt và dấu vết thay đổi.

### 2.2. Secret và khóa mật mã

Khóa dùng để bảo vệ token, mật khẩu provider và thông tin xác thực dịch vụ không phải policy công khai. Policy có thể chứa **tham chiếu** đến secret, còn giá trị secret được lấy qua cơ chế phân quyền riêng.

Ví dụ, `activeKeyRef: recovery/token-mac/current` là một định danh tham chiếu. Nó không phải khóa thật và không nên bị hiểu là cú pháp tự động của một framework cụ thể.

### 2.3. Trạng thái của từng lần recovery

`challengeId`, `issuedAt`, `expiresAt`, số lần đã thử, trạng thái sử dụng, bằng chứng đã xác minh và yêu cầu thu hồi session là dữ liệu nghiệp vụ. Chúng phải được lưu trong hệ thống trạng thái phù hợp, không được nhét vào file cấu hình hoặc thay bằng feature flag.

### 2.4. Kết quả đánh giá rủi ro

Điểm rủi ro của một yêu cầu là kết quả xử lý dữ liệu tại thời điểm ra quyết định. Ngưỡng và quy tắc diễn giải thuộc policy, nhưng điểm của từng người dùng không phải cấu hình tĩnh. Ghi lại những yếu tố cần thiết để giải thích quyết định, đồng thời hạn chế dữ liệu nhận dạng và dữ liệu thiết bị.

Sự phân tách này giúp trả lời chính xác: “Ai đã đổi policy?” khác “Ai đã dùng challenge?” và khác “Ai đã truy cập khóa?”.

## 3. Chọn nguồn cấu hình chuẩn và thứ tự ưu tiên rõ ràng

Một ứng dụng thường nhận cấu hình từ mặc định trong code, file đóng gói, biến môi trường, hệ thống cấu hình tập trung và override theo tenant. Nếu không quy định thứ tự, cùng một khóa có thể mang ý nghĩa khác nhau ở các node.

Một mô hình có thể áp dụng là:

```text
Giới hạn an toàn do hệ thống quy định
    + policy của môi trường đã được phê duyệt
    + override theo tenant được phép
    + trạng thái ứng phó khẩn cấp
    → biên dịch thành effective policy bất biến
```

Dấu `+` ở đây là phép kết hợp có kiểm tra, không phải ghi đè tự do. Cần quy định cụ thể cho từng khóa:

- Kênh được phép có thể là giao của tập kênh nền và tập kênh tenant yêu cầu.
- Số lần thử của tenant không được vượt trần hệ thống.
- Yêu cầu phê duyệt bổ sung có thể được thêm, nhưng không được bỏ nếu policy nền bắt buộc.
- Cấu hình khẩn cấp có thể dừng phát challenge hoặc chuyển review; nó không được tự tạo kết quả xác minh thành công.

Không có một toán tử “chọn giá trị nghiêm hơn” áp dụng đúng cho mọi khóa. TTL ngắn hơn có thể tăng nguy cơ người dùng không hoàn tất; cooldown dài hơn có thể tăng nguy cơ gây từ chối dịch vụ; giảm loại bằng chứng được chấp nhận có thể loại bỏ đường recovery hợp lệ. Các khóa liên quan phải được đánh giá như một policy hoàn chỉnh.

### 3.1. Không để biến môi trường vô tình thắng policy đã ký duyệt

Nếu hệ thống cho phép biến môi trường ghi đè mọi khóa, một biến còn sót từ lần debug có thể vô hiệu hóa thay đổi chính thức. Với khóa nhạy cảm, chọn một nguồn chuẩn và giới hạn rõ nguồn nào được cung cấp khóa đó. Khi hai nguồn cùng khai báo trái phép, từ chối cấu hình hoặc báo lỗi theo contract; đừng âm thầm chọn nguồn thắng.

### 3.2. Tách biệt môi trường bằng quyền truy cập

Tên file `production.yml` không đủ để bảo vệ production. Quyền đọc secret, namespace cấu hình, tài khoản dịch vụ và địa chỉ provider cần tương ứng đúng môi trường. Môi trường thử nghiệm không được đọc khóa production hoặc gửi thông báo recovery thật cho người dùng ngoài phạm vi cho phép.

Môi trường thử nghiệm có thể dùng đồng hồ điều khiển được hoặc provider giả lập. Những cơ chế đó cần bị ràng buộc bởi cấu hình triển khai và quyền riêng, không chỉ bởi một tham số từ HTTP request.

## 4. Thiết kế schema và giá trị mặc định có chủ đích

Ví dụ dưới đây minh họa một **schema riêng của ứng dụng**, không phải file có thể đưa nguyên vào bất kỳ framework nào. Các con số chỉ phục vụ diễn giải, phải được đánh giá theo mô hình rủi ro và nhu cầu vận hành thực tế.

```yaml
recovery:
  schemaVersion: 1
  revision: 184
  securityEpoch: 12
  environment: production
  enabled: true

  scope:
    tenantPolicyMode: bounded-overrides

  methods:
    passwordReset:
      enabled: true
      allowedChannels:
        - verified-email
      requireAdditionalReviewForHighRisk: true
    mfaRecovery:
      enabled: true
      requireIndependentEvidence: true
      requireManualReviewWhenEvidenceInsufficient: true
    passkeyRecovery:
      enabled: true
      requireSeparateEnrollmentAuthorization: true

  challengeProfiles:
    emailLink:
      ttl: PT10M
      maxVerificationAttempts: 5
      resendCooldown: PT1M

  limits:
    accountIssueLimit:
      maxRequests: 3
      window: PT15M
    accountVerifyLimit:
      maxRequests: 10
      window: PT15M

  completion:
    requireFreshAuthorization: true
    invalidateOtherRecoveryChallenges: true
    sessionRevocationRequired: true
    autoLoginAfterRecovery: false

  routing:
    publicRecoveryBaseUrl: https://accounts.example.invalid/recovery
    allowedHosts:
      - accounts.example.invalid
    allowArbitraryReturnUrl: false

  crypto:
    activeKeyRef: recovery/token-mac/current
    verificationKeySetRef: recovery/token-mac/accepted

  operations:
    issueNewChallenges: true
    allowExistingChallengeVerification: true
    providerTimeout: PT3S
    providerMaxAttempts: 2
```

Ý nghĩa cần được định nghĩa rõ:

- `schemaVersion` là phiên bản cấu trúc dữ liệu mà ứng dụng hiểu.
- `revision` là số lần phát hành policy, tăng khi có bản phát hành mới, kể cả bản khôi phục các giá trị cũ.
- `securityEpoch` là mốc do control plane tin cậy quản lý để loại bỏ policy hoặc bằng chứng thuộc thế hệ không còn được chấp nhận.
- `enabled` kiểm soát khả năng dùng chức năng theo contract; không đồng nghĩa mọi nhánh được phép bỏ kiểm tra.
- `requireFreshAuthorization` yêu cầu kiểm tra quyền hoàn tất ở thời điểm commit, với định nghĩa cụ thể về bằng chứng, thời hạn và hành động được cấp quyền.
- `sessionRevocationRequired` mô tả một điều kiện bảo mật của hậu khôi phục, không phải lệnh “cố gắng gửi event rồi coi như đã thu hồi”.

`allowExistingChallengeVerification: true` chỉ cho phép đi vào bước kiểm tra challenge cũ. Nó không được ghi đè điều kiện hết hạn, sử dụng một lần, epoch bị thu hồi hoặc yêu cầu bằng chứng hiện hành.

### 4.1. Không dùng một profile cho mọi loại artifact

Link email ngắn hạn, mã gửi qua thiết bị, recovery code dự phòng và yêu cầu support đang chờ review có vòng đời khác nhau. Tránh dùng một khóa `tokenTtl` chung cho tất cả.

Recovery code dự phòng có thể tồn tại lâu và được thiết kế khác challenge gửi theo yêu cầu. Dù thời hạn khác nhau, mỗi loại vẫn cần contract về entropy, lưu trữ, sử dụng một lần, thu hồi và cấp lại. Việc thay profile phải chỉ rõ artifact nào chịu tác động.

### 4.2. Giá trị thiếu và giá trị rỗng không giống nhau

Một danh sách kênh rỗng có thể nghĩa là đóng chức năng; danh sách bị thiếu có thể là lỗi schema. Không nên mặc định cả hai thành “cho phép mọi kênh”. Tương tự, TTL thiếu không được biến thành không hết hạn, số lần thử bằng không không được hiểu ngầm thành vô hạn.

Với khóa bảo mật bắt buộc, thiếu giá trị phải dẫn đến lỗi cấu hình hoặc trạng thái đóng đúng phạm vi. Với khóa thuần trình bày như tên template thông báo, có thể có mặc định an toàn đã được kiểm soát.

### 4.3. Quy định đơn vị và biên

Dùng biểu diễn thời gian không mơ hồ và parser nhất quán. Khi chọn chuỗi duration như `PT10M`, phải xác định ứng dụng có chấp nhận số lẻ hay giá trị âm không. Khi dùng số nguyên, tên khóa nên thể hiện đơn vị và kiểm tra tràn số khi chuyển đổi.

Giới hạn kỹ thuật và giới hạn policy nên tách rõ: parser có thể đọc một duration rất lớn nhưng policy không nhất thiết cho phép TTL đó. Biên phải có tài liệu và thuộc cùng vòng xét duyệt với policy.

## 5. Validation phải kiểm tra cả quan hệ giữa các khóa

Một file parse thành công vẫn có thể không sử dụng được. Nên có ít nhất bốn lớp kiểm tra:

| Lớp | Câu hỏi cần trả lời | Ví dụ lỗi |
|---|---|---|
| Cấu trúc | Ứng dụng có hiểu đúng schema không? | Sai tên khóa, khóa trùng, sai kiểu dữ liệu |
| Giá trị | Giá trị có nằm trong biên cho phép không? | TTL âm, retry không giới hạn |
| Quan hệ | Các trường có tạo thành policy hợp lệ không? | Bắt review nhưng không có đường chuyển review khả dụng |
| Khả năng thực thi | Hệ thống có quyền và tài nguyên để thực hiện không? | Không truy cập được khóa cần thiết, backend thu hồi session không đáp ứng |

Với các khóa lạ hoặc bị viết sai, nên từ chối thay vì bỏ qua âm thầm. Nếu cần hỗ trợ nhiều phiên bản, danh sách khóa được hỗ trợ và cách hạ cấp phải được xác định rõ; ứng dụng cũ không được tự coi yêu cầu bảo mật mới là tùy chọn.

Một số bất biến đáng kiểm tra:

1. Kênh được bật phải thuộc tập kênh hệ thống hỗ trợ và có cơ chế chứng minh quyền sở hữu tương ứng.
2. TTL, giới hạn thử và cooldown của từng profile phải nằm trong biên đã phê duyệt.
3. Hành động gỡ MFA hoặc đăng ký credential mới phải có điều kiện cấp quyền riêng, không suy ra chỉ từ quyền yêu cầu reset mật khẩu.
4. Đường dẫn recovery phải thuộc origin đã cấu hình; không xây URL từ `Host` hoặc URL callback tùy ý của request.
5. Nếu policy yêu cầu vô hiệu hóa session, phải có cơ chế thực thi và trạng thái lỗi được định nghĩa trước khi hoàn tất.
6. Retry gửi tin không được tự tạo challenge mới ở mỗi lần thử của provider.
7. Tham chiếu khóa đang dùng và tập khóa chấp nhận phải nhất quán với vòng đời artifact còn hiệu lực.
8. Tenant override không được tạo ra tổ hợp nằm ngoài quyền được cấp cho tenant.

Các kiểm tra phụ thuộc mạng nên có timeout và phân loại lỗi. “Không truy cập được provider trong ba giây” khác “policy yêu cầu provider chưa được cấu hình”. Một lỗi tạm thời không nên bị diễn giải thành việc được phép bỏ qua xác minh.

## 6. Tạo snapshot bất biến cho từng thao tác

Không nên để một request đọc từng khóa trực tiếp từ một map đang bị cập nhật. Nếu `ttl` đến từ revision 184 nhưng `allowedChannels` và yêu cầu review đến từ revision 185, hệ thống đang thực thi một policy chưa từng được phê duyệt.

Mô hình phù hợp là:

```text
Đọc candidate
    → parse
    → validate toàn bộ
    → resolve override được phép
    → tạo EffectiveRecoveryPolicy bất biến
    → thay con trỏ active bằng một thao tác atomic
```

Đoạn Java sau minh họa việc giữ snapshot cho một **profile challenge email**, không triển khai toàn bộ luồng recovery hay cơ chế phân phối cấu hình:

```java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class RecoveryPolicyRegistry {
    public record EmailChallengePolicy(
            long revision,
            long securityEpoch,
            Duration ttl,
            int maxVerificationAttempts,
            Duration resendCooldown,
            boolean issueNewChallenges,
            boolean verifyExistingChallenges) {

        public EmailChallengePolicy {
            Objects.requireNonNull(ttl, "ttl");
            Objects.requireNonNull(resendCooldown, "resendCooldown");
            if (revision < 1 || securityEpoch < 1) {
                throw new IllegalArgumentException("Invalid policy identity");
            }
            // Các biên này chỉ minh họa contract của profile trong ví dụ.
            if (ttl.compareTo(Duration.ofMinutes(1)) < 0
                    || ttl.compareTo(Duration.ofMinutes(20)) > 0) {
                throw new IllegalArgumentException("TTL outside profile bounds");
            }
            if (maxVerificationAttempts < 1 || maxVerificationAttempts > 5) {
                throw new IllegalArgumentException("Invalid attempt budget");
            }
            if (resendCooldown.isNegative()
                    || resendCooldown.isZero()
                    || resendCooldown.compareTo(ttl) >= 0) {
                throw new IllegalArgumentException("Invalid resend cooldown");
            }
        }
    }

    private final AtomicReference<EmailChallengePolicy> active;

    public RecoveryPolicyRegistry(EmailChallengePolicy initial) {
        this.active = new AtomicReference<>(Objects.requireNonNull(initial));
    }

    public EmailChallengePolicy snapshot() {
        return active.get();
    }

    public synchronized void activate(EmailChallengePolicy candidate) {
        Objects.requireNonNull(candidate);
        EmailChallengePolicy current = active.get();
        if (candidate.revision() <= current.revision()) {
            throw new IllegalArgumentException("Revision must advance");
        }
        if (candidate.securityEpoch() < current.securityEpoch()) {
            throw new IllegalArgumentException("Security epoch cannot regress");
        }
        active.set(candidate);
    }
}
```

Khi bắt đầu một thao tác phát challenge:

```java
var policy = registry.snapshot();
if (!policy.issueNewChallenges()) {
    throw new RecoveryTemporarilyUnavailableException();
}
// Dùng cùng policy cho toàn bộ quyết định phát challenge này.
// expiresAt được tính từ thời điểm phát do server xác định.
// Lưu revision, epoch và các ràng buộc cần thiết cùng challenge.
```

`RecoveryTemporarilyUnavailableException` là tên lỗi nghiệp vụ minh họa. Registry trên chỉ bảo đảm không trộn trường trong một tiến trình và ngăn activation lùi theo trạng thái đang giữ. Nó chưa xác minh chữ ký, nguồn phát hành, tenant, đồng bộ liên node hay mốc epoch bền vững sau restart. Những trách nhiệm đó cần nằm trong tầng phân phối và lưu trữ tin cậy.

Một snapshot ở lúc phát không thay thế kiểm tra lại khi hoàn tất. Giữa hai thời điểm đó, bằng chứng hoặc phương thức có thể đã bị thu hồi do sự cố bảo mật.

## 7. Xử lý challenge đang tồn tại khi policy thay đổi

Đây là phần dễ gây lỗi nhất khi hot reload. Challenge là một cam kết có giới hạn tại thời điểm phát, không phải quyền bất biến được vượt mọi policy về sau.

Nên lưu cùng challenge những thông tin đủ để tái hiện và kiểm soát quyết định:

```text
challengeId
subjectId hoặc tham chiếu chủ thể nội bộ
tenantId
purpose / action được cấp quyền
profileId
issuedAt / expiresAt
policyRevisionAtIssue
securityEpochAtIssue
attemptBudgetAtIssue
evidenceState / requiredReviewState
keyId nếu artifact phụ thuộc khóa
consumedAt / revokedAt / trạng thái xử lý
```

Không đưa token thô, mã OTP, recovery code hoặc secret vào log chỉ để có khả năng truy vết policy.

### 7.1. Không tự kéo dài thời hạn của artifact cũ

Giả sử link phát lúc 10:00 với `expiresAt = 10:10`. Đến 10:04, policy mới cho phép TTL hai mươi phút. Link cũ vẫn hết hạn lúc 10:10. Tính lại thời hạn bằng TTL hiện hành sẽ làm thay đổi cam kết đã lưu và kéo dài cơ hội sử dụng artifact bị đánh cắp.

Nếu policy mới rút ngắn TTL, hệ thống cần một quy tắc migration rõ: giữ thời hạn cũ nếu vẫn nằm trong mức rủi ro được phê duyệt, rút ngắn theo điều kiện được định nghĩa, hoặc thu hồi nhóm challenge. Không âm thầm dùng cách khác nhau ở các node.

### 7.2. Không khôi phục ngân sách thử khi đổi revision

Nếu challenge đã thử sai bốn lần trên ngân sách năm lần, đổi revision không được reset bộ đếm. Việc giảm ngân sách có thể khiến challenge không còn được thử tiếp; việc tăng ngân sách không tự cấp thêm lượt cho challenge cũ trừ khi có chính sách migration được phê duyệt rõ ràng.

Giới hạn theo challenge phải đi cùng giới hạn tổng theo tài khoản hoặc phạm vi phù hợp. Nếu tạo challenge mới liên tục lại cấp một ngân sách đầy đủ, giới hạn theo challenge đơn lẻ không kiểm soát được tổng số lần đoán.

### 7.3. Quyền hoàn tất phải thỏa cả ràng buộc đã lưu và điều kiện hiện hành

Tại bước hoàn tất, cần kiểm tra trạng thái challenge, điều kiện đã gắn với challenge, quyền hiện hành đối với hành động cụ thể và các quyết định thu hồi. Không được chỉ hỏi “revision lúc phát có từng hợp lệ không?”.

Ví dụ, email link đã được phát cho reset mật khẩu không mặc nhiên cấp quyền gỡ MFA hoặc tạo passkey mới. Tương tự, policy mới yêu cầu review đối với một dấu hiệu rủi ro không được bị bỏ qua bằng cách yêu cầu backend dùng snapshot cũ.

### 7.4. Dùng security epoch có phạm vi được định nghĩa

Một sự cố có thể yêu cầu vô hiệu hóa tất cả challenge thuộc một thế hệ khóa hoặc kênh bị ảnh hưởng. Hệ thống có thể dùng epoch theo module, tenant, phương thức hoặc một phạm vi khác, nhưng phải ghi rõ cách so sánh và nơi lưu mốc tin cậy.

Không chỉ lưu `securityEpoch: 12` bên trong chính file cấu hình rồi coi như đã chống rollback. Nếu kẻ tấn công hoặc công cụ triển khai có thể khôi phục cả file lẫn mốc so sánh, node vẫn có thể chấp nhận policy cũ. Mốc tối thiểu phải được bảo vệ và lấy từ nguồn tin cậy phù hợp; sau restart cũng phải áp dụng được.

Thu hồi theo epoch cũng cần xem xét các tác vụ đang chạy. Phải kiểm tra điều kiện ở sát ranh giới commit hoặc ranh giới cấp quyền có bảo đảm nhất quán, để request đã bắt đầu trước sự cố không hoàn tất theo quyền vừa bị thu hồi.

## 8. Phân phối cấu hình trên nhiều node và nhiều vùng

Thay đổi một bản ghi cấu hình không có nghĩa mọi node đã áp dụng. Có thể tồn tại node mất kết nối, cache cũ, bản ứng dụng không hiểu schema mới hoặc worker nền chưa reload.

Một vòng phát hành có kiểm soát có thể gồm:

1. Tạo candidate với revision mới và checksum nội dung đã chuẩn hóa.
2. Validate schema, semantics, phạm vi và quyền người phát hành.
3. Gửi candidate tới các node hoặc nhóm node đích để chuẩn bị.
4. Thu nhận trạng thái đã tải, đã validate và khả năng thực thi của từng nhóm.
5. Kích hoạt theo kế hoạch rollout đã được phê duyệt.
6. Xác minh revision thực tế tại ingress, API, consumer và các vùng liên quan.
7. Gỡ lưu lượng hoặc hạn chế thao tác ở node không còn đáp ứng mức policy tối thiểu.

Phải phân biệt `downloaded`, `validated` và `active`. Một metric chỉ báo “đã nhận event” không chứng minh node đang áp dụng policy mới.

### 8.1. Canary chỉ phù hợp khi biết cách xử lý policy chênh lệch

Canary một thay đổi giao diện thường ít ảnh hưởng đến tính nhất quán bảo mật. Canary policy xác thực đòi hỏi thiết kế kỹ hơn. Challenge có thể được phát tại node A nhưng xác minh tại node B; request có thể đi qua vùng khác sau failover.

Nếu không có contract xử lý chênh revision, người tấn công có thể thử tìm node còn policy yếu hơn. Sticky session có thể giảm một số lỗi trải nghiệm nhưng không chứng minh ranh giới bảo mật, đặc biệt khi retry, failover hoặc API trực tiếp thay đổi đường đi.

Cần quyết định trước:

- Phiên bản ứng dụng nào hiểu và thực thi được candidate?
- Challenge thuộc revision mới có được xử lý ở node cũ không?
- Node cũ phải từ chối thao tác nào khi không hiểu yêu cầu mới?
- Ở đâu kiểm tra mốc policy hoặc epoch tối thiểu cho bước hoàn tất?
- Làm sao ngừng node cũ tham gia sau thời điểm cắt chuyển?

### 8.2. Thay đổi khẩn cấp không được phụ thuộc vào eventual convergence đơn thuần

Đối với thay đổi như thu hồi kênh bị xâm phạm, không thể chỉ chờ “cuối cùng mọi cache sẽ mới”. Cần chọn bảo đảm phù hợp với kiến trúc: kiểm tra trạng thái thu hồi qua backend có tính nhất quán cần thiết, xác minh lease cấu hình còn hạn, hoặc đưa node chậm cập nhật ra khỏi đường cấp quyền.

Nếu dùng lease, định nghĩa ai cấp, thời hạn tối đa, xử lý lệch đồng hồ và thao tác bị chặn khi hết hạn. Lease chỉ giới hạn cửa sổ stale trong mô hình đã giả định; nó không làm hệ thống tự nhiên có hiệu lực thu hồi tức thời.

### 8.3. Áp dụng cả ở tác vụ nền

Consumer gửi thông báo, job hoàn tất review và dịch vụ thu hồi session cũng dùng cấu hình. Một API đã chặn kênh nhưng consumer vẫn gửi link theo event cũ có thể gây nhầm lẫn hoặc tái tạo artifact không được phép.

Event nên có định danh và ngữ cảnh đủ để consumer kiểm tra quyền thực thi, xử lý idempotent và không tự cấp quyền mới. Retry việc gửi một thông báo không được biến thành phát một challenge mới ngoài policy hiện hành.

## 9. Quản lý secret, khóa và URL liên quan recovery

### 9.1. Quyền đọc secret theo nhu cầu thực tế

Dịch vụ gửi email không nhất thiết cần quyền đọc khóa tạo token; dịch vụ xác minh token không nhất thiết cần quyền quản trị provider. Tách quyền giúp một credential vận hành bị lộ không tự mở toàn bộ luồng recovery.

Thông tin nhạy cảm không nên xuất hiện trong repository, artifact cấu hình được lưu rộng rãi, log khởi động hay endpoint chẩn đoán. Khi hiển thị effective configuration cho người vận hành, dùng danh sách trường được phép hiển thị và che các giá trị nhạy cảm. Tắt log toàn bộ object cấu hình thường chưa đủ nếu thư viện khác vẫn log dữ liệu đã bind.

### 9.2. Đổi khóa theo vòng đời artifact

Với thiết kế có dùng MAC hoặc chữ ký, có thể cần một khóa phát mới và tập khóa được chấp nhận để kiểm tra artifact còn hiệu lực. `keyId` chỉ chọn khóa trong tập tin cậy do server quản lý; không cho client chỉ định đường dẫn secret hoặc URL tải khóa tùy ý.

Quy trình đổi khóa bình thường có thể là:

```text
Chuẩn bị khóa mới
    → đảm bảo verifier biết khóa mới
    → chuyển issuer sang khóa mới
    → giữ khóa cũ cho artifact hợp lệ còn tồn tại
    → gỡ khóa cũ sau khi hết nhu cầu xác minh
```

Khi khóa bị xâm phạm, lịch giữ khóa cũ có thể không còn phù hợp. Cần thu hồi và yêu cầu người dùng bắt đầu lại theo phương thức an toàn. Không kéo dài chấp nhận khóa bị lộ chỉ để tránh báo lỗi recovery.

Không phải mọi recovery token đều cần chữ ký. Token opaque ngẫu nhiên với trạng thái server có mô hình khác. Cấu hình phải phản ánh thiết kế đang dùng, không thêm một cơ chế mật mã hình thức rồi bỏ qua trạng thái sử dụng một lần.

### 9.3. Khóa URL và địa chỉ gửi theo môi trường tin cậy

URL trong email recovery phải được xây từ origin tin cậy của môi trường hoặc tenant đã xác minh. Không lấy tùy ý từ header request hoặc tham số `returnUrl`. Kiểm tra host phải dựa vào URI được parse và quy tắc so sánh rõ ràng; kiểm tra chuỗi chứa `example.com` có thể chấp nhận một đích hoàn toàn khác.

Nếu hỗ trợ domain riêng theo tenant, xác minh quyền sở hữu, ánh xạ tenant và quy trình thay đổi domain. Cần ràng buộc scheme, host, port và đường dẫn theo thiết kế, tránh user-info trong URI, fragment không mong muốn và cơ chế redirect mở.

Các endpoint provider cũng phải do cấu hình tin cậy quản lý. Không biến trường cấu hình cho tenant thành khả năng yêu cầu backend kết nối đến địa chỉ nội bộ bất kỳ.

## 10. Rollback cấu hình và xử lý sự cố phụ thuộc

### 10.1. Phân biệt quay lại hành vi cũ với quay lùi danh tính policy

Một cấu hình mới có thể làm tăng lỗi xác minh. Người vận hành muốn trở lại các tham số đã hoạt động trước đó. Nên phát hành **revision mới** chứa những giá trị cũ vẫn được phép, thay vì làm giảm revision hoặc epoch.

Ví dụ:

```text
revision 184, epoch 12: cấu hình đang hoạt động
revision 185, epoch 12: thay provider timeout, phát hiện lỗi
revision 186, epoch 12: khôi phục timeout trước đó
```

Nếu epoch đã tăng lên 13 do một sự cố bảo mật, revision tiếp theo không được quay về epoch 12. Bản rollback cần giữ điều kiện thu hồi mới và chỉ khôi phục những phần còn an toàn, chẳng hạn cấu hình provider.

### 10.2. Last-known-good phải còn được phép sử dụng

Giữ snapshot hợp lệ gần nhất có ích khi candidate mới sai cú pháp hoặc hệ thống cấu hình tạm thời mất kết nối. Tuy nhiên, snapshot đã hợp lệ hôm qua có thể không còn được phép sau lệnh thu hồi hôm nay.

Chỉ dùng last-known-good trong contract rõ ràng về nguồn tin cậy, mốc epoch tối thiểu, tuổi snapshot hoặc lease và phạm vi thao tác. Nếu không thể chứng minh điều kiện tối thiểu còn hiệu lực, hạn chế các hành động cấp quyền nhạy cảm theo thiết kế; không tự mặc định mở recovery để “giữ availability”.

### 10.3. Lỗi phụ thuộc cần hành vi theo từng giai đoạn

| Tình huống | Hành vi có thể thiết kế | Điều kiện phải giữ |
|---|---|---|
| Candidate không hợp lệ | Không kích hoạt candidate; giữ snapshot đang được phép | Báo lỗi revision và nguyên nhân, không trộn trường |
| Control plane mất kết nối | Dùng snapshot còn đủ điều kiện hoặc hạn chế thao tác | Tuân thủ tuổi cấu hình, lease và mốc thu hồi |
| Provider gửi tin lỗi | Retry có giới hạn hoặc chuyển kênh đã được cho phép | Không tự bỏ xác minh hay phát challenge vô hạn |
| Backend giới hạn thử lỗi | Chặn hoặc hoãn thao tác cần kiểm soát đó | Không coi lỗi backend là còn vô hạn lượt thử |
| Backend thu hồi session lỗi | Giữ trạng thái đang hoàn tất hoặc chặn cấp quyền theo thiết kế | Không báo đã thu hồi khi mới gửi yêu cầu |
| Bộ xác minh không hiểu schema | Không tham gia thực thi policy đó | Không bỏ qua điều kiện chưa hiểu |

Thông báo ngoài hệ thống cần hữu ích mà không tiết lộ tài khoản tồn tại, trạng thái factor hoặc nội dung policy nhạy cảm. Chi tiết kỹ thuật đi vào kênh vận hành có quyền truy cập phù hợp.

## 11. Kiểm soát thay đổi và quyền quản trị

Một thay đổi policy nên có bản diff dễ đọc và mô tả tác động đến từng hành động recovery. “Đổi cấu hình email” là mô tả quá chung nếu nó đồng thời đổi host link và loại bỏ bước review.

Luồng thay đổi có thể gồm đề xuất, kiểm tra tự động, người có thẩm quyền phê duyệt, phát hành và xác minh sau triển khai. Mức phê duyệt nên tương xứng với khả năng thay đổi quyền xác thực; thay template chữ khác với mở kênh gỡ MFA.

Tách vai trò khi cần thiết:

- Người đề xuất được tạo candidate nhưng không tự phát hành policy nhạy cảm.
- Người phê duyệt xem diff, phạm vi và bằng chứng kiểm tra.
- Danh tính triển khai chỉ được kích hoạt artifact đã được phê duyệt.
- Người ứng phó sự cố có quyền hạn chế hoặc thu hồi theo phạm vi được cấp.

Quyền break-glass cần có phạm vi, thời hạn và ghi nhận việc sử dụng. Nếu một công cụ ứng phó có thể đặt `skipVerification=true`, nó đang cấp một quyền thay thế xác thực rất lớn; không thể coi đó là một feature flag vận hành thông thường.

### 11.1. Audit đủ để giải thích, không thu thập bí mật

Sự kiện activation có thể chứa:

```json
{
  "eventType": "RECOVERY_POLICY_ACTIVATED",
  "environment": "production",
  "scope": "default-policy",
  "revision": 186,
  "securityEpoch": 12,
  "previousRevision": 185,
  "actorRef": "deployment-identity",
  "changeRef": "change-4821",
  "artifactDigest": "sha256:<digest-of-non-secret-policy-artifact>",
  "result": "activated"
}
```

Digest chỉ phục vụ định danh và phát hiện khác biệt theo mô hình tin cậy đã chọn; nó không tự chứng minh ai được phép phát hành. Không tính một checksum công khai trên tập dữ liệu chứa secret yếu rồi coi như đã che secret. Chọn artifact policy không chứa secret và ghi tham chiếu phù hợp.

Log nghiệp vụ có thể liên kết lần recovery với revision và outcome code. Không log token, OTP, URL đầy đủ có token, nội dung bằng chứng danh tính hoặc địa chỉ liên hệ nguyên dạng chỉ để phục vụ debug.

## 12. Quan sát cấu hình đang thực sự được áp dụng

Cần quan sát cả trạng thái phân phối và tác động nghiệp vụ.

Ở tầng cấu hình, theo dõi số lần activation thành công hoặc thất bại, node chưa đạt revision tối thiểu, snapshot quá tuổi, lease hết hạn và lỗi truy cập secret. Ở tầng recovery, theo dõi tỷ lệ phát challenge, xác minh thành công, hết hạn, bị giới hạn, chuyển review và lỗi hoàn tất.

Tránh gắn số lượng lớn tenant ID, user ID hoặc mọi revision vào label metric không có giới hạn. Có thể dùng metric tổng hợp theo nhóm hữu hạn, kết hợp log hoặc trace được kiểm soát để tra cứu revision cụ thể và tenant cụ thể.

Một trang vận hành nên trả lời được:

1. Policy nào đang được kỳ vọng ở môi trường và phạm vi này?
2. Những node nào đã kích hoạt, node nào chưa, và vì sao?
3. Có node nào đang xử lý với snapshot không còn được phép không?
4. Tỷ lệ lỗi tăng bắt đầu từ revision hoặc đợt rollout nào?
5. Đang có bao nhiêu recovery ở trạng thái cần xử lý sau thay đổi?

Không cần công khai toàn bộ effective configuration để đạt khả năng quan sát này. Cung cấp một projection gồm định danh policy, trạng thái và giá trị được phép xem thường an toàn hơn xuất object cấu hình đầy đủ.

## 13. Kiểm tra thay đổi trước khi triển khai

Kiểm tra cấu hình nên tập trung vào hành vi có thể làm thay đổi quyền, không chỉ việc file đúng YAML.

### 13.1. Kiểm tra tĩnh và compatibility

- Sai khóa, khóa trùng, trường bắt buộc thiếu, duration sai và giá trị ngoài biên phải có kết quả xác định.
- Phiên bản ứng dụng cũ phải xử lý schema mới theo contract, không âm thầm bỏ qua điều kiện bảo mật.
- Mọi tenant override phải nằm trong phạm vi được cấp và tạo ra effective policy hợp lệ.
- Policy artifact không chứa secret thật hoặc địa chỉ production xuất hiện sai môi trường.

### 13.2. Kiểm tra chuyển tiếp trạng thái

| Kịch bản | Kết quả cần chứng minh |
|---|---|
| Phát link rồi tăng TTL | Link cũ không tự sống lâu hơn |
| Đã thử sai gần hết ngân sách rồi đổi revision | Không được cấp lại lượt thử ngoài quy tắc migration |
| Tắt phát mới nhưng giữ xác minh cũ | Không phát challenge mới; challenge cũ vẫn qua đầy đủ điều kiện |
| Thu hồi một epoch trong lúc đang review | Không hoàn tất theo bằng chứng thuộc epoch bị thu hồi |
| Reset mật khẩu rồi yêu cầu gỡ MFA | Không tái sử dụng quyền reset cho hành động khác |
| Một node chậm cập nhật | Không tạo đường hoàn tất yếu hơn qua node đó |
| Retry hoặc nhận event trùng | Không phát sinh thêm quyền hay tiêu thụ challenge hai lần |
| Thu hồi session gặp lỗi | Trạng thái phản ánh đúng việc chưa bảo đảm hậu điều kiện |
| Restart sau sự cố | Mốc chống rollback và quyết định thu hồi vẫn có hiệu lực |

### 13.3. Kiểm tra cạnh tranh tại điểm hoàn tất

Hai request cùng xác minh không được cùng tiêu thụ một challenge. Trạng thái sử dụng một lần, ngân sách thử và điều kiện commit cần được bảo đảm bởi cơ chế lưu trữ hoặc transaction phù hợp. Snapshot cấu hình bất biến không giải quyết thay phần cạnh tranh trạng thái này.

Cũng cần kiểm tra cuộc đua giữa thu hồi policy và commit recovery. Thiết kế phải xác định rõ điểm cấp quyền có tính quyết định và cách kiểm tra phiên bản hoặc epoch tại điểm đó. Một lần kiểm tra rất sớm ở ingress không đủ nếu giao dịch hoàn tất diễn ra sau lệnh thu hồi.

## 14. Ví dụ vận hành: điều chỉnh provider trong lúc có yêu cầu đang chờ

Giả sử revision 184 đang dùng provider gửi email hiện tại. Đội vận hành muốn đổi timeout và chuyển endpoint provider, trong khi nhiều người dùng đã nhận link recovery.

Một cách triển khai có kiểm soát:

**Bước 1 — Xác định phạm vi.** Chỉ thay thông số kết nối và định tuyến của provider; giữ nguyên bằng chứng được chấp nhận, quyền reset mật khẩu, điều kiện MFA, thời hạn đã lưu và hậu điều kiện session. Nếu endpoint mới yêu cầu thay cách tạo link, phạm vi cần được đánh giá thêm thay vì coi như đổi hạ tầng thuần túy.

**Bước 2 — Tạo candidate 185.** Kiểm tra host provider, quyền secret, timeout và ngân sách retry. Bảo đảm retry không tạo challenge mới và request gửi có định danh idempotency theo khả năng của tích hợp.

**Bước 3 — Kiểm tra đường gửi và đường xác minh độc lập.** Link đã phát vẫn được xác minh theo trạng thái server và các ràng buộc hiện hành. Chuyển provider gửi không được làm mất khả năng kiểm tra artifact hợp lệ hoặc vô tình nhận artifact không hợp lệ.

**Bước 4 — Rollout và xác nhận.** Quan sát revision tại API và consumer, tỷ lệ gửi thành công, độ trễ và lỗi. Xác minh node chậm cập nhật không tiếp tục sử dụng endpoint đã bị cấm nếu việc chuyển đổi có tính bảo mật khẩn cấp.

**Bước 5 — Khôi phục khi lỗi.** Nếu candidate gây lỗi kết nối, phát hành revision 186 phục hồi giá trị provider còn hợp lệ. Giữ nguyên mọi epoch hoặc quyết định thu hồi đã có. Nếu provider cũ đã bị xâm phạm, không quay lại chỉ vì provider mới đang lỗi; dùng phương án hạn chế hoặc kênh khác đã được phê duyệt.

Ví dụ này cho thấy rollback là quyết định về những giá trị được phép trở lại, không phải chép nguyên file cũ bất kể ngữ cảnh.

## 15. Những lỗi thiết kế thường gặp

### “Cấu hình chỉ là dữ liệu nên ai deploy cũng đổi được”

Nếu dữ liệu quyết định bằng chứng nào được chấp nhận, quyền chỉnh nó có thể tương đương quyền đổi cơ chế xác thực. Cần quyền hạn và audit tương xứng.

### “Không đọc được cấu hình thì dùng mặc định dễ nhất”

Mặc định mở tất cả kênh hoặc bỏ kiểm tra giúp request chạy tiếp nhưng phá ranh giới recovery. Cần một trạng thái lỗi có chủ đích theo từng thao tác, cùng snapshot còn được phép nếu kiến trúc hỗ trợ.

### “Đã bật feature flag là đủ đồng bộ”

Feature flag không tự bảo đảm mọi node cùng nhìn thấy, trạng thái challenge được migration đúng hay việc hoàn tất có tính nguyên tử. Cần contract và bằng chứng phân phối thực tế.

### “Giữ policy lúc phát là luôn đủ”

Snapshot lúc phát giúp truy vết và giữ ràng buộc, nhưng không được vượt quyết định thu hồi hiện hành. Quyền hoàn tất cần được kiểm tra lại tại ranh giới thích hợp.

### “Rollback là giảm version về bản trước”

Giảm version làm mất dấu tiến trình phát hành và có thể tái chấp nhận policy đã bị thu hồi. Hãy dùng revision mới, giữ các mốc bảo mật không được lùi.

### “Đóng kênh yếu thì recovery tự an toàn”

Nếu hệ thống tự chuyển sang một fallback chưa được đánh giá hoặc support bỏ xác minh để giảm hàng chờ, mức bảo vệ vẫn có thể giảm. Fallback cần policy riêng về bằng chứng, quyền và audit.

## 16. Câu hỏi tự kiểm tra

1. Khi cùng một khóa xuất hiện ở biến môi trường và control plane, nguồn nào được phép quyết định? Hệ thống có phát hiện xung đột không?
2. Nếu TTL tăng sau khi phát link, `expiresAt` của link cũ thay đổi thế nào và vì sao?
3. Sau khi đổi revision, điều gì ngăn ngân sách thử của challenge hoặc tài khoản bị reset?
4. Một node bị mất kết nối trong lúc thu hồi kênh recovery sẽ được phép làm những thao tác nào?
5. Điều gì bảo vệ mốc epoch khi tiến trình restart hoặc khi công cụ triển khai khôi phục file cũ?
6. Có thể khôi phục cấu hình provider trước đó mà vẫn giữ nguyên quyết định thu hồi mới không?
7. Khi việc vô hiệu hóa session chưa hoàn tất, người dùng và hệ thống thấy trạng thái nào?
8. Có trường hợp nào log hoặc trang chẩn đoán đang lộ token, secret hay bằng chứng danh tính không?

Một hệ thống quản lý cấu hình recovery tốt phải giải thích được policy nào đã cấp quyền cho một hành động, chứng minh policy đó còn được phép tại lúc hoàn tất và thay đổi hành vi vận hành mà không làm mất các ràng buộc xác thực đã được đặt ra.
