# Key rotation — Xoay vòng API key an toàn

**Key rotation** là quy trình thay một API key đang được sử dụng bằng key mới, cập nhật các thành phần phụ thuộc và thu hồi key cũ theo một trình tự có kiểm soát. Mục tiêu là giới hạn thời gian và phạm vi tác động nếu secret bị lộ, đáp ứng thay đổi nhân sự/hệ thống, giảm rủi ro từ key tồn tại quá lâu và duy trì hoạt động liên tục của client hợp lệ.

API key thường là credential dạng bearer: bất kỳ bên nào nắm giữ key và được endpoint chấp nhận đều có thể gửi request dưới danh tính/quyền gắn với key đó. Vì vậy rotation là một phần của **credential lifecycle** trong authentication. Nó phải gắn với chủ sở hữu, mục đích, quyền hạn, thời hạn, nơi lưu secret, cách phân phối, giám sát sử dụng và quy trình thu hồi. Xoay key mà không cập nhật client, hoặc giữ key cũ hoạt động vô thời hạn, không giải quyết được rủi ro.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao API key cần được xoay vòng và phân biệt rotation, renewal, replacement và revocation.
2. Thiết kế định dạng key có key identifier và secret ngẫu nhiên đủ entropy.
3. Lập inventory key theo owner, service, environment, scope, trạng thái và thời điểm sử dụng.
4. Xây dựng quy trình rotation có giai đoạn tạo mới, phân phối, chuyển đổi, quan sát và thu hồi.
5. Duy trì hoạt động khi nhiều instance, worker và client chuyển sang key mới theo thời điểm khác nhau.
6. Xử lý rotation định kỳ, rotation do nghi ngờ lộ key và tình huống mất quyền truy cập secret.
7. Bảo vệ key trong secret manager, CI/CD, log, backup và cấu hình runtime.
8. Viết kiểm thử chứng minh key mới hoạt động, key cũ bị thu hồi đúng lúc và key bị replay/đánh cắp được xử lý theo policy.

## 2. API key là credential gì?

API key là một giá trị do hệ thống cấp cho client hoặc workload để nhận diện và/hoặc xác thực request. Nó thường là một chuỗi khó đoán được gửi trong header, ví dụ:

~~~http
GET /v1/reports HTTP/1.1
Host: api.studyhub.example
Authorization: Bearer sk_live_<secret>
~~~

Đây chỉ là định dạng minh họa. API key có thể được truyền trong header riêng như X-API-Key, nhưng nên tránh đặt secret trong URL query string vì URL thường xuất hiện trong access log, browser history, proxy log, analytics và referrer.

**API key không tự động là danh tính người dùng.** Trong nhiều hệ thống, nó xác thực một integration, ứng dụng hoặc workload. API key cũng không tự mô tả đầy đủ quyền truy cập: server cần ánh xạ key sang owner, client identity, scope, tenant, environment và policy. Nếu key có quyền rộng, việc lộ key có thể dẫn tới truy cập lớn dù request vẫn đến qua HTTPS.

### 2.1. Phân biệt API key bí mật và public API key

| Loại | Mục đích | Có cần giữ bí mật? | Cách bảo vệ |
| --- | --- | --- | --- |
| **Secret API key** | Xác thực server-side integration hoặc workload | Có; ai có key có thể sử dụng quyền gắn với key | Secret manager, hạn chế scope, rotation, audit và revocation. |
| **Public/client API key** | Nhận diện project/app hoặc áp chính sách giới hạn ở client công khai | Không thể coi là bí mật khi nhúng trong browser/mobile app | Domain/app restrictions, quota, abuse detection; không cấp quyền nhạy cảm chỉ dựa vào key này. |

Không nhúng secret API key trong mã JavaScript frontend, ứng dụng mobile có thể giải mã, repository hoặc file cấu hình phát hành công khai. Nếu một SDK yêu cầu public API key, hãy kiểm tra nhà cung cấp định nghĩa key đó là identifier công khai hay bearer credential có quyền truy cập thực.

### 2.2. API key và các credential khác

| Credential | Chủ thể thường được nhận diện | Đặc điểm |
| --- | --- | --- |
| API key | Integration/client/workload | Thường là bearer secret; đơn giản, cần kiểm soát scope và rotation. |
| User password | Người dùng | Knowledge factor; cần password KDF và có thể bị phishing. |
| Passkey/WebAuthn | Người dùng + authenticator gắn với RP | Chữ ký public-key ràng buộc origin/RP ID; phù hợp đăng nhập người dùng chống phishing. |
| Client certificate/mTLS | Workload/client sở hữu private key | Xác thực bằng chứng sở hữu khóa; có vòng đời chứng chỉ và rotation riêng. |
| OAuth access token | Client được cấp quyền tới resource | Có audience, scope, thời hạn và cơ chế cấp/thu hồi riêng. |

Không nên dùng một API key tĩnh, quyền rộng và không hết hạn để thay thế toàn bộ hệ thống danh tính workload hoặc OAuth khi yêu cầu cần delegation, scope theo người dùng, audience hoặc token ngắn hạn.

## 3. Vì sao cần rotation?

Một API key có thể tồn tại lâu trong nhiều hệ thống: source code, biến môi trường, pipeline, secret manager, container, job nền, backup và log. Càng nhiều bản sao, càng khó biết key đã xuất hiện ở đâu. Rotation giúp thay credential cũ bằng credential mới và giới hạn khoảng thời gian sử dụng key có nguy cơ.

| Nguyên nhân | Rủi ro | Hành động |
| --- | --- | --- |
| Rotation theo lịch/chính sách | Key tồn tại quá lâu, khó phát hiện lộ lọt | Thay key theo chu kỳ dựa trên rủi ro và khả năng vận hành. |
| Nhân sự/nhà cung cấp rời hệ thống | Chủ thể cũ có thể còn biết secret | Xoay hoặc thu hồi key thuộc phạm vi truy cập của họ; rà soát quyền liên quan. |
| Key xuất hiện trong repository/log/ticket | Secret có thể đã được sao chép | Xem là compromised, revoke/rotate khẩn cấp và điều tra phạm vi lộ. |
| Thay đổi kiến trúc hoặc môi trường | Key cũ có thể còn quyền vượt nhu cầu | Tạo key mới với scope/owner/environment phù hợp, sau đó thu hồi key cũ. |
| Nghi ngờ truy cập bất thường | Không biết attacker còn giữ key không | Revoke ngay khi rủi ro yêu cầu, cấp key mới qua kênh an toàn và điều tra. |
| Yêu cầu audit/tuân thủ | Cần chứng minh vòng đời và trách nhiệm | Lưu metadata, phê duyệt, sự kiện rotation và bằng chứng thu hồi. |

Rotation định kỳ không thay thế phản ứng sự cố. Nếu key đã bị lộ, việc chờ tới kỳ rotation tiếp theo kéo dài thời gian attacker có thể truy cập. Ngược lại, xoay key quá thường xuyên mà không có inventory và tự động hóa có thể làm tăng lỗi vận hành, khiến đội ngũ tìm cách lưu key ở nơi không an toàn.

## 4. Inventory: biết key nào đang tồn tại và ai chịu trách nhiệm

Không thể xoay vòng có kiểm soát nếu không biết key đang được sử dụng ở đâu. Mỗi key nên có metadata quản lý, không chứa secret rõ:

| Trường metadata | Ý nghĩa |
| --- | --- |
| key_id / prefix | Định danh không bí mật để tra cứu key; không dùng nó làm bằng chứng xác thực. |
| Owner/team | Nhóm chịu trách nhiệm ứng dụng hoặc integration. |
| Client/workload | Thành phần thực sự sử dụng key. |
| Environment | Development, staging, production hoặc tenant tương ứng. |
| Scope/permissions | Tập API/action được phép; theo nguyên tắc least privilege. |
| Created/activated/expires/revoked at | Mốc thời gian vòng đời. |
| Last used at | Tín hiệu sử dụng; cần lưu theo policy và độ chính xác của telemetry. |
| Status | Pending, active, retiring, revoked hoặc expired. |
| Rotation generation | Phiên bản/generation để phân biệt key cũ và mới. |
| Distribution reference | Tham chiếu secret manager/path hoặc cơ chế phân phối, không phải secret. |

Mỗi key cần có **owner cụ thể**. Key không có owner, không có last-used evidence hoặc được dùng bởi nhiều hệ thống không rõ ràng là dấu hiệu cần rà soát. Không xóa key chỉ vì không thấy traffic trong thời gian ngắn nếu workload chạy theo tháng/quý; hãy kiểm tra lịch chạy và owner trước khi thu hồi.

### 4.1. Mỗi integration nên có key riêng

Tránh dùng chung một key cho nhiều ứng dụng, đội hoặc môi trường. Nếu một client bị lộ, key riêng giúp thu hồi đúng integration và giới hạn blast radius. Tách dev/staging/production; không dùng production secret trong máy phát triển cá nhân hoặc test fixture.

Nếu nhiều workload cần gọi API, cân nhắc danh tính workload, mTLS hoặc OAuth client credentials thay cho một key dùng chung. Nếu vẫn dùng API key, cấp key riêng cho từng workload và scope tối thiểu.

## 5. Thiết kế định dạng key và lưu trữ verifier

Một định dạng hữu ích tách **key identifier** và **secret**:

~~~text
sk_live_<key_id>.<random_secret>
~~~

- Prefix như sk_live_ cho biết loại/environment ở mức hiển thị; không dùng prefix để thay thế kiểm tra server-side.
- key_id là định danh ngẫu nhiên hoặc không thể đoán, dùng tra cứu record. Nó không phải secret.
- random_secret được tạo bằng CSPRNG với entropy đủ cao, không phải chuỗi tăng dần, timestamp, UUID yếu hoặc thông tin client.

Server tra cứu record bằng key_id, sau đó xác minh secret theo cách phù hợp. Vì secret API key nên có entropy cao và do server sinh, một lựa chọn phổ biến là lưu **HMAC/hash verifier** thay vì secret rõ, với pepper/key HMAC được quản lý tách biệt trong KMS/HSM hoặc secret manager. Khi xác minh, server tính verifier từ secret nhận được và so sánh an toàn. Nếu key do người dùng tự chọn hoặc entropy thấp, cần cân nhắc password KDF; không áp dụng máy móc một hàm băm nhanh cho secret yếu.

Ví dụ record khái niệm:

~~~text
ApiKeyRecord:
  key_id
  secret_verifier
  verifier_version
  owner_id
  client_id
  environment
  scopes
  status
  created_at
  activated_at
  expires_at
  last_used_at
  revoked_at
  rotation_generation
~~~

Không lưu secret rõ để có thể hiển thị lại. Khi tạo key, chỉ hiển thị secret một lần và yêu cầu client lưu vào secret manager. Nếu người dùng làm mất secret, cấp key mới và thu hồi key cũ theo policy thay vì cung cấp lại secret cũ.

### 5.1. So sánh secret an toàn

- Dùng thư viện mật mã chuẩn và so sánh verifier bằng hàm constant-time khi phù hợp.
- Không ghi secret hoặc verifier nhạy cảm vào log, trace, exception, metrics label hay audit event.
- Giới hạn độ dài header/request trước khi tính verifier để tránh tiêu thụ tài nguyên vô hạn.
- Tách quyền đọc metadata khỏi quyền quản lý secret; nhân viên vận hành không cần xem secret rõ.
- Bảo vệ khóa HMAC/pepper bằng KMS/HSM và có quy trình rotation riêng; đừng đặt pepper cạnh database verifier.

### 5.2. Đừng nhầm key ID với quyền

key_id chỉ giúp tìm record. Server phải lấy trạng thái, owner, scope, tenant và environment từ dữ liệu đáng tin cậy. Không cho client gửi role=admin, scope=* hoặc tenant_id rồi tin trực tiếp. Mọi quyết định authorization cần được thực hiện ở server theo policy.

## 6. Quy trình rotation an toàn, giảm downtime

Một rotation không khẩn cấp thường nên có giai đoạn **overlap có giới hạn**: key mới được tạo và phân phối trước; client chuyển sang key mới; server quan sát traffic; sau đó key cũ bị thu hồi. Overlap không được kéo dài vô hạn và không áp dụng khi key cũ đã bị compromise nghiêm trọng.

~~~mermaid
flowchart TD
    A["Inventory và xác định owner/client"] --> B["Tạo key mới, trạng thái pending"]
    B --> C["Phân phối secret qua secret manager"]
    C --> D["Cập nhật client và triển khai"]
    D --> E["Xác minh request bằng key mới"]
    E --> F["Quan sát traffic key cũ và mới"]
    F --> G{"Tất cả client hợp lệ đã chuyển?"}
    G -->|Chưa| H["Tìm client còn dùng key cũ, hỗ trợ migration"]
    H --> F
    G -->|Rồi| I["Thu hồi key cũ"]
    I --> J["Xác minh key cũ bị từ chối"]
    J --> K["Đóng rotation, audit và cập nhật inventory"]
~~~

### 6.1. Bước 1 — Lập kế hoạch

Xác định:
- Key nào sẽ xoay và lý do (định kỳ, thay đổi owner, nâng scope hay sự cố).
- Owner, mọi client/worker sử dụng key và nơi lưu secret.
- Endpoint, scope, tenant và environment bị ảnh hưởng.
- Thời gian overlap tối đa, thời điểm cutover và người chịu trách nhiệm.
- Tiêu chí thành công, cách quan sát traffic và cách xử lý rollback.

Nếu key bị nghi lộ, coi đây là incident: không ưu tiên một overlap dài chỉ để thuận tiện. Có thể phải thu hồi ngay, chấp nhận gián đoạn có kiểm soát và cấp key mới sau khi xác minh owner.

### 6.2. Bước 2 — Tạo key mới

Server tạo key mới với:
- key_id mới và secret ngẫu nhiên độc lập.
- Owner, client, environment và scope đã được kiểm tra.
- Trạng thái pending/active theo quy trình triển khai.
- Thời điểm tạo, hết hạn và generation mới.
- Audit event ghi ai yêu cầu, ai phê duyệt và lý do.

Không tái sử dụng secret cũ hoặc chỉ đổi prefix. Một key mới phải có secret mới với entropy độc lập.

### 6.3. Bước 3 — Phân phối secret

Phân phối secret qua secret manager hoặc kênh bảo mật có kiểm soát. Cập nhật CI/CD và runtime configuration để client có thể lấy key mới mà không in secret ra output.

Tránh:
- Gửi key trong email/chat/ticket không có bảo vệ phù hợp.
- Đặt secret vào command line, URL, source code hoặc build artifact công khai.
- In biến môi trường trong log khi debug.
- Đưa key vào image/container layer hoặc cache lâu dài không có kiểm soát.
- Lưu key trong file cấu hình được commit vào repository.

Nên có quyền truy cập theo workload identity, audit việc đọc secret và cơ chế rollback cấu hình. Khi cần deploy, hãy dùng secret reference thay vì truyền secret trực tiếp qua manifest.

### 6.4. Bước 4 — Chuyển client

Cập nhật client để dùng key mới. Với hệ thống nhiều instance, triển khai theo batch/canary:
1. Cập nhật một instance hoặc nhóm nhỏ.
2. Kiểm tra request thành công và scope đúng.
3. Theo dõi lỗi 401/403, latency và các chỉ số nghiệp vụ.
4. Mở rộng tới các instance còn lại.
5. Kiểm tra worker/job chạy theo lịch và client ít hoạt động.

Không gửi cả key cũ và key mới trong cùng request để “dự phòng”; server cần xác định credential được trình bày và audit chính xác. Nếu client hỗ trợ cấu hình active/next key, thiết kế rõ thứ tự ưu tiên và tránh vô tình gửi cả hai.

### 6.5. Bước 5 — Overlap có giới hạn và quan sát

Trong giai đoạn chuyển đổi, server có thể chấp nhận cả key cũ và key mới trong một khoảng thời gian đã định. Mỗi request cần được xác thực bằng **một key cụ thể**, sau đó server áp scope tương ứng. Ghi nhận key ID đã dùng, client và kết quả; không ghi secret.

Theo dõi:
- Tỷ lệ request dùng key mới so với key cũ.
- Owner/client vẫn gửi bằng key cũ.
- Request thất bại sau cutover.
- Nguồn bất thường tiếp tục dùng key cũ.
- Các batch/job ít chạy chưa được cập nhật.
- Scope/permission có thay đổi ngoài kế hoạch không.

Đặt deadline và người xử lý cho từng client còn lại. Không kéo dài overlap chỉ vì không biết key cũ còn được dùng ở đâu; cần truy vết owner và dependency.

### 6.6. Bước 6 — Thu hồi và xác minh

Khi đạt điều kiện cutover, chuyển key cũ sang trạng thái revoked. Server phải từ chối request dùng key đó kể cả khi secret vẫn còn trong client. Kiểm thử trực tiếp key cũ và quan sát traffic sau thu hồi.

Nếu vẫn có client hợp lệ dùng key cũ, quyết định rollback/migration dựa trên rủi ro:
- Nếu rotation thông thường và chưa có compromise, có thể tạm phục hồi key cũ trong cửa sổ rất ngắn, có phê duyệt và thời hạn rõ.
- Nếu key cũ bị lộ, không khôi phục key đó để giảm lỗi; sửa client hoặc cấp key mới khác.
- Sau khi hoàn tất, xóa secret cũ khỏi secret manager theo retention policy, nhưng giữ metadata/audit cần thiết để điều tra.

## 7. Trạng thái key và chuyển trạng thái

Một state machine giúp tránh key bị active vô thời hạn hoặc bị thu hồi quá sớm:

~~~mermaid
stateDiagram-v2
    [*] --> Pending: Tạo key mới
    Pending --> Active: Được phê duyệt/kích hoạt
    Pending --> Revoked: Hủy trước khi dùng
    Active --> Retiring: Bắt đầu rotation
    Retiring --> Revoked: Hết overlap và cutover
    Active --> Revoked: Compromise hoặc thu hồi khẩn cấp
    Active --> Expired: Hết hạn theo policy
    Retiring --> Revoked: Phát hiện compromise
    Revoked --> [*]
    Expired --> [*]
~~~

| Trạng thái | Server có chấp nhận? | Ý nghĩa |
| --- | --- | --- |
| Pending | Không, trừ khi thiết kế xác nhận riêng | Key đã tạo nhưng chưa được phép sử dụng. |
| Active | Có | Credential hiện hành. |
| Retiring | Có trong thời hạn overlap được phê duyệt | Đang chuyển đổi; cần giám sát và deadline. |
| Revoked | Không | Đã thu hồi; không thể kích hoạt lại nếu policy không cho phép. |
| Expired | Không | Hết hạn. |

Không dùng một boolean active mơ hồ để biểu diễn mọi trạng thái. Lưu thời điểm chuyển trạng thái, actor, lý do và generation. Một key đã revoked nên được coi là terminal; nếu cần quay lại sử dụng, tạo key mới.

## 8. Rotation trong hệ thống phân tán

Rotation thường khó ở chỗ client và server không cập nhật đồng thời. Các thành phần có thể gồm nhiều pod, VM, worker, queue consumer, cron job, serverless function và đối tác bên ngoài.

### 8.1. Cập nhật server trước client hay client trước server?

Với overlap có kiểm soát, server cần nhận biết key mới trước khi client chuyển sang dùng nó. Một trình tự phổ biến:
1. Server thêm record key mới ở trạng thái được phép dùng.
2. Secret mới được phân phối.
3. Client chuyển dần sang key mới.
4. Server quan sát và xác nhận key cũ không còn traffic hợp lệ.
5. Server revoke key cũ.

Nếu key cũ bị compromise, thứ tự thay đổi: revoke ngay, sau đó khôi phục client bằng key mới. Không được giữ key bị lộ hoạt động chỉ để chờ mọi client cập nhật.

### 8.2. Cache và replica

Nếu trạng thái key được cache ở nhiều API instance, revoke có thể không có hiệu lực tức thời. Cần xác định:
- TTL cache tối đa.
- Cơ chế invalidation/publish event khi revoke.
- Hành vi khi cache hoặc database không sẵn sàng.
- Thời gian lan truyền trạng thái đến tất cả region.
- Cách xử lý request đồng thời với thời điểm revoke.

Với key có quyền cao, có thể cần kiểm tra trạng thái tập trung hoặc cache ngắn. Nếu dùng cache, phải định lượng cửa sổ mà key revoked vẫn có thể được chấp nhận và chấp nhận rủi ro đó bằng policy.

### 8.3. Đồng bộ thời gian và lịch chạy

Job ít chạy có thể bỏ lỡ cửa sổ overlap. Hãy inventory cả batch theo lịch tuần/tháng, job khôi phục dữ liệu và integration theo mùa. Thời gian hết hạn/overlap cần dựa vào chu kỳ sử dụng thực tế, không chỉ dựa vào traffic liên tục.

## 9. Rotation khẩn cấp khi key bị lộ

Khi secret xuất hiện trong public repository, log, ticket, máy cá nhân bị mất hoặc nguồn không đáng tin, giả định key đã bị compromise cho tới khi chứng minh được điều ngược lại.

Quy trình phản ứng:
1. **Phân loại và cô lập:** xác định key ID, owner, scope, environment, tenant và hệ thống bị ảnh hưởng.
2. **Thu hồi nhanh:** revoke key ở server hoặc giảm scope ngay nếu cần; không chờ rotation theo lịch.
3. **Cấp credential mới:** tạo key mới có scope tối thiểu, phân phối qua secret manager đã kiểm soát.
4. **Khôi phục client:** cập nhật integration và kiểm tra request mới; nếu attacker còn quyền truy cập môi trường, xử lý nguồn xâm nhập trước khi cấp lại.
5. **Tìm dấu hiệu lạm dụng:** truy vấn audit log theo key ID, IP/source, endpoint, thời gian và hành động; đánh giá dữ liệu đã truy cập.
6. **Xoay secret liên quan:** kiểm tra các key khác dùng chung secret, tài khoản service, token, database credential hoặc pipeline secret có thể cùng bị lộ.
7. **Thông báo và lưu bằng chứng:** theo incident policy, giữ audit cần thiết, không đưa secret vào báo cáo.
8. **Hậu kiểm:** xác định nguyên nhân gốc, sửa nơi lưu/phân phối, bổ sung guardrail và cập nhật inventory.

Không giả định xóa key khỏi repository làm secret hết nguy hiểm. Git history, fork, cache, build log và bản clone có thể còn giữ giá trị. **Revoke/rotate là hành động chính; xóa bản sao là bước giảm phơi lộ tiếp theo.**

## 10. Bảo vệ API key trong lúc sử dụng

Rotation không thay thế kiểm soát mỗi request. Hệ thống nên:
- Dùng HTTPS/TLS và xác thực request ở server.
- Truyền key trong header, tránh query string.
- Giới hạn scope, tenant, endpoint, method và quota.
- Rate limit theo key ID, owner, client và tín hiệu nguồn.
- Gắn key với client/workload, không chỉ một chuỗi chung.
- Hỗ trợ expiration và revocation.
- Không ghi secret trong log; che header Authorization ở proxy/APM.
- Cảnh báo khi key dùng từ môi trường/nguồn bất thường.
- Dùng mTLS, OAuth hoặc workload identity cho yêu cầu cần ràng buộc mạnh hơn bearer key.

API key thường là bearer credential: nếu attacker lấy được key, họ có thể dùng nó từ một client khác cho đến khi key bị giới hạn hoặc thu hồi. IP allowlist có thể là lớp bổ sung nhưng không nên thay thế xác thực key, scope và giám sát; IP cũng có thể thay đổi hoặc dùng chung.

## 11. Pseudocode xác thực và rotation

Ví dụ logic kiểm tra request:

~~~text
authenticateApiRequest(request):
    keyId, presentedSecret = parseAuthorizationHeader(request)
    record = keyStore.lookup(keyId)

    if record is missing:
        rejectUnauthorized()

    if record.status not in allowedStatuses:
        rejectUnauthorized()

    if record.expiresAt <= now:
        rejectUnauthorized()

    candidateVerifier = verifierFor(presentedSecret, record.verifierVersion)
    if not constantTimeEqual(candidateVerifier, record.secretVerifier):
        recordFailedAttempt(keyId, request.source)
        rejectUnauthorized()

    enforceRateLimit(record.keyId, record.ownerId, request.source)
    enforceScopeAndTenant(record, request.method, request.path)
    auditUse(keyId, request.endpoint, request.result)
    allowRequest()
~~~

Ví dụ này lược bỏ chi tiết parsing, cache, database transaction, error handling và key management. Không trả lỗi khác nhau có thể giúp attacker dò key ID tồn tại. Cần áp rate limit trước và sau các bước phù hợp, đồng thời tránh ghi presentedSecret vào log hoặc exception.

Quy trình rotation logic:

~~~text
rotateKey(oldKeyId, owner, client, reason):
    authorizeRotationRequest(owner, oldKeyId)
    verifyApprovalsIfRequired(reason, oldKeyId)

    newSecret = secureRandomSecret()
    newKeyId = createUniqueKeyId()
    newRecord = createPendingRecord(
        newKeyId, verifier(newSecret), owner, client,
        leastPrivilegeScopes(oldKeyId), nextGeneration(oldKeyId)
    )
    storeSecretOnceInSecretManager(newKeyId, newSecret)
    activateAccordingToPolicy(newRecord)

    notifyOwnerAndClient(newKeyId)
    observeNewKeyTraffic()
    waitUntilCutoverCriteriaOrDeadline()

    if oldKeyCompromised:
        revoke(oldKeyId)
    else if allExpectedClientsMigrated:
        revoke(oldKeyId)
    else:
        escalateMigrationBlocker()

    verifyOldKeyRejected(oldKeyId)
    auditRotation(oldKeyId, newKeyId, reason)
~~~

Trong triển khai thật, không lưu secret trong biến/trace lâu hơn cần thiết; bảo đảm việc tạo record, lưu verifier, phân phối secret và kích hoạt có trạng thái nhất quán. Nếu lưu secret vào secret manager thất bại, key không được kích hoạt hoặc báo là đã phân phối thành công.

## 12. Kiểm thử và tiêu chí chấp nhận

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Key mới được tạo với key ID và secret mới | Key mới xác thực được sau khi active; secret chỉ hiển thị một lần. |
| Secret mới sai hoặc key ID không tồn tại | Request bị từ chối; không tiết lộ key ID hợp lệ. |
| Key cũ trong trạng thái retiring và còn trong overlap | Được chấp nhận đúng policy, ghi nhận key ID đã dùng. |
| Key cũ sau thời điểm revoke | Bị từ chối trên mọi instance/region theo SLA thu hồi. |
| Key mới có scope thấp hơn | Chỉ gọi được endpoint/action được phép; không thừa quyền từ key cũ. |
| Client chưa chuyển trước deadline | Tạo cảnh báo và xử lý theo policy; không tự kéo dài overlap vô hạn. |
| Rotation xảy ra khi worker/cron job không hoạt động | Job được phát hiện trong inventory và chuyển key trước khi chạy hoặc bị chặn an toàn. |
| Hai rotation request đồng thời cho cùng key | Có kiểm soát concurrency/idempotency; không tạo nhiều generation ngoài dự kiến. |
| Secret bị đưa vào log/trace | Kiểm thử phát hiện/redaction; không lưu giá trị secret. |
| Key bị lộ và cần revoke khẩn cấp | Revoke không phụ thuộc cửa sổ overlap; request mới bằng key cũ bị từ chối. |
| Cache chưa nhận revoke event | Cửa sổ chấp nhận cũ nằm trong giới hạn policy; kiểm thử invalidation. |
| Secret manager không sẵn sàng khi tạo key | Key không được báo active/phân phối thành công; transaction xử lý an toàn. |
| API key trong query string | Bị từ chối hoặc không được hỗ trợ; log/proxy không chứa secret. |
| Public API key bị sao chép từ browser | Không thể dùng riêng nó để truy cập endpoint nhạy cảm. |
| Key hết hạn | Server từ chối và trả phản hồi chuẩn hóa. |
| Owner bị thu hồi quyền | Key liên quan được rà soát/revoke theo policy và audit. |

## 13. Bài thực hành: rotation cho StudyHub

**Bối cảnh:** StudyHub có API cho đối tác đồng bộ danh sách lớp. Integration campus-sync-prod sử dụng secret API key trong production. Có ba worker chạy ở hai region, một cron job mỗi tuần và một đối tác bên ngoài. Key hiện tại có quyền đọc/ghi toàn bộ dữ liệu lớp, không có owner rõ ràng và chưa có ngày hết hạn.

### 13.1. Việc cần làm

1. **Inventory:** xác định owner, client, region, cron job, đối tác, scope và nơi lưu key hiện tại.
2. **Giảm quyền:** tạo key mới chỉ có scope cần thiết cho thao tác đồng bộ; tách read/write nếu nghiệp vụ cho phép.
3. **Lập kế hoạch rotation:** xác định overlap, lịch cron, cửa sổ đối tác cập nhật, tiêu chí cutover và người chịu trách nhiệm.
4. **Phân phối:** dùng secret manager, cập nhật worker theo canary và xác minh mỗi region.
5. **Quan sát:** theo dõi key ID cũ/mới, request fail, scope và hoạt động bất thường.
6. **Thu hồi:** revoke key cũ, kiểm thử từ chối ở cả hai region, cập nhật inventory và audit.
7. **Ứng phó compromise:** viết nhánh riêng cho tình huống key hiện tại đã xuất hiện trong repository công khai; xác định điều gì phải revoke ngay.

### 13.2. Câu hỏi tự đánh giá

1. Vì sao API key thường được xem là bearer credential?
2. Key ID và secret khác nhau thế nào? Thành phần nào có thể xuất hiện trong log?
3. Vì sao không nên dùng chung một API key cho dev, staging và production?
4. Overlap có ích gì và khi nào không nên dùng?
5. Làm sao biết tất cả client đã chuyển sang key mới nếu có cron job chạy hàng tuần?
6. Nếu key cũ bị lộ, vì sao không nên chờ hết overlap?
7. Cache và replica ảnh hưởng thế nào tới thời gian revoke?
8. Vì sao rotation phải kết hợp least privilege và owner inventory?
9. Public API key trong browser khác secret API key ra sao?
10. Làm thế nào chứng minh key cũ không còn được chấp nhận sau rotation?

**Tiêu chí hoàn thành:** Người học có thể lập inventory, tạo key mới độc lập, chuyển client có kiểm soát, chứng minh key cũ bị từ chối, xử lý trường hợp compromise và giải thích trách nhiệm của owner ở từng giai đoạn. Rotation chỉ được coi là hoàn tất khi **mọi dependency đã được xử lý, key cũ bị thu hồi và kết quả được audit**.

## 14. Vận hành và chỉ số theo dõi

Các chỉ số hữu ích:
- Số key active/retiring/pending/revoked theo environment và owner.
- Số key không có owner, không có expiry hoặc không có last-used evidence.
- Tuổi key và thời gian từ tạo tới rotation.
- Tỷ lệ request bằng key cũ trong overlap.
- Thời gian từ yêu cầu revoke tới khi mọi instance từ chối key.
- Số lỗi client sau cutover và thời gian phục hồi.
- Số sự cố key lộ, nguồn lộ và thời gian containment.
- Số key có scope rộng hơn nhu cầu hoặc được dùng chung nhiều workload.

Audit log cần ghi key ID, owner/client, thời gian, endpoint/action, kết quả và lý do rotation/revocation. Không ghi secret, header Authorization nguyên vẹn hoặc verifier nhạy cảm. Hạn chế quyền truy cập audit, có retention phù hợp và đồng bộ thời gian giữa các service.

Nên có cảnh báo cho key không có owner, key quá hạn, key retiring vượt deadline, key cũ tiếp tục được dùng sau cutover và key production được gọi từ nguồn không mong đợi. Quy trình vận hành phải có người chịu trách nhiệm và playbook rõ cho rotation định kỳ lẫn khẩn cấp.

## 15. Tài liệu nên đọc tiếp

- **OWASP Secrets Management Cheat Sheet**: lưu trữ, phân phối, rotation và thu hồi secret.
- **OWASP REST Security Cheat Sheet**: truyền credential, HTTPS, xác thực và bảo vệ API.
- **NIST SP 800-57**: nguyên tắc quản lý vòng đời vật liệu mật mã; tham chiếu khi quản lý khóa mật mã và hệ thống liên quan.
- **Cloud provider secret manager/KMS documentation**: IAM, versioning, rotation hooks, audit và cache.
- **OAuth 2.0 Security Best Current Practice**: khi thay API key tĩnh bằng access token, client credentials hoặc cơ chế ràng buộc sender.
- **OWASP ASVS**: biến yêu cầu quản lý secret và authentication thành tiêu chí xác minh.

Khi áp dụng vào sản phẩm thật, hãy xác định key là secret bearer hay public identifier, owner và blast radius, thời gian lan truyền cấu hình, cách revoke ở mọi instance và yêu cầu tuân thủ. **Rotation an toàn không chỉ là tạo một chuỗi mới: đó là chuyển đổi có kiểm soát toàn bộ dependency và chứng minh credential cũ đã hết hiệu lực.**
