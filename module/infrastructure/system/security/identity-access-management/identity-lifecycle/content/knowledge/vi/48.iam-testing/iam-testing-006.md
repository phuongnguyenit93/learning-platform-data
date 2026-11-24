# Kiểm thử deprovisioning trong IAM

## 1. Deprovisioning là gì?

**Deprovisioning** là quá trình thu hồi tài khoản, quyền, phiên truy cập và thông tin xác thực khi chúng không còn được phép sử dụng. Trong quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, deprovisioning xuất hiện rõ nhất lúc người dùng nghỉ việc (**Leaver**), nhưng cũng cần thực hiện khi người dùng đổi phòng ban hoặc giảm chức vụ (**Mover**), nhà thầu hết hợp đồng, quyền đặc biệt hết hạn hoặc ứng dụng không còn được phép dùng.

Với hệ thống IAM tích hợp **HRIS, IdP, SSO, SCIM, RBAC/ABAC**, kiểm thử deprovisioning phải đánh giá từ sự kiện nguồn đến **khả năng truy cập thực tế tại ứng dụng**. Lệnh xóa nhóm thành công, trạng thái `active=false` hoặc tài khoản IdP bị khóa chỉ là những bằng chứng trung gian: một phiên đang hoạt động, token cũ, tài khoản ứng dụng cục bộ hoặc API key vẫn có thể tạo truy cập tồn dư.

Mục tiêu của bài kiểm thử:

- Thu hồi đúng danh tính và entitlement sau khi điều kiện cấp quyền không còn hiệu lực.
- Chặn cả **đăng nhập mới** và những **đường truy cập đang tồn tại** theo chính sách và SLA cụ thể.
- Không thu hồi nhầm quyền hoặc xóa dữ liệu của người khác khi mapping ID sai.
- Xử lý lỗi từng phần, yêu cầu lặp, sự kiện đến muộn và hệ thống đích không sẵn sàng.
- Giữ được dữ liệu, quyền sở hữu và bằng chứng phục vụ bàn giao, kiểm toán.
- Phát hiện và xử lý quyền tồn dư bằng reconciliation.

## 2. Phạm vi thu hồi: tài khoản, entitlement và credential

Phân biệt ba hành động:

| Hành động | Ý nghĩa | Cách xác minh |
|---|---|---|
| **Disable/suspend** | Ngăn tài khoản xác thực hoặc sử dụng theo chính sách, có thể khôi phục | Thử đăng nhập, kiểm tra trạng thái và access enforcement |
| **Revoke entitlements** | Gỡ nhóm, vai trò, quyền trực tiếp, quyền theo thuộc tính | So sánh quyền kỳ vọng và quyền có hiệu lực, thử API |
| **Delete/archive** | Xóa hoặc lưu trữ đối tượng theo chính sách dữ liệu | Kiểm tra retention, tài sản liên quan và dấu vết audit |

Đừng đồng nhất xóa tài khoản với thu hồi quyền. Nhiều tổ chức giữ tài khoản ở trạng thái vô hiệu để bảo toàn email, tài sản, lịch sử giao dịch và chứng cứ. Việc xóa dữ liệu chỉ được thực hiện nếu phù hợp chính sách lưu giữ.

Các đường truy cập cần liệt kê cho mỗi danh tính:

1. IdP/Directory, SSO và MFA.
2. Tài khoản SaaS qua SCIM hoặc connector riêng.
3. Nhóm trực tiếp, nhóm lồng nhau, role RBAC, điều kiện ABAC.
4. Role cục bộ, ACL chia sẻ tài liệu, phân quyền dự án và quyền ứng dụng độc lập.
5. Cookie phiên, access token, refresh token, personal access token (PAT).
6. API key, SSH key, certificate, VPN, VDI và tài khoản local.
7. Quyền quản lý secret, service account, máy chủ, repository, CI/CD và bot.

Không phải đường nào cũng hỗ trợ revoke tức thời. Test phải thể hiện rõ **giới hạn kỹ thuật và deadline được phê duyệt**, tránh tuyên bố đã thu hồi ngay chỉ vì gửi lệnh thành công.

## 3. Nguồn sự kiện và thời điểm hiệu lực

Một sự kiện thử có thể mang cấu trúc:

~~~yaml
eventId: offboard-person-505-v19
eventVersion: 19
eventType: LEAVER
personId: test-person-505
source: HRIS
employmentStatus: TERMINATED
effectiveAt: 2026-12-18T18:00:00+07:00
terminationMode: PLANNED
approvedBy: test-hr-approver
~~~

Đây là dữ liệu giả định, không phải schema bắt buộc. Với quyền giảm bớt khi Mover, sự kiện có thể chỉ yêu cầu thu hồi một tập entitlement mà vẫn giữ tài khoản active. Do đó test phải biết **scope thu hồi**.

Các đồng hồ quan trọng:

- `effectiveAt`: thời điểm quyền không còn được phép.
- `receivedAt`: lúc IAM nhận sự kiện.
- `executionAt`: lúc lệnh thu hồi gửi đi.
- `observedAt`: thời điểm quyền thực tế bị chặn.
- `deadlineAt`: mốc yêu cầu theo SLA của loại quyền và mức rủi ro.

Với Leaver khẩn cấp, chính sách có thể yêu cầu chặn truy cập ngay khi có xác nhận hợp lệ, trước khi hoàn thành việc bàn giao. Với nghỉ việc có kế hoạch, việc khóa sớm hơn ngày hiệu lực cũng có thể là lỗi nếu cản trở công việc hợp lệ.

## 4. Luồng deprovisioning và các điểm chốt

~~~mermaid
flowchart TD
    A[HRIS hoặc request được ủy quyền] --> B[Kiểm tra subject ID, event version, effectiveAt]
    B --> C[Phân loại Leaver, Mover, expiry, emergency]
    C --> D[Chặn đăng nhập / điều kiện truy cập]
    D --> E[Revoke session và credential theo chính sách]
    E --> F[Gỡ role, group, ACL, direct grants]
    F --> G[SCIM / connector tới từng ứng dụng]
    G --> H[Readback account và effective access]
    H --> I{Tất cả đích đạt SLA?}
    I -->|Có| J[Audit, handover, hoàn tất]
    I -->|Không| K[Alert, retry, reconciliation]
    K --> H
~~~

Một số bước có thể song song; ví dụ ứng dụng cần revoke session ngay trong khi SCIM deactivation còn chạy. Kiểm thử cần xác định điều kiện hoàn thành **theo từng target**, không đánh đồng một `HTTP 204` ở IdP với việc toàn hệ thống hoàn tất.

| Lớp | Dữ liệu kỳ vọng | Bằng chứng |
|---|---|---|
| HRIS/IAM | Sự kiện có căn cứ, đúng người và phiên bản | Event log và correlation ID |
| IdP | Không cho đăng nhập khi mất điều kiện | Thử SSO/IdP sign-in |
| Directory | Gỡ membership không hợp lệ | Query nhóm và quyền kế thừa |
| SCIM | User inactive hoặc đúng trạng thái contract | GET User, Groups, kiểm tra quyền |
| SaaS nội bộ | Không còn direct grants và role nội bộ | API access test và admin readback |
| Session/token | Thu hồi/hết hiệu lực theo deadline | Replay phiên/token cũ với tài nguyên |
| Credential | Key/secret cũ bị từ chối sau xử lý | Request thử hoặc xác minh rotation |
| Audit | Có thông tin từng bước và sai lệch | Audit trail, reconciliation report |

## 5. Ma trận testcase deprovisioning

| ID | Trường hợp | Kết quả kỳ vọng | Ưu tiên |
|---|---|---|---|
| D01 | Leaver theo lịch, đúng ngày | Thu hồi đúng thời điểm, không sớm và không quá hạn | Rất cao |
| D02 | Leaver khẩn cấp | Chặn truy cập ưu tiên cao trong deadline khẩn cấp | Rất cao |
| D03 | Mover giảm quyền | Chỉ gỡ quyền cũ, vẫn giữ quyền mới hợp lệ | Rất cao |
| D04 | Quyền tạm thời hết hạn | Role đặc quyền tự hết hiệu lực | Rất cao |
| D05 | Chặn IdP nhưng session SaaS vẫn sống | Phát hiện quyền truy cập tồn dư | Rất cao |
| D06 | Refresh token và access token cũ | Không tiếp tục truy cập quá SLA | Rất cao |
| D07 | Local account và PAT | Không còn đường truy cập ngoài SSO | Rất cao |
| D08 | Group lồng nhau hoặc direct ACL | Không còn effective grants bị cấm | Rất cao |
| D09 | SCIM timeout sau khi deactivate | Retry idempotent và readback đúng | Cao |
| D10 | Một target không sẵn sàng | Báo partial failure, alert và remediation | Cao |
| D11 | Gửi lặp cùng event | Không tái tạo quyền hoặc gây lỗi dữ liệu | Cao |
| D12 | Joiner/Mover cũ đến sau Leaver | Không kích hoạt lại tài khoản | Rất cao |
| D13 | Email đổi hoặc trùng tên | Không thu hồi nhầm người | Rất cao |
| D14 | Service account có owner rời tổ chức | Chuyển owner và gỡ quyền người cũ | Cao |
| D15 | Rehire sau chấm dứt | Chỉ cấp lại quyền theo phê duyệt hiện tại | Cao |
| D16 | Reconciliation thấy tài khoản mồ côi | Có finding, owner, hạn xử lý và readback | Cao |

Mỗi ca phải lưu `caseId`, precondition, event ID, expected grants, expected deny, target list, policy/SLA, actual grants, kết quả API, thời điểm quan sát và chứng cứ. Test âm tính đặc biệt quan trọng: sau thu hồi, **hành động bị cấm thật sự phải bị từ chối**.

## 6. Kiểm thử deactivation qua SCIM

SCIM 2.0 thường dùng thuộc tính `active` để biểu diễn trạng thái tài khoản. Ví dụ minh họa thao tác PATCH:

~~~http
PATCH /scim/v2/Users/user-505
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    { "op": "replace", "path": "active", "value": false }
  ]
}
~~~

Không phải mọi ứng dụng thực thi deactivation giống nhau: có nơi khóa đăng nhập nhưng giữ role; có nơi chỉ cập nhật một bản ghi provisioning mà không xóa session. Vì vậy **readback SCIM không thay được authorization test tại ứng dụng**.

Nhóm kiểm thử cần có:

- PATCH thành công rồi GET xác minh `active=false`.
- Deactivation user đã inactive: idempotent, không gây phát sinh quyền.
- `404 Not Found`: kiểm tra mapping externalId và quyền hiện có; chỉ coi là hoàn tất khi xác minh trạng thái thực tế.
- `429 Too Many Requests` và `5xx`: retry với backoff và ngân sách retry có giới hạn.
- Timeout khi server đã xử lý thành công: lookup trước khi retry, không tạo lại tài khoản.
- Sai externalId hoặc email trùng: phải chặn thao tác nhầm người.
- Group membership còn tồn tại: ứng dụng không còn cấp quyền hiệu lực hoặc cần gỡ nhóm theo chính sách.
- Connector không hỗ trợ SCIM: kiểm thử API/ticket thao tác thay thế và đọc lại trạng thái đích.

Việc xóa hoàn toàn User bằng DELETE không phải lúc nào cũng là hành vi mặc định thích hợp; chính sách retention và phụ thuộc dữ liệu phải quyết định hành động cuối.

## 7. Session, token và khả năng truy cập thực tế

Khi IdP disable tài khoản, đăng nhập mới qua SSO thường bị chặn, nhưng session hiện hữu ở ứng dụng có thể tiếp tục được chấp nhận. Một JWT access token tự chứa vẫn có thể hợp lệ cho tới khi hết hạn nếu resource server chỉ kiểm chữ ký, thời hạn và audience.

Thiết kế phép thử riêng:

1. Mở một session và phát access/refresh token **trước** khi deprovision.
2. Kích hoạt sự kiện và ghi thời điểm hiệu lực.
3. Thử đăng nhập mới từ IdP/SSO; phải bị từ chối theo SLA.
4. Dùng refresh token cũ xin token mới; kiểm chứng cơ chế revoke.
5. Gọi API nhạy cảm bằng access token cũ, cookie session cũ, token mới nếu có.
6. Poll tới deadline, ghi `lastAllowedAt` và `firstDeniedAt`.
7. Thử thao tác ghi và đọc tài nguyên, không chỉ tải trang tĩnh đã cache.

Nếu ứng dụng hỗ trợ revocation list, token introspection, back-channel logout hoặc giảm TTL, test cần xác minh hành vi đó. Nếu không hỗ trợ thu hồi tức thời, ghi rõ thời gian chấp nhận tối đa do kiến trúc và chính sách phê duyệt. Tránh xem một mã trạng thái cụ thể (`401` hoặc `403`) là tiêu chuẩn duy nhất; điều cốt lõi là request không thành công và tài nguyên không lộ.

## 8. Kiểm thử quyền RBAC, ABAC và đường cấp quyền gián tiếp

Một quyền có thể đến từ nhiều nguồn đồng thời. Ví dụ người dùng bị gỡ group `finance-admin` tại IdP nhưng còn thuộc group lồng nhau `regional-operators` hoặc có role nội bộ `report-exporter` ở SaaS. Khi đó effective access có thể còn tồn tại.

~~~text
expectedGrants = policy.evaluate(subject, stateAfterChange)
actualGrants = discoverEffectiveGrants(idp, apps, nestedGroups, directACLs)

unexpected = actualGrants - expectedGrants
missing = expectedGrants - actualGrants
~~~

Với Leaver, `expectedGrants` thông thường rỗng đối với truy cập tương tác; với Mover, chỉ những quyền không còn hợp lệ phải biến mất. Kiểm thử điều kiện ABAC theo `employmentStatus`, `department`, `region`, `contractEndAt` và cached claims. Khi source đã thay đổi nhưng token/PEP vẫn dùng thuộc tính cũ, phải đánh giá theo deadline và báo sai lệch nếu quyền tồn dư.

Kiểm tra quyền cấp trực tiếp, nhóm lồng nhau, ACL chia sẻ file, delegate access, quyền owner của repository/tài nguyên và quyền thông qua tài khoản dùng chung. Không dựa duy nhất vào membership tại IdP.

## 9. Idempotency, sự kiện đến muộn và lỗi từng phần

Một đường sự kiện điển hình:

~~~text
v18 MOVER: FINANCE -> SALES
v19 LEAVER: TERMINATED

Thứ tự xử lý: v19 trước, v18 đến sau.
Kỳ vọng: tài khoản vẫn TERMINATED; v18 không cấp lại SALES.
~~~

Sử dụng event version/sequence đáng tin cậy và đối chiếu nguồn trạng thái chuẩn. Thử replay Leaver nhiều lần, consumer restart trong lúc đang revoke, queue bị nghẽn và transaction đích hoàn tất nhưng mất response. **Idempotency** phải áp dụng cho trạng thái cuối và side effects, không chỉ cho số lượng request.

~~~mermaid
sequenceDiagram
    participant H as HRIS
    participant I as IAM
    participant D as IdP
    participant A as SaaS
    H->>I: LEAVER v19
    I->>D: Disable identity
    D-->>I: Success
    I->>A: Deactivate and revoke grants
    A--xI: Timeout
    I->>A: Read current state
    A-->>I: Inactive, role still assigned
    I->>A: Remove residual role
    A-->>I: Success
    I->>A: Test effective access
    A-->>I: DENY
~~~

Nếu một ứng dụng thất bại trong khi ứng dụng khác thành công, hệ thống phải báo trạng thái **PARTIAL_FAILURE/PENDING** hoặc trạng thái tương đương. Kiểm tra cảnh báo SLA, retry có giới hạn, dead-letter queue, khả năng replay an toàn và remediation có owner. Đừng coi workflow hoàn tất khi lỗi cuối chưa được đối soát.

## 10. Kiểm thử credentials độc lập và tài khoản dịch vụ

Thu hồi tài khoản con người có thể để lại các credential được cấp riêng. Cần liệt kê PAT Git, API key SaaS, SSH key máy chủ, VPN certificate, credentials local, mật khẩu chia sẻ, secret CI/CD và token tích hợp. Tạo dữ liệu thử phù hợp và xác minh các credential cũ không còn làm được hành động bị cấm sau deadline.

**Service account** thường vẫn cần hoạt động khi owner nghỉ việc. Test cần xác minh thay owner hợp lệ, gỡ quyền quản lý của người cũ, rotation secret nếu chính sách yêu cầu và kiểm tra bot/job vẫn chạy đúng. Không tự động xóa bot chỉ vì owner là Leaver; hành động đó có thể phá vỡ dịch vụ.

Trường hợp khó là một secret dùng chung đã từng được người nghỉ biết. Thu hồi quyền đọc vault không làm secret đã biết trở nên vô dụng; phải kiểm tra rotation và việc các hệ thống tiêu thụ đã chuyển sang credential mới.

## 11. Ví dụ kiểm thử tự động end-to-end

Đây là mã giả Python; `eventually`, client và policy được cung cấp bởi test harness. Bài kiểm thử cần chạy trên danh tính giả và môi trường an toàn:

~~~python
def test_deprovisioning_blocks_access(hris, iam, idp, crm, policy):
    person_id = "test-person-505"
    old_session = crm.open_test_session(person_id)
    old_token = crm.issue_test_access_token(person_id)
    event = {
        "eventId": "offboard-person-505-v19",
        "personId": person_id,
        "type": "LEAVER",
        "version": 19,
        "effectiveAt": policy.test_effective_at,
    }

    hris.publish(event)
    eventually(
        lambda: idp.is_disabled(person_id),
        timeout_seconds=policy.disable_sla_seconds,
    )
    eventually(
        lambda: crm.effective_permissions(person_id) == set(),
        timeout_seconds=policy.revoke_sla_seconds,
    )
    assert idp.try_new_sign_in(person_id).denied
    eventually(
        lambda: crm.request_with_session(old_session, "sensitive-report").denied,
        timeout_seconds=policy.session_sla_seconds,
    )
    eventually(
        lambda: crm.request_with_token(old_token, "sensitive-report").denied,
        timeout_seconds=policy.token_sla_seconds,
    )
    assert iam.audit_contains(event_id=event["eventId"])

    hris.publish(event)  # Replay.
    assert idp.count_by_person_id(person_id) == 1
~~~

Đây là ví dụ về cách tổ chức assertion, không phải mã chạy độc lập. Trong hệ thống thực, test phải đảm bảo sự kiện đã tới thời điểm hiệu lực; nếu test dùng đồng hồ giả thì phải đồng bộ đồng hồ giữa các thành phần. `request_with_session` và `request_with_token` cần gọi điểm thực thi thật, tránh mock cho kết quả DENY giả.

## 12. Audit, reconciliation và điều kiện hoàn tất

Bằng chứng cho mỗi yêu cầu nên gồm:

- **Intent:** nguồn sự kiện, person ID, thời điểm hiệu lực, phạm vi quyền cần thu hồi và phê duyệt.
- **Execution:** correlation ID, từng connector, thao tác disable/revoke, mã phản hồi, retry và lỗi.
- **Observed state:** tài khoản, direct/nested grants, trạng thái SSO, session, token và kết quả API.
- **Timeliness:** thời gian từ `effectiveAt` đến lúc từng đích không còn quyền, so với SLA.
- **Handover:** account/service ownership, tài sản, tài liệu, secret rotation và retention phù hợp.

Đối soát quyền tại đích phải phân biệt **inactive account vẫn còn dữ liệu để lưu trữ** với **active account chưa có người sở hữu**. Không tự động xóa dữ liệu công việc khi phát hiện tài khoản mồ côi. Mỗi sai lệch cần finding, mức độ ưu tiên, owner xử lý, deadline và readback sau remediation. Audit log tránh chứa password, private key hoặc access token.

Một test deprovisioning được xem là **PASS** khi đúng đối tượng bị thu hồi đúng phạm vi và đúng thời điểm, không còn truy cập bị cấm sau SLA, trạng thái tại các ứng dụng nhất quán, lỗi từng phần được xử lý và có chứng cứ kiểm toán. Sự kiện `disable` thành công đơn lẻ chưa đủ điều kiện PASS.

## 13. Bài thực hành

Giả lập nhân viên `test-person-505` hết hợp đồng lúc 18:00 ngày 18/12/2026. Người này có SSO, CRM qua SCIM, quyền Git bằng PAT, VPN và quyền đọc secret bot triển khai.

1. Lưu session và token CRM trước Leaver, kiểm tra chúng còn hoạt động.
2. Gửi sự kiện hợp lệ, xác minh chặn đăng nhập mới và `active=false` ở ứng dụng.
3. Thử lại bằng session/token/PAT/VPN; đo thời gian đến khi request bị từ chối.
4. Gây timeout sau khi SCIM đã cập nhật, rồi kiểm tra retry và readback.
5. Giữ một direct role CRM để chứng minh reconciliation phát hiện quyền tồn dư.
6. Phát lại Leaver và gửi Mover version cũ; xác nhận không có quyền hồi sinh.
7. Bàn giao owner bot, rotate secret nếu được yêu cầu và kiểm tra quyền người cũ đã mất.
8. Lập báo cáo `caseId, eventId, expected, actual, observedAt, deadlineAt, evidence, outcome, remediation`.

Trong deprovisioning, kết quả quan trọng nhất là **quyền truy cập thực tế đã bị chặn và bằng chứng xác nhận được lưu lại**. Đây là cách kiểm soát quyền truy cập tồn dư xuyên suốt vòng đời danh tính.
