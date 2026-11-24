# API key audit — Kiểm toán vòng đời và hoạt động sử dụng API key

> **Chương:** API key  
> **Chủ đề:** API key audit  
> **Phạm vi:** Security Authentication Fundamentals — quản lý, xác minh, theo dõi, thu hồi API key; liên kết danh tính máy/dịch vụ, kiểm soát quyền và phát hiện lạm dụng đăng nhập bằng credential dạng bearer.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích API key đại diện cho chủ thể nào và phân biệt xác thực API key với phân quyền request.
2. Thiết kế vòng đời API key gồm tạo, cấp phát, lưu giữ, sử dụng, luân chuyển, thu hồi và hết hạn.
3. Xác định sự kiện cần ghi nhận khi cấp key, thay đổi quyền, xác minh key, sử dụng API và thu hồi.
4. Thiết kế audit log có thể truy nguyên nhưng không làm lộ key hoặc dữ liệu nhạy cảm.
5. Phát hiện các mẫu sử dụng bất thường như key bị chia sẻ, lộ lọt, dùng sai scope, credential stuffing hoặc truy cập sau khi revoke.
6. Xây dựng quy trình điều tra, xoay vòng và thu hồi key mà vẫn duy trì khả năng vận hành của tích hợp hợp lệ.

## 1. API key là gì và vì sao cần audit?

**API key** là một credential được cấp cho client, ứng dụng hoặc workload để chứng minh quyền kiểm soát một giá trị bí mật khi gọi API. Máy chủ xác minh key và ánh xạ nó tới một principal, integration hoặc service account. Sau đó hệ thống áp dụng chính sách phân quyền tương ứng.

API key thường được dùng trong:

- Backend service gọi một API của nền tảng khác;
- Script tự động hóa hoặc tác vụ định kỳ;
- Tích hợp đối tác, webhook và hệ thống dữ liệu;
- Công cụ quản trị hoặc ứng dụng nội bộ;
- Một số API công khai cần định danh client và áp quota.

Phần lớn API key hoạt động như **bearer credential**: ai có được giá trị bí mật và gửi đúng cách có thể sử dụng key, trừ khi hệ thống bổ sung cơ chế ràng buộc khác. Vì vậy, key bị lộ có thể cho phép attacker mạo danh integration được cấp key.

**API key audit** là hoạt động ghi nhận và phân tích vòng đời cũng như cách sử dụng key để trả lời:

1. Ai hoặc hệ thống nào đã yêu cầu tạo key?
2. Key thuộc principal, tenant, ứng dụng và môi trường nào?
3. Key được cấp những quyền gì, thời hạn nào và ai phê duyệt?
4. Khi nào key được sử dụng, từ đâu, gọi API nào và kết quả ra sao?
5. Có dấu hiệu key bị chia sẻ, lộ lọt, dùng sai mục đích hoặc vượt quyền không?
6. Key đã được rotate/revoke chưa; các hệ thống phụ thuộc đã ngừng chấp nhận key cũ chưa?

Audit tốt giúp điều tra sự cố, kiểm soát quyền tối thiểu, đáp ứng yêu cầu quản trị và phát hiện tích hợp không còn cần thiết. Nó không tự ngăn mọi cuộc tấn công; cần kết hợp xác minh, authorization, rate limit, quản lý secret và giám sát.

## 2. API key xác thực điều gì?

Khi một request chứa API key hợp lệ, máy chủ có thể kết luận rằng request trình bày credential đã được cấp cho một principal hoặc integration. Điều này **không tự chứng minh**:

- Người thật nào đang thao tác phía sau integration;
- Máy gửi request là thiết bị được quản lý;
- Request chỉ được dùng cho mục đích ban đầu;
- Chủ thể có quyền trên mọi endpoint hoặc mọi tenant;
- Key chưa bị sao chép sang một máy khác;
- Request là hợp lệ về nghiệp vụ hoặc do người dùng cuối chấp thuận.

### Phân biệt authentication và authorization

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Identification** | Request đang khai báo principal nào? | Key ID ánh xạ tới integration đồng bộ kho |
| **Authentication** | Request có trình bày đúng credential của principal đó không? | Máy chủ xác minh secret của API key |
| **Authorization** | Principal có quyền gọi endpoint và thao tác này không? | Chỉ được đọc đơn hàng của tenant được cấp |
| **Accounting/audit** | Request đã làm gì, lúc nào và kết quả ra sao? | Ghi sự kiện đọc dữ liệu đơn hàng, status và request ID |

Một key hợp lệ nhưng gọi endpoint hoàn tiền ngoài scope phải bị từ chối. **Không dùng việc xác thực key thành công làm quyết định phân quyền duy nhất.**

### API key khác access token thế nào?

| Thuộc tính | API key | OAuth access token |
| --- | --- | --- |
| Vai trò thường gặp | Định danh client/integration hoặc service | Cấp quyền truy cập resource server theo grant/scope |
| Định dạng | Thường là chuỗi opaque có secret ngẫu nhiên | Có thể opaque hoặc JWT |
| Vòng đời | Có thể dài hạn cho đến khi hết hạn/rotate/revoke | Thường ngắn hạn; có thể được cấp lại bằng refresh token |
| Thu hồi | Thường tra cứu trạng thái key phía server | Tùy opaque introspection, JWT TTL, denylist hoặc cơ chế khác |
| Danh tính người dùng cuối | Không tự mang danh tính end-user | Có thể đại diện user hoặc client tùy grant |

Không nên gọi mọi chuỗi trong header Authorization là API key. Phải hiểu credential được phát hành theo mô hình nào để audit đúng chủ thể và quyền.

## 3. Vòng đời API key cần kiểm toán

Một key nên có trạng thái và chủ sở hữu rõ ràng. Ví dụ vòng đời:

`````````mermaid
stateDiagram-v2
    [*] --> REQUESTED: Yêu cầu tạo key
    REQUESTED --> PENDING_APPROVAL: Kiểm tra mục đích và quyền
    PENDING_APPROVAL --> ACTIVE: Phê duyệt và phát hành
    PENDING_APPROVAL --> REJECTED: Từ chối
    ACTIVE --> ROTATING: Bắt đầu thay key
    ROTATING --> ACTIVE: Key mới hoạt động, key cũ còn grace period
    ROTATING --> REVOKED: Thu hồi key cũ
    ACTIVE --> EXPIRED: Hết hạn
    ACTIVE --> REVOKED: Thu hồi khẩn cấp hoặc không còn cần
    EXPIRED --> [*]
    REVOKED --> [*]
    REJECTED --> [*]
`````````

Sơ đồ là mô hình minh họa; hệ thống có thể dùng các trạng thái khác. Cần định nghĩa chính xác trạng thái nào được xác minh và trạng thái nào không được chấp nhận.

| Giai đoạn | Sự kiện cần audit | Câu hỏi kiểm soát |
| --- | --- | --- |
| Request | Người yêu cầu, principal, mục đích, owner, tenant | Có nhu cầu nghiệp vụ và chủ sở hữu chịu trách nhiệm không? |
| Approval | Người duyệt, thời điểm, policy/version, lý do | Người duyệt có quyền? Có cần tách nhiệm vụ? |
| Issuance | Key ID, prefix, scope, expiry, môi trường | Secret được hiển thị một lần và truyền an toàn chưa? |
| Activation | Thời điểm key bắt đầu có hiệu lực | Key có được kích hoạt sau kiểm tra đúng không? |
| Usage | Request, endpoint, principal, kết quả, nguồn | Có đúng scope và hành vi dự kiến không? |
| Rotation | Key mới/cũ, overlap, owner, thời hạn | Các consumer đã chuyển sang key mới chưa? |
| Revocation | Ai thu hồi, lý do, thời điểm, propagation | API nào còn chấp nhận key cũ? |
| Expiration | Hết hạn, lần sử dụng cuối, owner | Có key cũ không còn dùng nhưng chưa thu hồi không? |

### Mỗi key cần có chủ sở hữu

Không nên phát key mà không biết ai chịu trách nhiệm. Một record metadata có thể gồm:

`````````yaml
api_key:
  key_id: key_7f2a91
  owner_type: service_account
  owner_id: inventory-sync
  tenant_id: tenant-42
  environment: production
  scopes:
    - orders.read
  created_at: "2026-11-22T05:00:00Z"
  expires_at: "2027-02-20T05:00:00Z"
  status: active
  last_used_at: null
`````````

Đây là metadata minh họa, không phải định dạng chuẩn. **Không lưu giá trị secret thô trong record này.** Key ID là định danh công khai/không bí mật để tra cứu và audit; nó không phải credential.

## 4. Phát hành và lưu API key an toàn

### Sinh key

Key cần được tạo bằng **cryptographically secure random number generator (CSPRNG)** với entropy đủ lớn. Tránh dùng timestamp, số thứ tự, email, tenant ID hoặc chuỗi có thể đoán làm secret.

Một định dạng thực tế có thể tách:

- **Prefix/key ID:** hỗ trợ tra cứu nhanh và nhận diện môi trường, không phải bí mật;
- **Secret:** phần ngẫu nhiên có entropy cao, chỉ hiển thị cho người tạo tại thời điểm cấp;
- **Metadata:** owner, tenant, scope, expiry, status, creation/approval reference.

Ví dụ định dạng minh họa:

`````````
ak_prod_<public-key-id>_<random-secret>
`````````

Không dùng đúng chuỗi ví dụ này làm key thực tế. Prefix giúp phân biệt môi trường hoặc loại key và có thể hỗ trợ tìm kiếm khi key bị lộ; không nên nhúng dữ liệu cá nhân hay quyền hạn nhạy cảm vào prefix.

### Lưu verifier thay vì lưu secret rõ

Thông thường server chỉ cần kiểm tra key được gửi có khớp với credential đã cấp. Có thể lưu:

- Key ID/prefix để tìm record;
- Hash hoặc HMAC verifier của secret;
- Metadata và trạng thái key;
- Thông tin phiên bản thuật toán/pepper để hỗ trợ rotation.

API key được tạo với entropy cao khác mật khẩu người dùng. Hash mật mã phù hợp có thể dùng để lưu verifier; HMAC với pepper được giữ trong KMS/secret store là một lớp bảo vệ bổ sung khi database bị lộ. Lựa chọn cụ thể phụ thuộc định dạng, entropy và threat model.

**Không lưu key plaintext để tiện hiển thị lại.** Nếu người dùng mất secret, quy trình đúng thường là tạo key mới và thu hồi key cũ.

### Truyền và sử dụng

- Dùng HTTPS/TLS.
- Gửi qua header được quy định rõ, chẳng hạn Authorization hoặc header API key chuyên biệt.
- Không truyền secret trong query string, URL, browser history hoặc referrer.
- Không đặt key trong source code, repository, image/container layer hoặc file cấu hình công khai.
- Dùng secret manager, vault hoặc cơ chế cấp secret runtime phù hợp.
- Hạn chế quyền đọc secret và tránh đưa key vào log, tracing, crash dump hay thông báo hỗ trợ.

## 5. Audit log: cần ghi những gì?

Audit nên phân thành **sự kiện quản trị vòng đời** và **sự kiện sử dụng trong runtime**.

### Sự kiện vòng đời

| Event | Trường dữ liệu gợi ý |
| --- | --- |
| api_key.requested | Request ID, actor, owner, tenant, purpose, requested scopes |
| api_key.approved | Approver, approval policy, reason code, timestamp |
| api_key.issued | Key ID, prefix, owner, scopes, expiry, environment |
| api_key.updated | Key ID, trường metadata thay đổi, before/after an toàn |
| api_key.rotated | Old/new key ID, overlap start/end, actor, reason |
| api_key.revoked | Key ID, actor, reason, timestamp, incident/change reference |
| api_key.expired | Key ID, expiry, owner, last-used reference |
| api_key.reenabled | Nếu hệ thống cho phép, actor, approval và lý do |

### Sự kiện sử dụng

| Event/field | Mục đích |
| --- | --- |
| event_id, occurred_at | Định danh sự kiện và thời điểm server ghi nhận |
| request_id, trace_id | Nối log gateway, application và downstream |
| key_id | Xác định key đã được sử dụng mà không lưu secret |
| principal_id, owner_id, tenant_id | Biết key đại diện cho chủ thể và phạm vi nào |
| auth_result, reason_code | Thành công, key không hợp lệ, revoked, expired hoặc bị rate limit |
| method, route, operation | Endpoint và thao tác đã gọi |
| http_status, latency_ms | Kết quả và đặc tính vận hành |
| source_ip, user_agent | Tín hiệu điều tra; phải tuân thủ chính sách dữ liệu |
| scope_decision | Scope nào được yêu cầu, cho phép hoặc từ chối |
| environment, service_name | Phân biệt production/staging và dịch vụ tiếp nhận |
| bytes_in, bytes_out | Hỗ trợ phát hiện bất thường lưu lượng khi phù hợp |
| rate_limit_decision | Theo dõi abuse và throttling |

### Những dữ liệu tuyệt đối không ghi vào audit thông thường

- Secret API key đầy đủ;
- Authorization header nguyên vẹn;
- Password, OTP, TOTP seed, private key hoặc refresh token;
- Query/body có chứa secret hoặc dữ liệu cá nhân không cần thiết;
- Giá trị credential được che một phần nhưng vẫn đủ để tái tạo secret.

Nếu cần điều tra một key cụ thể, dùng **key ID** hoặc một fingerprint an toàn đã được thiết kế trước. Không ghi lại secret chỉ để tiện tìm kiếm.

## 6. Thiết kế audit log có thể tin cậy

Audit log chỉ có ích khi dữ liệu đầy đủ, có nguồn tin và khó bị sửa/xóa trái phép.

### Nguyên tắc

1. **Server-side generation:** event về xác thực và quyết định quyền phải do gateway/verifier/resource server đáng tin phát ra, không lấy kết quả do client tự khai.
2. **Append-oriented:** ưu tiên thêm sự kiện mới; không sửa âm thầm lịch sử khi owner, scope hoặc trạng thái thay đổi.
3. **Integrity:** kiểm soát quyền ghi/xóa, lưu bản sao độc lập hoặc cơ chế chống sửa đổi phù hợp.
4. **Time integrity:** đồng bộ thời gian, lưu timestamp phía server và xử lý độ trễ event.
5. **Correlation:** nối các event qua request ID, trace ID, change ID và key ID.
6. **Access control:** tách quyền đọc audit, quản trị key và xóa dữ liệu theo retention.
7. **Retention:** giữ dữ liệu theo mục đích, yêu cầu pháp lý và chính sách; xóa/ẩn danh đúng thời hạn.
8. **Data minimization:** chỉ ghi IP, user agent, payload metadata hoặc định danh người dùng khi thực sự cần và được phép.

### Phân biệt audit trail với application log

| Application log | Audit trail |
| --- | --- |
| Hỗ trợ debug và vận hành | Hỗ trợ truy nguyên hành động và trách nhiệm |
| Có thể có mức chi tiết kỹ thuật cao | Có schema và sự kiện nghiệp vụ ổn định |
| Thường có retention ngắn hơn | Có retention và kiểm soát toàn vẹn theo chính sách |
| Có thể sampling ở một số môi trường | Không nên bỏ mất sự kiện bảo mật bắt buộc do sampling |
| Có thể thay đổi format thường xuyên | Cần versioning schema và khả năng đối chiếu |

Một hệ thống có thể gửi cùng sự kiện tới cả log vận hành và audit store, nhưng hai mục tiêu không giống nhau. Debug log không tự thay thế audit trail.

## 7. Kiểm soát authorization và scope của API key

API key thường đại diện cho client/service account. Vì key có thể tồn tại lâu, **least privilege** rất quan trọng.

Một key nên được giới hạn theo:

- **Principal/owner:** một integration hoặc service account riêng, tránh dùng key chung cho nhiều ứng dụng.
- **Tenant:** chỉ dữ liệu của tổ chức được cấp.
- **Environment:** tách production, staging và development.
- **Scope/action:** chỉ các thao tác thực sự cần, ví dụ orders.read thay vì quyền quản trị toàn bộ.
- **Resource:** giới hạn dự án, kho dữ liệu, nhóm endpoint hoặc tài nguyên cụ thể.
- **Expiry:** thời hạn phù hợp với mục đích và chu kỳ vận hành.
- **Rate/quota:** giới hạn request, burst, chi phí và mức tiêu thụ.

### Mẫu authorization

`````````
authorizeApiRequest(keyRecord, request):
    require(keyRecord.status == ACTIVE)
    require(not keyRecord.expired)
    require(keyRecord.environment == request.environment)
    require(keyRecord.tenantId == request.tenantId)
    require(request.action in keyRecord.scopes)
    require(resourceBelongsToAllowedScope(request.resource, keyRecord))
    enforceRateAndQuota(keyRecord, request)
    return ALLOW
`````````

Đây là pseudocode minh họa. Các giá trị tenantId, action và resource phải được xác định/kiểm tra ở phía server theo dữ liệu đáng tin; không tin client gửi tenant ID rồi tự coi đó là phạm vi được phép.

**Một key hợp lệ không đồng nghĩa request hợp lệ.** Ví dụ key của dịch vụ báo cáo có scope đọc đơn hàng; nếu gọi endpoint xóa đơn hàng, API phải từ chối và audit quyết định đó.

### Key dùng chung làm mất khả năng quy trách nhiệm

Nếu năm hệ thống dùng cùng một key, log chỉ cho biết key đó đã gọi API. Rất khó xác định ứng dụng nào bị lộ hoặc hệ thống nào tạo lưu lượng bất thường. Nên cấp **một key riêng cho mỗi integration/workload**, có owner và vòng đời riêng. Nếu API cần biết người dùng cuối đứng sau dịch vụ, hãy dùng cơ chế delegated identity hoặc token on-behalf-of phù hợp; đừng suy ra danh tính end-user từ API key của service.

## 8. Phát hiện sử dụng API key bất thường

Audit cần được phân tích theo baseline và bối cảnh. Một key có thể hợp lệ về mặt mật mã nhưng đang bị dùng sai.

### Dấu hiệu đáng chú ý

| Dấu hiệu | Ví dụ | Hành động điều tra |
| --- | --- | --- |
| **Nguồn mới/bất thường** | Key vốn chỉ dùng từ hạ tầng cố định đột nhiên xuất hiện từ quốc gia hoặc ASN khác | Kiểm tra owner, deployment và khả năng key bị lộ |
| **Thay đổi khung giờ** | Job chỉ chạy ban đêm bắt đầu gửi request liên tục ban ngày | Xác minh lịch triển khai hoặc automation trái phép |
| **Tăng đột biến request** | Lưu lượng tăng gấp nhiều lần baseline | Xem xét loop lỗi, scraping hoặc abuse |
| **Endpoint mới** | Key chỉ đọc dữ liệu bắt đầu gọi endpoint export/xóa | Kiểm tra scope, thay đổi ứng dụng và privilege escalation |
| **Tăng tỷ lệ lỗi** | Nhiều lần thử key sai hoặc 401/403 | Credential stuffing, key cũ, cấu hình sai hoặc replay |
| **Nhiều IP đồng thời** | Cùng key xuất hiện từ nhiều mạng không liên quan | Có thể bị chia sẻ hoặc lộ secret |
| **Sử dụng sau revoke** | Request tiếp tục mang key đã thu hồi | Kiểm tra propagation, cache và consumer chưa rotate |
| **Key không hoạt động lâu** | Key nhiều tháng không có request nhưng vẫn active | Xác nhận owner và thu hồi key dư thừa |
| **Truy cập dữ liệu bất thường** | Response size lớn, export nhiều tenant | Kiểm tra data exfiltration và authorization |
| **Tạo key hàng loạt** | Một actor tạo nhiều key hoặc scope rộng bất thường | Kiểm tra quyền admin, automation và approval |

Không có dấu hiệu đơn lẻ nào chứng minh chắc chắn key bị xâm phạm. VPN, cloud deployment, failover hoặc thay đổi nhà cung cấp có thể tạo nguồn IP mới hợp lệ. Kết hợp nhiều tín hiệu, xác minh với owner và đối chiếu change record trước khi kết luận.

### Ví dụ rule phát hiện

`````````
IF key.status == ACTIVE
AND request.source_asn NOT IN key.approved_asns
AND request.rate > key.baseline_rate * 5
THEN alert("API_KEY_USAGE_ANOMALY")
`````````

Rule này chỉ minh họa. Baseline, ngưỡng và danh sách nguồn cần phù hợp với workload; một ngưỡng cố định có thể tạo nhiều false positive hoặc bỏ lọt tấn công chậm.

## 9. Rotation và revocation

API key dài hạn làm tăng thời gian attacker có thể sử dụng credential sau khi bị lộ. **Rotation** thay key cũ bằng key mới; **revocation** ngừng chấp nhận key.

### Rotation có overlap

Một quy trình rotation có thể:

1. Xác minh owner và quyền yêu cầu rotate.
2. Sinh key mới, lưu verifier và phát secret một lần qua kênh an toàn.
3. Cấp key mới với scope/tenant/environment tương đương hoặc hẹp hơn theo review.
4. Cập nhật consumer sang key mới.
5. Theo dõi request của cả key cũ và mới trong một grace period được giới hạn.
6. Thu hồi key cũ đúng thời điểm; xác minh gateway/resource server đã ngừng chấp nhận.
7. Audit kết quả và thông báo hoàn tất cho owner.

Không để grace period vô thời hạn. Nếu key cũ bị nghi lộ, ưu tiên **revoke khẩn cấp** thay vì giữ overlap để tiện chuyển đổi.

### Revoke khẩn cấp khi key bị lộ

- Đánh dấu key revoked tại nguồn có thẩm quyền.
- Phân phối trạng thái revoke tới gateway và resource API; xử lý cache/replica.
- Chặn request mới, dừng job hoặc integration đang dùng key.
- Xác định thời gian nghi bị lộ và truy vấn audit theo key ID.
- Kiểm tra các thao tác đã thực hiện, dữ liệu đã đọc/xuất và downstream credentials có thể bị ảnh hưởng.
- Cấp key mới sau khi xác minh owner, làm sạch môi trường và thu hẹp scope.
- Lưu incident/change reference và theo dõi việc key cũ còn xuất hiện hay không.

### Độ trễ thu hồi

Nếu API gateway cache trạng thái key, một key đã revoke có thể còn được chấp nhận trong khoảng thời gian cache tồn tại. Cần đặt SLA rõ, ví dụ “request dùng key đã revoke phải bị từ chối trong tối đa X giây từ khi commit revoke”. X là yêu cầu kiến trúc theo rủi ro, không phải một giá trị chung cho mọi hệ thống.

Với endpoint nhạy cảm, có thể kiểm tra trạng thái key/credential tại nguồn đáng tin hoặc dùng cơ chế invalidation nhanh. Không chỉ dựa vào việc key đã biến mất khỏi UI quản trị.

## 10. Điều tra sự cố bằng audit trail

Khi phát hiện key có dấu hiệu bị lộ, điều tra theo trình tự:

1. **Xác định key:** tra cứu bằng key ID/prefix/fingerprint; không yêu cầu người dùng gửi secret qua chat hoặc ticket.
2. **Xác định phạm vi:** owner, tenant, environment, scopes, endpoints và hệ thống phụ thuộc.
3. **Xác định thời gian:** lần sử dụng hợp lệ cuối, thời điểm bất thường đầu tiên, thời điểm phát hiện và thời điểm revoke.
4. **Tìm hoạt động đáng ngờ:** nguồn mới, burst, endpoint bất thường, lỗi xác thực, response size và hành động ghi/xóa.
5. **Đối chiếu thay đổi:** deployment, rotation, ticket, approval và thay đổi network.
6. **Chặn và bảo toàn bằng chứng:** revoke key, thu thập audit liên quan và bảo vệ tính toàn vẹn.
7. **Đánh giá tác động:** dữ liệu bị đọc/xuất, thay đổi nghiệp vụ, token hoặc credential downstream có thể bị lộ.
8. **Khôi phục:** cấp key mới với scope tối thiểu, cập nhật consumer và theo dõi hành vi.
9. **Rút kinh nghiệm:** nguyên nhân gốc, thời gian phát hiện/thu hồi, lỗ hổng logging hoặc quyền quá rộng.

### Ví dụ truy vấn audit

`````````sql
SELECT
    occurred_at,
    key_id,
    principal_id,
    source_ip,
    method,
    route,
    http_status,
    reason_code,
    request_id
FROM api_key_usage_audit
WHERE key_id = :key_id
  AND occurred_at >= :incident_start
  AND occurred_at < :incident_end
ORDER BY occurred_at;
`````````

Đây là SQL minh họa. Cần giới hạn quyền truy vấn, phân vùng dữ liệu theo thời gian, bảo vệ định danh và không đưa secret vào điều kiện truy vấn.

### Không thể kết luận từ audit thiếu dữ liệu

Nếu gateway chỉ ghi 401/200 mà không ghi key ID, route hoặc request ID, điều tra có thể không xác định được request nào do key cụ thể tạo ra. Ngược lại, nếu ghi toàn bộ Authorization header, log trở thành kho credential thứ hai. Audit schema phải cân bằng **khả năng truy nguyên và bảo vệ secret**.

## 11. Multi-tenant và attribution

Trong SaaS nhiều tenant, API key phải gắn với phạm vi tenant ở phía server. Những câu hỏi cần kiểm tra:

- Key được tạo trong tenant nào?
- Principal sở hữu key có được phép gọi resource của tenant khác không?
- Tenant ID trong request có được so sánh với tenant gắn trong key không?
- Key có thể được chia sẻ giữa các tenant hay chỉ dùng trong một integration?
- Khi tenant đóng hoặc subscription hết hạn, key có bị disable/revoke không?

Không để client tự thay tenant ID trong request để mở rộng phạm vi. Mọi quyết định phải dựa trên **key record và policy đã được xác minh**, sau đó kiểm tra resource thực tế.

### Attribution cho người dùng cuối

API key của service account thường chỉ nhận diện service. Nếu service gọi API thay mặt nhiều nhân viên, audit có thể cần cả:

- **Calling principal:** integration/service account được xác thực bằng key;
- **Delegated subject:** người dùng cuối đã được xác thực theo một cơ chế riêng;
- **Actor/action context:** hành động cụ thể và nguồn ủy quyền;
- **Request/transaction reference:** liên kết với workflow nghiệp vụ.

Không ghi một user ID do client tùy ý gửi rồi coi đó là danh tính đã xác thực. Nếu cần delegated identity, dùng token hoặc assertion có chữ ký và audience/scope đúng, được kiểm tra theo giao thức.

## 12. Chính sách retention và quyền riêng tư của audit

Audit có thể chứa IP, user agent, tenant, principal, endpoint và thông tin sử dụng dịch vụ. Đây có thể là dữ liệu nhạy cảm hoặc dữ liệu cá nhân tùy bối cảnh.

Thiết kế cần:

- Xác định mục đích thu thập và trường dữ liệu tối thiểu;
- Giới hạn người có quyền đọc audit và theo dõi việc truy cập audit;
- Quy định retention theo yêu cầu bảo mật, hợp đồng và pháp luật áp dụng;
- Ẩn danh/pseudonymize dữ liệu khi có thể mà vẫn giữ khả năng điều tra;
- Bảo vệ log khi export sang SIEM, data lake hoặc nhà cung cấp bên ngoài;
- Tránh lưu payload nghiệp vụ đầy đủ nếu metadata đủ để phát hiện bất thường;
- Đảm bảo yêu cầu xóa dữ liệu không phá vỡ nghĩa vụ lưu giữ bắt buộc, và mọi ngoại lệ được phê duyệt.

Không nên giữ audit vô thời hạn “phòng khi cần”. Retention phải có căn cứ, kiểm soát và khả năng thực thi.

## 13. Tình huống thực tế: key của integration bị lộ

Một dịch vụ đồng bộ kho hàng dùng API key production có scope orders.read và inventory.write. Key được cấu hình trong biến môi trường của một worker. Sau một lần triển khai, key xuất hiện trong log debug do ứng dụng in toàn bộ header khi request lỗi.

Hai giờ sau, audit phát hiện cùng key được sử dụng từ một ASN lạ, gọi endpoint export dữ liệu đơn hàng với số lượng lớn và có tỷ lệ request tăng đột biến.

### Phân tích

1. Key là bearer credential; người lấy được secret có thể mạo danh integration.
2. Việc log Authorization header tạo thêm một bản sao secret ngoài secret manager.
3. Scope orders.read cho phép đọc dữ liệu, nhưng nếu API export không giới hạn tenant/volume thì có thể bị lạm dụng để trích xuất hàng loạt.
4. Audit theo key ID và request ID giúp liên kết hoạt động lạ mà không cần lưu secret.
5. Nếu key status bị cache lâu, revoke tại database chưa chắc ngăn request ngay lập tức.

### Xử lý đề xuất

1. Revoke key bị lộ và xác minh gateway/resource API đã chặn theo SLA.
2. Dừng hoặc tạm giữ worker, xóa log có secret theo quy trình bảo toàn bằng chứng và kiểm soát truy cập.
3. Tìm mọi request theo key ID trong cửa sổ nghi bị lộ; xác định dữ liệu đã xuất và thao tác ghi đã thực hiện.
4. Kiểm tra secret có nằm trong log aggregation, backup, CI artifact hoặc ticket không.
5. Tạo key mới với scope hẹp hơn; nếu integration chỉ cần đọc đơn hàng, bỏ inventory.write.
6. Cập nhật secret qua secret manager, triển khai consumer và xác minh không còn request bằng key cũ.
7. Bổ sung redaction cho Authorization header, kiểm thử log masking và cảnh báo ASN/volume bất thường.

### Bài học thiết kế

- Secret phải được redaction tại gateway, application logger, APM và tracing.
- Key riêng cho từng integration giúp khoanh vùng khi sự cố.
- Scope và quota phải giới hạn blast radius.
- Rotation phải được diễn tập; không chờ đến khi key bị lộ mới biết consumer nào sử dụng.
- Audit cần đủ dữ liệu để điều tra nhưng tuyệt đối không lưu secret.

## 14. Chỉ số vận hành và cảnh báo

| Chỉ số | Định nghĩa gợi ý | Giá trị sử dụng |
| --- | --- | --- |
| **Active key inventory** | Số key ACTIVE theo owner, tenant, environment và scope | Biết bề mặt credential đang tồn tại |
| **Unowned key count** | Key active không có owner/đơn vị chịu trách nhiệm | Phát hiện credential mồ côi |
| **Stale key count** | Key không sử dụng quá khoảng thời gian policy quy định | Tìm key dư thừa cần review/revoke |
| **Key age distribution** | Tuổi key từ lúc phát hành tới hiện tại | Đánh giá chu kỳ rotation |
| **Revocation propagation latency** | Thời gian từ commit revoke đến khi mọi điểm thực thi từ chối | Đo hiệu lực thu hồi |
| **Post-revocation accepted requests** | Request được chấp nhận sau mốc revoke có hiệu lực | Phát hiện lỗi cache/propagation |
| **Invalid key attempt rate** | Tần suất request trình bày key không hợp lệ | Phát hiện dò key hoặc cấu hình cũ |
| **Usage anomaly count** | Số alert từ nguồn, volume, endpoint hoặc thời gian bất thường | Theo dõi dấu hiệu lộ/lạm dụng |
| **Scope violation count** | Request bị từ chối do scope/tenant không phù hợp | Phát hiện integration gọi sai hoặc attacker thử vượt quyền |
| **Rotation completion rate** | Số rotation hoàn tất trước hạn / số rotation được lên kế hoạch | Đo kỷ luật quản trị secret |

Mẫu số cần được định nghĩa. Ví dụ “rotation completion rate 100%” không có ý nghĩa nếu danh sách key cần rotate chưa được kiểm kê. Cần đối soát inventory, owner và consumer thực tế.

### Cảnh báo nên ưu tiên

- Key revoked vẫn được chấp nhận;
- Key production xuất hiện ở môi trường staging/development hoặc nguồn không nằm trong baseline;
- Key có quyền quản trị được sử dụng từ workload mới;
- Một key gọi endpoint nhạy cảm ngoài scope;
- Key không có owner hoặc quá hạn nhưng vẫn active;
- Nhiều lần tạo/rotate/revoke key từ một actor bất thường;
- Key có volume/response size tăng đột biến;
- Audit ingestion bị gián đoạn hoặc event quan trọng bị thiếu.

## 15. Bộ kiểm thử chấp nhận

| Trường hợp | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| **Key hợp lệ** | Gọi endpoint trong scope | Request được xác thực, principal được ánh xạ đúng |
| **Key sai** | Gửi secret ngẫu nhiên | Từ chối, không lộ thông tin key hợp lệ |
| **Key hết hạn** | Gọi sau expiry | Từ chối |
| **Key revoked** | Gọi sau revoke | Từ chối theo SLA |
| **Sai tenant** | Key tenant A gọi resource tenant B | Từ chối ở server |
| **Sai scope** | Key chỉ read gọi endpoint write/delete | Từ chối và audit scope violation |
| **Sai environment** | Key staging gọi production | Từ chối nếu policy tách môi trường |
| **Header leak** | Tạo request lỗi và kiểm tra app/gateway/APM log | Secret không xuất hiện |
| **Query-string key** | Gửi key trong URL | Từ chối hoặc không hỗ trợ; URL/log không lưu secret |
| **Concurrent revoke** | Gọi API đồng thời với lúc key bị revoke | Hành vi theo mốc hiệu lực/SLA đã định |
| **Rotation overlap** | Chuyển consumer từ key cũ sang mới | Cả hai chỉ hoạt động trong cửa sổ đã phê duyệt; key cũ bị chặn sau đó |
| **Unowned key** | Tạo record không có owner | Không cho activate hoặc cảnh báo theo policy |
| **Key sharing** | Dùng một key từ nhiều integration không liên quan | Phát hiện anomaly/vi phạm chính sách nếu có |
| **Rate abuse** | Tăng request vượt quota | Throttling và audit |
| **Audit tampering** | Actor thử sửa/xóa lịch sử của mình | Bị ngăn hoặc có bản sao độc lập phát hiện |
| **Audit outage** | Làm gián đoạn pipeline ghi audit | Có buffer/alert và hành vi theo chính sách; không âm thầm mất event |
| **Credential rotation failure** | Consumer vẫn dùng key cũ sau hạn | Cảnh báo owner và từ chối key cũ |

Kiểm thử phải thực hiện trong môi trường được phép với key thử nghiệm. Không dùng key production thật để thử brute force, leak hoặc chia sẻ.

## 16. Checklist triển khai API key audit

- **Identity:** Mỗi key gắn với principal/owner, tenant, integration và environment rõ ràng?
- **Issuance:** Key có entropy cao, được tạo bằng CSPRNG, hiển thị secret một lần và có approval phù hợp?
- **Storage:** Server lưu verifier an toàn, không lưu plaintext, secret manager bảo vệ consumer?
- **Transport:** Key chỉ gửi qua HTTPS/header phù hợp; không xuất hiện trong URL, source code, log hoặc tracing?
- **Authorization:** Scope, tenant, resource, expiry, quota và rate limit được kiểm tra ở server?
- **Lifecycle:** Có request, approval, issue, activation, rotation, expiry và revoke với audit riêng?
- **Audit events:** Có key ID, principal, request ID, route, kết quả, timestamp và reason code?
- **Secret hygiene:** Authorization header, OTP, password, private key và token thô được redaction?
- **Integrity:** Audit có quyền đọc/ghi tách biệt, bảo vệ sửa/xóa và retention rõ?
- **Detection:** Có baseline theo key/owner, phát hiện nguồn mới, burst, endpoint lạ và post-revoke usage?
- **Incident response:** Có thể tìm key theo ID, revoke nhanh, xác định consumer và điều tra hoạt động?
- **Attribution:** Nếu cần danh tính end-user, có delegated identity được xác minh thay vì tin user ID từ client?
- **Offboarding:** Khi owner/service/tenant không còn hoạt động, key có được thu hồi?
- **Testing:** Đã kiểm thử sai key, sai scope, tenant isolation, rotation, revoke, concurrency và log redaction?

### Câu hỏi tự kiểm tra

1. Vì sao API key hợp lệ không đồng nghĩa request được phép thực hiện?
2. Tại sao không nên lưu secret API key dạng rõ để có thể hiển thị lại cho người dùng?
3. Một API key dùng chung cho nhiều integration làm suy giảm khả năng audit và ứng phó sự cố như thế nào?
4. Audit log cần những trường nào để điều tra một key bị lộ mà không lưu secret?
5. Nếu key đã revoke nhưng một gateway còn cache trạng thái ACTIVE, rủi ro nào xuất hiện và cần đo chỉ số gì?
6. Rotation có overlap khác revoke khẩn cấp như thế nào?
7. Vì sao API key của service không tự chứng minh danh tính người dùng cuối?
8. Khi nào cần dùng OAuth access token hoặc workload identity thay vì API key dài hạn?

## Kết luận

**API key audit phải bao quát cả vòng đời credential và từng lần sử dụng thực tế.** Một hệ thống có thể xác minh key đúng nhưng vẫn không an toàn nếu key không có owner, scope quá rộng, secret bị ghi vào log, không phát hiện hành vi bất thường hoặc revoke không lan tới mọi điểm thực thi. Thiết kế tốt dùng key ngẫu nhiên có entropy cao, lưu verifier thay vì secret rõ, gắn key với principal/tenant/environment, kiểm tra authorization riêng, ghi audit bằng key ID và request context, rồi giám sát rotation/revocation cùng độ trễ propagation. Audit cần đủ để truy nguyên và điều tra, đồng thời không biến log thành một kho credential mới.
