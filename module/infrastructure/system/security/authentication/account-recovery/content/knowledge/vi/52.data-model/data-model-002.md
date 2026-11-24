# Recovery challenge entity — Mô hình dữ liệu cho thử thách khôi phục tài khoản

## 1. Challenge đại diện cho một yêu cầu chứng minh cụ thể

Recovery challenge là thực thể ghi lại một thử thách mà người yêu cầu khôi phục phải đáp ứng trong một ngữ cảnh xác định. Ví dụ: nhập mã được gửi tới một địa chỉ đã đăng ký hoặc trình bày token từ liên kết khôi phục.

Thực thể này cần giúp máy chủ trả lời:

1. Thử thách thuộc yêu cầu recovery và tài khoản nào?
2. Bằng chứng được phép dùng cho mục đích gì?
3. Máy chủ xác minh bằng chứng như thế nào mà không lưu bí mật dưới dạng dễ lộ?
4. Thử thách còn hạn, còn lượt thử và còn là thử thách hiện hành không?
5. Đã có giao dịch nào tiêu thụ bằng chứng này thành công chưa?

Một bản ghi chỉ gồm email, code và expiresAt thường thiếu những ràng buộc cần thiết. Cùng một mã có thể bị chấp nhận nhầm cho yêu cầu khác, bộ đếm thử sai có thể mất cập nhật và hai máy chủ có thể đồng thời xác nhận thành công.

OWASP khuyến nghị token hoặc mã khôi phục được sinh bằng nguồn ngẫu nhiên an toàn, lưu trữ an toàn, có hạn dùng và chỉ dùng một lần. Mô hình dữ liệu phải tạo điều kiện thực thi các đặc tính đó. Xem [Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Các tên thực thể, trạng thái và SQL trong bài là một phương án thiết kế minh họa. Phần schema cụ thể tập trung vào challenge sử dụng OTP do máy chủ cấp hoặc URL token, không phải schema đầy đủ cho mọi hình thức xác minh danh tính.

## 2. Phân biệt challenge với request, bằng chứng và quyền khôi phục

| Thành phần | Trách nhiệm |
| --- | --- |
| Recovery request | Điều phối một hành trình recovery, các yêu cầu bằng chứng và kết quả chung |
| Recovery challenge | Quản lý một thử thách được cấp cho một yêu cầu chứng minh cụ thể |
| Verification attempt | Ghi nhận một lần gửi bằng chứng và kết quả xử lý tối thiểu |
| Verified evidence | Ghi lại kết quả chứng minh đã được chấp nhận, cùng nguồn gốc và phạm vi |
| Recovery grant | Cấp quyền có giới hạn để thực hiện hành động tiếp theo khi đã đủ điều kiện |

Một request có thể cần nhiều challenge. Một challenge thành công chỉ cung cấp bằng chứng trong phạm vi của nó; việc có được một bằng chứng không tự cho phép bỏ qua các yêu cầu còn lại.

~~~mermaid
erDiagram
    RECOVERY_REQUEST ||--o{ RECOVERY_CHALLENGE : contains
    RECOVERY_CHALLENGE ||--o{ VERIFICATION_ATTEMPT : receives
    RECOVERY_CHALLENGE ||--o| VERIFIED_EVIDENCE : produces
    RECOVERY_REQUEST ||--o{ RECOVERY_GRANT : authorizes
~~~

Trong mô hình minh họa, một challenge tạo tối đa một bằng chứng được chấp nhận. Request mới là nơi quyết định tổ hợp bằng chứng có đủ để cấp grant hay chưa.

Không dùng boolean “verified” trên tài khoản để thay toàn bộ cấu trúc này. Giá trị đó không giải thích ai đã xác minh, bằng cách nào, cho request nào hoặc tại thời điểm nào.

## 3. Những nhóm trường cốt lõi

### Định danh và phạm vi

| Trường | Ý nghĩa |
| --- | --- |
| challengeId | Định danh không chứa bí mật xác minh |
| tenantId | Phạm vi tenant nếu dịch vụ có nhiều tenant |
| requestId | Yêu cầu recovery sở hữu challenge |
| accountId | Tài khoản đích đã được máy chủ xác định |
| requirementKey | Yêu cầu bằng chứng trong request mà challenge đáp ứng |
| purpose | Hành động recovery đang được xem xét |
| generation | Lần cấp challenge trong cùng request và requirement |

purpose có thể là RESET_PASSWORD, REPLACE_MFA hoặc REGISTER_PASSKEY. Các giá trị cụ thể phụ thuộc nghiệp vụ; chúng phải được xác định ở máy chủ.

Không lấy accountId hoặc purpose từ biểu mẫu rồi tin rằng chúng đúng. Máy chủ cần đối chiếu request, quyền tiếp tục và quan hệ sở hữu dữ liệu. Một UUID khó đoán cũng không thay thế kiểm soát truy cập.

### Cơ chế bằng chứng và kênh

| Trường | Ý nghĩa |
| --- | --- |
| proofType | Cách xác minh, chẳng hạn OTP hoặc URL_TOKEN |
| destinationRef | Tham chiếu nội bộ tới đích gửi đã được chọn |
| destinationVersion | Phiên bản thông tin liên hệ dùng khi cấp challenge |
| verifierMac | Giá trị dùng để kiểm tra bí mật trong thiết kế HMAC minh họa |
| verifierKeyId | Tham chiếu tới phiên bản khóa phía máy chủ |
| policyVersion | Chính sách dùng khi cấp challenge |

Tham chiếu đích gửi giúp tránh sao chép email hoặc số điện thoại đầy đủ vào mọi bản ghi. Nó cũng giúp nhận biết rằng địa chỉ đã thay đổi sau lúc cấp challenge.

Thay đổi thông tin liên hệ có thể làm challenge cũ không còn phù hợp. Chính sách cần xác định khi nào phải thu hồi hoặc xác minh lại; việc bản ghi còn trỏ tới một địa chỉ không tự chứng minh địa chỉ ấy còn an toàn.

### Vòng đời và giới hạn

| Trường | Ý nghĩa |
| --- | --- |
| state | Trạng thái lưu trữ của challenge |
| failedAttempts | Số lần xác minh sai đã được ghi nhận |
| maxFailedAttempts | Ngưỡng thử sai của challenge |
| createdAt, issuedAt | Thời điểm tạo và bắt đầu hiệu lực |
| expiresAt | Hạn cuối được chấp nhận bằng chứng |
| resolvedAt | Thời điểm kết thúc bằng tiêu thụ, khóa hoặc thu hồi |
| consumedAt | Thời điểm bằng chứng đã được chấp nhận và tiêu thụ |
| rowVersion | Phiên bản bản ghi nếu cần đối chiếu cập nhật |

Giới hạn thử sai và thời hạn phải do chính sách phía máy chủ quyết định. Không cho client gửi maxFailedAttempts hoặc expiresAt tùy ý.

policyVersion phục vụ giải thích nguồn gốc cấu hình, không cho phép tiếp tục dùng một chính sách cũ đã bị thu hồi vì lý do bảo mật.

## 4. Lưu verifier thay cho bí mật

Mã OTP ngắn và token ngẫu nhiên dài có đặc tính khác nhau.

Token có đủ entropy có thể được kiểm tra qua giá trị băm với thiết kế phù hợp. OTP ngắn có không gian tìm kiếm nhỏ: một mã sáu chữ số chỉ có một triệu khả năng. OWASP chỉ rõ rằng băm OTP không đem lại khả năng chống dò ngoại tuyến mạnh như băm mật khẩu. Xem [Hashing OTPs](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#hashing-otps).

Một phương án cho OTP và token do dịch vụ cấp là lưu HMAC-SHA-256 của bí mật cùng ngữ cảnh. Khóa HMAC được quản lý ngoài cơ sở dữ liệu chứa challenge.

~~~text
verifierMac = HMAC-SHA-256(
    key = keyStore[verifierKeyId],
    message = encodeLengthPrefixed(
        "account-recovery/challenge/v1",
        tenantId,
        requestId,
        accountId,
        challengeId,
        requirementKey,
        purpose,
        proofType,
        generation,
        destinationRef,
        destinationVersion,
        policyVersion,
        secret
    )
)
~~~

Đây là thiết kế minh họa, không phải yêu cầu dùng cùng một định dạng cho mọi hệ thống. Cách mã hóa cần có thứ tự, kiểu dữ liệu và ranh giới trường rõ ràng; không nối chuỗi tùy ý khiến hai tập giá trị khác nhau sinh cùng một chuỗi đầu vào.

Các trường tham gia MAC phải giữ nguyên trong vòng đời challenge. Nếu đổi mục đích, đích gửi hoặc ngữ cảnh xác minh, hãy cấp challenge mới thay vì sửa những trường đó tại chỗ.

HMAC giúp hạn chế dò OTP ngoại tuyến khi chỉ cơ sở dữ liệu bị lộ và khóa vẫn được bảo vệ. Nó không ngăn dò trực tuyến qua API, không bảo vệ khi cả khóa và dữ liệu cùng bị chiếm quyền, và không làm kênh gửi OTP trở thành chống phishing.

Cần lưu verifierKeyId để tìm đúng khóa khi kiểm tra. Không lưu chính khóa HMAC cạnh verifierMac. Kế hoạch xoay khóa phải tính đến challenge còn hiệu lực; nếu khóa bị lộ, có thể cần thu hồi các challenge liên quan thay vì tiếp tục chấp nhận.

Bí mật gốc chỉ xuất hiện ở các điểm cần thiết cho việc cấp, gửi và xác minh; bảng challenge không lưu giá trị gốc. Không đưa OTP hay URL token vào log, exception, tracing hoặc sự kiện phân tích.

Mã có số 0 ở đầu cần được xử lý như chuỗi theo định dạng đã quy định. Không chuyển “004812” thành số nguyên rồi vô tình chấp nhận một biểu diễn khác. Nếu hỗ trợ chuẩn hóa đầu vào, quy tắc phải rõ và nhất quán giữa lúc cấp với lúc kiểm tra.

So sánh các giá trị MAC bằng cơ chế phù hợp để tránh rò rỉ thời gian so sánh. Quyền truy cập, thời hạn, giới hạn thử và trạng thái request vẫn phải được kiểm tra riêng.

## 5. Chọn vòng đời dễ thực thi một lần

Trong mô hình này, state có bốn giá trị lưu trữ:

| State | Ý nghĩa |
| --- | --- |
| ISSUED | Đã cấp, chưa kết thúc; còn phải kiểm tra hạn và ngữ cảnh |
| CONSUMED | Đã xác minh thành công và tiêu thụ bằng chứng |
| LOCKED | Đã đạt ngưỡng thử sai, không còn được kiểm tra bằng challenge này |
| REVOKED | Bị thu hồi, chẳng hạn do cấp phiên bản thay thế hoặc hủy request |

Hết hạn được xác định bằng expiresAt, không cần chờ một công việc nền đổi state:

~~~text
canAttempt =
    state == ISSUED
    and issuedAt <= trustedNow
    and trustedNow < expiresAt
    and failedAttempts < maxFailedAttempts
    and requestIsActive
    and challengeIsCurrentForRequirement
    and contextMatches
~~~

Một bản ghi ISSUED vẫn có thể đã hết hạn. Khi hiển thị trạng thái hoặc xét quyền dùng, phải kết hợp state với thời gian.

Trong phương án này, xác minh thành công và tiêu thụ bí mật là cùng một chuyển trạng thái sang CONSUMED. Không tạo một khoảng hở “VERIFIED nhưng còn dùng lại được” trước lúc ghi nhận bằng chứng.

CONSUMED chỉ nói rằng challenge đã hoàn thành nhiệm vụ chứng minh. Nó không có nghĩa mật khẩu đã được đổi, MFA đã được thay hoặc mọi session cũ đã bị thu hồi.

Các trạng thái kết thúc không được chuyển ngược về ISSUED. Nếu cần thử lại theo chính sách, cấp challenge mới với định danh và generation mới.

## 6. Schema PostgreSQL minh họa

~~~sql
CREATE TABLE recovery_challenge (
    challenge_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    request_id UUID NOT NULL,
    account_id UUID NOT NULL,
    requirement_key TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation > 0),

    purpose TEXT NOT NULL CHECK (
        purpose IN ('RESET_PASSWORD', 'REPLACE_MFA', 'REGISTER_PASSKEY')
    ),
    proof_type TEXT NOT NULL CHECK (
        proof_type IN ('OTP', 'URL_TOKEN')
    ),

    destination_ref UUID NOT NULL,
    destination_version BIGINT NOT NULL CHECK (destination_version > 0),
    policy_version TEXT NOT NULL,

    verifier_mac BYTEA NOT NULL CHECK (octet_length(verifier_mac) = 32),
    verifier_key_id TEXT NOT NULL,

    state TEXT NOT NULL DEFAULT 'ISSUED' CHECK (
        state IN ('ISSUED', 'CONSUMED', 'LOCKED', 'REVOKED')
    ),
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    max_failed_attempts INTEGER NOT NULL CHECK (max_failed_attempts > 0),

    created_at TIMESTAMPTZ NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    consumed_at TIMESTAMPTZ,
    row_version BIGINT NOT NULL DEFAULT 0 CHECK (row_version >= 0),

    CHECK (created_at <= issued_at),
    CHECK (issued_at < expires_at),
    CHECK (failed_attempts BETWEEN 0 AND max_failed_attempts),
    CHECK (resolved_at IS NULL OR resolved_at >= issued_at),
    CHECK (
        consumed_at IS NULL
        OR (consumed_at >= issued_at AND consumed_at < expires_at)
    ),
    CHECK (
        (state = 'ISSUED'
            AND resolved_at IS NULL AND consumed_at IS NULL)
        OR
        (state = 'CONSUMED'
            AND resolved_at IS NOT NULL
            AND consumed_at IS NOT NULL
            AND resolved_at = consumed_at)
        OR
        (state IN ('LOCKED', 'REVOKED')
            AND resolved_at IS NOT NULL AND consumed_at IS NULL)
    ),
    CHECK (
        (state = 'LOCKED' AND failed_attempts = max_failed_attempts)
        OR
        (state IN ('ISSUED', 'CONSUMED')
            AND failed_attempts < max_failed_attempts)
        OR
        state = 'REVOKED'
    ),

    UNIQUE (tenant_id, request_id, requirement_key, generation)
);

CREATE UNIQUE INDEX recovery_challenge_one_issued
    ON recovery_challenge (tenant_id, request_id, requirement_key)
    WHERE state = 'ISSUED';

CREATE INDEX recovery_challenge_request_lookup
    ON recovery_challenge (tenant_id, request_id, issued_at);

CREATE INDEX recovery_challenge_expiry_lookup
    ON recovery_challenge (expires_at)
    WHERE state = 'ISSUED';
~~~

Schema chỉ trình bày bảng challenge. Khi tích hợp, cần bổ sung khóa ngoại tới mô hình request, account và đích gửi thực tế; khóa ngoại ghép hoặc ràng buộc tương đương phải ngăn việc ghép request của tenant này với account của tenant khác.

Không đặt một CHECK phụ thuộc thời gian hiện tại để hy vọng cơ sở dữ liệu tự vô hiệu hóa bản ghi khi đồng hồ chạy. Các CHECK ở đây chỉ bảo vệ quan hệ giữa dữ liệu lưu; điều kiện còn hạn phải được xét khi xử lý thao tác.

Chỉ mục một bản ISSUED áp dụng cho **một requirement trong một request**, không phải toàn bộ tài khoản. Một bản ISSUED đã hết hạn vẫn chiếm vị trí trong chỉ mục. Luồng cấp mới phải thu hồi bản đó trong cùng giao dịch trước khi thêm bản thay thế.

Schema không dùng sự biến mất của bản ghi để biểu diễn tiêu thụ. Giữ dấu vết kết thúc giúp phân biệt đã dùng, đã khóa và bị thay thế trong thời gian lưu dữ liệu được phép.

## 7. Xác minh và tiêu thụ trong cùng giao dịch

Hai request xác minh có thể đến đồng thời ở hai máy chủ. Nếu cả hai cùng đọc “chưa dùng”, cùng so sánh đúng rồi cùng ghi thành công, thuộc tính dùng một lần đã bị phá vỡ.

Một cách thực hiện là khóa request trước, rồi khóa challenge theo một thứ tự thống nhất. Mọi đường cập nhật liên quan như cấp lại, hủy và tiêu thụ phải tuân theo cùng giao thức phối hợp.

PostgreSQL mô tả SELECT FOR UPDATE là cơ chế khóa các hàng được chọn để ngăn các giao dịch khác sửa, xóa hoặc lấy khóa xung đột cho tới khi giao dịch kết thúc. Xem [Row-Level Locks](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS).

Ví dụ truy vấn khóa challenge, sau khi đã khóa request:

~~~sql
SELECT *
FROM recovery_challenge
WHERE tenant_id = :tenant_id
  AND request_id = :request_id
  AND challenge_id = :challenge_id
FOR UPDATE;
~~~

Các tham số phải đến từ ngữ cảnh đã được máy chủ đối chiếu. Không chỉ tìm challenge bằng mã người dùng nhập rồi tự chọn tài khoản từ kết quả.

Một luồng giả mã:

~~~text
begin transaction

    request = lockRecoveryRequest(tenantId, requestId)
    challenge = lockChallenge(tenantId, requestId, challengeId)

    requireCallerCanUseThisRecoveryContext(request, callerContext)
    requireChallengeBelongsToRequestAndAccount(challenge, request)
    requireImmutableContextMatches(challenge, submittedContext)

    rejectIfRequestOrChallengeCannotBeUsed()

    candidateMac = calculateMacUsingStoredImmutableContext(
        challenge,
        submittedSecret
    )
    matches = constantTimeEquals(candidateMac, challenge.verifierMac)

    decisionTime = readCurrentDatabaseClock()

    if not eligibleAt(request, challenge, decisionTime):
        finishWithoutAcceptingProof()
        commit
        return rejectedResult

    if not matches:
        challenge.failedAttempts += 1
        challenge.rowVersion += 1

        if challenge.failedAttempts == challenge.maxFailedAttempts:
            challenge.state = LOCKED
            challenge.resolvedAt = decisionTime

        saveChallenge()
        recordFailedAttemptWithoutSecret()
        commit
        return rejectedResult

    consumeChallengeWithExpectedStateAndVersion(
        consumedAt = decisionTime,
        resolvedAt = decisionTime
    )
    insertVerifiedEvidenceWithUniqueChallengeReference()
    recordSuccessfulAttemptWithoutSecret()

commit
return acceptedEvidenceReference
~~~

eligibleAt cần kiểm tra hạn dùng, thời điểm bắt đầu hiệu lực, trạng thái request, giới hạn thử, generation hiện hành và chính sách còn cho phép tiếp tục. Kiểm tra này diễn ra sau khi lấy khóa, không chỉ ở một bước đọc trước giao dịch.

Bản ghi bằng chứng cần có ràng buộc duy nhất cho challenge trong phạm vi thích hợp, chẳng hạn tenantId và challengeId. Tiêu thụ challenge và ghi bằng chứng phải cùng commit hoặc cùng rollback. Nếu cập nhật tiêu thụ không tác động đúng một bản ghi, không được ghi bằng chứng thành công.

Các thao tác trong ví dụ được giữ ngắn; việc gửi email, chờ người dùng hoặc gọi một quy trình hỗ trợ kéo dài không nằm trong giao dịch đang khóa hàng. Nếu nhiều thực thể phải khóa, cần thống nhất thứ tự ở mọi đường xử lý và có cách xử lý lỗi giao dịch phù hợp.

### Đừng để lỗi nghiệp vụ làm mất bộ đếm thử sai

Nếu tăng failedAttempts rồi ném exception khiến transaction rollback, số lần sai có thể không được lưu. Người tấn công sẽ tiếp tục thử dù ứng dụng tưởng rằng đã giới hạn.

Kết quả “bằng chứng không hợp lệ” cần đi qua nhánh commit phần cập nhật bộ đếm. Lỗi hạ tầng làm rollback là một trường hợp khác và phải được kiểm soát bằng các giới hạn ở tầng rộng hơn.

Trong mô hình này, failedAttempts chỉ đếm lần xác minh sai của challenge còn được phép thử. Lần thành công không tăng bộ đếm này; lần gửi tới challenge đã kết thúc cũng không biến nó thành một thử thách mới.

## 8. Hạn dùng cần một mốc quyết định đáng tin

Chỉ có expiresAt chưa đủ nếu thời gian dùng để kiểm tra bị client điều khiển hoặc bị lấy quá sớm.

Ví dụ, giao dịch bắt đầu trước khi mã hết hạn nhưng phải chờ khóa một khoảng dài. Nếu dùng lại thời gian từ đầu giao dịch, hệ thống có thể chấp nhận bằng chứng sau mốc dự kiến.

Trong PostgreSQL, now() và CURRENT_TIMESTAMP phản ánh thời điểm bắt đầu giao dịch, còn clock_timestamp() trả thời gian thực tại lúc gọi. Khi cần kiểm tra sau lúc chờ khóa, phải chọn hàm và thời điểm lấy mốc phù hợp. Xem [Current Date/Time](https://www.postgresql.org/docs/current/functions-datetime.html#FUNCTIONS-DATETIME-CURRENT).

Trong giả mã trên, decisionTime được lấy từ đồng hồ cơ sở dữ liệu sau khi khóa và ngay trước chuyển trạng thái. Nó là mốc quyết định dùng cho điều kiện thời gian và các timestamp kết quả, không phải giá trị nhận từ client.

Cần định nghĩa rõ biên hạn dùng. Bài dùng điều kiện:

~~~text
issuedAt <= decisionTime < expiresAt
~~~

Khi decisionTime bằng expiresAt, bằng chứng không còn được chấp nhận. Thời điểm quyết định và thời điểm commit có thể khác nhau; tài liệu hệ thống phải nói rõ ý nghĩa của consumedAt và không nhầm nó với một cam kết rằng mọi công việc tiếp theo đã hoàn tất trước expiresAt.

Công việc nền dọn bản ghi giúp quản lý dung lượng, không phải hàng rào ngăn token hết hạn được sử dụng. Cho dù công việc nền bị chậm, đường xác minh vẫn phải từ chối đúng hạn.

Không lấy thời gian từ replica có thể trễ hoặc tin một cache còn ghi “ISSUED” để quyết định tiêu thụ. Quyết định cần đi qua nơi thực thi cập nhật nhất quán đã chọn.

## 9. Cấp lại tạo challenge mới theo chính sách rõ ràng

Có hai khái niệm khác nhau: thử gửi lại một thông điệp chứa cùng challenge và cấp một challenge mới.

Trong phương án “challenge mới thay challenge cũ”, quy trình có thể là:

1. Khóa request và xác nhận còn được phép cấp lại.
2. Xác định requirement cần đáp ứng.
3. Đánh dấu bản ISSUED cũ của requirement là REVOKED.
4. Sinh challengeId, bí mật và generation mới.
5. Ghi verifier cùng thời hạn, giới hạn thử và ràng buộc ngữ cảnh mới.
6. Cập nhật tham chiếu challenge hiện hành của requirement.
7. Commit dữ liệu cấp mới và công việc gửi nếu dùng cơ chế hàng đợi phù hợp.

Việc thu hồi và thêm bản mới phải cùng giao dịch. Chỉ mục một ISSUED là hàng rào bổ sung; khóa request giúp phối hợp cả khi trước đó chưa có challenge nào.

Không đổi bí mật ngay trên cùng một challengeId rồi đặt failedAttempts về không. Cách đó làm khó phân biệt các lần cấp, các lần gửi và kết quả của yêu cầu đến muộn.

Khi hai yêu cầu “gửi mã mới” đến đồng thời, không để cả hai tạo ra hai challenge hiện hành cho cùng requirement. Khi xác minh cạnh tranh với cấp lại, giao dịch có quyền khóa trước sẽ xác định diễn tiến; giao dịch sau phải kiểm tra lại trạng thái mới.

Giới hạn theo challenge chưa ngăn được việc liên tục cấp challenge mới để nhận thêm lượt đoán. Cần có ngân sách thử và giới hạn cấp lại theo account, request, nguồn hoặc phạm vi phù hợp. Các bộ đếm rộng hơn không được tự reset chỉ vì generation tăng.

Quy tắc “một challenge hiện hành” trong một request cũng không giải quyết mọi request song song của cùng tài khoản. Chính sách cấp quyền cuối cùng cần xét những yêu cầu khác, phiên bản bảo mật tài khoản và các thay đổi đã xảy ra.

## 10. Tách trạng thái chuyển phát khỏi trạng thái xác minh

Nhà cung cấp email hoặc SMS chấp nhận thông điệp không đồng nghĩa chủ tài khoản đã nhận, đọc hoặc trình bày bằng chứng hợp lệ.

Các lần chuyển phát nên có bản ghi riêng, tham chiếu challengeId:

| Nhóm dữ liệu chuyển phát | Ví dụ |
| --- | --- |
| Định danh | deliveryId, challengeId, kênh gửi |
| Lần thử | attemptNumber, thời điểm thử, thời điểm thử lại |
| Kết quả nhà cung cấp | Đã chấp nhận, lỗi tạm thời, không chuyển phát được |
| Đối chiếu | Mã tham chiếu nhà cung cấp với phạm vi truy cập phù hợp |

Callback chuyển phát không có quyền đặt challenge thành CONSUMED. Nó chỉ cập nhật dữ liệu chuyển phát theo cơ chế xác thực callback.

Nếu dùng transactional outbox, việc lưu challenge và công việc gửi có thể cùng một giao dịch cơ sở dữ liệu. Outbox giúp tránh mất công việc sau commit nhưng không bảo đảm phía người nhận chỉ nhận đúng một thông điệp.

Một verifier HMAC không cho phép tái dựng bí mật để gửi lại. Nếu dispatcher cần truy cập bí mật sau commit, phải có thiết kế riêng, chẳng hạn payload được mã hóa với quản lý khóa, quyền truy cập và thời gian lưu rất hạn chế. Payload mã hóa vẫn là dữ liệu nhạy cảm, không được đưa vào log hoặc giữ lâu như audit thông thường.

Trong trường hợp đó, bí mật gốc chỉ xuất hiện tại các điểm cần giải mã để gửi; bảng challenge vẫn chỉ lưu verifier. Không dùng nhu cầu retry làm lý do lưu OTP dạng rõ lâu dài.

Dispatcher cũng cần xử lý công việc đã cũ. Nếu challenge bị thay thế hoặc hết hạn, chính sách gửi phải ngăn hoặc xử lý thông điệp trễ phù hợp. Không tự chuyển người nhận sang challenge khác chỉ vì một công việc cũ đang được retry.

## 11. Retry sau thành công không được tạo thêm quyền

Một tình huống thường gặp:

1. Máy chủ tiêu thụ challenge và ghi bằng chứng thành công.
2. Giao dịch commit.
3. Kết nối bị mất trước khi client nhận phản hồi.
4. Client gửi lại cùng thao tác.

Challenge lúc này đã CONSUMED. Không xác minh bí mật thêm một lần rồi tạo bằng chứng hoặc grant mới.

Nếu có hỗ trợ idempotency, khóa idempotency phải gắn với đúng người hoặc ngữ cảnh được phép tiếp tục, request và loại thao tác. Bản ghi kết quả cần được phối hợp với giao dịch tiêu thụ để retry có thể nhận lại kết quả được phép xem.

Biết challengeId hoặc khóa idempotency không mặc nhiên cấp quyền lấy một grant. Việc trả lại kết quả nhạy cảm vẫn phải kiểm tra quyền của người gọi và giới hạn hiệu lực.

Nếu không thể khôi phục cùng kết quả một cách an toàn, cung cấp cách tra cứu hoặc tiếp tục đã được thiết kế cho giao dịch đó. Không đặt state trở lại ISSUED để “sửa” một lỗi phản hồi mạng.

Bản ghi bằng chứng cũng cần giới hạn sử dụng ở cấp điều phối. Một challenge đã tiêu thụ chỉ tạo một bằng chứng không có nghĩa bằng chứng đó được phép dùng cho vô số request khác.

## 12. Mở rộng cho passkey, TOTP và xác minh thủ công

Phần schema phía trên không nên được mở rộng bằng cách nhét mọi loại bí mật vào verifierMac.

| Loại bằng chứng | Dữ liệu chuyên biệt cần quan tâm |
| --- | --- |
| OTP do máy chủ cấp | Verifier, đích gửi, thời hạn, lượt thử và generation |
| URL token | Token đủ entropy, phạm vi sử dụng, verifier và tiêu thụ một lần |
| Passkey/WebAuthn | Challenge của giao thức, credential hợp lệ, origin, RP ID và kết quả kiểm tra giao thức |
| TOTP của phương thức đã đăng ký | Tham chiếu authenticator, cửa sổ thời gian và trạng thái chống dùng lại ở authenticator |
| Xét duyệt danh tính thủ công | Tham chiếu hồ sơ bằng chứng, quyết định có thẩm quyền và nguồn gốc quyết định |

Đối với passkey, có một chuỗi challenge trùng khớp chưa đủ để chấp nhận assertion; vẫn cần toàn bộ việc kiểm tra giao thức và chính sách của phương thức xác thực.

Đối với TOTP, cần ngăn cùng một mã hoặc bước thời gian được chấp nhận qua các request cạnh tranh ở phạm vi authenticator thích hợp. Một bộ đếm trên từng recovery challenge riêng lẻ không tự giải quyết việc dùng lại TOTP giữa các luồng.

Đối với hỗ trợ thủ công, nhân viên không được đặt một cột “verified” mà thiếu bằng chứng quyết định, phạm vi và kiểm soát quyền. Tài liệu định danh nên nằm trong hệ thống lưu trữ được bảo vệ tương ứng, không nằm trong một trường JSON tùy ý của challenge.

Có thể dùng một phần vòng đời chung và các bảng chi tiết theo proofType. Các trường cần ràng buộc chặt nên có kiểu và quy tắc rõ; JSON mở rộng không được trở thành nơi ghi đè purpose, accountId, state hoặc thời hạn mà bỏ qua kiểm soát.

## 13. Dữ liệu lưu trữ và dữ liệu được công bố là hai hợp đồng

Một API trả trạng thái challenge không nên serialize nguyên entity cơ sở dữ liệu.

Phản hồi tối thiểu có thể gồm trạng thái hiển thị, mốc thời gian cần thiết và hành động được phép trình bày trong ngữ cảnh đã được xác định. Không trả verifierMac, verifierKeyId, đích gửi đầy đủ, chi tiết chính sách rủi ro hoặc định danh nội bộ không cần thiết.

Các lỗi như không tìm thấy challenge, đã hết hạn hoặc không khớp tài khoản cần có cách phản hồi phù hợp để tránh dò dữ liệu. Phân loại nội bộ có thể chi tiết hơn nội dung công khai.

Audit nên tập trung vào sự kiện cấp, lần thử thất bại, khóa, thu hồi và tiêu thụ, cùng định danh tham chiếu và thời điểm. Không ghi submittedSecret hoặc toàn bộ request body.

Với schema minh họa đang yêu cầu verifierMac không rỗng, việc xóa challenge phải theo chính sách retention và quan hệ tham chiếu đã thiết kế. Nếu cần giữ metadata nhưng loại bỏ verifier sớm hơn, phải thiết kế mô hình lưu trữ và ràng buộc cho trường hợp đó; không đơn giản gán NULL trái với schema.

Xóa dữ liệu xác minh nhạy cảm và giữ bằng chứng tối thiểu phục vụ điều tra là những nhu cầu cần phối hợp. Không mặc định giữ mọi bản ghi, payload và bí mật mã hóa mãi chỉ vì chúng liên quan tới bảo mật.

## 14. Ví dụ xuyên suốt: thay MFA sau khi mất thiết bị

Hà mất điện thoại chứa ứng dụng MFA. Một request recovery được tạo theo chính sách của dịch vụ và có một requirement xác minh qua kênh được phép.

**Cấp challenge C1:** Máy chủ ghi requestId, accountId, purpose REPLACE_MFA, requirementKey, đích gửi và generation 1. Mã gốc đi qua đường gửi được bảo vệ; bảng challenge lưu verifier.

**Nhập sai:** Hai lần nhập sai được ghi tăng failedAttempts. Các cập nhật được phối hợp để không mất một lần tăng do hai máy chủ cùng xử lý.

**Cấp challenge C2:** Hà được phép yêu cầu mã mới. Giao dịch thu hồi C1, tạo C2 với generation 2 và chuyển tham chiếu hiện hành sang C2. Một lần xác minh đến muộn cho C1 không được tiêu thụ C1 nữa.

**Nhập đúng C2:** Hai lần gửi giống nhau tới hai máy chủ cạnh tranh. Giao dịch đầu tiên đủ điều kiện tiêu thụ C2 và ghi một bằng chứng. Giao dịch thứ hai đọc trạng thái đã kết thúc, không tạo bằng chứng thứ hai.

**Đánh giá ở request:** Bằng chứng này được đối chiếu với các yêu cầu khác. Nếu chính sách còn yêu cầu một bước độc lập, Hà phải hoàn tất bước đó trước khi nhận quyền thay MFA.

**Kết thúc:** Khi việc thay MFA thực sự hoàn tất, hệ thống xử lý các challenge và grant còn lại theo chính sách. Việc thu hồi session, liên kết recovery khác và thông báo bảo mật được quản lý ở phạm vi tương ứng, không bị suy ra từ riêng trạng thái CONSUMED của C2.

Một recovery challenge entity có ích khi nó gắn bằng chứng với đúng ngữ cảnh, giữ hạn dùng và lượt thử đáng tin, đồng thời cho phép tiêu thụ nguyên tử. Ranh giới đó giúp hệ thống phân biệt rõ “đã chấp nhận một bằng chứng” với “đã cho phép và hoàn tất khôi phục tài khoản”.
