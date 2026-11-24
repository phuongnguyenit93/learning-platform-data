# Key revocation — Thu hồi API key an toàn

## 1. Key revocation là gì?

**Key revocation** (thu hồi khóa) là thao tác làm cho một API key hoặc credential dạng khóa **không còn được chấp nhận để xác thực hay gọi API**. Khi key bị lộ, không còn cần thiết, thuộc về người dùng/dịch vụ đã ngừng hoạt động hoặc vi phạm chính sách, hệ thống phải có cách vô hiệu hóa key và ngăn các request mới sử dụng nó.

Ví dụ: một nhóm phát hiện API key của dịch vụ báo cáo xuất hiện trong repository công khai. Quản trị viên cần xác định key bị lộ, thu hồi đúng key đó, kiểm tra các request đã dùng key, cấp credential thay thế cho workload hợp lệ và theo dõi việc key cũ bị từ chối ở mọi API gateway.

Trong chương **API key** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, chủ đề này liên hệ với credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. API key là một dạng bearer credential: ai có giá trị key có thể sử dụng nó trong phạm vi quyền được cấp, trừ khi hệ thống có thêm cơ chế ràng buộc. Vì vậy, thu hồi phải là một phần được thiết kế ngay từ vòng đời credential, giúp giảm thời gian kẻ tấn công có thể sử dụng key bị lộ.

**Thu hồi khác với xóa một chuỗi ở phía client.** Nếu server vẫn chấp nhận key trong database hoặc cache, bản sao key của kẻ tấn công vẫn hoạt động. Quyết định thu hồi phải được thực thi ở phía xác minh, có hiệu lực theo một quy tắc rõ ràng và có thể kiểm chứng.

### Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Revoke** | Vô hiệu hóa một credential đã cấp. | Đánh dấu API key \`key_123\` bị thu hồi. |
| **Rotate** | Thay key cũ bằng key mới theo một quy trình chuyển đổi. | Cấp key mới, cập nhật workload, sau đó thu hồi key cũ. |
| **Expire** | Key tự hết hiệu lực theo thời hạn đã đặt. | Key chỉ dùng đến ngày kết thúc dự án. |
| **Delete** | Xóa bản ghi hoặc dữ liệu key theo chính sách lưu trữ. | Xóa metadata sau thời gian audit/retention. |
| **Disable/suspend** | Tạm ngưng key, có thể cho phép bật lại theo chính sách. | Tạm khóa key khi phát hiện hoạt động bất thường đang được điều tra. |

Trong thực tế, thu hồi có thể là trạng thái không thể đảo ngược. Nếu cần tạm dừng để điều tra, mô hình trạng thái nên phân biệt \`suspended\` với \`revoked\`. **Không tái kích hoạt một secret đã bị lộ** chỉ vì hoạt động bất thường tạm ngừng.

## 2. API key đại diện cho điều gì?

API key thường là một chuỗi bí mật được client gửi trong header hoặc một cơ chế xác thực được quy định. Server tra cứu key, xác minh nó còn hoạt động, rồi xác định principal, scope và giới hạn sử dụng.

Một mô hình đơn giản:

~~~text
API key credential
       |
       v
API gateway / authentication middleware
       |
       v
Lookup key record + verify secret
       |
       v
Check status, expiry, scope, quota, owner
       |
       v
Authorize request for resource/action
~~~

API key **xác thực một ứng dụng, workload hoặc chủ thể được cấp key** theo thiết kế của hệ thống. Nó không tự chứng minh người đang vận hành ứng dụng là ai, cũng không tự cấp quyền quản trị. Một key có thể được gắn với:

- Một tài khoản người dùng hoặc tổ chức.
- Một service account/workload.
- Một ứng dụng tích hợp hoặc đối tác.
- Một môi trường như development, staging hoặc production.
- Một tập scope và tài nguyên cụ thể.

Nếu nhiều ứng dụng dùng chung một key, việc thu hồi hoặc điều tra sẽ khó xác định phạm vi. Nên cấp key riêng theo principal, môi trường và mục đích, với quyền tối thiểu cần thiết.

## 3. Mô hình dữ liệu và ranh giới tin cậy

Server cần lưu metadata để nhận diện và quản lý key, đồng thời bảo vệ secret. Một bản ghi khái niệm:

~~~text
ApiKeyRecord
  key_id:          key_7F2A
  secret_verifier: <hash/HMAC verifier>
  owner_id:        service-reporting
  tenant_id:       org-27
  environment:     production
  scopes:          [reports:read]
  status:          active | suspended | revoked | expired
  created_at:      <timestamp>
  expires_at:      <timestamp>
  revoked_at:      <timestamp or null>
  revoked_by:      <principal or system>
  revoke_reason:   <controlled reason code>
~~~

Giá trị secret thô chỉ nên được hiển thị khi tạo key theo thiết kế; hệ thống thường lưu **verifier** để có thể kiểm tra key mà không giữ bản rõ. Một số kiến trúc dùng hash/KDF phù hợp, hoặc HMAC với pepper/secret quản lý ngoài database. Lựa chọn phụ thuộc entropy và định dạng key. Nếu key được sinh ngẫu nhiên với entropy cao, hash có thể phù hợp; nếu có nguy cơ key ngắn/yếu, cần cơ chế chống dò đoán mạnh hơn và không được tự thiết kế thuật toán mật mã.

Nên tách **key ID/prefix công khai** khỏi secret:

~~~text
key_live_7F2A_<random-secret>
^^^^^^^^^^^^^^
prefix / key identifier
               ^^^^^^^^^^^^^^
               secret ngẫu nhiên
~~~

Prefix giúp chọn đúng bản ghi và định tuyến tra cứu, không phải bằng chứng xác thực. Không dùng key ID thay cho secret. Không đưa secret thô vào log, trace, exception, URL, source code, issue hoặc telemetry.

### Ranh giới tin cậy

~~~mermaid
flowchart LR
    C["Client / workload<br/>giữ API key"]
    G["Gateway / API server<br/>nhận request"]
    V["Key verifier<br/>xác minh secret"]
    D[("Key registry<br/>status, owner, scopes")]
    R["Authorization<br/>resource + action"]
    A["API resource"]
    O["Admin / owner<br/>quản lý key"]
    C -->|"API key qua TLS"| G
    G --> V
    V <--> D
    V -->|"Principal đã xác minh"| R
    R -->|"Được phép"| A
    O -->|"Revoke / rotate request"| D
~~~

Client không được tự gửi \`status=active\`, \`ownerId\` hoặc \`scopes\` để quyết định quyền. Server lấy các giá trị này từ registry đã được bảo vệ. Hành động thu hồi cũng cần xác thực và phân quyền: chỉ chủ thể/administrator được phép quản lý key của phạm vi tương ứng mới có thể thu hồi.

## 4. Vòng đời API key và trạng thái thu hồi

Một API key có vòng đời rõ ràng:

1. **Create:** tạo secret ngẫu nhiên, key ID, owner, scope, thời hạn và metadata.
2. **Deliver:** hiển thị/cung cấp secret một cách an toàn cho đúng chủ thể.
3. **Active:** xác minh key ở mỗi request theo chính sách.
4. **Rotate:** cấp key mới và chuyển workload theo kế hoạch.
5. **Suspend/revoke/expire:** ngừng chấp nhận key theo lý do và thời điểm cụ thể.
6. **Retain/delete metadata:** giữ bản ghi audit hoặc xóa theo chính sách lưu trữ; secret không cần được lưu bản rõ để thu hồi.

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Active: Secret được cấp an toàn
    Created --> Expired: Quá hạn thiết lập
    Active --> Suspended: Tạm dừng điều tra
    Suspended --> Active: Được phép khôi phục theo policy
    Active --> Rotated: Key mới thay thế
    Active --> Revoked: Thu hồi
    Suspended --> Revoked: Xác nhận sự cố
    Active --> Expired: Đến hạn
    Rotated --> [*]
    Revoked --> [*]
    Expired --> [*]
~~~

Sơ đồ là mô hình tham khảo. Một hệ thống có thể không cho phép chuyển từ \`revoked\` trở lại \`active\`; nếu cần key mới thì tạo **credential mới với ID và secret mới**. Không tái sử dụng cùng secret dưới một bản ghi mới.

### Trạng thái phải được kiểm tra ở server

| Trạng thái | Request mới có được chấp nhận? | Hành vi |
| --- | --- | --- |
| \`created/pending\` | Không. | Chưa hoàn tất cấp phát hoặc xác nhận. |
| \`active\` | Có thể, nếu secret, thời hạn, scope và chính sách đều hợp lệ. | Tiếp tục xác thực và authorization. |
| \`suspended\` | Không. | Tạm từ chối; có thể chờ điều tra hoặc phê duyệt. |
| \`revoked\` | Không. | Từ chối vĩnh viễn key đó. |
| \`expired\` | Không. | Yêu cầu quy trình cấp key mới. |
| \`rotated\` | Không đối với key cũ sau thời điểm cutover. | Dùng key mới theo bản ghi riêng. |

**Thu hồi là quyết định về hiệu lực credential**, không chỉ là trạng thái giao diện. API gateway, worker, batch job và service nội bộ đều phải tuân theo cùng chính sách xác minh.

## 5. Luồng thu hồi một API key

Một thao tác thu hồi bình thường:

1. Chủ sở hữu hoặc quản trị viên mở trang quản lý credential và xác thực lại nếu thao tác nhạy cảm.
2. Chọn key theo ID/nhãn/owner/environment; server xác minh người yêu cầu có quyền quản lý key đó.
3. Server ghi nhận lệnh thu hồi với lý do có kiểm soát và thời điểm.
4. Trạng thái key chuyển sang \`revoked\` bằng thao tác nguyên tử; các verifier/gateway được thông báo hoặc lấy trạng thái mới.
5. Mọi request mới sử dụng key đó bị từ chối sau thời điểm hiệu lực được định nghĩa.
6. Hệ thống ghi audit, thông báo cho chủ sở hữu và hiển thị trạng thái đã thu hồi.

~~~mermaid
sequenceDiagram
    participant O as Owner / admin
    participant M as Key management API
    participant D as Key registry
    participant E as Event / cache invalidation
    participant G as API gateway
    O->>M: Revoke key_id + reason
    M->>M: Authenticate + authorize owner
    M->>D: Atomic status=revoked, timestamp, actor
    D-->>M: Commit success
    M->>E: Publish key-revoked event
    E-->>G: Invalidate cached key status
    G->>D: Refresh status if needed
    M-->>O: Revocation result
    Note over G: New requests with revoked key are rejected
~~~

Server chỉ nên trả “đã thu hồi” sau khi trạng thái đã commit ở nguồn dữ liệu có thẩm quyền. Nếu commit thành công nhưng event invalidation bị trễ, hệ thống cần có cơ chế retry/repair và thời gian hiệu lực tối đa đã xác định. Không tuyên bố thu hồi tức thời nếu cache ở gateway vẫn có thể chấp nhận key trong một khoảng chưa được kiểm soát.

## 6. Thu hồi tức thời trong hệ thống phân tán

Đây là phần khó nhất của key revocation. Một API key có thể được kiểm tra ở nhiều API gateway, region, microservice hoặc worker. Nếu mỗi nơi cache trạng thái \`active\`, việc cập nhật registry không tự làm mọi cache biết key đã bị thu hồi.

### Các mô hình phổ biến

| Mô hình | Cách hoạt động | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| **Lookup online mỗi request** | Verifier tra registry hoặc dịch vụ xác thực trung tâm cho từng request. | Trạng thái mới có thể được áp dụng nhanh. | Tăng latency/tải; phụ thuộc dịch vụ registry. |
| **Cache có TTL ngắn** | Gateway cache kết quả xác minh trong khoảng thời gian giới hạn. | Giảm tải và latency. | Key bị thu hồi có thể còn được chấp nhận đến khi cache hết hạn hoặc bị invalidation. |
| **Push invalidation/event** | Registry phát sự kiện thu hồi tới verifier/gateway. | Có thể giảm thời gian lan truyền. | Event có thể trễ/mất; cần retry, replay event và kiểm tra định kỳ. |
| **Revocation list/version** | Verifier kiểm tra trạng thái hoặc phiên bản key theo danh sách/epoch. | Có thể phù hợp khi số key lớn và cần kiểm soát theo nhóm. | Quản lý đồng bộ, kích thước danh sách và độ trễ. |
| **Introspection service** | API hỏi dịch vụ trung tâm xem key còn active không. | Một nguồn quyết định tập trung. | Phải bảo vệ, scale và xử lý khi introspection không sẵn sàng. |

Không có hệ thống phân tán nào nên tuyên bố “instant revocation” nếu vẫn có cache không được invalidation và không có giới hạn TTL. Cần đặt một **revocation propagation objective**: ví dụ, sau khi registry commit, mọi verifier phải từ chối key trong một khoảng thời gian tối đa đã xác định và kiểm thử được. Con số cụ thể phụ thuộc mức rủi ro và kiến trúc.

### Thiết kế cache an toàn

- Cache theo key ID, không theo secret thô.
- Cache cả kết quả active lẫn trạng thái thu hồi, nhưng đặt TTL phù hợp với mức nhạy cảm.
- Sự kiện thu hồi phải làm invalidation theo key ID và có thể phát lại an toàn.
- Nếu verifier không nhận được event, periodic refresh/TTL vẫn phải giới hạn thời gian chấp nhận trạng thái cũ.
- Theo dõi độ trễ từ thời điểm commit đến khi từng verifier áp dụng.
- Khi registry không sẵn sàng, quyết định fail-open/fail-closed phải được xác định theo rủi ro; không âm thầm chấp nhận key chưa thể kiểm tra khi yêu cầu bảo đảm cao.

### Consistency và race condition

Giả sử một request xác thực key bắt đầu đúng lúc quản trị viên thu hồi key. Hệ thống phải định nghĩa **điểm tuyến tính hóa** hoặc thời điểm quyết định:

- Request đã được xác minh trước khi revoke commit có thể đang xử lý; thu hồi không nhất thiết hủy ngược một transaction nghiệp vụ đã hoàn tất.
- Request bắt đầu sau khi revoke commit phải bị từ chối theo chính sách nhất quán đã chọn.
- Nếu request được xác minh ở gateway bằng cache cũ sau khi revoke commit, đó là độ trễ lan truyền cần giới hạn, đo lường và giảm thiểu.
- Với thao tác cực kỳ nhạy cảm, có thể yêu cầu kiểm tra trạng thái trực tuyến tại điểm thực thi hoặc kiểm tra lại trước commit nghiệp vụ.

Thu hồi credential không tự động rollback giao dịch đã thực hiện. Nếu key bị lạm dụng để tạo giao dịch, cần quy trình xử lý gian lận/sự cố riêng.

## 7. Key revocation và key rotation

**Rotation** là thay thế key; **revocation** là vô hiệu hóa key cũ. Rotation có thể kết thúc bằng thu hồi key cũ, nhưng hai hành động không nhất thiết diễn ra cùng thời điểm.

Một quy trình rotation có kiểm soát:

1. Tạo key mới với secret mới, owner và scope tương đương hoặc hẹp hơn.
2. Lưu secret mới ở secret manager/vault của workload.
3. Cập nhật ứng dụng, deploy và xác minh request dùng key mới thành công.
4. Theo dõi key cũ còn được sử dụng ở đâu; xác định client chưa chuyển đổi.
5. Thu hồi key cũ vào thời điểm cutover đã thông báo.
6. Xác nhận mọi verifier từ chối key cũ; xóa secret cũ khỏi nơi lưu trữ theo quy trình.

~~~mermaid
flowchart LR
    A["Key cũ active"] --> B["Tạo key mới"]
    B --> C["Cập nhật workload / secret store"]
    C --> D["Xác minh request bằng key mới"]
    D --> E{"Mọi client đã chuyển?"}
    E -->|"Chưa"| F["Điều tra client còn dùng key cũ<br/>theo deadline"]
    F --> D
    E -->|"Rồi"| G["Revoke key cũ"]
    G --> H["Kiểm thử key cũ bị từ chối"]
    H --> I["Hoàn tất rotation"]
~~~

Nếu key cũ bị lộ, **không nên duy trì giai đoạn chồng lấp dài chỉ để migration thuận tiện**. Cần ưu tiên thu hồi ngay theo incident policy, cấp key mới an toàn và cập nhật workload. Nếu không có cách chuyển đổi an toàn tức thời, cân nhắc chặn endpoint hoặc tạm dừng workload bị ảnh hưởng thay vì tiếp tục chấp nhận secret đã biết là bị lộ.

## 8. Thu hồi theo phạm vi và quyền tối thiểu

Không phải mọi sự cố đều cần thu hồi tất cả API key của tổ chức. Cần xác định phạm vi:

| Phạm vi | Khi phù hợp | Tác động |
| --- | --- | --- |
| **Một key** | Chỉ một secret bị lộ hoặc không còn cần. | Ít gián đoạn nhất; các key khác tiếp tục hoạt động. |
| **Một owner/service account** | Danh tính hoặc workload owner bị xâm phạm. | Thu hồi toàn bộ key thuộc principal đó. |
| **Một tenant/project** | Sự cố ảnh hưởng một tổ chức hoặc dự án. | Thu hồi credential trong phạm vi tenant/project. |
| **Một environment** | Key staging/dev bị lộ hoặc chính sách môi trường thay đổi. | Ngăn credential môi trường đó truy cập hệ thống tương ứng. |
| **Toàn bộ key theo nhóm/issuer** | CA, hệ thống phát hành hoặc secret manager bị xâm phạm trên diện rộng. | Tác động lớn; cần phối hợp incident response và kế hoạch khôi phục. |

Key nên có scope tối thiểu, ví dụ \`reports:read\` thay vì \`admin:*\`. Khi key bị lộ, phạm vi quyền nhỏ giúp giới hạn thiệt hại và thu hồi có thể nhắm đúng. Không dùng một key production cho nhiều workload nếu có thể cấp riêng.

### Thu hồi không thay thế authorization

Một key active vẫn phải bị giới hạn bởi scope, quota, owner, tenant và resource. Ngược lại, key đã revoked phải bị từ chối **trước khi** xử lý quyền. Không nên để một cache authorization cũ làm request tiếp tục thành công sau khi credential đã bị thu hồi.

## 9. Thu hồi API key khi có sự cố

Khi phát hiện key xuất hiện trong repository, log, ticket hoặc thiết bị bị xâm nhập:

1. **Xác nhận key ID và owner:** dùng prefix/ID hoặc dấu vết đã che secret; không sao chép key thô vào ticket/chat.
2. **Đánh giá phạm vi:** key có scope gì, ở môi trường nào, ai có quyền, request gần đây từ đâu và có dấu hiệu bị dùng trái phép không.
3. **Thu hồi key:** cập nhật registry và phát sự kiện invalidation; với key có nguy cơ cao, ưu tiên thu hồi nhanh.
4. **Cấp credential thay thế:** sinh secret mới qua quy trình an toàn, giới hạn scope và lưu vào secret manager.
5. **Cập nhật workload:** deploy cấu hình mới, xác minh request hợp lệ bằng key mới.
6. **Kiểm tra các verifier:** xác nhận gateway/region/service đều từ chối key cũ trong giới hạn propagation objective.
7. **Rà soát hoạt động đã xảy ra:** request, dữ liệu truy cập, thay đổi cấu hình, tài nguyên tạo mới, API key khác hoặc session liên quan.
8. **Thông báo và lưu audit:** thông báo owner, ghi thời gian/actor/reason/result mà không lưu secret thô.

Nếu key có quyền rộng hoặc đã được sử dụng để thay đổi tài khoản, cần kiểm tra thêm việc tạo credential mới, thay đổi MFA, refresh token, session và liên kết danh tính. Thu hồi API key không tự thu hồi những token/phiên khác mà kẻ tấn công đã tạo bằng quyền của key, trừ khi hệ thống có quan hệ và chính sách thu hồi rõ ràng.

## 10. API key rotation và revocation trong CI/CD

Pipeline CI/CD thường cần API key để publish artifact, gọi cloud API hoặc triển khai dịch vụ. Đây là bề mặt rủi ro vì log build, artifact, variable và cấu hình runner có thể làm lộ secret.

Biện pháp:

- Dùng secret manager hoặc secret store của nền tảng CI; giới hạn job/runner nào được đọc key.
- Tách key theo project, environment và nhiệm vụ; không dùng key cá nhân cho automation lâu dài.
- Ưu tiên workload identity hoặc credential ngắn hạn khi nền tảng hỗ trợ, thay vì secret tĩnh sống lâu.
- Không echo secret, bật masking phù hợp và kiểm soát log/artifact/cache.
- Khi runner bị xâm nhập, thu hồi key của runner/project liên quan và rà soát key khác có thể đọc được.
- Rotation theo lịch và theo sự kiện; kiểm tra deploy thành công trước khi revoke key cũ trong quy trình bình thường.
- Khi phát hiện leak, không đợi đến kỳ rotation kế tiếp.

Một pipeline không nên lưu key production trong file cấu hình được commit. Nếu cần cấu hình, chỉ lưu **tên tham chiếu secret** và lấy giá trị từ kho được kiểm soát ở runtime.

## 11. Mã giả: xác minh API key và thực thi trạng thái revoke

Mã giả sau mô tả logic server. Đây không phải code production và không thay thế thư viện quản lý secret/cryptography:

~~~text
authenticateApiKey(request):
    presented = extractApiKeyFromApprovedHeader(request)
    if presented is missing:
        return unauthorized()

    keyId, secret = parseKeyIdAndSecret(presented)
    if keyId is invalid:
        return unauthorized()

    record = keyRegistry.lookup(keyId)
    if record is missing:
        performComparableVerificationWork()
        return unauthorized()

    if record.status != "active":
        return unauthorized()
    if record.expiresAt <= trustedClock.now():
        return unauthorized()
    if not verifySecretWithApprovedScheme(secret, record.verifier):
        recordAbuseSignal(keyId, safeRequestMetadata)
        return unauthorized()

    principal = resolveOwnerAndScopes(record)
    if not principal.active:
        return unauthorized()

    return authenticatedPrincipal(principal)

revokeApiKey(actor, keyId, reason):
    require actorMayManageKey(actor, keyId)
    atomically:
        record = lockKeyRecord(keyId)
        if record.status == "revoked":
            return alreadyRevoked()
        setStatus(record, "revoked")
        setRevokedAt(record, trustedClock.now())
        setRevokedBy(record, actor.id)
        setRevokeReason(record, allowedReasonCode(reason))
        commit()

    publishRevocationEvent(keyId)
    auditWithoutSecret("api_key_revoked", actor.id, keyId)
    return revokeAccepted()
~~~

Trong triển khai thực tế, cần bảo đảm:

- Key secret được so sánh bằng cơ chế an toàn của thư viện; không ghi hoặc hiển thị secret.
- Trạng thái revoke và các trường audit được commit nguyên tử.
- Event có ID/sequence để consumer xử lý idempotent; event mất hoặc trễ có cơ chế retry và reconcile.
- Gateway không dùng cache active quá thời hạn cho phép; nếu cần hiệu lực gần tức thời, phải kiểm tra online hoặc dùng invalidation đáng tin cậy.
- \`alreadyRevoked\` không làm key sống lại; API revoke có thể idempotent.
- Quyền revoke được kiểm tra theo owner/tenant và actor; mọi request quản trị đều được audit.

## 12. Thiết kế API quản lý thu hồi

Một API quản lý key có thể cung cấp các thao tác:

| Thao tác | Ví dụ endpoint khái niệm | Yêu cầu |
| --- | --- | --- |
| Liệt kê key metadata | \`GET /api-keys\` | Chỉ trả ID, nhãn, owner, scope, status, thời hạn; không trả secret. |
| Tạo key | \`POST /api-keys\` | Xác thực mạnh, kiểm tra quyền, tạo secret một lần và hiển thị an toàn. |
| Thu hồi key | \`POST /api-keys/{id}/revoke\` | Kiểm tra owner/admin, CSRF nếu dùng cookie, reason code, audit. |
| Xem trạng thái | \`GET /api-keys/{id}\` | Phân quyền theo tenant/owner; không lộ secret/verifier. |
| Rotation | \`POST /api-keys/{id}/rotate\` | Tạo key mới, quản lý cutover và thu hồi key cũ theo policy. |

Endpoint quản lý key là bề mặt có quyền cao. Cần chống IDOR, CSRF, replay thao tác quản trị và lạm dụng API. Nếu request revoke được gửi lại do timeout, kết quả nên idempotent: key vẫn revoked, không tạo secret mới hoặc khôi phục trạng thái.

Không nên đưa secret vào path/query string vì URL có thể xuất hiện trong access log, browser history, proxy hoặc Referer. Secret chỉ nên được gửi qua kênh TLS trong header/body phù hợp với giao thức và không được log.

## 13. Quan sát, audit và đo hiệu quả thu hồi

Sự kiện quản lý key nên ghi:

- Key ID, owner, tenant và environment.
- Actor yêu cầu thu hồi và nguồn xác thực/ủy quyền của actor.
- Thời điểm request, thời điểm commit, lý do thu hồi và kết quả.
- Số verifier/gateway đã nhận invalidation, độ trễ propagation và lỗi consumer.
- Request bị từ chối do key revoked/expired/suspended; chỉ lưu metadata tối thiểu.

**Không ghi secret API key thô, hash/verifier nhạy cảm, access token hoặc session cookie.** Log cần có quyền truy cập giới hạn, retention và khả năng phát hiện chỉnh sửa. Nếu cần đối chiếu sự kiện, dùng key ID hoặc mã tham chiếu không thể dùng để xác thực.

Các chỉ số hữu ích:

| Chỉ số | Câu hỏi |
| --- | --- |
| **Revocation propagation latency** | Mất bao lâu từ commit đến khi verifier cuối cùng từ chối key? |
| **Revocation coverage** | Bao nhiêu gateway/region/service đã áp dụng sự kiện? |
| **Old-key request count** | Sau revoke, key cũ còn bị thử ở đâu và tần suất ra sao? |
| **Rotation completion** | Bao nhiêu workload đã chuyển sang key mới trước deadline? |
| **False revocation / service impact** | Có key hợp lệ nào bị thu hồi nhầm hoặc workload nào bị gián đoạn? |
| **Unmanaged key inventory** | Có key không rõ owner, scope hoặc thời hạn hay không? |

Một hệ thống có thể báo “revoke API thành công” nhưng nếu một region vẫn chấp nhận key cũ thì sự cố chưa được xử lý hoàn toàn. Cần theo dõi **hiệu lực thực tế ở điểm xác minh**, không chỉ trạng thái trong trang quản trị.

## 14. Tình huống thực tế: API key bị lộ trong repository

Một nhóm phát triển vô tình commit API key production có scope \`reports:read\` vào repository công khai. Key được sử dụng bởi ba worker chạy ở hai region. API gateway cache kết quả key hợp lệ trong 10 phút.

### Phân tích

| Vấn đề | Nguy cơ | Hành động |
| --- | --- | --- |
| Secret đã xuất hiện công khai | Bất kỳ ai có thể đã sao chép key. | Xem key là bị lộ; không chờ xác minh ai đã dùng. |
| Ba worker dùng chung key | Khó xác định workload nào tạo request. | Cấp key riêng cho từng worker/service sau sự cố. |
| Gateway cache 10 phút | Key cũ có thể còn được chấp nhận sau registry revoke. | Invalidate cache, giảm TTL/lookup online theo risk policy, kiểm tra cả hai region. |
| Secret còn trong Git history | Xóa commit mới không xóa bản sao lịch sử/fork. | Thu hồi key; xử lý repository và secret scanning theo quy trình. |
| Scope chỉ đọc báo cáo | Thiệt hại bị giới hạn nhưng dữ liệu vẫn nhạy cảm. | Rà soát truy cập dữ liệu, export và request bất thường. |

### Trình tự ứng phó

1. Xác định key ID bằng metadata/log đã che secret.
2. Thu hồi key cũ ở registry và phát sự kiện tới gateway.
3. Kiểm tra hai region đã từ chối key cũ; không chỉ kiểm tra dashboard.
4. Tạo key mới riêng cho từng worker, scope hẹp và thời hạn phù hợp.
5. Đưa key mới vào secret manager/CI secret store, deploy và kiểm tra.
6. Rà soát request trong khoảng thời gian key có thể đã bị lộ.
7. Gỡ secret khỏi source hiện tại và xử lý lịch sử repository theo chính sách; nhớ rằng việc xóa khỏi Git không thay thế revoke.
8. Bật secret scanning và kiểm tra các credential khác có thể cùng bị commit.

**Câu hỏi:** Nếu xóa dòng key khỏi commit mới, có cần revoke không? **Có.** Bản sao cũ vẫn có thể tồn tại trong Git history, fork, cache hoặc clone của người khác. Chỉ thu hồi ở verifier mới làm key không còn được chấp nhận.

## 15. Danh sách kiểm tra thiết kế key revocation

- [ ] Mỗi API key có ID riêng, owner, tenant, environment, scope và thời hạn rõ ràng.
- [ ] Secret được sinh ngẫu nhiên đủ mạnh, chỉ hiển thị/cấp phát an toàn và không lưu plaintext nếu không cần.
- [ ] Server kiểm tra status, expiry, secret verifier, owner và scope trước khi cho request tiếp tục.
- [ ] Có thể thu hồi một key cụ thể, toàn bộ key của owner hoặc phạm vi tenant theo chính sách.
- [ ] Thao tác revoke được phân quyền, xác thực lại khi cần, chống CSRF/IDOR và có audit.
- [ ] Trạng thái revoke được commit nguyên tử và không thể bị bật lại ngoài quy trình được duyệt.
- [ ] Cache/gateway/region có cơ chế invalidation, TTL và reconcile; có propagation objective được đo.
- [ ] Hành vi khi registry/event service không sẵn sàng đã được xác định theo rủi ro.
- [ ] Rotation có bước tạo key mới, cập nhật workload, xác minh và thu hồi key cũ.
- [ ] Key bị lộ được thu hồi ngay theo incident policy; xóa khỏi repository không thay thế revoke.
- [ ] Refresh token/session/API credential khác được rà soát nếu key có thể đã dùng để tạo chúng.
- [ ] Log không chứa secret; dashboard theo dõi propagation latency và request dùng key cũ.
- [ ] Có kiểm thử request sau revoke ở tất cả region/gateway và kiểm thử race/retry.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao xóa API key khỏi file cấu hình hoặc repository không đồng nghĩa với thu hồi?

**Gợi ý:** Server vẫn có thể chấp nhận secret cũ; bản sao cũng có thể tồn tại trong Git history, fork, log hoặc clone.

**Câu 2.** API key đã được đánh dấu revoked ở database nhưng gateway cache trạng thái active thêm 10 phút. Có thể tuyên bố key đã bị vô hiệu hóa tức thời không?

**Gợi ý:** Không. Cần invalidation hoặc giới hạn TTL, đo độ trễ và định nghĩa thời điểm hiệu lực tối đa.

**Câu 3.** Vì sao rotate và revoke là hai hành động khác nhau?

**Gợi ý:** Rotate thay thế key theo quy trình chuyển đổi; revoke làm key cụ thể mất hiệu lực. Rotation bình thường có thể có giai đoạn chuyển tiếp, còn key đã lộ cần thu hồi nhanh.

**Câu 4.** Khi một key bị lộ, có luôn phải thu hồi tất cả API key của tổ chức không?

**Gợi ý:** Không nhất thiết. Xác định phạm vi owner, tenant, environment, issuer và quyền; mở rộng thu hồi nếu hệ thống cấp phát hoặc principal gốc bị xâm phạm.

**Câu 5.** Tại sao một API key active vẫn cần kiểm tra scope và authorization?

**Gợi ý:** Authentication xác định principal; authorization quyết định principal được truy cập resource/action nào. Active không có nghĩa quyền vô hạn.

**Câu 6.** Nếu request revoke bị gửi lại do timeout, điều gì nên xảy ra?

**Gợi ý:** Thao tác nên idempotent; key vẫn ở trạng thái revoked, không được khôi phục hoặc tạo thêm secret ngoài ý muốn.

## 17. Ghi nhớ

**Key revocation là cơ chế làm cho một API key không còn được chấp nhận ở phía xác minh.** Xóa secret khỏi client hoặc repository không đủ; server phải cập nhật trạng thái, truyền quyết định tới mọi verifier và giới hạn độ trễ cache. Một thiết kế tốt định danh key riêng, quản lý owner/scope/expiry, phân quyền thao tác revoke, hỗ trợ rotation, xử lý sự cố và audit mà không lộ secret. Khi key bị lộ, thu hồi credential cũ, cấp key mới có phạm vi tối thiểu và xác minh mọi gateway đã từ chối key cũ là các bước cần thiết để khép lại rủi ro.
