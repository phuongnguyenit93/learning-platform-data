# Key scope

**Key scope** là phạm vi hành động và tài nguyên mà một API key được phép sử dụng. Khi một client trình bày API key hợp lệ, server cần xác định key đại diện cho integration, service hoặc project nào, key được phép gọi endpoint nào, trên dữ liệu thuộc tenant nào và trong những điều kiện nào. Scope được thiết kế tốt giúp giới hạn thiệt hại nếu key bị lộ hoặc bị dùng sai mục đích.

Bài học thuộc chương **API key** trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Người học sẽ biết phân biệt API key với danh tính người dùng và OAuth scope; thiết kế scope theo hành động, tài nguyên và tenant; áp dụng least privilege; kết hợp giới hạn môi trường, mạng, thời hạn và quota; đồng thời bảo vệ vòng đời tạo, lưu trữ, xoay vòng và thu hồi key.

Một nguyên tắc quan trọng: **API key hợp lệ chỉ chứng minh caller đang giữ một credential được cấp. Nó không tự động chứng minh người dùng cuối là ai hoặc caller được quyền truy cập mọi dữ liệu.** Server vẫn phải kiểm tra scope, trạng thái key, tenant, quyền trên đối tượng và điều kiện nghiệp vụ.

## 1. API key và scope giải quyết vấn đề gì?

API key thường là một chuỗi bí mật ngẫu nhiên được cấp cho ứng dụng, integration hoặc service để xác thực các request tới API. Ví dụ, một dịch vụ đồng bộ khóa học có thể dùng key riêng để đọc danh sách khóa học và cập nhật trạng thái hoàn thành.

Nếu chỉ kiểm tra “key có tồn tại trong database không?”, một key bị cấp quyền rộng có thể thực hiện quá nhiều hành động. Key scope bổ sung giới hạn rõ ràng:

- Key nào được gọi API nào?
- Key được đọc, tạo, cập nhật hay xóa loại tài nguyên nào?
- Key chỉ hoạt động trong tenant hoặc project nào?
- Key có được gọi endpoint quản trị hay thao tác nhạy cảm không?
- Key có bị giới hạn theo môi trường, thời gian, mạng hoặc hạn mức sử dụng không?

Ví dụ:

| API key | Scope được cấp | Hành động được phép |
| --- | --- | --- |
| `course-sync-read` | `courses.read` | Đọc danh sách và thông tin khóa học được phép. |
| `completion-writer` | `completions.create`, `completions.read` | Ghi nhận và đọc trạng thái hoàn thành. |
| `billing-export` | `invoices.read` | Đọc hóa đơn trong phạm vi được cấp để xuất báo cáo. |
| `platform-admin` | Quyền quản trị đặc biệt | Chỉ cấp cho quy trình quản trị có kiểm soát tăng cường. |

Nếu `course-sync-read` bị lộ, attacker không nên có khả năng phát hành chứng chỉ, thay đổi quyền hoặc đọc dữ liệu thanh toán. Scope không ngăn mọi hành vi lạm dụng, nhưng làm giảm phạm vi hành động mà key bị lộ có thể thực hiện.

## 2. Phân biệt API key, identity và scope

Ba khái niệm này thường bị trộn lẫn:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **API key** | Credential mà client trình bày để server xác thực request. | Chuỗi bí mật được cấp cho integration `course-sync`. |
| **Key identity / owner** | Thực thể nội bộ mà key đại diện và chịu trách nhiệm. | `client_id=course-sync-prod`, owner là nhóm tích hợp đào tạo. |
| **Scope** | Tập hành động hoặc quyền mà key có thể yêu cầu. | `courses.read`, `completions.create`. |
| **Resource / tenant binding** | Phạm vi dữ liệu key có thể tác động. | Chỉ dữ liệu tenant `org-7` hoặc project `project-12`. |
| **Restriction** | Điều kiện bổ sung khi sử dụng key. | Môi trường production, IP allowlist, hạn dùng hoặc quota. |

API key thường là **bearer credential**: bên nào giữ được chuỗi bí mật có thể trình bày nó. Vì vậy key phải được bảo vệ như mật khẩu hoặc token nhạy cảm. Tuy nhiên, key thường đại diện cho một integration/service chứ không phải người dùng cuối.

**Không dùng API key như bằng chứng rằng một người đã đăng nhập bằng MFA.** Nếu API cần hành động nhân danh người dùng, cần một cơ chế delegation/token phù hợp để truyền ngữ cảnh người dùng đã được xác thực và ủy quyền.

## 3. Thiết kế scope theo hành động và tài nguyên

Một scope tốt phải diễn đạt rõ **hành động nào trên loại tài nguyên nào**. Tên scope chỉ là quy ước; server phải ánh xạ nó tới chính sách thực tế.

### 3.1. Phân tách quyền đọc và ghi

Ví dụ với API khóa học:

| Scope | Hành động ví dụ |
| --- | --- |
| `courses.read` | Xem danh sách và chi tiết khóa học. |
| `courses.create` | Tạo khóa học mới. |
| `courses.update` | Sửa metadata hoặc nội dung khóa học. |
| `courses.archive` | Lưu trữ khóa học theo quy trình cho phép. |
| `courses.delete` | Xóa khóa học nếu nghiệp vụ hỗ trợ và caller được phép. |

Không nên dùng một scope chung như `courses.manage` cho mọi integration nếu phần lớn chỉ cần đọc. Quyền ghi, xóa, thay đổi membership hoặc phát hành chứng chỉ có hậu quả lớn hơn quyền đọc nên cần scope riêng, phê duyệt riêng hoặc xác thực tăng cường.

### 3.2. Scope phải gắn với loại tài nguyên cụ thể

Một scope như `read` quá chung chung. Nó không cho biết đọc loại dữ liệu nào. Nên chọn tên có namespace rõ ràng, ví dụ:

- `learners.read`
- `courses.read`
- `completions.create`
- `certificates.issue`
- `certificates.revoke`
- `webhooks.manage`

Tên scope nên ổn định, có mô tả, owner và chính sách tương ứng. Không đổi ý nghĩa một scope đang được dùng mà không đánh giá các key hiện có.

### 3.3. Scope không thay thế object-level authorization

Giả sử key có scope `invoices.read`. Điều đó có thể cho phép gọi endpoint đọc hóa đơn, nhưng **không tự động cho phép đọc hóa đơn của mọi tenant hoặc mọi khách hàng**.

Server còn cần kiểm tra:

- Key thuộc tenant hoặc project nào.
- Resource ID có thuộc phạm vi tenant/project đó không.
- Caller có quyền trên đúng đối tượng và trạng thái nghiệp vụ không.
- Request có vượt giới hạn dữ liệu hoặc mục đích sử dụng không.

Ví dụ, `GET /invoices/inv-99` không được trả hóa đơn tenant B chỉ vì key của tenant A có scope `invoices.read`. Nếu chỉ kiểm tra scope mà bỏ kiểm tra quyền trên object, hệ thống vẫn có thể mắc lỗi IDOR/BOLA.

## 4. Scope, role, permission và OAuth scope

Các mô hình quyền có liên quan nhưng không hoàn toàn giống nhau:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Scope** | Nhãn phạm vi quyền được gắn với credential hoặc token trong một giao thức/chính sách. |
| **Permission** | Quyền cụ thể để thực hiện hành động trên tài nguyên. |
| **Role** | Tập hợp permissions được gán cho một chủ thể theo trách nhiệm. |
| **Policy** | Quy tắc quyết định có cho phép hành động dựa trên subject, action, resource, context hay không. |

Một API key có thể lưu danh sách scope trực tiếp trong bản ghi key. Khi request đến, server ánh xạ scope thành permissions hoặc kiểm tra policy. Với OAuth 2.0, scope thường là chuỗi quyền mà client yêu cầu và authorization server cấp trong access token. **OAuth scope không phải một quyền tự thi hành**: resource server vẫn cần định nghĩa và thực thi cách scope ánh xạ tới quyền.

Ví dụ:

```text
API key record:
  key_id: key_82a
  client_id: course-sync-prod
  tenant_id: org-7
  scopes:
    - courses.read
    - completions.create
  status: active
  expires_at: 2027-01-01T00:00:00Z

Request:
  GET /v1/courses

Authorization decision:
  authenticate key
  require key.status == active
  require key has courses.read
  require requested tenant == org-7
  require resource policy allows this client
```

Nếu hệ thống dùng RBAC/ABAC, scope có thể là một đầu vào cho policy chứ không phải toàn bộ policy. Chẳng hạn, `certificates.issue` vẫn có thể yêu cầu khóa học đã hoàn tất, người học thuộc tenant hợp lệ và key có quyền phát hành cho loại chứng chỉ đó.

## 5. Giới hạn phạm vi theo tenant, project và môi trường

### 5.1. Tenant binding

Trong hệ thống đa tenant, key nên được gắn với tenant hoặc tập tenant cụ thể. Không cho client tự gửi `tenant_id` rồi coi giá trị đó là phạm vi được phép.

Quy trình nên:

1. Xác thực key và tìm bản ghi key nội bộ.
2. Lấy tenant/project binding từ bản ghi đáng tin cậy.
3. So sánh request context với binding và chính sách cho phép.
4. Kiểm tra resource thuộc tenant đó.
5. Ghi audit với key ID, tenant, resource và kết quả.

Nếu một integration thực sự cần truy cập nhiều tenant, phải khai báo rõ danh sách/phạm vi, có owner và phê duyệt; không dùng một key toàn cục với quyền ngầm định.

### 5.2. Tách môi trường

Tạo key riêng cho development, staging và production:

- Key development không thể gọi production.
- Key staging chỉ truy cập dữ liệu thử nghiệm.
- Key production không được sao chép vào máy cá nhân hoặc môi trường test.
- Khi thay đổi môi trường hoặc owner, cần tạo key mới theo quy trình cấp phát.

Chỉ đặt tên `prod` trong metadata không đủ. API phải kiểm tra môi trường của key và resource server đang phục vụ.

### 5.3. Giới hạn mạng và nguồn gọi

IP allowlist, mTLS hoặc giới hạn endpoint có thể giảm khả năng key bị dùng từ nguồn lạ. Nhưng IP là tín hiệu/vùng mạng, không phải identity đầy đủ; NAT, proxy, cloud egress và môi trường triển khai có thể làm thay đổi địa chỉ. Nếu dùng allowlist, phải có quy trình cập nhật, kiểm tra và xử lý khi IP thay đổi.

Giới hạn theo HTTP referrer/origin thường hữu ích như một lớp hạn chế cho API key công khai ở browser, nhưng **không biến key phía client thành bí mật**. Header/referrer có thể bị giả mạo trong những môi trường khác; không cấp quyền nhạy cảm chỉ dựa vào kiểm tra origin.

## 6. Nguyên tắc least privilege khi cấp key

Một key chỉ nên có **quyền tối thiểu cần cho một integration cụ thể**. Không cấp quyền rộng để tránh phải cấu hình lại sau này.

Quy trình đề xuất:

1. Xác định owner chịu trách nhiệm và service sử dụng key.
2. Liệt kê endpoint và hành động thực sự cần dùng.
3. Chọn scope nhỏ nhất có thể, tách đọc/ghi/xóa/quản trị.
4. Ràng buộc tenant/project và môi trường.
5. Đặt hạn dùng, quota và điều kiện mạng theo mức rủi ro.
6. Yêu cầu phê duyệt khi key có quyền nhạy cảm hoặc truy cập nhiều tenant.
7. Kiểm thử request được phép và request phải bị từ chối.
8. Ghi nhận owner, mục đích, ngày cấp, ngày hết hạn và quy trình rotation.

Ví dụ, integration chỉ đồng bộ danh sách khóa học mỗi giờ không cần `certificates.issue`, `users.delete` hoặc `admin.*`. Khi nghiệp vụ thay đổi, tạo hoặc điều chỉnh key qua quy trình quản lý có audit, không âm thầm nâng quyền của key cũ.

## 7. API key là bearer secret: bảo vệ cách tạo và lưu

### 7.1. Tạo key có entropy cao

API key nên được tạo bằng bộ sinh số ngẫu nhiên mật mã (CSPRNG), đủ dài và không có cấu trúc dễ đoán. Không tạo key từ tên ứng dụng, thời gian, số tăng dần hoặc hash của email.

Một định dạng thường gặp:

```text
ak_live_<public-prefix>_<random-secret>
```

Prefix có thể giúp nhận diện môi trường hoặc tìm bản ghi trong hệ thống, nhưng không được chứa thông tin nhạy cảm. Phần bí mật phải có entropy cao; không dùng lại cùng một secret cho nhiều integration.

### 7.2. Chỉ hiển thị secret khi tạo

Sau khi cấp key, giao diện có thể hiển thị secret một lần để owner lưu vào secret manager. Khi người dùng rời màn hình, server không cần cho xem lại secret nguyên bản. Nếu mất key, tạo key mới và thu hồi key cũ theo quy trình.

Vì API key được tạo ngẫu nhiên với entropy cao, server thường có thể lưu **bản băm/HMAC verifier** thay vì secret rõ. Ví dụ, dùng HMAC với pepper được giữ riêng trong KMS/secret manager để tra cứu/kiểm tra; lựa chọn cụ thể cần tính tới threat model và kiến trúc key lookup. Nếu key có entropy thấp hoặc do người dùng tự chọn, cần cách lưu phù hợp với secret yếu như password hashing. Không đưa secret vào log hoặc hệ thống phân tích.

### 7.3. Truyền key an toàn

- Chỉ gửi qua TLS; từ chối hoặc chuyển hướng các luồng không an toàn theo chính sách.
- Dùng header chuyên dụng như `X-API-Key` hoặc cơ chế Authorization được tài liệu API định nghĩa.
- Không đặt key trong query string, URL, path hoặc tham số có thể xuất hiện trong browser history, proxy log và analytics.
- Không ghi header chứa key vào application log, tracing, error report hoặc audit.
- Không nhúng secret production vào mã nguồn, container image, frontend bundle hoặc mobile app.
- Lưu key trong secret manager phù hợp; giới hạn người và workload có thể đọc hoặc sử dụng.

**API key nhúng trong browser/mobile app không thể giữ bí mật trước người sử dụng thiết bị.** Nếu client công khai phải gọi API, chỉ dùng key có quyền công khai/giới hạn chặt như nhận diện project, quota hoặc truy cập dữ liệu công khai. Với dữ liệu riêng tư hoặc hành động thay mặt người dùng, dùng backend-for-frontend hoặc OAuth/OIDC với flow phù hợp (ví dụ Authorization Code + PKCE cho ứng dụng công khai).

## 8. Thực thi scope tại API server

Một quyết định authorization cần dựa trên key đã được xác thực và dữ liệu đáng tin cậy phía server, không dựa vào trường scope do client gửi.

Ví dụ pseudocode:

```text
handleRequest(request):
    rawKey = readApiKeyFromConfiguredHeader(request)
    keyRecord = lookupAndVerifyKey(rawKey)

    require keyRecord exists
    require keyRecord.status == "active"
    require keyRecord.expiresAt is absent or now < keyRecord.expiresAt
    require request.environment is allowed by keyRecord
    require request.sourceNetwork satisfies keyRecord restrictions

    action = mapRouteAndMethodToPermission(request)
    require keyRecord.scopes contains requiredScope(action)

    tenant = keyRecord.tenantBinding
    resource = loadResource(request.resourceId)
    require resource.tenantId == tenant
    require policyAllows(keyRecord.clientId, action, resource, request.context)

    enforceQuotaAndRateLimit(keyRecord.keyId, action)
    recordSecurityAudit(keyRecord.keyId, action, tenant, resource.id)
    return executeRequest()
```

Các điểm cần chú ý:

- `mapRouteAndMethodToPermission` phải được cấu hình phía server. Không nhận scope từ query/body.
- Key bị vô hiệu hóa hoặc hết hạn phải bị từ chối dù secret vẫn đúng.
- Route và HTTP method cần ánh xạ rõ tới hành động; không để một endpoint ghi có thể bị gọi qua method khác mà không kiểm tra.
- Resource và tenant phải được tải/kiểm tra phía server; không tin ID do client khai là thuộc phạm vi key.
- Quota/rate limit không thay thế authorization, nhưng giúp hạn chế brute force và lạm dụng.
- Audit chỉ ghi key ID/prefix và metadata cần thiết, không ghi secret.

### 8.1. Scope và quota là hai giới hạn khác nhau

Scope giới hạn **được làm gì**; quota/rate limit giới hạn **làm bao nhiêu hoặc với tốc độ nào**. Một key có `courses.read` vẫn có thể gây tải lớn nếu được phép gửi hàng triệu request. Một key có quota thấp nhưng scope `admin.*` vẫn có thể thực hiện hành động nguy hiểm trong vài request.

Cần kết hợp permission, quota, burst limit, kích thước payload, pagination, timeout và phát hiện hành vi bất thường theo client.

## 9. Rotation, thu hồi và thay đổi scope

Key có vòng đời: tạo, phân phối, sử dụng, gia hạn/rotation, thu hồi và xóa metadata theo chính sách. Không nên giữ key vô thời hạn chỉ vì integration đã hoạt động lâu.

### 9.1. Rotation không gây gián đoạn

Một quy trình rotation có thể gồm:

1. Owner yêu cầu key mới với scope/binding đã được rà soát.
2. Server cấp key mới và chỉ hiển thị secret một lần.
3. Integration cập nhật secret trong secret manager và triển khai bản mới.
4. Theo dõi request thành công bằng key mới; xác nhận key cũ không còn cần thiết.
5. Thu hồi key cũ và kiểm tra các lần sử dụng còn sót.
6. Lưu audit và cập nhật inventory.

Trong thời gian chuyển tiếp, có thể tồn tại hai key hợp lệ nhưng mỗi key phải có ID và trạng thái riêng, thời hạn chuyển tiếp rõ ràng và quyền không rộng hơn nhu cầu.

### 9.2. Thu hồi khẩn cấp

Khi key bị lộ:

- Đánh dấu key revoked tại nguồn quản lý và chặn request mới.
- Xác định tenant, scope, resource và thời gian key có thể bị lạm dụng.
- Kiểm tra log theo key ID/prefix, không cần tìm secret nguyên bản.
- Xoay các secret khác nếu chúng được lưu chung hoặc có khả năng bị lộ cùng lúc.
- Kiểm tra dữ liệu bị đọc/sửa và thu hồi session/token phát sinh nếu có.
- Cấp key thay thế với scope tối thiểu sau khi khắc phục nguyên nhân.

Nếu key được đổi thành JWT hoặc token tự chứa, cần hiểu việc thu hồi có thể phụ thuộc thời hạn token, introspection, denylist hoặc kiểm tra trạng thái phía resource server. Đừng tuyên bố thu hồi tức thì nếu API vẫn chấp nhận credential cũ đến khi hết hạn.

### 9.3. Thay đổi scope

Nếu scope lưu trong database và được kiểm tra mỗi request, thu hẹp quyền có thể có hiệu lực ngay khi cập nhật bản ghi hoặc cache hết hạn. Nếu quyền được đóng gói trong token tự chứa, thay đổi ở nguồn cấp có thể không tác động tới token đã phát hành cho tới khi token hết hạn hoặc có cơ chế thu hồi.

Khi nâng scope, cần phê duyệt theo rủi ro và ghi lý do. Khi giảm scope, theo dõi integration có bị lỗi và xác nhận quyền cũ đã bị loại bỏ. Không thay đổi ý nghĩa của tên scope cũ mà không versioning/chuyển đổi rõ ràng.

## 10. Threat model cho API key scope

| Mối đe dọa | Nguyên nhân | Kiểm soát |
| --- | --- | --- |
| **Key leakage** | Key trong source code, log, URL, ticket hoặc frontend bundle. | Secret manager, redaction, scan secret, rotation và thu hồi. |
| **Over-scoped key** | Cấp `admin.*` hoặc quyền ghi/xóa cho integration chỉ cần đọc. | Least privilege, scope riêng, phê duyệt và rà soát định kỳ. |
| **Cross-tenant access** | Tin tenant ID từ request hoặc key dùng chung nhiều tenant. | Tenant binding server-side và object-level authorization. |
| **Key sharing** | Nhiều integration/người cùng dùng một key. | Key riêng theo owner, service, môi trường; audit theo key ID. |
| **Browser/mobile extraction** | Secret nhúng trong bundle hoặc app có thể bị trích xuất. | Không đặt secret nhạy cảm trong client công khai; dùng BFF/OAuth phù hợp. |
| **Replay / token theft** | Bearer key bị lấy và dùng lại từ nơi khác. | TLS, hạn dùng, giới hạn mạng khi phù hợp, rate limit, rotation và giám sát. |
| **Brute-force discovery** | Key ngắn, dễ đoán hoặc endpoint kiểm tra key không giới hạn. | CSPRNG, entropy cao, rate limit, phản hồi đồng nhất và phát hiện dò quét. |
| **Stale key** | Key không có owner hoặc không hết hạn sau khi integration dừng. | Inventory, owner, expiry, review và auto-revocation theo chính sách. |
| **Privilege escalation** | Endpoint mapping scope sai hoặc tin scope client tự khai. | Permission mapping server-side, kiểm thử deny cases, review thay đổi route/policy. |
| **Confused deputy** | Service có quyền rộng dùng key để truy cập resource mà caller không được phép. | Ràng buộc caller, tenant, object, context và delegation đúng cách. |

## 11. Tình huống thực hành: key đọc khóa học bị dùng để phát hành chứng chỉ

**Bối cảnh:** Một integration `course-sync` chỉ cần đồng bộ danh sách khóa học. Khi tạo key, nhóm phát triển cấp `courses.read` và `certificates.issue` vì muốn tránh phải xin thêm quyền sau này. Một bản log bị lộ chứa API key. Attacker sử dụng key để phát hành chứng chỉ giả.

**Phân tích:**

1. Key đã được xác thực đúng, nhưng **scope vượt nhu cầu** của integration.
2. Việc lộ key biến credential hợp lệ thành công cụ thực hiện hành động nhạy cảm.
3. API có thể chỉ kiểm tra `certificates.issue` mà chưa kiểm tra điều kiện hoàn thành khóa học, tenant và người học.
4. Không có inventory/owner hoặc alert sử dụng scope phát hành bất thường khiến sự cố phát hiện muộn.

**Cách thiết kế lại:**

- Cấp key chỉ có `courses.read`, gắn với tenant/project và môi trường phù hợp.
- Nếu sau này cần phát hành chứng chỉ, tạo một key riêng cho workflow đó với `certificates.issue`, owner, phê duyệt và quota phù hợp.
- Không ghi secret vào log; nếu đã lộ, thu hồi key, kiểm tra lịch sử sử dụng và cấp key mới.
- Certificate API kiểm tra scope, tenant, quyền trên learner/course, kết quả hoàn thành và idempotency trước khi phát hành.
- Theo dõi key ID, hành động, tenant, kết quả và số lượng request để phát hiện lạm dụng.

**Bài tập:** Nếu integration cần đọc khóa học ở ba tenant, nên dùng một key không giới hạn hay ba key riêng? Một lựa chọn dễ kiểm soát là cấp key theo từng tenant nếu quy trình vận hành cho phép; nếu dùng một key đa tenant, danh sách tenant phải được khai báo rõ, có owner/phê duyệt và mọi request vẫn kiểm tra tenant phía server.

## 12. Checklist thiết kế key scope

- [ ] Mỗi key có owner, mục đích, client/service và môi trường rõ ràng.
- [ ] Scope tách theo resource và action; tách đọc, ghi, xóa, quản trị và thao tác nhạy cảm.
- [ ] Không cấp wildcard hoặc quyền rộng nếu integration không cần.
- [ ] Gắn key với tenant/project; không tin tenant ID tự khai từ request.
- [ ] Phân biệt scope, role, permission, policy, quota và network restriction.
- [ ] Thực thi mapping route/method → permission ở server; không tin scope do client gửi.
- [ ] Kiểm tra object-level authorization và điều kiện nghiệp vụ sau khi scope đạt.
- [ ] Tạo key ngẫu nhiên có entropy cao; chỉ hiển thị secret khi tạo.
- [ ] Truyền qua TLS/header; không đặt key trong URL, source code, frontend bundle hoặc log.
- [ ] Lưu verifier/hash/HMAC phù hợp và bảo vệ pepper/secret trong KMS hoặc secret manager.
- [ ] Có expiry, rotation, revoke, inventory và rà soát quyền định kỳ.
- [ ] Rate limit, quota, giám sát bất thường và quy trình xử lý key bị lộ.
- [ ] Kiểm thử cả request được phép lẫn request sai scope, sai tenant, key hết hạn hoặc bị thu hồi.
- [ ] Không dùng API key để giả định user đã xác thực hoặc đã ủy quyền hành động.

## 13. Câu hỏi tự kiểm tra

**1. API key hợp lệ có nghĩa là caller được gọi mọi endpoint không?**  
Không. Key phải còn hoạt động, đúng môi trường và đáp ứng scope, tenant, resource policy cùng điều kiện nghiệp vụ.

**2. Scope `invoices.read` có cho phép đọc hóa đơn của mọi tenant không?**  
Không. Scope giới hạn hành động; tenant binding và object-level authorization giới hạn dữ liệu được truy cập.

**3. Scope khác quota như thế nào?**  
Scope trả lời “được làm gì”; quota trả lời “được làm bao nhiêu hoặc với tốc độ nào”.

**4. API key có chứng minh người dùng cuối đã đăng nhập MFA không?**  
Không. API key thường đại diện cho client/service. Nếu cần hành động nhân danh user, phải dùng cơ chế delegation và truyền ngữ cảnh xác thực được bảo vệ.

**5. Vì sao không nên nhúng API key nhạy cảm vào frontend?**  
Vì người sử dụng hoặc attacker có thể trích xuất secret từ bundle, bộ nhớ hoặc request. Hạn chế referrer/origin chỉ giảm một số cách lạm dụng, không biến secret thành bí mật.

**6. Vì sao cần key riêng cho từng integration?**  
Để phân tách owner, scope, môi trường, audit và thu hồi. Một key dùng chung làm tăng phạm vi ảnh hưởng và khó xác định nguồn sự cố.

**7. Nếu scope bị giảm trong database, token/key đã phát hành có chắc mất quyền ngay không?**  
Không nhất thiết. Hiệu lực phụ thuộc cách API tra scope, cache, token tự chứa, introspection và cơ chế thu hồi.

**8. Key bị lộ cần xử lý những gì ngoài việc tạo key mới?**  
Thu hồi key cũ, xác định phạm vi scope/tenant, rà soát log và hành động, đánh giá dữ liệu bị truy cập, xoay secret liên quan và khắc phục nơi làm lộ key.

**Ghi nhớ:** Key scope giới hạn những gì một API key được phép làm. Hãy thiết kế theo **resource + action + tenant**, áp dụng least privilege, kiểm tra quyền phía server, bảo vệ key như bearer secret và quản lý đầy đủ vòng đời. Scope chỉ là một phần của authorization; nó không thay thế kiểm tra quyền trên đối tượng, ngữ cảnh người dùng hoặc điều kiện nghiệp vụ.
