# Test authentication policy trong vòng đời danh tính IAM

## 1. Mục tiêu và phạm vi

**Authentication policy** là tập quy tắc xác định **ai được xác thực, bằng phương thức nào, trong điều kiện gì và khi nào cần tăng mức xác minh**. Những quy tắc này thường do Identity Provider (IdP), hệ thống Single Sign-On (SSO), cổng VPN, ứng dụng hoặc một tầng điều khiển truy cập thực thi. Kiểm thử authentication policy phải chứng minh người dùng hợp lệ đăng nhập được với cơ chế cần thiết và các trường hợp không đáp ứng chính sách bị chặn.

Trong module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`, vòng đời Joiner–Mover–Leaver làm thay đổi điều kiện đăng nhập: Joiner chỉ được kích hoạt sau xác minh và ngày hiệu lực; Mover có thể cần MFA mạnh hơn hoặc hạn chế truy cập theo vai trò mới; Leaver phải bị chặn đăng nhập và xử lý phiên cũ. Kiểm thử phải liên kết trạng thái HRIS/IAM với IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và dấu vết kiểm toán để giảm quyền truy cập tồn dư.

**Phân biệt hai lớp kiểm soát:**

- **Authentication (AuthN):** chứng minh chủ thể là ai, ví dụ mật khẩu kết hợp MFA, passkey hoặc xác thực chứng chỉ.
- **Authorization (AuthZ):** sau khi xác thực, quyết định chủ thể có quyền thực hiện thao tác trên tài nguyên hay không.

Đăng nhập SSO thành công không đồng nghĩa có quyền xem dữ liệu nhạy cảm. Ngược lại, một tài khoản đã bị khóa không thể được đánh giá chỉ bằng cách xem nhóm RBAC; cần thử đăng nhập mới và đường truy cập đang tồn tại.

## 2. Chuyển quy tắc thành oracle kiểm thử

Để xây dựng testcase, nhóm IAM phải có **policy baseline** được phê duyệt và thông số triển khai thực tế: nhóm người dùng, loại thiết bị, vị trí truy cập, phương thức xác thực, mức rủi ro, ngày hiệu lực, chính sách phiên và xử lý ngoại lệ.

Ví dụ chính sách giả định:

| Ngữ cảnh | Yêu cầu AuthN | Kết quả khi không đáp ứng |
|---|---|---|
| Nhân viên active, ứng dụng nội bộ thông thường | SSO và MFA theo policy hiện hành | Chặn hoặc yêu cầu thêm yếu tố |
| Truy cập chức năng quản trị | MFA chống phishing hoặc cơ chế mạnh được phê duyệt | Không cấp phiên quản trị |
| Thiết bị không được quản lý | Điều kiện trust thiết bị trước truy cập nhạy cảm | Chặn hoặc giới hạn theo policy |
| Rủi ro đăng nhập cao | Step-up, xác minh bổ sung hoặc chặn | Không cho vượt kiểm soát |
| Nhân viên chưa tới ngày hiệu lực | Không cấp truy cập sử dụng | Từ chối ngay cả khi account được provision sớm |
| Tài khoản bị suspend/terminated | Chặn đăng nhập mới | Không phát hành phiên mới |
| Service principal | Workload identity, certificate hoặc key được kiểm soát | Không dùng luồng MFA tương tác của người |

Các ví dụ chỉ thể hiện **cách lập oracle**, không quy định bắt buộc mọi tổ chức phải áp dụng cùng một phương thức MFA. Với mỗi testcase, ghi policy ID/version và nguyên nhân kỳ vọng ALLOW, CHALLENGE hoặc DENY. Không gán hành vi cố định cho mọi loại ứng dụng khi kiến trúc hỗ trợ session, token và chính sách khác nhau.

~~~text
if identity.status not in allowedIdentityStates:
    decision = DENY
elif now < identity.effectiveAt:
    decision = DENY
elif not satisfies(requiredAuthenticationStrength, authenticationContext):
    decision = CHALLENGE_OR_DENY
elif not satisfies(deviceAndRiskConditions):
    decision = CHALLENGE_OR_DENY
else:
    decision = ALLOW_AUTHENTICATION

# Quyết định tài nguyên được thực hiện riêng bằng authorization policy.
~~~

Các trạng thái, mức assurance và nhánh xử lý thách thức cần ánh xạ sang IdP đang sử dụng. Nếu thiếu thuộc tính bắt buộc, test cần kiểm tra xử lý an toàn theo baseline, thường là không cho truy cập nhạy cảm khi chưa xác định được điều kiện.

## 3. Luồng kiểm thử end-to-end

~~~mermaid
flowchart TD
    U[Người dùng / workload] --> R[Yêu cầu đăng nhập]
    R --> I[IdP: xác định identity và trạng thái]
    I --> C[Đánh giá context: risk, device, location, app]
    C --> P[Authentication policy]
    P -->|Từ chối| D[DENY + audit]
    P -->|Cần tăng mức| M[MFA / step-up]
    M -->|Không đạt| D
    M -->|Đạt| S[Phát hành phiên / token]
    P -->|Đủ điều kiện| S
    S --> A[Ứng dụng xác thực token/session]
    A --> Z[Authorization theo RBAC / ABAC]
    Z --> T[Kiểm tra hành động ALLOW / DENY]
    T --> L[Audit, readback, đo SLA]
~~~

Quan sát ở bốn điểm: **nguồn danh tính** (HRIS/IAM status), **quyết định IdP** (policy đánh giá ra sao), **trạng thái phiên/token** (có thực sự được phát hành hay không) và **điểm thực thi ứng dụng** (request có được chấp nhận không). Nếu điều kiện áp dụng chính sách thay đổi ở Mover/Leaver, kiểm tra cả phiên đã tồn tại.

## 4. Test fixture và môi trường

Tạo danh tính giả cho các nhóm: Joiner chưa đến ngày bắt đầu, nhân viên active, quản trị viên đặc quyền, người dùng đổi phòng ban, contractor hết hạn, suspended, Leaver, người có ngoại lệ tạm thời và workload identity. Chuẩn bị ít nhất một tài nguyên thông thường và một tài nguyên nhạy cảm để đo tác động của chính sách.

Với thiết bị/ngữ cảnh, chuẩn bị các trạng thái được quản lý, không quản lý, compliant, non-compliant, risk thấp/cao và nhiều nguồn mạng theo khả năng của test tenant. Điều kiện rủi ro địa lý hoặc thiết bị chỉ nên mô phỏng bằng chức năng test được hỗ trợ; không cần sử dụng mạng hay tài khoản sản xuất.

Mỗi testcase có:

| Trường | Mục đích |
|---|---|
| `caseId`, `identityId` | Truy vết testcase và danh tính giả |
| `policyId`, `policyVersion` | Ràng buộc kết quả với phiên bản chính sách |
| `lifecycleState`, `effectiveAt` | Tình trạng Joiner/Mover/Leaver |
| `appId`, `resource` | Đích được bảo vệ |
| `authMethod`, `mfaContext` | Cách xác thực và bằng chứng assurance |
| `deviceContext`, `riskContext` | Thuộc tính thiết bị và rủi ro |
| `expectedDecision` | ALLOW, CHALLENGE hoặc DENY |
| `actualDecision`, `observedAt` | Kết quả và thời điểm |
| `evidence`, `correlationId` | Log và chứng cứ kiểm tra |

Không đưa mật khẩu, OTP, private key, refresh token hoặc access token nguyên văn vào báo cáo. Nếu phải dùng credentials thử nghiệm, lưu trong secret manager và dùng tài khoản có phạm vi cô lập.

## 5. Kiểm thử chính sách theo vòng đời JML

### Joiner

Người mới có thể được provision account trước ngày bắt đầu để chuẩn bị công cụ làm việc. Test phải kiểm tra tính **tách biệt giữa account tồn tại và khả năng đăng nhập**. Trước `effectiveAt`, đăng nhập bị chặn theo chính sách. Sau khi HR xác minh, đến ngày hiệu lực và hoàn tất các điều kiện bắt buộc, người dùng mới được bắt đầu phiên phù hợp.

Thử thiếu xác minh, không có phê duyệt, lời mời kích hoạt đã hết hạn, tài khoản chưa thiết lập MFA và email trùng. Không được bỏ qua bước xác minh chỉ vì SCIM đã tạo user thành công.

### Mover

Khi chuyển từ vai trò thường sang quản trị, authentication strength có thể phải tăng. Test xác nhận **step-up** thực sự diễn ra trước hành động nhạy cảm, kể cả khi người dùng đã có session SSO ở mức assurance thấp. Khi giảm quyền, kiểm tra session có claim cũ không tiếp tục cho phép hành động vượt phạm vi.

Thay đổi `department`, `region`, `deviceTrust` hoặc nhóm chính sách có thể làm thay đổi yêu cầu đăng nhập. Kiểm tra sự kiện ngoài thứ tự không làm phục hồi policy cũ sau khi trạng thái mới được áp dụng.

### Leaver

Sau sự kiện Leaver hợp lệ và đúng thời điểm, mọi đăng nhập tương tác mới bị từ chối. Test riêng với mật khẩu, passkey, MFA và SSO từ ứng dụng đang liên kết. Thử dùng session, refresh token và access token đã cấp trước Leaver; xác minh chúng được xử lý theo kiến trúc thu hồi và SLA, không giả định disable IdP tức thời vô hiệu mọi JWT.

Nếu Leaver xảy ra trước khi một event Joiner/Mover cũ được xử lý, hệ thống không được cấp lại quyền hoặc phát hành session cho danh tính đã chấm dứt.

## 6. Kiểm thử phương thức xác thực và MFA

Các nhóm kiểm thử cần đánh giá chính xác thứ tự yêu cầu yếu tố và kết quả khi thất bại:

| ID | Tình huống | Kỳ vọng |
|---|---|---|
| A01 | Đăng nhập với phương thức được cho phép | ALLOW khi mọi điều kiện được đáp ứng |
| A02 | Sai mật khẩu hoặc bằng chứng xác thực | DENY, không tạo session |
| A03 | Cần MFA nhưng chưa đăng ký | Chặn hoặc hướng dẫn đăng ký an toàn theo policy |
| A04 | MFA sai, hết hạn, thử lại nhiều lần | Không cấp token; giới hạn thử theo policy |
| A05 | MFA thành công nhưng risk/device không đạt | Không bỏ qua điều kiện khác |
| A06 | Quản trị viên dùng phương thức assurance thấp | Yêu cầu step-up hoặc DENY |
| A07 | MFA ngoại lệ tạm thời hết hạn | Không tiếp tục sử dụng ngoại lệ |
| A08 | Recovery/reset MFA | Bảo đảm xác minh chủ thể và audit tương ứng |
| A09 | MFA đã đạt trong session cũ | Step-up nếu tài nguyên yêu cầu assurance cao hơn |
| A10 | Tài khoản bị suspended sau khi đăng nhập | Phiên bị giới hạn hoặc thu hồi trong SLA |

**Chống phishing** và **MFA thông thường** là những mức bảo vệ khác nhau. Nếu chính sách yêu cầu phương thức mạnh như khóa bảo mật hoặc passkey phù hợp, OTP qua SMS không được mặc nhiên được coi tương đương. Thực thi cụ thể phụ thuộc IdP và bộ chính sách được phê duyệt.

Trong kiểm thử recovery, tránh tiết lộ danh tính có hay không bằng thông báo lỗi quá chi tiết; đánh giá cả rate limiting, khóa tạm và audit. Không viết test tự động làm khóa hàng loạt tài khoản thật.

## 7. Conditional access: thiết bị, mạng và rủi ro

Conditional access thường kết hợp trạng thái danh tính, thiết bị, nguồn mạng, ứng dụng, loại tài nguyên và tín hiệu rủi ro. Xây dựng bảng quyết định để kiểm tra từng điều kiện và các tổ hợp:

| Identity | Thiết bị | Risk | Ứng dụng | Kỳ vọng minh họa |
|---|---|---|---|---|
| Active | Compliant | Low | App thường | ALLOW khi AuthN đủ |
| Active | Unmanaged | Low | App nhạy cảm | DENY hoặc truy cập hạn chế |
| Active | Compliant | High | App nhạy cảm | Step-up hoặc DENY |
| Admin | Compliant | Low | Admin console | Yêu cầu assurance mạnh |
| Suspended | Compliant | Low | Bất kỳ | DENY |
| Terminated | Compliant | Low | Bất kỳ | DENY |

Đây là ma trận ví dụ để kiểm thử policy, không phải quy tắc chung của mọi tổ chức. Với dữ liệu rủi ro thiếu hoặc thay đổi giữa luồng đăng nhập, kiểm tra IdP xử lý nhất quán và không vô tình fail-open cho tài nguyên nhạy cảm.

Thử cả phiên SSO đã được tạo trước khi thiết bị trở thành non-compliant. Nếu kiến trúc chỉ tái đánh giá tại thời điểm tạo session hoặc khi refresh, kiểm chứng deadline hội tụ và các biện pháp hạn chế bổ sung theo policy.

## 8. SSO, token và session policy

Đối với SSO, kiểm thử ID token/access token hoặc assertion theo đúng giao thức ứng dụng sử dụng. Với OIDC, các kiểm tra cơ bản ở resource/client phù hợp bao gồm issuer, audience, chữ ký, thời hạn `exp`, thời điểm `nbf` nếu có, nonce/state ở luồng liên quan và claim chính sách. Với SAML, cần kiểm tra điều kiện chữ ký, audience, recipient, thời gian và replay protection theo profile sử dụng.

Các test quan trọng:

1. Token hợp lệ từ đúng issuer/audience được chấp nhận trong thời hạn.
2. Token hết hạn, chưa có hiệu lực, sai audience hoặc issuer bị từ chối.
3. Session bị giới hạn bởi idle timeout và absolute timeout theo policy.
4. Refresh token rotation/revocation không cho phép kéo dài phiên trái quy định.
5. Logout và back-channel/front-channel logout (nếu hỗ trợ) làm mất quyền sử dụng phiên tương ứng.
6. Sau thay đổi trạng thái JML, phiên/token cũ bị hạn chế theo SLA; cần dùng token thật tại API để kiểm tra.
7. Khi IdP gián đoạn, failover không được bỏ qua điều kiện bảo mật quan trọng.

**Cảnh báo kỹ thuật:** JWT tự chứa vẫn có thể được resource server chấp nhận tới hết hạn khi server chỉ kiểm chữ ký và claim. Nếu cần thu hồi sớm, kiến trúc phải hỗ trợ cách kiểm tra trạng thái hiện hành hoặc TTL phù hợp. Test phải phản ánh đặc điểm đó, không kết luận chỉ dựa trên `account.disabled=true`.

## 9. Kiểm thử đối tượng đặc biệt và tài khoản dịch vụ

Service account, workload identity và machine-to-machine flow thường **không có tương tác MFA như người dùng**. Kiểm thử authentication policy của chúng qua chứng chỉ, client credentials, workload federation, quyền sử dụng khóa, thời hạn token và secret rotation.

Các trường hợp cần có: secret hết hạn, certificate sai hoặc revoked, workload sai audience, yêu cầu từ môi trường không được tin cậy, service principal thiếu owner hoặc quyền gọi bị thu hồi. Khi owner là nhân sự Mover/Leaver, test phải xác minh quyền quản trị secret của người đó bị gỡ và owner mới được phê duyệt; không tự động tắt ứng dụng đang vận hành nếu chưa có kế hoạch.

Với break-glass account, kiểm tra policy ngoại lệ theo thiết kế đã duyệt: ghi log, giám sát, yêu cầu thủ tục khôi phục và phạm vi sử dụng. Không coi ngoại lệ là cách bỏ qua toàn bộ authentication policy.

## 10. Ma trận kiểm thử tổng hợp

| Case | Biến cố | Kỳ vọng | Độ ưu tiên |
|---|---|---|---|
| T01 | Joiner chưa tới ngày hiệu lực | Không đăng nhập được | Rất cao |
| T02 | Joiner đủ điều kiện, thiết lập MFA đúng | Được cấp session phù hợp | Cao |
| T03 | Mover thành admin, session assurance thấp | Step-up trước quyền nhạy cảm | Rất cao |
| T04 | Mover giảm role, token chứa claim cũ | Không có hành động vượt quyền sau SLA | Rất cao |
| T05 | Leaver: mật khẩu và SSO mới | Không phát hành session mới | Rất cao |
| T06 | Leaver: refresh/access token cũ | Không truy cập quá deadline đã phê duyệt | Rất cao |
| T07 | Tài khoản suspended | AuthN bị chặn theo policy | Rất cao |
| T08 | MFA thất bại/hết hạn | Không phát session/token | Cao |
| T09 | Yêu cầu phishing-resistant MFA | Phương thức yếu không đạt yêu cầu | Rất cao |
| T10 | Thiết bị không compliant | Quyết định theo conditional policy | Cao |
| T11 | Rủi ro cao và thuộc tính thiếu | Không fail-open vượt baseline | Rất cao |
| T12 | Event Mover cũ sau Leaver | Không kích hoạt lại tài khoản | Rất cao |
| T13 | Break-glass theo ngoại lệ duyệt | Đúng phạm vi, audit đầy đủ | Cao |
| T14 | Workload credential sai/hết hạn | Không cấp token M2M | Cao |
| T15 | IdP policy thay đổi khi session còn sống | Enforcement và timeout đúng SLA | Cao |

Mỗi test lưu kết quả thực tế cùng policy ID/version và correlation ID; phải phân biệt lỗi AuthN với DENY do AuthZ để xác định lớp cần sửa.

## 11. Ví dụ tự động hóa kiểm thử

Ví dụ mã giả Python cho các testcase trạng thái JML và MFA. Các client, time controller và `eventually` do test harness hiện thực:

~~~python
def test_authentication_policy_jml(hris, idp, app, policy):
    user_id = "test-person-808"
    hris.set_status(user_id, "ACTIVE")
    idp.set_test_context(user_id, device="COMPLIANT", risk="LOW")

    # Đăng nhập đủ MFA được cho phép.
    session = idp.test_sign_in(user_id, auth_method="APPROVED_MFA")
    assert session.allowed
    assert app.call_with_session(session, "profile.read").allowed

    # Step-up cho tác vụ nhạy cảm.
    admin_attempt = idp.test_sign_in(
        user_id, auth_method="PASSWORD_ONLY", resource="admin.console"
    )
    assert admin_attempt.challenge_required or admin_attempt.denied

    # Chấm dứt quan hệ: đăng nhập mới bị chặn.
    hris.publish({
        "eventId": "leave-808-v9", "version": 9,
        "personId": user_id, "type": "LEAVER",
        "effectiveAt": policy.test_effective_at,
    })
    eventually(
        lambda: idp.is_disabled(user_id),
        timeout_seconds=policy.disable_sla_seconds,
    )
    assert idp.test_sign_in(user_id, auth_method="APPROVED_MFA").denied
    eventually(
        lambda: app.call_with_session(session, "profile.read").denied,
        timeout_seconds=policy.session_revoke_sla_seconds,
    )
~~~

Đây là pseudocode; test harness phải bảo đảm đã đến thời điểm `effectiveAt`, tuân thủ policy, không dựa hoàn toàn vào mock và dùng dữ liệu giả. Khi step-up yêu cầu chọn phương thức cụ thể, assertion phải khớp response của IdP trong tổ chức thay vì dùng chung mọi trạng thái.

## 12. Audit, vận hành và tiêu chí PASS

Một testcase authentication policy có thể được xem là đạt khi **quyết định AuthN đúng rule**, bằng chứng MFA/assurance đúng, session/token phát hành hoặc bị từ chối phù hợp, kết quả tại ứng dụng phản ánh chính sách, và sự thay đổi JML được áp dụng trong SLA.

Nhật ký nên chứa: subject ID giả, policy ID/version, correlation ID, thời điểm, phương thức (không ghi bí mật), risk/device context cần thiết, kết quả allow/challenge/deny, nguồn sự kiện lifecycle và lỗi liên quan. Hạn chế ghi thông tin cá nhân hoặc tín hiệu thiết bị quá chi tiết không cần thiết.

Khi policy engine trả DENY nhưng ứng dụng vẫn chấp nhận session cũ, báo lỗi **enforcement** hoặc **session revocation** thay vì kết luận toàn bộ authentication policy đã đạt. Khi sự kiện HRIS đã cập nhật mà IdP vẫn coi account active, báo lỗi đồng bộ lifecycle. Reconciliation, retry và alert phải giúp khoanh vùng sự khác biệt giữa policy mong muốn và trạng thái quan sát.

## 13. Bài thực hành

Giả lập nhân viên `test-person-808` có account trên IdP, dùng SSO vào một ứng dụng thông thường và cổng quản trị. Ban đầu là nhân viên active với MFA đã đăng ký; sau đó chuyển sang vai trò quản trị và cuối cùng nghỉ việc.

1. Thiết kế policy cho app thường, admin console, thiết bị compliant/non-compliant và mức risk cao/thấp.
2. Thử đăng nhập bằng phương thức được duyệt và phương thức assurance thấp; xác minh yêu cầu step-up tại admin console.
3. Chuyển người dùng sang vai trò quản trị; thử sử dụng session mức thấp được tạo trước Mover.
4. Đánh dấu thiết bị non-compliant khi session đang hoạt động và đo thời điểm điều kiện policy được thực thi.
5. Phát hành session/token thử trước Leaver; sau Leaver kiểm tra đăng nhập mới, refresh token, session hiện hữu trong SLA.
6. Gửi một event Mover cũ sau Leaver; chứng minh không phát hành session cho danh tính đã chấm dứt.
7. Tổng hợp `caseId, policyVersion, identityState, authContext, expected, actual, observedAt, deadline, evidence, outcome`.

Phân biệt trong báo cáo lỗi ở HRIS/IAM, quyết định policy của IdP, phát hành token và enforcement tại ứng dụng. Kiểm thử authentication policy đạt mục tiêu khi đúng danh tính được xác thực với mức bảo đảm phù hợp ở đúng thời điểm, còn danh tính hoặc ngữ cảnh không hợp lệ bị chặn một cách có thể chứng minh và kiểm toán.
